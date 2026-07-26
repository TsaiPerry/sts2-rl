# Stream 4 — content audits: events + enchantments

Setup:
```bash
cd /c/Users/Perry/Desktop/sts2-rl
git worktree add /c/Users/Perry/Desktop/sts2-rl-event -b audit-event audit-pipeline
```
Copy everything below the line into a fresh Claude Code session.

---

You are running the **event and enchantment content audits** of a
source-to-sim audit pipeline, concurrently with three other content streams
and the engine-seam tier.

WORKTREE (all work here): `c:\Users\Perry\Desktop\sts2-rl-event`  (branch `audit-event`)
GAME SOURCE (READ-ONLY): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Read first, in order

1. `docs/superpowers/prompts/_shared-audit-contract.md` — **your binding
   contract**: operational rules, the eight verdict rules, file ownership,
   the per-unit procedure. Follow it exactly.
2. `tools/audit/PROMPT.md` — the audit instruction sheet and bug-class
   checklist. **Read-only for you**; the relic stream owns it. Send it
   lessons via your report.

## Your scope

Two kinds, **82 units total** — the smallest content stream, so you are also
the most likely to finish and free up capacity.

- `audits/event/**` — 65 units. Roster: `py tools/audit/harness.py roster event`
- `audits/enchantment/**` — 17 units. Roster: `py tools/audit/harness.py roster enchantment`

## Scope boundary for events

**Combat-facing effects only.** Pure-UI event text is out of audit scope and
gets a `waiver` — that is a genuine out-of-scope waiver under rule 1, and one
of the few places the word is correct.

But be strict about the line. An event that *heals*, *changes max HP*, *adds
or transforms a card*, *grants a relic*, *starts a combat*, or *awards gold*
is doing modelled work, and every one of those verbs has been a source of
real divergence. Only the presentation layer is waivable.

Two live seam findings sit squarely in event territory:

- **`turn_structure` step 38a (LIVE)** — `events/dense_vegetation.py:67`
  calls a bare `run.heal()`, skipping the `Hook.AfterRestSiteHeal` +
  `ModifyRestSiteHealRewards` that `HealRestSiteOption.ExecuteRestSiteHeal`
  runs, so Stone Humidifier is ignored (80→80 / 40→64 vs the correct
  80→85 / 40→69). **Check every event that heals for the same shortcut.**
- **`creature_card_cmds` G3 (LIVE)** — deck-pile transforms bypass the
  deck-entry hooks, so the egg relics never upgrade a transformed card.
  **Check every event that transforms or adds a card.**

Per rule 3 do not re-verdict those machinery findings; do record which of
your units are in their blast radius.

Also relevant: each act's Neow/Orobas/Tanx node bumps `eventsVisited`, so the
first `?` node serves `events[1]`. If a unit's audit turns on event ordering,
say so explicitly.

## Scope note for enchantments

Enchantments modify cards. The seam tier found one live consequence already —
`Downgrade` skips the `Enchantment.ModifyCard()` re-apply, so a
Souls-enchanted Discovery regains Exhaust after upgrade+downgrade
(`creature_card_cmds` step 52). Check whether each enchantment's port
re-applies correctly across upgrade, downgrade, transform and copy.

Note the sts2 egg relics are **not** sts1's: Toxic = Skill, Frozen = Power,
Molten = Attack, and they upgrade reward offers, shop stock **and** deck adds.

## Batching

15 units per batch. Validate, status-check, run the suite, and commit each
batch before starting the next — see the shared contract for the exact
commands. Do enchantments first: 17 units is barely more than one batch, and
finishing a whole kind gives the status report its first `unaudited 0` row.

The relic stream is running the Tier 1 pilot and will harden `PROMPT.md` from
it. Either wait for that to land and branch after it, or start now and
**re-read `tools/audit/PROMPT.md` at each batch boundary**.

## Report

Write `.superpowers/sdd/content-event-enchantment-report.md`. Include: units
audited per kind, every gap with its live/dormant determination and
reachability evidence, the list of events that heal (step 38a's blast radius)
and events that transform or add cards (G3's blast radius), every waiver with
the specific reason it is presentation-only rather than unimplemented,
lessons for `PROMPT.md` for the relic stream, any unit the roster
mis-resolved, any cross-record disagreement under rule 3, and cost data.
