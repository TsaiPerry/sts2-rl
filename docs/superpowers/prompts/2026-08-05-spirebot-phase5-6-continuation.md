# SpireBot continuation — Task 16 parity grind → Phase 6 training

Continue the SpireBot live-bot project. Plan: `c:\Users\Perry\Desktop\sts2-rl\docs\superpowers\plans\2026-08-04-spirebot-live-bot.md`.
Read the `spirebot-live-bot-planned` memory first — it holds the full 2026-08-05 debugging history and every gotcha below in detail.

## Rules (non-negotiable)

- **Never `git commit` or `git push` in any repo. Stage only (`git add`); Perry commits.**
- Dispatch all subagents on **sonnet**.
- `sts2_rl/vocab.json` is frozen append-only.
- Full Python suite green at every task boundary: `py -m pytest test/ -q` from `c:\Users\Perry\Desktop\sts2-rl` (baseline **4730 passed / 1 skipped / 4 xfailed / 0 failed**).
- The obs schema is FROZEN once training starts (Task 17). Any change after that restarts training.

## Where things stand

Tasks 1–15 and Task 16 Step 1 are implemented and staged (uncommitted) across two repos:

- `c:\Users\Perry\Desktop\sts2-rl` — schemas combat v7 / run v10, `sts2_rl/live/` (`contract.py`, `export_contract.py`, `export_onnx.py`, `game_ids.py`, `sim_obs_dump.py`, `compare_obs.py`) + their tests.
- `c:\Users\Perry\Desktop\SpireBot` — the mod (net9.0 / Godot 4.5.1). Vendored RunReplays machinery lives in `SpireBotCode/Replay/` (namespace `SpireBot.Replay`); read `SpireBotCode/Replay/VENDORED-FROM.md` before touching it — it records all 6 intentional deltas.

**A full hands-off run works.** It cleared combats, an elite, events, a shop, rest sites and a treasure room before dying at an elite (expected: `FirstLegalPolicy` plays cards left-to-right and always targets the first living enemy). Zero policy/executor/obs exceptions.

Deployed at `D:\SteamLibrary\steamapps\common\Slay the Spire 2\mods\SpireBot\` (dll + `model\contract.json` + `model\stub.onnx`).

## Next steps, in order

### 1. Task 14 acceptance — stub-ONNX run (quick, needs Perry at the keyboard)

Set `OnnxModelPath` in SpireBot's in-game config to
`D:\SteamLibrary\steamapps\common\Slay the Spire 2\mods\SpireBot\model\stub.onnx`
(empty = `FirstLegalPolicy`; a directory also resolves via `ModPaths`). This is uniform-random-over-legal, so it exercises targeting, potions and skip/take decisions far more broadly than first-legal. Watch the overlay and the log for `MAPPING GAP` lines.

### 2. Task 16 Steps 2–3 — the obs parity grind (the real gate before training)

This is the plan's acceptance linchpin: **byte-parity between the sim's obs and the mod's obs** over the two converged replays (89U21BV1TZ, 933T39V18D), `f` within 1e-6 and `i` exact.

- **Step 2a — add `PassiveDump` to `SpireBotConfig`.** In passive mode `BotController` observes and dumps at each decision **without acting**, so RunReplays' own playback drives the run. Do NOT set `ReplayEngine.BotDriving` in passive mode — a real replay sets `IsActive` itself.
- **Step 2b — produce the game dump.** Replay 89U in-game with the **local RunReplays fork** (`c:\Users\Perry\Desktop\RunReplays`, dev-machine only) with SpireBot in passive dump mode. Set `DumpDecisions=true` and a real `DumpDir` (empty `DumpDir` silently disables dumping — it only logs a notice).
- **Step 2c — produce the sim dump.**
  ```
  cd c:\Users\Perry\Desktop\sts2-rl
  py -m sts2_rl.live.sim_obs_dump --seed 89U21BV1TZ --out sim_89U.jsonl
  py -m sts2_rl.live.export_contract --out contract.json
  ```
- **Step 3 — grind to parity.**
  ```
  py -m sts2_rl.live.compare_obs sim_89U.jsonl game_89U.jsonl --contract contract.json
  ```
  Fix C# writers, or the sim where the C# side reveals a real sim bug (then re-run the suite). Log every fix — that list is the review artifact. Repeat for 933T39V18D. Exit code 0 on both seeds is the gate.

Join key is `(floor, kind, decision_index)`. **`floor` is the per-act floor** (`ActFloor` = `current_point.row + 1`), not a cumulative floor. In-combat `SelectCards` decisions never appear in the sim dump (resolved inside `ReplayCombatDriver._grid_selector`) — that carve-out is already built into `compare_obs`.

### 3. Phase 6 — Tasks 17–18 (train, export, showcase)

Only after parity. Train an entset run-env checkpoint (`train_torch.py`, `--device cuda`, `--shared-encoder`), bar = beats masked-random on mean floor. Then `export_onnx runs\<name>.pt` (the checkpoint-parity test activates), point the mod at it, and do three consecutive hands-off runs with zero unhandled exceptions.

## Known open items

- **Shop purchases are unverified.** C# purchase commands are title-keyed; the sim indexes `all_entries` positionally. Opening the shop works now; buying is untested. A `MAPPING GAP — kind=Shop` line after the wares are visible is this bug.
- Other flagged mapping questions: rest-site `OptionId` strings (substring heuristic), select-candidate ordering (C# uses screen order; the sim sorts by `_run_card_row`), reward-screen architecture mismatch (no reroll-slot command), `hand.f` magic_number is 0, `event.page`/`select.count`/`select.purpose.ids` are 0, `run.boss.ids` may over-report.
- Perry may still want the inert flat `mods\RunReplays.dll` + `.json` deleted (hash-identical to the `mods\RunReplays\` subfolder copy; the loader only scans subfolders, so they do nothing).

## Gotchas that cost hours already

- **The decompiled game source is at `c:\Users\Perry\Desktop\Slay the Spire 2\src\`** — grep it for any "what does the game actually do" question instead of disassembling `sts2.dll`.
- **Diagnose stalls with `StallDiagnostics`**, not by reading code: `grep "\[SpireBot\]" "$APPDATA/SlayTheSpire2/logs/godot.log"` after the Bot Run press. Its one-line `STALL (...)` dump names kind/available/map-travel/event-finished/room/blocked-flags/dispatchable, which has identified every stall in a single run.
- **The real exception often isn't in `godot.log`** — it may only be in the Sentry breadcrumbs at `%APPDATA%\SlayTheSpire2\sentry\<uuid>.run\__sentry-breadcrumb1` (that is how the launch-crash `FileNotFoundException` was found).
- **`OS.IsDebugBuild()` is always false in the shipped game** (it runs export_release). Gate debug work on `SpireBotConfig.SelfChecks` instead.
- **The build fails at the copy step while the game is running** (DLL lock). Verify a compile with `dotnet build ... -p:ModsPath=<scratch dir>`, then rebuild properly once the game is closed.
- **The bot must obey the game's own preconditions**, in two forms: control-level `Affordance.IsLive(NClickableControl)` (`IsEnabled && IsVisibleInTree()` — clicks are gated in the input path, so `EmitSignal(Released)` bypasses everything), and state-level predicates like `Affordance.RelicPickingActive()`. Every "the bot did something a player can't" bug is one of these — check for an existing guard first (`ProceedToMapCommand` already had one).
- **The vendored enumerator answers "is this command type legal on this screen", not "should it be issued again."** Recorded replays supplied idempotency implicitly; a live policy does not.
