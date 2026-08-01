# R7 — settle unlabelled batch power-2 (11 entries, 10 records)

Identical protocol to R3 (`.superpowers/sdd/round13/R3-brief.md` — read it
in full and follow it; PROTOCOL.md is binding), with these substitutions:

- Your manifest: `.superpowers/sdd/unlabelled-r13/power-2-brief.md`.
- Your report path: `.superpowers/sdd/round13/R7-report.md`.
- You run in a LATER wave than R3: engine lanes have since reworked
  `hooks.py` (listener registry, R1), `combat.py`/`player.py`/`cmds.py`
  (Play pile, R5) and possibly the attack-results payload (R9). Any
  entry whose analysis touches listener order, pile membership,
  `all_cards`, or attack results must be re-derived against the CURRENT
  tree, not the record's citations. Check
  `.superpowers/sdd/round13/R1-report.md` / `R5-report.md` / `R9-report.md`
  if a claim seems off.
- `power/ringing/ShouldPlay` (if in your manifest): its sibling entry's
  pile-limbo analysis may have been settled by R5's Play pile — verify
  against current `player.py::all_cards` before inheriting any claim.

Footprint: `sts2_rl/powers.py` + power-adjacent content files your
entries' fixes live in, plus tests. NOT yours: `hooks.py`, `combat.py`,
`player.py`, `cmds.py`, `driver.py`, `run.py`, `relics/**`, `events/**`,
`cards/**`, `monsters/**`, `audit/**` — BLOCKED-ON-FOOTPRINT instead.
