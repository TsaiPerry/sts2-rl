# Power tier — gap ledger

Every `gap`-verdict entry in the 138 committed power audit records, in one
place. **Generated from `audit/records/power/*.json`, not hand-written** — each line
traces to a record, and the record carries the full reasoning and the file:line
citations. Regenerate after any record changes rather than editing this file.

## Counts

| | |
|---|---|
| units audited | 138 |
| unit rollups | 63 gap, 31 faithful, 26 waiver, 18 deliberate-divergence |
| entries (hooks + guards) | 1209 — 912 faithful, 163 waiver, 90 gap, 44 deliberate-divergence |
| **gap entries** | **90**, across 63 units |
| of which LIVE | **7** |
| of which DORMANT | 80 |
| unclassified | 3 |

LIVE / DORMANT is read from the auditor's own wording in each entry (whichever
marker appears first). An entry counted DORMANT names a trigger — the thing
that would make it observable. **`waiver` entries are NOT in this file**: per
binding rule 1 a waiver means genuinely out of scope, whereas "nothing ported
triggers this" is a dormant gap and is included below.

### Three caveats on these numbers, so they are not over-read

1. **An entry is not a distinct bug.** Binding rule 3 gives one mechanism one
   verdict at every site, so a mechanism shared by sibling units is recorded
   once per unit. The eight `TemporaryStrength`/`TemporaryDexterity` units all
   carry the same `AfterSideTurnEnd` slot gap, for instance — eight entries,
   one defect, one one-line fix. The count of *distinct* live mechanisms is
   roughly 28; they are enumerated in the stream report's sections 0 and 4,
   which is the right place to plan fixes from. Use this file to find every
   site a mechanism touches.
2. **The unclassified bucket UNDER-reports live gaps** — it is a labelling
   artifact, not a severity judgement. Those entries simply never write the
   word LIVE or DORMANT. Several are known-live from the stream report; the
   wrong-RNG-stream class is the clearest case, where `aggression`'s entry
   describes `combat._rng.sample` against C#'s
   `UnstableShuffle(Rng.CombatCardSelection)` and is live per report section 0
   item 4, yet lands here unclassified. **Treat the report, not this bucket, as
   authoritative on severity.** Classifying these entry by entry is outstanding
   work.
3. **Two of these findings would change a committed seam record**
   (`turn_structure` G8 and `power_cmd` G6 flipping to live) and rest on
   witnesses executed by continuation sessions rather than re-derived. Re-run
   those before amending the seam docs.

## How to read a dormant gap

Dormant does not mean harmless. It means no *currently ported* content reaches
the divergent path. Every dormant entry below is a latent bug that activates
the moment its trigger is ported — which is why they are recorded as gaps
rather than waived. When porting new content, grep this file for the mechanism
first.

## LIVE gaps

These diverge from the game on content that is already ported. Ordered by
unit. Full text, because these are the actionable ones.

### `chains_of_binding` — AfterCardDrawn

*(hook; record: `audit/records/power/chains_of_binding.json`)*

Two divergences. (1) A DROPPED GUARD: C# requires `base.CombatState.CurrentSide == base.Owner.Side` (ChainsOfBindingPower.cs:38), so only cards drawn during the PLAYER's own turn are Bound; the sim has no side test (powers.py:3313-3314), so a card drawn during the ENEMY turn is Bound in the sim and not in the game. Enemy-turn draws are ported and ordinary (any enemy effect that makes the player draw), so this is the live-shaped half. (2) The BUDGET is counted differently: C# counts `CardAfflictedEntry` history entries this turn by this actor with a Bound affliction (ChainsOfBindingPower.cs:40) -- so an affliction the player OVERWRITES still consumes budget, and the history is the source of truth -- where the sim keeps its own `_afflicted_this_turn` counter reset at turn end (powers.py:3311, 3335). Equivalent while nothing else writes Bound; the sim's counter is the cheaper model of the same number. Also `Affliction<Bound>().CanAfflict(card)` becomes `card.affliction is None`, which is the sim's affliction-slot rule. DORMANT overall pending an executed enemy-turn-draw witness against the Queen (monsters/glory/queen.py); labelled dormant per binding rule 6 rather than asserted live. Third-file citations, not hashed here.

### `cruelty` — CrueltyPower.cs:27 `amount + base.Amount / 100m`

*(guard; record: `audit/records/power/cruelty.json`)*

Replaced the record's "third non-dyadic multiplier" framing: the ONE live applier (`cards/cruelty.py`) only ever grants multiples of 25, so `1.5 + n/100.0` is exact in `float` for every reachable value (executed: `Decimal` cross-check for n in 25..500 step 25, plus n=500). The float-vs-decimal TYPE mismatch is real but currently inert on its own; what actually widens `hook_dispatch/G9` is the pre-existing literal factors (Shrink `×0.7` etc.), not Cruelty. Verdict stays `gap`/`live:false` by cross-reference to G9's own (already-`gap`) verdict, not because Cruelty independently reaches it. Pinned by `test/test_r14_powers.py::TestCruelty` (13 tests, incl. an 11-value parametrized exactness sweep).

### `hellraiser` — AfterSideTurnEnd

*(hook; record: `audit/records/power/hellraiser.json`)*

Re-executed the record's own claim by direct introspection (`vars()` on a live `HellraiserPower` instance, `hasattr` checks for `after_side_turn_end`/`after_enemy_side_end`) instead of citing its prose. Confirmed: no counter, no cap check, no reset method exists on either side of this hook — the record's dormancy verdict was already correct and needed no change, only fresh evidence. Pinned by `test/test_r14_powers.py::TestHellraiserReset` (2 tests).

### `juggling` — AfterCardPlayed

*(hook; record: `audit/records/power/juggling.json`)*

The copy is rebuilt from the class rather than cloned. JugglingPower.cs:48 is `cardPlay.Card.CreateClone()`, which reproduces the card's full live state; powers.py constructs `type(card)()` and replays `card.upgrade_level` upgrades onto it. Upgrade level is therefore carried and everything else is not -- a this-combat cost override (ConfusedPower/Snecko Eye, powers.py), an affliction (Entangled, Ringing, Smog, Bound, Galvanized, Tainted -- all ported), or a this-turn free flag would all be dropped. DORMANT only in the narrow sense that no test exercises it; the route is a Snecko-Eye or Tangled combat plus a Juggling trigger, both ported. Named trigger: any Juggling copy of a card carrying per-combat state. Third-file citations, not hashed here.

### `ravenous` — AfterDeath

*(hook; record: `audit/records/power/ravenous.json`)*

Confirmed the missing `applier=` is real (executed: `strength.applier is None` after a live Ravenous trigger) and re-ran the consumer census fresh rather than trusting the high_voltage cross-reference: `relics/unsettling_lamp.py` (the only `modify_power_amount_given_*` listener) and two `on_power_amount_changed`/ `on_power_applied` listeners in `powers.py` all gate on conditions this grant never satisfies (player-only applier, DEBUFF-only, name/sign filters unrelated to Strength). Same class of bug as `power/high_voltage`, left unfixed there for the identical reason — not fixed here either, to stay consistent with that precedent rather than diverge on an unobservable difference. The `IsRavenous` flag half stays out of scope (belongs to the Corpse Slug monster record). Pinned by `test/test_r14_powers.py::TestRavenousMissingApplier` (2 tests).

### `speed_potion` — The Dexterity leg's own observable consequence, as distinct from the family's slot verdict

*(guard; record: `audit/records/power/speed_potion.json`)*

RE-DERIVED 2026-07-26 (review fix pass). Stated separately so the AfterSideTurnEnd verdict above is not read as more proven than it is, and re-labelled from an admission that the consequence is "UNPROVEN" to a positive dormancy argument with a named trigger. The SLOT gap is the same code path power/setup_strike executed, so the verdict is inherited under rule 3 -- but setup_strike's witness is a DAMAGE witness (Stampede auto-plays an ATTACK from its own on_player_turn_end, so it sees the reverted Strength). Dexterity modifies BLOCK, so an equivalent witness needs a POWERED block gain landing strictly between combat.py:654 (on_player_turn_end, where the sim reverts) and combat.py:665 (after_player_turn_end, the correct slot). **ENUMERATED 2026-07-26; there is none.** (1) Dexterity's only consumer in the sim is DexterityPower.modify_block_additive (powers.py:129-137), and BlockCmd.apply dispatches the block-modifier families ONLY when `is_powered_attack(props)` (cmds.py:145-147), which is `MOVE in props and UNPOWERED not in props` (valueprops.py:47-49). (2) All four ported turn-end block relics pass `props=ValueProp.UNPOWERED` and therefore skip Dexterity entirely: relics/orichalcum.py:22-25, relics/cloak_clasp.py:19-24, relics/fake_orichalcum.py:25-30, relics/ripple_basin.py:36-39. (3) An AST sweep of every `on_player_turn_end` in sts2_rl finds exactly two bodies that mention block: PlatingPower._gain_block (powers.py:1058-1070), also ValueProp.UNPOWERED and owner-filtered, and ImbalancedPower's `_blocked_this_turn = False` reset (powers.py:1820), which gains none. (4) `_process_turn_end_cards` (combat.py:352-376) runs only the ethereal exhaust pass and the ten ported `on_turn_end_in_hand` bodies (bad_luck, beckon, burn, decay, doubt, infection, regret, shame, toxic, wither), and an AST sweep finds not one of them gains block. So: MECHANISM live and inherited; the DEXTERITY LEG DORMANT. **NAMED TRIGGER:** any ported effect that gains POWERED block (props MOVE without UNPOWERED -- i.e. card block, or a relic/power turn-end gain that drops the UNPOWERED prop) strictly between combat.py:654 and combat.py:665; concretely, a turn-end-in-hand card that gains card block, or an Orichalcum/Cloak Clasp-shaped relic ported without the UNPOWERED prop. Whoever fixes the family (one line: on_player_turn_end -> after_player_turn_end) fixes both legs regardless.

### `unmovable` — ModifyBlockMultiplicative

*(hook; record: `audit/records/power/unmovable.json`)*

Re-executed rather than left narrated: confirmed the reset DOES fire on an extra player turn (round_number unchanged, `_start_player_turn` is the shared entry point for both paths) — the record's mechanism claim is correct. But census of every `should_take_extra_turn` listener in the sim finds exactly one (`relics/paels_eye.py`), and its own trigger condition (`not any cards played this turn`) is structurally incompatible with `_plays_used` having anything nonzero to lose — so today's one live extra-turn source can never actually observe the reset. DORMANT, not previously determined either way. A faithful fix needs `history.py` (a `BlockGainedEntry` type) + `cmds.py` (`BlockCmd` wiring), both outside this lane's footprint — noted, not attempted, since nothing currently depends on it. Pinned by `test/test_r14_powers.py::TestUnmovableResetBoundary` (2 tests).

## DORMANT gaps

Trimmed to the opening of each entry; the record has the rest, including the
named trigger. Ordered by unit.

### `buffer`

- **ModifyHpLostAfterOstyLate** *(hook)* — The arithmetic is exact -- 0 for the owner, unchanged otherwise (BufferPower.cs:20-27 vs powers.py:4011-4013) -- and the AFTER-Osty position is right, since cmds.py:86 runs after block absorption (:74-81). What is lost is the LATE half, and BufferPower.cs:16-19 states in as many words why it is Late: 'We use Late because other effects may reduce damage taken to 0 too, and it's more player-friendly for them to trigger […]
### `burrowed`

- **AfterRemoved** *(hook)* — C#'s AfterRemoved is `CreatureCmd.LoseBlock(oldOwner, 999999999m)` -- dump ALL the block -- and it runs on EVERY removal path, including the automatic strip when the owner dies (CreatureCmd.cs:533 then each power's AfterRemoved). The sim has no AfterRemoved analogue and hand-inlines the block dump at the single on_block_broken call site (powers.py:2300, comment `# AfterRemoved: LoseBlock(all)`). […]
### `calamity`

- **BeforeCardPlayed** *(hook)* — C# uses a TWO-HOOK LATCH the sim collapses into one. CalamityPower.cs:28-40 records amountsForPlayedCards[card] = base.Amount at BeforeCardPlayed and :44 removes it at AfterCardPlayed, so (a) the Amount is SNAPSHOTTED at the start of the play and (b) the after-hook only fires for a card the before-hook admitted. The sim reads self.amount at the end of the play (powers.py:3493) and re-tests the card type there. […]
### `chains_of_binding`

- **BeforeCardPlayed** *(hook)* — WRONG SIDE OF THE PLAY, the same shape as SlothPower's: C# sets `boundCardPlayed` in BeforeCardPlayed (ChainsOfBindingPower.cs:48-65) and the sim sets it in on_card_played, after resolution -- while the sim's `before_card_played` slot (combat.py:466) exists and is used by StranglePower and SurroundedPower. […]
### `crab_rage`

- **CrabRagePower.cs:36 `applier: base.Owner`** *(guard)* — MISSING `applier=`. C# passes `base.Owner` (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)`); the sim omits it, so `applier` is None through hooks.modify_power_amount (cmds.py:297), hooks.on_power_applied (cmds.py:327) and hooks.on_power_amount_changed (cmds.py:312), and the granted power's .applier is left None (powers.py:59). Recurring gap shape 5. […]
### `crimson_mantle`

- **CrimsonMantlePower.cs:31 fires the damage UNCONDITIONALLY** *(guard)* — C# calls CreatureCmd.Damage with the DamageVar's BaseValue every turn, including the first, when the value is 0; powers.py:643 guards on `if self.self_damage > 0`. A 0-damage CreatureCmd.Damage is not a no-op in C#: it still runs the pipeline and fires BeforeDamageReceived. […]
### `cruelty`

- **CrueltyPower.cs:19-22 `target == base.Owner` -> unmodified** *(guard)* — Cruelty's self-exclusion is dropped by its consumer. Recorded in full on power/vulnerable's matching guard -- the sim reads Cruelty's amount with no such test, so a Cruelty holder attacking its own Vulnerable self would get the bonus in the sim and not in the game. […]
### `curious`

- **CuriousPower.cs:12-14,32 the TryModify predicate protocol** *(guard)* — C#'s Try* hooks are a predicate chain: the listener returns bool to say 'I changed it' and writes the new value to an out-param, and Hook.ModifyEnergyCostInCombat (Hook.cs:1574-1590) uses that to decide who to notify afterwards and, in some families, to stop looking. […]
### `curl_up`

- **AfterCardPlayed** *(hook)* — NARROWED 2026-07-29 (round 11): this entry's own premise was stale. It was written to say the sim has AfterCardPlayed's whole job missing ("the block and the removal moved into AfterDamageReceived"), but that was the PRE-round-7 sim -- the AfterDamageReceived entry in this same record shows it was closed 2026-07-29 (round 7): the block grant (ValueProp.Unpowered) and the PowerCmd.Remove-equivalent (`self._expire()`) […]
### `dark_shackles`

- **ITemporaryPower as a marker interface** *(guard)* — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has five readers of power is ITemporaryPower: IllusionPower.cs:59-66 (Illusions keep their debuffs on death UNLESS the debuff is temporary, so that the wrapper's internal Strength goes away with it), Rend.cs:43-50 an […]
- **TemporaryStrengthPower.cs:141-144 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs:30, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal StrengthPower; without the flag the copy would double the Strength steal. […]
### `dexterity`

- **Sign-aware power typing on a negative Dexterity application** *(guard)* — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs:460-471, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGATIVE amount, because StackType == Counter && AllowNegative. The sim has no get_type_for_amount at all and tests the static class attribute, so a negative-amount application is a Buff to the sim and a Debuff to the game. […]
- **ModifyBlockAdditive** *(hook)* — The sim keys the ownership test on the BLOCK TARGET where C# keys it on the CARD's owner. DexterityPower.cs:16-26: when cardSource != null the test is `cardSource.Owner.Creature != base.Owner -> 0m` and the target is not consulted at all; only for cardSource == null (a monster move) does it fall back to `base.Owner != target`. powers.py:249 tests `target is self.owner` in both cases. […]
### `disintegration`

- **AfterSideTurnEndLate** *(hook)* — REVISED 2026-08-04: the slot/phase half of this finding is CLOSED, not merely renumbered -- re-read confirms real code change, not a re-reading of the old code. The power is no longer on `on_player_turn_end` (Hook.BeforeTurnEnd); […]
### `feeding_frenzy`

- **ITemporaryPower as a marker interface** *(guard)* — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has five readers of power is ITemporaryPower: IllusionPower.cs:59-66 (Illusions keep their debuffs on death UNLESS the debuff is temporary, so that the wrapper's internal Strength goes away with it), Rend.cs:43-50 an […]
- **TemporaryStrengthPower.cs:141-144 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs:30, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal StrengthPower; without the flag the copy would double the Strength steal. […]
### `flame_barrier`

- **AfterSideTurnEnd** *(hook)* — The removal condition is inverted from a side comparison into a hard-coded side. FlameBarrierPower.cs:26-32 removes the power whenever `base.Owner.Side != side` -- i.e. at the end of the turn belonging to the side the owner is NOT on, which for a player-held Flame Barrier is the enemy side's end and for an enemy-held one is the PLAYER side's end. […]
### `flex_potion`

- **ITemporaryPower as a marker interface** *(guard)* — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; Rend, Sleight of Flesh and Misery are unported, but IllusionPower IS ported (powers.py:1560ff) and owns the ShouldPowerBeRemovedOnDeath port. […]
- **TemporaryStrengthPower.cs:141-144 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal stat power. DORMANT: Misery is unported (grep -rn misery sts2_rl/ --include=*.py is empty). Named trigger: porting Misery. Dormant gap, not a waiver, per binding rule 1. […]
### `free_attack`

- **The TryModify predicate protocol** *(guard)* — C#'s Try* hooks return bool and write to an out-param, which Hook.ModifyEnergyCostInCombat (Hook.cs:1574-1590) uses to build its notification list; the sim's modify_card_energy_cost (hooks.py:1051-) is a plain fold with neither. Identical entry to power/curious's, same verdict per binding rule 3, dormant with the same named trigger (any AfterModifyingEnergyCostInCombat implementer).
### `galvanic`

- **AfterCardPlayed** *(hook)* — **PROPS.** C# deals the Galvanized damage with `ValueProp.Unpowered | ValueProp.Move` (GalvanicPower.cs:55); the sim passes `DamageProps.NON_CARD_UNPOWERED`, which valueprops.py:42 defines as `UNPOWERED` **alone** -- the MOVE flag is missing. The right constant exists and is one line up: `DamageProps.CARD_UNPOWERED` (valueprops.py:36) is exactly `UNPOWERED | MOVE`. […]
- **BeforeCombatStart** *(hook)* — Right slot -- combat.py:356 fires on_combat_start immediately before `start_turn()`, which turn_structure identifies as the sim's BeforeCombatStart. The divergence is an ADDED GUARD (recurring shape 8): C# afflicts EVERY Power card unconditionally (GalvanicPower.cs:34-38 has no `Affliction == null` test at this site, and `CardCmd.Afflict` overwrites) while the sim skips already-afflicted cards (powers.py:3846 `card.a […]
### `gigantification`

- **AfterAttack** *(hook)* — The slot is right (combat.py:1176, immediately after the card's on_play inside the play-count loop). The GAP is the IDENTITY the latch is cleared against: C# compares ATTACK-COMMAND identity (`command == internalData.commandToModify`, GigantificationPower.cs:80), the sim compares CARD identity (`card is self._card_to_modify`, powers.py:4934). […]
### `hardened_shell`

- **ModifyHpLostBeforeOstyLate** *(hook)* — The FORMULA is exact -- `target != Owner -> amount`, `amount == 0 -> amount`, else `Math.Min(amount, Amount - damageReceivedThisTurn)` (HardenedShellPower.cs:32-43) vs powers.py:2513-2515 -- and the BeforeOsty/AfterOsty phase collapse is already resolved as faithful by damage_pipeline (Osty redirection is waived, so its steps 8 and 11 fold into one `modify_hp_lost` call). […]
### `heist`

- **BeforeDeath** *(hook)* — HOOK-PHASE MISMATCH -- a BEFORE hook ported onto an AFTER hook, the recurring shape section 0 item 5 of the stream report names for thorns/curl_up/skittish/suck, now in a death-time form. C# calls Hook.BeforeDeath UNCONDITIONALLY at CreatureCmd.cs:503, two lines BEFORE Hook.ShouldDie at :505 decides whether the death stands. The sim's on_death fires only INSIDE the should_die-true branch (cmds.py), i.e. […]
### `hello_world`

- **HelloWorldPower.cs:22 base.AmountOnTurnStart >= 1 (used as BOTH the guard and the card count)** *(guard)* — The guard is ported as self.amount < 1 (powers.py) and the count as self.amount (:2825), where C# uses base.AmountOnTurnStart for both (HelloWorldPower.cs:22 and :27). PowerModel.AmountOnTurnStart has NO sim counterpart -- grep -rn amount_on_turn_start sts2_rl/ returns nothing. […]
### `hellraiser`

- **AfterCardDrawnEarly** *(hook)* — NARROWED 2026-07-28. Clause (a), PHASE LOSS, is CLOSED. The sim now has real phase passes and this listener is on the Early one: HellraiserPower.on_card_drawn_early (sts2_rl/powers.py) is picked up by HookSystem._each's `_very_early -> _early -> plain -> _late` walk (sts2_rl/hooks.py _PHASES, :153-180 _each), which HookSystem.on_card_drawn (sts2_rl/hooks.py) dispatches through, and `_phase_hooks(HellraiserPower)` ret […]
### `high_voltage`

- **HighVoltagePower.cs:23 `participants.Contains(base.Owner)`** *(guard)* — The sim substitutes `if not self.owner.is_dead` (powers.py) -- recurring gap shape 8, a guard the sim changes rather than drops. The two are not the same predicate: a corpse the combat RETAINED is still a side participant in C# (the "death does not mean removal" finding; combat.py keeps a retained corpse taking turns), so C# would grant it Strength where the sim refuses. […]
- **HighVoltagePower.cs:26 `applier: base.Owner`** *(guard)* — MISSING `applier=`. C# passes `base.Owner` as the applier (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)`); the sim calls `PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)` with no applier, so `applier` is None through hooks.modify_power_amount (cmds.py), hooks.on_power_applied (cmds.py) and hooks.on_power_amount_changed (cmds.py), and the granted StrengthP […]
### `inferno`

- **InfernoPower.cs:48 CombatState.HittableEnemies** *(guard)* — The sim iterates `combat.enemies` filtered on `not enemy.is_gone` (powers.py) where C# uses HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs:308-322). So the sim burns creatures the game considers unhittable -- a mid-revival Illusion or a withered Decimillipede segment (powers.py, :2354-2357 both implement should_allow_hitting). […]
### `intangible`

- **IntangiblePower.cs:20-23 `!CombatManager.Instance.IsInProgress` -> unmodified** *(guard)* — The sim has no combat-phase guard on any modifier hook. This is the power-level face of audit/records/seam/power_cmd.json's structural gap G6 (no IsEnding/CanReceivePowers backstop) and of hook_dispatch's gap G8 (no IsOverOrEnding gate on combat dispatches); per binding rule 3 it carries the same `gap` verdict and is cross-referenced rather than re-argued. […]
### `juggernaut`

- **JuggernautPower.cs:21-22 CombatState.HittableEnemies and the empty check** *(guard)* — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs:308-322), so the sim aims at creatures the game considers unhittable -- a mid-revival Illusion (powers.py) or a withered Decimillipede segment (powers.py). DORMANT: DamageCmd.deal re-checks should_allow_hitting at entry (cmds.py) and returns 0. […]
### `mangle`

- **ITemporaryPower as a marker interface** *(guard)* — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has five readers of power is ITemporaryPower: IllusionPower.cs:59-66 (Illusions keep their debuffs on death UNLESS the debuff is temporary, so that the wrapper's internal Strength goes away with it), Rend.cs:43-50 an […]
- **TemporaryStrengthPower.cs:141-144 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs:30, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal StrengthPower; without the flag the copy would double the Strength steal. […]
### `nemesis`

- **NemesisPower.cs:22 `participants.Contains(base.Owner)`** *(guard)* — Replaced by `if self.owner.is_dead: return` (powers.py) -- the same substitution as HighVoltage's and Territorial's, and one degree worse here, because the sim's early return also SKIPS THE TOGGLE (`_should_apply` is not flipped), so a Nemesis owner that is dead for one side end and alive for the next resumes on the wrong beat where C# would have flipped. […]
### `painful_stabs`

- **PainfulStabsPower.cs:36 the three AfterAttack guards** *(guard)* — RE-OPENED 2026-07-28. Two of the three early-return conditions map; the THIRD does not, and the AfterAttack hook entry in this record already says so ("NOTE this record's guard on 'the three AfterAttack early-return conditions' still reads `faithful`, which is no longer true of the third one") -- the re-derivation pass wrote that sentence and left this entry at `faithful` anyway. […]
- **ShouldCreatureBeRemovedFromCombatAfterDeath** *(hook)* — Was a genuine unimplemented hook (`PainfulStabsPower.cs:29-32` had no sim counterpart), dormant under current content only because the power's one consumer (Test Subject) always pairs it with `AdaptablePower`'s equivalent OR-veto (`hooks.py`). […]
### `panache`

- **AfterCardPlayed** *(hook)* — The sim iterates `combat.enemies` filtered on `not enemy.is_gone` where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs:308-322). The sim therefore aims at creatures the game considers unhittable -- a mid-revival Illusion (powers.py:1572-1575) or a withered Decimillipede segment (powers.py:2354-2357). […]
### `plow`

- **AfterDamageReceived** *(hook)* — Right hook and right slot; the threshold matches exactly (`target != base.Owner || result.UnblockedDamage <= 0 || target.CurrentHp > base.Amount -> return`, PlowPower.cs:30, vs powers.py:1713-1716). Three divergences. (1) The sim ADDS `self.owner.is_dead` to the early-out (powers.py:1713) where C# has no such guard -- recurring gap shape 8; […]
### `poison`

- **AfterSideTurnStart** *(hook)* — STILL OPEN at (b) and (c). Clause (a), the SLOT, is CLOSED: PoisonPower.cs:55 declares AfterSideTurnStart and the power is on the new `after_side_turn_start` dispatcher (CombatManager.cs:522), post-draw, so the tick no longer lands before the hand draw and a lethal tick can no longer cancel a draw the game already made. […]
### `rampart`

- **RampartPower.cs:27 `base.CombatState.Enemies.Where(c => c.Monster is TurretOperator)`** *(guard)* — powers.py:3815-3817 adds `and not enemy.is_gone` (recurring gap shape 8, a guard the sim ADDS). C#'s CombatState.Enemies is the raw participant list and a corpse the combat retained is still in it, so the game grants block to a dead-but-present Turret Operator and the sim does not. DORMANT: TurretOperator overrides no ShouldCreatureBeRemovedFromCombatAfterDeath, so a dead one leaves the list; […]
### `ravenous`

- **RavenousPower.cs:33 `applier: base.Owner`** *(guard)* — MISSING `applier=`. C# passes `base.Owner` (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)`); the sim omits it, so `applier` is None through the modify/apply dispatch chain in cmds.py (bare filename; line numbers no longer resolved this pass) and the granted power's .applier is left None (powers.py:132). Recurring gap shape 5. […]
### `reptile_trinket`

- **ITemporaryPower as a marker interface** *(guard)* — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has five readers of power is ITemporaryPower: IllusionPower.cs:59-66 (Illusions keep their debuffs on death UNLESS the debuff is temporary, so that the wrapper's internal Strength goes away with it), Rend.cs:43-50 an […]
- **TemporaryStrengthPower.cs:141-144 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs:30, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal StrengthPower; without the flag the copy would double the Strength steal. […]
### `rolling_boulder`

- **RollingBoulderPower.cs:37 CombatState.HittableEnemies (TestMode arm)** *(guard)* — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py:4652) where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs:308-322), so the sim aims at creatures the game considers unhittable -- a mid-revival Illusion (powers.py:1572-1575) or a withered Decimillipede segment (powers.py:2354-2357). […]
### `sandpit`

- **AfterRemoved** *(hook)* — The EFFECT is right and the MECHANISM is not. C#'s AfterRemoved (SandpitPower.cs:91-124) returns early on `oldOwner.IsDead || base.Target.IsDead`, hides the affected creatures, and `CreatureCmd.Kill(..., force: true)` every one that IsPlayer or is an Osty; the sim overrides `_expire` (powers.py:2610-2619) to kill `combat.player` unless `owner_gone` or the player is already dead. Two divergences. […]
### `setup_strike`

- **ITemporaryPower as a marker interface** *(guard)* — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has five readers of power is ITemporaryPower: IllusionPower.cs:59-66 (Illusions keep their debuffs on death UNLESS the debuff is temporary, so that the wrapper's internal Strength goes away with it), Rend.cs:43-50 an […]
- **TemporaryStrengthPower.cs:141-144 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs:30, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal StrengthPower; without the flag the copy would double the Strength steal. […]
### `shackling_potion`

- **ITemporaryPower as a marker interface** *(guard)* — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has five readers of power is ITemporaryPower: IllusionPower.cs:59-66 (Illusions keep their debuffs on death UNLESS the debuff is temporary, so that the wrapper's internal Strength goes away with it), Rend.cs:43-50 an […]
- **TemporaryStrengthPower.cs:141-144 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs:30, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal StrengthPower; without the flag the copy would double the Strength steal. […]
### `shrink`

- **AfterDeath** *(hook)* — The `wasRemovalPrevented` guard is missing. ShrinkPower.cs:87-93 removes Shrink only when `!wasRemovalPrevented && creature == base.Applier`; the sim tests only `creature is self.applier` (powers.py:1398). A prevented removal (a death whose corpse the combat keeps) therefore drops Shrink in the sim and keeps it in the game. […]
- **AfterSideTurnEnd** *(hook)* — Two divergences in one hook. (a) The `!IsInfinite` guard (ShrinkPower.cs:81, i.e. Amount >= 0) is spelled `self.amount > 0` on both sim legs (powers.py:1390,1394); those agree only because Amount == 0 is unreachable (ShouldRemoveDueToAmount removes at exactly 0), so this half is equivalent rather than identical. […]
- **AllowNegative** *(hook)* — ShrinkPower.cs:38 declares `AllowNegative => true`; the sim's ShrinkPower never sets allow_negative, so it inherits False from Power (powers.py:47). That changes ShouldRemoveDueToAmount (PowerModel.cs:478-489): C# removes an AllowNegative power only at EXACTLY 0 and lets it sit negative, while the sim's stacking branch removes it at any amount < 0 (cmds.py:317-319). […]
### `skittish`

- **AfterSideTurnEnd** *(hook)* — NARROWED 2026-07-27. THE SLOT HALF IS CLOSED: the reset is now `after_player_turn_end` (powers.py:1927), the sim's Hook.AfterTurnEnd slot (combat.py:809 / CombatManager.cs:1307). WHAT REMAINS is the side test: SkittishPower.cs:73 acts only when `side != base.Owner.Side`, while powers.py:1927-1929 resets on every player turn end regardless of the owner's side. […]
### `slippery`

- **ModifyHpLostAfterOsty** *(hook)* — The formula is exact: `target != base.Owner -> amount`, `amount < 1m -> amount`, else `1m` (SlipperyPower.cs:19-30) vs powers.py:1520-1522. The BeforeOsty/AfterOsty phase collapse is already resolved as faithful by damage_pipeline (Osty redirection is waived, so its steps 8 and 11 fold into one call). […]
### `sloth`

- **BeforeCardPlayed** *(hook)* — WRONG SIDE OF THE PLAY. C# increments the counter in `BeforeCardPlayed` (SlothPower.cs:31-40), i.e. before the card resolves; the sim increments in `on_card_played`, after. The sim HAS the right slot -- `before_card_played` (combat.py:466), which ChainsOfBindingPower's sibling port and StranglePower both use. […]
### `slow`

- **ModifyDamageMultiplicative** *(hook)* — The factor matches (`1m + 0.1m * SlowAmount` at SlowPower.cs:43 vs `1.0 + 0.1 * self._cards_this_turn` at powers.py:1261) and `target != base.Owner -> 1m` matches, but the POWERED test does not: C# is `props.IsPoweredAttack()` (SlowPower.cs:39) and the sim is `card is not None and not card.is_unpowered` (powers.py:1260). […]
### `speed_potion`

- **ITemporaryPower as a marker interface** *(guard)* — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; Rend, Sleight of Flesh and Misery are unported, but IllusionPower IS ported (powers.py:1560ff) and owns the ShouldPowerBeRemovedOnDeath port. […]
- **TemporaryDexterityPower.cs:137-140 IgnoreNextInstance** *(guard)* — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs:59-61, which copies an enemy's debuffs and must not re-apply the wrapper's internal stat power. DORMANT: Misery is unported (grep -rn misery sts2_rl/ --include=*.py is empty). Named trigger: porting Misery. Dormant gap, not a waiver, per binding rule 1. […]
### `steam_eruption`

- **The prevention branch's HP contract: sim `hp = 1` vs C# leaving the creature at 0 and re-entering KillWithoutCheckingWinCondition** *(guard)* — STAYS OPEN, DORMANT AT THIS SITE -- enumeration executed 2026-08-01 (round 13, R3) rather than inherited from the mechanism. Enumerated every should_die implementer in sts2_rl/ (three: the dispatcher, Fairy in a Bottle [player-only], Lizard Tail [player-only, relic]); […]
### `strength`

- **Sign-aware power typing on a negative Strength application** *(guard)* — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs:460-471, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGATIVE amount, because StackType == Counter && AllowNegative. The sim has no get_type_for_amount at all and tests the static class attribute, so a negative-amount application is a Buff to the sim and a Debuff to the game. […]
### `surprise`

- **AfterDeath** *(hook)* — Right hook and the right two spawns (`CreatureCmd.Add<SneakyGremlin>` then `<FatGremlin>`, SurprisePower.cs:23-24, vs powers.py:1704-1706 in the same order, which matters because it fixes the enemy-list indices). The gap is the THIEVERY TRANSFER. […]
### `surrounded`

- **SurroundedPower.cs:92 `!wasRemovalPrevented`** *(guard)* — Absent from powers.py:2584-2586, which tests only the side. C# skips the re-facing entirely when a death's REMOVAL was prevented (the creature is still there, so the board did not change); the sim re-runs its `all(...)` scan anyway. […]
- **AfterDeath** *(hook)* — The logic matches SurroundedPower.cs:90-100 -- skip when the dead creature is on the owner's own side, then, if every remaining hittable enemy carries the SAME marker power, re-face on hittableEnemies[0] -- but the sim reads `[e for e in combat.enemies if not e.is_gone]` (powers.py:2590) where C# reads `base.Owner.CombatState.HittableEnemies`. […]
- **ModifyDamageMultiplicative** *(hook)* — The arithmetic and the facing logic are exact -- `dealer == null -> 1m`, `target != base.Owner -> 1m`, then 1.5x only if the dealer holds the marker power OPPOSITE the facing (SurroundedPower.cs:46-72 vs powers.py:2559-2565), and 1.5 is dyadic so hook_dispatch G9 does not bite (`power_census.py multipliers`). […]
### `swipe`

- **BeforeDeath** *(hook)* — HOOK SLOT: C# is `BeforeDeath`, fired at CreatureCmd.cs:503 **before** `Hook.ShouldDie` and therefore before any death prevention; the sim uses `hooks.on_death`, fired at cmds.py:105 only on the branch where should_die returned True. Two consequences. […]
### `tender`

- **AfterCardPlayed** *(hook)* — The applier is dropped. TenderPower.cs:50-51 applies Strength and Dexterity -1 with `applier: base.Applier` -- the creature that applied Tender -- and `silent: true`; powers.py:2115-2116 calls PowerCmd.apply with no applier at all. […]
- **AfterSideTurnEnd** *(hook)* — NARROWED 2026-07-27, RE-OPENED 2026-07-28: the SLOT fix landed, the APPLIER defect this entry used to carry verbatim did not, and the flip dropped its text. CLOSED (the slot): the player-side leg moved off the sim's Hook.BeforeTurnEnd slot (`on_player_turn_end`) onto `after_player_turn_end`, which combat.py:809 dispatches AFTER _process_turn_end_cards and the hand flush -- the sim's port of Hook.AfterTurnEnd (CombatM […]
### `territorial`

- **TerritorialPower.cs:23 `participants.Contains(base.Owner)`** *(guard)* — Same substitution as HighVoltagePower's: the sim tests `not self.owner.is_dead` (powers.py:1273) where C# tests side participation, which a retained corpse still satisfies. Identical mechanism, identical verdict (rule 3), identical dormancy -- Byrdonis is never retained after death. […]
- **TerritorialPower.cs:26 `applier: base.Owner`** *(guard)* — MISSING `applier=`. C# passes `base.Owner` as the applier (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)`); the sim calls `PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)` with no applier, so `applier` is None through hooks.modify_power_amount (cmds.py:297), hooks.on_power_applied (cmds.py:327) and hooks.on_power_amount_changed (cmds.py:312), and the grant […]
### `the_bomb`

- **TheBombPower.cs:51 / :56 CombatState.HittableEnemies** *(guard)* — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs:308-322), so the sim aims at creatures the game considers unhittable -- a mid-revival Illusion (powers.py:1572-1575) or a withered Decimillipede segment (powers.py:2354-2357). […]
### `vigor`

- **ModifyDamageAdditive** *(hook)* — The sim keeps only the FIRST of C#'s four guards. C# (VigorPower.cs:57-77) tests, in order: base.Owner != dealer (present, powers.py:2430-2431), !props.IsPoweredAttack() (present structurally -- cmds.py only runs the additive family for powered damage), `commandToModify != null && cardSource != null && cardSource != commandToModify.ModelSource` (ABSENT), and `commandToModify != null && commandToModify.Attacker != dea […]
### `vital_spark`

- **AfterPowerAmountChanged** *(hook)* — C# re-syncs every Tainted affliction's Amount to the power's new Amount from `AfterPowerAmountChanged` with a `power != this` guard (VitalSparkPower.cs:79-98), so it fires on ANY amount change -- a stack, a decrement, or an Unsettling-Lamp-doubled application. The sim folds the sync into `on_stack` (powers.py:3083-3089), which cmds.py calls only on the re-application path. […]
- **AfterRemoved** *(hook)* — C#'s AfterRemoved clears every Tainted affliction on EVERY removal path (VitalSparkPower.cs:58-77, guarded by `oldOwner.CombatState == null`); the sim hangs the same sweep on `on_death` filtered to the owner (powers.py:3091-3100) and then calls `self._expire()`. […]
- **BeforeCombatStart** *(hook)* — STAYS OPEN, DORMANT -- reasoning REPLACED ENTIRELY (2026-08-01, round 13, R3 + review). The record's stated mechanism was wrong: CardCmd.Afflict (CardCmd.cs:625-659) does NOT overwrite. It refuses a different-type affliction via CanAfflict (AfflictionModel.cs:200-203, which the sim's own cmds.py CardCmd.afflict already ports) and STACKS a same-type one (CardCmd.cs:656). […]
### `vulnerable`

- **CrueltyPower.cs:19-22 `target == base.Owner` -> unmodified** *(guard)* — Cruelty's own self-exclusion is dropped. C# skips the Cruelty bonus when the Vulnerable target IS the Cruelty holder; powers.py:707-710 reads `dealer.powers.get('cruelty')` with no such test, so a Cruelty holder attacking its own Vulnerable self would get the bonus in the sim and not in the game. […]
- **VulnerablePower.cs:41-45 DebilitatePower leg** *(guard)* — DebilitatePower is not ported (`grep -c DebilitatePower sts2_rl/powers.py` returns 0), so the third link of C#'s modifier chain has no sim counterpart. Per binding rule 1 an unported C# side is a DORMANT gap, not a waiver. Named trigger: porting DebilitatePower.
- **ModifyDamageMultiplicative** *(hook)* — The base multiplier and both ported modifiers are right, but the value is computed in FLOAT where C# uses DECIMAL, which puts this hook inside hook_dispatch gap G9's blast radius. C# reads DamageIncrease = 1.5m from the DynamicVar (VulnerablePower.cs:12,27) and threads it through PaperPhrog, then CrueltyPower, then DebilitatePower (:30-45). […]
### `weak`

- **ModifyDamageMultiplicative** *(hook)* — The sim returns the bare literal 0.75 and has no modifier chain at all, where WeakPower.cs:24-35 threads DamageDecrease = 0.75m through PaperKrane (the TARGET's relic, -0.15m) and then DebilitatePower. Neither is ported -- `ls sts2_rl/relics/ | grep -i paper` returns joss_paper, lead_paperweight and paper_phrog but no paper_krane, and `grep -c DebilitatePower sts2_rl/powers.py` returns 0 -- and there is no modify_wea […]
### `withering_presence`

- **AfterCardPlayed** *(hook)* — RE-VERIFIED 2026-08-04: the sim's own architecture for the Wither's upgrade-matching CHANGED since the last audit and the record's mechanism description is stale on that one point, though the verdict and both named dormant gaps still hold. The mechanism is right -- count the target player's card plays down from 6, add a Wither to HAND at 0, reset to 6. […]

## Unclassified gaps

The entry does not state LIVE or DORMANT in those words. Listed separately
rather than assumed either way — settling them is outstanding work.

### `dampen`

- **AfterApplied** *(hook)* — One finding remains open; the other is CLOSED. (1) MECHANISM, the same substitution as illusion's, STILL OPEN: C#'s AfterApplied runs after PowerCmd registers the power; the sim does the work in __init__, i.e. inside `power_cls(...)` at cmds.py:324 and therefore BEFORE hooks.register and hooks.on_power_applied. […]
### `illusion`

- **IllusionPower.cs:34-45 FollowUpStateId** *(guard)* — Re-executed rather than cited: confirmed by direct class inspection that both of the sim's two `IllusionPower` appliers (`EyeWithTeeth`, `Parafright`) are single-move, non-`MachineMonster` classes, matching their C# sources' single self-looping `MoveState` exactly. The record's post-2026-07-26 reasoning holds; this closes it with fresh evidence instead of leaving it to a third re-read. […]
### `suck`

- **Counting GROUPS with unblocked damage, not individual results** *(guard)* — Re-executed rather than cited: confirmed FossilStalker is the power's sole applier in the entire C# source (not just the sim), and confirmed by reading `fossil_stalker.py` in full that none of its three moves is AoE (LASH's 2 hits are sequential single-target, not simultaneous multi-target, so it does not trigger the group-vs-result distinction either). […]

## Regenerating

```
py audit/tools/gap_ledger.py > audit/content/power/gap-ledger.md
```
