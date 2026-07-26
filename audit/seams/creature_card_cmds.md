# Engine seam: `creature_card_cmds`

Audited 2026-07-25 (Task 7 of the six seam audits, Tier 2 of the
source-audit-pipeline design). Verdicts and rationale live in
`audit/records/seam/creature_card_cmds.json`; this file is the durable ordering spec
extracted from the C# source that the JSON record judges the sim against.

This seam is the *rest of the command layer*: every creature verb that is not
the damage pipeline (add / escape / block / heal / max-HP / stun), the player
resource verbs (energy / gold / stars / potion slots), and the whole card and
card-pile layer (auto-play, discard, exhaust, upgrade, transform, enchant,
afflict, pile add/remove, draw, shuffle, card selection).

## Source correction (Step A)

`audit/tools/harness.py`'s `SEAM_SOURCES["creature_card_cmds"]` listed four C#
files and one sim file. All four C# files are real and do contain seam logic,
but **three files carrying logic this seam audits were missing, and the sim
side named only one of the four files that implement the counterpart.** The
table was corrected (the edit is staged in this branch):

Added on the game side:

- **`src/Core/Commands/CardSelectCmd.cs`** — the sim file already in the table
  (`sts2_rl/cmds.py`) defines a `CardSelectCmd` class whose docstring says it
  "mirrors the game's CardSelectCmd", and no listed file contained that class.
  It carries real gameplay rules, not just screens: the auto-select shortcut
  (`!prefs.RequireManualConfirmation && count <= prefs.MinSelect` → take every
  candidate with no player choice, `CardSelectCmd.cs:396-399, 708-711`) and the
  draw-pile presentation sort (`orderby c.Rarity, c.Id`, `CardSelectCmd.cs:403-408`).
- **`src/Core/Entities/Cards/CardPile.cs`** — `CardPileCmd` never mutates a
  pile itself; every add/remove delegates to `CardPile.AddInternal` /
  `RemoveInternal` / `RandomizeOrderInternal` (`CardPile.cs:83-132, 69-74`),
  which is where the index semantics (`-1` appends, `>= 0` inserts), the
  duplicate-instance throw, `MaxCardsInHand = 10` (`CardPile.cs:21`) and the
  initial-shuffle `ModifyShuffleOrder` call live. Same relationship
  `PowerModel.cs` has to `PowerCmd.cs` in the `power_cmd` seam.
- **`src/Core/Extensions/ListExtensions.cs`** — the brief's seed fact "a random
  card pick is a StableShuffle + take-first; ties keep incoming order" is
  *defined* here (`ListExtensions.cs:22-60`), and `CardPileCmd.Shuffle` is
  nothing but a call to it plus bookkeeping.

Added on the sim side (`sts2_rl/cmds.py` alone covers well under half the
seam):

- **`sts2_rl/player.py`** — `CardPileCmd.Draw` / `Shuffle` / `ShuffleIfNecessary`
  and `CardCmd.Discard` have their counterparts on `PlayerCombatState`
  (`_draw`, `_shuffle_draw_pile`, `reshuffle_discard_into_draw`,
  `shuffle_draw_and_discard`, `discard_hand`, `stable_shuffled_cards`).
- **`sts2_rl/run.py`** — `CardPileCmd.Add`-to-Deck, `RemoveFromDeck`,
  `CardCmd.Transform`-to-Deck and `PlayerCmd.GainGold`/`LoseGold` live on
  `RunState` (`add_card`, `remove_cards`, `transform_card`, `gain_gold`,
  `lose_gold`).
- **`sts2_rl/combat.py`** — `CardCmd.AutoPlay`'s counterpart is
  `CombatState.auto_play_card` / `auto_play`, and the PileType.Play limbo
  bookkeeping the brief's first seed fact is about is
  `_resolve_card_play`'s `_playing_card` marker.

### Source correction, fix pass 1 (2026-07-25)

Review found three more files the record cites as **primary evidence** but
that carried no sha256 staleness pin. All three were added to
`SEAM_SOURCES["creature_card_cmds"]` and the record's hash lists were
regenerated (`py audit/tools/audit_status.py` → not stale):

- **`src/Core/Entities/Creatures/Creature.cs`** (note the path — `Creature.cs`
  lives under `Entities/Creatures/`, not `Entities/`). Every `CreatureCmd`
  verb delegates its actual mutation here: `GainBlockInternal` /
  `LoseBlockInternal` (`Creature.cs:473-491`), `HealInternal` /
  `SetCurrentHpInternal` / `SetMaxHpInternal` (`477-501`), `StunInternal`
  (`524-542`), `RemoveAllPowersInternalExcept` (`658-666`). Cited at steps
  8/16/18/20/25/30 and in guards **G4** and **G13**. Same relationship
  `PowerModel.cs` has to `PowerCmd.cs` in the `power_cmd` seam.
- **`src/Core/Hooks/Hook.cs`** — the four **block** dispatchers this record
  claims (see the scope-boundary note below) are Hook.cs bodies:
  `ModifyBlock` (`Hook.cs:1310-1340`) is **G1**'s primary evidence and
  `AfterModifyingBlockAmount` (`Hook.cs:649-656`) is **G2**'s. Both prior
  seams (`damage_pipeline`, `power_cmd`) already list `Hook.cs` for exactly
  this reason.
- **`sts2_rl/hooks.py`** — the sim side of the same claim: the block modifier
  hooks return a bare aggregate with no companion event (`hooks.py:98-124`),
  which is **G2**'s core evidence, and the absence of `modify_shuffle_order`
  / `before_block_gained` / `after_card_changed_piles` from this file is what
  **G10**, step 12 and **G8** rest on.

### Source correction, fix pass 2 (2026-07-26)

Fix pass 2 propagated `hook_dispatch`'s gap **G9** (parallel sum/product vs
C#'s sequential running-value chain) to its third and last site, the **block**
dispatch, as **clause (c) of step 13**. That clause's verdict is *dormant*,
and the dormancy rests entirely on the **literal factors** the block modifiers
return — every reachable block multiplier is binary-exact, so the sim's float
product equals C#'s sequential decimal fold. That claim breaks the moment any
one of those files grows a non-dyadic factor, so the **whole block-modifier
population** is now pinned. Thirteen files were added to
`SEAM_SOURCES["creature_card_cmds"]` and the record's hash lists were
regenerated (`py audit/tools/audit_status.py` → not stale; no pre-existing hash
drifted):

- the **8** C# `ModifyBlockMultiplicative` overrides —
  `Powers/FrailPower.cs`, `Powers/NoBlockPower.cs`, `Powers/ShadowmeldPower.cs`,
  `Powers/UnmovablePower.cs`, `Relics/PaelsLegion.cs`, `Relics/Vambrace.cs`,
  `Relics/VitruvianMinion.cs`, `Singleton/MultiplayerScalingModel.cs`;
- the **2** C# `ModifyBlockAdditive` overrides — `Powers/DexterityPower.cs`,
  `Powers/FastenPower.cs` (the additive half of the same dispatch; **G1** and
  step 15 already cited both);
- the **3** sim files holding their five ported counterparts —
  `sts2_rl/powers.py` (Frail ×0.75, Unmovable ×2, No Block ×0),
  `sts2_rl/relics/vambrace.py` (×2 — also **G1**'s and **G2**'s primary sim
  evidence, previously unpinned) and `sts2_rl/relics/paels_legion.py` (×2).

The record now pins **19** game sources and **8** sim sources.

### Scope boundary — READ BEFORE TASK 8 (`turn_structure`) AND TASK 9 (`hook_dispatch`)

Three of this seam's files are shared with later seams. The split is by
**method**, with line ranges:

**`src/Core/Commands/CreatureCmd.cs`** — already split by `damage_pipeline`
(Task 5), which owns `CreatureCmd.cs:240-572` (`Damage`, `Kill`,
`KillWithoutCheckingWinCondition`). **This record does not re-audit that
region.** It owns the remainder: `Add` (38-82), the `Damage` overload
*forwarders* only as dispatch (96-240 — no logic), `Escape` (579-603),
`GainBlock` (617-664), `LoseBlock` (666-678), `Heal` (691-755),
`SetCurrentHp` (762-779), `GainMaxHp` (786-799), `LoseMaxHp` (811-828),
`SetMaxHp` (839-849), `SetMaxAndCurrentHp` (856-860), `Stun` (870-904),
`TriggerAnim` (912-945).

**`sts2_rl/combat.py`** — `turn_structure` (Task 8) owns the turn/phase
machinery: `_execute_enemy_turn`, `_run_enemy_turns`, `_end_combat`,
`_process_turn_end_cards`, `end_turn`, `valid_actions`, `is_over`, and
`play_card`'s energy/phase gate. **This record owns only the card-play
plumbing that mirrors `CardCmd.AutoPlay` and the pile layer**:
`auto_play` (combat.py:424-439), `auto_play_card` (516-558),
`select_cards` (560-581), and — inside `_resolve_card_play` (441-514) — the
result-pile placement and the `_playing_card` limbo marker only
(combat.py:452-454, 496-498, 500-512). The replay loop, the attack bracket
and the played-hook ordering inside `_resolve_card_play` belong to
`turn_structure`.

**`sts2_rl/player.py`** — `turn_structure` (Task 8) owns `start_turn`
(player.py:151-186) and the potion-belt accessors (107-149). **This record
owns the pile verbs**: `_compare_to_key` (23-34), `stable_shuffled_cards`
(37-50), `discard_hand` (188-197), `reshuffle_discard_into_draw` (199-218),
`shuffle_draw_and_discard` (220-239), `_shuffle_draw_pile` (241-274) and
`_draw` (276-292). `start_turn`'s *call* to `_draw` is `turn_structure`'s;
`_draw`'s own behaviour is this record's.

**Block-hook dispatchers.** `Hook.cs` is claimed by `damage_pipeline` (damage
modifiers), `power_cmd` (the six power-amount dispatchers) and `hook_dispatch`
(Task 9, everything else). The four **block** dispatchers —
`BeforeBlockGained` (Hook.cs:131-137), `AfterBlockGained` (143-149),
`AfterModifyingBlockAmount` (649-656) and `ModifyBlock` (1310-1340) — are the
direct bodies of `CreatureCmd.GainBlock`'s four calls and no other seam covers
them, so **this record claims those four**. Task 9 must not re-audit them; a
block-dispatch finding belongs here as an amendment to
`audit/records/seam/creature_card_cmds.json`.

### Scope boundary — READ BEFORE TASK 10 (`monster_state_machine`)

`CreatureCmd.Stun` (`CreatureCmd.cs:870-904`) is split between the two
records. **This record owns only the Cmd-level contract** — who may be
stunned and what `StunInternal` refuses (`Creature.cs:524-542`: throws for a
non-monster, no-ops on a dead creature or one with no combat state) — which
is step **30** and guard **N1**. **Task 10 owns the move-machine half** and
must audit it there, not here: the `"STUNNED"` `MoveState` installed via
`SetMoveImmediate`, its `MustPerformOnceBeforeTransitioning = true` flag, and
the `nextMoveId` default derived from `Monster.MoveStateMachine.StateLog`'s
last performed move. The sim's counterpart is a bare
`target.stunned = True` plus an optional `_move_key` rewrite
(`cmds.py:208-218`); everything about how that interacts with
`monsters/state_machine.py` is Task 10's finding to record.

Step **3** (`PrepareForNextTurn(rollNewMove: false)` for a monster spawned on
the player's turn, `CreatureCmd.cs:72-75`) defers to Task 10 for the same
reason: the sim has no separate intent-preparation step, and whether that
matters is a state-machine question.

## Seed facts, verified

1. **A card mid-OnPlay sits in `PileType.Play`, so a reshuffle it triggers
   excludes it.** Confirmed structurally: manual play moves the card out of
   the hand and into the Play pile *before* `OnPlay`
   (`CardPileCmd.AddDuringManualCardPlay`, `CardPileCmd.cs:669-670`), auto-play
   does the same when the card has no pile (`CardCmd.cs:114-117`), and
   `CardPileCmd.Shuffle` reads only the **Draw** and **Discard** piles
   (`CardPileCmd.cs:870-871`) — the Play pile is never in the shuffled set.
   Sim: `_resolve_card_play` appends the card to the *discard* pile and sets
   `player._playing_card` (`combat.py:452-454`), which
   `reshuffle_discard_into_draw` / `shuffle_draw_and_discard` hold back
   (`player.py:202-215, 230-237`) — **in parity mode only**. Verified by
   execution: parity run → held card not in the new draw pile; legacy run →
   held card **is** in the new draw pile (see guard **N9**).
2. **Out-of-combat transform APPENDS at the deck end.** Confirmed at
   `CardCmd.cs:436-446`: `if (type == PileType.Deck) pile2.AddInternal(replacement2)`
   — no index, and `CardPile.AddInternal`'s default `index = -1` appends
   (`CardPile.cs:83, 90-97`); every non-Deck pile takes the `AddInternal(replacement2, item4)`
   branch that re-inserts at the original card's recorded index. Sim:
   `RunState.transform_card` appends under parity and replaces in place under
   legacy (`run.py:459-469`). Verified by execution: parity → replacement at
   index 9 of 10; legacy → index 0.
3. **A random card pick is a StableShuffle + take-first; ties keep incoming
   order, sorted on the UPPERCASE id.** Confirmed: `StableShuffle`
   (`ListExtensions.cs:22-31`) copies, `Sort()`s with the element's own
   `IComparable` (for cards, `CardModel.CompareTo` = ordinal
   `ModelId.Entry` then `CurrentUpgradeLevel`), writes back, then runs
   `UnstableShuffle` — a Fisher-Yates consuming exactly `Count - 1`
   `rng.NextInt` draws (`ListExtensions.cs:45-60`). Sim:
   `stable_shuffled_cards` and `_shuffle_draw_pile` reproduce both
   (`player.py:23-50, 241-274`), parity-only.
4. **Death ≠ removal.** Confirmed on this side of the seam too: `Escape` is
   the *other* way a creature leaves combat (`CreatureCmd.cs:579-603`) and it
   explicitly refuses to run on an already-dead creature (581-584); `Heal` has
   **no** dead guard at all and revives a 0-HP creature
   (`CreatureCmd.cs:691-703`, `Creature.cs:477-486`) — see **G4**.
5. **Stun skips the move but not turn-start/end effects; escape counts as gone
   without dying.** Confirmed: `Stun` only swaps in a `"STUNNED"` `MoveState`
   with a no-op body via `SetMoveImmediate` (`CreatureCmd.cs:884-904`,
   `Creature.cs:524-542`) — nothing about turn boundaries is touched; and
   `Escape` removes the creature from combat with no `Kill`, no `BeforeDeath`,
   no `AfterDeath` (`CreatureCmd.cs:589-602`).

## Numbered ordering spec

### `CreatureCmd.Add` — `CreatureCmd.cs:38-82`

1. Guard: `!CombatManager.IsInProgress` → **throw**; `creature.CombatState == null`
   → **throw**; `!combatState.IsLiveCombat()` → return silently.
   `CreatureCmd.cs:55-67`.
2. `combatState.AddCreature` → `CombatManager.AddCreature` → node add →
   `CombatManager.AfterCreatureAdded`. `CreatureCmd.cs:68-71`.
3. If `combatState.CurrentSide != Enemy && creature.IsMonster` →
   `creature.PrepareForNextTurn(players, rollNewMove: false)` — a monster
   spawned during the **player's** turn immediately prepares its next turn
   *without* rolling a new move. `CreatureCmd.cs:72-75`.
4. Run-history `MonsterIds` bookkeeping. `CreatureCmd.cs:76-80`. Waiver.
5. `Hook.AfterCreatureAddedToCombat(combatState, creature)`. `CreatureCmd.cs:81`.

### `CreatureCmd.Escape` — `CreatureCmd.cs:579-603`

6. Guard: `creature.IsDead` → no-op. `CreatureCmd.cs:581-584`.
7. Guard: `CombatState == null || !IsLiveCombat()` → no-op. `CreatureCmd.cs:585-588`.
8. `creature.RemoveAllPowersInternalExcept()` — removes **every** power off the
   escaper via `PowerModel.RemoveInternal()`, i.e. **silently**: unlike death
   (`CreatureCmd.cs:533-537`, which awaits each power's `AfterRemoved`), escape
   fires no `AfterRemoved`. `CreatureCmd.cs:589`; `Creature.cs:658-666`.
9. Node teardown. `CreatureCmd.cs:590-599`. Waiver.
10. `CombatManager.RemoveCreature(creature)` + `CombatState.CreatureEscaped(creature)`.
    **No hook fires for an escape at all.** `CreatureCmd.cs:600-601`.

### `CreatureCmd.GainBlock` — `CreatureCmd.cs:617-664`

11. Guard: `CombatManager.IsOverOrEnding` → return `0`. `CreatureCmd.cs:637-640`.
12. Event: `Hook.BeforeBlockGained(combatState, creature, amount, props, card)`
    — unconditional, with the **raw** amount, before any modifier.
    `CreatureCmd.cs:642`; `Hook.cs:131-137`.
13. `Hook.ModifyBlock`: the card's **enchantment** modifies first
    (`EnchantBlockAdditive` then `EnchantBlockMultiplicative`), then an
    additive chain over every combat hook listener, then a multiplicative
    chain over every listener, collecting the ones that actually changed the
    value. Both chains thread the **running** `decimal`: `decimal num2 =
    item.ModifyBlockAdditive(target, num, …); num += num2;`
    (`Hook.cs:1322-1323`) then `decimal num3 =
    item2.ModifyBlockMultiplicative(target, num, …); num *= num3;`
    (`Hook.cs:1331-1332`) — each contribution folded in immediately and the
    next listener handed the folded value. **There is no props gate at the
    pipeline level** — every listener is called for every block gain and
    self-gates. `CreatureCmd.cs:644`; `Hook.cs:1310-1340`. See guard **G1**
    for the gate and **clause (c)** of the record's step 13 for the
    aggregation shape (`hook_dispatch`'s gap **G9**).
14. `modifiedAmount = Math.Max(modifiedAmount, 0)`. `CreatureCmd.cs:645`.
15. Event: `Hook.AfterModifyingBlockAmount(combatState, modifiedAmount, card,
    cardPlay, modifiers)` — fires only for the listeners that changed the
    value. `CreatureCmd.cs:646`; `Hook.cs:649-656`. See guard **G2**.
16. `if (modifiedAmount > 0)`: sfx/vfx, `creature.GainBlockInternal(modifiedAmount)`
    (clamped at 999,999,999 — `Creature.cs:459-466`), history, wait.
    `CreatureCmd.cs:647-661`.
17. Event: `Hook.AfterBlockGained(combatState, creature, modifiedAmount, props,
    card)` — **unconditional**, fires even when the modified amount is 0.
    `CreatureCmd.cs:662`; `Hook.cs:143-149`.

### `CreatureCmd.LoseBlock` — `CreatureCmd.cs:666-678`

18. Guards `!IsOverOrEnding && !creature.IsDead && amount > 0`;
    `LoseBlockInternal` (floors at 0, `Creature.cs:468-475`); if block was
    `> 0` and is now `<= 0` → sfx + `Hook.AfterBlockBroken`.
    `CreatureCmd.cs:668-677`.

### `CreatureCmd.Heal` — `CreatureCmd.cs:691-755`

19. Guard: `CombatManager.IsEnding && !creature.IsPlayer` → return.
    **There is no dead guard.** `CreatureCmd.cs:693-696`.
20. `creature.HealInternal(amount)` → `SetCurrentHpInternal(CurrentHp + amount)`,
    clamped at `MaxHp`; if the creature *was* dead and now is not, the player's
    hooks are re-activated and the `Revived` event fires. `CreatureCmd.cs:703`;
    `Creature.cs:477-491`. See guard **G4**.
21. Anim/vfx/history. `CreatureCmd.cs:704-750`. Waiver.
22. Event: `if (amount > 0 && creature.CombatState != null)
    Hook.AfterCurrentHpChanged(..., amount)` — gated on and carrying the
    **raw requested amount**, not the clamped heal. `CreatureCmd.cs:751-754`.
    See guard **G5**.

### `CreatureCmd.SetCurrentHp` — `CreatureCmd.cs:762-779`

23. `SetCurrentHpInternal(amount)` (clamped at MaxHp); if it changed →
    revive anim + `Hook.AfterCurrentHpChanged(delta)`; then
    `if (creature.IsDead) await Kill(creature)` — setting HP to 0 runs the
    full death pipeline. `CreatureCmd.cs:764-778`.

### `CreatureCmd.GainMaxHp` / `SetMaxHp` / `SetMaxAndCurrentHp` — `CreatureCmd.cs:786-860`

24. `GainMaxHp`: throw on a negative amount; `SetMaxHp(MaxHp + amount)`
    returns the **actual** delta; history; `Heal(creature, delta)`.
    `CreatureCmd.cs:788-798`.
25. `SetMaxHp`: `SetMaxHpInternal(Math.Max(0, amount))` — clamps CurrentHp
    down to the new MaxHp (`Creature.cs:493-501`); `if (MaxHp <= 0) Kill`;
    returns `newMaxHp - oldMaxHp`. `CreatureCmd.cs:841-848`.
26. `SetMaxAndCurrentHp`: `SetMaxHp` then `SetCurrentHp`.
    `CreatureCmd.cs:858-859`.

### `CreatureCmd.LoseMaxHp` — `CreatureCmd.cs:811-828`

27. Throw on a negative amount; run-history bookkeeping.
    `CreatureCmd.cs:813-822`.
28. `newMaxHp = MaxHp - amount` — **not floored here**. If
    `newMaxHp < CurrentHp` → `Damage(choiceContext, creature,
    CurrentHp - newMaxHp, Unblockable|Unpowered (+ Move when isFromCard),
    null, null)`: the difference is dealt through the **full damage pipeline**,
    so it fires the damage hooks and can kill. `CreatureCmd.cs:823-826`.
    See guard **G6**.
29. **Then** `SetMaxHp(creature, Math.Max(1, newMaxHp))` — the max-HP floor is
    applied *after* the damage, so it never shrinks the damage.
    `CreatureCmd.cs:827`.

### `CreatureCmd.Stun` — `CreatureCmd.cs:870-904`

30. `creature.StunInternal(wrapper, nextMoveId)`: **throws** if the creature is
    not a monster ("Can't stun a player"); no-ops if `CombatState == null ||
    IsDead`; an empty `nextMoveId` defaults to the **last performed move's id**
    from `Monster.MoveStateMachine.StateLog`; installs a `"STUNNED"`
    `MoveState` with `MustPerformOnceBeforeTransitioning = true` via
    `SetMoveImmediate`. Nothing about turn start/end is touched.
    `CreatureCmd.cs:886`; `Creature.cs:524-542`.

### `PlayerCmd` — energy, stars, gold, potion slots — `PlayerCmd.cs:29-294`

31. `GainEnergy`: guards `amount <= 0` and `CombatManager.IsEnding`;
    `Hook.ModifyEnergyGain(out modifiers)` → `Hook.AfterModifyingEnergyGain(modifiers)`;
    then `if (finalAmount > 0)` sfx + `GainEnergy(finalAmount)` — a modifier
    that drives the amount to zero or below adds nothing. `PlayerCmd.cs:31-42`.
32. `LoseEnergy` guards `amount <= 0` / `IsEnding`; `SetEnergy` routes through
    `GainEnergy`/`LoseEnergy`, so raising energy by `SetEnergy` runs the whole
    modifier chain. `PlayerCmd.cs:50-83`.
33. `GainStars` / `LoseStars` / `SetStars` (`Hook.ShouldGainStars`,
    `Hook.AfterStarsGained`). `PlayerCmd.cs:90-133`. Waiver — the star
    resource belongs to the Regent, not the Ironclad.
34. `GainGold`: `Hook.ModifyGoldGained(out modifiers)` →
    `Hook.AfterModifyingGoldGained(modifiers, amount)` → `if (!(amount > 0))
    return` → sfx + run-history (`GoldStolen` when `wasStolenBack`, else
    `GoldGained`) → `player.Gold += (int)amount` → `Hook.AfterGoldGained`.
    `PlayerCmd.cs:143-169`. See guard **G12**.
35. `LoseGold`: sfx, run-history keyed by `GoldLossType`
    (Spent/Lost/Stolen — Stolen also `MarkLootStolen`), then
    `Gold = max(0, Gold - (int)amount)` — truncating, floored at 0.
    `PlayerCmd.cs:180-198`. `SetGold` routes through Gain/Lose
    (`PlayerCmd.cs:207-218`).
36. `GainMaxPotionCount` / `LoseMaxPotionCount` → `Player.AddToMaxPotionCount` /
    `SubtractFromMaxPotionCount`. `PlayerCmd.cs:220-230`.
37. `AddPet<T>` / `AddPet` — `PlayerCmd.cs:237-257`. Waiver, no pet system.
38a. `MimicRestSiteHeal` → `HealRestSiteOption.ExecuteRestSiteHeal`
    (`PlayerCmd.cs:264-274`, `HealRestSiteOption.cs:106-113`):
    `CreatureCmd.Heal(GetHealAmount)` → `Hook.AfterRestSiteHeal(player,
    isMimicked)` → `Hook.ModifyRestSiteHealRewards` →
    `RewardsCmd.OfferCustom`. **Not a delegation stub — it runs two hooks**,
    and its one gameplay caller (`Events/DenseVegetation.cs:90`) is ported.
    See the fix-pass gap below.
38b. `EndTurn` (`PlayerCmd.cs:279-289`) is `turn_structure`'s (Task 8);
    `CompleteQuest` (`PlayerCmd.cs:291-294`) writes only
    `CompletedQuests` run-history. Waiver.

### `CardCmd.AutoPlay` — `CardCmd.cs:51-137`

39. Guard: `CombatManager.IsOverOrEnding || card.Owner.Creature.IsDead` →
    return. `CardCmd.cs:53-56`.
40. Guard: `card.Keywords.Contains(Unplayable)` →
    `MoveToResultPileWithoutPlaying` = `CardPileCmd.Add(card, PileType.Play)`
    then `card.MoveToResultPileWithoutPlaying(...)` — the card still transits
    the **Play** pile. `CardCmd.cs:58-62, 133-137`.
41. Guard: `!Hook.ShouldPlay(combatState, card, out preventer, type)` →
    same result-pile move plus the preventer's dialogue bubble.
    `CardCmd.cs:63-72`.
42. `TargetType.AnyEnemy` with no target → `card.Owner.RunState.Rng.CombatTargets
    .NextItem(combatState.HittableEnemies)`; still null → result-pile move.
    `CardCmd.cs:73-84`.
43. `TargetType.AnyAlly` → `Rng.CombatTargets.NextItem(other living player
    allies)`. `CardCmd.cs:85-97`. Waiver, multiplayer.
44. Unless `skipXCapture`: `card.EnergyCost.CapturedXValue = playerCombatState
    .Energy` for X-cost cards (**captured, not spent**), and `LastStarsSpent`
    for star costs. `CardCmd.cs:99-113`.
45. `if (card.Pile == null) await CardPileCmd.Add(card, PileType.Play)` — the
    Play-pile move happens **only** for a card that has no pile; a card already
    in a pile is left there and moved by `OnPlayWrapper`. `CardCmd.cs:114-117`.
46. `Hook.BeforeCardAutoPlayed(combatState, card, target, type)` — a hook
    distinct from `BeforeCardPlayed`. `CardCmd.cs:122`.
47. `ResourceInfo { EnergySpent = 0, EnergyValue = cost, StarsSpent = 0,
    StarValue = ... }` then `card.OnPlayWrapper(..., isAutoPlay: true, ...)`.
    `CardCmd.cs:123-130`.

### `CardCmd.Discard` / `DiscardAndDraw` — `CardCmd.cs:147-205`

48. Guard `IsOverOrEnding`; empty list → return. `CardCmd.cs:174-182`.
49. Per card, **in order**: collect it if `IsSlyThisTurn`; `CardPileCmd.Add(card,
    discardPile)` — the move happens **first** — then history, then
    `Hook.AfterCardDiscarded(combatState, choiceContext, card)`. Each card's
    hook runs before the next card is moved. `CardCmd.cs:186-195`.
    See guard **G11**.
50. `discardPile.InvokeContentsChanged()`, then `CardPileCmd.Draw(cardsToDraw)`
    — the draw happens **after every discard hook**, which is the whole point
    of `DiscardAndDraw` over discard-then-draw. `CardCmd.cs:196-200`.
51. Finally, `AutoPlay(..., AutoPlayType.SlyDiscard)` for each collected Sly
    card. `CardCmd.cs:201-204`.

### `CardCmd.Downgrade` / `Upgrade` — `CardCmd.cs:212-314`

52. `Downgrade`: guard `IsEnding`; deck-pile history; `card.DowngradeInternal()`.
    `CardCmd.cs:214-222`.
53. `Upgrade`: guard `IsEnding`; skip any card with `!IsUpgradable`; deck-pile
    history; `UpgradeInternal()` **then** `FinalizeUpgradeInternal()`; preview
    VFX. `CardCmd.cs:267-313`.

### `CardCmd.Transform` — `CardCmd.cs:323-509`

54. Guard `IsEnding`; empty set → empty result. `CardCmd.cs:371-379`.
55. Pass 1, per transformation: `AssertMutable`; `!IsTransformable` → throw;
    `Pile == null` → throw; record `pile.Cards.IndexOf(original)`;
    `item.GetReplacement(rng)` (null → throw); `original.RemoveFromCurrentPile()`.
    `CardCmd.cs:382-404`.
56. Sort the recorded tuples by `(pile type, original index)` — `PileIndexSort`,
    `CardCmd.cs:353-360, 405`.
57. Pass 2, per transformation, **Deck pile only**:
    `Hook.ModifyCardBeingAddedToDeck(runState, replacement, out modifyingModels)`
    (may substitute a different card — this is the egg relics' hook),
    `replacement.FloorAddedToDeck = runState.TotalFloor`, run-history
    `CardsTransformed`. `CardCmd.cs:427-435`. See guard **G3**.
58. **Placement.** `PileType.Deck` → `pile2.AddInternal(replacement2)` — no
    index, so `CardPile.AddInternal`'s `index = -1` default **appends at the
    deck's end**. Every other pile → `pile2.AddInternal(replacement2, item4)`,
    re-inserting at the original's recorded index, plus history `CardGenerated`
    and `Hook.AfterCardEnteredCombat`. `CardCmd.cs:436-446`; `CardPile.cs:83-97`.
59. `Hook.AfterCardChangedPiles(runState, combatState, replacement, pile.Type,
    null)` → `pile.InvokeCardAddFinished()` → `original.AfterTransformedFrom()`
    → `replacement.AfterTransformedTo()`. `CardCmd.cs:447-450`.
60. Transform VFX / shine. `CardCmd.cs:453-498`. Waiver.
61. Tail pass: for every replacement now in a combat pile,
    `Hook.AfterCardGeneratedForCombat`; then `original.RemoveFromState()`.
    `CardCmd.cs:499-507`.

### `CardCmd.Enchant` / `ClearEnchantment` — `CardCmd.cs:518-568`

62. `AssertMutable`; `!enchantment.CanEnchant(card)` → throw; no existing
    enchantment → `card.EnchantInternal(enchantment, amount)` +
    `enchantment.ModifyCard()`; same type → `Amount += (int)amount`;
    **different** type → throw; then `FinalizeUpgradeInternal()` and deck-pile
    history. `CardCmd.cs:534-558`.

### `CardCmd.Afflict` — `CardCmd.cs:613-669`

63. Guard: `IsOverOrEnding` **and** the card is in a combat pile → null (an
    out-of-combat card can still be afflicted while combat ends).
    `CardCmd.cs:627-634`.
64. Guard: `combatState == null || !Hook.ShouldAfflict(combatState, card,
    affliction)` → null. `CardCmd.cs:636-640`.
65. Guard: `!affliction.CanAfflict(card)` → null. `CardCmd.cs:641-644`.
66. No existing affliction → `card.AfflictInternal(affliction, amount)` then
    `affliction.AfterApplied()`; same type → `Amount += (int)amount`;
    **different** type → throw. Then history. `CardCmd.cs:645-659`.
    `ClearAffliction` → `card.ClearAfflictionInternal()`. `CardCmd.cs:666-669`.

### `CardCmd` keyword / preview helpers — `CardCmd.cs:676-887`

67. `ApplyKeyword` / `RemoveKeyword` / `ApplySingleTurnSly` mutate the card and
    refresh its node. `Preview*` / `PreviewInternal` / `FlashRelics` are pure
    presentation. `CardCmd.cs:676-887`. Waiver except the keyword mutation.

### `CardPileCmd.RemoveFromDeck` — `CardPileCmd.cs:42-81`

68. Per card: `Pile.Type != Deck` → throw; run-history `CardsRemoved`;
    `Hook.BeforeCardRemoved`; `card.RemoveFromCurrentPile()`; preview;
    `card.RemoveFromState()`. `CardPileCmd.cs:54-80`.

### `CardPileCmd.RemoveFromCombat` — `CardPileCmd.cs:90-191`

69. Per card: must be in a combat pile else throw; record the old pile;
    `RemoveFromCurrentPile()`. Then tweens. Then, per card,
    `Hook.AfterCardChangedPiles(..., oldPile.Type, null)` and
    `card.RemoveFromState()`. `CardPileCmd.cs:104-190`.

### `CardPileCmd.AddGeneratedCardsToCombat` — `CardPileCmd.cs:216-249`

70. Guards: empty → empty; `!IsInProgress` → empty; any card that already has a
    pile → throw; a non-combat target pile → throw; `combatState == null` →
    empty. Then per card: history `CardGenerated` → `Add(card, pile, position)`
    → `Hook.AfterCardGeneratedForCombat`. `CardPileCmd.cs:218-248`.

### `CardPileCmd.Add` — `CardPileCmd.cs:306-639` (the core pile verb)

71. Guard: empty → empty. Guard: `newPile.IsCombatPile && IsEnding` → every
    result `success = false`. `CardPileCmd.cs:308-319`.
72. Per-card validation pass: no owner → throw;
    `HasBeenRemovedFromState || owner.Creature.IsDead || (IsInCombat &&
    CombatState == null)` → `success = false` (silently dropped, not thrown);
    a Deck add whose card is not in the RunState → throw; a combat add whose
    card is not in the CombatState → throw; a preview card → throw; mixed
    owners → throw. `CardPileCmd.cs:322-377`.
73. Deck pile only: `Hook.ShouldAddToDeck(runState, card, out preventer)` —
    true → run-history `CardsGained` + `card.FloorAddedToDeck = TotalFloor`;
    false → `preventer.AfterAddToDeckPrevented(card)` and `success = false`.
    `CardPileCmd.cs:379-397`.
74. Guard: combat pile while combat is not in progress → return early (results
    kept, nothing moved); no successful result → return.
    `CardPileCmd.cs:398-405`.
75. **Full-hand redirect**: if the target pile is `Hand` and it already holds
    `>= CardPile.MaxCardsInHand` (10) cards, the target is silently switched to
    the owner's **Discard** pile. `CardPileCmd.cs:419-423`; `CardPile.cs:21`.
76. Node/visual classification (`cardNodes`, `cardsWithoutNodesChangingPiles`).
    `CardPileCmd.cs:424-491`. Waiver.
77. `if (oldPile != null) card.RemoveFromCurrentPile(skipVisuals)` — **else if**
    the target is the Deck, `Hook.ModifyCardBeingAddedToDeck` may swap in a
    different card (recorded in the result). The two are mutually exclusive:
    a card moving *between* piles never re-runs the deck-entry hook.
    `CardPileCmd.cs:492-509`.
78. `targetPile.AddInternal(card, position switch { Bottom => -1, Top => 0,
    Random => card.Owner.RunState.Rng.Shuffle.NextInt(targetPile.Cards.Count + 1) })`
    — the Random slot is drawn from the **Shuffle** stream, and `AddInternal`
    throws if the pile already contains that instance. `CardPileCmd.cs:510-516`;
    `CardPile.cs:83-107`.
79. `if (oldPile == null && targetPile.IsCombatPile) Hook.AfterCardEnteredCombat`
    — fires only for a card entering combat from nowhere, not for pile-to-pile
    moves. `CardPileCmd.cs:517-520`.
80. Hand-full thought bubble; visuals; tweens. `CardPileCmd.cs:521-629`. Waiver.
81. Per successful result: `Hook.AfterCardChangedPiles(runState, combatState,
    card, oldPile?.Type ?? PileType.None, clonedBy)` — **after every card has
    moved**, not interleaved. `CardPileCmd.cs:630-637`. See guard **G8**.

### `CardPileCmd.AddDuringManualCardPlay` — `CardPileCmd.cs:647-684`

82. Guard `IsOverOrEnding`; the card must be in the CombatState else throw;
    `card.RemoveFromCurrentPile()`; `PileType.Play.GetPile(owner).AddInternal(card)`
    — the card lives in the **Play** pile for the whole of `OnPlay`; tween;
    `Hook.AfterCardChangedPiles(..., oldPile?.Type ?? None, null)`.
    `CardPileCmd.cs:649-683`. This is seed fact 1's mechanism.

### `CardPileCmd.Draw` — `CardPileCmd.cs:798-857`

83. Guard `IsOverOrEnding` → empty. `CardPileCmd.cs:800-803`.
84. `Hook.ShouldDraw(combatState, player, fromHandDraw, out modifier)` —
    evaluated **once, before the loop**; on false, `Hook.AfterPreventingDraw(modifier)`
    and return empty. `CardPileCmd.cs:804-808`. See guard **G9**.
85. `drawsRequested = count > 0 ? ceil(count) : 0`; 0 → empty. If the hand has
    no room at all → thought bubble and return. `CardPileCmd.cs:813-823`.
86. Loop `drawsRequested` times, breaking on: no hand room, `IsOverOrEnding`,
    or `CheckIfDrawIsPossible...` false (draw + discard both empty, or hand
    full). `CardPileCmd.cs:824-837`.
87. `await ShuffleIfNecessary(choiceContext, player)` then **re-check**
    `CheckIfDrawIsPossible...` — a shuffle-triggered effect that drains the
    pile stops the draw. `CardPileCmd.cs:838-842`.
88. `card = drawPile.Cards.FirstOrDefault()` (index 0 = top); null or hand full
    → break. `CardPileCmd.cs:843-847`.
89. `await Add(card, hand)` — the full `Add` pipeline, so the drawn card also
    gets `AfterCardChangedPiles`; then history `CardDrawn`,
    `Hook.AfterCardDrawn(card, fromHandDraw)`, `card.InvokeDrawn()`, recompute
    hand room. `CardPileCmd.cs:848-855`.

### `CardPileCmd.Shuffle` / `ShuffleIfNecessary` — `CardPileCmd.cs:864-981`

90. Guard `IsOverOrEnding`. `CardPileCmd.cs:866-869`.
91. `list = discardPile.Cards.ToList()`, then `list.AddRange(drawPile.Cards)` —
    **discard first, current draw pile second**; the draw pile's existing
    contents are part of the shuffled set. `CardPileCmd.cs:871-875`.
92. `list.StableShuffle(player.RunState.Rng.Shuffle)` — sort into canonical
    order (so the result is independent of incoming order), then Fisher-Yates
    consuming `Count - 1` draws. `CardPileCmd.cs:876`; `ListExtensions.cs:22-60`.
93. `Hook.ModifyShuffleOrder(combatState, player, list, isInitialShuffle: false)`
    — mutates the shuffled list **in place, before any card is placed**, and
    therefore strictly before `AfterShuffle`. `CardPileCmd.cs:877`.
    See guard **G10**.
94. Silently empty the draw pile (`RemoveInternal(item, silent: true)`).
    `CardPileCmd.cs:878-881`.
95. Debug forced-top-card override. `CardPileCmd.cs:882-890`. Waiver.
96. Re-add in list order: a card that came from the **discard** goes through the
    full `Add(item, drawPile)` (hooks and all) with a per-card wait; a card that
    was already in the draw pile is re-seated with
    `AddInternal(item, -1, silent: true)`. `CardPileCmd.cs:892-913`.
97. Wait, then `if (!IsOverOrEnding) Hook.AfterShuffle(combatState,
    choiceContext, player)`. `CardPileCmd.cs:914-918`.
98. `ShuffleIfNecessary` shuffles **only** when the draw pile is empty *and*
    the discard pile is not. `CardPileCmd.cs:972-981`.

### `CardPileCmd.AutoPlayFromDrawPile` and the remaining helpers — `CardPileCmd.cs:931-1071`

99. `AutoPlayFromDrawPile`: guard `IsOverOrEnding`; per count →
    `ShuffleIfNecessary` → pick `Bottom`/`Top`/`Rng.CombatCardSelection.NextItem`
    → `Add(card, PileType.Play)`; **then** play each collected card with
    `ExhaustOnNextPlay = forceExhaust`, stopping as soon as the owner is dead.
    `CardPileCmd.cs:933-965`.
100. `AddToCombatAndPreview<T>`: dead owner → return; create `count` cards on
     the CombatState and route each through `AddGeneratedCardToCombat`; then
     preview. `CardPileCmd.cs:1005-1035`.
101. `AddCurseToDeck` / `AddCursesToDeck`: non-Curse → throw; create on the
     RunState; `Add(card, PileType.Deck)`; preview.
     `CardPileCmd.cs:1042-1056`.

### `CardPile` internals — `CardPile.cs`

102a. `MaxCardsInHand => 10` (`CardPile.cs:21`); `AddInternal`'s index
     semantics — `index < 0` appends, `>= 0` inserts (`CardPile.cs:83-107`).
102b. `RandomizeOrderInternal` (the combat-start draw-pile randomize) is
     `UnstableShuffle` — Fisher-Yates with **no** stabilizing sort — followed
     by `Hook.ModifyShuffleOrder(isInitialShuffle: true)`
     (`CardPile.cs:69-74`). The second half is **G10**'s gap.
102c. `AddInternal` **throws** if the pile already contains that `CardModel`
     instance (`CardPile.cs:86-89`) and `RemoveInternal` **throws** if the
     card is absent (`CardPile.cs:115-132`). This is **N4**, and the mechanism
     behind **G7**.

### `CardSelectCmd` — `CardSelectCmd.cs`

103a. 0 eligible candidates → empty (the deck/grid screens also
     `ReportSoftlock`). `CardSelectCmd.cs:194-199, 277-285, 382-394, 694-707`.
103b. Every selection screen **also** guards `CombatManager.IsEnding` /
     `IsOverOrEnding` → empty, at the same call sites. The sim has no such
     check anywhere in `CombatState.select_cards`; see **G14**.
104. **Auto-select shortcut**: `!prefs.RequireManualConfirmation &&
     candidateCount <= prefs.MinSelect` → return **all** candidates with no
     player choice at all. `CardSelectCmd.cs:287-290, 396-399, 708-711`.
105. Otherwise the `Selector` (test/AI hook) is asked for `MinSelect..MaxSelect`
     cards; for a **Draw** pile the candidate list is first re-ordered
     `orderby c.Rarity, c.Id`, hiding the true draw order from the chooser.
     `CardSelectCmd.cs:400-410, 712-715`.
106. Local screen / remote-choice synchronisation, `LogChoice`.
     `CardSelectCmd.cs:411-431, 716-732`. Waiver — presentation/multiplayer.

## Sim comparison (Step C summary — full verdicts in the JSON)

The sim spreads the counterpart across four files: `cmds.py` holds
`BlockCmd`/`CreatureCmd`/`ExhaustCmd`/`CardCmd`/`CardPileCmd`/`CardSelectCmd`/
`EnergyCmd`/`DrawCmd`; `player.py` holds the draw/shuffle/discard verbs;
`run.py` holds the deck and gold verbs; `combat.py` holds auto-play and the
Play-pile limbo marker. Two structural differences run through the whole
record:

- **There is no `CardPile` object.** Piles are plain Python lists, so every
  `CardPileCmd.Add` invariant that lives in `AddInternal` (duplicate-instance
  throw, index semantics, subscription bookkeeping) and every result-object
  path (`success = false` for a dead owner or a removed card) has no analogue;
  each sim helper hand-rolls its own move.
- **There is no unified `AfterCardChangedPiles`.** The sim has one hook per
  transition (`on_card_drawn`, `on_card_discarded`, `on_card_exhausted`,
  `on_card_entered_combat`) plus a deck-only relic shim
  (`Relic.after_card_added_to_deck`), and nothing that sees an arbitrary
  pile-to-pile move.

**Verdict counts** — *re-recomputed in fix pass 2, 2026-07-26*
(`collections.Counter` over `steps + guards` of
`audit/records/seam/creature_card_cmds.json`):

```
steps    (110): gap 53, faithful 33, waiver 13, deliberate-divergence 11
guards   ( 25): gap 20, waiver 3, deliberate-divergence 2
combined (135): gap 73, faithful 33, waiver 16, deliberate-divergence 13
unit verdict: "gap"  (= max(all verdicts, key=VERDICTS.index))
```

**Unchanged by fix pass 2.** That pass added clause (c) to step 13 and a scope
sentence to guard **G1**; both entries were already `gap`, no entry was added,
split or re-verdicted, so every count above is identical to fix pass 1's and
the rollup still equals `max(verdicts)`.

The first pass recorded `steps (106): faithful 35, gap 33, waiver 20, dd 18` /
`guards (24): gap 13, dd 8, waiver 3` / `combined (130): gap 46, faithful 35,
dd 26, waiver 23`. The fix pass split three steps into per-clause entries
(38 → 38a/38b, 102 → 102a/102b/102c, 103 → 103a/103b), added guard **G14**,
and re-verdicted 24 entries — every change moved *up* the precedence ladder
except step 44 and step 92, which kept `faithful` and gained explanatory
rationale. The two governing rules applied throughout:

- **`waiver` means out of scope** (multiplayer, presentation/animation,
  ascension values). It does **not** mean "nothing currently triggers this"
  and it does **not** mean "the C# side is unported". A divergence no ported
  content triggers is a **dormant gap**; dormancy describes today's content,
  not the divergence's shape.
- **A guard rollup carries `max(verdict)` of the steps it aggregates.** Six
  `N`-guards sat below their own steps and were raised (**N2**, **N3**,
  **N4**, **N5**, **N9**, **N10**).

**Gaps found** (short form; full text in the JSON). **Five** are live on
currently-ported content — **G1**, **G2**, **G3**, and the two the fix pass
found, step **38a** (`MimicRestSiteHeal`) and step **52** (`Downgrade`); the
rest are dormant with the trigger named. *Fix pass 2 (2026-07-26) added one
more dormant entry, **clause (c) of step 13** — `hook_dispatch`'s gap **G9** at
the block site — narrated with the other step-level gaps below; the live count
is still five.*

- **G1 — block modifiers are gated at the pipeline level on
  `is_powered_attack`. LIVE.** `BlockCmd.apply` (`cmds.py:145-147`) skips the
  entire `modify_block_additive`/`modify_block_multiplicative` dispatch unless
  `props` is `Move && !Unpowered`. C#'s `Hook.ModifyBlock` (`Hook.cs:1310-1340`)
  calls **every** listener for **every** block gain and leaves the gate to each
  implementation — and while Dexterity, Frail and Fasten do self-gate on
  `IsPoweredCardOrMonsterMoveBlock` (`DexterityPower.cs:33`, `FrailPower.cs:28`,
  `FastenPower.cs:27`), **`Vambrace.cs:59-63` and `PaelsLegion.cs:132-134`
  self-gate only on `IsCardOrMonsterMove()`**, which is `Move` alone and
  ignores `Unpowered` (`ValuePropExtensions.cs:22-25`). Both sides are ported:
  `Entrench` gains block with `MOVE | UNPOWERED` in the sim
  (`cards/trash_heap_cards.py:159-179`) exactly as in C# (`Entrench.cs:23`),
  and `Vambrace` is a ported Uncommon relic (`relics/vambrace.py`). Verified by
  execution: player at 10 Block holding Vambrace plays Entrench → sim gains
  **10** (C# gains 20); the control powered card block (Defend 5 → **10**)
  shows the doubling is otherwise wired up. Pinned with a strict xfail.
- **G2 — no `AfterModifyingBlockAmount` machinery; Vambrace's latch is
  hand-rolled onto the wrong event. LIVE.** `Hook.ModifyBlock` returns
  `out modifiers` and `CreatureCmd.cs:646` notifies exactly the listeners that
  changed the value (`Hook.cs:649-656`); the sim's block modifier hooks
  (`hooks.py:98-124`) return a bare aggregate with no companion event — the
  same shape as `power_cmd`'s G4. All **three** current C# listeners on that
  event are ported (`Vambrace.cs:78-90`, `PaelsLegion.cs:146-158`,
  `FastenPower.cs:36-40`), and Vambrace's port hand-rolls the latch onto
  `on_block_gained` (`relics/vambrace.py:36-40`), setting its once-per-combat
  `_used` flag on the **first** block gain. C# instead latches only
  `TriggeringCard = cardSource` there and burns `BlockGainedThisCombat` in
  `AfterCardPlayed` (`Vambrace.cs:92-105`), so **every** block instance of the
  same card play is doubled. Ported witnesses that gain block more than once
  per play: `Evil Eye` (`cards/evil_eye.py:37-42`, two gains after an exhaust)
  and `Second Wind` (`cards/second_wind.py:34-39`, one gain per exhausted
  non-Attack). Verified by execution: two `BlockCmd.apply` calls carrying the
  same `card=` yield **10 then 5**; C# yields 10 then 10. Pinned with a
  strict xfail.
- **G3 — a deck transform bypasses the entire card-entering-the-deck pipeline.
  LIVE.** `CardCmd.Transform` runs `Hook.ModifyCardBeingAddedToDeck`
  (`CardCmd.cs:430`), sets `FloorAddedToDeck` (433) and fires
  `Hook.AfterCardChangedPiles` (447) for Deck-pile transforms — the same two
  hooks `CardPileCmd.Add` runs (`CardPileCmd.cs:501, 635`). The sim's
  `RunState.transform_card` (`run.py:459-469`) deletes the original and
  `append`s the replacement directly, never routing through `add_card`
  (`run.py:341-354`), which is where both sim-side hooks live. Verified by
  execution: holding **Frozen Egg**, `add_card(Inflame)` yields
  `upgrade_level 1` but `transform_card(..., into=Inflame)` yields
  `upgrade_level 0`; holding **Bing Bong**, `add_card` grows the deck by 2 but
  `transform_card` adds 0 clones. Every participant is ported — the three egg
  relics, Bing Bong, Book of Five Rings, Darkstone Periapt on one side, and
  Pandora's Box / Astrolabe / Wood Carvings / Morphic Grove / Symbiote as
  deck transformers on the other. Pinned with a strict xfail.
  *Fix pass:* the third thing `CardCmd.Transform` does at that site,
  `replacement.FloorAddedToDeck = runState.TotalFloor` (`CardCmd.cs:433`), is
  **not** part of this gap — it is read nowhere in the game except the save
  serializers (`SerializableCard.cs:32-69`) and the run-history screens
  (`NDeckHistory.cs:93-94`, `NMapPointHistory.cs:76-78`), i.e. telemetry with
  no gameplay reader, which is exactly how step 73 treats it. The two entries
  now agree.
- **G4 — `CreatureCmd.heal` refuses to heal a dead creature; C#'s `Heal`
  revives. Dormant (the one ported caller hand-rolls around it).**
  `cmds.py:160-161` early-returns 0 on `target.is_dead`; `CreatureCmd.Heal`
  guards only `IsEnding && !IsPlayer` (`CreatureCmd.cs:693-696`) and
  `HealInternal` raises CurrentHp and fires `Revived` when it crosses 0
  (`Creature.cs:477-486`). Verified: healing a 0-HP retained creature returns
  0 and leaves it at 0 HP. The only ported site that needs a corpse heal —
  `ReattachPower.DoReattach`, literally `CreatureCmd.Heal(Owner, Amount)` in
  C# (`ReattachPower.cs:47`) — bypasses the Cmd with a direct
  `owner.hp = self.amount` assignment (`powers.py:2360-2365`), so the two net
  the same today. Live the moment a second corpse-heal is ported, or the
  moment anyone routes Reattach back through `CreatureCmd.heal`.
- **G5 — `Heal` reports the raw amount, and reports it even at full HP.
  Dormant.** `CreatureCmd.cs:751-754` fires `AfterCurrentHpChanged` when the
  **requested** `amount > 0`, carrying that same raw amount; the sim
  (`cmds.py:162-166`) fires `on_hp_changed(target, healed)` only when the
  **clamped** heal is positive. Verified: healing 20 on a player 3 below max
  reports delta **3** in the sim (C#: 20); healing at full HP reports nothing
  (C#: reports +amount). Dormant because the only ported `on_hp_changed`
  listener, Red Skull (`relics/red_skull.py:44-46`), ignores the delta and
  recomputes idempotently; it becomes live when any delta-reading
  `AfterCurrentHpChanged` listener is ported.
- **G6 — `lose_max_hp` never routes through the damage pipeline and can never
  kill. Dormant.** `CreatureCmd.LoseMaxHp` computes an **unfloored**
  `newMaxHp = MaxHp - amount` and, when that is below CurrentHp, deals
  `CurrentHp - newMaxHp` as `Unblockable | Unpowered` damage
  (`| Move` when `isFromCard`) through the full pipeline — hooks, death check,
  `Kill` — and only afterwards floors MaxHp at 1 (`CreatureCmd.cs:823-827`).
  The sim (`cmds.py:179-189`) floors max HP first and clamps HP with a bare
  `on_hp_changed`, so no `on_damage_received`, `should_die` or `on_death` ever
  fires and the creature cannot die of max-HP loss. Verified: a 10/10 player
  losing 30 max HP ends alive at 1/1; C# would deal 30 unblockable damage and
  kill. Dormant: the in-combat callers are Brightest Flame
  (`cards/brightest_flame.py:37`) and `PaperCutsPower` (`powers.py:2959`),
  neither of which reaches a fatal magnitude, and the `isFromCard` `Move`
  flag exists for Rupture-style triggers that are unported.
- **G7 — `ExhaustCmd.exhaust` only knows about the hand and the discard pile.
  Dormant.** `cmds.py:379-384` removes the card from `hand` or
  `discard_pile` and appends it to `exhaust_pile`; a card in the draw pile,
  the exhaust pile, or mid-play ends up in **two** piles at once. Re-run
  2026-07-25 with the observed values: a Strike placed alone in the draw pile
  and passed to `ExhaustCmd.exhaust` ends with `card in draw_pile` **True**
  and `card in exhaust_pile` **True**, `len(draw_pile) == 1`,
  `len(exhaust_pile) == 1`; a Strike already in the exhaust pile and exhausted
  again ends with `len(exhaust_pile) == 2` holding the same instance twice.
  Both states are exceptions in the game. C# routes through
  `CardPileCmd.Add(card, PileType.Exhaust, Bottom)` whose
  `RemoveFromCurrentPile()` is pile-agnostic (`CardPileCmd.cs:496`) and whose
  `AddInternal` throws outright if the target already holds the instance
  (`CardPile.cs:86-89`). Dormant: all twelve ported callers pass hand cards
  (spot-checked `cinder.py:40-45`, `true_grit.py:48-55`, `second_wind.py:38`,
  `paels_eye.py:44-46`).
- **G8 — no `Hook.AfterCardChangedPiles` at all. Dormant for combat piles.**
  Every C# pile move funnels through it (`CardPileCmd.cs:635, 188, 683`;
  `CardCmd.cs:447`). The sim has per-transition hooks plus the deck-only
  `Relic.after_card_added_to_deck` shim (`relics/base.py:208-210`). All four
  ported C# listeners filter to `pile.Type == Deck` (`BingBong.cs:31`,
  `BookOfFiveRings.cs:84`, `DarkstonePeriapt.cs:19`, `LuckyFysh.cs:27`), so
  the shim covers them except on the transform path (**G3**); the three C#
  listeners that watch combat piles — `SovereignBlade`, `Hoarder`,
  `SoulFysh` — are unported. Porting any of those three makes this live.
- **G9 — `should_draw` is re-evaluated per drawn card, and there is no
  `after_preventing_draw`. Dormant.** `CardPileCmd.Draw` evaluates
  `Hook.ShouldDraw` exactly once, before the loop, and fires
  `Hook.AfterPreventingDraw` on refusal (`CardPileCmd.cs:804-808`); the sim's
  `_draw` calls `should_draw` inside the per-card loop (`player.py:280-281`).
  Same result while every listener is stateless — Fiddle
  (`relics/fiddle.py:26-31`) is the only ported one and is — but a listener
  that flips mid-draw would truncate the draw in the sim and be ignored
  entirely in C#. `AfterPreventingDraw`'s only C# implementation is a
  `Flash()` (`Fiddle.cs:36-40`), i.e. presentation.
- **G10 — `ModifyShuffleOrder` modelled as an `AfterShuffle` listener.
  Dormant.** C# mutates the shuffled list **inside** the shuffle, before any
  card is placed and strictly before `AfterShuffle`
  (`CardPileCmd.cs:876-877` vs `917`; and `CardPile.cs:69-74` for the
  combat-start randomize, which the sim's `_shuffle_draw_pile(stable=False)`
  also does not hook). The sim has no `modify_shuffle_order` hook at all:
  `PerfectFitEnchantment` hand-rolls it on `on_shuffle`
  (`enchantments.py:186-189`). The net effect is the same *only* while
  registration order happens to put Perfect Fit after the other `on_shuffle`
  listeners; C# guarantees it by call sequence, the sim does not. Re-run
  2026-07-25 with the observed values: (1) `modify_shuffle_order` does not
  exist in `sts2_rl/hooks.py`; the only `on_shuffle` definitions in the sim
  are `hooks.py:433` (the dispatcher), `enchantments.py:186` (Perfect Fit),
  `powers.py:3736`, `relics/biiig_hug.py:28` and `relics/the_abacus.py:22`.
  (2) With Biiig Hug (the ported `on_shuffle` listener that mutates the draw
  pile — it adds a Soot) and Perfect Fit on a Bash in the same combat, an
  8-card discard reshuffled to
  `['strike','soot','strike','defend','strike','strike','defend','defend','bash']`
  (top last) — the Perfect Fit card **did** land on top, with registration
  order `[BiiigHug, PerfectFitEnchantment]`, so **no collision is
  demonstrated**; nothing in the sim's architecture prevents one if the order
  were reversed. (3) The initial-shuffle variant has **no sim surface at
  all**: wrapping the hook system across `_shuffle_draw_pile(stable=False)`
  records **zero** hook invocations. Recorded at step level as **102b** (the
  fix pass split it out of the old step 102, whose blanket `faithful`
  contradicted this guard).
- **G11 — `AfterCardDiscarded` fires before the card has moved, and in a
  batch. Dormant.** C# adds each card to the discard pile *first*, then fires
  the hook, one card at a time (`CardCmd.cs:186-195`). `discard_hand` fires
  `on_card_discarded` for every flushed card while they are **all** still in
  `hand` and none is in `discard_pile` (`player.py:192-196`). Re-run
  2026-07-25 with the observed values: flushing a hand of `[Strike, Defend]`
  with a spy listener records
  `[('strike', in_hand=True, in_discard=False), ('defend', in_hand=True,
  in_discard=False)]` at hook time, where C# would give `(False, True)` for
  each and would have moved Strike before Defend's hook ran. Dormant in the
  strongest possible sense: a walk of every `.py` under `sts2_rl/` finds
  `def on_card_discarded` in exactly **one** file, `hooks.py` (the
  dispatcher) — **zero** listeners, so nothing can observe it today.
- **G12 — no `Hook.AfterGoldGained`, and no gold-gain hook surface at all.**
  `PlayerCmd.GainGold` fires `Hook.ModifyGoldGained` →
  `Hook.AfterModifyingGoldGained` → `Hook.AfterGoldGained`
  (`PlayerCmd.cs:144-169`). `RunState.gain_gold` (`run.py:325-333`) runs a
  relic `modify_gold_gained` loop and nothing else. Its one ported C#
  listener, `DragonFruit.cs:22-29` (+1 Max HP per gold gain), is consequently
  a no-op stub in the sim (`relics/dragon_fruit.py`, whose docstring still
  claims "no gold system" although `run.gold` exists) — as is `LuckyFysh`
  (`relics/lucky_fysh.py`) for the same reason on the `AfterCardChangedPiles`
  side. The relics' own stubbing is a Tier-1 relic-audit item; the missing
  hook surface is this seam's.
- **G13 — `CreatureCmd.escape` does not remove the escaper's powers. Dormant.**
  `Escape` calls `RemoveAllPowersInternalExcept()` (`CreatureCmd.cs:589`),
  stripping every power *silently* — `RemoveInternal()` with no `AfterRemoved`
  (`Creature.cs:658-666`), the deliberate contrast with death, which does
  await `AfterRemoved` (`CreatureCmd.cs:533-537`). The sim's `escape`
  (`cmds.py:221-234`) sets `escaped = True`, fires an invented
  `on_creature_escaped` hook (C# fires nothing) and leaves every power
  registered as a live hook listener. Dormant: the three ported escape sites
  (`monsters/hive/thieving_hopper.py:125`,
  `monsters/underdocks/gremlin_merc.py:137`, `powers.py:2928`) leave behind
  only owner-scoped powers (`SwipePower`, `FlutterPower`,
  `BattlewornDummyTimeLimitPower`), each of which self-filters on
  `is self.owner`. It becomes live for any escaping monster holding a power
  with a global (non-owner-scoped) hook.

- **G14 — the combat-over / `IsEnding` guard family has no sim counterpart
  anywhere. Dormant.** *Added in fix pass 1* to give **one** treatment to a
  mechanism the first pass verdicted three different ways. Every C# command in
  this seam opens with a liveness check (`IsOverOrEnding` / `IsEnding` /
  `!IsLiveCombat()`) and returns empty/zero/no-op: `CreatureCmd.Add` (55-67),
  `Escape` (585-588), `GainBlock` (637-640), `LoseBlock` (668), `Heal`
  (693-696), `CardCmd.AutoPlay` (53-56), `Discard` (174-177), `Downgrade`
  (214), `Upgrade` (269), `Transform` (371-374), `Afflict` (627-634),
  `CardPileCmd.Add` (308-319, 398-401), `AddDuringManualCardPlay` (649),
  `Draw` (800-803), `Shuffle` (866-869, 914-918), `AutoPlayFromDrawPile`
  (933), and every `CardSelectCmd` screen (194-199, 277-285, 382-394,
  694-707). **The sim reproduces exactly one of them** —
  `CombatState.auto_play_card` (`combat.py:525`), which is why step 39 stays
  `faithful`. Every other site is unguarded and is now a dormant gap: steps
  **1, 7, 11, 48, 54, 63, 71, 72, 74, 83, 90, 103b**. Dormant as a family for
  one structural reason: the sim sets `Phase.COMBAT_OVER` only inside
  `_end_combat`, which the card-play paths reach strictly *after*
  `_resolve_card_play` returns (`combat.py:417-420` manual, `554-557`
  auto), so no ported effect can be mid-resolution with the phase already
  flipped. Verified by execution on the one site the reviewer probed: with
  `phase = Phase.COMBAT_OVER`, `select_cards("exhaust", [Strike, Defend], 1)`
  returns **1 card (`[Defend]`)** where every C# screen returns empty. Pinned
  with a strict xfail. Cross-referenced by `damage_pipeline`'s **G5** and
  `power_cmd`'s **G6**.
- **Step 38a — `MimicRestSiteHeal` skips both rest-site-heal hooks. LIVE.**
  *Found in fix pass 1; the first pass waived this as "rest-site
  delegation".* `PlayerCmd.MimicRestSiteHeal` (`PlayerCmd.cs:264-274`) is not
  a stub: it delegates to `HealRestSiteOption.ExecuteRestSiteHeal`
  (`HealRestSiteOption.cs:106-113`), which heals and **then** fires
  `Hook.AfterRestSiteHeal(player, isMimicked)` and
  `Hook.ModifyRestSiteHealRewards`, offering the resulting rewards. Its one
  gameplay caller, `Events/DenseVegetation.cs:90`, is ported — but the sim's
  `DenseVegetation._rest` (`events/dense_vegetation.py:65-68`) calls
  `run.heal(run.rest_site_heal_amount())` **directly**, bypassing
  `RunState.rest_heal` (`run.py:1089-1095`, which does fire
  `after_rest_site_heal`) and `RunState.rest_heal_rewards`
  (`run.py:1097-1110`, which does fire `modify_rest_site_heal_rewards`). Both
  listener sides are ported: **Stone Humidifier**
  (`relics/stone_humidifier.py:15-16`, +5 Max HP, mirroring
  `StoneHumidifier.cs:18-25`) and **Dream Catcher**
  (`relics/dream_catcher.py:22-25`, a 3-card Monster-room reward, mirroring
  `DreamCatcher.cs:16-25`). Verified by execution on a string-seeded run
  holding Stone Humidifier at 40/80 HP: Dense Vegetation's Rest gives
  `max_hp 80 → 80`, `hp 40 → 64`, where `RunState.rest_heal()` on the
  identical run gives `max_hp 80 → 85`, `hp 40 → 69`. Pinned with a strict
  xfail.
- **Step 52 — `CardCmd.Downgrade` does not re-apply the card's enchantment.
  LIVE.** *Found in fix pass 1; the first pass waived this as "no ported
  content downgrades a card … the sim has no downgrade verb", which was wrong
  on both clauses.* `DampenPower.cs:35` calls `CardCmd.Downgrade` and
  `DampenPower` is ported (`powers.py:3149-3183`, applied by the Magi Knight's
  `DAMPEN_MOVE`, `monsters/glory/knights.py:69-72`); `Reflections.cs:43` is a
  second ported caller (`events/reflections.py:36-41`); and the sim's verb is
  `Card.downgrade` (`cards/base.py:150-165`). Step by step against
  `CardCmd.cs:212-223` + `CardModel.DowngradeInternal`
  (`CardModel.cs:2135-2147`): the `IsEnding` guard is **G14**'s family
  (dormant); the deck-pile history is telemetry; `CurrentUpgradeLevel = 0`
  (reset to *base form*) versus the sim's one-level drop is **dormant**, since
  `Card.max_upgrade_level` is 1 for all 168 upgradable cards and 0 for the 35
  status/curse cards, so the two coincide; but `DowngradeInternal`'s tail —
  `AfterDowngraded(); Enchantment?.ModifyCard(); Affliction?.AfterApplied();`
  — has **no** sim counterpart, and the sim's `_init_vars()` rebuild
  *un-does* the enchantment's card mutation. Verified by execution:
  Discovery's `_init_vars` sets `self.exhausts = True`
  (`cards/colorless_skills.py:211-213`); attaching the ported Souls
  enchantment (`enchantments.py:209-212`, from the ported Grave of the
  Forgotten event) clears it; after `upgrade()` then `downgrade()` the sim
  reports `exhausts == True` **with Souls still attached**, where C# would
  re-run Souls' `ModifyCard` and leave Exhaust removed. Prolong
  (`colorless_skills.py:486-491`) and two more Exhaust-toggling colorless
  skills have the same shape. Pinned with a strict xfail.
- **Step 26 — `SetMaxAndCurrentHp` has no sim verb and two ported callers
  hand-roll around it. Dormant.** *Re-verdicted in fix pass 1; the first pass
  waived it on a false unreachability claim ("no ported caller … multiplayer
  HP scaling and boss setup").* The C# callers are
  `DecimillipedeSegment.cs:142`, `ToughEgg.cs:173` and
  `WaterfallGiant.cs:305`, and **the first two are ported**:
  `monsters/hive/decimillipede.py:68` and `:167` do a raw
  `max_hp = hp = …`, and `monsters/hive/ovicopter.py:81-83` does the same for
  the Tough Egg hatchling. The raw assignment skips `SetMaxHpInternal`'s
  CurrentHp clamp (`Creature.cs:493-501`), `SetMaxHp`'s `MaxHp <= 0 → Kill`
  (`CreatureCmd.cs:844-847`), and `SetCurrentHp`'s `AfterCurrentHpChanged` +
  trailing death pipeline (`CreatureCmd.cs:766-778`). Dormant, verified by
  execution: both ports assign `max_hp` and `hp` together so the clamp cannot
  differ; every ported amount is strictly positive (segments come out
  **46/44/42**, the hatchling rolls Niche 19–21) so neither `Kill` is
  reachable; and while Ovicopter *does* hand-roll the event
  (`ctx.hooks.on_hp_changed(self, delta)`) and Decimillipede fires **nothing**
  (confirmed with a spy listener — zero calls), the only `on_hp_changed`
  listener in the sim is Red Skull (`relics/red_skull.py:44-46`), which
  early-returns unless `creature is self.player`, and both callers are
  monsters.
- **Step 104 — the auto-select shortcut costs RNG draws the game never
  takes.** *Raised from `deliberate-divergence` in fix pass 1.* C#'s shortcut
  (`!RequireManualConfirmation && candidateCount <= MinSelect` → return every
  candidate in pile order, `CardSelectCmd.cs:287-290, 396-399, 708-711`)
  consumes **nothing** from any stream. The sim has no shortcut: `select_cards`
  clamps `count = min(count, len(candidates))` (`combat.py:577`) and, with no
  `card_selector` installed, falls through to
  `self._rng.sample(candidates, count)` (`combat.py:581`) — which both burns
  draws C# never takes *and* takes them off-stream. Under seed parity a
  differing draw count is an observable desync, so the same membership reached
  by a different route is not enough to keep this a `deliberate-divergence`.
  See step 105 for the off-stream fallback itself.
- **Step 13, clause (c) — the block modifiers are aggregated in parallel where
  C# threads a running value. Dormant.** *Added in fix pass 2; this is
  `hook_dispatch`'s gap **G9** and `damage_pipeline`'s guard **N3**, the same
  mechanism carried to its third and last site (rule 3: one verdict per
  mechanism at every site, including across records). Beware the name clash —
  **G9** here always means `hook_dispatch`'s; this record's own **G9**
  (`should_draw`) is unrelated.* **Confirmed, not assumed:**
  `Hook.ModifyBlock` (`Hook.cs:1320-1337`) has exactly the shape of
  `Hook.ModifyDamageInternal` (`Hook.cs:2515-2538`) — two sequential `foreach`
  loops over `IterateCombatHookListeners`, `num += num2` then `num *= num3`,
  each contribution folded into the running `decimal` immediately — and the
  sim has exactly the damage site's parallel shape: `hooks.py:98-109` sums
  every listener's additive return against the same pre-step base,
  `hooks.py:111-122` multiplies every listener's factor together in **float**,
  and `cmds.py:145-147` applies each aggregate once
  (`amount = amount + hooks.modify_block_additive(...)` then
  `amount = int(amount * hooks.modify_block_multiplicative(...))`). Same
  divergence, same verdict: **gap**. **Dormant here** where the damage site is
  live, evidence executed:
  1. The base-vs-running *argument* is inert at this site too —
     `py audit/tools/dormancy_probes.py cs-running-value` finds **0 of 46** C#
     `Modify{Damage,Block}{Additive,Multiplicative}` overrides reading the
     value they are handed, **10** of those 46 being the block pair
     (`DexterityPower.cs:20`, `FastenPower.cs:20`; `FrailPower.cs:22`,
     `NoBlockPower.cs:30`, `ShadowmeldPower.cs:24`, `UnmovablePower.cs:21`,
     `PaelsLegion.cs:134`, `Vambrace.cs:57`, `VitruvianMinion.cs:34`,
     `MultiplayerScalingModel.cs:52`) — and `sim-running-value` finds **0 of
     31** sim implementations reading theirs.
  2. The block **additive** family is therefore exactly equal over integers.
  3. The block **multiplicative** family is *also* equal today, unlike
     damage's, because every reachable block factor is **binary-exact
     (dyadic)** and a float product of dyadic factors equals the sequential
     decimal fold bit for bit. An AST enumeration of `sts2_rl` finds exactly
     five ported implementations — Frail ×0.75 (`powers.py:452`), Unmovable ×2
     (`powers.py:1105`), No Block ×0 (`powers.py:3673`), Pael's Legion ×2
     (`relics/paels_legion.py:36`), Vambrace ×2 (`relics/vambrace.py:26`) —
     factor set `{0.0, 0.75, 2.0}`; an exhaustive sweep of all **15** ordered
     subsets × bases 0–999 finds **0 mismatches** between `int(base × product)`
     (sim), the sequential decimal fold (game) and a sequential-float control.
     Executed end-to-end through the real pipeline: a player holding the
     ported **Vambrace** with 1 **Frail** gaining 5 card block gets **7** in
     the sim and **7** in the game (`5m × 2m = 10m`, `10m × 0.75m = 7.5m`,
     `GainBlockInternal` truncates to 7, `Creature.cs:459-466`; sim
     `2.0 × 0.75 == 1.5` exactly, `int(5 × 1.5) == 7`) — where the damage
     site's Shrink ×0.7 + Vulnerable ×1.5 gives **20 vs 21**.

  **Concrete trigger:** any block multiplier whose factor is *not*
  binary-exact. None exists in single-player content — all 8 C#
  `ModifyBlockMultiplicative` overrides return dyadic values
  (`FrailPower.cs:32` `0.75m`, `NoBlockPower.cs:44` `0m`,
  `ShadowmeldPower.cs:30` `2^Amount`, `UnmovablePower.cs:40` `2m`,
  `PaelsLegion.cs:152` `2m`, `Vambrace.cs:79` `2m`, `VitruvianMinion.cs:48`
  `2m`) and the **only** non-dyadic block factor anywhere in the decompiled
  source is `MultiplayerScalingModel.cs:52-68`
  (`playerCount × {1.1m, 1.2m, 1.3m}`), which `hook_dispatch`'s note **N1**
  waives as multiplayer. So the named unported thing that would make this site
  live is a block multiplier returning a non-dyadic factor: a port of the
  MultiplayerScalingModel factor, or new content mirroring the damage side's
  ×0.7 Shrink shape onto block. **Not pinned by a test**, for exactly that
  reason — with today's ported content the two shapes cannot be made to
  disagree, so a strict xfail would XPASS. The mechanism's one pin lives at
  the damage site
  (`test/test_hook_order.py::TestHookDispatchOrder::test_multiplicative_damage_modifiers_chain_sequentially`).

**The `N`-guards.** Fix pass 1 raised six of these to `gap` (**N2**, **N3**,
**N4**, **N5**, **N9**, **N10**) because a guard rollup must carry
`max(verdict)` of the steps it aggregates — each of the six sat below its own
step and therefore read as non-actionable. Their explanatory text is unchanged
except for the added note of which steps each aggregates. Full rationale in
the JSON.

*Now `gap`:* **N2** `CardCmd.afflict` skips the `IsOverOrEnding` guard,
`Hook.ShouldAfflict` (no C# override exists) and `CanAfflict`, and returns
`None` on a type mismatch where C# throws — aggregates steps 63-66, three of
which are gaps. **N3** the whole `CardPileAddResult` failure surface (dead
owner, removed-from-state card, `ShouldAddToDeck` prevention) has no sim
analogue — aggregates steps 70-74, all gaps. **N4** no duplicate-instance
guard on any sim pile insert — this is **G7**'s mechanism and step **102c**.
**N5** `EnergyCmd.gain` lacks C#'s `finalAmount > 0` guard, so a negative
modifier would subtract energy; the only ported `modify_energy_gain` listener
returns `0` (`powers.py:554-557`) — word-for-word step 31's claim, which is a
gap. **N9** the sim has no Play pile: `_resolve_card_play` puts the played
card straight into the discard pile and marks `player._playing_card`
(`combat.py:452-454`); the reshuffle exclusion is **parity-only** (a genuine
deliberate decision, see **N11**), but the undemonstrated exposure it carries
— an effect counting the discard pile during its own `OnPlay` — is a dormant
gap, and it aggregates step 82, which is a gap. **N10** `CardSelectCmd`'s
auto-select shortcut and draw-pile `orderby Rarity, Id` have no sim
counterpart, and `select_cards`' random fallback draws on the shared legacy
`self._rng` rather than `combat_rng.card_selection` (`combat.py:575-581`) —
aggregates steps 104 and 105, both gaps.

*Still `deliberate-divergence`:* **N1** `CreatureCmd.stun` accepts any
creature, including the player and a dead one, where `StunInternal` throws /
no-ops (its step, 30, is also `dd`; the move-machine half is Task 10's — see
the Task 10 boundary above). **N11** the parity-only card-ordering rules.

*Still `waiver` — genuinely out of scope:* **N6** stars are the Regent's
resource and the sim is Ironclad-only. **N7** pets: `PlayerCmd.AddPet<T>` and
the whole `PetOwner` plumbing, cross-referenced by `damage_pipeline`'s
already-shipped Osty waivers (steps 10 and 15 of that record) — kept a waiver
here so the two seams do not disagree; if a later pass re-verdicts it, both
records must move together. **N8** VFX/SFX/history/screen-shake/preview/
thought-bubble paths and the whole local/remote `PlayerChoiceSynchronizer`
layer.

## Existing test coverage (Step D)

- **Play-limbo reshuffle exclusion** (pin table item 1): no existing test
  covers it. `test/test_ancients.py:582-585` and
  `test/test_underdocks_hive_events.py:640-644` both call
  `reshuffle_discard_into_draw` directly but with no card mid-play, and
  `test/test_colorless.py:690` / `test/test_ironclad_final_cards.py:370-380`
  exercise reshuffle-during-draw without the limbo marker. New pin added:
  `test/test_hook_order.py::TestCreatureCardCmdsOrder::
  test_card_mid_play_is_excluded_from_a_reshuffle_it_triggers`.
- **Transform appends at deck end** (pin table item 2): the existing
  `test/test_events.py::test_transform_replaces_in_place_with_pool_card`
  pins the **legacy** in-place behaviour (`run.deck[3] is replacement`) on a
  `fresh_run()` with no string seed, which is the opposite of the parity rule.
  New pin added for the parity path:
  `test/test_hook_order.py::TestCreatureCardCmdsOrder::
  test_deck_transform_appends_at_the_end_under_parity`.
- **G1 (unpowered card block skips the block modifiers)**: new strict xfail,
  `test/test_hook_order.py::TestCreatureCardCmdsOrder::
  test_unpowered_card_block_still_runs_block_modifiers`.
- **G2 (Vambrace latches on the first gain instead of on the card play)**: new
  strict xfail, `test/test_hook_order.py::TestCreatureCardCmdsOrder::
  test_vambrace_doubles_every_block_gain_of_one_card_play`.
- **G3 (deck transform bypasses the deck-entry hooks)**: new strict xfail,
  `test/test_hook_order.py::TestCreatureCardCmdsOrder::
  test_deck_transform_runs_modify_card_being_added_to_deck`.
- **GainBlock hook order** (not a pin-table item, but the record's ordering
  claim for steps 12-17): new order-tracing test,
  `test/test_hook_order.py::TestCreatureCardCmdsOrder::
  test_gain_block_hook_order`.

### Pins added in fix pass 1 (2026-07-25)

Three of the fix pass's verdict changes are pinnable and were unpinned; each
got a `strict=True` xfail in the same class:

- **G14 / step 103b** (`select_cards` has no combat-over guard):
  `test_select_cards_refuses_once_the_combat_is_over`.
- **Step 52** (`Downgrade` does not re-apply the card's enchantment):
  `test_downgrade_reapplies_the_cards_enchantment`.
- **Step 38a** (`MimicRestSiteHeal`'s hooks skipped on Dense Vegetation's
  Rest): `test_dense_vegetation_rest_fires_the_rest_site_heal_hooks`.

`py -m pytest test/test_hook_order.py -q` → **9 passed, 9 xfailed**; forced
with `--runxfail` all nine fail at their stated assertions.

### Pins added in fix pass 2 (2026-07-26)

**None, deliberately.** Fix pass 2's only new finding is clause (c) of step 13
(`hook_dispatch`'s gap **G9** at the block site) and it is **dormant**: every
ported block multiplier returns a binary-exact factor, so the sim's float
product and C#'s sequential decimal fold agree on all 15 ordered subsets of
`{0.0, 0.75, 2.0}` × bases 0–999. A `strict=True` xfail asserting the game's
number would therefore **XPASS**, which the pipeline treats as a failure. The
mechanism stays pinned once, at the live damage site
(`TestHookDispatchOrder::test_multiplicative_damage_modifiers_chain_sequentially`),
and this record's clause (c) names the unported trigger instead: a block
multiplier with a non-dyadic factor.

### Sim-side follow-up for Perry (not an audit finding)

`sts2_rl/player.py:253-258` — `_shuffle_draw_pile`'s docstring says the
stabilizing sort compares "the sim card `id` … a lowercase slug whose ordinal
order matches the game Entry ordinal". It does not: the code passes
`_compare_to_key`, which **uppercases** first
(`return (card.id.upper(), card.upgrade_level)`, `player.py:34`), precisely
because an ordinal compare puts `_` (0x5F) after the uppercase letters but
before the lowercase ones. `_compare_to_key`'s own docstring
(`player.py:23-33`) is correct, and so is the code — step 92's `faithful`
stands. Only the prose misleads, and engine files are outside this task's
edit scope, so it is recorded here and in the JSON at step 92 rather than
fixed.
