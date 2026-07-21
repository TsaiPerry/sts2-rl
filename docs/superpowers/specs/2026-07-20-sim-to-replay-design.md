# sim → `.sts2replay` exporter with RNG parity

**Status:** design approved 2026-07-20; awaiting spec review before SP1 planning.
**Owner:** Perry
**Related workspaces:** `sts2-rl` (this repo), `Slay the Spire 2` (decompiled game source, RNG ground truth), `RunReplays` (the replay mod + format).

## Goal

A pure-Python tool in `sts2-rl` that plays a trained run policy (target:
`runs/sts2_run_torch_v5.pt`) through the simulation over a chosen **game seed**
and emits a single `actions.sts2replay` file which, dropped into the
RunReplays logs folder, replays the model's full three-act run **bit-exact**
on the real Slay the Spire 2 game.

Non-goals: no `run.save` generation, no C# changes to RunReplays, no live
"bot drives the game" bridge. The deliverable is one text file per run.

## Why this is the shape it is (the two findings that set the constraints)

1. **A from-scratch replay needs no `run.save`.**
   `RunReplayMenu.StartReplay` (RunReplays) starts a fresh run from only the
   log header (`# Seed`, `# Acts`, `# Character`, `# Ascension`) plus the
   cumulative command list, via `NGame.StartNewSingleplayerRun(...)`. The
   per-floor `run.save` files exist only for the "resume/continue at floor N"
   feature. A `floor_49/actions.sts2replay` log holds the whole run from Neow
   onward. → Our entire deliverable is one `actions.sts2replay` file.

2. **A replay is only valid against the world its seed generates.**
   The game replays deterministically from the seed: it regenerates the exact
   map, card shuffles, monster moves, and reward rolls, and the recorded
   commands (map columns, per-combat card ids, reward indices) line up because
   that world is reproduced. A sim rollout is a *different* world unless the
   sim reproduces the game's RNG. The sim today explicitly has **no seed
   parity** (`actmap.py`: "one shared `random.Random` … no seed parity with
   the real game"). Therefore the core of this project is making the sim
   reproduce the game's RNG-driven world for a given seed.

   Because *we* choose the seed and the parity-sim reproduces that seed's
   world, the emitted commands are valid on the real game. Everything hinges
   on parity holding.

## Data flow

```
string seed ──► RunRngSet (12 ported streams, seeded identically to the game)
                    │
                    ▼
        parity-sim full run (driver.RunDriver) ──► model answers each
                    │                              DecisionRequest (greedy,
                    │                              from the checkpoint)
                    ▼
     decision trace  +  live combat-card-id table (ported NetCombatCardDb)
                    │
                    ▼
        command translator ──► actions.sts2replay  (header + command list)
```

## Component 1 — the parity contract (the core)

### RNG primitives (ground truth: `Slay the Spire 2/src/Core/Random/`)

- **`MegaRandom`** — Xoshiro256\*\* with splitmix64 seeding
  (`MegaRandom.cs`). Pure `uint64` math. `Reinitialise(ulong seed)` runs
  splitmix64 four times to fill `s0..s3`. Draw primitives:
  - `NextULongInner()` — the xoshiro step.
  - `NextDouble() = (NextULongInner() >> 11) * 2^-53`.
  - `NextInt() = (int)(NextULongInner() >> 33)`  (inclusive of int.MaxValue).
  - `Next(maxValue) = (int)(NextDouble() * maxValue)`  (`NextInner`).
  - `Next(min,max) = NextInner(max-min) + min`.
  - `NextUInt() = (uint)NextULongInner()`, `NextFloat() = (NextULongInner() >> 40) * 2^-24`.
- **`Rng`** — counter wrapper (`Rng.cs`). Every `Next*` increments `Counter`
  by one call to the underlying generator; `NextGaussian*` calls `NextDouble`
  **twice per rejection-loop iteration** (counter parity must match this).
  Methods we must port with exact semantics: `NextInt(max)`,
  `NextInt(min,max)`, `NextUnsignedInt(min,max)` (via `NextDouble`),
  `NextFloat(min,max)`, `NextDouble`, `NextBool` (`Next(2)==0`),
  `NextItem` (`NextInt(0,count)` then `ElementAt`),
  `WeightedNextItem` (uses one `NextFloat()`),
  `Shuffle` (Fisher-Yates: for i from n-1 downto 1, `j = NextInt(i+1)`, swap),
  `FastForwardCounter` (advances by discarding `NextInt()`s).
- **Seeding**: `RunRngSet.Seed = (uint)GetDeterministicHashCode(stringSeed)`;
  each stream `= new Rng(Seed, snake_case(streamName))
  = new Rng(Seed + (uint)GetDeterministicHashCode(snake_case_name))`. The uint
  seed widens to `ulong` (zero-extended) into `MegaRandom`.
- **`GetDeterministicHashCode`** (`StringHelper.cs`) — the exact two-accumulator
  int hash; must reproduce `int` overflow semantics (32-bit wraparound).
- **`SnakeCase`** (`StringHelper.cs`) — `CamelCaseRegex().Replace(txt.Trim(),
  "$1_$2").ToLowerInvariant()`. Applied to `RunRngType.ToString()` values, so
  in practice we can precompute the 12 fixed names, but we port the function
  and assert it against the enum names.

### The 12 streams (`RunRngSet.cs` / `RunRngType.cs`)

`UpFront, Shuffle, UnknownMapPoint, CombatCardGeneration,
CombatPotionGeneration, CombatCardSelection, CombatEnergyCosts, CombatTargets,
MonsterAi, Niche, CombatOrbs, TreasureRoomRelics`.

Stream isolation is the property that makes parity tractable: a desync in one
subsystem cannot corrupt another, so parity can be achieved and verified
subsystem by subsystem. `UpFront` "determines everything generated upfront when
a run starts" (monsters, events, relics offered); `Shuffle` drives every draw
pile; `MonsterAi` drives random monster moves; etc.

### The obligation

Replace the sim's single `random.Random` with a `RunRngSet`, and route **every
RNG call site in the ported engine through the correct stream in the same order
and count as the game**. This includes replacing Python's `random.shuffle` /
`random.choice` / `random.sample` with the ported `Shuffle` / `NextItem` — they
produce different sequences even on an identical stream. This is pervasive and
exacting; the failure mode is silent (one extra/missing draw desyncs a stream
and diverges downstream with no error), which is why Component 2 exists.

## Component 2 — the conformance harness (built first; the safety net)

A test harness that turns existing recordings into golden tests:

1. Parse a recording: header (`# Seed`, `# Acts`, `# Ascension`, `# Character`),
   the command list, and each command's inline `# comment` and
   `|| Hand: […] Enemies: […]` pre-state annotation.
2. Seed the parity-sim `RunRngSet` from `# Seed`; start the run with the
   recording's act list and `ascension` (Asc 1 ⇒ SwarmingElites map, base
   combat values).
3. Drive `driver.RunDriver`, answering each `DecisionRequest` by translating
   the recording's next command index into the matching `DecisionRequest`
   action (Component 3's mapping, used in reverse).
4. **Assert** at every command that the sim's live state matches the
   annotation: hand card ids/names, enemy names and `currentHp/maxHp`, reward
   options, etc.
5. At floor boundaries, diff each stream's `Counter` against the paired
   `run.save`'s `SerializableRunRngSet.Counters` (parses the save's rng block
   only — not full save deserialization).

The first assertion failure pinpoints the parity bug and its stream. The
`Resources/*` recordings (Ironclad, Asc 1, full 3-act) are the initial golden
corpus; more can be added by recording runs with the mod.

## Component 3 — command translation + combat-card ids

### DecisionRequest ↔ ReplayCommand mapping

| sim `DecisionKind` (driver.py)            | RunReplays command(s)                          |
|-------------------------------------------|------------------------------------------------|
| `MAP` (pick point)                        | `MoveToMapCoord {col}`                          |
| `COMBAT` end-turn                         | `EndTurn`                                       |
| `COMBAT` play h@e                         | `PlayCard {combatId} [{targetId}]`              |
| `COMBAT` potion p@e                       | `UsePotion {slot} [{targetId}]`                 |
| `EVENT`                                   | `ChooseEventOption {index}` (+ `-1` PROCEED)    |
| `SHOP` buy / leave                        | `OpenShop`, `BuyCard/BuyRelic/BuyPotion/BuyCardRemoval`, close |
| `REST`                                    | `ChooseRestSiteOption {HEAL\|SMITH\|…}`         |
| `REWARD_CARD` pick / skip                 | `ClaimReward {i}` + `TakeCard {i\|skip}`        |
| `REWARD_POTION`                           | `ClaimReward {i}`                               |
| `SELECT_CARDS` / `SELECT_OPTION`          | `SelectGridCard` / `SelectHandCards` / `SelectCardFromScreen` |
| treasure                                  | `OpenChest` + `TakeChestRelic`                  |
| act advance                               | `ProceedToNextAct`                              |

Details to pin down during SP4/SP5 against the recordings: `ClaimReward` index
ordering (gold/relic/potion/card button order on the screen), which selection
screen each `SELECT_*` purpose maps to, and shop entry ordering. The recordings
are the oracle for all of these.

### Combat-card ids (`NetCombatCardDb.cs`)

`PlayCard` uses a per-combat `uint` from `NetCombatCardDb`, assigned
deterministically: at `StartCombat`, `_nextId=0`, then `IdCardIfNecessary` walks
`player.PlayerCombatState.AllPiles.SelectMany(p => p.Cards)` assigning
sequential ids; afterward, cards newly added to any pile (generated statuses,
etc.) get the next id in pile-`ContentsChanged` order. We port this scheme and
run it inside the sim so each `COMBAT play` resolves to the same `uint` the game
will assign. Requires replicating the sim's pile membership/iteration order to
match `AllPiles`. Validated by checking our ids against the recordings'
`PlayCard {id}` values.

## Component 4 — the exporter (CLI)

```
py export_replay.py runs/sts2_run_torch_v5.pt --seed ABCDEFGHIJ \
    --ascension 1 --out actions.sts2replay [--sample]
```

Loads the checkpoint via the existing `checkpoints.load_agent` path, plays a
full run through `RunDriver` with a greedy (default) or sampling policy over the
run-env obs, records the decision trace + combat ids, and writes the header +
command list. Header fields: `# Character: IRONCLAD`, `# Seed`, `# Ascension`,
`# Acts: …` (from the sim's rolled act list), `# Game`, `# Mod` (match the
target game/mod versions).

## Decomposition & sequencing

Five sub-projects, each its own spec → plan → implementation, each gated on the
harness staying/going green. Milestone (per approval): a **full three-act**
model run exported and replaying on the real game.

- **SP1 — RNG core.** Port `MegaRandom`, `Rng`, `GetDeterministicHashCode`,
  `SnakeCase`, `RunRngSet`. Tests: raw Xoshiro256\*\* against published
  reference vectors; splitmix64 seeding; hash/snake-case against the enum
  names; counter accounting. Low-risk, foundational.
- **SP2 — Stream wiring + map/economy parity + the harness.** Swap the sim's
  single `random.Random` for `RunRngSet`; port map generation and unknown-room
  rolls onto `UpFront`/`UnknownMapPoint` with matching draw order; build the
  conformance harness. Green: a recording's map traversal and room types
  reproduce exactly.
- **SP3 — Combat parity.** `Shuffle` (draw piles) + `MonsterAi` (random moves)
  + combat generation/selection/targets/energy streams. Highest-frequency,
  highest-risk. Green: `Hand/Enemies` annotations match through full fights.
- **SP4 — Rewards / events / shop parity.** Reward, relic, potion rolls and
  event RNG on their streams; the reward/screen index mapping. Green: reward
  and event command indices match.
- **SP5 — Combat-card-id replication + exporter.** Port `NetCombatCardDb`;
  build the translator and `export_replay.py`. Green: a full 3-act recording
  round-trips (import → re-export → identical commands), and a model run emits
  a replay that loads and plays on the real game.

## Risks & mitigations

- **Silent desync (primary risk).** Mitigation: harness-first; assert against
  per-command state annotations and per-floor stream counters, so a divergence
  is localized to one stream and one command.
- **Draw-order gaps in existing ports.** The sim ports the game's *logic* but
  not its draw order/primitives; some sites batch or reorder draws, or use
  Python RNG primitives. Each must be rewritten to the ported `Rng` in game
  order. Scope is bounded (finite call sites) but pervasive.
- **`AllPiles` iteration order for combat ids.** Must match the game's pile
  enumeration; validated directly against recordings.
- **Screen/index conventions** (`ClaimReward`, `SELECT_*`, shop order) are
  under-documented; the recordings are the oracle — treat any mismatch as a
  bug to fix against them.
- **Save-counter parsing.** We parse only the rng block of `run.save`; if the
  format is opaque (Godot binary), fall back to state-annotation asserts only.

## Assumptions verified during design

- Ascension 1 = `SwarmingElites` only (`AscensionLevel` enum: `None=0,
  SwarmingElites=1, WearyTraveler=2, …`); combat/economy scaling starts at
  Asc 2. So Asc-1 recordings carry base combat values matching the sim, and we
  generate sim runs at `ascension=1` (8-elite map).
- The sim wires full three-act runs (`run.py` `_ACTS_BY_INDEX =
  [[overgrowth, underdocks], [hive], [glory]]`, `advance_act`); the actmap
  "Acts 2-3 run layers aren't in the sim yet" comment is stale (Act 2/3 content
  epic completed 2026-07-17).

## Carried-forward RNG gaps (from SP1's final review — SP2/later must handle)

SP1 (RNG core) shipped `MegaRandom`, `Rng`, the hash/`snake_case`, and `RunRngSet`,
all golden-verified (suite green, 2162 tests). The whole-branch review surfaced pieces
deliberately out of SP1 scope that later SPs must not forget:

- **`PlayerRngSet` / `PlayerRngType`** (`src/Core/Random/PlayerRngSet.cs`): the per-player
  sibling of `RunRngSet` — 3 streams `Rewards`, `Shops`, `Transformations`, same
  `CreateRng`/`SnakeCase` pattern. `Shops` drives shop price jitter, `Rewards` drives
  reward generation → **needed for SP2 (economy)**. Primitives already exist; only the
  thin wrapper class is missing.
- **`Rng.NextGaussianInt/Float/Double`** (`Rng.cs:190-247`): rejection-sampling Gaussians
  used by map generation for rest-site counts (`Overgrowth/Hive/Underdocks.cs`,
  `MapPointTypeCounts.StandardRandomUnknownCount`) → **needed for SP2 (map parity)**.
  Counter consumption is data-dependent (loop over `NextDouble`); needs a golden vector.
- **`Rng(Player, ModelId, mixin, counter)`** per-content constructor (`Rng.cs:47-50`):
  used by relics (Byrdpip, FurCoat) → needed whenever relics/per-content RNG are ported.
- **`weighted_next_item` float32 fidelity**: currently double-accumulated (has a
  `TODO(later SP)` in `rng.py`); no consumer in the decompiled source yet. Fix to float32
  + add a golden vector when the first caller is ported.
- **`next_unsigned_int`** now has golden coverage; `MegaRandom.NextBool/NextUInt/NextULong/
  NextBytes` remain unported but are confirmed unused by `Rng` (add only if a direct
  `MegaRandom` consumer appears).

## Acceptance

1. Conformance harness replays every `Resources/*` recording through the
   parity-sim with zero state-annotation mismatches and matching stream
   counters, across all three acts.
2. `export_replay.py runs/sts2_run_torch_v5.pt --seed <s>` produces an
   `actions.sts2replay` that loads from the RunReplays main menu and plays the
   model's full run to its recorded end without divergence stalls.
