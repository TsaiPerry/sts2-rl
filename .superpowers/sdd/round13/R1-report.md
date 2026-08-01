# R1 report — hook_dispatch registry family, combat level (G1 + G7-state + G5 + G6)

Lane: R1, round 13. Worktree `c:\Users\Perry\Desktop\sts2-rl-tier2`.
Spec: decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2`, non-ascension.

## Headline

`HookSystem` no longer keeps a dispatch ORDER. `_ordered()` now rebuilds the
list per dispatch out of the live combat state — the literal shape of
`CombatState.IterateHookListeners` (`src/Core/Combat/CombatState.cs:410-493`) —
and `_each` applies the lazy per-item `Contains` filter (`:482-488`, arms at
`:549-599`) as it reaches each listener. `_listeners` survives as the
MEMBERSHIP set only (what `register`/`unregister` maintain, what the presence
cache keys on).

All four clusters landed. G1, G2-slot, G5 and G6 are FIXED; G7 is FIXED for
every listener kind inside my footprint and NARROWED for `Power`/`Potion`,
whose `hook_contains` needs a one-line addition to files another lane owns
(exact diffs in §7).

**The brief's C# map is correct in every particular I checked.** Line numbers,
arm-by-arm `Contains` semantics, the `AllPiles` five-pile order, the
`IsActiveForHooks` assignment sites, the `IsMelted` skip and the note that the
PowerModel arm never checks power-attachment all verified. Two brief claims did
NOT verify — a perf figure and a sim line number — see §8.

---

## 1. Per-entry verdicts

### G1 — card listener order is derived per dispatch (steps 9, 44) — **FIXED**

C#: `CombatState.cs:449-467` walks `player.PlayerCombatState.AllPiles` on every
enumeration, and `AllPiles` is `new CardPile[5] { Hand, DrawPile, DiscardPile,
ExhaustPile, PlayPile }` (`src/Core/Entities/Players/PlayerCombatState.cs:70-80`,
verified verbatim). Per card it adds the card (`:457`), then
`cardModel.Affliction` (`:458-461`), then `cardModel.Enchantment` (`:462-465`).
So a card that changes pile changes its position in the listener list, with no
registration event anywhere.

Sim before: `combat.py` registered `player.all_cards` once at combat setup, in
the frozen order `hand + draw_pile + discard_pile + exhaust_pile`, and
`_ordered()` sorted on the registration index inside the card category.

Sim after (`sts2_rl/hooks.py:323-459`, `_derive`): the four sim piles are walked
in `AllPiles` order and the fifth (`PileType.Play`) is derived from
`player._playing_card`, which is excluded from the discard leg and emitted after
the exhaust pile. That is exactly where C# has a card mid-`OnPlay`
(`CardCmd.cs:114-117` puts it in `PileType.Play` before `OnPlayWrapper`).

Pins: `test_a_card_that_changes_pile_changes_its_dispatch_position`,
`test_pile_order_beats_registration_order`,
`test_the_four_piles_walk_in_allpiles_order`,
`test_a_card_mid_onplay_walks_in_the_play_slot_last`.

Seam left for the fifth pile: `_derive`'s Play leg is a single named block; when
`PlayerCombatState` grows a real `play_pile` list, the block becomes one more
`extend()` and `_playing_card` disappears from `hooks.py` entirely.

### G7 — the lazy per-item re-check (steps 4, 11, 12, 16, 45) — **FIXED for cards / relics / afflictions / enchantments / monsters; NARROWED for powers and potions**

The brief's record correction verified: the REGISTRATION half was already done.
Confirmed by reading the committed tree (`git show HEAD:sts2_rl/hooks.py`): the
old `_each` re-checked `id(l) in self._live` per item inside both the phased and
plain loops. What was missing was the STATE half. Implemented:

| `Contains` arm | C# | sim |
|---|---|---|
| CardModel | `:593` `!HasBeenRemovedFromState && Owner.IsActiveForHooks` | `Card.hook_contains` (`cards/base.py:250-266`), new `has_been_removed_from_state` (`:144`) mirroring `CardModel.cs:948`/`:1605-1608` |
| RelicModel | `:597` same shape | `Relic.hook_contains` (`relics/base.py:214-229`), new `has_been_removed_from_state` (`:126`) mirroring `RelicModel.cs:420`/`:531-534` |
| AfflictionModel | `:591` `HasCard && !Card.HasBeenRemovedFromState && Card.Owner.IsActiveForHooks` | `Affliction.hook_contains` (`afflictions.py:54-...`) |
| EnchantmentModel | `:589` same shape via `Card` | `Enchantment.hook_contains` (`enchantments.py:54-...`) |
| MonsterModel | `:585` `Creature.CombatState != null` and NOTHING else | `Monster.hook_contains` (`monsters/base.py:110-...`) = `not is_removed_from_combat` |
| OrbModel | `:587` | waived (note N7, no orbs) |
| Badge/Modifier/Achievement/MultiplayerScaling | `:575-583` always true | waived (notes N1, N4) |
| PowerModel | `:599` `Owner.CombatState != null && (Owner.Player?.IsActiveForHooks ?? true)` | **BLOCKED-ON-FOOTPRINT** — `powers.py` is another lane's; exact diff in §7 |
| PotionModel | `:595` `!HasBeenRemovedFromState && Owner.IsActiveForHooks` | **BLOCKED-ON-FOOTPRINT** — `potions.py`; exact diff in §7. Both legs are already covered STRUCTURALLY (a used/discarded potion is unregistered and its slot nulled; an inactive player's potions are skipped at `:424-427`); only a mid-dispatch flip is missed |

The structural half of G7 also landed: `IsActiveForHooks` now exists
(`player.py:94`, mirroring `Player.cs:112`), `_derive` honours the
`!player.IsActiveForHooks -> continue` skip at `CombatState.cs:424-427`
(relics/potions/orbs/cards go, the powers already added at `:416` stay), and the
`IsMelted` relic skip at `:431` is expressible (`Relic.is_melted`,
`relics/base.py:122`).

`IsActiveForHooks` lifecycle, all four C# sites mirrored:
* initialised true (`Player.cs:272`, `:438` `= Creature.IsAlive`);
* cleared by `DeactivateHooks` (`Player.cs:857-860`) from `CreatureCmd.cs:553`,
  which is inside the REAL-death arm only and after `Hook.AfterDeath` — mirrored
  in `cmds.py` `_resolve_death`, after `_strip_powers_after_death`;
* set by `ActivateHooks` (`Player.cs:868-871`) from `Creature.HealInternal`
  (`src/Core/Entities/Creatures/Creature.cs:477-485`) when a heal takes a dead
  creature back above zero — mirrored in `CreatureCmd.heal`;
* the prevented-death arm (`CreatureCmd.cs:560-570`) leaves it alone.

Pins: `test_a_card_removed_from_state_mid_dispatch_is_skipped`,
`test_a_relic_removed_from_state_mid_dispatch_is_skipped`,
`test_a_melted_relic_is_skipped_by_the_walk`,
`test_an_inactive_player_contributes_only_its_powers`,
`test_the_player_stops_being_active_for_hooks_once_it_really_dies`,
`test_death_prevention_leaves_the_player_active_for_hooks`,
`test_a_revive_puts_the_player_back_in_the_walk`,
`test_the_victory_path_revives_before_dispatching_after_combat_end`,
`test_a_monster_removed_from_combat_stops_being_dispatched_to`.

### G5 — MonsterModel is a listener (step 3) — **FIXED, both shims deleted**

C#: `CombatState.cs:417-421` — `creature.Player == null -> list.Add(creature.Monster)`,
immediately after `list.AddRange(creature.Powers)` at `:416`;
`MonsterModel.cs:51` `public override bool ShouldReceiveCombatHooks => true`
(verified). Its `Contains` arm is `:585`.

Sim: `Monster` gains `hook_category = CAT_MONSTER` and registers itself in
`__init__` (`monsters/base.py:108`, `:176-183`). `_derive` emits it from
`combat.enemies`, so registration order is immaterial — only membership is.
`hooks` may be `None` for a monster built outside any combat (the
state-machine construction tests do exactly that); such a creature is in no
`CombatState.Enemies` either, so it is not registered.

**Collision check executed before building this** (the one thing that could have
made G5 a silent mass behaviour change): every `public`-named `HookSystem`
dispatcher (94) crossed with all four `_PHASES` suffixes, intersected with
`dir(Monster)` and with the `__dict__` of all **114** sim `Monster` subclasses →
**zero** collisions. No monster method silently became a hook handler.

Shims deleted and their handlers moved onto the monsters:
* `monsters/glory/aeonglass.py` — `_AeonglassWitherListener` (was lines 25-51,
  registered at `:71`) → `Aeonglass.on_card_generated_for_combat`, body
  unchanged (`Aeonglass.cs:150-166`);
* `monsters/glory/queen.py` — `_AmalgamDeathListener` (was lines 90-108,
  registered at `:125`) → `Queen.on_death`, body unchanged (`Queen.cs:221-234`).
Both `from ...hooks import CAT_POWER` imports removed. The shims' hand-made
`hook_category = CAT_POWER + 1` slot is now a real category.

Behaviour is byte-identical: `test_glory.py` and
`test_task8_aeonglass_generated_wither.py` pass unmodified except for the two
tests that named the deleted class by name (re-staged, see §5).

Pins: `test_the_monster_is_a_listener_right_after_its_own_powers`,
`test_a_monster_removed_from_combat_stops_being_dispatched_to`,
`test_aeonglass_is_itself_the_listener`, plus the `["power", "monster"]` tail of
`test_dispatch_order_is_the_games_derived_per_creature_walk`.

### G6 — AfflictionModel is a listener (guard G6) — **FIXED (machinery); stays DORMANT on content**

C#: `CombatState.cs:458-461` adds `cardModel.Affliction` between the card and
its enchantment; `AfflictionModel.cs:146` declares `ShouldReceiveCombatHooks`.

Sim: `Affliction` gains `hook_category = CAT_CARD` and `hook_is_card_rider`;
`_derive` emits it from the pile walk in the card→affliction→enchantment order.
Registration added at the three sites where a card can acquire one:
`CardCmd.afflict` (`cmds.py`), `CardPileCmd._enter_combat` (a clone arrives
already afflicted — `create_clone` rebuilds it via C#'s `AfflictInternal`,
`CardModel.cs:1204-1215`), and `CombatState.__init__` (a deck card afflicted out
of combat; `CardCmd.afflict` is deliberately the same command in and out of
combat).

**The `HasCard` seam the brief flagged is real and is fixed.** `CardCmd.
clear_affliction` did `card.affliction = None` and nothing else, leaving the
affliction pointing at a card it no longer afflicts.
`CardModel.ClearAfflictionInternal` (`CardModel.cs:1532-1540`) does TWO things:
it calls `AfflictionModel.ClearInternal` (`AfflictionModel.cs:249-254`), which
nulls `_card`, and then nulls the card's `Affliction`. `HasCard` is
`_card != null` (`AfflictionModel.cs:90`) and is the FIRST leg of the affliction
`Contains` arm — so with afflictions now listeners, that stale back-reference
would have been a cleared affliction that still passed `Contains`. Both halves
plus the unregistration are now mirrored.

Dormancy re-enumerated, not assumed. Sim side: all seven `Affliction` subclasses
in `afflictions.py` define only `__init__`/`__repr__`/`can_afflict*`
(re-read; the brief's claim holds). Game side: of the ten files under
`src/Core/Models/Afflictions`, exactly one overrides an AbstractModel hook —
`Hexed.cs` (`AfterCardEnteredCombat`) — and `HexedAffliction` is a data-only
stub here. So G6 is machinery-only today, which is why the pin uses a synthetic
`_HookedAffliction`.

Pins: `test_an_affliction_dispatches_immediately_after_its_own_card`,
`test_an_affliction_is_registered_and_unregistered_with_its_card`,
`test_an_affliction_whose_card_left_its_pile_is_not_derived`.

### G2 slot half (step 6) — **VERIFIED AND FIXED** (claimed, as the brief invited)

C#: `CombatState.cs:436-443` indexes `player.PotionSlots` and skips nulls;
`Player.cs:120` `PotionSlots => _potionSlots` is the fixed-length array.

The record (step 6, `live: false`) is exactly right about the divergence:
`add_potion` filled the correct belt slot but then `register()`ed, and
`_ordered()`'s tie-break was that registration index. `_derive` now walks
`player.potions` by index, so a potion procured into a freed slot 0 dispatches
ahead of one that has been sitting in slot 1 since combat start.

Pin: `test_potions_dispatch_in_belt_slot_order_not_registration_order`. It is
RED on the committed tree.

Dormancy claim in the record still holds and I did not disturb it: exactly one
sim `Potion` class (`FairyInABottle`) implements any hook, so there is no pair
of potion listeners to reorder today.

---

## 2. Design: what replaced what, and why it is safe

`_ordered()` (`hooks.py:281-321`) is now:

```
order = self._derive()
if self._undeclared or len(order) != len(self._listeners):
    return self._merge_extras()
return order
```

**`_derive` never drops a registered listener silently, and `_merge_extras`
never resurrects one the walk refused.** That distinction is the one real
design subtlety here and it is worth stating plainly, because getting it wrong
either way is a silent fidelity break:

* "the walk could not REACH it" — an orphaned Instanced power instance
  (`power_cmd/G5`: C#'s `Creature.Powers` is a LIST that keeps both instances,
  the sim's `powers` dict indexes only the newer one), a card sitting in no
  pile, a bare object a test registered. These are sim-side shortfalls;
  dropping them would retire listeners the sim dispatches to today. They are
  merged back at the END of their `(creature, category)` group, which is where
  the old registration-index tie-break also put them.
* "the walk REFUSED it" — a melted relic (`:431`), everything past an inactive
  player's powers (`:424-427`). These are C# decisions and `_merge_extras` must
  not undo them, so `_derive` records their ids in an `excluded` set.

`_merge_extras` re-derives with group boundaries and splices; it is the slow
path and it ran **zero times** across the whole end_turn benchmark (§3).

Other decisions worth recording:

* **`_derive` does not filter by `_live`.** `_each`'s inner loop already does,
  so the result is identical and the fast path can splice piles with
  `list.extend`. Consequence: `len(order) != len(_listeners)` is the
  completeness signal, and it is exact as long as everything in a pile is
  registered (which it is — `CardPileCmd._enter_combat`, combat setup, and
  `primal_force` are the only card-into-pile paths that create cards).
* **A played Power card now stops listening.** Its result pile is
  `PileType.None` (`CardModel.GetResultPileTypeForCardPlay`,
  `CardModel.cs:2070-2075`), which `CardModel.cs:1979-1982` resolves to
  `CardPileCmd.RemoveFromCombat` — it leaves every combat pile and therefore
  `AllPiles`. The sim never returned it to a pile either but left it registered
  for the rest of the fight, so it kept receiving hooks the game had stopped
  sending it. Fixed in `_resolve_card_play`. Dormant on content (none of the six
  hook-implementing card classes is a Power — checked: stomp/bolas/
  thrumming_hatchet/clash ATTACK, drum_of_battle SKILL, regret/enthralled/
  normality CURSE) and it is also what keeps `_ordered()` on its fast path
  after the first Power card of a combat.
  Pin: `test_a_played_power_card_stops_listening`.
* **Category constants renumbered** (`hooks.py:38-44`) to make room for the
  monster and orb slots: `HISTORY -1, POWER 0, MONSTER 1, RELIC 2, POTION 3,
  ORB 4, CARD 5`. Only the relative order is ever read; `powers.py` and
  `potions.py` import the names, not the values, so they need no change.
* **`modify_shuffle_order` no longer open-codes its own pile derivation.** It
  was the one dispatcher outside `_each`, and the reason given in its docstring
  was that `_ordered()` could not express pile order. It can now, so the
  hand-rolled sort is gone and it walks `_ordered()` with the same per-item
  filter. This additionally puts powers, relics and potions in their real slots
  where the hand-rolled key sorted every non-card listener to the tail. Today's
  outcome is unchanged: both implementers are enchantments.
  It still does NOT route through `_each`, deliberately — see §8, finding F3.

---

## 3. Performance contract — measured, item by item

No benchmark script exists in the repo, so this is a throwaway loop as the brief
describes: 25 combats × 10 end_turns, 30-card deck, 3 relics, enemies at 100k HP
so nothing ends early, warmed, 7 samples, min and median reported. Baseline is a
`git archive HEAD` export in the scratchpad running in its own interpreter with
its own `sys.path` — NOT a revert of the live tree (forbidden, and another agent
is live in it). Identical script both sides; two independent rounds each.

**Primary measurement** (quiet machine, two independent rounds each side):

| scenario | HEAD (before) | live (after) | Δ |
|---|---|---|---|
| plain 30-card deck | min 0.1034 / 0.1043 s, median 0.1045 / 0.1057 s | min 0.1043 / 0.1026 s, median 0.1047 / 0.1053 s | **≈ 0%** (−0.4% and +0.2% on median — inside noise) |
| 6 enchanted cards (forces the per-card walk) | min 0.1161 / 0.1165 s, median 0.1171 / 0.1178 s | min 0.1223 / 0.1221 s, median 0.1229 / 0.1236 s | **+5.0%** (+4.9% and +5.0% on median; +5.2% on min) |

**Corroborating measurement**, taken later once the concurrent lanes had folded
and the machine was under heavy load from other agents. Absolute numbers are not
comparable to the primary round — HEAD ITSELF moved from 0.1034 to 0.1235 min
(+19%), which is the load, not the code — so this round is reported as four
strictly interleaved HEAD/LIVE pairs with the global minimum of each (the
noise-robust statistic; medians in this round are worthless, one LIVE sample
came in at 0.2387 and the next at 0.1514):

| scenario | HEAD global min | live global min | Δ |
|---|---|---|---|
| plain 30-card deck | 0.1235 s | 0.1210 s | **−2.0%** |
| 6 enchanted cards | 0.1389 s | 0.1475 s | **+6.2%** |

The two rounds agree: no measurable cost on the ordinary path, +5–6% in the
worst case. Budget ~15%. No redesign needed.

Why the enchanted case is the worst case, explicitly: an enchantment (or an
affliction) rides on a card rather than sitting in a pile, so the four piles can
no longer be spliced in with `list.extend` and `_derive` must walk card by card
reading `.affliction`/`.enchantment`. Measured in isolation, the per-item walk
is 7.0 µs against 0.8 µs for the extend path on a 34-listener combat (the cached
lookup it replaced was 0.62 µs) — a 9× difference on the derivation itself,
which the presence gate then dilutes to the +5–6% above. The `_riders` counter
on `HookSystem` is what selects between the two paths, and it is maintained in
`register`/`unregister` from a `hook_is_card_rider` class attribute, so an
un-enchanted, un-afflicted combat never pays it.

Requirement-by-requirement, plainly:

1. **Presence gate stays ABOVE the derivation — DONE.** `_each` runs the
   combat-over gate and `_has_listener_for` before anything touches
   `_ordered()`. Pinned by `test_the_presence_gate_stays_above_the_derivation`,
   which patches `_derive` and asserts it is never entered for a hook nobody
   implements.
2. **`_phased` maintained incrementally — DONE.** `register` unions in
   `_phase_hooks(type(l))` (`hooks.py:253`); `unregister` recomputes
   (`:271-273`), which cannot be incremental for a union but is orders of
   magnitude rarer than dispatch and unions ~35 interned frozensets rather than
   scanning `dir()`. This also let me delete the bare `self._ordered()` call
   `_each` used to make purely to refresh `_phased`: `_ordered()` calls over the
   benchmark dropped **3075 → 2100**.
3. **Cache invalidation split — DONE.** The presence cache still keys on
   `_epoch` alone, i.e. on listener-SET membership; the order derivation reads
   membership + enemy order + pile arrangement + potion slots at use time and
   has no cache at all. A pile move therefore cannot thrash the presence cache.
   Pinned by `test_a_pile_move_does_not_invalidate_the_presence_cache`
   (asserts `_epoch` and the whole `_presence_cache` dict are byte-identical
   across a hand↔draw move while `_ordered()` reports the new order). I did NOT
   add a dirty flag to any of the 67 pile-mutation sites, as instructed.
4. **Per-item state re-check is attribute reads, not isinstance — DONE.** One
   `hook_contains()` predicate per listener base, reached through a single
   `getattr(l, "hook_contains", None)`. No type dispatch anywhere on the hot
   path.
   One thing I did beyond the brief and want on the record: the inner loop now
   runs `getattr(l, hook)` FIRST and both filter legs (`id(l) in live`,
   `hook_contains()`) only for listeners that actually implement the hook. This
   is observationally identical — in C# every model implements every hook as a
   virtual no-op, so `Contains` filtering a non-implementor in or out is
   unobservable — and it keeps both checks off the ~90% of the walk that is a
   `getattr` miss. It is the single reason the plain-deck number did not move.

Two supporting measurements:

* **`_merge_extras` ran 0 times** over the whole plain benchmark
  (`_derive` 2100, `_merge_extras` 0). The slow path is genuinely exceptional.
* **The brief's gate figure is wrong for this workload.** Instrumenting the
  pre-change tree: 13,275 `_each` calls, of which 1,025 pass the gate — **7.7%**,
  not the 2.4% the brief's "skips 97.6%" implies. The gate still does the work
  the design depends on, but the derivation is paid ~3× more often than the
  brief's arithmetic assumes. It is priced in above.

---

## 4. Stale-listener instrumentation — fresh numbers, before and after

Command (brief's): `py -m pytest test/ -q -p audit.tools.stale_listener_plugin`

| | instrumented listener calls | hits | distinct pairs | suite |
|---|---|---|---|---|
| **record quotes** | 191,270 | `on_enemy_side_end -> IntangiblePower` ×10 | 1 | 2476 passed / 30 xfailed |
| **BEFORE** (HEAD export) | 175,517 | **0** | **0** | 3685 passed / 30 skipped / 6 xfailed |
| **AFTER** (live tree) | 178,595 | **0** | **0** | 3826 passed / 6 xfailed |

Exclusions: `test_conformance_floor_state.py` both sides (known missing 933T
floor_49 fixture — never counted). The HEAD export additionally excludes
`test_conformance_map/recording/save.py`, whose fixture path resolves relative
to cwd and cannot find `RunReplays` from a scratchpad export; that accounts for
the 30 skipped and part of the count gap, not for anything behavioural.

**Finding: the record's probe result is stale in the hit as well as the counts,
and it was already stale BEFORE my change.** The `IntangiblePower` ×10 hit is
gone on the committed tree, because this record's own step 11 closed the
registration-liveness half on 2026-07-28 and `_each` has skipped
non-`_live` listeners ever since. The record kept quoting the pre-fix probe as
live evidence in five entries (steps 4, 11, 12, 16, 45). Correction proposed in
§6.

That the probe reports zero on both sides is also the cleanest evidence I have
that the reordering is behaviour-preserving where it should be.

---

## 5. Tests

New: `test/test_round13_listener_derivation.py` — 22 tests, the file is
organised by gap (G1 / G2-slot / G5 / G6 / G7 / extras / perf contract).

**RED evidence.** Reverting the fix to see RED is forbidden and another agent is
live in the tree, so I got RED by `git archive HEAD | tar -x` into the
scratchpad and running the new file against the untouched committed tree:
**18 of the 20 tests that existed at that point failed on HEAD.** The two that
passed are `test_the_four_piles_walk_in_allpiles_order` (registration order
happened to coincide with pile order at combat start) and
`test_a_registered_listener_the_walk_cannot_reach_keeps_its_category_slot`
(the old sort already did that — it is a no-regression pin, and it is the one I
would most want if someone later "simplifies" `_merge_extras` away). The four
tests added after that RED run (`test_a_revive_puts_the_player_back_in_the_walk`,
`test_the_victory_path_revives_before_dispatching_after_combat_end` and the two
they replaced parts of) were written after the fix; they are honestly reported
as post-hoc pins, and both fail on HEAD for the trivial reason that
`is_active_for_hooks` does not exist there.

Re-staged (as the brief predicted):
* `test/test_hook_order.py` — `listener_categories()` gained the monster and
  affliction kinds; the `TestHookDispatchOrder` docstring stated the OLD rule
  and now states the derived one with its own history; the expected walk gained
  its `"monster"` tail; the "enemy's Vulnerable is last" assertions became
  "powers then MonsterModel". 68 passed.
* `test/test_task8_aeonglass_generated_wither.py` — imported
  `_AeonglassWitherListener` by name; the two tests that did now exercise the
  monster's own method and assert the shim class is gone and that the monster
  dispatches in the monster slot. 7 passed.
* `test/test_task8_hook_presence_cache.py` — **needed no change**, contrary to
  the brief's prediction. All 7 tests pass unmodified. They register bare
  objects with no `hook_category`, which is exactly the `_undeclared` path, so
  they turned out to be a good accidental pin on `_merge_extras`.

Commands run and counts:

```
py -m pytest test/test_round13_listener_derivation.py -q
    -> 22 passed

py -m pytest test/test_hook_order.py test/test_task8_hook_presence_cache.py \
    test/test_combat_over_hook_gate.py test/test_task8_pile_move_and_generated_hooks.py \
    test/test_discard_draw_order.py test/test_combat_veto_and_dealer_event.py \
    test/test_turn_start_split.py test/test_glory.py \
    test/test_task8_aeonglass_generated_wither.py -q
    -> 237 passed

py -m pytest test/ -q -p audit.tools.stale_listener_plugin \
    --ignore=test/test_conformance_floor_state.py
    -> 3826 passed, 6 xfailed; probe: 178,595 calls, 0 hits
```

(The controller independently confirmed 113 passed across my five core files and
3826 passed / 6 xfailed / 0 failed on the full suite with concurrent lanes
folded in.)

Re-run after the concurrent lanes folded (`powers.py`, `rewards.py`, `run.py`,
`driver.py` and several audit records changed under me):

```
py -m pytest test/test_round13_listener_derivation.py test/test_hook_order.py \
    test/test_task8_hook_presence_cache.py test/test_task8_aeonglass_generated_wither.py \
    test/test_combat_over_hook_gate.py test/test_task8_pile_move_and_generated_hooks.py \
    test/test_discard_draw_order.py test/test_combat_veto_and_dealer_event.py \
    test/test_turn_start_split.py test/test_glory.py -q
    -> 260 passed
```

Also re-checked after the fold: neither `powers.py` nor `potions.py` grew a
`hook_contains`, so §7 is still owed; and `run.py:1113-1116` still returns
`[*self.relics, *self.deck]`, so finding F2 still stands.

One test-suite regression found and fixed during the work:
`test_state_machine_construction.py` builds a `Monster` with `hooks=None`, which
G5's unconditional `hooks.register(self)` crashed on. Guarded — a monster
outside a combat is in no `CombatState.Enemies` either, so C# has no listener for
it.

---

## 6. Record-close proposals

Record file: `audit/records/seam/hook_dispatch.json`. For each, the verdict and
**which reasoning it replaces** — not only which verdict.

**step 3 (G5) → `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R1). `Monster` is now a hook listener
in its own right (`monsters/base.py`: `hook_category = CAT_MONSTER`, registered
in `__init__`, `hook_contains` = `CombatState.cs:585`'s `Creature.CombatState !=
null`), emitted by `HookSystem._derive` from `combat.enemies` immediately after
that creature's powers — `CombatState.cs:417-421`. The two stand-in listeners
this entry's dormancy verdict depended on are DELETED
(`_AeonglassWitherListener`, `_AmalgamDeathListener`) and their handlers moved
onto `Aeonglass`/`Queen`, where the C# overrides are.*
Reasoning replaced: the entry said "the sim has no listener category to hang one
on" and rested its dormancy on "across 113 sim Monster subclasses, 0 define any
of HookSystem's 66 hook names". That census is now the SAFETY argument rather
than the dormancy argument, and it was re-executed at 114 classes × 94
dispatchers × 4 phase suffixes with zero collisions — which is what made the
category safe to add. The entry's own "concrete trigger" (KinPriest's AfterDeath)
is now a pure content port with no engine work in front of it.

**step 4 (G7) → `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R1). The structural half of this entry
— `!player.IsActiveForHooks -> continue`, skipping relics/potions/orbs/cards but
NOT the powers added at `:416` — is implemented in `HookSystem._derive`, and
`PlayerCombatState.is_active_for_hooks` mirrors all four C# lifecycle sites
(`Player.cs:272`/`:438` init, `:857-860` `DeactivateHooks` from
`CreatureCmd.cs:553`, `:868-871` `ActivateHooks` from `Creature.cs:477-485`).*
Reasoning replaced: the entry's dormancy evidence was the stale_listener_plugin
result "the only hit is on_enemy_side_end -> IntangiblePower x10 over 191,270
calls / 2476 passed / 30 xfailed". **That result no longer reproduces and did not
reproduce on the pre-round-13 tree either** — re-run on `HEAD`: 175,517 calls,
ZERO hits, 3685 passed. The probe had been closed by this record's own step 11
on 2026-07-28 and the number was never refreshed.

**step 11 → stays `faithful`; issue text needs the same number correction.**
Close note: *Numbers corrected 2026-08-01: the quoted "2476 passed / 30 xfailed
… 191,270 instrumented listener calls … IntangiblePower x10" is a pre-fix
measurement that this very entry's fix invalidated. Fresh: 178,595 calls, 0 hits,
3826 passed / 6 xfailed.* Also worth adding: the lazy filter is now TWO legs, not
one — registration (`id(l) in _live`) and state (`hook_contains()`).

**step 12 (G7, the `Contains` arm table) → `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R1). Every arm the sim can express is
implemented as a `hook_contains()` predicate on the listener base: CardModel
(`:593`), RelicModel (`:597`), AfflictionModel (`:591`), EnchantmentModel
(`:589`), MonsterModel (`:585`). Orb (`:587`) stays waived under N7; Badge /
Modifier / Achievement / MultiplayerScaling (`:575-583`) under N1/N4. NARROWED,
not fully closed: the PowerModel (`:599`) and PotionModel (`:595`) arms need a
one-line method on `Power`/`Potion`, whose files were owned by another lane this
wave — exact diffs in `.superpowers/sdd/round13/R1-report.md` §7.*
Reasoning replaced: "every sim dispatcher walks a `list(self._listeners)`
snapshot with no re-check" — doubly wrong by round 13: there is no snapshot
(the list is re-derived) and there were already two re-checks.

**step 16 (run-side lazy `Contains`) → LEFT-OPEN, re-scoped under N5.**
Note: *This entry is about `RunState.cs:577-583`, not the combat walk. Round 13
R1 was combat-level only and N5 is explicitly out of scope. Proposal: move this
entry's issue text off the shared G7 paragraph (which is now wrong for the
combat side) and onto N5, so closing the combat half does not read as closing
the run half.* Verified while checking: `RunState.IterateHookListeners`
(`RunState.cs:545-596`) applies `IsActiveForHooks` at `:550` (deck cards) and
`:567` (relics/potions) and the same lazy `Contains` at `:577-583` — the sim has
no counterpart at run level.

**step 44 (G1) → `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R1). `player.all_cards` is no longer
the dispatch order — it is not consulted by the hook system at all.
`HookSystem._ordered` re-derives per dispatch from Hand → Draw → Discard →
Exhaust → Play (`PlayerCombatState.cs:70-80`), with the Play leg derived from
`_playing_card` until the sim grows a fifth pile list.*
Reasoning replaced: "evaluated ONCE at combat start, so the card listener order
is frozen for the combat". Also note the dormancy census this entry relied on
(203 card classes, six implemented hooks, "none able to observe cross-card
order") is no longer load-bearing — the order is right whether or not anything
observes it.

**step 9 (G1) → `faithful`.** Same close note as step 44, plus: *the
card→Affliction→Enchantment triple of `:456-465` is emitted in that exact order,
which is also gap G6's close.*

**step 6 (G2, slot half, currently `live: false`) → `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R1). `HookSystem._derive` walks
`player.potions` BY INDEX (`CombatState.cs:436-443`), skipping null slots, so
belt-slot order decides dispatch order and registration order is not consulted.
Pinned by `test_potions_dispatch_in_belt_slot_order_not_registration_order`,
which is RED on the pre-round-13 tree.*
Reasoning replaced: the entry's whole SETTLED analysis rested on "`_ordered()`'s
sort key is `(rank, hook_category, i)` where `i` is that registration-order
index". There is no sort key any more. The dormancy argument (only
`FairyInABottle` implements a potion hook, so no pair exists to reorder) is
still true and still worth keeping as the reason this was never observable.

**guard G6 → `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R1). `Affliction` is a listener
(`hook_category = CAT_CARD`, `hook_is_card_rider`, `hook_contains` =
`CombatState.cs:591`) registered at all three acquisition sites
(`CardCmd.afflict`, `CardPileCmd._enter_combat` for an already-afflicted clone,
`CombatState.__init__` for a deck card afflicted out of combat) and emitted
immediately after its card and before its enchantment. `CardCmd.
clear_affliction` additionally now nulls the affliction's `card` back-reference,
mirroring `AfflictionModel.ClearInternal` (`AfflictionModel.cs:249-254`) —
without which `HasCard`, the first leg of the `:591` arm, would have stayed true
for a cleared affliction. STILL DORMANT ON CONTENT: 0 of 7 sim afflictions and
1 of 10 C# afflictions (`Hexed.cs`) define a hook, and Hexed is unported.*
Reasoning replaced: "the sim's frozen registration order (gap G1) cannot express
[an affliction right after its own card] either" — G1 is closed and it can.

**guard G7 → NARROWED (not closed).** Remaining: the `Power` and `Potion` arms
(§7). Everything else in the guard is closed.

**step 45 → `faithful`, and its premise should be recorded as having been triply
stale.**
Close note: *Closed 2026-08-01 (round 13, R1). The entry's premise — "every one
of the 66 sim dispatchers is `for l in list(self._listeners): if hasattr(...)`,
the `list()` copy makes the walk a snapshot" — was wrong in three separate ways
by the time it was read: (a) there are 94 dispatchers, not 66; (b) the
registration re-check had existed since 2026-07-28; (c) as of round 13 there is
no `_listeners` snapshot in the dispatch path at all — `_each` walks a list
derived from the combat state and re-checks both registration and model state
per item.*

**step 41 / step 43** (sim-registry descriptions) are now stale prose rather
than wrong verdicts: `_listeners` is still the store, but the "sim registration
order" they describe no longer reaches dispatch except through `_merge_extras`.
Suggest a one-line freshening rather than a verdict change.

---

## 7. BLOCKED-ON-FOOTPRINT — exact diffs for the controller

`sts2_rl/powers.py` and `sts2_rl/potions.py` belong to other lanes this wave.
Each needs one method. Without them, a power or potion whose owner becomes
inactive MID-dispatch is still called; both are dormant (the structural skip at
`CombatState.cs:424-427` already covers the between-dispatch case for potions,
and `_strip_powers_after_death` has already removed the powers in the only
reachable case), so landing them is correctness-completing, not urgent.

**`sts2_rl/powers.py`** — add to `class Power`, next to `hook_category`:

```python
    def hook_contains(self) -> bool:
        """`CombatState.Contains`' PowerModel arm (CombatState.cs:599):

            powerModel.Owner.CombatState != null
                && (powerModel.Owner.Player?.IsActiveForHooks ?? true)

        Note what it does NOT test: that the power is still attached to its
        owner. A power an earlier listener removed during the SAME dispatch is
        still called — which is why the recorded `on_enemy_side_end ->
        IntangiblePower` probe hit was faithful rather than a bug.

        `Owner.CombatState != null` is `not is_removed_from_combat` for a
        monster; for the PLAYER it is always true inside a combat (players are
        NOT removed on death — Player.cs:107-110 says that is the whole reason
        IsActiveForHooks exists), so the player leg is the flag alone.
        """
        owner = self.owner
        if getattr(owner, "side", None) == "player":
            return owner.is_active_for_hooks
        return not owner.is_removed_from_combat
```

**`sts2_rl/potions.py`** — add to `class Potion`, next to `hook_category`:

```python
    # `PotionModel.HasBeenRemovedFromState` (PotionModel.cs:202), set by
    # Discard (:221-224) and RemoveBeforeUse (:229-233).
    has_been_removed_from_state: bool = False

    def hook_contains(self) -> bool:
        """`CombatState.Contains`' PotionModel arm (CombatState.cs:595):
        `!HasBeenRemovedFromState && Owner.IsActiveForHooks`."""
        if self.has_been_removed_from_state:
            return False
        combat = self.combat
        if combat is None:
            return True
        player = getattr(combat, "player", None)
        return player is None or player.is_active_for_hooks
```

(The `has_been_removed_from_state` flag is optional — the sim already
unregisters a used/discarded potion and nulls its slot, so the first leg is
covered structurally. Adding it makes the arm literal and costs nothing.)

---

## 8. Findings NOT in the brief

**F1 — the record's stale_listener_plugin evidence does not reproduce, and did
not before my change either.** Detailed in §4 and §6. Five entries cite it. This
matters beyond bookkeeping: it is a dormancy verdict whose *evidence* had been
invalidated by a fix inside the same record, and nobody re-ran it for three
rounds. The zero-hit result is now the correct evidence for a DIFFERENT claim
(the registration re-check works) than the one it is quoted for.

**F2 — the brief's `run.py:1095-1098` citation has drifted; the bug is real.**
The method is now `sts2_rl/run.py:1113-1116`:

```python
    def _map_listeners(self):
        """AbstractModel hook listeners for map generation — the run's relics
        and deck cards (mirrors IRunState.IterateHookListeners for this pass)."""
        return [*self.relics, *self.deck]
```

`RunState.IterateHookListeners` (`RunState.cs:548-562`) adds every active
player's DECK CARDS (each followed by its Enchantment) FIRST, and only then —
and only when `childCombatState == null` (`:563-576`) — relics and potions. So
the sim's order is reversed. Live today: `LanternKeyCard` implements
`modify_generated_map`/`modify_next_event` (`cards/event_cards.py`), so a deck
card and a relic can both listen to the same map hook, and the relic currently
wins. Not mine to fix (`run.py` is another lane's, and it is N5 territory), but
it is a LIVE ordering divergence, not a dormant one. Recommend the controller
queue it explicitly rather than folding it into N5's dormancy.

**F3 — `HookSystem.combat_is_over` is narrower than `IsOverOrEnding`, and one
hook already knows it.** `_each`'s gate is
`phase == Phase.COMBAT_OVER`, i.e. only C#'s `!IsInProgress` half.
`CombatState.is_over_or_ending` (`combat.py`) is the faithful predicate and
carries the `IsEnding` half too (pending loss, or every primary enemy dead with
nothing vetoing). `modify_shuffle_order` open-codes `is_over_or_ending`, so
routing it through `_each` would have WEAKENED an already-exact gate — which is
why I left it outside `_each`. The general question ("should `combat_is_over`
be `is_over_or_ending`?") applies to all 73 gated dispatchers and is a
`combat_is_over`-owner decision, not this lane's. Flagging it as a new candidate
gap: on today's tree, a dispatch that begins between the killing blow and the
teardown reaches listeners in the sim that it would not reach in C#.

**F4 — `Player.ReviveBeforeCombatEnd` was load-bearing and would have silently
broken.** Implementing `IsActiveForHooks` without `ActivateHooks` would have
made `_end_combat_internal`'s `player.hp = 1` pointless and silently killed
every `AfterCombatEnd` relic effect on a fight won at 0 HP (Chosen Cheese today;
Player.cs:816-819 names Centennial Puzzle and Captain's Wheel). The sim already
had the revive and its comment quoted the C# reason verbatim — the flag it was
protecting against just did not exist yet. Nothing in the suite would have
caught it; `test_the_victory_path_revives_before_dispatching_after_combat_end`
now does. This is the round-12 lesson repeating: a green suite is not evidence
of fidelity.

**F5 — orphaned Instanced power instances are a real divergence, in the
opposite direction from what `_derive` would naturally do.** C#'s
`Creature.Powers` is a LIST and holds both instances after a second application
of an Instanced/InstancedPerApplier power; the sim's `powers` dict indexes only
the newer one while the older stays registered and ticking (`power_cmd/G5`). A
naive "derive powers from `creature.powers.values()`" would have dropped the
orphan — quietly retiring a listener BOTH engines dispatch to. `_merge_extras`
is what prevents that, and this is the concrete case it exists for. Worth a
`power_cmd/G5` cross-reference: the honest long-term fix is for the sim's
`Creature.powers` to become a list with a dict index, at which point
`_merge_extras` stops being needed for powers.

**F6 — `primal_force.py` leaves a card registered in no pile.** `on_play`
replaces `player.hand[idx]` with a Giant Rock and registers the rock, but never
unregisters the card it displaced (`cards/primal_force.py`). In C# that card
would have gone through `CardCmd` and left the combat. It now lands in
`_merge_extras`' card-group tail rather than being dropped. Out of my footprint
(`cards/*.py`); flagging for the card lane.

**F7 — `Encounter.create_monsters` builds monsters before `combat.enemies`
exists**, so during `CombatState.__init__` a monster's own `PowerCmd.apply`
dispatches through a walk that cannot yet see the enemy list. Transient and
harmless (the monsters land in `_merge_extras`' tail for those few dispatches,
and the enemy list is assigned immediately after), but it is the one window in
which the derived order is not the final one. Recorded so nobody is surprised
by it later.

---

## 9. Queue annotations (GAP-QUEUE.md style)

**seam/hook_dispatch G1** — CLOSED 2026-08-01 (round 13 R1). `HookSystem.
_ordered` re-derives the listener list per dispatch from the live combat state
instead of sorting a frozen registration list; cards walk Hand/Draw/Discard/
Exhaust/Play (`PlayerCombatState.cs:70-80`) with the Play leg from
`_playing_card`, and each card is followed by its affliction then its
enchantment (`CombatState.cs:456-465`). steps 9 + 44 close. Registration list
survives as membership only.

**seam/hook_dispatch G2 (slot half)** — CLOSED 2026-08-01 (round 13 R1). Potions
walk `player.potions` by index (`CombatState.cs:436-443`), so a potion procured
into a freed slot 0 dispatches ahead of a longer-held slot-1 potion. step 6
closes; its dormancy argument (only `FairyInABottle` implements a potion hook)
is unaffected and still true.

**seam/hook_dispatch G5** — CLOSED 2026-08-01 (round 13 R1). `Monster` is a
listener in its own category between powers and relics (`CombatState.cs:417-421`,
`Contains` arm `:585`); the two stand-in listeners in `monsters/glory/` are
deleted and their handlers are on `Aeonglass`/`Queen`. 114 sim monster classes ×
94 dispatchers × 4 phase suffixes: zero hook-name collisions, so no monster
method silently became a handler. step 3 closes.

**seam/hook_dispatch G6** — CLOSED 2026-08-01 (round 13 R1), machinery only.
`Affliction` is a listener right after its card (`CombatState.cs:458-461`),
registered at all three acquisition sites and unregistered on clear;
`clear_affliction` now also nulls the `card` back-reference, mirroring
`AfflictionModel.ClearInternal` — without which `HasCard` would have kept a
cleared affliction alive in the walk. Still dormant on content (0/7 sim, 1/10 C#
afflictions define a hook, and that one is unported Hexed).

**seam/hook_dispatch G7** — NARROWED 2026-08-01 (round 13 R1). State half of
`Contains` implemented as `hook_contains()` on Card, Relic, Affliction,
Enchantment and Monster, plus `IsActiveForHooks` on the player with all four C#
lifecycle sites. REMAINS OPEN: the `Power` (`:599`) and `Potion` (`:595`) arms,
blocked on another lane's files — exact one-method diffs in R1-report §7. steps
4, 11, 12, 45 close; step 16 is run-side and belongs to N5. The record's
stale_listener_plugin evidence is stale: fresh run is 0 hits / 178,595 calls /
3826 passed, and HEAD already reported 0.

**seam/hook_dispatch N5** — untouched, and now has a foundation. R1's
`_derive`/`_merge_extras`/`hook_contains` split is deliberately run-level-ready:
see R1-report §10. Separately, `run.py:1113-1116` `_map_listeners` returns
`[*relics, *deck]` where `RunState.cs:548-576` is deck-first — a LIVE ordering
divergence (LanternKeyCard vs map-hook relics), not dormant.

**seam/hook_dispatch (new) — `combat_is_over` is narrower than
`IsOverOrEnding`.** `HookSystem.combat_is_over` tests
`phase == COMBAT_OVER` (C#'s `!IsInProgress` half only) where
`Hook.IterateCombatHookListeners` gates on `CombatManager.IsOverOrEnding`.
`CombatState.is_over_or_ending` is the faithful predicate and already exists.
Affects all 73 gated dispatchers between the killing blow and teardown.

---

## 10. What this exposes for N5 (out of scope, per the brief)

N5 needs a run-level listener list with the same shape:
`RunState.IterateHookListeners` (`RunState.cs:545-596`) = per active player, deck
cards each followed by its Enchantment; then, ONLY when
`childCombatState == null`, non-melted relics and potions, Modifiers,
BadgeModels, MultiplayerScalingModel; then the same lazy `Contains`
(`:577-583`, arms `:715-731`); then, when there IS a child combat, the WHOLE
combat list appended (`:588-595`).

Three pieces of this lane's design are directly reusable and were built with
that in mind:

1. **`hook_contains()` is listener-side, not combat-side.** `RunState.Contains`
   (`:715-731`) is the same predicate as `CombatState.Contains` minus the power,
   orb and monster arms, so a run-level walk can reuse the identical methods
   with no changes. `Card.hook_contains` already tolerates `combat is None`
   (returns True), which is the out-of-combat case.
2. **`_derive`'s creature loop is the only combat-specific part.** The
   `groups`/`excluded` protocol and `_merge_extras` are generic: a
   `RunHookSystem` would supply a different `_derive` (deck cards + enchantments
   + relics + potions) and inherit everything else, including the presence gate,
   `_phased`, and the per-item filter.
3. **The delegation at `:588-595` is a list concatenation**, so a run-level
   `_derive` can literally end with `out.extend(combat.hooks._ordered())` once
   both exist — no shared registry needed, which is the thing that makes the
   sim's two disjoint systems hard to unify today.

The one thing N5 must NOT copy: `_merge_extras`. At run level there is no
registry to outlive the structure — the deck IS the list — so a run-level walk
should be a pure derivation with no extras path.

---

## 11. Footprint touched

Engine (all inside the declared footprint):
`sts2_rl/hooks.py`, `sts2_rl/combat.py`, `sts2_rl/player.py`, `sts2_rl/cmds.py`,
`sts2_rl/cards/base.py`, `sts2_rl/enchantments.py`, `sts2_rl/afflictions.py`,
`sts2_rl/relics/base.py`, `sts2_rl/monsters/base.py`,
`sts2_rl/monsters/glory/aeonglass.py`, `sts2_rl/monsters/glory/queen.py`.

`sts2_rl/history.py` was in the footprint and needed no change: `CombatHistory`
already declared `hook_category = CAT_HISTORY` and `_derive` emits it from
`combat.history` ahead of the creature walk (note N3). It has no C# counterpart
and therefore no `hook_contains`.

Tests: `test/test_round13_listener_derivation.py` (new),
`test/test_hook_order.py`, `test/test_task8_aeonglass_generated_wither.py`.

No `audit/records/**` or `audit/GAP-QUEUE.md` file was edited. No git index
command was run.

---

# Fix pass (2026-08-01)

Response to `R1-review.md`. Everything below was re-derived from the C# and
re-executed; where the review is right I say so, where its *remedy* is wrong I
say why. **The review's three findings (R-1, R-2, R-3) are all real.** Two are
now FIXED in code rather than narrowed; the third is partly wired and honestly
narrowed. Verdicts move: **G1 stays FIXED (R-2 closed, not left as residue),
G5 stays FIXED (R-1 closed), G7 remains NARROWED** — for a longer list of
reasons than §6 gave.

## FP-0. The review's suggested remedy for R-1 does not work — the defect is wider than diagnosed

The review proposed (its §D): *"compute `should_remove` into a local at :159,
dispatch `hooks.on_death(target, False)`, and assign `target.
retained_after_death` after it."* **That fixes nothing.** `Creature.
is_removed_from_combat` is `is_gone and not retained_after_death`, and
`retained_after_death` *defaults* to `False` — so the predicate is already
`True` the moment HP reaches zero, before `_resolve_death` is entered at all.
Moving the assignment later leaves the flag at its default for the whole
window. Executed on the pre-fix tree:

```
monster in _ordered before death: True
at 0 HP, BEFORE _resolve_death runs at all:
   is_gone True  retained_after_death False  is_removed_from_combat True  hook_contains False
after kill: retained_after_death: False | is_removed_from_combat: True
dying monster's own on_death delivered: []
```

So the defect is not "the sim assigns one flag one line early". It is that the
sim's `is_removed_from_combat` is a **prediction** ("will this corpse be
removed?"), evaluated eagerly at the HP write, where C#'s `Creature.CombatState
!= null` is an **event** — the back-pointer is nulled by `CombatState.
RemoveCreature` (`CombatState.cs:299-302`), reached only from
`CreatureCmd.cs:529` and `:601`. The window the sim gets wrong therefore also
covers `Hook.ShouldDie` (`:505`), `Hook.ShouldCreatureBeRemovedFromCombat-
AfterDeath` (`:508`), and — in the damage path — `Hook.AfterCurrentHpChanged`
(`CreatureCmd.cs:382`) and `Hook.AfterDamageGiven` (`:390`), all of which C#
runs before `Kill()` at `:409`.

### C# statement order, re-derived here from `CreatureCmd.cs:490-573`

```
:505  if (force || creature.MaxHp <= 0 || Hook.ShouldDie(...))        <- listener
:508  shouldRemoveFromCombat = Hook.ShouldCreature...AfterDeath(...)  <- listener
:519  await Hook.AfterDeath(..., wasRemovalPrevented: false, ...)     <- listener
:523      if (shouldRemoveFromCombat && Side == Enemy && Enemies.Contains(creature))
:525          CombatManager.Instance.RemoveCreature(creature)
:527          if (monster != null && !monster.IsPerformingMove)
:529              combatState.RemoveCreature(creature)   // <- Creature.CombatState = null
:533-537  RemoveAllPowersAfterDeath() + await item.AfterRemoved(creature)
:553      player.DeactivateHooks()                        // player arm only
```

Three gates on the removal, not one, and I mirrored all three. The
`IsPerformingMove` gate at `:527` is completed by `MonsterModel.PerformMove`'s
own tail (`MonsterModel.cs:447-451`): `IsPerformingMove = false`, then `if
(Creature.IsDead && Hook.ShouldCreatureBeRemovedFromCombatAfterDeath(...))
combatState.RemoveCreature(Creature)`. The escape path is `CreatureCmd.cs:601`
-> `CombatState.CreatureEscaped` (`CombatState.cs:266-270`) -> `RemoveCreature`,
unconditional and with no hook.

### The fix

`Monster` gains **`combat_removal_committed`** (`monsters/base.py`), an EVENT
flag set at exactly the two `CombatState.RemoveCreature` statements, and
`Monster.hook_contains()` reads it instead of `is_removed_from_combat`:

* `cmds.py::_resolve_death` — after `hooks.on_death(target, False)`, gated on
  `side == "enemy"` (`:523`), `not retained_after_death` (the sim's cached
  answer to `:508`) and `not is_performing_move` (`:527`);
* `cmds.py::CreatureCmd.escape` — unconditional for an enemy (`:601`);
* `combat.py::CombatState._perform_move` (new, wrapping `enemy.take_turn`) —
  raises/clears `is_performing_move` (`MonsterModel.cs:440`/`:447`) and
  completes the deferred removal (`:448-451`).

`Creature.is_removed_from_combat` is **untouched** — `creatures.py` is outside
the footprint, and the prediction is still correct for its own callers, all of
which read it after the death sequence has finished. Blast radius of the change
is therefore exactly one predicate: `Monster.hook_contains`.

**Why this matters beyond the machinery:** the §7 `Power` diff, as the review
approved it, carries the SAME defect — `not owner.is_removed_from_combat` would
drop a power from its own owner's `AfterDeath`, where C# has both the
back-pointer (`:529` is later) and the power itself (`:533-537` is later)
still in place. Corrected diff in FP-6. Had the controller landed the original
diff, `ReattachPower`/`SteamEruptionPower`/`AdaptablePower` would have survived
only by accident (they retain their creature, so `retained_after_death` is set
True before the dispatch); any non-retaining self-death power would not have.

## FP-1. G1 / R-2 — the draw-pile leg is now walked top-first (FIXED, not narrowed)

R-2 is real and I re-derived it independently rather than inheriting it:

* `CardPile` is top-first — `MoveToTopInternal` is `_cards.Insert(0, card)`
  (`CardPile.cs:160-167`), `MoveToBottomInternal` is `_cards.Add` (`:139-149`),
  `AddInternal`'s default `index = -1` appends (`:82-96`), `CardPileCmd`'s
  default position is `CardPilePosition.Bottom` (`CardPileCmd.cs:259`);
* the decisive citation the review did not give: **a draw takes
  `drawPile.Cards.FirstOrDefault()`** (`CardPileCmd.cs:843`), so index 0 *is*
  the top, and `CombatState.cs:452-455` enumerates top -> bottom;
* the sim's own code says the opposite orientation in as many words —
  `player.py:581` `draw_pile.pop()  # end of list = top of pile`, and
  `CardPileCmd.add_to_draw` (`cmds.py:1492-1505`) converts a game index `p` to
  sim index `count - p` with the comment *"The game pile counts index 0 = top
  (next drawn); the sim stores its top at the END"*.

Fixed in `hooks.py::_derive` — and only there. **The draw pile is still stored
top-last; only the listener walk enumerates it reversed** (`extend(reversed(
player.draw_pile))` on the fast path, `reversed(player.draw_pile)` in the
per-card path). Hand, discard and exhaust are append-at-end in both engines and
are untouched.

Pinned by `test_the_draw_pile_walks_top_first`, and
`test_a_card_that_changes_pile_changes_its_dispatch_position` was rewritten to
move the pile's BOTTOM card so it still demonstrates a *change* of position
under the new orientation.

Cost, measured: `extend(reversed(pile))` vs `extend(pile)` on a 25-card draw
pile is **0.404 µs vs 0.219 µs**, i.e. +0.185 µs per derivation against
`_ordered()`'s 1.75 µs on a 32-listener combat — ~+10 % of the derivation,
which the 84 % presence gate dilutes to well under 1 % of dispatch. No
redesign.

**Consequently G1 closes FIXED, not NARROWED.** The review's NARROWED ruling
was explicitly conditional on the reversal being left in place; it is not.

## FP-2. G7 / R-3 — `has_been_removed_from_state` is now set in production for Cards; Relics stay machinery-only

R-3 is real: before this pass neither flag was assigned anywhere outside the
pins. C# carriers re-read: `CardModel.cs:948` (declaration), `:1228`
(`AfterCloned` clears), `:1604-1608` (`RemoveFromState` sets), called from
`CardPileCmd.cs:79`, `CardPileCmd.cs:189` and `CardCmd.cs:506`;
`RelicModel.cs:420`/`:525`/`:531-534` from `Player.RemoveRelicInternal`
(`Player.cs:476-492`).

**Card — wired at 2 of the 3 C# set sites plus the clear site, all in
footprint:**

| C# site | sim site | status |
|---|---|---|
| `CardPileCmd.cs:189` (`RemoveFromCombat`) | `combat.py::_resolve_card_play`, the played-Power-card block (its result pile is `PileType.None` -> `CardModel.cs:1979-1982` -> `RemoveFromCombat`) | **wired** |
| `CardCmd.cs:506` (transform tail) | `cmds.py::CardCmd.transform_to_random` | **wired** |
| `CardPileCmd.cs:79` (deck removal) | `RunState.remove_cards` (`run.py:455-460`) | **BLOCKED-ON-FOOTPRINT** — one line, `card.has_been_removed_from_state = True` after `self.before_card_removed(card)`. Unobservable today: a card removed from the deck is never registered in a later combat. |
| `CardModel.cs:1228` (`AfterCloned` clears) | `Card.reset_combat_state` — the sim's stand-in for the per-combat clone, since one `Card` object serves a whole run | **wired** (load-bearing: without it a Power card played once would never listen again) |

**Relic — still machinery-only, and the comment now says so** (as `is_melted`'s
already did). Enumerated rather than asserted: every sim relic-removal site is a
bare `run.relics.remove(...)` — `events/ranwid_the_elder.py:86`,
`events/relic_trader.py:63`, `relics/toy_box.py:45`,
`conformance/runner.py:468` and `:733`. There is no `RelicCmd.Remove` command to
hang the flag off, and all five files are outside the footprint. The LIVE leg of
the `:597` arm is `Owner.IsActiveForHooks`.

**G7 therefore stays NARROWED**, and for three named reasons rather than one:
the `Power` (`:599`) and `Potion` (`:595`) arms are still absent
(blocked-on-footprint, diffs in FP-6); the Relic arm's first leg is never set;
the Card arm's first leg is set at two of three sites.

## FP-3. The contradictory `player.py` comment (review defect 1)

Rewritten (`player.py:78-112`). It now states that single-player **does** reach
`ActivateHooks`, names the caller chain (`Creature.HealInternal`,
`Creature.cs:477-485` -> `Player.ReviveBeforeCombatEnd`, `Player.cs:821-827` <-
`CombatManager.cs:986`, one statement before `Hook.AfterCombatEnd` at `:988`),
quotes `Player.cs:813-819` on why the order is load-bearing, notes that C#'s own
"likely only called in multiplayer" is a guess in a doc comment, records that
**seven** call sites reach `_end_combat(player_won=True)` without the
`_has_pending_loss` test (verified: `cmds.py:783`, `combat.py:709`,
`combat.py:1532`, `powers.py:4565`, `powers.py:4651`, `relics/base.py:498`,
`conformance/runner.py:236`), and ends with *"do not delete the two lines that
do"* plus the pin name.

Re-proved the effect myself, without reverting anything (another lane is live) —
by running `_end_combat_internal`'s two halves separately:

```
WITHOUT ActivateHooks: max_hp 80 -> 80
LIVE tree            : max_hp 80 -> 81
```

## FP-4. The remaining review items

* **defect 3** — `combat.py`'s "six hook-implementing card classes" replaced by
  the re-executed census: **nine** (Bolas, Clash, Drum of Battle, Enthralled,
  Howl from Beyond, Normality, Regret, Stomp, Thrumming Hatchet), over 204
  `Card` subclasses × 328 dispatch names. The review's list is exactly right.
* **defect 4** — `monsters/base.py`'s "there is no window in which a constructed
  monster is not in the combat" now names the window (F7:
  `Encounter.create_monsters` builds the roster before `CombatState.enemies` is
  assigned, so those few dispatches go through `_merge_extras`' tail).
* **defect 5** — `test_an_affliction_whose_card_left_its_pile_is_not_derived`
  renamed to `..._is_seated_by_the_extras_merge`, and its docstring now opens by
  stating that it pins a KNOWN DIVERGENCE: C# is unambiguous for cards (a card
  in no pile is in no `AllPiles` entry, and `CardModel.ShouldReceiveCombatHooks`
  is `Pile?.IsCombatPile ?? false`, `CardModel.cs:1045`), and `_merge_extras` is
  a transitional safety net, not a design nicety. The review is right that §2's
  "could not reach vs refused" framing understated this.
* **defect 6** — `_each`'s docstring drops "92 %" for the measured 84 % (2,100
  of 13,275 `_each` calls got past the gate on the round-13 benchmark), with the
  workload named and flagged as workload-dependent.
* **decorative citations** — `AfflictionModel.cs:146` and `MonsterModel.cs:51`
  are now explicitly labelled as corroboration with zero readers in this build;
  the load-bearing citations (`CombatState.cs:458-461` and `:417-421`) are named
  as such in both comments.

## FP-5. New pins and their RED evidence

All ten were written before the corresponding fix and run against the live tree
in that state (no revert — another lane is live; the RED came from the tests
being new).

| pin | RED evidence on the pre-fix tree |
|---|---|
| `test_a_dying_monster_receives_its_own_after_death` | `assert [] == [(<FuzzyWurmCrawler>, False)]` — **the headline; behavioural** |
| `test_a_dying_monster_is_consulted_by_its_own_should_die` | `assert [] == [<FuzzyWurmCrawler>]` — behavioural |
| `test_a_monster_removed_from_combat_stops_being_dispatched_to` (rewritten) | `assert [] == [<FuzzyWurmCrawler>]` at the "at 0 HP, nothing has removed it yet" step — behavioural |
| `test_a_death_vetoed_corpse_is_still_dispatched_to` | `AttributeError: 'FuzzyWurmCrawler' object has no attribute 'combat_removal_committed'` |
| `test_an_escaped_monster_stops_being_dispatched_to` | same `AttributeError` |
| `test_a_monster_that_dies_during_its_own_move_leaves_when_the_move_ends` | same `AttributeError` |
| `test_the_draw_pile_walks_top_first` | `assert [Strike, Defend] == [Defend, Strike]` — behavioural |
| `test_a_played_power_card_is_flagged_removed_from_state` | `assert False is True where False = Inflame.has_been_removed_from_state` |
| `test_a_transformed_card_is_flagged_removed_from_state` | `assert False is True where False = Strike.has_been_removed_from_state` |
| `test_combat_setup_clears_the_removed_from_state_flag` | `assert True is False where True = Inflame.has_been_removed_from_state` |

Aggregate before the fixes: `10 failed, 21 passed`. After: `31 passed`.

The G5 collision census was re-executed after adding the three new `Monster`
members, with every monster module force-imported this time (`pkgutil.
walk_packages`), which resolves the report's 114 / the review's 113
disagreement — both were right, counting `Monster` itself or not:

```
classes: 114 | names: 328 | collisions: ['Aeonglass.on_card_generated_for_combat', 'Queen.on_death']
new attrs are hook names? set()
```

## FP-6. Corrected close proposals and blocked diffs

These SUPERSEDE §6 and §7 above wherever they differ. The controller should
apply these.

**step 3 (G5) → `faithful`.** §6's note stands, plus: *"The dying creature's own
`AfterDeath` is delivered to it. `Monster.hook_contains` reads
`combat_removal_committed`, an event flag set at the two `CombatState.
RemoveCreature` statements (`CreatureCmd.cs:529` under the `:523`/`:527` gates,
and `:601` via `CombatState.CreatureEscaped`), NOT the eager
`Creature.is_removed_from_combat` prediction, which is `is_gone and not
retained_after_death` and so goes true at the HP write — before `ShouldDie`
(`:505`), `ShouldCreatureBeRemovedFromCombatAfterDeath` (`:508`) and
`AfterDeath` (`:519`) have run. `CombatState._perform_move` mirrors the
`IsPerformingMove` deferral (`MonsterModel.cs:440/:447-451`). This matters for
the entry's own named trigger: KinPriest's `AfterDeath` has an explicit `else
if (creature == base.Creature)` arm (`KinPriest.cs:104-107`), and eight of the
ten C# monster `AfterDeath` overrides are self-death-only, so the port G5
unblocks lands precisely on this hook."*
**Do NOT open the companion R-1 entry the review asked for — it is closed.**

**steps 9 / 44 (G1) → `faithful`** (not narrowed). §6's notes stand, with two
amendments:
* replace the "six hook-implementing card classes" figure with **nine** (Bolas,
  Clash, Drum of Battle, Enthralled, Howl from Beyond, Normality, Regret, Stomp,
  Thrumming Hatchet; the census the entry inherited missed
  `HowlFromBeyondCard.after_auto_post_play_phase_entered` among others);
* add: *"Pile ORIENTATION is included: `CardPile` is top-first
  (`CardPile.cs:160-167` `Insert(0, …)`; a draw takes `Cards.FirstOrDefault()`,
  `CardPileCmd.cs:843`) where the sim stores the draw pile's top at the END
  (`player.py:581`; `CardPileCmd.add_to_draw` converts a game index `p` to sim
  index `count - p`), so `HookSystem._derive` walks the draw pile REVERSED. The
  pile's storage order is unchanged — only the listener walk is flipped. Hand,
  discard and exhaust append at the end in both engines and need no flip."*

**step 12 (G7) → NARROWED** (§6 said `faithful`; that was too generous even
before this pass). Close note: *"Card (`:593`), Relic (`:597`), Affliction
(`:591`), Enchantment (`:589`) and Monster (`:585`) arms are implemented as
`hook_contains()` predicates. Orb (`:587`) waived under N7; Badge / Modifier /
Achievement / MultiplayerScaling (`:575-583`) under N1/N4. THREE residues: (a)
the PowerModel (`:599`) and PotionModel (`:595`) arms are absent — one method
each on `Power`/`Potion`, files owned by other lanes this wave, exact diffs
below; (b) the Relic arm's first leg, `HasBeenRemovedFromState`, is declared but
never set in production — machinery-only, like `is_melted`; every sim relic
removal is a bare `run.relics.remove(...)` in `events/ranwid_the_elder.py`,
`events/relic_trader.py`, `relics/toy_box.py`, `conformance/runner.py`, none of
which is a `RelicCmd.Remove`; the live leg of that arm is
`Owner.IsActiveForHooks`; (c) the Card arm's first leg is now set at
`CardPileCmd.cs:189` (played Power card) and `CardCmd.cs:506` (transform
original) and cleared at `CardModel.cs:1228`'s counterpart
(`Card.reset_combat_state`), but NOT at `CardPileCmd.cs:79` (deck removal,
`run.py`)."*
Reasoning replaced: unchanged from §6 ("every sim dispatcher walks a
`list(self._listeners)` snapshot with no re-check" — doubly wrong), plus the
report's own arm table, which presented both `HasBeenRemovedFromState` legs as
implemented without saying they were never set.

**steps 4 / 11 / 45, step 6, step 16, guard G6** — apply §6 as written; the
review confirmed each and this pass did not disturb them.

**guard G7 → NARROWED**, with step 12's three residues named.

**steps 41 / 43** — one-line freshening, as §6 proposed.

### §7 blocked diffs, CORRECTED

`sts2_rl/powers.py` — the `Owner.CombatState != null` leg must read the removal
EVENT, not the prediction. **This is a correction to §7, not a restatement:**

```python
    def hook_contains(self) -> bool:
        """`CombatState.Contains`' PowerModel arm (CombatState.cs:599):

            powerModel.Owner.CombatState != null
                && (powerModel.Owner.Player?.IsActiveForHooks ?? true)

        Note what it does NOT test: that the power is still attached to its
        owner. A power an earlier listener removed during the SAME dispatch is
        still called — which is why the recorded `on_enemy_side_end ->
        IntangiblePower` probe hit was faithful rather than a bug.

        `Owner.CombatState != null` is `not owner.combat_removal_committed`
        for a monster — the EVENT set at CreatureCmd.cs:529/:601, NOT the eager
        `is_removed_from_combat` prediction, which goes true at the HP write.
        The difference is load-bearing here: C# nulls the back-pointer at
        :523-531 and strips the powers at :533-537, both AFTER Hook.AfterDeath
        (:519), so a power IS a listener for its own owner's death.
        For the PLAYER the leg is always true inside a combat (players are NOT
        removed on death — Player.cs:107-110 says that is the whole reason
        IsActiveForHooks exists), so the player leg is the flag alone.
        """
        owner = self.owner
        if getattr(owner, "side", None) == "player":
            return owner.is_active_for_hooks
        return not getattr(owner, "combat_removal_committed", False)
```

`sts2_rl/potions.py` — **unchanged from §7** (the PotionModel arm `:595` has no
`CombatState` leg): apply the diff exactly as printed there.

`sts2_rl/run.py` (NEW, small) — `RunState.remove_cards` should set
`card.has_been_removed_from_state = True` after `self.before_card_removed(card)`,
mirroring `CardPileCmd.cs:79`. Dormant (a removed deck card is never registered
in a later combat); listed for completeness of the Card arm.

### Queue annotations, corrected

* **G1** — as §9, plus: *"draw-pile ORIENTATION included: the walk enumerates
  the draw pile top-first (`CardPile.cs:160-167`, `CardPileCmd.cs:843`) where
  the sim stores its top last; storage unchanged, walk reversed."* Drop "six
  hook-implementing card classes" → nine.
* **G5** — as §9, plus: *"the dying creature receives its own AfterDeath:
  `Monster.combat_removal_committed` is set at `CreatureCmd.cs:529`/`:601`, not
  predicted at the HP write; `IsPerformingMove` deferral mirrored
  (`MonsterModel.cs:447-451`)."*
* **G7** — as §9, but NARROWED for three reasons, not one: Power/Potion arms
  missing; Relic `HasBeenRemovedFromState` never set (machinery-only); Card
  `HasBeenRemovedFromState` set at 2 of 3 C# sites.
* **NEW, `seam/creature_cmds` (or wherever `is_removed_from_combat` lives)** —
  *"`Creature.is_removed_from_combat` is an EAGER PREDICTION (`is_gone and not
  retained_after_death`), true from the HP write, where C#'s `Creature.
  CombatState` is nulled only at `CombatState.RemoveCreature`
  (`CreatureCmd.cs:529`/`:601`). Round 13 R1 fixed the one consumer inside its
  footprint (the hook walk) with an explicit event flag. TWO consumers still
  read the prediction and diverge for the whole death sequence:
  `can_receive_powers` (`cmds.py:65-75`, C#'s `Creature.CanReceivePowers`
  `Creature.cs:308-322` is `CombatState != null && …`) and
  `_combat_contains_creature` (`cmds.py:78-99`, C#'s `ICombatState.
  ContainsCreature` is physical list membership, which survives until
  `RemoveCreature`). Both were left alone deliberately: `creatures.py` is
  outside R1's footprint and changing the property would have live blast radius
  on the damage/power pipelines."*

## FP-7. Findings this pass added

* **FP-0's headline**: the review's remedy for its own R-1 would not have worked;
  the defect is a prediction-vs-event mismatch, not a statement-order slip. Two
  further consumers of the same prediction are queued above.
* **The approved §7 `Power` diff would have shipped R-1 into `powers.py`.**
  Corrected above. This is the round-12 lesson again in a new place: a diff
  reviewed as "correct C#" was correct about the *arm* and wrong about the
  *timing of the sim value it reads*.
* `CreatureCmd.cs:527`'s `!monster.IsPerformingMove` gate and its completion at
  `MonsterModel.cs:447-451` are not mentioned anywhere in the record or the
  review; the sim now models both.
* The sim resolves death EARLIER than C# in the damage path — `_resolve_death`
  runs at `DamageCmd.deal` step 8, before `after_damage_given` /
  `after_damage_received`, where `CreatureCmd.Damage` runs `Kill()` at `:409`
  AFTER `Hook.AfterDamageGiven` (`:390`) and `Hook.AfterDamageReceived`
  (`:394`). Not in scope here and it has no observable effect today (the victim's
  `AfterDamageReceived` is skipped on a killing blow anyway, `:392`), but it is
  the reason the new flag alone cannot make the sim's whole damage tail
  order-faithful. Recorded, not fixed.

## FP-8. Tests

Files changed: `test/test_round13_listener_derivation.py` only (10 new/rewritten
pins, one rename). Engine files changed: `sts2_rl/hooks.py`,
`sts2_rl/combat.py`, `sts2_rl/cmds.py`, `sts2_rl/player.py`,
`sts2_rl/cards/base.py`, `sts2_rl/relics/base.py`, `sts2_rl/monsters/base.py`,
`sts2_rl/afflictions.py`. All inside the declared footprint. No `audit/**` edit,
no git index command.

```
py -m pytest test/test_round13_listener_derivation.py -q
    -> 10 failed, 21 passed      (BEFORE the fixes — the RED table in FP-5)
    -> 31 passed                 (AFTER)

py -m pytest test/test_round13_listener_derivation.py test/test_hook_order.py \
    test/test_task8_hook_presence_cache.py test/test_task8_aeonglass_generated_wither.py \
    test/test_combat_over_hook_gate.py test/test_task8_pile_move_and_generated_hooks.py \
    test/test_discard_draw_order.py test/test_combat_veto_and_dealer_event.py \
    test/test_turn_start_split.py test/test_glory.py test/test_can_receive_powers.py \
    test/test_exhaust_escape_removal.py test/test_hive.py test/test_monster_tier_families.py \
    test/test_overgrowth_powers.py test/test_turn_start_snapshot.py -q
    -> 564 passed

py -m pytest test/test_ancients.py test/test_card_generation_pool.py \
    test/test_card_plays_started.py test/test_card_residue_gaps.py \
    test/test_card_residue_gaps2.py test/test_colorless.py test/test_curses.py \
    test/test_engine_features.py test/test_ironclad_final_cards.py \
    test/test_live_false_gaps.py test/test_printed_vars.py test/test_relics.py \
    test/test_underdocks.py test/test_unplayable_cost.py -q
    -> 670 passed          (the draw-pile reversal's blast radius: card content)

py -m pytest test/test_conformance_combat.py test/test_conformance_determinism.py \
    test/test_conformance_map.py test/test_conformance_player_state.py \
    test/test_conformance_pools.py test/test_conformance_recording.py \
    test/test_conformance_relic_bag.py test/test_conformance_rooms.py \
    test/test_conformance_runner.py test/test_conformance_save.py -q
    -> 95 passed, 6 xfailed        (test_conformance_floor_state.py excluded: known
                                    missing 933T floor_49 fixture, never counted)

py -m pytest test/test_combat_card_db.py test/test_combat_ending_command_guards.py \
    test/test_combat_rng.py test/test_encounter_slots.py test/test_event_combat_layout.py \
    test/test_extra_turn_guard.py test/test_is_dead_early_returns.py \
    test/test_state_machine_construction.py test/test_turn_structure_gaps.py \
    test/test_turn_structure_residues.py test/test_encounter_selection_rng.py -q
    -> 177 passed          (the _perform_move wrapper's blast radius)

py -m pytest test/test_can_receive_powers.py test/test_exhaust_escape_removal.py \
    test/test_hive.py test/test_monster_tier_families.py test/test_overgrowth_powers.py \
    test/test_turn_start_snapshot.py test/test_auto_play_from_draw_pile.py \
    test/test_monster_branch_audit.py test/test_powers.py test/test_ironclad_powers.py -q
    -> 493 passed          (the death-path change's blast radius)
```

Full-suite gating is the controller's, per protocol; it was not run here.

## FP-9. Final verdicts

| gap | verdict after this pass |
|---|---|
| **G1** (steps 9, 44) | **FIXED.** Per-dispatch derivation, `AllPiles` sequence, the card→affliction→enchantment triple, the Play seam AND the draw-pile orientation (R-2). No residue. |
| **G2, slot half** (step 6) | **FIXED.** Unchanged by this pass; the review confirmed it independently. |
| **G5** (step 3) | **FIXED**, R-1 included. Monster is a listener in `CombatState.cs:417-421`'s slot, both shims deleted, census clean at 114 × 328 with 2 intended collisions, and the dying creature is a listener for its own death sequence. No companion entry needed. |
| **G6** (guard G6) | **FIXED (machinery), DORMANT (content).** Unchanged; the review re-executed both censuses. |
| **G7** (steps 4, 11, 12, 45; guard G7) | **NARROWED.** Missing: Power (`:599`) and Potion (`:595`) arms (blocked on other lanes' files; corrected diffs in FP-6). Machinery-only: Relic `HasBeenRemovedFromState`. Partial: Card `HasBeenRemovedFromState`, set at 2 of 3 C# sites. Step 16 stays LEFT-OPEN under N5. |
