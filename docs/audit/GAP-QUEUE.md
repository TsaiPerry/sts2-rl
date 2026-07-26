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
  and Spiked Gauntlets (`relics/spiked_gauntlets.py:26-31`, ported Tanx shrine —
  the record cites `26-32`, one line past the end of the file)
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

- **sites** `turn_structure/step65`, `/step68`, `/G3`, plus `turn_structure/N4`
  and `turn_structure/step66` — RoundNumber vs TurnNumber, which the record says
  carries G3's precedence (5 entries).
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


---

# Tier 2 — dormant gaps

67 mechanisms are dormant at every recorded site: the divergence is real and
verified, but no currently-ported content reaches it. Each names the concrete
thing that makes it live (collected in the watch list below). Ordered by
seed-convergence exposure first, then by blast radius.

## 2A. Parity-relevant dormant gaps — extra or off-stream RNG draws

These are labelled dormant because no *gameplay* effect differs today, but each
one takes a draw the game does not take, or takes it from the wrong stream.
Under legacy single-stream RNG that is invisible; under seed parity it is a
desync. **Read this group before the next conformance grind.**

### 24. `creature_card_cmds/N10` + `/step104` — CardSelectCmd's auto-select shortcut  [DORMANT / parity-live] [unpinned]

- **sites** `creature_card_cmds/step104`, `/step105`, `/N10` (3 entries; step 105 sits under N10).
- **divergence** C#'s auto-select shortcut (`!prefs.RequireManualConfirmation &&
  candidateCount <= prefs.MinSelect` -> return every candidate in pile order,
  `CardSelectCmd.cs:287-290, 396-399, 708-711`) consumes **nothing** from any
  stream; `CombatState.select_cards` (`combat.py:560-581`) has no shortcut — it
  clamps `count = min(count, len(candidates))` (`combat.py:577`) and, with no
  `card_selector` installed, falls through to `self._rng.sample(candidates, count)`
  (`combat.py:581`).
- **observable** The same *membership*, reached by burning draws C# never takes,
  **and taking them off-stream** on the shared legacy `random.Random` rather than
  `combat_rng.card_selection`. Also missing: the MinSelect/MaxSelect range, the
  `RequireManualConfirmation` flag, and C#'s draw-pile pre-sort
  (`CardSelectCmd.cs:403-408`) — an installed selector sees the true draw order
  where C#'s would see a rarity/id sort.
- **trigger** Already reachable in any replay containing a forced full-hand
  selection; "dormant" here means no *gameplay* divergence, not no desync.
- **pin** unpinned. A conformance-side pin is the right home, not `test_hook_order.py`.
- **fix** Add the auto-select shortcut to `select_cards` (return all candidates,
  in pile order, drawing nothing) and move the fallback onto
  `combat_rng.card_selection`. Failing test: a forced selection of every
  candidate consumes zero draws from any stream.
- **radius** `creature_card_cmds/step99` (`AutoPlayFromDrawPile`'s two-phase
  structure), `/G10` (shuffle order). Any replay through a grid/selection screen.

### 25. `creature_card_cmds/step55` — the in-combat transform rolls off-stream  [DORMANT / parity-live] [unpinned]

- **divergence** `CardCmd.transform_to_random` (`cmds.py:415-450`) rolls its
  replacement on `hooks.combat._rng` (`cmds.py:435`) — the shared legacy
  `random.Random` — where C# takes an explicit `Rng` argument
  (`CardCmd.cs:323, 369`). It also searches only hand/draw/discard/exhaust and
  returns `None` for a card mid-play, because the sim has no Play pile.
- **observable** Every in-combat transform in a conformance replay draws from the
  wrong stream. Dormant for the Play-pile half (Entropy, the only ported
  in-combat transformer, targets the hand).
- **trigger** Any conformance replay containing an in-combat transform; the
  Play-pile half needs a transformer that can target a resolving card.
- **pin** unpinned.
- **fix** Route the roll through the appropriate `combat_rng` stream (mirror what
  `CardCmd.cs` passes at each call site) and teach the pile search about
  `player._playing_card`. Failing test: an Entropy transform consumes a draw from
  the named stream and none from the legacy rng.
- **radius** Tier 1 #9 (`creature_card_cmds/G3`), `/step56` (`PileIndexSort`),
  `/N9` (no Play pile).

### 26. `creature_card_cmds/G10` — `ModifyShuffleOrder` modelled as an `AfterShuffle` listener  [DORMANT / parity-live] [unpinned]

- **sites** `creature_card_cmds/step93`, `/step102b`, `/G10` (3 entries).
- **divergence** C# mutates the shuffled list **inside** the shuffle, on the
  shuffled-but-not-yet-placed list, strictly before `AfterShuffle`
  (`CardPileCmd.cs:876-877` vs `917`), and the combat-start randomize calls it too
  with `isInitialShuffle: true` (`CardPile.cs:69-74`); the sim has no
  `modify_shuffle_order` hook at all, so `PerfectFitEnchantment` hand-rolls the
  reposition on `on_shuffle` (`enchantments.py:186-189`) and the net order is
  decided by hook-registration order.
- **observable** Draw order after a reshuffle — the most convergence-sensitive
  thing in the engine — is decided by registration order rather than by C#'s fixed
  call sequence. `step102b` adds that `RandomizeOrderInternal` is an **Unstable**
  shuffle (no stabilising sort) plus its own `ModifyShuffleOrder`.
- **trigger** A second `on_shuffle` listener that also repositions, or any
  reshuffle in a replay where Perfect Fit is enchanted.
- **pin** unpinned.
- **fix** Add a real `modify_shuffle_order(pile, cards)` hook called from inside
  the shuffle before placement, and move Perfect Fit onto it. Failing test: with
  Perfect Fit plus one other repositioning listener the post-shuffle order matches
  C#'s call sequence regardless of registration order.
- **radius** `creature_card_cmds/N9` (Play-pile limbo already changes which cards
  a reshuffle sees), `/G9` (draw prevention).

### 27. `monster_state_machine/G6` — one machine roll on the wrong stream  [DORMANT] [pinned]

- **sites** `monster_state_machine/step35`, `/step41` (2 entries).
- **divergence** `MonsterModel.RollMove` uses the dedicated `RunRng.MonsterAi`
  stream (`MonsterModel.cs:415-418`). SP3 already moved both machine roll sites
  onto `monster_ai`; **one** off-stream site survives — `powers.py:2233` passes
  `self.owner._rng`, the shared combat `random.Random`. Clause (b): the sim's
  `roll_move` walks all the way to a `MoveState` and so **consumes a branch draw**
  where `FlutterPower.cs:47` consumes none (`MoveState.GetNextState` is
  deterministic).
- **trigger** `FlutterPower` reaching a monster whose machine has a
  `RandomBranchState`. Its only applier on both sides is Thieving Hopper, whose
  machine is a pure deterministic chain (`thieving_hopper.py:61-65`).
- **pin** `TestMonsterStateMachineOrder::test_flutter_stun_splice_consumes_no_shared_stream_draw`
  (the first pass labelled this LIVE and the pin itself refuted that by XPASSing).
- **fix** Pass `combat_rng.monster_ai` at `powers.py:2233` and give the splice a
  deterministic "ask the last logged state for its follow-up" path that does not
  advance the machine. Failing test asserts zero shared-stream draws.
- **radius** Tier 1 #2 (`turn_structure/G9`), Tier 1 #21 (`/G4`).

## 2B. Missing guard families

### 28. `hook_dispatch/G8` — no `IsEnding` / `IsOverOrEnding` dispatch gate  [DORMANT] [pinned]

**The largest mechanism in the queue: 22 entries across three records.**

- **sites** `hook_dispatch/step19`, `/step20`, `/step21`;
  `creature_card_cmds/step1`, `/step7`, `/step11`, `/step48`, `/step54`,
  `/step63`, `/step71`, `/step72`, `/step74`, `/step83`, `/step90`, `/step103b`,
  `/G14`; `power_cmd/step1`, `/step2`, `/step6`, `/step16`, `/step24`, `/G6`.
- **divergence** `Hook.IterateCombatHookListeners` (`Hook.cs:53-63`) yields
  **nothing** to a dispatch that begins after combat started ending, and 73 of the
  147 dispatchers go through it; separately, every C# command in
  `creature_card_cmds`' scope opens with its own liveness check
  (`CreatureCmd.Add` 55-67, `Escape` 585-588, `GainBlock` 637-640, `Heal` 693-696,
  `CardCmd.Discard` 174-177, `Downgrade` 214, `Transform` 371-374,
  `CardPileCmd.Add` 308-319, `Draw` 800-803, `Shuffle` 866-869 ...), and
  `PowerCmd.Apply`/`ModifyAmount` check `IsEnding` twice (`PowerCmd.cs:69-72`,
  `217-220`) plus `CanReceivePowers` (`73-76`, `133`). The sim has no gate
  anywhere: `combat.py` flips `Phase.COMBAT_OVER` only inside `_end_combat` and no
  dispatcher or command consults it.
- **observable** Executed: with Daughter of the Wind
  (`relics/daughter_of_the_wind.py:23-33`) a lethal Strike still grants its 1 Block
  from `on_card_played` after `_all_enemies_dead()` is true.
- **trigger** Porting a listener on a guarded dispatcher that mutates **run-level**
  state (HP, gold, deck) from `AfterCardPlayed`/`AfterCardDrawn`/
  `AfterCardExhausted`/`AfterShuffle`/`AfterEnergySpent`. The record names the
  conformance exporter as the near-term risk.
- **pin** `TestHookDispatchOrder::test_no_listener_runs_after_the_combat_starts_ending`
  and `TestCreatureCardCmdsOrder::test_select_cards_refuses_once_the_combat_is_over`.
- **fix** One gate in `HookSystem`'s dispatch helper (`if combat is ending and not
  starting: return`) plus a shared `_assert_live()` helper on the command module.
  Both are cheap; the risk is that the existing suite relies on post-combat
  dispatches being harmless. Land it behind the two pins.
- **radius** Tier 1 #7 (`turn_structure/G13`) and `/G10` decide *when* the gate
  closes, so all three should be designed together. `power_cmd/G6` also carries the
  missing `CanReceivePowers` half — that needs `should_allow_hitting` wired into
  the power pipeline, not just a phase check.

### 29. `damage_pipeline/G5` — no dealer-dead / target-dead entry guard  [DORMANT] [unpinned]

- **sites** `damage_pipeline/step1`, `/step3`, `/G5` (3 entries).
- **divergence** `CreatureCmd.Damage` refuses any hit from an already-dead dealer
  (`CreatureCmd.cs:242-245`) and skips an already-dead target in its per-target
  loop (`256-259`); `DamageCmd.deal` has neither and relies on call-site discipline
  (`monsters/base.py:114-117`, `cards/whirlwind.py:43-49`, both correct on
  spot-check).
- **trigger** A new multi-hit or multi-target effect that forgets the check.
- **pin** unpinned. **fix** two `if ... return` guards at the top of
  `DamageCmd.deal`; failing test drives a hit from a dead dealer and asserts zero
  hooks fire. **radius** `power_cmd/G6` is the same backstop absence on the power
  pipeline; `damage_pipeline/N1` (the sim-only `should_allow_hitting` pre-check) is
  the deliberate-divergence beside it.

### 30. `creature_card_cmds/N3` — the `CardPileAddResult` failure surface is unmodelled  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step70`, `/step73`, `/N3` (3 entries; `/step72` is
  also a site).
- **divergence** C#'s `Add` returns a per-card result carrying
  success/oldPile/modifyingModels and sets `success = false` for a dead owner, a
  removed-from-state card, a detached combat card, or a `ShouldAddToDeck`
  prevention (`CardPileCmd.cs:322-397`); the sim's three pile helpers
  (`cmds.py:463-512`) return `None` and always succeed. The behaviourally
  significant one is `creature.IsDead -> success = false`
  (`CardPileCmd.cs:329-340`): C# silently drops a card generated onto a dead
  player, the sim appends it.
- **trigger** `ShouldAddToDeck`/`AfterAddToDeckPrevented` have zero overrides
  game-wide, so the trigger is porting the first one — or any card generation that
  can outlive the player's death (the sim ends combat as soon as the player dies,
  `combat.py:419-420`).
- **pin** unpinned. **fix** return a small result object from the pile helpers and
  honour the dead-owner drop. **radius** `hook_dispatch/G8`, `/N4`.

### 31. `creature_card_cmds/N4` — no duplicate-instance guard on any pile insert  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step102c`, `/N4` (2 entries).
- `CardPile.AddInternal` throws if the pile already holds that `CardModel`
  instance and `RemoveInternal` throws if it does not (`CardPile.cs:86-89,
  117-120`); the sim's piles are plain lists with no invariant — which is what lets
  `/G7`'s double-membership bug exist silently.
- **pin** unpinned. **fix** assert the invariant in the three pile helpers.
  **radius** `/G7` is the verb-level symptom of this container-level hole; fix N4
  first and G7 becomes a loud failure instead of a silent one.

### 32. `creature_card_cmds/N2` — `afflict` skips ShouldAfflict / CanAfflict / AfterApplied  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step64`, `/step65`, `/N2` (3 entries).
- `CardCmd.Afflict` guards on `Hook.ShouldAfflict` and `affliction.CanAfflict(card)`
  and fires an `AfterApplied` lifecycle event (`CardCmd.cs:627-634` ff.); the sim
  has no surface for any of the three and returns `None` where C# throws.
  `ShouldAfflict` has zero overrides game-wide; `CanAfflict` has no sim surface at
  all. Trigger: porting any affliction with a `CanAfflict` restriction.
- **radius** `hook_dispatch/G6` (afflictions are not listeners at all), `/G8`.

### 33. `creature_card_cmds/N5` + `/step31` — `EnergyCmd.gain` lacks the `finalAmount > 0` guard  [DORMANT] [unpinned]

`PlayerCmd.cs:37-41` adds energy only when the modified amount is positive;
`cmds.py:553-554` does `player.energy += amount` unconditionally, so a modifier
returning a negative value would subtract energy. The only ported
`modify_energy_gain` listener returns 0 (`NoEnergyGainPower`,
`powers.py:554-557`), a no-op under both rules. One `if final > 0` guard.

## 2C. Missing hook surfaces

### 34. `creature_card_cmds/G8` — no `AfterCardChangedPiles` at all  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step69`, `/step81`, `/step89`, `/step96`, `/G8`
  (5 entries; `/step59` is also a site).
- **divergence** Every C# pile move funnels through it (`CardPileCmd.cs:635` Add,
  `188` RemoveFromCombat, `683` manual play, `CardCmd.cs:447` transform); the sim
  has one hook per transition (`on_card_drawn`, `on_card_discarded`,
  `on_card_exhausted`, `on_card_entered_combat`) plus a deck-only relic shim
  (`relics/base.py:208-210`), and nothing observes an arbitrary pile-to-pile move.
- **trigger** All four ported C# listeners filter to `pile.Type == Deck`, so the
  shim covers them everywhere except the transform path (Tier 1 #9). The three C#
  listeners that watch **combat** piles — `SovereignBlade`, `Hoarder`, `SoulFysh`
  — are unported; porting any makes this live.
- **pin** unpinned. **fix** add `on_card_changed_piles(card, old_pile, new_pile)`
  and fire it from the three pile helpers. **radius** Tier 1 #9, `/G11`,
  `hook_dispatch/G1`.

### 35. `creature_card_cmds/G12` + `/step34` — no gold-gain hook surface  [DORMANT] [unpinned]

`PlayerCmd.GainGold` fires `ModifyGoldGained` -> `AfterModifyingGoldGained` ->
`AfterGoldGained` (`PlayerCmd.cs:144-169`); `RunState.gain_gold`
(`run.py:325-333`) runs a relic `modify_gold_gained` loop and nothing else. The
consequence is visible **today**: `DragonFruit.cs:22-29` grants +1 Max HP on every
gold gain and is a ported relic whose sim implementation is an inert stub
(`relics/dragon_fruit.py`, docstring still claiming "no gold system" although
`run.gold` exists). Fix: add `after_gold_gained(amount)` to the run-side surface
and un-stub Dragon Fruit. **radius** `damage_pipeline/G2` (the
`AfterModifyingGoldGained` variant), `hook_dispatch/N5` (no run-level listener
list to hang it on).

### 36. `creature_card_cmds/G11` + `/step49` — `AfterCardDiscarded` fires pre-move and in a batch  [DORMANT] [unpinned]

C# adds each card to the discard pile **first**, then fires the hook, one card at
a time (`CardCmd.cs:186-195`); `discard_hand` (`player.py:192-196`) fires
`on_card_discarded` for every flushed card while they are all still in `hand`,
then moves them as a batch. Executed: flushing `[Strike, Defend]` records
`[('strike', in_hand=True, in_discard=False), ('defend', in_hand=True,
in_discard=False)]` at hook time; C# would give `(False, True)` for each and would
have moved Strike before Defend's hook ran. Trigger: any `on_card_discarded`
listener that reads pile membership. Fix: interleave move-then-fire.

### 37. `creature_card_cmds/G9` + `/step84` — `ShouldDraw` re-evaluated per card, no `AfterPreventingDraw`  [DORMANT] [unpinned]

`CardPileCmd.Draw` evaluates `Hook.ShouldDraw` exactly once before the loop and
fires `Hook.AfterPreventingDraw` on refusal (`CardPileCmd.cs:804-808`);
`player.py:280-281` calls `should_draw` inside the per-card loop and has no
`after_preventing_draw`. Trigger: a `should_draw` listener that flips mid-draw —
Fiddle (`relics/fiddle.py:26-29`) is the only ported one and is stateless. Fix:
hoist the check; add the hook.

### 38. `creature_card_cmds/step12` — no `BeforeBlockGained`  [DORMANT] [unpinned]

C#'s unconditional pre-modifier event carrying the raw amount
(`CreatureCmd.cs:642`, `Hook.cs:131-137`) has no sim surface. Zero overrides
game-wide today; live the moment any model implements it. One dispatcher to add.

### 39. `creature_card_cmds/step46` — no `BeforeCardAutoPlayed`  [DORMANT] [unpinned]

`combat.py:552` fires `on_energy_spent(card, 0)` and then the ordinary
`before_card_played`; the auto-play-only event is absent and none of its C#
implementations is ported. **radius** `hook_dispatch/G4` (the per-play bracket).

### 40. `creature_card_cmds/step61` — no `AfterCardGeneratedForCombat` on transform  [DORMANT] [unpinned]

`cmds.py:445-450` fires only `on_card_entered_combat`; C# fires **both** events for
a combat-pile transform (`CardCmd.cs:445` and `504`). None of the seven C#
implementations is ported.

### 41. `creature_card_cmds/step68` — no `BeforeCardRemoved`, no removed-from-state marking  [DORMANT] [unpinned]

`RunState.remove_cards` (`run.py:356-358`) is a bare `self.deck.remove(card)` loop.
No ported listener, and the sim's cards carry no `HasBeenRemovedFromState` flag for
anything to read — which is also why `hook_dispatch/G7` cannot be implemented as
C# does it.

### 42. `turn_structure/step20` — no `AfterModifyingHandDraw`  [DORMANT] [unpinned]

`modify_hand_draw` is ported with the same base of 5 (`player.py:171`), but the
companion event is absent. C# has four implementers; the two ported ones are
presentation-only (`Pocketwatch.cs:67-71` is a bare `Flash()`). This is one of
`damage_pipeline/G2`'s 13 variants.

### 43. `turn_structure/step55` — no `BeforeFlush`  [DORMANT] [unpinned]

No slot between `_process_turn_end_cards` (`combat.py:658`) and the flush
(`661-662`). C#'s three implementers (`SlumberingEssence.cs`,
`WellLaidPlansPower.cs`, a mock) are unported. **radius** Tier 1 #18.

### 44. `turn_structure/G11` + `/step37` — no enemy-side `BeforeTurnEnd` slot  [DORMANT] [unpinned]

C# fires the same three-pass `BeforeTurnEnd` dispatcher for the enemy side
(`CombatManager.cs:1251`); the sim has only per-enemy `on_enemy_turn_end`
(`combat.py:341`) and side-scoped `on_enemy_side_end` (`345`), with no slot
between them. Eight C# powers implement a `BeforeSideTurnEnd*` phase
(`AsleepPower`, `PlatingPower`, `ChainsOfBindingPower`, `DoomPower`,
`HailstormPower`, `SandpitPower`, `TheBombPower` + a mock); none is ported onto
that slot. **radius** Tier 1 #13, `hook_dispatch/G3`.

### 45. `turn_structure/G16` — `on_hand_emptied` fires from the one site C# excludes  [DORMANT] [unpinned]

- **sites** `turn_structure/step63`, `/step73`, `/G16` (3 entries).
- C#'s `CheckForEmptyHand` (`CombatManager.cs:887-893`) is called **only** after a
  card play and after a potion use, gated on `IsExecutingCardOrPotionEffect` and
  the player's phase; `UnceasingTop.cs:25-35` carries a source remark explaining
  why the draw and the flush must not trigger it. The sim's `on_hand_emptied` has
  exactly one call site — `player.py:197`, at the bottom of `discard_hand`, i.e.
  the flush — and none after a play or potion.
- **trigger** Porting Unceasing Top, or any listener that draws on an empty hand.
- **radius** Tier 1 #18 and #19 (Joss Paper leans on the flush firing it).

### 46. `turn_structure/G7` + `/step38` — `EndOfTurnCleanup` has no counterpart at either site  [DORMANT] [unpinned]

C# runs it twice per round — end of the enemy turn for every player
(`CombatManager.cs:1252-1255`) and inside each `FlushPlayerHand` (`1346`) —
clearing `ExhaustOnNextPlay`, `HasSingleTurnRetain`, `HasSingleTurnSly` and the
turn-scoped cost modifiers in **every** pile (`PlayerCombatState.cs:268-274`,
`CardModel.cs:1610-1623`). The sim's only per-turn card reset
(`cards/base.py:265-269`) clears three cost fields and runs at the **start** of the
next player turn (`player.py:153-155`). Two consequences: the reset window is a
full enemy turn wider than the game's, and single-turn Retain / Sly /
ExhaustOnNextPlay do not exist at all. **radius** Tier 1 #18 (the flush tail that
should run it), `creature_card_cmds/step51` (Sly is unported).

### 47. `turn_structure/step8` — no per-power `AmountOnTurnStart` snapshot  [DORMANT] [unpinned]

`grep -rn amount_on_turn_start sts2_rl/` returns 0 hits. C# snapshots every power's
amount before anything else in the turn (`CombatManager.cs:449-455`,
`Creature.cs:673-679`) and three powers read it, two ported:
`DrawCardsNextTurnPower` (`AmountOnTurnStart == 0` suppresses both the extra draw
and the removal, `DrawCardsNextTurnPower.cs:28,37`) and `HelloWorldPower`. The
sim's `DrawCardsNextTurnPower` (`powers.py:2737-2754`) has no such guard, so a
stack applied during the turn-start window would draw and expire in the same turn.

### 48. `turn_structure/step17` — the two energy hooks fire in the opposite order  [DORMANT] [unpinned]

The arithmetic matches (`player.py:163-167`) but the sim calls `modify_max_energy`
first and `should_reset_energy` second, where C# evaluates
`ShouldPlayerResetEnergy` first and reads `MaxEnergy` inside the chosen branch
(`CombatManager.cs`). Unobservable while both dispatchers are pure aggregations;
live with the first side-effecting implementation of either.

### 49. `hook_dispatch/step37` — the predicate family short-circuits in the sim  [DORMANT] [unpinned]

C# uses `flag = flag || item.ShouldX(...)` with **no** short-circuit, calling every
listener (`Hook.cs:2472-2480` `ShouldForcePotionReward`, `2485-2493`
`ShouldAllowFreeTravel` — those are the only two); the sim aggregates with a
short-circuiting `any(...)` (`rewards.py:449`). Each hook has exactly one
implementer today (`WhiteBeastStatue.cs`, `WingedBoots.cs`), both side-effect free.
Trigger: a second ported implementer with a side effect.

## 2D. Listener-registry shape

### 50. `hook_dispatch/G7` — no per-item liveness re-check  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step4`, `/step11`, `/step12`, `/step16`, `/step45` (5 entries).
- **divergence** C# yields `if (Contains(item))` **lazily, per item**
  (`CombatState.cs:482-488`), and `Contains` (`549-599`) drops any
  relic/potion/card/affliction/enchantment/orb whose `HasBeenRemovedFromState` is
  set or whose owner is not `IsActiveForHooks`; every sim dispatcher walks a
  `list(self._listeners)` snapshot with no re-check.
- **observable** Dormancy is *executed and reproducible from the committed tree*:
  `py -m pytest test/ -q -p tools.audit.stale_listener_plugin` instruments every
  listener call with C#'s lazy re-check. The only hit across the suite is
  `on_enemy_side_end -> IntangiblePower`. **Caveat: the record quotes that run as
  "2476 passed / 30 xfailed", which is a stale tree — the suite is 2478 passed /
  38 xfailed today. Re-run before relying on the number.**
- **trigger** Any listener that removes another listener mid-dispatch.
- **fix** Needs Tier 1 #5's derived listener list plus a `HasBeenRemovedFromState`
  flag on cards/relics (`creature_card_cmds/step68`).
- **radius** `hook_dispatch/G2`, `/G1`, `/G5`, `/G6`, `/N5` — the registry-shape
  family lands together or not at all.

### 51. `hook_dispatch/G1` — card listener order frozen at combat start  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step9`, `/step44` (2 entries).
- `CombatState.cs:449-467` walks `AllPiles` = Hand, Draw, Discard, Exhaust, Play
  (`PlayerCombatState.cs:70-80`) on **every** dispatch, so a card that moves pile
  moves position in the listener list; `combat.py:124` registers `player.all_cards`
  once, in a fixed order (`player.py:100-103`), and never reorders. Dormancy
  executed: card classes implement only six hooks (`dormancy_probes.py card-hooks`,
  203 classes x 66 hook names) and none can observe cross-card order.
- **radius** Tier 1 #5 (same list), `/G6`.

### 52. `hook_dispatch/G5` + `/step3` — `MonsterModel` is not a sim listener  [DORMANT] [unpinned]

`CombatState.cs:420` adds `creature.Monster` to the listener list and
`MonsterModel.cs:51` declares `ShouldReceiveCombatHooks => true`. Exactly **12** C#
monster models override an `AbstractModel` hook
(`py tools/audit/dormancy_probes.py cs-monster-hooks`); only `KinPriest` has been
adjudicated (waiver: presentation). **The other 11 are in no seam's scope — see
the holes section.** Trigger: porting any of them onto their real hook.

### 53. `hook_dispatch/G6` — `AfflictionModel` is not a sim listener  [DORMANT] [unpinned]

`CombatState.cs:458-461` adds `cardModel.Affliction` immediately after its card and
`AfflictionModel.cs:146` declares `ShouldReceiveCombatHooks => true`. Executed both
ways: 0 of the 7 sim `Affliction` subclasses define any hook, and exactly one of
the 10 C# affliction files overrides one (`Hexed.cs`, `AfterCardEnteredCombat`) —
and Hexed is a data-only stub (`afflictions.py:72-79`). Trigger: porting Hexed's
hook; it then needs `hook_dispatch/G1`'s per-card ordering to register in the right
position.

### 54. `hook_dispatch/N5` — no run-level listener list  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step14`, `/step18`, `/N5` (3 entries).
- `RunState.cs:545-596` makes every deck card and its enchantment a run listener at
  all times, in and out of combat, and appends the whole combat list when there is
  a child combat; the sim has two disjoint systems — `HookSystem` inside a combat,
  duck-typing over `run.relics` (`relics/base.py:205-235`) outside one — and a deck
  card is never a listener. Executed: no sim card class implements a run-scoped
  hook at all.
- **trigger** Porting any `CardModel` overriding `AfterRoomEntered`,
  `AfterRewardTaken`, `ShouldAddToDeck` or another run-level hook.
- **radius** `creature_card_cmds/G12` (nowhere to hang `AfterGoldGained`).

## 2E. Power pipeline

### 55. `power_cmd/G1` — Artifact's typing is static, not sign-aware  [DORMANT] [pinned]

- **sites** `power_cmd/step13`, `/step28`, `/G1` (3 entries).
- `cmds.py:299` checks `power_cls.power_type == PowerType.DEBUFF` (a fixed class
  attribute) instead of C#'s `canonicalPower.GetTypeForAmount(amount) !=
  PowerType.Debuff` (`ArtifactPower.cs:24`; `PowerModel.cs:460-471` — a
  Counter+AllowNegative power with a negative amount **is** a Debuff).
  Strength/Dexterity are Counter+AllowNegative+Buff on both sides, so a
  negative-amount application bypasses the sim's Artifact branch entirely.
- **trigger** Dormant in both directions: no player-side `ArtifactPower` source
  exists anywhere in the game, and the enemy side needs a ported negative-Strength
  applier (`Malaise`, `Resonance` — neither ported).
- **pin** `TestPowerCmdOrder::test_artifact_blocks_negative_signed_debuff`.
- **fix** Add `get_type_for_amount(amount)` to the power model and use it at
  `cmds.py:299` and in Unsettling Lamp. **radius** `/G2`, `/G3`.

### 56. `power_cmd/G2` + `/step10` — Unsettling Lamp's condition has the same blind spot  [DORMANT] [unpinned]

`relics/unsettling_lamp.py:44-53` bails on `amount <= 0` and then checks the static
`power_type`, where C# uses `power.GetTypeForAmount(amount)`
(`UnsettlingLamp.cs:124`). `Malaise.cs:40` and `Resonance.cs:33` both apply
negative `StrengthPower` with `applier = player, cardSource = this` — exactly the
shape Lamp doubles — and the sim's `amount <= 0` guard rejects it before the
sign-aware check would matter. **This is the seam the 933T Mecha Knight bug lived
on**: the ordering half is fixed, the sign half is not.

### 57. `power_cmd/G3` — the three power-amount phases collapsed into one chain  [DORMANT] [unpinned]

- **sites** `power_cmd/step12`, `/step27`, `/G3` (3 entries).
- C# runs `BeforePowerAmountChanged` -> `ModifyPowerAmountGiven` (guarded on
  `applier != null && ContainsCreature(applier)`) -> `ModifyPowerAmountReceived`,
  three separately-sequenced calls (`PowerCmd.cs:120,125,127`); `hooks.py:170-183`
  is one flat registration-order chain with no phase separation and no applier
  gate, and `ArtifactPower` is not a listener at all (hard-coded at
  `cmds.py:299-306`).
- **trigger** The two general listeners are domain-disjoint today (Unsettling Lamp
  given-side debuff-only, Ruined Helmet received-side buff-only). A third listener,
  or either widening, collides.
- **radius** Tier 1 #6 (`hook_dispatch/G3`, phases), Tier 1 #11
  (`damage_pipeline/G2`, the companion events), `/G1`.

### 58. `power_cmd/G5` + `/step3` — no `PowerInstanceType`  [DORMANT] [unpinned]

`PowerCmd.cs:165-174`'s `FindExistingInstanceForStacking` dispatches on
`power.InstanceType` (`PowerModel.cs:144`, default `None`); the sim's
`if power_cls.id in target.powers` (`cmds.py:308`) always behaves as `None`. **21**
C# powers declare an override (19 `Instanced`, 2 `InstancedPerApplier` —
`OblivionPower.cs:27`, `StranglePower.cs:29`), **11 of them ported**. Trigger: two
appliers of the same `InstancedPerApplier` power in one combat, or any ported
`Instanced` power stacking where it should not.

### 59. `power_cmd/step4` and `power_cmd/step26` — one code path serves Apply and ModifyAmount  [DORMANT] [unpinned]

C# has two independently-coded pipelines whose guards differ (`PowerCmd.cs:79-87`);
the sim collapses them (`cmds.py:270-332`). It reaches the same steady state for
ported content, but the collapse is not verified line-for-line — and Tier 1 #22 is
the one place it has already been proven wrong. **Read this entry before touching
`PowerCmd.apply`.**

### 60. `power_cmd/step6` — no `amount == 0` early return  [DORMANT] [unpinned]

Filed under the `IsEnding` family by its first reference, but it owns the
zero-amount half itself. Executed: `PowerCmd.apply(cs.hooks, cs.enemy,
StrengthPower, 0)` -> `{'strength': Strength(0)}`, same for Vulnerable, where C#
(`PowerCmd.cs:103`) registers nothing; a 0-amount debuff on the **player**
additionally lands with `skip_next_tick = True`. One guard at the top of
`PowerCmd.apply`.

## 2F. Damage pipeline remainder

### 61. `damage_pipeline/G1` — Thorns is on the wrong hook  [DORMANT] [pinned]

C#'s `ThornsPower.BeforeDamageReceived` (`ThornsPower.cs:17-24`) fires
unconditionally for every hit, **including the hit that kills its owner**, and is
gated on `props.IsPoweredAttack() || cardSource is Omnislice`; the sim's
`ThornsPower` (`powers.py:328-353`) hooks `on_damage_received`, which the damage
pipeline skips entirely on a killing blow, and has no powered/Omnislice gate. Two
consequences: no reflect on the killing blow, and an incorrect reflect against
Unpowered dealer-attributed damage. Pin:
`TestDamagePipelineOrder::test_thorns_reflects_even_on_killing_blow`. **radius**
`/G4` (the killing-blow snapshot), `/G3` (the powered gate).

### 62. `damage_pipeline/G4` + `/step17.5` — the killing-blow skip is recomputed after death prevention  [DORMANT] [unpinned]

C# decides whether to fire `AfterDamageReceived` (`CreatureCmd.cs:392-399`) from a
snapshot taken **before** `Kill()`, so an arithmetically-lethal hit permanently
skips it even if a `ShouldDieLate` listener prevents the death — `LizardTail.cs:49-55`
restores HP through its own `AfterPreventingDeath` hook instead; the sim resets HP
to 1 first and only then tests `target.is_dead` (`cmds.py:84-120`), so a prevented
death does **not** skip `on_damage_received`. **Witness to use as the failing
test**: Lizard Tail + Centennial Puzzle, both ported — C#'s
`CentennialPuzzle.AfterDamageReceived` is itself killing-blow guarded and correctly
does not draw; the sim's (`relics/centennial_puzzle.py:24-35`) fires and draws 3
cards.

### 63. `damage_pipeline/G6` and `damage_pipeline/step17.4` — the dealer-side event fires after the victim-side one  [DORMANT] [unpinned]

(Two mechanism ids, one finding: the guard and the step that records it each
stand alone because the step names no guard.)

`CreatureCmd.cs:388-395` fires `AfterDamageGiven` (unconditional) **before** the
killing-blow-guarded `AfterDamageReceived`; `DamageCmd.deal` fires
`on_damage_received` then `on_damage_dealt` — the reverse. No sim power implements
`on_damage_dealt` yet. Two lines to swap.

## 2G. Creature and card verbs with no sim counterpart

### 64. `creature_card_cmds/G4` — `heal` refuses to heal a corpse; C#'s revives  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step19`, `/step20`, `/G4` (3 entries).
- `cmds.py:160-161` early-returns 0 on `target.is_dead`; `CreatureCmd.Heal` guards
  only `IsEnding && !IsPlayer` (`CreatureCmd.cs:693-696`) and `HealInternal` fires
  `Revived` and re-activates the player's hooks when HP crosses 0
  (`Creature.cs:477-491`) — healing a corpse is a supported operation. The one
  ported corpse-heal, `ReattachPower.DoReattach`, hand-rolls
  `owner.hp = self.amount` (`powers.py:2360-2365`) and nets the same. Live the
  moment a second corpse-heal is ported, or anyone routes Reattach through the verb.

### 65. `creature_card_cmds/G5` + `/step22` — heal reports the clamped amount, and nothing at full HP  [DORMANT] [unpinned]

`CreatureCmd.cs:751-754` fires `AfterCurrentHpChanged` when the **requested** amount
> 0, carrying that raw amount; `cmds.py:162-166` fires with the **clamped** amount
and only when positive. Executed: healing 20 on a player 3 below max reports delta 3
(C#: 20); healing at full HP reports nothing (C#: reports +amount). The only ported
`on_hp_changed` listener is Red Skull (`relics/red_skull.py:44-46`), which ignores
the delta.

### 66. `creature_card_cmds/G6` — `lose_max_hp` cannot kill  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step28`, `/G6`; `creature_card_cmds/step29` is
  the same finding recorded on its own step (the record files it separately
  because the *order* is the load-bearing part).

`CreatureCmd.LoseMaxHp` computes an **unfloored** `newMaxHp` and, when it is below
`CurrentHp`, deals the difference as Unblockable|Unpowered damage through the
**full** damage pipeline — hooks, death check, `Kill` — and only afterwards floors
MaxHp at 1 (`CreatureCmd.cs:823-827`). The sim floors first (`cmds.py:179-189`), so
no `modify_hp_lost` / `on_damage_received` / `should_die` / `on_death` fires and no
creature can die of max-HP loss. Executed: a 10/10 player losing 30 max HP ends
**alive at 1/1**; C# deals `10 - (-20) = 30` unblockable damage and kills. The order
is load-bearing (`/step29`). Ported in-combat callers: Brightest Flame
(`cards/brightest_flame.py:37`), `PaperCutsPower`.

### 67. `creature_card_cmds/G7` — `exhaust` only knows the hand and the discard pile  [DORMANT] [unpinned]

`cmds.py:379-384` removes the card from `hand` or `discard_pile` and appends it to
`exhaust_pile`; a card in the draw pile, the exhaust pile, or mid-play stays put
**and** lands in the exhaust pile — it exists in two piles at once. Executed: a
Strike alone in the draw pile ends with `card in draw_pile` **and** `card in
exhaust_pile`; a Strike exhausted twice ends with the same instance in the exhaust
pile twice. C# routes through `CardPileCmd.Add(card, Exhaust, Bottom)` whose
`RemoveFromCurrentPile()` is pile-agnostic (`CardPileCmd.cs:496`). **radius** `/N4`
is the missing invariant that hides it.

### 68. `creature_card_cmds/G13` + `/step8` — escape leaves the escaper's powers registered  [DORMANT] [unpinned]

`CreatureCmd.Escape` calls `RemoveAllPowersInternalExcept()` (`CreatureCmd.cs:589`),
stripping every power silently — the deliberate contrast with death, which awaits
each `AfterRemoved` (`533-537`); the sim's escape (`cmds.py:221-234`) sets
`escaped = True`, fires an invented `on_creature_escaped` hook and leaves every
power on the creature **and registered as a live hook listener**. The three ported
escape sites (Thieving Hopper, Gremlin Merc, `BattlewornDummyTimeLimitPower`) leave
only owner-scoped, self-filtering powers.

### 69. `creature_card_cmds/step18` — no `LoseBlock` verb  [DORMANT] [unpinned]

Four sites assign `block = 0` directly (`combat.py:297`, `player.py:158`,
`powers.py:1208`, `powers.py:2300`). `BurrowedPower`'s C# original calls
`CreatureCmd.LoseBlock(owner, all)` from `AfterRemoved`, so where C# re-fires
`Hook.AfterBlockBroken` on residual block the sim fires nothing. Hand Drill
(`relics/hand_drill.py:21`) is a live `on_block_broken` listener that would see the
difference.

### 70. `creature_card_cmds/step23` — no `SetCurrentHp` verb  [DORMANT] [unpinned]

Sites that need one assign HP directly (`powers.py:2360-2365`, `cmds.py:112`); none
runs the death pipeline the way `CreatureCmd.cs:775-778` does, so setting HP to 0
through those paths would leave a 0-HP creature that never fired
`BeforeDeath`/`ShouldDie`/`AfterDeath`. Every ported direct assignment sets a
positive HP (a revive).

### 71. `creature_card_cmds/step26` — no `SetMaxAndCurrentHp` verb  [DORMANT] [unpinned]

Three C# callers, **two ported**: `DecimillipedeSegment.cs:142` and `ToughEgg.cs:173`
(plus `WaterfallGiant.cs:305`). Both ports hand-roll a raw assignment
(`monsters/hive/decimillipede.py:68` and `:167`, `monsters/hive/ovicopter.py:81-83`),
skipping `SetMaxHpInternal`'s CurrentHp clamp (`Creature.cs:493-501`), `SetMaxHp`'s
`if (MaxHp <= 0) Kill` (`CreatureCmd.cs:844-847`) and the `SetCurrentHp` death check.

### 72. `creature_card_cmds/step51` — the Sly keyword is unported  [DORMANT] [unpinned]

No `CardKeyword.Sly` / `IsSlyThisTurn` analogue anywhere in `sts2_rl`, so
`CardCmd.Discard`'s collect-then-auto-play tail (`CardCmd.cs:186-188, 201-204`) and
the `AutoPlayType.SlyDiscard` path have no counterpart. Porting any Sly card also
makes step 50's DiscardAndDraw ordering live at the same moment.

### 73. `creature_card_cmds/step52` — `Downgrade` drops one level, not to base  [DORMANT] [pinned]

`CardModel.DowngradeInternal` (`CardModel.cs:2135-2147`) re-derives the card from
its canonical model — `CurrentUpgradeLevel = 0`, "downgrades a card to its **base**
form" — where `Card.downgrade` (`cards/base.py:150-165`) drops exactly one level and
does not re-apply the enchantment. Ported callers: `DampenPower`
(`powers.py:3149-3183`, from the Magi Knight's DAMPEN_MOVE) and the Reflections
event (`events/reflections.py:36-41`). Pin:
`TestCreatureCardCmdsOrder::test_downgrade_reapplies_the_cards_enchantment`.

### 74. `creature_card_cmds/step56` — no `PileIndexSort` on transform  [DORMANT] [unpinned]

`CardCmd.cs:353-360, 405` sorts recorded tuples by (pile type, original index) so a
multi-card transform re-inserts deterministically; neither sim transform path sorts,
because both are single-card verbs. Trigger: porting any multi-card transform.

### 75. `creature_card_cmds/step99` — no `AutoPlayFromDrawPile` verb  [DORMANT] [unpinned]

C# moves **every** selected card to the Play pile first and only then plays them,
which is what makes it immune to the second card's reshuffle disturbing the first
card's selection; the sim's Havoc-shaped effects pull and play one at a time.
Trigger: any ported card that plays more than one card from the draw pile.
**radius** `/N9`, `/N10`.

### 76. `creature_card_cmds/N9` + `/step82` — the sim has no Play pile  [DORMANT] [unpinned]

C# holds a card being played in `PileType.Play` for the whole of `OnPlay`
(`CardPileCmd.cs:669-670`, `CardCmd.cs:114-117`) and `Shuffle` reads only Draw and
Discard (`CardPileCmd.cs:870-871`) — the entire mechanism behind the exoskeleton
reshuffle parity fact. The sim appends the played card to the **discard** pile and
holds it back from a reshuffle **in parity mode only** (`player.py:203, 232`),
because legacy RL runs are kept byte-for-byte. Residual exposure: an effect that
counts the discard pile during its own `OnPlay` sees the resolving card in the sim
and not in the game.

## 2H. Monster state machine remainder

### 77. `monster_state_machine/G8` — no construction validation  [DORMANT] [pinned]

- **sites** `/step3` (duplicate state id: `Dictionary.Add` throws
  (`RandomBranchState.cs:171`, `MoveState.cs:74`), the sim's dict assignment
  silently overwrites), `/step37` (`monster.machine = other` is a legal Python
  rebind where the C# setter throws, `MonsterModel.cs:228-236`), `/step22`
  (overload #1's `CanRepeatXTimes` rejection, `RandomBranchState.cs:48-51`, has no
  sim analogue) — 3 entries, one mechanism: *C# validates a malformed machine and
  raises; the sim's API does not*.
- **trigger** Porting a monster with a repeated state id — `Fogmog.cs:44-45` is the
  near-miss in the shipped source — or any code that rebuilds a machine mid-combat.
  Dormancy executed over 82 of the 83 ported machines and 6,560,008 fuzzed
  transitions; `_Cultist` is unbuildable (needs a constructor arg) so it is
  unproven for that one machine.
- **pin** `TestMonsterStateMachineOrder::test_duplicate_state_id_is_rejected_at_machine_construction`.

### 78. `monster_state_machine/G7` — `AddBranch` repeat-limit edge cases  [DORMANT] [pinned]

- **sites** `/step21` (clause a: `maxTimes == 0` with `CanRepeatXTimes`
  **permanently disables** the branch in C#, `RandomBranchState.cs:144-147`; the sim
  refuses to build the machine at all), `/step15` (clause c: a float
  subtract-and-check fall-through **throws** in C#, `RandomBranchState.cs:127`, and
  quietly picks the last branch in the sim) — 2 entries.
- **trigger** A C# monster added with `AddBranch(state, 0)`; all 15 non-default
  integer arguments across the 61 call sites are 2 or 3 today. The fall-through
  needs a non-dyadic weight — the only ported one is `TwoTailedRat.cs:127`'s
  `1f/12f`, behind a `_can_summon()` gate the machine-only fuzz cannot open.
- **pin** `TestMonsterStateMachineOrder::test_max_times_zero_disables_the_branch_instead_of_raising`.
- **radius** Tier 1 #1 (`/G1`) is the same `AddBranch` argument surface — read both
  before touching `add_branch`.

### 79. `monster_state_machine/G9` — the spawn roll is not gated on the combat side  [DORMANT] [unpinned]

- **sites** `/step11`, `/step48` (2 entries).
- C# leaves a freshly added enemy on `UNSET_MOVE` with no intent until the next
  player-turn roll — `AfterCreatureAdded` only rolls when `CurrentSide == Player`
  (`CombatManager.cs:863-866`) — and `rollNewMove: false` (`CreatureCmd.cs:72-75`)
  suppresses it for a player-side monster even on the player's turn. The sim rolls
  in the constructor, unconditionally. Dormancy: `combat.py:286-345` runs the whole
  enemy side to completion before returning, so nothing observes the interim state;
  all 11 sim `CreatureCmd.add` sites fire during the enemy side and every ported
  monster is `side='enemy'`.
- **trigger** A sim consumer that reads an enemy's intent mid-enemy-side — a
  per-enemy observation build, or an interruptible enemy phase. **radius**
  Tier 1 #2 owns where the roll is placed.

### 80. `monster_state_machine/G5` — `stun`'s `next_move_key` is dropped for a machine monster  [DORMANT] [pinned]

- **sites** `monster_state_machine/step36` (1 entry).

Two halves: (a) no `CanTransitionAway` guard on the override path, so a move pinned
by `must_perform_once_before_transitioning` can be replaced where the game refuses
(`MonsterModel.cs:420-432`); (b) `cmds.py:216` gates `next_move_key` on
`hasattr(target, '_move_key')` — the hand-rolled monsters' field — so for a
`MachineMonster` the caller's explicit next move **evaporates silently**. Executed
on a `MachineMonster` FossilStalker: `next_move_key='LASH_MOVE' was SILENTLY
DROPPED`. The only ported caller passing one is
`monsters/overgrowth/ceremonial_beast.py:45`, and Ceremonial Beast is hand-rolled.
Pin: `TestMonsterStateMachineOrder::test_stun_next_move_key_reaches_a_machine_monster`.
**radius** Tier 1 #21 — same fix site.

### 81. `monster_state_machine/G3` — `MoveState` has no string follow-up  [DORMANT] [pinned]

`MoveState.GetNextState` is `(FollowUpState?.Id ?? FollowUpStateId) ?? throw`
(`MoveState.cs:23-25, 67-70`); the sim has no string form, so a C# monster that sets
`FollowUpStateId` without `FollowUpState` cannot be ported without making
`build_machine` two-pass. `grep FollowUpStateId` over the game returns exactly two
sites: the declaration and `Creature.cs:539`, the stun path (Tier 1 #21). Pin:
`TestMonsterStateMachineOrder::test_move_state_accepts_a_string_follow_up_id`.

### 82. `monster_state_machine/G2` — no way to express an unreachable registered state  [DORMANT] [unpinned]

`Inklet.cs:69-71` builds and registers `INIT_RAND` with two branches (one of them
`AddBranch(JAB, 2, 1f)` = maxRepeats 2) and never wires it; `PhrogParasite.cs:6-10`
is the same shape. Reproducing only the reachable graph is *correct* today, but the
sim cannot express the dead state, so the moment one becomes reachable the port
silently keeps the old graph. Pinned in the opposite direction by
`test/test_monster_branch_audit.py::TestInkletMoveSequence` and
`::TestPhrogParasiteMoveSequence`, which assert **zero** `monster_ai` draws on
exactly those legs.

## 2I. Turn structure remainder

### 83. `turn_structure/G10` — the combat-end path collapses five C# distinctions  [DORMANT] [unpinned]

- **sites** 7 entries (`/G10`, `/N5` and five steps).
- C# distinguishes a **loss** (`LoseCombat()` -> `_pendingLoss` ->
  `ProcessPendingLoss()`, which fires the `CombatEnded` event and **no hook at
  all**, `CombatManager.cs:945-965`) from a **victory** (`EndCombatInternal` with
  `ReviveBeforeCombatEnd()` -> `AfterCombatEnd` -> `AfterCombatVictory`,
  `970-1033`), and consults `Hook.ShouldStopCombatFromEnding` inside `IsEnding`
  (`196-199`). The sim has one `_end_combat(player_won)` firing one
  `on_combat_end` (`combat.py:347-350`), no revive step, no
  `should_stop_combat_from_ending`.
- **On top of that**, `_run_enemy_turns` has **two player-death exits that
  disagree**: `combat.py:308-310` calls `_end_combat(player_won=False)` (the hook
  fires) while `combat.py:332-335` sets phase/result by hand and returns (it does
  not). Executed: `killed from on_enemy_turn_start: hooks=[('on_combat_end',
  False)]` versus `killed by the attack: hooks=[]` — same end state, different hook
  record.
- **trigger** Any `AfterCombatVictory`-only listener with an unconditional effect;
  the two-exit inconsistency goes live for any `on_combat_end` listener whose
  effect outlives the combat. All four ported listeners gate on victory or on the
  player being alive. The win-condition **predicate** itself is faithful (`/N5`).
- **radius** Tier 1 #7 (`/G13`) and `hook_dispatch/G8` — one design.

### 84. `turn_structure/G5` + `/step9` — the enemy side is per-enemy in the sim, per-side in the game  [DORMANT] [unpinned]

C# has **no** per-creature turn-start or turn-end hook: `BeforeTurnStart`
(`CombatManager.cs:449-455`), `AfterTurnStart`/`ClearBlock` (`492-499`) and
`AfterBlockCleared` (`500-507`) each run as a complete pass over every participant,
then one `AfterSideTurnStart` (`522`), the moves (`1072-1090`), one `BeforeTurnEnd`
(`1251`) and one `AfterTurnEnd` (`1256`); `_run_enemy_turns` (`combat.py:286-345`)
does [clear block -> `on_enemy_turn_start` -> move -> `on_enemy_turn_end`] per enemy
and only `on_enemy_side_end` once. Dormant because every ported listener on those
hooks self-filters to its own owner. **radius** Tier 1 #15, `/G11`.

### 85. `turn_structure/G15` — the turn-end wrapper re-consults `should_ethereal_trigger`  [DORMANT] [unpinned]

`CardModel.OnTurnEndInHandWrapper` (`CardModel.cs:1682-1698`) decides the card's
destination on the raw keyword and never re-consults the hook; `combat.py:370` does
(`if card.is_ethereal and self.hooks.should_ethereal_trigger(card)`), so a false
predicate would send an Ethereal turn-end card to the discard pile in the sim and
to the exhaust pile in the game. Zero implementations on either side, so the
predicate is constant-true and the branches coincide. `turn_structure/step54` is
the same finding on its step.

### 86. `turn_structure/step32` + `/step67` — no `SpawnedThisTurn` flag, no `OnSideSwitch`  [DORMANT] [unpinned]

`TakeTurn` runs `PerformMove()` only if `!Monster.SpawnedThisTurn`; `grep -rn
spawned_this_turn sts2_rl/` returns 0 hits, and there is no side-switch verb to
clear it either (`CombatManager.cs:1420-1424`, `MonsterModel.cs:479-483`). The
no-`IsDead`-guard half **is** faithfully ported (`combat.py:288-292` keeps a
`retained_after_death` corpse in the loop — that is how a withered Decimillipede
segment reaches REATTACH). The record could not construct a reachable C# path where
the flag survives to `TakeTurn`. **radius** `monster_state_machine/G9`.


---

# Dormant-trigger watch list

Every dormant gap names a concrete unported thing that would make it live.
**Anyone porting a row's trigger needs to read that row's mechanisms first** —
the port will otherwise be written against a sim seam that does not behave like
the game's. Sorted roughly by how likely the trigger is to come up.

| trigger — the unported thing | wakes | queue # |
|---|---|---|
| Any conformance replay through a card-selection / grid screen | `creature_card_cmds/N10`, `/step104` | 24 |
| Any conformance replay containing an in-combat transform | `creature_card_cmds/step55` | 25 |
| Any reshuffle in a replay where Perfect Fit is enchanted; a 2nd repositioning `on_shuffle` listener | `creature_card_cmds/G10` | 26 |
| Porting **BufferPower** | `damage_pipeline/G2`, `hook_dispatch/G3` | 11, 6 |
| Porting **Malaise** or **Resonance** (negative-Strength appliers) | `power_cmd/G1`, `/G2` | 55, 56 |
| Porting **Unceasing Top** | `turn_structure/G16` | 45 |
| Porting **SovereignBlade**, **Hoarder** or **SoulFysh** (combat-pile watchers) | `creature_card_cmds/G8` | 34 |
| Porting **Hexed**'s `AfterCardEnteredCombat` | `hook_dispatch/G6` (needs `/G1` too) | 53, 51 |
| Porting **SlumberingEssence** or **WellLaidPlansPower** (`BeforeFlush`); **Bookmark** (`AfterFlush`) | `turn_structure/step55`, `/G4` | 43, 18 |
| Porting **any Sly card** | `creature_card_cmds/step51` (+ step 50's ordering) | 72 |
| Porting **DoomPower** or **HailstormPower** onto the enemy-side `BeforeSideTurnEnd` | `turn_structure/G11` | 44 |
| Porting **NoEnergyGainPower**'s `AfterModifyingEnergyGain`, or **BowlerHat**/**Ectoplasm**'s `AfterModifyingGoldGained` | `damage_pipeline/G2` | 11 |
| Porting **PaleBlueDotPower**, or any gameplay `AfterModifyingHandDraw` | `turn_structure/step20` | 42 |
| Un-stubbing **Dragon Fruit** or **Lucky Fysh** (both ported, both inert) | `creature_card_cmds/G12`, `/G8` | 35, 34 |
| Porting any of the **11 unclaimed C# monster hook overrides** (table below) | `hook_dispatch/G5` | 52 |
| Porting a monster with a **repeated state id** (`Fogmog.cs:44-45` is the near-miss) | `monster_state_machine/G8` | 77 |
| A C# monster added with **`AddBranch(state, 0)`**, or a non-dyadic branch weight | `monster_state_machine/G7` | 78 |
| Porting **CeremonialBeast** onto `MachineMonster`, or the DecimillipedeSegment / TestSubject / WaterfallGiant stun callers | `monster_state_machine/G5` | 80 |
| Wiring **`Inklet.cs:69`'s INIT_RAND**, or porting Inklet / PhrogParasite onto `MachineMonster` | `monster_state_machine/G2` | 82 |
| A monster model needing a **forward state reference** (`FollowUpStateId` without `FollowUpState`) | `monster_state_machine/G3` | 81 |
| A sim consumer that reads an **enemy intent mid-enemy-side** (per-enemy obs build, interruptible enemy phase) | `monster_state_machine/G9` | 79 |
| Porting any `CardModel` with a **run-level hook** (`AfterRoomEntered`, `AfterRewardTaken`, `ShouldAddToDeck`) | `hook_dispatch/N5`, `creature_card_cmds/N3` | 54, 30 |
| A listener on a **guarded dispatcher** that mutates run-level state (HP, gold, deck); **the conformance exporter** | `hook_dispatch/G8` | 28 |
| A listener that **removes another listener mid-dispatch** | `hook_dispatch/G7` | 50 |
| A **card hook that reads state another card's hook writes** | `hook_dispatch/G1` | 51 |
| A **non-dyadic block multiplier** (only `MultiplayerScalingModel.cs:52-68` exists, waived) | `hook_dispatch/G9` block site | 3 |
| A **second implementer** of `ShouldForcePotionReward` / `ShouldAllowFreeTravel` | `hook_dispatch/step37` | 49 |
| A **second corpse-heal**, or routing `ReattachPower` through the heal verb | `creature_card_cmds/G4` | 64 |
| Any `AfterCurrentHpChanged` listener that **reads the amount** | `creature_card_cmds/G5` | 65 |
| A model overriding **`BeforeBlockGained`** (zero overrides game-wide today) | `creature_card_cmds/step12` | 38 |
| Porting a **multi-card transform** | `creature_card_cmds/step56` | 74 |
| Porting a card that **plays more than one card from the draw pile** | `creature_card_cmds/step99`, `/N9` | 75, 76 |
| Two appliers of the same **`InstancedPerApplier`** power in one combat | `power_cmd/G5` | 58 |
| A **third `modify_power_amount` listener**, or Unsettling Lamp / Ruined Helmet widening | `power_cmd/G3` | 57 |
| An **`AfterCombatVictory`-only** listener with an unconditional effect; any `on_combat_end` effect that outlives the combat | `turn_structure/G10` | 83 |
| The first **side-effecting** `should_reset_energy` or `modify_max_energy` | `turn_structure/step17` | 48 |
| The first **`ShouldEtherealTrigger`** implementation on either side | `turn_structure/G15` | 85 |
| Porting a `BeforeCardRemoved` listener, or adding a removed-from-state flag | `creature_card_cmds/step68` | 41 |
| A **new multi-hit / multi-target effect** that forgets the per-hit death check | `damage_pipeline/G5` | 29 |
| Porting a second `on_damage_dealt` power | `damage_pipeline/G6`, `/step17.4` | 63 |

---

# Behaviour in no seam's scope

Holes are queue items too. The six records cover engine *machinery*; these
things are covered by nothing. Recorded in
`docs/audit/seams/monster_state_machine.md`'s scope-boundary section (it is the
last seam, so the holes are collected there) and reproduced here so the queue is
the single view.

1. **Per-monster move content.** What `SkitterMove` or `RitualMove` actually
   does — its damage numbers, its intent list. The ~121
   `src/Core/Models/Monsters/*.cs` models are a **content tier** with no audit
   record. `state_machine_probes.py mismatch` covers the branch *parameters* of
   the 13 ported `RandomBranchState`s (12 sim modules) and nothing else.
2. **`AbstractIntent` and the intent vocabulary.** `src/Core/MonsterMoves/Intents/`
   is unaudited: the sim collapses a C# `AbstractIntent[]` into one `Intent` with
   an `also` tuple (`monsters/base.py:36-59`) and nothing checks that mapping.
   `MonsterModel.IntendsToAttack` (`MonsterModel.cs:241-245`) reads the intent
   list and gates ported content, so a wrong mapping is a gameplay bug, not a
   display bug.
3. **`MonsterModel`'s non-machine surface** — `GenerateBestiaryMoveList`,
   `GetIntents`, `ResetStateMachine`, `CanonicalInstance`/`ToMutable`, HP
   generation and the Niche roll. Only `SetUpForCombat` / `OnSideSwitch` are
   claimed (by `turn_structure`). **HP generation and the Niche roll are
   RNG-consuming**, which puts part of this hole on the convergence path.
4. **`EncounterModel` / monster-slot generation.** Which monsters spawn, in what
   slots, with what HP roll, is claimed by no seam. `hook_dispatch` names
   `AfterCreatureAdded` and `monster_state_machine` names `SetUpForCombat`, but
   the *selection* is unaudited — also RNG-consuming.
5. **Eleven C# monster models' `AbstractModel` hook overrides.** The probe
   `py tools/audit/dormancy_probes.py cs-monster-hooks` finds **12** models
   overriding a hook; only `KinPriest` has been adjudicated
   (`monster_state_machine` guard N6, waiver: a barks line plus a music
   parameter). The other 11 are audited by no seam — a hook override is
   per-monster behaviour, i.e. content tier, and hole 1 covers move content but
   not hook overrides. Handed to the content-monster stream
   (`docs/superpowers/prompts/2026-07-26-content-monster.md`).

   | model | overridden hook(s) | note |
   |---|---|---|
   | `Aeonglass.cs` | `AfterCardGeneratedForCombat`, `AfterDeath` | |
   | `Crusher.cs` | `AfterCurrentHpChanged`, `BeforeDeath` | |
   | `DecimillipedeSegment.cs` | `AfterDeath` | ported monster |
   | `LagavulinMatriarch.cs` | `AfterDamageReceived`, `AfterDeath` | **ported mechanic**: the wake-from-damage path, hand-rolled in the sim as `AsleepPower` → `wake_up(stunned=True)` (`monsters/underdocks/lagavulin_matriarch.py:75-87`) |
   | `Queen.cs` | `AfterDeath` | |
   | `Rocket.cs` | `AfterCurrentHpChanged`, `BeforeDeath` | Kaiser Crab's attack |
   | `SoulFysh.cs` | `AfterCardChangedPilesLate`, `AfterDeath` | also `creature_card_cmds/G8`'s trigger |
   | `TestSubject.cs` | `AfterDeath` | ported boss |
   | `TheInsatiable.cs` | `AfterDeath` | |
   | `Vantom.cs` | `AfterDeath` | |
   | `WaterfallGiant.cs` | `AfterDeath` | |

   Most are in ported pools (`rooms.py:124-207`).

Two more holes this aggregation noticed, not recorded by any seam:

6. **No record owns the `combat_rng` stream map.** Four queue entries are
   "the sim draws from the wrong stream, or draws when the game does not"
   (#2, #24, #25, #27) and each was found incidentally by the seam that happened
   to touch the call site. Nothing audits the stream assignment as a subject.
   Given that stream desync is the highest-impact failure class in this queue,
   that is the largest structural hole here.
7. **Relic and card *content* has no seam.** `creature_card_cmds/G12` names two
   ported relics (Dragon Fruit, Lucky Fysh) whose sim implementations are inert
   stubs with docstrings that are no longer true. The seam records the missing
   hook; nothing owns the stubbed relic.

---

# Record inconsistencies found while aggregating

Rule 3 signals: a gap whose text contradicts another record's, or its own. This
class has already caught one live bug on this project, so they are reported, not
fixed. **None of these was corrected in this pass — `audits/**` is untouched.**

1. **Two stale sim citations, caught mechanically.**
   `hook_dispatch`'s G2 evidence cites `relics/spiked_gauntlets.py:26-32`; the
   file ends at line 31 (the method is 26-31). `creature_card_cmds`' G9 and
   step 84 cite `relics/fiddle.py:26-31`; the file ends at 29 (the method is
   26-29). Both are one-line overruns — harmless to a reader, fatal to a
   `sed -n`. `py tools/audit/gap_queue.py cite-check` regenerates this check over
   all 327 citations in this queue.

2. **`hook_dispatch`/G7's executed evidence is from a stale tree.** It records
   the stale-listener plugin run as "the whole suite (2476 passed / 30 xfailed)
   and 191,270 instrumented listener calls". The suite is **2478 passed / 38
   xfailed** today. The conclusion may well still hold — the record says the run
   is reproducible from the committed tree — but the number in the record was
   taken before 8 more xfails and 2 more tests existed, so **re-run it before
   relying on the "only one hit" claim**.

3. **One RE-AUDIT paragraph pasted onto four entries, one of which it does not
   describe.** `damage_pipeline` steps 5, 9, 12 and guard G2 carry a
   byte-identical "RE-AUDIT 2026-07-25 … PARTIALLY RESOLVED" block whose subject
   is the **HpLost** variant. Step 5 is `AfterModifyingDamageAmount` — a
   different variant, and one the same paragraph later lists among the 12 that
   "remain absent". A fixer reading step 5 alone would conclude the damage-amount
   variant is partially resolved when nothing about it changed. The G2 rollup is
   the entry to trust.

4. **One entry, two clauses, two liveness values.** `creature_card_cmds`' step 13
   opens "See guard **G1 (LIVE)**" and its clause (c) is `hook_dispatch`'s G9,
   which that record explicitly marks **DORMANT at this site** ("AMENDED (fix
   pass 2): it carries the identical gap, but is DORMANT there"). Any tool — or
   reader — that takes an entry's first liveness token as the entry's liveness
   mis-files it. This queue files it under `damage_pipeline/G3` (live) and lists
   it as a co-site of `hook_dispatch/G9`.

5. **12 vs 11 monster models.** `hook_dispatch`'s step 3 states "exactly 12
   monster models override a hook"; `monster_state_machine`'s boundary section
   heads its table "**Eleven** C# monster models' `AbstractModel` hook
   overrides". Both are right — 12 total, minus `KinPriest`, adjudicated as a
   waiver — but the subtraction is invisible from the JSON records alone and the
   probe prints 12. Anyone quoting a number here should quote the probe.

6. **Gap-id collisions across records, unflagged by the records themselves.**
   `G8` is the missing `IsEnding` gate in `hook_dispatch` and the missing
   AutoPrePlay/AutoPostPlay phases in `turn_structure`; `G2`, `G3`, `G4`, `G9`
   and `N5` each mean two different things in two records. The records
   cross-reference by bare id in several places ("carries G8's precedence",
   "see guard N3"), which is only unambiguous because those references happen to
   be within-record. This is a latent mis-merge waiting for the next reader.

7. **Self-corrections the records themselves record** — not outstanding
   contradictions, but they establish that first-pass verdicts on this project
   are not reliable without re-execution:
   - `monster_state_machine` step 13: "A first pass stated '13 resolved / 8
     match', having read the branch-state count as the pair count."
   - `monster_state_machine` G2: the first pass's gap ids and step list
     disagreed — "a recount found 8 distinct gap ids across the steps against 9
     in the doc."
   - `monster_state_machine` step 22: corrected from `deliberate-divergence`
     whose rationale "cannot both hold".
   - `monster_state_machine` step 35: the inherited **seed fact** "the sim uses
     the shared combat stream" is **stale** for the machine itself.
   - `creature_card_cmds` G14: the first pass verdicted one mechanism three
     different ways — gap at steps 11/71/72, deliberate-divergence at 74/83/90,
     faithful at 48/54/103.
   - `turn_structure` G13: the inherited doc's dormancy claim is called "FALSE";
     G11's inherited content list "was WRONG"; G12's "no ported pair contends for
     the same event today" is "WRONG"; G4 is live "NOT for the reason the
     inherited doc gave".
   - `power_cmd` step 20: the previous rationale was "factually wrong".
   - `monster_state_machine` G6: the first pass's **LIVE** label was refuted by
     its own pin XPASSing.

---

# Appendix — regenerating this file

```
py tools/audit/gap_queue.py counts        # the summary table
py tools/audit/gap_queue.py mechanisms    # every mechanism with its sites and pin
py tools/audit/gap_queue.py list          # every gap entry, one line
py tools/audit/gap_queue.py pins          # the 32 strict xfails
py tools/audit/gap_queue.py unpinned      # the 59 unpinned mechanisms
py tools/audit/gap_queue.py coverage      # every mechanism and entry appears here
py tools/audit/gap_queue.py cite-check    # every file:line here resolves
py tools/audit/harness.py validate        # 6 records, 0 invalid
```

`coverage` and `cite-check` are the two that fail loudly if this file drifts from
the records: `coverage` asserts that all 90 mechanisms and all 224 entry ids are
locatable in the prose, `cite-check` that all 327 `file:line` citations resolve
in `sts2_rl/` or in the decompiled game tree.

Both were run clean at the commit that added this line, together with
`py -m pytest test/ -q` (2478 passed / 38 xfailed, unchanged — this stream adds
no test code and no engine code).
