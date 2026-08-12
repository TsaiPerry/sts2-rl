"""STS2RunEnv — the full-run Gymnasium environment (a complete game run).

The engine side is `driver.py`'s RunDriver: the whole run written as plain
synchronous code that calls ``ask(DecisionRequest) -> int`` at every decision.
This env runs the driver on a **greenlet**; ``ask`` switches back to the env,
so every decision — map path, Neow/event options, shop purchases, rest
choices, post-combat reward picks, every combat action, and every
mid-resolution card selection (RL.md's "two-phase env") — surfaces as one
masked Gym step, fully on-policy.

Action space (flat Discrete, four blocks). T5a's brief scoped that lane to
this env's OBSERVATION half only; T5b (this pass) does the action-space work
— R4 (the per-candidate SELECT block, building on the
``_sorted_candidate_order`` helper T5a left behind) and Task A (widening the
potion-belt ceiling to its true worst case, fixing a live crash, not just an
undersized cap). Absolute sizes as built: N_ACTIONS = 243
(N_COMBAT_ACTIONS=121, CHOICE_SLOTS=16, MAX_SELECT_CANDIDATES=96,
MAX_POTION_SLOTS=10):

  [0 .. N_COMBAT_ACTIONS)         combat block — identical semantics to
                                 STS2FullCombatEnv (end turn / play h@e /
                                 potion p@e), sized for MAX_POTION_SLOTS=10
                                 belts (base 3 + Phial Holster's 1 + Potion
                                 Belt's 2 + Alchemical Coffer's 4, the true
                                 worst case — Task A): 61 + 10×6 = 121
  [CHOICE_BASE .. +CHOICE_SLOTS) generic choice slots: the i-th option of the
                                 current MAP / EVENT / SHOP / REST /
                                 REWARD_* / SELECT_OPTION decision (shop slot
                                 12 = leave, reward slot len(cards) = skip …
                                 exactly DecisionRequest.legal_actions()).
                                 During a skippable SELECT_CARDS, slot 0 =
                                 skip.
  [SELECT_BASE .. +MAX_SELECT_CANDIDATES)
                                 select-by-CANDIDATE-INDEX block (R4): action
                                 SELECT_BASE + i answers sorted candidate row
                                 i — ``_sorted_candidate_order(request)[i]``,
                                 the SAME canonical order the observation's
                                 ``select.candidates`` rows are written in
                                 (``ObsBuffer.write_rows(..., sort=True)``),
                                 so a row and the action that picks it always
                                 agree. Replaces the pre-R4 (card id,
                                 upgraded)-pair block, which collapsed two
                                 candidates differing only by enchantment /
                                 affliction / cost modifier onto one action
                                 and handed the driver the FIRST match — a
                                 documented approximation this fixes.
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
import random
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
from .driver import (
    POTION_ACTION_BASE,
    REST_HEAL,
    REST_SMITH,
    DecisionKind,
    DecisionRequest,
    RunDriver,
    RunResult,
)
from .events import ALL_EVENTS
from .full_env import (
    CARD_INDEX,
    MAX_COMBAT_CARDS,
    MAX_OBS_ID as _COMBAT_MAX_OBS_ID,
    MAX_POTION_ROWS,
    MAX_RELIC_ROWS,
    MONSTER_INDEX,
    # N_RELICS/RELIC_IDS: not used inside this module (MAX_RELIC_ROWS covers
    # everything the observation needs), but re-exported here on purpose —
    # test/test_vocab.py addresses them as `run_env.RELIC_IDS` /
    # `run_env.N_RELICS` (predating T5a), and an import binds the name in
    # this module's namespace exactly as a local definition would.
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
# migration exists). v2: capacity-padded frozen vocabularies (vocab.py) —
# dims are reserved capacities, so future content additions no longer bump
# this. v3: the shop's Colorless section (SHOP_CARD_SLOTS 5 → 7, shifting
# the relic/potion/removal segments and the SHOP decision's entry indices).
# v4: run.boss.identity + run.map.grid/meta (the act boss and the whole act
# map, matching what the game shows the player all act) — v3 checkpoints
# migrate losslessly via migrate_ckpt.py (checkpoints.migrate_checkpoint).
# v5: DecisionKind gained REWARD_RELIC (the take-or-skip relic offer,
# relic/_auto_keep), so PHASES = list(DecisionKind) is one wider and every run-
# obs index after the leading ("phase", N_PHASES) segment shifts.
# v6: the ACTION layout only — a MAX_POTION_SLOTS-wide out-of-combat belt block
# (potion/_any_time_usage). The observation is byte-identical to v5, so v5
# checkpoints migrate losslessly by growing the actor head alone
# (checkpoints.migrate_checkpoint_actions).
# v7 (OBS_SCHEMA.md, entity-obs-schema phase 1, T5a): the flat
# float Box observation is replaced by the {"f": Box(0,1), "i": Box(0,
# MAX_OBS_ID)} Dict contract — every one-hot/multi-hot vocabulary segment
# (potions, deck, relics, boss identity, event identity, shop/reward stock,
# select purpose/candidates) becomes an id row (R1 relic rows with real
# per-relic state instead of presence-only bits; R2 card-instance rows
# instead of a 2·N_CARDS histogram) plus R6 log1p-compressed gold/shop/
# removal prices in place of the old linear-clip scale. The ACTION layout
# (N_ACTIONS, CHOICE_BASE, SELECT_BASE, POTION_BASE, combat action block) was
# UNCHANGED by T5a's bump — the action-space follow-up this schema bump set
# up (R4, the per-candidate action block) is T5b, immediately below, and it
# is folded into the SAME v7 bump rather than an eighth version (nothing has
# been trained against v7 yet): the SELECT_CARDS block changes from a
# `2*N_CARDS`-wide `(card id, upgraded)`-pair block to a
# `MAX_SELECT_CANDIDATES`-wide candidate-INDEX block (`_sorted_candidate_
# order`'s canonical order — see that method and `_translate`'s SELECT_CARDS
# branch), and `full_env.MAX_POTION_ROWS` (and therefore `MAX_POTION_SLOTS`
# and every downstream action-layout constant) widens from 4 to 10 (Task A —
# the true worst-case belt, fixing a live `IndexError` crash, not just an
# undersized ceiling).
#
# THERE IS NO v6->v7 MIGRATION, unlike v3->v4's `migrate_checkpoint`: a flat
# `Box` and a two-leaf `Dict` are different Gym space TYPES, not a reshape of
# the same array, so there is no meaningful "grow the old weight matrix"
# operation to perform — every v6-and-earlier checkpoint requires a full
# retrain against v7, same as any other observation-space-type change. As a
# direct consequence, `checkpoints.migrate_checkpoint` (the run v3→v4 path)
# is now UNREACHABLE DEAD CODE: nothing can migrate INTO v7 through it, and
# nothing downstream of v7 will ever ask to migrate OUT of v3/v4/v5/v6 into a
# flat-Box target again. Left in place, not deleted — `checkpoints.py` is not
# this lane's file to edit (T6 owns the checkpoint-migration cleanup); this
# comment is the report of the gap, per the T5a brief.
# v8 (defect fix, 2026-08-02): this env's observation EMBEDS the combat
# block verbatim (`write_combat_obs(..., prefix="combat.")` above/below), so
# `full_env.OBS_SCHEMA_VERSION`'s 4->5 bump (the enemy row's new StatusIntent
# count float, full_env.py) silently widened `f_dim` here too (6 enemies x 1
# float = +6) without this constant moving — a version number that no longer
# names a single (f_dim, i_dim) contract is itself the defect, independent of
# whether `checkpoints.check_checkpoint`'s shape check happens to also catch
# a stale checkpoint. No layout code changed for v8; only this constant
# (and everything downstream that pins it) had drifted from what the env
# already emits. See `test_run_schema_version_matches_declared_dims` in
# test/test_run_obs_v4.py, which pins the (version, f_dim, i_dim) triple so a
# future embedded-width change can't repeat this silently.
# v9 (R3, full_env.OBS_SCHEMA_VERSION 5->6): per-enemy intent HISTORY
# (`enemy{e}.intent_history.f`, no `.ids` half) is folded in through the
# SAME embedding this env uses for the rest of the combat block, so it grows
# `f_dim` by `MAX_ENEMIES * MAX_INTENT_HISTORY * _N_ENEMY_HISTORY_SCALARS`
# (6 * 3 * 15 = 270) with `i_dim` unchanged — bumped explicitly this time
# (learned from v8's defect: a combat-side width change propagates here and
# must move this number in the SAME change, not be discovered later).
# v10 (SpireBot schema audit, docs/superpowers/specs/
# 2026-08-04-spirebot-schema-audit.md, Task 4): the audit walked every run
# v9 field (excluding the embedded `combat.*` block, covered by the v6->v7
# audit/bump) against the live game's readable API surface and found ZERO
# fields requiring DROP — every segment has either a direct C# read (KEEP),
# a stated proxy (REDEFINE), or a stated accumulation rule (ACCUMULATE). No
# segment is added or removed and no width changes (`f_dim`/`i_dim` both
# unchanged from v9); v10 is a pure version bump. The audit names two
# REDEFINE rows (`phase`, `select.purpose.ids`) but BOTH are
# documentation-only for this sim: their proxy language describes how the
# future C# `ObsBuilder` will SOURCE the value from live game state (screen-
# predicate dispatch for `phase`; mod-side session memory of "what action did
# I just dispatch" for `select.purpose`), not a change to what this Python
# env computes today — `run_obs_segments_f`'s `phase` one-hot (from
# `DecisionKind`) and `_build_obs`'s `select.purpose.ids` (from
# `DecisionRequest.purpose` via `PURPOSE_INDEX`) are both already exactly
# what the audit's proxy targets, so nothing here changes. Embedded combat
# block: v7 (see full_env.OBS_SCHEMA_VERSION's own v7 comment).
# v10 amendment (Task B, same day, addendum to the audit above): the audit's
# own "also noted" flagged a real content GAP outside its KEEP/DROP/REDEFINE/
# ACCUMULATE scope — `DecisionKind.REWARD_RELIC` (added at run-obs v5) never
# got a `reward.relic.ids/.f` block, so the policy could see THAT a relic
# offer exists (`phase`'s one-hot, the `CHOICE` take/skip mask) but not WHICH
# relic. Perry approved closing that gap AS PART OF v10 rather than a v11
# bump — v10 is brand-new and uncommitted, nothing has trained on it, and
# every doc/test/contract already reference 10, so amending in place avoids
# a same-day double bump. `reward.relic.f`/`reward.relic.ids` (width 1 each,
# a single scalar id + presence float, mirroring `reward.potion` exactly —
# not `reward.cards`' multi-slot block, because `RunState.offer_relic`/
# `DecisionRequest.relic` always offers exactly ONE relic at a time even when
# `CombatRewards.relics` holds several) are the only width change to EITHER
# half of this schema since v9: `f_dim`/`i_dim` each grow by 1.
#
# v11: `REWARD_CARD_SLOTS` 3 -> 4 (see the constant's own comment — Lasting
# Candy's appended Power option was being truncated out of an observation
# whose action stayed legal). `reward.cards.f`/`reward.cards.ids` each grow by
# one 4-wide row, so `f_dim`/`i_dim` each grow by 4. Unlike the v10 relic
# amendment above this is a real bump: v10 is no longer brand-new. There is no
# migration function — nothing on disk claims schema 10 (runs/ was cleared
# before the v6 curriculum), and `check_checkpoint` refuses a mismatch outright
# rather than guessing.
RUN_OBS_SCHEMA_VERSION = 11

# ── Fixed-size bounds ────────────────────────────────────────────────────
# Potion belt headroom. T5a Task 0 moved this from an independently-declared
# literal 4 to a reference onto full_env.MAX_POTION_ROWS — see that
# constant's own comment in full_env.py for the full citation (three
# belt-growing relics, not the one the earlier brief named).
#
# T5b (Task A): T5a kept the value at 4, deferring the true worst case (10)
# as out of scope for its lane (widening it grows N_ACTIONS). That deferral
# turned out to be a live CRASH, not just an undersized static ceiling: a
# single COMMON relic (Potion Belt, +2 slots) already grows the belt past 4,
# and `action_masks()` indexed past the end of the mask the first time it ran
# with 5 belt slots held (`IndexError: index 1385 is out of bounds for axis 0
# with size 1385`, reproduced and pinned by
# test_select_candidate_actions.py::test_potion_belt_grown_past_the_old_cap_does_not_crash_action_masks).
# Fixed by widening `full_env.MAX_POTION_ROWS` itself to 10 (the true worst
# case: base 3 + Phial Holster's 1 + Potion Belt's 2 + Alchemical Coffer's
# 4); this reference means `N_COMBAT_ACTIONS`/`CHOICE_BASE`/`SELECT_BASE`/
# `POTION_BASE`/`N_ACTIONS` all widen from that ONE source rather than a
# second hardcoded literal here.
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

# T5a brief §2.6: "Set MAX_SELECT_CANDIDATES = 96, matching MAX_COMBAT_CARDS:
# the largest candidate list a purpose can offer is bounded by 'a whole pile'
# or 'the whole deck'." The R4 census that would measure this properly is
# HELD on the user's instruction, so — like MAX_RELIC_ROWS and
# MAX_COMBAT_CARDS themselves — this is a static argument, not a measurement.
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
# T5b (Task A): MAX_POTION_SLOTS follows MAX_POTION_ROWS, which just grew
# 4 -> 10 (the true worst-case belt), so N_COMBAT_ACTIONS/CHOICE_BASE/
# SELECT_BASE/POTION_BASE/N_ACTIONS all widen with it automatically — never
# hardcode these widths, they must always be recomputed from the sizing
# constants above.
N_COMBAT_ACTIONS = combat_action_count(MAX_POTION_SLOTS)
CHOICE_BASE = N_COMBAT_ACTIONS
SELECT_BASE = CHOICE_BASE + CHOICE_SLOTS
# T5b (R4): the select-by-card-id-pair block (2*N_CARDS wide) is replaced by
# a candidate-INDEX block, MAX_SELECT_CANDIDATES wide — see `_translate`'s
# SELECT_CARDS branch and `_sorted_candidate_order` below.
POTION_BASE = SELECT_BASE + MAX_SELECT_CANDIDATES
# The out-of-combat belt (driver.POTION_ACTION_BASE). Its own block rather
# than extra slots on each decision: an AnyTime potion is usable from every
# screen, and a shop already offers 15 of CHOICE_SLOTS' 16.
N_ACTIONS = POTION_BASE + MAX_POTION_SLOTS

# ── Stable vocabularies (frozen append-only + capacity-padded; vocab.py) ──
# RELIC_IDS/RELIC_INDEX/N_RELICS: imported from full_env rather than
# recomputed here. Both modules used to call frozen_ids("relics", ALL_RELICS)
# independently — harmless (same persisted vocab.json key, idempotent), per
# full_env's own module comment — but importing one is simpler than keeping
# two call sites that have to agree by construction rather than by
# reference. full_env is already imported for MAX_RELIC_ROWS/CARD_INDEX/…,
# so this adds no new dependency.

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
    # Non-declinable selection screens (Toolbox.cs:28, ChoicesParadox.cs:46):
    # the sim expresses "not skippable" as membership in
    # driver.SKIPPABLE_PURPOSES, so these needed their own purpose rather than
    # reusing "obtain". Appended, never reordered — the registry is frozen.
    "choose_a_card",
    # ...and its canSkip:true twin, the generator potions' screen
    # (CardSelectCmd.cs:216-261 `FromChooseACardScreen(..., canSkip: true)`).
    # Skippability is per-screen in the source, so the same screen shape needs
    # both purposes here.
    "choose_a_card_optional",
    # Kifuda's non-cancelable MinSelect-0 enchant screen (Kifuda.cs:26-29,
    # driver.SKIPPABLE_PURPOSES) — registered so it doesn't fall into the
    # shared "_unknown" bucket like the pre-existing "transform_optional"
    # (Claws.cs) currently does; see this round's report for that gap.
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

# T5a brief §1: full_env.MAX_OBS_ID is computed over the vocabularies the
# COMBAT observation touches. The run observation additionally touches
# events and purposes (and, positionally, relics/potions/monsters/cards —
# already in full_env's set) directly, plus the embedded combat sub-block
# touches powers — so this is computed independently rather than importing
# full_env's, per the brief's explicit instruction. It comes out IDENTICAL
# to full_env.MAX_OBS_ID (640, from the cards vocabulary) because cards is
# the largest capacity in EITHER set and events (96) / purposes (24) don't
# come close — reported here rather than assumed, per the brief.
MAX_OBS_ID = max(
    vocab_capacity(kind) for kind in (
        "cards", "relics", "powers", "monsters", "potions",
        "afflictions", "enchantments", "events", "purposes",
    )
)
# Fix-pass correction (review item 5): a bare module-level `assert` is a
# no-op under `python -O` (assertions are stripped), silently disarming this
# check exactly where it matters most (a divergence would corrupt every
# consumer of either constant). Raise explicitly instead so the check is
# real regardless of how the interpreter is invoked.
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
# exceeds a few hundred.
#
# Fix-pass correction (review item 2): the original 300/3000 pair moved R6's
# own defect rather than removing it — a review measured every value in
# {300, 500, 1000, 1500, 3000} reading EXACTLY 1.0 on the fine channel
# (saturating at the fine denom itself, same shape as the `gold/100` bug R6
# replaces), and {3000, 4000, 5000, ...} all reading 1.0 on the coarse
# channel too, so a genuinely hoarding run had NO resolution at all above
# 3000g on either channel.
#
# Retuned so the fine channel keeps resolving further into a normally-
# shopping player's range (800, not 300, so 300g and 500g no longer collide
# on the fine channel alone) and the coarse channel resolves the WHOLE
# comment-defined hoarding ceiling ("a few thousand") with headroom: at
# 3000g the coarse channel reads ~0.89, not 1.0, and 5000g still resolves at
# ~0.95 — both denominators are reasoned defaults (no act-0 census reaches
# these balances; see OBS_SCHEMA.md §7), chosen so neither channel plateaus
# inside the range this module's own comments claim to cover, verified by
# test_gold_realistic_band_resolves_without_plateau.
GOLD_LOG_FINE_DENOM = 800.0
GOLD_LOG_COARSE_DENOM = 8000.0

# Shop/removal prices (shop.py): card slots top out around 150-190g (a rare
# Colorless card with the ±5% jitter), relic slots around 235-320g (a Rare
# relic's `merchant_cost` with ±15% jitter), potion slots around 50-110g —
# all comfortably bounded. Card removal (`75 + 25 × removals_used`,
# shop.py:419-436) is the one genuinely UNBOUNDED quantity here, climbing
# without limit over a long, removal-heavy run.
#
# Fix-pass correction (review item 2): the old denom (2000) technically
# didn't collide the two named test points, but a review measured the
# realistic 40-320g item-price band spreading only 27% of [0,1], all bunched
# in the upper half — the comment's claim that this "resolves the
# shopping-relevant range" was not true. A SINGLE shared log1p denom cannot
# spread an ~8x price ratio across all of [0,1] while ALSO keeping the
# unbounded removal cost resolvable well past 800g — that is a hard
# mathematical tradeoff of the log1p family (the ratio between any two
# fixed points is invariant to the denom; only the overall scale moves), not
# a tuning oversight. 900 is the reasoned middle ground: it noticeably
# improves the item-price spread (~30%, verified by
# test_shop_cost_realistic_band_spreads_more_than_the_old_defect) while
# still keeping 800g comfortably short of saturation (~0.98, not 1.0), so a
# heavily-removal run still resolves past the named 500-vs-800 pair.
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
    ``"combat."`` (T5a brief §1) — one ``ObsLayout``, one ``ObsBuffer``,
    exactly as ``write_combat_obs``'s own docstring specifies for this
    lane."""
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
    clipped. UNCHANGED (T5a brief §2.2) — not touched by the v7 rewrite."""
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

    T5b (Task B): this used to be a hand-kept duplicate of
    ``full_env._pile_card_row``'s row shape — a T5a brief contradicted
    itself (asking that lane to "reuse `_pile_card_row`" while restricting
    its `full_env.py` edits to Task 0 only), so T5a correctly left the
    duplication in place and reported the conflict rather than resolving it
    by violating its own ownership boundary. T5b owns `full_env.py` for this
    task, so the row-shape logic is promoted there
    (``full_env.card_instance_row``) and both envs call the ONE function —
    R2's whole premise is one row shape everywhere, and two encoders that
    must agree by construction is exactly the drift this project keeps
    getting bitten by.

    The one genuine divergence (OBS_SCHEMA.md §2.3) is expressed as
    ``card_instance_row``'s explicit ``effective_cost`` parameter rather
    than a second code path: out of combat there is no hook pipeline
    (``previews.preview_card_energy_cost`` needs a live ``CombatState``) to
    run cost modifiers through, so this passes the card's plain printed
    ``energy_cost`` — which is also what the game's own out-of-combat
    screens (deck view, shop, reward) show.

    ``pile_id`` is always PAD (0): there is no pile concept outside combat —
    never invent a new pile id for a run-side block. Fix-pass correction
    (review item 7): this used to take an unused ``pile_id: int = PAD``
    parameter — every one of its 4 call sites relied on the default — so it
    is hardcoded here instead of threaded through as dead flexibility.
    Round-4 fix: ``canonical_energy_cost`` (printed, modifier-immune), not
    ``energy_cost`` — see ``full_env._pile_card_row``'s docstring for why
    the plain getter is the wrong accessor even out of combat (a run-side
    Card object is fresh per screen today, but the two callers should not
    silently diverge in which accessor is "the printed cost")."""
    return card_instance_row(card, PAD, card.canonical_energy_cost)


def _hp_potential(ratio: float, knee: float, low_share: float) -> float:
    """Concave HP potential: `low_share` of the value lives in [0, knee]
    (danger zone — HP is precious), the rest in [knee, 1] (HP is currency
    to spend on elites). Piecewise-linear, phi(0)=0, phi(1)=1."""
    if ratio <= knee:
        return low_share * ratio / knee
    return low_share + (1.0 - low_share) * (ratio - knee) / (1.0 - knee)


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
        floor_reward: float = 1.0,
        act_reward: float = 0.0,
        floor_rewards_by_act: "tuple[float, ...] | None" = None,
        reward_upgrade: float = 0.0,
        reward_remove: float = 0.0,
        reward_elite: float = 0.0,
        reward_relic: float = 0.0,
        rest_heal_mask_above: float | None = None,
        potion_potential_scale: float = 0.0,
        deck_random_prob: float = 0.0,
        deck_random_cards: tuple[int, int] = (4, 14),
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
        # v8 HP-economy (plan Task 1): concave HP potential shaping. Default
        # OFF (scale 0.0) — see `_hp_potential` for the piecewise-linear
        # curve shape.
        self._hp_potential_scale = hp_potential_scale
        self._hp_potential_knee = hp_potential_knee
        self._hp_potential_low_share = hp_potential_low_share
        self._floor_reward = floor_reward
        self._act_reward = act_reward
        # v7 reward terms (plan Task 6). All default OFF. Accepted wrinkles,
        # by design: an upgraded card taken from a reward counts as
        # +upgrade_level upgrades (it IS acquired power); a transform
        # (remove+add in one step) nets zero removals. (v8 Task 2 revises the
        # old "a potion SOLD counts as used" wrinkle below: `_ep_potions_used`
        # now counts only actual drinks — a belt decrease with no matching
        # drink answer, e.g. an event trading a potion away, still moves the
        # v8 ledger but no longer inflates this count. There is no shop-sell
        # feature in this sim; "sold" here means any non-drink belt loss.)
        self._floor_rewards_by_act = (
            tuple(floor_rewards_by_act) if floor_rewards_by_act is not None else None
        )
        self._reward_upgrade = reward_upgrade
        self._reward_remove = reward_remove
        self._reward_elite = reward_elite
        # v8 relic reward (plan Task 3): +reward_relic per relic gained,
        # measured the same way as the deck-length delta above (out-of-combat
        # decisions only). Default OFF.
        self._reward_relic = reward_relic
        # v8 curriculum mask (plan Task 4): above this hp/max_hp ratio at a
        # rest site, REST_HEAL's mask bit is cleared IF at least one other
        # rest action is legal — forces generation of upgrade-path data
        # instead of letting the policy always top off. Default None (off);
        # a mask knob, not a reward term, so it is deliberately NOT stamped
        # into checkpoints (`checkpoints.py`) — see `action_masks` below.
        self._rest_heal_mask_above = rest_heal_mask_above
        # v8 potion ledger (plan Task 2): potion_potential_scale * (potions
        # held now - potions held before), off the SAME belt-count delta v7
        # Task 6c already tracks below. No terminal term — a potion still on
        # the belt at episode end keeps its +k (that asymmetry against the
        # -k a drink/loss pays IS the hoarding-vs-spending weighing bar);
        # `_ep_potions_expired` just tallies the held count at episode end
        # for visibility, with no reward attached. Default OFF.
        self._potion_potential_scale = potion_potential_scale
        # v7 deck randomization (plan Task 9): card-exposure domain
        # randomization — with probability deck_random_prob an episode
        # starts with 4..14 extra reward-pool cards appended to the starter
        # deck, so every card gets combat playtime regardless of drafting.
        self._deck_random_prob = deck_random_prob
        self._deck_random_cards = tuple(deck_random_cards)
        self._max_steps = max_steps
        self.render_mode = render_mode
        # Harvest hook (phase 3, Task 4): threaded straight to the
        # `RunDriver` this env constructs per-episode inside `reset()`'s
        # `_drive` closure. The env is the only owner of that construction
        # (the driver runs on a private greenlet `reset()` starts), so a
        # caller outside this module — e.g. `harvest.py` — has no other way
        # to observe `RunDriver.on_combat_start` (locked decision 4) firing;
        # exposing it here is the smallest seam that doesn't require
        # subclassing or monkeypatching a production object.  `None` (the
        # default) means zero behavior change, same as the driver's own
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
        # v7 deck randomization — BEFORE the driver greenlet starts, so the
        # extra cards exist from the first decision on. The prob > 0.0
        # short-circuit is load-bearing (branch_prob precedent,
        # curriculum_env.py:238-244): the default env must draw no rng here.
        if self._deck_random_prob > 0.0 and self._rng.random() < self._deck_random_prob:
            self._randomize_deck(self._run)
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
        # v7 tallies (plan Task 6): counted always, rewarded only when the
        # matching reward_* kwarg is non-zero.
        self._ep_upgrades = 0
        self._ep_removes = 0
        # v8 (plan Task 3): relics gained tally, alongside the deck deltas.
        self._ep_relics = 0
        # v8 (plan Task 1): combat sloppiness tally, independent of the
        # hp_potential_scale shaping (which can be off while this stays on).
        self._ep_hp_lost = 0
        self._ep_elites_won = 0
        self._ep_potions_obtained = 0
        self._ep_potions_used = 0
        # v8 potion ledger (plan Task 2): USE classification + timing.
        # `_ep_potions_used_elite/boss/normal` sum to `_ep_potions_used` (now
        # a drinks-only count, see the __init__ comment); `_ep_potion_use_hp`
        # is a running SUM of hp/max_hp at each drink (eval divides by uses);
        # `_ep_potions_expired` is overwritten every step with the CURRENT
        # held count, so it lands on the belt count at whatever step turns
        # out to be the episode's last — no terminal-only special case.
        self._ep_potions_used_elite = 0
        self._ep_potions_used_boss = 0
        self._ep_potions_used_normal = 0
        self._ep_potions_expired = 0
        self._ep_potion_use_hp = 0.0
        self._elite_reward_key: tuple[int, int] | None = None
        # v7 per-card exposure tallies (plan Task 8): card CLASS name (unique
        # per card class, unlike display ids) -> count. Eval-only — never in
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
            )
            return driver.play()

        self._glet = greenlet.greenlet(_drive)
        self._switch(None)   # run until the first decision
        # Baselines for the v7 deck/belt deltas — taken AFTER the driver runs
        # to the first decision (the run is set up, Neow pending): deck and
        # belt are their true episode-start selves here.
        self._deck_upgrade_base = sum(c.upgrade_level for c in run.deck)
        self._deck_len_base = len(run.deck)
        self._belt_base = sum(1 for p in run.potions if p is not None)
        # v8 (plan Task 3): relic count baseline. Taken here, same as the
        # deck/belt baselines, so the starting relic (e.g. Burning Blood) is
        # already counted and never fires the reward.
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

    def step(self, action: int):
        assert self._run is not None, "call reset() before step()"
        run = self._run
        request = self._request
        self._steps += 1

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
            self._count_behavior(request, answer)
            self._switch(answer)
        else:
            hp_before, floor_before, act_before = run.hp, run.total_floor, run.act_index
            max_hp_before = run.max_hp
            elites_before = self._ep_elites_won

        self._ep_hp_lost += max(0, hp_before - run.hp)
        reward = self._hp_reward_scale * (min(run.hp, run.max_hp) - min(hp_before, run.max_hp)) / max(1, run.max_hp)
        # v8 HP-economy (plan Task 1): concave potential-based shaping, each
        # ratio measured against its OWN step's max_hp (before-ratio uses
        # max_hp_before, after-ratio uses the post-step max_hp) so a max-HP
        # gain can't fire this term backwards. Death terminal: hp=0 -> phi=0,
        # no special case needed (the piecewise formula already gives 0).
        ratio_before = min(hp_before, max_hp_before) / max(1, max_hp_before)
        ratio_after = min(run.hp, run.max_hp) / max(1, run.max_hp)
        reward += self._hp_potential_scale * (
            _hp_potential(ratio_after, self._hp_potential_knee, self._hp_potential_low_share)
            - _hp_potential(ratio_before, self._hp_potential_knee, self._hp_potential_low_share)
        )
        if self._floor_rewards_by_act is not None:
            act_i = max(0, min(run.act_index, len(self._floor_rewards_by_act) - 1))
            reward += self._floor_rewards_by_act[act_i] * (run.total_floor - floor_before)
        else:
            reward += self._floor_reward * (run.total_floor - floor_before)
        reward += self._act_reward * (run.act_index - act_before)
        reward += self._reward_elite * (self._ep_elites_won - elites_before)

        terminated = self._result is not None
        if terminated:
            if self._result.victory:
                reward += self._reward_win + self._win_hp_bonus * (
                    self._result.hp / max(1, self._result.max_hp)
                )
            else:
                reward += self._reward_loss
        truncated = (not terminated) and self._steps >= self._max_steps

        # v7 deck/belt deltas — measured only between decisions with no live
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
            self._relic_len_base = relics_now
        belt_now = sum(1 for p in run.potions if p is not None)
        if belt_now > self._belt_base:
            gained = belt_now - self._belt_base
            self._ep_potions_obtained += gained
            # v8 potion ledger (plan Task 2): +k per potion picked up. No
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
            if request is not None and answer >= POTION_ACTION_BASE:
                self._ep_potions_used += lost
                use_hp_ratio = min(hp_before, max_hp_before) / max(1, max_hp_before)
                self._ep_potion_use_hp += use_hp_ratio * lost
                room = None
                if (request.kind == DecisionKind.COMBAT
                        and request.combat is not None):
                    room = request.combat.room_type
                if room == RoomType.ELITE:
                    self._ep_potions_used_elite += lost
                elif room == RoomType.BOSS:
                    self._ep_potions_used_boss += lost
                else:
                    self._ep_potions_used_normal += lost
        self._belt_base = belt_now
        # Overwritten every step with the CURRENT held count, so whichever
        # step turns out to be the episode's last (`_info` gates on that same
        # terminated-or-truncated condition) leaves this at the right value —
        # no separate terminal-only branch needed.
        self._ep_potions_expired = belt_now

        return self._build_obs(), float(reward), terminated, truncated, self._info()

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
        # v7 elite tally: any request carrying a rewards screen from an elite
        # room means the elite was beaten; dedupe per room like rest visits
        # (the rewards screen re-asks per item taken).
        rewards = getattr(request, "rewards", None)
        if rewards is not None and rewards.room_type == RoomType.ELITE:
            key = (request.run.act_index, request.run.total_floor)
            if key != self._elite_reward_key:
                self._elite_reward_key = key
                self._ep_elites_won += 1
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
            # v7 per-card exposure (plan Task 8): tally every offered card,
            # and the taken one, by class name.
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
            if answer == REST_HEAL and not self._rest_healed_here:
                self._rest_healed_here = True
                self._ep_rest_heals += 1
            elif answer == REST_SMITH and not self._rest_upgraded_here:
                self._rest_upgraded_here = True
                self._ep_rest_upgrades += 1

    def close(self) -> None:
        self._kill_driver()
        super().close()

    # ------------------------------------------------------------------
    # Action translation / masking. T5b (R4): the SELECT_CARDS branches of
    # both methods below are the only part of this section the v7
    # observation rewrite's action-space follow-up actually changes — see
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
        legal = request.own_actions()
        if kind == DecisionKind.COMBAT:
            return action if action < N_COMBAT_ACTIONS and action in legal else None
        if kind == DecisionKind.SELECT_CARDS:
            if request.skippable and action == CHOICE_BASE:
                return len(request.candidates)
            # R4: action SELECT_BASE + i answers sorted candidate row i —
            # ``_sorted_candidate_order(request)[i]``, the SAME order the
            # observation's ``select.candidates`` rows are written in. `order`
            # already reflects the cap (it never returns more entries than
            # rows actually exist — see that method's docstring), so an `i`
            # past `len(order)` correctly falls through to illegal (None),
            # matching how the old code let the reserved-capacity tail fall
            # through.
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
        # Bound, don't crash (fix-pass review item 2): this used to write one
        # mask cell per ACTUAL belt slot `request.potion_actions()` yields,
        # uncapped, so a belt grown past MAX_POTION_SLOTS indexed past the
        # end of this array (a live IndexError — Task A's own regression,
        # just at a higher threshold). Agrees with the SELECT branch's
        # policy below: truncate rather than assert, since a crash
        # mid-training is worse than an unreachable slot. The loud signal
        # for this overflow already lives on the observation side —
        # `_build_obs`'s `run.potions` block shares this SAME
        # MAX_POTION_SLOTS cap, so an overgrown belt also fires
        # `run.potions.overflow` there — unlike the SELECT branch, this one
        # needs no separate signal of its own.
        for answer in request.potion_actions():
            slot = answer - POTION_ACTION_BASE
            if slot < MAX_POTION_SLOTS:
                mask[POTION_BASE + slot] = True
        legal = request.own_actions()
        if kind == DecisionKind.COMBAT:
            mask[legal] = True
        elif kind == DecisionKind.SELECT_CARDS:
            # R4: one mask bit per candidate row `_sorted_candidate_order`
            # actually addresses — never more than MAX_SELECT_CANDIDATES,
            # since that helper already truncates to match the observation.
            # OBS_SCHEMA.md §2.3/this method's own history: overflow here is
            # more serious than elsewhere in this project — a truncated
            # OBSERVATION block only degrades the view, but a truncated
            # ACTION block makes a real, choosable candidate unclickable,
            # which the actual game never does. So this never asserts on
            # overflow (a crash mid-training would be worse); the loud
            # signal is `select.candidates.overflow` in the observation
            # (`_build_obs`, `buf.write_rows(..., cap=MAX_SELECT_CANDIDATES)`)
            # firing from the SAME truncated order, which is a genuine, if
            # remote, ACTION-SPACE fidelity narrowing, not just an
            # observation one.
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
            # v8 (plan Task 4): rest_heal_mask_above curriculum mask. Only
            # at a rest-site decision, only above the HP-ratio threshold,
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
    # T5b (R4): the candidate-index action block (`_translate`/`action_masks`
    # above) addresses ``select.candidates``' SORTED row order and translates
    # a chosen row back to the true candidate index through this method. This
    # is the single source of that order — the observation writer below sorts
    # via ``ObsBuffer.write_rows(..., sort=True)``, and this method computes
    # the IDENTICAL key independently, so the two can never silently
    # disagree.
    # ------------------------------------------------------------------

    def _sorted_candidate_order(self, request: DecisionRequest) -> list[int]:
        """The true candidate indices (into ``request.candidates``), in the
        SAME canonical order ``select.candidates``' rows are written in —
        and, since ``write_rows`` TRUNCATES to ``MAX_SELECT_CANDIDATES``
        after sorting, this returns EXACTLY the rows that exist, never more.

        Fix-pass correction (review item 1): this used to return every
        candidate index uncapped, so past ``MAX_SELECT_CANDIDATES`` it
        described rows ``write_rows`` had already truncated away — the next
        lane (T5b, R4) builds one action-mask bit per entry this method
        returns, so an uncapped helper would enable actions for candidate
        rows that are all-PAD in the policy's own observation (the exact
        observation/action seam this env's split into two lanes exists to
        protect). Also mirrors ``select.candidates``' own guard (review item
        3): a candidate whose card id cannot be resolved to a vocab index
        never becomes a row there, so it must never appear in this order
        either — computed with the identical ``card.id in CARD_INDEX``
        predicate, in the same position (before the sort), for the same
        reason ``write_rows(sort=True)`` sorts before truncating (see that
        method's own docstring): the retained set must be a deterministic
        function of the candidate multiset alone, not of input order.

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
        fine per the brief: any canonical, order-independent sort closes the
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
        # Round-6 obs-parity fix: `RunState.potions` is a pre-combat
        # SNAPSHOT — `RunState.finish_combat` only copies the live
        # `combat.player.potions` back into it once the combat ENDS (see
        # `run.py:finish_combat`'s `self.potions = list(combat.player.
        # potions)`). The game has no such split (one Player, one belt), so
        # a potion drunk MID-combat (e.g. Skill Potion's card-add, surfaced
        # here as a SELECT_CARDS decision) empties its game-side belt slot
        # immediately, while this block used to keep reading the stale
        # RunState list until the combat's `finish_combat` call — confirmed
        # against seed 89U21BV1TZ act 0 floor 15 (game dump: belt slot 2
        # already empty from Combat decision 4 onward; sim dump: still
        # filled for the whole rest of the combat). Read the LIVE belt off
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
        # Fix-pass correction (review item 3): a card whose id is not in
        # CARD_INDEX is SKIPPED, matching the pre-v7 code's `if idx is not
        # None` guard — `_run_card_row` computes its floats straight off the
        # card object regardless of id resolution, so writing it anyway
        # would produce a row with a PAD id but live floats, violating
        # OBS_SCHEMA.md §2.1's "PAD means id==0 AND all-zero floats"
        # invariant. Unreachable today (CARD_INDEX is built from the same
        # registry every real Card's id comes from).
        overflow["run.deck"] = buf.write_rows(
            "run.deck", [_run_card_row(c) for c in run.deck if c.id in CARD_INDEX],
            cap=MAX_DECK_ROWS, n_int=4, n_float=4, sort=True)

        # ── Relics (R1, acquisition order — what the relic bar shows) ────
        # Fix-pass correction (review item 3): skip a relic whose id is not
        # in RELIC_INDEX, rather than writing a PAD-id row with `relic_row`'s
        # live counter/flag floats (same invariant as run.deck above).
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
                # Fix-pass correction (review item 3, "the worst" case): an
                # unrecognised monster class must be SKIPPED, not appended
                # as a PAD row — appending would consume one of only
                # MAX_BOSS_IDS slots and shift every later real id into a
                # row it doesn't belong in. Unreachable today (MONSTER_INDEX
                # is built from the same registry every boss draws from).
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
                # Fix-pass correction (review item 3): `reward.cards` is
                # POSITIONAL (the action space picks a reward by slot
                # index), so an unresolvable id can't be dropped from the
                # list like the sorted blocks below — that would shift
                # every later slot into the wrong action index. Treat it as
                # an explicit PAD row IN PLACE instead, same as an absent
                # slot (card is None).
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
            # Bug fix (T5a): the pre-v7 code fell back to a fixed index
            # `N_PURPOSES - 1` (the CAPACITY tail, a dead padded one-hot
            # slot — vocab.json's actual "_unknown" entry sits at whatever
            # index the persisted vocabulary gave it, e.g. 0, not 23) for
            # any unrecognized purpose string, so an unrecognized purpose
            # was silently invisible rather than routed to the real
            # "_unknown" bucket the vocabulary defines for exactly this.
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
                # Fix-pass correction (review item 3): skip a candidate
                # whose id is not in CARD_INDEX (same invariant as
                # run.deck above) — `_sorted_candidate_order` applies the
                # IDENTICAL `card.id in CARD_INDEX` filter before its own
                # sort, so the two never disagree about which candidates
                # address a row at all.
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
            info["ep_upgrades"] = self._ep_upgrades
            info["ep_removes"] = self._ep_removes
            info["ep_relics"] = self._ep_relics
            info["ep_elites_won"] = self._ep_elites_won
            info["ep_potions_obtained"] = self._ep_potions_obtained
            info["ep_potions_used"] = self._ep_potions_used
            info["ep_potions_used_elite"] = self._ep_potions_used_elite
            info["ep_potions_used_boss"] = self._ep_potions_used_boss
            info["ep_potions_used_normal"] = self._ep_potions_used_normal
            info["ep_potions_expired"] = self._ep_potions_expired
            info["ep_potion_use_hp"] = self._ep_potion_use_hp
            info["ep_hp_lost"] = self._ep_hp_lost
            info["ep_card_offer_ids"] = dict(self._ep_card_offer_ids)
            info["ep_card_take_ids"] = dict(self._ep_card_take_ids)
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
