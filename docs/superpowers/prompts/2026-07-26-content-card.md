# Stream 3 — content audits: cards

Setup:
```bash
cd /c/Users/Perry/Desktop/sts2-rl
git worktree add /c/Users/Perry/Desktop/sts2-rl-card -b audit-card audit-pipeline
```
Copy everything below the line into a fresh Claude Code session.

---

You are running the **card content audits** of a source-to-sim audit
pipeline, concurrently with four other content streams and the engine-seam
tier.

WORKTREE (all work here): `c:\Users\Perry\Desktop\sts2-rl-card`  (branch `audit-card`)
GAME SOURCE (READ-ONLY): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Read first, in order

1. `docs/superpowers/prompts/_shared-audit-contract.md` — **your binding
   contract**: operational rules, the eight verdict rules, file ownership,
   the per-unit procedure. Follow it exactly.
2. `tools/audit/PROMPT.md` — the audit instruction sheet and bug-class
   checklist. **Read-only for you**; the relic stream owns it. Send it
   lessons via your report.
3. `docs/audit/seams/creature_card_cmds.md` — the completed card/pile command
   seam audit. Read its gap list first so you record card-level findings
   rather than re-reporting machinery ones.

## Your scope

`audits/card/**` — **203 units**, the largest content pool. Roster:
`py tools/audit/harness.py roster card`.

## What makes cards different

Per the plan, cards are mostly numbers and keywords — the cheapest per-unit
audits, and the stream most likely to finish. Two card-specific demands:

- **Audit the upgrade (`+`) values too.** The sim models upgrades inside one
  class; C# may use fields, a separate branch, or a distinct model. A card
  whose base numbers match and whose upgraded numbers do not is a gap, and
  the record must state which of the two you checked.
- **Keyword sets are part of the comparison**: Exhaust, Ethereal, Innate,
  Retain, Unplayable, and the ValueProps a card's effects carry
  (`Move`, `Unpowered`, `Unblockable`). The seam tier found real bugs turning
  on exactly these flags.

## Seam findings that bear on card units

Read these before verdicting; each is already recorded, so per rule 3 do not
re-verdict the machinery — but flag card units that depend on them:

- **`creature_card_cmds` G1 (LIVE)** — `BlockCmd.apply` gates the whole
  block-modifier dispatch on `is_powered_attack`, while C# calls every
  listener and lets each self-gate. Entrench gains block with
  `MOVE|UNPOWERED`, so the real game doubles it under Vambrace and the sim
  does not. **Any card you audit that gains block with `Unpowered` is in this
  blast radius** — list them.
- **`creature_card_cmds` G3 (LIVE)** — deck-pile transforms bypass the
  deck-entry hooks, so the egg relics never upgrade a transformed card.
  Relevant to every card reachable via transform.
- **`hook_dispatch` G4 (LIVE)** — the `CardPlay` bracket fires **per replay
  iteration** in C# (`CardModel.cs:1904` loop contains both
  `Hook.BeforeCardPlayed:1929` and `AfterCardPlayed:1959`) but **once per
  play** in the sim. Any card with a play-count > 1 is affected; Throwing Axe
  + Pen Nib gives sim 1 attack, game 2.
- **`creature_card_cmds` step 52 (LIVE)** — `Downgrade` skips the
  `Enchantment.ModifyCard()` re-apply, so a Souls-enchanted Discovery regains
  Exhaust after upgrade+downgrade.
- The Play-limbo rule: a card mid-`OnPlay` sits in `PileType.Play`, so a
  reshuffle it triggers excludes it. Already pinned; check ports respect it.

## Batching

15 units per batch. Validate, status-check, run the suite, and commit each
batch before starting the next — see the shared contract for the exact
commands.

The relic stream is running the Tier 1 pilot and will harden `PROMPT.md` from
it. Either wait for that to land and branch after it, or start now and
**re-read `tools/audit/PROMPT.md` at each batch boundary**.

Because this pool is the largest and cheapest per unit, it is also the best
source of throughput data. Report your per-unit cost after the **first two**
batches, not only at the end.

## Report

Write `.superpowers/sdd/content-card-report.md`. Include: units audited,
every gap with its live/dormant determination and reachability evidence, the
list of cards that gain block with `Unpowered` (G1's blast radius), the list
of cards with a play-count > 1 (G4's blast radius), any card whose upgraded
values diverge while its base values match, lessons for `PROMPT.md` for the
relic stream, any unit the roster mis-resolved, any cross-record disagreement
under rule 3, and cost data (wall time and tokens per unit, gap rate, how many
units needed execution to settle).
