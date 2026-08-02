# Handoff — entity observation schema, phase 2 onward

Written 2026-08-02 at the end of the phase-1 + post-phase-1 session. This file
is the entry point: it says what is true now, what is next, and what will bite
you. Everything it summarises is recorded in full elsewhere, and those records
are authoritative if this file ever disagrees.

## Read these, in this order

1. **`prompts/entity-obs-schema.md`** — the project prompt. Phase 2 starts at
   its "Phase 2 — the encoder and the tied action head" section (~line 272),
   with riders R8/R9/R10 immediately after, then phase 3 (R11–R13).
2. **`OBS_SCHEMA.md`** — the **normative contract** for what the envs emit.
   §2 padding/overflow, §5 combat layout, §5A run layout, §5.4 intent history,
   §6 the admissibility rule, §7 known gaps and soft spots.
3. **`docs/superpowers/plans/2026-08-01-entity-obs-schema.md`** — the ledger.
   Authoritative on every decision and measurement. Read the last three
   sections, which cover everything after phase 1 closed.
4. `docs/superpowers/plans/2026-08-02-entity-obs-schema-phase1-report.md` — the
   readable phase-1 summary. Its figures table carries corrections; the topmost
   correction is current.

`prompts/entity-obs-schema-CONTINUE.md` is the **previous** handoff (phase 1).
It is a point-in-time snapshot and is now stale — do not follow it.

## Hard constraints — these are not negotiable

- **Never `git commit` or `git push`.** Stage only (`git add`); committing is
  the user's call. This holds mid-task and overrides any skill or workflow that
  would normally commit. (CLAUDE.md §4.)
- **There is no old-vs-new comparison in this project, in any form** — not
  checkpoint scores, not steps/sec, not random-policy deltas. Validation is
  against engine ground truth. A *within-new-stack* A/B one variable apart
  (which is what R10 asks for) is fine and is not this.
- **`test/test_conformance_floor_state.py`'s 2 failures are an environment gap**
  (a missing `933T39V18D/floor_49` fixture). Never "fix" them, never count them
  as regressions. Run the suite with
  `--ignore=test/test_conformance_floor_state.py`.
- **The run-env `env.step()` hang is owned by the concurrent source-fidelity
  audit**, not by this project. Do not diagnose it; do not paper over it with
  timeout-and-truncate.
- Use the **`py` launcher** — there is no `python` on PATH. `cd` to the repo
  explicitly; a session's default shell cwd may be the game-source directory.
- The decompiled game source lives at `c:\Users\Perry\Desktop\Slay the Spire 2`
  and is the authority on behaviour. Never edit it.

## How the user wants the work run

- **Dispatch subagents per task with disjoint file ownership.** This applies to
  ad-hoc investigation too, not only planned tasks — a census, a sweep, or an
  empirical measurement goes to a subagent with a read-only brief, reports to a
  scratchpad file, and returns only the answer.
- **Re-run the full suite yourself after every lane**, rather than trusting a
  lane's green. This is how most of this session's real defects were caught.
- Every dispatch must forbid `git commit`, `push`, `add`, `stash`, `checkout`,
  `reset`, `restore`, and "temporarily revert the fix to see RED".
- Brief lanes to **test their premise, not confirm it**, and to report where the
  brief was wrong. That was the highest-value thing lanes did, on nearly every
  dispatch.

## Verified state as of this handoff

Controller-measured, not lane-reported:

```
combat schema 6   f 1677  i 606   9,132 bytes/env/step   79 actions
run    schema 9   f 4710  i 1464  24,696 bytes/env/step  243 actions
curric schema 9   f 4710  i 1464  24,696 bytes/env/step  243 actions
```

Suite: **4399 passed / 6 xfailed / 0 failed** with the ignore above.
**Everything is STAGED and UNCOMMITTED**; `HEAD` is `206c9bd round 13 bug fixes`.
Use `git diff --cached --stat` for the current file count — do not trust a
number written in any document.

## What is done

Phase 0 (power instances) and phase 1 (the integer/entity observation) are
complete, plus three post-phase-1 rounds. The flat float `Box` is gone; both
envs emit `spaces.Dict({"f": float32, "i": int32})`.

| rider | status |
|---|---|
| R1 relic block with per-relic displayed state | **shipped**, both obs |
| R2 card-instance aux fields | **shipped** |
| R3 per-enemy intent history | **shipped** (v6) — 3 slots, `net_id`-keyed, displayed intents only |
| R4 select candidates + candidate-index actions | **shipped** |
| R5 character id + ascension | **CUT** (constants until a 2nd character exists) |
| R6 log1p for unbounded scalars | **shipped** |
| R7 watched-history statistics | **deferred** (lowest value; pity cut as hidden information) |

Also closed: `power_cmd/G5`'s observation residue; a `StatusIntent` card-count
gap; and a **genuine engine bug** — `DeathBlowIntent` lacked the ATTACK flag, so
Go For The Eyes was silently failing against Living Fog and Waterfall Giant.

`--arch` is `mlp | entity | entset`; **`entset` is the default and the only one
that reads the modern schema.** `mlp` and `entity` are refused against it (user
approved), guarded by a per-`env_kind` *threshold* so a future bump cannot
silently disable the refusal.

## What is next

**Phase 2 — the encoder and the tied action head** (`prompts/entity-obs-schema.md`
~line 272). Embeddings per vocabulary kind, masked pooling, then a head that
scores `(card_entity, target_entity)` pairs against the same tables the
observation uses, instead of the positional `MAX_HAND × MAX_ENEMIES` index
space. **Preserve the masked-categorical contract** (`get_value` /
`get_action_and_value`, `_MASK_FILL`, and the guarantee of at least one legal
action per row) so the PPO loop stays untouched.

Then R8 (extend the pointer head to every run-env decision), R9 (feed the damage
matrix and incoming previews into the pair score), R10 (measure a shared
encoder — a within-stack A/B, keep only on a throughput win with no stability
regression).

**Phase 3 — R11–R13**, no schema impact, after phase 2. R11 (mid-run start-state
distribution for the combat env) is flagged in the prompt as the
highest-leverage sample-efficiency idea in the file.

## Open items and hazards

- **Schema bumps are still cheap — but be precise about what makes them
  expensive.** Phase 1's organizing rule is *the from-scratch retrain is paid
  exactly once*. Three combat bumps landed on 2026-08-02 at zero cost because
  nothing has been trained for real yet. **The trigger is owning a trained
  checkpoint you don't want to discard, NOT the phase-2 boundary** — phase 2
  changes the architecture, and `checkpoints.check_checkpoint` refuses
  cross-arch loads outright, so a schema change bundled with phase 2 is equally
  free. What actually starts the clock is the first serious training run
  (R10's A/B, R11's snapshot harvesting, or validating the act-0 caps).

  Two real costs do rise, though:

  1. **The tied action head couples observations to actions.** Today they are
     largely independent, so a bump ripples into segment maps, the arch guard,
     pin tests and stale document figures — annoying but bounded. After the
     head scores actions from the same entity rows and embedding tables the
     observation uses, an observation change can perturb the *action* space.
     That is a strictly worse blast radius, and every expensive defect in this
     project has lived at a seam like it. Prefer landing schema work before it.
  2. **"No migration path" is a policy, not a law.** `check_checkpoint`
     hard-fails on a schema mismatch today, but `migrate_checkpoint`'s
     docstring records that widenings *are* mechanically migratable: pure
     feature additions splice zero columns into each head's first trunk layer,
     with the Adam moments spliced to match. That machinery existed for v3 → v4
     and was removed as dead code when phase 1 orphaned it. If bumps ever get
     genuinely expensive, rebuilding it is the escape hatch.
- **Any combat widening widens the run envs**, which embed the combat block.
  This was missed once and left one version naming two contracts. Pinned by
  `test_run_schema_version_matches_declared_dims` (`test/test_run_obs_v4.py`).
- **The StatusIntent card count is two-thirds inert**: only 5 of 18
  `StatusIntent` construction sites carry a count; the rest read 0.0 rather than
  fabricating one. That is the pre-existing `monster/_intent_count_lost` port
  gap, not a bug in the observation.
- **`USE_ONLY_ONCE` is unrecoverable from intent history** — it is a permanent
  flag, not a recency window, so no bounded N exposes it. R3's N=3 spans every
  *cooldown* window the engine consults, and nothing more.
- **Every empirical census is an act-0 floor.** Masked-random play dies in act 0,
  so `MAX_RELIC_ROWS`, `MAX_COMBAT_CARDS` and `MAX_SELECT_CANDIDATES` (96) rest
  on static arguments. `MAX_SELECT_CANDIDATES` is load-bearing on *actions* — a
  candidate past the cap is unclickable, which the real game never does. Nothing
  asserts `N_ACTIONS == 243`, and every layout constant derives symbolically
  from it, so moving it reflows the action space silently.
- **R6's log1p denominators are reasoned defaults**, not fitted to an observed
  distribution.
- **For the source-fidelity audit workstream:** the monster stream audited all
  109 monsters and declared complete, yet the DEATH_BLOW `also=(MoveType.ATTACK,)`
  omission sat in two of them. Nothing about it was file-specific — a sweep of
  the other `Intent(...)` construction sites for the same omission is warranted.
  Left as a recommendation; this project did not write into the audit's records.

## Method lessons that earned their place

**A green suite is not evidence.** Six defects this project shipped past were
invisible to the implementing lane's own passing tests: a truncate-then-sort
information leak, tests green alone and red under the full suite, an all-padding
fixture comparing nothing, a duplicate-handling test with no duplicates, a
process-global warning latch making order decide the result, and an encoder that
implemented half the padding rule.

Two habits are standard here as a result:

- **Mutation-check every invariant test** — break the invariant at runtime in a
  throwaway scratchpad script and confirm RED. Never by editing tracked files.
- **Never let process-global state decide a test's result.** `test/conftest.py`
  clears the warn-once latch before every test; assert a block's `.overflow`
  float, never a once-per-process warning.

**The expensive defects live between correctly-implemented parts.** Five of them
this session: the encoder mask vs the schema's padding rule; DeathBlow's intent
vs the observation's gate; the combat bump vs the run version; the bump vs the
arch guard; a report's table vs every lane's ownership boundary. Each side was
individually right, so per-lane review cannot see them. **Re-measuring the whole
system is what catches them** — running both envs and printing
`(version, f_dim, i_dim)` rather than reading two green reports.

**Cost estimates inherit the design they were made against.** R3 sat deferred on
a cost that included phase-epoch machinery which only ever applied to the
move-id design that had already been rejected. Re-pricing against the design
actually on the table cut it to something worth building immediately.
