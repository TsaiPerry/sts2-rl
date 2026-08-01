# R1 review — hook_dispatch registry family (G1 + G7-state + G5 + G6)

Reviewer pass, round 13. Everything below was re-derived from the C# at
`c:\Users\Perry\Desktop\Slay the Spire 2` and re-executed against the live
worktree and a `git archive HEAD` export in the scratchpad. Nothing is taken
from the brief or the report on trust; where I agree with them I say so, where
I do not I say why.

**Verdict: NEEDS-FIXES.** The engineering is the best I have reviewed in this
campaign — the derivation is a faithful port of `CombatState.cs:410-493`, the
`Contains` arms are arm-for-arm exact, every instrumentation number in the
report reproduces to the digit, and F4 is a genuine, load-bearing catch that I
independently proved would have silently lost a relic effect. But three things
must land before the record closes:

* **R-1 (new, mine, outranks the task's findings).** G5's new
  `Monster.hook_contains` silently removes a **dying monster from its own
  `AfterDeath` dispatch**, because `_resolve_death` assigns
  `retained_after_death` *before* `hooks.on_death`, where C# removes the
  creature only *after* `Hook.AfterDeath` (`CreatureCmd.cs:519` vs `:525-529`).
  Eight of the ten C# monster `AfterDeath` overrides are self-death-only —
  including **KinPriest, the entry's own named "concrete trigger" for G5**.
  Dormant on ported content, real in the machinery R1 just built.
* **R-2 (new, mine).** G1 is **not** the exact order: within the DRAW pile the
  sim walks bottom→top where `CardPile` is top-first (`CardPile.cs:160-167`
  `MoveToTopInternal` = `Insert(0, …)`). The pile *sequence* is right; the
  *within-draw-pile* order is reversed. Verified by execution.
* **R-3.** `Card.has_been_removed_from_state` / `Relic.has_been_removed_from_state`
  are **never set anywhere in production code** — those legs are machinery-only,
  exactly like `is_melted`, and the report's arm table presents them as
  implemented without saying so.

Consequently **G1 and G7 should close as NARROWED, not FIXED**; G2-slot, G5
(machinery) and G6 close as proposed, with G5 carrying R-1 as a new open entry.
None of this is a regression against HEAD — every defect above is either
pre-existing or newly *expressible* rather than newly *wrong* — so the change
is safe to fold; it is the record wording that must not overstate.

---

## A. THE DERIVATION ORDER (G1) — **PASS with one residual (R-2)**

`CombatState.IterateHookListeners` re-read in full (`CombatState.cs:410-493`).
Category by category, against `HookSystem._derive` (`hooks.py:323-459`):

| C# | line | sim | verdict |
|---|---|---|---|
| `_allies` then `_enemies` as ONE index space | `:413-415` | `creatures = [player] + enemies`, `enumerate` gives the rank | exact |
| `list.AddRange(creature.Powers)` | `:416` | `extend(creature.powers.values())`, **before** the active check | exact |
| `creature.Player == null -> list.Add(creature.Monster)` | `:417-421` | `add(creature)` then `continue` | exact |
| `if (!player.IsActiveForHooks) continue` | `:424-427` | `if player.is_active_for_hooks:` … `else:` records `excluded` | exact |
| relics, skipping `IsMelted` | `:428-435`, skip at `:431` | `for relic in combat.relics: if relic.is_melted: continue` | exact |
| `PotionSlots` by INDEX, skipping nulls | `:436-443` | `for potion in player.potions: if potion is not None` | exact |
| `OrbQueue.Orbs` | `:448` | waived, sim has no orbs (note N7); slot reserved | acceptable |
| per pile per card: card, Affliction, Enchantment | `:449-467` (`:457`/`:458-461`/`:462-465`) | slow leg emits exactly that triple | exact |
| `Modifiers` / `BadgeModels` / `MultiplayerScalingModel` | `:470-481` | none exist in the sim; nothing registers them | acceptable (N1/N4) |

I confirm the two structural subtleties the prompt singled out:

* **Powers are added at `:416`, one line BEFORE the `:424` player-active
  check.** A dead player's powers therefore stay in the list and are dropped, if
  at all, only by the lazy `PowerModel` arm at `:599`. `_derive` reproduces this
  literally (`hooks.py:367` runs unconditionally; the `is_active_for_hooks`
  branch starts at `:380`). Pinned by
  `test_an_inactive_player_contributes_only_its_powers`.
* **`AllPiles` is `new CardPile[5] { Hand, DrawPile, DiscardPile, ExhaustPile,
  PlayPile }`** — `PlayerCombatState.cs:70-80`, array literal at `:76`, verified
  verbatim. The sim's four-pile sequence matches, and the fifth-pile seam is
  honest: `player._playing_card` is excluded from the discard leg
  (`hooks.py:419-420`) and appended after the exhaust pile (`:428-435`), which
  is where `CardCmd.cs:114-116` (`if (card.Pile == null) await
  CardPileCmd.Add(card, PileType.Play)`) and `CardModel.cs:1978-1982`
  (`pile.Type == PileType.Play` when the result-pile move runs) put it. The
  block is a single named leg; collapsing it into a fifth `extend()` later is a
  one-line change, as claimed.

**A pile move really does move position.** Verified independently, not just via
the lane's test: two cards registered in the draw pile in a fixed order swap
dispatch position when one is moved to the hand, with no register/unregister
(`test_a_card_that_changes_pile_changes_its_dispatch_position` fails on the
HEAD export with `[Strike, Defend] == [Defend, Strike]` — a behavioural RED, not
an import error).

**Serendipitously correct, worth recording:** a Power card mid-`OnPlay` is in no
sim pile at all (`combat.py:914-916` only parks non-Power cards), so `_derive`
cannot reach it and `_merge_extras` seats it at the end of the player's card
group — which *is* the Play slot, since Play is last in `AllPiles`. Right answer
by a different route; nothing documents that it is load-bearing.

### R-2 — the draw-pile leg is reversed (NEW, mine)

`CardPile` is **top-first**: `MoveToTopInternal` is `_cards.Insert(0, card)`
(`CardPile.cs:160-167`), `MoveToBottomInternal` is `_cards.Add(card)`
(`:142-149`), and `AddInternal`'s default `index = -1` appends
(`CardPile.cs:82-96`, and `CardPileCmd.Add`'s default is
`CardPilePosition.Bottom`, `CardPileCmd.cs:259`). So `CombatState.cs:452-455`
walks the draw pile **top → bottom**.

The sim's draw pile is **top-last** (`player.py:581` `card =
self.draw_pile.pop()  # end of list = top of pile`; `combat.py:1060`
`draw_pile.append(card)  # end of list = top of pile`). `_derive` iterates
`player.draw_pile` in list order, i.e. **bottom → top**. Executed:

```
draw_pile = [Strike, Defend]      # Defend is the top (pop() takes the end)
derived order:  ['StrikeCard', 'DefendCard']
next draw  ==  DefendCard          # i.e. C#'s DrawPile.Cards[0]
```

C# would emit `Defend, Strike`. **The draw-pile leg is exactly reversed.**

Hand, discard and exhaust are fine: all three are append-at-end in both engines
(`CardPileCmd.cs:259` default Bottom → `_cards.Add`), which is also why the
existing `modify_shuffle_order` reasoning ("the card sitting LATER IN THE
DISCARD fires last") stays correct.

This is **not a regression** — `player.all_cards` had the same reversal, so the
frozen order was wrong the same way. But it means the claim "the sim now
produces C#'s exact order" is false, and G1 must close **NARROWED**. Observable
surface today: `BolasCard` and `ThrummingHatchetCard` both implement
`on_player_turn_start`, and `SlitherEnchantment` implements `on_card_drawn` —
any two of those sitting in the draw pile dispatch in the wrong relative order.
(Nine card classes implement hooks, not the six the record's census claims —
`HowlFromBeyondCard.after_auto_post_play_phase_entered`, `ClashCard`,
`EnthralledCard` and `NormalityCard`'s `should_play_card` are in it; the "six"
figure is inherited stale and is repeated verbatim in the new comment at
`combat.py:1029`.)

---

## B. THE STATE RE-CHECK (G7) — **arms exact; narrowing honest; two legs are machinery-only (R-3)**

`Contains` re-read arm by arm (`CombatState.cs:549-599`). Every implemented arm
is literally right:

| arm | C# | sim | verdict |
|---|---|---|---|
| `MonsterModel` `:585` | `monsterModel.Creature.CombatState != null` — **and nothing else** | `monsters/base.py:110-121` `not self.is_removed_from_combat` | exact (see R-1 for the *timing* of the flag) |
| `OrbModel` `:587` | `!HasBeenRemovedFromState && Owner.IsActiveForHooks` | waived, no orbs | acceptable |
| `EnchantmentModel` `:589` | `HasCard && !Card.HasBeenRemovedFromState && Card.Owner.IsActiveForHooks` | `enchantments.py:54-66` `card is not None and card.hook_contains()` | exact (`EnchantmentModel.HasCard` is `_card != null`, `EnchantmentModel.cs:154`) |
| `AfflictionModel` `:591` | same shape | `afflictions.py:54-65` same composition | exact (`AfflictionModel.HasCard` `:90`) |
| `CardModel` `:593` | `!HasBeenRemovedFromState && Owner.IsActiveForHooks` | `cards/base.py:250-266` | exact in shape; first leg dormant, see R-3 |
| `PotionModel` `:595` | same | **absent** | NARROWED (blocked-on-footprint) |
| `RelicModel` `:597` | same | `relics/base.py:214-229` | exact in shape; first leg dormant, see R-3 |
| `PowerModel` `:599` | `Owner.CombatState != null && (Owner.Player?.IsActiveForHooks ?? true)` | **absent** | NARROWED (blocked-on-footprint) |
| Achievement/Badge/Modifier/MultiplayerScaling `:575-583` | always true | none exist | acceptable |

**The narrowing is honest.** I grepped the live tree: `hook_contains` exists on
`Card`, `Relic`, `Affliction`, `Enchantment`, `Monster` and on nothing else;
`powers.py` and `potions.py` have neither the method nor the flag. Those two
really are the only gap, and the §7 diffs are correct C#:

* the `Power` diff's player leg collapses `Owner.CombatState != null` to `True`
  and reads `is_active_for_hooks` alone — right, because `Player.cs:103-111`
  states in as many words that players are *not* removed from combat on death
  and that this is the entire reason `IsActiveForHooks` exists;
* the `Potion` diff mirrors `PotionModel.cs:202` / `:221-224` (`Discard`) /
  `:229-233` (`RemoveBeforeUse`) correctly, and the "flag is optional because
  the sim already unregisters and nulls the slot" caveat is accurate.

I also checked the report's "moot in practice" claim for the missing Power arm
by enumerating the five sim powers that override
`should_power_be_removed_after_owner_death` (`powers.py:1937, 2483, 2871, 4147,
4194` = Minion / SteamEruption / Reattach / Adaptable / PainfulStabs). Three of
them (`SteamEruption`, `Reattach`, `Adaptable`) also implement
`should_remove_from_combat_after_death`, i.e. they *retain* their creature, so
C# keeps them too; `MinionPower` implements no hook; `PainfulStabsPower.
after_attack` guards on `dealer is not self.owner`, which a removed corpse can
never satisfy. **The claim holds.** Good.

### R-3 — `has_been_removed_from_state` is never set (NEW, mine)

```
$ grep -rn has_been_removed_from_state sts2_rl/ test/
sts2_rl/cards/base.py:144   (declaration)   sts2_rl/cards/base.py:260  (read)
sts2_rl/relics/base.py:126  (declaration)   sts2_rl/relics/base.py:223 (read)
test/test_round13_listener_derivation.py:352, :371   (set, by the pins only)
```

No production site sets either flag. `CardModel.RemoveFromState`
(`CardModel.cs:1604-1608`) is called from `CardPileCmd.cs:79` and `:189` and
`CardCmd.cs:506`; `RelicModel.RemoveInternal` (`RelicModel.cs:531-534`) from
relic removal. The sim has counterparts for some of those. So the first leg of
both arms is **machinery-only**, exactly like `is_melted` — and unlike
`is_melted`, whose comment (`relics/base.py:118-123`) honestly says "this is
False for every relic that exists". The `has_been_removed_from_state` comments
do not. **Fix: say so in the comment and in the record close.** (The second leg,
`Owner.IsActiveForHooks`, is genuinely live — see C.)

Note a related asymmetry the report should own: for CARDS, C#'s answer to "a
registered card that is in no pile" is *unambiguous* — it is not a listener
(`CardModel.cs:1045` `ShouldReceiveCombatHooks => Pile?.IsCombatPile ?? false`,
and it simply is not in `AllPiles`). `_merge_extras` deliberately re-seats such
a card. That is a **known, documented divergence**, not a neutral safety net,
and §2's "could not reach vs refused" framing does not say that for cards the
two coincide. It is the right *transitional* call (dropping them would retire
listeners the sim dispatches to today, silently), but it must be recorded as a
divergence, not as a design nicety.

---

## C. IsActiveForHooks — **PASS, and F4 is real; I proved both halves**

C# side, all four sites re-read and confirmed at the cited lines:

* `Player.cs:112` `public bool IsActiveForHooks { get; private set; }`, with the
  doc comment `:103-111` that names the exact reason it is on `Player` and not
  `Creature`;
* initialised `= Creature.IsAlive` at `:272` and `:438`;
* `DeactivateHooks()` `:857-860`, called from `CreatureCmd.cs:553` — inside the
  real-death arm only, **after** `Hook.AfterDeath` (`:519`) and after the power
  strip (`:533-537`); the prevented arm (`:558-570`) never touches it;
* `ActivateHooks()` `:868-871`, called from `Creature.HealInternal`
  (`Creature.cs:477-485`, the call at `:483`) under `if (isDead && !IsDead)`.

Sim side mirrors all four: `player.py` `is_active_for_hooks = True` in
`__init__`; `cmds.py:182-183` clears it in `_resolve_death`'s real arm after
`on_death` and after `_strip_powers_after_death`; `cmds.py:151-153` re-sets it
in `CreatureCmd.heal` under `was_dead and not target.is_dead`;
`combat.py:779` re-sets it on the `ReviveBeforeCombatEnd` path
(`CombatManager.cs:985-988` — every player's `ReviveBeforeCombatEnd`, *then*
`Hook.AfterCombatEnd`; verified verbatim).

**The pin genuinely fails without it.** Forbidden to revert the live tree, I
copied `sts2_rl/` + `test/` to the scratchpad, deleted *only* the two
`is_active_for_hooks = True` reactivation lines, and ran the file:

```
2 failed, 20 passed
  test_a_revive_puts_the_player_back_in_the_walk
  test_the_victory_path_revives_before_dispatching_after_combat_end
```

and the underlying effect, directly:

```
WITHOUT ActivateHooks: max_hp 80 -> 80 | ChosenCheese fired: False
LIVE tree            : max_hp 80 -> 81 | ChosenCheese fired: True
```

F4 stands, and it is the round-12 lesson repeating: nothing else in the suite
would have caught it.

Two corrections to the report's framing:

* **Reachability is narrower than stated, but real.** The sim's main
  `_check_win_condition` tests `_has_pending_loss` *first* (`combat.py:715`),
  and `_has_pending_loss` includes `player.is_dead` (`:739`) — so the primary
  path can never reach `_end_combat_internal` with a dead player. But **seven
  other call sites call `_end_combat(player_won=True)` directly** without that
  test (`cmds.py:753`, `combat.py:686`, `combat.py:1498`, `powers.py:4565`,
  `powers.py:4651`, `relics/base.py:488`, `conformance/runner.py:236`), so the
  window is genuinely open. Say that, rather than "a fight won at 0 HP".
* **`player.py`'s new comment contradicts the fix.** It says *"`ActivateHooks`
  (:868-871) is multiplayer revival, which single-player never reaches"* — while
  `combat.py:770-779`, added by the same lane, says the reactivation is "the
  entire POINT of doing the revive here" and that "Chosen Cheese and every future
  AfterCombatEnd relic reads through this flag now". Both cannot be true. The
  `player.py` one is the wrong one (C#'s own `ActivateHooks` doc says "*likely*
  only called in multiplayer", and the reachability above shows why "likely" is
  not "never"). **This is the comment that would get the fix deleted by the next
  reader.** Must be corrected.

---

## D. G5 / G6 — **PASS on behaviour and slot; G5 carries a new defect (R-1)**

**G5, slot.** `CombatState.cs:417-421` adds `creature.Monster` immediately after
`list.AddRange(creature.Powers)` (`:416`) and before the loop advances to the
next creature. `_derive` does exactly that (`hooks.py:370-376`), and I confirmed
by execution that a Thorns-carrying enemy yields `… , ThornsPower, <enemy>` as
the last two entries of the walk. `MonsterModel.cs:51`
`ShouldReceiveCombatHooks => true` is real, though note it is **dead in this
build** — `grep -rn ShouldReceiveCombatHooks src/` returns declarations only,
zero readers. It is fine as corroboration; the load-bearing citation is `:420`.

**G5, shims.** Both are gone. `_AeonglassWitherListener` → `Aeonglass.
on_card_generated_for_combat` (body unchanged; `Aeonglass.cs:150-166`) and
`_AmalgamDeathListener` → `Queen.on_death` (body unchanged; `Queen.cs:221-234`).
Positionally identical: the shims declared `hook_category = CAT_POWER + 1`,
which under the old numbering was `CAT_RELIC` and, for an enemy owner with no
relics, sorted immediately after that creature's powers — i.e. the same slot the
real `CAT_MONSTER` now occupies. `test_glory.py` +
`test_task8_aeonglass_generated_wither.py` pass (I ran them; 260 passed across
the ten relevant files).

**G5, the collision census — re-executed by me, not inherited.** This was the
one thing that could have turned G5 into a silent mass behaviour change. I
extracted the 94 hook names from `_each("…")` call sites in `hooks.py`, crossed
them with all four `_PHASES` suffixes (376 names), and intersected against
`vars()` of every class in the MRO of all **113** `Monster` subclasses plus
`Monster` itself:

```
COLLISION: Aeonglass.on_card_generated_for_combat   (intended)
COLLISION: Queen.on_death                           (intended)
total unintended collisions: 0
```

Also confirmed there is **no `__getattr__` anywhere in `sts2_rl/`** (so no class
can accidentally answer every hook name) and **no `__eq__`/`__hash__` on any
listener class** (so `_listeners.remove` / `in` are identity-based, which
`register`/`unregister`'s new counters depend on). The census is sound.

**G6.** Machinery is right and the dormancy verdict is **re-executed, not
inherited**. My own runs:

* sim side: 7 `Affliction` subclasses (`Ringing, Entangled, Smog, Tainted,
  Galvanized, Hexed, Bound`), members are `id`/`name`/`is_stackable`/
  `can_afflict_card_type` only — **zero hooks**;
* game side: `grep -rn "public override" src/Core/Models/Afflictions/*.cs`
  yields exactly one AbstractModel hook, `Hexed.cs:17 AfterCardEnteredCombat`,
  and `HexedAffliction` in the sim is a data-only stub.

The `HasCard` seam fix is correct and well-motivated: `CardModel.
ClearAfflictionInternal` (`CardModel.cs:1532-1542`) calls
`AfflictionModel.ClearInternal` (`:253-257`), which nulls `_card`, *then* nulls
the card's `Affliction`; `HasCard` is `_card != null` (`:90`) and is the first
leg of `:591`. Without the back-reference null, a cleared affliction would have
kept passing `Contains`. Registration is wired at all three acquisition sites
(`CardCmd.afflict`, `CardPileCmd._enter_combat` for an already-afflicted clone,
`CombatState.__init__` for a deck card afflicted out of combat) and the
`hooks is None` guard on the out-of-combat path is correct.

### R-1 — the dying monster loses its own `AfterDeath` (NEW, mine — the headline)

C# order in `CreatureCmd.KillWithoutCheckingWinCondition`:

```
:508  shouldRemoveFromCombat = Hook.ShouldCreatureBeRemovedFromCombatAfterDeath(...)   // computed
:519  await Hook.AfterDeath(runState, combatState, creature, wasRemovalPrevented:false, ...)
:525  CombatManager.Instance.RemoveCreature(creature)
:529  combatState.RemoveCreature(creature)        // -> CombatState.cs:299-302 nulls Creature.CombatState
```

So at `:519` the dying creature's `CombatState` is **still non-null**, its
`MonsterModel` passes `Contains` (`:585` tests nothing else), and **the monster
receives its own AfterDeath**. Removal happens two statements later.

The sim inverts that. `cmds.py:159-162`:

```python
target.retained_after_death = (not hooks.should_remove_from_combat_after_death(target))
hooks.on_death(target, False)
```

and `Creature.is_removed_from_combat` is `is_gone and not retained_after_death`.
For an ordinary (non-retained) death the flag is `False` *before* the dispatch,
so `is_removed_from_combat` is already `True` and the new
`Monster.hook_contains()` refuses. Executed:

```
monster in _ordered before death: True
retained_after_death: False | is_removed_from_combat: True
dying monster's own on_death delivered: []
```

The same inversion also excludes the dying monster from the `should_die` and
`should_remove_from_combat_after_death` dispatches that run while it is at 0 HP,
where C# consults it (`:505`, `:508`, both before removal).

**Why this outranks the task's own findings.** Of the ten C# monster
`AfterDeath` overrides, **eight open with `if (creature != base.Creature)
return`** — Aeonglass, DecimillipedeSegment, LagavulinMatriarch, SoulFysh,
TestSubject, TheInsatiable, Vantom, WaterfallGiant — and **KinPriest has an
explicit `else if (creature == base.Creature)` arm** (`KinPriest.cs:104-107`).
KinPriest's AfterDeath is the entry's own recorded "concrete trigger" for G5.
So the very first content port G5 unblocks lands on a hook the new machinery
cannot deliver.

**Dormant today**, on two counts: the only sim monster implementing `on_death`
is `Queen`, whose body filters to `TorchHeadAmalgam` (a *different*, live
creature — that path works, and `test_glory.py` proves it); and all eight C#
self-arms are presentation-only (music parameters, textures, VFX). So this is
not a blocker for the fold. It **is** a defect in machinery R1 shipped, found
only by reading the C# control flow, and it must be queued.

Suggested fix (inside R1's own footprint, `cmds.py`): mirror C#'s statement
order — compute `should_remove` into a local at `:159`, dispatch
`hooks.on_death(target, False)`, and assign `target.retained_after_death` after
it. That is strictly more faithful in general, not only for this hook: during
`AfterDeath` C# has `Creature.CombatState != null`, so *every* predicate keyed
on `is_removed_from_combat` should read `False` for the duration of that
dispatch.

---

## E. THE PERFORMANCE CONTRACT — **PASS. Re-measured independently.**

Own throwaway benchmark (`bench_hooks.py` in the scratchpad): 25 combats × 10
`end_turn`s, 30-card deck, 3 relics, enemies and player pinned at 100k HP,
warmed, 5 samples per run, **three strictly interleaved HEAD/LIVE rounds** —
HEAD being a `git archive HEAD` export in its own interpreter, never a revert of
the live tree.

| scenario | HEAD global min | LIVE global min | Δ |
|---|---|---|---|
| plain 30-card deck | **0.1230 s** | **0.1231 s** | **+0.1 %** (noise) |
| 6 enchanted cards (forces the per-card walk) | **0.1335 s** | **0.1433 s** | **+7.3 %** |

Per-round medians: plain −3.3 % / +4.4 % / +1.2 %; enchanted +7.3 % / +3.2 % /
+14.3 % (the third round was visibly loaded). The min-based figure is the
noise-robust one. **Budget was ~15 %; the worst case is +7 %.** My enchanted
number is ~2 points above the report's +5.0 %, which is inside the spread the
report itself warns about; the RELATIVE conclusion — no measurable cost on the
ordinary path, single-digit on the worst case, no redesign needed — is confirmed.

All four structural requirements verified by reading the code AND by
instrumentation. My counters over the plain benchmark reproduce the report's to
the digit:

```
LIVE : _each 13,275 | _ordered 2,100 | _derive 2,100 | _merge_extras 0
HEAD : _each 13,275 | _ordered 3,075
```

1. **Gate above the derivation — YES.** `_each` (`hooks.py:651-654`) runs the
   `_COMBAT_GATED_HOOKS`/`combat_is_over` test, then `_has_listener_for`, and
   only then touches `_ordered()`. 2,100 builds for 13,275 calls = 84 % never
   build. (The docstring at `:625` says 92 % and the brief said 97.6 %; both are
   workload-dependent guesses. Cosmetic, but the docstring should carry the
   measured number or none.)
2. **`_phased` incremental — YES.** `register` unions (`:253`), `unregister`
   recomputes (`:271-273`), and the bare `self._ordered()` call `_each` used to
   make purely to refresh it is gone. The 3,075 → 2,100 drop is exactly that.
3. **Cache split — YES.** `_presence_cache` keys on `_epoch` alone
   (`:587-597`), and `_epoch` moves only in `register`/`unregister`. A pile move
   is a plain list mutation: it cannot touch `_epoch`, therefore cannot thrash
   the presence cache. Pinned by
   `test_a_pile_move_does_not_invalidate_the_presence_cache`, which asserts both
   `_epoch` and the whole `_presence_cache` dict are unchanged across a hand↔draw
   move while `_ordered()` reports the new order. No dirty flag was added to any
   of the 67 mutation sites, as instructed.
4. **Per-item re-check is attribute reads — YES.** One
   `getattr(l, "hook_contains", None)` + one call (`:669-671`, `:678-680`). No
   `isinstance` anywhere on the dispatch path.

The `_riders` fast/slow split is a legitimate optimisation and is correctly
maintained: `hook_is_card_rider` is a class attribute on `Affliction` and
`Enchantment` only, counted in `register`/`unregister`. I checked the failure
modes — an attached-but-unregistered rider is skipped by the fast path *and*
would have been dropped by `_live` anyway; a registered-but-detached rider forces
the slow path, lands in `_merge_extras`, and is then refused by its own
`hook_contains()`. Consistent either way.

The one accepted deviation: **`modify_shuffle_order` bypasses the presence
gate** and builds `_ordered()` on every shuffle. That is unchanged from HEAD
(which built a full sort of `_listeners` there), so it is not a regression.

---

## F. THE TESTS — **PASS, one naming defect**

**RED claim verified, and it is stronger than reported.** I exported HEAD with
`git archive HEAD | tar -x`, dropped the new file in, and ran it:

```
20 failed, 2 passed in 9.72s
```

The two passing are exactly the two the report names
(`test_the_four_piles_walk_in_allpiles_order`, which coincides with registration
order at combat start, and
`test_a_registered_listener_the_walk_cannot_reach_keeps_its_category_slot`,
honestly labelled a no-regression pin). The report claimed 18 of 20 at the time
it ran; with all 22 present, 20 fail. Honest and conservative.

Spot-checked the pins that matter, and they fail on HEAD for **behavioural**
reasons, not missing attributes:

| pin | HEAD failure |
|---|---|
| pile-move reordering | `assert [Strike, Defend] == [Defend, Strike]` |
| monster slot | `assert <FuzzyWurmCrawler> in [CombatHistory, Defend, …]` |
| state re-check drops a removed card mid-dispatch | `assert [Strike, Defend] == [Strike]` |
| state re-check drops a removed relic mid-dispatch | `assert [Pen Nib, Orichalcum] == [Pen Nib]` |
| IsActiveForHooks / F4 | `AttributeError: no attribute 'is_active_for_hooks'` (unavoidable) |

No test asserts nothing. No test is circular in the "sim vs sim" sense except
`test_a_registered_listener_the_walk_cannot_reach_keeps_its_category_slot`,
which pins a deliberately sim-only mechanism and says so in its docstring — that
is the right way to do it.

**Defect:** `test_an_affliction_whose_card_left_its_pile_is_not_derived` asserts
the **opposite of its name**. Its body asserts the card *and* its affliction are
still in `_ordered()` (seated by `_merge_extras`), i.e. it pins the sim's
divergence from C#, where a card outside `AllPiles` is not a listener at all
(`CombatState.cs:449-467`; `CardModel.cs:1045`). The docstring's first paragraph
states the C# rule and the body pins the sim's departure from it. Rename to
something like `…_is_seated_by_the_extras_merge_not_by_the_pile_walk` and say in
the docstring that this pins a known divergence. As written it will be read a
year from now as evidence that the sim matches C# here.

**Re-staged tests state the TRUE rule.** `test_hook_order.py`'s
`TestHookDispatchOrder` docstring (`:947-965`) now says the sim "DERIVES the walk
per dispatch from the live combat state … Order is a function of current pile
membership, potion-slot occupancy, relic order, `creature.powers` and the enemy
list — not of registration history", with `_listeners` reduced to membership +
an unreachable-listener tie-break. I checked that against the code: **true**,
and it even carries its own history (pre-round-8 → round-8-12 → now), which is
the right shape for a rule that has changed three times. `listener_categories()`
correctly gained the `affliction` and `monster` kinds and the expected walk
gained its `"monster"` tail. `test_task8_hook_presence_cache.py` really did need
no change (its bare objects exercise the `_undeclared` path) — 7 pass unmodified.

Full lane re-run in the live tree: `260 passed` across
`test_round13_listener_derivation.py`, `test_hook_order.py`,
`test_task8_hook_presence_cache.py`, `test_task8_aeonglass_generated_wither.py`,
`test_combat_over_hook_gate.py`, `test_task8_pile_move_and_generated_hooks.py`,
`test_discard_draw_order.py`, `test_glory.py`,
`test_combat_veto_and_dealer_event.py`, `test_turn_start_split.py`.

And the whole suite with the stale-listener probe, run by me on the live tree
with all concurrent lanes folded in:

```
py -m pytest test/ -q -p audit.tools.stale_listener_plugin \
    --ignore=test/test_conformance_floor_state.py
-> 3833 passed, 6 xfailed in 367s
   probe: 176,549 instrumented listener calls, 0 hits, 0 distinct pairs
```

(The report's 3,826 / 178,595 is the same result at an earlier fold point.) Zero
failures, and the probe's zero-hit result on both HEAD and the live tree is the
cleanest available evidence that the reordering is behaviour-preserving where it
should be — though, per F1 and the campaign's own binding history, a zero on a
probe that no ported listener can trip is evidence of nothing about the
mechanisms this lane touched. R-1 and R-2 are both invisible to it.

---

## G. F3 (`combat_is_over` vs `IsOverOrEnding`) — **REAL, and leaving it open was RIGHT**

Verified both sides:

* `Hook.IterateCombatHookListeners` (`Hook.cs:53-63`) gates on
  `CombatManager.Instance.IsOverOrEnding && !IsStarting`, and its own doc
  comment (`:32-51`) spells out why;
* `HookSystem.combat_is_over` (`hooks.py:515-555`) returns
  `phase == Phase.COMBAT_OVER`, i.e. only C#'s `!IsInProgress` half;
* `CombatState.is_over_or_ending` (`combat.py:1598-1618`) already exists and is
  the faithful `IsEnding || !IsInProgress`, with `is_ending` (`:1576-…`)
  carrying the pending-loss and all-primaries-dead-with-nothing-vetoing arms.

So on today's tree a dispatch that begins between the killing blow and the
teardown reaches listeners the game would not. Real, and it affects all 73 gated
dispatchers.

**Leaving it open was the right call, and there is a stronger reason than the
report gives.** `is_over_or_ending` reads `is_ending`, which calls
`_all_enemies_dead()` (`combat.py:442-452`), which **dispatches
`hooks.should_stop_combat_from_ending()`**. Wiring it into `_each`'s gate would
nest a hook dispatch inside the gate of every combat-gated dispatch. There is no
recursion hazard (`should_stop_combat_from_ending` is one of the ten deliberate
`IterateCombatHookListeners` bypasses, so it is ungated), but it needs a design
— a cached/short-circuited predicate — not a one-line swap. That belongs to a
`combat_is_over` owner, not to this lane, and the brief did not scope it.

Keeping `modify_shuffle_order` outside `_each` is likewise correct: it
open-codes `is_over_or_ending`, so routing it through `_each` would have
**weakened** an already-exact gate. The report says which and why, as the brief
demanded.

---

## H. PROTOCOL COMPLIANCE — **PASS**

* **No `audit/**` edits by this lane.** The only touched record is
  `audit/records/seam/hook_dispatch.json`, and its diff is a single appended
  guard entry authored by **R10** (`G-R10`, treasure-room `ModifyRewards`) —
  none of R1's proposed closes have been applied, so steps 3/4/6/9/12/16/44/45
  are all still `gap`. `audit/GAP-QUEUE.md` likewise carries no R1 text.
* **No git index mutation.** `HEAD` is still `c9bc337`; the lane's work is
  staged, which the controller did, not the implementer (the implementer is
  forbidden `git add` and there is no evidence of one).
* **Footprint respected.** `git diff HEAD --stat` over the declared footprint
  accounts for the entire lane: 11 engine files + 3 test files, 1,314 insertions
  / 199 deletions. `history.py` is untouched (correctly — it already declared
  `CAT_HISTORY` and needs no `hook_contains`). `powers.py`/`potions.py` were
  **not** touched (I verified neither grew a `hook_contains`), so the
  blocked-on-footprint handling is genuine and not a euphemism.
* Test discipline: the lane ran its own files and the covering files, reported
  exact commands and counts, and did not "fix" the known
  `test_conformance_floor_state.py` failures.

---

## Rulings on each claimed gap verdict

| claim | ruling |
|---|---|
| **G1 (steps 9, 44) FIXED** | **NARROWED, not FIXED.** Pile *sequence*, per-dispatch derivation, the card→affliction→enchantment triple and the Play seam are all exact and pinned. The **draw-pile leg walks in the sim's reversed orientation** (R-2) — `CardPile.cs:160-167` vs `player.py:581` — so a card's position within the draw pile is still wrong. Close steps 9 and 44 with the reversal named as the residue. |
| **G2 slot half (step 6) FIXED** | **CONFIRMED FIXED.** `CombatState.cs:436-443` indexes `PotionSlots`; `_derive` walks `player.potions` by index. Pin is RED on HEAD (I ran it). The record's own SETTLED analysis ("`_ordered()`'s sort key is `(rank, hook_category, i)`") is genuinely obsolete, and the dormancy argument (only `FairyInABottle` implements a potion hook) survives untouched. |
| **G5 (step 3) FIXED** | **FIXED for the slot and the shims; carries a NEW open entry (R-1).** `Monster` is a listener in `CombatState.cs:417-421`'s slot, the census is clean (I re-executed it: 0 unintended collisions over 113 classes × 376 names), both shims are gone with behaviour preserved. But `hook_contains` + `_resolve_death`'s premature `retained_after_death` assignment removes a dying monster from its own `AfterDeath`, where C# removes it at `:525-529`, two statements after `:519`. Close step 3, open a new entry for R-1. |
| **G6 FIXED (machinery), DORMANT (content)** | **CONFIRMED.** Machinery exact against `:458-461`/`:591`, the `HasCard` seam fix is right, and I re-executed both dormancy censuses myself rather than inheriting them (7 sim afflictions, 0 hooks; 1 of the C# affliction files overrides a hook, `Hexed.cs:17`). |
| **G7 NARROWED** | **CONFIRMED NARROWED, but the narrowing must also name R-3.** Power and Potion are correctly identified as the only *missing* arms. The two implemented arms whose first leg (`HasBeenRemovedFromState`) is never set in production are machinery-only and must be recorded as such, alongside `is_melted`. |

---

## Verdict on the record-close proposals (§6/§7)

Overall: **accurate, and they do state which reasoning they replace** — which is
the part this campaign keeps losing. Every one of them names the superseded
sentence, not just the superseded verdict, and several correctly demote a claim
from "dormancy argument" to "safety argument" rather than deleting it. The
controller can apply them nearly verbatim **with these amendments**:

* **step 9 / step 44 (G1):** change `faithful` → **narrowed**, and add: *"Residue:
  the draw-pile leg still walks the sim's own orientation (top at the END,
  `player.py:581`) where `CardPile` is top-first (`CardPile.cs:160-167`), so the
  order WITHIN the draw pile is reversed vs `CombatState.cs:452-455`. Hand,
  discard and exhaust match (both engines append at the end;
  `CardPileCmd.cs:259` defaults to `CardPilePosition.Bottom`)."* Also drop the
  "six hook-implementing card classes" figure — it is **nine**
  (Bolas, Clash, DrumOfBattle, Enthralled, HowlFromBeyond, Normality, Regret,
  Stomp, ThrummingHatchet), and `HowlFromBeyondCard.
  after_auto_post_play_phase_entered` is the one the old census missed.
* **step 3 (G5):** apply as written, and open a companion entry for **R-1**
  (dying monster excluded from its own AfterDeath; `CreatureCmd.cs:519` vs
  `:525-529`; trigger = KinPriest's `else if (creature == base.Creature)` arm,
  `KinPriest.cs:104-107`). Without it the close reads as "the KinPriest port is
  now pure content", which is exactly what it is not.
* **step 12 (G7):** apply, and add R-3: *"The `HasBeenRemovedFromState` leg of
  the Card (`:593`) and Relic (`:597`) arms is declared but never set in the sim
  — machinery-only, like `is_melted`. The live leg of both arms is
  `Owner.IsActiveForHooks`."*
* **step 4 / step 11 / step 45:** apply as written. The stale-evidence
  correction (F1) is the single most valuable bookkeeping item in the report and
  I reproduced its core: `_ordered()` on HEAD is 3,075 calls for 13,275 `_each`
  calls, exactly as reported, and the probe's `IntangiblePower ×10` hit is gone
  on HEAD, i.e. the record's dormancy evidence had been invalidated by the
  record's own step 11 three rounds ago. Step 45's "premise was triply stale"
  note is correct on all three counts.
* **step 6 (G2 slot):** apply as written. Accurate.
* **guard G6:** apply as written. Accurate.
* **guard G7:** apply as **NARROWED** with the R-3 amendment above.
* **step 16:** the LEFT-OPEN / re-scope-under-N5 proposal is right —
  `RunState.IterateHookListeners` (`RunState.cs:545-596`) applies
  `IsActiveForHooks` at `:550` and `:567` and the same lazy `Contains` at
  `:577-583`, and the sim has no run-level counterpart. Verified verbatim.
* **steps 41/43:** "stale prose, not wrong verdicts, freshen in one line" is the
  right call.
* **F2 (`run.py:1113-1116` `_map_listeners` is `[*relics, *deck]`):** verified
  and it is genuinely **live**, not dormant. `RunState.cs:548-562` adds every
  active player's deck cards (each followed by its Enchantment) FIRST and only
  then, and only when `childCombatState == null` (`:563-576`), relics and
  potions. The sim has map-hook implementers on **both** sides today —
  `cards/event_cards.py` and `cards/spoils_map.py` vs `relics/golden_compass.py`
  — so a run holding both really does dispatch in the wrong order. Queue it
  explicitly, as the report asks, rather than folding it into N5's dormancy.
* **§7 blocked diffs:** both are correct C# and correctly attributed to another
  lane's files. Land them.

New queue entries this review adds, in priority order: **R-1** (monster
self-AfterDeath), **R-2** (draw-pile orientation), **R-3**
(`has_been_removed_from_state` unset), plus the `player.py` contradictory
comment and the mis-named affliction test as fix-ups on this lane.

---

## Spec compliance

Every C# citation I checked resolves, at the cited line or within a line or two:
`CombatState.cs:410-493`, `:549-599` (all ten arms), `PlayerCombatState.cs:70-80`
(array at `:76`), `Player.cs:112/:272/:438/:857-860/:868-871` and the `:103-111`
doc comment, `Creature.cs:477-485`, `CreatureCmd.cs:505/:508/:519/:525-529/:553/
:558-570`, `CombatManager.cs:985-988`, `Hook.cs:53-63`, `CardModel.cs:948/:1228/
:1045/:1532-1542/:1604-1608/:1955-1990/:2070-2082`, `CardCmd.cs:114-116`,
`CardPile.cs:82-96/:142-167`, `CardPileCmd.cs:259`, `AfflictionModel.cs:90/:146/
:253-257`, `EnchantmentModel.cs:120/:154`, `MonsterModel.cs:51`,
`RelicModel.cs:420/:525/:531-534`, `PotionModel.cs:197/:202/:217/:221-224/
:229-233`, `RunState.cs:545-596/:715-731`, `KinPriest.cs:81-108`,
`Aeonglass.cs:150-166`, `Queen.cs:221-234`. Two are a line or two off
(`AfflictionModel.ClearInternal` is `:253-257` not `:249-254`;
`ClearAfflictionInternal` is `:1532-1542` not `:1532-1540`) — both cite the doc
comment's first line, which is the house style elsewhere in this repo. No
citation I checked was wrong about what the code does.

Two citations are decorative rather than load-bearing and should be labelled as
such: `AfflictionModel.cs:146` and `MonsterModel.cs:51`
(`ShouldReceiveCombatHooks`) have **zero readers anywhere in `src/`** in this
build. The real evidence that an affliction or a monster is a listener is
`CombatState.cs:458-461` and `:420`, which the report also cites.

**Spec-compliance verdict: PASS.**

## Code quality

Genuinely good, and unusually so for a change of this blast radius.
`_ordered`/`_derive`/`_merge_extras` is the right decomposition; the
`groups`/`excluded` protocol makes "the walk could not reach it" and "the walk
refused it" two separate, testable facts instead of one fudge; the fast/slow
split on `_riders` is measured rather than assumed; the docstrings explain *why*
each deviation exists and cite the C# for it; and the comment history embedded in
`test_hook_order.py`'s docstring is the right way to record a rule that has
changed three times. `_each`'s reordering of the `getattr` miss ahead of both
filter legs is correct and correctly argued (in C# every model implements every
hook as a virtual no-op, so filtering a non-implementor is unobservable) — and it
is the reason the plain-deck number did not move.

Defects, all minor except the first:

1. **`player.py`'s "single-player never reaches `ActivateHooks`" comment
   contradicts `combat.py:770-779` and `cmds.py:141-153`, added by the same
   lane.** Highest-value fix in this list: it is the comment that would get the
   reactivation deleted.
2. `has_been_removed_from_state` comments do not say the flag is never set,
   where the neighbouring `is_melted` comment does (R-3).
3. `combat.py:1029` repeats the stale "six hook-implementing card classes"
   census (it is nine).
4. `monsters/base.py:170-181` claims "there is no window in which a constructed
   monster is not in the combat", which the report's own F7 contradicts
   (`Encounter.create_monsters` builds monsters before `combat.enemies` exists;
   they land in `_merge_extras`' tail for those few dispatches). Harmless today —
   no monster implements a hook that fires during construction — but the comment
   and the finding should agree.
5. `test_an_affliction_whose_card_left_its_pile_is_not_derived` is named for the
   opposite of what it asserts.
6. `_each`'s docstring quotes "92 %" and `hooks.py:211-215` quotes "67 mutation
   sites"; the first measures 84 % on the benchmark workload. Cosmetic.

**Code-quality verdict: PASS.**

---

## What I verified that outranks the task's own findings

R-1. The lane's own G5 machinery drops a dying monster from its own
`Hook.AfterDeath`, and the record's named trigger for G5 — KinPriest — is
precisely a monster whose `AfterDeath` has a self-death arm. It took reading
`CreatureCmd.cs:505-553` statement by statement against
`cmds.py:154-183` to see it: the sim assigns the flag that
`Monster.hook_contains()` now reads one line *before* the dispatch that C# makes
one removal *before*. Every test in the suite passes with the divergence in
place, and would keep passing after any future KinPriest port. That is the
round-12 lesson a third time: the green suite is not the evidence.

---

# Re-review (2026-08-01)

Second pass, after the lane's fix pass (`R1-report.md` FP-0 through FP-9). My
perf verification and the four structural claims from the first pass are
unchanged and were not redone except where the fix pass touched the hot path
(RR-6). Everything here is re-derived from the C# and re-executed.

**Verdict: APPROVED.**

The headline: **the lane is right and I was wrong.** My proposed remedy for my
own R-1 would have fixed nothing, its diagnosis of *why* is correct, and its
replacement is a better port than the one I asked for. It also caught that the
`Power` diff I approved in section 7 would have shipped the same bug into
`powers.py` — a diff I had checked against the C# *arm* without checking the
*timing of the sim value it reads*. That correction is worth more than anything
in my first pass.

---

## RR-1. The R-1 adjudication — the lane's replacement is correct; my remedy was INERT

### (a) My remedy would have done nothing. Proved.

I exported the pre-fix-pass tree (`git checkout-index -a`, i.e. the index, which
is R1 before this pass), applied **only** my proposed change — compute
`should_remove` into a local, dispatch `on_death`, assign `retained_after_death`
afterwards — and ran the probe:

```
before death: in _ordered? True
at 0 HP, before _resolve_death: is_gone True | retained False
                                | is_removed_from_combat True | hook_contains False
WITH REVIEWER'S REMEDY -> own on_death delivered: []
```

`retained_after_death` **defaults to `False`**, so `is_gone and not
retained_after_death` is already `True` at the HP write, before `_resolve_death`
is entered at all. Moving the assignment later leaves the flag at its default
for the entire window. My remedy is inert. FP-0 is right, including its claim to
have proved it by execution — I reproduced the proof independently.

What I got right was the *defect* (C# removes at `:525-529`, two statements after
`Hook.AfterDeath` at `:519`) and its *consequence* (KinPriest). What I got wrong
was the sim's default, and therefore the fix. The lane's reframing —
**prediction vs event** — is the correct diagnosis and is strictly wider than
mine: the same window also swallows `Hook.ShouldDie` (`:505`) and
`Hook.ShouldCreatureBeRemovedFromCombatAfterDeath` (`:508`), which my write-up
mentioned only in passing and which my remedy would not have touched either.

### (b) The new predicate fires at exactly C#'s removal points and nowhere else

`Creature.CombatState` is nulled only by `CombatState.RemoveCreature`
(`CombatState.cs:277-304`; the null is at `:300-302` under `unattach: true`,
which is the parameter default). I enumerated **every** caller in the tree:

| C# call site | in-fight? | sim mirror |
|---|---|---|
| `CreatureCmd.cs:529` (death, under the `:523` and `:527` gates) | yes | `cmds.py:185` in `_resolve_death` |
| `CreatureCmd.cs:601` -> `CombatState.CreatureEscaped` (`:266-270`) -> `RemoveCreature`, unconditional | yes | `cmds.py:778` in `CreatureCmd.escape` |
| `MonsterModel.cs:450` (`PerformMove`'s tail, `:447-451`) | yes | `combat.py:587` in `CombatState._perform_move`'s `finally` |
| `CombatManager.cs:909` | no — `EndCombat`'s graceful teardown loop | n/a |
| `CombatRoom.cs:152` | no — combat-end teardown | n/a |
| `EventModel.cs:417` | no — the event card-layout preview state | n/a |
| `MockCombatCleanupOrb.cs:24` | no — mock | n/a |

Three in-fight statements, three sim assignments, and `grep -rn
combat_removal_committed sts2_rl/` finds exactly those three writes plus the
declaration and the single read. **1:1, nothing else.** The C# gates verified
verbatim: `:523` `shouldRemoveFromCombat && Side == Enemy && Enemies.Contains`,
`:527` `monster != null && !monster.IsPerformingMove`, and
`MonsterModel.cs:440`/`:447` raising and dropping `IsPerformingMove` around the
move with the deferred removal at `:448-451`. All three are mirrored, and
`_resolve_death` correctly tests the **dying creature's own**
`is_performing_move`, as `:527` does (`creature.Monster`), not the mover's.

`combat.py:583` is the only `take_turn(` call site in the whole package, so
`_perform_move` is a complete funnel — no monster-action path bypasses the
`IsPerformingMove` window.

### (c) Behaviour, all eight cases, executed

```
1-3 dying monster consulted by its own should_die / should_remove / on_death:
       {'should_die': [True], 'should_remove': [True], 'on_death': [True]}
    after the sequence: committed=True  hook_contains=False   (still in _ordered,
                                                               refused by Contains)
4 death-vetoed corpse:  committed=False  retained=True   hook_contains=True
5 retained corpse:      committed=False  retained=True   hook_contains=True
   ...and still False after it takes another turn (the withered-segment case)
6 escaped monster:      committed=True                   hook_contains=False
7 died mid-move:        committed=False  hook_contains=True  is_performing_move=True
                        -> after the move returns: committed=True
8 player after death:   no combat_removal_committed attribute at all;
                        is_active_for_hooks=False
```

Every one matches the C#. Cases 4 and 5 are the ones that would have been easy
to break — a corpse the `:523-531` block never ran for stays a listener, which
is exactly `Contains`' `:585` testing the back-pointer and nothing else — and
case 5 also covers the withered-Decimillipede-segment shape, where
`MonsterModel.cs:449` re-asks the same hook and also declines. Case 8 confirms
the player path is untouched and still runs through `DeactivateHooks`, as
`Player.cs:103-111` requires.

`Creature.is_removed_from_combat` is untouched, so the blast radius really is
one predicate.

**One imprecision, disclosed rather than hidden:** `_perform_move`'s deferred
completion reads the cached `retained_after_death` where `MonsterModel.cs:449`
**re-dispatches** `Hook.ShouldCreatureBeRemovedFromCombatAfterDeath`. A listener
that changed its answer between the death and the end of the move would diverge.
The code comment says exactly this; it is worth one line in the queue
annotation.

**RR-1 verdict: the lane's `combat_removal_committed` is correct; my
`retained_after_death` reordering was wrong. G5 closes FIXED with no companion
entry, as FP-6 asks.**

---

## RR-2. G1 / R-2 — FIXED, and the citation I lacked is real

`CardPileCmd.cs:843` verified verbatim, inside the draw loop:

```csharp
CardModel card = drawPile.Cards.FirstOrDefault();
```

A draw takes index 0, so index 0 **is** the top and `CombatState.cs:452-455`
enumerates the draw pile top to bottom. That is decisive where my
`MoveToTopInternal`-based inference was only strong; the lane found the better
citation.

Executed against the live tree, one card per position in each of the four piles:

```
derived walk: ['hand-first', 'hand-second',        # append order, both engines
               'draw-top', 'draw-bottom',          # REVERSED vs sim storage
               'discard-first', 'discard-second',
               'exhaust-first', 'exhaust-second']
matches C# AllPiles top-first enumeration: True
```

with the draw pile's top independently confirmed as the card the sim draws next.
Hand, discard and exhaust are append-at-end in both engines (`CardPile.
AddInternal`'s default `index = -1` -> `_cards.Add`; `CardPileCmd.cs:259`'s
default `CardPilePosition.Bottom`), so leaving those three unflipped is right.
Storage orientation is unchanged — only the walk — which is the minimal
intervention.

**G1 closes FIXED. My NARROWED ruling is withdrawn; it was explicitly
conditional on the reversal being left in place, and it is not.**

---

## RR-3. G7 / R-3 — the narrowing is honest and both wired sites are the right ones

C# sites re-checked by locating the enclosing method, not just the line:

* `CardPileCmd.cs:189` `oldCard.RemoveFromState()` is inside
  **`RemoveFromCombat(IEnumerable<CardModel>)`** (`:102`), and the single-card
  overload at `:90` delegates to it — so the played-Power-card mapping is right;
* `CardPileCmd.cs:79` `card.RemoveFromState()` is inside
  **`RemoveFromDeck(IReadOnlyList<CardModel>)`** (`:52`) — so "deck removal, sim
  counterpart `RunState.remove_cards` in `run.py`" is right, and `run.py` is
  genuinely outside the footprint;
* `CardCmd.cs:506` is the transform tail, in the results loop after
  `Hook.AfterCardGeneratedForCombat`;
* `CardModel.cs:1228` is inside **`AfterCloned`** (`:1218`), confirming
  `reset_combat_state` as the right clear site — and `grep` shows
  `reset_combat_state()` is called from exactly one place, `combat.py:198`
  (combat setup), which is precisely the per-combat-clone semantics.

Executed:

```
power card after play:      removed_from_state=True   registered=False  hook_contains=False
after next combat setup:    removed_from_state=False  in _ordered=True     <- clear works
transform original:         removed_from_state=True   registered=False
ordinary card after play:   removed_from_state=False  in _ordered=True     <- no over-reach
```

The clear really is load-bearing: without it a Power card played once would
never listen again in any later combat.

The Relic side is now honestly labelled machinery-only with all five removal
sites enumerated in the comment, matching `is_melted`'s existing honesty. I
spot-checked the enumeration: there is no `RelicCmd.Remove` in the package.

**G7 stays NARROWED, now for three named reasons instead of one. Correct.**

Nit, unobservable: the sim sets the transform flag *before*
`_enter_combat(replacement)` where C# sets it *after*
`Hook.AfterCardGeneratedForCombat`. The original is already unregistered at that
point, so `_each` drops it either way.

---

## RR-4. The contradictory `player.py` comment — now true

Re-read (`player.py:89-112`). It states that single-player *does* reach
`ActivateHooks`, names the chain (`Creature.HealInternal`, `Creature.cs:477-485`
-> `Player.ReviveBeforeCombatEnd`, `Player.cs:821-827` <- `CombatManager.cs:986`,
one statement before `Hook.AfterCombatEnd` at `:988`), quotes `Player.cs:813-819`
on why the order matters, flags C#'s own "likely only called in multiplayer" as
a doc-comment guess, lists the seven victory call sites that bypass
`_has_pending_loss`, records the executed 80->80 / 80->81 evidence, ends with
"do not delete the two lines that do", and names the pin. Every clause checks
out against the C# and against `grep`. This is now the strongest comment in the
lane.

## RR-5. Review defects 3-6 — all applied

* **3** — `combat.py`'s census is now **nine**, with the same list I derived
  independently (Bolas, Clash, Drum of Battle, Enthralled, Howl from Beyond,
  Normality, Regret, Stomp, Thrumming Hatchet), and it names the re-run.
* **4** — `monsters/base.py` now names the F7 window
  (`Encounter.create_monsters` builds the roster before `CombatState.enemies` is
  assigned) instead of denying it.
* **5** — renamed to
  `test_an_affliction_whose_card_left_its_pile_is_seated_by_the_extras_merge`,
  and the docstring now opens **"PINS A KNOWN DIVERGENCE, not the C# rule"** and
  cites `CardModel.cs:1045`. Exactly what was needed.
* **6** — "92%" replaced by the measured 84% (2,100 of 13,275) with the workload
  named and flagged workload-dependent.
* **decorative citations** — `AfflictionModel.cs:146` and `MonsterModel.cs:51`
  are now labelled corroboration-with-zero-readers, with the load-bearing
  citation named alongside in both places.

## RR-6. Tests and perf after the fix pass

New pins re-verified RED on the pre-fix-pass tree (the index export, with only
the new test file copied in): **11 failed / 20 passed** — one more than the
report's 10, because `test_a_card_that_changes_pile_changes_its_dispatch_position`
was rewritten for the new orientation and is also RED. The headline ones fail
behaviourally, not on a missing attribute:

```
test_a_dying_monster_receives_its_own_after_death
    assert [] == [(<FuzzyWurmCrawler>, False)]
test_a_dying_monster_is_consulted_by_its_own_should_die
    assert [] == [<FuzzyWurmCrawler>]
test_the_draw_pile_walks_top_first
    assert [Strike, Defend] == [Defend, Strike]
test_a_played_power_card_is_flagged_removed_from_state
    assert False is True where False = Inflame.has_been_removed_from_state
test_combat_setup_clears_the_removed_from_state_flag
    assert True is False where True = Inflame.has_been_removed_from_state
```

`test_a_dying_monster_receives_its_own_after_death` is a good pin specifically
because it asserts the tuple `(enemy, False)` — it pins both that the hook was
delivered *and* that the removal had not yet been committed when it was.

Green on the live tree: `test_round13_listener_derivation.py` **31 passed**; the
lane plus its blast radius (16 files including `test_can_receive_powers.py`,
`test_exhaust_escape_removal.py`, `test_hive.py`,
`test_state_machine_construction.py`, `test_is_dead_early_returns.py`) **406
passed**. Full suite with the stale-listener probe:

```
py -m pytest test/ -q -p audit.tools.stale_listener_plugin \
    --ignore=test/test_conformance_floor_state.py
-> 1 failed, 3864 passed, 6 xfailed in 326s
```

The single failure is
`test/test_r13_relic2.py::test_paper_phrog_n2_brand_self_damage_is_not_a_powered_attack`
— an untracked file belonging to **R8** ("Round 13 (R8) — settling the
`relic-2` unlabelled batch"), failing on `AttributeError: 'function' object has
no attribute '__func__'`, a test-authoring bug in that lane. Not R1's; R1 touched
neither the file nor the relic. (An earlier transient failure in
`test_monster_tier_families.py` — a line-number census of another lane's
`monsters/overgrowth/vantom.py` — has since gone green as that lane settled.)

**Perf, re-measured, three-way controlled** (the coordinator is right that the
first pass's numbers stand; I redid it only because the fix pass touched
`_derive`'s hot loop). Global minima over two interleaved rounds of 5 samples:

| scenario | HEAD | R1 pre-fix-pass | R1 post-fix |
|---|---|---|---|
| plain 30-card deck | 0.1120 s | 0.1065 s | 0.1117 s (**-0.3 % vs HEAD**) |
| 6 enchanted cards | 0.1213 s | 0.1321 s | 0.1316 s (**+8.5 % vs HEAD, -0.4 % vs pre-fix**) |

plus an isolated control — the live tree with **only** `reversed(...)` removed
from `_derive`, three interleaved rounds:

```
no-reversal  global min 0.1112     LIVE  global min 0.1108     ->  -0.4 %
```

So the draw-pile flip costs **nothing measurable** on `end_turn`, corroborating
the lane's +0.185 microseconds/derivation micro-figure (0.185 us x 2,100
derivations is about 0.39 ms on a ~110 ms run, about 0.35 %, below noise). The
fix pass adds no cost; the overall R1 delta is unchanged at about 0 % plain and
+7-8.5 % enchanted against a ~15 % budget. (An uncontrolled HEAD-vs-live reading
earlier in this session showed +5.2 %/+12.1 %; the three-way above localises that
to other lanes' newly unstaged work and to machine load, not to R1.)

**Protocol, re-checked for the fix pass:** engine edits confined to `hooks.py`,
`combat.py`, `cmds.py`, `player.py`, `cards/base.py`, `relics/base.py`,
`monsters/base.py`, `afflictions.py`; the only test file touched is
`test_round13_listener_derivation.py`; the unstaged `audit/` changes are R6's and
R10's; `test_is_dead_early_returns.py` is R11's ("round 13 R11 item 1"); no git
index command. Clean.

---

## RR-7. RULING ON THE TWO SECTION-7 DIFFS (the controller lands these; a wrong one is permanent)

### `sts2_rl/powers.py` — REJECT the section-7 diff. LAND the FP-6 diff.

I installed each candidate into its own scratch copy of the live tree and asked
the only question that separates them: does a power still listen during its
**own owner's** `AfterDeath`?

```
[old  S7 : return not owner.is_removed_from_combat]
        power received its OWN owner's AfterDeath: []          <- the R-1 bug
[new FP-6: return not getattr(owner, "combat_removal_committed", False)]
        power received its OWN owner's AfterDeath: [True]
        ...and after the sequence: hook_contains = False       <- correctly excluded
```

C# says `[True]`: `Hook.AfterDeath` at `CreatureCmd.cs:519` runs while the
back-pointer is still set (nulled at `:529`) **and** while the power is still
attached (stripped at `:533-537`). The section-7 diff I approved reads the eager
prediction and drops it. The lane's warning is exactly right, and its
observation about *why* I missed it is the important part: I checked the diff
against the C# **arm** and not against the **timing of the sim value it reads**.

The FP-6 diff is correct on both legs — monster: the removal event; player:
`is_active_for_hooks` alone, because `Owner.CombatState != null` is invariantly
true for a player in combat (`:523` gates on `Side == Enemy`, and
`Player.cs:103-111` states the design intent). The `getattr(..., False)` default
is a safe fallback for any owner without the attribute.

### `sts2_rl/potions.py` — LAND unchanged, exactly as printed in section 7.

The PotionModel arm (`CombatState.cs:595`) is
`!HasBeenRemovedFromState && Owner.IsActiveForHooks` — it has **no
`CombatState` leg at all**, so the prediction-vs-event trap cannot apply.
`PotionModel.cs:202` / `:221-224` (`Discard`) / `:229-233` (`RemoveBeforeUse`)
confirm the flag's carriers, and I verified that `Potion` instances really do
carry a `.combat` back-reference (`type(pot.combat).__name__ == 'CombatState'`),
so the diff lands without an AttributeError. Correct as written.

### `sts2_rl/run.py` (new, from FP-6) — LAND.

`RunState.remove_cards` setting `card.has_been_removed_from_state = True` after
`before_card_removed` mirrors `CardPileCmd.cs:79` (inside
`RemoveFromDeck(IReadOnlyList<CardModel>)`, verified). Dormant, one line,
completes the Card arm.

---

## RR-8. The deferred gap (`can_receive_powers`, `_combat_contains_creature`)

**Deferring is right. The description is nearly filable, but its stated REASON
is half wrong and the controller must not file it as written.**

The gap is real and I verified both C# counterparts:
`Creature.CanReceivePowers` (`Creature.cs:308-322`) opens `if (CombatState ==
null) return false` — the *event*; `ICombatState.ContainsCreature`
(`CombatState.cs:306-313`) is physical list membership, which survives until
`RemoveCreature`. Both sim consumers AND in the eager prediction. Demonstrated
live at the machinery level, from inside the dying monster's own `AfterDeath`:

```
can_receive_powers_during_AfterDeath   = False    (C#: True)
contains_creature_during_AfterDeath    = False    (C#: True)
power_landed                           = False    (C#: it lands)
```

**Two corrections for the controller before filing:**

1. **It is NOT blocked on footprint.** The queue text says *"`creatures.py` is
   outside R1's footprint and changing the property would have live blast
   radius"*. The first clause is a non-reason: both consumers live in `cmds.py`,
   which **is** in the footprint, and fixing them needs no `creatures.py` edit at
   all — `getattr(target, "combat_removal_committed", False)` at those two call
   sites is the same technique the lane just used for `Monster.hook_contains`.
   The honest reason is the second clause alone: it is a live behaviour change on
   `PowerCmd.apply`'s gate, the hottest state-mutating path, in a wave with other
   lanes live in the tree, and it is outside the brief's four clusters. File it
   on that reason; otherwise a future round reads "blocked on footprint",
   believes it, and skips it again.
2. **Add the dormancy statement, which the entry lacks.** I enumerated every
   death-hook handler in the package that applies or removes a power — there are
   four. `RavenousPower` (`powers.py:2017`) and `CrabRagePower` (`:3084`) both
   `return` when `creature is self.owner` and target a live teammate;
   `SurprisePower` (`:2149`) targets a newly-summoned gremlin; `_PossessPower`
   (`:3862`) targets the player, who is not in a death sequence. **None targets a
   creature that is mid-death-sequence, so the gap is machinery-live but
   content-dormant today** — and `SurprisePower` / `_PossessPower` show that the
   pattern (a power reacting to its own owner's death and mutating combat state)
   is already one content port away.

Give it a home: it belongs with the `is_removed_from_combat` property, i.e. the
`creature_cmds` / `power_cmd` family, not `hook_dispatch`.

---

## RR-9. Final rulings

| item | first pass | after the fix pass |
|---|---|---|
| **G1** (steps 9, 44) | NARROWED (draw-pile reversal) | **FIXED** — reversal closed; `CardPileCmd.cs:843` verified; all four piles verified by execution; cost nil |
| **G2 slot** (step 6) | FIXED | **FIXED**, undisturbed |
| **G5** (step 3) | FIXED plus a new open entry (R-1) | **FIXED, no companion entry** — R-1 closed by `combat_removal_committed`; 8/8 behavioural cases correct; 3 write sites map 1:1 onto 3 C# statements |
| **G6** (guard G6) | FIXED machinery / DORMANT content | unchanged |
| **G7** (steps 4, 11, 12, 45; guard G7) | NARROWED | **NARROWED**, now for three named reasons; Card flag wired at 2 of 3 sites plus the clear, verified by execution |
| **section-7 `Power` diff** | approved (WRONG) | **REJECTED — land FP-6's instead** |
| **section-7 `Potion` diff** | approved | **approved, unchanged** |
| **F3 / step 16 / steps 41-43** | LEFT-OPEN, correct | unchanged |
| **`is_removed_from_combat` prediction** | — | queue it, with the two corrections in RR-8 |

Record-close proposals: apply **FP-6** wherever it differs from sections 6 and 7.
Its close notes state which reasoning they replace, and the step-12 demotion from
`faithful` to NARROWED is the lane correcting itself against its own earlier
proposal — which is the behaviour this campaign wants.
