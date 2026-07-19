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

A large flat `Box` in `[0, 1]`, schema v2, built in `_build_obs`. The design
principle: *the agent sees everything a human sees, with absolute numbers so
lethal math is computable.* Every HP-like quantity is encoded on a shared dual
scale (`/100` fine + `/500` coarse via `_abs2`). Segments (mapped by name in
`obs_segments`):

- **Player vitals** — HP (ratio + absolute), block, energy, strength/dexterity,
  pile sizes, telegraphed incoming damage, history scalars, and the full
  `ALL_POWERS` vocabulary (presence + signed amount at two scales).
- **Hand rows** (one per slot) — card identity one-hot + engineered features
  (effective energy cost, type/target flags, base/effective damage & block).
- **Enemy rows** (one per slot) — absolute vitals, 9 intent flags, the intent's
  attack run through the full damage pipeline via `previews.py`, enemy identity
  one-hot, power vocabulary.
- **Damage matrix** — a H×E grid aligned 1:1 with the play actions: the exact
  modified per-hit damage each card would deal to each enemy.
- **Potion rows** + **pile histograms** (order-agnostic base/upgraded card
  counts for the draw / discard / exhaust piles).

The obs dimension is **measured once** at construction (by building a throwaway
combat), so the declared space can never drift from `_build_obs`.

### Reward

In `step`: per-step normalized player-HP delta + a terminal win/loss bonus,
optionally plus a dense enemy-damage-dealt signal. Since only `end turn`
advances enemies, damage taken is naturally attributed to the step that ended
the turn.

---

## Layer 2 — `models.py`: the network

`MaskedActorCritic` is a deliberately plain MLP baseline — **separate** actor
and critic trunks (no shared torso), each a `Tanh` MLP with orthogonal init (the
standard PPO recipe: `sqrt(2)` gain on hidden layers, `0.01` on the policy head
for a near-uniform initial policy, `1.0` on the value head).

The key method is `_dist`: it computes action logits, then
`masked_fill(~mask, -1e8)` drives illegal actions to ~0 probability *before*
building the `Categorical`. This guarantees the distribution the agent **acts
under** and the one the **update scores** are identical — exactly what a
hand-rolled PPO must get right.

This file is the single swap point: to upgrade to embeddings / attention over
per-entity tokens, only `models.py` changes.

---

## Layer 3 — `train_torch.py`: the PPO loop

A single-file, hand-vectorized PPO over `--n-envs` synchronous envs (default 8).
Standard CleanRL-style structure:

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
   advantage normalization, gradient clipping, optional `target_kl` early-stop.

Checkpoints stamp `OBS_SCHEMA_VERSION`, and `--resume` refuses to load if the
schema changed — a guard against silently loading a model against an
incompatible observation layout.

---

## The seam that makes it modular

The loop only ever touches `env.reset / step / action_masks` and the model's
three methods (`get_value`, `get_action_and_value`, and `_dist` internally).
That is the deliberate design stated in both docstrings:

> **Change the observation in `full_env.py`, change the torso in `models.py`,
> and `train_torch.py` never moves.**

The masking is applied consistently at both act-time and update-time, which is
the one correctness-critical detail of doing masked PPO without SB3.
