# SpireBot — live model-driven bot mod for Slay the Spire 2

**Date:** 2026-08-04
**Status:** approved design, pre-implementation
**Repos involved:** `sts2-rl` (obs schema, training, contract/export tooling), new mod repo `SpireBot` (C#/Godot), small visibility tweaks in `RunReplays`.

## Purpose

A showcase mod: watch an sts2-rl-trained agent play full Ironclad runs (ascension 0) live in the real game. The **game is the sole source of truth** — every decision is made from a fresh read of actual game state. There is no shadow sim and no divergence concept: the model simply observes whatever the game did and reacts.

No model is currently trained; training a first checkpoint is part of this project. That makes the obs-schema change below cheap — nothing is trained on the old schema that we'd need to preserve.

## Core architectural decisions (settled with Perry)

1. **Full-run scope** — the bot plays every decision point of a run (combat, map, events, shop, rest, rewards, selection screens) using the run-env action space (`N_ACTIONS = 243`).
2. **Game-observable obs schema** — the observation contract is revised so that every field is buildable by the C# mod from live game state. The sim's obs builders are updated to the same new schema and training runs on it, so training-time and game-time observations share one contract by construction.
3. **Obs built in C#, inference in-process via ONNX** — the mod builds the `f`/`i` arrays itself and runs the exported model with ONNX Runtime (CPU EP, batch of 1). No Python process at game time.
4. **New mod depending on RunReplays + BaseLib** — SpireBot is its own mod (manifest `dependencies: ["BaseLib", "RunReplays"]`), reusing RunReplays' command classes, dispatch/settle machinery, and legality enumerator rather than duplicating them.
5. **Showcase UX = thinking overlay** — an in-game overlay showing the decision kind, chosen action, and top-k action probabilities. Run start via a minimal main-menu "Bot Run" entry (mechanically necessary; RunReplays' menu-injection pattern).
6. **Training is part of the plan** — an entset run-env Ironclad checkpoint trained with the existing `train_torch.py` on CUDA; modest strength target (coherent play, not a strong agent). Pipeline development does not block on it (stub policies below).

## Components

### A. sts2-rl: game-observable obs schema (new combat + run schema versions)

Audit every field of the current schemas (combat v6: 1677 f / 606 i; run v9: 4710 f / 1464 i) and produce a revised schema in which **each field is annotated with the concrete game API that produces it**. Field classes:

- **Directly readable** — HP/max HP, energy, gold, floor/act, piles (card ids, upgrades, costs), player/enemy powers with amounts, relics with counters, potions/slots, displayed enemy intents, screen contexts (map nodes, reward lists, shop inventory + prices, event options, selection-screen candidates). Kept as-is.
- **Game-computable** — the per-(hand card × enemy) damage-preview matrix. The game computes per-target damage previews for its own card UI; a research task determines whether the mod can invoke that calculation per (card, enemy) pair. If yes, the matrix is kept (sim previews are already converged against the game, so trained values match game-time values). If the game API cannot be called per-target, the field is **dropped** from the schema.
- **Session-accumulated** — per-enemy displayed-intent history (3-deep): the mod accumulates it across turns exactly as the sim does. Any other field requiring cross-decision memory gets the same treatment or is dropped.
- **Not game-observable and not accumulable** — dropped. Every drop is an explicit, recorded decision in the audit.

Deliverables: updated `OBS_SCHEMA.md`, bumped `OBS_SCHEMA_VERSION` / `RUN_OBS_SCHEMA_VERSION`, updated builders in `sts2_rl/full_env.py` (+ run obs builder), updated tests. **The schema freezes when training starts.**

Action masks are *not* part of this contract at game time: the mod derives the mask from RunReplays' `GetAvailableCommands()` (game-truth legality) mapped onto the action layout. This replaces the sim's hook-derived masks at inference and eliminates any reject/re-sample loop. The sim keeps its own mask logic for training.

### B. sts2-rl: contract export

`py -m sts2_rl.live.export_contract` emits `contract.json`:

- combat/run schema versions and `f`/`i` segment layouts (names, offsets, widths — from `ObsLayout`),
- vocab maps: game model id string → vocab index, for every vocab kind (derived from `vocab.json` plus the conformance id mapping in `sts2_rl/conformance/ids.py`/`idmap.py`),
- action-space layout (block bases/sizes mirroring `run_env`'s blocks and `decode_combat_action` semantics).

The C# mod loads `contract.json` at startup and hard-refuses on version mismatch. Python remains the single source of truth for offsets and vocab; C# never hand-copies a number.

### C. sts2-rl: ONNX export

`py -m sts2_rl.live.export_onnx runs/x.pt` exports the entset model's `action_logits` path (embeddings, linear+tanh row projections, masked sum-pool, pointer heads, masked_fill — all ONNX-representable). Includes a numerical parity gate: N random obs/mask pairs through torch and onnxruntime, max-abs-diff threshold, export refuses to emit on failure. Also exports a **masked-random stub ONNX** (uniform logits) so the mod pipeline runs before any real checkpoint exists.

Escape hatch (documented, not built unless needed): if ONNX export fights the arch, fall back to a thin mod-spawned Python child doing checkpoint-load + forward pass over stdio.

### D. SpireBot C# mod (new repo from the empty ModTemplate scaffold)

Packaging: net9.0 / Godot 4.5.1 class library, `[ModInitializer]` entry + Harmony `PatchAll()`, publicized `sts2.dll`, HintPath references to `BaseLib.dll` and `RunReplays.dll` (runtime-provided, `Private=false`), manifest `dependencies: ["BaseLib", "RunReplays"]`, `CopyToModsFolderOnBuild` install target, BaseLib `ModConfig` for settings (ONNX model path, contract path, sampling temperature, overlay toggles).

Components:

- **`ObsBuilder`** — builds the `f`/`i` arrays per `contract.json` from live game state. The largest new C# surface; every segment writer maps 1:1 to a schema annotation from the audit.
- **`MaskBuilder`** — `ReplayDispatcher.GetAvailableCommands()` → boolean mask over the action layout.
- **`OnnxPolicy`** — ONNX Runtime (Microsoft.ML.OnnxRuntime NuGet) session; argmax or temperature sampling over masked logits; top-k probabilities surfaced for the overlay.
- **`BotController`** — run lifecycle: "Bot Run" main-menu entry starts a fresh Ironclad asc-0 run (random or configured seed); decision loop driven by RunReplays' idle detection (dispatchable-type change signal + quiet-frame settling); per-run session state (intent history, run stats).
- **`ActionExecutor`** — action id → semantic action → matching RunReplays command object, executed through the existing dispatcher machinery (inheriting its retry and watchdog behavior).
- **`ThinkingOverlay`** — Godot overlay: decision kind, chosen action label, top-k bars. Built like RunReplays' overlay UI.
- **Scripted fallbacks** — for screens outside the action space (crystal-sphere minigame) and for any decision where the obs cannot be built (e.g. unknown modded content): take a safe default (skip / first legal / end turn), log the reason, continue the run.
- **Debug dump flag** — writes `(snapshot, obs, mask, chosen action, top-k)` per decision to disk; feeds the validation harness and offline debugging.

### E. RunReplays upstream tweaks

Small visibility changes only (internal → public on the command classes / dispatcher entry points / `GetAvailableCommands` as needed). No behavior changes; Perry owns the repo so these land upstream, not in a fork.

### F. Training

Train an entset run-env (or curriculum) Ironclad policy on the new schema with `train_torch.py` on the RTX 3070. Success bar: plays coherently through act 1+ more often than masked-random — a real checkpoint to showcase, not a strength milestone. Then `export_onnx` + drop into the mod config.

## Decision flow (per decision point)

1. RunReplays idle detection fires (dispatchable set changed, animations settled).
2. `ObsBuilder` reads game state → `f`/`i` arrays; `MaskBuilder` → mask.
3. `OnnxPolicy` → action id + top-k probs.
4. Overlay updates; `ActionExecutor` maps the id to a RunReplays command and dispatches.
5. Wait for settle; repeat. On failure at any step: scripted fallback + log; the run keeps going.

## Validation harness (the linchpin)

The converged conformance replays (89U21BV1TZ, 933T39V18D) double as an obs cross-check:

1. Replay the seed in-game via RunReplays with SpireBot's dump flag on (passive: dump obs at each decision without acting).
2. Replay the same seed in the sim, building new-schema obs at the same decision points.
3. Diff the arrays. Byte-parity proves the C# `ObsBuilder` implements the contract.

This reuses the finished Ironclad fidelity work as the ground truth for the new component.

## Error handling

- Contract/model version mismatch at startup → refuse to start a bot run, clear overlay/log message.
- Obs build failure at a decision → scripted fallback for that decision, log the field/content id, continue.
- Chosen action fails to execute (game rejected it despite the mask) → bounded retries via the dispatcher, then fallback action; log.
- ONNX session error → pause the bot, surface in overlay; run can be resumed or abandoned manually.

## Testing

- **Python:** schema-audit tests (every field annotated, builders match layout widths), contract-export golden test, ONNX parity gate test, existing suite stays green through the schema bump (legacy tests updated with the schema, per the "original means game source" rule — here the authority is the new contract).
- **C#:** stub end-to-end first — a first-legal-action policy driving a full run in-game proves snapshotting, dispatch, settling, and fallbacks before any model exists; then the masked-random ONNX stub proves the ONNX path.
- **Cross-language:** the replay validation harness above is the acceptance gate for `ObsBuilder`.

## Risks

1. **Schema audit surprises** — some fields may lack a clean game-side source; each becomes an explicit keep/drop decision, all settled before the schema freezes for training.
2. **ObsBuilder correctness** — mitigated by the replay cross-validation harness; an imperfect obs degrades play quality, it never crashes the run (fallbacks).
3. **ONNX export wrinkles** (dynamic shapes, masked ops) — mitigated by the parity gate; Python-child fallback documented.
4. **Damage-matrix research task fails** (no per-target game API) → the field is dropped; the model trains without it. Decision is made early, before training.
5. **Training yields a weak policy** — acceptable by design; the showcase bar is "plays a coherent run," and the pipeline accepts any future stronger checkpoint unchanged.

## Out of scope

- Characters other than Ironclad; ascensions above 0.
- Divergence detection / conformance logging from the live bot.
- Real-game trajectory collection for training.
- Multiplayer, and any non-Windows packaging.
