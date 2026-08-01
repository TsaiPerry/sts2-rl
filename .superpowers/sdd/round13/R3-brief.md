# R3 — settle unlabelled batch power-1 (12 entries, 10 records)

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding), then your
manifest: `.superpowers/sdd/unlabelled-r13/power-1-brief.md`.

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

- `sts2_rl/powers.py` and any `sts2_rl/potions.py`/power-adjacent content
  file your entries' fixes live in.
- New/changed tests under `test/`, named `test_r13_*` or added to existing
  power test files you already own by editing.
- NOT yours (report BLOCKED-ON-FOOTPRINT instead of editing): `hooks.py`,
  `combat.py`, `player.py`, `cmds.py`, `driver.py`, `run.py`, `relics/**`,
  `events/**`, `cards/**`, `monsters/**`, anything in `audit/**`.
- Your manifest's record files are listed in the manifest header — they are
  the entries you settle, but remember: you never edit records, you propose.

## Notes specific to this batch

- Entries under an already-labelled mechanism (e.g. `power/_death_prevention_branch`,
  `power_cmd/G5`, `damage_pipeline/G3`) get a SITE verdict: does this site's
  behavior match the mechanism's recorded story, and is the site itself
  reachable? Cross-reference the seam record's text (read-only) if needed.
- `power/artifact/AfterModifyingPowerAmountReceived` (if in your manifest):
  round 12's Task 18 rebuilt Artifact/RuinedHelmet as real listeners on the
  new AfterModifyingPowerAmount* machinery — the entry likely predates that.
  Verify against today's code, not the record's description.
- Report path: `.superpowers/sdd/round13/R3-report.md`.
