# Gap queue — every open gap, aggregated

Every `"verdict": "gap"` entry in `audit/records/**`, de-duplicated **by
mechanism** and ordered for work. Generated from the records, not transcribed.

**This file holds current state, the fix for each gap, and standing lessons —
nothing else.** Which round closed what, and when, is in the git log and in
`docs/superpowers/plans/`; it is deliberately not kept here. A closed mechanism
is deleted from this file, not annotated — if a mechanism has no gap entry left
in the records, it has no section here.

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

## Current state

| | |
|---|---|
| gap entries | **324** |
| — labelled LIVE | 0 |
| — labelled DORMANT | 324 |
| — unlabelled | 0 |
| **distinct mechanisms** | **299** |
| — with at least one live entry | **0** |
| mechanisms pinned by a `strict=True` xfail | 0 |

**2026-08-04 (stale-record sweep).** All 843 records the previous round left
STALE were re-audited (re-read against current code, not re-hashed): 954/0
invalid, 0 stale. Several verdicts flipped from `gap` to `faithful`/`waiver`
(their mechanisms are CLOSED and deleted below, per this file's own rule), and
one entry was promoted from dormant to **LIVE**: `card/mad_science/GainsBlock`
— fixed the same day, so it is closed too (see [Live gaps](#live-gaps) for the
closure record). Net: 347 → 324 entries, 322 → 299 mechanisms.
Re-derive with `py audit/tools/gap_queue.py counts` rather than trusting this
sentence.

No entry is unlabelled — but note the label usually lives in the entry's prose
tokens, not the typed `live:` key: only a minority of gap guards carry the typed
field, and `counts` reads both. **Trust the typed field over the sentence next
to it**: a record whose prose says "no longer a gap" while its `verdict` field
still reads `"gap"` counts as a real entry here, and that is the right call.

**2026-08-03 (`card/beat_down/g2` — a DORMANT label refuted by execution).**
Closed, 348 -> 347 entries and 323 -> 322 mechanisms. It is filed here rather
than in the git log because of HOW it was found: someone opened the record and
asked why it was still a gap, and whether it was really dormant. It was not.
The entry's own dormancy argument — "no such preventer is ported that fires on
an auto-played Attack" — was a claim, and a census of all **8** ported
`should_play_card` implementers says **5** can veto an auto-played Attack.
Three do it unconditionally, checking neither `auto_play` nor card type
(`SlothPower`, reached as a Knowledge Demon curse; `VelvetChoker`, a Darv event
reward; `NormalityCard`, whose own comment already said the game blocks
auto-plays in that window); two more veto an Attack carrying their affliction
(`RingingPower`, `ChainsOfBindingPower`), and neither affliction is
type-restricted. Only `ClashCard`, `EnthralledCard` (both exempt auto-plays)
and `SmoggyPower` (skills only) cannot.

Measured before the fix, three AnyEnemy Attacks in the discard pile — one
`CombatTargets` draw each in C#: baseline **3**, with `SlothPower(1)` the sim
drew **1**, with Velvet Choker at its cap **0**. That is a stream desync for
the rest of the combat. Fixed by giving `BeatDownCard.on_play` the pre-roll
BeatDown.cs:32-40 does, which is the only pre-roll `AutoPlay` caller in the
game source. **The entry had sat DORMANT since 2026-07-26 while three of the
five preventers were already ported.**

**2026-08-03 (gap-fix pass).** Every live entry the systems-tier campaign filed
earlier the same day is CLOSED — 36 entries across 10 mechanisms and 25
records, taking the queue from 384/20-live to **348/0-live**. The mechanisms
were landed whole: 16 of the 36 were DORMANT sites of the same mechanisms
(every encounter that declares a C# `Slots` row now carries it, not just the
two whose summons made it observable), per the standing lesson that a partial
port is the worst resting state. Two of the closes overturned a queue claim —
`rng_streams/G7` was a replay-harness bug rather than a stream bug, and
`run_layer/G6`'s "no fixture carries discovery history" premise was false. See
[Live gaps](#live-gaps) for both, and each record's own entry for the fix.

**The 25 touched records are deliberately left STALE, not re-hashed.** This
pass re-verified the entries it closed; it did not re-read every other entry in
those records against the changed sim files. Regenerating a hash without
re-reading is the one thing that silently destroys this pipeline's value, so
the staleness flag stands as the signal for a proper re-audit pass.

**2026-08-03 (systems-tier campaign).** Three new content kinds
(`encounter`/`affliction`/`character`) and six new seams
(`rng_streams`/`rewards`/`relic_pools`/`run_layer`/`rooms_and_map`/`potion_pipeline`)
joined the pipeline. `encounter` filed **45 gap entries, 16 of them live** —
the queue's first-ever live content entries — and five of the new seams filed
**12 more, 4 live**. Full writeup in
[Systems tier — 2026-08-03 campaign](#systems-tier--2026-08-03-campaign)
below. All 20 are now closed (above).

Per kind (records / gap entries / mechanisms anchored / live entries):

| kind | records | entries | mechanisms | live |
|---|---|---|---|---|
| `seam` | 12 | 34 | 29 | 0 |
| `power` | 138 | 90 | 89 | 0 |
| `card` | 202 | 24 | 24 | 0 |
| `event` | 65 | 7 | 7 | 0 |
| `enchantment` | 20 | 0 | 0 | 0 |
| `relic` | 260 | 137 | 132 | 0 |
| `monster` | 109 | 2 | 1 | 0 |
| `potion` | 51 | 15 | 12 | 0 |
| `encounter` | 85 | 14 | 4 | 0 |
| `affliction` | 7 | 1 | 1 | 0 |
| `character` | 5 | 0 | 0 | 0 |

Per seam record (entries / mechanisms / live entries):

| record | entries | mechanisms | live |
|---|---|---|---|
| `damage_pipeline` | 1 | 1 | 0 |
| `power_cmd` | 6 | 5 | 0 |
| `creature_card_cmds` | 9 | 7 | 0 |
| `turn_structure` | 2 | 3 | 0 |
| `hook_dispatch` | 8 | 5 | 0 |
| `monster_state_machine` | 0 | 0 | 0 |
| `rng_streams` | 1 | 1 | 0 |
| `rewards` | 1 | 1 | 0 |
| `relic_pools` | 3 | 3 | 0 |
| `potion_pipeline` | 2 | 2 | 0 |
| `run_layer` | 1 | 1 | 0 |

`rooms_and_map` still has a record but no gap entry — it is not in
`gap_queue.SEAMS` for exactly that reason (see the list's own comment); it
joins the moment it files a `verdict: "gap"`.

## Where to start

1. **[Live gaps](#live-gaps)** — currently one entry, `card/mad_science/GainsBlock`
   (found 2026-08-04). The section also holds the 2026-08-03 closing summary
   and the two findings from it worth carrying forward.
2. **[Tier 1](#tier-1--the-largest-multi-site-families)** — the multi-site
   dormant families, one fix each clearing many sites.
3. **[Tier 2](#tier-2--dormant-gaps)**, then
   **[Tier 3](#tier-3--the-long-tail)**. Dormant is not safer than live (see
   Standing lessons): the work in the dormant tail is re-executing dormancy
   claims as much as fixing code. With no live entries left, **re-execution is
   now the highest-value work in this file** — a dormancy claim that has gone
   live is invisible until someone re-runs its witness.

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

- **Read the fixture before searching the code.** `run.save`'s
  `map_point_history` has carried per-ROOM `current_hp`/`max_hp`/
  `damage_taken`/`hp_healed` (plus gold counters and the relic/event choices
  made at each point) the entire time, and `SaveOracle` already parsed the
  field for relic reconciliation. Three rounds searched a whole act for the
  89U `+6 HP` while comparing HP at three ACT boundaries; reading the per-room
  numbers put the divergence inside one boss fight in a single pass. **Before
  bisecting behaviour, check what the oracle already knows.**
- **A harness that silently resolves to nothing looks exactly like a faithful
  no-op.** `rng_streams/G7` was a REPLAY bug, not a sim bug: an unhandled
  command kind made a recorded choice resolve to "chose nothing", and the
  unconsumed command was then dispatched into an empty screen and dropped.
  Both halves failed quietly and every counter stayed green. When a divergence
  survives a clean stream audit, suspect the replay layer, not only the engine.
- **A C# `.Sort()` is NOT a stable sort, and the sim's `list.sort` is.**
  `List<T>.Sort()` is .NET's introsort: insertion sort at 16 elements or
  fewer (stable), quicksort above it (not). So a port disagrees only on ties in
  a large-enough partition — which is precisely why the divergence inside
  `StableShuffle` survived every unit test and only surfaced as a walled replay
  100+ rooms in. `dotnet_sort.dotnet_list_sort` is the port; any other `.Sort()`
  transcribed as `list.sort` carries the same latent split.
- **Name-level agreement is not identity-level agreement.** Two identical cards
  are interchangeable in play and indistinguishable in every annotation the
  recording carries, so a divergence between them is invisible to the hand and
  enemy comparators and shows up only where an IDENTITY is named — a
  `NetCombatCardDb` id. A comparator that reads display names cannot clear an
  ordering claim.
- **A green suite is not evidence of fidelity.** Four fixes have each introduced
  a *new* divergence that the full suite passed straight over — a power spending
  a stack where C# abstains, a monster dropped from its own `AfterDeath`, a
  reward screen widened by a relic C# forbids there, a killing-blow card leaving
  a pile C# leaves it in. **All four were found by reading the C#. None was
  found by a test.**
- **Tests defend bugs.** One asserted a missing status count was intended; one
  asserted a card lands in the exhaust pile where the game leaves it in Play —
  and that one was the *only* thing keeping the suite green over a real fix. A
  test asserting today's behaviour is not evidence the behaviour is right; check
  what it was written to prove.
- **When a pin and the C# disagree, the C# wins.** Four pins here have been
  wrong, and one was hiding a regression the same pass introduced.
- **Tooling defects are found by unit work, never by tool review.** If a probe
  disagrees with an execution, suspect the probe. The gap-fix pass found two
  more this way: `encounter_probes_e7.py` had no `sys.path` bootstrap and had
  never run at all (it raised `ModuleNotFoundError` on import — its
  "executed" numbers came from somewhere else), and several probes printed a
  hard-coded DIVERGENCE verdict below their computed output, so they went on
  reporting the gap after the fix landed. **A probe must derive its verdict
  from what it just executed**; the ones touched here now do.

**On dormancy**

- **A dormancy argument is worth much less than an enumeration.** "No ported
  listener can see this" is a claim; "all 13 overrides of this hook ignore the
  parameter" is a fact.
- **"No ported X can reach this" is the single most dangerous sentence in these
  records, and it is cheap to test.** `card/beat_down/g2` sat DORMANT for eight
  days on "no such preventer is ported that fires on an auto-played Attack";
  enumerating the hook's 8 implementers took one grep and found 5 that do,
  three of them unconditional. Writing the sentence costs nothing; the
  enumeration that would refute it usually costs one command. **Run it before
  you write it** — and when you inherit one, run it before you trust it.
- **Dormancy fails on its enumerations far more often than on its verdicts.** A
  4-site census was really 10. A "backstop" relied on by four entries was dead
  code, dominated by an earlier guard. A guard was closed on a consumer census
  that never listed the production driver.
- **Commands re-gate; counters do not.** A command that runs in a stale window
  is usually re-checked downstream and self-corrects. A `[SavedProperty]`
  counter incremented in that window never does — it permanently phase-shifts
  every later draw. Do not carry a dormancy argument from one to the other.
- **Dormant is not safer than live.** It is a claim about today's ported
  content, which the next port invalidates. Re-execute before trusting any
  liveness label, including a dormant one.
- **A BLOCKED-ON-DESIGN label is a hypothesis, not a finding.** Both entries
  ever carrying one turned out not to be blocked on design at all.

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
- **An "unportable" verdict needs a source sweep first.** Check the game's own
  `AutoSlay` screen handlers and the `RunReplays` command set before writing
  that something has no headless equivalent; the one verdict that claimed it was
  refuted by both.

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

- **The REPLAY HARNESS is still audited by nobody, though the act-2 wall it
  built is now gone.** `sts2_rl/conformance/**` and `sts2_rl/combat_card_db.py`
  are the oracle every liveness claim here rests on, and no record's `unit` is
  any part of it: 100 records cite `conformance/combat_driver.py` or
  `runner.py` as EXTRA sources (evidence for someone else's verdict), zero cite
  `combat_card_db.py`, and it is not even listed among the holes in
  [Behaviour in no tier's scope](#behaviour-in-no-tiers-scope). It has now
  produced **three** of this pipeline's hardest divergences: `rng_streams/G7`,
  and both halves of the 89U act-2 wall, **CLOSED 2026-08-03**:

  1. `CombatCardDb` RECONSTRUCTED ids post-draw by walking hand-then-draw,
     where the game stamps each card as it is ADDED — `NetCombatCardDb`
     subscribes to every pile's `ContentsChanged`
     (NetCombatCardDb.cs:48-58) and `CardPile.AddInternal` raises it per
     non-silent add (CardPile.cs:102-106). With Blessed Antler putting 3 Dazed
     in the draw pile at `BeforeHandDraw` (ids 23-25, all three still in the
     draw pile) and Vexing Puzzlebox adding a card to the hand after the draw
     (id 26), the reconstruction gave the drawn Dazed an early id and slid the
     Puzzlebox card in front of its siblings, so `PlayCard 26` resolved to a
     Dazed. Fixed by starting the db at the game's own instant —
     `CombatManager.SetUpCombat` runs it at CombatManager.cs:372, right after
     `PopulateCombatState` (:370) and before the opening draw — and stamping
     later cards in `CardPileCmd._enter_combat`. Act-2 `forced_combats`
     **8 -> 5**.
  2. The wall then moved to mecha_knight, and it was **NOT** "a second
     generated-card cause" as this entry previously claimed. It was
     `StableShuffle`'s stabilizing sort: `List<T>.Sort()`
     (ListExtensions.cs:22-31) is .NET's UNSTABLE introsort, and the sim used
     Python's stable `list.sort`. Two identical un-upgraded Forgotten Rituals
     compare 0 (`CardModel.CompareTo`, CardModel.cs:2242-2263) and a 20-plus-
     card turn-4 reshuffle put them in the opposite order from the game, so
     `PlayCard 12` named the twin still in the draw pile. Ported as
     `sts2_rl/dotnet_sort.py` and wired into all three stabilizing-sort sites
     (`player._shuffle_cards`, `player.stable_shuffled_cards`,
     `actmap.stable_shuffle`). Act-2 `forced_combats` **5 -> 0**.

  **Result, measured three times identically**: BOTH Ironclad seeds now pass
  the act 0-2 gate (`resync_player=False` — reaches the act-2 boss, HP and
  max-HP match at the final boundary, no stream-counter divergence), so
  `test_full_run_player_state_parity` no longer marks either seed xfail. Both
  reach `forced_combats=0`; 933T39V18D also drops to **zero** per-command
  mismatches (its Test Subject boss force-win and its room-593 `Inferno+`
  mismatch both went with the sort fix).

  **And the harness produced a FOURTH one, found by asking how converged the
  seeds really were.** 89U's 14 surviving per-command mismatches were all
  `Wither` vs `Wither+1`, and they were a COMPARATOR bug, not an engine bug:
  `Wither.Title` (Wither.cs:16-27) appends `+{FakeUpgradeLevel}`, a counter
  separate from `CurrentUpgradeLevel` — which for Wither is permanently 0
  (`MaxUpgradeLevel => 0`, :41) because the card grows through `FakeUpgrade()`
  (:60-64). `card_display_name` read `upgrade_level` alone and so could never
  render the recording's spelling, reporting a correctly fake-upgraded Wither
  as a hand divergence on every turn one was held. The tell was there in the
  numbers the whole time: HP, counters, deck, relics, gold and potions all
  matched EXACTLY while 14 "divergences" stood, which a real +3-self-damage-per
  -turn difference could not have done. Fixed in `combat_driver.py`; 89U's
  per-command mismatches **14 -> 0**, 933T unaffected.

  **Whole-run end state, both seeds, resync OFF (what the gate does not
  assert):** deck, relics, gold and potion belt all match the final
  `run.save` exactly (89U 24 cards / 18 relics / 113 gold / empty belt; 933T 34
  cards / 18 relics / 203 gold / `{1: explosive_ampoule}`), the act-2 boss
  fight IS replayed, and the only unconsumed recording commands are the 5-6
  post-boss `ProceedToNextAct` / `ChooseEventOption` lines the harness stops
  before by design. Both recordings are 3 acts (`OVERGROWTH`/`HIVE`/`GLORY`,
  `current_act_index=2`), so `stop_after_act=2` is the whole run, not a prefix.
  **On every observable the oracle carries, both Ironclad seeds are converged.**

  The one measurement that still disagrees is the resync-ON triage path:
  89U is clean there too, but **933T39V18D reports floor 47 (hp 74 vs 66,
  CombatTargets 21 vs 22), floor 49, and an act-2 boundary delta of +13** for a
  run whose unresynced end state matches exactly. Trust the gate, not the
  triage — see the two `resync_floors` items below.

  **Still open, and still nobody's unit**: the harness has no audit record, no
  seam claims it, and the third divergence class it can hide — a driver that
  silently resolves a command to nothing — has only ever been found by a
  failing replay. **A failing replay is not a gap entry in this queue and never
  has been** — `forced_combats` is counted by the runner, not filed — which is
  why none of this reads as live work.
- **Two lessons the sort fix leaves behind.** (a) A divergence that is
  invisible in play can still wall a replay: the two Forgotten Rituals are
  interchangeable in every observable respect, the recording's per-command
  `Hand:` annotations matched name-for-name the whole way, and the ONLY thing
  that noticed was a recorded `NetCombatCardDb` id. Name-level agreement is not
  identity-level agreement. (b) `List<T>.Sort()` is unstable for ties of any
  size above `IntrosortSizeThreshold` (16) and stable below it, because small
  partitions go to `InsertionSort` — which is why every small pile agreed and
  the bug survived every unit test. Any other port of a C# `.Sort()` in this
  sim has the same latent split; `dotnet_sort.dotnet_list_sort` is the fix for
  all of them.
- **RESOLVED 2026-08-04 (Task 3, revised after code review): `resync_floors`'s
  degradation was two separate capture-semantics bugs, both fixed in
  `_check_floor_state`.** `tools/oracle_semantics_probe.py` reconciled all 49
  of 933T39V18D's per-floor backup saves against the run-end save's
  `map_point_history`: 46 of 49 line up exactly with a room-ENTRY capture
  (matching the previous room's exit hp, directly or via the
  `damage_taken`/`hp_healed` arithmetic). Floor 47's backup (hp 74) matches
  NEITHER that entry value (66, confirmed twice — from history directly and
  from arithmetic) NOR the post-room value (80) NOR anything else reachable
  — a mid-room/wrong-moment capture artifact, while the live sim's own hp
  there (66) agrees with history. Floor 48's backup is a byte-duplicate of
  47's, already caught by `_is_stale_floor_save`. Fixes: (a)
  `_is_inconsistent_floor_save` excludes floor 47 the same way a stale save
  is excluded — diff and resync both suppressed — but ONLY when the LIVE SIM
  also agrees with the history-consistent reference (`run.hp` must equal one
  of the reachable values); if a future floor's backup were inconsistent AND
  the sim disagreed too, the diff is recorded normally rather than silently
  dropped (first version of this guard was oracle-only and could have
  masked a real bug — tightened after code review); (b) the final
  checkpointed floor (its backup is an entry-style capture, structurally
  incomparable to the run-END oracle DETECTORS 2/3 already check) now skips
  BOTH the diff and the resync — recording an unwinnable diff there made a
  fully-converged replay print DIVERGENCES REMAIN forever (also tightened
  after code review; the first version recorded the diff and only skipped
  the resync). Together these took 933T's DETECTOR 2 (3 stream-counter
  diffs), DETECTOR 3 (act-2 boundary +13), and DETECTOR 4 (floors 47 and 49)
  to zero — **both installed seeds now print FULLY CONVERGED**, reproduced
  twice each. Tests: `test_resync_skips_the_final_checkpointed_floor`,
  `test_floor_47_backup_save_is_excluded_as_an_inconsistent_capture`,
  `test_is_inconsistent_floor_save_requires_sim_agreement_with_history`
  (`test/test_conformance_floor_state.py`).
- **DETECTOR 3 and DETECTOR 4 compare different captures, and used to look
  inverted.** Both always print `expected` = oracle, `got` = sim
  (`runner.py` `_check_player_state` / `_check_floor_state` both construct
  `Divergence(stream, idx, expected=oracle, actual=sim)`). The 933T
  "expected 67 got 80" vs "expected 80 got 67" pair was two *oracles*
  disagreeing — the act-boundary check reads the run-END truncation save
  while the per-floor check reads the floor-N backup save, and the run-end
  save's own `map_point_history` is a third oracle that disagrees with the
  backup at floor 47 (66 vs 74). Detector headers now name their capture,
  `test/test_converge_triage_format.py` pins the printed sense, and
  `tools/oracle_semantics_probe.py` reconciles the three oracles per floor.
- **RESOLVED — per-room state oracles are built: DETECTOR 5.**
  `SaveOracle.room_stats_by_act` parses `map_point_history`'s `player_stats`
  per map point (`current_hp`, `max_hp`, `damage_taken`, `hp_healed`, the four
  gold deltas, `max_hp_gained`/`_lost`); `runner.py`'s `_check_room_stats`
  (report-only, never resyncs) diffs the sim's post-room hp/max_hp/gold
  against it every room, streamed as `room_hp`/`room_max_hp`/`room_gold` with
  `command_index = run.total_floor`. It localized 933T's residual act-2 HP
  story to a single room (act 2 room 12, the elite fight) before Task 3's fix
  landed. Task 3 added one more guard: the run's terminal point (the final
  act's boss room) captures an internally-inconsistent all-zero
  `player_stats` block (current_hp=max_hp=current_gold=0) in every installed
  recording — a run-end capture artifact, not a real 0-HP moment — so
  `_check_room_stats` keeps an unconditional all-zero fast path plus a
  general reachability guard (unreachable from the previous point via
  `current_hp + damage_taken - hp_healed`) that ALSO requires the live sim's
  hp to agree with that previous point before skipping (tightened after code
  review — a sim-blind version could mask a real divergence on some future
  recording), closing the last standing divergence and taking both
  installed Ironclad seeds to FULLY CONVERGED end-to-end. Tests:
  `test_detector5_skips_the_zeroed_terminal_boss_point`,
  `test_room_stats_reachability_guard_reports_when_sim_also_disagrees`
  (`test/test_conformance_room_stats.py`). Act 3 and the four un-ported
  characters are its next users.
- **`SelectCardFromScreen` may be mis-resolved elsewhere.** The fix routes it
  through `_grid_selector` only when no deferred screen is pending. Every
  other `CardSelectCmd.FromChooseACardScreen` call the game resolves MID-MOVE
  (rather than parking it for the driver) has the same shape and has not been
  enumerated — a census of `FromChooseACardScreen` call sites against the
  sim's two screen mechanisms would say whether Knowledge Demon was the only
  one.
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
- **`PlayerCmd.CompleteQuest` has no sim equivalent anywhere.**
  `WarHistorianRepy.cs:119,129` calls it after resolving UnlockCage/UnlockChest;
  every `CompletedQuests` reader in the decompiled tree
  (`NMapPointHistoryHoverTip.cs:304`, `NMapPointHistoryEntry.cs:186`,
  `PlayerMapPointHistoryEntry.cs` + its serializer) is Run History screen/save
  bookkeeping with zero gameplay effect — not a gap by this campaign's
  observable-divergence bar, but every Lantern-Key consumer may be missing it
  and nobody has enumerated the full consumer list. `ExtraFields.FreedRepy`
  (`WarHistorianRepy.cs:98`) is the same shape (its only other reader,
  `NQueenRepyBgVfx.cs:20`, is a background VFX toggle) and is likewise unported
  and unfiled.
- **`run_env.py`'s `PURPOSE_IDS` vocab is missing entries.** `driver.py`'s
  `SKIPPABLE_PURPOSES` registry carries purposes (`enchant_optional`,
  `exhaust_any`, `discard_any`, `from_discard`) that `run_env.py`'s observation
  vocabulary does not know about. Observation-only, lower severity than a
  behavioural gap — file it, don't block on it.
- **`relic/paper_phrog`'s target-identity guard is filed, not open work.**
  `PaperPhrog.cs:18-21`'s `target == base.Owner.Creature` self-damage bail has
  no sim analogue because `modify_vulnerable_multiplier`'s signature carries no
  `target` parameter. This IS a gap entry already — `relic/paper_phrog/g3` — not
  a hole; noted here only because the fix needs a `hooks.py`/`powers.py`
  signature change that is wider than the relic.

## What this queue does NOT cover

Every content kind is audited and aggregated; the counts are in
[Current state](#current-state) above. `py audit/tools/audit_status.py` is the
authority on coverage. What no record reaches:

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
authored and may lag.** Read the bodies as briefs, and the `open sites` line and
`counts` as the current state.

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
   Currently none; the section holds the record of what was closed.
2. **[Tier 1 — the largest multi-site families](#tier-1--the-largest-multi-site-families)**,
   written out in full. One fix each clearing many sites.
3. **[Tier 2 — dormant gaps](#tier-2--dormant-gaps)**, written out in full,
   grouped by the machinery they share.
4. **[Tier 3 — the long tail](#tier-3--the-long-tail)**, one row per remaining
   mechanism: single-site, single-unit findings, cheaper to read straight out of
   the record than to restate. The row gives the id, the liveness and the
   record's own statement of the divergence.

---

# Live gaps

**No live entry. Zero mechanisms carry one** — re-derive rather than
trusting this sentence: `py audit/tools/gap_queue.py counts`, the `with a
live entry` row. The section stays because it is the first thing a fixer
reads, and it holds the record of what was closed.

`card/mad_science/GainsBlock` — filed LIVE by the 2026-08-04 stale-record
sweep and **CLOSED the same day**. `MadScienceCard` left `gains_block` at
the `Card` base-class `False` default, so Nimble's `CanEnchant` (which
gates on exactly that flag) refused a Skill-configured Mad Science the
game accepts. Fixed with a `gains_block` property returning
`self.tinker_type == CardType.SKILL` (`mad_science.py:101-105`), mirroring
the sibling `base_block` property that already carried the same
type-dependence; pinned by
`test/test_shared_enchantments.py::test_nimble_accepts_a_skill_mad_science_only`,
which asserts the flag and Nimble's verdict for all three tinker types and
failed before the fix.

The 20 entries / 10 mechanisms the systems-tier campaign filed on 2026-08-03
(the queue's first-ever live entries) were all CLOSED the same day by the
gap-fix pass, along with 16 dormant entries belonging to the same mechanisms —
a mechanism was never landed at only its live sites, per the standing lesson
that a partial port is the worst resting state. Each closed mechanism's
section is DELETED from this file per its own rule; the fix, the executed
before/after and the re-checked reasoning live in the closing text on each
record's own entry, and the code lives behind the tests named there.

What was closed, and where its writeup now lives:

| mechanism | entries closed | closing record |
|---|---|---|
| `encounter/_slot_order` | 8 | `records/encounter/{two_tailed_rats,axebots,decimillipede,kaiser_crab,knights,queen}.json` |
| `encounter/_selection_rng_fallback` | 7 | `records/encounter/{flyconid,punch_off_event,ruby_raiders,slimes_normal,slimes_weak,slithering_strangler,two_tailed_rats}.json` |
| `encounter/_entry_slug_mismatch` | 6 | `records/encounter/{battleworn_dummy_event,dense_vegetation_event,fake_merchant_event,mysterious_knight_event,punch_off_event}.json` |
| `encounter/_slots_not_ported` | 4 | `records/encounter/{dense_vegetation_event,fake_merchant_event}.json` |
| `encounter/_slot_name_not_set` | 3 | `records/encounter/{mytes,the_obscura}.json` |
| `encounter/fogmog/Slots` | 2 | `records/encounter/fogmog.json` |
| `encounter/gremlin_merc/CalculateGoldProportion` | 1 | `records/encounter/gremlin_merc.json` |
| `rng_streams/G7` | 1 | `records/seam/rng_streams.json` |
| `relic_pools/step13` | 1 | `records/seam/relic_pools.json` |
| `potion_pipeline/G1` (== `potion/foul_potion/G1`) | 2 | `records/seam/potion_pipeline.json`, `records/potion/foul_potion.json` |
| `run_layer/G6` | 1 | `records/seam/run_layer.json` |

Two of those merit reading before the next round starts, because each
overturned something the queue asserted:

**`rng_streams/G7` was never an RNG bug.** The 89U act-1 `+6 HP` that three
rounds failed to localize was the conformance REPLAY dropping a recorded
choice: Knowledge Demon's Curse of Knowledge is a
`CardSelectCmd.FromChooseACardScreen` resolved mid-move
(`KnowledgeDemon.cs:183`), recorded as `SelectCardFromScreen N`, and
`ReplayCombatDriver._grid_selector` understood only
`SelectGridCard`/`SelectHandCards` — so the choice resolved to nothing, no
curse power was applied, and the recorded command was then dispatched into an
empty `_pending_screen_cards` and silently dropped. **Both halves failed
quietly**: a screen that took no pick, and a command that resolved nothing.
89U's act-1 boundary now matches exactly (51) with ZERO divergent floors
through act 1, and the second Ironclad seed 933T39V18D greened its act-1
boundary too (+12 → 0, 3 divergent floors → 2).

**It was found by ground truth nobody had read.** `run.save`'s
`map_point_history` carries, for every map point of every act,
`current_hp` / `max_hp` / `damage_taken` / `hp_healed` / gold counters and the
event and relic choices made there. The pipeline had been comparing HP at
three ACT boundaries while the save held it per ROOM the whole time —
`SaveOracle` already parsed the field for relic reconciliation. Reading it
turned a run-length search into a one-room one. **Any remaining HP/gold
divergence should start here**; see the open-work item below.

---

# Systems tier — 2026-08-03 campaign

Three new content kinds — `encounter` (85 units), `affliction` (7),
`character` (5) — and six new seams —
`rng_streams`/`rewards`/`relic_pools`/`run_layer`/`rooms_and_map`/`potion_pipeline`
— joined `audit/`. `character` and `rooms_and_map` have records but zero
filled verdicts / zero gap entries yet (skeletons, per each kind's own
comment in `gap_queue.py`) and contribute nothing below. The rest filed:

| kind/seam | entries | mechanisms | live |
|---|---|---|---|
| `encounter` | 45 | 11 | 16 |
| `affliction` | 1 | 1 | 0 |
| `rng_streams` | 2 | 2 | 1 |
| `rewards` | 1 | 1 | 0 |
| `relic_pools` | 6 | 6 | 3 |
| `potion_pipeline` | 3 | 3 | 1 |
| `run_layer` | 2 | 2 | 1 |
| **total** | **60** | **26** | **22** |

*As originally filed 2026-08-03; historical, kept as the round's own record
of what it produced.* Two of `relic_pools`'s three live entries
(`relic_pools/step6`, `relic_pools/step7`) were CLOSED the same day by a real
engine fix — see `records/seam/relic_pools.json` and
`test/test_conformance_relic_bag.py` — and are deleted from
[Live gaps](#live-gaps) per this file's own rule. **Current** totals (after
that closure): `relic_pools` 4/4/1, seam-family total 58/24/20 — re-derive
with `py audit/tools/gap_queue.py counts` rather than trusting this table.

`run_layer` filed its two entries (guards G6/G7) on a concurrently-running
worktree, after the rest of this section was already drafted — folded in
once `TestQueueGeneratorCoversEverySeamWithGaps` caught the gap; see its
table row's own note above.

The 22 live entries (12 live mechanisms) as originally filed were the queue's
first live entries ever, closing the "no record carries `live: true`" state
every prior round reported. **All 22 are now closed** — 2
(`relic_pools/step6`/`step7`) by the relic-bag fix the same day and the other
20 by the gap-fix pass that followed it; their per-mechanism writeups have
been deleted from [Live gaps](#live-gaps) per this file's own rule, which now
carries the closing summary instead. This
section covers what Live gaps doesn't: the dormant families, the recurring
merges (`_FAMILIES` additions in `audit/tools/gap_queue.py`), the
cross-record disagreements the campaign surfaced, and the one liveness label
this round scrutinised before folding it in.

## Recurring families

`encounter` tags nothing, so its entries would anchor one mechanism each
without a `_FAMILIES` table entry for every declared merge — the batches
proposed shared ids in the record TEXT precisely so they would not. Nine
patterns collapsed the campaign's 45 entries into 11 mechanisms; the gap-fix
pass then closed seven of those eleven outright, leaving **14 entries across 4
mechanisms**, all dormant:

| mechanism | sites | liveness | units |
|---|---|---|---|
| `encounter/_all_possible_monsters` | 9 | dormant | aeonglass, axebots, construct_menagerie, devoted_sculptor, fabricator, frog_knight, globe_head, knights, mecha_knight |
| `encounter/_slot_row_unpopulated` | 2 | dormant | phrog_parasite, the_kin |
| `encounter/nibbits_normal/Slots` (same-unit merge) | 2 | dormant | nibbits_normal |
| `encounter/gremlin_merc/g1` | 1 | dormant | gremlin_merc |

CLOSED by the gap-fix pass and deleted from this table: `_slot_order` (8),
`_selection_rng_fallback` (7), `_entry_slug_mismatch` (6), `_slots_not_ported`
(4), `_slot_name_not_set` (3), `fogmog/Slots` (2),
`gremlin_merc/CalculateGoldProportion` (1).

**The two slot families still open are the ones with no C# `Slots` row at
all.** Every encounter whose C# DOES declare one now carries it, so
`_slot_row_unpopulated` (phrog_parasite, the_kin) and
`encounter/nibbits_normal/Slots` are the remaining shape: a row exists in the
game and nothing in the unit ever re-sorts against it. The
"re-read whether `_slots_not_ported` should fold into `_slot_order`"
recommendation below is moot — both were closed by the same fix, which is
itself the evidence that they were one mechanism.

**`AllPossibleMonsters` decision: one mechanism, not several.** All nine
records write the identical sentence (sourced from `encounter/aeonglass`,
cited by the other eight rather than restated): "Shared finding... filed once
under `encounter/_all_possible_monsters`." The per-unit AllPossibleMonsters
lists differ in shape — most are a single class, `construct_menagerie`'s is
two, `fabricator`'s is a five-monster superset that differs from its own
`GenerateMonsters` roster in KIND and not just count — but every record's
underlying argument is identical and dormant for the identical reason: the
sim has no `AllPossibleMonsters` analogue at all, and the concept's three
game-side consumers (`UnlockConsoleCmd.cs:68`, `:147`,
`NGeneralStatsGrid.cs:164`) are all dev-console/stats-screen UI with no
sim-side counterpart to read them. One mechanism.

**Four distinct "slot" families were filed; ONE fix closed all four's open
sites.** The campaign kept `_slot_order`, `_slot_name_not_set`,
`_slots_not_ported` and `_slot_row_unpopulated` split because no record
cross-referenced another's name — the file's own "declared or nothing" rule.
The gap-fix pass then closed the first three, plus both same-unit merges
(`encounter/fogmog/Slots`, and `nibbits_normal`'s is dormant only because
Nibbit cannot summon), with a single change: declare the C# `Slots` row on
every encounter that has one, pass `slot_name=` at each summon site, and route
every roster through `Encounter.seat_in_slots`. **The split was a bookkeeping
fact about the records, not about the code** — worth remembering the next time
this file keeps four ids apart on the same rule.

## Dormant entries, by mechanism

**`affliction/hexed/AfterCardEnteredCombat`** (dormant) — `HexedAffliction`
defines zero hook methods, so Hexed's one piece of logic (self-clearing when
its card re-enters combat and the owner no longer has `HexPower`) never
fires. Dormant because the sole applier, Spectral Knight
(`monsters/glory/knights.py`), always dies before a normal combat can end in
a player win, so `HexPower.AfterDeath`'s explicit sweep always beats the
silent `AfterCombatEnd` strip that would otherwise leak a stale Hexed
affliction into a later `AfterCardEnteredCombat`.

**`encounter/_all_possible_monsters`** (dormant, 9 sites) — see table above;
no sim consumer of the concept exists.

**`encounter/_slot_row_unpopulated`** (dormant, 2 sites: phrog_parasite,
the_kin) — same shape; no C# consumer of `SlotName` applies to either unit's
own monsters (grepped and read in full by the batch).

**`encounter/nibbits_normal/Slots`** (dormant, 2 sites) — Nibbit never
summons and has no other spawn path in the whole decompiled tree, so the
missing row/attribute has no reader on either side.

**`encounter/gremlin_merc/g1`** (dormant) — the slot LABELs GenerateMonsters
and SurprisePower.AfterDeath attach ('merc'/'sneaky'/'fat') are dropped, but
`GremlinMercNormal` doesn't override `Slots` (inherits the empty default), so
the game's own sort is a no-op here too.

**`rng_streams/step16`** (dormant) — `Rng.WeightedNextItem<T>`'s C# arithmetic
is 32-bit `float` throughout; `sts2_rl/rng.py`'s `weighted_next_item` sums in
Python `float` (== C# `double`). Dormant on BOTH sides: `grep -rn
'\.WeightedNextItem\(' src/` returns zero call sites in the whole decompiled
game, stronger than the mechanism's original "no consumer YET" framing.

**`rewards/step16`** (dormant) — `CardReward`'s C# constructor subscribes to
`player.RelicObtained` and re-runs both card-reward modifier hooks if a relic
is obtained while the reward screen is still open; the sim has no
counterpart. Already verdicted dormant by `relic/silver_crucible.json`
("the sim grants relics between rooms, never with a reward screen open") —
**this seam's own read of `generate_combat_rewards` narrows that premise; see
Cross-record disagreement #2.**

**`relic_pools/guard4`** (dormant) — the LEGACY (no `string_seed`) relic
grab bag's rarity filter (`run.py`'s `_BAG_RARITIES`) omits Shop, unlike both
`RelicGrabBag.Populate`'s 4-rarity filter and `relic_pools.py`'s own
`BAG_RARITIES`. Root cause of `relic_pools/G5`'s under-report (below); the
parity path is unaffected (step 1, faithful).

**`relic_pools/G5`** (dormant, entry id `relic_pools/step8`) —
`RelicGrabBag.HasAvailableRelics` loops all 4 bag rarities;
`run.has_available_relics` is `bool(self.relic_grab_bag)`, faithful in
parity but under-reporting in LEGACY mode once Common/Uncommon/Rare are
exhausted while a Shop-rarity relic remains (guard4's own gap). Two ported
consumers (`events/luminous_choir.py`, `relics/shovel.py`). Not executed —
draining an entire run's C/U/R bag is an extreme-length scenario the batch
did not construct a witness for, so it stays dormant rather than claimed
live without one.
**Mechanism-key note:** the auto-derived key for this entry is
`relic_pools/G5`, not `relic_pools/step8` — its own text says "(see guard
G5)", but `relic_pools.json`'s guards carry no `G5:` label (the guard this
sentence means is `guard4`, whose own "what" has no letter prefix and so
auto-numbers positionally). A record-prose mislabel, not a second mechanism;
recorded under the key the tool actually derives (per this file's own
convention of naming what the auto-resolver produces rather than silently
correcting it) so `coverage` and the next reader both find it.

**`relic_pools/step5`** (dormant) — `GetAvailableDeque`'s `_refreshAllowed`
refill branch. RE-DERIVES `relic/circlet/g4`'s second finding and corrects
its reachability framing: `player.RelicGrabBag` — the only bag any of the
four consumer methods are ever called on — is ALWAYS built via the
parameterless ctor (both of `Player`'s construction sites), so
`refreshAllowed` is always false; the only `refreshAllowed:true` instances
(`RunState.SharedRelicGrabBag`) are never the SUBJECT of those four methods
anywhere in the decompiled tree. Faithful-by-vacuity in every mode, not an
open reachability question — `py audit/tools/relic_pool_probes.py
refresh-allowed-dead`.

**`potion_pipeline/G2`** (dormant) — `RunState.add_potion` runs the
`ShouldProcurePotion`-equivalent gate correctly for every out-of-combat grant
path but never dispatches `after_potion_procured`. Dormant because C#'s own
sole `AfterPotionProcured` implementer, `BeltBuckle.cs:63-70`, gates itself on
`CombatManager.Instance.IsInProgress` — a no-op for every out-of-combat
procure on the GAME side too.

**`potion_pipeline/G3`** (dormant) — `PotionCmd.Discard`'s unconditional
`AfterPotionDiscarded` dispatch has no sim counterpart on either the in- or
out-of-combat discard verb. Already filed at
`audit/records/relic/belt_buckle.json`'s `AfterPotionDiscarded` hook entry;
matched here per rule 3 as the verb-level home for the same missing
dispatch.

**`run_layer/G7`** (dormant) — starting-relic `AfterObtained` timing relative
to `GenerateRooms`: the game fires it AFTER room generation
(`FinalizeStartingRelics`); the sim fires it BEFORE
`_generate_all_act_rooms`. A pure ordering swap with no value divergence
today — executed: `py audit/tools/run_layer_probes.py starting-relic-order`
confirms `BurningBlood.cs` (Ironclad's only starting relic, and the only one
reachable in this Ironclad-only sim) has no `AfterObtained` override at all
(its one override is the unrelated in-combat `AfterCombatVictory`). Would go
live the moment a ported starting relic's `AfterObtained` reads or mutates
run/act/room state that `GenerateRooms` also touches — not reachable today
because no other character is ported.

## Cross-record disagreements found this campaign

Recorded as open items for the next round, not resolved here — resolving
each needs its own evidence pass, and `audit/records/monster/`,
`audit/records/relic/`, `audit/records/potion/` and
`audit/content/potion/shared-mechanisms.md` are not edited by this one.

1. **`monster/fabricator.json`'s guard4 vs `encounter/queen`.** Fabricator's
   closing note (round 7) says "Encounters with no row are unaffected — the
   sort is a no-op and a spawn appends, which is every other encounter."
   False: `encounter/queen` declares a real `Slots => ["amalgam", "queen"]`
   row (`QueenBoss.cs`) and the sim's `QUEEN_BOSS` still inherits the empty
   default — one of the eight `encounter/_slot_order` sites above. The guard
   itself is not wrong about the mechanism it shipped, only about its
   breadth claim.
2. **`relic/silver_crucible.json`'s "relics are granted between rooms" vs
   `seam/rewards` step 16.** Silver Crucible's own guard dormancy premise:
   "That path is dormant (the sim grants relics between rooms, never with a
   reward screen open)." `seam/rewards`' own read of
   `generate_combat_rewards`'s Elite branch: `rewards.cards =
   create_reward_cards(...)` completes BEFORE `run.offer_relic(relic)`
   resolves that SAME elite's own relic reward, inside the SAME function
   call — narrower than "between rooms" for this one case. Confirming it
   live needs a specific Common/Uncommon relic reachable via an Elite's own
   grab-bag pull that also implements `modify_card_reward_options[_late]`
   against already-drawn cards — a `relic_pools`/content-tier determination,
   not made here.
3. **`potion/foul_potion.json` self-contradicts across its own dated
   entries.** Its 2026-07-27 `PassesCustomUsabilityCheck` dormancy claim
   ("DORMANT today only because no production caller reaches
   `RunState.use_potion`") is falsified by its own 2026-07-28 `Usage` entry,
   which records that the conformance `ReplayRunner` was wired to drive an
   out-of-combat `UsePotion` through `RunState.use_potion` — real, in the
   main replay loop (`conformance/runner.py:846` → `_use_map_potion` →
   `run.use_potion` at `:564`). `potion_pipeline`'s own `step13` entry
   (`potion_pipeline/G1` above) files this exact gap **live** on that basis,
   flagging the sibling record's `live: false` as stale rather than
   overturning it directly. Both `foul_potion.json`'s `G1` guard and its
   `PassesCustomUsabilityCheck` hook still read `live: false` on disk.
4. **`audit/content/potion/shared-mechanisms.md` is three rounds behind the
   51 potion records it narrates.** Its `W2`/`W4`/`W10` describe a hole in
   `PotionModel.OnUseWrapper` that was fixed 2026-07-29 (round 6) — all 51
   potion records already carry the corrected `faithful` verdict on `W`/`W4`
   (confirmed while reading `potion_pipeline`'s own `G2`/`G3` neighbours
   above). Not re-verified against `W2`/`W10` specifically by this campaign;
   flagged for the potion stream to reconcile.

## Liveness scrutiny: `encounter/_selection_rng_fallback`

The brief for this round asked whether this mechanism's flat `live: true`
label is honest, since the **conformance** path wires a `string_seed` (an
earlier round's `RunState` string-seed streams work) that the mechanism's own
argument depends on being absent.

**Checked directly, not re-derived:**

- `sts2_rl/run_env.py:747`, inside `STS2RunEnv._make_run_state`:
  `return RunState(rng=self._rng, character=self._character)` — no
  `string_seed` argument. This is the construction every RL training/eval
  episode uses.
- `sts2_rl/conformance/runner.py:800`: `run = RunState(string_seed=rec.seed)`
  — the construction every conformance replay uses.

**Finding: the label is directionally correct, but "live" needs scope, and
the record text (correctly) already carries it — the typed field does not
need to change.** `RunState.rng_set` is only built when a `string_seed` is
supplied; `run_env.py` never supplies one, so `encounter_selection_rng` is
`None` for every training episode and all seven sites take the shared-stream
fallback — an actually-exercised divergence in the sim's primary training
configuration, not a hypothetical. `conformance/runner.py` always supplies
one, so every conformance replay takes the correct, independent
`make_encounter_rng`-seeded branch and this mechanism does not fire there —
consistent with every one of the seven records' own "does not explain the
89U conformance divergence" note.

**Outcome: the label was right, and the mechanism is now FIXED.** The
gap-fix pass gave the seedless path a real per-encounter Rng
(`RunState.derive_encounter_seed`), so both paths now behave the way this
scrutiny concluded only the conformance one did. The reasoning below is kept
because its VOCABULARY question outlived the entry: "live" here means
reachable on some real, currently-exercised path — RL training counts.

**Conclusion as recorded at the time: `"live": true` stays.** "Live" in this queue's
vocabulary has never meant "affects conformance specifically" — it means
"reachable and consequential on some real, currently-exercised code path",
and RL training is the sim's primary use case, not an edge case. Flipping
the field to `false` would misreport a mechanism that fires on every
unseeded episode reaching one of these seven encounters. What was missing
was scope in the QUEUE TEXT, not a wrong typed field — each entry above
under `encounter/_selection_rng_fallback` stated the RL-live /
conformance-dormant split explicitly, with both file:line citations.
`audit/records/encounter/*.json` was not edited by that scrutiny (the
gap-fix pass later flipped all seven entries to `faithful`).

---

# Tier 1 — the largest multi-site families

The mechanisms with the widest blast radius: one fix each clearing many sites.

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

- **open sites** 2: `power/steam_eruption/g4` (dormant), `monster/test_subject/g1` (dormant)
- **impact** B — an HP number conformance asserts on directly, plus a missing
  energy gain and a missing draw.
- **divergence** C# **lets the death happen**: `Hook.ShouldDie` returns true,
  `CreatureCmd.cs:507-508` fires the died event and computes
  `shouldRemoveFromCombat = false`, then `AfterDeath` sets `isReviving` — leaving
  the creature **dead at 0 HP, retained in combat**. The sim **prevents** the
  death from `should_die` (`sts2_rl/powers.py:3365-3370` returns `False`) and
  `sts2_rl/cmds.py:106-113` floors the creature at **1 HP** with `is_dead` False.
- **observable** Three:
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

### `turn_structure/G13` — `CheckWinCondition` hand-rolled instead of reached  [DORMANT] [unpinned]

- **open sites** 2: `relic/festive_popper/AfterPlayerTurnStart` (dormant), `relic/festive_popper/g3` (dormant)
- **impact** B — a dead player keeps taking legal actions; a relic's own
  tie-break disagrees with the engine's.
- **state** The seam half is closed: all six C# sites recompute, the four inline
  `_all_enemies_dead()` / `is_dead` pairs call the real check, and
  `SetupPlayerTurn`'s `IsDead` guard is ported. **What is open is the relic
  half** — `festive_popper.py:28` hand-rolls `self._check_win()` where C# reaches
  `CheckWinCondition`, and `Relic._check_win()` (`relics/base.py`) has the
  win/loss tie-break backwards, going straight to
  `_all_enemies_dead() -> _end_combat(player_won=True)` without testing the
  pending LOSS first (that is `turn_structure/guard23`, the fifth site of the
  class this mechanism's close note said it had eliminated at four).
- **divergence** C# calls `CheckWinCondition` at six sites, including immediately
  after `SetupPlayerTurn` (`CombatManager.cs:573`).
- **observable** A player killed during turn-1 setup — by an
  `on_combat_start`/`on_player_turn_start(ed)` listener — must not be left in
  `Phase.PLAYER_TURN` at 0 HP with a legal action set. On the relic path a
  simultaneous kill resolves as a win where the game resolves it as a loss.
- **pin** `TestTurnStructureOrder::test_turn_one_setup_death_ends_the_combat`.
- **fix** Delete `Relic._check_win()`'s hand-rolled body in favour of the
  engine's recomputing check, tie-break included, and route Festive Popper
  through it. Failing test asserts a simultaneous kill on the relic's damage
  resolves as a loss.
- **radius** `turn_structure/G10` (the combat-end path's two disagreeing
  player-death exits) and `hook_dispatch/G8` (nothing should dispatch once combat
  is ending) are the same area, and a fix here should land with G10's two-exit
  reconciliation.

### `damage_pipeline/G2` — no `AfterModifyingXxx(modifiers)` companion events  [DORMANT] [unpinned]

- **open sites** 3: `damage_pipeline/G2` (dormant), `power_cmd/step31` (dormant), `hook_dispatch/step38` (dormant)
- **state** The arithmetic, stated exactly because the body below invites
  miscounting: `Hook.cs` declares **13** `AfterModifying*` variants; 4 of them
  (Block, Damage, HpLostBeforeOsty, HpLostAfterOsty) are covered by 3 sim hooks
  and were never part of the 9 this mechanism tracks; of those 9, **2 are
  implemented and 7 remain** — CardPlayCount, CardRewardOptions, EnergyGain,
  GoldGained, HandDraw, OrbPassiveTriggerCount (Defect-only, waived under N3) and
  Rewards. Each is dormant on its own executed merits, and none of the 7 has been
  re-verified since.
- **impact** B at the block site (a relic fires on the wrong gain), C elsewhere.
- **divergence** C#'s modifier dispatchers track which listeners actually
  changed the value and fire a companion event so those listeners can react only
  when they were an active modifier (`Hook.cs:649-829`). The sim implements
  `modify_hp_lost` / `after_modify_hp_lost` (`hooks.py:126-155`, called from
  `cmds.py:85-87`) and the two power-amount variants; the rest have no surface.
- **observable** Sharpest at the **block** site: all three C# listeners on
  `AfterModifyingBlockAmount` are ported (`Vambrace.cs:78-90`,
  `PaelsLegion.cs:146-158`, `FastenPower.cs:36-40`) and each hand-rolls its
  "I actually fired" side effect onto a different event. Pael's Legion's
  hand-roll nets the same (`relics/paels_legion.py:33-51`); **Vambrace's does
  not** — `relics/vambrace.py:36-40` burns its once-per-combat `_used` flag on
  the *first* block gain, where C# latches `TriggeringCard` and doubles every
  block gain of that one card play. Elsewhere the machinery's absence is
  structural: `RuinedHelmet.cs:55-60` is reimplemented inline at
  `relics/ruined_helmet.py:37`.
- **pin** `TestCreatureCardCmdsOrder::test_vambrace_doubles_every_block_gain_of_one_card_play` (the block site only; the other variants are unpinned).
- **fix** Generalise the `modify_hp_lost` pattern: give each remaining modifier
  dispatcher in `hooks.py` an out-param `modifiers` list and a paired
  `after_modify_<x>` notifier, then re-home the three block listeners onto it.
  Failing test asserts Vambrace doubles *both* block gains of a two-block-gain
  card play and neither gain of the next card.
- **radius** Blocks a faithful `BufferPower` port (its whole mechanism is
  `AfterModifyingHpLostAfterOsty`) and sits on the seam the Unsettling Lamp bug
  lived on (PowerAmountGiven/Received). Same dispatchers as `hook_dispatch/G9`
  and `damage_pipeline/G3`.

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

- **open sites** 2: `relic/bing_bong/g1` (dormant), `relic/massive_scroll/g4` (dormant)
- **impact** B — the relic simply does nothing.
- **divergence** `sts2_rl/relics/base.py:20-24` documents a deliberate policy:
  relics whose whole effect is out of combat are "registered as documented no-op
  stubs so the full pool is constructible". The policy was sound when written.
  **The premises have since been overtaken** — the sim grew a gold system, a
  potion belt, rest sites and card rewards, and the stubs' docstrings still cite
  their absence. `lucky_fysh` says "no gold system"; `run.gold` exists.
- **state** Both survivors are real divergences left open because they are
  unreachable, not because they are unchecked: `bing_bong` needs an adder
  argument threaded through `after_card_added_to_deck`, and `massive_scroll`
  needs a MultiplayerOnly card pool that is not ported. The third site,
  `punch_dagger`, closed when Momentum landed — its stub premise ("the sim has
  no enchantments") had been false for some time.
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

# Tier 2 — dormant gaps

Real divergences argued unreachable on today's ported content, grouped by the
machinery they share. Dormant is a claim about content, not about the code —
the next port invalidates it.

## 2A. Missing guard families

### `creature_card_cmds/N3` — the `CardPileAddResult` failure surface is unmodelled  [DORMANT] [unpinned]

- **open sites** 2: `creature_card_cmds/step70` (dormant), `creature_card_cmds/step73` (dormant)
- **state** The behaviourally significant branch is already reproduced.
  `CardPileCmd._refuses_combat_add` is one boolean consulted at the top of all
  three pile-ADD helpers and covers C#'s batch `IsEnding` refusal, the per-card
  `creature.IsDead` refusal and the `!IsInProgress` refusal. What stays open is
  the RESULT OBJECT, and it is a confirmed waiver rather than a deferral: no
  external C# caller reads `.success` / `.oldPile` / `.modifyingModels` for
  gameplay outside the Deck path, and on this call path `oldPile` and
  `modifyingModels` are provably always null — a ported object would carry no
  information beyond `success`. `step73` (`ShouldAddToDeck`, still zero overrides
  game-wide) stays its own open gap.
- **divergence** C#'s `Add` returns a per-card result carrying
  success/oldPile/modifyingModels and sets `success = false` for a dead owner, a
  removed-from-state card, a detached combat card, or a `ShouldAddToDeck`
  prevention (`CardPileCmd.cs:322-397`); the sim's three pile helpers
  (`cmds.py:463-512`) return `None` and always succeed.
- **trigger** `ShouldAddToDeck`/`AfterAddToDeckPrevented` have zero overrides
  game-wide, so the trigger is porting the first one — or any card generation that
  can outlive the player's death (the sim ends combat as soon as the player dies,
  `combat.py:419-420`).
- **pin** unpinned. **fix** return a small result object from the pile helpers and
  honour the dead-owner drop. **radius** `hook_dispatch/G8`, `/N4`.

## 2B. Missing hook surfaces

### `creature_card_cmds/G8` — no `AfterCardChangedPiles` at all  [DORMANT] [unpinned]

- **open sites** 1: `creature_card_cmds/G8` (dormant)
- **state** **Narrowed, not closed, and its own site enumeration was one short.**
  `CardCmd.Exhaust` IS `CardPileCmd.Add(card, PileType.Exhaust)`
  (`CardCmd.cs:242`), so **every exhaust dispatches `AfterCardChangedPiles` in C#
  and none does in the sim** — five dispatch sites, not four. Add, Draw, the two
  reshuffle helpers and `RemoveFromCombat` are wired; the manual play needs the
  Play-pile modelling first (`creature_card_cmds/N9`), and the exhaust leg is
  unwired. Deliberately left: a faithful wiring is five sites, and landing two of
  five is worse than landing none.
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
  and fire it from the three pile helpers, exhaust leg included. **radius**
  `creature_card_cmds/G3`, `/G11`, `hook_dispatch/G1`.

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
  `on_enemy_side_end -> IntangiblePower`. **The record quotes a suite size
  thousands of tests smaller than today's — re-run it before relying on the
  "only one hit" claim.**
- **trigger** Any listener that removes another listener mid-dispatch.
- **fix** Needs `hook_dispatch/G1`'s derived listener list plus a `HasBeenRemovedFromState`
  flag on cards/relics (`creature_card_cmds/step68`).
- **radius** `hook_dispatch/G2`, `/G1`, `/G5`, `/G6`, `/N5` — the registry-shape
  family lands together or not at all.

### `hook_dispatch/N5` — no run-level listener list  [DORMANT] [unpinned]

- **open sites** 3: `hook_dispatch/N5` (dormant), `hook_dispatch/step14` (dormant), `hook_dispatch/step18` (dormant)
- **trigger** Porting any `CardModel` overriding `AfterRoomEntered`,
  `AfterRewardTaken`, `ShouldAddToDeck` or another run-level hook.
- **fix** Give `HookSystem` a run-level listener list alongside the combat one,
  so a run-scoped hook has somewhere to hang.
- **radius** `creature_card_cmds/G12` (nowhere to hang `AfterGoldGained`).

## 2D. Power pipeline

### `power_cmd/G2` — Unsettling Lamp's condition is sign-aware, the dispatch is not  [DORMANT] [unpinned]

- **open sites** 1: `power_cmd/step10` (dormant)
- **state** `UnsettlingLamp.cs` has no `amount <= 0` guard anywhere — both its
  latch and its doubling gate purely on `GetTypeForAmount(amount) != Debuff`, and
  the sim's condition is sign-aware to match (`Malaise.cs:40` and
  `Resonance.cs:33` apply negative `StrengthPower` with `applier = player,
  cardSource = this` — exactly the shape the Lamp doubles). Duration ticks are
  structurally unreachable from the Lamp: every tick goes through
  `PowerCmd.modify_amount`, which never calls `modify_power_amount`.
- **divergence** What is left is dispatch architecture, and it is what blocks
  `damage_pipeline/G2`'s remaining variants: `modify_power_amount` returns a bare
  int with no modifiers out-list, so no listener can be told it was the one that
  changed the value.
- **fix** Lands with `damage_pipeline/G2`'s out-param generalisation.

### `power_cmd/G3` — the three power-amount phases collapsed into one chain  [DORMANT] [unpinned]

- **open sites** 1: `power_cmd/step27` (dormant)
- **state** The flat registration-order chain is gone: given-additive then
  given-multiplicative (C#'s exact sum-then-product, which a naive fold gets
  wrong) under a real `applier != null && ContainsCreature(applier)` gate, then
  the received chain unconditionally. Artifact and Ruined Helmet are real
  listeners now instead of a hard-coded block outside the hook loop.
- **trigger** The two general listeners are domain-disjoint today — Unsettling
  Lamp is GIVEN-side and Ruined Helmet / Artifact are RECEIVED-side, so they were
  never on the same C# hook. A third listener, or either widening across sides,
  collides.
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

### `monster/knowledge_demon/g1` — the curse's power carries no card source  [DORMANT] [unpinned]

- **open sites** 1: `monster/knowledge_demon/g1` (dormant)
- **state** The applier half is fixed (`applier=player`, per all four curse
  cards' C#). The card-SOURCE half stays open: `PowerCmd.apply` and `Power` model
  no source parameter anywhere — an architecture-wide absence that belongs to
  `power_cmd`.
- **divergence** In the game the curse card applies its own power with the
  **player** as applier and the card as the source (`Disintegration.cs:25-28`,
  `MindRot.cs:25-28`, `Sloth.cs:25-28`, `WasteAway.cs:28-31`).
- **dormancy** No ported listener distinguishes the source on these four powers.
- **trigger** Any listener that gates on source identity for a curse-applied
  power — `PowerCmd.Apply`'s arguments are not decoration: they select the
  `Hook.ModifyPowerAmountGiven` pass and key
  `FindExistingInstanceForStacking`.

---

# Tier 3 — the long tail

One row per remaining mechanism, generated from the records. They are real,
recorded and verified — they are rows rather than sections because a
single-unit finding is cheaper to read in its own record than restated. The id
is the path: `power/aggression/…` is `audit/records/power/aggression.json`.

**Line numbers are stripped from these summaries on purpose**, so that
`cite-check` stays a check on the authored prose above rather than a
re-validation of record excerpts.

## Seam remainder — 8 mechanisms

- `creature_card_cmds/G4` — DORMANT — G4 (dormant) -- CreatureCmd.heal refuses to heal a dead creature; C#'s Heal revives — CombatManager.IsEnding (CombatManager.cs) OPENS with `if (!IsInProgress) return false;`, so it is true exactly DURING the ending sequence and false again the instant combat is torn down -- the…
- `creature_card_cmds/guard26` — DORMANT — NoUpgradeRoll is unmodelled at every non-combat card-creation site but one — Every non-combat card-creation site reachable in the single-character sim now either correctly carries NoUpgradeRoll or correctly does not, by citation, not by sweep.
- `hook_dispatch/G8` — DORMANT (sites: `hook_dispatch/step46`) — The sim has no phase concept, no preventer for most predicates, no Contains re-check, no IsOverOrEnding gate, no per-listener choice context, and no run-level HookSystem (hooks.py in full) — `grep -n xfail test/test_hook_order.py` finds zero `@pytest.mark.xfail` decorators (`py -m pytest…
- `hook_dispatch/guard11` — DORMANT — can_receive_powers and _combat_contains_creature read the eager removal PREDICTION — `can_receive_powers` and `_combat_contains_creature` STILL read the prediction and so diverge for the whole death sequence (demonstrated: all three read False mid-AfterDeath where C# would allow the power to land).
- `power_cmd/N4` — DORMANT (sites: `power_cmd/step4`) — Branch: no existing instance -> new-power Apply(...) pipeline (steps 6-23); existing instance -> ModifyAmount(...) pipeline (steps 24-37), nulling the result if it returns exactly 0 (PowerCmd.cs) — The sim's single code path (`sts2_rl/cmds.py PowerCmd.apply`, current lines 508-605) really…
- `power_cmd/step21` — DORMANT — Guard givenModifiers!=null: await Hook.AfterModifyingPowerAmountGiven(combatState, givenModifiers, power) (PowerCmd.cs; Hook.cs) — The dormancy reason has changed in kind: this was 'no sim counterpart at all', and the counterpart now EXISTS and is correctly wired…
- `turn_structure/G7` — DORMANT (sites: `turn_structure/step63`) — `await Hook.AfterFlush(state, player, ctx, cardsToFlush, cardsToRetain)` -- UNCONDITIONAL, fired even when nothing was flushed -- then PlayerCombatState.EndOfTurnCleanup(), also unconditional and the SECOND of its two per-round sites (CombatManager.cs; Hook.cs) — What remains…
- `turn_structure/guard23` — DORMANT — `Relic._check_win()` (relics/base.py) has the win/loss tie-break BACKWARDS -- the FIFTH site of the class G13's close note says it eliminated at four. — DIVERGENCE: the helper goes straight to `_all_enemies_dead() -> _end_combat(player_won=True)` without testing the pending LOSS first.

## `power` — 89 mechanisms

- `power/buffer/ModifyHpLostAfterOstyLate` — DORMANT — The arithmetic is exact -- 0 for the owner, unchanged otherwise (BufferPower.cs vs powers.py) -- and the AFTER-Osty position is right, since cmds.py runs after block absorption .
- `power/burrowed/AfterRemoved` — DORMANT — C#'s AfterRemoved is `CreatureCmd.LoseBlock(oldOwner, 999999999m)` -- dump ALL the block -- and it runs on EVERY removal path, including the automatic strip when the owner dies (CreatureCmd.cs then each power's AfterRemoved).
- `power/calamity/BeforeCardPlayed` — DORMANT — C# uses a TWO-HOOK LATCH the sim collapses into one. CalamityPower.cs records amountsForPlayedCards[card] = base.Amount at BeforeCardPlayed and removes it at AfterCardPlayed, so (a) the Amount is SNAPSHOTTED at the start of the play and (b) the after-hook only fires for a card the…
- `power/chains_of_binding/AfterCardDrawn` — DORMANT — (1) A DROPPED GUARD: C# requires `base.CombatState.CurrentSide == base.Owner.Side` (ChainsOfBindingPower.cs), so only cards drawn during the PLAYER's own turn are Bound; the sim has no side test (powers.py), so a card drawn during the ENEMY turn is Bound in the sim and not in the game.
- `power/chains_of_binding/BeforeCardPlayed` — DORMANT — WRONG SIDE OF THE PLAY, the same shape as SlothPower's: C# sets `boundCardPlayed` in BeforeCardPlayed (ChainsOfBindingPower.cs) and the sim sets it in on_card_played, after resolution -- while the sim's `before_card_played` slot (combat.py) exists and is used by StranglePower and…
- `power/crab_rage/g1` — DORMANT — CrabRagePower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)`); the sim omits it, so `applier` is None through hooks.modify_power_amount (cmds.py), hooks.on_power_applied (cmds.py)…
- `power/crimson_mantle/g3` — DORMANT — CrimsonMantlePower.cs fires the damage UNCONDITIONALLY — C# calls CreatureCmd.Damage with the DamageVar's BaseValue every turn, including the first, when the value is 0; powers.py guards on `if self.self_damage > 0`.
- `power/cruelty/g2` — DORMANT — CrueltyPower.cs `target == base.Owner` -> unmodified — Cruelty's self-exclusion is dropped by its consumer. Recorded in full on power/vulnerable's matching guard -- the sim reads Cruelty's amount with no such test, so a Cruelty holder attacking its own Vulnerable self would get the bonus…
- `power/cruelty/g4` — DORMANT — CrueltyPower.cs `amount + base.Amount / 100m` — Replaced the record's "third non-dyadic multiplier" framing: the ONE live applier (`cards/cruelty.py`) only ever grants multiples of 25, so `1.5 + n/100.0` is exact in `float` for every reachable value (executed: `Decimal` cross-check for n in…
- `power/curious/g2` — DORMANT — CuriousPower.cs,32 the TryModify predicate protocol — C#'s Try* hooks are a predicate chain: the listener returns bool to say 'I changed it' and writes the new value to an out-param, and Hook.ModifyEnergyCostInCombat (Hook.cs) uses that to decide who to notify afterwards and, in…
- `power/curl_up/AfterCardPlayed` — DORMANT — EXECUTED: test/test_powers.py TestCurlUp (`test_gains_block_once_the_card_play_finishes`, `test_a_multi_hit_attack_is_not_absorbed_mid_card`) passes today.
- `power/dampen/AfterApplied` — DORMANT — (1) MECHANISM, the same substitution as illusion's: C#'s AfterApplied runs after PowerCmd registers the power; the sim does the work in __init__, i.e. inside `power_cls(...)` at cmds.py and therefore BEFORE hooks.register and hooks.on_power_applied.
- `power/dark_shackles/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, , consumed at and) has NO sim counterpart at all.
- `power/dark_shackles/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers.
- `power/dexterity/ModifyBlockAdditive` — DORMANT — The sim keys the ownership test on the BLOCK TARGET where C# keys it on the CARD's owner. DexterityPower.cs: when cardSource != null the test is `cardSource.Owner.Creature != base.Owner -> 0m` and the target is not consulted at all; only for cardSource == null (a monster move) does it fall…
- `power/dexterity/g2` — DORMANT — Sign-aware power typing on a negative Dexterity application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGATIVE amount, because StackType == Counter && AllowNegative.
- `power/disintegration/AfterSideTurnEndLate` — DORMANT — Wrong slot AND lost phase, and it is the only power in this group with both. (a) PHASE: this is `AfterSideTurnEndLate`, the second complete pass Hook.AfterTurnEnd runs (Hook.cs), so in the game Disintegration's damage lands after EVERY plain AfterSideTurnEnd listener has finished…
- `power/feeding_frenzy/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, , consumed at and) has NO sim counterpart at all.
- `power/feeding_frenzy/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers.
- `power/flame_barrier/AfterSideTurnEnd` — DORMANT — The removal condition is inverted from a side comparison into a hard-coded side. FlameBarrierPower.cs removes the power whenever `base.Owner.Side != side` -- i.e.
- `power/flex_potion/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the wrapper's internal stat power.
- `power/flex_potion/g5` — DORMANT — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers.
- `power/free_attack/g4` — DORMANT — C#'s Try* hooks return bool and write to an out-param, which Hook.ModifyEnergyCostInCombat (Hook.cs) uses to build its notification list; the sim's modify_card_energy_cost (hooks.py) is a plain fold with neither.
- `power/galvanic/AfterCardPlayed` — DORMANT — **PROPS.** C# deals the Galvanized damage with `ValueProp.Unpowered | ValueProp.Move` (GalvanicPower.cs); the sim passes `DamageProps.NON_CARD_UNPOWERED`, which valueprops.py defines as `UNPOWERED` **alone** -- the MOVE flag is missing.
- `power/galvanic/BeforeCombatStart` — DORMANT — Right slot -- combat.py fires on_combat_start immediately before `start_turn()` at, which turn_structure identifies as the sim's BeforeCombatStart.
- `power/gigantification/AfterAttack` — DORMANT — The slot is right (combat.py, immediately after the card's on_play inside the play-count loop). The GAP is the IDENTITY the latch is cleared against: C# compares ATTACK-COMMAND identity (`command == internalData.commandToModify`, GigantificationPower.cs), the sim compares CARD identity…
- `power/hardened_shell/ModifyHpLostBeforeOstyLate` — DORMANT — The FORMULA is exact -- `target != Owner -> amount`, `amount == 0 -> amount`, else `Math.Min(amount, Amount - damageReceivedThisTurn)` (HardenedShellPower.cs) vs powers.py -- and the BeforeOsty/AfterOsty phase collapse is already resolved as faithful by damage_pipeline (Osty…
- `power/heist/BeforeDeath` — DORMANT — HOOK-PHASE MISMATCH -- a BEFORE hook ported onto an AFTER hook, the recurring shape section 0 item 5 of the stream report names for thorns/curl_up/skittish/suck, now in a death-time form.
- `power/hello_world/g1` — DORMANT — HelloWorldPower.cs base.AmountOnTurnStart >= 1 (used as BOTH the guard and the card count) — The guard is ported as self.amount < 1 (powers.py) and the count as self.amount , where C# uses base.AmountOnTurnStart for both (HelloWorldPower.cs and).
- `power/hellraiser/AfterSideTurnEnd` — DORMANT — Re-executed the record's own claim by direct introspection (`vars()` on a live `HellraiserPower` instance, `hasattr` checks for `after_side_turn_end`/`after_enemy_side_end`) instead of citing its prose.
- `power/high_voltage/g1` — DORMANT — HighVoltagePower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` as the applier (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)`); the sim calls `PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)` with no…
- `power/high_voltage/g2` — DORMANT — HighVoltagePower.cs `participants.Contains(base.Owner)` — The sim substitutes `if not self.owner.is_dead` (powers.py) -- recurring gap shape 8, a guard the sim changes rather than drops.
- `power/illusion/g1` — DORMANT — IllusionPower.cs FollowUpStateId — Re-executed rather than cited: confirmed by direct class inspection that both of the sim's two `IllusionPower` appliers (`EyeWithTeeth`, `Parafright`) are single-move, non-`MachineMonster` classes, matching their C# sources' single self-looping…
- `power/inferno/g4` — DORMANT — InfernoPower.cs CombatState.HittableEnemies — The sim iterates `combat.enemies` filtered on `not enemy.is_gone` (powers.py) where C# uses HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs).
- `power/intangible/g1` — DORMANT — IntangiblePower.cs `!CombatManager.Instance.IsInProgress` -> unmodified — The sim has no combat-phase guard on any modifier hook. This is the power-level face of audit/records/seam/power_cmd.json's structural gap G6 (no IsEnding/CanReceivePowers backstop) and of hook_dispatch's gap G8 (no…
- `power/juggernaut/g2` — DORMANT — JuggernautPower.cs CombatState.HittableEnemies and the empty check — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs), so the sim aims at creatures the game…
- `power/juggling/AfterCardPlayed` — DORMANT — The copy is rebuilt from the class rather than cloned. JugglingPower.cs is `cardPlay.Card.CreateClone()`, which reproduces the card's full live state; powers.py constructs `type(card)()` and replays `card.upgrade_level` upgrades onto it.
- `power/mangle/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, , consumed at and) has NO sim counterpart at all.
- `power/mangle/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers.
- `power/nemesis/g1` — DORMANT — NemesisPower.cs `participants.Contains(base.Owner)` — Replaced by `if self.owner.is_dead: return` (powers.py) -- the same substitution as HighVoltage's and Territorial's, and one degree worse here, because the sim's early return also SKIPS THE TOGGLE (`_should_apply` is not flipped), so…
- `power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath` — DORMANT — ShouldCreatureBeRemovedFromCombatAfterDeath — Was a genuine unimplemented hook (`PainfulStabsPower.cs` had no sim counterpart), dormant under current content only because the power's one consumer (Test Subject) always pairs it with `AdaptablePower`'s equivalent OR-veto (`hooks.py`).
- `power/painful_stabs/g1` — DORMANT — PainfulStabsPower.cs the three AfterAttack guards — PainfulStabsPower.cs is `command.Attacker != base.Owner || command.TargetSide == base.Owner.Side || !command.DamageProps.IsPoweredAttack()`.
- `power/panache/AfterCardPlayed` — DORMANT — The sim iterates `combat.enemies` filtered on `not enemy.is_gone` where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs).
- `power/plow/AfterDamageReceived` — DORMANT — Right hook and right slot; the threshold matches exactly (`target != base.Owner || result.UnblockedDamage <= 0 || target.CurrentHp > base.Amount -> return`, PlowPower.cs, vs powers.py).
- `power/poison/AfterSideTurnStart` — DORMANT — STILL OPEN at (b) and (c). WHAT REMAINS: (b) TRIGGER COUNT -- C# loops `TriggerCount` times where the sim fires once (AccelerantPower is unported, so this stays a dormant gap); and (c) the DECREMENT GUARD -- C# decrements only `if (Owner.IsAlive)` while the sim always ticks, and the sim adds an…
- `power/rampart/g3` — DORMANT — RampartPower.cs `base.CombatState.Enemies.Where(c => c.Monster is TurretOperator)` — powers.py adds `and not enemy.is_gone` (recurring gap shape 8, a guard the sim ADDS).
- `power/ravenous/AfterDeath` — DORMANT — Confirmed the missing `applier=` is real (executed: `strength.applier is None` after a live Ravenous trigger) and re-ran the consumer census fresh rather than trusting the high_voltage cross-reference: `relics/unsettling_lamp.py` (the only `modify_power_amount_given_*` listener) and two…
- `power/ravenous/g1` — DORMANT — RavenousPower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, ..., base.Owner, null)`); the sim omits it, so `applier` is None through hooks.modify_power_amount (cmds.py), hooks.on_power_applied (cmds.py)…
- `power/reptile_trinket/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, , consumed at and) has NO sim counterpart at all.
- `power/reptile_trinket/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers.
- `power/rolling_boulder/g2` — DORMANT — RollingBoulderPower.cs CombatState.HittableEnemies (TestMode arm) — The sim iterates combat.enemies filtered on not enemy.is_gone (powers.py) where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs), so the sim aims at creatures…
- `power/sandpit/AfterRemoved` — DORMANT — The EFFECT is right and the MECHANISM is not. C#'s AfterRemoved (SandpitPower.cs) returns early on `oldOwner.IsDead || base.Target.IsDead`, hides the affected creatures, and `CreatureCmd.Kill(..., force: true)` every one that IsPlayer or is an Osty; the sim overrides `_expire`…
- `power/setup_strike/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, , consumed at and) has NO sim counterpart at all.
- `power/setup_strike/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers.
- `power/shackling_potion/g4` — DORMANT — TemporaryStrengthPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance (TemporaryStrengthPower.cs, , consumed at and) has NO sim counterpart at all.
- `power/shackling_potion/g5` — DORMANT — ITemporaryPower as a marker interface — The ITemporaryPower MARKER ITSELF is absent from the sim -- there is no is_temporary attribute, no InternallyAppliedPower, and no should_power_be_removed_on_death hook among hooks.py's 66 dispatchers.
- `power/shrink/AfterDeath` — DORMANT — The `wasRemovalPrevented` guard is missing. ShrinkPower.cs removes Shrink only when `!wasRemovalPrevented && creature == base.Applier`; the sim tests only `creature is self.applier` (powers.py).
- `power/shrink/AfterSideTurnEnd` — DORMANT — (a) The `!IsInfinite` guard (ShrinkPower.cs, i.e. Amount >= 0) is spelled `self.amount > 0` on both sim legs (powers.py,1394); those agree only because Amount == 0 is unreachable (ShouldRemoveDueToAmount removes at exactly 0), so this half is equivalent rather than identical.
- `power/shrink/AllowNegative` — DORMANT — ShrinkPower.cs declares `AllowNegative => true`; the sim's ShrinkPower never sets allow_negative, so it inherits False from Power (powers.py). That changes ShouldRemoveDueToAmount (PowerModel.cs): C# removes an AllowNegative power only at EXACTLY 0 and lets it sit negative, while…
- `power/skittish/AfterSideTurnEnd` — DORMANT — WHAT REMAINS is the side test: SkittishPower.cs acts only when `side != base.Owner.Side`, while powers.py resets on every player turn end regardless of the owner's side.
- `power/slippery/ModifyHpLostAfterOsty` — DORMANT — The formula is exact: `target != base.Owner -> amount`, `amount < 1m -> amount`, else `1m` (SlipperyPower.cs) vs powers.py. The BeforeOsty/AfterOsty phase collapse is already resolved as faithful by damage_pipeline (Osty redirection is waived, so its steps 8 and 11 fold into one…
- `power/sloth/BeforeCardPlayed` — DORMANT — WRONG SIDE OF THE PLAY. C# increments the counter in `BeforeCardPlayed` (SlothPower.cs), i.e. before the card resolves; the sim increments in `on_card_played`, after.
- `power/slow/ModifyDamageMultiplicative` — DORMANT — The factor matches (`1m + 0.1m * SlowAmount` at SlowPower.cs vs `1.0 + 0.1 * self._cards_this_turn` at powers.py) and `target != base.Owner -> 1m` matches, but the POWERED test does not: C# is `props.IsPoweredAttack()` (SlowPower.cs) and the sim is `card is not None and not…
- `power/speed_potion/g4` — DORMANT — TemporaryDexterityPower.cs IgnoreNextInstance — ITemporaryPower.IgnoreNextInstance / _shouldIgnoreNextInstance has NO sim counterpart. Its one caller is Misery.cs, which copies an enemy's debuffs and must not re-apply the wrapper's internal stat power.
- `power/speed_potion/g5` — DORMANT — ITemporaryPower as a marker interface — The marker itself is absent from the sim -- no is_temporary attribute, no InternallyAppliedPower, no should_power_be_removed_on_death among hooks.py's dispatchers.
- `power/speed_potion/g8` — DORMANT — The Dexterity leg's own observable consequence, as distinct from the family's slot verdict — Stated separately so the AfterSideTurnEnd verdict above is not read as more proven than it is, and re-labelled from an admission that the consequence is "UNPROVEN" to a positive dormancy argument with a…
- `power/strength/g3` — DORMANT — Sign-aware power typing on a negative Strength application — SIGN-AWARE TYPING (PROMPT.md bug class 3). GetTypeForAmount (PowerModel.cs, a third file not hashed by this record) returns PowerType.Debuff for this power at any NEGATIVE amount, because StackType == Counter && AllowNegative.
- `power/suck/g2` — DORMANT — Counting GROUPS with unblocked damage, not individual results — Re-executed rather than cited: confirmed FossilStalker is the power's sole applier in the entire C# source (not just the sim), and confirmed by reading `fossil_stalker.py` in full that none of its three moves is AoE (LASH's 2 hits…
- `power/surprise/AfterDeath` — DORMANT — Right hook and the right two spawns (`CreatureCmd.Add<SneakyGremlin>` then `<FatGremlin>`, SurprisePower.cs, vs powers.py in the same order, which matters because it fixes the enemy-list indices).
- `power/surrounded/AfterDeath` — DORMANT — The logic matches SurroundedPower.cs -- skip when the dead creature is on the owner's own side, then, if every remaining hittable enemy carries the SAME marker power, re-face on hittableEnemies[0] -- but the sim reads `[e for e in combat.enemies if not e.is_gone]` (powers.py) where…
- `power/surrounded/ModifyDamageMultiplicative` — DORMANT — The arithmetic and the facing logic are exact -- `dealer == null -> 1m`, `target != base.Owner -> 1m`, then 1.5x only if the dealer holds the marker power OPPOSITE the facing (SurroundedPower.cs vs powers.py), and 1.5 is dyadic so hook_dispatch G9 does not bite (`power_census.py…
- `power/surrounded/g1` — DORMANT — SurroundedPower.cs `!wasRemovalPrevented` — Absent from powers.py, which tests only the side. C# skips the re-facing entirely when a death's REMOVAL was prevented (the creature is still there, so the board did not change); the sim re-runs its `all(...)` scan anyway.
- `power/swipe/BeforeDeath` — DORMANT — HOOK SLOT: C# is `BeforeDeath`, fired at CreatureCmd.cs **before** `Hook.ShouldDie` and therefore before any death prevention; the sim uses `hooks.on_death`, fired at cmds.py only on the branch where should_die returned True.
- `power/tender/AfterCardPlayed` — DORMANT — The applier is dropped. TenderPower.cs applies Strength and Dexterity -1 with `applier: base.Applier` -- the creature that applied Tender -- and `silent: true`; powers.py calls PowerCmd.apply with no applier at all.
- `power/tender/AfterSideTurnEnd` — DORMANT — The registration-order witness is gone too: StampedePower moved to after_auto_post_play_phase_entered (powers.py), which combat.py fires strictly before this slot.
- `power/territorial/g1` — DORMANT — TerritorialPower.cs `applier: base.Owner` — MISSING `applier=`. C# passes `base.Owner` as the applier (`PowerCmd.Apply<StrengthPower>(choiceContext, base.Owner, base.Amount, base.Owner, null)`); the sim calls `PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)` with no…
- `power/territorial/g2` — DORMANT — TerritorialPower.cs `participants.Contains(base.Owner)` — Same substitution as HighVoltagePower's: the sim tests `not self.owner.is_dead` (powers.py) where C# tests side participation, which a retained corpse still satisfies.
- `power/the_bomb/g2` — DORMANT — TheBombPower.cs / CombatState.HittableEnemies — The sim iterates combat.enemies filtered on not enemy.is_gone where C# uses CombatState.HittableEnemies, which additionally consults Hook.ShouldAllowHitting (Creature.cs), so the sim aims at creatures the game considers unhittable…
- `power/unmovable/ModifyBlockMultiplicative` — DORMANT — Re-executed rather than left narrated: confirmed the reset DOES fire on an extra player turn (round_number unchanged, `_start_player_turn` is the shared entry point for both paths) — the record's mechanism claim is correct.
- `power/vigor/ModifyDamageAdditive` — DORMANT — The sim keeps only the FIRST of C#'s four guards. C# (VigorPower.cs) tests, in order: base.Owner != dealer (present, powers.py), !props.IsPoweredAttack() (present structurally -- cmds.py only runs the additive family for powered damage), `commandToModify != null && cardSource !=…
- `power/vital_spark/AfterPowerAmountChanged` — DORMANT — C# re-syncs every Tainted affliction's Amount to the power's new Amount from `AfterPowerAmountChanged` with a `power != this` guard (VitalSparkPower.cs), so it fires on ANY amount change -- a stack, a decrement, or an Unsettling-Lamp-doubled application.
- `power/vital_spark/AfterRemoved` — DORMANT — C#'s AfterRemoved clears every Tainted affliction on EVERY removal path (VitalSparkPower.cs, guarded by `oldOwner.CombatState == null`); the sim hangs the same sweep on `on_death` filtered to the owner (powers.py) and then calls `self._expire()`.
- `power/vital_spark/BeforeCombatStart` — DORMANT — The record's stated mechanism was wrong: CardCmd.Afflict (CardCmd.cs) does NOT overwrite. It refuses a different-type affliction via CanAfflict (AfflictionModel.cs, which the sim's own cmds.py CardCmd.afflict already ports) and STACKS a same-type one (CardCmd.cs).
- `power/vulnerable/ModifyDamageMultiplicative` — DORMANT — The base multiplier and both ported modifiers are right, but the value is computed in FLOAT where C# uses DECIMAL, which puts this hook inside hook_dispatch gap G9's blast radius.
- `power/vulnerable/g3` — DORMANT — CrueltyPower.cs `target == base.Owner` -> unmodified — Cruelty's own self-exclusion is dropped. C# skips the Cruelty bonus when the Vulnerable target IS the Cruelty holder; powers.py reads `dealer.powers.get('cruelty')` with no such test, so a Cruelty holder attacking its own…
- `power/vulnerable/g4` — DORMANT — VulnerablePower.cs DebilitatePower leg — DebilitatePower is not ported (`grep -c DebilitatePower sts2_rl/powers.py` returns 0), so the third link of C#'s modifier chain has no sim counterpart.
- `power/weak/ModifyDamageMultiplicative` — DORMANT — The sim returns the bare literal 0.75 and has no modifier chain at all, where WeakPower.cs threads DamageDecrease = 0.75m through PaperKrane (the TARGET's relic, -0.15m) and then DebilitatePower.
- `power/withering_presence/AfterCardPlayed` — DORMANT — The mechanism is right -- count the target player's card plays down from 6, add a Wither to HAND at 0, reset to 6 -- and the Wither's upgrade matching is preserved (`aeonglass.MatchWitherToUpgradeCount(wither)` at WitheringPresencePower.cs vs powers.py's `for _ in…

## `card` — 25 mechanisms

- `card/anointed/g2` — DORMANT — cards are moved to the hand with CardPileCmd.Add(cards, PileType.Hand) (Anointed.cs) vs direct list mutation — The sim pops each card out of `player.draw_pile` and appends to `player.hand` in place (colorless_skills.py) instead of routing through a pile-add verb, so nothing fires for…
- `card/apotheosis/g1` — DORMANT — the `allCard != this` self-exclusion, and whether the two AllCards sets are the same set (Apotheosis.cs) — C# `PlayerCombatState.AllCards` is `AllPiles.SelectMany(p => p.Cards)` (PlayerCombatState.cs) over Hand, Draw, Discard, Exhaust AND Play (PlayerCombatState.cs, quoted by…
- `card/breakthrough/g1` — DORMANT — the enemy loop skips on `enemy.is_dead`, not `enemy.is_gone` (breakthrough.py) — Every other AoE card in the sim filters on `not e.is_gone` (conflagration, shockwave, omnislice, sword_boomerang, rip_and_tear -- see `py audit/tools/card_probes.py dead-target-guards`), and `is_gone` is `is_dead…
- `card/brightest_flame/g1` — DORMANT — CROSS-RECORD DISAGREEMENT (rule 3): CreatureCmd.LoseMaxHp(..., isFromCard: true) is seam gap G6, which labels itself DORMANT; this card makes it LIVE — The seam's VERDICT (`gap`) is not disputed and is not re-verdicted here -- only its liveness label is.
- `card/conflagration/OnPlay` — DORMANT — Damage per hit, hit count, target set and the OUTER loop order are all faithful: `DamageCmd.Attack(2).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState)` (Conflagration.cs) runs `for (i = 0; i < attackCount; i++)` with the target list re-derived per hit…
- `card/dramatic_entrance/OnPlay` — DORMANT — The damage, the target set and the single hit are all faithful: `DamageCmd.Attack(11).FromCard(this).TargetingAllOpponents(CombatState)` (DramaticEntrance.cs) hits every living opponent once, and the sim's framework routing calls `on_play` once per living enemy because…
- `card/enlightenment/g1` — DORMANT — `reduceOnly` is evaluated LAZILY at cost-calculation time, so C# registers the modifier on EVERY hand card including those already at cost 0 or 1; the sim `continue`s past them (Enlightenment.cs vs event_cards.py) — `LocalCostModifier.IsReduceOnly` is documented as "should this…
- `card/expect_a_fight/g1` — DORMANT — the sim skips the gain entirely when there are no Attacks in hand (`if attacks > 0`, expect_a_fight.py); C# calls GainEnergy(0) — `PlayerCmd.GainEnergy(0, ...)` (ExpectAFight.cs) adds nothing but still runs the engine's gain path; the sim skips the call outright (`if attacks > 0`…
- `card/exterminate/OnPlay` — DORMANT — Damage per hit, hit count, target set and the hits-outer/enemies-inner loop order are all faithful against `DamageCmd.Attack(3).WithHitCount(4).FromCard(this).TargetingAllOpponents(CombatState)` (Exterminate.cs) -- AttackCommand runs `for (i = 0; i < attackCount; i++)` with the target list…
- `card/havoc/g2` — DORMANT — `forceExhaust: true` is reproduced by appending to the exhaust pile directly (havoc.py) — C# sets `item.ExhaustOnNextPlay = forceExhaust` (CardPileCmd.cs) and lets the play pipeline route the card to the exhaust pile, which means the card passes through PileType.Play first and lands in…
- `card/howl_from_beyond/OnPlay` — DORMANT — The damage and the single hit per enemy are faithful against `DamageCmd.Attack(16).FromCard(this).TargetingAllOpponents(CombatState)` (HowlFromBeyond.cs), and leaving `handles_own_routing` False is correct for a one-hit AoE -- the framework filters on `is_gone` (combat.py), the…
- `card/neows_fury/g1` — DORMANT — the chosen cards are moved with `CardPileCmd.Add(list, PileType.Hand)` in C# (NeowsFury.cs) and by direct list mutation in the sim (neows_fury.py) — The sim pops the chosen cards out of `player.discard_pile` and appends them to `player.hand` in place (neows_fury.py) instead of…
- `card/omnislice/g1` — DORMANT — the sim returns early when nothing got through (`if dealt <= 0: return`, colorless_attacks.py); C# proceeds whenever the DamageResult is non-null (Omnislice.cs) — C# proceeds whenever the DamageResult is non-null (Omnislice.cs) and would splash a value of 0, which damages…
- `card/pacts_end/OnPlay` — DORMANT — The gate and the damage are faithful: `CanDealDamage` is `CardPile.GetCards(Owner, PileType.Exhaust).Count() >= Cards.IntValue` (PactsEnd.cs) == `if len(ctx.player.exhaust_pile) < self._required_exhausted: return`, and the whole play is a no-op below the threshold on both sides.
- `card/pillage/g1` — DORMANT — the sim identifies the drawn card as `player.hand[-1]` (pillage.py) where C# uses the value the single-card Draw overload returns — C#'s single-card `CardPileCmd.Draw` overload RETURNS the card it drew (Pillage.cs) and the type test reads that value; the sim infers the drawn card from list…
- `card/primal_force/OnPlay` — DORMANT — The candidate set, the per-card upgrade and the index-preserving replacement are all faithful. C# selects `Hand.Cards.Where(c => c != null && c.IsTransformable && c.Type == CardType.Attack)` (PrimalForce.cs) and the sim's `if card.card_type != CardType.ATTACK: continue` is equivalent -- the…
- `card/purity/OnPlay` — DORMANT — The candidate set and the effect are faithful: `CardSelectCmd.FromHand(..., filter: null, source: this)` over the whole hand then `CardCmd.Exhaust` on each (Purity.cs) == `CardSelectCmd.from_hand(ctx.hooks, ctx.player, 'exhaust', count=self._cards)` then `ExhaustCmd.exhaust` on each, and…
- `card/rend/g1` — DORMANT — the ITemporaryPower exclusion is approximated by a single class (colorless_attacks.py) — C#'s `ShouldCountPower` is `power.TypeForCurrentAmount == PowerType.Debuff && !(power is ITemporaryPower)` (Rend.cs).
- `card/stomp/OnPlay` — DORMANT — The damage, the single hit per enemy and the target set are faithful against `DamageCmd.Attack(12).FromCard(this).TargetingAllOpponents(CombatState)` (Stomp.cs), and leaving `handles_own_routing` False is correct for a one-hit AoE -- the framework filters on `is_gone`, the right analogue…
- `card/the_bomb/g1` — DORMANT — C# dereferences the Apply result WITHOUT a null check; the sim re-fetches by id and skips on None (TheBomb.cs vs colorless_skills.py) — `PowerCmd.Apply<T>` documents three null cases (PowerCmd.cs): combat ending, `!target.CanReceivePowers`, and a stacking `ModifyAmount` that…
- `card/thunderclap/OnPlay` — DORMANT — The TWO-PASS structure is faithful and is the point of the card: C# resolves the whole attack first (`DamageCmd.Attack(4).FromCard(this).TargetingAllOpponents(CombatState)`, Thunderclap.cs) and only then applies Vulnerable to `CombatState.HittableEnemies` through the multi-target…
- `card/thunderclap/g1` — DORMANT — the sim `continue`s rather than breaking when an enemy is gone in the damage pass, and re-checks `ctx.player.is_dead` between the passes (thunderclap.py) — C#'s AttackCommand does skip non-alive targets by re-deriving `validTargets` (AttackCommand.cs) and does bail on…
- `card/toric_toughness/g1` — DORMANT — C# skips SetBlock when Apply returns NULL via `?.`; the sim re-fetches by id and skips on None (ToricToughness.cs vs event_cards.py) — Same mechanism and same verdict as card/crimson_mantle's and card/inferno's guards (rule 3): `PowerCmd.Apply<T>` returns null when combat is ending…
- `card/whirlwind/OnPlay` — DORMANT — The X-value plumbing, the hit count and the hits-outer/enemies-inner loop order are all faithful: `WithHitCount(ResolveEnergyXValue())` on `TargetingAllOpponents(CombatState)` (Whirlwind.cs, 42-45) == `for _ in range(self.captured_x)` with a per-hit living-enemy sweep, where `captured_x` is…

## `event` — 6 mechanisms

- `event/hungry_for_mushrooms/g3` — DORMANT — BigMushroom's +20 Max HP pickup effect is implemented on the EVENT, not on the relic. BigMushroom.cs AfterObtained calls CreatureCmd.GainMaxHp(MaxHpVar 20) — relics/big_mushroom.py has NO after_obtained override -- only modify_hand_draw -- and events/hungry_for_mushrooms.py applies…
- `event/neow/g8` — DORMANT — the RUN MODIFIERS branch is not ported. Neow.cs is a whole second mode: when RunState.Modifiers is non-empty the relic offer is REPLACED by one option per modifier that returns a GenerateNeowOption delegate, presented one at a time through OnModifierOptionSelected, which chains to the…
- `event/relic_trader/g5` — DORMANT — GenerateInitialOptions gates each option on `OwnedRelics.Count` ALONE (RelicTrader.cs), and Trade then indexes NewRelics at the same position (RelicTrader.cs) — events/relic_trader.py gates on `min(len(self._owned), len(self._new))`.
- `event/vakuu/g5` — DORMANT — UNIT GAP (dormant): Distinguished Cape's -9 Max HP is implemented on the EVENT OPTION instead of on the relic. DistinguishedCape.cs's AfterObtained() runs `CreatureCmd.LoseMaxHp(..., DynamicVars.HpLoss = 9, isFromCard: false)` and only then adds the 3 Apparitions; Vakuu.cs's…
- `event/war_historian_repy/g2` — DORMANT — DEFERRED PORT, leg 2 -- THE BODY. Nothing below GenerateInitialOptions is ported: events/war_historian_repy.py returns []. Unported: the two initial options UNLOCK_CAGE / UNLOCK_CHEST (WarHistorianRepy.cs); the second-reward page that offers the OTHER option ; UnlockCage's…
- `event/welcome_to_wongos/g8` — DORMANT — CheckObtainWongoBadge (WelcomeToWongos.cs) is not ported: the sim never grants WongoCustomerAppreciationBadge, and it tracks points on an ad-hoc attribute instead of run state — The badge is awarded when `SaveManager.Instance.Progress.WongoPoints % 2000 + pointsEarned >= 2000`…

## `relic` — 132 mechanisms

- `relic/_auto_keep` — DORMANT (sites: `relic/gambling_chip/AfterPlayerTurnStart`) — G1 (Sly auto-play) FLIPS from dormant-gap to faithful: gambling_chip.py no longer open-codes a discard loop -- it now calls the shared CardCmd.discard_and_draw (cmds.py), which implements the Sly-collect-and-auto-play tail in full.
- `relic/anchor/g3` — DORMANT — ordering against other BeforeCombatStart listeners — C# grants Anchor's block at step 3 (Hook.BeforeCombatStart, before StartTurn); the sim grants it at step 14's equivalent (the AfterBlockCleared loop, well inside turn-1 setup).
- `relic/archaic_tooth/AfterObtained` — DORMANT — Reasoning re-derived, verdict unchanged. G1 (upgrade-carry): Bash's max_upgrade_level is confirmed still 1 (default, unoverridden), so the sim's upgrade loop and C#'s single-call Upgrade agree for every reachable input.
- `relic/archaic_tooth/g1` — DORMANT — C# carries the upgrade with a single `if (starterCard.IsUpgraded) CardCmd.Upgrade(cardModel)` (ArchaicTooth.cs); the sim loops `for _ in range(original.upgrade_level)` (archaic_tooth.py) — C# grants exactly ONE upgrade level regardless of how many the original had; the sim grants…
- `relic/archaic_tooth/g2` — DORMANT — the sim adds a `can_enchant(transformed)` condition C# does not have, and MOVES the enchantment instead of cloning it (archaic_tooth.py vs ArchaicTooth.cs) — C# clones the enchantment (`(EnchantmentModel)starterCard.Enchantment.MutableClone()`) and enchants unconditionally; the sim…
- `relic/belt_buckle/AfterObtained` — DORMANT — BeltBuckle.cs applies the Dexterity immediately if the relic is picked up DURING a combat with no potions held. The sim's port defines only on_combat_start and on_potion_used, so a Belt Buckle obtained mid-combat grants nothing until the next combat -- and, per guard G2, not even then.
- `relic/belt_buckle/AfterPotionDiscarded` — DORMANT — The mirror of AfterPotionProcured: BeltBuckle.cs RE-APPLIES the Dexterity when discarding leaves the player potionless mid-combat. The sim implements on_potion_used but not a discard analogue, so the two ways of emptying the belt behave differently in the sim and identically in C#.
- `relic/bing_bong/AfterCardChangedPiles` — DORMANT — Rollup of guard G1 per binding rule 4. The core is right -- the deck-pile filter, the anti-recursion skip set, and the bottom-of-deck placement all match -- but C#'s `clonedBy == null` clause has no sim counterpart.
- `relic/booming_conch/AfterSideTurnStart` — DORMANT — G2 (energy-gain modifier-chain bypass) re-executed rather than re-read: the bypass is real (spied hooks.modify_energy_gain, zero calls), and the one power that could expose it (NoEnergyGainPower) can only be granted by a played card, which cannot predate this relic's own turn<=1…
- `relic/booming_conch/g2` — DORMANT — C# grants the energy through PlayerCmd.GainEnergy, which runs Hook.ModifyEnergyGain and Hook.AfterModifyingEnergyGain; the sim assigns player.energy directly (booming_conch.py) — MECHANISM: PlayerCmd.GainEnergy (PlayerCmd.cs) computes `finalAmount = Hook.ModifyEnergyGain(...)`, awaits…
- `relic/brilliant_scarf/TryModifyEnergyCostInCombatLate` — DORMANT — WHAT REMAINS is guard G3: ShouldModifyCost's other two clauses (BrilliantScarf.cs) -- the card's owner must be the relic's owner, and the card must currently be in the Hand or Play pile -- are still absent; the port checks only the counter, so the relic would zero the displayed cost of a…
- `relic/brilliant_scarf/g3` — DORMANT — the sim's modify_card_energy_cost drops ShouldModifyCost's owner check and its Hand/Play pile check (BrilliantScarf.cs) — C# refuses to modify a cost unless the card's owner is the relic's owner AND the card is currently in the Hand or Play pile; brilliant_scarf.py checks only the…
- `relic/byrdpip/AfterObtained` — DORMANT — Rollup of guards G1 and G3 per binding rule 4. The deck half of the Byrdonis Egg -> Byrd Swoop transform is faithful; the combat-pile half (G1) and the mid-combat SummonPet call (G3) are dropped.
- `relic/byrdpip/BeforeCombatStart` — DORMANT — Byrdpip.cs summons the pet at the start of EVERY combat. The port has no on_combat_start. Carries guard G3's verdict; see G3 for why the omission is observationally inert today.
- `relic/byrdpip/HasUponPickupEffect` — DORMANT — Byrdpip.cs declares `HasUponPickupEffect => true` and the sim's Relic base has the exact field for it (relics/base.py), which fourteen other ports set.
- `relic/byrdpip/SpawnsPets` — DORMANT — Byrdpip.cs declares `SpawnsPets => true`; relics/base.py has the field and the port leaves it False. DORMANT, enumerated: `git grep -n spawns_pets sts2_rl/*.py sts2_rl/**/*.py` (excluding .pyc) returns exactly two non-declaration hits in the whole sim -- relics/base.py (the field…
- `relic/byrdpip/g1` — DORMANT — the transform covers the deck only, not the combat piles — Byrdpip.cs collects every ByrdonisEgg from the Deck pile and, `if (CombatManager.Instance.IsInProgress)`, ALSO from `Owner.PlayerCombatState.AllCards` -- i.e.
- `relic/charons_ashes/AfterCardExhausted` — DORMANT — Re-executed rather than re-derived (already fully settled. No change to the verdict. A fresh, narrower witness in test/test_r14_relics_a.py confirms the surviving claim.
- `relic/charons_ashes/g1` — DORMANT — `HittableEnemies` vs `living_enemies()` — One verdict per mechanism (binding rule 3): this is the same call-site divergence audit/records/relic/bag_of_marbles.json records as its guard G2, with the same verdict.
- `relic/circlet/g4` — DORMANT — _refreshAllowed / RefreshRarity -- the deque-refill branch before the ladder — Whether the absence is a divergence depends on which bags are constructed with `refreshAllowed: true`, and this record did NOT enumerate the ctor's callers -- so the branch is recorded as an open question, not…
- `relic/claws/AfterObtained` — DORMANT — WHAT REMAINS is guard G2 alone, and it is still open: RE-VERIFIED against today's claws.py -- `after_obtained` still loops `for original in run.select_cards(...): ...
- `relic/claws/g2` — DORMANT — C# removes every original first and then appends the replacements in DECK-INDEX order; the sim removes and appends one card at a time in SELECTION order — MECHANISM: CardCmd.Transform(IEnumerable<CardTransformation>, rng) collects each original's pile and index, calls…
- `relic/darkstone_periapt/AfterCardChangedPiles` — DORMANT — Rollup of guard G2 (DORMANT) per binding rule 4; Executed (py audit/tools/relic_probes_b04.py darkstone): a curse transformed into another curse now takes Max HP 86 -> 92, and the probe prints 'DIVERGENCE: sim +6, C# +6'.
- `relic/darkstone_periapt/g2` — DORMANT — C# fires AfterCardChangedPiles for a card entering PileType.Deck at ANY time, including mid-combat; the sim's after_card_added_to_deck exists only on the out-of-combat RunState.add_card path — MECHANISM: CardPileCmd.cs and dispatch the hook from the general Add path, and PileType.Deck…
- `relic/demon_tongue/g2` — DORMANT — C# heals `result.UnblockedDamage`, which EXCLUDES OverkillDamage; the sim heals the raw `hp_lost`, which includes it — MECHANISM: DamageResult.cs documents UnblockedDamage as the damage the target received after blocking and OverkillDamage as the excess past 0 HP, and they are separate fields…
- `relic/dusty_tome/AfterObtained` — DORMANT — Rollup of guards G1 (the unguarded Card.upgrade, dormant), G2 (the lazy re-roll, LIVE on the runner path) and N2 (the added HasUponPickupEffect declaration) per binding rule 4.
- `relic/dusty_tome/g1` — DORMANT — `CardCmd.Upgrade(card)` skips a card whose IsUpgradable is false (DustyTome.cs); dusty_tome.py's `card.upgrade()` is a bare `upgrade_level += 1` with no guard (PROMPT.md class 14) — MECHANISM: CardCmd.Upgrade filters on IsUpgradable == `CurrentUpgradeLevel < MaxUpgradeLevel`…
- `relic/dusty_tome/g6` — DORMANT — the sim ADDS `has_upon_pickup_effect = True` (dusty_tome.py) where DustyTome.cs declares no HasUponPickupEffect override — MECHANISM: RelicModel.HasUponPickupEffect defaults to false and DustyTome does not override it -- contrast DistinguishedCape.cs and DollysMirror.cs in this same…
- `relic/electric_shrymp/g4` — DORMANT — run.select_cards falls back to `self.rng.sample` when no card_selector is installed (run.py), where C# opens a player-choice screen and draws no RNG at all — PROMPT.md bug class 16's second half at an out-of-combat site: C#'s FromDeckForEnchantment consumes no Rng…
- `relic/ember_tea/g1` — DORMANT — C#'s AfterRoomEntered runs strictly BEFORE every BeforeCombatStart listener; the sim's on_combat_start runs interleaved with them in relic-registration order — MECHANISM: CombatRoom.cs calls CombatManager.SetUpCombat and then Hook.AfterRoomEntered; Hook.BeforeCombatStart is only reached…
- `relic/empty_cage/AfterObtained` — DORMANT — Rollup of guard N2 per binding rule 4. The count (CardsVar(2), EmptyCage.cs, vs CARDS = 2, empty_cage.py), the candidate filter (N1) and the removal itself all match -- executed: a fresh run's 10-card deck goes to 8.
- `relic/empty_cage/g2` — DORMANT — run.select_cards falls back to `self.rng.sample` when no card_selector is installed (run.py), where the game opens a removal screen and draws no RNG — Same mechanism and same verdict as relic/electric_shrymp guard N3 in this batch (binding rule 3): C#'s FromDeckGeneric…
- `relic/fake_anchor/g3` — DORMANT — the ordering window -- C# grants the block at turn_structure step 3, the sim at the step-14 AfterBlockCleared loop, and anything between the two that reads player Block sees 4 in C# and 0 in the sim — Same mechanism as relic/anchor's guard N3 and carried with the same gap verdict per binding…
- `relic/fake_snecko_eye/AfterObtained` — DORMANT — MECHANISM: FakeSneckoEye.cs applies the Confused power immediately when the relic is picked up if `CombatManager.Instance.IsInProgress`, so a Fake Snecko Eye obtained mid-combat confuses you for the rest of that fight.
- `relic/festive_popper/g2` — DORMANT — `combatState.HittableEnemies` (FestivePopper.cs) vs the sim's living_enemies() (festive_popper.py) — Identical mechanism to relic/bag_of_marbles guard G2 and carried with the same gap verdict per binding rule 3, at another turn-1 all-enemies effect.
- `relic/forgotten_soul/AfterCardExhausted` — DORMANT — Rollup of guard G1 per binding rule 4. Every number and stream matches -- DamageVar(1m, ValueProp.Unpowered) (ForgottenSoul.cs) is DAMAGE = 1 with DamageProps.NON_CARD_UNPOWERED (= ValueProp.UNPOWERED, valueprops.py), the dealer is the player's own creature on both sides, and…
- `relic/fragrant_mushroom/AfterObtained` — DORMANT — WHAT REMAINS is guard G2, DORMANT: FragrantMushroom.cs routes the 15 through `CreatureCmd.Damage(..., Unblockable|Unpowered, ...)`, i.e. the full damage command with its run-level Hook pipeline and death check, while the port still calls `run.lose_hp(15)` (sts2_rl/run.py), which runs…
- `relic/fragrant_mushroom/g2` — DORMANT — `CreatureCmd.Damage(ThrowingPlayerChoiceContext, Owner.Creature, HpLoss.BaseValue, Unblockable|Unpowered, null, null)` (FragrantMushroom.cs) vs `run.lose_hp(15)` (fragrant_mushroom.py) — MECHANISM: the source routes the 15 through the full damage command even out of combat, so the…
- `relic/fresnel_lens/g2` — DORMANT — `EnchantCard` clones the card first (`base.Owner.RunState.CloneCard(card)`, FresnelLens.cs) and enchants the CLONE, then hands it back via `option.ModifyCard(...)` / `out newCard` — PROMPT.md bug class 17 (shallow clones) applies to whoever implements this relic, so it is recorded now rather…
- `relic/frozen_egg/g3` — DORMANT — the sim upgrades the ORIGINAL card object where C# substitutes an upgraded CloneCard (FrozenEgg.cs; EggRelicHelper.cs) — PROMPT.md bug class 17 at the egg relics' two sites.
- `relic/fur_coat/AfterCreatureAddedToCombat` — DORMANT — Stays open ONLY via the inherited BeforeCombatStart guards (act check / SetCurrentHp substitution), which are a different mechanism id and not this entry's to close.
- `relic/fur_coat/g3` — DORMANT — `CreatureCmd.SetCurrentHp(item, 1m)` (FurCoat.cs, 139) vs the sim's raw `enemy.hp = 1` (fur_coat.py, 87) — MECHANISM: CreatureCmd.SetCurrentHp (CreatureCmd.cs) does three things the raw assignment does not -- it fires `Hook.AfterCurrentHpChanged(runState, combatState, creature…
- `relic/gambling_chip/g1` — DORMANT — CardCmd.DiscardAndDraw auto-plays every discarded card that `IsSlyThisTurn`, AFTER the draw (CardCmd.cs); the sim's loop has no Sly concept — MECHANISM: DiscardAndDraw collects `if (card.IsSlyThisTurn) slyCards.Add(card)` while discarding (CardCmd.cs), draws, and then `foreach…
- `relic/gambling_chip/g2` — DORMANT — each discard goes through `CardPileCmd.Add(card, discardPile)` in C# (CardCmd.cs) where the sim mutates the two lists directly (gambling_chip.py) — MECHANISM: CardPileCmd.Add runs the game's pile-change machinery -- Hook.ShouldAddToDeck / Hook.ModifyCardBeingAddedToDeck for deck adds…
- `relic/ghost_seed/AfterCardEnteredCombat` — DORMANT — Rollup of guard G2 per binding rule 4. The predicate and the effect match -- GhostSeed.cs applies CardKeyword.Ethereal to any card CanAffect accepts -- but C#'s `CardCmd.ApplyKeyword` adds a keyword whose SOURCE is tracked (KeywordSources.Local), while the sim sets a single boolean…
- `relic/ghost_seed/AfterRoomEntered` — DORMANT — See guard G1. GhostSeed.cs filters `room is CombatRoom` and then sweeps `Owner.PlayerCombatState.AllCards`; the sim iterates `self.player.all_cards` at on_combat_start.
- `relic/ghost_seed/g1` — DORMANT — the sweep runs at BeforeCombatStart in the sim and at AfterRoomEntered in C#, two dispatch points earlier — MECHANISM: the C# order is SetUpCombat -> Hook.AfterRoomEntered (CombatRoom.cs) -> AfterCombatRoomLoaded -> StartCombatInternal, which runs `Hook.AfterCreatureAddedToCombat` for…
- `relic/ghost_seed/g2` — DORMANT — `!card.GetKeywordsWithSources(KeywordSources.Local).Contains(Ethereal)` (GhostSeed.cs) vs the sim's single `not card.is_ethereal` boolean — MECHANISM: C# tracks WHERE each keyword came from, and CanAffect only refuses a card that already has a LOCALLY sourced Ethereal -- a card that is…
- `relic/girya/AfterRoomEntered` — DORMANT — See guard G2. Girya.cs applies StrengthPower equal to TimesLifted when `TimesLifted > 0 && room is CombatRoom`; girya.py does the same at combat start, two dispatch points later (C#'s AfterRoomEntered for a combat room fires at CombatRoom.cs, before StartCombatInternal's…
- `relic/girya/g2` — DORMANT — the Strength lands at BeforeCombatStart in the sim and at AfterRoomEntered in C#, two dispatch points earlier -- and the sim's slot is interleaved with other relics' on_combat_start by registration order where C#'s always precedes every BeforeCombatStart listener — MECHANISM…
- `relic/glitter/g1` — DORMANT — `base.Owner.RunState.CloneCard(card)` then `CardCmd.Enchant<Glam>(card2, 1m)` then `cardReward.ModifyCard(card2, this)` (Glitter.cs) vs `GlamEnchantment().attach(card)` in place (glitter.py) — PROMPT.md bug class 17.
- `relic/gremlin_horn/AfterDeath` — DORMANT — REASONING REPLACED at the hooks-level rollup. Re-confirmed directly: neither IllusionPower nor AdaptablePower defines should_die; both define should_remove_from_combat_after_death, and an executed two-enemy kill confirms the payout lands on a real Illusion death.
- `relic/gremlin_horn/g2` — DORMANT — the sim resolves death INSIDE the damage pipeline, before the dealer's post-damage event; C# defers Kill() until after AfterDamageGiven and AfterDamageReceived have run for every target of the batch — MECHANISM: CreatureCmd.cs runs AfterDamageGiven, then the killing-blow-guarded…
- `relic/hand_drill/g1` — DORMANT — C# orders AfterBlockBroken listeners BEFORE AfterDamageGiven listeners for the same damage result; the sim puts Hand Drill on the same event as the AfterBlockBroken listener and lets registration order decide — MECHANISM: CreatureCmd.cs runs `Hook.AfterBlockBroken` and then…
- `relic/hand_drill/g2` — DORMANT — the C# guard is `dealer == base.Owner.Creature || dealer?.PetOwner == base.Owner` -- the port drops the PET arm entirely (hand_drill.py is `dealer is not self.player`) — MECHANISM: HandDrill.cs credits the owner's PET's damage to the owner, so an Osty (or any relic-granted pet) that breaks…
- `relic/happy_flower/g3` — DORMANT — PlayerCmd.GainEnergy's `Hook.AfterModifyingEnergyGain` companion event and its `finalAmount > 0` gate (PlayerCmd.cs) have no counterpart in the sim's EnergyCmd.gain (cmds.py) — MECHANISM: C# folds Hook.ModifyEnergyGain, then fires AfterModifyingEnergyGain over the listeners that…
- `relic/intimidating_helmet/g3` — DORMANT — the SLOT -- C# fires BeforeCardPlayed after the card has been added to the Play pile and after GeneratePlayCount; the sim fires on_energy_spent immediately after deducting the energy, before the card leaves the hand — MECHANISM: CardModel.OnPlayWrapper does CardPileCmd.AddDuringManualCardPlay ->…
- `relic/jeweled_mask/g3` — DORMANT — SetToFreeThisTurn is `EndOfTurn | WhenPlayed` in C#; the sim's _free_this_turn expires only at the next turn start — MECHANISM: CardModel.SetToFreeThisTurn (CardModel.cs) adds a LocalCostModifier with `LocalCostModifierExpiration.EndOfTurn | LocalCostModifierExpiration.WhenPlayed`…
- `relic/jeweled_mask/g4` — DORMANT — the port moves the card with two list operations (`draw_pile.remove` / `hand.append`, jeweled_mask.py) instead of the sim's CardPileCmd, so it bypasses the hand cap — MECHANISM: C# calls `CardPileCmd.Add(cardModel, PileType.Hand)` (JeweledMask.cs), which goes through the pile machinery…
- `relic/kusarigama/AfterCardPlayed` — DORMANT — Re-derived (not trusted) that the fix is currently unobservable: every ported `should_allow_hitting` implementer only fires post-death, so `hittable_enemies() == living_enemies()` for every reachable state today (pinned by `test_reviving_enemy_is_still_is_gone_today`).
- `relic/kusarigama/g2` — DORMANT — `Owner.Creature.CombatState.HittableEnemies` (Kusarigama.cs) vs the sim's living_enemies() (kusarigama.py) — C# picks the random target from `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is `!IsDead && Hook.ShouldAllowHitting(CombatState, this)`…
- `relic/lantern/g1` — DORMANT — `PlayerCmd.GainEnergy(amount, player)` (Lantern.cs) vs `EnergyCmd.gain(self.hooks, player, 1)` (lantern.py) -- the missing AfterModifyingEnergyGain companion and the `finalAmount > 0` / `IsEnding` guards — EnergyCmd.gain now opens with an is_ending(hooks) bail, mirroring…
- `relic/lasting_candy/AfterCombatEnd` — DORMANT — LastingCandy.cs is the `CombatsSeen++` counter that decides 'every other combat' (IsInTriggeringCombat = `CombatsSeen > 0 && CombatsSeen % 2 == 0`, LastingCandy.cs).
- `relic/lava_lamp/g2` — DORMANT — C# UPGRADES A CLONE -- `RunState.CloneCard(card)` then `CardCmd.Upgrade(card2)` then `cardReward.ModifyCard(card2, this)` (LavaLamp.cs) -- and the sim has no clone helper — PROMPT.md bug class 17.
- `relic/leafy_poultice/g3` — DORMANT — `CreatureCmd.LoseMaxHp` routes the excess current HP through the FULL damage pipeline; RunState.lose_max_hp just clamps — CreatureCmd.LoseMaxHp (src/Core/Commands/CreatureCmd.cs) computes an UNFLOORED newMaxHp = MaxHp - amount and, when that is below CurrentHp, deals the difference as…
- `relic/letter_opener/AfterCardPlayed` — DORMANT — Same fix and same reasoning as kusarigama. Additionally found that `DamageCmd.deal` itself backstops `should_allow_hitting` (`cmds.py`), a second, independent reason the pre-fix code was already unobservable via raw HP — the candidate-set bug was strictly "iterates and calls deal on a…
- `relic/letter_opener/g2` — DORMANT — `Owner.Creature.CombatState.HittableEnemies` (LetterOpener.cs) vs the sim's living_enemies() (letter_opener.py) — C# damages `Enemies.Where(e => e.IsHittable)` -- `!IsDead && Hook.ShouldAllowHitting(...)` (src/Core/Combat/CombatState.cs…
- `relic/lost_coffer/g4` — DORMANT — `CardCreationFlags.IsCardReward` is set by CardReward's constructor (CardReward.cs); the sim has no card-creation flag concept at all — The flag exists so that relics which affect card REWARDS only (CardCreationFlags.cs names Prismatic Gem and Dingy Rug) can tell a reward roll from…
- `relic/meat_cleaver/TryModifyRestSiteOptions` — DORMANT — Guard G1 is NOT part of the gap -- it is `deliberate-divergence` (the sim omits a disabled option rather than adding one greyed out; same reachable action set, since the sim has no rest-site UI to show the grey row).
- `relic/meat_cleaver/g1` — DORMANT — CookRestSiteOption's card-removal screen is `Cancelable = true` and a cancel makes the whole option a no-op (CookRestSiteOption.cs); the sim's cook always removes 2 cards and always grants the 9 Max HP — MECHANISM: CookRestSiteOption.OnSelect builds…
- `relic/miniature_cannon/ModifyDamageAdditive` — DORMANT — No action taken.
- `relic/miniature_cannon/g1` — DORMANT — `if (dealer != base.Owner.Creature && cardSource.Owner != base.Owner) return 0` (MiniatureCannon.cs) is an AND, so C# adds the damage when EITHER the dealer is the owner OR the card belongs to the owner; the port keeps only the first disjunct — MECHANISM: miniature_cannon.py requires…
- `relic/miniature_tent/g1` — DORMANT — C# aggregates this hook over `runState.IterateHookListeners(null)` -- deck cards, powers and modifiers as well as relics -- and the sim iterates `self.relics` only — MECHANISM: Hook.ShouldDisableRemainingRestSiteOptions (Hook.cs) walks every hook listener…
- `relic/molten_egg/ModifyMerchantCardCreationResults` — DORMANT — Same body as the reward path in C# too -- MoltenEgg.cs calls the identical EggRelicHelper.UpgradeValidCards (no CurrentUpgradeLevel check anywhere in that helper, EggRelicHelper.cs) -- and notably has NO NoHookUpgrades check, so the delegation is faithful in shape.
- `relic/molten_egg/g4` — DORMANT — the sim applies Molten Egg's already-upgraded refusal to ALL THREE paths; C# applies it ONLY to the deck-add path, because EggRelicHelper.UpgradeValidCards has no upgrade-level check — MECHANISM: the reward and merchant paths both go through `EggRelicHelper.UpgradeValidCards(cards…
- `relic/molten_egg/g9` — DORMANT — the sim has ONE modify_card_reward_options pass where C# runs TryModifyCardRewardOptions and then TryModifyCardRewardOptions**Late** as two complete passes — MECHANISM: Hook.TryModifyCardRewardOptions (Hook.cs) walks every listener's non-Late override and then walks every listener's…
- `relic/new_leaf/AfterObtained` — DORMANT — Rollup of guards N1 and G1 per binding rule 4. Count, selection prompt and deck placement are all faithful; the named Niche RNG stream is dropped (N1, live for RNG parity) and the candidate list omits C#'s Quest-card exclusion (G1, dormant).
- `relic/new_leaf/g2` — DORMANT — CardSelectCmd.FromDeckForTransformation also excludes Quest cards; run.transformable_cards() filters only Eternal — MECHANISM: CardSelectCmd.FromDeckForTransformation (CardSelectCmd.cs) builds its candidate list as `Cards.Where(c => c.Type != CardType.Quest && c.IsTransformable)`.
- `relic/nunchaku/g5` — DORMANT — `PlayerCmd.GainEnergy` (Nunchaku.cs) runs Hook.ModifyEnergyGain, then Hook.AfterModifyingEnergyGain, then a `finalAmount > 0` check (PlayerCmd.cs); EnergyCmd.gain (cmds.py) runs the modify chain and adds unconditionally — Observed at the ENERGY dispatcher: the sim's…
- `relic/old_coin/g3` — DORMANT — `PlayerCmd.GainGold`'s companion event `Hook.AfterModifyingGoldGained` (PlayerCmd.cs) has no sim counterpart — Observed at the GOLD dispatcher: run.gain_gold (run.py) chains modify_gold_gained over the run's relics and returns a bare number, with no modifiers list and no companion event.
- `relic/paels_legion/g3` — DORMANT — the sim adds a `target is not self.player` check that C#'s ModifyBlockMultiplicative does not have — MECHANISM: PaelsLegion.cs checks props, cardSource and cardSource.Owner -- and NOTHING about the target.
- `relic/paper_phrog/ModifyVulnerableMultiplier` — DORMANT — The rollup's G1 dispatch-set text is confirmed accurate and unchanged. NEW: found and enumerated a second, previously unrecorded DORMANT divergence — `PaperPhrog.cs`'s `target == Owner.Creature` self-damage bail has no sim analogue because `modify_vulnerable_multiplier`'s signature carries…
- `relic/paper_phrog/g1` — DORMANT — C# consults the dealer's phrog ONCE by direct lookup; the sim runs a hook chain over every combat listener, so N copies of the relic would each add 0.25 — MECHANISM: VulnerablePower.cs does `dealer.Player?.GetRelic<PaperPhrog>()` and calls the method on that single instance, so the bonus…
- `relic/paper_phrog/g3` — DORMANT — `if (target == base.Owner.Creature) return amount;` (PaperPhrog.cs) -- no bonus when the phrog's own owner is the Vulnerable creature; the sim checks only the dealer — MECHANISM: paper_phrog.py is `if dealer is self.player`, with no target check.
- `relic/pen_nib/g3` — DORMANT — C# skips Hook.AfterCardPlayed entirely when the play ended the combat (CardModel.cs gates on CombatManager.IsInProgress) while combat.py always fires it, so a game-side 10th Attack that lands the killing blow stays MARKED and the sim's does not — MECHANISM: the mark (AttackToDouble /…
- `relic/philosophers_stone/AfterCreatureAddedToCombat` — DORMANT — Re-executed rather than re-derived. No change: the sim's CombatState models no player-side creature other than the player, so the side-vs-identity substitution in the skip clause cannot currently misclassify anything.
- `relic/philosophers_stone/g1` — DORMANT — C# skips any creature on the OWNER's SIDE (PhilosophersStone.cs); the sim skips only the player OBJECT (philosophers_stone.py), so a player-side creature that is not the player would be strengthened in the sim and not in the game — MECHANISM: `if (creature.Side == base.Owner.Creature.Side)…
- `relic/prismatic_gem/g1` — DORMANT — the four early-return clauses of ModifyCardRewardCreationOptions (PrismaticGem.cs) select exactly the case the waiver above depends on -- and one of them is the residual risk — MECHANISM: C# bails on NoCardPoolModifications, on !IsCardReward, on `options.CustomCardPool != null` and on…
- `relic/prismatic_gem/g2` — DORMANT — modify_max_energy is evaluated BEFORE should_reset_energy in the sim and inside the chosen branch in C# — One verdict per mechanism (binding rule 3): the seam records it as a DORMANT gap because both sim dispatchers are pure aggregations and no ported should_reset_energy or modify_max_energy…
- `relic/rainbow_ring/AfterCardPlayed` — DORMANT — The port still latches BEFORE the two PowerCmd.apply calls (`sts2_rl/relics/rainbow_ring.py`: `self._activated = True` is set, then Strength then Dexterity are applied), where C# increments `ActivationCountThisTurn` only AFTER both awaits resolve (RainbowRing.cs) -- unchanged.
- `relic/rainbow_ring/g1` — DORMANT — C# increments ActivationCountThisTurn AFTER awaiting both PowerCmd.Apply calls (RainbowRing.cs); the sim sets `_activated = True` BEFORE them (rainbow_ring.py) — MECHANISM: C#'s guard is `ActivationCountThisTurn < 1` (RainbowRing.cs) and the counter is only bumped at line 119…
- `relic/red_skull/g3` — DORMANT — C#'s AfterCurrentHpChanged has NO `creature == Owner.Creature` check (RedSkull.cs); the sim gates on `creature is self.player` (red_skull.py) — MECHANISM: C# re-evaluates the owner's threshold whenever ANY creature's HP changes during combat -- an enemy taking damage re-runs…
- `relic/ruined_helmet/g2` — DORMANT — C#'s RECEIVED-side predicate chain is a separately-sequenced phase; the sim has one flat registration-order chain — One verdict per mechanism, binding rule 3; the seam owns the machinery and this record owns the relic's observable.
- `relic/ruined_helmet/g3` — DORMANT — the 'mark used' side effect is hand-inlined into the modifier, so it fires at a point C# would not have reached — Binding rule 3: verdict matched, not re-derived.
- `relic/sai/g1` — DORMANT — AfterSideTurnStart is C#'s SECOND turn-start pass and the sim runs one flat walk (seam guard G12, PROMPT.md class 25) — MECHANISM: Hook.AfterSideTurnStart runs every listener's AfterSideTurnStart and then every listener's AfterSideTurnStartLate as two complete passes (Hook.cs), and it…
- `relic/seal_of_gold/g2` — DORMANT — AfterSideTurnStart is C#'s second turn-start pass and the sim runs one flat walk (seam guard G12, PROMPT.md class 25) — MECHANISM as recorded for relic/sai in this batch: Hook.AfterSideTurnStart is a complete pass that runs after every step-22 Hook.AfterPlayerTurnStart listener and is followed…
- `relic/self_forming_clay/g3` — DORMANT — the sim has no SelfFormingClayPower at all, so the pending Block is not a visible, stackable, removable power on the player — MECHANISM: `grep -rn SelfFormingClay sts2_rl/powers.py` returns nothing -- the sim models the effect as a private int on the relic.
- `relic/shovel/TryModifyRestSiteOptions` — DORMANT — Rollup of guard G2 per binding rule 4. The DIG option's effect matches -- RelicCmd.Obtain(RelicFactory.PullNextRelicFromFront(Owner)) (DigRestSiteOption.cs) maps to run.obtain_relic_from_grab_bag() (shovel.py), and the default overload's Rewards-stream rarity roll is what…
- `relic/shovel/g2` — DORMANT — the sim refuses to OFFER the DIG option when the grab bag is empty; C# always offers it and grants RelicFactory.FallbackRelic instead — MECHANISM: Shovel.TryModifyRestSiteOptions adds `new DigRestSiteOption(player)` unconditionally (Shovel.cs) and DigRestSiteOption overrides nothing that…
- `relic/signet_ring/g2` — DORMANT — Hook.AfterModifyingGoldGained (PlayerCmd.cs) has no sim counterpart — MECHANISM: C#'s gold pipeline is the same two-phase shape as its damage and power pipelines -- ModifyGoldGained collects the listeners that changed the amount, then AfterModifyingGoldGained notifies exactly those listeners…
- `relic/silver_crucible/ShouldGenerateTreasure` — DORMANT — G3 re-executed against the CURRENT RunState.enter_point (the audit's own citation of "enter_room"/"run.py" is itself stale -- the method is enter_point and has moved).
- `relic/silver_crucible/g3` — DORMANT — a suppressed treasure room still pays out Spoils Map in the sim — MECHANISM: C# reaches the Spoils Map payout only from INSIDE the gated reward routine -- OneOffSynchronizer.DoTreasureRoomRewards opens with `if (!Hook.ShouldGenerateTreasure(player.RunState, player)) return 0;`…
- `relic/sling_of_courage/AfterRoomEntered` — DORMANT — Rollup of guard N1 per binding rule 4. SlingOfCourage.cs applies PowerVar<StrengthPower>(2) from AfterRoomEntered when `room.RoomType == RoomType.Elite`, and for a CombatRoom that hook fires after CombatManager.SetUpCombat and BEFORE Hook.BeforeCombatStart (CombatRoom.cs) -- so C#…
- `relic/sling_of_courage/g1` — DORMANT — the slot move -- C# guarantees the Strength lands BEFORE every BeforeCombatStart listener; the sim puts it INSIDE that pass — MECHANISM: for a CombatRoom, `Hook.AfterRoomEntered` fires at CombatRoom.cs, between SetUpCombat (line 225) and AfterCombatRoomLoaded (line 230), which starts the…
- `relic/snecko_eye/AfterObtained` — DORMANT — SneckoEye.cs applies the Confused power immediately when the relic is picked up DURING a combat (`if (CombatManager.Instance.IsInProgress) await ApplyPower()`).
- `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — DORMANT — Only G3 (X-cost bail) remains open, re-confirmed dormant: still zero X-cost Power cards in the pool. Propose narrowing the hooks-level issue text to name G3 alone.
- `relic/spiked_gauntlets/g2` — DORMANT — the hook has a PLAIN pass and a LATE pass and the sim has neither — Hook.ModifyEnergyCostInCombat runs TWO complete listener passes -- every TryModifyEnergyCostInCombat, then every TryModifyEnergyCostInCombatLate (Hook.cs).
- `relic/spiked_gauntlets/g3` — DORMANT — the sim drops the `card.Owner.Creature != base.Owner.Creature` guard AND the dispatcher's `originalCost < 0` X-cost bail; it adds a final max(0, cost) clamp C# does not have — (a) The owner guard (SpikedGauntlets.cs) is multiplayer-only and is separately waived at N1.
- `relic/stone_calendar/BeforeSideTurnEnd` — DORMANT — REASONING REPLACED at the hooks-level rollup, same shape as gremlin_horn's. Re-confirmed directly: HookSystem.on_player_turn_end's source dispatches through self._each("on_player_turn_end") today.
- `relic/stone_calendar/g2` — DORMANT — `combatState.HittableEnemies` (StoneCalendar.cs) vs the sim's living_enemies() (stone_calendar.py) — Same mechanism and therefore the same verdict as relic/bag_of_marbles guard G2 (binding rule 3): C# targets `Enemies.Where(e => e.IsHittable)` (CombatState.cs), and IsHittable is…
- `relic/stone_cracker/AfterRoomEntered` — DORMANT — Re-executed rather than re-derived. No staleness found in this entry's hooks-level text (already correctly narrowed to G2 only in. G2's pool-wide census re-run against the current tree: still exactly two on_combat_start implementers touch the draw pile (stone_cracker, tea_of_discourtesy), on…
- `relic/stone_cracker/g2` — DORMANT — the C# hook is AfterRoomEntered, which runs one full dispatch BEFORE Hook.BeforeCombatStart; the port uses on_combat_start — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE ported relics whose C# combat effect hangs off `AfterRoomEntered` with a `room…
- `relic/stone_humidifier/AfterRestSiteHeal` — DORMANT — Rollup of guard G1 per binding rule 4, which this record already labels dormant and unchanged. RE-VERIFIED: `grep -n mend sts2_rl/run.py sts2_rl/rest_site.py` finds no Mend rest-site option anywhere in the sim -- the only hit is an unrelated comment about Pillow at run.py -- and…
- `relic/stone_humidifier/g1` — DORMANT — Hook.AfterRestSiteHeal has TWO dispatch sites in C# and the sim ports only one — MECHANISM: an executed grep for AfterRestSiteHeal over the decompiled source finds two callers outside the relic models -- HealRestSiteOption.cs (`isMimicked` forwarded from the option) and…
- `relic/strike_dummy/g2` — DORMANT — C# grants the +3 when EITHER the dealer is the owner's creature OR the Strike card BELONGS to the owner; the port requires the dealer — MECHANISM: StrikeDummy.cs is `if (dealer != base.Owner.Creature && cardSource.Owner != base.Owner) return 0m;` -- a conjunction of negatives, so either…
- `relic/sword_of_jade/AfterRoomEntered` — DORMANT — Re-executed rather than re-derived. G1's pool-wide census (AfterRoomEntered-vs-on_combat_start dispatch collapse, shared by the same twelve relics as stone_cracker's G2) re-confirmed against the current ALL_RELICS registry
- `relic/sword_of_jade/g1` — DORMANT — the C# hook is AfterRoomEntered, which runs a full dispatch BEFORE Hook.BeforeCombatStart; the port uses on_combat_start — POOL-WIDE SHAPE (executed census, py audit/tools/relic_probes_b15.py b15-censuses): TWELVE ported relics whose C# combat effect hangs off `AfterRoomEntered` with a `room is…
- `relic/tea_of_discourtesy/g2` — DORMANT — the port skips CardPileCmd._enter_combat, so the two generated Dazed are never registered as combat hook listeners and AfterCardEnteredCombat never fires for them — MECHANISM: C# creates the card with `combatState.CreateCard<T>(player)` (CardPileCmd.cs) and adds it through…
- `relic/the_boot/g2` — DORMANT — C# gates on `props.IsPoweredAttack()`; the sim's modify_hp_lost signature carries no props at all, so the port substitutes `card is None or card.is_unpowered` — MECHANISM: ValuePropExtensions.IsPoweredAttack (ValuePropExtensions.cs) is `props.HasFlag(Move) && !props.HasFlag(Unpowered)` -- a…
- `relic/touch_of_orobas/AfterObtained` — DORMANT — Rollup of guards G1 and N4 per binding rule 4. The core behaviour is right and executed: the starter relic is replaced IN PLACE by its refinement and the replacement's own after_obtained runs.
- `relic/touch_of_orobas/g2` — DORMANT — RelicCmd.Obtain strips the obtained relic from both grab bags (`player.RelicGrabBag.Remove(relic)` and `runState.SharedRelicGrabBag.Remove(relic)`, RelicCmd.cs) and stamps `FloorAddedToDeck`; the port's direct list assignment does neither — MECHANISM: the port bypasses RunState.add_relic…
- `relic/toy_box/AfterCombatEnd` — DORMANT — Rollup of guards G2 and N1 per binding rule 4. The counter and the every-3rd-combat trigger are faithful (N1); the divergence is that RelicCmd.Melt leaves the melted relic in the player's relic list as an inert entry and the port deletes it from run.relics (G2, dormant).
- `relic/toy_box/g2` — DORMANT — `RelicCmd.Melt` leaves the relic in `Player.Relics` as an inert entry; the port removes it from run.relics entirely — MECHANISM: RelicCmd.Melt (RelicCmd.cs) is `relic.Owner.MeltRelicInternal(relic); await relic.AfterRemoved();` -- the relic STAYS in the list, and the game stops it working…
- `relic/tungsten_rod/g6` — DORMANT — the run-level walk's listener SET -- `RunState.lose_hp` iterates relics only (run.py), where C#'s IterateHookListeners(null) also walks every deck card and its enchantment (RunState.cs) and the player's potions — MECHANISM: out of combat, C# gives deck cards, card…
- `relic/unsettling_lamp/BeforePowerAmountChanged` — DORMANT — No action taken.
- `relic/unsettling_lamp/ModifyPowerAmountGivenMultiplicative` — DORMANT — ModifyPowerAmountGivenMultiplicative — C# returns a MULTIPLICATIVE factor into Hook.ModifyPowerAmountGiven's two-pass fold (Hook.cs: every listener's additive contribution is summed FIRST, then every listener's multiplicative factor is applied to that sum).
- `relic/unsettling_lamp/g5` — DORMANT — C#'s ModifyPowerAmountGivenMultiplicative has NO target-side guard and NO giver guard -- only the LATCH checks `target.Side == Owner.Creature.Side` and `applier != Owner.Creature` -- whereas the sim applies both checks to the doubling as well — MECHANISM: UnsettlingLamp.cs puts the applier…
- `relic/unsettling_lamp/g6` — DORMANT — C#'s cardSource is a per-APPLICATION argument; the sim substitutes an ambient `_in_flight` card set by before_card_played and cleared by on_card_played, so a nested card play inside the triggering card's resolution clears it — The previous 3-/4-site auto_play_card census did not meet the…
- `relic/vajra/g1` — DORMANT — nothing observes the player's Strength in the window between C#'s AfterRoomEntered and the sim's on_combat_start, so the phase difference has no observable today — MECHANISM: as above -- one full combat-setup phase separates the two positions, and it contains AfterCreatureAdded plus every…
- `relic/vexing_puzzlebox/g4` — DORMANT — `cardModel.SetToFreeThisTurn()` (VexingPuzzlebox.cs) vs `card.set_free_this_turn()` (vexing_puzzlebox.py) — C#'s SetToFreeThisTurn is `EnergyCost.SetThisTurnOrUntilPlayed(0)` plus SetStarCostThisTurn(0) (CardModel.cs).
- `relic/wing_charm/g3` — DORMANT — `base.Owner.RunState.CloneCard(...)` is a full model clone and the sim has no clone helper — The dormancy premise has changed: the port is no longer empty -- sts2_rl/relics/wing_charm.py implements the hook -- but it takes the SIBLING's shape rather than the source's, attaching…
- `relic/winged_boots/g3` — DORMANT — the sim charges only the FIRST relic whose should_allow_free_travel() is True and then `break`s (run.py); C# charges every AfterRoomEntered implementer independently — MECHANISM: in C# the charge is each relic's own business, so two free-travel sources both react to the same non-child…

## `potion` — 13 mechanisms

- `potion/_strength_applier` — DORMANT (sites: `potion/fysh_oil/OnUse`, `potion/fysh_oil/g1`, `potion/strength_potion/OnUse`, `potion/strength_potion/g1`) — OnUse (protected override, FyshOil.cs) — Rollup of guard N(applier) per binding rule 4. The two applications, their amounts and their ORDER (Strength first, then Dexterity -- FyshOil.cs vs potions.py) all match; what does not is the applier argument on the Strength half.
- `potion/fairy_in_a_bottle/AfterPreventingDeath` — DORMANT — The C# body is one line -- `await OnUseWrapper(new ThrowingPlayerChoiceContext(), creature)` (FairyInABottle.cs) -- i.e. the automatic trigger runs the FULL use pipeline.
- `potion/fairy_in_a_bottle/g1` — DORMANT — the automatic trigger bypasses OnUseWrapper, so Hook.AfterPotionUsed never fires when the fairy pops — FairyInABottle.after_preventing_death (potions.py) now ends with `combat.hooks.on_potion_used(self, creature)`, so the automatic trigger DOES reach Hook.AfterPotionUsed, which is what…
- `potion/fairy_in_a_bottle/g2` — DORMANT — `discard_potion` is the DiscardPotionInternal verb; OnUseWrapper's first step is RemoveBeforeUse, a different one — PotionModel has two removal verbs with different meanings: Discard() -> `Owner.DiscardPotionInternal(this)` (PotionModel.cs), used by PotionCmd.Discard which then fires…
- `potion/foul_potion/OnUse` — DORMANT — OnUse (protected override, FoulPotion.cs) — G1 is partly closed: the C# body is a three-way branch on the room (combat / MerchantRoom / FakeMerchant event), and the sim now ports two of the three EFFECTS but no branch -- `use` is the combat arm and `use_out_of_combat` (potions.py)…
- `potion/foul_potion/PassesCustomUsabilityCheck` — DORMANT — EXECUTED CENSUS (unchanged): `grep -rn 'override bool PassesCustomUsabilityCheck' src/` returns exactly one hit in the whole game, FoulPotion.cs -- this unit is the sole implementer and PotionModel.cs's `virtual bool ... => true` answers for the other 50.
- `potion/foul_potion/TargetType` — DORMANT — FoulPotion.cs is the tier's only COMPUTED TargetType: `TargetType.TargetedNoCreature` when `!CombatManager.Instance.IsInProgress`, `TargetType.AllEnemies` in combat.
- `potion/foul_potion/g1` — DORMANT — the two out-of-combat arms are unported, and the port's docstring names a sim capability that does not exist — WHAT REMAINS, three things. (1) `RunState.merchant_driven_off` has NO READER -- an executed `grep -rn merchant_driven_off sts2_rl/` returns exactly two hits, the initialiser and this…
- `potion/gamblers_brew/g3` — DORMANT — the Sly auto-play deferral has no sim counterpart — CardCmd.cs collects every discarded card with `IsSlyThisTurn`, and after the draw auto-plays each of them with AutoPlayType.SlyDiscard.
- `potion/gamblers_brew/g4` — DORMANT — the sim fires on_card_discarded BEFORE the card reaches the discard pile; C# fires it after — C# per card: `CardPileCmd.Add(card, discardPile)` then `History.CardDiscarded` then `Hook.AfterCardDiscarded` (CardCmd.cs) -- the card is already in the pile when the hook runs.
- `potion/snecko_oil/OnUse` — DORMANT — OnUse (protected override, SneckoOil.cs) — Rollup of guards N2 and N3 per binding rule 4. The structure is right and it is the part a replay would notice: draw 7 FIRST, then walk the resulting hand in order and take ONE `Rng.CombatEnergyCosts.NextInt(4)` per non-X card (SneckoOil.cs…
- `potion/snecko_oil/g2` — DORMANT — the C# skips a card whose unmodified cost is NEGATIVE and the port has no such clause — SneckoOil.cs guards each card with `if (item.EnergyCost.GetWithModifiers(CostModifiers.None) >= 0)` on top of the `!c.EnergyCost.CostsX` filter at. potions.py ports only the CostsX half.
- `potion/snecko_oil/g3` — DORMANT — `SetThisTurnOrUntilPlayed` also expires when the card is PLAYED; the sim models only the end-of-turn half — SneckoOil.cs calls `EnergyCost.SetThisTurnOrUntilPlayed(...)`, whose name states two expiry conditions.

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
plus what aggregating the tiers exposed.

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

**A prior worth keeping:** of eleven `AbstractModel` overrides on C# monster
models that looked mechanical, **ten were presentation** — a music parameter, a
barks line, a `Sprite2D.Texture` assignment, an animation call — and one was a
real gap. An override that looks mechanical usually is not, and only reading it
to the end separates them. The trap runs in both directions:
`LagavulinMatriarch.AfterDamageReceived` is documented as "the wake-from-damage
path" and is entirely presentation (the wake is `AsleepPower.cs:21-36`), while
`TestSubject.AfterDeath` is presentation and its *mechanical* death behaviour
lives in `AdaptablePower.AfterDeath`.

---

# Outstanding record defects

Rule-3 signals still true of the records on disk: a gap whose text contradicts
another record's, or its own. Each is **reported, not edited**, and belongs to
the stream that owns the record.

- **`hook_dispatch/G7`'s executed evidence is from a stale tree.** It records the
  stale-listener plugin run as "the whole suite (2476 passed / 30 xfailed) and
  191,270 instrumented listener calls". The suite is thousands of tests larger
  now. The conclusion may still hold — the record says the run is reproducible
  from the committed tree — but **re-run it before relying on the "only one hit"
  claim**.
- **`monster_probes_b06.py`'s `probe_wither()` greps literally for
  `WitherCard(` and cannot see `make_card()`-style dynamic construction.** Its
  "NOT LIVE, executed" verdict missed the Entropy-transform Wither route, which
  was already reachable. Any other dormancy verdict resting on a
  literal-constructor grep from that probe family should be re-derived against
  the dynamic construction paths before being trusted.
- **One RE-AUDIT paragraph pasted onto four entries, one of which it does not
  describe.** `damage_pipeline` steps 5, 9, 12 and guard G2 carry a
  byte-identical "PARTIALLY RESOLVED" block whose subject is the **HpLost**
  variant. Step 5 is `AfterModifyingDamageAmount` — a different variant, and one
  the same paragraph later lists among the variants that "remain absent".
  **The G2 rollup is the entry to trust.**
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
  kind and no `audit/records/potion/`." Both halves are false. Records:
  `relic/alchemical_coffer`, `relic/phial_holster`. Distinguish these from the
  records that quote the clause as explicit "RE-VERDICTED … has been DELETED"
  history: that is correct and should stay.
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
