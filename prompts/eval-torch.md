# Prompt: Evaluation harness for the raw-torch checkpoints

Copy everything below into a fresh session.

**When to run this:** before any long training run — without it there is no
way to compare checkpoints or verify a long run actually worked.

---

In `c:\Users\Perry\Desktop\sts2-rl`. Training is raw-PyTorch masked PPO
(`train_torch.py` + `sts2_rl/models.py`), producing arch-stamped checkpoints
(`runs/*.pt` with `model/optim/iteration/obs_dim/n_actions/hidden/arch/
obs_schema/env_kind` keys — see `train_torch.save` and `check_checkpoint`).

## Problem

`eval.py` and the adapters in `sts2_rl/evaluation.py` (`model_policy`) only
load **SB3 MaskablePPO zips** — the legacy path. There is no policy adapter
for the raw-torch checkpoints actually being trained
(`runs/sts2_column_torch.pt`, `runs/sts2_run_torch.pt`, the bench pair), and
no evaluation mode for the run-scale envs at all. The only signal during
training is the log's win rate, which comes from the *exploring* policy on
the training distribution.

## Design

1. **Torch policy adapter** (in `sts2_rl/evaluation.py`, beside
   `model_policy`): load a checkpoint, dispatch on its `arch` stamp to
   rebuild `MaskedActorCritic` or `EntityActorCritic` exactly the way
   `train_torch.make_model` does (`EntityActorCritic` needs the segment
   layout — reuse/relocate `train_torch.env_obs_segments` so trainer and
   eval share one construction path rather than duplicating it), call
   `model.eval()`, and act **greedy** (argmax over masked logits; optional
   `--sample` flag for stochastic rollouts). Refuse mismatched
   `obs_schema` / `env_kind` with the same clear messages as
   `train_torch.check_checkpoint` (reuse it).
2. **Run-scale evaluation loop**: N seeded episodes on
   `STS2RunEnv` / `STS2CurriculumRunEnv` (`--env run|column`, `--acts`
   passthrough). Report at minimum: win rate, mean/median **max floor
   reached**, act-reached histogram, death floor/act distribution, HP left
   on wins, mean decisions per episode. Always offer a `masked-random`
   baseline row (`run_env.masked_random_run_policy`).
3. **Combat checkpoints** (`env_kind: "combat"`): route through the existing
   `evaluate_win_rate` + `evaluate_probes` machinery with the new adapter,
   so torch combat models get win rate + lethal-probe accuracy like SB3
   models do.
4. **CLI**: extend `eval.py` — detect `.pt` (torch) vs SB3 zip by extension/
   content and dispatch; keep the existing SB3 paths working unchanged.

## Deliverables

- Adapter + run-scale evaluation in `sts2_rl/evaluation.py`, CLI in
  `eval.py`.
- Tests: adapter greedy determinism under fixed seed; arch dispatch from the
  stamp (both arches); schema/env-kind refusal; a smoke evaluation of a
  freshly constructed (untrained) model on a short seeded column episode
  batch.
- Doc updates: `CLAUDE.md` Commands section (eval examples for torch
  checkpoints), `RL_ARCHITECTURE.md` if it gains a moving part.
- Full suite green: `py -m pytest test/ -q` (1914 baseline).

## Constraints

- Evaluation must not mutate checkpoints and must run on CPU by default.
- Keep `train_torch.py`'s loop untouched except for relocating shared
  helpers (`env_obs_segments` / `check_checkpoint`) if you choose to — if
  relocated, `train_torch.py` imports them from the new home (no behavior
  change, checkpoints stay compatible).
- Deterministic given `--seed`: same seed → same episodes → same report.
