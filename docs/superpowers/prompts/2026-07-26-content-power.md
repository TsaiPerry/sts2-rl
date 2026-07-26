# Stream 2 — content audits: powers

Setup:
```bash
cd /c/Users/Perry/Desktop/sts2-rl
git worktree add /c/Users/Perry/Desktop/sts2-rl-power -b audit-power audit-pipeline
```
Copy everything below the line into a fresh Claude Code session.

---

You are running the **power content audits** of a source-to-sim audit
pipeline, concurrently with four other content streams and the engine-seam
tier.

WORKTREE (all work here): `c:\Users\Perry\Desktop\sts2-rl-power`  (branch `audit-power`)
GAME SOURCE (READ-ONLY): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Read first, in order

1. `docs/superpowers/prompts/_shared-audit-contract.md` — **your binding
   contract**: operational rules, the eight verdict rules, file ownership,
   the per-unit procedure. Follow it exactly.
2. `tools/audit/PROMPT.md` — the audit instruction sheet and bug-class
   checklist. **Read-only for you**; the relic stream owns it. Send it
   lessons via your report.
3. `docs/audit/seams/power_cmd.md` — the completed `PowerCmd` seam audit.
   This is the machinery your units plug into; read its gap list before
   verdicting anything, so you record power-level findings rather than
   re-reporting machinery ones.

## Your scope

`audits/power/**` — **134 units**. Roster: `py tools/audit/harness.py roster power`.

## Why this stream is the highest-yield one

The seam tier found that **sign-aware power typing** is systematically wrong
in the sim: C# decides Buff-vs-Debuff with `PowerModel.GetTypeForAmount(amount)`
(`PowerModel.cs:460-471`), which returns `Debuff` when the power is
`Counter` + `AllowNegative` and the amount is negative. The sim tests a
static `power_type` class attribute instead, so a negative-amount Strength or
Dexterity application is a Buff to the sim and a Debuff to the game.

**Bug class 3 in `PROMPT.md` therefore applies to every stack-amount power
you audit.** For each unit, check:

- does the C# power declare `AllowNegative`, and what is its `StackType`?
- does anything apply it with a negative amount?
- does the sim's port model the sign-dependence at all?

The seam-level finding is already recorded (`power_cmd` gap G1) and is
**dormant** — no player-side Artifact source exists in the game, so the
Artifact-interception consequence cannot fire today. Per rule 3, do not
re-verdict that machinery finding. **Do** record per-power consequences that
are reachable by some other route, and per rule 6 prove reachability before
labelling anything live.

Also read these `power_cmd` findings before you start; each constrains what
counts as a power-level gap versus an already-recorded machinery gap:
`ModifyPowerAmountGiven` / `Received` guard coverage, the missing
`AfterModifying*` machinery, the zero-amount no-op, and the `skip_next_tick`
re-arm on re-stacking.

## Cross-stream note

`hook_dispatch` gap **G9** is live and touches powers directly: the sim's
multiplicative modifier hooks return the **product** of all factors applied
once, where C# threads a running decimal through each listener. Executed
witness: Shrink ×0.7 + Vulnerable ×1.5 on a 20-damage attack gives the sim 20
and the game 21. Any power you audit that returns a multiplicative factor
participates in this. Do not re-verdict G9 (rule 3) — but if you find a power
whose factor is **non-dyadic**, say so loudly in your report: that widens G9's
blast radius, and the block-site analysis specifically depended on all ported
multipliers being dyadic.

## Batching

15 units per batch. Validate, status-check, run the suite, and commit each
batch before starting the next — see the shared contract for the exact
commands.

The relic stream is running the Tier 1 pilot and will harden `PROMPT.md` from
it. Either wait for that to land and branch after it, or start now and
**re-read `tools/audit/PROMPT.md` at each batch boundary** so you pick up
hardening as it arrives.

## Report

Write `.superpowers/sdd/content-power-report.md`. Include: units audited,
every gap with its live/dormant determination and reachability evidence, every
power found to carry the sign-awareness defect (this list is the deliverable
Perry most needs), any non-dyadic multiplicative factor you found, lessons for
`PROMPT.md` for the relic stream to fold in, any unit the roster
mis-resolved, any cross-record disagreement you spotted under rule 3, and
cost data (wall time and tokens per unit, gap rate, how many units needed
execution to settle).
