# Prompt: Embedding/entity model to replace the flat one-hot MLP

Copy everything below into a fresh session.

**When to run this:** after env stepping is parallelized (or profiled to be
acceptable) and you're ready for a deliberate, one-time full retrain. Measured
baseline (2026-07-16, CPU): one PPO iteration = ~51 s at defaults, split 79%
env stepping / 14% update / 7% rollout inference; obs 29,190 floats; model
15.4M params (two 256×256 trunks, first layers dominated by the one-hot input);
rollout obs buffer ≈ 460 MB fp32 at n_steps=512 × n_envs=8.

---

In `c:\Users\Perry\Desktop\sts2-rl`. The RL stack is raw-PyTorch masked PPO:
`train_torch.py` (loop), `sts2_rl/models.py` (`MaskedActorCritic`),
`sts2_rl/full_env.py` (combat env, flat Box obs + `Discrete(79)` +
`action_masks()`), `sts2_rl/run_env.py` (full-run env, flat Box obs +
`Discrete(1381)`), `sts2_rl/curriculum_env.py` (subclasses the run env, same
layout). Obs layout is documented in `OBS_PLAN.md` and self-described at
runtime by each env's `obs_segments` / `obs_slices`.

## Problem

The observation is dominated by sparse one-hots over capacity-padded
vocabularies (`sts2_rl/vocab.py`: cards 640, relics 336, powers 288, monsters
144, potions 80, events 96, purposes 24 — live counts are far smaller, and
most slots are zero at any given step). A flat MLP burns most of its
parameters on first-layer rows that fire rarely, and the 29k-float obs makes
rollout buffers and host↔device copies expensive. Replace it with an
embedding/entity architecture.

## Design requirements

1. **Preserve the vocab contract.** Embedding tables are indexed by the
   frozen `vocab.json` indices, with `num_embeddings = capacity(kind)` (from
   `sts2_rl/vocab.py`). That keeps today's guarantee: porting new content
   appends vocab rows, never reshapes weights — future content additions stay
   fine-tune-only. This is the whole reason the capacities exist; don't size
   tables to live counts.

2. **Two implementation strategies — evaluate, then pick:**
   - **(a) Model-side only (recommended first step):** keep the envs' flat Box
     obs unchanged and give the model the layout: pass `obs_slices` into the
     model constructor; the model slices each segment and applies per-segment
     encoders (a one-hot segment × embedding matrix is just a `Linear` without
     bias over that slice — mathematically an embedding lookup, but works on
     the existing float obs, including multi-hot histogram segments where it
     becomes a sum of embeddings, which is exactly the right set-pooling).
     Zero env changes, no schema bump, but rollout buffers stay 29k floats.
   - **(b) Env-side structured obs:** envs emit integer id arrays + dense
     scalar blocks (Dict space or packed int/float pair); model does true
     `nn.Embedding` lookups. Buffers shrink ~50×, copies get cheap, but it
     touches every env, the PPO loop's buffer code, and bumps both schema
     versions. Do (a) first, measure, and only do (b) if buffer/copy cost is
     the proven bottleneck.

3. **Shared embeddings across segments.** One card-embedding table serves
   hand/draw/discard/exhaust histograms, deck histogram, shop rows, reward
   rows, and select-candidate histograms (upgraded status enters as a
   learned offset or a 2-row modifier table, matching the `2 × N_CARDS`
   base/upgraded encoding). Same for relic/potion/monster/power/event tables.
   Entity structure: per-enemy rows (`enemy_row` in `full_env.py`) become
   [monster embedding ‖ scalar block ‖ pooled power embeddings]; pool
   variable-size sets with sum or mean (attention only if sum demonstrably
   plateaus).

4. **Action space unchanged.** Keep the flat masked `Discrete` heads —
   `train_torch.py` only depends on `reset`/`step`/`action_masks` and the
   model's `get_value` / `get_action_and_value` signatures (see the module
   docstring). Optional refinement for the run env's `2 × N_CARDS` select
   block: score it as dot products between a select-head query and the card
   embeddings (weight tying) instead of 1,280 independent output rows — this
   makes select generalize across cards, but keep the output shape
   `(B, n_actions)` so the loop and masking are untouched.

5. **Checkpoint/architecture stamping.** `train_torch.py` refuses checkpoints
   on `(obs_dim, n_actions, hidden)` mismatch and stores schema versions.
   Extend the stamp with an architecture tag (e.g. `arch: "mlp" | "entity"`)
   so old MLP checkpoints are refused with a clear message. This is a
   deliberate full retrain — there is no weight migration from the MLP.

## Deliverables

- `sts2_rl/models.py`: new model class alongside `MaskedActorCritic` (keep
  the MLP for A/B comparison), selected by a `--arch` flag in
  `train_torch.py`.
- Tests: forward/`get_action_and_value` shape + mask correctness (illegal
  actions get ~0 probability); embedding-table sizes == capacities;
  determinism under seed; checkpoint save/resume round-trip including the
  arch stamp and refusal of mismatched arch.
- Benchmarks, reported in the final summary: sps (rollout and update split,
  like the baseline above) and params for MLP vs entity model; a short
  equal-timestep training run of each (e.g. 200k steps on `--env column`)
  comparing ep_ret/win curves. The entity model should be strictly smaller
  in first-layer params and at least match the MLP's learning curve.
- Doc updates: `OBS_PLAN.md` (architecture section) and `CLAUDE.md`
  (models.py entry).

## Constraints

- `sts2_rl/vocab.json` is frozen/append-only; never reorder. Table row `i`
  must mean vocab id `i` forever.
- Full suite green: `py -m pytest test/ -q`.
- Don't change env obs layouts in strategy (a); if you proceed to (b), bump
  `OBS_SCHEMA_VERSION` / `RUN_OBS_SCHEMA_VERSION` and document the new layout
  in `OBS_PLAN.md` with the same segment-table rigor as the current version.
