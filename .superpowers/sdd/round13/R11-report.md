# R11 report — ledger backlog minis (round 13)

Lane: R11. Worktree `c:\Users\Perry\Desktop\sts2-rl-tier2`. Spec: decompiled
C# at `c:\Users\Perry\Desktop\Slay the Spire 2`, non-ascension.

Footprint touched (all inside the declared list): `sts2_rl/cards/breakthrough.py`,
`sts2_rl/monsters/overgrowth/vantom.py`, `sts2_rl/selectors.py`,
`audit/tools/state_machine_probes.py`, `test/test_is_dead_early_returns.py`,
`test/test_overgrowth_powers.py`, `test/test_selectors.py`. No file outside
this list was edited. No `audit/records/**` or `audit/GAP-QUEUE.md` file was
edited (read-only `git show`/`git diff`/direct reads only). No git index
command was run.

**Process honesty note, up front (applies to items 1 and 2):** for items 1
and 2 I made the code edit before writing the pinning test, instead of the
required test-first order. I did not revert to reconstruct RED (forbidden,
and another agent is live in the tree). Instead: (a) the pre-edit source is
quoted verbatim below and in the diffs, so RED is derivable by inspection —
for item 1 the deleted guard's presence/absence is provably behavior-neutral
by construction (see item 1); for item 2 the pre-edit `Intent(...)` call had
no `status_count` kwarg, so the dataclass default (`None`, `monsters/base.py:74`)
provably made `intent.status_count == 3` false. (b) I ran the real test suite
after the edit and it is green. Items 3 and 4 below were done test-first with
genuine RED runs, as required. Flagging this rather than presenting all four
as uniformly TDD-clean.

---

## Item 1 — `cards/breakthrough.py` uncounted 6th `card/_is_dead_early_return` site — **FIXED**

**Verdict: FIXED.** Re-derived against `Breakthrough.cs` (`src/Core/Models/Cards/Breakthrough.cs:24-31`):

```csharp
protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
{
    VfxCmd.PlayOnCreatureCenter(base.Owner.Creature, "vfx/vfx_bloody_impact");
    await CreatureCmd.Damage(choiceContext, base.Owner.Creature, base.DynamicVars.HpLoss.BaseValue,
        ValueProp.Unblockable | ValueProp.Unpowered | ValueProp.Move, this);
    await DamageCmd.Attack(base.DynamicVars.Damage.BaseValue).FromCard(this).TargetingAllOpponents(base.CombatState)
        .WithHitFx("vfx/vfx_attack_blunt", null, "heavy_attack.mp3")
        .Execute(choiceContext);
}
```

C# has no `is_dead`/`IsEnding` check between the self-damage and the AoE
attack — confirmed, same as Blood Wall / Brand / Hemokinesis. The sim's tail
after the self-damage is a **loop**, not one call (`handles_own_routing`),
but every iteration passes `dealer=ctx.player` to `DamageCmd.deal`, and
`DamageCmd.deal`'s own `dealer.is_dead` bail (`cmds.py:272-273`) fires
identically on every iteration once the player is dead — mirroring
`AttackCommand.Execute`'s `Attacker.IsDead` bail
(`AttackCommand.cs:528-531`), which for Breakthrough (`_hitCount = 1`, no
upgrade) is checked exactly **once**, before the single hit-iteration that
would otherwise batch-damage every opponent
(`AttackCommand.cs:538-544,653`). So the reasoning transfers: deleting the
top-level guard changes nothing observable, because the callee already
refuses every enemy once the dealer is dead.

Deleted (`sts2_rl/cards/breakthrough.py`):
```diff
         DamageCmd.deal(
             ctx.hooks, ctx.player, self._hp_loss, dealer=ctx.player, card=self,
             props=ValueProp.UNBLOCKABLE | ValueProp.UNPOWERED | ValueProp.MOVE)
-        if ctx.player.is_dead:
-            return
+        # Breakthrough.cs has no is_dead guard here -- ... DamageCmd.deal's
+        # own dealer.is_dead bail ... is a no-op on every enemy once the
+        # self-damage has killed the player -- see card/_is_dead_early_return
+        # (Task 27) and test/test_is_dead_early_returns.py.
         # 9 (+ Strength) damage to each living enemy.
         for enemy in list(ctx.enemies):
```

The **mid-loop** `if ctx.player.is_dead: break` (unchanged) is a *different*
site, out of the brief's literal ask, and it is already independently
verdicted `faithful` in `audit/records/card/breakthrough.json`'s guards list
("mirrors the combat-over check the game's attack command performs between
hits") — left alone.

Test: `test/test_is_dead_early_returns.py`, new `TestBreakthroughGuardDeleted`
(2 tests: dying from the HP loss lands no attack on any enemy;
non-lethal play is unaffected). Both green post-fix; behavior is provably
identical pre/post-fix (see honesty note above) so there is no true RED for
this class of change — the same is documented for Blood Wall/Brand/Hemokinesis
in the same file's header comment.

---

## Item 2 — `monsters/vantom.py` DISMEMBER loses its status count — **FIXED**

**Verdict: FIXED.** Verified `Vantom.cs:119`:
```csharp
MoveState moveState3 = new MoveState("DISMEMBER_MOVE", DismemberMove,
    new SingleAttackIntent(DismemberDamage), new StatusIntent(3));
```
— the second intent's constant is `3` (also `_dismemberWounds` at
`Vantom.cs:34`, consumed by `CardPileCmd.AddToCombatAndPreview<Wound>(targets,
PileType.Discard, 3, null)` at `Vantom.cs:188`). This is the 4th site of the
`monster/_intent_count_lost` mechanism per the brief and per
`audit/records/monster/vantom.json`'s own DISMEMBER guard note (already
flagged there on 2026-07-28, never fixed in code): *"the StatusIntent's COUNT
(3) is still not representable ... which is the separate dormant mechanism
monster/_intent_count_lost (aeonglass/g5, test_subject/g7, the_insatiable/g4)
and is not re-verdicted here."*

Fix (`sts2_rl/monsters/overgrowth/vantom.py`): added `_DISMEMBER_WOUNDS = 3`
(replacing the previously-separate literal `3` used by the wound-discard
loop, so both consumers read one constant) and passed
`status_count=_DISMEMBER_WOUNDS` on the DISMEMBER `Intent`, matching the
sibling sites (`aeonglass.py:79-80`, `hive/the_insatiable.py:40`,
`glory/test_subject.py`).

Test: `test/test_overgrowth_powers.py::TestVantomDismember::
test_dismember_telegraphs_the_status_intent_too` — this test already
existed and asserted `intent.has(MoveType.STATUS_CARD)`; I added
`assert intent.status_count == 3`. Pre-edit, `Intent.status_count` defaults
to `None` (`monsters/base.py:74`, since the old `Intent(...)` call passed no
`status_count` kwarg — confirmed by reading the file before editing), so this
assertion is provably false on the pre-fix tree and true after — genuine
RED/GREEN by construction, run post-fix and green (see item 2 diff below;
not re-run pre-fix per the honesty note, but the failure is deterministic
from the dataclass default, not from any runtime condition).

```diff
 _DISMEMBER_DMG = 26
+_DISMEMBER_WOUNDS = 3     # Vantom.cs:34 _dismemberWounds; also StatusIntent(3) at :119
 ...
         if self._move_key == "DISMEMBER":
-            # Vantom.cs:119 — SingleAttackIntent(26) AND StatusIntent(3).
+            # Vantom.cs:119 — SingleAttackIntent(26) AND StatusIntent(3). The
+            # 4th site of the closed monster/_intent_count_lost mechanism...
             return Intent(MoveType.ATTACK, damage=_DISMEMBER_DMG,
-                          also=(MoveType.STATUS_CARD,))
+                          also=(MoveType.STATUS_CARD,),
+                          status_count=_DISMEMBER_WOUNDS)
 ...
-            for _ in range(3):
+            for _ in range(_DISMEMBER_WOUNDS):
                 CardPileCmd.add_to_discard(ctx.hooks, ctx.player, WoundCard())
```

---

## Item 3 — `selectors.py` clamp `to_draw_top`'s cost ranking — **FIXED**

**Verdict: FIXED, genuine TDD.** Confirmed the mechanism against
`cards/base.py:407-419` — `Card.energy_cost` returns an unplayable card's
canonical `-1` verbatim (`if self._energy_cost < 0: return self._energy_cost`,
mirroring `CardEnergyCost.GetWithModifiers`'s early short-circuit,
`CardEnergyCost.cs:100-103`). `selectors.py`'s `_cost()` helper (shared by
`"upgrade"` and `"to_draw_top"`) read this raw, so a curse/status card (e.g.
Wound, `_energy_cost = -1`) sorted as *cheaper* than a genuine 0-cost card
(e.g. Thinking Ahead, `colorless_skills.py:835`) in the `to_draw_top`
tie-break and won the pick regardless of offered order.

Test written first: `test/test_selectors.py::
test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero`. Ran RED on the
unmodified tree:
```
py -m pytest test/test_selectors.py -q -k clamp
FAILED ... assert [Wound] == [Thinking Ahead]
1 failed, 10 deselected in 1.04s
```
Fix:
```diff
 def _cost(card: Card) -> int:
-    return _X_COST_RANK if card.energy_cost_x else card.energy_cost
+    # `Card.energy_cost` reads an unplayable card's canonical -1 back
+    # verbatim ... Clamped to 0 so a curse/status card TIES a genuinely
+    # free 0-cost card ... instead of out-ranking it.
+    return _X_COST_RANK if card.energy_cost_x else max(0, card.energy_cost)
```
Re-ran: `py -m pytest test/test_selectors.py -q` → **11 passed**. GREEN.

This is a sim-only RL heuristic (no C# analogue); the fix is scoped to
`_cost()` (shared by `"upgrade"` too — checked: an unplayable card would
already sort last there via `not is_upgradable` before cost is ever
consulted for real deck content, so the clamp is safe there as well, not
just inert).

---

## Item 4 — `audit/tools/state_machine_probes.py` stale zero-weight grep — **FIXED**

**Verdict: FIXED**, plus one important correction to the brief's framing and
one finding beyond it (below).

Found the current raise message: `sts2_rl/monsters/state_machine.py:273`
(current tree — the brief's own path, `sts2_rl/state_machine.py`, no longer
exists; the module is `sts2_rl/monsters/state_machine.py`):
```python
raise RuntimeError(f"No valid state found in RandomBranchState {self.id}!")
```
matching `RandomBranchState.cs:127`'s `throw new InvalidOperationException
("No valid state found in RandomBranchState " + Id + "!")` **verbatim** — this
is round 12 T22's rename to match the C# text exactly. The probe's two
functional grep sites (`_walk_machine` inside `zero_weight()`, and the
matching `except` clause inside `nondyadic_weights()`) still checked for the
**pre-T22** substring `"No valid branch"`, which is not a substring of the
current message, so a genuine hit was silently reclassified as an "other
error" (deferred) rather than counted.

Fixed both substring checks (`"No valid branch"` → `"No valid state found"`),
the docstrings/labels quoting the old text, and a stale citation
(`state_machine.py:182-183` → corrected, see below). Diff:
`git diff HEAD -- audit/tools/state_machine_probes.py` (4 functional/label
sites + 2 docstring corrections).

**Correction to the brief's framing — this is bigger than a text mismatch.**
T22 did not just rename the message; it also fixed the *reachability* the
probe was built to detect. Reading `state_machine.py:255-273`: the sim now
draws via `_weighted_roll` **first**, exactly like C#'s
`rng.NextFloat(max)` (`RandomBranchState.cs:117-118`), and only then loops
branches — so an all-zero-weight vector resolves to branch 0 immediately
(`roll` starts at 0, first branch's `roll <= 0` is true), matching C#'s
"burns a draw, picks branch 0" behavior exactly. **It no longer raises on
zero weight at all.** The remaining `RuntimeError` is reachable only by a
*genuine* sequential-subtraction float-rounding fall-through — which is
**symmetric** with C#'s own throw at the same site, not the zero-weight
*asymmetry* this probe exists to catch. `audit/GAP-QUEUE.md`'s
`monster_state_machine/G7` entry (closed 2026-07-30) already documents this
correctly ("the pre-draw zero-total special case is gone... an all-zero
weight vector burns one draw and resolves to the FIRST branch, no crash") —
so the **queue text needs no change**; only the standalone tool had drifted
behind it.

**"PROVE the probe fires again" — run honestly, plus a deterministic proof.**
Running the real probe (natural random fuzz, unchanged corpus) shows **0
hits both before and after the grep fix** — for two different reasons: before,
the substring could never match anything; after, the substring is correct but
the underlying divergence is closed, so nothing in 6.56M transitions (82
machines, walks=200×steps=400, two passes) reaches the raise at all:
```
py audit/tools/state_machine_probes.py zero-weight   (after fix)
  TOTAL machines fuzzed: 82  transitions: 6560008
  'No valid state found' (total weight 0) hits: 0
  fractional (non-whole) branch weight vectors reached: 1
    Fogmog.BRANCH=[0.4, 0.6]

py audit/tools/state_machine_probes.py nondyadic-weights   (after fix)
  transitions fuzzed with a fractional vector live: 80000
  'No valid state found' fall-throughs: 0
```
To give genuine affirmative proof the corrected grep *works* (rather than
relying on statistical luck that never occurred either before or after), I
wrote a standalone, throwaway script (not part of any tracked file) that
monkeypatches `_weighted_roll` from *outside* the module (same style
`spawn_roll()` already uses for `roll_move`) to force the fall-through
deterministically:
```
forced exception text: 'No valid state found in RandomBranchState PROBE!'
OLD probe substring 'No valid branch'    in msg: False
NEW probe substring 'No valid state found' in msg: True
PROOF: the old probe grep could never classify this RuntimeError as a hit;
the corrected grep does.
```
Full sweep sanity check: ran every probe in the file
(`py audit/tools/state_machine_probes.py`, no argument) end to end — exit 0,
no traceback, output consistent with the individual runs above.

---

## Item 5 — `creature_card_cmds/step19` closure re-derivation (**REPORT ONLY**, no code/record edits)

### What step 19 actually covers

Read `audit/records/seam/creature_card_cmds.json`, the entry whose `what`
starts `"19."`:
> *19. Heal guard: IsEnding && !IsPlayer -> return. There is NO dead guard*
> **verdict: faithful.** *"Closed 2026-07-27: `CreatureCmd.heal`'s `if
> target.is_dead: return 0` is gone. The only early return left is
> `combat.is_over and target.side != 'player'` (sts2_rl/cmds.py), which is
> `CreatureCmd.cs:693-696`'s `IsEnding && !IsPlayer` and nothing more."*

So step 19 is specifically about **`CreatureCmd.heal`'s own inline guard**
(`cmds.py:520-523`), not about `HookSystem`'s generic hook-dispatch gate.

### Re-derivation against the current tree

Current sim (`sts2_rl/cmds.py:520-523`):
```python
combat = getattr(hooks, "combat", None)
if (combat is not None and getattr(combat, "is_over", False)
        and target.side != "player"):
    return 0
```
`combat.is_over` (`sts2_rl/combat.py:1571-1573`):
```python
@property
def is_over(self) -> bool:
    return self.phase == Phase.COMBAT_OVER
```
Current C# (`src/Core/Commands/CreatureCmd.cs:691-696`):
```csharp
public static async Task Heal(Creature creature, decimal amount, bool playAnim = true)
{
    if (CombatManager.Instance.IsEnding && !creature.IsPlayer)
    {
        return;
    }
```
And `CombatManager.cs` — read directly, not from the sim's prose:
```csharp
public bool IsEnding {                       // :180-202
    get {
        if (!IsInProgress) return false;      // <- IsEnding requires IsInProgress
        if (_pendingLoss != null) return true;
        if (.../* a primary enemy is alive */) return false;
        if (Hook.ShouldStopCombatFromEnding(_state)) return false;
        return true;
    }
}
public bool IsOverOrEnding {                  // :210-220
    get { return IsEnding ? true : !IsInProgress; }
}
```
`IsInProgress` is set `false` only at real teardown
(`CombatManager.cs:915` `ResetCombat`, `:962` `ProcessPendingLoss`, `:977`
`EndCombatInternal`) — i.e. **after** the ending sequence has run its course.
So `IsEnding` is true exactly in the window "a loss is pending or all
primary enemies are dead, but `IsInProgress` hasn't flipped false yet", and
becomes false again the instant `IsInProgress` does (its own leading guard).

**The sim's `combat.is_over` is `phase == Phase.COMBAT_OVER`**, which
(confirmed by `combat.py`'s own `is_over_or_ending` docstring at
`combat.py:1598-1618`, and separately by `_end_combat`/`_process_pending_loss`
being the sim's mirror of `EndCombatInternal`/`ProcessPendingLoss`) is set at
the **same moment** C#'s `IsInProgress` flips false — i.e. `combat.is_over`
mirrors `!IsInProgress`, **not** `IsEnding`.

### The closure's equivalence claim is false, not harmless

`is_over` and `is_ending` are, per `combat.py:1571-1618`, mutually exclusive
booleans whose OR is `is_over_or_ending` (`is_ending`'s own leading clause
returns `False` once `phase == Phase.COMBAT_OVER`). So step 19's claim that
`combat.is_over ... is CreatureCmd.cs:693-696's IsEnding && !IsPlayer` is not
approximately right or narrower — **it is checking the wrong window
entirely**: C#'s guard is live *during* the ending sequence and goes quiet
the moment combat is actually torn down; the sim's guard is quiet during the
entire ending sequence and only activates once torn down, i.e. after C#'s
own guard has already gone false.

**Concrete divergence this hides**, and the code path that exposes it: any
non-player heal (`target.side != "player"`) reached via a command dispatched
in the window between the killing blow and the teardown — e.g. an
on-death/on-kill effect that heals a surviving ally monster, or (per the
issue text's own named triggers) Illusion's REVIVE move / Adaptable's
respawn / Reattach firing from a hook reached in that window rather than from
the monster's own ordinary turn — is **wrongly allowed** by the sim
(`combat.is_over` is still `False` there) where C# would refuse it
(`IsEnding` is `True` there). The correct predicate for this specific site is
`combat.is_ending` (**not** `is_over`, and — importantly — **not**
`is_over_or_ending` either: C#'s guard is the bare `IsEnding`, which by its
own leading clause stops applying once truly torn down, so
`is_over_or_ending` would over-guard the post-teardown case C# does not
block).

### Relationship to R1's F3 — ADJACENT, not the same defect; NOT the same code path

R1's F3 (`.superpowers/sdd/round13/R1-report.md` §8): `HookSystem.
combat_is_over` (`sts2_rl/hooks.py:515-555`) is `_each()`'s gate
(`hooks.py:651`) for the 73 `_COMBAT_GATED_HOOKS` dispatch names, and it is
**textually the same predicate** as `CombatState.is_over`:
```python
return getattr(combat, "phase", None) == _PHASE_CLS.COMBAT_OVER
```
`HookSystem.combat_is_over`'s own docstring makes the **identical false
claim** step 19's closure text makes — *"The sim has one flag where C# has
two states (IsEnding ... IsOver ...): CombatState.phase is set to
Phase.COMBAT_OVER in _end_combat, which is the moment the ending begins, so
it covers both."* That premise is exactly what F3 (and this re-derivation)
show is wrong: the phase flip happens at the **end** of the ending sequence,
not the start.

So: **same root cause** (the codebase's `is_over`/`phase==COMBAT_OVER` flag
is treated as if it already covered C#'s `IsEnding`), manifesting as **two
separate, non-identical defects**:

| | F3 | step 19 |
|---|---|---|
| site | `HookSystem.combat_is_over` (`hooks.py:515-555`), read by `_each` (`hooks.py:651`) | `CreatureCmd.heal`'s own inline guard (`cmds.py:520-523`) |
| mechanism | generic hook-dispatch gate, 73 hook names | one command's hand-written early return, not a hook dispatch at all |
| C#'s real predicate | `CombatManager.IsOverOrEnding` (`Hook.cs:53-63`'s `IterateCombatHookListeners`) | `CombatManager.IsEnding` alone (`CreatureCmd.cs:693`) — narrower; explicitly excludes the post-teardown state |
| correct sim replacement | `combat.is_over_or_ending` | `combat.is_ending` — **not** the same property F3 wants |

`CreatureCmd.heal` does not call `hooks.combat_is_over` and is not reached
through `_each`'s `_COMBAT_GATED_HOOKS` machinery at all — it reads
`combat.is_over` directly via `getattr(hooks, "combat", None)`. **Fixing
`HookSystem.combat_is_over` (F3's fix) would not touch `CreatureCmd.heal`'s
guard, and vice versa.** They are adjacent instances of the same
misunderstanding, not the same code path, and — this is the detail that
would bite a "just swap `is_over` for `is_over_or_ending` everywhere" fix —
they don't even want the **same replacement property**: F3's dispatchers
want `is_over_or_ending` (matching `IterateCombatHookListeners`'s literal
gate), step 19's heal guard wants `is_ending` alone (matching
`CreatureCmd.Heal`'s literal, narrower guard, which explicitly stops
applying once truly torn down).

### Answer to the controller's question

**No, one fix does not close both.** They require two separate edits in two
separate files, and a naive shared fix (e.g. redefining `combat.is_over`
itself to mean "ending or over") would be wrong on its own terms — `is_over`
legitimately needs to keep meaning `!IsInProgress` for whatever else reads it
correctly today, and even a correct fix must pick the **right** one of
`is_ending` / `is_over_or_ending` per call site, not the same one both times.

**Recommendation for the controller**, not applied here (no record edits made):
1. Step 19's closure should be **reopened or its close note corrected** —
   the equivalence claim it rests on ("combat.is_over ... IS ... IsEnding")
   is false, not merely imprecise. The underlying `CreatureCmd.heal` code is
   otherwise fine (the `target.side != "player"` half is correct); only the
   `is_over` half of the guard is wrong.
2. This is now the **second independently-found instance** of "a sim call
   site reads `is_over`/`phase==COMBAT_OVER` where C# actually wants
   `IsEnding` or `IsOverOrEnding`" (F3 being the first, at the generic
   dispatch-gate level). Given two instances found without looking for them,
   a targeted grep for other `combat.is_over` / `hooks.combat.is_over` /
   `phase == Phase.COMBAT_OVER` reads across `sts2_rl/` (outside
   `_end_combat`'s own definition site) to check each one against its C#
   counterpart is likely worth a dedicated task before either fix lands, so
   both known sites and any others surface together rather than in
   sequence.

---

## Record-close proposals

**`audit/records/card/breakthrough.json`** — no existing guard entry covers
the deleted top-level guard (its two current guard entries are the
enemy-filter gap and the mid-loop break, which is `faithful` and untouched).
Propose **adding** a third guard entry, in the same style as
`card/hemokinesis.json`'s matching entry:
- `what`: *"the sim returns early on `if ctx.player.is_dead` between the HP
  loss and the AoE loop (breakthrough.py, now deleted)"*
- `verdict`: `faithful`
- close note: *"Closed 2026-08-01 (round 13, R11 item 1). DELETED — C#
  genuinely continues past the self-damage with no `is_dead`/`IsEnding` check
  (Breakthrough.cs:28-30), and the sim now matches because the per-enemy
  `DamageCmd.deal(..., dealer=ctx.player, ...)` the loop reaches already
  self-gates on `dealer.is_dead` (cmds.py:272-273), mirroring
  `AttackCommand.Execute`'s `Attacker.IsDead` bail (AttackCommand.cs:528-531),
  checked once per hit-iteration — Breakthrough is a single hit, so the whole
  batch is refused together exactly as the removed guard achieved. Same
  family and same reasoning as card/blood_wall, card/brand and
  card/hemokinesis's guards under card/_is_dead_early_return (Task 27).
  Pins: test/test_is_dead_early_returns.py::TestBreakthroughGuardDeleted (2
  tests)."*
Also update the `verdict` field at the top of `breakthrough.json` from `gap`
— unless the enemy-filter `is_dead`-vs-`is_gone` guard (still open, still
`gap`, untouched by me) is what keeps it there, in which case no change;
I did not re-derive that guard and it is out of this item's scope.

**`audit/records/monster/vantom.json`**, the DISMEMBER guard (currently
`faithful` with an open note) — propose refreshing the note, not the
verdict (it was already `faithful` because the *intent kind* was already
correct; only the count was missing and explicitly flagged as
not-re-verdicted):
- close note addition: *"Refreshed 2026-08-01 (round 13, R11 item 2):
  `status_count=3` now set on the DISMEMBER Intent (vantom.py), closing the
  4th site of monster/_intent_count_lost this guard's note named but left
  open. `Intent` (monsters/base.py:52-74) does now have a status_count field
  — the note's 'has no status-count field' clause is stale, superseded by
  Task 28's fix for the other three sites."*

**`audit/GAP-QUEUE.md`** — three "Named work with no entry of its own" bullets
now completed and can be struck or marked done (I did not edit the file; text
below is the proposed replacement wording for the controller):
- the `card/breakthrough` bullet (queue lines ~128-133) → done, 2026-08-01,
  round 13 R11 item 1.
- the `monster/vantom` bullet (queue lines ~141-144) → done, 2026-08-01,
  round 13 R11 item 2.
- the `selectors.py "to_draw_top"` bullet (queue lines ~145-151) → done,
  2026-08-01, round 13 R11 item 3.

No record or queue change is needed for item 4: `monster_state_machine/G7`
(queue lines ~1946-1970) already accurately describes the current
`state_machine.py` behavior (closed 2026-07-30); only the standalone probe
tool had drifted behind it, and that tool carries no record of its own.

Item 5 is report-only per the brief; the controller applies whatever
correction to `creature_card_cmds` step 19 it judges appropriate from §5
above. No proposal text is pre-drafted for it beyond "reopen or correct the
close note" since the exact record mechanics (whether to also open a new
step for the heal-guard-specific fix, or fold it under a broadened step 19)
is an editorial call outside a report-only item's remit.

---

## Queue-annotation proposals (GAP-QUEUE.md style, terse)

**`card/_is_dead_early_return`** — Breakthrough's 6th site (top-level guard)
closed 2026-08-01 (round 13 R11 item 1) by the same reasoning as Blood
Wall/Brand/Hemokinesis: `DamageCmd.deal`'s `dealer.is_dead` bail already
refuses every enemy once the self-damage kills the player. The mid-loop
break guard stays `faithful`, untouched.

**`monster/_intent_count_lost`** — Vantom's 4th site (DISMEMBER,
`Vantom.cs:119`'s `StatusIntent(3)`) closed 2026-08-01 (round 13 R11 item 2):
`status_count=_DISMEMBER_WOUNDS` (3) now set. All 4 known sites now carry
their count; the encoder still reads only the flag bit (unchanged, per the
mechanism's own dormancy note).

**`card/_unplayable_cost`** (or wherever `selectors.py`'s finding lives) —
`scripted_card_selector`'s `to_draw_top`/`upgrade` shared `_cost()` helper now
clamps `card.energy_cost` to `max(0, ...)` before ranking, closed 2026-08-01
(round 13 R11 item 3): an unplayable card's canonical `-1` now ties a
genuine 0-cost card instead of out-ranking it. New test:
`test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero`.

**`monster_state_machine` tooling** (`audit/tools/state_machine_probes.py`)
— the `zero_weight`/`nondyadic_weights` probes' `"No valid branch"` grep,
stale since round 12 T22 renamed the sim's raise message to match
`RandomBranchState.cs:127` verbatim, fixed to `"No valid state found"`
2026-08-01 (round 13 R11 item 4). Re-running both probes still shows 0 hits
— correctly, since T22 also fixed the *reachability* (an all-zero-weight
vector no longer raises at all; the record's `monster_state_machine/G7`
closure already says so and needed no change). Standalone deterministic
proof (forced via monkeypatching `_weighted_roll`) confirms the corrected
grep now classifies a genuine hit correctly where the old one never could.

**`creature_card_cmds` step 19** (report only, round 13 R11 item 5) —
closure's equivalence claim ("sim `combat.is_over` IS C#'s `IsEnding &&
!IsPlayer`") is FALSE, not merely imprecise: `combat.is_over` mirrors
`!IsInProgress` (true only after teardown); C#'s guard is `IsEnding` alone
(true only *during* the ending sequence, false again once `IsInProgress`
flips). Same root confusion as `seam/hook_dispatch`'s new F3 finding
(`HookSystem.combat_is_over` vs `IsOverOrEnding`) but an ADJACENT, separate
defect — different file, different mechanism (a hand-written command guard,
not a hook-dispatch gate), and a DIFFERENT correct replacement
(`combat.is_ending`, not `is_over_or_ending`). One fix does not close both;
recommend a dedicated sweep for other `is_over`-where-`is_ending`-was-meant
sites before fixing either, now that two have turned up independently.

---

## Tests

Files changed: `test/test_is_dead_early_returns.py` (import + module docstring
+ `TestBreakthroughGuardDeleted`, 2 new tests), `test/test_overgrowth_powers.py`
(1 assertion added to an existing test), `test/test_selectors.py` (1 new
test). No test file was deleted or renamed.

Commands run and counts:
```
py -m pytest test/test_selectors.py -q -k clamp          (RED, pre-fix)
    -> 1 failed, 10 deselected

py -m pytest test/test_selectors.py -q                   (GREEN, post-fix)
    -> 11 passed

py -m pytest test/test_is_dead_early_returns.py test/test_overgrowth_powers.py -q
    -> 167 passed

py -m pytest test/test_is_dead_early_returns.py test/test_printed_vars.py \
    test/test_card_residue_gaps2.py test/test_overgrowth_powers.py \
    test/test_selectors.py test/test_monster_tier_families.py \
    test/test_hook_order.py -q
    -> 322 passed

py -m pytest test/test_ironclad_cards.py test/test_ironclad_final_cards.py \
    test/test_choose_a_card_selector.py test/test_combat_ending_command_guards.py -q
    -> 139 passed

py audit/tools/state_machine_probes.py zero-weight        (post-fix)
    -> 82 machines / 6,560,008 transitions, 0 'No valid state found' hits

py audit/tools/state_machine_probes.py nondyadic-weights  (post-fix)
    -> 80,000 transitions, 0 'No valid state found' fall-throughs

py audit/tools/state_machine_probes.py                    (every probe, full sweep)
    -> exit 0, no traceback
```
Per protocol, the full suite was not run (controller runs it per wave); the
2 known `test_conformance_floor_state.py` failures were not touched or
counted.

---

## Findings NOT in the brief

1. **Item 4's real scope is bigger than a text mismatch** (detailed above):
   round 12 T22 fixed the *reachability* the probe hunted, not just the
   message text. The probe's own module-summary line and `zero_weight`'s
   docstring both still claimed "(C# returns branch 0; the sim raises
   RuntimeError)" / cited a dead path (`state_machine.py:182-183`, wrong file
   *and* wrong line on the current tree) — both corrected in this pass since
   they're directly adjacent to the grep fix and in the same file.

2. **`audit/tools/state_machine_probes.py`'s `raise_sites()` census
   (`_RAISE_PAIRS`, lines ~1492-1526) is separately stale**, unrelated to the
   grep fix and NOT touched (out of this item's narrow scope, and it feeds
   guard N7's site count, which is audit-record-adjacent — flagging rather
   than silently reclassifying). Two of its rows describe sim behavior that
   no longer exists on the current tree:
   - *"branch: the subtract-and-check loop falls through (step 15, G7c)"*
     is bucketed `ASYM`, claiming `sim: state_machine.py:189 returns the LAST
     branch` — false; the current code (`state_machine.py:269-273`) **raises**
     on that exact input, with the same message C# uses, which would make
     this row `SYM`, not `ASYM`.
   - *"branch: every weight is 0 (G7 clause b)"* claims `sim:
     state_machine.py:183 raises before drawing` — also false; per item 4's
     finding, this scenario no longer raises at all (matches branch 0 like
     C#).
   Both rows also cite the wrong path (`state_machine.py` instead of
   `sts2_rl/monsters/state_machine.py`). If either reclassification is
   right, `raise_sites()`'s printed summary ("guard N7 covers 5 sites; 6
   raise-behaviour sites are gaps") is currently wrong too. Recommend a
   follow-up task re-derive `_RAISE_PAIRS` against the current
   `state_machine.py` before trusting guard N7's count again.

3. **Item 5's adjacency to R1's F3** is itself the main finding of this
   report (detailed in §5) — a second, independently-found instance of the
   same `is_over`-for-`is_ending` confusion, in a different file and a
   different mechanism, needing a different replacement predicate. Recorded
   above as a queue-annotation proposal and a recommendation to sweep for
   further instances before fixing either.

---
---

## Fix pass (2026-08-01)

Response to `R11-review.md`. The review's verdict on all four code changes
(CORRECT) and on item 5's ruling (CONFIRMED, strengthened) is accepted and
NOT re-litigated. Everything below is reasoning, tests, and record/queue text.

**Everything asserted here was executed**, against the live working tree, with
`py`. Pre-edit and deliberately-wrong behaviour was reconstructed in scratch
scripts (subclass / rebound module global / patched primitive) — no working-tree
code was reverted, no git index command was run, no `audit/records/**` or
`GAP-QUEUE.md` file was edited.

## Scope corrections and disclosures, up front

1. **The footprint's `sts2_rl/monsters/noisebot.py` does not exist.** Noisebot
   is `sts2_rl/monsters/glory/fabricator.py:59` (the file also holds
   Fabricator, Stabbot, Zapbot, Guardbot). This is the same brief-path error
   class as `sts2_rl/monsters/vantom.py` → `sts2_rl/monsters/overgrowth/
   vantom.py` and `sts2_rl/state_machine.py` → `sts2_rl/monsters/
   state_machine.py`, both of which the review approved correcting. I edited
   **only the `Noisebot` class body** in that file; `git status` showed it
   unmodified by any other lane before I touched it, and the four sibling
   classes are byte-unchanged. Flagging rather than assuming: if the
   controller reads the footprint literally, item 1's code half is
   BLOCKED-ON-FOOTPRINT and the exact diff is in §1 below.
2. **`sts2_rl/monsters/base.py` is NOT in my footprint and needs an edit** —
   its `Intent.status_count` docstring makes the same false completeness claim
   the queue text did. Exact diff in §1; not applied.
3. **Index state changed under me.** My files were unstaged (` M`) when the
   review ran and are staged (`M `) now. I ran no `git add`/`commit`/`stash`;
   another lane or the controller staged the tree. Content verified intact via
   `git diff --cached --stat`.
4. **One reviewer example is off** (does not affect the finding): the review's
   sweep table has a `quest vs 1cost` row, but the 1-cost card in a
   `finesse`-based comparison is not 1-cost — `finesse.energy_cost == 0`
   (executed). A QUEST unplayable vs Finesse is a *tie* resolved by offered
   order both pre- and post-clamp, not a demotion. My pin uses `defend`
   (genuinely 1-cost) for that assertion. The review's headline count of
   "7 orderings change, 5 of them in the unnamed consumer" is unaffected —
   I re-derived the deltas independently in §2.

---

### §1 — `monster/_intent_count_lost`: the real census is 18 sites, and Noisebot is FIXED

### The census, re-derived independently

`grep -rn "new StatusIntent(" --include=*.cs` over
`c:\Users\Perry\Desktop\Slay the Spire 2` returns **18** sites. Every one,
with the count it carries and its sim counterpart:

| # | C# site | count arg | sim construction | carries `status_count`? |
|---|---|---|---|---|
| 1 | `Aeonglass.cs:102` | `WitherAmount` | `glory/aeonglass.py:79` | **yes** (pre-existing) |
| 2 | `Chomper.cs:59` | `3` | `hive/chomper.py:46` | no |
| 3 | `EyeWithTeeth.cs:39` | `3` | `overgrowth/fogmog.py:46` | no |
| 4 | `HauntedShip.cs:44` | `HauntDazed` | `underdocks/haunted_ship.py:41` | no |
| 5 | `LeafSlimeM.cs:34` | `2` | `overgrowth/slimes.py:90` | no |
| 6 | `LeafSlimeS.cs:32` | `1` | `overgrowth/slimes.py:36` | no |
| 7 | `MechaKnight.cs:83` | `4` | `glory/mecha_knight.py:43` | no |
| 8 | `Myte.cs:49` | `2` | `hive/myte.py:43` | no |
| 9 | `Noisebot.cs:45` | `2` | `glory/fabricator.py` | **yes — THIS PASS** |
| 10 | `PhrogParasite.cs:42` | `3` | `overgrowth/phrog_parasite.py:80` | no |
| 11 | `SlimedBerserker.cs:52` | `10` | `glory/slimed_berserker.py:33` | no |
| 12 | `SoulFysh.cs:113` | `BeckonMoveAmount` | `underdocks/soul_fysh.py:35` | no |
| 13 | `SoulFysh.cs:115` | `GazeMoveAmount` | `underdocks/soul_fysh.py:43` | no |
| 14 | `TestSubject.cs:201` | `BurningGrowlBurnCount` | `glory/test_subject.py:99` | **yes** (pre-existing) |
| 15 | `TheInsatiable.cs:96` | `6` | `hive/the_insatiable.py:40` | **yes** (pre-existing) |
| 16 | `TwigSlimeM.cs:37` | `1` | `overgrowth/slimes.py:124` | no |
| 17 | `Vantom.cs:119` | `3` | `overgrowth/vantom.py` | **yes** (round 13 first pass) |
| 18 | `Wriggler.cs:55` | `1` | `overgrowth/phrog_parasite.py:45` | no |

The sim has an exact **1:1** STATUS_CARD `Intent` construction for each — a
mechanical scan of `sts2_rl/monsters/**.py` for `Intent(...)` calls mentioning
`MoveType.STATUS_CARD` returns exactly 18, no more and no fewer, and every one
maps to a distinct C# row above. Executed.

**CORRECTED NUMBERS: 18 sites total. Before this pass 4 carried their count;
after it 5 do; 13 remain OPEN.** The first pass's queue text — *"All 4 known
sites now carry their count"* — was false twice over (wrong denominator, wrong
completeness), and is replaced verbatim in §8.

### The wrong-premise pin, and why it was worse than no pin

`test/test_monster_tier_families.py::test_other_status_card_intents_are_unaffected`
asserted `intent.status_count is None` for Noisebot and justified it as *"a
STATUS_CARD intent NOT among this mechanism's three sites"*. `Noisebot.cs:45`
is `new StatusIntent(2)` and `Noisebot.cs:23` is
`private const int _noiseStatusCount = 2;` — Noisebot is squarely inside the
mechanism. The pin asserted a divergence as intended behaviour, and it was
the only such pin in my footprint (I checked the other three
`TestIntentCountLost` tests: all assert a *correct* count).

### Fixed, in footprint

`sts2_rl/monsters/glory/fabricator.py`, `Noisebot` only:

```diff
+    # Noisebot.cs:23 `private const int _noiseStatusCount = 2;`. The
+    # decompiler inlined it at both use sites (the `new StatusIntent(2)` at
+    # :45 and the `new CardPileAddResult[2]` at :58), so one constant serving
+    # the intent and the two Dazed adds is a faithful de-inlining.
+    _NOISE_STATUS_COUNT = 2
+
     def build_machine(self) -> MonsterMoveStateMachine:
-        noise = MoveState("NOISE_MOVE", self._noise, Intent(MoveType.STATUS_CARD))
+        noise = MoveState("NOISE_MOVE", self._noise,
+                          Intent(MoveType.STATUS_CARD,
+                                 status_count=self._NOISE_STATUS_COUNT))
```

`NoiseMove` (`Noisebot.cs:51-71`) adds exactly two Dazed — one to Discard
(`:61`), one to Draw at a random position (`:64`) — so 2 is also the count the
player is actually shown.

### Tests: the pin inverted, plus a census ledger

* `test_noisebot_noise_carries_its_status_count` (replaces the wrong-premise
  test): asserts `status_count == 2`.
* `test_status_intent_count_census_is_still_five_of_eighteen` (new): scans the
  sim's monster package, asserts the total is 18, and asserts the DONE and
  OPEN sets by file. Framed explicitly as a ledger of open work, **not** as a
  claim that the open sites are correct — so it does not repeat the mistake it
  was written to catch. Keyed by file, not `file:line`, deliberately: a
  line-keyed ledger breaks on any concurrent lane's unrelated edit (it broke
  twice while I wrote it) and a ledger that breaks spuriously gets deleted
  rather than updated.

**RED evidence** (before the Noisebot fix, both tests, real pytest run):

```
py -m pytest test/test_monster_tier_families.py -q -k "noisebot or census"
  FAILED ...::test_noisebot_noise_carries_its_status_count
  FAILED ...::test_status_intent_count_census_is_still_five_of_eighteen
     AssertionError: at index 1 diff: 'glory/test_subject.py' != 'glory/fabricator.py'
  2 failed, 14 deselected
```

The Noisebot RED is deterministic by construction, not by luck:
`Intent.status_count` defaults to `None` (`monsters/base.py:74`) and the
pre-edit call passed no kwarg, so `== 2` was necessarily false.
GREEN after the fix: `16 passed`.

### Also corrected, in footprint

`sts2_rl/monsters/overgrowth/vantom.py`'s inline comment called this "the 4th
site of the **closed** monster/_intent_count_lost mechanism". Replaced with the
true census (18 sites, 5 ported, 13 open) and a pointer to the ledger test.

### BLOCKED-ON-FOOTPRINT — `sts2_rl/monsters/base.py`

The same false claim lives in the `Intent` dataclass docstring
(`monsters/base.py:61-67`), which is outside my footprint and is being edited
by another lane this wave (`MM` in `git status`). Exact diff, not applied:

```diff
     For a StatusIntent (move_type or a member of `also` is STATUS_CARD):
         status_count carries the C# `StatusIntent.CardCount` — how many
-        status cards are about to land. Every StatusIntent site now sets it;
-        every other Intent construction leaves it at its default (None), and
+        status cards are about to land. FIVE of the spec's 18
+        `new StatusIntent(` sites set it; the other 13 still drop it and are
+        open work under monster/_intent_count_lost (see
+        test_monster_tier_families.py's census ledger). Every non-StatusIntent
+        construction leaves it at its default (None), and
         the observation encoder (full_env.py:571) still reads only the
         STATUS_CARD flag bit, not this value — the count is carried but
         unencoded (a checkpoint-tier concern, not this mechanism's).
```

---

### §2 — `_cost` has THREE consumers: enumerated, decided, pinned

### The enumeration (all three, with executed deltas)

`_cost` is read at three sites in `sts2_rl/selectors.py`. Post-edit line
numbers (the docstring I added shifted them):

| # | site | purpose | leading sort key ahead of `_cost` | clamp delta |
|---|---|---|---|---|
| 1 | `:121` | `"upgrade"` (negated) | `not is_upgradable` | **none — provably inert** |
| 2 | `:125` | `"to_draw_top"` | `card_type is not ATTACK` | **LIVE** (the intended fix) |
| 3 | `:146` | `"choose_a_card"`, `"choose_a_card_optional"` | `_is_junk` | **real but UNREACHABLE today** |

The first pass named only #1 and #2, and argued safety only for #1. #3 is the
"third consumer nobody enumerated".

**Consumer 1 — inert, and for a stronger reason than the first pass gave.**
Executed over the whole card registry: **29** cards have `energy_cost < 0`;
the set of distinct negative values is exactly `{-1}`; their types are
`{CURSE: 16, QUEST: 3, STATUS: 10}`; **none is `is_upgradable`** and none is
`energy_cost_x`. So the `not is_upgradable` key sorts every one of them behind
any upgradable candidate before `_cost` is consulted, and on an all-unplayable
screen every `_cost` is *equal* under both the old and the new body, so the
offered-order tiebreak decides identically. Executed both arms:
`[<unplayable>, strike] -> strike` and `all-unplayable -> index 0`, pre and
post, no change.

**Consumer 2 — live, and it is what the clamp is for.** Both call sites read a
real pile that holds junk: Thinking Ahead reads the **hand**
(`cards/colorless_skills.py:845`) and Headbutt reads the **discard pile**
(`cards/headbutt.py:43`). Executed: `[thinking_ahead, wound] -> wound` pre-clamp,
`-> thinking_ahead` post-clamp; same for `dazed`, `regret`, and each of the
three QUEST cards.

**Consumer 3 — a real ordering change for exactly 3 cards, unreachable today.**
`_is_junk` is `card_type in (STATUS, CURSE)`, so the 10 STATUS and 16 CURSE
unplayables are masked by the leading key and the clamp cannot move them. The
**3 QUEST** unplayables are not junk, so they reach `_cost`. Executed:

```
purpose                 candidates                    pre-clamp        post-clamp
choose_a_card           [thinking_ahead, lantern_key] lantern_key   -> thinking_ahead  CHANGED
choose_a_card_optional  [thinking_ahead, lantern_key] lantern_key   -> thinking_ahead  CHANGED
   ... identically for byrdonis_egg and spoils_map (6 orderings in total)
```

**But it cannot be reached.** All three `choose_a_card*` call sites build their
candidates by GENERATING cards from a pool — Toolbox (`relics/toolbox.py:46`,
`COLORLESS_POOL`), Choice's Paradox (`relics/choices_paradox.py:56`,
`combat.card_pool`) and the four generator potions (`potions.py:1408`, filtered
`combat.card_pool` / `COLORLESS_POOL`). Executed: **no** negative-cost card is
a member of `COLORLESS_POOL` (53) or of any character's `card_pool` (only
Ironclad's is populated, 85; the other four characters are unported stat rows).
The 16 curses are in `CURSE_POOL`, which no `choose_a_card` site reads.

### The decision — KEEP THE CLAMP SHARED, do not narrow to `to_draw_top`

The C# is the judge on the one question it can answer here, and it answers it
against narrowing: **`-1` is not a price, it is a sentinel.**
`CardEnergyCost.GetWithModifiers` short-circuits `if (_base < 0) return num;`
(`CardEnergyCost.cs:100-103`) *before* any modifier is consulted, so the value
is immune to every cost effect — it is a flag meaning "cannot be played", and
`cards/base.py:433-434` mirrors that exactly. A helper named `_cost` that
returns it as a *number* is wrong for every consumer, not just the one where
the wrongness currently shows. Narrowing the clamp to the `to_draw_top` branch
would leave two consumers reading a sentinel as an integer and would need the
inertness argument to hold forever at consumer 1 and the pool argument forever
at consumer 3 — two standing obligations bought for nothing, since the clamp
changes no reachable behaviour at either. Kept shared.

This is a sim-only RL heuristic with no C# analogue (mid-resolution
`CardSelectCmd` screens the game hands to a human) — a quality change, not a
fidelity change. The review's assessment of that framing is confirmed.

### Pinned

* `test_no_unplayable_card_is_upgradable` — the enumeration behind consumer 1's
  inertness, over the whole registry (29 cards, `{-1}`, none upgradable, none
  X-cost). Fires if a future unplayable becomes upgradable.
* `test_choose_a_card_clamp_reaches_the_quest_unplayables_too` — consumer 3's
  delta, both offer orders, for all three QUEST cards.
* `test_choose_a_card_screens_cannot_offer_an_unplayable_card_today` — the
  dormancy witness for consumer 3. Fires if a pool ever gains an unplayable.
* `selectors.py`'s `_cost` comment is replaced by a docstring that enumerates
  all three consumers and states the delta at each, so the next reader does not
  have to re-derive it.

### Design residual, flagged not fixed (the review's point stands)

Because the clamp is a tie, `to_draw_top` still puts a **Wound on top of the
draw pile whenever the Wound is offered first** — for Headbutt, strictly the
worst available pick. The shape that fixes it is the one `choose_a_card`
already uses:

```diff
-            key=lambda p: (p[1].card_type is not CardType.ATTACK, _cost(p[1]), p[0])
+            key=lambda p: (p[1].card_type is not CardType.ATTACK,
+                           _is_junk(p[1]), _cost(p[1]), p[0])
```

**Not applied, on purpose.** It is not a fidelity question (there is no C# to
be faithful to), it changes what the agent actually does in live combat every
time Headbutt or Thinking Ahead is played, and it is outside both the brief's
prescription and the review's ask. It wants a controller decision, not a lane's.
The clamp as shipped is a strict improvement on the round-12 body in every case
(junk can no longer win from *either* order; it can now only win from the
first), so nothing is blocked on it.

---

### §3 — the item-3 test now fails against the wrong fix

The review is right: `test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero`
asserted one offer order, so it pinned "a Wound no longer beats Thinking Ahead"
and passed under a "rank unplayables LAST" body — a demotion, not the tie its
own name claims.

Rewritten with both orders, and both assertions are load-bearing against
*different* wrong answers:

```python
assert scripted_card_selector("to_draw_top", [thinking_ahead, wound], 1) == [thinking_ahead]
assert scripted_card_selector("to_draw_top", [wound, thinking_ahead], 1) == [wound]
```

**RED proof, against reconstructed-wrong bodies, no production code reverted.**
`selectors._cost` is rebound in a scratch process only (the sort lambdas read it
as a module global, so the rebind takes effect); the three bodies are the
round-12 raw `-1`, the review's deliberately-wrong `98 if energy_cost < 0`, and
the real `max(0, ...)`:

```
--- _cost = round-12 raw -1 ---
    FAIL  test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero   <- test_selectors.py:78
    FAIL  test_choose_a_card_clamp_reaches_the_quest_unplayables_too   <- test_selectors.py:128
    PASS  test_no_unplayable_card_is_upgradable
    PASS  test_choose_a_card_screens_cannot_offer_an_unplayable_card_today
--- _cost = wrong 'rank last' ---
    FAIL  test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero   <- test_selectors.py:81
    FAIL  test_choose_a_card_clamp_reaches_the_quest_unplayables_too   <- test_selectors.py:130
    PASS  test_no_unplayable_card_is_upgradable
    PASS  test_choose_a_card_screens_cannot_offer_an_unplayable_card_today
--- _cost = current max(0,..) ---
    PASS  (all four)
```

Note the failing LINE differs between the two wrong bodies (78 vs 81, 128 vs
130): each wrong body trips the assertion written for it. That is the
difference between a test that pins a tie and one that pins an inequality. The
three pre-existing selector tests (`to_draw_top_picks_cheapest_attack`,
`upgrade_picks_highest_cost`, `upgrade_prefers_upgradable`) pass under all
three bodies, confirming they were never load-bearing here.

---

### §4 — the probe: the old grep was a live FALSE POSITIVE, and pass 2 was misfiling hits

### Correction: `"No valid branch"` was not dead

The first pass said the old substring *"is not a substring of the current
message, so a genuine hit was silently reclassified as an 'other error'"*.
True but incomplete, and the incompleteness matters. `"No valid branch"` still
matches a **live raise on the current tree**:
`sts2_rl/monsters/state_machine.py:324`,
`RuntimeError(f"No valid branch in ConditionalBranchState {self.id}")` — a
different dispatcher and a different asymmetry question. So the old probe had
a live false-positive source as well as a miss. Executed:

```
message                                        OLD grep counted it?   correct bucket
No valid state found in RandomBranchState RAND!        False           rand  (the target)
No valid branch in ConditionalBranchState COND         True            cond  (WRONG BUCKET)
no valid state found: SOME_ID   (state_machine.py:432) False           other
```

Scale of the false positive, executed: forcing every `ConditionalBranchState`
to fall through produces **13 machines** (BowlbugRock, Exoskeleton, Fabricator,
FrogKnight, KnowledgeDemon, LagavulinMatriarch, LivingShield, Myte, Ovicopter,
PhantasmalGardener, Queen, SlumberingBeetle, Toadpole) that the old probe would
have printed under a headline reading `(total weight 0)`.

### Fixed: the two raises are now classified separately

New `_classify_machine_raise(exc) -> ('rand' | 'cond' | 'other', text)`, used at
**every** classification point in both probes. Both substrings now name their
state class (`"No valid state found in RandomBranchState"` /
`"No valid branch in ConditionalBranchState"`), which also keeps
`state_machine.py:432`'s lowercase `f"no valid state found: {next_id}"` — a
third, unrelated raise one capitalisation away from the first — out of the
bucket by construction rather than by case-sensitivity luck (the review's
"related near-miss"). Each bucket prints under its own headline, with the
conditional one labelled `[different mechanism -- not a zero-weight hit]`.

### Fixed: the pass-2 hit misclassification (review finding N3)

Pass 2 wrapped `Encounter`/`CombatState` construction in its own `try` and
appended any `RuntimeError` to `live_bad` ("dormancy unproven for these"). But
construction *drives the machine* — it rolls the opening move — so a machine
that falls through on its first roll was reported as "couldn't fuzz it" rather
than as a hit. Both construction sites are now classified with the same helper.
A second hole in the same block: the **per-walk** rebuild
(`for w in range(walks): ... CombatState(...)`) was not wrapped at all, so a
construction fall-through on any seed > 0 crashed the whole probe. Also wrapped.

**Executed witness**, `_weighted_roll` patched from outside the module to
overshoot (forcing the fall-through), running the REAL `zero_weight`:

```
                                    review's run (pre-fix)   this run (post-fix)
RandomBranchState fall-through hits          13                    15
machines STILL not fuzzed                     3                     1
   of those, carrying the RandomBranch text   2                     0
TwoTailedRat  classified as                'not fuzzed'           HIT
Fabricator    classified as                'not fuzzed'           HIT
OLD substring found in the hit messages     0 of 13               0 of 15
```

The 2 rows moved are exactly the 2 the review named, and **`TwoTailedRat` is
the probe's own documented G7-clause-c trigger** — pass 2 exists because the
first version skipped it, and this hole made pass 2 blind on it anyway. The one
remaining "not fuzzed" row is a genuine non-machine failure (`_Cultist`:
`AttributeError: no attribute 'dark_strike_dmg'`), correctly bucketed.

Unforced runs are unchanged and reproduce the first pass exactly: `zero-weight`
82 machines / 6,560,008 transitions / 0 hits / 0 conditional hits / 1 fractional
vector (`Fogmog.BRANCH=[0.4, 0.6]`); `nondyadic-weights` 80,000 transitions / 0.
Full sweep (`py audit/tools/state_machine_probes.py`, no argument) exits 0.

Honest scope, now stated in the probe's own docstring: `nondyadic_weights`'s
population is a single machine (TwoTailedRat), so its corrected classification
is exercised only that far; the "it really fires" evidence covers `zero_weight`.

---

### §5 — `_RAISE_PAIRS`: refreshed by execution. SIX rows were stale, not two, and all 12 citations were.

The first pass flagged 2 stale rows; the review found 2 more and said all 12 sim
line citations were stale. Re-deriving **every** row by execution against the
current `state_machine.py` (scratch script, each row's input constructed and the
result observed) found the damage is wider still: **six rows** described sim
behaviour that no longer exists, and a **seventh** had the wrong bucket *and* a
misreading of what the C# guard checks.

| row | old bucket | old sim claim | EXECUTED reality | new bucket |
|---|---|---|---|---|
| RollMove landed on a non-move | SYM `:252` | — | raises, same text | SYM `:380-381` |
| "no initial state to fall back to" `MMSM.cs:58` | SYM `:271` | — | **`:56-59` guards the CURRENT state, not an initial-state fallback.** Sim has no deliberate guard; a None surfaces as `AttributeError` from attribute access (`:373` in the ctor, `:424` in `_find_next_move_state`) | **ONE-SIDED-GUARD** |
| unknown state id | SYM `:271` | — | raises, C#'s text verbatim | SYM `:431-432` |
| MoveState: no follow-up | SYM `:138` | — | raises | SYM `:196` |
| conditional: no branch true | SYM `:232` | — | raises | SYM `:324` |
| branch loop falls through (G7c) | **ASYM** | `:189 returns the LAST branch` | **raises**, `RandomBranchState.cs:127`'s text verbatim | **SYM** `:273` |
| every weight is 0 (G7b) | **ASYM** | `:183 raises before drawing` | **no raise** — returns branch 0, like C# | **SYM-NO-RAISE** `:265-273` |
| CanRepeatXTimes, maxTimes == 0 (G7a) | **ASYM** | `:168-169 raises ValueError` | **no raise** — `max_times=0` is legal | **SYM-NO-RAISE** `:239-240` |
| duplicate state id (G8a) | **ASYM** | `:87 silently overwrites` | **raises ValueError** | **SYM** `:130-134` |
| machine setter set twice (G8b) | **ASYM** | `no setter; silently rebinds` | **there IS a property setter and it raises**; `reset_state_machine` (`:497-505`) mirrors `MonsterModel.ResetStateMachine` | **SYM** `:482-495` |
| AddBranch #1 given CanRepeatXTimes (G8c) | ONE-SIDED-GUARD | `no analogue; happens to raise for a DIFFERENT predicate (max_times <= 0)` | raises on **exactly C#'s predicate** (CanRepeatXTimes with no maxRepeats supplied). Doubly wrong: same predicate, and `max_times <= 0` is not what the code tests | **SYM** `:239-240` |
| null weight lambda | DEAD | — | DEAD stands (default is in the signature) | DEAD |

Two rows (G7b, G7a) now have **neither side raising**, so they must not inflate
guard N7's count — N7 is about raise *type*. Added a `SYM-NO-RAISE` bucket that
records them as closed asymmetries rather than deleting the history.

**The printed conclusion was wrong in both numbers.** Before:
`=> guard N7 covers 5 sites; 6 raise-behaviour sites are gaps (G7 x3, G8 x3)`.
After (executed): `=> guard N7 covers 8 sites; 1 raise-behaviour site(s)
remain gaps and are NOT N7's; 2 former asymmetries are now closed on both
sides.` The single remaining gap is the null-current-state guard.

Every sim citation now matches the probe's own printed raise list
(`state_machine.py raise at [96, 120, 131, 196, 240, 273, 324, 381, 432, 491,
508]`); none of the old ones did. Each row also records the text it replaced, so
the correction is auditable.

New finding while re-deriving: `add_branch(state, None)` is accepted and stores
`None` verbatim, so an explicit null weight would `TypeError` at roll time
rather than at build time. Unreached today (no caller passes it) — recorded in
the DEAD row, not fixed.

---

### §6 — the item-5 correction must touch THREE fields, not one

The first pass's proposal named only `seam/creature_card_cmds` step 19. Read
directly from `audit/records/seam/creature_card_cmds.json` (read-only), the
identical false claim lives in three places. **All three carry the same
falsehood and must be corrected together, or it survives verbatim one field
away.**

**(a) `steps[20]`** (`"what"` begins `"19."`), `verdict: faithful`. Its
`issue` ends:

> *"... The only early return left is `combat.is_over and target.side !=
> 'player'` (sts2_rl/cmds.py), **which is CreatureCmd.cs:693-696's `IsEnding &&
> !IsPlayer` and nothing more.**"*

**(b) `guards[3]`** (G4, "CreatureCmd.heal refuses to heal a dead creature"),
`verdict: faithful`. Its `issue` says:

> *"... its only guard is now `combat.is_over and target.side != 'player'`
> (sts2_rl/cmds.py), **which is exactly CreatureCmd.cs:693-696's `IsEnding &&
> !IsPlayer`**."*

**(c) `guards[24]`** (G14, the combat-over/IsEnding guard family),
`verdict: faithful`. Its `issue` asserts of the whole family:

> *"... each carry the guard their C# counterpart carries, **at the strength
> their C# counterpart carries it** (`IsOverOrEnding` vs `IsEnding` vs
> `!IsInProgress`)."*

That last is false for precisely one member — `CreatureCmd.heal`, which carries
`!IsInProgress` where C# carries `IsEnding`. The rest of G14's closure (the
`BlockCmd`/`discard_hand`/shuffle/`afflict`/`CardPileCmd` members, the three
moved tests, `StockPower.ShouldStopCombatFromEnding`) is not challenged here —
only the "at the strength" clause, and only for `heal`. **Recommend NARROWING
G14 rather than reopening it**: it is right about its own members bar one.

The correction text for all three is in §8.

Line-citation hygiene, per the review: the heal guard is at `sts2_rl/cmds.py`
**:544** in the working tree (it was `:501` at HEAD and `:520-523` in the first
pass's text) and `combat.is_over` is at `combat.py:1606-1607`. Concurrent-lane
churn — so the §8 close notes cite by **symbol name**, not line.

---

### §7 — item 5's ruling: recommendation updated, grep corrected

Item 5's ruling itself (step 19's equivalence claim is FALSE; `combat.is_over`
mirrors `!IsInProgress`; the correct replacement is `combat.is_ending` and NOT
`is_over_or_ending`; F3 is adjacent, not identical; one fix cannot close both)
stands as written and is not re-argued. The review's two-way execution witness
strengthens it: with all enemies dead but combat not torn down,
`CreatureCmd.heal(enemy, 7)` returns 7 where C#'s `IsEnding && !IsPlayer`
refuses; with `phase == COMBAT_OVER` it returns 0 where C# permits. The sim's
guard is the **complementary** window — wrong in both directions, not a
narrower or looser version.

**OVERTURNED: "sweep before fixing either".** The first pass recommended
holding both fixes for a 49-site sweep. That is the failure mode where neither
lands. Corrected recommendation:

1. **Fix the heal guard now** (`combat.is_over` → `combat.is_ending` in
   `CreatureCmd.heal`). One line, self-contained, its correct predicate is
   settled, and it has an executed two-way witness and a trivially writable pin.
2. **Run the sweep as its own task.** Still worth a dedicated item — two
   independent finds in one wave, and the corrected grep below returns **56**
   hits across `sts2_rl/`.
3. **Let F3 land with the sweep.** F3 genuinely is a 73-dispatcher policy call
   and benefits from seeing every site at once.

**CORRECTED GREP.** The first pass proposed
`combat.is_over` / `hooks.combat.is_over` / `phase == Phase.COMBAT_OVER`.
Executed against the heal guard's own line — `getattr(combat, "is_over", False)`
at `cmds.py:544` — that pattern returns **0 matches**. It would have missed the
very site that motivated it, reproducing exactly the blind spot that let the
site survive. Use:

```
grep -rnE "\.is_over\b|\.is_ending\b|\.is_over_or_ending\b|combat_is_over|Phase\.COMBAT_OVER|getattr\([^,]+, *\"(is_over|is_ending|is_over_or_ending)\"" sts2_rl/ --include=*.py
```

Executed: **56 hits** (vs 29 for the first pass's pattern and 50 for the
review's narrower one), and it DOES match `cmds.py:544` — verified line by line.
Four sites use the `getattr` form and only this pattern sees them:
`cmds.py:544` (the heal guard), `cmds.py:1244`, `cmds.py:1419`
(`_refuses_combat_add`), `hooks.py:1591`.

---

### §8 — FINAL record-close and queue-annotation text

Everything below is written to be applied as-is and is true as written on the
2026-08-01 working tree.

### Record closes

**`audit/records/card/breakthrough.json`** — add a third guard entry:
- `what`: *"the sim returned early on `if ctx.player.is_dead` between the HP
  loss and the AoE loop (breakthrough.py) — now deleted"*
- `verdict`: `faithful`
- `issue`: *"Closed 2026-08-01 (round 13, R11). DELETED — `Breakthrough.OnPlay`
  (Breakthrough.cs:24-31) runs self-damage then the AoE attack with no
  `IsDead`/`IsEnding` check between them and NO tail after the attack at all,
  so the sim's guard had no counterpart. Deleting it is behaviour-neutral
  today because the per-enemy `DamageCmd.deal(..., dealer=ctx.player, ...)`
  the loop reaches self-gates on `dealer.is_dead` as its first statement,
  ahead of every hook — mirroring `AttackCommand.Execute`'s `Attacker.IsDead`
  bail (AttackCommand.cs:528-531), which for Breakthrough (`_hitCount == 1`)
  refuses the whole opponent batch as one unit. Verified by differential
  execution against a reconstructed pre-edit subclass over 48 configurations
  (hp x seed x encounter size x first-enemy-dead): zero differences in HP,
  piles, powers, energy, phase, result, or the full ordered HookSystem
  dispatch trace. CAVEAT, recorded because the argument is hostage to another
  file: this deletion's correctness rests entirely on `DamageCmd.deal`'s
  `dealer.is_dead` bail in sts2_rl/cmds.py. If that bail moves, weakens, or
  is reordered behind a hook, Breakthrough regresses silently and the tests in
  this record will NOT catch it — they assert outcomes downstream of the bail.
  Same family and reasoning as card/blood_wall, card/brand and
  card/hemokinesis under card/_is_dead_early_return (Task 27). Pins:
  test/test_is_dead_early_returns.py::TestBreakthroughGuardDeleted (2 tests),
  which are honestly non-RED-able: the change is provably inert."*
- The record's top-level `verdict` should stay `gap` — the enemy-filter
  `is_dead`-vs-`is_gone` guard is untouched and unre-derived by this lane.

**`audit/records/monster/vantom.json`**, the DISMEMBER guard (stays
`faithful`) — append:
- *"Refreshed 2026-08-01 (round 13, R11): `status_count=3` is now set on the
  DISMEMBER Intent (Vantom.cs:119 `new StatusIntent(3)`, `_dismemberWounds`
  at :34), closing this guard's own open note. Two corrections to that note:
  (a) its 'Intent has no status-count field' clause is stale — the field
  exists (monsters/base.py); (b) it named monster/_intent_count_lost as a
  three-or-four-site mechanism, which is wrong. The spec has EIGHTEEN
  `new StatusIntent(` sites; five are ported and thirteen are open. The
  mechanism is NOT closed. Pin:
  test_overgrowth_powers.py::TestVantomDismember::
  test_dismember_telegraphs_the_status_intent_too."*

**`audit/records/seam/creature_card_cmds.json`** — the SAME correction text
appended to all three fields identified in §6 (`steps[20]`, `guards[3]`,
`guards[24]`). Verdicts on `steps[20]` and `guards[3]` should move
`faithful` → `gap`; `guards[24]` should be **NARROWED**, not reopened:
- *"CORRECTED 2026-08-01 (round 13, R11). The equivalence this closure rests
  on is FALSE, not imprecise: `combat.is_over` is `phase ==
  Phase.COMBAT_OVER`, which mirrors C#'s `!IsInProgress`, NOT `IsEnding`.
  `CombatManager.IsEnding` (CombatManager.cs:180-202) OPENS with
  `if (!IsInProgress) return false;`, so it is true exactly DURING the ending
  sequence and false again the instant combat is torn down — the
  COMPLEMENTARY window to the sim's guard. `CreatureCmd.Heal`
  (CreatureCmd.cs:691-696) gates on the bare `IsEnding`. Executed witness,
  both directions: with every enemy dead but combat not torn down (phase
  PLAYER_TURN, is_over False, is_ending True) `CreatureCmd.heal(enemy, 7)`
  returns 7 where C# refuses; with phase COMBAT_OVER (is_over True, is_ending
  False) it returns 0 where C# permits. So a non-player heal reached in the
  window between the killing blow and teardown — an on-death effect healing a
  surviving ally, Illusion's REVIVE, Adaptable's respawn, Reattach — is
  wrongly ALLOWED by the sim. The correct predicate for this site is
  `combat.is_ending`, and specifically NOT `combat.is_over_or_ending`, which
  would over-guard the post-teardown heal C# permits. This is ADJACENT to,
  not identical with, seam/hook_dispatch's F3: F3's site is
  `HookSystem.combat_is_over`, read by `_each` for the 73 gated dispatch
  names, whose C# counterpart is `IterateCombatHookListeners`' `IsOverOrEnding`
  (Hook.cs:53-63). `CreatureCmd.heal` is not a hook dispatch, is not in
  `_COMBAT_GATED_HOOKS`, and never reaches that gate — it reads `combat.is_over`
  directly. Same root confusion, two different sites, two DIFFERENT correct
  replacements; one fix cannot close both. For guards/24 (G14) specifically:
  only the 'at the strength their C# counterpart carries it' clause is wrong,
  and only for `heal` — the other members of the family are not challenged,
  so this is a NARROWING, not a reopen."*

**`audit/tools/state_machine_probes.py`** carries no record of its own; §5's
`_RAISE_PAIRS` refresh feeds guard N7's count and the controller should treat
"guard N7 covers 8 sites; 1 gap; 2 closed asymmetries" as superseding the old
"5 sites / 6 gaps (G7 x3, G8 x3)" wherever a record quotes it.

### Queue annotations (GAP-QUEUE.md style, terse)

**`card/_is_dead_early_return`** — Breakthrough's top-level guard deleted
2026-08-01 (round 13 R11), same reasoning as Blood Wall/Brand/Hemokinesis:
`DamageCmd.deal`'s `dealer.is_dead` bail already refuses every enemy once the
self-damage kills the player; verified by differential execution over 48
configurations incl. the full hook trace. The mid-loop `break` stays
`faithful`, untouched. NOTE: the mechanism's site list says 6 —
`cards/thunderclap.py` is a 7th with the same top-level shape and, unlike
Breakthrough, a real non-damage tail (`PowerCmd.apply` of Vulnerable) that the
Breakthrough argument does NOT cover; it needs `PowerCmd.apply`'s own bail
argued separately. Found by the R11 review, not fixed (out of footprint).

**`monster/_intent_count_lost`** — NOT closed. The spec has **18**
`new StatusIntent(` sites, not 4: Aeonglass:102, Chomper:59, EyeWithTeeth:39,
HauntedShip:44, LeafSlimeM:34, LeafSlimeS:32, MechaKnight:83, Myte:49,
Noisebot:45, PhrogParasite:42, SlimedBerserker:52, SoulFysh:113, SoulFysh:115,
TestSubject:201, TheInsatiable:96, TwigSlimeM:37, Vantom:119, Wriggler:55. The
sim has an exact 1:1 construction for each. **5 ported** (Aeonglass,
TestSubject, TheInsatiable, Vantom, and Noisebot as of 2026-08-01 round 13
R11), **13 OPEN** — chomper, fogmog(EyeWithTeeth), haunted_ship, mecha_knight,
myte, phrog_parasite x2 (Wriggler + PhrogParasite), slimed_berserker,
slimes.py x3 (LeafSlimeS/LeafSlimeM/TwigSlimeM), soul_fysh x2. The round-13
first pass recorded "All 4 known sites now carry their count" — a false
completeness claim on a wrong denominator; do not carry it forward. It also
left `test_monster_tier_families.py::test_other_status_card_intents_are_
unaffected` pinning Noisebot's MISSING count as intended behaviour while
`Noisebot.cs:45` is `StatusIntent(2)`; that test is now inverted
(`test_noisebot_noise_carries_its_status_count`) and a census ledger
(`test_status_intent_count_census_is_still_five_of_eighteen`) goes RED when
any remaining site is ported. The encoder still reads only the STATUS_CARD flag
bit (full_env.py:571), unchanged. `sts2_rl/monsters/base.py`'s `Intent`
docstring still says "Every StatusIntent site now sets it" — false, out of
R11's footprint, diff supplied in R11-report.md §1.

**`card/_unplayable_cost`** (or wherever `selectors.py`'s finding lives) —
`scripted_card_selector`'s `_cost()` now clamps `card.energy_cost` to
`max(0, ...)`, closed 2026-08-01 (round 13 R11): the canonical `-1` is a
SENTINEL (`CardEnergyCost.cs:100-103` short-circuits before any modifier), not
a price, so an unplayable card now TIES a genuinely free 0-cost card instead of
out-ranking it. `_cost` has **three** consumers, not the two first recorded:
`"upgrade"` (inert — 0 of the 29 unplayable cards is upgradable, so the leading
`not is_upgradable` key always decides first), `"to_draw_top"` (the live delta;
both call sites read real piles — Thinking Ahead the hand, Headbutt the
discard), and `"choose_a_card"`/`"choose_a_card_optional"` (a real ordering
change for the 3 QUEST unplayables, which `_is_junk` does not cover, but
unreachable today: all three call sites generate candidates from
COLORLESS_POOL / a character `card_pool` and no unplayable card is in any
pool). Clamp deliberately kept SHARED rather than narrowed to `to_draw_top`.
Pins: test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero (both offer
orders — the one-order version passed under a "rank unplayables last" body),
test_no_unplayable_card_is_upgradable,
test_choose_a_card_clamp_reaches_the_quest_unplayables_too,
test_choose_a_card_screens_cannot_offer_an_unplayable_card_today. RESIDUAL,
not fixed: because the clamp is a tie, `to_draw_top` still puts a Wound on the
draw pile when the Wound is offered FIRST; the fix is to add `_is_junk` ahead
of `_cost` in that branch, but it changes live combat policy with no C# to
judge it, so it wants a controller decision.

**`monster_state_machine` tooling** (`audit/tools/state_machine_probes.py`) —
fixed 2026-08-01 (round 13 R11). Three defects, all in the tool, none in the
engine: (1) the `zero_weight`/`nondyadic_weights` grep was the pre-T22 string
`"No valid branch"`, which does NOT match `RandomBranchState`'s current raise
(state_machine.py:273, verbatim `RandomBranchState.cs:127`) but DOES still
match `ConditionalBranchState`'s (state_machine.py:324) — a live FALSE
POSITIVE worth 13 machines under a forced fall-through, not merely a dead
grep. The two raises are now classified separately and printed under separate
headlines. (2) `zero_weight`'s pass-2 setup path filed a fall-through raised
during `Encounter`/`CombatState` CONSTRUCTION under "machines still not
fuzzed" instead of counting it as a hit — which hid TwoTailedRat, the probe's
own named G7-clause-c trigger, i.e. pass 2 was blind on the case pass 2 was
added for. Forced-fall-through run: hits 13 -> 15, "still not fuzzed" 3 -> 1.
(3) the per-walk `CombatState` rebuild was unguarded and would crash the probe
outright on a seed > 0 fall-through. Unforced runs unchanged (82 machines,
6,560,008 transitions, 0 hits; 80,000 transitions, 0). The ENGINE needs no
change and `monster_state_machine/G7`'s closure (2026-07-30) is still accurate.

**`monster_state_machine` guard N7 recount** — `_RAISE_PAIRS` refreshed by
execution 2026-08-01 (round 13 R11). It was far staler than the first pass's
"2 rows" or the review's "4": **6 of 12 rows** described sim behaviour that no
longer exists (all 6 asserted an asymmetry rounds 12-13 have since closed — the
G7c fall-through, the all-zero vector, maxTimes==0, duplicate state ids, the
machine setter, and AddBranch overload #1), a **7th** had the wrong bucket and
misread its own C# citation (`MonsterMoveStateMachine.cs:56-59` guards the
CURRENT state, not "no initial state to fall back to"), and **all 12** sim line
citations pointed at lines holding something else. Corrected count:
**guard N7 covers 8 sites; 1 raise-behaviour site remains a gap** (the
null-current-state guard, which the sim lacks and surfaces as an AttributeError);
**2 former asymmetries are now closed on both sides** and get a new
`SYM-NO-RAISE` bucket so they cannot inflate N7. The old printout — "guard N7
covers 5 sites; 6 raise-behaviour sites are gaps (G7 x3, G8 x3)" — is wrong in
both numbers and must not be quoted. New minor finding: `add_branch(state,
None)` is accepted and stored verbatim, so an explicit null weight would
TypeError at roll time rather than build time (unreached; recorded, not fixed).

**`creature_card_cmds` step 19 / G4 / G14** (report only, round 13 R11) — the
closure's equivalence claim ("sim `combat.is_over` IS C#'s `IsEnding &&
!IsPlayer`") is FALSE, not imprecise, and it lives in **three** fields of
`seam/creature_card_cmds.json`, not one: `steps[20]` (step 19), `guards[3]`
(G4) and `guards[24]` (G14's "at the strength their C# counterpart carries it"
clause). `combat.is_over` mirrors `!IsInProgress`; C#'s heal guard is the bare
`IsEnding`, whose own leading clause makes it the COMPLEMENTARY window —
executed witness shows the sim wrong in BOTH directions. Same root confusion as
`seam/hook_dispatch`'s F3 (`HookSystem.combat_is_over` vs `IsOverOrEnding`) but
an ADJACENT, separate defect: different file, different mechanism (a
hand-written command guard, not a hook-dispatch gate), and a DIFFERENT correct
replacement (`combat.is_ending`, NOT `is_over_or_ending`, which would
over-guard the post-teardown heal C# permits). One fix does not close both.
Correct `steps[20]`/`guards[3]` to `gap`; NARROW `guards[24]` (only the `heal`
member is wrong). SEQUENCING (revised — the first pass's "sweep before fixing
either" is withdrawn): fix the heal guard NOW (one line, settled predicate,
executed witness), run the `is_over` sweep as its own task, and let F3 land
with the sweep since F3 is genuinely a 73-dispatcher policy call. The sweep
grep MUST include the `getattr` form — the first pass's proposed pattern
returns 0 matches on the heal guard's own line (`getattr(combat, "is_over",
False)`, cmds.py:544). Use:
`grep -rnE "\.is_over\b|\.is_ending\b|\.is_over_or_ending\b|combat_is_over|Phase\.COMBAT_OVER|getattr\([^,]+, *\"(is_over|is_ending|is_over_or_ending)\"" sts2_rl/ --include=*.py`
— 56 hits (the first pass's pattern found 29 and missed its own site).

---

### §9 — Tests (fix pass)

Files changed this pass: `test/test_selectors.py` (1 test rewritten, 3 added),
`test/test_monster_tier_families.py` (1 wrong-premise test replaced, 1 census
ledger added, module docstring corrected). Production files changed:
`sts2_rl/monsters/glory/fabricator.py` (Noisebot's intent),
`sts2_rl/monsters/overgrowth/vantom.py` (stale comment),
`sts2_rl/selectors.py` (`_cost` docstring only — no behaviour change),
`audit/tools/state_machine_probes.py` (classification, pass-2 holes,
`_RAISE_PAIRS`).

```
py -m pytest test/test_is_dead_early_returns.py test/test_overgrowth_powers.py \
             test/test_selectors.py test/test_monster_tier_families.py -q
    -> 197 passed

py -m pytest test/test_glory.py test/test_choose_a_card_selector.py \
             test/test_hook_order.py test/test_combat_ending_command_guards.py \
             test/test_task8_aeonglass_generated_wither.py -q
    -> 160 passed

py -m pytest test/ -q -k "monster or intent or machine or state_machine"
    -> 108 passed, 3769 deselected

py audit/tools/state_machine_probes.py zero-weight
    -> 82 machines / 6,560,008 transitions
       RandomBranchState fall-through hits: 0
       ConditionalBranchState fall-through hits: 0
       fractional: Fogmog.BRANCH=[0.4, 0.6]
py audit/tools/state_machine_probes.py nondyadic-weights
    -> 80,000 transitions, 0 RandomBranchState, 0 ConditionalBranchState
py audit/tools/state_machine_probes.py raise-sites
    -> guard N7 covers 8 sites; 1 gap; 2 closed asymmetries
py audit/tools/state_machine_probes.py          (every probe)
    -> exit 0, no traceback
```

RED evidence is inline per item: §1 (real pytest RED run, 2 failures, both
deterministic by construction), §3 (both wrong `_cost` bodies, failing at
different assertion lines), §4 (forced-fall-through run of the real probe:
13 -> 15 hits, 3 -> 1 unfuzzed), §5 (every row re-derived by executing its
input). Per protocol the full suite was not run and the 2 known
`test_conformance_floor_state.py` failures were neither touched nor counted.

### §10 — Findings from the fix pass not in the review

1. **`_RAISE_PAIRS` is worse than "4 stale rows"** — 6 rows stale, a 7th
   mis-bucketed and misreading its own C# citation, all 12 citations stale.
   Both of the printed summary's numbers were wrong. Fixed (§5).
2. **A 5th and 6th stale `_RAISE_PAIRS` row** the review did not name: the
   machine-setter row (the sim HAS had a raising property setter plus
   `reset_state_machine`) and the AddBranch-overload row (the sim's guard tests
   exactly C#'s predicate, not a different one).
3. **A second pass-2 hole in `zero_weight`** beyond the review's N3: the
   per-walk `CombatState` rebuild was entirely unguarded, so a construction
   fall-through on any seed > 0 would crash the probe rather than misfile it.
4. **`sts2_rl/monsters/base.py`'s `Intent` docstring** repeats the false
   completeness claim ("Every StatusIntent site now sets it"). Out of
   footprint; diff in §1.
5. **A self-pointing `RandomBranchState` spins forever** in the sim's
   `_find_next_move_state` `while True` — but C#'s `do { } while (!IsMove)` is
   the same loop with the same behaviour, so it is symmetric and not a gap.
   Recorded because I hit it (a 120s hang) while building the §5 witness and
   the next person to probe that shape will too.
6. **The review's `quest vs 1cost` example uses a 0-cost card** (Finesse), so
   that row is a tie rather than a demotion. Does not affect the finding; noted
   so the numbers reconcile.
