"""`search_worker --temperature` and `--min-score-gap`: the two target knobs.

v26's distillation memorized its shards partly because the targets it was
handed were near-uniform at T=1.0 — a distribution with almost no preference
in it teaches almost nothing except the identity of the records. These tests
pin the knob that lets a later calibration pass sharpen them: T=1.0 must stay
bit-for-bit what the worker wrote before the flag existed (so old shard sets
remain reproducible), a T below 1 must actually concentrate mass without
breaking the -1 pad convention, and the chosen T must reach `provenance.json`
so a shard set can be told apart from one written at another temperature.

The 08-28 calibration then found temperature ALONE cannot clear the bar: the
raw rollout scores are near-tied (median top1−top2 δ ≈ 0.016; 19.5% of records
have every candidate scored *exactly* equal, where a softmax is literally
temperature-invariant). So the second half of this file pins the source
filter that fixes it — `--min-score-gap G` drops a searched decision whose
δ ≤ G — including the boundary and the backward-compatible G = 0.0 default.
"""
import ast
import inspect
import json

import numpy as np
import pytest

from tools import search_worker


SCORES = [12.0, 11.5, 11.0, 9.0]
CANDS = [3, 17, 42, 8]
K = 6


def _valid(idx, prob):
    """The documented decode: `tgt_idx >= 0` masks both arrays."""
    keep = idx >= 0
    return idx[keep], prob[keep]


def test_temperature_one_reproduces_the_unparameterized_softmax():
    s = np.asarray(SCORES, dtype=np.float64)
    e = np.exp(s - s.max())
    want = (e / e.sum()).astype(np.float16)

    idx, prob = search_worker.targets_from_scores(CANDS, SCORES, K,
                                                  temperature=1.0)
    idx_d, prob_d = search_worker.targets_from_scores(CANDS, SCORES, K)

    # bit-for-bit, both through the explicit T=1.0 and through the default
    assert np.array_equal(prob[: len(CANDS)].view(np.uint16),
                          want.view(np.uint16))
    assert np.array_equal(prob.view(np.uint16), prob_d.view(np.uint16))
    assert np.array_equal(idx, idx_d)
    assert list(idx[: len(CANDS)]) == CANDS


def test_low_temperature_concentrates_mass():
    _, warm = search_worker.targets_from_scores(CANDS, SCORES, K,
                                                temperature=1.0)
    idx, cold = search_worker.targets_from_scores(CANDS, SCORES, K,
                                                  temperature=0.25)

    n = len(CANDS)
    assert cold[:n].max() > warm[:n].max()
    # still a distribution over the candidates present, never over the pad
    assert float(np.sum(cold[:n].astype(np.float64))) == pytest.approx(1.0,
                                                                      abs=1e-3)
    assert np.all(idx[n:] == -1)
    assert np.all(cold[n:].astype(np.float64) == -1.0)
    # the search's preference ordering is unchanged, only its sharpness
    assert list(np.argsort(-cold[:n].astype(np.float64))) == [0, 1, 2, 3]


@pytest.mark.parametrize("bad", [0.0, -0.5, -1.0])
def test_non_positive_temperature_raises(bad):
    with pytest.raises(ValueError):
        search_worker.targets_from_scores(CANDS, SCORES, K, temperature=bad)


def test_provenance_dict_carries_the_temperature(monkeypatch):
    """The stamp is built inline in `run_worker`; read the literal off the
    source so the assertion is about the dict that actually gets written,
    without standing up a whole worker run (bank, ckpt, envs, rollouts)."""
    tree = ast.parse(inspect.getsource(search_worker.run_worker))
    dicts = [n.value for n in ast.walk(tree)
             if isinstance(n, ast.Assign)
             and isinstance(n.value, ast.Dict)
             and any(isinstance(t, ast.Name) and t.id == "provenance"
                     for t in n.targets)]
    assert len(dicts) == 1, "expected exactly one `provenance = {...}` literal"
    keys = [k.value for k in dicts[0].keys if isinstance(k, ast.Constant)]
    assert "temperature" in keys
    value = dicts[0].values[keys.index("temperature")]
    assert isinstance(value, ast.Attribute) and value.attr == "temperature"

    # and the CLI supplies it, defaulting to the historical T=1.0
    captured = []
    monkeypatch.setattr(search_worker, "run_worker",
                        lambda args: (captured.append(args), 0)[1])

    def parse(extra):
        captured.clear()
        search_worker.main(["CKPT", "--bank", "b.jsonl", "--out", "d"] + extra)
        return captured[0]

    assert parse([]).temperature == 1.0
    assert parse(["--temperature", "0.4"]).temperature == 0.4


# ════════════════════════════════════════════════════════════════════════════
# --min-score-gap: the decisiveness filter (Task 4b, 2026-08-28)
# ════════════════════════════════════════════════════════════════════════════


def test_score_gap_is_top1_minus_top2_of_the_raw_scores():
    assert search_worker.score_gap([12.0, 11.5, 11.0, 9.0]) == pytest.approx(0.5)
    # order-independent: it is the top TWO, not the first two
    assert search_worker.score_gap([9.0, 11.0, 12.0, 11.5]) == pytest.approx(0.5)
    # negative scores are ordinary scores
    assert search_worker.score_gap([-3.0, -1.0, -9.0]) == pytest.approx(2.0)


def test_score_gap_of_all_equal_scores_is_zero():
    """19.5% of the calibration records looked exactly like this."""
    assert search_worker.score_gap([4.0, 4.0, 4.0, 4.0]) == 0.0


def test_score_gap_of_a_lone_candidate_is_infinite():
    """No second candidate to be tied with, so nothing to filter out."""
    assert search_worker.score_gap([7.5]) == float("inf")


def test_score_gap_needs_at_least_one_score():
    with pytest.raises(ValueError):
        search_worker.score_gap([])


@pytest.mark.parametrize("scores", [
    [12.0, 11.5, 11.0, 9.0],      # decisive
    [4.0, 4.0, 4.0, 4.0],         # exactly tied — the temperature no-op case
    [4.0, 4.0 - 1e-12],           # all but tied
    [7.5],                        # lone candidate
])
def test_the_default_gap_of_zero_keeps_everything(scores):
    """Backward compatibility: every pre-4b shard set was written unfiltered,
    and G=0.0 must mean 'no filter', NOT 'drop the exact ties'."""
    assert search_worker.is_decisive(scores, 0.0) is True


def test_any_positive_gap_drops_an_exactly_tied_decision():
    for g in (1e-9, 0.05, 1.0):
        assert search_worker.is_decisive([4.0, 4.0, 4.0], g) is False


def test_the_boundary_is_closed_the_skipped_way():
    """δ == G is SKIPPED — the filter keeps δ > G strictly, so the pinned
    v27 rule 'raw score gap > 0.05' means exactly what it says.

    Pinned on binary-exact values (0.5, 0.25): `1.05 - 1.0` is
    0.050000000000000044 in float64, which would test the FPU, not the rule.
    The 0.05-flavoured cases below stay well clear of that ULP.
    """
    assert search_worker.is_decisive([1.5, 1.0], 0.5) is False      # δ == G
    assert search_worker.is_decisive([1.75, 1.0], 0.5) is True      # δ  > G
    assert search_worker.is_decisive([1.25, 1.0], 0.5) is False     # δ  < G
    assert search_worker.is_decisive([1.06, 1.0], 0.05) is True
    assert search_worker.is_decisive([1.04, 1.0], 0.05) is False


def test_the_filter_ignores_the_candidates_below_the_top_two():
    """Only the top two decide: a decision whose 3rd and 4th are tied with
    each other is still decisive if its leader is clear."""
    assert search_worker.is_decisive([9.0, 1.0, 1.0, 1.0], 0.05) is True
    # ... and a decision whose LEADERS are tied is not, however spread the tail
    assert search_worker.is_decisive([9.0, 9.0, 1.0, -40.0], 0.05) is False


def test_a_lone_candidate_survives_any_filter():
    assert search_worker.is_decisive([7.5], 100.0) is True


def test_provenance_and_cli_carry_the_min_score_gap(monkeypatch):
    """Same source-level assertion as the temperature test: the stamp is an
    inline literal in `run_worker`, so read it off the AST rather than standing
    up a worker run (bank, ckpt, envs, rollouts)."""
    tree = ast.parse(inspect.getsource(search_worker.run_worker))
    dicts = [n.value for n in ast.walk(tree)
             if isinstance(n, ast.Assign)
             and isinstance(n.value, ast.Dict)
             and any(isinstance(t, ast.Name) and t.id == "provenance"
                     for t in n.targets)]
    assert len(dicts) == 1
    keys = [k.value for k in dicts[0].keys if isinstance(k, ast.Constant)]
    assert "min_score_gap" in keys
    value = dicts[0].values[keys.index("min_score_gap")]
    assert isinstance(value, ast.Attribute) and value.attr == "min_score_gap"

    captured = []
    monkeypatch.setattr(search_worker, "run_worker",
                        lambda args: (captured.append(args), 0)[1])

    def parse(extra):
        captured.clear()
        search_worker.main(["CKPT", "--bank", "b.jsonl", "--out", "d"] + extra)
        return captured[0]

    assert parse([]).min_score_gap == 0.0          # unfiltered by default
    assert parse(["--min-score-gap", "0.05"]).min_score_gap == 0.05


def test_a_negative_min_score_gap_is_rejected_by_the_cli():
    with pytest.raises(SystemExit):
        search_worker.main(["CKPT", "--bank", "b.jsonl", "--out", "d",
                            "--min-score-gap", "-0.1"])


def test_the_stats_dataclass_counts_searched_and_skipped():
    """`merge_distill` sums NUMERIC stats leaves automatically, so the two new
    counters only have to exist and be numbers."""
    s = search_worker.Stats()
    assert s.decisions_searched == 0
    assert s.skipped_indecisive == 0

    tree = ast.parse(inspect.getsource(search_worker.run_worker))
    stamped = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
               and any(isinstance(t, ast.Name) and t.id == "provenance"
                       for t in n.targets)][0]
    keys = [k.value for k in stamped.keys if isinstance(k, ast.Constant)]
    stats_dict = stamped.values[keys.index("stats")]
    stats_keys = [k.value for k in stats_dict.keys if isinstance(k, ast.Constant)]
    assert "decisions_searched" in stats_keys
    assert "skipped_indecisive" in stats_keys


def test_the_scoring_loop_applies_the_filter_to_the_rollout_scores():
    """The filter must read the SAME `res.scores` that `targets_from_scores`
    consumes — a filter on any other quantity would not be the one the v27
    calibration measured."""
    src = inspect.getsource(search_worker.run_worker)
    assert "is_decisive(res.scores, args.min_score_gap)" in src
    assert "skipped_indecisive" in src


# ════════════════════════════════════════════════════════════════════════════
# The driver's round loop — budget accounting and TERMINATION
#
# `run_worker` is exercised with the sim, the policy and the search all stubbed
# out: no CUDA, no env, no rollouts, no checkpoint. What is under test is the
# control flow the filter forced — that `--decisions` counts KEPT records, that
# a rejected decision is re-collected rather than abandoned, and above all that
# a bank of purely indecisive decisions terminates on `--max-fights` instead of
# spinning forever waiting for a budget it can never fill.
# ════════════════════════════════════════════════════════════════════════════

F_DIM, I_DIM, N_ACTIONS = 4, 3, 6


class _Res:
    def __init__(self, scores, searched=True, flipped=False):
        self.scores = list(scores)
        self.candidates = list(range(len(scores)))
        self.searched = searched
        self.flipped = flipped
        self.n_rollouts = 40


class _Space:
    def __init__(self, n):
        self.shape = (n,)


def _stub_worker(monkeypatch, tmp_path, *, score_pattern,
                 per_fight=3, **cli):
    """Run `run_worker` against stubs; return `(rc, provenance dict)`.

    `score_pattern` is a list of score vectors, cycled over the searched
    decisions, so a caller can make every decision tied, every decision
    decisive, or any mix.
    """
    real_run_worker = search_worker.run_worker

    captured = []
    monkeypatch.setattr(search_worker, "run_worker",
                        lambda args: (captured.append(args), 0)[1])
    argv = ["CKPT", "--bank", "b.jsonl", "--out", str(tmp_path / "out")]
    for flag, val in cli.items():
        argv += ["--" + flag.replace("_", "-"), str(val)]
    search_worker.main(argv)
    args = captured[0]

    class _Snap:
        room_type = "ELITE"          # so select_decisions keeps everything
        encounter_id = "stub"

    class _Env:
        _card_obs = "hybrid"
        observation_space = {"f": _Space(F_DIM), "i": _Space(I_DIM)}
        action_space = type("A", (), {"n": N_ACTIONS})()

    class _Layout:
        f_dim, i_dim = F_DIM, I_DIM

    fights_started = []

    def fake_collect(fork, policy, fight, snap_idx, room, *, device, stats):
        assert len(fights_started) < 10_000, "collection is not terminating"
        fights_started.append(fight)
        out = []
        for d in range(per_fight):
            stats.decisions += 1
            out.append(search_worker.Candidate(
                fight=fight, d=d, snap_idx=snap_idx, room=room,
                entropy=1.0 + 0.01 * d, prefix=(),
                f=np.zeros(F_DIM, dtype=np.float16),
                i=np.zeros(I_DIM, dtype=np.int32),
                mask=np.ones(N_ACTIONS, dtype=bool)))
        return out

    n_searched = [0]

    def fake_expectimax(*a, **kw):
        scores = score_pattern[n_searched[0] % len(score_pattern)]
        n_searched[0] += 1
        return _Res(scores)

    monkeypatch.setattr(search_worker, "_usable_snapshots",
                        lambda bank, rooms: ([_Snap(), _Snap()], 2, 0))
    monkeypatch.setattr(search_worker, "STS2RunEnv", lambda **kw: _Env())
    monkeypatch.setattr(search_worker, "run_obs_layout", lambda c: _Layout())
    monkeypatch.setattr(search_worker, "load_policy",
                        lambda args, env: (type("P", (), {"_generator": 1})(),
                                           {"obs_schema": 13, "arch": "entity"}))
    monkeypatch.setattr(search_worker, "CombatFork",
                        lambda snap, **kw: object())
    monkeypatch.setattr(search_worker, "collect_fight", fake_collect)
    monkeypatch.setattr(search_worker.forksim, "expectimax", fake_expectimax)

    rc = real_run_worker(args)
    prov_path = tmp_path / "out" / "provenance.json"
    prov = (json.loads(prov_path.read_text(encoding="utf-8"))
            if prov_path.is_file() else None)
    return rc, prov, len(fights_started)


DECISIVE = [10.0, 1.0, 0.5]
TIED = [4.0, 4.0, 4.0]


def test_unfiltered_the_driver_still_writes_exactly_the_budget(monkeypatch,
                                                               tmp_path):
    """G = 0.0: one round, `--decisions` records, nothing skipped — the
    pre-4b shape."""
    rc, prov, _ = _stub_worker(monkeypatch, tmp_path, score_pattern=[TIED],
                               decisions=5, k=5, shard_size=64)
    assert rc == 0
    assert prov["records"] == 5
    assert prov["stats"]["skipped_indecisive"] == 0
    assert prov["stats"]["decisions_searched"] == 5
    assert prov["stats"]["rounds"] == 1
    assert prov["min_score_gap"] == 0.0


def test_the_budget_counts_KEPT_records_not_searches(monkeypatch, tmp_path):
    """Every other decision is tied, so filling a 6-record budget must cost
    ~12 searches and more than one round of collection."""
    rc, prov, fights = _stub_worker(
        monkeypatch, tmp_path, score_pattern=[DECISIVE, TIED],
        decisions=6, k=5, shard_size=64, min_score_gap=0.05, per_fight=3)
    assert rc == 0
    assert prov["records"] == 6, "short of the budget the filter is supposed " \
                                 "to make the worker work harder for"
    assert prov["stats"]["searched"] == 6
    assert prov["stats"]["skipped_indecisive"] >= 5
    assert (prov["stats"]["decisions_searched"]
            == prov["stats"]["searched"] + prov["stats"]["skipped_indecisive"])
    assert prov["stats"]["rounds"] >= 2, "the filter must force a re-collect"
    assert fights > 2, "6 kept records at ~50% keep rate cannot come from 2 " \
                       "fights of 3 decisions"


def test_an_entirely_indecisive_bank_terminates_on_max_fights(monkeypatch,
                                                              tmp_path):
    """THE termination case. No decision can ever clear the gap, so the budget
    is unreachable; the worker must stop at `--max-fights` with an honest,
    short provenance rather than collecting forever."""
    rc, prov, fights = _stub_worker(
        monkeypatch, tmp_path, score_pattern=[TIED],
        decisions=50, k=5, shard_size=64, min_score_gap=0.05,
        max_fights=7, per_fight=3)
    assert rc == 0
    assert fights == 7                       # bounded by --max-fights exactly
    assert prov["records"] == 0
    assert prov["shards"] == []
    assert prov["stats"]["searched"] == 0
    assert prov["stats"]["skipped_indecisive"] == 21
    assert prov["stats"]["decisions_searched"] == 21


def test_a_decision_is_never_searched_twice_across_rounds(monkeypatch,
                                                          tmp_path):
    """`scored` has to hold, or a re-collect round would re-pay for every
    candidate the previous round already rejected."""
    rc, prov, fights = _stub_worker(
        monkeypatch, tmp_path, score_pattern=[TIED],
        decisions=50, k=5, shard_size=64, min_score_gap=0.05,
        max_fights=9, per_fight=4)
    assert rc == 0
    # 9 fights x 4 decisions, each searched exactly once
    assert prov["stats"]["decisions_searched"] == 36
    assert prov["stats"]["collected"] == 36
