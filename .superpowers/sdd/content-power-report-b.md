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
| half-B units audited | 15 / 48 (batch 1) |
| power kind overall | 60 / 134 audited, 0 invalid, 0 stale |
| suite | 2476 passed / 31 xfailed at the batch-1 gate, unchanged |
| commits | batch 1: see the branch log |

## 0. Headline findings

1. **`turn_structure` G5 is settled and stays DORMANT — but its dormancy
   argument is wrong and one of its premises is false.** Section 1.
2. **Two NEW live gaps**, both executed: **`rampart`** drops C#'s extra-turn
   guard (Pael's Eye witness), and **`flutter`** re-rolls the stunned hopper's
   move on the **wrong RNG stream**. Section 2.
3. **No fourth non-dyadic multiplicative factor** in half B. Section 4.
4. One new **recurring gap shape** for `PROMPT.md`, plus an independent
   reproduction of an existing seam finding's population. Sections 3 and 6.

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

## 4. Non-dyadic multiplicative factors — no fourth one in half B

Answering the prompt's loud question: **no.** Half B's four multiplicative
factors are Flutter `0.5`, Soar `0.5`, Surrounded `1.5` and Slow `0.1`. The
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

## 7. Harness / roster problems (half B owns neither; reporting per the contract)

Nothing new beyond the main report's section 8. Specifically checked:

- `harness.list_overrides`'s tuple-return blind spot (section 8 item 2) did
  **not** bite in batch 1: no half-B C# file has a `public override (A, B) Name`.
  Verified by reading all 15 files in full.
- The roster resolved all 15 units correctly; no `name_overrides.json` change is
  needed for them.

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

## 9. Half B's residual queue — 33 units

Grouped the way batch 2 and 3 should be taken, with what is already known:

1. **The death / minion / removal family (15)** — `adaptable`, `illusion`,
   `infested`, `minion`, `ravenous`, `reattach`, `steam_eruption`, `stock`,
   `surprise`, `swipe`, `crab_rage`, `dampen`, `hex`, `possess_speed`,
   `possess_strength`. Highest expected yield: they are the units that override
   `AfterDeath` / `ShouldAllowHitting` /
   `ShouldCreatureBeRemovedFromCombatAfterDeath` /
   `ShouldPowerBeRemovedAfterOwnerDeath`, i.e. the exact classes section 3 names
   as the trigger for the substituted-guard shape. `possess_speed` /
   `possess_strength` are also the ported *readers* of the missing-`applier=`
   shape, so they should be audited before anything else that applies a power
   without an applier. `swipe` carries `PowerInstanceType.Instanced`
   (power_cmd G5) and `dampen`/`hex` carry `on_stack -> pass`.
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

`on_stack -> pass` units still owed by half B: `adaptable`, `burrowed`,
`dampen`, `hex`, `imbalanced`. (`nemesis`, `soar` and `surrounded` are done.)
