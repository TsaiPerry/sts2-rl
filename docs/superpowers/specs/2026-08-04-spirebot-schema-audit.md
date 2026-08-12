# SpireBot obs-schema audit: combat v6 → v7, run v9 → v10

Field-by-field disposition for every segment of the CURRENT combat and run
observation schemas, walked from code (`sts2_rl/full_env.py`,
`sts2_rl/run_env.py`), not just `OBS_SCHEMA.md`. This is the implementation
spec for Tasks 3–4 (the schema bump) and Tasks 11–12 (the C# `ObsBuilder`).

**Dispositions**
- **KEEP** — the C# mod can read this directly from live game state; a
  concrete API path is named.
- **DROP** — no game-readable equivalent exists (sim-internal only); a
  one-line justification is given.
- **REDEFINE** — a close game-readable proxy exists but is not identical to
  the sim's current computation; the proxy is stated exactly.
- **ACCUMULATE** — needs cross-turn/cross-decision memory the mod must
  maintain itself (session state), because the game does not expose a
  running counter for it.

Sources walked: `sts2_rl/full_env.py` (`combat_obs_segments_i/_f`,
`write_combat_obs`, `card_features`, `_enemy_floats`,
`_enemy_intent_history_floats`, `_power_aux`, `_relic_rows`,
`combat_action_masks`), `sts2_rl/run_env.py` (`run_obs_segments_i/_f`,
`_build_obs`), `sts2_rl/relic_obs.py`, `sts2_rl/driver.py` (`DecisionKind`,
`DecisionRequest.own_actions`/`potion_actions`), `OBS_SCHEMA.md` §§2–7,
Task 1's damage-preview verdict doc, `RunReplays/GameStateSnapshot.cs`,
`RunReplays/ReplayDispatcher.cs`, and the decompiled game source under
`Slay the Spire 2/src` (`PlayerCombatState.cs`, `CombatHistory.cs`,
`RelicModel.cs`, `Hook.cs`, `DynamicVar*.cs`) for API existence checks.

---

## Step 1/2 — Combat observation (v6)

### 1.1 Int half (`combat_obs_segments_i`)

| segment | field | disposition | game source | notes |
|---|---|---|---|---|
| `player.powers.ids` | power id (×`MAX_POWERS_PLAYER`=32 rows) | KEEP | `player.Creature.Powers[i].Id` (`Creature.Powers` — an ordered `List<PowerModel>`, `GameStateSnapshot.cs` already reads it) | vocab `powers`; oldest-first = C#'s own list order |
| `player.relics.ids` | relic id (×`MAX_RELIC_ROWS`=48) | KEEP | `player.Relics[i].Id` (`GameStateSnapshot.cs`: `player.Relics`) | acquisition order |
| `hand.ids` | `card_id` (×`MAX_HAND`=10) | KEEP | `combat.Player.PlayerCombatState.Hand.Cards[h].Id` | positional row = hand slot h |
| `hand.ids` | `affliction_id` | KEEP | `CardModel.Affliction?.Id` (affliction vocab, new v6) | PAD if none |
| `hand.ids` | `enchantment_id` | KEEP | `CardModel.Enchantment?.Id` (enchantment vocab, new v6) | PAD if none |
| `enemies.ids` | monster id (×`MAX_ENEMIES`=6) | KEEP | `combatState.Enemies[e].Monster`'s class / `EnemyInfo.Name`-equivalent typed id (`combatState.Enemies` already read by `GameStateSnapshot.cs`) | positional row = enemy slot e; PAD if slot gone/absent (`!e.IsAlive` / `e.IsGone`) |
| `enemy{e}.powers.ids` (×6 slots, `MAX_POWERS_ENEMY`=16 each) | power id | KEEP | `combatState.Enemies[e].Powers[i].Id` (`Creature.Powers`, same accessor `GameStateSnapshot.cs` uses for `EnemyInfo.Powers`) | one segment per enemy slot, templated identically across e |
| `potions.ids` | potion id (×`MAX_POTION_ROWS`=10) | KEEP | `player.GetPotionAtSlotIndex(p)?.Id` (`ReplayDispatcher.GetAvailableCommands`'s `UsePotionCommand` loop already indexes this) | positional row = belt slot p |
| `cards.ids` | `pile_id` (×`MAX_COMBAT_CARDS`=96) | KEEP | LITERAL (1=draw,2=discard,3=exhaust), not a game field — set by which of `combat.DrawPile`/`DiscardPile`/`ExhaustPile` the card came from | mirrors `GameStateSnapshot.cs`'s three separate pile reads |
| `cards.ids` | `card_id` | KEEP | `CardModel.Id` from the owning pile's `.Cards` | sorted (§5.3 hidden-info rule) — draw-pile order must NOT be exposed; mod must sort by the same canonical key before writing |
| `cards.ids` | `affliction_id` / `enchantment_id` | KEEP | `CardModel.Affliction?.Id` / `CardModel.Enchantment?.Id` | same as hand |

### 1.2 Float half (`combat_obs_segments_f`)

| segment | field | disposition | game source | notes |
|---|---|---|---|---|
| `player.hp_ratio` | hp/max_hp | KEEP | `player.Creature.CurrentHp` / `.MaxHp` | `GameStateSnapshot.cs` already reads both |
| `player.hp_abs` (2) | fine/coarse abs | KEEP | same as above, `_abs2` scaling done in C# or on read | |
| `player.max_hp_abs` (2) | fine/coarse abs | KEEP | `player.Creature.MaxHp` | |
| `player.block_abs` (2) | fine/coarse abs | KEEP | `player.Creature.Block` | not in `GameStateSnapshot.cs` today but same `Creature` object |
| `player.energy` | energy/6 | KEEP | `combat.Energy` (`PlayerCombatState.Energy`) | |
| `player.strength` | signed(±30) | KEEP | `player.Creature.Powers.Get<StrengthPower>()?.Amount ?? 0` | |
| `player.dexterity` | signed(±30) | KEEP | `player.Creature.Powers.Get<DexterityPower>()?.Amount ?? 0` | |
| `player.pile_sizes` (4) | hand/draw/discard/exhaust counts /X | KEEP | `combat.Hand.Cards.Count`, `.DrawPile.Cards.Count`, `.DiscardPile.Cards.Count`, `.ExhaustPile.Cards.Count` | all four already read individually by `GameStateSnapshot.cs` |
| `player.turn` | turn/30 | KEEP | `PlayerCombatState.TurnNumber` (public property, `PlayerCombatState.cs:37`) | NOT `ICombatState.RoundNumber` — the doc comment at that property explicitly warns "you usually want TurnNumber instead of this" |
| `player.incoming_post_block` (2) | aggregate predicted incoming dmg minus block | KEEP (Task 1 pattern) | sum over `combatState.Enemies` of each attacking enemy's `Hook.ModifyDamage(..., target=player, ...)` (same call Task 1 verdicted KEEP for `damage_matrix`, run against the enemy's own next-move damage instead of a card) minus `player.Creature.Block` | not a single number the UI displays as one figure, but a pure function of per-enemy numbers the UI DOES display (each enemy's attack-intent icon) — same admissibility class as `damage_matrix` |
| `player.cards_played_this_turn` | count/10 | KEEP | `combat.History.Entries.OfType<CardPlayFinishedEntry>()` filtered to `RoundNumber == combat.RoundNumber` (well, `TurnNumber` — see note) and `CurrentSide == player's side` | `CombatHistory` (`Core/Combat/History/CombatHistory.cs`) is a public, generically-queryable event log — `History.Entries` is `IEnumerable<CombatHistoryEntry>`, `CombatHistoryEntry.RoundNumber`/`CurrentSide` are on the base class; this is a materially better source than the sim's own per-power private counters (`TenderPower._cardsPlayedThisTurn` is NOT public) |
| `player.attacks_this_turn` | count/10 | KEEP | `combat.History.Entries.OfType<CardPlayFinishedEntry>()` filtered to this turn AND `CardModel.CardType == CardType.Attack` | same `CombatHistory` source |
| `player.damage_taken` (2) | this-turn dmg taken, abs2 | KEEP | `combat.History.Entries.OfType<DamageReceivedEntry>()` filtered to `Receiver == player.Creature` and this turn, summed `Result.Amount` | same `CombatHistory` source |
| `player.powers.f` | `amount_fine`/`amount_coarse` (×32) | KEEP | `Creature.Powers[i].Amount` | |
| `player.powers.f` | `aux` (×32) | KEEP for the 10 admitted powers; DROP (reads 0.0) for all others by construction | the power's own `PowerModel.DisplayAmount` override (`_power_aux`'s docstring: `the_bomb.damage`, `toric_toughness.block`, `automation/panache.cards_left`, `thievery.gold_stolen`, `withering_presence._cards_left`, `hardened_shell` remaining-cap, `sloth`/`tender` cards-played, `slow` displayed amount) | `_power_aux` is the exact per-id dispatch table the C# builder must replicate 1:1 — these are the only 10 power ids where `aux` is non-zero; every other id's `aux` field is a structural 0.0, not a missing read |
| `player.relics.f` | `counter/10`, `flag` (×48) | KEEP for relics with `ShowCounter`/`Status`/`IsUsedUp`; structural 0/0 otherwise | `RelicModel.DisplayAmount` gated on `RelicModel.ShowCounter` (default false, `RelicModel.cs:347`); flag from `RelicModel.Status`/`IsUsedUp` (`relic_obs.py`'s per-relic table, §6) | 29 relics (`EXCLUDED_RELIC_STATE`) must publish 0 even though they have raw state — `fur_coat.marked_coords` (future map knowledge) and `dusty_tome.ancient_card` (unseen card) are DROP by design, not omission |
| `hand.f` | field 0 `effective_cost/6` | KEEP (Task-1-pattern) | `CardModel.DynamicVars` cost var, hook-modified — same `UpdateDynamicVarPreview`/`Hook.Modify*` call class Task 1 verdicted KEEP for damage, applied to the cost dynamic var instead | |
| `hand.f` | field 1 `energy_cost_x` flag | KEEP | `CardModel.Cost.IsX` (or equivalent X-cost flag) | |
| `hand.f` | fields 2-6 card-type one-hot | KEEP | `CardModel.CardType` | |
| `hand.f` | fields 7-11 target-type one-hot | KEEP | `CardModel.TargetType` | |
| `hand.f` | field 12 `exhausts` | KEEP | `CardModel.ExhaustsOnPlay`/keyword flag | |
| `hand.f` | field 13 `is_ethereal` | KEEP | `CardModel` Ethereal keyword | |
| `hand.f` | field 14 `is_playable` | KEEP | `CardModel.CanPlayTargeting(...)`, the exact predicate `ReplayDispatcher`'s `PlayCardCommand` enumeration already calls | |
| `hand.f` | field 15 `affordable` | KEEP | `energy_cost_x \|\| effective_cost <= combat.Energy` | derived from two already-KEEP fields |
| `hand.f` | field 16 `upgrade_level/5` | KEEP | `CardModel.UpgradeLevel` / `IsUpgraded` | |
| `hand.f` | fields 17-18 base damage abs2 | KEEP (Task-1-pattern) | `DynamicVars.Damage`/`CalculatedDamage.PreviewValue` (Task 1's call sequence, `target=null`/base) | |
| `hand.f` | field 19 `base_hits/10` | KEEP | `DynamicVars.Repeat.BaseValue` if present | Task 1's doc: `RepeatVar` has no hook pass |
| `hand.f` | fields 20-21 base/effective block | KEEP (Task-1-pattern) | `DynamicVars.Block`/`CalculatedBlock.PreviewValue` — parallel accessor Task 1's doc names as in-scope-but-unexercised | |
| `hand.f` | field 22 `base_hp_loss` | KEEP | card's HP-loss dynamic var (e.g. Blood for Blood-style costs) if present, else 0 | needs the analogous `DynamicVars` entry; verify a `HpLossVar` exists for ported HP-cost cards |
| `hand.f` | field 23 `magic_number/20` | KEEP | `CardModel.DynamicVars` magic-number var (card-specific, e.g. Feed's stack size) | |
| `hand.f` | field 24 `affliction_amount/10` | KEEP | `CardModel.Affliction.Amount` | |
| `hand.f` | field 25 `exhaust_on_next_play` | KEEP | `CardModel`'s deferred-exhaust flag (per-instance state surviving pile moves) | |
| `hand.f` | field 26 `_has_single_turn_retain` | KEEP | `CardModel`'s single-turn-Retain flag (hand-only per-instance state) | |
| `hand.f` | field 27 `_has_single_turn_sly` | KEEP | `CardModel`'s single-turn-Sly flag | |
| `hand.f` | field 28 `base_replay_count/3` | KEEP | `CardModel`'s replay-count field (Corruption/Normality-style repeat count) | |
| `enemies.f` | field 0 `presence` | KEEP | `e.IsAlive && !e.IsGone` | |
| `enemies.f` | field 1 `hp_ratio`, 2-3 hp abs2, 4-5 max_hp abs2, 6-7 block abs2 | KEEP | `Creature.CurrentHp`/`MaxHp`/`Block` | all already read by `GameStateSnapshot.cs`'s `EnemyInfo` |
| `enemies.f` | field 8 `strength` signed | KEEP | `Creature.Powers.Get<StrengthPower>()` | |
| `enemies.f` | fields 9-17 intent-flag one-hot (9 `MoveType` booleans) | KEEP | `Monster.NextMove.Intents` — `IntentType`/derived `MoveType` flags (`AbstractIntent`, `NIntent.cs`'s own display logic) | `GameStateSnapshot.cs` reads only `.FirstOrDefault()?.IntentType` today — mod needs the full intent-flag union across `Intents`, not just the first |
| `enemies.f` | fields 18-23 attack preview (per_hit, hits, total abs2, post_block abs2) | KEEP (Task 1 verdict) | `AttackIntent.GetSingleDamage`-equivalent preview path, or the same `Hook.ModifyDamage(target=player)` call used for `player.incoming_post_block`, per enemy | this is literally what the attack-intent icon displays |
| `enemies.f` | field 24 `status_count/10` | KEEP | `StatusIntent`'s displayed card count (`NIntent.cs:133-136`, `FORMAT_STATUS_CARD_COUNT`) | only set when intent is `StatusIntent` and a count is known |
| `enemy{e}.powers.f` (×6, `amount_fine/coarse`, `aux`) | same as `player.powers.f` | KEEP / structural-0 | `Creature.Powers[i].Amount`, `PowerModel.DisplayAmount` for the enemy-side admitted ids (`thievery`, `withering_presence`) | |
| `enemy{e}.intent_history.f` (×6, 3 slots × 15 floats) | `recorded` presence | **ACCUMULATE** | no game field — the mod must snapshot each enemy's displayed intent flags/preview numbers itself, once per player-turn-start, keyed by the enemy's stable id | rule: same as sim's `CombatState._roll_enemy_intents` — record the ABOUT-TO-BE-REPLACED intent right before the reroll, only if the enemy has already shown a full turn (`performed_first_move`); most-recent-first, capped at `MAX_INTENT_HISTORY`=3 |
| `enemy{e}.intent_history.f` | 9 intent flags, `per_hit`/`hits`/`total`, `status_count` | **ACCUMULATE** (same rule) | same fields as `enemies.f` 9-17/18-20/24, captured at the recording instant, not re-read live | `post_block` is deliberately excluded from the recorded slot (matches sim: it's a derived combination the sim itself doesn't retain either) |
| `damage_matrix` (60 = `MAX_HAND`×`MAX_ENEMIES`) | per-(card,enemy) hit damage | KEEP (Task 1 verdict) | `card.UpdateDynamicVarPreview(CardPreviewMode.Normal, target, card.DynamicVars)` → `DynamicVars.Damage`/`CalculatedDamage.PreviewValue`, per hand card × per living enemy | full call sequence in Task 1's doc; unplayable/untargetable cells read 0 |
| `potions.f` | targeted flag (×10) | KEEP | `PotionModel.TargetType == TargetType.AnyEnemy` (same predicate `ReplayDispatcher`'s `UsePotionCommand` enumeration uses for `needsEnemyTarget`) | |
| `cards.f` | `upgrade` | KEEP | `CardModel.IsUpgraded`/`UpgradeLevel` | |
| `cards.f` | `effective_cost` | KEEP (Task-1-pattern) | same cost dynamic var as `hand.f` field 0, but the card is not necessarily in `Hand`/`Play` pile — `UpdateDynamicVarPreview`'s `runGlobalHooks` gate (Task 1 doc) is FALSE for draw/discard/exhaust cards, so this reads the card's PLAIN printed cost, not hook-modified | **REDEFINE**: matches what `run_env._run_card_row` already does for out-of-combat cards (plain `energy_cost`, no hooks) — the sim's in-combat `cards.f` builder should be checked for consistency with this; if it currently hook-modifies non-hand cards, that itself has no game-readable equivalent and the schema bump should align it to the plain-cost reading |
| `cards.f` | `affliction_amount` | KEEP | `CardModel.Affliction.Amount` | |
| `cards.f` | `exhaust_on_next_play` | KEEP | same per-instance flag as `hand.f` field 25 | |
| every `*.overflow` (12 blocks) | truncation flag | **ACCUMULATE** | no game field — set by the mod's own writer when it truncates a block to its cap, exactly mirroring `ObsBuffer.write_rows`'s truncate-and-flag behavior | pure implementation-side bookkeeping, not a game read at all |

---

## Step 1/2 — Run observation (v9)

### 2.1 Float half (`run_obs_segments_f`, excluding the folded-in `combat.*` block already covered above)

| segment | field | disposition | game source | notes |
|---|---|---|---|---|
| `phase` (`N_PHASES` one-hot) | current `DecisionKind` | KEEP | derived from `RoomType`/active screen captures — `GameStateSnapshot.RoomType`, `CombatManager.Instance.IsInProgress`, plus which screen-capture class is live (`CardGridScreenCapture`, `ChooseACardScreenCapture`, `HandSelectionCapture`, `ReplayState.Active*` fields already used by `ReplayDispatcher.GetDispatchableTypes`) | REDEFINE in the sense that "phase" is a sim vocabulary (`DecisionKind`) with no single C# enum — the mod must build the one-hot from the SAME disjoint set of screen-state checks `GetDispatchableTypes` already performs; a 1:1 mapping table (`DecisionKind` → screen predicate) is straightforward but not a single game field |
| `run.hp_ratio`/`hp_abs`/`max_hp_abs` | | KEEP | `player.Creature.CurrentHp`/`MaxHp` | `GameStateSnapshot.cs` already reads both |
| `run.gold` (2, log1p) | | KEEP | `player.Gold` | `GameStateSnapshot.cs` already reads it |
| `run.act` / `run.floor` | | KEEP | `state.CurrentActIndex` / `state.ActFloor` | `GameStateSnapshot.cs` already reads both |
| `run.potions.f` (present, slot_exists) | | KEEP | `player.PotionSlots.Count` (slot_exists), `player.GetPotionAtSlotIndex(p) != null` (present) | |
| `run.potions.overflow` | | ACCUMULATE | mod's own truncation bookkeeping | |
| `run.deck.f` (upgrade, cost, affl_amt, exhaust_next ×`MAX_DECK_ROWS`=96) | | KEEP | `player.Deck.Cards[i]` — same list `GameStateSnapshot.cs`'s `Deck` already enumerates; cost = plain printed cost (no live `CombatState`, same rule as `cards.f`'s REDEFINE note) | |
| `run.deck.overflow` | | ACCUMULATE | | |
| `run.relics.f` (counter/10, flag ×48) | | KEEP (same admissibility as combat `player.relics.f`) | `RelicModel.DisplayAmount`/`ShowCounter`, out-of-combat gate: 10 counters are `_IN_COMBAT_ONLY_COUNTERS` and must read 0 outside combat | mod must replicate this out-of-combat suppression list, not just the base admissibility table |
| `run.relics.overflow` | | ACCUMULATE | | |
| `run.boss.f` (zero-width) | n/a | n/a | structural (no per-instance float) | |
| `run.boss.overflow` | | ACCUMULATE | | |
| `map{m}` (×`MAP_SLOTS`=7, 1+9+9) | present / point-type one-hot / child-type-count one-hot | KEEP | `NMapScreen`'s point dictionary — the exact `MapCoord`→`NMapPoint` structure `MapMoveCommand`'s enumeration in `ReplayDispatcher.cs` already reads (`currentPoint.Point.Children`) | action-aligned 1-ply lookahead |
| `run.map.grid` (`MAP_GRID_ROWS`×`_MAP_WIDTH`×`MAP_GRID_NODE`) | whole-act map topology | KEEP | same `NMapScreen` point dictionary, walked for every row/col rather than just the current point's children | |
| `run.map.meta` (2: at-Ancient, at-boss) | | KEEP | `state.CurrentMapCoord` compared against the map's starting/boss point | |
| `event.present` | | KEEP | `RoomType == EventRoom` / `ReplayState.ActiveEventSynchronizer != null` | |
| `event.page` | | KEEP | `sync.Events[0]`'s current page != "INITIAL" (event's own page-state field) | |
| `event.options` (2×`CHOICE_SLOTS`, present+locked ×16) | | KEEP | `sync.Events[0].CurrentOptions[i].Locked` — same list `ChooseEventOptionCommand`'s enumeration in `ReplayDispatcher.cs` already walks | |
| `shop.cards.f` / `shop.relics.f` / `shop.potions.f` / `shop.removal` | present, cost(log1p), enough_gold, on_sale | KEEP | `OpenShopCommand.GetEntries(room)`, filtered by `MerchantCardEntry`/`MerchantRelicEntry`/`MerchantPotionEntry`/`MerchantCardRemovalEntry` — the exact enumeration `BuyCardCommand`/`BuyRelicCommand`/`BuyPotionCommand`/`BuyCardRemovalCommand` already use in `ReplayDispatcher.cs` | `on_sale` needs `MerchantCardEntry`'s sale flag, not yet confirmed read anywhere in RunReplays — verify before C# build |
| `reward.cards.f` (×`REWARD_CARD_SLOTS`) | upgrade/cost/affl/exhaust | KEEP | `CombatRewards.Cards` — the reward screen's card list, same objects `TakeCardCommand`'s `cardRow` child enumeration in `ReplayDispatcher.cs` walks | |
| `reward.potion.f` (present) | | KEEP | reward screen's offered potion (bare offer, `ClaimRewardCommand`'s generic button enumeration covers the dispatch side) | |
| `select.count` / `select.skippable` | | KEEP | the active selection screen's `MinSelect`/remaining-count and cancelable/skippable flag (`CardSelectorPrefs`) | needs the prefs object behind whichever of `SelectGridCardCommand`/`SelectCardFromScreenCommand`/`SelectHandCardsCommand` is live |
| `select.candidates.f` (×`MAX_SELECT_CANDIDATES`=96) | per-candidate row | KEEP | the active screen's candidate `CardModel` list (`CardGridScreenCapture.GetSelectableCards`, `ChooseACardScreenCapture`'s children, or `HandSelectionCapture`'s hand) — same lists `ReplayDispatcher.cs`'s `SelectGridCardCommand`/`SelectCardFromScreenCommand`/`SelectHandCardsCommand` enumerations already walk | see Step 3 — the SORT ORDER the sim writes these in has no guaranteed correspondence to the screen's own positional index; the C# builder must independently sort by the same canonical key `_sorted_candidate_order` uses (card id, upgraded, affliction, enchantment) rather than trust screen order |
| `select.candidates.overflow` | | ACCUMULATE | | |

### 2.2 Int half (`run_obs_segments_i`)

| segment | field | disposition | game source | notes |
|---|---|---|---|---|
| `run.potions.ids` | potion id ×10 | KEEP | `player.GetPotionAtSlotIndex(p)?.Id` | |
| `run.deck.ids` | pile_id(PAD)/card_id/affl/ench ×96 | KEEP | `player.Deck.Cards[i]` | |
| `run.relics.ids` | relic id ×48 | KEEP | `player.Relics[i].Id` | |
| `run.boss.ids` | monster class ids ×`MAX_BOSS_IDS`=4 | KEEP | the act's boss encounter definition — known at act entry (`ActModel`/room generation names the boss monster class(es)) | mod needs this looked up from the act's config, not a live creature (boss isn't spawned yet) |
| `event.ids` | event id (scalar) | KEEP | `sync.Events[0].Id` | |
| `shop.cards.ids` / `shop.relics.ids` / `shop.potions.ids` | stock ids | KEEP | same `MerchantEntry` lists as the float half | |
| `reward.cards.ids` | card ids ×`REWARD_CARD_SLOTS` | KEEP | `CombatRewards.Cards[i].Id` | |
| `reward.potion.ids` | potion id (scalar) | KEEP | `CombatRewards.Potion?.Id` | |
| `select.purpose.ids` | purpose vocab id (scalar) | **REDEFINE** | no single C# field carries the sim's `purpose` string (a categorization of WHICH relic/card/event opened the screen: `"card_reward"`, `"enchant"`, `"exhaust_any"`, etc.) | proxy: the mod tags the purpose itself as SESSION STATE at the moment it dispatches the action that opens the selection screen (it already knows it just played Ashwater / opened a card-reward screen / etc.), then looks that tag up in the same `PURPOSE_INDEX` vocabulary the sim uses. This is closer to ACCUMULATE than a game read — listed as REDEFINE because the vocabulary target is unchanged, only the acquisition method moves from "engine annotates the request" to "mod remembers what it just did" |
| `select.candidates.ids` | pile_id(PAD)/card_id/affl/ench ×96 | KEEP | same candidate `CardModel` list as the float half | |

---

## Step 3 — Mask contract (`GetAvailableCommands()` vs. the run-env action layout)

Action layout (`run_env.py` module docstring, `N_ACTIONS`=243):
`[0..N_COMBAT_ACTIONS)` combat block, `[CHOICE_BASE..+CHOICE_SLOTS)` generic
choice slots, `[SELECT_BASE..+MAX_SELECT_CANDIDATES)` select-by-candidate,
`[POTION_BASE..+MAX_POTION_SLOTS)` out-of-combat any-time potion belt.

| action block | sim decision kinds it serves | `GetAvailableCommands()` coverage | verdict |
|---|---|---|---|
| combat: end turn | `COMBAT` | `EndTurnCommand` (parameterless, always enumerated in `PLAYER_TURN`/`Play` phase) | decidable |
| combat: play h@e | `COMBAT` | `PlayCardCommand(id)` / `PlayCardCommand(id, enemy.CombatId)`, enumerated per hand card × `CanPlayTargeting(null/enemy)` | decidable — positional hand index must be recovered from `NetCombatCardDb`'s `id`, not the loop index; the mod's hand-slot→id mapping must match the sim's `hand.ids` row order exactly (both are `combat.Hand.Cards` positional) |
| combat: potion p@e | `COMBAT` | `UsePotionCommand(slot)` / `UsePotionCommand(slot, enemy.CombatId)`, enumerated per belt slot × `needsEnemyTarget` | decidable |
| CHOICE: `MAP` | `MAP` | `MapMoveCommand(col)`, enumerated over `currentPoint.Point.Children` (or row-0 nodes at act start) | decidable, but indexed by **column**, not by the sim's `range(len(self.points))` sequential option index — the C# builder must map `CHOICE_BASE + i` to the i-th `MapPoint` in the SAME order the observation's `map{m}` slots were written, then translate to `MapMoveCommand(child.coord.col)`; a naive `i == col` assumption will misfire whenever children aren't laid out at columns `0..n-1` |
| CHOICE: `EVENT` | `EVENT` | `ChooseEventOptionCommand(i)` for each non-locked option index, plus `ChooseEventOptionCommand(-1)` when `IsFinished` | decidable |
| CHOICE: `SHOP` | `SHOP` | **not index-based** — `BuyCardCommand(title)` / `BuyRelicCommand(title)` / `BuyPotionCommand(title)` / `BuyCardRemovalCommand()`, keyed by card/relic **title string**, not by the sim's flat entry-index (`entries[i]`) | **gap** — the sim's `shop.own_actions()` addresses `all_entries[i]`, a single flat list mixing cards/relics/potions/removal in a fixed order; RunReplays instead exposes four SEPARATE, type-keyed command families with no positional index at all. The C# mod must reconstruct the flat index itself (walk `OpenShopCommand.GetEntries(room)` in the same concatenation order the sim's `MerchantInventory.all_entries` uses) and re-key each Buy command by TITLE at dispatch time — title collisions between differently-modified copies of the same card (Task 1's damage-preview caveat class) are a real risk requiring exact-instance disambiguation this command shape doesn't support today. "Leave shop" (`len(entries)`) maps to `CloseShopCommand`. **Flag for Task 8**: RunReplays should grow an index-based `BuyEntryCommand(int index)` or the mod-side reconciliation is fragile. |
| CHOICE: `REST` | `REST` | `ChooseRestSiteOptionCommand(optionId)`, enumerated over `sync.GetLocalOptions()` | decidable IF option order is stable and matches `RestSiteOption.Generate`'s heal/smith/leave/extras ordering — needs verification, not index-free like Buy* |
| CHOICE: `REWARD_CARD` / `REWARD_POTION` / `REWARD_RELIC` | corresponding `DecisionKind`s | `TakeCardCommand(i)`/`.Skip()`/`.Sacrifice()` for cards; `ClaimRewardCommand(i)` for generic (gold/potion/relic/key) reward buttons | decidable, but two DIFFERENT command families serve what the sim treats as one `CHOICE` slot space per kind — the mod must route `REWARD_CARD` actions to `TakeCardCommand` and `REWARD_POTION`/`REWARD_RELIC` actions to `ClaimRewardCommand`, matching `kind` |
| CHOICE: `SELECT_OPTION` | `SELECT_OPTION` (Scroll Boxes etc.) | no command type in `ReplayDispatcher.cs` obviously maps to a bare "pick option i of N" generic screen | **gap** — `SelectCardFromScreenCommand`/`ClickGridCardCommand`/`SelectGridCardCommand` are all CARD-shaped (they enumerate a `CardModel` per index); a generic non-card option screen has no enumerated command visible in `GetAvailableCommands()`. **Flag for Task 8** unless `SELECT_OPTION`'s sim purposes are confirmed to always be card-shaped in practice (needs a source check against which relics/events raise this kind) |
| SELECT_BASE: `SELECT_CARDS` candidate index | `SELECT_CARDS` | one of `SelectHandCardsCommand(i)` / `SelectGridCardCommand([i])` / `ClickGridCardCommand(i)` / `SelectCardFromScreenCommand(i)`, depending on which screen is active (`ReplayDispatcher.GetDispatchableTypes` picks exactly one of these per active screen type) | **decidable but non-trivial** — every one of these commands indexes by the SCREEN's own positional order (hand order, grid order, or `FindChildren` traversal order), NOT the sim's canonical sorted order (`_sorted_candidate_order`: card id, upgraded, affliction, enchantment). The C# builder must build its own `SELECT_BASE + i → command` table by re-deriving the sim's sort over the SAME candidate `CardModel` list the active screen exposes, then mapping sorted position i to that screen's actual positional index — an index translation layer, not a direct pass-through. This is real complexity, not just a naming mismatch. |
| POTION_BASE: out-of-combat any-time potion | any non-combat kind | `UsePotionCommand(slot)`, enumerated whenever `!inCombat` and potion's `Usage != CombatOnly` | decidable for potions with no target requirement. **One caveat**: if `needsEnemyTarget` (potion `TargetType==AnyEnemy`) AND `combatState == null` (out of combat), `ReplayDispatcher.cs`'s loop adds NO command for that slot at all (line ~151: `if (needsEnemyTarget && combatState != null)`) — an `AnyTime` potion that also requires an enemy target would be **mask-off-always** via this enumerator even on turns the sim's `potion_actions()` would legally offer it. Needs a content check: does any ported `AnyTime` potion have `TargetType.AnyEnemy`? If yes, real gap; if the two properties are mutually exclusive in practice, no action needed but should be confirmed, not assumed. |

**Actions the enumerator can't express at all**: none found that are pure
"decidable = false" (every sim action block maps to SOME command type), but
three items above are load-bearing complexity, not simple pass-throughs, and
one (`SHOP`) and one (`SELECT_OPTION`) are flagged as candidate RunReplays
extensions for Task 8's scope: (1) an index-based shop-buy command, (2) a
generic non-card option-select command if `SELECT_OPTION` turns out not to
always be card-shaped.

**Also noted, not a mask-contract defect**: `DiscardPotionCommand` exists in
`ReplayDispatcher.cs` with no corresponding sim action at all — the run-env
action space never asks to discard a potion. Not a gap (nothing needs to be
decidable that isn't asked), but worth flagging if a future action-space
widening wants it.

**Also noted**: the current schema (v9/run, v6/combat) has **no observation
segment for the `REWARD_RELIC` offer's relic identity** — `DecisionKind`
gained `REWARD_RELIC` at run-obs v5 but no `reward.relic.ids/.f` block was
ever added (confirmed absent from `run_obs_segments_f`/`_i`). The `CHOICE`
block still answers the take/skip decision correctly, but the policy (sim OR
a future live agent) cannot see WHICH relic is being offered. Out of this
audit's scope (existing-field disposition only) but should be raised to
whoever plans the v10 field additions, since v10 is bumping anyway.
**RESOLVED same day (Task B): see the "Addendum (Task B, 2026-08-04):
`reward.relic.*` closes finding #1" section at the end of this document —
`reward.relic.ids/.f` shipped as a v10-in-place amendment.**

---

## Net width-change summary

This audit finds **zero fields requiring DROP** in either schema — every
existing float/int field in combat v6 and run v9 has either a direct C# read
(KEEP), a stated proxy (REDEFINE), or a stated accumulation rule
(ACCUMULATE). Nothing sim-only-with-no-equivalent was found, which means
Task 1's "damage preview is the game's own number" verdict generalizes: the
whole preview/dynamic-var machinery (`hand.f`'s damage/block/cost fields,
`enemies.f`'s attack preview, `player.incoming_post_block`, `damage_matrix`)
rides the same `UpdateDynamicVarPreview`/`Hook.ModifyDamage` call class, and
the one segment that looked hardest to source before this audit
(`enemy{e}.intent_history.f`) turns out to be ACCUMULATE-shaped rather than
DROP-shaped — the mod just has to run the same `_roll_enemy_intents`-style
snapshot-before-reroll logic the sim already runs, since every field it
records is itself already KEEP at the point of capture.

**Combat schema (v6 → v7): width unchanged, semantics reclassified.**
No field is added or removed by this audit; every row keeps its current
width. The width change (if any) belongs to Tasks 3–4's actual schema-bump
work, not this audit. What changes is HOW each field is filled in C#:
- **10 KEEP-with-caveat power `aux` ids** and **~61 relic ids with real
  `counter`/`flag` state** need a hand-ported per-id dispatch table
  (`_power_aux`, `relic_obs.py`'s admissibility tables) — direct 1:1 source
  citations exist for all of them (`PowerModel.DisplayAmount`,
  `RelicModel.ShowCounter`/`DisplayAmount`/`IsUsedUp` overrides).
- **`enemy{e}.intent_history.f`** (6×3×15 = 270 floats) is entirely
  ACCUMULATE — the single largest chunk of session-state bookkeeping the C#
  `ObsBuilder` must implement, mirroring `CombatState._roll_enemy_intents`'s
  hook timing exactly (record pre-reroll, once per player-turn-start, only
  after the enemy's first full displayed turn).
- **12 `.overflow` flags** are pure mod-side bookkeeping (ACCUMULATE),
  trivial to implement once each block's writer exists.
- **`cards.f`'s `effective_cost`** field surfaced a possible existing
  sim/proxy mismatch (REDEFINE note above) worth checking before porting,
  not after.

**Run schema (v9 → v10): width unchanged by this audit; two real content
gaps flagged for the people scoping v10's field additions**, both outside
this audit's KEEP/DROP/ACCUMULATE/REDEFINE table because they are MISSING
fields, not existing ones:
1. No `reward.relic.*` segment for the `REWARD_RELIC` offer's identity.
   **RESOLVED same day (Task B) — see this document's closing addendum.**
2. `select.purpose` shifts from "engine-annotated" to "mod-remembers-what-
   it-just-dispatched" (REDEFINE) — cheap to implement but is a real
   behavior change (a purpose tag that depends on the mod's own action
   history being correct, not a stateless read) worth flagging to whoever
   owns Task 11/12's `ObsBuilder` reliability story.

Mask-contract verdict (Step 3): **every run-env action block maps to at
least one `GetAvailableCommands()` type**, but three blocks (`SHOP`'s
flat-index scheme, `SELECT_CARDS`'s candidate-sort-vs-screen-order mismatch,
`SELECT_OPTION`'s apparent absence of a generic non-card command) require
non-trivial index-translation logic in the C# mod rather than a direct
action-id pass-through, and two are flagged as candidate RunReplays
extensions (Task 8 scope): an index-based shop-buy command, and a
generic option-select command if `SELECT_OPTION` isn't always card-shaped.

---

## Addendum (Task B, 2026-08-04): `reward.relic.*` closes finding #1

This audit's "Net width-change summary" (Run schema, item 1) flagged that
"no `reward.relic.*` segment exists for the `REWARD_RELIC` offer's
identity". Perry approved closing it as a same-day amendment to v10 in
place (v10 was brand-new and uncommitted, nothing had trained on it, and
every doc/test/contract already referenced 10 — see
`sts2_rl/run_env.py`'s `RUN_OBS_SCHEMA_VERSION`'s own "v10 amendment"
comment for the full reasoning). This section resolves the finding with the
same disposition-table format the rest of this audit uses.

| segment | field | disposition | C# game source | notes |
|---|---|---|---|---|
| `reward.relic.f` | presence (1.0/0.0) | KEEP | derived alongside `reward.relic.ids` below — 1.0 whenever the current screen's offered item resolves to a `RelicReward` with a known relic id | mirrors `reward.potion.f`'s presence float exactly |
| `reward.relic.ids` | relic id (scalar, vocab `relics` kind, oid = index+1, 0 = PAD/absent) | KEEP | `RelicReward.Relic.Id` for the button `ClaimRewardCommand.EnumerateRewardButtons(screen)` is currently offering, when that button's underlying `Reward` is a `RelicReward` — same `NRewardButton` enumeration `ClaimRewardCommand.Execute()` (`ReplayDispatcher.cs`) already walks to dispatch the take/skip action, just read instead of clicked | zero-filled (`id == 0`, `reward.relic.f == 0.0`) on every screen OTHER than an active `REWARD_RELIC` decision — see "Population rule" below |

**Why width 1, not a multi-slot block like `reward.cards`:** a reward set
can carry SEVERAL relic offers at once (`CombatRewards.relics` — e.g. Lava
Rock grants two extra relic rolls on the act-1 boss), but the sim never
presents them together. `RunState.offer_relic` (the `reward_selector
("relic", item)` seam `driver.py`'s `RunDriver._reward_selector` answers)
raises one independent take-or-skip `DecisionKind.REWARD_RELIC` screen per
relic, sequentially — exactly the shape `reward.potion.ids/.f` already
covers for the single-potion pity drop (`CombatRewards.potions`/
`special_potions` are walked the same way, one screen at a time). The C#
`NRewardsScreen` shows the same thing: each `RelicReward` is its own
`NRewardButton`, claimed one `ClaimRewardCommand` at a time.

**Population rule (task brief requirement 3):** `reward.relic.ids/.f` is
populated ONLY while `request.kind == DecisionKind.REWARD_RELIC`, read from
`request.relic` (NOT `request.rewards` — the offered relic lives on the
`DecisionRequest` itself for this one `DecisionKind`, unlike `REWARD_CARD`/
`REWARD_POTION` which read `request.rewards`). Every other screen —
including `REWARD_CARD`/`REWARD_POTION` screens on the SAME combat's reward
set, the map, a shop, an event, mid-combat — leaves both fields at their
reset PAD/zero value. A relic whose id fails to resolve in the frozen
`relics` vocabulary is skipped (implicit PAD), the same invariant
`run.relics`/`run.deck`/`select.candidates` already hold (§5A's "Padding
invariant guards").

**Ordering guarantee (task brief requirement 2):** the run env's `CHOICE`
action block answers `REWARD_RELIC` with exactly `DecisionRequest.
own_actions()`'s `[0, 1]` (`driver.py` — action `CHOICE_BASE + 0` = take,
`CHOICE_BASE + 1` = skip). Because `reward.relic.*` is a SINGLE slot (one
relic offered at a time, argued above), slot 0 of `reward.relic.ids/.f`
IS the relic that action `CHOICE_BASE + 0` takes — there is no second slot
to misalign. This is the same slot-for-action alignment contract
`reward.cards` (positional against `REWARD_CARD`'s per-card take actions)
and `select.candidates` (index-aligned against `SELECT_CARDS`'s per-
candidate actions) already hold for their own multi-slot cases; a future C#
`ActionMap` must address `reward.relic` the identical way it will address
those — by the SAME index the `CHOICE`/`SELECT` action block uses for that
screen, never a re-sorted or re-filtered order of its own.

**Width accounting:** `reward.relic.f` and `reward.relic.ids` are each
width 1, appended after `reward.potion.f`/`reward.potion.ids` respectively
in `run_obs_segments_f`/`run_obs_segments_i` (`sts2_rl/run_env.py`). `f_dim`
4710 → 4711, `i_dim` 1464 → 1465. This is the ONLY width change made by
Task B; every other segment in this audit's tables is unchanged.
