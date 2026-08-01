# Batch `relic-1` — unlabelled gap entries to settle

14 entries across 13 record files. **These record files are yours alone; no other agent writes them.**

## `relic/archaic_tooth`  → `audit/records/relic/archaic_tooth.json`

- **`relic/archaic_tooth/AfterObtained`** (section `hooks`, key `AfterObtained`, mechanism `relic/archaic_tooth/AfterObtained`)
  - what: AfterObtained
  - issue: Rollup of guards G1 and G2 per binding rule 4. The transform itself is right -- first deck card whose id is a TranscendenceUpgrades key (ArchaicTooth.cs:146 vs archaic_tooth.py:23-25), replaced via run.transform_card(into=) -- but the upgrade-carry and enchantment-carry clauses of GetTranscendenceTransformedCard (ArchaicTooth.cs:149-166) are each reproduced with a different condition than the source.
  - citations: ArchaicTooth.cs:146, ArchaicTooth.cs:149-166, archaic_tooth.py:23-25

## `relic/booming_conch`  → `audit/records/relic/booming_conch.json`

- **`relic/booming_conch/AfterSideTurnStart`** (section `hooks`, key `AfterSideTurnStart`, mechanism `relic/booming_conch/AfterSideTurnStart`)
  - what: AfterSideTurnStart
  - issue: STILL OPEN on the ENERGY-GAIN CHAIN only. The HOOK SLOT is CLOSED: BoomingConch.cs:45 declares AfterSideTurnStart and the relic moved from the pre-draw slot to the new `after_side_turn_start` dispatcher (CombatManager.cs:522). WHAT REMAINS is the other guard: the grant bypasses the energy-gain modifier chain.  NARROWED 2026-07-28 (round 3) by the gap-queue continuation's post-section-A pass; what follows is what is still open. The issue it replaced read: Rollup of guards G1 and G2 per binding rule 4. The energy amount and the Elite/turn-1 conditions are right (executed: Elite turn-1 energy is 4 = base 3 + 1), but the hook slot is wrong and the grant bypasses the energy-gain modifier chain.
  - citations: BoomingConch.cs:45, CombatManager.cs:522

## `relic/fake_strike_dummy`  → `audit/records/relic/fake_strike_dummy.json`

- **`relic/fake_strike_dummy/ModifyDamageAdditive`** (section `hooks`, key `ModifyDamageAdditive`, mechanism `damage_pipeline/G3`)
  - what: ModifyDamageAdditive
  - issue: NARROWED 2026-07-27. The hoisted-props half (N1) is CLOSED: the hook carries `props`, DamageCmd.deal runs the chain unconditionally (sts2_rl/hooks.py:185-208, sts2_rl/cmds.py:120-133) and sts2_rl/relics/fake_strike_dummy.py self-gates on `is_powered_attack(props)`, which is FakeStrikeDummy.cs:23-26. WHAT REMAINS is guard G1: FakeStrikeDummy.cs:35-38's fourth clause is an AND of two negatives -- decline only when the dealer is not the owner's creature AND the card is not the owner's -- and the port still narrows it to `dealer is self.player`, so the same Strike with dealer=None lands for 6 where C# gives 7.
  - citations: FakeStrikeDummy.cs:23-26, FakeStrikeDummy.cs:35-38, sts2_rl/cmds.py:120-133, sts2_rl/hooks.py:185-208

## `relic/fur_coat`  → `audit/records/relic/fur_coat.json`

- **`relic/fur_coat/AfterCreatureAddedToCombat`** (section `hooks`, key `AfterCreatureAddedToCombat`, mechanism `relic/fur_coat/AfterCreatureAddedToCombat`)
  - what: AfterCreatureAddedToCombat
  - issue: Two divergences, both inherited rather than local. (a) C# fires Hook.AfterCreatureAddedToCombat for the STARTING creatures as well -- CombatManager.StartCombatInternal loops `foreach (Creature creature in _state.Creatures) await AfterCreatureAdded(creature)` (CombatManager.cs:394-398) BEFORE Hook.BeforeCombatStart (:403) -- whereas the sim's on_creature_added is dispatched only from the mid-combat summon path (cmds.py:266). For Fur Coat this is shadowed: on_combat_start covers the starting enemies with the identical effect, so the observable is the same. (b) The act check and the SetCurrentHp substitution are the same guards G1/G3 as BeforeCombatStart, which this entry carries as a rollup per binding rule 4. `creature.Side == CombatSide.Enemy` maps to `creature.side == 'enemy'` (fur_coat.py:86).
  - citations: CombatManager.cs:394-398, cmds.py:266, fur_coat.py:86

## `relic/gremlin_horn`  → `audit/records/relic/gremlin_horn.json`

- **`relic/gremlin_horn/AfterDeath`** (section `hooks`, key `AfterDeath`, mechanism `relic/gremlin_horn/AfterDeath`)
  - what: AfterDeath
  - issue: Rollup of guards G1 and G2 per binding rule 4. The relic's own body is exact -- GremlinHorn.cs:24-32's side check, EnergyVar(1) and CardsVar(1) map one-for-one onto gremlin_horn.py:19-22, and EXECUTED (py audit/tools/relic_probes_b07.py horn-death) an enemy death takes energy 3 -> 4 and hand 5 -> 6 while a player-side death changes neither. What diverges is WHICH deaths reach the hook (G1: the sim never fires on_death for a prevented death, and C# does) and WHEN relative to the dealer's own post-damage event (G2).
  - citations: GremlinHorn.cs:24-32, gremlin_horn.py:19-22

## `relic/kusarigama`  → `audit/records/relic/kusarigama.json`

- **`relic/kusarigama/AfterCardPlayed`** (section `hooks`, key `AfterCardPlayed`, mechanism `relic/kusarigama/AfterCardPlayed`)
  - what: AfterCardPlayed
  - issue: NARROWED 2026-07-27. The per-Replay half (G1) is CLOSED: CombatState._resolve_card_play fires on_card_played inside the play-count loop (sts2_rl/combat.py:574, 597-600). WHAT REMAINS is guard G2, the candidate list: Kusarigama.cs picks with `RunState.Rng.CombatTargets.NextItem(HittableEnemies)` and sts2_rl/relics/kusarigama.py still passes `self.living_enemies()`, which sts2_rl/relics/base.py:386-389 filters on `not e.is_gone` alone -- no Hook.ShouldAllowHitting term -- so an alive-but-unhittable enemy is still eligible to be drawn.
  - citations: sts2_rl/combat.py:574, sts2_rl/relics/base.py:386-389

## `relic/lizard_tail`  → `audit/records/relic/lizard_tail.json`

- **`relic/lizard_tail/ShouldDieLate`** (section `hooks`, key `ShouldDieLate`, mechanism `relic/lizard_tail/ShouldDieLate`)
  - what: ShouldDieLate
  - issue: NARROWED 2026-07-27. Guards G1, G2, G4 and N1 are CLOSED -- see those guards: the port now uses `should_die_late` and `after_preventing_death` (sts2_rl/relics/lizard_tail.py), HookSystem runs the ShouldDie/ShouldDieLate passes separately (sts2_rl/hooks.py:153-180, 843-854), CreatureCmd.kill routes through _resolve_death (sts2_rl/cmds.py:285-292) and the prevented death is no longer floored at 1 HP (sts2_rl/cmds.py:51-64). WHAT REMAINS is guard G3: the port still sets `self._used = True` and `self._heal_pending = True` INSIDE `should_die_late`, where LizardTail.ShouldDieLate (LizardTail.cs:40-51) is pure and WasUsed is written in AfterPreventingDeath (:56). Any caller that uses should_die as a bare predicate -- cards/breakthrough.py's `if p.hp <= 0 and ctx.hooks.should_die(p)` -- still burns the relic for nothing.
  - citations: LizardTail.cs:40-51, sts2_rl/cmds.py:285-292, sts2_rl/cmds.py:51-64, sts2_rl/hooks.py:153-180
- **`relic/lizard_tail/AfterPreventingDeath`** (section `hooks`, key `AfterPreventingDeath`, mechanism `relic/lizard_tail/AfterPreventingDeath`)
  - what: AfterPreventingDeath
  - issue: NARROWED 2026-07-27. Guards G1, G2, G4 and N1 are CLOSED -- see those guards: the port now uses `should_die_late` and `after_preventing_death` (sts2_rl/relics/lizard_tail.py), HookSystem runs the ShouldDie/ShouldDieLate passes separately (sts2_rl/hooks.py:153-180, 843-854), CreatureCmd.kill routes through _resolve_death (sts2_rl/cmds.py:285-292) and the prevented death is no longer floored at 1 HP (sts2_rl/cmds.py:51-64). WHAT REMAINS is guard G3: the port still sets `self._used = True` and `self._heal_pending = True` INSIDE `should_die_late`, where LizardTail.ShouldDieLate (LizardTail.cs:40-51) is pure and WasUsed is written in AfterPreventingDeath (:56). Any caller that uses should_die as a bare predicate -- cards/breakthrough.py's `if p.hp <= 0 and ctx.hooks.should_die(p)` -- still burns the relic for nothing.
  - citations: LizardTail.cs:40-51, sts2_rl/cmds.py:285-292, sts2_rl/cmds.py:51-64, sts2_rl/hooks.py:153-180

## `relic/miniature_cannon`  → `audit/records/relic/miniature_cannon.json`

- **`relic/miniature_cannon/ModifyDamageAdditive`** (section `hooks`, key `ModifyDamageAdditive`, mechanism `relic/miniature_cannon/ModifyDamageAdditive`)
  - what: ModifyDamageAdditive
  - issue: Rollup of guard G1 per binding rule 4. Three of C#'s four early returns are reproduced exactly (N1-N3, all executed); the fourth is an AND that the port narrows to one of its two disjuncts.

## `relic/pen_nib`  → `audit/records/relic/pen_nib.json`

- **`relic/pen_nib/AfterCardPlayed`** (section `hooks`, key `AfterCardPlayed`, mechanism `relic/pen_nib/AfterCardPlayed`)
  - what: AfterCardPlayed
  - issue: Rollup of guards G1 and G3. The unmark logic is identical (PenNib.cs:154-166: bail unless AttackToDouble is this card, then null it), but the same per-iteration/per-play mismatch applies -- C# fires it at CardModel.cs:1959, INSIDE the play-count loop, so the game clears the mark at the end of iteration 0 and iteration 1 of a replayed 10th Attack is NOT doubled, where the sim clears it only after every iteration and doubles them all. Executed: a Throwing-Axe-replayed 10th Strike costs the enemy 24 HP in the sim (12 + 12) against the game's 18 (12 + 6) -- py audit/tools/relic_probes_b12.py b12-pennib.
  - citations: CardModel.cs:1959, PenNib.cs:154-166

## `relic/silver_crucible`  → `audit/records/relic/silver_crucible.json`

- **`relic/silver_crucible/ShouldGenerateTreasure`** (section `hooks`, key `ShouldGenerateTreasure`, mechanism `relic/silver_crucible/ShouldGenerateTreasure`)
  - what: ShouldGenerateTreasure
  - issue: Rollup of guard G3 per binding rule 4. The predicate matches (`TreasureRoomsEntered > 1`, SilverCrucible.cs:146) and so does the all-must-agree dispatcher (`if (!item.ShouldGenerateTreasure(player)) return false`, Hook.cs:2316-2322). What diverges is WHAT the gate covers: C# reaches the Spoils Map payout only inside the gated DoTreasureRoomRewards, and the sim pays map-point quests outside the gate (G3).
  - citations: Hook.cs:2316-2322, SilverCrucible.cs:146

## `relic/stone_calendar`  → `audit/records/relic/stone_calendar.json`

- **`relic/stone_calendar/BeforeSideTurnEnd`** (section `hooks`, key `BeforeSideTurnEnd`, mechanism `relic/stone_calendar/BeforeSideTurnEnd`)
  - what: BeforeSideTurnEnd
  - issue: Rollup of guards G1 and G2 per binding rule 4. The trigger turn, the damage number, the target set and the props all match and are executed; the divergences are the flattened sub-phase ordering (G1) and the living_enemies-vs-HittableEnemies set (G2).

## `relic/strike_dummy`  → `audit/records/relic/strike_dummy.json`

- **`relic/strike_dummy/ModifyDamageAdditive`** (section `hooks`, key `ModifyDamageAdditive`, mechanism `damage_pipeline/G3`)
  - what: ModifyDamageAdditive
  - issue: NARROWED 2026-07-27. The hoisted-props half (G1) is CLOSED: the hook carries `props`, DamageCmd.deal runs the chain unconditionally (sts2_rl/hooks.py:185-208, sts2_rl/cmds.py:120-133) and sts2_rl/relics/strike_dummy.py self-gates on `is_powered_attack(props)`, which is StrikeDummy.cs:21-23. WHAT REMAINS is guard G2: StrikeDummy.cs:33-36 is `if (dealer != Owner.Creature && cardSource.Owner != Owner) return 0` -- either disjunct alone suffices -- and the port still requires `dealer is self.player` and never consults the card's owner.
  - citations: StrikeDummy.cs:21-23, StrikeDummy.cs:33-36, sts2_rl/cmds.py:120-133, sts2_rl/hooks.py:185-208

## `relic/unsettling_lamp`  → `audit/records/relic/unsettling_lamp.json`

- **`relic/unsettling_lamp/BeforePowerAmountChanged`** (section `hooks`, key `BeforePowerAmountChanged`, mechanism `relic/unsettling_lamp/BeforePowerAmountChanged`)
  - what: BeforePowerAmountChanged
  - issue: The latch is not separable from the double in the sim, which is what makes guards G2 and G3 possible: C# runs seven latch guards (UnsettlingLamp.cs:73-100) and a DIFFERENT five-guard set on the multiplicative (lines 108-127), and the two sets are not the same. Specifically the C# multiplicative has NO target-side check and NO applier check, while the sim applies `applier is not self.player or target is self.player` (unsettling_lamp.py:47) to both roles at once. Each resulting divergence is verdicted at its own guard (G2, G3, G4, G5); this hook entry carries their rollup per binding rule 4.
  - citations: UnsettlingLamp.cs:73-100, unsettling_lamp.py:47
