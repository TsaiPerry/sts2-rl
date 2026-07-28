# Gap queue — every audited record, aggregated

> ## ⚠ 2026-07-28 — LEDGER RECONCILED AGAINST THE CODE, AND ALL PINS ARE GREEN.
>
> Two things happened after the Tier 1 campaign; read both before trusting a
> present-tense sentence anywhere below.
>
> **1. The ledger was one pass behind the engine, and has been reconciled.** The
> campaign's per-record verdict re-derivation ran *concurrently with* its own last
> round of code fixes, so entries were still recorded `gap` that the code had
> already closed. All **207** then-LIVE mechanisms (368 entries) were re-derived
> against today's code, and every proposed clear was attacked by two adversarial
> lenses before being applied:
>
> | | |
> |---|---|
> | entries re-derived | 368 |
> | still a real gap | 316 |
> | proposed clears | 52 |
> | applied | 44 |
> | **refuted, kept as gaps with corrected text** | **8** |
>
> **2. The six remaining `strict=True` xfail pins are fixed** — `power_cmd/G1`,
> `monster_state_machine/G3`, `/G7`, `/G8`, and the two `hook_dispatch/G8` tests.
> `test/test_hook_order.py` is 51 passed, 0 xfailed.
>
> **The eight refutations are the reason this section exists.** Several corrected
> a *narrowing* rather than a fix (`relic/tungsten_rod/g3` — the sim has no
> BeforeOsty invocation at all, not merely a misplaced Boot); `enchantment/
> slither/EG2` and `/perfect_fit/EG2` found a second divergence inside the same C#
> method (`create_clone` still rebuilds from the class, so `CardModel.cs:1202`'s
> `_energyCost = _energyCost?.Clone(this)` is unported and a copy of a Slither card
> loses its rolled cost).
>
> **One refutation caught a regression this very pass had introduced, and the pin
> was the cause.** `test_no_listener_runs_after_the_combat_starts_ending` asserted
> that `Hook.AfterCardPlayed` reaches nobody once the killing blow has landed. The
> C# says the opposite: `Hook.AfterCardPlayed` (`Hook.cs:278-294`) iterates
> `IterateHookListeners()` **directly**, and `Hook.cs:275-276` states why —
> *"Dispatched directly, not through the IterateCombatHookListeners guard: it
> completes resolution of the card that caused the kill."* Its only gate is
> `IsInProgress` (`CardModel.cs:1957`), still true between the blow and the
> teardown. Gating that site on `is_over_or_ending` suppressed **every**
> `AfterCardPlayed` listener on the winning card play — including Game Piece's
> `DrawCmd.draw`, which can force a reshuffle and consume RNG, so it was
> stream-observable for the conformance exporter. Reverted; the pin is rewritten as
> `test_after_card_played_still_fires_on_the_killing_blow`. **This is the fourth
> wrong pin this project has found, and the rule holds: when a pin and the C#
> disagree, the C# wins.** Note the inverse mismatch it exposed, still open:
> `Hook.BeforeCardPlayed` (`Hook.cs:263-270`) **is** gated in C# and is not gated
> in the sim.
>
> `hook_dispatch/G8` is therefore **not** closed. One of its 20 sites is
> (`creature_card_cmds/step103b`, CardSelectCmd's screens, via the new
> `CombatState.is_over_or_ending`). The mechanism needs a fresh witness: **72 of
> Hook.cs's 146 dispatchers go through `IterateCombatHookListeners` and 73 bypass
> it on purpose**, so the sim-side gate belongs in `HookSystem._each` scoped to
> exactly those 72 — and `AfterCardPlayed` is emphatically not one of them.
>
> ## ⚠ TIER 1 IS CLOSED (2026-07-27/28). READ THIS BEFORE THE BODY.
>
> **Sections 1A–1F below describe work that has been DONE.** They are kept as the
> record of what the divergences were and how they were found — the `divergence`,
> `observable` and `radius` fields are still the best writeup of each mechanism —
> but they are **no longer a work list**. The numbers in the Summary and in every
> section header have been regenerated; the *prose* in Tier 1 has not been
> rewritten entry by entry, so where an entry says "the sim does X" in the present
> tense, read it as "the sim did X before this was fixed".
>
> What actually changed, measured:
>
> | | before | after |
> |---|---|---|
> | gap entries | 1612 | **1160** |
> | distinct mechanisms | 856 | **749** |
> | mechanisms with a live entry | 319 | **207** |
> | strict `xfail` pins | 36 | **6** |
> | suite | 2518 passed | **2857 passed** |
>
> **All 6 remaining pins are Tier 2 (dormant) mechanisms** — `power_cmd/G1`,
> `hook_dispatch/G8` (two tests), `monster_state_machine/G3`, `/G7`, `/G8`. Zero
> Tier 1 pins remain. Per-kind live entries fell to 0 for `card`, `event` and
> `enchantment`, and to 3 / 1 / 1 for `monster` / `power` / `relic`.
>
> **`potion` is the exception and the honest caveat:** its live count did not
> move, because 51 of its entries are the single shared guard
> `potion/_effect_bracket` — one missing re-entrancy bracket carried once per
> unit — which was never in Tier 1. `potion/_use_pipeline`, which WAS, is closed.
>
> **Not everything in Tier 1 closed completely.** `relic/_auto_keep`,
> part of `relic/_stub`, `potion/_min_select_zero` and `potion/foul_potion`'s
> Fake Merchant arm are partially closed; each of those entries now carries a
> narrowed `issue` naming exactly what remains. `docs/superpowers/plans/
> 2026-07-27-tier1-gap-fixes.md` has the full outcome, including three pins that
> were themselves WRONG and were corrected, two latent wrong-stream bugs the
> fixes unmasked (Stampede and Havoc, both caught by `test_rng_tripwire`), one
> regression the fix campaign introduced and the adversarial audit caught
> (Diamond Diadem lost its props gate), and one hard crash the same audit found
> (an enchantment on a mid-combat card copy was never registered).
>
> **The verdicts were re-derived per record against the code, then adversarially
> audited.** That audit returned `sound: false` for five of the eight kinds and
> named 18 false clears; all 18 were verified and reverted to `gap` before
> `harness.py rehash` was run. `audit_status.py` now reports **0 stale, 0
> invalid** across all 846 records.

Every `"verdict": "gap"` entry from `audit/records/**`, de-duplicated **by
mechanism**, ordered for work, and left **queued, not fixed** (Perry's standing
decision). The audits found far more than recorded-run convergence ever
surfaced; this file is the single actionable view of it.

Generated, not transcribed. Regenerate the numbers with:

```
py audit/tools/gap_queue.py counts        # the summary header below
py audit/tools/gap_queue.py mechanisms    # the grouping, largest first
py audit/tools/gap_queue.py pins          # the strict xfails and what they pin
py audit/tools/gap_queue.py unpinned      # mechanisms with no pin
py audit/tools/gap_queue.py coverage      # every mechanism/entry appears here
py audit/tools/gap_queue.py cite-check    # every file:line here resolves
```

**Last regenerated 2026-07-27, with the `monster` tier (109 units, 45 gap
entries, 28 live) and the `potion` tier (51 units, 152 gap entries, 83 live).**
**All seven content kinds and all six seams are now aggregated here** — the
first time that has been true.

Do not trust a count stated in prose anywhere in this project — including this
file. Re-run `counts`.

## What this queue does NOT cover

**Every content kind is audited and aggregated. One unit is not, by design.**

| kind | units | records | in this queue |
|---|---|---|---|
| seam (engine) | 6 seams | 6 | yes |
| power | 138 | 138 | yes |
| card | 203 | 202 | yes — `card/sweep` is sim-only and has no record |
| event | 65 | 65 | yes |
| enchantment | 17 | 17 | yes |
| relic | 258 | 258 | yes — **merged 2026-07-26** |
| monster | 109 | 109 | yes — **merged 2026-07-27** |
| **potion** | **51** | **51** | yes — **merged 2026-07-27** |

What this queue still cannot cover is the residue named below: emergent
interactions between two individually-faithful units, and any mechanism that
lives somewhere no record reaches. **One such place is now known and named:**
`PotionModel` is a framework root, so `harness.MODEL_ROOT_CLASSES` stops
base-class following there on the promise that a seam covers it — and **no seam
does**. `PotionModel.OnUseWrapper` is the entire use path for all 51 potions and
was verdicted nowhere until the potion tier recorded it as one guard per record
(entry 46 below, `potion/_use_pipeline`, 51 sites). Check the other twelve roots
in `MODEL_ROOT_CLASSES` against `SEAMS` before assuming this is the only one.

**The tooling did not see this tier for a day, and that is worth recording as a
queue-integrity fact.** `gap_queue.py` keeps its own `CONTENT_KINDS`, so while
51 finished records sat on disk `counts` printed `NOT AUDITED : potion (51 C#
units)` and `audit_status.py` — which derives kinds from the harness — reported
them audited. 152 gap entries were missing from this file and nothing failed:
`coverage` and `cite-check` printed their complaints and exited 0, because
`main()` discarded the command's return value. Both are fixed, and
`test/test_audit_status.py::TestQueueGeneratorCoversEveryKind` pins the kind
lists together.

**The 11 unclaimed monster hook overrides are now claimed.** They were listed
here as a hole: 11 C# monster models override an `AbstractModel` hook and no
seam claimed them (`py audit/tools/dormancy_probes.py cs-monster-hooks`). The
monster tier audited all 11. **Ten are presentation** — a music parameter, a
barks line, a texture assignment or an animation call, the `KinPriest` N6 shape
repeating far more often than anyone expected — and **one is a live gap**,
`Queen.AfterDeath` (entry 67), which hides three mechanical statements inside
the same presentation shell. `Aeonglass.AfterCardGeneratedForCombat` (entry
148) is mechanical too but dormant. The lesson recorded for the next reader is
that N6 is a **prior, not a rule**: nine overrides that look mechanical are
not, and reading each one to the end is what separates them.

**`potion` is a new row for an old problem, and it is worth understanding why
it appears here rather than having always been here.** Until 2026-07-26 the
shared contract said "Out of scope everywhere: potions (deferred by Perry)", so
potions were not an unaudited kind — they were an *excluded* one, which meant
nothing counted them and nothing reported them missing. Perry has replaced that
clause ("don't ignore potions anymore") and `potion` is now an ordinary kind:
51 sim units, `audit/records/potion/`, `harness.py roster potion` resolves all
51 against `src/Core/Models/Potions`.

The exclusion did damage in both directions while it stood, which is the
argument for never expressing scope as an exclusion again:

- **It manufactured a rule-3 break.** Ten entries across the `card` and `power`
  tiers waived real behaviour on it — including the whole of `card/alchemize`,
  a ported Colorless card whose entire effect is potion procurement — while the
  `relic` tier filed **45** potion-mechanic gaps, 27 of them LIVE. One
  mechanism, two answers, caused by the contract itself.
- **It protected a false claim.** `damage_pipeline` N4 waived the two-phase
  `ShouldDie` ordering on the grounds that Fairy in a Bottle was out of scope.
  The potion is **ported**, at `sts2_rl/potions.py:1242`, with a real
  `should_die` — so the waiver was hiding a live gap, not deferring a decision.
  It is now entry 57.

Unaudited is a fact the tools report. Out-of-scope was a claim that hid things.

**What the relic tier's arrival did to the rest of the queue** is the strongest
evidence available that this "nobody looked" caveat is not boilerplate. Adding
one kind did not just append its own gaps:

- `power/diamond_diadem` was the standing blocked-on-relic marker — it had been
  re-verdicted `waiver` → `gap` because its rationale delegated to
  `audit/records/relic/diamond_diadem`, which did not exist. It exists now, and
  reaches the same `gap` on its own executed witness. **Unblocked.**
- The relic tier's own review found **`UnmovablePower` × `Entrench`**, a LIVE
  gap in the *power* and *seam* tiers that neither had recorded: `power/unmovable`
  verdicted it `faithful` on a misread guard, and `creature_card_cmds` G1's
  census of affected listeners omitted the power. Both are corrected here. It is
  the third time on this project that two records disagreeing about one
  mechanism meant **neither was right**, and the first found across content tiers.
- Two seam records were corrected by the relic stream in flight —
  `hook_dispatch`'s `ShouldDie` guard (`waiver` → `gap`, because FairyInABottle
  *is* ported) and `turn_structure`'s Whispering Earring auto-play guard
  (`dormant` → LIVE, because Crossbow refutes the "only turn-start auto-players"
  claim). Both now carry queue entries that did not exist before the merge.

**And it happened again with `monster`, in both directions.** Adding the kind
corrected two entries that were already here and one that was not:

- `power/sandpit`'s guard "Frantic Escape as the counterplay" is recorded
  `faithful`; it compared counts and pile types but not `CardPilePosition`, and
  so cleared what is now **entry 71**, a live 3-vs-6-draw gap.
- `power/withering_presence` cites `WitheringPresencePower.cs:37` as where
  generated Withers are matched; that line is inside `ExtraHoverTips`, a
  hover-tip preview. The real mechanism is entry 148.
- `monster_state_machine` **G7b's dormancy does not cover its own reachable
  case**. Flyconid's branch reaches an all-zero weight vector on ported act-1
  content on all five probe seeds; C# burns one `NextFloat(0)` and returns
  branch 0, and the hand-rolled port matches it — but the sim **machinery**
  raises. G7b was labelled dormant on a fuzz of 82 *machines*, and Flyconid is
  hand-rolled, so the fuzz never saw it. **Porting Flyconid onto
  `MachineMonster` — the convention the codebase prefers — would crash the
  run.** See entry 130.

It also settled a three-way disagreement about one mechanism in which **neither
confident answer was right**: `ShouldDisappearFromDoom` drew a dormant `gap`
from one batch ("the creature is NOT removed when Doom's kill sweep fires") and
`faithful` from another ("ten sites, every one a declaration — the game never
reads it"). There **is** exactly one reader, `DoomPower.cs:90`, so the second is
false; but it sits inside `PlayVfx` and feeds only `StartDoomAnim` and a
`Cmd.Wait` timing branch, while `DoomKill`'s `CreatureCmd.Kill` is unconditional
and outside it, so the first is false too. Resolved to `waiver`, presentation,
at all nine overriding models — which **removed two false dormant gaps from
this queue**. The transferable lesson is to resolve a grep hit to its enclosing
**member**, not to count matches.

The same is now to be expected of `potion`.

`py audit/tools/audit_status.py` is the authority on coverage; this table is a
transcription of it and can go stale.

## Summary

| | |
|---|---|
| gap entries across all 846 records | **1117** |
| — labelled LIVE (own text, or the explicit `live` field) | 272 |
| — labelled DORMANT (own text, or the explicit `live` field) | 537 |
| — unlabelled (inherit their mechanism's liveness) | 308 |
| **distinct mechanisms** | **722** |
| — with at least one live site | **179** |
| — dormant at every site | 543 |
| mechanisms pinned by a `strict=True` xfail | **0** |
| mechanisms unpinned | 722 |
| `strict=True` xfails in `test/test_hook_order.py` | **0** |

Regenerated **2026-07-28**, after the ledger-vs-code reconciliation and the
remaining-pin pass (below). Before it, that day: 1160 / 306 / 541 / 313 / 749 /
207 / 542 / 5 / 744 / 6. Before the Tier 1 fix campaign: 1612 / 658 / 568 / 386 /
856 / 319 / 537 / 32 / 824 / 36.

**The xfail count is 0 for the first time.** That is not "no gaps left" — it is
"every mechanism that had an acceptance test now passes it". 722 mechanisms are
unpinned, which is the coverage problem `audit/README.md` has flagged since the
seam tier: a gap with no pin cannot prove its own fix. Adding a pin as a gap is
worked remains the cheapest way to stop that rotting.

Per kind (records / gap entries / mechanisms anchored there / entries labelled live):

| kind | records | entries | mechanisms | live |
|---|---|---|---|---|
| `seam` | 6 | 166 | 83 | 5 |
| `power` | 138 | 224 | 170 | 27 |
| `card` | 202 | 147 | 93 | 49 |
| `event` | 65 | 40 | 21 | 24 |
| `enchantment` | 17 | 6 | 4 | 3 |
| `relic` | 258 | 369 | 323 | 103 |
| `monster` | 109 | 25 | 10 | 6 |
| `potion` | 51 | 140 | 18 | 55 |

`enchantment` moved most (14 → 6 entries): seven of the nine `EG2` sites cleared
once `CardPileCmd._enter_combat` began registering `card.enchantment`, and the
two that did not are the two an adversarial pass refuted — see below.

The `power` and `card` rows moved without the monster merge touching them (268→270 and 149→152 entries): those tiers gained entries after this file was last regenerated, which is what the header means by *do not trust a count stated in prose anywhere in this project — re-run `counts`*.

**Read the `potion` row carefully: 152 entries over 51 records is the highest
entries-per-record ratio in the table, and it is not 152 findings.** 102 of them
are two shared guards (`potion/_use_pipeline`, `potion/_effect_bracket`) carried
once per unit because `PotionModel` is a framework root with no seam — see
[What this queue does NOT cover](#what-this-queue-does-not-cover). The tier's
real shape is **24 mechanisms**, 8 of which have more than one site and 17 of
which are single-unit findings.

**Four pins are content-anchored for the first time** (`TestPotionContentPins`),
which is why the xfail count moved 32→36 while pinned mechanisms moved only
31→32: three of the four pin potion mechanisms that had no pin, and the fourth
pins `power/_should_allow_hitting`, which was already in the queue as unpinned.

Per seam record, which is how the engine tier was originally reported:

| record | entries | mechanisms | live |
|---|---|---|---|
| `damage_pipeline` | 15 | 8 | 1 |
| `power_cmd` | 24 | 7 | 1 |
| `creature_card_cmds` | 75 | 34 | 9 |
| `turn_structure` | 67 | 24 | 19 |
| `hook_dispatch` | 30 | 11 | 13 |
| `monster_state_machine` | 16 | 9 | 4 |

**1460 entries are not 1460 jobs, and the ratio is worse than it looks.** The
relic tier is the sharpest case: **620 entries collapse to 404 mechanisms**, and
16 recurring families carry 227 of those 620 between them. Five of the sixteen
resolve to a mechanism a *seam* record already owns, which is binding rule 3
doing its job across kinds rather than within one.

| mechanism | sites | what collapses |
|---|---|---|
| `potion/_use_pipeline` | 51 | **one un-seamed framework root**, recorded once per potion |
| `potion/_effect_bracket` | 51 | one missing re-entrancy bracket, recorded once per potion |
| `hook_dispatch/G4` | 36 | one loop boundary, now recorded across **4 kinds** |
| `relic/_is_allowed` | 34 | **one missing `Relic.is_allowed` member**, on 19 relics |
| `power/_side_turn_slot` | 29 | one wiring bug in `combat.py`, recorded on 29 powers |
| `card/_unplayable_cost` | 29 | one value-model divergence, on 29 curses/statuses |
| `event/EV-3` | 28 | one RNG-plumbing decision, recorded on 28 events |
| `hook_dispatch/G3` | 24 | the missing phase passes, now across 3 kinds |
| `relic/_reward_late_pass` | 24 | one collapsed two-pass reward dispatch, on 15 relics |
| `card/_printed_vars` | 23 | one `_init_vars` convention, recorded on 23 cards |
| `relic/_stub` | 23 | 21 relics ported as no-ops on premises that are now false |
| `hook_dispatch/G8` | 22 | one missing dispatch gate, recorded on 3 seams |
| `relic/_off_stream_draw` | 20 | draws on the legacy shared rng, on 15 relics |
| `relic/_auto_keep` | 19 | one force-grant house rule, on 15 relics |
| `enchantment/EG2` | 17 | **one** `CreateClone` behaviour, on all 17 enchantments |
| `event/EV-1` | 17 | one `run.lose_hp` shape, recorded on 17 events |
| `relic/_combat_reset` | 16 | **one missing combat-boundary reset**, on 13 relics |
| `power/_stack_type_single` | 16 | one misreading of `PowerStackType.Single`, on 16 powers |
| `power/_death_prevention_branch` | 15 | one wrong death branch, now across **2 kinds** (+5 monster sites) |
| `relic/_stable_shuffle` | 14 | one `StableShuffle` contract, on 7 relics |
| `turn_structure/G13` | 13 | one missing win check, now across 2 kinds |
| `damage_pipeline/G3` | 10 | the props hoist, now across 3 kinds |

Two of those relic families are worth calling out because their collapse ratio
is the whole point: `relic/_is_allowed` is **34 recorded sites and one missing
base-class member**, and `relic/_combat_reset` is 16 sites of a single missing
reset dispatch — the one whose absence makes combat 2 open at Strength −3.

The collapse is even sharper than the entry count suggests, because the
content tiers also de-duplicate their **non-gap** verdicts the same way: the
"the applier is a potion, and the potion kind has no audit tier" **waiver** is
carried verbatim on 7 power records. It is not in this queue — a waiver is not
a gap — but it is the same one-mechanism-many-records shape, and a reader
counting records rather than mechanisms will over-count everywhere.

## How to read an entry

```
### N. <mechanism id>  — <one-line name>            [LIVE|DORMANT] [pinned|unpinned]
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

Sorted by **seed-convergence impact** first, then blast radius, then fix cost;
live above dormant throughout. Convergence impact is graded:

- **A — stream desync.** Changes an RNG draw count or the stream a draw comes
  from. Every later draw in the run shifts; a replay stops converging outright.
- **B — state divergence.** Changes a damage/block/HP number, a hand, a pile or
  a deck entry. The next conformance assert fires.
- **C — bookkeeping only.** Hook order or event identity with no numeric effect
  on currently-ported content.

The document has three tiers:

1. **[Tier 1 — live gaps](#tier-1--live-gaps)**, written out in full. These
   are the ones with a site the records label LIVE on already-ported content.
2. **[Tier 2 — dormant gaps](#tier-2--dormant-gaps)**, written out in full,
   grouped by the machinery they share.
3. **[Tier 3 — the long tail](#tier-3--the-long-tail)**, one row per remaining
   mechanism. These are single-site, single-unit findings: real, recorded,
   verified, and cheaper to read straight out of the record than to restate.
   The row gives the id, the liveness and the record's own lead clause.

`py audit/tools/gap_queue.py coverage` asserts that every mechanism and every
one of the 1460 entries is locatable here, so the tail cannot silently shrink.

---

# Tier 1 — live gaps

The mechanisms with at least one site the records label LIVE on already-ported
content. Graded A before B; within a grade, blast radius then fix cost.

## 1A. Grade A — stream desync

A wrong draw count or a wrong stream. These are the ones that stop a replay
converging outright, which is the work this pipeline exists to unblock.

### 1. `event/EV-3` — the per-event `Rng` replaced by the shared run stream  [LIVE] [**unpinned**]

- **sites** 28 entries on 28 event records (`aroma_of_chaos`, `battleworn_dummy`,
  `dense_vegetation`, `doll_room`, `doors_of_light_and_dark`, `endless_conveyor`,
  `fake_merchant`, `infested_automaton`, `jungle_maze_adventure` ×2, `lost_wisp`,
  `luminous_choir`, `morphic_grove`, `punch_off`, `ranwid_the_elder`,
  `reflections`, `relic_trader`, `room_full_of_cheese`, `slippery_bridge`,
  `stone_of_all_time`, `sunken_statue`, `sunken_treasury`, `symbiote`,
  `the_future_of_potions`, `this_or_that`, `trash_heap`, `trial`,
  `welcome_to_wongos`). **The single largest live mechanism in the queue.**
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

### 2. `monster_state_machine/G1` — `AddBranch` integer arguments read as weights  [LIVE] [pinned]

- **sites** `monster_state_machine/step13` (1 entry; the mismatch probe covers 12 resolved C#↔sim module pairs).
- **impact** A — the roll distribution itself differs, so `combat_rng.monster_ai` desyncs.
- **divergence** C#'s `AddBranch` puts *cooldown-or-maxRepeats* in positional
  slot 2 across its ten overloads (`RandomBranchState.cs:46-113`); the sim's
  `add_branch` puts *weight* there, so a positional transliteration turns a
  repeat limit into a weight.
- **observable** Five of the twelve resolved pairs misread it —
  `FlailKnight.cs:50,51` (maxRepeats 2) → `sts2_rl/monsters/hive/flail_knight.py:51,52`
  (`weight=2.0`, `CAN_REPEAT_FOREVER`); `HunterKiller.cs:43` →
  `sts2_rl/monsters/hive/hunter_killer.py:45`; `ScrollOfBiting.cs:90` →
  `sts2_rl/monsters/glory/scroll_of_biting.py:65`; `SpectralKnight.cs:52` →
  `sts2_rl/monsters/glory/knights.py:111`; `FakeMerchantMonster.cs:58`
  (cooldown 3) → `sts2_rl/monsters/fake_merchant.py:72-75`
  (`weight=_ENRAGE_WEIGHT` = 3.0, no cooldown — the misreading is written into
  the docstring at `fake_merchant.py:40`). Probe `distribution` (100000 rolls,
  seed 7) shows the sim's and the game's move distributions differing.
- **pin** `test/test_hook_order.py::TestMonsterStateMachineOrder::test_addbranch_int_args_are_repeat_limits_not_weights`.
- **fix** Per monster module, re-read the C# call and re-express: `AddBranch(state, N)`
  with `CanRepeatXTimes` is `max_times=N`, with the default repeat type it is a
  cooldown. The sim's `add_branch` already takes `max_times`; a cooldown needs
  either the `cooldown` parameter or the equivalent
  `MoveRepeatType.CANNOT_REPEAT`-plus-counter shape. Failing test asserts the
  branch's *selection frequency* over a fixed seed matches the C# semantics
  (e.g. Flail Knight cannot pick `FLAIL` a third consecutive time).
- **radius** This is the bug class whose earlier fix greened a conformance seed
  (the TwigSlimeM + Flyconid fix that closed 89U's act-0 player-HP delta — that
  attribution is project history, not something the record states); the same
  misreading survives in five more monsters. Content units: Flail Knight,
  Hunter Killer, Scroll of Biting,
  Spectral Knight (the `knights` elite), Fake Merchant. Related but distinct:
  `monster_state_machine/G7` (maxTimes == 0) and `/G8` (construction validation)
  are the other two `AddBranch`-semantics mechanisms.

### 3. `turn_structure/G9` — enemy intents rolled per-move, not in one pass at player-turn start  [LIVE] [**unpinned**]

- **sites** `turn_structure/step2`, `/step11`, `/step33`, `/G9` (4 entries);
  cross-referenced by `monster_state_machine/G6` and `/step11`.
- **impact** A — a proven off-by-one in the `monster_ai` draw count.
- **divergence** `CombatManager.cs:478-484` rolls *every* enemy's next move in
  one pass at the start of the player's turn, in enemy-list order, and skips the
  pass on an extra player turn; the sim advances each monster's own machine
  inside its move (`sts2_rl/monsters/base.py:96-105` `telegraph_next_move`,
  driven from `sts2_rl/combat.py:314-329`).
- **observable** A monster that does not act — stunned — takes **no**
  `monster_ai` draw in the sim and **one** in the game. Executed with a
  one-`LeafSlimeS` encounter and a counting proxy over the `monster_ai`
  accessor: `normal enemy turn: MonsterAi draws = 1`, `STUNNED enemy turn:
  MonsterAi draws = 0`. One stunned enemy round desyncs the stream by exactly
  one draw and every later draw in the combat shifts. Player-reachable:
  `sts2_rl/cards/whistle.py:30-38` (Tanx's Whistle) stuns with no
  `next_move_key`.
- **pin** Deliberately none — "the observable is an RNG-stream draw count, not a
  hook order, and the conformance suite is its natural home". **The single
  highest-value unpinned live gap in the queue.**
- **fix** Move the roll out of the move: give `CombatState` a
  `_roll_enemy_intents()` that walks `self.enemies` in list order at the top of
  the player turn (`combat.py`, alongside the turn-1 setup and the
  `start_turn()` path), have `telegraph_next_move` stop rolling, and skip the
  pass on the extra-turn path (`combat.py:648-652`). The spawn roll stays where
  `CreatureCmd.add` puts it. Failing test: a stunned enemy round consumes
  exactly one `combat_rng.monster_ai` draw (count the stream, as the record's
  probe does) — this belongs in `test/test_conformance_determinism.py` or
  `test/test_rng_tripwire.py` rather than `test_hook_order.py`.
- **radius** Interacts with `monster_state_machine/G4` (stun as a real move —
  the deferred-move re-log is the *other* half of the same stunned-enemy
  scenario) and `/G6` (`FlutterPower` splicing a roll). Anything that changes
  when a monster rolls changes the entire `monster_ai` stream for the run.

### 4. `event/unrest_site/IsAllowed` — a float 70% gate re-indexes the whole event queue  [LIVE] [**unpinned**]

- **sites** `event/unrest_site/IsAllowed` (1 entry); its consequence is proven by
  a second, `faithful`, guard on the same record.
- **impact** A — not one event, the *order* of every later event.
- **divergence** `UnrestSite.cs:26-29` is
  `(decimal)CurrentHp <= (decimal)MaxHp * 0.70m`, exact base-10;
  `sts2_rl/events/unrest_site.py:30` is `run.hp <= run.max_hp * 0.70` in binary
  float, which lands just below the true 70% for some max HP values.
- **observable** Executed (`py audit/tools/event_probes_b.py gate`), sweeping every
  `(max_hp, hp)` pair with `max_hp <= 400`: **7 disagreements, all sim-False /
  game-True**, all at exactly 70% — 90/63, 170/119, 180/126, 330/231, 340/238,
  350/245, 360/252. `90*0.70 == 62.99999999999999` in the sim; `90m*0.70m` is
  exactly `63.00m` in the game. Then the second guard executes the consequence:
  `RoomSet.EnsureNextEventIsValid` (`sts2_rl/rooms.py:441-457`) **increments**
  `events_visited` past every event whose `IsAllowed` fails, so a wrongly-refused
  event does not go missing — it advances the cursor. Driving the queue
  `[unrest_site, doll_room, tea_master, this_or_that]` on a 90/63 run and serving
  three event rooms, **the game serves `[unrest_site, doll_room, tea_master]` and
  the sim serves `[doll_room, tea_master, this_or_that]`**. Every later pick
  shifts by one and the sim reaches in three rooms an event the game would not
  have reached until the fourth. An Ironclad starts at 80 max HP and 90 is one
  Max-HP relic away.
- **pin** Unpinned; the same reasoning as `event/EV-3`.
- **fix** Compare in integers or `decimal`: `run.hp * 100 <= run.max_hp * 70`.
  Sweep the other event gates for the same shape at the same time — this is the
  representation, not the constant, and `0.70m` is the canonical value under the
  shared contract's non-ascension rule. Failing test asserts the seven pairs.
- **radius** Same bug class as `hook_dispatch/G9`'s decimal-vs-float, at an
  *event gate* rather than in the damage pipeline, so it is a separate site and
  not that mechanism's blast radius — the record says so explicitly.

### 5. `event/EV-12` — a Combat-layout event builds its encounter at room entry  [LIVE] [**unpinned**]

- **sites** `event/punch_off/EV-12`, `event/the_lantern_key/EV-12` (2 entries).
- **impact** A — monster HP rolls, on a path the player can decline.
- **divergence** `EventRoom.EnterInternal` calls `GenerateInternalCombatState`
  (`EventRoom.cs:67-71`), which runs `GenerateMonstersWithSlots` — monsters, HP
  rolls and `AfterAddedToRoom` — **when the room is entered**. The sim has no
  room-entry encounter generation at all: `sts2_rl/events/punch_off.py:77-83`
  records `pending_encounter` and `sts2_rl/run.py:1135-1152` builds the monsters
  when the driver runs the fight.
- **observable** Two of them: the draws move, and they move *conditionally*. The
  game burns them unconditionally at entry, so a player who takes the NAB branch
  still consumes them; the sim consumes them only on the FIGHT path, and even
  there at a different point in each stream. Executed
  (`py audit/tools/event_probes_a.py combatlayout`): a parity run entering
  Punch-Off consumes **0 Niche draws on both paths where the game consumes 2**,
  plus 2 encounter-`Rng` `NextInt(2,10)` draws. Punch-Off is an ordinary
  Underdocks event gated only on `TotalFloor >= 6`.
- **pin** Unpinned.
- **fix** Move encounter construction to event-room entry for Combat-layout
  events: build the `pending_encounter` eagerly in the event's room-entry path
  rather than lazily in `run.create_combat`. Failing test asserts the Niche and
  encounter draw counts are equal on the NAB and FIGHT branches.
- **radius** `py audit/tools/event_probes_a.py combatlayout` lists the
  Combat-layout events in the source: `PunchOff.cs:33`, `TheLanternKey.cs:15` and
  `TheArchitect.cs:52` (unported, no sim unit). A desynced Niche stream misprices
  every later monster HP roll, which is the same hole
  [no tier owns](#behaviour-in-no-tiers-scope) as item 3.

### 6. `event/EV-9` — the potion offer draws on the shared run stream, not `PlayerRng.Rewards`  [LIVE] [**unpinned**]

- **sites** `event/the_legends_were_true/EV-9`, `event/wellspring/EV-9`,
  `event/whispering_hollow/EV-9` (3 entries; the source idiom appears at 4 sites).
- **impact** A — a per-player Rewards draw taken off the wrong stream.
- **divergence** Four events share one verbatim three-line idiom —
  `potion = Owner.PlayerRng.Rewards.NextItem(items)` at
  `TheLegendsWereTrue.cs:52-59`, `BattlewornDummy.cs:84-90`,
  `EndlessConveyor.cs:152-158`, `Wellspring.cs:32-38`.
  `sts2_rl/events/the_legends_were_true.py:47` calls `random_potion(self.rng)`.
- **observable** The sim already has the stream — `RunState.rewards_rng` is
  `player_rng.rewards` whenever a parity rng_set exists
  (`sts2_rl/run.py:271-274`) — and `sts2_rl/events/potion_courier.py:55` already
  draws its potion pick off it. Executed
  (`py audit/tools/event_probes_b.py potionoffer`): all four sim sites route
  through `self.rng` / `run.rng` instead.
- **pin** Unpinned.
- **fix** Replace `random_potion(self.rng)` with the `rewards_rng.next_item`
  shape `potion_courier` already uses. Failing test asserts the Rewards stream
  advances by one and the shared stream by zero.
- **radius** **Distinct from `event/EV-3`** and the record says so: these sites
  never touch `base.Rng` at all, so threading the event rng would not fix them.
  Shares the Rewards stream with the relic-rarity roll, which is
  [unaudited](#what-this-queue-does-not-cover).

### 7. `event/EV-7` — `StableShuffle`'s sort key is the sim's lowercase id  [LIVE] [**unpinned**]

- **sites** `event/relic_trader/EV-7` (1 entry; the radius is every
  `stable_shuffle` call site).
- **impact** A — the same draws produce a different permutation.
- **divergence** `ListExtensions.StableShuffle` sorts by the element's natural
  order *first* and then runs Fisher-Yates, so the sort fixes the permutation.
  `sts2_rl/events/relic_trader.py:39-40` sorts on the sim's **lowercase** id
  where the game sorts on the C# name.
- **observable** `_` is `0x5F`: above `A`-`Z` and below `a`-`z`, so for two ids
  sharing a prefix where one continues with `_`, the two orders are **opposite**.
  Executed (`py audit/tools/event_probes.py sortkey`): over the sim's 258 relic
  ids **8 land at a different index in 4 clashing pairs** — (`pen_nib`,
  `pendulum`), (`sea_glass`, `seal_of_gold`), (`wing_charm`, `winged_boots`),
  (`wongo_customer_appreciation_badge`, `wongos_mystery_ticket`) — and over the
  85 Ironclad card ids 2 move: (`blood_wall`, `bloodletting`).
- **pin** Unpinned.
- **fix** `key=str.upper`-equivalent at every `stable_shuffle` call site. One
  line each; the probe is the checklist.
- **radius** Every `stable_shuffle` caller, in and out of the event tier
  (`sts2_rl/actmap.py:193-201` is the faithful port and is used correctly by
  `sts2_rl/events/doll_room.py:53` and `sts2_rl/relics/fragrant_mushroom.py:31-36`).
  Invisible in legacy mode only because legacy runs are graded against themselves.

### 8. `event/EV-5` — `StableShuffle` replaced by a different algorithm entirely  [LIVE] [**unpinned**]

- **sites** `event/doors_of_light_and_dark/EV-5`, `event/fake_merchant/EV-5`
  (2 entries).
- **impact** A — a different pick from the same stream position, and
  `random.sample` does not even consume the stream the same way.
- **divergence** `DoorsOfLightAndDark.cs:28-29` is
  `Deck.Where(IsUpgradable).ToList().StableShuffle(base.Rng).Take(2)`;
  `sts2_rl/events/doors_of_light_and_dark.py:29` is
  `self.rng.sample(upgradable, count)`. Fake Merchant's is a bare shuffle.
- **observable** The sort is the point — it makes the pick independent of the
  pile's incidental order, so two runs holding the same cards in a different
  order pick the same ones. Both substitutes drop it. Every site is an ordinary
  event branch, and a deck whose card order differs from its sorted order is the
  normal case after any add or transform.
- **pin** Unpinned.
- **fix** Call `actmap.stable_shuffle` — already the faithful port — with the
  event rng and an uppercase key (see `event/EV-7`). Failing test asserts the
  same pick from two decks holding the same cards in different order.
- **radius** Compounded by `event/EV-3` (wrong stream) and `event/EV-7` (wrong
  key): a site can need all three fixes before it converges.

### 9. `event/EV-6` — `CreateForReward` replaced by the in-combat generator  [LIVE] [**unpinned**]

- **sites** `event/infested_automaton/EV-6` (1 entry).
- **impact** A — no rarity roll, no upgrade draw, and the wrong stream.
- **divergence** Both `InfestedAutomaton.cs` branches (`:31`, `:46`) call
  `CardFactory.CreateForReward(..., ForNonCombatWithDefaultOdds(pool, filter))`;
  the sim calls `random_pool_cards` (`sts2_rl/cards/pool.py:136-161`), whose own
  docstring says it "Mirrors CardFactory.GetForCombat (uniform, with
  replacement)" (`sts2_rl/cards/pool.py:146-147`) — the generator behind Infernal
  Blade and Stoke, not the reward one.
- **observable** Three, and only the third is parity-only: (1) **no rarity odds**
  — every card in the pool is equally likely, so Rares appear at pool frequency
  instead of the non-combat default odds; (2) **no upgrade draw** — the
  act-scaled chance for the offered card to arrive upgraded is never rolled;
  (3) the wrong stream. The sim has a faithful `CreateForReward` port —
  `sts2_rl/rewards.py:235-275`, which does the escalating rarity roll, the
  act-scaled upgrade draw, the distinct-card constraint and draws on
  `run.rewards_rng` (`sts2_rl/rewards.py:255-257`) — and the sibling site
  `sts2_rl/events/brain_leech.py:44-47` already calls it.
- **pin** Unpinned.
- **fix** Swap `random_pool_cards` for `rewards.create_reward_cards` at the two
  branches. Failing test asserts a Rare appears at the reward odds, not the pool
  frequency, over a fixed seed.
- **radius** Related to but distinct from `event/EV-8` — EV-8 is the missing
  *hook tail* on a correct `CreateForReward`; this is the wrong factory.

### 10. `event/EV-4` — a take-or-skip reward screen collapsed into an unconditional grant  [LIVE] [**unpinned**]

- **sites** 7 entries on `drowning_beacon`, `endless_conveyor`, `potion_courier`,
  `the_future_of_potions`, `the_legends_were_true`, `wellspring`,
  `whispering_hollow`.
- **impact** A/B — a screen the replay records, and a belt slot the player did
  not choose to spend.
- **divergence** The source wraps these payouts in `RewardsCmd.OfferCustom`, a
  **take-or-skip** screen (`DrowningBeacon.cs:39-46` is the worked example); the
  sim grants unconditionally.
- **observable** Declining is a real choice — a colourless card reward can be a
  card the player does not want in the deck, and a potion offer can be declined
  to keep a belt slot. The source distinguishes the two screens deliberately:
  `BrainLeech.cs:67-70` sets `Cancelable = false` on its grid pick while its RIP
  branch at `BrainLeech.cs:58` uses plain `OfferCustom`. The sim already models
  the offer contract elsewhere — `Event.resume_after_combat` returns potions "to
  surface as take-or-skip offers (RewardsCmd.OfferCustom)"
  (`sts2_rl/events/base.py:116-122`) — so this is an inconsistency inside the sim.
- **pin** Unpinned.
- **fix** Return the reward from the event rather than granting it, the way
  `battleworn_dummy` already hands its Setting1 potion to the driver. Failing
  test asserts a declined offer leaves the belt unchanged.
- **radius** Interacts with the potion-belt model: a forced grant into a full
  belt is a second divergence the records do not separate out.

### 11. `event/EV-8` — a hand-rolled offer skips `CreateForReward`'s hook tail  [LIVE] [**unpinned**]

- **sites** `event/room_full_of_cheese/EV-8`, `event/the_future_of_potions/EV-8`
  (2 entries).
- **impact** B — the offered screen differs, which is what a player and a replay
  both read.
- **divergence** `CardFactory.CreateForReward`'s tail runs
  `Hook.ModifyCardRewardCreationOptions` (`CardFactory.cs:215`) and
  `Hook.TryModifyCardRewardOptions` + `Hook.AfterModifyingCardRewardOptions`
  (`CardFactory.cs:262-266`) unless `NoModifyHooks` is set — it is not, at
  `RoomFullOfCheese.cs:40-42`. A hand-rolled offer never reaches them.
- **observable** The sim has the hook: the egg relics implement
  `modify_card_reward_options` (`sts2_rl/relics/_eggs.py:38-41`). Executed
  (`py audit/tools/event_probes.py cheese`): holding Molten Egg, the GORGE screen
  offers 8 Commons of which 4 are Attacks, and **the sim shows 0 of the 4
  upgraded where the game shows 4**. The deck outcome coincides — `run.add_card`
  still runs the deck-entry hook — but the *screen* differs, which is why this is
  a gap and not a deliberate-divergence.
  `py audit/tools/event_probes.py reach` shows `molten_egg` / `toxic_egg` /
  `frozen_egg` all ported and in the relic grab bag.
- **pin** Unpinned.
- **fix** Route both offers through `rewards.create_reward_cards` (see
  `event/EV-6`) so the offer-side hook runs. Failing test asserts the 4 Attacks
  arrive upgraded on the screen.
- **radius** Every hand-rolled card offer outside the two named events. The egg
  relics are the only current implementers, and the relic tier is
  [unaudited](#what-this-queue-does-not-cover), so there may be more.

### 12. `monster_state_machine/G4` — a stun is not a real move  [LIVE] [pinned]

- **sites** `monster_state_machine/step39`, `/step40`, `/step44` (3 entries;
  clauses a/b/c of one mechanism).
- **impact** A — the following turn's move distribution differs.
- **divergence** `Creature.StunInternal` (`Creature.cs:524-544`) builds a real
  `MoveState("STUNNED", stunMove, new StunIntent())` with
  `FollowUpStateId = nextMoveId` and `MustPerformOnceBeforeTransitioning = true`,
  hands it to `SetMoveImmediate`, and the deferred move is **re-logged** on the
  next roll; the sim models only the intent half —
  `MachineMonster.current_intent` special-cases `self.stunned`
  (`sts2_rl/monsters/state_machine.py:315-318`).
- **observable** The deferred move never re-enters `state_log`, so every
  weight-reads-the-log branch downstream sees a different history. Route is
  executed end to end (`probe whistle-route`): Whistle (`cards/whistle.py:38`) is
  the only sim stun site taking an external target, it comes only from Tanx's
  Whistle, Tanx is in **Glory**'s ancient keys only, and four Glory monsters have
  log-reading branch weights — Scroll of Biting (the cleanest, executed at 100000
  rolls), Flail Knight, Spectral Knight, Soul Nexus.
- **pin** `TestMonsterStateMachineOrder::test_stun_makes_the_stun_a_move_and_relogs_the_deferred_one`.
- **fix** Build the stun as a real `MoveState` in `state_machine.py` —
  performed, pinned by `must_perform_once_before_transitioning`, logged — and let
  the next roll transition `STUNNED → next` with no branch draw. `CreatureCmd.stun`
  (`cmds.py:208-218`) becomes a machine operation for `MachineMonster` instead of
  a boolean. Failing test asserts the stunned turn logs `STUNNED` and the next
  turn re-logs the deferred move without drawing.
- **radius** `monster_state_machine/G5` (the `next_move_key` override is silently
  dropped for a `MachineMonster` — same fix site), `/G6` (FlutterPower's splice),
  and `turn_structure/G9` (the stunned-turn draw count). **These four are one
  work package**: they are all "what happens to the machine when a monster is
  stunned", and fixing them separately risks fixing the draw count twice.

## 1B. Grade B — state divergence

A number, a hand, a pile or a deck entry differs. The next conformance assert
fires; the stream itself survives.

### 13. `event/EV-1` — event damage bypasses the death / death-prevention pass  [LIVE] [**unpinned**]

- **sites** 17 entries on 17 event records (`abyssal_baths`, `brain_leech`,
  `colossal_flower`, `dense_vegetation`, `doll_room`, `jungle_maze_adventure`,
  `room_full_of_cheese`, `round_tea_party`, `slippery_bridge`, `spirit_grafter`,
  `stone_of_all_time`, `sunken_statue`, `tablet_of_truth`,
  `the_legends_were_true`, `this_or_that`, `trash_heap`, `whispering_hollow`);
  the record counts 18 `lose_hp` call sites.
- **impact** B, and the most severe B in the queue — **it ends the run**.
- **divergence** C# routes event damage through `CreatureCmd.Damage`, whose
  `Hook.ShouldDie` / `Hook.AfterPreventingDeath` pass runs over
  `RunState.IterateHookListeners` (`RunState.cs:545-596`), which yields the
  **potion belt** outside combat. `RunState.lose_hp`
  (`sts2_rl/run.py:294-302`) just subtracts.
- **observable** Fairy in a Bottle (`FairyInABottle.cs:33-45`: `ShouldDie` false
  for its owner, `AfterPreventingDeath` heals to `max(MaxHp*0.3, 1)`) **is**
  ported (`sts2_rl/potions.py:1222-1250`) and **is** in the reward pool
  (`sts2_rl/potion_pools.py:49`) — but the sim's copy returns early when
  `self.combat is None` (`sts2_rl/potions.py:1246-1248`) and is only registered
  as a listener by `CombatState` (`sts2_rl/combat.py:164-166`), so it is inert
  during an event. Executed (`py audit/tools/event_probes.py lethal`): a run at
  5 HP holding a belt Fairy that loses 15 HP **ends DEAD at hp = -10 with the
  Fairy still in the belt; the game ends alive at 24 HP with the Fairy
  consumed.** Secondary: `run.lose_hp` does not clamp at 0, so the sim carries
  negative HP.
- **pin** Unpinned. The natural pin is a run-level test, not a hook-order one.
- **fix** Give `RunState.lose_hp` the death pass: dispatch `should_die` /
  `after_preventing_death` over the run-level listener list — which does not
  exist yet, so this needs `hook_dispatch/N5` first or a narrower belt-only
  iteration — and clamp at 0. Then drop the `self.combat is None` early return in
  the Fairy. Failing test asserts the 5-HP-plus-belt-Fairy run survives at 24 HP.
- **radius** Prerequisite `hook_dispatch/N5` (no run-level listener list) and
  adjacent to `event/EV-2` (`lose_max_hp`'s overflow damage takes the same path).
  Every out-of-combat HP loss in the game, not only events.

### 14. `creature_card_cmds/step8b` — `ShouldPowerBeRemovedAfterOwnerDeath` inverted by omission  [LIVE] [**unpinned**]

- **sites** `creature_card_cmds/step8b` plus
  `power/illusion/ShouldPowerBeRemovedOnDeath` (2 entries), cross-referenced by
  five more power records whose own overrides stay `faithful` **because the sim
  gives their behaviour away for free** (`adaptable`, `minion`, `painful_stabs`,
  `reattach`, `steam_eruption`).
- **impact** B — a dead creature keeps every debuff and buff it was holding.
- **divergence** On the real-death branch `CreatureCmd.cs:533-537` calls
  `creature.RemoveAllPowersAfterDeath()` and then awaits each stripped power's
  `AfterRemoved` — the deliberate contrast with escape, which strips silently.
  `Creature.cs:668-671` defines it as **strip by default**:
  `PowerModel.ShouldPowerBeRemovedAfterOwnerDeath` returns **true**
  (`PowerModel.cs:637-640` — "Usually true, but false for powers that do things
  like revive their owner"), only six non-mock powers override it, and
  `Hook.ShouldPowerBeRemovedOnDeath` (`Hook.cs:2495-2509`) has exactly one
  implementer in the whole decompiled game (`IllusionPower.cs:59-66`).
  `sts2_rl/cmds.py:96-105` goes straight from the HP write to `should_die` /
  `should_remove_from_combat_after_death` / `on_death`. There is no strip, no
  `AfterRemoved` analogue and no `should_power_be_removed_on_death` dispatcher.
  **The sim inverts the default: every power C# strips survives.**
- **observable** Executed on the Decimillipede: a `DecimillipedeSegmentFront`
  given Vulnerable 3 and hit for 999 ends at hp 0, `is_dead` True,
  `retained_after_death` True and **still holding `['reattach', 'vulnerable']`**;
  `ReattachPower.do_reattach()` (`sts2_rl/powers.py:2359-2367`) brings it back
  **at 25 HP still Vulnerable 3**. In the game the segment loses the Vulnerable
  on death — `VulnerablePower` does not override the predicate, `ReattachPower`
  overrides only its own (`ReattachPower.cs:98`) and implements no
  `ShouldPowerBeRemovedOnDeath`, so nothing vetoes the strip. The Decimillipede
  is a ported Hive elite and Bash/Vulnerable is ported basic-pool content.
- **pin** Unpinned. **Added 2026-07-26** in the power tier's review fix pass:
  until then this engine-wide absence existed only as prose in a stream report,
  carried no verdict anywhere, and so reached neither `audit_status`, nor this
  queue, nor any fix work list.
- **fix** Add the strip to the real-death arm of `sts2_rl/cmds.py`: build
  `should_power_be_removed_on_death` as a hook, give `Power` a
  `should_power_be_removed_after_owner_death` defaulting to **True**, strip the
  survivors and fire `on_removed` for each. Failing test asserts the reattached
  segment comes back without Vulnerable.
- **radius** Wide and second-order: the record notes **several ported powers
  hand-roll their own `_expire()` where C# adds none — the sim compensating for
  the missing strip one power at a time.** Every one of those is a candidate to
  delete once this lands. Adjacent to `creature_card_cmds/G13` (escape leaves
  powers registered) and `power/_death_prevention_branch`.
- **monster site added 2026-07-27** `monster/test_subject` — the Test Subject is
  where the missing power strip bites hardest, because it respawns twice and
  therefore carries the un-stripped powers through two resets.

### 15. `hook_dispatch/G9` — multiplicative modifier hooks: parallel product vs sequential chain  [LIVE] [pinned]

- **sites** `hook_dispatch/step31`, `damage_pipeline/N3` (2 entries), plus
  `creature_card_cmds/step13` clause (c) as the block-side site (dormant there).
- **content sites** **+2 enchantment sites** (`corrupted`, `instinct`, tagged `BR-1`) with a **sharper witness than either seam record has**: `Hook.cs:1490-1499` applies the source card's `Enchant*Additive` then `Enchant*Multiplicative` to the running damage *before* either listener loop, and the sim pools the enchantment's factor in with everyone else's (`sts2_rl/combat.py:130-133`). Executed (`py audit/tools/enchantment_probes.py order`): **a Corrupted Strike (base 6) with Strength 3 deals 13 in the sim and 12 in the game** — C# folds `6 * 1.5 = 9` then adds 3; the sim sums `6 + 3 = 9` then multiplies by 1.5. The additive-only control (Sharp +2 with Strength +3 = 11) matches, isolating the multiplicative phase. **This witness needs no float at all** — it is a pure phase-order difference, where the seam records' Shrink×Vulnerable case rests on float rounding.
- **impact** B — raw damage numbers differ.
- **divergence** C# folds each listener's factor into a running `decimal`
  (`Hook.cs:2515-2538` `ModifyDamageInternal`, `Hook.cs:1320-1337` `ModifyBlock`);
  the sim multiplies every factor together in float first and applies the product
  once (`sts2_rl/hooks.py:66-78`, `111-122`, applied at `sts2_rl/cmds.py:57-58`
  and `145-147`).
- **observable** Shrink (×0.7, `sts2_rl/powers.py:1366-1387`, from the ported
  Shrinker Beetle `monsters/overgrowth/shrinker_beetle.py:39-40` and the Shrink
  Potion `potions.py:718-722`) plus Vulnerable (×1.5, `powers.py:403-417`) on a
  20-damage powered attack: **sim 20, game 21** — the sim computes
  `1.5*0.7 = 1.0499999999999998`, `20 * that = 20.999999999999996`, `int → 20`;
  the game computes `20m*1.5m = 30m`, `30m*0.7m = 21m`. Base 40 diverges the
  same way. A control run that keeps float arithmetic but threads it
  sequentially returns 21, so the cause is the aggregation shape, not
  float-vs-decimal.
- **pin** `TestHookDispatchOrder::test_multiplicative_damage_modifiers_chain_sequentially`.
- **fix** Change `hooks.modify_damage_multiplicative` /
  `modify_block_multiplicative` from "return the product" to "take the running
  amount, fold each listener's factor in, return the new amount", and change the
  two call sites in `cmds.py` to assign rather than multiply. Keep the additive
  family as is — the record proves base+sum ≡ sequential over integers. Failing
  test asserts 21, not 20, for the Shrink+Vulnerable 20-damage case.
- **radius** Block site (`creature_card_cmds/step13`) is dormant only because all
  five ported block multipliers are dyadic (`{0.0, 0.75, 2.0}`); it goes live
  with the first non-dyadic one. Adjacent mechanisms on the same dispatchers:
  `damage_pipeline/G3` (the powered-attack gate) and `damage_pipeline/G2` (the
  missing modifier-notification list).

### 16. `hook_dispatch/G4` — one hook bracket per logical play instead of per `CardPlay`  [LIVE] [pinned]

- **sites** `hook_dispatch/G4` (1 entry).
- **content sites** **+13 content sites** — 9 power (`calamity`, `duplication`, `enrage`, `free_attack`, `nostalgia`, `one_two_punch`, `rage`, `strangle`, `unmovable`) and 4 enchantment (`corrupted`, `goopy`, `swift`, `vigorous`, tagged `BR-2`). **14 entries in all — the widest cross-kind mechanism in the queue**, and `enchantment/EG1` shares the same loop.
- **impact** B — wrong card gets doubled, from the first combat of a run.
- **divergence** `CardModel.cs:1904-1965` loops `for (i = 0; i < playCount; i++)`,
  builds a fresh `CardPlay` with `PlayIndex = i` each iteration (1919-1928) and
  fires `Hook.BeforeCardPlayed` (1929) **and** `Hook.AfterCardPlayed` (1959)
  *inside* the loop; `sts2_rl/combat.py:466` fires `before_card_played` once
  before the `for _ in range(play_count)` loop (477-494) and `combat.py:514`
  fires `on_card_played` once after it.
- **observable** Throwing Axe (`relics/throwing_axe.py:30-36`, from the ported
  Tanx shrine `events/tanx.py:13`) makes the first card of a combat play twice;
  Pen Nib (`relics/pen_nib.py:30-35`) counts Attack plays in `before_card_played`
  and doubles every 10th. One Throwing-Axe-doubled Strike advances the sim's
  counter by 1 where the game advances it by 2 — **so from the first combat on,
  the sim doubles a different attack than the game does**.
- **pin** `TestHookDispatchOrder::test_before_card_played_fires_once_per_replay_iteration`.
- **fix** In `combat._resolve_card_play`, move the `before_card_played` /
  `on_card_played` dispatches inside the play-count loop and give each iteration
  its own play index. Watch the history writer (`history.py:80-81` records a
  `CardPlayedEntry` per `on_card_played`) — the entry count is deliberately
  per-play in C# too, so it should follow. Failing test asserts Pen Nib's counter
  advances by 2 on a Throwing-Axe-doubled Strike.
- **radius** Four ported replay sources widen it (`enchantments.py:167`,
  `enchantments.py:232`, `powers.py:966` One-Two Punch, `powers.py:3919`
  Duplication) and all 48 sim `on_card_played` listeners see the wrong bracket
  count. Touches `turn_structure/G18` (Pael's Eye counts plays) and
  `creature_card_cmds` step 46 (auto-play bracket).

### 17. `power/_side_turn_slot` — the sim's `on_player_turn_end` is C#'s `BeforeTurnEnd`, not `AfterTurnEnd`  [LIVE] [**unpinned**]

- **sites** 29 entries on 28 power records (`plating` twice). Reproduce the
  affected population with `py audit/tools/power_census.py slots`: **54 units
  override a C# side-turn hook**.
- **impact** B — whether a power is still on the creature when the turn-end card
  effects run.
- **divergence** `AbstractModel.AfterSideTurnEnd` is dispatched by
  `Hook.AfterTurnEnd` (`Hook.cs:1267-1292`), called for the player side at
  `CombatManager.cs:1307` — **after** the turn-end card effects and the hand
  flush. The sim's `on_player_turn_end` is `Hook.BeforeTurnEnd`
  (`sts2_rl/combat.py:654`), which runs **before** `_process_turn_end_cards`
  (`sts2_rl/combat.py:658`) and before the flush (`sts2_rl/combat.py:661-662`).
  The sim's real `AfterTurnEnd` slot, `after_player_turn_end`
  (`sts2_rl/combat.py:665`), exists and is unused.
- **observable** The concrete route, which the record says applies to every unit
  in the group: Stampede (`sts2_rl/powers.py:1025-1041`) auto-plays Attack cards
  from its own `on_player_turn_end`, i.e. inside the very same dispatch, and
  `_process_turn_end_cards` runs more card effects immediately after. **In the
  game every turn-end auto-play happens while these powers are still on the
  creature; in the sim whether it does depends on hook-registration order.** For
  Duplication that is the difference between doubling Stampede's auto-plays and
  not (`DuplicationPower.cs:18-25` has no card-type test).
- **pin** Unpinned. The natural pin is one order test per leg, not 29.
- **fix** One wiring change with 29 beneficiaries: move the powers that override
  C#'s `AfterSideTurnEnd` off `on_player_turn_end` onto the existing
  `after_player_turn_end` slot, or re-point the dispatch. Do it with the census
  as the checklist — some of the 54 are correctly placed and must not move.
  Failing test asserts Duplication doubles a Stampede turn-end auto-play.
- **radius** The enemy leg of the same census is `turn_structure/G5`
  (per-creature in the sim, per-side in the game), still dormant; the phase leg
  is `hook_dispatch/G3`. All three are the same probe's output and probably one
  sitting.

### 18. `enchantment/EG2` — `CreateClone` re-attaches the enchantment; five sim copy sites drop it  [LIVE] [**unpinned**]

- **sites** 17 entries — **every enchantment record carries it**, and the
  divergence is LIVE on 15 of them. Five sim copy sites, one C# behaviour.
- **impact** B — the copy behaves as a different card for the rest of the combat.
- **divergence** `CardModel.CreateClone` (`CardModel.cs:2168`) → `MutableClone`
  → `DeepCloneFields` re-attaches the source card's enchantment onto the copy —
  `CardModel.cs:1204-1209`,
  `(EnchantmentModel)Enchantment.ClonePreservingMutability()`,
  `Enchantment = null`, `EnchantInternal(clone, clone.Amount)` — and does the
  same for the Affliction two lines down (`CardModel.cs:1210-1215`). Five ported
  sim copy sites rebuild the card from its class and carry only the upgrade
  level: `sts2_rl/cards/trash_heap_cards.py:18-24` (`_clone`, Dual Wield),
  `sts2_rl/powers.py:827-830` (Juggling),
  `sts2_rl/relics/music_box.py:46-48`, `sts2_rl/cards/anger.py:36-38` and
  `sts2_rl/relics/burning_sticks.py:30-32`.
- **observable** Executed, per unit and then over all 17 ids: enchant a Strike,
  `_clone` it, and the copy's `enchantment` is `None` where the game's is a live
  copy of the enchantment. Every dropping site puts the copy in hand (or in
  discard, for Anger), so a later reshuffle sweeps it into the draw pile — and
  for Perfect Fit the game then places it on top and draws it next, and the sim
  does not. `CreateClone` throws unless the card sits in a **combat** pile
  (`CardModel.cs:2170-2173`), so every copy site is a combat-pile copy.
- **pin** Unpinned. A cheap `test_hook_order.py` pin is available: assert the
  clone's `enchantment` is not `None`.
- **fix** One helper. The sim's *other* copy paths are already correct and are
  what makes this a bug rather than a design choice —
  `sts2_rl/relics/bing_bong.py:37` and `sts2_rl/events/reflections.py:52` use
  `copy.deepcopy` (the enchantment rides along),
  `sts2_rl/relics/paels_growth.py:39-46` re-attaches Clone by hand, and the
  per-combat deck copy (`sts2_rl/run.py:1136`) carries it. Give the five rebuild
  sites the same carry (and the affliction with it). Failing test asserts
  `_clone(enchanted_strike).enchantment is not None`.
- **radius** All 17 enchantments; Dual Wield, Juggling, Music Box, Anger and
  Burning Sticks as the copy sources. **False docstring:** `_clone`'s says it
  "mirrors CreateClone for the sim's needs" — it carries neither the enchantment
  nor the affliction. Fifth entry in the enchantment stream's false-docstring
  list.

### 19. `power/_death_prevention_branch` — death prevention runs the wrong branch, and `AfterDeath` never fires  [LIVE] [**unpinned**]

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

### 20. `hook_dispatch/G2` — cross-listener dispatch order  [LIVE] [pinned]

- **sites** `hook_dispatch/step1`, `/step2`, `/step5`, `/step6`, `/step41`, `/step43` (6 entries).
- **impact** B — a card's energy cost differs, which changes what is playable.
- **divergence** `CombatState.cs:413-467` groups listeners **per creature**,
  allies before enemies, and within a player walks Powers → Relics → PotionSlots
  → Orbs → cards; `sts2_rl/hooks.py:38,43-44` keeps one flat registration-order
  list whose category order is History → Cards → Relics → Potions → Powers
  (`combat.py:106-166`, `cmds.py:326`) — **powers first in the game and last in
  the sim; cards last in the game and first in the sim**.
- **observable** Executed on `Hook.ModifyEnergyCostInCombat`: with
  `CuriousPower(2)` (`powers.py:2883`, applied by the ported Mad Science card)
  and Spiked Gauntlets (`relics/spiked_gauntlets.py:26-31`, ported Tanx shrine —
  the record cites `26-32`, one line past the end of the file)
  on a 1-cost Power card, the game computes `max(0, 1-2) = 0` then `+1 = 1`; the
  sim computes `1+1 = 2` then `max(0, 2-2) = 0`. **Game 1, sim 0.** Co-occurrence
  is explicit: Mad Science comes from the ported Glory event Tinker Time
  (`events/tinker_time.py:74`).
- **pin** `TestHookDispatchOrder::test_powers_modify_energy_cost_before_relics_do`.
- **fix** Stop relying on registration order: have `HookSystem` iterate a
  *derived* order rather than `self._listeners` as appended. Cheapest faithful
  shape is to keep per-category buckets (powers, relics, potions, cards) per
  creature and yield allies-then-enemies, powers-first, which also gives
  `hook_dispatch/G1` (per-pile card order) somewhere to live. Failing test
  asserts the 1-cost Power card costs 1, not 0, with Curious + Spiked Gauntlets.
- **radius** Every one of the sim's 66 dispatchers. Prerequisite for
  `hook_dispatch/G1` (card listener order re-derived per dispatch),
  `hook_dispatch/G6` (afflictions register right after their card),
  `hook_dispatch/G5` (`MonsterModel` as a listener) and `hook_dispatch/G7` (the
  lazy `Contains` re-check) — all four are dormant today and all four need this
  list to exist first.

### 21. `hook_dispatch/G3` — no Early / VeryEarly / Late phase passes  [LIVE] [pinned]

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

### 22. `enchantment/EG1` — `EnchantmentModel.OnPlay` is a direct in-loop call, not a hook  [LIVE] [**unpinned**]

- **sites** `enchantment/corrupted/EG1`, `/goopy`, `/sown`, `/swift`,
  `/vigorous` (5 entries), plus the three `OnPlay` and two `AfterCardPlayed` hook
  entries that reference it.
- **impact** B — the order two effects resolve in, and how many times.
- **divergence** C# calls `Enchantment.OnPlay` **directly inside the per-Replay
  loop**, after the card's own `OnPlay` and before `Hook.AfterCardPlayed`
  (`CardModel.cs:1904` `for (i < playCount)`, `:1931` the card's `OnPlay`,
  `:1937-1945` the enchantment's, `:1959` `Hook.AfterCardPlayed`). The sim has no
  such slot and wires enchantment `OnPlay` to `before_card_played`.
- **observable** Both legs executed on Corrupted
  (`py audit/tools/enchantment_probes.py onplay-slot replay`):
  **(1) position** — with Rupture at 1 stack (`sts2_rl/powers.py:272-289`, from
  the Ironclad card), a Corrupted Strike deals **10 in the sim and 9 in the
  game**: the sim's self-damage fires first, Rupture grants +1 Strength and the
  Strike lands at Strength 1, where C# resolves the Strike at Strength 0 and only
  then takes the 2. **(2) per-replay** — with Throwing Axe
  (`sts2_rl/relics/throwing_axe.py:30-36`) the card is played twice: **the sim
  takes 2 self-damage, the game takes 4.** Corrupted comes from the ported
  Symbiote event (`sts2_rl/events/symbiote.py:33-45`), Rupture is an Ironclad
  pool card (`sts2_rl/cards/pool.py:30`) and Throwing Axe is a ported Ancient
  relic.
- **pin** Unpinned.
- **fix** Add the slot: call `card.enchantment.on_play(...)` from inside
  `combat._resolve_card_play`'s play-count loop, after the card's `on_play` and
  before `on_card_played`. This is the same loop `hook_dispatch/G4` moves the
  hook bracket into — **do them together**. Failing test asserts the Corrupted +
  Rupture Strike deals 9.
- **radius** Leg (2) is `hook_dispatch/G4` at an enchantment site and the
  enchantment records record it separately as `BR-2`; the whole group lands in
  one loop.

### 23. `power/_killing_blow_guard` — `on_damage_received` is skipped on the killing blow  [LIVE] [**unpinned**]

- **sites** `power/flame_barrier/g5`, `power/flutter/AfterDamageReceived`,
  `power/hardened_shell/AfterDamageReceived`, `power/painful_stabs/AfterAttack`,
  `power/slippery/AfterDamageReceived`, `power/suck/AfterAttack`,
  `power/the_gambit/AfterDamageReceived` (7 entries).
- **impact** B — a reflect, a cap or a counter that fires in one engine and not
  the other, on the most common event in the game.
- **divergence** `sts2_rl/cmds.py:121` reproduces `CreatureCmd.cs:392`'s
  "skip the victim's `AfterDamageReceived` on a kill" — correctly, for powers
  whose C# hook really is `AfterDamageReceived`. The gap is every power whose C#
  hook is something else and which the sim nonetheless hung on
  `on_damage_received`.
- **observable** `power/flame_barrier`'s entry is the clean statement of the
  contrast, and is verdicted `gap` purely to carry it at the same precedence:
  both engines skip Flame Barrier's reflect on a kill (faithful), **and both
  engines must not skip Thorns'** — see `damage_pipeline/G1` below, where the
  executed number is a 99-damage Strike into a 3-HP Thorns-5 enemy costing the
  sim's player **0 HP and the game 5**.
- **pin** Unpinned as a family; `damage_pipeline/G1`'s pin covers the Thorns
  site.
- **fix** Not one fix — a per-unit re-hosting. For each of the 7, decide from the
  C# hook whether the guard applies, and move the sim listener to
  `before_damage_received` / `on_damage_dealt` where it does not. The census is
  the checklist; `power/_after_damage_given_substitution` is the same exercise
  for the dealer side.
- **radius** `damage_pipeline/G4` (the skip decision recomputed after death
  prevention) and `power/_death_prevention_branch` both change *when* the guard
  is evaluated, so fix those first or the re-hosting is measured against a moving
  target.

### 24. `damage_pipeline/G1` — Thorns is on the wrong hook  [LIVE] [pinned]  ← raised from DORMANT by the power tier

- **sites** `damage_pipeline/G1` (the seam entry, which labels itself
  **dormant**) and `power/thorns/BeforeDamageReceived` (the power record, which
  labels it **LIVE, twice over, with two executed witnesses**). One mechanism,
  two records, two liveness values — see
  [Record inconsistencies](#record-inconsistencies-found-while-aggregating).
- **impact** B — reflected damage the player does or does not take.
- **divergence** `ThornsPower.cs:17-24` is `BeforeDamageReceived` with the guard
  `target == Owner && dealer != null && (props.IsPoweredAttack() || cardSource is
  Omnislice)`; `sts2_rl/powers.py:339-348` is `on_damage_received`
  (`sts2_rl/cmds.py:122`, fired after the HP write at `sts2_rl/cmds.py:92`) with
  the guard `target is self.owner and dealer is not None` and **no props test at
  all**.
- **observable** Two, both executed. **(1) Killing blow:** the sim's
  `on_damage_received` is skipped when the hit killed the victim
  (`sts2_rl/cmds.py:121`), but C#'s `BeforeDamageReceived` runs before any HP
  loss and is not subject to that guard — a **99-damage Strike into a 3-HP enemy
  holding Thorns 5 costs the sim's player 0 HP and the game 5**; a non-killing
  hit costs 5 in both (control). Reachable from the first Thorns enemy the player
  kills: Spiny Toad (`sts2_rl/monsters/hive/spiny_toad.py:45`) and Toadpole
  (`sts2_rl/monsters/underdocks/toadpole.py:75`) both self-apply Thorns.
  **(2) Missing props gate:** `on_damage_received` fires for every damage type,
  so the sim reflects Thorns off unpowered non-attack damage the game ignores —
  **3 unpowered non-card damage into a Thorns-5 enemy costs the sim's player 5 HP
  and the game 0**, reachable with the ported Juggernaut
  (`sts2_rl/cards/juggernaut.py:38` → `sts2_rl/powers.py:791-794`); Panache,
  Inferno, Rolling Boulder, The Bomb and Flame Barrier all deal damage in the
  same shape.
- **pin** The seam's existing `damage_pipeline/G1` xfail — see
  `py audit/tools/gap_queue.py pins`. It was written against the dormant reading;
  the power record's two witnesses are the assertions it should carry.
- **fix** Move the sim's Thorns listener to `before_damage_received` and add the
  props gate (`is_powered_attack or cardSource is Omnislice`). Failing test
  asserts 5 on the killing blow and 0 on unpowered non-card damage.
- **radius** `damage_pipeline/G3` (the pipeline-level `is_powered_attack` gate)
  is the general form of leg 2; `power/_killing_blow_guard` is the family leg 1
  belongs to.

### 25. `power/_should_allow_hitting` — `PowerCmd.apply` has no `CanReceivePowers` backstop  [LIVE] [pinned]  ← **pinned 2026-07-27 by the potion tier**

- **sites** `power/adaptable/ShouldAllowHitting`, `power/illusion/…`,
  `power/reattach/…` (3 entries, identical text, verdict carried per rule 3),
  `monster/the_obscura/g1`, and four potion entries added 2026-07-27:
  `potion/potion_of_binding/OnUse`, `potion/potion_of_binding/g1`,
  `potion/shackling_potion/OnUse`, `potion/shackling_potion/g1`. **8 entries
  across 3 kinds.**
- **impact** B — a power lands on a creature the game refuses to apply to.
- **divergence** C#'s `PowerCmd.Apply<T>` refuses to apply anything to a creature
  `CanReceivePowers` says no to, and `CanReceivePowers` reuses
  `Hook.ShouldAllowHitting`. The sim wires `should_allow_hitting` into
  `DamageCmd.deal` (`sts2_rl/cmds.py:51-52`) but **not** into `PowerCmd.apply`,
  which has no such guard at any point.
- **observable** Executed: in a `TEST_SUBJECT_BOSS` combat (the Test Subject
  starts with `['adaptable', 'enrage']`), after a lethal Strike the sim reports
  `is_reviving True`, `should_allow_hitting(ts) False`, **and then still lands
  `Vulnerable(2)` on the reviving boss**, where the game refuses the application
  outright. Control: a 10-damage Strike in the same window returns 0 HP lost,
  proving the predicate *is* wired into the damage path and only the power path
  is missing it. Bash/Vulnerable is ported basic-pool Ironclad content and the
  revive window is the ordinary flow of the fight.
- **pin** `test/test_hook_order.py::TestPotionContentPins::test_aoe_power_potion_skips_an_unhittable_enemy`
  (strict, failing). **Read the pin's history before trusting any pin's
  attribution.** Its `reason` names `seam/power_cmd` G6 — correctly, per rule 3
  — but G6 is a *two-headed* guard ("No `CombatManager.IsEnding` /
  `CanReceivePowers` guard backstop") and this queue merges `power_cmd/G6` into
  `hook_dispatch/G8`, the `IsEnding` family. So the pin scanner filed a LIVE,
  failing, executed pin against a **dormant** 22-site mechanism while this
  entry, the one it actually proves, read `unpinned`. `gap_queue._PIN_OVERRIDE`
  now redirects it. A pin credited to the wrong mechanism is worse than one
  credited to none: it reports coverage in two places at once.
- **fix** Add the guard at the top of `sts2_rl/cmds.py`'s `PowerCmd.apply`:
  return without applying when `hooks.should_allow_hitting(target)` is false.
  Failing test asserts the Vulnerable does not land on the reviving Test Subject.
- **radius** **This falsifies a dormancy claim.** `power_cmd`'s G6 says "No
  concrete broken interaction is demonstrated (spot-checked callers apply powers
  only to already-resolved targets)". It is now demonstrated. Reported, not
  fixed — see [Record inconsistencies](#record-inconsistencies-found-while-aggregating).
- **monster site added 2026-07-27** `monster/the_obscura` — WAIL applies
  `StrengthPower 3m` to `GetTeammatesOf(Creature)`, which includes a reviving
  Parafright, and the sim's `PowerCmd.apply` has no `CanReceivePowers` backstop.
  A concrete site of the mechanism rather than a new one.
- **potion sites added 2026-07-27, with a second executed witness and the
  contrast that localises the fix.** Potion of Binding and Shackling Potion walk
  `CombatState.HittableEnemies` (`CombatState.cs:142`), which the sim ports as
  `[e for e in ctx.enemies if not e.is_gone]` — no `ShouldAllowHitting` term.
  `py audit/tools/potion_probes.py aoe-power` builds an Eye with Teeth
  mid-Illusion-revival (summoned by Fogmog,
  `sts2_rl/monsters/overgrowth/fogmog.py:95`) and prints
  `should_allow_hitting False`, C# `HittableEnemies` empty, sim filter keeps 1 —
  then Potion of Binding lands `weak 1` + `vulnerable 1` and Shackling Potion
  lands `strength -7`, where the game applies nothing. **The same probe shows
  Explosive Ampoule changing nothing on that creature**, because `DamageCmd.deal`
  applies the predicate itself (`sts2_rl/cmds.py:51-52`). That contrast is the
  argument for fixing `PowerCmd.apply` rather than the potions' target filters:
  the damage path is already correct at every site.

### 26. `event/EV-2` — `lose_max_hp` has no overflow damage and floors max HP first  [LIVE] [**unpinned**]

- **sites** `event/drowning_beacon/EV-2`, `event/tablet_of_truth/EV-2`,
  `event/unrest_site/EV-2`, `event/vakuu/EV-2` (4 entries; one verdict at every
  `lose_max_hp` site).
- **impact** B — an HP number, and in the extreme a run that should have ended.
- **divergence** C# `CreatureCmd.LoseMaxHp` turns the overflow into **real
  damage**, so HP-loss modifiers apply and the damage is computed against the
  *unfloored* new max; `sts2_rl/run.py:316-321` floors max HP and clamps.
- **observable** Both legs executed (`py audit/tools/event_probes.py maxhp`):
  **(1)** at 80/80, losing 10 max HP while holding the ported Tungsten Rod
  (`sts2_rl/relics/tungsten_rod.py:39`) leaves the sim at **70** and the game at
  **71**; **(2)** losing more max HP than the player has — the game computes the
  damage against the unfloored new max (80 − 100 = −20, so 100 damage) and
  **kills the player**, while the sim floors max HP at 1 first and leaves them
  alive at 1/1. Leg (1) is live on every max-HP-loss event with the rod held.
- **pin** Unpinned.
- **fix** Reshape `RunState.lose_max_hp` to C#'s order: compute the new max
  unfloored, route the overflow through the HP-loss path (which needs
  `event/EV-1`'s death pass to be right), *then* floor. Failing test asserts 71,
  not 70, with Tungsten Rod.
- **radius** `creature_card_cmds/G6` (`lose_max_hp` cannot kill) is the seam
  record of leg (2); `event/EV-1` is the death pass leg (2) needs.

### 27. `event/EV-10` — the transform screen reuses the removal predicate  [LIVE] [**unpinned**]

- **sites** `event/morphic_grove/EV-10`, `event/trial/EV-10` (2 entries).
- **impact** B — the wrong card is destroyed, permanently.
- **divergence** `sts2_rl/run.py:364-366` (`run.transformable_cards`) reuses the
  REMOVAL predicate for the TRANSFORM screen, where
  `CardSelectCmd.FromDeckForTransformation` (`CardSelectCmd.cs:487`) filters
  `c.Type != CardType.Quest && c.IsTransformable`.
- **observable** Executed: on the deck `[strike, spoils_map]` with 100 gold, the
  sim's screen offers `['strike','spoils_map']` where the game's offers
  `['strike']`; because Morphic Grove's GROUP passes
  `new CardSelectorPrefs(prompt, 2)` — `MinSelect == MaxSelect`, so
  `RequireManualConfirmation` is false (`CardSelectorPrefs.cs:68-78`) — **the
  game auto-takes its whole 1-card list (`CardSelectCmd.cs:493-495`) and
  transforms one card, while the sim transforms two and destroys the Quest
  card.** The *gate* is fine and the record corrects an earlier claim that it was
  not: `MorphicGrove.cs:26` counts `c.IsTransformable`, which for a Deck card is
  `!Eternal` (`CardModel.cs:739-750`) with no Quest clause, so both engines count
  Quest cards toward the `>= 2`.
- **pin** Unpinned.
- **fix** Split the predicate: give `run.transformable_cards` the
  `Type != Quest && IsTransformable` test and leave the removal predicate alone.
  Failing test asserts `spoils_map` is not offered on the transform screen.
- **radius** Every `transformable_cards()` caller. Adjacent to
  `creature_card_cmds/G3` (transform bypassing the deck-entry pipeline) — the
  same screen, a different half.

### 28. `creature_card_cmds/step52` — `Downgrade` drops one level and does not re-run `ModifyCard`  [LIVE] [pinned]  ← raised from DORMANT by the enchantment tier

- **sites** `creature_card_cmds/step52` (the seam entry, **dormant**) plus
  `enchantment/goopy/BR-3`, `/souls/BR-3`, `/steady/BR-3`,
  `/tezcataras_ember/BR-3` (5 entries total).
- **impact** B — a keyword an enchantment added or removed comes back.
- **divergence** `CardModel.DowngradeInternal` re-runs `Enchantment?.ModifyCard()`
  (`CardModel.cs:2145`); `sts2_rl/cards/base.py:150-165` (`Card.downgrade`) does
  not, because it rebuilds the card from its canonical model.
- **observable** Executed on the Souls twin
  (`py audit/tools/enchantment_probes.py souls-reset`): `exhausts` is False after
  attach, **True after `upgrade()` + `downgrade()`** — and False again after the
  next combat's `Enchantment.reset()` (`sts2_rl/enchantments.py:293-296`, called
  from `sts2_rl/combat.py:131`). Only the four enchantments that mutate a static
  card property at attach time can be undone this way —
  `['goopy','souls','steady','tezcataras_ember']`, executed.
- **pin** The seam's existing `creature_card_cmds/step52` xfail.
- **fix** Re-apply `card.enchantment.modify_card(card)` after the rebuild inside
  `Card.downgrade` (and `upgrade`). Failing test asserts a Souls'd Exhaust card
  is still non-Exhaust after upgrade + downgrade.
- **radius** **The enchantment record corrects the seam's witness**: step 52's
  stated out-of-combat leg does not reach the player — the only ported
  out-of-combat downgrade is the Reflections event
  (`sts2_rl/events/reflections.py:36-41`), which self-heals before the card is
  played again — while the in-combat leg (Dampen,
  `sts2_rl/powers.py:3149-3183`) does. The divergence window is bounded by the
  next combat's `reset()`.

### 29. `turn_structure/G13` — no `CheckWinCondition` after the turn-1 setup  [LIVE] [pinned]

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

### 30. `turn_structure/G14` — the turn-1 `ShouldStartAtBottomOfDrawPile` pass is missing  [LIVE] [pinned]

- **sites** `turn_structure/step21`, `/G14` (2 entries).
- **content sites** **+1 enchantment site**, `enchantment/imbued/BR-5`. 3 entries in all.
- **impact** B — the opening hand differs, which changes every play in it.
- **divergence** `CombatManager.cs:657-672` runs **two** pile moves before the
  turn-1 draw — first every card whose enchantment sets
  `ShouldStartAtBottomOfDrawPile` goes to the bottom, then every Innate card not
  already moved goes to the top (`.Except(list)`); `sts2_rl/player.py:172-182`
  ports only the Innate half.
- **observable** `ShouldStartAtBottomOfDrawPile` has exactly one implementer in
  the whole decompiled game — `Imbued.cs:11` — and Imbued **is** ported
  (`enchantments.py:243-267`) and obtainable (Electric Shrymp,
  `relics/electric_shrymp.py:17-21`, enchants a deck Skill with it). Observed
  over 30 seeds with a 9-Strike + 1-Imbued-Defend deck: the sim's turn-1 hand is
  4 cards in 17 of them (the Imbued card occupies an opening-hand slot the game
  never gives it).
- **pin** `TestTurnStructureOrder::test_imbued_card_starts_at_the_bottom_of_the_draw_pile`.
- **fix** In `player.start_turn`'s `_first_turn` arm, run the bottom-move pass
  *before* the Innate top-move pass and exclude already-moved cards from the
  Innate pass, mirroring `.Except(list)`. Failing test asserts the Imbued Defend
  is at the bottom of the draw pile and the opening hand is 5 Strikes.
- **radius** Only Imbued today, but the pass is generic; any future enchantment
  overriding the hook lands here. Touches the same `_first_turn` block as
  `turn_structure/G6` (turn-1 block clear) — fix them together.

### 31. `creature_card_cmds/G3` — a deck transform bypasses the deck-entry pipeline  [LIVE] [pinned]

- **sites** `creature_card_cmds/step57`, `/step59`, `/G3` (3 entries).
- **content sites** **+7 event sites** (`aroma_of_chaos`, `endless_conveyor`, `morphic_grove`, `symbiote`, `trial`, `whispering_hollow`, `wood_carvings`, each tagged `BR-G3`), all naming `RunState.transform_card` (`sts2_rl/run.py:406-470`) as the bypass. 10 entries in all.
- **impact** B — the deck itself diverges, permanently, for the rest of the run.
- **divergence** `CardCmd.Transform` runs `Hook.ModifyCardBeingAddedToDeck`
  (`CardCmd.cs:430`) and fires `Hook.AfterCardChangedPiles` (`CardCmd.cs:447`) for
  Deck-pile transforms — the same two hooks `CardPileCmd.Add` runs;
  `sts2_rl/run.py:459-469` (`RunState.transform_card`) deletes the original and
  appends the replacement directly, never routing through `run.py:341-354`
  (`add_card`), which is where both sim-side hooks live.
- **observable** Executed: holding Frozen Egg, `add_card(Inflame)` yields
  `upgrade_level 1` but `transform_card(..., into=Inflame)` yields **0**; holding
  Bing Bong, `add_card` grows the deck by 2 but `transform_card` adds **0**
  clones. Every participant is ported: the three egg relics (Frozen/Toxic/Molten),
  Bing Bong, Book of Five Rings, Darkstone Periapt, Lucky Fysh.
- **pin** `TestCreatureCardCmdsOrder::test_deck_transform_runs_modify_card_being_added_to_deck`.
- **fix** Route `transform_card`'s replacement through the same hook calls
  `add_card` makes — `modify_card_being_added_to_deck` before insertion and the
  deck-add shim (`relics/base.py:208-210`) after — while keeping the
  append-at-deck-end position (`CardCmd.cs:437`, an already-verified parity fact).
  Failing test asserts a Frozen-Egg transform into a Skill produces an upgraded
  card.
- **radius** `creature_card_cmds/G8` (no `AfterCardChangedPiles` at all) is the
  general version — the deck-only shim covers the four ported listeners
  *everywhere except this transform path*, which is exactly why G3 bites.
  `creature_card_cmds/step55` (in-combat transform rolls off-stream) is the
  combat-side sibling and is a parity defect in its own right.

### 32. `damage_pipeline/G3` — pipeline-level `is_powered_attack` gate  [LIVE] [pinned]

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

### 33. `damage_pipeline/G2` — no `AfterModifyingXxx(modifiers)` companion events  [LIVE at the block site] [pinned]

- **sites** `damage_pipeline/step5`, `/step9`, `/step12`, `/G2`;
  `power_cmd/step21`, `/step22`, `/step31`, `/step32`, `/G4`;
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

### 34. `turn_structure/G8` — the AutoPrePlay / AutoPostPlay phases do not exist  [LIVE] [pinned]

- **sites** `turn_structure/step6`, `/step10`, `/step26`, `/step47`, `/G8`,
  `/N1` and N1's two co-entries (8 entries).
- **content sites** **+1 enchantment site**, `enchantment/imbued/BR-4` — Imbued's `AfterAutoPrePlayPhaseEntered` has nowhere to fire. 9 entries in all.
- **impact** B — block totals differ; also the home of a hand-rolled recursion
  guard.
- **divergence** C# gives start-of-turn auto-plays their own phase, entered
  strictly after `Hook.AfterSideTurnStart` and the orb queue
  (`CombatManager.cs:556-572`), and end-of-turn auto-plays a phase entered
  strictly before `Hook.BeforeTurnEnd` (`CombatManager.cs:1160-1176`); the sim has
  neither hook and hand-rolls both onto neighbouring slots.
- **observable** `StampedePower` is ported and fires from `on_player_turn_end`
  (`powers.py:1025`) — the sim's `BeforeTurnEnd` slot — where C# implements
  `AfterAutoPostPlayPhaseEntered`; Cloak Clasp (`relics/cloak_clasp.py:19-24`)
  gains 1 block per card in hand from `BeforeSideTurnEnd`. C# **always** runs
  Stampede's auto-plays before Cloak Clasp counts the hand; the sim's answer
  depends on registration order. Observed with a 5-card hand and Stampede 2.
- **pin** `TestTurnStructureOrder::test_end_of_turn_auto_plays_run_before_turn_end_hooks`.
- **fix** Add the two phase slots to `combat.end_turn` / `player.start_turn` as
  explicit steps (drain auto-plays, then dispatch the turn-end hooks) rather than
  as listeners; that also gives `turn_structure/N1`'s hand-rolled recursion guard
  (`relics/whispering_earring.py:27-43`, `if combat.is_over or self.turn !=
  start_turn: break`) a real home. Failing test asserts Cloak Clasp counts the
  post-Stampede hand.
- **radius** `turn_structure/N1` (the `_inPlayerTurnSetup` race guard) carries
  this mechanism's precedence by the record's own statement.
  `hook_dispatch/G3`'s phase machinery is the neighbouring fix; `turn_structure/G12`
  is the other ordering-by-phase entry.

### 35. `turn_structure/G12` — sub-phase ordering inside BeforeTurnEnd / AfterTurnEnd / AfterSideTurnStart  [LIVE] [pinned]

- **sites** `turn_structure/step23`, `/step39`, `/step48`, `/step64`, `/G12` (5 entries).
- **impact** B — a relic's snapshot reads post-mutation state.
- **divergence** C# guarantees ordering with separate complete passes —
  `BeforeSideTurnEndVeryEarly` → `Early` → `BeforeSideTurnEnd`
  (`Hook.cs:1238-1261`), `AfterSideTurnEnd` → `AfterSideTurnEndLate`
  (`Hook.cs:1265-1291`), `AfterSideTurnStart` → `Late` (`Hook.cs:1163-1175`); the
  sim's dispatchers are a single pass each (`hooks.py:285-295`, `297-301`,
  `338-342`).
- **observable** Orichalcum is ported and deliberately two-phase in C# —
  `BeforeSideTurnEndVeryEarly` snapshots `Block > 0` into `ShouldTrigger`
  (`Orichalcum.cs:44-56`) and `BeforeSideTurnEnd` then grants the 6 block. In the
  sim both halves collapse into one pass, so whether the snapshot sees a
  block-spending listener's effect is registration-order luck. The record
  explicitly overturns the inherited "no ported pair contends" claim.
- **pin** `TestTurnStructureOrder::test_orichalcum_snapshots_block_before_other_turn_end_listeners`.
- **fix** Same machinery as `hook_dispatch/G3`: phase passes in `HookSystem`.
  Land G3 first, then convert these three dispatchers. Failing test asserts
  Orichalcum still grants its block when another turn-end listener spends the
  block first.
- **radius** `hook_dispatch/G3` (the general phase gap, 5 more sites),
  `turn_structure/G11` (the missing enemy-side `BeforeTurnEnd` slot).

### 36. `turn_structure/G3` — the extra-turn check short-circuits the entire turn-end pipeline  [LIVE] [pinned]

- **sites** `turn_structure/step65`, `/step68`, `/G3`, plus `turn_structure/N4`
  and `turn_structure/step66` — RoundNumber vs TurnNumber, which the record says
  carries G3's precedence (5 entries).
- **impact** B — an entire turn's worth of end-of-turn effects is skipped.
- **divergence** `combat.py:648-652` tests `should_take_extra_turn` at the **top**
  of `end_turn` and, on success, runs only `on_extra_turn`, `turn += 1` and
  `start_turn()`; C# evaluates `Hook.ShouldTakeExtraTurn` in
  `SwitchFromPlayerToEnemySide` (`CombatManager.cs:1360-1373`) **after** both
  end-turn phases have run, and skips only the enemy side.
- **observable** With Pael's Eye held (ported Ancient relic from the Pael shrine,
  `events/pael.py:53`, `relics/paels_eye.py:36-47`) and no card played, a full
  hook trace of `end_turn` records `should_take_extra_turn` and nothing else — no
  `on_player_turn_end`, no flush, no `after_player_turn_end`. The sim has dozens
  of `on_player_turn_end` listeners plus Parrying Shield's
  `after_player_turn_end`.
- **pin** `TestTurnStructureOrder::test_extra_turn_still_runs_the_turn_end_pipeline`.
- **fix** Move the `should_take_extra_turn` test to the *bottom* of `end_turn`,
  after the flush and cleanup, and make it skip only `_run_enemy_turns`. While
  there, split `self.turn` into a player `turn_number` and a combat
  `round_number` (`turn_structure/N4`) — `CombatManager.cs:1405-1418` increments
  them differently. Failing test asserts an extra turn still fires
  `on_player_turn_end` and the flush.
- **radius** `turn_structure/N4` merges here by the record's own precedence
  statement; `turn_structure/G18` (Pael's Eye's own predicate) is the same relic's
  other gap and the two interact — fix G18 first or the test fixture will disagree
  with itself.

### 37. `turn_structure/G1` — `AfterBlockCleared` is a separate unconditional loop  [LIVE] [pinned]

- **sites** `turn_structure/step14`, `/G1` (2 entries).
- **impact** B — block-triggered relics fire (or fail to fire) a turn early.
- **divergence** C# runs the block clear and its event in **two** loops —
  `foreach (item3 in creaturesStartingTurn) await item3.AfterTurnStart(side)`
  (`CombatManager.cs:492-499`) then `foreach (item4 …) await
  Hook.AfterBlockCleared(_state, item4)` (500-507) — so the event fires for every
  participant, including one with no block, one whose clear a `ShouldClearBlock`
  listener prevented, and a turn-1 player whose `AfterTurnStart` returned early.
  The sim fuses them: `player.py:157-159` fires `on_block_cleared` only inside the
  `if should_clear_block(...)` arm and `combat.py:296-298` additionally gates the
  enemy arm on `enemy.block > 0`.
- **observable** Both preventers are ported — Barricade
  (`cards/barricade_card.py:33-34`, `powers.py:140`) and Sturdy Clamp — and both
  Anchor and Fake Anchor are wired onto `on_block_cleared` as their compensation
  for `turn_structure/G6`, so a Barricaded player never re-arms them.
- **pin** `TestTurnStructureOrder::test_block_clear_event_fires_even_when_prevented`.
- **fix** Split the fused arm: clear the block under `should_clear_block`, then
  fire `on_block_cleared` unconditionally for every participant, in a second pass
  over the same list (`player.py:157-159` and `combat.py:296-298`). Failing test
  asserts `on_block_cleared` fires for a Barricaded player.
- **radius** `turn_structure/G2` (the missing preventer identity) and
  `turn_structure/G6` (turn-1 clear) are the same three lines of `player.py`;
  land all three in one pass. Content: Anchor, Fake Anchor, Barricade, Sturdy
  Clamp, Orichalcum.

### 38. `turn_structure/G2` — no `after_preventing_block_clear`, no preventer identity  [LIVE] [pinned]

- **sites** `turn_structure/step13`, `/G2` (2 entries).
- **impact** B — Sturdy Clamp caps block it should not cap.
- **divergence** `Creature.ClearBlock` (`Creature.cs:718-728`) passes the vetoing
  listener out of `Hook.ShouldClearBlock` and fires
  `Hook.AfterPreventingBlockClear(preventer, creature)` on the else-arm;
  `SturdyClamp.cs:31-46` caps the retained block at 10 there and guards
  `if (this != preventer || creature != Owner.Creature) return`. The sim's
  `hooks.should_clear_block` (`hooks.py:613-619`) returns a bare bool, so
  `relics/sturdy_clamp.py:27-30` caps from `on_player_turn_start` instead — with
  no preventer test and at a different point in the turn (`player.py:169`, after
  the energy reset at 163-168).
- **observable** With Barricade active, the sim's Sturdy Clamp caps the retained
  block at 10 even though Barricade, not Sturdy Clamp, prevented the clear; C#
  leaves it uncapped.
- **pin** `TestTurnStructureOrder::test_sturdy_clamp_does_not_cap_when_it_is_not_the_preventer`.
- **fix** Make `should_clear_block` return `(bool, preventer)` like the sim's
  `should_die`/`preventer` pattern already does (`cmds.py:96-112`), add
  `after_preventing_block_clear(preventer, creature)`, and move Sturdy Clamp's
  cap onto it. Failing test asserts Barricade + Sturdy Clamp keeps 30 block.
- **radius** `turn_structure/G1` (same lines), `damage_pipeline/G4` (the sim's
  other preventer-shaped hook). The `should_die` preventer out-param is the
  template to copy.

### 39. `turn_structure/G6` — the sim clears the player's block on turn 1  [LIVE] [pinned]

- **sites** `turn_structure/step12`, `/G6` (2 entries).
- **impact** B — pre-combat block evaporates before the first enemy turn.
- **divergence** `Creature.AfterTurnStart` returns **before** `ClearBlock` for a
  player whose `PlayerCombatState.TurnNumber == 1` (`Creature.cs:681-692`), which
  is what lets `Hook.BeforeCombatStart` grant block that survives into the first
  enemy turn; `player.py:157-159` has no turn-1 arm.
- **observable** A player holding 10 block at the first `start_turn`
  (`_first_turn = True`) ends it with 0. Anchor's real hook is
  `BeforeCombatStart` (`Anchor.cs:19-23`) and the sim had to re-wire it onto
  `on_block_cleared` to compensate (`relics/anchor.py:21-24`, whose docstring says
  so) — as did Fake Anchor (`relics/fake_anchor.py:24-29`). That workaround is
  itself what makes `turn_structure/G1` bite those two relics.
- **pin** `TestTurnStructureOrder::test_player_block_is_not_cleared_on_turn_one`.
- **fix** Add the turn-1 early return to `player.start_turn`'s block-clear arm,
  then un-rewire Anchor and Fake Anchor back onto a `before_combat_start` hook.
  Failing test asserts a player granted 10 block before combat still has it when
  the first enemy attacks.
- **radius** `turn_structure/G1`, `/G2` (same three lines), `/G14` (the other
  turn-1-only branch in `player.start_turn`). Content: Anchor, Fake Anchor.

### 40. `turn_structure/G4` — a false `ShouldFlush` skips the whole flush tail  [LIVE] [pinned]

- **sites** `turn_structure/step61`, `/G4` (2 entries).
- **impact** B — a deferred exhaust credit is never paid.
- **divergence** C#'s `FlushPlayerHand` treats `ShouldFlush == false` as "every
  card is retained" — `cardsToFlush` is empty and the batched Add is skipped — but
  it still runs `Hook.AfterFlush(..., cardsToFlush, cardsToRetain)` **and**
  `PlayerCombatState.EndOfTurnCleanup()` (`CombatManager.cs:1327-1346`); the sim
  guards the whole thing: `if self.hooks.should_flush_hand(): self.player.discard_hand()`
  (`combat.py:661-662`).
- **observable** The live path is the sim's `on_hand_emptied`, fired from inside
  `discard_hand` (`player.py:197`): Joss Paper defers Ethereal-caused exhausts and
  credits them from `on_hand_emptied` (`relics/joss_paper.py:41-45`), so with a
  retain effect suppressing the flush the credit is silently dropped.
- **pin** `TestTurnStructureOrder::test_no_flush_still_credits_the_end_of_turn_hand_events`.
- **fix** Unconditionally run the flush *tail* — the after-flush hooks and the
  end-of-turn cleanup — and let `should_flush_hand` decide only which cards move.
  Failing test asserts Joss Paper's credit lands on a no-flush turn.
- **radius** `turn_structure/G16` (`on_hand_emptied` fired from the one site C#
  excludes) and `/G17` (Joss Paper's cause proxy) are the same relic's other two
  gaps — all three should be read together before touching `joss_paper.py`.
  `turn_structure/G7` (`EndOfTurnCleanup` has no counterpart at either site) is
  the missing tail itself.

### 41. `turn_structure/G17` — Joss Paper's `causedByEthereal` proxy is the card, not the cause  [LIVE] [pinned]

- **sites** `turn_structure/G17` (1 entry).
- **impact** B — a mid-turn exhaust credit is withheld until the flush.
- **divergence** C#'s `AfterCardExhausted` takes the cause as a parameter —
  `AfterCardExhausted(ctx, card, bool causedByEthereal)` (`JossPaper.cs:102-114`,
  dispatched from `CardCmd.cs:237-244` / `Hook.cs:237-242`) — and
  `causedByEthereal: true` is passed from exactly two sites in the whole game,
  both at turn end (`CombatManager.cs:1240`, `CardModel.cs:1692`). The sim has no
  cause parameter: `relics/joss_paper.py:36` branches on `card.is_ethereal`, a
  property of the *card*.
- **observable** An Ethereal card exhausted in the middle of the play phase is
  booked to `_ethereal_pending` and its credit withheld until `on_hand_emptied`
  fires from the flush; the game credits it at once.
- **pin** `TestTurnStructureOrder::test_joss_paper_credits_a_mid_turn_ethereal_exhaust_at_once`.
- **fix** Add a `caused_by_ethereal: bool = False` parameter to
  `hooks.on_card_exhausted` and pass `True` only from the two turn-end sites
  (`combat.py`'s ethereal exhaust pass and the turn-end-in-hand wrapper); switch
  `joss_paper.py:36` to read it. Failing test asserts a mid-turn Ethereal exhaust
  credits immediately.
- **radius** `turn_structure/G4`, `/G16` (the same relic), `creature_card_cmds/G8`
  (pile-change events generally).

### 42. `turn_structure/G18` — Pael's Eye's predicate is missing both C# clauses  [LIVE] [pinned]

- **sites** `turn_structure/G18` (1 entry).
- **impact** B — an extra turn is granted (or withheld) on the wrong turn.
- **divergence** `PaelsEye.AnyCardsPlayedThisTurn` (`PaelsEye.cs:149-156`) has two
  clauses `relics/paels_eye.py:27-34` has neither of: (1) on turn 1, merely
  *holding* Whispering Earring counts as having played (`PaelsEye.cs:152`), which
  switches Pael's Eye off for that turn; (2) the history scan filters
  `&& !e.CardPlay.IsAutoPlay`, so auto-plays never count. The sim's predicate is a
  bare `any(history.of_type(CardPlayedEntry, this_turn=True))` and
  `history.py:80-81` records every play including auto-plays.
- **observable** The record notes the two omissions **cancel** in the common
  Whispering-Earring case and diverge otherwise — read the record's full text
  before writing the test.
- **pin** `TestTurnStructureOrder::test_paels_eye_ignores_auto_plays`.
- **fix** Give `CardPlayedEntry` an `is_auto_play` flag (the missing flag is
  already documented as a known divergence at `relics/whispering_earring.py:36`),
  filter on it in `paels_eye.py:27-34`, and add the turn-1 Whispering Earring
  short-circuit. Failing test asserts an auto-played card does not suppress the
  extra turn.
- **radius** `turn_structure/G3` (the extra turn itself), `hook_dispatch/G4` (the
  per-play bracket that produces the history entries).

### 43. `power_cmd/step20` — `skip_next_tick` re-armed on re-stacking  [LIVE] [pinned]

- **sites** `power_cmd/step20` (1 entry).
- **impact** B — a player debuff lasts one turn longer than it should.
- **divergence** `cmds.py:331-332` sets `power.skip_next_tick = True` at function
  scope, **after** the new-vs-stacking if/else (`cmds.py:308-329`), on the shared
  `power` variable the stacking branch rebinds to `existing` — so the sim re-arms
  it on every re-stack; C# sets `SkipNextDurationTick` only in the new-power
  `Apply` path (`PowerCmd.cs:144-147`) and `ModifyAmount` (`PowerCmd.cs:215-271`)
  never touches it.
- **observable** Any player debuff applied twice in one turn (a second Vulnerable
  or Weak stack) skips a duration tick it should have taken, so it expires a turn
  late.
- **pin** `TestPowerCmdOrder::test_restacking_a_player_debuff_does_not_rearm_skip_next_tick`.
- **fix** Move the two lines inside the new-power branch of `PowerCmd.apply`.
  One-line-scope change, no hook machinery. **Cheapest live fix in the queue.**
  Failing test asserts a twice-applied Vulnerable expires on the same turn as a
  once-applied one plus its stacks.
- **radius** Same function as `power_cmd/G1` (Artifact's sign-aware typing),
  `/G3` (given/received phase collapse), `/G6` (the missing guards) — but
  independent of all three.

### 44. `creature_card_cmds/step38a` — Dense Vegetation's rest heal bypasses both rest hooks  [LIVE] [pinned]

- **sites** `creature_card_cmds/step38a` (1 entry).
- **content sites** **+1 event site**, `event/dense_vegetation/BR-38a` — the same rest-site heal, recorded from the event side. That record cites it as "turn_structure.json step 38a"; step 38a is in `creature_card_cmds.json`. See [Record inconsistencies](#record-inconsistencies-found-while-aggregating).
- **impact** B — a rest-site reward offer is skipped entirely.
- **divergence** C# (`PlayerCmd.cs:264-274` → `HealRestSiteOption.cs:106-113`)
  heals, then fires `Hook.AfterRestSiteHeal(player, isMimicked)` and
  `Hook.ModifyRestSiteHealRewards`, then offers the resulting rewards; the sim's
  `events/dense_vegetation.py:65-68` calls `self.run.heal(...)` directly, skipping
  `RunState.rest_heal` (`run.py:1089-1095`, which fires `after_rest_site_heal`) and
  `RunState.rest_heal_rewards` (`run.py:1097-1110`).
- **observable** The one gameplay caller of `MimicRestSiteHeal` is
  `Events/DenseVegetation.cs:90` and the event **is** ported: resting via Dense
  Vegetation heals but grants none of the rest-site reward machinery a real
  campfire rest grants.
- **pin** `TestCreatureCardCmdsOrder::test_dense_vegetation_rest_fires_the_rest_site_heal_hooks`.
- **fix** Point `dense_vegetation.py:65-68` at `run.rest_heal()` and
  `run.rest_heal_rewards()` instead of `run.heal()`. Failing test asserts the
  after-rest hooks fire and the reward offer appears.
- **radius** Isolated — one event, two call sites. Cheapest B-impact fix here.


---

### 45. `power/diamond_diadem/g1` — `AfterCombatEnd` resets `CardsPlayedThisTurn`; the sim does not  [LIVE by execution, unlabelled in the record] [**unpinned**]  ← **UNBLOCKED 2026-07-26**

- **sites** `power/diamond_diadem/g1` (1 entry). **Re-verdicted `waiver` → `gap`
  on 2026-07-26** because the old rationale delegated the applier's condition to
  `audit/records/relic/diamond_diadem`, which did not exist at the time.
  **It exists now.** The relic tier merged on 2026-07-26 and
  `relic/diamond_diadem` G1 reaches the same `gap` on the same executed witness,
  so the two records agree and this entry is no longer blocked on anything. The
  fix still belongs to the relic side; see entry 51 (`relic/_combat_reset`),
  which is the same missing-reset mechanism at 16 sites.
- **impact** B — a power silently fails to appear for a turn of a later fight.
- **divergence** `DiamondDiadem.cs` does three things: counts plays in
  `AfterCardPlayed` behind `Card.Owner == Owner` and
  `CombatManager.Instance.IsInProgress` (`:43-56`); grants the power from
  `BeforeSideTurnEnd` when `CardsPlayedThisTurn <= CardThreshold` (2) and zeroes
  the counter (`:58-70`); and **zeroes the counter again in `AfterCombatEnd`**
  (`:78-84`). `sts2_rl/relics/diamond_diadem.py:28-39` reproduces the first two
  and has no combat-end reset.
- **observable** Executed: play two harmless cards, then kill the last enemy with
  a third. The combat ends inside `play_card` (`sts2_rl/combat.py:417-418`), so
  `on_player_turn_end` never runs and the relic keeps
  `cards_played_this_turn == 3`; carried into the next combat, **turn 1 of that
  fight grants no Diamond Diadem power (3 > 2) where the game grants it.**
- **pin** Unpinned.
- **fix** Add an `on_combat_end` that zeroes the counter. One line — but the
  **fix belongs to the relic tier**, which is 0 of 258 audited, so this entry is
  the explicit blocked-on-relic-tier marker and cannot be closed from the power
  stream. Failing test asserts the power is granted on turn 1 of the next combat.
- **radius** The first concrete cost of the
  [unaudited relic tier](#what-this-queue-does-not-cover) showing up inside an
  audited one. Every relic whose state must survive or reset across a combat
  boundary is in the same unexamined class.

---

## 1C. Relic tier — live gaps  *(merged 2026-07-26)*

These 13 arrived with the relic tier. They are grouped here rather than
interleaved into 1A/1B because they landed as one batch and a reader wants to
see what one merge added; **each entry states its own grade**, and the grades are
what to order by. Two of them (58, 57) are not relic-tier entries at all — they
are corrections the relic tier's review forced on the `power` and `seam` tiers.

The relic tier is where the queue's collapse ratio is most extreme: **620 gap
entries, 404 mechanisms**, and the eleven families below carry 212 of the 620.
Fixing one site of any of them generally clears every site.

### 46. `relic/_is_allowed` — `Relic` has no `is_allowed` member at all  [LIVE] [**unpinned**]

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

### 47. `relic/_off_stream_draw` — relic draws taken from the legacy shared rng  [LIVE] [**unpinned**]

- **sites** 20 entries across 15 relics (`astrolabe`, `choices_paradox`,
  `dusty_tome`, `glass_eye`, `lost_coffer`, `neows_bones`, `new_leaf`,
  `royal_stamp`, `scroll_boxes`, `sea_glass`, `sere_talon`, `snecko_eye`,
  `toolbox`, `war_hammer`, `wing_charm`).
- **impact** **A — stream desync.** A replay stops converging outright.
- **divergence** C# names a specific stream (`Rng.Niche`, `PlayerRng.Rewards`)
  and the sim draws from the legacy shared `random.Random` instead — so the
  named stream's counter never advances and the shared one advances when the
  game's would not.
- **observable** Executed on `lost_coffer`: C#'s `PotionReward` draws from
  `Player.PlayerRng.Rewards`; the sim's `random_potion` leaves that counter at 0
  and mutates the shared run rng instead.
- **pin** Unpinned. Pinnable only as an assertion on a constructed `RunRngSet`'s
  draw counters — never against gameplay output, because out-of-combat draws on
  the unseeded shared rng make gameplay deltas nondeterministic.
- **fix** Route each site at its named stream. Same family as `event/EV-3` and
  `event/EV-9`, which are the event tier's version of this.
- **radius** The one relic family that is grade A, and therefore the one that
  matters for the five conformance seeds.

### 48. `relic/_stub` — 21 relics ported as no-ops on premises that are now false  [LIVE] [**unpinned**]

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

### 49. `relic/_reward_late_pass` — the two-pass reward dispatch collapsed into one  [LIVE] [**unpinned**]

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

### 50. `relic/_auto_keep` — the sim force-grants rewards the game offers  [LIVE] [**unpinned**]

- **sites** 19 entries across 15 relics (`calling_bell`, `toy_box`,
  `small_capsule`, `black_star`, `lava_rock`, `wongos_mystery_ticket`,
  `gambling_chip`, `lost_coffer`, `orrery`, `glass_eye`, `cauldron`,
  `choices_paradox`, `dream_catcher`, `driftwood`, `toolbox`).
- **impact** B, and **A at `lost_coffer`**, whose potion half also moves a stream.
- **divergence** The sim applies a house rule — "non-choice relic offers are
  auto-kept" — to screens the game lets the player decline.
  `WithSkippingDisallowed` appears on exactly **two lines in the whole C# source**
  (its definition and `NeowsBones.cs:43`); every other site is a plain skippable
  `RewardsCmd.OfferCustom`. **Re-verdicted `deliberate-divergence` → `gap` by the
  merge review**, because a decline is not invisible: `RelicReward.OnSkipped`
  writes `wasPicked: false` into run history and
  `sts2_rl/conformance/runner.py:430-431` reads that field back.
- **observable** The conformance runner already carries a bespoke workaround for
  this exact divergence — `_reconcile_node_relics` drops relics the sim
  auto-granted that the save did not pick, and calls `undo_after_obtained` to
  unwind the max-HP ones. **A divergence that needs a replay-time patch is not an
  identical observable.** `gambling_chip` is the worst case and is graded A: its
  purpose is not in the driver's `SKIPPABLE_PURPOSES`, and the driver
  short-circuits a full-hand selection without ever issuing a decision request,
  so the whole hand is mulliganed with no way to decline.
- **pin** Unpinned.
- **fix** Route these through the existing selection/skip machinery.
  `neows_bones`, `claws` and `glass_eye`'s transform half correctly stay
  `deliberate-divergence` — do not "fix" those.
- **radius** Also `rewards.py:474-479` and `:515-519` force-grant relics by the
  same house rule and have **no owning record anywhere**.

### 51. `relic/_combat_reset` — per-combat relic state is never reset  [LIVE] [**unpinned**]

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
- **fix** Add the combat-boundary reset dispatch. Note entry 45
  (`power/diamond_diadem`) and `relic/diamond_diadem` G1 are the *same* mechanism
  reached through a different hole — a combat that ends on the player's own turn
  never reaches `on_player_turn_end` at all — so fixing only the turn-end path
  will leave that one broken and looking fixed.
- **radius** 13 relics, one dispatch. `red_skull`'s −3 Strength is the defect
  `PROMPT.md` v6 names as the sweep's worst false clear.

### 52. `relic/_stable_shuffle` — the `StableShuffle` contract is mis-ported three ways  [LIVE] [**unpinned**]

- **sites** 14 entries across 7 relics (`sand_castle`, `war_hammer`,
  `war_paint`, `whetstone`, `stone_cracker`, `fragrant_mushroom`, `paels_tooth`).
- **impact** A/B — it changes *which* cards are affected, and at two sites *how
  many*.
- **divergence** Three separate errors ride on one helper: the pile is fed in the
  wrong orientation, the sort key is the sim's lowercase id rather than the
  game's UPPERCASE model id, and at `sand_castle`/`war_hammer` the `.Take(N)`
  limit is dropped entirely.
- **observable** Executed: `sand_castle` upgrades **all 10** cards of a 10-card
  deck where C# upgrades exactly 6; `war_hammer` upgrades 10 where C# upgrades 4;
  `fragrant_mushroom` picks a different card on 8 of 8 `Niche` seeds.
- **pin** Unpinned. The `.Take(N)` half pins trivially and *deterministically* —
  assert the COUNT — and survives the separate RNG-stream fix landing later.
- **fix** One shared helper. See [stable-shuffle tie order] in the seam notes:
  equal cards keep incoming order, so pass piles top-first and sort on the
  UPPERCASE id.
- **radius** Every relic that shuffles, plus the same helper's card-tier users.

### 53. `relic/_undo_clamp` — `undo_after_obtained` clamps instead of subtracting  [LIVE — tooling] [**unpinned**]

- **sites** 7 entries across 7 relics; **all five implementers do it**
  (`mango`, `strawberry`, `lees_waffle`, `looming_fruit`, `pear`).
- **impact** B — but against the *conformance runner*, not against the game.
- **divergence** `PROMPT.md` v6 item 3 is explicit that the *absence* of
  `undo_after_obtained` is `faithful` — nothing in the game un-picks a relic, so
  there is no source behaviour to diverge from. An implementation that EXISTS
  and violates its own stated contract is a different matter: these subtract the
  max-HP grant by clamping current HP to the new maximum instead of by undoing
  the heal.
- **observable** Executed at 75/80 HP, all five: grant then undo leaves
  **(80, 80)** where the contract requires (75, 80) — a silent **+5 HP** leak.
- **pin** Unpinned; a two-line pin.
- **fix** Subtract what was added. This is what defeats the conformance runner's
  DETECTOR 3 act-boundary HP assertion, and entry 50's `_reconcile_node_relics`
  workaround depends on it being correct.
- **radius** Tooling correctness rather than game fidelity — recorded because the
  helper is load-bearing for seed convergence.

### 54. `relic/_shop_price` — no price-modifier hook surface at all  [LIVE] [**unpinned**]

- **sites** 6 entries across 3 relics (`membership_card`, `the_courier`,
  and the Courier's restock half).
- **impact** B — gold spent differs for the rest of the run.
- **divergence** `hasattr(Relic, 'modify_merchant_price')` is **False**; the sim
  computes shop costs once at inventory creation and nothing can modify them.
- **observable** Executed: a stocked inventory reports the identical 14 costs
  with and without Membership Card, where C# halves every one. A bought slot also
  never restocks for the Courier.
- **pin** Unpinned. Pins deterministically given a seeded inventory — assert
  `costs_with == [c // 2 for c in costs_without]`, and note the game
  **truncates**, so 175 → 87.
- **fix** Add the hook and route `MerchantEntry` cost through it.
- **radius** Also blocks a correct port of any future price relic.

### 55. `relic/_victory_flatten` — `AfterCombatVictoryEarly` and `AfterCombatVictory` are one dispatch  [LIVE] [**unpinned**]

- **sites** 5 entries across 3 relics (`meat_on_the_bone`, `sword_of_stone`,
  `war_hammer`).
- **impact** C at most sites, **B at `meat_on_the_bone`**.
- **divergence** C# runs an Early pass before the main one; the sim has a single
  victory dispatch, so relics that must observe the pre-Early HP see the
  post-Early value.
- **observable** Executed: with `['burning_blood', 'meat_on_the_bone']` the sim
  heals to **44** where the game reaches **56** — the heal reads an HP that
  Burning Blood has already raised.
- **pin** Unpinned; pins as a plain HP assertion with two relics equipped.
- **fix** Split the pass. Sibling of `hook_dispatch/G3`.
- **radius** `war_hammer`'s entry was `faithful` until the merge review; its
  sibling `sword_of_stone` was already `gap` for the identical shape — a rule-3
  break that the review settled toward `gap`.

### 56. `relic/_auto_play_counted` — auto-plays counted as real card plays  [LIVE] [**unpinned**]

- **sites** 4 entries across 4 relics; `brilliant_scarf` is the live one.
- **impact** B — an off-by-one in which card is free for the rest of the turn.
- **divergence** `BrilliantScarf.cs:84-87` opens `if (cardPlay.IsAutoPlay)
  return;`. The sim's port increments unconditionally.
- **observable** Executed: one `auto_play_card` leaves
  `cards_played_this_turn == 1` where C# leaves **0**.
- **pin** Unpinned.
- **fix** Thread an `is_auto_play` flag through the play path. **Do not fix this
  over-broadly** — `PROMPT.md` bug class 29 exists because `rainbow_ring` and
  `razor_tooth` deliberately *do* count auto-plays; those entries are `faithful`
  and must stay so.
- **radius** The flag is missing from the sim's play path generally.

### 57. `damage_pipeline/N4` — the two-phase `ShouldDie` / `ShouldDieLate` priority is one pass  [LIVE] [**unpinned**]  ← corrected by the relic tier

- **sites** `damage_pipeline/N4`, `potion/fairy_in_a_bottle/ShouldDie`
  (2 entries). **Re-verdicted `waiver` → `gap` by the relic stream's batch 8**,
  carried into this branch by the merge, and given its second site by the potion
  tier on 2026-07-27 — the potion whose supposed out-of-scope-ness was the
  waiver's whole rationale now carries the same verdict at its own site.
- **impact** B — the wrong death-prevention resource is spent.
- **divergence** C# runs an early `ShouldDie` pass before the late one, so a
  potion that prevents death always resolves before a relic that does. The sim
  has one pass and the outcome falls out of listener order.
- **observable** The waiver's entire rationale was that `LizardTail` is the only
  listener in the source, "FairyInABottle being out of scope". **That
  reachability claim was false** — Fairy in a Bottle *is* ported, at
  `sts2_rl/potions.py:1242`, with a real `should_die`. Executed: holding a Fairy,
  the sim spends the **Tail** (listener order `['LizardTail','FairyInABottle']`,
  ending at 41 HP with the fairy still in the belt) where the game always spends
  the fairy first.
- **pin** Unpinned.
- **fix** Add the early pass. Note a distinct defect the same batch found and
  this entry does *not* cover: three sim powers are ported onto `should_die`
  where C# implements `ShouldCreatureBeRemovedFromCombatAfterDeath`.
- **radius** A worked example of the queue's own warning that "no ported content
  triggers this" is a dormant gap and not a waiver — here it was not even dormant.
  The potion tier's own record (`audit/records/potion/fairy_in_a_bottle.json`,
  `ShouldDie`) states the loop closed: "this record is that waiver's
  counterexample and matches the corrected verdict per binding rule 3".

### 58. `power/unmovable/g2` — the block props hoist, at a listener the census missed  [LIVE] [pinned]  ← found by the relic tier's rule-3 review

- **sites** `power/unmovable/g2` (1 entry), plus the census correction at
  `creature_card_cmds` G1. Same mechanism as entry 33 / `damage_pipeline/G3`.
- **impact** B — a doubled block gain is not doubled.
- **divergence** `BlockCmd.apply` hoists `is_powered_attack(props)` — Move **and
  not** Unpowered — out of the listeners and into the call site
  (`sts2_rl/cmds.py:145`). `Hook.ModifyBlock` calls every listener for every
  block gain and lets each self-gate, and `UnmovablePower.cs:27-30` gates on
  `!props.IsCardOrMonsterMove()`, which `ValuePropExtensions.cs:23-26` defines as
  exactly `props.HasFlag(ValueProp.Move)` — **Move alone**. It deliberately
  permits Unpowered, like Vambrace and Pael's Legion. The sim never reaches the
  listener.
- **observable** Executed: `Entrench` from 10 block with Unmovable 1 gives
  **20** in the sim and **30** in the game; the control powered Defend doubles
  correctly in both.
- **pin** **Pinned** —
  `test/test_hook_order.py::TestCreatureCardCmdsOrder::test_unpowered_card_block_still_runs_block_modifiers`
  already covers the fix.
- **fix** Push the gate back into the listeners. Nothing new is required; this
  entry exists because two records were wrong about who is affected.
- **radius** **This changes the mechanism's liveness basis.** G1's LIVE argument
  previously rested on Vambrace and Pael's Legion, both of which must be obtained
  and Pael's are shrine-gated. The Unmovable leg needs **no relic at all** —
  `unmovable` is in `IRONCLAD_POOL` and `entrench` comes from the ported Trash
  Heap event. Two records had it wrong in opposite directions: `power/unmovable`
  said `faithful` on a misread guard, and `creature_card_cmds` G1 simply omitted
  the power from its list. `py audit/tools/power_slot_probes.py
  ungated-modifiers` had already reported `UnmovablePower.cs:21` as UNGATED —
  the census existed and the record that needed it never ran it.

---

## 1D. Potion scope — live gaps unmasked by deleting the exclusion  *(2026-07-26)*

> **Historical section, and deliberately kept as one.** It records what the
> *exclusion* hid, in the window between deleting the clause (2026-07-26) and
> auditing the kind (2026-07-27). The tier itself is now
> [section 1F](#1f-potion-tier--live-gaps-merged-2026-07-27); these five entries
> are the ones that existed before it and are not re-listed there. Read this
> section for the failure mode, 1F for the coverage.

These five were not found by auditing anything new. **They were already in the
records, waived, and the waiver's entire support was the contract clause "Out of
scope everywhere: potions (deferred by Perry)".** Perry deleted the clause; the
waivers had nothing left holding them up; re-deriving the ten affected entries
turned five of them into LIVE gaps and three of those had never been looked at
by anyone.

That is the cost of expressing scope as an *exclusion* rather than as an
unaudited kind, and it is worth stating plainly: an exclusion is invisible to
every tool in this pipeline. `audit_status` cannot report it, `gap_queue` cannot
count it, and `validate` cannot reject a verdict that leans on it. Six of the
ten re-derived entries came back `faithful` — the clause was not hiding a
disaster — but it *was* hiding these five, and one of them
(`power/surrounded`) had additionally been recorded `faithful` on a claim about
the sim that was simply false.

**Two further entries flipped DORMANT → LIVE** without needing a new mechanism,
because they were already `gap` and only their *reachability* rested on the
clause. Both said, in effect, "the only ported source is a potion, and potions
are out of scope, so nothing applies this":

- **`power/demise/AfterSideTurnEnd`** (mechanism `power/_side_turn_slot`,
  entry 17). Powdered Demise is ported at `sts2_rl/potions.py:869-877` and sits
  in the generation pool at `sts2_rl/potion_pools.py:57` as uncommon.
- **`power/regen/AfterSideTurnEnd`** (same mechanism). Regen Potion is ported at
  `sts2_rl/potions.py:605-615` and is in the pool at `potion_pools.py:58`; it is
  in `NOT_GENERATED_IN_COMBAT`, which bars in-*combat* generation only, not the
  reward pool.

Both had named their own trigger as "any non-potion source". **The trigger had
already fired** — it was the potion. This is the exact failure mode the queue
warns about under `waiver`: a dormancy claim that describes a *scope decision*
rather than a fact about today's content is not a dormancy claim at all.

### 59. `card/alchemize/OnPlay` — an entire ported card was waived  [LIVE] [**unpinned**]

- **sites** `card/alchemize/OnPlay`, rolling up guards G1 and G2 (entries 60–61).
- **impact** B.
- **divergence** `Alchemize.cs:24` is one statement with two halves —
  *generate* a random in-combat potion, then *procure* it through
  `PotionCmd.TryToProcure`. **The whole card was `waiver`** because its whole
  body is potion procurement.
- **observable** The generation half re-derived clean: the right named stream
  (`Rng.CombatPotionGeneration`), exactly 2 draws executed, and the in-combat
  filter set is exactly the three C# potions overriding
  `CanBeGeneratedInCombat`. The procure half is entries 60 and 61.
- **pin** Unpinned.
- **fix** See 60 and 61; this entry is the rollup.
- **radius** Also a rule-3 correction: `relic/sozu` G1 already filed this
  mechanism LIVE **and names Alchemize by name**, as do `relic/delicate_frond`
  G2/G3 and `relic/belt_buckle`. One mechanism, two answers — the contract
  caused the disagreement.

### 60. `card/alchemize/g2` — combat-side procurement skips the `ShouldProcurePotion` gate  [LIVE] [**unpinned**]

- **sites** `card/alchemize/g2`; same mechanism at `relic/sozu` G1,
  `relic/delicate_frond` G2/G3.
- **impact** B.
- **divergence** C# has exactly one procure entry point and it is gated;
  `Sozu.cs:17-20` is the source's only `ShouldProcurePotion` implementer. **The
  sim splits the operation:** `RunState.add_potion` runs the gate
  (`sts2_rl/run.py:480`), `PlayerCombatState.add_potion` does not — and its own
  docstring concedes it while citing the deleted clause (`sts2_rl/player.py:112-115`:
  *"does not run the Hook.ShouldProcurePotion gate today … out of scope"*). The
  gate itself is ported and works (`sts2_rl/relics/sozu.py:26-27`).
- **observable** Executed: with `relics=[]` and with `relics=['sozu']` the belt
  ends `['explosive_ampoule', None, None]` **both times**, where C# leaves the
  Sozu owner's belt empty.
- **pin** Unpinned; pins trivially — assert the Sozu owner's belt stays empty.
- **fix** Route combat-side procurement through the same gate. **Delete the
  docstring's out-of-scope justification in the same commit** — it is the only
  thing that made this look intentional.
- **radius** Every combat-side potion source: Alchemize, Delicate Frond,
  Petrified Toad.

### 61. `card/alchemize/g3` — no `AfterPotionProcured` event on the success branch  [LIVE] [**unpinned**]

- **sites** `card/alchemize/g3`; same mechanism at `relic/belt_buckle`
  (`AfterPotionProcured`) and `relic/delicate_frond`.
- **impact** B — and the observable is not a potion-system detail.
- **divergence** `TryToProcure` fires `Hook.AfterPotionProcured` on success.
  `BeltBuckle.cs:63-70` removes its 2 Dexterity the moment a potion is procured
  mid-combat — it is the half of "while you have no potions" that enforces the
  *no*. The sim's port implements only `on_potion_used`
  (`sts2_rl/relics/belt_buckle.py:32-33`) and `sts2_rl/player.py:107-121`
  dispatches nothing at all.
- **observable** Executed: `relics=['belt_buckle']` starts at
  `[('dexterity', 2)]` with an empty belt; after **one** Alchemize the belt is
  `['attack_potion', None, None]` and Dexterity is **still 2**, where C# leaves
  0. Dexterity changes every Block number for the rest of the fight.
- **pin** Unpinned.
- **fix** Add the hook and dispatch it from the combat-side procure path.
- **radius** Same dispatch as entry 60; one fix likely serves both.

### 62. `power/shackling_potion/g8` — the applier targets `not is_gone` where C# targets `HittableEnemies`  [LIVE] [**unpinned**]

- **sites** `power/shackling_potion/g8`.
- **impact** B.
- **divergence** The potion applies to `creature.CombatState.HittableEnemies`;
  the sim's applier targets everything `not is_gone`. **Why this one is live
  where its siblings are dormant:** `power/the_bomb`, `power/inferno` and
  `power/rolling_boulder` call the same mechanism dormant because
  `DamageCmd.deal` re-checks `should_allow_hitting` downstream. **`PowerCmd.apply`
  has no such check** — that is `power_cmd`'s G6 — so a *debuff* actually lands
  where damage would not.
- **observable** Executed against a mid-revival Fogmog: the sim targets **3**
  enemies, the game targets **2**, and the unhittable one ends at
  `strength −7`.
- **pin** Unpinned.
- **fix** Use the hittable-enemy predicate in the applier. Note this is the
  *second* live consequence of `PowerCmd.apply` lacking the
  `CanReceivePowers`/`should_allow_hitting` backstop — see entry 25.
- **radius** Any potion or power that targets "all enemies" during a revival
  window.

### 63. `power/surrounded/BeforePotionUsed` — the sim has one potion hook where C# has two  [LIVE] [**unpinned**]

- **sites** `power/surrounded/BeforePotionUsed`. **A new mechanism — nothing in
  the queue covered it.**
- **impact** B.
- **divergence** `PotionModel.OnUseWrapper` fires two hooks on either side of
  the effect — `PotionModel.cs:297 Hook.BeforePotionUsed`, `:325 OnUse`,
  `:338 Hook.AfterPotionUsed` — and `SurroundedPower.cs:82` is the source's
  **only** `BeforePotionUsed` implementer. The sim has **one** hook:
  `sts2_rl/hooks.py:566` `on_potion_used`, whose own docstring says it "mirrors
  AfterPotionUsed", dispatched at `sts2_rl/combat.py:610` — *after*
  `potion.use(...)` at `:609`. So Surrounded's facing flip runs a phase late.
- **observable** Executed on the ported Kaiser Crab boss, Fire Potion into a
  1-HP Crusher: the sim ends facing **left** (1.5× multiplier), the game ends
  **right** (1.0×) — **80 → 44 HP in the sim vs 80 → 56 in the game** on one
  Precision Beam.
- **pin** Unpinned.
- **fix** Add `before_potion_used` and dispatch it before `potion.use`. This
  entry was `faithful` until 2026-07-26 on a rationale asserting the hook "is
  ported and correct" — it is neither.
- **radius** The whole potion-use bracket; every `AfterPotionUsed` implementer
  (`BeltBuckle.cs:81`, `ReptileTrinket.cs:22`) currently shares one slot with
  the only Before implementer.

---

## 1E. Monster tier — live gaps  *(merged 2026-07-27)*

The monster stream audited **109 of 109 units** and filed **45 gap entries, 28
of them LIVE, across 23 mechanisms** — 18 anchored in the monster tier and 5
joining a mechanism a seam or the power tier already owned. Every gap entry in
this tier carries the explicit `"live": true|false` field, which is why none of
them lands in the "unlabelled" bucket in the Summary; `gap_queue.py` now reads
that field in preference to its prose scan.

Two things about this merge are worth reading before the entries.

**It confirmed a negative that matters more than most of the positives.** The
stream's brief was to hunt monsters misreading a `RandomBranchState.AddBranch`
integer argument — the class that broke seed convergence and that entry 2
records. There is **no sixth monster**: the population is exactly the five
`monster_state_machine` G1 already named. That negative was established over the
27 hand-rolled ports G1's own probe structurally cannot reach, by rebuilding
each C# `GenerateMoveStateMachine` node-for-node on the sim's machine and diffing
it against the port on identically seeded streams.

**But the same method found a bug class no parameter check can catch** — entry
64, branch add order, where the parameters are identical, the marginal
distribution is identical, and only a per-draw sequence diff on a shared stream
separates the two.

**Amendment to entry 2 (`monster_state_machine/G1`).** The monster tier added
five sites to it and one route to its liveness argument; it is not a new
mechanism and gets no number of its own.

- **sites** now 6: the seam's own `step13` plus `monster/flail_knight`,
  `monster/hunter_killer`, `monster/mysterious_knight`,
  `monster/scroll_of_biting`, `monster/spectral_knight`. (`fake_merchant` is the
  fifth port G1 names and carries the same misread; it has no monster record
  because the roster resolves it to the event tier.)
- **new** `monster/mysterious_knight` is a **second reachable route** that G1's
  liveness list does not name: it overrides no move machine, so it inherits
  `FlailKnight`'s — including the misread arguments — and it is reached through
  the ported Lantern Key event (`events/the_lantern_key.py:41`) rather than
  through the Hive elite pool.
- **confirmed** `state_machine_probes.py mismatch` still reports 12 resolved
  pairs / 13 C# `RandomBranchState`s / 7 exact matches / 5 misreads, unchanged;
  and the two counter-evidence ports (`fossil_stalker` reading `maxRepeats=2`,
  `two_tailed_rat` reading `cooldown=3`) were re-derived from the overload table
  and are correct.

### 64. `monster/inklet/GenerateMoveStateMachine` — branch ADD ORDER reversed  [LIVE] [**unpinned**]

- **sites** 1 (`monster/inklet`), but the *class* is pool-wide and unswept: no
  existing tool looks for it.
- **impact** **A — stream desync.** Same draw count, different move.
- **divergence** `Inklet.cs:73-74` adds the live `RAND` branch's two arms in the
  order `PIERCING_GAZE_MOVE` then `WHIRLWIND_MOVE`, both `CannotRepeat` at weight
  `1f`. `inklets.py:62-65` rolls `['WHIRLWIND', 'PIERCING_GAZE']` — the opposite
  mapping. Branch add order is observable by `monster_state_machine` step 14: the
  walk subtracts weights **in add order** and returns the first branch at
  `num <= 0`, so with equal weights the same draw resolves to a different branch.
- **observable** Executed: **0 / 20 000 agreement** on identically seeded
  `MonsterAi` streams, while the marginal is preserved (sim 10022 WHIRLWIND /
  9978 PIERCING_GAZE, game 10022 PIERCING_GAZE / 9978 WHIRLWIND). Full-run diffs
  over both `is_middle` arms diverge at the **first** `JAB → RAND` transition on
  every seed with **identical draw counts (20 vs 20)** — pure move content, not
  stream drift.
- **why it is not entry 2** G1 is about integers read as weights. Here every
  integer is right; the *order* is wrong. Recorded as its own mechanism, and the
  monster record says so explicitly, so `gap_queue.py` pins the exclusion in
  `_FAMILY_OVERRIDE` rather than letting a text match merge the two.
- **pin** Unpinned, and **the existing pin actively protects the defect**:
  `test/test_monster_branch_audit.py::TestInkletMoveSequence::test_jab_rolls_exactly_one_draw_matching_game_primitive`
  computes its own expectation using the same reversed order it should be
  checking, and its docstring's "a true 50/50 every time" is a true statement
  about the marginal that is silent about the mapping. **A pin that derives its
  expectation from the sim is not a pin.**
- **fix** Swap the two arms in `inklets.py`, then rewrite the pin to name the C#
  source order as a constant.

### 65. `monster/_encounter_selection_rng` — the per-encounter `Rng` does not exist in the sim  [LIVE] [**unpinned**]

- **sites** 3 (`monster/corpse_slug`, `monster/slithering_strangler`,
  `monster/scroll_of_biting`).
- **impact** **A — stream desync, and worse: replay non-determinism.**
- **divergence** `EncounterModel` owns a deterministic per-encounter `Rng`
  (constructed from the run seed + total floor + the encounter id hash) and uses
  it for composition and per-monster setup. The sim has **no analogue of that
  concept at all**: ~20 `create_monsters` overrides accept a `selection_rng` and
  ignore it, falling back to the shared combat `random.Random`.
- **observable** Executed on Corpse Slug: **6 of 10 seed/floor configurations
  disagree** on which move each slug starts on, and the selection stream is drawn
  **0** times where the game draws 1. Under a *fixed* seed the sim returned
  `[2,0,1] [0,1,2] [1,2,0] [1,2,0]` on four consecutive runs — so Corpse Slug
  replays do not even reproduce themselves. Slithering Strangler leaves 2–3 draws
  unconsumed; Scroll of Biting's starter index diverges from seed 0 onward.
- **why it is not entry 66** There the stream exists in the sim and is unused —
  a one-line swap. Here the missing thing is a concept, and the fix has to build
  it before any site can be corrected.
- **fix** Give `Encounter` a parity Rng derived the way `EncounterModel`'s is,
  and thread it through `create_monsters`. This is the same shape as
  `relic/_off_stream_draw` and `event/EV-3` at encounter-generation scope.

### 66. `monster/_off_stream_draw` — a named C# stream replaced by the shared combat rng  [LIVE] [**unpinned**]

- **sites** 2 (`monster/fabricator`, `monster/thieving_hopper`).
- **impact** **A — stream desync.**
- **divergence** PROMPT.md bug class 16 at two monster sites.
  `Fabricator.cs:115` is `base.RunRng.MonsterAi.NextItem(items)` — the same
  dedicated stream `MonsterModel.RollMove` names — and `fabricator.py:176` is
  `ctx.hooks.combat._rng.choice(choices)`. `ThievingHopper.cs:222` is
  `base.RunRng.CombatCardGeneration.NextItem(enumerable)` and
  `thieving_hopper.py:94` is `ctx.combat._rng.choice(candidates)`.
- **observable** Under parity `CombatRng` the two streams are distinct, so both
  the named stream's counter and the shared one diverge from the game's on every
  Fabricator spawn and every Thievery steal.
- **fix** One line each — **the sim already has both streams**
  (`combat_rng.monster_ai`, `combat_rng.card_gen`, the latter currently unused).

### 67. `monster/queen/AfterDeath` — the amalgam's death does not replace the telegraphed move  [LIVE] [**unpinned**]

- **sites** 1 (`monster/queen`), and it is **the one of the eleven unclaimed C#
  monster hook overrides that is not presentation**.
- **impact** B — the player sees the wrong intent for a turn.
- **divergence** `monster_state_machine` boundary hole 5 handed 11
  `AbstractModel` hook overrides to the content tier. Ten reduce to a music
  parameter, a barks line, a texture assignment or an animation call — the
  `KinPriest` N6 shape. `Queen.cs:226-232` does not: inside the same
  presentation shell it sets `HasAmalgamDied = true`, nulls `Amalgam`, and — if
  the Queen's telegraphed move is Burn Bright — calls
  `SetMoveImmediate(EnragedState)`, which is `NextMove = state` **plus**
  `ForceCurrentState(state)` (`MonsterModel.cs:420-432`). The sim has no
  listener and substitutes at *resolution* time instead (`queen.py:169-171`).
- **observable** Executed with the Queen parked on Burn Bright and the amalgam
  at 0 HP: the sim still telegraphs `BURN_BRIGHT_FOR_ME_MOVE intent=BUFF` where
  the game shows `ENRAGE_MOVE`. The effect (+2 Strength, 0 block) and the next
  move both match, and `state_log` agrees because `ForceCurrentState` does not
  log — so it is precisely an intent/replay divergence.
- **fix** Move the substitution to the amalgam's death rather than the Queen's
  turn. Note the sim has **no `MonsterModel` listener category at all**
  (`hook_dispatch` G5), so the fix is open-coded wherever the amalgam dies.

### 68. `monster/living_fog/g1` — a mid-combat spawn is appended instead of slotted  [LIVE] [**unpinned**]

- **sites** 1 (`monster/living_fog`), but the rule is engine-wide and the check
  cleared two other spawners, so the site count is the finding.
- **impact** **A — turn order and every enemy index flip.**
- **divergence** `CombatManager.AddCreature` re-sorts `Enemies` by
  `Encounter.Slots.IndexOf(SlotName)` whenever the added creature carries a slot
  (`SortEnemiesBySlotName`). The sim's BLOAT spawn appends.
- **observable** Executed on a real driven `CombatState`: sim `[LivingFog,
  GasBomb]` vs game `[GasBomb, LivingFog]`. Both the turn order and the enemy
  index (1 vs 0) invert, and `combat_driver.py:184-191` zips enemy state
  **positionally**, so a conformance replay mis-attributes every subsequent
  enemy assertion.
- **fix** `CreatureCmd.add(index=)` already exists for exactly this rule (it is
  how Ovicopter's eggs are placed); route the slot through it.
- **method note** This is PROMPT.md class 20 pointed at creature lists: trace
  `CreatureCmd.Add`'s *enclosing* call chain, not just the spawn site. The same
  check **cleared** `gremlin_merc` (no `Slots` override → the sort is a no-op)
  and `phantasmal_gardener` (generated in slot order).

### 69. `monster/ovicopter/g2` — egg slots are filled forwards, not backwards  [LIVE] [**unpinned**]

- **sites** 1 (`monster/ovicopter`).
- **impact** A — enemy order and indices, on the legacy path only.
- **divergence** `Ovicopter.cs:87` picks `Encounter.Slots.LastOrDefault(s => no
  enemy occupies s)` against `Slots = [egg1..egg5, ovicopter]`, so the game fills
  egg slots **backwards**. The sim's legacy arm does not.
- **observable** Executed on the real encounter: the game yields
  `['Ovicopter','ToughEgg','ToughEgg','ToughEgg']`.
- **dual-mode caveat, and it generalises** The unit gates on
  `combat_rng.is_parity`: the **parity arm is faithful and the legacy arm
  diverges** — and legacy is the default and the RL training path
  (`combat.py:95`, `run.py:140-144`). A dual-mode port has two verdicts and both
  must be audited; a reviewer who reads only the parity arm clears it.

### 70. `monster/punch_construct/AfterAddedToRoom` — `StartingHpReduction` cuts max HP, not current  [LIVE] [**unpinned**]

- **sites** 1 (`monster/punch_construct`).
- **impact** B — the monster is permanently smaller than the game's.
- **divergence** `PunchConstruct.cs:75-78` is
  `SetCurrentHpInternal(Max(1, CurrentHp - r))` with `MaxHp` fixed at 55; the
  sim's Punch Off event cuts **`max_hp`** (`events/punch_off.py:27-28`).
- **observable** Executed at seed 4: sim `hp=53 max_hp=53` and `hp=49
  max_hp=49` against a game `MaxHp` of 55. Both constructs roll `NextInt(2,10)`
  so the reduction is always `> 0` and the divergence always fires.
- **method note** Invisible from the monster file: the C# member exists on the
  model, the sim has no member at all, and the *encounter* re-implements it.
  Whenever a C# model has a settable property no sim class mirrors, grep the C#
  property's **setters** and audit the sim site that replaced it.

### 71. `monster/the_insatiable/g1` — `CardPilePosition.Random` collapsed into an append  [LIVE] [**unpinned**]

- **sites** 1 (`monster/the_insatiable`).
- **impact** **A — three missing draws per cast, plus a different pile order.**
- **divergence** `TheInsatiable.cs:130-137` loops `i in [0,6)` calling
  `CardPileCmd.AddGeneratedCardToCombat(card, i < 3 ? PileType.Draw :
  PileType.Discard, null, CardPilePosition.Random)`, and
  `CardPileCmd.cs:512-514` resolves `Random` to an `Rng.Shuffle.NextInt` draw
  **for every pile type**. The sim's `add_to_draw` reproduces it; `add_to_discard`
  appends.
- **observable** **3 draws where the game takes 6**, and the three discarded
  Frantic Escapes land in a fixed order instead of a random one.
- **rule-3 note** `power/sandpit`'s guard "Frantic Escape as the counterplay" is
  recorded `faithful`: it compared counts and pile types but **not**
  `CardPilePosition`, and so cleared this. Reported, not edited — see
  [record inconsistencies](#record-inconsistencies-found-while-aggregating).
- **fix** Give `add_to_discard` the position argument `add_to_draw` already has.

### 72. `monster/thieving_hopper/g2` — the steal-priority predicates each drop a clause  [LIVE] [**unpinned**]

- **sites** 1 (`monster/thieving_hopper`).
- **impact** B — the wrong card is stolen.
- **divergence** `ThievingHopper.cs:31-69` defines `_stealPriorities` as four
  predicates tried in order, the first that matches anything narrowing the
  candidate set. `thieving_hopper.py:68-76` transliterates all four and loses a
  clause from each: **Event** from tier 2, **Quest** from tier 3, and both
  `Imbued` arms.
- **observable** Reachable on ported content, executed: 19 EVENT and 3 QUEST
  cards are ported, and `ImbuedEnchantment` is granted by the ported Electric
  Shrymp — so all four dropped clauses can decide a real steal.

### 73. `monster/tough_egg/g2` — an inclusive `randint` against an exclusive `NextInt`  [LIVE] [**unpinned**]

- **sites** 1 (`monster/tough_egg`), and the bound convention is pool-wide.
- **impact** B — an HP value the game cannot produce.
- **divergence** `ToughEgg.cs:172` rolls
  `base.RunRng.Niche.NextInt(HatchlingMinHp, HatchlingMaxHp)` = `NextInt(19, 22)`,
  and `Rng.cs:95-109` documents and implements the second argument as
  **max-EXCLUSIVE**. Python's `random.randint(a, b)` is inclusive of `b`.
- **observable** Executed: the sim returns 22, which the game cannot roll.
- **method note, and the reason this is not a whole family** The convention is
  handled correctly everywhere else, for a subtle reason worth recording: the
  game's *HP* range is inclusive of `MaxInitialHp` precisely because
  `Creature.cs:378` pre-computes `MaxInitialHp + 1` and feeds that same value to
  both `Enumerable.Range` and the fallback `NextInt`. The parity port puts its
  two `+ 1`s in exactly those two places. Batch 1 executed all 9 of its HP ranges
  (400 seeded combats each) and observed the top endpoint every time. **Check the
  bound convention, not just the constants.**

### 74. `monster/slumbering_beetle/g1` — a `Stun(creature, delegate, nextMoveId)` body run at call time  [LIVE] [**unpinned**]

- **sites** 1 (`monster/slumbering_beetle`).
- **impact** B — an in-turn state divergence: the beetle loses Plating a phase
  early.
- **divergence** `SlumberPower.cs:22-32`'s `AfterDamageReceived` decrements on
  unblocked damage and, at 0, calls
  `CreatureCmd.Stun(Owner, slumberingBeetle.WakeUpMove, "ROLL_OUT_MOVE")` —
  which makes the Plating removal the **stun move's perform body**, run on the
  beetle's own stunned turn. The sim inlines it at damage time.
- **observable** Executed: the sim strips Plating mid-player-turn. No HP-number
  consequence could be proved (Plating grants block at side-turn-end), so the
  entry states the observable as the in-turn state/power-list divergence it is
  rather than overclaiming.
- **method note** Whenever the C# hands a method to `CreatureCmd.Stun`, its body
  runs on the victim's turn, not at call time. A port that inlines it moves the
  effect a phase earlier.

### 75. `monster/_second_intent_dropped` — a two-intent `MoveState` telegraphed as one  [LIVE] [**unpinned**]

- **sites** 2 (`monster/vantom` DISMEMBER, `monster/vine_shambler`
  GRASPING_VINES).
- **impact** B — the telegraph is wrong; the effect is right.
- **divergence** Both C# moves are constructed with **two** `AbstractIntent`s —
  `SingleAttackIntent` + `StatusIntent(3)` for Dismember, `SingleAttackIntent` +
  `CardDebuffIntent` for Grasping Vines — and each port keeps only the attack.
  The three Wound cards and the `TangledPower` **are** applied, so only the
  telegraph diverges.
- **observable** Reachable and read: `env.py:163-167` and `full_env.py:568-571`
  consult `Intent.has()` for exactly those two types, so an RL policy sees a
  plain attack where the game shows attack + status / attack + card-debuff.
- **the sim can already express it** `Intent.also` is the mechanism, and
  `kin_priest` and `axe_ruby_raider` use it — so this is an omission at two
  sites, not a missing capability. Of 45 moves checked by probe, exactly these
  two mismatch.

---

## 1F. Potion tier — live gaps  *(merged 2026-07-27)*

51 records, 152 gap entries, 83 labelled live, **24 mechanisms**. The entry
count is the highest per record in the project and it is not 152 findings:
102 entries are the two shared guards below, carried once per unit.

Nothing in this section was reachable before 2026-07-26 — see
[1D](#1d-potion-scope--live-gaps-unmasked-by-deleting-the-exclusion-2026-07-26)
for why. Four of these mechanisms carry the project's first **content-anchored
pins**.

### 46a. `potion/_use_pipeline` — `PotionModel.OnUseWrapper` is covered by no seam  [LIVE] [**unpinned**]

- **sites** 51 — one per potion record (`potion/<unit>/gN`, the guard each
  record labels `W`). Full list: `potion/ashwater/g5`, `potion/attack_potion/g6`,
  `potion/beetle_juice/g2`, `potion/blessing_of_the_forge/g4`,
  `potion/block_potion/g2`, `potion/blood_potion/g4`,
  `potion/bottled_potential/g3`, `potion/clarity/g2`,
  `potion/colorless_potion/g7`, `potion/cure_all/g2`,
  `potion/dexterity_potion/g2`, `potion/distilled_chaos/g5`,
  `potion/droplet_of_precognition/g5`, `potion/duplicator/g2`,
  `potion/energy_potion/g1`, `potion/entropic_brew/g6`,
  `potion/explosive_ampoule/g3`, `potion/fairy_in_a_bottle/g6`,
  `potion/fire_potion/g2`, `potion/flex_potion/g2`, `potion/fortifier/g2`,
  `potion/foul_potion/g5`, `potion/fruit_juice/g2`, `potion/fysh_oil/g3`,
  `potion/gamblers_brew/g5`, `potion/gigantification_potion/g1`,
  `potion/glowwater/g3`, `potion/heart_of_iron/g1`, `potion/liquid_bronze/g1`,
  `potion/liquid_memories/g3`, `potion/lucky_tonic/g1`,
  `potion/mazaleths_gift/g2`, `potion/orobic_acid/g4`,
  `potion/potion_of_binding/g5`, `potion/potion_shaped_rock/g2`,
  `potion/powdered_demise/g1`, `potion/power_potion/g5`,
  `potion/radiant_tincture/g1`, `potion/regen_potion/g2`,
  `potion/shackling_potion/g4`, `potion/ship_in_a_bottle/g1`,
  `potion/skill_potion/g5`, `potion/snecko_oil/g5`, `potion/soldiers_stew/g3`,
  `potion/speed_potion/g1`, `potion/stable_serum/g1`,
  `potion/strength_potion/g3`, `potion/swift_potion/g1`,
  `potion/touch_of_insanity/g4`, `potion/vulnerable_potion/g2`,
  `potion/weak_potion/g2`.
- **impact** B, twice over — a missing hook dispatch and a missing draw.
- **divergence** `PotionModel.cs:291-342` is the use pipeline for every potion:
  `:293` `RemoveBeforeUse`, `:297` `Hook.BeforePotionUsed`, `:327` `OnUse`,
  `:336` `History.PotionUsed`, `:338` `Hook.AfterPotionUsed`, `:340`
  `CheckForEmptyHand`. The sim implements `RemoveBeforeUse`
  (`sts2_rl/combat.py:603-606`) and `AfterPotionUsed`
  (`sts2_rl/combat.py:610`) and **neither of the other two dispatches**.
  Structurally, `PotionModel` is in `harness.MODEL_ROOT_CLASSES`, so no unit
  record enumerates it — and no seam record covers it either, so this layer was
  audited nowhere at all.
- **observable** Two, both already owned and matched here per rule 3 rather than
  re-derived. (1) `Hook.BeforePotionUsed` has exactly one implementer,
  `SurroundedPower.cs:82`, ported at `sts2_rl/powers.py:2523`: throwing a
  targeted potion at the far Kaiser Crab arm does not turn the player to face
  it — `power/surrounded/BeforePotionUsed`, entry in
  [1D](#1d-potion-scope--live-gaps-unmasked-by-deleting-the-exclusion-2026-07-26).
  (2) `CheckForEmptyHand` (`CombatManager.cs:887-893`) has two callers,
  `CardModel.cs:1992` and `PotionModel.cs:340`, and the sim's only
  `on_hand_emptied` site is `sts2_rl/player.py:197` — the end-of-turn flush
  `CombatManager.cs:880-883` explicitly excludes: `relic/unceasing_top`'s G1,
  executed with an Ashwater witness. Reachable from **every** potion, because C#
  tests the hand *after* the use.
- **pin** Unpinned as a mechanism. Its two observables are pinned at their own
  sites' entries.
- **fix** Two independent one-liners in `sts2_rl/combat.py`'s `use_potion`: add
  a `before_potion_used` dispatcher and call it before `potion.use`, and call
  the empty-hand check after. **The structural fix is a `potion_pipeline`
  seam** (or extending `creature_card_cmds` to cover `PotionModel`, `PotionCmd`
  and `Player`'s belt verbs); until one exists every future potion record will
  carry this guard again.
- **radius** 51 records. Also the reason to check the other twelve entries in
  `MODEL_ROOT_CLASSES` against the six seams — this is the only root known to be
  uncovered, and nothing would have reported a second one.
- **narration** `audit/content/potion/shared-mechanisms.md`.

### 46b. `potion/_choose_a_card_screen` — the generated-card potions skip `FromChooseACardScreen`  [LIVE] [**unpinned**]

- **sites** 8 — `potion/attack_potion/OnUse`, `potion/attack_potion/g2`,
  `potion/colorless_potion/OnUse`, `potion/colorless_potion/g3`,
  `potion/power_potion/OnUse`, `potion/power_potion/g2`,
  `potion/skill_potion/OnUse`, `potion/skill_potion/g2`.
- **impact** B — a different card enters the hand, and the skip option does not
  exist.
- **divergence** Each of the four potions generates three cards and hands them
  to `CardSelectCmd.FromChooseACardScreen(..., canSkip: true)`
  (`CardSelectCmd.cs:216-261`), adding the result only `if (cardModel != null)`.
  The sim forks on `combat.combat_rng.is_parity`: the parity arm defers to
  `CombatState.offer_screen_selection` (`sts2_rl/combat.py:618-637`) and honours
  a recorded `SelectCardFromScreen skip`; the **legacy arm takes `cards[0]`
  unconditionally**.
- **observable** The RL env and every non-parity test take the legacy arm
  (`sts2_rl/full_env.py:788` builds the env with no `rng_set`), so in training
  the potion is deterministic in generated order, the other two candidates do
  not exist, and the potion can never be declined. The observation encoder reads
  the resulting hand.
- **dormancy** Live. `orobic_acid` is **not** a site and the distinction is
  deliberate: it has no screen at all in the source, which its record records as
  a PROMPT.md class-29 counter-example.
- **pin** Unpinned.
- **fix** Give the legacy arm the same `offer_screen_selection` path with a
  policy hook for the pick, or expose the choice as an env action.
- **radius** 4 potions; the generation half (`GetDistinctForCombat` → one
  `UnstableShuffle` on `Rng.CombatCardGeneration`) is verdicted faithful at all
  four, so the draw counts are already right and this is a state-only fix.

### 46c. `potion/_any_time_usage` — `PotionUsage.AnyTime` has no sim path at all  [LIVE] [**unpinned**]

- **sites** 4 — `potion/blood_potion/Usage`, `potion/entropic_brew/Usage`,
  `potion/foul_potion/Usage`, `potion/fruit_juice/Usage`.
- **impact** B, and A for a replay — a recorded run that drinks one of these
  outside combat cannot be replayed at all.
- **divergence** `PotionUsage.AnyTime` means the Use button is live outside
  combat, and `OnUseWrapper` is written for it (`PotionModel.cs:294,298,334,336`
  all null-check the combat state). The sim models no `usage` attribute and has
  exactly one use path: `py audit/tools/potion_probes.py sweep-usage` finds one
  `def use_potion` in `sts2_rl/`, on `CombatState`. The conformance layer agrees
  — `UsePotion` is a combat-only command in both
  `sts2_rl/conformance/combat_driver.py:16` and
  `sts2_rl/conformance/runner.py:147-150`.
- **observable** All four potions are ported and reachable. Drinking Fruit Juice
  on the map changes max HP, which the runner asserts at the next act boundary;
  the `UsePotion` command instead falls to the room-boundary branch and is never
  executed, so the belt and the HP both drift.
- **pin** Unpinned.
- **fix** A run-level `use_potion` on `RunState` plus a `usage` attribute; the
  four potions' own effects are already implemented.

### 46d. `potion/_min_select_zero` — `CardSelectorPrefs` MinSelect 0 is not modelled  [LIVE] [**unpinned**]

- **sites** 4 — `potion/ashwater/OnUse`, `potion/ashwater/g1`,
  `potion/gamblers_brew/OnUse`, `potion/gamblers_brew/g1`.
- **impact** B — a whole hand's worth of cards.
- **divergence** Both potions build `CardSelectorPrefs(prompt, 0, 999999999)`.
  `FromHand`'s auto-resolve shortcut is `list.Count <= prefs.MinSelect`
  (`CardSelectCmd.cs:708-711`), false for any non-empty hand at MinSelect 0, so
  the screen is always shown and the player may confirm none.
  `CombatState.select_cards` (`sts2_rl/combat.py:575-581`) has no
  minimum/maximum pair at all — it clamps `count` and returns exactly that many
  — and both installed selectors return the full count
  (`sts2_rl/selectors.py:83`, `sts2_rl/combat.py:581`).
- **observable** Ashwater **always exhausts the entire hand** and Gambler's Brew
  always cycles it. Both are pooled Uncommons.
- **dormancy** Live for the env; the conformance replay is unaffected, because
  `combat_driver.py:74-111` reads the recorded `SelectHandCards` picks.
- **pin** Unpinned.
- **fix** Give `select_cards` a `min_select`; the mechanism is already
  expressible — `selectors.py:79-82`'s `gambling_chip` branch filters the
  candidates instead of taking `count`.

### 46e–46l. Potion single-unit live findings

Eight mechanisms, one unit each, each with its own record entry. Listed compactly
because none shares a site with anything else.

- **`potion/foul_potion/g2`** — the in-combat arm damages **enemies then player**
  where `CombatState.Creatures` is `_allies.Concat(_enemies)`
  (`CombatState.cs:70`), i.e. the thrower first (`sts2_rl/potions.py:418`).
  Grade B, and worse at the edge: with the player and the last enemy both on ≤12
  HP the game ends the run and the sim calls `_end_combat(player_won=True)`,
  because `use_potion` tests `_all_enemies_dead()` before `player.is_dead`
  (`sts2_rl/combat.py:612-615`). **Pinned** —
  `TestPotionContentPins::test_foul_potion_damages_the_thrower_first`.
- **`potion/foul_potion/g1`** and **`potion/foul_potion/OnUse`** — both
  out-of-combat arms unported: the shop arm (drive the merchant off +
  `GoldVar(100)`, `FoulPotion.cs:79-88`) and the Fake Merchant arm (`:89-108`).
  The port's docstring cites `RunState.merchant_driven_off`, which does not
  exist — `grep -rin merchant_driven_off sts2_rl/` returns only that docstring.
  Partial credit: the Fake Merchant *event* option is ported
  (`sts2_rl/events/fake_merchant.py:75-97`) but it **discards** the potion
  rather than using it, so no `OnUseWrapper` and no `AfterPotionUsed`.
- **`potion/fairy_in_a_bottle/g1`** and
  **`potion/fairy_in_a_bottle/AfterPreventingDeath`** — the automatic trigger
  calls `potion.use` directly (`sts2_rl/potions.py:1245-1250`) instead of
  `OnUseWrapper` (`FairyInABottle.cs:44`), so `Hook.AfterPotionUsed` never fires
  when the fairy pops. Both C# implementers are ported and working at their own
  sites (`relics/reptile_trinket.py:23-29`, `relics/belt_buckle.py:32-33`): the
  game grants 3 temporary Strength when the fairy saves you and the sim grants
  none. **Pinned** —
  `TestPotionContentPins::test_fairy_in_a_bottle_fires_after_potion_used`,
  whose first assertion (the 30%-of-max-HP heal) *passes*, confirming the
  record's arithmetic by execution before the second one fails.
- **`potion/touch_of_insanity/g1`** and **`potion/touch_of_insanity/OnUse`** —
  the candidate filter is an OR over `CostModifiers.Local` and `.All`
  (`TouchOfInsanity.cs:22`, `CardModel.cs:1578-1595`) and the sim tests only
  `c.energy_cost > 0`, which is the local cost
  (`sts2_rl/cards/base.py:222-232`). Executed
  (`py audit/tools/potion_probes.py touch-of-insanity`): with Spiked Gauntlets
  held and a Power card made free this turn, local cost 0 / global cost 1, the
  game offers the card and the sim's candidate list is empty — the potion does
  nothing. **Pinned** —
  `TestPotionContentPins::test_touch_of_insanity_offers_a_globally_costed_card`.
- **`potion/entropic_brew/g2`** and **`potion/entropic_brew/OnUse`** — the
  legacy generator is the wrong factory. The source calls
  `CreateRandomPotionOutOfCombat` **on purpose** (`EntropicBrew.cs:23`), so
  Fairy in a Bottle, Fruit Juice and Regen Potion are reachable from the brew;
  `sts2_rl/potions.py:1216`'s legacy arm calls `random_potion`, which filters
  exactly those three and picks uniformly instead of rolling a rarity. The
  parity arm is correct. Live for the RL env, which never builds an `rng_set`.

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

### 76. `creature_card_cmds/N10` + `/step104` — CardSelectCmd's auto-select shortcut  [DORMANT / parity-live] [unpinned]

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

### 77. `creature_card_cmds/step55` — the in-combat transform rolls off-stream  [DORMANT / parity-live] [unpinned]

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
- **radius** Tier 1 #9 (`creature_card_cmds/G3`), `/step56` (`PileIndexSort`),
  `/N9` (no Play pile).

### 78. `creature_card_cmds/G10` — `ModifyShuffleOrder` modelled as an `AfterShuffle` listener  [DORMANT / parity-live] [unpinned]

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

### 79. `monster_state_machine/G6` — one machine roll on the wrong stream  [DORMANT] [pinned]

- **sites** `monster_state_machine/step35`, `/step41` (2 entries).
- **divergence** `MonsterModel.RollMove` uses the dedicated `RunRng.MonsterAi`
  stream (`MonsterModel.cs:415-418`). SP3 already moved both machine roll sites
  onto `monster_ai`; **one** off-stream site survives — `powers.py:2233` passes
  `self.owner._rng`, the shared combat `random.Random`. Clause (b): the sim's
  `roll_move` walks all the way to a `MoveState` and so **consumes a branch draw**
  where `FlutterPower.cs:47` consumes none (`MoveState.GetNextState` is
  deterministic).
- **trigger** `FlutterPower` reaching a monster whose machine has a
  `RandomBranchState`. Its only applier on both sides is Thieving Hopper, whose
  machine is a pure deterministic chain (`thieving_hopper.py:61-65`).
- **pin** `TestMonsterStateMachineOrder::test_flutter_stun_splice_consumes_no_shared_stream_draw`
  (the first pass labelled this LIVE and the pin itself refuted that by XPASSing).
- **fix** Pass `combat_rng.monster_ai` at `powers.py:2233` and give the splice a
  deterministic "ask the last logged state for its follow-up" path that does not
  advance the machine. Failing test asserts zero shared-stream draws.
- **radius** Tier 1 #2 (`turn_structure/G9`), Tier 1 #21 (`/G4`).

## 2B. Missing guard families

### 80. `hook_dispatch/G8` — no `IsEnding` / `IsOverOrEnding` dispatch gate  [DORMANT] [pinned]

**The largest mechanism in the queue: 22 entries across three records.**

- **sites** `hook_dispatch/step19`, `/step20`, `/step21`;
  `creature_card_cmds/step1`, `/step7`, `/step11`, `/step48`, `/step54`,
  `/step63`, `/step71`, `/step72`, `/step74`, `/step83`, `/step90`, `/step103b`,
  `/G14`; `power_cmd/step1`, `/step2`, `/step6`, `/step16`, `/step24`, `/G6`.
- **divergence** `Hook.IterateCombatHookListeners` (`Hook.cs:53-63`) yields
  **nothing** to a dispatch that begins after combat started ending, and 73 of the
  147 dispatchers go through it; separately, every C# command in
  `creature_card_cmds`' scope opens with its own liveness check
  (`CreatureCmd.Add` 55-67, `Escape` 585-588, `GainBlock` 637-640, `Heal` 693-696,
  `CardCmd.Discard` 174-177, `Downgrade` 214, `Transform` 371-374,
  `CardPileCmd.Add` 308-319, `Draw` 800-803, `Shuffle` 866-869 ...), and
  `PowerCmd.Apply`/`ModifyAmount` check `IsEnding` twice (`PowerCmd.cs:69-72`,
  `217-220`) plus `CanReceivePowers` (`73-76`, `133`). The sim has no gate
  anywhere: `combat.py` flips `Phase.COMBAT_OVER` only inside `_end_combat` and no
  dispatcher or command consults it.
- **observable** Executed: with Daughter of the Wind
  (`relics/daughter_of_the_wind.py:23-33`) a lethal Strike still grants its 1 Block
  from `on_card_played` after `_all_enemies_dead()` is true.
- **trigger** Porting a listener on a guarded dispatcher that mutates **run-level**
  state (HP, gold, deck) from `AfterCardPlayed`/`AfterCardDrawn`/
  `AfterCardExhausted`/`AfterShuffle`/`AfterEnergySpent`. The record names the
  conformance exporter as the near-term risk.
- **pin** `TestHookDispatchOrder::test_no_listener_runs_after_the_combat_starts_ending`
  and `TestCreatureCardCmdsOrder::test_select_cards_refuses_once_the_combat_is_over`.
- **fix** One gate in `HookSystem`'s dispatch helper (`if combat is ending and not
  starting: return`) plus a shared `_assert_live()` helper on the command module.
  Both are cheap; the risk is that the existing suite relies on post-combat
  dispatches being harmless. Land it behind the two pins.
- **radius** Tier 1 #7 (`turn_structure/G13`) and `/G10` decide *when* the gate
  closes, so all three should be designed together. `power_cmd/G6` also carries the
  missing `CanReceivePowers` half — that needs `should_allow_hitting` wired into
  the power pipeline, not just a phase check.

### 81. `damage_pipeline/G5` — no dealer-dead / target-dead entry guard  [DORMANT] [unpinned]

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

### 82. `creature_card_cmds/N3` — the `CardPileAddResult` failure surface is unmodelled  [DORMANT] [unpinned]

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

### 83. `creature_card_cmds/N4` — no duplicate-instance guard on any pile insert  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step102c`, `/N4` (2 entries).
- `CardPile.AddInternal` throws if the pile already holds that `CardModel`
  instance and `RemoveInternal` throws if it does not (`CardPile.cs:86-89,
  117-120`); the sim's piles are plain lists with no invariant — which is what lets
  `/G7`'s double-membership bug exist silently.
- **pin** unpinned. **fix** assert the invariant in the three pile helpers.
  **radius** `/G7` is the verb-level symptom of this container-level hole; fix N4
  first and G7 becomes a loud failure instead of a silent one.

### 84. `creature_card_cmds/N2` — `afflict` skips ShouldAfflict / CanAfflict / AfterApplied  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step64`, `/step65`, `/N2` (3 entries).
- `CardCmd.Afflict` guards on `Hook.ShouldAfflict` and `affliction.CanAfflict(card)`
  and fires an `AfterApplied` lifecycle event (`CardCmd.cs:627-634` ff.); the sim
  has no surface for any of the three and returns `None` where C# throws.
  `ShouldAfflict` has zero overrides game-wide; `CanAfflict` has no sim surface at
  all. Trigger: porting any affliction with a `CanAfflict` restriction.
- **radius** `hook_dispatch/G6` (afflictions are not listeners at all), `/G8`.

### 85. `creature_card_cmds/N5` + `/step31` — `EnergyCmd.gain` lacks the `finalAmount > 0` guard  [DORMANT] [unpinned]

`PlayerCmd.cs:37-41` adds energy only when the modified amount is positive;
`cmds.py:553-554` does `player.energy += amount` unconditionally, so a modifier
returning a negative value would subtract energy. The only ported
`modify_energy_gain` listener returns 0 (`NoEnergyGainPower`,
`powers.py:554-557`), a no-op under both rules. One `if final > 0` guard.

## 2C. Missing hook surfaces

### 86. `creature_card_cmds/G8` — no `AfterCardChangedPiles` at all  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step69`, `/step81`, `/step89`, `/step96`, `/G8`
  (5 entries; `/step59` is also a site).
- **divergence** Every C# pile move funnels through it (`CardPileCmd.cs:635` Add,
  `188` RemoveFromCombat, `683` manual play, `CardCmd.cs:447` transform); the sim
  has one hook per transition (`on_card_drawn`, `on_card_discarded`,
  `on_card_exhausted`, `on_card_entered_combat`) plus a deck-only relic shim
  (`relics/base.py:208-210`), and nothing observes an arbitrary pile-to-pile move.
- **trigger** All four ported C# listeners filter to `pile.Type == Deck`, so the
  shim covers them everywhere except the transform path (Tier 1 #9). The three C#
  listeners that watch **combat** piles — `SovereignBlade`, `Hoarder`, `SoulFysh`
  — are unported; porting any makes this live.
- **pin** unpinned. **fix** add `on_card_changed_piles(card, old_pile, new_pile)`
  and fire it from the three pile helpers. **radius** Tier 1 #9, `/G11`,
  `hook_dispatch/G1`.

### 87. `creature_card_cmds/G12` + `/step34` — no gold-gain hook surface  [DORMANT] [unpinned]

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

### 88. `creature_card_cmds/G11` + `/step49` — `AfterCardDiscarded` fires pre-move and in a batch  [DORMANT] [unpinned]

C# adds each card to the discard pile **first**, then fires the hook, one card at
a time (`CardCmd.cs:186-195`); `discard_hand` (`player.py:192-196`) fires
`on_card_discarded` for every flushed card while they are all still in `hand`,
then moves them as a batch. Executed: flushing `[Strike, Defend]` records
`[('strike', in_hand=True, in_discard=False), ('defend', in_hand=True,
in_discard=False)]` at hook time; C# would give `(False, True)` for each and would
have moved Strike before Defend's hook ran. Trigger: any `on_card_discarded`
listener that reads pile membership. Fix: interleave move-then-fire.

### 89. `creature_card_cmds/G9` + `/step84` — `ShouldDraw` re-evaluated per card, no `AfterPreventingDraw`  [DORMANT] [unpinned]

`CardPileCmd.Draw` evaluates `Hook.ShouldDraw` exactly once before the loop and
fires `Hook.AfterPreventingDraw` on refusal (`CardPileCmd.cs:804-808`);
`player.py:280-281` calls `should_draw` inside the per-card loop and has no
`after_preventing_draw`. Trigger: a `should_draw` listener that flips mid-draw —
Fiddle (`relics/fiddle.py:26-29`) is the only ported one and is stateless. Fix:
hoist the check; add the hook.

### 90. `creature_card_cmds/step12` — no `BeforeBlockGained`  [DORMANT] [unpinned]

C#'s unconditional pre-modifier event carrying the raw amount
(`CreatureCmd.cs:642`, `Hook.cs:131-137`) has no sim surface. Zero overrides
game-wide today; live the moment any model implements it. One dispatcher to add.

### 91. `creature_card_cmds/step46` — no `BeforeCardAutoPlayed`  [DORMANT] [unpinned]

`combat.py:552` fires `on_energy_spent(card, 0)` and then the ordinary
`before_card_played`; the auto-play-only event is absent and none of its C#
implementations is ported. **radius** `hook_dispatch/G4` (the per-play bracket).

### 92. `creature_card_cmds/step61` — no `AfterCardGeneratedForCombat` on transform  [DORMANT] [unpinned]

`cmds.py:445-450` fires only `on_card_entered_combat`; C# fires **both** events for
a combat-pile transform (`CardCmd.cs:445` and `504`). None of the seven C#
implementations is ported.

### 93. `creature_card_cmds/step68` — no `BeforeCardRemoved`, no removed-from-state marking  [DORMANT] [unpinned]

`RunState.remove_cards` (`run.py:356-358`) is a bare `self.deck.remove(card)` loop.
No ported listener, and the sim's cards carry no `HasBeenRemovedFromState` flag for
anything to read — which is also why `hook_dispatch/G7` cannot be implemented as
C# does it.

### 94. `turn_structure/step20` — no `AfterModifyingHandDraw`  [DORMANT] [unpinned]

`modify_hand_draw` is ported with the same base of 5 (`player.py:171`), but the
companion event is absent. C# has four implementers; the two ported ones are
presentation-only (`Pocketwatch.cs:67-71` is a bare `Flash()`). This is one of
`damage_pipeline/G2`'s 13 variants.

### 95. `turn_structure/step55` — no `BeforeFlush`  [DORMANT] [unpinned]

No slot between `_process_turn_end_cards` (`combat.py:658`) and the flush
(`661-662`). C#'s three implementers (`SlumberingEssence.cs`,
`WellLaidPlansPower.cs`, a mock) are unported. **radius** Tier 1 #18.

### 96. `turn_structure/G11` + `/step37` — no enemy-side `BeforeTurnEnd` slot  [DORMANT] [unpinned]

C# fires the same three-pass `BeforeTurnEnd` dispatcher for the enemy side
(`CombatManager.cs:1251`); the sim has only per-enemy `on_enemy_turn_end`
(`combat.py:341`) and side-scoped `on_enemy_side_end` (`345`), with no slot
between them. Eight C# powers implement a `BeforeSideTurnEnd*` phase
(`AsleepPower`, `PlatingPower`, `ChainsOfBindingPower`, `DoomPower`,
`HailstormPower`, `SandpitPower`, `TheBombPower` + a mock); none is ported onto
that slot. **radius** Tier 1 #13, `hook_dispatch/G3`.

### 97. `turn_structure/G16` — `on_hand_emptied` fires from the one site C# excludes  [DORMANT] [unpinned]

- **sites** `turn_structure/step63`, `/step73`, `/G16` (3 entries).
- C#'s `CheckForEmptyHand` (`CombatManager.cs:887-893`) is called **only** after a
  card play and after a potion use, gated on `IsExecutingCardOrPotionEffect` and
  the player's phase; `UnceasingTop.cs:25-35` carries a source remark explaining
  why the draw and the flush must not trigger it. The sim's `on_hand_emptied` has
  exactly one call site — `player.py:197`, at the bottom of `discard_hand`, i.e.
  the flush — and none after a play or potion.
- **trigger** Porting Unceasing Top, or any listener that draws on an empty hand.
- **radius** Tier 1 #18 and #19 (Joss Paper leans on the flush firing it).

### 98. `turn_structure/G7` + `/step38` — `EndOfTurnCleanup` has no counterpart at either site  [DORMANT] [unpinned]

C# runs it twice per round — end of the enemy turn for every player
(`CombatManager.cs:1252-1255`) and inside each `FlushPlayerHand` (`1346`) —
clearing `ExhaustOnNextPlay`, `HasSingleTurnRetain`, `HasSingleTurnSly` and the
turn-scoped cost modifiers in **every** pile (`PlayerCombatState.cs:268-274`,
`CardModel.cs:1610-1623`). The sim's only per-turn card reset
(`cards/base.py:265-269`) clears three cost fields and runs at the **start** of the
next player turn (`player.py:153-155`). Two consequences: the reset window is a
full enemy turn wider than the game's, and single-turn Retain / Sly /
ExhaustOnNextPlay do not exist at all. **radius** Tier 1 #18 (the flush tail that
should run it), `creature_card_cmds/step51` (Sly is unported).

### 99. `turn_structure/step8` — no per-power `AmountOnTurnStart` snapshot  [DORMANT] [unpinned]

`grep -rn amount_on_turn_start sts2_rl/` returns 0 hits. C# snapshots every power's
amount before anything else in the turn (`CombatManager.cs:449-455`,
`Creature.cs:673-679`) and three powers read it, two ported:
`DrawCardsNextTurnPower` (`AmountOnTurnStart == 0` suppresses both the extra draw
and the removal, `DrawCardsNextTurnPower.cs:28,37`) and `HelloWorldPower`. The
sim's `DrawCardsNextTurnPower` (`powers.py:2737-2754`) has no such guard, so a
stack applied during the turn-start window would draw and expire in the same turn.

### 100. `turn_structure/step17` — the two energy hooks fire in the opposite order  [DORMANT] [unpinned]

The arithmetic matches (`player.py:163-167`) but the sim calls `modify_max_energy`
first and `should_reset_energy` second, where C# evaluates
`ShouldPlayerResetEnergy` first and reads `MaxEnergy` inside the chosen branch
(`CombatManager.cs`). Unobservable while both dispatchers are pure aggregations;
live with the first side-effecting implementation of either.

### 101. `hook_dispatch/step37` — the predicate family short-circuits in the sim  [DORMANT] [unpinned]

C# uses `flag = flag || item.ShouldX(...)` with **no** short-circuit, calling every
listener (`Hook.cs:2472-2480` `ShouldForcePotionReward`, `2485-2493`
`ShouldAllowFreeTravel` — those are the only two); the sim aggregates with a
short-circuiting `any(...)` (`rewards.py:449`). Each hook has exactly one
implementer today (`WhiteBeastStatue.cs`, `WingedBoots.cs`), both side-effect free.
Trigger: a second ported implementer with a side effect.

## 2D. Listener-registry shape

### 102. `hook_dispatch/G7` — no per-item liveness re-check  [DORMANT] [unpinned]

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
- **fix** Needs Tier 1 #5's derived listener list plus a `HasBeenRemovedFromState`
  flag on cards/relics (`creature_card_cmds/step68`).
- **radius** `hook_dispatch/G2`, `/G1`, `/G5`, `/G6`, `/N5` — the registry-shape
  family lands together or not at all.

### 103. `hook_dispatch/G1` — card listener order frozen at combat start  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step9`, `/step44` (2 entries).
- `CombatState.cs:449-467` walks `AllPiles` = Hand, Draw, Discard, Exhaust, Play
  (`PlayerCombatState.cs:70-80`) on **every** dispatch, so a card that moves pile
  moves position in the listener list; `combat.py:124` registers `player.all_cards`
  once, in a fixed order (`player.py:100-103`), and never reorders. Dormancy
  executed: card classes implement only six hooks (`dormancy_probes.py card-hooks`,
  203 classes x 66 hook names) and none can observe cross-card order.
- **radius** Tier 1 #5 (same list), `/G6`.

### 104. `hook_dispatch/G5` + `/step3` — `MonsterModel` is not a sim listener  [DORMANT] [unpinned]

`CombatState.cs:420` adds `creature.Monster` to the listener list and
`MonsterModel.cs:51` declares `ShouldReceiveCombatHooks => true`. Exactly **12** C#
monster models override an `AbstractModel` hook
(`py audit/tools/dormancy_probes.py cs-monster-hooks`); only `KinPriest` has been
adjudicated (waiver: presentation). **The other 11 are in no seam's scope — see
the holes section.** Trigger: porting any of them onto their real hook.

### 105. `hook_dispatch/G6` — `AfflictionModel` is not a sim listener  [DORMANT] [unpinned]

`CombatState.cs:458-461` adds `cardModel.Affliction` immediately after its card and
`AfflictionModel.cs:146` declares `ShouldReceiveCombatHooks => true`. Executed both
ways: 0 of the 7 sim `Affliction` subclasses define any hook, and exactly one of
the 10 C# affliction files overrides one (`Hexed.cs`, `AfterCardEnteredCombat`) —
and Hexed is a data-only stub (`afflictions.py:72-79`). Trigger: porting Hexed's
hook; it then needs `hook_dispatch/G1`'s per-card ordering to register in the right
position.

### 106. `hook_dispatch/N5` — no run-level listener list  [DORMANT] [unpinned]

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

### 107. `power_cmd/G1` — Artifact's typing is static, not sign-aware  [DORMANT] [pinned]

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

### 108. `power_cmd/G2` + `/step10` — Unsettling Lamp's condition has the same blind spot  [DORMANT] [unpinned]

`relics/unsettling_lamp.py:44-53` bails on `amount <= 0` and then checks the static
`power_type`, where C# uses `power.GetTypeForAmount(amount)`
(`UnsettlingLamp.cs:124`). `Malaise.cs:40` and `Resonance.cs:33` both apply
negative `StrengthPower` with `applier = player, cardSource = this` — exactly the
shape Lamp doubles — and the sim's `amount <= 0` guard rejects it before the
sign-aware check would matter. **This is the seam the 933T Mecha Knight bug lived
on**: the ordering half is fixed, the sign half is not.

### 109. `power_cmd/G3` — the three power-amount phases collapsed into one chain  [DORMANT] [unpinned]

- **sites** `power_cmd/step12`, `/step27`, `/G3` (3 entries).
- C# runs `BeforePowerAmountChanged` -> `ModifyPowerAmountGiven` (guarded on
  `applier != null && ContainsCreature(applier)`) -> `ModifyPowerAmountReceived`,
  three separately-sequenced calls (`PowerCmd.cs:120,125,127`); `hooks.py:170-183`
  is one flat registration-order chain with no phase separation and no applier
  gate, and `ArtifactPower` is not a listener at all (hard-coded at
  `cmds.py:299-306`).
- **trigger** The two general listeners are domain-disjoint today (Unsettling Lamp
  given-side debuff-only, Ruined Helmet received-side buff-only). A third listener,
  or either widening, collides.
- **radius** Tier 1 #6 (`hook_dispatch/G3`, phases), Tier 1 #11
  (`damage_pipeline/G2`, the companion events), `/G1`.

### 110. `power_cmd/G5` + `/step3` — no `PowerInstanceType`  [DORMANT] [unpinned]

`PowerCmd.cs:165-174`'s `FindExistingInstanceForStacking` dispatches on
`power.InstanceType` (`PowerModel.cs:144`, default `None`); the sim's
`if power_cls.id in target.powers` (`cmds.py:308`) always behaves as `None`. **21**
C# powers declare an override (19 `Instanced`, 2 `InstancedPerApplier` —
`OblivionPower.cs:27`, `StranglePower.cs:29`), **11 of them ported**. Trigger: two
appliers of the same `InstancedPerApplier` power in one combat, or any ported
`Instanced` power stacking where it should not.

### 111. `power_cmd/step4` and `power_cmd/step26` — one code path serves Apply and ModifyAmount  [DORMANT] [unpinned]

C# has two independently-coded pipelines whose guards differ (`PowerCmd.cs:79-87`);
the sim collapses them (`cmds.py:270-332`). It reaches the same steady state for
ported content, but the collapse is not verified line-for-line — and Tier 1 #22 is
the one place it has already been proven wrong. **Read this entry before touching
`PowerCmd.apply`.**

### 112. `power_cmd/step6` — no `amount == 0` early return  [DORMANT] [unpinned]

Filed under the `IsEnding` family by its first reference, but it owns the
zero-amount half itself. Executed: `PowerCmd.apply(cs.hooks, cs.enemy,
StrengthPower, 0)` -> `{'strength': Strength(0)}`, same for Vulnerable, where C#
(`PowerCmd.cs:103`) registers nothing; a 0-amount debuff on the **player**
additionally lands with `skip_next_tick = True`. One guard at the top of
`PowerCmd.apply`.

## 2F. Damage pipeline remainder

### 113. `damage_pipeline/G1` — Thorns is on the wrong hook  [DORMANT] [pinned]

C#'s `ThornsPower.BeforeDamageReceived` (`ThornsPower.cs:17-24`) fires
unconditionally for every hit, **including the hit that kills its owner**, and is
gated on `props.IsPoweredAttack() || cardSource is Omnislice`; the sim's
`ThornsPower` (`powers.py:328-353`) hooks `on_damage_received`, which the damage
pipeline skips entirely on a killing blow, and has no powered/Omnislice gate. Two
consequences: no reflect on the killing blow, and an incorrect reflect against
Unpowered dealer-attributed damage. Pin:
`TestDamagePipelineOrder::test_thorns_reflects_even_on_killing_blow`. **radius**
`/G4` (the killing-blow snapshot), `/G3` (the powered gate).

### 114. `damage_pipeline/G4` + `/step17.5` — the killing-blow skip is recomputed after death prevention  [DORMANT] [unpinned]

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

### 115. `damage_pipeline/G6` and `damage_pipeline/step17.4` — the dealer-side event fires after the victim-side one  [DORMANT] [unpinned]

(Two mechanism ids, one finding: the guard and the step that records it each
stand alone because the step names no guard.)

`CreatureCmd.cs:388-395` fires `AfterDamageGiven` (unconditional) **before** the
killing-blow-guarded `AfterDamageReceived`; `DamageCmd.deal` fires
`on_damage_received` then `on_damage_dealt` — the reverse. No sim power implements
`on_damage_dealt` yet. Two lines to swap.

## 2G. Creature and card verbs with no sim counterpart

### 116. `creature_card_cmds/G4` — `heal` refuses to heal a corpse; C#'s revives  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step19`, `/step20`, `/G4` (3 entries).
- `cmds.py:160-161` early-returns 0 on `target.is_dead`; `CreatureCmd.Heal` guards
  only `IsEnding && !IsPlayer` (`CreatureCmd.cs:693-696`) and `HealInternal` fires
  `Revived` and re-activates the player's hooks when HP crosses 0
  (`Creature.cs:477-491`) — healing a corpse is a supported operation. The one
  ported corpse-heal, `ReattachPower.DoReattach`, hand-rolls
  `owner.hp = self.amount` (`powers.py:2360-2365`) and nets the same. Live the
  moment a second corpse-heal is ported, or anyone routes Reattach through the verb.

### 117. `creature_card_cmds/G5` + `/step22` — heal reports the clamped amount, and nothing at full HP  [DORMANT] [unpinned]

`CreatureCmd.cs:751-754` fires `AfterCurrentHpChanged` when the **requested** amount
> 0, carrying that raw amount; `cmds.py:162-166` fires with the **clamped** amount
and only when positive. Executed: healing 20 on a player 3 below max reports delta 3
(C#: 20); healing at full HP reports nothing (C#: reports +amount). The only ported
`on_hp_changed` listener is Red Skull (`relics/red_skull.py:44-46`), which ignores
the delta.

### 118. `creature_card_cmds/G6` — `lose_max_hp` cannot kill  [DORMANT] [unpinned]

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

### 119. `creature_card_cmds/G7` — `exhaust` only knows the hand and the discard pile  [DORMANT] [unpinned]

`cmds.py:379-384` removes the card from `hand` or `discard_pile` and appends it to
`exhaust_pile`; a card in the draw pile, the exhaust pile, or mid-play stays put
**and** lands in the exhaust pile — it exists in two piles at once. Executed: a
Strike alone in the draw pile ends with `card in draw_pile` **and** `card in
exhaust_pile`; a Strike exhausted twice ends with the same instance in the exhaust
pile twice. C# routes through `CardPileCmd.Add(card, Exhaust, Bottom)` whose
`RemoveFromCurrentPile()` is pile-agnostic (`CardPileCmd.cs:496`). **radius** `/N4`
is the missing invariant that hides it.

### 120. `creature_card_cmds/G13` + `/step8` — escape leaves the escaper's powers registered  [DORMANT] [unpinned]

`CreatureCmd.Escape` calls `RemoveAllPowersInternalExcept()` (`CreatureCmd.cs:589`),
stripping every power silently — the deliberate contrast with death, which awaits
each `AfterRemoved` (`533-537`); the sim's escape (`cmds.py:221-234`) sets
`escaped = True`, fires an invented `on_creature_escaped` hook and leaves every
power on the creature **and registered as a live hook listener**. The three ported
escape sites (Thieving Hopper, Gremlin Merc, `BattlewornDummyTimeLimitPower`) leave
only owner-scoped, self-filtering powers.

### 121. `creature_card_cmds/step18` — no `LoseBlock` verb  [DORMANT] [unpinned]

Four sites assign `block = 0` directly (`combat.py:297`, `player.py:158`,
`powers.py:1208`, `powers.py:2300`). `BurrowedPower`'s C# original calls
`CreatureCmd.LoseBlock(owner, all)` from `AfterRemoved`, so where C# re-fires
`Hook.AfterBlockBroken` on residual block the sim fires nothing. Hand Drill
(`relics/hand_drill.py:21`) is a live `on_block_broken` listener that would see the
difference.

### 122. `creature_card_cmds/step23` — no `SetCurrentHp` verb  [DORMANT] [unpinned]

Sites that need one assign HP directly (`powers.py:2360-2365`, `cmds.py:112`); none
runs the death pipeline the way `CreatureCmd.cs:775-778` does, so setting HP to 0
through those paths would leave a 0-HP creature that never fired
`BeforeDeath`/`ShouldDie`/`AfterDeath`. Every ported direct assignment sets a
positive HP (a revive).

### 123. `creature_card_cmds/step26` — no `SetMaxAndCurrentHp` verb  [DORMANT] [unpinned]

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

### 124. `creature_card_cmds/step51` — the Sly keyword is unported  [DORMANT] [unpinned]

No `CardKeyword.Sly` / `IsSlyThisTurn` analogue anywhere in `sts2_rl`, so
`CardCmd.Discard`'s collect-then-auto-play tail (`CardCmd.cs:186-188, 201-204`) and
the `AutoPlayType.SlyDiscard` path have no counterpart. Porting any Sly card also
makes step 50's DiscardAndDraw ordering live at the same moment.

### 125. `creature_card_cmds/step52` — `Downgrade` drops one level, not to base  [DORMANT] [pinned]

`CardModel.DowngradeInternal` (`CardModel.cs:2135-2147`) re-derives the card from
its canonical model — `CurrentUpgradeLevel = 0`, "downgrades a card to its **base**
form" — where `Card.downgrade` (`cards/base.py:150-165`) drops exactly one level and
does not re-apply the enchantment. Ported callers: `DampenPower`
(`powers.py:3149-3183`, from the Magi Knight's DAMPEN_MOVE) and the Reflections
event (`events/reflections.py:36-41`). Pin:
`TestCreatureCardCmdsOrder::test_downgrade_reapplies_the_cards_enchantment`.

### 126. `creature_card_cmds/step56` — no `PileIndexSort` on transform  [DORMANT] [unpinned]

`CardCmd.cs:353-360, 405` sorts recorded tuples by (pile type, original index) so a
multi-card transform re-inserts deterministically; neither sim transform path sorts,
because both are single-card verbs. Trigger: porting any multi-card transform.

### 127. `creature_card_cmds/step99` — no `AutoPlayFromDrawPile` verb  [DORMANT] [unpinned]

C# moves **every** selected card to the Play pile first and only then plays them,
which is what makes it immune to the second card's reshuffle disturbing the first
card's selection; the sim's Havoc-shaped effects pull and play one at a time.
Trigger: any ported card that plays more than one card from the draw pile.
**radius** `/N9`, `/N10`.

### 128. `creature_card_cmds/N9` + `/step82` — the sim has no Play pile  [DORMANT] [unpinned]

C# holds a card being played in `PileType.Play` for the whole of `OnPlay`
(`CardPileCmd.cs:669-670`, `CardCmd.cs:114-117`) and `Shuffle` reads only Draw and
Discard (`CardPileCmd.cs:870-871`) — the entire mechanism behind the exoskeleton
reshuffle parity fact. The sim appends the played card to the **discard** pile and
holds it back from a reshuffle **in parity mode only** (`player.py:203, 232`),
because legacy RL runs are kept byte-for-byte. Residual exposure: an effect that
counts the discard pile during its own `OnPlay` sees the resolving card in the sim
and not in the game.

## 2H. Monster state machine remainder

### 129. `monster_state_machine/G8` — no construction validation  [DORMANT] [pinned]

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

### 130. `monster_state_machine/G7` — `AddBranch` repeat-limit edge cases  [DORMANT] [pinned]

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
- **radius** Tier 1 #1 (`/G1`) is the same `AddBranch` argument surface — read both
  before touching `add_branch`.

### 131. `monster_state_machine/G9` — the spawn roll is not gated on the combat side  [DORMANT] [unpinned]

- **sites** `/step11`, `/step48` (2 entries).
- C# leaves a freshly added enemy on `UNSET_MOVE` with no intent until the next
  player-turn roll — `AfterCreatureAdded` only rolls when `CurrentSide == Player`
  (`CombatManager.cs:863-866`) — and `rollNewMove: false` (`CreatureCmd.cs:72-75`)
  suppresses it for a player-side monster even on the player's turn. The sim rolls
  in the constructor, unconditionally. Dormancy: `combat.py:286-345` runs the whole
  enemy side to completion before returning, so nothing observes the interim state;
  all 11 sim `CreatureCmd.add` sites fire during the enemy side and every ported
  monster is `side='enemy'`.
- **trigger** A sim consumer that reads an enemy's intent mid-enemy-side — a
  per-enemy observation build, or an interruptible enemy phase. **radius**
  Tier 1 #2 owns where the roll is placed.

### 132. `monster_state_machine/G5` — `stun`'s `next_move_key` is dropped for a machine monster  [DORMANT] [pinned]

- **sites** `monster_state_machine/step36` (1 entry).

Two halves: (a) no `CanTransitionAway` guard on the override path, so a move pinned
by `must_perform_once_before_transitioning` can be replaced where the game refuses
(`MonsterModel.cs:420-432`); (b) `cmds.py:216` gates `next_move_key` on
`hasattr(target, '_move_key')` — the hand-rolled monsters' field — so for a
`MachineMonster` the caller's explicit next move **evaporates silently**. Executed
on a `MachineMonster` FossilStalker: `next_move_key='LASH_MOVE' was SILENTLY
DROPPED`. The only ported caller passing one is
`monsters/overgrowth/ceremonial_beast.py:45`, and Ceremonial Beast is hand-rolled.
Pin: `TestMonsterStateMachineOrder::test_stun_next_move_key_reaches_a_machine_monster`.
**radius** Tier 1 #21 — same fix site.

### 133. `monster_state_machine/G3` — `MoveState` has no string follow-up  [DORMANT] [pinned]

`MoveState.GetNextState` is `(FollowUpState?.Id ?? FollowUpStateId) ?? throw`
(`MoveState.cs:23-25, 67-70`); the sim has no string form, so a C# monster that sets
`FollowUpStateId` without `FollowUpState` cannot be ported without making
`build_machine` two-pass. `grep FollowUpStateId` over the game returns exactly two
sites: the declaration and `Creature.cs:539`, the stun path (Tier 1 #21). Pin:
`TestMonsterStateMachineOrder::test_move_state_accepts_a_string_follow_up_id`.

### 134. `monster_state_machine/G2` — no way to express an unreachable registered state  [DORMANT] [unpinned]

`Inklet.cs:69-71` builds and registers `INIT_RAND` with two branches (one of them
`AddBranch(JAB, 2, 1f)` = maxRepeats 2) and never wires it; `PhrogParasite.cs:6-10`
is the same shape. Reproducing only the reachable graph is *correct* today, but the
sim cannot express the dead state, so the moment one becomes reachable the port
silently keeps the old graph. Pinned in the opposite direction by
`test/test_monster_branch_audit.py::TestInkletMoveSequence` and
`::TestPhrogParasiteMoveSequence`, which assert **zero** `monster_ai` draws on
exactly those legs.

## 2I. Turn structure remainder

### 135. `turn_structure/G10` — the combat-end path collapses five C# distinctions  [DORMANT] [unpinned]

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
- **radius** Tier 1 #7 (`/G13`) and `hook_dispatch/G8` — one design.

### 136. `turn_structure/G5` + `/step9` — the enemy side is per-enemy in the sim, per-side in the game  [DORMANT] [unpinned]

C# has **no** per-creature turn-start or turn-end hook: `BeforeTurnStart`
(`CombatManager.cs:449-455`), `AfterTurnStart`/`ClearBlock` (`492-499`) and
`AfterBlockCleared` (`500-507`) each run as a complete pass over every participant,
then one `AfterSideTurnStart` (`522`), the moves (`1072-1090`), one `BeforeTurnEnd`
(`1251`) and one `AfterTurnEnd` (`1256`); `_run_enemy_turns` (`combat.py:286-345`)
does [clear block -> `on_enemy_turn_start` -> move -> `on_enemy_turn_end`] per enemy
and only `on_enemy_side_end` once. Dormant because every ported listener on those
hooks self-filters to its own owner. **radius** Tier 1 #15, `/G11`.

### 137. `turn_structure/G15` — the turn-end wrapper re-consults `should_ethereal_trigger`  [DORMANT] [unpinned]

`CardModel.OnTurnEndInHandWrapper` (`CardModel.cs:1682-1698`) decides the card's
destination on the raw keyword and never re-consults the hook; `combat.py:370` does
(`if card.is_ethereal and self.hooks.should_ethereal_trigger(card)`), so a false
predicate would send an Ethereal turn-end card to the discard pile in the sim and
to the exhaust pile in the game. Zero implementations on either side, so the
predicate is constant-true and the branches coincide. `turn_structure/step54` is
the same finding on its step.

### 138. `turn_structure/step32` + `/step67` — no `SpawnedThisTurn` flag, no `OnSideSwitch`  [DORMANT] [unpinned]

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

### 139. `card/_unplayable_cost` — an unplayable card's canonical energy cost is `-1` in C# and `0` in the sim  [DORMANT] [unpinned]

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

### 140. `card/_printed_vars` — printed card vars with no `_init_vars` entry  [DORMANT for the game, LIVE for the observation encoder] [unpinned]

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

### 141. `power/_stack_type_single` — `PowerStackType.Single` misread as "does not stack"  [DORMANT] [unpinned]

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

### 142. `card/_is_dead_early_return` — a sim `is_dead` early return splits one card's effect in two  [DORMANT] [unpinned]

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

### 143. `creature_card_cmds/step8c` — no `ShouldStopCombatFromEnding`; the win check has no veto point  [DORMANT] [unpinned]

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

### 144. `power/_after_damage_given_substitution` — `AfterDamageGiven` ported onto `on_damage_received`  [DORMANT] [unpinned]

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

## 2K. Monster tier — dormant families  *(merged 2026-07-27)*

Six dormant mechanisms, 12 entries. Three of them are the same underlying hole:
**the sim's intent vocabulary is lossier than C#'s `AbstractIntent[]`**, which
`monster_state_machine` boundary item 2 named as belonging to no seam's scope
and which nothing has audited since. They are dormant because no sim consumer
reads the missing part today — but the RL observation encoder is exactly the
kind of consumer that would, and entry 75 is the same vocabulary hole already
LIVE for two moves that drop a whole intent rather than a field of one.

### 145. `monster/_no_intent_unrepresentable` — a `MoveState` with an empty intent array  [DORMANT] [unpinned]

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

### 146. `monster/_intent_count_lost` — `StatusIntent(N)` loses its N  [DORMANT] [unpinned]

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
  telegraph-only loss, which is why it is dormant where entry 75 (a dropped
  *whole* intent, read by `Intent.has()`) is live.

### 147. `monster/_retained_corpse_in_scan` — a teammate scan that the sim filters and C# does not  [DORMANT] [unpinned]

- **sites** 2 (`monster/guardbot` GuardMove, `monster/queen` BurnBrightForMe).
- **divergence** `Guardbot.cs:51` is
  `CombatState.Enemies.Where(c => c.Monster is Fabricator)` and
  `Queen.cs:187-188` is `GetTeammatesOf(Creature).Where(t => t != Creature)` —
  **membership of the enemy side is the only test in both**. A creature whose
  removal was vetoed (`ShouldCreatureBeRemovedFromCombatAfterDeath`) is still in
  `Enemies` and is therefore still a valid target. The sim's ports filter the
  corpse out.
- **why it is not entry 19** This is a *consequence* of the death-prevention
  mechanism, not that mechanism: fixing the death hooks does not fix these scans,
  and fixing these scans does not restore `AfterDeath`. Recorded separately for
  that reason. (The first `gap_queue.py` run merged them and it was wrong.)
- **dormancy** Executed: none of the three sim `should_die`/retention
  implementers is applied to anything in a Fabricator or Queen encounter, so no
  retained corpse can be present when either scan runs.
- **trigger** Any retained corpse on the Glory enemy side — an Illusion,
  Reattach or Adaptable holder joining either fight.

### 148. `monster/aeonglass/AfterCardGeneratedForCombat` — generated Withers are not fake-upgraded  [DORMANT] [unpinned]

- **sites** 1 (`monster/aeonglass`), and it is the **second** of the eleven
  unclaimed hook overrides that turned out mechanical (entry 67 is the other).
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

### 149. `monster/knowledge_demon/g1` — the curse's power is applied by the wrong creature  [DORMANT] [unpinned]

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

### 150. `monster/magi_knight/g1` — `DampenPower`'s caster set collapsed to a bare re-apply  [DORMANT] [unpinned]

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

287 mechanisms, one gap entry each. They are real, recorded and verified — they
are here rather than written out because a single-unit finding is cheaper to
read in its own record than restated, and because a 287-entry prose list would
bury Tiers 1 and 2.

Each row is the mechanism id, the liveness the record's own text states, and
that record's lead clause, trimmed. **Line numbers are stripped from these
summaries on purpose** — open the record for the citation, so that
`cite-check` stays a check on the authored prose above rather than a
re-validation of 680 record excerpts. The id is the path: `power/aggression/…`
is `audit/records/power/aggression.json`.

`unlabelled` means the record states neither LIVE nor DORMANT anywhere in the
entry. That is not a third state — it is a hole, 224 entries wide across the
whole queue, and the shared contract now asks for the `live` key precisely
because of it.

## 3A. `power` — 162 single-site mechanisms

One power, one finding. The recurring power families are in Tier 1
(`power/_side_turn_slot`, `power/_death_prevention_branch`,
`power/_killing_blow_guard`, `power/_should_allow_hitting`) and Tier 2
(`power/_stack_type_single`, `power_cmd/G5`, `turn_structure/G5`,
`creature_card_cmds/step8c`, `power/_after_damage_given_substitution`);
everything below stands alone.

- `power/adaptable/ShouldCreatureBeRemovedFromCombatAfterDeath` — *unlabelled* — The sim HAS the hook (hooks.py, consumed at cmds.py to set retained_after_death) and this power does not use it, because the sim took the death-prevention route instead (see the AfterDeath entry). Folded into that entry's …
- `power/aggression/BeforeSideTurnStart` — *unlabelled* — The card selection uses the wrong RNG and the wrong shuffle. AggressionPower.cs is source.ToList().UnstableShuffle(Rng.CombatCardSelection).Take(Amount) -- an UnstableShuffle drawn from the dedicated CombatCardSelection stream. …
- `power/artifact/AfterModifyingPowerAmountReceived` — *unlabelled* — The stack-consumption event is hand-inlined. C# consumes the stack via PowerCmd.Decrement(this) from AfterModifyingPowerAmountReceived (ArtifactPower.cs) -- i.e. through the full ModifyAmount pipeline, which is what runs …
- `power/artifact/TryModifyPowerAmountReceived` — dormant — The interception is reimplemented outside the hook system entirely, and the debuff test is the wrong one. C# (ArtifactPower.cs) is a TryModifyPowerAmountReceived listener whose three guards are target != Owner, …
- `power/asleep/g4` — *unlabelled* — AsleepPower.cs participants.Contains(base.Owner) — Folded into the AfterSideTurnEnd slot entry: the sim expresses the same intent with enemy is not self.owner -> return (powers.py) on a per-creature dispatch. Equivalent for a …
- `power/buffer/ModifyHpLostAfterOstyLate` — dormant — The arithmetic is exact -- 0 for the owner, unchanged otherwise (BufferPower.cs vs powers.py) -- and the AFTER-Osty position is right, since cmds.py runs after block absorption (:74-81). What is lost is the LATE half, and …
- `power/burrowed/AfterBlockBroken` — **live** — The trigger condition is right and the trigger POINT is right -- C# fires on the block actually breaking and cmds.py reproduces the exact Block <= 0 && blockedDamage > 0 semantics its own comment quotes (an exact break counts). …
- `power/burrowed/AfterRemoved` — dormant — C#'s AfterRemoved is CreatureCmd.LoseBlock(oldOwner, 999999999m) -- dump ALL the block -- and it runs on EVERY removal path, including the automatic strip when the owner dies (CreatureCmd.cs then each power's AfterRemoved). The …
- `power/calamity/BeforeCardPlayed` — dormant — C# uses a TWO-HOOK LATCH the sim collapses into one. CalamityPower.cs records amountsForPlayedCards[card] = base.Amount at BeforeCardPlayed and :44 removes it at AfterCardPlayed, so (a) the Amount is SNAPSHOTTED at the start of …
- `power/chains_of_binding/AfterCardDrawn` — dormant — Two divergences. (1) A DROPPED GUARD: C# requires base.CombatState.CurrentSide == base.Owner.Side (ChainsOfBindingPower.cs), so only cards drawn during the PLAYER's own turn are Bound; the sim has no side test (powers.py), so a …
- `power/chains_of_binding/BeforeCardPlayed` — dormant — WRONG SIDE OF THE PLAY, the same shape as SlothPower's: C# sets boundCardPlayed in BeforeCardPlayed (ChainsOfBindingPower.cs) and the sim sets it in on_card_played, after resolution -- while the sim's before_card_played slot …
- `power/clarity/AfterSideTurnStart` — *unlabelled* — The SLOT is right and the group's usual slot gap does not apply here: Hook.AfterSideTurnStart (CombatManager.cs) is post-draw, and the sim's on_player_turn_started (player.py) is the post-draw slot -- confirmed by the ordering …
- `power/confused/g1` — **live** — ConfusedPower.cs Rng.CombatEnergyCosts.NextInt(4) — WRONG RNG STREAM. C# draws the cost from base.Owner.Player.RunState.Rng.CombatEnergyCosts; powers.py uses combat._rng.randrange(4), the SHARED unseeded random.Random …
- `power/constrict/AfterDeath` — dormant — The wasRemovalPrevented guard is missing. C# removes this power only when !wasRemovalPrevented && creature == base.Applier; the sim tests only the applier (hooks.py carries no wasRemovalPrevented argument at all), so a death …
- `power/corruption/ModifyCardPlayResultPileTypeAndPosition` — *unlabelled* — The destination-pile DECISION is replaced by an after-the-fact move, and the sim has the right hook available and does not use it. C# (CorruptionPower.cs) returns (PileType.Exhaust, position) from the pile-resolution chain, so a …
- `power/crab_rage/AfterDeath` — *unlabelled* — Constants and props both checked and both right: DynamicVars.Strength is new PowerVar<StrengthPower>(6m) and DynamicVars.Block is new BlockVar(99m, ValueProp.Unpowered) (CrabRagePower.cs), matching powers.py's STRENGTH_GAIN = 6 / …
- `power/crab_rage/g1` — dormant — CrabRagePower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)); the sim omits it, so applier is None through …
- `power/crimson_mantle/g3` — dormant — CrimsonMantlePower.cs fires the damage UNCONDITIONALLY — C# calls CreatureCmd.Damage with the DamageVar's BaseValue every turn, including the first, when the value is 0; powers.py guards on if self.self_damage > 0. A 0-damage …
- `power/cruelty/g2` — dormant — CrueltyPower.cs target == base.Owner -> unmodified — Cruelty's self-exclusion is dropped by its consumer. Recorded in full on power/vulnerable's matching guard -- the sim reads Cruelty's amount with no such test, so a Cruelty …
- `power/cruelty/g4` — *unlabelled* — CrueltyPower.cs amount + base.Amount / 100m — The arithmetic is right and the TYPE is not: powers.py computes mult += cruelty.amount / 100.0 in float where C# uses decimal. 1.5 + n/100 is non-dyadic for most n (10 -> 1.6, 30 -> …
- `power/curious/TryModifyEnergyCostInCombat` — **live** — The arithmetic is exact -- originalCost - Amount floored at 0, with the Power-card and cost > 0 gates (CuriousPower.cs vs powers.py). What is wrong is everything about HOW it is dispatched, and this power is already the executed …
- `power/curious/g2` — dormant — CuriousPower.cs the TryModify predicate protocol — C#'s Try* hooks are a predicate chain: the listener returns bool to say 'I changed it' and writes the new value to an out-param, and Hook.ModifyEnergyCostInCombat (Hook.cs) uses …
- `power/curl_up/AfterCardPlayed` — *unlabelled* — CurlUpPower.cs is where C# gains the block (ValueProp.Unpowered), clears the latch, sets LouseProgenitor.Curled = true and calls PowerCmd.Remove. The sim has none of it: the block and the removal moved into AfterDamageReceived …
- `power/curl_up/AfterDamageReceived` — **live** — LIVE. C# only LATCHES the triggering card here and grants nothing; the sim grants the block and expires the power on the spot. CurlUpPower.cs records cardSource in internal Data and returns; CurlUpPower.cs (AfterCardPlayed) is …
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
- `power/demon_form/AfterSideTurnStart` — **live** — LIVE. The player leg is one slot too early. The sim's on_player_turn_start (player.py) fires BEFORE the hand draw (player.py), where C#'s AfterSideTurnStart is dispatched at CombatManager.cs, AFTER SetupPlayerTurn (:514) has …
- `power/demon_form/g1` — *unlabelled* — DemonFormPower.cs participants.Contains(base.Owner) — Enemy leg: the sim uses the per-creature on_enemy_turn_start (combat.py), which runs immediately before THIS enemy's move, where Hook.AfterSideTurnStart runs once at …
- `power/dexterity/ModifyBlockAdditive` — dormant — The sim keys the ownership test on the BLOCK TARGET where C# keys it on the CARD's owner. DexterityPower.cs: when cardSource != null the test is cardSource.Owner.Creature != base.Owner -> 0m and the target is not consulted at …
- `power/dexterity/g2` — dormant — Sign-aware power typing on a negative Dexterity application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any …
- `power/disintegration/AfterSideTurnEndLate` — dormant — Wrong slot AND lost phase, and it is the only power in this group with both. (a) PHASE: this is AfterSideTurnEndLate, the second complete pass Hook.AfterTurnEnd runs (Hook.cs), so in the game Disintegration's damage lands after …
- `power/draw_cards_next_turn/AfterSideTurnStart` — **live** — Right slot, wrong condition, and the wrongness is reachable. DrawCardsNextTurnPower.cs removes the power only when participants.Contains(base.Owner) AND base.AmountOnTurnStart != 0; powers.py expires it whenever the owner's turn …
- `power/draw_cards_next_turn/ModifyHandDraw` — dormant — The count is right (count + Amount, DrawCardsNextTurnPower.cs vs powers.py -- and correctly NOT the flat +1 that its sibling power/clarity uses; the two classes exist precisely to differ here, ClarityPower.cs). The GUARD is …
- `power/draw_cards_next_turn/g2` — *unlabelled* — Phase collapse in the sim's single post-draw slot — PHASE COLLAPSE. The sim's on_player_turn_started (player.py) is a single slot serving THREE distinct C# phases that the game runs in a fixed order: Hook.AfterPlayerTurnStart …
- `power/entropy/AfterPlayerTurnStart` — *unlabelled* — The slot is post-draw on both sides, which is what matters for a hand-transform effect: C#'s Hook.AfterPlayerTurnStart is CombatManager.cs, the last statement of SetupPlayerTurn and therefore immediately after CardPileCmd.Draw at …
- `power/entropy/g3` — **live** — EntropyPower.cs the transform rolls on Rng.CombatCardSelection — WRONG RNG STREAM. C# threads player.RunState.Rng.CombatCardSelection into CardCmd.TransformToRandom (CardCmd.cs -> Transform), so every replacement is drawn from …
- `power/escape_artist/g3` — *unlabelled* — EscapeArtistPower.cs participants.Contains(base.Owner) — Folded into the AfterSideTurnEnd entry; the sim's enemy is self.owner on a per-creature dispatch is the same intent on the wrong dispatcher.
- `power/feeding_frenzy/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/feeding_frenzy/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/feel_no_pain/AfterCardExhausted` — **live** — LIVE. The block is dealt as POWERED where C# deals it UNPOWERED, so Dexterity and Frail modify Feel No Pain's block in the sim and not in the game. FeelNoPainPower.cs is CreatureCmd.GainBlock(Owner, Amount, ValueProp.Unpowered, …
- `power/flame_barrier/AfterSideTurnEnd` — dormant — The removal condition is inverted from a side comparison into a hard-coded side. FlameBarrierPower.cs removes the power whenever base.Owner.Side != side -- i.e. at the end of the turn belonging to the side the owner is NOT on, …
- `power/flex_potion/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the …
- `power/flex_potion/g5` — dormant — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; …
- `power/free_attack/TryModifyEnergyCostInCombatLate` — **live** — This power is hook_dispatch G3's LIVE WITNESS from the Late side, and the witness is recorded there with an execution: Tangled (TryModifyEnergyCostInCombat, the EARLY pass, ported at powers.py and applied by the ported Act-1 Vine …
- `power/free_attack/g4` — dormant — The TryModify predicate protocol — C#'s Try* hooks return bool and write to an out-param, which Hook.ModifyEnergyCostInCombat (Hook.cs) uses to build its notification list; the sim's modify_card_energy_cost (hooks.py) is a plain …
- `power/galvanic/AfterCardPlayed` — dormant — PROPS. C# deals the Galvanized damage with ValueProp.Unpowered | ValueProp.Move (GalvanicPower.cs); the sim passes DamageProps.NON_CARD_UNPOWERED, which valueprops.py defines as UNPOWERED alone -- the MOVE flag is missing. The …
- `power/galvanic/BeforeCombatStart` — dormant — Right slot -- combat.py fires on_combat_start immediately before start_turn() at :209, which turn_structure identifies as the sim's BeforeCombatStart. The divergence is an ADDED GUARD (recurring shape 8): C# afflicts EVERY Power …
- `power/gigantification/AfterAttack` — dormant — The slot is right (combat.py, immediately after the card's on_play inside the play-count loop). The GAP is the IDENTITY the latch is cleared against: C# compares ATTACK-COMMAND identity (command == internalData.commandToModify, …
- `power/hardened_shell/BeforeSideTurnStart` — dormant — C#'s BeforeSideTurnStart (HardenedShellPower.cs) has NO side filter and NO participants filter, so the cap resets at the start of EVERY side's turn. The sim reproduces that with two listeners: on_player_turn_start unfiltered …
- `power/hardened_shell/ModifyHpLostBeforeOstyLate` — dormant — The FORMULA is exact -- target != Owner -> amount, amount == 0 -> amount, else Math.Min(amount, Amount - damageReceivedThisTurn) (HardenedShellPower.cs) vs powers.py -- and the BeforeOsty/AfterOsty phase collapse is already …
- `power/hatch/g1` — *unlabelled* — HatchPower.cs participants.Contains(base.Owner) — Folded into the AfterSideTurnEnd entry. Carried separately because with up to five simultaneous owners this is the one guard in this batch whose per-side vs per-creature reading …
- `power/heist/BeforeDeath` — dormant — HOOK-PHASE MISMATCH -- a BEFORE hook ported onto an AFTER hook, the recurring shape section 0 item 5 of the stream report names for thorns/curl_up/skittish/suck, now in a death-time form. C# calls Hook.BeforeDeath UNCONDITIONALLY …
- `power/hello_world/g1` — dormant — HelloWorldPower.cs base.AmountOnTurnStart >= 1 (used as BOTH the guard and the card count) — The guard is ported as self.amount < 1 (powers.py) and the count as self.amount (:2825), where C# uses base.AmountOnTurnStart for both …
- `power/hello_world/g3` — **live** — HelloWorldPower.cs the draw runs on Rng.CombatCardGeneration via TakeRandom — WRONG RNG STREAM AND WRONG ALGORITHM, and the correct sim helper exists and is not used. C# is CardFactory.GetDistinctForCombat(..., …
- `power/hellraiser/AfterSideTurnEnd` — *unlabelled* — HellraiserPower.cs resets the per-turn infinite-auto-play counter. The sim tracks no counter (see the AfterCardDrawnEarly entry), so there is nothing to reset. Dormant for the same reason and with the same trigger; carried …
- `power/high_voltage/g1` — dormant — HighVoltagePower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner as the applier (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)); the sim calls PowerCmd.apply(self.hooks, …
- `power/high_voltage/g2` — dormant — HighVoltagePower.cs participants.Contains(base.Owner) — The sim substitutes if not self.owner.is_dead (powers.py) -- recurring gap shape 8, a guard the sim changes rather than drops. The two are not the same predicate: a corpse …
- `power/illusion/g1` — *unlabelled* — IllusionPower.cs FollowUpStateId — A public settable property with no sim analogue: it lets an applier choose which state the revived creature resumes on, defaulting to the last LOGGED state. Folded into the AfterDeath entry; …
- `power/improvement/AfterCombatEnd` — dormant — THE EFFECT IS ENTIRELY UNIMPLEMENTED. ImprovementPower.cs upgrades base.Amount random upgradable DECK cards after the combat ends: it takes PileType.Deck's cards filtered on IsUpgradable, then loops Amount times picking with …
- `power/improvement/g1` — **live** — ImprovementPower.cs Rng.CombatCardSelection — Recorded so it is not lost when the effect is implemented: the picks must come off combat.combat_rng.card_selection (combat_rng.py), not combat._rng. WRONG RNG STREAM. combat._rng is …
- `power/improvement/g2` — *unlabelled* — ImprovementPower.cs PileType.Deck filtered on IsUpgradable, and :27's list.Remove making the picks DISTINCT — Also recorded for the implementation: the candidates are the RUN deck (not the combat piles), the filter is …
- `power/inferno/g4` — dormant — InfernoPower.cs CombatState.HittableEnemies — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). So the sim …
- `power/intangible/g1` — dormant — IntangiblePower.cs !CombatManager.Instance.IsInProgress -> unmodified — The sim has no combat-phase guard on any modifier hook. This is the power-level face of audit/records/seam/power_cmd.json's structural gap G6 (no …
- `power/juggernaut/AfterBlockGained` — *unlabelled* — The hook, the guards, the props and the dealer are all right -- amount <= 0 and creature == base.Owner (JuggernautPower.cs vs powers.py), and CreatureCmd.Damage(target, base.Amount, ValueProp.Unpowered, base.Owner) (:26) vs …
- `power/juggernaut/g1` — **live** — JuggernautPower.cs Rng.CombatTargets.NextItem(hittableEnemies) — WRONG RNG STREAM. combat._rng is the SHARED unseeded random.Random (combat.py), NOT the per-purpose accessor object -- that is combat.combat_rng, built one line …
- `power/juggernaut/g2` — dormant — JuggernautPower.cs CombatState.HittableEnemies and the empty check — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting …
- `power/juggling/AfterCardPlayed` — dormant — The copy is rebuilt from the class rather than cloned. JugglingPower.cs is cardPlay.Card.CreateClone(), which reproduces the card's full live state; powers.py constructs type(card)() and replays card.upgrade_level upgrades onto …
- `power/mangle/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/mangle/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/mayhem/AfterAutoPrePlayPhaseEntered` — **live** — WRONG PHASE, and this is the finding that makes turn_structure's G8 -- the AutoPrePlay and AutoPostPlay phases do not exist in the sim and their two hooks are hand-rolled onto neighbouring slots. Not re-verdicted here (binding …
- `power/mayhem/g2` — **live** — MayhemPower.cs CardPileCmd.AutoPlayFromDrawPile is TWO-PHASE — CardPileCmd.cs first moves ALL count cards out of the draw pile into PileType.Play (the loop at :939-955, one ShuffleIfNecessary per pick), and only THEN plays them …
- `power/minion/ShouldOwnerDeathTriggerFatal` — **live** — LIVE. C# reads this at three card sites -- Feed.cs, HandOfGreed.cs, TheHunt.cs, each cardPlay.Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal()) computed BEFORE the attack -- and MinionPower returns false, so killing a …
- `power/nemesis/g1` — dormant — NemesisPower.cs participants.Contains(base.Owner) — Replaced by if self.owner.is_dead: return (powers.py) -- the same substitution as HighVoltage's and Territorial's, and one degree worse here, because the sim's early return also …
- `power/nostalgia/ModifyCardPlayResultPileTypeAndPosition` — *unlabelled* — ADDED BY HAND -- the harness did not enumerate it. NostalgiaPower.cs is public override (PileType, CardPilePosition) ModifyCardPlayResultPileTypeAndPosition(...), and harness.list_overrides' _OVERRIDE_RE return-type class does …
- `power/nostalgia/g8` — *unlabelled* — Contention with power/corruption and power/rebound on the same chain — Nostalgia is the one power in this group that uses the RIGHT hook, and that is precisely why it wins the contention the other two lose: …
- `power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath` — *unlabelled* — => creature != base.Owner, i.e. the Test Subject's corpse stays in combat. The sim has the hook (hooks.py, consumed at cmds.py) and this power does not use it -- AdaptablePower on the same creature prevents the death instead …
- `power/panache/AfterCardPlayed` — dormant — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). The sim therefore aims at creatures the game considers …
- `power/plating/BeforeSideTurnEndEarly` — **live** — PHASE, and LIVE with an executed witness. C# is BeforeSideTurnEndEarly -- the EARLY pass of Hook.BeforeTurnEnd (CombatManager.cs) -- and PlatingPower.cs says why in as many words: 'We do this in early so that it triggers before …
- `power/plow/AfterDamageReceived` — dormant — Right hook and right slot; the threshold matches exactly (target != base.Owner || result.UnblockedDamage <= 0 || target.CurrentHp > base.Amount -> return, PlowPower.cs, vs powers.py). Three divergences. (1) The sim ADDS …
- `power/poison/AfterSideTurnStart` — dormant — Three divergences, all DORMANT for one shared reason: nothing in the sim applies Poison at all. An executed grep for PoisonPower outside powers.py and the package re-exports returns no applier -- no card, relic, event, monster or …
- `power/prep_time/AfterSideTurnStart` — *unlabelled* — The slot is right -- Hook.AfterSideTurnStart (CombatManager.cs) and the sim's on_player_turn_started (player.py) are both post-draw, which matters because Hellraiser-style auto-plays that fire DURING the draw (CardPileCmd.Draw at …
- `power/prep_time/g3` — **live** — Registration-order contention with Mayhem in the collapsed slot — LIVE, and it widens turn_structure's G8. MayhemPower is C#'s third ported AfterAutoPrePlayPhaseEntered implementer (MayhemPower.cs, applied by the ported Colorless …
- `power/rampart/g1` — **live** — RampartPower.cs CombatManager.Instance.PlayersTakingExtraTurn.Count > 0 -> return — LIVE, and absent from the sim entirely. C# refuses to grant the block on a player's EXTRA turn: _playersTakingExtraTurn is filled at …
- `power/rampart/g3` — dormant — RampartPower.cs base.CombatState.Enemies.Where(c => c.Monster is TurretOperator) — powers.py adds and not enemy.is_gone (recurring gap shape 8, a guard the sim ADDS). C#'s CombatState.Enemies is the raw participant list and a …
- `power/ravenous/AfterDeath` — *unlabelled* — The guards are exact -- target != base.Owner && target.Side == base.Owner.Side && !base.Owner.IsDead (RavenousPower.cs) maps line-for-line to powers.py -- and the effect order matches (stun the owner, then grant Strength). Two …
- `power/ravenous/g1` — dormant — RavenousPower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)); the sim omits it, so applier is None through …
- `power/reattach/ShouldOwnerDeathTriggerFatal` — **live** — Same missing hook as MinionPower's, and here the override is CONDITIONAL: ShouldOwnerDeathTriggerFatal() => AreAllOtherSegmentsDead() (ReattachPower.cs), so killing a segment while others stand must NOT trigger a Fatal payoff and …
- `power/rebound/AfterModifyingCardPlayResultPileOrPosition` — *unlabelled* — C# consumes the stack from this dedicated after-hook (ReboundPower.cs -> PowerCmd.Decrement), which Hook.ModifyCardPlayResultPileTypeAndPosition fires over exactly the listeners that changed the value (Hook.cs, one of …
- `power/rebound/ModifyCardPlayResultPileTypeAndPosition` — *unlabelled* — The destination-pile DECISION is replaced by an after-the-fact move. The sim has the matching hook -- hooks.modify_card_play_result_pile (hooks.py), dispatched at combat.py -- and this power does not use it, reaching into the …
- `power/regen/AfterSideTurnEnd` — dormant — Both legs are in the wrong slot and the IsDead guard is missing. RegenPower.cs is if (participants.Contains(Owner) && !Owner.IsDead) { Heal(Amount); Decrement; } on AfterSideTurnEnd. (a) The ENEMY leg uses the per-creature …
- `power/regen/g1` — *unlabelled* — RegenPower.cs participants.Contains(base.Owner) — Same mechanism as turn_structure gap G5 (the enemy side is per-enemy in the sim, per-side in the game): the sim's on_enemy_turn_end (combat.py) runs immediately after THIS enemy's …
- `power/regen/g2` — *unlabelled* — RegenPower.cs !base.Owner.IsDead — Absent from the sim -- see clause (c) of the AfterSideTurnEnd entry. Carried as its own guard because it is a distinct omission from the slot problem and would survive a slot fix.
- `power/reptile_trinket/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is …
- `power/reptile_trinket/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 …
- `power/retain_hand/AfterSideTurnEnd` — **live** — A DELIBERATE SLOT SHIFT that is observationally correct in the normal case and LIVE through turn_structure's G3 in the extra-turn case. C# decrements at the PLAYER side's Hook.AfterTurnEnd (CombatManager.cs), i.e. after …
- `power/retain_hand/ShouldFlush` — **live** — The predicate itself is faithful -- false for the owner, true otherwise (RetainHandPower.cs), and the sim's should_flush_hand has no player parameter at all, which is a single-player tautology. What differs is what a FALSE result …
- `power/ringing/AfterCardEnteredCombat` — dormant — The owner filter is dropped, which is harmless in single-player, but the SITE is not: C# afflicts from AfterCardEnteredCombat (RingingPower.cs) and the sim's on_card_entered_combat (hooks.py) is fired only where the sim happens …
- `power/ringing/ShouldPlay` — *unlabelled* — HISTORY vs FLAG. C# answers 'has the owner played a card this turn' by querying CombatManager.History.CardPlaysStarted for entries that HappenedThisTurn; the sim keeps a boolean set from on_card_played. The two differ during a …
- `power/ritual/AfterApplied` — **live** — LIVE. The skip-first-trigger condition is wrong. RitualPower.cs sets WasJustAppliedByEnemy = true whenever base.Owner.IsEnemy -- the applier is not consulted at all. powers.py instead sets it when applier is not None and …
- `power/ritual/g1` — *unlabelled* — RitualPower.cs participants.Contains(base.Owner) — Same mechanism as turn_structure gap G5 (the enemy side is per-enemy in the sim, per-side in the game): the sim's on_enemy_turn_end (combat.py) runs immediately after THIS …
- `power/rolling_boulder/AfterPlayerTurnStart` — *unlabelled* — Post-draw on both sides (CombatManager.cs vs player.py), so the slot itself is right. The gap is the phase collapse: PHASE COLLAPSE. The sim's on_player_turn_started (player.py) is a single slot serving THREE distinct C# phases …
- `power/rolling_boulder/g2` — dormant — RollingBoulderPower.cs CombatState.HittableEnemies (TestMode arm) — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses CombatState.HittableEnemies, which additionally consults …
- `power/rolling_boulder/g6` — **live** — Registration-order contention with Mayhem in the collapsed slot — LIVE, and it widens turn_structure's G8. MayhemPower is C#'s third ported AfterAutoPrePlayPhaseEntered implementer (MayhemPower.cs, applied by the ported Colorless …
- `power/rupture/AfterCardPlayed` — *unlabelled* — The payout half of the deferral described on the BeforeCardPlayed entry: RupturePower.cs removes the card's accumulator and applies the summed Strength once. Absent from the sim. Carried separately because the harness requires a …
- `power/rupture/AfterDamageReceived` — **live** — LIVE, and the bigger half. C# requires base.CombatState.CurrentSide == base.Owner.Side (RupturePower.cs): Rupture only pays out for damage the owner takes DURING ITS OWN TURN, i.e. self-inflicted HP loss. powers.py tests only …
- `power/rupture/BeforeCardPlayed` — **live** — Half of a deferral mechanism the sim does not implement at all. RupturePower.cs registers every card the owner starts playing during its own side turn in an internal playedCards dictionary; AfterDamageReceived then ACCUMULATES …
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
- `power/slow/g1` — *unlabelled* — SlowPower.cs !participants.Contains(base.Owner) -> no reset — The sim expresses it as enemy is self.owner (powers.py) on the per-creature dispatch. Same intent, wrong dispatcher; folded into the AfterSideTurnStart entry.
- `power/slow/g2` — **live** — Once-per-play vs once-per-CardPlay counting — hook_dispatch gap G4 (LIVE and already pinned with an executed witness) applies directly: CardModel.cs constructs a fresh CardPlay per Replay iteration and fires AfterCardPlayed …
- `power/smoggy/AfterCardEnteredCombat` — *unlabelled* — Same pile-limbo shape as power/ringing's matching entry: the sim walks getattr(self.owner, 'all_cards', ()), and PlayerCombatState.all_cards (player.py) is hand + draw + discard + exhaust with NO Play pile, where C#'s …
- `power/speed_potion/g4` — dormant — TemporaryDexterityPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the …
- `power/speed_potion/g5` — dormant — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; …
- `power/speed_potion/g8` — dormant — The Dexterity leg's own observable consequence, as distinct from the family's slot verdict — RE-DERIVED 2026-07-26 (review fix pass). Stated separately so the AfterSideTurnEnd verdict above is not read as more proven than it is, …
- `power/stampede/AfterAutoPostPlayPhaseEntered` — **live** — WRONG PHASE. This is turn_structure's G8 -- the AutoPrePlay and AutoPostPlay phases do not exist in the sim and their two hooks are hand-rolled onto neighbouring slots. Not re-verdicted here (binding rule 3); the verdict is gap …
- `power/stampede/g2` — **live** — StampedePower.cs Rng.Shuffle.NextItem(items) — WRONG RNG STREAM. C# picks the Attack to auto-play off base.Owner.Player.RunState.Rng.Shuffle -- the SHUFFLE stream, which is surprising but is what the source says -- and the sim …
- `power/steam_eruption/ShouldCreatureBeRemovedFromCombatAfterDeath` — *unlabelled* — The sim has the hook and this power does not use it, because it prevents the death instead. Same unused-hook finding as adaptable's and illusion's, and the same inconsistency with reattach, which does use it. Folded into the …
- `power/strength/g3` — dormant — Sign-aware power typing on a negative Strength application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any …
- `power/suck/g2` — *unlabelled* — Counting GROUPS with unblocked damage, not individual results — C#'s num counts outer lists (per-hit result groups) in which ANY result had unblocked damage, so a single AoE hit that connects with three creatures counts 1. The …
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
- `power/thorns/g1` — dormant — ThornsPower.cs props.IsPoweredAttack() || cardSource is Omnislice — Absent entirely -- see consequence 2 of the BeforeDamageReceived entry. Carried as its own guard because it survives a hook-slot fix: moving the sim to a …
- `power/vigor/ModifyDamageAdditive` — dormant — The sim keeps only the FIRST of C#'s four guards. C# (VigorPower.cs) tests, in order: base.Owner != dealer (present, powers.py), !props.IsPoweredAttack() (present structurally -- cmds.py only runs the additive family for powered …
- `power/vital_spark/AfterPowerAmountChanged` — dormant — C# re-syncs every Tainted affliction's Amount to the power's new Amount from AfterPowerAmountChanged with a power != this guard (VitalSparkPower.cs), so it fires on ANY amount change -- a stack, a decrement, or an …
- `power/vital_spark/AfterRemoved` — dormant — C#'s AfterRemoved clears every Tainted affliction on EVERY removal path (VitalSparkPower.cs, guarded by oldOwner.CombatState == null); the sim hangs the same sweep on on_death filtered to the owner (powers.py) and then calls …
- `power/vital_spark/BeforeCombatStart` — *unlabelled* — Identical shape to GalvanicPower's, one card type over (Skills rather than Powers, Tainted rather than Galvanized): the sim adds a card.affliction is None test that VitalSparkPower.cs does not have, where C#'s CardCmd.Afflict …
- `power/vulnerable/ModifyDamageMultiplicative` — dormant — The base multiplier and both ported modifiers are right, but the value is computed in FLOAT where C# uses DECIMAL, which puts this hook inside hook_dispatch gap G9's blast radius. C# reads DamageIncrease = 1.5m from the …
- `power/vulnerable/g3` — dormant — CrueltyPower.cs target == base.Owner -> unmodified — Cruelty's own self-exclusion is dropped. C# skips the Cruelty bonus when the Vulnerable target IS the Cruelty holder; powers.py reads dealer.powers.get('cruelty') with no such …
- `power/vulnerable/g4` — dormant — VulnerablePower.cs DebilitatePower leg — DebilitatePower is not ported (grep -c DebilitatePower sts2_rl/powers.py returns 0), so the third link of C#'s modifier chain has no sim counterpart. Per binding rule 1 an unported C# side …
- `power/weak/ModifyDamageMultiplicative` — dormant — The sim returns the bare literal 0.75 and has no modifier chain at all, where WeakPower.cs threads DamageDecrease = 0.75m through PaperKrane (the TARGET's relic, -0.15m) and then DebilitatePower. Neither is ported -- ls …
- `power/withering_presence/AfterCardPlayed` — dormant — The mechanism is right -- count the target player's card plays down from 6, add a Wither to HAND at 0, reset to 6 -- and the Wither's upgrade matching is preserved (aeonglass.MatchWitherToUpgradeCount(wither) at …

## 3B. `card` — 92 single-site mechanisms

The card tier's families (`card/_unplayable_cost`, `card/_printed_vars`,
`card/_is_dead_early_return`) are in Tier 2. `OnPlay` entries are the card's
own effect diverging; `ctor` and `CanonicalVars` entries that are not in a
family are one-off value-model divergences.

- `card/aggression/OnUpgrade` — **live** — The UPGRADE is faithful; the DOWNGRADE is not. AddKeyword(CardKeyword.Innate) (Aggression.cs) maps to self.innate = True, correct at upgrade level 1. But Card.downgrade (cards/base.py) rebuilds printed state by zeroing …
- `card/anger/OnPlay` — **live** — The damage half is faithful (DamageCmd.Attack(DynamicVars.Damage.BaseValue).FromCard(this).Targeting(cardPlay.Target), Anger.cs, == DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, …
- `card/anointed/OnPlay` — **live** — WRONG RNG STREAM AND WRONG SELECTION ALGORITHM. C#: PileType.Draw.GetPile(Owner).Cards.Where(c => c.Rarity == Rare).TakeRandom(count, Owner.RunState.Rng.CombatCardSelection) (Anointed.cs), and TakeRandom is …
- `card/anointed/g2` — dormant — cards are moved to the hand with CardPileCmd.Add(cards, PileType.Hand) (Anointed.cs) vs direct list mutation — The sim pops each card out of player.draw_pile and appends to player.hand in place (colorless_skills.py) instead of …
- `card/apotheosis/g1` — dormant — the allCard != this self-exclusion, and whether the two AllCards sets are the same set (Apotheosis.cs) — C# PlayerCombatState.AllCards is AllPiles.SelectMany(p => p.Cards) (PlayerCombatState.cs) over Hand, Draw, Discard, Exhaust …
- `card/apparition/OnUpgrade` — **live** — The UPGRADE is faithful; the DOWNGRADE is not. RemoveKeyword(CardKeyword.Ethereal) (Apparition.cs) maps to self.is_ethereal = False, correct at level 1. But Card.downgrade (cards/base.py) rebuilds by re-running _init_vars, and …
- `card/bash/OnPlay` — **live** — The damage, the ordering (damage BEFORE the debuff) and both amounts are faithful. The divergence is the sim's extra liveness guard: if not target.is_gone: PowerCmd.apply(..., VulnerablePower, ...) (bash.py). C# applies the …
- `card/beat_down/OnPlay` — **live** — The candidate FILTER is faithful (c.Type == CardType.Attack && !c.Keywords.Contains(CardKeyword.Unplayable) on the discard pile, BeatDown.cs, == c.card_type == CardType.ATTACK and c.is_playable over ctx.player.discard_pile), and …
- `card/beat_down/g2` — dormant — target selection for AnyEnemy attacks: C# rolls Rng.CombatTargets.NextItem(CombatState.HittableEnemies) in BeatDown itself and passes it to AutoPlay; the sim lets auto_play_card roll (BeatDown.cs) — The stream is right on both …
- `card/bolas/BeforeHandDraw` — **live** — The trigger condition is faithful -- C# checks CombatManager.Instance.History.CardPlaysFinished.Any(e => e.HappenedLastPlayerTurn(Owner) && e.CardPlay.Card == this) (Bolas.cs) and the sim checks e.card is card and e.turn == …
- `card/break/OnPlay` — **live** — The damage, the ordering and every amount are faithful; the divergence is the sim's extra if not target.is_gone: guard before the debuff. C# applies it unconditionally and the only gate is Creature.CanReceivePowers (Creature.cs), …
- `card/breakthrough/OnPlay` — **live** — The AoE half is faithful (DamageCmd.Attack(9).FromCard(this).TargetingAllOpponents(CombatState), Breakthrough.cs, == a per-enemy DamageCmd.deal(..., dealer=ctx.player, card=self)), and so is the order (self-damage FIRST). THE …
- `card/breakthrough/g1` — dormant — the enemy loop skips on enemy.is_dead, not enemy.is_gone (breakthrough.py) — Every other AoE card in the sim filters on not e.is_gone (conflagration, shockwave, omnislice, sword_boomerang, rip_and_tear -- see py …
- `card/brightest_flame/g1` — dormant — CROSS-RECORD DISAGREEMENT (rule 3): CreatureCmd.LoseMaxHp(..., isFromCard: true) is seam gap G6, which labels itself DORMANT; this card makes it LIVE — The seam's VERDICT (gap) is not disputed and is not re-verdicted here -- only …
- `card/catastrophe/g1` — **live** — the sim breaks the pick loop on ctx.combat.is_over or ctx.player.is_dead (colorless_skills.py); Catastrophe.cs has NO loop-level bail-out — C#'s loop runs the full CardsVar iterations unconditionally. The combat-over check lives …
- `card/clash/IsPlayable` — **live** — The PREDICATE is faithful -- CardPile.GetCards(Owner, PileType.Hand).All(c => c.Type == CardType.Attack) (Clash.cs) == all(c.card_type == CardType.ATTACK for c in self.combat.player.hand), and the sim correctly returns True for …
- `card/conflagration/OnPlay` — dormant — Damage per hit, hit count, target set and the OUTER loop order are all faithful: DamageCmd.Attack(2).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState) (Conflagration.cs) runs for (i = 0; i < attackCount; i++) with …
- `card/crimson_mantle/g1` — dormant — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (CrimsonMantle.cs vs crimson_mantle.py) — PowerCmd.Apply<T> returns null in three documented cases (PowerCmd.cs): combat is …
- `card/debt/HasTurnEndInHandEffect` — *unlabelled* — public override bool HasTurnEndInHandEffect => true (Debt.cs) has no counterpart: the sim leaves the class default False (cards/base.py), so the end-of-turn hand pass never even asks Debt for an effect. This is the flag half of …
- `card/debt/OnTurnEndInHand` — **live** — Mathf.Min(DynamicVars.Gold.IntValue, Owner.Gold) then PlayerCmd.LoseGold(num, Owner) (Debt.cs) is simply absent from the sim. The sim's own docstring (debt.py) justifies it with "The sim has no gold" -- THAT CLAIM IS FALSE. …
- `card/discovery/OnPlay` — **live** — The SHAPE is right -- generate 3 distinct cards, choose 1, make it free this turn, add it to hand -- and both sides apply SetToFreeThisTurn BEFORE the pile add, which matters because the sim's set_free_this_turn is cleared by the …
- `card/disintegration/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (Disintegration.cs) has no counterpart: the sim leaves can_be_generated_in_combat at its True default and instead turns OFF a DIFFERENT flag, can_be_generated_by_modifiers, …
- `card/disintegration/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); Disintegration.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the same …
- `card/distraction/OnPlay` — **live** — The shape is right -- generate 1 distinct SKILL from the character pool, make it free this turn, add it to hand, in that order. WRONG RNG STREAM: CardFactory.GetDistinctForCombat(..., 1, Owner.RunState.Rng.CombatCardGeneration) …
- `card/dramatic_entrance/OnPlay` — dormant — The damage, the target set and the single hit are all faithful: DamageCmd.Attack(11).FromCard(this).TargetingAllOpponents(CombatState) (DramaticEntrance.cs) hits every living opponent once, and the sim's framework routing calls …
- `card/drum_of_battle/AfterCardExhausted` — **live** — The self-check and the payout loop are faithful -- if (card == this && CombatState != null) (DrumOfBattle.cs) == if card is not self or self.combat is None: return, and both then gain Energy.BaseValue once per play-count …
- `card/dual_wield/OnPlay` — **live** — The selection filter and the loop are faithful: C#'s filter: c => c.Type == Attack || c.Type == Power with MinSelect 1 (DualWield.cs) == predicate=lambda c: c.card_type in (CardType.ATTACK, CardType.POWER), the null/empty result …
- `card/enlightenment/OnPlay` — **live** — The BRANCH is right and easy to get backwards, so it is worth stating: unupgraded uses SetThisTurnOrUntilPlayed(1, reduceOnly: true) and UPGRADED uses SetThisCombat(1, reduceOnly: true) (Enlightenment.cs), and the sim maps them …
- `card/enlightenment/g1` — dormant — reduceOnly is evaluated LAZILY at cost-calculation time, so C# registers the modifier on EVERY hand card including those already at cost 0 or 1; the sim continues past them (Enlightenment.cs vs event_cards.py) — …
- `card/entrench/g1` — **live** — THIS CARD IS THE ENTIRE PORTED BLAST RADIUS OF SEAM GAP G1 (block modifiers gated on is_powered_attack) — Recorded here with the seam's own verdict (gap), not re-verdicted: creature_card_cmds G1 states that BlockCmd.apply …
- `card/expect_a_fight/g1` — dormant — the sim skips the gain entirely when there are no Attacks in hand (if attacks > 0, expect_a_fight.py); C# calls GainEnergy(0) — PlayerCmd.GainEnergy(0, ...) (ExpectAFight.cs) adds nothing but still runs the engine's gain path; …
- `card/exterminate/OnPlay` — dormant — Damage per hit, hit count, target set and the hits-outer/enemies-inner loop order are all faithful against DamageCmd.Attack(3).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState) (Exterminate.cs) -- AttackCommand …
- `card/feed/OnPlay` — **live** — The damage and the max-HP amount are faithful, and so is the max-HP verb's shape: CreatureCmd.GainMaxHp(Owner.Creature, MaxHp.IntValue) is SetMaxHp(MaxHp + amount) followed by Heal(num) (CreatureCmd.cs) == the sim's …
- `card/fight_me/OnPlay` — **live** — The attack (5 damage, 2 hits), the self-Strength 3 and the enemy-Strength 1 are all faithful and in C#'s order: attack, then SELF, then TARGET (FightMe.cs). The divergence is the sim's extra if not target.is_gone: before the …
- `card/fisticuffs/OnPlay` — **live** — The attack is faithful and the block prop set is right (ValueProp.Move, powered, so not in G1's blast radius). THE BLOCK AMOUNT IS COMPUTED FROM A DIFFERENT QUANTITY. C# gains attackCommand.Results.SelectMany(r => r).Sum(r => …
- `card/frantic_escape/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (FranticEscape.cs) has no counterpart: the sim leaves can_be_generated_in_combat at its True default and instead turns off can_be_generated_by_modifiers, which FranticEscape.cs …
- `card/frantic_escape/OnPlay` — **live** — TWO DIVERGENCES. (1) THE COST BUMP IS PERMANENT IN THE SIM. base.EnergyCost.AddThisCombat(1) (FranticEscape.cs) registers a LocalCostModifier with LocalCostModifierExpiration.EndOfCombat (CardEnergyCost.cs, the AddThisCombat …
- `card/guilty/AfterCombatEnd` — **live** — AfterCombatEnd increments CombatsSeen while the card is in the Deck pile and, at 5, calls CardPileCmd.RemoveFromDeck(this) (Guilty.cs). None of it is ported: the sim's Card base has no after-combat hook at all, so Guilty NEVER …
- `card/hand_of_greed/OnPlay` — **live** — The damage and the gold amount are faithful, and the gold does reach the run (ctx.combat.gold_gained += self._gold, credited by finish_combat) where C# calls PlayerCmd.GainGold immediately -- a timing re-architecture with the …
- `card/havoc/OnPlay` — **live** — C# is a single line: CardPileCmd.AutoPlayFromDrawPile(choiceContext, Owner, 1, CardPilePosition.Top, forceExhaust: true) (Havoc.cs). The sim reimplements the whole verb inline AND, unlike card/cascade -- which reimplements the …
- `card/havoc/g2` — dormant — forceExhaust: true is reproduced by appending to the exhaust pile directly (havoc.py) — C# sets item.ExhaustOnNextPlay = forceExhaust (CardPileCmd.cs) and lets the play pipeline route the card to the exhaust pile, which means the …
- `card/hello_world/OnUpgrade` — **live** — AddKeyword(CardKeyword.Innate) (HelloWorld.cs) maps to self.innate = True, which is correct at upgrade level 1. DOWNGRADE IS STICKY: Card.downgrade (cards/base.py) rebuilds by re-running _init_vars and re-applying upgrades, and …
- `card/hidden_gem/OnPlay` — **live** — The empty-pile early return, the two-tier filter and the prefer-then-fall-back structure are all faithful. C#'s obfuscated type tests decode as expected: (uint)(type - 5) <= 1u excludes the two type values above Power (Curse and …
- `card/howl_from_beyond/OnPlay` — dormant — The damage and the single hit per enemy are faithful against DamageCmd.Attack(16).FromCard(this).TargetingAllOpponents(CombatState) (HowlFromBeyond.cs), and leaving handles_own_routing False is correct for a one-hit AoE -- the …
- `card/inferno/g1` — dormant — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (Inferno.cs vs inferno.py) — Identical to card/crimson_mantle's guard and carrying the same verdict (rule 3): …
- `card/jack_of_all_trades/OnPlay` — **live** — The POOL and the self-exclusion are faithful: ModelDb.CardPool<ColorlessCardPool>()...Where(c => !(c is JackOfAllTrades)) (JackOfAllTrades.cs) == random_pool_cards(..., pool=COLORLESS_POOL, exclude_ids={self.id}), and the …
- `card/jackpot/OnPlay` — **live** — Order, filter and the upgrade-the-generated-cards branch are all faithful. Attack first (Jackpot.cs), then generation. The filter is transcribed exactly, including the subtle part: C# tests energyCost.Canonical == 0 && …
- `card/juggling/OnUpgrade` — **live** — AddKeyword(CardKeyword.Innate) (Juggling.cs) maps to self.innate = True, correct at upgrade level 1. DOWNGRADE IS STICKY: Card.downgrade (cards/base.py) rebuilds by re-running _init_vars and re-applying upgrades, and _init_vars …
- `card/lantern_key/ModifyNextEvent` — dormant — if (2 != Owner.RunState.CurrentActIndex) return currentEvent; return ModelDb.Event<WarHistorianRepy>(); (LanternKey.cs) redirects the next act-3 event to War Historian Repy -- the payoff the Lantern Key quest exists for. The …
- `card/lantern_key/ModifyUnknownMapPointRoomTypes` — **live** — if (2 != Owner.RunState.CurrentActIndex) return roomTypes; return new HashSet<RoomType> { RoomType.Event }; (LanternKey.cs) forces every "?" node in ACT 3 (act index 2, the Glory act) to roll an Event room. The sim's …
- `card/mad_science/GainsBlock` — dormant — public override bool GainsBlock => TinkerTimeType == CardType.Skill (MadScience.cs) is TYPE-DEPENDENT, and the sim never sets gains_block at all -- not in the class body and not in configure (mad_science.py, which sets card_type, …
- `card/mad_science/OnPlay` — **live** — The type dispatch, every rider effect and every amount are faithful, and the rider-per-type partition is correct: C# handles Expertise/Curious/Improvement inside ExecutePower (MadScience.cs) and …
- `card/mangle/OnPlay` — **live** — C# applies the power unconditionally and the only gate is Creature.CanReceivePowers (Creature.cs), whose doc comment states that DEAD creatures can still receive powers -- it refuses only for a REMOVED corpse. The two agree for …
- `card/maul/AfterDowngraded` — **live** — AfterDowngraded() calls base and then DynamicVars.Damage.BaseValue += ExtraDamageFromMaulPlays (Maul.cs) -- i.e. after DowngradeInternal has rebuilt the damage var from canonical (CardModel.cs) it RE-ADDS the total this Maul has …
- `card/metamorphosis/OnPlay` — **live** — The pool filter (character-pool ATTACKS), the count, the free-for-the-combat marking and the destination pile are all faithful in shape: CardFactory.GetForCombat WITH replacement (so duplicates are allowed, matching …
- `card/mind_rot/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (MindRot.cs) has no counterpart; the sim leaves can_be_generated_in_combat True and turns off a different flag that MindRot.cs does not override. Identical to …
- `card/mind_rot/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); MindRot.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the same shape as …
- `card/neows_fury/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (NeowsFury.cs) has no can_be_generated_in_combat = False counterpart; the sim's comment says the ANCIENT rarity already keeps it out of pool_card_ids. That is true today, so …
- `card/neows_fury/OnPlay` — dormant — Attack first, then the hand-size-capped selection: Math.Min(Cards.IntValue, CardPile.MaxCardsInHand - Hand.Cards.Count) (NeowsFury.cs) == min(self._cards, PlayerCombatState.MAX_HAND_SIZE - len(ctx.player.hand)), with both …
- `card/neows_fury/g1` — dormant — the chosen cards are moved with CardPileCmd.Add(list, PileType.Hand) in C# (NeowsFury.cs) and by direct list mutation in the sim (neows_fury.py) — The sim pops the chosen cards out of player.discard_pile and appends them to …
- `card/normality/ShouldPlay` — **live** — The hook choice is RIGHT (unlike card/clash) -- C# really does override ShouldPlay, which both the manual path (CardModel.CanPlay, CardModel.cs) and the auto-play path (CardCmd.AutoPlay, CardCmd.cs) consult -- and so are the …
- `card/omnislice/OnPlay` — **live** — The structure is faithful: powered 8 to the target, then the splash to every OTHER hittable enemy as Unpowered | Move (Omnislice.cs) == props=DamageProps.CARD_UNPOWERED (colorless_attacks.py), and the target set matches -- C#'s …
- `card/omnislice/g1` — dormant — the sim returns early when nothing got through (if dealt <= 0: return, colorless_attacks.py); C# proceeds whenever the DamageResult is non-null (Omnislice.cs) — C# proceeds whenever the DamageResult is non-null (Omnislice.cs) and …
- `card/pacts_end/OnPlay` — dormant — The gate and the damage are faithful: CanDealDamage is CardPile.GetCards(Owner, PileType.Exhaust).Count() >= Cards.IntValue (PactsEnd.cs) == if len(ctx.player.exhaust_pile) < self._required_exhausted: return, and the whole play …
- `card/pillage/g1` — dormant — the sim identifies the drawn card as player.hand[-1] (pillage.py) where C# uses the value the single-card Draw overload returns — C#'s single-card CardPileCmd.Draw overload RETURNS the card it drew (Pillage.cs) and the type test …
- `card/primal_force/OnPlay` — dormant — The candidate set, the per-card upgrade and the index-preserving replacement are all faithful. C# selects Hand.Cards.Where(c => c != null && c.IsTransformable && c.Type == CardType.Attack) (PrimalForce.cs) and the sim's if …
- `card/purity/OnPlay` — dormant — The candidate set and the effect are faithful: CardSelectCmd.FromHand(..., filter: null, source: this) over the whole hand then CardCmd.Exhaust on each (Purity.cs) == CardSelectCmd.from_hand(ctx.hooks, ctx.player, 'exhaust', …
- `card/rampage/AfterDowngraded` — **live** — AfterDowngraded() calls base and then DynamicVars.Damage.BaseValue += ExtraDamageFromPlays (Rampage.cs), re-adding everything this Rampage has accumulated from its own plays after DowngradeInternal rebuilt the damage var from …
- `card/rend/g1` — dormant — the ITemporaryPower exclusion is approximated by a single class (colorless_attacks.py) — C#'s ShouldCountPower is power.TypeForCurrentAmount == PowerType.Debuff && !(power is ITemporaryPower) (Rend.cs). The sim reproduces the …
- `card/rip_and_tear/OnPlay` — **live** — The per-hit re-roll, the duplicate policy and the living-target filter are all faithful. C#'s TargetingRandomOpponents(CombatState) defaults allowDuplicates: true (AttackCommand.cs) and _doesRandomTargetingAllowDuplicates is …
- `card/seeker_strike/OnPlay` — **live** — Attack first, then the offer-three-take-one selection -- and the SHAPE is right, including that only one card moves and the hand-size cap applies. WRONG RNG STREAM AND WRONG ALGORITHM for building the offer. C# does …
- `card/sloth/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false has no counterpart: the sim's shared _ChoosableCurse base leaves can_be_generated_in_combat True and instead turns off can_be_generated_by_modifiers (knowledge_curses.py), …
- `card/sloth/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); Sloth.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status. Same mechanism and …
- `card/splash/OnPlay` — **live** — The three-options / upgrade-the-options / choose-one / free-this-turn / add-to-hand sequence is faithful, including that the upgrade is applied to the OPTIONS before the choice (Splash.cs == colorless_skills.py) so the player …
- `card/spoils_map/BeforeCardRemoved` — **live** — if (card != this) return; if (SpoilsActIndex != Owner.RunState.CurrentActIndex) return; if (!SpoilsCoord.HasValue) return; Owner.RunState.Map.GetPoint(SpoilsCoord.Value)?.RemoveQuest(this); (SpoilsMap.cs) is the CLEANUP path: if …
- `card/squash/OnPlay` — **live** — C# applies the debuff unconditionally and the only gate is Creature.CanReceivePowers (Creature.cs), whose doc comment states that DEAD creatures can still receive powers -- it refuses only for a REMOVED corpse. The two agree for …
- `card/stomp/OnPlay` — dormant — The damage, the single hit per enemy and the target set are faithful against DamageCmd.Attack(12).FromCard(this).TargetingAllOpponents(CombatState) (Stomp.cs), and leaving handles_own_routing False is correct for a one-hit AoE -- …
- `card/taunt/OnPlay` — **live** — C# applies the debuff unconditionally and the only gate is Creature.CanReceivePowers (Creature.cs), whose doc comment states that DEAD creatures can still receive powers -- it refuses only for a REMOVED corpse. The two agree for …
- `card/the_bomb/g1` — dormant — C# dereferences the Apply result WITHOUT a null check; the sim re-fetches by id and skips on None (TheBomb.cs vs colorless_skills.py) — This is the INVERSE of card/crimson_mantle's and card/inferno's ?. finding: those two use the …
- `card/thrash/AfterDowngraded` — **live** — AfterDowngraded() calls base and then DynamicVars.Damage.BaseValue += ExtraDamage (Thrash.cs), where ExtraDamage is the running total of every absorbed Attack's damage (72). C# tracks the accumulation in a private field precisely …
- `card/thrumming_hatchet/BeforeHandDraw` — **live** — This card SHARES card/bolas's return-to-hand helper, and the two C# implementations are byte-identical (ThrummingHatchet.cs vs Bolas.cs), so the finding transfers verbatim and carries the same verdict (rule 3). The trigger …
- `card/thunderclap/OnPlay` — dormant — The TWO-PASS structure is faithful and is the point of the card: C# resolves the whole attack first (DamageCmd.Attack(4).FromCard(this).TargetingAllOpponents(CombatState), Thunderclap.cs) and only then applies Vulnerable to …
- `card/thunderclap/g1` — dormant — the sim continues rather than breaking when an enemy is gone in the damage pass, and re-checks ctx.player.is_dead between the passes (thunderclap.py) — Two behaviours are bundled here and only one is the source's. C#'s …
- `card/toric_toughness/g1` — dormant — C# skips SetBlock when Apply returns NULL via ?.; the sim re-fetches by id and skips on None (ToricToughness.cs vs event_cards.py) — Same mechanism and same verdict as card/crimson_mantle's and card/inferno's guards (rule 3): …
- `card/tremble/OnPlay` — **live** — C# applies the debuff unconditionally and the only gate is Creature.CanReceivePowers (Creature.cs), whose doc comment states that DEAD creatures can still receive powers -- it refuses only for a REMOVED corpse. The two agree for …
- `card/uppercut/OnPlay` — **live** — C# applies the debuff unconditionally and the only gate is Creature.CanReceivePowers (Creature.cs), whose doc comment states that DEAD creatures can still receive powers -- it refuses only for a REMOVED corpse. The two agree for …
- `card/volley/OnPlay` — **live** — The X-value plumbing, the hit count and the duplicates policy are all faithful: WithHitCount(ResolveEnergyXValue()) (Volley.cs) == for _ in range(self.captured_x), where captured_x is set by the play pipeline as …
- `card/waste_away/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (WasteAway.cs) has no counterpart; the sim leaves can_be_generated_in_combat True and turns off a different flag that WasteAway.cs does not override (C# leaves it => true, …
- `card/waste_away/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); WasteAway.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the shape …
- `card/whirlwind/OnPlay` — dormant — The X-value plumbing, the hit count and the hits-outer/enemies-inner loop order are all faithful: WithHitCount(ResolveEnergyXValue()) on TargetingAllOpponents(CombatState) (Whirlwind.cs) == for _ in range(self.captured_x) with a …
- `card/whistle/OnPlay` — **live** — The damage is faithful and the STUN is the right verb. The divergence is the sim's extra if not target.is_gone: before it (whistle.py). C# calls CreatureCmd.Stun(cardPlay.Target) UNCONDITIONALLY (Whistle.cs), and Stun has NO …
- `card/wish/OnUpgrade` — **live** — AddKeyword(CardKeyword.Retain) (Wish.cs) maps to self.retain = True, correct at upgrade level 1. DOWNGRADE IS STICKY: Card.downgrade (cards/base.py) rebuilds by re-running _init_vars and re-applying upgrades, and …

## 3C. `event` — 25 single-site mechanisms

The event tier's `EV-n` mechanisms are all in Tier 1. These are the
per-event findings that no `EV-n` covers.

- `event/EV-11` — dormant — EV-11: BARGAIN_BIN's Common pull (WelcomeToWongos.cs) and GenerateInitialOptions' Rare pull (:80) calls run.pull_relic_from_front (run.py), which scans the merged bag for the first relic of the asked rarity passing the filter …
- `event/battleworn_dummy/Resume` — *unlabelled* — All three reward branches diverge on the RNG stream and two on the selection shape. (1) Setting1: C# draws base.Owner.PlayerRng.Rewards.NextItem(character pool + shared pool) (BattlewornDummy.cs), the sim calls …
- `event/brain_leech/g3` — **live** — Rip (BrainLeech.cs): 5 damage, then RewardCount iterations of a 3-card COLORLESS CardReward offered through RewardsCmd.OfferCustom -- a SKIPPABLE screen — events/brain_leech.py takes the damage and builds the same 3-card …
- `event/crystal_sphere/CalculateVars` — *unlabelled* — Unreachable in the sim only because the whole event is stubbed off -- see the DEFERRED-PORT guard, which carries this unit's verdict.
- `event/crystal_sphere/IsAllowed` — *unlabelled* — See the DEFERRED-PORT guard. The gate is satisfiable with ported content -- gold >= 100 in act 2+ is an ordinary run state -- so this is not an unreachability waiver.
- `event/crystal_sphere/g1` — dormant — DEFERRED PORT: the whole event is a stub. CrystalSphere.cs's payout is the CrystalSphereMinigame (Events/Custom/CrystalSphereEvent/), driven 3 times for UNCOVER_FUTURE (after LoseGold(50 + NextInt(1,50), GoldLossType.Spent)) and …
- `event/dense_vegetation/CalculateVars` — *unlabelled* — Two problems. (1) The roll is on the shared run RNG, not the per-event Rng -- see guard EV-3. (2) The second var is not ported at all: DenseVegetation.cs sets Heal.BaseValue = HealRestSiteOption.GetHealAmount(Owner), which CALLS …
- `event/endless_conveyor/g7` — **live** — FriedEel (EndlessConveyor.cs) draws from the COLORLESS card pool: ForNonCombatWithDefaultOdds(ModelDb.CardPool<ColorlessCardPool>()) -> CreateForReward(1) -> CardPileCmd.Add(card, Deck) — events/endless_conveyor.py calls …
- `event/endless_conveyor/g8` — *unlabelled* — SuspiciousCondiment (EndlessConveyor.cs) draws base.Owner.PlayerRng.Rewards.NextItem(character potion pool + SharedPotionPool) and offers it — events/endless_conveyor.py calls run.random_potion() (run.py), which is rng.choice …
- `event/fake_merchant/g3` — **live** — MerchantRelicEntry.CalcCost (MerchantRelicEntry.cs): the price is (int)Math.Round(Model.MerchantCost * _player.PlayerRng.Shops.NextFloat(0.85f, 1.15f)), one Shops-stream draw per stocked entry; every fake relic declares …
- `event/hungry_for_mushrooms/g3` — dormant — BigMushroom's +20 Max HP pickup effect is implemented on the EVENT, not on the relic. BigMushroom.cs AfterObtained calls CreatureCmd.GainMaxHp(MaxHpVar 20) — relics/big_mushroom.py has NO after_obtained override -- only …
- `event/neow/g8` — dormant — the RUN MODIFIERS branch is not ported. Neow.cs is a whole second mode: when RunState.Modifiers is non-empty the relic offer is REPLACED by one option per modifier that returns a GenerateNeowOption delegate, presented one at a …
- `event/orobas/g6` — **live** — OptionPool3's LOCKED path skips an RNG draw. Orobas.cs adds a null-onChosen OPTION_POOL_3_LOCKED option INTO the list when both gates fail, and Orobas.cs then calls base.Rng.NextItem(OptionPool3) unconditionally -- so the game …
- `event/punch_off/LayoutType` — *unlabelled* — PunchOff.cs EventLayoutType.Combat is NOT presentation-only: EventRoom.EnterInternal branches on it to call GenerateInternalCombatState (EventRoom.cs). See the EV-12 guard -- this hook is the trigger for that mechanism, so it …
- `event/punch_off/g7` — **live** — PunchConstruct.StartingHpReduction is applied to the wrong HP value and in the wrong lifecycle slot. PunchOffEventEncounter.cs rolls StartingHpReduction = base.Rng.NextInt(2, 10) per construct, and PunchConstruct.AfterAddedToRoom …
- `event/ranwid_the_elder/g10` — dormant — BR-relic_trader (blast radius): the grab-bag-runs-dry state. RanwidTheElder.cs and :131 call RelicFactory.PullNextRelicFromFront(base.Owner).ToMutable() with no null check at all, so an empty bag is an NRE in the source — ALREADY …
- `event/reflections/g9` — **live** — BR-step52 (blast radius): audit/records/seam/creature_card_cmds.json step 52 -- CardCmd.Downgrade skips the Enchantment.ModifyCard() re-apply, and step 52's rationale names events/reflections.py (TouchAMirror's downgrade loop) as …
- `event/relic_trader/g5` — dormant — GenerateInitialOptions gates each option on OwnedRelics.Count ALONE (RelicTrader.cs), and Trade then indexes NewRelics at the same position (RelicTrader.cs) — events/relic_trader.py gates on min(len(self._owned), len(self._new)). …
- `event/the_lantern_key/LayoutType` — *unlabelled* — TheLanternKey.cs EventLayoutType.Combat is NOT presentation-only: EventRoom.EnterInternal branches on it to call GenerateInternalCombatState (EventRoom.cs). See the EV-12 guard below -- this hook is the trigger for that …
- `event/the_legends_were_true/g5` — **live** — UNIT GAP: the_legends_were_true draws its potion from the sim's IN-COMBAT potion generator. The source's pool is Character.PotionPool.GetUnlockedPotions(UnlockState).Concat(SharedPotionPool.GetUnlockedPotions(UnlockState)) …
- `event/trial/g8` — **live** — UNIT GAP: NondescriptGuilty's two card-reward screens are not modelled at all. Trial.cs adds Doubt and then builds TWO CardReward(CardCreationOptions.ForNonCombatWithDefaultOdds([Owner.Character.CardPool]), 3, Owner) entries and …
- `event/vakuu/g5` — dormant — UNIT GAP (dormant): Distinguished Cape's -9 Max HP is implemented on the EVENT OPTION instead of on the relic. DistinguishedCape.cs's AfterObtained() runs CreatureCmd.LoseMaxHp(..., DynamicVars.HpLoss = 9, isFromCard: false) and …
- `event/war_historian_repy/g1` — **live** — DEFERRED PORT, leg 1 -- THE ENTRY. IsAllowed => false does not mean the game never runs this event: LanternKey.cs injects it. ModifyUnknownMapPointRoomTypes narrows every '?' node in act index 2 to RoomType.Event, and …
- `event/war_historian_repy/g2` — *unlabelled* — DEFERRED PORT, leg 2 -- THE BODY. Nothing below GenerateInitialOptions is ported: events/war_historian_repy.py returns []. Unported: the two initial options UNLOCK_CAGE / UNLOCK_CHEST (WarHistorianRepy.cs); the second-reward page …
- `event/welcome_to_wongos/g8` — dormant — CheckObtainWongoBadge (WelcomeToWongos.cs) is not ported: the sim never grants WongoCustomerAppreciationBadge, and it tracks points on an ad-hoc attribute instead of run state — The badge is awarded when …

## 3D. `enchantment` — 8 single-site mechanisms

`EG1`, `EG2` and the six `BR-n` cross-references are elsewhere; these eight
are per-enchantment.

- `enchantment/corrupted/OnPlay` — *unlabelled* — The 2 damage is correct; WHEN it is dealt is not. See guard EG1: the sim wires OnPlay to before_card_played, so the self-damage lands BEFORE the card's own attack instead of after it, and only ONCE however many times the card is …
- `enchantment/goopy/AfterCardPlayed` — *unlabelled* — Per-replay firing. See guard EG1: C# runs AfterCardPlayed once per Replay iteration, the sim's on_card_played once per card play. EXECUTED (py audit/tools/enchantment_probes.py replay): Goopy(1) on a Defend played twice by the …
- `enchantment/imbued/AfterAutoPrePlayPhaseEntered` — **live** — The sim adds a guard C# does not have. Imbued.cs is if (player == Card.Owner && player.PlayerCombatState.TurnNumber <= 1) await CardCmd.AutoPlay(ctx, Card, null); -- NO pile check, so the card is auto-played from wherever it is, …
- `enchantment/imbued/ShouldStartAtBottomOfDrawPile` — *unlabelled* — The sim's docstring calls this 'cosmetic and not modeled' (enchantments.py); it is not cosmetic -- it changes the draw pile's order for the whole combat and, for Imbued specifically, is what keeps the card OUT of the opening hand …
- `enchantment/slither/AfterCardDrawn` — **live** — WRONG RNG STREAM. Slither.cs rolls on base.Card.Owner.RunState.Rng.CombatEnergyCosts.NextInt(4); the sim rolls on self.combat._rng.randrange(4) (enchantments.py), the shared combat random.Random, not the per-purpose accessor. The …
- `enchantment/sown/OnPlay` — *unlabelled* — Wrong slot. See guard EG1: C# runs Enchantment.OnPlay AFTER the card's own OnPlay, inside the replay loop (CardModel.cs then 1937-1945); the sim wires it to before_card_played, which fires once, before the card's effect. Same …
- `enchantment/swift/OnPlay` — *unlabelled* — Wrong slot. See guard EG1: C# runs Enchantment.OnPlay inside the replay loop, after the card's own OnPlay and BEFORE Hook.AfterCardPlayed (CardModel.cs); the sim wires it to on_card_played, which fires once, after ALL replays AND …
- `enchantment/vigorous/AfterCardPlayed` — **live** — Per-replay firing. See guard EG1: C# fires AfterCardPlayed once per Replay iteration (CardModel.cs), so the FIRST play gets the bonus and the second does not; the sim's on_card_played runs once, after the whole loop, so every …

---

## 3E. `relic` — 393 single-site mechanisms

The relic tier's sixteen recurring families are in
[Tier 1C](#1c-relic-tier--live-gaps-merged-2026-07-26) (`relic/_is_allowed`,
`relic/_off_stream_draw`, `relic/_stub`, `relic/_reward_late_pass`,
`relic/_auto_keep`, `relic/_combat_reset`, `relic/_stable_shuffle`,
`relic/_undo_clamp`, `relic/_shop_price`, `relic/_victory_flatten`,
`relic/_auto_play_counted`) or resolve to a mechanism a seam record already owns
(`hook_dispatch/G4`, `hook_dispatch/G3`, `damage_pipeline/G3`,
`turn_structure/G13`, `creature_card_cmds/step68`). Everything below stands
alone: one relic, one finding.

This is the largest single-site block in the queue, and the honest reading is
that **the relic tier's gap density is genuinely higher than the other content
tiers'** — 620 entries over 258 units, against the card tier's 149 over 202.
Relics reach into every subsystem, and the sim's out-of-combat surfaces are
where the port is thinnest.

- `relic/alchemical_coffer/AfterObtained` — **live** — SCOPE RULING (2026-07-26 relic fix pass, applied at every potion site in this tier). The shared contract's 'Out of scope everywhere: potions (deferred by Perry)' means POTION IS NOT AN AUDITED KIND -- there is no `potion` roster …
- `relic/amethyst_aubergine/g2` — **live** — Part of the same unported TryModifyRewards body, recorded separately because a fix that adds the gold but forgets this clause would pay 15 extra on the run's last boss where the game pays nothing. Carries TryModifyRewards' LIVE …
- `relic/anchor/g3` — dormant — C# grants Anchor's block at step 3 (Hook.BeforeCombatStart, before StartTurn); the sim grants it at step 14's equivalent (the AfterBlockCleared loop, well inside turn-1 setup). Any effect that runs BETWEEN those two points and …
- `relic/archaic_tooth/AfterObtained` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The transform itself is right -- first deck card whose id is a TranscendenceUpgrades key (ArchaicTooth.cs vs archaic_tooth.py), replaced via run.transform_card(into=) -- but the …
- `relic/archaic_tooth/g1` — dormant — C# grants exactly ONE upgrade level regardless of how many the original had; the sim grants as many as the original had. They agree only while upgrade_level is 0 or 1. REACHABILITY (DORMANT): the sim's Card.max_upgrade_level …
- `relic/archaic_tooth/g2` — dormant — C# clones the enchantment (`(EnchantmentModel)starterCard.Enchantment.MutableClone`) and enchants unconditionally; the sim detaches the original object, then re-attaches it ONLY if `enchantment.can_enchant(transformed)` -- so …
- `relic/astrolabe/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. The selection and the transform are faithful -- 3 cards (CardsVar(3), Astrolabe.cs vs astrolabe.py), chosen from the deck's transformable cards, each replaced and then upgraded, on the Niche …
- `relic/astrolabe/g1` — **live** — MECHANISM: CardCmd.Upgrade(IEnumerable<CardModel>, style) guards each card with `if (!card.IsUpgradable)` and skips it; IsUpgradable is `CurrentUpgradeLevel < MaxUpgradeLevel` (CardModel.cs) with MaxUpgradeLevel virtual and …
- `relic/bag_of_marbles/BeforeSideTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect is right -- 1 Vulnerable (PowerVar<VulnerablePower>(1m), BagOfMarbles.cs) to every enemy on turn 1, applier = the player -- but the hook slot and the enemy set are both …
- `relic/bag_of_marbles/g1` — dormant — MECHANISM: audit/records/seam/turn_structure.json puts Hook.BeforeSideTurnStart at step 9 -- before any block is cleared and before the enemies re-roll their moves -- and Hook.AfterSideTurnStart at step 23, after the hand draw. …
- `relic/bag_of_marbles/g2` — dormant — C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHitting(CombatState, this)` (Creature.cs). The sim's Relic.living_enemies (relics/base.py) filters on `not e.is_gone` …
- `relic/bag_of_preparation/g1` — dormant — C# collects which listeners changed the draw count and fires Hook.AfterModifyingHandDraw over them; the sim's modify_hand_draw returns a bare int with no companion event (hooks.py). This is the missing-AfterModifying-companion …
- `relic/belt_buckle/AfterCombatVictory` — **live** — The SECOND of C#'s two DexterityApplied resets (BeltBuckle.cs). Recorded separately from BeforeCombatStart because C# is deliberately redundant here and the sim has neither: with both missing, the flag latches for the whole run. …
- `relic/belt_buckle/AfterObtained` — dormant — BeltBuckle.cs applies the Dexterity immediately if the relic is picked up DURING a combat with no potions held. The sim's port defines only on_combat_start and on_potion_used, so a Belt Buckle obtained mid-combat grants nothing …
- `relic/belt_buckle/AfterPotionDiscarded` — dormant — The mirror of AfterPotionProcured: BeltBuckle.cs RE-APPLIES the Dexterity when discarding leaves the player potionless mid-combat. The sim implements on_potion_used but not a discard analogue, so the two ways of emptying the belt …
- `relic/belt_buckle/AfterPotionProcured` — **live** — MECHANISM: BeltBuckle.cs REMOVES the 2 Dexterity (RemoveDexterity -> PowerCmd.Apply<DexterityPower>(-2)) as soon as a potion is procured while combat is in progress -- the relic reads 'while you have no potions', and this is the …
- `relic/belt_buckle/BeforeCombatStart` — *unlabelled* — Rollup of guard G2 per binding rule 4. BeltBuckle.cs does THREE things -- `DexterityApplied = false`, RefreshStatus, then ApplyDexterity when potionless -- and the sim's on_combat_start does only the third. The missing reset is …
- `relic/bing_bong/AfterCardChangedPiles` — *unlabelled* — Rollup of guard G1 per binding rule 4. The core is right -- the deck-pile filter, the anti-recursion skip set, and the bottom-of-deck placement all match -- but C#'s `clonedBy == null` clause has no sim counterpart.
- `relic/blood_vial/AfterPlayerTurnStartLate` — *unlabelled* — The effect is right -- HealVar(2m).IntValue healed to the owner on TurnNumber <= 1 (BloodVial.cs) vs CreatureCmd.heal(player, 2) on `self.turn <= 1` -- and the post-draw slot is right (executed: py audit/tools/relic_probes.py …
- `relic/blood_vial/g1` — dormant — MECHANISM: the game runs its turn-start listener list twice, plain then Late, so a Late listener is guaranteed to observe every plain listener's effect. The sim's hooks.on_player_turn_started (hooks.py) is a single flat pass in …
- `relic/bone_tea/AfterSideTurnStart` — *unlabelled* — Rollup of guard G1 per binding rule 4. The slot, the guards and the charge accounting are all right -- post-draw (turn_structure step 23, executed via the turn-order probe), `IsUsedUp` / `participants` / `TurnNumber > 1` all …
- `relic/bone_tea/g1` — **live** — MECHANISM: CardCmd.Upgrade(IEnumerable, style) guards each card with `if (!card.IsUpgradable)` and skips it; IsUpgradable is `CurrentUpgradeLevel < MaxUpgradeLevel` (CardModel.cs). Card.upgrade in the sim (cards/base.py) is a …
- `relic/book_of_five_rings/g1` — **live** — Recorded separately from the hook because a fix that stores 'cards since last heal' and zeroes it would drift from C# the moment anything else touches the counter, and because CardsAdded is a [SavedProperty] -- it survives a …
- `relic/booming_conch/AfterSideTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The energy amount and the Elite/turn-1 conditions are right (executed: Elite turn-1 energy is 4 = base 3 + 1), but the hook slot is wrong and the grant bypasses the energy-gain …
- `relic/booming_conch/g1` — dormant — The relic's own two halves end up on opposite sides of the draw from the source's arrangement: C# adds the cards (ModifyHandDraw, step 20), draws, and only then grants the energy (step 23); the sim grants the energy at step ~19 …
- `relic/booming_conch/g2` — dormant — MECHANISM: PlayerCmd.GainEnergy (PlayerCmd.cs) computes `finalAmount = Hook.ModifyEnergyGain(...)`, awaits Hook.AfterModifyingEnergyGain over the modifiers, and grants only `if (finalAmount > 0)`. The sim HAS that chain …
- `relic/bowler_hat/g1` — **live** — C# multiplies in decimal and the result flows into PlayerCmd's gold path; the sim's gain_gold takes a float (run.py) and RunState.gold is an int. A fix that writes `int(amount * 1.25)` picks a rounding rule this record cannot …
- `relic/brilliant_scarf/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4 -- the sim counts auto-plays that C# explicitly excludes.
- `relic/brilliant_scarf/TryModifyEnergyCostInCombatLate` — *unlabelled* — Rollup of guards G2 and G3 per binding rule 4. The trigger arithmetic matches -- cost 0 when CardsPlayedThisTurn == CardsVar(5) - 1, i.e. the fifth card of the turn -- but the sim drops the Late PHASE (G2) and both of …
- `relic/brilliant_scarf/g2` — dormant — This is audit/records/seam/hook_dispatch.json's gap G3 at the site that record already names: it cites Relics/BrilliantScarf.cs (56-63) and sts2_rl/relics/brilliant_scarf.py as the ported Late-phase witness that makes G2/G3 LIVE …
- `relic/brilliant_scarf/g3` — dormant — C# refuses to modify a cost unless the card's owner is the relic's owner AND the card is currently in the Hand or Play pile; brilliant_scarf.py checks only the counter. The pile clause is the substantive one: it stops the relic …
- `relic/burning_blood/AfterCombatVictory` — *unlabelled* — Rollup of guard G1 per binding rule 4. The heal itself is faithful (6 HP, `!IsDead`, no ascension branch); what diverges is the hook the sim maps it onto -- one collapsed on_combat_end(player_won) instead of C#'s separate …
- `relic/burning_blood/g1` — dormant — MECHANISM: C# reaches AfterCombatEnd and AfterCombatVictory only through EndCombatInternal (CombatManager.cs), which is the VICTORY path; a loss goes LoseCombat -> _pendingLoss -> ProcessPendingLoss (CombatManager.cs, 1046-1052) …
- `relic/burning_sticks/AfterCardExhausted` — *unlabelled* — Rollup of guards G1 and G3 per binding rule 4. The trigger logic matches (first Skill exhausted, clone to hand), but the relic fires in the first combat of a run only (G1) and the copy it makes is a fresh card by id rather than …
- `relic/burning_sticks/AfterCombatEnd` — **live** — The SECOND reset (BurningSticks.cs). Recorded separately from AfterRoomEntered because C# is deliberately redundant here and the sim has neither; with both missing the flag latches for the whole run. Exactly the relic/belt_buckle …
- `relic/burning_sticks/AfterRoomEntered` — **live** — The FIRST of C#'s two resets: BurningSticks.cs clears WasUsedThisCombat on entering any CombatRoom. The sim implements neither this nor the AfterCombatEnd twin. Carries guard G1's LIVE label. Note the sim DOES have a run-level …
- `relic/burning_sticks/g2` — **live** — MECHANISM: BurningSticks.cs calls `card.CreateClone`, which is `CardScope.CloneCard(this)` -> `ClonePreservingMutability` (CardModel.cs; CombatState.cs) -- a full model clone that carries the card's upgrade level, its …
- `relic/byrdpip/AfterObtained` — *unlabelled* — Rollup of guards G1 and G3 per binding rule 4. The deck half of the Byrdonis Egg -> Byrd Swoop transform is faithful; the combat-pile half (G1) and the mid-combat SummonPet call (G3) are dropped.
- `relic/byrdpip/BeforeCombatStart` — *unlabelled* — Byrdpip.cs summons the pet at the start of EVERY combat. The port has no on_combat_start. Carries guard G3's verdict; see G3 for why the omission is observationally inert today.
- `relic/byrdpip/HasUponPickupEffect` — dormant — Byrdpip.cs declares `HasUponPickupEffect => true` and the sim's Relic base has the exact field for it (relics/base.py), which fourteen other ports set. Byrdpip leaves it at the False default. DORMANT (executed -- `py …
- `relic/byrdpip/SpawnsPets` — *unlabelled* — Byrdpip.cs declares `SpawnsPets => true`; relics/base.py has the field and the port leaves it False. Same dormancy and same executed evidence as HasUponPickupEffect -- both feed only is_tradable, which EVENT rarity already …
- `relic/byrdpip/g1` — dormant — Byrdpip.cs collects every ByrdonisEgg from the Deck pile and, `if (CombatManager.Instance.IsInProgress)`, ALSO from `Owner.PlayerCombatState.AllCards` -- i.e. a Byrdonis Egg sitting in the draw/hand/discard/exhaust pile of a …
- `relic/calling_bell/g1` — **live** — MECHANISM: CallingBell.cs has two arms. The `if (TestMode.IsOn)` arm (lines 39-52) builds three RelicRewards with FIXED models -- Anchor, Gremlin Horn, Mummified Hand. The shipping arm (53-63) builds `new …
- `relic/calling_bell/g2` — **live** — MECHANISM: each of the shipping arm's three RelicRewards burns a pull from the player's relic grab bag when it Populates, and (per the project's own note, recorded in memory as 'Relic rarity rolls on Rewards') …
- `relic/captains_wheel/AfterBlockCleared` — *unlabelled* — Rollup of guard G1 per binding rule 4. The arithmetic, the turn index, the target test and the ValueProp all match; what diverges is that the sim only FIRES the hook when a block clear actually happened, so a turn-3 block-clear …
- `relic/captains_wheel/g1` — **live** — This is audit/records/seam/turn_structure.json guard G1 (step 14) at the site that record already names, and one verdict per mechanism (binding rule 3) means it is cited rather than re-derived. C# runs two separate loops over the …
- `relic/centennial_puzzle/AfterCombatEnd` — **live** — CentennialPuzzle.cs exists for one reason: to clear UsedThisCombat. The sim implements neither this nor any other reset. This is the entire content of guard G1 and carries its LIVE label.
- `relic/centennial_puzzle/AfterDamageReceived` — *unlabelled* — Rollup of guard G1 per binding rule 4. Every clause of the trigger is faithful -- owner, unblocked damage > 0, not-yet-used, draw 3 -- but the not-yet-used flag is never cleared, so the whole hook is dead from the second combat …
- `relic/charons_ashes/AfterCardExhausted` — *unlabelled* — Rollup of guard G1 per binding rule 4. Amount, props, dealer, card source and the absence of any once-per-turn limit all match; the target SET is built from a different predicate (G1), and the multi-target damage is issued as N …
- `relic/charons_ashes/g1` — dormant — One verdict per mechanism (binding rule 3): this is the same call-site divergence audit/records/relic/bag_of_marbles.json records as its guard G2, with the same verdict. C# targets `Enemies.Where(e => e.IsHittable)` …
- `relic/choices_paradox/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect is right -- 5 distinct pool cards on turn 1, each given Retain, one chosen into hand -- but they are rolled on the wrong RNG stream with the wrong draw algorithm (G1), and …
- `relic/chosen_cheese/AfterCombatEnd` — *unlabelled* — Rollup of guard G1 per binding rule 4. The +1 Max HP, the heal that accompanies it and the run-level propagation are all faithful and executed; what diverges is the hook -- C#'s AfterCombatEnd is a victory-only event that runs …
- `relic/chosen_cheese/g1` — dormant — MECHANISM: C# reaches AfterCombatEnd and AfterCombatVictory only through EndCombatInternal (CombatManager.cs), which is the VICTORY path; a loss goes LoseCombat -> _pendingLoss -> ProcessPendingLoss (CombatManager.cs, 1046-1052) …
- `relic/claws/AfterObtained` — *unlabelled* — Rollup of guards G1, G2 and G5 per binding rule 4. The per-card transform is faithful in every detail that matters -- one upgrade level carried, enchantment carried when CanEnchant allows, deck-end placement, no RNG consumed …
- `relic/claws/g1` — **live** — MECHANISM: C# builds the selection from `PileType.Deck.GetPile(player).Cards.Where(c => c.Type != CardType.Quest && c.IsTransformable)` (CardSelectCmd.cs) -- Quest cards are excluded by name. claws.py passes …
- `relic/claws/g2` — dormant — MECHANISM: CardCmd.Transform(IEnumerable<CardTransformation>, rng) collects each original's pile and index, calls `item.Original.RemoveFromCurrentPile` for all of them, then sorts the batch with PileIndexSort (CardCmd.cs, 405) …
- `relic/cloak_clasp/BeforeSideTurnEnd` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The arithmetic, the empty-hand guard and the Unpowered prop all match, and the slot is correctly ahead of the hand flush -- but the sim has no sub-phase ordering inside its turn-end …
- `relic/cloak_clasp/g2` — **live** — audit/records/seam/turn_structure.json guard G8 owns this mechanism and verdicts it a gap; cited and matched under binding rule 3. C# enters a dedicated AutoPostPlay phase strictly BEFORE Hook.BeforeTurnEnd (CombatManager.cs), so …
- `relic/crossbow/AfterSideTurnStart` — **live** — Rollup of guards G1 (the auto-play phase boundary, LIVE), G2 (the RNG stream and draw shape) and G3 (FilterForCombat's Event-rarity clause) per binding rule 4. The relic's own arithmetic is right: one distinct Attack from the …
- `relic/crossbow/g1` — **live** — MECHANISM: CombatManager.cs enters the AutoPrePlay phase after Hook.AfterSideTurnStart (CombatManager.cs) has completed for every listener -- the ordering is structural in C#. The sim has no auto-play phase at all, so …
- `relic/crossbow/g2` — **live** — MECHANISM: PROMPT.md bug class 16's second half. TWO divergences in one call, and the stream IS consumed on both sides so the class-16 caveat does not apply. (a) STREAM: the sim's parity helper cards/pool.py …
- `relic/crossbow/g3` — dormant — MECHANISM: C# filters the Attack list through FilterForCombat, whose predicate is 'CanBeGeneratedInCombat && Rarity != Basic && Rarity != Ancient && Rarity != Event'. pool_card_ids implements the first three clauses and omits the …
- `relic/darkstone_periapt/AfterCardChangedPiles` — **live** — Rollup of guards G1 (LIVE) and G2 per binding rule 4. The narrowing is only sound if every C# path that puts a card into PileType.Deck reaches run.add_card. It does not: the out-of-combat TRANSFORM path writes the deck directly.
- `relic/darkstone_periapt/g1` — **live** — MECHANISM: CardCmd's transform loop fires BOTH deck hooks for the replacement when the pile is the deck -- Hook.ModifyCardBeingAddedToDeck at CardCmd.cs and Hook.AfterCardChangedPiles at CardCmd.cs -- so DarkstonePeriapt.cs sees …
- `relic/darkstone_periapt/g2` — dormant — MECHANISM: CardPileCmd.cs and :683 dispatch the hook from the general Add path, and PileType.Deck is a non-combat pile (CardPile.cs IsCombatPile), so a card added to the run's deck while a fight is in progress still triggers it. …
- `relic/daughter_of_the_wind/AfterCardPlayed` — **live** — Rollup of guards G1 (LIVE) and G2 per binding rule 4. The arithmetic and the type filter are right; the DISPATCH is not -- the sim fires on_card_played once per logical play where C# fires it once per CardPlay (G1), and fires it …
- `relic/daughter_of_the_wind/g2` — dormant — MECHANISM: Hook.IterateCombatHookListeners (Hook.cs) yields nothing once IsOverOrEnding is set, and 73 of the game's 147 dispatchers go through it; combat.py flips Phase.COMBAT_OVER only inside _end_combat and no dispatcher …
- `relic/delicate_frond/BeforeCombatStart` — **live** — Rollup of guards G1, G2 and G3 (all LIVE) per binding rule 4. The loop SHAPE is right -- fill every open slot at combat start -- but each of the three things the C# body actually calls is replaced by something weaker: the …
- `relic/delicate_frond/g1` — **live** — MECHANISM: DelicateFrond.cs calls PotionFactory.CreateRandomPotionOutOfCombat, which is CreateRandomPotion(GetPotionOptions(...), 1, rng) at PotionFactory.cs; PotionFactory.cs does `float num = rng.NextFloat` then `num <= 0.1f ? …
- `relic/delicate_frond/g2` — **live** — MECHANISM: PotionCmd.cs returns success=false with PotionProcureFailureReason.NotAllowed when Hook.ShouldProcurePotion is false, and DelicateFrond.cs breaks out of the while loop on that failure -- so a player holding Sozu gets …
- `relic/delicate_frond/g3` — **live** — MECHANISM: the same substitution as G2, on the success branch. BeltBuckle.cs removes its 2 Dexterity the moment a potion is procured mid-combat; with the Frond filling the belt during BeforeCombatStart, C# grants the Dexterity …
- `relic/demon_tongue/g2` — dormant — MECHANISM: DamageResult.cs documents UnblockedDamage as the damage the target received after blocking and OverkillDamage as the excess past 0 HP, and they are separate fields (CreatureCmd.cs has to ADD them back together when it …
- `relic/diamond_diadem/AfterCardPlayed` — *unlabelled* — Rollup of guard G2 per binding rule 4 -- the sim counts one card per logical play where C# counts one per CardPlay, so a replayed card advances the counter by 1 instead of 2 and the relic's 'at most 2 cards' condition is easier …
- `relic/diamond_diadem/AfterCombatEnd` — **live** — Carries guard G1's LIVE label. DiamondDiadem.cs zeroes CardsPlayedThisTurn at combat end; the sim has no such reset, and its only reset (in on_player_turn_end) does not run on the turn a combat ends.
- `relic/dingy_rug/ModifyCardRewardCreationOptions` — **live** — Carries guard G1's LIVE label. Card rewards never contain Colorless cards in the sim; they should, for the whole run once the relic is bought.
- `relic/dingy_rug/g1` — **live** — MECHANISM: DingyRug.cs returns `options.WithCardPools(options.CardPools.Concat(ColorlessCardPool), options.CardPoolFilter)`, so every card REWARD (not shop stock, not combat generation) draws from the character pool PLUS the …
- `relic/dingy_rug/g2` — *unlabelled* — Recorded as a group and carrying G1's verdict, because with no hook there is nothing for any of them to gate. They are listed rather than skipped because three of them are load-bearing for the FIX and easy to lose: IsCardReward …
- `relic/distinguished_cape/AfterObtained` — **live** — Carries guard G1's LIVE label. The card half is faithful -- three Apparitions appended to the deck -- but the relic's -9 Max HP is not implemented at all; the port puts it in the Vakuu event option instead, on a premise about the …
- `relic/dollys_mirror/AfterObtained` — **live** — Carries guard G1's LIVE label. The relic's whole effect (duplicate a chosen deck card) never happens.
- `relic/dollys_mirror/g1` — **live** — MECHANISM: DollysMirror.cs selects one non-Quest card from the deck (CardSelectCmd.FromDeckGeneric with a CardSelectorPrefs count of 1), clones it with RunState.CloneCard and adds the clone to PileType.Deck. dollys_mirror.py …
- `relic/dollys_mirror/g2` — *unlabelled* — Carries G1's verdict -- with no method there is nothing to filter -- and recorded because the filter is NOT the one a reader would guess and the sim has no matching predicate. The C# filter excludes only Quest cards: Curses …
- `relic/dragon_fruit/AfterGoldGained` — **live** — Carries guard G1's LIVE label: +1 Max HP per gold gain never happens.
- `relic/dragon_fruit/g1` — **live** — MECHANISM: DragonFruit.cs grants MaxHpVar(1) on every gold gain by its owner. The port implements nothing. THE PREMISE IS FALSE, and this is the same false premise batch 1 already disproved for relic/amethyst_aubergine ('the sim …
- `relic/dream_catcher/TryModifyRestSiteHealRewards` — **live** — Rollup of guards G1 (LIVE) and G3 per binding rule 4. The relic's own body is faithful -- a 3-card, Monster-odds choice appended to the rest-heal reward screen (guard G2) -- and both gaps are in the surrounding dispatch: the …
- `relic/dusty_tome/AfterObtained` — dormant — Rollup of guards G1 (the unguarded Card.upgrade, dormant), G2 (the lazy re-roll, LIVE on the runner path) and N2 (the added HasUponPickupEffect declaration) per binding rule 4. The core effect is faithful and executed …
- `relic/dusty_tome/g1` — dormant — MECHANISM: CardCmd.Upgrade filters on IsUpgradable == `CurrentUpgradeLevel < MaxUpgradeLevel` (CardModel.cs); cards/base.py's Card.upgrade has no filter, so every caller must supply one and this one does not. …
- `relic/dusty_tome/g6` — dormant — MECHANISM: RelicModel.HasUponPickupEffect defaults to false and DustyTome does not override it -- contrast DistinguishedCape.cs and DollysMirror.cs in this same batch, which do. The sim sets it True. The flag is not decorative …
- `relic/electric_shrymp/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. The relic's OWN halves are all faithful -- the candidate filter (N1, executed: zero disagreements over 203 ported cards), the count of 1, and the enchantment identity -- but the Imbued …
- `relic/electric_shrymp/g1` — **live** — MECHANISM: Imbued.cs's AfterAutoPrePlayPhaseEntered calls CardCmd.AutoPlay(ctx, base.Card, null) unconditionally while TurnNumber <= 1 -- it does not care which pile the card is in, and Imbued.cs's ShouldStartAtBottomOfDrawPile …
- `relic/electric_shrymp/g4` — dormant — PROMPT.md bug class 16's second half at an out-of-combat site: C#'s FromDeckForEnchantment consumes no Rng (CardSelectCmd.cs is a UI/remote-choice branch), so the sim's default random pick both chooses differently AND advances …
- `relic/ember_tea/g1` — dormant — MECHANISM: CombatRoom.cs calls CombatManager.SetUpCombat and then Hook.AfterRoomEntered; Hook.BeforeCombatStart is only reached later, from CombatManager.StartCombatInternal (CombatManager.cs, after IsInProgress is set at :402). …
- `relic/empty_cage/AfterObtained` — *unlabelled* — Rollup of guard N2 per binding rule 4. The count (CardsVar(2), EmptyCage.cs, vs CARDS = 2, empty_cage.py), the candidate filter (N1) and the removal itself all match -- executed: a fresh run's 10-card deck goes to 8. The only …
- `relic/empty_cage/g2` — dormant — Same mechanism and same verdict as relic/electric_shrymp guard N3 in this batch (binding rule 3): C#'s FromDeckGeneric (CardSelectCmd.cs) reaches either the Selector, the local UI screen or a remote choice, none of which consumes …
- `relic/fake_anchor/g3` — dormant — Same mechanism as relic/anchor's guard N3 and carried with the same gap verdict per binding rule 3, with this relic's own dormancy evidence re-executed rather than inherited: the window spans turn_structure steps 4-13, which …
- `relic/fake_blood_vial/AfterPlayerTurnStartLate` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect is right -- heal Heal.IntValue = 1 (HealVar(1m), FakeBloodVial.cs) once, on turn 1 only; executed (py audit/tools/relic_probes_b05.py flower-blood) 40 -> 41 on turn 1 and …
- `relic/fake_blood_vial/g1` — dormant — MECHANISM: Hook.AfterPlayerTurnStart runs three complete passes -- Early, then plain, then Late (Hook.cs) -- so a Late listener is guaranteed to see every plain listener's result. The sim's hooks.py has one walk per hook and no …
- `relic/fake_blood_vial/g2` — dormant — MECHANISM: turn_structure step 22 is `CardPileCmd.Draw` followed immediately by Hook.AfterPlayerTurnStart (CombatManager.cs); step 23 is Hook.AfterSideTurnStart (CombatManager.cs), which on the player side runs only after EVERY …
- `relic/fake_orichalcum/BeforeSideTurnEnd` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect itself is right: FakeOrichalcum.cs grants BlockVar(3m, ValueProp.Unpowered) (line 23) once, clearing the latch first, and fake_orichalcum.py grants 3 at the same …
- `relic/fake_snecko_eye/AfterObtained` — dormant — MECHANISM: FakeSneckoEye.cs applies the Confused power immediately when the relic is picked up if `CombatManager.Instance.IsInProgress`, so a Fake Snecko Eye obtained mid-combat confuses you for the rest of that fight. The sim …
- `relic/fake_strike_dummy/ModifyDamageAdditive` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. The amount is right -- DynamicVar('ExtraDamage', 1m) read as BaseValue (FakeStrikeDummy.cs, :39) vs EXTRA_DAMAGE = 1 (fake_strike_dummy.py), no AscensionHelper branch in the file …
- `relic/fake_strike_dummy/g2` — dormant — MECHANISM: FakeStrikeDummy.cs declines only when the dealer is not the owner's creature AND the card does not belong to the owner. In single-player the card's owner is always the player, so the second half is always false and the …
- `relic/fake_strike_dummy/g4` — **live** — The additive contribution is folded differently on the two sides: C#'s ModifyDamageInternal threads the RUNNING value through each listener and folds each contribution in immediately, in decimal (Hook.cs), while hooks.py hands …
- `relic/fake_venerable_tea_set/AfterRoomEntered` — *unlabelled* — Rollup of guard G1 per binding rule 4, and the whole of this record's finding: without the latch the relic can never fire in a real run.
- `relic/fake_venerable_tea_set/g1` — **live** — MECHANISM: FakeVenerableTeaSet.cs latches GainEnergyInNextCombat from AfterRoomEntered when `room is RestSiteRoom`. The sim's port implements ONLY the spend half and expects the latch as a constructor argument, `__init__(self …
- `relic/fake_venerable_tea_set/g2` — *unlabelled* — This is a SHAPE, not a one-off, and it is invisible to the existing sweeps -- .superpowers/sdd/content-relic-sweeps.md's sweep A diffs a field across two combats, and a field that is never written looks identical on both …
- `relic/festive_popper/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The effect's numbers are right -- DamageVar(9m, ValueProp.Unpowered) (FestivePopper.cs) vs DAMAGE = 9 at DamageProps.NON_CARD_UNPOWERED (festive_popper.py, :27), no …
- `relic/festive_popper/g1` — dormant — MECHANISM: step 22 is `await CardPileCmd.Draw(...)` then `await Hook.AfterPlayerTurnStart(state, choiceContext, player)` (CombatManager.cs), which itself runs Early -> plain -> Late passes (Hook.cs); step 23 is …
- `relic/festive_popper/g2` — dormant — Identical mechanism to relic/bag_of_marbles guard G2 and carried with the same gap verdict per binding rule 3, at another turn-1 all-enemies effect. C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs) and IsHittable is …
- `relic/fiddle/ModifyHandDrawLate` — *unlabelled* — Rollup of guards G2 and N1 per binding rule 4. The arithmetic matches -- Fiddle.cs returns `count + Cards.IntValue` and CanonicalVars pins CardsVar(2) (Fiddle.cs), the sim's CARDS = 2 (fiddle.py) -- but the hook is …
- `relic/fiddle/ShouldDraw` — **live** — Rollup of guard G1 per binding rule 4. C# has THREE bails and the sim reproduces one: `fromHandDraw -> return true` is `return from_hand_draw`, but `player != base.Owner` (N1, waived) and -- the substantive one …
- `relic/fiddle/g1` — **live** — MECHANISM: Fiddle.cs returns true (allow) on `fromHandDraw`, on a foreign player, and on `player.Creature.Side != player.Creature.CombatState.CurrentSide`. Only the fall-through returns false. So the relic's downside is scoped to …
- `relic/forgotten_soul/AfterCardExhausted` — dormant — Rollup of guard G1 per binding rule 4. Every number and stream matches -- DamageVar(1m, ValueProp.Unpowered) (ForgottenSoul.cs) is DAMAGE = 1 with DamageProps.NON_CARD_UNPOWERED (= ValueProp.UNPOWERED, valueprops.py), the dealer …
- `relic/fragrant_mushroom/g2` — dormant — MECHANISM: the source routes the 15 through the full damage command even out of combat, so the run-level Hook pipeline runs -- ModifyHpLostBeforeOsty / AfterOsty, the damage-received notifications, and the death check. …
- `relic/fresnel_lens/ModifyMerchantCardCreationResults` — *unlabelled* — FresnelLens.cs enchants every card the merchant stocks. Not implemented; same false premise as above (guard G1). The hook is live -- the egg relics use it (relics/_eggs.py) -- so the shelf shows un-enchanted cards where the game …
- `relic/fresnel_lens/TryModifyCardBeingAddedToDeck` — **live** — FresnelLens.cs replaces every card entering the deck with a Nimble-enchanted clone, gated on `ModelDb.Enchantment<Nimble>.CanEnchant(card)`. Not implemented. LIVE, executed (`py audit/tools/relic_probes_b06.py b06-stubs`): with …
- `relic/fresnel_lens/g1` — **live** — PROMPT.md bug class 12: a port that does nothing usually justifies itself with a claim about the sim, so check the claim. Executed (`py audit/tools/relic_probes_b06.py b06-stubs`): (a) `sts2_rl.enchantments.NimbleEnchantment` …
- `relic/fresnel_lens/g2` — dormant — PROMPT.md bug class 17 (shallow clones) applies to whoever implements this relic, so it is recorded now rather than discovered by the fix: CardModel.CreateClone / CardScope.CloneCard (CardModel.cs) carries the card's upgrade …
- `relic/frozen_egg/g3` — dormant — PROMPT.md bug class 17 at the egg relics' two sites. CardScope.CloneCard -> ClonePreservingMutability (CardModel.cs) carries upgrade level, enchantment, affliction, keyword edits and local energy-cost modifiers; the sim has no …
- `relic/fur_coat/AfterCreatureAddedToCombat` — *unlabelled* — Two divergences, both inherited rather than local. (a) C# fires Hook.AfterCreatureAddedToCombat for the STARTING creatures as well -- CombatManager.StartCombatInternal loops `foreach (Creature creature in _state.Creatures) await …
- `relic/fur_coat/BeforeCombatStart` — **live** — Rollup of guards G1 and G3 per binding rule 4. The effect matches -- every hittable enemy is set to 1 HP -- but C#'s test is `GetMarkedCoords.Contains(RunState.CurrentMapPoint.coord)` with NO act check (FurCoat.cs), while the …
- `relic/fur_coat/ModifyGeneratedMapLate` — **live** — See guard G2. The sim dispatches the Late map pass on EVERY fresh map generation; the game dispatches it on exactly one code path -- the SavedActMap (save-load) branch of RunManager.GenerateMap (RunManager.cs). The …
- `relic/fur_coat/g1` — **live** — MECHANISM: FurCoat.cs has an act check in exactly one place, AddMarkedRooms (line 65: `if (CurrentActIndex != FurCoatActIndex) return map;`), which controls only whether QUESTS get attached to map points. BeforeCombatStart …
- `relic/fur_coat/g2` — **live** — MECHANISM: `grep -rn ModifyGeneratedMapLate src/` outside AbstractModel.cs/Hook.cs returns three lines: the two implementers (src/Core/Models/Cards/SpoilsMap.cs, src/Core/Models/Relics/FurCoat.cs) and the single dispatch at …
- `relic/fur_coat/g3` — dormant — MECHANISM: CreatureCmd.SetCurrentHp (CreatureCmd.cs) does three things the raw assignment does not -- it fires `Hook.AfterCurrentHpChanged(runState, combatState, creature, delta)` whenever the value actually changed, it plays a …
- `relic/gambling_chip/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The hook SLOT is right and the turn gate matches, but CardCmd.DiscardAndDraw does two things the sim's inline loop does not: it routes each discard through CardPileCmd.Add (G2) …
- `relic/gambling_chip/g1` — dormant — MECHANISM: DiscardAndDraw collects `if (card.IsSlyThisTurn) slyCards.Add(card)` while discarding (CardCmd.cs), draws, and then `foreach (CardModel item in slyCards) await AutoPlay(choiceContext, item, null …
- `relic/gambling_chip/g2` — dormant — MECHANISM: CardPileCmd.Add runs the game's pile-change machinery -- Hook.ShouldAddToDeck / Hook.ModifyCardBeingAddedToDeck for deck adds, and Hook.AfterCardChangedPiles(+Late) generally -- plus `discardPile.InvokeContentsChanged` …
- `relic/game_piece/g1` — **live** — MECHANISM: CardModel.cs builds a fresh CardPlay inside `for (int i = 0; i < playCount; i++)` and fires Hook.AfterCardPlayed at line 1961 INSIDE that loop, so every replay is a separate AfterCardPlayed. …
- `relic/ghost_seed/AfterCardEnteredCombat` — dormant — Rollup of guard G2 per binding rule 4. The predicate and the effect match -- GhostSeed.cs applies CardKeyword.Ethereal to any card CanAffect accepts -- but C#'s `CardCmd.ApplyKeyword` adds a keyword whose SOURCE is tracked …
- `relic/ghost_seed/AfterRoomEntered` — dormant — See guard G1. GhostSeed.cs filters `room is CombatRoom` and then sweeps `Owner.PlayerCombatState.AllCards`; the sim iterates `self.player.all_cards` at on_combat_start. C#'s AfterRoomEntered for a combat room is dispatched at …
- `relic/ghost_seed/g1` — dormant — MECHANISM: the C# order is SetUpCombat -> Hook.AfterRoomEntered (CombatRoom.cs) -> AfterCombatRoomLoaded -> StartCombatInternal, which runs `Hook.AfterCreatureAddedToCombat` for every starting creature and only then …
- `relic/ghost_seed/g2` — dormant — MECHANISM: C# tracks WHERE each keyword came from, and CanAffect only refuses a card that already has a LOCALLY sourced Ethereal -- a card that is Ethereal for some other reason still receives Ghost Seed's own local copy, so the …
- `relic/girya/AfterRoomEntered` — dormant — See guard G2. Girya.cs applies StrengthPower equal to TimesLifted when `TimesLifted > 0 && room is CombatRoom`; girya.py does the same at combat start, two dispatch points later (C#'s AfterRoomEntered for a combat room fires at …
- `relic/girya/g2` — dormant — MECHANISM: CombatRoom.cs fires Hook.AfterRoomEntered after SetUpCombat, and CombatManager.StartCombatInternal then runs `AfterCreatureAdded` for every starting creature (CombatManager.cs) before `Hook.BeforeCombatStart` (:403). …
- `relic/glass_eye/g2` — **live** — PROMPT.md bug class 12: check the claim. MECHANISM: RollForUpgrade computes `originalOdds = baseChance + CurrentActIndex * UpgradedCardOddScaling` for any card whose Rarity != Rare, then lets Hook.ModifyCardRewardUpgradeOdds …
- `relic/glass_eye/g4` — **live** — MECHANISM: GlassEye.cs builds `CardCreationOptions.ForNonCombatWithUniformOdds(new [Owner.Character.CardPool], c => c.Rarity == rarity)`, and CreateForReward resolves the candidates through `options.GetPossibleCards(player)` …
- `relic/glitter/g1` — dormant — PROMPT.md bug class 17. CardScope.CloneCard -> ClonePreservingMutability (CardModel.cs) carries upgrade level, enchantment, affliction, keyword edits and local energy-cost modifiers, and the sim has no clone helper at all …
- `relic/gnarled_hammer/AfterObtained` — **live** — See guard G1 (LIVE). GnarledHammer.cs offers a non-cancelable pick-up-to-`Cards`(3) deck screen filtered to cards Sharp can enchant, then enchants each pick with Sharp at `SharpAmount`(3). gnarled_hammer.py implements nothing …
- `relic/gnarled_hammer/g1` — **live** — PROMPT.md bug class 12: a port that does nothing usually justifies itself with a claim about the sim, so check the claim. Executed (`py audit/tools/relic_probes_b06.py b06-stubs`): (a) `sts2_rl.enchantments.SharpEnchantment` …
- `relic/golden_pearl/g2` — dormant — MECHANISM: every gold gain in the game ends with a full listener pass over AfterGoldGained; run.gain_gold (run.py) stops after the addition. Golden Pearl itself does not implement AfterGoldGained, so the relic's OWN behaviour is …
- `relic/gorget/g4` — dormant — MECHANISM: PlatingPower.cs decrements in AfterSideTurnStart with a `TurnNumber != 1` guard for a player owner (turn_structure spec step 23, after the hand draw); powers.py's PlatingPower._decay runs from on_player_turn_start with …
- `relic/gremlin_horn/AfterDeath` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The relic's own body is exact -- GremlinHorn.cs's side check, EnergyVar(1) and CardsVar(1) map one-for-one onto gremlin_horn.py, and EXECUTED (py audit/tools/relic_probes_b07.py …
- `relic/gremlin_horn/g1` — **live** — MECHANISM, two layers. (a) CreatureCmd.Kill has two AfterDeath sites: line 519 on a real death and line 566 on a prevented one; the sim's DamageCmd.deal calls hooks.on_death ONLY in the should_die-true arm (cmds.py) and the …
- `relic/gremlin_horn/g2` — dormant — MECHANISM: CreatureCmd.cs runs AfterDamageGiven, then the killing-blow-guarded AfterDamageReceived, and only then `await Kill(killedCreatures)` -- so in C# every AfterDamageGiven listener sees the victim at 0 HP but not yet dead …
- `relic/hand_drill/g1` — dormant — MECHANISM: CreatureCmd.cs runs `Hook.AfterBlockBroken` and then `Hook.AfterDamageGiven` as separate statements in the per-result loop, so every AfterBlockBroken implementer is guaranteed to run before Hand Drill. In the sim both …
- `relic/hand_drill/g2` — dormant — MECHANISM: HandDrill.cs credits the owner's PET's damage to the owner, so an Osty (or any relic-granted pet) that breaks an enemy's block also triggers Hand Drill. The sim has no pet concept at all -- executed: `grep -rn …
- `relic/happy_flower/g3` — dormant — MECHANISM: C# folds Hook.ModifyEnergyGain, then fires AfterModifyingEnergyGain over the listeners that modified it, then adds only if the result is positive; the sim folds modify_energy_gain and adds unconditionally. Two …
- `relic/hefty_tablet/AfterObtained` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The skeleton is right -- three Rare candidates on the Rewards stream with prior picks excluded and no upgrade roll, a choose-one screen, then the chosen card and an Injury …
- `relic/hefty_tablet/g1` — **live** — MECHANISM: HeftyTablet.cs builds `new CardCreationOptions(Owner.Character.CardPool, ..., CardRarityOddsType.Uniform, c => c.Rarity == CardRarity.Rare)`, and CardFactory.CreateForReward -> CreateForReward(player, blacklist …
- `relic/hefty_tablet/g2` — dormant — MECHANISM: CardFactory.cs folds `Hook.TryModifyCardRewardOptions(player.RunState, player, list2, options, out modifiers)` and then AfterModifyingCardRewardOptions over the created reward list; HeftyTablet.cs sets …
- `relic/horn_cleat/AfterBlockCleared` — *unlabelled* — Rollup of guard G1 per binding rule 4. The relic's own arithmetic and guards are exact -- `creature == Owner.Creature && TurnNumber == 2` -> BlockVar(14, Unpowered) (HornCleat.cs) vs `target is self.player and self.turn == 2` -> …
- `relic/horn_cleat/g1` — **live** — This is audit/records/seam/turn_structure.json gap G1 (spec step 14) at the site that record already names -- its issue text cites HornCleat.cs and relics/horn_cleat.py as a NAMED PORTED LISTENER and labels the mechanism LIVE. …
- `relic/horn_cleat/g2` — dormant — MECHANISM: Creature.AfterTurnStart returns BEFORE ClearBlock for a player whose TurnNumber == 1, but the AfterBlockCleared loop still runs for that player; the sim's player.py has no turn-1 arm, so it both clears and fires. That …
- `relic/ice_cream/g2` — dormant — This is audit/records/seam/turn_structure.json gap at spec step 17, verdicted there and matched here per binding rule 3. MECHANISM: player.py folds modify_max_energy, then asks should_reset_energy, then assigns or accumulates …
- `relic/intimidating_helmet/g1` — **live** — MECHANISM: ResourceInfo has two separate fields and the struct's own doc comment spells the difference out -- 'The amount of energy that this card cost when it was played. Note that this is not necessarily the same as …
- `relic/intimidating_helmet/g3` — dormant — MECHANISM: CardModel.OnPlayWrapper does CardPileCmd.AddDuringManualCardPlay -> ModifyCardPlayResultPileTypeAndPosition -> GeneratePlayCount -> `if (Owner.Creature.IsDead) return` -> BeforeCardPlayed (CardModel.cs). combat.py …
- `relic/iron_club/g1` — **live** — MECHANISM: IronClub.cs declares `CanonicalVars => ... new CardsVar(4)`, and every consumer reads it -- DisplayAmount (line 32), UpdateDisplay (line 77) and the draw condition `CardsPlayed % intValue == 0` (lines 88-89). The port …
- `relic/jeweled_mask/g3` — dormant — MECHANISM: CardModel.SetToFreeThisTurn (CardModel.cs) adds a LocalCostModifier with `LocalCostModifierExpiration.EndOfTurn | LocalCostModifierExpiration.WhenPlayed` (CardEnergyCost.cs), and the source's own remark at …
- `relic/jeweled_mask/g4` — dormant — MECHANISM: C# calls `CardPileCmd.Add(cardModel, PileType.Hand)` (JeweledMask.cs), which goes through the pile machinery; the sim's CardPileCmd.add_to_hand overflows to the discard pile when the hand is at …
- `relic/joss_paper/AfterCardExhausted` — *unlabelled* — Rollup of guard G1 per binding rule 4. The counting arithmetic is exact -- CardsExhausted++ then DrawIfThresholdMet, threshold 5, draw `CardsExhausted / 5` truncated, then `CardsExhausted %= 5` (JossPaper.cs vs joss_paper.py) …
- `relic/joss_paper/AfterSideTurnEnd` — *unlabelled* — Rollup of guard G2 per binding rule 4. C#'s AfterSideTurnEnd (JossPaper.cs) fires unconditionally for the player side after the hand flush -- turn_structure spec step 64, the slot the sim exposes as after_player_turn_end …
- `relic/joss_paper/g1` — **live** — This is audit/records/seam/turn_structure.json gap G17 at the site that record names -- its issue text cites JossPaper.cs and relics/joss_paper.py directly, labels it LIVE, and pins it with …
- `relic/joss_paper/g2` — **live** — This is audit/records/seam/turn_structure.json gap G4 (spec step 64) at the site that record names, compounded with its gap G16 (on_hand_emptied's only call site is the one C# deliberately excludes). Both are verdicted `gap` …
- `relic/juzu_bracelet/ModifyUnknownMapPointRoomTypes` — **live** — MECHANISM: JuzuBracelet.cs copies the incoming room-type set, removes RoomType.Monster and returns it, so a '?' node can never roll a combat. The port is behaviourless and its docstring justifies itself with 'map-only effect …
- `relic/kifuda/AfterObtained` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. Kifuda.cs enchants up to 3 deck cards with Adroit at amount 3; the port does nothing at all.
- `relic/kifuda/g1` — **live** — MECHANISM: Kifuda.cs builds a CardSelectorPrefs with min 0 / max `DynamicVars.Cards.IntValue` == 3, Cancelable = false, then `CardSelectCmd.FromDeckForEnchantment(Owner, ModelDb.Enchantment<Adroit>, 3, prefs)` and, for each pick …
- `relic/kifuda/g2` — dormant — C# offers a not-cancelable screen whose selection size is 0..3 -- the player may confirm with fewer than 3 picks but may not back out -- while the sim's out-of-combat verb is `run.select_cards(purpose, candidates, count)` …
- `relic/kunai/BeforeSideTurnStart` — dormant — C#'s Hook.BeforeSideTurnStart is audit/records/seam/turn_structure.json step 9 -- it fires for BOTH sides BEFORE any block is cleared. The sim has no such slot; `py audit/tools/relic_probes.py turn-order` shows …
- `relic/kusarigama/AfterSideTurnEnd` — **live** — WRONG TURN-END SLOT. C#'s player-side AfterSideTurnEnd is audit/records/seam/turn_structure.json step 64 -- it runs AFTER the hand flush -- and the sim HAS that slot: hooks.after_player_turn_end (hooks.py), whose own docstring …
- `relic/kusarigama/g2` — dormant — C# picks the random target from `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHitting(CombatState, this)` (Creature.cs). Relic.living_enemies (relics/base.py) filters on `not …
- `relic/lantern/g1` — dormant — PlayerCmd.GainEnergy does five things: bail on `amount <= 0`, bail on `CombatManager.Instance.IsEnding`, `Hook.ModifyEnergyGain(... out modifiers)`, `await Hook.AfterModifyingEnergyGain(state, modifiers)`, then …
- `relic/lasting_candy/AfterCombatEnd` — dormant — LastingCandy.cs is the `CombatsSeen++` counter that decides 'every other combat' (IsInTriggeringCombat = `CombatsSeen > 0 && CombatsSeen % 2 == 0`, LastingCandy.cs). The sim's Relic base HAS the hook -- `after_combat_end(run …
- `relic/lasting_candy/TryModifyCardRewardOptions` — *unlabelled* — Rollup of guards G1 and G4 per binding rule 4. LastingCandy.cs adds a Power card to every OTHER combat's card reward; the port does nothing.
- `relic/lava_lamp/AfterDamageReceived` — **live** — LavaLamp.cs sets TookDamageThisCombat when FOUR guards pass: the current room is a CombatRoom, the target is the owner's creature, `result.UnblockedDamage > 0`, and the damage does NOT carry ValueProp.Unblockable. The sim's …
- `relic/lava_lamp/AfterRoomEntered` — **live** — LavaLamp.cs clears TookDamageThisCombat on EVERY room entry (the parameter is AbstractRoom, not CombatRoom). The sim's Relic base has the hook -- `after_room_entered(run, point, room_type)` (relics/base.py), dispatched over …
- `relic/lava_lamp/g2` — dormant — PROMPT.md bug class 17. CardModel.CreateClone is ClonePreservingMutability (CardModel.cs) and carries the card's enchantment, affliction, keyword edits and local energy-cost modifiers as well as its upgrade level …
- `relic/leafy_poultice/AfterObtained` — **live** — Rollup of guards G1, G2, N1 and N2 per binding rule 4. LeafyPoultice.cs does two things: `CreatureCmd.LoseMaxHp(ctx, Owner.Creature, MaxHpVar(12).BaseValue, isFromCard: false)`, then ONE `CardCmd.Transform([first Basic Strike …
- `relic/leafy_poultice/g1` — **live** — MECHANISM: CardCmd.Transform's Deck branch calls `Hook.ModifyCardBeingAddedToDeck(runState, replacement, out modifiers)` (CardCmd.cs) and awaits `Hook.AfterCardChangedPiles(...)` (CardCmd.cs) -- the same two hooks CardPileCmd.Add …
- `relic/leafy_poultice/g2` — **live** — MECHANISM: PROMPT.md bug class 16's second half. LeafyPoultice.cs passes the player's Transformations Rng, and -- unlike relic/claws, where every CardTransformation carries an explicit Replacement so GetReplacement never touches …
- `relic/leafy_poultice/g3` — dormant — CreatureCmd.LoseMaxHp (src/Core/Commands/CreatureCmd.cs) computes an UNFLOORED newMaxHp = MaxHp - amount and, when that is below CurrentHp, deals the difference as Unblockable|Unpowered damage through the whole pipeline -- hooks …
- `relic/letter_opener/g2` — dormant — C# damages `Enemies.Where(e => e.IsHittable)` -- `!IsDead && Hook.ShouldAllowHitting(...)` (src/Core/Combat/CombatState.cs; src/Core/Entities/Creatures/Creature.cs) -- while Relic.living_enemies filters on `not e.is_gone` only …
- `relic/lizard_tail/AfterPreventingDeath` — **live** — Rollup of guards G1, G2 and G3 per binding rule 4. LizardTail.cs heals `Math.Max(1, MaxHp * HealVar(50)/100)` in AfterPreventingDeath. The sim HAS that hook -- HookSystem.after_preventing_death (hooks.py), dispatched by …
- `relic/lizard_tail/ShouldDieLate` — **live** — Rollup of guards G3 and G4 per binding rule 4. The predicate itself is transcribed correctly -- veto only for the owner's creature, and only while not already used -- but (a) the sim collapses C#'s ShouldDie/ShouldDieLate …
- `relic/lizard_tail/g1` — **live** — MECHANISM: C#'s Kill leaves CurrentHp at 0 when a listener prevents the death (the `else` arm at src/Core/Commands/CreatureCmd.cs does NOT restore HP), and AfterPreventingDeath then heals `Math.Max(1m, (decimal)MaxHp * …
- `relic/lizard_tail/g2` — **live** — MECHANISM: the port routes its heal through on_damage_received, so it depends on that event firing after the veto. CreatureCmd.kill (cmds.py) calls `hooks.should_die(target)` with NO preventer list, never calls …
- `relic/lizard_tail/g3` — **live** — MECHANISM: LizardTail.ShouldDieLate (LizardTail.cs) is pure -- it reads WasUsed and returns -- and the charge is spent in AfterPreventingDeath (line 56). lizard_tail.py mutates `self._used = True` and `self._heal_pending = True` …
- `relic/lizard_tail/g4` — **live** — MECHANISM: Hook.ShouldDie (src/Core/Hooks/Hook.cs) runs EVERY listener's ShouldDie in a first full pass and only then every listener's ShouldDieLate in a second. A census of the game source finds exactly one non-mock override of …
- `relic/lizard_tail/g5` — dormant — C# decides whether to fire AfterDamageReceived from the pre-Kill snapshot (`!WasTargetKilled || !IsDead`) and never revisits it, so a hit that reduced the creature to 0 permanently skips AfterDamageReceived even when a listener …
- `relic/lords_parasol/AfterRoomEntered` — *unlabelled* — Rollup of guard G1 per binding rule 4. LordsParasol.cs filters AfterRoomEntered to a MerchantRoom and hands the inventory to PurchaseEverything, which buys the character cards, the colorless cards, the relics, the potions AND …
- `relic/lost_coffer/AfterObtained` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The card half is faithful in count, pool, odds type and pity behaviour (guard N1); the SKIP affordance is gone (G1) and the potion half rolls on the wrong stream from an approximated …
- `relic/lost_coffer/g4` — dormant — The flag exists so that relics which affect card REWARDS only (CardCreationFlags.cs names Prismatic Gem and Dingy Rug) can tell a reward roll from any other card creation. The sim's create_reward_cards runs …
- `relic/lucky_fysh/AfterCardChangedPiles` — *unlabelled* — Rollup of guards G1 and G3 per binding rule 4: 15 gold is never granted on the deck-add path (G1, the stub's premise is false) and would still be missed on the deck-transform path even after a naive fix (G3).
- `relic/lucky_fysh/g3` — **live** — MECHANISM: CardCmd.Transform on a **Deck** pile fires BOTH deck-add hooks -- `Hook.ModifyCardBeingAddedToDeck` (CardCmd.cs) and `Hook.AfterCardChangedPiles` (CardCmd.cs) -- because a transform replacement really does enter the …
- `relic/mango/AfterObtained` — *unlabelled* — The forward direction is faithful (guard N1): run.gain_max_hp(14) is CreatureCmd.GainMaxHp's SetMaxHp-then-Heal pair exactly. The gap is guard G1 -- the sim-only undo, which the conformance runner depends on, gives back the max …
- `relic/meal_ticket/AfterRoomEntered` — *unlabelled* — Rollup of guard G1 per binding rule 4 -- 15 HP is never healed on a shop entry, and the stub's premise for dropping it is false.
- `relic/meat_cleaver/TryModifyRestSiteOptions` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The option is added with the right id and the right numbers (guards N2, N3), but the sim OMITS it when it would be disabled instead of adding a disabled one (G1) and its effect …
- `relic/meat_cleaver/g1` — dormant — MECHANISM: CookRestSiteOption.OnSelect builds `CardSelectorPrefs(RemoveSelectionPrompt, 2) { Cancelable = true, RequireManualConfirmation = true }`, and `if (!enumerable.Any) return false` -- cancelling removes nothing, grants no …
- `relic/membership_card/ModifyMerchantPrice` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4: shop prices are never halved (G1), and the sim's price model could not express the discount even with the hook added, because it freezes each cost at stock time where C# recomputes …
- `relic/mercury_hourglass/AfterPlayerTurnStart` — *unlabelled* — Rollup of guard G1 per binding rule 4. The SLOT is right -- step 22 is 'Draw then Hook.AfterPlayerTurnStart' and the sim draws then fires on_player_turn_started -- and the damage, props, dealer, target set and turn-1 firing all …
- `relic/miniature_cannon/ModifyDamageAdditive` — *unlabelled* — Rollup of guard G1 per binding rule 4. Three of C#'s four early returns are reproduced exactly (N1-N3, all executed); the fourth is an AND that the port narrows to one of its two disjuncts.
- `relic/miniature_cannon/g1` — dormant — MECHANISM: miniature_cannon.py requires `dealer is self.player`, dropping C#'s `cardSource.Owner == base.Owner` alternative. In single-player the two disjuncts coincide for ordinary card play, so the divergence needs a …
- `relic/miniature_tent/g1` — dormant — MECHANISM: Hook.ShouldDisableRemainingRestSiteOptions (Hook.cs) walks every hook listener; RunState.should_disable_remaining_rest_site_options (run.py) walks only the relic list, so a non-relic listener could never keep a …
- `relic/molten_egg/ModifyMerchantCardCreationResults` — *unlabelled* — Same body as the reward path in C# too -- MoltenEgg.cs calls the identical EggRelicHelper.UpgradeValidCards -- and notably has NO NoHookUpgrades check, so the delegation is faithful in shape. Carries guard G4's verdict (the extra …
- `relic/molten_egg/TryModifyCardBeingAddedToDeck` — *unlabelled* — Rollup of guards G2 and G5 per binding rule 4. All four of MoltenEgg.cs's guards are reproduced (N1-N3) and the add_card route works (executed: a Bash added to the deck arrives at upgrade_level 1), but the DECK-TRANSFORM route …
- `relic/molten_egg/g2` — **live** — MECHANISM: CardCmd.Transform on a **Deck** pile fires BOTH deck-add hooks -- `Hook.ModifyCardBeingAddedToDeck` (CardCmd.cs) and `Hook.AfterCardChangedPiles` (CardCmd.cs) -- because a transform replacement really does enter the …
- `relic/molten_egg/g4` — dormant — MECHANISM: the reward and merchant paths both go through `EggRelicHelper.UpgradeValidCards(cards, CardType.Attack, this)` (MoltenEgg.cs, :39), whose only filter is `card.Type == cardType && card.IsUpgradable` (EggRelicHelper.cs) …
- `relic/molten_egg/g9` — dormant — MECHANISM: Hook.TryModifyCardRewardOptions (Hook.cs) walks every listener's non-Late override and then walks every listener's Late override, so a Late modifier is guaranteed to see the finished output of every plain one. Molten …
- `relic/mr_struggles/AfterPlayerTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The slot, the scaling amount, the props, the dealer and the target set all match (N1-N3), but the port omits the win check its identically shaped sibling relic/mercury_hourglass …
- `relic/mummified_hand/AfterCardPlayed` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The trigger matches (a Power play, MummifiedHand.cs) and the RNG stream matches (Rng.CombatCardSelection, MummifiedHand.cs, vs combat_rng.card_selection, mummified_hand.py), but …
- `relic/mummified_hand/g1` — **live** — MECHANISM: MummifiedHand.cs and :36 filter on `c.CostsEnergyOrStars(includeGlobalModifiers: true)`, which is `!EnergyCost.CostsX && EnergyCost.GetWithModifiers(CostModifiers.All) > 0` (CardModel.cs) -- the cost the player would …
- `relic/mummified_hand/g2` — **live** — MECHANISM: MummifiedHand.cs keeps falling back -- `NextItem(list)` (base cost > 0, however cheap it is now) and finally `NextItem(cards)` (ANY hand card) -- so the game always picks a card when the hand is non-empty. …
- `relic/music_box/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. The identity test (`cardPlay.Card == CardBeingPlayed`, MusicBox.cs), the Ethereal keyword, the destination pile and both state writes all match; what does not is `cardPlay.Card.CreateClone` …
- `relic/music_box/g1` — **live** — MECHANISM: MusicBox.cs calls `cardPlay.Card.CreateClone`, which is CardScope.CloneCard -> ClonePreservingMutability (CardModel.cs) and carries the card's upgrade level, Enchantment, Affliction, keyword edits and local energy-cost …
- `relic/mystic_lighter/ModifyDamageAdditive` — *unlabelled* — Rollup of guard G1 per binding rule 4 -- the relic's entire effect (+9 damage on your Enchanted Attacks) is missing.
- `relic/mystic_lighter/g2` — *unlabelled* — Recorded because it changes the finding's SIZE, not just its wording: the sweep files Mystic Lighter among the drops that are 'larger than a one-relic fix', which would park it behind a pipeline change that is not needed. It IS a …
- `relic/neows_bones/AfterObtained` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The SHAPE is right -- two relics drawn from Neow's own option pool on the per-player Rewards stream, then one generatable curse on the Niche stream -- and the shuffle algorithm, the …
- `relic/neows_talisman/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. Card SELECTION is faithful (the last Basic-rarity deck card carrying each of the Strike and Defend tags), but the upgrade itself is `card.upgrade` -- the sim's unguarded bare increment …
- `relic/neows_talisman/g1` — **live** — MECHANISM: CardCmd.Upgrade(IEnumerable) opens with `if (!card.IsUpgradable) continue;` (CardCmd.cs), and IsUpgradable is `CurrentUpgradeLevel < MaxUpgradeLevel` (CardModel.cs) -- C# additionally THROWS if CurrentUpgradeLevel is …
- `relic/new_leaf/AfterObtained` — dormant — Rollup of guards N1 and G1 per binding rule 4. Count, selection prompt and deck placement are all faithful; the named Niche RNG stream is dropped (N1, live for RNG parity) and the candidate list omits C#'s Quest-card exclusion …
- `relic/new_leaf/g2` — dormant — MECHANISM: CardSelectCmd.FromDeckForTransformation (CardSelectCmd.cs) builds its candidate list as `Cards.Where(c => c.Type != CardType.Quest && c.IsTransformable)`. run.transformable_cards (run.py) returns removable_cards, i.e. …
- `relic/nunchaku/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. Trigger, counter, modulus, energy amount and the counter's per-RUN lifetime all match; what does not is how many times the hook fires for a REPLAYED attack.
- `relic/nunchaku/g5` — dormant — This is the missing-AfterModifying-companion family that audit/records/seam/power_cmd.json gap G4 records (13 AfterModifying* variants in Hook.cs, one of them implemented in the sim) and that relic/bag_of_preparation N1 already …
- `relic/old_coin/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4 -- the relic's entire effect (+300 gold on pickup) is missing.
- `relic/old_coin/g3` — dormant — This is the missing-AfterModifying-companion family that audit/records/seam/power_cmd.json gap G4 records and that relic/bag_of_preparation N1 already verdicted `gap` at the hand-draw dispatcher; one verdict per mechanism …
- `relic/orichalcum/BeforeSideTurnEnd` — *unlabelled* — Rollup of guard G1 per binding rule 4. The grant itself is faithful -- 6 unpowered Block to the owner -- and C#'s `ShouldTrigger = false` before granting (Orichalcum.cs) is subsumed by the sim having no flag at all. What is lost …
- `relic/ornamental_fan/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. The Attack filter, the counter, the modulus and the 4 unpowered Block all match; what does not is how many times the hook fires for a REPLAYED Attack.
- `relic/ornamental_fan/g1` — **live** — This is audit/records/seam/hook_dispatch.json gap G4 at this relic's own site: CardModel.cs builds a fresh CardPlay per play-count iteration and fires Hook.AfterCardPlayed at :1959 INSIDE the loop, while combat.py and :514 …
- `relic/orrery/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4 -- the relic's entire effect (five 3-card choices added to the deck) is missing.
- `relic/paels_eye/AfterCombatEnd` — **live** — PaelsEye.cs is `base.Status = RelicStatus.Normal; UsedThisCombat = false;`. The sim clears used_this_combat nowhere. Carries guard G1's LIVE label; the Status half is presentation.
- `relic/paels_eye/BeforeSideTurnEndEarly` — *unlabelled* — MECHANISM: PaelsEye.cs exhausts the hand from Hook.BeforeTurnEnd's SECOND sub-slot (Hook.cs), i.e. inside the ordinary turn-end pass and BEFORE the extra turn has even been decided; its four guards (line 120) merely re-derive the …
- `relic/paels_eye/ShouldTakeExtraTurn` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The predicate itself maps clause for clause -- `!UsedThisCombat && !AnyCardsPlayedThisTurn && WasOwnerPartOfLastPlayerTurn` (PaelsEye.cs) against `not self.used_this_combat and …
- `relic/paels_eye/g4` — dormant — MECHANISM: C# short-circuits so Pael's Eye can never grant an extra turn on the first turn of a combat while Whispering Earring is held (the Earring auto-plays your hand for you, which would otherwise be free). The sim reaches …
- `relic/paels_legion/AfterCombatEnd` — **live** — PaelsLegion.cs resets FOUR things -- base.Status, `Cooldown = 0`, `TriggeredBlockLastTurn = false`, `AffectedCardPlay = null` -- and the sim's port resets none of them. Carries guard G1's LIVE label. Status/TriggeredBlockLastTurn …
- `relic/paels_legion/AfterModifyingBlockAmount` — *unlabelled* — See guard G4. C# keeps the LATCH in a separate hook that Hook.AfterModifyingBlockAmount (Hook.cs) only calls for listeners that actually changed the value, and whose own body then applies two further guards -- `modifiedAmount <= …
- `relic/paels_legion/ModifyBlockMultiplicative` — **live** — Rollup of guards G2, G3 and G4 per binding rule 4. The multiplier itself is right (2m at PaelsLegion.cs vs 2.0 at paels_legion.py, no AscensionHelper.GetValueIfAscension in the file), and the `cardSource == null` and …
- `relic/paels_legion/g3` — dormant — MECHANISM: PaelsLegion.cs checks props, cardSource and cardSource.Owner -- and NOTHING about the target. So in C#, a card played by the owner that grants block to any creature has that block doubled, including a creature that is …
- `relic/paels_legion/g4` — dormant — MECHANISM (PROMPT.md bug class 15 -- two C# hooks collapsed onto one sim method, and the guard sets differ): (a) CreatureCmd.GainBlock computes the modified amount, floors it at 0, and only then calls …
- `relic/paels_tears/AfterCombatEnd` — **live** — PaelsTears.cs is `HadLeftoverEnergy = false;` and nothing else -- the relic's only reset. The sim clears the flag nowhere. Carries guard G1's LIVE label.
- `relic/paels_tears/g2` — **live** — MECHANISM: the sim's CombatState.end_turn consults should_take_extra_turn FIRST and returns (combat.py), so on_player_turn_end (combat.py) never runs on that turn; C# runs the whole turn-end pass and only then asks …
- `relic/paels_tooth/AfterObtained` — **live** — Rollup of guards G1 and G2 per binding rule 4. The count matches (CardsVar(5), PaelsTooth.cs, read via DynamicVars.Cards.IntValue at :83, vs CARDS = 5 at paels_tooth.py; no AscensionHelper.GetValueIfAscension in the file) and …
- `relic/paels_tooth/g1` — **live** — MECHANISM: PaelsTooth.cs calls `CardSelectCmd.FromDeckForRemoval(..., filter: (CardModel c) => c.IsUpgradable)`, and FromDeckForRemoval itself ANDs `c.IsRemovable` onto the caller's filter (CardSelectCmd.cs). paels_tooth.py …
- `relic/paels_wing/TryModifyCardRewardAlternatives` — *unlabelled* — Rollup of guard G1 per binding rule 4. The alternative's payload is right -- the SACRIFICE key (PaelsWing.cs vs rewards.py's documented "SACRIFICE" semantics) and PostAlternateCardRewardAction.EndSelectionAndCompleteReward, i.e. …
- `relic/paels_wing/g1` — **live** — MECHANISM: C# builds the alternatives list in `CardRewardAlternative.Generate(CardReward)` (CardRewardAlternative.cs), whose line 68 calls Hook.ModifyCardRewardAlternatives (Hook.cs) -- and Generate takes a CardReward, so ANY …
- `relic/paper_phrog/ModifyVulnerableMultiplier` — *unlabelled* — Rollup of guards G1 and N2 per binding rule 4. NOT a Hook override: PaperPhrog.cs is a plain public method, and its ONE caller is VulnerablePower.ModifyDamageMultiplicative, which looks the relic up directly on the dealer …
- `relic/paper_phrog/g1` — dormant — MECHANISM: VulnerablePower.cs does `dealer.Player?.GetRelic<PaperPhrog>` and calls the method on that single instance, so the bonus is applied at most once no matter what. hooks.py folds `mult` through EVERY listener that defines …
- `relic/paper_phrog/g3` — dormant — MECHANISM: paper_phrog.py is `if dealer is self.player`, with no target check. Combined with the caller's requirement that the dealer be the phrog's owner (VulnerablePower.cs) and the power's requirement that the target be the …
- `relic/parrying_shield/AfterSideTurnEnd` — **live** — Rollup of guards G1 and G2 per binding rule 4. Everything else maps: the threshold and the damage are `new BlockVar(10m, ValueProp.Unpowered)` and `new DamageVar(6m, ValueProp.Unpowered)` (ParryingShield.cs) with no …
- `relic/parrying_shield/g1` — **live** — MECHANISM: ParryingShield.cs draws over `base.Owner.Creature.CombatState.HittableEnemies`, which is `Enemies.Where(e => e.IsHittable)` (CombatState.cs) with IsHittable = `!IsDead && Hook.ShouldAllowHitting(CombatState, this)` …
- `relic/parrying_shield/g2` — **live** — MECHANISM: the sim's CombatState.end_turn consults should_take_extra_turn FIRST and `return`s (combat.py), skipping on_player_turn_end, the turn-end cards, the hand flush AND after_player_turn_end (combat.py). C# runs the entire …
- `relic/pen_nib/AfterCardPlayed` — *unlabelled* — Rollup of guards G1 and G3. The unmark logic is identical (PenNib.cs: bail unless AttackToDouble is this card, then null it), but the same per-iteration/per-play mismatch applies -- C# fires it at CardModel.cs, INSIDE the …
- `relic/pen_nib/ModifyDamageMultiplicative` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The `cardSource == AttackToDouble -> 2m` arm (PenNib.cs) is ported exactly, but the port drops the whole `AttackToDouble == null` arm (PenNib.cs), which is what doubles the PENDING …
- `relic/pen_nib/g2` — **live** — MECHANISM: PenNib.cs reads `CardPile? pile = cardSource.Pile; if ((pile == null || pile.Type != PileType.Play) && AttacksPlayed == 9) return 2m;`. A card mid-OnPlay is in PileType.Play (PROMPT.md bug class 7), so this arm can …
- `relic/pen_nib/g3` — dormant — MECHANISM: the mark (AttackToDouble / _card_to_double) is cleared only by the AfterCardPlayed handler. C#'s dispatch of that hook is conditional, the sim's is not, so the two codebases can leave the relic in different states …
- `relic/pendulum/AfterPlayerTurnStart` — *unlabelled* — Rollup of guard G1 per binding rule 4. Everything the relic itself computes is faithful -- see guard N2 for the slot, the arithmetic and the constants -- but the sim collapses C#'s THREE AfterPlayerTurnStart passes and the …
- `relic/petrified_toad/BeforeCombatStartLate` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The relic's own logic -- procure one Potion Shaped Rock at the start of every combat -- is ported and the potion exists, but the port reaches the belt through …
- `relic/petrified_toad/g1` — **live** — MECHANISM: PotionCmd.TryToProcure (src/Core/Commands/PotionCmd.cs) opens with `if (!Hook.ShouldProcurePotion(...)) return NotAllowed;` before it ever calls Player.AddPotionInternal, and PetrifiedToad.cs goes through TryToProcure. …
- `relic/petrified_toad/g2` — **live** — MECHANISM: PotionCmd.TryToProcure fires `await Hook.AfterPotionProcured(...)` on success (PotionCmd.cs). Belt Buckle implements it and REMOVES the 2 Dexterity the moment the belt stops being empty …
- `relic/phial_holster/AfterObtained` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. Both halves of PhialHolster.cs are present in shape -- one extra slot then two random potions -- but the potion generation ignores the RNG stream the source names and rolls a flat …
- `relic/phial_holster/g1` — **live** — MECHANISM: PhialHolster.cs calls `PotionFactory.CreateRandomPotionsOutOfCombat(Owner, 2, RunState.Rng.CombatPotionGeneration)`, which is `rng.NextFloat` for the rarity band (<= 0.1f Rare, <= 0.35f Uncommon, else Common) plus …
- `relic/philosophers_stone/AfterCreatureAddedToCombat` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect and the constant are right -- 1 Strength on each joiner, executed at b12-stone: a mid-combat SpinyToad spawn comes in at Strength(1) -- and the two hooks provably cannot …
- `relic/philosophers_stone/g1` — dormant — MECHANISM: `if (creature.Side == base.Owner.Creature.Side) return;` is a side comparison; `if creature is self.combat.player: return` is an identity comparison. For any player-side creature other than the player itself -- a pet …
- `relic/pocketwatch/ModifyHandDraw` — *unlabelled* — Rollup of guard G1. The arithmetic and all three clauses are faithful -- `player != Owner` (multiplayer), `TurnNumber == 1`, and `_cardsPlayedLastTurn > CardThreshold` -> no bonus, else `count + Cards` (Pocketwatch.cs) map onto …
- `relic/pocketwatch/g1` — **live** — MECHANISM: CardModel.cs opens `for (int i = 0; i < playCount; i++)` and fires Hook.AfterCardPlayed at :1959 INSIDE it; combat.py fires on_card_played once, after the sim's whole play-count loop. Pocketwatch's threshold is a …
- `relic/potion_belt/AfterObtained` — **live** — SCOPE RULING (2026-07-26 relic fix pass, applied at every potion site in this tier). The shared contract's 'Out of scope everywhere: potions (deferred by Perry)' means POTION IS NOT AN AUDITED KIND -- there is no `potion` roster …
- `relic/prismatic_gem/g1` — dormant — MECHANISM: C# bails on NoCardPoolModifications, on !IsCardReward, on `options.CustomCardPool != null` and on `options.CardPools.All(p => p.IsColorless)`. The CustomCardPool bail is what keeps the relic away from narrowed pools …
- `relic/prismatic_gem/g2` — dormant — This is audit/records/seam/turn_structure.json step 17's finding, not a new one: `player.py` calls modify_max_energy first and should_reset_energy second, where CombatManager.cs evaluates ShouldPlayerResetEnergy first and only …
- `relic/punch_dagger/AfterObtained` — *unlabelled* — Rollup of guard G1 per binding rule 4. PunchDagger.cs enchants one deck card with Momentum 5 on pickup; the port does nothing.
- `relic/punch_dagger/CanonicalVars` — *unlabelled* — PunchDagger.cs pins `new DynamicVar('Momentum', 5m)` and AfterObtained reads it TWICE -- as the enchantment amount passed to CardSelectCmd.FromDeckForEnchantment and as the amount passed to CardCmd.Enchant (PunchDagger.cs, 30). …
- `relic/rainbow_ring/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. The trigger, the amounts, the applier and the order (Strength then Dexterity) all match; the difference is WHEN the once-per-turn latch is set relative to the two PowerCmd.apply calls.
- `relic/rainbow_ring/g1` — dormant — MECHANISM: C#'s guard is `ActivationCountThisTurn < 1` (RainbowRing.cs) and the counter is only bumped at line 119, after `await PowerCmd.Apply<StrengthPower>` and `await PowerCmd.Apply<DexterityPower>` have both resolved. …
- `relic/red_mask/BeforeSideTurnStart` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect is right -- 1 Weak (PowerVar<WeakPower>(1m), RedMask.cs) to every enemy on turn 1, applier = the player -- but the hook slot and the enemy set are both off. This relic is …
- `relic/red_mask/g1` — dormant — MECHANISM: audit/records/seam/turn_structure.json puts Hook.BeforeSideTurnStart at step 9 (before any block is cleared, before the energy reset and before the enemies re-roll their moves at step 11) and Hook.AfterSideTurnStart at …
- `relic/red_mask/g2` — dormant — C# targets `Enemies.Where(e => e.IsHittable)`, and IsHittable is `!IsDead && Hook.ShouldAllowHitting(...)`. Relic.living_enemies (relics/base.py) filters on `not e.is_gone` ONLY -- its own docstring concedes the …
- `relic/red_skull/AfterCombatEnd` — **live** — Rollup of guard G1 per binding rule 4 -- the LIVE gap. RedSkull.cs sets `StrengthApplied = false` at combat end (the base.Status half is presentation); the sim clears `_applied` nowhere, so the flag latches across the combat …
- `relic/red_skull/g3` — dormant — MECHANISM: C# re-evaluates the owner's threshold whenever ANY creature's HP changes during combat -- an enemy taking damage re-runs ModifyStrengthIfNecessary -- because the method reads Owner.Creature and ignores the hook's …
- `relic/regal_pillow/CanonicalVars` — *unlabelled* — RegalPillow.cs pins `new HealVar(15m)` and ModifyRestSiteHealAmount returns `amount + DynamicVars.Heal.BaseValue` (RegalPillow.cs). No AscensionHelper.GetValueIfAscension in the file, so 15 is the non-ascension value; the port …
- `relic/regal_pillow/ModifyRestSiteHealAmount` — **live** — Rollup of guard G1 per binding rule 4 -- the LIVE gap, and the ONLY behavioural hook this relic has.
- `relic/ringing_triangle/ShouldFlush` — *unlabelled* — Rollup of guard G1 per binding rule 4. The PREDICATE is exact -- `TurnNumber > 1` (RingingTriangle.cs) against `self.turn > 1`, and both aggregators are first-false-wins (Hook.ShouldFlush, Hook.cs, vs hooks.py) -- but the sim …
- `relic/ringing_triangle/g1` — **live** — MECHANISM: C#'s FlushPlayerHand treats `ShouldFlush == false` as 'every card is retained' -- cardsToFlush is empty and the batched Add is skipped -- but it still runs Hook.AfterFlush AND PlayerCombatState.EndOfTurnCleanup …
- `relic/royal_stamp/CanonicalVars` — *unlabelled* — RoyalStamp.cs pins `new CardsVar(1)` and a StringVar naming the enchantment; AfterObtained passes `amount: 1` to CardSelectCmd.FromDeckForEnchantment and `1m` to CardCmd.Enchant<RoyallyApproved> (RoyalStamp.cs, 39). The port …
- `relic/ruined_helmet/AfterCombatEnd` — **live** — Rollup of guard G1 per binding rule 4 -- the LIVE gap. RuinedHelmet.cs sets `UsedThisCombat = false`; the sim clears `_used` nowhere, so the relic works in the first combat of a run only.
- `relic/ruined_helmet/AfterModifyingPowerAmountReceived` — *unlabelled* — Rollup of guard G3 per binding rule 4. RuinedHelmet.cs is a SEPARATE C# hook that fires only for listeners whose Try returned true (Hook.cs collects them into `receivedModifiers`; PowerCmd.cs and :242 dispatch to exactly those) …
- `relic/ruined_helmet/TryModifyPowerAmountReceived` — *unlabelled* — Rollup of guards G2 and G3 per binding rule 4. The four C# clauses are reproduced exactly -- `canonicalPower is StrengthPower`, `target == Owner.Creature`, `amount <= 0`, `UsedThisCombat` (RuinedHelmet.cs) against …
- `relic/ruined_helmet/UsedThisCombat` — *unlabelled* — Rollup of guard G1 per binding rule 4. RuinedHelmet.cs is a plain bool with an AssertMutable setter; the divergence is not the field but the fact that nothing in the sim ever puts it back.
- `relic/ruined_helmet/g2` — dormant — This is audit/records/seam/power_cmd.json gap G3 at the site that record already names -- it cites `sts2_rl/relics/ruined_helmet.py` as the received-side listener and labels the mechanism a gap. One verdict per mechanism, binding …
- `relic/ruined_helmet/g3` — dormant — This is audit/records/seam/power_cmd.json gap G4 at its own site -- that record names RuinedHelmet.AfterModifyingPowerAmountReceived (RuinedHelmet.cs) as one of the two live C# listeners on the missing companion event, and …
- `relic/runic_pyramid/ShouldFlush` — **live** — Rollup of guards G1 and N1 per binding rule 4. The predicate itself is faithful -- the sim returns False unconditionally, matching RunicPyramid.cs for the owner -- but the sim's CONSUMER of the predicate diverges …
- `relic/sai/AfterSideTurnStart` — **live** — Rollup of guard G1 per binding rule 4. The SLOT is right -- audit/records/seam/turn_structure.json step 23 maps AfterSideTurnStart (player side) to on_player_turn_started -- but the sim collapses THREE C# dispatch passes into it …
- `relic/sai/g1` — dormant — MECHANISM: Hook.AfterSideTurnStart runs every listener's AfterSideTurnStart and then every listener's AfterSideTurnStartLate as two complete passes (Hook.cs), and it runs only after every player's SetupPlayerTurn -- i.e. after …
- `relic/screaming_flagon/BeforeSideTurnEnd` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The effect arithmetic is faithful (empty-hand gate, 20 Unpowered damage to every hittable enemy) but the sim's turn-end pipeline diverges twice at this hook: C#'s Hook.BeforeTurnEnd …
- `relic/screaming_flagon/g1` — **live** — MECHANISM: C# asks Hook.ShouldTakeExtraTurn LAST (CombatManager.cs) -- after Hook.BeforeTurnEnd, DoTurnEnd, the hand flush and Hook.AfterTurnEnd -- so a turn that grants an extra turn still runs every turn-end effect. combat.py …
- `relic/scroll_boxes/g1` — dormant — MECHANISM: the hook lets a listener rewrite the CardCreationOptions -- pool, rarity filter, flags -- before the candidate list is materialised, and ScrollBoxes calls it once per rarity (Common at line 73, Uncommon at line 75). …
- `relic/sea_glass/AfterObtained` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. SeaGlass.cs does two separable things: it offers 15 cards from ANOTHER character's pool (waived, N1 -- genuine other-character scope) and it burns 15 CardFactory.CreateForReward …
- `relic/seal_of_gold/AfterSideTurnStart` — **live** — Rollup of guards G1 and G2 per binding rule 4. The relic pays 5 gold for 1 Energy at the start of every player turn on both sides and the constants match, but the sim reads the WRONG gold balance -- it omits combat.gold_gained …
- `relic/seal_of_gold/g1` — **live** — MECHANISM: SealOfGold.cs gates on `base.Owner.Gold >= base.DynamicVars.Gold.IntValue` and PlayerCmd.GainGold updates Player.Gold live (PlayerCmd.cs), so gold won mid-combat is immediately spendable. seal_of_gold.py computes …
- `relic/seal_of_gold/g2` — dormant — MECHANISM as recorded for relic/sai in this batch: Hook.AfterSideTurnStart is a complete pass that runs after every step-22 Hook.AfterPlayerTurnStart listener and is followed by a second AfterSideTurnStartLate pass (Hook.cs …
- `relic/self_forming_clay/AfterDamageReceived` — **live** — Rollup of guards G1, G2 and N3 per binding rule 4. The latch is faithful (owner check, unblocked-damage > 0, +3 per HP-loss event, killing-blow guard inherited from cmds.py) but the RE-ARCHITECTURE of the payout is where the …
- `relic/self_forming_clay/g1` — **live** — MECHANISM: C# has no relic-side counter at all. SelfFormingClay.cs applies a SelfFormingClayPower to the owner and SelfFormingClayPower.cs pays it out at AfterBlockCleared and then removes itself, so the pending block is a POWER …
- `relic/self_forming_clay/g2` — **live** — MECHANISM: SelfFormingClayPower.AfterBlockCleared (SelfFormingClayPower.cs) fires in the block-clear pass, before the energy reset, before ModifyHandDraw and before the whole AfterPlayerTurnStart / AfterSideTurnStart region …
- `relic/self_forming_clay/g3` — dormant — MECHANISM: `grep -rn SelfFormingClay sts2_rl/powers.py` returns nothing -- the sim models the effect as a private int on the relic. In C# it is a real PowerModel with `Type => Buff` and `StackType => Counter` …
- `relic/shovel/TryModifyRestSiteOptions` — *unlabelled* — Rollup of guard G2 per binding rule 4. The DIG option's effect matches -- RelicCmd.Obtain(RelicFactory.PullNextRelicFromFront(Owner)) (DigRestSiteOption.cs) maps to run.obtain_relic_from_grab_bag (shovel.py), and the default …
- `relic/shovel/g2` — dormant — MECHANISM: Shovel.TryModifyRestSiteOptions adds `new DigRestSiteOption(player)` unconditionally (Shovel.cs) and DigRestSiteOption overrides nothing that could disable it -- RestSiteOption.IsEnabled is the base `=> true` …
- `relic/signet_ring/g2` — dormant — MECHANISM: C#'s gold pipeline is the same two-phase shape as its damage and power pipelines -- ModifyGoldGained collects the listeners that changed the amount, then AfterModifyingGoldGained notifies exactly those listeners with …
- `relic/silken_tress/AfterModifyingCardRewardOptions` — *unlabelled* — MECHANISM: C# spends the charge from a SEPARATE hook, and Hook.AfterModifyingCardRewardOptions only notifies models that RETURNED TRUE from the modifier pass (Hook.cs walks the listeners and skips any not in the `modifiers` list …
- `relic/silken_tress/g1` — **live** — MECHANISM: C# refuses to touch the options unless `options.Flags.HasFlag(CardCreationFlags.IsCardReward)`, and that flag is set by exactly two places in the whole game -- CardReward's two constructors (CardReward.cs and :134) and …
- `relic/silver_crucible/AfterModifyingCardRewardOptions` — **live** — MECHANISM: C# spends the charge from a SEPARATE hook, and Hook.AfterModifyingCardRewardOptions only notifies models that RETURNED TRUE from the modifier pass (Hook.cs, against the `modifiers` list Hook.cs collects). …
- `relic/silver_crucible/ShouldGenerateTreasure` — *unlabelled* — Rollup of guard G3 per binding rule 4. The predicate matches (`TreasureRoomsEntered > 1`, SilverCrucible.cs) and so does the all-must-agree dispatcher (`if (!item.ShouldGenerateTreasure(player)) return false`, Hook.cs). What …
- `relic/silver_crucible/g1` — **live** — MECHANISM: C# refuses to touch the options unless `options.Flags.HasFlag(CardCreationFlags.IsCardReward)`, and that flag is set by exactly two places in the whole game -- CardReward's two constructors (CardReward.cs and :134) and …
- `relic/silver_crucible/g3` — dormant — MECHANISM: C# reaches the Spoils Map payout only from INSIDE the gated reward routine -- OneOffSynchronizer.DoTreasureRoomRewards opens with `if (!Hook.ShouldGenerateTreasure(player.RunState, player)) return 0;` …
- `relic/sling_of_courage/AfterRoomEntered` — dormant — Rollup of guard N1 per binding rule 4. SlingOfCourage.cs applies PowerVar<StrengthPower>(2) from AfterRoomEntered when `room.RoomType == RoomType.Elite`, and for a CombatRoom that hook fires after CombatManager.SetUpCombat and …
- `relic/sling_of_courage/g1` — dormant — MECHANISM: for a CombatRoom, `Hook.AfterRoomEntered` fires at CombatRoom.cs, between SetUpCombat (line 225) and AfterCombatRoomLoaded (line 230), which starts the combat and dispatches Hook.BeforeCombatStart. So in C# nothing in …
- `relic/snecko_eye/AfterObtained` — dormant — SneckoEye.cs applies the Confused power immediately when the relic is picked up DURING a combat (`if (CombatManager.Instance.IsInProgress) await ApplyPower`). snecko_eye.py defines only on_combat_start and modify_hand_draw, so a …
- `relic/sozu/ShouldProcurePotion` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. The predicate itself is right and the out-of-combat gate works; the divergence is that C# funnels EVERY procurement through one gated command and the sim has a second, ungated …
- `relic/sozu/g1` — **live** — MECHANISM: in C# there is exactly ONE procure entry point -- PotionCmd.TryToProcure (PotionCmd.cs) -- and its first statement is the Hook.ShouldProcurePotion gate (PotionCmd.cs); an executed grep finds all ten callers go through …
- `relic/sparkling_rouge/AfterBlockCleared` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect, the amounts and the turn number all match; the hook SLOT does not.
- `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The arithmetic is right -- a Power card costs 1 more -- but the sim has no phase structure and no per-creature listener grouping, and this relic is the named ported witness for …
- `relic/spiked_gauntlets/g1` — **live** — This is audit/records/seam/hook_dispatch.json gap G2 at the site that record already names as its executed witness, so per binding rule 3 this entry cites and matches rather than re-deriving: the seam's steps 1, 2, 5, 41 and 43 …
- `relic/spiked_gauntlets/g2` — dormant — Hook.ModifyEnergyCostInCombat runs TWO complete listener passes -- every TryModifyEnergyCostInCombat, then every TryModifyEnergyCostInCombatLate (Hook.cs). SpikedGauntlets implements the PLAIN one (SpikedGauntlets.cs), so in C# …
- `relic/spiked_gauntlets/g3` — dormant — Three differences in the same collapse, checked side by side per PROMPT.md bug class 15. (a) The owner guard (SpikedGauntlets.cs) is multiplayer-only and is separately waived at N1. (b) Hook.ModifyEnergyCostInCombat opens with …
- `relic/stone_calendar/BeforeSideTurnEnd` — *unlabelled* — Rollup of guards G1 and G2 per binding rule 4. The trigger turn, the damage number, the target set and the props all match and are executed; the divergences are the flattened sub-phase ordering (G1) and the …
- `relic/stone_calendar/g2` — dormant — Same mechanism and therefore the same verdict as relic/bag_of_marbles guard G2 (binding rule 3): C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHitting(...)`, while …
- `relic/stone_cracker/g2` — dormant — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE ported relics whose C# combat effect hangs off `AfterRoomEntered` with a `room is CombatRoom` test are mapped onto the sim's …
- `relic/stone_humidifier/AfterRestSiteHeal` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect and its amount are exactly right; the dispatch is missing one of the hook's two C# call sites.
- `relic/stone_humidifier/g1` — dormant — MECHANISM: an executed grep for AfterRestSiteHeal over the decompiled source finds two callers outside the relic models -- HealRestSiteOption.cs (`isMimicked` forwarded from the option) and MendRestSiteOption.cs (`isMimicked …
- `relic/strike_dummy/ModifyDamageAdditive` — *unlabelled* — Rollup of guards G1, G2 and N1 per binding rule 4. The +3 on a Strike-tagged powered attack is right and executed; the props gate has been hoisted out of the listener into the call site (G1) and the dealer/owner clause has been …
- `relic/strike_dummy/g2` — dormant — MECHANISM: StrikeDummy.cs is `if (dealer != base.Owner.Creature && cardSource.Owner != base.Owner) return 0m;` -- a conjunction of negatives, so either clause alone suffices. strike_dummy.py requires `dealer is self.player` and …
- `relic/sturdy_clamp/AfterPreventingBlockClear` — *unlabelled* — Rollup of guards G2, G3 and N1 per binding rule 4. The 10-block cap is right, but it runs from a different hook, at a different point in the turn, with no preventer test, and on turn 1 where C# never reaches it.
- `relic/sturdy_clamp/ShouldClearBlock` — *unlabelled* — Rollup of guards G1 and G3 per binding rule 4. The predicate itself is a faithful transcription of SturdyClamp.cs (veto for the owner, allow for everyone else), but the sim's dispatcher returns a bare bool with no PREVENTER …
- `relic/sturdy_clamp/g1` — **live** — This is audit/records/seam/turn_structure.json gap G1 at the site that record already names, so per binding rule 3 this entry cites and matches rather than re-deriving. That record's issue text: C# runs the clear and the event as …
- `relic/sturdy_clamp/g2` — **live** — This is audit/records/seam/turn_structure.json gap G2, which that record raised specifically about this relic, so per binding rule 3 the verdict is cited and matched. Its mechanism: Creature.ClearBlock (Creature.cs) passes the …
- `relic/sturdy_clamp/g3` — dormant — MECHANISM, and this is a third divergence the seam's G1/G2 do not cover: Creature.AfterTurnStart opens with `if (side == CombatSide.Player && player.PlayerCombatState?.TurnNumber == 1) return;` (Creature.cs), so ClearBlock -- and …
- `relic/sword_of_jade/AfterRoomEntered` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. The power, the amount and the target are right and executed; the hook SITE is one dispatch later than C#'s and the applier identity differs.
- `relic/sword_of_jade/g1` — dormant — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE ported relics whose C# combat effect hangs off `AfterRoomEntered` with a `room is CombatRoom` test are mapped onto the sim's …
- `relic/tea_of_discourtesy/BeforeCombatStart` — **live** — Rollup of guards G1 and G2 per binding rule 4. The SHAPE is right -- 2 Dazed into the draw pile at a random position, one charge, decrement after -- but the port hand-rolls CardPileCmd.AddToCombatAndPreview instead of calling the …
- `relic/tea_of_discourtesy/g1` — **live** — MECHANISM: CardPileCmd.cs resolves CardPilePosition.Random as `card.Owner.RunState.Rng.Shuffle.NextInt(targetPile.Cards.Count + 1)`, an index into a pile whose TOP is index 0. The sim stores the draw pile with its top at the END …
- `relic/tea_of_discourtesy/g2` — dormant — MECHANISM: C# creates the card with `combatState.CreateCard<T>(player)` (CardPileCmd.cs) and adds it through AddGeneratedCardToCombat, which fires `Hook.AfterCardEnteredCombat` (CardPileCmd.cs) and puts the CardModel in the …
- `relic/the_abacus/AfterShuffle` — *unlabelled* — Rollup of guard N4 per binding rule 4. The effect, the owner guard and the constant all match and the trigger set is executed-confirmed identical (N3); the one divergence is that C# refuses to dispatch AfterShuffle once the …
- `relic/the_abacus/g4` — dormant — MECHANISM: CardPileCmd.Shuffle returns immediately on `CombatManager.Instance.IsOverOrEnding` (CardPileCmd.cs), bails out mid-way through its card-add loop on the same condition (:897-900), and wraps the hook itself in `if …
- `relic/the_boot/ModifyHpLostAfterOstyLate` — **live** — Rollup of guards G1 and G2 per binding rule 4. The arithmetic is right (raise 1..4 unblocked HP loss to 5), but the sim has no LATE phase, so the relic loses the ordering guarantee its C# hook name carries (G1, LIVE), and the …
- `relic/the_boot/g1` — **live** — MECHANISM: Hook.ModifyHpLost (Hook.cs) runs `ModifyHpLostAfterOsty` over EVERY listener and then `ModifyHpLostAfterOstyLate` over EVERY listener -- two `foreach`es, which PROMPT.md bug class 25 says to count before verdicting any …
- `relic/the_boot/g2` — dormant — MECHANISM: ValuePropExtensions.IsPoweredAttack (ValuePropExtensions.cs) is `props.HasFlag(Move) && !props.HasFlag(Unpowered)` -- a property of the DAMAGE CALL. the_boot.py asks about the CARD instead: `if card is None or …
- `relic/the_courier/ModifyMerchantPrice` — **live** — Rollup of guard G1 per binding rule 4 (LIVE).
- `relic/tiny_mailbox/TryModifyRestSiteHealRewards` — **live** — Rollup of guard G1 per binding rule 4 (LIVE).
- `relic/toasty_mittens/BeforeHandDraw` — *unlabelled* — Rollup of guard G1 per binding rule 4. HALF THE RELIC IS MISSING: ToastyMittens.cs exhausts a draw-pile card AND applies 1 Strength every turn; the port implements only the exhaust. The slot, the reshuffle, the turn-1 non-Innate …
- `relic/toasty_mittens/g1` — **live** — MECHANISM: ToastyMittens.cs is `await PowerCmd.Apply<StrengthPower>(choiceContext, player.Creature, base.DynamicVars.Strength.BaseValue, player.Creature, null);` and it sits OUTSIDE the `if (cardModel != null)` branch that guards …
- `relic/touch_of_orobas/AfterObtained` — dormant — Rollup of guards G1 and N4 per binding rule 4. The core behaviour is right and executed: the starter relic is replaced IN PLACE by its refinement and the replacement's own after_obtained runs. What the port drops from …
- `relic/touch_of_orobas/g2` — dormant — MECHANISM: the port bypasses RunState.add_relic (run.py) entirely -- it writes into run.relics itself -- so nothing removes the replacement from the run's grab bag and a later pull could offer the same relic a second time. …
- `relic/toy_box/AfterCombatEnd` — dormant — Rollup of guards G2 and N1 per binding rule 4. The counter and the every-3rd-combat trigger are faithful (N1); the divergence is that RelicCmd.Melt leaves the melted relic in the player's relic list as an inert entry and the port …
- `relic/toy_box/AfterObtained` — **live** — Rollup of guard G1 per binding rule 4: the four pulls, their order, the IsWax marking and the stream they come off are all faithful (guard N2), but the four relics are FORCE-GRANTED where ToyBox.cs offers them on a skippable …
- `relic/toy_box/g2` — dormant — MECHANISM: RelicCmd.Melt (RelicCmd.cs) is `relic.Owner.MeltRelicInternal(relic); await relic.AfterRemoved;` -- the relic STAYS in the list, and the game stops it working by excluding melted relics from both hook-listener walks …
- `relic/tungsten_rod/g6` — dormant — MECHANISM: out of combat, C# gives deck cards, card enchantments, relics, potions, Modifiers, BadgeModels and the MultiplayerScalingModel a chance at ModifyHpLost; the sim's out-of-combat path consults relics alone. That is …
- `relic/tuning_fork/AfterCardPlayed` — *unlabelled* — Rollup of guard G1 per binding rule 4. Every clause of the relic is faithful -- the Skill test, the >= threshold, the `-= threshold` rather than a zeroing, the 10 and the 7, and (contrary to its own docstring) the per-run counter …
- `relic/tuning_fork/g1` — **live** — MECHANISM: CardModel.cs builds a fresh CardPlay inside `for (int i = 0; i < playCount; i++)` and fires Hook.AfterCardPlayed at line 1961 INSIDE that loop, so TuningFork.AfterCardPlayed (TuningFork.cs) runs once per iteration. The …
- `relic/unceasing_top/AfterHandEmptied` — **live** — Rollup of guards G1 and G2 per binding rule 4. The reroute is deliberate and mostly right (N1): the sim's on_hand_emptied fires only from the end-of-turn flush, which is the one site C# deliberately excludes, so listening on …
- `relic/unceasing_top/g1` — dormant — audit/records/seam/turn_structure.json guard G16 already verdicts this mechanism a `gap` and names this exact port as the reason it is DORMANT there: 'The one C# AfterHandEmptied implementer was re-wired away from it …
- `relic/unceasing_top/g2` — **live** — MECHANISM: `grep -rn 'CheckForEmptyHand' src/` gives the definition (CombatManager.cs) and exactly two callers -- CardModel.cs, after a card play resolves, and PotionModel.cs, after a potion's effect resolves -- and …
- `relic/unceasing_top/g3` — dormant — MECHANISM: C# refuses the empty-hand check while any card or potion effect is still executing -- CardModel.cs's play path releases the depth counter at EndCardOrPotionEffect (CardModel.cs) and only then reaches CheckForEmptyHand …
- `relic/unsettling_lamp/BeforePowerAmountChanged` — *unlabelled* — The latch is not separable from the double in the sim, which is what makes guards G2 and G3 possible: C# runs seven latch guards (UnsettlingLamp.cs) and a DIFFERENT five-guard set on the multiplicative (lines 108-127), and the …
- `relic/unsettling_lamp/ModifyPowerAmountGivenMultiplicative` — dormant — C# returns a MULTIPLICATIVE factor into Hook.ModifyPowerAmountGiven's two-pass fold (Hook.cs: every listener's additive contribution is summed FIRST, then every listener's multiplicative factor is applied to that sum). The sim's …
- `relic/unsettling_lamp/g3` — dormant — MECHANISM: PowerModel.GetTypeForAmount (PowerModel.cs) returns Debuff when `StackType == Counter && AllowNegative && amount < 0`, so a NEGATIVE-amount Strength or Dexterity -- both declared Type => Buff -- is a Debuff for the …
- `relic/unsettling_lamp/g5` — dormant — MECHANISM: UnsettlingLamp.cs puts the applier and target-side checks on BeforePowerAmountChanged (the latch) only. ModifyPowerAmountGivenMultiplicative (lines 106-129) checks just TriggeringCard / cardSource / …
- `relic/unsettling_lamp/g6` — dormant — MECHANISM: PowerCmd.Apply carries cardSource explicitly, so C# knows the exact card responsible for each individual power application; the Lamp compares `cardSource != TriggeringCard` (UnsettlingLamp.cs). The sim reconstructs it …
- `relic/vajra/g1` — dormant — MECHANISM: as above -- one full combat-setup phase separates the two positions, and it contains AfterCreatureAdded plus every enemy's opening RollMove. TWO readers could expose it and neither exists in ported content. (a) A …
- `relic/vambrace/AfterCardPlayed` — *unlabelled* — Rollup of guard G3 per binding rule 4. Vambrace.cs is where the charge is actually spent: BlockGainedThisCombat = true, gated on the played card being the latched TriggeringCard and on the flag not already being set. Dropping …
- `relic/vambrace/AfterCombatEnd` — **live** — The SECOND of C#'s two resets (Vambrace.cs, mirroring BeforeCombatStart at :49-55). Recorded separately because C# is deliberately redundant here and the sim has neither, so the flag latches for the whole run. Carries guard G1's …
- `relic/vambrace/AfterModifyingBlockAmount` — *unlabelled* — Rollup of guard G3 per binding rule 4. Vambrace.cs sets ONLY TriggeringCard here (plus Flash/Status); it does NOT spend the once-per-combat charge. The port sets `_used = True` here instead (vambrace.py), which spends the charge …
- `relic/vambrace/BeforeCombatStart` — *unlabelled* — Rollup of guard G1 per binding rule 4. Vambrace.cs clears BOTH state fields (TriggeringCard = null, BlockGainedThisCombat = false) and sets base.Status = Active. The port clears neither, and has no combat-boundary hook at all, so …
- `relic/vambrace/g3` — **live** — MECHANISM: C# splits the job across three hooks. AfterModifyingBlockAmount latches `TriggeringCard = cardSource` (Vambrace.cs) and nothing else; ModifyBlockMultiplicative then returns 2 for any gain whose cardSource IS that …
- `relic/vambrace/g6` — *unlabelled* — PROMPT.md bug class 24 -- a docstring that misdescribes the PORT. The multiplier hook is NOT stateless: vambrace.py reads `self._used`, which is exactly the per-combat state. The claim reads as a justification for putting the …
- `relic/velvet_choker/g2` — *unlabelled* — VelvetChoker.cs is a BeforeSideTurnStart override that zeroes `_cardsPlayedThisTurn` on every player turn start, so the comment's premise -- that the per-turn reset is a sim invention -- is false, and it invites a future reader …
- `relic/venerable_tea_set/AfterRoomEntered` — *unlabelled* — Rollup of guard G1 per binding rule 4, and the whole of this record's finding. VenerableTeaSet.cs latches GainEnergyInNextCombat = true whenever a RestSiteRoom is entered. Note what the C# latch is actually keyed on: room ENTRY …
- `relic/venerable_tea_set/GainEnergyInNextCombat` — *unlabelled* — Rollup of guard G1 per binding rule 4. The C# property is a [SavedProperty] whose change-guarded setter flips base.Status (VenerableTeaSet.cs); the persistence it needs -- survive the rest site, the map walk and the next combat's …
- `relic/venerable_tea_set/g1` — **live** — MECHANISM: the port's entire trigger is `self._pending = rested`, a constructor default (venerable_tea_set.py). RunState.add_relic builds relics through `make_relic(id)`, which is `_RELIC_CLASSES[relic_id]` with no arguments …
- `relic/vexing_puzzlebox/AfterPlayerTurnStart` — *unlabelled* — Rollup of guard G1 per binding rule 4. The effect itself is right: one distinct combat-generated card from the character pool, set free for the turn, added to hand on turn 1 only (executed below). What is wrong is the SLOT. C#'s …
- `relic/vexing_puzzlebox/g1` — **live** — MECHANISM: C# gives the two relics different phases. Vexing Puzzlebox implements Hook.AfterPlayerTurnStart (turn_structure step 22, right after the draw); Whispering Earring implements Hook.AfterAutoPrePlayPhaseEnteredLate, the …
- `relic/vexing_puzzlebox/g4` — dormant — C#'s SetToFreeThisTurn is `EnergyCost.SetThisTurnOrUntilPlayed(0)` plus SetStarCostThisTurn(0) (CardModel.cs). The sim's set_free_this_turn sets `_free_this_turn = True` (sts2_rl/cards/base.py) and clears it only in …
- `relic/war_paint/AfterObtained` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. WarPaint.cs upgrades CardsVar(2) randomly chosen upgradable SKILLS in the deck; the port upgrades nothing and consumes no Niche draw.
- `relic/war_paint/g3` — **live** — Recorded so a fix does not lose the filter: the Skill test is what distinguishes this relic from its identical twin Whetstone (Attacks) and from War Hammer (any upgradable card), and `IsUpgradable` is what keeps PROMPT.md bug …
- `relic/whetstone/AfterObtained` — *unlabelled* — Rollup of guards G1 and N1 per binding rule 4. Whetstone.cs upgrades CardsVar(2) randomly chosen upgradable ATTACKS in the deck; the port upgrades nothing and consumes no Niche draw.
- `relic/whetstone/g3` — **live** — Recorded so a fix does not lose the filter. `IsUpgradable` is what keeps PROMPT.md bug class 14 from firing -- the sim's Card.upgrade is a bare `upgrade_level += 1` (sts2_rl/cards/base.py) with no guard, and 18 ported Curses and …
- `relic/whispering_earring/AfterAutoPrePlayPhaseEnteredLate` — *unlabelled* — Rollup of guards G1, G2 and G3 per binding rule 4. The loop's SHAPE is right -- up to 13 iterations, break on combat over / turn change / nothing playable, take the first playable card in hand, spend its energy, play it. Three …
- `relic/whispering_earring/g1` — **live** — MECHANISM: Hook.AfterAutoPrePlayPhaseEntered runs AfterAutoPrePlayPhaseEnteredEarly, then AfterAutoPrePlayPhaseEntered, then AfterAutoPrePlayPhaseEnteredLate as three separate complete passes (Hook.cs) -- PROMPT.md bug class 25 …
- `relic/whispering_earring/g3` — **live** — MECHANISM: WhisperingEarring.cs wraps the loop in `using (CardSelectCmd.PushSelector(new VakuuCardSelector))`, and VakuuCardSelector.GetSelectedCards is `options.Take(maxSelect)` in row-major order (VakuuCardSelector.cs) -- fully …
- `relic/whispering_earring/g4` — dormant — The sim's loop breaks on `combat.is_over` and `self.turn != start_turn` (whispering_earring.py) but has no notion of a player having signalled 'end turn'. In the game this matters because the AutoPrePlay phase is asynchronous and …
- `relic/white_beast_statue/ShouldForcePotionReward` — *unlabelled* — Rollup of guard G1 per binding rule 4. WhiteBeastStatue.cs returns true for the owner on any combat room, forcing a potion into that room's reward screen; the port forces nothing.
- `relic/white_beast_statue/g3` — **live** — Recorded so a fix uses the right predicate rather than 'monster rooms'. RoomTypeExtensions.IsCombatRoom is `(uint)(room - 1) <= 2u` (RoomTypeExtensions.cs), i.e. the three room-type enum values immediately after the first one …
- `relic/white_star/TryModifyRewards` — *unlabelled* — Rollup of guard G1 per binding rule 4. WhiteStar.cs appends `new CardReward(CardCreationOptions.ForRoom(Owner, RoomType.Boss), 3, player)` to every ELITE room's reward list -- a second, Boss-tier three-card choice on top of the …
- `relic/white_star/g3` — **live** — Recorded so a fix uses the right odds rather than the elite's. ForRoom(RoomType.Boss) selects CardRarityOddsType.BossEncounter (CardCreationOptions.cs), and the sim has that table already: rewards.py maps RarityOddsType.BOSS to …
- `relic/wing_charm/g3` — dormant — PROMPT.md bug class 17. WingCharm.cs clones the chosen option and enchants the CLONE, then substitutes it via `cardCreationResult.ModifyCard(card, this)` (:43) rather than mutating the original -- so a fix that follows the C# …
- `relic/winged_boots/g3` — dormant — MECHANISM: in C# the charge is each relic's own business, so two free-travel sources both react to the same non-child travel -- Winged Boots would still burn a use even if something else were already granting the travel. The …
- `relic/wongos_mystery_ticket/TryModifyRewards` — **live** — Rollup of guards G1, N2, N5, N6, N7, N10 and N13 per binding rule 4 -- worst is G1, LIVE. The arithmetic and the latch match clause for clause (WongosMysteryTicket.cs: owner check, `!(room is CombatRoom)`, GaveRelic, `5 …
- `relic/wongos_mystery_ticket/g1` — **live** — MECHANISM: both codebases special-case the last act's boss, but at different depths. The sim: `generate_combat_rewards` returns an empty CombatRewards at rewards.py (`if room_type == RoomType.BOSS and run.is_final_act: return …
- `relic/wongos_mystery_ticket/g7` — dormant — MECHANISM: C#'s `PullNextRelicFromFront` is `TestRngInjector.ConsumeRelicOverride ?? player.RelicGrabBag.PullFromFront(rarity, filter, runState) ?? FallbackRelic` (RelicFactory.cs), so all three RelicRewards always Populate to a …

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
| Porting **CeremonialBeast** onto `MachineMonster`, or the DecimillipedeSegment / TestSubject / WaterfallGiant stun callers | `monster_state_machine/G5`  |
| Wiring **`Inklet.cs:69`'s INIT_RAND**, or porting Inklet / PhrogParasite onto `MachineMonster` | `monster_state_machine/G2`  |
| A monster model needing a **forward state reference** (`FollowUpStateId` without `FollowUpState`) | `monster_state_machine/G3`  |
| A sim consumer that reads an **enemy intent mid-enemy-side** (per-enemy obs build, interruptible enemy phase) | `monster_state_machine/G9`  |
| Porting any `CardModel` with a **run-level hook** (`AfterRoomEntered`, `AfterRewardTaken`, `ShouldAddToDeck`) | `hook_dispatch/N5`, `creature_card_cmds/N3`  |
| A listener on a **guarded dispatcher** that mutates run-level state (HP, gold, deck); **the conformance exporter** | `hook_dispatch/G8`  |
| A listener that **removes another listener mid-dispatch** | `hook_dispatch/G7`  |
| A **card hook that reads state another card's hook writes** | `hook_dispatch/G1`  |
| A **non-dyadic block multiplier** (only `MultiplayerScalingModel.cs:52-68` exists, waived) | `hook_dispatch/G9` block site  |
| A **second implementer** of `ShouldForcePotionReward` / `ShouldAllowFreeTravel` | `hook_dispatch/step37`  |
| A **second corpse-heal**, or routing `ReattachPower` through the heal verb | `creature_card_cmds/G4`  |
| Any `AfterCurrentHpChanged` listener that **reads the amount** | `creature_card_cmds/G5`  |
| A model overriding **`BeforeBlockGained`** (zero overrides game-wide today) | `creature_card_cmds/step12`  |
| Porting a **multi-card transform** | `creature_card_cmds/step56`  |
| Porting a card that **plays more than one card from the draw pile** | `creature_card_cmds/step99`, `/N9`  |
| Two appliers of the same **`InstancedPerApplier`** power in one combat | `power_cmd/G5`  |
| A **third `modify_power_amount` listener**, or Unsettling Lamp / Ruined Helmet widening | `power_cmd/G3`  |
| An **`AfterCombatVictory`-only** listener with an unconditional effect; any `on_combat_end` effect that outlives the combat | `turn_structure/G10`  |
| The first **side-effecting** `should_reset_energy` or `modify_max_energy` | `turn_structure/step17`  |
| The first **`ShouldEtherealTrigger`** implementation on either side | `turn_structure/G15`  |
| Porting a `BeforeCardRemoved` listener, or adding a removed-from-state flag | `creature_card_cmds/step68`  |
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
| Any enemy-side `AfterSideTurnEnd` / `AfterSideTurnStart` power whose effect is order-sensitive | `turn_structure/G5` (8 power sites on top of the seam's 2) |
| **Training against the sim at all** — this one is not dormant, it is live in every run and dormant only against the game | `card/_printed_vars` (23 cards, via `sts2_rl/full_env.py:488`) |
| Writing the **potion** audit stream | everything in [What this queue does NOT cover](#what-this-queue-does-not-cover) — the last unaudited kind |
| Porting **Flyconid** onto `MachineMonster` (the codebase's preferred convention) | `monster_state_machine/G7` — entry 130; the port is faithful today and the machinery raises where C# limps |
| A **second Dampen applier**, or two Magi Knights in one encounter | entry 150 |
| Any **retained corpse** on the Glory enemy side (an Illusion / Reattach / Adaptable holder) | entry 147 |
| A **third Wither source**, or porting any other `AfterCardGeneratedForCombat` implementer | entry 148 |
| Giving `Intent` a **count field**, or any consumer that reads one | entry 146 |

---

# Behaviour in no tier's scope

Holes are queue items too. The six seam records cover engine *machinery* and the
five content tiers cover 680 units; these things are covered by nothing.

**One hole is still a whole kind:** `potion`, 0 of 51 — see
[What this queue does NOT cover](#what-this-queue-does-not-cover). `relic`
(merged 2026-07-26) and `monster` (2026-07-27) have closed. Everything below is
a hole *inside* the audited perimeter.

The rest of this section is as the seam tier recorded it. Recorded in
`audit/seams/monster_state_machine.md`'s scope-boundary section (it is the
last seam, so the holes are collected there) and reproduced here so the queue is
the single view.

1. ~~**Per-monster move content.**~~ **CLOSED 2026-07-27** by the monster tier:
   all 109 ported units have a record, and every move's damage numbers,
   transitions and branch arguments were compared node-by-node. The residual is
   the ~12 C# models with no sim port at all, which is unported content rather
   than an audit hole.
2. **`AbstractIntent` and the intent vocabulary.** `src/Core/MonsterMoves/Intents/`
   is unaudited: the sim collapses a C# `AbstractIntent[]` into one `Intent` with
   an `also` tuple (`monsters/base.py:36-59`) and nothing checks that mapping.
   `MonsterModel.IntendsToAttack` (`MonsterModel.cs:241-245`) reads the intent
   list and gates ported content, so a wrong mapping is a gameplay bug, not a
   display bug. **Still open, and now the best-evidenced hole in this list**:
   the monster tier filed four mechanisms against it without auditing the
   mapping itself — entries 75 (a dropped second intent, LIVE, read by
   `Intent.has()`), 145 (an empty intent array the sim cannot express) and 146
   (`StatusIntent`'s count). Of 45 moves one batch checked, 2 mismatched.
3. **`MonsterModel`'s non-machine surface** — `GenerateBestiaryMoveList`,
   `GetIntents`, `ResetStateMachine`, `CanonicalInstance`/`ToMutable`, HP
   generation and the Niche roll. Only `SetUpForCombat` / `OnSideSwitch` are
   claimed (by `turn_structure`). **HP generation and the Niche roll are
   RNG-consuming**, which puts part of this hole on the convergence path.
4. **`EncounterModel` / monster-slot generation.** Which monsters spawn, in what
   slots, with what HP roll, is claimed by no seam. `hook_dispatch` names
   `AfterCreatureAdded` and `monster_state_machine` names `SetUpForCombat`, but
   the *selection* is unaudited — also RNG-consuming. **The monster tier hit
   this hole from three sides and it is now the highest-value one left**:
   entry 65 (the per-encounter `Rng` does not exist in the sim, and Corpse Slug
   replays are not even self-reproducing), entry 68 (`AddCreature` re-sorts
   `Enemies` by slot and the sim appends) and entry 69 (egg slots fill
   backwards). None of the three is visible from a monster model alone.
5. ~~**Eleven C# monster models' `AbstractModel` hook overrides.**~~ **CLOSED
   2026-07-27.** The content-monster stream audited all 11 (the twelfth,
   `KinPriest`, was `monster_state_machine` guard N6). **Ten are `waiver`,
   presentation** — the N6 shape repeating: a music parameter, a barks line, a
   `Sprite2D.Texture` assignment or an animation call. **One is a LIVE gap**
   (`Queen.AfterDeath`, entry 67) and one is mechanical but dormant
   (`Aeonglass.AfterCardGeneratedForCombat`, entry 148). The table below is kept
   with each model's answer, because the *prior* is the durable finding: an
   override that looks mechanical usually is not, and only reading it to the end
   separates the ten from the two.

   **This hole's own framing was wrong, and that is worth keeping too.**
   `monster_state_machine.md:296-298` — reproduced in the table below until now
   — said `LagavulinMatriarch.AfterDamageReceived` "is the wake-from-damage path
   whose sim counterpart is `AsleepPower` → `wake_up(stunned=True)`". The
   override is **entirely presentation**: a `target != Creature` early return,
   `SleepingVfx?.Stop()`, two `eyes_open` Spine calls and `IsShellAwake = true`,
   a flag whose only three references in the whole game tree are its own
   declaration, read and write. The mechanical wake lives in
   `AsleepPower.cs:21-36`. No verdict rested on the sentence, so there is no
   rule-3 conflict — but it was the "look at this one first" recommendation.

   | model | overridden hook(s) | note |
   |---|---|---|
   | `Aeonglass.cs` | `AfterCardGeneratedForCombat`, `AfterDeath` | **AfterCardGeneratedForCombat is a dormant gap (entry 148)**; AfterDeath is a music parameter |
   | `Crusher.cs` | `AfterCurrentHpChanged`, `BeforeDeath` | waiver — arm hurt/death anims; differs from Rocket only in `ArmSide` and one FMOD value |
   | `DecimillipedeSegment.cs` | `AfterDeath` | waiver — one `Sprite2D.Texture` assignment. The *wither* behaviour is `ReattachPower`'s, and it is ported correctly |
   | `LagavulinMatriarch.cs` | `AfterDamageReceived`, `AfterDeath` | waiver, **both** — see the correction above; the wake is `AsleepPower.cs:21-36`, not this override |
   | `Queen.cs` | `AfterDeath` | **LIVE gap (entry 67)** — the only one of the eleven that is not presentation |
   | `Rocket.cs` | `AfterCurrentHpChanged`, `BeforeDeath` | waiver — Kaiser Crab's attack; read separately from Crusher per rule 29, and they do differ |
   | `SoulFysh.cs` | `AfterCardChangedPilesLate`, `AfterDeath` | waiver — the Hand scan's only consumer is `UpdateMusicParameter("beckon", …)`; its result is never stored. Still `creature_card_cmds/G8`'s trigger |
   | `TestSubject.cs` | `AfterDeath` | waiver — `SetColor` + a music parameter. **The trap**: the mechanical death behaviour is `AdaptablePower.AfterDeath`'s, entry 19 |
   | `TheInsatiable.cs` | `AfterDeath` | waiver — one music parameter |
   | `Vantom.cs` | `AfterDeath` | waiver — an identity guard plus one music parameter |
   | `WaterfallGiant.cs` | `AfterDeath` | waiver — a music parameter plus `SfxCmd.StopLoop`. Its *death* gap is entry 19's mechanism, via `SteamEruptionPower` |

   Most are in ported pools (`rooms.py:124-207`), which is why the ten
   waivers are waivers on their merits rather than on unreachability.

Two more holes this aggregation noticed, not recorded by any seam:

6. **No record owns the `combat_rng` stream map.** Four queue entries are
   "the sim draws from the wrong stream, or draws when the game does not"
   (#2, #24, #25, #27) and each was found incidentally by the seam that happened
   to touch the call site. Nothing audits the stream assignment as a subject.
   Given that stream desync is the highest-impact failure class in this queue,
   that is the largest structural hole here.
7. **Relic and card *content* has no seam.** `creature_card_cmds/G12` names two
   ported relics (Dragon Fruit, Lucky Fysh) whose sim implementations are inert
   stubs with docstrings that are no longer true. The seam records the missing
   hook; nothing owns the stubbed relic.

Three more holes this aggregation noticed, on top of the seam tier's two:

8. **The content tiers audit units, not the pools they are drawn from.** The
   card tier verdicts 202 cards; nothing verdicts `sts2_rl/cards/pool.py`'s
   composition, and `event/EV-6` shows the two are not separable — its finding is
   that the wrong *factory* was used, which is a pool-side fact recorded on a
   card-generating event because that is where somebody happened to look.
9. **No tier owns the `_init_vars` convention** that `card/_printed_vars`'s 23
   entries are all instances of. Each record states its own missing var; nothing
   states the rule, so the 24th card to be written can reintroduce it.
10. **`sts2_rl/full_env.py`'s observation encoder is audited by accident.**
    `card/_printed_vars` is dormant against the game and live against the encoder,
    and the card tier recorded that only because the encoder happens to read a
    field the tier was checking. Nothing systematically compares what the encoder
    reads against what the game would show.

---

## 3F. `potion` — dormant and single-site mechanisms  *(merged 2026-07-27)*

Twelve mechanisms. The first is a 51-site family; the rest are one unit each.
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

## 3G. Mechanisms this file had never named  *(added 2026-07-28)*

**`py audit/tools/gap_queue.py coverage` had been exiting 1 since the Tier 1
campaign, and nobody had run it.** The campaign's re-derivation split 25 entries
out of the families they used to be grouped under — a verdict flip on a
neighbouring entry changes which regex family the remainder matches, so a
mechanism key can appear that no prose in this file mentions. `coverage` is the
check that catches exactly that, and the campaign's own definition-of-done listed
it; `cite-check` was run and `coverage` was not.

They are one entry each and none is a new finding — each is a site of a mechanism
already described above, re-keyed to its own id. Naming them here is what makes
`coverage` exit 0 again; the fix for each is its parent mechanism's.

| mechanism | liveness | parent family |
|---|---|---|
| `creature_card_cmds/step105` | unlabelled | CardSelectCmd (§2G) |
| `hook_dispatch/step6` | unlabelled | listener-registry shape (§2D) |
| `hook_dispatch/step29` | unlabelled | phase passes (§21) |
| `monster/fabricator/g5` | **live** | monster off-stream draw (§66) |
| `monster/test_subject/g2` | **live** | death prevention (§19) |
| `power/calamity/AfterCardPlayed` | unlabelled | per-CardPlay bracket (§16) |
| `power/constrict/AfterSideTurnEnd` | dormant | side-turn slot (§17) |
| `power/illusion/AfterDeath` | unlabelled | death prevention (§19) |
| `power/illusion/ShouldCreatureBeRemovedFromCombatAfterDeath` | unlabelled | death prevention (§19) |
| `power/nostalgia/g4` | **live** | single-unit power finding (§3A) |
| `power/painful_stabs/g1` | dormant | single-unit power finding (§3A) |
| `power/ritual/AfterSideTurnEnd` | unlabelled | side-turn slot (§17) |
| `power/skittish/AfterSideTurnEnd` | unlabelled | side-turn slot (§17) |
| `power/tender/AfterSideTurnEnd` | dormant | side-turn slot (§17) |
| `power/unmovable/ModifyBlockMultiplicative` | unlabelled | block props hoist (§58) |
| `relic/fragrant_mushroom/AfterObtained` | dormant | StableShuffle (§52) |
| `relic/intimidating_helmet/g2` | **live** | single-unit relic finding (§3E) |
| `relic/iron_club/AfterCardPlayed` | unlabelled | per-CardPlay bracket (§16) |
| `relic/kusarigama/AfterCardPlayed` | unlabelled | per-CardPlay bracket (§16) |
| `relic/letter_opener/AfterCardPlayed` | unlabelled | per-CardPlay bracket (§16) |
| `relic/prayer_wheel/TryModifyRewards` | unlabelled | reward late pass (§49) |
| `relic/stone_cracker/AfterRoomEntered` | unlabelled | StableShuffle (§52) |
| `relic/white_star/g1` | **live** | `relic/_stub` (§48) |
| `turn_structure/step26` | unlabelled | turn structure remainder (§2I) |
| `turn_structure/step47` | unlabelled | turn structure remainder (§2I) |

**Run `coverage` as well as `cite-check` after any regeneration.** Both exit
non-zero on failure as of 2026-07-27; only one of them was being run.

---

# Record inconsistencies found while aggregating

Rule 3 signals: a gap whose text contradicts another record's, or its own. This
class has already caught real bugs on this project, so they are reported here,
and historically were reported rather than fixed. **Re-read a record before
acting on a row here** — some rows are now stale in the good direction.

Items 1–7 are the seam tier's, found when this queue covered 6 records. Items
8–14 were found aggregating the four content tiers on top of them — and **five
of the seven are the content tier contradicting a seam verdict**, which is the
cross-tier check working exactly as rule 3 intends. Items 15–18 came with the
monster tier and keep the pattern: three of the four are a content tier
contradicting a seam or power verdict.

**2026-07-26, the relic tier merge:** this section's own thesis got its
strongest test yet, and it held. The relic tier's rule-3 review censused 27
shared mechanisms, fully resolved 12, and found **5 contradictions — of which 2
resolved to "neither record was right"**. Item 1 is now fixed. The two
"neither was right" cases are entries 58 and 33's mechanism (the props hoist:
one record misread the C# guard while the other's census of affected listeners
was incomplete) and the damage-side twin at `relic/fake_strike_dummy` vs
`relic/strike_dummy`. Both had the same shape — *an incomplete census on the
`gap` side meeting a misread guard on the `faithful` side* — and in one of them
the census that would have settled it **already existed as a probe nobody ran**.
The structural lesson, worth more than the individual fixes: every contradiction
found lived at a **shared engine gate** (a props filter, a phase pass, a
dispatcher hoist), never at a unit's own arithmetic. Per-unit records are
reliable about their own numbers and unreliable about whether the shared
machinery beneath them changes the answer, because each unit re-derives that
machinery's reachability from its own vantage point.

1. ~~**Two stale sim citations, caught mechanically.**~~ **FIXED 2026-07-26 by
   the relic tier merge.** `hook_dispatch`'s G2 evidence gave the Spiked
   Gauntlets method an end line one past the end of the file, and
   `creature_card_cmds`' G9 and step 84 did the same to Fiddle — both one-line
   overruns, harmless to a reader and fatal to a `sed -n`. (The broken ranges
   are deliberately not reproduced here; they no longer exist in any record, and
   quoting them would be the only thing in this file that `cite-check` had to be
   told to ignore.) The relic stream corrected both at source — it was auditing
   those two relics and read the real line ranges — and the corrections came in
   with the merge alongside 8 more of the same kind. `gap_queue.py`'s
   `_KNOWN_BAD_CITATIONS` allowlist, which existed only so `cite-check` would
   not fail on this queue *quoting* the two broken citations, is now empty.

   Worth keeping as the worked example it is: the defect was found
   mechanically, and it was **fixed by a different tier auditing a different
   kind** — nobody went looking for it. That is the argument for widening the
   citation sweep rather than for hand-checking seams.

2. **`hook_dispatch`/G7's executed evidence is from a stale tree.** It records
   the stale-listener plugin run as "the whole suite (2476 passed / 30 xfailed)
   and 191,270 instrumented listener calls". The suite is **2478 passed / 38
   xfailed** today. The conclusion may well still hold — the record says the run
   is reproducible from the committed tree — but the number in the record was
   taken before 8 more xfails and 2 more tests existed, so **re-run it before
   relying on the "only one hit" claim**.

3. **One RE-AUDIT paragraph pasted onto four entries, one of which it does not
   describe.** `damage_pipeline` steps 5, 9, 12 and guard G2 carry a
   byte-identical "RE-AUDIT 2026-07-25 … PARTIALLY RESOLVED" block whose subject
   is the **HpLost** variant. Step 5 is `AfterModifyingDamageAmount` — a
   different variant, and one the same paragraph later lists among the 12 that
   "remain absent". A fixer reading step 5 alone would conclude the damage-amount
   variant is partially resolved when nothing about it changed. The G2 rollup is
   the entry to trust.

4. **One entry, two clauses, two liveness values.** `creature_card_cmds`' step 13
   opens "See guard **G1 (LIVE)**" and its clause (c) is `hook_dispatch`'s G9,
   which that record explicitly marks **DORMANT at this site** ("AMENDED (fix
   pass 2): it carries the identical gap, but is DORMANT there"). Any tool — or
   reader — that takes an entry's first liveness token as the entry's liveness
   mis-files it. This queue files it under `damage_pipeline/G3` (live) and lists
   it as a co-site of `hook_dispatch/G9`.

5. **12 vs 11 monster models.** `hook_dispatch`'s step 3 states "exactly 12
   monster models override a hook"; `monster_state_machine`'s boundary section
   heads its table "**Eleven** C# monster models' `AbstractModel` hook
   overrides". Both are right — 12 total, minus `KinPriest`, adjudicated as a
   waiver — but the subtraction is invisible from the JSON records alone and the
   probe prints 12. Anyone quoting a number here should quote the probe.

6. **Gap-id collisions across records, unflagged by the records themselves.**
   `G8` is the missing `IsEnding` gate in `hook_dispatch` and the missing
   AutoPrePlay/AutoPostPlay phases in `turn_structure`; `G2`, `G3`, `G4`, `G9`
   and `N5` each mean two different things in two records. The records
   cross-reference by bare id in several places ("carries G8's precedence",
   "see guard N3"), which is only unambiguous because those references happen to
   be within-record. This is a latent mis-merge waiting for the next reader.

7. **Self-corrections the records themselves record** — not outstanding
   contradictions, but they establish that first-pass verdicts on this project
   are not reliable without re-execution:
   - `monster_state_machine` step 13: "A first pass stated '13 resolved / 8
     match', having read the branch-state count as the pair count."
   - `monster_state_machine` G2: the first pass's gap ids and step list
     disagreed — "a recount found 8 distinct gap ids across the steps against 9
     in the doc."
   - `monster_state_machine` step 22: corrected from `deliberate-divergence`
     whose rationale "cannot both hold".
   - `monster_state_machine` step 35: the inherited **seed fact** "the sim uses
     the shared combat stream" is **stale** for the machine itself.
   - `creature_card_cmds` G14: the first pass verdicted one mechanism three
     different ways — gap at steps 11/71/72, deliberate-divergence at 74/83/90,
     faithful at 48/54/103.
   - `turn_structure` G13: the inherited doc's dormancy claim is called "FALSE";
     G11's inherited content list "was WRONG"; G12's "no ported pair contends for
     the same event today" is "WRONG"; G4 is live "NOT for the reason the
     inherited doc gave".
   - `power_cmd` step 20: the previous rationale was "factually wrong".
   - `monster_state_machine` G6: the first pass's **LIVE** label was refuted by
     its own pin XPASSing.

8. **A dormant seam gap and a live content gap for one mechanism.**
   `damage_pipeline`'s **G1** (Thorns on the wrong hook) labels itself
   **dormant**. `power/thorns`' `BeforeDamageReceived` entry labels the same
   mechanism **"LIVE, twice over"** and backs it with two executed witnesses (0
   vs 5 HP on a killing blow; 5 vs 0 on unpowered non-card damage). Both records
   are internally consistent; only one can be right about today, and the power
   record has the execution. This queue files the mechanism as LIVE and pinned.

9. **A "no concrete broken interaction is demonstrated" that is now
   demonstrated.** `power_cmd`'s **G6** says the missing `CanReceivePowers`
   backstop in `PowerCmd.apply` has no demonstrated break, "spot-checked callers
   apply powers only to already-resolved targets". `power/adaptable`,
   `power/illusion` and `power/reattach` each execute one: Vulnerable 2 lands on
   a reviving Test Subject in the sim and is refused in the game. The G6 entry
   also mixes two clauses (the `IsEnding` gate and this one) under one verdict,
   so the falsification does not show up against the mechanism this queue files
   G6 under (`hook_dispatch/G8`).

10. **A seam step cited against the wrong record.** `event/dense_vegetation`'s
    `BR-38a` cites "`audit/records/seam/turn_structure.json` step 38a". Step 38a
    is in `creature_card_cmds.json`; `turn_structure`'s step 38 is
    `EndOfTurnCleanup`, an unrelated gap. The mechanism the text describes is
    unambiguous, so this queue merges it to the real home — but a reader
    following the citation lands on the wrong finding.

11. **A seam witness the content tier corrects.**
    `creature_card_cmds` step 52's stated out-of-combat downgrade leg does not
    reach the player: `enchantment/goopy`'s `BR-3` executes it and finds the only
    ported out-of-combat downgrade (the Reflections event) self-heals before the
    card is played again, while the in-combat leg (Dampen) does bite. The
    finding stands; the witness in the seam record does not.

12. **A content record correcting its own tier's earlier claim.**
    `event/morphic_grove`'s `EV-10` states that `event/trial` called this "the
    sharpest case" on a claim — that a Quest card can make the sim offer a map
    node the game would not — that **"was never true"**, and executes both gates
    agreeing. The *selection* half of EV-10 is live and unaffected. Two records
    in one tier, one superseded sentence.

13. **A `gap` entry that says it is not a divergence.** `power/flame_barrier`'s
    guard 5 is verdicted `gap` **"only to carry that cross-reference at the same
    precedence as the thorns finding it explains; nothing in THIS unit's
    behaviour diverges on the killing blow."** Under the rollup rule that makes
    `flame_barrier`'s whole record a `gap` record, and it adds an entry to every
    count in this file. The cross-reference is genuinely useful; the verdict is
    the wrong instrument for it, and there is no vocabulary term that fits.

14. **386 of 1460 gap entries state no liveness at all** — `seam` 104, `relic` 161, `power` 85,
    `enchantment` 19, `event` 16, `card` 1, `monster` **0**. The README already
    flags this for the power tier ("64 of the 258 power gap entries carried
    neither a LIVE nor a dormant token"); across the six kinds it is 26% of the
    queue. Those entries inherit their mechanism's liveness here, which is a
    guess wherever the mechanism is a singleton — most are. The `live` boolean
    the record schema allows is the fix.

    **PARTLY RESOLVED 2026-07-27.** The sentence that used to close this item —
    "it is not yet populated on a single record … every liveness in this queue is
    derived from prose" — is no longer true. The monster tier populates `live` on
    **all 45** of its gap entries, which is why it contributes 0 to the 386, and
    `gap_queue.py` now reads the field **in preference to** its prose scan
    (`_make_entry`'s `live` parameter). The prose scan remains for the other 386.
    The demonstration matters beyond the count: the scan is a heuristic over caps
    tokens near the head of an issue, and it cannot distinguish an entry that says
    "DORMANT" about itself from one that says it about the thing it cites.

## 2026-07-27, the monster tier merge — four more, and one of them is this section's own thesis again

15. **`power/sandpit`'s "Frantic Escape as the counterplay" guard is `faithful`
    and cleared a live gap.** It compared the card counts and the pile types and
    **not** `CardPilePosition`, which `CardPileCmd.cs:512-514` resolves to an
    `Rng.Shuffle.NextInt` draw for *every* pile type. The Insatiable's three
    discard-side Frantic Escapes therefore take 3 draws where the game takes 6,
    and land in a fixed order. Now entry 71. Reported, not edited.

16. **`power/withering_presence` cites a hover-tip property as the mechanism.**
    It names `WitheringPresencePower.cs:37` as where generated Withers are
    matched; that line is inside `ExtraHoverTips`, a preview. The real matching
    is `Aeonglass.AfterCardGeneratedForCombat` (entry 148). This is PROMPT.md
    class 20 — *read the enclosing member, not the line* — applied to a
    property, and it is the second time in this queue that a citation which
    looks verified protected a wrong claim.

17. **`monster_state_machine` G7b's dormancy argument does not cover its own
    reachable case.** G7b (entry 130) is "when every branch weighs 0, C# burns a
    draw and returns branch 0; the sim raises before drawing", labelled dormant
    on a fuzz of **82 machines**. Flyconid's `RAND` reaches an all-zero weight
    vector on ported act-1 content, hit on **all five** probe seeds at turns
    3–23 — and Flyconid is **hand-rolled**, so a fuzz that enumerates machines
    could never see it. The port is faithful (it burns the draw and returns
    branch 0, exactly as C# does); the *sim machinery* is what raises. The
    practical consequence is a trap for the next person: **porting Flyconid onto
    `MachineMonster`, which is the convention this codebase prefers, would crash
    the run.** Reported, not edited — the seam record's verdict is unchanged,
    only its coverage claim is.

18. **`monster_state_machine.md:296-298` misdescribes
    `LagavulinMatriarch.AfterDamageReceived`.** It calls it "the wake-from-damage
    path"; the override is entirely presentation and the wake is
    `AsleepPower.cs:21-36`. No verdict rested on it — it is a boundary-hole
    hand-off, not a finding — but it was reproduced in this queue as the
    "look at this one first" recommendation for the 11 unclaimed overrides, and
    it is now corrected in place.

## 2026-07-27, the potion tier merge — the scope-decision failure, one merge later

19. **Four relic records still assert the deleted potion clause as a live
    premise.** `relic/alchemical_coffer`, `relic/lost_coffer`,
    `relic/phial_holster` and `relic/potion_belt` each carry, verbatim:
    "SCOPE RULING (2026-07-26 relic fix pass, applied at every potion site in
    this tier). The shared contract's 'Out of scope everywhere: potions
    (deferred by Perry)' means **POTION IS NOT AN AUDITED KIND — there is no
    `potion` roster kind and no `audit/records/potion/`.**"
    Both halves are false: `audit/tools/harness.py:61` created the roster kind
    on 2026-07-26 and `audit/records/potion/` holds 51 records. Three of the four
    entries are `gap`/`live: true` and one (`phial_holster`) is a `faithful`
    resting on it. **This is section
    [1D](#1d-potion-scope--live-gaps-unmasked-by-deleting-the-exclusion-2026-07-26)'s
    own thesis recurring one merge later** — a dormancy claim that describes a
    *scope decision* rather than a fact about today's content. Reported to the
    relic stream, not edited. Distinguish these from the ten records
    (`card/alchemize`, `power/{buffer,clarity,demise,flex_potion,gigantification,radiance,regen,shackling_potion,speed_potion}`)
    that quote the clause as explicit "RE-VERDICTED … has been DELETED" history:
    that is correct and should stay.

20. **28 `extra_sources` hashes should never have been written, in 27 records
    owned by three other streams.** `citation_check.py` declares
    `_NEVER_HASHED = ("audit/tools/", "test/")` — the pipeline's own machinery
    and its pins are cited but not hashed, because "a broken pin fails loudly on
    its own" — and `backfill_sources.py` had no such exclusion, so it pinned
    them. The consequence is false staleness: a record hashing
    `test/test_hook_order.py` goes stale whenever **any** pin is added anywhere
    in that file, and one hashing `audit/tools/relic_probes.py` goes stale when a
    probe is edited. Appending the four potion pins staled nine records whose own
    cited lines had not moved by a byte. The tool is fixed; the data is a
    hand-off, by owning stream:

    | stream | records | pinned path |
    |---|---|---|
    | `card` (18) | `anointed`, `beat_down`, `discovery`, `distraction`, `havoc`, `hidden_gem`, `jack_of_all_trades`, `jackpot`, `metamorphosis`, `rip_and_tear`, `seeker_strike`, `splash`, `volley` | `test/test_rng_tripwire.py` |
    | | `feel_no_pain`, `mad_science` | `test/test_shared_enchantments.py` |
    | | `feel_no_pain` | `test/test_ironclad_cards.py` |
    | | `apotheosis`, `entrench`, `primal_force` | `test/test_hook_order.py` — **stale** |
    | `relic` (8) | `mystic_lighter`, `permafrost` | `audit/tools/relic_probes.py` |
    | | `horn_cleat`, `intimidating_helmet`, `iron_club`, `joss_paper`, `orichalcum`, `pen_nib` | `test/test_hook_order.py` — **stale** |
    | `power` (1) | `surrounded` | `test/test_hive.py` |

    Each stream applies
    `py audit/tools/backfill_sources.py --prune --no-add --kind <kind>`.
    **The nine marked stale above are already re-audited and re-pinned** (they
    went stale when the potion pins were appended, so clearing them was the
    potion stream's to finish). The re-audit is
    `py audit/tools/potion_probes.py pin-append`, and it is three checks rather
    than a hash rewrite: the pin file changed by **append only**; none of the 72
    line citations across those records moved or changed content; and every test
    those records name still exists and is still a `strict=True` xfail. Only
    then `harness.py rehash`, which re-pinned exactly one `extra_sources` entry
    per record and nothing else. The prune is still owed for all 27 — it is the
    durable fix, because a re-pin only buys time until the next pin is added.

21. **A pin was credited to the wrong mechanism, and the queue reported coverage
    in two places at once.** See entry 25's **pin** row: a two-headed seam guard
    (`power_cmd/G6`, "No `CombatManager.IsEnding` / `CanReceivePowers` guard
    backstop") is merged into the `IsEnding` family, so a pin citing it for its
    *other* head landed on a dormant 22-site mechanism while the LIVE 8-site one
    it proves read `unpinned`. The general lesson for rule-3 cross-references:
    **when you match a seam guard, name the head you are matching**, and check
    whether the queue already owns that head separately — it did.

**And once more, two records disagreeing about one mechanism meant neither was
right.** `ShouldDisappearFromDoom` (nine C# monster models) drew a dormant `gap`
from one batch and `faithful` from another. Adjudicated: there **is** exactly one
reader in the game tree, `DoomPower.cs:90`, so "no reader anywhere" is false —
but it sits inside `PlayVfx`, feeds only `StartDoomAnim` and a `Cmd.Wait` timing
branch, and `DoomKill`'s `CreatureCmd.Kill` is unconditional and outside it, so
"it gates whether the creature is removed" is false too. Settled as `waiver`,
presentation, at all nine sites, which **removed two false dormant gaps from this
queue before it was regenerated**. Both wrong answers came from counting grep
matches instead of resolving the one hit to its enclosing member. That is the
fourth time on this project, and the second inside the content tiers.

---

# Appendix — regenerating this file

```
py audit/tools/gap_queue.py counts        # the summary tables
py audit/tools/gap_queue.py mechanisms    # every mechanism with its sites and pin
py audit/tools/gap_queue.py list          # every gap entry, one line
py audit/tools/gap_queue.py pins          # the 32 strict xfails
py audit/tools/gap_queue.py unpinned      # the unpinned mechanisms
py audit/tools/gap_queue.py refs          # the raw cross-references in gap text
py audit/tools/gap_queue.py json          # the structured dump behind all of it
py audit/tools/gap_queue.py coverage      # every mechanism and entry appears here
py audit/tools/gap_queue.py cite-check    # every file:line here resolves
py audit/tools/harness.py validate        # every record, 0 invalid
```

`coverage` and `cite-check` are the two that fail loudly if this file drifts from
the records. `coverage` asserts that **every mechanism key and every one of the
1460 entries is locatable here** — a seam entry by its own id or its mechanism
plus its local id, a content entry by its mechanism, since 1460 ids cannot each
be spelled out in prose and `mechanisms` regenerates any group's site list on
demand. `cite-check` asserts that every `file:line` in the authored prose
resolves in `sts2_rl/` or in the decompiled game tree; Tier 3's summaries have
their line numbers stripped precisely so that check stays a check on this
document rather than a re-validation of 789 record excerpts.

**How the grouping is derived, and where to argue with it.** Every merge is
declared in `audit/tools/gap_queue.py` and carries the record text that asserts
it:

| table | what it merges | example |
|---|---|---|
| `_CROSS_RECORD` | mechanism keys two records declare to be one mechanism | `enchantment/BR-1` → `damage_pipeline/N3` → `hook_dispatch/G9` |
| `_TAG_MECHANISM` | a tier's `BR-` tag to the seam mechanism it cross-references | `event/BR-G3` → `creature_card_cmds/G3` |
| `_FAMILY_OVERRIDE` | one content entry the regex table would misfile | `power/thorns/BeforeDamageReceived` → `damage_pipeline/G1` |
| `_FAMILIES` | the recurring families in the untagged `power` and `card` tiers | body opening `SLOT` + `per-creature` → `turn_structure/G5` |

An over-split queue overstates the work; an over-merged one hides a job. The
tables lean split: anything a record does not explicitly tie to another
mechanism anchors its own, which is why most mechanisms are single-site and land
in Tier 3. **The monster tier's own additions are a worked example of the two
failure directions**: the first run over-merged four of its mechanisms (a
corpse-scan consequence swallowed by the death-prevention family; a
`CanReceivePowers` site swallowed by the same; the `step8b` family swallowing
the death gap that merely *mentions* the power strip) and under-merged two
others (a title-matched family written as a body match, so it matched nothing).
Both were found by reading the generated grouping against the records, which is
the only check there is on a `_FAMILIES` regex — ordering matters, and the
narrow mechanisms have to precede the broad one.

Both checks were run clean at the commit that added this line, together with
`py -m pytest test/ -q` — unchanged from the branch baseline, because this
stream adds no test code and no engine code.
