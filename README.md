# sts2-rl

A headless Python reimplementation of the **Slay the Spire 2** game engine, plus a
reinforcement-learning stack that trains an Ironclad agent on it with PPO.

The simulator is ported from the decompiled game source and validated against
real recorded runs: seeded conformance replays are driven through the sim and
every RNG draw, card pile, HP value, and reward screen is compared against what
the actual game produced. Two full Ironclad seeds (`89U...`, `933T...`) replay
to full parity.

## Layout

| Path | What it is |
|---|---|
| `sts2_rl/` | The engine: combat, run/map layer, cards, relics, potions, powers, monsters, events, RNG streams |
| `sts2_rl/conformance/` | Replay harness that drives recorded real-game runs through the sim and diffs every step |
| `sts2_rl/live/` | Export/compare tooling for running the trained policy inside the real game (see SpireBot below) |
| `sts2_rl/models.py`, `train_torch.py` | Entity-based policy network + raw-PyTorch PPO trainer |
| `eval.py` | Evaluation harness with behavior metrics and gate checks |
| `test/` | ~5000-test pytest suite pinning engine behavior against the game source |
| `audit/tools/`, `tools/` | Source-audit probe harness and misc tooling used to find fidelity gaps |
| `scripts/` | Curriculum training scripts (`train_curriculum_v*.ps1`) and harvest tooling |
| `docs/` | Engine/env/network reference docs (`OBS_SCHEMA.md`, `RL_ARCHITECTURE.md`, `MODULES.md`) |

## Setup

Windows / PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install PyTorch first — CPU or CUDA, your choice (see requirements.txt header)
pip install torch --index-url https://download.pytorch.org/whl/cu130   # GPU (RTX)
# or: pip install torch                                                # CPU

pip install -r requirements.txt
```

Sanity check:

```powershell
python -m pytest test -x -q
```

## Training and evaluation

```powershell
# Current curriculum run (stages, gates, and logging handled by the script)
.\scripts\train_curriculum_v22.ps1   # run from repo root

# Or drive the trainer directly
python train_torch.py --arch entity --device cuda ...

# Evaluate a checkpoint
python eval.py --ckpt runs\<run>\ckpt.pt
```

## SpireBot — running the policy in the real game

[SpireBot](https://github.com/TsaiPerry/SpireBot) is a C# mod that loads an exported ONNX policy and
plays actual Slay the Spire 2 runs with it. The obs/action contract is shared
with this repo (`contract.json`); `sts2_rl/live/export_onnx.py` produces the
model, and `sts2_rl/live/compare_obs.py` verifies sim-vs-game observation
parity.

Setup:

1. **Install BaseLib** (mod-loader dependency, `min_version 3.3.0`) into the
   game's mods folder or via Steam Workshop.
2. **Point the build at your game install**: in the SpireBot repo, copy
   `local.props.template` to `local.props` and set `Sts2Path` to your
   `steamapps\common\Slay the Spire 2` directory. (If your install is in a
   standard Steam location you can skip this — `Sts2PathDiscovery.props`
   auto-detects it.)
3. **Build**: `dotnet build` in the SpireBot repo. The build copies the mod
   into the game's mods folder.
4. **Export a policy** from a training checkpoint:
   `python -m sts2_rl.live.export_onnx --ckpt <ckpt> --out model.onnx`
5. **Set `OnnxModelPath`** in SpireBot's config to the exported model — this
   is a manual step; the mod does not discover the model on its own.
6. Launch the game with mods enabled and start (or attach to) a run.

## Related repos

- `../SpireBot` — in-game bot mod (above)
- `../RunReplays` — run-capture/replay mod used to record the conformance seeds
- `../BaseLib-StS2`, `../ModTemplate-StS2` — modding infrastructure
