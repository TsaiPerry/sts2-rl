# SP3 — player-state parity (DETECTOR 3) + full-run convergence

**Status:** design approved 2026-07-22 (approach + resync + map-stop handling +
process all confirmed with Perry); awaiting spec review before planning.
**Owner:** Perry
**Parent:** `2026-07-21-sp3-combat-parity-design.md` (this is the convergence
half of SP3 Task 9, re-scoped from "route RNG bugs one by one" to "make player
state observable and fix it in aggregate").
**Related workspaces:** `sts2-rl` (this repo), `Slay the Spire 2` (decompiled
game source, ground truth), `RunReplays` (recordings + `run.save` oracles).

## Why this re-scope (ground truth established during investigation)

The SP3 combat-RNG seam is done for everything the recordings exercise:

- **`converge_triage.py` DETECTOR 1 (RNG tripwire) reports ZERO wrong-stream
  in-combat draws** on `89U21BV1TZ/floor_18` (FULLY CONVERGED) and
  `.../floor_49`. Every in-combat draw already routes to the correct stream.
- The remaining floor_49 signal was DETECTOR 2 **under-draws** (Shuffle −523,
  CombatCardGeneration −1027). Those are not mis-routed call sites — they are
  **rooms that never executed.** The runner reports `stopped_reason="player
  died"` at `rooms_walked=23` of 47.

The player dies because of a **player-HP divergence the harness never checks.**
At floor 18 the sim reaches **10/71 HP where the game is at 56/71** — a ~46-HP
gap accumulated across act 1 — even though every combat's `Hand`/`Enemies`
annotations match, RNG is clean, and the SP2/SP3 stream counters match. The
harness's convergence definition (`Hand`/`Enemies` + counters + `forced_combats`)
has a blind spot: **it never asserts player HP, max HP, block, or heals.**

Root cause of the dominant gap is identified and verified: **the run never
grants the character's starting relic.** The game's `run.save` relic list at
floor 18 begins with `RELIC.BURNING_BLOOD` (`floor_added_to_deck: 1`); the sim's
relic list has every other relic but not `burning_blood`. Burning Blood heals 6
HP at end of combat (`relics/burning_blood.py`, `on_combat_end`), so over act 1's
~8 combats that is ~48 HP — almost exactly the observed 46-HP gap. Injecting
`burning_blood` at run start (diagnostic only) closes floor 18 to **54/71 vs
56/71** (2-HP residual) and **unblocks the entire run**: all 45 rooms replay,
no death.

With the run no longer dying, the real tail of work becomes observable across
all 5 seeds (Burning Blood injected, floor_49):

| Seed | Reaches | Sim HP | Game HP | Signal |
|---|---|---|---|---|
| 89U21BV1TZ | act 2 boss (45) | 77/77 | 33/111 | max −34, current +44 |
| TZEKRYTSNT | act 2 boss (45) | 80/80 | 60/67 | max −13, current +20 |
| L081UMJX4M | stops room 35 | 100/100 | 65/65 | "unreachable map coord" |
| DJDCSAQZNR | stops room 17 | 64/80 | 7/75 | "unreachable map coord" |
| QRWCVDPZN5 | stops room 20 | 56/67 | 38/51 | "no more MoveToMapCoord" |

Three residual classes remain: (1) **max-HP divergences in both directions**
(missing/mis-applied max-HP-changing content — events, rest-site, relics); (2)
**current-HP drift** (sim consistently takes too little damage / over-heals,
often ending at full); (3) a few **map/runner stops** that halt three seeds
before the end.

## Goal

Make **player state (HP + max HP)** a first-class, asserted oracle in the
conformance harness, and drive the full run of every `Resources/*` recording to
completion with player HP/max-HP matching the `run.save` snapshot at every floor
boundary (18/34/49) across all three acts — reusing the DETECTOR-style
structural triage so divergences surface in aggregate, not one death at a time.

Green target: for all 5 seeds, the parity runner replays every room through
floor_49 (no `player died` / `unreachable map coord` / `no more MoveToMapCoord`
stop), the seven combat-stream counters stay matched (no regression of the
RNG parity already achieved), and the player's `current_hp`/`max_hp` equal the
`run.save` values at floors 18, 34, and 49.

## Non-goals (later / out of scope)

- **RNG re-routing.** DETECTOR 1 is already clean for exercised content; this SP
  must not regress it. Proactively routing un-exercised combat RNG sites
  (colorless cards, unported monsters — no recording oracle) is deferred.
- **Deck / gold / potion parity** beyond what HP fidelity requires. Those are
  SP4 (`Rewards`/`Shops`) streams and their own oracles; the player-state oracle
  is *built to grow* into them but this SP asserts HP/max-HP only.
- **No changes to the RL training/eval path's behavior.** The legacy
  `random.Random` combat/run path and the RL run env stay byte-for-byte
  identical; the starter-relic grant and the resync are gated so they never
  affect a non-parity (no-`string_seed`) run — see the seam notes per work unit.
- Orbs / unported content (spec's standing SP3 non-goal).

## Architecture

Three additions, each isolated and independently testable:

- **Player-state oracle (`conformance/save.py`).** Extend `SaveOracle` with
  `player_current_hp: int` and `player_max_hp: int`, parsed from
  `players[0].current_hp` / `players[0].max_hp`. Pure parse; no behavior change.

- **Floor-boundary assertion + resync (`conformance/runner.py`).** At each act
  boundary and at run end, compare `run.hp`/`run.max_hp` to the oracle snapshot
  and emit a `Divergence` (new `"player_hp"` / `"player_max_hp"` streams) on
  mismatch. When resync is enabled, *after* asserting, pin `run.hp`/`run.max_hp`
  to the oracle values so an act-N bug cannot cascade into act N+1 or kill the
  player. Resync is **parity-only and opt-in** (a runner flag, default off for
  existing SP2 asserts; on for the new player-state test), and the single
  floor-18 snapshot only exists for act boundaries the recording actually
  reaches — so it degrades gracefully when a seed stops early.

- **DETECTOR 3 (`tools/converge_triage.py`).** Print the per-floor
  `player_hp`/`player_max_hp` deltas alongside DETECTOR 1/2, mapped to the
  likely source class (starter/relic heal, max-HP event, damage pipeline) so
  each delta points at where to look — the HP analogue of DETECTOR 1's
  file:line tripwire.

The starting-relic fix is a **run-layer content fix**, not a harness change:
`RunState.start_run` must grant the character's starting relic(s) the way the
game does (`burning_blood` for this character). **Decision (Perry, 2026-07-22):
grant it in ALL runs, not parity-only** — the game always grants it, so this is
a fidelity correction under `[[original-means-game-source]]`; the RL run env
becomes more faithful and any legacy test that encoded the relic-less start is
updated to the game-correct state. The full existing suite is the guard that
nothing else moves.

## Work units (each gated on the suite staying green)

### U1 — grant the starting relic
Find where the game grants the character's starting relic (character/run
initialization in the source) and grant it in `RunState.start_run` (before Neow
relics, `floor_added_to_deck: 1`). Verify: `89U21BV1TZ` floor-18 sim HP moves
from 10/71 to ~54/71, and the run replays past room 23 without dying. Legacy
suite stays green (a fixed-seed run now carries the starter relic — update any
test that asserted the old relic-less starting state to the game-correct one).

### U2 — player-state oracle + floor-boundary assertion
Extend `SaveOracle` (parse `current_hp`/`max_hp`). In the runner, at each act
boundary / run end, assert `run.hp`/`run.max_hp` against the snapshot and record
`player_hp`/`player_max_hp` `Divergence`s. Verify: the assertion fires the known
residuals (floor-18 −2 current on 89U, the max-HP gaps) as explicit divergences
instead of silence.

### U3 — opt-in floor-boundary resync
Add the parity-only resync (pin sim HP/max-HP to the snapshot after asserting).
Verify: with resync on, all 5 seeds replay to their natural recording end
without a `player died` stop, and each act's HP delta is reported independently
of the previous act's.

### U4 — converge (the loop, in aggregate)
With DETECTOR 3 live and resync isolating acts, iterate over all 5 seeds in one
pass. For each reported divergence class, in priority order:
1. **map/runner stops** ("unreachable map coord", "no more MoveToMapCoord") —
   triage each: a real map-generation / travel / act-transition fidelity bug
   gets fixed (so the full run replays); an unported-content stop is flagged.
2. **max-HP deltas** — find the max-HP-changing content the sim misses or
   mis-applies (max-HP events, rest-site, relics), fix against source.
3. **current-HP deltas** — the damage/heal-pipeline drift (sim takes too little
   damage / over-heals); fix against source, earliest act first.
Re-run the aggregate after each fix; stage per fix (small diffs, one subsystem).

## Verification & tooling

- `py tools/converge_triage.py [SEED] [FLOOR] [ACT]` gains DETECTOR 3 output.
- A parametrized `test/test_conformance_player_state.py` over the 5 seeds ×
  floor_49 asserts: run replays to end (no premature stop), combat-stream
  counters unregressed, and `player_hp`/`player_max_hp` match at each floor
  boundary reached.
- `py -m pytest test/ -q` (full suite, ~3.5 min) green after every unit;
  baseline is whatever the suite is at HEAD (report the number before U1).

## Risks & mitigations

- **Starter-relic grant perturbs the legacy/RL path.** It changes every run to
  carry the starter relic — which is the game-correct behavior, but it moves RL
  training/eval reward. Mitigation: it is a fidelity correction (the game always
  grants it), granted in ALL runs per the U1 decision; update the legacy tests
  that encoded the relic-less start; keep the full suite green. The RL run env
  gains the starter relic and would resume through the reward-distribution shift
  (e.g. `--critic-warmup`), consistent with `[[resume-after-env-change]]`.
- **Resync masks a real bug by pinning state.** Mitigation: resync happens
  *after* the assertion, so the divergence is always recorded; pinning only
  prevents cascade, it never suppresses the report.
- **Single floor snapshot per boundary.** We have HP only at floors 18/34/49, so
  a within-act bug localizes to an act, not a room. Mitigation: DETECTOR 3 maps
  the delta to a source class; per-combat instrumentation (sim-side HP log)
  narrows within the act when needed. Finer ground truth is not available in the
  recordings.
- **Map/runner stops may be SP2 regressions or new act-2/3 gaps.** Mitigation:
  triage each individually (U4 step 1); SP2's map/economy asserts stay green as
  the guard that a fix doesn't perturb map parity.

## Acceptance

1. `RunState.start_run` grants the character's starting relic; the full existing
   suite stays green (with any legacy starting-state tests updated).
2. The conformance harness asserts `player_hp`/`player_max_hp` at every floor
   boundary; `converge_triage.py` prints DETECTOR 3.
3. With resync on, all 5 seeds replay every room to the recording's end with no
   `player died` / `unreachable map coord` / `no more MoveToMapCoord` stop.
4. `player_hp`/`player_max_hp` match the `run.save` snapshot at floors 18, 34,
   and 49 for all 5 seeds, and the seven SP3 combat-stream counters are
   unregressed.
