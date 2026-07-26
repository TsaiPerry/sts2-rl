# Stream 1 — content audits: relics (+ the Tier 1 pilot)

Setup:
```bash
cd /c/Users/Perry/Desktop/sts2-rl
git worktree add /c/Users/Perry/Desktop/sts2-rl-relic -b audit-relic audit-pipeline
```
Copy everything below the line into a fresh Claude Code session.

---

You are running the **relic content audits** of a source-to-sim audit
pipeline, and you own its **Tier 1 pilot** — the batch that proves the
per-unit procedure the other content streams repeat.

WORKTREE (all work here): `c:\Users\Perry\Desktop\sts2-rl-relic`  (branch `audit-relic`)
GAME SOURCE (READ-ONLY): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Read first, in order

1. `docs/superpowers/prompts/_shared-audit-contract.md` — **your binding
   contract**: operational rules, the eight verdict rules, file ownership,
   the per-unit procedure. Follow it exactly.
2. `docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md` — what
   this pipeline is and why.
3. `tools/audit/PROMPT.md` — the versioned audit instruction sheet and
   bug-class checklist. **You are its sole owner** (see below).
4. `docs/superpowers/plans/2026-07-24-source-audit-pipeline.md`, **Task 11
   only** (search `### Task 11`) — the pilot's exact steps.

## Your scope

`audits/relic/**` — **258 units**. Roster: `py tools/audit/harness.py roster relic`.

You additionally own `tools/audit/PROMPT.md` and
`tools/audit/name_overrides.json`. No other stream may edit them; the others
will send you lessons to fold in. When you change `PROMPT.md`, bump its
version header.

Relic-specific notes from the plan: the roster includes event/Neow/Ancient-
shrine pools. Out-of-combat no-op stub relics get `waiver` verdicts **naming
the stubbed behavior** — per rule 1, "not implemented" alone is a dormant
gap, so the waiver only holds if the behavior is genuinely out of scope.

## The pilot batch

Audit the first 15 relics alphabetically, and **swap in
`relic/unsettling_lamp`** if it is not among them.

Unsettling Lamp is the design document's worked example and calibrates the
depth expected of every content record. Its record must carry guard entries
for all three of:
- `power.IsVisible`
- sign-aware `GetTypeForAmount(amount)` (a negative Dexterity amount counts
  as a Debuff)
- the `ITemporaryPower` double-dip

each with a real verdict. A waiver among them must name what makes it
unreachable — not merely say "out of scope".

Two live findings from the seam tier bear directly on Unsettling Lamp and are
already settled; do not re-derive them, but make sure your record is
consistent with both (rule 3):
- the Lamp's `modify_power_amount` correctly runs BEFORE the Artifact
  early-return (`audits/seam/power_cmd.json`, the ordering pin)
- the Lamp × `TemporaryStrength` double-dip equivalence was verified by
  execution and holds (`power_cmd` guard N2)

## Then harden the prompt

Append to `tools/audit/PROMPT.md` any bug class or procedure lesson the pilot
surfaced — a recurring C# idiom the checklist misses, a systematic way the
sim's relic ports differ. Bump the version header. **If nothing surfaced, say
so in your report; do not pad the file.**

## STOP AND REPORT AFTER THE PILOT

The content tier is 786 units across five streams and Perry has not yet
prioritised it. After the pilot batch validates and commits, stop and report
with real cost data:

- wall time and tokens per unit
- the gap rate, split live vs dormant
- how many units needed **execution** (not just reading) to settle
- which bug classes actually fired
- your recommendation for prioritising the remaining 243 relics and for the
  other four content streams

Do not launch the full relic sweep before that report. If Perry greenlights
it, continue in 15-unit batches, committing each.

## Report

Write `.superpowers/sdd/content-relic-report.md`. Include: units audited,
every gap with its live/dormant determination and reachability evidence,
every `PROMPT.md` change with its rationale, any unit the roster
mis-resolved, any cross-record disagreement you spotted under rule 3, the
cost data above, and the prioritisation recommendation.
