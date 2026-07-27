# Merging the relic tier

Copy everything below the line into a fresh Claude Code session. Nothing to
set up first — the work happens in the existing audit worktree.

---

You are merging the completed **relic** content audit into a source-to-sim
audit pipeline, then reviewing and integrating it. Four content tiers have
already been through this exact sequence; the traps below are the ones they hit.

WORKTREE: `c:\Users\Perry\Desktop\sts2-rl-audit`  (branch `audit-pipeline`)
RELIC WORKTREE (source of the merge): `c:\Users\Perry\Desktop\sts2-rl-relic`  (branch `audit-relic`)
GAME SOURCE (READ-ONLY): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Operational rules

- FOREGROUND commands only, generous timeouts (600000 ms). No background jobs
  — they cannot notify you and you will stall.
- **NEVER modify `sts2_rl/`.** The branch is engine-clean and must stay so:
  `git diff --name-only main...audit-pipeline | grep "^sts2_rl/"` must print
  nothing. Verify before you finish.
- Commit on `audit-pipeline` only. **Never push. Never touch `main`** — Perry
  commits there himself. Stage, don't commit, if asked to put anything on main.
- Commit in stages; several agents on this project have died at usage limits.
- Read `audit/README.md` first for the model and the verdict vocabulary.

## Starting state

`audit/records/` holds **428 records** — 6 seam + power 138, card 202, event
65, enchantment 17 — all reviewed and fix-passed. `relic` (258) and `monster`
(109) are the two unaudited kinds.

`audit-relic` is **complete: 258 records, the full relic roster.** Every batch
branch `audit-relic-b04` … `b18` is contained in `audit-relic`, so this is
**one merge**, not eighteen.

There is a known, unresolved item you must not be confused by: **181 records
are currently stale** because `main`'s `ALL_POWERS` commit moved `powers.py`.
That is a separate pending decision (rehash 177 vs re-audit 4) and is not
yours. Do not rehash anything to make a number look better.

---

## STEP 1 — merge, and expect two specific conflicts

```bash
cd c:/Users/Perry/Desktop/sts2-rl-audit
git merge audit-relic
```

**Conflict type 1 — `CONFLICT (file location)` on the 258 records.** This is
benign and expected. `audit-relic` was cut before the `audits/` →
`audit/records/` restructure, so it writes to the old path; git's rename
detection *already relocates the files correctly* to `audit/records/relic/`
and is only asking you to confirm. Accept with `git add audit/records/relic/`.
Verify the count is 258 and that nothing landed in a stray top-level `audits/`.

**Conflict type 2 — four SEAM records. This one needs care.** `audit-relic`
edits `audits/seam/{creature_card_cmds,damage_pipeline,hook_dispatch,turn_structure}.json`
— small additive edits (~15 lines total) adding cross-references to relic
records, e.g. `relic/lizard_tail` in `damage_pipeline`. But it made them
against the **pre-review, pre-restructure** seam records, which
`audit-pipeline` has since rewritten substantially through six review passes.

Do **not** resolve these with `--theirs` (drops the review fixes) and do
**not** blindly take `--ours` (silently drops real cross-reference work).
Resolve to `audit-pipeline`'s version, then **hand-port each relic
cross-reference** into the current text. Diff the branch's seam records
against the merge base to see exactly what to carry:

```bash
base=$(git merge-base audit-pipeline audit-relic)
git diff $base audit-relic -- audits/seam/
```

Report how many cross-references you ported.

## STEP 2 — repath everything the stream brought with it

The restructure landed mid-flight for this stream too, so:

- **Probe scripts** — 18 files (`relic_probes.py`, `relic_probes_b04` …
  `b18`, `citation_check.py`) land at `tools/audit/`. `git mv` them to
  `audit/tools/`.
- **`tools/audit/PROMPT.md`** — the relic stream *owns* this file by contract
  (it ran the Tier 1 pilot and hardens the prompt). Its version is likely
  newer than the one at `audit/tools/PROMPT.md`. Compare both and keep the
  relic stream's hardening, at the new path.
- **Batch prompts** — `docs/superpowers/prompts/relic-batches/` (19 files).
  `git mv` to `audit/prompts/relic-batches/`.
- **Imports** — every probe will have `from tools.audit.harness import …`,
  which is now `from audit.tools.harness import …`. Fix and run each one;
  all must exit 0.
- **Citation sweep** — the records will cite `py tools/audit/<probe>.py`
  (now `audit/tools/`) and `audits/<kind>/` (now `audit/records/<kind>/`).
  Sweep all 258. Prior tiers had 320 and 141 of these respectively; validate
  the JSON stays parseable after any bulk rewrite.

## STEP 3 — backfill source hashes

Until recently a content record could hash only one `game_source` and one
`sim_source`, so every other file its verdicts cited was invisible to
staleness detection. The schema now has an optional `extra_sources`, and
`audit/tools/backfill_sources.py` populates it from the records' own
citations. Run it over the relic tier.

It reports citations found / resolved / already-covered / **unresolvable**.
Unresolvable is a finding, not noise — a citation resolving to nothing is a
typo or a stale path. Prior tiers hit 0; report any.

Then **prove it worked** rather than asserting it: on a scratch copy, touch a
file several relic records cite and confirm `audit_status.py` now reports
those records stale where it previously reported 0. Report before/after.

## STEP 4 — review the tier

**Do this. All four prior tiers were reviewed and a review found real defects
in every single one**, including two that the audits' own reports contradicted.

Dispatch a reviewer subagent (read-only; it must not modify any file). It
cannot check 258 records — require it to **state its sampling method and
sizes and report a defect rate per verdict class** so the result extrapolates.
Point it at the classes that actually broke elsewhere:

- **`waiver`s.** `waiver` means genuinely out of scope — multiplayer,
  presentation, ascension, other characters, potions. "No ported content
  triggers this" and "the C# side is unported" are **dormant gaps**. One seam
  audit shipped five waivers that were really gaps, two on false "no ported
  caller" claims. Have it re-run the grep behind any reachability claim.
- **LIVE claims.** LIVE requires proving BOTH sides reachable with ported
  content. A false LIVE sends someone to fix correct code; one seam audit
  shipped a "live" gap whose trigger does not exist anywhere in the game.
- **`faithful` resting on unexecuted unreachability.** Three such claims have
  been false and two were their seam's live gaps. Require at least two
  checked by *running the sim*.
- **Rule 3 — one mechanism, one verdict at every site, including across
  records.** This has been a *gap detector* twice: two records disagreeing
  about one mechanism turned out to mean both were wrong. Relics interact
  with everything, so cross-record contradictions are likelier here than
  anywhere. Check relic verdicts against the seam and power records
  especially.
- **`deliberate-divergence` under rule 2** — same shape, *identical*
  observable. If a player or replay would see a difference, it is a gap.

Also have it check: are there **pins**? All 31 `strict=True` xfails in
`test/test_hook_order.py` are seam-tier; no content mechanism has one, so
content fixes cannot prove themselves. Relic gaps are good pin candidates.

## STEP 5 — fix pass

Dispatch **one** fixer with the complete findings list, not one per finding —
per-finding fixers each rebuild context and re-run probes, and a previous
fix wave here cost more than the tasks it fixed. Scope it to
`audit/records/relic/**` plus its report.

Note for the fixer: prior fix passes each found *additional* live gaps while
correcting the ones they were sent — five clone-dropping sites where the
review found one, and a live debuff-strip gap that surfaced only because a
review caught a false grep claim. Encourage re-derivation, not just patching.

## STEP 6 — regenerate the queue and the README

- `py audit/tools/gap_queue.py` is the extractor; it verifies counts and
  citations but does **not** write the markdown — `audit/GAP-QUEUE.md` is
  authored prose. Widen it to include relic, grouping **by mechanism**: 788
  entries currently collapse to 403 mechanisms, and relic will collapse hard
  too. Extend the cross-record merge table for any relic mechanism that also
  appears in a seam or power record.
- Update `audit/README.md`'s Status: relic moves out of "not audited", and
  **`monster` (109) becomes the only unaudited kind**. Keep the coverage
  caveat honest.
- Do not paste generated numbers into prose you cannot regenerate; the README
  already tells readers to run the commands instead, and a pasted table there
  has gone stale twice.

## Verify before you finish

```
py audit/tools/harness.py validate --strict-inherited   -> 686 records, 0 invalid
py audit/tools/audit_status.py                          -> relic 258/258
py audit/tools/gap_queue.py cite-check                  -> 0 problems
py audit/tools/gap_queue.py coverage                    -> 0 unlocatable
py -m pytest test/ -q                                   -> no regressions (2522 passed / 38 xfailed at last count)
git diff --name-only main...audit-pipeline | grep "^sts2_rl/"   -> nothing
```

Every probe under `audit/tools/` exits 0. `validate --strict-inherited` may
flag relic records with un-audited **inherited** overrides — that check
recently started following `: BaseClass` and surfaced 16 such records in other
tiers, all legitimately waivable as presentation, but **read each in the C#
before waiving**; `InitialDescription` in particular can carry logic.

## Report

Write `.superpowers/sdd/relic-merge-report.md`. Return at the end: the merge
resolution (including how many seam cross-references you ported), the repath
counts, the backfill numbers with the staleness before/after proof, the
review's defect rate per class, what the fix pass changed, the new totals
(records, gap entries, distinct mechanisms), and anything you could not settle.
