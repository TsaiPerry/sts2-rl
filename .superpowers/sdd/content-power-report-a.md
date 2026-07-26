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
| half-A units audited | 15 / 41 |
| power units audited overall | 60 / 134 (`py tools/audit_status.py --kind power`) |
| suite | 2476 passed / 31 xfailed at every batch boundary |
| commits | batch 1: see below |

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

## 10. Residual queue — the 26 half-A units left

`automation, battleworn_dummy_time_limit, block_next_turn, buffer, calamity,
confused, curious, diamond_diadem, fasten, free_attack, gigantification,
improvement, juggernaut, mayhem, no_block, nostalgia, plating, retain_hand,
stampede, stratagem, the_bomb, the_gambit, toric_toughness, unmovable, vicious,
vigor`

Ordered by expected yield, with what is already known:

1. **`mayhem` and `stampede`** — the two units section 4 item 1 and item 2 are
   *about*. Both are cheap now (the C# and the witnesses are already read and
   executed) and both must cross-reference `turn_structure` G8.
2. **`nostalgia`** — the `ModifyCardPlayResultPileTypeAndPosition` tuple-return
   override the harness misses (main report section 8 item 2). It is the *other*
   side of `corruption`'s and `rebound`'s already-recorded contention, so the
   rule-3 obligation is to reach the same verdict from its end.
3. **`plating`** — the widest override list in half A (8) and the one unit in
   half A that the `slots` census flags as touching *other* creatures' state
   from an enemy-side per-creature slot, i.e. part of the main report's section-6
   disagreement with `turn_structure` G5. `asleep` (half B) removes Plating.
4. **`battleworn_dummy_time_limit`** — the prompt's section-6 note says all
   three G5 cases are in half B; **that is wrong, this one is in half A.** It
   escapes its owner in an enemy-side slot, and the Battle Friend encounter
   fields more than one dummy, so the two-dummy witness the main report asks for
   is half A's to execute.
5. **The `InstanceType` units** — `automation`, `the_bomb`, `toric_toughness`
   (`rolling_boulder` done). `power_cmd` G5 owns the mechanism; per-unit is
   whether two instances are reachable, and `rolling_boulder` shows that
   question is worth asking properly.
6. **The `on_stack`-no-op units in half A** — `confused`, `curious`,
   `the_gambit`. One grep each ("does anything read `Amount`").
7. **The block/damage-modifier units** — `buffer`, `diamond_diadem`, `fasten`,
   `gigantification`, `no_block`, `unmovable`, `vigor`, `juggernaut`,
   `block_next_turn`, `toric_toughness`. Expect the `props` omission (main
   report's proposed bug class 1) and `hook_dispatch` G9 cross-references;
   `no_block` (×0.0), `unmovable` (×2.0), `diamond_diadem` (×0.5) and
   `gigantification` (×3) are all already confirmed **dyadic** by the
   `multipliers` census, so none of them widens G9.
8. **The rest** — `calamity`, `free_attack`, `improvement`, `retain_hand`,
   `stratagem`, `vicious`.

**No fourth non-dyadic multiplicative factor has been found in half A so far.**
