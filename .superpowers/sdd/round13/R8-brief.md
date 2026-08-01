# R8 — settle unlabelled batch relic-2 (14 entries, 13 records)

Identical protocol to R4 (`.superpowers/sdd/round13/R4-brief.md` — read it
in full and follow it; PROTOCOL.md is binding), with these substitutions:

- Your manifest: `.superpowers/sdd/unlabelled-r13/relic-2-brief.md`.
- Your report path: `.superpowers/sdd/round13/R8-report.md`.
- You run in a LATER wave than R4: R1's listener-registry rework landed in
  `hooks.py`/`relics/base.py` (wave 1), and R5's Play pile may have landed
  in `player.py`/`combat.py`/`cmds.py`. Any entry whose analysis touches
  listener order, `HasBeenRemovedFromState`/melted filtering, pile
  membership or `all_cards` must be re-derived against the CURRENT tree,
  not the record's citations. Check `.superpowers/sdd/round13/R1-report.md`
  / `R5-report.md` if a claim seems off.
- `relics/base.py` remains NOT yours (engine lanes own it): propose exact
  diffs as BLOCKED-ON-FOOTPRINT if a fix needs it.

Footprint: individual `sts2_rl/relics/<name>.py` files for relics in your
manifest ONLY, plus tests. NOT yours: `relics/base.py`, `hooks.py`,
`combat.py`, `player.py`, `cmds.py`, `driver.py`, `run.py`, `powers.py`,
`events/**`, `cards/**`, `monsters/**`, `audit/**`.
