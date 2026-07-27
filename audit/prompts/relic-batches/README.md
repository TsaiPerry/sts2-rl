# Running the remaining relic batches in parallel

**Generated 2026-07-26** from `audit-relic` at batch 3 (46 of 258 relics
audited). 15 prompt files, `relic-batch-04.md` … `relic-batch-18.md`, cover the
remaining **212** units. Each is self-contained: copy everything below its
`---` into a fresh Claude Code session.

## Why the batches conflict, and what was changed

Batches 1–3 each touched three files beyond their own records:

```
audit/tools/relic_probes.py                  batch 1, 2, 3
audit/tools/PROMPT.md                        batch 1, 3
.superpowers/sdd/content-relic-sweeps.md     batch 2, 3
```

Those three are the entire conflict surface — the per-unit records are disjoint
and merge trivially. So the parallel prompts make all three **read-only** and
give each batch its own writable substitutes:

| Shared file (now read-only) | Per-batch substitute |
|---|---|
| `audit/tools/relic_probes.py` | `audit/tools/relic_probes_bNN.py` |
| `audit/tools/PROMPT.md` | `.superpowers/sdd/relic-batch-NN-lessons.md` |
| `.superpowers/sdd/content-relic-sweeps.md` | same lessons file |

With that, every batch writes only files no other batch touches, and the merge
is a fast-forward per branch with zero conflicts.

## Setup

Each session needs its **own worktree** — two sessions sharing one working
directory will race on `.git/index` and corrupt each other's commits.

```bash
cd /c/Users/Perry/Desktop/sts2-rl
for n in 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18; do
  git worktree add "/c/Users/Perry/Desktop/sts2-rl-relic-b$n" -b "audit-relic-b$n" audit-relic
done
```

Branch from **`audit-relic`**, not `main` — the batches need batches 1–3's
records, the v4 `PROMPT.md`, the sweep findings and the probe modules.

Run as many concurrently as you like; they are genuinely independent. Nothing
stops you doing 5 at a time in three rounds if that is easier to supervise.

## Merging

```bash
cd /c/Users/Perry/Desktop/sts2-rl-relic          # the audit-relic worktree
for n in 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18; do
  git merge --no-ff "audit-relic-b$n" -m "audit(relic): merge batch $n"
done
py audit/tools/harness.py validate               # 258 records, 0 invalid
py audit/tools/citation_check.py audits         # MISSING 0, OUT-OF-RANGE 0 (relic AND seam)
py tools/audit_status.py --kind relic            # audited 258, unaudited 0
py -m pytest test/ -q                            # 2476 passed / 31 xfailed
```

Order does not matter. A conflict here means a batch violated the concurrency
contract — check what it touched before resolving.

## After the merge — the fold-in step

1. Read every `.superpowers/sdd/relic-batch-NN-lessons.md`.
2. Fold genuinely new bug classes into `audit/tools/PROMPT.md` and bump the
   version header **once**. Only classes a unit actually exhibited; a checklist
   entry that never fired is noise the other four content streams pay for.
3. If several batches independently hit the same shape, that is a **new
   pool-wide sweep** — add it to `relic_probes.py`, run it across all 258, and
   record it in `content-relic-sweeps.md`. Four of the five existing sweeps
   were born exactly this way.
4. Fold the per-batch probe modules into `relic_probes.py` if any are reusable;
   delete the rest.
5. Update `.superpowers/sdd/content-relic-report.md` with the final coverage
   table and the full gap list.

## Verification gate

`audit/tools/citation_check.py` is what makes 15 unsupervised batches
reviewable. It resolves every `file.py:123` / `File.cs:45-67` a record cites
and fails on paths that do not exist and line numbers past end-of-file — the
mechanical half of binding rules 7 and 8, which exist because agents have
invented both. It found a wrong line number in a committed batch-2 record on
its first run.

**Run it over `audit/records/`, not `audit/records/relic/`.** The seam tree went unchecked for
the whole run and had 1 missing path and 6 line numbers past end-of-file when it
was finally checked — in the records that are the *authority* every batch is told
to cite and match, one of which I had introduced myself while patching a seam
guard. Batch 15 found it by quoting a seam citation verbatim and watching the
check fail. A gate you point at only part of the tree is a gate with a hole in it.

It does **not** judge whether a citation is apt, or whether a verdict is right.
Those still need a reader. Spot-check each batch's LIVE gaps against the
sources; a wrong `faithful` is the residual risk the harness cannot catch, and
it is the one the design document names.

## What parallelism costs

Honest accounting, from batches 1–3:

- **Lessons stop compounding.** Batch 3 found `TestMode.IsOn` branches (dead C#
  test scaffolding that `calling_bell` ported as if it were shipping
  behaviour) and added it as bug class 18 — batches 4+ get that because they
  branch from `audit-relic` after batch 3. But batch 11 will *not* learn from
  batch 7. The five existing sweeps already captured the big repeating shapes,
  which is what makes the trade acceptable; it would not have been before them.
- **Onboarding is re-paid per session.** A fresh session spends roughly 25–30k
  tokens reading the contract, `PROMPT.md`, the sweeps and the calibration
  records before auditing anything. Batch 3 (a subagent, cold) cost ~291k
  tokens for 15 units against ~8.4k/unit marginal in a warm session.
  Parallelism buys wall-clock, not tokens.
- **Duplicate discovery.** Two batches may independently find the same new
  shape and write it up twice. That is cheap to reconcile at fold-in and is
  strictly better than neither finding it.

## Pre-diagnosed units

The five pool-wide sweeps already diagnosed **72** of the 212 remaining units.
Each prompt lists its own, with the sweep's finding and instructions to
*confirm* rather than rediscover. Batch 5 is the only one with none — its 15
units are audited cold.
