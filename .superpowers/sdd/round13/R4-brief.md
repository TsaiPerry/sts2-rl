# R4 — settle unlabelled batch relic-1 (14 entries, 13 records)

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding), then your
manifest: `.superpowers/sdd/unlabelled-r13/relic-1-brief.md`.

## The job

Every entry in the manifest is a recorded gap whose liveness nobody has
settled — neither shown live nor shown dormant. Settle each **by
execution**, one of:

- **FIXED** — it is a real divergence: pin it with a RED test first, fix it,
  GREEN. (If the divergence is real but the fix needs a file outside your
  footprint: BLOCKED-ON-FOOTPRINT with the full analysis.)
- **DORMANT-ENUMERATED** — a real divergence, unreachable on today's
  content: write the complete consumer/trigger enumeration (what you
  grepped, what you read, why each path cannot reach it). An entry whose
  mechanism is already labelled dormant still needs ITS OWN site verified
  under that mechanism's argument — inherited dormancy is what round 12
  overturned.
- **STALE-ALREADY-FIXED** — the sim already matches the C#: cite both sides
  and say what drifted (usually the record predates a fix).

Expect a mix: the one previously-worked slice of unlabelled entries ran
4 stale / 4 real.

## Footprint (yours alone this wave)

- Individual relic files `sts2_rl/relics/<name>.py` for relics in your
  manifest ONLY.
- New/changed tests under `test/`, named `test_r13_*` or added to existing
  relic test files.
- **NOT yours — `sts2_rl/relics/base.py` is owned by another lane this
  wave.** Also not yours: `hooks.py`, `combat.py`, `player.py`, `cmds.py`,
  `driver.py`, `run.py`, `powers.py`, `events/**`, `cards/**`,
  `monsters/**`, anything in `audit/**`. BLOCKED-ON-FOOTPRINT instead.
- Many relic "Rollup of guards" entries (`AfterObtained`, `AfterDeath`, ...)
  aggregate per-guard findings — the site verdict may differ per guard;
  propose NARROWING when only part of a rollup settles.

## Notes specific to this batch

- `relic/ruined_helmet/*` entries (if in your manifest): round 12's Task 18
  rebuilt RuinedHelmet as a real listener on the new
  TryModifyPowerAmountReceived/AfterModifyingPowerAmountReceived machinery —
  the entries likely predate that. Verify against today's code.
- `relic/lizard_tail/*`: the ShouldDie/ShouldDieLate collapse claim needs
  checking against the CURRENT death pipeline (round 12 touched
  killing-blow ordering; the record may be stale on both sides).
- Report path: `.superpowers/sdd/round13/R4-report.md`.
