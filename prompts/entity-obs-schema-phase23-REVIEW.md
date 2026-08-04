# Independent review — entity-obs-schema phases 2+3 (staged, uncommitted)

Review the staged-but-uncommitted work in c:\Users\Perry\Desktop\sts2-rl —
the entity-obs-schema project's phase 2 (tied action head + riders
R8/R9/R10) and phase 3 (R11 snapshot start-states, R12 worker
re-measurement, R13 built-measured-deleted, evaluation rider), both
completed 2026-08-02. You were not involved in building it; your job is to
verify the claims independently, not to re-derive them.

## Ground rules

- NEVER commit, push, or otherwise mutate git state. The work is STAGED on
  HEAD `2dc0445` and must stay exactly as it is. `git stash` is also
  forbidden. Read-only git.
- Use the `py` launcher (`python` is not on PATH).
- The suite is `py -m pytest test -q --ignore=test/test_conformance_floor_state.py`.
  The claimed final state is **4521 passed / 6 xfailed / 0 failed**. That
  ignored file's 2 failures are a known missing fixture — never "fix" them
  and never count them.
- The decompiled game source (c:\Users\Perry\Desktop\Slay the Spire 2) is
  read-only authority; never edit it.
- The run-env step() hang is owned by a concurrent source-fidelity audit —
  do not diagnose it. If you drive run-env episodes, arm
  `faulthandler.dump_traceback_later` and keep budgets bounded.
- Do not "fix" anything you find. Report findings; the fix decisions are
  mine.

## What to read first (in this order)

1. `docs/superpowers/plans/2026-08-01-entity-obs-schema.md` — the project
   ledger; its "Phase 2" and "Phase 3" sections are the claims under review.
2. `docs/superpowers/plans/2026-08-02-entity-obs-schema-phase2.md` and
   `...-phase3.md` — the plans (locked decisions + global constraints).
3. `.superpowers/sdd/progress-obs-phase2.md` and `progress-obs-phase3.md`
   — execution ledgers: per-task verdicts, fix loops, measurement tables,
   deferred-minors roll-ups (phase 3's header lists 4 deferred minors M1-M4
   and earlier roll-up items — check each is genuinely minor, not a
   downgraded defect).
4. `git diff --cached --stat` then the full staged diff for anything you
   dig into. `OBS_SCHEMA.md` and `RL_ARCHITECTURE.md` are the contracts the
   code claims to honor.

## Claims worth independently verifying (prioritized)

1. **Suite**: run it yourself; expect 4521/6/0.
2. **Schema freeze**: phases 2-3 claim ZERO observation-layout change —
   combat schema 6 (f 1677 / i 606), run schema 9 (f 4710 / i 1464), and
   `models.ENTSET_HEAD_VERSION == 4`. Verify against the live envs.
3. **Tied head equivariance** (phase 2's core claim): the play head scores
   cards, not slots — `test/test_tied_head_combat.py`'s swap tests pin it;
   satisfy yourself the tests aren't tautological (they include a
   positional-baseline sanity test — check it can actually fail).
4. **R11 end-to-end**: `runs/snapshots/random-v1.jsonl` (1237 snapshots,
   untracked) should load via `sts2_rl.snapshots.load_snapshots`, every
   snapshot should `build_start_state`, and
   `py train_torch.py --env combat --start-snapshots runs/snapshots/random-v1.jsonl --timesteps 2048 --n-steps 64 --n-envs 8 --seed 1 --fresh --save runs/review-smoke.pt`
   should train clean (also exercises the new auto-worker default). Known
   honest limitations (documented, pinned by tests — verify they ARE
   documented rather than hidden): relic flag-state loss (~20 relics),
   dataset is all act-0 (masked-random harvest), belt slots 3+ visible but
   unactionable.
5. **R12 numbers**: combat 522→818 sps (+57%), column 319→453 (+42%) at 32
   envs w4, cuda. Spot-check ONE pair yourself if the machine is quiet
   (`--n-workers 0` vs `4`, 32 envs, 32768 timesteps) — direction and
   rough magnitude, not exact figures. Verify `--n-workers` auto default
   behavior at small vs large `--n-envs`.
6. **R13 really deleted**: repo-wide grep for `aux_win|aux-win` should hit
   only ledgers/plans/prompts — zero code hits. models.py/checkpoints.py
   should contain no orphaned R13 machinery.
7. **Harvest safety contract**: harvest.py must have NO
   timeout-and-continue path (watchdog trips kill the process); verify by
   reading the loop, and run a 2-3 episode harvest into a temp file.
8. **Eval rider**: `run_probes.py`'s oracle/anti-oracle gates (note
   deferred minor M1: a first-legal-action policy aces all 3 probes — is
   that acceptable for the probes' stated purpose?);
   `evaluation.compare_runs` same-policy ⇒ all-zero deltas.
9. **Refusal ladder**: a checkpoint mismatched on env_kind / obs_schema /
   arch / head_version / shared_encoder must be refused with an honest
   message before any shape error (`test/test_models.py` covers it; make
   sure the order claim matches the code).

## Report

Write findings to `prompts/entity-obs-schema-phase23-REVIEW-findings.md`
(new file, do not stage it): per claim — CONFIRMED / REFUTED / UNTESTED
(why), with commands and evidence; then any defects found, ranked
Critical / Important / Minor, with file:line. End with an overall verdict:
safe to commit as-is, or what must change first.
