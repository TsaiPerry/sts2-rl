# Gap queue — every audited record, aggregated

Every `"verdict": "gap"` entry from `audit/records/**`, de-duplicated **by
mechanism**, ordered for work, and left **queued, not fixed** unless a campaign
is explicitly working it. Generated, not transcribed.

**Do not trust a count stated in prose anywhere in this project, including this
file. Re-run `py audit/tools/gap_queue.py counts`.**

## Round 12 (2026-07-31) — Tier 2 dormant gaps, 29 tasks

**The engine tier has no live gap left: 0 live entries across all six seam
records.** `damage_pipeline/G2`, which carried the last one, dropped to dormant
when Task 18 built the `AfterModifyingPowerAmount*` machinery.

| | start of round | round 12 branch | after merging main |
|---|---|---|---|
| gap entries | 626 | 439 | **372** |
| mechanisms | 478 | 416 | **349** |
| mechanisms with a live entry | 6 | 5 | **7** |
| **live entries in seam records** | **1** | **0** | **0** |
| suite | 3347 passed | 3766 passed | see below |

The third column is the merged truth and the one to trust. Round 12 branched
from `650c3202` while main went on to commit rounds 8-11; the merge combined
both, so the entry count fell further than round 12 alone achieved, and the
live count ROSE to 7 because main promoted two sites this branch never saw:
`relic/_auto_keep` (`relic/kifuda/g2`) and `relic/kifuda/AfterObtained` under
`relic/_stub`. **The headline survives the merge: 0 live entries in any seam
record.**

The 7 remaining live mechanisms are all content-tier:
`power/skittish/AfterAttack` (needs an AttackCommand-level hook the sim has no
analogue for), `event/crystal_sphere` x2 and `event/war_historian_repy/g2`
(deferred whole-event port stubs), `event/the_future_of_potions/g15` (new this
round, see below), and — carried in from main at the merge — `relic/_auto_keep`
plus the `relic/kifuda/AfterObtained` site under `relic/_stub`.

### What this round did NOT do

- **`damage_pipeline/G2` is dormant, not closed.** 7 of its 9 tracked variants
  are still uncovered, and **none of the 7 was re-verified this round** — they
  inherit dormancy from a prior round's execution.
- **Tier 2 is not finished.** 439 entries / 416 mechanisms remain, including
  two planned families nobody has started: the Play-pile family
  (`creature_card_cmds/N9`, `step99`, `step51`, `step56`) and the
  `hook_dispatch` registry family (`G1`+`G7`+`G5`+`G6`, then `N5`), which the
  queue's own radius note says "lands together or not at all".
- **The 129 unlabelled entries are still unlabelled.** Nobody has shown them
  dormant or live.

### Findings that outrank the fixes

- **A dormancy verdict was overturned (Task 30).** The playable-Status cluster
  was recorded dormant on a check of `pool_card_ids` and `curse_pool_ids`, but
  a third consumer existed — `transform_options_in_combat`'s STATUS branch, via
  ported Entropy — and it genuinely leaked four bad cards for every reachable
  Status card, including `frantic_escape`, which The Insatiable really does put
  in piles. Reproduced independently by implementer and reviewer.
- **A live gap was DISCOVERED, not inherited (Tasks 31/32).** Mid-event reward
  screens never dispatched the reward modifiers, so Driftwood's reroll silently
  did nothing on them. Two sites fixed; a third
  (`event/the_future_of_potions/g15`) is recorded **open** because it needs a
  reroll surface, not a missing call.
- **Two fixes introduced or nearly introduced new divergences, and the suite
  caught neither.** Task 20's first exhaust fix raised `ValueError` where the
  game performs a legal reposition (`CardPileCmd.Add` removes before it adds,
  so the contains-guard tests an emptied slot). Task 18's first pass fired both
  companion events before the power was registered, where C# registers first —
  plus a third facet, that C# wraps its whole tail in `if (CanReceivePowers)`.
  **All three were invisible to every existing test and only visible against
  the C#.** Green suites are not evidence here.
- **Records keep being wrong about their own reasoning, not just their
  numbers.** `power_cmd/G3`'s disjointness argument rested on a static-typing
  fact Task 17 had already deleted; the conclusion survived only through a
  clause the record never mentioned (Lamp is given-side, Ruined Helmet is
  received-side — never the same C# hook). Correct verdict, dead reasoning.

### Still open, found this round, owned by nobody

- `run.reward_offer_selector` is **never wired by `driver.py`** (set only in
  test files), so take-or-skip reward screens auto-accept in real play.
  Pre-existing and larger than the flag it was found beside.
- The sim dispatches reward modifiers at several construction sites where C#
  has exactly one choke point (`RewardsSet.GenerateWithoutOffering`). Task 32
  fixed per-site because consolidating was out of footprint; **the next event
  ported this way can reintroduce the same bug.**
- `PowerCmd.apply` is 28-42% slower after Task 18 (three dispatches where there
  was one). `end_turn` is a net 14.8% *faster*, but 147 files call `apply`.

## Status

`counts` reports **7 entries labelled LIVE** and **7 mechanisms with a live
site**, none of them in a seam record. That is a statement about what the
records CLAIM, not about what is reachable, and the gap between those two
things is the remaining work:

| liveness | entries | what it means |
|---|---|---|
| labelled LIVE | 7 | all content-tier; 4 are deferred port stubs |
| labelled DORMANT | 309 | a real divergence, argued unreachable on today's content |
| **unlabelled** | **56** | **neither — nobody has shown these dormant** |

Round 12 showed the dormant label is not safe either: one mechanism labelled
dormant on an incomplete consumer census turned out to be reachable. Re-execute
before trusting any liveness claim, including a dormant one.

### Where to start

1. **The 212 unlabelled entries.** `py audit/tools/gap_queue.py list` prints
   each entry's liveness. Settle each by execution: either fix it, or replace
   the silence with a dormancy *enumeration* (see below). The one worked slice
   ran 4 stale / 4 real, so budget for both.
2. **[Tier 1](#tier-1--the-largest-multi-site-families)** — the ten widest
   families, all of which still have sites open.
3. **[Tier 2](#tier-2--dormant-gaps)**, then
   **[Tier 3](#tier-3--the-long-tail)**.

### Named work with no entry of its own

- **`power_cmd/G2`** blocks the `ModifyPowerAmountGiven` / `Received` chains —
  i.e. `power_cmd/G4` and the ten `AfterModifying*` variants under
  `damage_pipeline/G2`. Fix it first if you touch either.
- **`Hook.AfterModifyingCardPlayCount`** has no sim dispatcher at *any* site,
  including the normal play path.
- **`card/spoils_map` vs `Hook.ModifyGeneratedMapLate`.** The sim dispatches a
  Late map pass whose only game caller is the save-load branch
  (`RunManager.cs:740`), because Spoils Map folds its Treasure-coord recording
  into it. Documented at the dispatch site; no entry.
- **`card/sweep`** has no audit record. It is sim-only.
- **`card/breakthrough` is an uncounted 6th `card/_is_dead_early_return`
  site** (found 2026-07-31): `breakthrough.py`'s top-level `if
  ctx.player.is_dead: return` right after the self-damage is structurally
  identical to the three closed in Task 27 and safe to delete by the same
  reasoning; the card's own record covers only its enemy-filter and
  per-enemy break guards. One deletion plus a pin when someone owns it.
- **`combat.py`'s turn-end-in-hand `on_card_discarded` — REMOVED 2026-07-31**
  (Task 11): its C# counterpart `CardModel.OnTurnEndInHandWrapper`
  (CardModel.cs:1682-1698) calls `CardPileCmd.Add` directly and fires no
  `AfterCardDiscarded`; the hook's sole C# site is `CardCmd.cs:194`. The
  dispatch is gone and the affected turn-structure test now triggers its kill
  through `on_damage_received` at the same pipeline point. Filed here for the
  record; nothing outstanding.
- **`monster/vantom` DISMEMBER carries `StatusIntent(3)` with no site entry**
  (found 2026-07-30 closing `monster/_intent_count_lost`): a genuine 4th site
  of that mechanism — `Vantom.cs:119` — uncounted by the record's 3-site
  list. One `status_count=3` edit in `vantom.py` when someone owns it.
- **`selectors.py` "to_draw_top" ranks by raw `energy_cost`** (found closing
  `card/_unplayable_cost`, 2026-07-30): `scripted_card_selector`'s
  Headbutt/Thinking-Ahead tie-break reads `card.energy_cost` unclamped, so an
  unplayable card (now canonically `-1`) ranks below a genuinely-free card
  instead of tying at 0. Sim-only heuristic, no C# analogue, no test
  exercises a curse on that path. One-line clamp when someone owns
  `selectors.py`; details in the `card/_unplayable_cost` close notes.
- **`creature_card_cmds/G8` is narrowed, not closed.** `Hook.AfterCardChangedPiles`
  exists and is dispatched at one of C#'s four sites (the transform). The other
  three — `CardPileCmd.cs:635` Add, `:188` RemoveFromCombat, `:683` the manual
  play — are a wiring job. Deliberately left: the Add site is the DRAW path, the
  sim's hottest loop, and every ported listener filters to the Deck pile.

### How this queue has been wrong before

Ten rounds of fix campaigns have produced the same failure modes over and over.
They are worth more than any single entry below.

- **Staleness is the largest category, eight rounds running.** Roughly one entry
  in four turns out to be already fixed. **Start every unit by re-executing the
  entry's own witness**, not by reading its prose. An entry is only as current as
  the last change to the code it was written against.
- **A dormancy argument is worth much less than an enumeration.** "No ported
  listener can see this" is a claim; "all 13 overrides of this hook ignore the
  parameter" is a fact. Several dormancy labels have been correct only by
  accident, resting on a false premise about the sim or the source.
- **A no-op stub's stated premise is usually false** (PROMPT.md class 12). All
  twelve checked in one round were: gold exists, enchantments exist, the hook
  exists, the dispatch exists.
- **When a pin and the C# disagree, the C# wins.** Four pins on this project have
  been wrong, and one of them was hiding a regression the same pass introduced.
- **Two records disagreeing about one mechanism has four times meant neither was
  right.** Resolve a grep hit to its enclosing *member*; never count matches.
- **Tooling defects are found by unit work, never by tool review.** Five rounds
  running. If a probe disagrees with an execution, suspect the probe.

The round-by-round history of what closed when is in the git log and in
`docs/superpowers/plans/`; it is deliberately not kept here.

## What this queue does NOT cover

Every content kind is audited and aggregated:

| kind | units | records | note |
|---|---|---|---|
| seam (engine) | 6 seams | 6 | |
| power | 138 | 138 | |
| card | 203 | 202 | `card/sweep` is sim-only and has no record |
| event | 65 | 65 | |
| enchantment | 17 | 19 | the first kind with **zero** gap entries |
| relic | 258 | 258 | |
| monster | 109 | 109 | |
| potion | 51 | 51 | |

`py audit/tools/audit_status.py` is the authority on coverage; this table is a
transcription of it and can go stale.

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

Two integrity lessons from how those holes were found, both still live risks:

- **Never express scope as an exclusion.** While "potions are out of scope"
  stood, ten `card` and `power` entries waived real behaviour on it while the
  `relic` tier filed 45 potion-mechanic gaps — one mechanism, two answers,
  caused by the contract itself. It also protected a false claim:
  `damage_pipeline/N4` waived the two-phase `ShouldDie` ordering because Fairy in
  a Bottle was "out of scope", and the potion is ported. *Unaudited* is a fact
  the tools report; *out of scope* was a claim that hid things.
- **`gap_queue.py` keeps its own `CONTENT_KINDS` list**, not derived from the
  harness, so it can silently omit a kind — it omitted `potion` for a day while
  51 finished records sat on disk, and `coverage` / `cite-check` printed their
  complaints and exited 0 while it did.
  `test/test_audit_status.py::TestQueueGeneratorCoversEveryKind` pins the kind
  lists together now, and both commands return their exit code. Adding a kind
  means editing both.

## Summary

| | |
|---|---|
| gap entries across all 848 records | **646** |
| — labelled LIVE | **0** |
| — labelled DORMANT | 434 |
| — unlabelled (inherit their mechanism's liveness) | 212 |
| **distinct mechanisms** | **484** |
| — with at least one live site | **0** |
| mechanisms pinned by a `strict=True` xfail | **0** |

Per kind (records / gap entries / mechanisms anchored there):

| kind | records | entries | mechanisms |
|---|---|---|---|
| `seam` | 6 | 105 | 64 |
| `power` | 138 | 161 | 130 |
| `card` | 202 | 98 | 44 |
| `event` | 65 | 13 | 13 |
| `enchantment` | 19 | **0** | **0** |
| `relic` | 258 | 225 | 213 |
| `monster` | 109 | 18 | 6 |
| `potion` | 51 | 26 | 14 |

Per seam record:

| record | entries | mechanisms |
|---|---|---|
| `damage_pipeline` | 8 | 6 |
| `power_cmd` | 17 | 7 |
| `creature_card_cmds` | 48 | 29 |
| `turn_structure` | 12 | 10 |
| `hook_dispatch` | 16 | 9 |
| `monster_state_machine` | 4 | 3 |

**The xfail count is 0.** That is not "no gaps left" — it is "every mechanism
that had an acceptance test now passes it". All 484 mechanisms are unpinned,
which is the coverage problem `audit/README.md` has flagged since the seam tier:
**a gap with no pin cannot prove its own fix.** Adding a pin as a gap is worked
remains the cheapest way to stop that rotting.

---

## How to read an entry

```

### <mechanism id>  — <one-line name>                     [DORMANT] [pinned|unpinned]
still open (Tier 1 only) which of the mechanism's sites are STILL OPEN today
sites      every gap entry that is this same mechanism (the stable ids)
impact     A / B / C — see Ordering
divergence one sentence, sim file:line vs C# file:line
observable what a player or a replay sees; executed numbers where the record has them
trigger    (dormant only) the concrete unported thing that makes it live
pin        the strict xfail in test/test_hook_order.py that flips to passing, or why not
fix        which sim file changes and roughly how; what the failing test asserts
radius     other mechanisms sharing machinery; content units the record names
```

**Stable ids.** A seam entry is `<seam>/<step-or-guard-id>` —
`hook_dispatch/G9`, `creature_card_cmds/G14`. A content entry is
`<kind>/<unit>/<local>`, where `<local>` is the C# hook name for a hook verdict
(`power/adaptable/AfterDeath`), the record's own guard tag where the tier uses
one (`event/aroma_of_chaos/EV-3`, `enchantment/clone/EG2`), and `g<n>` — the
1-based index in the record's `guards` list — where it does not
(`power/diamond_diadem/g1`).

**Mechanism ids** are the anchor entry's id, except for the recurring content
families that no record numbers, which get a `_`-prefixed synthetic key:
`power/_side_turn_slot`, `card/_unplayable_cost`. Every merge — including
every cross-kind one — is declared in `audit/tools/gap_queue.py` with the
record text that asserts it, in `_CROSS_RECORD`, `_TAG_MECHANISM`,
`_FAMILY_OVERRIDE` or `_FAMILIES`. Nothing is grouped on an agent's hunch.

**Watch the id collisions.** `G8` is the missing `IsEnding` gate in
`hook_dispatch` but the missing AutoPrePlay/AutoPostPlay phases in
`turn_structure`; `G2`, `G3`, `G4`, `G9` and `N5` all mean different things in
different records. Always carry the prefix.

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

The document has three tiers. **Nothing in any of them is labelled live any
more**, so the ordering is by blast radius and convergence exposure alone:

1. **[Tier 1 — the largest multi-site families](#tier-1--the-largest-multi-site-families)**,
   written out in full. Ten mechanisms, one fix each clearing many sites.
2. **[Tier 2 — dormant gaps](#tier-2--dormant-gaps)**, written out in full,
   grouped by the machinery they share.
3. **[Tier 3 — the long tail](#tier-3--the-long-tail)**, one row per remaining
   mechanism. Single-site, single-unit findings: real, recorded, verified, and
   cheaper to read straight out of the record than to restate. The row gives the
   id, the liveness and the record's own lead clause.

`py audit/tools/gap_queue.py coverage` asserts that every mechanism and every
one of the 646 entries is locatable here, so the tail cannot silently shrink.

---

# Tier 1 — the largest multi-site families

The ten mechanisms with the widest blast radius. Every one was worked in the
Tier 1 campaign and every one still has sites open: **32 entries, 17 labelled
dormant and 15 unlabelled**. The unlabelled ones are unproven, not argued — the
last campaign found 4 real gaps in the 8 unlabelled sites it checked here.

**Read the bodies as briefs, not as current state.** They were written while the
mechanism was live and are in the present tense; the `divergence`, `observable`,
`fix` and `radius` fields are still the best writeup of each, but the
**`still open`** line at the head of every entry is the only current thing in
it. `py audit/tools/gap_queue.py counts` is the authority.

## 1A. Grade A — stream desync

A wrong draw count or a wrong stream. These are the ones that stop a replay
converging outright, which is the work this pipeline exists to unblock.

### `event/EV-3` — the per-event `Rng` replaced by the shared run stream  [DORMANT] [**unpinned**]

- **still open** 1 of 28 sites: `event/jungle_maze_adventure/EV-3` (dormant) — the `_fx.ToList().StableShuffle(base.Rng)` in DontNeedHelp's tail.
- **sites** 28 entries on 28 event records (`aroma_of_chaos`, `battleworn_dummy`,
  `dense_vegetation`, `doll_room`, `doors_of_light_and_dark`, `endless_conveyor`,
  `fake_merchant`, `infested_automaton`, `jungle_maze_adventure` ×2, `lost_wisp`,
  `luminous_choir`, `morphic_grove`, `punch_off`, `ranwid_the_elder`,
  `reflections`, `relic_trader`, `room_full_of_cheese`, `slippery_bridge`,
  `stone_of_all_time`, `sunken_statue`, `sunken_treasury`, `symbiote`,
  `the_future_of_potions`, `this_or_that`, `trash_heap`, `trial`,
  `welcome_to_wongos`).
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

A number, a hand, a pile or a deck entry differs. The next conformance assert
fires; the stream itself survives.

### `power/_death_prevention_branch` — death prevention runs the wrong branch, and `AfterDeath` never fires  [DORMANT] [**unpinned**]

- **still open** 4 of 15 sites: `power/adaptable/g5`, `power/illusion/g6`, `power/steam_eruption/g4` (all three **unlabelled** — the prevention branch's HP contract, sim `hp = 1` vs C# leaving the creature at 0) and `monster/test_subject/g1` (dormant — `RespawnMove`/`Revive` going through `CreatureCmd.SetMaxHp` + `Heal` rather than a raw assignment).
- **sites** 10 entries on `power/adaptable`, `power/illusion`,
  `power/steam_eruption` — hooks `AfterDeath`,
  `ShouldCreatureBeRemovedFromCombatAfterDeath`, plus the shared HP-contract and
  non-damage-kill guards on each record.
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
- **monster sites added 2026-07-27** 5, taking the mechanism to **15**:
  `monster/eye_with_teeth` (Fogmog's summoned Eye, via `IllusionPower`),
  `monster/parafright` (the same), `monster/waterfall_giant` (via
  `SteamEruptionPower`), and `monster/test_subject` twice — its
  `TriggerDeadState` and its `RespawnMove`/`Revive` observable, which the
  record separates because the second survives any fix that only re-slots the
  `AfterDeath` body. Executed on the boss with a ported Gremlin Horn attached:
  the sim dispatches `on_death` **once** across the three-form fight where the
  game dispatches `Hook.AfterDeath` **three** times, so the relic pays 1 energy
  + 1 card instead of 3 + 3; the revive delta is **+199 vs +200** because the
  sim floors the corpse at 1 HP (`cmds.py:112`) where C# leaves it at 0; and
  `RemoveAllPowersAfterDeath` never runs, so Enrage 2 and all its stacked
  Strength survive two resets the game wipes.
- **the counter-example is the useful half** `monster/decimillipede_segment` is
  **correct**: `ReattachPower` lands on `should_remove_from_combat_after_death`,
  not on `should_die`. Executed — a killed segment fires `on_death`, sets
  `retained_after_death=True` and keeps taking turns (DEAD → REATTACH → WRITHE →
  CONSTRICT → BULK). **PROMPT.md class 21 names the wrong landing site and not
  the right one; this is the right one.**


### `hook_dispatch/G3` — no Early / VeryEarly / Late phase passes  [DORMANT] [pinned]

- **still open** 3 of 7 sites: `hook_dispatch/step46` (unlabelled), `power/hellraiser/AfterCardDrawnEarly` and `relic/tungsten_rod/g3` (`ModifyHpLostAfterOsty` is the first of C#'s two HP-loss passes).
- **sites** `hook_dispatch/step27`, `/step28`, `/step29`, `/step30`, `/step46` (5 entries).
- **content sites** **+2 power sites**, `power/corruption/TryModifyEnergyCostInCombatLate` and `power/hellraiser/AfterCardDrawnEarly` — the phase leg of the power tier's slot census. 7 entries in all.
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


### `turn_structure/G13` — no `CheckWinCondition` after the turn-1 setup  [DORMANT] [pinned]

**Mostly closed 2026-07-29 (round 5).** All six C# sites are recomputations now, and the four inline `_all_enemies_dead()/is_dead` pairs — which were `CheckWinCondition` with the tie-break the wrong way round — call it instead. Step 16's `SetupPlayerTurn` IsDead guard is ported; step 60's needs no separate line in a one-player sim and is pinned by test. What follows is the text as it stood.

- **still open** 3 of 9 sites: `turn_structure/step29` and `/step51` (both unlabelled — the enemy-side and `DoTurnEnd` checks) and `relic/festive_popper/g3` (the port hand-rolls `self._check_win()`).
- **sites** `turn_structure/step16`, `/step27`, `/step29`, `/step41`, `/step49`,
  `/step51`, `/step56`, `/step60`, `/G13` (9 entries).
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


### `damage_pipeline/G3` — pipeline-level `is_powered_attack` gate  [DORMANT] [pinned]

- **still open** 4 sites, three of them unlabelled: `relic/fake_strike_dummy/ModifyDamageAdditive`, `relic/strike_dummy/ModifyDamageAdditive`, `relic/vambrace/ModifyBlockMultiplicative` and `relic/sparkling_rouge/g1`.
- **sites** `damage_pipeline/G3`, `creature_card_cmds/step13`, `creature_card_cmds/G1` (3 entries).
- **content sites** **+1 enchantment site**, `enchantment/nimble/BR-6`, naming `BlockCmd.apply` (`sts2_rl/cmds.py:145-147`) as the block-side dispatch that skips the gate. 4 entries in all.
- **impact** B — block totals differ on ported content.
- **divergence** `cmds.py:56-58` (damage) and `cmds.py:145-147` (block) skip the
  *entire* modifier dispatch when `is_powered_attack(props)` is false; C#'s
  `ModifyDamageInternal` (`Hook.cs:2515-2538`) and `ModifyBlock`
  (`Hook.cs:1310-1340`) always call every listener and leave the gate to each
  implementation.
- **observable** Dexterity, Frail and Fasten self-gate identically in both
  codebases, but **Vambrace** (`Vambrace.cs:59-63`) and **Pael's Legion**
  (`PaelsLegion.cs:132-134`) self-gate only on `IsCardOrMonsterMove()` — Move
  alone, ignoring Unpowered. Entrench is a ported Ironclad event card that gains
  block with `MOVE|UNPOWERED` (`cards/trash_heap_cards.py:159-179`), and Vambrace
  is a ported Uncommon relic: the game doubles Entrench's block, the sim does
  not. On the damage side the same gate silently drops `SurroundedPower`'s ×1.5
  (Kaiser Crab, `powers.py:2523-2565`) for any Unpowered dealer-attributed hit.
- **pin** `TestCreatureCardCmdsOrder::test_unpowered_card_block_still_runs_block_modifiers`.
- **fix** Delete the two pipeline-level gates and push `is_powered_attack` into
  each listener that needs it — Strength, Vulnerable, Weak, Dexterity, Frail,
  Fasten self-gate; Vambrace, Pael's Legion and Surrounded must not. Failing test
  asserts Vambrace doubles an Entrench block gain.
- **radius** Same two call sites as `hook_dispatch/G9` (aggregation shape) and
  `damage_pipeline/G2` (modifier notification) — one editing pass over
  `cmds.py:56-58` / `145-147` and `hooks.py:52-122` can land all three.


### `damage_pipeline/G2` — no `AfterModifyingXxx(modifiers)` companion events  [DORMANT] [pinned]
**NO LONGER LIVE 2026-07-31 (tier-2 campaign, Task 18) — but STILL AN OPEN
DORMANT GAP, not closed.** This mechanism carried the queue's last live engine
verdict, and it carried it entirely through the PowerAmountGiven/Received edge
recorded as `power_cmd/G4` (binding rule 3). Task 18 built that machinery, so
**the seam tier now has zero live entries across all six seam records.** The
arithmetic, stated exactly because the earlier text invited miscounting:
`Hook.cs` declares 13 `AfterModifying*` variants; 4 declarations (Block,
Damage, HpLostBeforeOsty, HpLostAfterOsty) were already covered by 3 sim hooks
and were **never part of the 9** this entry tracks; of those 9, Task 18
implemented 2, leaving **7** — CardPlayCount, CardRewardOptions, EnergyGain,
GoldGained, HandDraw, OrbPassiveTriggerCount (Defect-only, waived under N3) and
Rewards. Each was already dormant on its own executed merits and **none was
re-verified this round**. What follows is the text as it stood.

- **still open** 7 sites, five unlabelled: `damage_pipeline/G2`, `power_cmd/step21`, `power_cmd/step22`, `power_cmd/step31`, `power_cmd/step32`, `power_cmd/G4` and `hook_dispatch/step38`. **Blocked on `power_cmd/G2`.**
- **sites** `damage_pipeline/step5`, `/step9`, `/step12`, `/G2`;
  `power_cmd/step21`, `power_cmd/step22`, `power_cmd/step31`, `power_cmd/step32`, `/G4`;
  `creature_card_cmds/step15`, `/G2`; `hook_dispatch/step38` (**12 entries** —
  the second-largest mechanism in the queue).
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

Four families that arrived with the relic tier, kept together because they were
one merge and share one shape. The relic tier is where the queue's collapse
ratio is most extreme — fixing one site of any of these generally clears every
site, which is why three of the four are nearly closed.

### `relic/_is_allowed` — `Relic` has no `is_allowed` member at all  [DORMANT] [**unpinned**]

- **still open** 2 of 34 sites, both on one relic: `relic/lasting_candy/IsAllowed` and `/g3` (the `Character is Ironclad && UnlockState` clause).
- **sites** 34 entries across 19 relics (`toxic_egg`, `frozen_egg`, `molten_egg`,
  `girya`, `shovel`, `old_coin`, `dragon_fruit`, `lucky_fysh`, `meal_ticket`,
  `planisphere`, `lasting_candy`, `white_star`, `white_beast_statue`,
  `book_of_five_rings`, `bowler_hat`, `juzu_bracelet`, `amethyst_aubergine`,
  `large_capsule`, `regal_pillow`).
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


### `relic/_stub` — 21 relics ported as no-ops on premises that are now false  [DORMANT] [**unpinned**]
**Closed 2026-07-31 (tier-2 campaign, Task 31) — 1 of the 4 remaining sites was
a FALSE PREMISE, the other 3 stay open as genuine-but-dormant.** `royal_stamp`
is not a stub at all any more: it carries a complete `after_obtained` (Niche
shuffle + `RoyallyApprovedEnchantment` attach), already pinned by
`test_shared_enchantments.py::test_royal_stamp_enchants_a_deck_card_and_burns_the_niche_shuffle`,
which the task reviewer named and ran — so the heading's "the last two still
carry the false premise 'the sim has no enchantments'" is now true of
`punch_dagger` alone. `bing_bong` (needs an adder argument threaded through
`after_card_added_to_deck`; C# has exactly TWO non-null `clonedBy` call sites in
the whole tree, BingBong itself and the unported `Hoarder.cs:26`),
`massive_scroll` (no MultiplayerOnly card pool ported) and `punch_dagger` (port
correct; stale docstring numbers fixed) were each re-executed and deliberately
LEFT OPEN rather than closed — the divergences are real, just unreachable.
What follows is the text as it stood.

- **still open** 4 of 23 sites: `relic/bing_bong/g1`, `relic/massive_scroll/g4`, `relic/punch_dagger/g1` and `relic/royal_stamp/g1` — the last two still carry the false premise 'the sim has no enchantments'.
- **sites** 23 entries across 21 relics (`old_coin`, `meal_ticket`,
  `mystic_lighter`, `planisphere`, `lava_lamp`, `prayer_wheel`, `tiny_mailbox`,
  `white_beast_statue`, `white_star`, `lucky_fysh`, `bowler_hat`, `cauldron`,
  `potion_belt`, `punch_dagger`, `regal_pillow`, `royal_stamp`, `wing_charm`,
  `amethyst_aubergine`, `bing_bong`, `book_of_five_rings`, `massive_scroll`).
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


### `relic/_reward_late_pass` — the two-pass reward dispatch collapsed into one  [DORMANT] [**unpinned**]
**Closed 2026-07-31 (tier-2 campaign, Task 31), all 3 remaining sites — and it
SPUN OFF A NEW LIVE GAP.** Driftwood's guard G1 is resolved:
`RunState.rest_heal_rewards` dispatches `apply_reward_modifiers`
(`run.py:1417-1419`), matching `RewardsSet.GenerateWithoutOffering`
(`RewardsSet.cs:136`) — verified against `git show HEAD:sts2_rl/run.py` to be a
real pre-existing staged fix rather than an asserted one. Glitter (G1,
clone-vs-mutate) and Molten Egg (G4, upgrade-level filter) are unrelated guards,
re-confirmed dormant. **The new finding:** `events/brain_leech.py` and
`events/trial.py` build `CombatRewards` directly and hand them to
`driver.py._run_event`'s mid-event `pending_rewards` channel, which offers them
WITHOUT that dispatch — so Driftwood's reroll is unavailable on those screens
even though both events and Driftwood are ported and reachable. Confirmed live
by the task reviewer and fixed under its own task this round. What follows is
the text as it stood.

- **still open** 3 of 24 sites: `relic/driftwood/TryModifyRewardsLate` (unlabelled), `relic/glitter/TryModifyCardRewardOptionsLate` and `relic/molten_egg/TryModifyCardRewardOptionsLate`.
- **sites** 24 entries across 15 relics (`toxic_egg`, `frozen_egg`,
  `molten_egg`, `silken_tress`, `silver_crucible`, `wing_charm`, `glitter`,
  `fresnel_lens`, `lava_lamp`, `driftwood`, `glass_eye`, `lasting_candy`,
  `lava_rock`, `white_star`, `wongos_mystery_ticket`).
- **impact** B — reward contents differ.
- **divergence** C# dispatches rewards twice — `TryModifyCardRewardOptions` and
  then `TryModifyCardRewardOptionsLate` (likewise `TryModifyRewards` /
  `…Late`) — and the ordering between the two passes is load-bearing when one
  relic's output is another's input. The sim has a single pass, so the outcome
  falls out of listener registration order.
- **observable** The egg relics upgrade reward offers in the late pass; a relic
  that *adds* an option in the early pass must be visible to them. With one pass,
  whether it is depends on which relic registered first.
- **pin** Unpinned. Pinnable: two relics, one adding and one upgrading, assert
  the added card is upgraded.
- **fix** Split the dispatch. Same shape as `hook_dispatch/G3`'s phase passes.
- **radius** 15 relics; also the mechanism behind several "wax relic" oddities.


### `relic/_combat_reset` — per-combat relic state is never reset  [DORMANT] [**unpinned**]

- **still open** 1 of 16 sites: `relic/forgotten_soul/g1` — `CombatState.HittableEnemies` vs the sim's `living_enemies()`.
- **sites** 16 entries across 13 relics (`red_skull`, `permafrost`, `vambrace`,
  `centennial_puzzle`, `ruined_helmet`, `paels_tears`, `burning_sticks`,
  `belt_buckle`, `paels_eye`, `paels_legion`, `self_forming_clay`,
  `diamond_diadem`, `forgotten_soul`, `joss_paper`).
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

# Tier 2 — dormant gaps

Dormant at every recorded site: the divergence is real and verified, but no
currently-ported content reaches it. Each names the concrete thing that makes
it live, collected in the
[dormant-trigger watch list](#dormant-trigger-watch-list). Ordered by
seed-convergence exposure first, then by blast radius.

Sections 2A–2I are the engine seams; **2J is the content tiers**, whose dormant
families are far larger per mechanism because one decision is recorded on every
unit it touches.

## 2A. Parity-relevant dormant gaps — extra or off-stream RNG draws

These are labelled dormant because no *gameplay* effect differs today, but each
one takes a draw the game does not take, or takes it from the wrong stream.
Under legacy single-stream RNG that is invisible; under seed parity it is a
desync. **Read this group before the next conformance grind.**

### `creature_card_cmds/N10` + `/step104` — CardSelectCmd's auto-select shortcut  [DORMANT / parity-live] [unpinned]

**Closed 2026-07-30 (tier-2 campaign).** `CombatState.select_cards`
(`sts2_rl/combat.py`) now has the auto-select shortcut (`!RequireManual-
Confirmation && candidateCount <= MinSelect` -> every candidate, pile order,
zero draws), checked before the installed-selector branch — mirrors all
three C# sites (`CardSelectCmd.cs:287-290, 396-399, 708-711`).
`RequireManualConfirmation` is derived the way `CardSelectorPrefs.cs:77`
does, from the sim's pre-existing `min_select` parameter. The selectorless
RNG fallback now branches on `combat_rng.is_parity`: legacy stays on
`self._rng` byte-for-byte (unchanged algorithm and object); parity moves
onto `combat_rng.card_selection` via a new draw-without-replacement helper
(`GameRandomAdapter` has no `.sample()` — this selectorless path has no C#
analogue at all, since real `CardSelectCmd` always shows a screen or waits
on the network). The draw-pile pre-sort (`CardSelectCmd.cs:403-408`,
`orderby c.Rarity, c.Id`) is a new opt-in `is_draw_pile` flag on
`select_cards`, wired at every `FromCombatPile(Draw, ...)` call site found
by reading the C# directly: SecretTechnique/SecretWeapon, Wish (not
previously cited by this record), Seeker Strike (its own C# source turned
out to also route through `FromCombatPile(Draw, ...)`, not just the
shuffle the sim's comment described), and DropletOfPrecognition. Verified
the "rarity/id sort" claim against `CardRarity.cs` (a declaration-order
enum) rather than trusting it — the sim's own `CardRarity` enum lists
members in a different order, so a `_CS_RARITY_ORDER` map keyed to C#'s
ordinal was required. NOT modelled: a general `CardSelectorPrefs`/UI screen
object; `MaxSelect` as a field distinct from `count` (redundant — `count`
already plays that role). Pinned by
`test/test_engine_features.py::TestCardSelectionAutoSelectShortcut` (6
tests) and `::TestCardSelectionDrawPilePreSort` (2 tests), plus three new
parity-stream tests in `test/test_combat_rng.py`. Suite: 2 failed
(pre-existing 933T conformance fixture, unrelated) / 3373 passed / 6
xfailed — no regressions.

**POST-REVIEW ADDENDUM (same day).** Review caught two IMPORTANT gaps: (1)
NeowsFury's `0..2` range (`NeowsFury.cs:39`, `CardSelectorPrefs(prompt, 0,
num)`) was wrongly left un-wired (the paragraph above originally called this
"a pre-existing per-card gap, not this shared mechanism" — wrong, it's an
instance of this exact mechanism and had to be fixed here). Fixed by adding a
`min_select` passthrough to `CardSelectCmd.from_pile` and passing
`min_select=0` at the NeowsFury call site, with `test/test_neow.py`'s
pre-existing `test_neows_fury_card` updated (a genuine `0..2` range now
legitimately varies without a selector, so it installs
`scripted_card_selector`) plus a new statistical companion test. (2)
`select_cards`' shortcut was wrongly default-on for `CardSelectCmd
.FromChooseACardScreen`-mapped purposes (`CardSelectCmd.cs:216-261` has no
shortcut at all): fixed with a new `has_shortcut: bool = True` parameter,
`False` at every FromChooseACardScreen call site (Discovery, Splash, the four
generator potions, Toolbox, Knowledge Demon's curse pick). Re-checking
Choices Paradox's own C# source during this fix found it actually calls
`FromSimpleGrid` (which DOES have the shortcut), not `FromChooseACardScreen`
as `selectors.py`'s docstring and this note's first draft both wrongly
claimed — corrected in place, Choices Paradox keeps the default
`has_shortcut=True`. Plus one MINOR test gap: a pin that the shortcut's
draw-pile return is unsorted pile order (the shortcut runs before the
pre-sort in C# too). New tests:
`test_neows_fury_shaped_selection_does_not_shortcut_with_a_selector`,
`test_neows_fury_shaped_selection_without_a_selector_still_draws`,
`test_choose_a_card_shaped_selection_never_shortcuts`,
`test_choose_a_card_shaped_selection_without_a_selector_still_draws`,
`test_draw_pile_shortcut_returns_unsorted_pile_order` (test_engine_features.py)
and `test_neows_fury_selectorless_range_can_return_fewer_than_the_max`
(test_neow.py). Suite after this addendum: 2 failed (same fixture,
unrelated) / 3380 passed / 6 xfailed — no regressions. What follows is the
text as it stood.

- **sites** `creature_card_cmds/step104`, `/step105`, `/N10` (3 entries; step 105 sits under N10).
- **divergence** C#'s auto-select shortcut (`!prefs.RequireManualConfirmation &&
  candidateCount <= prefs.MinSelect` -> return every candidate in pile order,
  `CardSelectCmd.cs:287-290, 396-399, 708-711`) consumes **nothing** from any
  stream; `CombatState.select_cards` (`combat.py:560-581`) has no shortcut — it
  clamps `count = min(count, len(candidates))` (`combat.py:577`) and, with no
  `card_selector` installed, falls through to `self._rng.sample(candidates, count)`
  (`combat.py:581`).
- **observable** The same *membership*, reached by burning draws C# never takes,
  **and taking them off-stream** on the shared legacy `random.Random` rather than
  `combat_rng.card_selection`. Also missing: the MinSelect/MaxSelect range, the
  `RequireManualConfirmation` flag, and C#'s draw-pile pre-sort
  (`CardSelectCmd.cs:403-408`) — an installed selector sees the true draw order
  where C#'s would see a rarity/id sort.
- **trigger** Already reachable in any replay containing a forced full-hand
  selection; "dormant" here means no *gameplay* divergence, not no desync.
- **pin** unpinned. A conformance-side pin is the right home, not `test_hook_order.py`.
- **fix** Add the auto-select shortcut to `select_cards` (return all candidates,
  in pile order, drawing nothing) and move the fallback onto
  `combat_rng.card_selection`. Failing test: a forced selection of every
  candidate consumes zero draws from any stream.
- **radius** `creature_card_cmds/step99` (`AutoPlayFromDrawPile`'s two-phase
  structure), `/G10` (shuffle order). Any replay through a grid/selection screen.

### `creature_card_cmds/step55` — the in-combat transform rolls off-stream  [DORMANT / parity-live] [unpinned]

**RE-VERIFIED 2026-07-30 (tier-2 Task 4) — found already closed.** Witness
re-execution against today's `sts2_rl/cmds.py` shows both clauses fixed, and
the audit record (`audit/records/seam/creature_card_cmds.json`, step 55)
already carried a closure note from an earlier round predating this task;
this pass independently re-derived it rather than trusting that note, then
added the regression coverage that did not previously exist. STREAM HALF:
`transform_to_random` (cmds.py) rolls the replacement on
`hooks.combat.combat_rng.card_selection.choice(options)`, the named
CombatCardSelection stream `EntropyPower.cs:31` passes as the explicit `Rng`
argument (`CardCmd.cs:323`) — not the shared legacy `_rng`. C# call-site
enumeration (`grep -rn "TransformToRandom(" src/`) found `EntropyPower.cs:31`
is the ONLY ported IN-COMBAT caller; the six Events (AromaOfChaos,
EndlessConveyor, MorphicGrove, Symbiote, Trial, WhisperingHollow, all
`base.Rng`) and the New Leaf relic's `AfterObtained` (`RunState.Rng.Niche`)
are also ported but are run-level pickups/events that call
`RunState.transform_card` (run.py) out of combat — out of this seam,
untouched. `CombatRng.legacy` (`combat_rng.py:39`) aliases every named
accessor, card_selection included, to the identical shared `_rng` object, so
legacy RL runs are provably byte-for-byte unchanged. MID-PLAY HALF:
re-confirmed a false premise, not a gap — C# reads `item.Original.Pile`
(`CardCmd.cs:391`), whichever pile currently holds the card, and the sim's
Play-limbo stand-in physically parks a resolving card in `discard_pile` with
`player._playing_card` set (guard N9), so the existing discard branch already
finds and swaps it; no code change was needed or made. NEW TESTS (none of
this shape existed before):
`test/test_take_random_streams.py::test_entropy_draws_transform_and_selection_on_combat_card_selection`
(parity-mode stream spy — both draws land on card_selection, none on the
shared rng; confirmed RED by temporarily reverting the roll to
`hooks.combat._rng.choice(options)`, which fails "drew on the unseeded shared
rng", then restoring it byte-identical),
`::test_entropy_legacy_transform_uses_the_identical_shared_rng_object`
(legacy-mode identity proof) and `::test_transform_finds_a_card_that_is_mid_play`
(mid-play regression pin). NOT closed by this entry, left to guard `/N9`
(open, unchanged): the residual that a transform leaves `player._playing_card`
pointing at the orphaned original rather than the replacement, and N9's own
undemonstrated discard-pile-size exposure during a card's own OnPlay. Suite:
2 failed (933T floor_49 conformance fixture, pre-existing/unrelated) / 3383
passed / 6 xfailed — +3 over the 3380 floor, zero new failures. What follows
is the text as it stood.

- **divergence** `CardCmd.transform_to_random` (`cmds.py:415-450`) rolls its
  replacement on `hooks.combat._rng` (`cmds.py:435`) — the shared legacy
  `random.Random` — where C# takes an explicit `Rng` argument
  (`CardCmd.cs:323, 369`). It also searches only hand/draw/discard/exhaust and
  returns `None` for a card mid-play, because the sim has no Play pile.
- **observable** Every in-combat transform in a conformance replay draws from the
  wrong stream. Dormant for the Play-pile half (Entropy, the only ported
  in-combat transformer, targets the hand).
- **trigger** Any conformance replay containing an in-combat transform; the
  Play-pile half needs a transformer that can target a resolving card.
- **pin** unpinned.
- **fix** Route the roll through the appropriate `combat_rng` stream (mirror what
  `CardCmd.cs` passes at each call site) and teach the pile search about
  `player._playing_card`. Failing test: an Entropy transform consumes a draw from
  the named stream and none from the legacy rng.
- **radius** `creature_card_cmds/G3`, `/step56` (`PileIndexSort`),
  `/N9` (no Play pile).

### `creature_card_cmds/G10` — `ModifyShuffleOrder` modelled as an `AfterShuffle` listener  [DORMANT / parity-live] [unpinned]

**Closed 2026-07-30 (tier-2 campaign, Task 5).** RE-VERIFIED against today's
code, not a rule-3 re-derivation: an earlier round (2026-07-29, "Tier 1"
round 8) had already shipped the three headline fixes this entry's own `fix`
sketch calls for, and they still hold today — `HookSystem.modify_shuffle_order`
is a real dispatcher (`hooks.py:940-989`); both call sites fire it strictly
before `AfterShuffle`/`on_shuffle`; the combat-start call threads
`is_initial_shuffle=True`; `PerfectFitEnchantment` is a real
`modify_shuffle_order` listener (`enchantments.py:278-294`) with the C#
`isInitialShuffle` early return. BUT round 8's own proof of the two-listener
ordering claim — "the card sitting LATER IN THE DISCARD fires last and ends
on top" — did not actually hold: `reshuffle_discard_into_draw` and
`shuffle_draw_and_discard` (`sts2_rl/player.py`) both reassigned
`self.draw_pile`/`self.discard_pile` (moving cards over, emptying discard)
BEFORE shuffling and dispatching, so the hook's per-dispatch
`player.all_cards` position lookup (`hooks.py:972-985`) read the
ALREADY-SHUFFLED draw pile instead of the pre-shuffle discard order C# reads
(`CombatState.IterateHookListeners`, `CombatState.cs:449-467`, walking the
still-untouched real piles while `CardPileCmd.Shuffle`'s detached local
`list` sits unplaced, `CardPileCmd.cs:871-877` vs `878-913`). PROVEN BROKEN
by execution: two Perfect-Fit-enchanted cards (an original and a
`create_clone` copy) in a filler-padded discard, swept over 500 seeds each
direction — roughly half landed the wrong card on top. Round 8's own
regression tests only pinned `random.Random(0)`, whose 2-card Fisher-Yates
happens not to swap the pair, so they passed by coincidence and never caught
it. FIXED: `player.py`'s `_shuffle_draw_pile` renamed to `_shuffle_cards`,
now taking a DETACHED cards list; both reshuffle callers build that list as a
fresh copy (never an alias of `self.discard_pile`/`self.draw_pile`) and defer
reassigning either attribute until AFTER `_shuffle_cards` (and therefore
`modify_shuffle_order`) returns, so the hook's pile-position lookup sees the
pre-shuffle pile membership exactly as C# does. Combat-start (`__init__`) is
unchanged — it correctly passes `self.draw_pile` itself (aliased), matching
`CardPile.RandomizeOrderInternal`'s in-place shuffle-then-dispatch
(`CardPile.cs:69-73`), the one C# site where "pre-shuffle" and "post-shuffle"
pile are the same object. Re-swept 500 seeds each direction post-fix: 0
failures. Two new seed-swept regression tests (never delete-and-replace —
the seed-0-only originals stay):
`test_modify_shuffle_order_reads_pre_shuffle_pile_membership_on_reshuffle` /
`..._on_bottled_potential` (`test/test_tier1_last_five.py`). TDD: RED against
the pre-fix code (`py -m pytest test/test_tier1_last_five.py -k
pre_shuffle_pile_membership -q` → 2 failed, seed=1 clone_first=True the first
counterexample), GREEN after (24 passed in file; full suite 2 failed — the
pre-existing 933T `floor_49` fixture, unrelated — / 3385 passed / 6 xfailed,
+2 over the 3383 floor, zero new failures). Empty-chain (no listener
registered) reshuffle reproduces a raw Fisher-Yates byte-for-byte against an
RNG-state replay (zero extra draws), so legacy/no-enchantment runs are
unaffected. NOT covered by this close: the Play-pile-limbo nuance in the
held-card branch (guard `/N9`'s territory) — a card mid-`OnPlay` is still
found via `self.discard_pile`/`self.draw_pile` membership for hook-ordering
purposes rather than sorting last as an unfound Play-pile card would in C#;
this was already true before this fix and is unchanged by it. Also updated
alongside: `enchantment/EG2` (`audit/records/enchantment/perfect_fit.json`),
whose round-8 "EXECUTED, both directions" claim rested on the same
single-seed coincidence. What follows is the text as it stood.

- **sites** `creature_card_cmds/step93`, `/step102b`, `/G10` (3 entries).
- **divergence** C# mutates the shuffled list **inside** the shuffle, on the
  shuffled-but-not-yet-placed list, strictly before `AfterShuffle`
  (`CardPileCmd.cs:876-877` vs `917`), and the combat-start randomize calls it too
  with `isInitialShuffle: true` (`CardPile.cs:69-74`); the sim has no
  `modify_shuffle_order` hook at all, so `PerfectFitEnchantment` hand-rolls the
  reposition on `on_shuffle` (`enchantments.py:186-189`) and the net order is
  decided by hook-registration order.
- **observable** Draw order after a reshuffle — the most convergence-sensitive
  thing in the engine — is decided by registration order rather than by C#'s fixed
  call sequence. `step102b` adds that `RandomizeOrderInternal` is an **Unstable**
  shuffle (no stabilising sort) plus its own `ModifyShuffleOrder`.
- **trigger** A second `on_shuffle` listener that also repositions, or any
  reshuffle in a replay where Perfect Fit is enchanted.
- **pin** unpinned.
- **fix** Add a real `modify_shuffle_order(pile, cards)` hook called from inside
  the shuffle before placement, and move Perfect Fit onto it. Failing test: with
  Perfect Fit plus one other repositioning listener the post-shuffle order matches
  C#'s call sequence regardless of registration order.
- **radius** `creature_card_cmds/N9` (Play-pile limbo already changes which cards
  a reshuffle sees), `/G9` (draw prevention).

## 2B. Missing guard families

### `damage_pipeline/G5` — no dealer-dead / target-dead entry guard  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign, Task 6).** The dealer-half (`step1`) was
already closed by an earlier, unrecorded pass (re-verified this task, still
faithful). The target-half (`step3`/`G5` itself) is now fixed: `DamageCmd.deal`
(`sts2_rl/cmds.py`) gained `if target.is_dead: return 0` immediately after the
dealer-dead guard, mirroring `CreatureCmd.cs:256-259`'s per-target-loop
`originalTarget.IsDead -> continue` — the first statement of that loop, before
`ModifyDamage` or any other hook. `IsDead == !IsAlive == CurrentHp <= 0`
(`Creature.cs:206-208`), the same predicate the sim's own `is_dead` already is
— not `is_gone`, which would also catch an escaped-but-alive creature C# does
not skip here. Checked against the sim-only `should_allow_hitting` pre-check
(guard `N1`, used by the reviving Decimillipede-segment powers): a withered,
retained segment is `is_dead` for the whole window it is unhittable, so the
new guard reproduces that window too, redundantly rather than in conflict.
Re-checked every call site the record's own enumeration named (34 loop sites
including `monsters/base.py`'s `_execute_attack` and `cards/whirlwind.py`,
plus the fixed-AoE relics); none hits an already-dead target today, so this
closes the structural absence with no observed behaviour change. Pinned by
`test/test_hook_order.py::TestDamagePipelineOrder::test_dead_target_is_skipped_entirely_no_hooks_fire`.
What follows is the text as it stood.

- **sites** `damage_pipeline/step1`, `/step3`, `/G5` (3 entries).
- **divergence** `CreatureCmd.Damage` refuses any hit from an already-dead dealer
  (`CreatureCmd.cs:242-245`) and skips an already-dead target in its per-target
  loop (`256-259`); `DamageCmd.deal` has neither and relies on call-site discipline
  (`monsters/base.py:114-117`, `cards/whirlwind.py:43-49`, both correct on
  spot-check).
- **trigger** A new multi-hit or multi-target effect that forgets the check.
- **pin** unpinned. **fix** two `if ... return` guards at the top of
  `DamageCmd.deal`; failing test drives a hit from a dead dealer and asserts zero
  hooks fire. **radius** `power_cmd/G6` is the same backstop absence on the power
  pipeline; `damage_pipeline/N1` (the sim-only `should_allow_hitting` pre-check) is
  the deliberate-divergence beside it.

### `creature_card_cmds/N3` — the `CardPileAddResult` failure surface is unmodelled  [DORMANT] [unpinned]

**STALE-CLOSED 2026-07-30 (tier-2 campaign, Task 7) — the behaviourally
significant branch was already fixed pre-campaign and missed by this guard's
own last re-verdict; the object itself is a confirmed waiver, not a new
one.** Re-read the whole `Add` path fresh (`CardPileCmd.cs:259-639`): the
batch `IsEnding` refusal (`:312-319`), the per-card `creature.IsDead`
refusal (`:329-340`, "the behaviourally significant one" this guard names)
and the `!IsInProgress` refusal (`:398-401`) are all three already
reproduced by `CardPileCmd._refuses_combat_add` (`sts2_rl/cmds.py`, current
lines 914-932 — the record's `463-512` citation is stale), one boolean
consulted at the top of all three pile-ADD helpers. That guard predates this
campaign (closed at `step71`/`step72`/`step74`, round 4, 2026-07-28); this
guard's own claim that "the dead-owner drop has no ported window ... none
has a sim counterpart" was already false when written. Re-executed the
witness — `test/test_combat_ending_command_guards.py::test_a_generated_card_does_not_enter_a_combat_pile`
and `::test_a_generated_card_is_dropped_when_the_owner_is_dead`, both
green — and found one real, narrow coverage gap: the dead-owner witness only
exercised `add_to_hand`; added
`test_a_generated_card_is_dropped_from_draw_and_discard_when_the_owner_is_dead`
(RED-verified by temporarily disabling the guard, then reverted — zero diff
on `cmds.py`). The RESULT OBJECT stays unbuilt, confirmed rather than merely
deferred: exhaustively grepped every C# call site of `Add`/
`AddGeneratedCardToCombat`/`AddGeneratedCardsToCombat` targeting a combat
pile — no EXTERNAL caller reads `.success`/`.oldPile`/`.modifyingModels`
for gameplay logic outside the Deck path; every external reader feeds the
cosmetic VFX layer (`CardCmd.PreviewCardPileAdd`, `CardCmd.cs:735-760`,
itself a no-op under `TestMode.IsOn`), which the sim has no counterpart
for. Internally `Add`'s own body does gate `Hook.AfterCardChangedPiles` on
`item3.success` (`CardPileCmd.cs:630-637`) — a real gameplay hook, tracked
separately as `creature_card_cmds/G8`; a G8 fix needs no returned struct
because combat-pile success is fully determined by `_refuses_combat_add`.
[Claim narrowed 2026-07-30 after task review.]
`oldPile` and `modifyingModels` are additionally
provably always null on this call path (`AddGeneratedCardsToCombat` throws
if any card already has a pile; `modifyingModels` only populates on the Deck
branch, which a combat-pile add never takes), so a ported object would carry
zero information beyond `success` — matching the sim's own convention
(`DamageResult`, `cmds.py:158-176`) of building a result type only for an
actual consumer. Two call sites DO read `.success` for real logic
(`CardReward.cs:273`, `SpecialCardReward.cs:90`) but both go through the
DECK path (`RunState.add_card`, `run.py:341-354`) — `hook_dispatch/N5`'s
territory (Task 16), untouched here. NOT closed by this pass: `step73`
(`ShouldAddToDeck`, re-grepped, still zero overrides game-wide) stays its
own open gap; `step70` (`AfterCardGeneratedForCombat`) also stays open, for
a different reason than dormancy — re-reading `CardPileCmd.cs:241-247` shows
it fires UNCONDITIONALLY after every per-card `Add`, so it was never
actually part of "the `CardPileAddResult` failure surface" this guard
names, a scope mismatch inherited from an earlier aggregation pass ("FIX
6"); and two branches this guard's own text names stay genuinely
unreachable in the sim's architecture — the `HasBeenRemovedFromState` drop
(no sim flag, Task 14) and the detached-combat-card drop (`IsInCombat` with
a null `CombatState`, inexpressible: the sim sets `card.combat` directly and
unconditionally, with no notion of that inconsistent state). Full suite
re-run clean: no new failures beyond the 2 pre-existing conformance-fixture
ones. What follows is the text as it stood.

- **sites** `creature_card_cmds/step70`, `/step73`, `/N3` (3 entries; `/step72` is
  also a site).
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

### `creature_card_cmds/N4` — no duplicate-instance guard on any pile insert  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign, Task 6), narrowed scope.** The three
pile-ADD helpers (`add_to_discard`, `add_to_draw`, `add_to_hand` including its
overflow-to-discard arm, `sts2_rl/cmds.py`) now assert the target pile does
not already hold this exact `Card` instance before inserting, raising
`ValueError` — mirrors `CardPile.AddInternal`'s `InvalidOperationException`
(`CardPile.cs:86-89`), placed after the existing `IsOverOrEnding`/`IsEnding`
guard (`G14`, already closed). `ExhaustCmd.exhaust` (`/G7`, Task 20) was
deliberately NOT touched, per scope. A full-suite run with the invariant live
produced zero new failures, so it did not surface a `G7` double-membership
collision through any of these three helpers' current callers — `G7`'s bug
flows entirely through `ExhaustCmd.exhaust`'s own inline
`player.exhaust_pile.append(card)`, not through any of the three helpers this
task edited, so `G7` remains open, unexposed, and owned by Task 20.
`RemoveInternal`'s half of the divergence (`CardPile.cs:117-120`) was left
alone: the sim's one un-scoped removal site already only ever removes a card
it just confirmed present. Pinned by 4 new tests in
`test/test_hook_order.py::TestCreatureCardCmdsOrder`
(`test_add_to_discard/draw/hand_refuses_a_duplicate_instance`,
`test_add_to_hand_overflow_refuses_a_duplicate_already_in_discard`). What
follows is the text as it stood.

- **sites** `creature_card_cmds/step102c`, `/N4` (2 entries).
- `CardPile.AddInternal` throws if the pile already holds that `CardModel`
  instance and `RemoveInternal` throws if it does not (`CardPile.cs:86-89,
  117-120`); the sim's piles are plain lists with no invariant — which is what lets
  `/G7`'s double-membership bug exist silently.
- **pin** unpinned. **fix** assert the invariant in the three pile helpers.
  **radius** `/G7` is the verb-level symptom of this container-level hole; fix N4
  first and G7 becomes a loud failure instead of a silent one.

### `creature_card_cmds/N2` — `afflict` skips ShouldAfflict / CanAfflict / AfterApplied  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign, Task 6), narrowed scope (`step64` +
`step65` only — `step63` and `step66` were already settled and untouched).**
Added `HookSystem.should_afflict(card, affliction)` (`sts2_rl/hooks.py`), an
AND-all veto mirroring `Hook.ShouldAfflict` (`Hook.cs:2101-2111`) — added to
`_COMBAT_GATED_HOOKS` as `ShouldAfflict`. Added `Affliction.can_afflict(card)`
(`sts2_rl/afflictions.py`), a real port of `AfflictionModel.CanAfflict`
(`AfflictionModel.cs:190-205`): a card-type gate (`can_afflict_card_type`,
Skill-only override on `TaintedAffliction` per `Tainted.cs:17-19`) and the
already-afflicted/stackability refusal (`is_stackable`, `True` override on
`GalvanizedAffliction`/`TaintedAffliction`). `CardCmd.afflict` (`cmds.py`) now
builds the affliction instance up front and consults `should_afflict` then
`can_afflict`, in C#'s order, before applying. **Live finding**: the sim's
pre-existing "same-type reapplication always stacks" behaviour was wrong for
5 of 7 ported affliction types (everything except Galvanized/Tainted) — C#
refuses a same-type restack unless `IsStackable`. No ported power ever
exercises this (all 7 filter `card.affliction is None` first), so it stays
dormant on game content, matching `step65`'s own "no ported call could be
refused" finding — but a pre-existing sim unit test asserted the old,
incorrect stacking outcome for `RingingAffliction` (non-stackable in C#);
fixed to use `GalvanizedAffliction` instead
(`test/test_overgrowth_powers.py::TestAfflictionExclusivity::test_same_stackable_affliction_reapplied_stacks_amount`,
renamed). `ShouldAfflict` stays a no-op in practice (zero C# implementers
game-wide, re-confirmed). NOT touched: `step63` (already faithful) and
`step66` (`AfterApplied` + the type-mismatch throw, already
deliberate-divergence — and C#'s own base `CanAfflict` already refuses any
call that would reach the throw, since a differing-type existing affliction
fails `CanAfflict` before the throw site is ever reached, reinforcing that
`step66`'s return-`None` substitute was the right call). Pinned by 4 new
tests in `test/test_hook_order.py::TestCreatureCardCmdsOrder`
(`test_should_afflict_veto_refuses_the_application`,
`test_can_afflict_refuses_a_non_stackable_reafflict`,
`test_can_afflict_allows_a_stackable_reafflict`,
`test_can_afflict_refuses_the_wrong_card_type`). What follows is the text as
it stood.

- **sites** `creature_card_cmds/step64`, `/step65`, `/N2` (3 entries).
- `CardCmd.Afflict` guards on `Hook.ShouldAfflict` and `affliction.CanAfflict(card)`
  and fires an `AfterApplied` lifecycle event (`CardCmd.cs:627-634` ff.); the sim
  has no surface for any of the three and returns `None` where C# throws.
  `ShouldAfflict` has zero overrides game-wide; `CanAfflict` has no sim surface at
  all. Trigger: porting any affliction with a `CanAfflict` restriction.
- **radius** `hook_dispatch/G6` (afflictions are not listeners at all), `/G8`.

### `creature_card_cmds/N5` + `/step31` — `EnergyCmd.gain` lacks the `finalAmount > 0` guard  [DORMANT] [unpinned]

**STALE-CLOSED 2026-07-30 (tier-2 campaign, Task 6) — found already closed by
an incidental fix, missed by every prior re-verification pass.**
`hooks.modify_energy_gain` (`sts2_rl/hooks.py`) already returns `max(0,
amount)`, present since the sim's initial commit — predating every audit
round that re-verified this gap as unchanged, because those passes read
`EnergyCmd.gain` (`cmds.py`) in isolation ("`player.energy += amount`
unconditionally", true of that one line) without checking what the upstream
hook call could actually return. Because the value it receives can never be
negative, `player.energy += amount` can no longer subtract: at `amount==0`
it's a no-op, at `amount>0` it behaves like C#. `Hook.ModifyEnergyGain`
(`Hook.cs:1606-1621`) does not itself clamp — the sim's clamp is an
architectural difference, not a literal port of `PlayerCmd.cs:37`'s `if
(finalAmount > 0m)` — but it produces an identical `player.Energy` result for
every listener chain, since `PlayerCombatState.GainEnergy`'s own effect is
`Energy = Clamp(Energy + amount, 0, 999999999)` (adding 0 is indistinguishable
from not adding), and `GainEnergy` THROWS `ArgumentException` on a negative
argument in C# (`PlayerCombatState.cs:181-188`) — presumably why the
`finalAmount>0` guard exists downstream at all; the sim's upstream clamp
prevents that argument from ever forming, closing the same hole a different
way. Re-executed the record's own theory with a listener returning `-100` (a
merely-zeroing listener can't discriminate the two designs): `player.energy`
is unchanged on today's code, unmodified — no behavioural change made to
`cmds.py`. Pinned (both pass already, proving the stale claim rather than
driving a new guard) by
`test/test_hook_order.py::TestCreatureCardCmdsOrder::test_energy_gain_does_not_apply_a_non_positive_modified_amount`
and `::test_energy_gain_still_applies_a_positive_modified_amount`. NOT closed
by this pass: the sibling `AfterModifyingEnergyGain` companion event (the
`damage_pipeline/G2` `AfterModifying*` family) remains unported — out of
`N5`'s scope. What follows is the text as it stood.

`PlayerCmd.cs:37-41` adds energy only when the modified amount is positive;
`cmds.py:553-554` does `player.energy += amount` unconditionally, so a modifier
returning a negative value would subtract energy. The only ported
`modify_energy_gain` listener returns 0 (`NoEnergyGainPower`,
`powers.py:554-557`), a no-op under both rules. One `if final > 0` guard.

## 2C. Missing hook surfaces

### `creature_card_cmds/G8` — no `AfterCardChangedPiles` at all  [DORMANT] [unpinned]
**Narrowed further 2026-07-31 (tier-2 campaign, Task 20) — NOT closed.**
`RemoveFromCombat` (`step69`) is now wired: `thieving_hopper.py`'s `_thievery`
dispatches `after_card_changed_piles` with the leaving pile
(`CardPileCmd.cs:188`, `cardPile2.Type` / null `clonedBy`). That was the fourth
of the four enumerated C# dispatch sites, so **exactly one remains unwired**:
the manual play (`CardPileCmd.cs:683`), where `combat.py`'s
`_resolve_card_play` collapses the Play-pile leg and a faithful dispatch needs
the Play-pile modelling first (`creature_card_cmds/N9`). Dormancy unchanged —
all four ported listeners filter to Deck; SovereignBlade/Hoarder/SoulFysh
remain unported. What follows is the text as it stood.

**Wiring mostly closed 2026-07-30 (tier-2 campaign, Task 8):** 3 of the 4
originally-enumerated sites (Add/step81, Draw/step89, the two reshuffle
helpers/step96) are now dispatched; RemoveFromCombat (step69, the
thieving_hopper site — routed to the escape-verbs task) and the manual play
(needs the Play-pile modelling first, `creature_card_cmds/N9`) remain
unwired. STILL DORMANT: no ported listener watches a combat pile. Draw-path
dispatch cost was initially ~23-35% relative overhead on the hottest sim
loop; fixed in the same task via a new HookSystem-wide per-hook
listener-presence cache (`HookSystem._has_listener_for`, hooks.py) —
re-measured 50-63% FASTER than the pre-Task-8 baseline (the cache also
removed a pre-existing cost on `on_card_drawn`'s dispatch at the same call
site). What follows is the text as it stood.

- **sites** `creature_card_cmds/step69`, `/step81`, `/step89`, `/step96`, `/G8`
  (5 entries; `/step59` is also a site).
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

### `creature_card_cmds/G12` + `/step34` — no gold-gain hook surface  [DORMANT] [unpinned]

**Closed pre-campaign; verified 2026-07-30 (tier-2 campaign, Task 9).** The
fix (`run.py` gain_gold's ModifyGoldGained → AfterGoldGained order,
`relics/base.py`'s run-level surface, Dragon Fruit un-stubbed) was already
implemented and staged, with the records already `faithful` — this queue
entry had simply never been annotated. Task 9 re-verified line-by-line
against `PlayerCmd.cs:141-170` and `DragonFruit.cs:22-29` (including the
bail-tests-pre-truncation amount and dispatch-after-balance-moves ordering)
and added 8 pinning tests (`test/test_gold_gain_hooks.py`). What follows is
the text as it stood.

`PlayerCmd.GainGold` fires `ModifyGoldGained` -> `AfterModifyingGoldGained` ->
`AfterGoldGained` (`PlayerCmd.cs:144-169`); `RunState.gain_gold`
(`run.py:325-333`) runs a relic `modify_gold_gained` loop and nothing else. The
consequence is visible **today**: `DragonFruit.cs:22-29` grants +1 Max HP on every
gold gain and is a ported relic whose sim implementation is an inert stub
(`relics/dragon_fruit.py`, docstring still claiming "no gold system" although
`run.gold` exists). Fix: add `after_gold_gained(amount)` to the run-side surface
and un-stub Dragon Fruit. **radius** `damage_pipeline/G2` (the
`AfterModifyingGoldGained` variant), `hook_dispatch/N5` (no run-level listener
list to hang it on).

### `creature_card_cmds/G11` + `/step49` — `AfterCardDiscarded` fires pre-move and in a batch  [DORMANT] [unpinned]
**Closed 2026-07-30 (tier-2 campaign, Task 10) — premise reversed.** The
record cited the wrong C# method: `FlushPlayerHand` (CombatManager.cs:
1313-1347) never fires `AfterCardDiscarded` — the hook's sole C# call site
is `CardCmd.cs:194` inside `DiscardAndDraw`. The sim's flush dispatch was
REMOVED, not reordered (zero ported listeners either way). Same false
premise survives at combat.py's turn-end-in-hand discard — filed in "Named
work". What follows is the text as it stood.


C# adds each card to the discard pile **first**, then fires the hook, one card at
a time (`CardCmd.cs:186-195`); `discard_hand` (`player.py:192-196`) fires
`on_card_discarded` for every flushed card while they are all still in `hand`,
then moves them as a batch. Executed: flushing `[Strike, Defend]` records
`[('strike', in_hand=True, in_discard=False), ('defend', in_hand=True,
in_discard=False)]` at hook time; C# would give `(False, True)` for each and would
have moved Strike before Defend's hook ran. Trigger: any `on_card_discarded`
listener that reads pile membership. Fix: interleave move-then-fire.

### `creature_card_cmds/G9` + `/step84` — `ShouldDraw` re-evaluated per card, no `AfterPreventingDraw`  [DORMANT] [unpinned]
**Closed 2026-07-30 (tier-2 campaign, Task 10).** `should_draw` hoisted to
one pre-loop evaluation and `after_preventing_draw` added (targeted at the
vetoing listener, per Hook.cs:1056-1063); the mid-draw-flip divergence is
pinned (5 cards/1 call vs the old 1 card/2 calls). C# has exactly 2
ShouldDraw overrides and 1 AfterPreventingDraw override (Fiddle, cosmetic).
What follows is the text as it stood.


`CardPileCmd.Draw` evaluates `Hook.ShouldDraw` exactly once before the loop and
fires `Hook.AfterPreventingDraw` on refusal (`CardPileCmd.cs:804-808`);
`player.py:280-281` calls `should_draw` inside the per-card loop and has no
`after_preventing_draw`. Trigger: a `should_draw` listener that flips mid-draw —
Fiddle (`relics/fiddle.py:26-29`) is the only ported one and is stateless. Fix:
hoist the check; add the hook.

### `creature_card_cmds/step12` — no `BeforeBlockGained`  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 11).** `before_block_gained` dispatched
unconditionally with the raw pre-modifier amount from BlockCmd.apply
(CreatureCmd.cs:642). What follows is the text as it stood.


C#'s unconditional pre-modifier event carrying the raw amount
(`CreatureCmd.cs:642`, `Hook.cs:131-137`) has no sim surface. Zero overrides
game-wide today; live the moment any model implements it. One dispatcher to add.

### `creature_card_cmds/step46` — no `BeforeCardAutoPlayed`  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 11).** `before_card_auto_played` fires in
the auto-play path where CardCmd.cs:122 does; the AutoPlayType param is omitted
(its only C# reader is a Steam achievement). What follows is the text as it stood.


`combat.py:552` fires `on_energy_spent(card, 0)` and then the ordinary
`before_card_played`; the auto-play-only event is absent and none of its C#
implementations is ported. **radius** `hook_dispatch/G4` (the per-play bracket).

### `creature_card_cmds/step61` — no `AfterCardGeneratedForCombat` on transform  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign, Task 8).** `transform_to_random` now
dispatches `on_card_generated_for_combat` after `after_transformed_to`,
mirroring `CardCmd.cs:499-506` (success-gated, creator = the transforming
player); the Add-shaped sites dispatch it too (with step70's residual gate
nuance left open). `monster/aeonglass` is the one ported implementer, now on
the real hook. What follows is the text as it stood.

`cmds.py:445-450` fires only `on_card_entered_combat`; C# fires **both** events for
a combat-pile transform (`CardCmd.cs:445` and `504`). None of the seven C#
implementations is ported.

### `turn_structure/step20` — no `AfterModifyingHandDraw`  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 11).** Dispatcher added with C#'s exact
shape (walk the full listener order, call each member of the modifiers set at most
once — Hook.cs:739-749); the naive modifiers-list loop double-fired a both-phases
listener and was fixed in review. What follows is the text as it stood.


`modify_hand_draw` is ported with the same base of 5 (`player.py:171`), but the
companion event is absent. C# has four implementers; the two ported ones are
presentation-only (`Pocketwatch.cs:67-71` is a bare `Flash()`). This is one of
`damage_pipeline/G2`'s 13 variants.

### `turn_structure/step55` — no `BeforeFlush`  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 11).** `before_flush` occupies C#'s slot
(CombatManager.cs:1177-1208); its three C# implementers stay unported, so still
dormant. What follows is the text as it stood.


No slot between `_process_turn_end_cards` (`combat.py:658`) and the flush
(`661-662`). C#'s three implementers (`SlumberingEssence.cs`,
`WellLaidPlansPower.cs`, a mock) are unported. **radius** `enchantment/EG2`.

### `turn_structure/G11` + `/step37` — no enemy-side `BeforeTurnEnd` slot  [DORMANT] [unpinned]

**Mostly closed 2026-07-28 (round 4).** `before_enemy_side_end` is that slot (`CombatManager.cs:1251`), with the full suffix walk, and both ported enemy-side listeners are on it at their real phases. What follows is the text as it stood.

C# fires the same three-pass `BeforeTurnEnd` dispatcher for the enemy side
(`CombatManager.cs:1251`); the sim has only per-enemy `on_enemy_turn_end`
(`combat.py:341`) and side-scoped `on_enemy_side_end` (`345`), with no slot
between them. Eight C# powers implement a `BeforeSideTurnEnd*` phase
(`AsleepPower`, `PlatingPower`, `ChainsOfBindingPower`, `DoomPower`,
`HailstormPower`, `SandpitPower`, `TheBombPower` + a mock); none is ported onto
that slot. **radius** `turn_structure/G12`, `hook_dispatch/G3`.

### `turn_structure/G16` — `on_hand_emptied` fires from the one site C# excludes  [DORMANT] [unpinned]

**Mostly closed 2026-07-29 (round 5).** Both of C#'s call sites, neither of the sim's old ones, and the full `!IsExecutingCardOrPotionEffect` gate. Unceasing Top and Joss Paper both moved onto their real hooks. What follows is the text as it stood.

- **sites** `turn_structure/step63`, `/step73`, `/G16` (3 entries).
- C#'s `CheckForEmptyHand` (`CombatManager.cs:887-893`) is called **only** after a
  card play and after a potion use, gated on `IsExecutingCardOrPotionEffect` and
  the player's phase; `UnceasingTop.cs:25-35` carries a source remark explaining
  why the draw and the flush must not trigger it. The sim's `on_hand_emptied` has
  exactly one call site — `player.py:197`, at the bottom of `discard_hand`, i.e.
  the flush — and none after a play or potion.
- **trigger** Porting Unceasing Top, or any listener that draws on an empty hand.
- **radius** `turn_structure/G16` and `/G4` (Joss Paper leans on the flush firing it).

### `turn_structure/step8` — no per-power `AmountOnTurnStart` snapshot  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 13).** `snapshot_powers_on_turn_start`
runs first on both sides, and both ported readers use it — including
HelloWorldPower, which reads the snapshot as its generated-card COUNT, not
just as an eligibility gate. What follows is the text as it stood.


`grep -rn amount_on_turn_start sts2_rl/` returns 0 hits. C# snapshots every power's
amount before anything else in the turn (`CombatManager.cs:449-455`,
`Creature.cs:673-679`) and three powers read it, two ported:
`DrawCardsNextTurnPower` (`AmountOnTurnStart == 0` suppresses both the extra draw
and the removal, `DrawCardsNextTurnPower.cs:28,37`) and `HelloWorldPower`. The
sim's `DrawCardsNextTurnPower` (`powers.py:2737-2754`) has no such guard, so a
stack applied during the turn-start window would draw and expire in the same turn.

### `turn_structure/step17` — the two energy hooks fire in the opposite order  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 11).** `should_reset_energy` now precedes
`modify_max_energy`, which is read inside the chosen branch
(CombatManager.cs:641-649). What follows is the text as it stood.


The arithmetic matches (`player.py:163-167`) but the sim calls `modify_max_energy`
first and `should_reset_energy` second, where C# evaluates
`ShouldPlayerResetEnergy` first and reads `MaxEnergy` inside the chosen branch
(`CombatManager.cs`). Unobservable while both dispatchers are pure aggregations;
live with the first side-effecting implementation of either.

### `hook_dispatch/step37` — the predicate family short-circuits in the sim  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 11) — THIS ENTRY'S PREMISE WAS FALSE.**
C#'s `flag = flag || item.ShouldX(...)` DOES short-circuit: the foreach keeps
iterating, but once `flag` is true the listener call is not evaluated — exactly what
the sim's `any(...)` already did. Verified three ways: the language spec, a compiled
and executed reproduction (only the first listener ran), and Hook.cs:1451-1452, where
the developers hoisted a listener call onto its own line precisely to AVOID this skip.
A first pass "fixed" the sim and was reverted byte-identically. NO code changed; the
pin asserts the second listener is never called. **A record can be wrong about the C#
itself, not merely stale.** What follows is the text as it stood.


C# uses `flag = flag || item.ShouldX(...)` with **no** short-circuit, calling every
listener (`Hook.cs:2472-2480` `ShouldForcePotionReward`, `2485-2493`
`ShouldAllowFreeTravel` — those are the only two); the sim aggregates with a
short-circuiting `any(...)` (`rewards.py:449`). Each hook has exactly one
implementer today (`WhiteBeastStatue.cs`, `WingedBoots.cs`), both side-effect free.
Trigger: a second ported implementer with a side effect.

## 2D. Listener-registry shape

### `hook_dispatch/G7` — no per-item liveness re-check  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step4`, `/step11`, `/step12`, `/step16`, `/step45` (5 entries).
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

### `hook_dispatch/G1` — card listener order frozen at combat start  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step9`, `/step44` (2 entries).
- `CombatState.cs:449-467` walks `AllPiles` = Hand, Draw, Discard, Exhaust, Play
  (`PlayerCombatState.cs:70-80`) on **every** dispatch, so a card that moves pile
  moves position in the listener list; `combat.py:124` registers `player.all_cards`
  once, in a fixed order (`player.py:100-103`), and never reorders. Dormancy
  executed: card classes implement only six hooks (`dormancy_probes.py card-hooks`,
  203 classes x 66 hook names) and none can observe cross-card order.
- **radius** `hook_dispatch/G1` (same list), `/G6`.

### `hook_dispatch/G5` + `/step3` — `MonsterModel` is not a sim listener  [DORMANT] [unpinned]

`CombatState.cs:420` adds `creature.Monster` to the listener list and
`MonsterModel.cs:51` declares `ShouldReceiveCombatHooks => true`. Exactly **12** C#
monster models override an `AbstractModel` hook
(`py audit/tools/dormancy_probes.py cs-monster-hooks`); only `KinPriest` has been
adjudicated (waiver: presentation). **The other 11 are in no seam's scope — see
the holes section.** Trigger: porting any of them onto their real hook.

### `hook_dispatch/G6` — `AfflictionModel` is not a sim listener  [DORMANT] [unpinned]

`CombatState.cs:458-461` adds `cardModel.Affliction` immediately after its card and
`AfflictionModel.cs:146` declares `ShouldReceiveCombatHooks => true`. Executed both
ways: 0 of the 7 sim `Affliction` subclasses define any hook, and exactly one of
the 10 C# affliction files overrides one (`Hexed.cs`, `AfterCardEnteredCombat`) —
and Hexed is a data-only stub (`afflictions.py:72-79`). Trigger: porting Hexed's
hook; it then needs `hook_dispatch/G1`'s per-card ordering to register in the right
position.

### `hook_dispatch/N5` — no run-level listener list  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step14`, `/step18`, `/N5` (3 entries).
- `RunState.cs:545-596` makes every deck card and its enchantment a run listener at
  all times, in and out of combat, and appends the whole combat list when there is
  a child combat; the sim has two disjoint systems — `HookSystem` inside a combat,
  duck-typing over `run.relics` (`relics/base.py:205-235`) outside one — and a deck
  card is never a listener. Executed: no sim card class implements a run-scoped
  hook at all.
- **trigger** Porting any `CardModel` overriding `AfterRoomEntered`,
  `AfterRewardTaken`, `ShouldAddToDeck` or another run-level hook.
- **radius** `creature_card_cmds/G12` (nowhere to hang `AfterGoldGained`).

## 2E. Power pipeline

### `power_cmd/G1` — Artifact's typing is static, not sign-aware  [DORMANT] [pinned]
**Closed 2026-07-31 (tier-2 campaign, Task 17) — was already fixed.** The guard's own
record has read `faithful` since 2026-07-28; only the sibling `step13` prose stayed
stale. Re-verified: `Power.type_for_amount` matches `PowerModel.cs:460-471`, the
Artifact branch consults it (`ArtifactPower.cs:24`), the adjacent skip-next-tick site
correctly keeps C#'s STATIC check (`PowerCmd.cs:144`), and the named pin passes
un-xfailed. No code change. What follows is the text as it stood.

- **sites** `power_cmd/step13`, `/step28`, `/G1` (3 entries).
- `cmds.py:299` checks `power_cls.power_type == PowerType.DEBUFF` (a fixed class
  attribute) instead of C#'s `canonicalPower.GetTypeForAmount(amount) !=
  PowerType.Debuff` (`ArtifactPower.cs:24`; `PowerModel.cs:460-471` — a
  Counter+AllowNegative power with a negative amount **is** a Debuff).
  Strength/Dexterity are Counter+AllowNegative+Buff on both sides, so a
  negative-amount application bypasses the sim's Artifact branch entirely.
- **trigger** Dormant in both directions: no player-side `ArtifactPower` source
  exists anywhere in the game, and the enemy side needs a ported negative-Strength
  applier (`Malaise`, `Resonance` — neither ported).
- **pin** `TestPowerCmdOrder::test_artifact_blocks_negative_signed_debuff`.
- **fix** Add `get_type_for_amount(amount)` to the power model and use it at
  `cmds.py:299` and in Unsettling Lamp. **radius** `/G2`, `/G3`.

### `power_cmd/G2` + `power_cmd/step10` — Unsettling Lamp's condition has the same blind spot  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 17) — and the sim's docstring had the C#
BACKWARDS.** It claimed the sim lacked an `amount <= 0` bail that C# has;
`UnsettlingLamp.cs` has no such guard anywhere — both its latch (:71-104) and its
doubling (:106-129) gate purely on `GetTypeForAmount(amount) != Debuff`. The sim's own
bail WAS the divergence, rejecting exactly the negative-Strength shape C# doubles; it is
deleted and the condition is now sign-aware. Duration ticks are structurally unreachable
from the Lamp (every tick goes through `PowerCmd.modify_amount`, which never calls
`modify_power_amount`), so the 933T Mecha Knight behaviour is unchanged. **Still blocking
`power_cmd/G4` and `damage_pipeline/G2`'s ten variants: dispatch architecture** —
`modify_power_amount` returns a bare int with no modifiers out-list, and Artifact is
hard-coded outside the listener system (`power_cmd/G3`). What follows is the text as it
stood.

`relics/unsettling_lamp.py:44-53` bails on `amount <= 0` and then checks the static
`power_type`, where C# uses `power.GetTypeForAmount(amount)`
(`UnsettlingLamp.cs:124`). `Malaise.cs:40` and `Resonance.cs:33` both apply
negative `StrengthPower` with `applier = player, cardSource = this` — exactly the
shape Lamp doubles — and the sim's `amount <= 0` guard rejects it before the
sign-aware check would matter. **This is the seam the 933T Mecha Knight bug lived
on**: the ordering half is fixed, the sign half is not.

### `power_cmd/G3` — the three power-amount phases collapsed into one chain  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 18), both entries — and the census
reason on record was STALE.** The flat registration-order chain is gone:
given-additive then given-multiplicative (`Hook.cs:1888-1912`'s exact
sum-then-product, which a naive fold gets wrong) under a real
`applier != null && ContainsCreature(applier)` gate, then the received chain
unconditionally. Artifact and Ruined Helmet are now real listeners instead of a
hard-coded block outside the hook loop. **The dormancy argument needed
replacing:** it held that Lamp and Ruined Helmet are disjoint because Lamp gates
on the STATIC `power_type` — which Task 17 replaced with sign-aware
`type_for_amount`. The conclusion survived for a deeper reason nobody had
recorded: Lamp is a GIVEN-side override (`UnsettlingLamp.cs:106-129`) and
RuinedHelmet/Artifact are RECEIVED-side (`RuinedHelmet.cs:32-53`,
`ArtifactPower.cs:17-36`). They were never on the same C# hook at all, and the
sim's collapsed chain was the only thing that ever put them in a race — which
is the bug this guard named, now structurally impossible. What follows is the
text as it stood.

- **sites** `power_cmd/step12`, `power_cmd/step27`, `/G3` (3 entries).
- C# runs `BeforePowerAmountChanged` -> `ModifyPowerAmountGiven` (guarded on
  `applier != null && ContainsCreature(applier)`) -> `ModifyPowerAmountReceived`,
  three separately-sequenced calls (`PowerCmd.cs:120,125,127`); `hooks.py:170-183`
  is one flat registration-order chain with no phase separation and no applier
  gate, and `ArtifactPower` is not a listener at all (hard-coded at
  `cmds.py:299-306`).
- **trigger** The two general listeners are domain-disjoint today (Unsettling Lamp
  given-side debuff-only, Ruined Helmet received-side buff-only). A third listener,
  or either widening, collides.
- **radius** `hook_dispatch/G3` (phases), `hook_dispatch/G4`
  (`damage_pipeline/G2`, the companion events), `/G1`.

### `power_cmd/G5` + `/step3` — no `PowerInstanceType`  [DORMANT] [unpinned]

**Mostly closed 2026-07-30 (tier-2 campaign).** `PowerCmd.apply`'s stacking
branch now dispatches on `Power.instance_type` (`sts2_rl/powers.py`, mirroring
`PowerModel.InstanceType`) the way `FindExistingInstanceForStacking` does:
`NONE` still finds by id, `INSTANCED` never finds an existing instance (a
second application starts its own, independently hook-registered one),
`INSTANCED_PER_APPLIER` finds one only when the applier matches. 9 of the 11
ported units got the real attribute and are closed: `automation`,
`heist`, `panache`, `rolling_boulder`, `sandpit` (with a companion fix to
`FranticEscapeCard`, whose own re-application bypasses `Apply` in C# too),
`strangle`, `thievery`, `toric_toughness`, `withering_presence`. **Still open:**
`power/the_bomb/InstanceType` and `power/swipe/InstanceType` — both already
reproduce the observable behaviour via their own pre-existing hand-rolled
workarounds, and migrating either to the generic dispatch would silently
regress it (confirmed for `swipe` against `RunState.finish_combat`'s
escaped-hopper deck-reconciliation walk). What follows is the text as it
stood.

`PowerCmd.cs:165-174`'s `FindExistingInstanceForStacking` dispatches on
`power.InstanceType` (`PowerModel.cs:144`, default `None`); the sim's
`if power_cls.id in target.powers` (`cmds.py:308`) always behaves as `None`. **21**
C# powers declare an override (19 `Instanced`, 2 `InstancedPerApplier` —
`OblivionPower.cs:27`, `StranglePower.cs:29`), **11 of them ported**. Trigger: two
appliers of the same `InstancedPerApplier` power in one combat, or any ported
`Instanced` power stacking where it should not.

### `power_cmd/step4` and `power_cmd/step26` — one code path serves Apply and ModifyAmount  [DORMANT] [unpinned]

C# has two independently-coded pipelines whose guards differ (`PowerCmd.cs:79-87`);
the sim collapses them (`cmds.py:270-332`). It reaches the same steady state for
ported content, but the collapse is not verified line-for-line — and `hook_dispatch/G4` is
the one place it has already been proven wrong. **Read this entry before touching
`PowerCmd.apply`.**

### `power_cmd/step6` — no `amount == 0` early return  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 18).** `PowerCmd.apply` now bails on a
raw `amount == 0` before any hook runs (`PowerCmd.cs:103-106`), gated on
`existing is None` so it does not refuse a legitimate zero-offset re-stack —
C#'s own `ModifyAmount` does not refuse one either. What follows is the text as
it stood.

Filed under the `IsEnding` family by its first reference, but it owns the
zero-amount half itself. Executed: `PowerCmd.apply(cs.hooks, cs.enemy,
StrengthPower, 0)` -> `{'strength': Strength(0)}`, same for Vulnerable, where C#
(`PowerCmd.cs:103`) registers nothing; a 0-amount debuff on the **player**
additionally lands with `skip_next_tick = True`. One guard at the top of
`PowerCmd.apply`.

## 2F. Damage pipeline remainder

### `damage_pipeline/G4` + `/step17.5` — the killing-blow skip is recomputed after death prevention  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign).** `DamageCmd.deal` (`sts2_rl/cmds.py`)
now snapshots `was_lethal = target.is_dead` immediately after the HP write and
BEFORE `_resolve_death` runs (which includes any `should_die`/`should_die_late`
prevention AND the preventer's own synchronous heal, e.g.
`LizardTail.after_preventing_death`), and gates `on_damage_received` on that
snapshot instead of a live `target.is_dead` re-read taken afterward — matching
`CreatureCmd.cs:392`'s `!WasTargetKilled || !IsDead` reading
`LoseHpInternal`'s snapshot (`Creature.cs:445-457`) strictly before `Kill()`
(`CreatureCmd.cs:409`). Pinned by
`test/test_hook_order.py::TestDamagePipelineOrder::test_killing_blow_skip_is_a_pre_death_prevention_snapshot`
(Lizard Tail + Centennial Puzzle: the Tail still prevents the death and heals
to 50% max HP, and Centennial Puzzle's `on_damage_received` is now correctly
skipped instead of drawing 3) and
`::test_non_lethal_hit_still_fires_on_damage_received_with_lizard_tail` (the
non-lethal path is unaffected). NOT covered by this fix:
`damage_pipeline/N2`'s single-target-per-call architecture (C# defers `Kill()`
for a whole multi-target batch; the sim resolves one target's death before the
next target's `DamageCmd.deal` call begins) remains a recorded deliberate
divergence. What follows is the text as it stood.

C# decides whether to fire `AfterDamageReceived` (`CreatureCmd.cs:392-399`) from a
snapshot taken **before** `Kill()`, so an arithmetically-lethal hit permanently
skips it even if a `ShouldDieLate` listener prevents the death — `LizardTail.cs:49-55`
restores HP through its own `AfterPreventingDeath` hook instead; the sim resets HP
to 1 first and only then tests `target.is_dead` (`cmds.py:84-120`), so a prevented
death does **not** skip `on_damage_received`. **Witness to use as the failing
test**: Lizard Tail + Centennial Puzzle, both ported — C#'s
`CentennialPuzzle.AfterDamageReceived` is itself killing-blow guarded and correctly
does not draw; the sim's (`relics/centennial_puzzle.py:24-35`) fires and draws 3
cards.

### `damage_pipeline/G6` and `damage_pipeline/step17.4` — the dealer-side event fires after the victim-side one  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign).** The two lines in `DamageCmd.deal`
(`sts2_rl/cmds.py` step 9) are swapped: `on_damage_dealt` (dealer side) now
fires before `on_damage_received` (victim side), matching
`CreatureCmd.cs:388-395`'s `AfterDamageGiven`-before-guarded-
`AfterDamageReceived` order. Only the order changed — the pre-existing
`dealer is not None and hp_lost > 0` dispatch condition on `on_damage_dealt`
is untouched (a separate mechanism, `power/_after_damage_given_substitution` /
queue Task 26). Pinned with test-local listeners (no sim power implements
`on_damage_dealt` yet, so this stays content-dormant exactly as before) by
`test/test_hook_order.py::TestDamagePipelineOrder::test_dealer_side_event_fires_before_victim_side_event`
and `::test_killing_blow_records_dealer_side_event_only`. What follows is the
text as it stood.

(Two mechanism ids, one finding: the guard and the step that records it each
stand alone because the step names no guard.)

`CreatureCmd.cs:388-395` fires `AfterDamageGiven` (unconditional) **before** the
killing-blow-guarded `AfterDamageReceived`; `DamageCmd.deal` fires
`on_damage_received` then `on_damage_dealt` — the reverse. No sim power implements
`on_damage_dealt` yet. Two lines to swap.

## 2G. Creature and card verbs with no sim counterpart

### `creature_card_cmds/G5` + `/step22` — heal reports the clamped amount, and nothing at full HP  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 19).** `CreatureCmd.heal` now fires
`AfterCurrentHpChanged` on the RAW requested amount whenever that amount is
positive — including at full HP, where the clamped delta is 0 and the sim
previously fired nothing — matching `CreatureCmd.cs:751-754` exactly. Both
recorded witnesses re-executed and now report C#'s numbers. Pinned in
`test/test_hp_block_verbs.py`. What follows is the text as it stood.

`CreatureCmd.cs:751-754` fires `AfterCurrentHpChanged` when the **requested** amount
> 0, carrying that raw amount; `cmds.py:162-166` fires with the **clamped** amount
and only when positive. Executed: healing 20 on a player 3 below max reports delta 3
(C#: 20); healing at full HP reports nothing (C#: reports +amount). The only ported
`on_hp_changed` listener is Red Skull (`relics/red_skull.py:44-46`), which ignores
the delta.

### `creature_card_cmds/G6` — `lose_max_hp` cannot kill  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 19), all three entries.** `lose_max_hp`
now computes the unfloored `newMaxHp`, deals the `CurrentHp` overshoot as
Unblockable|Unpowered damage through the **full** `DamageCmd.deal` pipeline, and
floors MaxHp at 1 only afterwards (`CreatureCmd.cs:823-827`) — so the order
`/step29` records is now exact, and the pipeline observes the OLD unfloored MaxHp.
The recorded witness reverses: a 10/10 player losing 30 max HP now dies. Brightest
Flame and `PaperCutsPower` re-verified unchanged. What follows is the text as it
stood.

- **sites** `creature_card_cmds/step28`, `/G6`; `creature_card_cmds/step29` is
  the same finding recorded on its own step (the record files it separately
  because the *order* is the load-bearing part).

`CreatureCmd.LoseMaxHp` computes an **unfloored** `newMaxHp` and, when it is below
`CurrentHp`, deals the difference as Unblockable|Unpowered damage through the
**full** damage pipeline — hooks, death check, `Kill` — and only afterwards floors
MaxHp at 1 (`CreatureCmd.cs:823-827`). The sim floors first (`cmds.py:179-189`), so
no `modify_hp_lost` / `on_damage_received` / `should_die` / `on_death` fires and no
creature can die of max-HP loss. Executed: a 10/10 player losing 30 max HP ends
**alive at 1/1**; C# deals `10 - (-20) = 30` unblockable damage and kills. The order
is load-bearing (`/step29`). Ported in-combat callers: Brightest Flame
(`cards/brightest_flame.py:37`), `PaperCutsPower`.

### `creature_card_cmds/G7` — `exhaust` only knows the hand and the discard pile  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 20) — and the fix needed a SECOND
pass.** `ExhaustCmd.exhaust` now scans every combat pile (hand, draw, discard
**and exhaust**) for the card's current pile and removes it before appending,
mirroring `RemoveFromCurrentPile`'s pile-agnostic removal
(`CardPileCmd.cs:496`). Both recorded witnesses reverse. **The re-exhaust case
is worth reading before touching this again:** the first fix asserted the card
was absent from the exhaust pile and raised `ValueError`, reasoning from
`CardPile.AddInternal`'s throw (`CardPile.cs:86-89`). The task reviewer proved
that wrong from the C# — `CardPileCmd.Add` captures `oldPile`
(`CardPileCmd.cs:364`) and removes at `:494-496` BEFORE adding at `:510`, so
with `oldPile == targetPile == Exhaust` the contains-guard tests an
already-emptied slot and never fires. Re-exhausting is a legal **no-throw
reposition to the bottom**; raising would have been a new divergence
introduced by the fix. (The brief had suggested the raising behaviour; the C#
overruled it.) What follows is the text as it stood.

`cmds.py:379-384` removes the card from `hand` or `discard_pile` and appends it to
`exhaust_pile`; a card in the draw pile, the exhaust pile, or mid-play stays put
**and** lands in the exhaust pile — it exists in two piles at once. Executed: a
Strike alone in the draw pile ends with `card in draw_pile` **and** `card in
exhaust_pile`; a Strike exhausted twice ends with the same instance in the exhaust
pile twice. C# routes through `CardPileCmd.Add(card, Exhaust, Bottom)` whose
`RemoveFromCurrentPile()` is pile-agnostic (`CardPileCmd.cs:496`). **radius** `/N4`
is the missing invariant that hides it.

### `creature_card_cmds/G13` + `/step8` — escape leaves the escaper's powers registered  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 20), both entries.** `CreatureCmd.escape`
now strips every power via `Power._expire()` (unregister + detach, no
`on_removed`) before setting `escaped = True` — `RemoveAllPowersInternalExcept`
(`Creature.cs:658-666`) including its SILENCE, the deliberate contrast with
death, whose `_strip_powers_after_death` still fires `on_removed` and is
unchanged. The sim-invented `on_creature_escaped` was KEPT on evidence: the
reviewer read `CreatureCmd.Escape` → `RemoveAllPowersInternalExcept` →
`CombatManager.RemoveCreature` (`CombatManager.cs:1035-1044`) →
`CombatState.CreatureEscaped` (`CombatState.cs:266-270`) end to end and found
zero `Hook.AfterX` in the chain. One compensating change was required and is
justified: `run.py`'s `finish_combat` reconciles an escaped Thieving Hopper's
stolen cards by reading `SwipePower` off the escapee, which the strip would
destroy. C# has no deferred reconciliation at all (`SwipePower.Steal` removes
from the deck immediately, `SwipePower.cs:75`) — the post-hoc walk is sim-only
architecture — so the origins are handed off at the escape site and the
deck-theft outcome is numerically unchanged. What follows is the text as it
stood.

`CreatureCmd.Escape` calls `RemoveAllPowersInternalExcept()` (`CreatureCmd.cs:589`),
stripping every power silently — the deliberate contrast with death, which awaits
each `AfterRemoved` (`533-537`); the sim's escape (`cmds.py:221-234`) sets
`escaped = True`, fires an invented `on_creature_escaped` hook and leaves every
power on the creature **and registered as a live hook listener**. The three ported
escape sites (Thieving Hopper, Gremlin Merc, `BattlewornDummyTimeLimitPower`) leave
only owner-scoped, self-filtering powers.

### `creature_card_cmds/step18` — no `LoseBlock` verb  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 19).** `BlockCmd.lose_block` added with
C#'s guards, floor-at-0 and `AfterBlockBroken` re-fire on residual block;
`BurrowedPower` migrated off its raw `block = 0`, so Hand Drill now sees the event
C# gives it. The other three raw-assignment sites were re-checked against the
current file rather than the record's stale line numbers. What follows is the text
as it stood.

Four sites assign `block = 0` directly (`combat.py:297`, `player.py:158`,
`powers.py:1208`, `powers.py:2300`). `BurrowedPower`'s C# original calls
`CreatureCmd.LoseBlock(owner, all)` from `AfterRemoved`, so where C# re-fires
`Hook.AfterBlockBroken` on residual block the sim fires nothing. Hand Drill
(`relics/hand_drill.py:21`) is a live `on_block_broken` listener that would see the
difference.

### `creature_card_cmds/step23` — no `SetCurrentHp` verb  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 19).** `CreatureCmd.set_current_hp` added,
running the death pipeline at `CreatureCmd.cs:775-778` and firing
`AfterCurrentHpChanged` on the raw requested value. No ported caller needed
migrating — every direct assignment was re-confirmed strictly positive (revives).
One cited site (`powers.py`'s `ToricToughnessPower.block`) turned out to be a FALSE
POSITIVE: it is the power's own stored value, not a creature's, and is not part of
this mechanism. What follows is the text as it stood.

Sites that need one assign HP directly (`powers.py:2360-2365`, `cmds.py:112`); none
runs the death pipeline the way `CreatureCmd.cs:775-778` does, so setting HP to 0
through those paths would leave a 0-HP creature that never fired
`BeforeDeath`/`ShouldDie`/`AfterDeath`. Every ported direct assignment sets a
positive HP (a revive).

### `creature_card_cmds/step26` — no `SetMaxAndCurrentHp` verb  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 19), all 6 entries.**
`CreatureCmd.set_max_and_current_hp` added as SetMaxHp-then-SetCurrentHp
(`CreatureCmd.cs:856-860`); both ported callers migrated — Decimillipede's two sites
and ToughEgg's hatch. The five monster-tier entries' executed dormancy findings
stand unchanged (the assigned values still make every clause a no-op), but the sim
no longer relies on that to be correct. Two order-dependent consequences were found
and pinned rather than papered over: the silent MaxHp clamp pre-empting the HP event,
and the double-`_resolve_death` pass. Sibling `step25` (`SetMaxHp`, a
`deliberate-divergence` whose whole rationale was "there is no standalone
`set_max_hp` verb") was re-judged faithful in the same pass — there now is one.
What follows is the text as it stood.

Three C# callers, **two ported**: `DecimillipedeSegment.cs:142` and `ToughEgg.cs:173`
(plus `WaterfallGiant.cs:305`). Both ports hand-roll a raw assignment
(`monsters/hive/decimillipede.py:68` and `:167`, `monsters/hive/ovicopter.py:81-83`),
skipping `SetMaxHpInternal`'s CurrentHp clamp (`Creature.cs:493-501`), `SetMaxHp`'s
`if (MaxHp <= 0) Kill` (`CreatureCmd.cs:844-847`) and the `SetCurrentHp` death check.
- **monster sites added 2026-07-27, and its dormancy is now EXECUTED rather
  than asserted** 5, taking the mechanism to 6: the four Decimillipede
  segments and `monster/tough_egg`. The seam handed the content tier the
  liveness question and both answers came back dormant on observation, not on
  argument — Decimillipede's segments assign 40/46/44 and 46/42/44 (all even,
  strictly positive, distinct, `hp == max_hp`), and 2000 Ovicopter hatches put
  `max_hp` in [19,22] with delta never 0, so neither the clamp nor either
  `MaxHp <= 0 -> Kill` arm is reachable. A live `on_hp_changed` spy recorded
  **0 calls**, and the sim's only listener for it is player-gated
  (`relics/red_skull.py:45`).
- **one correction to the seam's wording** the Ovicopter site does **not**
  skip `AfterCurrentHpChanged`: `ovicopter.py:83` calls
  `ctx.hooks.on_hp_changed(self, delta)`, observed firing `('ToughEgg', 7)`.
  It bypasses the *command*, which is the real divergence.

### `creature_card_cmds/step51` — the Sly keyword is unported  [DORMANT] [unpinned]

No `CardKeyword.Sly` / `IsSlyThisTurn` analogue anywhere in `sts2_rl`, so
`CardCmd.Discard`'s collect-then-auto-play tail (`CardCmd.cs:186-188, 201-204`) and
the `AutoPlayType.SlyDiscard` path have no counterpart. Porting any Sly card also
makes step 50's DiscardAndDraw ordering live at the same moment.

### `creature_card_cmds/step56` — no `PileIndexSort` on transform  [DORMANT] [unpinned]

`CardCmd.cs:353-360, 405` sorts recorded tuples by (pile type, original index) so a
multi-card transform re-inserts deterministically; neither sim transform path sorts,
because both are single-card verbs. Trigger: porting any multi-card transform.

### `creature_card_cmds/step99` — no `AutoPlayFromDrawPile` verb  [DORMANT] [unpinned]

C# moves **every** selected card to the Play pile first and only then plays them,
which is what makes it immune to the second card's reshuffle disturbing the first
card's selection; the sim's Havoc-shaped effects pull and play one at a time.
Trigger: any ported card that plays more than one card from the draw pile.
**radius** `/N9`, `/N10`.

### `creature_card_cmds/N9` + `/step82` — the sim has no Play pile  [DORMANT] [unpinned]

C# holds a card being played in `PileType.Play` for the whole of `OnPlay`
(`CardPileCmd.cs:669-670`, `CardCmd.cs:114-117`) and `Shuffle` reads only Draw and
Discard (`CardPileCmd.cs:870-871`) — the entire mechanism behind the exoskeleton
reshuffle parity fact. The sim appends the played card to the **discard** pile and
holds it back from a reshuffle **in parity mode only** (`player.py:203, 232`),
because legacy RL runs are kept byte-for-byte. Residual exposure: an effect that
counts the discard pile during its own `OnPlay` sees the resolving card in the sim
and not in the game.

## 2H. Monster state machine remainder

### `monster_state_machine/G8` — no construction validation  [DORMANT] [pinned]

**Closed 2026-07-30 (tier-2 campaign).** All three sites faithful: step3
(duplicate-id raise) was already fixed round 4; step37 — `machine` is now a
guarded property + `reset_state_machine()` (MonsterModel.cs:228-236,
389-392); step22 — `add_branch` `max_times=None` sentinel raises on
overload #1's illegal `CAN_REPEAT_X_TIMES` shape (RandomBranchState.cs:46-51),
all 6 existing call sites already explicit. Pins:
`test/test_state_machine_construction.py`. What follows is the text as it
stood.

- **sites** `/step3` (duplicate state id: `Dictionary.Add` throws
  (`RandomBranchState.cs:171`, `MoveState.cs:74`), the sim's dict assignment
  silently overwrites), `/step37` (`monster.machine = other` is a legal Python
  rebind where the C# setter throws, `MonsterModel.cs:228-236`), `/step22`
  (overload #1's `CanRepeatXTimes` rejection, `RandomBranchState.cs:48-51`, has no
  sim analogue) — 3 entries, one mechanism: *C# validates a malformed machine and
  raises; the sim's API does not*.
- **trigger** Porting a monster with a repeated state id — `Fogmog.cs:44-45` is the
  near-miss in the shipped source — or any code that rebuilds a machine mid-combat.
  Dormancy executed over 82 of the 83 ported machines and 6,560,008 fuzzed
  transitions; `_Cultist` is unbuildable (needs a constructor arg) so it is
  unproven for that one machine.
- **pin** `TestMonsterStateMachineOrder::test_duplicate_state_id_is_rejected_at_machine_construction`.

### `monster_state_machine/G7` — `AddBranch` repeat-limit edge cases  [DORMANT] [pinned]

**Closed 2026-07-30 (tier-2 campaign).** step21 (maxTimes==0 permanently
disables) was already fixed round 4; step15 — the pre-draw zero-total
special case is gone, `get_next_state` runs C#'s exact loop
(RandomBranchState.cs:115-127): genuine float fall-through raises with C#'s
literal message, and an all-zero weight vector burns one draw and resolves
to the FIRST branch, no crash — this also closes the unnumbered clause-b
Flyconid hazard from the outstanding-defects list (the machinery half;
Flyconid itself stays hand-rolled). Pins:
`test/test_state_machine_construction.py::TestRandomBranchFallThrough`.
What follows is the text as it stood.

- **sites** `/step21` (clause a: `maxTimes == 0` with `CanRepeatXTimes`
  **permanently disables** the branch in C#, `RandomBranchState.cs:144-147`; the sim
  refuses to build the machine at all), `/step15` (clause c: a float
  subtract-and-check fall-through **throws** in C#, `RandomBranchState.cs:127`, and
  quietly picks the last branch in the sim) — 2 entries.
- **trigger** A C# monster added with `AddBranch(state, 0)`; all 15 non-default
  integer arguments across the 61 call sites are 2 or 3 today. The fall-through
  needs a non-dyadic weight — the only ported one is `TwoTailedRat.cs:127`'s
  `1f/12f`, behind a `_can_summon()` gate the machine-only fuzz cannot open.
- **pin** `TestMonsterStateMachineOrder::test_max_times_zero_disables_the_branch_instead_of_raising`.
- **radius** `monster_state_machine/G1` is the same `AddBranch` argument surface — read both
  before touching `add_branch`.

### `monster_state_machine/G2` — no way to express an unreachable registered state  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign) — machinery only, with a premise
correction.** `MonsterMoveStateMachine.__init__` gained `unreachable_states`
(registered via the same `register_states`, never reachable, no graph-walk —
matching MonsterMoveStateMachine.cs:20-25). Correction: Inklet's `INIT_RAND`
and PhrogParasite's `RAND` are NOT the same shape — only PhrogParasite's is
registered-but-unwired (PhrogParasite.cs:51); Inklet's never reaches the
constructor at all (Inklet.cs:69-84) and needs no machinery. Moving either
hand-rolled port onto `MachineMonster` is follow-up content work; their
zero-draw pins stay green. What follows is the text as it stood.

`Inklet.cs:69-71` builds and registers `INIT_RAND` with two branches (one of them
`AddBranch(JAB, 2, 1f)` = maxRepeats 2) and never wires it; `PhrogParasite.cs:6-10`
is the same shape. Reproducing only the reachable graph is *correct* today, but the
sim cannot express the dead state, so the moment one becomes reachable the port
silently keeps the old graph. Pinned in the opposite direction by
`test/test_monster_branch_audit.py::TestInkletMoveSequence` and
`::TestPhrogParasiteMoveSequence`, which assert **zero** `monster_ai` draws on
exactly those legs.

## 2I. Turn structure remainder

### `turn_structure/G10` — the combat-end path collapses five C# distinctions  [DORMANT] [unpinned]

**Mostly closed 2026-07-29 (round 5), with `turn_structure/N5`.** Two asymmetric exits: the losing one fires no hook at all, the winning one revives then fires `Hook.AfterCombatEnd` and `Hook.AfterCombatVictory` in turn. `lose_combat()` is the deferral. Four relics moved onto their real hooks. Clause (d) was stale — round 4's per-side rewrite had already removed the two disagreeing player-death exits. What follows is the text as it stood.

- **sites** 7 entries (`/G10`, `/N5` and five steps).
- C# distinguishes a **loss** (`LoseCombat()` -> `_pendingLoss` ->
  `ProcessPendingLoss()`, which fires the `CombatEnded` event and **no hook at
  all**, `CombatManager.cs:945-965`) from a **victory** (`EndCombatInternal` with
  `ReviveBeforeCombatEnd()` -> `AfterCombatEnd` -> `AfterCombatVictory`,
  `970-1033`), and consults `Hook.ShouldStopCombatFromEnding` inside `IsEnding`
  (`196-199`). The sim has one `_end_combat(player_won)` firing one
  `on_combat_end` (`combat.py:347-350`), no revive step, no
  `should_stop_combat_from_ending`.
- **On top of that**, `_run_enemy_turns` has **two player-death exits that
  disagree**: `combat.py:308-310` calls `_end_combat(player_won=False)` (the hook
  fires) while `combat.py:332-335` sets phase/result by hand and returns (it does
  not). Executed: `killed from on_enemy_turn_start: hooks=[('on_combat_end',
  False)]` versus `killed by the attack: hooks=[]` — same end state, different hook
  record.
- **trigger** Any `AfterCombatVictory`-only listener with an unconditional effect;
  the two-exit inconsistency goes live for any `on_combat_end` listener whose
  effect outlives the combat. All four ported listeners gate on victory or on the
  player being alive. The win-condition **predicate** itself is faithful (`/N5`).
- **radius** `turn_structure/G13` and `hook_dispatch/G8` — one design.

### `turn_structure/step14` — `AfterBlockCleared` fires unconditionally  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign) — STALE.** The record's "fused loop"
text described pre-round-4 code; today's `_run_enemy_turns` runs two
complete side-wide passes and all three no-op cases (no block, vetoed clear,
turn-1 early return) reach the listener — executed via
`test/test_turn_structure_residues.py` (Task 12, 4 pins). Residues A/B/D of
the same task confirmed `turn_structure/G11`, `/G16` and `/G10` closed as
recorded (step63's missing `AfterFlush` stays open+dormant, Bookmark
unported). What follows is the text as it stood.

The surviving site of the closed `turn_structure/G1` mechanism. C# runs a SECOND,
separate loop over the same participants — `await Hook.AfterBlockCleared(state,
creature)`, **unconditional** (`CombatManager.cs:500-507`, `Hook.cs:119-125`). It
fires for a creature that had no block, for a creature whose clear was PREVENTED,
and for a player on turn 1 whose `AfterTurnStart` returned early. The complete
second pass is ported; what is still recorded is whether every one of those three
no-op cases reaches the listener. Re-execute before working it.

### `turn_structure/step32` + `/step67` — no `SpawnedThisTurn` flag, no `OnSideSwitch`  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 13) — and the DORMANCY VERDICT WAS
WRONG.** The record argued no spawn survives to `TakeTurn` because it would be
outside "step 31's snapshot" — but step 31 is `ExecuteEnemyTurn`'s own
`_state.Enemies.ToList()` (CombatManager.cs:1072-1074), taken *after*
`AfterSideTurnStart` completes, not the earlier `creaturesStartingTurn` list.
A creature spawned during `AfterSideTurnStart` (Poison kills a monster →
Stock/Infested/Surprise spawns — ordinary gameplay) is invisible to the first
list but present in step 31's, still flagged. In the sim that path CRASHES
without the guard (`RuntimeError: No move has been set for the monster`).
`spawned_this_turn` + a single per-side clear now implement it (one reader in
C# and in the sim, so no `OnSideSwitch` verb was needed; a second reader would
need one). Step 31's own "faithful" rationale is overbroad in the same way and
should be tightened by whoever next touches it. What follows is the text as it
stood.


`TakeTurn` runs `PerformMove()` only if `!Monster.SpawnedThisTurn`; `grep -rn
spawned_this_turn sts2_rl/` returns 0 hits, and there is no side-switch verb to
clear it either (`CombatManager.cs:1420-1424`, `MonsterModel.cs:479-483`). The
no-`IsDead`-guard half **is** faithfully ported (`combat.py:288-292` keeps a
`retained_after_death` corpse in the loop — that is how a withered Decimillipede
segment reaches REATTACH). The record could not construct a reachable C# path where
the flag survives to `TakeTurn`. **radius** `monster_state_machine/G9`.

## 2J. Content-tier dormant families

The content tiers' recurring dormant mechanisms. Each is one decision
recorded on many units, so each is one fix — and each is a *large* fix, because
the population is large.

### `card/_unplayable_cost` — an unplayable card's canonical energy cost is `-1` in C# and `0` in the sim  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign).** All 29 `_init_vars` set
`self._energy_cost = -1`, each verified against its own C# constructor;
`Card.energy_cost` (`sts2_rl/cards/base.py`) short-circuits on
`_energy_cost < 0` before any local or global modifier, mirroring
`CardEnergyCost.GetWithModifiers`. The readers audit found the three known
readers still correct and the spend path / observation encoder unchanged by
construction (`hooks.modify_card_energy_cost`'s `max(0, cost)` tail clamp).
One new sim-internal finding left OPEN and filed in "Named work with no
entry of its own": `selectors.py`'s "to_draw_top" unclamped cost ranking.
Pins: `test/test_unplayable_cost.py` (15 tests). What follows is the text
as it stood.

- **sites** 29 entries, one per unplayable curse/status/quest card
  (`ascenders_bane`, `bad_luck`, `burn`, `byrdonis_egg`, `clumsy`,
  `curse_of_the_bell`, `dazed`, `debt`, `decay`, `disintegration`, `doubt`,
  `folly`, `greed`, `guilty`, `infection`, `injury`, `lantern_key`, `mind_rot`,
  `normality`, `poor_sleep`, `regret`, `shame`, `sloth`, `soot`, `spoils_map`,
  `waste_away`, `wither`, `wound`, `writhe`). **Joint-largest mechanism in the
  queue.**
- **impact** C today, B the moment any cost reader distinguishes the two.
- **divergence** `base(-1, CardType.Curse, …)` (`AscendersBane.cs:19-22`) versus
  `self._energy_cost = 0` (`sts2_rl/cards/ascenders_bane.py:33`). `-1` is not a
  cosmetic marker: `CardEnergyCost.GetWithModifiers` short-circuits on
  `if (_base < 0) return num;` (`CardEnergyCost.cs:100-103`) **before** any local
  or global cost modifier, so in the game an unplayable curse is immune to every
  cost modifier and keeps reporting `-1`, while `Card.energy_cost`
  (`sts2_rl/cards/base.py:222-232`) runs the whole
  `_free_this_turn` / `_cost_this_turn` / `_cost_this_combat` /
  `_cost_delta_this_turn` chain over a base of 0.
- **observable** None yet. `GetAmountToSpend()` clamps to `Math.Max(0, …)`
  (`CardEnergyCost.cs:134-139`), so the two agree on what is *spent* — the
  divergence is confined to what is *read*, and the three ported readers were
  checked and all agree by accident (`sts2_rl/relics/mummified_hand.py:25` and
  `sts2_rl/potions.py:168` filter on `energy_cost > 0`;
  `sts2_rl/cards/event_cards.py:328` skips at `<= 1`).
- **trigger** The first cost reader that distinguishes `-1` from `0`, or any
  content that applies a cost modifier to an unplayable card and then reads it
  back.
- **fix** Set `self._energy_cost = -1` in all 29 `_init_vars` and give
  `Card.energy_cost` the `< 0` short-circuit. One convention, 29 one-line edits,
  one property. Failing test asserts a Wound under Curious still reports -1.
- **radius** All 29 cards; touches `Card.energy_cost`, which everything reads.

### `card/_printed_vars` — printed card vars with no `_init_vars` entry  [DORMANT for the game, LIVE for the observation encoder] [unpinned]
**Closed 2026-07-30 (tier-2 campaign, Task 24), 23/23.** Every card stores
its printed CanonicalVars under a `_`-attribute the
`base_damage`/`base_block`/`base_hp_loss`/`base_gold`(new)/`magic_number`
API reads (guilty/normality/expect_a_fight via live `magic_number`
overrides — their C# var is computed, not constant; wither overrides
`base_damage`). feel_no_pain's value was WRONG (stored in `_block`,
misreporting a block-granting card), now `_power_amount`. No behavior
change anywhere; obs LAYOUT unchanged, encoded VALUES move for 20/23 —
**checkpoint note: retrain/re-evaluate policies sensitive to f[17]/f[18]/
f[20]/f[21]/f[22]/f[23] for those cards**. 3/23 (debt, spoils_map,
rolling_boulder's 2nd number) have no live obs read site regardless.
Pins: `test/test_printed_vars.py` (48). What follows is the text as it
stood.


- **sites** 23 entries (`bad_luck`, `beckon`, `breakthrough`, `burn`, `colossus`,
  `corruption`, `debt`, `decay`, `doubt`, `equilibrium`, `expect_a_fight`,
  `feel_no_pain`, `guilty`, `infection`, `normality`, `pacts_end`,
  `rolling_boulder`, `shame`, `slimed`, `spoils_map`, `stampede`, `toxic`,
  `wither`).
- **impact** C for game fidelity; **B for anything training against the sim**.
- **divergence** `new HpLossVar(13m)` (`BadLuck.cs:25`) is a printed card var; the
  sim declares no `_hp_loss` in `_init_vars`, so `Card.base_hp_loss`
  (`sts2_rl/cards/base.py:202-210`) returns its 0 default and the 13 exists only
  as a literal inside `on_turn_end_in_hand`. Same shape for `DamageVar`,
  `BlockVar`, `GoldVar` and generic `DynamicVar`s.
- **observable** The dealt damage is identical, so no player-visible combat
  outcome differs — **but `sts2_rl/full_env.py:488` encodes
  `card.base_hp_loss / ABS_SCALE` into the observation vector, so a policy sees
  Bad Luck as a harmless 0-HP-loss curse.** One variant differs: `feel_no_pain`
  stores its generic `DynamicVar("Power", 3m)` in `_block`, so the sim reports it
  as a card that itself grants 3 block.
- **trigger** For game fidelity, any C# reader of the printed var. For the sim,
  it is already live in every training run.
- **fix** One line per card in `_init_vars`. The records give the value and the
  attribute for each.
- **radius** The observation vector, i.e. every trained checkpoint — an obs
  change is a checkpoint migration, so this is not a free fix.

### `power/_stack_type_single` — `PowerStackType.Single` misread as "does not stack"  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 25), 16/16.** All 15 `on_stack`
no-op overrides deleted; the base `Power.on_stack` adds, matching
`PowerCmd.ModifyAmount`'s unconditional add. None of the 16 overrides
`InstanceType`, so none needed T1's instance machinery. Two corrections to
this entry's own list: **dampen's C# StackType is `None`, not Single**
(`DampenPower.cs:22`) — its deletion is inert because MagiKnight dedupes
caller-side and never reaches `PowerCmd.Apply`; and **hex genuinely reads
Amount** (`HexPower.cs:79` → `CardCmd.Afflict<Hexed>(card, Amount)`), so its
deletion closes a real divergence still dormant only because SpectralKnight
never re-reaches HEX and KnightsElite fields exactly one. Illusion needed no
override. Pins: `test/test_stack_type_single.py` (39). What follows is the
text as it stood.


- **sites** 16 entries (`adaptable`, `burrowed`, `confused`, `corruption`,
  `dampen`, `hellraiser`, `hex`, `illusion`, `imbalanced`, `nemesis`, `no_draw`,
  `no_energy_gain`, `smoggy`, `soar`, `surrounded`, `the_gambit`); the census
  counts **15 sim `on_stack` no-op overrides**
  (`py audit/tools/power_census.py stack`).
- **impact** C while nothing reads the amount, B the moment something does.
- **divergence** `PowerStackType.Single` means "Amount is hidden, and is always
  displayed as 1" (`PowerStackType.cs:10-13`). `PowerCmd.ModifyAmount`
  (`PowerCmd.cs:236`) **adds unconditionally, with no `StackType` branch**, so C#
  really reaches Amount 2. 15 sim powers override `on_stack` to `pass` citing
  Single, dropping a re-application's offset.
- **observable** None on ported content: nothing reads these powers' `Amount` —
  Adaptable's revive machinery is driven by the private `isReviving` /
  `is_reviving` flag (`AdaptablePower.cs:13`, `sts2_rl/powers.py:3360`), and the
  Test Subject applies it once at combat start. `power/illusion` is the one unit
  that goes the **other** way: it does *not* override `on_stack`, so a second
  application stacks — the same misreading, opposite sign.
- **trigger** Any reader of one of these 16 powers' `Amount`, or any content that
  applies one of them twice in a combat.
- **fix** Delete the 15 `on_stack` overrides. That is the whole fix; the base
  `Power.on_stack` already adds. Failing test asserts Amount 2 after two
  applications of a Single power.
- **radius** 16 powers. Adjacent to `power_cmd/G5` (`PowerInstanceType`), which
  is the *other* stacking axis the sim does not model.

### `card/_is_dead_early_return` — a sim `is_dead` early return splits one card's effect in two  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 20), both sites.** The blocker Task 27
identified was the root, and Task 20 owned the file it lived in: `EnergyCmd.gain`
now bails on `is_ending(hooks)`, mirroring `PlayerCmd.GainEnergy`'s
`!CombatManager.Instance.IsEnding` guard over its whole body
(`PlayerCmd.cs:29-43`) and matching `CardCmd.downgrade`/`upgrade`'s existing
idiom — `is_ending`, NOT `is_over_or_ending`, which is a real distinction in
this codebase. With the root fixed, Bloodletting's and Offering's sim-only
`is_dead` early returns were deleted, joining Blood Wall / Brand / Hemokinesis's
pattern. This also narrowed `relic/lantern/g1` to its last clause (the missing
`AfterModifyingEnergyGain` companion). What follows is the text as it stood.
**Partly closed 2026-07-31 (tier-2 campaign, Task 27) — and this entry's
stated dependency was WRONG.** blood_wall, brand and hemokinesis are FIXED
(returns deleted): every command their continued effect reaches already
self-gates exactly as its C# counterpart does (BlockCmd/GainBlock,
select_cards/FromHand, PowerCmd.apply/Apply, DamageCmd's dealer-dead bail vs
AttackCommand's own checks), and death is synchronous on both sides, so the
guard was provably redundant. bloodletting and offering stay OPEN, blocked
NOT by `power/_death_prevention_branch` (its remaining sites are per-power
revival paths; the generic prevented-death arm no longer floors at 1 HP) but
by **`EnergyCmd.gain`'s missing `IsEnding` bail** (C#: `PlayerCmd.cs:31`) —
the same mechanism as `relic/lantern/g1`. Delete those two in the commit
that adds the bail. Also found: **`card/breakthrough` is an uncounted 6th
site** of this idiom, same safety class as the three closed (filed in "Named
work"). Pins: `test/test_is_dead_early_returns.py` (11). What follows is the
text as it stood.


- **sites** `card/blood_wall`, `card/bloodletting`, `card/brand`,
  `card/hemokinesis`, `card/offering` (5 entries).
- **impact** C — no observable while the sim's death model holds.
- **divergence** `sts2_rl/cards/blood_wall.py:39-40` returns early on
  `if ctx.player.is_dead` between the HP loss and the block gain; `BloodWall.cs`
  has no such return and still awaits `CreatureCmd.GainBlock`, firing
  `Hook.ModifyBlock` and `AfterModifyingBlockAmount` on the dying player. Brand's
  return skips **both** the exhaust and the Strength.
- **observable** None: the sim's death-prevention path floors a saved creature at
  1 HP (`sts2_rl/cmds.py:106-112`), so `is_dead` here means genuinely dead and
  the combat is lost on both sides before a listener could read the result.
- **trigger** **`power/_death_prevention_branch`.** The moment the prevention
  arm stops flooring at 1 HP and starts leaving a live-but-dead creature the way
  C# does, `is_dead` becomes True in a window where the game keeps executing —
  and these five cards diverge immediately. **Fix the death branch and these five
  wake up in the same commit.**
- **fix** Delete the five early returns once the death model is right.
- **radius** Any card with a mid-effect HP loss. The five are the ones the card
  tier found; the pattern is a sim idiom, so a grep for
  `if ctx.player.is_dead` is the real population.

### `creature_card_cmds/step8c` — no `ShouldStopCombatFromEnding`; the win check has no veto point  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 26) — the entry was STALE and
self-contradictory.** The hook, its dispatch from the win check, and its
deliberate exclusion from the combat-gate table were all shipped by an earlier
round (the record claims both that all five C# overrides are ported and that
`hooks.py` defines no such hook). Four of the five powers already had their
override; only SurprisePower's was missing and is now added
(SurprisePower.cs:40-43), with a provable — not asserted — dormancy argument.
What follows is the text as it stood.


- **sites** `creature_card_cmds/step8c` (the engine-level home, **added
  2026-07-26**) plus `power/adaptable/ShouldStopCombatFromEnding`,
  `/infested`, `/steam_eruption`, `/stock`, `/surprise` (6 entries). The power
  record states the merge: "this mechanism now also carries `gap` at
  `audit/records/seam/creature_card_cmds.json` step 8c, which owns the missing
  hook surface itself; same verdict at every site per rule 3."
- **impact** C today — the sim reaches the same outcome by a different route in
  all five cases.
- **divergence** The win check returns false while
  `Hook.ShouldStopCombatFromEnding(_state)` is true (`CombatManager.cs:196`), and
  `Hook.cs:2442-2452` dispatches it to **every** listener, deliberately *outside*
  the `IsOverOrEnding` gate — `Hook.cs:2436-2441`'s own comment explains why:
  "it is a predicate that drives the decision of whether combat ends, so
  suppressing it while combat is ending would drop the votes it collects."
  `sts2_rl/hooks.py` defines no such hook and
  `sts2_rl/combat.py:272-277`'s `_all_enemies_dead` decides the win purely from
  `is_gone` over the non-minion enemies. There is no other veto point in the loop.
- **observable** None yet. All five ported overrides are paired with either a
  death prevention (`adaptable`, `steam_eruption`) or a mid-death spawn /
  retention that already keeps `_all_enemies_dead()` false on its own — so the
  dormancy is **per-power, not structural**.
- **trigger** A power that wants to hold combat open **without** also preventing
  a death or adding a creature. Also: fixing `power/_death_prevention_branch`
  removes the accidental cover for `adaptable` and `steam_eruption`, so that fix
  wakes this one.
- **fix** Add `should_stop_combat_from_ending` to `sts2_rl/hooks.py`, dispatch it
  from `_all_enemies_dead`, and *do not* gate it behind any combat-over check —
  the C# comment is explicit that gating it is the bug. Failing test asserts a
  power returning true keeps the combat alive with all enemies gone.
- **radius** The win check, i.e. every combat. Both this and
  `creature_card_cmds/step8b` were **prose-only in a stream report** until the
  power tier's fix pass gave them a record — they had no verdict, so they reached
  neither `audit_status` nor this queue nor any fix work list. That is the
  strongest available argument for the audit pipeline over ad-hoc reports.

### `power/_after_damage_given_substitution` — `AfterDamageGiven` ported onto `on_damage_received`  [DORMANT] [unpinned]
**Closed 2026-07-31 (tier-2 campaign, Task 26).** `on_damage_dealt` dropped its
`hp_lost > 0` dispatch condition, so the dealer-side event now sees fully-blocked
and zero-damage hits as `CreatureCmd.cs:388-395` does, and gained a
`was_fully_blocked` value mirroring C#'s formula exactly; Imbalanced and
PaperCuts moved onto it. Imbalanced also lost two guards C# never had (a
self-target exclusion — free on the dealer side — and a MOVE-only filter);
inert today since its only applier, BowlbugRock, never hits itself. T2's
dealer-before-victim order and killing-blow snapshot are intact. What follows is
the text as it stood.


- **sites** `power/imbalanced/AfterDamageGiven`, `power/paper_cuts/AfterDamageGiven`
  (2 entries, identical text).
- **impact** B when the powers are reachable; dormant only because they are not.
- **divergence** C#'s `AfterDamageGiven` is the **dealer**-side after-damage
  event; the sim's counterpart is `on_damage_dealt` (`sts2_rl/hooks.py:469`,
  fired at `sts2_rl/cmds.py:123-124`), and these powers use
  `on_damage_received` filtered on `dealer is self.owner` instead. **The reason
  the port had to do that is itself the finding:** `sts2_rl/cmds.py:123` fires
  `on_damage_dealt` only `if dealer is not None and hp_lost > 0`, so the sim's
  dealer-side event **cannot see a fully-blocked or zero-damage hit at all**,
  where C#'s sees every one — `result.WasFullyBlocked` is a field it is expected
  to read, and `ImbalancedPower.cs:19` keys the entire power on it.
- **observable** The substitution then inherits `sts2_rl/cmds.py:121`'s
  killing-blow guard, which C#'s dealer-side event does not have — the sim's own
  comment at `sts2_rl/cmds.py:119-120` says as much — so the power silently stops
  working on a lethal hit in the sim and keeps working in the game.
- **trigger** Porting a reachable applier for either power.
- **fix** Drop the `hp_lost > 0` condition from `on_damage_dealt`'s dispatch and
  move both powers onto it. Failing test asserts the power fires on a fully
  blocked hit.
- **radius** Every current and future `on_damage_dealt` listener — the dispatch
  condition is the bug, the two powers are only where it was noticed. Adjacent to
  `power/_killing_blow_guard` and `damage_pipeline/G6`.

## 2K. Monster-tier dormant families

Six dormant mechanisms, 12 entries. Three of them are the same underlying hole:
**the sim's intent vocabulary is lossier than C#'s `AbstractIntent[]`**, which
`monster_state_machine` boundary item 2 named as belonging to no seam's scope
and which nothing has audited since. They are dormant because no sim consumer
reads the missing part today — but the RL observation encoder is exactly the
kind of consumer that would, and `monster/_second_intent_dropped` is the same vocabulary hole already
LIVE for two moves that drop a whole intent rather than a field of one.

### `monster/_no_intent_unrepresentable` — a `MoveState` with an empty intent array  [DORMANT] [unpinned]
**Closed 2026-07-30 (tier-2 campaign, Task 28).** `MoveType.NONE` +
`Intent.none()` make the empty telegraph expressible; all 4 Battle Friend
sites use it; encoder flags stay all-zero for the dummies and byte-identical
for everyone else. What follows is the text as it stood.


- **sites** 4 (`monster/__battle_friend`, `monster/battle_friend_v1`, `_v2`,
  `_v3`).
- **divergence** `BattleFriendV1.cs:28`, `BattleFriendV2.cs:28` and
  `BattleFriendV3.cs:28` construct `NOTHING_MOVE` with **no
  intents at all** — the `params AbstractIntent[]` array is empty, so the dummy
  telegraphs nothing. The sim's `Intent` dataclass requires a `MoveType`, so the
  port substitutes one; there is no way to express "no intent".
- **dormancy** The Battleworn Dummy fight gives no rewards and the substituted
  intent drives nothing mechanical.
- **trigger** Any consumer that distinguishes "no intent" from a real one — the
  observation encoder, or a replay assertion on the intent panel.

### `monster/_intent_count_lost` — `StatusIntent(N)` loses its N  [DORMANT] [unpinned]
**Closed 2026-07-30 (tier-2 campaign, Task 28) for its three recorded
sites.** `Intent.status_count` carries C#'s number (aeonglass WitherAmount=1,
the_insatiable 6, test_subject BurningGrowlBurnCount=3); the encoder
deliberately stays a flag bit. `Vantom.cs:119`'s `StatusIntent(3)` (DISMEMBER)
is a genuine, previously-uncounted 4th site — filed under "Named work with no
entry of its own". What follows is the text as it stood.


- **sites** 3 (`monster/aeonglass` INCREASING_INTENSITY, `monster/the_insatiable`
  LIQUIFY, `monster/test_subject` BURNING_GROWL).
- **divergence** C# `StatusIntent` carries the **number** of status cards the
  player is about to receive and the intent panel renders it
  (`StatusIntent(WitherAmount)`, `StatusIntent(6)`,
  `StatusIntent(BurningGrowlBurnCount)`). The sim's `Intent`
  (`monsters/base.py`) has no count field at all, so the type survives and the
  number does not.
- **dormancy** Executed: `full_env.py:571` sets a single flag bit for the status
  intent and no sim consumer reads a count.
- **trigger** Giving `Intent` a count field, or any observation/replay consumer
  that reads one. Note the effects themselves are all correct — this is a
  telegraph-only loss, which is why it is dormant where `monster/_second_intent_dropped` (a dropped
  *whole* intent, read by `Intent.has()`) is live.

### `monster/_retained_corpse_in_scan` — a teammate scan that the sim filters and C# does not  [DORMANT] [unpinned]
**Closed 2026-07-30 (tier-2 campaign, Task 28).** Both scans now filter on
`not enemy.is_removed_from_combat` — membership-only, matching
`Guardbot.cs:51` / `Queen.cs:187-188`; a death-vetoed retained corpse is a
valid target, ordinary kills stay excluded. What follows is the text as it
stood.


- **sites** 2 (`monster/guardbot` GuardMove, `monster/queen` BurnBrightForMe).
- **divergence** `Guardbot.cs:51` is
  `CombatState.Enemies.Where(c => c.Monster is Fabricator)` and
  `Queen.cs:187-188` is `GetTeammatesOf(Creature).Where(t => t != Creature)` —
  **membership of the enemy side is the only test in both**. A creature whose
  removal was vetoed (`ShouldCreatureBeRemovedFromCombatAfterDeath`) is still in
  `Enemies` and is therefore still a valid target. The sim's ports filter the
  corpse out.
- **why it is not `power/_death_prevention_branch`** This is a *consequence* of the death-prevention
  mechanism, not that mechanism: fixing the death hooks does not fix these scans,
  and fixing these scans does not restore `AfterDeath`. Recorded separately for
  that reason. (The first `gap_queue.py` run merged them and it was wrong.)
- **dormancy** Executed: none of the three sim `should_die`/retention
  implementers is applied to anything in a Fabricator or Queen encounter, so no
  retained corpse can be present when either scan runs.
- **trigger** Any retained corpse on the Glory enemy side — an Illusion,
  Reattach or Adaptable holder joining either fight.

### `monster/aeonglass/AfterCardGeneratedForCombat` — generated Withers are not fake-upgraded  [DORMANT] [unpinned]

**Closed 2026-07-30 (tier-2 campaign, Task 8).** Aeonglass now has a real
`on_card_generated_for_combat` listener mirroring `Aeonglass.cs:150-166`;
both open-coded upgrade loops deleted. This entry's own anticipated trigger
("any third Wither source — drawing one from `StatusCardPool.cs:28`") was
ALREADY reachable — `wither` sits in the in-combat transform Status pool, so
an Entropy transform could roll one un-upgraded; the old "executed" dormancy
verdict was stale because `monster_probes_b06.py`'s literal `WitherCard(`
grep cannot see `make_card()` construction (probe defect filed under
Outstanding record defects). Transform-rolled Withers now arrive
fake-upgraded. What follows is the text as it stood.

- **sites** 1 (`monster/aeonglass`), and it is the **second** of the eleven
  unclaimed hook overrides that turned out mechanical (`monster/queen/AfterDeath`, now closed, was the other).
- **divergence** `Aeonglass.cs:150-166` fake-upgrades **every** generated Wither
  to `WitherUpgradeCount`, and the hook is dispatched generally from
  `CardPileCmd.cs:246` and `CardCmd.cs:504`. The sim has no dispatch for it and
  open-codes the upgrade at each Wither site instead.
- **dormancy** Executed: the sim constructs a `WitherCard` at exactly two sites
  (`aeonglass.py:79` and `powers.py:3286`) and **both already match** what the
  hook would have produced.
- **trigger** Any third Wither source — drawing one from `StatusCardPool.cs:28`,
  or porting any of the other six `AfterCardGeneratedForCombat` implementers.
- **record inconsistency found here** `power/withering_presence` cites
  `WitheringPresencePower.cs:37` as where generated Withers are matched. That
  line is inside `ExtraHoverTips`, a hover-tip preview; the real matching is this
  Aeonglass hook. Reported, not edited.

### `monster/knowledge_demon/g1` — the curse's power is applied by the wrong creature  [DORMANT] [unpinned]
**Narrowed 2026-07-30 (tier-2 campaign, Task 28).** The applier half is
fixed (applier=player per all four curse cards' C#); the card-SOURCE half
stays open — `PowerCmd.apply`/`Power` model no source parameter anywhere, an
architecture-wide absence belonging to power_cmd ownership. What follows is
the text as it stood.


- **sites** 1 (`monster/knowledge_demon`).
- **divergence** In the game the curse card applies its own power with the
  **player** as applier and the card as the source (`Disintegration.cs:25-28`,
  `MindRot.cs:25-28`, `Sloth.cs:25-28`, `WasteAway.cs:28-31`); the port applies
  it with the demon as applier.
- **dormancy** No ported listener distinguishes the applier on these four powers.
- **trigger** Any listener that gates on applier identity for a curse-applied
  power — `PowerCmd.Apply`'s `applier` is not decoration: a null or wrong applier
  skips the `Hook.ModifyPowerAmountGiven` pass and changes
  `FindExistingInstanceForStacking`'s key.

### `monster/magi_knight/g1` — `DampenPower`'s caster set collapsed to a bare re-apply  [DORMANT] [unpinned]
**Closed 2026-07-30 (tier-2 campaign, Task 28).** Real caster set with
refcounted `on_death` removal and last-caster expiry; MagiKnight
fetches-or-creates, applying only on create (`MagiKnight.cs:78-96`,
`DampenPower.cs:41-56`). What follows is the text as it stood.


- **sites** 1 (`monster/magi_knight`).
- **divergence** `MagiKnight.cs:82-92` fetches the target's existing
  `DampenPower`, calls `AddCaster(base.Creature)` on it, and calls
  `PowerCmd.Apply` **only when it had to create one**;
  `DampenPower.AfterDeath` then removes one caster. The sim re-applies
  unconditionally and models no caster set.
- **dormancy** Executed: `grep` shows MagiKnight is the **only** Dampen applier
  in the game, `KnightsElite` yields exactly one, and DAMPEN is unreachable twice
  in its chain — so the caster set can never hold more than one entry.
- **trigger** A second Dampen applier, or an encounter with two Magi Knights.

---

# Tier 3 — the long tail

One gap entry each. They are real, recorded and verified — they are here rather
than written out because a single-unit finding is cheaper to read in its own
record than restated, and because a prose list this long would bury Tiers 1
and 2.

Each row is the mechanism id, the liveness the record's own text states, and
that record's lead clause, trimmed. **Line numbers are stripped from these
summaries on purpose** — open the record for the citation, so that `cite-check`
stays a check on the authored prose above rather than a re-validation of the
record excerpts. The id is the path: `power/aggression/…` is
`audit/records/power/aggression.json`.

`unlabelled` means the record states neither LIVE nor DORMANT anywhere in the
entry. That is not a third state — it is a hole, and the shared contract now
asks for the `live` key precisely because of it. **An unlabelled row is not a
dormant row.**

## 3A. `power` — 117 single-site mechanisms

One power, one finding. The recurring power families are written out above —
`power/_death_prevention_branch` in Tier 1, and `power/_stack_type_single`,
`power_cmd/G5`, `creature_card_cmds/step8c` and
`power/_after_damage_given_substitution` in Tier 2. Everything below stands
alone.

- `power/adaptable/ShouldCreatureBeRemovedFromCombatAfterDeath` — *unlabelled* — The sim HAS the hook (hooks.py, consumed at cmds.py to set retained_after_death) and this power does not use it, because the sim took the death-prevention route instead (see the AfterDeath entry). Folded into that entry's …
- `power/aggression/BeforeSideTurnStart` — *unlabelled* — The card selection uses the wrong RNG and the wrong shuffle. AggressionPower.cs is source.ToList().UnstableShuffle(Rng.CombatCardSelection).Take(Amount) -- an UnstableShuffle drawn from the dedicated CombatCardSelection stream. …
- `power/artifact/AfterModifyingPowerAmountReceived` — *unlabelled* — The stack-consumption event is hand-inlined. C# consumes the stack via PowerCmd.Decrement(this) from AfterModifyingPowerAmountReceived (ArtifactPower.cs) -- i.e. through the full ModifyAmount pipeline, which is what runs …
- `power/artifact/TryModifyPowerAmountReceived` — dormant — The interception is reimplemented outside the hook system entirely, and the debuff test is the wrong one. C# (ArtifactPower.cs) is a TryModifyPowerAmountReceived listener whose three guards are target != Owner, …
- `power/buffer/ModifyHpLostAfterOstyLate` — dormant — The arithmetic is exact -- 0 for the owner, unchanged otherwise (BufferPower.cs vs powers.py) -- and the AFTER-Osty position is right, since cmds.py runs after block absorption (:74-81). What is lost is the LATE half, and …
- `power/burrowed/AfterRemoved` — dormant — C#'s AfterRemoved is CreatureCmd.LoseBlock(oldOwner, 999999999m) -- dump ALL the block -- and it runs on EVERY removal path, including the automatic strip when the owner dies (CreatureCmd.cs then each power's AfterRemoved). The …
- `power/calamity/BeforeCardPlayed` — dormant — C# uses a TWO-HOOK LATCH the sim collapses into one. CalamityPower.cs records amountsForPlayedCards[card] = base.Amount at BeforeCardPlayed and :44 removes it at AfterCardPlayed, so (a) the Amount is SNAPSHOTTED at the start of …
- `power/chains_of_binding/AfterCardDrawn` — dormant — Two divergences. (1) A DROPPED GUARD: C# requires base.CombatState.CurrentSide == base.Owner.Side (ChainsOfBindingPower.cs), so only cards drawn during the PLAYER's own turn are Bound; the sim has no side test (powers.py), so a …
- `power/chains_of_binding/BeforeCardPlayed` — dormant — WRONG SIDE OF THE PLAY, the same shape as SlothPower's: C# sets boundCardPlayed in BeforeCardPlayed (ChainsOfBindingPower.cs) and the sim sets it in on_card_played, after resolution -- while the sim's before_card_played slot …
- `power/corruption/ModifyCardPlayResultPileTypeAndPosition` — *unlabelled* — The destination-pile DECISION is replaced by an after-the-fact move, and the sim has the right hook available and does not use it. C# (CorruptionPower.cs) returns (PileType.Exhaust, position) from the pile-resolution chain, so a …
- `power/crab_rage/AfterDeath` — *unlabelled* — Constants and props both checked and both right: DynamicVars.Strength is new PowerVar<StrengthPower>(6m) and DynamicVars.Block is new BlockVar(99m, ValueProp.Unpowered) (CrabRagePower.cs), matching powers.py's STRENGTH_GAIN = 6 / …
- `power/crab_rage/g1` — dormant — CrabRagePower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)); the sim omits it, so applier is None through …
- `power/crimson_mantle/g3` — dormant — CrimsonMantlePower.cs fires the damage UNCONDITIONALLY — C# calls CreatureCmd.Damage with the DamageVar's BaseValue every turn, including the first, when the value is 0; powers.py guards on if self.self_damage > 0. A 0-damage …
- `power/cruelty/g2` — dormant — CrueltyPower.cs target == base.Owner -> unmodified — Cruelty's self-exclusion is dropped by its consumer. Recorded in full on power/vulnerable's matching guard -- the sim reads Cruelty's amount with no such test, so a Cruelty …
- `power/cruelty/g4` — *unlabelled* — CrueltyPower.cs amount + base.Amount / 100m — The arithmetic is right and the TYPE is not: powers.py computes mult += cruelty.amount / 100.0 in float where C# uses decimal. 1.5 + n/100 is non-dyadic for most n (10 -> 1.6, 30 -> …
- `power/curious/g2` — dormant — CuriousPower.cs the TryModify predicate protocol — C#'s Try* hooks are a predicate chain: the listener returns bool to say 'I changed it' and writes the new value to an out-param, and Hook.ModifyEnergyCostInCombat (Hook.cs) uses …
- `power/curl_up/AfterCardPlayed` — *unlabelled* — CurlUpPower.cs is where C# gains the block (ValueProp.Unpowered), clears the latch, sets LouseProgenitor.Curled = true and calls PowerCmd.Remove. The sim has none of it: the block and the removal moved into AfterDamageReceived …
- `power/curl_up/g1` — *unlabelled* — CurlUpPower.cs !props.IsPoweredAttack() -> return — Absent. powers.py requires only target is self.owner and dealer is not None, and the sim's on_damage_received fires for every damage type (cmds.py is outside the …
- `power/curl_up/g2` — *unlabelled* — CurlUpPower.cs cardSource == null -> return — Absent for the same reason: powers.py does not require a card at all, so a dealer-carrying non-card damage source triggers Curl Up in the sim. C# needs a card because the whole …
- `power/curl_up/g3` — *unlabelled* — CurlUpPower.cs the one-card latch — if (playedCard != null && cardSource != playedCard) return keeps the latch on the FIRST qualifying card until it resolves. The sim has no latch because it never defers -- the same gap as the …
- `power/curl_up/g4` — *unlabelled* — CurlUpPower.cs ValueProp.Unpowered on the block — powers.py calls BlockCmd.apply with no props, which defaults to ValueProp.MOVE (cmds.py) and so runs the block modifier families (cmds.py). Identical omission to …
- `power/dampen/AfterApplied` — dormant — Two findings. (1) MECHANISM, the same substitution as illusion's: C#'s AfterApplied runs after PowerCmd registers the power; the sim does the work in __init__, i.e. inside power_cls(...) at cmds.py and therefore BEFORE …
- `power/dampen/AfterDeath` — dormant — C# tracks a SET of casters (Data.casters, added through the public non-override AddCaster, DampenPower.cs/73-76) and removes the power only when the LAST caster dies (casters.Remove(creature); if (casters.Count == 0) …
- `power/dampen/g3` — *unlabelled* — DampenPower.cs public void AddCaster(Creature) — A public non-override method, so the harness does not enumerate it -- recorded so a reader does not think it was skipped (the same courtesy the main report gives …
- `power/dark_embrace/AfterCardExhausted` — *unlabelled* — Two divergences. (a) THE DRAW COUNT IS HARD-CODED TO 1. DarkEmbracePower.cs draws base.Amount; powers.py is DrawCmd.draw(self.owner, 1). Dormant only because the one ported applier always passes 1 (cards/dark_embrace_card.py, …
- `power/dark_embrace/AfterSideTurnEnd` — *unlabelled* — DarkEmbracePower.cs is half of a two-phase mechanism the sim has none of: an exhaust caused by the Ethereal keyword increments an internal etherealCount instead of drawing, and this hook then draws Amount * etherealCount at the …
- `power/dark_embrace/g2` — *unlabelled* — DarkEmbracePower.cs causedByEthereal — The parameter does not exist on the sim's hook, so the branch cannot be taken. Carried as its own guard because it is the root of the AfterSideTurnEnd gap and a fix has to start here.
- `power/dark_shackles/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/dark_shackles/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/dexterity/ModifyBlockAdditive` — dormant — The sim keys the ownership test on the BLOCK TARGET where C# keys it on the CARD's owner. DexterityPower.cs: when cardSource != null the test is cardSource.Owner.Creature != base.Owner -> 0m and the target is not consulted at …
- `power/dexterity/g2` — dormant — Sign-aware power typing on a negative Dexterity application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any …
- `power/disintegration/AfterSideTurnEndLate` — dormant — Wrong slot AND lost phase, and it is the only power in this group with both. (a) PHASE: this is AfterSideTurnEndLate, the second complete pass Hook.AfterTurnEnd runs (Hook.cs), so in the game Disintegration's damage lands after …
- `power/draw_cards_next_turn/AfterSideTurnStart` — *unlabelled* — Right slot, wrong condition, and the wrongness is reachable. DrawCardsNextTurnPower.cs removes the power only when participants.Contains(base.Owner) AND base.AmountOnTurnStart != 0; powers.py expires it whenever the owner's turn …
- `power/draw_cards_next_turn/ModifyHandDraw` — dormant — The count is right (count + Amount, DrawCardsNextTurnPower.cs vs powers.py -- and correctly NOT the flat +1 that its sibling power/clarity uses; the two classes exist precisely to differ here, ClarityPower.cs). The GUARD is …
- `power/draw_cards_next_turn/g2` — *unlabelled* — Phase collapse in the sim's single post-draw slot — PHASE COLLAPSE. The sim's on_player_turn_started (player.py) is a single slot serving THREE distinct C# phases that the game runs in a fixed order: Hook.AfterPlayerTurnStart …
- `power/feeding_frenzy/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/feeding_frenzy/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/flame_barrier/AfterSideTurnEnd` — dormant — The removal condition is inverted from a side comparison into a hard-coded side. FlameBarrierPower.cs removes the power whenever base.Owner.Side != side -- i.e. at the end of the turn belonging to the side the owner is NOT on, …
- `power/flex_potion/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the …
- `power/flex_potion/g5` — dormant — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; …
- `power/free_attack/g4` — dormant — The TryModify predicate protocol — C#'s Try* hooks return bool and write to an out-param, which Hook.ModifyEnergyCostInCombat (Hook.cs) uses to build its notification list; the sim's modify_card_energy_cost (hooks.py) is a plain …
- `power/galvanic/AfterCardPlayed` — dormant — PROPS. C# deals the Galvanized damage with ValueProp.Unpowered | ValueProp.Move (GalvanicPower.cs); the sim passes DamageProps.NON_CARD_UNPOWERED, which valueprops.py defines as UNPOWERED alone -- the MOVE flag is missing. The …
- `power/galvanic/BeforeCombatStart` — dormant — Right slot -- combat.py fires on_combat_start immediately before start_turn() at :209, which turn_structure identifies as the sim's BeforeCombatStart. The divergence is an ADDED GUARD (recurring shape 8): C# afflicts EVERY Power …
- `power/gigantification/AfterAttack` — dormant — The slot is right (combat.py, immediately after the card's on_play inside the play-count loop). The GAP is the IDENTITY the latch is cleared against: C# compares ATTACK-COMMAND identity (command == internalData.commandToModify, …
- `power/hardened_shell/ModifyHpLostBeforeOstyLate` — dormant — The FORMULA is exact -- target != Owner -> amount, amount == 0 -> amount, else Math.Min(amount, Amount - damageReceivedThisTurn) (HardenedShellPower.cs) vs powers.py -- and the BeforeOsty/AfterOsty phase collapse is already …
- `power/heist/BeforeDeath` — dormant — HOOK-PHASE MISMATCH -- a BEFORE hook ported onto an AFTER hook, the recurring shape section 0 item 5 of the stream report names for thorns/curl_up/skittish/suck, now in a death-time form. C# calls Hook.BeforeDeath UNCONDITIONALLY …
- `power/hello_world/g1` — dormant — HelloWorldPower.cs base.AmountOnTurnStart >= 1 (used as BOTH the guard and the card count) — The guard is ported as self.amount < 1 (powers.py) and the count as self.amount (:2825), where C# uses base.AmountOnTurnStart for both …
- `power/hellraiser/AfterSideTurnEnd` — *unlabelled* — HellraiserPower.cs resets the per-turn infinite-auto-play counter. The sim tracks no counter (see the AfterCardDrawnEarly entry), so there is nothing to reset. Dormant for the same reason and with the same trigger; carried …
- `power/high_voltage/g1` — dormant — HighVoltagePower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner as the applier (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)); the sim calls PowerCmd.apply(self.hooks, …
- `power/high_voltage/g2` — dormant — HighVoltagePower.cs participants.Contains(base.Owner) — The sim substitutes if not self.owner.is_dead (powers.py) -- recurring gap shape 8, a guard the sim changes rather than drops. The two are not the same predicate: a corpse …
- `power/illusion/g1` — *unlabelled* — IllusionPower.cs FollowUpStateId — A public settable property with no sim analogue: it lets an applier choose which state the revived creature resumes on, defaulting to the last LOGGED state. Folded into the AfterDeath entry; …
- `power/improvement/g2` — *unlabelled* — ImprovementPower.cs PileType.Deck filtered on IsUpgradable, and :27's list.Remove making the picks DISTINCT — Also recorded for the implementation: the candidates are the RUN deck (not the combat piles), the filter is …
- `power/inferno/g4` — dormant — InfernoPower.cs CombatState.HittableEnemies — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). So the sim …
- `power/intangible/g1` — dormant — IntangiblePower.cs !CombatManager.Instance.IsInProgress -> unmodified — The sim has no combat-phase guard on any modifier hook. This is the power-level face of audit/records/seam/power_cmd.json's structural gap G6 (no …
- `power/juggernaut/AfterBlockGained` — *unlabelled* — The hook, the guards, the props and the dealer are all right -- amount <= 0 and creature == base.Owner (JuggernautPower.cs vs powers.py), and CreatureCmd.Damage(target, base.Amount, ValueProp.Unpowered, base.Owner) (:26) vs …
- `power/juggernaut/g2` — dormant — JuggernautPower.cs CombatState.HittableEnemies and the empty check — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting …
- `power/juggling/AfterCardPlayed` — dormant — The copy is rebuilt from the class rather than cloned. JugglingPower.cs is cardPlay.Card.CreateClone(), which reproduces the card's full live state; powers.py constructs type(card)() and replays card.upgrade_level upgrades onto …
- `power/mangle/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/mangle/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/nemesis/g1` — dormant — NemesisPower.cs participants.Contains(base.Owner) — Replaced by if self.owner.is_dead: return (powers.py) -- the same substitution as HighVoltage's and Territorial's, and one degree worse here, because the sim's early return also …
- `power/nostalgia/g8` — *unlabelled* — Contention with power/corruption and power/rebound on the same chain — Nostalgia is the one power in this group that uses the RIGHT hook, and that is precisely why it wins the contention the other two lose: …
- `power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath` — *unlabelled* — => creature != base.Owner, i.e. the Test Subject's corpse stays in combat. The sim has the hook (hooks.py, consumed at cmds.py) and this power does not use it -- AdaptablePower on the same creature prevents the death instead …
- `power/painful_stabs/AfterAttack` — *unlabelled* — A site of the closed `power/_killing_blow_guard` family that was split out into its own mechanism. `AfterAttack` on the victim is skipped on the killing blow; re-derive whether this power's counter still diverges there.
- `power/panache/AfterCardPlayed` — dormant — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). The sim therefore aims at creatures the game considers …
- `power/plow/AfterDamageReceived` — dormant — Right hook and right slot; the threshold matches exactly (target != base.Owner || result.UnblockedDamage <= 0 || target.CurrentHp > base.Amount -> return, PlowPower.cs, vs powers.py). Three divergences. (1) The sim ADDS …
- `power/poison/AfterSideTurnStart` — dormant — Three divergences, all DORMANT for one shared reason: nothing in the sim applies Poison at all. An executed grep for PoisonPower outside powers.py and the package re-exports returns no applier -- no card, relic, event, monster or …
- `power/rampart/g3` — dormant — RampartPower.cs base.CombatState.Enemies.Where(c => c.Monster is TurretOperator) — powers.py adds and not enemy.is_gone (recurring gap shape 8, a guard the sim ADDS). C#'s CombatState.Enemies is the raw participant list and a …
- `power/ravenous/AfterDeath` — *unlabelled* — The guards are exact -- target != base.Owner && target.Side == base.Owner.Side && !base.Owner.IsDead (RavenousPower.cs) maps line-for-line to powers.py -- and the effect order matches (stun the owner, then grant Strength). Two …
- `power/ravenous/g1` — dormant — RavenousPower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)); the sim omits it, so applier is None through …
- `power/rebound/AfterModifyingCardPlayResultPileOrPosition` — *unlabelled* — C# consumes the stack from this dedicated after-hook (ReboundPower.cs -> PowerCmd.Decrement), which Hook.ModifyCardPlayResultPileTypeAndPosition fires over exactly the listeners that changed the value (Hook.cs, one of …
- `power/rebound/ModifyCardPlayResultPileTypeAndPosition` — *unlabelled* — The destination-pile DECISION is replaced by an after-the-fact move. The sim has the matching hook -- hooks.modify_card_play_result_pile (hooks.py), dispatched at combat.py -- and this power does not use it, reaching into the …
- `power/reptile_trinket/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/reptile_trinket/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/retain_hand/AfterSideTurnEnd` — *unlabelled* — A DELIBERATE SLOT SHIFT that is observationally correct in the normal case and LIVE through turn_structure's G3 in the extra-turn case. C# decrements at the PLAYER side's Hook.AfterTurnEnd (CombatManager.cs), i.e. after …
- `power/ringing/AfterCardEnteredCombat` — dormant — The owner filter is dropped, which is harmless in single-player, but the SITE is not: C# afflicts from AfterCardEnteredCombat (RingingPower.cs) and the sim's on_card_entered_combat (hooks.py) is fired only where the sim happens …
- `power/ringing/ShouldPlay` — *unlabelled* — HISTORY vs FLAG. C# answers 'has the owner played a card this turn' by querying CombatManager.History.CardPlaysStarted for entries that HappenedThisTurn; the sim keeps a boolean set from on_card_played. The two differ during a …
- `power/rolling_boulder/g2` — dormant — RollingBoulderPower.cs CombatState.HittableEnemies (TestMode arm) — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses CombatState.HittableEnemies, which additionally consults …
- `power/rupture/AfterCardPlayed` — *unlabelled* — The payout half of the deferral described on the BeforeCardPlayed entry: RupturePower.cs removes the card's accumulator and applies the summed Strength once. Absent from the sim. Carried separately because the harness requires a …
- `power/rupture/g3` — *unlabelled* — RupturePower.cs CurrentSide == Owner.Side — Absent -- the core of the AfterDamageReceived gap. Carried as its own guard because it is a one-line omission that survives any fix to the deferral, and because it is the single …
- `power/sandpit/AfterRemoved` — dormant — The EFFECT is right and the MECHANISM is not. C#'s AfterRemoved (SandpitPower.cs) returns early on oldOwner.IsDead || base.Target.IsDead, hides the affected creatures, and CreatureCmd.Kill(..., force: true) every one that …
- `power/setup_strike/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/setup_strike/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/shackling_potion/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/shackling_potion/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/shrink/AfterDeath` — dormant — The wasRemovalPrevented guard is missing. ShrinkPower.cs removes Shrink only when !wasRemovalPrevented && creature == base.Applier; the sim tests only creature is self.applier (powers.py). A prevented removal (a death whose …
- `power/shrink/AfterSideTurnEnd` — dormant — Two divergences in one hook. (a) The !IsInfinite guard (ShrinkPower.cs, i.e. Amount >= 0) is spelled self.amount > 0 on both sim legs (powers.py); those agree only because Amount == 0 is unreachable (ShouldRemoveDueToAmount …
- `power/shrink/AllowNegative` — dormant — ShrinkPower.cs declares AllowNegative => true; the sim's ShrinkPower never sets allow_negative, so it inherits False from Power (powers.py). That changes ShouldRemoveDueToAmount (PowerModel.cs): C# removes an AllowNegative power …
- `power/shrink/ModifyDamageMultiplicative` — *unlabelled* — NON-DYADIC FACTOR. C# computes (100m - DamageDecrease) / 100m in DECIMAL from the DynamicVar (ShrinkPower.cs, DamageDecrease = 30m at :18/:44) = exactly 0.7m; the sim returns the float literal 0.7 (powers.py), which is not a …
- `power/skittish/AfterAttack` — *unlabelled* — C#'s hook is AfterAttack, which fires ONCE per AttackCommand after every hit has landed (SkittishPower.cs searches command.Results for a DamageResult whose Receiver is the owner); the sim uses on_damage_received, which fires PER …
- `power/slippery/ModifyHpLostAfterOsty` — dormant — The formula is exact: target != base.Owner -> amount, amount < 1m -> amount, else 1m (SlipperyPower.cs) vs powers.py. The BeforeOsty/AfterOsty phase collapse is already resolved as faithful by damage_pipeline (Osty redirection is …
- `power/sloth/BeforeCardPlayed` — dormant — WRONG SIDE OF THE PLAY. C# increments the counter in BeforeCardPlayed (SlothPower.cs), i.e. before the card resolves; the sim increments in on_card_played, after. The sim HAS the right slot -- before_card_played (combat.py), …
- `power/slow/ModifyDamageMultiplicative` — dormant — The factor matches (1m + 0.1m * SlowAmount at SlowPower.cs vs 1.0 + 0.1 * self._cards_this_turn at powers.py) and target != base.Owner -> 1m matches, but the POWERED test does not: C# is props.IsPoweredAttack() (SlowPower.cs) and …
- `power/smoggy/AfterCardEnteredCombat` — *unlabelled* — Same pile-limbo shape as power/ringing's matching entry: the sim walks getattr(self.owner, 'all_cards', ()), and PlayerCombatState.all_cards (player.py) is hand + draw + discard + exhaust with NO Play pile, where C#'s …
- `power/speed_potion/g4` — dormant — TemporaryDexterityPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the …
- `power/speed_potion/g5` — dormant — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; …
- `power/speed_potion/g8` — dormant — The Dexterity leg's own observable consequence, as distinct from the family's slot verdict — RE-DERIVED 2026-07-26 (review fix pass). Stated separately so the AfterSideTurnEnd verdict above is not read as more proven than it is, …
- `power/strength/g3` — dormant — Sign-aware power typing on a negative Strength application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any …
- `power/suck/g2` — *unlabelled* — Counting GROUPS with unblocked damage, not individual results — C#'s num counts outer lists (per-hit result groups) in which ANY result had unblocked damage, so a single AoE hit that connects with three creatures counts 1. The …
- `power/suck/AfterAttack` — *unlabelled* — The other orphaned site of the closed `power/_killing_blow_guard` family, same shape as `power/painful_stabs/AfterAttack` above.
- `power/surprise/AfterDeath` — dormant — Right hook and the right two spawns (CreatureCmd.Add<SneakyGremlin> then <FatGremlin>, SurprisePower.cs, vs powers.py in the same order, which matters because it fixes the enemy-list indices). The gap is the THIEVERY TRANSFER. C# …
- `power/surrounded/AfterDeath` — dormant — The logic matches SurroundedPower.cs -- skip when the dead creature is on the owner's own side, then, if every remaining hittable enemy carries the SAME marker power, re-face on hittableEnemies[0] -- but the sim reads [e for e in …
- `power/surrounded/ModifyDamageMultiplicative` — dormant — The arithmetic and the facing logic are exact -- dealer == null -> 1m, target != base.Owner -> 1m, then 1.5x only if the dealer holds the marker power OPPOSITE the facing (SurroundedPower.cs vs powers.py), and 1.5 is dyadic so …
- `power/surrounded/g1` — dormant — SurroundedPower.cs !wasRemovalPrevented — Absent from powers.py, which tests only the side. C# skips the re-facing entirely when a death's REMOVAL was prevented (the creature is still there, so the board did not change); the sim …
- `power/swipe/BeforeDeath` — dormant — HOOK SLOT: C# is BeforeDeath, fired at CreatureCmd.cs before Hook.ShouldDie and therefore before any death prevention; the sim uses hooks.on_death, fired at cmds.py only on the branch where should_die returned True. Two …
- `power/tangled/AfterApplied` — *unlabelled* — The sim adds a guard C# does not have, and it changes the outcome. TangledPower.cs afflicts EVERY Attack card with Entangled unconditionally -- there is no Affliction == null test, unlike its own AfterCardEnteredCombat at :34 and …
- `power/tangled/TryModifyEnergyCostInCombat` — *unlabelled* — This is hook_dispatch gap G3's own primary witness: Tangled is the EARLY-phase cost modifier and FreeAttackPower is the Late one, and the sim has a single unphased pass, so the result depends on the order the two powers happened …
- `power/tender/AfterCardPlayed` — dormant — The applier is dropped. TenderPower.cs applies Strength and Dexterity -1 with applier: base.Applier -- the creature that applied Tender -- and silent: true; powers.py calls PowerCmd.apply with no applier at all. DORMANT but with …
- `power/territorial/g1` — dormant — TerritorialPower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner as the applier (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)); the sim calls PowerCmd.apply(self.hooks, …
- `power/territorial/g2` — *unlabelled* — TerritorialPower.cs participants.Contains(base.Owner) — Same substitution as HighVoltagePower's: the sim tests not self.owner.is_dead (powers.py) where C# tests side participation, which a retained corpse still satisfies. …
- `power/the_bomb/g2` — dormant — TheBombPower.cs / :56 CombatState.HittableEnemies — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs), so …
- `power/vigor/ModifyDamageAdditive` — dormant — The sim keeps only the FIRST of C#'s four guards. C# (VigorPower.cs) tests, in order: base.Owner != dealer (present, powers.py), !props.IsPoweredAttack() (present structurally -- cmds.py only runs the additive family for powered …
- `power/vital_spark/AfterPowerAmountChanged` — dormant — C# re-syncs every Tainted affliction's Amount to the power's new Amount from AfterPowerAmountChanged with a power != this guard (VitalSparkPower.cs), so it fires on ANY amount change -- a stack, a decrement, or an …
- `power/vital_spark/AfterRemoved` — dormant — C#'s AfterRemoved clears every Tainted affliction on EVERY removal path (VitalSparkPower.cs, guarded by oldOwner.CombatState == null); the sim hangs the same sweep on on_death filtered to the owner (powers.py) and then calls …
- `power/vital_spark/BeforeCombatStart` — *unlabelled* — Identical shape to GalvanicPower's, one card type over (Skills rather than Powers, Tainted rather than Galvanized): the sim adds a card.affliction is None test that VitalSparkPower.cs does not have, where C#'s CardCmd.Afflict …
- `power/vulnerable/ModifyDamageMultiplicative` — dormant — The base multiplier and both ported modifiers are right, but the value is computed in FLOAT where C# uses DECIMAL, which puts this hook inside hook_dispatch gap G9's blast radius. C# reads DamageIncrease = 1.5m from the …
- `power/vulnerable/g3` — dormant — CrueltyPower.cs target == base.Owner -> unmodified — Cruelty's own self-exclusion is dropped. C# skips the Cruelty bonus when the Vulnerable target IS the Cruelty holder; powers.py reads dealer.powers.get('cruelty') with no such …
- `power/vulnerable/g4` — dormant — VulnerablePower.cs DebilitatePower leg — DebilitatePower is not ported (grep -c DebilitatePower sts2_rl/powers.py returns 0), so the third link of C#'s modifier chain has no sim counterpart. Per binding rule 1 an unported C# side …
- `power/weak/ModifyDamageMultiplicative` — dormant — The sim returns the bare literal 0.75 and has no modifier chain at all, where WeakPower.cs threads DamageDecrease = 0.75m through PaperKrane (the TARGET's relic, -0.15m) and then DebilitatePower. Neither is ported -- ls …
- `power/withering_presence/AfterCardPlayed` — dormant — The mechanism is right -- count the target player's card plays down from 6, add a Wither to HAND at 0, reset to 6 -- and the Wither's upgrade matching is preserved (aeonglass.MatchWitherToUpgradeCount(wither) at …

## 3B. `card` — 41 single-site mechanisms

**Closed 2026-07-31 (tier-2 campaign, Task 30): the playable-Status /
`CanBeGeneratedInCombat` cluster, 10 entries across 6 cards — AND ITS RECORDED
DORMANCY WAS WRONG.** All six C# files were read line-by-line: none overrides
`CanBeGeneratedByModifiers` or `CanonicalKeywords`, so the sim's
`is_playable=False` AND `can_be_generated_by_modifiers=False` were BOTH wrong
and `can_be_generated_in_combat=False` was missing — two mismatched flags per
card. **The liveness correction matters more than the fix:** every entry's
dormancy argument checked only `pool_card_ids` and `curse_pool_ids`, but a
THIRD consumer exists — `transform_options_in_combat`'s STATUS branch, reached
by ported Entropy. Pre-fix it genuinely leaked all four bad cards as transform
options for every reachable Status card, including `frantic_escape`, which The
Insatiable really does put in piles (`test_hive.py::TestTheInsatiable`).
Reproduced by execution independently by the implementer and the task reviewer.
So this cluster was recorded DORMANT while being reachable. `card/neows_fury/g1`
and `/OnPlay` do NOT share this root and stay open.

The card tier's families — `card/_unplayable_cost`, `card/_printed_vars` and
`card/_is_dead_early_return` — are in Tier 2. `OnPlay` entries are the card's
own effect diverging; `ctor` and `CanonicalVars` entries that are not in a
family are one-off value-model divergences.

- `card/anointed/g2` — dormant — cards are moved to the hand with CardPileCmd.Add(cards, PileType.Hand) (Anointed.cs) vs direct list mutation — The sim pops each card out of player.draw_pile and appends to player.hand in place (colorless_skills.py) instead of …
- `card/apotheosis/g1` — dormant — the allCard != this self-exclusion, and whether the two AllCards sets are the same set (Apotheosis.cs) — C# PlayerCombatState.AllCards is AllPiles.SelectMany(p => p.Cards) (PlayerCombatState.cs) over Hand, Draw, Discard, Exhaust …
- `card/beat_down/g2` — dormant — target selection for AnyEnemy attacks: C# rolls Rng.CombatTargets.NextItem(CombatState.HittableEnemies) in BeatDown itself and passes it to AutoPlay; the sim lets auto_play_card roll (BeatDown.cs) — The stream is right on both …
- `card/breakthrough/g1` — dormant — the enemy loop skips on enemy.is_dead, not enemy.is_gone (breakthrough.py) — Every other AoE card in the sim filters on not e.is_gone (conflagration, shockwave, omnislice, sword_boomerang, rip_and_tear -- see py …
- `card/brightest_flame/g1` — dormant — CROSS-RECORD DISAGREEMENT (rule 3): CreatureCmd.LoseMaxHp(..., isFromCard: true) is seam gap G6, which labels itself DORMANT; this card makes it LIVE — The seam's VERDICT (gap) is not disputed and is not re-verdicted here -- only …
- `card/conflagration/OnPlay` — dormant — Damage per hit, hit count, target set and the OUTER loop order are all faithful: DamageCmd.Attack(2).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState) (Conflagration.cs) runs for (i = 0; i < attackCount; i++) with …
- `card/crimson_mantle/g1` — dormant — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (CrimsonMantle.cs vs crimson_mantle.py) — PowerCmd.Apply<T> returns null in three documented cases (PowerCmd.cs): combat is …
- `card/debt/HasTurnEndInHandEffect` — *unlabelled* — public override bool HasTurnEndInHandEffect => true (Debt.cs) has no counterpart: the sim leaves the class default False (cards/base.py), so the end-of-turn hand pass never even asks Debt for an effect. This is the flag half of …
- `card/disintegration/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (Disintegration.cs) has no counterpart: the sim leaves can_be_generated_in_combat at its True default and instead turns OFF a DIFFERENT flag, can_be_generated_by_modifiers, …
- `card/disintegration/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); Disintegration.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the same …
- `card/dramatic_entrance/OnPlay` — dormant — The damage, the target set and the single hit are all faithful: DamageCmd.Attack(11).FromCard(this).TargetingAllOpponents(CombatState) (DramaticEntrance.cs) hits every living opponent once, and the sim's framework routing calls …
- `card/enlightenment/g1` — dormant — reduceOnly is evaluated LAZILY at cost-calculation time, so C# registers the modifier on EVERY hand card including those already at cost 0 or 1; the sim continues past them (Enlightenment.cs vs event_cards.py) — …
- `card/expect_a_fight/g1` — dormant — the sim skips the gain entirely when there are no Attacks in hand (if attacks > 0, expect_a_fight.py); C# calls GainEnergy(0) — PlayerCmd.GainEnergy(0, ...) (ExpectAFight.cs) adds nothing but still runs the engine's gain path; …
- `card/exterminate/OnPlay` — dormant — Damage per hit, hit count, target set and the hits-outer/enemies-inner loop order are all faithful against DamageCmd.Attack(3).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState) (Exterminate.cs) -- AttackCommand …
- `card/frantic_escape/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (FranticEscape.cs) has no counterpart: the sim leaves can_be_generated_in_combat at its True default and instead turns off can_be_generated_by_modifiers, which FranticEscape.cs …
- `card/havoc/g2` — dormant — forceExhaust: true is reproduced by appending to the exhaust pile directly (havoc.py) — C# sets item.ExhaustOnNextPlay = forceExhaust (CardPileCmd.cs) and lets the play pipeline route the card to the exhaust pile, which means the …
- `card/howl_from_beyond/OnPlay` — dormant — The damage and the single hit per enemy are faithful against DamageCmd.Attack(16).FromCard(this).TargetingAllOpponents(CombatState) (HowlFromBeyond.cs), and leaving handles_own_routing False is correct for a one-hit AoE -- the …
- `card/inferno/g1` — dormant — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (Inferno.cs vs inferno.py) — Identical to card/crimson_mantle's guard and carrying the same verdict (rule 3): …
- `card/lantern_key/ModifyNextEvent` — dormant — if (2 != Owner.RunState.CurrentActIndex) return currentEvent; return ModelDb.Event<WarHistorianRepy>(); (LanternKey.cs) redirects the next act-3 event to War Historian Repy -- the payoff the Lantern Key quest exists for. The …
- `card/mad_science/GainsBlock` — dormant — public override bool GainsBlock => TinkerTimeType == CardType.Skill (MadScience.cs) is TYPE-DEPENDENT, and the sim never sets gains_block at all -- not in the class body and not in configure (mad_science.py, which sets card_type, …
- `card/mind_rot/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (MindRot.cs) has no counterpart; the sim leaves can_be_generated_in_combat True and turns off a different flag that MindRot.cs does not override. Identical to …
- `card/mind_rot/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); MindRot.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the same shape as …
- `card/neows_fury/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (NeowsFury.cs) has no can_be_generated_in_combat = False counterpart; the sim's comment says the ANCIENT rarity already keeps it out of pool_card_ids. That is true today, so …
- `card/neows_fury/OnPlay` — dormant — Attack first, then the hand-size-capped selection: Math.Min(Cards.IntValue, CardPile.MaxCardsInHand - Hand.Cards.Count) (NeowsFury.cs) == min(self._cards, PlayerCombatState.MAX_HAND_SIZE - len(ctx.player.hand)), with both …
- `card/neows_fury/g1` — dormant — the chosen cards are moved with CardPileCmd.Add(list, PileType.Hand) in C# (NeowsFury.cs) and by direct list mutation in the sim (neows_fury.py) — The sim pops the chosen cards out of player.discard_pile and appends them to …
- `card/omnislice/g1` — dormant — the sim returns early when nothing got through (if dealt <= 0: return, colorless_attacks.py); C# proceeds whenever the DamageResult is non-null (Omnislice.cs) — C# proceeds whenever the DamageResult is non-null (Omnislice.cs) and …
- `card/pacts_end/OnPlay` — dormant — The gate and the damage are faithful: CanDealDamage is CardPile.GetCards(Owner, PileType.Exhaust).Count() >= Cards.IntValue (PactsEnd.cs) == if len(ctx.player.exhaust_pile) < self._required_exhausted: return, and the whole play …
- `card/pillage/g1` — dormant — the sim identifies the drawn card as player.hand[-1] (pillage.py) where C# uses the value the single-card Draw overload returns — C#'s single-card CardPileCmd.Draw overload RETURNS the card it drew (Pillage.cs) and the type test …
- `card/primal_force/OnPlay` — dormant — The candidate set, the per-card upgrade and the index-preserving replacement are all faithful. C# selects Hand.Cards.Where(c => c != null && c.IsTransformable && c.Type == CardType.Attack) (PrimalForce.cs) and the sim's if …
- `card/purity/OnPlay` — dormant — The candidate set and the effect are faithful: CardSelectCmd.FromHand(..., filter: null, source: this) over the whole hand then CardCmd.Exhaust on each (Purity.cs) == CardSelectCmd.from_hand(ctx.hooks, ctx.player, 'exhaust', …
- `card/rend/g1` — dormant — the ITemporaryPower exclusion is approximated by a single class (colorless_attacks.py) — C#'s ShouldCountPower is power.TypeForCurrentAmount == PowerType.Debuff && !(power is ITemporaryPower) (Rend.cs). The sim reproduces the …
- `card/sloth/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false has no counterpart: the sim's shared _ChoosableCurse base leaves can_be_generated_in_combat True and instead turns off can_be_generated_by_modifiers (knowledge_curses.py), …
- `card/sloth/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); Sloth.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status. Same mechanism and …
- `card/stomp/OnPlay` — dormant — The damage, the single hit per enemy and the target set are faithful against DamageCmd.Attack(12).FromCard(this).TargetingAllOpponents(CombatState) (Stomp.cs), and leaving handles_own_routing False is correct for a one-hit AoE -- …
- `card/the_bomb/g1` — dormant — C# dereferences the Apply result WITHOUT a null check; the sim re-fetches by id and skips on None (TheBomb.cs vs colorless_skills.py) — This is the INVERSE of card/crimson_mantle's and card/inferno's ?. finding: those two use the …
- `card/thunderclap/OnPlay` — dormant — The TWO-PASS structure is faithful and is the point of the card: C# resolves the whole attack first (DamageCmd.Attack(4).FromCard(this).TargetingAllOpponents(CombatState), Thunderclap.cs) and only then applies Vulnerable to …
- `card/thunderclap/g1` — dormant — the sim continues rather than breaking when an enemy is gone in the damage pass, and re-checks ctx.player.is_dead between the passes (thunderclap.py) — Two behaviours are bundled here and only one is the source's. C#'s …
- `card/toric_toughness/g1` — dormant — C# skips SetBlock when Apply returns NULL via ?.; the sim re-fetches by id and skips on None (ToricToughness.cs vs event_cards.py) — Same mechanism and same verdict as card/crimson_mantle's and card/inferno's guards (rule 3): …
- `card/waste_away/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (WasteAway.cs) has no counterpart; the sim leaves can_be_generated_in_combat True and turns off a different flag that WasteAway.cs does not override (C# leaves it => true, …
- `card/waste_away/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); WasteAway.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the shape …
- `card/whirlwind/OnPlay` — dormant — The X-value plumbing, the hit count and the hits-outer/enemies-inner loop order are all faithful: WithHitCount(ResolveEnergyXValue()) on TargetingAllOpponents(CombatState) (Whirlwind.cs) == for _ in range(self.captured_x) with a …

## 3C. `event` — 12 single-site mechanisms

**2026-07-31 (tier-2 campaign, Task 32) — this round FOUND a live gap here that
was never in the queue, fixed two thirds of it, and left the third recorded
open.** C# calls `Hook.ModifyRewards` from `RewardsSet.GenerateWithoutOffering`
(`RewardsSet.cs:136`), which EVERY `RewardsSet` passes through. The sim
dispatches per construction site instead, and three sites were missing it:
`brain_leech.py::_rip` and `trial.py::_nondescript_guilty` (both **FIXED** —
Driftwood's reroll now reaches those screens) and
`events/base.py::Event.offer_card_reward`, sole caller
`the_future_of_potions.py` (**STILL OPEN**, `event/the_future_of_potions/g15`):
that one is not a missing call but a take-or-skip protocol with no reroll
surface, so it needs new capability. All three are LIVE — the events and
Driftwood are ported and reachable.

The fix is per-site because `driver.py`'s `_offer_rewards` has three other
callers that already dispatch at construction time (`rewards.py:698,761`,
`run.py:1419`, `glass_eye.py:78`), so a central call would double-dispatch and
duplicate AmethystAubergine/BlackStar/LavaRock gold and relics. **That leaves
the sim structurally unlike C#'s single choke point, and the next event ported
this way can reintroduce the same bug** — consolidating the construction-time
dispatches onto one choke point is the real fix and wants its own task.

**Separate and larger, found in the same pass:** `run.reward_offer_selector` is
never wired by `driver.py` (set only in test files, confirmed by repo-wide
grep), so take-or-skip reward screens AUTO-ACCEPT in real play. Pre-existing,
out of Task 32's scope, recorded on `event/the_future_of_potions/g15` for want
of a better home, and worth more than the reroll flag it was found beside.

The event tier's `EV-n` mechanisms are closed except `event/EV-3`, which is in
Tier 1. These are the per-event findings that no `EV-n` covers.

- `event/EV-11` — dormant — EV-11: BARGAIN_BIN's Common pull (WelcomeToWongos.cs) and GenerateInitialOptions' Rare pull (:80) calls run.pull_relic_from_front (run.py), which scans the merged bag for the first relic of the asked rarity passing the filter …
- `event/crystal_sphere/CalculateVars` — *unlabelled* — Unreachable in the sim only because the whole event is stubbed off -- see the DEFERRED-PORT guard, which carries this unit's verdict.
- `event/crystal_sphere/IsAllowed` — *unlabelled* — See the DEFERRED-PORT guard. The gate is satisfiable with ported content -- gold >= 100 in act 2+ is an ordinary run state -- so this is not an unreachability waiver.
- `event/crystal_sphere/g1` — dormant — DEFERRED PORT: the whole event is a stub. CrystalSphere.cs's payout is the CrystalSphereMinigame (Events/Custom/CrystalSphereEvent/), driven 3 times for UNCOVER_FUTURE (after LoseGold(50 + NextInt(1,50), GoldLossType.Spent)) and …
- `event/dense_vegetation/CalculateVars` — *unlabelled* — Two problems. (1) The roll is on the shared run RNG, not the per-event Rng -- see guard EV-3. (2) The second var is not ported at all: DenseVegetation.cs sets Heal.BaseValue = HealRestSiteOption.GetHealAmount(Owner), which CALLS …
- `event/hungry_for_mushrooms/g3` — dormant — BigMushroom's +20 Max HP pickup effect is implemented on the EVENT, not on the relic. BigMushroom.cs AfterObtained calls CreatureCmd.GainMaxHp(MaxHpVar 20) — relics/big_mushroom.py has NO after_obtained override -- only …
- `event/neow/g8` — dormant — the RUN MODIFIERS branch is not ported. Neow.cs is a whole second mode: when RunState.Modifiers is non-empty the relic offer is REPLACED by one option per modifier that returns a GenerateNeowOption delegate, presented one at a …
- `event/ranwid_the_elder/g10` — dormant — BR-relic_trader (blast radius): the grab-bag-runs-dry state. RanwidTheElder.cs and :131 call RelicFactory.PullNextRelicFromFront(base.Owner).ToMutable() with no null check at all, so an empty bag is an NRE in the source — ALREADY …
- `event/relic_trader/g5` — dormant — GenerateInitialOptions gates each option on OwnedRelics.Count ALONE (RelicTrader.cs), and Trade then indexes NewRelics at the same position (RelicTrader.cs) — events/relic_trader.py gates on min(len(self._owned), len(self._new)). …
- `event/vakuu/g5` — dormant — UNIT GAP (dormant): Distinguished Cape's -9 Max HP is implemented on the EVENT OPTION instead of on the relic. DistinguishedCape.cs's AfterObtained() runs CreatureCmd.LoseMaxHp(..., DynamicVars.HpLoss = 9, isFromCard: false) and …
- `event/war_historian_repy/g2` — *unlabelled* — DEFERRED PORT, leg 2 -- THE BODY. Nothing below GenerateInitialOptions is ported: events/war_historian_repy.py returns []. Unported: the two initial options UNLOCK_CAGE / UNLOCK_CHEST (WarHistorianRepy.cs); the second-reward page …
- `event/welcome_to_wongos/g8` — dormant — CheckObtainWongoBadge (WelcomeToWongos.cs) is not ported: the sim never grants WongoCustomerAppreciationBadge, and it tracks points on an ad-hoc attribute instead of run state — The badge is awarded when …

## 3E. `relic` — 203 single-site mechanisms

- `relic/_auto_keep` — **LIVE** — `relic/kifuda/g2` + `/AfterObtained`. `Kifuda.cs:26` builds `new CardSelectorPrefs(EnchantSelectionPrompt, 0, Cards.IntValue) { Cancelable = false, RequireManualConfirmation = true }` — MinSelect 0, MaxSelect 3, so the player may confirm having enchanted fewer cards than are eligible; the sim's driver runs a non-skippable always-fill-count selection loop. Promoted from DORMANT in round 11 once `G1` (`after_obtained`) was implemented, which discharged its own stated precondition for dormancy. **Carried in from main at the round-12 merge — it was never in this file before.**


**Closed 2026-07-31 (tier-2 campaign, Task 30): `relic/crossbow/g3`**, folded in
with `potion/_filter_for_combat_event_rarity` — it was the same root. Crossbow's
Attack list runs through `pool_card_ids`, which implemented three of
`CardFactory.FilterForCombat`'s four clauses and omitted the Event-rarity one;
`cards/pool.py:130` now excludes `CardRarity.EVENT` alongside `BASIC` and
`ANCIENT` (`CardFactory.cs:159-162`). Its executed dormancy still holds (no
Event-rarity card is in `IRONCLAD_POOL`), but the sim no longer relies on that
to be correct.

The relic tier's recurring families are written out above: the four that are
still open are in [Tier 1C](#1c-relic-tier-families) (`relic/_is_allowed`,
`relic/_stub`, `relic/_reward_late_pass`, `relic/_combat_reset`), and the rest
resolve to a mechanism a seam record already owns (`hook_dispatch/G3`,
`damage_pipeline/G3`, `turn_structure/G13`). Everything below stands alone: one
relic, one finding.

This is by far the largest single-site block in the queue, and the honest
reading is that **the relic tier's gap density is genuinely higher than the
other content tiers'.** Relics reach into every subsystem, and the sim's
out-of-combat surfaces are where the port is thinnest.

- `relic/anchor/g3` — dormant — C# grants Anchor's block at step 3 (Hook.BeforeCombatStart, before StartTurn); the sim grants it at step 14's equivalent (the AfterBlockCleared loop, well inside turn-1 setup). Any effect that runs BETWEEN those two points and …
- `relic/archaic_tooth/AfterObtained` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The transform itself is right -- first deck card whose id is a TranscendenceUpgrades key (ArchaicTooth.cs vs archaic_tooth.py), replaced via run.transform_card(into=) -- but the …
- `relic/archaic_tooth/g1` — dormant — C# grants exactly ONE upgrade level regardless of how many the original had; the sim grants as many as the original had. They agree only while upgrade_level is 0 or 1. REACHABILITY (DORMANT): the sim's Card.max_upgrade_level …
- `relic/archaic_tooth/g2` — dormant — C# clones the enchantment (`(EnchantmentModel)starterCard.Enchantment.MutableClone`) and enchants unconditionally; the sim detaches the original object, then re-attaches it ONLY if `enchantment.can_enchant(transformed)` -- so …
- `relic/astrolabe/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. The selection and the transform are faithful -- 3 cards (CardsVar(3), Astrolabe.cs vs astrolabe.py), chosen from the deck's transformable cards, each replaced and then upgraded, on the Niche …
- `relic/bag_of_marbles/BeforeSideTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect is right -- 1 Vulnerable (PowerVar<VulnerablePower>(1m), BagOfMarbles.cs) to every enemy on turn 1, applier = the player -- but the hook slot and the enemy set are both …
- `relic/bag_of_marbles/g1` — dormant — MECHANISM: audit/records/seam/turn_structure.json puts Hook.BeforeSideTurnStart at step 9 -- before any block is cleared and before the enemies re-roll their moves -- and Hook.AfterSideTurnStart at step 23, after the hand draw. …
- `relic/bag_of_marbles/g2` — dormant — C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHitting(CombatState, this)` (Creature.cs). The sim's Relic.living_enemies (relics/base.py) filters on `not e.is_gone` …
- `relic/bag_of_preparation/g1` — dormant — C# collects which listeners changed the draw count and fires Hook.AfterModifyingHandDraw over them; the sim's modify_hand_draw returns a bare int with no companion event (hooks.py). This is the missing-AfterModifying-companion …
- `relic/belt_buckle/AfterObtained` — dormant — BeltBuckle.cs applies the Dexterity immediately if the relic is picked up DURING a combat with no potions held. The sim's port defines only on_combat_start and on_potion_used, so a Belt Buckle obtained mid-combat grants nothing …
- `relic/belt_buckle/AfterPotionDiscarded` — dormant — The mirror of AfterPotionProcured: BeltBuckle.cs RE-APPLIES the Dexterity when discarding leaves the player potionless mid-combat. The sim implements on_potion_used but not a discard analogue, so the two ways of emptying the belt …
- `relic/bing_bong/AfterCardChangedPiles` — *unlabelled* — Rollup of guard G1 per binding rule 4. The core is right -- the deck-pile filter, the anti-recursion skip set, and the bottom-of-deck placement all match -- but C#'s `clonedBy == null` clause has no sim counterpart.
- `relic/bone_tea/AfterSideTurnStart` — *unlabelled* — Rollup of guard G1 per binding rule 4. The slot, the guards and the charge accounting are all right -- post-draw (turn_structure step 23, executed via the turn-order probe), `IsUsedUp` / `participants` / `TurnNumber > 1` all …
- `relic/booming_conch/AfterSideTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The energy amount and the Elite/turn-1 conditions are right (executed: Elite turn-1 energy is 4 = base 3 + 1), but the hook slot is wrong and the grant bypasses the energy-gain …
- `relic/booming_conch/g1` — dormant — The relic's own two halves end up on opposite sides of the draw from the source's arrangement: C# adds the cards (ModifyHandDraw, step 20), draws, and only then grants the energy (step 23); the sim grants the energy at step ~19 …
- `relic/booming_conch/g2` — dormant — MECHANISM: PlayerCmd.GainEnergy (PlayerCmd.cs) computes `finalAmount = Hook.ModifyEnergyGain(...)`, awaits Hook.AfterModifyingEnergyGain over the modifiers, and grants only `if (finalAmount > 0)`. The sim HAS that chain …
- `relic/brilliant_scarf/TryModifyEnergyCostInCombatLate` — dormant — Rollup of guards G2 and G3 per binding rule 4. The trigger arithmetic matches -- cost 0 when CardsPlayedThisTurn == CardsVar(5) - 1, i.e. the fifth card of the turn -- but the sim drops the Late PHASE (G2) and both of …
- `relic/brilliant_scarf/g3` — dormant — C# refuses to modify a cost unless the card's owner is the relic's owner AND the card is currently in the Hand or Play pile; brilliant_scarf.py checks only the counter. The pile clause is the substantive one: it stops the relic …
- `relic/burning_sticks/AfterCardExhausted` — *unlabelled* — Rollup of guards G1 and G3 per binding rule 4. The trigger logic matches (first Skill exhausted, clone to hand), but the relic fires in the first combat of a run only (G1) and the copy it makes is a fresh card by id rather than …
- `relic/byrdpip/AfterObtained` — *unlabelled* — Rollup of guards G1 and G3 per binding rule 4. The deck half of the Byrdonis Egg -> Byrd Swoop transform is faithful; the combat-pile half (G1) and the mid-combat SummonPet call (G3) are dropped.
- `relic/byrdpip/BeforeCombatStart` — *unlabelled* — Byrdpip.cs summons the pet at the start of EVERY combat. The port has no on_combat_start. Carries guard G3's verdict; see G3 for why the omission is observationally inert today.
- `relic/byrdpip/HasUponPickupEffect` — dormant — Byrdpip.cs declares `HasUponPickupEffect => true` and the sim's Relic base has the exact field for it (relics/base.py), which fourteen other ports set. Byrdpip leaves it at the False default. DORMANT (executed -- `py …
- `relic/byrdpip/SpawnsPets` — *unlabelled* — Byrdpip.cs declares `SpawnsPets => true`; relics/base.py has the field and the port leaves it False. Same dormancy and same executed evidence as HasUponPickupEffect -- both feed only is_tradable, which EVENT rarity already …
- `relic/byrdpip/g1` — dormant — Byrdpip.cs collects every ByrdonisEgg from the Deck pile and, `if (CombatManager.Instance.IsInProgress)`, ALSO from `Owner.PlayerCombatState.AllCards` -- i.e. a Byrdonis Egg sitting in the draw/hand/discard/exhaust pile of a …
- `relic/captains_wheel/AfterBlockCleared` — *unlabelled* — Rollup of guard G1 per binding rule 4. The arithmetic, the turn index, the target test and the ValueProp all match; what diverges is that the sim only FIRES the hook when a block clear actually happened, so a turn-3 block-clear …
- `relic/charons_ashes/AfterCardExhausted` — *unlabelled* — Rollup of guard G1 per binding rule 4. Amount, props, dealer, card source and the absence of any once-per-turn limit all match; the target SET is built from a different predicate (G1), and the multi-target damage is issued as N …
- `relic/charons_ashes/g1` — dormant — One verdict per mechanism (binding rule 3): this is the same call-site divergence audit/records/relic/bag_of_marbles.json records as its guard G2, with the same verdict. C# targets `Enemies.Where(e => e.IsHittable)` …
- `relic/choices_paradox/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect is right -- 5 distinct pool cards on turn 1, each given Retain, one chosen into hand -- but they are rolled on the wrong RNG stream with the wrong draw algorithm (G1), and …
- `relic/claws/AfterObtained` — *unlabelled* — Rollup of guards G1, G2 and G5 per binding rule 4. The per-card transform is faithful in every detail that matters -- one upgrade level carried, enchantment carried when CanEnchant allows, deck-end placement, no RNG consumed …
- `relic/claws/g2` — dormant — MECHANISM: CardCmd.Transform(IEnumerable<CardTransformation>, rng) collects each original's pile and index, calls `item.Original.RemoveFromCurrentPile` for all of them, then sorts the batch with PileIndexSort (CardCmd.cs, 405) …
- `relic/cloak_clasp/BeforeSideTurnEnd` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The arithmetic, the empty-hand guard and the Unpowered prop all match, and the slot is correctly ahead of the hand flush -- but the sim has no sub-phase ordering inside its turn-end …
- `relic/crossbow/g3` — dormant — MECHANISM: C# filters the Attack list through FilterForCombat, whose predicate is 'CanBeGeneratedInCombat && Rarity != Basic && Rarity != Ancient && Rarity != Event'. pool_card_ids implements the first three clauses and omits the …
- `relic/darkstone_periapt/AfterCardChangedPiles` — dormant — Rollup of guards G1 (LIVE) and G2 per binding rule 4. The narrowing is only sound if every C# path that puts a card into PileType.Deck reaches run.add_card. It does not: the out-of-combat TRANSFORM path writes the deck directly.
- `relic/darkstone_periapt/g2` — dormant — MECHANISM: CardPileCmd.cs and :683 dispatch the hook from the general Add path, and PileType.Deck is a non-combat pile (CardPile.cs IsCombatPile), so a card added to the run's deck while a fight is in progress still triggers it. …
- `relic/daughter_of_the_wind/g2` — dormant — MECHANISM: Hook.IterateCombatHookListeners (Hook.cs) yields nothing once IsOverOrEnding is set, and 73 of the game's 147 dispatchers go through it; combat.py flips Phase.COMBAT_OVER only inside _end_combat and no dispatcher …
- `relic/demon_tongue/g2` — dormant — MECHANISM: DamageResult.cs documents UnblockedDamage as the damage the target received after blocking and OverkillDamage as the excess past 0 HP, and they are separate fields (CreatureCmd.cs has to ADD them back together when it …
- `relic/diamond_diadem/AfterCardPlayed` — *unlabelled* — Rollup of guard G2 per binding rule 4 -- the sim counts one card per logical play where C# counts one per CardPlay, so a replayed card advances the counter by 1 instead of 2 and the relic's 'at most 2 cards' condition is easier …
- `relic/dusty_tome/AfterObtained` — dormant — Rollup of guards G1 (the unguarded Card.upgrade, dormant), G2 (the lazy re-roll, LIVE on the runner path) and N2 (the added HasUponPickupEffect declaration) per binding rule 4. The core effect is faithful and executed …
- `relic/dusty_tome/g1` — dormant — MECHANISM: CardCmd.Upgrade filters on IsUpgradable == `CurrentUpgradeLevel < MaxUpgradeLevel` (CardModel.cs); cards/base.py's Card.upgrade has no filter, so every caller must supply one and this one does not. …
- `relic/dusty_tome/g6` — dormant — MECHANISM: RelicModel.HasUponPickupEffect defaults to false and DustyTome does not override it -- contrast DistinguishedCape.cs and DollysMirror.cs in this same batch, which do. The sim sets it True. The flag is not decorative …
- `relic/electric_shrymp/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. The relic's OWN halves are all faithful -- the candidate filter (N1, executed: zero disagreements over 203 ported cards), the count of 1, and the enchantment identity -- but the Imbued …
- `relic/electric_shrymp/g4` — dormant — PROMPT.md bug class 16's second half at an out-of-combat site: C#'s FromDeckForEnchantment consumes no Rng (CardSelectCmd.cs is a UI/remote-choice branch), so the sim's default random pick both chooses differently AND advances …
- `relic/ember_tea/g1` — dormant — MECHANISM: CombatRoom.cs calls CombatManager.SetUpCombat and then Hook.AfterRoomEntered; Hook.BeforeCombatStart is only reached later, from CombatManager.StartCombatInternal (CombatManager.cs, after IsInProgress is set at :402). …
- `relic/empty_cage/AfterObtained` — *unlabelled* — Rollup of guard N2 per binding rule 4. The count (CardsVar(2), EmptyCage.cs, vs CARDS = 2, empty_cage.py), the candidate filter (N1) and the removal itself all match -- executed: a fresh run's 10-card deck goes to 8. The only …
- `relic/empty_cage/g2` — dormant — Same mechanism and same verdict as relic/electric_shrymp guard N3 in this batch (binding rule 3): C#'s FromDeckGeneric (CardSelectCmd.cs) reaches either the Selector, the local UI screen or a remote choice, none of which consumes …
- `relic/fake_anchor/g3` — dormant — Same mechanism as relic/anchor's guard N3 and carried with the same gap verdict per binding rule 3, with this relic's own dormancy evidence re-executed rather than inherited: the window spans turn_structure steps 4-13, which …
- `relic/fake_orichalcum/BeforeSideTurnEnd` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect itself is right: FakeOrichalcum.cs grants BlockVar(3m, ValueProp.Unpowered) (line 23) once, clearing the latch first, and fake_orichalcum.py grants 3 at the same …
- `relic/fake_snecko_eye/AfterObtained` — dormant — MECHANISM: FakeSneckoEye.cs applies the Confused power immediately when the relic is picked up if `CombatManager.Instance.IsInProgress`, so a Fake Snecko Eye obtained mid-combat confuses you for the rest of that fight. The sim …
- `relic/fake_strike_dummy/g2` — dormant — MECHANISM: FakeStrikeDummy.cs declines only when the dealer is not the owner's creature AND the card does not belong to the owner. In single-player the card's owner is always the player, so the second half is always false and the …
- `relic/fake_venerable_tea_set/g2` — *unlabelled* — This is a SHAPE, not a one-off, and it is invisible to the existing sweeps -- .superpowers/sdd/content-relic-sweeps.md's sweep A diffs a field across two combats, and a field that is never written looks identical on both …
- `relic/festive_popper/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The effect's numbers are right -- DamageVar(9m, ValueProp.Unpowered) (FestivePopper.cs) vs DAMAGE = 9 at DamageProps.NON_CARD_UNPOWERED (festive_popper.py, :27), no …
- `relic/festive_popper/g1` — dormant — MECHANISM: step 22 is `await CardPileCmd.Draw(...)` then `await Hook.AfterPlayerTurnStart(state, choiceContext, player)` (CombatManager.cs), which itself runs Early -> plain -> Late passes (Hook.cs); step 23 is …
- `relic/festive_popper/g2` — dormant — Identical mechanism to relic/bag_of_marbles guard G2 and carried with the same gap verdict per binding rule 3, at another turn-1 all-enemies effect. C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs) and IsHittable is …
- `relic/fiddle/ModifyHandDrawLate` — *unlabelled* — Rollup of guards G2 and N1 per binding rule 4. The arithmetic matches -- Fiddle.cs returns `count + Cards.IntValue` and CanonicalVars pins CardsVar(2) (Fiddle.cs), the sim's CARDS = 2 (fiddle.py) -- but the hook is …
- `relic/forgotten_soul/AfterCardExhausted` — dormant — Rollup of guard G1 per binding rule 4. Every number and stream matches -- DamageVar(1m, ValueProp.Unpowered) (ForgottenSoul.cs) is DAMAGE = 1 with DamageProps.NON_CARD_UNPOWERED (= ValueProp.UNPOWERED, valueprops.py), the dealer …
- `relic/fragrant_mushroom/g2` — dormant — MECHANISM: the source routes the 15 through the full damage command even out of combat, so the run-level Hook pipeline runs -- ModifyHpLostBeforeOsty / AfterOsty, the damage-received notifications, and the death check. …
- `relic/fresnel_lens/g2` — dormant — PROMPT.md bug class 17 (shallow clones) applies to whoever implements this relic, so it is recorded now rather than discovered by the fix: CardModel.CreateClone / CardScope.CloneCard (CardModel.cs) carries the card's upgrade …
- `relic/frozen_egg/g3` — dormant — PROMPT.md bug class 17 at the egg relics' two sites. CardScope.CloneCard -> ClonePreservingMutability (CardModel.cs) carries upgrade level, enchantment, affliction, keyword edits and local energy-cost modifiers; the sim has no …
- `relic/fur_coat/AfterCreatureAddedToCombat` — *unlabelled* — Two divergences, both inherited rather than local. (a) C# fires Hook.AfterCreatureAddedToCombat for the STARTING creatures as well -- CombatManager.StartCombatInternal loops `foreach (Creature creature in _state.Creatures) await …
- `relic/fur_coat/g3` — dormant — MECHANISM: CreatureCmd.SetCurrentHp (CreatureCmd.cs) does three things the raw assignment does not -- it fires `Hook.AfterCurrentHpChanged(runState, combatState, creature, delta)` whenever the value actually changed, it plays a …
- `relic/gambling_chip/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The hook SLOT is right and the turn gate matches, but CardCmd.DiscardAndDraw does two things the sim's inline loop does not: it routes each discard through CardPileCmd.Add (G2) …
- `relic/gambling_chip/g1` — dormant — MECHANISM: DiscardAndDraw collects `if (card.IsSlyThisTurn) slyCards.Add(card)` while discarding (CardCmd.cs), draws, and then `foreach (CardModel item in slyCards) await AutoPlay(choiceContext, item, null …
- `relic/gambling_chip/g2` — dormant — MECHANISM: CardPileCmd.Add runs the game's pile-change machinery -- Hook.ShouldAddToDeck / Hook.ModifyCardBeingAddedToDeck for deck adds, and Hook.AfterCardChangedPiles(+Late) generally -- plus `discardPile.InvokeContentsChanged` …
- `relic/ghost_seed/AfterCardEnteredCombat` — dormant — Rollup of guard G2 per binding rule 4. The predicate and the effect match -- GhostSeed.cs applies CardKeyword.Ethereal to any card CanAffect accepts -- but C#'s `CardCmd.ApplyKeyword` adds a keyword whose SOURCE is tracked …
- `relic/ghost_seed/AfterRoomEntered` — dormant — See guard G1. GhostSeed.cs filters `room is CombatRoom` and then sweeps `Owner.PlayerCombatState.AllCards`; the sim iterates `self.player.all_cards` at on_combat_start. C#'s AfterRoomEntered for a combat room is dispatched at …
- `relic/ghost_seed/g1` — dormant — MECHANISM: the C# order is SetUpCombat -> Hook.AfterRoomEntered (CombatRoom.cs) -> AfterCombatRoomLoaded -> StartCombatInternal, which runs `Hook.AfterCreatureAddedToCombat` for every starting creature and only then …
- `relic/ghost_seed/g2` — dormant — MECHANISM: C# tracks WHERE each keyword came from, and CanAffect only refuses a card that already has a LOCALLY sourced Ethereal -- a card that is Ethereal for some other reason still receives Ghost Seed's own local copy, so the …
- `relic/girya/AfterRoomEntered` — dormant — See guard G2. Girya.cs applies StrengthPower equal to TimesLifted when `TimesLifted > 0 && room is CombatRoom`; girya.py does the same at combat start, two dispatch points later (C#'s AfterRoomEntered for a combat room fires at …
- `relic/girya/g2` — dormant — MECHANISM: CombatRoom.cs fires Hook.AfterRoomEntered after SetUpCombat, and CombatManager.StartCombatInternal then runs `AfterCreatureAdded` for every starting creature (CombatManager.cs) before `Hook.BeforeCombatStart` (:403). …
- `relic/glitter/g1` — dormant — PROMPT.md bug class 17. CardScope.CloneCard -> ClonePreservingMutability (CardModel.cs) carries upgrade level, enchantment, affliction, keyword edits and local energy-cost modifiers, and the sim has no clone helper at all …
- `relic/golden_pearl/g2` — dormant — MECHANISM: every gold gain in the game ends with a full listener pass over AfterGoldGained; run.gain_gold (run.py) stops after the addition. Golden Pearl itself does not implement AfterGoldGained, so the relic's OWN behaviour is …
- `relic/gorget/g4` — dormant — MECHANISM: PlatingPower.cs decrements in AfterSideTurnStart with a `TurnNumber != 1` guard for a player owner (turn_structure spec step 23, after the hand draw); powers.py's PlatingPower._decay runs from on_player_turn_start with …
- `relic/gremlin_horn/AfterDeath` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The relic's own body is exact -- GremlinHorn.cs's side check, EnergyVar(1) and CardsVar(1) map one-for-one onto gremlin_horn.py, and EXECUTED (py audit/tools/relic_probes_b07.py …
- `relic/gremlin_horn/g2` — dormant — MECHANISM: CreatureCmd.cs runs AfterDamageGiven, then the killing-blow-guarded AfterDamageReceived, and only then `await Kill(killedCreatures)` -- so in C# every AfterDamageGiven listener sees the victim at 0 HP but not yet dead …
- `relic/hand_drill/g1` — dormant — MECHANISM: CreatureCmd.cs runs `Hook.AfterBlockBroken` and then `Hook.AfterDamageGiven` as separate statements in the per-result loop, so every AfterBlockBroken implementer is guaranteed to run before Hand Drill. In the sim both …
- `relic/hand_drill/g2` — dormant — MECHANISM: HandDrill.cs credits the owner's PET's damage to the owner, so an Osty (or any relic-granted pet) that breaks an enemy's block also triggers Hand Drill. The sim has no pet concept at all -- executed: `grep -rn …
- `relic/happy_flower/g3` — dormant — MECHANISM: C# folds Hook.ModifyEnergyGain, then fires AfterModifyingEnergyGain over the listeners that modified it, then adds only if the result is positive; the sim folds modify_energy_gain and adds unconditionally. Two …
- `relic/hefty_tablet/AfterObtained` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The skeleton is right -- three Rare candidates on the Rewards stream with prior picks excluded and no upgrade roll, a choose-one screen, then the chosen card and an Injury …
- `relic/hefty_tablet/g2` — dormant — MECHANISM: CardFactory.cs folds `Hook.TryModifyCardRewardOptions(player.RunState, player, list2, options, out modifiers)` and then AfterModifyingCardRewardOptions over the created reward list; HeftyTablet.cs sets …
- `relic/horn_cleat/AfterBlockCleared` — *unlabelled* — Rollup of guard G1 per binding rule 4. The relic's own arithmetic and guards are exact -- `creature == Owner.Creature && TurnNumber == 2` -> BlockVar(14, Unpowered) (HornCleat.cs) vs `target is self.player and self.turn == 2` -> …
- `relic/horn_cleat/g2` — dormant — MECHANISM: Creature.AfterTurnStart returns BEFORE ClearBlock for a player whose TurnNumber == 1, but the AfterBlockCleared loop still runs for that player; the sim's player.py has no turn-1 arm, so it both clears and fires. That …
- `relic/ice_cream/g2` — dormant — This is audit/records/seam/turn_structure.json gap at spec step 17, verdicted there and matched here per binding rule 3. MECHANISM: player.py folds modify_max_energy, then asks should_reset_energy, then assigns or accumulates …
- `relic/intimidating_helmet/g3` — dormant — MECHANISM: CardModel.OnPlayWrapper does CardPileCmd.AddDuringManualCardPlay -> ModifyCardPlayResultPileTypeAndPosition -> GeneratePlayCount -> `if (Owner.Creature.IsDead) return` -> BeforeCardPlayed (CardModel.cs). combat.py …
- `relic/jeweled_mask/g3` — dormant — MECHANISM: CardModel.SetToFreeThisTurn (CardModel.cs) adds a LocalCostModifier with `LocalCostModifierExpiration.EndOfTurn | LocalCostModifierExpiration.WhenPlayed` (CardEnergyCost.cs), and the source's own remark at …
- `relic/jeweled_mask/g4` — dormant — MECHANISM: C# calls `CardPileCmd.Add(cardModel, PileType.Hand)` (JeweledMask.cs), which goes through the pile machinery; the sim's CardPileCmd.add_to_hand overflows to the discard pile when the hand is at …
- `relic/kifuda/AfterObtained` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. Kifuda.cs enchants up to 3 deck cards with Adroit at amount 3; the port does nothing at all.
- `relic/kifuda/g2` — dormant — C# offers a not-cancelable screen whose selection size is 0..3 -- the player may confirm with fewer than 3 picks but may not back out -- while the sim's out-of-combat verb is `run.select_cards(purpose, candidates, count)` …
- `relic/kusarigama/g2` — dormant — C# picks the random target from `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHitting(CombatState, this)` (Creature.cs). Relic.living_enemies (relics/base.py) filters on `not …
- `relic/lantern/g1` — dormant — PlayerCmd.GainEnergy does five things: bail on `amount <= 0`, bail on `CombatManager.Instance.IsEnding`, `Hook.ModifyEnergyGain(... out modifiers)`, `await Hook.AfterModifyingEnergyGain(state, modifiers)`, then …
- `relic/lasting_candy/AfterCombatEnd` — dormant — LastingCandy.cs is the `CombatsSeen++` counter that decides 'every other combat' (IsInTriggeringCombat = `CombatsSeen > 0 && CombatsSeen % 2 == 0`, LastingCandy.cs). The sim's Relic base HAS the hook -- `after_combat_end(run …
- `relic/lasting_candy/TryModifyCardRewardOptions` — *unlabelled* — Rollup of guards G1 and G4 per binding rule 4. LastingCandy.cs adds a Power card to every OTHER combat's card reward; the port does nothing.
- `relic/lava_lamp/g2` — dormant — PROMPT.md bug class 17. CardModel.CreateClone is ClonePreservingMutability (CardModel.cs) and carries the card's enchantment, affliction, keyword edits and local energy-cost modifiers as well as its upgrade level …
- `relic/leafy_poultice/g3` — dormant — CreatureCmd.LoseMaxHp (src/Core/Commands/CreatureCmd.cs) computes an UNFLOORED newMaxHp = MaxHp - amount and, when that is below CurrentHp, deals the difference as Unblockable|Unpowered damage through the whole pipeline -- hooks …
- `relic/letter_opener/g2` — dormant — C# damages `Enemies.Where(e => e.IsHittable)` -- `!IsDead && Hook.ShouldAllowHitting(...)` (src/Core/Combat/CombatState.cs; src/Core/Entities/Creatures/Creature.cs) -- while Relic.living_enemies filters on `not e.is_gone` only …
- `relic/lizard_tail/AfterPreventingDeath` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. LizardTail.cs heals `Math.Max(1, MaxHp * HealVar(50)/100)` in AfterPreventingDeath. The sim HAS that hook -- HookSystem.after_preventing_death (hooks.py), dispatched by …
- `relic/lizard_tail/ShouldDieLate` — *unlabelled* — Rollup of guards G3 and G4 per binding rule 4. The predicate itself is transcribed correctly -- veto only for the owner's creature, and only while not already used -- but (a) the sim collapses C#'s ShouldDie/ShouldDieLate …
- `relic/lords_parasol/AfterRoomEntered` — *unlabelled* — Rollup of guard G1 per binding rule 4. LordsParasol.cs filters AfterRoomEntered to a MerchantRoom and hands the inventory to PurchaseEverything, which buys the character cards, the colorless cards, the relics, the potions AND …
- `relic/lost_coffer/g4` — dormant — The flag exists so that relics which affect card REWARDS only (CardCreationFlags.cs names Prismatic Gem and Dingy Rug) can tell a reward roll from any other card creation. The sim's create_reward_cards runs …
- `relic/mango/AfterObtained` — *unlabelled* — The forward direction is faithful (guard N1): run.gain_max_hp(14) is CreatureCmd.GainMaxHp's SetMaxHp-then-Heal pair exactly. The gap is guard G1 -- the sim-only undo, which the conformance runner depends on, gives back the max …
- `relic/meat_cleaver/TryModifyRestSiteOptions` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The option is added with the right id and the right numbers (guards N2, N3), but the sim OMITS it when it would be disabled instead of adding a disabled one (G1) and its effect …
- `relic/meat_cleaver/g1` — dormant — MECHANISM: CookRestSiteOption.OnSelect builds `CardSelectorPrefs(RemoveSelectionPrompt, 2) { Cancelable = true, RequireManualConfirmation = true }`, and `if (!enumerable.Any) return false` -- cancelling removes nothing, grants no …
- `relic/miniature_cannon/ModifyDamageAdditive` — *unlabelled* — Rollup of guard G1 per binding rule 4. Three of C#'s four early returns are reproduced exactly (N1-N3, all executed); the fourth is an AND that the port narrows to one of its two disjuncts.
- `relic/miniature_cannon/g1` — dormant — MECHANISM: miniature_cannon.py requires `dealer is self.player`, dropping C#'s `cardSource.Owner == base.Owner` alternative. In single-player the two disjuncts coincide for ordinary card play, so the divergence needs a …
- `relic/miniature_tent/g1` — dormant — MECHANISM: Hook.ShouldDisableRemainingRestSiteOptions (Hook.cs) walks every hook listener; RunState.should_disable_remaining_rest_site_options (run.py) walks only the relic list, so a non-relic listener could never keep a …
- `relic/molten_egg/ModifyMerchantCardCreationResults` — *unlabelled* — Same body as the reward path in C# too -- MoltenEgg.cs calls the identical EggRelicHelper.UpgradeValidCards -- and notably has NO NoHookUpgrades check, so the delegation is faithful in shape. Carries guard G4's verdict (the extra …
- `relic/molten_egg/TryModifyCardBeingAddedToDeck` — *unlabelled* — Rollup of guards G2 and G5 per binding rule 4. All four of MoltenEgg.cs's guards are reproduced (N1-N3) and the add_card route works (executed: a Bash added to the deck arrives at upgrade_level 1), but the DECK-TRANSFORM route …
- `relic/molten_egg/g4` — dormant — MECHANISM: the reward and merchant paths both go through `EggRelicHelper.UpgradeValidCards(cards, CardType.Attack, this)` (MoltenEgg.cs, :39), whose only filter is `card.Type == cardType && card.IsUpgradable` (EggRelicHelper.cs) …
- `relic/molten_egg/g9` — dormant — MECHANISM: Hook.TryModifyCardRewardOptions (Hook.cs) walks every listener's non-Late override and then walks every listener's Late override, so a Late modifier is guaranteed to see the finished output of every plain one. Molten …
- `relic/mr_struggles/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The slot, the scaling amount, the props, the dealer and the target set all match (N1-N3), but the port omits the win check its identically shaped sibling relic/mercury_hourglass …
- `relic/mummified_hand/AfterCardPlayed` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The trigger matches (a Power play, MummifiedHand.cs) and the RNG stream matches (Rng.CombatCardSelection, MummifiedHand.cs, vs combat_rng.card_selection, mummified_hand.py), but …
- `relic/music_box/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. The identity test (`cardPlay.Card == CardBeingPlayed`, MusicBox.cs), the Ethereal keyword, the destination pile and both state writes all match; what does not is `cardPlay.Card.CreateClone` …
- `relic/neows_bones/AfterObtained` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The SHAPE is right -- two relics drawn from Neow's own option pool on the per-player Rewards stream, then one generatable curse on the Niche stream -- and the shuffle algorithm, the …
- `relic/neows_talisman/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. Card SELECTION is faithful (the last Basic-rarity deck card carrying each of the Strike and Defend tags), but the upgrade itself is `card.upgrade` -- the sim's unguarded bare increment …
- `relic/new_leaf/AfterObtained` — dormant — Rollup of guards N1 and G1 per binding rule 4. Count, selection prompt and deck placement are all faithful; the named Niche RNG stream is dropped (N1, live for RNG parity) and the candidate list omits C#'s Quest-card exclusion …
- `relic/new_leaf/g2` — dormant — MECHANISM: CardSelectCmd.FromDeckForTransformation (CardSelectCmd.cs) builds its candidate list as `Cards.Where(c => c.Type != CardType.Quest && c.IsTransformable)`. run.transformable_cards (run.py) returns removable_cards, i.e. …
- `relic/nunchaku/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. Trigger, counter, modulus, energy amount and the counter's per-RUN lifetime all match; what does not is how many times the hook fires for a REPLAYED attack.
- `relic/nunchaku/g5` — dormant — This is the missing-AfterModifying-companion family that audit/records/seam/power_cmd.json gap G4 records (13 AfterModifying* variants in Hook.cs, one of them implemented in the sim) and that relic/bag_of_preparation N1 already …
- `relic/old_coin/g3` — dormant — This is the missing-AfterModifying-companion family that audit/records/seam/power_cmd.json gap G4 records and that relic/bag_of_preparation N1 already verdicted `gap` at the hand-draw dispatcher; one verdict per mechanism …
- `relic/ornamental_fan/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. The Attack filter, the counter, the modulus and the 4 unpowered Block all match; what does not is how many times the hook fires for a REPLAYED Attack.
- `relic/paels_legion/AfterModifyingBlockAmount` — *unlabelled* — See guard G4. C# keeps the LATCH in a separate hook that Hook.AfterModifyingBlockAmount (Hook.cs) only calls for listeners that actually changed the value, and whose own body then applies two further guards -- `modifiedAmount <= …
- `relic/paels_legion/g3` — dormant — MECHANISM: PaelsLegion.cs checks props, cardSource and cardSource.Owner -- and NOTHING about the target. So in C#, a card played by the owner that grants block to any creature has that block doubled, including a creature that is …
- `relic/paels_legion/g4` — dormant — MECHANISM (PROMPT.md bug class 15 -- two C# hooks collapsed onto one sim method, and the guard sets differ): (a) CreatureCmd.GainBlock computes the modified amount, floors it at 0, and only then calls …
- `relic/paels_wing/TryModifyCardRewardAlternatives` — *unlabelled* — Rollup of guard G1 per binding rule 4. The alternative's payload is right -- the SACRIFICE key (PaelsWing.cs vs rewards.py's documented "SACRIFICE" semantics) and PostAlternateCardRewardAction.EndSelectionAndCompleteReward, i.e. …
- `relic/paper_phrog/ModifyVulnerableMultiplier` — *unlabelled* — Rollup of guards G1 and N2 per binding rule 4. NOT a Hook override: PaperPhrog.cs is a plain public method, and its ONE caller is VulnerablePower.ModifyDamageMultiplicative, which looks the relic up directly on the dealer …
- `relic/paper_phrog/g1` — dormant — MECHANISM: VulnerablePower.cs does `dealer.Player?.GetRelic<PaperPhrog>` and calls the method on that single instance, so the bonus is applied at most once no matter what. hooks.py folds `mult` through EVERY listener that defines …
- `relic/paper_phrog/g3` — dormant — MECHANISM: paper_phrog.py is `if dealer is self.player`, with no target check. Combined with the caller's requirement that the dealer be the phrog's owner (VulnerablePower.cs) and the power's requirement that the target be the …
- `relic/parrying_shield/AfterSideTurnEnd` — dormant — Rollup of guards G1 and G2 per binding rule 4. Everything else maps: the threshold and the damage are `new BlockVar(10m, ValueProp.Unpowered)` and `new DamageVar(6m, ValueProp.Unpowered)` (ParryingShield.cs) with no …
- `relic/pen_nib/AfterCardPlayed` — *unlabelled* — Rollup of guards G1 and G3. The unmark logic is identical (PenNib.cs: bail unless AttackToDouble is this card, then null it), but the same per-iteration/per-play mismatch applies -- C# fires it at CardModel.cs, INSIDE the …
- `relic/pen_nib/ModifyDamageMultiplicative` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The `cardSource == AttackToDouble -> 2m` arm (PenNib.cs) is ported exactly, but the port drops the whole `AttackToDouble == null` arm (PenNib.cs), which is what doubles the PENDING …
- `relic/pen_nib/g3` — dormant — MECHANISM: the mark (AttackToDouble / _card_to_double) is cleared only by the AfterCardPlayed handler. C#'s dispatch of that hook is conditional, the sim's is not, so the two codebases can leave the relic in different states …
- `relic/phial_holster/AfterObtained` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. Both halves of PhialHolster.cs are present in shape -- one extra slot then two random potions -- but the potion generation ignores the RNG stream the source names and rolls a flat …
- `relic/philosophers_stone/AfterCreatureAddedToCombat` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect and the constant are right -- 1 Strength on each joiner, executed at b12-stone: a mid-combat SpinyToad spawn comes in at Strength(1) -- and the two hooks provably cannot …
- `relic/philosophers_stone/g1` — dormant — MECHANISM: `if (creature.Side == base.Owner.Creature.Side) return;` is a side comparison; `if creature is self.combat.player: return` is an identity comparison. For any player-side creature other than the player itself -- a pet …
- `relic/pocketwatch/ModifyHandDraw` — *unlabelled* — Rollup of guard G1. The arithmetic and all three clauses are faithful -- `player != Owner` (multiplayer), `TurnNumber == 1`, and `_cardsPlayedLastTurn > CardThreshold` -> no bonus, else `count + Cards` (Pocketwatch.cs) map onto …
- `relic/prismatic_gem/g1` — dormant — MECHANISM: C# bails on NoCardPoolModifications, on !IsCardReward, on `options.CustomCardPool != null` and on `options.CardPools.All(p => p.IsColorless)`. The CustomCardPool bail is what keeps the relic away from narrowed pools …
- `relic/prismatic_gem/g2` — dormant — This is audit/records/seam/turn_structure.json step 17's finding, not a new one: `player.py` calls modify_max_energy first and should_reset_energy second, where CombatManager.cs evaluates ShouldPlayerResetEnergy first and only …
- `relic/punch_dagger/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. PunchDagger.cs enchants one deck card with Momentum 5 on pickup; the port does nothing.
- `relic/punch_dagger/CanonicalVars` — *unlabelled* — PunchDagger.cs pins `new DynamicVar('Momentum', 5m)` and AfterObtained reads it TWICE -- as the enchantment amount passed to CardSelectCmd.FromDeckForEnchantment and as the amount passed to CardCmd.Enchant (PunchDagger.cs, 30). …
- `relic/rainbow_ring/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. The trigger, the amounts, the applier and the order (Strength then Dexterity) all match; the difference is WHEN the once-per-turn latch is set relative to the two PowerCmd.apply calls.
- `relic/rainbow_ring/g1` — dormant — MECHANISM: C#'s guard is `ActivationCountThisTurn < 1` (RainbowRing.cs) and the counter is only bumped at line 119, after `await PowerCmd.Apply<StrengthPower>` and `await PowerCmd.Apply<DexterityPower>` have both resolved. …
- `relic/red_mask/BeforeSideTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect is right -- 1 Weak (PowerVar<WeakPower>(1m), RedMask.cs) to every enemy on turn 1, applier = the player -- but the hook slot and the enemy set are both off. This relic is …
- `relic/red_mask/g1` — dormant — MECHANISM: audit/records/seam/turn_structure.json puts Hook.BeforeSideTurnStart at step 9 (before any block is cleared, before the energy reset and before the enemies re-roll their moves at step 11) and Hook.AfterSideTurnStart at …
- `relic/red_mask/g2` — dormant — C# targets `Enemies.Where(e => e.IsHittable)`, and IsHittable is `!IsDead && Hook.ShouldAllowHitting(...)`. Relic.living_enemies (relics/base.py) filters on `not e.is_gone` ONLY -- its own docstring concedes the …
- `relic/red_skull/g3` — dormant — MECHANISM: C# re-evaluates the owner's threshold whenever ANY creature's HP changes during combat -- an enemy taking damage re-runs ModifyStrengthIfNecessary -- because the method reads Owner.Creature and ignores the hook's …
- `relic/ruined_helmet/AfterModifyingPowerAmountReceived` — *unlabelled* — Rollup of guard G3 per binding rule 4. RuinedHelmet.cs is a SEPARATE C# hook that fires only for listeners whose Try returned true (Hook.cs collects them into `receivedModifiers`; PowerCmd.cs and :242 dispatch to exactly those) …
- `relic/ruined_helmet/TryModifyPowerAmountReceived` — *unlabelled* — Rollup of guards G2 and G3 per binding rule 4. The four C# clauses are reproduced exactly -- `canonicalPower is StrengthPower`, `target == Owner.Creature`, `amount <= 0`, `UsedThisCombat` (RuinedHelmet.cs) against …
- `relic/ruined_helmet/g2` — dormant — This is audit/records/seam/power_cmd.json gap G3 at the site that record already names -- it cites `sts2_rl/relics/ruined_helmet.py` as the received-side listener and labels the mechanism a gap. One verdict per mechanism, binding …
- `relic/ruined_helmet/g3` — dormant — This is audit/records/seam/power_cmd.json gap G4 at its own site -- that record names RuinedHelmet.AfterModifyingPowerAmountReceived (RuinedHelmet.cs) as one of the two live C# listeners on the missing companion event, and …
- `relic/sai/g1` — dormant — MECHANISM: Hook.AfterSideTurnStart runs every listener's AfterSideTurnStart and then every listener's AfterSideTurnStartLate as two complete passes (Hook.cs), and it runs only after every player's SetupPlayerTurn -- i.e. after …
- `relic/screaming_flagon/BeforeSideTurnEnd` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect arithmetic is faithful (empty-hand gate, 20 Unpowered damage to every hittable enemy) but the sim's turn-end pipeline diverges twice at this hook: C#'s Hook.BeforeTurnEnd …
- `relic/sea_glass/AfterObtained` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. SeaGlass.cs does two separable things: it offers 15 cards from ANOTHER character's pool (waived, N1 -- genuine other-character scope) and it burns 15 CardFactory.CreateForReward …
- `relic/seal_of_gold/g2` — dormant — MECHANISM as recorded for relic/sai in this batch: Hook.AfterSideTurnStart is a complete pass that runs after every step-22 Hook.AfterPlayerTurnStart listener and is followed by a second AfterSideTurnStartLate pass (Hook.cs …
- `relic/self_forming_clay/AfterDamageReceived` — *unlabelled* — Rollup of guards G1, G2 and N3 per binding rule 4. The latch is faithful (owner check, unblocked-damage > 0, +3 per HP-loss event, killing-blow guard inherited from cmds.py) but the RE-ARCHITECTURE of the payout is where the …
- `relic/self_forming_clay/g3` — dormant — MECHANISM: `grep -rn SelfFormingClay sts2_rl/powers.py` returns nothing -- the sim models the effect as a private int on the relic. In C# it is a real PowerModel with `Type => Buff` and `StackType => Counter` …
- `relic/shovel/TryModifyRestSiteOptions` — *unlabelled* — Rollup of guard G2 per binding rule 4. The DIG option's effect matches -- RelicCmd.Obtain(RelicFactory.PullNextRelicFromFront(Owner)) (DigRestSiteOption.cs) maps to run.obtain_relic_from_grab_bag (shovel.py), and the default …
- `relic/shovel/g2` — dormant — MECHANISM: Shovel.TryModifyRestSiteOptions adds `new DigRestSiteOption(player)` unconditionally (Shovel.cs) and DigRestSiteOption overrides nothing that could disable it -- RestSiteOption.IsEnabled is the base `=> true` …
- `relic/signet_ring/g2` — dormant — MECHANISM: C#'s gold pipeline is the same two-phase shape as its damage and power pipelines -- ModifyGoldGained collects the listeners that changed the amount, then AfterModifyingGoldGained notifies exactly those listeners with …
- `relic/silver_crucible/ShouldGenerateTreasure` — *unlabelled* — Rollup of guard G3 per binding rule 4. The predicate matches (`TreasureRoomsEntered > 1`, SilverCrucible.cs) and so does the all-must-agree dispatcher (`if (!item.ShouldGenerateTreasure(player)) return false`, Hook.cs). What …
- `relic/silver_crucible/g3` — dormant — MECHANISM: C# reaches the Spoils Map payout only from INSIDE the gated reward routine -- OneOffSynchronizer.DoTreasureRoomRewards opens with `if (!Hook.ShouldGenerateTreasure(player.RunState, player)) return 0;` …
- `relic/sling_of_courage/AfterRoomEntered` — dormant — Rollup of guard N1 per binding rule 4. SlingOfCourage.cs applies PowerVar<StrengthPower>(2) from AfterRoomEntered when `room.RoomType == RoomType.Elite`, and for a CombatRoom that hook fires after CombatManager.SetUpCombat and …
- `relic/sling_of_courage/g1` — dormant — MECHANISM: for a CombatRoom, `Hook.AfterRoomEntered` fires at CombatRoom.cs, between SetUpCombat (line 225) and AfterCombatRoomLoaded (line 230), which starts the combat and dispatches Hook.BeforeCombatStart. So in C# nothing in …
- `relic/snecko_eye/AfterObtained` — dormant — SneckoEye.cs applies the Confused power immediately when the relic is picked up DURING a combat (`if (CombatManager.Instance.IsInProgress) await ApplyPower`). snecko_eye.py defines only on_combat_start and modify_hand_draw, so a …
- `relic/sozu/ShouldProcurePotion` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. The predicate itself is right and the out-of-combat gate works; the divergence is that C# funnels EVERY procurement through one gated command and the sim has a second, ungated …
- `relic/sparkling_rouge/AfterBlockCleared` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect, the amounts and the turn number all match; the hook SLOT does not.
- `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The arithmetic is right -- a Power card costs 1 more -- but the sim has no phase structure and no per-creature listener grouping, and this relic is the named ported witness for …
- `relic/spiked_gauntlets/g2` — dormant — Hook.ModifyEnergyCostInCombat runs TWO complete listener passes -- every TryModifyEnergyCostInCombat, then every TryModifyEnergyCostInCombatLate (Hook.cs). SpikedGauntlets implements the PLAIN one (SpikedGauntlets.cs), so in C# …
- `relic/spiked_gauntlets/g3` — dormant — Three differences in the same collapse, checked side by side per PROMPT.md bug class 15. (a) The owner guard (SpikedGauntlets.cs) is multiplayer-only and is separately waived at N1. (b) Hook.ModifyEnergyCostInCombat opens with …
- `relic/stone_calendar/BeforeSideTurnEnd` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The trigger turn, the damage number, the target set and the props all match and are executed; the divergences are the flattened sub-phase ordering (G1) and the …
- `relic/stone_calendar/g2` — dormant — Same mechanism and therefore the same verdict as relic/bag_of_marbles guard G2 (binding rule 3): C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHitting(...)`, while …
- `relic/stone_cracker/g2` — dormant — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE ported relics whose C# combat effect hangs off `AfterRoomEntered` with a `room is CombatRoom` test are mapped onto the sim's …
- `relic/stone_humidifier/AfterRestSiteHeal` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect and its amount are exactly right; the dispatch is missing one of the hook's two C# call sites.
- `relic/stone_humidifier/g1` — dormant — MECHANISM: an executed grep for AfterRestSiteHeal over the decompiled source finds two callers outside the relic models -- HealRestSiteOption.cs (`isMimicked` forwarded from the option) and MendRestSiteOption.cs (`isMimicked …
- `relic/strike_dummy/g2` — dormant — MECHANISM: StrikeDummy.cs is `if (dealer != base.Owner.Creature && cardSource.Owner != base.Owner) return 0m;` -- a conjunction of negatives, so either clause alone suffices. strike_dummy.py requires `dealer is self.player` and …
- `relic/sword_of_jade/AfterRoomEntered` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. The power, the amount and the target are right and executed; the hook SITE is one dispatch later than C#'s and the applier identity differs.
- `relic/sword_of_jade/g1` — dormant — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE ported relics whose C# combat effect hangs off `AfterRoomEntered` with a `room is CombatRoom` test are mapped onto the sim's …
- `relic/tea_of_discourtesy/g2` — dormant — MECHANISM: C# creates the card with `combatState.CreateCard<T>(player)` (CardPileCmd.cs) and adds it through AddGeneratedCardToCombat, which fires `Hook.AfterCardEnteredCombat` (CardPileCmd.cs) and puts the CardModel in the …
- `relic/the_abacus/AfterShuffle` — *unlabelled* — Rollup of guard N4 per binding rule 4. The effect, the owner guard and the constant all match and the trigger set is executed-confirmed identical (N3); the one divergence is that C# refuses to dispatch AfterShuffle once the …
- `relic/the_abacus/g4` — dormant — MECHANISM: CardPileCmd.Shuffle returns immediately on `CombatManager.Instance.IsOverOrEnding` (CardPileCmd.cs), bails out mid-way through its card-add loop on the same condition (:897-900), and wraps the hook itself in `if …
- `relic/the_boot/g2` — dormant — MECHANISM: ValuePropExtensions.IsPoweredAttack (ValuePropExtensions.cs) is `props.HasFlag(Move) && !props.HasFlag(Unpowered)` -- a property of the DAMAGE CALL. the_boot.py asks about the CARD instead: `if card is None or …
- `relic/toasty_mittens/BeforeHandDraw` — *unlabelled* — Rollup of guard G1 per binding rule 4. HALF THE RELIC IS MISSING: ToastyMittens.cs exhausts a draw-pile card AND applies 1 Strength every turn; the port implements only the exhaust. The slot, the reshuffle, the turn-1 non-Innate …
- `relic/touch_of_orobas/AfterObtained` — dormant — Rollup of guards G1 and N4 per binding rule 4. The core behaviour is right and executed: the starter relic is replaced IN PLACE by its refinement and the replacement's own after_obtained runs. What the port drops from …
- `relic/touch_of_orobas/g2` — dormant — MECHANISM: the port bypasses RunState.add_relic (run.py) entirely -- it writes into run.relics itself -- so nothing removes the replacement from the run's grab bag and a later pull could offer the same relic a second time. …
- `relic/toy_box/AfterCombatEnd` — dormant — Rollup of guards G2 and N1 per binding rule 4. The counter and the every-3rd-combat trigger are faithful (N1); the divergence is that RelicCmd.Melt leaves the melted relic in the player's relic list as an inert entry and the port …
- `relic/toy_box/g2` — dormant — MECHANISM: RelicCmd.Melt (RelicCmd.cs) is `relic.Owner.MeltRelicInternal(relic); await relic.AfterRemoved;` -- the relic STAYS in the list, and the game stops it working by excluding melted relics from both hook-listener walks …
- `relic/tungsten_rod/g6` — dormant — MECHANISM: out of combat, C# gives deck cards, card enchantments, relics, potions, Modifiers, BadgeModels and the MultiplayerScalingModel a chance at ModifyHpLost; the sim's out-of-combat path consults relics alone. That is …
- `relic/tuning_fork/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. Every clause of the relic is faithful -- the Skill test, the >= threshold, the `-= threshold` rather than a zeroing, the 10 and the 7, and (contrary to its own docstring) the per-run counter …
- `relic/unsettling_lamp/BeforePowerAmountChanged` — *unlabelled* — The latch is not separable from the double in the sim, which is what makes guards G2 and G3 possible: C# runs seven latch guards (UnsettlingLamp.cs) and a DIFFERENT five-guard set on the multiplicative (lines 108-127), and the …
- `relic/unsettling_lamp/ModifyPowerAmountGivenMultiplicative` — dormant — C# returns a MULTIPLICATIVE factor into Hook.ModifyPowerAmountGiven's two-pass fold (Hook.cs: every listener's additive contribution is summed FIRST, then every listener's multiplicative factor is applied to that sum). The sim's …
- `relic/unsettling_lamp/g3` — dormant — MECHANISM: PowerModel.GetTypeForAmount (PowerModel.cs) returns Debuff when `StackType == Counter && AllowNegative && amount < 0`, so a NEGATIVE-amount Strength or Dexterity -- both declared Type => Buff -- is a Debuff for the …
- `relic/unsettling_lamp/g5` — dormant — MECHANISM: UnsettlingLamp.cs puts the applier and target-side checks on BeforePowerAmountChanged (the latch) only. ModifyPowerAmountGivenMultiplicative (lines 106-129) checks just TriggeringCard / cardSource / …
- `relic/unsettling_lamp/g6` — dormant — MECHANISM: PowerCmd.Apply carries cardSource explicitly, so C# knows the exact card responsible for each individual power application; the Lamp compares `cardSource != TriggeringCard` (UnsettlingLamp.cs). The sim reconstructs it …
- `relic/vajra/g1` — dormant — MECHANISM: as above -- one full combat-setup phase separates the two positions, and it contains AfterCreatureAdded plus every enemy's opening RollMove. TWO readers could expose it and neither exists in ported content. (a) A …
- `relic/vambrace/AfterCardPlayed` — *unlabelled* — Rollup of guard G3 per binding rule 4. Vambrace.cs is where the charge is actually spent: BlockGainedThisCombat = true, gated on the played card being the latched TriggeringCard and on the flag not already being set. Dropping …
- `relic/vambrace/AfterModifyingBlockAmount` — *unlabelled* — Rollup of guard G3 per binding rule 4. Vambrace.cs sets ONLY TriggeringCard here (plus Flash/Status); it does NOT spend the once-per-combat charge. The port sets `_used = True` here instead (vambrace.py), which spends the charge …
- `relic/vambrace/g6` — *unlabelled* — PROMPT.md bug class 24 -- a docstring that misdescribes the PORT. The multiplier hook is NOT stateless: vambrace.py reads `self._used`, which is exactly the per-combat state. The claim reads as a justification for putting the …
- `relic/velvet_choker/g2` — *unlabelled* — VelvetChoker.cs is a BeforeSideTurnStart override that zeroes `_cardsPlayedThisTurn` on every player turn start, so the comment's premise -- that the per-turn reset is a sim invention -- is false, and it invites a future reader …
- `relic/venerable_tea_set/AfterRoomEntered` — *unlabelled* — Rollup of guard G1 per binding rule 4, and the whole of this record's finding. VenerableTeaSet.cs latches GainEnergyInNextCombat = true whenever a RestSiteRoom is entered. Note what the C# latch is actually keyed on: room ENTRY …
- `relic/venerable_tea_set/GainEnergyInNextCombat` — *unlabelled* — Rollup of guard G1 per binding rule 4. The C# property is a [SavedProperty] whose change-guarded setter flips base.Status (VenerableTeaSet.cs); the persistence it needs -- survive the rest site, the map walk and the next combat's …
- `relic/vexing_puzzlebox/g4` — dormant — C#'s SetToFreeThisTurn is `EnergyCost.SetThisTurnOrUntilPlayed(0)` plus SetStarCostThisTurn(0) (CardModel.cs). The sim's set_free_this_turn sets `_free_this_turn = True` (sts2_rl/cards/base.py) and clears it only in …
- `relic/whispering_earring/AfterAutoPrePlayPhaseEnteredLate` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The loop's SHAPE is right -- up to 13 iterations, break on combat over / turn change / nothing playable, take the first playable card in hand, spend its energy, play it. Three …
- `relic/wing_charm/g3` — dormant — PROMPT.md bug class 17. WingCharm.cs clones the chosen option and enchants the CLONE, then substitutes it via `cardCreationResult.ModifyCard(card, this)` (:43) rather than mutating the original -- so a fix that follows the C# …
- `relic/winged_boots/g3` — dormant — MECHANISM: in C# the charge is each relic's own business, so two free-travel sources both react to the same non-child travel -- Winged Boots would still burn a use even if something else were already granting the travel. The …
- `relic/wongos_mystery_ticket/g7` — dormant — MECHANISM: C#'s `PullNextRelicFromFront` is `TestRngInjector.ConsumeRelicOverride ?? player.RelicGrabBag.PullFromFront(rarity, filter, runState) ?? FallbackRelic` (RelicFactory.cs), so all three RelicRewards always Populate to a …

## 3F. `potion` — dormant and single-site mechanisms

Fourteen mechanisms. The first is a 51-site family; the rest are one or two
sites each.
Every one carries an explicit `live: false` in its record — the potion tier
states the boolean on all 152 entries, so nothing here is inheriting its
liveness from a neighbour.

| mechanism | sites | dormant because | goes live when |
|---|---|---|---|
| `potion/_effect_bracket` | 51 | `PotionModel.cs:324-331` brackets `OnUse` in `BeginCardOrPotionEffect`/`EndCardOrPotionEffect` and the sim has no re-entrancy depth counter; the ported cards that auto-play mid-resolution do not move the draw pile between the inner and outer ends | a potion or card empties the hand and then moves the draw pile from inside a nested auto-play. **Deliberately not merged** into `relic/unceasing_top`'s card-play half: the guard's own text refuses it, because a fix that brackets only card plays leaves this half open |
| `potion/_filter_for_combat_event_rarity` | 6 | `CardFactory.FilterForCombat` drops Basic, Ancient **and Event** (`CardFactory.cs:159-162`); `cards/pool.py:108-117` drops the first two. Executed: both pools' Event buckets are empty (IRONCLAD 85→78, COLORLESS 53→50) | any Event-rarity card is added to `IRONCLAD_POOL` or `COLORLESS_POOL`. **CROSS-STREAM: the fix lands in `cards/pool.py`, which the card tier owns** — the recipe is not "edit a potion file" |
| `potion/_strength_applier` | 4 | `StrengthCmd.apply` (`sts2_rl/cmds.py:349-361`) drops the applier the C# passes; no ported listener reads a `StrengthPower`'s applier, and Unsettling Lamp's guard returns early for a self-targeted buff either way | a listener reads a `StrengthPower`'s applier, or Strength is applied to an **enemy** through `StrengthCmd`. Note the same potion passes the applier for its Dexterity half — the two halves of `fysh_oil` disagree |
| `potion/snecko_oil/g2` | 1 | `SneckoOil.cs:51` skips a card whose unmodified cost is negative; the sim clamps costs at 0 (`cards/base.py:232`) so no card can present one | an unclamped cost representation. **Grade A when it wakes**, not B: the skipped card also skips a `CombatEnergyCosts` draw |
| `potion/snecko_oil/g3` | 1 | `SetThisTurnOrUntilPlayed` also expires on play; `set_cost_this_turn` models only the end-of-turn half, and its own docstring says so | any effect that returns a played card to hand within the turn. **No other record verdicts this**, and `relic/snecko_eye` is the other consumer |
| `potion/snecko_oil/OnUse` | 1 | rollup of the two above | — |
| `potion/foul_potion/g1` + `potion/foul_potion/OnUse` | 2 | both out-of-combat arms are unported — the shop arm (`FoulPotion.cs:79-88`) and the Fake Merchant arm (`:89-108`) — and the port's docstring cites `RunState.merchant_driven_off`, which does not exist. The Fake Merchant event option is ported but **discards** the potion rather than using it, so no `OnUseWrapper` and no `AfterPotionUsed` | the sim gains an out-of-combat use path |
| `potion/fairy_in_a_bottle/g1` + `potion/fairy_in_a_bottle/AfterPreventingDeath` | 2 | the automatic trigger calls `potion.use` directly (`sts2_rl/potions.py:1245-1250`) instead of `OnUseWrapper` (`FairyInABottle.cs:44`), so `Hook.AfterPotionUsed` never fires when the fairy pops. Both C# implementers are ported and working at their own sites — the game grants 3 temporary Strength when the fairy saves you and the sim grants none | already reachable; it is recorded dormant only because no conformance replay pops a fairy |
| `potion/gamblers_brew/g3` | 1 | the Sly auto-play deferral (`CardCmd.cs:201-204`) has no sim counterpart; `grep -rn '\bsly\b' sts2_rl/` returns one hit, a docstring | any card with the Sly keyword is ported |
| `potion/gamblers_brew/g4` | 1 | the sim fires `on_card_discarded` *before* the pile move where C# fires it after (`CardCmd.cs:192-194`); executed, the sim has no `on_card_discarded` listener at all | any listener on `on_card_discarded` that reads the discard pile |
| `potion/fairy_in_a_bottle/g2` | 1 | the sim uses the *Discard* verb where C# uses `RemoveBeforeUse` (`PotionModel.cs:221-234`); harmless today because `discard_potion` dispatches nothing | `Hook.AfterPotionDiscarded` is wired to `discard_potion` — which `relic/belt_buckle` needs. **Recorded so that fix does not silently create a defect** |
| `potion/foul_potion/TargetType` | 1 | the tier's only computed `TargetType` branch (`FoulPotion.cs:33-43`: `TargetedNoCreature` out of combat, `AllEnemies` in it), unported | the sim gains an out-of-combat use path without also giving Foul Potion its non-combat arm |
| `potion/foul_potion/PassesCustomUsabilityCheck` | 1 | **the game's only implementer** of that hook (executed grep), unported; the only arm the sim can reach returns true unconditionally | the sim gains an out-of-combat use path, at which point Foul Potion becomes drinkable in rooms the game greys out |
| `potion/orobic_acid/OnUse` | 1 | rollup of `potion/_filter_for_combat_event_rarity` at that unit | — |

Sites, for `coverage`: `potion/ashwater/g6`, `potion/attack_potion/g3`,
`potion/attack_potion/g7`, `potion/beetle_juice/g3`,
`potion/blessing_of_the_forge/g5`, `potion/block_potion/g3`,
`potion/blood_potion/g5`, `potion/bottled_potential/g4`, `potion/clarity/g3`,
`potion/colorless_potion/g4`, `potion/colorless_potion/g8`,
`potion/cure_all/g3`, `potion/dexterity_potion/g3`, `potion/distilled_chaos/g6`,
`potion/droplet_of_precognition/g6`, `potion/duplicator/g3`,
`potion/energy_potion/g2`, `potion/entropic_brew/g7`,
`potion/explosive_ampoule/g4`, `potion/fairy_in_a_bottle/g2`,
`potion/fairy_in_a_bottle/g7`, `potion/fire_potion/g3`, `potion/flex_potion/g3`,
`potion/fortifier/g3`, `potion/foul_potion/PassesCustomUsabilityCheck`,
`potion/foul_potion/TargetType`, `potion/foul_potion/g6`,
`potion/fruit_juice/g3`, `potion/fysh_oil/OnUse`, `potion/fysh_oil/g1`,
`potion/fysh_oil/g4`, `potion/gamblers_brew/g3`, `potion/gamblers_brew/g4`,
`potion/gamblers_brew/g6`, `potion/gigantification_potion/g2`,
`potion/glowwater/g4`, `potion/heart_of_iron/g2`, `potion/liquid_bronze/g2`,
`potion/liquid_memories/g4`, `potion/lucky_tonic/g2`, `potion/mazaleths_gift/g3`,
`potion/orobic_acid/OnUse`, `potion/orobic_acid/g2`, `potion/orobic_acid/g5`,
`potion/potion_of_binding/g6`, `potion/potion_shaped_rock/g3`,
`potion/powdered_demise/g2`, `potion/power_potion/g3`, `potion/power_potion/g6`,
`potion/radiant_tincture/g2`, `potion/regen_potion/g3`,
`potion/shackling_potion/g5`, `potion/ship_in_a_bottle/g2`,
`potion/skill_potion/g3`, `potion/skill_potion/g6`, `potion/snecko_oil/OnUse`,
`potion/snecko_oil/g2`, `potion/snecko_oil/g3`, `potion/snecko_oil/g6`,
`potion/soldiers_stew/g4`, `potion/speed_potion/g2`, `potion/stable_serum/g2`,
`potion/strength_potion/OnUse`, `potion/strength_potion/g1`,
`potion/strength_potion/g4`, `potion/swift_potion/g2`,
`potion/touch_of_insanity/g5`, `potion/vulnerable_potion/g3`,
`potion/weak_potion/g3`.

## 3G. Coverage anchors — mechanisms with no prose home

One entry each, and none is a new finding: each is a site of a mechanism
described above that a verdict flip on a neighbouring entry split out of its
family, giving it its own mechanism key. They are named here so
`py audit/tools/gap_queue.py coverage` can locate them. **The fix for each is
its parent mechanism's.**

| mechanism | liveness | parent family |
|---|---|---|
| `creature_card_cmds/step105` | unlabelled | CardSelectCmd (§2A) |
| `hook_dispatch/step6` | unlabelled | listener-registry shape (§2D) |
| `hook_dispatch/step29` | unlabelled | phase passes (`hook_dispatch/G3`) |
| `power/calamity/AfterCardPlayed` | unlabelled | per-`CardPlay` bracket (`hook_dispatch/G4`) |
| `power/illusion/AfterDeath` | unlabelled | death prevention (`power/_death_prevention_branch`) |
| `power/illusion/ShouldCreatureBeRemovedFromCombatAfterDeath` | unlabelled | death prevention |
| `power/painful_stabs/g1` | dormant | single-unit power finding (§3A) |
| `power/skittish/AfterSideTurnEnd` | unlabelled | side-turn slot (`power/_side_turn_slot`) |
| `power/tender/AfterSideTurnEnd` | dormant | side-turn slot |
| `power/unmovable/ModifyBlockMultiplicative` | unlabelled | the block props hoist (`damage_pipeline/G3`) |
| `power_cmd/N4` | dormant | `power_cmd/step4` + `/step26` (§2E) — guard N4 itself is `faithful`; `step4`'s re-check names it in passing |
| `relic/fragrant_mushroom/AfterObtained` | dormant | `StableShuffle` (`relic/_stable_shuffle`) |
| `relic/iron_club/AfterCardPlayed` | unlabelled | per-`CardPlay` bracket |
| `relic/kusarigama/AfterCardPlayed` | unlabelled | per-`CardPlay` bracket |
| `relic/letter_opener/AfterCardPlayed` | unlabelled | per-`CardPlay` bracket |
| `relic/prayer_wheel/TryModifyRewards` | unlabelled | reward late pass (`relic/_reward_late_pass`) |
| `relic/stone_cracker/AfterRoomEntered` | unlabelled | `StableShuffle` |
| `turn_structure/G7` | dormant | `turn_structure/G16` (§2C) — the `EndOfTurnCleanup` half closed round 5; `step63`'s live half is the `AfterFlush` gap filed at `/G16`'s `sites` line |


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
| Any conformance replay through a card-selection / grid screen | `creature_card_cmds/N10`, `/step104`  |
| Any conformance replay containing an in-combat transform | `creature_card_cmds/step55`  |
| Any reshuffle in a replay where Perfect Fit is enchanted; a 2nd repositioning `on_shuffle` listener | `creature_card_cmds/G10`  |
| Porting **BufferPower** | `damage_pipeline/G2`, `hook_dispatch/G3`  |
| Porting **Malaise** or **Resonance** (negative-Strength appliers) | `power_cmd/G1`, `/G2`  |
| Porting **Unceasing Top** | `turn_structure/G16`  |
| Porting **SovereignBlade**, **Hoarder** or **SoulFysh** (combat-pile watchers) | `creature_card_cmds/G8`  |
| Porting **Hexed**'s `AfterCardEnteredCombat` | `hook_dispatch/G6` (needs `/G1` too)  |
| Porting **SlumberingEssence** or **WellLaidPlansPower** (`BeforeFlush`); **Bookmark** (`AfterFlush`) | `turn_structure/step55`, `/G4`  |
| Porting **any Sly card** | `creature_card_cmds/step51` (+ step 50's ordering)  |
| Porting **DoomPower** or **HailstormPower** onto the enemy-side `BeforeSideTurnEnd` | `turn_structure/G11`  |
| Porting **NoEnergyGainPower**'s `AfterModifyingEnergyGain`, or **BowlerHat**/**Ectoplasm**'s `AfterModifyingGoldGained` | `damage_pipeline/G2`  |
| Porting **PaleBlueDotPower**, or any gameplay `AfterModifyingHandDraw` | `turn_structure/step20`  |
| Un-stubbing **Dragon Fruit** or **Lucky Fysh** (both ported, both inert) | `creature_card_cmds/G12`, `/G8`  |
| Porting any of the **11 unclaimed C# monster hook overrides** (table below) | `hook_dispatch/G5`  |
| Porting a monster with a **repeated state id** (`Fogmog.cs:44-45` is the near-miss) | `monster_state_machine/G8`  |
| A C# monster added with **`AddBranch(state, 0)`**, or a non-dyadic branch weight | `monster_state_machine/G7`  |
| Wiring **`Inklet.cs:69`'s INIT_RAND**, or porting Inklet / PhrogParasite onto `MachineMonster` | `monster_state_machine/G2`  |
| Porting any `CardModel` with a **run-level hook** (`AfterRoomEntered`, `AfterRewardTaken`, `ShouldAddToDeck`) | `hook_dispatch/N5`, `creature_card_cmds/N3`  |
| A listener that **removes another listener mid-dispatch** | `hook_dispatch/G7`  |
| A **card hook that reads state another card's hook writes** | `hook_dispatch/G1`  |
| A **second implementer** of `ShouldForcePotionReward` / `ShouldAllowFreeTravel` | `hook_dispatch/step37`  |
| Any `AfterCurrentHpChanged` listener that **reads the amount** | `creature_card_cmds/G5`  |
| A model overriding **`BeforeBlockGained`** (zero overrides game-wide today) | `creature_card_cmds/step12`  |
| Porting a **multi-card transform** | `creature_card_cmds/step56`  |
| Porting a card that **plays more than one card from the draw pile** | `creature_card_cmds/step99`, `/N9`  |
| Two appliers of the same **`InstancedPerApplier`** power in one combat | `power_cmd/G5`  |
| A **third `modify_power_amount` listener**, or Unsettling Lamp / Ruined Helmet widening | `power_cmd/G3`  |
| An **`AfterCombatVictory`-only** listener with an unconditional effect; any `on_combat_end` effect that outlives the combat | `turn_structure/G10`  |
| The first **side-effecting** `should_reset_energy` or `modify_max_energy` | `turn_structure/step17`  |
| A **new multi-hit / multi-target effect** that forgets the per-hit death check | `damage_pipeline/G5`  |
| Porting a second `on_damage_dealt` power | `damage_pipeline/G6`, `/step17.4`  |

## B. Content-tier triggers

| trigger — the unported thing | wakes |
|---|---|
| **Fixing `power/_death_prevention_branch`** — the prevention arm stops flooring at 1 HP | `card/_is_dead_early_return` (5 cards), and it removes the accidental cover for two of `creature_card_cmds/step8c`'s five powers |
| The first cost reader that distinguishes a `-1` base cost from `0`, or any cost modifier applied to an unplayable card and read back | `card/_unplayable_cost` (29 cards) |
| Any reader of a `PowerStackType.Single` power's `Amount`, or any content that applies one twice in a combat | `power/_stack_type_single` (16 powers) |
| A power that holds combat open **without** also preventing a death or adding a creature | `creature_card_cmds/step8c` |
| A second applier of the same `InstancedPerApplier` power in one combat — the content-tier population is 11 powers, not the 2 the seam recorded | `power_cmd/G5` |
| Porting a reachable applier for **Imbalanced** or **Paper Cuts** | `power/_after_damage_given_substitution` |
| Porting the **Circlet** relic, or any content that drains a whole rarity deque inside one run | `event/EV-11` |
| **Training against the sim at all** — this one is not dormant, it is live in every run and dormant only against the game | `card/_printed_vars` (23 cards, via `sts2_rl/full_env.py:488`) |
| Writing the **potion** audit stream | everything in [What this queue does NOT cover](#what-this-queue-does-not-cover) — the last unaudited kind |
| Porting **Flyconid** onto `MachineMonster` (the codebase's preferred convention) | `monster_state_machine/G7`; the port is faithful today and the machinery raises where C# limps |
| A **second Dampen applier**, or two Magi Knights in one encounter | `monster/magi_knight/g1` |
| Any **retained corpse** on the Glory enemy side (an Illusion / Reattach / Adaptable holder) | `monster/_retained_corpse_in_scan` |
| Porting **Regalite**, **RocketPunch**, **ArsenalPower**, **PillarOfCreationPower**, **SmokestackPower** or **TrashToTreasurePower** (the other six `AfterCardGeneratedForCombat` implementers — Aeonglass is ported and its dispatch sites are wired) | `monster/aeonglass/AfterCardGeneratedForCombat` (closed 2026-07-30; listed as the pattern to crib from) |
| Giving `Intent` a **count field**, or any consumer that reads one | `monster/_intent_count_lost` |


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

Rule-3 signals that are still true of the records on disk: a gap whose text
contradicts another record's, or its own. This class has caught real bugs, so
it is tracked; each row is **reported, not edited**, and belongs to the stream
that owns the record.

- **`hook_dispatch/G7`'s executed evidence is from a stale tree.** It records the
  stale-listener plugin run as "the whole suite (2476 passed / 30 xfailed) and
  191,270 instrumented listener calls". The suite is thousands of tests larger
  now. The conclusion may still hold — the record says the run is reproducible
  from the committed tree — but **re-run it before relying on the "only one hit"
  claim**.
- **`monster_probes_b06.py`'s `probe_wither()` greps literally for
  `WitherCard(` and cannot see `make_card()`-style dynamic construction**
  (found 2026-07-30 closing `monster/aeonglass/AfterCardGeneratedForCombat`:
  the probe's "NOT LIVE, executed" verdict missed the Entropy-transform
  Wither route, which was already reachable). Any other dormancy verdict
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
  `Aeonglass.AfterCardGeneratedForCombat` — Tier 2's Aeonglass entry. PROMPT.md
  class 20 applied to a property.
- **`monster_state_machine/G7b`'s dormancy does not cover its own reachable
  case.** It was labelled dormant on a fuzz of 82 *machines*; Flyconid is
  hand-rolled, so the fuzz never saw it, and Flyconid's `RAND` reaches an
  all-zero weight vector on ported act-1 content on all five probe seeds. The
  port is faithful; the sim *machinery* raises. **Porting Flyconid onto
  `MachineMonster` — the convention this codebase prefers — would crash the run.**
- **Four relic records assert a deleted scope clause as a live premise.**
  `relic/alchemical_coffer`, `relic/lost_coffer`, `relic/phial_holster` and
  `relic/potion_belt` each carry, verbatim: "POTION IS NOT AN AUDITED KIND —
  there is no `potion` roster kind and no `audit/records/potion/`." Both halves
  are false. Distinguish these from the ten records (`card/alchemize`,
  `power/{buffer,clarity,demise,flex_potion,gigantification,radiance,regen,shackling_potion,speed_potion}`)
  that quote the clause as explicit "RE-VERDICTED … has been DELETED" history:
  that is correct and should stay.
- **28 `extra_sources` hashes should never have been written, in 27 records owned
  by three streams.** `citation_check.py` declares
  `_NEVER_HASHED = ("audit/tools/", "test/")` — the pipeline's own machinery and
  its pins are cited but not hashed, because a broken pin fails loudly on its own
  — and `backfill_sources.py` had no such exclusion. The consequence is false
  staleness: a record hashing `test/test_hook_order.py` goes stale whenever any
  pin is added anywhere in that file. The tool is fixed; **the prune is still
  owed for all 27** and is the durable fix, because a re-pin only buys time until
  the next pin lands. Each stream runs
  `py audit/tools/backfill_sources.py --prune --no-add --kind <kind>`:

  | stream | records | pinned path |
  |---|---|---|
  | `card` (18) | `anointed`, `beat_down`, `discovery`, `distraction`, `havoc`, `hidden_gem`, `jack_of_all_trades`, `jackpot`, `metamorphosis`, `rip_and_tear`, `seeker_strike`, `splash`, `volley` | `test/test_rng_tripwire.py` |
  | | `feel_no_pain`, `mad_science` | `test/test_shared_enchantments.py` |
  | | `feel_no_pain` | `test/test_ironclad_cards.py` |
  | | `apotheosis`, `entrench`, `primal_force` | `test/test_hook_order.py` |
  | `relic` (8) | `mystic_lighter`, `permafrost` | `audit/tools/relic_probes.py` |
  | | `horn_cleat`, `intimidating_helmet`, `iron_club`, `joss_paper`, `orichalcum`, `pen_nib` | `test/test_hook_order.py` |
  | `power` (1) | `surrounded` | `test/test_hive.py` |

**The structural lesson, worth more than the rows.** Every contradiction ever
found here lived at a **shared engine gate** — a props filter, a phase pass, a
dispatcher hoist — and never at a unit's own arithmetic. Per-unit records are
reliable about their own numbers and unreliable about whether the shared
machinery beneath them changes the answer, because each unit re-derives that
machinery's reachability from its own vantage point.

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
from the records, and both must be run after any edit to it.** `coverage`
asserts that every mechanism key and every one of the 646 entries is locatable
here — a seam entry by its own id or by its mechanism plus its local id
(`/step31`), a content entry by its mechanism, since the ids cannot each be
spelled out in prose and `mechanisms` regenerates any group's site list on
demand. `cite-check` asserts that every `file:line` in the authored prose
resolves in `sts2_rl/` or in the decompiled game tree; Tier 3's summaries have
their line numbers stripped precisely so that check stays a check on this
document rather than a re-validation of the record excerpts.

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

