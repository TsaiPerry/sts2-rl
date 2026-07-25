# RunReplays auto-validation mod — design / spec

**Status:** PROPOSAL — Perry's decision required (see §8). Not implemented.
**Date:** 2026-07-24
**Related workspaces:** `RunReplays` (the C# mod — where all code changes land),
`sts2-rl` (the sim + conformance harness that consumes the output).
**Lineage:** closes the manual step in
[`2026-07-23-sp3-efficient-convergence.md`](../plans/2026-07-23-sp3-efficient-convergence.md)
Task 10, and the manual acceptance step in
[`2026-07-20-sim-to-replay-design.md`](2026-07-20-sim-to-replay-design.md) §Acceptance 2.

---

## 1. Problem

Two verification loops still end with a human watching the game:

1. **Exporter validation (SP5).** `export_replay.py` emits an
   `actions.sts2replay` for a model run. The design's Acceptance 2 is "it loads
   from the RunReplays main menu and plays the model's full run … without
   divergence stalls" — verified by a person loading it and watching all three
   acts play out.
2. **Conformance ground-truth spot-checks.** When a sim divergence is
   ambiguous ("is the sim wrong or is the recording stale?"), the tie-breaker is
   replaying the same commands on the real game and reading the state by eye.

Both are the bottleneck the efficient-convergence work did *not* remove: the
sim side is now cheap (DETECTOR 4, deterministic replays, fuzz gates), but
crossing to game-truth is still manual and slow.

**Goal:** a hands-off loop — point the mod at an `actions.sts2replay`, it
launches, plays at max speed with no clicks, dumps the game's *realized*
per-command state, and exits. The sim side then diffs predicted vs realized
offline. Zero human play.

## 2. What already exists in the mod (do not rebuild)

The mod is ~80% of the way there. The delta is small because these are already
present:

| Capability | Where | Note |
|---|---|---|
| Auto-launch a replay on main-menu open | `MainMenuButtonInjector.cs:35,131` — `#if RUNREPLAYS_AUTOPLAY` + `const string AutoPlayTarget` | Exists but **compile-flagged and hardcoded** to one seed:floor. |
| Resolve + start a replay by seed/floor | `RunReplayMenu.AutoPlay(target)` → `StartReplay(entry)` | Scans the **logs dir** only; needs a "replay an arbitrary file path" path. |
| From-scratch replay needs no `run.save` | `StartReplay` → `NGame.StartNewSingleplayerRun` (per sim-to-replay design §Why 1) | An exported log's header + command list is sufficient. |
| Max-speed replay | `ReplayDispatcher.GameSpeed` → `Engine.TimeScale` (`ReplayDispatcher.cs:649-667`) | Already re-applied after transitions (`:1050`). |
| Full per-command game state, JSON-serializable | `GameStateSnapshot` (`GameStateSnapshot.cs`) — Hand/Draw/Discard/Exhaust, Enemies w/ CombatId·HP·Powers·Intent, Potions, Relics, Gold, Floor | Already serialized at `ReplayDispatcher.cs:548`, but the JSON is currently only fed to a debug channel, never persisted. |
| Text pre-state annotation, same grammar the sim parses | recorded via `PlayerActionBuffer`; format `# CARD.X (id) \|\| Hand: [names] Enemies: [name hp/maxhp]` | Identical grammar to `sts2_rl/conformance/recording.py` `_parse_annotation`. |
| Recorded-vs-live divergence check | `ReplayDispatcher.CheckPreState` → `DiagnosticLog "StateCheck"` | Already compares `cmd.ExpectedPreState` to live state per command. |
| Replay-finished hook | `ReplayEngine.ReplayCompleted` event | Fires when the command queue empties naturally. |
| Diagnostic log sink | `DiagnosticLog.Write(cat, msg)` → `{UserDataDir}/RunReplays/*.log` | Reuse for the run summary. |

## 3. The delta (four changes, all in the RunReplays repo)

### 3.1 Configurable, always-compiled launch target

Replace the `#if RUNREPLAYS_AUTOPLAY` + `const AutoPlayTarget` with a runtime
source resolved once on main-menu open:

- **Env var** `RUNREPLAYS_AUTOPLAY` (primary — CI/script-friendly), else
- **File** `{UserDataDir}/RunReplays/autoplay.txt` (first non-empty line), else
- inert (current behaviour: menu button only, no auto-play).

The target value is **either** the existing `SEED` / `SEED:floor_N` form
(resolved against the logs dir, unchanged) **or an absolute path** to an
`actions.sts2replay` file. Exported replays live outside the logs tree, so a
path is required — detect it with `File.Exists(target)` / path-separator
presence before falling back to the seed-scan resolver.

Ship it always-compiled but **inert unless the source is set**, so a normal
player build is unaffected. This is the only behaviour change visible to a
non-validating user, and it is a no-op for them.

### 3.2 Start a replay from an arbitrary file path

Add a `StartReplayFromFile(string path, RunReplayOutputCtx ctx)` alongside the
existing `StartReplay(entry)`. It parses the header + command list from that
file (the parser already exists — `ReplayCommandParser`) and calls the same
`NGame.StartNewSingleplayerRun` path. No `run.save` needed (design §Why 1).

### 3.3 Re-annotation dump during replay (the actual new artifact)

While `ReplayEngine.IsActive` and an output context is set, on **each consumed
command** capture the live pre-state and append to two files in a per-run output
dir (default `{UserDataDir}/RunReplays/autoplay-out/{runId}/`, overridable via
env `RUNREPLAYS_AUTOPLAY_OUT`):

- **`replayed.sts2replay`** — the command line re-emitted with the game's
  *realized* `|| Hand: [...] Enemies: [name hp/maxhp]` annotation, byte-identical
  grammar to the recorded/exported format. This is the primary diff target: the
  sim's exported file holds *predicted* annotations, this holds *realized* ones.
- **`annotations.jsonl`** — one `GameStateSnapshot` JSON per command (the object
  already built at `ReplayDispatcher.cs:548`; today it is serialized then
  dropped). Carries the richer state the text annotation omits — relics,
  potions-by-slot, player/enemy powers, draw/discard/exhaust piles, gold —
  which is exactly the SP3/SP4 state the sim now tracks per floor (DETECTOR 4).

Hook point: the same place `CheckPreState` runs (first execution of each
command, `PreStateChecked` guard already dedups retries). Write via a buffered
writer flushed on `ReplayCompleted` and on the stall watchdog.

### 3.4 Max-speed + auto-exit + machine-readable result

In autoplay mode:

- set `ReplayDispatcher.GameSpeed` to a high value (e.g. `8`–`16`; it is already
  re-applied after scene transitions);
- subscribe `ReplayEngine.ReplayCompleted` to flush the dumps, write
  **`result.json`** `{ target, commandsConsumed, lastFloor, stalled: bool,
  stallReason?, stateCheckDivergences: int }`, and quit:
  `GetTree().Quit(exitCode)` — `0` = clean finish, `1` = stalled/aborted.
- also fold the existing `CheckPreState` "StateCheck" divergence count into
  `result.json` (free in-mod signal; the authoritative diff is still offline).
- reuse the existing **stall watchdog** (`ReplayState.ClearActionInFlight` /
  the dispatch poll) to bound a hung replay: if no command is consumed within a
  timeout, write `result.json` with `stalled:true` and quit `1` rather than
  hanging forever.

## 4. Sim-side consumption (no mod code — for context)

The mod stays dumb; the diff logic lives in the sim toolchain where the team
already iterates:

1. `export_replay.py` gains (or already has) `|| Hand/Enemies` annotations on
   each `PlayCard`/`EndTurn` — it has the sim state, so this is the sim's
   *prediction*. (If not yet emitted, that is a one-line exporter addition, not
   a mod change.)
2. New `tools/validate_export.py` (sim side): given the exported file and the
   mod's `replayed.sts2replay` + `annotations.jsonl`, diff predicted vs realized
   per command using the existing `recording._parse_annotation`, and reuse
   `comparators.py` for the JSONL. Output mirrors DETECTOR 4's per-command
   Hand/Enemies delta format, so the two loops read the same.

## 5. Recommended comparison strategy

Two options were considered:

- **(A) In-mod compare only.** Load the exported (predicted) annotations as
  `ExpectedPreState`; `CheckPreState` already logs divergences. Cheapest — no
  new dump. But the diff rules live in compiled C#, the "divergence" definition
  can't evolve without a game rebuild, and it can't see relics/potions/powers
  (text annotation drops them).
- **(B) Dump + offline diff.** §3.3 + §4. The mod only records; the diff is
  Python.

**Recommend (B), keep (A) as a free bonus** (the `StateCheck` count in
`result.json` costs nothing). Rationale: the divergence semantics belong beside
DETECTOR 4 in the sim toolchain the team iterates daily; JSONL captures the full
per-floor state the sim now tracks; the mod never needs a rebuild to change what
counts as a divergence.

## 6. Effort & files touched (RunReplays repo)

Small — roughly four edits, all reusing existing machinery:

- `MainMenuButtonInjector.cs` — env/file target resolution replacing the
  compile-flag + const (§3.1).
- `RunReplayMenu.cs` — `AutoPlay` path-vs-seed branch + `StartReplayFromFile`
  (§3.2).
- `ReplayDispatcher.cs` — persist the already-built snapshot to
  `annotations.jsonl` + `replayed.sts2replay` at the `CheckPreState` hook; wire
  `GameSpeed`, `ReplayCompleted` → `result.json` + `GetTree().Quit` (§3.3, §3.4).
- one new small `AutoplaySession.cs` (or fold into `RunReplayMenu`) holding the
  output context + writers.

Sim side (separate, no mod build): `tools/validate_export.py` + optional
exporter annotation emit.

## 7. Risks & caveats

- **Not truly headless.** STS2 is a Godot game; `Engine.TimeScale` + auto-quit
  is the realistic "fast + hands-off", but it still opens a window and needs a
  GPU/display session. Fine for a local one-shot or a self-hosted runner; not a
  clean cloud-CI job without a virtual display.
- **Can't be unit-tested in the sim harness.** Validation of the mod change
  itself is a manual smoke test (build the mod, drop in `mods/`, set the env
  var, launch, confirm it plays + writes the three files + exits). Budget one
  manual pass per change to this code.
- **Gameplay-affecting mod.** `RunReplays.json` already declares
  `affects_gameplay: true`; the always-compiled auto-play is inert without the
  env/file trigger, so a normal player build is unchanged — but this must be
  verified (menu still works, no auto-launch when the trigger is unset).
- **Timescale fidelity.** Very high `Engine.TimeScale` can starve animation-gated
  logic the dispatcher waits on; the existing dispatch-poll + settle hooks should
  absorb it, but the smoke test must confirm a full 3-act run completes at the
  chosen speed without spurious stalls (start at `8`, raise only if clean).

## 8. Decision required (why this is a proposal, not a plan)

This **contradicts a stated non-goal** of the sim-to-replay design:

> Non-goals: no `run.save` generation, **no C# changes to RunReplays**, no live
> "bot drives the game" bridge. The deliverable is one text file per run.
> — `2026-07-20-sim-to-replay-design.md:15`

The non-goal was chosen to keep the export deliverable a pure text artifact and
avoid maintaining game-side code. This proposal reopens exactly that: it adds
C# to RunReplays to automate validation. That is a real trade — less manual
validation time vs. a new gameplay-affecting mod surface to maintain against
game updates.

**Options for Perry:**

1. **Build it (recommend B).** Highest ROI once export validation becomes the
   bottleneck; scope is genuinely small because the machinery exists.
2. **Build the minimal (A) only.** Un-hardcode the auto-play target + surface
   the existing `StateCheck` count + auto-quit. No new dump files. Least code,
   keeps the mod nearly as-is, but the diff stays coarse (no relics/potions/
   powers) and lives in C#.
3. **Defer.** Keep manual validation; the sim-side loop is already cheap and
   export validation is infrequent. Revisit if/when SP5 export becomes routine.

No implementation happens until this is chosen.
