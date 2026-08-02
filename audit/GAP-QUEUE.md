# Gap queue — every open gap, aggregated

Every `"verdict": "gap"` entry in `audit/records/**`, de-duplicated **by
mechanism** and ordered for work. Generated from the records, not transcribed.

**This file holds current state and standing lessons only.** Which round closed
what, and when, is in the git log and in `docs/superpowers/plans/`; it is
deliberately not kept here. A closed mechanism is deleted from this file, not
annotated — if a mechanism has no gap entry left in the records, it has no
section here.

**Do not trust a count stated in prose anywhere in this project, including this
file. Re-run `py audit/tools/gap_queue.py counts`.**

Two checks fail loudly when this file drifts from the records, and **both must
be run after any edit to it**:

```
py audit/tools/gap_queue.py coverage      # every mechanism and entry is locatable here
py audit/tools/gap_queue.py cite-check    # every file:line here resolves
```

`coverage` is what keeps the tail from silently shrinking: a seam entry must be
findable by its own id or by its mechanism plus its local id (`/step31`), a
content entry by its mechanism. It is why closing a mechanism means deleting its
section rather than leaving prose behind — and why a *new* finding is invisible
to the next round until it is filed as an entry and named here.

## Round 14 (2026-08-01)

Settled all 17 LIVE and 39 UNLABELLED entries the queue carried this morning.
Re-derive, never trust this table: `py audit/tools/gap_queue.py counts`.

| | before | after |
|---|---|---|
| gap entries | 360 | 335 |
| distinct mechanisms | 339 | 318 |
| live entries | 17 | 3 |
| unlabelled entries | 39 | 0 |
| suite (`--ignore=test_conformance_floor_state.py`) | 3939 passed / 6 xfailed | 4091 passed / 6 xfailed / 0 failed |

The 1 new failure is `test_relics.py::TestRegistry::test_full_ironclad_pool_registered`
asserting a stale relic count (258) -- round 14 added the `history_course`
relic (R12), bringing the real pool to 259. A leftover count pin, not a
regression; fix by bumping the literal.

**What shipped:** the last 2 live seam guards (`hook_dispatch/guard10`
`combat_is_over` vs `is_over_or_ending` across 73 dispatchers;
`hook_dispatch/guard12` run-listener order deck-first) plus
`creature_card_cmds/step19` (heal guard bare `is_ending`) -- reviewer-confirmed
**two** defects, not one; the event reroll family (`brain_leech` x2, `trial` --
`trial`'s record text was misfiled `brain_leech` wording, the real defect was
`mutate_pity` on the first draw); the `CardSelectorPrefs` family fixed at the
**root** (`guard25` + `ashwater` + `gamblers_brew` + `gnarled_hammer` +
`kifuda` + a 6th site `neows_fury`, finished by a `driver.py` registry fix,
`MinSelect-0` decline proven end-to-end); the AttackCommand-level `AfterAttack`
bracket (`skittish` fixed; multi-hit attacks no longer get blocked mid-swing);
`strike_dummy`/`fake_strike_dummy` dealer-guard removal; `NoUpgradeRoll`
carried at every C#-mandated non-combat creation site (12 `ForNonCombat*`
sites census + verified raw-ctor exclusions; `glass_eye`'s own docstring was
wrong and its draw count halved 30->15); `hefty_tablet` reward-options hooks
restored (was pinned dormant by a vacuous test); the whole
`war_historian_repy` event body ported + new `history_course` relic;
`rewards.py`'s `mutate_pity = pool is None` heuristic replaced by an explicit
source; RNG-stream fixes for `power/aggression` + `power/calamity` (wrong
stream AND wrong algorithm); `power/ringing`, `power/tangled`, `power/suck`,
`power/painful_stabs/AfterAttack`, `relic/vambrace/g6` also closed this round.
9 stale tests repaired that were pinning old buggy behaviour. 3 entries were
stale-already-fixed (`adaptable`/`illusion` death-prevention -- the record had
misidentified its own mechanism, no `ShouldDie` override exists; the
`nostalgia` chain).

**What this round did NOT do:** `power/the_bomb/InstanceType` (architectural --
judged to need `PowerCmd` `INSTANCED` dispatch AND a `full_env.py`
observation-encoding change *together*, left open on purpose -- **half of that
premise was wrong, and it is CLOSED 2026-08-01**: the blocker was the powers
CONTAINER, not the observation, and the observation change turned out to be
separable residue, see the entry);
`event/crystal_sphere` (judged a permanent deferred port -- **overturned and
CLOSED 2026-08-01**: the "no headless equivalent" premise was false, the source
ships two, see the entry); the dormant
tail (332 entries) untouched by design; `paper_phrog`'s target-identity guard
(already filed as `relic/paper_phrog/g3`, blocked on a `hooks.py` signature
change, see below); `PlayerCmd.CompleteQuest` (no sim equivalent anywhere,
unfiled -- see Open work); `run_env.py`'s `PURPOSE_IDS` vocab gap
(observation-only, unfiled -- see Open work).

**Findings that outrank the fixes:** `event/war_historian_repy/g2`'s own
`issue` text now reads "No longer a gap; no longer live" while its `verdict`
field is still `"gap"` -- the record was left internally inconsistent at fold
time. `gap_queue.py`'s typed-`live`-key rule (see Standing lessons) means the
queue counts it as a real, dormant entry regardless of the prose, which is the
right call: **trust the typed field over the sentence next to it, always**,
even when the sentence is this recent.

## Current state

| | |
|---|---|
| gap entries | **335** |
| — labelled LIVE | 3 |
| — labelled DORMANT | 332 |
| — unlabelled | 0 |
| **distinct mechanisms** | **318** |
| — with at least one live entry | **3** |
| mechanisms pinned by a `strict=True` xfail | 0 |

**No entry is unlabelled** (the first time this has been true) — but note the
label usually lives in the entry's prose tokens, not the typed `live:` key:
only a minority of gap guards carry the typed field, and `counts` reads both.

> **Stale as of 2026-08-01**, in this table and the two below it: all 3 of
> those LIVE entries have since been closed — `event/crystal_sphere` ×2 and
> `power_cmd/G5` (`power/the_bomb/InstanceType` plus the dormant
> `power/swipe/InstanceType` on the same mechanism), the last by phase 0 of
> `prompts/entity-obs-schema.md`. Re-derive rather than reading these
> numbers: `py audit/tools/gap_queue.py counts`.

Per kind (records / gap entries / mechanisms anchored / live entries):

| kind | records | entries | mechanisms | live |
|---|---|---|---|---|
| `seam` | 6 | 26 | 22 | 0 |
| `power` | 138 | 96 | 93 | 1 |
| `card` | 202 | 30 | 30 | 0 |
| `event` | 65 | 12 | 12 | 2 |
| `enchantment` | 19 | 0 | 0 | 0 |
| `relic` | 259 | 153 | 147 | 0 |
| `monster` | 109 | 2 | 1 | 0 |
| `potion` | 51 | 16 | 13 | 0 |

`power`'s one live mechanism was `power_cmd/G5` (`power/the_bomb/InstanceType`
the live site; `power/swipe/InstanceType` on the same mechanism dormant) —
**both closed 2026-08-01**, so that column reads 0 now. The seam per-record
table below already showed `power_cmd` at 0 live even while the mechanism it
anchors carried a live entry tagged `power` in the kind table above: the two
tables count different things (record-of-origin vs. tagged kind) and were
expected to disagree here.

Per seam record (entries / mechanisms / live entries):

| record | entries | mechanisms | live |
|---|---|---|---|
| `damage_pipeline` | 1 | 1 | 0 |
| `power_cmd` | 6 | 6 | 0 |
| `creature_card_cmds` | 9 | 7 | 0 |
| `turn_structure` | 2 | 3 | 0 |
| `hook_dispatch` | 8 | 5 | 0 |
| `monster_state_machine` | 0 | 0 | 0 |

## Where to start

1. **The live entries.** [Live gaps](#live-gaps) writes out every mechanism with
   a `live: true` entry — as of round 14 there were 3: one architectural
   (`power_cmd/G5`, `the_bomb`'s `InstanceType`) and two on one deferred port
   (`event/crystal_sphere`). **All three are CLOSED as of 2026-08-01**, so
   this section is currently empty; re-derive before believing that
   (`py audit/tools/gap_queue.py counts`). A live entry is a divergence
   somebody has shown is reachable on ported content today, and the set is
   meant to stay small enough to read start to finish.
2. **There are no unlabelled entries left** — every gap is now labelled live
   or dormant (typed `live:` key on a minority; prose token on the rest, and
   `gap_queue.py` reads both). That does not mean the labels are all still correct —
   **dormant is not safer than live** (see Standing lessons) — so the next
   round's work is re-executing dormancy claims, not filling a liveness hole.
3. **[Tier 1](#tier-1--the-largest-multi-site-families)**, then
   **[Tier 2](#tier-2--dormant-gaps)**, then
   **[Tier 3](#tier-3--the-long-tail)**.

## Standing lessons

These outrank any single entry below. Every one was paid for by a campaign that
learned it the expensive way, and most have recurred across several.

**On starting a unit**

- **Staleness is the largest single category.** Roughly one entry in four turns
  out to be already fixed. **Start by re-executing the entry's own witness**,
  not by reading its prose. An entry is only as current as the last change to
  the code it was written against.
- **Cross-record staleness is systemic.** Closing a seam mechanism does not
  update the content records that cite it, so downstream records keep naming it
  as open — two lanes have independently rediscovered the same closed root, and
  one record cited a gap that had closed *three rounds before that record's own
  audit date*.
- **A no-op stub's stated premise is usually false.** All twelve checked in one
  round were: gold exists, enchantments exist, the hook exists, the dispatch
  exists. "The port is a documented no-op" must never be read as "checked and
  cleared".

**On evidence**

- **A green suite is not evidence of fidelity.** In one round, four fixes each
  introduced a *new* divergence that the full suite passed straight over — a
  power spending a stack where C# abstains, a monster dropped from its own
  `AfterDeath`, a reward screen widened by a relic C# forbids there, a
  killing-blow card leaving a pile C# leaves it in. **All four were found by
  reading the C#. None was found by a test.**
- **Tests defend bugs.** Three did in one round: one asserted a missing status
  count was intended, one asserted a card lands in the exhaust pile where the
  game leaves it in Play — and that one was the *only* thing keeping the suite
  green over a real fix. A test asserting today's behaviour is not evidence the
  behaviour is right; check what it was written to prove.
- **When a pin and the C# disagree, the C# wins.** Four pins here have been
  wrong, and one was hiding a regression the same pass introduced.
- **Tooling defects are found by unit work, never by tool review** — five rounds
  running. If a probe disagrees with an execution, suspect the probe.

**On dormancy**

- **A dormancy argument is worth much less than an enumeration.** "No ported
  listener can see this" is a claim; "all 13 overrides of this hook ignore the
  parameter" is a fact.
- **Dormancy fails on its enumerations far more often than on its verdicts.** A
  4-site census was really 10. A "backstop" relied on by four entries was dead
  code, dominated by an earlier guard. A guard was closed on a consumer census
  that never listed the production driver. One reviewer withdrew its own
  dormancy rating after finding it had generalised from two probes instead of
  enumerating nine listeners.
- **Commands re-gate; counters do not.** A command that runs in a stale window
  is usually re-checked downstream and self-corrects. A `[SavedProperty]`
  counter incremented in that window never does — it permanently phase-shifts
  every later draw. Do not carry a dormancy argument from one to the other.
- **Dormant is not safer than live.** It is a claim about today's ported
  content, which the next port invalidates. Re-execute before trusting any
  liveness label, including a dormant one.

**On the records themselves**

- **Records are wrong about their reasoning more often than about their
  verdicts.** Recorded divergences that never existed (two differently-named C#
  methods conflated); entries filed under the wrong hook; premises true of the
  C# and false of the sim. A correct verdict resting on dead reasoning will
  survive until the reasoning is load-bearing, then fail silently.
- **Two records disagreeing about one mechanism has four times meant neither was
  right.** Resolve a grep hit to its enclosing *member*; never count matches.
- **Every contradiction ever found here lived at a shared engine gate** — a
  props filter, a phase pass, a dispatcher hoist — and never at a unit's own
  arithmetic. Per-unit records are reliable about their own numbers and
  unreliable about whether the shared machinery beneath them changes the answer,
  because each unit re-derives that reachability from its own vantage point.

**On closing**

- **Close conservatively. Narrowing is a result; a wrong close is a regression
  nobody will look for again.** Two mechanisms below are deliberately narrowed
  rather than closed because a faithful fix is five sites and landing two of
  five is worse than landing none.
- **A partial port is the worst resting state.** 5 of 18 sites carrying a field
  reads, to every later reader, as "this mechanism is handled". Batch the
  remainder as one task or leave it whole.
- **Never express scope as an exclusion.** While "potions are out of scope"
  stood, ten `card` and `power` entries waived real behaviour on it while the
  `relic` tier filed 45 potion-mechanic gaps — one mechanism, two answers,
  caused by the contract itself. *Unaudited* is a fact the tools report; *out of
  scope* was a claim that hid things.

**Tooling trap worth knowing before you fold a close**

`closer.py`'s entry lookup honours **two disagreeing conventions, and case alone
selects between them**: `find(rec, "G2")` matches the record's own guard label,
while `find(rec, "g2")` falls through to a **positional** lookup. The queue's
ids are positional, so a report quoting a record's own label lands on the wrong
entry and rewrites it. Use `find_labelled(local_id, label)`, which asserts the
landing. This has silently corrupted two records.

## Open work with no entry of its own

Real work that no gap entry covers. Each is here because the next person to
grep for it should find it filed rather than rediscover it.

- **`monster/_intent_count_lost` — the mechanism is closed in the records and
  the work is not done.** The spec has **18** `new StatusIntent(` sites, not the
  4 the closing census claimed: Aeonglass, Chomper, EyeWithTeeth, HauntedShip,
  LeafSlimeM, LeafSlimeS, MechaKnight, Myte, Noisebot, PhrogParasite,
  SlimedBerserker, SoulFysh (×2), TestSubject, TheInsatiable, TwigSlimeM,
  Vantom, Wriggler — the sim has an exact 1:1 construction for each. **5 are
  ported, 13 are open.** `Noisebot.cs:45` is `StatusIntent(2)`. Batch the
  remaining 13 as one task; a 5-of-18 split is the worst resting state.
- **`card/_is_dead_early_return` has two uncounted sites.** The mechanism closed
  with a 6-site list. `cards/breakthrough.py`'s top-level `if
  ctx.player.is_dead: return` right after the self-damage is structurally
  identical to the closed ones and safe to delete by the same reasoning.
  `cards/thunderclap.py` is a 7th with the same shape but, unlike Breakthrough,
  a real non-damage tail (`PowerCmd.apply` of Vulnerable) that the Breakthrough
  argument does **not** cover — it needs `PowerCmd.apply`'s own bail argued
  separately.
- **`Hook.AfterModifyingCardPlayCount` has no sim dispatcher at any site**,
  including the normal play path.
- **`card/spoils_map` vs `Hook.ModifyGeneratedMapLate`.** The sim dispatches a
  Late map pass whose only game caller is the save-load branch, because Spoils
  Map folds its Treasure-coord recording into it. Documented at the dispatch
  site; no entry.
- **`card/sweep` has no audit record.** It is sim-only.
- **`selectors.py`'s `to_draw_top` ranks by raw `energy_cost`.**
  `scripted_card_selector`'s Headbutt / Thinking-Ahead tie-break reads
  `card.energy_cost` unclamped, so an unplayable card (canonically `-1`) ranks
  below a genuinely-free card instead of tying at 0. Sim-only heuristic, no C#
  analogue, no test exercises a curse on that path. One-line clamp.
- **`run.reward_offer_selector` is deliberately unwired.** It is a test-only
  override with zero production writers by design. Events reach a real decision
  through `run.reward_selector`, which every `RunDriver` wires unconditionally
  (`driver.py:303`). **A future grep finding it unwired is expected, not a
  reopened gap.**
- **`PlayerCmd.CompleteQuest` has no sim equivalent anywhere.** Found round 14
  (R5 review, `event/war_historian_repy`): `WarHistorianRepy.cs:119,129` calls
  it after resolving UnlockCage/UnlockChest; grepped every `CompletedQuests`
  reader in the decompiled tree (`NMapPointHistoryHoverTip.cs:304`,
  `NMapPointHistoryEntry.cs:186`, `PlayerMapPointHistoryEntry.cs` + its
  serializer) and all of them are Run History screen/save bookkeeping with
  zero gameplay effect — not a gap by this campaign's own observable-
  divergence bar, but every Lantern-Key consumer may be missing it and nobody
  has enumerated the full consumer list. `ExtraFields.FreedRepy`
  (`WarHistorianRepy.cs:98`) is the same shape (its only other reader,
  `NQueenRepyBgVfx.cs:20`, is a background VFX toggle) and is likewise
  unported and unfiled.
- **`run_env.py`'s `PURPOSE_IDS` vocab is missing entries.** Found round 14
  (R7 review): `driver.py`'s `SKIPPABLE_PURPOSES` registry grew new purposes
  this round (`enchant_optional`, `exhaust_any`, `discard_any`,
  `from_discard`) that `run_env.py`'s observation vocabulary does not know
  about. Observation-only, lower severity than a behavioural gap — file it,
  don't block on it.
- **`relic/paper_phrog`'s target-identity guard is filed, not open work.**
  Found round 14 (R6): `PaperPhrog.cs:18-21`'s `target ==
  base.Owner.Creature` self-damage bail has no sim analogue because
  `modify_vulnerable_multiplier`'s signature carries no `target` parameter.
  This IS a gap entry already — `relic/paper_phrog/g3` — not a hole; noted
  here only because the fix needs a `hooks.py`/`powers.py` signature change
  that was out of R6's footprint that wave (BLOCKED-ON-FOOTPRINT, not
  BLOCKED-ON-DESIGN like `the_bomb` or `crystal_sphere` — **both of which
  turned out not to be blocked on design either, and closed 2026-08-01**;
  treat a BLOCKED-ON-DESIGN label as a hypothesis, not a finding).

## What this queue does NOT cover

Every content kind is audited and aggregated; the counts are in
[Current state](#current-state) above. What follows is what no record reaches.

`py audit/tools/audit_status.py` is the authority on coverage; the table above
is generated from the same record set as the rest of this file.

What no record reaches:

- **Framework roots with no seam.** `harness.MODEL_ROOT_CLASSES` stops
  base-class following at thirteen roots, each on the promise that a seam covers
  it. For `PotionModel` no seam did, so `PotionModel.OnUseWrapper` — the entire
  use path for all 51 potions — was verdicted nowhere until the potion tier
  recorded it once per unit. **Check the other twelve roots against `SEAMS`
  before assuming that was the only one.**
- **Emergent interactions between two individually-faithful units.**
- The holes enumerated in
  [Behaviour in no tier's scope](#behaviour-in-no-tiers-scope).

**`gap_queue.py` keeps its own `CONTENT_KINDS` list**, not derived from the
harness, so it can silently omit a kind — it omitted `potion` for a day while 51
finished records sat on disk, and `coverage` / `cite-check` printed their
complaints and exited 0 while it did.
`test/test_audit_status.py::TestQueueGeneratorCoversEveryKind` pins the kind
lists together now, and both commands return their exit code. Adding a kind
means editing both.

## How to read an entry

```
### <mechanism id>  — <one-line name>                     [LIVE|DORMANT] [pinned|unpinned]
open sites  every gap entry of this mechanism still open, with its liveness — GENERATED
impact      A / B / C — see Ordering
divergence  one sentence, sim file:line vs C# file:line
observable  what a player or a replay sees; executed numbers where the record has them
trigger     (dormant only) the concrete unported thing that makes it live
pin         the strict xfail in test/test_hook_order.py that flips to passing, or why not
fix         which sim file changes and roughly how; what the failing test asserts
radius      other mechanisms sharing machinery; content units the record names
```

**The `open sites` line is generated from the records; everything below it is
authored and may lag.** A body written while the mechanism was live stays in the
present tense after the live sites are fixed — read the bodies as briefs, and
the `open sites` line and `counts` as the current state.

**Stable ids.** A seam entry is `<seam>/<step-or-guard-id>` —
`hook_dispatch/G7`, `creature_card_cmds/N9`. A content entry is
`<kind>/<unit>/<local>`, where `<local>` is the C# hook name for a hook verdict
(`power/skittish/AfterAttack`), the record's own guard tag where the tier uses
one (`event/aroma_of_chaos/EV-3`), and `g<n>` — the 1-based index in the
record's `guards` list — where it does not (`power/nostalgia/g8`). **A
positional `guardN` id means the guard's own text does not begin with a `G`/`N`
label**; it is the generator's id, not the record's, and the two disagree
(see the `closer.py` trap above).

**Mechanism ids** are the anchor entry's id, except for the recurring content
families that no record numbers, which get a `_`-prefixed synthetic key:
`relic/_stub`, `potion/_min_select_zero`. Every merge — including every
cross-kind one — is declared in `audit/tools/gap_queue.py` with the record text
that asserts it, in `_CROSS_RECORD`, `_TAG_MECHANISM`, `_FAMILY_OVERRIDE` or
`_FAMILIES`. Nothing is grouped on an agent's hunch.

**Watch the id collisions.** `G2`, `G3`, `G4`, `G7` and `N5` all mean different
things in different records. Always carry the prefix.

**C# paths.** Records cite C# by bare filename. The ones this queue uses:

| file | path under `c:\Users\Perry\Desktop\Slay the Spire 2` |
|---|---|
| `Hook.cs` | `src/Core/Hooks/Hook.cs` |
| `CombatManager.cs`, `CombatState.cs` | `src/Core/Combat/` |
| `CreatureCmd.cs`, `CardCmd.cs`, `CardPileCmd.cs`, `PowerCmd.cs`, `PlayerCmd.cs`, `CardSelectCmd.cs` | `src/Core/Commands/` |
| `Creature.cs` | `src/Core/Entities/Creatures/` |
| `PlayerCombatState.cs` | `src/Core/Entities/Players/` |
| `CardModel.cs`, `MonsterModel.cs`, `AbstractModel.cs`, `EnchantmentModel.cs` | `src/Core/Models/` |
| `RandomBranchState.cs`, `MoveState.cs`, `MonsterMoveStateMachine.cs` | `src/Core/MonsterMoves/MonsterMoveStateMachine/` |
| `RunState.cs`, `RoomSet.cs` | `src/Core/Runs/` |
| events | `src/Core/Models/Events/` |
| powers / relics / monsters / enchantments | `src/Core/Models/{Powers,Relics,Monsters,Enchantments}/` |

Sim paths are repo-relative (`sts2_rl/...`, `test/...`).

## Ordering

Sorted by **seed-convergence impact** first, then blast radius, then fix cost.
Convergence impact is graded:

- **A — stream desync.** Changes an RNG draw count or the stream a draw comes
  from. Every later draw in the run shifts; a replay stops converging outright.
- **B — state divergence.** Changes a damage/block/HP number, a hand, a pile or
  a deck entry. The next conformance assert fires.
- **C — bookkeeping only.** Hook order or event identity with no numeric effect
  on currently-ported content.

The document runs live gaps first, then three tiers:

1. **[Live gaps](#live-gaps)** — every mechanism with a `live: true` entry.
2. **[Tier 1 — the largest multi-site families](#tier-1--the-largest-multi-site-families)**,
   written out in full. One fix each clearing many sites.
3. **[Tier 2 — dormant gaps](#tier-2--dormant-gaps)**, written out in full,
   grouped by the machinery they share.
4. **[Tier 3 — the long tail](#tier-3--the-long-tail)**, one row per remaining
   mechanism: single-site, single-unit findings, cheaper to read straight out of
   the record than to restate. The row gives the id, the liveness and the
   record's own lead clause.

---

# Live gaps

Every mechanism with at least one `live: true` entry: a divergence somebody has
shown is reachable on ported content **today**. These are the queue's first
call on anyone's time.

A live label is a claim about what the records state, not a proof of
reachability, and the reverse holds too: several of the entries below were
DORMANT until somebody re-executed them. Liveness moves in both directions, and
a round whose live count only falls is not measuring honestly.

### `power_cmd/G5` — no `PowerInstanceType` (Instanced / InstancedPerApplier)  [**CLOSED**] [unpinned]

- **open sites** 0 — `power/the_bomb/InstanceType` and
  `power/swipe/InstanceType` both closed 2026-08-01
- **impact** B — a power that should track per-applier instances collapses
  into one stack.
- **divergence** `PowerCmd.cs:165-174`'s `FindExistingInstanceForStacking`
  dispatches on `power.InstanceType` (`PowerModel.cs:144`, default `None`);
  the sim's stacking check always behaved as `None`. 21 C# powers declare an
  override (19 `Instanced`, 2 `InstancedPerApplier` — `OblivionPower.cs:27`,
  `StranglePower.cs:29`), 11 of them ported. Round 14 fixed the DISPATCH but
  not the CONTAINER: `Creature.powers` was a dict with one slot per id, so an
  Instanced re-application overwrote that slot and orphaned the instance it
  displaced — still hook-registered and still ticking, but unreadable.
- **state** **CLOSED 2026-08-01** (phase 0 of
  `prompts/entity-obs-schema.md`). `Creature.powers` is `creatures.PowerList`
  — C#'s ordered `List<PowerModel>` (`Creature.cs:34`) with C#'s own
  accessors: `get`/`[]` = `GetPower`, a FirstOrDefault and so the OLDEST
  instance (`Creature.cs:571`); `instances(id)` = `GetPowerInstances`
  (`:581`); `values()` = `Powers` (`:326`); `add`/`discard` =
  `ApplyPowerInternal`/`RemovePowerInternal` (`:600-612`, `:641-650`, the
  latter by identity). Three consequences, each pinned by
  `test/test_power_instances.py`: every instance is reachable and is a hook
  listener in application order (`CombatState.cs:416`), the death strip and
  the turn-start snapshot included; `INSTANCED_PER_APPLIER` searches every
  instance for the matching applier (`PowerCmd.cs:168`) instead of testing
  the one visible slot; and `PowerCmd.apply` returns the instance it produced
  (the sim's `Apply<T>`, `PowerCmd.cs:66-87`), which is what the six call
  sites that configure "the power I just applied" use now — a re-fetch by id
  would answer with the oldest instance. Both hand-rolled substitutes for
  instancing are retired (`TheBombPower`'s `bombs` fuse list, `SwipePower`'s
  `stolen_cards` bucket), so all 11 ported declarers carry the real dispatch.
- **residue — CLOSED 2026-08-02** (phase 1 of `prompts/entity-obs-schema.md`).
  Was: `full_env.py` wrote one `(presence, fine, coarse)` triple per power ID,
  so the OBSERVATION collapsed instances (an RL-schema limit with no C#
  counterpart, not a `PowerCmd` divergence). Now: `full_env.py`'s `_power_rows`
  writes one padded ROW per power INSTANCE off `creature.powers.values()`
  (the ordered list phase 0 introduced), each with its own `_power_aux`; two
  `the_bomb` fuses are two rows with independent `amount`/`aux`. Pinned by
  `test_power_instances.py::TestObservationResidue::
  test_two_instances_are_two_distinct_observation_rows_with_their_own_aux`
  (the same tripwire, inverted into a closure test) and
  `test_combat_obs_v4.py::test_the_bomb_two_instances_are_two_rows_with_distinct_aux`.
  The stream over fixed seeded episodes is no longer required to be
  byte-identical to the pre-phase-1 tree (the schema itself changed); see
  `records/seam/power_cmd.json` guard G5 for the full re-audit.
- **radius** Was the largest single member of `hook_dispatch/G3`'s
  neighbourhood by mechanism reach; not itself part of that phase-pass family.

### `event/crystal_sphere/IsAllowed` — CLOSED 2026-08-01  [**CLOSED**] [unpinned]

- **open sites** 0
- **divergence** C# gates entry on "every player holds >= 100 gold, and the act
  index is past act 1"; `events/crystal_sphere.py` hard-returned `False`
  unconditionally, a deliberate stub.
- **state** **CLOSED.** `CrystalSphere.is_allowed` now implements the real
  gate. It landed in the same change as `g1`, which the prior round's analysis
  correctly established was mandatory: `RoomSet.ensure_next_event_is_valid`
  (`rooms.py:441-458`) applies `is_allowed` as the **sole** routing gate with
  **no options-emptiness fallback**, and `Event.begin()`/`_set_state`
  (`events/base.py:167-176, 319-323`) silently self-finishes an empty-options
  event, so the gate alone would have traded one divergence for another. That
  reasoning stands and is now pinned by
  `test_crystal_sphere_routing_has_no_fallback_for_an_empty_bodied_event`.
- **radius** Closed together with `event/crystal_sphere/g1`.

### `event/crystal_sphere/g1` — CLOSED 2026-08-01  [**CLOSED**] [unpinned]

- **open sites** 0
- **divergence** The payout is the `CrystalSphereMinigame`, driven 3 times for
  `UNCOVER_FUTURE` (after a `LoseGold(50 + NextInt(1,50))`) and 6 times for
  `PAYMENT_PLAN` (after adding a Debt curse). None of it was ported.
- **state** **CLOSED.** The whole minigame is ported in
  `events/_crystal_sphere.py` — the 11x11 grid, the radius-2 corner pre-clear,
  all 15 items with their exact construction order and one `NextItem`
  placement draw each (including the `&&` short-circuit and the retry loop
  verbatim; the failure path is unreachable, measured over 20k boards), the
  Big/Small clear shapes with the source's neighbour ORDER, the
  all-cells-clear reveal rule, and the reveal-ordered payout.

  The prior round's "permanent deferred port" verdict rested on a premise that
  turned out to be false: that a 121-cell spatial choice has *no headless
  analogue*. The source ships two. `CrystalSphereScreenHandler`
  (`AutoSlay/Handlers/Screens/`) is the game's own automated player for this
  screen and clicks `random.NextItem(hidden cells)` — that is now the sim's
  click rule, cited rather than invented. And `RunReplays` already records the
  decision verbatim as `CrystalSphereClick {x} {y} {tool}`
  (`Commands/CrystalSphereClickCommand.cs`), so a replay needs no policy at
  all; `RunState.crystal_sphere_clicks` feeds those recorded clicks straight
  into the engine.

  What is NOT modelled, deliberately: the cell click as an RL *action*. A
  121-wide action block does not fit `CHOICE_SLOTS`, and at this event's
  frequency (act 2+, gold >= 100, one of 18 shared events, deduped per run)
  such a head would never train. The two EVENT options are surfaced normally.
  The click draw uses a SIM-ONLY `RunState.crystal_sphere_rng` — the game
  spends no run RNG on a human click, so drawing from any parity stream would
  shift every later placement and reward draw; pinned by
  `test_clicking_never_touches_a_parity_rng_stream`.

  `event/crystal_sphere/CalculateVars` closes with this: the
  `50 + NextInt(1, 50)` roll is implemented on the event's own Rng.
- **radius** Closed together with `event/crystal_sphere/IsAllowed`.
---

# Tier 1 — the largest multi-site families

The mechanisms with the widest blast radius: one fix each clearing many
sites. **Read the bodies as briefs.** They were written while the mechanism
was live and are in the present tense; the generated `open sites` line at the
head of each is the current thing in it.

## 1A. Grade A — stream desync

A wrong draw count or a wrong stream. These stop a replay converging
outright, which is the work this pipeline exists to unblock.

### `event/EV-3` — the per-event `Rng` replaced by the shared run stream  [DORMANT] [unpinned]

- **open sites** 1: `event/jungle_maze_adventure/EV-3` (dormant)
- **impact** A — every one of these draws comes off a stream the game never
  touches for it, and fails to advance the stream the game does.
- **divergence** Each C# `EventModel` owns an `Rng` seeded from the run seed plus
  the event id and rolls everything through `base.Rng`; 28 of the 34 sim event
  modules that roll anything roll only on the shared `self.rng`. The sim already
  models the per-event stream — `Event.__init__` builds `self.event_rng` from
  `make_event_rng(seed, ID)` (`sts2_rl/events/base.py:84-88`) and 6 modules branch
  on it — so this is an inconsistency inside the sim, not a missing capability.
- **observable** A shared-stream draw both takes a number the game never takes
  off that stream and leaves the event stream un-advanced, so the desync
  compounds for the rest of the run. Executed:
  `py audit/tools/event_probes.py eventrng` enumerates the 28. Worked example —
  `AromaOfChaos.cs:33` passes `base.Rng` into `CardCmd.TransformToRandom`;
  `sts2_rl/events/aroma_of_chaos.py:27` calls `run.transform_card(chosen[0])` with
  no `pick_rng`, so `sts2_rl/run.py:457-458` falls back to `self.rng.choice`.
- **pin** None. Like `turn_structure/G9` the observable is a stream identity, not
  a hook order, so `test_hook_order.py` is the wrong home; the natural pin is a
  stream-accounting assert in `test/test_conformance_determinism.py`.
- **fix** Per module, thread `self.event_rng` into the roll — most sites already
  have the argument (`run.transform_card(..., pick_rng=...)`,
  `stable_shuffle(..., rng)`), so the change is at the call site rather than in
  the run. Do it as one sweep: 28 modules, one convention, and the probe is the
  checklist. Failing test asserts that driving each event consumes zero draws
  from the shared run rng and the expected count from `event_rng`.
- **radius** Compounds every other event-tier mechanism that also picks wrongly
  (`event/EV-5`, `event/EV-6`, `event/EV-9`) — fixing the stream without fixing
  the pick, or the reverse, leaves the site still divergent. In legacy (RL) mode
  both streams are the same `random.Random`, so the observable is parity-only —
  an exercised sim mode, not an unreachable one.

## 1B. Grade B — state divergence

A number, a hand, a pile or a deck entry differs. The next conformance
assert fires; the stream itself survives.

### `power/_death_prevention_branch` — death prevention runs the wrong branch, and `AfterDeath` never fires  [DORMANT] [unpinned]

- **open sites** 4: `monster/test_subject/g1` (dormant), `power/adaptable/g5` (*unlabelled*), `power/illusion/g6` (*unlabelled*), `power/steam_eruption/g4` (dormant)
- **impact** B — an HP number conformance asserts on directly, plus a missing
  energy gain and a missing draw.
- **divergence** C# **lets the death happen**: `Hook.ShouldDie` returns true,
  `CreatureCmd.cs:507-508` fires the died event and computes
  `shouldRemoveFromCombat = false`, then `AfterDeath` sets `isReviving` — leaving
  the creature **dead at 0 HP, retained in combat**. The sim **prevents** the
  death from `should_die` (`sts2_rl/powers.py:3365-3370` returns `False`) and
  `sts2_rl/cmds.py:106-113` floors the creature at **1 HP** with `is_dead` False.
- **observable** Three, and the third is the one the prompt-level review found:
  1. **HP 1 vs 0**, asserted on directly by conformance.
  2. **Feed.** `Feed.cs:38` computes
     `shouldTriggerFatal = Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())`
     and `AdaptablePower` does not override it, and `WasTargetKilled` is true
     even when the death is prevented (`DamageResult.cs:89-99` says so in as many
     words, `:97` giving Fairy in a Bottle as the example). **The game grants the
     +3 max HP for Feeding the Test Subject to death; the sim grants nothing**,
     and `sts2_rl/cards/feed.py:17-18`'s docstring asserts the opposite behaviour
     is correct.
  3. **`Hook.AfterDeath` fires on BOTH C# branches and in the sim on NEITHER.**
     `CreatureCmd.cs:519` dispatches it with `wasRemovalPrevented: false` and
     `CreatureCmd.cs:566` with `wasRemovalPrevented: true`, in both cases to
     *every* listener. The sim fires `hooks.on_death` only on its real-death arm
     (`sts2_rl/cmds.py:105`). Witness: **`GremlinHorn.cs:24-32` has no
     `wasRemovalPrevented` guard** — its only test is
     `target.Side != base.Owner.Creature.Side` — so the game grants **+1 energy
     and draws 1 card** every time the Test Subject, the Waterfall Giant,
     Fogmog's Eye with Teeth or The Obscura's Parafright dies, prevented or not,
     while `sts2_rl/relics/gremlin_horn.py:18-22` never runs on any of them.
     Gremlin Horn is a ported Uncommon relic and all four appliers are ported
     enemies. The extra draw perturbs the piles for the rest of the fight and the
     RNG stream for the rest of the run.
- **pin** Unpinned.
- **fix** Reshape the prevention arm in `sts2_rl/cmds.py:106-113` to the C# one:
  let `is_dead` stand at 0 HP, keep the creature in `enemies` when
  `should_creature_be_removed_from_combat_after_death` says so, and dispatch
  `on_death(..., was_removal_prevented=True)` from it. Then let
  `sts2_rl/cards/feed.py:45` read the kill rather than `is_dead`. Failing test
  asserts Gremlin Horn's energy-and-draw fires on a prevented-death kill.
- **radius** `damage_pipeline/G4` (the killing-blow skip recomputed after death
  prevention) is the same window from the other side and is **not** re-verdicted
  by these records; `power/_should_stop_combat_from_ending` holds the combat open
  in the C# shape and does not exist in the sim.
- **the counter-example is the useful half** `monster/decimillipede_segment` is
  **correct**: `ReattachPower` lands on `should_remove_from_combat_after_death`,
  not on `should_die`. Executed — a killed segment fires `on_death`, sets
  `retained_after_death=True` and keeps taking turns (DEAD → REATTACH → WRITHE →
  CONSTRICT → BULK). **PROMPT.md class 21 names the wrong landing site and not
  the right one; this is the right one.**

### `hook_dispatch/G3` — no Early / VeryEarly / Late phase passes  [DORMANT] [unpinned]

- **open sites** 2: `power/hellraiser/AfterCardDrawnEarly` (dormant), `relic/tungsten_rod/g3` (dormant)
- **impact** B — energy cost differs; ordering becomes registration luck.
- **divergence** 24 of `Hook.cs`'s 147 dispatchers run 2-4 *complete* listener
  passes and `AbstractModel.cs` declares 27 phase-suffixed hooks; `sts2_rl/hooks.py`
  has one walk per hook and no phase concept at all (`hooks.py:673-680` says so).
- **observable** `TangledPower.TryModifyEnergyCostInCombat` (EARLY,
  `powers.py:1486-1502`, applied by the ported Vine Shambler
  `monsters/overgrowth/vine_shambler.py:42-43`) and
  `FreeAttackPower.TryModifyEnergyCostInCombatLate` (LATE, `powers.py:1133-1155`,
  applied by the ported card Unrelenting `cards/unrelenting.py:40`) both target
  Attacks: the game always ends at cost 0; the sim ends at 1 when Free Attack was
  applied first and 0 when Tangled was. `BufferPower.cs:17-19` carries a source
  comment stating the Late phase is load-bearing.
- **pin** `TestHookDispatchOrder::test_late_energy_cost_modifiers_run_after_early_ones`.
- **fix** Add a phase parameter to `HookSystem`'s dispatch helper and let a
  listener declare `<hook>_early` / `<hook>_late` methods; dispatch runs the
  passes in order, re-enumerating the listener list each pass (C# does). Start
  with the dispatchers that have ported phase-split listeners — energy cost,
  `BeforeTurnEnd` (that is `turn_structure/G12`), `AfterSideTurnStart`. Failing
  test asserts cost 0 regardless of which power was applied first.
- **radius** Same mechanism as `turn_structure/G12` (BeforeTurnEnd's three
  passes, Orichalcum) — fixing the phase machinery here is the prerequisite for
  that entry's clean fix. Also blocks a faithful `BufferPower` port
  (`damage_pipeline/G2`).

### `turn_structure/G13` — no `CheckWinCondition` after the turn-1 setup  [DORMANT] [unpinned]

- **open sites** 1: `relic/festive_popper/g3` (dormant)
- **state** All six C# sites recompute now, and the four inline
  `_all_enemies_dead()` / `is_dead` pairs -- which were
  `CheckWinCondition` with the tie-break the wrong way round -- call the
  real check instead. `SetupPlayerTurn`'s `IsDead` guard is ported.
- **impact** B — a dead player keeps taking legal actions.
- **divergence** C# calls `CheckWinCondition` at six sites, including
  immediately after `SetupPlayerTurn` (`CombatManager.cs:573`); the sim checks
  after each enemy move (`combat.py:336-338`), after the enemy side, and after
  the *next* player turn's setup (`combat.py:681-685`), but **nothing** follows
  `combat.py:208-209` (`on_combat_start` → `start_turn`). Its other three
  "checks" (`combat.py:655-660`, `666`, `673`) only test the cached
  `phase == COMBAT_OVER` flag.
- **observable** A player killed during turn-1 setup — by an
  `on_combat_start`/`on_player_turn_start(ed)` listener — is left in
  `Phase.PLAYER_TURN` at 0 HP with a legal action set, where the game ends the
  combat immediately. The record's own text flags that the inherited "no ported
  listener deals damage" dormancy claim is **false**.
- **pin** `TestTurnStructureOrder::test_turn_one_setup_death_ends_the_combat`.
- **fix** Add a real `_check_win_condition()` (recomputing, not reading the
  cached flag) and call it after `combat.py:209`; while there, decide whether the
  other two flag-reads should also recompute — the record notes none of the three
  existing sites does. Failing test asserts `phase == COMBAT_OVER` after a
  turn-1-setup kill.
- **radius** The largest single-record mechanism in `turn_structure`. Adjacent:
  `turn_structure/G10` (the combat-end path's two disagreeing player-death exits)
  and `hook_dispatch/G8` (nothing should dispatch once combat is ending) — all
  three are the same "the sim's combat-over state machine is thinner than the
  game's" area, and a fix that recomputes the condition should land with G10's
  two-exit reconciliation.

### `damage_pipeline/G2` — no `AfterModifyingXxx(modifiers)` companion events  [DORMANT] [unpinned]

- **open sites** 3: `damage_pipeline/G2` (dormant), `hook_dispatch/step38` (dormant), `power_cmd/step31` (dormant)
- **state** The arithmetic, stated exactly because the body below invites
  miscounting: `Hook.cs` declares **13** `AfterModifying*` variants; 4 of
  them (Block, Damage, HpLostBeforeOsty, HpLostAfterOsty) are covered by 3
  sim hooks and were never part of the 9 this mechanism tracks; of those 9,
  **2 are implemented and 7 remain** -- CardPlayCount, CardRewardOptions,
  EnergyGain, GoldGained, HandDraw, OrbPassiveTriggerCount (Defect-only,
  waived under N3) and Rewards. Each is dormant on its own executed merits,
  and none of the 7 has been re-verified since.
- **impact** B at the block site (a relic fires on the wrong gain), C elsewhere.
- **divergence** C#'s modifier dispatchers track which listeners actually
  changed the value and fire a companion event so those listeners can react only
  when they were an active modifier — `Hook.cs:649-829` declares **13**
  `AfterModifying*` variants. The sim implements exactly one, `modify_hp_lost` /
  `after_modify_hp_lost` (`hooks.py:126-155`, called from `cmds.py:85-87`); the
  other 12 (BlockAmount, CardPlayCount, CardRewardOptions, DamageAmount,
  EnergyGain, GoldGained, HandDraw, OrbPassiveTriggerCount, PowerAmountGiven,
  PowerAmountReceived, Rewards …) have no surface.
- **observable** Live at the **block** site: all three C# listeners on
  `AfterModifyingBlockAmount` are ported (`Vambrace.cs:78-90`,
  `PaelsLegion.cs:146-158`, `FastenPower.cs:36-40`) and each hand-rolls its
  "I actually fired" side effect onto a different event. Pael's Legion's
  hand-roll nets the same (`relics/paels_legion.py:33-51`); **Vambrace's does
  not** — `relics/vambrace.py:36-40` burns its once-per-combat `_used` flag on
  the *first* block gain, where C# latches `TriggeringCard` and doubles every
  block gain of that one card play. Elsewhere the machinery's absence is
  structural: `ArtifactPower.AfterModifyingPowerAmountReceived`
  (`ArtifactPower.cs:38-41`) is the actual method that calls
  `PowerCmd.Decrement`, reimplemented inline at `cmds.py:301-305`, and
  `RuinedHelmet.cs:55-60` likewise at `relics/ruined_helmet.py:37`.
- **pin** `TestCreatureCardCmdsOrder::test_vambrace_doubles_every_block_gain_of_one_card_play` (the block site only; the other 11 variants are unpinned).
- **fix** Generalise the `modify_hp_lost` pattern: give each modifier dispatcher
  in `hooks.py` an out-param `modifiers` list and a paired `after_modify_<x>`
  notifier, then re-home the three block listeners and the two power-amount
  listeners onto it. Failing test asserts Vambrace doubles *both* block gains of
  a two-block-gain card play and neither gain of the next card.
- **radius** Blocks a faithful `BufferPower` port (its whole mechanism is
  `AfterModifyingHpLostAfterOsty`) and sits on the very seam the Unsettling Lamp
  bug lived on (PowerAmountGiven/Received). Same dispatchers as
  `hook_dispatch/G9` and `damage_pipeline/G3`.

## 1C. Relic-tier families

Three families that share one shape. The relic tier is where the collapse
ratio is most extreme — fixing one site generally clears every site.

### `relic/_is_allowed` — `Relic` has no `is_allowed` member at all  [DORMANT] [unpinned]

- **open sites** 2: `relic/lasting_candy/IsAllowed` (dormant), `relic/lasting_candy/g3` (dormant)
- **impact** B — the wrong relic is offered, so the run diverges in content
  rather than in a draw count.
- **divergence** `RelicModel.IsAllowed(runState)` gates whether a relic may enter
  a pool at all; the commonest predicate is `IsBeforeAct3TreasureChest`
  (`TotalFloor < 41`). The sim's `Relic` base class **declares no `is_allowed`
  and no `is_allowed_at_neow` behaviour** — the gate simply does not exist, so
  every gated relic is offerable at every floor.
- **observable** Executed: at `total_floor = 60` the grab bag still yields
  `toxic_egg`, which the game stops offering after floor 40.
- **pin** Unpinned, and **it cannot be pinned yet** — a pin would have to assert
  on an API that does not exist, so it would error rather than xfail. Pin it the
  moment the member lands.
- **fix** Add `is_allowed(run)` to `sts2_rl/relics/base.py` and consult it in the
  pool builders. **`PROMPT.md` v6 item 2 is the trap:**
  `RelicModel.IsAllowedAtNeow` DEFAULTS to `IsAllowed(player.RunState)`
  (`RelicModel.cs:443-446`), and the sim models the two as independent members —
  whoever adds `is_allowed` must make `is_allowed_at_neow` delegate, or Neow will
  keep using a stale flag.
- **radius** 34 recorded sites, one base-class member. The largest
  single-member fix anywhere in this queue.

### `relic/_stub` — relics ported as no-ops on premises that are now false  [DORMANT] [unpinned]

- **open sites** 3: `relic/bing_bong/g1` (dormant), `relic/massive_scroll/g4` (dormant), `relic/punch_dagger/g1` (dormant)
- **state** Round 14 closed the live site: `relic/kifuda/AfterObtained` is no
  longer part of this family. Kifuda's stub premise had already gone false
  (`after_obtained` is real), and this round fixed what was left of it — the
  `CardSelectorPrefs` `MinSelect 0` root it shared with `guard25` — as part of
  the whole family fix (`ashwater`, `gamblers_brew`, `gnarled_hammer`,
  `kifuda`, `neows_fury`, `driver.py`'s `SKIPPABLE_PURPOSES` registry). See
  the standing lesson on the tooling trap: `closer.py`'s two id conventions
  cost round 13 two corrupted records on entries in this exact family.
  `royal_stamp` is no longer a stub either -- it carries a complete
  `after_obtained` (Niche shuffle + `RoyallyApprovedEnchantment` attach),
  pinned by
  `test_shared_enchantments.py::test_royal_stamp_enchants_a_deck_card_and_burns_the_niche_shuffle`.
  The false premise "the sim has no enchantments" is now true of
  `punch_dagger` alone. `bing_bong` (needs an adder argument threaded
  through `after_card_added_to_deck`) and `massive_scroll` (no
  MultiplayerOnly card pool ported) are real divergences left open because
  they are unreachable, not because they are unchecked.
- **impact** B — the relic simply does nothing.
- **divergence** `sts2_rl/relics/base.py:20-24` documents a deliberate policy:
  relics whose whole effect is out of combat are "registered as documented no-op
  stubs so the full pool is constructible". The policy was sound when written.
  **The premises have since been overtaken** — the sim grew a gold system, a
  potion belt, rest sites and card rewards, and the stubs' docstrings still cite
  their absence. `lucky_fysh` says "no gold system"; `run.gold` exists.
- **observable** Executed: holding `old_coin` the 300 gold never arrives;
  holding `planisphere` the 5 HP heal on a `?` node never happens.
- **pin** Unpinned. Each is individually easy to pin — assert the effect happens.
- **fix** Per relic, but the *class* is one decision: re-audit every stub whose
  docstring names a system the sim now has. The stub docstrings are the index.
- **radius** This family is why "the port is a documented no-op" must never be
  read as "checked and cleared".

### `relic/_combat_reset` — per-combat relic state is never reset  [DORMANT] [unpinned]

- **open sites** 1: `relic/forgotten_soul/g1` (dormant)
- **impact** B — a wrong number on turn 1 of every combat after the first.
- **divergence** `RunState` carries one relic instance across combats. C# resets
  per-combat relic state at the combat boundary; the sim has no such dispatch, so
  a latch set in combat 1 is still set in combat 2.
- **observable** Executed, same relic instance through two `CombatState`s:
  `red_skull` opens combat 2 at **Strength −3**; `permafrost` gives 7 block on
  the first Power in combat 1 and **0** in combat 2; `vambrace` 10 then 5;
  `centennial_puzzle` 3 cards then 0; `ruined_helmet` +4 Strength then +2;
  `paels_tears` turn-1 energy 3 then 5. The game gives combat 1's answer both
  times.
- **pin** Unpinned — and **this is the single best pin candidate in the tier.**
  One `@pytest.mark.parametrize` over `(relic_id, stimulus, assertion)`, body
  "run the stimulus in two successive combats with the same relic instance and
  assert the observations are equal". Zero RNG, ~6 lines per relic, and every
  case flips on one fix.
- **fix** Add the combat-boundary reset dispatch. Note `power/diamond_diadem/g1`
  (`power/diamond_diadem`) and `relic/diamond_diadem` G1 are the *same* mechanism
  reached through a different hole — a combat that ends on the player's own turn
  never reaches `on_player_turn_end` at all — so fixing only the turn-end path
  will leave that one broken and looking fixed.
- **radius** 13 relics, one dispatch. `red_skull`'s −3 Strength is the defect
  `PROMPT.md` v6 names as the sweep's worst false clear.


---

---

# Tier 2 — dormant gaps

Real divergences argued unreachable on today's ported content, grouped by the
machinery they share. Dormant is a claim about content, not about the code —
the next port invalidates it.

## 2A. Missing guard families

### `creature_card_cmds/N3` — the `CardPileAddResult` failure surface is unmodelled  [DORMANT] [unpinned]

- **open sites** 2: `creature_card_cmds/step70` (dormant), `creature_card_cmds/step73` (dormant)
- **state** The behaviourally significant branch is already reproduced.
  `CardPileCmd._refuses_combat_add` is one boolean consulted at the top of
  all three pile-ADD helpers and covers C#'s batch `IsEnding` refusal, the
  per-card `creature.IsDead` refusal and the `!IsInProgress` refusal. What
  stays open is the RESULT OBJECT, and it is a confirmed waiver rather than
  a deferral: no external C# caller reads `.success` / `.oldPile` /
  `.modifyingModels` for gameplay outside the Deck path, and on this call
  path `oldPile` and `modifyingModels` are provably always null -- a ported
  object would carry no information beyond `success`. `step73`
  (`ShouldAddToDeck`, still zero overrides game-wide) stays its own open gap.
- **divergence** C#'s `Add` returns a per-card result carrying
  success/oldPile/modifyingModels and sets `success = false` for a dead owner, a
  removed-from-state card, a detached combat card, or a `ShouldAddToDeck`
  prevention (`CardPileCmd.cs:322-397`); the sim's three pile helpers
  (`cmds.py:463-512`) return `None` and always succeed. The behaviourally
  significant one is `creature.IsDead -> success = false`
  (`CardPileCmd.cs:329-340`): C# silently drops a card generated onto a dead
  player, the sim appends it.
- **trigger** `ShouldAddToDeck`/`AfterAddToDeckPrevented` have zero overrides
  game-wide, so the trigger is porting the first one — or any card generation that
  can outlive the player's death (the sim ends combat as soon as the player dies,
  `combat.py:419-420`).
- **pin** unpinned. **fix** return a small result object from the pile helpers and
  honour the dead-owner drop. **radius** `hook_dispatch/G8`, `/N4`.

## 2B. Missing hook surfaces

### `creature_card_cmds/G8` — no `AfterCardChangedPiles` at all  [DORMANT] [unpinned]

- **open sites** 1: `creature_card_cmds/G8` (dormant)
- **state** **Narrowed, not closed, and its own site enumeration was one
  short.** `CardCmd.Exhaust` IS `CardPileCmd.Add(card, PileType.Exhaust)`
  (`CardCmd.cs:242`), so **every exhaust dispatches `AfterCardChangedPiles`
  in C# and none does in the sim** -- five dispatch sites, not four. Add,
  Draw, the two reshuffle helpers and `RemoveFromCombat` are wired; the
  manual play needs the Play-pile modelling first (`creature_card_cmds/N9`),
  and the exhaust leg is unwired. Deliberately left: a faithful wiring is
  five sites, and landing two of five is worse than landing none.
- **divergence** Every C# pile move funnels through it (`CardPileCmd.cs:635` Add,
  `188` RemoveFromCombat, `683` manual play, `CardCmd.cs:447` transform); the sim
  has one hook per transition (`on_card_drawn`, `on_card_discarded`,
  `on_card_exhausted`, `on_card_entered_combat`) plus a deck-only relic shim
  (`relics/base.py:208-210`), and nothing observes an arbitrary pile-to-pile move.
- **trigger** All four ported C# listeners filter to `pile.Type == Deck`, so the
  shim covers them everywhere except the transform path (`creature_card_cmds/G3`). The three C#
  listeners that watch **combat** piles — `SovereignBlade`, `Hoarder`, `SoulFysh`
  — are unported; porting any makes this live.
- **pin** unpinned. **fix** add `on_card_changed_piles(card, old_pile, new_pile)`
  and fire it from the three pile helpers. **radius** `creature_card_cmds/G3`, `/G11`,
  `hook_dispatch/G1`.

## 2C. Listener-registry shape

`hook_dispatch/G7` and `/N5` are the surviving half of a family the queue's
own radius notes say lands together or not at all.

### `hook_dispatch/G7` — no per-item liveness re-check  [DORMANT] [unpinned]

- **open sites** 2: `hook_dispatch/step12` (dormant), `hook_dispatch/step16` (dormant)
- **divergence** C# yields `if (Contains(item))` **lazily, per item**
  (`CombatState.cs:482-488`), and `Contains` (`549-599`) drops any
  relic/potion/card/affliction/enchantment/orb whose `HasBeenRemovedFromState` is
  set or whose owner is not `IsActiveForHooks`; every sim dispatcher walks a
  `list(self._listeners)` snapshot with no re-check.
- **observable** Dormancy is *executed and reproducible from the committed tree*:
  `py -m pytest test/ -q -p audit.tools.stale_listener_plugin` instruments every
  listener call with C#'s lazy re-check. The only hit across the suite is
  `on_enemy_side_end -> IntangiblePower`. **Caveat: the record quotes that run as
  "2476 passed / 30 xfailed", which is a stale tree — the suite is 2478 passed /
  38 xfailed today. Re-run before relying on the number.**
- **trigger** Any listener that removes another listener mid-dispatch.
- **fix** Needs `hook_dispatch/G1`'s derived listener list plus a `HasBeenRemovedFromState`
  flag on cards/relics (`creature_card_cmds/step68`).
- **radius** `hook_dispatch/G2`, `/G1`, `/G5`, `/G6`, `/N5` — the registry-shape
  family lands together or not at all.

### `hook_dispatch/N5` — no run-level listener list  [DORMANT] [unpinned]

- **open sites** 3: `hook_dispatch/N5` (dormant), `hook_dispatch/step14` (dormant), `hook_dispatch/step18` (dormant)
- **trigger** Porting any `CardModel` overriding `AfterRoomEntered`,
  `AfterRewardTaken`, `ShouldAddToDeck` or another run-level hook.
- **radius** `creature_card_cmds/G12` (nowhere to hang `AfterGoldGained`).

## 2D. Power pipeline

### `power_cmd/G2` — Unsettling Lamp's condition has the same blind spot  [DORMANT] [unpinned]

- **open sites** 1: `power_cmd/step10` (dormant)
- **state** The body below is **backwards about which side had the bug**.
  `UnsettlingLamp.cs` has no `amount <= 0` guard anywhere -- both its latch
  and its doubling gate purely on `GetTypeForAmount(amount) != Debuff`. The
  sim's own bail WAS the divergence, rejecting exactly the negative-Strength
  shape C# doubles; it is deleted and the condition is sign-aware now.
  Duration ticks are structurally unreachable from the Lamp (every tick goes
  through `PowerCmd.modify_amount`, which never calls `modify_power_amount`).
  **What still blocks `damage_pipeline/G2`'s variants is dispatch
  architecture**: `modify_power_amount` returns a bare int with no modifiers
  out-list.

`relics/unsettling_lamp.py:44-53` bails on `amount <= 0` and then checks the static
`power_type`, where C# uses `power.GetTypeForAmount(amount)`
(`UnsettlingLamp.cs:124`). `Malaise.cs:40` and `Resonance.cs:33` both apply
negative `StrengthPower` with `applier = player, cardSource = this` — exactly the
shape Lamp doubles — and the sim's `amount <= 0` guard rejects it before the
sign-aware check would matter. **This is the seam the 933T Mecha Knight bug lived
on**: the ordering half is fixed, the sign half is not.

### `power_cmd/G3` — the three power-amount phases collapsed into one chain  [DORMANT] [unpinned]

- **open sites** 1: `power_cmd/step27` (dormant)
- **state** The flat registration-order chain is gone: given-additive then
  given-multiplicative (C#'s exact sum-then-product, which a naive fold gets
  wrong) under a real `applier != null && ContainsCreature(applier)` gate,
  then the received chain unconditionally. Artifact and Ruined Helmet are
  real listeners now instead of a hard-coded block outside the hook loop.
  **The recorded dormancy reasoning was dead:** it held that Lamp and Ruined
  Helmet are disjoint because Lamp gates on the static `power_type`, which is
  no longer true. The conclusion survives for a reason nobody had recorded --
  Lamp is GIVEN-side and RuinedHelmet/Artifact are RECEIVED-side, so they
  were never on the same C# hook, and the sim's collapsed chain was the only
  thing that ever put them in a race.
- **trigger** The two general listeners are domain-disjoint today (Unsettling Lamp
  given-side debuff-only, Ruined Helmet received-side buff-only). A third listener,
  or either widening, collides.
- **radius** `hook_dispatch/G3` (phases), `hook_dispatch/G4`
  (`damage_pipeline/G2`, the companion events), `/G1`.

### `power_cmd/step26` — one code path serves Apply and ModifyAmount  [DORMANT] [unpinned]

- **open sites** 1: `power_cmd/step26` (dormant)

C# has two independently-coded pipelines whose guards differ (`PowerCmd.cs:79-87`);
the sim collapses them (`cmds.py:270-332`). It reaches the same steady state for
ported content, but the collapse is not verified line-for-line — and `hook_dispatch/G4` is
the one place it has already been proven wrong. **Read this entry before touching
`PowerCmd.apply`.**

## 2E. Card verbs with no sim counterpart

### `creature_card_cmds/step51` — the Sly keyword is unported  [DORMANT] [unpinned]

- **open sites** 1: `creature_card_cmds/step51` (dormant)

No `CardKeyword.Sly` / `IsSlyThisTurn` analogue anywhere in `sts2_rl`, so
`CardCmd.Discard`'s collect-then-auto-play tail (`CardCmd.cs:186-188, 201-204`) and
the `AutoPlayType.SlyDiscard` path have no counterpart. Porting any Sly card also
makes step 50's DiscardAndDraw ordering live at the same moment.

### `creature_card_cmds/step56` — no `PileIndexSort` on transform  [DORMANT] [unpinned]

- **open sites** 1: `creature_card_cmds/step56` (dormant)

`CardCmd.cs:353-360, 405` sorts recorded tuples by (pile type, original index) so a
multi-card transform re-inserts deterministically; neither sim transform path sorts,
because both are single-card verbs. Trigger: porting any multi-card transform.

### `creature_card_cmds/N9` — the sim has no Play pile  [DORMANT] [unpinned]

- **open sites** 2: `creature_card_cmds/N9` (dormant), `creature_card_cmds/step82` (dormant)

C# holds a card being played in `PileType.Play` for the whole of `OnPlay`
(`CardPileCmd.cs:669-670`, `CardCmd.cs:114-117`) and `Shuffle` reads only Draw and
Discard (`CardPileCmd.cs:870-871`) — the entire mechanism behind the exoskeleton
reshuffle parity fact. The sim appends the played card to the **discard** pile and
holds it back from a reshuffle **in parity mode only** (`player.py:203, 232`),
because legacy RL runs are kept byte-for-byte. Residual exposure: an effect that
counts the discard pile during its own `OnPlay` sees the resolving card in the sim
and not in the game.

## 2F. Monster tier

### `monster/knowledge_demon/g1` — the curse's power is applied by the wrong creature  [DORMANT] [unpinned]

- **open sites** 1: `monster/knowledge_demon/g1` (dormant)
- **state** The applier half is fixed (`applier=player`, per all four curse
  cards' C#). The card-SOURCE half stays open: `PowerCmd.apply` and `Power`
  model no source parameter anywhere -- an architecture-wide absence that
  belongs to `power_cmd`.
- **divergence** In the game the curse card applies its own power with the
  **player** as applier and the card as the source (`Disintegration.cs:25-28`,
  `MindRot.cs:25-28`, `Sloth.cs:25-28`, `WasteAway.cs:28-31`); the port applies
  it with the demon as applier.
- **dormancy** No ported listener distinguishes the applier on these four powers.
- **trigger** Any listener that gates on applier identity for a curse-applied
  power — `PowerCmd.Apply`'s `applier` is not decoration: a null or wrong applier
  skips the `Hook.ModifyPowerAmountGiven` pass and changes
  `FindExistingInstanceForStacking`'s key.

---

# Tier 3 — the long tail

One row per remaining mechanism, generated from the records. They are real,
recorded and verified — they are rows rather than sections because a
single-unit finding is cheaper to read in its own record than restated. The id
is the path: `power/aggression/…` is `audit/records/power/aggression.json`.

**Line numbers are stripped from these summaries on purpose**, so that
`cite-check` stays a check on the authored prose above rather than a
re-validation of record excerpts.

## Seam remainder — 9 mechanisms

- `creature_card_cmds/guard26` — DORMANT — `NoUpgradeRoll` census, closed to one residue.
  Round 14 finished the sweep the record's own text calls "F-R13d,
  CLASS-WIDE": every non-combat `CardCreationOptions` site in the
  single-character sim now either correctly carries `NoUpgradeRoll` or
  correctly does not, verified by citation against each site's own C#
  factory method (not swept blindly — Orrery and Lasting Candy use the raw
  constructor and genuinely take the roll). The one line left open:
  `relics/sea_glass.py` uses `ForNonCombatWithUniformOdds` (the flag DOES
  apply in C#) but the sim only models this relic as an RNG-cost stub
  (cross-character card generation, out of scope) — its 1-draw-per-card
  cost is already the `NoUpgradeRoll` shape, so there is nothing left to
  change. **MISFILED, still:** this is a content-tier gap sitting on a seam
  record that cites none of its C#; it was live last round and is dormant
  now, but rehoming it to a `relic/` record is still someone's job.
- `creature_card_cmds/G4` — DORMANT — sites `/G4` — G4 (dormant) -- CreatureCmd.heal refuses to heal a dead creature; C#'s Heal revives — CORRECTED. The equivalence this closure rests on is FALSE, not imprecise: `combat.is…
- `hook_dispatch/G8` — DORMANT — sites `/step46` — 46. The sim has no phase concept, no preventer for most predicates, no Contains re-check, no IsOverOrEnding gate, no per-listener choice context, and no run-level HookSys…
- `hook_dispatch/guard11` — DORMANT — sites `/guard11` — F-R13b: can_receive_powers and _combat_contains_creature read the eager removal PREDICTION — gave Monster a `combat_removal_committed` EVENT flag set at C#'s actual Comba…
- `power_cmd/N4` — DORMANT — sites `/step4` — 4. Branch: no existing instance -> new-power Apply(...) pipeline (steps 6-23); existing instance -> ModifyAmount(...) pipeline (steps 24-37), nulling the result if it ret…
- `power_cmd/step21` — DORMANT — sites `/step21` — 21. Guard givenModifiers!=null: await Hook.AfterModifyingPowerAmountGiven(combatState, givenModifiers, power) (PowerCmd.cs; Hook.cs) — Re-scoped, verdict UNCHANGED (still…
- `turn_structure/G7` — DORMANT — sites `/step63` — 63. `await Hook.AfterFlush(state, player, ctx, cardsToFlush, cardsToRetain)` -- UNCONDITIONAL, fired even when nothing was flushed -- then PlayerCombatState.EndOfTurnClea…
- `turn_structure/guard23` — DORMANT — sites `/guard23` — G-R8: `Relic._check_win()` (relics/base.py) has the win/loss tie-break BACKWARDS -- the FIFTH site of the class G13's close note says it eliminated at four. — DIVERGENCE:…

## `power` — 98 mechanisms

- `power/artifact/TryModifyPowerAmountReceived` — DORMANT — The interception is reimplemented outside the hook system entirely, and the debuff test is the wrong one. C# (ArtifactPower.cs) is a TryModifyPowerAmountReceived listener whose three guards are `target != Owner`, `canonicalPower.G…
- `power/buffer/ModifyHpLostAfterOstyLate` — DORMANT — The arithmetic is exact -- 0 for the owner, unchanged otherwise (BufferPower.cs vs powers.py) -- and the AFTER-Osty position is right, since cmds.py runs after block absorption (:74-81). What is lost is the LATE half, and BufferPo…
- `power/burrowed/AfterRemoved` — DORMANT — C#'s AfterRemoved is `CreatureCmd.LoseBlock(oldOwner, 999999999m)` -- dump ALL the block -- and it runs on EVERY removal path, including the automatic strip when the owner dies (CreatureCmd.cs then each power's AfterRemoved). The…
- `power/calamity/BeforeCardPlayed` — DORMANT — C# uses a TWO-HOOK LATCH the sim collapses into one. CalamityPower.cs records amountsForPlayedCards[card] = base.Amount at BeforeCardPlayed and:44 removes it at AfterCardPlayed, so (a) the Amount is SNAPSHOTTED at the start of the…
- `power/chains_of_binding/AfterCardDrawn` — DORMANT — Two divergences. (1) A DROPPED GUARD: C# requires `base.CombatState.CurrentSide == base.Owner.Side` (ChainsOfBindingPower.cs), so only cards drawn during the PLAYER's own turn are Bound; the sim has no side test (powers.py), so a…
- `power/chains_of_binding/BeforeCardPlayed` — DORMANT — WRONG SIDE OF THE PLAY, the same shape as SlothPower's: C# sets `boundCardPlayed` in BeforeCardPlayed (ChainsOfBindingPower.cs) and the sim sets it in on_card_played, after resolution -- while the sim's `before_card_played` slot (…
- `power/crab_rage/g1` — DORMANT — CrabRagePower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner,..., base.Owner, null)`); the sim omits it, so `applier` is None through hooks.modify_po…
- `power/crimson_mantle/g3` — DORMANT — CrimsonMantlePower.cs fires the damage UNCONDITIONALLY — C# calls CreatureCmd.Damage with the DamageVar's BaseValue every turn, including the first, when the value is 0; powers.py guards on `if self.self_damage > 0`. A 0-damage Cr…
- `power/cruelty/g2` — DORMANT — CrueltyPower.cs `target == base.Owner` -> unmodified — Cruelty's self-exclusion is dropped by its consumer. Recorded in full on power/vulnerable's matching guard -- the sim reads Cruelty's amount with no such test, so a Cruelty ho…
- `power/cruelty/g4` — DORMANT — CrueltyPower.cs `amount + base.Amount / 100m` — The arithmetic is right and the TYPE is not: powers.py computes `mult += cruelty.amount / 100.0` in float where C# uses decimal. `1.5 + n/100` is non-dyadic for most n (10 -> 1.6, 30…
- `power/curious/g2` — DORMANT — CuriousPower.cs,32 the TryModify predicate protocol — C#'s Try* hooks are a predicate chain: the listener returns bool to say 'I changed it' and writes the new value to an out-param, and Hook.ModifyEnergyCostInCombat (Hook.cs) use…
- `power/curl_up/AfterCardPlayed` — DORMANT — NARROWED: this entry's own premise was stale. It was written to say the sim has AfterCardPlayed's whole job missing ("the block and the removal moved into AfterDamageReceived"), but that was the PRE-round-7 sim -- the AfterDamageR…
- `power/dampen/AfterApplied` — DORMANT — Two findings. (1) MECHANISM, the same substitution as illusion's: C#'s AfterApplied runs after PowerCmd registers the power; the sim does the work in __init__, i.e. inside `power_cls(...)` at cmds.py and therefore BEFORE hooks.reg…
- `power/dampen/AfterDeath` — DORMANT — C# tracks a SET of casters (`Data.casters`, added through the public non-override `AddCaster`, DampenPower.cs/73-76) and removes the power only when the LAST caster dies (`casters.Remove(creature); if (casters.Count == 0) PowerCmd…
- `power/dampen/g3` — DORMANT — DampenPower.cs public void AddCaster(Creature) — A public non-override method, so the harness does not enumerate it -- recorded so a reader does not think it was skipped (the same courtesy the main report gives CrueltyPower.Modify…
- `power/dark_shackles/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs,:141-144, consumed at:148-151 and:162-165) has NO sim counterpart at all. Its one caller is M…
- `power/dark_shackles/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 di…
- `power/dexterity/ModifyBlockAdditive` — DORMANT — The sim keys the ownership test on the BLOCK TARGET where C# keys it on the CARD's owner. DexterityPower.cs: when cardSource != null the test is `cardSource.Owner.Creature != base.Owner -> 0m` and the target is not consulted at al…
- `power/dexterity/g2` — DORMANT — Sign-aware power typing on a negative Dexterity application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGAT…
- `power/disintegration/AfterSideTurnEndLate` — DORMANT — Wrong slot AND lost phase, and it is the only power in this group with both. (a) PHASE: this is `AfterSideTurnEndLate`, the second complete pass Hook.AfterTurnEnd runs (Hook.cs), so in the game Disintegration's damage lands after…
- `power/draw_cards_next_turn/ModifyHandDraw` — DORMANT — The count is right (count + Amount, DrawCardsNextTurnPower.cs vs powers.py -- and correctly NOT the flat +1 that its sibling power/clarity uses; the two classes exist precisely to differ here, ClarityPower.cs). The GUARD is missin…
- `power/feeding_frenzy/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs,:141-144, consumed at:148-151 and:162-165) has NO sim counterpart at all. Its one caller is M…
- `power/feeding_frenzy/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 di…
- `power/flame_barrier/AfterSideTurnEnd` — DORMANT — The removal condition is inverted from a side comparison into a hard-coded side. FlameBarrierPower.cs removes the power whenever `base.Owner.Side != side` -- i.e. at the end of the turn belonging to the side the owner is NOT on, w…
- `power/flex_potion/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the wrapper's…
- `power/flex_potion/g5` — DORMANT — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; Rend,…
- `power/free_attack/g4` — DORMANT — The TryModify predicate protocol — C#'s Try* hooks return bool and write to an out-param, which Hook.ModifyEnergyCostInCombat (Hook.cs) uses to build its notification list; the sim's modify_card_energy_cost (hooks.py) is a plain f…
- `power/galvanic/AfterCardPlayed` — DORMANT — **PROPS.** C# deals the Galvanized damage with `ValueProp.Unpowered | ValueProp.Move` (GalvanicPower.cs); the sim passes `DamageProps.NON_CARD_UNPOWERED`, which valueprops.py defines as `UNPOWERED` **alone** -- the MOVE flag is mi…
- `power/galvanic/BeforeCombatStart` — DORMANT — Right slot -- combat.py fires on_combat_start immediately before `start_turn()` at:209, which turn_structure identifies as the sim's BeforeCombatStart. The divergence is an ADDED GUARD (recurring shape 8): C# afflicts EVERY Power…
- `power/gigantification/AfterAttack` — DORMANT — The slot is right (combat.py, immediately after the card's on_play inside the play-count loop). The GAP is the IDENTITY the latch is cleared against: C# compares ATTACK-COMMAND identity (`command == internalData.commandToModify`,…
- `power/hardened_shell/ModifyHpLostBeforeOstyLate` — DORMANT — The FORMULA is exact -- `target != Owner -> amount`, `amount == 0 -> amount`, else `Math.Min(amount, Amount - damageReceivedThisTurn)` (HardenedShellPower.cs) vs powers.py -- and the BeforeOsty/AfterOsty phase collapse is already…
- `power/heist/BeforeDeath` — DORMANT — HOOK-PHASE MISMATCH -- a BEFORE hook ported onto an AFTER hook, the recurring shape section 0 item 5 of the stream report names for thorns/curl_up/skittish/suck, now in a death-time form. C# calls Hook.BeforeDeath UNCONDITIONALLY…
- `power/hello_world/g1` — DORMANT — HelloWorldPower.cs base.AmountOnTurnStart >= 1 (used as BOTH the guard and the card count) — The guard is ported as self.amount < 1 (powers.py) and the count as self.amount (:2825), where C# uses base.AmountOnTurnStart for both (H…
- `power/hellraiser/AfterSideTurnEnd` — DORMANT — HellraiserPower.cs resets the per-turn infinite-auto-play counter. The sim tracks no counter (see the AfterCardDrawnEarly entry), so there is nothing to reset. Dormant for the same reason and with the same trigger; carried separat…
- `power/high_voltage/g1` — DORMANT — HighVoltagePower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` as the applier (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)`); the sim calls `PowerCmd.apply(self.…
- `power/high_voltage/g2` — DORMANT — HighVoltagePower.cs `participants.Contains(base.Owner)` — The sim substitutes `if not self.owner.is_dead` (powers.py) -- recurring gap shape 8, a guard the sim changes rather than drops. The two are not the same predicate: a corps…
- `power/illusion/g1` — DORMANT — IllusionPower.cs FollowUpStateId — A public settable property with no sim analogue: it lets an applier choose which state the revived creature resumes on, defaulting to the last LOGGED state. Folded into the AfterDeath entry; carr…
- `power/inferno/g4` — DORMANT — InfernoPower.cs CombatState.HittableEnemies — The sim iterates `combat.enemies` filtered on `not enemy.is_gone` (powers.py) where C# uses HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). So the s…
- `power/intangible/g1` — DORMANT — IntangiblePower.cs `!CombatManager.Instance.IsInProgress` -> unmodified — The sim has no combat-phase guard on any modifier hook. This is the power-level face of audit/records/seam/power_cmd.json's structural gap G6 (no IsEnding/C…
- `power/juggernaut/g2` — DORMANT — JuggernautPower.cs CombatState.HittableEnemies and the empty check — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Cre…
- `power/juggling/AfterCardPlayed` — DORMANT — The copy is rebuilt from the class rather than cloned. JugglingPower.cs is `cardPlay.Card.CreateClone()`, which reproduces the card's full live state; powers.py constructs `type(card)()` and replays `card.upgrade_level` upgrades o…
- `power/mangle/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs,:141-144, consumed at:148-151 and:162-165) has NO sim counterpart at all. Its one caller is M…
- `power/mangle/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 di…
- `power/nemesis/g1` — DORMANT — NemesisPower.cs `participants.Contains(base.Owner)` — Replaced by `if self.owner.is_dead: return` (powers.py) -- the same substitution as HighVoltage's and Territorial's, and one degree worse here, because the sim's early return a…
- `power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath` — DORMANT — NARROWED. The retention observable is closed -- the sim's death-prevention arm now leaves the creature dead at 0 HP with `retained_after_death = True` (cmds.py) -- but this power still does not implement `should_remove_from_combat…
- `power/painful_stabs/g1` — DORMANT — PainfulStabsPower.cs the three AfterAttack guards — RE-OPENED. Two of the three early-return conditions map; the THIRD does not, and the AfterAttack hook entry in this record already says so ("NOTE this record's guard on 'the thre…
- `power/panache/AfterCardPlayed` — DORMANT — The sim iterates `combat.enemies` filtered on `not enemy.is_gone` where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). The sim therefore aims at creatures the game considers…
- `power/plow/AfterDamageReceived` — DORMANT — Right hook and right slot; the threshold matches exactly (`target != base.Owner || result.UnblockedDamage <= 0 || target.CurrentHp > base.Amount -> return`, PlowPower.cs, vs powers.py). Three divergences. (1) The sim ADDS `self.ow…
- `power/poison/AfterSideTurnStart` — DORMANT — STILL OPEN at (b) and (c). Clause (a), the SLOT, is CLOSED: PoisonPower.cs declares AfterSideTurnStart and the power is on the new `after_side_turn_start` dispatcher (CombatManager.cs), post-draw, so the tick no longer lands befor…
- `power/rampart/g3` — DORMANT — RampartPower.cs `base.CombatState.Enemies.Where(c => c.Monster is TurretOperator)` — powers.py adds `and not enemy.is_gone` (recurring gap shape 8, a guard the sim ADDS). C#'s CombatState.Enemies is the raw participant list and a…
- `power/ravenous/AfterDeath` — DORMANT — The guards are exact -- `target != base.Owner && target.Side == base.Owner.Side && !base.Owner.IsDead` (RavenousPower.cs) maps line-for-line to powers.py -- and the effect order matches (stun the owner, then grant Strength). Two d…
- `power/ravenous/g1` — DORMANT — RavenousPower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner,..., base.Owner, null)`); the sim omits it, so `applier` is None through hooks.modify_po…
- `power/reptile_trinket/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs,:141-144, consumed at:148-151 and:162-165) has NO sim counterpart at all. Its one caller is M…
- `power/reptile_trinket/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 di…
- `power/rolling_boulder/g2` — DORMANT — RollingBoulderPower.cs CombatState.HittableEnemies (TestMode arm) — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowH…
- `power/sandpit/AfterRemoved` — DORMANT — The EFFECT is right and the MECHANISM is not. C#'s AfterRemoved (SandpitPower.cs) returns early on `oldOwner.IsDead || base.Target.IsDead`, hides the affected creatures, and `CreatureCmd.Kill(..., force: true)` every one that IsPl…
- `power/setup_strike/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs,:141-144, consumed at:148-151 and:162-165) has NO sim counterpart at all. Its one caller is M…
- `power/setup_strike/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 di…
- `power/shackling_potion/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs,:141-144, consumed at:148-151 and:162-165) has NO sim counterpart at all. Its one caller is M…
- `power/shackling_potion/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 di…
- `power/shrink/AfterDeath` — DORMANT — The `wasRemovalPrevented` guard is missing. ShrinkPower.cs removes Shrink only when `!wasRemovalPrevented && creature == base.Applier`; the sim tests only `creature is self.applier` (powers.py). A prevented removal (a death whose…
- `power/shrink/AfterSideTurnEnd` — DORMANT — Two divergences in one hook. (a) The `!IsInfinite` guard (ShrinkPower.cs, i.e. Amount >= 0) is spelled `self.amount > 0` on both sim legs (powers.py,1394); those agree only because Amount == 0 is unreachable (ShouldRemoveDueToAmou…
- `power/shrink/AllowNegative` — DORMANT — ShrinkPower.cs declares `AllowNegative => true`; the sim's ShrinkPower never sets allow_negative, so it inherits False from Power (powers.py). That changes ShouldRemoveDueToAmount (PowerModel.cs): C# removes an AllowNegative power…
- `power/skittish/AfterSideTurnEnd` — DORMANT — NARROWED. THE SLOT HALF IS CLOSED: the reset is now `after_player_turn_end` (powers.py), the sim's Hook.AfterTurnEnd slot (combat.py / CombatManager.cs). WHAT REMAINS is the side test: SkittishPower.cs acts only when `side != base…
- `power/slippery/ModifyHpLostAfterOsty` — DORMANT — The formula is exact: `target != base.Owner -> amount`, `amount < 1m -> amount`, else `1m` (SlipperyPower.cs) vs powers.py. The BeforeOsty/AfterOsty phase collapse is already resolved as faithful by damage_pipeline (Osty redirecti…
- `power/sloth/BeforeCardPlayed` — DORMANT — WRONG SIDE OF THE PLAY. C# increments the counter in `BeforeCardPlayed` (SlothPower.cs), i.e. before the card resolves; the sim increments in `on_card_played`, after. The sim HAS the right slot -- `before_card_played` (combat.py),…
- `power/slow/ModifyDamageMultiplicative` — DORMANT — The factor matches (`1m + 0.1m * SlowAmount` at SlowPower.cs vs `1.0 + 0.1 * self._cards_this_turn` at powers.py) and `target != base.Owner -> 1m` matches, but the POWERED test does not: C# is `props.IsPoweredAttack()` (SlowPower.…
- `power/speed_potion/g4` — DORMANT — TemporaryDexterityPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the wrapper'…
- `power/speed_potion/g5` — DORMANT — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; Rend,…
- `power/speed_potion/g8` — DORMANT — The Dexterity leg's own observable consequence, as distinct from the family's slot verdict — RE-DERIVED (review fix pass). Stated separately so the AfterSideTurnEnd verdict above is not read as more proven than it is, and re-label…
- `power/strength/g3` — DORMANT — Sign-aware power typing on a negative Strength application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGATI…
- `power/suck/g2` — DORMANT — Counting GROUPS with unblocked damage, not individual results — C#'s `num` counts outer lists (per-hit result groups) in which ANY result had unblocked damage, so a single AoE hit that connects with three creatures counts 1. The s…
- `power/surprise/AfterDeath` — DORMANT — Right hook and the right two spawns (`CreatureCmd.Add<SneakyGremlin>` then `<FatGremlin>`, SurprisePower.cs, vs powers.py in the same order, which matters because it fixes the enemy-list indices). The gap is the THIEVERY TRANSFER.…
- `power/surrounded/AfterDeath` — DORMANT — The logic matches SurroundedPower.cs -- skip when the dead creature is on the owner's own side, then, if every remaining hittable enemy carries the SAME marker power, re-face on hittableEnemies[0] -- but the sim reads `[e for e in…
- `power/surrounded/ModifyDamageMultiplicative` — DORMANT — The arithmetic and the facing logic are exact -- `dealer == null -> 1m`, `target != base.Owner -> 1m`, then 1.5x only if the dealer holds the marker power OPPOSITE the facing (SurroundedPower.cs vs powers.py), and 1.5 is dyadic so…
- `power/surrounded/g1` — DORMANT — SurroundedPower.cs `!wasRemovalPrevented` — Absent from powers.py, which tests only the side. C# skips the re-facing entirely when a death's REMOVAL was prevented (the creature is still there, so the board did not change); the sim…
- `power/swipe/BeforeDeath` — DORMANT — HOOK SLOT: C# is `BeforeDeath`, fired at CreatureCmd.cs **before** `Hook.ShouldDie` and therefore before any death prevention; the sim uses `hooks.on_death`, fired at cmds.py only on the branch where should_die returned True. Two…
- `power/tender/AfterCardPlayed` — DORMANT — The applier is dropped. TenderPower.cs applies Strength and Dexterity -1 with `applier: base.Applier` -- the creature that applied Tender -- and `silent: true`; powers.py calls PowerCmd.apply with no applier at all. DORMANT but wi…
- `power/tender/AfterSideTurnEnd` — DORMANT — NARROWED, RE-OPENED: the SLOT fix landed, the APPLIER defect this entry used to carry verbatim did not, and the flip dropped its text. CLOSED (the slot): the player-side leg moved off the sim's Hook.BeforeTurnEnd slot (`on_player_…
- `power/territorial/g1` — DORMANT — TerritorialPower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` as the applier (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)`); the sim calls `PowerCmd.apply(self.…
- `power/territorial/g2` — DORMANT — TerritorialPower.cs `participants.Contains(base.Owner)` — Same substitution as HighVoltagePower's: the sim tests `not self.owner.is_dead` (powers.py) where C# tests side participation, which a retained corpse still satisfies. Iden…
- `power/the_bomb/g2` — DORMANT — TheBombPower.cs /:56 CombatState.HittableEnemies — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs), so the…
- `power/unmovable/ModifyBlockMultiplicative` — DORMANT — NARROWED. DIVERGENCE (b) IS CLOSED: `on_card_played` now fires once per replay iteration (combat.py, inside `for play_index in range(play_count)`), so a doubled block card consumes the allowance twice, matching UnmovablePower.cs's…
- `power/vigor/ModifyDamageAdditive` — DORMANT — The sim keeps only the FIRST of C#'s four guards. C# (VigorPower.cs) tests, in order: base.Owner != dealer (present, powers.py), !props.IsPoweredAttack() (present structurally -- cmds.py only runs the additive family for powered d…
- `power/vital_spark/AfterPowerAmountChanged` — DORMANT — C# re-syncs every Tainted affliction's Amount to the power's new Amount from `AfterPowerAmountChanged` with a `power != this` guard (VitalSparkPower.cs), so it fires on ANY amount change -- a stack, a decrement, or an Unsettling-L…
- `power/vital_spark/AfterRemoved` — DORMANT — C#'s AfterRemoved clears every Tainted affliction on EVERY removal path (VitalSparkPower.cs, guarded by `oldOwner.CombatState == null`); the sim hangs the same sweep on `on_death` filtered to the owner (powers.py) and then calls `…
- `power/vital_spark/BeforeCombatStart` — DORMANT — STAYS OPEN, DORMANT -- reasoning REPLACED ENTIRELY. The record's stated mechanism was wrong: CardCmd.Afflict (CardCmd.cs) does NOT overwrite. It refuses a different-type affliction via CanAfflict (AfflictionModel.cs, which the sim…
- `power/vulnerable/ModifyDamageMultiplicative` — DORMANT — The base multiplier and both ported modifiers are right, but the value is computed in FLOAT where C# uses DECIMAL, which puts this hook inside hook_dispatch gap G9's blast radius. C# reads DamageIncrease = 1.5m from the DynamicVar…
- `power/vulnerable/g3` — DORMANT — CrueltyPower.cs `target == base.Owner` -> unmodified — Cruelty's own self-exclusion is dropped. C# skips the Cruelty bonus when the Vulnerable target IS the Cruelty holder; powers.py reads `dealer.powers.get('cruelty')` with no su…
- `power/vulnerable/g4` — DORMANT — VulnerablePower.cs DebilitatePower leg — DebilitatePower is not ported (`grep -c DebilitatePower sts2_rl/powers.py` returns 0), so the third link of C#'s modifier chain has no sim counterpart. Per binding rule 1 an unported C# sid…
- `power/weak/ModifyDamageMultiplicative` — DORMANT — The sim returns the bare literal 0.75 and has no modifier chain at all, where WeakPower.cs threads DamageDecrease = 0.75m through PaperKrane (the TARGET's relic, -0.15m) and then DebilitatePower. Neither is ported -- `ls sts2_rl/r…
- `power/withering_presence/AfterCardPlayed` — DORMANT — The mechanism is right -- count the target player's card plays down from 6, add a Wither to HAND at 0, reset to 6 -- and the Wither's upgrade matching is preserved (`aeonglass.MatchWitherToUpgradeCount(wither)` at WitheringPresenc…

## `card` — 30 mechanisms

- `card/anointed/g2` — DORMANT — cards are moved to the hand with CardPileCmd.Add(cards, PileType.Hand) (Anointed.cs) vs direct list mutation — The sim pops each card out of `player.draw_pile` and appends to `player.hand` in place (colorless_skills.py) instead of…
- `card/apotheosis/g1` — DORMANT — the `allCard != this` self-exclusion, and whether the two AllCards sets are the same set (Apotheosis.cs) — C# `PlayerCombatState.AllCards` is `AllPiles.SelectMany(p => p.Cards)` (PlayerCombatState.cs) over Hand, Draw, Discard, Exh…
- `card/beat_down/g2` — DORMANT — target selection for AnyEnemy attacks: C# rolls `Rng.CombatTargets.NextItem(CombatState.HittableEnemies)` in BeatDown itself and passes it to AutoPlay; the sim lets `auto_play_card` roll (BeatDown.cs) — The stream is right on both…
- `card/breakthrough/g1` — DORMANT — the enemy loop skips on `enemy.is_dead`, not `enemy.is_gone` (breakthrough.py) — Every other AoE card in the sim filters on `not e.is_gone` (conflagration, shockwave, omnislice, sword_boomerang, rip_and_tear -- see `py audit/tools…
- `card/brightest_flame/g1` — DORMANT — CROSS-RECORD DISAGREEMENT (rule 3): CreatureCmd.LoseMaxHp(..., isFromCard: true) is seam gap G6, which labels itself DORMANT; this card makes it LIVE — The seam's VERDICT (`gap`) is not disputed and is not re-verdicted here -- onl…
- `card/conflagration/OnPlay` — DORMANT — Damage per hit, hit count, target set and the OUTER loop order are all faithful: `DamageCmd.Attack(2).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState)` (Conflagration.cs) runs `for (i = 0; i < attackCount; i++)` w…
- `card/crimson_mantle/g1` — DORMANT — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (CrimsonMantle.cs vs crimson_mantle.py) — `PowerCmd.Apply<T>` returns null in three documented cases (PowerCmd.cs, 68-87): comb…
- `card/dramatic_entrance/OnPlay` — DORMANT — The damage, the target set and the single hit are all faithful: `DamageCmd.Attack(11).FromCard(this).TargetingAllOpponents(CombatState)` (DramaticEntrance.cs) hits every living opponent once, and the sim's framework routing calls…
- `card/enlightenment/g1` — DORMANT — `reduceOnly` is evaluated LAZILY at cost-calculation time, so C# registers the modifier on EVERY hand card including those already at cost 0 or 1; the sim `continue`s past them (Enlightenment.cs vs event_cards.py) — `LocalCostModi…
- `card/expect_a_fight/g1` — DORMANT — the sim skips the gain entirely when there are no Attacks in hand (`if attacks > 0`, expect_a_fight.py); C# calls GainEnergy(0) — `PlayerCmd.GainEnergy(0,...)` (ExpectAFight.cs) adds nothing but still runs the engine's gain path;…
- `card/exterminate/OnPlay` — DORMANT — Damage per hit, hit count, target set and the hits-outer/enemies-inner loop order are all faithful against `DamageCmd.Attack(3).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState)` (Exterminate.cs) -- AttackCommand r…
- `card/havoc/g2` — DORMANT — `forceExhaust: true` is reproduced by appending to the exhaust pile directly (havoc.py) — C# sets `item.ExhaustOnNextPlay = forceExhaust` (CardPileCmd.cs) and lets the play pipeline route the card to the exhaust pile, which means…
- `card/howl_from_beyond/OnPlay` — DORMANT — The damage and the single hit per enemy are faithful against `DamageCmd.Attack(16).FromCard(this).TargetingAllOpponents(CombatState)` (HowlFromBeyond.cs), and leaving `handles_own_routing` False is correct for a one-hit AoE -- the…
- `card/inferno/g1` — DORMANT — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (Inferno.cs vs inferno.py) — Identical to card/crimson_mantle's guard and carrying the same verdict (rule 3): `PowerCmd.Apply<T…
- `card/lantern_key/ModifyNextEvent` — DORMANT — `if (2 != Owner.RunState.CurrentActIndex) return currentEvent; return ModelDb.Event<WarHistorianRepy>();` (LanternKey.cs) redirects the next act-3 event to War Historian Repy -- the payoff the Lantern Key quest exists for. The sim…
- `card/mad_science/GainsBlock` — DORMANT — `public override bool GainsBlock => TinkerTimeType == CardType.Skill` (MadScience.cs) is TYPE-DEPENDENT, and the sim never sets `gains_block` at all -- not in the class body and not in `configure` (mad_science.py, which sets `card…
- `card/neows_fury/OnPlay` — DORMANT — Attack first, then the hand-size-capped selection: `Math.Min(Cards.IntValue, CardPile.MaxCardsInHand - Hand.Cards.Count)` (NeowsFury.cs) == `min(self._cards, PlayerCombatState.MAX_HAND_SIZE - len(ctx.player.hand))`, with both skip…
- `card/neows_fury/g1` — DORMANT — the chosen cards are moved with `CardPileCmd.Add(list, PileType.Hand)` in C# (NeowsFury.cs) and by direct list mutation in the sim (neows_fury.py) — The sim pops the chosen cards out of `player.discard_pile` and appends them to `p…
- `card/omnislice/g1` — DORMANT — the sim returns early when nothing got through (`if dealt <= 0: return`, colorless_attacks.py); C# proceeds whenever the DamageResult is non-null (Omnislice.cs) — C# proceeds whenever the DamageResult is non-null (Omnislice.cs) an…
- `card/pacts_end/OnPlay` — DORMANT — The gate and the damage are faithful: `CanDealDamage` is `CardPile.GetCards(Owner, PileType.Exhaust).Count() >= Cards.IntValue` (PactsEnd.cs) == `if len(ctx.player.exhaust_pile) < self._required_exhausted: return`, and the whole p…
- `card/pillage/g1` — DORMANT — the sim identifies the drawn card as `player.hand[-1]` (pillage.py) where C# uses the value the single-card Draw overload returns — C#'s single-card `CardPileCmd.Draw` overload RETURNS the card it drew (Pillage.cs) and the type te…
- `card/primal_force/OnPlay` — DORMANT — The candidate set, the per-card upgrade and the index-preserving replacement are all faithful. C# selects `Hand.Cards.Where(c => c != null && c.IsTransformable && c.Type == CardType.Attack)` (PrimalForce.cs) and the sim's `if card…
- `card/purity/OnPlay` — DORMANT — The candidate set and the effect are faithful: `CardSelectCmd.FromHand(..., filter: null, source: this)` over the whole hand then `CardCmd.Exhaust` on each (Purity.cs) == `CardSelectCmd.from_hand(ctx.hooks, ctx.player, 'exhaust',…
- `card/rend/g1` — DORMANT — the ITemporaryPower exclusion is approximated by a single class (colorless_attacks.py) — C#'s `ShouldCountPower` is `power.TypeForCurrentAmount == PowerType.Debuff && !(power is ITemporaryPower)` (Rend.cs). The sim reproduces the…
- `card/stomp/OnPlay` — DORMANT — The damage, the single hit per enemy and the target set are faithful against `DamageCmd.Attack(12).FromCard(this).TargetingAllOpponents(CombatState)` (Stomp.cs), and leaving `handles_own_routing` False is correct for a one-hit AoE…
- `card/the_bomb/g1` — DORMANT — C# dereferences the Apply result WITHOUT a null check; the sim re-fetches by id and skips on None (TheBomb.cs vs colorless_skills.py) — This is the INVERSE of card/crimson_mantle's and card/inferno's `?.` finding: those two use th…
- `card/thunderclap/OnPlay` — DORMANT — The TWO-PASS structure is faithful and is the point of the card: C# resolves the whole attack first (`DamageCmd.Attack(4).FromCard(this).TargetingAllOpponents(CombatState)`, Thunderclap.cs) and only then applies Vulnerable to `Com…
- `card/thunderclap/g1` — DORMANT — the sim `continue`s rather than breaking when an enemy is gone in the damage pass, and re-checks `ctx.player.is_dead` between the passes (thunderclap.py) — Two behaviours are bundled here and only one is the source's. C#'s AttackC…
- `card/toric_toughness/g1` — DORMANT — C# skips SetBlock when Apply returns NULL via `?.`; the sim re-fetches by id and skips on None (ToricToughness.cs vs event_cards.py) — Same mechanism and same verdict as card/crimson_mantle's and card/inferno's guards (rule 3): `P…
- `card/whirlwind/OnPlay` — DORMANT — The X-value plumbing, the hit count and the hits-outer/enemies-inner loop order are all faithful: `WithHitCount(ResolveEnergyXValue())` on `TargetingAllOpponents(CombatState)` (Whirlwind.cs, 42-45) == `for _ in range(self.captured…

## `event` — 8 mechanisms

- `event/EV-11` — DORMANT — EV-11: BARGAIN_BIN's Common pull (WelcomeToWongos.cs) and GenerateInitialOptions' Rare pull (:80) calls run.pull_relic_from_front (run.py), which scans the merged bag for the first relic of the asked rarity passing the filter and,…
- `event/crystal_sphere/CalculateVars` — DORMANT — SETTLED. This entry's own text said it inherits the DEFERRED-PORT guard's verdict; the brief for this pass asked which of two readings is correct -- 'the event is stubbed off, so the sub-entries are dormant' or 'the stub itself is…
- `event/hungry_for_mushrooms/g3` — DORMANT — BigMushroom's +20 Max HP pickup effect is implemented on the EVENT, not on the relic. BigMushroom.cs AfterObtained calls CreatureCmd.GainMaxHp(MaxHpVar 20) — relics/big_mushroom.py has NO after_obtained override -- only modify_han…
- `event/neow/g8` — DORMANT — the RUN MODIFIERS branch is not ported. Neow.cs is a whole second mode: when RunState.Modifiers is non-empty the relic offer is REPLACED by one option per modifier that returns a GenerateNeowOption delegate, presented one at a tim…
- `event/ranwid_the_elder/g10` — DORMANT — BR-relic_trader (blast radius): the grab-bag-runs-dry state. RanwidTheElder.cs,:121 and:131 call `RelicFactory.PullNextRelicFromFront(base.Owner).ToMutable()` with no null check at all, so an empty bag is an NRE in the source — AL…
- `event/relic_trader/g5` — DORMANT — GenerateInitialOptions gates each option on `OwnedRelics.Count` ALONE (RelicTrader.cs), and Trade then indexes NewRelics at the same position (RelicTrader.cs) — events/relic_trader.py gates on `min(len(self._owned), len(self._new)…
- `event/vakuu/g5` — DORMANT — UNIT GAP (dormant): Distinguished Cape's -9 Max HP is implemented on the EVENT OPTION instead of on the relic. DistinguishedCape.cs's AfterObtained() runs `CreatureCmd.LoseMaxHp(..., DynamicVars.HpLoss = 9, isFromCard: false)` and…
- `event/welcome_to_wongos/g8` — DORMANT — CheckObtainWongoBadge (WelcomeToWongos.cs) is not ported: the sim never grants WongoCustomerAppreciationBadge, and it tracks points on an ad-hoc attribute instead of run state — The badge is awarded when `SaveManager.Instance.Prog…

## `relic` — 146 mechanisms

- `relic/anchor/g3` — DORMANT — N3: ordering against other BeforeCombatStart listeners — C# grants Anchor's block at step 3 (Hook.BeforeCombatStart, before StartTurn); the sim grants it at step 14's equivalent (the AfterBlockCleared loop, well inside turn-1 setu…
- `relic/archaic_tooth/AfterObtained` — DORMANT — Rollup of guards G1 and G2 per binding rule 4. The transform itself is right -- first deck card whose id is a TranscendenceUpgrades key (ArchaicTooth.cs vs archaic_tooth.py), replaced via run.transform_card(into=) -- but the upgra…
- `relic/archaic_tooth/g1` — DORMANT — G1 (DORMANT): C# carries the upgrade with a single `if (starterCard.IsUpgraded) CardCmd.Upgrade(cardModel)` (ArchaicTooth.cs); the sim loops `for _ in range(original.upgrade_level)` (archaic_tooth.py) — C# grants exactly ONE upgra…
- `relic/archaic_tooth/g2` — DORMANT — G2 (DORMANT): the sim adds a `can_enchant(transformed)` condition C# does not have, and MOVES the enchantment instead of cloning it (archaic_tooth.py vs ArchaicTooth.cs) — C# clones the enchantment (`(EnchantmentModel)starterCard.…
- `relic/bag_of_marbles/BeforeSideTurnStart` — DORMANT — REASONING STRENGTHENED. Replaces the premise that `PowerCmd.apply` does not apply should_allow_hitting either, 'that absence being seam/power_cmd G6'. power_cmd/G6 was FIXED -- THREE DAYS AFTER this record's audit -- and the recor…
- `relic/bag_of_marbles/g2` — DORMANT — G2 (DORMANT): `combatState.HittableEnemies` (BagOfMarbles.cs) vs the sim's living_enemies() (bag_of_marbles.py) — C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHittin…
- `relic/bag_of_preparation/g1` — DORMANT — N1: the chain's out-parameter `modifiers` and the AfterModifyingHandDraw companion event (CombatManager.cs, turn_structure step 20) — C# collects which listeners changed the draw count and fires Hook.AfterModifyingHandDraw over th…
- `relic/belt_buckle/AfterObtained` — DORMANT — BeltBuckle.cs applies the Dexterity immediately if the relic is picked up DURING a combat with no potions held. The sim's port defines only on_combat_start and on_potion_used, so a Belt Buckle obtained mid-combat grants nothing un…
- `relic/belt_buckle/AfterPotionDiscarded` — DORMANT — The mirror of AfterPotionProcured: BeltBuckle.cs RE-APPLIES the Dexterity when discarding leaves the player potionless mid-combat. The sim implements on_potion_used but not a discard analogue, so the two ways of emptying the belt…
- `relic/bing_bong/AfterCardChangedPiles` — DORMANT — Rollup of guard G1 per binding rule 4. The core is right -- the deck-pile filter, the anti-recursion skip set, and the bottom-of-deck placement all match -- but C#'s `clonedBy == null` clause has no sim counterpart. DORMANT, RE-VE…
- `relic/booming_conch/AfterSideTurnStart` — DORMANT — STILL OPEN on the ENERGY-GAIN CHAIN only. The HOOK SLOT is CLOSED: BoomingConch.cs declares AfterSideTurnStart and the relic moved from the pre-draw slot to the new `after_side_turn_start` dispatcher (CombatManager.cs). WHAT REMAI…
- `relic/booming_conch/g2` — DORMANT — G2 (DORMANT): C# grants the energy through PlayerCmd.GainEnergy, which runs Hook.ModifyEnergyGain and Hook.AfterModifyingEnergyGain; the sim assigns player.energy directly (booming_conch.py) — MECHANISM: PlayerCmd.GainEnergy (Play…
- `relic/brilliant_scarf/TryModifyEnergyCostInCombatLate` — DORMANT — NARROWED. The phase half (G2) is CLOSED: the port now overrides `modify_card_energy_cost_late` (sts2_rl/relics/brilliant_scarf.py) and HookSystem._each runs the Late pass as its own complete walk (sts2_rl/hooks.py, 153-180). WHAT…
- `relic/brilliant_scarf/g3` — DORMANT — G3 (DORMANT): the sim's modify_card_energy_cost drops ShouldModifyCost's owner check and its Hand/Play pile check (BrilliantScarf.cs) — C# refuses to modify a cost unless the card's owner is the relic's owner AND the card is curre…
- `relic/byrdpip/AfterObtained` — DORMANT — Rollup of guards G1 and G3 per binding rule 4. The deck half of the Byrdonis Egg -> Byrd Swoop transform is faithful; the combat-pile half (G1) and the mid-combat SummonPet call (G3) are dropped. DORMANT overall -- both halves set…
- `relic/byrdpip/BeforeCombatStart` — DORMANT — Byrdpip.cs summons the pet at the start of EVERY combat. The port has no on_combat_start. Carries guard G3's verdict; see G3 for why the omission is observationally inert today. DORMANT, enumerated independently of G3's own four r…
- `relic/byrdpip/HasUponPickupEffect` — DORMANT — Byrdpip.cs declares `HasUponPickupEffect => true` and the sim's Relic base has the exact field for it (relics/base.py), which fourteen other ports set. Byrdpip leaves it at the False default. DORMANT (executed -- `py audit/tools/r…
- `relic/byrdpip/SpawnsPets` — DORMANT — Byrdpip.cs declares `SpawnsPets => true`; relics/base.py has the field and the port leaves it False. DORMANT, enumerated: `git grep -n spawns_pets sts2_rl/*.py sts2_rl/**/*.py` (excluding.pyc) returns exactly two non-declaration h…
- `relic/byrdpip/g1` — DORMANT — G1 (DORMANT): the transform covers the deck only, not the combat piles — Byrdpip.cs collects every ByrdonisEgg from the Deck pile and, `if (CombatManager.Instance.IsInProgress)`, ALSO from `Owner.PlayerCombatState.AllCards` -- i.e…
- `relic/charons_ashes/AfterCardExhausted` — DORMANT — REASONING REPLACED. The retired text claimed a `DamageCmd.deal` backstop (`if not hooks.should_allow_hitting(target): return 0`). THAT BACKSTOP DOES NOT EXIST -- the line is DEAD CODE, dominated by the `if target.is_dead: return 0…
- `relic/charons_ashes/g1` — DORMANT — G1 (DORMANT): `HittableEnemies` vs `living_enemies()` — One verdict per mechanism (binding rule 3): this is the same call-site divergence audit/records/relic/bag_of_marbles.json records as its guard G2, with the same verdict. C# t…
- `relic/claws/AfterObtained` — DORMANT — RE-REGENERATED and G5 is `deliberate-divergence`, not a gap -- neither is open any more). WHAT REMAINS is guard G2 alone, and it is still open: RE-VERIFIED against today's claws.py -- `after_obtained` still loops `for original in…
- `relic/claws/g2` — DORMANT — G2 (DORMANT): C# removes every original first and then appends the replacements in DECK-INDEX order; the sim removes and appends one card at a time in SELECTION order — MECHANISM: CardCmd.Transform(IEnumerable<CardTransformation>,…
- `relic/darkstone_periapt/AfterCardChangedPiles` — DORMANT — NARROWED. Rollup of guard G2 (DORMANT) per binding rule 4; G1's half is CLOSED. CLOSED (G1): the out-of-combat TRANSFORM path no longer writes the deck silently. sts2_rl/run.py runs Hook.ModifyCardBeingAddedToDeck over every relic…
- `relic/darkstone_periapt/g2` — DORMANT — G2 (DORMANT): C# fires AfterCardChangedPiles for a card entering PileType.Deck at ANY time, including mid-combat; the sim's after_card_added_to_deck exists only on the out-of-combat RunState.add_card path — MECHANISM: CardPileCmd.…
- `relic/daughter_of_the_wind/g2` — DORMANT — G2 (DORMANT): C# yields no listeners to a combat hook dispatched after the combat has started ending; the sim has no such gate, so a LETHAL Attack still grants its 1 Block — MECHANISM: Hook.IterateCombatHookListeners (Hook.cs) yie…
- `relic/demon_tongue/g2` — DORMANT — G2 (DORMANT): C# heals `result.UnblockedDamage`, which EXCLUDES OverkillDamage; the sim heals the raw `hp_lost`, which includes it — MECHANISM: DamageResult.cs documents UnblockedDamage as the damage the target received after bloc…
- `relic/dusty_tome/AfterObtained` — DORMANT — Rollup of guards G1 (the unguarded Card.upgrade, dormant), G2 (the lazy re-roll, LIVE on the runner path) and N2 (the added HasUponPickupEffect declaration) per binding rule 4. The core effect is faithful and executed: `run.add_re…
- `relic/dusty_tome/g1` — DORMANT — G1 (DORMANT): `CardCmd.Upgrade(card)` skips a card whose IsUpgradable is false (DustyTome.cs); dusty_tome.py's `card.upgrade()` is a bare `upgrade_level += 1` with no guard (PROMPT.md class 14) — MECHANISM: CardCmd.Upgrade filters…
- `relic/dusty_tome/g6` — DORMANT — N2: the sim ADDS `has_upon_pickup_effect = True` (dusty_tome.py) where DustyTome.cs declares no HasUponPickupEffect override — MECHANISM: RelicModel.HasUponPickupEffect defaults to false and DustyTome does not override it -- contr…
- `relic/electric_shrymp/g4` — DORMANT — N3: run.select_cards falls back to `self.rng.sample` when no card_selector is installed (run.py), where C# opens a player-choice screen and draws no RNG at all — PROMPT.md bug class 16's second half at an out-of-combat site: C#'s…
- `relic/ember_tea/g1` — DORMANT — G1 (DORMANT): C#'s AfterRoomEntered runs strictly BEFORE every BeforeCombatStart listener; the sim's on_combat_start runs interleaved with them in relic-registration order — MECHANISM: CombatRoom.cs calls CombatManager.SetUpCombat…
- `relic/empty_cage/AfterObtained` — DORMANT — Rollup of guard N2 per binding rule 4. The count (CardsVar(2), EmptyCage.cs, vs CARDS = 2, empty_cage.py), the candidate filter (N1) and the removal itself all match -- executed: a fresh run's 10-card deck goes to 8. The only dive…
- `relic/empty_cage/g2` — DORMANT — N2: run.select_cards falls back to `self.rng.sample` when no card_selector is installed (run.py), where the game opens a removal screen and draws no RNG — Same mechanism and same verdict as relic/electric_shrymp guard N3 in this b…
- `relic/fake_anchor/g3` — DORMANT — N3 (DORMANT): the ordering window -- C# grants the block at turn_structure step 3, the sim at the step-14 AfterBlockCleared loop, and anything between the two that reads player Block sees 4 in C# and 0 in the sim — Same mechanism…
- `relic/fake_snecko_eye/AfterObtained` — DORMANT — MECHANISM: FakeSneckoEye.cs applies the Confused power immediately when the relic is picked up if `CombatManager.Instance.IsInProgress`, so a Fake Snecko Eye obtained mid-combat confuses you for the rest of that fight. The sim imp…
- `relic/fake_strike_dummy/g2` — DORMANT — G1 (DORMANT): C#'s fourth clause is `if (dealer != Owner.Creature && cardSource.Owner != Owner) return 0;` -- an AND of two negatives, i.e. fire when EITHER holds; the sim requires `dealer is self.player` alone (fake_strike_dummy.…
- `relic/festive_popper/AfterPlayerTurnStart` — DORMANT — STILL OPEN at G2 and G3. G1, the slot, is CLOSED: FestivePopper.cs declares AfterPlayerTurnStart and `on_player_turn_started` is now that hook alone -- the AfterSideTurnStart listeners it used to share a registration-ordered walk…
- `relic/festive_popper/g2` — DORMANT — G2 (DORMANT): `combatState.HittableEnemies` (FestivePopper.cs) vs the sim's living_enemies() (festive_popper.py) — Identical mechanism to relic/bag_of_marbles guard G2 and carried with the same gap verdict per binding rule 3, at a…
- `relic/forgotten_soul/AfterCardExhausted` — DORMANT — Rollup of guard G1 per binding rule 4. Every number and stream matches -- DamageVar(1m, ValueProp.Unpowered) (ForgottenSoul.cs) is DAMAGE = 1 with DamageProps.NON_CARD_UNPOWERED (= ValueProp.UNPOWERED, valueprops.py), the dealer i…
- `relic/fragrant_mushroom/AfterObtained` — DORMANT — NARROWED. The sort-key half (G1) is CLOSED: sts2_rl/relics/fragrant_mushroom.py now passes `key=_compare_to_key` (sts2_rl/player.py, the UPPERCASE ordinal compare) to actmap.stable_shuffle over run.rng_set.niche. WHAT REMAINS is g…
- `relic/fragrant_mushroom/g2` — DORMANT — G2 (DORMANT): `CreatureCmd.Damage(ThrowingPlayerChoiceContext, Owner.Creature, HpLoss.BaseValue, Unblockable|Unpowered, null, null)` (FragrantMushroom.cs) vs `run.lose_hp(15)` (fragrant_mushroom.py) — MECHANISM: the source routes…
- `relic/fresnel_lens/g2` — DORMANT — G2: `EnchantCard` clones the card first (`base.Owner.RunState.CloneCard(card)`, FresnelLens.cs) and enchants the CLONE, then hands it back via `option.ModifyCard(...)` / `out newCard` — PROMPT.md bug class 17 (shallow clones) appl…
- `relic/frozen_egg/g3` — DORMANT — G3: the sim upgrades the ORIGINAL card object where C# substitutes an upgraded CloneCard (FrozenEgg.cs; EggRelicHelper.cs) — PROMPT.md bug class 17 at the egg relics' two sites. CardScope.CloneCard -> ClonePreservingMutability (Ca…
- `relic/fur_coat/AfterCreatureAddedToCombat` — DORMANT — STAYS OPEN via inherited G3 -- but divergence (a) is REMOVED, not narrowed: IT WAS A CITATION ERROR AND THE DIVERGENCE NEVER EXISTED. The record conflated CombatManager.AfterCreatureAdded (CombatManager.cs, which only runs creatur…
- `relic/fur_coat/g3` — DORMANT — G3 (DORMANT): `CreatureCmd.SetCurrentHp(item, 1m)` (FurCoat.cs, 139) vs the sim's raw `enemy.hp = 1` (fur_coat.py, 87) — MECHANISM: CreatureCmd.SetCurrentHp (CreatureCmd.cs) does three things the raw assignment does not -- it fire…
- `relic/gambling_chip/AfterPlayerTurnStart` — DORMANT — mechanism `relic/_auto_keep` (family: `auto-keep` / `SKIPPABLE_PURPOSES`). REASONING REPLACED round 14: G1 (Sly auto-play) FLIPS to faithful — gambling_chip.py now calls the shared CardCmd.discard_and_draw, which implements the Sly-collect-and-auto-play tail; executed end to end, it auto-plays a hand-fed sly=True card. G1's only residue is a content gap (no registered card sets sly=True), filed under the Sly keyword's own porting record, not this one. G3 (min=0 decline) is also faithful (driver.py's SKIPPABLE_PURPOSES, closed 2026-07-27). Only G2 remains: no AfterCardChangedPiles dispatch on the pile mutation — zero registered listeners for that hook — see `relic/gambling_chip/g2`.
- `relic/gambling_chip/g1` — DORMANT — G1 (DORMANT): CardCmd.DiscardAndDraw auto-plays every discarded card that `IsSlyThisTurn`, AFTER the draw (CardCmd.cs); the sim's loop has no Sly concept — MECHANISM: DiscardAndDraw collects `if (card.IsSlyThisTurn) slyCards.Add(c…
- `relic/gambling_chip/g2` — DORMANT — G2 (DORMANT): each discard goes through `CardPileCmd.Add(card, discardPile)` in C# (CardCmd.cs) where the sim mutates the two lists directly (gambling_chip.py) — MECHANISM: CardPileCmd.Add runs the game's pile-change machinery --…
- `relic/ghost_seed/AfterCardEnteredCombat` — DORMANT — Rollup of guard G2 per binding rule 4. The predicate and the effect match -- GhostSeed.cs applies CardKeyword.Ethereal to any card CanAffect accepts -- but C#'s `CardCmd.ApplyKeyword` adds a keyword whose SOURCE is tracked (Keywor…
- `relic/ghost_seed/AfterRoomEntered` — DORMANT — See guard G1. GhostSeed.cs filters `room is CombatRoom` and then sweeps `Owner.PlayerCombatState.AllCards`; the sim iterates `self.player.all_cards` at on_combat_start. C#'s AfterRoomEntered for a combat room is dispatched at Comb…
- `relic/ghost_seed/g1` — DORMANT — G1 (DORMANT): the sweep runs at BeforeCombatStart in the sim and at AfterRoomEntered in C#, two dispatch points earlier — MECHANISM: the C# order is SetUpCombat -> Hook.AfterRoomEntered (CombatRoom.cs) -> AfterCombatRoomLoaded ->…
- `relic/ghost_seed/g2` — DORMANT — G2 (DORMANT): `!card.GetKeywordsWithSources(KeywordSources.Local).Contains(Ethereal)` (GhostSeed.cs) vs the sim's single `not card.is_ethereal` boolean — MECHANISM: C# tracks WHERE each keyword came from, and CanAffect only refuse…
- `relic/girya/AfterRoomEntered` — DORMANT — See guard G2. Girya.cs applies StrengthPower equal to TimesLifted when `TimesLifted > 0 && room is CombatRoom`; girya.py does the same at combat start, two dispatch points later (C#'s AfterRoomEntered for a combat room fires at Co…
- `relic/girya/g2` — DORMANT — G2 (DORMANT): the Strength lands at BeforeCombatStart in the sim and at AfterRoomEntered in C#, two dispatch points earlier -- and the sim's slot is interleaved with other relics' on_combat_start by registration order where C#'s a…
- `relic/glitter/g1` — DORMANT — G1 (DORMANT): `base.Owner.RunState.CloneCard(card)` then `CardCmd.Enchant<Glam>(card2, 1m)` then `cardReward.ModifyCard(card2, this)` (Glitter.cs) vs `GlamEnchantment().attach(card)` in place (glitter.py) — PROMPT.md bug class 17.…
- `relic/golden_pearl/g2` — DORMANT — N2 (DORMANT): PlayerCmd.GainGold's `Hook.AfterGoldGained(runState, player)` tail (PlayerCmd.cs) has no sim counterpart at all -- neither this relic nor the sim's Relic base declares an after_gold_gained hook — MECHANISM: every gol…
- `relic/gorget/g4` — DORMANT — N4 (DORMANT): PlatingPower's own port diverges on WHERE it decays -- the sim decays from on_player_turn_start (pre-draw) where PlatingPower.cs decays from AfterSideTurnStart (post-draw) — MECHANISM: PlatingPower.cs decrements in A…
- `relic/gremlin_horn/AfterDeath` — DORMANT — Rollup of guards G1 and G2 per binding rule 4. The relic's own body is exact -- GremlinHorn.cs's side check, EnergyVar(1) and CardsVar(1) map one-for-one onto gremlin_horn.py, and EXECUTED (py audit/tools/relic_probes_b07.py horn-…
- `relic/gremlin_horn/g2` — DORMANT — G2 (DORMANT): the sim resolves death INSIDE the damage pipeline, before the dealer's post-damage event; C# defers Kill() until after AfterDamageGiven and AfterDamageReceived have run for every target of the batch — MECHANISM: Crea…
- `relic/hand_drill/g1` — DORMANT — G1 (DORMANT): C# orders AfterBlockBroken listeners BEFORE AfterDamageGiven listeners for the same damage result; the sim puts Hand Drill on the same event as the AfterBlockBroken listener and lets registration order decide — MECHA…
- `relic/hand_drill/g2` — DORMANT — G2 (DORMANT): the C# guard is `dealer == base.Owner.Creature || dealer?.PetOwner == base.Owner` -- the port drops the PET arm entirely (hand_drill.py is `dealer is not self.player`) — MECHANISM: HandDrill.cs credits the owner's PE…
- `relic/happy_flower/g3` — DORMANT — N3 (DORMANT): PlayerCmd.GainEnergy's `Hook.AfterModifyingEnergyGain` companion event and its `finalAmount > 0` gate (PlayerCmd.cs) have no counterpart in the sim's EnergyCmd.gain (cmds.py) — MECHANISM: C# folds Hook.ModifyEnergyGa…
- `relic/hefty_tablet/g2` — DORMANT — G2 (DORMANT): CardFactory.CreateForReward runs Hook.TryModifyCardRewardOptions on the three cards unless CardCreationFlags.NoModifyHooks is set, and HeftyTablet sets only NoUpgradeRoll -- the port calls no such hook — MECHANISM: C…
- `relic/ice_cream/g2` — DORMANT — N2 (DORMANT): the sim calls modify_max_energy BEFORE should_reset_energy; C# evaluates ShouldPlayerResetEnergy first and only then reads MaxEnergy inside the chosen branch — This is audit/records/seam/turn_structure.json gap at sp…
- `relic/intimidating_helmet/g3` — DORMANT — N1 (DORMANT): the SLOT -- C# fires BeforeCardPlayed after the card has been added to the Play pile and after GeneratePlayCount; the sim fires on_energy_spent immediately after deducting the energy, before the card leaves the hand…
- `relic/jeweled_mask/g3` — DORMANT — N3 (DORMANT): SetToFreeThisTurn is `EndOfTurn | WhenPlayed` in C#; the sim's _free_this_turn expires only at the next turn start — MECHANISM: CardModel.SetToFreeThisTurn (CardModel.cs) adds a LocalCostModifier with `LocalCostModif…
- `relic/jeweled_mask/g4` — DORMANT — N4 (DORMANT): the port moves the card with two list operations (`draw_pile.remove` / `hand.append`, jeweled_mask.py) instead of the sim's CardPileCmd, so it bypasses the hand cap — MECHANISM: C# calls `CardPileCmd.Add(cardModel, P…
- `relic/kusarigama/AfterCardPlayed` — DORMANT — NARROWED. The per-Replay half (G1) is CLOSED: CombatState._resolve_card_play fires on_card_played inside the play-count loop (sts2_rl/combat.py, 597-600). WHAT REMAINS is guard G2, the candidate list: Kusarigama.cs picks with `Run…
- `relic/kusarigama/g2` — DORMANT — G2 (DORMANT): `Owner.Creature.CombatState.HittableEnemies` (Kusarigama.cs) vs the sim's living_enemies() (kusarigama.py) — C# picks the random target from `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!Is…
- `relic/lantern/g1` — DORMANT — N1: `PlayerCmd.GainEnergy(amount, player)` (Lantern.cs) vs `EnergyCmd.gain(self.hooks, player, 1)` (lantern.py) -- the missing AfterModifyingEnergyGain companion and the `finalAmount > 0` / `IsEnding` guards — Narrowed: the IsEndi…
- `relic/lasting_candy/AfterCombatEnd` — DORMANT — LastingCandy.cs is the `CombatsSeen++` counter that decides 'every other combat' (IsInTriggeringCombat = `CombatsSeen > 0 && CombatsSeen % 2 == 0`, LastingCandy.cs). The sim's Relic base HAS the hook -- `after_combat_end(run, room…
- `relic/lava_lamp/g2` — DORMANT — G2 (DORMANT, but the fix must not reproduce it): C# UPGRADES A CLONE -- `RunState.CloneCard(card)` then `CardCmd.Upgrade(card2)` then `cardReward.ModifyCard(card2, this)` (LavaLamp.cs) -- and the sim has no clone helper — PROMPT.m…
- `relic/leafy_poultice/g3` — DORMANT — N1 (DORMANT): `CreatureCmd.LoseMaxHp` routes the excess current HP through the FULL damage pipeline; RunState.lose_max_hp just clamps — CreatureCmd.LoseMaxHp (src/Core/Commands/CreatureCmd.cs) computes an UNFLOORED newMaxHp = MaxH…
- `relic/letter_opener/AfterCardPlayed` — DORMANT — REASONING REPLACED. The retired text claimed a `DamageCmd.deal` backstop (`if not hooks.should_allow_hitting(target): return 0`). THAT BACKSTOP DOES NOT EXIST -- the line is DEAD CODE, dominated by the `if target.is_dead: return 0…
- `relic/letter_opener/g2` — DORMANT — G2 (DORMANT): `Owner.Creature.CombatState.HittableEnemies` (LetterOpener.cs) vs the sim's living_enemies() (letter_opener.py) — C# damages `Enemies.Where(e => e.IsHittable)` -- `!IsDead && Hook.ShouldAllowHitting(...)` (src/Core/C…
- `relic/lost_coffer/g4` — DORMANT — N2: `CardCreationFlags.IsCardReward` is set by CardReward's constructor (CardReward.cs); the sim has no card-creation flag concept at all — The flag exists so that relics which affect card REWARDS only (CardCreationFlags.cs names…
- `relic/meat_cleaver/TryModifyRestSiteOptions` — DORMANT — RE-EXECUTED. Guard G1 is NOT part of the gap -- it is `deliberate-divergence` (the sim omits a disabled option rather than adding one greyed out; same reachable action set, since the sim has no rest-site UI to show the grey row).…
- `relic/meat_cleaver/g1` — DORMANT — G2 (DORMANT): CookRestSiteOption's card-removal screen is `Cancelable = true` and a cancel makes the whole option a no-op (CookRestSiteOption.cs); the sim's cook always removes 2 cards and always grants the 9 Max HP — MECHANISM: C…
- `relic/miniature_cannon/ModifyDamageAdditive` — DORMANT — Rollup of guard G1 per binding rule 4. Three of C#'s four early returns are reproduced exactly (N1-N3, all executed); the fourth is an AND that the port narrows to one of its two disjuncts.
- `relic/miniature_cannon/g1` — DORMANT — G1 (DORMANT): `if (dealer != base.Owner.Creature && cardSource.Owner != base.Owner) return 0` (MiniatureCannon.cs) is an AND, so C# adds the damage when EITHER the dealer is the owner OR the card belongs to the owner; the port kee…
- `relic/miniature_tent/g1` — DORMANT — G1 (DORMANT): C# aggregates this hook over `runState.IterateHookListeners(null)` -- deck cards, powers and modifiers as well as relics -- and the sim iterates `self.relics` only — MECHANISM: Hook.ShouldDisableRemainingRestSiteOpti…
- `relic/molten_egg/ModifyMerchantCardCreationResults` — DORMANT — Same body as the reward path in C# too -- MoltenEgg.cs calls the identical EggRelicHelper.UpgradeValidCards (no CurrentUpgradeLevel check anywhere in that helper, EggRelicHelper.cs) -- and notably has NO NoHookUpgrades check, so t…
- `relic/molten_egg/g4` — DORMANT — G4 (DORMANT): the sim applies Molten Egg's already-upgraded refusal to ALL THREE paths; C# applies it ONLY to the deck-add path, because EggRelicHelper.UpgradeValidCards has no upgrade-level check — MECHANISM: the reward and merch…
- `relic/molten_egg/g9` — DORMANT — N4: the sim has ONE modify_card_reward_options pass where C# runs TryModifyCardRewardOptions and then TryModifyCardRewardOptions**Late** as two complete passes — MECHANISM: Hook.TryModifyCardRewardOptions (Hook.cs) walks every lis…
- `relic/new_leaf/AfterObtained` — DORMANT — Rollup of guards N1 and G1 per binding rule 4. Count, selection prompt and deck placement are all faithful; the named Niche RNG stream is dropped (N1, live for RNG parity) and the candidate list omits C#'s Quest-card exclusion (G1…
- `relic/new_leaf/g2` — DORMANT — G1 (DORMANT): CardSelectCmd.FromDeckForTransformation also excludes Quest cards; run.transformable_cards() filters only Eternal — MECHANISM: CardSelectCmd.FromDeckForTransformation (CardSelectCmd.cs) builds its candidate list as `…
- `relic/nunchaku/g5` — DORMANT — N4: `PlayerCmd.GainEnergy` (Nunchaku.cs) runs Hook.ModifyEnergyGain, then Hook.AfterModifyingEnergyGain, then a `finalAmount > 0` check (PlayerCmd.cs); EnergyCmd.gain (cmds.py) runs the modify chain and adds unconditionally — This…
- `relic/old_coin/g3` — DORMANT — N1: `PlayerCmd.GainGold`'s companion event `Hook.AfterModifyingGoldGained` (PlayerCmd.cs) has no sim counterpart — This is the missing-AfterModifying-companion family that audit/records/seam/power_cmd.json gap G4 records and that…
- `relic/paels_legion/g3` — DORMANT — G3 (DORMANT): the sim adds a `target is not self.player` check that C#'s ModifyBlockMultiplicative does not have — MECHANISM: PaelsLegion.cs checks props, cardSource and cardSource.Owner -- and NOTHING about the target. So in C#,…
- `relic/paper_phrog/ModifyVulnerableMultiplier` — DORMANT — Rollup of guards G1 and N2 per binding rule 4. NOT a Hook override: PaperPhrog.cs is a plain public method, and its ONE caller is VulnerablePower.ModifyDamageMultiplicative, which looks the relic up directly on the dealer (`dealer…
- `relic/paper_phrog/g1` — DORMANT — G1 (DORMANT): C# consults the dealer's phrog ONCE by direct lookup; the sim runs a hook chain over every combat listener, so N copies of the relic would each add 0.25 — MECHANISM: VulnerablePower.cs does `dealer.Player?.GetRelic<P…
- `relic/paper_phrog/g3` — DORMANT — N2 (DORMANT): `if (target == base.Owner.Creature) return amount;` (PaperPhrog.cs) -- no bonus when the phrog's own owner is the Vulnerable creature; the sim checks only the dealer — MECHANISM: paper_phrog.py is `if dealer is self.…
- `relic/parrying_shield/AfterSideTurnEnd` — DORMANT — NARROWED (adversarial pass). Rollup of guard G1 only, and G1 is now DORMANT rather than LIVE; guard G2 is CLOSED. maps_to should be re-pointed to after_player_turn_end (parrying_shield.py), dispatched by HookSystem.after_player_tu…
- `relic/pen_nib/g3` — DORMANT — G3 (DORMANT): C# skips Hook.AfterCardPlayed entirely when the play ended the combat (CardModel.cs gates on CombatManager.IsInProgress) while combat.py always fires it, so a game-side 10th Attack that lands the killing blow stays M…
- `relic/philosophers_stone/AfterCreatureAddedToCombat` — DORMANT — Rollup of guard G1 per binding rule 4. The effect and the constant are right -- 1 Strength on each joiner, executed at b12-stone: a mid-combat SpinyToad spawn comes in at Strength(1) -- and the two hooks provably cannot double-app…
- `relic/philosophers_stone/g1` — DORMANT — G1 (DORMANT): C# skips any creature on the OWNER's SIDE (PhilosophersStone.cs); the sim skips only the player OBJECT (philosophers_stone.py), so a player-side creature that is not the player would be strengthened in the sim and no…
- `relic/prismatic_gem/g1` — DORMANT — G1 (DORMANT): the four early-return clauses of ModifyCardRewardCreationOptions (PrismaticGem.cs) select exactly the case the waiver above depends on -- and one of them is the residual risk — MECHANISM: C# bails on NoCardPoolModifi…
- `relic/prismatic_gem/g2` — DORMANT — N1: modify_max_energy is evaluated BEFORE should_reset_energy in the sim and inside the chosen branch in C# — This is audit/records/seam/turn_structure.json step 17's finding, not a new one: `player.py` calls modify_max_energy fir…
- `relic/punch_dagger/AfterObtained` — DORMANT — NARROWED. The stub PREMISE finding is discharged -- the docstring no longer rests on a false claim -- but the relic is STILL a no-op, and the reason is now written into the port. sts2_rl/relics/punch_dagger.py's docstring now name…
- `relic/punch_dagger/CanonicalVars` — DORMANT — NARROWED. The stub PREMISE finding is discharged -- the docstring no longer rests on a false claim -- but the relic is STILL a no-op, and the reason is now written into the port. sts2_rl/relics/punch_dagger.py's docstring now name…
- `relic/rainbow_ring/AfterCardPlayed` — DORMANT — RE-EXECUTED. The port still latches BEFORE the two PowerCmd.apply calls (`sts2_rl/relics/rainbow_ring.py`: `self._activated = True` is set, then Strength then Dexterity are applied), where C# increments `ActivationCountThisTurn` o…
- `relic/rainbow_ring/g1` — DORMANT — G1 (DORMANT): C# increments ActivationCountThisTurn AFTER awaiting both PowerCmd.Apply calls (RainbowRing.cs); the sim sets `_activated = True` BEFORE them (rainbow_ring.py) — MECHANISM: C#'s guard is `ActivationCountThisTurn < 1`…
- `relic/red_skull/g3` — DORMANT — N2 (DORMANT): C#'s AfterCurrentHpChanged has NO `creature == Owner.Creature` check (RedSkull.cs); the sim gates on `creature is self.player` (red_skull.py) — MECHANISM: C# re-evaluates the owner's threshold whenever ANY creature's…
- `relic/ruined_helmet/g2` — DORMANT — G2 (DORMANT): C#'s RECEIVED-side predicate chain is a separately-sequenced phase; the sim has one flat registration-order chain — This is audit/records/seam/power_cmd.json gap G3 at the site that record already names -- it cites `…
- `relic/ruined_helmet/g3` — DORMANT — G3 (DORMANT): the 'mark used' side effect is hand-inlined into the modifier, so it fires at a point C# would not have reached — This is audit/records/seam/power_cmd.json gap G4 at its own site -- that record names RuinedHelmet.Aft…
- `relic/sai/g1` — DORMANT — G1 (DORMANT at this site, LIVE as a mechanism): AfterSideTurnStart is C#'s SECOND turn-start pass and the sim runs one flat walk (seam guard G12, PROMPT.md class 25) — MECHANISM: Hook.AfterSideTurnStart runs every listener's After…
- `relic/seal_of_gold/g2` — DORMANT — G2 (DORMANT at this site, LIVE as a mechanism): AfterSideTurnStart is C#'s second turn-start pass and the sim runs one flat walk (seam guard G12, PROMPT.md class 25) — MECHANISM as recorded for relic/sai in this batch: Hook.AfterS…
- `relic/self_forming_clay/g3` — DORMANT — N3: the sim has no SelfFormingClayPower at all, so the pending Block is not a visible, stackable, removable power on the player — MECHANISM: `grep -rn SelfFormingClay sts2_rl/powers.py` returns nothing -- the sim models the effect…
- `relic/shovel/TryModifyRestSiteOptions` — DORMANT — Rollup of guard G2 per binding rule 4. The DIG option's effect matches -- RelicCmd.Obtain(RelicFactory.PullNextRelicFromFront(Owner)) (DigRestSiteOption.cs) maps to run.obtain_relic_from_grab_bag() (shovel.py), and the default ove…
- `relic/shovel/g2` — DORMANT — G2 (DORMANT): the sim refuses to OFFER the DIG option when the grab bag is empty; C# always offers it and grants RelicFactory.FallbackRelic instead — MECHANISM: Shovel.TryModifyRestSiteOptions adds `new DigRestSiteOption(player)`…
- `relic/signet_ring/g2` — DORMANT — N2: Hook.AfterModifyingGoldGained (PlayerCmd.cs) has no sim counterpart — MECHANISM: C#'s gold pipeline is the same two-phase shape as its damage and power pipelines -- ModifyGoldGained collects the listeners that changed the amou…
- `relic/silver_crucible/ShouldGenerateTreasure` — DORMANT — Rollup of guard G3 per binding rule 4. The predicate matches (`TreasureRoomsEntered > 1`, SilverCrucible.cs) and so does the all-must-agree dispatcher (`if (!item.ShouldGenerateTreasure(player)) return false`, Hook.cs). What diver…
- `relic/silver_crucible/g3` — DORMANT — G3 (DORMANT): a suppressed treasure room still pays out Spoils Map in the sim — MECHANISM: C# reaches the Spoils Map payout only from INSIDE the gated reward routine -- OneOffSynchronizer.DoTreasureRoomRewards opens with `if (!Hoo…
- `relic/sling_of_courage/AfterRoomEntered` — DORMANT — Rollup of guard N1 per binding rule 4. SlingOfCourage.cs applies PowerVar<StrengthPower>(2) from AfterRoomEntered when `room.RoomType == RoomType.Elite`, and for a CombatRoom that hook fires after CombatManager.SetUpCombat and BEF…
- `relic/sling_of_courage/g1` — DORMANT — N1 (DORMANT gap, matching audit/records/relic/girya.json G2): the slot move -- C# guarantees the Strength lands BEFORE every BeforeCombatStart listener; the sim puts it INSIDE that pass — MECHANISM: for a CombatRoom, `Hook.AfterRo…
- `relic/snecko_eye/AfterObtained` — DORMANT — SneckoEye.cs applies the Confused power immediately when the relic is picked up DURING a combat (`if (CombatManager.Instance.IsInProgress) await ApplyPower()`). snecko_eye.py defines only on_combat_start and modify_hand_draw, so a…
- `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — DORMANT — Rollup of guards G1, G2 and G3 per binding rule 4. The arithmetic is right -- a Power card costs 1 more -- but the sim has no phase structure and no per-creature listener grouping, and this relic is the named ported witness for BO…
- `relic/spiked_gauntlets/g2` — DORMANT — G2 (DORMANT at this site): the hook has a PLAIN pass and a LATE pass and the sim has neither — Hook.ModifyEnergyCostInCombat runs TWO complete listener passes -- every TryModifyEnergyCostInCombat, then every TryModifyEnergyCostInC…
- `relic/spiked_gauntlets/g3` — DORMANT — G3 (DORMANT): the sim drops the `card.Owner.Creature != base.Owner.Creature` guard AND the dispatcher's `originalCost < 0` X-cost bail; it adds a final max(0, cost) clamp C# does not have — Three differences in the same collapse,…
- `relic/stone_calendar/BeforeSideTurnEnd` — DORMANT — Rollup of guards G1 and G2 per binding rule 4. The trigger turn, the damage number, the target set and the props all match and are executed; the divergences are the flattened sub-phase ordering (G1) and the living_enemies-vs-Hitta…
- `relic/stone_calendar/g2` — DORMANT — G2 (DORMANT): `combatState.HittableEnemies` (StoneCalendar.cs) vs the sim's living_enemies() (stone_calendar.py) — Same mechanism and therefore the same verdict as relic/bag_of_marbles guard G2 (binding rule 3): C# targets `Enemie…
- `relic/stone_cracker/AfterRoomEntered` — DORMANT — NARROWED. The shuffle half (G1) is CLOSED: sts2_rl/relics/stone_cracker.py now feeds actmap.stable_shuffle the pile in the game's top-at-index-0 orientation (`list(reversed(upgradable))`) with `key=_compare_to_key`, over crng.card…
- `relic/stone_cracker/g2` — DORMANT — G2 (DORMANT): the C# hook is AfterRoomEntered, which runs one full dispatch BEFORE Hook.BeforeCombatStart; the port uses on_combat_start — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE…
- `relic/stone_humidifier/AfterRestSiteHeal` — DORMANT — DORMANT, settled by execution. Rollup of guard G1 per binding rule 4, which this record already labels dormant and unchanged. RE-VERIFIED: `grep -n mend sts2_rl/run.py sts2_rl/rest_site.py` finds no Mend rest-site option anywhere…
- `relic/stone_humidifier/g1` — DORMANT — G1 (DORMANT): Hook.AfterRestSiteHeal has TWO dispatch sites in C# and the sim ports only one — MECHANISM: an executed grep for AfterRestSiteHeal over the decompiled source finds two callers outside the relic models -- HealRestSite…
- `relic/strike_dummy/g2` — DORMANT — G2 (DORMANT): C# grants the +3 when EITHER the dealer is the owner's creature OR the Strike card BELONGS to the owner; the port requires the dealer — MECHANISM: StrikeDummy.cs is `if (dealer != base.Owner.Creature && cardSource.Ow…
- `relic/sword_of_jade/AfterRoomEntered` — DORMANT — Rollup of guards G1 and N1 per binding rule 4. The power, the amount and the target are right and executed; the hook SITE is one dispatch later than C#'s and the applier identity differs.
- `relic/sword_of_jade/g1` — DORMANT — G1 (DORMANT): the C# hook is AfterRoomEntered, which runs a full dispatch BEFORE Hook.BeforeCombatStart; the port uses on_combat_start — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE po…
- `relic/tea_of_discourtesy/g2` — DORMANT — G2 (DORMANT): the port skips CardPileCmd._enter_combat, so the two generated Dazed are never registered as combat hook listeners and AfterCardEnteredCombat never fires for them — MECHANISM: C# creates the card with `combatState.Cr…
- `relic/the_boot/g2` — DORMANT — G2 (DORMANT): C# gates on `props.IsPoweredAttack()`; the sim's modify_hp_lost signature carries no props at all, so the port substitutes `card is None or card.is_unpowered` — MECHANISM: ValuePropExtensions.IsPoweredAttack (ValuePr…
- `relic/touch_of_orobas/AfterObtained` — DORMANT — Rollup of guards G1 and N4 per binding rule 4. The core behaviour is right and executed: the starter relic is replaced IN PLACE by its refinement and the replacement's own after_obtained runs. What the port drops from RelicCmd.Rep…
- `relic/touch_of_orobas/g2` — DORMANT — G1 (DORMANT): RelicCmd.Obtain strips the obtained relic from both grab bags (`player.RelicGrabBag.Remove(relic)` and `runState.SharedRelicGrabBag.Remove(relic)`, RelicCmd.cs) and stamps `FloorAddedToDeck`; the port's direct list a…
- `relic/toy_box/AfterCombatEnd` — DORMANT — Rollup of guards G2 and N1 per binding rule 4. The counter and the every-3rd-combat trigger are faithful (N1); the divergence is that RelicCmd.Melt leaves the melted relic in the player's relic list as an inert entry and the port…
- `relic/toy_box/g2` — DORMANT — G2 (DORMANT): `RelicCmd.Melt` leaves the relic in `Player.Relics` as an inert entry; the port removes it from run.relics entirely — MECHANISM: RelicCmd.Melt (RelicCmd.cs) is `relic.Owner.MeltRelicInternal(relic); await relic.After…
- `relic/tungsten_rod/g6` — DORMANT — N5: the run-level walk's listener SET -- `RunState.lose_hp` iterates relics only (run.py), where C#'s IterateHookListeners(null) also walks every deck card and its enchantment (RunState.cs) and the player's potions (:570) — MECHAN…
- `relic/unsettling_lamp/BeforePowerAmountChanged` — DORMANT — STAYS OPEN (the record's G3 + G4 remain); its G2 closed. TEXT CORRECTED: the method this rollup named, modify_power_amount (unsettling_lamp.py), no longer exists -- the relic now implements modify_power_amount_given_multiplicative…
- `relic/unsettling_lamp/ModifyPowerAmountGivenMultiplicative` — DORMANT — C# returns a MULTIPLICATIVE factor into Hook.ModifyPowerAmountGiven's two-pass fold (Hook.cs: every listener's additive contribution is summed FIRST, then every listener's multiplicative factor is applied to that sum). The sim's m…
- `relic/unsettling_lamp/g5` — DORMANT — G3 (DORMANT): C#'s ModifyPowerAmountGivenMultiplicative has NO target-side guard and NO giver guard -- only the LATCH checks `target.Side == Owner.Creature.Side` and `applier != Owner.Creature` -- whereas the sim applies both chec…
- `relic/unsettling_lamp/g6` — DORMANT — G4 (DORMANT): C#'s cardSource is a per-APPLICATION argument; the sim substitutes an ambient `_in_flight` card set by before_card_played and cleared by on_card_played, so a nested card play inside the triggering card's resolution c…
- `relic/vajra/g1` — DORMANT — G1 (DORMANT): nothing observes the player's Strength in the window between C#'s AfterRoomEntered and the sim's on_combat_start, so the phase difference has no observable today — MECHANISM: as above -- one full combat-setup phase s…
- `relic/vexing_puzzlebox/g4` — DORMANT — N3: `cardModel.SetToFreeThisTurn()` (VexingPuzzlebox.cs) vs `card.set_free_this_turn()` (vexing_puzzlebox.py) — C#'s SetToFreeThisTurn is `EnergyCost.SetThisTurnOrUntilPlayed(0)` plus SetStarCostThisTurn(0) (CardModel.cs). The sim…
- `relic/wing_charm/g3` — DORMANT — N2 (DORMANT while the port is empty, LIVE the moment G1 is fixed): `base.Owner.RunState.CloneCard(...)` is a full model clone and the sim has no clone helper — NARROWED. The dormancy premise has changed: the port is no longer empt…
- `relic/winged_boots/g3` — DORMANT — N3: the sim charges only the FIRST relic whose should_allow_free_travel() is True and then `break`s (run.py); C# charges every AfterRoomEntered implementer independently — MECHANISM: in C# the charge is each relic's own business,…
- `relic/wongos_mystery_ticket/g7` — DORMANT — N6 (DORMANT): an exhausted relic grab bag makes the sim hand out FEWER than three relics and still spend the ticket, where C# substitutes RelicFactory.FallbackRelic and always resolves three — MECHANISM: C#'s `PullNextRelicFromFro…

## `potion` — 13 mechanisms

- `potion/_strength_applier` (4 sites) — DORMANT — OnUse (protected override, FyshOil.cs) — Rollup of guard N(applier) per binding rule 4. The two applications, their amounts and their ORDER (Strength first, then Dexterity -- FyshOil.cs vs potions.py) all match; what does not is t…
- `potion/fairy_in_a_bottle/AfterPreventingDeath` — DORMANT — Rollup of guards G1 and G2 per binding rule 4, NARROWED. The C# body is one line -- `await OnUseWrapper(new ThrowingPlayerChoiceContext(), creature)` (FairyInABottle.cs) -- i.e. the automatic trigger runs the FULL use pipeline. Th…
- `potion/fairy_in_a_bottle/g1` — DORMANT — G1 (LIVE): the automatic trigger bypasses OnUseWrapper, so Hook.AfterPotionUsed never fires when the fairy pops — NARROWED: partly closed. FairyInABottle.after_preventing_death (potions.py) now ends with `combat.hooks.on_potion_us…
- `potion/fairy_in_a_bottle/g2` — DORMANT — G2 (dormant): `discard_potion` is the DiscardPotionInternal verb; OnUseWrapper's first step is RemoveBeforeUse, a different one — PotionModel has two removal verbs with different meanings: Discard() -> `Owner.DiscardPotionInternal…
- `potion/foul_potion/OnUse` — DORMANT — OnUse (protected override, FoulPotion.cs) — Rollup of guards G1 and G2 per binding rule 4, NARROWED. G2 is CLOSED -- the in-combat arm now damages player-then-enemies, the source's `_allies.Concat(_enemies)` order (executed). G1 i…
- `potion/foul_potion/PassesCustomUsabilityCheck` — DORMANT — UPDATED: still a gap, and closer to live than it was. EXECUTED CENSUS (unchanged): `grep -rn 'override bool PassesCustomUsabilityCheck' src/` returns exactly one hit in the whole game, FoulPotion.cs -- this unit is the sole implem…
- `potion/foul_potion/TargetType` — DORMANT — UPDATED: still a gap, and its dormancy argument has changed. FoulPotion.cs is the tier's only COMPUTED TargetType: `TargetType.TargetedNoCreature` when `!CombatManager.Instance.IsInProgress`, `TargetType.AllEnemies` in combat. The…
- `potion/foul_potion/g1` — DORMANT — G1 (LIVE): the two out-of-combat arms are unported, and the port's docstring names a sim capability that does not exist — NARROWED: partly closed, and the remaining shape has changed. CLOSED: the potion has an out-of-combat arm an…
- `potion/gamblers_brew/g3` — DORMANT — N2 (dormant): the Sly auto-play deferral has no sim counterpart — CardCmd.cs collects every discarded card with `IsSlyThisTurn`, and after the draw auto-plays each of them with AutoPlayType.SlyDiscard. The sim has no Sly concept a…
- `potion/gamblers_brew/g4` — DORMANT — N3 (dormant): the sim fires on_card_discarded BEFORE the card reaches the discard pile; C# fires it after — C# per card: `CardPileCmd.Add(card, discardPile)` then `History.CardDiscarded` then `Hook.AfterCardDiscarded` (CardCmd.cs)…
- `potion/snecko_oil/OnUse` — DORMANT — OnUse (protected override, SneckoOil.cs) — Rollup of guards N2 and N3 per binding rule 4. The structure is right and it is the part a replay would notice: draw 7 FIRST, then walk the resulting hand in order and take ONE `Rng.Comba…
- `potion/snecko_oil/g2` — DORMANT — N2 (dormant): the C# skips a card whose unmodified cost is NEGATIVE and the port has no such clause — SneckoOil.cs guards each card with `if (item.EnergyCost.GetWithModifiers(CostModifiers.None) >= 0)` on top of the `!c.EnergyCost…
- `potion/snecko_oil/g3` — DORMANT — N3 (dormant): `SetThisTurnOrUntilPlayed` also expires when the card is PLAYED; the sim models only the end-of-turn half — SneckoOil.cs calls `EnergyCost.SetThisTurnOrUntilPlayed(...)`, whose name states two expiry conditions. The…

---

# Dormant-trigger watch list

Every dormant gap names a concrete unported thing that would make it live.
**Anyone porting a row's trigger needs to read that row's mechanisms first** —
the port will otherwise be written against a sim seam that does not behave like
the game's. Sorted roughly by how likely the trigger is to come up. Section A
is the engine seams; **section B is the content tiers**, whose triggers are
different in kind — several are *other queue entries*, so fixing one mechanism
wakes another and the two belong in the same commit.

## A. Engine-seam triggers

| trigger — the unported thing | wakes |
|---|---|
| Porting **BufferPower** | `damage_pipeline/G2`, `hook_dispatch/G3`  |
| Porting **SovereignBlade**, **Hoarder** or **SoulFysh** (combat-pile watchers) | `creature_card_cmds/G8`  |
| Porting **any Sly card** | `creature_card_cmds/step51` (+ step 50's ordering)  |
| Porting **NoEnergyGainPower**'s `AfterModifyingEnergyGain`, or **BowlerHat**/**Ectoplasm**'s `AfterModifyingGoldGained` | `damage_pipeline/G2`  |
| Porting any `CardModel` with a **run-level hook** (`AfterRoomEntered`, `AfterRewardTaken`, `ShouldAddToDeck`) | `hook_dispatch/N5`, `creature_card_cmds/N3`  |
| A listener that **removes another listener mid-dispatch** | `hook_dispatch/G7`  |
| Porting a **multi-card transform** | `creature_card_cmds/step56`  |
| A **third `modify_power_amount` listener**, or Unsettling Lamp / Ruined Helmet widening | `power_cmd/G3`  |

## B. Content-tier triggers

| trigger — the unported thing | wakes |
|---|---|
| Porting the **Circlet** relic, or any content that drains a whole rarity deque inside one run | `event/EV-11` |

---

# Behaviour in no tier's scope

Holes are queue items too. The six seam records cover engine *machinery* and the
seven content tiers cover 680 units; the following is covered by nothing. It is
collected from `audit/seams/monster_state_machine.md`'s scope-boundary section
(the last seam, so the holes were gathered there) plus what aggregating the
tiers exposed.

1. **`EncounterModel` / monster-slot generation — the highest-value hole left.**
   Which monsters spawn, in what slots, with what HP roll, is claimed by no seam.
   `hook_dispatch` names `AfterCreatureAdded` and `monster_state_machine` names
   `SetUpForCombat`, but the *selection* is unaudited, and it is
   **RNG-consuming**. The monster tier hit it from three sides — the
   per-encounter `Rng`, `AddCreature`'s slot re-sort, and backwards egg-slot fill
   — and none of the three was visible from a monster model alone.
2. **No record owns the `combat_rng` stream map.** Several entries are "the sim
   draws from the wrong stream, or draws when the game does not", and each was
   found incidentally by whichever seam happened to touch the call site. Nothing
   audits the stream assignment as a subject. Given that stream desync is the
   highest-impact failure class in this queue, that is the largest *structural*
   hole here.
3. **`AbstractIntent` and the intent vocabulary.** `src/Core/MonsterMoves/Intents/`
   is unaudited: the sim collapses a C# `AbstractIntent[]` into one `Intent` with
   an `also` tuple (`monsters/base.py:36-59`) and nothing checks that mapping.
   `MonsterModel.IntendsToAttack` (`MonsterModel.cs:241-245`) reads the intent
   list and gates ported content, so a wrong mapping is a gameplay bug, not a
   display bug. The monster tier filed three mechanisms against it without
   auditing the mapping itself; of 45 moves one batch checked, 2 mismatched.
4. **`MonsterModel`'s non-machine surface** — `GenerateBestiaryMoveList`,
   `GetIntents`, `ResetStateMachine`, `CanonicalInstance`/`ToMutable`, HP
   generation and the Niche roll. Only `SetUpForCombat` / `OnSideSwitch` are
   claimed (by `turn_structure`). HP generation and the Niche roll are
   RNG-consuming, which puts part of this hole on the convergence path.
5. **Relic and card *content* has no seam.** `creature_card_cmds/G12` names two
   ported relics (Dragon Fruit, Lucky Fysh) whose sim implementations are inert
   stubs with docstrings that are no longer true. The seam records the missing
   hook; nothing owns the stubbed relic.
6. **The content tiers audit units, not the pools they are drawn from.** The card
   tier verdicts 202 cards; nothing verdicts `sts2_rl/cards/pool.py`'s
   composition, and the two are not separable — one event finding turned out to
   be that the wrong *factory* was used, a pool-side fact recorded on a
   card-generating event because that is where somebody happened to look.
7. **No tier owns the `_init_vars` convention** that `card/_printed_vars`' 23
   entries are all instances of. Each record states its own missing var; nothing
   states the rule, so the 24th card to be written can reintroduce it.
8. **`sts2_rl/full_env.py`'s observation encoder is audited by accident.**
   `card/_printed_vars` is dormant against the game and live against the encoder,
   and the card tier recorded that only because the encoder happens to read a
   field the tier was checking. Nothing systematically compares what the encoder
   reads against what the game would show.

**A prior worth keeping, from closing the "eleven unclaimed monster hook
overrides" hole:** of eleven `AbstractModel` overrides on C# monster models that
looked mechanical, **ten were presentation** — a music parameter, a barks line, a
`Sprite2D.Texture` assignment, an animation call — and one was a real gap. An
override that looks mechanical usually is not, and only reading it to the end
separates them. The trap in both directions: `LagavulinMatriarch.AfterDamageReceived`
was documented as "the wake-from-damage path" and is entirely presentation (the
wake is `AsleepPower.cs:21-36`), while `TestSubject.AfterDeath` is presentation
and its *mechanical* death behaviour lives in `AdaptablePower.AfterDeath`.

---

# Outstanding record defects

Rule-3 signals still true of the records on disk: a gap whose text
contradicts another record's, or its own. Each is **reported, not edited**,
and belongs to the stream that owns the record. The two tables here are
regenerated from the records, so a row disappears when the record is fixed.


- **`hook_dispatch/G7`'s executed evidence is from a stale tree.** It records the
  stale-listener plugin run as "the whole suite (2476 passed / 30 xfailed) and
  191,270 instrumented listener calls". The suite is thousands of tests larger
  now. The conclusion may still hold — the record says the run is reproducible
  from the committed tree — but **re-run it before relying on the "only one hit"
  claim**.
- **`monster_probes_b06.py`'s `probe_wither()` greps literally for
  `WitherCard(` and cannot see `make_card()`-style dynamic construction** —
  found while closing Aeonglass's `AfterCardGeneratedForCombat`, where the
  probe's "NOT LIVE, executed" verdict missed the Entropy-transform
  Wither route, which was already reachable. Any other dormancy verdict
  resting on a literal-constructor grep from that probe family should be
  re-derived against the dynamic construction paths before being trusted.
- **One RE-AUDIT paragraph pasted onto four entries, one of which it does not
  describe.** `damage_pipeline` steps 5, 9, 12 and guard G2 carry a
  byte-identical "RE-AUDIT 2026-07-25 … PARTIALLY RESOLVED" block whose subject
  is the **HpLost** variant. Step 5 is `AfterModifyingDamageAmount` — a different
  variant, and one the same paragraph later lists among the 12 that "remain
  absent". **The G2 rollup is the entry to trust.**
- **`power/withering_presence` cites a hover-tip property as the mechanism.** It
  names `WitheringPresencePower.cs:37` as where generated Withers are matched;
  that line is inside `ExtraHoverTips`, a preview. The real matching is
  `Aeonglass.AfterCardGeneratedForCombat`. PROMPT.md class 20 applied to a
  property.
- **`monster_state_machine/G7b`'s dormancy does not cover its own reachable
  case.** It was labelled dormant on a fuzz of 82 *machines*; Flyconid is
  hand-rolled, so the fuzz never saw it, and Flyconid's `RAND` reaches an
  all-zero weight vector on ported act-1 content on all five probe seeds. The
  port is faithful; the sim *machinery* raises. **Porting Flyconid onto
  `MachineMonster` — the convention this codebase prefers — would crash the run.**

- **2 records assert a deleted scope clause as a live premise**, carrying
  verbatim: "POTION IS NOT AN AUDITED KIND — there is no `potion` roster
  kind and no `audit/records/potion/`." Both halves are false. Records: `relic/alchemical_coffer`, `relic/phial_holster`.
  Distinguish these from the records that quote the clause as explicit
  "RE-VERDICTED … has been DELETED" history: that is correct and should stay.

- **28 `extra_sources` hashes should never have been written.**
  `citation_check.py` declares `_NEVER_HASHED = ("audit/tools/", "test/")`
  — the pipeline's own machinery and its pins are cited but not hashed,
  because a broken pin fails loudly on its own — and `backfill_sources.py`
  had no such exclusion. The consequence is false staleness: a record
  hashing `test/test_hook_order.py` goes stale whenever any pin is added
  anywhere in that file. The tool is fixed; **the prune is still owed.**
  Each stream runs
  `py audit/tools/backfill_sources.py --prune --no-add --kind <kind>`:

  | pinned path | records |
  |---|---|
  | `audit/tools/relic_probes.py` | `relic/mystic_lighter`, `relic/permafrost` |
  | `test/test_hive.py` | `power/surrounded` |
  | `test/test_hook_order.py` | `card/apotheosis`, `card/entrench`, `card/primal_force`, `relic/horn_cleat`, `relic/intimidating_helmet`, `relic/iron_club`, `relic/joss_paper`, `relic/orichalcum`, `relic/pen_nib` |
  | `test/test_ironclad_cards.py` | `card/feel_no_pain` |
  | `test/test_rng_tripwire.py` | `card/anointed`, `card/beat_down`, `card/discovery`, `card/distraction`, `card/havoc`, `card/hidden_gem`, `card/jack_of_all_trades`, `card/jackpot`, `card/metamorphosis`, `card/rip_and_tear`, `card/seeker_strike`, `card/splash`, `card/volley` |
  | `test/test_shared_enchantments.py` | `card/feel_no_pain`, `card/mad_science` |

---

# Appendix — regenerating this file

```
py audit/tools/gap_queue.py counts        # the summary tables
py audit/tools/gap_queue.py mechanisms    # every mechanism with its sites and pin
py audit/tools/gap_queue.py list          # every gap entry, one line, with liveness
py audit/tools/gap_queue.py unpinned      # the unpinned mechanisms
py audit/tools/gap_queue.py refs          # the raw cross-references in gap text
py audit/tools/gap_queue.py json          # the structured dump behind all of it
py audit/tools/gap_queue.py coverage      # every mechanism and entry appears here
py audit/tools/gap_queue.py cite-check    # every file:line here resolves
py audit/tools/harness.py validate <files>  # every record, 0 invalid
```

**`coverage` and `cite-check` are the two that fail loudly if this file drifts
from the records, and both must be run after any edit to it.**

**How the grouping is derived, and where to argue with it.** Every merge is
declared in `audit/tools/gap_queue.py` and carries the record text that asserts
it — nothing is grouped on an agent's hunch:

| table | what it merges | example |
|---|---|---|
| `_CROSS_RECORD` | mechanism keys two records declare to be one mechanism | `enchantment/BR-1` → `damage_pipeline/N3` → `hook_dispatch/G9` |
| `_TAG_MECHANISM` | a tier's `BR-` tag to the seam mechanism it cross-references | `event/BR-G3` → `creature_card_cmds/G3` |
| `_FAMILY_OVERRIDE` | one content entry the regex table would misfile | `power/thorns/BeforeDamageReceived` → `damage_pipeline/G1` |
| `_FAMILIES` | the recurring families in the untagged `power` and `card` tiers | body opening `SLOT` + `per-creature` → `turn_structure/G5` |

An over-split queue overstates the work; an over-merged one hides a job. The
tables lean split: anything a record does not explicitly tie to another
mechanism anchors its own, which is why most mechanisms are single-site and land
in Tier 3. Both failure directions are real — one merge over-merged four
mechanisms and under-merged two others, all six found by reading the generated
grouping against the records, which is the only check there is on a `_FAMILIES`
regex. Ordering matters: the narrow mechanisms have to precede the broad one.
