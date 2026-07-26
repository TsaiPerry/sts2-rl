# Stream 5 — content audits: monsters  ⚠️ GATED

**Do not start this stream until Task 10 (`monster_state_machine`) is
committed on `audit-pipeline`.** Check with:

```bash
cd /c/Users/Perry/Desktop/sts2-rl-audit && py tools/audit_status.py
```

`seam` must read `6 audited`. Task 10 establishes the `AddState`/`AddBranch`
argument contract that this entire stream's method depends on; auditing 109
monsters against an unsettled contract means auditing them twice.

Setup, once the gate clears:
```bash
cd /c/Users/Perry/Desktop/sts2-rl
git worktree add /c/Users/Perry/Desktop/sts2-rl-monster -b audit-monster audit-pipeline
```
Copy everything below the line into a fresh Claude Code session.

---

You are running the **monster content audits** of a source-to-sim audit
pipeline. This is the hardest content stream: monsters are behaviour graphs,
not numbers.

WORKTREE (all work here): `c:\Users\Perry\Desktop\sts2-rl-monster`  (branch `audit-monster`)
GAME SOURCE (READ-ONLY): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Read first, in order

1. `docs/superpowers/prompts/_shared-audit-contract.md` — **your binding
   contract**: operational rules, the eight verdict rules, file ownership,
   the per-unit procedure.
2. `docs/audit/seams/monster_state_machine.md` — **the contract this stream
   rests on.** It contains the enumerated `AddBranch` overload table with each
   integer argument's role. Read it before your first unit; every graph
   comparison you make is against that table.
3. `tools/audit/PROMPT.md` — bug-class checklist. **Read-only for you**; the
   relic stream owns it. Send lessons via your report.

## Your scope

`audits/monster/**` — **109 units**. Roster: `py tools/audit/harness.py roster monster`.

## Method — two populations, two procedures

**MachineMonster ports (the majority).** Compare graphs **node by node**
against the C# `AddState`/`AddBranch` calls. For each node: the move it
emits, its transitions, and — critically — the **role of every integer
argument**. This is bug class 6.

The motivating bug: hand-rolled monsters misread `RandomBranchState.AddBranch`
integer arguments (cooldown / maxRepeats) **as weights**. Fixing TwigSlimeM
and Flyconid greened a conformance seed. A weight read as a cooldown produces
a move sequence that is right most of the time and wrong occasionally —
exactly the failure recorded runs miss.

Verify the repeat rules too: `CANNOT_REPEAT` / `CAN_REPEAT_X_TIMES` /
`USE_ONLY_ONCE`, and cooldowns keyed off the state log.

**Hand-rolled monsters (~18).** These have no graph to compare against.
Reconstruct the equivalent graph from the C#, then verify the hand-rolled
`_move_key` logic emits **identical move sequences over the reachable state
space**. If you cannot establish that, record a `gap` recommending a
state-machine port — that is the preferred convention in this codebase, not a
fallback.

Hive and Glory monsters are flagged as **never checked** for the
weight-vs-cooldown misreading. Prioritise them.

## Findings already recorded — do not re-verdict (rule 3)

- **RNG stream.** The game rolls moves at intent-display time from a dedicated
  `MonsterAi` stream; the sim uses the shared combat stream. Recorded in
  `turn_structure` (its G9) and reconciled by Task 10. Read both treatments
  before saying anything about move-roll RNG.
- **`turn_structure`** owns the turn-loop half of Stun; the move-machine half
  is in `monster_state_machine`. Neither is yours to re-verdict.
- **Death ≠ removal**: a 0-HP creature can persist and keep taking turns (a
  withered Decimillipede segment does); only removal from `Enemies` is vetoed.
  If a port conflates the two, that IS a monster-level gap — record it.
- **`hook_dispatch`** found `KinPriest.cs`'s `AfterDeath` uncovered by any
  seam and handed it to Task 10; check it landed.
- **`creature_card_cmds` step 26 (gap)** — `SetMaxAndCurrentHp` is raw-assigned
  in `monsters/hive/decimillipede.py:68,167` and `monsters/hive/ovicopter.py`,
  skipping the clamp, the `MaxHp <= 0 → Kill`, and `AfterCurrentHpChanged`.
  Dormant today; check whether any monster you audit makes it live.

## Ascension

Monster stats are the place ascension values bite hardest. Every number goes
against the **non-ascension** branch of `AscensionHelper.GetValueIfAscension(...)`.
A record that does not say which branch it read is not finished.

## Batching

15 units per batch, but expect monsters to be slower per unit than any other
content kind — graph comparison is not a numbers check. Validate, status-check,
run the suite, and commit each batch before starting the next.

Report your per-unit cost after the **first batch**, since the plan's batch
sizing was set from cheaper kinds and may need revising for this one.

## Report

Write `.superpowers/sdd/content-monster-report.md`. Include: units audited;
**every monster found misreading an `AddBranch` integer argument** (this list
is the deliverable Perry most needs — it is the class of bug that breaks seed
convergence); every hand-rolled monster and whether you could establish
sequence equivalence or are recommending a state-machine port; every gap with
its live/dormant determination and reachability evidence; lessons for
`PROMPT.md`; any unit the roster mis-resolved; any cross-record disagreement
under rule 3; and cost data.
