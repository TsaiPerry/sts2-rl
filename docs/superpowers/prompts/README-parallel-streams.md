# Parallel audit streams — index and dependency graph

Eight streams. Five can start now; three are gated. Every stream reads
`_shared-audit-contract.md` first — that file carries the operational rules,
the eight binding verdict rules, and the file-ownership matrix that keeps the
branches mergeable.

## Dependency graph

```
seam tier (Tasks 5-10) ──┬── [running] Task 10 monster_state_machine
                         │
                         ├──> gap-queue stream        (needs all 6 seams)
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
| 0 | seam tier | — | `audit-pipeline` | 6 seams | running (Task 10 last) |
| 1 | content — relic + **pilot** | `2026-07-26-content-relic.md` | `audit-relic` | 258 | ready |
| 2 | content — power | `2026-07-26-content-power.md` | `audit-power` | 134 | ready |
| 3 | content — card | `2026-07-26-content-card.md` | `audit-card` | 203 | ready |
| 4 | content — event + enchantment | `2026-07-26-content-event-enchantment.md` | `audit-event` | 82 | ready |
| 5 | content — monster | `2026-07-26-content-monster.md` | `audit-monster` | 109 | **gated on Task 10** |
| 6 | gap queue | `2026-07-26-gap-queue.md` | `audit-gapqueue` | — | **gated on Task 10** |
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
(`audits/relic/`, `audits/power/`, …), none of which exists yet. The seam
tier's churn is confined to `tools/audit/harness.py`, `test/test_hook_order.py`,
`audits/seam/` and `docs/audit/seams/`. The only genuinely shared files are
`tools/audit/PROMPT.md` and `tools/audit/name_overrides.json`, and the
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
in any order, then the gap queue. Re-run `py tools/audit_status.py` after each
merge — a stale count above zero means a merge brought in a sim change that
invalidates a record, and the record needs re-auditing rather than a hash
rewrite.
