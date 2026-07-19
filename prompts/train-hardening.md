# Prompt: Harden train_torch.py for unattended long runs

Copy everything below into a fresh session.

**When to run this:** before any multi-day training run. Small, independent
items — all in `train_torch.py`.

---

In `c:\Users\Perry\Desktop\sts2-rl`. Training is raw-PyTorch masked PPO
(`train_torch.py`), single file by design; checkpoints carry
`model/optim/iteration/obs_dim/n_actions/hidden/arch/obs_schema/env_kind`.
Measured baseline (2026-07-18): 176 sps at `--env column --arch entity`
defaults → one iteration ≈ 23 s, so `--save-every 50` ≈ 19 min between
saves.

## Problems (verified in code)

1. **Non-atomic saves.** `save()` calls `torch.save` directly on the target
   path. A crash/Ctrl-C mid-write corrupts the ONLY auto-resume checkpoint.
2. **Single overwritten checkpoint.** A late-run policy collapse (KL spike,
   entropy crash) silently overwrites the best weights within one
   save interval; there is no way back.
3. **No persistent metrics.** Stats go to stdout only — after a multi-day
   run there is no curve to inspect or compare.
4. **Resume gotchas:** `optimizer.load_state_dict` restores the saved LR, so
   `--lr` on resume is silently ignored; `global_step`/`t0` restart at 0 (sps
   and step counts misleading after resume); envs re-reset with the same
   `args.seed + i`, replaying the original run's initial episode draws.

## Design

1. **Atomic save**: write to `<path>.tmp` in the same directory, then
   `os.replace`. Applies to every save call.
2. **Rolling snapshots**: alongside the live `--save` file, also write
   iter-stamped snapshots (`<stem>.iter{N:06d}.pt`) on each periodic save and
   keep the most recent K (`--keep-snapshots`, default 5; 0 disables).
   Optionally track a `<stem>.best.pt` keyed on the 100-episode win-rate
   (or ep_ret for reward-shaped envs) — document that this is the
   exploring-policy metric, not a greedy eval.
3. **CSV log**: append one row per iteration to `<stem>.csv`:
   iter, global_step, wall_seconds, sps, ep_ret, win, ep_len, pg, v, ent,
   kl, clipfrac, lr. On resume, append without re-writing the header. This
   is deliberately CSV-not-TensorBoard: zero deps, trivially plottable.
4. **Resume fixes**: stamp `global_step` into the checkpoint and restore it;
   make `--lr` on resume explicit — change the flag default to `None`
   (fresh runs resolve to 3e-4); when passed together with a resume, apply
   it to the loaded optimizer's param groups and say so; fold `start_iter`
   into the per-env reset seeds so resumed runs don't replay the original
   opening episodes.

## Deliverables

- The four items above in `train_torch.py` (keep it single-file).
- Tests (extend `test/test_models.py`'s checkpoint tests or a new
  `test/test_train_io.py`): atomic replace leaves a loadable file when a
  fake failure interrupts the write; snapshot rotation keeps exactly K;
  CSV append-on-resume produces one header; `global_step` round-trips.
- Old checkpoints (without `global_step`) must still load (`.get` default).
- Doc update: `CLAUDE.md` Commands section if flags change.
- Full suite green: `py -m pytest test/ -q` (1914 baseline).
