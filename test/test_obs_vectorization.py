"""Reference-equality harness for the vectorized observation builders
(prompts/obs-vectorization.md).

The observation builders in ``full_env.py`` / ``run_env.py`` are being
rewritten from "append every float into a Python list, then ``np.asarray``"
into "start from a precomputed template array and write only the nonzero
entries in place". That rewrite must be **observation-value-neutral** (up to
float32 rounding) so old checkpoints keep producing identical policy outputs.

This module freezes the ORIGINAL pure-Python builders as reference
implementations (``_ref_*`` below, copied verbatim from the pre-vectorization
code) and asserts, over seeded episodes that visit every phase, that the live
module builders still produce:

  * identical shape,
  * identical nonzero support (same indices are exactly zero),
  * values equal within float32 tolerance (``atol=1e-6``).

If the vectorized builder ever drifts from the frozen reference by more than
float rounding, these tests go red.

Run with:  py -m pytest test/test_obs_vectorization.py -q
"""
from __future__ import annotations

import random

import numpy as np
import pytest

from sts2_rl import (
    BlockCmd,
    DexterityPower,
    Encounter,
    PowerCmd,
    STS2FullCombatEnv,
    StrengthPower,
    VulnerablePower,
    WeakPower,
)
from sts2_rl import full_env as FE
from sts2_rl import run_env as RE
from sts2_rl.driver import DecisionKind
from sts2_rl.full_env import (
    ABS_SCALE,
    ABS_SCALE_COARSE,
    CARD_INDEX,
    MAX_ENEMIES,
    MAX_HAND,
    MAX_POTIONS,
    MONSTER_INDEX,
    N_CARDS,
    N_MONSTERS,
    N_POTIONS,
    N_POWERS,
    PILE_COUNT_CAP,
    POTION_INDEX,
    POWER_IDS,
    _CARD_TYPES,
    _TARGET_TYPES,
    ENEMY_ROW_DIM,
    N_CARD_FEATURES,
    build_combat_obs,
)
from sts2_rl.monsters import MoveType
from sts2_rl.previews import (
    card_base_damage,
    preview_card_block,
    preview_card_damage,
    preview_card_energy_cost,
    preview_incoming_damage,
    preview_total_incoming,
)
from sts2_rl.history import CardPlayedEntry, DamageReceivedEntry
from sts2_rl.probes import probe_dummy
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.curriculum_env import STS2CurriculumRunEnv


# ═════════════════════════════════════════════════════════════════════════
# Frozen reference builders — verbatim copies of the pre-vectorization
# pure-Python code. These must NOT be "improved" alongside the module; they
# are the fixed oracle the vectorized builders are checked against.
# ═════════════════════════════════════════════════════════════════════════

def _ref_clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _ref_signed(x: float, cap: float) -> float:
    return _ref_clip01((x + cap) / (2.0 * cap))


def _ref_abs2(x: float) -> tuple[float, float]:
    return _ref_clip01(x / ABS_SCALE), _ref_clip01(x / ABS_SCALE_COARSE)


def _ref_power_amt(creature, pid: str) -> float:
    pw = creature.powers.get(pid)
    return float(pw.amount) if pw is not None else 0.0


def _ref_power_triples(creature) -> list[float]:
    out: list[float] = []
    powers = creature.powers
    for pid in POWER_IDS:
        pw = powers.get(pid)
        if pw is None:
            out.extend((0.0, 0.5, 0.5))
        else:
            out.extend((1.0, _ref_signed(pw.amount, 10), _ref_signed(pw.amount, 50)))
    out.extend((0.0, 0.5, 0.5) * (N_POWERS - len(POWER_IDS)))
    return out


def _ref_pile_composition(pile) -> list[float]:
    base = [0.0] * N_CARDS
    upgraded = [0.0] * N_CARDS
    for card in pile:
        idx = CARD_INDEX[card.id]
        if card.upgrade_level > 0:
            upgraded[idx] += 1.0
        else:
            base[idx] += 1.0
    return [_ref_clip01(c / PILE_COUNT_CAP) for c in base] + [
        _ref_clip01(c / PILE_COUNT_CAP) for c in upgraded
    ]


def _ref_card_features(state, card) -> list[float]:
    f = [0.0] * N_CARD_FEATURES
    if card is None:
        return f
    s = state
    effective_cost = preview_card_energy_cost(s, card)
    f[0] = _ref_clip01(effective_cost / 6.0)
    f[1] = 1.0 if card.energy_cost_x else 0.0
    for i, t in enumerate(_CARD_TYPES):
        if card.card_type == t:
            f[2 + i] = 1.0
    for i, t in enumerate(_TARGET_TYPES):
        if card.target_type == t:
            f[7 + i] = 1.0
    f[12] = 1.0 if card.exhausts else 0.0
    f[13] = 1.0 if card.is_ethereal else 0.0
    f[14] = 1.0 if card.is_playable else 0.0
    affordable = card.energy_cost_x or effective_cost <= s.player.energy
    f[15] = 1.0 if affordable else 0.0
    f[16] = _ref_clip01(card.upgrade_level / 5.0)
    base_dmg = card_base_damage(s, card, None)
    if base_dmg is not None:
        f[17], f[18] = _ref_abs2(base_dmg)
    f[19] = _ref_clip01(card.base_hits / 10.0)
    if card.base_block is not None:
        f[20] = _ref_clip01(card.base_block / ABS_SCALE)
        eff_block = preview_card_block(s, card)
        f[21] = _ref_clip01(eff_block / ABS_SCALE)
    f[22] = _ref_clip01(card.base_hp_loss / ABS_SCALE)
    magic = card.magic_number
    f[23] = _ref_clip01(magic / 20.0) if magic is not None else 0.0
    return f


def _ref_damage_matrix(state) -> list[float]:
    s = state
    out: list[float] = []
    for h in range(MAX_HAND):
        card = s.player.hand[h] if h < len(s.player.hand) else None
        for e_i in range(MAX_ENEMIES):
            e = s.enemies[e_i] if e_i < len(s.enemies) else None
            if card is None or e is None or e.is_gone:
                out.append(0.0)
                continue
            dmg = preview_card_damage(s, card, e)
            out.append(0.0 if dmg is None else _ref_clip01(dmg / ABS_SCALE))
    return out


def _ref_enemy_row(state, e) -> list[float]:
    if e is None or e.is_gone:
        return [0.0] * ENEMY_ROW_DIM
    s = state
    row: list[float] = [1.0]
    row.append(_ref_clip01(e.hp / max(1, e.max_hp)))
    row.extend(_ref_abs2(e.hp))
    row.extend(_ref_abs2(e.max_hp))
    row.extend(_ref_abs2(e.block))
    row.append(_ref_signed(e.strength, 30))

    intent = e.current_intent
    flags = [
        intent.has(MoveType.ATTACK),
        intent.has(MoveType.DEFEND),
        intent.has(MoveType.BUFF),
        intent.has(MoveType.DEBUFF) or intent.has(MoveType.DEBUFF_STRONG)
        or intent.has(MoveType.CARD_DEBUFF),
        intent.has(MoveType.STATUS_CARD),
        intent.has(MoveType.SUMMON),
        intent.has(MoveType.ESCAPE),
        intent.has(MoveType.HEAL),
        intent.has(MoveType.STUN) or intent.has(MoveType.SLEEP) or e.stunned,
    ]
    row.extend(1.0 if x else 0.0 for x in flags)

    preview = preview_incoming_damage(s, e)
    if preview is None:
        row.extend((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    else:
        row.append(_ref_clip01(preview.per_hit / ABS_SCALE))
        row.append(_ref_clip01(preview.hits / 10.0))
        row.extend(_ref_abs2(preview.total))
        row.extend(_ref_abs2(preview.post_block))

    hot = [0.0] * N_MONSTERS
    idx = MONSTER_INDEX.get(e.__class__.__name__)
    if idx is not None:
        hot[idx] = 1.0
    row.extend(hot)

    row.extend(_ref_power_triples(e))
    assert len(row) == ENEMY_ROW_DIM
    return row


def _ref_build_combat_obs(state, card_obs: str = "hybrid") -> np.ndarray:
    s = state
    p = s.player
    o: list[float] = []

    o.append(_ref_clip01(p.hp / max(1, p.max_hp)))
    o.extend(_ref_abs2(p.hp))
    o.extend(_ref_abs2(p.max_hp))
    o.extend(_ref_abs2(p.block))
    o.append(_ref_clip01(p.energy / 10.0))
    o.append(_ref_signed(p.strength, 30))
    o.append(_ref_signed(_ref_power_amt(p, "dexterity"), 30))
    o.append(_ref_clip01(len(p.hand) / MAX_HAND))
    o.append(_ref_clip01(len(p.draw_pile) / 40.0))
    o.append(_ref_clip01(len(p.discard_pile) / 40.0))
    o.append(_ref_clip01(len(p.exhaust_pile) / 40.0))
    o.append(_ref_clip01(s.turn / 30.0))
    o.extend(_ref_abs2(preview_total_incoming(s)))
    cards_this_turn = sum(1 for _ in s.history.of_type(CardPlayedEntry, this_turn=True))
    dmg_taken = sum(
        e.amount for e in s.history.of_type(DamageReceivedEntry) if e.target is p
    )
    o.append(_ref_clip01(cards_this_turn / 10.0))
    o.append(_ref_clip01(s.history.attack_plays_this_turn() / 10.0))
    o.extend(_ref_abs2(dmg_taken))
    o.extend(_ref_power_triples(p))

    for h in range(MAX_HAND):
        card = p.hand[h] if h < len(p.hand) else None
        o.append(1.0 if card is not None else 0.0)
        if card_obs == "hybrid":
            onehot = [0.0] * N_CARDS
            if card is not None:
                onehot[CARD_INDEX[card.id]] = 1.0
            o.extend(onehot)
        o.extend(_ref_card_features(s, card))

    for e_i in range(MAX_ENEMIES):
        e = s.enemies[e_i] if e_i < len(s.enemies) else None
        o.extend(_ref_enemy_row(s, e))

    o.extend(_ref_damage_matrix(s))

    for pi in range(MAX_POTIONS):
        potion = p.potions[pi] if pi < len(p.potions) else None
        o.append(1.0 if potion is not None else 0.0)
        hot = [0.0] * N_POTIONS
        if potion is not None:
            hot[POTION_INDEX[potion.id]] = 1.0
        o.extend(hot)
        o.append(1.0 if (potion is not None and potion.targeted) else 0.0)

    o.extend(_ref_pile_composition(p.draw_pile))
    o.extend(_ref_pile_composition(p.discard_pile))
    o.extend(_ref_pile_composition(p.exhaust_pile))

    return np.asarray(o, dtype=np.float32)


# ── Frozen reference for the run-env observation ──────────────────────────
# A verbatim copy of STS2RunEnv._build_obs, reading the env's live state but
# using the frozen reference combat/pile builders above.

def _ref_run_build_obs(env: STS2RunEnv) -> np.ndarray:
    run = env._run
    request = env._request
    o: list[float] = []

    phase = [0.0] * RE.N_PHASES
    if request is not None:
        phase[RE.PHASE_INDEX[request.kind]] = 1.0
    o.extend(phase)

    hp = max(0, run.hp)
    o.append(_ref_clip01(hp / max(1, run.max_hp)))
    o.extend(_ref_abs2(hp))
    o.extend(_ref_abs2(run.max_hp))
    o.append(_ref_clip01(run.gold / 100.0))
    o.append(_ref_clip01(run.gold / 1000.0))
    act = [0.0] * RE._N_ACTS
    if 0 <= run.act_index < RE._N_ACTS:
        act[run.act_index] = 1.0
    o.extend(act)
    o.append(_ref_clip01(run.total_floor / 50.0))

    for p in range(RE.MAX_POTION_SLOTS):
        potion = run.potions[p] if p < len(run.potions) else None
        o.append(1.0 if potion is not None else 0.0)
        hot = [0.0] * N_POTIONS
        if potion is not None:
            hot[POTION_INDEX[potion.id]] = 1.0
        o.extend(hot)
        o.append(1.0 if p < run.max_potions else 0.0)

    o.extend(_ref_pile_composition(run.deck))
    relics = [0.0] * RE.N_RELICS
    for relic in run.relics:
        idx = RE.RELIC_INDEX.get(relic.id)
        if idx is not None:
            relics[idx] = 1.0
    o.extend(relics)

    boss = [0.0] * RE.N_MONSTERS
    if run.room_set is not None and run.room_set.boss_key:
        for cls in run.room_set.next_boss_encounter.monster_classes:
            idx = RE.MONSTER_INDEX.get(getattr(cls, "__name__", ""))
            if idx is not None:
                boss[idx] = 1.0
    o.extend(boss)

    points = request.points if request is not None and request.kind == DecisionKind.MAP else []
    for m in range(RE.MAP_SLOTS):
        point = points[m] if m < len(points) else None
        o.append(1.0 if point is not None else 0.0)
        type_hot = [0.0] * RE._N_POINT_TYPES
        child_hist = [0.0] * RE._N_POINT_TYPES
        if point is not None:
            type_hot[RE._POINT_TYPE_INDEX[point.point_type]] = 1.0
            for child in point.children:
                child_hist[RE._POINT_TYPE_INDEX[child.point_type]] += 1.0
            child_hist = [_ref_clip01(c / 3.0) for c in child_hist]
        o.extend(type_hot)
        o.extend(child_hist)

    grid = [0.0] * (RE.MAP_GRID_ROWS * 7 * RE.MAP_GRID_NODE)
    meta = [0.0, 0.0]
    act_map = run.map
    if act_map is not None:
        for row in range(1, min(RE.MAP_GRID_ROWS, act_map.map_length - 1) + 1):
            for point in act_map.points_in_row(row):
                nb = ((row - 1) * 7 + point.col) * RE.MAP_GRID_NODE
                grid[nb] = 1.0
                grid[nb + 1 + RE._POINT_TYPE_INDEX[point.point_type]] = 1.0
                for child in point.children:
                    if child.row < act_map.map_length and 0 <= child.col < 7:
                        grid[nb + 1 + RE._N_POINT_TYPES + child.col] = 1.0
        cp = run.current_point
        if cp is not None:
            if cp is act_map.starting_point:
                meta[0] = 1.0
            elif cp is act_map.boss_point or cp is act_map.second_boss_point:
                meta[1] = 1.0
            elif 1 <= cp.row <= RE.MAP_GRID_ROWS and 0 <= cp.col < 7:
                grid[((cp.row - 1) * 7 + cp.col) * RE.MAP_GRID_NODE
                     + RE.MAP_GRID_NODE - 1] = 1.0
    o.extend(grid)
    o.extend(meta)

    event = request.event if request is not None and request.kind == DecisionKind.EVENT else None
    o.append(1.0 if event is not None else 0.0)
    hot = [0.0] * RE.N_EVENTS
    if event is not None:
        idx = RE.EVENT_INDEX.get(event.id)
        if idx is not None:
            hot[idx] = 1.0
    o.extend(hot)
    o.append(1.0 if (event is not None and event.page != "INITIAL") else 0.0)
    opts = event.options if event is not None else []
    for i in range(RE.CHOICE_SLOTS):
        if i < len(opts):
            o.append(1.0)
            o.append(1.0 if opts[i].locked else 0.0)
        else:
            o.extend((0.0, 0.0))

    shop = request.shop if request is not None and request.kind == DecisionKind.SHOP else None
    card_entries = shop.card_entries if shop is not None else []
    for c in range(RE.SHOP_CARD_SLOTS):
        entry = card_entries[c] if c < len(card_entries) else None
        stocked = entry is not None and entry.is_stocked
        o.append(1.0 if stocked else 0.0)
        hot = [0.0] * N_CARDS
        if stocked:
            hot[CARD_INDEX[entry.card.id]] = 1.0
        o.extend(hot)
        o.append(_ref_clip01(entry.cost / RE._COST_SCALE) if stocked else 0.0)
        o.append(1.0 if stocked and entry.enough_gold else 0.0)
        o.append(1.0 if stocked and entry.on_sale else 0.0)
    relic_entries = shop.relic_entries if shop is not None else []
    for r in range(RE.SHOP_RELIC_SLOTS):
        entry = relic_entries[r] if r < len(relic_entries) else None
        stocked = entry is not None and entry.is_stocked
        o.append(1.0 if stocked else 0.0)
        hot = [0.0] * RE.N_RELICS
        if stocked:
            hot[RE.RELIC_INDEX[entry.relic.id]] = 1.0
        o.extend(hot)
        o.append(_ref_clip01(entry.cost / RE._COST_SCALE) if stocked else 0.0)
        o.append(1.0 if stocked and entry.enough_gold else 0.0)
    potion_entries = shop.potion_entries if shop is not None else []
    for p in range(RE.SHOP_POTION_SLOTS):
        entry = potion_entries[p] if p < len(potion_entries) else None
        stocked = entry is not None and entry.is_stocked
        o.append(1.0 if stocked else 0.0)
        hot = [0.0] * N_POTIONS
        if stocked:
            hot[POTION_INDEX[entry.potion.id]] = 1.0
        o.extend(hot)
        o.append(_ref_clip01(entry.cost / RE._COST_SCALE) if stocked else 0.0)
        o.append(1.0 if stocked and entry.enough_gold else 0.0)
    removal = shop.card_removal_entry if shop is not None else None
    stocked = removal is not None and removal.is_stocked
    o.append(1.0 if stocked else 0.0)
    o.append(_ref_clip01(removal.cost / RE._COST_SCALE) if stocked else 0.0)
    o.append(1.0 if stocked and removal.enough_gold else 0.0)

    rewards = request.rewards if request is not None and request.kind in (
        DecisionKind.REWARD_CARD, DecisionKind.REWARD_POTION,
    ) else None
    cards = rewards.cards if rewards is not None and request.kind == DecisionKind.REWARD_CARD else []
    for c in range(RE.REWARD_CARD_SLOTS):
        card = cards[c] if c < len(cards) else None
        o.append(1.0 if card is not None else 0.0)
        hot = [0.0] * N_CARDS
        if card is not None:
            hot[CARD_INDEX[card.id]] = 1.0
        o.extend(hot)
        o.append(1.0 if (card is not None and card.upgrade_level > 0) else 0.0)
    potion = rewards.potion if rewards is not None and request.kind == DecisionKind.REWARD_POTION else None
    o.append(1.0 if potion is not None else 0.0)
    hot = [0.0] * N_POTIONS
    if potion is not None:
        hot[POTION_INDEX[potion.id]] = 1.0
    o.extend(hot)

    selecting = request is not None and request.kind in (
        DecisionKind.SELECT_CARDS, DecisionKind.SELECT_OPTION,
    )
    purpose_hot = [0.0] * RE.N_PURPOSES
    if selecting:
        purpose_hot[RE.PURPOSE_INDEX.get(request.purpose, RE.N_PURPOSES - 1)] = 1.0
    o.extend(purpose_hot)
    o.append(_ref_clip01(request.count_remaining / 5.0) if selecting else 0.0)
    o.append(1.0 if (selecting and request.skippable) else 0.0)
    if selecting and request.kind == DecisionKind.SELECT_CARDS:
        o.extend(_ref_pile_composition(request.candidates))
    else:
        o.extend([0.0] * (2 * N_CARDS))

    combat = request.combat if request is not None else None
    if combat is not None:
        o.extend(_ref_build_combat_obs(combat, env._card_obs).tolist())
    else:
        o.extend([0.0] * env._combat_obs_dim)

    return np.asarray(o, dtype=np.float32)


# ═════════════════════════════════════════════════════════════════════════
# Comparison helper
# ═════════════════════════════════════════════════════════════════════════

def _assert_matches(live: np.ndarray, ref: np.ndarray, label: str) -> None:
    assert live.shape == ref.shape, f"{label}: shape {live.shape} vs {ref.shape}"
    assert live.dtype == ref.dtype == np.float32, f"{label}: dtype {live.dtype}"
    # Identical nonzero support: the same indices must be exactly zero.
    live_nz = np.flatnonzero(live)
    ref_nz = np.flatnonzero(ref)
    if not np.array_equal(live_nz, ref_nz):
        only_live = np.setdiff1d(live_nz, ref_nz)
        only_ref = np.setdiff1d(ref_nz, live_nz)
        raise AssertionError(
            f"{label}: nonzero support differs; "
            f"nonzero only in live={only_live[:20].tolist()}, "
            f"only in ref={only_ref[:20].tolist()}"
        )
    if not np.allclose(live, ref, atol=1e-6, rtol=0.0):
        diff = np.abs(live - ref)
        i = int(np.argmax(diff))
        raise AssertionError(
            f"{label}: values differ; max |Δ|={diff[i]:.3e} at index {i} "
            f"(live={live[i]!r}, ref={ref[i]!r})"
        )


# ═════════════════════════════════════════════════════════════════════════
# Combat builder equality
# ═════════════════════════════════════════════════════════════════════════

def _rich_combat_env(card_obs: str = "hybrid") -> STS2FullCombatEnv:
    """A multi-enemy combat with potions in the belt and powers on both
    sides, so the obs exercises every combat sub-block at once."""
    d1 = probe_dummy("RichDummyA", hp=30, damage=12, hits=1)
    d2 = probe_dummy("RichDummyB", hp=18, damage=6, hits=2)
    env = STS2FullCombatEnv(
        encounter=Encounter(id="rich", monster_classes=[d1, d2]),
        deck=["strike", "defend", "bash", "whirlwind", "pommel_strike"],
        potions=["block_potion", "fire_potion"],
        card_obs=card_obs,
    )
    env.reset(seed=0)
    s = env._state
    PowerCmd.apply(s.hooks, s.player, StrengthPower, 3)
    PowerCmd.apply(s.hooks, s.player, DexterityPower, 2)
    PowerCmd.apply(s.hooks, s.player, VulnerablePower, 1)
    PowerCmd.apply(s.hooks, s.enemies[0], WeakPower, 1)
    PowerCmd.apply(s.hooks, s.enemies[1], StrengthPower, 2)
    BlockCmd.apply(s.hooks, s.player, 5)
    return env


@pytest.mark.parametrize("card_obs", ["hybrid", "features"])
def test_rich_combat_matches_reference(card_obs):
    env = _rich_combat_env(card_obs)
    live = build_combat_obs(env._state, card_obs)
    ref = _ref_build_combat_obs(env._state, card_obs)
    _assert_matches(live, ref, f"rich combat ({card_obs})")


@pytest.mark.parametrize("card_obs", ["hybrid", "features"])
def test_combat_episodes_match_reference(card_obs):
    """Drive masked-random combats over several encounters/seeds and compare
    the builder output at every step."""
    env = STS2FullCombatEnv(
        deck=["strike", "defend", "bash", "whirlwind", "bloodletting",
              "pommel_strike", "tremble"],
        potions=["fire_potion", "block_potion"],
        card_obs=card_obs,
    )
    rng = np.random.default_rng(0)
    for seed in range(12):
        env.reset(seed=seed)
        for _ in range(400):
            live = build_combat_obs(env._state, card_obs)
            ref = _ref_build_combat_obs(env._state, card_obs)
            _assert_matches(live, ref, f"combat seed {seed} ({card_obs})")
            mask = env.action_masks()
            action = int(rng.choice(np.flatnonzero(mask)))
            _, _, term, trunc, _ = env.step(action)
            if term or trunc:
                break


def test_step_returns_independent_copy():
    """step()/reset() must never alias a mutable internal buffer — two stored
    observations must not change under one another."""
    env = STS2FullCombatEnv(deck=["strike", "defend", "bash"])
    obs1, _ = env.reset(seed=0)
    snapshot = obs1.copy()
    mask = env.action_masks()
    obs2, *_ = env.step(int(np.flatnonzero(mask)[0]))
    # obs1 must be untouched by the second build.
    np.testing.assert_array_equal(obs1, snapshot)
    assert obs1 is not obs2
    assert not np.shares_memory(obs1, obs2)


# ═════════════════════════════════════════════════════════════════════════
# Sub-builder equality (public list-returning API stays intact)
# ═════════════════════════════════════════════════════════════════════════

def test_public_sub_builders_still_return_lists():
    env = _rich_combat_env()
    s = env._state
    pt = FE.power_triples(s.player)
    assert isinstance(pt, list) and len(pt) == 3 * N_POWERS
    np.testing.assert_allclose(pt, _ref_power_triples(s.player), atol=1e-6)
    pc = FE.pile_composition(s.player.hand)
    assert isinstance(pc, list) and len(pc) == 2 * N_CARDS
    np.testing.assert_allclose(pc, _ref_pile_composition(s.player.hand), atol=1e-6)


# ═════════════════════════════════════════════════════════════════════════
# Run-env builder equality (all phases)
# ═════════════════════════════════════════════════════════════════════════

def _drive_run_env_matching(env: STS2RunEnv, seeds, max_steps=20_000):
    """Drive masked-random episodes, comparing the live run obs to the frozen
    reference at every step; returns the set of phases visited."""
    rng = np.random.default_rng(0)
    seen = set()
    for seed in seeds:
        env.reset(seed=seed)
        live = env._build_obs()
        ref = _ref_run_build_obs(env)
        _assert_matches(live, ref, f"run reset seed {seed}")
        for _ in range(max_steps):
            if env._request is not None:
                seen.add(env._request.kind)
            mask = env.action_masks()
            _, _, term, trunc, _ = env.step(int(rng.choice(np.flatnonzero(mask))))
            live = env._build_obs()
            ref = _ref_run_build_obs(env)
            _assert_matches(live, ref, f"run seed {seed}")
            if term or trunc:
                break
    return seen


def test_run_env_matches_reference_all_phases():
    env = STS2RunEnv()
    seen = _drive_run_env_matching(env, range(100, 130))
    # The sweep must actually exercise the phase-specific blocks.
    needed = {
        DecisionKind.MAP, DecisionKind.EVENT, DecisionKind.COMBAT,
        DecisionKind.REWARD_CARD, DecisionKind.SELECT_CARDS, DecisionKind.REST,
    }
    missing = needed - seen
    assert not missing, f"phases not exercised by the sweep: {missing}"


def test_curriculum_run_env_matches_reference():
    env = STS2CurriculumRunEnv()
    _drive_run_env_matching(env, range(200, 210))
