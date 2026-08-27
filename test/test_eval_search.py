"""test/test_eval_search.py — the PURE parts of the Tier-B search measurement
(plan 2026-08-26-foresight-v25-v26, Task 9).

Deliberately no full fights here: one searched decision costs seconds, so the
suite covers what is cheap and easy to get wrong — the shard partition, the
top-k ordering and its tie-break, the injectivity of the salt/seed
derivations (the CRN discipline the whole measurement rests on), and the
expectimax control flow against a stub fork. The end-to-end behaviour is
covered by the timing smoke in the task report, not by pytest.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sts2_rl import forksim
from tools import eval_search


# ── shard math ──────────────────────────────────────────────────────────────


def test_shards_partition_the_fight_list_exactly():
    fights = list(enumerate(eval_search.build_fight_list(9, 150, seed=0)))
    for n in (1, 2, 3, 8, 10):
        shards = [eval_search.shard_of(fights, i, n) for i in range(n)]
        flat = [f for s in shards for f in s]
        assert sorted(flat) == sorted(fights)            # no loss, no dupes
        assert len(flat) == len(fights)
        assert max(len(s) for s in shards) - min(len(s) for s in shards) <= 1


def test_shard_keeps_global_fight_indices():
    """A shard's fights must carry their GLOBAL index — the salt derivation
    keys on it, so renumbering per shard would make two workers collide."""
    fights = list(enumerate(eval_search.build_fight_list(4, 12, seed=0)))
    assert [i for i, _ in eval_search.shard_of(fights, 1, 3)] == [1, 4, 7, 10]


def test_parse_shard():
    assert eval_search.parse_shard(None) == (0, 1)
    assert eval_search.parse_shard("3/8") == (3, 8)
    for bad in ("8/8", "-1/4", "1", "a/b", "1/0"):
        with pytest.raises(ValueError):
            eval_search.parse_shard(bad)


def test_fight_list_is_a_pure_function_and_cycles_the_bank():
    a = eval_search.build_fight_list(9, 150, seed=0)
    assert a == eval_search.build_fight_list(9, 150, seed=0)
    assert a != eval_search.build_fight_list(9, 150, seed=1)
    # every snapshot used within one lap, seeds all distinct
    assert [s for s, _ in a[:9]] == list(range(9))
    assert len({seed for _, seed in a}) == len(a)


# ── CRN seed derivations ────────────────────────────────────────────────────


def test_salts_are_shared_within_a_decision_and_disjoint_across_them():
    m = 8
    seen: dict[int, tuple[int, int]] = {}
    for fight in range(40):
        for d in range(30):
            base = eval_search._salt_base(fight, d, m)
            for j in range(m):
                salt = base + j
                assert salt not in seen, (
                    f"salt {salt} reused by {(fight, d)} and {seen[salt]}")
                seen[salt] = (fight, d)
    # ...and the m salts of one decision are exactly what every candidate
    # action of that decision shares (expectimax builds them off salt_base).
    base = eval_search._salt_base(3, 7, m)
    assert [base + j for j in range(m)] == list(range(base, base + m))


def test_rollout_seeds_and_act_seeds_live_in_disjoint_spaces():
    m = 8
    rollout = {eval_search._rollout_seed_base(f, d, m) + j
               for f in range(40) for d in range(30) for j in range(m)}
    act = {eval_search._act_seed(f, d) for f in range(40) for d in range(30)}
    assert len(rollout) == 40 * 30 * m
    assert len(act) == 40 * 30
    assert not (rollout & act)


def test_decision_index_rejects_an_overflowing_decision():
    with pytest.raises(ValueError):
        eval_search._decision_index(0, eval_search.MAX_DECISIONS)


# ── top-k ───────────────────────────────────────────────────────────────────


def test_top_k_takes_the_highest_prior_legal_actions_in_order():
    probs = np.array([0.0, 0.5, 0.1, 0.3, 0.1])
    mask = np.array([False, True, True, True, True])
    assert forksim.top_k_actions(probs, mask, 3) == [1, 3, 2]
    assert forksim.top_k_actions(probs, mask, 99) == [1, 3, 2, 4]


def test_top_k_skips_illegal_actions_even_at_high_prior():
    probs = np.array([0.9, 0.05, 0.05])
    mask = np.array([False, True, True])
    assert forksim.top_k_actions(probs, mask, 2) == [1, 2]


def test_top_k_breaks_exact_ties_by_ascending_action_id():
    probs = np.array([0.25, 0.25, 0.25, 0.25])
    mask = np.ones(4, dtype=bool)
    assert forksim.top_k_actions(probs, mask, 4) == [0, 1, 2, 3]


# ── expectimax control flow (stub fork, no engine) ──────────────────────────


class _StubEnv:
    """Just enough env for `expectimax`: a legality mask, plus the `_result`
    the terminal-vs-truncated split reads."""

    def __init__(self, mask, terminal=True):
        self._mask = np.asarray(mask, dtype=bool)
        self._result = object() if terminal else None

    def action_masks(self):
        return self._mask


class _StubFork:
    """Records every (prefix, action, salt) branch and returns a scripted
    score, so the CRN claim can be asserted directly rather than inferred.
    The branch envs are TERMINAL, which zeroes the bootstrap and makes a
    candidate's mean score exactly its scripted reward."""

    def __init__(self, scores):
        self.scores = scores          # {action: reward}
        self.calls = []

    def branch(self, actions, action, salt):
        self.calls.append((tuple(actions), int(action), int(salt)))
        return _StubEnv([True]), float(self.scores[int(action)]), True

    def rollout(self, env, policy, max_steps=120, gamma=0.999):
        raise AssertionError("scripted branches are terminal; no rollout expected")


class _StubPolicy:
    device = "cpu"
    model = None


def _patch_prior(monkeypatch, probs, mask):
    monkeypatch.setattr(forksim, "prior",
                        lambda policy, env: (np.asarray(probs), np.asarray(mask, dtype=bool)))


def test_expectimax_uses_the_same_salts_for_every_candidate(monkeypatch):
    _patch_prior(monkeypatch, [0.5, 0.3, 0.2], [True, True, True])
    fork = _StubFork({0: 0.0, 1: 1.0, 2: 0.0})
    res = forksim.expectimax(fork, [7, 7], _StubPolicy(), k=3, m=4,
                             env=_StubEnv([True] * 3), salt_base=1000)
    by_action: dict[int, list[int]] = {}
    for prefix, action, salt in fork.calls:
        assert prefix == (7, 7), "every branch must start from the same prefix"
        by_action.setdefault(action, []).append(salt)
    assert set(by_action) == {0, 1, 2}
    assert all(salts == [1000, 1001, 1002, 1003] for salts in by_action.values())
    assert res.n_rollouts == 12
    assert res.action == 1 and res.prior_argmax == 0 and res.flipped


def test_expectimax_ties_keep_the_prior_argmax(monkeypatch):
    """An exact score tie must not manufacture a flip."""
    _patch_prior(monkeypatch, [0.5, 0.3, 0.2], [True, True, True])
    fork = _StubFork({0: 1.0, 1: 1.0, 2: 1.0})
    res = forksim.expectimax(fork, [], _StubPolicy(), k=3, m=2,
                             env=_StubEnv([True] * 3))
    assert res.action == res.prior_argmax == 0
    assert not res.flipped


def test_expectimax_declines_a_forced_decision(monkeypatch):
    """One legal action is not a decision: no branches, no rollouts, and it
    must never be counted as a searched decision or a flip."""
    _patch_prior(monkeypatch, [0.0, 1.0, 0.0], [False, True, False])
    fork = _StubFork({1: 0.0})
    res = forksim.expectimax(fork, [], _StubPolicy(), k=5, m=8,
                             env=_StubEnv([False, True, False]))
    assert res.action == 1 and not res.searched and not res.flipped
    assert res.n_rollouts == 0 and fork.calls == []


def test_expectimax_honours_k(monkeypatch):
    _patch_prior(monkeypatch, [0.4, 0.3, 0.2, 0.1], [True] * 4)
    fork = _StubFork({0: 0.0, 1: 0.0, 2: 0.0, 3: 9.0})
    res = forksim.expectimax(fork, [], _StubPolicy(), k=2, m=1,
                             env=_StubEnv([True] * 4))
    assert res.candidates == (0, 1)
    assert res.action == 0            # the 9.0 action was never a candidate


def test_expectimax_bootstraps_a_truncation_but_not_a_termination(monkeypatch):
    """`branch` collapses terminated/truncated into one flag. A terminal
    state has no future (bootstrap 0); a truncation is a harness artifact and
    must still take the leaf value, or a candidate that happens to run long
    is scored as if the fight had simply stopped."""
    _patch_prior(monkeypatch, [0.6, 0.4], [True, True])
    seen = []

    class _TruncFork(_StubFork):
        def branch(self, actions, action, salt):
            self.calls.append((tuple(actions), int(action), int(salt)))
            return _StubEnv([True], terminal=False), 0.0, True

    monkeypatch.setattr(forksim.CombatFork, "_leaf_value",
                        staticmethod(lambda env, policy: seen.append(env) or 5.0))
    res = forksim.expectimax(_TruncFork({0: 0.0, 1: 0.0}), [], _StubPolicy(),
                             k=2, m=1, env=_StubEnv([True, True]))
    assert len(seen) == 2                       # one leaf per candidate
    assert res.scores == pytest.approx((0.999 * 5.0, 0.999 * 5.0))


def test_expectimax_rejects_a_dead_decision(monkeypatch):
    _patch_prior(monkeypatch, [0.0, 0.0], [False, False])
    with pytest.raises(ValueError):
        forksim.expectimax(_StubFork({}), [], _StubPolicy(), k=1, m=1,
                           env=_StubEnv([False, False]))


# ── arm bookkeeping ─────────────────────────────────────────────────────────


def test_unresolved_fights_leave_both_rates_alone():
    totals = eval_search.ArmTotals()
    totals.add(eval_search.ArmResult(died=True, hp_out=0, decisions=5))
    totals.add(eval_search.ArmResult(died=False, hp_out=40, decisions=5))
    totals.add(eval_search.ArmResult(died=False, hp_out=1, decisions=512,
                                     unresolved=True))
    assert totals.fights == 3 and totals.scored == 2
    assert totals.death_rate == 0.5
    assert totals.mean_hp == 40.0       # the capped fight's hp is not averaged
    assert totals.mean_hp_all == 20.0   # ...and the death counts as a 0


def test_survivors_mean_can_flatter_the_arm_that_dies_more():
    """The survivorship trap the report warns about, pinned as a test: arm A
    dies in the fight it would have limped out of, and its survivors-only
    mean goes UP as a result. `mean_hp_all` is the honest comparison."""
    a, b = eval_search.ArmTotals(), eval_search.ArmTotals()
    a.add(eval_search.ArmResult(died=True, hp_out=0, decisions=1))    # the limp
    a.add(eval_search.ArmResult(died=False, hp_out=80, decisions=1))
    b.add(eval_search.ArmResult(died=False, hp_out=5, decisions=1))   # survived it
    b.add(eval_search.ArmResult(died=False, hp_out=80, decisions=1))
    assert a.mean_hp == 80.0 and b.mean_hp == 42.5   # A "wins" on survivors
    assert a.mean_hp_all == 40.0 and b.mean_hp_all == 42.5   # B wins honestly
    assert a.death_rate > b.death_rate


# ── the greedy (deconfounding) arm ──────────────────────────────────────────


def test_greedy_arm_action_rule_matches_expectimax_prior_argmax(monkeypatch):
    """The greedy arm must be the search arm with the search switched off —
    same action rule, same tie-break — or search-vs-greedy would not isolate
    the search. Both sides are checked on an exact tie, where a differing
    tie-break would show up."""
    probs = np.array([0.0, 0.4, 0.4, 0.2])
    mask = np.array([False, True, True, True])
    greedy = forksim.top_k_actions(probs, mask, 1)[0]   # the greedy arm's rule
    _patch_prior(monkeypatch, probs, mask)
    res = forksim.expectimax(_StubFork({1: 0.0, 2: 0.0, 3: 0.0}), [], _StubPolicy(),
                             k=3, m=1, env=_StubEnv(mask))
    assert greedy == res.prior_argmax == 1


def test_play_fight_rejects_an_unknown_arm():
    with pytest.raises(ValueError):
        eval_search.play_fight(None, None, 0, mode="argmax", k=1, m=1,
                               rollout_steps=1, gamma=0.999, device="cpu")


def test_three_arms_are_named():
    assert eval_search.ARMS == ("policy", "greedy", "search")


# ── json round trip + merge math ────────────────────────────────────────────


def _totals(**kw):
    t = eval_search.ArmTotals()
    for name, value in kw.items():
        setattr(t, name, value)
    return t


def test_arm_totals_json_round_trip():
    t = _totals(fights=7, deaths=2, unresolved=1, survivors=4, hp_sum=123,
                decisions=88, seconds=1.5, searched=60, flips=9,
                flips_vs_sample=20, rollouts=720, search_seconds=180.0)
    back = eval_search.ArmTotals.from_json(t.to_json())
    assert back == t
    assert set(t.to_json()) == set(eval_search.ArmTotals.FIELDS)


def test_merge_sums_counters_and_recomputes_rates(tmp_path):
    """The rule the sharded overnight run rests on: rates come from SUMMED
    numerators and denominators, never from averaged shard rates. The two
    shards here have deliberately lopsided sizes, where averaging the rates
    (0.5 and 0.1 -> 0.30) differs from the correct pooled rate (6/60 + ...)."""
    cfg = {"ckpt": "c.pt", "bank": "b.jsonl", "fights": 60, "k": 3, "m": 4,
           "asc": 10, "room": None, "seed": 0, "gamma": 0.999,
           "rollout_steps": 120, "shard": "0/2", "bank_usable": 9}
    a = {arm: _totals(fights=10, deaths=5, survivors=5, hp_sum=100, decisions=50)
         for arm in eval_search.ARMS}
    b = {arm: _totals(fights=50, deaths=5, survivors=45, hp_sum=900, decisions=250)
         for arm in eval_search.ARMS}
    eval_search.write_json(tmp_path / "a.json", a, cfg)
    eval_search.write_json(tmp_path / "b.json", b, dict(cfg, shard="1/2"))

    totals, config = eval_search.merge_json(
        [str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    t = totals["search"]
    assert t.fights == 60 and t.deaths == 10 and t.decisions == 300
    assert t.death_rate == 10 / 60                 # pooled, not (0.5+0.1)/2
    assert t.death_rate != pytest.approx((0.5 + 0.1) / 2)
    assert t.mean_hp == 1000 / 50
    assert config["shard"] == "merged(0/2,1/2)"
    assert config["k"] == 3 and config["ckpt"] == "c.pt"


def test_merge_refuses_shards_that_measured_different_things(tmp_path):
    cfg = {"ckpt": "c.pt", "bank": "b.jsonl", "fights": 60, "k": 3, "m": 4,
           "asc": 10, "room": None, "seed": 0, "gamma": 0.999,
           "rollout_steps": 120, "shard": "0/2", "bank_usable": 9}
    arms = {arm: eval_search.ArmTotals() for arm in eval_search.ARMS}
    eval_search.write_json(tmp_path / "a.json", arms, cfg)
    eval_search.write_json(tmp_path / "b.json", arms, dict(cfg, shard="1/2", k=5))
    with pytest.raises(ValueError, match="k"):
        eval_search.merge_json([str(tmp_path / "a.json"), str(tmp_path / "b.json")])


#: the config shape write_json emits, minus the shard label.
_MERGE_CFG = {"ckpt": "c.pt", "bank": "b.jsonl", "fights": 60, "k": 3, "m": 4,
              "asc": 10, "room": None, "seed": 0, "gamma": 0.999,
              "rollout_steps": 120, "device": "cpu", "bank_usable": 9}


def test_merge_refuses_a_repeated_shard_index(tmp_path):
    """Merging shard 0 twice would double-count that slice of the fight list
    and print a wrong-but-plausible rate, so it is a hard error."""
    arms = {arm: eval_search.ArmTotals() for arm in eval_search.ARMS}
    eval_search.write_json(tmp_path / "a.json", arms, dict(_MERGE_CFG, shard="0/2"))
    eval_search.write_json(tmp_path / "b.json", arms, dict(_MERGE_CFG, shard="0/2"))
    with pytest.raises(ValueError, match="already merged"):
        eval_search.merge_json([str(tmp_path / "a.json"), str(tmp_path / "b.json")])


def test_merge_warns_when_the_shards_do_not_cover_the_fight_list(tmp_path, capsys):
    """A missing shard is a biased-but-usable sample, so it warns rather than
    refusing — but it must never merge silently."""
    arms = {arm: eval_search.ArmTotals() for arm in eval_search.ARMS}
    eval_search.write_json(tmp_path / "a.json", arms, dict(_MERGE_CFG, shard="0/3"))
    eval_search.write_json(tmp_path / "b.json", arms, dict(_MERGE_CFG, shard="2/3"))
    eval_search.merge_json([str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    err = capsys.readouterr().err
    assert "incomplete merge" in err and "[1]" in err

    # the complete union says nothing
    eval_search.write_json(tmp_path / "c.json", arms, dict(_MERGE_CFG, shard="1/3"))
    eval_search.merge_json([str(tmp_path / p)
                            for p in ("a.json", "b.json", "c.json")])
    assert "incomplete merge" not in capsys.readouterr().err


def test_merge_refuses_shards_that_ran_on_different_devices(tmp_path):
    """device is in must_match: cpu and cuda rollouts are not the same
    measurement (different float kernels -> different search decisions)."""
    arms = {arm: eval_search.ArmTotals() for arm in eval_search.ARMS}
    eval_search.write_json(tmp_path / "a.json", arms, dict(_MERGE_CFG, shard="0/2"))
    eval_search.write_json(tmp_path / "b.json", arms,
                           dict(_MERGE_CFG, shard="1/2", device="cuda"))
    with pytest.raises(ValueError, match="device"):
        eval_search.merge_json([str(tmp_path / "a.json"), str(tmp_path / "b.json")])


def test_merge_refuses_a_stale_schema(tmp_path):
    path = tmp_path / "old.json"
    path.write_text('{"eval_search_schema": 0, "config": {}, "arms": {}}',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="eval_search_schema"):
        eval_search.merge_json([str(path)])


# ── shard aliasing ──────────────────────────────────────────────────────────


def test_shard_alias_warning_fires_exactly_when_a_shard_misses_snapshots():
    # gcd(3, 9) = 3: shard 0 sees only snapshots 0, 3, 6.
    assert eval_search.shard_alias_warning(3, 9)
    assert eval_search.shard_alias_warning(4, 8)
    # coprime, or unsharded: every shard reaches every snapshot
    assert eval_search.shard_alias_warning(8, 9) == ""
    assert eval_search.shard_alias_warning(1, 9) == ""


def test_shard_alias_warning_matches_the_snapshots_a_shard_actually_touches():
    """The warning's claim, verified against the real fight list rather than
    restated: at gcd(n, S) = g a shard touches exactly S/g snapshots."""
    from math import gcd

    for bank_size, n in ((9, 3), (9, 8), (8, 4), (10, 5), (9, 1)):
        fights = list(enumerate(eval_search.build_fight_list(bank_size, 120, 0)))
        for i in range(n):
            seen = {snap for _, (snap, _seed) in eval_search.shard_of(fights, i, n)}
            assert len(seen) == bank_size // gcd(n, bank_size)
        warned = bool(eval_search.shard_alias_warning(n, bank_size))
        assert warned == (n > 1 and gcd(n, bank_size) > 1)
