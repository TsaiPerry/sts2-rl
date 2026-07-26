# Engine seam: `creature_card_cmds`

Audited 2026-07-25 (Task 7 of the six seam audits, Tier 2 of the
source-audit-pipeline design). Verdicts and rationale live in
`audits/seam/creature_card_cmds.json`; this file is the durable ordering spec
extracted from the C# source that the JSON record judges the sim against.

This seam is the *rest of the command layer*: every creature verb that is not
the damage pipeline (add / escape / block / heal / max-HP / stun), the player
resource verbs (energy / gold / stars / potion slots), and the whole card and
card-pile layer (auto-play, discard, exhaust, upgrade, transform, enchant,
afflict, pile add/remove, draw, shuffle, card selection).

## Source correction (Step A)

`tools/audit/harness.py`'s `SEAM_SOURCES["creature_card_cmds"]` listed four C#
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
`audits/seam/creature_card_cmds.json`.

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
    value. **There is no props gate at the pipeline level** — every listener is
    called for every block gain and self-gates. `CreatureCmd.cs:644`;
    `Hook.cs:1310-1340`. See guard **G1**.
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
38. `MimicRestSiteHeal`, `EndTurn`, `CompleteQuest`. `PlayerCmd.cs:264-294`.
    `EndTurn` is `turn_structure`'s (Task 8); the other two are waiver.

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

102. `MaxCardsInHand => 10` (`CardPile.cs:21`); `RandomizeOrderInternal` (the
     combat-start draw-pile randomize) is `UnstableShuffle` — Fisher-Yates with
     **no** stabilizing sort — followed by
     `Hook.ModifyShuffleOrder(isInitialShuffle: true)` (`CardPile.cs:69-74`);
     `AddInternal` throws on a duplicate instance and `index < 0` appends
     (`CardPile.cs:83-107`); `RemoveInternal` throws if the card is absent
     (`CardPile.cs:115-132`).

### `CardSelectCmd` — `CardSelectCmd.cs`

103. Every selection screen guards `CombatManager.IsEnding` / `IsOverOrEnding`
     → empty, and 0 eligible candidates → empty (the deck/grid screens also
     `ReportSoftlock`). `CardSelectCmd.cs:194-199, 277-285, 382-394, 694-707`.
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

**Verdict counts** (recomputed directly from
`audits/seam/creature_card_cmds.json`):

```
steps    (106): faithful 35, gap 33, waiver 20, deliberate-divergence 18
guards   ( 24): gap 13, deliberate-divergence 8, waiver 3
combined (130): gap 46, faithful 35, deliberate-divergence 26, waiver 23
unit verdict: "gap"  (= max(all verdicts, key=VERDICTS.index))
```

**Gaps found** (short form; full text in the JSON). Three are **live on
currently-ported content**; the rest are dormant with the trigger named.

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
  the exhaust pile, or mid-play ends up in **two** piles at once — verified by
  execution against a draw-pile card. C# routes through
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
  listeners; C# guarantees it by call sequence, the sim does not. Executed
  with Perfect Fit + Biiig Hug together (the one ported `on_shuffle` listener
  that mutates the draw pile): the Perfect Fit card did land on top, so **no
  collision is demonstrated** — but nothing in the sim's architecture prevents
  one.
- **G11 — `AfterCardDiscarded` fires before the card has moved, and in a
  batch. Dormant.** C# adds each card to the discard pile *first*, then fires
  the hook, one card at a time (`CardCmd.cs:186-195`). `discard_hand` fires
  `on_card_discarded` for every flushed card while they are **all** still in
  `hand` and none is in `discard_pile` (`player.py:192-196`) — verified,
  `(in_hand, in_discard) == (True, False)` at hook time. Dormant in the
  strongest possible sense: a grep of `sts2_rl/` finds **zero**
  `on_card_discarded` listeners, so nothing can observe it today.
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

**Lower-severity / no-current-effect notes** (`deliberate-divergence` or
`waiver`, full rationale in the JSON): **N1** `CreatureCmd.stun` accepts any
creature, including the player and a dead one, where `StunInternal` throws /
no-ops. **N2** `CardCmd.afflict` skips `Hook.ShouldAfflict` (no C# override
exists), `CanAfflict` and `AfterApplied`, and returns `None` on a type
mismatch where C# throws. **N3** the whole `CardPileAddResult` failure surface
(dead owner, removed-from-state card, `ShouldAddToDeck` prevention) has no sim
analogue — no C# override of `ShouldAddToDeck`/`AfterAddToDeckPrevented`
exists. **N4** no duplicate-instance guard on any sim pile insert. **N5**
`EnergyCmd.gain` lacks C#'s `finalAmount > 0` guard, so a negative modifier
would subtract energy; the only ported `modify_energy_gain` listener returns
`0` (`powers.py:554-557`). **N6** stars are Regent-only. **N7** pets are
unported. **N8** VFX/SFX/history/screen-shake/preview/thought-bubble paths and
the whole local/remote `PlayerChoiceSynchronizer` layer. **N9** the sim has no
Play pile: `_resolve_card_play` puts the played card straight into the discard
pile and marks `player._playing_card` (`combat.py:452-454`); the resulting
reshuffle exclusion is **parity-only**, so legacy runs still shuffle the
in-flight card back into the draw pile (verified by execution). **N10**
`CardSelectCmd`'s auto-select shortcut and draw-pile `orderby Rarity, Id` have
no sim counterpart, and `CombatState.select_cards`' random fallback draws on
the shared legacy `self._rng` rather than the `combat_rng.card_selection`
stream (`combat.py:575-581`).

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
