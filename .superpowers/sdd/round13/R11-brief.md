# R11 — ledger backlog minis (5 items, disjoint small files)

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding).

Five deferred items from round 12's ledger. Each is small; each still gets
the full method (RED test before fix where a fix applies; C# citations).

## Item 1 — `cards/breakthrough.py`: uncounted 6th `card/_is_dead_early_return` site

`breakthrough.py` has a top-level `if ctx.player.is_dead: return` right
after its self-damage. Round 12's T27 deleted three structurally identical
guards (blood_wall, brand, hemokinesis) because the downstream commands
self-gate exactly as C# does — the guard is provably redundant. Re-derive
that reasoning for Breakthrough against `Breakthrough.cs` (find it; confirm
C# has no such early return and that every downstream command in the sim's
OnPlay self-gates on a dead player), then delete the guard and pin. If the
reasoning does NOT transfer (Breakthrough's tail differs), keep the guard
and report why — do not defer to this brief.

## Item 2 — `monsters/vantom.py`: DISMEMBER loses its status count

`Vantom.cs:119` carries `StatusIntent(3)`; the sim's DISMEMBER move drops
the count (a 4th site of the closed `monster/_intent_count_lost`
mechanism, found 2026-07-30 but never edited). Verify Vantom.cs:119, apply
`status_count=3` in `monsters/vantom.py`, pin the intent's count.

## Item 3 — `sts2_rl/selectors.py`: clamp `to_draw_top`'s cost ranking

`scripted_card_selector`'s Headbutt/Thinking-Ahead tie-break reads
`card.energy_cost` raw; since round 12 an unplayable card is canonically
`-1`, so it ranks below a genuinely-free (0-cost) card instead of tying at
0. Sim-only heuristic (no C# analogue). Clamp with `max(0, ...)` and add
the missing test: a curse/unplayable card on that selection path.

## Item 4 — `audit/tools/state_machine_probes.py`: stale zero-weight grep

The `zero_weight` probe greps for message text that round 12's T22 reworded
(the AddBranch weight/cooldown fixes changed the raise message in
`sts2_rl/state_machine.py`). Find the probe, find the current message text,
fix the grep, and PROVE the probe fires again (run it; show output). Do not
change state_machine.py itself.

## Item 5 — `creature_card_cmds/step19` closure re-derivation (REPORT ONLY)

Round 12's T19 review flagged: step19's closure claims the sim's `is_over`
equals C#'s `IsEnding`, but the sim's `is_over` (phase == COMBAT_OVER) and
its `is_ending` are genuinely distinct states. Re-derive: read the C# for
spec step 19 of the creature_card_cmds seam (read-only:
`audit/records/seam/creature_card_cmds.json`, key step 19, for what it
covers), determine which sim flag actually corresponds to C#'s gate at that
point, and whether the closure's equivalence claim holds, is harmlessly
wrong, or hides a real divergence (name the code path that would expose
it). DO NOT edit any record and DO NOT edit combat.py/cmds.py — analysis
and report only; the controller applies the record correction.

## Footprint (yours alone this wave)

`sts2_rl/cards/breakthrough.py`, `sts2_rl/monsters/vantom.py`,
`sts2_rl/selectors.py`, `audit/tools/state_machine_probes.py`, plus tests.
NOT yours: `combat.py`, `cmds.py`, `powers.py`, `hooks.py`, `driver.py`,
`run.py`, `state_machine.py`, `relics/**`, `events/**`, `audit/records/**`,
`audit/GAP-QUEUE.md`.

Report path: `.superpowers/sdd/round13/R11-report.md`.
