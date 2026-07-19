# Graceful pause for `train_torch.py`

Date: 2026-07-18

## Problem

A training run can already be *resumed*: `train_torch.py` auto-resumes the
checkpoint at `--save`, restoring model, optimizer, `global_step`, `best_score`,
the CSV, and the env seed offset (`start_iter`). Running `--timesteps 25000000`
twice already yields 50M steps across two sittings.

What is missing is the *stop* side. The trainer installs no signal handler; the
`try/finally` around the iteration loop only closes env workers. Consequences:

- Ctrl-C loses everything since the last periodic save — up to `--save-every`
  (default 50) iterations, ~200k steps at default settings.
- The interrupt can land mid-rollout or mid-PPO-update, where there is no
  coherent state to write.
- With `--n-workers > 0` there is a second failure: workers exit on
  `KeyboardInterrupt` (`sts2_rl/vec_env.py`), and on Windows Ctrl-C is delivered
  to the whole console process group. Any scheme where the parent keeps working
  after the first Ctrl-C would find its workers already gone.

## Behavior

First Ctrl-C:

```
stop requested — finishing iteration N, then saving (Ctrl-C again to abort now)
```

The loop completes the current rollout, PPO update and logging row, breaks,
saves to `--save`, prints the resume command, and exits 0.

Second Ctrl-C: aborts immediately via the restored default `SIGINT`. The last
periodic checkpoint is intact — `atomic_save` writes to `<path>.tmp` and
`os.replace`s, so an interrupted write can only leave the previous checkpoint.

Resume is unchanged: re-running the same command auto-resumes `--save` with a
fresh `--timesteps` budget.

## Components

### 1. `GracefulStop` (in `train_torch.py`)

A small class, ~15 lines:

- `install()` registers the `SIGINT` handler.
- The handler sets `.requested`, prints the notice once, and restores the
  default handler, so the next Ctrl-C is a hard abort.

Kept as an object rather than a module global so tests can call
`.handler(signal.SIGINT, None)` directly — no real signals in the test suite.
It lives in `train_torch.py` rather than a new module: it is trainer-specific,
and `test/test_train_io.py` already imports from `train_torch`.

### 2. Loop check

One `if stop.requested: break` at the end of the iteration body, after the
existing periodic-checkpoint block. Placing it there means a stop that
coincides with a `--save-every` boundary does not write the checkpoint twice.

### 3. Correct the post-loop save

Current code:

```python
save(agent, optimizer, start_iter + n_iters, args, ...)
```

This is correct only because the loop always runs to completion. On a break it
overstates progress, and since `start_iter` offsets both the env seeds and the
`anneal_fraction` baseline, the next resume would silently skip ahead.

Fix: track the last completed iteration.

- Initialize `completed = start_iter` before the loop.
- Set `completed = iteration + 1` at the end of the iteration body.
- Post-loop: `save(agent, optimizer, completed, args, ...)`.

This also covers `n_iters == 0`, where the loop never runs and `completed`
correctly stays `start_iter`.

With this fix the existing post-loop `save()` *is* the pause checkpoint; no new
save path is added. `.best.pt` and the iter-stamped snapshots stay on the
periodic path only — they exist to roll back a late policy collapse, which a
deliberate pause is not.

### 4. Workers ignore SIGINT

`signal.signal(signal.SIGINT, signal.SIG_IGN)` at the top of `_worker_main` in
`sts2_rl/vec_env.py`, so workers die only on the parent's explicit `close`.
This is the standard subprocess-vec-env pattern. The existing
`except (KeyboardInterrupt, EOFError)` stays as a backstop.

## Testing

In `test/test_train_io.py`:

- The handler sets `requested` and prints the notice once.
- After the handler fires, the `SIGINT` disposition is back to the default
  (asserting the second Ctrl-C is a hard abort).
- A fake loop harness asserts the checkpoint written on break carries the
  *completed* iteration, not the budgeted one.

The `vec_env` change is covered by the existing worker round-trip test
continuing to pass.

Full suite must stay green: `py -m pytest test/ -q`.

## Out of scope

- A sentinel-file trigger for detached/backgrounded runs.
- Pausing and later resuming a *specific* `--timesteps` budget; a resume still
  takes a fresh budget, as today.
- Any change to how `--timesteps`, `--anneal-lr`, or `--ent-coef-final`
  schedules are interpreted across invocations.
