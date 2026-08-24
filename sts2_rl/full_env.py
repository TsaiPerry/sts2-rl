"""STS2FullCombatEnv — a Gymnasium env that exposes the *whole* combat.

Unlike the toy ``STS2CombatEnv`` (3 actions, one hardcoded fight), this env
drives the real engine: play any card in hand at any target, use potions, and
end the turn — across a configurable pool of encounters and a configurable
deck. It is built for ``sb3-contrib``'s ``MaskablePPO`` (an ``action_masks``
method reports the legal actions each step).

Design at a glance
------------------
Action space (flat ``Discrete``), decoded in ``_decode_action`` — UNCHANGED by
the schema-v4 observation rewrite below::

    0                          end turn
    1 .. H*E                   play hand card h at enemy target e
    1+H*E .. 1+H*E+P*E         use potion p at enemy target e

  where H = MAX_HAND, E = MAX_ENEMIES, P = MAX_POTIONS. Cards/potions that
  don't need a target (SELF / ALL_ENEMIES / non-targeted potions) are masked to
  a single canonical target so equivalent actions don't bloat the space.

Observation: ``OBS_SCHEMA_VERSION`` 4, the ``{"f": Box(0,1), "i": Box(0,
MAX_ID)}`` Dict contract of ``OBS_SCHEMA.md`` (this module's combat half —
``sts2_rl/obs.py`` for the shared contract, ``sts2_rl/relic_obs.py`` for the
relic row, ``sts2_rl/afflictions.py`` / ``sts2_rl/enchantments.py`` for the two
new vocabularies). Replaces the v3 flat float ``Box`` (17,873 floats, ~96% of
it sparse one-hot categoricals): every entity (a power INSTANCE, a relic, a
hand/pile card, an enemy, a potion) is now one row of ``(id, floats)`` instead
of a slot in a per-id one-hot, so two instances of the same power (The Bomb's
independently-ticking fuses) are two rows, not one dict slot silently
overwritten by the second.

The blocks (see OBS_SCHEMA.md §5 for the exact layout table):

* Player vitals — the pre-v4 scalar segments (hp/max_hp/block/energy/
  strength/dexterity/pile sizes/turn/incoming/history), names and encodings
  UNCHANGED (``--zero-segments`` and the pin tests address these by name).
* ``player.powers`` / ``enemy{e}.powers`` — every power INSTANCE on the
  creature (C#'s application order, oldest first), not one row per id:
  ``(power_id, amount_fine, amount_coarse, aux)``. ``aux`` carries the one
  per-instance numeric field beyond ``amount`` a handful of powers need (The
  Bomb's own blast damage, and others — see ``_power_aux``).
* ``player.relics`` — every relic the player holds, acquisition order:
  ``(relic_id, counter, flag)``, delegating the two aux floats to
  ``relic_obs.relic_row`` (which already applies every admissibility rule).
* ``hand`` — POSITIONAL (row *is* the action index): ``(card_id,
  affliction_id, enchantment_id)`` plus the 31 hand floats (``card_features``
  plus five R2 per-instance fields).
* ``enemies`` — POSITIONAL, monster identity id plus the 25-float enemy row
  (vitals, 9 intent flags, 6 intent-preview floats, 1 StatusIntent card-count
  float — the last one is v5; see ``_enemy_floats``).
* ``enemy{e}.intent_history`` — R3 (v6), one segment per enemy slot: the
  last ``MAX_INTENT_HISTORY`` (3) DISPLAYED intents for whichever creature
  currently occupies that slot, keyed internally by ``net_id`` (not list
  position) so slot-reordering encounters can't cross-contaminate two
  creatures' histories. No ``.ids`` half — see ``_N_ENEMY_HISTORY_SCALARS``.
* ``damage_matrix`` — unchanged: the per-(hand slot, enemy slot) effective
  per-hit damage preview, aligned 1:1 with the play actions.
* ``potions`` — POSITIONAL: potion id plus a targeted flag.
* ``cards`` — the ONE draw+discard+exhaust block, the ONLY sorted block (pile
  order is hidden information the real game never gives the player — see
  OBS_SCHEMA.md §5.3): ``(pile_id, card_id, affliction_id, enchantment_id)``
  ints, ``(upgrade, effective_cost, affliction_amount, exhaust_on_next_play)``
  floats. ``pile_id`` (1=draw, 2=discard, 3=exhaust) is a LITERAL, not a
  vocab index.

``card_obs`` keeps its two values, but v4's layout is IDENTICAL for both (an
id is one int, not a 640-wide one-hot): ``"features"`` writes PAD in place of
``card_id`` in ``hand.ids`` rows ONLY. The ``cards`` (pile) block always keeps
card identity in both modes — today's ``"features"`` mode only ever dropped
the hand one-hot, and the pile histograms always kept card identity, so
blanking them here would silently widen the ablation beyond what it has ever
meant.

Every padded row is ``id == 0`` (``PAD``) and all-zero floats (OBS_SCHEMA.md
§2.1) — a power *present* at amount 0 stays distinguishable from one that is
*absent* (id nonzero either way; the 0.5-centered ``_signed`` encoding never
reads exactly 0.0 for a present instance, only a padded slot does).

Simplifications (documented, not silent): mid-play card *selections*
(Armaments, Burning Pact, the Knowledge Demon curse pick, …) are not exposed
as separate timesteps; they are resolved by ``scripted_card_selector`` — a
deterministic heuristic (see ``selectors.py``), so training sees no hidden
stochasticity from selection effects. Pass ``card_selector=`` to substitute
your own policy, or ``card_selector=None`` for the engine's seeded-random
default. Living enemies past ``MAX_ENEMIES`` (only reachable via unusually
spammy summons) are not targetable.
"""
from __future__ import annotations

import copy
import random
from functools import lru_cache
from typing import Any, Callable, Sequence

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from .afflictions import AFFLICTION_INDEX
from .cards import Card, CardType, TargetType, make_card
from .cards.base import _CARD_CLASSES
from .combat import CombatState, Phase
from .enchantments import ENCHANTMENT_INDEX
from .history import CardPlayedEntry, DamageReceivedEntry
from .monsters import Encounter, Monster, MoveType
from .monsters.base import MAX_INTENT_HISTORY, intent_flags
from .monsters.overgrowth import BOSS_ENCOUNTER_KEYS as _BOSS_KEYS
from .monsters.overgrowth import ENCOUNTERS as _OVERGROWTH
from .obs import ObsBuffer, ObsLayout, PAD, oid
from .player import PlayerCombatState
from .potions import ALL_POTIONS, Potion, make_potion
from .powers import ALL_POWERS
from .relic_obs import relic_row
from .relics import ALL_RELICS, Relic
from .selectors import scripted_card_selector
from .snapshots import SnapshotDataset, build_start_state, load_snapshots
from .vocab import capacity as vocab_capacity, frozen_ids
from .previews import (
    card_base_block,
    card_base_damage,
    preview_card_block,
    preview_card_damage,
    preview_card_energy_cost,
    preview_incoming_damage,
    preview_total_incoming,
)
from .valueprops import ValueProp

# Bump whenever the observation layout changes (any change invalidates saved
# models — retrain).
# v4 (OBS_SCHEMA.md): flat float Box -> {"f": Box(0,1), "i": Box(0, MAX_ID)}
#   Dict; every entity is a row addressed by id, not a one-hot slot.
# v5: enemy row grows 24->25 floats — StatusIntent's displayed card count
#   (NIntent.cs:133-136 writes a number for AttackIntent AND StatusIntent;
#   only the former was encoded) is field 24.
# v6 (R3): per-enemy intent HISTORY — last MAX_INTENT_HISTORY (3) DISPLAYED
#   intents per enemy, keyed by net_id (not slot position) so the
#   slot-reordering encounters (ovicopter_normal, fabricator_normal,
#   living_fog_normal) can't cross-contaminate histories. New
#   `enemy{e}.intent_history.f` segments (no `.ids` half — see §5.2).
# v7: schema audit reclassified semantics only, no width change, except
#   `cards.f`'s `effective_cost` (`_pile_card_row`) now reads the card's
#   PLAIN printed `energy_cost` instead of `previews.preview_card_energy_cost`
#   — draw/discard/exhaust piles aren't `Hand`, so the game's own
#   `UpdateDynamicVarPreview` hook gate is FALSE for them (matches
#   `run_env._run_card_row`'s existing behavior).
# v8: two new hand.f fields (OBS_SCHEMA.md §5.2) — f[29] glow_gold
#   (CardModel.ShouldGlowGold, the ONLY obs carrier for on_play-only
#   conditions like Pact's End's exhaust-pile check) and f[30]
#   block_preview_move (the full MOVE-pipeline block preview: Dexterity,
#   Frail, enchantments, Fasten). Field 21 deliberately keeps its old
#   ValueProp.NONE parity value — see card_features's field-21 comment.
OBS_SCHEMA_VERSION = 8

# ── Fixed-size bounds (obs/action slots). Bump + retrain if an encounter or a
#    relic ever exceeds these. ────────────────────────────────────────────────
MAX_HAND = PlayerCombatState.MAX_HAND_SIZE      # 10
MAX_POTIONS = PlayerCombatState.MAX_POTIONS      # 3
MAX_ENEMIES = 6                                  # initial lineup ≤4; headroom for summons

# The `potions` OBSERVATION block is sized past MAX_POTIONS (3, the belt's
# default) because `PlayerCombatState.__init__` (player.py:136-139) accepts a
# `max_potions` grown past 3, and `RunState.create_combat` (run.py:1601)
# passes the run's grown `max_potions` into every combat it builds. Three
# relics grow the belt via `RunState.add_potion_slots` (run.py:808-813):
# `phial_holster.py:18` (+1), `potion_belt.py:19` (+2, COMMON, always
# reachable), `alchemical_coffer.py:27` (+4, ANCIENT) — each unique/one-shot,
# so worst case is base 3 + 1 + 2 + 4 = 10. This constant is the
# observation-only ceiling; it does NOT touch the action space
# (COMBAT_POTION_BASE / combat_action_count / STS2FullCombatEnv.n_actions
# stay keyed on MAX_POTIONS). `run_env.py`'s `action_masks` writes
# `mask[POTION_BASE + (answer - POTION_ACTION_BASE)]` per ACTUAL belt slot,
# so an undersized ceiling there raises IndexError once a held Potion Belt
# grows the belt past it — `run_env.MAX_POTION_SLOTS` /
# `N_COMBAT_ACTIONS` / `POTION_BASE` / `N_ACTIONS` all derive from this
# constant so the fix lands in one place.
MAX_POTION_ROWS = 10

# OBS_SCHEMA.md §4 — every one of these traces to a measurement in the phase-1
# ledger, not a guess.
MAX_POWERS_PLAYER = 32
MAX_POWERS_ENEMY = 16
MAX_RELIC_ROWS = 48
MAX_COMBAT_CARDS = 96

# Shared absolute unit for every HP-like quantity (HP, block, damage): a fine
# /100 scale plus a coarse /500 companion so Act-2+ values don't saturate.
# One shared unit lets the network compare features (incoming vs remaining HP)
# with a single learned mapping.
ABS_SCALE = 100.0
ABS_SCALE_COARSE = 500.0

# Stable vocabularies (index = position), frozen append-only via vocab.json
# so ported content never shifts existing indices; every N_* layout constant
# is the reserved *capacity* (padded slots stay zero/masked), so obs and
# action dims survive new content — see sts2_rl/vocab.py.
# Importing .cards / .potions / .monsters / .powers / .relics has already
# registered every class into these registries.
CARD_IDS: list[str] = frozen_ids("cards", _CARD_CLASSES)
CARD_INDEX: dict[str, int] = {cid: i for i, cid in enumerate(CARD_IDS)}
N_CARDS = vocab_capacity("cards")

POTION_IDS: list[str] = frozen_ids("potions", ALL_POTIONS)
POTION_INDEX: dict[str, int] = {pid: i for i, pid in enumerate(POTION_IDS)}
N_POTIONS = vocab_capacity("potions")

# The FULL power vocabulary (no curated subset: an unlisted power would be
# silently invisible to the agent). Strength/dexterity also get dedicated
# signed scalar slots for resolution, but stay in the vocabulary for
# uniformity. No longer sized as a one-hot-triple BLOCK WIDTH (that was v3;
# v4's player.powers/enemy{e}.powers are id-addressed instance rows, capped
# at MAX_POWERS_PLAYER/ENEMY) — POWER_INDEX is still how a power id becomes
# an observation id.
POWER_IDS: list[str] = frozen_ids("powers", ALL_POWERS)
POWER_INDEX: dict[str, int] = {pid: i for i, pid in enumerate(POWER_IDS)}
N_POWERS = vocab_capacity("powers")

# New in v4 (OBS_SCHEMA.md §6, R1): the combat observation had no relic
# segment at all before. Built here (not imported from run_env.py, which
# computes the identical thing for the run observation) so full_env.py has no
# dependency on run_env.py — frozen_ids is idempotent against the same
# persisted vocab.json key, so the two computations agree by construction.
RELIC_IDS: list[str] = frozen_ids("relics", ALL_RELICS)
RELIC_INDEX: dict[str, int] = {rid: i for i, rid in enumerate(RELIC_IDS)}
N_RELICS = vocab_capacity("relics")


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

# The largest storable observation id: stored id = vocab index + 1 (obs.oid),
# and index < capacity, so the max stored id over every vocabulary the
# observation uses equals the max CAPACITY over those vocabularies. Computed,
# not hardcoded, so a future capacity bump can never silently disagree with
# the declared space's upper bound.
MAX_OBS_ID = max(
    vocab_capacity(kind) for kind in
    ("cards", "relics", "powers", "monsters", "potions", "afflictions", "enchantments")
)

_CARD_TYPES = [CardType.ATTACK, CardType.SKILL, CardType.POWER, CardType.STATUS, CardType.CURSE]
_TARGET_TYPES = [
    TargetType.ANY_ENEMY, TargetType.ALL_ENEMIES, TargetType.RANDOM_ENEMY,
    TargetType.SELF, TargetType.NONE,
]

# card_features()'s per-hand-row / per-pile-row-adjacent width: the 24
# existing engineered features (cost/type/target/flags/numbers) plus 5 R2
# fields (OBS_SCHEMA.md §3.4) — affliction amount and three per-instance
# flags/counters no vocabulary can express — plus 2 v14 fields (§5.2):
# f[29] glow_gold (a flag) and f[30] block_preview_move (a preview number).
# Fields 17..23 of the original 24 are still "the card's numbers" (see
# _HAND_NUMERIC_OFFSETS below); the 5 R2 fields are deliberately NOT part of
# that numeric-ablation subset (see numeric_obs_indices) — f[30] IS, f[29]
# is not.
N_CARD_FEATURES = 31
#: Column of the hand.f / cards.f card row holding clip01(upgrade_level / 5)
#: (card_features below, CombatObsWriter.cs S(16)). Named so the duplicate-
#: merging policy decoder (evaluation.play_group_keys) reads the SAME cell.
CARD_UPGRADE_FEATURE = 16
# Enemy-row scalars (see _enemy_floats): present + hp ratio + hp×2 + max_hp×2
# + block×2 + strength + 9 intent flags + per_hit + hits + total×2 +
# post_block×2 + status_count. The first 24 are UNCHANGED from v3 — only the
# identity one-hot (now a single int id in enemies.ids) and the power
# vocabulary (now enemy{e}.powers, an instance-row block) moved out of this
# per-row float vector. Field 24 (status_count) is NEW in v5 — see
# OBS_SCHEMA_VERSION's comment and _enemy_floats.
_N_ENEMY_SCALARS = 25

# R3: one history slot's width. `recorded` (presence — §2.1's padding rule
# needs an explicit flag here because a history slot carries no id, so
# "id==0 and all-zero floats" isn't available to mean absent) + the 9 intent
# flags (`intent_flags` order) + 4 attack-preview floats (per_hit, hits,
# total_fine, total_coarse — `post_block` excluded, see
# `monsters.base.IntentHistoryEntry`'s docstring) + 1 StatusIntent
# card-count float = 15. `MAX_INTENT_HISTORY` (3) is sized in
# `monsters/base.py` by a census of every ported monster's repeat/cooldown
# windows (OBS_SCHEMA.md's R3 section has the numbers).
_N_ENEMY_HISTORY_SCALARS = 15


# ── v4 observation layout (OBS_SCHEMA.md §5) ─────────────────────────────────
# Named (segment, width) lists, exactly like v3's obs_segments()/obs_slices()
# but split across the int/float halves per sts2_rl.obs's ObsLayout
# convention: a logical block "name" is f"{name}.ids" (int half) / f"{name}.f"
# (float half). Consumed by build_combat_obs/write_combat_obs below, by
# STS2FullCombatEnv.observation_space, by the pin tests, and by T5's run env
# (which prefixes every name "combat." and folds these into its own layout —
# see write_combat_obs's docstring).


def _check_card_obs(card_obs: str) -> None:
    if card_obs not in ("hybrid", "features"):
        raise ValueError("card_obs must be 'hybrid' or 'features'")


def combat_obs_segments_i(card_obs: str = "hybrid") -> list[tuple[str, int]]:
    """The int half as an ordered (segment name, width) list (OBS_SCHEMA.md
    §3.1). Identical for both ``card_obs`` values — v4 stores an id as one
    int regardless of mode; only ``write_combat_obs`` reads ``card_obs`` (to
    decide whether ``hand.ids``' card_id column is PAD or real)."""
    _check_card_obs(card_obs)
    segs: list[tuple[str, int]] = [
        ("player.powers.ids", MAX_POWERS_PLAYER * 1),
        ("player.relics.ids", MAX_RELIC_ROWS * 1),
        ("hand.ids", MAX_HAND * 3),               # (card_id, affliction_id, enchantment_id)
        ("enemies.ids", MAX_ENEMIES * 1),          # monster_id
    ]
    for e in range(MAX_ENEMIES):
        segs.append((f"enemy{e}.powers.ids", MAX_POWERS_ENEMY * 1))
    segs.append(("potions.ids", MAX_POTION_ROWS * 1))
    # (pile_id, card_id, affliction_id, enchantment_id). pile_id (1=draw,
    # 2=discard, 3=exhaust) is a LITERAL, not a vocab index — see
    # OBS_SCHEMA.md §3.3's correction and _cards_rows below. pile_id comes
    # FIRST so ObsBuffer.write_rows(sort=True)'s generic (ints, floats) sort
    # reproduces the canonical (pile_id, card_id, ...) ordering.
    segs.append(("cards.ids", MAX_COMBAT_CARDS * 4))
    return segs


def combat_obs_segments_f(card_obs: str = "hybrid") -> list[tuple[str, int]]:
    """The float half as an ordered (segment name, width) list (OBS_SCHEMA.md
    §3.2). The player-vitals segment names/widths/encodings are UNCHANGED
    from v3 verbatim (``--zero-segments`` and the pin tests address them by
    name)."""
    _check_card_obs(card_obs)
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
        ("player.powers.f", MAX_POWERS_PLAYER * 3),    # (amount_fine, amount_coarse, aux)
        ("player.relics.f", MAX_RELIC_ROWS * 2),        # (counter/10, flag)
        ("hand.f", MAX_HAND * N_CARD_FEATURES),
        ("enemies.f", MAX_ENEMIES * _N_ENEMY_SCALARS),
    ]
    for e in range(MAX_ENEMIES):
        segs.append((f"enemy{e}.powers.f", MAX_POWERS_ENEMY * 3))
    # R3: no `.ids` counterpart — a history slot carries no id (see
    # `_N_ENEMY_HISTORY_SCALARS`'s docstring) — and no `.overflow` flag
    # either: unlike every other capped block, this one cannot overflow by
    # construction (the recorder is a `deque(maxlen=MAX_INTENT_HISTORY)`, so
    # it is physically impossible to ever hold more than the cap; there is no
    # externally-sized game quantity here for §2.3's "truncate rather than
    # assert" to apply to).
    for e in range(MAX_ENEMIES):
        segs.append(
            (f"enemy{e}.intent_history.f",
             MAX_INTENT_HISTORY * _N_ENEMY_HISTORY_SCALARS))
    segs.append(("damage_matrix", MAX_HAND * MAX_ENEMIES))
    segs.append(("potions.f", MAX_POTION_ROWS * 1))     # targeted flag
    segs.append(("cards.f", MAX_COMBAT_CARDS * 4))      # (upgrade, cost, affl_amt, exhaust_next)
    # Overflow flags (OBS_SCHEMA.md §2.3 / §3.5): one per capped block, set to
    # 1.0 iff ObsBuffer.write_rows truncated that block this step. Listed in
    # the order the blocks were introduced above.
    for name in ("player.powers", "player.relics", "hand", "enemies", "potions", "cards"):
        segs.append((f"{name}.overflow", 1))
    for e in range(MAX_ENEMIES):
        segs.append((f"enemy{e}.powers.overflow", 1))
    return segs


@lru_cache(maxsize=None)
def combat_obs_layout(card_obs: str = "hybrid") -> ObsLayout:
    return ObsLayout(combat_obs_segments_f(card_obs), combat_obs_segments_i(card_obs))


# ── Numeric ablation (OBS_PLAN Phase 4, step 12) ─────────────────────────────
# v4 packs a whole hand/enemy row into one "hand.f" / "enemies.f" segment, so
# the numeric subset is WITHIN-ROW offsets rather than whole segment names.
# Still means "what the agent saw before the schema-v2 numeric overhaul", so
# the 5 R2 hand fields (indices 24..28, added after v2) are deliberately
# excluded below. v14's f[30] (block_preview_move) IS a preview/numeric
# field, like f[17..23] — it joins this set. f[29] (glow_gold) is a flag,
# like f[25]-f[27], and stays excluded.
_HAND_NUMERIC_OFFSETS = tuple(range(17, 24)) + (30,)    # dmg×2, hits, block, eff_block, hp_loss, magic, block_preview_move
_ENEMY_NUMERIC_OFFSETS = (2, 3, 4, 5, 6, 7, 18, 19, 20, 21, 22, 23, 24)   # hp/max_hp/block_abs, preview, status_count
_PLAYER_NUMERIC_SEGMENTS = (
    "player.hp_abs", "player.max_hp_abs", "player.block_abs", "player.incoming_post_block",
)


def numeric_obs_indices(card_obs: str = "hybrid") -> np.ndarray:
    """Flat indices into ``obs["f"]`` of every absolute-number / preview
    feature (the v3 ablation, re-expressed over the v4 float layout).
    ``AblatedObsEnv.observation`` zeroes exactly these indices in ``obs["f"]``
    — ``obs["i"]`` is never touched, since ids are categorical, not numeric."""
    layout = combat_obs_layout(card_obs)
    idx: list[int] = []
    for name in _PLAYER_NUMERIC_SEGMENTS:
        sl = layout.f_slices[name]
        idx.extend(range(sl.start, sl.stop))
    dm = layout.f_slices["damage_matrix"]
    idx.extend(range(dm.start, dm.stop))
    hand_sl = layout.f_slices["hand.f"]
    for h in range(MAX_HAND):
        base = hand_sl.start + h * N_CARD_FEATURES
        idx.extend(base + o for o in _HAND_NUMERIC_OFFSETS)
    enemies_sl = layout.f_slices["enemies.f"]
    for e in range(MAX_ENEMIES):
        base = enemies_sl.start + e * _N_ENEMY_SCALARS
        idx.extend(base + o for o in _ENEMY_NUMERIC_OFFSETS)
    return np.asarray(sorted(idx), dtype=np.int64)


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
#    depends on how many potion slots the caller exposes. UNCHANGED by the
#    schema-v4 observation rewrite — the action space is not part of this
#    task. ──────────────────────────────────────────────────────────────────

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
        # PotionUsage.Automatic potions (Fairy in a Bottle) have no manual use.
        if potion is None or potion.automatic:
            continue
        if potion.targeted:
            for e in living:
                mask[COMBAT_POTION_BASE + p * MAX_ENEMIES + e] = True
        else:
            mask[COMBAT_POTION_BASE + p * MAX_ENEMIES + first] = True

    return mask


# ── Combat observation builder (shared by STS2FullCombatEnv and the run
#    env). Pure reads over a CombatState; layout documented segment-by-
#    segment in combat_obs_segments_i()/_f() above. ─────────────────────────


def _power_amt(creature, pid: str) -> float:
    pw = creature.powers.get(pid)
    return float(pw.amount) if pw is not None else 0.0


def _power_aux(pw) -> float:
    """The one per-instance numeric field beyond ``amount`` that no
    vocabulary can express (OBS_SCHEMA.md §3.6). Keyed on the power's id
    EXPLICITLY, never duck-typed off an attribute name — a duck-typed
    ``getattr(pw, "damage", 0)`` would silently misread any unrelated power
    that happens to define a same-named attribute.

    **Admissibility (fix-pass correction, 2026-08-02):** the original sweep
    here was scoped to ``PowerInstanceType.INSTANCED*`` classes, on the
    theory that those are "the only ones that can ever produce more than one
    row for the same id". That theory does not establish the scope: ``aux``
    is a per-ROW field, populated once per instance regardless of how many
    rows the id ends up with, so a power that only ever has ONE instance can
    still need an ``aux`` the moment it carries per-instance numeric state
    the ``(id, amount)`` pair alone can't express. The actual test — the
    same one ``relic_obs.py`` already applies to relics — is **the game's
    own display path**: a C# power's ``PowerModel.DisplayAmount`` override is
    that path for powers, exactly as ``RelicModel.ShowCounter`` /
    ``DisplayAmount`` is for relics. Twelve C# powers override
    ``DisplayAmount``; four are ported, and none of the four are INSTANCED —
    they are admitted below for that reason, not because they can multi-row.

    Grepping ``sts2_rl/powers.py`` for every ``PowerInstanceType.INSTANCED*``
    class found SIX with a per-instance numeric field beyond ``amount``, not
    just The Bomb:

    =====================  ======  =========================================
    power id                side    field (what it tracks)
    =====================  ======  =========================================
    the_bomb                player  damage   — this fuse's own blast damage
    toric_toughness         player  block    — this fuse's own block-on-clear
    automation              player  cards_left — countdown to the next tick
    panache                 player  cards_left — countdown to the next tick
    thievery                enemy   gold_stolen — running total THIS instance stole
    withering_presence      enemy   _cards_left — countdown to the next Wither
    =====================  ======  =========================================

    (``rolling_boulder`` is INSTANCED too, but its growing value IS
    ``amount`` — ``PowerCmd.modify_amount`` bumps it directly — so it needs no
    ``aux``. ``swipe``'s ``stolen_card`` and ``strangle``'s ``_amounts`` are
    also per-instance state beyond ``amount``, but neither is a NUMBER — a
    card reference and a transient dict aren't encodable as one float, so
    they are out of scope for this field; a future R3-style history block
    would be the right place for card-identity state like ``stolen_card``.)

    Four more, found by grepping the C# ``DisplayAmount`` overrides directly
    rather than the INSTANCED subset (verified against
    ``Slay the Spire 2/src/Core/Models/Powers/*.cs``, not taken on faith):

    =====================  ======  =========================================
    power id                side    displayed value (DisplayAmount)
    =====================  ======  =========================================
    hardened_shell          either  max(0, Amount − damageReceivedThisTurn)
                                     — the REMAINING absorb cap, never the raw
                                     damage-received counter
                                     (HardenedShellPower.cs:25)
    sloth                   either  _cardsPlayedThisTurn (SlothPower.cs:20)
    tender                  either  CardsPlayedThisTurn (TenderPower.cs:22)
    slow                    either  SlowAmount * 10 (SlowPower.cs:22,26-30)
    =====================  ======  =========================================

    Two scales, chosen by what kind of quantity the field is:
      - HP-like/currency-like quantities (blast damage, block, gold,
        hardened_shell's remaining cap) share this module's ABS_SCALE (/100)
        — the same unit every other HP/block/damage number here uses.
      - Small countdown/per-turn-count counters (bounded by their own
        CARDS_PER_TRIGGER or initial ``amount``, typically single digits)
        share a /10.0 scale — the same denominator already used for a
        relic's counter and a card's affliction amount — rather than
        ABS_SCALE, which would compress them into the bottom few percent of
        [0, 1] for no benefit. sloth and tender's displayed
        cards-played-this-turn counts land here.
      - slow is the interesting case: its C# ``DisplayAmount`` is already
        ``raw_counter * 10``, and this module's ABS_SCALE is 100 — so
        publishing ``displayed / ABS_SCALE`` and publishing
        ``raw_counter / 10.0`` are the exact same float, not two competing
        choices. It is implemented as ``_cards_this_turn / 10.0`` below,
        which is that shared value.
    """
    pid = pw.id
    if pid == "the_bomb":
        return _clip01(pw.damage / ABS_SCALE)
    if pid == "toric_toughness":
        return _clip01(pw.block / ABS_SCALE)
    if pid == "thievery":
        return _clip01(pw.gold_stolen / ABS_SCALE)
    if pid == "withering_presence":
        return _clip01(pw._cards_left / 10.0)
    if pid == "automation" or pid == "panache":
        return _clip01(pw.cards_left / 10.0)
    if pid == "hardened_shell":
        return _clip01(max(0, pw.amount - pw._damage_received_this_turn) / ABS_SCALE)
    if pid == "sloth" or pid == "tender":
        return _clip01(pw._cards_played_this_turn / 10.0)
    if pid == "slow":
        return _clip01(pw._cards_this_turn / 10.0)
    return 0.0


def _power_rows(creature) -> list[tuple[list[int], list[float]]]:
    """Every power INSTANCE on ``creature``, oldest-first — C#'s application
    order (``creatures.PowerList.values()``, phase 0). One row per INSTANCE,
    not per id: two ``the_bomb`` fuses are two rows with two different
    ``aux`` values, which is the entire reason phase 0 changed
    ``creature.powers`` from a dict to an ordered instance list."""
    return [
        ([oid(POWER_INDEX.get(pw.id))],
         [_signed(pw.amount, 10), _signed(pw.amount, 50), _power_aux(pw)])
        for pw in creature.powers.values()
    ]


def _relic_rows(state: CombatState) -> list[tuple[list[int], list[float]]]:
    """Every relic the player holds, in acquisition order (``state.relics`` —
    what the relic bar shows). The two aux floats are entirely
    ``relic_obs.relic_row``'s — every admissibility rule (displayed value,
    the in-combat-only gates, the clamp) already lives there; this only
    divides the returned counter by 10 (OBS_SCHEMA.md §5.2)."""
    rows = []
    for relic in state.relics:
        counter, flag = relic_row(relic, in_combat=True)
        rows.append(([oid(RELIC_INDEX.get(relic.id))], [counter / 10.0, float(flag)]))
    return rows


def _affliction_id_int(card: Card) -> int:
    aff = card.affliction
    return PAD if aff is None else oid(AFFLICTION_INDEX.get(aff.id))


def _enchantment_id_int(card: Card) -> int:
    ench = card.enchantment
    return PAD if ench is None else oid(ENCHANTMENT_INDEX.get(ench.id))


def card_features(state: CombatState, card: Card | None) -> list[float]:
    """31 floats: the original 24 engineered card features (fields 0..23,
    UNCHANGED — do not re-tune), 5 R2 per-instance fields (OBS_SCHEMA.md
    §3.4), and 2 v14 fields (§5.2: glow_gold, block_preview_move) no
    vocabulary can express."""
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
    f[CARD_UPGRADE_FEATURE] = _clip01(card.upgrade_level / 5.0)
    # Base numbers (upgrade-adjusted; dynamic cards like Body Slam /
    # Perfected Strike report their current computed base).
    base_dmg = card_base_damage(s, card, None)
    if base_dmg is not None:
        f[17], f[18] = _abs2(base_dmg)
    f[19] = _clip01(card.base_hits / 10.0)
    base_blk = card_base_block(s, card)
    if base_blk is not None:
        f[20] = _clip01(base_blk / ABS_SCALE)
        # Obs-parity fix (89U diff, field offset 21): the game's own
        # DecisionDumper (SpireBot's CombatObsWriter.cs:470) captures this
        # field via `Hook.ModifyBlock(..., default, card, null, ...)` —
        # `default(ValueProp)` carries no `.Move` flag, so every block
        # modifier gated on `IsPoweredCardOrMonsterMoveBlock()` (Dexterity,
        # Frail, ...) is a no-op there. Passing `ValueProp.NONE` mirrors
        # that exactly — see `preview_card_block`'s docstring. Do NOT
        # "fix" this to `ValueProp.MOVE`; that reintroduces the 224-mismatch
        # regression this fix closed.
        eff_block = preview_card_block(s, card, props=ValueProp.NONE)
        f[21] = _clip01(eff_block / ABS_SCALE)
    f[22] = _clip01(card.base_hp_loss / ABS_SCALE)
    magic = card.magic_number
    f[23] = _clip01(magic / 20.0) if magic is not None else 0.0
    # ── R2 fields (OBS_SCHEMA.md §3.4) ────────────────────────────────
    f[24] = _clip01(card.affliction.amount / 10.0) if card.affliction is not None else 0.0
    f[25] = 1.0 if card.exhaust_on_next_play else 0.0
    # Read the game-mirroring properties, not the raw single-turn flags —
    # C#'s ShouldRetainThisTurn/IsSlyThisTurn (CardModel.cs:590-629, ported
    # 1:1 as `should_retain_this_turn`/`is_sly_this_turn`) are the KEYWORD
    # "or" the single-turn grant, so a permanently-Retain card (Luminesce)
    # must read 1 here.
    f[26] = 1.0 if card.should_retain_this_turn else 0.0
    f[27] = 1.0 if card.is_sly_this_turn else 0.0
    f[28] = _clip01(card.base_replay_count / 3.0)
    # ── v14 fields (schema 8; OBS_SCHEMA.md §5.2) ─────────────────────
    # f[29]: the game's gold-glow "condition armed" signal
    # (CardModel.ShouldGlowGold) — the ONLY obs carrier for on_play-only
    # conditions like Pact's End; the parity-pinned damage/block fields
    # deliberately keep the card-face printed numbers.
    f[29] = 1.0 if card.should_glow_gold(s._ctx()) else 0.0
    # f[30]: the true block this card grants right now — the full MOVE
    # pipeline (Dexterity, Frail, enchantments, Fasten), unlike f[21]'s
    # ValueProp.NONE parity field.
    mv_block = preview_card_block(s, card, props=ValueProp.MOVE)
    f[30] = _clip01(mv_block / ABS_SCALE) if mv_block is not None else 0.0
    return f


def _hand_rows(state: CombatState, card_obs: str) -> list[tuple[list[int], list[float]]]:
    """POSITIONAL: row h IS hand slot h (the play-action grid depends on
    this). Empty slots are explicit PAD rows, never skipped.

    Builds ``max(MAX_HAND, len(hand))`` rows, not exactly ``MAX_HAND`` — a
    hand at or under cap gets exactly the same rows as before (this is a
    no-op change in the common case), but a hand that somehow exceeds
    ``MAX_HAND`` now hands ``write_rows`` a genuinely over-cap sequence, so
    ``hand.overflow`` can actually fire (OBS_SCHEMA.md §2.3) instead of being
    structurally dead. ``write_rows`` still does the real truncation/warning
    and keeps the positional prefix — this only stops pre-truncating before
    the caller ever sees the true count."""
    hand = state.player.hand
    rows = []
    for h in range(max(MAX_HAND, len(hand))):
        if h < len(hand):
            card = hand[h]
            card_id = PAD if card_obs == "features" else oid(CARD_INDEX.get(card.id))
            ints = [card_id, _affliction_id_int(card), _enchantment_id_int(card)]
            floats = card_features(state, card)
        else:
            ints = [PAD, PAD, PAD]
            floats = [0.0] * N_CARD_FEATURES
        rows.append((ints, floats))
    return rows


def _enemy_floats(state: CombatState, e) -> list[float]:
    """One living enemy's 25-float scalar row. Fields 0-23 are UNCHANGED
    from v3 — only the identity one-hot and power vocabulary moved out of
    this row. Field 24 (status_count) is NEW in v5 (OBS_SCHEMA_VERSION's
    comment). Gone/absent enemies are handled by the caller (an all-zero
    row)."""
    f = [0.0] * _N_ENEMY_SCALARS
    f[0] = 1.0
    f[1] = _clip01(e.hp / max(1, e.max_hp))
    f[2], f[3] = _abs2(e.hp)
    f[4], f[5] = _abs2(e.max_hp)
    f[6], f[7] = _abs2(e.block)
    f[8] = _signed(e.strength, 30)

    intent = e.current_intent
    fb = 9
    if intent.has(MoveType.ATTACK):
        f[fb] = 1.0
    if intent.has(MoveType.DEFEND):
        f[fb + 1] = 1.0
    if intent.has(MoveType.BUFF):
        f[fb + 2] = 1.0
    if (intent.has(MoveType.DEBUFF) or intent.has(MoveType.DEBUFF_STRONG)
            or intent.has(MoveType.CARD_DEBUFF)):
        f[fb + 3] = 1.0
    if intent.has(MoveType.STATUS_CARD):
        f[fb + 4] = 1.0
    if intent.has(MoveType.SUMMON):
        f[fb + 5] = 1.0
    if intent.has(MoveType.ESCAPE):
        f[fb + 6] = 1.0
    if intent.has(MoveType.HEAL):
        f[fb + 7] = 1.0
    if intent.has(MoveType.STUN) or intent.has(MoveType.SLEEP) or e.stunned:
        f[fb + 8] = 1.0

    # Telegraphed attack through the full modifier pipeline (what the game
    # displays — see AttackIntent.GetSingleDamage), plus a post-block preview
    # against the player's current block.
    preview = preview_incoming_damage(state, e)
    if preview is not None:
        pb = 18
        f[pb] = _clip01(preview.per_hit / ABS_SCALE)
        f[pb + 1] = _clip01(preview.hits / 10.0)
        f[pb + 2], f[pb + 3] = _abs2(preview.total)
        f[pb + 4], f[pb + 5] = _abs2(preview.post_block)

    # StatusIntent's card count — the only OTHER IntentType besides Attack
    # whose icon carries a number (NIntent.cs:133-136; StatusIntent.cs's
    # FORMAT_STATUS_CARD_COUNT labels it with CardCount). Same /10.0 bucket
    # as the `hits` field above: the C# source's `new StatusIntent(N)` call
    # sites range 1..10 (SlimedBerserker.cs's VOMIT_ICHOR_MOVE is the max).
    # `Intent.status_count` mirrors that C# CardCount, but as of
    # monster/_intent_count_lost only 5 of the sim's 18 StatusIntent
    # construction sites populate it (sts2_rl/monsters/base.py's `Intent`
    # docstring) — the other 13 leave it None, and this correctly reads 0.0
    # for them rather than fabricating a number the sim was never told,
    # pending that separate, already-tracked port gap.
    if intent.has(MoveType.STATUS_CARD) and intent.status_count is not None:
        f[24] = _clip01(intent.status_count / 10.0)
    return f


def _enemies_rows(state: CombatState) -> list[tuple[list[int], list[float]]]:
    """POSITIONAL: row e IS enemy slot e (the play-action grid and
    damage_matrix depend on this). A gone/absent enemy is an explicit PAD
    row, never skipped — see OBS_SCHEMA.md §3.3's alignment warning.

    Builds ``max(MAX_ENEMIES, len(enemies))`` rows (see ``_hand_rows``'s
    docstring for why) — a spammy-summon encounter that actually exceeds
    ``MAX_ENEMIES`` (the module docstring already documents these as
    unreachable by targeting) now sets ``enemies.overflow`` instead of
    silently hiding the extra creatures with the flag stuck at 0.0."""
    enemies = state.enemies
    rows = []
    for e_i in range(max(MAX_ENEMIES, len(enemies))):
        e = enemies[e_i] if e_i < len(enemies) else None
        if e is None or e.is_gone:
            rows.append(([PAD], [0.0] * _N_ENEMY_SCALARS))
        else:
            idx = MONSTER_INDEX.get(e.__class__.__name__)
            rows.append(([oid(idx)], _enemy_floats(state, e)))
    return rows


def _enemy_power_rows(state: CombatState, e_i: int) -> list[tuple[list[int], list[float]]]:
    """Power instance rows for enemy slot ``e_i`` — positional in the SLOT
    (one segment per enemy, ``enemy{e}.powers``), ``sort=False`` within it
    (C#'s application order), same as ``_power_rows``."""
    enemies = state.enemies
    e = enemies[e_i] if e_i < len(enemies) else None
    if e is None or e.is_gone:
        return []
    return _power_rows(e)


def _enemy_intent_history_floats(state: CombatState, e_i: int) -> list[float]:
    """R3: the ``MAX_INTENT_HISTORY * _N_ENEMY_HISTORY_SCALARS``-float
    history block for enemy slot ``e_i``, most-recent-first.

    Looked up by the creature CURRENTLY occupying slot ``e_i``'s ``net_id``
    — never by list position — so the three encounters that reorder a live
    enemy's slot mid-combat (``ovicopter_normal``, ``fabricator_normal``,
    ``living_fog_normal``) can't hand one creature's history to another: the
    dict is keyed by net_id, and this function re-resolves ``net_id`` from
    ``state.enemies[e_i]`` fresh on every call.

    A gone/absent slot (no creature, or ``is_gone``) reads fully unrecorded
    — every slot's `recorded` float 0.0 — matching how ``_enemies_rows``
    already blanks that row's CURRENT fields; a creature that once occupied
    this slot but is gone now has no business appearing in the observation
    at all, current or historical. A living creature with fewer than
    ``MAX_INTENT_HISTORY`` prior turns (freshly summoned, or still early in
    the combat) gets unrecorded PAD in its remaining slots — never
    fabricated zeros passed off as a real turn."""
    width = MAX_INTENT_HISTORY * _N_ENEMY_HISTORY_SCALARS
    enemies = state.enemies
    e = enemies[e_i] if e_i < len(enemies) else None
    if e is None or e.is_gone or e.net_id is None:
        return [0.0] * width
    entries = state._intent_history.get(e.net_id, ())
    out: list[float] = []
    for slot in range(MAX_INTENT_HISTORY):
        if slot < len(entries):
            entry = entries[slot]
            atk, defend, buff, deb, status_card, summon, escape, heal, stun = entry.flags
            row = [
                1.0,  # recorded
                1.0 if atk else 0.0,
                1.0 if defend else 0.0,
                1.0 if buff else 0.0,
                1.0 if deb else 0.0,
                1.0 if status_card else 0.0,
                1.0 if summon else 0.0,
                1.0 if escape else 0.0,
                1.0 if heal else 0.0,
                1.0 if stun else 0.0,
                _clip01(entry.per_hit / ABS_SCALE) if entry.per_hit is not None else 0.0,
                _clip01(entry.hits / 10.0) if entry.hits is not None else 0.0,
            ]
            row += list(_abs2(entry.total)) if entry.total is not None else [0.0, 0.0]
            row.append(
                _clip01(entry.status_count / 10.0)
                if entry.status_count is not None else 0.0
            )
        else:
            row = [0.0] * _N_ENEMY_HISTORY_SCALARS
        out.extend(row)
    return out


def _potions_rows(state: CombatState) -> list[tuple[list[int], list[float]]]:
    """POSITIONAL: row p IS potion slot p (the potion-action grid depends on
    this). An empty slot is an explicit PAD row, never skipped.

    Builds ``max(MAX_POTION_ROWS, len(potions))`` rows (see ``_hand_rows``'s
    docstring for why) — a belt grown past ``MAX_POTION_ROWS`` now sets
    ``potions.overflow`` instead of silently hiding the extra slot with the
    flag stuck at 0.0."""
    potions = state.player.potions
    rows = []
    for p_i in range(max(MAX_POTION_ROWS, len(potions))):
        potion = potions[p_i] if p_i < len(potions) else None
        if potion is None:
            rows.append(([PAD], [0.0]))
        else:
            rows.append(([oid(POTION_INDEX.get(potion.id))],
                         [1.0 if potion.targeted else 0.0]))
    return rows


def card_instance_row(
    card: Card, pile_id: int, effective_cost: float,
) -> tuple[list[int], list[float]]:
    """The shared R2 card-instance row (OBS_SCHEMA.md §5.1/§5.2):
    `(pile_id, card_id, affliction_id, enchantment_id)` ints,
    `(upgrade, effective_cost, affliction_amount, exhaust_on_next_play)`
    floats. Used for EVERY card-instance row in both envs — combat piles
    (`_pile_card_row`, below) and every run-side block with no live
    `CombatState` (deck, reward cards, select candidates —
    `run_env._run_card_row`).

    `effective_cost` is an explicit PARAMETER rather than computed here:
    this function only shapes the row, it never decides how the cost field
    is produced. Each caller passes whatever value matches what the game
    itself would show for that row (OBS_SCHEMA.md §2.3). `hand.f` rows
    (built via `card_features`, not this function) pass a hook-modified
    cost from `previews.preview_card_energy_cost` (runs the card through
    `state.hooks`/`state.player.energy`), since the game's own preview
    pipeline does the same for cards actually in `Hand`. Every row built
    through THIS function passes the card's plain printed `energy_cost`
    instead: combat pile cards (`_pile_card_row`, below — v7 REDEFINE,
    draw/discard/exhaust are not in `Hand` so the game never hook-modifies
    their cost) and every out-of-combat row with no live `CombatState`
    (`run_env._run_card_row` — deck, reward cards, select candidates —
    which is also what the game's own out-of-combat screens show).
    Splitting the row shape from cost computation this way means the two
    callers share ONE encoder rather than hand-keeping two copies of the row
    shape that have to agree by construction.
    """
    ints = [pile_id, oid(CARD_INDEX.get(card.id)), _affliction_id_int(card), _enchantment_id_int(card)]
    floats = [
        _clip01(card.upgrade_level / 5.0),
        _clip01(effective_cost / 6.0),
        _clip01(card.affliction.amount / 10.0) if card.affliction is not None else 0.0,
        1.0 if card.exhaust_on_next_play else 0.0,
    ]
    return ints, floats


def _pile_card_row(state: CombatState, card: Card, pile_id: int) -> tuple[list[int], list[float]]:
    """v7 (SpireBot schema audit, REDEFINE): draw/discard/exhaust pile cards
    are not in ``Hand``, so the game's own preview pipeline never hook-
    modifies their cost — the game-readable proxy is the card's plain
    printed ``energy_cost``, same as ``run_env._run_card_row`` already uses
    for out-of-combat card rows (deck/reward/select-candidates), and
    unlike ``hand.f``'s ``effective_cost`` (still hook-modified via
    ``preview_card_energy_cost`` — cards actually in hand ARE covered by
    the game's preview pipeline). This must be
    ``canonical_energy_cost`` (the printed cost, immune to every live
    modifier), not ``energy_cost`` (which still applies
    ``_free_this_turn``/``_cost_this_turn``/``_cost_this_combat``/
    ``_cost_delta_this_turn`` even for cards outside hand) — a whole-combat
    discount granted while a card was in hand otherwise leaks into this
    view after the card moves to a pile, where the game's own
    ``EnergyCost.Canonical`` proxy never reflected it at all."""
    return card_instance_row(card, pile_id, card.canonical_energy_cost)


def _cards_rows(state: CombatState) -> list[tuple[list[int], list[float]]]:
    """The unordered draw+discard+exhaust multiset (OBS_SCHEMA.md §5.3): the
    hidden-information rule the sort in ``write_rows(..., sort=True)``
    enforces. Card identity is ALWAYS carried here regardless of
    ``card_obs`` — see the module docstring's ``card_obs`` note."""
    p = state.player
    rows = []
    for pile_id, pile in ((1, p.draw_pile), (2, p.discard_pile), (3, p.exhaust_pile)):
        for card in pile:
            rows.append(_pile_card_row(state, card, pile_id))
    return rows


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


def write_combat_obs(
    state: CombatState, buf: ObsBuffer, card_obs: str = "hybrid", *, prefix: str = "",
) -> None:
    """Write the combat observation into ``buf``, a buffer the CALLER owns.

    Segments are addressed as ``prefix + name`` — so the run env (T5) can
    build one ``ObsLayout`` whose combat half is
    ``combat_obs_segments_*()`` with every name prefixed ``"combat."``,
    allocate one ``ObsBuffer`` for the whole run observation, and call
    ``write_combat_obs(combat, buf, prefix="combat.")``.

    Does NOT call ``buf.reset()`` (the caller owns that) and must not assume
    the buffer holds only combat segments — every write below goes through
    ``buf.write_rows`` (row blocks) or an explicit ``layout.f_slices[...]``
    lookup (scalars), never a raw offset into the whole array. Because the
    caller resets the buffer first, every segment here starts zeroed, so
    this function never needs to clear a tail (OBS_SCHEMA.md §2.1/§2.3).
    """
    _check_card_obs(card_obs)
    s = state
    p = s.player
    L = buf.layout

    def F(name: str) -> slice:
        return L.f_slices[prefix + name]

    # ── Player vitals (segment names/encodings UNCHANGED from v3) ────────
    buf.f[F("player.hp_ratio")] = _clip01(p.hp / max(1, p.max_hp))
    buf.f[F("player.hp_abs")] = _abs2(p.hp)
    buf.f[F("player.max_hp_abs")] = _abs2(p.max_hp)
    buf.f[F("player.block_abs")] = _abs2(p.block)
    buf.f[F("player.energy")] = _clip01(p.energy / 10.0)
    buf.f[F("player.strength")] = _signed(p.strength, 30)
    buf.f[F("player.dexterity")] = _signed(_power_amt(p, "dexterity"), 30)
    buf.f[F("player.pile_sizes")] = [
        _clip01(len(p.hand) / MAX_HAND),
        _clip01(len(p.draw_pile) / 40.0),
        _clip01(len(p.discard_pile) / 40.0),
        _clip01(len(p.exhaust_pile) / 40.0),
    ]
    buf.f[F("player.turn")] = _clip01(s.turn / 30.0)
    buf.f[F("player.incoming_post_block")] = _abs2(preview_total_incoming(s))
    # History scalars the deck can condition on (Stomp, Spite, ...).
    cards_this_turn = sum(1 for _ in s.history.of_type(CardPlayedEntry, this_turn=True))
    dmg_taken = sum(
        e.amount
        for e in s.history.of_type(DamageReceivedEntry, this_turn=True)
        if e.target is p
    )
    buf.f[F("player.cards_played_this_turn")] = _clip01(cards_this_turn / 10.0)
    buf.f[F("player.attacks_this_turn")] = _clip01(s.history.attack_plays_this_turn() / 10.0)
    buf.f[F("player.damage_taken")] = _abs2(dmg_taken)

    # ── Entity-row blocks — each returns whether it truncated (overflow) ──
    overflow: dict[str, bool] = {}

    overflow["player.powers"] = buf.write_rows(
        prefix + "player.powers", _power_rows(p),
        cap=MAX_POWERS_PLAYER, n_int=1, n_float=3, sort=False)

    overflow["player.relics"] = buf.write_rows(
        prefix + "player.relics", _relic_rows(s),
        cap=MAX_RELIC_ROWS, n_int=1, n_float=2, sort=False)

    overflow["hand"] = buf.write_rows(
        prefix + "hand", _hand_rows(s, card_obs),
        cap=MAX_HAND, n_int=3, n_float=N_CARD_FEATURES, sort=False)

    overflow["enemies"] = buf.write_rows(
        prefix + "enemies", _enemies_rows(s),
        cap=MAX_ENEMIES, n_int=1, n_float=_N_ENEMY_SCALARS, sort=False)

    for e_i in range(MAX_ENEMIES):
        name = f"enemy{e_i}.powers"
        overflow[name] = buf.write_rows(
            prefix + name, _enemy_power_rows(s, e_i),
            cap=MAX_POWERS_ENEMY, n_int=1, n_float=3, sort=False)

    # R3: direct slice writes, not write_rows — fixed-width, no ids, and
    # cannot overflow by construction (see the segment-registration comment
    # in combat_obs_segments_f).
    for e_i in range(MAX_ENEMIES):
        buf.f[F(f"enemy{e_i}.intent_history.f")] = (
            _enemy_intent_history_floats(s, e_i))

    # ── Effective damage matrix (aligned 1:1 with play(h, e) actions) ─────
    _write_damage_matrix(s, buf.f, F("damage_matrix").start)

    overflow["potions"] = buf.write_rows(
        prefix + "potions", _potions_rows(s),
        cap=MAX_POTION_ROWS, n_int=1, n_float=1, sort=False)

    # The ONLY sorted block — pile order is hidden information (OBS_SCHEMA.md
    # §5.3); sort=True makes the block a pure function of the multiset.
    overflow["cards"] = buf.write_rows(
        prefix + "cards", _cards_rows(s),
        cap=MAX_COMBAT_CARDS, n_int=4, n_float=4, sort=True)

    # ── Overflow flags: 1.0 iff truncated, else the reset()-left 0.0 ──────
    for name, truncated in overflow.items():
        if truncated:
            buf.f[F(f"{name}.overflow")] = 1.0


def build_combat_obs(state: CombatState, card_obs: str = "hybrid") -> dict[str, np.ndarray]:
    """The full v4 combat observation for a standalone ``CombatState``:
    allocate an ``ObsBuffer`` for ``combat_obs_layout(card_obs)``, reset it,
    ``write_combat_obs`` into it, and return COPIES — ``{"f": ..., "i":
    ...}``. Copies, not views: a caller holding onto a returned observation
    (a rollout buffer entry) must never see it silently mutate on the next
    call."""
    layout = combat_obs_layout(card_obs)
    buf = ObsBuffer(layout)
    buf.reset()
    write_combat_obs(state, buf, card_obs)
    return {"f": buf.f.copy(), "i": buf.i.copy()}


def _check_mutually_exclusive(a: object, b: object, message: str) -> None:
    """Raise ``ValueError(message)`` iff both ``a`` and ``b`` are given
    (not ``None``). Factored out of ``STS2FullCombatEnv.__init__`` so the
    guard itself is one small, independently testable/monkeypatchable unit
    rather than an inline conditional buried in a long constructor."""
    if a is not None and b is not None:
        raise ValueError(message)


class STS2FullCombatEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        *,
        encounter: Encounter | None = None,
        encounters: Sequence[Encounter] | None = None,
        deck: Sequence[str] | None = None,
        potions: Sequence[str] | None = None,
        deck_cards: Sequence[Card] | None = None,
        relics: Sequence[Relic] | None = None,
        max_hp: int | None = None,
        current_hp: int | None = None,
        potion_slots: Sequence[str | None] | None = None,
        snapshots: "SnapshotDataset | str | None" = None,
        ascension: int = 0,
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
        _check_card_obs(card_obs)
        _check_mutually_exclusive(deck, deck_cards, "pass either deck or deck_cards, not both")
        _check_mutually_exclusive(potions, potion_slots, "pass either potions or potion_slots, not both")
        if snapshots is not None:
            # A snapshot supplies all six start-state facts itself (Task 2's
            # `build_start_state`) -- every other start-state kwarg (the
            # encounter pool included) would be silently ignored or would
            # silently fight the snapshot for control, so this is a loud
            # ValueError, not a "snapshots wins" precedence rule.
            _conflicting = {
                "encounter": encounter, "encounters": encounters,
                "deck": deck, "potions": potions,
                "deck_cards": deck_cards, "relics": relics,
                "max_hp": max_hp, "current_hp": current_hp,
                "potion_slots": potion_slots,
            }
            _bad = [name for name, value in _conflicting.items() if value is not None]
            if _bad:
                raise ValueError(
                    "snapshots is mutually exclusive with "
                    f"{_bad} -- a snapshot supplies all start-state facts itself"
                )

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
        # `deck_cards` is the full-fidelity alternative to `deck`: real `Card`
        # instances (upgrade level / enchantment / affliction all survive)
        # instead of bare ids. `None` means "use `deck_ids` via `make_card`",
        # exactly like before this kwarg existed — the default path is
        # unchanged. Kept as a TEMPLATE list; `_new_state` deep-copies it
        # fresh every reset (see `_new_state`'s docstring) so one episode's
        # in-combat mutations (an Armaments upgrade, a ticking enchantment)
        # never leak into the next.
        self._deck_cards_template: list[Card] | None = (
            list(deck_cards) if deck_cards is not None else None
        )
        self._potion_ids = list(potions) if potions is not None else []
        # `potion_slots` is the slot-preserving alternative to `potions`:
        # `None` entries are real gaps (belt slot 0 empty, slot 1 filled),
        # not compacted away. `None` (the attribute) means "use
        # `_potion_ids` via `make_potion`", the pre-existing behaviour.
        # A `potion_slots` belt longer than 3 grows the `CombatState`/
        # `PlayerCombatState` belt to match (`_new_state` passes
        # `max_potions=len(potion_slots)`) so nothing beyond slot 3 is
        # silently dropped on rebuild -- but the env's ACTION SPACE stays
        # keyed on MAX_POTIONS=3 by design, so potions in slots 3+ become
        # visible-in-obs but unactionable.
        self._potion_slot_ids: list[str | None] | None = (
            list(potion_slots) if potion_slots is not None else None
        )
        # Relic TEMPLATES: same copy-per-reset contract as `deck_cards` (a
        # relic instance carries a mutable counter — Girya's lift count,
        # etc. — that combat ticks).
        self._relics_template: list[Relic] | None = list(relics) if relics is not None else None
        self._max_hp = max_hp
        self._current_hp = current_hp
        # Snapshot mode: `snapshots` is either an already-loaded
        # `SnapshotDataset` (kept as-is) or a path (str/Path), loaded LAZILY
        # -- not here in `__init__` -- so that constructing the env (as
        # `vec_env.build_env` does, once per worker process) never touches
        # disk; the load happens on the first `reset()`, and only once
        # (`self._snapshot_dataset` caches it). This is what lets the PATH
        # form cross a `SubprocVecEnv` worker boundary: `EnvSpec` carries the
        # path (a plain str, trivially picklable), never a live dataset of
        # `Card`/`Relic` objects.
        self._snapshot_mode = snapshots is not None
        self._snapshot_dataset: SnapshotDataset | None = (
            snapshots if isinstance(snapshots, SnapshotDataset) else None
        )
        self._snapshot_path = None if isinstance(snapshots, SnapshotDataset) else snapshots
        self._card_obs = card_obs
        self._card_selector = card_selector
        # Threaded straight into CombatState(...), which seeds
        # hooks.ascension BEFORE create_monsters — never set hooks.ascension
        # after construction (HP rolls read it at spawn).
        self._ascension = ascension
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
        # Dedicated snapshot RNG (Locked decision 3): reset(seed=s) seeds
        # this SEPARATELY from `self._rng`, as its own `random.Random(s)`
        # instance. In non-snapshot mode nothing ever reads from it, so
        # `self._rng`'s draw sequence -- and therefore every non-snapshot
        # episode's dynamics -- is untouched by this attribute's existence.
        self._snap_rng = random.Random()
        self._steps = 0
        self._encounter_start_hp = 1

        # The v4 layout is static (every dim is a reserved capacity), so the
        # declared space needs no throwaway probe combat to measure it.
        self.observation_space = combat_obs_layout(card_obs).space(MAX_OBS_ID)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _snapshot_dataset_ref(self) -> SnapshotDataset:
        """Lazily loads+caches the path form (a no-op once already a live
        `SnapshotDataset`, or after the first call)."""
        if self._snapshot_dataset is None:
            self._snapshot_dataset = load_snapshots(self._snapshot_path)
        return self._snapshot_dataset

    def _new_state(self, rng: random.Random) -> CombatState:
        if self._snapshot_mode:
            # `build_start_state` calls each Card/Relic's own `.rebuild()`
            # (`make_card`/`make_relic` under the hood), so every field here
            # is already a FRESH, unshared instance -- deep-copying again
            # would be a needless second copy (and the whole point of
            # avoiding it: large datasets, many resets). Two resets landing
            # on the identical `Snapshot` object still get independent
            # engine objects because `build_start_state` is called fresh
            # every time, not because anything here deep-copies its output.
            snap = self._snapshot_dataset_ref().sample(self._snap_rng)
            start = build_start_state(snap)
            deck = start["deck_cards"]
            relics = start["relics"]
            max_hp = start["max_hp"]
            current_hp = start["current_hp"]
            encounter = start["encounter"]
            # `potion_slots` here is raw ids/None (build_start_state's
            # contract matches the `potion_slots` kwarg exactly), so it goes
            # through the same slot-preserving `make_potion` transform the
            # `potion_slots` kwarg path below uses.
            potions: list[Potion | None] | None = [
                make_potion(pid) if pid is not None else None
                for pid in start["potion_slots"]
            ]
            # The snapshot's `potion_slots` tuple length IS the belt size
            # (see the comment above): thread it through as `max_potions`
            # so a >3-slot snapshot belt survives `PlayerCombatState`
            # (player.py:138), which otherwise clips to its 3-slot default.
            max_potions: int | None = len(potions)
        else:
            # Deck: `deck_cards` templates are deep-copied fresh every reset
            # (the same mechanism `RunState.create_combat` uses for its own
            # deck, run.py:1582 — `copy.deepcopy`) so a combat's mutations
            # (upgrades, afflictions, cost deltas) never leak into the next
            # episode's template. The id-based `deck` path is untouched:
            # `make_card` already returns a fresh instance per call.
            if self._deck_cards_template is not None:
                deck = copy.deepcopy(self._deck_cards_template)
            else:
                deck = [make_card(cid) for cid in self._deck_ids]

            # Potions: `potion_slots` builds a fresh list positionally
            # (`None` entries stay `None` = a real belt gap; ids become
            # fresh `Potion` instances), which `CombatState`/
            # `PlayerCombatState` already thread through slot-preserving
            # (player.py:138 indexes by position, it does not compact). The
            # id-based `potions` path is untouched.
            if self._potion_slot_ids is not None:
                potions = [
                    make_potion(pid) if pid is not None else None
                    for pid in self._potion_slot_ids
                ]
                # Same slot-size thread-through as the snapshot branch above:
                # a >3-slot `potion_slots` kwarg must not get clipped back to
                # 3 by `PlayerCombatState`'s default belt size.
                max_potions = len(potions)
            else:
                potions = [make_potion(pid) for pid in self._potion_ids] or None
                # Legacy `potions` kwarg / default path: untouched. No
                # `max_potions` is passed, so `CombatState`/
                # `PlayerCombatState` fall back to their own default (3) --
                # byte-identical to pre-fix behaviour.
                max_potions = None

            # Relics: same deep-copy-per-reset contract as the deck (a relic
            # instance carries mutable per-combat/per-run counters).
            relics = (
                copy.deepcopy(self._relics_template)
                if self._relics_template is not None else None
            )
            max_hp = self._max_hp
            current_hp = self._current_hp
            encounter = rng.choice(self._encounters)

        # The selector goes in at construction so turn-1 selection effects
        # (e.g. Gambling Chip's mulligan) already see it.
        state = CombatState(
            starting_deck=deck, rng=rng, encounter=encounter, potions=potions,
            card_selector=self._card_selector,
            relics=relics, max_hp=max_hp, current_hp=current_hp,
            max_potions=max_potions,
            ascension=self._ascension,
        )
        return state

    # ------------------------------------------------------------------
    # gym interface
    # ------------------------------------------------------------------

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = random.Random(seed)
            # Dedicated, SEPARATE instance -- see Locked decision 3 and the
            # `_snap_rng` attribute comment in `__init__`. Only ever read in
            # snapshot mode, so this line changes zero draws on `self._rng`.
            self._snap_rng = random.Random(seed)
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

    def _build_obs(self) -> dict[str, np.ndarray]:
        return build_combat_obs(self._state, self._card_obs)

    def _card_features(self, card: Card | None) -> list[float]:
        return card_features(self._state, card)

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
    comparable dimension-for-dimension on the same seeds.

    Adapted for the v4 Dict observation: only ``obs["f"]`` is ever ablated —
    ``obs["i"]`` holds ids, which are categorical, not numeric, and zeroing
    one would turn a real entity into a PAD row instead of impoverishing a
    number."""

    def __init__(self, env: STS2FullCombatEnv, indices: np.ndarray | None = None) -> None:
        super().__init__(env)
        if indices is None:
            indices = numeric_obs_indices(env.unwrapped._card_obs)
        self._ablated = np.asarray(indices, dtype=np.int64)

    def observation(self, observation: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        # Copy BOTH halves, not just "f". "f" needs its own copy because it is
        # mutated in place just below; "i" is never mutated here, but handing
        # out a reference the caller could mutate is only safe today because
        # build_combat_obs happens to always return fresh copies (its own
        # docstring's contract) — a future caller that hands this wrapper a
        # VIEW (e.g. a buffer-backed obs from T5's run env) would otherwise
        # let a rollout buffer entry's in-place edit corrupt the source
        # buffer. Copying defensively costs one array copy per step and
        # removes the dependency on that upstream contract entirely.
        f = observation["f"].copy()
        f[self._ablated] = 0.0
        return {"f": f, "i": observation["i"].copy()}

    def action_masks(self) -> np.ndarray:
        return self.env.action_masks()
