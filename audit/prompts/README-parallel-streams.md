# Parallel audit streams — index and dependency graph

Eight streams. The seam tier and the gap queue have landed; the five content
streams can all start now; the gap-fix stream is gated. Every stream reads
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
| 1 | content — relic + **pilot** | `2026-07-26-content-relic.md` | `audit-relic` | 258 | ready |
| 2 | content — power | `2026-07-26-content-power.md` | `audit-power` | 134 | ready |
| 3 | content — card | `2026-07-26-content-card.md` | `audit-card` | 203 | ready |
| 4 | content — event + enchantment | `2026-07-26-content-event-enchantment.md` | `audit-event` | 82 | ready |
| 5 | content — monster | `2026-07-26-content-monster.md` | `audit-monster` | 109 | ready (Task 10 landed) |
| 6 | gap queue | `2026-07-26-gap-queue.md` | `audit-gapqueue` | — | **complete** — `audit/GAP-QUEUE.md` |
| 7 | gap fixes | `2026-07-26-gap-fixes.md` | `audit-fixes` | ~20 live | **gated — read the warning** |

Content total: 786 units.

## Setup

Each stream gets its own worktree branched off the seam tier's current HEAD,
so it inherits the harness, the validator, the status tool and `PROMPT.md`:

```bash
cd C:/Users/Perry/Desktop/sts2-rl
git worktree add C:/Users/Perry/Desktop/sts2-rl-relic    -b audit-relic    audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-power    -b audit-power    audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-card     -b audit-card     audit-pipeline
git worktree add C:/Users/Perry/Desktop/sts2-rl-event    -b audit-event    audit-pipeline
```

Gated streams branch off later, once their dependency lands.

## Why these merge cleanly

Each content stream creates files in a directory no other stream touches
(`audit/records/relic/`, `audit/records/power/`, …). Each exists already but
holds nothing but a `.gitkeep`, so no two streams can produce the same path.
The seam tier's churn is confined to `audit/tools/harness.py`,
`test/test_hook_order.py`, `audit/records/seam/` and `audit/seams/`. The only
genuinely shared files are
`audit/tools/PROMPT.md` and `audit/tools/name_overrides.json`, and the
contract assigns both to the relic stream alone.

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
