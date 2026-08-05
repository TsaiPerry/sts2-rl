# The source-to-sim audit

`sts2_rl/` is a re-architected Python reimplementation of the decompiled C#
*Slay the Spire 2*. This pipeline proves the two encode the same rules by
**comparing the codebases directly** — agents read both sides and record a
verdict per unit and per hook — instead of discovering divergences one at a
time through recorded-run convergence, which only ever exercises the
trajectories a recording happens to take.

The sim is a deliberate re-architecture, not a transpilation, so no mechanical
diff can settle faithfulness; the comparison is semantic and that is agent
work. What agents cannot be trusted with unaided is **completeness** — having
seen every unit, every hook, every guard — and **staleness** — knowing a
verdict still describes today's code. Those two parts are mechanical, and
they are what the tools in `tools/` do. They never judge faithfulness.

---

## Status

**Audited and merged here: all 6 engine seams and all 7 content tiers — 846
records, 0 invalid, 0 stale.** Every one has been through an independent review
pass and a fix pass. The relic tier (258 records) merged on 2026-07-26;
`monster` (109) and `potion` (51) merged on 2026-07-27, which completes the
kind list. **One unit still has no record: the sim-only `card/sweep`** (see
[Sim-only units](#sim-only-units)) — so a whole-project claim here now covers
all seven content kinds, and 1 of 847 units.

**`potion` is the tier to read if you want to know what an *exclusion* costs.**
It became a kind on 2026-07-26, when Perry replaced the shared contract's
blanket "potions are out of scope" clause; until then those 51 units were not
merely unaudited, they were *invisible*, and ten entries across the card and
power tiers had waived real behaviour on the clause.

**What each merge did to the tiers that were already "done" is the reason to
keep the caveat loud.** The relic merge unblocked `power/diamond_diadem` (whose
verdict had been waiting on a record that did not exist), corrected two stale
seam citations, flipped a seam `waiver` to a `gap` by disproving its "no ported
listener" claim, raised a seam guard from dormant to LIVE, and turned up
**`UnmovablePower` × `Entrench`** — a live gap that the `power` and `seam`
records had between them recorded as `faithful` and omitted from a census. The
potion merge did the same: it supplied the executed witness `seam/power_cmd` G6
records as missing (which moved `power/_should_allow_hitting` to 8 sites and
gave it its first pin), flipped `damage_pipeline/N4` from dormant to LIVE at its
second site, and turned up a **framework root with no seam** — see
[`PotionModel` has no seam](#potionmodel-has-no-seam). It also broke four tools,
each of which is fixed and pinned by a test; do not assume the next kind will
not.

> **2026-08-04 (stale sweep): every record is current again.** The
> 2026-08-04 sweep re-audited all 843 stale records (25 fast-rehash class-a
> whose cited spans were byte-identical, 818 full agent re-audits) — see
> [`stale-sweep/SWEEP-REPORT.md`](stale-sweep/SWEEP-REPORT.md) and the
> receipts beside it. 16 mechanisms closed (fixes had landed, records
> lagged), one LIVE gap surfaced and queued (`card/mad_science`
> `GainsBlock`). Stale 0, invalid 0 at sweep end — but the very next edit to
> `sts2_rl/` stales records again; that is the detector working.

Do not trust a status number written in prose, including in this file. Run it:

```
py audit/tools/audit_status.py      # coverage, staleness, gaps, per kind
py audit/tools/gap_queue.py counts  # gap entries, mechanisms, pins
```

Three things to expect from that output rather than be surprised by:

- **`stale` is nonzero whenever a hashed file moves underneath a record** — an
  uncommitted edit to `sts2_rl/` is the usual cause (editing `cmds.py` alone
  stales 146), but a *merge* does it too, and so does appending to a file a
  record cites. That is the detector working. See [Staleness](#staleness).
- **Most records roll up to `gap`**, because one gap anywhere in a record makes
  the record a gap. Gaps are **queued, not fixed** — a standing decision, not
  an oversight.
- **The `live` column is uneven, and the unevenness is about record vintage,
  not liveness.** It counts *records carrying at least one `live: true` entry*,
  not live entries. `monster` (45/45 gap entries) and `potion` (152/152) state
  the boolean on every gap and report 24 and 51; `relic`, `power` and `card`
  report 12, 5 and 1 because most of their entries state nothing either way.
  Absence means *not stated*, not dormant. `potion`'s 51 is one shared wrapper
  gap per record, not 51 distinct mechanisms.

> **Content gaps have their first acceptance tests, and only their first.** The
> potion tier added `TestPotionContentPins` to `test/test_hook_order.py` — four
> `strict=True` xfails anchored in `audit/records/potion/**`, the first
> content-anchored pins in the project — taking the file to 36. Every other
> content tier's fixes still cannot prove themselves except where they sit under
> an already-pinned seam mechanism (`damage_pipeline/G3`, `hook_dispatch/G3`,
> `hook_dispatch/G4`, `turn_structure/G13`). Adding pins as gaps are worked is
> the cheapest way to keep that from rotting, and `GAP-QUEUE.md`'s
> `relic/_combat_reset` (16 sites, one parametrised test) is the highest-value
> place to start. On the ownership snag: `test/test_hook_order.py` is
> seam-tier-owned and the potion stream's prompt overrode that explicitly,
> confining its pins to one named class so the widening is visible and movable.
> Either widen the contract the same way for the next tier or give content pins
> a sibling module the `gap_queue.py pins` scanner reads — but note the scanner
> now resolves a content-anchored pin, which it did not before 2026-07-27.

> **2026-08-03 (systems-tier wiring): three new content kinds and six new
> seams joined the roster, all unfilled.** `encounter` (85 units), `affliction`
> (7) and `character` (5) are now `CONTENT_KINDS` — 97 skeleton records exist
> under `audit/records/{encounter,affliction,character}/`, every verdict
> blank. `rng_streams`, `rewards`, `relic_pools`, `run_layer`, `rooms_and_map`
> and `potion_pipeline` are now wired seams — 6 skeleton records exist under
> `audit/records/seam/`, every `steps` list empty. That makes **10 content
> kinds and 12 seams** total: 7 kinds and 6 seams of them audited, same as
> before this task. A later campaign fills the 97 + 6 = 103 unfilled records;
> auditing them is not what this update did. See
> [Not audited, and why](#not-audited-and-why) for the subjects that were
> deliberately never wired to any kind or seam at all — a different thing
> from "wired but not yet filled."

---

## Layout

```
audit/
  README.md          you are here
  GAP-QUEUE.md       every gap in every audited kind, de-duplicated by
                     mechanism, ordered for work — the 7 audited kinds
                     (10 total; see Not audited, and why)
  records/
    seam/*.json      12 seam records — 6 audited (the evidence), 6 unfilled
                     skeletons (2026-08-03: rng_streams, rewards,
                     relic_pools, run_layer, rooms_and_map, potion_pipeline)
    power/ card/ event/ enchantment/
    relic/ monster/ potion/                             840 audited content records
    encounter/ affliction/ character/                   97 unfilled skeletons
                     (2026-08-03; a later campaign fills them)
  content/<kind>/    per-tier narration docs, written by that tier's stream:
                     potion/shared-mechanisms.md   the PotionModel.OnUseWrapper
                                                   pipeline, recorded once
                     monster/SHARED-FINDINGS.md    the monster tier's
                                                   cross-batch findings
                     power/gap-ledger.md           the power tier's ledger
  seams/*.md         12 seam docs — 6 ordering specs, 6 scope scaffolds only
                     (the same 6 unfilled seams as above)
  tools/             the harness, the status tool, the queue generator, probes
```

**Deliberately not here:** `test/test_hook_order.py`, `test/test_audit_harness.py`
and `test/test_audit_status.py` stay in `test/`. They are pytest suite members;
the 36 strict-xfail gap pins have to run with the normal suite so that fixing a
gap turns a *suite* red-to-green, not a side script.

**`test/` and `audit/tools/` are never hashed by a record**, even when a
verdict cites a pin or a probe with a line number. Both `citation_check.py` and
`backfill_sources.py` enforce that (`_NEVER_HASHED`), and they disagreed until
2026-07-27: backfill had pinned 28 such entries, so appending four pins to
`test/test_hook_order.py` staled nine card and relic records whose own cited
lines had not moved by a byte. A record still *says* it rests on the pin, and
the pin still has to pass — it is the hash that was wrong, because a pin file
changes whenever any other pin is added.

> **The 28 entries are still there, on purpose.** They live in 27 records owned
> by the `card` (18), `relic` (8) and `power` (1) streams, and stripping them is
> a change to someone else's records, so it is queued rather than taken:
>
> ```
> py audit/tools/backfill_sources.py --prune --no-add --kind card
> py audit/tools/backfill_sources.py --prune --no-add --kind relic
> py audit/tools/backfill_sources.py --prune --no-add --kind power
> ```
>
> Nine of them went stale when the potion tier appended its pins, and have been
> **re-audited and re-pinned** rather than left for the reader to trip over:
> `card/{apotheosis,entrench,primal_force}` and
> `relic/{horn_cleat,intimidating_helmet,iron_club,joss_paper,orichalcum,pen_nib}`.
> The re-audit is `py audit/tools/potion_probes.py pin-append` and it is three
> checks, not a hash rewrite: the file changed by **append only**; none of the
> 72 line citations across those records moved or changed content; and every
> test those records name still exists and is still a `strict=True` xfail. Only
> then `harness.py rehash`, which re-pinned exactly one entry per record — the
> `--dry-run` output is the receipt. The other 18 are not stale; they simply
> carry a hash that will stale them the next time any pin, tripwire test or
> probe is edited, which is what the prune above is for.

---

## Start here if you want to FIX something

**[`GAP-QUEUE.md`](GAP-QUEUE.md)** — the single actionable view. Ordered by
seed-convergence impact first, then blast radius, then fix cost. **Nothing in
it is labelled live any more; its Status section is where to start.** Entries
are addressed by mechanism id, not by number.

| grade | meaning |
|---|---|
| **A** | stream desync — changes an RNG draw count or the stream a draw comes from; a replay stops converging outright |
| **B** | state divergence — changes a damage/block/HP number, a hand, a pile, a deck entry; the next conformance assert fires |
| **C** | bookkeeping only — hook order or event identity, no numeric effect on ported content |

**The queue covers all 7 content kinds** as of 2026-07-27. It did not for a
day, and the way it failed is worth keeping: `gap_queue.py` carries its **own**
kind list, so when `potion` became a roster kind and 51 finished records landed,
`counts` printed `NOT AUDITED : potion` while `audit_status.py` — which derives
its kinds from the harness — reported the same records audited. Two tools, two
answers, and only the one nobody reads was right.
`test/test_audit_status.py::TestQueueGeneratorCoversEveryKind` now pins the two
lists together so the next kind cannot go missing the same way.

**Entries are not jobs, and the relic tier is the sharpest illustration yet.**
1612 gap entries across the 846 records de-duplicate to 856 mechanisms; the
relic tier alone contributes 620 entries that collapse to 404, with 16 recurring
families carrying 227 of them. The extreme case is `relic/_is_allowed` — **34
recorded sites and one missing base-class member.** The largest cross-kind
mechanism is `hook_dispatch/G4` at 36 sites across four kinds, and the potion
tier's `potion/_use_pipeline` and `potion/_effect_bracket` are 51 sites each —
one shared wrapper gap recorded once per unit, not 102 jobs.

Fixing one site of a mechanism generally clears all of them, so treating the
entries as independent overstates the work badly, and the overstatement is worse
in the content tiers than it was at the seam tier. Do not reuse the figures in
this paragraph — re-run
`py audit/tools/gap_queue.py counts`. The queue is organised by mechanism, and
each one carries a **fix recipe**: sites, impact grade, divergence
(sim `file:line` vs C# `file:line`), observable, dormancy trigger, pin, which
sim file changes and roughly how, and the blast radius.

**The pins are the acceptance test.** 36 `strict=True` xfails in
`test/test_hook_order.py` pin 32 mechanisms: 32 pins are seam-anchored and
**four are content-anchored**, the potion tier's `TestPotionContentPins` and the
first in the project. Strict means the test *fails* if it unexpectedly passes —
so when you fix the gap the pin flips from xfail to a failure, and you delete
the marker in the same commit. That is the fix's proof.
`py audit/tools/gap_queue.py pins` lists what each pin resolves to and
`unpinned` lists the mechanisms with no pin yet.

Two things a pin can do wrong, both of which happened and are now checked by
`test/test_audit_status.py::TestPinsResolveToAMechanism`:

- **anchor nothing.** Until 2026-07-27 `pins()` derived a mechanism only from
  the six seam names, so a content-anchored pin resolved to a mechanism
  literally called `None/G1` — counted as a pin, pinning nothing. `pins` now
  prints `UNRESOLVED` and exits 1 rather than swallowing it.
- **anchor the wrong thing, which is worse.** The potion AoE pin names
  `seam/power_cmd` G6, correctly and per rule 3 — but G6 is a *two-headed*
  guard ("No `CombatManager.IsEnding` / `CanReceivePowers` guard backstop") and
  the queue merges `power_cmd/G6` into `hook_dispatch/G8`, the IsEnding family.
  A LIVE, failing pin was therefore credited to a *dormant* 22-site mechanism
  while the LIVE 8-site one it actually proves read "unpinned". `_PIN_OVERRIDE`
  fixes that site explicitly; a pin credited to the wrong mechanism is worse
  than one credited to none, because it reports coverage in two places at once.

Fixing anything in `sts2_rl/` marks the records that hashed those files stale
— see [Staleness](#staleness). That is why fixes run as their own stream, after
the audit tiers, not beside them.

---

## Start here if you want to VERIFY a verdict

Two halves, and you generally want both:

- **`records/seam/*.json`** — the *evidence*. Per record: a `game_sources` and
  `sim_sources` list (path + sha256 of every file the verdicts rest on), an
  ordered `steps` list, a `guards` list, a rollup `verdict`, and an `audited`
  date. Each step and guard carries its own verdict plus `file:line` citations.
- **`seams/*.md`** — the *ordering spec* the record is a verdict on, written as
  prose: what the C# actually does, in order, and where the sim's shape differs.
  Also carries each seam's scope boundary against the other five, which is how
  a shared file like `Hook.cs` is split by method rather than audited six times.

### Verdict vocabulary

| verdict | means | requires |
|---|---|---|
| `faithful` | same observable behaviour | `maps_to` (which sim construct) |
| `waiver` | genuinely **out of scope** — multiplayer, presentation, ascension values, another character | a rationale |
| `deliberate-divergence` | different shape, **identical** observable outcome | a rationale |
| `gap` | a player or a replay would see a difference | an `issue` |

"No ported content triggers this" is **not** a waiver — it is a *dormant gap*,
and the record must name the concrete unported thing that would make it live.
Dormancy describes today's content, not the divergence's shape.

State that as **data**, not only as prose: a `gap` entry may carry
`"live": true` or `"live": false` beside its `issue`. The key is optional and
only legal on a gap, and `audit_status.py`'s `live` column counts the records
carrying at least one `live: true` entry. Absence means *not stated* — 64 of
the 258 power gap entries carried neither a `LIVE` nor a `dormant` token
anywhere, and nothing could tell them apart from the dormant ones.

### Sim-only units

A handful of sim units have no C# counterpart at all — `card/sweep` is
`sts2_rl/cards/sweep.py` with no `Sweep.cs`. The ordinary record shape requires
a `game_source`, so those units could not be recorded and read as permanently
unaudited. Generate them with `harness.py skeleton <unit> --sim-only`:

```json
{"unit": "card/sweep", "sim_only": true,
 "rationale": "why the unit has no C# counterpart",
 "sim_source": {"path": "…", "sha256": "…"}, "hooks": {}, "guards": [],
 "verdict": "waiver", "audited": "YYYY-MM-DD"}
```

"There is no C# side" is a **claim**, so the shape costs a `rationale`, a
verdict and a date like any other, and its `sim_source` is hashed and goes
stale normally. It counts as audited.

### Rollup rule

Precedence low→high is exactly the order above. A record's `verdict` must equal
`max(verdict for every step and guard)` — `harness.py validate` rejects a record
whose rollup is wrong, whose `waiver`/`deliberate-divergence` has no rationale,
whose `gap` has no issue, whose `faithful` has no `maps_to`, or which skipped a
`public override` the C# file declares.

The same mechanism gets **one** verdict at every site, including across records.
In the seam tier this worked as a gap *detector*: two records disagreed about
one mechanism, and settling the conflict showed neither was right.

### What counts as "a `public override` the C# file declares"

The enumeration follows the unit's **immediate base class**, which normally
lives in another file: `FlexPotionPower.cs` declares one member and inherits
seven from `TemporaryStrengthPower`, so the record owes eight verdicts, not one.
Following stops at the framework roots (`PowerModel`, `CardModel`, …) — that
layer is meant to be audited once by the seam tier rather than 840 times.

<a id="potionmodel-has-no-seam"></a>
> **`PotionModel` has no seam, and that hole is invisible to every tool here.**
> `MODEL_ROOT_CLASSES` is a *promise* that the seam tier covers each framework
> root. For `PotionModel` it does not: there are six seams and none of them is
> the potion pipeline, so `PotionModel.OnUseWrapper`
> (`src/Core/Models/PotionModel.cs:291-342`) — the entire use path for all 51
> potions, carrying `Hook.BeforePotionUsed` and `CheckForEmptyHand`, neither of
> which the sim dispatches — was verdicted nowhere. `validate` cannot notice,
> because a root class is exactly what it is told to stop at. The potion tier
> recorded it once in [`content/potion/shared-mechanisms.md`](content/potion/shared-mechanisms.md)
> and carries one rollup guard per record (`potion/_use_pipeline`, 51 sites).
> **The fix is a `potion_pipeline` seam, or extending `creature_card_cmds`.**
> Worth a check that every other root class names its covering seam.
>
> **Update, 2026-08-03:** the fix landed — `potion_pipeline` is now a wired
> seam (`SEAM_SOURCES["potion_pipeline"]`, claiming `PotionCmd.cs` and
> `PotionModel.cs`), and `MODEL_ROOT_CLASSES`'s comment on `PotionModel` now
> points at it instead of asserting the hole is open. `records/seam/
> potion_pipeline.json` is still an unfilled skeleton, though — wiring a seam
> is not auditing it, so treat this hole as **named**, not yet **closed**. See
> [Not audited, and why](#not-audited-and-why).

A hook key is matched on the identifier it starts with, so a record may annotate
one with provenance: `"Type (inherited, TemporaryStrengthPower.cs:32-42)"`.

Un-audited **inherited** overrides are a `WARN` from `validate`, not an error,
because the records written before base-class following existed could not see
them; `validate --strict-inherited` promotes them to errors and is what the
ledger should be held to once those records catch up. Un-audited **declared**
overrides are an error, as they always were.

---

## The tools

All run from the repo root. None of them judges faithfulness.

| command | what it does |
|---|---|
| `py audit/tools/audit_status.py` | the coverage / staleness / gap table above. `--strict` exits 1 on stale, gaps or unaudited; exit 2 means an invalid record |
| `py audit/tools/harness.py roster <kind>` | the work queue for one kind: every sim unit joined to its C# model file, plus unmatched units and unported C# files |
| `py audit/tools/harness.py skeleton <kind>/<id>` | writes `audit/records/<kind>/<id>.json` with every `public override` enumerated and verdicts blank. Refuses to overwrite. `--sim-only` for a unit with no C# counterpart |
| `py audit/tools/harness.py validate` | completeness + vocabulary check over every record. **Staleness is not validation's job** |
| `py audit/tools/harness.py rehash <unit>` | re-pins a record's source hashes after a re-audit. **Not a re-audit** — see [Staleness](#staleness) |
| `py audit/tools/gap_queue.py counts` | the gap numbers above, regenerated from every `records/<kind>/` — also `list`, `mechanisms`, `pins`, `unpinned`, `refs`, `json`. Reads the kinds in its own `CONTENT_KINDS`, and names any kind it is *not* reading rather than reporting it as 0 gaps |
| `py audit/tools/gap_queue.py cite-check` | every `file:line` in `GAP-QUEUE.md` resolves to a real line. **Exits non-zero on failure** — it did not until 2026-07-27, when `main()` stopped discarding the command's return value |
| `py audit/tools/gap_queue.py coverage` | every mechanism and every gap entry is findable in `GAP-QUEUE.md`. Same exit-code fix; before it, a regeneration verified by exit code could pass while the queue was two dozen mechanisms short |
| `py audit/tools/citation_check.py [path]` | every `file:line` in a *record* resolves to a real line, and every file cited with a line number is hashed by that record — binding rule 7's enforcer. Consults `extra_sources` as well as the singular pair. `--strict` also fails on rule-7 misses |
| `py audit/tools/backfill_sources.py` | writes the `extra_sources` entry for every third file a record cites with a line number, so rule 7 holds without hand-transcribing hashes. `--prune` removes entries under `_NEVER_HASHED` (`test/`, `audit/tools/`), `--no-add` keeps that surgical |
| `py audit/tools/dormancy_probes.py [probe]` | re-derives every "executed evidence" number `hook_dispatch` states about which classes implement which hook |
| `py audit/tools/state_machine_probes.py [probe]` | the same for `monster_state_machine` — the `AddBranch` overload census, the roll-distribution diff, the rule-7 citation sweep |
| `py audit/tools/relic_probes*.py`, `monster_probes*.py`, `potion_probes.py` | each tier's pool-wide sweeps and executed witnesses. `potion_probes.py` carries `sweep-attrs` / `-usage` / `-onuse` / `-overrides` / `-hooks` / `-vars` plus the executed gap witnesses `aoe-power`, `touch-of-insanity` and `pin-append` |
| `py -m pytest test/ -q -p audit.tools.stale_listener_plugin` | instruments every hook dispatch to test `hook_dispatch` gap G7's dormancy over the whole suite |

Two files in `tools/` are content, not code: **`PROMPT.md`** is the versioned
per-unit instruction sheet and bug-class checklist, and
**`name_overrides.json`** maps sim unit ids to C# filenames the naming
convention cannot derive. Both are owned by the relic stream alone.

`SEAM_SOURCES` in `harness.py` is the seam tier's source table: which C# and
sim files each seam's verdicts rest on. Its game paths are game-root-relative
and its sim paths are `sts2_rl/`-relative, so nothing in this folder moving can
change what gets hashed.

---

## Staleness

Every record stores the sha256 of every source file its verdicts rest on —
`game_sources` on the C# side, `sim_sources` on the sim side (content records
use the singular `game_source`/`sim_source`). Hashes are over the file text with
line endings normalised, so a checkout with different newlines does not lie.

**`extra_sources` pins everything else.** A content record's singular pair only
covers the unit's own two files, and content verdicts routinely cite others —
`PowerCmd.cs`, `cmds.py`, `combat.py`, `cards/base.py`. Those citations go in an
optional `extra_sources` list, one entry per file:

```json
"extra_sources": [
  {"path": "src/Core/Commands/PowerCmd.cs", "sha256": "…", "side": "game"},
  {"path": "sts2_rl/cmds.py",               "sha256": "…", "side": "sim"}
]
```

`side` is required and names the root the path resolves against — `game` for the
game source tree, `sim` for the repo root — because unlike the singular pair the
list is mixed and unordered. The key is optional: a record without it is still
valid, it just pins less. `audit_status.py` checks it for every record shape.

**Editing `sts2_rl/` marks every record that hashed the edited file stale.**
`audit_status.py` reports the count; `--strict` exits non-zero on it.

**A stale record needs a re-audit by an agent, not a regenerated hash.** That
distinction is the entire point. A hash is not the finding — it is the claim
"these verdicts were reached against exactly this text". Rewriting it to silence
the tool converts a durable audit into a decoration. Re-audits cost agent time,
not script time, and staleness is expected to be rare: the game source is
frozen, and sim files change only when a gap is fixed.

`harness.py rehash <unit|path>...` (also `--all`, `--kind <kind>`, `--dry-run`)
re-pins every hash a record carries — singular, plural and `extra_sources` — and
prints the warning above every time it runs. It is the **last** step of a
re-audit, after an agent has re-read the changed source and confirmed the
verdicts still hold; run on its own it is exactly the decoration described.

The rule that makes this bite: **every file a verdict cites with a line number
must be hashed by the record.** If a dormancy argument rests on
`Orichalcum.cs:44-56`, then a change to Orichalcum has to invalidate that
verdict — even though the seam being audited is `turn_structure` and the file is
a relic. `state_machine_probes.py sources-sweep` mechanises the check for one
record; it was a review finding on three consecutive seam tasks.

---

## Adding a stream

The folder is built for content streams to extend it concurrently without
colliding. A stream is one worktree, one branch, one directory.

1. Read **[`tools/PROMPT.md`](tools/PROMPT.md)** in full — the versioned
   per-unit instruction sheet and bug-class checklist. It is binding: the
   verdict rules there were each written after a real defect shipped.
2. Read the [Verdict vocabulary](#verdict-vocabulary) and
   [Rollup rule](#rollup-rule) sections above, plus the ownership matrix below.
3. Write records to **`records/<kind>/*.json`** — generate each with
   `harness.py skeleton`, never by hand. You own that one directory and nothing
   else.

Paths below are relative to `audit/` except the two that are not in it:

| Path | Owner |
|---|---|
| `records/relic/**` | relic stream (also the Tier 1 pilot) |
| `records/power/**` | power stream |
| `records/card/**` | card stream |
| `records/event/**`, `records/enchantment/**` | event+enchantment stream |
| `records/monster/**` | monster stream |
| `records/potion/**`, `content/potion/**`, `tools/potion_probes.py`, `TestPotionContentPins` in `test/test_hook_order.py` | potion stream (complete 2026-07-27; the pins are a prompt-authorised exception to the seam-tier rule below, confined to one named class) |
| `records/encounter/**`, `records/affliction/**`, `records/character/**` | unclaimed — wired 2026-08-03 (systems-tier task), 97 skeletons, no verdicts written; a later campaign audits them |
| `GAP-QUEUE.md` | gap-queue stream |
| `records/seam/**`, `seams/**`, `tools/harness.py`, `test/test_hook_order.py` | seam tier only — includes the 6 new seams (`rng_streams`, `rewards`, `relic_pools`, `run_layer`, `rooms_and_map`, `potion_pipeline`) wired 2026-08-03, unaudited |
| `sts2_rl/**` | gap-fix stream only, once authorised |

**Never edit `tools/harness.py`, and never edit another stream's records.** If
the roster mis-resolves one of your units, do not fix the harness — record the
need in your report. If `tools/name_overrides.json` can express it, that is the
relic stream's call to apply.

**The one shared-file rule:** `tools/PROMPT.md` and `tools/name_overrides.json`
are owned by the **relic stream alone**. Every other stream treats them as
read-only and sends lessons back via its report; the relic stream folds them in
and bumps the version header. That single exception is why the branches merge
trivially.

A new *kind* beyond the ten needs a `GAME_MODEL_DIRS` entry and a `_sim_units`
branch in `harness.py` — that is a seam-tier change, so propose it rather than
making it.

---

## Not audited, and why

**This is a reported fact, not a silent boundary.** The potion tier's own
history above is why: a bare "out of scope" line for potions hid ten waived
divergences across the card and power tiers for months, because an exclusion
is invisible to every tool in this pipeline — `audit_status` cannot report
it, `gap_queue` cannot count it, `validate` cannot reject a verdict leaning on
it. Every subject below is named here instead, with the reason a human
decided it does not get a `kind` or a `seam`, so the next reader finds a
sentence rather than rediscovers the absence.

### Whole subjects, never wired to a kind or a seam

Four of these came with a `.cs` count in the campaign's source prompt.
Measured 2026-08-03 against the live game tree with
`find <dir> -iname "*.cs" | wc -l` (not carried over from the prompt): all
four match exactly, so no correction is needed there. The rest had no stated
count; the numbers below are this pass's own measurement.

| subject | real `.cs` count | reason |
|---|---|---|
| `src/Core/Nodes/` | 691 (matches prompt) | UI layer — Godot scene tree, screens, widgets; no game-state the sim's headless run needs to reproduce |
| `src/Core/Multiplayer/` | 147 (matches prompt) | multiplayer-only; the sim is single-player throughout |
| `src/Core/Saves/` | 118 (matches prompt) | save-file read/write and schema; the sim has no persistence layer to compare against |
| `src/Core/Timeline/` | 74 (matches prompt) | replay/spectator timeline scrubbing, a presentation feature over already-simulated state |
| `src/Core/Localization/` (incl. `DynamicVars/`, `Fonts/`, `Formatters/`) | 58 | display text, fonts, locale formatters — no game-state reader |
| `src/Core/DevConsole/` (incl. `ConsoleCommands/`) | 52 | developer cheat/debug console commands, not shipping gameplay |
| `src/Core/Platform/` (incl. `Null/`, `Steam/`) | 28 | Steam/platform integration — achievements, leaderboards, cloud saves, window mode |
| `Achievements` (`src/Core/Achievements/`, `Models/Achievements/`, `Models/AchievementModel.cs`) | 13 | meta-progression tracking, no gameplay branch |
| `Badges` (`Models/Badges/`, `Models/BadgeModel.cs`) | 30 | end-of-run stat badges, computed after the run the sim already modelled |
| `Orbs` (`Entities/Orbs/`, `Models/Orbs/`, `Nodes/Orbs/`, `OrbCmd.cs`, `OrbModel.cs`, `Entities/Cards/OrbEvokeType.cs`, `Combat/History/Entries/OrbChanneledEntry.cs`) | 13 | Defect-only mechanic; Defect is one of the four unported characters below |
| the four unported characters — Silent, Regent, Necrobinder, Defect | 4 (`Models/Characters/{Silent,Regent,Necrobinder,Defect}.cs`) | `sts2_rl/characters.py`'s `_unported()` rows carry real, source-verified stats but empty card/relic/potion pools — the sim cannot run them. Ironclad-only scope, per `tools/PROMPT.md`'s "Characters other than Ironclad: waiver with rationale." Each character's own card/relic/power/potion files are not double-counted here — they already show up as `unported C# files` in that kind's own `harness.py roster` output |

### The Acts models — folded into a seam, not a kind

`src/Core/Models/Acts/*.cs` (the 5 per-act subclasses) has no `kind` of its
own: the sim has no act registry — no `ACTS`, `ALL_ACTS` or `class Act`
anywhere under `sts2_rl/` (verified 2026-08-03) — so there is nothing to
roster Acts *against*. They are not dropped, though: `seams/rooms_and_map.md`
claims `ActModel.cs` and all five `Models/Acts/*.cs` files and records the
act-level structure (encounter/event rosters, boss discovery order, per-act
map rolls) as part of that seam instead of leaving it invisible.

### `src/Core/Commands/*.cs` the seam wiring left unclaimed

Of the 20 files under `Commands/`, 12 were already claimed by an existing
seam (`creature_card_cmds`, `damage_pipeline`, `power_cmd`) and 6 went to
seams the 2026-08-03 task wired (`rooms_and_map`: `MapCmd.cs`; `relic_pools`:
`RelicCmd.cs`, `RelicSelectCmd.cs`; `rewards`: `RewardsCmd.cs`;
`potion_pipeline`: `PotionCmd.cs`). The remaining 8 are named here with the
reason each was read and declined, not silently skipped:

| file | reason |
|---|---|
| `Cmd.cs` | presentation — Godot scene-tree timer waits (`Wait`/`CustomScaledWait`) for animation pacing, no gameplay state |
| `ForgeCmd.cs` | Regent-only (one of the four unported characters above) |
| `OrbCmd.cs` | Defect-only (one of the four unported characters above) |
| `OstyCmd.cs` | Necrobinder-only (one of the four unported characters above) |
| `SfxCmd.cs` | presentation — sound effects |
| `TalkCmd.cs` | presentation — dialogue/portrait talk bubbles |
| `ThinkCmd.cs` | presentation — thought-bubble UI |
| `VfxCmd.cs` | presentation — visual effects |

### `src/Core/Runs/*.cs` the `run_layer` seam dropped

`run_layer` claims only `RunManager.cs`, `IRunState.cs` and
`ExtraRunFields.cs` from `Runs/`. `RunState.cs` belongs to `hook_dispatch`
(pre-existing), and `RelicGrabBag.cs` / `RunRngSet.cs` / the four
`CardCreationFlags.cs`, `CardCreationOptions.cs`, `CardCreationSource.cs`,
`CardRarityOddsType.cs` files were reassigned to `relic_pools` / `rng_streams`
/ `rewards` respectively, because each is ported inside that seam's own sim
file rather than in `run.py`. The other 12 of the 21 `Runs/*.cs` candidates,
each read in full before being dropped:

| file | reason |
|---|---|
| `GameMode.cs` | bare enum; Daily/Custom modes unsimulated |
| `GameModeExtension.cs` | achievement/epoch lock helper — unsimulated meta-progression |
| `ICardScope.cs` | pure interface; implementations live on `RunState.cs`/`CombatState.cs`, both claimed elsewhere |
| `IPlayerCollection.cs` | pure test-mocking interface, per its own doc comment |
| `MapLocation.cs` | serialization/equality value type for multiplayer map voting |
| `RunLocation.cs` | same, for multiplayer message routing |
| `NullRunState.cs` | null-object stub for menu/test contexts with no active run; RL is always in a run |
| `PlayerMapPointHistoryEntry.cs` | per-floor stat DTO, serialization only |
| `RunHistory.cs` | save-file schema, no gameplay branch |
| `RunHistoryPlayer.cs` | serialization-only DTO nested under `RunHistory` |
| `RunHistoryUtilities.cs` | builds the save-file history entry; real logic, but save/UI-only |
| `ScoreUtility.cs` | score/badge/leaderboard math — save/UI-only |

### Genuinely-unported content the roster work surfaced

Three `encounter` game files have no sim counterpart at all (down from an
earlier miscount of six that a first pass corrected — see
`py audit/tools/harness.py roster encounter`'s `unported` list):

- `TheArchitectEventEncounter.cs` — The Architect's victory event is
  unported; `run.py`'s `complete_run()` just sets `self.victory = True`
- `TunnelerNormal.cs` — the sim only ports the Weak Tunneler encounter
  (`encounter/tunneler` maps to `TunnelerWeak.cs`)
- `DeprecatedEncounter.cs` — literally `Deprecated`, framework leftover, not
  content

Three `character` game files are permanently unrostered, all declaring
`IsPlayable => false`:

- `DeprecatedCharacter.cs`, `RandomCharacter.cs` — framework plumbing the
  game itself marks non-playable
- `Deprived.cs` — a debug/mock character (`MockCardPool`, 1000 starting HP,
  100 max energy) used for game-side test tooling, not a sixth playable
  character

---

## Honest limits

- **Agent audits are fallible readers.** A wrong `faithful` is the residual
  risk the harness cannot catch — it enforces that a verdict exists and is
  well-formed, never that it is right. Mitigations: the versioned bug-class
  checklist in `tools/PROMPT.md`, order-pinning tests for everything in the
  seam tier, execution-verified fixes for every gap, and the five recorded
  conformance seeds remaining as a runtime regression net underneath.
- **A static audit proves the sim encodes the same rules; it cannot see
  emergent interactions** that two individually-faithful units produce jointly.
  Entries an agent flags as statically unsettleable are the natural target list
  for a game-in-the-loop fuzzer, which remains a compatible future add-on.
- **The decompiled source is itself the ground truth.** Where decompilation
  artifacts obscure semantics, a record states the ambiguity rather than
  guessing.
- **Re-audits cost agent time, not script time.** Staleness is bounded and
  visible rather than silent — but it is not free, and a stream that edits
  `sts2_rl/` while others audit it will invalidate records faster than they are
  written. That is why the gap-fix stream runs alone.
- **Do not trust a count stated in prose anywhere in this project, including
  this file.** Re-run the command next to it.
