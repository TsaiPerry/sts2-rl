# Gap queue — the six engine-seam audits, aggregated

Every `"verdict": "gap"` entry from `audits/seam/*.json`, de-duplicated by
mechanism, ordered for work, and left **queued, not fixed** (Perry's standing
decision). The audits found far more than recorded-run convergence ever
surfaced; this file is the single actionable view of it.

Generated, not transcribed. Regenerate the numbers with:

```
py tools/audit/gap_queue.py counts        # the summary header below
py tools/audit/gap_queue.py mechanisms    # the grouping, largest first
py tools/audit/gap_queue.py pins          # the 32 strict xfails and what they pin
py tools/audit/gap_queue.py unpinned      # mechanisms with no pin
```

Do not trust a count stated in prose anywhere in this project — including this
file. Re-run `counts`.

## Summary

| | |
|---|---|
| gap entries across the 6 records | **224** |
| — labelled LIVE in their own text | 46 |
| — labelled DORMANT in their own text | 75 |
| — unlabelled (inherit their mechanism's liveness) | 103 |
| **distinct mechanisms** | **90** |
| — with at least one live site | **23** |
| — dormant at every site | 67 |
| mechanisms pinned by a `strict=True` xfail | **31** |
| mechanisms unpinned | 59 |
| `strict=True` xfails in `test/test_hook_order.py` | 32 (all strict) |

Per record (gap entries / mechanisms anchored there / entries labelled live):

| record | entries | mechanisms | live |
|---|---|---|---|
| `damage_pipeline` | 14 | 7 | 1 |
| `power_cmd` | 24 | 7 | 1 |
| `creature_card_cmds` | 73 | 32 | 8 |
| `turn_structure` | 67 | 24 | 19 |
| `hook_dispatch` | 30 | 11 | 13 |
| `monster_state_machine` | 16 | 9 | 4 |

**224 entries are not 224 jobs.** The largest mechanism, the missing
`IsEnding`/`IsOverOrEnding` dispatch gate, is recorded at **22** sites across
three records; the missing `AfterModifyingXxx(modifiers)` companion events at
**12**; `turn_structure`'s missing turn-1 win check at **9**. Fixing one site of
a mechanism generally clears all of them. A queue that listed the 224 entries as
independent items would overstate the work by roughly 2.5x.

## How to read an entry

```
### N. <mechanism id>  — <one-line name>            [LIVE|DORMANT] [pinned|unpinned]
sites      every gap entry that is this same mechanism (the stable ids)
divergence one sentence, sim file:line vs C# file:line
observable what a player or a replay sees; executed numbers where the record has them
trigger    (dormant only) the concrete unported thing that makes it live
pin        the strict xfail in test/test_hook_order.py that flips to passing, or why not
fix        which sim file changes and roughly how; what the failing test asserts
radius     other mechanisms sharing machinery; content units the record names
```

**Stable ids** are `<seam>/<step-or-guard-id>` — `hook_dispatch/G9`,
`monster_state_machine/step13`, `creature_card_cmds/G14`. A mechanism is named
by its anchor entry; where a mechanism was recorded in two records, the merge is
declared in `tools/audit/gap_queue.py::_CROSS_RECORD` with the record text that
asserts it.

**Watch the id collisions.** `G8` is the missing `IsEnding` gate in
`hook_dispatch` but the missing AutoPrePlay/AutoPostPlay phases in
`turn_structure`; `G2`, `G3`, `G4`, `G9` and `N5` all mean different things in
different records. Always carry the seam prefix.

**C# paths.** Records cite C# by bare filename. The ones this queue uses:

| file | path under `c:\Users\Perry\Desktop\Slay the Spire 2` |
|---|---|
| `Hook.cs` | `src/Core/Hooks/Hook.cs` |
| `CombatManager.cs`, `CombatState.cs` | `src/Core/Combat/` |
| `CreatureCmd.cs`, `CardCmd.cs`, `CardPileCmd.cs`, `PowerCmd.cs`, `PlayerCmd.cs`, `CardSelectCmd.cs` | `src/Core/Commands/` |
| `Creature.cs` | `src/Core/Entities/Creatures/` |
| `PlayerCombatState.cs` | `src/Core/Entities/Players/` |
| `CardModel.cs`, `MonsterModel.cs`, `AbstractModel.cs` | `src/Core/Models/` |
| `RandomBranchState.cs`, `MoveState.cs`, `MonsterMoveStateMachine.cs` | `src/Core/MonsterMoves/MonsterMoveStateMachine/` |
| `RunState.cs` | `src/Core/Runs/` |
| powers / relics / monsters / enchantments | `src/Core/Models/{Powers,Relics,Monsters,Enchantments}/` |

Sim paths are repo-relative (`sts2_rl/...`, `test/...`).

## Ordering

Sorted by **seed-convergence impact** first, then blast radius, then fix cost;
live above dormant throughout. Convergence impact is graded:

- **A — stream desync.** Changes an RNG draw count or the stream a draw comes
  from. Every later draw in the run shifts; a replay stops converging outright.
- **B — state divergence.** Changes a damage/block/HP number, a hand, a pile or
  a deck entry. The next conformance assert fires.
- **C — bookkeeping only.** Hook order or event identity with no numeric effect
  on currently-ported content.

---

# Tier 1 — live gaps

23 mechanisms have at least one site the records label LIVE on already-ported
content.

### 1. `monster_state_machine/G1` — `AddBranch` integer arguments read as weights  [LIVE] [pinned]

- **sites** `monster_state_machine/step13` (1 entry; the mismatch probe covers 12 resolved C#↔sim module pairs).
- **impact** A — the roll distribution itself differs, so `combat_rng.monster_ai` desyncs.
- **divergence** C#'s `AddBranch` puts *cooldown-or-maxRepeats* in positional
  slot 2 across its ten overloads (`RandomBranchState.cs:46-113`); the sim's
  `add_branch` puts *weight* there, so a positional transliteration turns a
  repeat limit into a weight.
- **observable** Five of the twelve resolved pairs misread it —
  `FlailKnight.cs:50,51` (maxRepeats 2) → `sts2_rl/monsters/hive/flail_knight.py:51,52`
  (`weight=2.0`, `CAN_REPEAT_FOREVER`); `HunterKiller.cs:43` →
  `sts2_rl/monsters/hive/hunter_killer.py:45`; `ScrollOfBiting.cs:90` →
  `sts2_rl/monsters/glory/scroll_of_biting.py:65`; `SpectralKnight.cs:52` →
  `sts2_rl/monsters/glory/knights.py:111`; `FakeMerchantMonster.cs:58`
  (cooldown 3) → `sts2_rl/monsters/fake_merchant.py:72-75`
  (`weight=_ENRAGE_WEIGHT` = 3.0, no cooldown — the misreading is written into
  the docstring at `fake_merchant.py:40`). Probe `distribution` (100000 rolls,
  seed 7) shows the sim's and the game's move distributions differing.
- **pin** `test/test_hook_order.py::TestMonsterStateMachineOrder::test_addbranch_int_args_are_repeat_limits_not_weights`.
- **fix** Per monster module, re-read the C# call and re-express: `AddBranch(state, N)`
  with `CanRepeatXTimes` is `max_times=N`, with the default repeat type it is a
  cooldown. The sim's `add_branch` already takes `max_times`; a cooldown needs
  either the `cooldown` parameter or the equivalent
  `MoveRepeatType.CANNOT_REPEAT`-plus-counter shape. Failing test asserts the
  branch's *selection frequency* over a fixed seed matches the C# semantics
  (e.g. Flail Knight cannot pick `FLAIL` a third consecutive time).
- **radius** This is the bug class whose earlier fix (TwigSlimeM + Flyconid)
  greened 89U's act-0 player HP; the same misreading survives in five more
  monsters. Content units: Flail Knight, Hunter Killer, Scroll of Biting,
  Spectral Knight (the `knights` elite), Fake Merchant. Related but distinct:
  `monster_state_machine/G7` (maxTimes == 0) and `/G8` (construction validation)
  are the other two `AddBranch`-semantics mechanisms.

### 2. `turn_structure/G9` — enemy intents rolled per-move, not in one pass at player-turn start  [LIVE] [**unpinned**]

- **sites** `turn_structure/step2`, `/step11`, `/step33`, `/G9` (4 entries);
  cross-referenced by `monster_state_machine/G6` and `/step11`.
- **impact** A — a proven off-by-one in the `monster_ai` draw count.
- **divergence** `CombatManager.cs:478-484` rolls *every* enemy's next move in
  one pass at the start of the player's turn, in enemy-list order, and skips the
  pass on an extra player turn; the sim advances each monster's own machine
  inside its move (`sts2_rl/monsters/base.py:96-105` `telegraph_next_move`,
  driven from `sts2_rl/combat.py:314-329`).
- **observable** A monster that does not act — stunned — takes **no**
  `monster_ai` draw in the sim and **one** in the game. Executed with a
  one-`LeafSlimeS` encounter and a counting proxy over the `monster_ai`
  accessor: `normal enemy turn: MonsterAi draws = 1`, `STUNNED enemy turn:
  MonsterAi draws = 0`. One stunned enemy round desyncs the stream by exactly
  one draw and every later draw in the combat shifts. Player-reachable:
  `sts2_rl/cards/whistle.py:30-38` (Tanx's Whistle) stuns with no
  `next_move_key`.
- **pin** Deliberately none — "the observable is an RNG-stream draw count, not a
  hook order, and the conformance suite is its natural home". **The single
  highest-value unpinned live gap in the queue.**
- **fix** Move the roll out of the move: give `CombatState` a
  `_roll_enemy_intents()` that walks `self.enemies` in list order at the top of
  the player turn (`combat.py`, alongside the turn-1 setup and the
  `start_turn()` path), have `telegraph_next_move` stop rolling, and skip the
  pass on the extra-turn path (`combat.py:648-652`). The spawn roll stays where
  `CreatureCmd.add` puts it. Failing test: a stunned enemy round consumes
  exactly one `combat_rng.monster_ai` draw (count the stream, as the record's
  probe does) — this belongs in `test/test_conformance_determinism.py` or
  `test/test_rng_tripwire.py` rather than `test_hook_order.py`.
- **radius** Interacts with `monster_state_machine/G4` (stun as a real move —
  the deferred-move re-log is the *other* half of the same stunned-enemy
  scenario) and `/G6` (`FlutterPower` splicing a roll). Anything that changes
  when a monster rolls changes the entire `monster_ai` stream for the run.

### 3. `hook_dispatch/G9` — multiplicative modifier hooks: parallel product vs sequential chain  [LIVE] [pinned]

- **sites** `hook_dispatch/step31`, `damage_pipeline/N3` (2 entries), plus
  `creature_card_cmds/step13` clause (c) as the block-side site (dormant there).
- **impact** B — raw damage numbers differ.
- **divergence** C# folds each listener's factor into a running `decimal`
  (`Hook.cs:2515-2538` `ModifyDamageInternal`, `Hook.cs:1320-1337` `ModifyBlock`);
  the sim multiplies every factor together in float first and applies the product
  once (`sts2_rl/hooks.py:66-78`, `111-122`, applied at `sts2_rl/cmds.py:57-58`
  and `145-147`).
- **observable** Shrink (×0.7, `sts2_rl/powers.py:1366-1387`, from the ported
  Shrinker Beetle `monsters/overgrowth/shrinker_beetle.py:39-40` and the Shrink
  Potion `potions.py:718-722`) plus Vulnerable (×1.5, `powers.py:403-417`) on a
  20-damage powered attack: **sim 20, game 21** — the sim computes
  `1.5*0.7 = 1.0499999999999998`, `20 * that = 20.999999999999996`, `int → 20`;
  the game computes `20m*1.5m = 30m`, `30m*0.7m = 21m`. Base 40 diverges the
  same way. A control run that keeps float arithmetic but threads it
  sequentially returns 21, so the cause is the aggregation shape, not
  float-vs-decimal.
- **pin** `TestHookDispatchOrder::test_multiplicative_damage_modifiers_chain_sequentially`.
- **fix** Change `hooks.modify_damage_multiplicative` /
  `modify_block_multiplicative` from "return the product" to "take the running
  amount, fold each listener's factor in, return the new amount", and change the
  two call sites in `cmds.py` to assign rather than multiply. Keep the additive
  family as is — the record proves base+sum ≡ sequential over integers. Failing
  test asserts 21, not 20, for the Shrink+Vulnerable 20-damage case.
- **radius** Block site (`creature_card_cmds/step13`) is dormant only because all
  five ported block multipliers are dyadic (`{0.0, 0.75, 2.0}`); it goes live
  with the first non-dyadic one. Adjacent mechanisms on the same dispatchers:
  `damage_pipeline/G3` (the powered-attack gate) and `damage_pipeline/G2` (the
  missing modifier-notification list).

### 4. `hook_dispatch/G4` — one hook bracket per logical play instead of per `CardPlay`  [LIVE] [pinned]

- **sites** `hook_dispatch/G4` (1 entry).
- **impact** B — wrong card gets doubled, from the first combat of a run.
- **divergence** `CardModel.cs:1904-1965` loops `for (i = 0; i < playCount; i++)`,
  builds a fresh `CardPlay` with `PlayIndex = i` each iteration (1919-1928) and
  fires `Hook.BeforeCardPlayed` (1929) **and** `Hook.AfterCardPlayed` (1959)
  *inside* the loop; `sts2_rl/combat.py:466` fires `before_card_played` once
  before the `for _ in range(play_count)` loop (477-494) and `combat.py:514`
  fires `on_card_played` once after it.
- **observable** Throwing Axe (`relics/throwing_axe.py:30-36`, from the ported
  Tanx shrine `events/tanx.py:13`) makes the first card of a combat play twice;
  Pen Nib (`relics/pen_nib.py:30-35`) counts Attack plays in `before_card_played`
  and doubles every 10th. One Throwing-Axe-doubled Strike advances the sim's
  counter by 1 where the game advances it by 2 — **so from the first combat on,
  the sim doubles a different attack than the game does**.
- **pin** `TestHookDispatchOrder::test_before_card_played_fires_once_per_replay_iteration`.
- **fix** In `combat._resolve_card_play`, move the `before_card_played` /
  `on_card_played` dispatches inside the play-count loop and give each iteration
  its own play index. Watch the history writer (`history.py:80-81` records a
  `CardPlayedEntry` per `on_card_played`) — the entry count is deliberately
  per-play in C# too, so it should follow. Failing test asserts Pen Nib's counter
  advances by 2 on a Throwing-Axe-doubled Strike.
- **radius** Four ported replay sources widen it (`enchantments.py:167`,
  `enchantments.py:232`, `powers.py:966` One-Two Punch, `powers.py:3919`
  Duplication) and all 48 sim `on_card_played` listeners see the wrong bracket
  count. Touches `turn_structure/G18` (Pael's Eye counts plays) and
  `creature_card_cmds` step 46 (auto-play bracket).

### 5. `hook_dispatch/G2` — cross-listener dispatch order  [LIVE] [pinned]

- **sites** `hook_dispatch/step1`, `/step2`, `/step5`, `/step6`, `/step41`, `/step43` (6 entries).
- **impact** B — a card's energy cost differs, which changes what is playable.
- **divergence** `CombatState.cs:413-467` groups listeners **per creature**,
  allies before enemies, and within a player walks Powers → Relics → PotionSlots
  → Orbs → cards; `sts2_rl/hooks.py:38,43-44` keeps one flat registration-order
  list whose category order is History → Cards → Relics → Potions → Powers
  (`combat.py:106-166`, `cmds.py:326`) — **powers first in the game and last in
  the sim; cards last in the game and first in the sim**.
- **observable** Executed on `Hook.ModifyEnergyCostInCombat`: with
  `CuriousPower(2)` (`powers.py:2883`, applied by the ported Mad Science card)
  and Spiked Gauntlets (`relics/spiked_gauntlets.py:26-32`, ported Tanx shrine)
  on a 1-cost Power card, the game computes `max(0, 1-2) = 0` then `+1 = 1`; the
  sim computes `1+1 = 2` then `max(0, 2-2) = 0`. **Game 1, sim 0.** Co-occurrence
  is explicit: Mad Science comes from the ported Glory event Tinker Time
  (`events/tinker_time.py:74`).
- **pin** `TestHookDispatchOrder::test_powers_modify_energy_cost_before_relics_do`.
- **fix** Stop relying on registration order: have `HookSystem` iterate a
  *derived* order rather than `self._listeners` as appended. Cheapest faithful
  shape is to keep per-category buckets (powers, relics, potions, cards) per
  creature and yield allies-then-enemies, powers-first, which also gives
  `hook_dispatch/G1` (per-pile card order) somewhere to live. Failing test
  asserts the 1-cost Power card costs 1, not 0, with Curious + Spiked Gauntlets.
- **radius** Every one of the sim's 66 dispatchers. Prerequisite for
  `hook_dispatch/G1` (card listener order re-derived per dispatch),
  `hook_dispatch/G6` (afflictions register right after their card),
  `hook_dispatch/G5` (`MonsterModel` as a listener) and `hook_dispatch/G7` (the
  lazy `Contains` re-check) — all four are dormant today and all four need this
  list to exist first.

### 6. `hook_dispatch/G3` — no Early / VeryEarly / Late phase passes  [LIVE] [pinned]

- **sites** `hook_dispatch/step27`, `/step28`, `/step29`, `/step30`, `/step46` (5 entries).
- **impact** B — energy cost differs; ordering becomes registration luck.
- **divergence** 24 of `Hook.cs`'s 147 dispatchers run 2-4 *complete* listener
  passes and `AbstractModel.cs` declares 27 phase-suffixed hooks; `sts2_rl/hooks.py`
  has one walk per hook and no phase concept at all (`hooks.py:673-680` says so).
- **observable** `TangledPower.TryModifyEnergyCostInCombat` (EARLY,
  `powers.py:1486-1502`, applied by the ported Vine Shambler
  `monsters/overgrowth/vine_shambler.py:42-43`) and
  `FreeAttackPower.TryModifyEnergyCostInCombatLate` (LATE, `powers.py:1133-1155`,
  applied by the ported card Unrelenting `cards/unrelenting.py:40`) both target
  Attacks: the game always ends at cost 0; the sim ends at 1 when Free Attack was
  applied first and 0 when Tangled was. `BufferPower.cs:17-19` carries a source
  comment stating the Late phase is load-bearing.
- **pin** `TestHookDispatchOrder::test_late_energy_cost_modifiers_run_after_early_ones`.
- **fix** Add a phase parameter to `HookSystem`'s dispatch helper and let a
  listener declare `<hook>_early` / `<hook>_late` methods; dispatch runs the
  passes in order, re-enumerating the listener list each pass (C# does). Start
  with the dispatchers that have ported phase-split listeners — energy cost,
  `BeforeTurnEnd` (that is `turn_structure/G12`), `AfterSideTurnStart`. Failing
  test asserts cost 0 regardless of which power was applied first.
- **radius** Same mechanism as `turn_structure/G12` (BeforeTurnEnd's three
  passes, Orichalcum) — fixing the phase machinery here is the prerequisite for
  that entry's clean fix. Also blocks a faithful `BufferPower` port
  (`damage_pipeline/G2`).

### 7. `turn_structure/G13` — no `CheckWinCondition` after the turn-1 setup  [LIVE] [pinned]

- **sites** `turn_structure/step16`, `/step27`, `/step29`, `/step41`, `/step49`,
  `/step51`, `/step56`, `/step60`, `/G13` (9 entries).
- **impact** B — a dead player keeps taking legal actions.
- **divergence** C# calls `CheckWinCondition` at six sites, including
  immediately after `SetupPlayerTurn` (`CombatManager.cs:573`); the sim checks
  after each enemy move (`combat.py:336-338`), after the enemy side, and after
  the *next* player turn's setup (`combat.py:681-685`), but **nothing** follows
  `combat.py:208-209` (`on_combat_start` → `start_turn`). Its other three
  "checks" (`combat.py:655-660`, `666`, `673`) only test the cached
  `phase == COMBAT_OVER` flag.
- **observable** A player killed during turn-1 setup — by an
  `on_combat_start`/`on_player_turn_start(ed)` listener — is left in
  `Phase.PLAYER_TURN` at 0 HP with a legal action set, where the game ends the
  combat immediately. The record's own text flags that the inherited "no ported
  listener deals damage" dormancy claim is **false**.
- **pin** `TestTurnStructureOrder::test_turn_one_setup_death_ends_the_combat`.
- **fix** Add a real `_check_win_condition()` (recomputing, not reading the
  cached flag) and call it after `combat.py:209`; while there, decide whether the
  other two flag-reads should also recompute — the record notes none of the three
  existing sites does. Failing test asserts `phase == COMBAT_OVER` after a
  turn-1-setup kill.
- **radius** The largest single-record mechanism in `turn_structure`. Adjacent:
  `turn_structure/G10` (the combat-end path's two disagreeing player-death exits)
  and `hook_dispatch/G8` (nothing should dispatch once combat is ending) — all
  three are the same "the sim's combat-over state machine is thinner than the
  game's" area, and a fix that recomputes the condition should land with G10's
  two-exit reconciliation.

### 8. `turn_structure/G14` — the turn-1 `ShouldStartAtBottomOfDrawPile` pass is missing  [LIVE] [pinned]

- **sites** `turn_structure/step21`, `/G14` (2 entries).
- **impact** B — the opening hand differs, which changes every play in it.
- **divergence** `CombatManager.cs:657-672` runs **two** pile moves before the
  turn-1 draw — first every card whose enchantment sets
  `ShouldStartAtBottomOfDrawPile` goes to the bottom, then every Innate card not
  already moved goes to the top (`.Except(list)`); `sts2_rl/player.py:172-182`
  ports only the Innate half.
- **observable** `ShouldStartAtBottomOfDrawPile` has exactly one implementer in
  the whole decompiled game — `Imbued.cs:11` — and Imbued **is** ported
  (`enchantments.py:243-267`) and obtainable (Electric Shrymp,
  `relics/electric_shrymp.py:17-21`, enchants a deck Skill with it). Observed
  over 30 seeds with a 9-Strike + 1-Imbued-Defend deck: the sim's turn-1 hand is
  4 cards in 17 of them (the Imbued card occupies an opening-hand slot the game
  never gives it).
- **pin** `TestTurnStructureOrder::test_imbued_card_starts_at_the_bottom_of_the_draw_pile`.
- **fix** In `player.start_turn`'s `_first_turn` arm, run the bottom-move pass
  *before* the Innate top-move pass and exclude already-moved cards from the
  Innate pass, mirroring `.Except(list)`. Failing test asserts the Imbued Defend
  is at the bottom of the draw pile and the opening hand is 5 Strikes.
- **radius** Only Imbued today, but the pass is generic; any future enchantment
  overriding the hook lands here. Touches the same `_first_turn` block as
  `turn_structure/G6` (turn-1 block clear) — fix them together.

### 9. `creature_card_cmds/G3` — a deck transform bypasses the deck-entry pipeline  [LIVE] [pinned]

- **sites** `creature_card_cmds/step57`, `/step59`, `/G3` (3 entries).
- **impact** B — the deck itself diverges, permanently, for the rest of the run.
- **divergence** `CardCmd.Transform` runs `Hook.ModifyCardBeingAddedToDeck`
  (`CardCmd.cs:430`) and fires `Hook.AfterCardChangedPiles` (`CardCmd.cs:447`) for
  Deck-pile transforms — the same two hooks `CardPileCmd.Add` runs;
  `sts2_rl/run.py:459-469` (`RunState.transform_card`) deletes the original and
  appends the replacement directly, never routing through `run.py:341-354`
  (`add_card`), which is where both sim-side hooks live.
- **observable** Executed: holding Frozen Egg, `add_card(Inflame)` yields
  `upgrade_level 1` but `transform_card(..., into=Inflame)` yields **0**; holding
  Bing Bong, `add_card` grows the deck by 2 but `transform_card` adds **0**
  clones. Every participant is ported: the three egg relics (Frozen/Toxic/Molten),
  Bing Bong, Book of Five Rings, Darkstone Periapt, Lucky Fysh.
- **pin** `TestCreatureCardCmdsOrder::test_deck_transform_runs_modify_card_being_added_to_deck`.
- **fix** Route `transform_card`'s replacement through the same hook calls
  `add_card` makes — `modify_card_being_added_to_deck` before insertion and the
  deck-add shim (`relics/base.py:208-210`) after — while keeping the
  append-at-deck-end position (`CardCmd.cs:437`, an already-verified parity fact).
  Failing test asserts a Frozen-Egg transform into a Skill produces an upgraded
  card.
- **radius** `creature_card_cmds/G8` (no `AfterCardChangedPiles` at all) is the
  general version — the deck-only shim covers the four ported listeners
  *everywhere except this transform path*, which is exactly why G3 bites.
  `creature_card_cmds/step55` (in-combat transform rolls off-stream) is the
  combat-side sibling and is a parity defect in its own right.

### 10. `damage_pipeline/G3` — pipeline-level `is_powered_attack` gate  [LIVE] [pinned]

- **sites** `damage_pipeline/G3`, `creature_card_cmds/step13`, `creature_card_cmds/G1` (3 entries).
- **impact** B — block totals differ on ported content.
- **divergence** `cmds.py:56-58` (damage) and `cmds.py:145-147` (block) skip the
  *entire* modifier dispatch when `is_powered_attack(props)` is false; C#'s
  `ModifyDamageInternal` (`Hook.cs:2515-2538`) and `ModifyBlock`
  (`Hook.cs:1310-1340`) always call every listener and leave the gate to each
  implementation.
- **observable** Dexterity, Frail and Fasten self-gate identically in both
  codebases, but **Vambrace** (`Vambrace.cs:59-63`) and **Pael's Legion**
  (`PaelsLegion.cs:132-134`) self-gate only on `IsCardOrMonsterMove()` — Move
  alone, ignoring Unpowered. Entrench is a ported Ironclad event card that gains
  block with `MOVE|UNPOWERED` (`cards/trash_heap_cards.py:159-179`), and Vambrace
  is a ported Uncommon relic: the game doubles Entrench's block, the sim does
  not. On the damage side the same gate silently drops `SurroundedPower`'s ×1.5
  (Kaiser Crab, `powers.py:2523-2565`) for any Unpowered dealer-attributed hit.
- **pin** `TestCreatureCardCmdsOrder::test_unpowered_card_block_still_runs_block_modifiers`.
- **fix** Delete the two pipeline-level gates and push `is_powered_attack` into
  each listener that needs it — Strength, Vulnerable, Weak, Dexterity, Frail,
  Fasten self-gate; Vambrace, Pael's Legion and Surrounded must not. Failing test
  asserts Vambrace doubles an Entrench block gain.
- **radius** Same two call sites as `hook_dispatch/G9` (aggregation shape) and
  `damage_pipeline/G2` (modifier notification) — one editing pass over
  `cmds.py:56-58` / `145-147` and `hooks.py:52-122` can land all three.

### 11. `damage_pipeline/G2` — no `AfterModifyingXxx(modifiers)` companion events  [LIVE at the block site] [pinned]

- **sites** `damage_pipeline/step5`, `/step9`, `/step12`, `/G2`;
  `power_cmd/step21`, `/step22`, `/step31`, `/step32`, `/G4`;
  `creature_card_cmds/step15`, `/G2`; `hook_dispatch/step38` (**12 entries** —
  the second-largest mechanism in the queue).
- **impact** B at the block site (a relic fires on the wrong gain), C elsewhere.
- **divergence** C#'s modifier dispatchers track which listeners actually
  changed the value and fire a companion event so those listeners can react only
  when they were an active modifier — `Hook.cs:649-829` declares **13**
  `AfterModifying*` variants. The sim implements exactly one, `modify_hp_lost` /
  `after_modify_hp_lost` (`hooks.py:126-155`, called from `cmds.py:85-87`); the
  other 12 (BlockAmount, CardPlayCount, CardRewardOptions, DamageAmount,
  EnergyGain, GoldGained, HandDraw, OrbPassiveTriggerCount, PowerAmountGiven,
  PowerAmountReceived, Rewards …) have no surface.
- **observable** Live at the **block** site: all three C# listeners on
  `AfterModifyingBlockAmount` are ported (`Vambrace.cs:78-90`,
  `PaelsLegion.cs:146-158`, `FastenPower.cs:36-40`) and each hand-rolls its
  "I actually fired" side effect onto a different event. Pael's Legion's
  hand-roll nets the same (`relics/paels_legion.py:33-51`); **Vambrace's does
  not** — `relics/vambrace.py:36-40` burns its once-per-combat `_used` flag on
  the *first* block gain, where C# latches `TriggeringCard` and doubles every
  block gain of that one card play. Elsewhere the machinery's absence is
  structural: `ArtifactPower.AfterModifyingPowerAmountReceived`
  (`ArtifactPower.cs:38-41`) is the actual method that calls
  `PowerCmd.Decrement`, reimplemented inline at `cmds.py:301-305`, and
  `RuinedHelmet.cs:55-60` likewise at `relics/ruined_helmet.py:37`.
- **pin** `TestCreatureCardCmdsOrder::test_vambrace_doubles_every_block_gain_of_one_card_play` (the block site only; the other 11 variants are unpinned).
- **fix** Generalise the `modify_hp_lost` pattern: give each modifier dispatcher
  in `hooks.py` an out-param `modifiers` list and a paired `after_modify_<x>`
  notifier, then re-home the three block listeners and the two power-amount
  listeners onto it. Failing test asserts Vambrace doubles *both* block gains of
  a two-block-gain card play and neither gain of the next card.
- **radius** Blocks a faithful `BufferPower` port (its whole mechanism is
  `AfterModifyingHpLostAfterOsty`) and sits on the very seam the Unsettling Lamp
  bug lived on (PowerAmountGiven/Received). Same dispatchers as
  `hook_dispatch/G9` and `damage_pipeline/G3`.

### 12. `turn_structure/G8` — the AutoPrePlay / AutoPostPlay phases do not exist  [LIVE] [pinned]

- **sites** `turn_structure/step6`, `/step10`, `/step26`, `/step47`, `/G8`,
  `/N1` and N1's two co-entries (8 entries).
- **impact** B — block totals differ; also the home of a hand-rolled recursion
  guard.
- **divergence** C# gives start-of-turn auto-plays their own phase, entered
  strictly after `Hook.AfterSideTurnStart` and the orb queue
  (`CombatManager.cs:556-572`), and end-of-turn auto-plays a phase entered
  strictly before `Hook.BeforeTurnEnd` (`CombatManager.cs:1160-1176`); the sim has
  neither hook and hand-rolls both onto neighbouring slots.
- **observable** `StampedePower` is ported and fires from `on_player_turn_end`
  (`powers.py:1025`) — the sim's `BeforeTurnEnd` slot — where C# implements
  `AfterAutoPostPlayPhaseEntered`; Cloak Clasp (`relics/cloak_clasp.py:19-24`)
  gains 1 block per card in hand from `BeforeSideTurnEnd`. C# **always** runs
  Stampede's auto-plays before Cloak Clasp counts the hand; the sim's answer
  depends on registration order. Observed with a 5-card hand and Stampede 2.
- **pin** `TestTurnStructureOrder::test_end_of_turn_auto_plays_run_before_turn_end_hooks`.
- **fix** Add the two phase slots to `combat.end_turn` / `player.start_turn` as
  explicit steps (drain auto-plays, then dispatch the turn-end hooks) rather than
  as listeners; that also gives `turn_structure/N1`'s hand-rolled recursion guard
  (`relics/whispering_earring.py:27-43`, `if combat.is_over or self.turn !=
  start_turn: break`) a real home. Failing test asserts Cloak Clasp counts the
  post-Stampede hand.
- **radius** `turn_structure/N1` (the `_inPlayerTurnSetup` race guard) carries
  this mechanism's precedence by the record's own statement.
  `hook_dispatch/G3`'s phase machinery is the neighbouring fix; `turn_structure/G12`
  is the other ordering-by-phase entry.

### 13. `turn_structure/G12` — sub-phase ordering inside BeforeTurnEnd / AfterTurnEnd / AfterSideTurnStart  [LIVE] [pinned]

- **sites** `turn_structure/step23`, `/step39`, `/step48`, `/step64`, `/G12` (5 entries).
- **impact** B — a relic's snapshot reads post-mutation state.
- **divergence** C# guarantees ordering with separate complete passes —
  `BeforeSideTurnEndVeryEarly` → `Early` → `BeforeSideTurnEnd`
  (`Hook.cs:1238-1261`), `AfterSideTurnEnd` → `AfterSideTurnEndLate`
  (`Hook.cs:1265-1291`), `AfterSideTurnStart` → `Late` (`Hook.cs:1163-1175`); the
  sim's dispatchers are a single pass each (`hooks.py:285-295`, `297-301`,
  `338-342`).
- **observable** Orichalcum is ported and deliberately two-phase in C# —
  `BeforeSideTurnEndVeryEarly` snapshots `Block > 0` into `ShouldTrigger`
  (`Orichalcum.cs:44-56`) and `BeforeSideTurnEnd` then grants the 6 block. In the
  sim both halves collapse into one pass, so whether the snapshot sees a
  block-spending listener's effect is registration-order luck. The record
  explicitly overturns the inherited "no ported pair contends" claim.
- **pin** `TestTurnStructureOrder::test_orichalcum_snapshots_block_before_other_turn_end_listeners`.
- **fix** Same machinery as `hook_dispatch/G3`: phase passes in `HookSystem`.
  Land G3 first, then convert these three dispatchers. Failing test asserts
  Orichalcum still grants its block when another turn-end listener spends the
  block first.
- **radius** `hook_dispatch/G3` (the general phase gap, 5 more sites),
  `turn_structure/G11` (the missing enemy-side `BeforeTurnEnd` slot).

### 14. `turn_structure/G3` — the extra-turn check short-circuits the entire turn-end pipeline  [LIVE] [pinned]

- **sites** `turn_structure/step65`, `/step68`, `/G3`, plus `/N4` (RoundNumber vs
  TurnNumber, which the record says carries G3's precedence) and its co-entry
  (5 entries).
- **impact** B — an entire turn's worth of end-of-turn effects is skipped.
- **divergence** `combat.py:648-652` tests `should_take_extra_turn` at the **top**
  of `end_turn` and, on success, runs only `on_extra_turn`, `turn += 1` and
  `start_turn()`; C# evaluates `Hook.ShouldTakeExtraTurn` in
  `SwitchFromPlayerToEnemySide` (`CombatManager.cs:1360-1373`) **after** both
  end-turn phases have run, and skips only the enemy side.
- **observable** With Pael's Eye held (ported Ancient relic from the Pael shrine,
  `events/pael.py:53`, `relics/paels_eye.py:36-47`) and no card played, a full
  hook trace of `end_turn` records `should_take_extra_turn` and nothing else — no
  `on_player_turn_end`, no flush, no `after_player_turn_end`. The sim has dozens
  of `on_player_turn_end` listeners plus Parrying Shield's
  `after_player_turn_end`.
- **pin** `TestTurnStructureOrder::test_extra_turn_still_runs_the_turn_end_pipeline`.
- **fix** Move the `should_take_extra_turn` test to the *bottom* of `end_turn`,
  after the flush and cleanup, and make it skip only `_run_enemy_turns`. While
  there, split `self.turn` into a player `turn_number` and a combat
  `round_number` (`turn_structure/N4`) — `CombatManager.cs:1405-1418` increments
  them differently. Failing test asserts an extra turn still fires
  `on_player_turn_end` and the flush.
- **radius** `turn_structure/N4` merges here by the record's own precedence
  statement; `turn_structure/G18` (Pael's Eye's own predicate) is the same relic's
  other gap and the two interact — fix G18 first or the test fixture will disagree
  with itself.

### 15. `turn_structure/G1` — `AfterBlockCleared` is a separate unconditional loop  [LIVE] [pinned]

- **sites** `turn_structure/step14`, `/G1` (2 entries).
- **impact** B — block-triggered relics fire (or fail to fire) a turn early.
- **divergence** C# runs the block clear and its event in **two** loops —
  `foreach (item3 in creaturesStartingTurn) await item3.AfterTurnStart(side)`
  (`CombatManager.cs:492-499`) then `foreach (item4 …) await
  Hook.AfterBlockCleared(_state, item4)` (500-507) — so the event fires for every
  participant, including one with no block, one whose clear a `ShouldClearBlock`
  listener prevented, and a turn-1 player whose `AfterTurnStart` returned early.
  The sim fuses them: `player.py:157-159` fires `on_block_cleared` only inside the
  `if should_clear_block(...)` arm and `combat.py:296-298` additionally gates the
  enemy arm on `enemy.block > 0`.
- **observable** Both preventers are ported — Barricade
  (`cards/barricade_card.py:33-34`, `powers.py:140`) and Sturdy Clamp — and both
  Anchor and Fake Anchor are wired onto `on_block_cleared` as their compensation
  for `turn_structure/G6`, so a Barricaded player never re-arms them.
- **pin** `TestTurnStructureOrder::test_block_clear_event_fires_even_when_prevented`.
- **fix** Split the fused arm: clear the block under `should_clear_block`, then
  fire `on_block_cleared` unconditionally for every participant, in a second pass
  over the same list (`player.py:157-159` and `combat.py:296-298`). Failing test
  asserts `on_block_cleared` fires for a Barricaded player.
- **radius** `turn_structure/G2` (the missing preventer identity) and
  `turn_structure/G6` (turn-1 clear) are the same three lines of `player.py`;
  land all three in one pass. Content: Anchor, Fake Anchor, Barricade, Sturdy
  Clamp, Orichalcum.

### 16. `turn_structure/G2` — no `after_preventing_block_clear`, no preventer identity  [LIVE] [pinned]

- **sites** `turn_structure/step13`, `/G2` (2 entries).
- **impact** B — Sturdy Clamp caps block it should not cap.
- **divergence** `Creature.ClearBlock` (`Creature.cs:718-728`) passes the vetoing
  listener out of `Hook.ShouldClearBlock` and fires
  `Hook.AfterPreventingBlockClear(preventer, creature)` on the else-arm;
  `SturdyClamp.cs:31-46` caps the retained block at 10 there and guards
  `if (this != preventer || creature != Owner.Creature) return`. The sim's
  `hooks.should_clear_block` (`hooks.py:613-619`) returns a bare bool, so
  `relics/sturdy_clamp.py:27-30` caps from `on_player_turn_start` instead — with
  no preventer test and at a different point in the turn (`player.py:169`, after
  the energy reset at 163-168).
- **observable** With Barricade active, the sim's Sturdy Clamp caps the retained
  block at 10 even though Barricade, not Sturdy Clamp, prevented the clear; C#
  leaves it uncapped.
- **pin** `TestTurnStructureOrder::test_sturdy_clamp_does_not_cap_when_it_is_not_the_preventer`.
- **fix** Make `should_clear_block` return `(bool, preventer)` like the sim's
  `should_die`/`preventer` pattern already does (`cmds.py:96-112`), add
  `after_preventing_block_clear(preventer, creature)`, and move Sturdy Clamp's
  cap onto it. Failing test asserts Barricade + Sturdy Clamp keeps 30 block.
- **radius** `turn_structure/G1` (same lines), `damage_pipeline/G4` (the sim's
  other preventer-shaped hook). The `should_die` preventer out-param is the
  template to copy.

### 17. `turn_structure/G6` — the sim clears the player's block on turn 1  [LIVE] [pinned]

- **sites** `turn_structure/step12`, `/G6` (2 entries).
- **impact** B — pre-combat block evaporates before the first enemy turn.
- **divergence** `Creature.AfterTurnStart` returns **before** `ClearBlock` for a
  player whose `PlayerCombatState.TurnNumber == 1` (`Creature.cs:681-692`), which
  is what lets `Hook.BeforeCombatStart` grant block that survives into the first
  enemy turn; `player.py:157-159` has no turn-1 arm.
- **observable** A player holding 10 block at the first `start_turn`
  (`_first_turn = True`) ends it with 0. Anchor's real hook is
  `BeforeCombatStart` (`Anchor.cs:19-23`) and the sim had to re-wire it onto
  `on_block_cleared` to compensate (`relics/anchor.py:21-24`, whose docstring says
  so) — as did Fake Anchor (`relics/fake_anchor.py:24-29`). That workaround is
  itself what makes `turn_structure/G1` bite those two relics.
- **pin** `TestTurnStructureOrder::test_player_block_is_not_cleared_on_turn_one`.
- **fix** Add the turn-1 early return to `player.start_turn`'s block-clear arm,
  then un-rewire Anchor and Fake Anchor back onto a `before_combat_start` hook.
  Failing test asserts a player granted 10 block before combat still has it when
  the first enemy attacks.
- **radius** `turn_structure/G1`, `/G2` (same three lines), `/G14` (the other
  turn-1-only branch in `player.start_turn`). Content: Anchor, Fake Anchor.

### 18. `turn_structure/G4` — a false `ShouldFlush` skips the whole flush tail  [LIVE] [pinned]

- **sites** `turn_structure/step61`, `/G4` (2 entries).
- **impact** B — a deferred exhaust credit is never paid.
- **divergence** C#'s `FlushPlayerHand` treats `ShouldFlush == false` as "every
  card is retained" — `cardsToFlush` is empty and the batched Add is skipped — but
  it still runs `Hook.AfterFlush(..., cardsToFlush, cardsToRetain)` **and**
  `PlayerCombatState.EndOfTurnCleanup()` (`CombatManager.cs:1327-1346`); the sim
  guards the whole thing: `if self.hooks.should_flush_hand(): self.player.discard_hand()`
  (`combat.py:661-662`).
- **observable** The live path is the sim's `on_hand_emptied`, fired from inside
  `discard_hand` (`player.py:197`): Joss Paper defers Ethereal-caused exhausts and
  credits them from `on_hand_emptied` (`relics/joss_paper.py:41-45`), so with a
  retain effect suppressing the flush the credit is silently dropped.
- **pin** `TestTurnStructureOrder::test_no_flush_still_credits_the_end_of_turn_hand_events`.
- **fix** Unconditionally run the flush *tail* — the after-flush hooks and the
  end-of-turn cleanup — and let `should_flush_hand` decide only which cards move.
  Failing test asserts Joss Paper's credit lands on a no-flush turn.
- **radius** `turn_structure/G16` (`on_hand_emptied` fired from the one site C#
  excludes) and `/G17` (Joss Paper's cause proxy) are the same relic's other two
  gaps — all three should be read together before touching `joss_paper.py`.
  `turn_structure/G7` (`EndOfTurnCleanup` has no counterpart at either site) is
  the missing tail itself.

### 19. `turn_structure/G17` — Joss Paper's `causedByEthereal` proxy is the card, not the cause  [LIVE] [pinned]

- **sites** `turn_structure/G17` (1 entry).
- **impact** B — a mid-turn exhaust credit is withheld until the flush.
- **divergence** C#'s `AfterCardExhausted` takes the cause as a parameter —
  `AfterCardExhausted(ctx, card, bool causedByEthereal)` (`JossPaper.cs:102-114`,
  dispatched from `CardCmd.cs:237-244` / `Hook.cs:237-242`) — and
  `causedByEthereal: true` is passed from exactly two sites in the whole game,
  both at turn end (`CombatManager.cs:1240`, `CardModel.cs:1692`). The sim has no
  cause parameter: `relics/joss_paper.py:36` branches on `card.is_ethereal`, a
  property of the *card*.
- **observable** An Ethereal card exhausted in the middle of the play phase is
  booked to `_ethereal_pending` and its credit withheld until `on_hand_emptied`
  fires from the flush; the game credits it at once.
- **pin** `TestTurnStructureOrder::test_joss_paper_credits_a_mid_turn_ethereal_exhaust_at_once`.
- **fix** Add a `caused_by_ethereal: bool = False` parameter to
  `hooks.on_card_exhausted` and pass `True` only from the two turn-end sites
  (`combat.py`'s ethereal exhaust pass and the turn-end-in-hand wrapper); switch
  `joss_paper.py:36` to read it. Failing test asserts a mid-turn Ethereal exhaust
  credits immediately.
- **radius** `turn_structure/G4`, `/G16` (the same relic), `creature_card_cmds/G8`
  (pile-change events generally).

### 20. `turn_structure/G18` — Pael's Eye's predicate is missing both C# clauses  [LIVE] [pinned]

- **sites** `turn_structure/G18` (1 entry).
- **impact** B — an extra turn is granted (or withheld) on the wrong turn.
- **divergence** `PaelsEye.AnyCardsPlayedThisTurn` (`PaelsEye.cs:149-156`) has two
  clauses `relics/paels_eye.py:27-34` has neither of: (1) on turn 1, merely
  *holding* Whispering Earring counts as having played (`PaelsEye.cs:152`), which
  switches Pael's Eye off for that turn; (2) the history scan filters
  `&& !e.CardPlay.IsAutoPlay`, so auto-plays never count. The sim's predicate is a
  bare `any(history.of_type(CardPlayedEntry, this_turn=True))` and
  `history.py:80-81` records every play including auto-plays.
- **observable** The record notes the two omissions **cancel** in the common
  Whispering-Earring case and diverge otherwise — read the record's full text
  before writing the test.
- **pin** `TestTurnStructureOrder::test_paels_eye_ignores_auto_plays`.
- **fix** Give `CardPlayedEntry` an `is_auto_play` flag (the missing flag is
  already documented as a known divergence at `relics/whispering_earring.py:36`),
  filter on it in `paels_eye.py:27-34`, and add the turn-1 Whispering Earring
  short-circuit. Failing test asserts an auto-played card does not suppress the
  extra turn.
- **radius** `turn_structure/G3` (the extra turn itself), `hook_dispatch/G4` (the
  per-play bracket that produces the history entries).

### 21. `monster_state_machine/G4` — a stun is not a real move  [LIVE] [pinned]

- **sites** `monster_state_machine/step39`, `/step40`, `/step44` (3 entries;
  clauses a/b/c of one mechanism).
- **impact** A — the following turn's move distribution differs.
- **divergence** `Creature.StunInternal` (`Creature.cs:524-544`) builds a real
  `MoveState("STUNNED", stunMove, new StunIntent())` with
  `FollowUpStateId = nextMoveId` and `MustPerformOnceBeforeTransitioning = true`,
  hands it to `SetMoveImmediate`, and the deferred move is **re-logged** on the
  next roll; the sim models only the intent half —
  `MachineMonster.current_intent` special-cases `self.stunned`
  (`sts2_rl/monsters/state_machine.py:315-318`).
- **observable** The deferred move never re-enters `state_log`, so every
  weight-reads-the-log branch downstream sees a different history. Route is
  executed end to end (`probe whistle-route`): Whistle (`cards/whistle.py:38`) is
  the only sim stun site taking an external target, it comes only from Tanx's
  Whistle, Tanx is in **Glory**'s ancient keys only, and four Glory monsters have
  log-reading branch weights — Scroll of Biting (the cleanest, executed at 100000
  rolls), Flail Knight, Spectral Knight, Soul Nexus.
- **pin** `TestMonsterStateMachineOrder::test_stun_makes_the_stun_a_move_and_relogs_the_deferred_one`.
- **fix** Build the stun as a real `MoveState` in `state_machine.py` —
  performed, pinned by `must_perform_once_before_transitioning`, logged — and let
  the next roll transition `STUNNED → next` with no branch draw. `CreatureCmd.stun`
  (`cmds.py:208-218`) becomes a machine operation for `MachineMonster` instead of
  a boolean. Failing test asserts the stunned turn logs `STUNNED` and the next
  turn re-logs the deferred move without drawing.
- **radius** `monster_state_machine/G5` (the `next_move_key` override is silently
  dropped for a `MachineMonster` — same fix site), `/G6` (FlutterPower's splice),
  and `turn_structure/G9` (the stunned-turn draw count). **These four are one
  work package**: they are all "what happens to the machine when a monster is
  stunned", and fixing them separately risks fixing the draw count twice.

### 22. `power_cmd/step20` — `skip_next_tick` re-armed on re-stacking  [LIVE] [pinned]

- **sites** `power_cmd/step20` (1 entry).
- **impact** B — a player debuff lasts one turn longer than it should.
- **divergence** `cmds.py:331-332` sets `power.skip_next_tick = True` at function
  scope, **after** the new-vs-stacking if/else (`cmds.py:308-329`), on the shared
  `power` variable the stacking branch rebinds to `existing` — so the sim re-arms
  it on every re-stack; C# sets `SkipNextDurationTick` only in the new-power
  `Apply` path (`PowerCmd.cs:144-147`) and `ModifyAmount` (`PowerCmd.cs:215-271`)
  never touches it.
- **observable** Any player debuff applied twice in one turn (a second Vulnerable
  or Weak stack) skips a duration tick it should have taken, so it expires a turn
  late.
- **pin** `TestPowerCmdOrder::test_restacking_a_player_debuff_does_not_rearm_skip_next_tick`.
- **fix** Move the two lines inside the new-power branch of `PowerCmd.apply`.
  One-line-scope change, no hook machinery. **Cheapest live fix in the queue.**
  Failing test asserts a twice-applied Vulnerable expires on the same turn as a
  once-applied one plus its stacks.
- **radius** Same function as `power_cmd/G1` (Artifact's sign-aware typing),
  `/G3` (given/received phase collapse), `/G6` (the missing guards) — but
  independent of all three.

### 23. `creature_card_cmds/step38a` — Dense Vegetation's rest heal bypasses both rest hooks  [LIVE] [pinned]

- **sites** `creature_card_cmds/step38a` (1 entry).
- **impact** B — a rest-site reward offer is skipped entirely.
- **divergence** C# (`PlayerCmd.cs:264-274` → `HealRestSiteOption.cs:106-113`)
  heals, then fires `Hook.AfterRestSiteHeal(player, isMimicked)` and
  `Hook.ModifyRestSiteHealRewards`, then offers the resulting rewards; the sim's
  `events/dense_vegetation.py:65-68` calls `self.run.heal(...)` directly, skipping
  `RunState.rest_heal` (`run.py:1089-1095`, which fires `after_rest_site_heal`) and
  `RunState.rest_heal_rewards` (`run.py:1097-1110`).
- **observable** The one gameplay caller of `MimicRestSiteHeal` is
  `Events/DenseVegetation.cs:90` and the event **is** ported: resting via Dense
  Vegetation heals but grants none of the rest-site reward machinery a real
  campfire rest grants.
- **pin** `TestCreatureCardCmdsOrder::test_dense_vegetation_rest_fires_the_rest_site_heal_hooks`.
- **fix** Point `dense_vegetation.py:65-68` at `run.rest_heal()` and
  `run.rest_heal_rewards()` instead of `run.heal()`. Failing test asserts the
  after-rest hooks fire and the reward offer appears.
- **radius** Isolated — one event, two call sites. Cheapest B-impact fix here.
