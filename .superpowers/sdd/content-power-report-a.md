# Stream report — content audits: powers, HALF A

Branch `audit-power-a`, worktree `C:\Users\Perry\Desktop\sts2-rl-power-a`, based
on `audit-power` at `6c3f2504`. Half A is the 41 player-side units (Ironclad
card powers, colorless, potion-source, event-card) from
`docs/superpowers/prompts/2026-07-26-content-power-continuation.md`.

**Do not fold this into `.superpowers/sdd/content-power-report.md` by hand** —
half B is writing `-b.md` concurrently; whoever merges the two branches folds
both in. Section numbering here deliberately mirrors the main report's.

**HALF A IS COMPLETE — all 41 units audited, 0 invalid, 0 stale.**

| | |
|---|---|
| half-A units audited | **41 / 41** |
| power units audited overall | 86 / 134 (`py tools/audit_status.py --kind power`) |
| half-A rollups | 34 gap, 4 faithful, 2 waiver, 1 deliberate-divergence |
| suite | 2476 passed / 31 xfailed at every batch boundary |
| commits | batch 1 `dfca8463`, batch 2 `5ff2baf8`, batch 3 (this) |

## Batch 3 — 11 units (half A finished)

`buffer`, `vigor`, `free_attack`, `fasten`, `juggernaut`, `block_next_turn`,
`calamity`, `vicious`, `stratagem`, `retain_hand`, `improvement`.

Rollups: 7 gap, 2 faithful (`vicious`, `stratagem`), 1 waiver (`fasten`),
1 deliberate-divergence (`block_next_turn`). The modifier-family group plus the
leftovers.

## Batch 2 — 15 units

`mayhem`, `stampede`, `nostalgia`, `plating`, `battleworn_dummy_time_limit`,
`automation`, `the_bomb`, `toric_toughness`, `confused`, `curious`,
`the_gambit`, `no_block`, `unmovable`, `diamond_diadem`, `gigantification`.

Rollups: 13 gap, 1 faithful (`no_block`), 1 waiver (`diamond_diadem`). Chosen
to close out the mechanisms batch 1 opened (the two auto-play phases, the
`InstanceType` cluster, the pile-decision chain) plus the block/damage-modifier
group.

## Batch 1 — 15 units

The six `TemporaryStrengthPower` subclasses (`setup_strike`, `reptile_trinket`,
`feeding_frenzy`, `mangle`, `dark_shackles`, `shackling_potion`) and the nine
turn-start / energy units (`clarity`, `draw_cards_next_turn`, `prep_time`,
`entropy`, `rolling_boulder`, `energy_next_turn`, `radiance`, `pyre`,
`hello_world`).

Rollups: 11 gap, 2 faithful, 1 waiver, 1 faithful. Chosen this way because the
six temp-strength units share one base class (one C# read, six records) and the
nine others share one turn-start ordering question (one `CombatManager` read,
nine records) — the marginal cost per unit inside a mechanism group is very low.

## 4. LIVE gaps found in half A (all executed)

1. **`turn_structure` G8's AutoPrePlay half is LIVE, and G8 does not name the
   power that makes it live.** G8 says the AutoPrePlay half is *dormant* because
   "the two ported users' effects (play cards / auto-play one Skill) do not read
   any other turn-start listener's output", naming only Whispering Earring and
   the Imbued enchantment. **`MayhemPower` is a third ported
   `AfterAutoPrePlayPhaseEntered` implementer** (`MayhemPower.cs`, applied by
   the ported Colorless card Mayhem, `cards/colorless_powers.py:157-174`) and it
   *does* read other turn-start listeners' output. In the game Mayhem's
   auto-plays run at `CombatManager.cs:568` → `RunAutoPrePlayPhase`
   (`:613-619`), strictly after `Hook.AfterSideTurnStart` (`:522`) and after
   `SetupPlayerTurn`'s `Hook.AfterPlayerTurnStart` (`:675`). In the sim
   `MayhemPower.on_player_turn_started` (`powers.py:3572-3583`) is in the *same*
   dispatch as every other turn-start power, so the order is
   hook-registration order. **Two executed witnesses, both on ported Colorless
   power cards a single run can hold:**
   - **Prep Time × Mayhem.** `PrepTimePower 3` + `MayhemPower 1`, one Strike on
     top of the draw pile: Prep Time applied first → the auto-played Strike
     deals **9** (6 + Vigor 3, Vigor consumed); Mayhem applied first → **6**,
     with `Vigor(3)` left unspent. The game always deals 9.
   - **Rolling Boulder × Mayhem.** `RollingBoulderPower 5` + `MayhemPower 1`
     against a 4-HP enemy, one Strike on top of the draw pile: boulder first →
     the enemy dies, combat ends, Mayhem's own `combat.is_over` guard
     (`powers.py:3577`) leaves the Strike in the **draw** pile; Mayhem first →
     the Strike is played into the **discard** pile and the boulder fires after.
     The game always resolves the boulder first. A card's final pile is
     conformance-visible and is in the RL observation, and the extra play
     perturbs every later shuffle.
   - A third, on the same mechanism: **Relax × Mayhem.** `DrawCardsNextTurn 2` +
     `Mayhem 1`, Relax on top of the draw pile: power first → the old instance
     expires, Mayhem plays Relax, and the fresh `Draw Cards Next Turn(2)`
     survives (the game's answer — the game removes the old instance at `:522`
     and only reaches Mayhem at `:568`); Mayhem first → Relax stacks onto the
     live instance (2 → 4) and the expiry then deletes the whole thing, so the
     player **loses two bonus draws the game grants**.

   This is reported rather than re-verdicted (binding rule 3): the verdict is
   `gap` on both sides. What the seam session should change is **G8's dormancy
   argument on the AutoPrePlay side and its list of implementers.**

2. **The player-side `AfterSideTurnEnd` slot gap now has a *damage* witness —
   the temp-strength family × Stampede.** The main report's section 4 item 11
   established the group is live via `StampedePower`. Executed here on the
   sharpest instance: `SetupStrikePower 2` + `StampedePower 1`, one Strike in
   hand. Ending the turn deals **6** when the temp-strength power was applied
   first (its revert runs first, so the auto-played Strike loses the +2) and
   **8** when Stampede was applied first. The game always deals 8, because
   `TemporaryStrengthPower.AfterSideTurnEnd` is dispatched by `Hook.AfterTurnEnd`
   (`CombatManager.cs:1307`), *after* `Hook.AfterAutoPostPlayPhaseEntered`
   (`:1167`, Stampede) and after `BeforeTurnEnd` (`:1179`). Affects all six
   temp-strength units' **player-owned** legs (`setup_strike`,
   `reptile_trinket`, `feeding_frenzy`, and `flex_potion` which is one of the 4
   roster-invisible units); the **enemy-owned** legs (`mangle`,
   `dark_shackles`, `shackling_potion`) use `on_enemy_side_end`
   (`combat.py:345`) and are in the **right** slot.
   Note the fix interaction: moving the `AfterSideTurnEnd` group to
   `after_player_turn_end` (`combat.py:665`) fixes *this* witness, but Stampede
   is still in the wrong phase for `turn_structure` G8's own Cloak Clasp
   witness, which is a `BeforeSideTurnEnd` relic. Both fixes are needed.

3. **`hello_world` — wrong RNG stream and wrong selection algorithm, with the
   correct helper already written and unused.** `HelloWorldPower.cs:25-27` is
   `CardFactory.GetDistinctForCombat(..., Rng.CombatCardGeneration)`, i.e.
   `FilterForCombat(pool).TakeRandom(n, rng)` == `UnstableShuffle(rng).Take(n)`
   (`CardFactory.cs:119-129`, `IEnumerableExtensions.cs:17`). `powers.py:2826`
   is `combat._rng.sample(commons, n)` on the **shared unseeded**
   `random.Random` (`combat.py:88`).
   `cards.pool.get_distinct_for_combat_parity` (`pool.py:182-204`) is an
   already-documented parity port of exactly this call driven by
   `combat.combat_rng.card_gen`, and **seven other sites use it**
   (`potions.py:435,468,1082,1120,1148`, `cards/infernal_blade.py:40`,
   `relics/vexing_puzzlebox.py:26`). Identical defect to `aggression`'s
   (main report item 8). Reachable: Hello World is a ported Trash Heap card
   (`cards/trash_heap_cards.py:186-203`).

4. **`entropy` — wrong RNG stream on the transform.** `EntropyPower.cs:31`
   threads `Rng.CombatCardSelection` into `CardCmd.TransformToRandom`
   (`CardCmd.cs:323-326`); `CardCmd.transform_to_random` picks with
   `hooks.combat._rng.choice(options)` (`cmds.py:435`) — the shared unseeded rng
   again, where `combat.combat_rng.card_selection` (`combat_rng.py:21,51`)
   exists. Ported Colorless power card (`cards/colorless_powers.py:74-94`).
   The *selection screen* half is faithful: `CardSelectCmd.from_hand` →
   `CombatState.select_cards` (`combat.py:560-581`) delegates to an installed
   `card_selector`, which is the sim's modelled player-choice seam.

5. **`rolling_boulder` — the sharpest reachable witness for `power_cmd` G5
   (`PowerInstanceType`), and the divergence is arithmetic, not bookkeeping.**
   `RollingBoulderPower.cs:24` is `PowerInstanceType.Instanced`: every
   application is an independently tracked instance with its own growing Amount
   (`SetAmount(Amount + 5)`, `:52`). The sim merges by id (`cmds.py:308-311`).
   The ported Colorless card Rolling Boulder is a normal deck card that can be
   drawn and played twice in one combat, so **two simultaneous instances are
   reachable**: the game then deals 5+5 = 10 next turn and 10+10 = 20 the turn
   after, while one merged sim instance holds 10 and deals 10, then 15, then 20
   — 5 short on two consecutive turns. It also fires **one** damage sweep where
   the game fires two, halving the `on_damage_received` dispatches (Thorns, Curl
   Up) the enemies see. `power_cmd` G5 currently says "no
   currently-demonstrated collision"; this is one.

6. **`draw_cards_next_turn` — both `AmountOnTurnStart` guards dropped.**
   `DrawCardsNextTurnPower.cs:28-31` returns the draw count unchanged when
   `AmountOnTurnStart == 0`, and `:37` removes the power only when
   `AmountOnTurnStart != 0`. `PowerModel.AmountOnTurnStart` (snapshotted in
   `Creature.BeforeTurnStart`, `Creature.cs:673-679`, called at
   `CombatManager.cs:453` before any other turn-start hook) **has no sim
   counterpart at all** — `grep -rn amount_on_turn_start sts2_rl/` returns
   nothing. Its documented purpose (`PowerModel.cs:199-205`) is exactly
   "preventing same-turn activation when applied mid-turn (e.g., via auto-play
   effects)". The removal half is live via the Relax × Mayhem witness above; the
   `ModifyHandDraw` half is dormant with its trigger named. `hello_world` drops
   the same field (`HelloWorldPower.cs:22,27`, used as both guard *and* count) —
   dormant there.

### Batch 2 additions to section 4

7. **`plating` — a `BeforeSideTurnEndEarly` phase dropped, and it costs HP.**
   `PlatingPower.cs:58-60` says outright why the hook is Early: *"We do this in
   early so that it triggers before end-of-turn damage effects."* The sim has no
   phase passes (`hook_dispatch` G3) and fires the block gain from the plain
   `on_player_turn_end` dispatch. **Executed:** Plating 4 on the player plus
   Constrict 6 — applying Constrict first costs the player **6 HP** and leaves
   **4 unused block**; applying Plating first costs **2 HP**. The game always
   costs 2. Reachable: player-side Plating four ways (`cards/stone_armor.py:38`,
   `relics/gorget.py:17`, `cards/colorless_powers.py:121`, `potions.py:592`) and
   Constrict from the ported Act-1 Slithering Strangler
   (`monsters/overgrowth/slithering_strangler.py:43`).
   `plating` also has the **wrong slot** on its decay leg (C#
   `AfterSideTurnStart` = post-draw, sim `on_player_turn_start` = pre-draw),
   dormant.
8. **`stampede` — wrong RNG stream, on top of `turn_structure` G8's phase gap.**
   `StampedePower.cs:28` picks the Attack with `Rng.Shuffle.NextItem(items)` —
   the **Shuffle** stream. `powers.py:1041` uses `combat._rng.choice`.
9. **`confused` — wrong RNG stream, widest blast radius of the four.**
   `ConfusedPower.cs:53` is `Rng.CombatEnergyCosts.NextInt(4)`;
   `powers.py:3873` is `combat._rng.randrange(4)`. Confused re-costs **every**
   card the player draws for the whole combat, so a Snecko Eye / Fake Snecko Eye
   run diverges on the first draw and perturbs every later shared-rng consumer.
   Both appliers are ported relics.
   **Four of half A's units now carry the same wrong-stream defect** —
   `hello_world` (`CombatCardGeneration`), `entropy` (`CombatCardSelection`),
   `stampede` (`Shuffle`), `confused` (`CombatEnergyCosts`) — plus
   `aggression` from the main report. Every one of the four correct accessors
   exists on `CombatRng` (`combat_rng.py:17-25`). This is a **systematic** defect
   worth its own `PROMPT.md` bug class, not five coincidences.
10. **`nostalgia` — the pile decision is made at the wrong TIME.**
    `Hook.ModifyCardPlayResultPileTypeAndPosition` is called at
    `CardModel.cs:1890`, **before** the play loop (`:1904`), `OnPlay`,
    `History.CardPlayStarted` (`:1930`) and `AfterCardPlayed` (`:1959`). The sim
    calls it at `combat.py:510`, **after** the whole loop. So a card whose own
    effect plays another card is counted against its own allowance: with
    Nostalgia 1, C# redirects the outer card and the sim sends it to the discard.
    Separately, C# counts `CardPlaysStarted` (one per play-count iteration) where
    the sim counts `CardPlayedEntry` (one per card, `combat.py:514`, outside the
    loop), so any replay source (Throwing Axe, Duplication) consumes the
    allowance at **half** the rate — `hook_dispatch` G4's blast radius, with a
    wrong *pile* as the observable rather than a wrong counter.
    `nostalgia` is also the **third** tuple-return-type override the harness
    silently missed.
11. **`mayhem` — `AutoPlayFromDrawPile` is two-phase and the sim interleaves.**
    `CardPileCmd.cs:931-966` moves **all** `count` cards into `PileType.Play`
    first (`:939-955`) and plays them after (`:956-965`); `powers.py:3576-3583`
    picks and plays one at a time. At Mayhem 2 the game commits both cards before
    either resolves — and they sit in `PileType.Play`, so a reshuffle the first
    card triggers excludes them (`PROMPT.md` bug class 7) — while the sim's
    second pick can be a card the reshuffle just moved. Not executed; the phase
    gap already carries the unit's live label.
12. **`unmovable` — a history query replaced by hand-rolled state that resets in
    the wrong window, and the per-`CardPlay` exclusion degraded to per-card.**
    `UnmovablePower.cs:35` counts `BlockGainedEntry` rows with
    `e.CardPlay != cardPlay`; the sim keeps `_plays_used`/`_active_card` and
    clears them from `on_player_turn_start` (`powers.py:1127-1130`), so the
    counter survives the whole enemy turn, and a doubled block card consumes one
    stack in the sim and two in the game — so a Throwing-Axe-doubled Iron Wave
    gets double block **twice** in the sim and once in the game.
13. **`automation` and `toric_toughness` — two more reachable, arithmetically
    divergent `power_cmd` G5 witnesses.** `automation`'s per-instance state is a
    *counter*: two C# instances each fire once per 10 cards drawn (two separate
    grants on the same draw), where the sim merges into one power with one
    `cards_left` and grants the summed amount at half the frequency — and the
    merged counter is never reset by the second application, so the second
    Automation's first trigger arrives up to 9 draws early.
    `toric_toughness` is the sharper one: two C# instances at 2 turns with block
    5 and 9 give **14 block for two turns**; the sim holds one instance at
    Amount 4 with block 9 and gives **9 block for four turns** — both the
    per-turn amount and the duration wrong, in opposite directions. Its own
    docstring (`powers.py:1194-1199`) admits it. Both appliers are normal deck
    cards playable twice in one combat.
    **`the_bomb` is the counter-example and it holds up**: its `self.bombs` fuse
    list (`powers.py:3768-3802`) reproduces N independent instances exactly; the
    only residue is per-instance identity and `set_damage` always writing the
    newest fuse.
14. **`the_gambit` — the kill bypasses a death prevention the engine just
    honoured.** `cmds.py:96-113` floors a prevented death at 1 HP and clears
    `is_dead`, after which `cmds.py:121` lets `on_damage_received` fire and this
    power calls `CreatureCmd.kill` outright. In C# `CreatureCmd.Kill` is itself
    subject to the death pipeline, so the preventer gets a second say. Dormant —
    the sim's preventers are the Illusion revive (enemy-only) and Fairy in a
    Bottle, and The Gambit is player-only.
15. **`gigantification` — the latch is cleared against CARD identity where C#
    uses ATTACK-COMMAND identity.** Dormant (`combat.py:477-494` fires exactly
    one `before_attack`/`after_attack` pair per play-count iteration), but if a
    card ever issued two attack commands in one play the sim would re-enter the
    `_card_to_modify is None` arm and triple the second hit for free.
    Recorded positively too: `gigantification` and `vigor` are the **only two**
    power units that use the sim's `before_attack`/`after_attack` slots, which
    `thorns`, `curl_up` and `skittish` all fail to use.

### Batch 3 additions to section 4

16. **`improvement` — the effect is entirely unimplemented, and it is
    run-level.** `ImprovementPower.cs:17-31` upgrades `Amount` random upgradable
    **deck** cards after combat (candidates from `PileType.Deck` filtered on
    `IsUpgradable`, picked *without* replacement off
    `Rng.CombatCardSelection`). `powers.py:2890-2902` is a **data-only stub with
    no methods at all**. Its docstring calls this a no-op because the sim fights
    over a deep-copied deck; per binding rule 1 that is a **dormant gap, not a
    waiver** — the dormancy rests on an engine property, not on scope. Reachable
    content: the ported Mad Science card's Improvement rider from the ported
    Act-3 Tinker Time event, the same card that supplies `curious`. The sim has
    no post-combat deck-access slot to hang it on (`hooks.py:271-277`'s
    `on_combat_end` is combat-scoped), so this is engine-shaped, not a one-line
    omission. Two triggers: wiring combat upgrades back to the run deck, or a
    conformance replay that plays Mad Science with the rider.
17. **`juggernaut` — wrong RNG stream, with the correct accessor used three
    lines away for the same purpose.** `JuggernautPower.cs:24` is
    `Rng.CombatTargets.NextItem(hittableEnemies)`; `powers.py:792` is
    `combat._rng.choice(living)` — while `combat.py:546` picks an auto-play's
    target with `combat_rng.targets.choice(living)`, citing the *same* C# stream.
    **Seventh unit with this defect.** Every block gain triggers Juggernaut, so a
    Juggernaut run diverges on its first block in a multi-enemy fight.
18. **`calamity` — wrong RNG stream *and* the wrong pool helper, plus the G4
    count.** `CalamityPower.cs:48-50` is
    `CardFactory.GetForCombat(..., Rng.CombatCardGeneration)` (the
    *with*-replacement variant, one `NextItem` per card); `powers.py:3493` calls
    `random_pool_cards(combat._rng, ...)`, the **legacy shared-rng** helper,
    where `cards.pool.get_for_combat_parity` (`pool.py:164-179`) is the written
    parity port that takes the `card_gen` accessor. The with-replacement
    *semantics* are right on both sides. Separately, C# fires
    `Before`/`AfterCardPlayed` once per replay iteration, so a doubled Attack
    generates 2 × Amount cards in the game and Amount in the sim
    (`hook_dispatch` G4). Its `BeforeCardPlayed` **latch** is also absent, so the
    Amount is read at play *end* rather than snapshotted at play *start*
    (dormant — no ported Attack applies Calamity).
19. **`retain_hand` — the tick is skipped entirely on an extra turn.**
    **Executed:** with a `should_take_extra_turn` listener registered (the shape
    of the ported Ancient relic Pael's Eye, `relics/paels_eye.py:36-46`), one
    `end_turn` leaves `Retain Hand(1)` **still on the player**, where the same
    `end_turn` without it leaves `None`. `combat.py:648-652` short-circuits at the
    *top* of `end_turn` and never reaches `on_player_turn_end`, the flush,
    `after_player_turn_end` **or** the enemy turn; C# evaluates
    `ShouldTakeExtraTurn` in `SwitchFromPlayerToEnemySide`
    (`CombatManager.cs:1360-1373`) *after* both `EndPlayerTurnPhase` methods, so
    `Hook.AfterTurnEnd` (`:1307`) has already decremented. Root cause is
    `turn_structure` **G3** (already LIVE); this is a concrete content instance,
    and note **moving the tick to `after_player_turn_end` would not fix it**.
    `retain_hand` is also the sim's **only** `should_flush_hand` implementer,
    i.e. `turn_structure` **G4**'s entire trigger surface in the power tier.
20. **`free_attack` — the pile guard is missing, and the stack count is halved by
    G4.** `FreeAttackPower.cs:26-39` only zeroes the cost when the card's pile is
    `Hand` or `Play`; `powers.py:1147-1151` zeroes every Attack of the owner's
    regardless. Dormant for the cost itself, but `modify_card_energy_cost` is
    also what `previews.py` and the RL observation read, so a draw-pile Attack
    *displays* as free. And C#'s `BeforeCardPlayed` fires per replay iteration
    (two stacks for a doubled Attack) where the sim's `on_energy_spent` fires
    once. `free_attack` is `hook_dispatch` **G3**'s live witness from the Late
    side (Tangled early vs Free Attack late), recorded from this end.
21. **`vigor` — two of C#'s four `ModifyDamageAdditive` guards are missing.** The
    load-bearing one is `commandToModify != null && cardSource != null &&
    cardSource != commandToModify.ModelSource` (`VigorPower.cs:68`), which
    confines the bonus to the **latched** card. Without it, a different card's
    powered damage from the same dealer while an attack is in flight gets the
    full Vigor in the sim and nothing in the game. Dormant — no ported Ironclad
    card plays another card mid-attack-bracket. Recorded positively too:
    `vigor`'s `AfterAttack` consumes the **snapshotted** amount, so Vigor gained
    during the attack survives it on both sides.
22. **`buffer` — a `Late` phase dropped in the one modifier family where the sim
    *does* have the notification machinery.** `AbstractModel` declares **four**
    hp-loss modifier hooks (`ModifyHpLost{Before,After}Osty{,Late}`,
    `AbstractModel.cs:1669,1689,1708,1728`) plus **two** notification hooks
    (`:905`, `:913`); the sim has **one** `modify_hp_lost` + **one**
    `after_modify_hp_lost` (`hooks.py:126-154`) holding all **seven** current
    listeners (`intangible`, `slippery`, `hardened_shell`, `buffer`,
    `beating_remnant`, `the_boot`, `tungsten_rod`). `BufferPower.cs:16-19` says
    why it is Late: *"other effects may reduce damage taken to 0 too, and it's
    more player-friendly for them to trigger first so that this power doesn't
    have to decrement."* Dormant, and the reachability was **checked**: of the
    six co-listeners only `hardened_shell` can return 0, and it is an enemy power
    that self-filters to its owner, so it can never share a creature with
    player-side Buffer.
    Recorded positively: `buffer`'s `AfterModifyingHpLostAfterOsty` is the **one
    place in the whole power stream** where the sim implements C#'s
    modify-then-notify-only-the-modifiers protocol properly
    (`cmds.py:85-87` + `hooks.py:145-146,152-154`) — the exact machinery
    `power_cmd` G4 finds absent from the power-amount family.
23. **`vicious` is the stream's cleanest re-architecture, and worth naming as
    such.** `Hook.AfterPowerAmountChanged` fires from *both* `PowerCmd`
    pipelines (`power_cmd` steps 23 and 33); the sim has a separate hook for each
    (`on_power_applied` at `cmds.py:327`, `on_power_amount_changed` at `:312`)
    and this power implements **both** and routes them to one `_maybe_draw`. All
    three C# guards present, including the `<= 0` gate that correctly makes a
    Single-stack no-op not draw. `faithful`.

## 6. Cross-record disagreements spotted under rule 3

1. **`turn_structure` G8's AutoPrePlay dormancy argument is wrong** — see
   section 4 item 1. This is the one substantive disagreement half A has found
   so far, and it is settled by execution rather than reported as open.
2. **`power_cmd` G5's "no currently-demonstrated collision" is now false** —
   see section 4 item 5 (`rolling_boulder`).
3. **`power_cmd` G1's trigger is re-confirmed, after examining two new
   candidate routes and finding both inert.** Worth recording because both
   looked live at first:
   - `TemporaryStrengthPower.cs:154` really is a ported route to a **negative
     `StrengthPower` on an enemy with `applier = the player`** (Mangle, Dark
     Shackles, Shackling Potion), and **five ported enemies self-apply
     Artifact** (`monsters/underdocks/punch_construct.py:40`,
     `monsters/overgrowth/cubex_construct.py:32`, `monsters/hive/chomper.py:38`,
     `monsters/glory/mecha_knight.py:36`, `monsters/glory/aeonglass.py:41`) — so
     rule 6's two halves are satisfied for the trigger. It still cannot diverge:
     the *wrapper* is itself a Debuff and is intercepted first, C#'s
     `BeforeApplied` then fires with `modifiedAmount == 0` and `PowerCmd.cs:103`
     no-ops the inner Strength, and the sim returns at `cmds.py:306` before
     constructing the wrapper at all. Both sides: one Artifact stack consumed,
     no Strength change.
   - `TemporaryStrengthPower.cs:179`'s revert applies a **negative
     `StrengthPower` to the player** for the positive members of the family,
     which `GetTypeForAmount` arm 1 calls a Debuff. All three consumers were
     traced and none fires: player-side Artifact does not exist anywhere in the
     game (G1's own grep), Lamp's latch needs `cardSource != null` and this call
     passes null, and `PowerCmd.cs:144`'s `SkipNextDurationTick` reads the
     **static** `power.Type`, not `GetTypeForAmount`.

   So porting Malaise or Resonance remains the single named trigger.
4. **The main report's own section 6 item 1 is partly WRONG, and the correction
   is a narrowing.** It named three units whose effects escape the
   "every ported listener self-filters to its own owner" argument behind
   `turn_structure` G5's dormancy, and asked for a **two-dummy Battle Friend
   witness**. There is no such witness to execute:
   `BattlewornDummyEventEncounter.GenerateMonsters`
   (`BattlewornDummyEventEncounter.cs:62-72`) returns a
   `_ReadOnlySingleElementList` — **exactly one dummy**, chosen by `Setting` —
   and the sim's three encounters each list a single monster class
   (`monsters/glory/battle_friend.py:67-78`). The dummy's only move is
   `NOTHING_MOVE`, so its escape cannot affect another creature's turn either.
   `battleworn_dummy_time_limit` therefore does **not** make G5 live. It is also
   **in half A, not half B** as the continuation prompt's section-6 note claims;
   the two remaining candidates (`asleep`, `slumber`) really are half B's.
5. **`hook_dispatch` G2's and G3's live witnesses are both `curious`, and it is
   half A's unit.** Recorded from the unit's end at the same `gap` verdict, so
   rule 3 holds. Worth noting because it means the seam record's most-cited
   content example is now audited independently and agrees.
6. **`hook_dispatch` G4's blast radius reaches two more units with a
   *state-changing* observable, not just a counter.** G4's own text says "every
   one of the sim's 48 `on_card_played` listeners" widens it; `nostalgia` (wrong
   destination pile) and `unmovable` (double block granted twice) are two where
   the consequence is player-visible state rather than a relic counter.

## 7. Lessons for `tools/audit/PROMPT.md` (relic stream to fold in)

`PROMPT.md` is still **v1** as of this batch — none of the main report's seven
proposed lessons has landed, so all seven are still live. Half A adds:

7. **New bug class — `PowerModel.AmountOnTurnStart` has no sim counterpart.**
   Checklist line: *if the C# power reads `AmountOnTurnStart`, the sim has
   nothing to port it to (`grep -rn amount_on_turn_start sts2_rl/` → 0); the
   field is snapshotted in `Creature.BeforeTurnStart` (`Creature.cs:673-679`) at
   `CombatManager.cs:453`, before every other turn-start hook, and its purpose is
   to suppress same-turn activation by an auto-play.* Three ported powers read
   it: `draw_cards_next_turn`, `hello_world`, `summon_next_turn` (unported).
8. **New bug class — the turn-start phase table, which is a different table
   from the turn-END one already proposed as lesson 2.** In call order:
   `Creature.BeforeTurnStart` (`:453`, the `AmountOnTurnStart` snapshot) →
   `Hook.BeforeSideTurnStart` (`:458`) → `AfterTurnStart`/`ClearBlock` (`:496`)
   → `Hook.AfterBlockCleared` (`:504`) → `SetupPlayerTurn` (`:514`: energy reset
   `:641`, `AfterEnergyReset` `:650`, `BeforeHandDraw` `:652`, `ModifyHandDraw`
   `:654`, `Draw` `:673`, `AfterPlayerTurnStart` `:675`) →
   `Hook.AfterSideTurnStart` (`:522`) → `RunAutoPrePlayPhase` (`:568` →
   `AfterAutoPrePlayPhaseEntered` `:617`). The sim has **two** slots for all of
   it: `on_player_turn_start` (`player.py:169`, post-energy-reset,
   pre-`modify_hand_draw`) and `on_player_turn_started` (`player.py:186`,
   post-draw). Checklist line: *`BeforeHandDraw` maps correctly to
   `on_player_turn_start` and `AfterEnergyReset` to `on_energy_reset`, but
   `BeforeSideTurnStart` does NOT — it runs before the energy reset in the game
   and after it in the sim; and `AfterPlayerTurnStart`, `AfterSideTurnStart` and
   `AfterAutoPrePlayPhaseEntered` are three ordered phases sharing one sim slot.*
9. **The harness does not follow a C# base class.** Six of this batch's units
   are `TemporaryStrengthPower` subclasses whose own `.cs` file declares only
   `OriginModel` (+ a `protected override IsPositive`, which is not `public` and
   so is correctly not enumerated). All five behavioural hooks — `Type`,
   `StackType`, `BeforeApplied`, `AfterPowerAmountChanged`, `AfterSideTurnEnd` —
   live on the base and the skeleton therefore asks for **one** verdict on a unit
   that needs six. Added by hand with the base class named in the key, and the
   base file flagged as an unhashed third file in every rationale. Checklist
   line: *if the unit's C# class extends something other than `PowerModel`, read
   the base and add its hooks to the record by hand.* This is a **silent**
   under-enumeration, the same failure mode as the tuple-return-type defect in
   the main report's section 8 item 2, and it is far more common — the roster has
   at least 10 such subclasses (`TemporaryStrengthPower` ×4 ported +
   `flex_potion`, `TemporaryDexterityPower`, and the potion-source powers).
11. **New bug class, and it is the highest-yield one half A found — "the power
    does not use the per-purpose RNG accessor."** Five power units now carry it
    (`aggression`, `hello_world`, `entropy`, `stampede`, `confused`), each
    reaching for `combat._rng` (the **shared unseeded** `random.Random`,
    `combat.py:88`) where C# names a specific `RunRngSet` stream. All five
    accessors exist on `CombatRng` (`combat_rng.py:17-25`: `shuffle`,
    `monster_ai`, `card_gen`, `card_selection`, `targets`, `energy`,
    `potion_gen`) and `combat.combat_rng` is the object that carries them. The
    trap is that `combat._rng` and `combat.combat_rng` are **different objects**
    one line apart (`combat.py:88` vs `:94`) and only the second is
    parity-aware. Checklist line: *any C# `Rng.<Stream>` in the unit must appear
    in the sim as `combat.combat_rng.<accessor>`; `combat._rng` is the shared
    legacy rng and is never the right answer under parity. Grep the unit's sim
    body for `_rng.` and check every hit.* Contrast the correct usage one line
    away in the same power: `stampede`'s target pick uses
    `combat_rng.targets.choice` (`combat.py:546`) while its candidate pick uses
    `combat._rng.choice` (`powers.py:1041`).
12. **New checklist line — the two auto-play phases.**
    `AfterAutoPrePlayPhaseEntered` fires at `CombatManager.cs:568` (**after**
    `AfterSideTurnStart` `:522` and `AfterPlayerTurnStart` `:675`) and
    `AfterAutoPostPlayPhaseEntered` at `:1167` (**before** `BeforeTurnEnd`
    `:1179`, `DoTurnEnd` `:1191`, the flush `:1296` and `AfterTurnEnd` `:1307`).
    Neither has a sim slot. `turn_structure` G8 owns the machinery; the per-unit
    obligation is to notice that a power on either hook is *ordered* against
    every other turn-start / turn-end power in the game and is a coin flip in the
    sim.
13. **`PowerInstanceType.Instanced` is a per-unit reachability question with real
    arithmetic behind it.** Three of half A's four `Instanced` units
    (`rolling_boulder`, `automation`, `toric_toughness`) have two simultaneous
    instances reachable from a *normal deck card played twice*, and in all three
    the merge changes numbers, not just bookkeeping. Checklist line: *for an
    `Instanced` power, ask "can the applier fire twice in one combat?" — for a
    deck card the answer is almost always yes — and then work out what the merge
    does to the per-instance state, which is often a counter or a paired value
    rather than the Amount.*
10. **`ITemporaryPower` is absent from the sim as a marker.** No `is_temporary`,
    no `InternallyAppliedPower`, and no `should_power_be_removed_on_death` hook
    among `hooks.py`'s 66. C# has five readers: `IllusionPower.cs:59-66`,
    `Rend.cs:43-50`, `SleightOfFleshPower.cs:23`, `Misery.cs:59`,
    `DebufferModel.cs:15`. Four are unported; **`IllusionPower` is ported**
    (`powers.py:1560ff`) and is a half-B unit, so half B owns the verdict.

## 8. Roster and harness problems (reporting per the contract; I own neither)

1. Section 7 item 9 above — the harness does not follow C# base classes. This
   is a harness change (`list_overrides` would have to walk the `: Base` clause
   and re-scan), not a `name_overrides.json` change.
2. Confirmed the main report's item 1: the 4 roster-invisible powers include
   `flex_potion`, which is a **`TemporaryStrengthPower` sibling of four units in
   half A**. It is genuinely un-auditable through the harness and its findings
   are identical to `setup_strike`'s — 4 lines in `ALL_POWERS` would let it be
   recorded properly.

## 9. Cost data (half A)

- **Batch 1: 15 units.** Front-loaded on the four binding documents, the two
  seam docs, `CombatManager.cs`'s turn-start and turn-end regions, and
  `TemporaryStrengthPower.cs`. The nine census subcommands were run but only
  `typing`, `slots`, `overrides` and `multipliers` were load-bearing.
- **4 units needed execution to settle** (`setup_strike` for the family,
  `prep_time`, `rolling_boulder`, `draw_cards_next_turn` — the last three all
  against Mayhem). Execution was decisive every time and **overturned one
  committed seam dormancy claim** (`turn_structure` G8's AutoPrePlay half).
- **Reused wording matters more than reused code.** The prior session's
  `fill.py` and its `STACK_C` / `SLOT` / `HITTABLE` / `AFTER_DEATH` constants
  were recoverable from the scratchpad and saved roughly a third of the writing
  cost; the constants are what make rule 3 cheap to honour.
- Suite: **223s** (3m43s), unchanged at 2476 passed / 31 xfailed, as expected
  since audits add no code.
- **Batch 2: 15 units, and materially cheaper per unit than batch 1** — the
  turn-start/turn-end `CombatManager` ordering table, the seam gap lists and the
  boilerplate rationales were all already paid for, so the marginal cost was one
  C# dump per 7-8 units plus one sim dump. **2 units needed execution**
  (`plating` against Constrict; `stampede`, whose witness was already run for
  batch 1's temp-strength family). Suite **215s**.
- **The single best return on time in both batches was following one mechanism
  across units instead of going alphabetically.** Batch 1's Mayhem witnesses paid
  for four records (`prep_time`, `rolling_boulder`, `draw_cards_next_turn`,
  `mayhem`); reading `CombatManager.cs`'s two auto-play phases once paid for
  `mayhem`, `stampede` and `plating`; and the `_rng` grep habit found the same
  live defect on four separate units at essentially zero marginal cost.
- **Two of the batch's best findings came from checking a *positive* claim.**
  `the_bomb`'s fuse-list workaround and `no_block`'s structural `Unpowered` gate
  both turned out to be right, and both are worth as much as a gap: they tell the
  gap-fix stream what NOT to touch, and `the_bomb` is the existence proof that
  the `Instanced` merge is fixable per-unit without engine work.

### Batch 3 additions to sections 6, 7 and 9

**Section 6 (rule-3 cross-references), batch 3.** No new *disagreements*; four
new agreements reached independently and recorded so they are verifiable from
both ends:
- `hook_dispatch` **G3**'s live witness pair is `curious` (Early) and
  `free_attack` (Late) — both half A, both now audited, both `gap`.
- `hook_dispatch` **G4** now has six half-A units in its blast radius
  (`nostalgia`, `unmovable`, `free_attack`, `calamity`, plus the two the main
  report already had).
- `turn_structure` **G3** and **G4** are both reached by `retain_hand`, which is
  the sim's only `should_flush_hand` implementer.
- `power/thorns`'s reachability claim (that `cards/juggernaut.py:38` →
  `powers.py:791-794` gives unpowered non-card damage with `dealer` = the player)
  is **confirmed from the `juggernaut` end**: the props really are
  `NON_CARD_UNPOWERED` and the dealer really is the player.

**Section 7 (PROMPT.md), batch 3.** The RNG-accessor bug class (item 11) is now
**seven units** (`aggression`, `hello_world`, `entropy`, `stampede`, `confused`,
`juggernaut`, `calamity`) — and `juggernaut` is the case to quote in the
checklist, because the *correct* accessor is used three lines away in the same
engine for the same C# stream (`combat.py:546`
`combat_rng.targets.choice(living)` vs `powers.py:792`
`combat._rng.choice(living)`). One further lesson:
14. **A "documented no-op" docstring is a dormant gap, not a waiver.**
    `improvement`'s sim class explains why it does nothing; under binding rule 1
    that explanation is the *dormancy argument*, and the verdict is still `gap`.
    Checklist line: *if the sim's docstring says an effect is deliberately not
    implemented, the verdict is `gap` with the docstring as the dormancy
    evidence — `waiver` requires the mechanism to be out of scope, not merely
    inconvenient.* Three half-A units were at risk of being mis-waived this way
    (`improvement`, `fasten`'s `AfterModifyingBlockAmount`, `nostalgia`'s
    presentation-only after-hook); only the first is a gap, and separating them
    took reading the C# bodies rather than the docstrings.

**Section 9 (cost), batch 3.** 11 units, **1 execution** (`retain_hand`'s
extra-turn witness). Cheapest batch by a wide margin: every mechanism the batch
touched had already been named in batch 1 or 2 or in a seam record, so most
entries are one cross-reference plus one `file:line` pair. Suite **221s**.

**Half-A totals.** 41 units in 3 batches; **7 units needed execution** to
settle (`setup_strike`/the temp-strength family, `prep_time`,
`rolling_boulder`, `draw_cards_next_turn`, `plating`, `stampede`,
`retain_hand`), producing **8 executed witnesses**. Execution overturned one
committed seam dormancy claim (`turn_structure` G8's AutoPrePlay half),
falsified one committed speculation (the two-dummy Battle Friend), and confirmed
`power_cmd` G1's trigger against two new candidate routes. Suite ran 3 × ~220s
and never moved off 2476 passed / 31 xfailed.

**Entry counts, which are the useful severity signal** (the main report's
section 9 makes this point and it holds): half A's 41 unit rollups are 34 gap,
but the gaps split roughly **12 live / 60 dormant**, and the live ones cluster
in three mechanisms — the two missing auto-play phases, the missing per-purpose
RNG accessors, and the collapsed modifier phases. Fixing those three would clear
most of half A's live ledger.

## 10. Residual queue — nothing left in half A

All 41 half-A units are audited and committed. What remains for the power stream
is **half B's 48 enemy powers** (a separate branch and report) plus the **4
roster-invisible units** blocked on the 4-line `ALL_POWERS` fix
(`flex_potion`, `heist`, `speed_potion`, `thievery`) — and `flex_potion` in
particular is a `TemporaryStrengthPower` sibling of four half-A units whose
findings apply to it verbatim.

### Handover: the three fixes that would clear most of half A's live ledger

Ordered by how many half-A units each one closes. None is an audit action; all
belong to the gap-fix stream.

1. **Give the sim the two auto-play phases** (`turn_structure` G8). One new
   pre-play slot fired after `on_player_turn_started`, one new post-play slot
   fired before `on_player_turn_end`, with `mayhem` moved to the first and
   `stampede`, Howl From Beyond and Whispering Earring / Imbued to the second.
   Closes the live half of `mayhem`, `stampede`, `prep_time`,
   `rolling_boulder`, `draw_cards_next_turn` and the player-side leg of the six
   `TemporaryStrengthPower` units — **11 units, 4 executed witnesses.**
2. **Route every power's randomness through `combat.combat_rng`.** Seven power
   units reach for `combat._rng` (`combat.py:88`, the shared legacy rng) where
   C# names a stream: `aggression` (`CombatCardSelection`), `hello_world`
   (`CombatCardGeneration`), `entropy` (`CombatCardSelection`), `stampede`
   (`Shuffle`), `confused` (`CombatEnergyCosts`), `juggernaut`
   (`CombatTargets`), `calamity` (`CombatCardGeneration`). Every accessor
   already exists (`combat_rng.py:17-25`) and, for the two card-generation
   cases, so does the parity helper (`pool.py:164-179`, `:182-204`).
   **7 units, all live under seed parity.**
3. **Move the misplaced turn slots**, which is one line each and the population
   is reproducible with `py tools/audit/power_census.py slots`: the player-side
   `AfterSideTurnEnd` group to `after_player_turn_end` (`combat.py:665`), and
   `plating`'s decay from `on_player_turn_start` to `on_player_turn_started`.

Two further items that are cheap and worth doing while the above is open:
`rolling_boulder`, `automation` and `toric_toughness` each need a per-unit
`Instanced` workaround of the kind `the_bomb` already has (`powers.py:3768-3802`
is the model to copy); and `improvement` needs either an implementation or an
explicit `xfail` pin, since today it silently does nothing.

### G9 (non-dyadic multiplicative factors) — half A adds nothing

**No fourth non-dyadic factor exists in half A.** Every multiplicative factor a
half-A unit contributes was checked against `py tools/audit/power_census.py
multipliers` and all are binary-exact: `no_block` ×0.0, `diamond_diadem` ×0.5,
`unmovable` ×2.0, `gigantification` ×3. The only other half-A units touching a
modifier family are `fasten` (block **additive**) and `buffer` (HP-loss, a
replacement not a factor), and `hook_dispatch` G9 already settled by execution
that the additive family is exactly equal to C#'s running fold over integers.
So G9's factor population is still Shrink `0.7`, Slow `0.1` and the
`Vulnerable + Cruelty` computed factor, and **half A does not widen it.** If a
fourth exists it is in half B's enemy powers.
