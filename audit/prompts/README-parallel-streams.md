# Parallel audit streams — index and dependency graph

Nine streams. The seam tier, the gap queue and all six content streams have
landed; only the gap-fix stream is still gated. Every stream reads
`_shared-audit-contract.md` first — that file carries the operational rules,
the eight binding verdict rules, and the file-ownership matrix that keeps the
branches mergeable.

## Dependency graph

```
seam tier (Tasks 5-10) ──┬── [DONE] all 6 seams audited
                         │
                         ├──> gap-queue stream        [DONE] audit/GAP-QUEUE.md
                         └──> content-monster stream  (needs Task 10's AddBranch contract)

content-relic (pilot) ───┬──> content-power
  owns PROMPT.md         ├──> content-card
                         └──> content-event-enchantment
                              (these three inherit the hardened PROMPT.md;
                               they may start immediately instead and
                               re-read it at each batch boundary)

gap-queue ──> gap-fix stream   (also needs Perry's go-ahead; see below)
```

## Streams

| # | Stream | Prompt | Branch | Units | Status |
|---|---|---|---|---|---|
| 0 | seam tier | — | `audit-pipeline` | 6 seams | **complete** (6/6, 0 stale) |
| 1 | content — relic + **pilot** | `2026-07-26-content-relic.md` | `audit-relic` | 258 | **complete** (258/258) |
| 2 | content — power | `2026-07-26-content-power.md` | `audit-power` | 138 | **complete** (138/138) |
| 3 | content — card | `2026-07-26-content-card.md` | `audit-card` | 203 | **complete** (202/203; `card/sweep` is sim-only) |
| 4 | content — event + enchantment | `2026-07-26-content-event-enchantment.md` | `audit-event` | 82 | **complete** (82/82) |
| 5 | content — monster | `2026-07-26-content-monster.md` | `audit-monster` | 109 | **complete** (109/109, merged 2026-07-27) |
| 6 | content — potion | `2026-07-26-content-potion.md` | `audit-potion` | 51 | **complete** (51/51, merged 2026-07-27; 152 gap entries, 83 live) |
| 7 | gap queue | `2026-07-26-gap-queue.md` | `audit-gapqueue` | — | **complete** — `audit/GAP-QUEUE.md` |
| 8 | gap fixes | `2026-07-26-gap-fixes.md` | `audit-fixes` | ~20 live | **gated — read the warning** |

Content total: 841 units, 840 of them recorded (the sim-only `card/sweep`
excepted).

## Setup

Each stream gets its own worktree branched off the seam tier's current HEAD,
so it inherits the harness, the validator, the status tool and `PROMPT.md`:

```bash
cd C:/Users/Perry/Desktop/sts2-rl
git worktree add C:/Users/Perry/Desktop/sts2-rl-relic    -b audit-relic    audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-power    -b audit-power    audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-card     -b audit-card     audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-event    -b audit-event    audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-monster  -b audit-monster  audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-potion   -b audit-potion   audit-pipeline
```

Gated streams branch off later, once their dependency lands.

## Why these merge cleanly

Each content stream creates files in a directory no other stream touches
(`audit/records/relic/`, `audit/records/power/`, …). Each exists already but
holds nothing but a `.gitkeep`, so no two streams can produce the same path.
The seam tier's churn is confined to `audit/tools/harness.py`,
`test/test_hook_order.py`, `audit/records/seam/` and `audit/seams/`. The
genuinely shared files are
`audit/tools/PROMPT.md` and `audit/tools/name_overrides.json` — the contract
assigns both to the relic stream alone — plus `test/test_hook_order.py`, which
is seam-owned but which the potion stream was authorised by its prompt to
extend with one clearly-named class of content pins.

**What did NOT merge cleanly, and will not next time either, is the shared
TOOLING.** A completed kind is invisible until `gap_queue.py`'s own
`CONTENT_KINDS` learns it, and the potion merge additionally needed
`citation_check.py`, `backfill_sources.py` and `pins()` changed. Budget a
tooling commit per kind, and run
`py -m pytest test/test_audit_status.py -q` — it now pins the queue's kind list
against `harness.GAME_MODEL_DIRS`.

## Why the gap-fix stream cannot run in parallel

Every audit record hashes the sim files it audited. **Editing `sts2_rl/` makes
those records stale** — that is the staleness detector working as designed,
and it already fired once on this branch when `main` moved underneath it. A
fix stream running beside the audit streams would invalidate records as fast
as they are written, and each invalidated record needs an agent re-audit, not
a script.

So fixes are batched **after** the audit tiers, in one stream, with a
deliberate re-audit pass for the units each fix touches. That stream also
needs Perry's go-ahead: his standing decision for this run was to **leave
gaps queued and documented, not fixed**.

## Merge order

Merge `audit-pipeline` first (it owns the harness), then the content branches
in any order, then the gap queue. Re-run `py audit/tools/audit_status.py` after each
merge — a stale count above zero means a merge brought in a sim change that
invalidates a record, and the record needs re-auditing rather than a hash
rewrite.

**Then re-run `py audit/tools/gap_queue.py counts` AND read its kind list.**
`audit_status.py` derives its kinds from `harness.GAME_MODEL_DIRS`;
`gap_queue.py` keeps its own. When `potion` merged, the two disagreed for a day
— `counts` said `NOT AUDITED : potion (51 C# units)` while `audit_status` said
audited — and 152 gap entries stayed out of the queue. The regression test is
`test/test_audit_status.py::TestQueueGeneratorCoversEveryKind`; the merge is not
finished until it passes and `gap_queue.py coverage` exits 0.

### Repath any branch cut before the audit/ restructure

`audit-pipeline` moved the whole pipeline into `audit/` on 2026-07-26. Streams
branched before that write their records to the old `audits/<kind>/` path, and a
merge will faithfully deliver them there — no conflict, just the wrong
directory, and `audit_status.py` will keep reporting them unaudited.

The tools and the seam records were moved with `git mv`, so git follows those
renames and they merge cleanly on their own. Only the stream's **new** record
files need moving, once per merged branch:

```bash
git merge audit-<stream>
git mv audits/<kind>/*.json audit/records/<kind>/    # per kind the branch wrote
rmdir audits/<kind> audits 2>/dev/null
py audit/tools/harness.py validate                   # 0 invalid
py audit/tools/audit_status.py                       # <kind> now counts, 0 stale
git commit
```

Then grep the merged records for `tools/audit/`, `tools/audit_status.py`,
`audits/` and `docs/audit/` and repoint any prose citations; the hashes
themselves never need touching, because they are over `sts2_rl/` and game files
that did not move.

**A stream that has not started yet should branch off current `audit-pipeline`
and skip all of this.**
