# SP2 — stream wiring + map/economy parity + the conformance harness

**Status:** design approved 2026-07-20; awaiting spec review before planning.
**Owner:** Perry
**Parent:** `2026-07-20-sim-to-replay-design.md` (Component 2 = the harness; SP2 in
the decomposition). This spec is SP2's own design.
**Related workspaces:** `sts2-rl` (this repo), `Slay the Spire 2` (decompiled game
source, RNG ground truth), `RunReplays` (recordings + `run.save` oracles).

## Goal

Make the sim reproduce the game's **map and economy** for a given string seed,
and build the **conformance harness** that proves it against the `RunReplays`
recordings. Green target: for every `Resources/*` recording, the parity-sim's
generated map, room types, and traversal reproduce exactly, and the per-floor
`UpFront` / `UnknownMapPoint` / `Rewards` / `Shops` stream counters match the
paired `run.save`.

Non-goals (later SPs): combat-stream parity (`Shuffle`, `MonsterAi`,
`Combat*` — SP3), event/relic-roll parity beyond map/economy (SP4),
combat-card-id replication + the exporter (SP5). This SP leaves combat on a
legacy `random.Random`; it only needs combats to *resolve* so the run advances.

## Why this is verifiable now (stream isolation)

The game's 12 `RunRngSet` streams plus the 3 `PlayerRngSet` streams are
independent generators. Combat draws only from combat streams (`Shuffle`,
`MonsterAi`, `CombatCardGeneration`, `CombatCardSelection`, `CombatTargets`,
`CombatEnergyCosts`, `CombatOrbs`, `CombatPotionGeneration`); map/economy draw
only from `UpFront`, `UnknownMapPoint`, and `PlayerRngSet.{Rewards,Shops}`, plus
a transient map-layout `Rng`. So an un-ported, non-parity combat **cannot
perturb any stream SP2 verifies** — map/economy parity is achievable and
assertable while combat is still a stub. This is the property that lets us build
subsystem by subsystem.

## Ground truth established during design

- **Map layout uses a transient per-act Rng, not `UpFront`.**
  `StandardActMap.FromRunState` builds `new Rng(runState.Rng.Seed,
  $"act_{CurrentActIndex + 1}_map")` and generates the whole map from it
  (`StandardActMap.cs:113`). This `act_N_map` Rng is **not** one of the 12
  persistent streams and its counter is **not** in `run.save`. → Map layout is
  verified *structurally* (generated map vs. the recording's `MoveToMapCoord`
  path and the save's map/encounter data), never against a saved counter. This
  corrects the parent spec's "port map generation onto UpFront".
- **`UpFront`** drives run-start generation: `act.GenerateRooms(Rng.UpFront,
  …)` produces each act's `normal_encounter_ids` / `elite_encounter_ids`
  sequences (present in the save); shared relic grab-bag population
  (`RunManager.cs:447/450`); the shared-ancient subset rolls
  (`RunManager.cs:670-673`, already mirrored by `driver._roll_shared_ancients`);
  and the optional second-boss pick. Counter **is** saved (`up_front`).
- **`UnknownMapPoint`** seeds `RunOddsSet(unknownMapPointRng)`
  (`RunOddsSet.cs:17`), the room-type odds for `?` nodes. Counter **is** saved
  (`unknown_map_point`).
- **Economy** uses `PlayerRngSet`: `Rewards` (reward generation), `Shops`
  (price jitter). `PlayerRngType` = `{Rewards, Shops, Transformations}`; each
  stream `= new Rng(Seed, SnakeCase(name))`; `Seed` is a numeric `uint`. Both
  counters are saved under `/players[0]/rng/counters`, alongside the player
  `seed`.
- **`run.save` is clean JSON** (UTF-8 BOM). The rng block is
  `/rng/{seed, counters{12 streams}}` and `/players[0]/rng/{seed,
  counters{rewards,shops,transformations}}`. No binary parsing; the parent
  spec's "opaque Godot binary" fallback does not apply. The save also carries
  `acts`, `ascension`, `current_act_index`, `visited_map_coords`,
  `map_point_history`, and per-act `normal_encounter_ids` / `elite_encounter_ids`
  — additional oracles.
- **Gaussians.** `Rng.NextGaussianInt(mean, stdDev, min, max)` (`Rng.cs`) loops
  drawing **two** `NextDouble()` per iteration (`d`, then `num`), computes
  `z = sqrt(-2 ln d) * Sin(2π·num)`, `n = round(mean + stdDev·z)`, and **rejects
  until `min ≤ n ≤ max`** — no `(max-min)` scaling. Note it uses **`Sin`**,
  whereas `NextGaussianDouble` uses `Cos` and *does* scale. Each loop iteration
  advances the stream counter by 2. The current `actmap.gaussian_int` uses a
  different formulation and must be re-ported to match `NextGaussianInt`
  exactly. `MapPointTypeCounts.StandardRandomUnknownCount =
  NextGaussianInt(12, 1, 10, 14)`; act rest counts are
  `NextGaussianInt(7|6, 1, 6, 7)` (Overgrowth/Underdocks/Hive) and Glory uses
  `NextInt(5, 7)` for rests.

## Architecture — the RNG seam

`RunState` gains, seeded from the string seed at construction:

- `rng_set: RunRngSet` — the 12 streams (already ported, SP1).
- `player_rng: PlayerRngSet` — the 3 streams (ported in this SP).
- a factory for the transient map-layout Rng: `Rng(rng_set.seed,
  name=f"act_{act_index+1}_map")`, created fresh per map generation.

The legacy `self.rng: random.Random` **stays** for all not-yet-ported
subsystems (combat, events, relics). Only the map/economy call sites are
rewritten to draw from the correct stream with game-exact primitives:

| Python `random.Random`         | ported `Rng`                                   |
|--------------------------------|------------------------------------------------|
| `rng.shuffle(x)`               | `stream.shuffle(x)` (Fisher-Yates, game order) |
| `rng.choice(seq)`              | `stream.next_item(seq)`                         |
| `rng.randrange(n)`             | `stream.next_int(n)`                            |
| `rng.randrange(a, b)`          | `stream.next_int_range(a, b)`                   |
| `rng.randint(a, b)`            | `stream.next_int_range(a, b + 1)`              |
| gaussian rest/unknown counts   | `stream.next_gaussian_int(mean, sd, lo, hi)`   |
| `rng.sample` (reward gen)      | game's actual draw (port per call site)         |

The seam is a mechanical, per-call-site rewrite bounded to the map/economy
files (`actmap.py`, the map/economy paths in `run.py`, `rooms.py` unknown-room
resolution, `rewards.py`, `shop.py`). Draw **order and count** must match the
game; the failure mode is silent, which is exactly what the harness catches.

## Work units

### U1 — RNG gaps from SP1 (prerequisites)

- **`PlayerRngSet` / `PlayerRngType`** in `rng.py`: enum `{REWARDS, SHOPS,
  TRANSFORMATIONS}`; `PlayerRngSet(seed: int)` builds `Rng(seed,
  name=snake_case(t))` per type; `counters()` / `load_counters()` mirrors
  `RunRngSet`. The run-start derivation of the player `uint` seed is a golden
  the save pins down (player seed `2221240958` for run `89U21BV1TZ`); resolve it
  against the game's `StartNewSingleplayerRun` / player construction and assert.
- **`Rng.next_gaussian_int(mean, stdDev, min, max)`** (and `_double`, `_float`
  for completeness): faithful port of the `Sin`-form rejection loop above, two
  `next_double()` per iteration. Golden vector dumped from the dll (data-
  dependent counter, so the vector must include resulting counters).

Tests: golden vectors from `sts2.dll` for the Gaussians and for a
`PlayerRngSet` seeded run; `snake_case` of the `PlayerRngType` names asserted.

### U2 — map-layout parity

Route `actmap.py` generation off `random.Random` onto a fresh transient
`Rng(seed, "act_N_map")` per act, matching `StandardActMap` draw order and
`ActModel.GetMapPointTypes` exactly (rest counts, unknown counts via the ported
Gaussian; the `stable_shuffle` → `Rng.shuffle`; column random-walk
`randrange` → `next_int`; `AssignRemainingTypesToRandomPoints` shuffles). No
saved counter exists for this Rng; verified structurally.

Green: for each recording, the generated act maps' room-type grid and legal
paths reproduce the save's `map_point_history` / `visited_map_coords`, and the
recording's `MoveToMapCoord` sequence is a legal traversal landing on the room
types the annotations imply.

### U3 — UpFront + UnknownMapPoint + economy parity

- `act.GenerateRooms` encounter-list rolls → `UpFront`, matching draw order so
  the generated `normal_encounter_ids` / `elite_encounter_ids` equal the save's.
- Shared relic grab-bag population and second-boss pick → `UpFront` (order
  relative to `GenerateRooms` matters; follow `RunManager.GenerateRooms`).
- Unknown-room room-type resolution → `UnknownMapPoint` (`RunOddsSet`), matching
  the odds rolls.
- Reward generation (gold, card rarity, potion) → `PlayerRngSet.Rewards`; shop
  price jitter → `PlayerRngSet.Shops`.

Green: at every floor boundary the harness diffs `UpFront`, `UnknownMapPoint`,
`Rewards`, `Shops` counters against the save and they match; reward/room-type
annotations match per command.

### U4 — the conformance harness

New module(s) under `sts2_rl/` (e.g. `conformance/`) + tests under `test/`:

1. **Recording parser** — parse a `.sts2replay` into `Recording{header:
   {seed, acts, ascension, character, game, mod}, commands: [Command{name,
   args, comment, annotation}]}`, where `annotation` parses `|| Hand: [names]
   Enemies: [name hp/maxhp]` and the `# CARD.X (id)` from `PlayCard` comments.
   Pure text→data; green against all 15 recordings.
2. **Save parser** — parse a `run.save` into `SaveOracle{run_counters (12),
   player_counters (3), run_seed, player_seed, acts, ascension,
   encounter_ids_by_act, map_history, visited_coords}`. Pure JSON; green against
   all 15 saves.
3. **Annotation model + comparators** — helpers that compare a live sim
   `RunState` / `CombatState` against a command's annotation (room type, reward
   options, and — where SP2 can — hand/enemy *names*; HP is combat-dependent and
   deferred to SP3). Pure, unit-tested with constructed states.
4. **The runner** — seed the parity-sim from the recording header, drive
   `driver.RunDriver`, translating each recorded command into its
   `DecisionRequest` answer (the reverse of Component 3's mapping, for the SP2
   command subset: `MoveToMapCoord`, `ClaimReward`, `TakeCard`, rest/shop/event
   choices). Combat is a **force-win stub**: the recordings show the player
   survived every fight, so the stub resolves each `COMBAT` decision to end the
   fight with the player alive (SP3 replaces it with real parity combat) — its
   only job in SP2 is to advance floors and trigger unknown-room and reward
   rolls. At each command the runner runs the U3/U2 comparators; at floor
   boundaries it diffs the four SP2 stream counters against the save. On the
   first mismatch it emits a **localized divergence report** (stream, command
   index, expected vs. actual) — the pinpoint the parent spec promises.

Green (acceptance for SP2): the runner replays every `Resources/*` recording
with zero map/room-type/economy-annotation mismatches and matching `UpFront` /
`UnknownMapPoint` / `Rewards` / `Shops` counters at every floor boundary, across
all three acts.

## Sequencing

U1 → U2 → U3 → U4, but the harness's *parsers* (U4.1, U4.2) can land first as
pure green units and are the oracle the rest is tested against. Suggested order:
U4.1/U4.2 (parsers, green immediately) → U1 (RNG gaps, golden) → U2 (map layout,
verified via U4.1/U4.2) → U3 (upfront/economy) → U4.3/U4.4 (comparators +
runner) tying it together.

## Risks & mitigations

- **Silent draw-order desync (primary).** Mitigation: harness-first parsers;
  per-floor counter diffs localize a divergence to one stream and one command.
- **Player-seed derivation unknown.** The save gives the exact `uint`; resolve
  the derivation against the game and lock it with a golden. If underivable in
  SP2 scope, seed `PlayerRngSet` directly from the saved value in the harness
  and flag the derivation as an SP-carry — economy counters still verify.
- **Gaussian counter accounting.** Data-dependent (rejection loop); mitigated by
  a golden vector that includes resulting counters, and by the per-floor
  `unknown_map_point` counter diff catching any miscount.
- **Force-win stub changes reward RNG.** Rewards depend on room type and relics,
  not on combat internals, so a stubbed combat still rolls the same `Rewards`
  draws — but any reward that *does* depend on combat state (e.g. HP-scaled) is
  out of SP2 scope and asserted only structurally.
- **`act_N_map` non-parity is invisible to counters.** Mitigated by structural
  map verification against `map_point_history` + `MoveToMapCoord` path, not
  counters.

## Acceptance

1. `PlayerRngSet` and the Gaussians pass golden vectors dumped from `sts2.dll`;
   suite stays green.
2. The recording and save parsers round-trip all 15 `Resources/*` pairs.
3. The conformance runner replays every recording through the parity-sim with
   zero map/room-type/economy mismatches and matching `UpFront` /
   `UnknownMapPoint` / `Rewards` / `Shops` counters at every floor boundary,
   across all three acts.
