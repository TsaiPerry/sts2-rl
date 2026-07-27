# Relic content audits — batch 7 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b07` (based on `audit-relic` @ 4542c32f)
**Units:** 15 · **Probes:** 18, in `tools/audit/relic_probes_b07.py` (this batch's own module; the shared `tools/audit/relic_probes.py` was used read-only for `turn-order`, `sweep-reset` and `sweep-isallowed`)

`py tools/audit/harness.py validate` → **66 records, 0 invalid**.
`py tools/audit/citation_check.py audits/relic` → **MISSING 0, OUT-OF-RANGE 0**.
`py tools/audit_status.py --kind relic` → `total 258 · audited 61 · invalid 0 · stale 0 · gaps 43 · unaudited 197`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged; no engine code was touched.

---

## Units and rollup verdicts

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `golden_pearl` | **gap** | 3 | 4 |
| `gorget` | **gap** | 2 | 5 |
| `gremlin_horn` | **gap** | 2 | 8 |
| `hand_drill` | **gap** | 2 | 7 |
| `happy_flower` | **gap** | 5 | 4 |
| `hefty_tablet` | **gap** | 3 | 10 |
| `horn_cleat` | **gap** | 2 | 5 |
| `ice_cream` | **gap** | 2 | 4 |
| `intimidating_helmet` | **gap** | 2 | 6 |
| `iron_club` | **gap** | 5 | 7 |
| `jeweled_mask` | **gap** | 2 | 7 |
| `jewelry_box` | waiver | 3 | 3 |
| `joss_paper` | **gap** | 7 | 7 |
| `juzu_bracelet` | **gap** | 3 | 3 |
| `kaleidoscope` | waiver | 4 | 3 |

13 of 15 roll up to `gap`. `jewelry_box` and `kaleidoscope` carry no divergence at all — their only non-`faithful` entries are the standard presentation waiver and, for `kaleidoscope`, the other-characters scope waiver.

---

## LIVE gaps (12), each with its executed evidence

1. **`iron_club` G1 — the threshold is wrong: the game draws every 4th card, the sim every 6th.**
   `IronClub.cs:38` is `new CardsVar(4)`; the port pins `CARDS = 6` and its own docstring asserts "CardsVar(6)". No `AscensionHelper` branch in the file and no second source file (`grep -rn IronClub src/ --include=*.cs`). *Executed (`relic_probes_b07.py club-count`):* the sim draws on plays 6 and 12 where the game draws on 4, 8 and 12. Obtainable via the ported Tanx shrine (`Tanx.cs:33`).
2. **`iron_club` G2 — a Replayed card advances the counter once, not once per iteration.** = `hook_dispatch` G4 at a new site. *Executed (`club-replay`):* `[iron_club, throwing_axe]`, one Strike played twice → `cards_played = 1` (C#: 2). Both relics come from the same Tanx shrine.
3. **`intimidating_helmet` G1 — the sim reads energy SPENT where C# reads the card's COST, so auto-plays cannot trigger it.** `ResourceInfo.cs:9-16` documents `EnergyValue` as the cost and `EnergySpent` as the spend, and `CardCmd.cs:123-128` sets `EnergySpent = 0, EnergyValue = cost` on the auto-play path. *Executed (`helmet-autoplay`):* auto-playing a 2-cost Dark Embrace gives block 0 (C#: 4); the manual control gives 4 on both sides.
4. **`intimidating_helmet` G2 — the 4 Block is granted once per play, not once per Replay iteration.** = `hook_dispatch` G4 on the `BeforeCardPlayed` half. *Executed (`helmet-replay`):* `[helmet, throwing_axe]` → block 4 with the power stacked to 2 (proving the replay happened); C# gives 8.
5. **`gremlin_horn` G1 — the relic pays nothing on an Illusion enemy that the game treats as really dead.** Two layers: C# fires `Hook.AfterDeath` on a prevented death too (`CreatureCmd.cs:566`), and the three ported revive powers override `ShouldCreatureBeRemovedFromCombatAfterDeath`, **not** `ShouldDie` (`grep -rln ShouldDie src/Core/Models/` → only `FairyInABottle`, `LizardTail`, two Mocks). *Executed (`horn-illusion`):* a lethal hit on Eye With Teeth (summoned by the ported act-1 Fogmog) leaves hp=1, `is_dead=False`, energy 3→3, hand 5→5; the game gives +1 energy and +1 card.
6. **`juzu_bracelet` `IsAllowed` — the `TotalFloor < 41` pool gate is unmodelled.** Confirms Sweep B (a)'s 16-relic cluster; *executed (`relic_probes.py sweep-isallowed`):* "sim Relic base defines is_allowed: False". Common in the transcribed grab bag, so it stays pullable past floor 41 and shifts every later pull.
7. **`juzu_bracelet` `ModifyUnknownMapPointRoomTypes` — "?" nodes still roll combats.** *Executed (`juzu-map`):* with the relic the allowed set is unchanged at `[ELITE, EVENT, MONSTER, SHOP, TREASURE]`, while the sibling `golden_compass`, which implements the same hook, correctly narrows it to `[EVENT]` — the sibling is what proves the `run.py:1046-1049` pipeline whole rather than merely present.
8. **`hefty_tablet` G1 — the Rare candidate pool is `FilterForCombat` where C# uses `GetUnlockedCards`.** *Executed (`tablet-pool`):* 23 candidates vs the game's 25; the missing two are `feed` and `not_yet` (both RARE, `can_be_generated_in_combat=False`). Two observables: those cards can never be offered, and a 23-item list returns a different card than a 25-item list for the same `Rewards` draw, so all three offers diverge on every seed.
9. **`joss_paper` G1 — `causedByEthereal` is a parameter of the exhaust CALL; the port infers it from `card.is_ethereal`.** = `turn_structure` G17, confirmed independently. *Executed (`joss-ethereal` leg 1):* five mid-turn exhausts of Dazed leave `cards_exhausted=0, _ethereal_pending=5` and draw nothing; the five-Defend control draws the card.
10. **`joss_paper` G2 — a vetoed hand flush strands the deferred credit forever.** = `turn_structure` G4 + G16. *Executed (`joss-ethereal` leg 2):* `[joss_paper]` credits and draws; `[joss_paper, runic_pyramid]` leaves `_ethereal_pending=5` and never draws.
11. **`joss_paper` `AfterCombatEnd` — the stranded `_ethereal_pending` crosses into the next combat.** C# clears `EtherealCount` at combat end and the port clears it nowhere. *Executed (`joss-ethereal` leg 3):* the same instance enters combat 2 holding 5.
12. **`horn_cleat` G1 — a prevented block clear also cancels the turn-2 block.** = `turn_structure` G1, which already names `HornCleat.cs:20-27` as its ported witness and pins it at `test/test_hook_order.py:601`. The relic's own arithmetic is exact: *executed (`cleat-turn2`)* block after the clear on turns 1-4 is 0, 14, 0, 0.

---

## DORMANT gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `golden_pearl` N2 | `Hook.AfterGoldGained` has no sim hook at all (`grep` → 0 hits) | porting any `AfterGoldGained` implementer — needs a new base-class hook first (Sweep C's tail list) |
| `happy_flower` N3 | `AfterModifyingEnergyGain` companion event and the `finalAmount > 0` gate missing from `EnergyCmd.gain` | any `AfterModifyingEnergyGain` implementer, or a `modify_energy_gain` listener that can drive the amount negative |
| `ice_cream` N2 | `modify_max_energy` is folded BEFORE `should_reset_energy`; C# branches first (= `turn_structure` step 17) | the first side-effecting `should_reset_energy` or `modify_max_energy` implementation — Ice Cream is the only ported reason the else-branch is ever taken |
| `gorget` N4 | `PlatingPower` decays at the sim's pre-draw slot, C#'s at `AfterSideTurnStart` (post-draw) | any turn-start effect between the two slots that scales off a Plating stack. **Belongs to the power stream**; recorded at Gorget's site because Gorget is the only ported player-side Plating source and `audits/power/` does not exist |
| `gremlin_horn` G2 | death resolves inside the sim's damage pipeline, before the dealer's post-damage event (= `damage_pipeline` step 18 / G6 / N2) | porting any `AfterDamageGiven` implementer that reads the player's energy or hand |
| `hand_drill` G1 | C# runs every `AfterBlockBroken` listener before `AfterDamageGiven`; the sim puts both on `on_block_broken` and lets registration order decide | a second `AfterBlockBroken` implementer (today: only `BurrowedPower.cs:24`, whole-source), or an ENEMY carrying Artifact so the order decides which debuff is negated |
| `hand_drill` G2 | the `dealer?.PetOwner == base.Owner` arm is dropped; the sim has no pet concept (`grep pet_owner\|PetOwner` → 0 hits) | porting a pet — `relics/base.py:91-92` carries an `adds_pet` flag for Pael's Legion with no creature behind it |
| `horn_cleat` G2 | the sim clears the player's block on turn 1 and the game does not (= `turn_structure` G6) | mis-reading the relic's guard as "the second clear" rather than `TurnNumber == 2`; recorded because G1 and G6 interact at this exact hook |
| `intimidating_helmet` N1 | the Block is granted before the card leaves the hand, and C# has an `Owner.IsDead` early return between the two points | a `modify_card_play_count` listener that can kill the player, or a Block reader in that window |
| `jeweled_mask` N3 | `SetToFreeThisTurn` is `EndOfTurn \| WhenPlayed`; the sim's `_free_this_turn` expires only at the next turn start | an effect that returns a played Power card to hand, or a second `set_free_this_turn` caller on a non-Power card. **Belongs to `cards/base.py`** (card stream) |
| `jeweled_mask` N4 | the port moves the card with two list ops, bypassing the hand cap | re-pointing the relic at a later slot, or an effect that fills the hand before `turn_structure` step 19 |
| `hefty_tablet` G2 | `CardFactory.CreateForReward` runs `Hook.TryModifyCardRewardOptions` (only `NoUpgradeRoll` is set); the port calls no such hook, so Silver Crucible would not upgrade its Rares | **any source that grants Hefty Tablet after floor 0.** Its only ported grant is Neow, where the player holds nothing but the starting relic; the C# `EventRelicPool` that lists it is a registry with no random puller (`grep -rn EventRelicPool src/` outside its own file → only the type table and `ModelDb`'s registration) |

---

## New bug classes and pool-wide shapes (for the relic stream to fold into `PROMPT.md`)

Each fired on a real unit in this batch. Two of them want a mechanical sweep before more batches run.

### Class A (NEW, **wants a sweep**) — a numeric constant that is wrong AND a docstring that misquotes the SOURCE

**Unit: `iron_club`.** Bug class 12 warns that a port's docstring claim *about the sim* is evidence and not truth. `iron_club` is the other half: its docstring claims a value *for the C# source* — "CardsVar(6)" — and the source says `CardsVar(4)`. A reader checking the port against its own docstring finds perfect agreement; only reading `IronClub.cs` catches it. This is the first numeric-constant defect in seven batches, and it was found by the step in the per-unit procedure that is easiest to skip ("check every numeric constant against the NON-ascension branch").

**The sweep it wants** is cheap and mechanical, and no existing sweep covers it: extract every `new *Var(<n>)` / `AscensionHelper.GetValueIfAscension` literal from each C# relic, extract the port's module-level and class-level integer constants, and report every relic where the multiset of C# constants is not a subset of the port's. It is the only one of the seven shapes so far that a script can decide with no reachability argument at all. **Not written here** — it belongs in the shared `relic_probes.py`, which the concurrency contract makes read-only to this batch.

### Class B (NEW, **cross-kind**) — `ResourceInfo.EnergySpent` and `EnergyValue` are collapsed into one number

**Unit: `intimidating_helmet`.** `ResourceInfo` carries two fields and its own doc comment (`ResourceInfo.cs:9-16`) says they differ on the auto-play path: cost 3, spend 0. The sim's `on_energy_spent(card, amount)` has one integer, and `combat.py:552` passes a literal `0` for every auto-play. Any C# model gated on `Resources.EnergyValue` therefore silently stops firing on auto-plays in the sim. Note the direction trap: `brilliant_scarf` G1 (batch 2) is the *same root cause pointing the other way* — there the sim counts an auto-play the game excludes. A fix must add the second field, not flip a flag. Worth a `grep -rn 'Resources.EnergyValue\|Resources.EnergySpent' src/Core/Models/` sweep across the relic, power and card streams.

### Class C (NEW, **cross-stream, high blast radius**) — death prevention modelled with `should_die` where the game only vetoes REMOVAL, so `AfterDeath` never fires

**Unit: `gremlin_horn`.** `IllusionPower`, `SteamEruptionPower` and `AdaptablePower` override `ShouldCreatureBeRemovedFromCombatAfterDeath` and `AfterDeath`; a whole-source `grep -rln ShouldDie src/Core/Models/` finds only `FairyInABottle`, `LizardTail` and two Mocks. In the game those creatures **really die** — HP 0, `AfterDeath` fires, they simply stay in the Enemies list and revive. The three sim ports return `should_die = False` instead, so the creature never dies and **every** `on_death` listener misses it. Compounding it, C# fires `AfterDeath` on a genuinely prevented death too (`CreatureCmd.cs:566`), which the sim never does. This is the memory note "death does not mean removal" applied to the wrong hook, it is reachable from a normal act-1 encounter, and it belongs to the power stream plus `cmds.py` — `audits/power/` does not exist yet, so no record owns it. `damage_pipeline`'s N4 and G4 do **not** cover it.

### Class D (NEW, **wants a sweep**) — the reward path using the combat-generation card pool

**Unit: `hefty_tablet`.** `cards/pool.py` exposes both `pool_card_ids()` (`FilterForCombat`) and `reward_pool_card_ids()` (`GetUnlockedCards`) and documents the difference, including the two casualties (`feed`, `not_yet`). `hefty_tablet` calls the combat one on a reward path. Since the choice changes both *which* cards exist and the *length of the list an `Rng.NextItem` draw indexes into*, it is a silent RNG-parity defect as well as a content one. Sweep: every sim call site of `pool_card_ids` that is reached from `after_obtained` / `modify_card_reward_options` / `modify_merchant_card_results` rather than from a combat hook.

### Class E (NEW, cheap but worth stating) — a false docstring claim that ACQUITS the port

**Unit: `happy_flower`.** The port's docstring says "the game's counter persists between combats; the sim's resets each combat". The second half is false — relic instances live on `RunState.relics`, so `turns_seen` carries — and that falsehood is exactly why the port is faithful to C#'s `[SavedProperty] TurnsSeen`. *Executed (`flower-carry`):* one turn in each of three consecutive combats on the same instance gives `turns_seen = 1, 2, 0` with the free energy landing in combat 3. `relics/base.py:20-24`'s "the sim runs a single combat, so per-run counters … are per-combat" is stale for the same reason. Class 12's inverse: a reviewer who trusts the docstring would "fix" a correct relic into `belt_buckle`'s shape. Three units in this batch (`happy_flower`, `iron_club`, `joss_paper`) hinge on this and all three are faithful — the trace bug class 13 asks for terminates at "no reset on either side".

### Class F (observation, not yet a class) — hand-rolled reward generation drops the reward hooks

`hefty_tablet` G2 and `kaleidoscope` N2 are the same question with opposite answers: `HeftyTablet` does *not* set `CardCreationFlags.NoCardPoolModifications`, so its options go through `TryModifyCardRewardOptions`, while `Kaleidoscope` *does* set it. Any port that builds card options with `make_card` instead of going through `rewards.py` needs the flag checked before it can be called complete. One instance so far, so it is reported rather than proposed as a class.

---

## Cross-record notes (binding rule 3)

**No verdict disagreement was found.** Eight mechanisms already carried a verdict in the seam tier and all eight are reproduced with the same verdict, cited, not re-derived: `turn_structure` G1 (`horn_cleat`), G4+G16 (`joss_paper`), G6 (`horn_cleat`), G17 (`joss_paper`), step 17 (`ice_cream`), `hook_dispatch` G4 (`iron_club`, `intimidating_helmet`), `damage_pipeline` N5 (`hand_drill`), G6/N2/step 18 (`gremlin_horn`). `relic/bronze_scales`'s `AfterRoomEntered → on_combat_start` divergence is matched by `gorget`, and `relic/calling_bell` G3's player-choice house rule is matched by `hefty_tablet` G3.

Three **factual refinements** to existing records, none of which changes a verdict:

- `damage_pipeline` guard **N5** describes Hand Drill as a listener on `AfterBlockBroken`. `HandDrill.cs:22` actually overrides **`AfterDamageGiven`** and self-filters on `result.WasBlockBroken`; the two C# hooks are 12 lines apart in the same per-result loop, so N5's verdict and its "reads neither HP nor death state" reasoning both still hold. It matters only for the ordering question, which is recorded as `hand_drill` G1.
- Sweep A files `happy_flower` under "reset at a TURN boundary only (art_of_war shape)". The write it detects is an **increment**, not a reset, and the correct classification is "no reset on either side" (see class E).
- Sweep A ran `joss_paper` through `sweep-reset-exec` and it "agreed with a fresh instance", because `_ethereal_pending` settles at 0 in an unvetoed turn. It is confirmed LIVE here through the flush-veto path — an instance of the sweep's own documented risk that a field-level diff can clear its own founding example.

## Roster mis-resolutions

**None.** All 15 units resolved to a real C# file on the first `harness.py skeleton` call, and `tools/audit/name_overrides.json` needs no additions. Obtainability confirmed for all 15 by execution (`relic_probes_b07.py pool`): **8** via the transcribed grab bag (`gorget` Common, `gremlin_horn` Uncommon, `happy_flower` Common, `horn_cleat` Uncommon, `ice_cream` Rare, `intimidating_helmet` Rare, `joss_paper` Uncommon, `juzu_bracelet` Common) and **7** via ported events (Neow ×3 for `golden_pearl` / `hefty_tablet` / `kaleidoscope`, Trash Heap for `hand_drill`, Tanx for `iron_club`, Vakuu for `jeweled_mask`, Nonupeipe for `jewelry_box`); `gremlin_horn` additionally via Calling Bell.

## Left unverified / out of scope

- **`hand_drill` G1's Artifact leg.** Whether any ported ENEMY can carry Artifact was not settled — the record therefore rests G1's dormancy on the `BurrowedPower` census (one whole-source `AfterBlockBroken` override) and names the enemy-Artifact question as an open trigger rather than claiming it impossible.
- **Class A's sweep was not written.** It belongs in `tools/audit/relic_probes.py`, which the concurrency contract makes read-only to this batch. Same for class B's and class D's greps.
- **`gorget` N4, `jeweled_mask` N3 and `gremlin_horn` G1 are not this stream's to fix** — they live in `sts2_rl/powers.py`, `sts2_rl/cards/base.py` and `sts2_rl/cmds.py`. They are recorded at the relic sites where they become observable because no `audits/power/` or `audits/card/` record exists yet to own them.
- **Potions** were not reached by any unit in this batch, so the contract's potion deferral never bound.
