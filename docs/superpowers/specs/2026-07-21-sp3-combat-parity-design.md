# SP3 — combat parity + combat-card ids

**Status:** design approved 2026-07-21; awaiting spec review before planning.
**Owner:** Perry
**Parent:** `2026-07-20-sim-to-replay-design.md` (SP3 in the decomposition;
Component 1 = the parity contract, Component 3's `NetCombatCardDb` pulled
forward into this SP by decision below).
**Related workspaces:** `sts2-rl` (this repo), `Slay the Spire 2` (decompiled
game source, RNG ground truth), `RunReplays` (recordings + `run.save` oracles).

## Goal

Make the sim reproduce the game's **combat** for a given string seed: every
draw pile, monster move, and combat-generation/selection/target/energy roll
lands on the same value in the same order and count as the real game. Replace
the SP2 conformance harness's **force-win combat stub** with a real
recording-driven combat driver, and port the game's per-combat card-id scheme
(`NetCombatCardDb`) so combat is driven and verified by the recorded
`PlayCard {id}`.

Green target: for every `Resources/*` recording, the parity-sim plays every
fight through with zero `|| Hand: […] Enemies: […]` annotation mismatches, the
combat-card ids we assign equal the recorded `PlayCard {id}` values, and the
seven combat-stream counters (`Shuffle`, `MonsterAi`, `CombatCardGeneration`,
`CombatCardSelection`, `CombatTargets`, `CombatEnergyCosts`,
`CombatPotionGeneration`) match the paired `run.save` at every floor boundary,
across all three acts.

## Non-goals (later / out of scope)

- The exporter (`export_replay.py`) and the DecisionRequest→ReplayCommand
  command translator — SP5. This SP ports `NetCombatCardDb` (so the harness can
  drive by `PlayCard {id}`) but does **not** emit replay files.
- `CombatOrbs` parity — no orbs are ported (deliberate engine gap); the stream
  stays at counter 0, matching runs that never spawn orbs. If a recording's
  fight uses orbs it is out of scope and flagged.
- Reward/event/relic-roll parity beyond what combat consumes — that is SP4's
  `Rewards`/`Shops`/event streams, already partly landed in SP2. SP3 must not
  perturb those streams.
- No changes to the RL training/eval path's behavior: the legacy
  `random.Random` combat path stays byte-for-byte identical (see the seam).

## Why this is verifiable now (stream isolation)

The 12 `RunRngSet` streams are independent generators. SP2 verified map/economy
(`UpFront`, `UnknownMapPoint`, `Rewards`, `Shops`) with combat still stubbed,
because combat draws only from combat streams. The same isolation runs in
reverse now: SP3 wires the combat streams while SP2's map/economy parity is
held fixed, and a combat desync cannot corrupt a map/economy counter the
harness already asserts green. Parity is achieved and checked stream by stream,
and the harness localizes any divergence to one stream and one command.

## Ground truth established during design

- **`GameRandomAdapter` is the lever, not a rewrite.** `rng.py` already exposes
  a `random.Random`-shaped facade over one game `Rng` stream, with
  `random`/`randrange`/`shuffle`/`choice` verified 1:1 against the C# source
  (SP2 uses it for map generation). The combat seam is therefore mostly
  *pointing each call site at the correct stream via an adapter*, plus adding
  the primitives combat needs that the map path never exercised (`sample`,
  `choices`, `randint`) — each mapped to the game primitive it mirrors and
  verified against the source. It is a per-call-site rewrite of *which stream*,
  not of the porting logic.

- **The combat RNG call-site inventory is finite and enumerated.** `combat._rng`
  and monster/card `.rng` are used in ~40 sites across `combat.py`, `player.py`,
  `cmds.py`, `monsters/`, `cards/pool.py`, and individual card/monster modules
  (`.choice`, `.shuffle`, `.sample`, `.choices`, `.randint`, `.randrange`,
  `.random`). Each maps to exactly one stream by purpose: draw-pile
  shuffle/reshuffle → `Shuffle`; random monster move selection → `MonsterAi`;
  in-combat card generation (`pool.py`, colorless card effects, status adds) →
  `CombatCardGeneration`; in-combat card *selection* (headless
  `select_cards`) → `CombatCardSelection`; random enemy/hand target picks →
  `CombatTargets`; energy-cost randomization → `CombatEnergyCosts`; in-combat
  potion generation → `CombatPotionGeneration`.

- **Monster moves roll at intent-display time (`MonsterAi`).** CLAUDE.md's
  "Single RNG stream; the game rolls monster moves at intent-display time from a
  dedicated seeded `MonsterAi` stream" gap is real. The game selects a random
  move when the intent is telegraphed (combat start and each enemy turn-start),
  not when the move resolves; the sim's `state_machine.py` and the hand-rolled
  `_move_key` monsters roll at resolution time. For `MonsterAi` order+count
  parity the roll must move to telegraph time. This changes timing-sensitive
  existing tests, which get updated to the game-correct behavior (per the repo's
  fidelity-to-source rule); the suite stays green.

- **`NetCombatCardDb` id scheme** (`src/Core/GameActions/Multiplayer/
  NetCombatCardDb.cs`, verified): at `StartCombat`, `_nextId = 0`, then walk
  `player.PlayerCombatState.AllPiles.SelectMany(p => p.Cards)` assigning
  sequential `uint` ids via `IdCardIfNecessary` (id per *mutable card instance*,
  by reference identity, contiguous, persistent for the whole combat). Then
  subscribe to each pile's `ContentsChanged`; any card newly added to a pile is
  id'd (next id) in pile-change order. `AllPiles` order is fixed:
  **`Hand, DrawPile, DiscardPile, ExhaustPile, PlayPile`** (`PlayerCombatState.
  cs:70`). Ids do **not** consume any RNG stream — this is a bookkeeping port,
  verified structurally against the recordings' `PlayCard {id}` values.

- **The sim lacks a distinct `PlayPile`.** `player.py`'s `all_cards` is
  `hand + draw_pile + discard_pile + exhaust_pile` (four piles). The game holds
  a card in a fifth `PlayPile` while it resolves. For the id walk this matters
  only when a card is mid-resolution at the moment another card is id'd; the id
  port must reproduce the game's pile membership at each `IdCardIfNecessary`
  point (including where a played card lives during its own resolution). The
  recordings' `PlayCard {id}` sequence is the oracle that pins this down.

- **Recordings carry the card name inline.** Each `PlayCard {id}` command has a
  `# CARD.X (id)` comment (already parsed by the SP2 recording parser) plus the
  `|| Hand/Enemies` pre-state annotation. So even before id parity is proven,
  the harness can cross-check that the card our ported db maps `{id}` to is the
  card the comment names — a second oracle on the id walk.

## Architecture — the combat RNG seam

`CombatState` today funnels all randomness through one `self._rng` (a
`random.Random`, handed down from `run.rng` via `create_combat`). The seam
splits it by purpose without disturbing the legacy path:

- **`CombatRng` accessor** on `CombatState`, exposing named streams as
  `random.Random`-shaped adapters: `.shuffle`, `.monster_ai`, `.card_gen`,
  `.card_selection`, `.targets`, `.energy`, `.potion_gen`.
- **Parity path** (run constructed with a `string_seed`): each accessor is a
  `GameRandomAdapter` over the matching `RunRngSet` stream, passed into
  `CombatState` by `create_combat`. Draw order and count must match the game.
- **Legacy path** (no `string_seed`; all RL training/eval): every accessor
  returns the one shared `random.Random`, so every sequence — and the whole
  test suite — is byte-for-byte identical to today. This is the invariant that
  keeps training reproducible.
- **`GameRandomAdapter`** gains `sample`, `choices` (weighted →
  `WeightedNextItem`), and `randint`, each verified 1:1 against the game
  primitive it mirrors. Sites using Python idioms with no faithful game
  analogue (e.g. batched `sample` where the game draws one-at-a-time) are
  rewritten to the game's actual draw order.

The per-call-site edit is mechanical: change `self._rng.shuffle(draw_pile)` to
`self._rng_shuffle.shuffle(draw_pile)` (etc.), selecting the accessor by the
purpose table above. The failure mode is silent (one extra/missing draw
desyncs a stream), which is exactly what the harness catches.

## Work units (each gated on the suite staying green)

### U1 — seam scaffold + `Shuffle` parity
`CombatRng` accessor; `create_combat` wiring to pass the combat streams in the
parity path (legacy path unchanged); extend `GameRandomAdapter` with the
combat primitives. Route the draw-pile **`Shuffle`** sites first (`player.py`
initial shuffle + `reshuffle_discard_into_draw`, `havoc.py`, any
`draw_pile` shuffle), matching the game's shuffle+draw order at combat start
and reshuffle. Verify: initial hands in the recordings' first-turn `|| Hand`
annotations reproduce.

### U2 — monster moves at intent time + `MonsterAi` parity
Move random move selection from resolution time to telegraph time (combat start
+ each enemy turn-start) in `state_machine.py` (`RandomBranchState`) and the
hand-rolled `_move_key` monsters, drawing from `MonsterAi` via the correct
primitive (`WeightedNextItem`/`NextItem`/`NextInt`). Update the timing-sensitive
legacy tests. Verify: enemy intents/moves in the recordings reproduce and the
`MonsterAi` counter matches at floor boundaries — scoped to the monster roster
the 15 recordings actually exercise.

### U3 — `CombatCardGeneration/Selection/Targets/EnergyCosts/PotionGeneration`
The per-content draw-order fixes: route each remaining combat call site to its
stream with the game-exact primitive and draw order —
- card generation (`cards/pool.py`, colorless card effects, status-card adds,
  `cmds.py` generators) → `CombatCardGeneration`;
- headless in-combat `select_cards` → `CombatCardSelection`;
- random enemy/hand target picks (`combat.py`, card/monster `.choice(living)`)
  → `CombatTargets`;
- energy-cost randomization → `CombatEnergyCosts`;
- in-combat potion generation → `CombatPotionGeneration`.
Bounded to content the 15 recordings touch; this is the long pole. Verify:
`Hand/Enemies` annotations match through the affected fights and each stream's
counter matches at floor boundaries.

### U4 — `NetCombatCardDb` id replication
Port the id scheme: a per-combat `CombatCardDb` that at combat start walks the
sim's piles in `AllPiles` order (`Hand, DrawPile, DiscardPile, ExhaustPile,
PlayPile`) assigning contiguous ids by card identity, and ids newly-added cards
in pile-change order thereafter. Reproduce the game's pile membership at each id
point (including the played-card-during-resolution case the sim's missing
`PlayPile` glosses). No RNG consumed. Verify: for every `PlayCard {id}` in the
recordings, our db maps `{id}` to the card the `# CARD.X` comment names, and the
id we would assign equals `{id}`.

### U5 — harness combat-driver + combat verification
Replace the runner's force-win `_run_combat` with a driver that plays the
recording's combat commands: `PlayCard {id} [{targetId}]` → look up the card via
`CombatCardDb`, play it at `targetId`; `UsePotion {slot} [{targetId}]`;
`EndTurn`. Before each command, assert the live `|| Hand/Enemies` annotation
(card ids/names; enemy names + `currentHp/maxHp`). At floor boundaries, diff the
seven combat-stream counters against the save (extend SP2's
`compare_counters`). On the first mismatch, emit the localized divergence report
(stream/command-index/expected-vs-actual). Drive to green on all 15 recordings.

## Sequencing

U1 → U2 → U3 in RNG-wiring order (seam, then the two highest-frequency streams,
then the rest), because the harness needs each stream wired before its counter
can be asserted. U4 (ids, no RNG) can land in parallel with U2/U3 — it is
verified structurally against the recordings independent of stream parity. U5
ties it together and is the acceptance gate; a thin version of the U5 driver
(drive by id, assert `Hand/Enemies` only, no counter diff) can land right after
U1 so each subsequent unit is checked against real fights as it lands, with the
counter diffs switched on per stream as U2/U3 complete.

## Risks & mitigations

- **Silent draw-order desync (primary).** Mitigation: harness-first; per-command
  `Hand/Enemies` asserts + per-floor combat-counter diffs localize a divergence
  to one stream and one command.
- **Intent-time refactor destabilizes green tests.** Expected and accepted:
  update legacy timing-sensitive tests to the game-correct telegraph-time
  behavior; the suite is the regression guard that the refactor is
  behavior-preserving elsewhere.
- **Per-content draw-order gaps (U3, the long pole).** The sim ports the game's
  logic but batches/reorders some draws and uses Python primitives (`sample`,
  `choices`). Each site is a bounded, finite rewrite to the game's order;
  bounded further to the content in the 15 recordings.
- **`AllPiles` iteration + missing `PlayPile` for ids (U4).** The played-card-
  during-resolution membership is the subtle case; the recordings' `PlayCard
  {id}` sequence is the direct oracle, and the `# CARD.X` comment is a second
  cross-check.
- **Legacy-path regressions.** Any accessor mis-wired to a game stream in the
  legacy (no-seed) path would change training sequences. Mitigation: the legacy
  path returns the single shared `random.Random` for every accessor, asserted by
  keeping the full existing suite green throughout.
- **Orb/unported-content fights.** A recording fight using an unported mechanic
  (orbs) is out of scope; the harness flags it rather than silently diverging.

## Acceptance

1. The seam is in place and the legacy `random.Random` combat path is unchanged:
   the full existing suite stays green (baseline 2235).
2. Monster moves roll at telegraph time from `MonsterAi`; updated legacy tests
   pass.
3. `CombatCardDb` assigns ids matching every `PlayCard {id}` in the 15
   recordings, each consistent with the `# CARD.X` comment.
4. The conformance runner plays every `Resources/*` recording's fights through
   the parity-sim with zero `Hand/Enemies` annotation mismatches and matching
   `Shuffle`, `MonsterAi`, `CombatCardGeneration`, `CombatCardSelection`,
   `CombatTargets`, `CombatEnergyCosts`, `CombatPotionGeneration` counters at
   every floor boundary, across all three acts.
