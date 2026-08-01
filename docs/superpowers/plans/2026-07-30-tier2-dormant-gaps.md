# 2026-07-30 — Tier 2 dormant-gap campaign

Worktree: `c:\Users\Perry\Desktop\sts2-rl-tier2` (branch `tier2-gaps`, carries
main's full staged state as of 2026-07-30). Executed subagent-driven: one
Sonnet implementer per task, one Sonnet reviewer per task, controller
adjudicates. Nothing is committed — Perry commits.

## Scope

Every mechanism written out in **Tier 2 (§2A–§2K) of `audit/GAP-QUEUE.md`**,
worked in queue order except that the two mechanisms whose records now carry
LIVE entries jump the queue (`power_cmd/G5`, `damage_pipeline/G4`). Tier 1
residue, Tier 3, and the unlabelled-liveness sweep are out of scope.

Out of scope but observed live on this tree (report to Perry, do not work
unless a Tier-2 fix reaches them naturally):

- `damage_pipeline/G2` (Tier 1B family; its blocker `power_cmd/G2` IS in
  scope as task T17)
- `power/skittish/AfterAttack`
- `event/crystal_sphere/*`, `event/war_historian_repy/g2` (deliberate
  deferred ports)

## Baseline (measured 2026-07-30 on this worktree)

```
py -m pytest test/ -q                  2 failed, 3347 passed, 6 xfailed (5:20)
py audit/tools/harness.py validate     848 record(s), 0 invalid
py audit/tools/audit_status.py         0 invalid; ~575 records stale (pre-
                                       existing — the character-port commit
                                       landed without a rehash; mechanically
                                       re-pinned at sweep 1, 2026-07-30)
py audit/tools/gap_queue.py counts     626 entries / 478 mechanisms / 11 live
py audit/tools/gap_queue.py cite-check 0 problem(s)
py audit/tools/gap_queue.py coverage   5 unlisted power_cmd sites (T0 fixes)
```

The 2 failures are the known missing
`RunReplays/.../933T39V18D/floor_49/actions.sts2replay` fixture. **Do not fix
them.** The floor is 3347 passed / those same 2 failures / 6 xfailed.

## Global constraints (bind every task)

1. **The decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2` is the
   source of truth** — not the queue's paraphrase, not the record's prose,
   not the sim's docstrings. Use NON-ASCENSION values.
2. **Re-execute the entry's own witness FIRST.** Roughly one entry in four is
   stale (eight rounds running). Stale → close with the enumeration you did;
   do not "fix" code that is already right.
3. **Test-driven.** Failing test first, watch it fail for the right reason.
4. **Surgical.** Every changed line traces to a named queue entry.
5. **Never run `git commit`, `push`, `checkout`, `stash`, `reset`, `restore`
   — and in this campaign, never `git add` either** (the controller manages
   the index; the working-tree diff is the task's review artifact).
6. "Original means game source": a legacy test that encodes old sim
   semantics gets UPDATED, with a comment naming the queue entry that moved it.
7. **A verdict flips only on evidence gathered from today's code.** A gap
   that is real but unobservable keeps `verdict: "gap"` with `live: false`
   plus the enumeration. Never re-verdict to `faithful` to clear a tier.
8. Record closes go through the closer helper
   (`<scratchpad>/closer.py`), stamp `Closed 2026-07-30 (tier-2 campaign):`,
   keep the `The text it replaced read:` tail, cite both C# and sim lines,
   and say what the close does NOT cover.
9. After record/queue edits:
   `py audit/tools/harness.py validate`, `py audit/tools/gap_queue.py counts`,
   `coverage`, `cite-check` — all clean (T0 clears the pre-existing coverage
   drift; after T0 the bar is 0 problems).
10. Never round-trip UTF-8 source through PowerShell
    `Get-Content`/`Set-Content`; use Python or the file tools.
11. RNG discipline: one shared `random.Random` per combat plus named
    `combat_rng` parity streams. Do not add draws to combat setup paths
    without checking seeded tests; when an entry says "off-stream", the fix
    routes through the named `combat_rng` stream the entry cites.
12. Update the mechanism's `audit/GAP-QUEUE.md` entry in place with a dated
    close/annotation that preserves the original text (existing "Mostly
    closed" entries are the model).

## Tasks

Each task = one implementer dispatch. The task brief is the mechanism's full
GAP-QUEUE.md entry (§ = queue section). Dependencies noted inline.

| # | mechanism(s) | § | note |
|---|---|---|---|
| T0 | queue coverage reconcile (5 unlisted `power_cmd` sites) | — | doc-only; gate must be green before batches |
| T1 | `power_cmd/G5` + `/step3` PowerInstanceType | 2E | **LIVE, n=13** — jumps queue |
| T2 | `damage_pipeline/G4` + `/step17.5`; `damage_pipeline/G6` + `/step17.4` | 2F | **G4 LIVE**; G6 is the two-line order swap beside it |
| T3 | `creature_card_cmds/N10` + `/step104` `/step105` auto-select shortcut | 2A | parity-live |
| T4 | `creature_card_cmds/step55` transform stream + Play-pile search | 2A | parity-live |
| T5 | `creature_card_cmds/G10` + `/step93` `/step102b` modify_shuffle_order | 2A | parity-live; moves Perfect Fit |
| T6 | `damage_pipeline/G5`; `creature_card_cmds/N4`; `/N5`+`/step31`; `/N2` | 2B | guard batch; N4 before T20 |
| T7 | `creature_card_cmds/N3` CardPileAddResult | 2B | after N4 |
| T8 | `creature_card_cmds/G8` residue; `/step61`; `monster/aeonglass/AfterCardGeneratedForCombat` | 2C+2K | shared dispatch; G8 Add site is the draw hot loop — measure before/after |
| T9 | `creature_card_cmds/G12` + `/step34` gold hooks; un-stub Dragon Fruit | 2C | visible today |
| T10 | `creature_card_cmds/G11` + `/step49`; `/G9` + `/step84` | 2C | discard interleave; draw hoist |
| T11 | `creature_card_cmds/step12`, `/step46`; `turn_structure/step20`, `/step55`, `/step17`; `hook_dispatch/step37` | 2C | six tiny dispatcher adds/swaps |
| T12 | residue verification: `turn_structure/G11`+`/step37`, `/G16`, `/step14`, `/G10` | 2C+2I | re-execute, close or annotate |
| T13 | `turn_structure/step8` AmountOnTurnStart; `/step32`+`/step67` | 2C+2I | turn-start machinery |
| T14 | `hook_dispatch/G1`; `/G7` | 2D | registry part 1: per-dispatch card order, per-item liveness, HasBeenRemovedFromState |
| T15 | `hook_dispatch/G5`; `/G6` | 2D | after T14 |
| T16 | `hook_dispatch/N5` run-level listener list | 2D | after T9, T14 |
| T17 | `power_cmd/G1`; `/G2` + `/step10` | 2E | sign-aware Artifact + Lamp; unblocks damage_pipeline/G2 chains |
| T18 | `power_cmd/G3`; `/step4`+`/step26`; `/step6` | 2E | after T17 |
| T19 | `creature_card_cmds/G5`+`/step22`; `/G6`; `/step18`; `/step23`; `/step26` | 2G | HP/block verb family |
| T20 | `creature_card_cmds/G7`; `/G13`+`/step8` | 2G | after T6 (N4) |
| T21 | `creature_card_cmds/N9`+`/step82`; `/step99`; `/step51`; `/step56` | 2G | Play-pile family; biggest design task |
| T22 | `monster_state_machine/G8`; `/G7`; `/G2` | 2H | construction validation family |
| T23 | `card/_unplayable_cost` (29 cards) | 2J | -1 convention + energy_cost short-circuit |
| T24 | `card/_printed_vars` (23 cards) | 2J | LIVE for the obs encoder; values from records |
| T25 | `power/_stack_type_single` (15 overrides) | 2J | delete overrides + test |
| T26 | `creature_card_cmds/step8c`; `power/_after_damage_given_substitution` | 2J | win-check veto; on_damage_dealt dispatch |
| T27 | `card/_is_dead_early_return` (5 cards) | 2J | blocked on `power/_death_prevention_branch` (Tier 1B) — verify, annotate, fix only if safe |
| T28 | `monster/_no_intent_unrepresentable`; `_intent_count_lost`; `_retained_corpse_in_scan`; `knowledge_demon/g1`; `magi_knight/g1` | 2K | intent model changes: obs encoder caution |

## Process adaptations (no-commit worktree)

- Controller `git add -A`s the approved state after each task, so at task
  start the unstaged diff is empty and at review time
  `git add -N . && git diff > task-N.diff` IS the task's diff.
- Reviewer gets brief + implementer report + diff file. Spec verdict AND
  quality verdict both required. Critical/Important → fix dispatch → re-review.
- Full suite once per task before DONE (floor: 3347/2/6). Full gate sweep
  (validate, rehash --all, audit_status, counts, cite-check, coverage,
  power_census slots) every 2–3 tasks and at campaign end.
- Ledger: `.superpowers/sdd/progress.md` (survives compaction; trust it plus
  `git status` over memory).
