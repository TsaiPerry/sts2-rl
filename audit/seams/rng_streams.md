# Engine seam: `rng_streams`

**STATUS: AUDITED 2026-08-03** (Phase 2 batch 1 of the systems-tier campaign).
Record:
`audit/records/seam/rng_streams.json` (23 steps, 8 guards). Top-level verdict
`gap` — one dormant divergence (`step 16`, `WeightedNextItem`'s float32-vs-
double precision, zero consumers on either side today), everything else
`faithful`/`waiver`/`deliberate-divergence`. Probes:
`audit/tools/rng_stream_probes.py` (7 probes, all executed and passing this
batch).

## Why this seam exists

`audit/GAP-QUEUE.md`'s own "Behaviour in no tier's scope" section called out,
verbatim: "no record owns the `combat_rng` stream map … given that stream
desync is the highest-impact failure class in this queue, that is the largest
structural hole here." Every other seam and every content record treats
"draw from the RNG" as a primitive it can call without asking which physical
stream answers, in what order, and how many draws it costs. This seam is
where that question has a home.

## What this seam found, in one paragraph

The stream-identity layer itself — the two enums, the seeding formula, the
`MegaRandom`/`Rng` primitives (including exact draw-count parity), the two
shuffle helpers, the save/load round-trip, and the four call-site categories
this batch checked (Rewards-stream relic pulls, `Catastrophe`'s
StableShuffle-then-First shape, combat-stream routing via `CombatRng`, and the
ad-hoc content-keyed `Rng(Player, ModelId, …)` formula family) — is faithful,
checked primitive-by-primitive against the C# and proven equal by execution,
not by reading alone (see `rng_stream_probes.py` and the record's own
`test/data/rng_golden.json` cross-checks). The seed for the `89U21BV1TZ` and
`933T39V18D` conformance strings was independently recomputed this batch and
matches the golden fixture (dumped from `sts2.dll`, not from this same Python
code) for `89U21BV1TZ`: **2221240958**; `933T39V18D` computes to
**3245367928**. The one real, dormant divergence found (`WeightedNextItem`'s
float32-vs-double weight-sum precision) has zero consumers anywhere in either
tree today — stronger than "no *ported* consumer", literally no C# call site
exists either.

**What this seam did NOT settle:** the 89U conformance seed still diverges by
+6 player HP at the act-1 boundary (`test_conformance_player_state.py`,
xfail(strict=False), still failing). `tools/converge_triage.py`'s DETECTOR 4
isolates floor 34 (the act-1-boundary combat) as the ONLY independently
divergent floor; DETECTOR 2's large stream-counter deltas over the whole act
are very likely downstream cascade noise from that one earlier divergence
(per the tool's own documented caveat), not four independent stream bugs.
Because every OTHER stream-map fact this record checked came back faithful,
this symptom is NOT explained by anything else in this seam's scope — it is
filed as an explicit LIVE handoff (record guard G7, `live: true` — an
actually-failing assertion on ported Ironclad content, not a reachability
argument) to whichever batch localizes floor 34's actual combat divergence
(candidate: `ENCOUNTER.VANTOM_BOSS`, the act-1 boss, per the save's own
`encounter_ids_by_act`, NOT independently confirmed as the diverging fight).

## Scope

**Claims:** which named stream a draw comes off (the `PlayerRngType` /
`RunRngType` enumerations), how each stream is seeded from the run/player base
seed plus its own name (`GetDeterministicHashCode(SnakeCase(name))`), the
counter-wrapping semantics of one `Rng` instance (`NextInt`/`NextDouble`/
`NextGaussianInt`/shuffle/`NextItem`/`WeightedNextItem`, each costing exactly
one or more counter increments), the underlying `MegaRandom` (Xoshiro256**)
core every stream shares, the save/load round-trip (`ToSerializable`/
`FromSerializable`/`LoadFromSerializable`/`FastForwardCounter`'s no-rewind
guard), and the ad-hoc content-keyed `Rng(Player, ModelId, mixin, counter)`
constructor family (`make_encounter_rng`/`make_event_rng` and the general
ctor's formula). In short: the stream *map* and the primitive *draw
semantics* — not any particular consumer's draw count (each consumer's draw
count is that consumer's own seam or content record's problem), with four
call-site categories checked this batch as evidence for the call-site-map
requirement (relic/reward pulls, one card, combat-stream routing, cosmetic
per-relic skin rolls).

**Does NOT claim:**
- Any specific consumer's use of a stream beyond the four categories spot-
  checked this batch — e.g. how many `UpFront` draws run-init spends, or which
  draws `RewardsSet` spends on `Rewards`. That lives with whichever seam/
  content record owns that consumer. **Concretely decided this batch:**
  `event/EV-3` (GAP-QUEUE.md Tier 1 1A — 28 of 34 event modules draw on the
  shared `self.rng` instead of `self.event_rng`) is a consumer stream-CHOICE
  mistake, not a primitive/seeding/map mistake, and stays the event kind's
  mechanism (record guard G3). This seam's own check of the plumbing EV-3's
  fix would use (`make_event_rng`) came back faithful, which narrows EV-3 to a
  pure call-site fix with no seeding-layer prerequisite.
- `sts2_rl/run.py`'s instantiation of `RunRngSet`/`PlayerRngSet` as an object
  — `run.py` is a *consumer* of this seam (it builds one `RunRngSet` and one
  `PlayerRngSet` per run and hands accessors to callers), not a definer of
  stream identity. Claimed by `run_layer` instead (see that seam's doc). (This
  seam DOES cite `run.py` in `extra_sources` this batch, for one specific,
  narrow fact — the Rewards-stream relic-pull path, guard G4 — without taking
  ownership of `run.py`'s broader behaviour.)
- `GrabBag.cs`'s and `RelicGrabBag.cs`'s consumption of a stream (which draws
  it spends and how) — those are `rooms_and_map`'s and `relic_pools`' problem
  respectively; this seam only certifies what one draw *means*. (`GrabBag<T>`
  is also a plausible future consumer of the currently-dormant
  `WeightedNextItem`/`weighted_next_item` divergence — flagged for whoever
  ports a weighted `GrabBag` pick.)
- `EncounterModel.GenerateMonstersWithSlots`'s and `MonsterModel`'s own move-
  roll dispatch (which stream a MOVE roll comes off, and when) — that is
  `monster_state_machine`'s subject. This seam DOES claim the underlying fact
  that `combat_rng.monster_ai` is wired correctly as the accessor
  `MonsterMoveStateMachine`-style monsters resolve to (record guard G5, which
  also refutes a stale "unseeded draw at `state_machine.py:131`" claim
  inherited from a prior round — that line is now an unrelated duplicate-
  state-id guard, not an RNG call at all).
- The floor-34 / 89U-seed HP divergence's ROOT CAUSE (see "What this seam did
  NOT settle" above) — recorded as a cross-reference (guard G7), not claimed.

## Game sources claimed

Same 7 files the scaffold pinned, unchanged: `src/Core/Random/Rng.cs`,
`MegaRandom.cs`, `PlayerRngSet.cs`; `src/Core/Runs/RunRngSet.cs`;
`src/Core/Entities/Rngs/PlayerRngType.cs`, `RunRngType.cs`;
`src/Core/Helpers/StringHelper.cs`. Plus, in `extra_sources` (files this
record cites specific facts from without claiming their whole behaviour):
`src/Core/Extensions/ListExtensions.cs` (`StableShuffle`/`UnstableShuffle`),
`src/Core/Models/EncounterModel.cs` and `EventModel.cs` (the two purpose-built
content-keyed seed formulas), `src/Core/Runs/RunState.cs` (the `Rng` property
that is actually a `RunRngSet`), and `src/Core/Models/Relics/PaelsLegion.cs` /
`Byrdpip.cs` (the cosmetic `Skin` roll — note both game trees also have
unrelated MONSTER classes sharing those bare filenames; every citation to
these two files in the record uses the full `Relics/` path to disambiguate).

## Sim sources claimed

Same 2 files: `sts2_rl/rng.py`, `sts2_rl/combat_rng.py`. Plus, in
`extra_sources`: `sts2_rl/player.py` (`stable_shuffled_cards`/
`_compare_to_key`), `sts2_rl/actmap.py` (`stable_shuffle`), `sts2_rl/combat.py`
(`CombatState`'s `_rng`/`_niche`/`combat_rng` wiring), `sts2_rl/cards/
colorless_skills.py` (`CatastropheCard`), `sts2_rl/monsters/state_machine.py`
(`MachineMonster._move_rng`), `sts2_rl/events/_combat_layout.py`
(`pregenerate_monster_hp`), `sts2_rl/run.py` (`pull_relic_from_front`), and
`sts2_rl/monsters/base.py` (`Encounter.create_monsters`).

`sts2_rl/run.py` is claimed here only for the one narrow fact above — its
broader behaviour is `run_layer`'s sim source, not this seam's.

## The stream map (for every later batch to cite)

| stream (game) | stream (sim) | what draws off it | seeded from | reset when | verdict |
|---|---|---|---|---|---|
| `RunRngType.UpFront` | `RunRngSet.up_front` | run-init generation (monsters, events, relics offered up-front) | run seed + `snake_case("UpFront")` hash | never (run lifetime) | faithful (map layer only — consumer draw count is `run_layer`'s) |
| `RunRngType.Shuffle` | `RunRngSet.shuffle` / `combat_rng.shuffle` | deck reshuffle, `CardPilePosition.Random` inserts, `Catastrophe`/`BeatDown`'s StableShuffle-then-First | run seed + hash | never | faithful, incl. draw-count shape (step 20, executed) |
| `RunRngType.UnknownMapPoint` | `RunRngSet.unknown_map_point` | room-type roll at an unknown map point | run seed + hash | never | faithful (map layer; consumer is `rooms_and_map`) |
| `RunRngType.CombatCardGeneration` | `RunRngSet.combat_card_generation` / `combat_rng.card_gen` | in-combat card generation (Attack Potion, Bundle of Joy, Discovery, …) | run seed + hash | never | faithful (map layer; consumer draw counts are `creature_card_cmds`'/content's) |
| `RunRngType.CombatPotionGeneration` | `RunRngSet.combat_potion_generation` / `combat_rng.potion_gen` | in-combat potion generation (Alchemize) | run seed + hash | never | faithful |
| `RunRngType.CombatCardSelection` | `RunRngSet.combat_card_selection` / `combat_rng.card_selection` | random draw-pile picks (Thrash-class, True Grit, Seeker Strike's own StableShuffle stream override) | run seed + hash | never | faithful |
| `RunRngType.CombatEnergyCosts` | `RunRngSet.combat_energy_costs` / `combat_rng.energy` | Confusion/Snecko Oil random costs | run seed + hash | never | faithful |
| `RunRngType.CombatTargets` | `RunRngSet.combat_targets` / `combat_rng.targets` | random single-target picks (Bouncing Flask, Sword Boomerang, auto-play ANY_ENEMY) | run seed + hash | never | faithful |
| `RunRngType.MonsterAi` | `RunRngSet.monster_ai` / `combat_rng.monster_ai` | every monster move roll | run seed + hash | never | faithful — `MachineMonster._move_rng` always resolves here regardless of the monster's constructor `rng` arg (guard G5) |
| `RunRngType.Niche` | `RunRngSet.niche` | unique monster HP rolls; a handful of "don't care" relic effects (`CursedRun`, etc.) | run seed + hash | never | faithful for the HP-roll path (wired directly via `CombatState._niche`, not through `CombatRng`); other Niche consumers are content records' own subject |
| `RunRngType.CombatOrbs` | `RunRngSet.combat_orbs` | Chaos card orb generation | run seed + hash | never | waiver — Defect-only content, unreachable in the Ironclad-only sim (guard G2) |
| `RunRngType.TreasureRoomRelics` | `RunRngSet.treasure_room_relics` | multiplayer treasure-room tie-break | run seed + hash | never | waiver — multiplayer-only, unreachable in the single-player sim (guard G2) |
| `PlayerRngType.Rewards` | `PlayerRngSet.rewards` | card/potion/relic reward rolls, `PullNextRelicFromFront`'s rarity roll | run seed (slot 0 == run seed in single-player) + hash | never | faithful, incl. draw-count parity for a real relic (guard G4, executed) |
| `PlayerRngType.Shops` | `PlayerRngSet.shops` | merchant stock generation | run seed + hash | never | map layer faithful; a live counter divergence exists in ACT-2 MERCHANT CONTENT per the 89U xfail text (168 vs 140) — that is a shop-content consumer bug, not this seam's, flagged for `rooms_and_map`/shop content |
| `PlayerRngType.Transformations` | `PlayerRngSet.transformations` | card transform rolls | run seed + hash | never | faithful (map layer; consumer draw counts are `relic_pools`'/content's) |
| *(ad-hoc)* `Rng(Player, ModelId, mixin)` | `make_encounter_rng` / `make_event_rng` / inline call-site formulas | per-encounter monster-slot selection; per-event rolls; a few relics' cosmetic skin picks | run seed + `TotalFloor`(encounter only) + content-id hash | re-seeded fresh every construction (not a persistent counter-bearing stream) | faithful for the two named helpers (step 21, executed formula match); the general 3-arg ctor has no single sim helper but every checked call site re-derives the same formula inline |
| *(dormant)* `Rng.WeightedNextItem` | `rng.weighted_next_item` | nothing yet, on either side | n/a (draws off whichever stream calls it) | n/a | gap, `live: false` — float32-vs-double weight-sum precision, zero consumers in the decompiled game source and zero ported-content consumers in the sim (step 16, executed grep both ways) |

## What the next batches need to know

1. **The primitive/seeding layer is not where the 89U seed's remaining
   divergence lives.** Every fact this record checked came back faithful.
   Look at floor 34's actual combat mechanics (candidate: the act-1 boss,
   `ENCOUNTER.VANTOM_BOSS`) — `damage_pipeline`, `creature_card_cmds`,
   `monster_state_machine` or the encounter/monster content records are the
   likely owners, not this seam.
2. **`event/EV-3` is real, unfixed, and not this seam's** — see guard G3.
   Whoever works the event kind should read this record's step 21 first: the
   plumbing the fix would use is already faithful.
3. **`PlayerRngType.Shops`'s act-2 counter divergence (168 vs 140, per the
   89U xfail text) is a shop-content consumer bug**, not a stream-map bug —
   handed to `rooms_and_map`/shop content, not investigated further here.
4. **`WeightedNextItem`/`weighted_next_item` is a live landmine for whoever
   ports a weighted `GrabBag` pick** (`rooms_and_map`/`relic_pools` territory)
   — re-run `py audit/tools/rng_stream_probes.py weighted` the day a real
   consumer appears on either side; it will very likely still report 0/0
   until then, and stop being dormant the day it doesn't.
5. **The `test/test_conformance_player_state.py` xfail reason string for
   89U21BV1TZ is stale** (says "+3" HP at act-1, the current failure is "+6")
   — not fixed here (`test/` is off-limits to an audit batch), flagged for
   whoever next touches that file.
