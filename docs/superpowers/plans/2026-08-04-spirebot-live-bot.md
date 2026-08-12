# SpireBot Live Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A SpireBot mod that plays full Ironclad asc-0 runs live in Slay the Spire 2, driven by an sts2-rl-trained model running in-process via ONNX, with a thinking overlay.

**Architecture:** sts2-rl's obs schema is revised to a game-observable version (every field buildable from live game state) and the first checkpoint is trained on it. A `contract.json` exported from Python (layouts, vocab maps, action layout) is the single source of truth; the C# mod builds obs arrays itself, derives action masks from RunReplays' `GetAvailableCommands()` (game truth), runs the exported model with ONNX Runtime, and dispatches actions through RunReplays' command machinery. Converged conformance replays (89U21BV1TZ, 933T39V18D) are the cross-language acceptance harness for the C# obs builder.

**Tech Stack:** Python 3 (`py`), PyTorch + torch.onnx, pytest — in `c:\Users\Perry\Desktop\sts2-rl`. C# net9.0 / Godot 4.5.1, Harmony, Microsoft.ML.OnnxRuntime — new repo `c:\Users\Perry\Desktop\SpireBot`, plus small edits in `c:\Users\Perry\Desktop\RunReplays`.

**Spec:** `docs/superpowers/specs/2026-08-04-spirebot-live-bot-design.md` (same repo). Read it before starting any task.

## Global Constraints

- **Never `git commit` or `git push` in any repo. Stage only (`git add`); Perry commits.** This overrides every "commit" step convention.
- All subagents dispatch on **sonnet**.
- `sts2_rl/vocab.json` is frozen append-only — never hand-edit, reorder, or delete entries.
- **The obs schema freezes at Task 14 (training start).** Any schema change after that restarts training.
- Full suite must stay green at every task boundary: `py -m pytest test/ -q` from repo root (baseline ~4671 passed, 0 failed).
- C# repos: never commit machine-specific game paths. The game install may be on `D:` on this machine (RunReplays' committed csproj HintPaths have gone stale before — 468 spurious errors). Use `local.props` / verified HintPaths locally.
- The C# mod hard-refuses to run on any contract/schema/model version mismatch — no silent fallbacks on version skew.
- Bot failure policy in-game: any per-decision failure falls back to a safe scripted action and logs; the run never crashes.

---

## Phase 0 — Research (parameterizes the schema bump)

### Task 1: Damage-preview API research (game side)

**Files:**
- Create: `docs/superpowers/specs/2026-08-04-spirebot-damage-preview-research.md` (in sts2-rl)
- Read-only: decompiled game source (Perry can point at it; also `sts2.dll` via RunReplays/BaseLib references), `c:\Users\Perry\Desktop\BaseLib-StS2\Notes.txt`, `c:\Users\Perry\Desktop\RunReplays\RunReplays\GameStateSnapshot.cs`

**Interfaces:**
- Produces: a **KEEP or DROP verdict for the `damage_matrix` obs segment**, consumed by Task 3. If KEEP: the exact C# call sequence (class, method, arguments) that returns the game's computed damage preview for one (card, target creature) pair from mod code, plus any preconditions (must the card be hovered? does it require a UI node or is it pure model code?).

- [ ] **Step 1: Locate the game's card-damage preview computation.** The game UI shows hook-modified damage numbers on cards. Search the decompiled source / publicized `sts2.dll` surface for the calculation the card text uses. Search terms to start from (derived from BaseLib's reverse-engineering notes and sim naming): `CalculateDamage`, `GetDamage`, `preview`, `FormatCardText`, damage-related members on `CardModel` / `AttackCommand` (BaseLib has `Extensions/AttackCommandExtensions.cs` — read it first, it likely names the real types).
- [ ] **Step 2: Determine per-target callability.** Verify whether the computation can be invoked per (card, enemy) pair from mod code without UI interaction, and that it accounts for strength/vulnerable/relic hooks (compare mentally against sim `sts2_rl/previews.py` semantics). Write a 5-line C# pseudocode call sequence.
- [ ] **Step 3: Write the verdict doc.** `docs/superpowers/specs/2026-08-04-spirebot-damage-preview-research.md`: verdict (KEEP/DROP), call sequence if KEEP, evidence (file/class names), and any semantic caveats (e.g. multi-hit cards, AoE).
- [ ] **Step 4: Stage.**

```powershell
git -C "c:\Users\Perry\Desktop\sts2-rl" add docs/superpowers/specs/2026-08-04-spirebot-damage-preview-research.md
```

### Task 2: Game-observable obs schema audit

**Files:**
- Create: `docs/superpowers/specs/2026-08-04-spirebot-schema-audit.md` (in sts2-rl)
- Read-only: `OBS_SCHEMA.md` (repo root), `sts2_rl/obs.py`, `sts2_rl/full_env.py` (`combat_obs_layout`, `build_combat_obs`), the run obs builder in `sts2_rl/run_env.py`/`full_env.py`, `sts2_rl/relic_obs.py`, `c:\Users\Perry\Desktop\RunReplays\RunReplays\GameStateSnapshot.cs`, Task 1's verdict doc

**Interfaces:**
- Produces: the **field-by-field disposition table** consumed by Tasks 3–4 and the C# ObsBuilder tasks (11–12). One row per obs segment/field of combat v6 and run v9: `segment | field | disposition (KEEP / DROP / ACCUMULATE / REDEFINE) | game source (C# API path or "session state") | notes`.

- [ ] **Step 1: Enumerate every segment.** Walk `combat_obs_layout` and the run layout in code (not just OBS_SCHEMA.md — the code is normative) and list every `(segment, width)` for both `f` and `i` halves of both schemas.
- [ ] **Step 2: Classify each field.** For each: can the C# mod read it directly from game state (`RunManager.Instance.State`, `CombatManager`, `PlayerCombatState`, screen nodes — use `GameStateSnapshot.cs` as the catalog of what's reachable)? Directly readable → KEEP with the C# source named. Needs cross-turn memory (e.g. `enemy{e}.intent_history`) → ACCUMULATE with the accumulation rule stated. Sim-computed → apply Task 1's verdict for `damage_matrix`; anything else sim-only (hook-internal values with no game-readable equivalent) → DROP, or REDEFINE if a close game-readable proxy exists (state the proxy exactly).
- [ ] **Step 3: Check the mask contract.** Confirm every action in the run-env action layout is decidable from `GetAvailableCommands()` output (read `c:\Users\Perry\Desktop\RunReplays\RunReplays\ReplayDispatcher.cs`). List any action the enumerator can't express — each becomes either a RunReplays extension (goes into Task 8's scope) or a mask-off-always.
- [ ] **Step 4: Write the audit doc** with the full disposition table plus a summary of net width changes per schema. Every DROP gets a one-line justification.
- [ ] **Step 5: Stage.**

```powershell
git -C "c:\Users\Perry\Desktop\sts2-rl" add docs/superpowers/specs/2026-08-04-spirebot-schema-audit.md
```

---

## Phase 1 — sts2-rl schema bump (combat v7, run v10)

### Task 3: Combat obs schema v7

**Files:**
- Modify: `sts2_rl/full_env.py` (`OBS_SCHEMA_VERSION`, `combat_obs_layout`, `build_combat_obs`), `OBS_SCHEMA.md`
- Modify: existing combat-obs tests under `test/` (find with `rg "OBS_SCHEMA_VERSION|combat_obs_layout" test/`)
- Test: `test/test_obs_game_observable.py` (new)

**Interfaces:**
- Consumes: Task 2's disposition table.
- Produces: `OBS_SCHEMA_VERSION = 7`; `combat_obs_layout()` and `build_combat_obs(state)` emitting only KEEP/ACCUMULATE/REDEFINE fields. Downstream tasks read widths from the layout, never from constants.

- [ ] **Step 1: Write the failing test.** In `test/test_obs_game_observable.py`, assert the new version and that dropped segments are gone:

```python
from sts2_rl import full_env

def test_combat_schema_v7_version():
    assert full_env.OBS_SCHEMA_VERSION == 7

def test_combat_layout_has_no_dropped_segments():
    layout = full_env.combat_obs_layout()
    names = {name for name, _ in layout.f_segments} | {name for name, _ in layout.i_segments}
    # Fill from the audit's DROP rows, e.g.:
    for dropped in DROPPED_COMBAT_SEGMENTS:  # literal list copied from the audit doc
        assert not any(n.startswith(dropped) for n in names), dropped
```

(Adapt attribute names to `ObsLayout`'s real API in `sts2_rl/obs.py` — read it first.)

- [ ] **Step 2: Run it, expect FAIL** (`py -m pytest test/test_obs_game_observable.py -q` → version still 6).
- [ ] **Step 3: Implement.** Apply the audit row-by-row to `combat_obs_layout` + `build_combat_obs`: delete DROP segments, keep KEEP, implement each REDEFINE exactly as its proxy row states. Bump `OBS_SCHEMA_VERSION` to 7. ACCUMULATE fields (intent history) stay in the schema — the sim already accumulates them; the audit row only documents the C# accumulation rule.
- [ ] **Step 4: Fix legacy tests.** Run the full suite; update every test that pinned v6 widths/fields to the new layout (per the "original means game source" convention — the new contract is the authority). Do not weaken tests: re-pin exact new widths.
- [ ] **Step 5: Full suite green.** `py -m pytest test/ -q` → 0 failed.
- [ ] **Step 6: Update `OBS_SCHEMA.md`** — new version, new segment table, and a per-field "game source" column copied from the audit.
- [ ] **Step 7: Stage** all modified files.

### Task 4: Run obs schema v10

**Files:**
- Modify: `sts2_rl/run_env.py` / `sts2_rl/full_env.py` (wherever `RUN_OBS_SCHEMA_VERSION` and the run layout/builder live), `OBS_SCHEMA.md`
- Modify: legacy run-obs tests
- Test: extend `test/test_obs_game_observable.py`

**Interfaces:**
- Consumes: Task 2's disposition table; combat v7 layout (embedded under the `combat.` prefix).
- Produces: `RUN_OBS_SCHEMA_VERSION = 10`; run layout/builder emitting only game-observable fields.

- [ ] **Step 1: Write the failing test** (same shape as Task 3: version == 10, dropped run segments absent, embedded combat block matches v7 widths).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the audit's run-schema rows; bump the version.
- [ ] **Step 4: Fix legacy tests; full suite green** (`py -m pytest test/ -q`).
- [ ] **Step 5: Update `OBS_SCHEMA.md`** run section.
- [ ] **Step 6: Stage.**

---

## Phase 2 — Contract + ONNX export (`sts2_rl/live/`)

### Task 5: Contract export

**Files:**
- Create: `sts2_rl/live/__init__.py`, `sts2_rl/live/contract.py`, `sts2_rl/live/export_contract.py` (CLI: `py -m sts2_rl.live.export_contract --out contract.json`)
- Test: `test/test_live_contract.py`

**Interfaces:**
- Consumes: `combat_obs_layout` / run layout (Tasks 3–4), `sts2_rl/vocab.py` + `vocab.json`, the game-id↔sim-id mapping in `sts2_rl/conformance/ids.py` / `idmap.py`, action constants from `full_env.py` / `run_env.py` (`N_ACTIONS`, `COMBAT_PLAY_BASE`, `COMBAT_POTION_BASE`, `CHOICE_BASE`, `SELECT_BASE`, `POTION_BASE`, `MAX_HAND`, `MAX_ENEMIES`, `MAX_POTIONS`, `MAX_SELECT_CANDIDATES`).
- Produces: `build_contract() -> dict` and a written `contract.json` with this exact top-level shape (consumed by C# `Contract.Load`, Task 10):

```json
{
  "contract_version": 1,
  "combat_obs_schema": 7,
  "run_obs_schema": 10,
  "f_dim": 0, "i_dim": 0,
  "layout": {
    "f": [{"name": "player.hp", "offset": 0, "width": 1}],
    "i": [{"name": "hand.card_id", "offset": 0, "width": 10}]
  },
  "vocab": {"cards": {"strike": 1}, "relics": {}, "powers": {}, "monsters": {}, "potions": {}, "events": {}, "purposes": {}, "afflictions": {}, "enchantments": {}},
  "game_id_map": {"cards": {"<game-model-id>": 1}},
  "actions": {
    "n_actions": 243,
    "combat": {"end_turn": 0, "play_base": 1, "max_hand": 10, "max_enemies": 6, "potion_base": 61, "max_potions": 3},
    "choice": {"base": 0, "slots": 0},
    "select": {"base": 0, "max_candidates": 0},
    "belt_potion": {"base": 0, "slots": 0}
  }
}
```

(`0` values above are placeholders in this plan only — the implementation reads every number from the live layout/env constants; nothing is hard-coded.)

- [ ] **Step 1: Write the failing tests** in `test/test_live_contract.py`:

```python
import json
from sts2_rl.live.contract import build_contract
from sts2_rl import full_env

def test_contract_dims_match_layout():
    c = build_contract()
    layout = full_env.run_obs_layout()  # adapt to the real accessor
    assert c["f_dim"] == sum(w for _, w in layout.f_segments)
    assert c["i_dim"] == sum(w for _, w in layout.i_segments)
    assert c["combat_obs_schema"] == 7 and c["run_obs_schema"] == 10

def test_contract_layout_offsets_are_contiguous():
    c = build_contract()
    for half in ("f", "i"):
        off = 0
        for seg in c["layout"][half]:
            assert seg["offset"] == off
            off += seg["width"]

def test_contract_vocab_matches_frozen_vocab():
    c = build_contract()
    from sts2_rl import vocab
    assert c["vocab"]["cards"] == {name: vocab.index_of("cards", name) + 1 for name in vocab.names("cards")}  # adapt to real vocab API; +1 = oid convention (0 is PAD)

def test_contract_game_id_map_covers_ironclad_cards():
    c = build_contract()
    assert len(c["game_id_map"]["cards"]) > 0
    # every mapped value must be a valid vocab id
    valid = set(c["vocab"]["cards"].values())
    assert set(c["game_id_map"]["cards"].values()) <= valid

def test_contract_is_json_serializable(tmp_path):
    p = tmp_path / "contract.json"
    p.write_text(json.dumps(build_contract()))
    assert json.loads(p.read_text())["contract_version"] == 1
```

- [ ] **Step 2: Run, expect FAIL** (module doesn't exist).
- [ ] **Step 3: Implement** `contract.py` (`build_contract()`) and `export_contract.py` (`__main__` CLI: `--out`, defaults `contract.json`). `game_id_map` comes from the conformance id mapping (`ids.py`/`idmap.py`) inverted to game-id→vocab-index; include cards, relics, potions, powers, monsters, events. The `oid` convention (vocab index + 1, 0 = PAD) must match `sts2_rl/obs.py:oid()` exactly — reuse it, don't re-implement.
- [ ] **Step 4: Run tests, expect PASS; full suite green.**
- [ ] **Step 5: Smoke the CLI:** `py -m sts2_rl.live.export_contract --out C:\Users\Perry\Desktop\sts2-rl\contract.json` then eyeball segment names/counts against `OBS_SCHEMA.md`.
- [ ] **Step 6: Stage** (`sts2_rl/live/`, `test/test_live_contract.py`; do not stage the generated `contract.json` — add it to `.gitignore` if not covered).

### Task 6: ONNX export + parity gate + stub model

**Files:**
- Create: `sts2_rl/live/export_onnx.py` (CLI: `py -m sts2_rl.live.export_onnx <ckpt.pt> --out model.onnx`, plus `--stub --out stub.onnx` needing no checkpoint)
- Test: `test/test_live_onnx.py`

**Interfaces:**
- Consumes: `sts2_rl/checkpoints.py:load_agent`, `sts2_rl/models.py:EntitySetActorCritic.action_logits`, run layout dims (Task 4).
- Produces: ONNX graph with inputs `f: float32[1, f_dim]`, `i: int64[1, i_dim]`, `mask: bool[1, n_actions]`, output `logits: float32[1, n_actions]` (masked positions = -1e8). Same I/O signature for the stub (uniform 0.0 logits at legal positions). Consumed by C# `OnnxPolicy` (Task 13).

- [ ] **Step 1: Add dependency.** `py -m pip install onnx onnxruntime` (torch is already present). Record versions in the module docstring.
- [ ] **Step 2: Write the failing tests:**

```python
import numpy as np, subprocess, sys

def test_stub_export_and_parity(tmp_path):
    out = tmp_path / "stub.onnx"
    subprocess.run([sys.executable, "-m", "sts2_rl.live.export_onnx", "--stub", "--out", str(out)], check=True)
    import onnxruntime as ort
    from sts2_rl import full_env
    sess = ort.InferenceSession(str(out))
    f_dim, i_dim, n = full_env.run_obs_dims() + (full_env.run_action_count(),)  # adapt to real accessors
    rng = np.random.default_rng(0)
    f = rng.random((1, f_dim), dtype=np.float32)
    i = rng.integers(0, 5, (1, i_dim)).astype(np.int64)
    mask = np.zeros((1, n), dtype=bool); mask[0, [0, 3, 7]] = True
    (logits,) = sess.run(None, {"f": f, "i": i, "mask": mask})
    assert logits.shape == (1, n)
    assert (logits[0, ~mask[0]] < -1e7).all()
    assert np.allclose(logits[0, mask[0]], 0.0)
```

Plus a checkpoint-parity test marked `@pytest.mark.skipif(no checkpoint available)` that loads a real ckpt via `checkpoints.load_agent`, runs 32 random obs/mask pairs through `model.action_logits` (torch) and the exported ONNX, and asserts `max|Δ| < 1e-4`. This test activates for real in Task 15.

- [ ] **Step 3: Run, expect FAIL.**
- [ ] **Step 4: Implement.** Wrapper module pattern:

```python
class _ExportWrapper(torch.nn.Module):
    def __init__(self, model, f_dim, i_dim):
        super().__init__(); self.model = model
    def forward(self, f, i, mask):
        obs = TensorObs(f=f, i=i)          # adapt to models.py's real obs container
        logits = self.model.action_logits(obs, mask)
        return logits
```

Export with `torch.onnx.export(wrapper, (f, i, mask), out, input_names=["f","i","mask"], output_names=["logits"], opset_version=17)`, fixed batch 1. The parity gate runs inside the CLI after export (N=32 random pairs, threshold 1e-4) and deletes the output + exits nonzero on failure. `--stub` builds a tiny torch module with the same I/O (a frozen zero-weight linear producing 0.0 everywhere, then `masked_fill(~mask, -1e8)`) and exports it identically.

- [ ] **Step 5: Run tests, expect PASS; full suite green.**
- [ ] **Step 6: Stage.**

---

## Phase 3 — RunReplays visibility + SpireBot scaffold

### Task 7: RunReplays visibility pass

**Files:**
- Modify (in `c:\Users\Perry\Desktop\RunReplays`): `RunReplays/ReplayDispatcher.cs`, `RunReplays/Commands/ReplayCommand.cs` and any `internal`/`private` command subclasses, `RunReplays/GameStateSnapshot.cs`, `RunReplays/ReplayState.cs`

**Interfaces:**
- Produces (public surface consumed by SpireBot): `ReplayDispatcher.GetDispatchableTypes()`, `ReplayDispatcher.GetAvailableCommands()`, direct construction + execution of `ReplayCommand` subclasses (`PlayCardCommand`, `EndTurnCommand`, `UsePotionCommand`, `MapMoveCommand`, `ChooseEventOptionCommand`, `ClaimRewardCommand`, `TakeCardCommand`, treasure/rest/shop/grid/hand commands), `GameStateSnapshot` capture, `ReplayState` screen fields, and the settle/quiet-frame signal (`DispatchSignalEmitter.InputRequired` or equivalent).

- [ ] **Step 1: Inventory access levels.** `rg "internal|private" RunReplays/Commands RunReplays/ReplayDispatcher.cs RunReplays/GameStateSnapshot.cs RunReplays/ReplayState.cs` — list what SpireBot's surface (above) can't reach.
- [ ] **Step 2: Make the minimal set public.** Visibility keywords only — zero behavior changes. Where a command's `Execute()` depends on replay-engine statics (`ReplayEngine.IsActive` etc.), note it in a code comment only if it blocks external use; behavior fixes are out of scope here and go through Perry.
- [ ] **Step 3: Build + install.** Build the RunReplays csproj (verify the `sts2.dll` HintPath against the actual game install first — it may point at a stale drive). Expected: 0 errors; post-build copies the DLL to the game `mods\` folder.
- [ ] **Step 4: Smoke in game.** Launch StS2, run one bundled sample replay for a few floors — confirms no regression from the visibility pass.
- [ ] **Step 5: Stage** in the RunReplays repo.

### Task 8: SpireBot repo scaffold

**Files:**
- Create repo `c:\Users\Perry\Desktop\SpireBot` (from the empty ModTemplate scaffold: `dotnet new` with the installed template, or copy `ModTemplate-StS2/content/ModTemplate` and rename): `SpireBot.csproj`, `SpireBot.json` (manifest), `SpireBotCode/MainFile.cs`, `SpireBotCode/SpireBotConfig.cs`, `Sts2PathDiscovery.props`, `Directory.Build.props`, `local.props` (gitignored), `.gitignore`

**Interfaces:**
- Produces: a loadable mod. Manifest `SpireBot.json`: `{"id": "SpireBot", "has_dll": true, "has_pck": false, "affects_gameplay": true, "dependencies": [{"id": "BaseLib", "min_version": "3.3.0"}, {"id": "RunReplays"}]}` (dependency syntax: objects with `id`/`min_version`, as RunReplays' shipping manifest and ModTemplate use — an earlier note here claiming "bare strings" was based on a stale repo-root copy; superseded by the 2026-08-05 amendment which drops the RunReplays dependency entirely). `SpireBotConfig` (BaseLib `ModConfig`): `OnnxModelPath`, `ContractPath`, `Temperature` (0 = argmax), `TopK` (default 5), `DumpDecisions` (bool), `DumpDir`.

- [ ] **Step 1: Scaffold** from ModTemplate; net9.0, `Godot.NET.Sdk/4.5.1`, `Krafs.Publicizer` on `sts2`, references: `sts2.dll` + `0Harmony.dll` via `$(Sts2DataDir)` HintPaths, `BaseLib.dll` + `RunReplays.dll` via HintPath to the game's `mods\` folder (`Private=false`), NuGet `Microsoft.ML.OnnxRuntime` (**this one `Private=true`** — its native DLLs must ship in the mod output; verify `onnxruntime.dll` lands in the build output and gets copied to `mods\SpireBot\`).
- [ ] **Step 2: Entry point.** `MainFile.cs`: `[ModInitializer(nameof(Initialize))]`, create `Harmony("SpireBot")`, `PatchAll()`, register `SpireBotConfig` via `ModConfigRegistry.Register`, and log a startup line (`GD.Print("[SpireBot] initialized")`).
- [ ] **Step 3: Build + install.** `dotnet build` → 0 errors, DLL + json copied to `mods\SpireBot\` by the `CopyToModsFolderOnBuild` target (copy the target from RunReplays.csproj if the template's differs).
- [ ] **Step 4: Smoke in game.** Launch StS2; confirm the startup log line and that the config screen shows SpireBot's settings.
- [ ] **Step 5: `git init`, stage everything** (never commit; `.gitignore` covers `local.props`, `bin/`, `obj/`, `.godot/`).

---

## Amendment 2026-08-05 — vendor RunReplays code into SpireBot (Task 8.5)

**Why (Perry decision, 2026-08-05):** RunReplays is boardengineer's mod (MIT), not Perry's — staged changes in the local clone never reach the real mod, and shipping SpireBot must not depend on a privately forked `RunReplays.dll`. Decision: **copy the necessary RunReplays code into SpireBot** (`SpireBot.Replay` namespace) so SpireBot is self-contained; the local RunReplays fork remains a **dev-machine-only** tool for the Phase 5 replay harness. Phase 3 as executed stays valid (Task 7's one-line visibility change becomes a local-fork nicety SpireBot no longer needs; do not revert it, it's harmless and staged).

### Task 8.5: Vendor the RunReplays driving machinery

**Files:**
- Create: `SpireBotCode/Replay/` (vendored, namespace-renamed to `SpireBot.Replay`): all of `RunReplays/Commands/*.cs` (29 command classes + capture helpers), `ReplayDispatcher.cs` (enumeration `GetAvailableCommands`/`GetDispatchableTypes`, execute/retry/watchdog, `DispatchSignalEmitter` settle signal), `ReplayState.cs`, `GameStateSnapshot.cs`, all of `RunReplays/Patches/**/*.cs` (~30 files — the Harmony screen synchronizers that populate `ReplayState`; without them the enumerator is blind). ≈5,400 lines total.
- Create: `SpireBotCode/Replay/VENDORED-FROM.md` (source repo path + `git rev-parse HEAD` + date + list of intentional deltas) and `SpireBotCode/Replay/LICENSE` (RunReplays' MIT notice, boardengineer's copyright — vendoring condition).
- **Do NOT copy:** `ReplayEngine.cs` (playback), `RunReplayMenu*.cs`/`MainMenuButtonInjector.cs` (menus), `RunOverlay.cs`, `RunReplaysConfig.cs`, `PlayerActionBuffer.cs`, autovalidation (`AutoplaySession.cs`), embedded replay resources.
- Modify: `SpireBot.csproj` (remove the `RunReplays` Reference + `$(BaseLibDllPath)`-style plumbing for it), `SpireBot.json` (drop the `{"id": "RunReplays"}` dependency).

**Interfaces:**
- Produces: the same surface Task 7 documented, but as `SpireBot.Replay.*` types compiled into SpireBot.dll. All later plan references to "RunReplays' public surface" (Tasks 9–14) now mean these vendored types.

- [ ] **Step 1: Copy verbatim + rename namespace** `RunReplays` → `SpireBot.Replay` (namespace lines and `using`s only; no logic edits). Write `VENDORED-FROM.md` + `LICENSE`.
- [ ] **Step 2: Compile-driven pruning.** The vendored files reference excluded machinery (`ReplayEngine.IsActive`, menu/engine statics). Resolve each compile error with the *smallest semantic decision*, recorded in `VENDORED-FROM.md`: e.g. a minimal `SpireBot.Replay.ReplayEngineShim` whose flags are pinned to live-bot values (`IsActive = false` — the bot is never inside a recorded playback), or deletion of a playback-only branch. Every shimmed/pinned flag gets a one-line justification.
- [ ] **Step 3: Harmony id.** The vendored patches apply under SpireBot's own `Harmony("SpireBot")` via the existing `PatchAll()`. Note: if Workshop RunReplays is also installed, the same game methods get patched by both mods. The patches are record-into-own-state synchronizers (separate static types, separate state), so double-patching is expected benign — but this is an explicit smoke-test item, not an assumption.
- [ ] **Step 4: Build + install.** `dotnet build` → 0 errors; `mods\SpireBot\` complete. Also delete the duplicate flat `mods\RunReplays.dll`+`RunReplays.json` pair (keep the `mods\RunReplays\` subfolder copy for the dev harness — or none at runtime if Perry unsubscribes/keeps Workshop only; either way exactly one RunReplays must remain).
- [ ] **Step 5: Smoke in game (Perry, Steam launch).** With Workshop RunReplays present: no startup errors from either mod, SpireBot config screen still shows, and a RunReplays replay still plays (double-patch benignity check).
- [ ] **Step 6: Stage.**

**Downstream deltas (apply when executing Phases 4–5, no task rewrites needed):**
- Tasks 9–14: every `ReplayDispatcher`/`ReplayCommand`/`ReplayState`/`GameStateSnapshot`/settle-signal reference resolves to `SpireBot.Replay.*`; SpireBot no longer references or depends on the RunReplays assembly at build or load time.
- Task 11 Step 1 (menu injection): the pattern is copied from `MainMenuButtonInjector.cs` as before, but implemented fresh in `MenuInjection.cs` — the injector itself was deliberately not vendored.
- Task 16 Step 2 (passive dump while replaying 89U): runs on the **local RunReplays fork build** (playback engine) — dev-time only. SpireBot's passive mode observes game state on its own settle signal; it does not link against RunReplays.
- Phase 5 grind fixes that touch vendored logic must be applied to `SpireBotCode/Replay/` AND noted in `VENDORED-FROM.md` (and optionally mirrored to the fork).

---

## Phase 4 — C# pipeline (stub-first)

### Task 9: Contract loader

**Files:**
- Create: `SpireBotCode/Contract.cs`
- Test: no in-game test — validated by a `--dump-contract-roundtrip` debug console command later; correctness is pinned by Task 16's cross-language harness. Unit-style check: a temporary `ContractSelfTest.Run()` called from `Initialize()` in debug builds that loads the real contract.json and asserts invariants.

**Interfaces:**
- Consumes: `contract.json` (Task 5's shape).
- Produces:

```csharp
public sealed class Contract {
    public static Contract Load(string path);       // throws ContractException with a clear message on any mismatch
    public int CombatObsSchema; public int RunObsSchema; public int FDim; public int IDim; public int NActions;
    public LayoutSlice F(string name);               // {int Offset; int Width}; throws on unknown name
    public LayoutSlice I(string name);
    public int VocabId(string kind, string gameModelId);   // 0 (PAD) when unmapped — callers treat 0 as "unknown content"
    public ActionLayout Actions;                     // mirrors contract.json "actions" block
}
```

- [ ] **Step 1: Implement** with `System.Text.Json`; store layouts in `Dictionary<string, LayoutSlice>`; `ContractSelfTest.Run()` asserts: offsets contiguous, `FDim`/`IDim` equal the sums, `Actions.NActions == 243`, a known vocab probe (`VocabId("cards", <a mapped Ironclad strike id from game_id_map>) != 0`).
- [ ] **Step 2: Build; run the game; self-test passes in the log.**
- [ ] **Step 3: Stage.**

### Task 10: ActionMap (mask + action-id ↔ command)

**Files:**
- Create: `SpireBotCode/ActionMap.cs`, `SpireBotCode/DecisionContext.cs`

**Interfaces:**
- Consumes: `Contract.Actions`; RunReplays `ReplayDispatcher.GetAvailableCommands()` + `GetDispatchableTypes()` + `ReplayState` (Task 7's public surface).
- Produces:

```csharp
public sealed class DecisionContext {           // one decision point, captured once
    public DecisionKind Kind;                   // Combat, Map, Event, Shop, Rest, RewardScreen, SelectCards, SelectOption, Unsupported
    public List<ReplayCommand> Available;       // from GetAvailableCommands()
    public GameStateSnapshot Snapshot;          // RunReplays' snapshot, captured at the same instant
}
public sealed class ActionMap {
    public static ActionMap Build(Contract c, DecisionContext ctx);
    public bool[] Mask;                                 // length NActions
    public ReplayCommand CommandFor(int actionId);      // null if masked off
    public string LabelFor(int actionId);               // human label for the overlay ("Play Bash → Cultist")
}
```

- [ ] **Step 1: Implement the kind classifier** from `GetDispatchableTypes()` + `ReplayState` screen fields (mirror `ReplayDispatcher`'s own logic; e.g. `PlayCardCommand`/`EndTurnCommand` dispatchable → Combat; `MapMoveCommand` → Map; grid/hand-select screens → SelectCards). Anything unmatched → `Unsupported`.
- [ ] **Step 2: Implement the mapping per kind**, mirroring `run_env`'s block semantics exactly (read `run_env.py:_translate` + `driver.py:own_actions` and keep a comment cross-referencing each block):
  - Combat: action `0` → `EndTurnCommand`; `play_base + h*max_enemies + e` → `PlayCardCommand` for hand position `h` targeting the `e`-th living enemy (hand order and enemy order MUST match the obs rows the ObsBuilder emits — same source arrays, single capture point in `DecisionContext`); `potion_base + p*max_enemies + e` → `UsePotionCommand`.
  - Choice block: i-th option slot → i-th entry of the screen's canonical list (map nodes by column order, event options by index, shop entries in `all_entries` order, rest options, reward buttons). The canonical order must equal the obs candidate-row order.
  - Select block: per-candidate rows in the same sorted order the obs uses (`_sorted_candidate_order` semantics — the contract can't export a comparator, so port the sort key and pin it in Task 16's harness).
  - Belt-potion block: slot p → `UsePotionCommand(p)` when legal outside combat.
- [ ] **Step 3: Mask = "a command exists for this id".** No sim logic — pure game truth from `Available`.
- [ ] **Step 4: Build; stage.** (Correctness lands with Task 11's stub-bot smoke and Task 16's harness.)

### Task 11: BotController + first-legal-action stub bot (end-to-end loop, no model)

**Files:**
- Create: `SpireBotCode/BotController.cs`, `SpireBotCode/ActionExecutor.cs`, `SpireBotCode/MenuInjection.cs`, `SpireBotCode/Policies/IPolicy.cs`, `SpireBotCode/Policies/FirstLegalPolicy.cs`

**Interfaces:**
- Consumes: `ActionMap`, `DecisionContext`, RunReplays dispatch/settle machinery, `NGame.Instance.StartNewSingleplayerRun(...)` (read `RunReplayMenu.StartReplay` for the exact invocation), Ironclad `CharacterModel` lookup.
- Produces:

```csharp
public interface IPolicy { PolicyResult Choose(DecisionContext ctx, ActionMap map); }
public sealed class PolicyResult { public int ActionId; public (string label, float prob)[] TopK; }
public sealed class BotController {   // singleton node
    public void StartBotRun(string seed = null);   // Ironclad, asc 0
    public void Stop();
    public event Action<DecisionContext, PolicyResult> DecisionMade;  // overlay + dump hook
}
```

- [ ] **Step 1: Menu entry.** `MenuInjection.cs`: Harmony postfix on the same main-menu `_Ready` RunReplays patches (copy `MainMenuButtonInjector`'s pattern) adding a "Bot Run" button → `BotController.StartBotRun()`.
- [ ] **Step 2: Decision loop.** Subscribe to RunReplays' idle/settle signals (dispatchable-set change + quiet frames — reuse `ReplayDispatcher`'s mechanism rather than a new poll). On idle: build `DecisionContext` → `ActionMap` → `policy.Choose` → `ActionExecutor.Execute(command)` (dispatch through RunReplays' execute/retry path, inheriting the watchdog) → wait for settle. Guard: if the same decision context recurs >3 times without state change, fire the fallback (log + `EndTurnCommand`/proceed/first-legal) and continue.
- [ ] **Step 3: `FirstLegalPolicy`** — lowest legal actionId, TopK = that action at 1.0.
- [ ] **Step 4: In-game acceptance.** Start a Bot Run; the stub must complete a full run (win or die) hands-off, including combats, map, events, shop, rest, rewards, treasure. Fix classifier/mapping holes it exposes (crystal-sphere → scripted fallback: random valid click via `CrystalSphereClickCommand`).
- [ ] **Step 5: Stage.**

### Task 12: ObsBuilder — combat block + session state

**Files:**
- Create: `SpireBotCode/Obs/ObsBuilder.cs`, `SpireBotCode/Obs/CombatObsWriter.cs`, `SpireBotCode/Obs/SessionState.cs`

**Interfaces:**
- Consumes: `Contract` layouts, Task 2's audit table (each field's C# source is specified there — the audit doc is the implementation spec for this task), game state via the same capture as `GameStateSnapshot`, Task 1's damage-preview call sequence (if KEEP).
- Produces:

```csharp
public sealed class Obs { public float[] F; public long[] I; }   // long: ONNX int64 input
public sealed class ObsBuilder {
    public ObsBuilder(Contract c, SessionState session);
    public Obs Build(DecisionContext ctx);        // full run-schema obs; combat block zeroed outside combat
}
public sealed class SessionState {                 // per-run accumulator, reset by BotController.StartBotRun
    public void OnTurnStart(...);                  // records displayed intents per enemy net_id (3-deep history)
}
```

- [ ] **Step 1: Implement segment writers** for the combat block: vitals, energy, hand rows (positional, aligned with ActionMap's hand order), enemy rows + powers + intent history (from `SessionState`), player powers, relics, potions, sorted-piles block (sort must replicate the sim's order-independent canonical sort — read `build_combat_obs`'s sort key and port it exactly), damage matrix per Task 1's verdict. Every writer targets `contract.F(name)`/`contract.I(name)` slices — no numeric offsets in code. Unknown content (VocabId==0) → write PAD and record the id in the decision log.
- [ ] **Step 2: Wire `SessionState`** accumulation into BotController turn hooks.
- [ ] **Step 3: Smoke:** stub-bot run with a debug assert that every write stayed in its slice and `F`/`I` lengths match `FDim`/`IDim`.
- [ ] **Step 4: Stage.**

### Task 13: ObsBuilder — run/screen contexts + decision dump

**Files:**
- Create: `SpireBotCode/Obs/RunObsWriter.cs`, `SpireBotCode/DecisionDumper.cs`

**Interfaces:**
- Consumes: audit rows for the run schema; screen contexts already captured for `ActionMap` (map nodes, rewards, shop, event options, select candidates) — same arrays, same order.
- Produces: full run-schema obs; `DecisionDumper.Write(ctx, obs, mask, result)` → one JSON line per decision in `{DumpDir}/{seed}/decisions.jsonl`: `{"floor":n,"kind":"Combat","f":[...],"i":[...],"mask":[...],"action":id,"topk":[...],"labels":{...}}` (gated on `SpireBotConfig.DumpDecisions`).

- [ ] **Step 1: Implement run-block writers** (map grid + boss identity, gold/HP/act/floor, deck summary, screen candidate rows — exactly the audit's rows).
- [ ] **Step 2: Implement `DecisionDumper`** (schema above; flush per line — crashes must not lose the tail).
- [ ] **Step 3: Smoke:** stub-bot run with dump on; spot-check a combat line and a map line for plausible values (nonzero hand ids in combat, mask count == available count).
- [ ] **Step 4: Stage.**

### Task 14: OnnxPolicy + ThinkingOverlay

**Files:**
- Create: `SpireBotCode/Policies/OnnxPolicy.cs`, `SpireBotCode/Overlay/ThinkingOverlay.cs`

**Interfaces:**
- Consumes: `Obs` (Task 12/13), stub ONNX from Task 6 (`py -m sts2_rl.live.export_onnx --stub --out stub.onnx`), `SpireBotConfig` paths, `BotController.DecisionMade`.
- Produces: `OnnxPolicy : IPolicy` — ONNX Runtime `InferenceSession` (CPU), inputs `f`/`i`/`mask`, softmax over masked logits, argmax if `Temperature == 0` else temperature sampling; TopK labels via `ActionMap.LabelFor`. `ThinkingOverlay`: Godot `CanvasLayer` showing decision kind, chosen label, TopK bars; toggleable in config.

- [ ] **Step 1: Implement `OnnxPolicy`** (validate session input shapes against `Contract` at load; refuse with a clear log line on mismatch).
- [ ] **Step 2: Implement `ThinkingOverlay`** subscribed to `DecisionMade`.
- [ ] **Step 3: In-game acceptance:** full hands-off run on the **stub ONNX** (uniform-random legal actions) with overlay live. This is the whole pipeline minus a trained model.
- [ ] **Step 4: Stage.**

---

## Phase 5 — Cross-language validation harness

### Task 15: Sim-side obs dump for converged replays

**Files:**
- Create: `sts2_rl/live/sim_obs_dump.py` (CLI: `py -m sts2_rl.live.sim_obs_dump --seed <seed> --out sim_dump.jsonl`)
- Test: `test/test_live_sim_dump.py` (smoke: runs on 89U fixture, emits >0 lines, each line has `f`/`i` of contract dims)

**Interfaces:**
- Consumes: the conformance replay machinery (`sts2_rl/conformance/runner.py`, recordings for 89U21BV1TZ and 933T39V18D) and the new-schema obs builders.
- Produces: JSONL, one line per decision point: `{"floor":n,"kind":...,"decision_index":k,"f":[...],"i":[...]}` — same keys as SpireBot's `DecisionDumper` so Task 16 can join on `(floor, kind, decision_index)`.

- [ ] **Step 1: Write the smoke test; run, expect FAIL.**
- [ ] **Step 2: Implement** by driving the recorded run through the sim (full combat replay — the same paths the convergence gates use, not the force-win stub) and calling the obs builders at every decision the run env would see.
- [ ] **Step 3: Tests pass; full suite green; stage.**

### Task 16: Obs diff tool + parity grind

**Files:**
- Create: `sts2_rl/live/compare_obs.py` (CLI: `py -m sts2_rl.live.compare_obs sim_dump.jsonl game_dump.jsonl --contract contract.json`)
- Test: `test/test_live_compare.py` (unit: two synthetic dumps, one seeded mismatch → report names the segment/field via layout lookup)

**Interfaces:**
- Consumes: Task 13's game dump + Task 15's sim dump + contract.
- Produces: per-decision, per-segment diff report (segment name, offset, sim vs game value) and exit code 0 on full parity. **Acceptance gate: byte-parity (`f` within 1e-6, `i` exact) on both converged seeds across all decisions.**

- [ ] **Step 1: Write the unit test; FAIL; implement; PASS.**
- [ ] **Step 2: Produce the game dump:** replay 89U in-game via RunReplays with SpireBot in **passive dump mode** (dump at each decision without acting — add a `PassiveDump` config flag: BotController observes RunReplays' own dispatch instead of driving).
- [ ] **Step 3: Grind to parity.** Run the diff; fix C# writers (or, where the C# side reveals a sim-side bug in the new schema, fix the sim and re-run the suite) until both seeds pass. Log each fix in the task notes — this list is the review artifact.
- [ ] **Step 4: Full suite green; stage both repos.**

---

## Phase 6 — Training + showcase

### Task 17: Train the first run-env checkpoint

**Files:**
- No source changes expected. Artifacts: `runs/<name>.pt` in sts2-rl (checkpoints are gitignored — verify; do not stage weights).

**Interfaces:**
- Consumes: `train_torch.py` (entset arch, run/curriculum env — check `py train_torch.py --help` and `RL.md` for current flags; use `--device cuda`, the tied-head defaults, and `--shared-encoder` per the phase-2 A/B win).
- Produces: an arch-stamped checkpoint with `env_kind=run`, `head_version=4`, new obs schema stamps — accepted by `checkpoints.load_agent`.

- [ ] **Step 1: Launch training** on the RTX 3070 (long-running: run in background, checkpoint periodically). If resuming across env changes ever comes up: `--critic-warmup` (known stale-critic gotcha).
- [ ] **Step 2: Evaluate:** `py eval.py runs/<name>.pt --env run --episodes 50` vs `--baselines`. **Bar: beats masked-random on mean floor reached.** This is a showcase checkpoint, not a strength milestone.
- [ ] **Step 3: Record** the eval numbers in the plan-execution notes.

### Task 18: Export, wire in, showcase run

**Files:**
- Artifacts: `model.onnx` + `contract.json` in a mod-config-pointed directory.

**Interfaces:**
- Consumes: Task 6's exporter (parity gate now runs against the real checkpoint — the skipif test activates), Task 17's checkpoint, the full SpireBot pipeline.

- [ ] **Step 1: Export:** `py -m sts2_rl.live.export_contract --out <dir>\contract.json` and `py -m sts2_rl.live.export_onnx runs\<name>.pt --out <dir>\model.onnx` (parity gate must pass).
- [ ] **Step 2: Point `SpireBotConfig`** at both; start a Bot Run; watch a full hands-off run with the overlay.
- [ ] **Step 3: Acceptance:** three consecutive hands-off runs with zero unhandled exceptions in the log (fallback activations are fine — count and note them). Overlay shows sane top-k throughout.
- [ ] **Step 4: Stage** any final fixes in all repos; hand the run report to Perry.

---

## Self-review notes (done at plan-writing time)

- Spec coverage: schema audit/bump (Tasks 2–4 ↔ spec §A), contract (5 ↔ §B), ONNX (6, 18 ↔ §C), mod components (8–14 ↔ §D: ObsBuilder=12/13, MaskBuilder=10, OnnxPolicy=14, BotController=11, ActionExecutor=11, ThinkingOverlay=14, fallbacks=11/12, dump=13), RunReplays tweaks (7 ↔ §E), training (17 ↔ §F), validation harness (15/16 ↔ spec's linchpin section), error handling folded into 9/11/14, damage-preview research (1 ↔ spec risk 4).
- Known unknowns are contained: exact sts2-rl accessor names (`run_obs_layout`, `run_obs_dims`, vocab API) are marked "adapt to real API" with the file to read; audit doc (Task 2) is the normative field spec for Tasks 12–13, so no obs field is specified twice.
- Type consistency: `Contract`/`ActionMap`/`DecisionContext`/`IPolicy`/`PolicyResult`/`Obs`/`SessionState` names match across Tasks 9–14; dump JSONL keys match between Tasks 13 and 15.
