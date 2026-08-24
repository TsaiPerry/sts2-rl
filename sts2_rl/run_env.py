"""STS2RunEnv — the full-run Gymnasium environment (a complete game run).

The engine side is `driver.py`'s RunDriver: the whole run written as plain
synchronous code that calls ``ask(DecisionRequest) -> int`` at every decision.
This env runs the driver on a **greenlet**; ``ask`` switches back to the env,
so every decision — map path, Neow/event options, shop purchases, rest
choices, post-combat reward picks, every combat action, and every
mid-resolution card selection (RL.md's "two-phase env") — surfaces as one
masked Gym step, fully on-policy.

Action space (flat Discrete, five blocks): a per-candidate SELECT block
(``_sorted_candidate_order``) plus a potion-belt ceiling sized to its true
worst case (fixing a live crash, not just an undersized cap), plus a v22
out-of-combat DISCARD tail block scored from those same belt rows. Absolute
sizes as built: N_ACTIONS = 253
(N_COMBAT_ACTIONS=121, CHOICE_SLOTS=16, MAX_SELECT_CANDIDATES=96,
MAX_POTION_SLOTS=10, MAX_POTION_SLOTS=10):

  [0 .. N_COMBAT_ACTIONS)         combat block — identical semantics to
                                 STS2FullCombatEnv (end turn / play h@e /
                                 potion p@e), sized for MAX_POTION_SLOTS=10
                                 belts (base 3 + Phial Holster's 1 + Potion
                                 Belt's 2 + Alchemical Coffer's 4, the true
                                 worst case): 61 + 10×6 = 121
  [CHOICE_BASE .. +CHOICE_SLOTS) generic choice slots: the i-th option of the
                                 current MAP / EVENT / SHOP / REST /
                                 REWARD_* / SELECT_OPTION decision (shop slot
                                 12 = leave, reward slot len(cards) = skip …
                                 exactly DecisionRequest.legal_actions()).
                                 During a skippable SELECT_CARDS, slot 0 =
                                 skip.
  [SELECT_BASE .. +MAX_SELECT_CANDIDATES)
                                 select-by-CANDIDATE-INDEX block: action
                                 SELECT_BASE + i answers sorted candidate row
                                 i — ``_sorted_candidate_order(request)[i]``,
                                 the SAME canonical order the observation's
                                 ``select.candidates`` rows are written in
                                 (``ObsBuffer.write_rows(..., sort=True)``),
                                 so a row and the action that picks it always
                                 agree.
  [POTION_BASE .. +MAX_POTION_SLOTS)
                                 out-of-combat belt block: drink the
                                 `PotionUsage.AnyTime` potion in slot p
                                 (NPotionPopup.cs:322-325 leaves the Use
                                 button live on every non-combat screen). It
                                 crosses every phase rather than sitting in
                                 any one decision's option slots, because
                                 that is what "any time" means — and, like
                                 the game's overlay, drinking does NOT answer
                                 the screen underneath: the same decision
                                 comes straight back.
  [DISCARD_BASE .. +MAX_POTION_SLOTS)
                                 out-of-combat DISCARD tail block (v22):
                                 discard the potion in belt slot p —
                                 answered as ``POTION_DISCARD_ACTION_BASE +
                                 slot`` (driver.py) — scored from the SAME
                                 ``run.potions`` entity rows as the belt-POTION
                                 block above, by its own pointer head (see
                                 `models.run_action_layout`).

Observation (OBS_SCHEMA.md; the v7 two-leaf ``{"f": Box(0,1), "i": Box(0,
MAX_OBS_ID)}`` Dict contract — see that document in full before touching
this module): a run block (phase one-hot, vitals, R6 log1p gold, act/floor,
the potion belt as R1-shaped id+float rows, the deck as R2 card-instance
rows, the held relics as R1 relic rows, the act boss's identity, and the
whole act map grid with topology and current position — both visible every
step, as the game shows the player), phase-specific blocks (map slots with
1-ply lookahead — unchanged floats, not converted — event identity+option
slots, shop stock as id+float rows with R6 log1p prices, reward slots as R2
rows, select purpose+candidate rows), then the full combat block of
``full_env.write_combat_obs`` (PAD ids / zero floats outside combat) folded
into the SAME buffer under a ``"combat."`` prefix. Conventions follow
``sts2_rl/obs.py``: stored id = frozen-vocab index + 1 (0 = PAD), named
``(segment, width)`` maps per half (``run_obs_segments_f`` /
``run_obs_segments_i``), row blocks via ``ObsBuffer.write_rows`` (sorted
where — and only where — pile/candidate order would otherwise leak hidden
information; positional with explicit PAD rows everywhere the action space
addresses a slot by index).

Reward (configurable): floor-only by default — ``floor_reward`` per floor
gained plus a terminal ``reward_win`` worth a few floors (the curriculum
env's settings; see its module docstring for why HP shaping is off — the
critic learns "low HP → fewer future floors" from the observation). HP-delta
/ act-progress shaping and an HP-conserved win bonus remain available via
``hp_reward_scale`` / ``act_reward`` / ``win_hp_bonus``, all defaulting to 0.
info carries floor/act/phase and, at episode end, is_success + hp_left.
"""
from __future__ import annotations

import math
import os
import random
import warnings
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

import greenlet
import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .actmap import ACT_MAP_CONFIGS, MapPointType, _MAP_WIDTH
from .cards import Card
from .characters import DEFAULT_CHARACTER
from .deck_stats import final_deck_histogram
from .driver import (
    POTION_ACTION_BASE,
    POTION_DISCARD_ACTION_BASE,
    REST_HEAL,
    REST_SMITH,
    DecisionKind,
    DecisionRequest,
    RunDriver,
    RunResult,
)
from .events import ALL_EVENTS
from .potions import BlockPotion
from .previews import preview_total_incoming
from .full_env import (
    CARD_INDEX,
    COMBAT_POTION_BASE,
    MAX_COMBAT_CARDS,
    MAX_ENEMIES,
    MAX_OBS_ID as _COMBAT_MAX_OBS_ID,
    MAX_POTION_ROWS,
    MAX_RELIC_ROWS,
    MONSTER_INDEX,
    # N_RELICS/RELIC_IDS: not used inside this module (MAX_RELIC_ROWS covers
    # everything the observation needs), but re-exported here on purpose —
    # test/test_vocab.py addresses them as `run_env.RELIC_IDS` /
    # `run_env.N_RELICS`, and an import binds the name in this module's
    # namespace exactly as a local definition would.
    N_RELICS,
    POTION_INDEX,
    RELIC_IDS,
    RELIC_INDEX,
    _abs2,
    _clip01,
    card_instance_row,
    combat_action_count,
    combat_obs_segments_f,
    combat_obs_segments_i,
    write_combat_obs,
)
from .combat import Phase
from .obs import ObsBuffer, ObsLayout, PAD, oid
from .relic_obs import relic_row
from .rooms import RoomType
from .run import RunState
from .vocab import capacity as vocab_capacity, frozen_ids

# Bump whenever the run-observation layout or action layout changes (any
# change invalidates saved run-env models — retrain, or migrate where a
# migration exists).
# v2: capacity-padded frozen vocabularies (vocab.py); dims are reserved
#     capacities so future content additions no longer bump this.
# v3: shop Colorless section (SHOP_CARD_SLOTS 5 -> 7), shifting the
#     relic/potion/removal segments and SHOP decision entry indices.
# v4: run.boss.identity + run.map.grid/meta. v3 checkpoints migrate
#     losslessly via checkpoints.migrate_checkpoint.
# v5: DecisionKind gained REWARD_RELIC, widening PHASES by one.
# v6: action layout only — MAX_POTION_SLOTS-wide out-of-combat belt block.
#     Observation byte-identical to v5; v5 checkpoints migrate losslessly by
#     growing the actor head alone (checkpoints.migrate_checkpoint_actions).
# v7 (OBS_SCHEMA.md, entity-obs-schema phase 1): flat float Box observation
#     replaced by the {"f": Box(0,1), "i": Box(0, MAX_OBS_ID)} Dict contract;
#     every one-hot/multi-hot vocab segment becomes an id row (R1 relic rows,
#     R2 card-instance rows) plus R6 log1p-compressed gold/shop/removal
#     prices. Action layout unchanged in width, but SELECT_CARDS moves from
#     a `2*N_CARDS` (card id, upgraded)-pair block to a
#     `MAX_SELECT_CANDIDATES`-wide candidate-INDEX block (see
#     `_sorted_candidate_order`), and `full_env.MAX_POTION_ROWS` widens 4->10
#     (true worst-case belt: base 3 + Phial Holster 1 + Potion Belt 2 +
#     Alchemical Coffer 4). NO v6->v7 migration exists: Box->Dict is a space
#     TYPE change, not a reshape, so every v6-and-earlier checkpoint needs a
#     full retrain. `checkpoints.migrate_checkpoint` (the v3->v4 path) is
#     unreachable dead code as of v7 but left in place.
# v8 (defect fix, 2026-08-02): this env embeds the combat block verbatim, so
#     `full_env.OBS_SCHEMA_VERSION`'s 4->5 bump (enemy StatusIntent count
#     float) silently widened `f_dim` here too (+6) without this constant
#     moving. No layout code changed; only this constant had drifted. See
#     `test_run_schema_version_matches_declared_dims`
#     (test/test_run_obs_v4.py), which pins (version, f_dim, i_dim).
# v9 (R3, full_env.OBS_SCHEMA_VERSION 5->6): per-enemy intent HISTORY grows
#     `f_dim` by MAX_ENEMIES * MAX_INTENT_HISTORY * _N_ENEMY_HISTORY_SCALARS
#     (6*3*15 = 270), `i_dim` unchanged.
# v10 (SpireBot schema audit, docs/superpowers/specs/
#     2026-08-04-spirebot-schema-audit.md, Task 4): pure version bump, no
#     width change — every run v9 field has either a direct C# read (KEEP),
#     a stated proxy (REDEFINE), or an accumulation rule (ACCUMULATE); the
#     REDEFINE rows (`phase`, `select.purpose.ids`) are documentation-only,
#     describing a future C# ObsBuilder source, not a change to this env.
#     Amendment (Task B, same day): `DecisionKind.REWARD_RELIC` (added at
#     v5) never got a `reward.relic.ids/.f` block — the policy could see
#     THAT a relic offer exists but not WHICH relic. Closed in place (v10
#     was still brand-new/uncommitted) rather than a v11 bump.
#     `reward.relic.f`/`reward.relic.ids` (width 1 each, mirroring
#     `reward.potion`) are the only width change since v9: f_dim/i_dim +1.
# v11: `REWARD_CARD_SLOTS` 3 -> 4 (Lasting Candy's appended Power option was
#     being truncated out of the observation while its action stayed legal).
#     `reward.cards.f`/`.ids` each grow by one 4-wide row (f_dim/i_dim +4).
#     No migration function exists for this bump.
# v12 (task 3, v14 mechanics-exposure): follows full_env.OBS_SCHEMA_VERSION
#     7 -> 8 in lockstep — the run layout embeds the combat hand.f block,
#     which grew by 2 fields (f[29] glow_gold, f[30] block_preview_move;
#     N_CARD_FEATURES 29 -> 31). No migration function exists for this bump.
RUN_OBS_SCHEMA_VERSION = 12

# ── Fixed-size bounds ────────────────────────────────────────────────────
# Potion belt headroom, referenced from full_env.MAX_POTION_ROWS (true
# worst-case belt: base 3 + Phial Holster 1 + Potion Belt 2 + Alchemical
# Coffer 4) rather than a second hardcoded literal — a belt grown past a
# smaller cap once indexed past the end of `action_masks()`'s array
# (IndexError, pinned by test_select_candidate_actions.py::
# test_potion_belt_grown_past_the_old_cap_does_not_crash_action_masks).
# N_COMBAT_ACTIONS/CHOICE_BASE/SELECT_BASE/POTION_BASE/N_ACTIONS all widen
# from this one source.
MAX_POTION_SLOTS = MAX_POTION_ROWS
# Generic choice slots. Must cover every non-combat, non-select decision's
# option count: map rows are ≤7 wide (free travel), shops have 14 entries
# (5 character + 2 Colorless cards, 3 relics, 3 potions, removal) + leave,
# events assert ≤ CHOICE_SLOTS options at mask time.
CHOICE_SLOTS = 16
# Map row width (7-wide grid) — the most travel options free travel allows.
MAP_SLOTS = 7
# Full-map grid (run.map.grid): playable rows 1..MAP_GRID_ROWS × the 7-wide
# grid. Sized to the longest act (Overgrowth/Underdocks, 15 rooms); shorter
# acts leave their top rows zero. The Ancient (row 0) and boss rows live
# outside the grid, exactly as in actmap.StandardMap — run.map.meta flags
# cover standing on them, run.boss.ids names the boss.
MAP_GRID_ROWS = 15
assert MAP_GRID_ROWS == max(c.num_rooms for c in ACT_MAP_CONFIGS.values())
# Per grid node: present, MapPointType one-hot, child-column mask (bit c =
# an edge to column c of the next row; edges to the off-grid boss point are
# omitted — every top-row node has one), and a "current position" bit.
MAP_GRID_NODE = 1 + len(MapPointType) + _MAP_WIDTH + 1
# Shop stock layout (MerchantInventory.all_entries order): 5 character card
# slots followed by the 2 Colorless slots (Uncommon, Rare).
SHOP_CARD_SLOTS = 7
SHOP_RELIC_SLOTS = 3
SHOP_POTION_SLOTS = 3
# Reward screen card choices. A CardRewardGroup always draws
# `CARD_REWARD_COUNT` = 3 (every construction site in the codebase passes 3 or
# takes the default), but Lasting Candy APPENDS one Power option to a
# post-encounter offer on its triggering combats (`cards.extend(added)`,
# relics/lasting_candy.py) — the only writer in the codebase that grows this
# list, and it adds exactly one — so a live screen is 3 or 4 wide.
#
# The cap has to cover 4, not 3, because the count also moves the SKIP action:
# `DecisionRequest.legal_actions` masks `range(len(cards) + 1)` with skip last
# (driver.py), so on a 4-card screen index 3 is the bonus Power and skip moves
# to 4. At cap 3 the extra card was truncated out of the observation while
# staying legal to pick, and a policy that had learned "slot 3 = skip" would
# take an unseen card instead. `test_reward_card_slots_cover_lasting_candy`
# (test/test_run_obs_v4.py) pins the width against the live maximum.
REWARD_CARD_SLOTS = 4

# R2 sizing (OBS_SCHEMA.md §2.3/§4): the act-0 masked-random census measured
# a max deck of 18, which is only a floor (every census in this project is
# act-0 — see OBS_SCHEMA.md §7). Rather than mint a SECOND unverified guess,
# `run.deck` reuses `full_env.MAX_COMBAT_CARDS` (96) — the project's existing
# static argument for "how many cards can plausibly exist in this player's
# combat-adjacent card pool at once" (deck size + in-combat generation,
# OBS_SCHEMA.md §4). Out of combat there is no in-combat generation, so a
# run's deck is, if anything, a narrower quantity than what that block
# already has to cover; reusing it is a deliberately conservative choice
# that avoids a second number that has to independently agree with the first.
MAX_DECK_ROWS = MAX_COMBAT_CARDS

# MAX_SELECT_CANDIDATES = 96, matching MAX_COMBAT_CARDS: the largest
# candidate list a purpose can offer is bounded by "a whole pile" or "the
# whole deck". A static argument, not a measurement (like MAX_RELIC_ROWS
# and MAX_COMBAT_CARDS themselves).
MAX_SELECT_CANDIDATES = MAX_COMBAT_CARDS

# `run.boss.ids` sizing: an EXHAUSTIVE census (not an act-0 floor — every
# boss Encounter in every act module was read directly) found the largest
# `monster_classes` list on any single boss fight is 3
# (`overgrowth.THE_KIN_BOSS`: KinFollower × 2 + KinPriest). DoubleBoss
# (Asc 10, final act) does NOT combine two encounters into one bigger fight —
# it is two SEPARATE sequential boss combats, each with its own
# `monster_classes` list — so the correct cap is the per-encounter max (3),
# not a cross-encounter sum. +1 row of headroom for un-audited future content,
# unlike MAX_RELIC_ROWS/MAX_COMBAT_CARDS this is not a floor that needs a
# generous multiple.
MAX_BOSS_IDS = 4

# ── Action layout ─────────────────────────────────────────────────────────
# Never hardcode these widths — always recompute from the sizing constants
# above so N_COMBAT_ACTIONS/CHOICE_BASE/SELECT_BASE/POTION_BASE/N_ACTIONS
# stay in sync automatically.
N_COMBAT_ACTIONS = combat_action_count(MAX_POTION_SLOTS)
CHOICE_BASE = N_COMBAT_ACTIONS
SELECT_BASE = CHOICE_BASE + CHOICE_SLOTS
# Candidate-INDEX block, MAX_SELECT_CANDIDATES wide — see `_translate`'s
# SELECT_CARDS branch and `_sorted_candidate_order` below.
POTION_BASE = SELECT_BASE + MAX_SELECT_CANDIDATES
# The out-of-combat belt (driver.POTION_ACTION_BASE). Its own block rather
# than extra slots on each decision: an AnyTime potion is usable from every
# screen, and a shop already offers 15 of CHOICE_SLOTS' 16.
DISCARD_BASE = POTION_BASE + MAX_POTION_SLOTS
# v22: throw a belt potion away (driver.POTION_DISCARD_ACTION_BASE). Tail
# append — every pre-v22 action index keeps its position.
N_ACTIONS = DISCARD_BASE + MAX_POTION_SLOTS

# ── Stable vocabularies (frozen append-only + capacity-padded; vocab.py) ──
# RELIC_IDS/RELIC_INDEX/N_RELICS: imported from full_env rather than
# recomputed here so the two modules agree by reference, not by two call
# sites that happen to compute the same thing.

EVENT_IDS: list[str] = frozen_ids("events", ALL_EVENTS)
EVENT_INDEX: dict[str, int] = {eid: i for i, eid in enumerate(EVENT_IDS)}
N_EVENTS = vocab_capacity("events")

# Every select_cards / select_option purpose in the engine (collected from
# the source; unknown future purposes land in the "_unknown" bucket until
# added here — the frozen registry pins each purpose's index once seen).
PURPOSE_IDS: list[str] = frozen_ids("purposes", [
    "bundle", "card_reward", "curse_of_knowledge", "duplicate", "enchant",
    "exhaust", "from_discard", "from_draw", "gambling_chip", "obtain",
    "remove", "to_draw_top", "transform", "upgrade", "_unknown",
    # Non-declinable selection screens (Toolbox.cs:28, ChoicesParadox.cs:46);
    # needs its own purpose since skippability (driver.SKIPPABLE_PURPOSES)
    # is per-screen in the source. Appended, never reordered — frozen registry.
    "choose_a_card",
    # canSkip:true twin — the generator potions' screen
    # (CardSelectCmd.cs:216-261 `FromChooseACardScreen(..., canSkip: true)`).
    "choose_a_card_optional",
    # Kifuda's non-cancelable MinSelect-0 enchant screen (Kifuda.cs:26-29,
    # driver.SKIPPABLE_PURPOSES); "transform_optional" (Claws.cs) still
    # falls into "_unknown" — a known gap.
    "enchant_optional",
])
PURPOSE_INDEX: dict[str, int] = {p: i for i, p in enumerate(PURPOSE_IDS)}
N_PURPOSES = vocab_capacity("purposes")

# Phase vocabulary = DecisionKind in declaration order.
PHASES: list[DecisionKind] = list(DecisionKind)
PHASE_INDEX: dict[DecisionKind, int] = {k: i for i, k in enumerate(PHASES)}
N_PHASES = len(PHASES)

_POINT_TYPES = list(MapPointType)
_N_POINT_TYPES = len(_POINT_TYPES)
_POINT_TYPE_INDEX = {t: i for i, t in enumerate(_POINT_TYPES)}

_N_ACTS = 3   # act-index one-hot width (the game's 3-act run)

# full_env.MAX_OBS_ID is computed over the vocabularies the COMBAT
# observation touches; the run observation additionally touches events and
# purposes directly, so this is computed independently rather than imported.
# Comes out IDENTICAL to full_env.MAX_OBS_ID (640, from cards) because cards
# is the largest capacity in either set.
MAX_OBS_ID = max(
    vocab_capacity(kind) for kind in (
        "cards", "relics", "powers", "monsters", "potions",
        "afflictions", "enchantments", "events", "purposes",
    )
)
# A bare `assert` is a no-op under `python -O`; raise explicitly so a
# vocabulary-capacity divergence between the two constants is never silently
# disarmed.
if MAX_OBS_ID != _COMBAT_MAX_OBS_ID:
    raise AssertionError(
        "run_env.MAX_OBS_ID and full_env.MAX_OBS_ID were expected to agree "
        "(cards dominates both sets) — if this ever fires, a vocabulary "
        "capacity bump made them diverge and every consumer of either constant "
        "needs to be re-audited, not just this assertion relaxed."
    )

# ── R6 (OBS_SCHEMA.md §2.5): log1p compression for genuinely UNBOUNDED
#    scalars — gold and shop/removal prices. ──────────────────────────────


def _log1p_scale(x: float, denom: float) -> float:
    """``clip01(log1p(max(0, x)) / log1p(denom))`` — a compressive scale for
    a quantity with no real upper bound, so two large values stay
    distinguishable instead of both saturating a linear ``/denom`` clip at
    1.0 (the bug this replaces: 1000g and 1500g both read `gold/1000`
    clipped to 1.0; a 500g and 800g card-removal price both read
    `cost/_COST_SCALE` clipped to 1.0). ``denom`` is the value at which the
    encoding reaches 1.0 — mirrors `_abs2`'s ABS_SCALE, just log-compressed
    instead of linear, so a value past `denom` still differs from one
    further past it instead of both pinning to the ceiling."""
    return _clip01(math.log1p(max(0.0, x)) / math.log1p(denom))


# Gold: GOLD_REWARD_RANGES (rewards.py) pays 10-20g/Monster, 35-45g/Elite,
# 100g/Boss, ~42-52g/Treasure — a full 3-act run's total INCOME is a few
# thousand gold, but a normally-shopping player's HELD balance rarely
# exceeds a few hundred. Fine denom 800 (not 300) keeps 300g/500g from
# colliding on the fine channel; coarse denom 8000 keeps the whole hoarding
# range (3000g ~0.89, 5000g ~0.95) short of saturation on either channel.
# Verified by test_gold_realistic_band_resolves_without_plateau.
GOLD_LOG_FINE_DENOM = 800.0
GOLD_LOG_COARSE_DENOM = 8000.0

# Shop/removal prices (shop.py): card slots top out ~150-190g, relic slots
# ~235-320g, potion slots ~50-110g — all bounded. Card removal
# (`75 + 25 x removals_used`, shop.py:419-436) is the one genuinely
# UNBOUNDED quantity, climbing without limit over a removal-heavy run. A
# single shared log1p denom can't fully spread the ~8x item-price ratio
# across [0,1] while also keeping unbounded removal cost resolvable past
# 800g (an inherent log1p tradeoff, not a tuning oversight); 900 is the
# reasoned middle ground (~30% spread on the item-price band, 800g still
# ~0.98 short of saturation), verified by
# test_shop_cost_realistic_band_spreads_more_than_the_old_defect.
SHOP_COST_LOG_DENOM = 900.0


def run_obs_segments_f(card_obs: str = "hybrid") -> list[tuple[str, int]]:
    """The run-only FLOAT half as an ordered (segment name, width) list
    (OBS_SCHEMA.md §2/§5.2's naming convention: a logical block ``name``
    splits into ``f"{name}.f"`` here and ``f"{name}.ids"`` in
    ``run_obs_segments_i``). Does NOT include the combat sub-block —
    ``run_obs_layout`` folds ``full_env.combat_obs_segments_f()`` in under a
    ``"combat."`` prefix."""
    segs: list[tuple[str, int]] = [
        ("phase", N_PHASES),
        ("run.hp_ratio", 1),
        ("run.hp_abs", 2),
        ("run.max_hp_abs", 2),
        ("run.gold", 2),                          # R6: log1p, not clipped
        ("run.act", _N_ACTS),
        ("run.floor", 1),
        ("run.potions.f", MAX_POTION_SLOTS * 2),  # (present, slot_exists)
        ("run.potions.overflow", 1),
        ("run.deck.f", MAX_DECK_ROWS * 4),
        ("run.deck.overflow", 1),
        ("run.relics.f", MAX_RELIC_ROWS * 2),     # (counter/10, flag)
        ("run.relics.overflow", 1),
        # run.boss has no per-instance float — see run_obs_segments_i's
        # comment on why it still gets a (zero-width) ".f" entry.
        ("run.boss.f", MAX_BOSS_IDS * 0),
        ("run.boss.overflow", 1),
    ]
    for m in range(MAP_SLOTS):
        segs.append((f"map{m}", 1 + _N_POINT_TYPES + _N_POINT_TYPES))
    # The whole act map, visible every step like the game's map screen — the
    # map{m} slots above stay the action-aligned 1-ply view of the current
    # MAP decision's options. UNCHANGED floats (OBS_SCHEMA.md §2.2): map
    # point types are a small enum and the grid is topology, not a
    # frozen-vocabulary categorical.
    segs.append(("run.map.grid", MAP_GRID_ROWS * _MAP_WIDTH * MAP_GRID_NODE))
    segs.append(("run.map.meta", 2))   # [at Ancient, at boss] (off-grid rows)
    segs.extend([
        ("event.present", 1),
        ("event.page", 1),
        ("event.options", 2 * CHOICE_SLOTS),
    ])
    segs.append(("shop.cards.f", SHOP_CARD_SLOTS * 4))     # present,cost,gold,sale
    segs.append(("shop.relics.f", SHOP_RELIC_SLOTS * 3))   # present,cost,gold
    segs.append(("shop.potions.f", SHOP_POTION_SLOTS * 3))
    segs.append(("shop.removal", 3))                        # present,cost,gold — R6 cost
    segs.append(("reward.cards.f", REWARD_CARD_SLOTS * 4))
    segs.append(("reward.potion.f", 1))                     # present
    segs.append(("reward.relic.f", 1))                      # present
    segs.extend([
        ("select.count", 1),
        ("select.skippable", 1),
        ("select.candidates.f", MAX_SELECT_CANDIDATES * 4),
        ("select.candidates.overflow", 1),
    ])
    return segs


def run_obs_segments_i(card_obs: str = "hybrid") -> list[tuple[str, int]]:
    """The run-only INT half — see ``run_obs_segments_f``'s docstring."""
    segs: list[tuple[str, int]] = [
        ("run.potions.ids", MAX_POTION_SLOTS * 1),
        ("run.deck.ids", MAX_DECK_ROWS * 4),      # (pile_id=PAD, card_id, affl, ench)
        ("run.relics.ids", MAX_RELIC_ROWS * 1),
        # A LIST-valued block (the boss encounter's monster classes, 1-3 of
        # them) rather than a single scalar id, so — unlike event.ids /
        # select.purpose.ids / reward.potion.ids below — it goes through
        # ObsBuffer.write_rows for the truncate/overflow machinery, which
        # requires a same-cap ".f" sibling to exist even though there is no
        # real per-row float (hence the zero-width ("run.boss.f", 0) entry
        # above rather than a bespoke single-purpose writer).
        ("run.boss.ids", MAX_BOSS_IDS * 1),
        ("event.ids", 1),
        ("shop.cards.ids", SHOP_CARD_SLOTS * 1),
        ("shop.relics.ids", SHOP_RELIC_SLOTS * 1),
        ("shop.potions.ids", SHOP_POTION_SLOTS * 1),
        ("reward.cards.ids", REWARD_CARD_SLOTS * 4),
        ("reward.potion.ids", 1),
        ("reward.relic.ids", 1),
        ("select.purpose.ids", 1),
        ("select.candidates.ids", MAX_SELECT_CANDIDATES * 4),
    ]
    return segs


@lru_cache(maxsize=None)
def run_obs_layout(card_obs: str = "hybrid") -> ObsLayout:
    """The WHOLE run observation's layout: this module's own segments
    followed by every ``full_env.combat_obs_segments_{f,i}()`` name prefixed
    ``"combat."`` — one ``ObsLayout``, one ``ObsBuffer``, exactly as
    ``write_combat_obs``'s own docstring specifies."""
    f_segs = run_obs_segments_f(card_obs) + [
        (f"combat.{name}", width) for name, width in combat_obs_segments_f(card_obs)
    ]
    i_segs = run_obs_segments_i(card_obs) + [
        (f"combat.{name}", width) for name, width in combat_obs_segments_i(card_obs)
    ]
    return ObsLayout(f_segs, i_segs)


@dataclass(frozen=True)
class _MapSlotLayout:
    """The only remaining hand-rolled base/stride pair: the per-decision
    ``map{m}`` 1-ply block is positional but NOT a row block (no id/float
    pairing — see the "unchanged floats" note), so it doesn't go through
    ``write_rows`` and still needs its own offsets."""
    map_base: int
    map_stride: int


@lru_cache(maxsize=None)
def _map_slot_layout(card_obs: str) -> _MapSlotLayout:
    L = run_obs_layout(card_obs)
    return _MapSlotLayout(
        map_base=L.f_slices["map0"].start,
        map_stride=L.f_slices["map1"].start - L.f_slices["map0"].start,
    )


def _map_grid_block(act_map) -> np.ndarray:
    """The static part of ``run.map.grid`` for one act map — present flags,
    node types and edge topology; the per-step current-position bit is
    written by ``_build_obs``. Built once per map object and cached (the map
    only changes at act entry or a Golden Compass regeneration). Rows past
    MAP_GRID_ROWS (a ``column_rooms`` override taller than any real act) are
    clipped."""
    block = np.zeros(MAP_GRID_ROWS * _MAP_WIDTH * MAP_GRID_NODE, dtype=np.float32)
    child_base = 1 + _N_POINT_TYPES
    top = min(MAP_GRID_ROWS, act_map.map_length - 1)
    for row in range(1, top + 1):
        for point in act_map.points_in_row(row):
            nb = ((row - 1) * _MAP_WIDTH + point.col) * MAP_GRID_NODE
            block[nb] = 1.0
            block[nb + 1 + _POINT_TYPE_INDEX[point.point_type]] = 1.0
            for child in point.children:
                # Off-grid children (the boss point) carry no routing info —
                # every top-row node connects to the boss.
                if child.row < act_map.map_length and 0 <= child.col < _MAP_WIDTH:
                    block[nb + child_base + child.col] = 1.0
    return block


# ── R2 card-instance row (run-side) ──────────────────────────────────────


def _run_card_row(card: Card) -> tuple[list[int], list[float]]:
    """The R2 card-instance row (OBS_SCHEMA.md §5.1/§5.2) for run-side
    blocks with no live CombatState: deck, reward cards, select candidates.

    Delegates to ``full_env.card_instance_row`` so both envs share one row
    shape (R2's whole premise). The one real divergence (OBS_SCHEMA.md
    §2.3): out of combat there is no hook pipeline to run cost modifiers
    through (``previews.preview_card_energy_cost`` needs a live
    ``CombatState``), so this passes the plain printed
    ``canonical_energy_cost`` — modifier-immune, matching what the game's
    own out-of-combat screens (deck view, shop, reward) show.

    ``pile_id`` is always PAD (0): there is no pile concept outside combat —
    never invent a new pile id for a run-side block."""
    return card_instance_row(card, PAD, card.canonical_energy_cost)


# ── run.deck overflow diagnostics ────────────────────────────────────────
# `ObsBuffer.write_rows` warns once per (process, segment) when a block
# overflows its cap and then silently truncates, which tells you THAT the
# 96-card `run.deck` cap was blown but not WHICH deck did it. This dumps the
# offending deck's contents alongside that warning so the overflow is
# actually diagnosable. Latched the same way the warning is — once per
# process — so a training loop that overflows every step cannot fill a disk.
DECK_OVERFLOW_LOG_ENV = "STS2_DECK_OVERFLOW_LOG"
DEFAULT_DECK_OVERFLOW_LOG = "deck_overflow.log"
_DECK_OVERFLOW_LOGGED = False


def reset_deck_overflow_latch() -> None:
    """Clear the log-once latch (test-only affordance, mirrors
    ``obs.reset_warned_segments``)."""
    global _DECK_OVERFLOW_LOGGED
    _DECK_OVERFLOW_LOGGED = False


def deck_overflow_log_path() -> str:
    """Where the deck dump goes: ``$STS2_DECK_OVERFLOW_LOG``, else
    ``deck_overflow.log`` in the working directory."""
    return os.environ.get(DECK_OVERFLOW_LOG_ENV) or DEFAULT_DECK_OVERFLOW_LOG


def _log_deck_overflow(run: RunState, deck: list[Card]) -> None:
    """Append the full deck to the overflow log. Once per process.

    Never raises: a diagnostic that can kill a training run is worse than no
    diagnostic, so an unwritable path is reported as a warning and dropped.
    """
    global _DECK_OVERFLOW_LOGGED
    if _DECK_OVERFLOW_LOGGED:
        return
    _DECK_OVERFLOW_LOGGED = True

    path = deck_overflow_log_path()
    lines = [
        f"run.deck overflow: {len(deck)} cards exceeds cap {MAX_DECK_ROWS}",
        f"  seed={getattr(run, 'string_seed', None)!r} "
        f"act_index={getattr(run, 'act_index', None)} "
        f"total_floor={getattr(run, 'total_floor', None)}",
    ]
    for i, card in enumerate(deck):
        affliction = card.affliction.id if card.affliction is not None else None
        enchantment = getattr(card, "enchantment", None)
        lines.append(
            f"  [{i:3d}] {card.id} +{card.upgrade_level}"
            f" cost={card.canonical_energy_cost}"
            f" affliction={affliction!r}"
            f" enchantment={getattr(enchantment, 'id', enchantment)!r}"
            f" in_vocab={card.id in CARD_INDEX}"
        )
    lines.append(
        "  counts: " + ", ".join(
            f"{cid}x{n}" for cid, n in sorted(Counter(c.id for c in deck).items())))
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:      # unwritable path — degrade, never crash
        warnings.warn(f"could not write deck overflow log {path!r}: {exc}",
                      stacklevel=2)


#: A rest visit counts as "high HP" when hp/max_hp is at or above this at
#: the visit's first answer. 0.65 sits above the v14 policy's observed
#: heal/smith crossover (heals dominate <= 0.60, smith dominates >= 0.74),
#: so the eval column isolates exactly the regime the rest-economy gates ask
#: about ("does it upgrade when healthy?").
HIHP_REST_THRESHOLD = 0.65


def _hp_potential(ratio: float, knee: float, low_share: float) -> float:
    """Concave HP potential: `low_share` of the value lives in [0, knee]
    (danger zone — HP is precious), the rest in [knee, 1] (HP is currency
    to spend on elites). Piecewise-linear, phi(0)=0, phi(1)=1."""
    if ratio <= knee:
        return low_share * ratio / knee
    return low_share + (1.0 - low_share) * (ratio - knee) / (1.0 - knee)


#: v21: denominator of the act-local option value — "2 elites + the boss"
#: is the whole act ahead (spec §2). A bigger count caps at 1.0.
POTION_OPTION_V_REF = 3

#: v21 metrics: relics whose effect is potions / belt slots (the files that
#: call run.add_potion / add_potion_slots). Keep in sync by grep, not by id
#: string in game code.
POTION_RELIC_IDS = frozenset({
    "phial_holster", "alchemical_coffer", "potion_belt", "belt_buckle",
    "delicate_frond", "petrified_toad",
})


def elites_ahead(run) -> int:
    """# ELITE map points reachable from ``run.current_point`` through
    ``MapPoint.children`` (transitive, any path, each node once) — the current
    point itself is NOT counted (spec: the hard fight you are in is not
    'ahead'). 0 with no current point (between acts)."""
    point = getattr(run, "current_point", None)
    if point is None:
        return 0
    seen: set[int] = set()
    stack = list(point.children)
    count = 0
    while stack:
        p = stack.pop()
        if id(p) in seen:
            continue
        seen.add(id(p))
        if p.point_type == MapPointType.ELITE:
            count += 1
        stack.extend(p.children)
    return count


def potion_option_value(run) -> float:
    """v(s) in [0, 1]: act-local hard fights still ahead after the current
    room (spec §2) — ELITE nodes ahead plus this act's boss unless standing in
    the boss room — over POTION_OPTION_V_REF, capped at 1. A drink at the act
    boss costs nothing; a whole-act-ahead drink costs the full k."""
    boss_ahead = 0 if getattr(run, "current_room_type", None) == RoomType.BOSS else 1
    return min(1.0, (elites_ahead(run) + boss_ahead) / POTION_OPTION_V_REF)


class STS2RunEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        *,
        acts: list[str] | None = None,
        ascension: int = 0,
        include_neow: bool = True,
        card_obs: str = "hybrid",
        reward_win: float = 3.0,
        reward_loss: float = 0.0,
        win_hp_bonus: float = 0.0,
        hp_reward_scale: float = 0.0,
        hp_potential_scale: float = 0.0,
        hp_potential_knee: float = 0.35,
        hp_potential_low_share: float = 0.7,
        rest_heal_shaping_knee_cap: bool = False,
        floor_reward: float = 1.0,
        act_reward: float = 0.0,
        floor_rewards_by_act: "tuple[float, ...] | None" = None,
        reward_upgrade: float = 0.0,
        reward_remove: float = 0.0,
        reward_elite: float = 0.0,
        reward_elite_attempt: float = 0.0,
        reward_boss: float = 0.0,
        reward_relic: float = 0.0,
        rest_heal_mask_above: float | None = None,
        potion_potential_scale: float = 0.0,
        potion_death_expiry: bool = False,
        potion_death_penalty: float = 0.0,
        energy_waste_penalty: float = 0.0,
        potion_option_value: float = 0.0,
        potion_option_expiry: bool = False,
        boss_hp_loss_penalty: float = 0.0,
        drill_snapshots: str | None = None,
        drill_prob: float = 0.0,
        drill_pools: "dict[str, float] | None" = None,
        drill_encounter_weights: "dict[str, float] | None" = None,
        deck_random_prob: float = 0.0,
        deck_random_cards: tuple[int, int] = (4, 14),
        deck_inject: str | None = None,
        deck_inject_prob: float = 0.0,
        deck_inject_midrun: str | None = None,
        deck_inject_midrun_prob: float = 0.0,
        max_steps: int = 10_000,
        render_mode: str | None = None,
        character: str = DEFAULT_CHARACTER,
        on_combat_start: "Callable[[RunState, Any], None] | None" = None,
    ) -> None:
        super().__init__()
        if card_obs not in ("hybrid", "features"):
            raise ValueError("card_obs must be 'hybrid' or 'features'")
        self._acts = list(acts) if acts is not None else None
        # The character every episode is played as (CharacterModel). Only the
        # RunState changes; the observation/action layout is character-
        # independent, so RUN_OBS_SCHEMA_VERSION is untouched.
        self._character = character
        self._ascension = ascension
        self._include_neow = include_neow
        self._card_obs = card_obs
        self._reward_win = reward_win
        self._reward_loss = reward_loss
        self._win_hp_bonus = win_hp_bonus
        self._hp_reward_scale = hp_reward_scale
        # Concave HP potential shaping. Default OFF (scale 0.0) — see
        # `_hp_potential` for the piecewise-linear curve shape.
        self._hp_potential_scale = hp_potential_scale
        self._hp_potential_knee = hp_potential_knee
        self._hp_potential_low_share = hp_potential_low_share
        # Rest-collapse fix: default OFF. See the step() ΔΦ block for the
        # mechanism.
        self._rest_heal_shaping_knee_cap = bool(rest_heal_shaping_knee_cap)
        self._floor_reward = floor_reward
        self._act_reward = act_reward
        # All default OFF. Accepted wrinkles, by design: an upgraded card
        # taken from a reward counts as +upgrade_level upgrades (it IS
        # acquired power); a transform (remove+add in one step) nets zero
        # removals. `_ep_potions_used` counts only actual drinks — a belt
        # decrease with no matching drink answer (e.g. an event trading a
        # potion away) still moves the ledger but doesn't inflate this count.
        # There is no shop-sell feature in this sim; "sold" means any
        # non-drink belt loss.
        self._floor_rewards_by_act = (
            tuple(floor_rewards_by_act) if floor_rewards_by_act is not None else None
        )
        self._reward_upgrade = reward_upgrade
        self._reward_remove = reward_remove
        self._reward_elite = reward_elite
        # v11.1: +reward_elite_attempt once per elite room ENTERED (first
        # answered combat decision in it), win or lose — reward_elite only
        # pays on the rewards screen, so pathing onto an elite and dying
        # earned nothing toward the pathing choice itself. Kept small vs
        # reward_elite: dying at an elite must stay net-negative (the HP
        # potential prices the death). Default OFF.
        self._reward_elite_attempt = reward_elite_attempt
        # v11: +reward_boss per act boss defeated (an act_index advance; the
        # FINAL boss ends the run without advancing, so the win branch pays
        # its share instead). Default OFF.
        self._reward_boss = reward_boss
        # +reward_relic per relic gained, measured the same way as the
        # deck-length delta above (out-of-combat decisions only). Default OFF.
        self._reward_relic = reward_relic
        # Curriculum mask: above this hp/max_hp ratio at a rest site,
        # REST_HEAL's mask bit is cleared IF at least one other rest action
        # is legal — forces generation of upgrade-path data instead of
        # letting the policy always top off. Default None (off); a mask
        # knob, not a reward term, so it is deliberately NOT stamped into
        # checkpoints (`checkpoints.py`) — see `action_masks` below.
        self._rest_heal_mask_above = rest_heal_mask_above
        # potion_potential_scale * (potions held now - potions held before),
        # off the same belt-count delta tracked below. No terminal term — a
        # potion still on the belt at episode end keeps its +k (that
        # asymmetry against the -k a drink/loss pays IS the
        # hoarding-vs-spending weighing bar); `_ep_potions_expired` just
        # tallies the held count at episode end for visibility, with no
        # reward attached. Default OFF.
        self._potion_potential_scale = potion_potential_scale
        # Never-drink fix: default OFF. See the step() forfeiture block for
        # the mechanism.
        self._potion_death_expiry = bool(potion_death_expiry)
        # v15.1: flat -potion_death_penalty per potion still held at DEATH,
        # on top of the expiry forfeiture. Expiry alone only nets
        # hoard-and-die back to 0, tying it with drink-and-die (+k-k); the
        # flat term breaks the tie so dying while holding is strictly worse
        # than using the potion and dying anyway. Default OFF.
        self._potion_death_penalty = potion_death_penalty
        # v16: flat -energy_waste_penalty per unspent energy point at every
        # player-turn END_TURN (the _count_behavior tally). UNCONDITIONAL —
        # empty-hand turns charge too; that IS the deck-building gradient,
        # and no alternative action exists on those turns. Tiebreaker-sized:
        # must stay well below the HP-shaping value of ~1 HP so passing vs
        # Thorns/Prism/Aeonglass-class punishers stays strictly optimal.
        self._energy_waste_penalty = energy_waste_penalty
        # v21 (spec 2026-08-22-v21-potion-option-value-design): -k * v(s) per
        # DRINK, v = act-local hard fights still ahead (potion_option_value()
        # above) — the opportunity value the drink forgoes; no pickup credit.
        # Default OFF (0.0) = bit-identical env.
        self._potion_option_value = float(potion_option_value)
        # NB: the kwarg shadows the module-level potion_option_value(run) helper
        # inside __init__ — do not call the helper from here.
        # v21: on a LOSS, -k * v(s_death) per potion still held (hoard-and-die
        # priced like drink-and-die). Independent of the v9 potion_death_*
        # flags. Default OFF.
        self._potion_option_expiry = bool(potion_option_expiry)
        # v20 (Task 3b): non-refundable price on damage taken inside a BOSS
        # combat, paid once when the combat resolves (won or lost):
        # -K * (hp_at_entry - hp_at_end) / max_hp. Deliberately NOT
        # potential-based — the hp-potential term's post-boss act-entry heal
        # refunds boss-fight HP loss almost in full, so without this the
        # policy has no gradient toward tighter boss play. Default 0.0 =
        # exactly the old reward function.
        self._boss_hp_loss_penalty = boss_hp_loss_penalty
        # Latch: (id(combat), hp at first decision) of the live boss combat.
        self._boss_hp_latch: "tuple[int, int] | None" = None
        # v20 drill mode: with probability drill_prob an episode starts
        # mid-run at a harvested combat (snapshots.py schema 2) instead of
        # at Neow, sampled by stratified (act, room_type) pools. Loaded and
        # validated at construction — a bad path, schema-1 bank, or an empty
        # named pool must raise here, not mid-training.
        self._drill_prob = drill_prob
        self._drill_pools_cfg = dict(drill_pools) if drill_pools else None
        self._drill_weights = (
            dict(drill_encounter_weights) if drill_encounter_weights else {})
        self._drill_pools: "list[tuple[str, float, list, list[float]]] | None" = None
        if drill_snapshots is not None:
            self._load_drill_snapshots(drill_snapshots)
        elif drill_prob > 0.0:
            raise ValueError(
                "drill_prob > 0 requires drill_snapshots (a schema-2 bank)")
        # Card-exposure domain randomization: with probability
        # deck_random_prob an episode starts with 4..14 extra reward-pool
        # cards appended to the starter deck, so every card gets combat
        # playtime regardless of drafting.
        self._deck_random_prob = deck_random_prob
        self._deck_random_cards = tuple(deck_random_cards)
        # v14: deck-inject packages (mechanics exposure). Loaded once at
        # construction time -- a bad path or unknown card id must raise here,
        # not mid-training on whatever episode first rolls the injection.
        self._deck_inject_prob = deck_inject_prob
        self._deck_inject_packages: list[list[str]] | None = None
        if deck_inject is not None:
            import json
            with open(deck_inject) as fh:
                pkgs = json.load(fh)["packages"]
            from .cards import make_card
            for pkg in pkgs:
                for cid in pkg:
                    make_card(cid)      # KeyError now, not at episode 40k
            self._deck_inject_packages = pkgs
        # v15: mid-run twin of deck_inject -- appended on a floor advance
        # (in step()) instead of at reset time. Same load-once-at-
        # construction validation.
        self._deck_inject_midrun_prob = deck_inject_midrun_prob
        self._deck_inject_midrun_packages: list[list[str]] | None = None
        if deck_inject_midrun is not None:
            import json
            with open(deck_inject_midrun) as fh:
                pkgs = json.load(fh)["packages"]
            from .cards import make_card
            for pkg in pkgs:
                for cid in pkg:
                    make_card(cid)      # KeyError now, not mid-training
            self._deck_inject_midrun_packages = pkgs
        self._max_steps = max_steps
        self.render_mode = render_mode
        # Harvest hook: threaded straight to the `RunDriver` this env
        # constructs per-episode inside `reset()`'s `_drive` closure. The env
        # is the only owner of that construction (the driver runs on a
        # private greenlet `reset()` starts), so a caller outside this
        # module — e.g. `harvest.py` — has no other way to observe
        # `RunDriver.on_combat_start` firing; exposing it here is the
        # smallest seam that doesn't require subclassing or monkeypatching a
        # production object. `None` (the default) means zero behavior
        # change, same as the driver's own
        # default.
        self._on_combat_start = on_combat_start

        self.n_actions = N_ACTIONS
        self.action_space = spaces.Discrete(self.n_actions)

        # The v7 layout is static (every dim is a reserved capacity or a
        # static-argument cap — see MAX_DECK_ROWS/MAX_SELECT_CANDIDATES'
        # own comments), so the declared space needs no throwaway probe
        # combat to measure it (unlike the old flat-Box env, which measured
        # `len(build_combat_obs(probe, card_obs))`).
        self._layout = run_obs_layout(card_obs)
        self._buf = ObsBuffer(self._layout)
        self.observation_space = self._layout.space(MAX_OBS_ID)

        self._rng = random.Random()
        self._run: RunState | None = None
        self._glet: greenlet.greenlet | None = None
        self._request: DecisionRequest | None = None
        self._result: RunResult | None = None
        self._steps = 0
        # (map object, static run.map.grid block) — rebuilt when the run's
        # map is a different object (act entry / Golden Compass).
        self._map_grid_cache: tuple[Any, np.ndarray] | None = None

    # ------------------------------------------------------------------
    # Named layout (pin tests)
    # ------------------------------------------------------------------

    def obs_segments_f(self) -> list[tuple[str, int]]:
        """run_obs_segments_f plus the combat float segments, prefixed."""
        return run_obs_segments_f(self._card_obs) + [
            (f"combat.{name}", w) for name, w in combat_obs_segments_f(self._card_obs)
        ]

    def obs_segments_i(self) -> list[tuple[str, int]]:
        """run_obs_segments_i plus the combat int segments, prefixed."""
        return run_obs_segments_i(self._card_obs) + [
            (f"combat.{name}", w) for name, w in combat_obs_segments_i(self._card_obs)
        ]

    # ------------------------------------------------------------------
    # Greenlet plumbing
    # ------------------------------------------------------------------

    def _kill_driver(self) -> None:
        if self._glet is not None and not self._glet.dead:
            self._glet.throw(greenlet.GreenletExit)
        self._glet = None

    def _deliver(self, request: DecisionRequest) -> int:
        """RunDriver's ask callback — runs INSIDE the driver greenlet: hand
        the request to the env greenlet and park until step() answers."""
        return greenlet.getcurrent().parent.switch(request)

    def _switch(self, value: Any) -> None:
        """Resume the driver greenlet; it returns either the next
        DecisionRequest (parked in _deliver) or the RunResult (finished)."""
        out = self._glet.switch(value)
        if isinstance(out, RunResult):
            self._result = out
            self._request = None
        elif isinstance(out, DecisionRequest):
            self._request = out
        elif self._glet.dead:
            # GreenletExit during teardown lands here; treat as terminal.
            self._request = None
        else:  # pragma: no cover - driver protocol violation
            raise AssertionError(f"unexpected switch value: {out!r}")

    # ------------------------------------------------------------------
    # gym interface
    # ------------------------------------------------------------------

    def _make_run_state(self) -> RunState:
        """Build the RunState the driver plays. Curriculum envs override this
        to install a RunState subclass (e.g. curriculum_env.ColumnRunState)."""
        return RunState(rng=self._rng, character=self._character)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self._kill_driver()
        if seed is not None:
            self._rng = random.Random(seed)
        self._run = self._make_run_state()
        # Deck randomization — BEFORE the driver greenlet starts, so the
        # extra cards exist from the first decision on. The prob > 0.0
        # short-circuit is load-bearing (branch_prob precedent,
        # curriculum_env.py:238-244): the default env must draw no rng here.
        if self._deck_random_prob > 0.0 and self._rng.random() < self._deck_random_prob:
            self._randomize_deck(self._run)
        # v14 deck-inject: same zero-draw short-circuit contract as the
        # deck_random_prob block above -- the default env (packages None or
        # prob 0.0) draws no rng here either.
        if (self._deck_inject_packages is not None
                and self._deck_inject_prob > 0.0
                and self._rng.random() < self._deck_inject_prob):
            self._inject_deck(self._run)
        # v20 drill roll — same zero-draw short-circuit contract as the two
        # blocks above: with drills off (no bank or prob 0.0) this draws NO
        # rng, so the default env's episode stream is byte-identical.
        drill_snap = None
        if (self._drill_pools is not None and self._drill_prob > 0.0
                and self._rng.random() < self._drill_prob):
            drill_snap = self._sample_drill_snapshot()
        self._result = None
        self._steps = 0
        self._map_grid_cache = None
        # Per-episode behavior tallies (`_count_behavior`), surfaced by
        # `_info` at episode end for training-time logging.
        self._ep_end_turns = 0
        self._ep_energy_unspent = 0.0
        self._ep_card_offers = 0
        self._ep_card_takes = 0
        self._ep_rest_visits = 0
        self._ep_rest_heals = 0
        self._ep_rest_upgrades = 0
        # (act, floor) of the rest site currently being answered, plus
        # whether it has already been credited — see `_count_behavior`.
        self._rest_visit_key: tuple[int, int] | None = None
        self._rest_healed_here = False
        self._rest_upgraded_here = False
        self._ep_rest_visits_hihp = 0
        self._ep_rest_upgrades_hihp = 0
        self._rest_visit_hihp = False
        # Counted always, rewarded only when the matching reward_* kwarg is
        # non-zero.
        self._ep_upgrades = 0
        self._ep_removes = 0
        self._ep_relics = 0
        # Combat sloppiness tally, independent of hp_potential_scale shaping
        # (which can be off while this stays on).
        self._ep_hp_lost = 0
        # v20 (Task 3b): HP lost inside BOSS combats, summed over the
        # episode's boss fights — counted always, priced only when
        # boss_hp_loss_penalty > 0.
        self._ep_boss_hp_lost = 0
        self._boss_hp_latch = None
        self._ep_elites_won = 0
        self._ep_potions_obtained = 0
        self._ep_potions_used = 0
        # `_ep_potions_used_elite/boss/normal` sum to `_ep_potions_used`
        # (drinks-only count); `_ep_potion_use_hp` is a running SUM of
        # hp/max_hp at each drink (eval divides by uses); `_ep_potions_expired`
        # is overwritten every step with the CURRENT held count, so it lands
        # on the belt count at whatever step turns out to be the episode's
        # last — no terminal-only special case.
        self._ep_potions_used_elite = 0
        self._ep_potions_used_boss = 0
        self._ep_potions_used_normal = 0
        self._ep_potions_expired = 0
        self._ep_potion_use_hp = 0.0
        # v21: running SUM of v(s) at each drink (eval divides by uses).
        self._ep_potion_v_at_use = 0.0
        self._ep_potions_wasted = 0
        # v21 acquisition reads (spec §3/§4): counted always, never priced.
        self._ep_potions_bought = 0
        self._ep_potion_rewards_skipped = 0
        self._ep_potion_rewards_forced = 0
        self._ep_potion_relic_picks = 0
        self._ep_potions_discarded = 0
        self._ep_potion_skips: list[dict] = []
        # 2026-08-23 hold-duration metric (Perry): per potion INSTANCE, pickup
        # floor -> resolution (used / lost / held at episode end) with floors
        # held, v(s) and room at use. Keyed by object identity (the combat
        # belt is a shallow copy of run.potions, so identity survives).
        # Eval-only (info["ep_potion_holds"]), never reward.
        self._potion_track: dict[int, tuple[str, int]] = {}
        # Objects already recorded as USED whose run.potions slot has not been
        # synced yet (an in-combat drink nulls the COMBAT belt; run.potions
        # keeps the object until finish_combat) — must not be re-tracked.
        self._potion_used_pending: set[int] = set()
        self._ep_potion_holds: list[dict] = []
        self._elite_reward_key: tuple[int, int] | None = None
        # v11.1: elite ATTEMPTS (rooms entered, win or lose), same per-room
        # (act, floor) dedup as the win tally above.
        self._ep_elites_fought = 0
        self._elite_fought_key: tuple[int, int] | None = None
        # Per-card exposure tallies: card CLASS name (unique per card class,
        # unlike display ids) -> count. Eval-only — never in
        # vec_env.EP_METRIC_KEYS (those batch as flat floats).
        self._ep_card_offer_ids: Counter[str] = Counter()
        self._ep_card_take_ids: Counter[str] = Counter()

        run = self._run

        def _drive(*_ignored) -> RunResult:
            # greenlet passes the first switch()'s argument into the target;
            # the kickoff value is meaningless here.
            driver = RunDriver(
                run,
                self._deliver,
                acts=self._acts,
                ascension=self._ascension,
                include_neow=self._include_neow,
                on_combat_start=self._on_combat_start,
                start_setup=(
                    (lambda r: self._drill_start_setup(r, drill_snap))
                    if drill_snap is not None else None),
            )
            return driver.play()

        self._glet = greenlet.greenlet(_drive)
        self._switch(None)   # run until the first decision
        # Baselines for the deck/belt deltas — taken AFTER the driver runs
        # to the first decision (the run is set up, Neow pending): deck and
        # belt are their true episode-start selves here.
        self._deck_upgrade_base = sum(c.upgrade_level for c in run.deck)
        self._deck_len_base = len(run.deck)
        self._belt_base = sum(1 for p in run.potions if p is not None)
        # Relic count baseline. Taken here, same as the deck/belt baselines,
        # so the starting relic (e.g. Burning Blood) is already counted and
        # never fires the reward.
        self._relic_len_base = len(run.relics)
        return self._build_obs(), self._info()

    def _randomize_deck(self, run: RunState) -> None:
        """Append k ~ U[deck_random_cards] reward-pool cards (drawn with
        replacement on the env rng), each upgraded with probability 0.25 when
        upgradable, via the silent deck-add AscendersBane uses (run.py:1318 —
        plain append; no hooks fire, there is no combat yet)."""
        from .cards import make_card
        from .cards.pool import reward_pool_card_ids

        rng = self._rng
        pool = reward_pool_card_ids(run.card_pool)
        k = rng.randint(*self._deck_random_cards)
        for _ in range(k):
            card = make_card(rng.choice(pool))
            if card.max_upgrade_level > 0 and rng.random() < 0.25:
                card.upgrade()
            run.deck.append(card)

    def _inject_deck(self, run: RunState) -> None:
        """v14: append one inject package (1-3 card ids) to the starting
        deck — plain append, no hooks, same as _randomize_deck. Packages,
        not single cards: a lone synergy card (Pact's End with no exhaust
        engine) would teach the card is dead (spec §3)."""
        from .cards import make_card
        pkg = self._rng.choice(self._deck_inject_packages)
        for cid in pkg:
            run.deck.append(make_card(cid))

    # ── v20 drill mode ────────────────────────────────────────────────────

    @staticmethod
    def _drill_pool_key(act_index: int, room_type: str) -> str:
        """Pool naming: 1-based display act + lowercase room — 'a1boss',
        'a2elite', 'a3monster'. `act_index` is the snapshot's 0-based field."""
        return f"a{act_index + 1}{room_type.lower()}"

    def _load_drill_snapshots(self, path: str) -> None:
        """Bucket a schema-2 bank into the configured pools, applying the
        per-encounter oversampling weights within each pool. Everything is
        validated here: `load_snapshots` rejects schema-1 files, and a named
        pool with zero snapshots raises — a silently empty pool would quietly
        renormalize the mix onto the pools that DO have coverage, which is
        the opposite of what stratification is for."""
        from .snapshots import act_module_for_encounter, load_snapshots

        dataset = load_snapshots(path)
        buckets: dict[str, list] = {}
        dropped = 0
        for i in range(len(dataset)):
            snap = dataset[i]
            # Event-launched encounters belong to no act package — the
            # drill setup can't restore an act RoomSet containing them.
            if act_module_for_encounter(snap.encounter_id) is None:
                dropped += 1
                continue
            buckets.setdefault(
                self._drill_pool_key(snap.act, snap.room_type), []
            ).append(snap)
        if dropped:
            print(f"[drill] {path}: dropped {dropped} event-encounter "
                  f"snapshots (not drillable)", flush=True)
        if self._drill_pools_cfg is not None:
            cfg = self._drill_pools_cfg
            missing = [k for k in cfg if k not in buckets or not buckets[k]]
            if missing:
                raise ValueError(
                    f"drill pools with ZERO snapshots in {path}: {missing} "
                    f"(bank has: {sorted(buckets)}) — harvest more coverage "
                    f"or drop the pool")
        else:
            # No pool config: every pool in the bank, mass proportional to
            # its snapshot count (i.e. flat bank sampling). v20 passes pools
            # explicitly; this default exists for ad-hoc use.
            cfg = {k: float(len(v)) for k, v in buckets.items()}
        total = sum(cfg.values())
        if total <= 0:
            raise ValueError("drill_pools masses must sum > 0")
        self._drill_pools = []
        for key, mass in cfg.items():
            snaps = buckets[key]
            weights = [
                self._drill_weights.get(s.encounter_id, 1.0) for s in snaps
            ]
            self._drill_pools.append((key, mass / total, snaps, weights))

    def _sample_drill_snapshot(self):
        """Two `self._rng` draws: pool by mass, then snapshot within pool
        (per-encounter weights applied)."""
        assert self._drill_pools is not None
        roll = self._rng.random()
        acc = 0.0
        key, _mass, snaps, weights = self._drill_pools[-1]
        for cand in self._drill_pools:
            acc += cand[1]
            if roll < acc:
                key, _mass, snaps, weights = cand
                break
        return self._rng.choices(snaps, weights=weights, k=1)[0]

    def _drill_start_setup(self, run: RunState, snap):
        """RunDriver start-injection callable: rewrite `run` (which
        `start_run` just initialized at act 0) into the snapshot's mid-run
        state and return the combat to open the episode with.

        Mirrors the tail of `run.enter_point` for the injected room
        (after_room_entered hook, mark_visited, map_history) so the fight
        sits in the same run-state context a naturally-entered combat would.
        Known approximations (plan Task 3): the act map is re-rolled (layout
        differs from the source run's), a DoubleBoss SECOND-boss snapshot is
        re-fought as the act's primary, and a snapshot belt longer than this
        run's `max_potions` (asc-0 harvest drilled at asc-10 TightBelt) is
        truncated."""
        from .potions import make_potion
        from .rooms import MapPointType, RoomType
        from .snapshots import act_module_for_encounter, build_start_state

        if snap.act >= len(run.act_list):
            raise ValueError(
                f"drill snapshot act {snap.act} out of range for act list "
                f"{run.act_list}")
        # Act 1 is a per-run coin flip (Overgrowth vs Underdocks); the
        # snapshot's encounter pins which module the source run rolled, and
        # that module's RoomSet is the only one containing the encounter —
        # force it before entering the act. (Acts 2/3 are fixed hive/glory,
        # so this is a no-op there.)
        module = act_module_for_encounter(snap.encounter_id)
        assert module is not None   # event snapshots were dropped at load
        if run.act_list[snap.act] != module:
            run.act_list[snap.act] = module
            if snap.act == 0:
                # start_run already started act 0 on the other module —
                # restart it on the right one (acts >= 1 are entered fresh
                # by the advance_act loop below and read the patched list).
                run.start_act(
                    module, ascension=run.ascension,
                    is_final_act=len(run.act_list) == 1, act_index=0)
        for _ in range(snap.act):
            run.advance_act()

        parts = build_start_state(snap)
        run.deck[:] = parts["deck_cards"]
        run.relics[:] = parts["relics"]
        run.max_hp = snap.max_hp
        run.hp = min(snap.hp, snap.max_hp)
        run.gold = snap.gold
        belt = [make_potion(pid) if pid is not None else None
                for pid in snap.potion_slots]
        belt = belt[: run.max_potions]
        belt += [None] * (run.max_potions - len(belt))
        run.potions[:] = belt

        room_type = RoomType[snap.room_type]
        encounter = parts["encounter"]
        if room_type == RoomType.BOSS:
            # Force the act's boss identity to the snapshot's encounter so
            # the run-block obs (run.boss.ids rows) agree with the fight —
            # otherwise the drill teaches "obs say boss X, fight boss Y".
            key = next(
                (k for k, enc in run.room_set.registry.items()
                 if enc.id == snap.encounter_id), None)
            if key is None:
                raise ValueError(
                    f"drill boss encounter {snap.encounter_id!r} not in this "
                    f"act's registry (act {snap.act})")
            if run.room_set.second_boss_key == key:
                run.room_set.second_boss_key = run.room_set.boss_key
            run.room_set.boss_key = key
            point = run.map.boss_point
        else:
            # Row from the within-act floor offset (approximate: acts differ
            # slightly in length; the clamp keeps it on the grid). The point
            # choice only shapes the map obs and the post-combat routing —
            # prefer a node whose type matches the fight.
            row_count = run.map.row_count
            floor_in_act = snap.floor - snap.act * row_count
            row = min(max(floor_in_act, 1), row_count - 1)
            candidates = run.map.points_in_row(row)
            want = (MapPointType.ELITE if room_type == RoomType.ELITE
                    else MapPointType.MONSTER)
            matching = [p for p in candidates if p.point_type == want]
            point = self._rng.choice(matching or candidates)

        run.current_point = point
        run.total_floor = snap.floor
        run.current_room_type = room_type
        run.current_event = None
        # The tail of enter_point for the injected room:
        for relic in list(run.relics):
            relic.after_room_entered(run, point, room_type)
        run.room_set.mark_visited(room_type)
        run._last_room_types = [room_type]
        run.map_history.append((point, room_type))
        return encounter, room_type

    def step(self, action: int):
        assert self._run is not None, "call reset() before step()"
        run = self._run
        request = self._request
        self._steps += 1
        reward = 0.0
        drink_potion = None
        drink_hp_before = None
        drink_block_wasted = False

        if request is not None:
            answer = self._translate(int(action), request)
            if answer is None:
                # Illegal action: a no-op step (mirrors full_env semantics).
                return self._build_obs(), 0.0, False, self._steps >= self._max_steps, self._info()
            hp_before = run.hp
            max_hp_before = run.max_hp
            floor_before = run.total_floor
            act_before = run.act_index
            elites_before = self._ep_elites_won
            fought_before = self._ep_elites_fought
            energy_before = self._ep_energy_unspent
            self._count_behavior(request, answer)
            # v21: opportunity-value charge at the drink, priced off the room
            # state BEFORE the action resolves (the room the drink happens in).
            drink_slot = self._drink_slot(request, answer)
            if drink_slot is not None:
                v_now = potion_option_value(run)
                self._ep_potion_v_at_use += v_now
                if self._potion_option_value:
                    reward -= self._potion_option_value * v_now
                in_combat = (
                    request.kind == DecisionKind.COMBAT
                    and request.combat is not None
                    and getattr(request.combat, "player", None) is not None)
                belt = (getattr(request.combat.player, "potions", None) if in_combat else None) or run.potions
                drink_potion = belt[drink_slot] if 0 <= drink_slot < len(belt) else None
                drink_hp_before = request.combat.player.hp if in_combat else run.hp
                if in_combat and isinstance(drink_potion, BlockPotion):
                    drink_block_wasted = preview_total_incoming(request.combat) <= 0
                if drink_potion is not None:
                    if in_combat:
                        rt = request.combat.room_type
                        room = ("elite" if rt == RoomType.ELITE
                                else "boss" if rt == RoomType.BOSS else "normal")
                    else:
                        room = "none"
                    self._record_potion_hold(drink_potion, "used", room=room, v=v_now)
            # v22: a discard resolves the tracked instance at decision time,
            # like a drink — the slot is nulled inside _switch. v(s) recorded
            # for the read; NO reward here (the belt-delta ledger below pays
            # the -k, identically to any other belt decrease).
            if answer >= POTION_DISCARD_ACTION_BASE:
                discard_potion = run.potions[answer - POTION_DISCARD_ACTION_BASE]
                if discard_potion is not None:
                    self._ep_potions_discarded += 1
                    self._record_potion_hold(
                        discard_potion, "discarded", room="none",
                        v=potion_option_value(run))
            # v20 (Task 3b): latch HP at the first decision of a BOSS
            # combat (new-combat detection by combat-object identity —
            # the boss_probe.py pattern). The pre-combat run.hp equals
            # combat.player.hp here, minus any combat-start relic effects,
            # which is the right baseline: "damage taken across the fight's
            # decisions".
            _boss_combat = (
                request.combat
                if request.combat is not None
                and request.combat.room_type == RoomType.BOSS
                # getattr guards: reward-screen test doubles hand the env
                # SimpleNamespace combats with no player/result.
                and getattr(request.combat, "player", None) is not None
                else None)
            if _boss_combat is not None and (
                    self._boss_hp_latch is None
                    or self._boss_hp_latch[0] != id(_boss_combat)):
                self._boss_hp_latch = (
                    id(_boss_combat), _boss_combat.player.hp)
            self._switch(answer)
        else:
            _boss_combat = None
            hp_before, floor_before, act_before = run.hp, run.total_floor, run.act_index
            max_hp_before = run.max_hp
            elites_before = self._ep_elites_won
            fought_before = self._ep_elites_fought
            energy_before = self._ep_energy_unspent

        self._ep_hp_lost += max(0, hp_before - run.hp)
        reward += self._hp_reward_scale * (min(run.hp, run.max_hp) - min(hp_before, run.max_hp)) / max(1, run.max_hp)
        # v20 (Task 3b): boss-fight HP loss, paid once when the boss combat
        # resolves (won or lost). Non-refundable by design — the act-entry
        # heal refunds the hp-potential term's in-fight losses, this term is
        # the surviving price. Counted always; priced only when K > 0.
        if (_boss_combat is not None and self._boss_hp_latch is not None
                and self._boss_hp_latch[0] == id(_boss_combat)
                and (getattr(_boss_combat, "result", None) is not None
                     or getattr(_boss_combat.player, "is_dead", False))):
            _lost = max(0, self._boss_hp_latch[1]
                        - max(0, _boss_combat.player.hp))
            self._ep_boss_hp_lost += _lost
            reward -= self._boss_hp_loss_penalty * _lost / max(1, run.max_hp)
            self._boss_hp_latch = None
        # Concave potential-based shaping, each ratio measured against its
        # OWN step's max_hp (before-ratio uses
        # max_hp_before, after-ratio uses the post-step max_hp) so a max-HP
        # gain can't fire this term backwards. Death terminal: hp=0 -> phi=0,
        # no special case needed (the piecewise formula already gives 0).
        ratio_before = min(hp_before, max_hp_before) / max(1, max_hp_before)
        ratio_after = min(run.hp, run.max_hp) / max(1, run.max_hp)
        shaped_after = ratio_after
        if (self._rest_heal_shaping_knee_cap
                and request is not None
                and request.kind == DecisionKind.REST
                and answer == REST_HEAL):
            # Rest-collapse fix: a rest heal earns shaped reward only
            # inside the danger zone. ΔΦ is undiscounted while the healed
            # HP's later losses are discounted, so an uncapped campfire heal
            # is a net-positive farm that outbids REST_SMITH's flat
            # +reward_upgrade; capping the after-ratio at the knee (and
            # clamping to zero when the heal STARTS at/above it) removes
            # exactly that edge and nothing else.
            shaped_after = min(ratio_after, self._hp_potential_knee)
            if shaped_after < ratio_before:
                shaped_after = ratio_before
        reward += self._hp_potential_scale * (
            _hp_potential(shaped_after, self._hp_potential_knee, self._hp_potential_low_share)
            - _hp_potential(ratio_before, self._hp_potential_knee, self._hp_potential_low_share)
        )
        if self._floor_rewards_by_act is not None:
            act_i = max(0, min(run.act_index, len(self._floor_rewards_by_act) - 1))
            reward += self._floor_rewards_by_act[act_i] * (run.total_floor - floor_before)
        else:
            reward += self._floor_reward * (run.total_floor - floor_before)
        # v15 mid-run exposure: on a floor advance, with probability P,
        # append one dead-list package to the live deck. Same zero-draw
        # short-circuit contract as the reset-time inject (see
        # `_deck_inject_packages` above): packages None or prob 0.0 must
        # draw no rng. Plain append of UNUPGRADED cards only -- the deck
        # ledger below pays nothing for growth, and the next out-of-combat
        # check re-syncs _deck_len_base, so no reward term fires from the
        # injection itself.
        if (run.total_floor > floor_before
                and self._deck_inject_midrun_packages is not None
                and self._deck_inject_midrun_prob > 0.0
                and self._rng.random() < self._deck_inject_midrun_prob):
            from .cards import make_card
            for cid in self._rng.choice(self._deck_inject_midrun_packages):
                run.deck.append(make_card(cid))
        reward += self._act_reward * (run.act_index - act_before)
        reward += self._reward_elite * (self._ep_elites_won - elites_before)
        # v11.1: pay the elite-entry credit the step the attempt is tallied
        # (`_count_behavior` above), decoupled from the win-only term.
        reward += self._reward_elite_attempt * (self._ep_elites_fought - fought_before)
        # v16: charge stranded energy the step its END_TURN is tallied
        # (`_count_behavior` above) — per-turn, never terminal-gated.
        reward -= self._energy_waste_penalty * (self._ep_energy_unspent - energy_before)
        # v11: an act-boss kill IS the act_index advance (act entry lands on
        # the next act's Ancient node in the same transition); the final
        # boss pays via the win branch below — exactly once per boss.
        reward += self._reward_boss * (run.act_index - act_before)

        terminated = self._result is not None
        if terminated:
            if self._result.victory:
                reward += self._reward_win + self._reward_boss + self._win_hp_bonus * (
                    self._result.hp / max(1, self._result.max_hp)
                )
            else:
                reward += self._reward_loss
        truncated = (not terminated) and self._steps >= self._max_steps

        # Deck/belt deltas — measured only between decisions with no live
        # combat (in-combat temporary upgrades and mid-combat deck adds are
        # ignored; permanent changes get credited at the first out-of-combat
        # step).
        if self._request is None or self._request.kind != DecisionKind.COMBAT:
            up_now = sum(c.upgrade_level for c in run.deck)
            if up_now > self._deck_upgrade_base:
                gained = up_now - self._deck_upgrade_base
                reward += self._reward_upgrade * gained
                self._ep_upgrades += gained
            self._deck_upgrade_base = up_now
            n_now = len(run.deck)
            if n_now < self._deck_len_base:
                removed = self._deck_len_base - n_now
                reward += self._reward_remove * removed
                self._ep_removes += removed
            self._deck_len_base = n_now
            relics_now = len(run.relics)
            if relics_now > self._relic_len_base:
                gained_relics = relics_now - self._relic_len_base
                reward += self._reward_relic * gained_relics
                self._ep_relics += gained_relics
                for relic in run.relics[self._relic_len_base:]:
                    if getattr(relic, "id", None) in POTION_RELIC_IDS:
                        self._ep_potion_relic_picks += 1
            self._relic_len_base = relics_now
        # v21 metric: was the drink (near-)nil? Heal overflow or block with
        # nothing incoming. Counter only — never touches reward.
        if drink_potion is not None:
            wasted = drink_block_wasted
            heal_pct = getattr(drink_potion, "HEAL_PERCENT", 0)
            if heal_pct > 0:
                nxt = self._request
                if (nxt is not None and nxt.kind == DecisionKind.COMBAT
                        and nxt.combat is not None
                        and getattr(nxt.combat, "player", None) is not None):
                    hp_after = nxt.combat.player.hp
                else:
                    hp_after = run.hp
                nominal = run.max_hp * heal_pct // 100
                wasted = wasted or (hp_after - drink_hp_before) < 0.5 * nominal
            if wasted:
                self._ep_potions_wasted += 1
        self._sync_potion_track(terminated or truncated)
        belt_now = sum(1 for p in run.potions if p is not None)
        if belt_now > self._belt_base:
            gained = belt_now - self._belt_base
            self._ep_potions_obtained += gained
            # +k per potion picked up. No
            # terminal zeroing — a potion still held at episode end keeps
            # this +k (see `_ep_potions_expired` below).
            reward += self._potion_potential_scale * gained
        elif belt_now < self._belt_base:
            lost = self._belt_base - belt_now
            reward -= self._potion_potential_scale * lost
            # A DRINK is exactly the answer this step decoded to a belt slot
            # (`_translate`'s POTION_BASE branch -> `POTION_ACTION_BASE +
            # slot`; driver.py:405-411 always empties that slot on the same
            # turn). Any OTHER belt decrease — a shop sale (no such feature
            # exists in this sim today, but the same non-drink shape would
            # apply) or an event trading a potion away (discard_potion) —
            # moves the ledger but is not a "use": it never answered via a
            # potion action this step, so it can't be attributed to a room.
            if (request is not None
                    and POTION_ACTION_BASE <= answer < POTION_DISCARD_ACTION_BASE):
                # An overlay drink empties exactly ONE slot, so count 1, not
                # `lost` — a coincident non-drink loss in the same delta must
                # stay anonymous. And an AnyTime overlay drink is by
                # definition OUTSIDE live combat (the overlay is masked off
                # while combat is live), so it is always `normal`; elite/boss
                # attribution happens at the in-combat pair action in
                # `_count_behavior` (2026-08-18 counter fix — the old
                # `kind == COMBAT` split here was dead code).
                self._ep_potions_used += 1
                self._ep_potion_use_hp += (
                    min(hp_before, max_hp_before) / max(1, max_hp_before))
                self._ep_potions_used_normal += 1
        self._belt_base = belt_now
        # Overwritten every step with the CURRENT held count, so whichever
        # step turns out to be the episode's last (`_info` gates on that same
        # terminated-or-truncated condition) leaves this at the right value —
        # no separate terminal-only branch needed.
        self._ep_potions_expired = belt_now

        if (self._potion_death_expiry and terminated
                and self._result is not None and not self._result.victory):
            # Never-drink fix: the ledger pays +k on pickup and nothing at
            # episode end, so hoard-until-death nets +k per potion and
            # strictly dominates drinking (drink = +k-k = 0). Forfeiting the
            # pickup credit on DEATH makes hoard-and-die net 0 too — the
            # tiebreaker becomes the potion's actual combat value. Wins keep
            # the credit (winning with a spare potion is not a sin), and
            # truncation is a harness artifact, so neither expires.
            reward -= self._potion_potential_scale * belt_now
        if (self._potion_death_penalty and terminated
                and self._result is not None and not self._result.victory):
            # v15.1: flat charge per held potion at death (see ctor comment).
            # Same guard shape as the expiry above: deaths only — wins and
            # truncations keep their belts free of charge.
            reward -= self._potion_death_penalty * belt_now
        if (self._potion_option_expiry and self._potion_option_value and terminated
                and self._result is not None and not self._result.victory):
            # v21: hoard-and-die pays what drinking each potion here would have.
            reward -= self._potion_option_value * potion_option_value(run) * belt_now

        return self._build_obs(), float(reward), terminated, truncated, self._info()

    def _drink_slot(self, request: DecisionRequest | None, answer: int) -> int | None:
        """Belt slot this answer drinks from, or None when it is not a drink.
        Two paths exist (2026-08-18 counter fix): the in-combat potion-pair
        block of a COMBAT request, and the AnyTime belt overlay on any
        request (`POTION_ACTION_BASE + slot`)."""
        if request is None:
            return None
        if POTION_ACTION_BASE <= answer < POTION_DISCARD_ACTION_BASE:
            return answer - POTION_ACTION_BASE
        if (request.kind == DecisionKind.COMBAT and request.combat is not None
                and COMBAT_POTION_BASE <= answer < N_COMBAT_ACTIONS):
            return (answer - COMBAT_POTION_BASE) // MAX_ENEMIES
        return None

    def _record_potion_hold(self, potion, outcome: str, *, room: str = "none",
                            v: float | None = None) -> None:
        """Resolve one tracked potion instance into `_ep_potion_holds`. An
        untracked potion (created and drunk inside one combat, so it never
        reached run.potions) is recorded with a zero hold."""
        run = self._run
        floor = run.total_floor
        pid, pickup = self._potion_track.pop(
            id(potion), (getattr(potion, "id", "?"), floor))
        self._potion_used_pending.add(id(potion))
        self._ep_potion_holds.append({
            "id": pid, "held": floor - pickup, "outcome": outcome, "room": room,
            "v": v, "pickup_floor": pickup, "floor": floor})

    def _sync_potion_track(self, episode_over: bool) -> None:
        """After the action resolved: start tracking potions that newly
        appeared on run.potions, resolve tracked ones that vanished without a
        drink this step as 'lost', and at episode end resolve the rest as
        'held'. Combat-time belt changes surface here when finish_combat syncs
        run.potions (the drink itself was already recorded at decision time)."""
        run = self._run
        live = {id(p): p for p in run.potions if p is not None}
        self._potion_used_pending &= set(live)      # synced away -> forget
        for key, p in live.items():
            if key not in self._potion_track and key not in self._potion_used_pending:
                self._potion_track[key] = (getattr(p, "id", "?"), run.total_floor)
        for key in [k for k in self._potion_track if k not in live]:
            pid, pickup = self._potion_track.pop(key)
            self._ep_potion_holds.append({
                "id": pid, "held": run.total_floor - pickup, "outcome": "lost",
                "room": "none", "v": None, "pickup_floor": pickup,
                "floor": run.total_floor})
        if episode_over:
            for key in list(self._potion_track):
                pid, pickup = self._potion_track.pop(key)
                self._ep_potion_holds.append({
                    "id": pid, "held": run.total_floor - pickup, "outcome": "held",
                    "room": "none", "v": None, "pickup_floor": pickup,
                    "floor": run.total_floor})

    def _count_behavior(self, request: DecisionRequest, answer: int) -> None:
        """Per-episode behavior tallies, read back by `_info` at episode end.

        End-turns count only on the player's turn — action 0 is also the
        always-legal no-op outside it, and counting those would dilute the
        unspent-energy average with meaningless energy readings. Card-reward
        screens count only on their own take/skip answers: reroll and
        sacrifice re-raise or transform the screen (counting them would tally
        the same offer twice), and a belt drink doesn't answer it at all.

        Rest sites count per VISIT, not per decision: `RunDriver._rest_site`
        re-asks until Leave, so one visit can answer several times (Miniature
        Tent even allows heal AND smith), and healing twice in one visit is
        still one healed visit. A visit is keyed on (act, floor) — a rest site
        is one room on one floor and its decisions are consecutive, so the key
        changes exactly at a visit boundary. Every visit counts in the
        denominator, including one the agent simply left.
        """
        # Elite tally: any request carrying a rewards screen from an elite
        # room means the elite was beaten; dedupe per room like rest visits
        # (the rewards screen re-asks per item taken).
        rewards = getattr(request, "rewards", None)
        if rewards is not None and rewards.room_type == RoomType.ELITE:
            key = (request.run.act_index, request.run.total_floor)
            if key != self._elite_reward_key:
                self._elite_reward_key = key
                self._ep_elites_won += 1
        # v11.1: elite ATTEMPT — the first answered combat decision inside an
        # elite room, before the outcome exists (a death here never reaches
        # the rewards screen, so the win tally above can't see it).
        if (request.kind == DecisionKind.COMBAT and request.combat is not None
                and request.combat.room_type == RoomType.ELITE):
            key = (request.run.act_index, request.run.total_floor)
            if key != self._elite_fought_key:
                self._elite_fought_key = key
                self._ep_elites_fought += 1
        # 2026-08-18 counter fix: an IN-COMBAT drink is a potion-pair action
        # ([COMBAT_POTION_BASE, N_COMBAT_ACTIONS)), passed through RAW by
        # `_translate`'s COMBAT branch — it never reaches the belt-delta
        # branch's `answer >= POTION_ACTION_BASE` test (the belt overlay is
        # masked off while combat is live), so before this block ~97% of all
        # drinks were booked as anonymous belt losses and the elite/boss
        # split was structurally always 0. Counted here, at the answered
        # action, off the COMBAT player's decision-time hp (the run-level
        # `hp_before` can lag the live combat). The belt decrement itself
        # surfaces on a LATER step and stays an uncounted ledger move — no
        # double count (test_v8_rewards pair-drink tests).
        if (request.kind == DecisionKind.COMBAT
                and request.combat is not None
                and COMBAT_POTION_BASE <= answer < N_COMBAT_ACTIONS):
            self._ep_potions_used += 1
            player = request.combat.player
            self._ep_potion_use_hp += (
                min(player.hp, player.max_hp) / max(1, player.max_hp))
            room = request.combat.room_type
            if room == RoomType.ELITE:
                self._ep_potions_used_elite += 1
            elif room == RoomType.BOSS:
                self._ep_potions_used_boss += 1
            else:
                self._ep_potions_used_normal += 1
        # v21: SHOP answer that buys a potion (entry inspected BEFORE the
        # driver's purchase()); a full belt is excluded — the purchase would
        # be refused and the policy can retry it hundreds of times (seen:
        # 9932/ep), which is not a buy.
        if request.kind == DecisionKind.SHOP and request.shop is not None:
            entries = request.shop.all_entries
            if 0 <= answer < len(entries):
                from .shop import MerchantPotionEntry
                entry = entries[answer]
                if (isinstance(entry, MerchantPotionEntry)
                        and entry.is_stocked and entry.enough_gold
                        and request.run.has_open_potion_slot):
                    self._ep_potions_bought += 1
        # v21: potion reward declined — voluntarily (a slot was open) vs forced
        # (belt full: skip was the only legal answer; sizes the v22
        # discard-to-take affordance gap).
        if request.kind == DecisionKind.REWARD_POTION and answer == 1:
            if request.run.has_open_potion_slot:
                self._ep_potion_rewards_skipped += 1
                # v22 selectivity read: what was declined while holding what.
                # The offered potion is request.potion on a bare offer
                # (_offer_potion) and rewards.potions[0] on the reward-set
                # path (the loop narrows rewards.potions to the one being
                # asked about — driver.py `pending` loop).
                offered = request.potion
                if offered is None and request.rewards is not None and request.rewards.potions:
                    offered = request.rewards.potions[0]
                self._ep_potion_skips.append({
                    "offered": getattr(offered, "id", "?"),
                    "belt": [p.id for p in request.run.potions if p is not None],
                    "floor": request.run.total_floor,
                })
            else:
                self._ep_potion_rewards_forced += 1
        if (request.kind == DecisionKind.COMBAT and answer == 0
                and request.combat is not None
                and request.combat.phase == Phase.PLAYER_TURN):
            self._ep_end_turns += 1
            self._ep_energy_unspent += request.combat.player.energy
        elif (request.kind == DecisionKind.REWARD_CARD
                and answer < POTION_ACTION_BASE
                and answer <= len(request.rewards.cards)):
            self._ep_card_offers += 1
            self._ep_card_takes += int(answer < len(request.rewards.cards))
            # Per-card exposure: tally every offered card, and the taken
            # one, by class name.
            for card in request.rewards.cards:
                self._ep_card_offer_ids[type(card).__name__] += 1
            if answer < len(request.rewards.cards):
                self._ep_card_take_ids[
                    type(request.rewards.cards[answer]).__name__] += 1
        elif request.kind == DecisionKind.REST and answer < POTION_ACTION_BASE:
            key = (request.run.act_index, request.run.total_floor)
            if key != self._rest_visit_key:
                self._rest_visit_key = key
                self._ep_rest_visits += 1
                self._rest_healed_here = False
                self._rest_upgraded_here = False
                # Classified once, at the visit's first answer -- later
                # answers at the same site (heal after smith etc.) keep the
                # entry ratio, so the split is per-visit not per-answer.
                ratio = min(request.run.hp, request.run.max_hp) / max(1, request.run.max_hp)
                self._rest_visit_hihp = ratio >= HIHP_REST_THRESHOLD
                if self._rest_visit_hihp:
                    self._ep_rest_visits_hihp += 1
            if answer == REST_HEAL and not self._rest_healed_here:
                self._rest_healed_here = True
                self._ep_rest_heals += 1
            elif answer == REST_SMITH and not self._rest_upgraded_here:
                self._rest_upgraded_here = True
                self._ep_rest_upgrades += 1
                if self._rest_visit_hihp:
                    self._ep_rest_upgrades_hihp += 1

    def close(self) -> None:
        self._kill_driver()
        super().close()

    # ------------------------------------------------------------------
    # Action translation / masking. The SELECT_CARDS branches of both
    # methods below address the sorted candidate order — see
    # ``_sorted_candidate_order``'s docstring for the ordering contract both
    # sides share.
    # ------------------------------------------------------------------

    def _translate(self, action: int, request: DecisionRequest) -> int | None:
        """Env action → the driver's answer for the pending request; None if
        the action is illegal for the current phase."""
        kind = request.kind
        # The belt block crosses every phase (an AnyTime potion is usable from
        # any screen), so it is decoded before the per-kind blocks.
        if POTION_BASE <= action < POTION_BASE + MAX_POTION_SLOTS:
            answer = POTION_ACTION_BASE + (action - POTION_BASE)
            return answer if answer in request.potion_actions() else None
        if DISCARD_BASE <= action < DISCARD_BASE + MAX_POTION_SLOTS:
            answer = POTION_DISCARD_ACTION_BASE + (action - DISCARD_BASE)
            return answer if answer in request.discard_actions() else None
        legal = request.own_actions()
        if kind == DecisionKind.COMBAT:
            return action if action < N_COMBAT_ACTIONS and action in legal else None
        if kind == DecisionKind.SELECT_CARDS:
            if request.skippable and action == CHOICE_BASE:
                return len(request.candidates)
            # action SELECT_BASE + i answers sorted candidate row i —
            # ``_sorted_candidate_order(request)[i]``, the SAME order the
            # observation's ``select.candidates`` rows are written in. `order`
            # already reflects the cap (never more entries than rows
            # actually exist — see that method's docstring), so an `i` past
            # `len(order)` correctly falls through to illegal (None).
            if SELECT_BASE <= action < SELECT_BASE + MAX_SELECT_CANDIDATES:
                i = action - SELECT_BASE
                order = self._sorted_candidate_order(request)
                if i < len(order):
                    return order[i]
            return None
        # Every other kind answers with a generic choice-slot index.
        if CHOICE_BASE <= action < CHOICE_BASE + CHOICE_SLOTS:
            answer = action - CHOICE_BASE
            return answer if answer in legal else None
        return None

    def action_masks(self) -> np.ndarray:
        mask = np.zeros(self.n_actions, dtype=bool)
        request = self._request
        if request is None:
            mask[0] = True   # terminal/truncated: one harmless no-op
            return mask
        kind = request.kind
        # Bound, don't crash: a belt grown past MAX_POTION_SLOTS must not
        # index past the end of this array. Truncate rather than assert — a
        # crash mid-training is worse than an unreachable slot. `_build_obs`'s
        # `run.potions` block shares this same cap, so an overgrown belt
        # also fires `run.potions.overflow` there.
        for answer in request.potion_actions():
            slot = answer - POTION_ACTION_BASE
            if slot < MAX_POTION_SLOTS:
                mask[POTION_BASE + slot] = True
        for answer in request.discard_actions():
            slot = answer - POTION_DISCARD_ACTION_BASE
            if slot < MAX_POTION_SLOTS:
                mask[DISCARD_BASE + slot] = True
        legal = request.own_actions()
        if kind == DecisionKind.COMBAT:
            mask[legal] = True
        elif kind == DecisionKind.SELECT_CARDS:
            # One mask bit per candidate row `_sorted_candidate_order`
            # actually addresses — never more than MAX_SELECT_CANDIDATES,
            # since that helper already truncates to match the observation.
            # A truncated ACTION block makes a real, choosable candidate
            # unclickable (worse than a truncated observation block, which
            # only degrades the view), so this never asserts on overflow —
            # the loud signal is `select.candidates.overflow` in the
            # observation, firing from the same truncated order.
            order = self._sorted_candidate_order(request)
            for i in range(len(order)):
                mask[SELECT_BASE + i] = True
            if request.skippable:
                mask[CHOICE_BASE] = True
        else:
            assert max(legal) < CHOICE_SLOTS, (
                f"{kind} offered {max(legal) + 1} options; grow CHOICE_SLOTS"
            )
            for i in legal:
                mask[CHOICE_BASE + i] = True
            # rest_heal_mask_above curriculum mask. Only at a rest-site
            # decision, only above the HP-ratio threshold,
            # and only when REST_HEAL is not the sole legal action — never
            # mask away the only option (`driver.py`'s REST_HEAL/REST_SMITH/
            # REST_LEAVE=0,1,2; REST_HEAL always legal unless already used
            # this visit).
            if (kind == DecisionKind.REST
                    and self._rest_heal_mask_above is not None
                    and REST_HEAL in legal
                    and len(legal) > 1):
                run = self._run
                ratio = run.hp / max(1, run.max_hp)
                if ratio >= self._rest_heal_mask_above:
                    mask[CHOICE_BASE + REST_HEAL] = False
        assert mask.any()
        return mask

    # ------------------------------------------------------------------
    # The candidate-index action block (`_translate`/`action_masks` above)
    # addresses ``select.candidates``' SORTED row order and translates a
    # chosen row back to the true candidate index through this method. This
    # is the single source of that order — the observation writer below sorts
    # via ``ObsBuffer.write_rows(..., sort=True)``, and this method computes
    # the IDENTICAL key independently, so the two can never silently
    # disagree.
    # ------------------------------------------------------------------

    def _sorted_candidate_order(self, request: DecisionRequest) -> list[int]:
        """The true candidate indices (into ``request.candidates``), in the
        SAME canonical order ``select.candidates``' rows are written in —
        and, since ``write_rows`` TRUNCATES to ``MAX_SELECT_CANDIDATES``
        after sorting, this returns EXACTLY the rows that exist, never more
        (an uncapped helper would enable actions for candidate rows that are
        all-PAD in the policy's own observation). Also mirrors
        ``select.candidates``' own guard: a candidate whose card id cannot
        be resolved to a vocab index never becomes a row there, so it must
        never appear in this order either — computed with the identical
        ``card.id in CARD_INDEX`` predicate, in the same position (before
        the sort), for the same reason ``write_rows(sort=True)`` sorts
        before truncating (see that method's own docstring): the retained
        set must be a deterministic function of the candidate multiset
        alone, not of input order.

        OBS_SCHEMA.md §2.6's trap: ``from_draw`` candidates arrive in
        draw-pile order — hidden information the real game's own select
        screen does not leak (confirmed at source:
        ``NCombatPileCardSelectScreen.UpdatePileContents``,
        `Slay the Spire 2/src/Core/Nodes/Screens/CardSelection/
        NCombatPileCardSelectScreen.cs:215-258`, sorts Draw-pile candidates
        by ``(Rarity, Alphabet)`` before handing them to the card grid —
        other piles, e.g. Discard, use the source order unsorted, but those
        aren't hidden-order piles anyway). This module's own sort key
        differs from the game's (ours is ``(tuple(ints), tuple(floats))``
        over ``_run_card_row``'s row shape, not rarity+alphabet) — that is
        fine: any canonical, order-independent sort closes the
        leak; matching the game's own display order is not required, only
        matching what OUR OWN observation actually wrote.

        Python's ``sorted`` is stable, and ``write_rows(sort=True)`` sorts
        the exact same ``(ints, floats)`` pairs with the exact same key
        (see ``obs.ObsBuffer.write_rows``'s docstring) — so this needs no
        access to the actual written buffer to guarantee agreement; it is
        the same deterministic function of ``request.candidates`` alone.
        """
        addressable = [
            i for i, card in enumerate(request.candidates) if card.id in CARD_INDEX
        ]
        rows = {i: _run_card_row(request.candidates[i]) for i in addressable}
        order = sorted(
            addressable, key=lambda i: (tuple(rows[i][0]), tuple(rows[i][1])),
        )
        return order[:MAX_SELECT_CANDIDATES]

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def _build_obs(self) -> dict[str, np.ndarray]:
        # One persistent buffer, reset()+rewritten every step (OBS_SCHEMA.md
        # §2.1: reset() leaves PAD ids / zero floats, so a block that is not
        # live this step — e.g. every phase-specific block except the
        # current phase's, or the whole combat sub-block outside combat —
        # is exactly that: PAD/zero, never stale content from a previous
        # step). ``buf.f`` / ``buf.i`` are the buffer's OWN arrays (this
        # method copies them directly at the end rather than routing
        # through ``ObsBuffer.as_obs()``, which would hand back those same
        # live arrays uncopied) — the returned dict is copied before
        # leaving this method — the SAME hazard `full_env.build_combat_obs`'s
        # docstring warns about (a rollout-buffer entry must never see
        # itself mutate on the next step()).
        run = self._run
        request = self._request
        buf = self._buf
        buf.reset()
        L = buf.layout

        def F(name: str) -> slice:
            return L.f_slices[name]

        def I(name: str) -> slice:
            return L.i_slices[name]

        # ── Phase one-hot (kept a float one-hot: DecisionKind is not a
        #    vocab.py vocabulary and N_PHASES is small — OBS_SCHEMA.md §2.2) ─
        if request is not None:
            buf.f[F("phase").start + PHASE_INDEX[request.kind]] = 1.0

        # ── Run vitals (unchanged names/encodings, except R6 gold) ────────
        hp = max(0, run.hp)
        buf.f[F("run.hp_ratio")] = _clip01(hp / max(1, run.max_hp))
        buf.f[F("run.hp_abs")] = _abs2(hp)
        buf.f[F("run.max_hp_abs")] = _abs2(run.max_hp)
        buf.f[F("run.gold")] = [
            _log1p_scale(run.gold, GOLD_LOG_FINE_DENOM),
            _log1p_scale(run.gold, GOLD_LOG_COARSE_DENOM),
        ]
        if 0 <= run.act_index < _N_ACTS:
            buf.f[F("run.act").start + run.act_index] = 1.0
        buf.f[F("run.floor")] = _clip01(run.total_floor / 50.0)

        overflow: dict[str, bool] = {}

        # ── Potion belt (run-level; combat exposes its own rows too) ─────
        # `RunState.potions` is a pre-combat SNAPSHOT — `RunState.
        # finish_combat` only copies the live `combat.player.potions` back
        # into it once the combat ENDS (`run.py:finish_combat`'s
        # `self.potions = list(combat.player.potions)`). The game has no
        # such split (one Player, one belt), so a potion drunk MID-combat
        # (e.g. Skill Potion's card-add, surfaced as a SELECT_CARDS
        # decision) empties its game-side belt slot immediately — confirmed
        # against seed 89U21BV1TZ act 0 floor 15 (game dump: belt slot 2
        # already empty from Combat decision 4 onward; sim dump: still
        # filled for the rest of the combat). Read the LIVE belt off
        # `request.combat.player.potions` whenever a combat is active.
        live_combat = request.combat if request is not None else None
        potions = live_combat.player.potions if live_combat is not None else run.potions
        potion_rows = []
        for p in range(max(MAX_POTION_SLOTS, len(potions))):
            potion = potions[p] if p < len(potions) else None
            ints = [oid(POTION_INDEX.get(potion.id))] if potion is not None else [PAD]
            floats = [
                1.0 if potion is not None else 0.0,     # present
                1.0 if p < run.max_potions else 0.0,    # slot exists
            ]
            potion_rows.append((ints, floats))
        overflow["run.potions"] = buf.write_rows(
            "run.potions", potion_rows, cap=MAX_POTION_SLOTS, n_int=1, n_float=2, sort=False)

        # ── Deck (R2 instance rows, SORTED — a multiset, order-independent
        #    for free; deck order is not hidden information, but the sort
        #    makes this block canonical the same way `cards` is in combat) ─
        # A card whose id is not in CARD_INDEX is SKIPPED — `_run_card_row`
        # computes its floats straight off the card object regardless of id
        # resolution, so writing it anyway would produce a PAD-id row with
        # live floats, violating OBS_SCHEMA.md §2.1's "PAD means id==0 AND
        # all-zero floats" invariant. Unreachable today.
        # On overflow `write_rows` warns (once per process) and truncates,
        # which names the segment but not the deck that blew the cap — so dump
        # the deck's contents to the overflow log alongside that warning.
        overflow["run.deck"] = buf.write_rows(
            "run.deck", [_run_card_row(c) for c in run.deck if c.id in CARD_INDEX],
            cap=MAX_DECK_ROWS, n_int=4, n_float=4, sort=True)
        if overflow["run.deck"]:
            _log_deck_overflow(run, list(run.deck))

        # ── Relics (R1, acquisition order — what the relic bar shows) ────
        # Skip a relic whose id is not in RELIC_INDEX, rather than writing a
        # PAD-id row with `relic_row`'s live counter/flag floats (same
        # invariant as run.deck above).
        relic_rows = []
        for relic in run.relics:
            idx = RELIC_INDEX.get(relic.id)
            if idx is None:
                continue
            counter, flag = relic_row(relic, in_combat=False)
            relic_rows.append(([oid(idx)], [counter / 10.0, float(flag)]))
        overflow["run.relics"] = buf.write_rows(
            "run.relics", relic_rows, cap=MAX_RELIC_ROWS, n_int=1, n_float=2, sort=False)

        # ── Boss identity (known from act entry, like the boss icon) ─────
        room_set = run.room_set
        boss_rows = []
        if room_set is not None and room_set.boss_key:
            # next_boss_encounter switches to the second boss under
            # DoubleBoss once the first falls, matching the icon.
            for cls in room_set.next_boss_encounter.monster_classes:
                idx = MONSTER_INDEX.get(getattr(cls, "__name__", ""))
                # An unrecognised monster class must be SKIPPED, not
                # appended as a PAD row — appending would consume one of
                # only MAX_BOSS_IDS slots and shift every later real id into
                # a row it doesn't belong in. Unreachable today.
                if idx is None:
                    continue
                boss_rows.append(([oid(idx)], []))
        overflow["run.boss"] = buf.write_rows(
            "run.boss", boss_rows, cap=MAX_BOSS_IDS, n_int=1, n_float=0, sort=False)

        # ── Map block (filled during MAP; slots align with choice slots) ─
        if request is not None and request.kind == DecisionKind.MAP:
            ML = _map_slot_layout(self._card_obs)
            points = request.points
            for m in range(min(MAP_SLOTS, len(points))):
                point = points[m]
                if point is None:
                    continue
                rb = ML.map_base + m * ML.map_stride
                buf.f[rb] = 1.0
                buf.f[rb + 1 + _POINT_TYPE_INDEX[point.point_type]] = 1.0
                child_base = rb + 1 + _N_POINT_TYPES
                counts: dict[int, int] = {}
                for child in point.children:
                    ci = _POINT_TYPE_INDEX[child.point_type]
                    counts[ci] = counts.get(ci, 0) + 1
                for ci, c in counts.items():
                    buf.f[child_base + ci] = _clip01(c / 3.0)

        # ── Whole-map grid (visible every step, like the map screen) ─────
        act_map = run.map
        if act_map is not None:
            cache = self._map_grid_cache
            if cache is None or cache[0] is not act_map:
                cache = (act_map, _map_grid_block(act_map))
                self._map_grid_cache = cache
            gb = F("run.map.grid").start
            buf.f[gb:gb + cache[1].shape[0]] = cache[1]
            point = run.current_point
            if point is not None:
                if point is act_map.starting_point:
                    buf.f[F("run.map.meta").start] = 1.0
                elif point is act_map.boss_point or point is act_map.second_boss_point:
                    buf.f[F("run.map.meta").start + 1] = 1.0
                elif 1 <= point.row <= MAP_GRID_ROWS and 0 <= point.col < _MAP_WIDTH:
                    buf.f[gb + ((point.row - 1) * _MAP_WIDTH + point.col)
                          * MAP_GRID_NODE + MAP_GRID_NODE - 1] = 1.0

        # ── Event block ──────────────────────────────────────────────────
        event = request.event if request is not None and request.kind == DecisionKind.EVENT else None
        if event is not None:
            buf.f[F("event.present")] = 1.0
            idx = EVENT_INDEX.get(event.id)
            buf.i[I("event.ids")] = [oid(idx)]
            if event.page != "INITIAL":
                buf.f[F("event.page")] = 1.0
            opt_base = F("event.options").start
            opts = event.options
            for i in range(min(CHOICE_SLOTS, len(opts))):
                buf.f[opt_base + 2 * i] = 1.0
                if opts[i].locked:
                    buf.f[opt_base + 2 * i + 1] = 1.0

        # ── Shop block (positional; unstocked slots stay explicit PAD
        #    rows — write_rows never skips a slot, OBS_SCHEMA.md §2.2) ────
        shop = request.shop if request is not None and request.kind == DecisionKind.SHOP else None
        if shop is not None:
            entries = shop.card_entries
            rows = []
            for c in range(max(SHOP_CARD_SLOTS, len(entries))):
                entry = entries[c] if c < len(entries) else None
                if entry is None or not entry.is_stocked:
                    rows.append(([PAD], [0.0, 0.0, 0.0, 0.0]))
                else:
                    rows.append(([oid(CARD_INDEX.get(entry.card.id))], [
                        1.0,
                        _log1p_scale(entry.cost, SHOP_COST_LOG_DENOM),
                        1.0 if entry.enough_gold else 0.0,
                        1.0 if entry.on_sale else 0.0,
                    ]))
            buf.write_rows("shop.cards", rows, cap=SHOP_CARD_SLOTS, n_int=1, n_float=4, sort=False)

            entries = shop.relic_entries
            rows = []
            for r in range(max(SHOP_RELIC_SLOTS, len(entries))):
                entry = entries[r] if r < len(entries) else None
                if entry is None or not entry.is_stocked:
                    rows.append(([PAD], [0.0, 0.0, 0.0]))
                else:
                    rows.append(([oid(RELIC_INDEX.get(entry.relic.id))], [
                        1.0,
                        _log1p_scale(entry.cost, SHOP_COST_LOG_DENOM),
                        1.0 if entry.enough_gold else 0.0,
                    ]))
            buf.write_rows("shop.relics", rows, cap=SHOP_RELIC_SLOTS, n_int=1, n_float=3, sort=False)

            entries = shop.potion_entries
            rows = []
            for p in range(max(SHOP_POTION_SLOTS, len(entries))):
                entry = entries[p] if p < len(entries) else None
                if entry is None or not entry.is_stocked:
                    rows.append(([PAD], [0.0, 0.0, 0.0]))
                else:
                    rows.append(([oid(POTION_INDEX.get(entry.potion.id))], [
                        1.0,
                        _log1p_scale(entry.cost, SHOP_COST_LOG_DENOM),
                        1.0 if entry.enough_gold else 0.0,
                    ]))
            buf.write_rows("shop.potions", rows, cap=SHOP_POTION_SLOTS, n_int=1, n_float=3, sort=False)

            removal = shop.card_removal_entry
            if removal is not None and removal.is_stocked:
                buf.f[F("shop.removal")] = [
                    1.0,
                    _log1p_scale(removal.cost, SHOP_COST_LOG_DENOM),
                    1.0 if removal.enough_gold else 0.0,
                ]

        # ── Reward block ─────────────────────────────────────────────────
        rewards = request.rewards if request is not None and request.kind in (
            DecisionKind.REWARD_CARD, DecisionKind.REWARD_POTION,
        ) else None
        if rewards is not None and request.kind == DecisionKind.REWARD_CARD:
            cards = rewards.cards
            rows = []
            for c in range(max(REWARD_CARD_SLOTS, len(cards))):
                card = cards[c] if c < len(cards) else None
                # `reward.cards` is POSITIONAL (the action space picks a
                # reward by slot index), so an unresolvable id can't be
                # dropped from the list like the sorted blocks below — that
                # would shift every later slot into the wrong action index.
                # Treat it as an explicit PAD row IN PLACE instead, same as
                # an absent slot (card is None).
                if card is not None and card.id not in CARD_INDEX:
                    card = None
                rows.append(([PAD, PAD, PAD, PAD], [0.0, 0.0, 0.0, 0.0]) if card is None
                            else _run_card_row(card))
            buf.write_rows("reward.cards", rows, cap=REWARD_CARD_SLOTS, n_int=4, n_float=4, sort=False)
        # `reward.potion.*` is screen-scoped, not ask-scoped: the game shows
        # the full offer (card + potion + relic still pending) on EVERY
        # reward decision of a floor, not only the ask whose own sub-kind
        # matches that item (game dump `unseeded_20260807_005254/
        # decisions.jsonl` floor 2, decision_index 0 — the card ask — already
        # has `reward.potion.f == 1`; the old `kind == REWARD_POTION` gate
        # only lit it on the later dedicated potion ask). `rewards` here is
        # the SAME `CombatRewards` object the potion ask reads `.potion`
        # off of (see driver.py `_offer_rewards`: the single-card-group case
        # reuses one object across both asks), so reading it unconditionally
        # off `rewards` — instead of gating on `request.kind` — surfaces data
        # that was already present on the object, not a new source.
        if rewards is not None:
            potion = rewards.potion
            if potion is not None:
                buf.i[I("reward.potion.ids")] = [oid(POTION_INDEX.get(potion.id))]
                buf.f[F("reward.potion.f")] = 1.0
        # REWARD_RELIC (RunState.offer_relic / RelicReward, RunState.reward_
        # selector's "relic" seam, driver.py's `_offer`/`_offer_card_group`'s
        # sacrifice path): unlike REWARD_CARD/REWARD_POTION the offered item
        # lives on the DecisionRequest itself (`request.relic`), never on
        # `request.rewards` — a reward set can carry SEVERAL RelicRewards
        # (`CombatRewards.relics`, e.g. Lava Rock's two on the act-1 boss),
        # but each is surfaced as its own independent take-or-skip
        # DecisionKind.REWARD_RELIC screen (one relic at a time), same
        # shape as the single-potion pity-drop offer above — so this is a
        # width-1 identity+presence pair, mirroring `reward.potion` exactly,
        # not a multi-slot block like `reward.cards`.
        if request is not None and request.kind == DecisionKind.REWARD_RELIC:
            relic = request.relic
            if relic is not None:
                idx = RELIC_INDEX.get(relic.id)
                if idx is not None:
                    buf.i[I("reward.relic.ids")] = [oid(idx)]
                    buf.f[F("reward.relic.f")] = 1.0

        # ── Select block ─────────────────────────────────────────────────
        selecting = request is not None and request.kind in (
            DecisionKind.SELECT_CARDS, DecisionKind.SELECT_OPTION,
        )
        if selecting:
            # An unrecognized purpose string must route to the real
            # "_unknown" vocabulary entry (`vocab.json`'s persisted index,
            # e.g. 0), not a fixed `N_PURPOSES - 1` capacity-tail slot,
            # which would leave it silently invisible.
            unknown_idx = PURPOSE_INDEX.get("_unknown")
            purpose_idx = PURPOSE_INDEX.get(request.purpose, unknown_idx)
            buf.i[I("select.purpose.ids")] = [oid(purpose_idx)]
            buf.f[F("select.count")] = _clip01(request.count_remaining / 5.0)
            if request.skippable:
                buf.f[F("select.skippable")] = 1.0
            if request.kind == DecisionKind.SELECT_CARDS:
                # The ONLY sorted run-level block besides run.deck — the
                # hidden-information trap OBS_SCHEMA.md §2.6 documents:
                # `from_draw` candidates arrive in draw-pile order, and the
                # real game's own select screen does not show that order
                # either (see _sorted_candidate_order's docstring for the
                # source citation). sort=True makes the row order a pure
                # function of the candidate multiset.
                # Skip a candidate whose id is not in CARD_INDEX (same
                # invariant as run.deck above) — `_sorted_candidate_order`
                # applies the IDENTICAL filter before its own sort, so the
                # two never disagree about which candidates address a row.
                overflow["select.candidates"] = buf.write_rows(
                    "select.candidates",
                    [_run_card_row(c) for c in request.candidates if c.id in CARD_INDEX],
                    cap=MAX_SELECT_CANDIDATES, n_int=4, n_float=4, sort=True)

        # ── Overflow flags ───────────────────────────────────────────────
        for name, truncated in overflow.items():
            if truncated:
                buf.f[F(f"{name}.overflow")] = 1.0

        # ── Combat block (folded in under a "combat." prefix; PAD/zero
        #    outside combat, exactly as reset() left it) ──────────────────
        combat = request.combat if request is not None else None
        if combat is not None:
            write_combat_obs(combat, buf, self._card_obs, prefix="combat.")

        # Copies, not views (see this method's own docstring): a caller
        # holding a previous step's observation must never see it mutate
        # when this buffer is reset()+rewritten on the NEXT call.
        return {"f": buf.f.copy(), "i": buf.i.copy()}

    # ------------------------------------------------------------------

    def _info(self) -> dict[str, Any]:
        run = self._run
        info: dict[str, Any] = {
            "floor": run.total_floor,
            "act": run.act_index,
            "phase": self._request.kind.value if self._request is not None else "done",
        }
        if self._result is not None:
            info["is_success"] = self._result.victory
            info["hp_left"] = self._result.hp
            info["decisions"] = self._result.decisions
        # Episode-end only (termination above, truncation below — the step
        # that trips _max_steps is this episode's last observation-bearing
        # step either way): the `_count_behavior` tallies.
        if self._result is not None or self._steps >= self._max_steps:
            info["ep_end_turns"] = self._ep_end_turns
            info["ep_energy_unspent"] = self._ep_energy_unspent
            info["ep_card_offers"] = self._ep_card_offers
            info["ep_card_takes"] = self._ep_card_takes
            info["ep_rest_visits"] = self._ep_rest_visits
            info["ep_rest_heals"] = self._ep_rest_heals
            info["ep_rest_upgrades"] = self._ep_rest_upgrades
            info["ep_rest_visits_hihp"] = self._ep_rest_visits_hihp
            info["ep_rest_upgrades_hihp"] = self._ep_rest_upgrades_hihp
            info["ep_upgrades"] = self._ep_upgrades
            info["ep_removes"] = self._ep_removes
            info["ep_relics"] = self._ep_relics
            info["ep_elites_won"] = self._ep_elites_won
            info["ep_elites_fought"] = self._ep_elites_fought
            info["ep_potions_obtained"] = self._ep_potions_obtained
            info["ep_potions_used"] = self._ep_potions_used
            info["ep_potions_used_elite"] = self._ep_potions_used_elite
            info["ep_potions_used_boss"] = self._ep_potions_used_boss
            info["ep_potions_used_normal"] = self._ep_potions_used_normal
            info["ep_potions_expired"] = self._ep_potions_expired
            info["ep_potion_use_hp"] = self._ep_potion_use_hp
            info["ep_potion_v_at_use"] = self._ep_potion_v_at_use
            info["ep_potions_wasted"] = self._ep_potions_wasted
            info["ep_potions_bought"] = self._ep_potions_bought
            info["ep_potion_rewards_skipped"] = self._ep_potion_rewards_skipped
            info["ep_potion_rewards_forced"] = self._ep_potion_rewards_forced
            info["ep_potion_relic_picks"] = self._ep_potion_relic_picks
            info["ep_potion_holds"] = list(self._ep_potion_holds)
            info["ep_potions_discarded"] = self._ep_potions_discarded
            info["ep_potion_skips"] = list(self._ep_potion_skips)
            info["ep_hp_lost"] = self._ep_hp_lost
            info["ep_boss_hp_lost"] = self._ep_boss_hp_lost
            info["ep_card_offer_ids"] = dict(self._ep_card_offer_ids)
            info["ep_card_take_ids"] = dict(self._ep_card_take_ids)
            # The end-of-run deck census (eval.py --deck-hist). `run` is
            # bound at the top of this method and `self._run` is never
            # cleared on termination, so the deck here is the deck the
            # episode finished with.
            info["ep_final_deck"] = final_deck_histogram(run)
        return info

    def render(self) -> None:
        if self.render_mode != "human" or self._run is None:
            return
        run = self._run
        phase = self._request.kind.value if self._request is not None else "done"
        print(
            f"[{phase}] act {run.act_index + 1} floor {run.total_floor}  "
            f"HP {max(0, run.hp)}/{run.max_hp}  gold {run.gold}  "
            f"deck {len(run.deck)}  relics {len(run.relics)}"
        )


def masked_random_run_policy(rng: random.Random) -> Callable:
    """(env, obs, mask) -> action — uniform over the mask (baseline)."""

    def policy(env, obs, mask):
        return int(rng.choice(np.flatnonzero(mask)))

    return policy
