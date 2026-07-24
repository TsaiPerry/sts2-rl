"""STS2FullCombatEnv — a Gymnasium env that exposes the *whole* combat.

Unlike the toy ``STS2CombatEnv`` (3 actions, one hardcoded fight), this env
drives the real engine: play any card in hand at any target, use potions, and
end the turn — across a configurable pool of encounters and a configurable
deck. It is built for ``sb3-contrib``'s ``MaskablePPO`` (an ``action_masks``
method reports the legal actions each step).

Design at a glance
------------------
Action space (flat ``Discrete``), decoded in ``_decode_action``::

    0                          end turn
    1 .. H*E                   play hand card h at enemy target e
    1+H*E .. 1+H*E+P*E         use potion p at enemy target e

  where H = MAX_HAND, E = MAX_ENEMIES, P = MAX_POTIONS. Cards/potions that
  don't need a target (SELF / ALL_ENEMIES / non-targeted potions) are masked to
  a single canonical target so equivalent actions don't bloat the space.

Observation (flat ``Box`` in [0, 1], layout in ``_build_obs``), schema
``OBS_SCHEMA_VERSION``. Guiding principle: the agent sees everything a human
sees on screen, with absolute numbers so lethal math is computable — every
HP-like quantity (HP, block, damage) is encoded on one shared absolute scale
(``/ABS_SCALE`` clipped, plus a coarse ``/ABS_SCALE_COARSE`` companion so
Act-2+ values don't saturate). The blocks:

* Player vitals: HP as ratio *and* absolute hp/max_hp, block, energy,
  strength/dexterity (signed), pile sizes, turn, the total post-block damage
  telegraphed at the player this turn, history scalars (cards/attacks played
  this turn, damage taken this combat), and the **full power vocabulary**
  (every id in ``ALL_POWERS``: presence + signed amount at two scales).
* One row per hand slot: card identity one-hot (in ``card_obs="hybrid"``
  mode) plus engineered features — hook-modified effective energy cost,
  type/target flags, base damage/hits/block, *effective* block
  (Dexterity/Frail-modified), self HP loss, magic number.
* One row per enemy slot: absolute+ratio vitals, intent flags, the intent's
  attack fully run through the damage-modifier pipeline (per-hit, hits,
  total, and post-block vs the player's current block — mirroring
  ``AttackIntent.GetSingleDamage``), enemy identity one-hot (from the
  ``Monster`` subclass registry), and the full power vocabulary.
* A per-(hand slot, enemy slot) **effective damage matrix** aligned 1:1 with
  the play actions: the fully modified per-hit damage each card would deal
  to each enemy (Strength, Weak, target Vulnerable — the number printed on
  the card face).
* One row per potion slot, then — for each of the draw / discard / exhaust
  piles — an unordered *composition histogram*: per card id, how many base
  copies and how many upgraded copies it holds (the shuffled draw order
  stays hidden, only the multiset is exposed).

The exact dimension is measured once at construction so the declared space and
``_build_obs`` never drift.

Reward (all configurable): per-step normalized player-HP delta, plus a terminal
win/loss bonus. Because only ``end turn`` advances the enemy, damage taken is
naturally attributed to the step that ended the turn. On a win the bonus is
``reward_win + win_hp_bonus * (final HP / max HP)`` — ``win_hp_bonus`` (default 0)
makes winning with more HP worth more, so the agent is pushed to win *clean* and
not just to win. ``enemy_hp_reward_scale`` (default 0) adds a dense damage-dealt
signal normalized by the encounter's total starting HP.

Simplifications (documented, not silent): mid-play card *selections* (Armaments,
Burning Pact, the Knowledge Demon curse pick, …) are not exposed as separate
timesteps; they are resolved by ``scripted_card_selector`` — a deterministic
heuristic (see ``selectors.py``), so training sees no hidden stochasticity from
selection effects. Pass ``card_selector=`` to substitute your own policy, or
``card_selector=None`` for the engine's seeded-random default. Living enemies
past ``MAX_ENEMIES`` (only reachable via unusually spammy summons) are not
targetable.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Sequence

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from .cards import Card, CardType, TargetType, make_card
from .cards.base import _CARD_CLASSES
from .combat import CombatState, Phase
from .history import CardPlayedEntry, DamageReceivedEntry
from .monsters import Encounter, Monster, MoveType
from .monsters.overgrowth import BOSS_ENCOUNTER_KEYS as _BOSS_KEYS
from .monsters.overgrowth import ENCOUNTERS as _OVERGROWTH
from .player import PlayerCombatState
from .potions import ALL_POTIONS, Potion, make_potion
from .powers import ALL_POWERS
from .selectors import scripted_card_selector
from .vocab import capacity as vocab_capacity, frozen_ids
from .previews import (
    card_base_damage,
    preview_card_block,
    preview_card_damage,
    preview_card_energy_cost,
    preview_incoming_damage,
    preview_total_incoming,
)

# Bump whenever the observation layout changes (any change invalidates saved
# models — retrain). v2: absolute HP/block/damage encoding, pipeline-accurate
# intent + card previews, full power vocabulary, enemy identity, history
# scalars, dexterity fix. v3: capacity-padded frozen vocabularies (vocab.py) —
# dims are reserved capacities, so future content additions no longer bump
# this.
OBS_SCHEMA_VERSION = 3

# ── Fixed-size bounds (obs/action slots). Bump + retrain if an encounter or a
#    relic ever exceeds these. ────────────────────────────────────────────────
MAX_HAND = PlayerCombatState.MAX_HAND_SIZE      # 10
MAX_POTIONS = PlayerCombatState.MAX_POTIONS      # 3
MAX_ENEMIES = 6                                  # initial lineup ≤4; headroom for summons

# Shared absolute unit for every HP-like quantity (HP, block, damage): a fine
# /100 scale plus a coarse /500 companion so Act-2+ values don't saturate.
# One shared unit lets the network compare features (incoming vs remaining HP)
# with a single learned mapping.
ABS_SCALE = 100.0
ABS_SCALE_COARSE = 500.0

# Saturation cap for per-card pile-composition counts: how many copies of a
# *single* card id one pile can hold before the (normalized) count saturates.
# 10 comfortably covers realistic decks; bump if you train pathological stacks.
PILE_COUNT_CAP = 10.0

# Stable vocabularies (index = position), frozen append-only via vocab.json
# so ported content never shifts existing indices; every N_* layout constant
# is the reserved *capacity* (padded slots stay zero/masked), so obs and
# action dims survive new content — see sts2_rl/vocab.py.
# Importing .cards / .potions / .monsters / .powers has already registered
# every class into these registries.
CARD_IDS: list[str] = frozen_ids("cards", _CARD_CLASSES)
CARD_INDEX: dict[str, int] = {cid: i for i, cid in enumerate(CARD_IDS)}
N_CARDS = vocab_capacity("cards")

POTION_IDS: list[str] = frozen_ids("potions", ALL_POTIONS)
POTION_INDEX: dict[str, int] = {pid: i for i, pid in enumerate(POTION_IDS)}
N_POTIONS = vocab_capacity("potions")

# The FULL power vocabulary (no curated subset: an unlisted power would be
# silently invisible to the agent). Strength/dexterity also get dedicated
# signed scalar slots for resolution, but stay in the vocabulary for
# uniformity.
POWER_IDS: list[str] = frozen_ids("powers", ALL_POWERS)
POWER_INDEX: dict[str, int] = {pid: i for i, pid in enumerate(POWER_IDS)}
N_POWERS = vocab_capacity("powers")


def _monster_classes() -> list[type[Monster]]:
    """Every registered Monster subclass, sorted by class name (a stable
    vocabulary — importing .monsters pulled in every act's roster, including
    summon-only enemies that appear in no encounter list)."""
    seen: dict[str, type[Monster]] = {}
    stack: list[type[Monster]] = [Monster]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub.__name__ not in seen:
                seen[sub.__name__] = sub
                stack.append(sub)
    return [seen[name] for name in sorted(seen)]


MONSTER_IDS: list[str] = frozen_ids(
    "monsters", [cls.__name__ for cls in _monster_classes()])
MONSTER_INDEX: dict[str, int] = {mid: i for i, mid in enumerate(MONSTER_IDS)}
N_MONSTERS = vocab_capacity("monsters")

_CARD_TYPES = [CardType.ATTACK, CardType.SKILL, CardType.POWER, CardType.STATUS, CardType.CURSE]
_TARGET_TYPES = [
    TargetType.ANY_ENEMY, TargetType.ALL_ENEMIES, TargetType.RANDOM_ENEMY,
    TargetType.SELF, TargetType.NONE,
]

# Engineered card features per hand slot (see _card_features).
N_CARD_FEATURES = 24
# Enemy-row scalars before the identity one-hot and power vocabulary
# (see _enemy_row): present + hp ratio + hp×2 + max_hp×2 + block×2 + strength
# + 9 intent flags + per_hit + hits + total×2 + post_block×2.
_N_ENEMY_SCALARS = 24
ENEMY_ROW_DIM = _N_ENEMY_SCALARS + N_MONSTERS + 3 * N_POWERS

# ── Observation layout map ───────────────────────────────────────────────────
# A named index map over the flat observation, mirroring _build_obs segment by
# segment. Consumed by the pin tests (test/test_obs_pins.py) and by the
# Phase 4 ablation (AblatedObsEnv) to address feature groups by name instead
# of magic indices. A drift between this map and _build_obs fails the pin test
# that sums the segments against the probe-measured obs dimension.

# _card_features splits into f[0:17] (cost/type/target/flags) and f[17:24] —
# the card's *numbers* (base damage ×2 scales, hits, base block, effective
# block, HP loss, magic number), which is what the numeric ablation removes.
_N_CARD_NUMBER_FEATURES = 7


def obs_segments(card_obs: str = "hybrid") -> list[tuple[str, int]]:
    """The observation as an ordered (segment name, width) list."""
    segs: list[tuple[str, int]] = [
        ("player.hp_ratio", 1),
        ("player.hp_abs", 2),
        ("player.max_hp_abs", 2),
        ("player.block_abs", 2),
        ("player.energy", 1),
        ("player.strength", 1),
        ("player.dexterity", 1),
        ("player.pile_sizes", 4),
        ("player.turn", 1),
        ("player.incoming_post_block", 2),
        ("player.cards_played_this_turn", 1),
        ("player.attacks_this_turn", 1),
        ("player.damage_taken", 2),
        ("player.powers", 3 * N_POWERS),
    ]
    for h in range(MAX_HAND):
        segs.append((f"hand{h}.present", 1))
        if card_obs == "hybrid":
            segs.append((f"hand{h}.onehot", N_CARDS))
        segs.append((f"hand{h}.features", N_CARD_FEATURES - _N_CARD_NUMBER_FEATURES))
        segs.append((f"hand{h}.numbers", _N_CARD_NUMBER_FEATURES))
    for e in range(MAX_ENEMIES):
        segs.extend([
            (f"enemy{e}.present", 1),
            (f"enemy{e}.hp_ratio", 1),
            (f"enemy{e}.hp_abs", 2),
            (f"enemy{e}.max_hp_abs", 2),
            (f"enemy{e}.block_abs", 2),
            (f"enemy{e}.strength", 1),
            (f"enemy{e}.intent_flags", 9),
            (f"enemy{e}.intent_preview", 6),
            (f"enemy{e}.identity", N_MONSTERS),
            (f"enemy{e}.powers", 3 * N_POWERS),
        ])
    segs.append(("damage_matrix", MAX_HAND * MAX_ENEMIES))
    for p in range(MAX_POTIONS):
        segs.append((f"potion{p}", 1 + N_POTIONS + 1))
    segs.extend([
        ("draw_pile", 2 * N_CARDS),
        ("discard_pile", 2 * N_CARDS),
        ("exhaust_pile", 2 * N_CARDS),
    ])
    return segs


def obs_slices(card_obs: str = "hybrid") -> dict[str, slice]:
    """Segment name → slice into the flat observation vector."""
    out: dict[str, slice] = {}
    i = 0
    for name, width in obs_segments(card_obs):
        out[name] = slice(i, i + width)
        i += width
    return out


# The Phase 1 "absolute numbers & pipeline previews" feature groups — the
# enhanced half of the OBS_PLAN Phase 4 ablation. Everything else (ratios,
# energy, flags, identities, power vocabulary, pile histograms) stays.
_NUMERIC_SEGMENT_SUFFIXES = (
    "hp_abs", "max_hp_abs", "block_abs", "incoming_post_block",
    "numbers", "intent_preview",
)


def numeric_obs_indices(card_obs: str = "hybrid") -> np.ndarray:
    """Flat indices of every absolute-number / preview feature."""
    idx: list[int] = []
    for name, sl in obs_slices(card_obs).items():
        if name == "damage_matrix" or name.rsplit(".", 1)[-1] in _NUMERIC_SEGMENT_SUFFIXES:
            idx.extend(range(sl.start, sl.stop))
    return np.asarray(idx, dtype=np.int64)


DEFAULT_DECK_IDS = ["strike"] * 5 + ["defend"] * 4 + ["bash"] + ["whirlwind"] + ["bloodletting"] + ["pommel_strike"] + ["tremble"]
# Default training pool: Act 1 (Overgrowth) minus the bosses. Pass
# encounter=/encounters= to fix a single fight or supply your own curriculum.
DEFAULT_ENCOUNTERS: list[Encounter] = [
    e for k, e in _OVERGROWTH.items() if k not in _BOSS_KEYS
]


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _signed(x: float, cap: float) -> float:
    """Map a signed value in [-cap, cap] onto [0, 1] (0.5 = zero)."""
    return _clip01((x + cap) / (2.0 * cap))


def _abs2(x: float) -> tuple[float, float]:
    """A value in the shared absolute unit: (fine /100, coarse /500)."""
    return _clip01(x / ABS_SCALE), _clip01(x / ABS_SCALE_COARSE)


# ── Combat action block (shared by STS2FullCombatEnv and the run driver /
#    run env): 0 = end turn, then MAX_HAND×MAX_ENEMIES play actions, then
#    per-slot potion actions. The play block is fixed-size, so decoding never
#    depends on how many potion slots the caller exposes. ──────────────────

COMBAT_PLAY_BASE = 1
COMBAT_POTION_BASE = COMBAT_PLAY_BASE + MAX_HAND * MAX_ENEMIES   # 61


def combat_action_count(max_potions: int = MAX_POTIONS) -> int:
    """Size of the flat combat action block for a given potion-belt size
    (79 at the base 3 slots)."""
    return COMBAT_POTION_BASE + max_potions * MAX_ENEMIES


def decode_combat_action(action: int) -> tuple[str, int, int | None]:
    """Flat combat action → ("end"|"play"|"potion", slot, target)."""
    if action <= 0:
        return "end", 0, None
    if action < COMBAT_POTION_BASE:
        idx = action - COMBAT_PLAY_BASE
        return "play", idx // MAX_ENEMIES, idx % MAX_ENEMIES
    idx = action - COMBAT_POTION_BASE
    return "potion", idx // MAX_ENEMIES, idx % MAX_ENEMIES


def apply_combat_action(state: CombatState, action: int) -> None:
    """Execute a flat combat action on a CombatState (illegal = no-op,
    matching CombatState.play_card / use_potion semantics)."""
    kind, a, b = decode_combat_action(int(action))
    if kind == "end":
        state.end_turn()
    elif kind == "play":
        state.play_card(a, b)
    else:
        state.use_potion(a, b)


def combat_action_masks(
    state: CombatState | None,
    max_potions: int = MAX_POTIONS,
) -> np.ndarray:
    """Boolean legality mask over the flat combat block (for MaskablePPO and
    the run driver). Guarantees at least one legal action: end turn (a
    harmless no-op outside the player's turn)."""
    mask = np.zeros(combat_action_count(max_potions), dtype=bool)
    if state is None or state.phase != Phase.PLAYER_TURN:
        mask[0] = True
        return mask

    mask[0] = True       # end turn is always legal on the player's turn
    s = state
    living = [i for i, e in enumerate(s.enemies) if not e.is_gone and i < MAX_ENEMIES]
    first = living[0] if living else 0

    for h, card in enumerate(s.player.hand[:MAX_HAND]):
        if not card.is_playable or not s.hooks.should_play_card(card):
            continue
        if not card.energy_cost_x:
            if s.hooks.modify_card_energy_cost(card, card.energy_cost) > s.player.energy:
                continue
        if card.target_type == TargetType.ANY_ENEMY:
            for e in living:
                mask[COMBAT_PLAY_BASE + h * MAX_ENEMIES + e] = True
        else:
            mask[COMBAT_PLAY_BASE + h * MAX_ENEMIES + first] = True

    for p, potion in enumerate(s.player.potions[:max_potions]):
        if potion is None:
            continue
        if potion.targeted:
            for e in living:
                mask[COMBAT_POTION_BASE + p * MAX_ENEMIES + e] = True
        else:
            mask[COMBAT_POTION_BASE + p * MAX_ENEMIES + first] = True

    return mask


# ── Combat observation builder (shared by STS2FullCombatEnv and the run
#    env). Pure reads over a CombatState; layout documented segment-by-
#    segment in obs_segments()/obs_slices() above. ─────────────────────────


def _power_amt(creature, pid: str) -> float:
    pw = creature.powers.get(pid)
    return float(pw.amount) if pw is not None else 0.0


# The constant power-vocabulary background: every slot as an *absent* power
# (presence 0, signed amount 0.5/0.5 at both scales — the encoding of "not
# present"). Baked into the obs template so a present power is a few sparse
# overwrites instead of pushing 3·N_POWERS constants every build.
_POWER_BG = np.empty(3 * N_POWERS, dtype=np.float32)
_POWER_BG[0::3] = 0.0
_POWER_BG[1::3] = 0.5
_POWER_BG[2::3] = 0.5


def _write_power_triples(creature, out: np.ndarray, base: int) -> None:
    """Overwrite the present powers into ``out[base : base+3·N_POWERS]``,
    which must already hold the ``_POWER_BG`` absent-power background. Only a
    creature's actually-present powers (a handful) are written; every absent
    slot and the reserved-capacity tail keep the (0, 0.5, 0.5) background."""
    for pid, pw in creature.powers.items():
        i = POWER_INDEX.get(pid)
        if i is None:                      # power id outside the frozen vocab
            continue
        o = base + 3 * i
        out[o] = 1.0
        out[o + 1] = _signed(pw.amount, 10)
        out[o + 2] = _signed(pw.amount, 50)


def power_triples(creature) -> list[float]:
    """Full power vocabulary: per power id, presence bit + signed amount at
    a fine (±10) and a coarse (±50) scale. Signed so Strength/Dexterity
    below zero stay representable; presence disambiguates 'absent' from
    'present at 0'. Thin list-returning wrapper over ``_write_power_triples``
    for legacy callers; the obs builders write in place. Computed in float64
    so the returned list is bit-identical to the pre-vectorization API (the
    observation itself is float32, exactly as before)."""
    out = np.array(_POWER_BG, dtype=np.float64)
    _write_power_triples(creature, out, 0)
    return out.tolist()


def _write_pile_composition(pile, out: np.ndarray, base: int) -> None:
    """Write a pile's normalized base/upgraded histogram into
    ``out[base : base+2·N_CARDS]`` (which must start zeroed). Loops the pile's
    cards (tens) and writes only the distinct ids present — never scans the
    2·N_CARDS slots or clips constants. Matches the reference exactly: counts
    are ``count / PILE_COUNT_CAP`` clipped to 1.0."""
    counts: dict[int, int] = {}
    for card in pile:
        idx = CARD_INDEX[card.id]
        key = (N_CARDS + idx) if card.upgrade_level > 0 else idx
        counts[key] = counts.get(key, 0) + 1
    for key, c in counts.items():
        v = c / PILE_COUNT_CAP
        out[base + key] = 1.0 if v > 1.0 else v


def pile_composition(pile: list[Card]) -> list[float]:
    """Order-agnostic histogram of a card pile, split by upgrade state.

    Returns ``2 * N_CARDS`` normalized counts: the first ``N_CARDS`` are
    base (unupgraded) copies per card id, the next ``N_CARDS`` are upgraded
    copies. Splitting the histogram is what lets the policy tell a pile of
    Strikes from a pile of Strike+ — upgrade is (currently) a single bit per
    card, so a base/upgraded split captures it exactly; any card whose
    ``upgrade_level`` climbs past 1 in future simply counts as upgraded. Thin
    list-returning wrapper (float64, bit-identical to the pre-vectorization
    API); the obs builders write float32 in place."""
    out = np.zeros(2 * N_CARDS, dtype=np.float64)
    _write_pile_composition(pile, out, 0)
    return out.tolist()


def card_features(state: CombatState, card: Card | None) -> list[float]:
    f = [0.0] * N_CARD_FEATURES
    if card is None:
        return f
    s = state
    # Effective cost: hook-modified (Corruption, Tangled, per-turn
    # discounts via card.energy_cost); X-cost = all remaining energy.
    effective_cost = preview_card_energy_cost(s, card)
    f[0] = _clip01(effective_cost / 6.0)
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
    f[16] = _clip01(card.upgrade_level / 5.0)
    # Base numbers (upgrade-adjusted; dynamic cards like Body Slam /
    # Perfected Strike report their current computed base).
    base_dmg = card_base_damage(s, card, None)
    if base_dmg is not None:
        f[17], f[18] = _abs2(base_dmg)
    f[19] = _clip01(card.base_hits / 10.0)
    if card.base_block is not None:
        f[20] = _clip01(card.base_block / ABS_SCALE)
        eff_block = preview_card_block(s, card)
        f[21] = _clip01(eff_block / ABS_SCALE)
    f[22] = _clip01(card.base_hp_loss / ABS_SCALE)
    magic = card.magic_number
    f[23] = _clip01(magic / 20.0) if magic is not None else 0.0
    return f


def _write_damage_matrix(state: CombatState, out: np.ndarray, base: int) -> None:
    """Write the MAX_HAND × MAX_ENEMIES per-hit damage previews into
    ``out[base : base+MAX_HAND·MAX_ENEMIES]`` (zeroed). Only nonzero cells are
    written; empty slots, gone enemies, and no-damage cards keep the zero
    background (identical to the reference, which appended 0 for them)."""
    s = state
    hand = s.player.hand
    enemies = s.enemies
    ne = len(enemies)
    for h in range(min(MAX_HAND, len(hand))):
        card = hand[h]
        rowbase = base + h * MAX_ENEMIES
        for e_i in range(min(MAX_ENEMIES, ne)):
            e = enemies[e_i]
            if e.is_gone:
                continue
            dmg = preview_card_damage(s, card, e)
            if dmg:
                v = dmg / ABS_SCALE
                out[rowbase + e_i] = 1.0 if v > 1.0 else v


def damage_matrix(state: CombatState) -> list[float]:
    """MAX_HAND × MAX_ENEMIES effective per-hit damage previews, in the
    shared absolute unit; 0 for empty slots, gone enemies, and cards that
    deal no enemy damage. Thin list-returning wrapper (float64, bit-identical
    to the pre-vectorization API); obs builders write float32 in place."""
    out = np.zeros(MAX_HAND * MAX_ENEMIES, dtype=np.float64)
    _write_damage_matrix(state, out, 0)
    return out.tolist()


# Intra-enemy-row byte offsets (relative to the row start), derived once from
# the layout — enemy rows are identical in both card_obs modes.
def _enemy_row_offsets() -> dict[str, int]:
    sl = obs_slices("hybrid")
    base = sl["enemy0.present"].start
    return {
        "hp_ratio": sl["enemy0.hp_ratio"].start - base,
        "hp_abs": sl["enemy0.hp_abs"].start - base,
        "max_hp": sl["enemy0.max_hp_abs"].start - base,
        "block": sl["enemy0.block_abs"].start - base,
        "strength": sl["enemy0.strength"].start - base,
        "flags": sl["enemy0.intent_flags"].start - base,
        "preview": sl["enemy0.intent_preview"].start - base,
        "identity": sl["enemy0.identity"].start - base,
        "powers": sl["enemy0.powers"].start - base,
    }


_ENEMY_E_OFF = _enemy_row_offsets()


def _write_enemy_row(state: CombatState, e, out: np.ndarray, rb: int,
                     off: dict[str, int]) -> None:
    """Write a *living* enemy's row into ``out`` starting at ``rb``. The row's
    scalar/identity region must be zeroed and its power sub-block must hold the
    ``_POWER_BG`` background; only present features/powers are written."""
    s = state
    out[rb] = 1.0
    out[rb + off["hp_ratio"]] = _clip01(e.hp / max(1, e.max_hp))
    o = rb + off["hp_abs"]; out[o:o + 2] = _abs2(e.hp)
    o = rb + off["max_hp"]; out[o:o + 2] = _abs2(e.max_hp)
    o = rb + off["block"]; out[o:o + 2] = _abs2(e.block)
    out[rb + off["strength"]] = _signed(e.strength, 30)

    intent = e.current_intent
    fb = rb + off["flags"]
    if intent.has(MoveType.ATTACK):
        out[fb] = 1.0
    if intent.has(MoveType.DEFEND):
        out[fb + 1] = 1.0
    if intent.has(MoveType.BUFF):
        out[fb + 2] = 1.0
    if (intent.has(MoveType.DEBUFF) or intent.has(MoveType.DEBUFF_STRONG)
            or intent.has(MoveType.CARD_DEBUFF)):
        out[fb + 3] = 1.0
    if intent.has(MoveType.STATUS_CARD):
        out[fb + 4] = 1.0
    if intent.has(MoveType.SUMMON):
        out[fb + 5] = 1.0
    if intent.has(MoveType.ESCAPE):
        out[fb + 6] = 1.0
    if intent.has(MoveType.HEAL):
        out[fb + 7] = 1.0
    if intent.has(MoveType.STUN) or intent.has(MoveType.SLEEP) or e.stunned:
        out[fb + 8] = 1.0

    # Telegraphed attack through the full modifier pipeline (what the
    # game displays — see AttackIntent.GetSingleDamage), plus a post-block
    # preview against the player's current block.
    preview = preview_incoming_damage(s, e)
    if preview is not None:
        pb = rb + off["preview"]
        out[pb] = _clip01(preview.per_hit / ABS_SCALE)
        out[pb + 1] = _clip01(preview.hits / 10.0)
        out[pb + 2:pb + 4] = _abs2(preview.total)
        out[pb + 4:pb + 6] = _abs2(preview.post_block)

    # Enemy identity one-hot (unknown classes stay all-zero).
    idx = MONSTER_INDEX.get(e.__class__.__name__)
    if idx is not None:
        out[rb + off["identity"] + idx] = 1.0

    _write_power_triples(e, out, rb + off["powers"])


def enemy_row(state: CombatState, e) -> list[float]:
    """One enemy's observation row (thin list-returning wrapper; obs builders
    write in place; float64, bit-identical to the pre-vectorization API).
    Gone/absent enemies are an all-zero row."""
    out = np.zeros(ENEMY_ROW_DIM, dtype=np.float64)
    if e is not None and not e.is_gone:
        pb = _ENEMY_E_OFF["powers"]
        out[pb:pb + 3 * N_POWERS] = _POWER_BG
        _write_enemy_row(state, e, out, 0, _ENEMY_E_OFF)
    return out.tolist()


@dataclass(frozen=True)
class _CombatLayout:
    """Precomputed integer write-offsets and the constant template for one
    ``card_obs`` mode — derived once from ``obs_slices`` so it can never drift
    from the layout. ``_write_combat_obs`` writes into a copy of ``template``."""
    dim: int
    template: np.ndarray
    hybrid: bool
    p: dict            # player segment name (sans "player.") -> start offset
    p_powers: int
    enemy_base: int
    enemy_stride: int
    e_off: dict
    hand_base: int
    hand_stride: int
    h_onehot: int      # offset within a hand row, or -1 in "features" mode
    h_feat: int
    dmg_base: int
    potion_base: int
    potion_stride: int
    po_onehot: int
    po_targeted: int
    draw: int
    discard: int
    exhaust: int


@lru_cache(maxsize=None)
def _combat_layout(card_obs: str) -> _CombatLayout:
    sl = obs_slices(card_obs)
    dim = sum(w for _, w in obs_segments(card_obs))

    p = {name.split(".", 1)[1]: s.start for name, s in sl.items()
         if name.startswith("player.")}
    p_powers = sl["player.powers"].start

    enemy_base = sl["enemy0.present"].start
    enemy_stride = sl["enemy1.present"].start - enemy_base

    hand_base = sl["hand0.present"].start
    hand_stride = sl["hand1.present"].start - hand_base
    hybrid = card_obs == "hybrid"
    h_onehot = (sl["hand0.onehot"].start - hand_base) if hybrid else -1
    h_feat = sl["hand0.features"].start - hand_base

    potion_base = sl["potion0"].start
    potion_stride = sl["potion1"].start - potion_base

    template = np.zeros(dim, dtype=np.float32)
    template[p_powers:p_powers + 3 * N_POWERS] = _POWER_BG
    for e in range(MAX_ENEMIES):
        b = enemy_base + e * enemy_stride + _ENEMY_E_OFF["powers"]
        template[b:b + 3 * N_POWERS] = _POWER_BG

    return _CombatLayout(
        dim=dim, template=template, hybrid=hybrid, p=p, p_powers=p_powers,
        enemy_base=enemy_base, enemy_stride=enemy_stride, e_off=_ENEMY_E_OFF,
        hand_base=hand_base, hand_stride=hand_stride, h_onehot=h_onehot,
        h_feat=h_feat, dmg_base=sl["damage_matrix"].start,
        potion_base=potion_base, potion_stride=potion_stride,
        po_onehot=1, po_targeted=1 + N_POTIONS,
        draw=sl["draw_pile"].start, discard=sl["discard_pile"].start,
        exhaust=sl["exhaust_pile"].start,
    )


def _write_combat_obs(state: CombatState, L: _CombatLayout, buf: np.ndarray) -> None:
    """Sparse-write the live combat features into ``buf`` (which must already
    hold ``L.template`` — the power backgrounds and zeros). Only the few dozen
    nonzero entries per step are touched."""
    s = state
    p = s.player
    P = L.p

    # ── Player vitals (layout mirrors the player.* segments) ─────────
    buf[P["hp_ratio"]] = _clip01(p.hp / max(1, p.max_hp))
    o = P["hp_abs"]; buf[o:o + 2] = _abs2(p.hp)
    o = P["max_hp_abs"]; buf[o:o + 2] = _abs2(p.max_hp)
    o = P["block_abs"]; buf[o:o + 2] = _abs2(p.block)
    buf[P["energy"]] = _clip01(p.energy / 10.0)
    buf[P["strength"]] = _signed(p.strength, 30)
    buf[P["dexterity"]] = _signed(_power_amt(p, "dexterity"), 30)
    ps = P["pile_sizes"]
    buf[ps] = _clip01(len(p.hand) / MAX_HAND)
    buf[ps + 1] = _clip01(len(p.draw_pile) / 40.0)
    buf[ps + 2] = _clip01(len(p.discard_pile) / 40.0)
    buf[ps + 3] = _clip01(len(p.exhaust_pile) / 40.0)
    buf[P["turn"]] = _clip01(s.turn / 30.0)
    o = P["incoming_post_block"]; buf[o:o + 2] = _abs2(preview_total_incoming(s))
    # History scalars the deck can condition on (Stomp, Spite, ...).
    cards_this_turn = sum(1 for _ in s.history.of_type(CardPlayedEntry, this_turn=True))
    dmg_taken = sum(
        e.amount for e in s.history.of_type(DamageReceivedEntry) if e.target is p
    )
    buf[P["cards_played_this_turn"]] = _clip01(cards_this_turn / 10.0)
    buf[P["attacks_this_turn"]] = _clip01(s.history.attack_plays_this_turn() / 10.0)
    o = P["damage_taken"]; buf[o:o + 2] = _abs2(dmg_taken)
    _write_power_triples(p, buf, L.p_powers)

    # ── Hand rows (empty slots keep the zero template) ───────────────
    hand = p.hand
    for h in range(min(MAX_HAND, len(hand))):
        card = hand[h]
        rb = L.hand_base + h * L.hand_stride
        buf[rb] = 1.0
        if L.h_onehot >= 0:
            buf[rb + L.h_onehot + CARD_INDEX[card.id]] = 1.0
        fb = rb + L.h_feat
        buf[fb:fb + N_CARD_FEATURES] = card_features(s, card)

    # ── Enemy rows (gone/absent rows are zeroed to clear power bg) ────
    enemies = s.enemies
    ne = len(enemies)
    for e_i in range(MAX_ENEMIES):
        rb = L.enemy_base + e_i * L.enemy_stride
        e = enemies[e_i] if e_i < ne else None
        if e is None or e.is_gone:
            buf[rb:rb + L.enemy_stride] = 0.0
            continue
        _write_enemy_row(s, e, buf, rb, L.e_off)

    # ── Effective damage matrix (aligned 1:1 with play(h, e) actions) ─
    _write_damage_matrix(s, buf, L.dmg_base)

    # ── Potion rows ──────────────────────────────────────────────────
    potions = p.potions
    for pi in range(min(MAX_POTIONS, len(potions))):
        potion = potions[pi]
        if potion is None:
            continue
        rb = L.potion_base + pi * L.potion_stride
        buf[rb] = 1.0
        buf[rb + L.po_onehot + POTION_INDEX[potion.id]] = 1.0
        if potion.targeted:
            buf[rb + L.po_targeted] = 1.0

    # ── Pile composition (unordered; base vs upgraded copies per card) ─
    _write_pile_composition(p.draw_pile, buf, L.draw)
    _write_pile_composition(p.discard_pile, buf, L.discard)
    _write_pile_composition(p.exhaust_pile, buf, L.exhaust)


def build_combat_obs(
    state: CombatState, card_obs: str = "hybrid", out: np.ndarray | None = None,
) -> np.ndarray:
    """The full combat observation (schema v3) for a CombatState — the body
    of STS2FullCombatEnv._build_obs, reusable by the run env (which embeds it
    as its combat block, zeroed outside combat).

    Template + sparse writes: start from a precomputed constant template (all
    zeros plus the absent-power backgrounds) and overwrite only the entries
    that are nonzero this step. Pass ``out=`` a length-``dim`` array (e.g. a
    slice of the run buffer) to write in place; with ``out=None`` a fresh
    array is returned (an independent copy, safe for the caller to store)."""
    L = _combat_layout(card_obs)
    if out is None:
        buf = L.template.copy()
    else:
        np.copyto(out, L.template)
        buf = out
    _write_combat_obs(state, L, buf)
    return buf


class STS2FullCombatEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        *,
        encounter: Encounter | None = None,
        encounters: Sequence[Encounter] | None = None,
        deck: Sequence[str] | None = None,
        potions: Sequence[str] | None = None,
        card_obs: str = "hybrid",
        card_selector: Callable[[str, list[Card], int], list[Card]] | None = scripted_card_selector,
        reward_win: float = 1.0,
        reward_loss: float = 0.0,
        win_hp_bonus: float = 0.0,
        hp_reward_scale: float = 1.0,
        enemy_hp_reward_scale: float = 0.0,
        max_steps: int = 2000,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        if card_obs not in ("hybrid", "features"):
            raise ValueError("card_obs must be 'hybrid' or 'features'")

        # Encounter pool to sample each reset.
        if encounter is not None:
            self._encounters: list[Encounter] = [encounter]
        elif encounters is not None:
            self._encounters = list(encounters)
            if not self._encounters:
                raise ValueError("encounters is empty")
        else:
            self._encounters = list(DEFAULT_ENCOUNTERS)

        self._deck_ids = list(deck) if deck is not None else list(DEFAULT_DECK_IDS)
        self._potion_ids = list(potions) if potions is not None else []
        self._card_obs = card_obs
        self._card_selector = card_selector
        self._reward_win = reward_win
        self._reward_loss = reward_loss
        self._win_hp_bonus = win_hp_bonus
        self._hp_reward_scale = hp_reward_scale
        self._enemy_hp_reward_scale = enemy_hp_reward_scale
        self._max_steps = max_steps
        self.render_mode = render_mode

        # Action space: end turn + play(hand, target) + potion(slot, target).
        self._play_base = 1
        self._potion_base = 1 + MAX_HAND * MAX_ENEMIES
        self.n_actions = self._potion_base + MAX_POTIONS * MAX_ENEMIES
        self.action_space = spaces.Discrete(self.n_actions)

        self._state: CombatState | None = None
        self._rng = random.Random()
        self._steps = 0
        self._encounter_start_hp = 1

        # Measure the observation dimension once from a throwaway combat so the
        # declared space can never disagree with _build_obs.
        probe = self._new_state(random.Random(0))
        self._state = probe
        obs_dim = len(self._build_obs())
        self._state = None
        self.observation_space = spaces.Box(0.0, 1.0, shape=(obs_dim,), dtype=np.float32)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _new_state(self, rng: random.Random) -> CombatState:
        deck = [make_card(cid) for cid in self._deck_ids]
        potions = [make_potion(pid) for pid in self._potion_ids] or None
        encounter = rng.choice(self._encounters)
        # The selector goes in at construction so turn-1 selection effects
        # (e.g. Gambling Chip's mulligan) already see it.
        state = CombatState(
            starting_deck=deck, rng=rng, encounter=encounter, potions=potions,
            card_selector=self._card_selector,
        )
        return state

    # ------------------------------------------------------------------
    # gym interface
    # ------------------------------------------------------------------

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = random.Random(seed)
        self._state = self._new_state(self._rng)
        self._encounter_start_hp = max(1, sum(e.max_hp for e in self._state.enemies))
        self._steps = 0
        return self._build_obs(), self._info()

    def step(self, action: int):
        assert self._state is not None, "call reset() before step()"
        s = self._state
        self._steps += 1

        hp_before = s.player.hp
        enemy_hp_before = self._total_enemy_hp()

        apply_combat_action(s, int(action))   # illegal actions are no-ops

        reward = self._hp_reward_scale * (s.player.hp - hp_before) / max(1, s.player.max_hp)
        if self._enemy_hp_reward_scale:
            reward += (
                self._enemy_hp_reward_scale
                * (enemy_hp_before - self._total_enemy_hp())
                / self._encounter_start_hp
            )

        terminated = s.is_over
        if terminated:
            if s.result.player_won:
                # Win bonus scaled by HP conserved: reward_win is the floor for
                # any win, win_hp_bonus * (final HP fraction) rewards winning
                # *clean*, so a full-HP win beats a near-death one.
                reward += self._reward_win + self._win_hp_bonus * (
                    s.player.hp / max(1, s.player.max_hp)
                )
            else:
                reward += self._reward_loss
        truncated = (not terminated) and self._steps >= self._max_steps

        return self._build_obs(), float(reward), terminated, truncated, self._info()

    def action_masks(self) -> np.ndarray:
        """Boolean legality mask over the flat action space (for MaskablePPO)."""
        return combat_action_masks(self._state)

    def render(self) -> None:
        if self.render_mode != "human" or self._state is None:
            return
        s = self._state
        print(f"\n=== Turn {s.turn} ===")
        p = s.player
        print(f"Player HP {p.hp}/{p.max_hp}  Block {p.block}  Energy {p.energy}")
        for i, e in enumerate(s.enemies):
            tag = "DEAD" if e.is_gone else f"HP {e.hp}/{e.max_hp} Block {e.block}"
            intent = "" if e.is_gone else f"  intent={e.current_intent.move_type.value}"
            print(f"  [{i}] {e.__class__.__name__}: {tag}{intent}")
        print(f"Hand: {[repr(c) for c in p.hand]}")

    # ------------------------------------------------------------------
    # Action decoding (module-level decode_combat_action does the work)
    # ------------------------------------------------------------------

    def _decode_action(self, action: int) -> tuple[str, int, int | None]:
        return decode_combat_action(int(action))

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def _total_enemy_hp(self) -> int:
        return sum(e.hp for e in self._state.enemies if not e.is_gone)

    # The observation is built by the module-level build_combat_obs (shared
    # with the run env); these thin delegates keep the historical method
    # surface for tests and subclasses.

    @staticmethod
    def _power_amt(creature, pid: str) -> float:
        return _power_amt(creature, pid)

    @staticmethod
    def _power_triples(creature) -> list[float]:
        return power_triples(creature)

    def _build_obs(self) -> np.ndarray:
        return build_combat_obs(self._state, self._card_obs)

    def _pile_composition(self, pile: list[Card]) -> list[float]:
        return pile_composition(pile)

    def _card_features(self, card: Card | None) -> list[float]:
        return card_features(self._state, card)

    def _damage_matrix(self) -> list[float]:
        return damage_matrix(self._state)

    def _enemy_row(self, e) -> list[float]:
        return enemy_row(self._state, e)

    # ------------------------------------------------------------------

    def _info(self) -> dict[str, Any]:
        s = self._state
        info: dict[str, Any] = {"turn": s.turn, "phase": s.phase.value}
        if s.is_over:
            info["is_success"] = bool(s.result.player_won)
            info["hp_left"] = max(0, s.player.hp)
        return info


class AblatedObsEnv(gym.ObservationWrapper):
    """The baseline arm of the OBS_PLAN Phase 4 ablation: the same env with
    the absolute-number / preview features zeroed (``numeric_obs_indices``) —
    what the agent saw before the schema-v2 numeric overhaul. Dynamics, action
    space, masks, and the obs *shape* are untouched, so full/ablated runs are
    comparable dimension-for-dimension on the same seeds."""

    def __init__(self, env: STS2FullCombatEnv, indices: np.ndarray | None = None) -> None:
        super().__init__(env)
        if indices is None:
            indices = numeric_obs_indices(env.unwrapped._card_obs)
        self._ablated = np.asarray(indices, dtype=np.int64)

    def observation(self, observation: np.ndarray) -> np.ndarray:
        observation = observation.copy()
        observation[self._ablated] = 0.0
        return observation

    def action_masks(self) -> np.ndarray:
        return self.env.action_masks()
