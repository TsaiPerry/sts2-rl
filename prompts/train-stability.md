# Prompt: PPO stability knobs for unattended long runs

Copy everything below into a fresh session.

**When to run this:** cheap and independent; land it any time before a
multi-day run. Pairs with `prompts/train-hardening.md` (which owns
checkpoint/logging hygiene; this one owns the optimization schedule).

---

In `c:\Users\Perry\Desktop\sts2-rl`. `train_torch.py` is a single-file
raw-PyTorch masked PPO (CleanRL-style). Current defaults: constant
`--lr 3e-4`, `--ent-coef 0.01`, `--target-kl None` (off). Measured healthy
short-run stats (2026-07-18, `--env column --arch entity`): KL ≈ 0.008–0.011,
clipfrac 0.05–0.09, entropy ≈ 1.3.

## Motivation

Over tens of millions of unattended steps, a single destructive update (KL
spike) or an LR that stays at its warm-up value forever can quietly ruin a
run. These are the two standard guards.

## Design

1. **Linear LR annealing** (`--anneal-lr`, off by default to preserve
   current behavior): each iteration set
   `lr = args.lr * (1 - done_fraction)` on the optimizer's param groups,
   where `done_fraction` counts THIS invocation's iterations
   (`(iter - start_iter) / n_iters`) — document that resuming restarts the
   schedule over the new `--timesteps` budget, which is the sane behavior
   for open-ended resume-based training. Log the effective lr each
   iteration (the CSV from train-hardening has an `lr` column).
   Note the interaction: `optimizer.load_state_dict` restores the saved lr
   on resume, so annealing must set lr AFTER any resume load, every
   iteration.
2. **target_kl on by default for the run-scale envs**: default
   `--target-kl 0.02` for `--env run|column` (long-horizon, high-variance),
   keep `None` for `--env combat` unless passed. It early-stops the epoch
   loop only — cheap, standard, and the measured baseline KL (~0.01) sits
   comfortably under it. Make the KL used for the check more robust than
   today's last-minibatch value: track the mean approx_kl over the epoch's
   minibatches and check that.
3. Optional, only if trivial: `--ent-coef-final` for linear entropy-bonus
   annealing (default: equal to `--ent-coef`, i.e. constant). Do NOT add
   speculative schedulers beyond these.

## Deliverables

- The flags above in `train_torch.py` (single-file, minimal diff).
- Tests: annealing math at iteration boundaries (start, mid, final
  iteration; resume restart); target-kl early-stop triggers on a synthetic
  KL sequence; defaults unchanged for `--env combat`.
- Doc update: `CLAUDE.md` Commands section if defaults change behavior.
- Full suite green: `py -m pytest test/ -q` (1914 baseline).
