# Gap-fix pass — every LIVE entry in the queue, 2026-08-03

Scope: `audit/GAP-QUEUE.md`'s **20 live entries across 10 mechanisms** (the
queue's first-ever live entries, filed the same day by the systems-tier
campaign). All 10 are closed. 16 dormant entries belonging to the same
mechanisms were closed with them — a mechanism was never landed at only its
live sites.

**Final state:** queue 384 entries / 20 live → **348 / 0 live**; 335
mechanisms / 10 live → **323 / 0 live**. Suite **4639 passed, 6 xfailed**
(from 4526). `coverage`, `cite-check` and `audit_status` all green (0 invalid
records).

---

## 1. `encounter/_slot_order`, `_slot_name_not_set`, `fogmog/Slots`, `_slots_not_ported` (17 entries)

Four separately-filed "slot" mechanisms, one fix. Every encounter whose C#
declares a `Slots` row now declares it, every summon site passes its
`slot_name=`, and `CombatState.__init__` routes whatever `create_monsters`
returns through the new `Encounter.seat_in_slots` so the seventeen overrides
are seated too.

- 11 encounters given their row: two_tailed_rats, fogmog, the_obscura, mytes,
  axebots, decimillipede, kaiser_crab, knights (names only — no `Slots`
  override in C#), queen, dense_vegetation_event, fake_merchant_event.
- 3 summon sites given a slot: `TwoTailedRat._call_for_backup` (which now
  resolves it the way C# does, `Slots.LastOrDefault(free)`),
  `Fogmog._illusion_move`, `TheObscura._illusion`.
- `TwoTailedRat._can_summon`'s headcount gate replaced by the row gate the C#
  actually uses (`GetNextSlot` non-empty).

**Two engine bugs found while landing it, neither filed anywhere:**

1. `Encounter.get_next_slot`/`last_free_slot` scanned ALL of `combat.enemies`
   for occupancy, including corpses. The game's `Enemies` list has already
   dropped a dead creature (`CombatState.RemoveCreature`), so its slot is free
   for the next summon. Fixed to skip `is_removed_from_combat`, matching what
   `fabricator.py`/`queen.py` already do for their own `Enemies` scans. This
   was dormant until two_tailed_rats (whose rats die mid-fight) started using
   the row.
2. `PregeneratedEncounter.of` copied a hand-listed subset of the encounter's
   fields, so an event-layout fight silently lost the slot row and the entry
   slug. Now copies them; caught by an existing test, not by review.

**Recipe correction:** the queue said the rats' summon "lands at `enemies[1]`".
It lands at `enemies[0]` — the three starting rats occupy `Slots[2..4]`, so the
summon takes `"second"` (index 1) and sorts ahead of all three.

Tests: `test/test_encounter_slots.py` (+8). Probes `encounter_probes_e8
rat-slot-order`, `e1 fogmog-slot-order`, `e4 obscura-slot` all now print MATCH.

## 2. `encounter/_entry_slug_mismatch` (6 entries)

`Encounter` gained an explicit `entry_slug`; `Encounter.entry` returns it when
set. The sim id stays the sim's identity, and the per-encounter Rng gets the
game's real `ModelId.Entry`.

**The record's five units were not all of them.** A mechanical sweep of all 87
sim encounters against `src/Core/Models/Encounters/*.cs`
(`audit/tools/encounter_entry_sweep.py`, new) found two more nobody had
checked: `fuzzy_wurm_crawler` (C# `FuzzyWurmCrawlerWeak`) and
`overgrowth_crawlers_normal` (C# `OvergrowthCrawlers`). The sweep now reports
MATCH for all 87.

Tests: `test/test_encounter_entry_slugs.py` (new, 12).

## 3. `encounter/_selection_rng_fallback` (7 entries)

`RunState.create_combat` builds the per-encounter Rng on BOTH paths. The
seedless (RL training/eval) path has no numeric run seed, so it derives one at
construction from the shared generator's STATE
(`run.derive_encounter_seed`) — deterministic, and a pure read, so no other
legacy stream shifts by a single draw. `create_monsters`' `selection_rng=None`
arm is now unreachable from production.

Tests: `test/test_encounter_selection_rng.py` (+15), including "advance the
shared stream, the composition must not move" for all seven units.

## 4. `encounter/gremlin_merc/CalculateGoldProportion` (1 entry)

`EncounterModel.CalculateGoldProportion` ported on the base (`1 − escaped
creatures / DISTINCT spawned models` — the two counts are deliberately
different shapes in C#), overridden by a new `GremlinMercEncounter`.
`driver._run_combat` and `conformance/runner.py` compute it off the finished
combat, as `CombatRoom.OnCombatEnded` does.

**Recipe correction:** the queue described a two-arm override. It has three —
`1.0` / `0.5` (fled, nothing stolen) / `0.0` (fled with stolen gold). The 0.5
arm was missing from the queue text.

`GoldWasStolen` is read as `combat.gold_stolen > 0`: `Encounter` objects are
module-level singletons shared by every combat (C# takes a per-run
`ToMutable()` copy), and both the Merc's ThieveryPower and the Fat Gremlin's
HeistPower are cleared by the death and the escape before rewards generate.

Tests: `test/test_underdocks.py::TestGremlinMercGoldProportion` (+4).

## 5. `relic_pools/step13` (1 entry)

`cards/pool.py` declares `STATUS_POOL` in `StatusCardPool.cs`'s own
(non-alphabetical) order and the STATUS transform branch uses it. The old code
rebuilt the row from `sorted(_CARD_CLASSES)`, which both alphabetized it and
swept in four sim statuses that are not StatusCardPool members at all.

Tests: `test/test_card_generation_pool.py::TestStatusTransformKeepsTheDeclaredPoolOrder`.

## 6. `potion_pipeline/G1` == `potion/foul_potion/G1` (2 entries)

`Potion.passes_custom_usability_check` ported as a default-True hook,
consulted by both use paths, with FoulPotion's three-arm override. `RunState`
gained the `current_room_type`/`current_event` it needs (set in `enter_point`).

The event arm of `FoulPotion.OnUse` was ported at the same time —
`use_out_of_combat` routes to a new `FakeMerchant.foul_potion_thrown` instead
of paying the shop's 100 gold — because admitting that room without it would
have introduced a fresh divergence. One legacy test drank the potion in no
room at all and was updated (it now enters the shop).

Tests: `test/test_potions.py::TestFoulPotionUsabilityCheck` (+5).

## 7. `run_layer/G6` (1 entry)

`ActModel.ApplyDiscoveryOrderModifications` ported as
`RoomSet.apply_discovery_order_modifications`, run where RunManager.cs runs it
and drawing no RNG: the boss override walks each act's transcribed
`BossDiscoveryOrder`, and Overgrowth's first-run lineup is ported with both
arms of `RoomSet.SwapToOrCreateAtIndex`. It reads a new `rooms.UnlockState`
(`HasSeenEncounter` + `NumberOfRuns`) that `RunState` takes as a parameter.

**The record's premise that no fixture carries discovery history is refuted.**
Both installed Ironclad captures store `players[0].unlock_state` —
`number_of_runs` 999999999, all 12 bosses seen. The conformance runner now
feeds the recording's own profile, so "the pass is a no-op for these seeds" is
a measured fact rather than the assumption behind the `UnlockState.VETERAN`
default. `rooms.py`'s line comment calling this a tutorial-only path (the very
bug class the guard filed) is rewritten.

Tests: `test/test_discovery_order.py` (new, 27).

## 8. `rng_streams/G7` — the 89U act-1 `+6 HP`, open for three rounds

**Closed, and it was not an RNG bug.**

Localized with ground truth nobody had read: `run.save`'s `map_point_history`
carries per map point `current_hp` / `max_hp` / `damage_taken` / `hp_healed`
(plus gold counters and that point's relic/event choices), and `SaveOracle`
already parsed the field for relic reconciliation. Act 1's last point records
`damage_taken 18, healed 6, 63 → 51` against the sim's `12 / 6 / 63 → 57`,
with every earlier point matching exactly — the whole divergence sat inside the
act-1 boss fight.

Root cause: Knowledge Demon's Curse of Knowledge is a
`CardSelectCmd.FromChooseACardScreen` resolved MID-MOVE
(`KnowledgeDemon.cs:183`), which the recording writes as
`SelectCardFromScreen N`. `ReplayCombatDriver._grid_selector` understood only
`SelectGridCard`/`SelectHandCards`, so `select_cards('curse_of_knowledge', …)`
returned `[]` — no curse power applied — and the recorded command was then
dispatched into an empty `_pending_screen_cards` and silently dropped. Both
halves failed quietly; every stream counter stayed green.

**Conformance delta (the headline this pipeline exists to produce):**

| seed | before | after |
|---|---|---|
| 89U21BV1TZ act-1 boundary HP | expected 51, got 57 | **51 — exact** |
| 89U21BV1TZ divergent floors (act 1) | 1 (floor 34) | **0** |
| 933T39V18D act-1 boundary HP | expected 56, got 68 | **56 — exact** |
| 933T39V18D divergent floors (whole run) | 3 (34/47/49) | **2 (47/49)** |

Still open on both seeds: the act-2 boundary (89U expected 33/111, got
107/107, forced=8; 933T +13). Both xfail reason strings were rewritten — the
old ones were stale by three rounds.

**Correction to an earlier draft of this report**, which said act 2 was blocked
because "Glory combat parity is incomplete". That was inherited from the stale
xfail text and is wrong on both counts: forced is 8, not 9, and **all eight
act-2 units are ported**. Investigated after the fact — the first act-2 fight's
opening hand matches the recording card for card, and the divergence is the
replay harness a second time, in `combat_card_db.py`. The game ids turn-1
generated cards as they are ADDED (Blessed Antler's 3 Dazed enter the draw pile
at `BeforeHandDraw`, taking ids 23-25 while all three are still in the draw
pile; Vexing Puzzlebox's card takes 26 after the draw), while the sim
RECONSTRUCTS ids post-draw by walking hand-then-draw — so the one Dazed that got
drawn takes an early id and the Puzzlebox card slides in front of its siblings.
`PlayCard 26` resolves to a Dazed instead of Rampage, and the fight force-wins.
Measured: walking draw-before-hand for the generated cards takes act-2
`forced_combats` **8 → 5** and greens the first three fights; the wall then
moves into mecha_knight on a second, separate generated-card cause. That
experiment is not a correct general fix and was not shipped — filed as open
work.

Tests: `test_the_curse_of_knowledge_choice_is_taken_from_the_recording`.

---

## Tooling defects found (all by unit work, none by review)

1. `audit/tools/encounter_probes_e7.py` had no `sys.path` bootstrap and had
   **never run** — it raised `ModuleNotFoundError` on import, so its
   "executed" numbers came from somewhere else. Fixed.
2. Several probes printed a hard-coded DIVERGENCE verdict below their computed
   output, so they kept reporting the gap after the fix landed. `e1`, `e2`,
   `e7`, `e8` and `run_layer_probes` now derive the verdict from what they just
   executed.

## Records and staleness

36 entries flipped to `faithful` across 25 records, each with the closing
rationale written where the `issue` was and the original text preserved under
`WHAT THE GAP SAID:`. Record-level verdict rollups recomputed (17 records).

**Hashes deliberately NOT refreshed.** This pass re-verified the entries it
closed, not every other entry in those records, so the staleness flag stands
as the signal for a proper re-audit pass.

## Left for the next round

- **Build the per-room oracle.** `map_point_history` would localize every
  remaining HP/gold divergence to a single room the way it just did by hand —
  including 89U's act-2 delta and 933T's floor 47. Filed in the queue's
  open-work section; the highest-leverage tooling left here.
- **Census `FromChooseACardScreen` call sites** against the sim's two screen
  mechanisms: Knowledge Demon may not be the only mid-move screen the replay
  driver mis-resolves.
