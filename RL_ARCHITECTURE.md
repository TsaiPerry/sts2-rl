# RL architecture (current)

How the reinforcement-learning stack fits together, starting from the
environment. The system is a **masked PPO** setup in three layers, each
swappable without touching the others:

```
full_env.py  →  models.py  →  train_torch.py
(env: obs,       (network:      (PPO loop:
 actions,         masked         rollout + GAE
 masks, reward)   actor-critic)  + clipped update)
```

---

## Layer 1 — `full_env.py`: the environment

`STS2FullCombatEnv` is a Gymnasium env wrapping the real combat engine
(`CombatState`). It exposes the three things the PPO loop depends on: `reset`,
`step`, and `action_masks`.

### Action space

A flat `Discrete`, decoded in `_decode_action`:

| Range          | Meaning                          |
|----------------|----------------------------------|
| `0`            | end turn                         |
| `1 .. H*E`     | play hand card *h* at enemy *e*  |
| next `P*E`     | use potion *p* at enemy *e*      |

where `H = 10` hand slots, `E = 6` enemy slots, `P = 3` potions. Non-targeted
cards (SELF / ALL_ENEMIES) are collapsed to one canonical target so equivalent
actions don't bloat the space.

### Action masking

`action_masks()` returns a boolean legality vector — the crux of the whole
design. Rather than let the policy waste probability on illegal plays (wrong
phase, unaffordable energy, dead target), the mask enforces legality. It checks
`card.is_playable`, the `should_play_card` hook, hook-modified energy cost vs
available energy, and living-enemy targets. End-turn is always legal.

### Observation

A two-leaf `spaces.Dict({"f": float32 Box, "i": int32 Box})` — the
integer/entity contract of **`OBS_SCHEMA.md`**, which is the normative
description (padding rule `id == 0`, segment tables, admissibility rule).
Combat schema 6 (`f` 1677 / `i` 606); the run envs embed the combat block
under a `combat.` prefix (run schema 9, `f` 4710 / `i` 1464). The design
principle is unchanged: *the agent sees everything a human sees — and
nothing a human cannot* (§6's display-path rule), with absolute numbers so
lethal math is computable. The `damage_matrix` segment stays a H×E float
grid aligned 1:1 with the play actions.

Both halves keep named `(segment, width)` maps (`combat_obs_segments_f/_i`,
`run_obs_segments_f/_i`); `--zero-segments`, the segment plans in
`models.py` and the pin tests all address the observation by segment name.

### Start state (R11 — mid-run snapshot distribution)

By default every combat episode starts from the fixed 13-card deck, zero
relics, full HP and the Act-1 non-boss pool. `STS2FullCombatEnv` also
accepts the rich start-state kwargs `CombatState` always supported
(`relics`, `max_hp` / `current_hp`, `deck_cards` with upgrades /
enchantments / afflictions, a gap-preserving `potion_slots` belt), and —
the point of the plumbing — `snapshots=`: a dataset of
`(deck, relics, hp, potions, act, encounter)` snapshots harvested from
run-env episodes (`sts2_rl/snapshots.py`, JSONL), sampled at every
`reset()` from a dedicated RNG so the combat stream itself is untouched.
`harvest.py` produces datasets (masked-random by default, `--checkpoint`
for a trained policy; watchdog-armed, per-step repro log, no
timeout-and-continue by design), and `train_torch.py --start-snapshots
PATH` trains the cheap env on the hard env's state distribution. Datasets
cross worker boundaries as paths, loaded per-process.

### Reward

In `step`: per-step normalized player-HP delta + a terminal win/loss bonus,
optionally plus a dense enemy-damage-dealt signal. Since only `end turn`
advances enemies, damage taken is naturally attributed to the step that ended
the turn.

---

## Layer 2 — `models.py`: the network

The live architecture is **`entset`** (`EntitySetActorCritic`), the only arch
buildable against the modern Dict observation — `mlp` (`MaskedActorCritic`)
and `entity` (`EntityActorCritic`) are frozen v3-era baselines that
`checkpoints.make_model` refuses against combat schema ≥ 4 / run schema ≥ 7
(a per-`env_kind` *threshold*, so a future bump cannot silently disable the
refusal).

**Encoder** (`_EntsetEncoder`, one instance each for actor and critic): one
`nn.Embedding(capacity + 1, dim, padding_idx=0)` per vocabulary kind (9
tables — cards, relics, powers, monsters, potions, events, purposes,
afflictions, enchantments; rows from `vocab.CAPACITIES`, so porting content
appends rows instead of reshaping weights). Each `.ids` row block concats
its embeddings with its paired floats, projects through a shared
`Linear(row_in, block_dim=32) + tanh`, multiplies by the presence mask
(id ≠ 0, OR any-float-nonzero — PAD rows become exact zero vectors) and
sum-pools over rows. `.f`-only segments pass through raw. `encode(obs)`
returns both the pooled vector and the per-row features
(`dict[logical_block_name, (cap, block_dim)]`) — the tied head reads the
rows; the critic reads only the pooled vector.

**Tied action head (phase 2, `ENTSET_HEAD_VERSION = 4`).** The actor trunk
is a feature MLP (`hidden = (256, 256)`, Tanh, orthogonal init) whose output
`ctx` feeds per-block heads assembled by an explicit `ActionLayout`
(`combat_action_layout` / `run_action_layout` — every base offset imported
live from `full_env` / `run_env`, validated to tile `n_actions` exactly at
construction):

- **end turn** — `Linear(ctx, 1)`;
- **play block** — a `PairPointerHead` (`action_heads.py`) scoring every
  (hand row, enemy row) pair `[src; tgt; proj(ctx); pair] → MLP → logit`,
  row-major `h*MAX_ENEMIES + e`, exactly the env's action grid. The 7
  `pair` features (R9) are the `damage_matrix` cell for that exact
  (card, enemy) pair plus the enemy's incoming-preview floats — the head
  that picks the action sees the number that decides it;
- **potion block** — a second, independent `PairPointerHead` over
  (potion row, enemy row) pairs (no pair features);
- **run-env SELECT and belt-POTION blocks** — `PointerHead`s over the
  `select.candidates` / `run.potions` rows (R8), replacing their
  positional Linears: each option scored from its own content;
- **run-env CHOICE block** — a positional `Linear(ctx, 16)` base plus
  additive, presence-gated content overlays (R8): reward-card rows, shop
  card/relic/potion rows, the shop-removal cost floats and the `map{m}`
  option floats each score the CHOICE slot they occupy (offsets pinned by
  a `driver.py` census). A PAD row contributes exactly 0.0, so
  out-of-phase overlays are inert. EVENT / REST / SELECT_OPTION /
  REWARD_POTION options carry no content rows in the observation and stay
  purely positional — by decision, not omission.

`--shared-encoder` (R10, measured and kept) builds ONE encoder serving
actor and critic; the default stays separate. A/B on paired seeds: +2.4%
sps, no stability regression at the probe budget.

Because the pair heads read the same mask-multiplied entity rows the
observation encoder computes, the policy scores *cards*, not hand slots —
swapping two hand rows provably permutes the corresponding play logits
(pinned by equivariance tests in `test/test_tied_head_combat.py` /
`_run.py`, with a positional-baseline sanity test proving the property can
fail).

The key method is unchanged: `_dist` computes action logits, then
`masked_fill(~mask, -1e8)` drives illegal actions to ~0 probability *before*
building the `Categorical`. This guarantees the distribution the agent
**acts under** and the one the **update scores** are identical — exactly
what a hand-rolled PPO must get right. `get_value` / `get_action_and_value`
keep their signatures, so `train_torch.py` never moved through the phase-2
restructure.

---

## Layer 3 — `train_torch.py`: the PPO loop

A single-file, hand-vectorized PPO over `--n-envs` synchronous envs.
Envs step through `sts2_rl/vec_env.py` — `--n-workers` defaults to auto:
4 subprocess workers at 16+ envs, the in-process serial path below that
(measured 2026-08-02 on the integer schema: +57% sps combat / +42% column
at 32 envs, worker arms bit-equivalent in training behavior; the old "~4%,
leave off" verdict died with the 117 KB float payload). An auxiliary
critic-side win-prediction head (R13) was built, A/B-measured on paired
seeds, and **deleted on a null result** — the numbers live in the phase-3
ledger. Standard CleanRL-style structure:

1. **Rollout** — for `n_steps` (512), stack each env's obs + mask, call
   `get_action_and_value` under `no_grad`, step all envs. Buffers are
   `[n_steps, n_envs, ...]`. Masks are re-fetched every step via `stack_masks()`.
   - **Truncation bootstrap**: on time-limit truncation (not real termination),
     fold `gamma * V(terminal_obs)` into the reward so GAE treats the cutoff
     correctly. Natural terminations bootstrap 0.
2. **GAE** — standard generalized advantage estimation backward over the
   rollout; `returns = advantages + values`.
3. **Update** — flatten the batch, then for `epochs` (4) × `minibatches` (8):
   recompute logprob / entropy / value **with the stored masks**, compute the
   clipped policy loss, a clipped value loss, minus entropy bonus. Per-minibatch
   advantage normalization, gradient clipping, and a `target_kl` early-stop on
   each epoch's *mean* approx_kl (default 0.02 for the run-scale envs, off for
   `--env combat`). The LR (`--anneal-lr`) and entropy coefficient
   (`--ent-coef-final`) can decay linearly across the invocation's iterations;
   a resume restarts either schedule over its own `--timesteps` budget.

Checkpoints stamp `OBS_SCHEMA_VERSION` **and `head_version`
(`models.ENTSET_HEAD_VERSION`)**; `--resume` refuses a changed schema, and an
entset checkpoint whose stored version differs from the current constant
(`!=`, not a floor — a missing key reads as version 1) is refused with an
honest "use `--fresh`" message *before* the shape check can produce a
confusing fallback error.

---

## Layer 4 — `checkpoints.py` + `evaluation.py`: reloading and scoring

Rebuilding a saved model needs the same three decisions the trainer made — env
layout, architecture, hidden sizes. `sts2_rl/checkpoints.py` owns that as a
`ModelSpec`, so the trainer (`--resume`) and the evaluator (`eval.py`) share
one construction path instead of each keeping a copy of the rules:

- `obs_schema_version` / `model_obs_segments` — the layout the checkpoint's
  observation and the entity model's segment slicing must agree on;
- `make_model` — `--arch` dispatch;
- `check_checkpoint` — refuses a mismatched env kind, schema, arch or shape
  with a message instead of a `load_state_dict` traceback. `run` and `column`
  are deliberately interchangeable: that handoff *is* the curriculum's phase 2;
- `load_agent` — checkpoint → eval-mode model, dispatching on the checkpoint's
  own `arch` stamp so weights always reload as what they were trained as.

`sts2_rl/evaluation.py` turns models into policies (`(env, obs, mask) -> int`)
and scores them. `TorchPolicy` acts greedily — `argmax` over
`model.action_logits`, the mode of the distribution the agent trained under —
or samples from it under a seeded generator. Two evaluators sit on top:
`evaluate_win_rate` + `evaluate_probes` for the combat envs, and
`evaluate_run` for the run-scale ones, which reports max floor reached, acts
reached, the death-floor distribution and decisions per episode. Win rate alone
can't rank two run-scale checkpoints while both sit near zero; floors can.

Two run-scale additions (phase 3):

- **Run micro-probes** (`sts2_rl/run_probes.py`) — fixed scenarios with one
  clearly-right decision (rest at critical HP, buy the dominant shop
  removal, take the on-curve reward card), built by pinning a `RunState`
  through a `_make_run_state` override and scored on the resulting run
  state, `probes.py`-style. A scripted oracle scores 1.0 and an
  anti-oracle 0.0 by construction, so the checks are proven to
  discriminate.
- **Paired-seed A/B** (`evaluation.compare_runs`, `eval.py --compare A B`)
  — both checkpoints play the same fixed seed list (`EVAL_SEEDS`), and the
  report is per-seed deltas plus better/worse/tie counts, not two
  aggregate means on different seeds — which is how a real regression
  hides inside run-to-run variance.

---

## The seam that makes it modular

The loop only ever touches `env.reset / step / action_masks` and the model's
methods (`get_value`, `get_action_and_value`, plus `action_logits` for greedy
evaluation).
That is the deliberate design stated in both docstrings:

> **Change the observation in `full_env.py`, change the torso in `models.py`,
> and `train_torch.py` never moves.**

The masking is applied consistently at both act-time and update-time, which is
the one correctness-critical detail of doing masked PPO without SB3.
