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

- Design: [`../docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md`](../docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md)
- Plan: [`../docs/superpowers/plans/2026-07-24-source-audit-pipeline.md`](../docs/superpowers/plans/2026-07-24-source-audit-pipeline.md)

---

## Status

**What is established: the engine-seam tier is complete — 6 of 6 seams
audited, 0 invalid.** That is the claim this folder supports with evidence.

**The content tier is in progress, and none of it is on this branch.** The
relic, power, card and event+enchantment streams are running in sibling
worktrees and have written several hundred records between them. So the
content rows below read 0 because nothing has been *merged here* — not
because the work has not started.

Do not trust a status number written in prose, including in this file. Run it:

```
py audit/tools/audit_status.py      # coverage, staleness, gaps, per kind
py audit/tools/gap_queue.py counts  # gap entries, mechanisms, pins
```

Two things to expect from that output rather than be surprised by:

- **`stale` is nonzero whenever `sts2_rl/` has uncommitted edits.** Records
  hash the sim files they audited, so any working-tree change to an audited
  file marks its records stale on sight. That is the detector working. See
  [Staleness](#staleness).
- **Every seam rolls up to `gap`**, because one gap anywhere in a record makes
  the record a gap. Gaps are **queued, not fixed** — a standing decision, not
  an oversight.

> **Merging a content stream needs one extra step.** Those streams were cut
> before this folder existed and write to the **pre-restructure** path
> `audits/<kind>/*.json`. Merging one drops its records there, beside the empty
> `audit/records/<kind>/` here, and the status table will keep reading 0 until
> they are moved. See *Merge order* in
> [`prompts/README-parallel-streams.md`](prompts/README-parallel-streams.md)
> for the one-line repath.

---

## Layout

```
audit/
  README.md          you are here
  GAP-QUEUE.md       every gap, de-duplicated by mechanism, ordered for work
  records/
    seam/*.json      the 6 engine-seam audit records — the evidence
    relic/ power/ card/ event/ enchantment/ monster/    empty; one per stream
  seams/*.md         the 6 seam narration docs — the ordering specs
  tools/             the harness, the status tool, the queue generator, probes
  prompts/           the shared contract + the 8 stream prompts
```

**Deliberately not here:** `test/test_hook_order.py`, `test/test_audit_harness.py`
and `test/test_audit_status.py` stay in `test/`. They are pytest suite members;
the 32 strict-xfail gap pins have to run with the normal suite so that fixing a
gap turns a *suite* red-to-green, not a side script.

---

## Start here if you want to FIX something

**[`GAP-QUEUE.md`](GAP-QUEUE.md)** — the single actionable view. Ordered by
seed-convergence impact first, then blast radius, then fix cost; live above
dormant.

| grade | meaning |
|---|---|
| **A** | stream desync — changes an RNG draw count or the stream a draw comes from; a replay stops converging outright |
| **B** | state divergence — changes a damage/block/HP number, a hand, a pile, a deck entry; the next conformance assert fires |
| **C** | bookkeeping only — hook order or event identity, no numeric effect on ported content |

**Entries are not jobs.** At the seam tier, 224 entries de-duplicate to 90
mechanisms. The largest one — the missing `IsEnding`/`IsOverOrEnding` dispatch
gate — is recorded at 22 sites across three records; the missing
`AfterModifyingXxx(modifiers)` companion events at 12. Fixing one site of a
mechanism generally clears all of them, so treating the entries as independent
overstates the work by roughly 2.5x. Expect the same ratio to hold as content
records land and the queue grows — re-run `py audit/tools/gap_queue.py counts`
rather than reusing the figures above. The queue is organised by mechanism, and
each one carries a **fix recipe**: sites, impact grade, divergence
(sim `file:line` vs C# `file:line`), observable, dormancy trigger, pin, which
sim file changes and roughly how, and the blast radius.

**The pins are the acceptance test.** A third of the seam-tier mechanisms are
pinned by a `strict=True` xfail in `test/test_hook_order.py`. Strict means the
test *fails* if it unexpectedly passes — so when you fix the gap the pin flips
from xfail to a failure, and you delete the marker in the same commit. That is
the fix's proof. `py audit/tools/gap_queue.py pins` lists what is pinned and
`unpinned` lists the mechanisms with no pin yet.

Fixing anything in `sts2_rl/` marks the records that hashed those files stale
— see [Staleness](#staleness). That is why fixes run as their own stream
(`prompts/2026-07-26-gap-fixes.md`) after the audit tiers, not beside them.

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
layer is audited once by the seam tier, not 422 times.

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
| `py audit/tools/gap_queue.py counts` | the gap numbers above, regenerated from the records — also `list`, `mechanisms`, `pins`, `unpinned`, `refs`, `json` |
| `py audit/tools/gap_queue.py cite-check` | every `file:line` in `GAP-QUEUE.md` resolves to a real line |
| `py audit/tools/gap_queue.py coverage` | every mechanism and every gap entry is findable in `GAP-QUEUE.md` |
| `py audit/tools/dormancy_probes.py [probe]` | re-derives every "executed evidence" number `hook_dispatch` states about which classes implement which hook |
| `py audit/tools/state_machine_probes.py [probe]` | the same for `monster_state_machine` — the `AddBranch` overload census, the roll-distribution diff, the rule-7 citation sweep |
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

The folder is built for five content streams to extend it concurrently without
colliding. A stream is one worktree, one branch, one directory.

1. Read **[`prompts/_shared-audit-contract.md`](prompts/_shared-audit-contract.md)**
   in full. It is binding: operational rules, the eight verdict rules (each
   written after a real defect shipped), the ownership matrix, and the per-unit
   procedure.
2. Take your stream's prompt from **[`prompts/`](prompts/)**. The dependency
   graph, branch names and worktree setup are in
   **[`prompts/README-parallel-streams.md`](prompts/README-parallel-streams.md)**.
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
| `GAP-QUEUE.md` | gap-queue stream |
| `records/seam/**`, `seams/**`, `tools/harness.py`, `test/test_hook_order.py` | seam tier only |
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

A new *kind* beyond the six needs a `GAME_MODEL_DIRS` entry and a `_sim_units`
branch in `harness.py` — that is a seam-tier change, so propose it rather than
making it.

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
