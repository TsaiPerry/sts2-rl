# Engine seam: `monster_state_machine`

Audited 2026-07-26 (Task 10, the **last** of the six seam audits, Tier 2 of the
source-audit-pipeline design). Verdicts and rationale live in
`audit/records/seam/monster_state_machine.json`; this file is the durable ordering
spec extracted from the C# source that the JSON record judges the sim against.

This seam is the **monster move-selection machinery**: the state graph
(`MonsterState` / `MoveState` / `RandomBranchState` / `ConditionalBranchState`),
the walk that turns "advance the machine" into "here is the next move", the
history-dependent weighting (`MoveRepeatType` + cooldowns keyed off
`StateLog`), the RNG stream the roll draws from, and the two external
overrides (`ForceCurrentState` / `SetMoveImmediate`, i.e. the move-machine half
of Stun). It does **not** own *when* the roll is called — that is
`turn_structure`'s, by its own boundary section.

Every "executed evidence" number below is reproducible from
`audit/tools/state_machine_probes.py` (probe name given at each site).

## Inherited prior art — verified, and what was wrong with it

`audit/tools/state_machine_probes.py` arrived from an interrupted earlier
attempt at this task: 396 lines, runnable, never validated, never reported,
never committed. Both of its load-bearing claims were re-derived independently
before anything was built on them.

1. **The 10-overload table is CORRECT.** Checked line by line against
   `RandomBranchState.cs:46-113`, including the delegation chains (`:75` →
   `:62`, `:95` → `:75`, `:105` → `:95`, `:100` → `:80` → `:46`, `:110` →
   `:85`). Every integer's role in the table matches the parameter it lands on.
   Reproduced in full below.
2. **The 61-site / 21-file census is CORRECT.** Re-derived by a completely
   different method — `grep -c AddBranch` per file minus `grep -c 'AddBranch("'`
   (the `CreatureAnimator.AddBranch(string, …)` overload, which shares the
   name) — giving 21 files summing to exactly **61**. The script's directory
   scope was also checked and is complete: `grep -rl
   "RandomBranchState\|ConditionalBranchState" --include=*.cs` over the whole
   game tree returns **only** files under `src/Core/Models/Monsters/` plus the
   machine's own directory, so nothing lives outside the glob, and the
   `Monsters/Mocks/` subdirectory the non-recursive glob skips contains no
   `AddBranch` at all. Every argument at all 61 sites is a **literal** (no
   named arguments, no int-valued variables, no arithmetic), which is why the
   script reports zero `UNRESOLVED` — and the classifier's one weak spot,
   confusing a `float` literal with a `Func<float>`, provably cannot change an
   answer, because the three overload pairs it could confuse
   (`:46`/`:80`, `:85`/`:90`, `:75`/`:95`) give the **same** int role in each
   pair.

**What was wrong with it.** Nothing in the two verified claims — but the script
as inherited answered a *narrower* question than the seam asks, and four things
were corrected or added (all in the committed version):

- **It had no `ConditionalBranchState` census at all.** `AddBranch` is only one
  of the two branch dispatchers; `AddState` is the other, and it is **41 call
  sites in 16 files** (`cs-conditional`). The inherited `hand-rolled` probe's
  "population exposed to the misreading" was therefore under-counted as a
  statement about the seam.
- **`addbranch-diff` compared the two censuses only by *presence*** — it
  printed the C# sites and the sim sites side by side and left the reader to
  eyeball them. It could not answer "does the port reproduce the semantics",
  which is the whole question. Replaced by **`mismatch`**, which resolves each
  C# branch to its full `(weight, repeatType, maxTimes, cooldown)` tuple and
  compares it position-by-position with the sim's, and by **`distribution`**,
  which executes the difference.
- **`move-rng` scanned only `sts2_rl/monsters/`,** so it could not see the one
  `machine.roll_move(...)` call site outside that package —
  `powers.py:2233` — which is precisely the site that uses the wrong stream
  (**G6**). It now walks `sts2_rl/` and reports the rng expression at every
  `roll_move` call.
- **A `UnicodeEncodeError`** (a `λ` in an f-string) crashed `mismatch` on this
  console's cp1252 codec, and `distribution` crashed on the monsters whose
  `build_machine` reads a constructor-set field. Both fixed.

`branch-order`, `hand-rolled` and `sim-addbranch` were kept as-is and are
correct.

**What the fix pass then found wrong in the *committed* version.** Six probe
changes, each forced by a number that would not reproduce:

- **`zero-weight` skipped 24 of the 83 ported machines** and only disclosed it in
  one line of prose, while three verdicts (steps 3, 15, 21) leaned on its
  coverage. Worse, the skipped set contained **`TwoTailedRat`, the named trigger
  of the very clause it was proving dormant.** A second pass now builds a **live
  instance** for anything the detached build cannot serve: 59 → **82 machines**,
  4,720,008 → **6,560,008 transitions**, one residual (`_Cultist`).
- **`nondyadic-weights` (new)** because breadth was still not enough: the one
  ported non-dyadic weight is a *lambda* the machine-only fuzz can never open.
- **`mismatch` printed no totals**, which is how "12 pairs / 7 match" drifted
  into "13 / 8". It now prints them.
- **`stun-sites` (new)** and **`whistle-route` (new)**: **G4** was LIVE on an
  unexecuted reachability claim, and all three monsters it named turned out
  unable to exhibit the observable. These two probes derive the real route.
- **`spawn-roll` (new)** for the `rollNewMove` hand-off that this record
  originally dropped (see the boundary section).
- **`raise-sites` (new)** to count what guard **N7** does and does not cover; its
  note said "two places" where the true answer is six.
- **`sources-sweep` resolved by basename**, a false-positive risk; now path-aware
  and line-number-aware (see the sweep note below).

## Source correction (Step A)

`SEAM_SOURCES["monster_state_machine"]` listed **one** game file
(`.../MonsterMoveStateMachine.cs`) and **one** sim file
(`sts2_rl/monsters/state_machine.py`). Both are real and both are the unit's
core — but the C# file listed is the *driver loop only*: it holds no branch
semantics, no repeat rules, no weights, and no stun handling. Everything this
seam's seed facts are about lives in its four siblings.

The table is now **41 game files + 45 sim files** (verified by the `sources-sweep` probe: every `.cs`/`.py` file the record or this doc cites with a line number is hashed; was 40+43 before the P3 correction pass added `SludgeSpinner.cs`/`soul_nexus.py`/`sludge_spinner.py` for the widened `mismatch` probe — see the "Gaps found" correction note). Added on the game side:

- **`.../MonsterMoveStateMachine/RandomBranchState.cs`** — the 10 `AddBranch`
  overloads (46-113), `GetNextState` (115-128) and `GetStateWeight` (130-167).
  Seed fact 1, steps 12-24, and gaps **G1**, **G2**, **G7** rest on it.
- **`.../MonsterMoveStateMachine/ConditionalBranchState.cs`** — the second
  branch dispatcher (39-54). Steps 25-27; guard **N3**.
- **`.../MonsterMoveStateMachine/MoveState.cs`** — `CanTransitionAway`
  (27-37), `FollowUpStateId`/`FollowUpState` (23-25), `GetNextState` (67-70)
  and the `OnExitState` reset (62-65). Steps 8-11; **G3**, **G4**.
- **`.../MonsterMoveStateMachine/MonsterState.cs`** — the base contract:
  `ShouldAppearInLogs`, `CanTransitionAway`, `IsMove` (9-19). Steps 1, 6.
- **`src/Core/MonsterMoves/MoveRepeatType.cs`** — the four-value enum. Seed
  fact 2.
- **`src/Core/Models/MonsterModel.cs`** — `RollMove` (415-418), which names the
  **`RunRng.MonsterAi`** stream, and `SetMoveImmediate` (420-432). Steps
  28-30; **G6**, **G5**. Already listed under `turn_structure`, which owns the
  *placement* of these calls — split by method, see the boundary section.
- **`src/Core/Entities/Creatures/Creature.cs`** — `StunInternal` (524-544), the
  move-machine half of Stun that `turn_structure` explicitly deferred here.
  Steps 31-34; **G4**, **G5**. Already listed under `turn_structure` and
  `creature_card_cmds`.
- **`src/Core/Commands/CreatureCmd.cs`** — `Stun` (863-890), the public entry.
  Step 31. Already listed under `creature_card_cmds`.
- **The 14 monster models the record cites with line numbers** — the five that
  made **G1** live until it closed 2026-07-28 (`FlailKnight.cs`, `HunterKiller.cs`,
  `ScrollOfBiting.cs`, `SpectralKnight.cs`, `FakeMerchantMonster.cs`), the two that read the same
  arguments **correctly** and are the counter-evidence that this is a port bug
  and not a machinery bug (`FossilStalker.cs`, `TwoTailedRat.cs`), the
  hand-rolled ports (`Flyconid.cs`, `TwigSlimeM.cs`, `LeafSlimeS.cs`,
  `Inklet.cs`, `PhrogParasite.cs`, `SlitheringStrangler.cs`), the pin
  monsters (`Mawler.cs`, `Fogmog.cs`), the `ConditionalBranchState` users
  (`Exoskeleton.cs`, `Fabricator.cs`), the stun-with-a-next-move case
  (`CeremonialBeast.cs`) and `KinPriest.cs` — the file `hook_dispatch` handed
  this record.
- **`src/Core/Models/Powers/IllusionPower.cs`** — the only
  `MustPerformOnceBeforeTransitioning` setter outside a monster model, and
  **G6**'s C# half via `FlutterPower`'s sibling pattern. (`FlutterPower.cs`
  itself is cited from `sts2_rl/powers.py`'s side and is listed in the record's
  evidence for **G6**; see the sweep note below.)

Added on the sim side (`state_machine.py` is the machine; the **ports** are
where the seam is actually violated):

- **`sts2_rl/monsters/base.py`** — `Monster.telegraph_next_move` (96-105), the
  no-op default, and the `Intent` vocabulary.
- **`sts2_rl/cmds.py`** — `CreatureCmd.stun` (208-218). **G4**, **G5**.
- **`sts2_rl/combat.py`** — the stunned branch of `_run_enemy_turns` (313-329).
- **`sts2_rl/creatures.py`** — the `stunned` flag (24).
- **`sts2_rl/powers.py`** — `FlutterPower`'s stun splice (2226-2235), the one
  `roll_move` call site outside the machine and the one on the wrong stream.
  **G6**.
- **The 13 sim monster ports** the record cites with line numbers:
  `hive/flail_knight.py`, `hive/hunter_killer.py`, `glory/scroll_of_biting.py`,
  `glory/knights.py`, `fake_merchant.py` (**G1**, CLOSED 2026-07-28),
  `underdocks/fossil_stalker.py`, `underdocks/two_tailed_rat.py` (correct),
  `overgrowth/flyconid.py`, `overgrowth/slimes.py`, `overgrowth/inklets.py`,
  `overgrowth/phrog_parasite.py`, `overgrowth/slithering_strangler.py`
  (hand-rolled), `overgrowth/mawler.py`, `overgrowth/fogmog.py` (pins),
  `hive/exoskeleton.py`, `glory/fabricator.py`, `hive/decimillipede.py`
  (**N3**), `overgrowth/ceremonial_beast.py` (**G5**),
  `overgrowth/the_kin.py` (**N6**).

The fix pass added, all cited with line numbers by **G4**'s corrected liveness
route or by steps 47-49: on the game side `src/Core/Combat/CombatSide.cs` (the
three-value enum behind step 48's truth table) and
`src/Core/Models/Monsters/SoulNexus.cs` (the Glory control monster whose three
branches are all `CannotRepeat`); on the sim side `sts2_rl/rooms.py` and
`sts2_rl/run.py` (the `tanx`-is-Glory-only and Glory-is-the-last-act facts),
`sts2_rl/relics/tanxs_whistle.py` (the grant), `sts2_rl/monsters/hive/bowlbugs.py`
and `sts2_rl/monsters/underdocks/corpse_slug.py` (why the two power-side stun
sites are inert), and `sts2_rl/monsters/hive/ovicopter.py`,
`.../hive/the_obscura.py`, `.../underdocks/living_fog.py` (spawn callers cited
by step 48's dormancy argument).

The rule applied is Task 8's, restated by `hook_dispatch`: *if a verdict's
liveness or dormancy argument cites a file with line numbers, that file is part
of the audited unit's evidence and must be hashed.* Deliberately **not**
hashed, for the reasons `hook_dispatch` gives: `test/*.py` (the pins),
`audit/tools/harness.py`, `audit/tools/dormancy_probes.py` and
`audit/tools/state_machine_probes.py` (the record's own machinery, re-runnable
by definition).

`sources-sweep` **now enforces that rule as written**, in two ways the first
pass did not. (1) **Resolution is path-aware.** It used to resolve every token
by *basename*, so a citation of `sts2_rl/cards/base.py` would have been
satisfied by the hashed `sts2_rl/monsters/base.py`. A token carrying a directory
must now match a hashed path by suffix; a bare basename is resolved against the
real trees first, and if several real files share the name the token is reported
as **AMBIGUOUS** with all candidates listed. One ambiguity survives and is
benign: `fake_merchant.py`, where **both** real files (`monsters/` and `events/`)
are hashed. The residual limitation is stated in the probe's docstring — for an
ambiguous bare basename the probe cannot know which candidate the prose meant,
so it accepts the token and flags it for a human. (2) **Only line-numbered
citations count.** Rule 7 says "cites a file *with line numbers*", so a bare
mention is reported as **NAME ONLY** rather than as a miss. Nine tokens land
there: the eight unclaimed hook-override models of boundary hole 5
(`Aeonglass.cs`, `Crusher.cs`, `LagavulinMatriarch.cs`, `Queen.cs`, `Rocket.cs`,
`SoulFysh.cs`, `TheInsatiable.cs`, `Vantom.cs`), named in a hole table and used
as evidence for nothing, plus the `sts2_rl/cards/base.py` in the paragraph
above, which is a worked example of the false positive rather than a citation.
Output as of the original pass: **194 tokens cited, 179 hashed, 0 NOT hashed,
6 excluded, 9 name-only, 1 ambiguous.** Current output (2026-08-03, after the
P3 correction pass added `SludgeSpinner.cs`/`soul_nexus.py`/`sludge_spinner.py`
to the widened `mismatch` probe's evidence and hashed them): **204 tokens
cited, 178 hashed, 1 NOT hashed, 8 excluded, 17 name-only, 1 ambiguous.** The
one NOT-hashed token, `Rng.cs` (→ `src/Core/Random/Rng.cs`), is **pre-existing
and unrelated to G1** — it comes from step 15's `Rng.cs:145-164` citation
(closed 2026-07-30, G7 clause b), not from anything this pass touched. It
predates this pass's edits (confirmed by re-running the sweep before making
any `.md` changes) and is left unfixed here per this pass's scope: it belongs
to a different mechanism, and rule 7's fix (adding `Rng.cs` to `game_sources`)
was not verified against that mechanism's own evidence in this pass. Flagged
as a live tooling defect for whoever next touches G7/step 15, not corrected.

### Scope boundary — what the six seams together do NOT cover

This is the last seam, so the holes are recorded here rather than lost.

**Split with `turn_structure`.** Its boundary section assigns
`MonsterModel.cs`'s *turn-loop call sites* (`SetUpForCombat`/`SpawnedThisTurn`
409-413, the *placement* of `RollMove`, `PerformMove`'s bracket 434-453,
`OnSideSwitch` 479-483) to itself and "everything inside the state machine" to
this record. Honoured exactly: this record verdicts what `RollMove` *returns*,
never where it is called from. Its **G9** (intents rolled per-monster instead of
one pass at player-turn start) is cross-referenced from **G6** here and **not**
re-verdicted.

**Split with `creature_card_cmds`.** It owns `Creature.StunInternal` as a
*creature mutator*; this record owns the same lines as a *move-machine
override* — the `MoveState("STUNNED", …)` construction and the
`FollowUpStateId` semantics. No overlap of observable. It also deferred **two**
things here, and both are now audited: its step 30 / guard N1 hand-off of the
stun's move-machine half (steps 38-41, **G4**, **G5**) and — picked up in the
fix pass, having been dropped by the first — its **step 3**,
`PrepareForNextTurn(rollNewMove: false)` for a monster added while
`CurrentSide != Enemy` (`creature_card_cmds.md:174-177`,
`CreatureCmd.cs:72-75`). That is steps **47** (`faithful`, the exactly-once
spawn roll) and **48** (**G9 clause b**, the suppression arms), executed by
probe `spawn-roll`.

**Split with `hook_dispatch`.** It owns the fact that the sim has no
`MonsterModel` listener category (its **G5**, dormant). It handed this record
`KinPriest.cs:81-108`'s `AfterDeath` as "Task 10's content finding". Picked up
and answered by execution below (**N6**) — the answer is that it is
presentation. It also told this record to start from the **12** C# monster
models that override an `AbstractModel` hook; only `KinPriest` was addressed,
and the other **11** are recorded as a hole below (item 5) and handed to the
content-monster stream.

**Behaviour in NO seam's scope.** Five things fall outside all six records and
are named here so the holes are documented:

1. **Per-monster move *content*** — what `SkitterMove` or `RitualMove` actually
   does, its damage numbers, its intent list. The six seams audit engine
   machinery; the ~121 `src/Core/Models/Monsters/*.cs` models are a
   **content tier** with no audit record of their own. `mismatch` covers the
   branch *parameters* of the 13 ported `RandomBranchState`s (12 sim modules)
   only.
2. **`AbstractIntent` and the intent vocabulary.** `src/Core/MonsterMoves/
   Intents/` is unaudited: the sim collapses a C# `AbstractIntent[]` into one
   `Intent` with an `also` tuple (`monsters/base.py:36-59`) and nothing checks
   that mapping. `MonsterModel.IntendsToAttack` (`MonsterModel.cs:241-245`)
   reads the intent list and gates ported content.
3. **`MonsterModel`'s non-machine surface** — `GenerateBestiaryMoveList`,
   `GetIntents`, `ResetStateMachine`, `CanonicalInstance`/`ToMutable`, HP
   generation and the Niche roll. Presentation and model-lifecycle; only
   `SetUpForCombat`/`OnSideSwitch` are claimed (by `turn_structure`).
4. **`EncounterModel` / monster-slot generation.** Which monsters spawn, in
   what slots, with what HP roll, is claimed by no seam. `hook_dispatch` names
   `AfterCreatureAdded` and this record names `SetUpForCombat`, but the
   selection itself is unaudited.
5. **Eleven C# monster models' `AbstractModel` hook overrides.** `hook_dispatch`
   (`hook_dispatch.md:184-190`) told this record to start from the **12** C#
   monster models that override an `AbstractModel` hook — enumerate them with
   `py audit/tools/dormancy_probes.py cs-monster-hooks`. Only **`KinPriest`** was
   addressed (guard **N6**, `waiver`: the whole override is a barks line plus a
   music parameter). The other **11 are audited by no seam and are not this
   record's to audit** — a hook override is per-monster *behaviour*, i.e.
   content tier, and boundary item 1 covers move content but not hook overrides:

   | model | overridden hook(s) |
   |---|---|
   | `Aeonglass.cs` | `AfterCardGeneratedForCombat`, `AfterDeath` |
   | `Crusher.cs` | `AfterCurrentHpChanged`, `BeforeDeath` |
   | `DecimillipedeSegment.cs` | `AfterDeath` |
   | `LagavulinMatriarch.cs` | `AfterDamageReceived`, `AfterDeath` |
   | `Queen.cs` | `AfterDeath` |
   | `Rocket.cs` | `AfterCurrentHpChanged`, `BeforeDeath` |
   | `SoulFysh.cs` | `AfterCardChangedPilesLate`, `AfterDeath` |
   | `TestSubject.cs` | `AfterDeath` |
   | `TheInsatiable.cs` | `AfterDeath` |
   | `Vantom.cs` | `AfterDeath` |
   | `WaterfallGiant.cs` | `AfterDeath` |

   Most are in ported pools (`rooms.py:124-207`), and at least one carries a
   *ported* mechanic that the hook is how the game implements —
   `LagavulinMatriarch.AfterDamageReceived` is the wake-from-damage path whose
   sim counterpart is `AsleepPower` → `wake_up(stunned=True)`
   (`underdocks/lagavulin_matriarch.py:75-87`). **Handed to the content-monster
   stream** with its own heading in
   `audit/prompts/2026-07-26-content-monster.md`.

## Seed facts, verified

1. **"AddBranch int args are cooldown/maxRepeats in some overloads, weights in
   others — enumerate every overload signature and document the arg roles."**
   Verified against `RandomBranchState.cs` and reproduced below — **with one
   correction to the seed fact's own wording: no `AddBranch` overload takes a
   weight as an `int`.** Every one of the 10 takes its weight as a `float` or a
   `Func<float>`; the `int` parameters are *only ever* `cooldown` or
   `maxRepeats`. The bug the seed fact comes from is therefore not "the same
   position means different things in different overloads" — it is that the
   **sim's `add_branch` puts `weight` in positional slot 2**
   (`state_machine.py:160-167`) where **C# puts `cooldown`/`maxRepeats`**, so a
   positional transliteration silently converts a repeat limit into a weight.
   **Five ported monsters did this** (**G1**, CLOSED 2026-07-28 — see below,
   and the correction note at the top of "Gaps found").
2. **"Repeat rules: CANNOT_REPEAT / CAN_REPEAT_X_TIMES / USE_ONLY_ONCE +
   cooldowns keyed off state_log."** Confirmed on both sides and the sim's
   implementation of the rules themselves is **faithful** —
   `RandomBranchState._effective_weight` (`state_machine.py:191-212`) is a
   correct transliteration of `GetStateWeight` (`RandomBranchState.cs:130-167`),
   including the "last *n* logged entries all equal this state" loop and the
   `IsMove`-filtered cooldown window. The gaps are in *what the ports pass in*,
   not in the rules. One machinery-level divergence remains (**G7**, the
   `maxTimes == 0` and total-weight-0 arms).
3. **"The game rolls moves at intent-display time from a dedicated MonsterAi
   RNG stream; sim uses the shared combat stream."** **This seed fact is STALE
   on its second clause and must not be recorded as written.** The sim's
   `MachineMonster._move_rng` (`state_machine.py:306-312`) returns
   `self._hooks.combat.combat_rng.monster_ai`, and every hand-rolled port that
   rolls a move does the same (executed: `move-rng` — the two
   `machine.roll_move` sites in `state_machine.py` and all five hand-rolled
   files). The SP3 parity work already fixed this. What survives is a **single
   residual site**: `powers.py:2233`, FlutterPower's stun splice, passes
   `self.owner._rng` — the shared combat stream — where
   `FlutterPower.cs:47` passes `RunRng.MonsterAi`. That is **G6**, and it is
   **dormant** — see the correction under **G6** below, which the pin itself
   forced by XPASSing.
   *Reconciliation with `turn_structure` (rule 3): `turn_structure`'s **G9** is
   about* **when** *the roll happens (per-monster at end-of-move vs one pass at
   player-turn start) and its observable is a missed draw on a stunned turn. It
   is not the same mechanism as this record's* **G6** *(a roll on the wrong
   stream at a different call site), so rule 3 does not force one verdict
   across them — but both are `gap`, both are about the `MonsterAi` stream, and
   they cross-reference each other. Neither record re-verdicts the other's
   site.*

## Numbered ordering spec

### The state contract — `MonsterState` (`MonsterState.cs:7-28`)

1. Three virtuals decide how a node behaves in the walk: `ShouldAppearInLogs`
   (default **true**), `CanTransitionAway` (default **true**), and `IsMove`
   (default `this is MoveState`). `MonsterState.cs:11-15`. The sim mirrors all
   three as class attributes plus a property (`state_machine.py:76-81`).
2. `GetNextState(Creature owner, Rng rng)` is abstract and returns a **string
   id**, never an object. `MonsterState.cs:17`.
3. `RegisterStates(Dictionary<string, MonsterState>)` is abstract; every
   concrete class implements it as `monsterStates.Add(Id, this)`.
   `MonsterState.cs:19`. **`Dictionary.Add` throws on a duplicate key** — the
   sim's `states[self.id] = self` (`state_machine.py:86-87`) silently
   overwrites. See **G8**.
4. `OnEnterState` / `OnExitState` are no-op virtuals.
   `MonsterState.cs:21-27`.

### The move node — `MoveState` (`MoveState.cs:11-81`)

5. A `MoveState` carries `Intents` (an `AbstractIntent[]`, **plural**), a
   `StateId`, an `_onPerform` delegate, and two follow-up fields:
   `FollowUpStateId` (a `string?`, `init`-only) and `FollowUpState` (a
   `MonsterState?`). `MoveState.cs:17-25`.
6. `IsMove => true` and `ShouldAppearInLogs` is inherited as **true**, so
   **only `MoveState`s ever reach `StateLog`** — both branch classes override
   `ShouldAppearInLogs => false` (`RandomBranchState.cs:37`,
   `ConditionalBranchState.cs:32`). This is why the cooldown window's
   `.Where(state => state.IsMove)` filter (`RandomBranchState.cs:160`) is a
   no-op in practice; the sim carries the same redundant filter
   (`state_machine.py:207`).
7. `CanTransitionAway` returns `_performedAtLeastOnce` when
   `MustPerformOnceBeforeTransitioning` is set, else `true`.
   `MoveState.cs:27-37`. Set at six sites: `CeremonialBeast.cs:150`,
   `DecimillipedeSegment.cs:155`, `TestSubject.cs:194`,
   `WaterfallGiant.cs:202`, `IllusionPower.cs:86`, and — the one that matters
   for Stun — `Creature.cs:540`.
8. `PerformMove` sets `_performedAtLeastOnce = true` **before** awaiting the
   delegate. `MoveState.cs:55-60`. Sim: `perform` does the same
   (`state_machine.py:129-131`).
9. `OnExitState` **resets** `_performedAtLeastOnce = false`, so the flag is
   per-visit, not per-combat. `MoveState.cs:62-65`; sim
   `state_machine.py:133-134`.
10. `GetNextState` returns `(FollowUpState?.Id ?? FollowUpStateId) ?? throw`.
    **The object wins over the string, and either is acceptable.**
    `MoveState.cs:67-70`. The sim has **only** the object
    (`state_machine.py:136-139`) — there is no string form. See **G3**.
11. The parameterless `MoveState()` constructor builds an `"UNSET_MOVE"` whose
    perform delegate throws; `MonsterModel.NextMove` is initialised to one
    (`MonsterModel.cs:239`) so a monster that has never rolled has a
    non-null but unusable move. `MoveState.cs:43-46, 77-80`. No sim analogue —
    `MachineMonster.__init__` rolls immediately (`state_machine.py:301`).

### The weighted branch — `RandomBranchState` (`RandomBranchState.cs:9-173`)

12. A branch is a `StateWeight` struct of five fields: `stateId`, `repeatType`,
    `maxTimes`, `weightLambda` and `cooldown`. `RandomBranchState.cs:11-31`.
    `GetWeight()` **throws** if `weightLambda` is null (23-30) — there is no
    "default weight" at read time; the defaults are supplied by the overloads.
13. **The 10 `AddBranch` overloads and every integer's role**
    (`RandomBranchState.cs:46-113`), verified line by line. `R` =
    `MoveRepeatType`; the last two columns are what the branch ends up holding.

| # | line | signature after `MonsterState state` | integer role(s) | delegates to | resulting `repeatType` |
|---|---|---|---|---|---|
| 1 | 46 | `int cooldown, R repeatType, Func<float> weight` | `int` = **cooldown** | *(base)* | the argument — **throws** if it is `CanRepeatXTimes` (48-51) |
| 2 | 62 | `int cooldown, int maxRepeats, Func<float> weight` | `int0` = **cooldown**, `int1` = **maxRepeats** | *(base)* | forced to `CanRepeatXTimes` (67) |
| 3 | 75 | `int maxRepeats, Func<float> weight` | `int` = **maxRepeats** | → #2 with `cooldown = 0` | `CanRepeatXTimes` |
| 4 | 80 | `int cooldown, R repeatType, float weight` | `int` = **cooldown** | → #1 with `() => weight` | the argument |
| 5 | 85 | `R repeatType, float weight` | *(no int)* | → #6 | the argument |
| 6 | 90 | `R repeatType, Func<float> weight` | *(no int)* | → #1 with `cooldown = 0` | the argument |
| 7 | 95 | `int maxRepeats, float weight` | `int` = **maxRepeats** | → #3 | `CanRepeatXTimes` |
| 8 | 100 | `int cooldown, R repeatType` | `int` = **cooldown** | → #4 with `weight = 1f` | the argument |
| 9 | 105 | `int maxRepeats` | `int` = **maxRepeats** | → #7 with `weight = 1f` | `CanRepeatXTimes` |
| 10 | 110 | `R repeatType` | *(no int)* | → #5 with `weight = 1f` | the argument |

    **No overload takes a weight as an `int`.** The weight is always a `float`
    or a `Func<float>`, and defaults to `1f`. The disambiguator is the type of
    the *second* argument: a bare `int` after the state is a **cooldown** when
    a `MoveRepeatType` follows it, and a **maxRepeats** otherwise.
    Census (`cs-addbranch`): **61 monster call sites in 21 files** — 28 use
    overload #10, 11 use #5, 9 use #9, 7 use #6, 4 use #8, 1 uses #7, 1 uses
    #1; zero unresolved. **15 of the 61 carry a non-default cooldown or
    maxRepeats**, in 10 files.
14. `GetNextState`: `max = States.Sum(GetStateWeight)`, one draw
    `num = rng.NextFloat(max)`, then walk the branches **in add order**
    subtracting each weight and returning the first with `num <= 0`.
    `RandomBranchState.cs:115-128`. **Add order is observable** — with equal
    weights the walk still resolves ties toward the earlier branch. The sim is
    a transliteration (`state_machine.py:178-189`) and uses the identical
    single-`NextFloat(total)` primitive (`_weighted_roll`, 31-44).
15. If the loop falls through, C# **throws** `InvalidOperationException`
    (127). The sim instead returns the **last** branch (189) — unreachable in
    both by the same float argument, and the sim's earlier total-weight guard
    (182-183) intercepts the only case that could reach it. See **G7**.
16. `GetStateWeight` (`RandomBranchState.cs:130-167`) computes
    `allowed * GetWeight()` in four arms, evaluated in this order:
17.  **`UseOnlyOnce`**: `allowed = 0` iff `StateLog.Contains(theState)` —
    reference containment over the whole log. `RandomBranchState.cs:134-141`;
    sim `state_machine.py:198-200`.
18.  **`CanRepeatForever`**: skipped entirely, `allowed` stays 1.
    `RandomBranchState.cs:142`; sim `state_machine.py:201`.
19.  **`CannotRepeat` / `CanRepeatXTimes`**: `n = 1` for `CannotRepeat`, else
    `maxTimes`. `allowed = 1` if `StateLog.Count < n`; otherwise walk the last
    `n` entries and set `allowed = 1` on the **first one that differs**, else
    leave it 0. Net effect: *blocked iff the last `n` logged moves are all this
    move.* `RandomBranchState.cs:142-157`; sim `state_machine.py:201-204`,
    which expresses the same thing as
    `0.0 if len(log) >= n and all(s is state for s in log[-n:]) else 1.0`.
20.  **Cooldown**, applied last and as an **early return of 0**, not a
    multiplier: if `cooldown > 0` and the state appears in the last `cooldown`
    `IsMove` entries of the log (newest first), the branch weight is **0**
    regardless of everything above. `RandomBranchState.cs:158-165`; sim
    `state_machine.py:206-209`. Note the cooldown check reads
    `stateWeight.stateId` by **string id** while the repeat arms compare by
    **object reference** — the sim mirrors both (`m.id == branch["state_id"]`
    vs `s is state`).
21. `maxTimes == 0` with `CanRepeatXTimes` is **permanently disabled** in C#:
    `n = 0`, `allowed = (Count < 0) ? 1 : 0` → 0, and the while-loop's
    `num3 < 0` guard is false so it never runs. The sim **raises `ValueError`
    at construction** instead (`state_machine.py:168-169`). See **G7**.
22. Only overload #1 validates its `repeatType` (throwing on
    `CanRepeatXTimes`, 48-51). The sim's `add_branch` has **no analogue** of
    that guard — its `max_times <= 0` check is a *different, wider* predicate
    (it also rejects `AddBranch(state, 0)`, which C# accepts: step 21). See
    **G8 clause c**.
23. `RegisterStates` adds **only itself** — a branch does not register the
    states it points at. `RandomBranchState.cs:169-172`. Every monster
    therefore passes a flat list of all its states to the machine constructor,
    and a state left out of that list is a `no valid state found` throw at
    roll time.
24. Branch **weights are lambdas evaluated at roll time**, so they can read
    live combat state — `TwoTailedRat.cs:124-127` returns `1f` or `1f/12f`
    depending on `CanSummon()`. Sim: `weight` may be a callable, evaluated in
    `_effective_weight` (`state_machine.py:211-212`).

### The conditional branch — `ConditionalBranchState` (`ConditionalBranchState.cs:8-60`)

25. `AddState(MonsterState move, Func<bool> condition)` appends a
    `ConditionalBranch` whose `Evaluate()` is `condition() ? 1 : 0`, and
    **`1f` when the lambda is null**. `ConditionalBranchState.cs:10-23, 39-42`.
26. `GetNextState` returns the **first** branch whose `Evaluate() > 0`, and
    **throws** if none match. `ConditionalBranchState.cs:44-54`. It ignores
    both its `Creature` and its `Rng` parameters — a conditional branch never
    draws. Sim `state_machine.py:228-232` is identical, including the raise.
27. Census (`cs-conditional`): **41 `AddState` call sites in 16 files**, and
    **0** of them omit the condition lambda — so the null-lambda arm is dead in
    the shipped content, and the sim's `condition=None` default
    (`state_machine.py:224-226`) is an unused convenience, not a divergence.

### The driver — `MonsterMoveStateMachine` (`MonsterMoveStateMachine.cs:8-88`)

28. Construction: register every state (`RegisterStates`), set
    `_currentState = _initialState`, and **log the initial state immediately
    if `ShouldAppearInLogs`** — so a machine whose initial state is a
    `MoveState` starts with a one-entry `StateLog`, and one whose initial state
    is a branch starts empty. `MonsterMoveStateMachine.cs:20-32`; sim
    `state_machine.py:236-245`. Identical.
29. `RollMove(targets, owner, rng)` → `FindNextMoveState(…, logMove: true)`,
    then **throws** if the state it landed on is not a move.
    `MonsterMoveStateMachine.cs:34-42`. `targets` is passed in and never used
    by any state's `GetNextState`; the sim's `roll_move(owner, rng)` simply
    omits it (`state_machine.py:247-253`).
30. `FindNextMoveState`'s two-part early return — **the initial-move sticky
    rule**: `if (!_currentState.CanTransitionAway || (!_performedFirstMove &&
    _currentState.IsMove)) return;`. Rolling before the first move has been
    *performed* leaves the move unchanged, so the opening move a monster
    telegraphs is its initial state, not a roll.
    `MonsterMoveStateMachine.cs:60-63`; sim `state_machine.py:262-266`.
    Identical, and `_performedFirstMove` is set by `OnMovePerformed` on both
    sides (49-52 / 259-260).
31. The walk: a `do…while (!_currentState.IsMove)` loop that calls
    `GetNextState`, **throws on an unknown non-empty id**, and treats a
    null-or-empty id as "go to the initial state".
    `MonsterMoveStateMachine.cs:64-75`. The sim treats **`None`** as the
    initial state (`state_machine.py:270-274`) and has no empty-string arm —
    equivalent, because no sim `get_next_state` can return `""`.
32. **Exactly one entry is logged per roll**, and it is the **first**
    loggable state entered during the walk, appended **after** the walk
    completes: `monsterState = (monsterState == null && ShouldAppearInLogs) ?
    _currentState : monsterState` inside the loop, `StateLog.Add(monsterState)`
    after it. `MonsterMoveStateMachine.cs:73, 76-79`; sim
    `state_machine.py:267, 275-280`. Identical — and since only `MoveState`s
    are loggable, "the first loggable state entered" is always the move the
    walk lands on.
33. `SetCurrentState` brackets every transition with
    `OnExitState()` on the old state and `OnEnterState()` on the new — **the
    old state's exit runs even when the walk passes through a branch**.
    `MonsterMoveStateMachine.cs:82-87`; sim `state_machine.py:282-285`.
34. `ForceCurrentState(state)` is `SetCurrentState(state)` with no guard —
    it does **not** log, does not check `IsMove`, and does not require the
    state to be registered. `MonsterMoveStateMachine.cs:44-47`; sim
    `state_machine.py:255-257`.

### The machine's drivers — `MonsterModel` (`MonsterModel.cs`) and Stun

35. `RollMove(targets)` is `NextMove = MoveStateMachine.RollMove(targets,
    Creature, RunRng.MonsterAi)` — **the dedicated `MonsterAi` stream, named at
    exactly this one site**. `MonsterModel.cs:415-418`. It is the *only*
    `RollMove` caller in the game (`Creature.PrepareForNextTurn` 546-554 and
    `CombatManager.AfterCreatureAdded` 860-867), plus one direct
    `GetNextState` call at `FlutterPower.cs:47`, which also passes
    `RunRng.MonsterAi`.
36. `SetMoveImmediate(state, forceTransition = false)`: **guarded by
    `NextMove.CanTransitionAway`** — a `MustPerformOnceBeforeTransitioning`
    move that has not yet been performed **cannot be overridden**, and the call
    is a silent no-op. Then `NextMove = state` *and*
    `MoveStateMachine.ForceCurrentState(state)`.
    `MonsterModel.cs:420-432`. See **G5**.
37. `SetUpForCombat` builds the machine, and the `MoveStateMachine` setter
    **throws if it is set twice** (`MonsterModel.cs:228-236`);
    `ResetStateMachine` (389-392) is the only way to clear it. The sim's
    `self.machine = …` (`state_machine.py:300`) is a plain attribute with no
    setter, no guard and no reset, so a rebind silently replaces a live machine.
    See **G8 clause b**. `turn_structure` owns the call placement.
38. **Stun, the move-machine half** (`Creature.StunInternal`,
    `Creature.cs:524-544`; entry `CreatureCmd.Stun`, `CreatureCmd.cs:863-890`).
    Guarded by `Monster != null` (throws for a player) and
    `CombatState != null && !IsDead`.
39.  If `nextMoveId` is null/empty it defaults to
    **`MoveStateMachine.StateLog.Last().Id`** — the move that was rolled for
    this turn. `Creature.cs:532-536`.
40.  A **synthetic `MoveState("STUNNED", stunMove, new StunIntent())`** is
    constructed with `FollowUpStateId = nextMoveId` and
    `MustPerformOnceBeforeTransitioning = true`, then handed to
    `SetMoveImmediate`. `Creature.cs:537-542`. Consequences, all of them
    machine-level: the stun **is** a move and is performed like one; it pins
    itself for exactly one turn (step 7); the roll at the start of the next
    player turn transitions `STUNNED → nextMoveId` with **no branch draw**
    (step 10 — `MoveState.GetNextState` is deterministic); and that roll
    **appends `nextMoveId` to `StateLog` a second time** (step 32), because the
    log entry from the pre-stun roll is still there. A stun therefore
    **duplicates the deferred move in the log**, which feeds every repeat rule
    and cooldown window afterwards (steps 17-20).
41. `FlutterPower.cs:47` is the one caller that computes `nextMoveId` itself:
    `StateLog.Last().GetNextState(Owner, Owner.Monster.RunRng.MonsterAi)`. Note
    what this does — it asks the **last logged MoveState** for *its* follow-up,
    which by step 10 is deterministic and returns the **branch's** id when the
    follow-up is a branch. So the `MonsterAi` rng it passes is **never
    consumed**, and the branch is resolved later, by the post-stun roll. See
    **G6**.

### The sim's machine — `sts2_rl/monsters/state_machine.py`

42. `MachineMonster.__init__` builds the machine and **rolls immediately**
    (`state_machine.py:300-301`), so `_current_move` is never the "UNSET_MOVE"
    placeholder. By step 30 that first roll returns the initial state unchanged
    and draws nothing when the initial state is a `MoveState`.
43. `_move_rng` is `self._hooks.combat.combat_rng.monster_ai`
    (`state_machine.py:306-312`) — the correct stream, and the docstring cites
    `MonsterModel.RollMove`.
44. `current_intent` returns `Intent(MoveType.STUN)` when `self.stunned`
    (`state_machine.py:315-318`) — the intent half of the stun is modelled,
    the machine half is not (**G4**).
45. `take_turn` performs, calls `on_move_performed`, then
    `telegraph_next_move` (`state_machine.py:320-330`) — the sim's stand-in for
    the game's turn-start pass. `turn_structure` **G9** owns that placement.
46. `Monster.telegraph_next_move` on the base class is a **no-op**
    (`monsters/base.py:96-105`), so a hand-rolled monster that forgets to
    override it never advances — silently.

### The spawn-roll contract (`CreatureCmd.Add`) — `creature_card_cmds`' hand-off

47. **A mid-combat monster spawn rolls its move exactly once, or not at all.**
    `CreatureCmd.Add` runs, in this order: (i)
    `await CombatManager.AfterCreatureAdded(creature)`, which rolls **iff**
    `creature.IsEnemy && _state.CurrentSide == CombatSide.Player`
    (`CombatManager.cs:860-867`); then (ii)
    `if (combatState.CurrentSide != CombatSide.Enemy && creature.IsMonster)` →
    `creature.PrepareForNextTurn(players, rollNewMove: false)`
    (`CreatureCmd.cs:72-75`). With the flag **false**, the whole body of
    `PrepareForNextTurn` (`Creature.cs:546-554`) reduces to
    `NCombatRoom…RefreshIntents()` — so step (ii) adds no mechanics, and the
    flag is a **double-roll guard**: it stops (ii) re-rolling what (i) already
    rolled. `PrepareForNextTurn` has exactly two call sites and only this one
    passes `false` (`CombatManager.cs:482` takes the default `true`; executed:
    probe `spawn-roll`).
48. The **suppression** side of the same flag. `CombatSide` has three values
    (`CombatSide.cs:3-8`), so the truth table is:

| `CurrentSide` | monster kind | rolls at (i) | (ii) reached | net rolls |
|---|---|---|---|---|
| `Player` | enemy | **yes** | yes, but `rollNewMove: false` | **1** |
| `Player` | non-enemy | no (`IsEnemy` fails) | yes, suppressed | **0** → `UNSET_MOVE` |
| `Enemy` | any | no (side fails) | no | **0** → `UNSET_MOVE` |
| `None` | any | no | yes, suppressed | **0** → `UNSET_MOVE` |

    The sim has no separate intent-preparation step at all: `CreatureCmd.add`
    (`cmds.py:237-266`) never rolls and `MachineMonster.__init__` rolls once
    (`state_machine.py:300-301`), unconditionally. The exactly-once row matches
    (step 47, `faithful`); every zero-roll row is **G9 clause b** (step 48).
49. A `RandomBranchState` the game **constructs and registers but never
    wires**: `Inklet.cs:69-71` builds `INIT_RAND` with two branches (one of
    them `AddBranch(JAB, 2, 1f)` = maxRepeats 2, overload #7), and nothing
    assigns it to a `FollowUpState`; it is not the initial state either.
    `PhrogParasite.cs:6-10` is the same shape. By step 23 registration says
    nothing about reachability, so the game holds a dead branch dispatcher.
    See **G2**.

## Sim comparison (Step C summary — full verdicts in the JSON)

The **machinery** is a close transliteration: steps 1-2, 4-9, 12, 14, 16-20,
23-26, 28-34, 42-45 and 47 are `faithful`, and the two branch classes'
`get_next_state` walks are line-for-line equivalents including the single
`NextFloat(total)` primitive. The seam's failures were, at the time this
section was written, concentrated in three places — **all closed today; see
the "Gaps found" correction note below**:

- **The ports' branch arguments** (**G1**, CLOSED 2026-07-28) — five monsters
  used to convert a C# `maxRepeats`/`cooldown` into a sim `weight`.
- **The stun override** (**G4**, **G5**; **G4** CLOSED 2026-07-27, checked
  this pass) — the sim used to model the *intent* of a stun and none of the
  *machine* consequences.
- **Machinery details** — the missing string follow-up (**G3**), the
  unrepresentable unwired branch (**G2**), the three unvalidated machine
  constructions (**G8**, steps 3/22/37), the degenerate-weight arms (**G7**),
  one wrong RNG stream at the one `roll_move` call site outside the machine
  (**G6**), and the ungated spawn roll (**G9**, steps 11/48).

**Verdict counts**, recomputed programmatically from
`audit/records/seam/monster_state_machine.json`, are stated in the JSON's own summary
and in `.superpowers/sdd/task-10-report.md`; do not copy them by hand.

### Gaps found

> **CORRECTION (2026-08-03, P3 pass).** This whole section was stale. It read
> "Two are LIVE — **G1** and **G4**" as though that were still true; it has not
> been true since **2026-07-27/28**. The JSON record (`audit/records/seam/
> monster_state_machine.json`) was updated at the time — every one of **G1**
> through **G9** now carries `"verdict": "faithful"` or `"deliberate-divergence"`
> with a dated `"issue"` documenting the closure, and `py audit/tools/
> gap_queue.py counts` reads **0 live / 0 dormant / 0 total** gap-verdicted
> entries for this seam today — but this doc, the human-readable half of the
> same record, was never brought back in sync, and a later investigation that
> trusted this section's "LIVE" label over the JSON would have filed a false
> gap. **G1** is corrected below, with the closure re-verified independently
> this pass (not just copied from the JSON): read all five C# sites and all
> five sim ports directly, re-ran `mismatch` (widened — see its note below),
> and re-ran the pinning tests
> (`test/test_hook_order.py::test_addbranch_int_args_are_repeat_limits_not_weights`,
> `test/test_monster_branch_audit.py::TestAddBranchIntArgsAreRepeatLimits`'s 11
> cases) — all green. **G4** was checked as a byproduct, because the paragraph
> this replaces named it in the same breath as G1: `sts2_rl/monsters/
> state_machine.py`'s `MonsterMoveStateMachine.stun` does build the synthetic
> `STUNNED` state described as missing below (`STUN_STATE_ID`,
> `must_perform_once_before_transitioning=True`), and
> `test_stun_makes_the_stun_a_move_and_relogs_the_deferred_one` passes — so G4
> is closed too. **G2, G3, G5–G9 were NOT independently re-verified by this
> pass** beyond the `gap_queue` count above; they read as closed in the JSON's
> own `"issue"` text (each with a date and an executed witness) but this doc's
> prose for them is left exactly as the first pass wrote it and should not be
> trusted without the same treatment G1 got here. Do not delete this note when
> editing nearby text — it is the record of why the two documents disagreed.

**Historically, two were LIVE on currently-ported content** — **G1** and
**G4** — and **seven were dormant** — **G2**, **G3**, **G5**, **G6**, **G7**,
**G8**, **G9** — each with its concrete unported (or un-contended) trigger
named and its dormancy argument **executed**, not asserted, at the time this
section was written. Two labels were CORRECTED after the first pass. **G6**
was written LIVE and demoted when its own strict xfail XPASSed (argument
under **G6** below). **G8** absorbed steps 22 and 37, which the first pass
verdicted `deliberate-divergence` and `faithful`: all three sites are one
mechanism and rule 3 forces one verdict (see **G8**). **G4** kept its LIVE
label but on a different — and executed — reachability argument (see **G4**);
only the route was wrong. **All nine are closed today; see the correction
note above.**

- **G1 — five ported monsters read a C# `maxRepeats`/`cooldown` argument as a
  sim `weight`. CLOSED 2026-07-28 (all five sites; the machinery's own
  reading — the `add_branch` signature itself — was already correct
  2026-07-27), and it was the same bug class as the shipped
  TwigSlimeM/Flyconid fix.** `RandomBranchState.AddBranch`'s positional slot 2
  is `cooldown` or `maxRepeats` (never a weight — see seed fact 1); the sim's
  `add_branch(state, weight=1.0, repeat_type=…, max_times=0, cooldown=0)`
  (`state_machine.py:160-167`) puts **`weight`** there, so a positional port
  used to convert one into the other. Each of the five now passes
  `max_times=`/`cooldown=` by **keyword** and leaves `weight` at its 1.0
  default — verified 2026-08-03 by reading all five C# sites
  (`FlailKnight.cs:49-57`, `HunterKiller.cs:42-48`, `ScrollOfBiting.cs:89-90`,
  `SpectralKnight.cs:52-53`, `FakeMerchantMonster.cs:55-58`) directly against
  `RandomBranchState.cs`'s overload table and all five current sim ports
  (`hive/flail_knight.py:53-58`, `hive/hunter_killer.py:44-49`,
  `glory/scroll_of_biting.py:60-68`, `glory/knights.py:111-116`,
  `fake_merchant.py:66-75`) line by line, plus each C# call's own comment
  identifying the overload it resolves to
  (e.g. `hive/flail_knight.py:50-51`: *"FlailKnight.cs:50-51 AddBranch(state,
  2) is the (state, int maxRepeats) overload — a repeat limit, not a
  weight."*). Executed (`mismatch`, **WIDENED 2026-08-03** — see the probe's
  own docstring; it used to resolve 12 of the 14 sim classes `hand-rolled`
  reports as ported onto the state machine, missing `SoulNexus`,
  `SludgeSpinner` and `TheObscura`, none of which could exhibit this bug
  since none has a non-default int argument in C#, but the coverage claim
  was not true of the probe's own output until now): of the **15** resolved
  C#↔sim pairs — one per ported sim *module*, together covering **16** C#
  `RandomBranchState`s because `fake_merchant.py` folds two (`RAND_MOVE`,
  `FakeMerchantMonster.cs:55-58`, and `RAND_ATTACK_MOVE`, `:66-68`) into one
  row — **all 15 match exactly and 0 misread**. (Before the fix, a first pass
  found 7 matched and 5 did not, having resolved only 12 pairs / 13 branch
  states; an even earlier pass had said "13 resolved / 8 match", having read
  the branch-state count as the pair count.) Per-monster pin:
  `test/test_monster_branch_audit.py::TestAddBranchIntArgsAreRepeatLimits`
  (11 cases, all green) plus
  `test/test_hook_order.py::test_addbranch_int_args_are_repeat_limits_not_weights`.

  **Correction to an earlier synthesis of this closure.** The JSON's own
  closure note (step 13) at one point named the five sites as "Flail Knight,
  Hunter Killer, **Mysterious Knight**, Scroll of Biting, Spectral Knight" —
  substituting Mysterious Knight for Fake Merchant. `MysteriousKnight.cs` is
  16 lines, overrides no `GenerateMoveStateMachine` at all, and inherits
  `FlailKnight`'s machine verbatim (confirmed by reading it, and by
  `audit/records/monster/mysterious_knight.json:38`, which shares text with
  `flail_knight.json` because it is the same underlying fix) — so it was never
  a distinct sixth site, and Fake Merchant's own `FakeMerchantMonster.cs:58`
  `AddBranch(ENRAGE, 3, MoveRepeatType.CannotRepeat)` is the genuine fifth.
  Fixed in the JSON in this pass.

  **What it looked like broken, preserved for history.** Before the fix, the
  five sites read:
  - `FlailKnight.cs:50,51` `AddBranch(FLAIL, 2)` / `AddBranch(RAM, 2)` =
    maxRepeats 2, weight 1 → `hive/flail_knight.py` had `weight=2.0`,
    `CAN_REPEAT_FOREVER`;
  - `HunterKiller.cs:43` `AddBranch(PUNCTURE, 2)` →
    `hive/hunter_killer.py` had `weight=2.0`;
  - `ScrollOfBiting.cs:90` `AddBranch(CHEW, 2)` →
    `glory/scroll_of_biting.py` had `weight=2.0`;
  - `SpectralKnight.cs:52` `AddBranch(SOUL_SLASH, 2)` →
    `glory/knights.py` had `weight=2.0`;
  - `FakeMerchantMonster.cs:58` `AddBranch(ENRAGE, 3,
    MoveRepeatType.CannotRepeat)` = **cooldown 3**, weight 1 →
    `fake_merchant.py` had `weight=_ENRAGE_WEIGHT` (`= 3.0`), no
    cooldown. The sim's own docstring used to record the misreading in prose:
    *"ENRAGE (+2 Strength, weight 3)"*; the current docstring
    (`fake_merchant.py:39`) reads *"ENRAGE (+2 Strength, cooldown 3)"*.

  Both halves of the divergence were observable, and both had been
  **executed** (`distribution`, 100000 rolls, seed 7, the broken sim machine
  vs the same machine with the C# parameters restored) before the fix:

  | monster | sim (broken) | game |
  |---|---|---|
  | FlailKnight | FLAIL 41.6% / RAM 41.6% / WAR_CHANT 16.8% | 36.2% / 36.4% / 27.4% |
  | HunterKiller | BITE 25.1% / PUNCTURE 74.9% | 40.0% / 60.0% |
  | ScrollOfBiting | CHEW 59.9% / CHOMP 20.0% / MORE_TEETH 20.0% | 42.9% / 28.6% / 28.6% |
  | SpectralKnight | SOUL_SLASH 75.1% / SOUL_FLAME 24.9% | 60.0% / 40.0% |
  | FakeMerchant | ENRAGE 30.0% / SWIPE 25.2% / SPEW 24.9% / THROW 20.0% | 13.6% / 29.7% / 29.4% / 27.4% |

  `distribution`'s hard-coded `_DIST_CASES` fixture still applies the C#
  parameters on top of *today's* (already-fixed) build to reproduce this
  table on demand — it is a regression fixture now, not a live finding.

  **Was LIVE, with both sides reachable on ported content** (rule 6): all
  five monsters are exported from ported encounter modules —
  `monsters/hive/__init__.py:26,31` (FlailKnight, HunterKiller),
  `monsters/glory/__init__.py:30,35` (SpectralKnight, ScrollOfBiting),
  `monsters/fake_merchant.py:117-120` (`FAKE_MERCHANT_EVENT_ENCOUNTER`, the
  ported `FakeMerchant` event's fight, `events/fake_merchant.py:26`). The
  observable was an enemy intent a player sees on screen and a replay
  records, plus a different `MonsterAi` draw sequence — now matching.
  *Counter-evidence that this was a port bug and not a machinery bug:*
  `FossilStalker.cs:58-60` and `TwoTailedRat.cs:127` carry the same argument
  shapes and their ports read them **correctly**
  (`underdocks/fossil_stalker.py:57` `max_times=2`,
  `underdocks/two_tailed_rat.py:83` `cooldown=3`).

- **G2 — the sim silently drops a `RandomBranchState` that C# builds but never
  wires. DORMANT** (step 49 — the fix pass gave it a numbered step, which it
  had lacked while appearing in this list, so the record's gap ids and its step
  list now agree). `Inklet.cs:69-71` constructs `INIT_RAND` and gives it two
  branches, one of them `AddBranch(JAB, 2, 1f)` = maxRepeats 2; it is never
  assigned to any `FollowUpState` and is not the initial state, so it is dead
  in the game too. `PhrogParasite.cs:6-10` is the same shape. The sim's
  hand-rolled ports reproduce the *reachable* graph and not the dead one, which
  is correct today — but the sim has no way to *represent* an unreachable
  registered state, so the moment such a state becomes reachable (a C# patch
  wiring `INIT_RAND`, or a re-port onto `MachineMonster`) the port silently
  keeps the old graph. Executed dormancy:
  `test/test_monster_branch_audit.py::TestInkletMoveSequence` and
  `::TestPhrogParasiteMoveSequence` assert 0 `monster_ai` draws on exactly the
  legs where `INIT_RAND` would have drawn. Concrete trigger: wiring
  `Inklet.cs:69`'s `INIT_RAND` into `initialState`.

- **G3 — `MoveState` has no string follow-up in the sim. DORMANT.**
  `MoveState.cs:23-25, 67-70` accepts **either** `FollowUpState` (an object) or
  `FollowUpStateId` (a string), resolving the object first; the sim's
  `MoveState` has only `follow_up: MonsterState | None` and raises when it is
  `None` (`state_machine.py:116, 136-139`). Executed:
  `grep -rn "FollowUpStateId" src/` returns exactly **two** sites —
  `Creature.cs:539` (Stun, which is **G4**'s subject and is not modelled at all)
  and the declaration itself. So no *monster model* uses the string form and
  the gap cannot fire through a port today. Concrete trigger: any monster
  model that sets `FollowUpStateId` on a `MoveState` — the natural use is a
  forward reference to a state constructed later in `GenerateMoveStateMachine`,
  which the sim would have to express as a two-pass build.

- **G4 — a stun does not touch the move machine in the sim, so the deferred
  move is not re-logged. LIVE.** C# (`Creature.cs:524-544`, step 40) replaces
  the current state with a synthetic `STUNNED` `MoveState`, performs it, and
  at the next roll transitions `STUNNED → StateLog.Last().Id`, **appending that
  id to `StateLog` a second time**. The sim (`cmds.py:208-218`) sets
  `target.stunned = True`, `combat.py:314-329` skips the turn and clears the
  flag, and `state_machine.py:315-318` shows a `STUN` intent — the machine's
  `current`, `state_log` and `_current_move` are all untouched. Executed
  (`stun-machine`, a `FossilStalker` because its branch is
  `CAN_REPEAT_X_TIMES(2)`, the rule the log length feeds):
  `current_move LATCH_MOVE -> LATCH_MOVE`, `machine.current 'LATCH_MOVE'`,
  `state_log ['LATCH_MOVE'] -> ['LATCH_MOVE']`. C# would reach
  `['LATCH_MOVE', 'LATCH_MOVE']` after the post-stun roll, which by step 19
  **blocks** LATCH's `CanRepeatXTimes(2)` branch on the following roll while
  the sim still allows it.

  **LIVE, and the route is Whistle into Glory** — executed end to end, because
  the first pass's liveness list was inert and its subject unreachable.

  1. **Only one sim stun takes an external target.** Probe `stun-sites`
     enumerates all **8** `CreatureCmd.stun` call sites in `sts2_rl/`: seven are
     self-stuns (`self` / `self.owner`, so the target is by construction the
     monster owning the move or power and can never be the player) —
     `hive/slumbering_beetle.py:68`, `overgrowth/ceremonial_beast.py:45`,
     `underdocks/lagavulin_matriarch.py:87`, `underdocks/terror_eel.py:65`,
     `powers.py:1601` (`RavenousPower`), `powers.py:2071` (`ImbalancedPower`),
     `powers.py:2227` (`FlutterPower`) — and one is external,
     `cards/whistle.py:38`.
  2. **Whistle is Glory-only.** `rooms.py:206` puts `tanx` in **Glory's**
     `ancient_keys` and in no other act's (overgrowth and underdocks are
     `('neow',)`, hive is `('orobas','pael','tezcatara')`), and
     `relics/tanxs_whistle.py:17` grants `make_card("whistle")` on pickup.
     Glory is act index **2**, the last act
     (`run._ACTS_BY_INDEX = [[overgrowth, underdocks], [hive], [glory]]`), so
     the stun-reachable population is Glory's own pools — **not** any earlier
     act's monster, because a relic cannot be carried backwards.
  3. **Glory's pools hold four `RandomBranchState` machines whose weights read
     the state log** (probe `whistle-route` walks every monster in Glory's
     weak/normal/elite/boss keys): `ScrollOfBiting` (`scrolls_of_biting_weak` /
     `_normal`), `FlailKnight` and `SpectralKnight` (the `knights` elite,
     `glory/knights.py:131`) and `SoulNexus` (`soul_nexus`).
  4. **Executed observable** on `ScrollOfBiting` (probe `stun-machine`, 100000
     rolls, seed 7, the machine parked telegraphing `CHEW` after the reachable
     prefix `CHOMP → MORE_TEETH → CHEW`). The move the branch picks on the turn
     **after** the deferred `CHEW`:

  | | CHEW | CHOMP |
  |---|---|---|
  | sim as shipped (G4 gap **and** G1 gap) | **66.5%** | 33.5% |
  | duplicate restored, C# params still mis-read (G1 gap only) | 66.5% | 33.5% |
  | C# params restored, duplicate still missing (G4 gap only) | 50.0% | 50.0% |
  | **the game** (both fixed) | 0% | **100%** |

  The game's post-stun branch is **forced** to `CHOMP`, because the duplicated
  `CHEW` fills `CanRepeatXTimes(2)`'s window (step 19). The 2×2 also shows the
  two gaps are genuinely two: neither can be closed by fixing the other, which
  is why **G1** and **G4** stay separate under rule 3. `SoulNexus` is the
  control — its three branches are all `CannotRepeat` (`SoulNexus.cs:70-72`,
  *n* = 1), and a duplicate at the tail of the log cannot change a last-1
  window, so it is both correctly ported **and** insensitive.

  *Correction to the first pass.* It cited `SlumberingBeetle`,
  `LagavulinMatriarch` and `TerrorEel` as making G4 live. **None of the three
  can exhibit this observable**: `SlumberingBeetle`'s only branch is a
  `ConditionalBranchState` (`hive/slumbering_beetle.py:50-52`, reading
  `self.powers`, never `state_log`), `LagavulinMatriarch`'s likewise
  (`underdocks/lagavulin_matriarch.py:63-65`), and `TerrorEel` has **no branch
  state at all** (`underdocks/terror_eel.py:53-56` is a pure chain) — a log
  duplicate cannot move any of their weights. All three additionally
  hand-splice the follow-up themselves (`force_current_state` +
  `_current_move`: `slumbering_beetle.py:65-66`, `lagavulin_matriarch.py:83-84`,
  `terror_eel.py:62-63`), so they already emulate the machine half. All three
  are also in earlier acts than the Whistle. The clause "`FossilStalker` is a
  ported Underdocks monster" is withdrawn too: it is the probe vehicle for a
  correctly-ported `CanRepeatXTimes(2)` branch and for G5's `next_move_key`
  drop, but **no ported caller can stun it** (its powers are Suck and Latch,
  not Ravenous/Imbalanced/Flutter, and Whistle cannot reach act 0 from act 2).
  The two power-side stuns are inert for the same reason, and probe
  `stun-sites` resolves them: `RavenousPower`'s only applier is `CorpseSlug`, a
  pure chain, and `ImbalancedPower`'s only applier is `BowlbugRock`, which sets
  `is_off_balance` in its constructor (`hive/bowlbugs.py:43`) and therefore
  takes the flag arm at `powers.py:2069` rather than the stun arm — and whose
  branch is conditional anyway.

- **G5 — the sim's `next_move_key` is silently dropped for every
  `MachineMonster`, and `SetMoveImmediate`'s `CanTransitionAway` guard has no
  analogue. DORMANT.** `CreatureCmd.stun`'s override is
  `if next_move_key is not None and hasattr(target, "_move_key")`
  (`cmds.py:216-217`) — `_move_key` is the **hand-rolled** monsters' field, so
  a `MachineMonster` takes the `hasattr` false branch and the argument
  evaporates with no error (executed in `stun-machine`:
  `next_move_key='LASH_MOVE' was SILENTLY DROPPED (hasattr _move_key = False)`).
  Separately, C#'s `SetMoveImmediate` refuses to override a move whose
  `MustPerformOnceBeforeTransitioning` has not been satisfied
  (`MonsterModel.cs:422`), and the sim has no such guard anywhere. Dormant
  because the **one** ported caller that passes `next_move_key` is
  `overgrowth/ceremonial_beast.py:45`, and `CeremonialBeast` is a hand-rolled
  `Monster` (line 32) that **does** have `_move_key` — so the live path works
  today. Concrete trigger: porting `CeremonialBeast` (or `DecimillipedeSegment`
  / `TestSubject` / `WaterfallGiant`, the other
  `MustPerformOnceBeforeTransitioning` users at `CeremonialBeast.cs:150`,
  `DecimillipedeSegment.cs:155`, `TestSubject.cs:194`,
  `WaterfallGiant.cs:202`) onto `MachineMonster`, or stunning any existing
  `MachineMonster` with an explicit next move.

- **G6 — FlutterPower's stun splice rolls on the SHARED combat stream and
  draws where the game draws nothing. DORMANT.** `FlutterPower.cs:47` calls
  `StateLog.Last().GetNextState(Owner, Owner.Monster.RunRng.MonsterAi)` — the
  **MonsterAi** stream, and by step 41 the rng is not even consumed, because
  `MoveState.GetNextState` is deterministic. `powers.py:2226-2235` instead
  calls `machine.roll_move(self.owner, self.owner._rng)` — the **shared
  combat** `random.Random`, and `roll_move` walks all the way to a `MoveState`,
  which **does** draw when the follow-up is a branch. Executed (`move-rng`,
  which now scans all of `sts2_rl/`): of the **three** `machine.roll_move(...)`
  call sites in the sim, `state_machine.py:301` and `:330` pass `_move_rng`
  and `powers.py:2233` passes `self.owner._rng` — the only one off-stream.
  **DORMANT — and this label CORRECTS a first-pass LIVE claim that the pin
  itself refuted by XPASSing.** `FlutterPower` has exactly **one** applier on
  each side: the ported Hive monster **ThievingHopper**
  (`monsters/hive/thieving_hopper.py:113-114`, a `MachineMonster` at line 29;
  in C#, `grep -rl FlutterPower src/` returns only `ThievingHopper.cs`,
  `FlutterPower.cs` and `AbstractModelSubtypes.cs`). ThievingHopper's machine
  is a **pure deterministic chain with no `RandomBranchState` on either side**
  — `thieving_hopper.py:61-65` is
  `THIEVERY -> FLUTTER -> HAT_TRICK -> NAB -> ESCAPE -> ESCAPE`, matching
  `ThievingHopper.cs`'s `FollowUpState` assignments exactly — so the splice
  roll consumes **no draw from any stream**, neither clause is observable
  today, and the resulting `state_log` is identical on both sides. Named
  trigger: a `FlutterPower` user whose current move's follow-up is a
  `RandomBranchState` — any of the 12 resolved ported branch ports would do
  (probe `mismatch`). The pin
  **constructs that trigger** (it splices a branch behind `FLUTTER_MOVE` and
  parks the machine there) and then fails on `rng.floats == before` with
  `10 == 9`, the one extra shared-stream draw. **Cross-referenced to
  `turn_structure`'s G9**, which owns the *placement* question (one pass at
  turn start vs per-monster after its move) and is a different mechanism — see
  seed fact 3.

- **G7 — the degenerate-weight arms differ: C# limps, the sim raises.
  DORMANT.** Two arms. (a) `maxTimes == 0` with `CanRepeatXTimes` **permanently
  disables** the branch in C# (step 21) and is a construction-time `ValueError`
  in the sim (`state_machine.py:168-169`). (b) When every branch weighs 0, C#
  does `rng.NextFloat(0)` → 0, then `0 - 0 <= 0` on the **first** branch and
  returns it — **burning a draw and picking branch 0**
  (`RandomBranchState.cs:117-124`); the sim raises `RuntimeError("No valid
  branch …")` **before** drawing (`state_machine.py:182-183`). There is a third
  arm, **(c)**, at step 15: the float fall-through, where C# throws and the sim
  returns the last branch.

  **Executed coverage, and its bound.** `zero-weight` now runs **two passes**,
  because the first pass's detached `cls.__new__(cls).build_machine()` cannot
  serve a monster whose graph reads constructor-set fields or live combat
  state. Pass 1 (detached) fuzzes **59** machines over **4,720,008**
  transitions — the numbers this record cited from the start. Pass 2 builds a
  **live instance** (a one-monster `Encounter` in a real `CombatState`) for
  every machine pass 1 deferred and fuzzes **23** more over **1,840,000**
  transitions. **Total 82 machines / 6,560,008 transitions / 0 `No valid
  branch` hits.** That second pass matters: the 24 machines the first pass
  **skipped** included `TwoTailedRat` — this gap's own named trigger — plus
  `ScrollOfBiting`, `LagavulinMatriarch`, `SlumberingBeetle`, `Queen`,
  `Fabricator`, `Exoskeleton` and all four Decimillipede segments, so the
  dormancy claim did not cover its own trigger. **One machine is still
  unbuildable and dormancy is unproven for it: `_Cultist`**, which needs a
  constructor argument.

  **Depth on the trigger.** Breadth alone still could not reach the non-dyadic
  arm. The only ported non-dyadic weight is `TwoTailedRat.cs:127`'s `1f/12f`
  (`underdocks/two_tailed_rat.py:75-86`) and it is a **lambda** gated on
  `_can_summon()`, which reads `turns_until_summonable` — decremented by a
  move's *perform* delegate, which a machine-only fuzz never runs. So the fuzz
  reached that machine with weights `[1, 1, 1, 0]` and never `[1/12, …]`. Probe
  **`nondyadic-weights`** closes it: it finds the one ported branch with a
  callable weight (`TwoTailedRat`), searches the monster's own integer fields
  for one that opens the gate (`turns_until_summonable` 2 → 0 yields
  `RAND=[0.083333, 0.0, 0.083333, 0.75]`), and fuzzes **80,000** transitions
  with that fractional vector live — **0 fall-throughs**.

  Arm (a) is likewise unreachable — no C# call site passes `0` as `maxRepeats`
  (`cs-addbranch` lists all 15 non-default int arguments; they are all `2` or
  `3`), and no ported *port* does either, since 82 of the 83 machines build
  without tripping the sim's `ValueError`. Concrete trigger: a
  `RandomBranchState` all of whose branches are simultaneously blocked — the
  natural construction is every branch `CannotRepeat` **with only one branch**,
  or a lambda weight that can return `0f` on every branch at once
  (`TwoTailedRat.cs:127`'s `CanSummon()` lambda is one `0f` away from this
  shape).

- **G8 — C# validates a malformed machine construction and raises; the sim's
  corresponding API has no equivalent validation. Three sites, ONE verdict.
  DORMANT.** This is the fix pass's biggest verdict change: steps 3, 22 and 37
  are the *same mechanism* at three sites and by governing rule 3 must carry the
  same verdict. They previously carried three different ones (`gap`,
  `deliberate-divergence`, `faithful`). Site census: probe `raise-sites`.

  - **(a) duplicate state ids** (step 3). Every `RegisterStates` implementation
    is `monsterStates.Add(Id, this)` (`RandomBranchState.cs:171`,
    `MoveState.cs:74`, `ConditionalBranchState.cs:58`) and
    `Dictionary<K,V>.Add` **throws `ArgumentException`** on a duplicate key, so
    a monster with two states sharing an id fails loudly at machine
    construction. The sim's `states[self.id] = self`
    (`state_machine.py:86-87`) overwrites, so the second definition wins and
    every `follow_up` pointing at the first resolves to the second.
  - **(b) the machine set twice** (step 37, was `faithful`). The
    `MoveStateMachine` setter throws (`MonsterModel.cs:228-236`) and
    `ResetStateMachine` (389-392) is the only legal clear. The first pass called
    this `faithful` on the grounds that "a double-build is unrepresentable
    rather than rejected" — **it is not unrepresentable**:
    `monster.machine = other` is a legal Python attribute rebind that silently
    replaces a live machine, losing its `state_log` and current state. What is
    missing is the *validation*, i.e. clause (a) at a second site.
  - **(c) `AddBranch` overload #1 given `CanRepeatXTimes`** (step 22, was
    `deliberate-divergence`). See **rule 2** below.

  **Why one verdict, and why `gap`.** Governing rule 1: `waiver` is
  out-of-scope only, so "nothing ported triggers this" is *dormancy*, not a
  waiver — none of the three may be waived. `deliberate-divergence` needs the
  **same observable**, which clauses (a) and (b) plainly lack (C# raises; the
  sim carries on with a silently wrong machine). And clause (c) cannot be `dd`
  either, once its rationale is stated honestly: the first pass wrote "same
  observable … reached by different routes", which cannot both hold. C#'s check
  is an artifact of positional overload resolution — overload #1 accepts a
  `repeatType` but has no `maxRepeats` slot, so `CanRepeatXTimes` must be
  rejected *there* and expressed through overload #2 instead. The sim's
  `add_branch` is a single keyword signature in which `max_times` is always
  addressable, so **C#'s guard is inapplicable and the sim has no analogue of
  it**. The `ValueError` the sim raises on the closest transliteration comes
  from an unrelated, *wider* predicate — `max_times <= 0` — which also rejects
  `AddBranch(state, 0)`, a construction C# **accepts** (that is **G7 clause a**,
  step 21). So the sim's apparent coverage of C#'s guard is incidental to a
  different divergence, and it would **disappear** the moment G7a were fixed
  toward the game: a sim that permanently disabled a `max_times == 0` branch as
  C# does would then silently accept the very construction C# rejects here.
  Probe `raise-sites` buckets it as the one **one-sided guard** site.

  **Executed dormancy, all three clauses.** (a) the `zero-weight` fuzz now
  builds **82** ported machines (59 detached + 23 live) and none raises at
  construction; only `_Cultist` is unbuilt. (b)
  `grep -rn 'self\.machine\s*=' sts2_rl/` returns exactly **one** assignment
  site, `MachineMonster.__init__` (`state_machine.py:300`), and probe
  `spawn-roll` confirms `CreatureCmd.add` (`cmds.py:237-266`) never touches a
  machine, so no ported path rebinds one. (c) `cs-addbranch` resolves all 61
  monster call sites: exactly **one** uses overload #1 at all and none pairs it
  with `CanRepeatXTimes`, and none passes `0` as `maxRepeats`.
  **Concrete triggers.** (a) porting a monster with a repeated state id —
  `Fogmog.cs:44-45` is the game's own near-miss, two distinct `MoveState`s
  (`SWIPE_MOVE`, `SWIPE_RANDOM_MOVE`) sharing one `SwipeMove` delegate and
  differing only in id. (b) any sim code that rebuilds a machine mid-combat (a
  transform, a re-port of `ResetStateMachine`, a fixture reusing a monster).
  (c) the same as G7a's.

- **G9 — the sim has no UNSET_MOVE placeholder, so a monster rolls at
  construction. DORMANT.** C# initialises `MonsterModel.NextMove` to a
  `MoveState()` whose id is `UNSET_MOVE`, whose perform delegate throws and
  whose intent list is **empty** (`MonsterModel.cs:239`, `MoveState.cs:43-46,
  77-80`), and `CombatManager.AfterCreatureAdded` only rolls a real move
  `if (creature.IsEnemy && _state.CurrentSide == CombatSide.Player)`
  (`CombatManager.cs:863-866`) — so an enemy **summoned during the enemy side**
  has no intent until the next player turn. The sim's `MachineMonster.__init__`
  rolls immediately (`state_machine.py:300-301`), so such a monster holds a
  rolled move and a displayable intent the game would not have yet. Dormancy
  executed: `combat.py:286-345` runs the entire enemy side to completion before
  returning, so no sim consumer can observe the interim state; only the draw
  *ordering* differs, and that half is `turn_structure`'s **G9** — same `gap`
  verdict at both sites per governing rule 3, cross-referenced and not
  re-verdicted here. Named trigger: a sim consumer that reads an enemy's intent
  mid-enemy-side (a per-enemy observation build, or an interruptible enemy
  phase).

### Guards and waivers

- **N1 — `RollMove(targets)`'s unused `targets` parameter.** `waiver`,
  multiplayer/API plumbing: `MonsterMoveStateMachine.cs:34` threads
  `IEnumerable<Creature> targets` to `FindNextMoveState` and no
  `GetNextState` override reads it. Executed: `grep -n "GetNextState" src/`
  over the three implementations shows all three ignore the parameter
  (`RandomBranchState.cs:115` uses `owner`, `ConditionalBranchState.cs:44`
  discards both with `_`/`__`, `MoveState.cs:67` discards both).
- **N2 — presentation on the transition path.** `waiver`:
  `SetMoveImmediate`'s `NCreature.RefreshIntents()`
  (`MonsterModel.cs:426-430`), `PerformMove`'s `Cmd.CustomScaledWait` bracket
  and `Log.Info` (`MonsterModel.cs:439, 443, 452`),
  `Creature.PrepareForNextTurn`'s `NCombatRoom…RefreshIntents()`
  (`Creature.cs:553`), and `FlutterPower.cs:46`'s `TriggerAnim`.
- **N3 — `ConditionalBranchState`'s null-condition arm.** `faithful`: the sim
  has it (`state_machine.py:230`) and so does C#
  (`ConditionalBranchState.cs:18-22`); executed, **0 of 41** shipped
  `AddState` sites omit the lambda (`cs-conditional`), so the two
  implementations agree on a path neither exercises. Rollup of steps 25-27.
- **N4 — ascension.** `waiver`, out of scope by the audit prompt: several
  monsters gate branch weights on `AscensionHelper.GetValueIfAscension`; the
  non-ascension branch is the one compared throughout.
- **N5 — `MonsterModel.GetIntents` / `GenerateBestiaryMoveList` build a
  throw-away second machine.** `waiver`, presentation: `MonsterModel.cs:296-308`
  calls `GenerateMoveStateMachine()` purely to enumerate intents for the
  Bestiary, discarding it. It draws no RNG (construction only) and has no sim
  counterpart because the sim has no Bestiary.
- **N6 — `KinPriest.AfterDeath`, handed over by `hook_dispatch`.** `waiver`,
  presentation — **and this overturns `hook_dispatch`'s framing of it as a
  contended content gap.** `hook_dispatch`'s scope note says
  `KinPriest.cs:81-108`'s all-followers-dead `AllFollowerDeathResponse` "has no
  counterpart in the ported sim `KinPriest`" and calls it "Task 10's content
  finding". Read to the end, `AllFollowerDeathResponse` is
  **`TalkCmd.Play(_followersDeathLine, Creature, VfxColor.Purple,
  VfxDuration.Standard)`** and nothing else (`KinPriest.cs:197-200`) — a barks
  line with a colour and a duration. The other arm of the same override is
  `NRunMusicController.Instance?.UpdateMusicParameter("the_kin_progress", …)`
  (`KinPriest.cs:95, 106`), i.e. a music parameter. **The entire override is
  presentation**, so the correct verdict is `waiver`, not the dormant gap
  `hook_dispatch` implied; there is no mechanical behaviour for
  `monsters/overgrowth/the_kin.py:67-110` to be missing. `hook_dispatch`'s own
  verdict — that the sim has no `MonsterModel` listener category to hang a
  monster hook on (its **G5**, dormant) — is unaffected and is not
  re-verdicted here.
- **N7 — the machine's exception messages.** `deliberate-divergence`, and
  **recounted** in the fix pass (probe `raise-sites`, which prints the raw
  `throw new` / `raise` greps and then buckets the resolved pairing). This guard
  covers the **five symmetric** sites, where both implementations raise on the
  same input and only the type differs: `MonsterMoveStateMachine.cs:39` vs
  `state_machine.py:252`, `:58` vs `:271`, `:70` vs `:271`, `MoveState.cs:69`
  vs `state_machine.py:138`, `ConditionalBranchState.cs:53` vs
  `state_machine.py:232`. Same observable — the run crashes in both — and
  `grep -rn 'except RuntimeError' sts2_rl/` finds no ported content catching
  either type.

  The first pass's note said this guard "does **not** cover the **two** places
  where one side raises and the other does not". There are **six**, not two:
  five **asymmetric** (exactly one side raises) — **G7c** (step 15: C# throws on
  the fall-through, the sim returns the last branch), **G7b**
  (`RandomBranchState.cs:117-124` burns a draw and picks branch 0;
  `state_machine.py:183` raises before drawing), **G7a** (step 21: the sim
  raises, C# builds a dead branch), **G8a** (step 3) and **G8b** (step 37) — plus
  one **one-sided guard**, **G8c** (step 22). One further C# throw is in neither
  bucket and is `faithful` at step 12: `RandomBranchState.cs:29`'s
  null-`weightLambda` check is dead on both sides, because no overload can leave
  the lambda null and the sim has no such field.

## Pins (Step D)

| behaviour | status |
|---|---|
| Weight-vs-cooldown arg handling | **CLOSED 2026-07-28, re-verified 2026-08-03 — no longer an xfail.** `test/test_monster_branch_audit.py` (whole file, 211 lines, 5 classes) is the verified regression file for the hand-rolled overgrowth ports and the two previously-fixed monsters — `TestPreviouslyFixedBugClassRegression::test_twig_slime_m_draws_every_turn` and `::test_flyconid_draws_every_turn` are the direct descendants of the shipped fix — and it gained `TestAddBranchIntArgsAreRepeatLimits` (11 cases) covering the five machine ports of **G1** directly. `TestMonsterStateMachineOrder::test_addbranch_int_args_are_repeat_limits_not_weights` (`test/test_hook_order.py:1304`) was originally added as a strict xfail; its `strict=True` xfail marker has since been removed and it is now a plain passing assertion (re-run this pass: green, along with the 11 `TestAddBranchIntArgsAreRepeatLimits` cases). |
| Repeat-rule enforcement | **Pre-existing, verified by path.** `test/test_new_features.py::TestStateMachine::test_mawler_roar_used_at_most_once_per_combat` (line 148) covers `USE_ONLY_ONCE` **and** `CANNOT_REPEAT` on **Mawler**, one of the brief's named monsters; `::test_fogmog_branch_only_yields_legal_sequences` (line 126) covers **Fogmog**; `::test_use_only_once_and_cannot_repeat_weights` (line 168) covers both rules on a synthetic machine over 60 transitions. **`CAN_REPEAT_X_TIMES` was covered by none of them**, and it is the rule the five bugged ports drop, so `test_can_repeat_x_times_blocks_the_n_plus_first_repeat` was added (passing) to close that hole. |
| Spawn-roll exactly-once | **New, passing.** `creature_card_cmds` step 3's deferred `PrepareForNextTurn(rollNewMove: false)` site (steps 47-48) had no coverage: nothing asserted that a mid-combat spawn rolls its move exactly once, so a future `telegraph_next_move` inside `CreatureCmd.add` would silently double-roll (one extra `MonsterAi` draw plus a second log entry). `test_a_mid_combat_spawn_rolls_its_move_exactly_once` closes it. |

**Nine tests** live in `test/test_hook_order.py::TestMonsterStateMachineOrder`.
As originally written this was **two passing** (the `CAN_REPEAT_X_TIMES` rule
and the spawn-roll exactly-once property) and **seven strict xfails** pinning
**G1**, **G3**, **G4**, **G5**, **G6**, **G7a** and **G8**. **STALE as of
2026-08-03**, re G1 only (see the "Gaps found" correction note; the other six
were not re-checked this pass): `test_addbranch_int_args_are_repeat_limits_not_weights`
(**G1**'s pin) carries no `xfail` marker today and passes — re-run this pass —
so the count is now **at least three passing** (the two above plus G1's) and
**at most six strict xfails**; the JSON's own per-step "issue" text (steps 3,
10, 15, 22, 35-37, 39-44, 48-49) claims G3-G9 are ALL closed too, with the
JSON's `strict xfail marker is deleted and which now passes` language repeated
at nearly every one, but this doc does not re-derive that here. **G2** and
**G9** are not pinned by this class: G2's observable is already asserted by
`test/test_monster_branch_audit.py`'s zero-draw tests, and G9's (both clauses)
is a non-observable, because the sim's enemy side is atomic — neither had an
assertion that would fail for the reason stated, at the time this was written.
