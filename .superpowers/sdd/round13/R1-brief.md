# R1 — hook_dispatch registry family, combat level (G1 + G7-state + G5 + G6)

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding). This is the
round's hardest engine task. The C# is the specification; this brief's maps
were scouted 2026-08-01 and re-verifying them is part of the job.

## Objective

Make the sim's combat listener enumeration match C#
`CombatState.IterateHookListeners` (`CombatState.cs:410-493`): an
**eagerly-built, per-dispatch-derived list** (order = current pile
membership and creature state, not registration history) filtered by a
**lazy per-item `Contains` re-check** (`:482-488`, arms at `:549-599`).
Four gap clusters land together:

- **G1** (sites `step9`, `step44`): card listener order must be derived
  from pile membership per dispatch. C# walks `AllPiles` = Hand, Draw,
  Discard, Exhaust, Play (`PlayerCombatState.cs:70-80`) every enumeration;
  the sim registers `player.all_cards` once at `combat.py:197-206` in a
  frozen order. (The sim has no Play pile yet — that is next wave's task;
  derive from the four piles that exist plus the `_playing_card` limbo,
  and leave a clean seam for the fifth pile.)
- **G7 state half** (sites `step4`, `step11`, `step12`, `step16`,
  `step45`): the per-item re-check. IMPORTANT RECORD CORRECTION, verify
  then build on it: the *registration* half is ALREADY DONE — all 94
  dispatchers route through `_each`, whose inner loops re-check
  `id(l) in self._live` per item (`hooks.py:410`, `:417`), so
  mid-dispatch unregistration is already honored. What is missing is the
  **state** half of C#'s `Contains`: `HasBeenRemovedFromState` (carriers:
  `CardModel.cs:948`, `RelicModel.cs:420`, `PotionModel.cs:202`,
  `OrbModel.cs:46`; afflictions/enchantments borrow their card's flag),
  `IsActiveForHooks` (`Player.cs:112`, assigned `:272`, `:438`
  `= Creature.IsAlive`, `:859`, `:870`), the relic `IsMelted` skip
  (`CombatState.cs:428-435`), and the per-type arms (`:585-599` — note
  the PowerModel arm `:599` checks only owner state, never
  power-still-attached, which is why the recorded
  `on_enemy_side_end -> IntangiblePower` stale hit is FAITHFUL).
- **G5** (+ `step3`): `MonsterModel` is a listener (`CombatState.cs:417-421`;
  its `Contains` arm is `Creature.CombatState != null`, `:585`). Make the
  sim `Monster` a listener in the right slot, then DELETE the two shims
  that fake this today — `monsters/glory/aeonglass.py:25-51,71` and
  `monsters/glory/queen.py:90-108,125` (both docstrings cite G5) — moving
  their handlers onto the monsters themselves. Behavior must be
  byte-identical (their tests pin it).
- **G6**: `AfflictionModel` is a listener added immediately after its card
  (`CombatState.cs:458-461`; `Contains` arm `:591`
  `HasCard && !Card.HasBeenRemovedFromState && Card.Owner.IsActiveForHooks`).
  Build the machinery; the sim's 7 affliction classes define zero hooks
  (verified — `afflictions.py` has only `__init__`/`__repr__`/`can_afflict*`),
  so this stays dormant. Note `clear_affliction` (`cmds.py:1214-1216`)
  leaves a stale `card` back-ref on the affliction — decide what
  `HasCard` maps to and fix that seam if needed.

## The C# derivation order (build exactly this)

Per creature, allies then enemies (`CombatState.cs:413-415`):
`creature.Powers` (`:416`, added BEFORE the player-active check — a dead
player's powers are dropped only by the lazy `Contains` PowerModel arm,
not the structural skip at `:424`), then monster (`:417-421`) or, for
players passing `IsActiveForHooks` (`:424-427`): relics skipping `IsMelted`
(`:428-435`), potions in SLOT order skipping nulls (`:436-443` — the sim
appends potions at the tail via `player.py:159`; deriving from slot order
closes the recorded slot-order half of hook_dispatch/G2 — verify against
the record and claim it in your report if true), orbs (`:448`, waived),
then per pile per card: card → its affliction → its enchantment
(`:449-467`). After all creatures: combat `Modifiers` (`:470-473`),
`BadgeModels` (`:474-477`), multiplayer scaling (`:478-481`). The
`Player` object itself is never a listener. `CombatHistory` is sim-only
(recorded note N3) — keep it first.

## Performance contract (binding — this is the hottest path in the sim)

Measured on today's tree: the presence gate (`_has_listener_for`,
`hooks.py:394-395`) skips 97.6% of `_each` calls BEFORE any order build;
a naive rebuild-per-dispatch costs +13% on end_turn, most of it in
`_ordered()`'s `_phased` frozenset recompute (`hooks.py:278-280`).
Requirements:
1. The presence gate stays ABOVE the derivation. Never build the list for
   a dispatch with no listener.
2. Maintain `_phased` incrementally in `register`/`unregister` instead of
   recomputing per rebuild.
3. Split cache invalidation: the presence cache must key on listener-SET
   membership only (a pile move must NOT thrash it); the order derivation
   keys on membership + enemy order + pile arrangement. There is NO
   pile-mutation choke point (67 direct pile-list mutation sites across 15
   files) — deriving order from the piles at use time, behind the presence
   gate, is the honest port; do not try to add a dirty-flag to every
   mutation site.
4. Keep the per-item state re-check to attribute reads in the inner loop
   (a `_contains()`-style predicate per listener base), not isinstance
   cascades.
5. Measure end_turn before/after with an ad-hoc in-process benchmark
   (there is no benchmark script in the repo; round 12 used a throwaway
   loop — e.g. 25 combats x 10 end_turns, 30-card deck, warmed). Report
   both numbers and the %. A regression beyond ~15% needs a redesign, not
   a shrug.

## Sim map (verified 2026-08-01; line numbers current)

- `hooks.py`: `_listeners`/`_live`/`_epoch` `:188-200`; `_ordered()`
  `:237-281` (cache key `:261` = epoch + enemy ids — the thing G1
  replaces); `_has_listener_for` `:325-362`; `_each` `:364-421`;
  categories `:24-33`; `modify_shuffle_order` `:1294-1317` is the ONE
  dispatcher outside `_each` (it derives pile positions itself — align or
  leave, but say which and why).
- `combat.py:184-243`: registration order today = history → cards+ench →
  enemy powers/shims → relics → potions.
- `player.py:79-82` piles, `:104` `_playing_card`, `:113-117` `all_cards`,
  `:119-142` `pile_type_of`, `:159` `add_potion`, `:173` `detach_potion`.
- `cmds.py`: register/unregister sites `:959`, `:1044`, `:1258`,
  `:1335-1358`; afflict/clear `:1162-1216`.
- Kind bases: cards/base.py:137, enchantments.py:46, relics/base.py:113,
  history.py:107, monsters/base.py (stores `_hooks`, never registers).

## Footprint (yours alone this wave)

`sts2_rl/hooks.py`, `sts2_rl/combat.py`, `sts2_rl/player.py`,
`sts2_rl/cmds.py`, `sts2_rl/monsters/base.py`,
`sts2_rl/monsters/glory/aeonglass.py`, `sts2_rl/monsters/glory/queen.py`,
`sts2_rl/afflictions.py`, `sts2_rl/cards/base.py`,
`sts2_rl/enchantments.py`, `sts2_rl/relics/base.py`,
`sts2_rl/history.py`, plus tests.
NOT yours this wave (other lanes own them): `sts2_rl/powers.py`,
`sts2_rl/potions.py`, `sts2_rl/run.py`, `sts2_rl/driver.py`,
`sts2_rl/rewards.py`, `events/**`, individual `relics/*.py` and
`cards/*.py` content files, `audit/**`. If Power/Potion base classes need
a one-line change (category constant, state flag), write the EXACT diff in
your report — the controller lands it at fold time.

## Explicitly OUT of scope

**N5** (run-level listener list, `RunState.cs:545-596`) is a later task.
Do not touch the run-level walks. DO include in your report: what your
combat-level design exposes for N5 to build on, and note the known
`run.py:1095-1098` `_map_listeners()` order bug (`[*relics, *deck]`,
reversed vs C# deck-first) for the controller's queue annotation.

## Tests

- Will break and need re-staging: `test/test_hook_order.py:917-943`
  (`listener_categories()` reads `_ordered()` directly) and the
  `TestHookDispatchOrder` docstring `:946-953` (states the old rule);
  `test/test_task8_hook_presence_cache.py` (7 tests pin `_has_listener_for`
  + `_epoch`).
- New pins required: a card that changes pile changes dispatch position
  (G1); a removed/melted/inactive listener is dropped by the state
  re-check mid-dispatch (G7); monster hook fires in the monster slot (G5,
  via the aeonglass/queen migrations); affliction would dispatch
  immediately after its card (G6 — machinery-level test with a synthetic
  affliction, since no real one has hooks).
- Run before AND after: `py -m pytest test/ -q -p
  audit.tools.stale_listener_plugin` (the record quotes a stale tree's
  numbers; report fresh ones).
- Also run: test_combat_over_hook_gate.py,
  test_task8_pile_move_and_generated_hooks.py, test_discard_draw_order.py,
  the aeonglass/queen/glory tests, and every file you touch.

## Record-close proposals to include (controller applies)

For each of: G1 (step9, step44), G7 (step4, step11, step12, step16,
step45 — note step45's "66 dispatchers walk a snapshot" premise is
doubly stale: 94 dispatchers, and the registration re-check exists),
G5 (+step3), G6, and (if the slot-order claim verifies) the G2 slot half:
verdict + which reasoning you replaced. Flag the stale_listener_plugin
"2476 passed / 30 xfailed" recorded number for correction.

Report path: `.superpowers/sdd/round13/R1-report.md`.
