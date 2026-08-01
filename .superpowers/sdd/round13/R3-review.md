# R3 review — batch `power-1` (12 unlabelled entries, 10 records)

Reviewer: independent re-derivation from the decompiled C# and the current
tree. I read the lane's whole delta (`sts2_rl/powers.py` — 3 hunks:
`DarkEmbracePower`, `ReboundPower`, `RetainHandPower`; new
`test/test_r13_power1.py`; edited `test/test_underdocks_hive_events.py`) and
ignored every other modified path (`hooks.py`, `combat.py`, `cmds.py`,
`player.py`, `relics/**`, `rewards.py`, `driver.py`, `run.py`,
`.superpowers/**`, `audit/tools/**`) as other lanes' work.

**Verdict: NEEDS-FIXES.** Four of the five FIXED entries are correct and
well-pinned. One shipped fix (Rebound's stack tick) carries a live,
in-footprint divergence the tests cannot see, and the reasoning attached to
two entries (`corruption`, `vital_spark`) is wrong on the C#. The record
overturn on `power/rebound` **STANDS** and is the best work in this batch.

---

## 0. Executive summary of what changes

| # | Entry | Report verdict | Review ruling |
|---|---|---|---|
| 1 | `power/artifact/AfterModifyingPowerAmountReceived` | STALE-ALREADY-FIXED | **CONFIRM** |
| 2 | `power/corruption/ModifyCardPlayResultPileTypeAndPosition` | LIVE / BLOCKED-ON-FOOTPRINT | **CONFIRM verdict, OVERTURN reasoning** — the report's stated divergence is not a divergence |
| 3 | `power/dark_embrace/AfterCardExhausted` | FIXED | **CONFIRM** |
| 4 | `power/dark_embrace/AfterSideTurnEnd` | FIXED | **CONFIRM** (one RED-before claim is false; one dormant residual noted) |
| 5 | `power/draw_cards_next_turn/AfterSideTurnStart` | STALE-ALREADY-FIXED | **CONFIRM** |
| 6 | `power/nostalgia/g8` | NARROWED | **CONFIRM the Rebound half; OVERTURN the Corruption half's rationale** (inherits #2) |
| 7 | `power/rebound/ModifyCardPlayResultPileTypeAndPosition` | FIXED | **CONFIRM the move; NEEDS-FIX on the guard** |
| 8 | `power/rebound/AfterModifyingCardPlayResultPileOrPosition` | FIXED | **NEEDS-FIX** — the tick's gate is not the C# gate |
| 9 | `power/retain_hand/AfterSideTurnEnd` | FIXED | **CONFIRM** |
| 10 | `power/steam_eruption/g4` | DORMANT-ENUMERATED | **CONFIRM** |
| 11 | `power/the_bomb/InstanceType` | LIVE, no in-footprint fix | **CONFIRM** |
| 12 | `power/vital_spark/BeforeCombatStart` | DORMANT-ENUMERATED | **CONFIRM verdict, OVERTURN reasoning** — the record's C# claim is false and the report repeats it |

Record overturn on `power/rebound`'s guard "Rebound redirects the Rebound
card itself": **UPHELD** (section 2).

---

## 1. Per-entry rulings

### 1 — `power/artifact/AfterModifyingPowerAmountReceived` : CONFIRM (stale)

C#: `ArtifactPower.cs:38-41` — `AfterModifyingPowerAmountReceived(PowerModel
power) => await PowerCmd.Decrement(this)`, i.e. it decrements **itself** and
ignores the argument.

Sim today (read, not remembered): `ArtifactPower.after_modify_power_amount_received`
(`sts2_rl/powers.py:571-575`) calls `self._tick()`; `Power._tick`
(`powers.py:144-151`) routes through `PowerCmd.modify_amount`
(`cmds.py:1014+`), which carries the `IsEnding` guard and the
`ShouldRemoveDueToAmount` expiry. The dispatch really exists and really fires:
`hooks.after_modify_power_amount_received(received_modifiers, power)` at
`cmds.py:922` and `cmds.py:1011`, with the hook-name map entry at
`hooks.py:112` and the dispatcher at `hooks.py:1012-1030`. The record's
"hand-inlined" description is genuinely stale (round-12 Task 18).

One nuance the report omitted but which does not change the verdict:
`modify_amount` deliberately does **not** re-run the Given/Received chains on
the decrement path, and `cmds.py`'s own comment argues that is harmless for
both real listeners. That is `power_cmd` G3/G4's territory, correctly not
re-argued. **CONFIRM `faithful`.**

### 2 — `power/corruption/…` : CONFIRM verdict, OVERTURN the reasoning

The report's central claim is:

> "**Corruption therefore always wins over Nostalgia regardless of which power
> was applied first** — the opposite of C#'s single … chain with
> last-writer-wins … where the winner would depend on listener order.
> Order-independence is itself the divergence."

**That is wrong.** Re-derive from the two C# listeners:

- `CorruptionPower.cs:27-38` returns `(PileType.Exhaust, position)` for any
  owner-owned Skill **with no `pileType` guard at all**.
- `NostalgiaPower.cs:16-47` and `ReboundPower.cs:19-30` both bail with
  `if (pileType != PileType.Discard) return (pileType, position);`.

So in C#, for either listener order:
- Corruption first → Exhaust; Nostalgia/Rebound then see `!= Discard` → abstain → **Exhaust**.
- Nostalgia first → Draw/Top; Corruption then overwrites unconditionally → **Exhaust**.

C# is **also** order-independent here, and Corruption also always wins. The
sim's executed result (`exhausted=True` in both orders — I reproduced it
myself, plus the Rebound pairing) therefore **matches the game on the final
pile**. The report elevated a correct behaviour into the headline divergence.

The entry is still **LIVE**, on three residues the report never names:

1. **Rebound's stack under Corruption is unconditionally consumed.** Executed
   both orders: `corruption+rebound (corr first)` and `(reb first)` both end
   with the Rebound power gone. In C# the tick comes from
   `AfterModifyingCardPlayResultPileOrPosition`, fired only over the listeners
   that *changed* the value (`Hook.cs:1391-1406`), so if Corruption is ordered
   first Rebound sees `Exhaust`, abstains, is **not** a modifier, and keeps its
   stack. Order-dependent in C#, unconditional in the sim.
2. **Exhaust timing.** `CorruptionPower.on_card_played` (`powers.py:888-899`)
   runs inside the play-count loop (`combat.py:996`, inside
   `for play_index in range(play_count)`), where C# performs the exhaust once
   after the loop (`CardModel.cs:1976-1990`, `case PileType.Exhaust` at
   `:1984`). For a replayed Skill (Burst/Hidden Gem) the sim's card sits in the
   exhaust pile for the remaining iterations where the game keeps it in
   `PileType.Play` limbo, and `on_card_exhausted` (Feel No Pain, Dark Embrace,
   Charon's Ashes) fires mid-loop instead of after it.
3. Corruption is absent from the chain entirely, so the `modifiers`
   notification set differs (cosmetic `Flash()` only today).

**BLOCKED-ON-FOOTPRINT is correct** and the proposed fix shape (teach
`modify_card_play_result_pile` an `"exhaust"` destination; branch on it in
`combat.py`'s post-loop move; delete `CorruptionPower.on_card_played`) is
sound — it is the only way to get residues 1–3 at once. **But the handoff text
must be rewritten**: telling the next lane that "a faithful port would let
application order decide" the *winner* would send them to build the wrong
thing. Application order decides only *whether Rebound is credited with a
change*, never the winner.

### 3 — `power/dark_embrace/AfterCardExhausted` : CONFIRM

`DarkEmbracePower.cs:37-50`: `if (card.Owner.Creature == base.Owner)` then
`causedByEthereal ? etherealCount++ : await CardPileCmd.Draw(ctx, base.Amount,
…)`. The sim now draws `self.amount`. Correct.

RED-before verified by reconstruction (I rebuilt the pre-fix class in a
scratch script rather than reverting the tree, per protocol):
`test_draws_amount_cards_per_exhaust_not_a_hardcoded_one` **RED**,
`test_ethereal_exhaust_does_not_draw_immediately` **RED**.

`DarkEmbracePower` is one of only four AfterCardExhausted implementers that
read `causedByEthereal` at all (`DrumOfBattle.cs:31`, `DarkEmbracePower.cs:37`,
`BurningSticks.cs:44`, `JossPaper.cs:102`; `FeelNoPainPower.cs:19`,
`CharonsAshes.cs:17`, `ForgottenSoul.cs:18` take `bool _`), so restricting the
new branch to this class is right.

### 4 — `power/dark_embrace/AfterSideTurnEnd` : CONFIRM (with two notes)

Slot is right. `Hook.AfterTurnEnd` for the **player** side is
`CombatManager.cs:1307`, inside `EndPlayerTurnPhaseTwoInternal`, strictly after
the `FlushPlayerHand` loop (`:1289-1300`). The sim's `after_player_turn_end`
fires at `combat.py:1484`, after `_process_turn_end_cards()` (`:1464` — the
two `caused_by_ethereal=True` sites are `combat.py:793` and `:814`) and after
`discard_hand(flush=…)` (`:1481`). That is exactly the ordering
`DarkEmbracePower.cs:18-23`'s source comment exists for.
`test_ethereal_exhaust_draw_survives_the_hand_flush` **RED** pre-fix (`hand=0`
— the drawn card really was flushed away). Good pin; it is the one that
matters.

**Note 4a — a false RED claim.** The report says "All three RED before the
fix". `test_ethereal_exhaust_draw_is_deferred_to_after_player_turn_end`
**passed** against the reconstructed pre-fix class: with `amount=1` and three
ethereal exhausts, the old code drew 1×3 immediately and the new code draws
1×3 at turn end — the same draw-pile delta. It is a legitimate documentation
test but it is not a pin, and the report should not claim it was RED. No
fidelity consequence (tests 2 and 4 cover the behaviour), but the campaign's
own rule is that pins have been wrong four times; this one is inert rather
than wrong, and the claim about it is what is wrong.

**Note 4b — a dormant residual introduced by the fix.** C# calls
`CardPileCmd.Draw(ctx, base.Amount * etherealCount, …)` **unconditionally**
when the owner is a participant, including with a product of 0.
`CardPileCmd.cs:804-813` fires `Hook.ShouldDraw` (and `Hook.AfterPreventingDraw`
on a refusal) **before** `drawsRequested == 0` returns. The sim's
`if … self._ethereal_count == 0: return` skips that dispatch. Today this is
provably unobservable — the two `should_draw` implementers
(`powers.py:814` `NoDrawPower`, `relics/fiddle.py:32`) are pure predicates and
nothing in `sts2_rl/` implements `after_preventing_draw` (grep: dispatcher at
`hooks.py:1921` and the one call site at `player.py:568`, zero listeners) — so
it is a legitimate DORMANT residual, but it should be recorded, not silent.

### 5 — `power/draw_cards_next_turn/AfterSideTurnStart` : CONFIRM (stale)

`DrawCardsNextTurnPower.cs:22-36` guards `ModifyHandDraw` on
`AmountOnTurnStart == 0`; `:38-44` guards the removal on
`AmountOnTurnStart != 0`. Sim: `powers.py:3338-3360` implements **both**
guards. The backing machinery exists and is committed — I checked
`git show HEAD:sts2_rl/creatures.py`, which contains
`snapshot_powers_on_turn_start` at `:79-99` citing `Creature.cs:673-679`, and
it is called from `combat.py:609` (enemies) and `combat.py:1372` (player). The
record's "executed grep … returns nothing" is stale. **CONFIRM `faithful`.**

Minor, pre-existing, not this lane's: C# uses `PowerCmd.Remove(this)`, the sim
uses `_expire()`, which does not fire `on_removed` (see
`cmds.py:_strip_powers_after_death`, which calls the two separately).
Harmless here (`DrawCardsNextTurnPower` has no `AfterRemoved`) and the same
shape applies to `ReboundPower.after_player_turn_end`; flagging so it is on
the record somewhere.

### 6 — `power/nostalgia/g8` : CONFIRM the Rebound half, OVERTURN the Corruption half's rationale

**Rebound half — correctly closed.** Re-derived: with both on the sim's one
chain, Rebound-first gives (redirect, tick) and Nostalgia-first gives
(redirect, no tick) — which is exactly `Hook.cs:1391-1406`'s per-listener
"did I change it" rule applied to `ReboundPower.cs:25-28`'s
`pileType != Discard` bail. The sim now reproduces both C# branches. Which
branch a given application order produces is `hook_dispatch/G2`, correctly not
re-argued. Both order tests reconstructed against the pre-fix class:
`nostalgia_first_leaves_rebound_unticked` **RED** (the old code ticked
unconditionally). Good.

Note this also confirms the record's own 2026-07-27 narrowing text was
already stale in a second way: it claims "Nostalgia's redirect finds the card
already gone from the discard pile". Pre-fix the sim actually ticked Rebound
on *every* contended play, because `on_card_played` fires inside the loop
(`combat.py:996`) while the chain's move happens after it (`combat.py:1048`).
The close note should say that.

**Corruption half — verdict LIVE stands, rationale does not.** See §2 above.

### 7 — `power/rebound/ModifyCardPlayResultPileTypeAndPosition` : CONFIRM the move, **NEEDS-FIX** the guard

The move itself is right and is the single most valuable change in the batch:
`ReboundPower.cs:19-30` is a chain listener, `CardModel.cs:1890` evaluates the
chain once before the play loop, and the sim's dispatch point
(`combat.py:934`) is that same position. The `card in discard_pile` half of
the new guard is a correct substitute for `pileType != PileType.Discard` in
the Power-card case, because `combat.py:904-905` only appends non-Power cards
to `discard_pile` before the hook runs at `:934`. I verified that ordering by
reading the function, not by trusting the report.

**NEEDS-FIX.** `GetResultPileTypeForCardPlay` (`CardModel.cs:2070-2083`) is
the chain's `defaultPileType` argument and returns **`PileType.Exhaust`** for
`ExhaustOnNextPlay || Keywords.Contains(CardKeyword.Exhaust)`, and
`PileType.None` for `IsDupe || Type == Power`. The sim's dispatcher passes the
literal `"discard"` for **every** card (`combat.py:934`; `exhausts_this_play`
is only computed afterwards at `:938`). So for an Exhaust-keyword card,
`ReboundPower` sees `pile == "discard"`, finds the card in `discard_pile`
(appended at `:905`), **ticks, and returns `"draw_top"`** — where
`ReboundPower.cs:25-28` bails, is not added to `Hook.cs:1400-1404`'s
`modifiers` list, and therefore never reaches
`AfterModifyingCardPlayResultPileOrPosition` and never decrements.

Executed against the current tree:

```
rebound only, exhaust card impervious: exhaust=True draw=False discard=False rebound=None   <-- stack consumed
rebound only, plain skill defend     : exhaust=False draw=True  discard=False rebound=None
```

`Impervious.cs:17` declares `CardKeyword.Exhaust`; the sim marks 36
Attack/Skill cards `exhausts=True`, and `ReboundCard`
(`sts2_rl/cards/trash_heap_cards.py:244-272`) is reachable from the Trash Heap
event (`sts2_rl/events/trash_heap.py:18`). **This is live, ordinary play.**

This is *not* a regression — the pre-fix code was worse (the exhausting card
went to draw-top and never exhausted at all; I confirmed that against the
reconstructed old class). But the fix converted a loud divergence into a
**silent** one: the pile is now right and only the stack count is wrong, which
no existing or new test observes. That is precisely round 12's recorded
failure mode.

The fix is in-footprint and two lines, mirroring `combat.py:938`'s own
translation of `GetResultPileTypeForCardPlay`:

```python
if pile != "discard" or card not in getattr(player, "discard_pile", ()):
    return pile
# GetResultPileTypeForCardPlay (CardModel.cs:2070-2083) hands the chain
# PileType.Exhaust for an Exhaust-keyword card or a consumed
# ExhaustOnNextPlay, so ReboundPower.cs:25-28 bails and no stack is spent.
# The sim's hook always receives the literal "discard" (combat.py:934
# computes `exhausts_this_play` only afterwards, :938), so the test has to
# be made here.
if card.exhausts or card.exhaust_on_next_play:
    return pile
self._tick()
return "draw_top"
```

`card.exhaust_on_next_play` is still `True` at hook time — `combat.py:939`
consumes it after the dispatch, where `GetResultPileTypeForCardPlay` consumes
it before; reading it here is the faithful order. A pinning test should play
an Exhaust-keyword card under `ReboundPower(1)` and assert the card exhausts
**and** the power still has amount 1, then that the *next* ordinary play is
redirected.

Verdict on the entry: the hook move is `faithful`; the entry cannot be closed
`faithful` until the exhaust gate is added.

### 8 — `power/rebound/AfterModifyingCardPlayResultPileOrPosition` : **NEEDS-FIX**

The report's justification is:

> "the tick is folded into `modify_card_play_result_pile` itself, gated on the
> SAME condition the dedicated after-hook's 'did I change it' check would
> require: `pile == "discard"` on entry."

`pile == "discard"` on entry is **not** the same condition, for exactly the
reason in §7: `Hook.cs:1400-1404` compares the value before and after *this
listener's* call against the *real* `defaultPileType`, which is `Exhaust` for
an exhausting card and `None` for a Power/dupe. `"discard"` on entry is the
sim's flattening of three distinct C# pile types into one. Folding the tick
into the chain call is a legitimate workaround for the missing
notification-list machinery (`seam/power_cmd` G4 — I confirmed no
`after_modify_card_play_result_pile` mechanism exists), but it has to be gated
on the condition that actually reproduces "I changed it", which means the
exhaust test from §7.

Two further observations that should go in the close note rather than block it:

- The tick now happens **inside** the chain, before later listeners run; C#
  fires all `AfterModifyingCardPlayResultPileOrPosition` callbacks after the
  whole chain (`CardModel.cs:1891-1894`). Unobservable today (no chain
  listener reads Rebound's amount), but it is a real ordering divergence.
- `modify_card_play_result_pile` now has a **mutating side effect inside a
  "modify" chain hook**. The sim has exactly one call site today
  (`combat.py:934`, verified by grep), so it is safe; but any future
  speculative/preview call would silently burn a Rebound stack. Worth a
  one-line warning in the docstring.

### 9 — `power/retain_hand/AfterSideTurnEnd` : CONFIRM

`RetainHandPower.cs:28-34`'s `AfterSideTurnEnd` is the **player** side's
`Hook.AfterTurnEnd`, dispatched at `CombatManager.cs:1307` inside
`EndPlayerTurnPhaseTwoInternal` — after `FlushPlayerHand` (`:1289-1300`,
itself the `ShouldFlush` consumer, `:1325+`) and **before**
`SwitchFromPlayerToEnemySide` ever evaluates `Hook.ShouldTakeExtraTurn`
(`:1358-1368`). So it fires once per player-side end regardless of whether the
enemy side runs.

Sim: `after_player_turn_end` at `combat.py:1484`, after
`discard_hand(flush=self.hooks.should_flush_hand())` at `:1481` and before
`should_take_extra_turn` at `:1502`. Exactly right. The old slot
(`on_enemy_side_end`, `combat.py:701`) is inside `_execute_enemy_turn`, which
`combat.py:1502-1516` returns before on an extra turn.

RED-before reconstructed: `test_ticks_on_a_normal_turn_end` **passed** pre-fix
(the report says so — correct, it is regression coverage) and
`test_ticks_on_an_extra_turn_too` **RED** pre-fix ("survived the extra turn").
Both claims in the report are accurate.

No other consumer moved: `retain_hand` is applied only by Equilibrium
(`cards/colorless_skills.py:285`), Salvo (`cards/colorless_attacks.py:428`) and
a potion (`potions.py:304`); the two other test files that touch it
(`test_new_features.py:296`, `test_printed_vars.py:252`) assert the applied
amount only and both pass. **CONFIRM `faithful`.**

### 10 — `power/steam_eruption/g4` : CONFIRM (dormant, site-verified)

Re-derived independently. `cmds.py:154-197` selects the prevention arm **only**
when `target.max_hp > 0 and not hooks.should_die(target, preventer)`.
`SteamEruptionPower.cs` (read in full) declares `AfterDeath`,
`ShouldStopCombatFromEnding`, `ShouldCreatureBeRemovedFromCombatAfterDeath`,
`ShouldPowerBeRemovedAfterOwnerDeath` — and **no `ShouldDie`**. Its
`AfterDeath` guards `!wasRemovalPrevented`.

I re-ran the enumeration myself: `grep -rn "def should_die" sts2_rl/` returns
exactly three — the dispatcher (`hooks.py:1568`), Fairy in a Bottle
(`potions.py:1338`, `return creature.side != "player"`, i.e. it *never* saves a
monster) and Lizard Tail (`relics/lizard_tail.py:32`, and note it is
`should_die_late`, a different pass, which the report's prefix-matching grep
covered by accident rather than by design — worth saying out loud, since the
Late pass is a separate dispatcher). Relics belong to the player. Nothing can
make `should_die` false for the Waterfall Giant, so the prevention arm and the
unmodelled `CreatureCmd.cs:562-565` re-entry are unreachable through this
power. **CONFIRM DORMANT for this site**; the mechanism-level `gap` stands.

Finding F2 in the report checks out on its factual core: **no `Power` subclass
in `powers.py` implements `should_die` at all** today, so `AdaptablePower` and
`IllusionPower` really have dropped their overrides. Good, genuinely useful
handoff.

### 11 — `power/the_bomb/InstanceType` : CONFIRM LIVE

I re-executed the reproduction independently (two `the_bomb` plays on
consecutive turns):

```
bombs: [[2, 40], [3, 40]] amount: 2
power list keys: ['the_bomb']
```

Identical to the record's 2026-07-26 evidence: one power entry with the
shorter fuse's amount where C# holds two `TheBombPower` instances (Amount 2
and Amount 3). Damage is exact; state and observation are not. **CONFIRM
LIVE**, not inherited-dormant, and CONFIRM there is no in-footprint fix
(`instance_type = INSTANCED` would suppress `on_stack`, which the fuse-list
workaround depends on; a real fix needs `cmds.py` + `full_env.py`).
Finding F3 is fair.

### 12 — `power/vital_spark/BeforeCombatStart` : CONFIRM DORMANT, OVERTURN the reasoning

The record — and the report, which repeats it — say the divergence is that
"C#'s `CardCmd.Afflict` **overwrites**" where the sim adds
`card.affliction is None`. **`CardCmd.Afflict` does not overwrite.**
`CardCmd.cs:625-659`:

- `:641` — `if (!affliction.CanAfflict(card)) return null;`
- `AfflictionModel.cs:200-203` — `CanAfflict` returns **false** when
  `card.Affliction != null && (!IsStackable || card.Affliction.GetType() != GetType())`.
- `:645-657` — a different type would `throw`; the same type does
  `card.Affliction.Amount += (int)amount`.

So the real behaviour split is:

- **different affliction already present** → C# refuses (`CanAfflict` false).
  The sim's `powers.py:2994` guard produces the *same* outcome — and the sim's
  own `CardCmd.afflict` (`cmds.py:1218-1242`) already ports `CanAfflict`, so
  the power-level guard is redundant here, not divergent.
- **`Tainted` already present** → C# **stacks** the amount
  (`TaintedAffliction.is_stackable = True`, `Tainted.cs:9-19`); the sim skips.
  **That, and only that, is the divergence.**

The report's enumeration ("exactly two `on_combat_start` affliction listeners,
disjoint by `card_type`") answers a question that was never the reachability
question. The right question is *can a Skill already carry `Tainted` when a
`BeforeCombatStart` runs*. I checked it:

- `Card.reset_combat_state()` (`cards/base.py:462-473`) does **not** clear
  `card.affliction`, and `combat.py:203-207` explicitly documents that a deck
  card can arrive already afflicted — so the report's "no affliction persists
  across combats" is factually wrong as stated.
- The dormancy nevertheless holds, for a reason the report does not give:
  `VitalSparkPower.on_death` (`powers.py:3017-3026`) clears every `Tainted`
  affliction when its owner dies, and its only owner is the Infested Prism
  monster (`monsters/hive/infested_prism.py:39, :80`), which you must kill to
  win. And `InfestedPrismsElite.cs:14-18` puts exactly **one** Infested Prism
  in the encounter (the sim agrees: `monster_classes=[InfestedPrism]`), so two
  simultaneous `BeforeCombatStart` afflicters cannot exist.
- Trigger to record: a second simultaneous `Tainted` source, or any path that
  leaves the power's owner alive at combat end.

**CONFIRM `gap`, dormant — but the close note must be rewritten**, because it
currently records a false statement about C# and a false statement about the
sim, and it would mislead whoever settles the sibling
`power/galvanic/BeforeCombatStart` (same shape,
`GalvanizedAffliction.is_stackable = True` too).

---

## 2. Explicit ruling on the `power/rebound` record-overturn

**The overturn STANDS. Upheld in full.** This is the strongest piece of work
in the batch.

The guard "Rebound redirects the Rebound card itself" claimed the power is
applied during Rebound's own resolution and so redirects its own card. Traced
from the C# directly, not from the report:

1. `CardModel.OnPlayWrapper` evaluates the chain **once**, at
   `CardModel.cs:1890`, with `GetResultPileTypeForCardPlay()` as the seed —
   and fires the `AfterModifyingCardPlayResultPileOrPosition` callbacks
   immediately after, at `:1891-1894`. Both are **before**
   `BeginCardOrPotionEffect` and the play-count loop.
2. `await OnPlay(choiceContext, cardPlay)` is at `:1931`, inside that loop.
3. `Rebound.cs:25-32` is that `OnPlay`: damage, then
   `PowerCmd.Apply<ReboundPower>(…)` at `:31`.
4. The result pile is applied at `:1976-1990`, from the value captured at
   `:1890`.

`ReboundPower` therefore does not exist as a listener when its own card's
destination is decided. The Rebound card goes to the **discard** pile. The old
sim only "worked" because `on_card_played` is dispatched from a later point
(`combat.py:996`, inside the loop, after `on_play`), which is an artefact of
the wrong hook slot rather than a ported behaviour. The lane's diagnosis is
exactly right.

The corrected pre-existing test pins the C# truth, not a compromise. I
reconstructed the pre-fix class and ran the new assertion against it:
`does_not_redirect_own_play` → **RED** ("rebound self-redirected"). The split
in `test/test_underdocks_hive_events.py` is clean: the new
`test_rebound_does_not_redirect_its_own_play` asserts the card is in
`discard_pile`, absent from `draw_pile`, and the power is at amount 1 (i.e. it
also pins that no stack was spent on the self-play), and
`test_rebound_puts_the_next_play_on_top_of_draw` preserves the original
redirect coverage retargeted at the next play. No coverage was dropped and
nothing was silently deleted.

Handling was also correct procedurally: the lane did not edit the record, it
proposed the re-verdict in its report and flagged it prominently. The
controller should apply it, and should note the *reason* (`CardModel.cs:1890`
precedes `:1931`), not just the verdict.

---

## 3. Spec-compliance verdict: **PASS**

- **Footprint.** `git status --porcelain` shows this lane owns exactly
  `sts2_rl/powers.py` (3 hunks: `DarkEmbracePower` ~`:353-397`, `ReboundPower`
  ~`:3380-3427`, `RetainHandPower` ~`:4309-4331` — I read the whole diff; no
  other class is touched), new `test/test_r13_power1.py`, and modified
  `test/test_underdocks_hive_events.py`. Every forbidden file (`hooks.py`,
  `combat.py`, `player.py`, `cmds.py`, `driver.py`, `run.py`, `relics/**`) is
  modified by other lanes, not this one.
- **`audit/**`.** No `audit/records/**` or `audit/GAP-QUEUE.md` change in the
  tree. (`audit/tools/unlabelled_batches.py` is staged, but it is staged
  alongside the controller's own `.superpowers/sdd/round13/*` briefs and is
  the batch generator — controller work, not this lane's.)
- **Git index.** `R3-report.md` and `test_r13_power1.py` are untracked (`??`),
  i.e. the lane ran no `git add`. No commit/stash/checkout evidence.
- **Method.** TDD was followed for the fixes; I independently reconstructed
  the pre-fix classes in a scratch script (never touching the tree) and
  confirmed 4 of the 5 claimed RED pins really were RED. The one exception is
  documented in §1.4a.
- **Dormancy closes** carry executed enumerations rather than silence
  (`should_die` implementers; `the_bomb` re-execution). Their *content* is
  criticised above, but the discipline was applied.
- **Report contract.** All five required sections present, per-entry close
  notes state which reasoning they replace, findings section present.

The environmental caveat is resolved: the three
`test_powers.py::TestPowerInstanceType` failures the report attributed to the
concurrent `hooks.py` rewrite are **green now** (`py -m pytest
test/test_powers.py -k InstanceType -q` → 12 passed). The attribution was
plausible on the diff (nothing in the lane's 3 hunks touches instancing) and
is now moot.

**Tests re-run by me** (`c:\Users\Perry\Desktop\sts2-rl-tier2`):

```
py -m pytest test/test_r13_power1.py test/test_underdocks_hive_events.py -q
  -> 96 passed
py -m pytest test/test_powers.py test/test_ironclad_powers.py -q
  -> 160 passed
py -m pytest test/test_r13_power1.py test/test_underdocks_hive_events.py \
   test/test_powers.py test/test_ironclad_powers.py test/test_new_features.py \
   test/test_card_plays_started.py test/test_stack_type_single.py \
   test/test_previews.py test/test_relic_live_tail.py test/test_can_receive_powers.py \
   test/test_overgrowth_powers.py test/test_power_modifier_phases.py \
   test/test_power_type_for_amount.py test/test_relics.py \
   test/test_turn_start_snapshot.py test/test_turn_structure_gaps.py -q
  -> 768 passed, 0 failed
```

---

## 4. Code-quality verdict: **GOOD, with two smells**

Positives: the three changed classes' docstrings now carry the C# line
citations and, in `ReboundPower`'s case, an explicit note that the previous
docstring was wrong — exactly the right way to retire a bad rationale.
`RetainHandPower`'s docstring explains *why* `on_enemy_side_end` is the wrong
slot (the extra-turn short circuit), which is the sort of thing that stops the
next person re-introducing it. The `_ExtraTurn` test helper avoids depending
on the out-of-footprint Pael's Eye relic. `DarkEmbracePower.__init__` matches
`Power.__init__`'s signature (`powers.py:96-102`) exactly.

Smells:

1. **A "modify" chain hook with a mutating side effect**
   (`ReboundPower.modify_card_play_result_pile` calls `self._tick()`). Safe
   today because there is exactly one call site, but it is a trap. At minimum
   the docstring should say "must only ever be called once per play; it spends
   a stack".
2. **`hooks.modify_card_play_result_pile`'s own docstring is now provably
   false** (`hooks.py:1081-1090`): "Consulted only for cards that would land in
   the discard pile (exhausted cards and Powers never reach it)." It **is**
   consulted for Power cards and for exhausting cards (`combat.py:934` is
   unconditional). That stale invariant is very likely what led the lane into
   the §7/§8 defect. `hooks.py` is out of the lane's footprint, so this is a
   handoff, but it must not be left standing — it is an active trap for the
   Corruption fix that is queued behind this work.

---

## 5. Reviewer findings that outrank the task's

- **RF1 (most load-bearing).** The Corruption/Nostalgia contention's *final
  pile* is already faithful, in both application orders, because
  `CorruptionPower.cs:27-38` has no `pileType` guard while
  `NostalgiaPower.cs:39-42` and `ReboundPower.cs:25-28` both bail on
  non-`Discard`. C# is order-independent here too, and Corruption always wins.
  The report's "order-independence is itself the divergence" is wrong and, if
  it reaches `GAP-QUEUE.md`, will misdirect the `hooks.py`+`combat.py` lane
  that inherits this. The real Corruption residues are (i) Rebound's stack
  consumed unconditionally where C# consumes it order-dependently, (ii) the
  exhaust happening inside the play-count loop rather than after it
  (`CardModel.cs:1976-1990`), (iii) the absent chain membership. The proposed
  fix shape still closes all three; only the justification needs replacing.
- **RF2.** `ReboundPower` spends a stack on Exhaust-keyword cards where
  `GetResultPileTypeForCardPlay` (`CardModel.cs:2070-2083`) hands the chain
  `PileType.Exhaust` and `ReboundPower.cs:25-28` abstains. Live and
  in-footprint; executed evidence in §7. This is the one item that must be
  fixed before the entries close.
- **RF3.** The `vital_spark` (and by rule-3 inheritance the `galvanic`) record
  states a false fact about C#: `CardCmd.Afflict` refuses a different-type
  affliction (`AfflictionModel.cs:200-203`) and *stacks* a same-type one
  (`CardCmd.cs:656`) — it never overwrites. The divergence is one-sixth the
  size the record describes, and the sim's own `CardCmd.afflict`
  (`cmds.py:1218-1242`) already models `CanAfflict`. Both records' issue text
  should be corrected, not just their verdicts.
- **RF4.** `hooks.py:1081-1090`'s docstring asserts an invariant
  `combat.py:934` violates. Stale-comment gap, out of footprint, feeds RF2.
- **RF5.** Dark Embrace's `etherealCount == 0` early return skips a
  `Hook.ShouldDraw` dispatch that C# always performs
  (`CardPileCmd.cs:804-813` runs it before the `drawsRequested == 0` return).
  Dormant today (zero `after_preventing_draw` listeners) but it belongs in the
  close note as a named residual rather than being invisible.
- **RF6.** `Card` has no `is_dupe` concept anywhere in `sts2_rl/`, so the
  `IsDupe -> PileType.None` arm of `GetResultPileTypeForCardPlay`
  (`CardModel.cs:2073-2076`) is unmodelled engine-wide. Not this lane's, but it
  is the third arm of the same function RF2 is about and nobody appears to
  have it recorded.

---

## 6. Required before this batch folds

1. Add the exhaust gate to `ReboundPower.modify_card_play_result_pile`
   (§7) plus a pinning test (exhausting card under `ReboundPower(1)`: card
   exhausts, power still at 1, next ordinary play redirected).
2. Rewrite entry #2's and entry #6's Corruption-half analysis per RF1 before
   the queue annotation is applied.
3. Rewrite entry #12's close note per RF3.
4. Drop the "All three RED before the fix" claim on entry #4 (§1.4a) and add
   the RF5 residual.
5. Optional but recommended: hand RF4 and RF6 to whoever owns `hooks.py` next.

---

## Re-review (2026-08-01)

Scope: only the NEEDS-FIXES items. Standing verdicts and the `power/rebound`
record-overturn are not re-opened.

**Verdict: APPROVED.**

### Item 1 — the blocking defect (RF2 / §1.7, §1.8) : **RESOLVED**

`ReboundPower.modify_card_play_result_pile` now bails on
`card.exhausts or card.exhaust_on_next_play` before `self._tick()`.

I re-derived the equivalence rather than checking it off. C#'s single test is
`if (pileType != PileType.Discard) return (pileType, position);`
(`ReboundPower.cs:25-28`) against a value seeded by
`GetResultPileTypeForCardPlay` (`CardModel.cs:2070-2083`) and possibly already
rewritten by an earlier chain listener. The sim's three-part conjunction maps
onto it arm for arm:

| C# seed / state | C# result | sim guard that covers it |
|---|---|---|
| earlier listener already rewrote it (Nostalgia) | abstain | `pile != "discard"` |
| `IsDupe` or `Type == Power` -> `PileType.None` | abstain | `card not in player.discard_pile` (`combat.py:904-905` never appends a Power card before the `:934` dispatch) |
| `ExhaustOnNextPlay` or `Keywords.Contains(Exhaust)` -> `PileType.Exhaust` | abstain | **new**: `card.exhausts or card.exhaust_on_next_play` |
| else -> `PileType.Discard` | redirect + notify | falls through to `_tick()` + `return "draw_top"` |

The new arm reads exactly the expression `combat.py:938` uses for the same C#
line, so it is the sim's own translation of that source rather than a second,
independent one — which is the right way to keep them from drifting apart.

Edge cases executed against the shipped tree (my own probe, not the report's):

```
PRE-FIX-2 (hook move, no exhaust guard), Impervious : rebound=None   <- stack spent  (RED)
POST-FIX  (shipped),                     Impervious : rebound=1      <- stack kept   (GREEN)
PRE-FIX-2, Strike with exhaust_on_next_play=True    : rebound=None   (RED)
POST-FIX,  Strike with exhaust_on_next_play=True    : rebound=1      (GREEN)
POST-FIX,  ordinary Strike                          : draw=True, rebound=None  (still redirects+ticks)
POST-FIX,  Power card (inflame)                     : rebound=1      (abstains, card leaves combat)
```

- **RED-first confirmed independently.** I rebuilt the intermediate
  (hook-moved, no-guard) class in a scratch script and it spends the stack —
  matching the report's `KeyError: 'rebound'`. The claim is real, not asserted.
- **The `exhaust_on_next_play` edge case the coordinator asked about is
  genuinely safe**: `combat.py:939` clears the flag on the line *after* the
  `:934` dispatch, where `GetResultPileTypeForCardPlay` consumes it *as* it
  produces the seed — so reading it inside the hook reads the same value C#
  seeds with. Probed both flag paths; both abstain.
- **Power/Dupe -> `PileType.None`**: the Power half is covered by the
  discard-pile membership test (probe confirms `inflame` abstains and the
  stack survives). The Dupe half is unmodelled *engine-wide* (RF6 — no
  `is_dupe` anywhere in `sts2_rl/`), unchanged by this pass and correctly
  handed off rather than faked.

Pin: `test_r13_power1.py::TestReboundResultPileHook::test_exhausting_card_does_not_spend_a_rebound_stack`
uses `ImperviousCard` (Skill, `exhausts = True`, `sts2_rl/cards/impervious.py:25`;
`Impervious.cs:17` declares `CardKeyword.Exhaust`) and asserts both halves —
the stack survives the exhausting play *and* still redirects the next ordinary
one. That second assertion is what makes it a behavioural pin rather than a
counter check. Good test.

Entry #8 closes on the same fix, correctly: the tick lives inside the same
method, so the corrected gate *is* the corrected "did I change it" condition.

### Item 2 — rewritten entries #2, #4, #6, #7, #8, #12 : **RESOLVED**

All six carry the corrected analysis with the superseded text struck rather
than deleted, per the close-note contract.

- **#2 (RF1) — correct, and the handoff is now actively protective.** The
  rewrite states what I derived: `CorruptionPower.cs:27-38` has no `pileType`
  guard, `NostalgiaPower.cs:39-42` / `ReboundPower.cs:25-28` both bail on
  non-Discard, so C# is also order-independent and Corruption also always
  wins — the sim's final pile already matches. The three real residues
  (Rebound's stack spent unconditionally vs. order-dependently; the exhaust
  move inside the play-count loop vs. `CardModel.cs:1976-1990`'s post-loop
  `case PileType.Exhaust` at `:1984`; Corruption absent from the chain) are
  stated correctly and the fix shape is shown to close all three at once. The
  queue annotation ends with an explicit **"Do not build 'let application
  order decide the winner' — it already doesn't, in either engine."** That is
  the single most important sentence for the later `hooks.py`+`combat.py`
  lane, and it is now in the text that lane will read.
- **#6** — correctly demoted to a cross-reference to #2 rather than carrying
  its own copy of the (wrong) reasoning. The Rebound half stays closed.
- **#4 (RF5)** — the false "All three RED" claim is struck and the
  non-distinguishing test is named; the zero-`etherealCount` early-return
  residual (C# always calls `CardPileCmd.Draw(..., 0, ...)`, and
  `CardPileCmd.cs:804-813` fires `Hook.ShouldDraw` *before* the
  `drawsRequested == 0` return) is recorded as a named dormant residual with
  the zero-listener evidence.
- **#7 / #8 (RF2)** — both close notes retract the premature `faithful` and
  state precisely which condition was incomplete.
- **#12 (RF3)** — the false "C#'s `CardCmd.Afflict` overwrites" claim is gone
  and replaced with the true split (`CanAfflict` refuses a different type,
  `AfflictionModel.cs:200-203`; `CardCmd.cs:656` stacks a same-type one), the
  divergence is correctly narrowed to the stackable-`Tainted` case, and the
  `power/galvanic` sibling is flagged as carrying the identical false claim.

### Item 3 — anything outside `powers.py` `ReboundPower` + named tests + report : **CLEAN**

Diffed the whole delta against what I reviewed on 2026-07-31:
`sts2_rl/powers.py`'s `DarkEmbracePower` and `RetainHandPower` hunks are
byte-identical; the only change is inside
`ReboundPower.modify_card_play_result_pile` plus its class docstring.
`test/test_r13_power1.py` gained exactly one test;
`test/test_underdocks_hive_events.py` is unchanged from the version I already
cleared. `test/test_hook_order.py`,
`test/test_task8_aeonglass_generated_wither.py` and the untracked
`test/test_round13_listener_derivation.py` appeared in the tree since my first
pass and belong to the concurrent hooks/monster lanes — not this lane's, not
findings here. No `audit/**` change; `R3-report.md` and `R3-review.md` are
still untracked (`??`), so no git-index mutation.

Sweep re-run by me (the review's 16 files plus `test_printed_vars.py`):
**817 passed, 0 failed.**

### Remaining non-blocking nits (do not hold the fold)

1. `ReboundPower`'s docstring still says, in its third paragraph, that the
   tick is "gated on the SAME condition that call would need — `pile ==
   "discard"`", which the newly-added fourth paragraph then correctly
   qualifies. The two paragraphs read as contradicting each other; the third
   should be reconciled to "`pile == "discard"` **and** a non-exhausting card"
   next time that file is open.
2. Entry #12 still opens its dormancy bullet with "No affliction persists
   across combats", which remains over-broad as a statement of fact:
   `Card.reset_combat_state()` (`cards/base.py:462-473`) does not clear
   `card.affliction` and `combat.py:203-207` explicitly documents that a deck
   card can arrive afflicted. The *clearing* mechanism the note goes on to
   name (`VitalSparkPower.on_death`, `powers.py:3017-3026`, whose only owner
   is the Infested Prism you must kill to win) is the correct argument and
   the verdict stands on it — the leading sentence should just be reworded to
   say so. The second independent leg, that `InfestedPrismsElite.cs:14-18`
   (and the sim's `monster_classes=[InfestedPrism]`) puts exactly **one**
   Prism in the encounter, so two simultaneous `BeforeCombatStart` afflicters
   cannot coexist, is still uncited and would make the enumeration airtight.
3. RF4 (`hooks.py:1081-1090`'s docstring asserts an invariant `combat.py:934`
   violates — the direct cause of this pass's defect) and RF6 (no `is_dupe`
   concept anywhere in `sts2_rl/`) remain open, correctly, as out-of-footprint
   handoffs.
