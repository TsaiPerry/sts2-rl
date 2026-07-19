# Prompt: Subprocess env workers for train_torch.py

Copy everything below into a fresh session.

**When to run this:** AFTER `prompts/obs-vectorization.md` has landed — env
stepping was measured at ~87% observation building (2026-07-18); parallelize
the remainder, don't parallelize waste. Re-measure the serial trainer sps
first and use it as the baseline here.

---

In `c:\Users\Perry\Desktop\sts2-rl`, Windows. `train_torch.py` steps
`--n-envs` (default 8) envs **serially in-process** (the loop in the rollout
phase); the model batches inference across envs, but env stepping is
single-core. Envs: `STS2FullCombatEnv` / `STS2RunEnv` /
`STS2CurriculumRunEnv` (the run-scale envs drive the engine on a greenlet —
greenlets are per-process state; each worker process simply owns whole envs,
so this needs no special handling beyond not sharing envs across processes).

## Design

1. **Worker processes** (`multiprocessing`, `spawn` start method — the only
   one on Windows): `--n-workers W` (default: min(n_envs, cpu_count-1));
   each worker owns `n_envs / W` envs. Command protocol over pipes:
   `reset(seeds)`, `step(actions) -> (obs, rewards, dones, masks, info
   summaries)` batched as numpy arrays, `close`. Keep the training loop's
   lockstep-synchronous semantics — buffers, GAE, and the update do not
   change shape or math.
2. **Auto-reset in the worker** on episode end, following the gymnasium
   vector convention: when an episode terminates/truncates, the worker
   returns the **final** observation (needed for the truncation bootstrap:
   the main loop computes `gamma * V(final_obs)` — today it does this
   inline; preserve exact semantics) plus the reset observation for the
   next step, and the terminal info fields the loop consumes
   (`is_success`, episode return/length accounting stays in the main loop).
3. **Seeding unchanged**: env *i* (global index) gets `args.seed + i`
   exactly as today, regardless of worker layout — a run with W workers and
   the serial path must see identical per-env episode streams for a fixed
   policy.
4. **Transport**: start with pickled numpy batches over pipes; obs are 29k
   float32 (~117 KB/env/step). If profiling shows serialization dominating,
   switch to `multiprocessing.shared_memory` ring buffers — measure before
   adding that complexity. (The real fix for obs size is strategy (b) of
   the retired embedding-model prompt — env-side integer obs — which is a
   separate, schema-bumping project.)
5. **Fallback**: `--n-workers 0` (or 1?) keeps the current in-process serial
   path — keep it for debugging and for the equivalence test.

## Deliverables

- Worker plumbing (a small module or a section of `train_torch.py`; keep the
  loop's core untouched — it should still only see stacked
  obs/mask/reward/done arrays).
- **Equivalence test**: with a fixed seed and a deterministic policy stub,
  serial and worker paths produce identical rollout buffers for a few
  hundred steps (combat env at minimum; run env as a smoke test).
- Benchmarks in the final summary: trainer sps serial vs 2/4/8 workers on
  `--env column --arch entity` (pre-parallelization baseline 176 sps on
  2026-07-18, before obs vectorization — re-measure post-vectorization
  first), plus worker startup overhead (engine import is seconds per spawn;
  amortized over a long run, but report it).
- Ctrl-C / crash handling: workers terminate cleanly with the parent
  (daemon processes or explicit close in `finally`), no orphaned pythons.
- Full suite green: `py -m pytest test/ -q` (1914 baseline).

## Constraints

- Windows `spawn` means everything sent to workers must be picklable and
  module-level importable — no lambdas/closures in worker args.
- Do not change env semantics, obs layout, action layout, or schema
  versions.
- Checkpoints remain identical in format; resume works across worker-count
  changes (worker layout is a runtime detail, not checkpoint state).
