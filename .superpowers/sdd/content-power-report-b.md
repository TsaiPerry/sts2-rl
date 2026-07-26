# Stream report — content audits: powers, HALF B (enemy powers)

Branch `audit-power-b`, worktree `c:\Users\Perry\Desktop\sts2-rl-power-b`, based on
`audit-power` at `6c3f2504`. Written 2026-07-26.

This is the **half-B** companion to `.superpowers/sdd/content-power-report.md`
(the main power report, 45 units). It is a separate file on purpose — half A
runs concurrently in a sibling worktree and the main report is the one file the
two halves would collide on. **Whoever merges `audit-power-a` and
`audit-power-b` folds both halves into the main report's sections 4-10.** Do not
edit the main report from here.

Scope: the 48 enemy-power units (Overgrowth / Hive / Glory) the continuation
prompt assigned to half B. Verified against the live roster, not the prompt's
list.

| | |
|---|---|
| half-B units audited | **48 / 48 — COMPLETE** (batches 1-3) |
| power kind overall | 93 / 134 audited, 0 invalid, 0 stale |
| suite | 2476 passed / 31 xfailed at every batch gate, unchanged |
| commits | batch 1 `c27003a4`; batch 2 `8696d479`; batch 3 see the branch log |

## 0. Headline findings

1. **`turn_structure` G5 is settled and stays DORMANT — but its dormancy
   argument is wrong and one of its premises is false.** Section 1.
2. **Five NEW live gaps**, all executed. Section 2:
   - **`rampart`** drops C#'s extra-turn guard (Pael's Eye witness);
   - **`flutter`** re-rolls the stunned hopper's move on the **wrong RNG
     stream**;
   - **`power_cmd` G6 is LIVE** — its own record says "no concrete broken
     interaction is demonstrated"; `adaptable` demonstrates one;
   - **`minion` / `reattach`** — the missing `ShouldOwnerDeathTriggerFatal`
     hook lets Feed pay out on a minion's death;
   - **`suck`** — C#'s `AfterAttack` ported onto the per-hit
     `on_damage_received`, so the Fossil Stalker's 2-hit LASH deals 9 in the sim
     and 6 in the game.
3. **No fourth non-dyadic multiplicative factor** in half B. Section 4.
4. Two new **recurring gap shapes** for `PROMPT.md`, plus independent
   reproductions of two existing seam findings' populations and two
   corrections to seam-record text. Sections 3, 5 and 6.

## 1. `turn_structure` G5 — the question half B was asked to settle

The main report's section 6 opened this: G5's dormancy rests on "every ported
listener on these hooks self-filters to its own owner", which establishes only
that *ordering within one hook* is unobservable. It named three units whose
effect changes state other creatures then read —
`battleworn_dummy_time_limit` (escapes its owner mid-round), `asleep` (removes
another power and wakes the owner) and `slumber` (stuns) — and asked half B to
settle it with a two-dummy Battle Friend witness.

**Verdict: G5 remains DORMANT for all three, and the correct dormancy argument
is not the one G5 gives.** It is not "listeners self-filter" — it is **the
encounter rosters**: a per-creature turn-end slot is observationally equal to
the side-end slot exactly when the owner is the *last* creature in the enemy
list, and a per-creature turn-start slot equals the side-start slot when the
owner is *first*. Every half-B owner satisfies that today. Executed with
`py tools/audit/power_slot_probes.py rosters` (committed):

```
battleworn_dummy_time_limit BATTLEWORN_DUMMY_SETTING_1/2/3  n=1
asleep / plating            LAGAVULIN_MATRIARCH_BOSS        n=1
slumber                     SLUMBERING_BEETLE_NORMAL        n=3  [BowlbugRock, BowlbugSilk, SlumberingBeetle]
hatch / minion              OVICOPTER_NORMAL                n=1  (+ up to 5 eggs spawned mid-combat)
escape_artist / flutter     THIEVING_HOPPER_WEAK            n=1
sandpit                     THE_INSATIABLE_BOSS             n=1
hardened_shell              SKULKING_COLONY_ELITE           n=1
```

Three specific corrections to the main report's section 6:

1. **The two-dummy premise is FALSE.** The report says "the Battle Friend
   encounters field more than one dummy, so the sim can remove dummy #1 before
   dummy #2 acts". There is no two-dummy encounter anywhere in either source.
   `BattlewornDummyEventEncounter.GenerateMonsters`
   (`BattlewornDummyEventEncounter.cs:63-72`) returns a
   `_003C_003Ez__ReadOnlySingleElementList`, and `BattlewornDummyEventEncounter.cs`
   is the **only** file under `src/Core/Models/Encounters` that mentions
   `BattleFriend` at all; the sim's three encounters are
   `monster_classes=['BattleFriendV1' | 'V2' | 'V3']`
   (`sts2_rl/monsters/glory/battle_friend.py:67-78`). Executed:
   `py tools/audit/power_slot_probes.py g5-witness`. **The requested witness is
   not constructible**, which is itself the answer. (The record for
   `battleworn_dummy_time_limit` belongs to half A; half B did not write it.)
2. **`asleep` does not touch another *creature's* state.** It removes
   `PlatingPower` from **its own owner** (`AsleepPower.cs:27,42`
   `base.Owner.GetPower<PlatingPower>()`), and the only listener that reads that
   Plating is `PlatingPower`'s own owner-filtered `on_enemy_turn_end`
   (`powers.py:1076-1078`), in a later slot in both models. The Matriarch fight
   is solo besides. So `asleep` is inside G5's original self-filtering
   argument after all.
3. **`slumber` is the real test, and it passes for a reason G5 does not state.**
   `SLUMBERING_BEETLE_NORMAL` really does field three creatures, so the
   per-creature dispatch really is N-fold — executed hook order
   (`power_slot_probes.py enemy-hook-order`):

   ```
   ['clear:BowlbugRock','start:BowlbugRock','end:BowlbugRock',
    'clear:BowlbugSilk','start:BowlbugSilk','end:BowlbugSilk',
    'clear:SlumberingBeetle','start:SlumberingBeetle','end:SlumberingBeetle',
    'side_end']
   ```

   vs C#'s `[clear×3, AfterBlockCleared×3, AfterSideTurnStart, move×3,
   BeforeTurnEnd, AfterTurnEnd]`. It is unobservable only because the Slumber
   owner is **last**, so nothing acts between its turn end and the side end.
   The *block-clear* half is separately dormant: neither Bowlbug move grants
   block to an ally (`monsters/hive/bowlbugs.py:87` gains block on `self`), so
   the sim clearing the beetle's block only after the Bowlbugs have moved cannot
   lose block the game kept — the same shape as G5's existing Guardbot argument,
   one encounter over.

**Note on the split (coordinator correction, folded in):**
`battleworn_dummy_time_limit` is **half A's** unit, not half B's — the
continuation prompt's split list is wrong about it, and half A has audited it.
Half B did not write that record. Half A independently reached the same
single-element-list finding. So the G5 question comes down to **`asleep` and
`slumber` alone**, which is what the two paragraphs below settle: `asleep`'s
effect never leaves its own owner, and `slumber`'s owner is the last creature in
its (genuinely 3-strong) encounter. Neither produces a witness, and **both are
labelled dormant-with-reason rather than asserted** — the reason being the
roster, which is checkable by a committed probe.

**What this means for the seam record** (reported, not edited — half B owns
neither `audits/seam/**` nor `docs/audit/seams/**`): G5's verdict does not
change, but its **dormancy rationale should be restated in roster terms and its
Battle Friend sentence removed as factually wrong.** The restated argument is
strictly stronger, because it is checkable by a committed probe and it names
the exact thing a future encounter change would break. The concrete triggers
G5 should carry, in ascending order of likelihood:

- an Ovicopter-style encounter where a per-creature-slot power sits on a
  **non-last** creature (already half true — the eggs are inserted *before* the
  Ovicopter, `monsters/hive/ovicopter.py:137-150`, so egg 1's `Hatch` ticks
  before eggs 2-3 and the Ovicopter move; dormant only because nothing reads a
  sibling's Hatch);
- fielding the Lagavulin Matriarch or a Thieving Hopper with a second enemy
  (both wake/stun their owner, and `wake_up` re-telegraphs the move, which is
  conformance-visible);
- a cross-enemy block or turn-start-power move (G5's existing Guardbot case).

## 2. LIVE gaps found in half B (both executed)

### 2.1 `rampart` — C#'s extra-turn guard is missing, and player extra turns ARE reachable

`RampartPower.cs:23` returns early when
`CombatManager.Instance.PlayersTakingExtraTurn.Count > 0`, so Living Shield's
25 Block for every Turret Operator is **not** granted on a player's extra turn.
`_playersTakingExtraTurn` is filled during the side switch
(`CombatManager.cs:1366-1369`) and read inside `StartTurn`
(`CombatManager.cs:435,439`), so it is non-empty when
`Hook.AfterSideTurnStart` fires at `CombatManager.cs:522` for that turn. The
sim's extra-turn path (`combat.py:648-652`) calls `player.start_turn()` with no
such flag, and `RampartPower.on_player_turn_start` (`powers.py:2994-3002`)
grants the block again.

**Executed.** `TURRET_OPERATOR_WEAK` (`[LivingShield(rampart 25),
TurretOperator]`) plus the ported relic **Pael's Eye**: the Turret Operator has
**25** block after the turn-1 start (control — correct in both models); zero it,
end the turn without playing a card so Pael's Eye claims the extra turn
(`relics/paels_eye.py:36-40`), and the sim leaves it on **25** where the game
leaves it on **0**.

**Rule-6 co-occurrence, stated explicitly.** Pael's Eye comes from the ported
Act-2 (Hive) Ancient **Pael** (`events/pael.py:53`, `pool3`), Living
Shield/Turret Operator is a ported Act-3 (Glory) weak encounter
(`monsters/glory/turret_operator.py:112-114`,
`monsters/glory/__init__.py:60`), and relics persist across acts — one run holds
both trivially. `py tools/audit/power_slot_probes.py extra-turns` enumerates the
sim's extra-turn sources: `relics/paels_eye.py` is the only one, and it is real
ported content.

Rampart also has the ordinary `AfterSideTurnStart → on_player_turn_start`
pre-draw slot error (the main report's section-5 table, same shape as
`demon_form`); on its own that half is dormant because the block lands on
enemies.

### 2.2 `flutter` — the stunned hopper's move is re-rolled on the WRONG RNG STREAM

`FlutterPower.cs:47` takes the follow-up state from the last logged state on the
**MonsterAi** stream:
`Owner.Monster.MoveStateMachine.StateLog.Last().GetNextState(base.Owner,
base.Owner.Monster.RunRng.MonsterAi)`. The sim calls
`machine.roll_move(self.owner, self.owner._rng)` (`powers.py:2233-2235`) — the
monster's **construction** rng, not `_move_rng`. Every other move roll in the
sim goes through `MachineMonster._move_rng`
(`monsters/state_machine.py:306-312`), which is
`self._hooks.combat.combat_rng.monster_ai` and whose own comment says move
selection "happens on the MonsterAi stream (mirrors MonsterModel.RollMove(...) =>
MoveStateMachine.RollMove(..., RunRng.MonsterAi))" and that "`self._rng` … is
untouched".

**Executed** on a parity combat (`RunRngSet("933T39V18D")`,
`THIEVING_HOPPER_WEAK`): `combat_rng.is_parity` is `True`, `hopper._rng` is a
plain `random.Random` while `hopper._move_rng` is a `GameRandomAdapter`, and
`_rng is _move_rng` is `False`. So the roll draws from the wrong stream **and
does not advance MonsterAi at all**.

Same defect class as the already-recorded `aggression` (wrong RNG stream), and
**LIVE**: the Thieving Hopper is ported Hive content, it self-applies Flutter
(`monsters/hive/thieving_hopper.py:113-114`), and exhausting those stacks with
powered attacks is the ordinary way to fight it — so any conformance replay that
stuns a hopper diverges on the move chosen *and* on every later MonsterAi draw.
Secondary: `roll_move` **mutates** the machine's current state where C#'s
`StateLog.Last().GetNextState(...)` queries the last *logged* state, which is a
different state once a `ConditionalBranchState` is involved.

This one is worth flagging to the conformance-parity work directly, not just to
the gap queue: it is a replay-divergence source in a ported act-2 encounter.

### 2.3 `power_cmd` G6 is LIVE — `adaptable` demonstrates the interaction G6 says is undemonstrated

`power_cmd`'s **G6** ("No `CombatManager.IsEnding`/`CanReceivePowers` guard
backstop in `PowerCmd.apply`") ends with: *"No concrete broken interaction is
demonstrated (spot-checked callers apply powers only to already-resolved
targets)."* **That is now falsified.**

`AdaptablePower.ShouldAllowHitting` (`AdaptablePower.cs:44-51`) exists for one
stated reason — its own doc comment is *"This is so the Test Subject doesn't
receive **powers** while it is reviving"*. C#'s `PowerCmd.Apply<T>` honours it
through step 2's `CanReceivePowers`, which reuses `Hook.ShouldAllowHitting`. The
sim wires `should_allow_hitting` into `DamageCmd.deal` (`cmds.py:51-52`) and
**not** into `PowerCmd.apply`, which has no such guard at all.

**Executed.** A `TEST_SUBJECT_BOSS` combat (the boss starts with powers
`['adaptable', 'enrage']`), a lethal Strike, then Vulnerable 2 from the player:

```
after lethal hit: is_reviving True  hp 1  is_dead False
should_allow_hitting(ts): False
sim: vulnerable on the reviving Test Subject -> Vulnerable(2)
control -- damage while reviving is refused by the sim too: 0
```

The control is the important half: damage **is** refused, so the predicate is
correctly wired for one pipeline and missing from the other. Rule-6
co-occurrence: the Test Subject is the ported Act-3 Glory boss and self-applies
`adaptable` at combat start; Bash/Vulnerable is ported basic-pool Ironclad
content; and the revive window is simply the rest of the player's turn after the
killing blow. `IllusionPower` and `ReattachPower` carry the identical override,
so all three records cross-reference it. **Reported, not edited** — half B owns
neither `audits/seam/**` nor `docs/audit/seams/**`.

### 2.4 `minion` and `reattach` — `ShouldOwnerDeathTriggerFatal` has no sim hook, and Feed pays out on a minion

C# reads `ShouldOwnerDeathTriggerFatal` at three card sites — `Feed.cs:38`,
`HandOfGreed.cs:49`, `TheHunt.cs:41` — each computing
`cardPlay.Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())` **before**
the attack. `MinionPower` returns `false` (`MinionPower.cs:20-23`) and
`ReattachPower` returns `AreAllOtherSegmentsDead()`
(`ReattachPower.cs:106-109`). The sim has no such hook anywhere in `hooks.py`,
and `cards/feed.py:45` tests only `target.is_dead`.

**Executed.** Feed played into a 4-HP Tough Egg carrying `MinionPower 1`:

```
egg WITH minion   : (['hatch','minion'], is_dead=True, max_hp delta 3)   <- sim
egg WITHOUT minion: (['hatch'],          is_dead=True, max_hp delta 3)   <- control
game WITH minion  : shouldTriggerFatal=False -> max_hp delta 0
```

Rule-6 co-occurrence: Feed is a ported Rare Ironclad Attack; Tough Eggs receive
`MinionPower` from the ported Act-2 Hive Ovicopter
(`monsters/hive/ovicopter.py:153`), which lays up to five of them; the Kin
Followers are a second ported source. Hand of Greed and The Hunt are unported,
so Feed is the whole live surface — and it is enough. The fix is a
`should_owner_death_trigger_fatal` hook plus one line in `cards/feed.py`.

**A second, opposite-direction consequence on `adaptable`:** `AdaptablePower`
does *not* override `ShouldOwnerDeathTriggerFatal`, and in C# the Test Subject
genuinely dies, so `WasTargetKilled` is true and **the game grants the +3 max HP
for Feeding the Test Subject to death**. The sim prevents the death, so
`target.is_dead` is False and it grants nothing — and `cards/feed.py:17-18`'s
docstring asserts the opposite ("death-prevented targets such as Illusions don't
count, which falls out of the is_dead check here"). That reasoning is right for
Illusion (which auto-applies Minion) and **wrong for Adaptable**.

### 2.5 `suck` — `AfterAttack` ported onto the per-hit hook, and here it costs damage

C#'s `AfterAttack(choiceContext, AttackCommand command)` fires **once** per attack
command with the whole `command.Results`, so `SuckPower` counts the connecting
hit groups and applies `base.Amount * num` Strength once, *after* the attack
(`SuckPower.cs:28-46`). The sim ports it onto `on_damage_received`
(`powers.py:1614-1630`), which fires **per hit and inside the damage pipeline**,
so hit 2 of a multi-hit attack is boosted by the Strength hit 1 earned. The sim
has the right slot and does not use it: `hooks.py:361` `after_attack`, which
Vigor and Gigantification already use.

**Executed.** The ported Underdocks Fossil Stalker's LASH is `_LASH_DMG = 3` ×
`_LASH_HITS = 2` (`monsters/underdocks/fossil_stalker.py:22-23,72`):

```
player hp: 80 -> 71   total lost: 9     <- sim
stalker strength after: Strength(6)     <- correct on both sides
game: AfterAttack fires once after the whole 2-hit LASH -> 3 + 3 = 6
```

The total Strength is right (6 on both sides); only the mid-attack damage is
wrong, by 50%. No co-occurrence needed — it is the first Fossil Stalker LASH the
player fails to fully block, in ported act-1 content. This is the third instance
of the main report's `curl_up` / `skittish` defect (section 4 items 5 and 14),
and the first where the inline effect is **damage** rather than block.
`painful_stabs` is the fourth instance and is dormant, because its inline effect
is Wounds in the discard, which nothing mid-attack reads.

## 3. New recurring gap shape: the *substituted* guard `is_dead` for `participants.Contains(Owner)`

Four half-B units (`high_voltage`, `territorial`, `nemesis`, and — for the
`Enemies` list rather than participants — `rampart`) replace C#'s
`participants.Contains(base.Owner)` / `CombatState.Enemies` with an
`is_dead` / `not is_gone` test. These are **not the same predicate**: a corpse
the combat *retained* is still a side participant in C# (the "death does not
mean removal" finding; `combat.py:292` keeps a retained corpse taking turns), so
the game still grants it Strength/Block where the sim refuses.

`nemesis` is one degree worse: its early return also **skips the toggle**
(`powers.py:3435` returns before `_should_apply = not _should_apply`), so an
owner dead for one side end and alive for the next resumes on the wrong beat.

All dormant today — the only ported retain-after-death mechanism is
`ReattachPower` on Decimillipede segments, which never carry these powers — but
the trigger is *ported classes*, not unported ones: `illusion`, `reattach`,
`adaptable`, `infested`, `steam_eruption`, `stock` and `surprise` all override
`ShouldCreatureBeRemovedFromCombatAfterDeath` or `ShouldStopCombatFromEnding`,
and all seven are in half B's remaining 33. **This shape is a checklist line
for `PROMPT.md`** (section 6).

This is distinct from the prompt's shape 8 ("a guard the sim ADDS") because the
sim did not add a guard — it *translated* one, and the translation is lossy.

### 3b. Batch 2's own recurring shape: `should_die` standing in for `AfterDeath`

Four half-B units re-express C#'s *"the creature dies, is retained in combat, and
its `AfterDeath` listener flips it into a revive state"* as *"prevent the death
from `should_die`"*: `adaptable`, `illusion`, `steam_eruption` and — going the
other way — `reattach`, which uses the real hooks and is the odd one out.

The substitution produces three observables:

1. **HP 1 vs 0.** `cmds.py:112` floors a prevented death at 1 HP; C# leaves the
   creature at 0 HP and dead. Conformance asserts on HP directly.
2. **`damage_pipeline` G4.** C# locks the `AfterDamageReceived`-skip to the
   pre-`Kill()` snapshot, so an arithmetically lethal hit permanently skips the
   victim's on-damage-received powers; the sim resets HP to 1 *first* and only
   then tests `target.is_dead` (`cmds.py:121`), so those powers fire. Cross-ref,
   not re-verdicted.
3. **`is_dead` readers.** `cards/feed.py:45` is one (section 2.4);
   `combat.py:272-277`'s win check is another.

`steam_eruption` is the model of how to do it: it *documents* the substitution
and then repairs the only observable it produces, restoring
`hp = max_hp = 999_999_999` from `on_damage_received`
(`powers.py:2022-2033`) to mirror C#'s `SetMaxAndCurrentHp(999999999)`. That is
why it is a `deliberate-divergence` and `adaptable`/`illusion` are `gap`s. Note
the irony: its repair *depends* on G4's divergence — a prevented death must fire
`on_damage_received` for the restore to run, and in C# it would not.

### 3c. Two absent death-time machineries, reported not verdicted

Both are engine-wide absences rather than any one power's divergence, so they are
recorded here and each unit's record cross-references them:

- **`ShouldStopCombatFromEnding` has no sim hook.** C# reads it inside the win
  check (`Hook.ShouldStopCombatFromEnding`, `CombatManager.cs:196`); the sim
  decides the win purely from `is_gone` over the non-minion enemies
  (`combat.py:272-277`). All five ported overrides (`adaptable`, `infested`,
  `steam_eruption`, `stock`, `surprise`) happen to be paired with a death
  prevention or a mid-death spawn that keeps `_all_enemies_dead()` false on its
  own, so it is dormant — but a future power wanting to hold combat open without
  doing either has nothing to hook.
- **`ShouldPowerBeRemovedAfterOwnerDeath` is inverted-by-omission.** C# strips a
  dead creature's powers at `CreatureCmd.cs:533` (`RemoveAllPowersAfterDeath()`,
  then each power's `AfterRemoved`) and the **default is `true`**. The sim never
  removes powers on death at all. So every power that *overrides it to `false`*
  (`adaptable`, `minion`, `reattach`, `steam_eruption`) is satisfied for free,
  and every power that does **not** override it should be stripped and is not.
  That is a one-line-per-site engine gap for the gap-fix stream, and it is the
  reason several units in this batch add their own `_expire()` where C# adds
  none — those hand-rolled expiries are the sim compensating for the missing
  strip, one power at a time.

### 3d. Batch 3's shape: the dealer-side after-damage event the sim cannot express

`imbalanced` and `paper_cuts` both override C#'s **`AfterDamageGiven`** and both
are ported onto the victim's `on_damage_received`, filtered on
`dealer is self.owner`. The sim *has* a dealer-side event — `on_damage_dealt`
(`hooks.py:469`) — and neither uses it, for a reason that is itself the finding:
`cmds.py:123` fires it only `if dealer is not None and hp_lost > 0`, so **the
sim's dealer-side event cannot see a fully blocked or zero-damage hit at all**,
which is precisely what `ImbalancedPower` keys on (`result.WasFullyBlocked`).

Consequences of the substitution: `cmds.py:121`'s killing-blow guard suppresses
the sim's hook when the hit killed the *victim* — and `cmds.py:119-120`'s own
comment says "AfterDamageGiven (on_damage_dealt) is not guarded and still fires
on the kill" — so both powers silently stop working on a lethal blow in the sim
and keep working in the game. Both are dormant (the lethal-blow case is only
observable through a death prevention, and on that path `cmds.py:112` sets
`hp = 1` so the sim fires after all), but the fix is a real one: give
`on_damage_dealt` the C# firing condition.

### 3e. Two more `AfterRemoved` bodies hand-inlined at a single call site

`burrowed` (dump all block) and `vital_spark` (clear every Tainted affliction)
both have behavioural C# `AfterRemoved` bodies and no sim `AfterRemoved` slot, so
both hand-inline the work at *one* removal site — `on_block_broken` and
`on_death` respectively. Every other removal route therefore skips it. Both are
dormant **only because the sim never strips powers on death either** (section
3c), so death is not currently a second removal route — the two gaps cancel, and
**fixing either one alone re-opens the other.** That coupling is worth carrying
into the gap queue as a pair rather than as two independent items.

## 4. Non-dyadic multiplicative factors — no fourth one in half B

Answering the prompt's loud question: **no**, and now for all 48 units rather
than for a batch. The census enumerates **26 literal multiplicative operands
across all 134 ported powers, of which 2 are non-dyadic** — and both were already
named. Half B's four factors are Flutter `0.5`, Soar `0.5`, Surrounded `1.5` and
Slow `0.1`. The four shapes the coordinator flagged as worth a close look turn
out not to be multiplicative at all: `hardened_shell` is a `min()` HP-loss cap,
`rampart` is an unpowered block *grant*, `dampen` has no numeric modifier, and
`withering_presence` is an integer countdown. Combined with half A's finding
(`no_block` ×0.0, `diamond_diadem` ×0.5, `unmovable` ×2.0, `gigantification` ×3,
all dyadic), **`hook_dispatch` G9's factor population is now closed at three:
Shrink `0.7`, Slow `0.1`, and the computed `Vulnerable + Cruelty` factor.** The
first three are dyadic; `0.1` is the one the main report's section 3 already
raised as G9's second missing factor, and it is in half B (`slow`). Both `0.5`s
were checked against the game data rather than assumed: `SoarPower.cs:17` and
`FlutterPower.cs:24` both declare `CanonicalVars = new DynamicVar(
"DamageDecrease", 50m)` and both return `BaseValue / 100m`, so the sim's
hard-coded `0.5` is exact. So `hook_dispatch` G9's factor population is
**Shrink 0.7, Slow 0.1, Vulnerable+Cruelty computed** — unchanged by half B, and
now checked from both ends.

## 5. Other cross-record notes under rule 3

1. **`damage_pipeline` G3's population, independently reproduced and confirmed.**
   `py tools/audit/power_slot_probes.py ungated-modifiers` walks every
   `public override decimal Modify{Damage,Block}{Additive,Multiplicative}` under
   `src/Core/Models` and classifies it by whether the body self-gates on
   powered-ness: **37 gated, 9 ungated**. The ungated nine are `HangPower`,
   `ShadowmeldPower`, **`SurroundedPower`**, `UnmovablePower`,
   `MockRevivePower`, `PaelsLegion`, `Vambrace`, `VitruvianMinion` (×2).
   `damage_pipeline` G3 already names `SurroundedPower` by name and
   `creature_card_cmds` G1 already covers the block side (LIVE via Vambrace), so
   **no new gap** — this is a confirmation found by looking for a counterexample,
   and it is worth as much as a contradiction. `HangPower`/`ShadowmeldPower` are
   unported (no sim class), so the damage-side population is complete.
   `UnmovablePower` is **half A's unit** and inherits `creature_card_cmds` G1's
   LIVE verdict; flagged here so half A does not verdict it independently.
2. **`turn_structure` G11's content list is confirmed correct as re-derived.**
   G11's fix pass says `AsleepPower`'s `BeforeSideTurnEndVeryEarly` went onto
   `on_enemy_turn_`**`start`** — one slot *further* from the C# position than its
   first draft said. Re-read: correct (`powers.py:1853-1857`, whose own comment
   says "Mirrors BeforeSideTurnEndVeryEarly"). `SandpitPower`'s
   `BeforeSideTurnEnd` — also on G11's list — turns out to be pure presentation
   (`SandpitPower.cs:139-145` is a position tween), so the missing slot costs
   nothing for it; G11 could say so.
3. **`hook_dispatch` G7's single whole-suite hit is `nemesis`, and it is
   faithful.** G7's `stale_listener_plugin` found exactly one instrumented
   miss — `on_enemy_side_end → IntangiblePower` ×10, Nemesis removing Intangible
   mid-dispatch — and G7 records that C# makes the same call because the
   `PowerModel` arm of `CombatState.Contains` (`CombatState.cs:599`) checks only
   `Owner.CombatState != null`. Auditing `nemesis` from the content side agrees.
4. **`hook_dispatch` G4 (LIVE) has two new per-unit consequences**: `strangle`
   deals its unblockable damage **once** per replayed card where C# deals it
   per `CardPlay` iteration, and `slow`'s counter advances by 1 instead of by
   `playCount`. Both inherit G4's verdict, not re-verdicted.
5. **`power_cmd` G5's `InstancedPerApplier` half now has its sharpest
   statement.** `strangle` is the only ported `InstancedPerApplier` power, and
   it is dormant **by scope** (one player = one applier), not by content — so
   unlike the rest of G5 it will not become live by porting more Ironclad
   content. Worth adding to G5.
6. **`power_cmd` G5's documentation count is wrong: it is 3 of 11, not 2.** G5
   says only `ToricToughnessPower` and `TheBombPower` "explicitly document the
   approximation and hand-roll a workaround" while "the other nine do not
   acknowledge the distinction at all". **`SwipePower` is a third**: its
   docstring (`powers.py:2238-2247`) explains the per-stolen-card instancing and
   bundles the instances into one `stolen_cards` list. `SwipePower` should move
   out of the nine.
7. **`wasRemovalPrevented` is misnamed in the decompiled source, and the obvious
   reading is wrong.** It is passed `true` when **`Hook.ShouldDie` returned
   false** (`CreatureCmd.cs:566`) and `false` on the real-death path
   (`CreatureCmd.cs:519`); it has nothing to do with
   `ShouldCreatureBeRemovedFromCombatAfterDeath`, which is computed separately at
   `CreatureCmd.cs:508` and never feeds the flag. So `!wasRemovalPrevented`
   means "the creature actually died". Ten half-B units guard on it, and reading
   it the other way would have produced ten wrong verdicts. The sim satisfies it
   structurally (`hooks.on_death` fires only on the should_die-true branch), so
   all ten are faithful; the residue — the sim has no `AfterDeath` dispatch at
   all for a prevented death — is dormant machinery, since no ported power acts
   on the flag being true. **This belongs in `PROMPT.md`.**
8. **`cards/base.py`'s `downgrade()` docstring is wrong, harmlessly.** It says
   it "Mirrors CardCmd.Downgrade: drop one upgrade level"; `CardCmd.Downgrade`
   → `CardModel.DowngradeInternal` (`CardModel.cs:2135-2148`) sets
   `CurrentUpgradeLevel = 0` — a full reset. Effects agree only because **no
   card in the game has `MaxUpgradeLevel > 1`**: `grep -rn 'override int
   MaxUpgradeLevel' src/Core/Models/Cards/` returns only overrides to `0` plus
   `Mocks/MockCardModel.cs`, and `grep -rn 'max_upgrade_level = [2-9]'
   sts2_rl/` returns nothing. Flagged for the **card stream**, since
   `dampen`'s restore loop depends on it.

## 6. Lessons for `tools/audit/PROMPT.md` (relic stream to fold in)

Half B did not touch `PROMPT.md`. Proposed additions, on top of the main
report's section 7 (all seven of which were still live checklist items and all
of which earned their keep this batch):

1. **New bug class — a *translated* guard, not a dropped one.** Section 3.
   Checklist line: *when C# guards on `participants.Contains(base.Owner)` or
   `CombatState.Enemies`, check what the sim substituted. `is_dead` /
   `not is_gone` is NOT the same predicate — a retained corpse is still a
   participant — and a substituted guard whose early return also skips a state
   mutation (Nemesis's toggle) is worse than a dropped one.*
2. **New bug class — RNG stream discipline on move re-rolls.** Section 2.2.
   Checklist line: *any sim code that re-rolls a monster's move must use
   `MachineMonster._move_rng` (the MonsterAi stream), never the monster's
   `_rng`. Grep for `roll_move(` and check the second argument.* This would have
   found `flutter` in one grep.
3. **`DynamicVars` defaults must be read, not inferred from the sim.** Soar and
   Flutter both hard-code `0.5` where C# reads
   `DynamicVars["DamageDecrease"].BaseValue / 100m`; both are right, but the
   only way to know is to read `CanonicalVars` — which the standard C#-dump
   grep filter (`grep -v ... CanonicalVars ...`) **deletes**. Checklist line:
   *un-filter `CanonicalVars` before believing any numeric constant that comes
   from a DynamicVar.* This is a real trap: the recommended dump command in the
   power continuation prompt hides exactly the line you need.
4. **`ShouldScaleInMultiplayer` is a one-line waiver** and shows up on 6 of
   half B's 48 units. Worth naming once in `PROMPT.md` rather than re-deriving.
5. **`wasRemovalPrevented` means "the death was prevented", not "the removal
   was prevented".** Section 5 item 7. Checklist line: *`AfterDeath`'s
   `wasRemovalPrevented` is set from `Hook.ShouldDie` returning false
   (`CreatureCmd.cs:566`), not from
   `ShouldCreatureBeRemovedFromCombatAfterDeath`. `!wasRemovalPrevented` == "the
   creature actually died". The sim's `hooks.on_death` fires only on that
   branch, so the guard is usually satisfied structurally — say so rather than
   calling it dropped.* Ten units in one batch turned on this.
6. **The death-time hook family the sim does not have.** Checklist line: *the
   sim has no `should_stop_combat_from_ending`, no
   `should_power_be_removed_after_owner_death`, no
   `should_power_be_removed_on_death` and no
   `should_owner_death_trigger_fatal`. It DOES have `should_die`,
   `should_remove_from_combat_after_death`, `after_preventing_death` and
   `should_allow_hitting`. Check which of the eight a unit's C# uses before
   believing any mapping.* Half B's batch 2 found one LIVE gap
   (`should_owner_death_trigger_fatal`) hiding in that list.
7. **A `should_die` port of an `AfterDeath` revive is a divergence, not a
   refactor.** Section 3b. Checklist line: *when C# lets a creature die and
   retains it (`ShouldCreatureBeRemovedFromCombatAfterDeath` false) and the sim
   instead prevents the death from `should_die`, the creature ends at 1 HP vs 0
   and `is_dead` disagrees — check every `is_dead` reader, `cards/feed.py`
   included.*

## 7. Harness / roster problems (half B owns neither; reporting per the contract)

Nothing new beyond the main report's section 8. Both of the harness defects the
coordinator warned about were checked against all 48 half-B files and **neither
bites in half B**:

- **Tuple-return overrides** (`public override (A, B) Name`): a grep of all 46
  half-B `*Power.cs` files returns nothing, so no hook is silently
  under-enumerated. Confirmed by reading every file in full as well.
- **A C# base class other than `PowerModel`**: every one of the 46 files declares
  `public sealed class XPower : PowerModel`. So the base-class blind spot half A
  hit on six units does not apply here. Note the near-miss worth recording: the
  **sim** side *does* subclass — `PossessStrengthPower` and `PossessSpeedPower`
  both extend `_PossessPower` (`powers.py:3075`) — but the harness enumerates the
  **C#** file's overrides, so the sim-side hierarchy is invisible to it either
  way and the records simply cite the base class's line numbers.
- The roster resolved all 48 units correctly; no `name_overrides.json` change is
  needed for any of them.
- **Roster mis-resolution in the *prompt*, not the harness:** the continuation
  prompt's half-B list includes `battleworn_dummy_time_limit`, which is really
  half A's (half A has audited it). Half B did **not** write that record. The
  live-roster check the prompt itself recommends is what caught it, which is an
  argument for keeping that step.

### 7b. The `combat._rng` class half A found — checked on all of half B, and it does not bite

Half A found **seven** power units reaching for `combat._rng` (the shared legacy
`random.Random`) where C# names a stream. Half B has exactly **three**
`combat._rng` uses, all in the same shape — a mid-combat monster spawn's
constructor, whose `Monster.__init__` rolls HP from the passed rng
(`monsters/base.py:78-79`): `infested` (`powers.py:1420`, Wriggler),
`surprise` (`powers.py:1703`, Sneaky/Fat Gremlin) and `stock`
(`powers.py:2981`, Axebot). **All three are repaired one level up and are
therefore faithful:** `CreatureCmd.add` calls `combat.assign_parity_hp(creature)`
(`cmds.py:254` → `combat.py:259-267`), which re-rolls a mid-combat spawn's HP on
the **Niche** stream against the current siblings, mirroring
`CombatState.CreateCreature`'s `SetUniqueMonsterHpValue`, and is a no-op in
legacy mode where the shared rng *is* the model. The repair is load-bearing
rather than vacuous — all three spawns really have HP variance (Wriggler 17-21,
Axebot 70-78, Gremlins 10-17). The constructor's `randint` still consumes a draw
from the unseeded shared rng in parity mode, which is harmless because no parity
content reads that stream. A guard entry recording this was added to each of the
three records.

The remaining `combat._rng` sites in `powers.py` (`:514` Aggression, `:792`,
`:1041` Stampede, `:2826`, `:3493`, `:3873`) are **half A's units**, which is
consistent with half A's count of seven.

**Where the RNG class DOES bite in half B is not `combat._rng` at all — it is
`flutter`'s use of the monster's own `_rng` instead of `_move_rng` for a move
re-roll (section 2.2), which is LIVE.** So the checklist line should be about the
*move-roll* accessor, not only about `combat._rng`.

Additionally confirmed for batch 2: **`ThieveryPower` and `HeistPower` — two of
the four unauditable powers (main report section 8 item 1) — are load-bearing
dependencies of `surprise`**, whose whole gold-return mechanism is expressed in
terms of them. So the 4-line `ALL_POWERS` fix is not merely coverage
bookkeeping: one audited unit's correctness currently rests on two units nobody
can record.

## 8. Cost data

- **Batch 1: 15 units.** Front-loaded cost was the four binding documents plus
  the two seam gap lists, then ~2 C# dumps of 7-8 files each with real line
  numbers, then one filler script.
- **6 of 15 units needed execution to settle** (`asleep`, `slumber`,
  `escape_artist`/`hatch`/`sandpit`/`hardened_shell` via the roster probe, plus
  the two live witnesses on `rampart` and `flutter` and the
  `hardened_shell` × The Boot ordering probe). Execution was decisive every
  time and **falsified a premise in the main report** (section 1 item 1), which
  is the second time in this stream that an executed check overturned an
  asserted one.
- **The efficient loop was unchanged**: `grep -n "" X.cs | grep -v …` on 7-8
  files at a time, read the sim classes with one dumper script, then one Python
  filler. The one change worth carrying: **do not filter `CanonicalVars`** out
  of the C# dump (section 6 item 3).
- **The batch gate is ~4m15s of `py -m pytest test/ -q`** and correctly never
  moves off 2476 passed / 31 xfailed.
- New reproducible tool: **`tools/audit/power_slot_probes.py`** (6 subcommands),
  committed alongside the records per the contract's "if a number comes from a
  script, commit the script" rule. It is the reproduction path for every number
  in section 1 and for the `ungated-modifiers` population in section 5.

## 9. Half B is COMPLETE — 48 / 48, nothing residual

Batch 3 (18 units) finished the half: `back_attack_left`, `back_attack_right`,
`hard_to_kill`, `mind_rot`, `waste_away`, `burrowed`, `slippery`,
`personal_hive`, `suck`, `painful_stabs`, `paper_cuts`, `imbalanced`, `plow`,
`galvanic`, `vital_spark`, `sloth`, `chains_of_binding`, `withering_presence`.

**Five half-B units came out fully `faithful`** — `personal_hive`,
`hard_to_kill`, `mind_rot`, `waste_away` and (modulo their marker-only nature)
`back_attack_left`/`back_attack_right`. That is a better ratio than the main
report's 2-in-45 and is worth carrying: the enemy powers that touch a single
well-defined modifier hook (`ModifyDamageCap`, `ModifyHandDraw`,
`ModifyMaxEnergy`) are ported cleanly; the ones that touch *turn structure*,
*death* or *whole-attack* hooks are where every gap lives.

What remains for the power kind overall is the **41 units of half A's original
scope plus the 4 unauditable ones**, not half B's business. The one thing half B
would flag for whoever picks the kind back up: of the four unauditable units
(`flex_potion`, `heist`, `speed_potion`, `thievery`), **two are load-bearing
dependencies of an audited half-B unit** (`surprise`), so the 4-line `ALL_POWERS`
fix has a real correctness consequence and not just a coverage one.

### The queue as it stood after batch 2, kept for the merge record — 18 units

Batch 2 (the death / minion / removal family, 15 units) is **done**:
`adaptable`, `illusion`, `infested`, `minion`, `ravenous`, `reattach`,
`steam_eruption`, `stock`, `surprise`, `swipe`, `crab_rage`, `dampen`, `hex`,
`possess_speed`, `possess_strength`. It was the right group to take second —
it yielded two of half B's four live gaps, both corrections to `power_cmd`, the
`wasRemovalPrevented` correction, and the section-3b/3c shapes.

Remaining, grouped the way batch 3 should be taken:

1. ~~The death / minion / removal family~~ — **done in batch 2.**
2. **Damage/block modifiers and per-hit reactors (10)** — `hard_to_kill`,
   `slippery`, `plow`, `personal_hive`, `paper_cuts`, `imbalanced`, `suck`,
   `painful_stabs`, `burrowed`, `galvanic`. Expect the before-hook-on-after-hook
   shape (`painful_stabs` and `suck` are `AfterAttack`, the same defect as
   `curl_up`/`skittish`) and the omitted-`props` shape.
3. **Card / energy / keyword powers (8)** — `chains_of_binding`, `sloth`,
   `mind_rot`, `waste_away`, `withering_presence`, `vital_spark`,
   `back_attack_left`, `back_attack_right`. The two `back_attack_*` are pure
   marker powers (`BackAttackLeftPower.cs:6` says so) and should be cheap;
   `withering_presence` carries `PowerInstanceType.Instanced`.

`on_stack -> pass` units still owed by half B: `burrowed`, `imbalanced`.
(`nemesis`, `soar`, `surrounded`, `adaptable`, `dampen` and `hex` are done —
`hex` is the one whose Amount is genuinely read, so it is the sharpest of the
15.) Half B also found the *inverse* class worth naming: `minion`, `illusion`,
`reattach`, `crab_rage`, `swipe`, `surprise`, `infested`, `possess_speed` and
`possess_strength` are `PowerStackType.Single` units that leave `Power.on_stack`
alone — i.e. they get Single **right**. Whoever folds these halves in should
report the ratio, not just the wrong 15.
