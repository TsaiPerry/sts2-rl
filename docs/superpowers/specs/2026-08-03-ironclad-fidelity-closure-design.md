# Ironclad fidelity closure — design

**Date:** 2026-08-03
**Goal:** make "the sim has the exact same behavior as the real game for
Ironclad" a defensible, gated claim. Concretely: settle the 933T39V18D
floor 47/49 triage residue, promote every convergence detector into strict
suite gates for both Ironclad seeds, and re-audit every stale audit record so
the ledger's "0 live gaps" describes today's code.

## Background — measured 2026-08-03

`py tools/converge_triage.py <seed> floor_49 2`, run twice each (identical
output both runs, per the determinism rule):

- **89U21BV1TZ: FULLY CONVERGED.** All detectors clean.
- **933T39V18D: DIVERGENCES REMAIN** — but only on the resync-ON triage arm:
  - floor 47: `floor_hp` expected 74 got 66; `counter_CombatTargets` 21 vs 22
  - floor 49: `floor_hp` expected 80 got 67; `counter_Shuffle` 892 vs 909;
    `counter_CombatCardSelection` 9 vs 8
  - DETECTOR 2 (run-end counters): Shuffle 909 vs 892,
    CombatCardSelection 8 vs 9, CombatTargets 26 vs 25
  - DETECTOR 3: act-2 boundary `player_hp` expected 67 got 80

The suite's hard gate for 933T
(`test/test_conformance_player_state.py::test_full_run_player_state_parity`,
resync **OFF**) is **green**: final HP/max-HP match, zero counter divergence,
`forced_combats == 0`. The audit queue reports 347 gap entries, all DORMANT,
0 LIVE — but `audit_status.py` shows ~843 of 954 records **stale** (all 12
seams, 138/138 power, 255/260 relic, 159/202 card, …), so those verdicts
describe an older sim than the one running.

`GAP-QUEUE.md` ("Standing lessons", the `resync_floors` items) already
documents three confounds sitting exactly where the residue is:

1. **`resync_floors` is structurally lossy on the final floor**: per-floor
   resync pins floor 49 to a floor-*entry* snapshot
   (`sts2-run-backups/.../floor_N/run.save`) while the whole-run counter check
   compares a run-*end* capture (`RunReplays/.../floor_49/run.save`), so the
   resynced arm cannot converge there by construction. Left unresolved when
   the seeds converged.
2. **`converge_triage.py` prints DETECTOR 3 and DETECTOR 4 HP with opposite
   expected/got senses** (act-2 "expected 67 got 80" vs floor-49
   "expected 80 got 67" in the same run). At least one is inverted;
   undiagnosed.
3. **The floor-47 delta is explained by neither** — it is an open question
   whether it is a real sim gap or a snapshot-semantics artifact.

So the current instrument is known-untrustworthy in exactly the region under
inspection. The design fixes the instrument first, adjudicates what is real,
locks gates so triage and suite can never disagree again, then does the stale
sweep.

## Non-goals

- New replay capture (autovalidation-mod corpus growth) — explicitly deferred
  by decision; the success bar is both bundled Ironclad seeds green under hard
  gates.
- Draining the 347 dormant gap entries — separate campaign. Exception: any
  dormant/faithful verdict this work *proves wrong* is corrected as part of
  the fix.
- The four un-ported characters and their seeds (permanent xfail, accurate
  reasons).
- Act 3+ content beyond what `stop_after_act=2` replays exercise (the
  recordings end at floor 49).

## Phase 1 — Make the instrument trustworthy, then adjudicate floors 47/49

1. **Fix the DETECTOR 3/4 inversion.** Diagnose which detector swaps
   expected/got (`tools/converge_triage.py` vs the comparators in
   `sts2_rl/conformance/`), fix it, and pin with a unit test so the two
   detectors can never disagree in sense again.
2. **Resolve `resync_floors` final-floor semantics.** Decide between: pin the
   last floor to the run-end save, or skip resync on the final floor. Either
   makes the resynced arm *able* to converge; the choice is made by whichever
   matches the game's own capture semantics, recorded in the code comment and
   in `GAP-QUEUE.md` (delete the standing-lesson item once resolved).
3. **Build the per-room oracle (DETECTOR 5).** `SaveOracle.map_history`
   already parses `map_point_history`; its `player_stats` per map point
   (`current_hp`, `max_hp`, `damage_taken`, `hp_healed`, `gold_gained`,
   `gold_spent`, `gold_lost`, `gold_stolen`, `max_hp_gained/_lost`) are
   unread. A detector that walks these against the sim room-by-room localizes
   any HP/gold divergence to a single room — the queue calls this the
   highest-leverage tooling left. This is what settles floor 47 definitively.
4. **Adjudicate every remaining floor-47/49 signal** into one of:
   - **harness artifact** → fix the harness/triage tool;
   - **capture semantics** → encode the semantics in the oracle/comparator
     (never as a tolerance — an exact pin against the correct snapshot);
   - **real sim gap** → detector-guided bisection: per-command Hand/Enemies
     diff to the earliest divergent command, read the decompiled source for
     the implicated units only, fix the engine, add a `strict=True` pin test.
5. **Correct the audit ledger for anything real.** A real gap here proves a
   wrong `faithful` or wrong `dormant` verdict in some record. Identify which
   record(s), file the gap entry with the fix recipe, regenerate
   `GAP-QUEUE.md`, and run `gap_queue.py coverage` + `cite-check`. The
   counter signature (Shuffle −17, CombatCardSelection +1, CombatTargets ±1)
   suggests a single auto-play/card-AI branch per floor, not five bugs — but
   that is a hypothesis for the bisection, not an assumption.

**Exit criteria:** three identical `converge_triage.py` runs per Ironclad
seed print `FULLY CONVERGED` on **both** arms (resync ON and OFF); full suite
green.

## Phase 2 — Hard gates: triage and suite can never disagree again

The failure mode this closes: the suite was green while triage printed
`DIVERGENCES REMAIN`, because the gate asserts a subset of what triage
checks.

1. **Extract the `clean` predicate** from `converge_triage.py` (currently an
   inline expression over the five detectors) into a callable the suite
   imports, so the tool and the tests share one definition of converged.
2. **Gate both Ironclad seeds on the full predicate**, parametrized:
   - resync-OFF whole-run gate (exists; keep);
   - resync-ON per-floor gate over all checkpoints (new — meaningful after
     Phase 1.2);
   - zero DETECTOR 1 tripwire bug-sites (new as a suite gate);
   - DETECTOR 5 per-room HP/gold walk (new).
3. **No skips, no xfails** on the two Ironclad seeds. The four other-character
   seeds keep their permanent xfail with accurate reasons.

**Exit criteria:** deleting any Phase 1 fix turns the suite red; suite green
at head; `converge_triage.py` and pytest agree by construction.

## Phase 3 — Stale sweep to 0

Runs **last**: Phase 1 engine edits would re-stale anything re-audited
earlier. ~843 stale records (re-measure before starting;
`py audit/tools/audit_status.py`).

1. **Diff triage pass (cheap, scripted).** For each stale record, diff the
   hashed file(s) against the text the hash was taken over (git history has
   both). Classify:
   - **(a) cited lines untouched** (append-only edits, changes elsewhere in
     the file) → fast re-audit per the pin-append precedent: verify the cited
     lines did not move or change content and named tests still exist, then
     `harness.py rehash` — the check script's output is the receipt;
   - **(b) cited code moved or changed** → full agent re-audit of the record.
2. **Full re-audits in batches by kind**, parallel subagents, the established
   stream pattern: each batch owns one slice of `records/<kind>/`, re-reads
   the changed sim source against the C#, confirms or revises each verdict,
   rehashes last. A revised verdict that opens a gap files the entry;
   `GAP-QUEUE.md` is regenerated at the end, not per batch.
3. **The sweep is read-only on `sts2_rl/`.** Re-audit agents never fix; new
   gaps found are queued (this keeps records from re-staling mid-sweep). If a
   re-audit finds a **live** gap, the sweep pauses and it is triaged
   immediately — a live find would also contradict the green gates, so it
   must be reconciled, not queued.

**Exit criteria:** `audit_status.py --strict` exits 0 (0 stale, 0 invalid,
per-kind gaps only where queued); `gap_queue.py counts`, `coverage`,
`cite-check` all clean; suite green.

## Verification, throughout

- Full pytest suite green after every phase (baseline: run and record the
  count at start; last known 4650 passed / 0 failed).
- Three identical triage runs per seed before trusting any triage delta
  (out-of-combat unseeded draws make single runs unreliable).
- No `git commit` — stage only; Perry commits (standing project rule).

## Risks

- **Floor 47 may be a real, subtle gap** (the resync arm diverging where the
  unresynced arm is green can happen when an error and a compensating error
  cancel by run end). That is exactly what DETECTOR 5 exists to expose; if
  found, it also demotes the "final HP matches" gate from sufficient to
  merely necessary — the per-room gate becomes the primary one.
- **The stale sweep's class (a)/(b) split could be gamed by a sloppy diff
  script** into rehash-as-decoration. Mitigation: the classifier emits a
  per-record receipt (file, cited lines, verbatim before/after) and class (a)
  requires byte-identical cited lines, not "looks unchanged".
- **Sweep scale** (~843 records) — bounded by batching by kind and by the
  class (a) fast path; previous campaigns of similar size (relic tier, 258
  records in 18 batches) completed with zero merge conflicts using the same
  ownership rules.
