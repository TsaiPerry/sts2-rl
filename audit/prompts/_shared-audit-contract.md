# Shared audit contract

Binding for every parallel audit session. Your stream prompt tells you what
to audit; this file tells you how, and what you may touch. Read it in full
before your first unit.

Everything the pipeline owns lives under `audit/`. `audit/README.md` is the
map: current status, the tools and their commands, how staleness works, and
how a new stream plugs in. Read it once if you have not seen this folder
before.

## Operational rules

- Run every command in the FOREGROUND with a generous timeout (600000 ms).
  Do NOT start background jobs or monitors; they cannot notify you and you
  will stall.
- **NEVER modify engine code under `sts2_rl/`.** Audits record findings; they
  do not fix them. Audits add no executable code, so if the test suite changes
  state you made an accidental edit — revert it.
- The game source at `c:\Users\Perry\Desktop\Slay the Spire 2` is READ-ONLY.
- Commit only on your own branch. **Never push. Never touch `main`.**
- Commit each batch the moment it validates. Sessions here have repeatedly
  died at usage limits; committed files and written reports are what survive.
  Do not polish before committing.
- If a number you record comes from a script, commit the script under
  `audit/tools/` (see `audit/tools/dormancy_probes.py` for the pattern) so it
  is reproducible. Otherwise use the scratchpad.

## File ownership — the concurrency contract

Several sessions run against sibling worktrees of one repo and merge later.
Merges stay trivial only while ownership holds.

**Nobody but the seam session touches:**
`audit/tools/harness.py` · `audit/records/seam/**` · `audit/seams/**` ·
`.superpowers/sdd/progress.md`

`test/test_hook_order.py` is seam-owned **for everything except gap pins**. A
content stream may add `strict=True` xfails there only when its own stream
prompt says so, and only inside one clearly-named class of its own
(`TestPotionContentPins` is the precedent, 2026-07-27) so the widening stays
visible and the block stays movable. Anything else in that file is still the
seam session's.

**One owner each:**

| Path | Owner |
|---|---|
| `audit/records/relic/**` | relic stream |
| `audit/records/power/**` | power stream |
| `audit/records/card/**` | card stream |
| `audit/records/event/**`, `audit/records/enchantment/**` | event+enchantment stream |
| `audit/records/monster/**` | monster stream |
| `audit/records/potion/**` | potion stream |
| `audit/content/<kind>/**` | that kind's stream (narration docs, if you write any — never `audit/content/` directly) |
| `audit/tools/PROMPT.md`, `audit/tools/name_overrides.json` | **relic stream only** |
| `audit/GAP-QUEUE.md` | gap-queue stream |
| `sts2_rl/**` | gap-fix stream only, and only once authorised |

If you need a change in a file you do not own — e.g. the roster mis-resolves
a unit and you want `harness.py` fixed — **do not make it.** Record the need
in your report. If `audit/tools/name_overrides.json` can express it and you
are not the relic stream, report it for the relic stream to apply.

Every stream except the relic stream: **treat `audit/tools/PROMPT.md` as
read-only.** Report lessons; the relic stream folds them in and bumps the
version header.

## Verdict vocabulary

Precedence low→high: `faithful`, `waiver`, `deliberate-divergence`, `gap`.
Unit rollup = `max(verdicts, key=VERDICTS.index)`. Non-`faithful` verdicts
MUST carry rationale/issue text or validation fails.

## THE EIGHT BINDING VERDICT RULES

Each was written after a real defect shipped in the engine-seam tier and a
review caught it. Expect to make the same mistakes.

1. **`waiver` means genuinely OUT OF SCOPE and nothing else** — multiplayer,
   presentation/animation/SFX, ascension values, other characters. "No ported
   content triggers this" is a **dormant `gap`**. "The C# side is unported" is
   a **dormant `gap`**. Dormancy describes today's content, not the
   divergence's shape. One seam shipped five waivers that were really gaps,
   two resting on FALSE "no ported caller" claims.
2. **`deliberate-divergence` requires the SAME observable outcome.** If a
   player or a replay would see a difference, it is a `gap`.
3. **The same mechanism gets ONE verdict at every site — including across
   records.** In the seam tier this worked as a gap *detector*: two records
   disagreed about one mechanism, and settling the conflict showed neither was
   right — a live gap was hiding in the disagreement. If a prior record
   disagrees with a verdict you reach, treat it as a signal. Report it; do not
   edit records you do not own.
4. **A guard/rollup entry carries `max(verdict)` of what it aggregates.**
5. **Never justify `faithful` with an unreachability claim you have not
   EXECUTED.** Three such claims were false and two turned out to be their
   seam's live gaps. If a rationale depends on a value or state never
   occurring, write a script, RUN it, and record the observed output.
6. **Claiming a gap is LIVE requires proving BOTH sides reachable with ported
   content** — the relic obtainable, the card in the Ironclad pool, the code
   path actually taken. One audit shipped a "live" gap whose trigger (a player
   holding Artifact) exists nowhere in the game. If you cannot prove it, label
   it dormant and NAME the concrete unported thing that would make it live.
7. **Every file you cite with a line number must be hashed by the record.**
   This was a review finding on three consecutive tasks. Content records hash
   the unit's own two files; if a rationale leans on a third file, say so
   explicitly in the rationale so the staleness blind spot is visible.
8. **Verify every test path you cite by grepping for it.** Two successive
   agents invented a test class that does not exist.

## Global scope

The sim is **Ironclad-only**. Findings about mechanics unreachable in that
scope are `waiver` with the reason named — never silently skipped.

**Out of scope everywhere:** out-of-combat UI-only behavior, multiplayer-only
paths, ascension values (the sim uses non-ascension numbers by convention).

**Potions are IN SCOPE (changed 2026-07-26 by Perry: "don't ignore potions
anymore").** The old clause read "Out of scope everywhere: potions (deferred by
Perry)" and it has been deleted, not narrowed. `potion` is now an ordinary
audit kind — 51 sim units, `audit/records/potion/`, in
`harness.py roster potion` — and as of **2026-07-27 it is audited**, like
`monster`: 51 records, 152 gap entries, 83 live. Out-of-scope was a claim that
hid things; unaudited was a fact the tools report; audited is a set of records
you must now **match rather than re-derive** under binding rule 3.

Two consequences, both binding:

- **A potion may never be the reason for a `waiver` again.** "The applier is a
  potion" and "potions have no audit tier" are now dormancy arguments at best,
  and usually not even that, because the potion is probably ported: the sim has
  51 potion classes, 48 of them in the reward pool, and the potion belt is
  asserted slot-by-slot by the conformance runner. If a divergence is real and
  a potion triggers it, that is a **gap** — `live` if the potion is ported.
- **The clause did real damage while it stood, in both directions.** Ten
  entries across the `card` and `power` tiers waived genuine behaviour on it
  while the `relic` tier filed 45 potion-mechanic gaps, 27 of them LIVE — one
  mechanism, two answers, which is a binding-rule-3 break the contract itself
  caused. It also protected a false claim: `damage_pipeline` N4 waived the
  two-phase `ShouldDie` ordering because "FairyInABottle is out of scope", and
  the potion turned out to be ported at `sts2_rl/potions.py:1242` with a real
  `should_die`. Re-read any verdict that cites the old clause. **Four relic
  records still assert the deleted clause as a live premise** — `alchemical_
  coffer`, `lost_coffer`, `phial_holster`, `potion_belt` each say "POTION IS NOT
  AN AUDITED KIND — there is no `potion` roster kind and no
  `audit/records/potion/`". Both halves are false; that is the relic stream's
  to correct.

**The `live` boolean is now the expected form on every gap entry.** `monster`
(45/45) and `potion` (152/152) state it on every one; the older tiers leave most
unstated, and `audit_status.py`'s `live` column counts records, not entries.
Absence means *not stated*, never *dormant*.

Numeric constants are checked against the **non-ascension** branch of
`AscensionHelper.GetValueIfAscension(...)`.

## Per-unit procedure

```
py audit/tools/harness.py skeleton <kind>/<id>    # generates the record shell
```

Then: read the C# model **in full** → read the sim counterpart **in full** →
fill a verdict for every enumerated hook, plus a guard entry per conditional
the C# applies → check numeric constants → validate.

Follow `audit/tools/PROMPT.md`'s bug-class checklist on every unit.

**Batch size 15.** After each batch:

```
py audit/tools/harness.py validate          # 0 invalid
py audit/tools/audit_status.py --kind <kind>
py -m pytest test/ -q                       # must be unchanged; audits add no code
git add audit/records/<kind> && git commit         # name the units and the gap count
```

## Depth calibration

Read `audit/seams/hook_dispatch.md` once before starting. You are not
redoing seam work — it calibrates the expected depth, the `file:line`
citation discipline, and the rationale style. A verdict with no citation and
no executed evidence is not an audit finding.
