"""v8 HP-economy reward terms (plan Task 1): concave HP potential shaping.
All default OFF: a default-constructed env must be bit-identical to today's
behavior (test_v7_rewards.test_default_env_reward_unchanged already pins
that; this file adds the hp_potential_scale-specific slice of it).

Task 2 (below the HP-potential section) adds the potion ledger
(`potion_potential_scale`) + USE-timing counters."""
from types import SimpleNamespace

import numpy as np
import pytest

from sts2_rl.driver import (
    DecisionKind, DecisionRequest, POTION_ACTION_BASE, REST_HEAL, REST_LEAVE,
    REST_SMITH, RunResult,
)
from sts2_rl.rooms import RoomType
from sts2_rl.run_env import CHOICE_BASE, STS2RunEnv, _hp_potential

KNEE = 0.35
LOW_SHARE = 0.7


def _phi(ratio: float) -> float:
    return _hp_potential(ratio, KNEE, LOW_SHARE)


# ----------------------------------------------------------------------
# Pure _hp_potential unit tests
# ----------------------------------------------------------------------

def test_hp_potential_anchors():
    assert _phi(0.0) == 0.0
    assert abs(_phi(KNEE) - LOW_SHARE) < 1e-12
    assert abs(_phi(1.0) - 1.0) < 1e-12


def test_hp_potential_concave_below_knee_steeper_than_above():
    eps = 1e-6
    slope_below = (_phi(KNEE) - _phi(KNEE - eps)) / eps
    slope_above = (_phi(KNEE + eps) - _phi(KNEE)) / eps
    assert slope_below > slope_above
    # Sanity: below-knee slope is low_share/knee, above is (1-low_share)/(1-knee).
    assert abs(slope_below - LOW_SHARE / KNEE) < 1e-3
    assert abs(slope_above - (1.0 - LOW_SHARE) / (1.0 - KNEE)) < 1e-3


def test_damage_costs_less_at_high_hp_than_low_hp():
    # Same absolute 10-HP hit out of a 100 max-HP pool: 90->80 (high HP)
    # vs 20->10 (low HP, inside the danger zone below the knee).
    cost_high = _phi(0.90) - _phi(0.80)
    cost_low = _phi(0.20) - _phi(0.10)
    assert cost_high > 0.0 and cost_low > 0.0
    assert cost_low > cost_high


def test_heal_earns_more_at_low_hp_than_high_hp():
    gain_low = _phi(0.20) - _phi(0.10)
    gain_high = _phi(0.90) - _phi(0.80)
    assert gain_low > 0.0 and gain_high > 0.0
    assert gain_low > gain_high


def test_telescoping_damage_then_full_heal_nets_zero():
    dmg = _phi(0.80) - _phi(1.00)     # 100 -> 80
    heal = _phi(1.00) - _phi(0.80)    # 80 -> 100
    assert abs(dmg + heal) < 1e-12


def test_death_terminal_hp_zero_gives_phi_zero_no_special_case():
    assert _phi(0.0) == 0.0
    # A lethal hit from any ratio down to 0 loses exactly phi(before).
    assert abs((_phi(0.0) - _phi(0.5)) - (-_phi(0.5))) < 1e-12


# ----------------------------------------------------------------------
# step()-level wiring: the term fires as phi(after) - phi(before), each
# ratio against its OWN step's max_hp.
# ----------------------------------------------------------------------

def _hp_only_step(env, hp_before, hp_after, max_hp=100):
    """Force a single step() call whose only run-state change is HP, by
    monkeypatching the driver-facing seams (`_translate`/`_count_behavior`/
    `_switch`) so no real decision is answered. Isolates the reward-side
    hp_potential arithmetic from the game/driver machinery."""
    env._run.hp = hp_before
    env._run.max_hp = max_hp
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: setattr(env._run, "hp", hp_after)
    return env.step(0)


def test_step_applies_phi_delta_scaled():
    env = STS2RunEnv(hp_potential_scale=2.0, hp_potential_knee=KNEE,
                      hp_potential_low_share=LOW_SHARE)
    env.reset(seed=0)
    _, reward, terminated, truncated, _ = _hp_only_step(env, hp_before=80, hp_after=30, max_hp=100)
    assert not terminated and not truncated
    expected = 2.0 * (_phi(0.30) - _phi(0.80))
    assert abs(reward - expected) < 1e-9
    assert expected < 0.0   # took damage -> negative shaping reward


def test_step_uses_each_side_own_max_hp():
    # max_hp changes mid-step (e.g. a relic/curse); before-ratio must use
    # the pre-step max_hp, after-ratio the post-step max_hp.
    env = STS2RunEnv(hp_potential_scale=1.0, hp_potential_knee=KNEE,
                      hp_potential_low_share=LOW_SHARE)
    env.reset(seed=0)
    env._run.hp = 50
    env._run.max_hp = 100
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None

    def _switch(answer):
        env._run.hp = 60
        env._run.max_hp = 120   # max_hp grew during the step

    env._switch = _switch
    _, reward, *_ = env.step(0)
    expected = _phi(60 / 120) - _phi(50 / 100)
    assert abs(reward - expected) < 1e-9


def test_ep_hp_lost_tallies_damage_only():
    env = STS2RunEnv(hp_potential_scale=0.0)
    env.reset(seed=0)
    _hp_only_step(env, hp_before=80, hp_after=30, max_hp=100)
    assert env._ep_hp_lost == 50
    _hp_only_step(env, hp_before=30, hp_after=90, max_hp=100)   # a heal
    assert env._ep_hp_lost == 50   # heals don't add to the tally


# ----------------------------------------------------------------------
# Default-off bit-identity
# ----------------------------------------------------------------------

def _roll(env, seed, steps=400):
    obs, _ = env.reset(seed=seed)
    total = 0.0
    info = {}
    for _ in range(steps):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        obs, r, term, trunc, info = env.step(a)
        total += r
        if term or trunc:
            break
    return total, info


def test_default_env_reward_unchanged_with_hp_potential_off():
    r_a, info_a = _roll(STS2RunEnv(), seed=7)
    r_b, info_b = _roll(STS2RunEnv(hp_potential_scale=0.0, hp_potential_knee=0.35,
                                    hp_potential_low_share=0.7), seed=7)
    assert r_a == r_b
    assert "ep_hp_lost" in info_a and info_a["ep_hp_lost"] == info_b["ep_hp_lost"]


def test_default_kwargs_inert():
    env = STS2RunEnv()
    assert env._hp_potential_scale == 0.0
    assert env._hp_potential_knee == 0.35
    assert env._hp_potential_low_share == 0.7


# ----------------------------------------------------------------------
# Task 2: potion ledger (potion_potential_scale) + USE timing counters.
#
# All scripted the same way as the hp_potential tests above: monkeypatch
# `_translate`/`_count_behavior`/`_switch` so a single step() call is driven
# entirely by the test, isolating the ledger arithmetic from the real
# driver/greenlet machinery. `_switch` is where the belt mutation happens —
# exactly where the real driver would leave the belt after answering the
# decision `_translate` decoded.
# ----------------------------------------------------------------------

def _add_potion(env) -> None:
    """Fill the first open belt slot with a placeholder. The ledger itself
    only ever tests `is not None`, but `_build_obs`'s potion-belt block reads
    `.id` off every live slot (unconditionally, even outside combat), so the
    placeholder needs one — an id absent from POTION_INDEX just resolves to
    PAD there, which is fine for these reward/counter-only tests."""
    run = env._run
    run.potions[run.potions.index(None)] = SimpleNamespace(id="__test_placeholder__")


def _remove_potion(env) -> None:
    run = env._run
    idx = next(i for i, p in enumerate(run.potions) if p is not None)
    run.potions[idx] = None


def _seed_potion(env) -> None:
    """Add one potion via a REAL step() (not a bare `_add_potion` call) so
    `_belt_base` syncs to it, matching what a real pickup does. Skipping this
    and calling `_add_potion` directly would leave `_belt_base` stale at 0,
    so a later removal step reads `belt_now == _belt_base` (both back to 0
    once the mutation lands) and never even sees a decrease — masking the
    exact behavior the use/sell tests below exist to check."""
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_potion(env)
    env.step(0)


def _combat_request(env, room_type) -> DecisionRequest:
    """A COMBAT DecisionRequest carrying only what the ledger's classification
    reads (`combat.room_type`) — a real `CombatState` writes a full combat
    observation `_build_obs` would need many more fields for, which this
    reward/counter-only test has no reason to fake. `_build_obs` is stubbed
    out here too (return value unused by any of these tests) so a stub combat
    object never reaches `write_combat_obs`."""
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
    return DecisionRequest(
        kind=DecisionKind.COMBAT, run=env._run,
        combat=SimpleNamespace(room_type=room_type))


def test_potion_ledger_fires_plus_k_on_pickup():
    env = STS2RunEnv(potion_potential_scale=3.0)
    env.reset(seed=0)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_potion(env)
    _, reward, terminated, truncated, info = env.step(0)
    assert not terminated and not truncated
    assert reward == pytest.approx(3.0)
    assert env._ep_potions_obtained == 1


def test_potion_ledger_fires_minus_k_on_use():
    env = STS2RunEnv(potion_potential_scale=2.0)
    env.reset(seed=0)
    _seed_potion(env)
    env._run.hp, env._run.max_hp = 40, 100
    env._request = _combat_request(env, RoomType.MONSTER)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(-2.0)
    assert env._ep_potions_used == 1


def test_potion_ledger_fires_minus_k_on_non_drink_decrease():
    """A belt loss NOT answered via a potion action (e.g. a shop sale, or an
    event trading a potion away — there is no shop-sell feature in this sim,
    but any such non-drink loss takes this same shape) still moves the
    ledger, but must NOT increment any use counter — it wasn't drunk."""
    env = STS2RunEnv(potion_potential_scale=1.5)
    env.reset(seed=0)
    _seed_potion(env)
    env._request = DecisionRequest(kind=DecisionKind.EVENT, run=env._run)
    env._translate = lambda action, request: 0   # NOT a potion-use answer
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(-1.5)
    assert env._ep_potions_used == 0
    assert env._ep_potions_used_elite == 0
    assert env._ep_potions_used_boss == 0
    assert env._ep_potions_used_normal == 0


def test_pickup_then_use_nets_zero():
    env = STS2RunEnv(potion_potential_scale=4.0)
    env.reset(seed=0)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_potion(env)
    _, r1, *_ = env.step(0)

    env._request = _combat_request(env, RoomType.MONSTER)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._switch = lambda answer: _remove_potion(env)
    _, r2, *_ = env.step(0)

    assert r1 == pytest.approx(4.0)
    assert r2 == pytest.approx(-4.0)
    assert r1 + r2 == pytest.approx(0.0)
    assert env._ep_potions_obtained == 1
    assert env._ep_potions_used == 1


def test_pickup_then_episode_end_keeps_plus_k_no_terminal_zeroing():
    """The no-terminal-zeroing property, asserted explicitly: a potion picked
    up and never spent keeps its +k at episode end (no offsetting term), and
    the held count lands in `ep_potions_expired` for visibility only."""
    env = STS2RunEnv(potion_potential_scale=5.0, reward_win=0.0, win_hp_bonus=0.0)
    env.reset(seed=0)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_potion(env)
    _, r1, terminated, truncated, info = env.step(0)
    assert not terminated and not truncated
    assert r1 == pytest.approx(5.0)
    assert "ep_potions_expired" not in info   # not episode-end yet

    def _end(answer):
        env._result = RunResult(victory=True, hp=env._run.hp, max_hp=env._run.max_hp,
                                 gold=0, floor=env._run.total_floor,
                                 act_index=env._run.act_index,
                                 deck_size=len(env._run.deck), decisions=1)
        env._request = None

    env._translate = lambda action, request: 0
    env._switch = _end
    _, r2, terminated2, truncated2, info2 = env.step(0)
    assert terminated2
    assert r2 == pytest.approx(0.0)             # no belt change, no reward source fires
    assert r1 + r2 == pytest.approx(5.0)         # the pickup's +k was never clawed back
    assert info2["ep_potions_expired"] == 1
    assert info2["ep_potions_obtained"] == 1
    assert info2["ep_potions_used"] == 0


def test_potion_use_classification_elite_vs_normal():
    env = STS2RunEnv(potion_potential_scale=1.0)
    env.reset(seed=0)

    _seed_potion(env)
    env._run.hp, env._run.max_hp = 60, 100
    env._request = _combat_request(env, RoomType.ELITE)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    env.step(0)
    assert env._ep_potions_used_elite == 1
    assert env._ep_potions_used_boss == 0
    assert env._ep_potions_used_normal == 0

    _seed_potion(env)
    env._run.hp, env._run.max_hp = 30, 100
    env._request = _combat_request(env, RoomType.MONSTER)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._switch = lambda answer: _remove_potion(env)
    env.step(0)
    assert env._ep_potions_used_elite == 1
    assert env._ep_potions_used_boss == 0
    assert env._ep_potions_used_normal == 1

    assert env._ep_potion_use_hp == pytest.approx(0.6 + 0.3)


def test_potion_use_classification_boss_and_out_of_combat_count_as_normal():
    env = STS2RunEnv(potion_potential_scale=1.0)
    env.reset(seed=0)

    _seed_potion(env)
    env._request = _combat_request(env, RoomType.BOSS)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    env.step(0)
    assert env._ep_potions_used_boss == 1

    # An AnyTime potion drunk from a non-combat screen: no room to attribute
    # to, so it falls in the catch-all "normal" bucket.
    _seed_potion(env)
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._switch = lambda answer: _remove_potion(env)
    env.step(0)
    assert env._ep_potions_used_normal == 1


def test_potion_use_bucket_sum_equals_ep_potions_used():
    env = STS2RunEnv(potion_potential_scale=1.0)
    env.reset(seed=0)
    env._count_behavior = lambda request, answer: None

    for room_type in (RoomType.ELITE, RoomType.BOSS, RoomType.MONSTER, RoomType.ELITE):
        _seed_potion(env)
        env._request = _combat_request(env, room_type)
        env._translate = lambda action, request: POTION_ACTION_BASE + 0
        env._switch = lambda answer: _remove_potion(env)
        env.step(0)

    total_bucketed = (env._ep_potions_used_elite + env._ep_potions_used_boss
                       + env._ep_potions_used_normal)
    assert total_bucketed == env._ep_potions_used == 4
    assert env._ep_potions_used_elite == 2
    assert env._ep_potions_used_boss == 1
    assert env._ep_potions_used_normal == 1


def test_default_env_reward_unchanged_with_potion_potential_off():
    r_a, info_a = _roll(STS2RunEnv(), seed=11)
    r_b, info_b = _roll(STS2RunEnv(potion_potential_scale=0.0), seed=11)
    assert r_a == r_b
    assert info_a.get("ep_potions_obtained") == info_b.get("ep_potions_obtained")
    assert info_a.get("ep_potions_used") == info_b.get("ep_potions_used")


def test_default_kwargs_inert_potion():
    env = STS2RunEnv()
    assert env._potion_potential_scale == 0.0


# ----------------------------------------------------------------------
# Task 3: reward_relic. Scripted the same way as the potion ledger tests
# above: monkeypatch `_translate`/`_count_behavior`/`_switch` so a single
# step() call is driven entirely by the test, and mutate `run.relics`
# directly in `_switch` — exactly where a real pickup would leave it.
# ----------------------------------------------------------------------

def _add_relic(env, relic_id: str = "__test_relic__") -> None:
    env._run.relics.append(SimpleNamespace(id=relic_id))


def test_starting_relic_does_not_count():
    # Ironclad (the default character) starts with Burning Blood — the
    # baseline snapshot must be taken AFTER it lands, so it never fires
    # the reward on its own.
    env = STS2RunEnv(reward_relic=1.0)
    env.reset(seed=0)
    assert len(env._run.relics) >= 1
    assert env._relic_len_base == len(env._run.relics)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: None   # no relic change this step
    _, reward, terminated, truncated, info = env.step(0)
    assert not terminated and not truncated
    assert reward == 0.0
    assert env._ep_relics == 0
    assert "ep_relics" not in info   # not episode-end yet


def test_relic_reward_fires_on_pickup():
    env = STS2RunEnv(reward_relic=1.5)
    env.reset(seed=0)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_relic(env)
    _, reward, terminated, truncated, info = env.step(0)
    assert not terminated and not truncated
    assert reward == pytest.approx(1.5)
    assert env._ep_relics == 1


def test_relic_reward_scales_with_multiple_gained_at_once():
    env = STS2RunEnv(reward_relic=0.25)
    env.reset(seed=0)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None

    def _switch(answer):
        _add_relic(env, "__a__")
        _add_relic(env, "__b__")

    env._switch = _switch
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(0.5)
    assert env._ep_relics == 2


def test_relic_reward_ignored_during_combat_decision():
    # Same out-of-combat guard as the deck deltas: a relic that lands while
    # `_request.kind == DecisionKind.COMBAT` is not credited until the first
    # out-of-combat step afterward.
    env = STS2RunEnv(reward_relic=1.0)
    env.reset(seed=0)
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
    env._request = DecisionRequest(
        kind=DecisionKind.COMBAT, run=env._run,
        combat=SimpleNamespace(room_type=RoomType.MONSTER))
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_relic(env)
    _, reward, *_ = env.step(0)
    assert reward == 0.0
    assert env._ep_relics == 0

    # First out-of-combat step afterward credits the relic that already landed.
    env._request = None
    env._switch = lambda answer: None
    _, reward2, *_ = env.step(0)
    assert reward2 == pytest.approx(1.0)
    assert env._ep_relics == 1


def test_ep_relics_reported_at_episode_end():
    env = STS2RunEnv(reward_relic=0.0, reward_win=0.0, win_hp_bonus=0.0)
    env.reset(seed=0)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_relic(env)
    env.step(0)
    assert env._ep_relics == 1

    def _end(answer):
        env._result = RunResult(victory=True, hp=env._run.hp, max_hp=env._run.max_hp,
                                 gold=0, floor=env._run.total_floor,
                                 act_index=env._run.act_index,
                                 deck_size=len(env._run.deck), decisions=1)
        env._request = None

    env._translate = lambda action, request: 0
    env._switch = _end
    _, _, terminated, truncated, info = env.step(0)
    assert terminated
    assert info["ep_relics"] == 1


def test_default_env_reward_unchanged_with_reward_relic_off():
    r_a, info_a = _roll(STS2RunEnv(), seed=13)
    r_b, info_b = _roll(STS2RunEnv(reward_relic=0.0), seed=13)
    assert r_a == r_b
    assert info_a.get("ep_relics") == info_b.get("ep_relics")


def test_default_kwargs_inert_relic():
    env = STS2RunEnv()
    assert env._reward_relic == 0.0


# ----------------------------------------------------------------------
# Task 4: rest_heal_mask_above curriculum mask. Above the threshold, with
# another rest action legal, REST_HEAL's mask bit is cleared; the choice
# block's own layout is REST_HEAL/REST_SMITH/REST_LEAVE = 0,1,2 at
# CHOICE_BASE (driver.py:79).
# ----------------------------------------------------------------------

def _rest_request(env) -> DecisionRequest:
    """A real REST DecisionRequest off the live run — `own_actions()` reads
    `run.upgradable_cards()`, so a fresh reset's starter deck (Strikes/
    Defends, all upgradable) makes REST_SMITH legal alongside REST_HEAL/
    REST_LEAVE, exactly like a real rest-site visit before anything is used
    up this visit."""
    return DecisionRequest(kind=DecisionKind.REST, run=env._run)


def test_mask_clears_rest_heal_above_threshold_with_full_hp():
    env = STS2RunEnv(rest_heal_mask_above=0.8)
    env.reset(seed=0)
    env._run.hp = env._run.max_hp   # full HP, ratio 1.0 >= 0.8
    env._request = _rest_request(env)
    mask = env.action_masks()
    assert mask[CHOICE_BASE + REST_HEAL] == False
    assert mask[CHOICE_BASE + REST_SMITH] == True
    assert mask[CHOICE_BASE + REST_LEAVE] == True


def test_mask_unchanged_below_threshold():
    env = STS2RunEnv(rest_heal_mask_above=0.8)
    env.reset(seed=0)
    env._run.hp = max(1, int(env._run.max_hp * 0.5))   # ratio 0.5 < 0.8
    env._request = _rest_request(env)
    mask = env.action_masks()
    assert mask[CHOICE_BASE + REST_HEAL] == True
    assert mask[CHOICE_BASE + REST_SMITH] == True
    assert mask[CHOICE_BASE + REST_LEAVE] == True


def test_mask_never_clears_when_rest_heal_is_only_legal_action():
    # REST_LEAVE is always appended by the real `own_actions()`, so a real
    # rest decision can never actually offer REST_HEAL alone (per the task
    # brief, this may be unreachable in practice) -- exercise the mask
    # helper directly by faking a request whose own_actions() returns only
    # REST_HEAL, bypassing the driver's real REST_LEAVE-always-legal rule.
    env = STS2RunEnv(rest_heal_mask_above=0.0)   # threshold trivially met
    env.reset(seed=0)
    env._run.hp = env._run.max_hp
    request = _rest_request(env)
    request.own_actions = lambda: [REST_HEAL]
    env._request = request
    mask = env.action_masks()
    assert mask[CHOICE_BASE + REST_HEAL] == True


def test_default_env_masks_bit_identical_with_rest_heal_mask_above_none():
    def _roll_masks(env, seed, steps=400):
        obs, _ = env.reset(seed=seed)
        masks = []
        for _ in range(steps):
            mask = env.action_masks()
            masks.append(mask.copy())
            a = int(np.flatnonzero(mask)[0])
            obs, r, term, trunc, info = env.step(a)
            if term or trunc:
                break
        return masks

    masks_a = _roll_masks(STS2RunEnv(), seed=17)
    masks_b = _roll_masks(STS2RunEnv(rest_heal_mask_above=None), seed=17)
    assert len(masks_a) == len(masks_b)
    for m_a, m_b in zip(masks_a, masks_b):
        assert np.array_equal(m_a, m_b)


def test_default_kwargs_inert_rest_heal_mask():
    env = STS2RunEnv()
    assert env._rest_heal_mask_above is None
