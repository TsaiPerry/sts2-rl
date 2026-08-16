# Aux HP-loss head + GAE λ 0.98 — design (folds into v10)

**Problem.** Rest-vs-upgrade (and potion timing) require anticipating the upcoming map. Credit from actual returns decays as (γλ)^k ≈ 0.949^k at the current γ=0.999/λ=0.95 — a half-life of ~14 decisions (< half a floor) — so long-horizon judgment is delegated almost entirely to the critic's bootstrap. The obs has carried the whole-map grid + boss identity since v4; nothing forces the encoder to *read* it.

**Decisions (Perry, 2026-08-13):** both levers; single aux target "HP lost over the next 3 floors"; folded into the v10 escape-and-settle run (s10/s11), not a separate run.

## 1. GAE λ 0.95 → 0.98

Pure CLI change (`--gae-lambda`, used only at train_torch.py:801, stamped nowhere). Both v10 stages pass 0.98. Credit half-life ~14 → ~50 decisions (~2 floors). Not raised further: λ→1 trades bias for variance, and the aux head is the intended carrier of the longer horizon.

## 2. Auxiliary head

- **Module**: `aux_hp3_head` = small MLP (encoder_out → 64 → 1) on `EntitySetActorCritic`, consuming the **critic/shared encoder output** (same features `self.critic` eats). Registered **last** in `__init__` so every pre-existing parameter keeps its position (Adam state is positional — the entity-reorder gotcha).
- **Prediction ride-along**: `get_action_and_value(..., with_aux=True)` returns a 5th tensor computed from the *same* encoder pass the PPO update already does — zero extra encoder cost. Default `with_aux=False` keeps the 4-tuple contract for all existing call sites. `action_logits`/`get_value` untouched → ONNX export and SpireBot parity unaffected.
- **Target** (per step t, env e, computed post-rollout from the stored obs buffers only — no env or vec_env changes): cumulative `run.hp_ratio` **decreases** (sum of per-step drops, so heals don't cancel damage) from t until the first in-window step where floor ≥ floor(t)+3 **or the episode ends** (death or win inside the horizon is a real, valid label — and exactly the danger signal). Floors reconstruct as `round(f * 50)` (`run.floor` = total_floor/50 clipped, run_env.py:1322).
- **Mask**: label invalid only when the 512-step rollout window ends before either stopping point (expected coverage ~80%). `done_buf[t]==1` means obs t is a *fresh episode's first obs* (auto-reset lands same-slot), so accumulation and the floor comparison must never cross a done flag — the next episode's floors/HP would otherwise leak into the label.
- **Loss**: masked MSE, `--aux-hp-coef` (default **0.0 = fully off, bit-identical**; v10 runs 0.25 — targets are ~0.1/floor of hp_ratio, so the term lands in value-loss range). Active during critic warmup too (both are supervised). `--aux-hp-coef > 0` with `--env combat` is a `SystemExit` (the `run.floor`/`run.hp_ratio` slices are run-layout).

## 3. Checkpoint compatibility (chosen: lenient allowlisted load)

- `head_version` stays 4 — it versions the *action-head* layout, which is unchanged; a version bump would needlessly refuse every old checkpoint everywhere.
- `checkpoints.load_agent`: when the checkpoint's model dict is missing keys and **all** of them start with `aux_`, build `full = dict(model.state_dict()); full.update(ckpt["model"])` and strict-load that (the warm-start overlay pattern — a complete dict, so `strict=True` semantics are preserved). Any other missing key still fails exactly as today. Old→new loads work for train resume, eval, and export alike (all go through `load_agent`).
- **Optimizer restore on `--resume`**: the saved Adam `param_groups[0]["params"]` has P entries; the live model has P+n (aux registered last). Patch the saved indices list with the trailing new ids before `optimizer.load_state_dict` — old params keep their moments, aux params lazily initialize on first step. Only permitted when the shortfall equals the aux param count; anything else fails as today.

## 4. v10 integration & gates

- Both stages (s10 escape, s11 settle) add `--gae-lambda 0.98 --aux-hp-coef 0.25`. Seed stays `runs/sts2_run_torch_v9_s9.pt` (no aux keys → lenient path + optimizer patch fire on the s10 resume).
- v10-run-log gains: s10 sanity gate "aux_loss falls over the stage" (supervised — flat aux loss = broken wiring, readable from training logs before s11 spends its 3M); knob-table rows for λ and the aux head.
- Attribution caveat accepted (4 changes in one run): aux has its own supervised metric; λ has no rest/potion fingerprint; the reward knobs are gated by `Test-RestUpgradeGate` mid-script.

## Rejected alternatives

- `head_version` 5 + migration: wrong semantics, heavier, refuses old ckpts.
- `--warm-start` into s10: reinitializes trunk first-layers and drops s9's optimizer — wrong tool for adding two small layers.
- Extra aux targets (death-within-3, act-boss-beaten, floors-survived): YAGNI for now; the head/loss plumbing generalizes if HP-loss alone proves out.
- Storing per-step info dicts in the rollout: unnecessary — both needed scalars already live in the stored obs.
