# Engine seam: `rooms_and_map`

**STATUS: AUDITED 2026-08-03** (Phase 2, `p2-rooms_and_map` batch). Wired
2026-08-03 (P1-T2 of the systems-tier campaign), audited the same day.
`audit/records/seam/rooms_and_map.json` carries 36 verdicted steps + 3 guards,
`py audit/tools/harness.py validate` reports 0 invalid, `py
audit/tools/citation_check.py` reports 0 MISSING / 0 OUT-OF-RANGE.

**Rollup verdict: `deliberate-divergence`** (33 steps faithful, 2 steps
waiver-equivalent... see the record for the exact split; one step —
`AbstractRoom`'s Enter/Exit/Resume lifecycle and the C#'s room-stack
architecture, step 18 — is a genuine `deliberate-divergence`: the sim
collapses a 6-class OOP room hierarchy plus a stack-based `Resume` mechanism
into one flat `RunState.enter_point` function, because the sim has no
scene-tree/UI layer for `Resume` to serve in the first place. That is the
rollup's ceiling: `max(step verdicts)` in this record's precedence order
(`faithful < waiver < deliberate-divergence < gap`) is `deliberate-divergence`,
so the unit-level verdict is raised to match rather than silently absorbed
into a `faithful` rollup that would misrepresent how differently that one
mechanism is shaped — even though nothing observable is lost; see guard G2).
**Zero `gap` verdicts were filed** — every divergence found either has a
functionally-equivalent sim counterpart (verdicted `faithful` or
`deliberate-divergence`) or is a save-progression/first-run-ever/dead-code
mechanism outside this campaign's fully-unlocked-run scope (verdicted
`waiver`). This is a genuinely well-ported seam, confirmed by three
independent deep-read passes plus this auditor's own direct re-verification
of the highest-risk claims (the encounter-tag mechanism, the Ancient-node
`eventsVisited` off-by-one, the Spoils Map RNG-stream wiring, the merchant
rounding convention, and a live re-execution of the "stops on map coord"
conformance failure). See the record's steps/guards for the full evidence;
the headline findings are summarized below.

## Headline findings

- **Map generation (`StandardActMap`/`SpoilsActMap`/`GoldenPathActMap`,
  `MapPathPruning`, `MapPostProcessing`, `MapPointTypeCounts`) is faithfully
  ported**, draw-for-draw, in `sts2_rl/actmap.py`'s PARITY path (when a
  `string_seed` is supplied). The default RL-training env (`STS2RunEnv`) never
  supplies one, so production training runs use a bare, unseeded-relative-to-
  the-game `random.Random` for map generation — a **documented, intentional**
  divergence (`actmap.py`'s own comments), not a bug; the conformance/parity
  path is where fidelity is claimed and it holds.
- **Confirmed: map layout comes from the ad hoc `act_N_map`/`spoils_map`
  string-keyed transient streams, not from `UpFront`** — this seam's own
  reading independently reaches the same conclusion `seam/rng_streams`
  already recorded; cited, not re-derived.
- **The encounter/event picker (`Helpers/GrabBag.cs`,
  `ActModel.AddWithoutRepeatingTags`) is faithfully ported, INCLUDING tag
  handling.** The sim's `rooms.py` models `EncounterTag` fully, at the correct
  one-step-lookback scope (rejects only against the immediately preceding
  pick, not a same-act/same-run exclusion set) — this directly answers the
  question nine sibling `encounter`-kind batches were pointed at this seam
  for. A predicated `GrabAndRemove` costs a *variable*, value-dependent number
  of draws (not a fixed 1 per pick) on both sides — a clarifying fact for
  anyone hand-computing stream draw counts.
- **The Ancient-node / `eventsVisited` off-by-one (a documented campaign
  trap — "Ancient node is an event room") is ALREADY CORRECTLY PORTED.**
  `run.py`'s `start_act` independently reconstructs the same C# citation
  chain this seam's own reading found. Verdicted faithful, not left as an
  open risk.
- **The three historical "stops on unreachable map coord" conformance seeds
  are confirmed a character-content gap, not a map-generation bug** — this
  seam re-executed the claim rather than inheriting it (`py
  tools/converge_triage.py DJDCSAQZNR floor_49 2`): the divergence starts at
  room 11 with the wrong (Ironclad) hand of cards, cascading into RNG-stream
  drift that only manifests as an unreachable coordinate several rooms later.
  Waivered as out of this Ironclad-only campaign's scope, with an executed
  witness, per the brief's instruction to treat the prior diagnosis as an
  open question rather than settled.
- **Hive/Glory's room/encounter/event data is NOT thin or stub** — a prior
  report's worry is refuted: all four acts' `_<name>_rooms()` factories carry
  full, correctly-shaped pools, verified key-by-key against the C# arrays.
- **Merchant pricing/stocking is faithfully ported**, including a resolved
  open question from the research phase: Godot's `Mathf.RoundToInt` and C#'s
  `Math.Round` both use `MidpointRounding.ToEven` (banker's rounding) — the
  same convention Python's `round()` uses — so there is no second rounding
  rule in the source to diverge from.
- **`AbstractRoom`'s OOP lifecycle (Enter/Exit/Resume, the room-stack) has no
  sim counterpart at all** — a deliberate architectural collapse into one
  flat function, not a missing feature. The one place this could have mattered
  (an event's own post-combat continuation after a nested combat room exits)
  is independently confirmed preserved via a directly-callable method instead
  of a room-stack pop (guard G2). This is the seam's sole `deliberate-
  divergence`-level finding and sets its rollup verdict.

## Scope

**Claims:** what a map point becomes when the player travels onto it (room
type rolling, blacklists, the four acts' pre-rolled encounter/event queues),
the map's own generation (path carving, point-type assignment, pruning,
post-processing), each act's structural data (encounter/event rosters, boss
discovery order, per-act map-point-type rolls), the rest-site and merchant
room contents (pricing, stocking), and the "?" node pity-roll odds.

## The Acts-into-this-seam decision (recorded, per the brief)

**Decision:** `src/Core/Models/Acts/*.cs` (5 files: `Overgrowth`, `Underdocks`,
`Hive`, `Glory`, `DeprecatedAct`) is folded into `rooms_and_map` rather than
becoming its own kind or its own seam.

**Reason:** the sim has no act registry. Verified 2026-08-03: no `ACTS`,
`ALL_ACTS`, or `class Act` anywhere under `sts2_rl/` — an act's identity in
the sim is implicit in which of `rooms.py`'s four `_<name>_rooms()` functions
and `actmap.py`'s four `ActMapConfig`s a caller reaches for, not a rostered
object with its own audit unit shape (`roster(kind)` has nothing to iterate).
Since there is no "act" kind, Acts' structure would otherwise be invisible to
the whole pipeline the same way rewards/pools/rooms/map were before this
task — so it is folded into the seam whose subject (room/map generation) is
what Acts actually configure, rather than being left unaudited on a
technicality.

## Scope boundary (what this does NOT claim, and which seam does)

- `EncounterModel`'s own monster-slot generation
  (`GenerateMonstersWithSlots`) — **not claimed by any seam wired in this
  task.** `audit/GAP-QUEUE.md`'s "Behaviour in no tier's scope" section names
  this as one of the two worst systems-tier holes, but it is the `encounter`
  KIND's own subject (each encounter content record's future job — "how does
  THIS encounter build its monster list"), not "which encounter gets rolled
  for a room" (this seam's job). Left open on purpose; see the P1-T2 report's
  `MODEL_ROOT_CLASSES` discussion for why `EncounterModel.cs` is still not a
  root class.
- Reward generation once a room ends — `rewards`'s job. This seam ends at
  "this room is a `CombatRoom`/`EventRoom`/etc holding this encounter/event";
  `RewardsCmd.OfferForRoomEnd` picks up from there.
- Relic/card/potion pool composition and the rarity/escalation ladder —
  `relic_pools`'s job, even for the merchant's own stock (the shop pulls from
  the same pools; this seam claims the shop's PRICING/SLOT-COUNT rules, not
  the pool it draws from).
- RNG stream identity — `rng_streams`'s job. Map generation is heavily
  RNG-consuming (this seam's own doc comment in `SEAM_SOURCES` calls it out),
  but which physical stream a draw comes off is not this seam's claim.
- `RunManager.cs` in full — `run_layer`'s job. This seam cross-cites the file
  only for `BuildRoomTypeBlacklist`/`RollRoomTypeFor` (per `rooms.py`'s own
  docstring); everything else in `RunManager.cs` is `run_layer`'s.

## Game sources claimed, with justification

- `src/Core/Rooms/*.cs` (14 files, claimed wholesale — no shared base worth
  pointing at instead, same reasoning as `relic_pools`' 32 pool files):
  `AbstractRoom`, `BackgroundAssets`, `CombatEventVisuals`, `CombatRoom`,
  `CombatRoomMode`, `EventRoom`, `ICombatRoomVisuals`, `MapRoom`,
  `MerchantRoom`, `RestSiteRoom`, `RoomSet`, `RoomType`, `RoomTypeExtensions`,
  `TreasureRoom`.
- `src/Core/Map/*.cs` (16 files, claimed wholesale, same reasoning): `ActMap`,
  `GoldenPathActMap`, `MapCoord`, `MapPathPruning`, `MapPoint`,
  `MapPointState`, `MapPointType`, `MapPointTypeCounts`, `MapPostProcessing`,
  `MapTravel`, `MockCraftedActMap`, `MockSinglePointActMap`, `NullActMap`,
  `SavedActMap`, `SpoilsActMap`, `StandardActMap`.
- `src/Core/Models/Acts/*.cs` (5 files: `Overgrowth`, `Underdocks`, `Hive`,
  `Glory`, `DeprecatedAct`) — see the Acts decision above.
- `src/Core/Models/ActModel.cs` — the Acts' BASE class. Not in any directory
  the brief named, but `rooms.py`'s own docstring cites it directly
  ("`RoomSet.cs + ActModel.GenerateRooms -> RoomSet` and `ActRooms`");
  omitting it would leave the one method every Act file calls into unpinned.
  Also holds the default `GetMapPointTypes` and
  `ApplyActDiscoveryOrderModifications` (the "first run ever" reordering —
  save-progression-gated, expect a waiver/dormant verdict since the sim
  models a fully-unlocked run).
- `src/Core/Odds/UnknownMapPointOdds.cs` — the "?"-node pity roller
  `rooms.py` ports as `UnknownOdds`. Lives under `Core/Odds/`, outside both
  `Rooms/` and `Map/`; found by reading `rooms.py`'s own docstring.
- `src/Core/Entities/RestSite/RestSiteOption.cs` — `rest_site.py`'s own
  docstring names it as ground truth (`Hook.TryModifyRestSiteOptions`). A
  sibling of `Rooms/RestSiteRoom.cs`, not the same file — the room shell is
  in `Rooms/`, the "extra rest-site action a card/relic contributes"
  mechanism is in `Entities/RestSite/`.
- `src/Core/Entities/Merchant/MerchantEntry.cs`, `MerchantInventory.cs`,
  `MerchantCardEntry.cs`, `MerchantCardRemovalEntry.cs`,
  `MerchantPotionEntry.cs`, `MerchantRelicEntry.cs`, `PurchaseStatus.cs` (7 of
  8 files under `Entities/Merchant/`) — `shop.py`'s own docstring names
  `MerchantRoom.cs`/`MerchantInventory.cs` as ground truth alongside the
  entry subclasses and their pricing formulas. `MerchantDialogueSet.cs` (the
  8th file, shop NPC flavor lines) is **dropped** — presentation only, no
  priced/stocked behavior.
- `src/Core/Helpers/GrabBag.cs` — the generic weighted-pop primitive
  `ActModel` uses for tag-safe encounter/event picking
  (`AddWithoutRepeatingTags`). Not claimed by `relic_pools` (see that seam's
  doc) because `RelicGrabBag`'s own logic never calls it despite the similar
  name.
- `src/Core/Commands/MapCmd.cs` — `SetBossEncounter`, the one behavioral line
  (`runState.Act.SetBossEncounter(boss)`) behind a presentation-only method;
  the only `Commands/*.cs` file whose subject is the map/act.
- `src/Core/Runs/RunManager.cs` — cross-cited from `run_layer`
  (`BuildRoomTypeBlacklist`/`RollRoomTypeFor` only, per `rooms.py`'s
  docstring — the rest of the file is `run_layer`'s).

## Sim sources claimed, with justification

- `sts2_rl/rooms.py` — room resolution: `RoomType`, `RoomSet`/`ActRooms`,
  `UnknownOdds`, `build_room_type_blacklist`/`roll_room_type`. Its own
  docstring lists every game file it ports.
- `sts2_rl/actmap.py` — map generation: `StandardMap`, `MapPoint`,
  `MapPointType`, `MapPointTypeCounts`, pruning/post-processing, and
  `golden_path_map`. Its own docstring lists every game file it mirrors.
- `sts2_rl/rest_site.py` — `RestSiteOption`, small but a real, direct port.
- `sts2_rl/shop.py` — the merchant: `MerchantInventory` and the four entry
  types' pricing.

## What the Phase-2 auditor needs to know

1. This is the largest file list of the six new seams (~47 game files). Most
   of the bulk is the deliberately-wholesale Rooms/Map/pool-shaped
   directories, not per-file complexity — do not read this as "the hardest
   seam," read it as "the seam with the most named-but-simple data files."
2. `ActModel.ApplyActDiscoveryOrderModifications`'s "first run ever" branch
   (`unlockState.NumberOfRuns == 0`) is a save-progression gate the sim
   deliberately does not model (fully-unlocked run assumption, same as every
   other epoch/unlock check across this whole audit). Expect this to verdict
   `deliberate-divergence` or `waiver`, not `gap`.
3. `EncounterModel`'s monster-slot generation is explicitly OUT of this
   seam's scope (see the boundary section above) — do not let it creep in
   just because `ActModel.GenerateAllEncounters` returns `EncounterModel`
   instances. This seam stops at "which encounter got picked."
4. `actmap.py`'s docstring notes Acts 2-3's maps "generate correctly today
   even though their run layers (events, shops) aren't in the sim yet" — the
   sim's `rooms.py` docstring claims full act coverage that may be narrower
   than it sounds; verify against the actual `_hive_rooms`/`_glory_rooms`
   contents before trusting the docstring's "every act ModelDb ships is
   wired into the run layer" claim at face value.

**All four items above were checked by the 2026-08-03 audit (see "Headline
findings" above and the record's steps).** Item 2 (tutorial `NumberOfRuns==0`
gates, both the map-quota one and `ApplyActDiscoveryOrderModifications`'s)
verdicted `waiver`, as predicted. Item 3 was respected — no monster-slot
generation crept into this record. Item 4's docstring claim was checked
directly against `_hive_rooms`/`_glory_rooms` and found accurate for the
room/encounter/event/ancient data this seam owns (see step 21) — it was
**not** overclaiming.
