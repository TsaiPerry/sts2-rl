# Batch `power-2` — unlabelled gap entries to settle

11 entries across 10 record files. **These record files are yours alone; no other agent writes them.**

## `power/adaptable`  → `audit/records/power/adaptable.json`

- **`power/adaptable/g5`** (section `guards`, key `g5`, mechanism `power/_death_prevention_branch`)
  - what: The prevention branch's HP contract: sim `hp = 1` vs C# leaving the creature at 0 and re-entering KillWithoutCheckingWinCondition
  - issue: NARROWED 2026-07-27. THE FLOOR IS GONE: `_resolve_death`'s prevention arm (cmds.py:51-64) no longer writes `target.hp = 1`; it leaves the creature dead at 0 HP, sets `retained_after_death = True`, fires `on_death(..., True)` and then `after_preventing_death` -- CreatureCmd.cs:560-571's shape. The 1-vs-0 HP number conformance asserts on now matches, and the downstream consequences this entry listed go with it (Feed's `if target.is_dead` scores, and steam_eruption's HP restore no longer depends on the floor -- it moved to `on_death`, powers.py:2144-2151). WHAT REMAINS: the sim still does not model C#'s RE-ENTRY. CreatureCmd.cs:562-565 re-enters `KillWithoutCheckingWinCondition(creature, force, recursion + 1)` while `creature.IsDead`, up to 10 times before throwing InvalidOperationException; `_resolve_death`'s else-arm simply returns. So a prevention that heals nothing is permanent in the sim and re-kills in the game, and the sim still cannot express a prevention that fails. VERIFIED by reading cmds.py:30-64.
  - citations: CreatureCmd.cs:560-571, CreatureCmd.cs:562-565, cmds.py:30-64, cmds.py:51-64, powers.py:2144-2151

## `power/aggression`  → `audit/records/power/aggression.json`

- **`power/aggression/BeforeSideTurnStart`** (section `hooks`, key `BeforeSideTurnStart`, mechanism `power/aggression/BeforeSideTurnStart`)
  - what: BeforeSideTurnStart
  - issue: The card selection uses the wrong RNG and the wrong shuffle. AggressionPower.cs:28 is `source.ToList().UnstableShuffle(Rng.CombatCardSelection).Take(Amount)` -- an UnstableShuffle drawn from the dedicated CombatCardSelection stream. powers.py:514 is `combat._rng.sample(candidates, min(self.amount, len(candidates)))`, i.e. Python's reservoir sampling on the shared unseeded combat rng. Two consequences: the stream is wrong, so an Aggression turn perturbs every later draw on the shared rng and consumes nothing from CombatCardSelection; and `random.sample` is a different algorithm from UnstableShuffle+Take, so even given the same stream position it selects different cards. Conformance-visible on any replay that plays Aggression -- this is the class of defect docs/superpowers/prompts/_shared-audit-contract.md's sibling seeds are graded on. The SLOT half is correct for once: C# uses BeforeSideTurnStart (pre-draw, CombatManager.cs:458) and the sim uses on_player_turn_start (pre-draw, player.py:169), which is exactly right and is what makes the moved Attacks part of the same turn's hand. The sim's on_player_turn_start (player.py:169) fires BEFORE the hand draw (player.py:171-186); C#'s side-turn-start dispatchers run at CombatManager.cs:458 (Before) and :522 (After), i.e. either side of SetupPlayerTurn at :514. EXECUTED: a spy records [on_player_turn_start hand=5, 4x on_card_drawn, on_player_turn_started hand=9]. Third-file citations, not hashed here.
  - citations: AggressionPower.cs:28, CombatManager.cs:458, player.py:169, player.py:171-186, powers.py:514

## `power/calamity`  → `audit/records/power/calamity.json`

- **`power/calamity/AfterCardPlayed`** (section `hooks`, key `AfterCardPlayed`, mechanism `power/calamity/AfterCardPlayed`)
  - what: AfterCardPlayed
  - issue: NARROWED 2026-07-27. GAP (1), THE COUNT, IS CLOSED: combat.py:574-600 fires `before_card_played` and `on_card_played` inside the playCount loop, per CardModel.cs:1904-1965. WHAT REMAINS is gap (2), THE RNG AND THE POOL HELPER: powers.py:3681 still calls `random_pool_cards(combat._rng, self.amount, CardType.ATTACK)` -- the legacy shared unseeded random.Random -- where CalamityPower.cs:48-50 is `CardFactory.GetForCombat(..., Rng.CombatCardGeneration)` and `cards.pool.get_for_combat_parity` is the already-written parity port taking the card_gen accessor. VERIFIED by grep: `combat.combat_rng` has exactly one user in powers.py (StampedePower, :1111) and this is not it.
  - citations: CalamityPower.cs:48-50, CardModel.cs:1904-1965, combat.py:574-600, powers.py:3681

## `power/cruelty`  → `audit/records/power/cruelty.json`

- **`power/cruelty/g4`** (section `guards`, key `g4`, mechanism `power/cruelty/g4`)
  - what: CrueltyPower.cs:27 `amount + base.Amount / 100m`
  - issue: The arithmetic is right and the TYPE is not: powers.py:416 computes `mult += cruelty.amount / 100.0` in float where C# uses decimal. `1.5 + n/100` is non-dyadic for most n (10 -> 1.6, 30 -> 1.8), so a Cruelty-boosted Vulnerable is a third non-dyadic damage multiplier beyond the two literals `py audit/tools/power_census.py multipliers` reports, widening hook_dispatch gap G9. Per rule 3 the aggregation mechanism keeps G9's verdict; recorded at both this record and power/vulnerable because the factor is jointly theirs.
  - citations: CrueltyPower.cs:27, powers.py:416

## `power/hellraiser`  → `audit/records/power/hellraiser.json`

- **`power/hellraiser/AfterSideTurnEnd`** (section `hooks`, key `AfterSideTurnEnd`, mechanism `power/hellraiser/AfterSideTurnEnd`)
  - what: AfterSideTurnEnd
  - issue: HellraiserPower.cs:70-78 resets the per-turn infinite-auto-play counter. The sim tracks no counter (see the AfterCardDrawnEarly entry), so there is nothing to reset. Dormant for the same reason and with the same trigger; carried separately because a fix for the cap must add this reset too, and because the harness requires a verdict per override.
  - citations: HellraiserPower.cs:70-78

## `power/illusion`  → `audit/records/power/illusion.json`

- **`power/illusion/g1`** (section `guards`, key `g1`, mechanism `power/illusion/g1`)
  - what: IllusionPower.cs:34-45 FollowUpStateId
  - issue: A public settable property with no sim analogue: it lets an applier choose which state the revived creature resumes on, defaulting to the last LOGGED state. Folded into the AfterDeath entry; carried separately because it survives a should_die-to-AfterDeath fix. Dormant, but NOT for the reason recorded before the 2026-07-26 fix pass ("no ported applier", which was false): both ported appliers have single self-looping move machines (Parafright.cs:44-47, EyeWithTeeth.cs:39-42) and neither sets FollowUpStateId, so the default resolves to the only state there is. Trigger: an IllusionPower applier with more than one move state, or a caller that sets the property.
  - citations: EyeWithTeeth.cs:39-42, IllusionPower.cs:34-45, Parafright.cs:44-47
- **`power/illusion/g6`** (section `guards`, key `g6`, mechanism `power/_death_prevention_branch`)
  - what: The prevention branch's HP contract: sim `hp = 1` vs C# leaving the creature at 0 and re-entering KillWithoutCheckingWinCondition
  - issue: NARROWED 2026-07-27. THE FLOOR IS GONE: `_resolve_death`'s prevention arm (cmds.py:51-64) no longer writes `target.hp = 1`; it leaves the creature dead at 0 HP, sets `retained_after_death = True`, fires `on_death(..., True)` and then `after_preventing_death` -- CreatureCmd.cs:560-571's shape. The 1-vs-0 HP number conformance asserts on now matches, and the downstream consequences this entry listed go with it (Feed's `if target.is_dead` scores, and steam_eruption's HP restore no longer depends on the floor -- it moved to `on_death`, powers.py:2144-2151). WHAT REMAINS: the sim still does not model C#'s RE-ENTRY. CreatureCmd.cs:562-565 re-enters `KillWithoutCheckingWinCondition(creature, force, recursion + 1)` while `creature.IsDead`, up to 10 times before throwing InvalidOperationException; `_resolve_death`'s else-arm simply returns. So a prevention that heals nothing is permanent in the sim and re-kills in the game, and the sim still cannot express a prevention that fails. VERIFIED by reading cmds.py:30-64.
  - citations: CreatureCmd.cs:560-571, CreatureCmd.cs:562-565, cmds.py:30-64, cmds.py:51-64, powers.py:2144-2151

## `power/ravenous`  → `audit/records/power/ravenous.json`

- **`power/ravenous/AfterDeath`** (section `hooks`, key `AfterDeath`, mechanism `power/ravenous/AfterDeath`)
  - what: AfterDeath
  - issue: The guards are exact -- `target != base.Owner && target.Side == base.Owner.Side && !base.Owner.IsDead` (RavenousPower.cs:26) maps line-for-line to powers.py:1594-1599 -- and the effect order matches (stun the owner, then grant Strength). Two divergences. (1) MISSING `applier=` on the Strength grant: RavenousPower.cs:33 passes `base.Owner` and powers.py:1602 omits it; same shape and same dormancy as power/high_voltage's, carried as its own guard below. (2) The `((CorpseSlug)base.Owner.Monster).IsRavenous` flag (RavenousPower.cs:31, cleared in StunnedMove at :41) has no sim counterpart at all -- the sim stuns and buffs but never marks the Corpse Slug as devouring. Whether that is observable depends on what reads IsRavenous on the monster; it is the Corpse Slug's own record to settle, and it is flagged here rather than waived because a monster-state flag set and cleared across a stun is the kind of thing an intent or a move branch reads. Third-file citations, not hashed here.
  - citations: RavenousPower.cs:26, RavenousPower.cs:31, RavenousPower.cs:33, powers.py:1594-1599, powers.py:1602

## `power/ringing`  → `audit/records/power/ringing.json`

- **`power/ringing/ShouldPlay`** (section `hooks`, key `ShouldPlay`, mechanism `power/ringing/ShouldPlay`)
  - what: ShouldPlay
  - issue: HISTORY vs FLAG. C# answers 'has the owner played a card this turn' by querying CombatManager.History.CardPlaysStarted for entries that HappenedThisTurn; the sim keeps a boolean set from on_card_played. The two differ during a card's own resolution: C#'s history entry is written when the play STARTS (CardModel.cs:1930), so a card auto-played from inside the first card's resolution is already 'after a card this turn' and is blocked, while the sim's flag is set only in on_card_played, AFTER resolution (combat.py:514), so the nested auto-play slips through. Reachable: the sim auto-plays from inside a resolution in several ported places (HellraiserPower powers.py:707-713 on draw, MayhemPower :3572-3583, StampedePower :1025-1041). Third-file citations, not hashed here.
  - citations: CardModel.cs:1930, combat.py:514, powers.py:707-713

## `power/tangled`  → `audit/records/power/tangled.json`

- **`power/tangled/AfterApplied`** (section `hooks`, key `AfterApplied`, mechanism `power/tangled/AfterApplied`)
  - what: AfterApplied
  - issue: The sim adds a guard C# does not have, and it changes the outcome. TangledPower.cs:23-30 afflicts EVERY Attack card with Entangled unconditionally -- there is no `Affliction == null` test, unlike its own AfterCardEnteredCombat at :34 and unlike Ringing's and Smoggy's AfterApplied -- so in the game Tangled OVERWRITES an existing affliction on Attack cards. powers.py:1476 adds `card.affliction is None`, so the sim skips already-afflicted Attacks and they cost nothing extra. Reachable with two ported enemy powers in one combat: Ringing (powers.py:1319-1332) afflicts every unafflicted card, after which the game's Tangled re-afflicts the Attacks as Entangled and the sim leaves them Ringing. Also note the sim's __init__ walk misses the Play pile for the same reason recorded on power/ringing and power/smoggy (player.py:100-103 vs PlayerCombatState.cs:70-80). Third-file citations, not hashed here.
  - citations: PlayerCombatState.cs:70-80, TangledPower.cs:23-30, player.py:100-103, powers.py:1319-1332, powers.py:1476

## `power/unmovable`  → `audit/records/power/unmovable.json`

- **`power/unmovable/ModifyBlockMultiplicative`** (section `hooks`, key `ModifyBlockMultiplicative`, mechanism `power/unmovable/ModifyBlockMultiplicative`)
  - what: ModifyBlockMultiplicative
  - issue: NARROWED 2026-07-27. DIVERGENCE (b) IS CLOSED: `on_card_played` now fires once per replay iteration (combat.py:600, inside `for play_index in range(play_count)`), so a doubled block card consumes the allowance twice, matching UnmovablePower.cs:35's per-CardPlay comparison -- traced through powers.py:1175-1199, with Unmovable 1 a doubled Iron Wave now doubles exactly once in both models and with Unmovable 2 exactly twice in both. WHAT REMAINS is divergence (a), THE RESET SLOT: powers.py:1201-1204 still clears `_plays_used` from `on_player_turn_start` (pre-draw), where C# keeps no counter at all and re-derives the count on every call from History.Entries.OfType<BlockGainedEntry>() filtered on `HappenedThisTurn(base.CombatState)`. Any block the owner gains outside the player's own turn therefore falls in a different window on the two sides.
  - citations: UnmovablePower.cs:35, combat.py:600, powers.py:1175-1199, powers.py:1201-1204
