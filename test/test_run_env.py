"""STS2RunEnv (sts2_rl/run_env.py): action layout, masks, observation
schema pins, greenlet lifecycle, and seeded determinism."""
import random

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind
from sts2_rl.full_env import combat_action_count, combat_obs_segments_f, combat_obs_segments_i
from sts2_rl.run_env import (
    CHOICE_BASE,
    CHOICE_SLOTS,
    GOLD_LOG_FINE_DENOM,
    MAX_POTION_SLOTS,
    MAX_SELECT_CANDIDATES,
    N_ACTIONS,
    N_COMBAT_ACTIONS,
    POTION_BASE,
    RUN_OBS_SCHEMA_VERSION,
    SELECT_BASE,
    STS2RunEnv,
    _log1p_scale,
    run_obs_layout,
    run_obs_segments_f,
    run_obs_segments_i,
)

_ENV = None


def shared_env():
    """Construction probes a CombatState, so share one env across tests."""
    global _ENV
    if _ENV is None:
        _ENV = STS2RunEnv()
    return _ENV


def masked_random_episode(env, seed, max_steps=20_000):
    rng = np.random.default_rng(seed)
    obs, info = env.reset(seed=seed)
    trajectory = []
    for _ in range(max_steps):
        mask = env.action_masks()
        assert mask.shape == (env.n_actions,) and mask.any()
        action = int(rng.choice(np.flatnonzero(mask)))
        obs, reward, terminated, truncated, info = env.step(action)
        trajectory.append((action, round(float(reward), 6), info["phase"]))
        if terminated or truncated:
            return trajectory, info, obs
    pytest.fail("episode did not finish")


# ═════════════════════════════════════════════════════════════════════════
# Layout pins
# ═════════════════════════════════════════════════════════════════════════

def test_action_layout():
    # RUN_OBS_SCHEMA_VERSION 12: {"f", "i"} Dict obs contract, SELECT_CARDS
    # uses a per-CANDIDATE-index block (MAX_SELECT_CANDIDATES wide, see
    # run_env.py's `_sorted_candidate_order`), MAX_POTION_SLOTS is the true
    # worst-case belt (base 3 + Phial Holster + Potion Belt + Alchemical
    # Coffer = 10). Recent version bumps (v8-v12) were observation-only
    # widenings (combat enemy row, intent history, REWARD_CARD_SLOTS,
    # glow_gold/block_preview_move) that don't affect this action layout.
    assert RUN_OBS_SCHEMA_VERSION == 12
    # Combat block sized for the true worst-case belt: 1 + 10×6 + 10×6 = 121.
    assert N_COMBAT_ACTIONS == combat_action_count(MAX_POTION_SLOTS) == 121
    assert CHOICE_BASE == 121
    assert SELECT_BASE == 121 + CHOICE_SLOTS == 137
    assert POTION_BASE == SELECT_BASE + MAX_SELECT_CANDIDATES == 233
    assert N_ACTIONS == POTION_BASE + MAX_POTION_SLOTS == 243
    env = shared_env()
    assert env.action_space.n == env.n_actions == N_ACTIONS


def test_obs_segments_sum_to_declared_dim():
    env = shared_env()
    segs_f = env.obs_segments_f()
    segs_i = env.obs_segments_i()
    assert sum(w for _, w in segs_f) == env.observation_space["f"].shape[0]
    assert sum(w for _, w in segs_i) == env.observation_space["i"].shape[0]
    # The named slice map tiles each half exactly.
    layout = run_obs_layout()
    assert sorted(s.stop for s in layout.f_slices.values())[-1] == layout.f_dim
    assert sorted(s.stop for s in layout.i_slices.values())[-1] == layout.i_dim
    # run_obs_segments_f/i (module-level) are the same lists minus the
    # trailing combat block that obs_segments_f/i() (and run_obs_layout)
    # fold in under a "combat." prefix.
    n_run_f = len(run_obs_segments_f())
    n_run_i = len(run_obs_segments_i())
    assert segs_f[:n_run_f] == run_obs_segments_f()
    assert segs_i[:n_run_i] == run_obs_segments_i()
    assert segs_f[n_run_f:] and all(n.startswith("combat.") for n, _ in segs_f[n_run_f:])
    assert segs_i[n_run_i:] and all(n.startswith("combat.") for n, _ in segs_i[n_run_i:])


def test_reset_obs_in_bounds():
    env = shared_env()
    obs, info = env.reset(seed=0)
    layout = run_obs_layout()
    assert obs["f"].shape == (layout.f_dim,)
    assert obs["i"].shape == (layout.i_dim,)
    assert obs["f"].min() >= 0.0 and obs["f"].max() <= 1.0
    assert obs["i"].min() >= 0
    assert info["phase"] == DecisionKind.EVENT.value   # Neow first
    # Neow: the event block is live and the phase one-hot says EVENT.
    assert obs["f"][layout.f_slices["event.present"]][0] == 1.0
    assert obs["f"][layout.f_slices["phase"]].sum() == 1.0
    # Not in combat: every combat.* segment is PAD id / zero float.
    for name, _w in combat_obs_segments_i():
        assert not obs["i"][layout.i_slices[f"combat.{name}"]].any(), name
    for name, _w in combat_obs_segments_f():
        assert not obs["f"][layout.f_slices[f"combat.{name}"]].any(), name


# ═════════════════════════════════════════════════════════════════════════
# Episodes
# ═════════════════════════════════════════════════════════════════════════

def test_masked_random_episode_terminates():
    env = shared_env()
    trajectory, info, obs = masked_random_episode(env, seed=1)
    assert "is_success" in info and "hp_left" in info
    assert info["floor"] >= 1
    assert obs["f"].min() >= 0.0 and obs["f"].max() <= 1.0
    assert obs["i"].min() >= 0


def test_seeded_episodes_are_deterministic():
    env = shared_env()
    t1, i1, _ = masked_random_episode(env, seed=7)
    t2, i2, _ = masked_random_episode(env, seed=7)
    assert t1 == t2
    assert i1["floor"] == i2["floor"] and i1["is_success"] == i2["is_success"]
    t3, _, _ = masked_random_episode(env, seed=8)
    assert t1 != t3


def test_illegal_action_is_noop():
    env = shared_env()
    obs, _ = env.reset(seed=2)
    mask = env.action_masks()
    illegal = int(np.flatnonzero(~mask)[0])
    obs2, reward, terminated, truncated, info = env.step(illegal)
    assert reward == 0.0 and not terminated
    np.testing.assert_array_equal(obs["f"], obs2["f"])   # nothing advanced
    np.testing.assert_array_equal(obs["i"], obs2["i"])
    assert np.array_equal(mask, env.action_masks())


def test_reset_mid_run_cleans_up_and_replays():
    env = STS2RunEnv()
    env.reset(seed=3)
    for _ in range(5):                        # abandon a run mid-flight
        mask = env.action_masks()
        env.step(int(np.flatnonzero(mask)[0]))
    glet = env._glet
    assert glet is not None and not glet.dead
    env.reset(seed=3)                         # kills the parked greenlet
    assert glet.dead
    t1, _, _ = masked_random_episode(env, seed=9)
    t2, _, _ = masked_random_episode(env, seed=9)
    assert t1 == t2
    env.close()
    assert env._glet is None or env._glet.dead


def test_phases_cover_the_run():
    # One random episode should visit the core phases; sweep seeds until the
    # rarer ones (shop, rest, rewards, select) have all appeared.
    env = shared_env()
    seen = set()
    for seed in range(30):
        trajectory, _, _ = masked_random_episode(env, seed=seed + 100)
        seen.update(phase for _, _, phase in trajectory)
        needed = {
            DecisionKind.MAP.value, DecisionKind.EVENT.value,
            DecisionKind.COMBAT.value, DecisionKind.REWARD_CARD.value,
            DecisionKind.SELECT_CARDS.value, DecisionKind.REST.value,
        }
        if needed <= seen:
            break
    assert DecisionKind.MAP.value in seen
    assert DecisionKind.EVENT.value in seen
    assert DecisionKind.COMBAT.value in seen
    assert DecisionKind.REWARD_CARD.value in seen


def test_run_vitals_track_engine_state():
    env = shared_env()
    env.reset(seed=4)
    layout = run_obs_layout()
    # Play a few steps, then check the vitals against the RunState.
    rng = np.random.default_rng(4)
    obs = None
    for _ in range(10):
        mask = env.action_masks()
        obs, *_ = env.step(int(rng.choice(np.flatnonzero(mask))))
    run = env._run
    hp = max(0, run.hp)
    f, i = obs["f"], obs["i"]
    assert f[layout.f_slices["run.hp_abs"]][0] == pytest.approx(min(1.0, hp / 100.0), abs=1e-6)
    # R6: run.gold is log1p-compressed, not clipped-linear.
    assert f[layout.f_slices["run.gold"]][0] == pytest.approx(
        _log1p_scale(run.gold, GOLD_LOG_FINE_DENOM), abs=1e-6)
    deck_ids = i[layout.i_slices["run.deck.ids"]]
    assert (deck_ids != 0).any()                          # the deck block is live
    relic_ids = i[layout.i_slices["run.relics.ids"]]
    assert int((relic_ids != 0).sum()) == len(run.relics)  # Neow's pick is visible


def test_combat_block_live_in_combat():
    env = shared_env()
    rng = np.random.default_rng(5)
    obs, _ = env.reset(seed=5)
    layout = run_obs_layout()
    for _ in range(5_000):
        if env._request is not None and env._request.kind == DecisionKind.COMBAT:
            break
        mask = env.action_masks()
        obs, _, term, trunc, _ = env.step(int(rng.choice(np.flatnonzero(mask))))
        assert not (term or trunc), "episode ended before reaching a combat"
    obs = env._build_obs()
    live = (
        any(obs["i"][layout.i_slices[f"combat.{name}"]].any()
            for name, _w in combat_obs_segments_i())
        or any(obs["f"][layout.f_slices[f"combat.{name}"]].any()
               for name, _w in combat_obs_segments_f())
    )
    assert live, "combat block must carry live features once in combat"
    phase = obs["f"][layout.f_slices["phase"]]
    assert phase[list(DecisionKind).index(DecisionKind.COMBAT)] == 1.0


def test_run_potions_block_reflects_live_combat_belt_not_stale_run_snapshot():
    # Round-6 obs-parity bug: `RunState.finish_combat` only syncs
    # `run.potions` from `combat.player.potions` when the combat ENDS, but
    # `run.potions` (the run-level belt obs, offset 0 of `run.potions.ids`)
    # is what player-facing UsePotion changes update live in the game — a
    # potion drunk MID-combat (e.g. via a SelectCards side-effect like Skill
    # Potion) empties its belt slot immediately in the game's own dump, but
    # the sim's `_build_obs` read `run.potions` (the RunState's own,
    # pre-combat-frozen list) instead of the live `combat.player.potions`,
    # so the obs kept showing the already-drunk potion until the combat's
    # `finish_combat` call. Confirmed against a real game dump: seed
    # 89U21BV1TZ act 0 floor 15's Combat decisions 4-13 show the belt's
    # slot 2 already empty (a Skill Potion drunk via the floor's SelectCards
    # decision), while the sim dump kept showing it filled for the whole
    # rest of the combat.
    from sts2_rl.potions import make_potion
    from sts2_rl.run_env import POTION_INDEX
    from sts2_rl.obs import oid

    env = shared_env()
    rng = np.random.default_rng(5)
    obs, _ = env.reset(seed=5)
    layout = run_obs_layout()
    for _ in range(5_000):
        if env._request is not None and env._request.kind == DecisionKind.COMBAT:
            break
        mask = env.action_masks()
        obs, _, term, trunc, _ = env.step(int(rng.choice(np.flatnonzero(mask))))
        assert not (term or trunc), "episode ended before reaching a combat"

    combat = env._request.combat
    assert combat is not None
    # Simulate "drunk mid-combat": the live combat belt's slot 0 is empty,
    # while the RunState's own (pre-combat, stale) snapshot still shows a
    # potion there -- exactly the divergence `finish_combat` would only
    # reconcile at combat end.
    combat.player.potions[0] = None
    env._run.potions[0] = make_potion("block_potion")

    obs = env._build_obs()
    ids = obs["i"][layout.i_slices["run.potions.ids"]]
    assert ids[0] == 0, (
        "run.potions.ids must reflect the LIVE in-combat belt "
        "(combat.player.potions), not RunState's stale pre-combat snapshot"
    )


class _InvincibleRunEnv(STS2RunEnv):
    """STS2RunEnv whose driver plays an effectively unkillable run, so a
    masked-random policy can clear all three acts and exercise the env's
    act-3 / final-boss-victory plumbing (a real policy dies long before)."""

    def _make_run_state(self):
        from sts2_rl.run import RunState

        return RunState(rng=self._rng, max_hp=100_000, hp=100_000)


def test_invincible_env_run_reaches_act3_and_wins():
    # Sweep seeds for a masked-random invincible run that beats the Glory
    # boss. A win must land in act 3 (act_index 2), report is_success, carry
    # a positive terminal reward (the win bonus), and keep the act-3 one-hot
    # lit with obs still in bounds (floor normalization never saturates).
    env = _InvincibleRunEnv()
    layout = run_obs_layout()
    rng = np.random.default_rng(0)
    for seed in range(25):
        obs, info = env.reset(seed=seed)
        saw_act3_onehot = False
        max_act = info["act"]
        reward = 0.0
        for _ in range(30_000):
            mask = env.action_masks()
            obs, reward, term, trunc, info = env.step(int(rng.choice(np.flatnonzero(mask))))
            max_act = max(max_act, info["act"])
            if info["act"] == 2:
                onehot = obs["f"][layout.f_slices["run.act"]]
                assert onehot[2] == 1.0 and onehot.sum() == 1.0
                saw_act3_onehot = True
            assert obs["f"].min() >= 0.0 and obs["f"].max() <= 1.0
            assert obs["i"].min() >= 0
            if term or trunc:
                break
        if info.get("is_success"):
            assert max_act == 2                    # a win means clearing Glory
            assert saw_act3_onehot
            assert reward > 0.0                    # includes the victory bonus
            return
    pytest.fail("no invincible env run won in 25 seeds")


def test_select_phase_masks_candidate_indices():
    # Force a run-level selection through the env: hunt a seed whose random
    # episode passes a SELECT_CARDS phase and check the mask geometry there.
    env = shared_env()
    rng = np.random.default_rng(6)
    for seed in range(40):
        env.reset(seed=seed + 200)
        for _ in range(20_000):
            request = env._request
            if request is None:
                break
            if request.kind == DecisionKind.SELECT_CARDS:
                mask = env.action_masks()
                legal = np.flatnonzero(mask)
                # Bounded strictly to the SELECT block: the out-of-combat
                # potion belt block sits immediately after it in the layout
                # (POTION_BASE == SELECT_BASE + MAX_SELECT_CANDIDATES) and
                # can ALSO be unmasked here (an AnyTime potion is usable
                # from every screen) — `a >= SELECT_BASE` alone would wrongly
                # fold those bits into "in_select" too.
                in_select = [a for a in legal if SELECT_BASE <= a < POTION_BASE]
                assert in_select, "select phase must unmask candidate-index actions"
                assert len(in_select) <= len(request.candidates)
                if request.skippable:
                    assert mask[CHOICE_BASE]
                return
            m = env.action_masks()
            _, _, term, trunc, _ = env.step(int(rng.choice(np.flatnonzero(m))))
            if term or trunc:
                break
    pytest.fail("no SELECT_CARDS phase reached in 40 seeds")


def test_ep_final_deck_reported_at_episode_end_only():
    """The deck census rides the same episode-end block as the ep_* tallies."""
    env = STS2RunEnv()
    env.reset(seed=0)
    mid_info = {}
    term = trunc = False
    for _ in range(20_000):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        _, _, term, trunc, info = env.step(a)
        if term or trunc:
            break
        mid_info = info
    assert term or trunc, "episode never ended in 20k steps -- repin"
    assert mid_info, "no mid-episode step was recorded -- episode ended on " \
        "its first step, so the next assertion would pass vacuously"
    # Mid-episode steps carry no census (it is an end-of-run measurement).
    assert "ep_final_deck" not in mid_info
    deck = info["ep_final_deck"]
    assert isinstance(deck, dict)
    assert set(deck) <= {"common", "uncommon", "rare"}
    for cards in deck.values():
        assert cards, "an emitted rarity must not be empty"
        assert all(isinstance(k, str) and isinstance(v, int)
                   for k, v in cards.items())
    # Starters are excluded, so a first-legal run that dies early is empty.
    assert "StrikeCard" not in {c for cards in deck.values() for c in cards}


def test_deck_hist_writes_a_csv_next_to_the_others(tmp_path):
    """`write_deck_csv` writes the expected header + row to a real path.

    This exercises the writer itself (path-or-file handling, header, row
    formatting) given a hand-built RunEvalReport -- it does NOT exercise
    eval.py's ``f"{stem}.deck.csv"`` naming derivation or its
    ``if deck_hist:`` CLI wiring, since it calls `write_deck_csv` directly
    rather than going through eval.py."""
    from sts2_rl.evaluation import RunEvalReport, write_deck_csv

    report = RunEvalReport(
        episodes=1, floors=(3,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(4,),
        deck_rarity_counts={"common": {"AngerCard": 2}},
    )
    path = tmp_path / "out.deck.csv"
    write_deck_csv(str(path), [("p", report)])
    text = path.read_text().strip().splitlines()
    assert text[0].startswith("policy,rarity,card")
    assert text[1] == "p,common,AngerCard,2,1.0,2.0"


def test_eval_cli_rejects_deck_hist_without_csv():
    """--deck-hist has no output of its own, so it must not silently no-op."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "eval.py", "runs/nonexistent.pt", "--env", "run",
         "--deck-hist"],
        capture_output=True, text=True)
    assert proc.returncode != 0
    assert "--deck-hist" in proc.stderr and "--csv" in proc.stderr


def test_eval_cli_rejects_deck_hist_on_combat_env():
    import subprocess
    import sys

    # No --csv here on purpose: with it, the shared run-scale-only loop would
    # reject --csv first and this test would pass for the wrong reason.
    proc = subprocess.run(
        [sys.executable, "eval.py", "--env", "full", "--baselines",
         "--deck-hist"],
        capture_output=True, text=True)
    assert proc.returncode != 0
    assert "--deck-hist" in proc.stderr and "run/column" in proc.stderr
