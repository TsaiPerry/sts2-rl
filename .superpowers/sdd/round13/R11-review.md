# R11 review — ledger backlog minis (round 13)

Reviewer scope: lane R11 only. Footprint reviewed via
`git diff HEAD -- sts2_rl/cards/breakthrough.py sts2_rl/monsters/overgrowth/vantom.py
sts2_rl/selectors.py audit/tools/state_machine_probes.py test/test_is_dead_early_returns.py
test/test_overgrowth_powers.py test/test_selectors.py`.
Every other modified path in the tree (hooks.py, combat.py, cmds.py, powers.py,
player.py, rewards.py, run.py, driver.py, events/**, relics/**, audit/records/**,
other test files) belongs to concurrent lanes and was read but **not** reviewed
or attributed here.

**Overall: NEEDS-FIXES.** All four code changes are correct and I re-derived
each from the C# independently. The defects are in the *report's* reasoning and
in the record/queue proposals the controller will apply verbatim: item 3's
consumer enumeration is missing a third consumer at which the clamp is **not**
inert; item 2's queue annotation makes a false completeness claim (4 sites of a
mechanism that has 18); item 4's account of *why* the old grep failed is
half-right in a way that matters. Plus three findings of my own that outrank
the task. Item 5's ruling is **CONFIRMED** and I strengthened it with an
execution witness the report did not have.

---

## Method note

Everything below that says "executed" was run against the live working tree
with `PYTHONPATH=c:/Users/Perry/Desktop/sts2-rl-tier2 py <script>`; scratch
scripts live in the session scratchpad and touch nothing in the repo. No
working-tree code was reverted (other lanes are live), no git index command was
run, no `audit/records/**` or `GAP-QUEUE.md` file was edited.

Tests re-run by me:

```
py -m pytest test/test_is_dead_early_returns.py test/test_overgrowth_powers.py \
             test/test_selectors.py test/test_monster_tier_families.py -q
   -> 193 passed in 1.36s
py audit/tools/state_machine_probes.py zero-weight
   -> TOTAL machines fuzzed: 82  transitions: 6560008
      'No valid state found' (total weight 0) hits: 0
      fractional: Fogmog.BRANCH=[0.4, 0.6]        (reproduces the report exactly)
py audit/tools/state_machine_probes.py nondyadic-weights
   -> 1 machine (TwoTailedRat), 80000 transitions, 0 fall-throughs  (reproduces)
py audit/tools/state_machine_probes.py raise-sites                  (see item 4)
```

---

## Item 1 — `cards/breakthrough.py`, the DELETION — **CORRECT (code); test is weak**

### C# re-derivation

`src/Core/Models/Cards/Breakthrough.cs:24-31` is the whole of `OnPlay`:

```csharp
VfxCmd.PlayOnCreatureCenter(...);                                        // :26
await CreatureCmd.Damage(choiceContext, Owner.Creature, HpLoss.BaseValue, // :27
                         Unblockable | Unpowered | Move, this);
await DamageCmd.Attack(Damage.BaseValue).FromCard(this)                   // :28-30
      .TargetingAllOpponents(CombatState).WithHitFx(...).Execute(choiceContext);
```

There is **no** `IsDead`/`IsEnding` check between the self-damage and the
attack, and — the reviewer's specific question — **there is no tail after the
attack at all**. `OnPlay` ends at `:31`. So the "non-damage tail" failure mode
does not exist for this card. (It *does* exist for other cards of the same
family — see finding **N3** below.)

The sim's tail is a loop, so the redundancy argument has to hold per-iteration.
It does: `AttackCommand.Execute` bails at `AttackCommand.cs:528-531`
(`if (Attacker.IsDead) return this;`) **before** `Hook.BeforeAttack` (`:536`),
before the hit loop (`:538`), before `History.CreatureAttacked` (`:655`) and
before `Hook.AfterAttack` (`:656`) — i.e. a dead attacker produces literally
nothing. Breakthrough has `_hitCount == 1` (no `WithHitCount`, no upgrade
change), so the single iteration that would have batch-damaged every opponent
(`:544-546` builds `validTargets` from all possible targets; `:653` passes the
whole list to `CreatureCmd.Damage`) is refused as one unit.

The sim's per-enemy `DamageCmd.deal(..., dealer=ctx.player, ...)` bails at
`sts2_rl/cmds.py:272-273` (`if dealer is not None and dealer.is_dead: return 0`)
**as the first statement after props inference**, ahead of every hook. So each
iteration is a total no-op. The reasoning transfers.

### Executed proof (not reading)

I did not revert anything. I built a `PreEditBreakthrough(BreakthroughCard)`
subclass whose `on_play` is the pre-edit body verbatim (deleted guard restored)
and diffed post-edit vs pre-edit on identical fresh combats, comparing player
HP/dead/block, phase, result, every enemy's HP and dead flag, all four piles,
all powers on all creatures, energy, `play_card`'s return value, **and a full
ordered trace of every `HookSystem` dispatch** (name + arg type list), with the
clone's class name normalised out.

- Run A (default `fresh()` encounter): hp ∈ {1, 2, 80} × seeds {0,1,2,7} = 12
  configs. **0 differences.** In the lethal case both sides log exactly 22 hook
  dispatches — the post-edit loop adds **zero** hook calls, confirming
  `cmds.py:272` fires ahead of everything.
- Run B (`Encounter` of 1/3/5 `LeafSlimeS`, × first-enemy-already-dead on/off,
  × hp ∈ {1,2,60} × seeds {0,3}) = 36 configs. **0 differences.**

Verdict: the deletion is behaviour-neutral on today's tree and structurally
closer to the C#. **Approved.**

### Test quality — WEAK, and the report is honest about why

`TestBreakthroughGuardDeleted`'s two tests pass identically against the pre-edit
code (I ran them against the pre-edit clone: same outcome), so there is no RED
and the report says so. That is acceptable for a provably-inert deletion. But
note what the tests do **not** pin:

- They would also pass if the mid-loop `if ctx.player.is_dead: break` were
  deleted, or if the `if not enemy.is_dead` filter were dropped — anything
  downstream of `cmds.py:272-273` is masked by that bail. The real safety
  property is *"`DamageCmd.deal` refuses a dead dealer before any hook"*, and
  nothing in this file pins **that**; it lives in `cmds.py`, another lane's
  file, so the deletion's correctness is hostage to a file R11 does not own.
- Suggested strengthening (cheap, in-footprint): assert the hook trace, not
  just HP — e.g. that playing a lethal Breakthrough dispatches no
  `on_attacked` / `modify_damage_additive` for any enemy. That distinguishes
  "no damage landed" from "damage landed and was zeroed".

### Fragility to flag

The deletion's justification is a fact about `sts2_rl/cmds.py`, which is being
edited concurrently by another lane this same wave. If that lane moves or
weakens the `dealer.is_dead` bail, Breakthrough silently regresses and only my
equivalence harness (not the committed tests) would catch it. Worth a
cross-reference in the record close note.

---

## Item 2 — `monsters/overgrowth/vantom.py` `status_count=3` — **CORRECT (code); the queue text is wrong**

### C# verification

- `src/Core/Models/Monsters/Vantom.cs:119`
  `new MoveState("DISMEMBER_MOVE", DismemberMove, new SingleAttackIntent(DismemberDamage), new StatusIntent(3))` ✓
- `Vantom.cs:34` `private const int _dismemberWounds = 3;` ✓
- `Vantom.cs:188` `await CardPileCmd.AddToCombatAndPreview<Wound>(targets, PileType.Discard, 3, null);` ✓
  (the decompiler inlined the const, so the sim's single `_DISMEMBER_WOUNDS`
  constant serving both is a faithful de-inlining, not an invention)
- `StatusIntent.cs` — `public int CardCount { get; }`, set from the ctor arg and
  read by `GetIntentLabel`/`GetIntentDescription`. The count is telegraphed to
  the player, so carrying it is right. ✓

Sim intent now reports 3: executed via the lane's own test plus
`test_monster_tier_families.py` (193 passed).

### "did anything else consume the old (missing) count?"

Enumerated: `status_count` appears at `sts2_rl/monsters/base.py:62,74` (the
docstring + field) and at exactly four construction sites
(`glory/aeonglass.py:80`, `glory/test_subject.py:100`,
`hive/the_insatiable.py:40`, `overgrowth/vantom.py:52`). The only reader is
tests. The observation encoder (`sts2_rl/full_env.py:566-578`) sets a single
flag bit from `intent.has(MoveType.STATUS_CARD)` and never touches
`status_count` — verified by reading the block, not by trusting the docstring.
So the field is still write-only and this change cannot regress anything.
**No consumer regression.**

### FINDING N1 (outranks) — the mechanism has 18 sites, not 4, and one existing test enshrines a divergence

`grep -rn "new StatusIntent(" --include=*.cs` over the spec returns **18**
sites:

```
Aeonglass.cs:102(WitherAmount)  Chomper.cs:59(3)         EyeWithTeeth.cs:39(3)
HauntedShip.cs:44(HauntDazed)   LeafSlimeM.cs:34(2)      LeafSlimeS.cs:32(1)
MechaKnight.cs:83(4)            Myte.cs:49(2)            Noisebot.cs:45(2)
PhrogParasite.cs:42(3)          SlimedBerserker.cs:52(10) SoulFysh.cs:113(Beckon)
SoulFysh.cs:115(Gaze)           TestSubject.cs:201(BurningGrowlBurnCount)
TheInsatiable.cs:96(6)          TwigSlimeM.cs:37(1)      Vantom.cs:119(3)
Wriggler.cs:55(1)
```

The sim has ~19 `MoveType.STATUS_CARD` intent constructions and **4** carry a
count. So `monster/_intent_count_lost` is a **14-site-open** mechanism, not a
"4th and final site". The report's queue annotation —
*"All 4 known sites now carry their count"* — is a false completeness claim and
must not go into GAP-QUEUE.md as written.

Worse: `test/test_monster_tier_families.py:169-175`
(`test_other_status_card_intents_are_unaffected`) asserts
`intent.status_count is None` for **Noisebot**, calling it a *"Byte-identical
guard: a STATUS_CARD intent NOT among this mechanism's three sites"*. But
`Noisebot.cs:45` is `new StatusIntent(2)` — Noisebot is squarely inside the
mechanism. That test actively pins a divergence as intended behaviour and will
have to be inverted when the remaining sites are done. This is precisely the
round-12 lesson (a green suite is not evidence of fidelity): the test's premise
was never checked against the C#. R11 walked past it while editing the file next
door.

**Required report/queue fix:** replace "All 4 known sites" with the real census
(4 of 18 done, 14 open, list them), and flag
`test_other_status_card_intents_are_unaffected` as a wrong-premise test.

---

## Item 3 — `selectors.py` `max(0, ...)` clamp — **CORRECT (code); enumeration incomplete; test under-specified**

### The three claims I was asked to verify

**(a) Is `-1` really the canonical unplayable cost today?** Executed over the
whole card registry: 29 cards have `energy_cost < 0`, and the set of distinct
negative values is exactly `{-1}`. Their types are `{CURSE, QUEST, STATUS}`;
none is `energy_cost_x`. Spec side confirmed: `CardEnergyCost.GetWithModifiers`
short-circuits `if (_base < 0) return num;` (`CardEnergyCost.cs:100-103`), and
`Wound.cs:13` is `base(-1, CardType.Status, ...)`. `cards/base.py:407-419`
mirrors it. ✓

**(b) Does the clamp produce a TIE, or merely stop out-ranking?** Executed both
offer orders:

```
to_draw_top [thinking_ahead, wound] -> ['thinking_ahead']
to_draw_top [wound, thinking_ahead] -> ['wound']
```

A genuine tie broken by offered order. ✓ (Under a "rank unplayable last"
implementation the second line would also return `thinking_ahead`.)

**(c) Is the "sim-only heuristic, no C# analogue" framing right?** Yes. These
purposes are mid-resolution `CardSelectCmd` screens the game hands to a human;
`scripted_card_selector` is the RL stand-in documented in selectors.py's module
docstring. There is nothing in the C# to be faithful *to* here, so this is a
quality change, not a fidelity change. ✓ The report says the same. ✓

### FINDING N2 (outranks) — `_cost` has THREE consumers, not two, and the clamp is not inert at the third

The report says `_cost()` is *"shared by `"upgrade"` and `"to_draw_top"`"* and
argues safety only for `upgrade`. `_cost` is read at **three** sites:

```
selectors.py:89   "upgrade"                              -_cost(...)
selectors.py:94   "to_draw_top"                           _cost(...)
selectors.py:114  "choose_a_card" / "choose_a_card_optional"  _cost(...)   <-- unlisted
```

The third one matters because `_is_junk` is `card_type in (STATUS, CURSE)` — it
does **not** cover the QUEST unplayables. Executed:

```
lantern_key    type=QUEST  cost=-1  _is_junk=False
byrdonis_egg   type=QUEST  cost=-1  _is_junk=False
spoils_map     type=QUEST  cost=-1  _is_junk=False
```

so those three reach `_cost` in the `choose_a_card` branch ahead of the junk
key. Executed before/after sweep of the clamp:

```
pool            purpose                 pre-clamp                     post-clamp
quest second    to_draw_top             [lantern_key, thinking_ahead] [thinking_ahead, lantern_key]  CHANGED
quest second    choose_a_card           [lantern_key, thinking_ahead] [thinking_ahead, lantern_key]  CHANGED
quest second    choose_a_card_optional  [lantern_key, thinking_ahead] [thinking_ahead, lantern_key]  CHANGED
quest vs 1cost  to_draw_top/choose_*    lantern_key first             thinking_ahead first           CHANGED
```

7 orderings change, 5 of them in the consumer the report never named. The
direction is an improvement (an unplayable quest card no longer beats a free
playable one), and whether a QUEST card can actually reach a generator screen is
a separate dormancy question — but the protocol's explicit instruction is *"ask
what else reads this"*, and the answer here was a third consumer with a live
behavioural delta. The `upgrade` claim itself checks out for a stronger reason
than the report gives: **zero** of the 29 unplayables is `is_upgradable`, so the
branch's leading `not is_upgradable` key always sorts them last and `_cost` is
never decisive there.

### Test quality — under-specified

`test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero` asserts one offer
order only. Executed: with a deliberately *wrong* fix (`return 98 if
energy_cost < 0`, i.e. "rank unplayable LAST" rather than "tie at 0") the test
**still passes**. So it pins "a Wound no longer beats Thinking Ahead", not the
tie semantics its own name and docstring claim. One extra assertion with the
candidates reversed (`[wound, thinking_ahead] == [wound]`) would fix it. The RED
run reported (`1 failed, 10 deselected`) is genuine and I do not dispute it.

### Design residual worth recording

Because the clamp produces a tie, `to_draw_top` still puts a **Wound** on top of
the draw pile whenever the Wound is offered first (executed above). For a
Headbutt-style effect that is strictly the worst available pick. If the intent
is "the selector should never choose dead weight", the right shape is the one
`choose_a_card` already uses — `(_is_junk(c), _cost(c), index)` — not a clamp.
The brief prescribed `max(0, ...)` and the lane followed it; flagging that the
brief's prescription is a half-measure, per "do not defer to the brief".

---

## Item 4 — `state_machine_probes.py` stale grep — **CORRECT; proof strengthened; reasoning half-right**

### The grep fix itself

`sts2_rl/monsters/state_machine.py:273` raises
`RuntimeError(f"No valid state found in RandomBranchState {self.id}!")`, verbatim
`RandomBranchState.cs:127`'s
`throw new InvalidOperationException("No valid state found in RandomBranchState " + Id + "!")`.
The old `"No valid branch"` substring cannot match it. Both functional sites
(`_walk_machine` in `zero_weight`, the `except` in `nondyadic_weights`) plus the
labels/docstrings are corrected. The brief's path `sts2_rl/state_machine.py`
indeed does not exist (`ls` confirms); the module is
`sts2_rl/monsters/state_machine.py`. The lane's correction of the brief is right.

The reachability re-derivation is also right: `get_next_state`
(`state_machine.py:265-273`) draws via `_weighted_roll` **first** and then walks
the branches, so an all-zero vector burns a draw and lands on branch 0, matching
`RandomBranchState.cs:117-124`. The remaining raise is the symmetric
float-rounding fall-through. ✓

### "PROVE the probe fires" — reproduced and improved

The lane's proof only showed that a synthetic message contains the new
substring. That does not exercise the probe's classification path. I ran the
**real** `zero_weight()` with the fall-through forced from outside the module
(`sts2_rl.monsters.state_machine._weighted_roll` patched to return `total+1000`,
so every `roll -= w` stays positive):

```
1. unforced, corrected grep : 'No valid state found' (total weight 0) hits: 0
2. FORCED,   corrected grep : 'No valid state found' (total weight 0) hits: 13
     e.g. FlailKnight / Fogmog / FossilStalker / FakeMerchantMonster
3. FORCED,   OLD substring  : 0 of those 13 messages contain 'No valid branch'
```

The corrected probe genuinely fires. **Item 4's "prove it fires" obligation is
now met** (it was not, on the lane's own evidence).

### CORRECTION to the lane's reasoning — the old grep was not merely dead

The report says the old substring *"is not a substring of the current message,
so a genuine hit was silently reclassified as an 'other error'"*. True — but
incomplete. `"No valid branch"` **still matches a live raise on the current
tree**: `ConditionalBranchState.get_next_state`, `state_machine.py:324`,
`RuntimeError(f"No valid branch in ConditionalBranchState {self.id}")`.
Executed:

```
message: No valid branch in ConditionalBranchState COND
OLD substring 'No valid branch'       in msg: True
NEW substring 'No valid state found'  in msg: False
```

So the old probe had a live **false-positive** source, not only a miss: a
ConditionalBranchState fall-through would have been counted and printed under a
headline that says "(total weight 0)" — a different mechanism entirely. The fix
is still right (it narrows the probe to its own mechanism); the close note
should say *both* things, because "which reasoning you replaced" is part of the
report contract. Related near-miss to record: `state_machine.py:432` raises
`f"no valid state found: {next_id}"` (lowercase) — the corrected grep is
case-sensitive and correctly misses it today, but that is one capitalisation away
from a new false positive.

### FINDING N3 (outranks) — the probe misfiles genuine hits raised during pass-2 setup

Bucketing the forced run by the probe's own output sections:

```
pass 1 could not fuzz              : 23 rows, 0 carry 'No valid state found'
machines STILL not fuzzed (pass 2) :  3 rows, 2 carry 'No valid state found'
    Fabricator:   CombatState: RuntimeError: No valid state found in RandomBranchState RAND!
    TwoTailedRat: CombatState: RuntimeError: No valid state found in RandomBranchState RAND!
'No valid state found' hits        : 13 rows
```

Pass 2 wraps `Encounter`/`CombatState` construction in its own `try`, and a
`RuntimeError` raised *there* is appended to `live_bad` ("dormancy unproven for
these") instead of to `hits`. A monster whose machine falls through on its very
first roll — which is what construction does — is therefore reported as
"couldn't fuzz it" rather than as a hit. **`TwoTailedRat` is the probe's own
named G7-clause-c trigger** (its docstring says pass 2 exists *because* the
first version skipped TwoTailedRat), so this hole sits exactly on the case the
probe was extended to cover. Fix: classify the construction `except` with the
same substring test `_walk_machine` uses.

Also honest-scope: `nondyadic_weights`'s population is a single machine
(TwoTailedRat, 80 000 transitions), and under the forced fall-through that
machine fails construction, so its population drops to 0. **Its corrected grep
is still unexercised** — the "prove it fires" evidence covers `zero_weight`
only.

### Flagged-not-fixed `raise_sites()` / `_RAISE_PAIRS` — CONFIRMED and WIDER than reported

The lane flagged 2 stale rows and (correctly, per footprint discipline —
`_RAISE_PAIRS` feeds guard N7's count) did not edit them. Both are stale as
described. Two **more** are, which the lane did not find:

1. `("ASYM", "register: duplicate state id (step 3, G8 clause a)", ...,
   "state_machine.py:87 silently overwrites")` — **false**.
   `MonsterState.register_states` (`state_machine.py:128-135`) now raises
   `ValueError("duplicate state id ...")`. Executed:
   `duplicate id RAISES ValueError: duplicate state id 'DUP' in the move graph`.
   That row is **SYM**, not a gap.
2. `("ASYM", "branch: CanRepeatXTimes with maxTimes == 0 (step 21, G7a)", ...,
   "state_machine.py:168-169 raises ValueError")` — **false**. The current guard
   raises only for `max_times is None`; `max_times=0` is explicitly legal (the
   permanently-dead branch, `RandomBranchState.cs:144-147`, ported in
   `_effective_weight`). Executed:
   `add_branch(..., CAN_REPEAT_X_TIMES, max_times=0)` accepted, no raise.

And **every** sim line citation in all 12 rows is stale. The probe prints the
actual raise list two screens above its own census:

```
state_machine.py  raise at [96, 120, 131, 196, 240, 273, 324, 381, 432, 491, 508]
```

None of the census's cited sim lines (`87, 138, 168-169, 183, 189, 232, 252,
271`) is in it. So the printed conclusion — *"guard N7 covers 5 sites; 6
raise-behaviour sites are gaps (G7 x3, G8 x3)"* — is wrong on today's tree in
both numbers. The lane's recommendation (re-derive `_RAISE_PAIRS` before
trusting N7's count again) stands and should be raised in priority: at least 4
of 12 rows have flipped bucket.

---

## Item 5 — step19 vs F3 — **CONFIRM the ruling** (and I have an execution witness)

### C# re-derivation, done independently

- `CreatureCmd.cs:691-696`:
  `public static async Task Heal(Creature creature, decimal amount, bool playAnim = true) { if (CombatManager.Instance.IsEnding && !creature.IsPlayer) { return; } ... }`
  — the bare `IsEnding`, nothing else.
- `CombatManager.cs:180-202` — `IsEnding` opens with
  `if (!IsInProgress) { return false; }`, then `_pendingLoss != null -> true`,
  then any live primary enemy `-> false`, then
  `Hook.ShouldStopCombatFromEnding -> false`, else `true`. The doc-comment at
  `:171-179` says it explicitly: *"False when ... Combat is not in progress."*
- `CombatManager.cs:210-220` — `IsOverOrEnding => IsEnding ? true : !IsInProgress`,
  with the doc-comment at `:204-209` recommending it *over* `IsEnding` precisely
  because the two differ at boundary points.
- `Hook.cs:53-63` — `IterateCombatHookListeners` yields nothing when
  `IsOverOrEnding && !IsStarting`. Different predicate, different site.

Sim side: `combat.py` `is_over` is `phase == Phase.COMBAT_OVER`; `is_ending`
returns `False` when `phase in (None, COMBAT_OVER)` and otherwise
`_has_pending_loss or _all_enemies_dead()`; `is_over_or_ending` is their OR.
The heal guard reads `getattr(combat, "is_over", False)` — i.e. `!IsInProgress`,
the *complement* window of `IsEnding`.

### Executed witness — the divergence, in both directions

```
window A: every enemy dead, combat not yet torn down
  phase = PLAYER_TURN   is_over = False   is_ending = True   is_over_or_ending = True
  CreatureCmd.heal(enemy, 7) -> returned 7, enemy hp 0 -> 7
  C#: IsEnding && !IsPlayer -> returns immediately, hp stays 0.     DIVERGENCE

window B: phase == COMBAT_OVER (torn down)
  is_over = True    is_ending = False
  CreatureCmd.heal(enemy, 7) -> returned 0, enemy hp 10 -> 10
  C#: IsEnding is False here, guard does not fire, heal lands.      DIVERGENCE (opposite)

control: heal(player, 7) with phase == COMBAT_OVER -> 7   (C# also allows; !IsPlayer is False)
```

The sim's guard is not a narrower or looser version of C#'s — it is the
**complementary** window, wrong in both directions. The report reached this by
reading; it is now executed.

### The ruling, point by point

| lane's claim | verdict |
|---|---|
| step19's closure ("sim `combat.is_over` IS C#'s `IsEnding`") is FALSE, not imprecise | **CONFIRMED** (executed above) |
| `combat.is_over` mirrors `!IsInProgress`; C#'s heal guard is `IsEnding` alone | **CONFIRMED** (`CombatManager.cs:184-186`, `CreatureCmd.cs:693`) |
| ADJACENT to, not identical with, F3 — different file, different mechanism | **CONFIRMED**. `CreatureCmd.heal` reads `combat.is_over` directly via `getattr(hooks, "combat", None)`; it is not a hook name, is not in `_COMBAT_GATED_HOOKS`, and never reaches `hooks.py:671`'s `_each` gate. F3's site is `HookSystem.combat_is_over` (`hooks.py:515-555`), read once per `_each` call for the 73 gated dispatch names. I re-read R1-report §8 (F3) and the lane characterised it accurately. |
| they need DIFFERENT replacements — `combat.is_ending` vs `is_over_or_ending` | **CONFIRMED**, and this is the load-bearing half of the ruling. `Hook.cs:55` gates on `IsOverOrEnding`; `CreatureCmd.cs:693` gates on bare `IsEnding`. A single shared "swap `is_over` for `is_over_or_ending`" edit would **over-guard** the heal site: window B above shows C# permitting a post-teardown non-player heal that `is_over_or_ending` would refuse. |
| one fix cannot close both | **CONFIRMED** |

**So: CONFIRM. Assign them as two separate work items.** F3's is the
higher-blast-radius one (73 dispatchers); the heal guard is a one-line change in
`cmds.py` with an executed two-way witness and a trivially writable pin.

### Assessment of the "sweep first" recommendation — CONFIRM the sweep, PARTIALLY OVERTURN "before"

- **The sweep is worth a dedicated task.** `grep -rn "\.is_over\b|combat_is_over|Phase.COMBAT_OVER" sts2_rl/`
  returns **49** hits; stripping the definitions, the drivers/env terminators
  and `combat.py`'s own internals still leaves a dozen-plus gameplay reads that
  each need a C# counterpart check — e.g. `cards/cascade.py:56`,
  `cards/colorless_skills.py:132`, `potions.py:1048`, `powers.py:997`,
  `powers.py:1342`, `powers.py:4301`, `powers.py:4484`, `powers.py:4557`,
  `powers.py:4643`, `cmds.py:782`. Two independent finds in one wave justify it.
- **But the lane's proposed grep would miss its own site.** It recommends
  grepping for `combat.is_over` / `hooks.combat.is_over` / `phase == Phase.COMBAT_OVER`.
  The heal guard is written `getattr(combat, "is_over", False)` — the substring
  `combat.is_over` does not occur in it. Any sweep must include the `getattr`
  form (`getattr(<x>, "is_over"` / `"is_over_or_ending"` / `"is_ending"`), or it
  will reproduce exactly the blind spot that let this site survive.
- **"before fixing either" — overturn.** Holding a one-line, independently
  derived, executable fix hostage to a 49-site sweep is the failure mode where
  neither lands. Sequence it the other way: fix the heal guard now (it is
  self-contained and its correct predicate is settled), run the sweep as its own
  task, and let F3 land with the sweep since F3's decision genuinely is a
  73-dispatcher policy call.

### FINDING N4 (outranks) — the same false equivalence lives in a SECOND record entry

The lane's correction proposal names only `seam/creature_card_cmds` step 19
(array index `steps/20`). The identical claim is also in the same record's
**`guards/3`**:

> *"Closed 2026-07-27: CreatureCmd.heal's dead-creature early return is gone;
> its only guard is now `combat.is_over and target.side != 'player'`
> (sts2_rl/cmds.py), **which is exactly CreatureCmd.cs:693-696's `IsEnding &&
> !IsPlayer`**."*

If the controller corrects only step 19, the false statement survives verbatim
one field away. And `guards/24` (G14)'s closure asserts that the guarded
commands each carry *"the guard their C# counterpart carries, **at the strength
their C# counterpart carries it** (`IsOverOrEnding` vs `IsEnding` vs
`!IsInProgress`)"* — which is false for `heal`, the one member of that family
carrying `!IsInProgress` where C# carries `IsEnding`. Recommend the correction
touch all three.

---

## Additional finding

### FINDING N5 — a 7th `card/_is_dead_early_return` site with a real non-damage tail

The brief called Breakthrough "the 6th site". `sts2_rl/cards/thunderclap.py:45`
has the same top-level shape and, unlike Breakthrough, **does** have a tail the
redundancy argument would have to cover separately:

```python
for enemy in list(ctx.enemies):
    if enemy.is_gone or ctx.player.is_dead: continue
    DamageCmd.deal(...)
if ctx.player.is_dead:            # <-- same family, uncounted
    return
for enemy in list(ctx.enemies):
    if not enemy.is_gone:
        PowerCmd.apply(ctx.hooks, enemy, VulnerablePower, ...)
```

`Thunderclap.cs:28-32` has no such check — it awaits the attack and then
`PowerCmd.Apply<VulnerablePower>` unconditionally. Whether the sim's guard is
redundant there depends on `PowerCmd.apply`'s own bail (an `is_ending` guard,
not a `dealer.is_dead` one), i.e. a **different** argument from the one used for
Breakthrough. Recommend adding it to the mechanism's site list rather than
letting "6 sites" stand. (Out of R11's footprint; flagged, not fixed.)

### Note, not a finding — `before_attack`/`after_attack` bracket placement

While tracing item 1 I observed that the sim dispatches `before_attack` /
`after_attack` at the card-play level (`combat.py:970` and `:983`, around the
whole `on_play`), whereas C# fires them **inside** `AttackCommand.Execute`
(`:536`, `:656`), i.e. after the `Attacker.IsDead` bail. A lethal Breakthrough
therefore dispatches both hooks in the sim and neither in C#. This is
pre-existing, identical before and after R11's deletion (my hook traces are
byte-equal in the lethal case), and lives in `combat.py` — another lane's file.
Recorded so it is not mistaken for fallout of this deletion.

---

## Spec-compliance verdict

| protocol rule | verdict |
|---|---|
| work only in `sts2-rl-tier2` | ✓ |
| footprint respected | ✓ — `git status` shows exactly `sts2_rl/cards/breakthrough.py`, `sts2_rl/monsters/overgrowth/vantom.py`, `sts2_rl/selectors.py`, `audit/tools/state_machine_probes.py`, `test/test_is_dead_early_returns.py`, `test/test_overgrowth_powers.py`, `test/test_selectors.py` modified-unstaged by this lane. The probe tool is in scope (brief item 4 assigned it); the "never touch audit/**" rule covers `audit/records/**` + `GAP-QUEUE.md`, neither touched. |
| no forbidden git ops | ✓ — all seven lane files are unstaged (` M`); nothing added/committed/stashed |
| no "revert to see RED" | ✓ — and I honoured it too (pre-edit behaviour reconstructed by subclass, never by reverting) |
| `py` launcher | ✓ |
| record/queue proposed, not applied | ✓ |
| brief contradictions flagged | ✓ — the brief's `sts2_rl/state_machine.py` path and `sts2_rl/monsters/vantom.py` path are both wrong and the lane said so |
| report contract items 1–5 | ✓ present, and the TDD-order deviation is disclosed up front rather than buried |
| full suite not run | ✓ |

Minor: several sim-side line citations in the report (`cmds.py:520-523` for the
heal guard — HEAD has it at `:501`, working tree at `:544`; `combat.py:1571-1573`
for `is_over` — working tree `:1606-1607`) have drifted. That is concurrent-lane
churn, not a lane defect, but record close notes are durable artefacts and should
cite by symbol name where the line is volatile.

---

## Test-quality verdict per item

| item | test | RED-able against pre-edit code? | pins the C#? | verdict |
|---|---|---|---|---|
| 1 | `TestBreakthroughGuardDeleted` (2) | **No**, and cannot be — the change is provably inert (I verified: passes identically against a pre-edit clone) | Partially. Pins "a dead player lands no attack", which is C#-correct, but is masked by `cmds.py:272-273` and would pass under several wrong card bodies | **ACCEPTABLE, weak.** Disclosure is honest. Strengthen by asserting the hook trace, not just HP. |
| 2 | `test_dismember_telegraphs_the_status_intent_too` (+1 assertion) | **Yes**, deterministically — `Intent.status_count` defaults to `None` (`monsters/base.py:74`) and the pre-edit call passed no kwarg, so `== 3` was necessarily false | Yes — `Vantom.cs:119`'s `StatusIntent(3)` | **GOOD** (RED derivable by construction, not by runtime luck) |
| 3 | `test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero` | **Yes**, genuine RED run shown and credible | No C# to pin (sim heuristic). **Does not pin the asserted semantics**: passes under a "rank unplayable last" implementation too (executed) | **NEEDS ONE MORE ASSERTION** (reversed offer order) |
| 4 | no unit test; probe run + throwaway script | n/a | n/a | **INSUFFICIENT as submitted** (substring-only proof); **now satisfied** by my forced-fall-through run of the real probe. `nondyadic_weights`'s grep remains unexercised. |
| 5 | report only | n/a | n/a | **EXCEEDS** — correct ruling, now backed by an execution witness |

---

## What must change before this lane is approved

1. **Item 2 queue annotation:** drop "All 4 known sites now carry their count".
   `monster/_intent_count_lost` has 18 C# sites; 4 are done, 14 open (list in
   finding N1). Add the note that
   `test_monster_tier_families.py::test_other_status_card_intents_are_unaffected`
   pins Noisebot's missing count as intended, and Noisebot.cs:45 is
   `StatusIntent(2)` — a wrong-premise test to invert when the rest land.
2. **Item 3 report text:** enumerate all three `_cost` consumers and state the
   executed delta at `choose_a_card`/`choose_a_card_optional` for the three
   QUEST unplayables. The current text asserts inertness at a consumer it never
   named.
3. **Item 3 test:** add the reversed-offer-order assertion so the test pins
   "tie", which is what its name claims.
4. **Item 4 close note:** add that `"No valid branch"` still matches
   `ConditionalBranchState`'s raise (`state_machine.py:324`), so the old grep was
   a live false-positive source, not only a miss.
5. **Item 4 flag:** extend the `_RAISE_PAIRS` finding to 4 stale rows (add the
   duplicate-state-id and `maxTimes==0` rows) and to "every sim line citation in
   all 12 rows is stale", so the follow-up task is scoped correctly.
6. **Item 5 correction proposal:** name `guards/3` and `guards/24` of
   `seam/creature_card_cmds.json` alongside step 19, and correct the proposed
   sweep grep to include the `getattr(<x>, "is_over"...)` form (which its own
   site uses).

Optional but recommended: fix the pass-2 hit misclassification in `zero_weight`
(finding N3) — it is inside R11's footprint and it is the difference between the
probe reporting a real divergence and reporting "dormancy unproven".

---

# Re-review (2026-08-01)

Scope: the six NEEDS-FIXES items only. My four code-change confirmations and my
item-5 ruling stand unchanged and are not re-argued. Everything below was
re-derived from the C# or executed against the live tree; no working-tree code
was reverted and no git index command was run.

**Verdict: APPROVED.**

## Test status first, because the tree is noisy

R11's own tests: `py -m pytest test/test_selectors.py test/test_monster_tier_families.py
test/test_is_dead_early_returns.py::TestBreakthroughGuardDeleted
test/test_overgrowth_powers.py::TestVantomDismember -q` -> **38 passed**.

Running those four files whole gives **3 failures** — `TestOfferingGuardDeleted`
(x2) and `TestStatusCardClasses::test_slimed_play_draws_one_and_exhausts`. All
three fail with the played card still in `hand` (`assert 4 == 3`,
`assert [Offering] == []`). That is a concurrent **Play-pile** lane's in-flight
work (untracked `test/test_round13_play_pile.py`, 795 lines, alongside its
`cards/base.py` / `player.py` edits), not R11: R11 changed no card-play routing
and touched neither Offering nor Slimed, and its own 38 tests are green. **Not
attributed to this lane.** Flagged so the wave suite is not misread.

## 1. The corrected censuses

### StatusIntent — 18 / 18 / 5 ported / 13 open: **VERIFIED**

`grep -rn "new StatusIntent(" --include=*.cs` over the spec returns exactly the
18 sites the ledger names. I mapped every one to its sim construction
independently, including the two the mapping could plausibly have got wrong:
`Wriggler.cs:55` (`new BuffIntent(), new StatusIntent(1)`) -> `overgrowth/phrog_parasite.py:46`,
where `class Wriggler` lives alongside `PhrogParasite` (hence that file's count
of 2); and the three slime species (`LeafSlimeS.cs:32`, `LeafSlimeM.cs:34`,
`TwigSlimeM.cs:37`) -> `overgrowth/slimes.py`'s 3. There is **no** STATUS_CARD
`Intent` construction anywhere outside `sts2_rl/monsters/` (`env.py:167` and
`full_env.py:571` only read the flag), so the ledger's search root is complete.
5 done / 13 open.

The ledger test is well built: keyed by **file** not `file:line` (survives
concurrent line churn), and it asserts `total == 18` *before* the two dicts, so
a construction its regex fails to match fails **loudly** rather than silently
under-counting. Nested-paren fragility is real (the regex handles one level of
nesting) but it is fail-loud, which is the right trade.

### `_cost` — 3 consumers: inert / live / real-but-unreachable: **VERIFIED**

- **`upgrade` inert** — executed over the whole registry: 29 unplayables, cost
  set exactly `{-1}`, types `{CURSE, QUEST, STATUS}`, **0 upgradable**, 0
  X-cost. The leading `not is_upgradable` key therefore always decides first.
  Now pinned by `test_no_unplayable_card_is_upgradable`.
- **`to_draw_top` live** — my original executed delta, unchanged.
- **`choose_a_card*` real but unreachable** — I re-derived the call-site
  enumeration myself: `grep '"choose_a_card'` gives exactly three call sites
  (`relics/toolbox.py:46`, `relics/choices_paradox.py:56`, `potions.py:1422`);
  `driver.py:99` and `run_env.py:182,187` are purpose-name registries, not
  calls. `combat.card_pool` is `self.character.card_pool` (`combat.py:366-372`),
  so the dormancy test's iteration over `CHARACTERS.values()` plus
  `COLORLESS_POOL` is complete coverage of the generation sources.

### The SENTINEL argument — **RULING: SOUND. Keep the clamp shared.**

This is the one judgement call in the pass and the lane got it right, for the
reason it gives. `CardEnergyCost.GetWithModifiers` (`CardEnergyCost.cs:95-107`)
is a ladder of short-circuits — `IsCanonical`, then `_base < 0`, then `CostsX` —
each returning `num` *before* any modifier is consulted. `-1` and `CostsX` are
handled by the **same** mechanism in the same method: neither is a price, both
are flags. `selectors.py` already accepts that for one of them
(`_X_COST_RANK = 99` for `energy_cost_x`); refusing it for the other was the
inconsistency. `_cost` is the single place in the file that turns a `Card` into
a sort rank, so it is the correct locus for sentinel normalisation, and
narrowing to `to_draw_top` would leave two consumers reading a flag as an
integer and would create two standing obligations (consumer 1's inertness,
consumer 3's pool argument) for zero behavioural gain. **Shared clamp
confirmed.**

One caveat I record rather than dispute: `max(0, ...)` normalises the sentinel
*to a real price*, which is itself a category choice — the strictly parallel
treatment would be an `_UNPLAYABLE_RANK` sentinel alongside `_X_COST_RANK`. The
lane's own residual section says exactly that, supplies the diff, and defers it
to the controller as a policy question rather than a fidelity one. That is the
right disposition, and the choice is now explicit and pinned instead of
implicit. My review point is satisfied.

### `_RAISE_PAIRS` — 6 stale + a 7th mis-bucketed + all 12 citations; summary "8 SYM / 1 gap / 2 closed": **VERIFIED, numbers right**

Bucket count over the new table: SYM = rows 1,3,4,5,6,9,10,11 = **8**;
ASYM + ONE-SIDED-GUARD = **1**; SYM-NO-RAISE = **2**; DEAD = 1; total 12. The
live `raise-sites` run prints exactly that.

Rows that changed bucket: old rows 6,7,8,9,10 (all `ASYM`) and old row 11
(`ONE-SIDED-GUARD`) = the **six** stale ones; old row 2 (`SYM` ->
`ONE-SIDED-GUARD`) is the **seventh**, rebucketed for a different reason. That
matches the lane's framing.

Row-level checks I executed or read myself, beyond the two I found first time:

- **Row 2's C# misread is real.** `MonsterMoveStateMachine.cs:56-59` is
  `if (_currentState == null) throw ... "Cannot find next move state when
  current state is null."` — it guards the **current** state. The old label
  "no initial state to fall back to" pointed at the wrong thing; the actual
  initial-state fallback (`SetCurrentState(string.IsNullOrEmpty(nextState)
  ? _initialState : States[nextState])`) has no guard on either side. The sim
  has no explicit None guard either — `_find_next_move_state`
  (`state_machine.py:424`) reads `self.current.can_transition_away`, so a None
  surfaces as an `AttributeError`. `ONE-SIDED-GUARD` is the right bucket.
- **Row 1** — C# `RollMove` throws `_currentState.Id + " is not a valid move
  state"`; sim `state_machine.py:381` raises the same text. SYM.
- **Row 3** — C# throws `"no valid state found: " + nextState`; sim
  `state_machine.py:432` raises `f"no valid state found: {next_id}"`. Verbatim.
  SYM — and this **retracts a remark of mine**: I called that lowercase message
  a "near-miss one capitalisation away from a false positive". It is not a
  typo, it is a faithful port of C#'s own lowercase string. The lane's fix
  (both probe substrings now name their state class rather than relying on
  case-sensitivity) is the better defence, and its comment says so.
- **Row 10** — `MonsterModel.cs:222-237` is a private setter that throws
  "...'s move state machine has already been set", with `ResetStateMachine`
  (`:389-392`) as the sanctioned clear. The sim's `machine` **is** a property
  setter raising `RuntimeError` (`state_machine.py:482-495`) with
  `reset_state_machine` (`:497-505`) mirroring the clear. Both pre-existing —
  the lane edited no engine file. SYM.
- **Row 11** — `RandomBranchState.cs:46-51` is the overload *without* a
  maxRepeats slot, throwing `ArgumentException("Use other constructor to
  specify number of repeats")` when `repeatType == CanRepeatXTimes`. The sim's
  `max_times is None` means precisely "no maxRepeats supplied". Same predicate,
  and the old row's "raises for a DIFFERENT predicate (max_times <= 0)" was
  doubly wrong as the new text says. SYM.
- Rows 6/7/8/9 re-confirm my own first-pass executions.

**All 12 sim citations were stale**: the probe's own printout lists the real
raise lines `[96, 120, 131, 196, 240, 273, 324, 381, 432, 491, 508]`, and none
of the old table's `87 / 138 / 168-169 / 183 / 189 / 232 / 252 / 271` is among
them.

## 2. Noisebot — **VERIFIED; the pin asserts the C# truth; no coverage dropped**

`Noisebot.cs:23` `private const int _noiseStatusCount = 2;`; `:45`
`new MoveState("NOISE_MOVE", NoiseMove, new StatusIntent(2))`; `NoiseMove`
builds `new CardPileAddResult[2]` and adds Dazed to `PileType.Discard` then
Dazed to `PileType.Draw` at `CardPilePosition.Random`. The sim now carries
`_NOISE_STATUS_COUNT = 2` on the intent, and the diff is a **single hunk at
lines 62-90, entirely inside `class Noisebot` (59-91)** — Guardbot, Stabbot,
Zapbot and Fabricator are byte-unchanged.

`test_noisebot_noise_carries_its_status_count` asserts `status_count == 2`, i.e.
the C# truth, and keeps the old test's `move_type == STATUS_CARD` assertion. No
legitimate coverage was dropped: the replaced test was an **invalid** negative
control (its subject was inside the mechanism it claimed to be outside), and
the census ledger is a strictly stronger control since it names all 13 open
sites rather than one. One minor observation, not a blocker: the ledger is a
**source-text** check, so the tree now has no *runtime* assertion that
`Intent.status_count` defaults to `None`. If anyone ever adds an
`Intent.__post_init__`, nothing would catch a default change.

## 3. The selector test — **VERIFIED; my counter-example is dead**

Executed the revised tests against three bodies by patching
`sts2_rl.selectors._cost` (no code reverted):

```
body                  test_to_draw_top_clamps...        test_choose_a_card_clamp...
GOOD  max(0, .)       PASS                              PASS
WRONG raw -1          FAIL at line 78                   FAIL at line 128
WRONG rank-last 98    FAIL at line 81                   FAIL at line 130
```

Both wrong bodies die, at **different assertion lines**, exactly as claimed —
and the "rank-last 98" body is the counter-example I constructed in the first
review, so the gap I found is genuinely closed. The three new pins pass under
the good body, and the pre-existing selector tests are unaffected under all
three bodies.

## 4. The probe — **VERIFIED; fires where it should, silent where it should**

Three forcings of the real `zero_weight()` (walks=1, steps=3):

```
                                       rand_hits  cond_hits  still_unfuzzed  fuzzed
A. unforced (real rolls)                   0          0            1           82
B. forced RandomBranch fall-through       15          0            1           80
C. forced ConditionalBranch raise          0         12            1           82
```

- **B: 13 -> 15 confirmed**, and `TwoTailedRat` and `Fabricator` now appear as
  hits and no longer in the "STILL not fuzzed" list — the pass-2 blind spot I
  found (N3) is closed at **both** setup sites (the initial build and the
  per-walk rebuild). `still_unfuzzed` 3 -> 1 (`_Cultist`, an unrelated
  `AttributeError`).
- **C: the live false positive is confirmed by execution.** With the
  ConditionalBranchState raise forced, **13** of the printed lines match the
  old single grep `"No valid branch"` — under the pre-fix probe those would
  have been counted and printed under a headline reading "(total weight 0)".
  The new code files them under a separate "ConditionalBranchState
  fall-through ... [different mechanism -- not a zero-weight hit]" headline and
  reports `rand_hits = 0`. Exactly the prediction, now executed.
- **A: silent when it should be** — 0/0, and the full-scale unforced run
  reproduces the report's headline numbers (82 machines, 6,560,008 transitions,
  0 hits, `Fogmog.BRANCH=[0.4, 0.6]`).

`nondyadic_weights` gets the same classifier, and its honest scope caveat
(population = 1 machine, so its corrected classification is exercised only that
far) is now in its docstring.

## 5. §8's verbatim record-close text — **TRUE AS WRITTEN**

Checked field by field against the actual record and my own executions:

- `steps[20]` and `guards[3]` are both currently `verdict: faithful`, so the
  proposed `faithful -> gap` moves are correct and not no-ops. `guards[24]` is
  `faithful` and **NARROWED** is the right disposition — only its "at the
  strength their C# counterpart carries it" clause fails, and only for `heal`;
  the other members (BlockCmd, discard_hand, _draw, the two shuffles, afflict,
  the three pile helpers) are not challenged.
- The executed witness quoted in the note (7 returned in the ending window,
  0 returned post-teardown, player arm unaffected) matches my numbers exactly.
- The Breakthrough note's "48 configurations" matches my two harnesses
  (12 + 36), and it carries forward the `cmds.py` hostage caveat and the honest
  "non-RED-able" statement.
- Numeric nit, not load-bearing: the corrected sweep grep returns **57** on my
  run, not 56 — the tree is live under concurrent lanes, so treat that number
  as indicative. Every load-bearing claim holds: the first pass's pattern
  returns **0** matches on `cmds.py:544` (the heal guard's own line), the
  corrected pattern matches it, and the four `getattr` sites are real
  (`cmds.py:544`, `:1244`, `:1419`, `hooks.py:1593` — the report says 1591,
  drifted by concurrent edits).

## Adjudications

**(a) Noisebot at `glory/fabricator.py` instead of the brief's non-existent
`monsters/noisebot.py` — RIGHT CALL, in scope, NOT BLOCKED-ON-FOOTPRINT.**
The footprint exists to prevent collisions between concurrent lanes, not to
protect filenames. The brief named a path that does not exist, and the only
coherent reading of "`sts2_rl/monsters/noisebot.py`" is "the Noisebot class".
The lane edited only that class body (verified: one hunk at 62-90, inside
`class Noisebot` 59-91; four sibling classes byte-unchanged), the file was
untouched by any other lane when it started, and this is the same correction
class as `vantom.py` and `state_machine.py`, both of which I approved in the
first pass — consistency demands the same ruling. The lane also did the right
belt-and-braces thing: it disclosed the deviation at the top of the fix pass
and supplied the exact diff, so a controller reading the footprint literally
can still treat the code half as blocked without re-deriving anything.

**(b) The `monsters/base.py` `Intent` docstring diff — CORRECT, apply it.**
I diffed the supplied hunk against the current file: all three context lines
("status cards are about to land. Every StatusIntent site now sets it;" /
"every other Intent construction leaves it at its default (None), and" /
"the observation encoder (full_env.py:571) still reads only the") match
byte-for-byte, so it applies cleanly even with another lane live in that file.
The replacement text is accurate — 5 of 18 set, 13 open, mechanism not closed —
and `full_env.py:571` is still the STATUS_CARD flag read. Correctly refused as
out of footprint. One wording note, no change needed: "Every non-StatusIntent
construction leaves it at its default (None)" is true, and the sentence before
it already says the 13 open StatusIntent sites also leave it None, so the
paragraph is internally consistent.

**(c) The lane's disclosure #4 misattributes an example to me.** It says my
sweep table's `quest vs 1cost` row used a `finesse`-based comparison and that
`finesse.energy_cost == 0`. My row used **`defend`**, which is genuinely
1-cost; the printed ordering (`lantern_key, thinking_ahead, defend` ->
`thinking_ahead, lantern_key, defend`) is correct as it stands. Harmless — the
lane says the headline count is unaffected and re-derived the deltas
independently, which it did — but the record should not carry a correction to
something I did not write.

## Re-review verdict table

| item | verdict |
|---|---|
| 1. corrected censuses (StatusIntent / `_cost` / `_RAISE_PAIRS`) | **VERIFIED**, numbers right |
| 1b. sentinel argument for keeping the clamp shared | **SOUND — ruling upheld** |
| 2. Noisebot fix + inverted pin + census ledger | **VERIFIED**, no coverage lost |
| 3. selector test kills both wrong bodies | **VERIFIED by execution** |
| 4. probe classification + both pass-2 holes | **VERIFIED by execution** |
| 5. §8 record-close text | **TRUE AS WRITTEN** (one indicative number drifted) |
| (a) Noisebot footprint call | **in scope, right call** |
| (b) `base.py` docstring diff | **correct, applies cleanly** |

## One standing recommendation the fix pass does not itself resolve

`monster/_intent_count_lost` must be **re-scoped and REOPENED**, not treated as
closed. The queue and the mechanism's own record still describe a three-or-four
site mechanism; the truth is 18 sites with 13 open. All 13 are dormant *today*
only because the encoder reads a flag bit and not the count
(`full_env.py:566-578`) — which is the same argument that made the five fixed
ones dormant, so "dormant" is not a reason to leave them. A partial port is the
worst resting state: five monsters telegraph a count, thirteen do not, and
nothing in the tree explains the split except this lane's report. The census
ledger test is the right instrument and will fire the moment the split changes;
the queue entry should be rewritten to match it, and the remaining 13 batched
as one follow-up task.

All six NEEDS-FIXES items are closed. **APPROVED.**
