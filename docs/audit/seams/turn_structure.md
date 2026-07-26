# Engine seam: `turn_structure`

Audited 2026-07-25 (Task 8 of the six seam audits, Tier 2 of the
source-audit-pipeline design). Verdicts and rationale live in
`audits/seam/turn_structure.json`; this file is the durable ordering spec
extracted from the C# source that the JSON record judges the sim against.

This seam is the **combat turn loop**: combat start, the player-turn setup
(block clear → energy → hand draw), the two-phase player turn end (turn-end
hooks → ethereal/turn-end-in-hand cards → hand flush → `AfterTurnEnd`), the
side switch and extra turns, the enemy side (per-enemy moves → side end →
Vulnerable/Weak/Frail duration tick), and the win/loss check.

## Source correction (Step A)

`tools/audit/harness.py`'s `SEAM_SOURCES["turn_structure"]` listed
`src/Core/Combat/CombatManager.cs` + `src/Core/Combat/PlayerTurnPhase.cs` on
the game side and `sts2_rl/combat.py` + `sts2_rl/player.py` on the sim side.
`CombatManager.cs` is the right primary file, but **`PlayerTurnPhase.cs` is a
bare 61-line `enum` with no logic at all** (it is kept, because it is the
normative statement of the six turn phases this record's steps 10/26/47 are
about), and **every other file the ordering spec rests on was missing**. Both
lists were widened; the edit is staged in this branch and the record's hashes
were regenerated from it (`py tools/audit_status.py` → not stale).

Added on the game side:

- **`src/Core/Combat/CombatState.cs`** — `CurrentSide` (110), `RoundNumber`
  (102), `CreaturesOnCurrentSide` (133), `Enemies` (65), `HittableEnemies`
  (142), `IsLiveCombat` (608-611). Every `StartTurn` / `SwitchSides` branch
  reads these; steps 7, 29, 66 and guard **G10** cite them.
- **`src/Core/Entities/Creatures/Creature.cs`** — the per-creature turn verbs
  `CombatManager` calls out to: `BeforeTurnStart` (673-679), `AfterTurnStart`
  (681-692, which is where the **turn-1 player block-clear skip** lives),
  `ClearBlock` (718-728), `OnSideSwitch` (694-704), `TakeTurn` (706-716),
  `PrepareForNextTurn` (546-554), `IsPrimaryEnemy`/`IsSecondaryEnemy`
  (252-277). Primary evidence for steps 8, 11, 12, 13, 32, 67, 69 and gaps
  **G1**, **G6**, **G9**. Split by method against `creature_card_cmds` — see
  the scope-boundary section below.
- **`src/Core/Entities/Players/PlayerCombatState.cs`** — `TurnNumber` (37),
  `IncrementTurnNumber` (157-160), `ResetEnergy` (162-165),
  `AddMaxEnergyToCurrent` (167-170), `MaxEnergy` (101), `EndOfTurnCleanup`
  (268-274), `Phase` (44). Steps 17, 38, 63, 66; gap **G7**.
- **`src/Core/Models/CardModel.cs`** — `HasTurnEndInHandEffect` (1043),
  `OnTurnEndInHandWrapper` (1682-1698) and the per-turn card reset
  `EndOfTurnCleanup` (1610-1623). Steps 38, 52, 54; gap **G7**. No other seam
  lists this file.
- **`src/Core/Models/MonsterModel.cs`** — `SetUpForCombat`/`SpawnedThisTurn`
  (409-413, 247), `RollMove` (415-418), `PerformMove` (434-453),
  `OnSideSwitch` (479-483). Steps 11, 32, 33, 67; gap **G9**. Move
  *selection* is Task 10's — see the boundary section.
- **`src/Core/Hooks/Hook.cs`** — the turn dispatchers themselves. This record
  claims 24 of them by name (listed in the boundary section); the two whose
  internal phase structure the spec depends on are `BeforeTurnEnd`
  (1238-1261: `BeforeSideTurnEndVeryEarly` → `BeforeSideTurnEndEarly` →
  `BeforeSideTurnEnd`) and `AfterTurnEnd` (1265-1291: `AfterSideTurnEnd`,
  awaited, then `AfterSideTurnEndLate`). `AfterBlockCleared` (119-125) is
  **G1**'s primary evidence and `AfterPreventingBlockClear` (1032-1038) is
  **G2**'s. The three prior seams already list `Hook.cs`.
- **`src/Core/Commands/PowerCmd.cs`** — `TickDownDuration` (190-200), the verb
  the seed fact's V/W/F tick runs through (step 40). `power_cmd` (Task 6) owns
  the **set** site of `SkipNextDurationTick` (`PowerCmd.cs:146`, its step 20);
  this record owns the **consume** site only.
- **`src/Core/Models/Powers/WeakPower.cs`** (48-53),
  **`VulnerablePower.cs`** (59-64), **`FrailPower.cs`** (35-40) — the three
  `AfterSideTurnEnd` overrides whose `side == CombatSide.Enemy` guard is what
  makes the duration tick an *enemy-side-end* event, i.e. exactly what the
  sim's `on_enemy_side_end` maps to. Step 39 rests on them.
- **`src/Core/Models/Relics/SturdyClamp.cs`** (22-46),
  **`HornCleat.cs`** (20-27), **`CaptainsWheel.cs`** (20-27),
  **`Anchor.cs`** (19-23) — the load-bearing witnesses for **G1**/**G2**/
  **G6**: one ported `ShouldClearBlock` preventer, two ported
  `AfterBlockCleared` listeners, and the ported relic whose real hook is
  `BeforeCombatStart` (which is why **G6** matters). Cited with line numbers,
  so they are pinned. *Fake Anchor is the same shape as Anchor and is named
  only, not separately cited.*
- **`src/Core/Models/Relics/PaelsEye.cs`** (108-137) and
  **`RunicPyramid.cs`** (10-17) — the ported `ShouldTakeExtraTurn` and
  `ShouldFlush` implementations that make **G3** and **G4** live.

Added on the sim side (`combat.py` + `player.py` cover under half of it):

- **`sts2_rl/hooks.py`** — the sim's turn dispatchers (`on_player_turn_start`
  279-283, `on_player_turn_started` 285-295, `on_player_turn_end` 297-301,
  `after_player_turn_end` 303-310, `on_enemy_turn_start` 326-330,
  `on_enemy_turn_end` 332-336, `on_enemy_side_end` 338-342,
  `should_clear_block` 613-619, `should_reset_energy` 621-629,
  `should_flush_hand` 644-652, `should_take_extra_turn` 662-671,
  `should_ethereal_trigger` 696-702), and the **absence** of
  `after_preventing_block_clear`, `after_flush`, `before_flush`,
  `should_stop_combat_from_ending` and any auto-pre/post-play hook, which is
  what **G2**, **G4**, **G8** and **G10** rest on.
- **`sts2_rl/creatures.py`** — `is_gone` (43-46) and `retained_after_death`
  (31), the win-condition and enemy-loop inputs (steps 31, 69; **G10**).
- **`sts2_rl/monsters/base.py`** — `take_turn` (93-94) and
  `telegraph_next_move` (96-105), the sim's counterpart to `Creature.TakeTurn`
  and to `PrepareForNextTurn`'s roll (**G9**).
- **`sts2_rl/powers.py`** — `Power._tick_duration` (77-84, the port of
  `PowerCmd.TickDownDuration`) and the three `on_enemy_side_end` tick sites
  (419-420, 441-442, 462-463); step 39/40.
- **`sts2_rl/cards/base.py`** — `reset_turn_cost_modifiers` (265-269), the
  sim's only per-turn card-state reset (**G7**).
- **`sts2_rl/relics/sturdy_clamp.py`**, **`horn_cleat.py`**,
  **`captains_wheel.py`**, **`anchor.py`**, **`paels_eye.py`**,
  **`runic_pyramid.py`** — the sim halves of the four live gaps, each cited
  with line numbers.

### Scope boundary — READ BEFORE TASK 9 (`hook_dispatch`) AND TASK 10 (`monster_state_machine`)

**`src/Core/Hooks/Hook.cs`** is now listed under four seams and is split by
**method**. `damage_pipeline` owns the damage modifiers; `power_cmd` owns the
six power-amount dispatchers; `creature_card_cmds` owns the four block
dispatchers (`BeforeBlockGained`, `AfterBlockGained`,
`AfterModifyingBlockAmount`, `ModifyBlock`). **This record claims the 24
turn-lifecycle dispatchers below, and Task 9 must not re-audit them** — a
turn-dispatcher finding belongs here as an amendment to
`audits/seam/turn_structure.json`:

`AfterBlockCleared` (119-125), `BeforeCombatStart` (311-324), `AfterCombatEnd`
(328-336), `AfterCombatVictory` (340-348), `AfterEnergyReset` (503-509),
`BeforeFlush` (532-538), `AfterFlush` (560-570), `BeforeHandDraw` (588-601),
`AfterHandEmptied` (611-621), `AfterModifyingHandDraw` (739-745),
`AfterPlayerTurnStart` (882-895), `AfterAutoPostPlayPhaseEntered` (910-920),
`AfterAutoPrePlayPhaseEntered` (928-938), `AfterPreventingBlockClear`
(1032-1038), `BeforeSideTurnStart` (1144-1159), `AfterSideTurnStart`
(1163-1175), `AfterTakingExtraTurn` (1220-1226), `BeforeTurnEnd` (1238-1261),
`AfterTurnEnd` (1265-1291), `ModifyHandDraw` (1684-1700), `ModifyMaxEnergy`
(1770-1782), `ShouldClearBlock` (2193-2204), `ShouldEtherealTrigger`
(2286-2296), `ShouldFlush` (2301-2311), `ShouldPlayerResetEnergy` (2378-2388),
`ShouldStopCombatFromEnding` (2442-2452), `ShouldTakeExtraTurn` (2457-2467).

Task 9 keeps `AbstractModel.cs` in full and the generic listener-iteration
machinery (`IterateCombatHookListeners` and friends). **The *shape* of a
dispatcher's listener walk is Task 9's; the *place in the turn* it is called
from is this record's.** Where this record says a dispatcher runs sub-phases
in a fixed order (`BeforeTurnEnd`'s three, `AfterTurnEnd`'s two,
`AfterSideTurnStart`'s two), that ordering claim is this record's because the
turn depends on it; the per-listener pause/choice-context plumbing inside the
same loop is Task 9's.

**`src/Core/Entities/Creatures/Creature.cs`** is shared with
`creature_card_cmds` (Task 7), which owns the `*Internal` mutators
(`GainBlockInternal`/`LoseBlockInternal` 459-491, `HealInternal`/
`SetCurrentHpInternal`/`SetMaxHpInternal` 477-501, `StunInternal` 524-542,
`RemoveAllPowersInternalExcept` 658-666). **This record owns the turn verbs
only**: `IsPrimaryEnemy`/`IsSecondaryEnemy` (252-277), `PrepareForNextTurn`
(546-554), `BeforeTurnStart` (673-679), `AfterTurnStart` (681-692),
`OnSideSwitch` (694-704), `TakeTurn` (706-716), `ClearBlock` (718-728).

**`src/Core/Commands/PowerCmd.cs`** is shared with `power_cmd` (Task 6), which
owns the whole file except **`TickDownDuration` (190-200)**, which is this
record's step 40. The `SkipNextDurationTick` **set** site (`PowerCmd.cs:146`)
stays Task 6's (its step 20, already a pinned gap); the **consume** site is
here. The two must stay consistent: Task 6's gap is that the sim re-arms the
flag on re-stacking, and this record's step 40 is that the consume half is
otherwise faithful.

**`src/Core/Models/MonsterModel.cs`** is shared with Task 10
(`monster_state_machine`). **This record owns the turn-loop call sites**:
`SetUpForCombat`/`SpawnedThisTurn` (409-413), the *placement* of `RollMove`
(415-418) at `Creature.PrepareForNextTurn` and at `AfterCreatureAdded`,
`PerformMove`'s turn-scoped bracket (434-453) and `OnSideSwitch` (479-483).
**Task 10 owns everything inside the state machine** — what `RollMove`
returns, `MoveStateMachine.OnMovePerformed`, `MoveState`/`RandomBranchState`
semantics, and `ForceCurrentState`/`SetMoveImmediate`. Gap **G9** below is
about *when* the roll happens, not *what* it rolls; if Task 10 finds the sim's
roll produces the wrong move, that is Task 10's finding, and it should
cross-reference **G9** rather than re-verdict it.

**`sts2_rl/combat.py`** is shared with `creature_card_cmds` (Task 7), whose
boundary section already assigns the split. Honouring it: **this record owns**
`_all_enemies_dead` (272-277), `_execute_enemy_turn` (279-284),
`_run_enemy_turns` (286-345), `_end_combat` (347-350),
`_process_turn_end_cards` (352-375), `end_turn` (639-685), `valid_actions`
(687-704), `is_over` (706-708), `play_card`'s phase/energy gate (390-413) and
its trailing combat-end checks (417-421), and `__init__`'s combat-start
sequence (208-209). Task 7 owns `auto_play` (424-439), `auto_play_card`
(516-558), `select_cards` (560-581) and the pile/limbo bookkeeping inside
`_resolve_card_play`.

**`sts2_rl/player.py`** is shared the same way: **this record owns
`start_turn` (151-186)**; Task 7 owns the pile verbs, including `discard_hand`
(188-197) and `_draw` (276-292). `start_turn`'s *call* to `_draw` and
`end_turn`'s *call* to `discard_hand` are this record's; their bodies are
Task 7's. Where a finding here is about the call being skipped entirely
(**G4**), it is this record's; where it is about what the callee does with the
cards (Task 7's **G11**, `on_card_discarded` firing before the move), it is
not re-verdicted here.

## Seed facts, verified

1. **`end_turn` order: player turn-end hooks → in-hand turn-end effects
   (ethereal, Burn) → discard hand → per-enemy turns (block clear →
   on_enemy_turn_start → move/stun-skip → on_enemy_turn_end) →
   on_enemy_side_end (V/W/F tick) → player turn (block clear → energy →
   on_player_turn_start → draw).** Verified by execution as the sim's actual
   order (see the pin `test_end_turn_hook_sequence`), and verified against the
   source as the sim's *intended* mapping. The C# order it maps to is
   steps 42-74 + 5-29 below, and it differs in five places, each recorded:
   the extra-turn check happens first in the sim and last in C# (**G3**), the
   hand flush is conditional in the sim and its two tail hooks unconditional
   in C# (**G4**), the enemy side is per-enemy in the sim and per-side in C#
   (**G5**), `EndOfTurnCleanup` has no sim counterpart at either of its two
   C# sites (**G7**), and the auto-pre/post-play phases do not exist in the
   sim (**G8**).
2. **`CheckWinCondition` runs after the player's turn SETUP; player
   `AfterTurnEnd` fires after the hand flush (Parrying Shield).** Confirmed:
   `CombatManager.cs:573` puts `await CheckWinCondition()` after
   `SetupPlayerTurn` *and* after `RunAutoPrePlayPhase`, before the play phase
   opens (step 27); and `CombatManager.cs:1307` fires
   `Hook.AfterTurnEnd(state, Player, participants)` inside
   `EndPlayerTurnPhaseTwoInternal`, i.e. **after** every player's
   `FlushPlayerHand` has completed (step 64). The sim mirrors both:
   `combat.py:681-685` and `combat.py:665` respectively, and
   `relics/parrying_shield.py:24` is the ported `after_player_turn_end`
   listener that depends on it.
3. **Combat ends when the player is dead or every non-minion enemy is
   dead/escaped.** Confirmed but incomplete: `CombatManager.IsEnding`
   (180-202) is `IsInProgress && (pendingLoss || (no living
   `IsPrimaryEnemy`) && !Hook.ShouldStopCombatFromEnding(state))`.
   `IsPrimaryEnemy` is "on the enemy side and holding no power with
   `OwnerIsSecondaryEnemy`" (`Creature.cs:252-277`), and a full-source grep
   shows **`MinionPower` is the only power that sets it** — so the sim's
   `"minion" not in e.powers` test (`combat.py:276`) is exactly right, and
   `IllusionPower` is *not* a secondary-enemy marker despite reviving its
   owner. The two pieces the sim has no counterpart for are
   `Hook.ShouldStopCombatFromEnding` and the pending-loss two-step; see
   **G10**.

## Numbered ordering spec

### Combat start — `CombatManager.SetUpCombat` / `StartCombatInternal`

1. `SetUpCombat`: throw if a combat is already set up; `IsStarting = true`;
   `MultiplayerScalingModel?.OnCombatEntered`; clear `_playersTakingExtraTurn`;
   per player `ResetCombatState()` then
   `PopulateCombatState(RunState.Rng.Shuffle, state)` (the initial draw-pile
   randomize); `NetCombatCardDb.StartCombat`; per creature `AddCreature`;
   `CombatSetUp` event. `CombatManager.cs:350-378`.
2. `StartCombatInternal`: per creature `AfterCreatureAdded` →
   `creature.AfterAddedToRoom()`, and `if (IsEnemy && CurrentSide == Player)
   Monster.RollMove(players)` — every enemy's **first** intent is rolled here,
   while `IsInProgress` is still false. `CombatManager.cs:394-398, 860-867`.
3. `IsInProgress = true; IsStarting = false;` then
   `Hook.BeforeCombatStart(runState, state)` — combat is already "in progress"
   when it fires, and it fires **before** `StartTurn`.
   `CombatManager.cs:399-403`; `Hook.cs:311-324`.
4. Banner/FTUE/wait, then `await StartTurn()`. `CombatManager.cs:406-419`.

### `CombatManager.StartTurn` — `CombatManager.cs:422-605`

5. Guard `!IsInProgress` → return. `CombatManager.cs:424-427`.
6. `SetPhaseForAllPlayers(PlayerTurnPhase.None)` — every player's phase is
   None for the whole of the enemy turn and for the first part of their own.
   `CombatManager.cs:429`; `PlayerTurnPhase.cs:11`.
7. Participants: `isExtraPlayerTurn = _playersTakingExtraTurn.Count > 0`; on a
   player-side extra turn only those players participate, otherwise
   `CreaturesOnCurrentSide` (and `playersStartingTurn` is empty on the enemy
   side). `CombatManager.cs:430-448`; `CombatState.cs:133`.
8. Per participant: `creature.BeforeTurnStart(side)` → for every power,
   `AmountOnTurnStart = Amount` — a snapshot taken **before** anything else
   in the turn. `CombatManager.cs:449-455`; `Creature.cs:673-679`.
9. `Hook.BeforeSideTurnStart(state, side, participants)`.
   `CombatManager.cs:456-460`; `Hook.cs:1144-1159`.
10. Player side only: `SetPhaseForAllPlayers(Start)`,
    `PlayerActionsDisabled = false`, clear `_playersReadyToEndTurn` and
    `_playersReadyToBeginEnemyTurn`, `_inPlayerTurnSetup = true`,
    `_deferredEndTurnTransition = null`; turn banner.
    `CombatManager.cs:461-477`.
11. Player side and `!isExtraPlayerTurn` only: `foreach (enemy in
    _state.Enemies) enemy.PrepareForNextTurn(_state.PlayerCreatures)` →
    `Monster.RollMove(targets)`. **Every enemy's next move is rolled at the
    start of the PLAYER's turn, unconditionally** — including an enemy that
    was stunned and skipped its move, and including one that has just spawned.
    An extra player turn skips the roll entirely. `CombatManager.cs:478-484`;
    `Creature.cs:546-554`; `MonsterModel.cs:415-418`. See **G9**.
12. Per participant: `await creature.AfterTurnStart(side)` → `ClearBlock()`,
    **except** a player whose `PlayerCombatState.TurnNumber == 1`, which
    returns before clearing anything. `CombatManager.cs:492-499`;
    `Creature.cs:681-692`. See **G6**.
13. `ClearBlock`: `if (Hook.ShouldClearBlock(CombatState, this, out preventer))
    Block = 0; else await Hook.AfterPreventingBlockClear(CombatState,
    preventer, this)`. `Creature.cs:718-728`; `Hook.cs:2193-2204, 1032-1038`.
    See **G2**.
14. A **second, separate loop** over the same participants:
    `await Hook.AfterBlockCleared(state, creature)` — **unconditional**. It
    fires for a creature that had no block, for a creature whose clear was
    *prevented*, and for a player on turn 1 whose `AfterTurnStart` returned
    early. `CombatManager.cs:500-507`; `Hook.cs:119-125`. See **G1**.
15. Per player participant: `SetupPlayerTurn(player, choiceContext)` (steps
    16-22), each awaited to its pause-or-completion point.
    `CombatManager.cs:508-519`.
16. `SetupPlayerTurn` guards: `player.Creature.IsDead` → return; null combat
    state → warn and return. `CombatManager.cs:629-639`.
17. `if (Hook.ShouldPlayerResetEnergy(state, player)) ResetEnergy()` (i.e.
    `Energy = MaxEnergy`) `else AddMaxEnergyToCurrent()` (`Energy +=
    MaxEnergy`). `MaxEnergy` is itself `Hook.ModifyMaxEnergy(state, player,
    player.MaxEnergy)`. `CombatManager.cs:641-649`;
    `PlayerCombatState.cs:101, 162-170`; `Hook.cs:2378-2388, 1770-1782`.
18. `await Hook.AfterEnergyReset(state, player)`. `CombatManager.cs:650`;
    `Hook.cs:503-509`.
19. `await Hook.BeforeHandDraw(state, player, choiceContext)`.
    `CombatManager.cs:652`; `Hook.cs:588-601`.
20. `handDraw = Hook.ModifyHandDraw(state, player, 5m, out modifiers)` then
    `await Hook.AfterModifyingHandDraw(state, modifiers)`. The base is the
    const `baseHandDrawCount = 5` (`CombatManager.cs:40`).
    `CombatManager.cs:654-655`; `Hook.cs:1684-1700, 739-745`.
21. **Turn 1 only**: first move every card whose enchantment sets
    `ShouldStartAtBottomOfDrawPile` to the **bottom** (`MoveToBottomInternal`),
    then move every `Innate` card *not already moved* to the **top**
    (`MoveToTopInternal`); `handDraw = min(max(handDraw, innateCount),
    CardPile.MaxCardsInHand)`. `CombatManager.cs:657-672`.
22. `await CardPileCmd.Draw(choiceContext, handDraw, player, fromHandDraw:
    true)` then `await Hook.AfterPlayerTurnStart(state, choiceContext,
    player)`. `CombatManager.cs:673-675`; `Hook.cs:882-895`.
23. `await Hook.AfterSideTurnStart(state, side, participants)` — every
    listener's `AfterSideTurnStart`, then a **second** full pass of every
    listener's `AfterSideTurnStartLate`. Fires for **both** sides, and on the
    player side only after every player's `SetupPlayerTurn` has finished.
    `CombatManager.cs:520-524`; `Hook.cs:1163-1175`.
24. Player side: per player, `PlayerCombatState.OrbQueue.AfterTurnStart(ctx)`.
    `CombatManager.cs:526-537`. Waiver — orbs are the Defect's.
25. Player side: every dead player and every player *not* in
    `playersStartingTurn` is auto-`SetReadyToEndTurn(canBackOut: false)`; if
    that makes everyone ready, release the deferred transition and return.
    `CombatManager.cs:543-555`. Waiver — multiplayer/extra-turn bookkeeping.
26. Player side: per player, `RunAutoPrePlayPhase(ctx, setupTask, player)` —
    await the player's setup task, `Phase = AutoPrePlay`,
    `Hook.AfterAutoPrePlayPhaseEntered`, `Phase = Play`. This is strictly
    **after** step 23 and step 24, so start-of-turn auto-plays (Whispering
    Earring, Imbued, History Course) run after every turn-start relic and
    power. `CombatManager.cs:556-572, 613-619`; `Hook.cs:928-938`. See **G8**.
27. `await CheckWinCondition()` — **after the player's turn setup and the
    auto-pre-play phase**, before the play phase opens (seed fact 2).
    `CombatManager.cs:573`.
28. If still `IsInProgress`: unpause the action executor, set the queue to
    `PlayPhase`, `IsEnemyTurnStarted = false`, `_inPlayerTurnSetup = false`,
    fire `TurnStarted`; then `ReleaseDeferredEndTurnTransitionIfNeeded()`.
    `CombatManager.cs:575-586`. See **N1**.
29. Enemy-side branch: `IsEnemyTurnStarted = true`, `TurnStarted`, checksum,
    `WaitForUnpause`, `CheckWinCondition`, then `if (IsInProgress) await
    ExecuteEnemyTurn(actionDuringEnemyTurn)`. `CombatManager.cs:588-604`.

### `CombatManager.ExecuteEnemyTurn` — `CombatManager.cs:1061-1093`

30. Guard `!IsInProgress` → return; optional test hook
    `actionDuringEnemyTurn()`. `CombatManager.cs:1063-1071`.
31. Iterate a **snapshot** of `_state.Enemies.ToList()`, skipping any creature
    the state no longer contains — so a monster spawned or removed during the
    enemy side does not change this turn's participant list.
    `CombatManager.cs:1072-1074`.
32. Per enemy: intent animation, then `await enemy.TakeTurn()` — which throws
    unless the creature is a monster on the enemy side, and runs
    `Monster.PerformMove()` **only if `!Monster.SpawnedThisTurn`**. There is
    **no `IsDead` guard**: a corpse the combat retained still takes its turn.
    `CombatManager.cs:1076-1081`; `Creature.cs:706-716`.
33. `PerformMove`: scaled wait → `IsPerformingMove = true` → `move =
    NextMove` → `move.PerformMove(combatState.PlayerCreatures)` →
    `MoveStateMachine.OnMovePerformed(move)` (Task 10) → history →
    `IsPerformingMove = false` → if the monster is now dead and
    `Hook.ShouldCreatureBeRemovedFromCombatAfterDeath` →
    `combatState.RemoveCreature`. `MonsterModel.cs:434-453`.
34. Per enemy, after its move: `WaitForUnpause`, `await CheckWinCondition()`,
    `if (!IsInProgress) return`. `CombatManager.cs:1082-1088`.
35. After the loop: checksum, then `await EndEnemyTurn()`.
    `CombatManager.cs:1091-1092`.

### `CombatManager.EndEnemyTurn` / `EndEnemyTurnInternal` — `CombatManager.cs:817-839, 1248-1257`

36. Guard `IsInProgress`; **throw** if `CurrentSide != Enemy`; `WaitForUnpause`.
    `CombatManager.cs:819-827`.
37. `EndEnemyTurnInternal`: `await Hook.BeforeTurnEnd(state, Enemy,
    CreaturesOnCurrentSide)` — three complete listener passes in order:
    `BeforeSideTurnEndVeryEarly`, then `BeforeSideTurnEndEarly`, then
    `BeforeSideTurnEnd`, with all the resulting tasks awaited together at the
    end. `CombatManager.cs:1250-1251`; `Hook.cs:1238-1261`. See **G11**.
38. `foreach (player in _state.Players) PlayerCombatState.EndOfTurnCleanup()`
    — per card in **every** pile: `ExhaustOnNextPlay = false`,
    `HasSingleTurnRetain = false`, `HasSingleTurnSly = false`, drop every
    local energy-cost modifier flagged `EndOfTurn` and every temporary star
    cost flagged `ClearsWhenTurnEnds`. `CombatManager.cs:1252-1255`;
    `PlayerCombatState.cs:268-274`; `CardModel.cs:1610-1623`. See **G7**.
39. `await Hook.AfterTurnEnd(state, Enemy, enemies)` — every listener's
    `AfterSideTurnEnd` (awaited as a group), **then** every listener's
    `AfterSideTurnEndLate`. **This is where Vulnerable, Weak and Frail tick
    down**: each overrides `AfterSideTurnEnd` and calls
    `PowerCmd.TickDownDuration(this)` when `side == CombatSide.Enemy`.
    `CombatManager.cs:1256`; `Hook.cs:1265-1291`; `WeakPower.cs:48-53`,
    `VulnerablePower.cs:59-64`, `FrailPower.cs:35-40`.
40. `PowerCmd.TickDownDuration(power)`: `if (power.SkipNextDurationTick)
    { SkipNextDurationTick = false; }` else `await Decrement(power)` =
    `ModifyAmount(..., -1m, ...)`. `PowerCmd.cs:190-200`.
41. Back in `EndEnemyTurn`: `await CheckWinCondition()`; then `if (!IsEnding)
    { SwitchSides(); WaitForUnpause(); await StartTurn(); }`.
    `CombatManager.cs:830-837`.

### The player's end of turn, phase one — `CombatManager.cs:684-735, 1101-1116, 1143-1209`

42. `SetReadyToEndTurn(player, canBackOut, actionDuringEnemyTurn)`:
    idempotent per player; fires `PlayerEndedTurn`; returns immediately unless
    `AllPlayersReadyToEndTurn()`. `CombatManager.cs:684-698`.
43. Choose the transition: if a **player-driven** action is currently running,
    wait for it first (`WaitForActionThenEndTurn`), else run
    `AfterAllPlayersReadyToEndTurn` directly. If `_inPlayerTurnSetup` is true,
    the whole transition is **deferred** into `_deferredEndTurnTransition` and
    released at every exit of `StartTurn`. `CombatManager.cs:699-714,
    722-735, 1095-1099`. See **N1**.
44. `AfterAllPlayersReadyToEndTurn`: guard `IsInProgress`;
    `EndingPlayerTurnPhaseOne = true`; drain the queue
    (`WaitUntilQueueIsEmptyOrWaitingOnNonPlayerDrivenAction`); run
    `EndPlayerTurnPhaseOneInternal()`; enqueue `ReadyToBeginEnemyTurnAction`;
    `EndingPlayerTurnPhaseOne = false`. `CombatManager.cs:1101-1116`.
45. `EndPlayerTurnPhaseOneInternal` guards: null state → return; **throw** if
    `CurrentSide != Player`; `WaitForUnpause`.
    `CombatManager.cs:1145-1154`.
46. Participants: the extra-turn players if any, else every player.
    `CombatManager.cs:1155-1159`.
47. Per player: `Phase = AutoPostPlay`, then
    `Hook.AfterAutoPostPlayPhaseEntered(ctx, state, player)`; in a **second**
    pass, await each context and set `Phase = End`.
    `CombatManager.cs:1160-1176`; `Hook.cs:910-920`. See **G8**.
48. `await Hook.BeforeTurnEnd(state, Player, participants)` — the same
    three-pass dispatcher as step 37. `CombatManager.cs:1177-1180`.
49. `if (await CheckWinCondition()) return` — a turn-end effect that ends the
    fight aborts the rest of the pipeline. `CombatManager.cs:1181-1184`.
50. Per player: `DoTurnEnd(player, ctx)` (steps 51-54), each on its own choice
    context; then await all of them. `CombatManager.cs:1185-1199`.
51. `DoTurnEnd`: `await OrbQueue.BeforeTurnEnd(ctx)`; `if (IsOverOrEnding)
    return`. `CombatManager.cs:1216-1222`.
52. Partition the hand **in pile order** into two lists: a card with
    `HasTurnEndInHandEffect` → `turnEndCards`; **else if**
    `Keywords.Contains(Ethereal) && Hook.ShouldEtherealTrigger(state, card)`
    → the ethereal list. A card with *both* goes into `turnEndCards` only.
    `CombatManager.cs:1223-1237`; `CardModel.cs:1043`; `Hook.cs:2286-2296`.
53. Exhaust **every** ethereal card first, in order, via
    `CardCmd.Exhaust(ctx, card, causedByEthereal: true)` — the whole ethereal
    pass completes before any turn-end effect runs.
    `CombatManager.cs:1238-1241`.
54. Then, per turn-end card, `OnTurnEndInHandWrapper(ctx)`:
    `CardPileCmd.Add(this, PileType.Play)` (the card sits in the **Play** pile
    for the whole effect) → wait → `OnTurnEndInHand(ctx)` → if `Ethereal`
    `CardCmd.Exhaust(ctx, this, causedByEthereal: true)` **else**
    `CardPileCmd.Add(this, Discard)`. The wrapper does **not** re-consult
    `ShouldEtherealTrigger`. `CombatManager.cs:1242-1245`;
    `CardModel.cs:1682-1698`.
55. Per player: `await Hook.BeforeFlush(state, player)`.
    `CombatManager.cs:1200-1206`; `Hook.cs:532-538`.
56. Checksum, then `await CheckWinCondition()`. `CombatManager.cs:1207-1208`.

### The player's end of turn, phase two — `CombatManager.cs:1259-1347`

57. `AfterAllPlayersReadyToBeginEnemyTurn`: guard `IsInProgress`;
    `EndingPlayerTurnPhaseTwo = true`; queue → `NotPlayPhase`;
    `AboutToSwitchToEnemyTurn` event; `await Task.Yield()`;
    `EndPlayerTurnPhaseTwoInternal()`; `SwitchFromPlayerToEnemySide()`.
    `CombatManager.cs:1259-1272`.
58. `EndPlayerTurnPhaseTwoInternal`: **throw** if `CurrentSide != Player`;
    participants as in step 46. `CombatManager.cs:1279-1289`.
59. Per player: `FlushPlayerHand(player, ctx)` (steps 60-63); then await all.
    `CombatManager.cs:1290-1304`.
60. `FlushPlayerHand` guards: `player.Creature.IsDead` → return; null state →
    warn and return. `CombatManager.cs:1313-1323`.
61. `flag = Hook.ShouldFlush(state, player)`; per card **in hand order**:
    `!flag || card.ShouldRetainThisTurn` → `cardsToRetain`, else
    `cardsToFlush`. A false `ShouldFlush` retains the **whole** hand.
    `CombatManager.cs:1327-1338`; `Hook.cs:2301-2311`.
62. `if (cardsToFlush.Count > 0) await CardPileCmd.Add(cardsToFlush,
    PileType.Discard)` — one batched `Add` for the whole flush (its per-card
    semantics are `creature_card_cmds`'). `CombatManager.cs:1339-1343`.
63. `await Hook.AfterFlush(state, player, ctx, cardsToFlush, cardsToRetain)`
    — **unconditional**, fired even when nothing was flushed — then
    `PlayerCombatState.EndOfTurnCleanup()`, also unconditional and the
    **second** of its two per-round sites (the other is step 38).
    `CombatManager.cs:1344-1346`; `Hook.cs:560-570`. See **G4**, **G7**.
64. `await Hook.AfterTurnEnd(state, Player, participants)` — the player-side
    `AfterSideTurnEnd`/`AfterSideTurnEndLate` pair, **after** the hand flush
    (seed fact 2, the Parrying Shield slot). `CombatManager.cs:1305-1310`.

### Side switch and extra turns — `CombatManager.cs:1354-1425`

65. `SwitchFromPlayerToEnemySide`: null state → return; clear
    `_playersTakingExtraTurn`, then per player `Hook.ShouldTakeExtraTurn(state,
    player)` → repopulate it. **Evaluated at the very end of the turn-end
    pipeline, after steps 42-64 have all run.** `CombatManager.cs:1356-1373`;
    `Hook.cs:2457-2467`. See **G3**.
66. `SwitchSides()`: on the player side with no extra turn →
    `CurrentSide = Enemy`. Otherwise → `CurrentSide = Player`, and
    `IncrementTurnNumber()` for the extra-turn players; on a **normal** round
    it is every player **and `RoundNumber++`**. An extra turn therefore
    advances `TurnNumber` but **not** `RoundNumber`.
    `CombatManager.cs:1387-1419`; `PlayerCombatState.cs:157-160`. See **N4**.
67. `foreach (creature in _state.Creatures) creature.OnSideSwitch()` — a
    monster clears `SpawnedThisTurn`, a player does nothing; then the
    `TurnEnded` event. `CombatManager.cs:1420-1424`; `Creature.cs:694-704`;
    `MonsterModel.cs:479-483`; `Player.cs:849-851`.
68. Per extra-turn player: `await Hook.AfterTakingExtraTurn(state, player)`;
    then `WaitForUnpause()` and `await StartTurn(actionDuringEnemyTurn)`.
    `CombatManager.cs:1375-1384`; `Hook.cs:1220-1226`.

### Win / loss / reset — `CombatManager.cs:180-220, 887-1059`

69. `IsEnding`: `!IsInProgress` → false; `_pendingLoss != null` → true; any
    `e.IsAlive && e.IsPrimaryEnemy` → false;
    `Hook.ShouldStopCombatFromEnding(state)` → false; else true.
    `IsOverOrEnding` is `IsEnding || !IsInProgress`.
    `CombatManager.cs:180-220`; `Creature.cs:252-277`; `Hook.cs:2442-2452`.
70. `CheckWinCondition`: a pending loss → `ProcessPendingLoss()` (null the
    pending loss, `IsInProgress = false`, fire the **`CombatEnded` C# event
    only — no hook whatsoever**) and return true; else `IsEnding` →
    `EndCombatInternal()` and return true; else false.
    `CombatManager.cs:1046-1059, 945-965`.
71. `EndCombatInternal` (the **victory** path): record `TurnNumber`;
    `IsInProgress = false`; phase None; `PlayerActionsDisabled = false`; clear
    extra turns; per player `await ReviveBeforeCombatEnd()`;
    `Hook.AfterCombatEnd(runState, state, room)`; `History.Clear()`;
    `room.OnCombatEnded()`; write the replay; per player `AfterCombatEnd()`;
    `Hook.AfterCombatVictory(runState, state, room)`; hover-tips, turn
    accounting, saves, achievements, `CombatWon` and `CombatEnded` events.
    `CombatManager.cs:970-1033`; `Hook.cs:328-336, 340-348`.
72. `LoseCombat()` only *records* `_pendingLoss = new PendingLossState(state,
    room)` (idempotent); the loss is processed at the next `CheckWinCondition`.
    `HandlePlayerDeath(player)` separately removes every card in all five
    piles from combat and zeroes energy and stars.
    `CombatManager.cs:923-951`.
73. `CheckForEmptyHand(ctx, player)`: `IsInProgress &&
    !IsExecutingCardOrPotionEffect(player) && hand is empty` →
    `Hook.AfterHandEmptied`. Called **only** after a card play and after a
    potion use — explicitly *not* from ending the turn.
    `CombatManager.cs:887-893`; `Hook.cs:611-621`.
74. `Reset(graceful)`: cancel the CT; per creature `Reset()` +
    `RemoveCreature` + `state.RemoveCreature`; `_state = null`;
    `_pendingLoss = null`; `DebugForcedTopCardOnNextShuffle = null`;
    `IsInProgress`/`IsStarting`/`IsEnemyTurnStarted = false`;
    `History.Clear()`; clear `_cardOrPotionEffectDepth`.
    `CombatManager.cs:899-921`. Waiver — the sim builds a fresh
    `CombatState` per combat instead.

## Sim comparison (Step C summary — full verdicts in the JSON)

The sim's turn loop is `CombatState.end_turn` (`combat.py:639-685`) plus
`PlayerCombatState.start_turn` (`player.py:151-186`), and it is *linear*: one
player, one function per phase, no action queue, no choice contexts, no
deferral. Three structural differences run through the whole record:

- **The sim has two turn phases, the game has six.** `Phase.PLAYER_TURN` /
  `Phase.COMBAT_OVER` (`combat.py:35-37`) against
  `None/Start/AutoPrePlay/Play/AutoPostPlay/End` (`PlayerTurnPhase.cs`).
  There is no window in which the sim's phase says "the player is being set
  up" or "auto-plays are running", so the two auto-play phases and the
  `_inPlayerTurnSetup` deferral have no surface at all (**G8**, **N1**).
- **The sim's enemy side is per-enemy; the game's is per-side.** C# has no
  per-creature turn-start or turn-end hook at all: block clear, `BeforeTurnStart`
  and `AfterBlockCleared` run in three complete passes over every participant,
  and `AfterSideTurnStart` / `BeforeTurnEnd` / `AfterTurnEnd` fire **once**
  for the whole side. The sim invents `on_enemy_turn_start(enemy)` and
  `on_enemy_turn_end(enemy)` and interleaves them with each enemy's move
  (**G5**).
- **The sim has no `AfterFlush`, no `BeforeFlush`, no
  `AfterPreventingBlockClear`, no `ShouldStopCombatFromEnding`, no
  `AfterCombatVictory` and no auto-play-phase hooks.** Where the game brackets
  a step with a "we did/did not do it" event, the sim usually has only the
  action (**G2**, **G4**, **G10**).

**Verdict counts**, recomputed programmatically from
`audits/seam/turn_structure.json` (`collections.Counter` over
`steps + guards`), are **95 entries: 64 gap, 20 faithful, 10 waiver, 1
deliberate-divergence** — 74 steps (45 gap / 20 faithful / 8 waiver / 1 dd)
and 21 guards (19 gap / 2 waiver). The unit verdict is the rollup `gap`.

### Gaps found

**Nine are LIVE on currently-ported content and pinned with a strict xfail** —
**G1**, **G2**, **G3**, **G4**, **G6**, **G8**, **G12**, **G13**, **G14** —
and a tenth, **G9**, is live under seed parity but is an RNG-stream finding
rather than a hook-order one, so the conformance suite is its pin. The rest
(**G5**, **G7**, **G10**, **G11**, **G15**, **G16**) are dormant with the
concrete unported trigger named.

> **Corrections made in Step C/D to this file's own Step-A/B prose.** Every
> one was found by running the sim, not by re-reading the source:
>
> 1. **G13 was written as dormant on the claim that none of the sim's
>    `on_combat_start` / `on_player_turn_start(ed)` listeners deals damage.
>    That claim is false** — a scripted scan finds seven, four of them relics.
>    G13 is **LIVE** (Royal Poison; see below) and is now pinned.
> 2. **G8 and G12 were written as dormant on the claim that no ported pair
>    contends. Both contend today** — Stampede vs Cloak Clasp (G8) and
>    Orichalcum vs Cloak Clasp (G12), each verified by execution. Both are now
>    **LIVE** and pinned.
> 3. **G4's stated mechanism was wrong.** `after_flush` has no ported listener
>    at all (C#'s only implementer, `Bookmark.cs`, is unported), so "Runic
>    Pyramid is a ported `ShouldFlush` listener" does not by itself make
>    anything observable. The live path is Joss Paper's port hanging its
>    deferred-Ethereal credit on `on_hand_emptied`, which the skipped flush
>    never fires.
> 4. **G2's liveness is now proven rather than asserted.**
>    `CombatState.IterateHookListeners` walks a creature's **powers before its
>    relics** (`CombatState.cs:412-435`) and `Hook.ShouldClearBlock` returns
>    the **first** vetoing listener (`Hook.cs:2193-2204`), so with Barricade +
>    Sturdy Clamp the C# preventer is Barricade and Sturdy Clamp's cap never
>    runs.
> 5. **G3's quoted trace was a narrow-trace artefact.** A full hook trace of
>    the Pael's Eye `end_turn` is 24 calls long, not three; the three-call
>    claim only holds for the hooks the previous agent happened to wrap.
> 6. **G5 said "nine `on_enemy_turn_end` implementations". There are eight**
>    (and seven `on_enemy_turn_start`); all fifteen self-filter, so the
>    dormancy conclusion stands.
> 7. **Three gaps the prose did not have at all** were found in Step C and are
>    recorded below: **G14** (the turn-1 `ShouldStartAtBottomOfDrawPile` pass,
>    LIVE via Imbued), **G15** (the turn-end-in-hand wrapper re-consulting
>    `ShouldEtherealTrigger`, dormant on both sides) and **G16**
>    (`on_hand_emptied` fired from the flush, the one site C# excludes).

- **G1 — `AfterBlockCleared` is a separate unconditional loop; the sim fires
  it only when the block was actually cleared. LIVE.** C# runs the block clear
  and the event in **two** loops (`CombatManager.cs:492-499` then `500-507`),
  so `Hook.AfterBlockCleared(state, creature)` fires for *every* participant —
  including one with no block, one whose clear a `ShouldClearBlock` listener
  prevented, and a player on turn 1 whose `AfterTurnStart` returned early. The
  sim fuses the two: `player.py:157-159` fires `on_block_cleared` only inside
  the `if should_clear_block(...)` arm, and `combat.py:296-298` additionally
  gates the enemy arm on `enemy.block > 0`. Both sides ported: **Sturdy
  Clamp** returns false from `ShouldClearBlock` for its owner
  (`SturdyClamp.cs:22-29`, `relics/sturdy_clamp.py:23-25`) and **Horn Cleat**
  / **Captain's Wheel** are `AfterBlockCleared` listeners
  (`HornCleat.cs:20-27`, `CaptainsWheel.cs:20-27`,
  `relics/horn_cleat.py:19-22`, `relics/captains_wheel.py:19-22`); so are
  **Anchor** and **Fake Anchor**, which the sim re-wired onto the same hook
  (see **G6**). The strongest preventer is not a relic at all: **Barricade**
  is a ported Ironclad Rare Power card (`cards/barricade_card.py:33-34`,
  `powers.py:140`) whose `ShouldClearBlock` is false for its owner every turn.
  Verified by execution: a fresh combat with `[horn_cleat]` reaches turn 2
  with **14** block; the same combat with one Barricade stack on the player
  reaches turn 2 with **0**, and `[sturdy_clamp, horn_cleat]` also **0** (C#
  fires Horn Cleat regardless — under Sturdy Clamp it caps the carry-over at
  10 in `AfterPreventingBlockClear` first and then adds 14).
  `[captains_wheel]` reaches turn 3 with **18** block and
  `[sturdy_clamp, captains_wheel]` with **0**. The
  `block > 0` half is the same mechanism and gets the same verdict at every
  site (dormant on the enemy side only because the ported enemy-side
  `AfterBlockCleared` listeners — `SelfFormingClayPower`, `BurrowedPower`'s
  companion — are not; `ToricToughnessPower` and `BlockNextTurnPower` are
  ported but only ever land on the player, via the Toric Toughness event card
  `cards/event_cards.py:142-146` and Prolong `cards/colorless_skills.py:495-499`).
  Pinned with a strict xfail.
- **G2 — there is no `after_preventing_block_clear` hook; Sturdy Clamp
  hand-rolls it onto `on_player_turn_start`. LIVE (same combats as G1).**
  `Creature.ClearBlock` (`Creature.cs:718-728`) fires
  `Hook.AfterPreventingBlockClear(preventer, creature)` on the else-arm, and
  `SturdyClamp.cs:31-46` uses it to cap the retained block at 10 *at the
  moment of the prevented clear*. `sts2_rl/hooks.py` defines no such hook, so
  `relics/sturdy_clamp.py:28-32` caps on `on_player_turn_start` instead —
  which `player.py:169` fires **after** the energy reset (`player.py:163-168`)
  rather than before it. The gap is a real ordering difference at a hook the
  sim does not have; it is also the reason C#'s `preventer` identity check
  (`if (this != preventer)`) has no analogue, so with two block-clear
  preventers the sim runs every one's prevention effect where C# runs only the
  one that actually vetoed. **That second half is the provable one**, and it
  is why G2 is pinned separately from G1: `Hook.ShouldClearBlock` returns the
  **first** listener that vetoes (`Hook.cs:2193-2204`) and
  `CombatState.IterateHookListeners` adds each creature's **powers before that
  player's relics** (`CombatState.cs:412-435`), so with Barricade and Sturdy
  Clamp both held the preventer is `BarricadePower` and Sturdy Clamp's cap
  never runs. Verified by execution: the sim trims a 30-block player to
  **10**; C# keeps all 30. Pinned with a strict xfail
  (`test_sturdy_clamp_does_not_cap_when_it_is_not_the_preventer`).
- **G3 — the extra-turn check short-circuits the entire turn-end pipeline.
  LIVE.** `combat.py:648-652` tests `should_take_extra_turn` at the **top** of
  `end_turn` and, on success, runs only `on_extra_turn`, `turn += 1` and
  `start_turn()`. C# evaluates `Hook.ShouldTakeExtraTurn` in
  `SwitchFromPlayerToEnemySide` (`CombatManager.cs:1360-1373`), i.e. **after**
  `EndPlayerTurnPhaseOneInternal` (auto-post-play, `BeforeTurnEnd`,
  `DoTurnEnd`, `BeforeFlush`) and **after** `EndPlayerTurnPhaseTwoInternal`
  (`FlushPlayerHand`, `AfterFlush`, `EndOfTurnCleanup`, `AfterTurnEnd`); only
  the *enemy side* is skipped. Ported on both sides: **Pael's Eye** is a
  ported Ancient relic (`PaelsEye.cs:108-137`, `relics/paels_eye.py:36-46`),
  and the sim has **38** `on_player_turn_end` listeners plus
  `after_player_turn_end` (Parrying Shield). Verified by execution: with
  Pael's Eye held and no card played, a **full** hook trace of `end_turn` is
  24 calls long — `should_take_extra_turn` → `on_extra_turn` → five
  `on_card_exhausted` (Pael's Eye's own hand exhaust) → the entire
  `start_turn` — and contains **no** `on_player_turn_end`, **no**
  `should_flush_hand`, **no** `after_player_turn_end`, no ethereal exhaust
  pass and no turn-end-in-hand effects. (An earlier draft of this file
  reported the trace as exactly
  `['should_take_extra_turn', 'on_extra_turn', 'on_player_turn_started']`;
  that was a narrow-trace artefact, corrected here.) Pinned with a strict
  xfail. (Note the sim also folds C#'s
  `BeforeSideTurnEndEarly` hand-exhaust and `AfterTakingExtraTurn` into one
  `on_extra_turn` notification — the same mechanism, same verdict.)
- **G4 — a false `ShouldFlush` skips `AfterFlush` and `EndOfTurnCleanup`, and
  neither exists in the sim anyway. LIVE.** C#'s `FlushPlayerHand` treats
  `ShouldFlush == false` as "every card is retained" and then still runs
  `Hook.AfterFlush(..., cardsToFlush, cardsToRetain)` and
  `PlayerCombatState.EndOfTurnCleanup()` unconditionally
  (`CombatManager.cs:1327-1346`). The sim's `end_turn` guards the whole thing:
  `if self.hooks.should_flush_hand(): self.player.discard_hand()`
  (`combat.py:661-662`), so with a false result nothing at all happens — no
  `on_hand_emptied`, and there is no `after_flush` hook in `sts2_rl/hooks.py`
  to fire in the first place. **The `after_flush` half is dormant** — C#'s only
  `AfterFlush` implementer is `Bookmark.cs`, which is unported — and the
  `EndOfTurnCleanup` half is **G7**, also dormant, so "Runic Pyramid is a
  ported `ShouldFlush` listener" is *not* on its own enough to make the gap
  live (a correction to this file's Step-B prose). **The live path runs
  through the sim's `on_hand_emptied`**, which `player.py:197` fires from
  inside `discard_hand`: **Joss Paper** is a ported Uncommon relic whose port
  defers Ethereal-caused exhausts and credits them from `on_hand_emptied`
  (`relics/joss_paper.py:41-45`), where the real Joss Paper credits them from
  `AfterSideTurnEnd` (`JossPaper.cs:116`), which fires whatever `ShouldFlush`
  returned. **Runic Pyramid** (`RunicPyramid.cs:10-17`,
  `relics/runic_pyramid.py:16-17`, from the Darv shrine, `events/darv.py:33`)
  and **Ringing Triangle** (`relics/ringing_triangle.py:15`) are the ported
  `ShouldFlush` listeners. Verified by execution: a turn that exhausts five
  Ethereal cards leaves the next hand at **6** cards with `[joss_paper]` and
  at **5** with `[joss_paper, runic_pyramid]` — the deferred credit is
  stranded (`_ethereal_pending` stays at 5) and the Joss Paper draw never
  happens, where the real game draws it either way. Pinned with a strict
  xfail. See also **G16** for the `on_hand_emptied` call site itself.
- **G5 — the enemy side is per-enemy in the sim and per-side in the game.
  Dormant.** C# runs three complete passes over every participant before any
  enemy acts (`BeforeTurnStart` 449-455, `AfterTurnStart`/`ClearBlock`
  492-499, `AfterBlockCleared` 500-507), then one `Hook.AfterSideTurnStart`
  (522), then the moves (1072-1090), then one `Hook.BeforeTurnEnd` (1251) and
  one `Hook.AfterTurnEnd` (1256). The sim's `_run_enemy_turns`
  (`combat.py:286-345`) does `[clear block → on_enemy_turn_start → move →
  on_enemy_turn_end]` per enemy and only `on_enemy_side_end` once. Verified by
  execution with two enemies holding block: the sim records
  `['on_block_cleared', 'on_enemy_turn_start', 'on_enemy_turn_end',
  'on_block_cleared', 'on_enemy_turn_start', 'on_enemy_turn_end',
  'on_enemy_side_end']`, where C# gives `[clear1, clear2, AfterBlockCleared1,
  AfterBlockCleared2, AfterSideTurnStart, move1, move2, BeforeTurnEnd,
  AfterTurnEnd]`. **Dormant**, and the reachability was checked rather than
  assumed: every ported listener on these hooks self-filters to its own owner
  (a walk of `sts2_rl/powers.py` finds `if self.owner is enemy` / `if enemy is
  self.owner` on all seven `on_enemy_turn_start` and all **eight**
  `on_enemy_turn_end` implementations — an earlier draft said nine — and
  **zero** relic, card, enchantment or potion implements any of the three, the
  only non-`hooks.py` definitions in the whole package being in `powers.py`),
  so the N-fold dispatch is neutralised;
  and the only ported monster move that touches another monster's block is
  Guardbot's `GUARD_MOVE` (`monsters/glory/fabricator.py:44-49`), whose target,
  the Fabricator, always sits *earlier* in the enemy list and has therefore
  already cleared in both models. It goes live the moment (a) any
  cross-enemy effect targets a *later*-indexed enemy's block or turn-start
  power, or (b) `PoisonPower` becomes reachable — it is ported
  (`powers.py:484-490`) and C# fires it from `AfterSideTurnStart`
  (`PoisonPower.cs:54-73`), i.e. for *all* enemies before *any* move, but a
  grep of `sts2_rl/cards`, `sts2_rl/relics` and `sts2_rl/potions.py` finds no
  Ironclad-reachable source that applies it.
- **G6 — the sim clears the player's block on turn 1; the game does not.
  LIVE.** `Creature.AfterTurnStart` returns *before* `ClearBlock` for a player
  whose `PlayerCombatState.TurnNumber == 1` (`Creature.cs:681-692`), which is
  what lets `Hook.BeforeCombatStart` grant block that survives into the first
  enemy turn. `player.py:157-159` has no turn-1 arm. Verified by execution: a
  relic that grants 10 block from `on_combat_start` (which `combat.py:208`
  fires immediately before `start_turn()` at 209 — the sim's own
  `BeforeCombatStart` slot) leaves the player at **0** block on turn 1. LIVE
  and already load-bearing: **Anchor**'s real hook is `BeforeCombatStart`
  (`Anchor.cs:19-23`) and the sim had to re-wire it onto `on_block_cleared`
  to compensate (`relics/anchor.py:16-25`, whose docstring says so outright:
  "the sim grants it after the turn-1 block clear so it survives into the
  first enemy turn"), as did **Fake Anchor** (`relics/fake_anchor.py:24-31`).
  That workaround is itself what makes **G1** bite those two relics. Pinned
  with a strict xfail.
- **G7 — `PlayerCombatState.EndOfTurnCleanup` has no sim counterpart at
  either of its two sites. Dormant.** C# runs it twice per round: at the end
  of the enemy turn for every player (`CombatManager.cs:1252-1255`) and inside
  each player's `FlushPlayerHand` (1346). Per card in **every** pile it clears
  `ExhaustOnNextPlay`, `HasSingleTurnRetain`, `HasSingleTurnSly` and the
  turn-scoped cost modifiers (`CardModel.cs:1610-1623`;
  `CardEnergyCost.cs:331-336`). The sim's only per-turn card reset is
  `Card.reset_turn_cost_modifiers` (`cards/base.py:265-269`), which clears
  `_cost_delta_this_turn` / `_free_this_turn` / `_cost_this_turn` and nothing
  else, and it runs at the **start** of the next player turn
  (`player.py:153-155`) rather than at either end-of-turn site. Two
  consequences: the reset window is a full enemy turn wider than the game's
  (an effect reading a card's cost during the enemy turn sees the stale
  modifier), and there is no single-turn Retain / single-turn Sly /
  ExhaustOnNextPlay state to clear because the sim has no such fields — a card
  is `retain` or not (`player.py:192`). Dormant: no ported effect grants Retain
  or Sly for one turn only, and `ExhaustOnNextPlay` is set only by
  `CardPileCmd.AutoPlayFromDrawPile(forceExhaust)`
  (`CardPileCmd.cs:933-965`), which is unported. It goes live with the first
  single-turn Retain/Sly grant, or with any effect that reads a cost modifier
  during the enemy turn.
- **G8 — the AutoPrePlay and AutoPostPlay phases do not exist; their two hooks
  are hand-rolled onto neighbouring slots. LIVE on the AutoPostPlay side.**
  C# gives start-of-turn
  auto-plays their own phase, entered strictly **after** `AfterSideTurnStart`
  and the orb queue (`CombatManager.cs:556-572`), and end-of-turn auto-plays
  a phase entered strictly **before** `BeforeTurnEnd`
  (`CombatManager.cs:1160-1176`). The sim has neither hook: **Whispering
  Earring** (`relics/whispering_earring.py:27-43`) and the **Imbued**
  enchantment (`enchantments.py:262-272`) both fire from
  `on_player_turn_started`, which is the sim's `AfterSideTurnStart` slot
  (`hooks.py:285-295`), so their auto-plays are interleaved with the
  turn-start relics in listener-registration order instead of running after
  all of them; and nothing at all maps to `AfterAutoPostPlayPhaseEntered`.
  **The AutoPrePlay half is dormant** — the two ported users' effects (play
  cards / auto-play one Skill) do not read any other turn-start listener's
  output — but **the AutoPostPlay half is LIVE, and this file's Step-B prose
  saying otherwise was wrong.** C#'s `AfterAutoPostPlayPhaseEntered`
  implementers are `HowlFromBeyond.cs`, `IAmInvincible.cs` and
  `StampedePower.cs`; **Stampede** (`powers.py:1017-1040`) and the **Howl From
  Beyond** card (`cards/howl_from_beyond.py:45`) are both ported and both fire
  from `on_player_turn_end`, the sim's `BeforeTurnEnd` slot. **Cloak Clasp** is
  a ported Rare relic that gains 1 Block per card in hand from *plain*
  `BeforeSideTurnEnd` (`CloakClasp.cs:24`, `relics/cloak_clasp.py:19-24`), so
  the two contend directly: C# always runs Stampede's auto-plays first and lets
  Cloak Clasp count the reduced hand, while the sim registers relics before
  powers and counts the full one. Verified by execution with a 5-card hand and
  Stampede 2: forcing Stampede first gives **3** block (the C# answer), the
  natural order gives **5**. Pinned with a strict xfail. It also goes live for
  any content whose *start*-of-turn auto-play must observe every turn-start
  effect first (History Course is the C# example, unported).
- **G9 — enemy intents are rolled at the end of each monster's own move, not
  at the start of the player's turn. Dormant-under-legacy, LIVE under seed
  parity.** `CombatManager.cs:478-484` rolls **every** enemy's next move in one
  pass at the start of the player's turn, unconditionally and in enemy-list
  order, and skips the pass entirely on an extra player turn; the very first
  roll happens even earlier, in `AfterCreatureAdded`
  (`CombatManager.cs:863-866`). The sim instead advances each monster's own
  machine as part of performing its move, with `telegraph_next_move`
  (`monsters/base.py:96-105`) as the explicit stand-in, and `combat.py:314-329`
  documents the consequence in the engine itself: a monster stunned this round
  keeps its move (correct) but **misses one `MonsterAi` draw** where the game
  takes one. Under a parity run a missed draw is a stream desync, which is
  observable by definition; under legacy it is invisible. Recorded here as a
  gap rather than fixed, and cross-referenced to Task 10, which owns what the
  roll returns.
- **G10 — the combat-end path collapses five C# distinctions into one hook,
  and the sim's two player-death exits disagree with each other. Dormant.**
  C# distinguishes (a) a **loss**, which goes `LoseCombat()` → `_pendingLoss`
  → `ProcessPendingLoss()` and fires the `CombatEnded` C# event and **no hook
  at all** (`CombatManager.cs:945-965`), from (b) a **victory**, which runs
  `EndCombatInternal` with `ReviveBeforeCombatEnd()` →
  `Hook.AfterCombatEnd` → `Hook.AfterCombatVictory` (970-1033); and it
  consults `Hook.ShouldStopCombatFromEnding` inside `IsEnding` (196-199). The
  sim has one `_end_combat(player_won)` firing one `on_combat_end(player_won)`
  (`combat.py:347-350`), no revive step, and no
  `should_stop_combat_from_ending` hook. On top of that, `_run_enemy_turns`
  has **two** player-death exits that behave differently: `combat.py:308-310`
  calls `_end_combat(player_won=False)` (hook fires) while
  `combat.py:332-335` sets `phase`/`result` by hand and returns (hook does
  **not** fire). Verified by execution: a listener that kills the player from
  `on_enemy_turn_start` records `[('on_combat_end', False)]`, and the ordinary
  case — the player dying to an enemy's attack — records `[]`, both ending in
  `Phase.COMBAT_OVER`. Dormant: the two ported effects that need
  `ShouldStopCombatFromEnding` hand-roll around it (`SteamEruptionPower`
  prevents the death instead, `powers.py:2004-2010`; `StockPower` spawns the
  replacement Axebot from `on_death`, `powers.py:2962-2984`, which runs before
  the `_all_enemies_dead()` check), and no ported `on_combat_end` listener
  distinguishes win from loss in a way the missed call would change. It goes
  live for any `AfterCombatVictory`-only listener, and the two-exit
  inconsistency is live the moment any `on_combat_end` listener has an effect
  that outlives the combat.
- **G11 — `Hook.BeforeTurnEnd(Enemy)` has no sim counterpart. Dormant.** C#
  fires the same three-pass `BeforeTurnEnd` dispatcher for the **enemy** side
  at `CombatManager.cs:1251`, immediately before `EndOfTurnCleanup` and
  `AfterTurnEnd`. The sim's `_run_enemy_turns` has only the per-enemy
  `on_enemy_turn_end` (`combat.py:341`) and the side-scoped
  `on_enemy_side_end` (345), which maps to `AfterTurnEnd`; there is no slot
  between them. Dormant because the ported enemy-side `BeforeSideTurnEnd*`
  content — `AsleepPower.BeforeSideTurnEndVeryEarly`, `DoomPower`,
  `HailstormPower`, `ChainsOfBindingPower` — was ported onto
  `on_enemy_turn_end` with an owner filter (`powers.py:1853-1863` is the
  Asleep case, which the sim's own comment labels "Mirrors
  BeforeSideTurnEndVeryEarly"), so with one enemy the two coincide. It goes
  live in any multi-enemy fight where one of those powers must act after the
  *last* enemy's move rather than after its own.
- **G12 — the sub-phase ordering inside `BeforeTurnEnd` / `AfterTurnEnd` /
  `AfterSideTurnStart` is flattened. LIVE.** C# guarantees ordering by
  running separate complete passes: `BeforeSideTurnEndVeryEarly` →
  `BeforeSideTurnEndEarly` → `BeforeSideTurnEnd` (`Hook.cs:1238-1261`),
  `AfterSideTurnEnd` → (awaited) → `AfterSideTurnEndLate`
  (`Hook.cs:1265-1291`), `AfterSideTurnStart` → `AfterSideTurnStartLate`
  (`Hook.cs:1163-1175`). The sim's `hooks.py` dispatchers are a single
  `for l in list(self._listeners)` pass each (e.g. `hooks.py:297-301`,
  `338-342`), so a "Late"/"VeryEarly" listener's guaranteed position becomes
  registration-order luck. **This file's Step-B prose claimed no ported pair
  contends today. That is wrong — one does, and it is a headline relic.**
  `Orichalcum` is deliberately two-phase in C#: `BeforeSideTurnEndVeryEarly`
  snapshots `Block > 0` into `ShouldTrigger` (`Orichalcum.cs:44-56`) and
  `BeforeSideTurnEnd` then grants the 6 Block, so *no* later turn-end listener
  can suppress it. **Cloak Clasp** grants 1 Block per card in hand from plain
  `BeforeSideTurnEnd` (`CloakClasp.cs:24`). Both are ported and both fire from
  the single `on_player_turn_end` slot (`relics/orichalcum.py:22-26`,
  `relics/cloak_clasp.py:19-24`). Verified by execution with a 5-card hand:
  `[cloak_clasp, orichalcum]` gives **5** block and `[orichalcum,
  cloak_clasp]` gives **11**, where C# always gives 11 — i.e. acquiring Cloak
  Clasp before Orichalcum silently switches Orichalcum off. Fake Orichalcum
  and Ripple Basin are the same shape, as are the ported `SandpitPower`
  (`AfterSideTurnStartLate`) and `DisintegrationPower`
  (`AfterSideTurnEndLate`). Same shape as `creature_card_cmds`' **G10**
  (`ModifyShuffleOrder` vs `AfterShuffle`). Pinned with a strict xfail.
- **G13 — `CheckWinCondition` runs at three of the game's six sites, and none
  of the three recomputes the condition. LIVE.** C# calls it after the
  player-turn setup (573), after the enemy
  turn starts (598), after **each** enemy's move (1084), after
  `Hook.BeforeTurnEnd(Player)` (1181), at the end of phase one (1208) and
  after `EndEnemyTurnInternal` (830). The sim checks after each enemy's move
  (`combat.py:336-338`), after the enemy side (implicitly, via the same
  return), and after the next player turn's setup (`combat.py:681-685`); it
  does **not** check after the turn-1 setup in `__init__` (`combat.py:209` is
  followed by nothing), nor between `on_player_turn_end` and
  `_process_turn_end_cards` in the shape C# uses (the sim's checks at 655-660
  test `phase == COMBAT_OVER`, which is only set by a *previous*
  `_end_combat`, not recomputed).
  **LIVE. This file's Step-B prose called it dormant on the claim that none of
  the sim's `on_combat_start` / `on_player_turn_start(ed)` listeners deals
  damage; a scripted scan of every such listener finds SEVEN that do**, four
  of them relics: `relics/festive_popper.py:21` (9 to all enemies on turn 1),
  `mercury_hourglass.py:22` (3 to all enemies every turn),
  `mr_struggles.py:22` (turn-number damage to all enemies) and
  `royal_poison.py:25` (4 unblockable to the **player** on turn 1), plus three
  powers. Two of them — Festive Popper and Mercury Hourglass — hand-roll a
  `self._check_win()` call (`relics/base.py`) *precisely because this check is
  missing*, which is itself evidence of the gap; and **neither covers player
  death**. **Royal Poison** is a ported Event relic granted by the Round Tea
  Party event (`events/round_tea_party.py:40`), mirroring
  `RoyalPoison.cs:18-25`'s `AfterPlayerTurnStart` — which C# follows
  immediately with `CheckWinCondition` at `CombatManager.cs:573`. Verified by
  execution: `CombatState(relics=[royal_poison], current_hp=4, max_hp=80)`
  returns with `player.hp == 0`, `player.is_dead == True`,
  `phase == Phase.PLAYER_TURN`, `is_over == False` and **six valid actions** —
  the sim hands the player a whole turn (which they can win the fight in)
  after a death the real game processes on the spot. Pinned with a strict
  xfail.
- **G14 — the turn-1 `ShouldStartAtBottomOfDrawPile` pass is missing, so an
  Imbued card can be drawn into the opening hand. LIVE.** On turn 1
  `CombatManager.cs:657-672` runs **two** pile moves before the draw: every
  card whose enchantment sets `ShouldStartAtBottomOfDrawPile` goes to the
  **bottom** (`MoveToBottomInternal`), and only then does every `Innate` card
  *not already moved* (`.Except(list)`) go to the top. `player.py:172-182`
  ports the Innate half only. `ShouldStartAtBottomOfDrawPile` has exactly one
  implementer in the whole decompiled game — `Imbued.cs:11` — and **Imbued is
  ported** (`enchantments.py:243-267`) and obtainable: **Electric Shrymp** is a
  ported relic in `ALL_RELICS` that enchants a deck Skill with it
  (`relics/electric_shrymp.py:17-21`). The bottom-move exists so the
  self-auto-playing Imbued card does not occupy an opening-hand slot. Verified
  by execution over 30 seeds with a 9-Strike + 1-Imbued-Defend deck: the sim's
  turn-1 hand is **4** cards on 17 seeds and 5 on the other 13, where C# is
  always 5. Knock-on: the sim's Imbued only fires `if self.card in player.hand`
  (`enchantments.py:261-266`), so on the seeds where it is not drawn the sim
  never auto-plays it at all, where C# always does (`Imbued.cs:20-26`, from the
  AutoPrePlay phase — **G8**). Pinned with a strict xfail.
- **G15 — the turn-end-in-hand wrapper re-consults `should_ethereal_trigger`
  in the sim; C# does not. Dormant.** `CardModel.OnTurnEndInHandWrapper`
  (`CardModel.cs:1682-1698`) decides the card's destination on the raw
  keyword — `if (Keywords.Contains(Ethereal)) Exhaust else Add(Discard)` — and
  never re-consults `Hook.ShouldEtherealTrigger`, which step 52's partition
  already consulted (and only for the cards with *no* turn-end effect).
  `combat.py:370` re-consults it, so a false predicate would send an Ethereal
  turn-end card to the **discard** pile in the sim and to the **exhaust** pile
  in the game. Dormant on **both** sides, verified:
  `grep -rl 'override.*ShouldEtherealTrigger'` over the whole decompiled game
  returns **zero** files, and `grep -rn 'def should_ethereal_trigger' sts2_rl/`
  returns only the `hooks.py` dispatcher — the predicate is constant-true and
  the branches coincide. Goes live with the first implementation on either
  side.
- **G16 — `on_hand_emptied` is fired from the end-of-turn flush, the one site
  C# deliberately excludes, and from nowhere else. Dormant.** C#'s
  `CheckForEmptyHand` (`CombatManager.cs:887-893`) is called **only** after a
  card play and after a potion use, and `UnceasingTop.cs:25-35` carries an
  explicit remark saying why the hand draw and the hand flush must not trigger
  it ("if a card is autoplayed during this time, the player's hand will always
  be empty, so Unceasing Top will always draw"); it further gates on
  `IsExecutingCardOrPotionEffect` and on the player's `Phase` being
  AutoPrePlay/Play/AutoPostPlay. The sim's `on_hand_emptied` has exactly one
  call site — `player.py:197`, at the bottom of `discard_hand` — and none after
  a card play or a potion. Dormant: the sim re-wired the one C#
  `AfterHandEmptied` implementer away from it (`relics/unceasing_top.py:21-28`
  uses `on_card_played` with a hand-empty test, which reproduces the C#
  semantics), and the only listener left, **Joss Paper**
  (`relics/joss_paper.py:41-45`), was deliberately written against the sim's
  flush-time semantics — its C# counterpart uses `AfterSideTurnEnd`
  (`JossPaper.cs:116`). Not independently observable today, but it is the
  mechanism through which **G4** becomes live.

### The `N`-guards

- **N1 — the `_inPlayerTurnSetup` / `_deferredEndTurnTransition` race guard has
  no sim analogue.** `CombatManager.cs:56-65, 700-714, 722-735` exists exactly
  so that a card auto-played during the AutoPrePlay phase can end the turn
  without the transition racing the tail of `StartTurn`. The sim's
  `start_turn` is synchronous and `end_turn` re-entered from inside it would
  recurse. Recorded as a **gap** and not a waiver: the ported Whispering
  Earring auto-plays real cards during what C# calls the setup window
  (`relics/whispering_earring.py:27-43`) and guards against the recursion by
  hand (`if combat.is_over or self.turn != start_turn: break`), which is a
  workaround for exactly this missing machinery. Dormant only because no
  ported turn-1 auto-playable card ends the turn.
- **N2 — presentation, animation, SFX, banners, checksums, replay writing,
  saves, achievements, the `ActionExecutor`/`ActionQueueSynchronizer` layer and
  every `HookPlayerChoiceContext` pause/resume path.** Waiver — out of scope
  by the shared rules, and the sim is single-player and synchronous.
- **N3 — orbs (`OrbQueue.AfterTurnStart` at `CombatManager.cs:533`,
  `OrbQueue.BeforeTurnEnd` at 1218).** Waiver — orbs are the Defect's and the
  sim is Ironclad-only.
- **N4 — `RoundNumber` and `TurnNumber` are one counter in the sim.**
  `CombatState.turn` (`combat.py:108`) is incremented once per player turn
  including extra turns (`combat.py:650`, `674`), whereas
  `SwitchSides` increments `PlayerCombatState.TurnNumber` for extra-turn
  players but `CombatState.RoundNumber` **only** on a normal round
  (`CombatManager.cs:1405-1418`). `AbstractModel.cs:1125` explicitly directs
  content to use `AfterSideTurnStart` "with a RoundNumber check", so the two
  are meant to be distinguishable. Recorded as a **gap** carrying **G3**'s
  precedence (it is only reachable on the extra-turn path, which G3 already
  makes divergent); dormant on its own because no ported content reads a
  round counter that an extra turn would skew.
- **N5 — the win-condition predicate itself is faithful.** `_all_enemies_dead`
  (`combat.py:272-277`) reproduces `IsPrimaryEnemy` exactly (`MinionPower` is
  the only `OwnerIsSecondaryEnemy` power in the whole source) and its
  `primaries or self.enemies` fallback matches C#'s behaviour when every
  enemy is a minion. The two things missing from the *surrounding*
  machinery — `ShouldStopCombatFromEnding` and the pending-loss two-step —
  are **G10**'s, and this guard carries G10's verdict so the rollup stays
  actionable.

## Test coverage (Step D)

- **Full `end_turn` hook sequence** (pin table item 1): `Grep`ping `test/` for
  `end_turn` finds 300+ call sites but **no ordering assertion** — the closest
  are `test/test_powers.py` cases that assert a single hook's *effect* after
  `end_turn`, and `test/test_hook_order.py` had no turn-structure class at
  all. New pin added:
  `test/test_hook_order.py::TestTurnStructureOrder::test_end_turn_hook_sequence`,
  a single exact-list assertion over **32 calls** to the **21** distinct
  turn-lifecycle hooks one `end_turn` touches (an earlier draft of this file
  said 18 hooks; 21 is the measured figure, and 32 is the call count once the
  repeated `on_card_discarded` / `should_clear_block` / `on_block_cleared` /
  `should_draw` / `on_card_drawn` calls are counted individually — the
  assertion pins the repeats too). The hand is seeded with Dazed / Burn /
  Strike so the ethereal pass (step 53), the turn-end-in-hand pass (step 54)
  and the flush (step 62) are all exercised, and both the enemy's and the
  player's block clears appear so the two are positionally distinguishable.
  The damage-pipeline hooks the enemy's attack runs through are deliberately
  left untraced: they are `damage_pipeline`'s seam.
- **`AfterTurnEnd` after the hand flush** (pin table item 2): `Grep`ping
  `test/` for `parrying_shield` finds
  `test/test_ancients.py::TestParryingShield` (three cases), which pins the
  relic's *effect* (block retained / halved) but not the ordering claim that
  `after_player_turn_end` runs after `discard_hand`. Recorded here as the
  existing coverage, and complemented — not duplicated — by the ordering
  assertion inside `test_end_turn_hook_sequence`, which places
  `after_player_turn_end` after `on_hand_emptied`.
- **G5** (per-enemy vs per-side scoping): new order-tracing test
  `TestTurnStructureOrder::test_enemy_side_is_interleaved_per_enemy`, written
  as a **passing** pin of the sim's current (divergent) order so that a future
  fix to the C# order has to come here and change it deliberately.

Nine new strict xfails, one per live gap. Each `reason` names the sim line,
the C# line, live-or-dormant and the observable effect, and each was
force-run (`py -m pytest test/test_hook_order.py::TestTurnStructureOrder -q
--runxfail`) to confirm it fails at the assertion its reason describes:

| gap | test | force-run failure |
| --- | --- | --- |
| G1  | `test_block_clear_event_fires_even_when_prevented` | `assert 0 == 14` |
| G2  | `test_sturdy_clamp_does_not_cap_when_it_is_not_the_preventer` | `assert 10 == 30` |
| G3  | `test_extra_turn_still_runs_the_turn_end_pipeline` | trace `[] != [on_player_turn_end, should_flush_hand, after_player_turn_end, on_extra_turn]` |
| G4  | `test_no_flush_still_credits_the_end_of_turn_hand_events` | `assert 5 == 6` |
| G6  | `test_player_block_is_not_cleared_on_turn_one` | `assert 0 == 10` |
| G8  | `test_end_of_turn_auto_plays_run_before_turn_end_hooks` | `assert 5 == 3` |
| G12 | `test_orichalcum_snapshots_block_before_other_turn_end_listeners` | `assert 5 == (5 + 6)` |
| G13 | `test_turn_one_setup_death_ends_the_combat` | `assert False` (`cs.is_over`) |
| G14 | `test_imbued_card_starts_at_the_bottom_of_the_draw_pile` | `assert 4 == 5` |

Under a normal run the class is 2 passed / 9 xfailed with no XPASS.
**G9** is the one live gap with no pin here: its observable is a MonsterAi
RNG-stream draw count, not a hook order, so the conformance suite owns it.
**G7**, **G10**, **G11**, **G15** and **G16** are dormant and unpinned — a pin
would have to assert behaviour no ported content can produce.
