"""STS2RunEnv (sts2_rl/run_env.py): action layout, masks, observation
schema pins, greenlet lifecycle, and seeded determinism."""
import random

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind
from sts2_rl.full_env import N_CARDS, combat_action_count
from sts2_rl.run_env import (
    CHOICE_BASE,
    CHOICE_SLOTS,
    MAX_POTION_SLOTS,
    N_ACTIONS,
    N_COMBAT_ACTIONS,
    RUN_OBS_SCHEMA_VERSION,
    SELECT_BASE,
    STS2RunEnv,
    run_obs_segments,
    run_obs_slices,
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
    # v2: capacity-padded frozen vocabularies; v3: the shop's Colorless
    # section (SHOP_CARD_SLOTS 5 → 7); v4: run.boss.identity +
    # run.map.grid/meta (boss + whole-map visibility).
    assert RUN_OBS_SCHEMA_VERSION == 4
    # Combat block sized for a Phial-Holster belt: 1 + 10×6 + 4×6 = 85.
    assert N_COMBAT_ACTIONS == combat_action_count(MAX_POTION_SLOTS) == 85
    assert CHOICE_BASE == 85
    assert SELECT_BASE == 85 + CHOICE_SLOTS == 101
    assert N_ACTIONS == SELECT_BASE + 2 * N_CARDS
    env = shared_env()
    assert env.action_space.n == env.n_actions == N_ACTIONS


def test_obs_segments_sum_to_declared_dim():
    env = shared_env()
    segs = env.obs_segments()
    assert sum(w for _, w in segs) == env.observation_space.shape[0]
    # The named slice map tiles the vector exactly.
    slices = env.obs_slices()
    stops = sorted(s.stop for s in slices.values())
    assert stops[-1] == env.observation_space.shape[0]
    # run_obs_segments (module-level) is the same list minus the combat block.
    assert segs[:-1] == run_obs_segments()
    assert segs[-1][0] == "combat"


def test_reset_obs_in_bounds():
    env = shared_env()
    obs, info = env.reset(seed=0)
    assert obs.shape == env.observation_space.shape
    assert obs.min() >= 0.0 and obs.max() <= 1.0
    assert info["phase"] == DecisionKind.EVENT.value   # Neow first
    # Neow: the event block is live and the phase one-hot says EVENT.
    slices = env.obs_slices()
    assert obs[slices["event.present"]][0] == 1.0
    assert obs[slices["phase"]].sum() == 1.0
    # Not in combat: the combat block is all zero.
    assert not obs[slices["combat"]].any()


# ═════════════════════════════════════════════════════════════════════════
# Episodes
# ═════════════════════════════════════════════════════════════════════════

def test_masked_random_episode_terminates():
    env = shared_env()
    trajectory, info, obs = masked_random_episode(env, seed=1)
    assert "is_success" in info and "hp_left" in info
    assert info["floor"] >= 1
    assert obs.min() >= 0.0 and obs.max() <= 1.0


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
    assert np.array_equal(obs, obs2)          # nothing advanced
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
    slices = env.obs_slices()
    # Play a few steps, then check the vitals against the RunState.
    rng = np.random.default_rng(4)
    obs = None
    for _ in range(10):
        mask = env.action_masks()
        obs, *_ = env.step(int(rng.choice(np.flatnonzero(mask))))
    run = env._run
    hp = max(0, run.hp)
    assert obs[slices["run.hp_abs"]][0] == pytest.approx(min(1.0, hp / 100.0), abs=1e-6)
    assert obs[slices["run.gold"]][0] == pytest.approx(min(1.0, run.gold / 100.0), abs=1e-6)
    deck = obs[slices["run.deck"]]
    assert deck.sum() > 0                      # the deck histogram is live
    relics = obs[slices["run.relics"]]
    assert relics.sum() == len(run.relics)     # Neow's pick is visible


def test_combat_block_live_in_combat():
    env = shared_env()
    rng = np.random.default_rng(5)
    obs, _ = env.reset(seed=5)
    slices = env.obs_slices()
    for _ in range(5_000):
        if env._request is not None and env._request.kind == DecisionKind.COMBAT:
            break
        mask = env.action_masks()
        obs, _, term, trunc, _ = env.step(int(rng.choice(np.flatnonzero(mask))))
        assert not (term or trunc), "episode ended before reaching a combat"
    obs = env._build_obs()
    combat = obs[slices["combat"]]
    assert combat.any()                        # live combat features
    assert obs[slices["phase"]][list(DecisionKind).index(DecisionKind.COMBAT)] == 1.0


class _InvincibleRunEnv(STS2RunEnv):
    """STS2RunEnv whose driver plays an effectively unkillable run, so a
    masked-random policy can clear all three acts and exercise the env's
    act-3 / final-boss-victory plumbing (a real policy dies long before)."""

    def _make_run_state(self):
        from sts2_rl.run import RunState

        return RunState(rng=self._rng, max_hp=100_000, hp=100_000)


def test_invincible_env_run_reaches_act3_and_wins():
    # Sweep seeds for a masked-random invincible run that beats the Glory boss.
    # A win must land in act 3 (act_index 2), report is_success, carry a
    # positive terminal reward (the win bonus), and keep the act-3 one-hot lit
    # with obs still in [0, 1] (floor normalization never saturates).
    env = _InvincibleRunEnv()
    slices = env.obs_slices()
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
                onehot = obs[slices["run.act"]]
                assert onehot[2] == 1.0 and onehot.sum() == 1.0
                saw_act3_onehot = True
            assert obs.min() >= 0.0 and obs.max() <= 1.0
            if term or trunc:
                break
        if info.get("is_success"):
            assert max_act == 2                    # a win means clearing Glory
            assert saw_act3_onehot
            assert reward > 0.0                    # includes the victory bonus
            return
    pytest.fail("no invincible env run won in 25 seeds")


def test_select_phase_masks_pairs():
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
                in_select = [a for a in legal if a >= SELECT_BASE]
                assert in_select, "select phase must unmask card pairs"
                assert len(in_select) <= len(request.candidates)
                if request.skippable:
                    assert mask[CHOICE_BASE]
                return
            m = env.action_masks()
            _, _, term, trunc, _ = env.step(int(rng.choice(np.flatnonzero(m))))
            if term or trunc:
                break
    pytest.fail("no SELECT_CARDS phase reached in 40 seeds")
