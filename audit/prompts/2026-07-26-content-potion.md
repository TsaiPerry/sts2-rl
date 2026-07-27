# Stream 6 — content audits: potions  (NEW KIND, 2026-07-26)

This kind did not exist until 2026-07-26. Until then the shared contract said
**"Out of scope everywhere: potions (deferred by Perry)"**, so potions were not
an unaudited kind — they were an *excluded* one, which meant nothing counted
them and nothing reported them missing. Perry replaced that clause ("don't
ignore potions anymore") and `potion` is now an ordinary kind.

Confirm the wiring before you start:

```bash
cd C:/Users/Perry/Desktop/sts2-rl-audit && py audit/tools/harness.py roster potion
```

Must read `potion: 51 sim units, 0 unmatched`. If a unit is unmatched, the
override belongs in `audit/tools/name_overrides.json` (one is already there:
`potion/glowwater` → `GlowwaterPotion.cs`).

Setup:
```bash
cd C:/Users/Perry/Desktop/sts2-rl
git worktree add C:/Users/Perry/Desktop/sts2-rl-potion -b audit-potion audit-pipeline
```
Copy everything below the line into a fresh Claude Code session.

---

You are running the **potion content audits** of a source-to-sim audit
pipeline.

WORKTREE (all work here): `c:\Users\Perry\Desktop\sts2-rl-potion`  (branch `audit-potion`)
GAME SOURCE (READ-ONLY): `c:\Users\Perry\Desktop\Slay the Spire 2`

## Read first, in order

1. `audit/prompts/_shared-audit-contract.md` — **your binding contract**:
   operational rules, the eight verdict rules, file ownership, the per-unit
   procedure. Read §"Global scope" carefully: it is the clause that was just
   rewritten for you, and it explains what the old exclusion broke.
2. `audit/README.md` — the model, the verdict vocabulary, the rollup rule, and
   the staleness contract.
3. `audit/tools/PROMPT.md` — the v6 bug-class checklist (classes 1–29).
   **Read-only for you**; the relic stream owns it. Send lessons via your
   report.

## Your scope

`audit/records/potion/**` — **51 units**, `src/Core/Models/Potions` (129 C#
files, so expect ~78 unported: cross-character and cut content).
Roster: `py audit/tools/harness.py roster potion`.

You own that one directory and nothing else.

## Why this stream matters more than its unit count suggests

51 units is the smallest content tier, and it is **not** low-priority work,
because the exclusion means every other tier reasoned around potions rather
than about them. Two things are already known to be wrong because of it:

- **Ten entries across the `card` and `power` tiers waived real behaviour** on
  "the applier is a potion". Those are being re-verdicted separately; if you
  find one still standing, report it rather than editing it.
- **`damage_pipeline` N4 waived the two-phase `ShouldDie` ordering** because
  "FairyInABottle is out of scope". The potion is **ported**, at
  `sts2_rl/potions.py:1242`, with a real `should_die`, so the waiver was hiding
  a live gap. It is now queue entry 57 and it is *your* unit's mechanism.

Assume nothing about which potions are ported — grep. 51 are registered in
`ALL_POTIONS`, 48 are in the reward pool.

## Where the sim keeps potions (it is not one-file-per-unit)

**`sts2_rl/potions.py` is a single ~1300-line module holding all 51 classes.**
That is unlike relics/cards/events, which are one file per unit, and it has two
consequences you must plan for:

- Every record's `sim_source` is the same file, so **one edit to `potions.py`
  stales all 51 records at once**. Expect that; do not rehash to hide it.
- Your `file:line` citations all point into one big module, so they drift
  easily. `py audit/tools/citation_check.py` is the mechanical check — run it
  over your kind before every commit, not just at the end.

Potion *powers* (`flex_potion`, `speed_potion`, `shackling_potion`,
`gigantification`, `radiance`, `buffer`, `clarity`) live in `sts2_rl/powers.py`
and already have `power/*` records. **Do not re-verdict those** — cite them and
match, per binding rule 3.

## The mechanisms most likely to bite, from what the other tiers already found

1. **`PotionCmd.TryToProcure` silently drops the potion when the belt is full**
   — create-then-drop ordering, and the belt-full case is *reachable* because
   `relic/potion_belt` is a live gap (the sim's belt stays at 3 slots where the
   game grows to 5).
2. **Slot identity.** `UsePotion` replay commands name a **slot**, not a potion,
   and `sts2_rl/conformance/runner.py:625-631` diffs `floor_potions`
   slot-by-slot against the save oracle. `relic/alchemical_coffer` is already a
   gap for procuring into the wrong slots. Any potion that adds or removes
   belt entries is in this class.
3. **Named RNG streams.** `Rng.CombatPotionGeneration` and
   `PlayerRng.Rewards` are the two that matter. `relic/lost_coffer` G2 is
   already a grade-A gap for drawing potions off the legacy shared rng instead
   of `PlayerRng.Rewards`. A wrong stream is grade A — a replay stops
   converging.
4. **`RemoveBeforeUse`** — whether the potion leaves the belt before or after
   its effect resolves, which changes what a listener sees mid-effect.
5. **`BeforePotionUsed` / `AfterPotionUsed`** hook surfaces — check they exist
   in the sim at all before assuming a potion attaches to them.
6. The **automatic** potions (`automatic = True`, e.g. Fairy in a Bottle) are
   hook listeners while they merely *sit in the belt*. Their listener
   registration and ordering is the `damage_pipeline` N4 mechanism above.

## Procedure, per unit

```
py audit/tools/harness.py skeleton potion/<id>     # generates the record shell
```

Then: read the C# model **in full** → read the sim counterpart **in full** →
fill a verdict for every enumerated `public override`, plus a guard entry per
conditional the C# applies → check numeric constants against the
**non-ascension** branch → validate.

```
py audit/tools/harness.py validate audit/records/potion/<id>.json
py audit/tools/citation_check.py audit/records/potion
py audit/tools/backfill_sources.py --kind potion    # pin every file you cited
```

Before your final commit also run `py audit/tools/harness.py validate
--strict-inherited`. `list_overrides` follows `: BaseClass` now, so it surfaces
hooks a unit inherits rather than declares. That check found 16 under-audited
records in other tiers. Most inherited hooks are presentation and waive
legitimately, but **read each in the C# before waiving** — `InitialDescription`
carried real branching in the event tier.

Batch the work (the relic tier ran 258 units in 18 batches) and **commit in
stages** — several agents on this project have died at usage limits.

## Record liveness as data, not only as prose

A `gap` entry may carry `"live": true` or `"live": false` beside its `issue`,
and `audit_status.py` has a `live` column that counts it. The field is new and
**almost nothing populates it** — 386 gap entries across the project state no
liveness at all, which is why the column still reads near zero. Populate it on
every gap you file. Absence means *not stated*, not *dormant*.

## Add pins — this tier is the best place to start

**No content mechanism in this project has an acceptance test.** All 31
`strict=True` xfails in `test/test_hook_order.py` are seam-tier. A seam fix
proves itself by flipping a pin from xfail to failure; a content fix currently
cannot prove itself at all.

Potions are the best tier to break that, because the relic stream already filed
45 potion-mechanic gaps of which **27 are LIVE** — concrete, reachable
divergences with known witnesses, which is exactly what a pin needs.

For each LIVE gap you file where the divergence is expressible as a test, add a
`strict=True` xfail to `test/test_hook_order.py` whose `reason` names the sim
`file:line`, the C# `file:line`, live-or-dormant, and the observable effect.
Match the style already in that file, and follow its `fresh()` idiom. Then
**force-run it** (`py -m pytest test/test_hook_order.py -q --runxfail`) and
confirm it fails at the assertion its reason describes rather than erroring —
an xfail that fails for the wrong reason is worse than no pin, because it reads
as coverage. Confirm none XPASSes on a normal run.

You do not need a pin for every gap. Prioritise the grade-A ones (stream
desync) and anything with an executed witness already in hand.

## Rules that have cost this project real defects

- **`waiver` means genuinely out of scope** — multiplayer, presentation,
  ascension, another character. "No ported content triggers this" is a
  **dormant gap** and must name the concrete unported thing that would make it
  live. A potion is never a reason for a waiver any more.
- **LIVE requires proving BOTH sides reachable with ported content.** A false
  LIVE sends someone to fix correct code.
- **`deliberate-divergence` means an IDENTICAL observable.** If a player or a
  replay would see a difference, it is a gap. The RL observation encoder counts
  as an observer.
- **One mechanism, one verdict at every site, including across records.** This
  has been a *gap detector* three times on this project: two records disagreeing
  turned out to mean **neither** was right. Check your verdicts against the
  `power/*` potion-power records and against `seam/damage_pipeline`.
- **Every file you cite with a line number must be hashed by the record**
  (`backfill_sources.py` does this).
- If you cannot settle a question from your sources, that is **not a `gap`** —
  it is a note. Filing uncertainty as a gap was a real defect class in the relic
  tier and it was wrong 2 times out of 2.

## Never

- Modify `sts2_rl/`. Fixes are the gap-fix stream's job.
- Edit `audit/tools/harness.py`, `audit/tools/PROMPT.md`, `audit/GAP-QUEUE.md`,
  or another stream's records.
- Run `harness.py rehash` to make a number look better. A hash is a claim, not
  a decoration.
- Commit to `main`, or push.

## Report

`.superpowers/sdd/content-potion-report.md`: units audited, every gap with its
live/dormant determination, cross-record consistency notes, roster
mis-resolutions, lessons for `PROMPT.md`, and anything you could not settle.
