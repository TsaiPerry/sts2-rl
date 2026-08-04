# Bring the Ironclad-relevant SYSTEMS into the audit pipeline

## Why this task exists

The source-to-sim audit (`audit/`) covers **models**: seven content kinds
(`card`, `relic`, `power`, `monster`, `event`, `potion`, `enchantment`) plus six
engine seams. Its roster is derived from the sim's own registries
(`harness._sim_units`), so it can only ever see things that come one-class-per-unit.

Everything that is a **system** rather than a model is therefore invisible to it:
encounters, pools, rooms, the map, rewards, the RNG streams, the run layer. Not
one of those has a record, a verdict, or a staleness check.

That is not academic. Measured 2026-08-03:

- `py audit/tools/gap_queue.py counts` reports **0 live gap entries** — no audited
  divergence is known to be reachable on ported content.
- `test/test_conformance_player_state.py::test_full_run_player_state_parity[89U21BV1TZ]`
  (an Ironclad seed, fixture installed, runs today) diverges anyway:
  `player_hp` **57 vs the game's 51 at the act-1 boundary**, 44 combat
  divergences, `unresolved_play_card_ids: []`. Nothing un-portable is involved —
  the sim plays those fights; the hands desynchronise (it is repeatedly short a
  Dazed the recording plays) and the Mecha Knight ends 4 HP off.
- Ironclad's *unit* coverage is essentially complete: of the game's
  Ironclad-visible pools, 0 cards, 0 potions and 1 relic (now ported) were
  missing. So the divergence is not missing content. It is in the systems tier,
  which nothing audits.

`audit/GAP-QUEUE.md`'s own "Behaviour in no tier's scope" section says the same
thing from the other side, and names the two worst: `EncounterModel` /
monster-slot generation ("the highest-value hole left"), and **no record owns the
`combat_rng` stream map** ("given that stream desync is the highest-impact
failure class in this queue, that is the largest structural hole here").

## Goal

Make the systems tier auditable on the same terms as everything else — rostered,
recorded, verdicted, covered by the staleness and coverage checks — **and then
audit it.** Wiring alone would only convert "invisible" into "unaudited"; the
deliverable is a verdict on every unit, filed as a record, with every gap named
in `audit/GAP-QUEUE.md`.

Three phases, in order. Phase 1 is a day's work; **phase 2 is the campaign** and
should be batched (~95 records); phase 3 is what the other two are for.

## Phase 1 — wiring: scope, in priority order

Ironclad-relevant only. Skip anything reachable solely by another character, in
multiplayer, or in the UI/save/localisation layers.

### A. New content KINDS (unit-per-class, fits the existing roster machinery)

| kind | game dir | game `.cs` | sim registry | notes |
|---|---|---|---|---|
| `encounter` | `src/Core/Models/Encounters` | 96 | `ENCOUNTERS` in `sts2_rl/monsters/{overgrowth,hive,glory,underdocks}/__init__.py` (80 total) | **do this one first** |
| `affliction` | `src/Core/Models/Afflictions` | 10 | `sts2_rl/afflictions.py` (7) | `AfflictionModel.cs` is already seam-claimed; the 10 models are not |
| `character` | `src/Core/Models/Characters` | 8 | `sts2_rl/characters.py` | audit Ironclad's row only; the other four are unported by design |

`src/Core/Models/Acts` (5) — check whether the sim has an act registry. If it
does, add it as a kind; if it does not, fold act structure into seam D3 below
rather than inventing a registry for it.

### B. New SEAMS (file-set records, for systems with no unit shape)

Priority order, highest first. Each needs an `audit/seams/<name>.md` scope doc, a
`SEAM_SOURCES` entry naming its C# and sim files, and a
`audit/records/seam/<name>.json`.

1. **`rng_streams`** — `src/Core/Random/*` (3 files: `Rng.cs`, `MegaRandom.cs`)
   plus the per-stream map: which stream each draw comes off, and the draw counts.
   The queue calls this the largest structural hole. Several existing entries are
   "the sim draws from the wrong stream, or draws when the game does not", each
   found incidentally by whichever seam happened to touch the call site.
2. **`rewards`** — `src/Core/Rewards/*` (11) + `RewardsCmd.cs`. `RewardsSet
   .GenerateWithoutOffering`'s two populate loops around `Hook.ModifyRewards`
   were the root of a live gap closed on 2026-08-03
   (`event/crystal_sphere/g3`); nothing owns the choke point itself.
3. **`relic_pools`** — `src/Core/Runs/RelicGrabBag.cs` +
   `src/Core/Factories/RelicFactory.cs` + `src/Core/Models/{Relic,Card,Potion}Pools/*`
   (32 files). Pool composition and the rarity ladder. Two bugs already found
   here by hand: the escalation ladder (`GetAvailableDeque` climbs
   Shop→Common→Uncommon→Rare before falling back to Circlet) and the
   `_refreshAllowed` refill branch, filed as `relic/circlet/g4`.
4. **`run_layer`** — `src/Core/Runs/*` minus `RunState.cs` (already seam-claimed):
   `RoomSet.cs`, `RunManager.cs`, and the rest (38 unclaimed files).
5. **`rooms_and_map`** — `src/Core/Rooms/*` (14) + `src/Core/Map/*` (16). Map
   generation is RNG-consuming and the room lifecycle is every floor's spine.
6. **`commands_remainder`** — the 13 of 20 `src/Core/Commands/*.cs` no seam
   claims (`RelicCmd`, `RewardsCmd`, `PotionCmd`, `MapCmd`, …). Consider folding
   each file into the seam above that owns its subject instead of making this a
   seam of its own; decide explicitly and record the decision.

### C. Out of scope — state it, do not silently omit

`Nodes` (691, UI), `Multiplayer` (147), `Saves` (118), `Timeline` (74),
`Localization`, `DevConsole`, `Platform`, `Achievements`, `Badges`, `Orbs`
(Defect-only), and the four unported characters. Record these as an explicit
"not audited, and why" list in `audit/README.md` — the campaign has been burned
before by scope expressed as an exclusion rather than as a reported fact.

## How to wire a new kind (mechanical, and there are two lists to edit)

1. `audit/tools/harness.py`: add the dir to `GAME_MODEL_DIRS` and a branch to
   `_sim_units`. Check `_game_path`'s PascalCase mapping resolves; add entries to
   `audit/tools/name_overrides.json` where it does not.
2. `audit/tools/gap_queue.py`: add the kind to `CONTENT_KINDS` (line ~102).
   **This list is maintained by hand and is not derived from the harness** — it
   silently omitted `potion` for a day while 51 finished records sat on disk, and
   `coverage` / `cite-check` printed their complaints and exited 0 while it did.
   `test/test_audit_status.py::TestQueueGeneratorCoversEveryKind` pins the two
   lists together; make it pass rather than editing around it.
3. `py audit/tools/harness.py roster <kind>` — expect `0 unmatched`; investigate
   every unmatched unit before generating skeletons.
4. `py audit/tools/harness.py skeleton <kind>/<unit>` per unit, then fill them.
5. `py audit/tools/audit_status.py` should now show the kind with its totals.

For a new seam: add `SEAM_SOURCES[<name>]`, write `audit/seams/<name>.md`
(scope, what it claims, what it explicitly does not), and create
`audit/records/seam/<name>.json`.

## Traps, paid for already

- **The roster comes from the sim, not the game.** A kind whose sim side has no
  registry cannot be rostered. Encounters are fine (four `ENCOUNTERS` dicts);
  verify before promising a kind for acts.
- **`harness.unported <kind>` is informational, not a gap list** — many entries
  are other characters' content. Scope every count to Ironclad-visible before
  quoting it: the game's card pools are literal lists, so visibility is exact
  (`Ironclad`, `Colorless`, `Curse`, `Event`, `Quest`, `Status`, `Token` pools;
  `CardMultiplayerConstraint.MultiplayerOnly` drops out).
- **`coverage` and `cite-check` must both pass after any edit to GAP-QUEUE.md**,
  and both now return their exit codes — check them, do not eyeball the output.
- **Do not hash `audit/tools/` or `test/` paths** in `extra_sources`
  (`citation_check._NEVER_HASHED`): it makes records go stale whenever any pin
  moves.
- **A citation with a line number must resolve**; cite a member name instead of a
  line for sim files that change often.
- Read `audit/tools/PROMPT.md` (the auditor contract, v6) before writing any
  verdict, and `audit/GAP-QUEUE.md`'s Standing lessons before trusting any
  dormancy claim you inherit.

## Phase 2 — actually audit them

This is the bulk of the work: **~95 records** (80 encounters, 7 afflictions, 1
character, 6 seams, plus whatever `Acts` turns into). Do not treat phase 1 as the
finish line — a rostered kind with empty verdicts is worse than no kind at all,
because `audit_status` will report it as covered.

**Read `audit/tools/PROMPT.md` (the auditor contract, v6) first, in full.** It
defines the verdict vocabulary (`faithful` / `waiver` / `deliberate-divergence` /
`gap`), the liveness labels, the binding rules (one verdict per mechanism; a
cross-record disagreement is resolved, not duplicated), and the recurring bug
classes to check each unit against. Everything below is in addition to it, not
instead of it.

### Batching

Natural batches, roughly in dependency order:

| batch | units | why this order |
|---|---|---|
| 1 | seam `rng_streams` | every later record cites stream identity; settle the map first |
| 2 | `encounter` × 22 (overgrowth) | act 1, the acts the conformance seeds replay green |
| 3 | `encounter` × 20 (hive) | act 2 — where 89U's forced wins are |
| 4 | `encounter` × 18 (glory) + × 20 (underdocks) | |
| 5 | seam `rewards`, seam `relic_pools` | both already have known findings to re-derive |
| 6 | `affliction` × 7, `character` × 1 | small, and afflictions ride card hooks |
| 7 | seam `run_layer`, seam `rooms_and_map` | broadest; do last, with the rest as context |

Run batches concurrently where they do not share files — the relic tier audited
258 units this way in 18 batches over 4 rounds with zero merge conflicts, and the
monster tier did 109 in 8. Each batch: read both sides, fill the skeleton,
`validate`, `citation_check`, then hand back a short report naming every gap it
filed.

### Rules that decide whether this campaign is worth anything

- **Execute the witness; do not argue it.** "No ported listener can see this" is
  a claim; "all 13 overrides ignore the parameter" is a fact. Every dormancy
  verdict needs an enumeration or a probe, and probes belong in
  `audit/tools/` next to the existing `*_probes*.py`.
- **Encounters are RNG-consuming — that is the point of auditing them.**
  `BowlbugsNormal.GenerateMonsters` draws `base.Rng.NextItem(items)` twice under
  per-worker count caps; others place by slot name. For each encounter, verdict
  the roster, the slot assignment, the draw count and the stream it comes off,
  and the gold override — not just "the same monsters appear".
- **A green suite is not evidence of fidelity.** Four fixes in one past round each
  introduced a new divergence the whole suite passed over. Read the C#.
- **Audits RECORD; they do not edit the engine.** The relic tier's 258 records
  landed with zero engine edits, and that is why it merged cleanly. If a fix is
  irresistible, it is a separate task with a failing test first
  (`superpowers:test-driven-development`).
- **File every finding as an entry AND name its mechanism in
  `audit/GAP-QUEUE.md`.** `coverage` enforces the second half; nothing enforces
  the first, and an unfiled finding is invisible to the next round.
- **Expect the live count to rise, and say so plainly.** It is currently 0. A
  campaign over an unaudited tier that produces 0 new live entries has almost
  certainly failed to look; the seeds say something is live.

### Phase 2 done

- Every new record: a verdict on every hook and guard, `0 invalid` from
  `harness.py validate`, clean `citation_check`.
- `py audit/tools/gap_queue.py counts` reports the new kinds with real numbers,
  and `GAP-QUEUE.md` is regenerated so `coverage` and `cite-check` exit 0.
- A written summary per batch: units audited, gaps filed, live vs dormant, and
  which existing entries the new records contradict (cross-record disagreement
  has four times meant *neither* record was right).

## Phase 3 — cash it in: explain the 89U divergence

With the systems tier recorded, go back to the thing that motivated all of it:

```
py -m pytest test/test_conformance_player_state.py -q -k 89U --runxfail
```

`player_hp` 57 vs 51 at the act-1 boundary, in an act with no unported content.
Bisect it against the new records — encounter rosters/slots, the reward populate
order, and the RNG stream map are the three candidates. Whatever it is:

1. File it as a gap entry with `live: true` and an executed witness.
2. Fix it under TDD (failing conformance-shaped test first).
3. Re-run the seed and record the new boundary numbers in the xfail reason.

Then install the `933T39V18D` fixture (captured and in-game-validated
2026-07-23, never installed, so its xfail fails at file load and measures
nothing) and repeat. Its acts 0–1 were reported fully green, which makes it the
sharper of the two seeds.

## Definition of done

**Phase 1:**

- `py audit/tools/audit_status.py` lists every new kind with `0 invalid`.
- `py audit/tools/harness.py roster <kind>` shows `0 unmatched` for each.
- `py audit/tools/gap_queue.py counts` names the new kinds in its per-kind table.
- `py audit/tools/gap_queue.py coverage` and `... cite-check` both exit 0.
- `py audit/tools/citation_check.py audit/records` shows no MISSING and no
  OUT-OF-RANGE rows for the new records.
- `py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py` is green
  (baseline 2026-08-03: **4537 passed / 6 xfailed**).
- `audit/README.md` states the new kinds/seams and the explicit out-of-scope list.

**Phase 2:**

- Every unit of every new kind has a record with a verdict on every hook and
  guard — no empty strings, no `TODO`. `harness.py validate` reports `0 invalid`
  across `audit/records`.
- Every gap filed is named in `audit/GAP-QUEUE.md`; `coverage` and `cite-check`
  exit 0 after the regeneration.
- The per-batch summaries exist, including the cross-record disagreements found.

**Phase 3:**

- The 89U act-1 divergence has a named cause, a gap entry with an executed
  witness, and a fix landed under TDD.
- `py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py` green,
  with the act-1 boundary either passing or its xfail reason rewritten to the
  measured numbers (never left stale — the current strings are, which is what
  sent this investigation down a dead end twice).
- The `933T39V18D` fixture is installed and its xfail reflects a real run.

## Sequencing note

Phase 2 is far larger than phase 1 and should not be attempted in one pass.
Work batch by batch, keep the suite green between batches, and stage as you go.
If context runs short, the natural stopping points are batch boundaries — each
leaves the tree valid (`validate` 0 invalid, `coverage` 0 missing) and the next
session can resume from `audit_status`.

## Repo conventions

- **Never `git commit` or `git push` in this repo unless asked** — stage only.
- No `Co-Authored-By` trailers.
- `python` is `py` on this machine; set `PYTHONIOENCODING=utf-8` when a script
  prints non-ASCII.
