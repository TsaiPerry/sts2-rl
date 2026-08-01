# Batch `relic-2` — unlabelled gap entries to settle

14 entries across 13 record files. **These record files are yours alone; no other agent writes them.**

## `relic/bag_of_marbles`  → `audit/records/relic/bag_of_marbles.json`

- **`relic/bag_of_marbles/BeforeSideTurnStart`** (section `hooks`, key `BeforeSideTurnStart`, mechanism `relic/bag_of_marbles/BeforeSideTurnStart`)
  - what: BeforeSideTurnStart
  - issue: STILL OPEN on the ENEMY SET only. The HOOK SLOT is CLOSED: BagOfMarbles.cs:23 declares BeforeSideTurnStart and the relic is on the sim's new `before_side_turn_start` dispatcher (CombatManager.cs:458), which fires before the block clear -- the slot this rollup's G1 was filed for. WHAT REMAINS is G2, the enemy set built from a weaker predicate than the source's.  NARROWED 2026-07-28 (round 3) by the gap-queue continuation's post-section-A pass; what follows is what is still open. The issue it replaced read: Rollup of guards G1 and G2 per binding rule 4. The effect is right -- 1 Vulnerable (PowerVar<VulnerablePower>(1m), BagOfMarbles.cs:19) to every enemy on turn 1, applier = the player -- but the hook slot and the enemy set are both off.
  - citations: BagOfMarbles.cs:19, BagOfMarbles.cs:23, CombatManager.cs:458

## `relic/charons_ashes`  → `audit/records/relic/charons_ashes.json`

- **`relic/charons_ashes/AfterCardExhausted`** (section `hooks`, key `AfterCardExhausted`, mechanism `relic/charons_ashes/AfterCardExhausted`)
  - what: AfterCardExhausted
  - issue: Rollup of guard G1 per binding rule 4. Amount, props, dealer, card source and the absence of any once-per-turn limit all match; the target SET is built from a different predicate (G1), and the multi-target damage is issued as N sequential single-target calls rather than one batched call (G3).

## `relic/festive_popper`  → `audit/records/relic/festive_popper.json`

- **`relic/festive_popper/AfterPlayerTurnStart`** (section `hooks`, key `AfterPlayerTurnStart`, mechanism `relic/festive_popper/AfterPlayerTurnStart`)
  - what: AfterPlayerTurnStart
  - issue: STILL OPEN at G2 and G3. G1, the slot, is CLOSED: FestivePopper.cs declares AfterPlayerTurnStart and `on_player_turn_started` is now that hook alone -- the AfterSideTurnStart listeners it used to share a registration-ordered walk with are on the new `after_side_turn_start`, fired strictly later. WHAT REMAINS: G2, the enemy set built from a weaker predicate, and G3, the hand-rolled inline win check.  NARROWED 2026-07-28 (round 3) by the gap-queue continuation's post-section-A pass; what follows is what is still open. The issue it replaced read: Rollup of guards G1, G2 and G3 per binding rule 4. The effect's numbers are right -- DamageVar(9m, ValueProp.Unpowered) (FestivePopper.cs:17) vs DAMAGE = 9 at DamageProps.NON_CARD_UNPOWERED (festive_popper.py:19, :27), no AscensionHelper branch in the file, dealer = the player on both sides, turn 1 only -- but the hook slot is a step late (G1), the enemy set is built from a weaker predicate (G2), and the win check the source performs after the whole turn-start sequence is hand-rolled inline instead (G3).
  - citations: FestivePopper.cs:17, festive_popper.py:19

## `relic/gambling_chip`  → `audit/records/relic/gambling_chip.json`

- **`relic/gambling_chip/AfterPlayerTurnStart`** (section `hooks`, key `AfterPlayerTurnStart`, mechanism `relic/gambling_chip/AfterPlayerTurnStart`)
  - what: AfterPlayerTurnStart
  - issue: Rollup of guards G1, G2 and G3 per binding rule 4. The hook SLOT is right and the turn gate matches, but CardCmd.DiscardAndDraw does two things the sim's inline loop does not: it routes each discard through CardPileCmd.Add (G2) and, after the draw, it AUTO-PLAYS every discarded card that was Sly this turn (G1). The selector's `min = 0` is also collapsed (G3). [2026-07-26 fix pass: guard G3 is now also a gap -- the min-0 decline is unreachable in the sim.]

## `relic/hefty_tablet`  → `audit/records/relic/hefty_tablet.json`

- **`relic/hefty_tablet/AfterObtained`** (section `hooks`, key `AfterObtained`, mechanism `relic/hefty_tablet/AfterObtained`)
  - what: AfterObtained
  - issue: Rollup of guards G1, G2 and G3 per binding rule 4. The skeleton is right -- three Rare candidates on the Rewards stream with prior picks excluded and no upgrade roll, a choose-one screen, then the chosen card and an Injury appended to the deck in that order -- and guards N1-N4 confirm each of those clauses individually. What diverges is the CANDIDATE POOL (G1: FilterForCombat instead of GetUnlockedCards, so Feed and Not Yet can never be offered), the dropped card-reward-options hook (G2) and the skip the sim cannot express (G3).

## `relic/letter_opener`  → `audit/records/relic/letter_opener.json`

- **`relic/letter_opener/AfterCardPlayed`** (section `hooks`, key `AfterCardPlayed`, mechanism `relic/letter_opener/AfterCardPlayed`)
  - what: AfterCardPlayed
  - issue: NARROWED 2026-07-27. The per-Replay half (G1) is CLOSED: CombatState._resolve_card_play fires on_card_played inside the play-count loop (sts2_rl/combat.py:574, 597-600). WHAT REMAINS is guard G2, the target set: LetterOpener.cs damages HittableEnemies and sts2_rl/relics/letter_opener.py still loops `self.living_enemies()`, which sts2_rl/relics/base.py:386-389 filters on `not e.is_gone` alone, with no Hook.ShouldAllowHitting term.
  - citations: sts2_rl/combat.py:574, sts2_rl/relics/base.py:386-389

## `relic/paper_phrog`  → `audit/records/relic/paper_phrog.json`

- **`relic/paper_phrog/ModifyVulnerableMultiplier`** (section `hooks`, key `ModifyVulnerableMultiplier`, mechanism `relic/paper_phrog/ModifyVulnerableMultiplier`)
  - what: ModifyVulnerableMultiplier
  - issue: Rollup of guards G1 and N2 per binding rule 4. NOT a Hook override: PaperPhrog.cs:16 is a plain public method, and its ONE caller is VulnerablePower.ModifyDamageMultiplicative, which looks the relic up directly on the dealer (`dealer.Player?.GetRelic<PaperPhrog>()`, VulnerablePower.cs:40-44). The sim turns that direct lookup into a real hook chain, which is where G1's divergence in the DISPATCH SET comes from; the +0.25 itself (PaperPhrog.cs:26 vs paper_phrog.py:23) and the 1.5 base it modifies (VulnerablePower.cs:22's `DamageIncrease` 1.5m vs powers.py:411) match, with no AscensionHelper.GetValueIfAscension in either file.
  - citations: PaperPhrog.cs:16, PaperPhrog.cs:26, VulnerablePower.cs:22, VulnerablePower.cs:40-44, paper_phrog.py:23, powers.py:411

## `relic/philosophers_stone`  → `audit/records/relic/philosophers_stone.json`

- **`relic/philosophers_stone/AfterCreatureAddedToCombat`** (section `hooks`, key `AfterCreatureAddedToCombat`, mechanism `relic/philosophers_stone/AfterCreatureAddedToCombat`)
  - what: AfterCreatureAddedToCombat
  - issue: Rollup of guard G1 per binding rule 4. The effect and the constant are right -- 1 Strength on each joiner, executed at b12-stone: a mid-combat SpinyToad spawn comes in at Strength(1) -- and the two hooks provably cannot double-apply (guard N1). The divergence is the side test: C# skips creatures on the OWNER's side (`creature.Side == base.Owner.Creature.Side`, PhilosophersStone.cs:43) while the sim skips only the player object itself (`creature is self.combat.player`, philosophers_stone.py:39).
  - citations: PhilosophersStone.cs:43, philosophers_stone.py:39

## `relic/ruined_helmet`  → `audit/records/relic/ruined_helmet.json`

- **`relic/ruined_helmet/TryModifyPowerAmountReceived`** (section `hooks`, key `TryModifyPowerAmountReceived`, mechanism `relic/ruined_helmet/TryModifyPowerAmountReceived`)
  - what: TryModifyPowerAmountReceived
  - issue: Rollup of guards G2 and G3 per binding rule 4. The four C# clauses are reproduced exactly -- `canonicalPower is StrengthPower`, `target == Owner.Creature`, `amount <= 0`, `UsedThisCombat` (RuinedHelmet.cs:35-50) against ruined_helmet.py:31-37 -- and so is the `modifiedAmount *= 2m` (RuinedHelmet.cs:51 vs :38). EXECUTED (`py audit/tools/relic_probes_b13.py ruined-helmet`): a first +2 Strength lands as 4 and a second as +2 (total 6), which is C#'s answer; an applier=None application is also doubled, matching the fact that neither side has an applier clause here. What is verdicted is the RECEIVED-side phase being collapsed into the sim's single flat chain (G2) and the After-event's side effect being hand-inlined (G3).
  - citations: RuinedHelmet.cs:35-50, RuinedHelmet.cs:51, ruined_helmet.py:31-37
- **`relic/ruined_helmet/AfterModifyingPowerAmountReceived`** (section `hooks`, key `AfterModifyingPowerAmountReceived`, mechanism `relic/ruined_helmet/AfterModifyingPowerAmountReceived`)
  - what: AfterModifyingPowerAmountReceived
  - issue: Rollup of guard G3 per binding rule 4. RuinedHelmet.cs:55-60 is a SEPARATE C# hook that fires only for listeners whose Try returned true (Hook.cs:1917-1931 collects them into `receivedModifiers`; PowerCmd.cs:152 and :242 dispatch to exactly those), and only after the amount has actually been set. The sim folds the 'mark used' effect into the modifier itself, which is audit/records/seam/power_cmd.json gap G4.
  - citations: Hook.cs:1917-1931, PowerCmd.cs:152, RuinedHelmet.cs:55-60

## `relic/spiked_gauntlets`  → `audit/records/relic/spiked_gauntlets.json`

- **`relic/spiked_gauntlets/TryModifyEnergyCostInCombat`** (section `hooks`, key `TryModifyEnergyCostInCombat`, mechanism `relic/spiked_gauntlets/TryModifyEnergyCostInCombat`)
  - what: TryModifyEnergyCostInCombat
  - issue: Rollup of guards G1, G2 and G3 per binding rule 4. The arithmetic is right -- a Power card costs 1 more -- but the sim has no phase structure and no per-creature listener grouping, and this relic is the named ported witness for BOTH of audit/records/seam/hook_dispatch.json's gaps G2 and G3.

## `relic/stone_cracker`  → `audit/records/relic/stone_cracker.json`

- **`relic/stone_cracker/AfterRoomEntered`** (section `hooks`, key `AfterRoomEntered`, mechanism `relic/stone_cracker/AfterRoomEntered`)
  - what: AfterRoomEntered
  - issue: NARROWED 2026-07-27. The shuffle half (G1) is CLOSED: sts2_rl/relics/stone_cracker.py now feeds actmap.stable_shuffle the pile in the game's top-at-index-0 orientation (`list(reversed(upgradable))`) with `key=_compare_to_key`, over crng.card_selection. WHAT REMAINS is guard G2: the C# hook is AfterRoomEntered, which CombatRoom.cs:228 fires one full dispatch BEFORE Hook.BeforeCombatStart, and the port still hangs the effect off `on_combat_start` -- the sim's BeforeCombatStart slot. Twelve ported relics share that mapping.
  - citations: CombatRoom.cs:228

## `relic/sword_of_jade`  → `audit/records/relic/sword_of_jade.json`

- **`relic/sword_of_jade/AfterRoomEntered`** (section `hooks`, key `AfterRoomEntered`, mechanism `relic/sword_of_jade/AfterRoomEntered`)
  - what: AfterRoomEntered
  - issue: Rollup of guards G1 and N1 per binding rule 4. The power, the amount and the target are right and executed; the hook SITE is one dispatch later than C#'s and the applier identity differs.

## `relic/vambrace`  → `audit/records/relic/vambrace.json`

- **`relic/vambrace/g6`** (section `guards`, key `g6`, mechanism `relic/vambrace/g6`)
  - what: N3: the port's docstring claims 'The multiplier hook stays stateless (safe for previews)' (vambrace.py:14-16)
  - issue: PROMPT.md bug class 24 -- a docstring that misdescribes the PORT. The multiplier hook is NOT stateless: vambrace.py:32 reads `self._used`, which is exactly the per-combat state. The claim reads as a justification for putting the latch in on_block_gained, and it is the sentence that makes G3 look intentional. Filed as a gap entry rather than a note because the misdescription is load-bearing for a reader deciding whether the port is correct -- but the verdict-carrying divergence is G3's, not this entry's; this entry adds no new observable.
  - citations: vambrace.py:14-16, vambrace.py:32
