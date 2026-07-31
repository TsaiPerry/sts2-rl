# Gap queue — every audited record, aggregated

Every `"verdict": "gap"` entry from `audit/records/**`, de-duplicated **by
mechanism**, ordered for work, and left **queued, not fixed** unless a campaign
is explicitly working it. Generated, not transcribed.

**Do not trust a count stated in prose anywhere in this project, including this
file. Re-run `py audit/tools/gap_queue.py counts`.**

## Status

`counts` reports **28 entries labelled LIVE**, spread over **22 mechanisms**,
and **0 unlabelled**. The last of those three is the new thing: for ten rounds
this file had a third pile it could not describe.

| liveness | entries | what it means |
|---|---|---|
| **labelled LIVE** | **28** | reachable on today's ported content, each with an executed witness |
| labelled DORMANT | 530 | a real divergence, shown unreachable by an **enumeration** |
| unlabelled | **0** | closed 2026-07-29 (round 11) |

Round 11 settled every one of the 212 entries that stated neither, by execution,
in 17 concurrent batches. **88 of them were stale** — the verdict flipped
`gap` → `faithful` / `waiver` / `deliberate-divergence` and the entry left the
queue outright. The rest were typed: `"live": false` with an enumeration, or
`"live": true` with a divergence, an observable, a trigger, a fix and a radius.

| | before round 11 | now |
|---|---|---|
| gap entries | 646 | **558** |
| — labelled LIVE | 0 | **28** |
| — labelled DORMANT | 434 | 530 |
| — unlabelled | **212** | **0** |
| distinct mechanisms | 484 | **404** |
| — with a live entry | 0 | **22** |

**The dormant column now means something stronger than it did.** Every label
this round rests on an enumeration that was *run* — "these are all N overrides
of this hook in `src/`, and none of them is ported" — rather than on an argument
that nothing reaches the site. That is the difference this round was for. It
does not retroactively upgrade the dormant labels that predate it: those still
have to be re-derived one at a time, and the eight rounds before this one say
roughly one in four of them will turn out to be stale.

### Where to start

1. **[Tier 1](#tier-1--the-live-gaps) — the 28 live entries.** All 22
   mechanisms are written out there, with what makes each one live.
   `py audit/tools/gap_queue.py list` prints the liveness of every entry;
   `mechanisms` groups them. Six of the 28 entries are a single mechanism
   (`power_cmd/G5`); most of the rest are one entry each, so the tier is wide
   and shallow rather than deep.
2. **[Tier 2](#tier-2--dormant-gaps)** — 530 dormant entries, widest families
   first.
3. **[Tier 3](#tier-3--the-long-tail)** — one row per remaining mechanism.

### Named work with no entry of its own

- **`Hook.AfterModifyingCardPlayCount` has no sim counterpart at any site.**
  `hooks.py:593`'s `modify_card_play_count` is the decision hook only; there is
  no `after_modifying_card_play_count` anywhere in `sts2_rl/`. It is one of
  `damage_pipeline/G2`'s twelve absent `AfterModifying*` variants and carries no
  entry of its own.
- **`card/spoils_map` vs `Hook.ModifyGeneratedMapLate`.** The sim dispatches a
  Late map pass (`run.py:1150`) whose only game caller is the save-load branch
  (`RunManager.cs:740`), because Spoils Map folds its Treasure-coord recording
  into it. Documented at the dispatch site; no entry.
- **`card/sweep` has no audit record.** It is sim-only — there is no
  `audit/records/card/sweep.json` and no `Sweep.cs`.
- **`creature_card_cmds/G8` is narrowed, not closed, and it is now four open
  sites rather than three.** `Hook.AfterCardChangedPiles` exists
  (`hooks.py:880-906`) and is dispatched at one of C#'s four sites, the
  combat-pile transform. Still silent: `/step81` (Add), `/step69`
  (RemoveFromCombat), `/step89` (the draw path, `player.py:440-459`, a direct
  `pop`/`append` that never enters `CardPileCmd`) and `/step96` (the reshuffle,
  `player.py:341-397`). Deliberately left: `/step89` is the sim's hottest loop
  and every ported listener filters to the Deck pile.

**No longer a blocker: `power_cmd/G2`.** It was listed here as gating
`power_cmd/G4` and the ten `AfterModifying*` variants under
`damage_pipeline/G2`. Round 11 settled it **dormant** by enumeration:
`AfterModifyingPowerAmountGiven` has exactly **one** C# override,
`SneckoSkull.cs:32-36`, which is presentation-only and unported;
`AfterModifyingPowerAmountReceived` has **two**, and both are already reproduced
inline in the sim (`cmds.py:301-305` for Artifact, `relics/ruined_helmet.py:37`
for Ruined Helmet). Nothing is waiting on it.

### How this queue has been wrong before

Eleven rounds of fix campaigns have produced the same failure modes over and
over. They are worth more than any single entry below.

- **Staleness is the largest category, nine rounds running.** Roughly one entry
  in four turns out to be already fixed; round 11 ran 88 stale out of 212.
  **Start every unit by re-executing the entry's own witness**, not by reading
  its prose. An entry is only as current as the last change to the code it was
  written against.
- **Record decay has six distinct forms, and unit work found all six — review
  found none.** A *stale premise* (the code moved). A *rationale describing the
  wrong hook's bug* (`power/smoggy/AfterCardEnteredCombat` was filed with
  `AfterCardPlayed`'s pile-limbo theory, which could not support a gap on its
  own key). A *dangling mechanism id* (`hook_dispatch G9` is cited across this
  file and no longer exists under that name). An **un-regenerated `hooks`-level
  rollup** summarising guards that had since closed — **the single largest
  category**: one batch ran 9 of its 12 units on it and four batches were
  dominated by it. An **un-regenerated record-level `verdict` field**, still
  `gap` after every guard beneath it closed. And **stale guidance in
  `audit/tools/PROMPT.md` itself** — its v6 `undo_after_obtained` claim was
  false against code fixed three days before it was quoted into a batch brief.
  Corrected in PROMPT.md now.
- **A dormancy label can silently go LIVE, and nobody checks that direction.**
  `relic/kifuda`'s G2 was dormant on a stated precondition — "it stays dormant
  until G1 is fixed: with the relic implementing nothing, there is no screen to
  get wrong". G1 was fixed in round 7. The precondition was discharged, the
  entry was re-executed against the real implementation, and it is **live**.
  Every other finding this round ran the other way (gap → faithful), which is
  exactly why this one nearly went unnoticed. **A dormancy argument with a
  named precondition is a dated cheque: re-read it whenever its precondition
  might have been paid.**
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
- **Tooling defects are found by unit work, never by tool review.** Six rounds
  running. If a probe disagrees with an execution, suspect the probe. Round 11's
  two:
  - **`gap_queue.extract()` ignored typed data for two days.** It passed
    `e.get("live")` on the content branch and omitted it on the seam branch, so
    21 correctly-settled seam entries kept reporting `unlabelled` after their
    records had been written, validated and merged. Two batches settled them,
    `counts` did not move, and the records were right while the tool everyone
    downstream reads was wrong. Fixed, and pinned by
    `test/test_audit_status.py::TestTypedLivenessIsHonouredEverywhere`, which is
    negative-controlled — it fails with the fix reverted.
  - **`_liveness`'s prose scan is first-token-wins with no negation handling.**
    It labels an entry by whichever of the tokens LIVE / DORMANT appears first,
    so a sentence like "DORMANT is the wrong label here … so: LIVE" reads as
    dormant. A sweep found **47 entries carrying both tokens**, of which **45
    were labelled by token position alone**; exactly one had a detectable
    negation cue, and that one is fixed. **The other 44 are unaudited, not
    confirmed.** The typed `live` key is the real remedy and is now present on
    every gap entry, which is what makes the prose scan a fallback rather than
    the answer.

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
| enchantment | 19 | 19 | the first kind with **zero** gap entries |
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
  means editing both. The same shape recurred in round 11 one level down, in
  `extract()`'s per-branch handling of the typed `live` key — see above.

## Summary

| | |
|---|---|
| gap entries across all 848 records | **558** |
| — labelled LIVE | **28** |
| — labelled DORMANT | 530 |
| — unlabelled | **0** |
| entries sitting in a mechanism that has a live site | 43 |
| **distinct mechanisms** | **404** |
| — with at least one live entry | **22** |
| mechanisms pinned by a `strict=True` xfail | **0** |

Per kind (records / gap entries / mechanisms anchored there / live entries):

| kind | records | entries | mechanisms | live |
|---|---|---|---|---|
| `seam` | 6 | 91 | 59 | 4 |
| `power` | 138 | 144 | 113 | 17 |
| `card` | 202 | 97 | 43 | **0** |
| `event` | 65 | 12 | 12 | 3 |
| `enchantment` | 19 | **0** | **0** | 0 |
| `relic` | 258 | 170 | 157 | 4 |
| `monster` | 109 | 18 | 6 | **0** |
| `potion` | 51 | 26 | 14 | **0** |

Per seam record (entries / mechanisms anchored there / live entries):

| record | entries | mechanisms | live |
|---|---|---|---|
| `damage_pipeline` | 7 | 6 | 2 |
| `power_cmd` | 16 | 8 | 2 |
| `creature_card_cmds` | 41 | 25 | 0 |
| `turn_structure` | 8 | 8 | 0 |
| `hook_dispatch` | 15 | 9 | 0 |
| `monster_state_machine` | 4 | 3 | 0 |

Three kinds have **no live entry at all** — `card`, `monster` and `potion` —
and that is a claim about their records, not a compliment: the card tier's 97
entries are 43 mechanisms of which the two largest (`card/_unplayable_cost`,
`card/_printed_vars`) are value-model divergences the game cannot see, and the
monster and potion tiers were the two most recently written, so their dormancy
enumerations are also the youngest and least re-checked.

**The xfail count is 0.** That is not "no gaps left" — it is "every mechanism
that had an acceptance test now passes it". All 404 mechanisms are unpinned,
including all 22 live ones, which is the coverage problem `audit/README.md` has
flagged since the seam tier: **a gap with no pin cannot prove its own fix.**
Adding a pin as a gap is worked remains the cheapest way to stop that rotting,
and Tier 1 is now the obvious place to start doing it.

---

## How to read an entry

```

### <mechanism id>  — <one-line name>                     [LIVE|DORMANT] [pinned|unpinned]
sites      every gap entry that is this same mechanism (the stable ids)
impact     A / B / C — see Ordering
divergence one sentence, sim file:line vs C# file:line
observable what a player or a replay sees; executed numbers where the record has them
trigger    (live) the ported content that reaches it; (dormant) the unported thing that would
pin        the strict xfail in test/test_hook_order.py that flips to passing, or why not
fix        which sim file changes and roughly how; what the failing test asserts
radius     other mechanisms sharing machinery; content units the record names
```

**Stable ids.** A seam entry is `<seam>/<step-or-guard-id>` —
`power_cmd/G5`, `creature_card_cmds/G14`. A content entry is
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

**A mechanism id can go away, and the prose citing it does not.**
`hook_dispatch/G9` is cited by several entries below as a shared blast radius;
it is no longer a mechanism in `counts`, because every entry that anchored it
closed. Treat a seam id you cannot find in
`py audit/tools/gap_queue.py mechanisms` as history, not as a live dependency.

**Watch the id collisions.** `G8` is the missing `IsEnding` gate in
`hook_dispatch` but the missing AutoPrePlay/AutoPostPlay phases in
`turn_structure`; `G2`, `G3`, `G4`, `G5`, `G7` and `N5` all mean different
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

Sorted by **liveness** first, then by seed-convergence impact, then blast
radius, then fix cost. Convergence impact is graded:

- **A — stream desync.** Changes an RNG draw count or the stream a draw comes
  from. Every later draw in the run shifts; a replay stops converging outright.
- **B — state divergence.** Changes a damage/block/HP number, a hand, a pile or
  a deck entry. The next conformance assert fires.
- **C — bookkeeping only.** Hook order or event identity with no numeric effect
  on currently-ported content.

The document has three tiers:

1. **[Tier 1 — the live gaps](#tier-1--the-live-gaps)**, written out in full.
   All 22 mechanisms that carry a live entry, in impact order.
2. **[Tier 2 — dormant gaps](#tier-2--dormant-gaps)**, written out in full,
   grouped by the machinery they share, widest families first.
3. **[Tier 3 — the long tail](#tier-3--the-long-tail)**, one row per remaining
   mechanism. Single-site, single-unit findings: real, recorded, verified, and
   cheaper to read straight out of the record than to restate. The row gives the
   id, the liveness and the record's own lead clause.

`py audit/tools/gap_queue.py coverage` asserts that every mechanism and every
one of the 558 entries is locatable here, so the tail cannot silently shrink.

---

# Tier 1 — the live gaps

**22 mechanisms, 28 entries, every one reachable on content that is ported
today.** This is the whole of what round 11 could demonstrate; it is not the
whole of what is broken, because 530 dormant entries sit behind it and a
dormancy label is only as good as the enumeration under it.

Each mechanism below carries the executed witness from its record. Where a
record ran a probe, the probe path is named — those live under
`.superpowers/sdd/unlabelled/probes/` and are the cheapest way to re-prove an
entry before working it.

**None of the 22 is pinned.** Every one is a candidate for the first pin.

## 1A. Grade A — stream desync

A wrong draw count or a wrong stream. These stop a replay converging outright,
which is the work this pipeline exists to unblock. Both are in `powers.py` and
both have an already-landed fix elsewhere in the file to copy.

### `power/aggression/BeforeSideTurnStart` — the wrong stream *and* the wrong shuffle  [LIVE] [**unpinned**]

- **sites** 1 entry, `power/aggression/BeforeSideTurnStart`.
- **impact** A, twice over.
- **divergence** `AggressionPower.cs:28` is
  `source.ToList().UnstableShuffle(Rng.CombatCardSelection).Take(Amount)` — a
  full Fisher-Yates on the dedicated CombatCardSelection stream.
  `powers.py:704` is `combat._rng.sample(candidates, min(self.amount, len(candidates)))`
  — Python reservoir sampling on the shared unseeded legacy `random.Random`.
- **observable** Two independent wrongnesses stack. (1) **Stream**: the draw
  never touches `combat.combat_rng.card_selection`, which is present and wired
  for exactly this purpose (`combat_rng.py:21`), so an Aggression turn consumes
  zero draws from CombatCardSelection and perturbs the shared rng instead.
  (2) **Draw count**: `random.sample(candidates, k)` and
  `UnstableShuffle(rng).Take(k)` consume different numbers of draws even when
  `len(candidates) == k`. Either alone desyncs the rest of the run.
- **trigger** Aggression is a registered Ironclad Rare Power card
  (`cards/aggression.py`), reachable from any card reward or shop. Any seed that
  plays it with an Attack in the discard pile.
- **pin** Unpinned. The natural home is a stream-accounting assert in
  `test/test_conformance_determinism.py`, not `test_hook_order.py`.
- **fix** Shuffle-then-slice on `combat.combat_rng.card_selection`, mirroring the
  already-landed HelloWorldPower fix (`powers.py:3279-3282`) but on the
  `card_selection` accessor rather than `card_gen`. The slot half is already
  correct — `before_side_turn_start` is a real dedicated hook now.
- **radius** `cards/pool.py:181`'s `take_random(items, count, rng)` is the other
  existing UnstableShuffle+Take port and is the candidate shared implementation
  for this and for every other unconverted `.sample(` site.

### `power/calamity/AfterCardPlayed` — a pure wrong-stream generation  [LIVE] [**unpinned**]

- **sites** 1 entry, `power/calamity/AfterCardPlayed`.
- **impact** A.
- **divergence** `CalamityPower.cs:48-50` generates through
  `CardFactory.GetForCombat(..., Rng.CombatCardGeneration)`;
  `powers.py:4031-4033` calls `random_pool_cards(combat._rng, ...)` — the shared
  legacy rng.
- **observable** The *algorithm* is already right: `random_pool_cards`'
  with-replacement branch (`cards/pool.py:153-178`) is textually the same
  per-card `rng.choice` loop as the parity port `cards/pool.py:204-219`,
  differing only in which rng it is handed. So this is same draws, same count,
  **wrong source** — `self.amount` draws land on the shared stream that
  CombatCardGeneration should have absorbed, and both streams are then wrong for
  the rest of the run.
- **trigger** `CalamityCard` (`colorless_powers.py:45-66`) is a registered
  colorless Power card reachable from any card reward; the power fires on the
  next Attack played.
- **pin** Unpinned; same home as Aggression's.
- **fix** One line: `cards.pool.get_for_combat_parity(combat.combat_rng.card_gen, ...)`.
- **radius** `random_pool_cards` is the legacy helper. Re-verified 2026-07-30
  that `combat.combat_rng` has exactly one other caller in `powers.py`
  (StampedePower) — **any other power still generating through
  `random_pool_cards(combat._rng, ...)` carries this same gap and is not
  enumerated anywhere.** That enumeration is owed.

## 1B. Grade B — the multi-site live families

Fix one site and several close. These are where the tier's leverage is.

### `power_cmd/G5` — no `PowerInstanceType`: every application merges  [LIVE] [**unpinned**]

- **sites** 13 entries, **6 of them live**: `power_cmd/step3`, `power_cmd/G5`,
  `power/automation/InstanceType`, `power/rolling_boulder/InstanceType`,
  `power/the_bomb/InstanceType`, `power/toric_toughness/InstanceType`. Dormant
  at the other seven (`heist`, `panache`, `sandpit`, `strangle`, `swipe`,
  `thievery`, `withering_presence`) — each for its own single-applier reason.
  **The largest live mechanism in the queue, and the largest mechanism of any
  liveness.**
- **impact** B — a payout lands at the wrong turn, and the sim's power list
  cannot represent the game's state.
- **divergence** `PowerCmd.cs:165-174`'s `FindExistingInstanceForStacking`
  dispatches on `power.InstanceType` (`PowerModel.cs:144`): `Instanced` always
  returns null — never merges, every application is an independent model with
  its own counter — `InstancedPerApplier` matches by applier, `None` matches by
  id. The sim's check is `if power_cls.id in target.powers` (`cmds.py:567`),
  which is `None` behaviour unconditionally, for all **11 ported**
  Instanced/InstancedPerApplier powers. Re-counted this round: 21 C# overrides,
  19 `Instanced` + 2 `InstancedPerApplier` (`OblivionPower.cs:27`,
  `StranglePower.cs:29`).
- **observable, executed** `.superpowers/sdd/unlabelled/probes/seam-power-cmd-g5-automation2.py`:
  apply `AutomationPower(1)`, fire 6 `on_card_drawn`, apply it again — the sim
  merges to `amount=2` on one instance whose `cards_left` never reset — then 4
  more draws fire a **single** `GainEnergy(2)` at draw #10, and draw #16 fires
  nothing. C# fires `GainEnergy(1)` at draw #10 (instance A) and a separate
  `GainEnergy(1)` at draw #16 (instance B, whose own counter started at its own
  creation). Same total, wrong timing — a combat ending between draw #10 and #16
  hands the sim's player energy the game is still withholding.
  `PanachePower` (`powers.py:4166-4212`) has the identical shape.
  For The Bomb, executed: play it on two consecutive turns and the sim holds
  **one** power with fuse list `[[2, 40], [3, 40]]` and `amount == 2` where the
  game holds **two** powers at Amount 2 and Amount 3 — and `full_env.py:412`
  encodes each power id as one presence bit plus one amount, so the game's state
  is **not representable** in the observation at all.
- **trigger** Ordinary duplicate colorless-card acquisition. `AutomationCard`
  and `PanacheCard` (`sts2_rl/cards/colorless_powers.py:17-41`) are un-gated
  Uncommon Power-card rewards with **no uniqueness check anywhere in
  `sts2_rl/rewards.py`**, so one run can take the same card from two reward
  screens. The Bomb (`cards/colorless_skills.py:750-778`) has no Exhaust
  keyword, so one copy played on two turns is enough.
- **pin** Unpinned.
- **fix** Give `Power.on_stack` real multi-instance semantics for the
  Instanced/InstancedPerApplier subset — a per-application sub-state list, the
  way `TheBombPower.on_stack` already does at `powers.py:4325-4327` for its
  fuses — instead of the silent default merge at `cmds.py:567-580`.
  `ToricToughnessPower`'s own docstring already flags the same risk for itself.
- **radius** All 11 ported units, plus **10 unported** ones that will need the
  distinction the day they land (Covered, Flanking, Guarded, Knockdown,
  MagicBomb, Monologue, Nightmare, Oblivion, Orbit, TagTeam). **Scope
  correction the record flagged and did not fix:** `sts2_rl/powers.py:64-65`
  cites this guard id for the sim's separate absence of `PowerStackType`
  (`PowerModel.cs:236`) — a *different* C# enum from `PowerInstanceType`. That
  citation is a mis-attribution; `power/_stack_type_single` (Tier 2) is
  PowerStackType's real home.

### `damage_pipeline/G4` + `/step17.5` — the killing-blow skip is recomputed after death prevention  [LIVE] [**unpinned**]

Bound to it at two more sites: **`relic/lizard_tail/ShouldDieLate`** and
**`relic/lizard_tail/AfterPreventingDeath`**, which are separate mechanism ids
carrying the same finding by binding rule 3. Four live entries, one fix.

- **sites** `damage_pipeline/G4`, `damage_pipeline/step17.5`,
  `relic/lizard_tail/ShouldDieLate`, `relic/lizard_tail/AfterPreventingDeath`.
- **impact** B — three cards drawn that the game does not draw, which perturbs
  the piles for the rest of the fight.
- **divergence** `DamageCmd.deal` runs `_resolve_death` — which includes the
  prevention *and* the preventer's own synchronous heal — **before** it reads
  `target.is_dead` to gate `on_damage_received` (`cmds.py:296`). C# locks the
  `AfterDamageReceived` skip decision to a `WasTargetKilled`/`IsDead` snapshot
  taken **before** `Kill()` (`CreatureCmd.cs:392`) and never revisits it, so the
  skip survives any later heal.
- **observable, executed** `.superpowers/sdd/unlabelled/probes/seam-damage-turn-g4.py`
  — player at 1/80 HP holding `[lizard_tail, centennial_puzzle]` takes 999
  damage: `lizard tail used: True`, hand grows 5 → 8 because Centennial Puzzle's
  `on_damage_received` fired and drew 3. The game skips that hook entirely on a
  killing blow.
- **trigger** Both relics are ported, independently obtainable content
  (`LizardTail.cs:40-51` / `:53-59` are reproduced faithfully at
  `lizard_tail.py:68-71` — **the relic is not the bug**).
- **pin** Unpinned. Pinnable exactly as the probe is written.
- **fix** Snapshot `target.is_dead` immediately after the HP write, before
  `_resolve_death` runs, and gate the `on_damage_received` dispatch on the
  snapshot rather than the live read — mirroring `CreatureCmd.cs`'s
  `WasTargetKilled` capture. Not fixable at either relic's own site.
- **radius** Any other death-preventer with a synchronous heal. Fairy in a Bottle
  reaches the same state through `should_die` instead of
  `after_preventing_death`; that leg is **named, not independently probed**.

### `power/_death_prevention_branch` — death prevention never re-kills  [LIVE] [**unpinned**]

**Most of this mechanism closed since the entry was written, and the closures
matter more than what is left.** The 1-HP floor is gone and `AfterDeath` now
fires on *both* arms: `_resolve_death`'s prevention arm (`cmds.py:123-136`)
leaves the creature dead at 0 HP, sets `retained_after_death`, fires
`on_death(..., True)` and then `after_preventing_death` — `CreatureCmd.cs:560-571`'s
shape. Feed scores its kill and Gremlin Horn fires. **Five entries elsewhere in
this queue are still dormant on the removed floor — see
[Outstanding record defects](#outstanding-record-defects).**

- **sites** 4 entries, **1 live**: `power/steam_eruption/g4`. Dormant at
  `power/adaptable/g5`, `power/illusion/g6`, `monster/test_subject/g1`.
- **what remains** The sim does not model C#'s **re-entry**:
  `CreatureCmd.cs:562-565` re-enters `KillWithoutCheckingWinCondition` while
  `creature.IsDead`, up to 10 times before throwing; `_resolve_death`'s
  else-arm simply returns. **A prevention that heals nothing is permanent in the
  sim and re-kills in the game, and the sim cannot express a prevention that
  fails.** That residual is not itself independently witnessed — the mechanism
  is live because `damage_pipeline/G4` proved the family live with the Lizard
  Tail probe, and binding rule 3 carries one verdict to every site.
- **impact** B — a creature the game re-kills goes on fighting in the sim.
- **pin** Unpinned.
- **fix** Add the bounded re-entry loop to `_resolve_death`'s else-arm, and land
  it with `damage_pipeline/G4`'s snapshot fix — they are the same window from
  two sides.
- **radius** `power/_should_stop_combat_from_ending` holds the combat open in the
  C# shape and does not exist in the sim.
- **the counter-example is the useful half** `monster/decimillipede_segment` is
  **correct**: `ReattachPower` lands on `should_remove_from_combat_after_death`,
  not on `should_die`. Executed — a killed segment fires `on_death`, sets
  `retained_after_death=True` and keeps taking turns (DEAD → REATTACH → WRITHE →
  CONSTRICT → BULK). **PROMPT.md class 21 names the wrong landing site and not
  the right one; this is the right one.**


### `relic/_stub` — relics ported as no-ops on premises that are now false  [LIVE] [**unpinned**]

- **sites** 5 entries, **1 live**: `relic/kifuda/AfterObtained`. Dormant at
  `relic/bing_bong/g1`, `relic/massive_scroll/g4`, `relic/punch_dagger/g1`,
  `relic/royal_stamp/g1` — the last two still carry the false premise "the sim
  has no enchantments".
- **what makes it live** Kifuda's stub premise is gone: G1 closed in round 7 and
  `kifuda.py` implements `after_obtained` for real (`Kifuda.cs:24-37`). What the
  entry now carries is that the *implemented* relic is wrong in the way
  `relic/_auto_keep` describes below — it always enchants `min(3, eligible)`
  cards with no way to enchant fewer. Kifuda is Shop rarity, and owning it with
  any eligible deck card is close to guaranteed every run.
- **impact** B — at the four dormant sites the relic simply does nothing; at
  Kifuda it does the wrong thing, which is worse.
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


### `relic/_auto_keep` — the driver has no "stop early", so every selection screen is forced  [LIVE] [**unpinned**]

**New mechanism this round.** It did not exist before round 11: it was split out
of the relic tier's offer-handling family when `relic/kifuda`'s G2 was promoted
from dormant to live, and it is the one entry in the whole round that moved in
that direction.

- **sites** 2 entries, **1 live**: `relic/kifuda/g2`. Dormant at
  `relic/gambling_chip/AfterPlayerTurnStart`, whose two remaining halves (the
  Sly auto-play and the Add-site `AfterCardChangedPiles`) are unreachable — no
  card or effect anywhere in `sts2_rl/` ever sets a card Sly, so
  `is_sly_this_turn` is unreachably False for every card in play.
- **impact** B — the deck the player ends the run with is not one the game could
  produce.
- **divergence** `Kifuda.cs:26` is
  `new CardSelectorPrefs(EnchantSelectionPrompt, 0, base.DynamicVars.Cards.IntValue) { Cancelable = false, RequireManualConfirmation = true }`
  — MinSelect 0, MaxSelect 3: the player may confirm having enchanted 0, 1 or 2
  cards even when more are eligible, and may only not back out of the screen
  entirely. `kifuda.py:25` is `run.select_cards("enchant", candidates, self.CARDS)`,
  one count and no range.
- **observable, executed** `.superpowers/sdd/unlabelled/probes/relic-7-kifuda-g2.py`.
  `RunState.select_cards` itself (`run.py:488-507`) is **permissive** — a
  hand-rolled selector returning 1 candidate is honoured. The restriction is in
  the driver gameplay and the RL environment actually use:
  `RunDriver._card_selector` (`driver.py:329-350`) computes
  `skippable = purpose in SKIPPABLE_PURPOSES` (`driver.py:93-96`) and `"enchant"`
  is not a member; with `skippable=False`, `DecisionRequest.legal_actions()` for
  SELECT_CARDS is `list(range(len(candidates)))` with no skip index appended
  (`driver.py:221-225`). **There is no legal action that means "stop".** The
  probe: `enchanted count (no selector installed): 3` on the bare Ironclad
  starting deck, and `'enchant' in SKIPPABLE_PURPOSES: False`.
- **trigger** Any run that buys Kifuda with at least one eligible card in deck —
  the bare starting deck alone has 8 of 10 eligible.
- **pin** Unpinned.
- **fix** Replace the boolean `SKIPPABLE_PURPOSES` with a per-purpose
  **minimum**, and append the stop action in `legal_actions()` once
  `len(picked) >= min_select` rather than only when the whole purpose is
  skippable.
- **radius** `driver.py`'s `SKIPPABLE_PURPOSES` / `_card_selector` /
  `DecisionRequest.legal_actions` are shared by **every** out-of-combat
  card-selection purpose — transform, upgrade, remove, and every other enchant
  relic. **Not extended here, deliberately**: `electric_shrymp`'s N2 and
  `tri_boomerang`'s N3 record that *their* C# `CardSelectorPrefs` set
  `MinSelect == MaxSelect`, a genuinely forced screen and a different shape from
  Kifuda's 0..3 range. `beautiful_bracelet` and `paels_growth` are unread —
  reading their constructors is an owed hand-off, not a claim.

## 1C. Grade B — the card-play result-pile chain

**Four live mechanisms, one fix.** C# has Corruption, Rebound and Nostalgia on a
single `ModifyCardPlayResultPileTypeAndPosition` chain (`Hook.cs:1391-1405`)
consulted once before the play-count loop, where each listener sees the previous
one's decision. The sim has the hook (`hooks.py:604-613`) but only Nostalgia
uses it; Corruption and Rebound are **after-the-fact movers** that reach into
the piles from `on_card_played` (`combat.py:904`) and both test the same
`card in player.discard_pile` membership. Two movers racing on one membership
test is order-dependent in a way the C# chain is not.

Read all four together. Fixing one alone makes the others worse.

### `power/corruption/ModifyCardPlayResultPileTypeAndPosition` — the exhaust redirect is a post-hoc move  [LIVE] [**unpinned**]

- **impact** B — a played Skill ends in the wrong pile.
- **divergence** `CorruptionPower.cs:27-38` returns `(PileType.Exhaust, position)`
  from the chain **unconditionally**, ignoring the incoming pileType, whenever
  the card is a Skill — so a played Skill never enters the discard pile at all.
  The sim appends it to the discard pile (`combat.py:812-814`), computes but does
  not apply the chain (`combat.py:842`), runs the play loop, and only inside
  `on_card_played` does `CorruptionPower` (`powers.py:799-810`) pull the card out
  and exhaust it.
- **observable, executed** The entry's *inherited* claim — that Nostalgia beats
  Corruption — was **false**, and checking it is what found the real edge.
  `power-5-corruption-nostalgia-contention.py`: Corruption wins, matching C#,
  because Nostalgia's C# override only fires `if (pileType != PileType.Discard)`
  while Corruption's ignores the incoming pile entirely. **The real live pairing
  is Rebound**: `power-5-corruption-rebound-order.py` — Corruption applied first,
  the Skill exhausts (matches C#); **Rebound applied first, the same Skill lands
  on top of the draw pile**, where C# exhausts it regardless of pickup order.
- **trigger** Corruption (`powers.py:780-810`) and Rebound (`powers.py:3220-3246`)
  are both ported Ironclad-pool card powers with no acquisition-order constraint.
- **pin** Unpinned.
- **fix** Give Corruption a real `modify_card_play_result_pile` override that
  fires before the loop. **This requires widening the sim's hook**, which today
  carries only `"discard"` / `"draw_top"` (`hooks.py:604-613`) with real
  exhausting handled by a wholly separate keyword path (`combat.py:846`) —
  neither of the sim's two pile-decision mechanisms has a slot for a
  power-driven, unconditional, incoming-state-ignoring redirect.
- **radius** Rebound's identical shape, and the exhaust-keyword branch's
  interaction with a widened hook. The **event-timing** half of the original
  text — Feel No Pain / Dark Embrace seeing `on_card_exhausted` fire mid-play
  rather than after the card resolves — is a structural consequence of the same
  shape, carried in this fix's radius but **not independently demonstrated**.

### `power/rebound/ModifyCardPlayResultPileTypeAndPosition` — Rebound is not on the chain at all  [LIVE] [**unpinned**]

- **impact** B.
- **divergence** The sim has the hook and this power does not use it, reaching
  into the piles from `on_card_played` instead. Hook order, executed:
  `combat.py:842` runs the chain **before** the play-count loop starts;
  `on_card_played` fires at `combat.py:904` inside it. So Nostalgia's hook always
  runs first, moves the card to the draw pile top, and Rebound then finds nothing
  in `player.discard_pile` (`powers.py:3237`) and **silently does neither its
  move nor its tick**. In C# both are on one chain and both always get a say.
- **trigger, executed** `ReboundCard` (`cards/trash_heap_cards.py:245-271`, a
  Trash Heap event reward) and `NostalgiaCard` (`cards/colorless_powers.py:178-199`)
  are ordinary registered Power cards; any run that plays both in one combat.
- **fix** Port Rebound onto `hooks.modify_card_play_result_pile` so it
  participates in the same one-decision chain.

### `power/rebound/AfterModifyingCardPlayResultPileOrPosition` — the stack tick has no hook to hang on  [LIVE] [**unpinned**]

- **impact** B — Rebound's remaining duration is wrong for the rest of the turn.
- **divergence** C# consumes the stack from a **dedicated after-hook**
  (`ReboundPower.cs:32-39` → `PowerCmd.Decrement`) that
  `Hook.ModifyCardPlayResultPileTypeAndPosition` fires over exactly the listeners
  that changed the value (`Hook.cs:1396-1405`). The sim has no such after-hook
  anywhere in `hooks.py`, so the tick is folded into Rebound's own
  `on_card_played` move: it fires **iff** the move fired.
- **observable** This is what silently drops the tick under the Nostalgia
  contention above — when Nostalgia already moved the card, `on_card_played`
  finds nothing and `self._tick()` never runs.
- **fix** Not independently fixable. Porting Rebound onto the shared hook and
  having it self-tick there closes this and the entry above together.
- **radius** The same absent machinery as `damage_pipeline/G2`'s twelve missing
  `AfterModifying*` variants, one family over.

### `power/nostalgia/g8` — Nostalgia can never win a contention it should sometimes win  [LIVE] [**unpinned**]

- **impact** B.
- **divergence** In C#, the last listener in `IterateCombatHookListeners` order
  wins the chain, so the outcome depends on **application order**. The sim
  structurally guarantees Corruption/Rebound always win: their hand-rolled move
  runs inside the play loop, Nostalgia's runs after it (`combat.py:929-931`) and
  is gated on `if card in self.player.discard_pile` (`combat.py:929`), already
  false.
- **observable, executed** `power-2-nostalgia-corruption.py`: apply Nostalgia
  then Corruption, play a Defend — it ends in `exhaust_pile`; with Rebound
  instead, it ends in `draw_pile`. A C# run that applied Nostalgia last would see
  it go to draw-top. **The sim can never produce that outcome, at any
  application order.** The prior, unexecuted pass claimed Nostalgia used to win —
  only the direction of the wrong answer changed, not the gap.
- **trigger** Corruption's gate is Skill-only and Nostalgia's is Attack-or-Skill;
  a played Skill is the overlap. Reachable with no relic.
- **fix** The shared one: move all three onto one real chain consulted once
  before the loop, each returning the incoming pile/position or overriding it.
- **radius** The three ported units are the whole current population; any future
  redirecting power joins the same chain.

## 1D. Grade B — single-mechanism live powers

Six mechanisms, one entry each, no shared machinery beyond the two `dark_embrace`
entries. Each is a small, self-contained fix in `powers.py`.

### `power/dark_embrace/AfterCardExhausted` — the draw count is a hard-coded 1  [LIVE] [**unpinned**]

`DarkEmbracePower.cs:47` draws `base.Amount`; `powers.py:339` is
`DrawCmd.draw(self.owner, 1)`, a literal, ignoring `self.amount` entirely. The
power's StackType is Counter and the one ported applier
(`cards/dark_embrace_card.py:34`) always passes 1 — but Dark Embrace is an
ordinary Rare Power card, not deck-unique, so two copies obtained across a run
and played in one combat stack Amount to 2 and the sim still draws 1.
**fix** `DrawCmd.draw(self.owner, self.amount)`, together with the deferral
below — fixing the amount alone still draws at the wrong time.

### `power/dark_embrace/AfterSideTurnEnd` — the ethereal deferral is missing  [LIVE] [**unpinned**]

**One premise of the inherited text is now false**: the `caused_by_ethereal`
plumbing this entry said "cannot be fixed inside the power" **exists** —
`hooks.on_card_exhausted(card, caused_by_ethereal=False)` (`hooks.py:914-928`),
the base `Power.on_card_exhausted` (`powers.py:314-315`), dispatched
`caused_by_ethereal=True` from the two ethereal-exhaust sites, and
`joss_paper.py:47` already consumes it. What remains:
`DarkEmbracePower.on_card_exhausted` (`powers.py:334-339`) accepts the parameter
and **does not branch on it**, drawing immediately instead of accumulating an
etherealCount and deferring to the side's end (`DarkEmbracePower.cs:52-60`,
whose source comment says the deferral exists so the drawn cards survive the
flush). Executed ordering: `combat.py:1260` runs `_process_turn_end_cards`
strictly before `combat.py:1272`'s flush — **so the card Dark Embrace draws off
a turn-end ethereal exhaust is discarded by the flush in the same call.**
**trigger** Dark Embrace plus any ported Ethereal card left in hand at turn end
(Apparition, Ascender's Bane, Clumsy, Dazed, Folly).
**fix** An `_ethereal_count` field, an early return in `on_card_exhausted` when
`caused_by_ethereal`, and a post-flush slot that draws `amount * count`.

### `power/retain_hand/AfterSideTurnEnd` — an extra turn skips the tick  [LIVE] [**unpinned**]

**The root cause this entry originally named is fixed** — `should_take_extra_turn`
moved to `combat.py:1293`, after `on_player_turn_end`, `_process_turn_end_cards`,
the flush and `after_player_turn_end`, mirroring `CombatManager.cs:1360-1373`.
The power still ticks from `on_enemy_side_end` (`powers.py:4082-4083`), and an
extra turn still skips it, because `combat.py:1292-1307` returns before ever
reaching `_execute_enemy_turn` and `on_enemy_side_end` is dispatched only from
inside it (`combat.py:617`).
**trigger, named this round** Pael's Eye (`relics/paels_eye.py`, ported ANCIENT
relic) grants an extra turn when the player ends a turn having played no cards;
Retain Hand comes from Equilibrium (`cards/colorless_skills.py:259-280`) or
Salvo. Play either, hold Pael's Eye, end the turn playing nothing: the sim
leaves Retain Hand(1) where C# has already decremented.
**fix** Move the tick to `after_player_turn_end` (`combat.py:1275`) — which
runs before the extra-turn check and after the flush. **This entry's earlier
reasoning that that slot would not fix it is false.**

### `power/ringing/ShouldPlay` — a history query modelled as a post-resolution flag  [LIVE] [**unpinned**]

C# asks "has the owner played a card this turn" by querying
`History.CardPlaysStarted` for entries that happened this turn, and the history
row is written when a play **starts** (`CardModel.cs:1930`, immediately after
`Hook.BeforeCardPlayed` and before `OnPlay`). The sim keeps a boolean
(`powers.py:1604`) set only from `on_card_played` (`powers.py:1623-1625`), which
fires **after** `OnPlay` has fully resolved (`combat.py:904`). So a card
auto-played from *inside* another card's `OnPlay` sees the flag still False and
slips through a block the game applies.
**observable, executed** `power-5-ringing-hellraiser-order.py`: player has
Ringing and Hellraiser, hand holds only Battle Trance
(`cards/battle_trance.py:34-38`, draw 3). Playing it draws the Ringing-afflicted
Strike mid-resolution; `HellraiserPower.on_card_drawn_early` (`powers.py:890-912`)
auto-plays it through `combat.auto_play_card` (`combat.py:999`), which *does*
consult `should_play_card` — and it passes. The Strike **resolved**: enemy HP
dropped to 50 from the 55-57 starting range.
**fix** Read `combat.history` — `combat.py:866`'s `card_play_started` call
already fires at the right moment — instead of setting a private flag from
`on_card_played`.
**radius** MayhemPower (`powers.py:3572-3583`) and StampedePower
(`powers.py:1025-1041`) also auto-play from mid-resolution contexts and are
named as further triggers for the same gap, **not independently executed**. Any
other ShouldPlay-family power reading a "played this turn" flag has the identical
shape.

### `power/skittish/AfterAttack` — block granted mid-card instead of after it  [LIVE] [**unpinned**]

`SkittishPower.cs:56-69` is an `AfterAttack` listener, firing **once** per
AttackCommand after every hit has landed; the sim uses `on_damage_received`
(`powers.py:2136-2157`), which fires **per hit**. The once-per-turn gate makes
the totals agree and the timing disagree: the second and later hits of a
multi-hit Attack are absorbed by block the game has not granted yet.
**observable, executed** Enemy with Skittish 8 hit by a Twin Strike (2×5): the
enemy loses **5 HP, not 10**, and ends at block 3.
**trigger** The ported Phantasmal Gardener
(`monsters/underdocks/phantasmal_gardener.py:50`) is a reachable elite, and Twin
Strike is a starter-adjacent Attack.
**fix** The slot already exists — `hooks.py:361-370`'s `after_attack`, used by
Vigor and Gigantification. Move the grant onto it.
**note** `power/curl_up` is the same shape and **turned out to have been fixed
already** — check the sibling before assuming this class is uniform.

### `power/smoggy/AfterCardEnteredCombat` — the same history-vs-flag shape  [LIVE] [**unpinned**]

**The record's filed rationale did not match the code and was re-derived from
the C# rather than the prose.** The stale claim — that this hook walks
`all_cards` — belongs to a *different* hook on the same power
(`powers.py:2081-2088`, `AfterCardPlayed`'s sweep), which this record already
carries as a separate `faithful` entry, so it could not have supported a gap
here at all.
The real divergence, from `SmoggyPower.cs:39-45`: C# guards on a
`History.CardPlaysStarted` query — seeded the moment a play *starts*
(`CardModel.cs:1930`) — while the sim reads `_skill_played_this_turn`
(`powers.py:2090-2096`), set at `powers.py:2085` inside `on_card_played`, i.e.
after the triggering Skill's own `on_play` returned.
**observable** If the first Skill a Smog'd player plays this turn generates a
new Skill mid-resolution, C# afflicts the new Skill with Smog and the sim does
not — so the sim's freshly-generated Skill is playable this turn where the
game's is blocked.
**trigger, executed** `DiscoveryCard` (`cards/colorless_skills.py:221-249`) adds
a chosen card straight to hand inside its own `on_play`, through
`CardPileCmd.add_to_hand` (`cmds.py:978-992`) → `_enter_combat` →
`on_card_entered_combat`, all before Discovery's own `on_card_played` sets the
flag. Living Fog applies Smoggy; the pool draw can offer a Skill.
**fix** Swap the flag read in `on_card_entered_combat` for a
`combat.history.of_type(CardPlayStartedEntry, this_turn=True)` query filtered to
Skills and this owner — the identical API `NostalgiaPower` already uses at
`powers.py:4148-4159`. The flag's other two readers are turn-boundary resets and
are unaffected.

## 1E. Grade B — deferred event ports that are not scope exclusions

Three live entries on two events. The lesson they share: **"DEFERRED PORT" is a
gap, not a waiver, whenever the gate is ordinary run state.** Both of these were
sitting behind stub `is_allowed` returns that looked like scope decisions.

### `event/crystal_sphere/IsAllowed` and `event/crystal_sphere/g1` — a real gate with no content behind it  [LIVE] [**unpinned**]

- **divergence** `CrystalSphere.cs:49-56` gates entry on
  `Players.All(p => p.Gold >= 100) && CurrentActIndex > 0`;
  `events/crystal_sphere.py:30-33` hard-returns `False`, a deliberate stub
  because the payout is an 11×11 reveal minigame with no headless analogue.
- **observable** A run in act 2 or 3 holding ≥100 gold that lands on a shared-pool
  `?` node the game would route to Crystal Sphere gets a **different event**. The
  gate is ordinary run state, not a rare edge.
- **trigger, executed** `misc-crystal-sphere-witness.py` builds a
  `RunState(gold=250)` at `act_index = 1`, shows `CrystalSphere.is_allowed(run)`
  is False while both C# preconditions hold, and that `'crystal_sphere'` is
  absent from `events.allowed_events(...)` — the actual selection-time filter
  (`rooms.py:451`, `events/__init__.py:146`).
- **fix** Porting the gate alone would surface an event whose `initial_options`
  is `[]` — a real gate with no content, which is worse. The honest fix is the
  gate **plus** the two portable non-presentation side effects:
  UncoverFutureCost's `LoseGold(50 + NextInt(1,50), Spent)` and PaymentPlan's
  `AddCurseToDeck<Debt>`.
- **radius** The 18-id SHARED_EVENTS shuffle keeps its draw count today only
  because the stub consumes no RNG (`events/crystal_sphere.py:1-14`); a port has
  to preserve that.
- **why two mechanisms** `g1` is the deferral itself and `IsAllowed` is the hook
  it lives on. `g1` is also the entry that exposed `_liveness`'s first-token-wins
  bug: its text reads "DORMANT is the wrong label here … so: LIVE", and the tool
  read the first token.

### `event/war_historian_repy/g2` — the Lantern Key now routes to an empty body  [LIVE] [**unpinned**]

- **why it is live now** Leg 1 (the routing) closed in **round 8**, *after* this
  leg was last written. That closure changed leg 2's reachability: it is no
  longer hypothetical.
- **divergence** `RunState.enter_point`'s EVENT arm calls `make_event(event_id, self)`
  on whatever id the `modify_next_event` chain produced (`run.py:1290-1295`) and
  **does not re-check that event's own `is_allowed`** — which is exactly leg 1's
  point. So `events/war_historian_repy.py:34-36`'s bare `return []` runs for
  real.
- **observable, executed** `misc-war-historian-witness.py`: a `RunState` at
  `act_index = 2` with a Lantern Key in the deck resolves
  `event_id == 'war_historian_repy'`; `make_event(...).begin()` then reports
  `initial_options() == []` and `finished == True` immediately. **No relic, no
  Lantern Key consumed, no choice ever shown**, where the game presents a real
  UNLOCK_CAGE / UNLOCK_CHEST decision with a payout (`WarHistorianRepy.cs:35-42`).
- **trigger** Hold a Lantern Key into act index 2. No new porting required.
- **fix** Port `history_course` as a relic — the one concrete unported
  dependency, confirmed by `py audit/tools/event_probes_c.py repy` — then the two
  options and their branches. Everything but the relic class is already
  expressible with verbs the sim has.
- **stale, flagged not fixed** `events/war_historian_repy.py`'s module docstring
  still says the event is "reached only … via a quest/room hook the sim does not
  model". That hook is modelled. Presentation-adjacent comment drift in a file
  the settling wave was not permitted to edit.

---

# Tier 2 — dormant gaps

Dormant at every recorded site: the divergence is real and verified, but no
currently-ported content reaches it. Each names the concrete thing that makes
it live, collected in the
[dormant-trigger watch list](#dormant-trigger-watch-list). Ordered by blast
radius first, then by seed-convergence exposure.

**530 entries, 382 mechanisms.** Sections 2A–2J are the engine seams and the
families that span them; **2K and 2L are the content tiers**, whose dormant
families are far larger per mechanism because one decision is recorded on every
unit it touches.

**Read every dormancy claim with a date on it.** The labels written in round 11
rest on executed enumerations. The ones written before it mostly rest on
arguments, and `relic/kifuda`'s G2 — dormant on the stated precondition "until
G1 is fixed", which was then fixed — is the proof that a dormancy argument can
expire without anyone noticing.

## 2A. The widest dormant families

Eight mechanisms that were this file's Tier 1 for ten rounds, when Tier 1 meant
"widest blast radius" rather than "live". Every one of them has been worked down
to a handful of sites — several from thirty-odd — and every one is still open at
those sites. They stay written out in full because they are still the largest
single-fix leverage in the queue, and because a mechanism this wide is exactly
the kind whose dormancy claim goes stale first.

**Read the bodies as briefs, not as current state.** They were written while the
mechanism was live and are in the present tense; the `divergence`, `observable`,
`fix` and `radius` fields are the best writeup of each, but the **`still open`**
line at the head of every entry is the only current thing in it.
`py audit/tools/gap_queue.py mechanisms` is the authority.

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


### `damage_pipeline/G2` — no `AfterModifyingXxx(modifiers)` companion events  [DORMANT] [**unpinned**]

- **still open** 6 sites: `damage_pipeline/G2`, `power_cmd/step22`, `/step31`, `/step32`, `power_cmd/G4` and `hook_dispatch/step38`. **No longer blocked on `power_cmd/G2`** — that guard settled dormant in round 11 (one presentation-only Given override, two Received overrides already reproduced inline).
- **sites, historically** `damage_pipeline/step5`, `/step9`, `/step12`, `/G2`;
  `power_cmd/step21`, `/step22`, `/step31`, `/step32`, `/G4`;
  `creature_card_cmds/step15`, `/G2`; `hook_dispatch/step38` — 12 entries at its
  widest, 6 today, still the second-largest mechanism in the queue.
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


### `damage_pipeline/G3` — pipeline-level `is_powered_attack` gate  [DORMANT] [**unpinned**]

- **still open** 3 sites, all on relics: `relic/fake_strike_dummy/ModifyDamageAdditive`, `relic/miniature_cannon/ModifyDamageAdditive` and `relic/strike_dummy/ModifyDamageAdditive`. The Vambrace and Sparkling Rouge sites closed in round 11.
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


### `hook_dispatch/G3` — no Early / VeryEarly / Late phase passes  [DORMANT] [**unpinned**]

- **still open** 2 of 7 sites: `power/hellraiser/AfterCardDrawnEarly` and `relic/tungsten_rod/g3` (`ModifyHpLostAfterOsty` is the first of C#'s two HP-loss passes). The five seam steps closed in rounds 8-11.
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


### `turn_structure/G13` — no `CheckWinCondition` after the turn-1 setup  [DORMANT] [**unpinned**]

**Mostly closed 2026-07-29 (round 5).** All six C# sites are recomputations now, and the four inline `_all_enemies_dead()/is_dead` pairs — which were `CheckWinCondition` with the tie-break the wrong way round — call it instead. Step 16's `SetupPlayerTurn` IsDead guard is ported; step 60's needs no separate line in a one-player sim and is pinned by test. What follows is the text as it stood.

- **still open** 2 of 9 sites, both on one relic: `relic/festive_popper/AfterPlayerTurnStart` and `/g3` — the port hand-rolls `self._check_win()`. Every seam step closed.
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


### `relic/_reward_late_pass` — the two-pass reward dispatch collapsed into one  [DORMANT] [**unpinned**]

- **still open** 2 of 24 sites: `relic/glitter/TryModifyCardRewardOptionsLate` and `relic/molten_egg/TryModifyCardRewardOptionsLate`. Driftwood closed in round 11.
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


## 2B. Parity-relevant dormant gaps — extra or off-stream RNG draws

These are labelled dormant because no *gameplay* effect differs today, but each
one takes a draw the game does not take, or takes it from the wrong stream.
Under legacy single-stream RNG that is invisible; under seed parity it is a
desync. **Read this group before the next conformance grind.**

### `creature_card_cmds/N10` + `/step104` — CardSelectCmd's auto-select shortcut  [DORMANT / parity-live] [unpinned]

- **sites** `/N10` (1 entry today). `creature_card_cmds/step104` and
  `creature_card_cmds/step105` each anchor their own one-site mechanism now — the
  first is this heading, the second is in
  [3F](#3f-coverage-anchors--the-seam-mechanism-with-no-prose-home) — and all
  three share this body's finding.
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
- **radius** Any replay through a grid/selection screen. The two mechanisms this
  bullet used to name — `AutoPlayFromDrawPile`'s two-phase structure and the
  shuffle-order one — both closed in round 11.

## 2C. Missing guard families

### `damage_pipeline/G5` — no dealer-dead / target-dead entry guard  [DORMANT] [unpinned]

- **sites** `damage_pipeline/step3`, `/G5` (2 entries; `/step1` closed).
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

- **sites** `creature_card_cmds/step102c`, `/N4` (2 entries).
- `CardPile.AddInternal` throws if the pile already holds that `CardModel`
  instance and `RemoveInternal` throws if it does not (`CardPile.cs:86-89,
  117-120`); the sim's piles are plain lists with no invariant — which is what lets
  `/G7`'s double-membership bug exist silently.
- **pin** unpinned. **fix** assert the invariant in the three pile helpers.
  **radius** `/G7` is the verb-level symptom of this container-level hole; fix N4
  first and G7 becomes a loud failure instead of a silent one.

### `creature_card_cmds/N2` — `afflict` skips ShouldAfflict / CanAfflict / AfterApplied  [DORMANT] [unpinned]

- **sites** `creature_card_cmds/step64`, `/step65`, `/N2` (3 entries).
- `CardCmd.Afflict` guards on `Hook.ShouldAfflict` and `affliction.CanAfflict(card)`
  and fires an `AfterApplied` lifecycle event (`CardCmd.cs:627-634` ff.); the sim
  has no surface for any of the three and returns `None` where C# throws.
  `ShouldAfflict` has zero overrides game-wide; `CanAfflict` has no sim surface at
  all. Trigger: porting any affliction with a `CanAfflict` restriction.
- **radius** `hook_dispatch/G6` (afflictions are not listeners at all), `/G8`.

### `creature_card_cmds/N5` + `/step31` — `EnergyCmd.gain` lacks the `finalAmount > 0` guard  [DORMANT] [unpinned]

`PlayerCmd.cs:37-41` adds energy only when the modified amount is positive;
`cmds.py:553-554` does `player.energy += amount` unconditionally, so a modifier
returning a negative value would subtract energy. The only ported
`modify_energy_gain` listener returns 0 (`NoEnergyGainPower`,
`powers.py:554-557`), a no-op under both rules. One `if final > 0` guard.

## 2D. Missing hook surfaces

### `creature_card_cmds/G8` — no `AfterCardChangedPiles` at all  [DORMANT] [unpinned]

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

### `creature_card_cmds/G11` + `/step49` — `AfterCardDiscarded` fires pre-move and in a batch  [DORMANT] [unpinned]

C# adds each card to the discard pile **first**, then fires the hook, one card at
a time (`CardCmd.cs:186-195`); `discard_hand` (`player.py:192-196`) fires
`on_card_discarded` for every flushed card while they are all still in `hand`,
then moves them as a batch. Executed: flushing `[Strike, Defend]` records
`[('strike', in_hand=True, in_discard=False), ('defend', in_hand=True,
in_discard=False)]` at hook time; C# would give `(False, True)` for each and would
have moved Strike before Defend's hook ran. Trigger: any `on_card_discarded`
listener that reads pile membership. Fix: interleave move-then-fire.

### `creature_card_cmds/G9` + `/step84` — `ShouldDraw` re-evaluated per card, no `AfterPreventingDraw`  [DORMANT] [unpinned]

`CardPileCmd.Draw` evaluates `Hook.ShouldDraw` exactly once before the loop and
fires `Hook.AfterPreventingDraw` on refusal (`CardPileCmd.cs:804-808`);
`player.py:280-281` calls `should_draw` inside the per-card loop and has no
`after_preventing_draw`. Trigger: a `should_draw` listener that flips mid-draw —
Fiddle (`relics/fiddle.py:26-29`) is the only ported one and is stateless. Fix:
hoist the check; add the hook.

### `creature_card_cmds/step12` — no `BeforeBlockGained`  [DORMANT] [unpinned]

C#'s unconditional pre-modifier event carrying the raw amount
(`CreatureCmd.cs:642`, `Hook.cs:131-137`) has no sim surface. Zero overrides
game-wide today; live the moment any model implements it. One dispatcher to add.

### `creature_card_cmds/step46` — no `BeforeCardAutoPlayed`  [DORMANT] [unpinned]

`combat.py:552` fires `on_energy_spent(card, 0)` and then the ordinary
`before_card_played`; the auto-play-only event is absent and none of its C#
implementations is ported. **radius** `hook_dispatch/G4` (the per-play bracket).

### `creature_card_cmds/step61` — no `AfterCardGeneratedForCombat` on transform  [DORMANT] [unpinned]

`cmds.py:445-450` fires only `on_card_entered_combat`; C# fires **both** events for
a combat-pile transform (`CardCmd.cs:445` and `504`). None of the seven C#
implementations is ported.

### `turn_structure/step20` — no `AfterModifyingHandDraw`  [DORMANT] [unpinned]

`modify_hand_draw` is ported with the same base of 5 (`player.py:171`), but the
companion event is absent. C# has four implementers; the two ported ones are
presentation-only (`Pocketwatch.cs:67-71` is a bare `Flash()`). This is one of
`damage_pipeline/G2`'s 13 variants.

### `turn_structure/step55` — no `BeforeFlush`  [DORMANT] [unpinned]

No slot between `_process_turn_end_cards` (`combat.py:658`) and the flush
(`661-662`). C#'s three implementers (`SlumberingEssence.cs`,
`WellLaidPlansPower.cs`, a mock) are unported. **radius** `enchantment/EG2`.

### `turn_structure/G7` + `/step63` — no `AfterFlush`  [DORMANT] [**unpinned**]

**Narrowed in round 11: the guard is half closed.** `EndOfTurnCleanup` — the
second of C#'s two per-round sites (`CombatManager.cs:1344-1346`) — is ported:
`PlayerCombatState.discard_hand` calls `end_of_turn_cleanup()` unconditionally
as its last line. What remains is `Hook.AfterFlush` (`Hook.cs:560-570`), which
C# fires **unconditionally**, even when nothing was flushed, and which has no
`after_flush` anywhere in `sts2_rl/hooks.py`. **Dormant by enumeration,
executed:** `grep -rl 'override.*Task AfterFlush' src/` over the decompiled game
returns exactly **one** file, `Bookmark.cs` — a Rare relic that shaves 1 energy
off a random retained card — and Bookmark is not ported. `on_hand_emptied` is
confirmed *not* AfterFlush's counterpart: C# excludes the flush from
`CheckForEmptyHand` (`CombatManager.cs:880-883`) and the sim now matches.

### `turn_structure/step8` — no per-power `AmountOnTurnStart` snapshot  [DORMANT] [unpinned]

`grep -rn amount_on_turn_start sts2_rl/` returns 0 hits. C# snapshots every power's
amount before anything else in the turn (`CombatManager.cs:449-455`,
`Creature.cs:673-679`) and three powers read it, two ported:
`DrawCardsNextTurnPower` (`AmountOnTurnStart == 0` suppresses both the extra draw
and the removal, `DrawCardsNextTurnPower.cs:28,37`) and `HelloWorldPower`. The
sim's `DrawCardsNextTurnPower` (`powers.py:2737-2754`) has no such guard, so a
stack applied during the turn-start window would draw and expire in the same turn.

### `turn_structure/step17` — the two energy hooks fire in the opposite order  [DORMANT] [unpinned]

The arithmetic matches (`player.py:163-167`) but the sim calls `modify_max_energy`
first and `should_reset_energy` second, where C# evaluates
`ShouldPlayerResetEnergy` first and reads `MaxEnergy` inside the chosen branch
(`CombatManager.cs`). Unobservable while both dispatchers are pure aggregations;
live with the first side-effecting implementation of either.

### `hook_dispatch/step37` — the predicate family short-circuits in the sim  [DORMANT] [unpinned]

C# uses `flag = flag || item.ShouldX(...)` with **no** short-circuit, calling every
listener (`Hook.cs:2472-2480` `ShouldForcePotionReward`, `2485-2493`
`ShouldAllowFreeTravel` — those are the only two); the sim aggregates with a
short-circuiting `any(...)` (`rewards.py:449`). Each hook has exactly one
implementer today (`WhiteBeastStatue.cs`, `WingedBoots.cs`), both side-effect free.
Trigger: a second ported implementer with a side effect.

## 2E. Listener-registry shape

### `hook_dispatch/G7` — no per-item liveness re-check  [DORMANT] [unpinned]

- **sites** `hook_dispatch/step4`, `/step12`, `/step16`, `/step45` (4 entries; `/step11` closed).
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

## 2F. Power pipeline

### `power_cmd/G1` — Artifact's typing is static, not sign-aware  [DORMANT] [**unpinned**]

- **sites** `power_cmd/step13` (1 entry today; `/step28` and the `/G1` guard row itself both closed, so the mechanism now lives at its step alone).
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

### `power_cmd/G2` + `/step10` — Unsettling Lamp's condition has the same blind spot  [DORMANT] [unpinned]

`relics/unsettling_lamp.py:44-53` bails on `amount <= 0` and then checks the static
`power_type`, where C# uses `power.GetTypeForAmount(amount)`
(`UnsettlingLamp.cs:124`). `Malaise.cs:40` and `Resonance.cs:33` both apply
negative `StrengthPower` with `applier = player, cardSource = this` — exactly the
shape Lamp doubles — and the sim's `amount <= 0` guard rejects it before the
sign-aware check would matter. **This is the seam the 933T Mecha Knight bug lived
on**: the ordering half is fixed, the sign half is not.

### `power_cmd/G3` — the three power-amount phases collapsed into one chain  [DORMANT] [unpinned]

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
- **radius** `hook_dispatch/G3` (phases), `hook_dispatch/G4`
  (`damage_pipeline/G2`, the companion events), `/G1`.

### `power_cmd/N4` — `/step4` and `/step26`: one code path serves Apply and ModifyAmount  [DORMANT] [**unpinned**]

C# has two independently-coded pipelines whose guards differ
(`PowerCmd.cs:79-87` branches; Apply is `PowerCmd.cs:101-159`, ModifyAmount
`:215-271`); the sim collapses them into one `PowerCmd.apply`
(`cmds.py:508-605`). **Settled dormant in round 11 by reading the two C#
pipelines side by side.** Every guard-level difference this structural note
points at is already tracked under its own name in the same record: the
`amount == 0` half is `power_cmd/step6` below; the `CanReceivePowers` half is
guard N4's own `faithful` finding (C#'s ModifyAmount does not check it either,
so the asymmetry is in the source, not in the port); `BeforeApplied` /
`AfterApplied` is a `deliberate-divergence` verified by execution; and the two
History differences are waived as telemetry. The three hook calls
(`BeforePowerAmountChanged`, `ModifyPowerAmountGiven`,
`ModifyPowerAmountReceived`) run in the **same order in both** C# pipelines,
which is what lets the sim's one collapsed call (`cmds.py:553`) stand in for
both. **Read this entry before touching `PowerCmd.apply`**: it is where a future
guard difference between the two pipelines would surface, and `hook_dispatch/G4`
is the one place a collapse like this has already been proven wrong.

`power_cmd/step26` — the ModifyAmount entry point itself — anchors its own
one-site mechanism at the same place, and settled dormant on the same reading.

### `power_cmd/step6` — no `amount == 0` early return  [DORMANT] [unpinned]

Filed under the `IsEnding` family by its first reference, but it owns the
zero-amount half itself. Executed: `PowerCmd.apply(cs.hooks, cs.enemy,
StrengthPower, 0)` -> `{'strength': Strength(0)}`, same for Vulnerable, where C#
(`PowerCmd.cs:103`) registers nothing; a 0-amount debuff on the **player**
additionally lands with `skip_next_tick = True`. One guard at the top of
`PowerCmd.apply`.

## 2G. Damage pipeline remainder

### `damage_pipeline/G6` and `damage_pipeline/step17.4` — the dealer-side event fires after the victim-side one  [DORMANT] [unpinned]

(Two mechanism ids, one finding: the guard and the step that records it each
stand alone because the step names no guard.)

`CreatureCmd.cs:388-395` fires `AfterDamageGiven` (unconditional) **before** the
killing-blow-guarded `AfterDamageReceived`; `DamageCmd.deal` fires
`on_damage_received` then `on_damage_dealt` — the reverse. No sim power implements
`on_damage_dealt` yet. Two lines to swap.

## 2H. Creature and card verbs with no sim counterpart

### `creature_card_cmds/G5` + `/step22` — heal reports the clamped amount, and nothing at full HP  [DORMANT] [unpinned]

`CreatureCmd.cs:751-754` fires `AfterCurrentHpChanged` when the **requested** amount
> 0, carrying that raw amount; `cmds.py:162-166` fires with the **clamped** amount
and only when positive. Executed: healing 20 on a player 3 below max reports delta 3
(C#: 20); healing at full HP reports nothing (C#: reports +amount). The only ported
`on_hp_changed` listener is Red Skull (`relics/red_skull.py:44-46`), which ignores
the delta.

### `creature_card_cmds/G6` — `lose_max_hp` cannot kill  [DORMANT] [unpinned]

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

`cmds.py:379-384` removes the card from `hand` or `discard_pile` and appends it to
`exhaust_pile`; a card in the draw pile, the exhaust pile, or mid-play stays put
**and** lands in the exhaust pile — it exists in two piles at once. Executed: a
Strike alone in the draw pile ends with `card in draw_pile` **and** `card in
exhaust_pile`; a Strike exhausted twice ends with the same instance in the exhaust
pile twice. C# routes through `CardPileCmd.Add(card, Exhaust, Bottom)` whose
`RemoveFromCurrentPile()` is pile-agnostic (`CardPileCmd.cs:496`). **radius** `/N4`
is the missing invariant that hides it.

### `creature_card_cmds/G13` + `/step8` — escape leaves the escaper's powers registered  [DORMANT] [unpinned]

`CreatureCmd.Escape` calls `RemoveAllPowersInternalExcept()` (`CreatureCmd.cs:589`),
stripping every power silently — the deliberate contrast with death, which awaits
each `AfterRemoved` (`533-537`); the sim's escape (`cmds.py:221-234`) sets
`escaped = True`, fires an invented `on_creature_escaped` hook and leaves every
power on the creature **and registered as a live hook listener**. The three ported
escape sites (Thieving Hopper, Gremlin Merc, `BattlewornDummyTimeLimitPower`) leave
only owner-scoped, self-filtering powers.

### `creature_card_cmds/step18` — no `LoseBlock` verb  [DORMANT] [unpinned]

Four sites assign `block = 0` directly (`combat.py:297`, `player.py:158`,
`powers.py:1208`, `powers.py:2300`). `BurrowedPower`'s C# original calls
`CreatureCmd.LoseBlock(owner, all)` from `AfterRemoved`, so where C# re-fires
`Hook.AfterBlockBroken` on residual block the sim fires nothing. Hand Drill
(`relics/hand_drill.py:21`) is a live `on_block_broken` listener that would see the
difference.

### `creature_card_cmds/step23` — no `SetCurrentHp` verb  [DORMANT] [unpinned]

Sites that need one assign HP directly (`powers.py:2360-2365`, `cmds.py:112`); none
runs the death pipeline the way `CreatureCmd.cs:775-778` does, so setting HP to 0
through those paths would leave a 0-HP creature that never fired
`BeforeDeath`/`ShouldDie`/`AfterDeath`. Every ported direct assignment sets a
positive HP (a revive).

### `creature_card_cmds/step26` — no `SetMaxAndCurrentHp` verb  [DORMANT] [unpinned]

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

### `creature_card_cmds/N9` + `/step82` — the sim has no Play pile  [DORMANT] [unpinned]

C# holds a card being played in `PileType.Play` for the whole of `OnPlay`
(`CardPileCmd.cs:669-670`, `CardCmd.cs:114-117`) and `Shuffle` reads only Draw and
Discard (`CardPileCmd.cs:870-871`) — the entire mechanism behind the exoskeleton
reshuffle parity fact. The sim appends the played card to the **discard** pile and
holds it back from a reshuffle **in parity mode only** (`player.py:203, 232`),
because legacy RL runs are kept byte-for-byte. Residual exposure: an effect that
counts the discard pile during its own `OnPlay` sees the resolving card in the sim
and not in the game.

## 2I. Monster state machine remainder

### `monster_state_machine/G8` — no construction validation  [DORMANT] [**unpinned**]

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

### `monster_state_machine/G7` — `AddBranch` repeat-limit edge cases  [DORMANT] [**unpinned**]

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

`Inklet.cs:69-71` builds and registers `INIT_RAND` with two branches (one of them
`AddBranch(JAB, 2, 1f)` = maxRepeats 2) and never wires it; `PhrogParasite.cs:6-10`
is the same shape. Reproducing only the reachable graph is *correct* today, but the
sim cannot express the dead state, so the moment one becomes reachable the port
silently keeps the old graph. Pinned in the opposite direction by
`test/test_monster_branch_audit.py::TestInkletMoveSequence` and
`::TestPhrogParasiteMoveSequence`, which assert **zero** `monster_ai` draws on
exactly those legs.

## 2J. Turn structure remainder

### `turn_structure/step14` — `AfterBlockCleared` fires unconditionally  [DORMANT] [unpinned]

The surviving site of the closed `turn_structure/G1` mechanism. C# runs a SECOND,
separate loop over the same participants — `await Hook.AfterBlockCleared(state,
creature)`, **unconditional** (`CombatManager.cs:500-507`, `Hook.cs:119-125`). It
fires for a creature that had no block, for a creature whose clear was PREVENTED,
and for a player on turn 1 whose `AfterTurnStart` returned early. The complete
second pass is ported; what is still recorded is whether every one of those three
no-op cases reaches the listener. Re-execute before working it.

### `turn_structure/step32` + `/step67` — no `SpawnedThisTurn` flag, no `OnSideSwitch`  [DORMANT] [unpinned]

`TakeTurn` runs `PerformMove()` only if `!Monster.SpawnedThisTurn`; `grep -rn
spawned_this_turn sts2_rl/` returns 0 hits, and there is no side-switch verb to
clear it either (`CombatManager.cs:1420-1424`, `MonsterModel.cs:479-483`). The
no-`IsDead`-guard half **is** faithfully ported (`combat.py:288-292` keeps a
`retained_after_death` corpse in the loop — that is how a withered Decimillipede
segment reaches REATTACH). The record could not construct a reachable C# path where
the flag survives to `TakeTurn`. **radius** `monster_state_machine/G9`.

## 2K. Content-tier dormant families

The content tiers' recurring dormant mechanisms. Each is one decision
recorded on many units, so each is one fix — and each is a *large* fix, because
the population is large.

### `card/_unplayable_cost` — an unplayable card's canonical energy cost is `-1` in C# and `0` in the sim  [DORMANT] [unpinned]

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

## 2L. Monster-tier dormant families

Six dormant mechanisms, 12 entries. Three of them are the same underlying hole:
**the sim's intent vocabulary is lossier than C#'s `AbstractIntent[]`**, which
`monster_state_machine` boundary item 2 named as belonging to no seam's scope
and which nothing has audited since. They are dormant because no sim consumer
reads the missing part today — but the RL observation encoder is exactly the
kind of consumer that would, and `monster/_second_intent_dropped` is the same vocabulary hole already
LIVE for two moves that drop a whole intent rather than a field of one.

### `monster/_no_intent_unrepresentable` — a `MoveState` with an empty intent array  [DORMANT] [unpinned]

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

One gap entry each, with a handful of two-site exceptions. They are real,
recorded and verified — they are here rather than written out because a
single-unit finding is cheaper to read in its own record than restated, and
because a prose list this long would bury Tiers 1 and 2.

Each row is the mechanism id, the liveness its record now states as a typed
`live` boolean, and that record's lead clause, trimmed. **Line numbers are
stripped from these summaries on purpose** — open the record for the
citation, so that `cite-check` stays a check on the authored prose above
rather than a re-validation of the record excerpts. The id is the path:
`power/artifact/…` is `audit/records/power/artifact.json`.

**There is no `unlabelled` row any more.** Every entry below carries an
explicit `live` key. That is a claim about the records' *form*, not a
guarantee about their *content*: a `live: false` written on a stale premise
still reads as dormant here, and Tier 3 is where the least-re-checked
dormancy arguments live.

## 3A. `power` — 98 single-site mechanisms

One power, one finding. The recurring power families are written out above —
`power/_death_prevention_branch` and `power_cmd/G5` in Tier 1, and
`power/_stack_type_single`, `creature_card_cmds/step8c` and
`power/_after_damage_given_substitution` in Tier 2. Everything below stands
alone.

- `power/artifact/AfterModifyingPowerAmountReceived` — dormant — ADJUDICATION 2026-07-30 (round 11, batch power-5) -- this entry was the blocking tie-break between damage_pipeline/G2 (recorded 'live', citing this exact PowerAmountReceived edge via power_cmd/G4's 'Unsettling Lamp seam') and this batch's assignment …
- `power/artifact/TryModifyPowerAmountReceived` — dormant — The interception is reimplemented outside the hook system entirely, and the debuff test is the wrong one. C# (ArtifactPower.cs) is a TryModifyPowerAmountReceived listener whose three guards are target != Owner, …
- `power/buffer/ModifyHpLostAfterOstyLate` — dormant — The arithmetic is exact -- 0 for the owner, unchanged otherwise (BufferPower.cs vs powers.py) -- and the AFTER-Osty position is right, since cmds.py runs after block absorption (:74-81). What is lost is the LATE half, and BufferPower.cs states in as …
- `power/burrowed/AfterRemoved` — dormant — C#'s AfterRemoved is CreatureCmd.LoseBlock(oldOwner, 999999999m) -- dump ALL the block -- and it runs on EVERY removal path, including the automatic strip when the owner dies (CreatureCmd.cs then each power's AfterRemoved). The sim has no …
- `power/calamity/BeforeCardPlayed` — dormant — C# uses a TWO-HOOK LATCH the sim collapses into one. CalamityPower.cs records amountsForPlayedCards[card] = base.Amount at BeforeCardPlayed and :44 removes it at AfterCardPlayed, so (a) the Amount is SNAPSHOTTED at the start of the play and (b) the …
- `power/chains_of_binding/AfterCardDrawn` — dormant — Two divergences. (1) A DROPPED GUARD: C# requires base.CombatState.CurrentSide == base.Owner.Side (ChainsOfBindingPower.cs), so only cards drawn during the PLAYER's own turn are Bound; the sim has no side test (powers.py), so a card drawn during the …
- `power/chains_of_binding/BeforeCardPlayed` — dormant — WRONG SIDE OF THE PLAY, the same shape as SlothPower's: C# sets boundCardPlayed in BeforeCardPlayed (ChainsOfBindingPower.cs) and the sim sets it in on_card_played, after resolution -- while the sim's before_card_played slot (combat.py) exists and …
- `power/crab_rage/g1` — dormant — CrabRagePower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)); the sim's PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.STRENGTH_GAIN) …
- `power/crimson_mantle/g3` — dormant — CrimsonMantlePower.cs fires the damage UNCONDITIONALLY — C# calls CreatureCmd.Damage with the DamageVar's BaseValue every turn, including the first, when the value is 0; powers.py guards on if self.self_damage > 0. A 0-damage CreatureCmd.Damage is …
- `power/cruelty/g2` — dormant — CrueltyPower.cs target == base.Owner -> unmodified — Cruelty's self-exclusion is dropped by its consumer. Recorded in full on power/vulnerable's matching guard -- the sim reads Cruelty's amount with no such test, so a Cruelty holder attacking its …
- `power/cruelty/g4` — dormant — CrueltyPower.cs amount + base.Amount / 100m — SETTLED 2026-07-30 (round 11), by execution -- arithmetic worked out in full, not hand-waved. The TYPE mismatch is real: powers.py computes mult += cruelty.amount / 100.0 in Python float where C# …
- `power/curious/g2` — dormant — CuriousPower.cs,32 the TryModify predicate protocol — C#'s Try* hooks are a predicate chain: the listener returns bool to say 'I changed it' and writes the new value to an out-param, and Hook.ModifyEnergyCostInCombat (Hook.cs) uses that to decide …
- `power/curl_up/AfterCardPlayed` — dormant — NARROWED 2026-07-29 (round 11): this entry's own premise was stale. It was written to say the sim has AfterCardPlayed's whole job missing ("the block and the removal moved into AfterDamageReceived"), but that was the PRE-round-7 sim -- the …
- `power/dampen/AfterApplied` — dormant — Two findings. (1) MECHANISM, the same substitution as illusion's: C#'s AfterApplied runs after PowerCmd registers the power; the sim does the work in __init__, i.e. inside power_cls(...) at cmds.py and therefore BEFORE hooks.register and …
- `power/dampen/AfterDeath` — dormant — C# tracks a SET of casters (Data.casters, added through the public non-override AddCaster, DampenPower.cs/73-76) and removes the power only when the LAST caster dies (casters.Remove(creature); if (casters.Count == 0) PowerCmd.Remove(this), …
- `power/dampen/g3` — dormant — DampenPower.cs public void AddCaster(Creature) — A public non-override method, so the harness does not enumerate it -- recorded so a reader does not think it was skipped (the same courtesy the main report gives …
- `power/dark_shackles/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs, which …
- `power/dark_shackles/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has …
- `power/dexterity/ModifyBlockAdditive` — dormant — The sim keys the ownership test on the BLOCK TARGET where C# keys it on the CARD's owner. DexterityPower.cs: when cardSource != null the test is cardSource.Owner.Creature != base.Owner -> 0m and the target is not consulted at all; only for …
- `power/dexterity/g2` — dormant — Sign-aware power typing on a negative Dexterity application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGATIVE amount, because …
- `power/disintegration/AfterSideTurnEndLate` — dormant — Wrong slot AND lost phase, and it is the only power in this group with both. (a) PHASE: this is AfterSideTurnEndLate, the second complete pass Hook.AfterTurnEnd runs (Hook.cs), so in the game Disintegration's damage lands after EVERY plain …
- `power/draw_cards_next_turn/AfterSideTurnStart` — dormant — RE-READ 2026-07-30 (round 11): the entry's own citations (powers.py on_player_turn_started) are STALE -- the code has moved twice since this text was drafted (per CONTRACT rule: re-execute the witness before trusting the prose). Today …
- `power/draw_cards_next_turn/ModifyHandDraw` — dormant — The count is right (count + Amount, DrawCardsNextTurnPower.cs vs powers.py -- and correctly NOT the flat +1 that its sibling power/clarity uses; the two classes exist precisely to differ here, ClarityPower.cs). The GUARD is missing: …
- `power/feeding_frenzy/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs, which …
- `power/feeding_frenzy/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has …
- `power/flame_barrier/AfterSideTurnEnd` — dormant — The removal condition is inverted from a side comparison into a hard-coded side. FlameBarrierPower.cs removes the power whenever base.Owner.Side != side -- i.e. at the end of the turn belonging to the side the owner is NOT on, which for a …
- `power/flex_potion/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the wrapper's internal stat …
- `power/flex_potion/g5` — dormant — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; Rend, Sleight of Flesh …
- `power/free_attack/g4` — dormant — The TryModify predicate protocol — C#'s Try* hooks return bool and write to an out-param, which Hook.ModifyEnergyCostInCombat (Hook.cs) uses to build its notification list; the sim's modify_card_energy_cost (hooks.py) is a plain fold with neither. …
- `power/galvanic/AfterCardPlayed` — dormant — **PROPS.** C# deals the Galvanized damage with ValueProp.Unpowered | ValueProp.Move (GalvanicPower.cs); the sim passes DamageProps.NON_CARD_UNPOWERED, which valueprops.py defines as UNPOWERED **alone** -- the MOVE flag is missing. The right constant …
- `power/galvanic/BeforeCombatStart` — dormant — Right slot -- combat.py fires on_combat_start immediately before start_turn() at :209, which turn_structure identifies as the sim's BeforeCombatStart. The divergence is an ADDED GUARD (recurring shape 8): C# afflicts EVERY Power card unconditionally …
- `power/gigantification/AfterAttack` — dormant — The slot is right (combat.py, immediately after the card's on_play inside the play-count loop). The GAP is the IDENTITY the latch is cleared against: C# compares ATTACK-COMMAND identity (command == internalData.commandToModify, …
- `power/hardened_shell/ModifyHpLostBeforeOstyLate` — dormant — The FORMULA is exact -- target != Owner -> amount, amount == 0 -> amount, else Math.Min(amount, Amount - damageReceivedThisTurn) (HardenedShellPower.cs) vs powers.py -- and the BeforeOsty/AfterOsty phase collapse is already resolved as faithful by …
- `power/heist/BeforeDeath` — dormant — HOOK-PHASE MISMATCH -- a BEFORE hook ported onto an AFTER hook, the recurring shape section 0 item 5 of the stream report names for thorns/curl_up/skittish/suck, now in a death-time form. C# calls Hook.BeforeDeath UNCONDITIONALLY at CreatureCmd.cs, …
- `power/hello_world/g1` — dormant — HelloWorldPower.cs base.AmountOnTurnStart >= 1 (used as BOTH the guard and the card count) — The guard is ported as self.amount < 1 (powers.py) and the count as self.amount (:2825), where C# uses base.AmountOnTurnStart for both (HelloWorldPower.cs …
- `power/hellraiser/AfterSideTurnEnd` — dormant — RE-VERIFIED 2026-07-30. HellraiserPower.cs resets the per-turn infinite-auto-play counter (infiniteAutoPlaysThisTurn = 0). The sim's HellraiserPower (powers.py, current text read in full) tracks no such counter at all -- on_card_drawn_early …
- `power/high_voltage/g1` — dormant — HighVoltagePower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner as the applier (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)); the sim calls PowerCmd.apply(self.hooks, self.owner, …
- `power/high_voltage/g2` — dormant — HighVoltagePower.cs participants.Contains(base.Owner) — The sim substitutes if not self.owner.is_dead (powers.py) -- recurring gap shape 8, a guard the sim changes rather than drops. The two are not the same predicate: a corpse the combat RETAINED …
- `power/illusion/g1` — dormant — IllusionPower.cs FollowUpStateId — RE-VERIFIED 2026-07-30, survives the AfterDeath fix (now faithful, see above): a public settable property with no sim analogue at all, letting an applier choose which state the revived creature resumes on (default: …
- `power/inferno/g4` — dormant — InfernoPower.cs CombatState.HittableEnemies — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). So the sim burns creatures the …
- `power/intangible/g1` — dormant — IntangiblePower.cs !CombatManager.Instance.IsInProgress -> unmodified — The sim has no combat-phase guard on any modifier hook. This is the power-level face of audit/records/seam/power_cmd.json's structural gap G6 (no IsEnding/CanReceivePowers …
- `power/juggernaut/g2` — dormant — JuggernautPower.cs CombatState.HittableEnemies and the empty check — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs), so the …
- `power/juggling/AfterCardPlayed` — dormant — The copy is rebuilt from the class rather than cloned. JugglingPower.cs is cardPlay.Card.CreateClone(), which reproduces the card's full live state; powers.py constructs type(card)() and replays card.upgrade_level upgrades onto it. Upgrade level is …
- `power/mangle/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs, which …
- `power/mangle/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has …
- `power/nemesis/g1` — dormant — NemesisPower.cs participants.Contains(base.Owner) — Replaced by if self.owner.is_dead: return (powers.py) -- the same substitution as HighVoltage's and Territorial's, and one degree worse here, because the sim's early return also SKIPS THE TOGGLE …
- `power/painful_stabs/AfterAttack` — dormant — NARROWED 2026-07-27, and a NEW residual is recorded. THE HOOK IS FIXED: PainfulStabsPower now implements after_attack(dealer, card, results) (powers.py), groups the AttackCommand results by player receiver and adds Amount * hits Wounds once per …
- `power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath` — dormant — NARROWED 2026-07-27. The retention observable is closed -- the sim's death-prevention arm now leaves the creature dead at 0 HP with retained_after_death = True (cmds.py) -- but this power still does not implement …
- `power/painful_stabs/g1` — dormant — PainfulStabsPower.cs the three AfterAttack guards — RE-OPENED 2026-07-28. Two of the three early-return conditions map; the THIRD does not, and the AfterAttack hook entry in this record already says so ("NOTE this record's guard on 'the three …
- `power/panache/AfterCardPlayed` — dormant — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs). The sim therefore aims at creatures the game considers unhittable -- a …
- `power/plow/AfterDamageReceived` — dormant — Right hook and right slot; the threshold matches exactly (target != base.Owner || result.UnblockedDamage <= 0 || target.CurrentHp > base.Amount -> return, PlowPower.cs, vs powers.py). Three divergences. (1) The sim ADDS self.owner.is_dead to the …
- `power/poison/AfterSideTurnStart` — dormant — STILL OPEN at (b) and (c). Clause (a), the SLOT, is CLOSED: PoisonPower.cs declares AfterSideTurnStart and the power is on the new after_side_turn_start dispatcher (CombatManager.cs), post-draw, so the tick no longer lands before the hand draw and a …
- `power/rampart/g3` — dormant — RampartPower.cs base.CombatState.Enemies.Where(c => c.Monster is TurretOperator) — powers.py adds and not enemy.is_gone (recurring gap shape 8, a guard the sim ADDS). C#'s CombatState.Enemies is the raw participant list and a corpse the combat …
- `power/ravenous/AfterDeath` — dormant — RE-EXECUTED 2026-07-30. The guards are exact -- target != base.Owner && target.Side == base.Owner.Side && !base.Owner.IsDead (RavenousPower.cs) maps line-for-line to powers.py -- and the effect order matches (stun the owner, then grant Strength). …
- `power/ravenous/g1` — dormant — RavenousPower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)); the sim omits it, so applier is None through hooks.modify_power_amount (cmds.py), …
- `power/reptile_trinket/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs, which …
- `power/reptile_trinket/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has …
- `power/ringing/AfterCardEnteredCombat` — dormant — The owner filter is dropped, which is harmless in single-player, but the SITE is not: C# afflicts from AfterCardEnteredCombat (RingingPower.cs) and the sim's on_card_entered_combat (hooks.py) is fired only where the sim happens to call it. Recorded …
- `power/rolling_boulder/g2` — dormant — RollingBoulderPower.cs CombatState.HittableEnemies (TestMode arm) — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting …
- `power/sandpit/AfterRemoved` — dormant — The EFFECT is right and the MECHANISM is not. C#'s AfterRemoved (SandpitPower.cs) returns early on oldOwner.IsDead || base.Target.IsDead, hides the affected creatures, and CreatureCmd.Kill(..., force: true) every one that IsPlayer or is an Osty; the …
- `power/setup_strike/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs, which …
- `power/setup_strike/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has …
- `power/shackling_potion/g4` — dormant — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, :141-144, consumed at :148-151 and :162-165) has NO sim counterpart at all. Its one caller is Misery.cs, which …
- `power/shackling_potion/g5` — dormant — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers. C# has …
- `power/shrink/AfterDeath` — dormant — The wasRemovalPrevented guard is missing. ShrinkPower.cs removes Shrink only when !wasRemovalPrevented && creature == base.Applier; the sim tests only creature is self.applier (powers.py). A prevented removal (a death whose corpse the combat keeps) …
- `power/shrink/AfterSideTurnEnd` — dormant — Two divergences in one hook. (a) The !IsInfinite guard (ShrinkPower.cs, i.e. Amount >= 0) is spelled self.amount > 0 on both sim legs (powers.py,1394); those agree only because Amount == 0 is unreachable (ShouldRemoveDueToAmount removes at exactly …
- `power/shrink/AllowNegative` — dormant — ShrinkPower.cs declares AllowNegative => true; the sim's ShrinkPower never sets allow_negative, so it inherits False from Power (powers.py). That changes ShouldRemoveDueToAmount (PowerModel.cs): C# removes an AllowNegative power only at EXACTLY 0 …
- `power/skittish/AfterSideTurnEnd` — dormant — NARROWED 2026-07-27. THE SLOT HALF IS CLOSED: the reset is now after_player_turn_end (powers.py), the sim's Hook.AfterTurnEnd slot (combat.py / CombatManager.cs). WHAT REMAINS is the side test: SkittishPower.cs acts only when side != …
- `power/slippery/ModifyHpLostAfterOsty` — dormant — The formula is exact: target != base.Owner -> amount, amount < 1m -> amount, else 1m (SlipperyPower.cs) vs powers.py. The BeforeOsty/AfterOsty phase collapse is already resolved as faithful by damage_pipeline (Osty redirection is waived, so its …
- `power/sloth/BeforeCardPlayed` — dormant — WRONG SIDE OF THE PLAY. C# increments the counter in BeforeCardPlayed (SlothPower.cs), i.e. before the card resolves; the sim increments in on_card_played, after. The sim HAS the right slot -- before_card_played (combat.py), which …
- `power/slow/ModifyDamageMultiplicative` — dormant — The factor matches (1m + 0.1m * SlowAmount at SlowPower.cs vs 1.0 + 0.1 * self._cards_this_turn at powers.py) and target != base.Owner -> 1m matches, but the POWERED test does not: C# is props.IsPoweredAttack() (SlowPower.cs) and the sim is card is …
- `power/speed_potion/g4` — dormant — TemporaryDexterityPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the wrapper's internal stat …
- `power/speed_potion/g5` — dormant — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers. C# has five readers; Rend, Sleight of Flesh …
- `power/speed_potion/g8` — dormant — The Dexterity leg's own observable consequence, as distinct from the family's slot verdict — RE-DERIVED 2026-07-26 (review fix pass). Stated separately so the AfterSideTurnEnd verdict above is not read as more proven than it is, and re-labelled from …
- `power/strength/g3` — dormant — Sign-aware power typing on a negative Strength application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGATIVE amount, because …
- `power/suck/AfterAttack` — dormant — RE-VERIFIED 2026-07-30, residual unchanged, enumeration re-executed against today's tree. THE HOOK IS FIXED: SuckPower implements after_attack(dealer, card, results) (powers.py), the sim's Hook.AfterAttack bracket, and hooks.after_attack hands it …
- `power/suck/g2` — dormant — Counting GROUPS with unblocked damage, not individual results — RE-VERIFIED 2026-07-30. C#'s num counts outer lists (per-hit result groups) in which ANY result had unblocked damage, so a single AoE hit that connects with three creatures counts 1. …
- `power/surprise/AfterDeath` — dormant — Right hook and the right two spawns (CreatureCmd.Add<SneakyGremlin> then <FatGremlin>, SurprisePower.cs, vs powers.py in the same order, which matters because it fixes the enemy-list indices). The gap is the THIEVERY TRANSFER. C# iterates …
- `power/surrounded/AfterDeath` — dormant — The logic matches SurroundedPower.cs -- skip when the dead creature is on the owner's own side, then, if every remaining hittable enemy carries the SAME marker power, re-face on hittableEnemies[0] -- but the sim reads [e for e in combat.enemies if …
- `power/surrounded/ModifyDamageMultiplicative` — dormant — The arithmetic and the facing logic are exact -- dealer == null -> 1m, target != base.Owner -> 1m, then 1.5x only if the dealer holds the marker power OPPOSITE the facing (SurroundedPower.cs vs powers.py), and 1.5 is dyadic so hook_dispatch G9 does …
- `power/surrounded/g1` — dormant — SurroundedPower.cs !wasRemovalPrevented — Absent from powers.py, which tests only the side. C# skips the re-facing entirely when a death's REMOVAL was prevented (the creature is still there, so the board did not change); the sim re-runs its all(...) …
- `power/swipe/BeforeDeath` — dormant — HOOK SLOT: C# is BeforeDeath, fired at CreatureCmd.cs **before** Hook.ShouldDie and therefore before any death prevention; the sim uses hooks.on_death, fired at cmds.py only on the branch where should_die returned True. Two consequences. (1) A …
- `power/tangled/AfterApplied` — dormant — The sim adds a guard C# does not have, and it changes the outcome. TangledPower.cs afflicts EVERY Attack card with Entangled unconditionally -- there is no Affliction == null test, unlike its own AfterCardEnteredCombat at :34 and unlike Ringing's …
- `power/tender/AfterCardPlayed` — dormant — The applier is dropped. TenderPower.cs applies Strength and Dexterity -1 with applier: base.Applier -- the creature that applied Tender -- and silent: true; powers.py calls PowerCmd.apply with no applier at all. DORMANT but with a real route: …
- `power/tender/AfterSideTurnEnd` — dormant — NARROWED 2026-07-27, RE-OPENED 2026-07-28: the SLOT fix landed, the APPLIER defect this entry used to carry verbatim did not, and the flip dropped its text. CLOSED (the slot): the player-side leg moved off the sim's Hook.BeforeTurnEnd slot …
- `power/territorial/g1` — dormant — TerritorialPower.cs applier: base.Owner — MISSING applier=. C# passes base.Owner as the applier (PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)); the sim calls PowerCmd.apply(self.hooks, self.owner, …
- `power/territorial/g2` — dormant — TerritorialPower.cs participants.Contains(base.Owner) — Same substitution as HighVoltagePower's: the sim tests not self.owner.is_dead (powers.py) where C# tests side participation, which a retained corpse still satisfies. Identical mechanism, …
- `power/the_bomb/g2` — dormant — TheBombPower.cs / :56 CombatState.HittableEnemies — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs), so the sim aims at …
- `power/unmovable/ModifyBlockMultiplicative` — dormant — NARROWED 2026-07-27. DIVERGENCE (b) IS CLOSED: on_card_played now fires once per replay iteration (combat.py, inside for play_index in range(play_count)), so a doubled block card consumes the allowance twice, matching UnmovablePower.cs's …
- `power/vigor/ModifyDamageAdditive` — dormant — The sim keeps only the FIRST of C#'s four guards. C# (VigorPower.cs) tests, in order: base.Owner != dealer (present, powers.py), !props.IsPoweredAttack() (present structurally -- cmds.py only runs the additive family for powered damage), …
- `power/vital_spark/AfterPowerAmountChanged` — dormant — C# re-syncs every Tainted affliction's Amount to the power's new Amount from AfterPowerAmountChanged with a power != this guard (VitalSparkPower.cs), so it fires on ANY amount change -- a stack, a decrement, or an Unsettling-Lamp-doubled …
- `power/vital_spark/AfterRemoved` — dormant — C#'s AfterRemoved clears every Tainted affliction on EVERY removal path (VitalSparkPower.cs, guarded by oldOwner.CombatState == null); the sim hangs the same sweep on on_death filtered to the owner (powers.py) and then calls self._expire(). So the …
- `power/vital_spark/BeforeCombatStart` — dormant — SETTLED 2026-07-30 (round 11), by execution -- the inherited framing ('C#'s CardCmd.Afflict overwrites') is IMPRECISE and corrected here, not merely re-cited (CardCmd.cs does NOT overwrite): card.Affliction == null applies fresh; if the card already …
- `power/vulnerable/ModifyDamageMultiplicative` — dormant — The base multiplier and both ported modifiers are right, but the value is computed in FLOAT where C# uses DECIMAL, which puts this hook inside hook_dispatch gap G9's blast radius. C# reads DamageIncrease = 1.5m from the DynamicVar …
- `power/vulnerable/g3` — dormant — CrueltyPower.cs target == base.Owner -> unmodified — Cruelty's own self-exclusion is dropped. C# skips the Cruelty bonus when the Vulnerable target IS the Cruelty holder; powers.py reads dealer.powers.get('cruelty') with no such test, so a Cruelty …
- `power/vulnerable/g4` — dormant — VulnerablePower.cs DebilitatePower leg — DebilitatePower is not ported (grep -c DebilitatePower sts2_rl/powers.py returns 0), so the third link of C#'s modifier chain has no sim counterpart. Per binding rule 1 an unported C# side is a DORMANT gap, …
- `power/weak/ModifyDamageMultiplicative` — dormant — The sim returns the bare literal 0.75 and has no modifier chain at all, where WeakPower.cs threads DamageDecrease = 0.75m through PaperKrane (the TARGET's relic, -0.15m) and then DebilitatePower. Neither is ported -- ls sts2_rl/relics/ | grep -i …
- `power/withering_presence/AfterCardPlayed` — dormant — The mechanism is right -- count the target player's card plays down from 6, add a Wither to HAND at 0, reset to 6 -- and the Wither's upgrade matching is preserved (aeonglass.MatchWitherToUpgradeCount(wither) at WitheringPresencePower.cs vs …

## 3B. `card` — 40 single-site mechanisms

The card tier's families — `card/_unplayable_cost`, `card/_printed_vars` and
`card/_is_dead_early_return` — are in Tier 2. `OnPlay` entries are the card's
own effect diverging; `ctor` and `CanonicalVars` entries that are not in a
family are one-off value-model divergences. **The card tier has no live entry
at all**, which is the strongest such claim in the queue and the one most
worth attacking next.

- `card/anointed/g2` — dormant — cards are moved to the hand with CardPileCmd.Add(cards, PileType.Hand) (Anointed.cs) vs direct list mutation — The sim pops each card out of player.draw_pile and appends to player.hand in place (colorless_skills.py) instead of routing through a …
- `card/apotheosis/g1` — dormant — the allCard != this self-exclusion, and whether the two AllCards sets are the same set (Apotheosis.cs) — C# PlayerCombatState.AllCards is AllPiles.SelectMany(p => p.Cards) (PlayerCombatState.cs) over Hand, Draw, Discard, Exhaust AND Play …
- `card/beat_down/g2` — dormant — target selection for AnyEnemy attacks: C# rolls Rng.CombatTargets.NextItem(CombatState.HittableEnemies) in BeatDown itself and passes it to AutoPlay; the sim lets auto_play_card roll (BeatDown.cs) — The stream is right on both sides -- …
- `card/breakthrough/g1` — dormant — the enemy loop skips on enemy.is_dead, not enemy.is_gone (breakthrough.py) — Every other AoE card in the sim filters on not e.is_gone (conflagration, shockwave, omnislice, sword_boomerang, rip_and_tear -- see py audit/tools/card_probes.py …
- `card/brightest_flame/g1` — dormant — CROSS-RECORD DISAGREEMENT (rule 3): CreatureCmd.LoseMaxHp(..., isFromCard: true) is seam gap G6, which labels itself DORMANT; this card makes it LIVE — The seam's VERDICT (gap) is not disputed and is not re-verdicted here -- only its liveness label …
- `card/conflagration/OnPlay` — dormant — Damage per hit, hit count, target set and the OUTER loop order are all faithful: DamageCmd.Attack(2).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState) (Conflagration.cs) runs for (i = 0; i < attackCount; i++) with the target list …
- `card/crimson_mantle/g1` — dormant — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (CrimsonMantle.cs vs crimson_mantle.py) — PowerCmd.Apply<T> returns null in three documented cases (PowerCmd.cs, 68-87): combat is ending, …
- `card/disintegration/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (Disintegration.cs) has no counterpart: the sim leaves can_be_generated_in_combat at its True default and instead turns OFF a DIFFERENT flag, can_be_generated_by_modifiers, which Disintegration.cs …
- `card/disintegration/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); Disintegration.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the same shape as card/beckon, …
- `card/dramatic_entrance/OnPlay` — dormant — The damage, the target set and the single hit are all faithful: DamageCmd.Attack(11).FromCard(this).TargetingAllOpponents(CombatState) (DramaticEntrance.cs) hits every living opponent once, and the sim's framework routing calls on_play once per …
- `card/enlightenment/g1` — dormant — reduceOnly is evaluated LAZILY at cost-calculation time, so C# registers the modifier on EVERY hand card including those already at cost 0 or 1; the sim continues past them (Enlightenment.cs vs event_cards.py) — LocalCostModifier.IsReduceOnly is …
- `card/expect_a_fight/g1` — dormant — the sim skips the gain entirely when there are no Attacks in hand (if attacks > 0, expect_a_fight.py); C# calls GainEnergy(0) — PlayerCmd.GainEnergy(0, ...) (ExpectAFight.cs) adds nothing but still runs the engine's gain path; the sim skips the call …
- `card/exterminate/OnPlay` — dormant — Damage per hit, hit count, target set and the hits-outer/enemies-inner loop order are all faithful against DamageCmd.Attack(3).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState) (Exterminate.cs) -- AttackCommand runs for (i = 0; i < …
- `card/frantic_escape/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (FranticEscape.cs) has no counterpart: the sim leaves can_be_generated_in_combat at its True default and instead turns off can_be_generated_by_modifiers, which FranticEscape.cs does not override …
- `card/havoc/g2` — dormant — forceExhaust: true is reproduced by appending to the exhaust pile directly (havoc.py) — C# sets item.ExhaustOnNextPlay = forceExhaust (CardPileCmd.cs) and lets the play pipeline route the card to the exhaust pile, which means the card passes through …
- `card/howl_from_beyond/OnPlay` — dormant — The damage and the single hit per enemy are faithful against DamageCmd.Attack(16).FromCard(this).TargetingAllOpponents(CombatState) (HowlFromBeyond.cs), and leaving handles_own_routing False is correct for a one-hit AoE -- the framework filters on …
- `card/inferno/g1` — dormant — C# skips IncrementSelfDamage when Apply returns NULL; the sim increments whenever the power is present (Inferno.cs vs inferno.py) — Identical to card/crimson_mantle's guard and carrying the same verdict (rule 3): PowerCmd.Apply<T> returns null when …
- `card/lantern_key/ModifyNextEvent` — dormant — if (2 != Owner.RunState.CurrentActIndex) return currentEvent; return ModelDb.Event<WarHistorianRepy>(); (LanternKey.cs) redirects the next act-3 event to War Historian Repy -- the payoff the Lantern Key quest exists for. The sim's Card class exposes …
- `card/mad_science/GainsBlock` — dormant — public override bool GainsBlock => TinkerTimeType == CardType.Skill (MadScience.cs) is TYPE-DEPENDENT, and the sim never sets gains_block at all -- not in the class body and not in configure (mad_science.py, which sets card_type, target_type and …
- `card/mind_rot/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (MindRot.cs) has no counterpart; the sim leaves can_be_generated_in_combat True and turns off a different flag that MindRot.cs does not override. Identical to card/disintegration's and …
- `card/mind_rot/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); MindRot.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the same shape as card/beckon, which …
- `card/neows_fury/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (NeowsFury.cs) has no can_be_generated_in_combat = False counterpart; the sim's comment says the ANCIENT rarity already keeps it out of pool_card_ids. That is true today, so the OUTCOME matches -- …
- `card/neows_fury/OnPlay` — dormant — Attack first, then the hand-size-capped selection: Math.Min(Cards.IntValue, CardPile.MaxCardsInHand - Hand.Cards.Count) (NeowsFury.cs) == min(self._cards, PlayerCombatState.MAX_HAND_SIZE - len(ctx.player.hand)), with both skipping everything when …
- `card/neows_fury/g1` — dormant — the chosen cards are moved with CardPileCmd.Add(list, PileType.Hand) in C# (NeowsFury.cs) and by direct list mutation in the sim (neows_fury.py) — The sim pops the chosen cards out of player.discard_pile and appends them to player.hand in place …
- `card/omnislice/g1` — dormant — the sim returns early when nothing got through (if dealt <= 0: return, colorless_attacks.py); C# proceeds whenever the DamageResult is non-null (Omnislice.cs) — C# proceeds whenever the DamageResult is non-null (Omnislice.cs) and would splash a …
- `card/pacts_end/OnPlay` — dormant — The gate and the damage are faithful: CanDealDamage is CardPile.GetCards(Owner, PileType.Exhaust).Count() >= Cards.IntValue (PactsEnd.cs) == if len(ctx.player.exhaust_pile) < self._required_exhausted: return, and the whole play is a no-op below the …
- `card/pillage/g1` — dormant — the sim identifies the drawn card as player.hand[-1] (pillage.py) where C# uses the value the single-card Draw overload returns — C#'s single-card CardPileCmd.Draw overload RETURNS the card it drew (Pillage.cs) and the type test reads that value; …
- `card/primal_force/OnPlay` — dormant — The candidate set, the per-card upgrade and the index-preserving replacement are all faithful. C# selects Hand.Cards.Where(c => c != null && c.IsTransformable && c.Type == CardType.Attack) (PrimalForce.cs) and the sim's if card.card_type != …
- `card/purity/OnPlay` — dormant — The candidate set and the effect are faithful: CardSelectCmd.FromHand(..., filter: null, source: this) over the whole hand then CardCmd.Exhaust on each (Purity.cs) == CardSelectCmd.from_hand(ctx.hooks, ctx.player, 'exhaust', count=self._cards) then …
- `card/rend/g1` — dormant — the ITemporaryPower exclusion is approximated by a single class (colorless_attacks.py) — C#'s ShouldCountPower is power.TypeForCurrentAmount == PowerType.Debuff && !(power is ITemporaryPower) (Rend.cs). The sim reproduces the SIGN-AWARE half well -- …
- `card/sloth/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false has no counterpart: the sim's shared _ChoosableCurse base leaves can_be_generated_in_combat True and instead turns off can_be_generated_by_modifiers (knowledge_curses.py), which the C# card does …
- `card/sloth/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); Sloth.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status. Same mechanism and same verdict as …
- `card/stomp/OnPlay` — dormant — The damage, the single hit per enemy and the target set are faithful against DamageCmd.Attack(12).FromCard(this).TargetingAllOpponents(CombatState) (Stomp.cs), and leaving handles_own_routing False is correct for a one-hit AoE -- the framework …
- `card/the_bomb/g1` — dormant — C# dereferences the Apply result WITHOUT a null check; the sim re-fetches by id and skips on None (TheBomb.cs vs colorless_skills.py) — This is the INVERSE of card/crimson_mantle's and card/inferno's ?. finding: those two use the null-conditional …
- `card/thunderclap/OnPlay` — dormant — The TWO-PASS structure is faithful and is the point of the card: C# resolves the whole attack first (DamageCmd.Attack(4).FromCard(this).TargetingAllOpponents(CombatState), Thunderclap.cs) and only then applies Vulnerable to …
- `card/thunderclap/g1` — dormant — the sim continues rather than breaking when an enemy is gone in the damage pass, and re-checks ctx.player.is_dead between the passes (thunderclap.py) — Two behaviours are bundled here and only one is the source's. C#'s AttackCommand does skip …
- `card/toric_toughness/g1` — dormant — C# skips SetBlock when Apply returns NULL via ?.; the sim re-fetches by id and skips on None (ToricToughness.cs vs event_cards.py) — Same mechanism and same verdict as card/crimson_mantle's and card/inferno's guards (rule 3): PowerCmd.Apply<T> …
- `card/waste_away/CanBeGeneratedInCombat` — dormant — public override bool CanBeGeneratedInCombat => false (WasteAway.cs) has no counterpart; the sim leaves can_be_generated_in_combat True and turns off a different flag that WasteAway.cs does not override (C# leaves it => true, CardModel.cs). Two …
- `card/waste_away/g1` — dormant — the sim marks the card is_playable = False (knowledge_curses.py); WasteAway.cs declares NO Unplayable keyword — C# gives this Status no CanonicalKeywords at all, so in the game it is a PLAYABLE no-effect Status -- the shape card/beckon, card/slimed, …
- `card/whirlwind/OnPlay` — dormant — The X-value plumbing, the hit count and the hits-outer/enemies-inner loop order are all faithful: WithHitCount(ResolveEnergyXValue()) on TargetingAllOpponents(CombatState) (Whirlwind.cs, 42-45) == for _ in range(self.captured_x) with a per-hit …

## 3C. `event` — 8 single-site mechanisms

The event tier's `EV-n` mechanisms are closed except `event/EV-3`, which is in
Tier 2. The two live event mechanisms are in Tier 1. These are the per-event
findings that no `EV-n` covers.

- `event/EV-11` — dormant — EV-11: BARGAIN_BIN's Common pull (WelcomeToWongos.cs) and GenerateInitialOptions' Rare pull (:80) calls run.pull_relic_from_front (run.py), which scans the merged bag for the first relic of the asked rarity passing the filter and, on no match, pops …
- `event/crystal_sphere/CalculateVars` — dormant — SETTLED 2026-07-29 (round 11). This entry's own text said it inherits the DEFERRED-PORT guard's verdict; the brief for this pass asked which of two readings is correct -- 'the event is stubbed off, so the sub-entries are dormant' or 'the stub itself …
- `event/hungry_for_mushrooms/g3` — dormant — BigMushroom's +20 Max HP pickup effect is implemented on the EVENT, not on the relic. BigMushroom.cs AfterObtained calls CreatureCmd.GainMaxHp(MaxHpVar 20) — relics/big_mushroom.py has NO after_obtained override -- only modify_hand_draw -- and …
- `event/neow/g8` — dormant — the RUN MODIFIERS branch is not ported. Neow.cs is a whole second mode: when RunState.Modifiers is non-empty the relic offer is REPLACED by one option per modifier that returns a GenerateNeowOption delegate, presented one at a time through …
- `event/ranwid_the_elder/g10` — dormant — BR-relic_trader (blast radius): the grab-bag-runs-dry state. RanwidTheElder.cs, :121 and :131 call RelicFactory.PullNextRelicFromFront(base.Owner).ToMutable() with no null check at all, so an empty bag is an NRE in the source — ALREADY RECORDED as …
- `event/relic_trader/g5` — dormant — GenerateInitialOptions gates each option on OwnedRelics.Count ALONE (RelicTrader.cs), and Trade then indexes NewRelics at the same position (RelicTrader.cs) — events/relic_trader.py gates on min(len(self._owned), len(self._new)). The extra …
- `event/vakuu/g5` — dormant — UNIT GAP (dormant): Distinguished Cape's -9 Max HP is implemented on the EVENT OPTION instead of on the relic. DistinguishedCape.cs's AfterObtained() runs CreatureCmd.LoseMaxHp(..., DynamicVars.HpLoss = 9, isFromCard: false) and only then adds the 3 …
- `event/welcome_to_wongos/g8` — dormant — CheckObtainWongoBadge (WelcomeToWongos.cs) is not ported: the sim never grants WongoCustomerAppreciationBadge, and it tracks points on an ad-hoc attribute instead of run state — The badge is awarded when SaveManager.Instance.Progress.WongoPoints % …

## 3D. `relic` — 150 single-site mechanisms

The relic tier's recurring families are written out above: `relic/_stub` and
`relic/_auto_keep` in Tier 1, and `relic/_is_allowed`,
`relic/_reward_late_pass` and `relic/_combat_reset` in Tier 2A. The rest
resolve to a mechanism a seam record already owns (`hook_dispatch/G3`,
`damage_pipeline/G3`, `turn_structure/G13`). Everything below stands alone:
one relic, one finding.

This is by far the largest single-site block in the queue, and the honest
reading is that **the relic tier's gap density is genuinely higher than the
other content tiers'.** Relics reach into every subsystem, so a relic record
is the first place a shared-machinery divergence shows up.

- `relic/anchor/g3` — dormant — N3: ordering against other BeforeCombatStart listeners — C# grants Anchor's block at step 3 (Hook.BeforeCombatStart, before StartTurn); the sim grants it at step 14's equivalent (the AfterBlockCleared loop, well inside turn-1 setup). Any effect that …
- `relic/archaic_tooth/AfterObtained` — dormant — Rollup of guards G1 and G2 per binding rule 4, RE-EXECUTED 2026-07-30 (round 11) against today's code rather than inherited. The transform itself is right -- first deck card whose id is a TranscendenceUpgrades key (ArchaicTooth.cs vs …
- `relic/archaic_tooth/g1` — dormant — G1 (DORMANT): C# carries the upgrade with a single if (starterCard.IsUpgraded) CardCmd.Upgrade(cardModel) (ArchaicTooth.cs); the sim loops for _ in range(original.upgrade_level) (archaic_tooth.py) — C# grants exactly ONE upgrade level regardless of …
- `relic/archaic_tooth/g2` — dormant — G2 (DORMANT): the sim adds a can_enchant(transformed) condition C# does not have, and MOVES the enchantment instead of cloning it (archaic_tooth.py vs ArchaicTooth.cs) — C# clones the enchantment …
- `relic/bag_of_marbles/BeforeSideTurnStart` — dormant — RE-EXECUTED 2026-07-30 (round 11). The HOOK SLOT (G1) is CLOSED and CONFIRMED, not merely narrated: test/test_turn_start_split.py::test_each_relic_listens_on_the_hook_it_overrides[bag_of_marbles-before_side_turn_start] passes today, and the relic's …
- `relic/bag_of_marbles/g2` — dormant — G2 (DORMANT): combatState.HittableEnemies (BagOfMarbles.cs) vs the sim's living_enemies() (bag_of_marbles.py) — C# targets Enemies.Where(e => e.IsHittable) (CombatState.cs), and IsHittable is !IsDead && Hook.ShouldAllowHitting(CombatState, this) …
- `relic/bag_of_preparation/g1` — dormant — N1: the chain's out-parameter modifiers and the AfterModifyingHandDraw companion event (CombatManager.cs, turn_structure step 20) — C# collects which listeners changed the draw count and fires Hook.AfterModifyingHandDraw over them; the sim's …
- `relic/belt_buckle/AfterObtained` — dormant — BeltBuckle.cs applies the Dexterity immediately if the relic is picked up DURING a combat with no potions held. The sim's port defines only on_combat_start and on_potion_used, so a Belt Buckle obtained mid-combat grants nothing until the next combat …
- `relic/belt_buckle/AfterPotionDiscarded` — dormant — The mirror of AfterPotionProcured: BeltBuckle.cs RE-APPLIES the Dexterity when discarding leaves the player potionless mid-combat. The sim implements on_potion_used but not a discard analogue, so the two ways of emptying the belt behave differently …
- `relic/bing_bong/AfterCardChangedPiles` — dormant — Rollup of guard G1 per binding rule 4. The core is right -- the deck-pile filter, the anti-recursion skip set, and the bottom-of-deck placement all match -- but C#'s clonedBy == null clause has no sim counterpart. DORMANT, RE-VERIFIED 2026-07-30 …
- `relic/booming_conch/AfterSideTurnStart` — dormant — DORMANT. Rollup of guard G2 per binding rule 4 (round 11 re-settle): G1, the hook-SLOT divergence, is STALE -- confirmed CLOSED by execution, not just by the prior narrowing's prose. player.py calls _setup_player_turn() (which performs the turn-1 …
- `relic/booming_conch/g2` — dormant — G2 (DORMANT): C# grants the energy through PlayerCmd.GainEnergy, which runs Hook.ModifyEnergyGain and Hook.AfterModifyingEnergyGain; the sim assigns player.energy directly (booming_conch.py) — STILL OPEN, re-executed round 11: …
- `relic/brilliant_scarf/TryModifyEnergyCostInCombatLate` — dormant — NARROWED 2026-07-27. The phase half (G2) is CLOSED: the port now overrides modify_card_energy_cost_late (sts2_rl/relics/brilliant_scarf.py) and HookSystem._each runs the Late pass as its own complete walk (sts2_rl/hooks.py, 153-180). WHAT REMAINS is …
- `relic/brilliant_scarf/g3` — dormant — G3 (DORMANT): the sim's modify_card_energy_cost drops ShouldModifyCost's owner check and its Hand/Play pile check (BrilliantScarf.cs) — C# refuses to modify a cost unless the card's owner is the relic's owner AND the card is currently in the Hand or …
- `relic/byrdpip/AfterObtained` — dormant — Rollup of guards G1 and G3 per binding rule 4. The deck half of the Byrdonis Egg -> Byrd Swoop transform is faithful; the combat-pile half (G1) and the mid-combat SummonPet call (G3) are dropped. DORMANT overall -- both halves settle to unreachable …
- `relic/byrdpip/BeforeCombatStart` — dormant — Byrdpip.cs summons the pet at the start of EVERY combat. The port has no on_combat_start. Carries guard G3's verdict; see G3 for why the omission is observationally inert today. DORMANT, enumerated independently of G3's own four readings: the sim's …
- `relic/byrdpip/HasUponPickupEffect` — dormant — Byrdpip.cs declares HasUponPickupEffect => true and the sim's Relic base has the exact field for it (relics/base.py), which fourteen other ports set. Byrdpip leaves it at the False default. DORMANT (executed -- py audit/tools/relic_probes.py …
- `relic/byrdpip/SpawnsPets` — dormant — Byrdpip.cs declares SpawnsPets => true; relics/base.py has the field and the port leaves it False. DORMANT, enumerated: git grep -n spawns_pets sts2_rl/*.py sts2_rl/**/*.py (excluding .pyc) returns exactly two non-declaration hits in the whole sim …
- `relic/byrdpip/g1` — dormant — G1 (DORMANT): the transform covers the deck only, not the combat piles — Byrdpip.cs collects every ByrdonisEgg from the Deck pile and, if (CombatManager.Instance.IsInProgress), ALSO from Owner.PlayerCombatState.AllCards -- i.e. a Byrdonis Egg …
- `relic/charons_ashes/AfterCardExhausted` — dormant — Rollup of guard G1 per binding rule 4 (G3, the batched-vs-sequential dispatch, carries its own deliberate-divergence verdict and needs no live label). DORMANT, enumerated: of the two guard-level divergences this hook rolls up, only G1 (target set: …
- `relic/charons_ashes/g1` — dormant — G1 (DORMANT): HittableEnemies vs living_enemies() — One verdict per mechanism (binding rule 3): this is the same call-site divergence audit/records/relic/bag_of_marbles.json records as its guard G2, with the same verdict. C# targets Enemies.Where(e …
- `relic/claws/AfterObtained` — dormant — RE-REGENERATED 2026-07-30 (the prior rollup of guards G1, G2 and G5 was stale: G1 was closed 'faithful' 2026-07-29 (round 7) and G5 is deliberate-divergence, not a gap -- neither is open any more). WHAT REMAINS is guard G2 alone, and it is still …
- `relic/claws/g2` — dormant — G2 (DORMANT): C# removes every original first and then appends the replacements in DECK-INDEX order; the sim removes and appends one card at a time in SELECTION order — MECHANISM: CardCmd.Transform(IEnumerable<CardTransformation>, rng) collects each …
- `relic/crossbow/g3` — dormant — G3 (DORMANT): CardFactory.FilterForCombat also drops CardRarity.Event (CardFactory.cs); the sim's pool_card_ids (cards/pool.py) drops only Basic and Ancient — MECHANISM: C# filters the Attack list through FilterForCombat, whose predicate is …
- `relic/darkstone_periapt/AfterCardChangedPiles` — dormant — NARROWED 2026-07-28. Rollup of guard G2 (DORMANT) per binding rule 4; G1's half is CLOSED. CLOSED (G1): the out-of-combat TRANSFORM path no longer writes the deck silently. sts2_rl/run.py runs Hook.ModifyCardBeingAddedToDeck over every relic before …
- `relic/darkstone_periapt/g2` — dormant — G2 (DORMANT): C# fires AfterCardChangedPiles for a card entering PileType.Deck at ANY time, including mid-combat; the sim's after_card_added_to_deck exists only on the out-of-combat RunState.add_card path — MECHANISM: CardPileCmd.cs and :683 …
- `relic/daughter_of_the_wind/g2` — dormant — G2 (DORMANT): C# yields no listeners to a combat hook dispatched after the combat has started ending; the sim has no such gate, so a LETHAL Attack still grants its 1 Block — MECHANISM: Hook.IterateCombatHookListeners (Hook.cs) yields nothing once …
- `relic/demon_tongue/g2` — dormant — G2 (DORMANT): C# heals result.UnblockedDamage, which EXCLUDES OverkillDamage; the sim heals the raw hp_lost, which includes it — MECHANISM: DamageResult.cs documents UnblockedDamage as the damage the target received after blocking and OverkillDamage …
- `relic/dusty_tome/AfterObtained` — dormant — Rollup of guards G1 (the unguarded Card.upgrade, dormant), G2 (the lazy re-roll, LIVE on the runner path) and N2 (the added HasUponPickupEffect declaration) per binding rule 4. The core effect is faithful and executed: …
- `relic/dusty_tome/g1` — dormant — G1 (DORMANT): CardCmd.Upgrade(card) skips a card whose IsUpgradable is false (DustyTome.cs); dusty_tome.py's card.upgrade() is a bare upgrade_level += 1 with no guard (PROMPT.md class 14) — MECHANISM: CardCmd.Upgrade filters on IsUpgradable == …
- `relic/dusty_tome/g6` — dormant — N2: the sim ADDS has_upon_pickup_effect = True (dusty_tome.py) where DustyTome.cs declares no HasUponPickupEffect override — MECHANISM: RelicModel.HasUponPickupEffect defaults to false and DustyTome does not override it -- contrast …
- `relic/electric_shrymp/g4` — dormant — N3: run.select_cards falls back to self.rng.sample when no card_selector is installed (run.py), where C# opens a player-choice screen and draws no RNG at all — PROMPT.md bug class 16's second half at an out-of-combat site: C#'s …
- `relic/ember_tea/g1` — dormant — G1 (DORMANT): C#'s AfterRoomEntered runs strictly BEFORE every BeforeCombatStart listener; the sim's on_combat_start runs interleaved with them in relic-registration order — MECHANISM: CombatRoom.cs calls CombatManager.SetUpCombat and then …
- `relic/empty_cage/AfterObtained` — dormant — Rollup of guard N2 per binding rule 4. The count (CardsVar(2), EmptyCage.cs, vs CARDS = 2, empty_cage.py), the candidate filter (N1) and the removal itself all match -- executed: a fresh run's 10-card deck goes to 8. The only divergence is that the …
- `relic/empty_cage/g2` — dormant — N2: run.select_cards falls back to self.rng.sample when no card_selector is installed (run.py), where the game opens a removal screen and draws no RNG — Same mechanism and same verdict as relic/electric_shrymp guard N3 in this batch (binding rule …
- `relic/fake_anchor/g3` — dormant — N3 (DORMANT): the ordering window -- C# grants the block at turn_structure step 3, the sim at the step-14 AfterBlockCleared loop, and anything between the two that reads player Block sees 4 in C# and 0 in the sim — Same mechanism as relic/anchor's …
- `relic/fake_snecko_eye/AfterObtained` — dormant — MECHANISM: FakeSneckoEye.cs applies the Confused power immediately when the relic is picked up if CombatManager.Instance.IsInProgress, so a Fake Snecko Eye obtained mid-combat confuses you for the rest of that fight. The sim implements no …
- `relic/fake_strike_dummy/g2` — dormant — G1 (DORMANT): C#'s fourth clause is if (dealer != Owner.Creature && cardSource.Owner != Owner) return 0; -- an AND of two negatives, i.e. fire when EITHER holds; the sim requires dealer is self.player alone (fake_strike_dummy.py) — MECHANISM: …
- `relic/festive_popper/g1` — dormant — G1 (DORMANT): C#'s hook is AfterPlayerTurnStart, turn_structure step 22; the sim's on_player_turn_started is the step-23 AfterSideTurnStart slot — MECHANISM: step 22 is await CardPileCmd.Draw(...) then await Hook.AfterPlayerTurnStart(state, …
- `relic/festive_popper/g2` — dormant — G2 (DORMANT): combatState.HittableEnemies (FestivePopper.cs) vs the sim's living_enemies() (festive_popper.py) — Identical mechanism to relic/bag_of_marbles guard G2 and carried with the same gap verdict per binding rule 3, at another turn-1 …
- `relic/forgotten_soul/AfterCardExhausted` — dormant — Rollup of guard G1 per binding rule 4. Every number and stream matches -- DamageVar(1m, ValueProp.Unpowered) (ForgottenSoul.cs) is DAMAGE = 1 with DamageProps.NON_CARD_UNPOWERED (= ValueProp.UNPOWERED, valueprops.py), the dealer is the player's own …
- `relic/fragrant_mushroom/AfterObtained` — dormant — NARROWED 2026-07-27. The sort-key half (G1) is CLOSED: sts2_rl/relics/fragrant_mushroom.py now passes key=_compare_to_key (sts2_rl/player.py, the UPPERCASE ordinal compare) to actmap.stable_shuffle over run.rng_set.niche. WHAT REMAINS is guard G2, …
- `relic/fragrant_mushroom/g2` — dormant — G2 (DORMANT): CreatureCmd.Damage(ThrowingPlayerChoiceContext, Owner.Creature, HpLoss.BaseValue, Unblockable|Unpowered, null, null) (FragrantMushroom.cs) vs run.lose_hp(15) (fragrant_mushroom.py) — MECHANISM: the source routes the 15 through the full …
- `relic/fresnel_lens/g2` — dormant — G2: EnchantCard clones the card first (base.Owner.RunState.CloneCard(card), FresnelLens.cs) and enchants the CLONE, then hands it back via option.ModifyCard(...) / out newCard — PROMPT.md bug class 17 (shallow clones) applies to whoever implements …
- `relic/frozen_egg/g3` — dormant — G3: the sim upgrades the ORIGINAL card object where C# substitutes an upgraded CloneCard (FrozenEgg.cs; EggRelicHelper.cs) — PROMPT.md bug class 17 at the egg relics' two sites. CardScope.CloneCard -> ClonePreservingMutability (CardModel.cs) carries …
- `relic/fur_coat/AfterCreatureAddedToCombat` — dormant — DORMANT, settled by execution 2026-07-30 (round 11). Two components, both non-live today. (a) NOT STALE, RE-VERIFIED: C# fires Hook.AfterCreatureAddedToCombat for the STARTING creatures too -- CombatManager.StartCombatInternal loops foreach …
- `relic/fur_coat/g3` — dormant — G3 (DORMANT): CreatureCmd.SetCurrentHp(item, 1m) (FurCoat.cs, 139) vs the sim's raw enemy.hp = 1 (fur_coat.py, 87) — MECHANISM: CreatureCmd.SetCurrentHp (CreatureCmd.cs) does three things the raw assignment does not -- it fires …
- `relic/gambling_chip/g1` — dormant — G1 (DORMANT): CardCmd.DiscardAndDraw auto-plays every discarded card that IsSlyThisTurn, AFTER the draw (CardCmd.cs); the sim's loop has no Sly concept — MECHANISM: DiscardAndDraw collects if (card.IsSlyThisTurn) slyCards.Add(card) while discarding …
- `relic/gambling_chip/g2` — dormant — G2 (DORMANT): each discard goes through CardPileCmd.Add(card, discardPile) in C# (CardCmd.cs) where the sim mutates the two lists directly (gambling_chip.py) — MECHANISM: CardPileCmd.Add runs the game's pile-change machinery -- Hook.ShouldAddToDeck …
- `relic/ghost_seed/AfterCardEnteredCombat` — dormant — Rollup of guard G2 per binding rule 4. The predicate and the effect match -- GhostSeed.cs applies CardKeyword.Ethereal to any card CanAffect accepts -- but C#'s CardCmd.ApplyKeyword adds a keyword whose SOURCE is tracked (KeywordSources.Local), …
- `relic/ghost_seed/AfterRoomEntered` — dormant — See guard G1. GhostSeed.cs filters room is CombatRoom and then sweeps Owner.PlayerCombatState.AllCards; the sim iterates self.player.all_cards at on_combat_start. C#'s AfterRoomEntered for a combat room is dispatched at CombatRoom.cs, AFTER …
- `relic/ghost_seed/g1` — dormant — G1 (DORMANT): the sweep runs at BeforeCombatStart in the sim and at AfterRoomEntered in C#, two dispatch points earlier — MECHANISM: the C# order is SetUpCombat -> Hook.AfterRoomEntered (CombatRoom.cs) -> AfterCombatRoomLoaded -> …
- `relic/ghost_seed/g2` — dormant — G2 (DORMANT): !card.GetKeywordsWithSources(KeywordSources.Local).Contains(Ethereal) (GhostSeed.cs) vs the sim's single not card.is_ethereal boolean — MECHANISM: C# tracks WHERE each keyword came from, and CanAffect only refuses a card that already …
- `relic/girya/AfterRoomEntered` — dormant — See guard G2. Girya.cs applies StrengthPower equal to TimesLifted when TimesLifted > 0 && room is CombatRoom; girya.py does the same at combat start, two dispatch points later (C#'s AfterRoomEntered for a combat room fires at CombatRoom.cs, before …
- `relic/girya/g2` — dormant — G2 (DORMANT): the Strength lands at BeforeCombatStart in the sim and at AfterRoomEntered in C#, two dispatch points earlier -- and the sim's slot is interleaved with other relics' on_combat_start by registration order where C#'s always precedes …
- `relic/glitter/g1` — dormant — G1 (DORMANT): base.Owner.RunState.CloneCard(card) then CardCmd.Enchant<Glam>(card2, 1m) then cardReward.ModifyCard(card2, this) (Glitter.cs) vs GlamEnchantment().attach(card) in place (glitter.py) — PROMPT.md bug class 17. CardScope.CloneCard -> …
- `relic/golden_pearl/g2` — dormant — N2 (DORMANT): PlayerCmd.GainGold's Hook.AfterGoldGained(runState, player) tail (PlayerCmd.cs) has no sim counterpart at all -- neither this relic nor the sim's Relic base declares an after_gold_gained hook — MECHANISM: every gold gain in the game …
- `relic/gorget/g4` — dormant — N4 (DORMANT): PlatingPower's own port diverges on WHERE it decays -- the sim decays from on_player_turn_start (pre-draw) where PlatingPower.cs decays from AfterSideTurnStart (post-draw) — MECHANISM: PlatingPower.cs decrements in AfterSideTurnStart …
- `relic/gremlin_horn/AfterDeath` — dormant — Rollup of guards G1 and G2 per binding rule 4. The relic's own body is exact -- GremlinHorn.cs's side check, EnergyVar(1) and CardsVar(1) map one-for-one onto gremlin_horn.py, and EXECUTED (py audit/tools/relic_probes_b07.py horn-death) an enemy …
- `relic/gremlin_horn/g2` — dormant — G2 (DORMANT): the sim resolves death INSIDE the damage pipeline, before the dealer's post-damage event; C# defers Kill() until after AfterDamageGiven and AfterDamageReceived have run for every target of the batch — MECHANISM: CreatureCmd.cs runs …
- `relic/hand_drill/g1` — dormant — G1 (DORMANT): C# orders AfterBlockBroken listeners BEFORE AfterDamageGiven listeners for the same damage result; the sim puts Hand Drill on the same event as the AfterBlockBroken listener and lets registration order decide — MECHANISM: …
- `relic/hand_drill/g2` — dormant — G2 (DORMANT): the C# guard is dealer == base.Owner.Creature || dealer?.PetOwner == base.Owner -- the port drops the PET arm entirely (hand_drill.py is dealer is not self.player) — MECHANISM: HandDrill.cs credits the owner's PET's damage to the …
- `relic/happy_flower/g3` — dormant — N3 (DORMANT): PlayerCmd.GainEnergy's Hook.AfterModifyingEnergyGain companion event and its finalAmount > 0 gate (PlayerCmd.cs) have no counterpart in the sim's EnergyCmd.gain (cmds.py) — MECHANISM: C# folds Hook.ModifyEnergyGain, then fires …
- `relic/hefty_tablet/AfterObtained` — dormant — NARROWED at round 11: two of this rollup's three named guards are closed. G1 (candidate pool: FilterForCombat vs GetUnlockedCards) was closed 2026-07-29 (round 7) -- EXECUTED (this pass): hefty_tablet.py, 34-37 now calls …
- `relic/hefty_tablet/g2` — dormant — G2 (DORMANT): CardFactory.CreateForReward runs Hook.TryModifyCardRewardOptions on the three cards unless CardCreationFlags.NoModifyHooks is set, and HeftyTablet sets only NoUpgradeRoll -- the port calls no such hook — MECHANISM: CardFactory.cs folds …
- `relic/ice_cream/g2` — dormant — N2 (DORMANT): the sim calls modify_max_energy BEFORE should_reset_energy; C# evaluates ShouldPlayerResetEnergy first and only then reads MaxEnergy inside the chosen branch — This is audit/records/seam/turn_structure.json gap at spec step 17, …
- `relic/intimidating_helmet/g3` — dormant — N1 (DORMANT): the SLOT -- C# fires BeforeCardPlayed after the card has been added to the Play pile and after GeneratePlayCount; the sim fires on_energy_spent immediately after deducting the energy, before the card leaves the hand — MECHANISM: …
- `relic/jeweled_mask/g3` — dormant — N3 (DORMANT): SetToFreeThisTurn is EndOfTurn | WhenPlayed in C#; the sim's _free_this_turn expires only at the next turn start — MECHANISM: CardModel.SetToFreeThisTurn (CardModel.cs) adds a LocalCostModifier with …
- `relic/jeweled_mask/g4` — dormant — N4 (DORMANT): the port moves the card with two list operations (draw_pile.remove / hand.append, jeweled_mask.py) instead of the sim's CardPileCmd, so it bypasses the hand cap — MECHANISM: C# calls CardPileCmd.Add(cardModel, PileType.Hand) …
- `relic/kusarigama/AfterCardPlayed` — dormant — DORMANT, re-settled round 11 (guard G2 re-derived from today's callers, not trusted from prior prose). NARROWED 2026-07-27. The per-Replay half (G1) is CLOSED: CombatState._resolve_card_play fires on_card_played inside the play-count loop …
- `relic/kusarigama/g2` — dormant — G2 (DORMANT): Owner.Creature.CombatState.HittableEnemies (Kusarigama.cs) vs the sim's living_enemies() (kusarigama.py) — RE-VERIFIED round 11 (the entry was not re-derived, only trusted, at the last pass -- and its cited line numbers had drifted): …
- `relic/lantern/g1` — dormant — N1: PlayerCmd.GainEnergy(amount, player) (Lantern.cs) vs EnergyCmd.gain(self.hooks, player, 1) (lantern.py) -- the missing AfterModifyingEnergyGain companion and the finalAmount > 0 / IsEnding guards — PlayerCmd.GainEnergy does five things: bail on …
- `relic/lasting_candy/AfterCombatEnd` — dormant — LastingCandy.cs is the CombatsSeen++ counter that decides 'every other combat' (IsInTriggeringCombat = CombatsSeen > 0 && CombatsSeen % 2 == 0, LastingCandy.cs). The sim's Relic base HAS the hook -- after_combat_end(run, room_type) (relics/base.py), …
- `relic/lava_lamp/g2` — dormant — G2 (DORMANT, but the fix must not reproduce it): C# UPGRADES A CLONE -- RunState.CloneCard(card) then CardCmd.Upgrade(card2) then cardReward.ModifyCard(card2, this) (LavaLamp.cs) -- and the sim has no clone helper — PROMPT.md bug class 17. …
- `relic/leafy_poultice/g3` — dormant — N1 (DORMANT): CreatureCmd.LoseMaxHp routes the excess current HP through the FULL damage pipeline; RunState.lose_max_hp just clamps — CreatureCmd.LoseMaxHp (src/Core/Commands/CreatureCmd.cs) computes an UNFLOORED newMaxHp = MaxHp - amount and, when …
- `relic/letter_opener/AfterCardPlayed` — dormant — NARROWED 2026-07-27. The per-Replay half (G1) is CLOSED: CombatState._resolve_card_play fires on_card_played inside the play-count loop (sts2_rl/combat.py, 597-600). WHAT REMAINS is guard G2, the target set: LetterOpener.cs damages HittableEnemies …
- `relic/letter_opener/g2` — dormant — G2 (DORMANT): Owner.Creature.CombatState.HittableEnemies (LetterOpener.cs) vs the sim's living_enemies() (letter_opener.py) — C# damages Enemies.Where(e => e.IsHittable) -- !IsDead && Hook.ShouldAllowHitting(...) (src/Core/Combat/CombatState.cs; …
- `relic/lost_coffer/g4` — dormant — N2: CardCreationFlags.IsCardReward is set by CardReward's constructor (CardReward.cs); the sim has no card-creation flag concept at all — The flag exists so that relics which affect card REWARDS only (CardCreationFlags.cs names Prismatic Gem and …
- `relic/meat_cleaver/TryModifyRestSiteOptions` — dormant — RE-EXECUTED 2026-07-30 (round 11). Guard G1 is NOT part of the gap -- it is deliberate-divergence (the sim omits a disabled option rather than adding one greyed out; same reachable action set, since the sim has no rest-site UI to show the grey row). …
- `relic/meat_cleaver/g1` — dormant — G2 (DORMANT): CookRestSiteOption's card-removal screen is Cancelable = true and a cancel makes the whole option a no-op (CookRestSiteOption.cs); the sim's cook always removes 2 cards and always grants the 9 Max HP — MECHANISM: …
- `relic/miniature_cannon/g1` — dormant — G1 (DORMANT): if (dealer != base.Owner.Creature && cardSource.Owner != base.Owner) return 0 (MiniatureCannon.cs) is an AND, so C# adds the damage when EITHER the dealer is the owner OR the card belongs to the owner; the port keeps only the first …
- `relic/miniature_tent/g1` — dormant — G1 (DORMANT): C# aggregates this hook over runState.IterateHookListeners(null) -- deck cards, powers and modifiers as well as relics -- and the sim iterates self.relics only — MECHANISM: Hook.ShouldDisableRemainingRestSiteOptions (Hook.cs) walks …
- `relic/molten_egg/ModifyMerchantCardCreationResults` — dormant — Same body as the reward path in C# too -- MoltenEgg.cs calls the identical EggRelicHelper.UpgradeValidCards (no CurrentUpgradeLevel check anywhere in that helper, EggRelicHelper.cs) -- and notably has NO NoHookUpgrades check, so the delegation is …
- `relic/molten_egg/g4` — dormant — G4 (DORMANT): the sim applies Molten Egg's already-upgraded refusal to ALL THREE paths; C# applies it ONLY to the deck-add path, because EggRelicHelper.UpgradeValidCards has no upgrade-level check — MECHANISM: the reward and merchant paths both go …
- `relic/molten_egg/g9` — dormant — N4: the sim has ONE modify_card_reward_options pass where C# runs TryModifyCardRewardOptions and then TryModifyCardRewardOptions**Late** as two complete passes — MECHANISM: Hook.TryModifyCardRewardOptions (Hook.cs) walks every listener's non-Late …
- `relic/new_leaf/AfterObtained` — dormant — Rollup of guards N1 and G1 per binding rule 4. Count, selection prompt and deck placement are all faithful; the named Niche RNG stream is dropped (N1, live for RNG parity) and the candidate list omits C#'s Quest-card exclusion (G1, dormant).
- `relic/new_leaf/g2` — dormant — G1 (DORMANT): CardSelectCmd.FromDeckForTransformation also excludes Quest cards; run.transformable_cards() filters only Eternal — MECHANISM: CardSelectCmd.FromDeckForTransformation (CardSelectCmd.cs) builds its candidate list as Cards.Where(c => …
- `relic/nunchaku/g5` — dormant — N4: PlayerCmd.GainEnergy (Nunchaku.cs) runs Hook.ModifyEnergyGain, then Hook.AfterModifyingEnergyGain, then a finalAmount > 0 check (PlayerCmd.cs); EnergyCmd.gain (cmds.py) runs the modify chain and adds unconditionally — This is the …
- `relic/old_coin/g3` — dormant — N1: PlayerCmd.GainGold's companion event Hook.AfterModifyingGoldGained (PlayerCmd.cs) has no sim counterpart — This is the missing-AfterModifying-companion family that audit/records/seam/power_cmd.json gap G4 records and that …
- `relic/paels_legion/g3` — dormant — G3 (DORMANT): the sim adds a target is not self.player check that C#'s ModifyBlockMultiplicative does not have — MECHANISM: PaelsLegion.cs checks props, cardSource and cardSource.Owner -- and NOTHING about the target. So in C#, a card played by the …
- `relic/paper_phrog/ModifyVulnerableMultiplier` — dormant — DORMANT (round 11 re-settle, both guards re-executed against today's content rather than trusted). Rollup of guards G1 and N2 per binding rule 4. NOT a Hook override: PaperPhrog.cs is a plain public method, and its ONE caller is …
- `relic/paper_phrog/g1` — dormant — G1 (DORMANT): C# consults the dealer's phrog ONCE by direct lookup; the sim runs a hook chain over every combat listener, so N copies of the relic would each add 0.25 — RE-SETTLED round 11: the open question this guard left ('whether Toy Box can …
- `relic/paper_phrog/g3` — dormant — N2 (DORMANT): if (target == base.Owner.Creature) return amount; (PaperPhrog.cs) -- no bonus when the phrog's own owner is the Vulnerable creature; the sim checks only the dealer — RE-EXECUTED round 11: MECHANISM: paper_phrog.py is if dealer is …
- `relic/parrying_shield/AfterSideTurnEnd` — dormant — NARROWED 2026-07-28 (adversarial pass). Rollup of guard G1 only, and G1 is now DORMANT rather than LIVE; guard G2 is CLOSED. maps_to should be re-pointed to after_player_turn_end (parrying_shield.py), dispatched by HookSystem.after_player_turn_end …
- `relic/pen_nib/AfterCardPlayed` — dormant — RE-EXECUTED 2026-07-30 (round 11). Guard G1 (the per-iteration/per-play replay mismatch) is CLOSED -- combat.py now fires on_card_played once per play_index, so a replayed 10th Attack unmarks after its FIRST iteration exactly as CardModel.cs does …
- `relic/pen_nib/g3` — dormant — G3 (DORMANT): C# skips Hook.AfterCardPlayed entirely when the play ended the combat (CardModel.cs gates on CombatManager.IsInProgress) while combat.py always fires it, so a game-side 10th Attack that lands the killing blow stays MARKED and the sim's …
- `relic/philosophers_stone/AfterCreatureAddedToCombat` — dormant — Rollup of guard G1 per binding rule 4. The effect and the constant are right -- 1 Strength on each joiner, executed at b12-stone: a mid-combat SpinyToad spawn comes in at Strength(1) -- and the two hooks provably cannot double-apply (guard N1). The …
- `relic/philosophers_stone/g1` — dormant — G1 (DORMANT): C# skips any creature on the OWNER's SIDE (PhilosophersStone.cs); the sim skips only the player OBJECT (philosophers_stone.py), so a player-side creature that is not the player would be strengthened in the sim and not in the game — …
- `relic/prismatic_gem/g1` — dormant — G1 (DORMANT): the four early-return clauses of ModifyCardRewardCreationOptions (PrismaticGem.cs) select exactly the case the waiver above depends on -- and one of them is the residual risk — MECHANISM: C# bails on NoCardPoolModifications, on …
- `relic/prismatic_gem/g2` — dormant — N1: modify_max_energy is evaluated BEFORE should_reset_energy in the sim and inside the chosen branch in C# — This is audit/records/seam/turn_structure.json step 17's finding, not a new one: player.py calls modify_max_energy first and …
- `relic/punch_dagger/AfterObtained` — dormant — NARROWED 2026-07-27. The stub PREMISE finding is discharged -- the docstring no longer rests on a false claim -- but the relic is STILL a no-op, and the reason is now written into the port. sts2_rl/relics/punch_dagger.py's docstring now names the …
- `relic/punch_dagger/CanonicalVars` — dormant — NARROWED 2026-07-27. The stub PREMISE finding is discharged -- the docstring no longer rests on a false claim -- but the relic is STILL a no-op, and the reason is now written into the port. sts2_rl/relics/punch_dagger.py's docstring now names the …
- `relic/rainbow_ring/AfterCardPlayed` — dormant — RE-EXECUTED 2026-07-30 (round 11). The port still latches BEFORE the two PowerCmd.apply calls (sts2_rl/relics/rainbow_ring.py: self._activated = True is set, then Strength then Dexterity are applied), where C# increments ActivationCountThisTurn only …
- `relic/rainbow_ring/g1` — dormant — G1 (DORMANT): C# increments ActivationCountThisTurn AFTER awaiting both PowerCmd.Apply calls (RainbowRing.cs); the sim sets _activated = True BEFORE them (rainbow_ring.py) — MECHANISM: C#'s guard is ActivationCountThisTurn < 1 (RainbowRing.cs) and …
- `relic/red_skull/g3` — dormant — N2 (DORMANT): C#'s AfterCurrentHpChanged has NO creature == Owner.Creature check (RedSkull.cs); the sim gates on creature is self.player (red_skull.py) — MECHANISM: C# re-evaluates the owner's threshold whenever ANY creature's HP changes during …
- `relic/ruined_helmet/AfterModifyingPowerAmountReceived` — dormant — LABELLED (round 11): DORMANT, matching guard G3's own already-established dormancy (this hooks-level rollup summarizes G3 alone). RuinedHelmet.cs is a SEPARATE C# hook that fires only for listeners whose Try returned true (Hook.cs collects them into …
- `relic/ruined_helmet/TryModifyPowerAmountReceived` — dormant — LABELLED (round 11): DORMANT overall -- both cited guards are dormant, re-checked rather than inherited. The four C# clauses are reproduced exactly -- canonicalPower is StrengthPower, target == Owner.Creature, amount <= 0, UsedThisCombat …
- `relic/ruined_helmet/g2` — dormant — G2 (DORMANT): C#'s RECEIVED-side predicate chain is a separately-sequenced phase; the sim has one flat registration-order chain — This is audit/records/seam/power_cmd.json gap G3 at the site that record already names -- it cites …
- `relic/ruined_helmet/g3` — dormant — G3 (DORMANT): the 'mark used' side effect is hand-inlined into the modifier, so it fires at a point C# would not have reached — This is audit/records/seam/power_cmd.json gap G4 at its own site -- that record names …
- `relic/sai/g1` — dormant — G1 (DORMANT at this site, LIVE as a mechanism): AfterSideTurnStart is C#'s SECOND turn-start pass and the sim runs one flat walk (seam guard G12, PROMPT.md class 25) — MECHANISM: Hook.AfterSideTurnStart runs every listener's AfterSideTurnStart and …
- `relic/seal_of_gold/g2` — dormant — G2 (DORMANT at this site, LIVE as a mechanism): AfterSideTurnStart is C#'s second turn-start pass and the sim runs one flat walk (seam guard G12, PROMPT.md class 25) — MECHANISM as recorded for relic/sai in this batch: Hook.AfterSideTurnStart is a …
- `relic/self_forming_clay/g3` — dormant — N3: the sim has no SelfFormingClayPower at all, so the pending Block is not a visible, stackable, removable power on the player — MECHANISM: grep -rn SelfFormingClay sts2_rl/powers.py returns nothing -- the sim models the effect as a private int on …
- `relic/shovel/TryModifyRestSiteOptions` — dormant — Rollup of guard G2 per binding rule 4. The DIG option's effect matches -- RelicCmd.Obtain(RelicFactory.PullNextRelicFromFront(Owner)) (DigRestSiteOption.cs) maps to run.obtain_relic_from_grab_bag() (shovel.py), and the default overload's …
- `relic/shovel/g2` — dormant — G2 (DORMANT): the sim refuses to OFFER the DIG option when the grab bag is empty; C# always offers it and grants RelicFactory.FallbackRelic instead — MECHANISM: Shovel.TryModifyRestSiteOptions adds new DigRestSiteOption(player) unconditionally …
- `relic/signet_ring/g2` — dormant — N2: Hook.AfterModifyingGoldGained (PlayerCmd.cs) has no sim counterpart — MECHANISM: C#'s gold pipeline is the same two-phase shape as its damage and power pipelines -- ModifyGoldGained collects the listeners that changed the amount, then …
- `relic/silver_crucible/ShouldGenerateTreasure` — dormant — Rollup of guard G3 per binding rule 4. The predicate matches (TreasureRoomsEntered > 1, SilverCrucible.cs) and so does the all-must-agree dispatcher (if (!item.ShouldGenerateTreasure(player)) return false, Hook.cs). What diverges is WHAT the gate …
- `relic/silver_crucible/g3` — dormant — G3 (DORMANT): a suppressed treasure room still pays out Spoils Map in the sim — MECHANISM: C# reaches the Spoils Map payout only from INSIDE the gated reward routine -- OneOffSynchronizer.DoTreasureRoomRewards opens with if …
- `relic/sling_of_courage/AfterRoomEntered` — dormant — Rollup of guard N1 per binding rule 4. SlingOfCourage.cs applies PowerVar<StrengthPower>(2) from AfterRoomEntered when room.RoomType == RoomType.Elite, and for a CombatRoom that hook fires after CombatManager.SetUpCombat and BEFORE …
- `relic/sling_of_courage/g1` — dormant — N1 (DORMANT gap, matching audit/records/relic/girya.json G2): the slot move -- C# guarantees the Strength lands BEFORE every BeforeCombatStart listener; the sim puts it INSIDE that pass — MECHANISM: for a CombatRoom, Hook.AfterRoomEntered fires at …
- `relic/snecko_eye/AfterObtained` — dormant — SneckoEye.cs applies the Confused power immediately when the relic is picked up DURING a combat (if (CombatManager.Instance.IsInProgress) await ApplyPower()). snecko_eye.py defines only on_combat_start and modify_hand_draw, so a Snecko Eye obtained …
- `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — dormant — RE-REGENERATED 2026-07-30 (the prior rollup of guards G1, G2 and G3 was stale: G1 was RECONCILED to faithful 2026-07-28 -- the listener-order fix that closed it landed and the record's per-guard entry was updated, but this hooks-level summary was …
- `relic/spiked_gauntlets/g2` — dormant — G2 (DORMANT at this site): the hook has a PLAIN pass and a LATE pass and the sim has neither — Hook.ModifyEnergyCostInCombat runs TWO complete listener passes -- every TryModifyEnergyCostInCombat, then every TryModifyEnergyCostInCombatLate …
- `relic/spiked_gauntlets/g3` — dormant — G3 (DORMANT): the sim drops the card.Owner.Creature != base.Owner.Creature guard AND the dispatcher's originalCost < 0 X-cost bail; it adds a final max(0, cost) clamp C# does not have — Three differences in the same collapse, checked side by side …
- `relic/stone_calendar/BeforeSideTurnEnd` — dormant — LABELLED (round 11): G1 is CLOSED (2026-07-27, the four-phase listener walk is real -- re-confirmed today via py -m pytest test/test_hook_order.py -k "orichalcum_snapshots_block_before_other_turn_end_listeners or …
- `relic/stone_calendar/g2` — dormant — G2 (DORMANT): combatState.HittableEnemies (StoneCalendar.cs) vs the sim's living_enemies() (stone_calendar.py) — Same mechanism and therefore the same verdict as relic/bag_of_marbles guard G2 (binding rule 3): C# targets Enemies.Where(e => …
- `relic/stone_cracker/AfterRoomEntered` — dormant — DORMANT (round 11 re-settle -- explicit liveness label added; the mechanism itself was already correctly narrowed and is re-confirmed, not changed). NARROWED 2026-07-27. The shuffle half (G1) is CLOSED: sts2_rl/relics/stone_cracker.py now feeds …
- `relic/stone_cracker/g2` — dormant — G2 (DORMANT): the C# hook is AfterRoomEntered, which runs one full dispatch BEFORE Hook.BeforeCombatStart; the port uses on_combat_start — RE-VERIFIED round 11, unchanged: POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py …
- `relic/stone_humidifier/AfterRestSiteHeal` — dormant — DORMANT, settled by execution 2026-07-30 (round 11). Rollup of guard G1 per binding rule 4, which this record already labels dormant and unchanged. RE-VERIFIED: grep -n mend sts2_rl/run.py sts2_rl/rest_site.py finds no Mend rest-site option anywhere …
- `relic/stone_humidifier/g1` — dormant — G1 (DORMANT): Hook.AfterRestSiteHeal has TWO dispatch sites in C# and the sim ports only one — MECHANISM: an executed grep for AfterRestSiteHeal over the decompiled source finds two callers outside the relic models -- HealRestSiteOption.cs …
- `relic/strike_dummy/g2` — dormant — G2 (DORMANT): C# grants the +3 when EITHER the dealer is the owner's creature OR the Strike card BELONGS to the owner; the port requires the dealer — MECHANISM: StrikeDummy.cs is if (dealer != base.Owner.Creature && cardSource.Owner != base.Owner) …
- `relic/sword_of_jade/AfterRoomEntered` — dormant — Rollup of guards G1 and N1 per binding rule 4. The power, the amount and the target are right and executed; the hook SITE is one dispatch later than C#'s and the applier identity differs. N1 (applier identity) is faithful, not an open gap -- the …
- `relic/sword_of_jade/g1` — dormant — G1 (DORMANT): the C# hook is AfterRoomEntered, which runs a full dispatch BEFORE Hook.BeforeCombatStart; the port uses on_combat_start — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE ported relics whose …
- `relic/tea_of_discourtesy/g2` — dormant — G2 (DORMANT): the port skips CardPileCmd._enter_combat, so the two generated Dazed are never registered as combat hook listeners and AfterCardEnteredCombat never fires for them — MECHANISM: C# creates the card with combatState.CreateCard<T>(player) …
- `relic/the_boot/g2` — dormant — G2 (DORMANT): C# gates on props.IsPoweredAttack(); the sim's modify_hp_lost signature carries no props at all, so the port substitutes card is None or card.is_unpowered — MECHANISM: ValuePropExtensions.IsPoweredAttack (ValuePropExtensions.cs) is …
- `relic/touch_of_orobas/AfterObtained` — dormant — Rollup of guards G1 and N4 per binding rule 4. The core behaviour is right and executed: the starter relic is replaced IN PLACE by its refinement and the replacement's own after_obtained runs. What the port drops from RelicCmd.Replace -> Obtain is …
- `relic/touch_of_orobas/g2` — dormant — G1 (DORMANT): RelicCmd.Obtain strips the obtained relic from both grab bags (player.RelicGrabBag.Remove(relic) and runState.SharedRelicGrabBag.Remove(relic), RelicCmd.cs) and stamps FloorAddedToDeck; the port's direct list assignment does neither — …
- `relic/toy_box/AfterCombatEnd` — dormant — Rollup of guards G2 and N1 per binding rule 4. The counter and the every-3rd-combat trigger are faithful (N1); the divergence is that RelicCmd.Melt leaves the melted relic in the player's relic list as an inert entry and the port deletes it from …
- `relic/toy_box/g2` — dormant — G2 (DORMANT): RelicCmd.Melt leaves the relic in Player.Relics as an inert entry; the port removes it from run.relics entirely — MECHANISM: RelicCmd.Melt (RelicCmd.cs) is relic.Owner.MeltRelicInternal(relic); await relic.AfterRemoved(); -- the relic …
- `relic/tungsten_rod/g6` — dormant — N5: the run-level walk's listener SET -- RunState.lose_hp iterates relics only (run.py), where C#'s IterateHookListeners(null) also walks every deck card and its enchantment (RunState.cs) and the player's potions (:570) — MECHANISM: out of combat, …
- `relic/unsettling_lamp/BeforePowerAmountChanged` — dormant — LABELLED (round 11): DORMANT overall -- every guard this rollup cites is dormant, re-checked rather than inherited, and none has flipped since its own last audit. The latch is not separable from the double in the sim: C# runs seven latch guards …
- `relic/unsettling_lamp/ModifyPowerAmountGivenMultiplicative` — dormant — C# returns a MULTIPLICATIVE factor into Hook.ModifyPowerAmountGiven's two-pass fold (Hook.cs: every listener's additive contribution is summed FIRST, then every listener's multiplicative factor is applied to that sum). The sim's modify_power_amount …
- `relic/unsettling_lamp/g3` — dormant — G2 (MANDATED, DORMANT): sign-aware power.GetTypeForAmount(amount) != PowerType.Debuff (UnsettlingLamp.cs and :124) vs the sim's static power_cls.power_type != PowerType.DEBUFF plus an amount <= 0 early bail — MECHANISM: PowerModel.GetTypeForAmount …
- `relic/unsettling_lamp/g5` — dormant — G3 (DORMANT): C#'s ModifyPowerAmountGivenMultiplicative has NO target-side guard and NO giver guard -- only the LATCH checks target.Side == Owner.Creature.Side and applier != Owner.Creature -- whereas the sim applies both checks to the doubling as …
- `relic/unsettling_lamp/g6` — dormant — G4 (DORMANT): C#'s cardSource is a per-APPLICATION argument; the sim substitutes an ambient _in_flight card set by before_card_played and cleared by on_card_played, so a nested card play inside the triggering card's resolution clears it — MECHANISM: …
- `relic/vajra/g1` — dormant — G1 (DORMANT): nothing observes the player's Strength in the window between C#'s AfterRoomEntered and the sim's on_combat_start, so the phase difference has no observable today — MECHANISM: as above -- one full combat-setup phase separates the two …
- `relic/vambrace/g6` — dormant — N3 / g6: the port's docstring claims 'The multiplier hook stays stateless (safe for previews); the one-shot flag is set from the real on_block_gained event' (vambrace.py) — DORMANT, settled by execution 2026-07-30 (round 11) -- RE-VERIFIED, not …
- `relic/vexing_puzzlebox/g4` — dormant — N3: cardModel.SetToFreeThisTurn() (VexingPuzzlebox.cs) vs card.set_free_this_turn() (vexing_puzzlebox.py) — C#'s SetToFreeThisTurn is EnergyCost.SetThisTurnOrUntilPlayed(0) plus SetStarCostThisTurn(0) (CardModel.cs). The sim's set_free_this_turn …
- `relic/wing_charm/g3` — dormant — N2 (DORMANT while the port is empty, LIVE the moment G1 is fixed): base.Owner.RunState.CloneCard(...) is a full model clone and the sim has no clone helper — NARROWED 2026-07-27. The dormancy premise has changed: the port is no longer empty -- …
- `relic/winged_boots/g3` — dormant — N3: the sim charges only the FIRST relic whose should_allow_free_travel() is True and then breaks (run.py); C# charges every AfterRoomEntered implementer independently — MECHANISM: in C# the charge is each relic's own business, so two free-travel …
- `relic/wongos_mystery_ticket/g7` — dormant — N6 (DORMANT): an exhausted relic grab bag makes the sim hand out FEWER than three relics and still spend the ticket, where C# substitutes RelicFactory.FallbackRelic and always resolves three — MECHANISM: C#'s PullNextRelicFromFront is …

## 3E. `potion` — 14 mechanisms, 26 entries

Two families and twelve further one-or-two-site mechanisms. Every one carries an
explicit `live: false` in its record — the potion tier states the boolean on
every entry, so nothing here inherits its liveness from a neighbour — and
**no potion entry is live.** `potion/_effect_bracket`, which was a 51-site
family, closed entirely.

| mechanism | sites | dormant because | goes live when |
|---|---|---|---|
| `potion/_filter_for_combat_event_rarity` | 10 | `CardFactory.FilterForCombat` drops Basic, Ancient **and Event** (`CardFactory.cs:159-162`); `cards/pool.py:108-117` drops the first two. Executed: both pools' Event buckets are empty (IRONCLAD 85→78, COLORLESS 53→50) | any Event-rarity card is added to `IRONCLAD_POOL` or `COLORLESS_POOL`. **CROSS-STREAM: the fix lands in `cards/pool.py`, which the card tier owns** — the recipe is not "edit a potion file" |
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


## 3F. Coverage anchors — the seam mechanism with no prose home

One entry, and it is not a new finding: it is a site of a mechanism described
above that a verdict flip on a neighbouring entry split out of its family,
giving it its own mechanism key. It is named here so
`py audit/tools/gap_queue.py coverage` can locate it. **The fix is its parent
mechanism's.**

| mechanism | liveness | parent family |
|---|---|---|
| `creature_card_cmds/step105` | dormant | CardSelectCmd (§2B) |

The previous round's anchor table had sixteen rows. Fifteen of them were
entries with no typed liveness; settling them either closed the entry or gave
it a home in its kind's Tier 3 block above.


---

# Dormant-trigger watch list

Every dormant gap names a concrete unported thing that would make it live.
**Anyone porting a row's trigger needs to read that row's mechanisms first** —
the port will otherwise be written against a sim seam that does not behave like
the game's. Sorted roughly by how likely the trigger is to come up. Section A
is the engine seams; **section B is the content tiers**, whose triggers are
different in kind — several are *other queue entries*, so fixing one mechanism
wakes another and the two belong in the same commit.

**A trigger can be paid without anyone noticing.** `relic/kifuda`'s G2 was on a
list like this one, its trigger was discharged in round 7, and it sat labelled
dormant for four rounds. Two rows below are known-dated in the same way and are
marked. Re-read a row before trusting it.

## A. Engine-seam triggers

| trigger — the unported thing | wakes |
|---|---|
| Any conformance replay through a card-selection / grid screen | `creature_card_cmds/N10`, `/step104`, `/step105`  |
| Porting **BufferPower** | `damage_pipeline/G2`, `hook_dispatch/G3`  |
| Porting **Malaise** or **Resonance** (negative-Strength appliers) | `power_cmd/G1`, `/G2`  |
| Porting **SovereignBlade**, **Hoarder** or **SoulFysh** (combat-pile watchers) | `creature_card_cmds/G8`  |
| Porting **Hexed**'s `AfterCardEnteredCombat` | `hook_dispatch/G6` (needs `/G1` too)  |
| Porting **SlumberingEssence** or **WellLaidPlansPower** (`BeforeFlush`); **Bookmark** (`AfterFlush`) | `turn_structure/step55`, `turn_structure/G7`  |
| Porting **any Sly card** | `creature_card_cmds/step51`, `relic/_auto_keep`'s Gambling Chip half  |
| Porting **NoEnergyGainPower**'s `AfterModifyingEnergyGain`, or **BowlerHat**/**Ectoplasm**'s `AfterModifyingGoldGained` | `damage_pipeline/G2`  |
| Porting **PaleBlueDotPower**, or any gameplay `AfterModifyingHandDraw` | `turn_structure/step20`  |
| Un-stubbing **Dragon Fruit** or **Lucky Fysh** (both ported, both inert) | `creature_card_cmds/G8`, `relic/_stub`  |
| Porting any of the **11 unclaimed C# monster hook overrides** | `hook_dispatch/G5`  |
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
| Porting a card that **plays more than one card from the draw pile** | `creature_card_cmds/N9`, `/step82`  |
| A **third `modify_power_amount` listener**, or Unsettling Lamp / Ruined Helmet widening | `power_cmd/G3`  |
| The first **side-effecting** `should_reset_energy` or `modify_max_energy` | `turn_structure/step17`  |
| A **new multi-hit / multi-target effect** that forgets the per-hit death check | `damage_pipeline/G5`  |
| Porting a second `on_damage_dealt` power | `damage_pipeline/G6`, `/step17.4`  |

Rows that left this table in round 11 because the mechanism itself closed:
in-combat transform streams, `ModifyShuffleOrder`, the gold-gain hook surface,
`Unceasing Top`/`on_hand_emptied`, the enemy-side `BeforeTurnEnd` slot, the
combat-end path's five distinctions, and `AutoPlayFromDrawPile`. The
`InstancedPerApplier` row also left — not closed, but **promoted**: it is
`power_cmd/G5`, Tier 1.

## B. Content-tier triggers

| trigger — the unported thing | wakes |
|---|---|
| **DATED — re-check before trusting.** "The prevention arm stops flooring at 1 HP" | `card/_is_dead_early_return` (5 cards). **The floor is already gone** (`cmds.py:123-136` leaves the creature dead at 0), and those five entries still read `DORMANT: the sim floors a death-prevented creature at 1 HP`. Their dormancy has not been re-derived against today's code |
| **DATED — re-check before trusting.** The same clause, for two of `creature_card_cmds/step8c`'s powers | `creature_card_cmds/step8c` |
| The first cost reader that distinguishes a `-1` base cost from `0`, or any cost modifier applied to an unplayable card and read back | `card/_unplayable_cost` (29 cards) |
| Any reader of a `PowerStackType.Single` power's `Amount`, or any content that applies one twice in a combat | `power/_stack_type_single` (16 powers) |
| A power that holds combat open **without** also preventing a death or adding a creature | `creature_card_cmds/step8c` |
| Porting a reachable applier for **Imbalanced** or **Paper Cuts** | `power/_after_damage_given_substitution` |
| Porting the **Circlet** relic, or any content that drains a whole rarity deque inside one run | `event/EV-11` |
| **Training against the sim at all** — this one is not dormant, it is live in every run and dormant only against the game | `card/_printed_vars` (23 cards, via `sts2_rl/full_env.py:488`) |
| Porting **Flyconid** onto `MachineMonster` (the codebase's preferred convention) | `monster_state_machine/G7`; the port is faithful today and the machinery raises where C# limps |
| A **second Dampen applier**, or two Magi Knights in one encounter | `monster/magi_knight/g1` |
| Any **retained corpse** on the Glory enemy side (an Illusion / Reattach / Adaptable holder) | `monster/_retained_corpse_in_scan` |
| A **third Wither source**, or porting any other `AfterCardGeneratedForCombat` implementer | `monster/aeonglass/AfterCardGeneratedForCombat` |
| Giving `Intent` a **count field**, or any consumer that reads one | `monster/_intent_count_lost` |
| Any Event-rarity card added to `IRONCLAD_POOL` or `COLORLESS_POOL` | `potion/_filter_for_combat_event_rarity` (10 entries) — **the fix lands in `cards/pool.py`, which the card tier owns** |

The row "writing the **potion** audit stream" left this table: that stream landed
2026-07-27 and the kind is fully audited.


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
5. **Relic and card *content* has no seam.** `relic/_stub` collects relics whose
   sim implementations are inert stubs with docstrings that are no longer true —
   Dragon Fruit and Lucky Fysh among them. The seam that recorded their missing
   gold-gain hook closed in round 11; the stubbed relics did not, and no seam
   owns them.
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
contradicts another record's, or its own, or the code. This class has caught
real bugs, so it is tracked; each row is **reported, not edited**, and belongs
to the stream that owns the record.

- **`card/_is_dead_early_return`'s five entries are dormant on a premise that is
  gone.** Each reads, verbatim, "DORMANT: the sim floors a death-prevented
  creature at 1 HP (`cmds.py:106-112`)". The floor was removed:
  `_resolve_death`'s prevention arm (`cmds.py:123-136`) now leaves the creature
  dead at 0 HP, and its own docstring says "the sim used to floor it at 1 HP
  here". Five entries — `card/blood_wall/g1`, `card/bloodletting/g1`,
  `card/brand/g1`, `card/hemokinesis/g1`, `card/offering/g1` — have not been
  re-derived against that. **This is the same shape as `relic/kifuda`'s G2, the
  one entry round 11 promoted from dormant to live**, and it is the most likely
  place for the next one.
- **`sts2_rl/powers.py:64-65` cites `power_cmd/G5` for the wrong C# enum.** The
  docstring uses the guard id for the sim's absence of `PowerStackType`
  (`PowerModel.cs:236`); G5 is about `PowerInstanceType` (`PowerModel.cs:144`).
  Found while settling G5, flagged rather than corrected because the settling
  wave could not edit `sts2_rl/`. `power/_stack_type_single` is PowerStackType's
  real home.
- **`events/war_historian_repy.py`'s module docstring is stale.** It says the
  event is "reached only … via a quest/room hook the sim does not model"; that
  hook (`ModifyNextEvent`) has been modelled since round 8, which is precisely
  what made `event/war_historian_repy/g2` live.
- **`hook_dispatch/G7`'s executed evidence is from a stale tree.** It records the
  stale-listener plugin run as "the whole suite (2476 passed / 30 xfailed) and
  191,270 instrumented listener calls". The suite is thousands of tests larger
  now. The conclusion may still hold — the record says the run is reproducible
  from the committed tree — but **re-run it before relying on the "only one hit"
  claim**.
- **One RE-AUDIT paragraph was pasted onto four `damage_pipeline` entries, and
  three of the four have since closed.** Steps 5, 9 and 12 are gone; guard `G2`
  still carries the byte-identical "RE-AUDIT 2026-07-25 … PARTIALLY RESOLVED"
  block whose subject is the **HpLost** variant, and it is the entry to trust.
  The lesson survives the closures: a paragraph pasted onto four entries
  described only one of them.
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
machinery's reachability from its own vantage point. Round 11's largest decay
category — the `hooks`-level rollup that summarised guards which had since
closed — is the same lesson one level up: **a summary of other entries goes
stale every time one of them moves, and nothing regenerates it.**

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
asserts that every mechanism key and every one of the 558 entries is locatable
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
