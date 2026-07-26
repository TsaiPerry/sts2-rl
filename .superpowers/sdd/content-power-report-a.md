# Stream report — content audits: powers, HALF A

Branch `audit-power-a`, worktree `C:\Users\Perry\Desktop\sts2-rl-power-a`, based
on `audit-power` at `6c3f2504`. Half A is the 41 player-side units (Ironclad
card powers, colorless, potion-source, event-card) from
`docs/superpowers/prompts/2026-07-26-content-power-continuation.md`.

**Do not fold this into `.superpowers/sdd/content-power-report.md` by hand** —
half B is writing `-b.md` concurrently; whoever merges the two branches folds
both in. Section numbering here deliberately mirrors the main report's.

| | |
|---|---|
| half-A units audited | 30 / 41 |
| power units audited overall | 75 / 134 (`py tools/audit_status.py --kind power`) |
| suite | 2476 passed / 31 xfailed at every batch boundary |
| commits | batch 1 `dfca8463`, batch 2 (this) |

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

## 10. Residual queue — the 11 half-A units left

`block_next_turn, buffer, calamity, fasten, free_attack, improvement,
juggernaut, retain_hand, stratagem, vicious, vigor`

Ordered by expected yield, with what is already known:

1. **`buffer`** — the only half-A unit on the `ModifyHpLostAfterOstyLate` /
   `AfterModifyingHpLostAfterOsty` pair, i.e. a **Late** phase (`hook_dispatch`
   G3) on the one modifier family the sim *does* carry two-phase machinery for
   (`hooks.py:126-154`, `modify_hp_lost` + `after_modify_hp_lost` — the pair
   `power_cmd` G4 says the power-amount family lacks). So it is the natural test
   of whether the sim's one correct two-phase implementation is used correctly.
   It also declares `GetScaledAmountForMultiplayer` (waiver).
2. **`vigor`** — the second of the only two units that use
   `before_attack`/`after_attack` (see section 4 item 15) and the reader of
   `prep_time`'s and `akabeko`'s grants. `ModifyDamageAdditive` only, so no G9
   exposure.
3. **`free_attack`** — `TryModifyEnergyCostInCombatLate`, i.e. the **Late** half
   of the pair whose Early half is `curious`. `hook_dispatch` G3's live witness
   is *literally this pair* (Tangled early vs Free Attack late), so the rule-3
   obligation is to reach the same verdict from this end. Also declares
   `BeforeCardPlayed`.
4. **`fasten`** — `ModifyBlockAdditive` + `AfterModifyingBlockAmount`, the block
   analogue of `buffer`'s pair; expect the same missing-notification-list shape
   as `power_cmd` G4 and `curious`'s `TryModify` guard.
5. **`juggernaut`** and **`block_next_turn`** — `AfterBlockGained` and
   `AfterBlockCleared`. `juggernaut` is already cited by `power/thorns` as the
   reachable route to unpowered non-card damage, so its `props` argument matters.
   `block_next_turn` shares `toric_toughness`'s hook and should agree with it.
6. **`calamity`** — `BeforeCardPlayed` + `AfterCardPlayed`, i.e. squarely inside
   `hook_dispatch` G4's per-`CardPlay` bracket; and its C# generator is
   `CardFactory.GetForCombat` (the *with*-replacement sibling of the call
   `hello_world` gets wrong), so check the RNG accessor per section 7 item 11.
7. **`vicious`** — `AfterPowerAmountChanged`, the one half-A unit that listens to
   the power pipeline itself; cross-reference `power_cmd` steps 23 and 33.
8. **`stratagem`** (`AfterShuffle`), **`retain_hand`** (`ShouldFlush` +
   `AfterSideTurnEnd`), **`improvement`** (`AfterCombatEnd`) — lower yield;
   `retain_hand`'s `ShouldFlush` is `turn_structure` territory and its
   `AfterSideTurnEnd` is the already-settled enemy-side slot.

**No fourth non-dyadic multiplicative factor has been found in half A.** Batch 2
checked four more factors against the census and all four are dyadic:
`no_block` ×0.0, `unmovable` ×2.0, `diamond_diadem` ×0.5, `gigantification` ×3.
Only `fasten` (additive) and `buffer` (HP-loss) remain in half A that touch a
modifier family at all, so **half A is unlikely to widen `hook_dispatch` G9**.
