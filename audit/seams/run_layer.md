# Engine seam: `run_layer`

**STATUS: AUDITED 2026-08-03** (Phase 2 of the systems-tier campaign).
`audit/records/seam/run_layer.json` carries 14 steps + 10 guards, rollup
verdict `gap` (0 invalid under `harness.py validate`; 0 MISSING/OUT-OF-RANGE
under `citation_check.py`). Three live/dormant gaps filed, all with executed
witnesses in `audit/tools/run_layer_probes.py`:

- **`run_layer/discovery_order` (guard G6, LIVE).** `RunManager.
  ShouldApplyTutorialModifications()` defaults `true` for every ordinary,
  non-test, Standard-mode run (no player-count or first-run check despite its
  name and its own XML summary) and gates `ActModel.
  ApplyDiscoveryOrderModifications`, which overrides an act's rolled boss (and
  other encounters, per-act) to the first one the profile's
  `UnlockState.HasSeenEncounter` has not yet seen. The sim has zero functional
  references to this mechanism anywhere — `run.py`'s module docs disclose the
  omission, but the individual comment justifying it ("tutorial mods are off
  for real runs") is wrong about *why* it is safe; it is not tutorial-only.
- **`run_layer/starting_relic_after_obtained_order` (guard G7, dormant).** The
  game fires a starting relic's `AfterObtained` *after* `RunManager.
  GenerateRooms`; the sim's `add_relic` fires it *before*
  `_generate_all_act_rooms`. Dormant because Ironclad's only starting relic
  (Burning Blood, the only one reachable in this Ironclad-only sim) has no
  `AfterObtained` override.
- **`run_layer/*` (no new mechanism id — a HANDOFF, guard G8).** Confirmed
  *where* the already-filed, already-LIVE `encounter/_selection_rng_fallback`
  family's root cause lives: `RunState.__init__`'s `string_seed` parameter
  defaults to `None`, the RL training env files never override it, and only
  the conformance driver does. The pass-through logic itself
  (`create_combat`'s `encounter_selection_rng`) is faithful; the consequence
  for content that draws from it is that family's problem, matched under Rule
  3, not re-filed here.

See the report this task filed
(`p2-runlayer-report.md`, in the campaign's scratch directory) for every
step/guard, every witness, and the correction below.

## Scope

**Claims:** the run orchestration singleton (`RunManager`) and the contract it
and every other run-scoped object implements (`IRunState`), plus the one
small run-scoped flags bag that carries real (if narrow) gameplay state
(`ExtraRunFields`).

This seam is **deliberately thin.** Every other "systems tier" seam wired in
this task peels a specific subject off the run layer: `RunState.cs` itself
(the `IRunState` implementation) is already claimed by `hook_dispatch`
(`IterateHookListeners`); `RelicGrabBag.cs` and `RunRngSet.cs` are claimed by
`relic_pools` and `rng_streams`; `CardCreationFlags`/`CardCreationOptions`/
`CardCreationSource`/`CardRarityOddsType.cs` are claimed by `rewards`
(overruling this task's own brief — see below); rooms/map generation is
`rooms_and_map`'s. What is left after every neighbouring seam takes its
subject really is just the orchestrator and its contract.

**Does NOT claim (and which seam does):**
- `src/Core/Runs/RunState.cs` — `hook_dispatch` (already claimed before this
  task; verified in `SEAM_SOURCES["hook_dispatch"]`).
- `src/Core/Runs/RelicGrabBag.cs` — `relic_pools`.
- `src/Core/Runs/RunRngSet.cs` — `rng_streams`.
- `src/Core/Runs/CardCreationFlags.cs`, `CardCreationOptions.cs`,
  `CardCreationSource.cs`, `CardRarityOddsType.cs` — `rewards`. **This
  overrules the P1-T2 brief's own controller-analysis**, which filed these
  four under `run_layer` because they live in the `Runs/` folder. On reading
  them, all four are ported *inside* `sts2_rl/rewards.py` (the
  `RarityOddsType`/`CardCreationSource`/`CardCreationFlags`/
  `CardCreationOptions` classes), not `run.py` — their subject is reward card
  generation, not run orchestration, and the game's folder layout does not
  determine seam ownership (the same principle `RelicGrabBag.cs`/
  `RunRngSet.cs` already establish by living in `Runs/` while being claimed
  by `relic_pools`/`rng_streams`).
- `src/Core/Commands/PlayerCmd.cs` — the brief also suggested folding this
  (plus `Cmd.cs`) into `run_layer` as part of the `commands_remainder`
  decision. `PlayerCmd.cs` is **already claimed by `creature_card_cmds`**
  (verified in `SEAM_SOURCES["creature_card_cmds"]`, present since that seam
  was audited) — the brief's own list of "seven files already claimed by
  existing seams" undercounts by missing this one. Not double-claimed here.
- `src/Core/Commands/Cmd.cs` — **overruling the brief's suggestion to fold
  this into `run_layer`.** On inspection `Cmd.cs` is nothing but
  Godot scene-tree timer waits (`Wait`/`CustomScaledWait`) for animation
  pacing — the same presentation category as `SfxCmd`/`VfxCmd`/`TalkCmd`/
  `ThinkCmd` beside it in the `commands_remainder` decision, not run
  orchestration. Filed out of scope (presentation layer); see
  `audit/seams/potion_pipeline.md`'s file-list note for the full
  `commands_remainder` disposition of all 13 files.

## Dropped Runs/*.cs files (12 of the 21 candidates), with reason

The brief listed 21 candidate files (every file under `src/Core/Runs/` except
`RunState.cs`, which was already claimed) and asked for an explicit
drop-with-reason for pure plumbing rather than a silent omission. Two more
(`RelicGrabBag.cs`, `RunRngSet.cs`) are reassigned, not dropped (see above);
four more (`CardCreationFlags/Options/Source`, `CardRarityOddsType.cs`) are
also reassigned, not dropped (see above). The remaining 12 are genuinely out
of scope:

| File | Reason |
|---|---|
| `GameMode.cs` | Bare enum (`Standard`/`Daily`/`Custom`); Daily/Custom modes are unsimulated. |
| `GameModeExtension.cs` | One helper (`AreAchievementsAndEpochsLocked`) gating achievements/epochs — unsimulated meta-progression. |
| `ICardScope.cs` | Pure interface (`CreateCard`/`AddCard`/`RemoveCard`/`CloneCard` contract); the implementations live on `RunState.cs` (hook_dispatch) and `CombatState.cs` (hook_dispatch/turn_structure), both already claimed. |
| `IPlayerCollection.cs` | Pure interface, by its own doc comment "Primarily used to allow mocking the player collection for testing." |
| `MapLocation.cs` | Value type with only equality/packet-serialization behavior; its own doc comment says it exists "for situations where the room doesn't matter, e.g. map voting" — multiplayer plumbing. |
| `RunLocation.cs` | Same shape as `MapLocation.cs`; its own doc comment says it exists "for `RunLocationTargetedMessageBuffer`" — multiplayer message routing. |
| `NullRunState.cs` | Null-object `IRunState` stub for menu/dev-console/test contexts with no active run. The RL sim is always inside a run; this branch is never exercised. |
| `PlayerMapPointHistoryEntry.cs` | Per-floor stat-tracking DTO (JSON + packet serialization only); consumed by `RunHistory`/`ScoreUtility`, dropped for the same reason below. |
| `RunHistory.cs` | Save-file schema (`ISaveSchema`) for the local run-history UI; no gameplay branch. |
| `RunHistoryPlayer.cs` | Serialization-only DTO nested under `RunHistory.cs`. |
| `RunHistoryUtilities.cs` | Builds a `RunHistory` entry at run end (killed-by-encounter/event, badges) — real logic, but purely for the save-file/UI, not RL-relevant. |
| `ScoreUtility.cs` | Score/badge/leaderboard math — the brief's own "score plumbing" drop category, explicitly named as droppable. |

## Game sources claimed, with justification

- `src/Core/Runs/RunManager.cs` — the run orchestrator singleton. Also
  cross-cited by `rooms_and_map` for its `BuildRoomTypeBlacklist`/
  `RollRoomTypeFor` methods only (split by method — see that seam's doc; this
  record owns everything else in the file).
- `src/Core/Runs/IRunState.cs` — the declared run-state surface every
  consumer calls through. Plays the same "root contract, audited once" role
  `AbstractModel.cs` plays for `hook_dispatch` — most of its members are
  IMPLEMENTED on `RunState.cs` (hook_dispatch's problem) but the CONTRACT
  itself, and default/static members it declares directly
  (`ICardScope.DebugOnlyGet`-adjacent statics live on `ICardScope`, not here —
  double check `IRunState.cs` for any default-implemented members of its own
  before assuming everything routes to `RunState.cs`).
- `src/Core/Runs/ExtraRunFields.cs` — a 3-field bag, all three now audited
  (`run_layer.json` guards G1-adjacent/G2/G3). **Correction to this doc's own
  prior claim, found during the audit:** this section used to say `FreedRepy`
  "is real, ported gameplay state," citing `war_historian_repy.py`'s own
  comment as support. Re-reading that exact comment shows the OPPOSITE:
  `FreedRepy`'s only reader besides its setter is `NQueenRepyBgVfx.cs:20`, a
  purely cosmetic background-VFX visibility toggle, so the sim's own comment
  concludes "it is not ported" — and correctly does not model it.
  `StartedWithNeow` is not merely "unsimulated" either: it gates two real
  structural branches at Act 0 (guard G1), the sim just always takes the
  branch that assumes it is `true`, which every real conformance fixture in
  this repo (an established player's save) satisfies. `TestSubjectKills` is
  confirmed profile-lifetime, display-only (guard G2, matching
  `monster/test_subject.json`'s pre-existing verdict under Rule 3). Claimed
  whole because auditing it required reading every field, not because every
  field turned out to carry gameplay weight.

## Sim sources claimed, with justification

- `sts2_rl/run.py` — the sim's `RunState` class fuses what the game splits
  across `RunManager`/`RunState`/`IRunState`. No other sim file claims it on
  the sim side of any existing seam (`hook_dispatch`'s sim list, which claims
  `RunState.cs` on the game side, does not include `run.py`), so there is no
  double-claim to avoid here.

## Scope boundary against the neighbouring seams (settled by the audit)

What this record looked at and explicitly did NOT claim, because another
seam already owns the file or the mechanism:

- **`rng_streams`** — owns stream IDENTITY, seeding, and primitive draw
  semantics (its report's stream-map table is authoritative; cited, not
  re-derived). This record owns *which run-layer draws happen, in what
  order, at which boundary* — traced draw-for-draw against `RunManager.
  GenerateRooms`/`run.py._generate_all_act_rooms` (step 3) and closes
  `rng_streams`' own deferred item ("consumer draw count is run_layer's").
  Also traced the `string_seed`/`rng_set` default that decides whether a
  run's per-encounter RNG is even seeded at all (guard G8) — the ORIGIN of
  the already-live `encounter/_selection_rng_fallback` family, not a new
  rng_streams-level mechanism.
- **`rooms_and_map`** — owns `ActModel.cs`, `RoomSet.cs`'s own body
  (`eventsVisited`/`MarkVisited`/`NextEvent`), `BuildRoomTypeBlacklist`/
  `RollRoomTypeFor`'s own room-type-rolling logic, and per-act encounter/boss
  CONTENT (`BossDiscoveryOrder`, `ApplyActDiscoveryOrderModifications`). This
  record verified the Ancient-node `eventsVisited` bump's CALL SITE
  (`RunManager.cs:1129`, step 7 — faithful) and filed the discovery-order
  GATE (`ShouldApplyTutorialModifications`, its own file/method, guard G6,
  LIVE) since that gate and its call site are `RunManager.cs`'s, not
  `ActModel.cs`'s — but the gated CONTENT is rooms_and_map's to detail
  further if it wants to. `TryGetRoomTypeForTutorial` (guard G9) is a private
  RunManager.cs helper called from within `RollRoomTypeFor`; verdicted here
  because rooms_and_map's own scope doc cross-cites `RollRoomTypeFor` "for
  its method only," which is ambiguous about a transitively-called private
  helper — flagged for the controller to settle, not left unclaimed.
- **`rewards`** — owns `CardCreationFlags/Options/Source.cs`,
  `CardRarityOddsType.cs` (per this doc's own prior override note, unchanged)
  and reward-screen generation. Not touched by this audit.
- **`relic_pools`** — owns `RelicGrabBag.cs`, bucket identity/order for the
  grab bags this record's steps 2-3 cite by call position only.
- **`turn_structure`** — owns everything inside a combat (this record's step
  11 names `create_combat`/`finish_combat` as the BOUNDARY into and out of a
  combat — the deck-copy-in/HP-carry/results-sync-back contract — but not
  what happens between them).
- **`hook_dispatch`** — owns `RunState.cs`'s own body (the `IRunState`
  implementation, `IterateHookListeners`) and `Player.cs` (starting deck/
  relic/potion/HP/gold granting, step 0). This record's own contract file,
  `IRunState.cs`, declares the surface `RunState.cs` implements; this record
  claims `IRunState.cs`'s few DEFAULT-implemented members of its own
  (`IRunState.GetFrom`, guard G4) and leaves everything IMPLEMENTED on
  `RunState.cs` to hook_dispatch, per this doc's original design.

## What the next auditor needs to know

1. `RunManager.cs` is 56.7K of orchestration. The ordering spec (14 steps)
   covers run start through run end; it does not re-walk every one of the
   file's ~110 members — only the ones on the critical path a conformance
   run actually takes.
2. `run.py`'s docstring calls itself "the minimal out-of-combat run layer
   that events act on." Confirmed: multiplayer sync, save/load, and Daily/
   Custom-mode content are the load-bearing things it deliberately does not
   attempt (`NullRunState.cs`/`RunHistory*.cs`/`ScoreUtility.cs`'s drop
   reasons above, plus guard G5's ascension-effects waiver and G6/G9's
   profile-scope findings, all confirm this rather than assume it).
3. **`character` kind is unaudited (0 of 5 records filled).** This record's
   step 0 spot-checked Ironclad's own starting HP/gold/deck/relics against
   `Ironclad.cs` and found them faithful, but that is not a substitute for a
   real `character/ironclad` audit — nobody owns per-value correctness for
   any of the 5 characters' starting kits today, the same shape of hole
   `EncounterModel`'s monster-slot generation was before the `encounter` kind
   was audited.
4. **`AscendersBane`/`TightBelt`-class ascension effects (guard G5) are a
   genuine structural absence**, waived here only because this campaign's
   standing precedent treats ascension broadly as out of scope (matching
   `hook_dispatch`'s Modifiers/BadgeModels guards and `monster_state_
   machine`'s N4). If that stance ever narrows, `AscensionManager.
   ApplyEffectsTo` is where to start.
