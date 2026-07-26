# Relic content audit — batch 13 of 18

**Generated 2026-07-26.** One of 15 parallel batch prompts. Copy everything
below the line into a fresh Claude Code session.

Setup (each parallel session needs its OWN worktree — see the concurrency
contract below):

```bash
cd /c/Users/Perry/Desktop/sts2-rl
git worktree add /c/Users/Perry/Desktop/sts2-rl-relic-b13 -b audit-relic-b13 audit-relic
```

---

You are executing **batch 13** of the relic content audits in an
established source-to-sim audit pipeline. Batches 1–3 are complete and
committed (46 of 258 relics, 51 records, 0 invalid); you are repeating a proven
procedure, not inventing one.

WORKTREE (all work here): `c:\Users\Perry\Desktop\sts2-rl-relic-b13` (branch `audit-relic-b13`)
GAME SOURCE (**READ-ONLY**): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Read these first, in this order — do not skip any

1. `docs/superpowers/prompts/_shared-audit-contract.md` — your binding
   contract: operational rules, the EIGHT BINDING VERDICT RULES, file
   ownership, the per-unit procedure. Follow it exactly.
2. `tools/audit/PROMPT.md` (**v5**) — the versioned instruction sheet and the
   23-item bug-class checklist. Check EVERY class against EVERY unit.
3. `.superpowers/sdd/content-relic-sweeps.md` — five pool-wide sweeps already
   ran across all 258 relics. **Units in your batch that they diagnosed are
   listed below; read their sweep section before auditing them so you confirm
   rather than rediscover.**
4. `.superpowers/sdd/content-relic-report.md` — the batch-1 report (depth
   calibration, cost data, the live/dormant discipline).
5. Skim these records to calibrate depth and style — they are the standard your
   work is measured against: `audits/relic/unsettling_lamp.json` (the deepest),
   `audits/relic/belt_buckle.json`, `audits/relic/brilliant_scarf.json`,
   `audits/relic/calling_bell.json`.

## Your batch (15 units)

- `prismatic_gem`
- `pumpkin_candle`
- `punch_dagger`
- `radiant_pearl`
- `rainbow_ring`
- `razor_tooth`
- `red_mask`
- `red_skull`
- `regal_pillow`
- `reptile_trinket`
- `ringing_triangle`
- `ripple_basin`
- `royal_poison`
- `royal_stamp`
- `ruined_helmet`

## Pre-diagnosed units — CONFIRM these, do not rediscover

The pool-wide sweeps already reached these findings and recorded the evidence. Your job is to settle each one properly in its record (live vs dormant, with executed evidence), citing the sweep — not to re-derive it from scratch.

- **`pumpkin_candle`** — Sweep A candidate (`kindle_count`; C# resets at `AfterCombatEnd`).
- **`punch_dagger`** — Sweep C stub: `AfterObtained` dispatched; 'no enchantments' is FALSE.
- **`red_skull`** — Sweep A candidate (`_applied`; C# resets at `AfterCombatEnd`). Settle by execution.
- **`regal_pillow`** — Sweep C stub: `AfterRestSiteHeal` and `AfterRoomEntered` dispatched.
- **`royal_poison`** — Named witness in `audits/seam/turn_structure.json` G13 (turn-1 player-damage trigger). Cite and match.
- **`royal_stamp`** — Sweep C stub: `AfterObtained` dispatched; 'no enchantments' is FALSE.
- **`ruined_helmet`** — Sweep A candidate (`_used`; C# resets at `AfterCombatEnd`). Settle by execution. Also a named listener in `audits/seam/power_cmd.json` gaps G3/G4 — cite and match under rule 3.

## Sweeps A and B were REWRITTEN on 2026-07-26 — read the corrections

Batches 4-8 each faulted the pool-wide sweeps they were told to trust, and all
of the faults were real. Both sweeps are fixed and re-run; the corrected
findings are in `.superpowers/sdd/content-relic-sweeps.md`. What changed:

- **Sweep A** pooled turn-END resets with turn-START resets and never tested the
  safety claim on either; counted `x = x + 1` as a reset; printed a **census of
  C# overrides** as if it were a census of resets (so it credited relics with
  resets they do not perform); and could not see a field written only in
  `__init__` from a parameter nothing passes. Its "safe" bucket is now 13 units,
  not 21, and 7 relics are confirmed carrying state, not 3.
- **Sweep B** read only the FIRST LINE of each `IsAllowed` body, so multi-clause
  bodies lost every gate after the first. The `IsBeforeAct3TreasureChest`
  cluster is **17 relics, not 16**.

**The lesson, which applies to your batch:** a sweep's output is evidence, not
authority. If a bucket label makes a safety claim ("safe only if the reset runs
before any reader"), that claim was probably never executed — execute it or move
the unit out of the bucket. Report anything you find wrong in your lessons file;
four of the five previous batches found something.

## Procedure per unit

```
py tools/audit/harness.py skeleton relic/<id>
```
Then: read the C# model **in full** → read `sts2_rl/relics/<id>.py` **in full**
→ fill a verdict for every enumerated hook, plus a `guards` entry per
conditional that needed thought (not only per problem) → check every numeric
constant against the NON-ascension branch → validate.

Record shape: `hooks` (one entry per `public override`, each with `maps_to` +
`verdict`), `guards` (`{what, verdict, rationale|issue}`), unit `verdict` =
max over all entries in precedence order `faithful < waiver <
deliberate-divergence < gap`, `audited` = today's date `YYYY-MM-DD`.

## What separates a real finding from a plausible one

- **Rule 5**: never justify `faithful` with an unreachability claim you have
  not EXECUTED. Write a probe, RUN it, record the observed output.
- **Rule 6**: labelling a gap LIVE requires proving BOTH sides reachable with
  ported content — the relic obtainable, the trigger present, the code path
  actually taken. Otherwise label it dormant and NAME the concrete unported
  thing that would make it live.
- **Rule 1**: `waiver` means genuinely OUT OF SCOPE (multiplayer,
  presentation/animation, ascension values, other characters). "No ported
  content triggers this" and "the sim has no such system" are **dormant gaps**,
  not waivers.
- **Rule 3**: the same mechanism gets ONE verdict at every site, including
  across records. If an `audits/seam/*.json` record already verdicted a
  mechanism, cite it and match it — do not re-derive.
- **Rule 7**: the record hashes only the unit's own two files. If a rationale
  leans on any third file, say so explicitly in the rationale.
- **Rule 8**: verify every test path you cite by grepping for it.

## CONCURRENCY CONTRACT — read this, it is what makes parallel batches mergeable

Up to 15 batches run at once against sibling worktrees of one repo and merge
afterwards. Merges stay trivial only while nobody edits a shared file.

**You may create/edit ONLY:**
- `audits/relic/<your 15 unit ids>.json`
- `tools/audit/relic_probes_b13.py` — **your own** probe module (see below)
- `.superpowers/sdd/relic-batch-13-lessons.md` — your report

**You may NOT touch, for any reason:**
- `tools/audit/relic_probes.py`, `tools/audit/PROMPT.md`,
  `.superpowers/sdd/content-relic-sweeps.md`,
  `.superpowers/sdd/content-relic-report.md` — every batch so far edited these
  and that is exactly what would conflict. They are **read-only** to you.
- `sts2_rl/**` (engine), `tools/audit/harness.py`, `audits/seam/**`,
  `docs/audit/**`, `.superpowers/sdd/progress.md`, any other batch's records.

**Your probe module.** Copy the import preamble from
`tools/audit/relic_probes.py`, then define your batch's probes in
`tools/audit/relic_probes_b13.py` with its own `main()`; run it as
`py tools/audit/relic_probes_b13.py`. Do NOT register anything in the
shared module. Re-USING the shared module read-only is encouraged —
`py tools/audit/relic_probes.py turn-order` is the executed hook-order
reference and you should not verdict a hook mapping without it.

**Lessons instead of PROMPT.md edits.** If a new bug class or a pool-wide
shape surfaces, write it to `.superpowers/sdd/relic-batch-13-lessons.md`
with the unit that exhibited it and the evidence. The relic stream owner folds
the lessons files into `PROMPT.md` after the batches merge. Do not bump the
version header yourself. If nothing surfaced, say so — do not pad.

## Hard rules

- **NEVER modify engine code under `sts2_rl/`.** Audits record findings; they
  do not fix them. Baseline is **2476 passed / 31 xfailed**; if `py -m pytest
  test/ -q` differs you made an accidental edit — revert it.
- The game source is READ-ONLY.
- Commit on `audit-relic-b13` only. **Never push. Never touch `main` or
  `audit-relic`.**
- Run every command in the FOREGROUND with a generous timeout (600000 ms). Do
  not start background jobs — they cannot notify you and you will stall.
- Python is `py` on this machine, not `python`.
- Commit the moment the batch validates. Sessions here have died at usage
  limits; committed files are what survive. Do not polish before committing.

## Finish

1. `py tools/audit/harness.py validate` → 0 invalid
2. `py tools/audit/citation_check.py audits/relic` → **MISSING 0,
   OUT-OF-RANGE 0**. This is the mechanical enforcement of binding rules 7
   and 8: it resolves every `file.py:123` / `File.cs:45-67` you cite and
   checks the path exists and the line number is real. It already caught a
   fabricated-looking line number in a committed batch-2 record. A
   non-zero count means you cited something that does not exist — fix the
   citation, do not silence the check. (Its UNHASHED list is a rule-7
   REMINDER, not a failure: those files must be *named as unhashed* in the
   rationale that leans on them.)
3. `py tools/audit_status.py --kind relic` → your 15 units audited
4. `py -m pytest test/ -q` → unchanged (2476 passed / 31 xfailed)
5. `git add audits/relic tools/audit/relic_probes_b13.py .superpowers/sdd/relic-batch-13-lessons.md`
   then commit, naming the units, the gap count, and each LIVE gap with its
   one-line executed evidence.

## Report

Write `.superpowers/sdd/relic-batch-13-lessons.md` containing: the 15
units with rollup verdicts; every LIVE gap with its executed evidence; every
dormant gap with the concrete unported thing that would make it live; any
cross-record disagreement under rule 3; any unit the roster mis-resolved (and
the `name_overrides.json` entry it would need — **report it, do not apply
it**); any new bug class or pool-wide shape, with the unit that exhibited it;
and the commit SHA. Be concise and factual. Say plainly if anything is
unverified or was left out.
