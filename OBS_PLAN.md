# OBS_PLAN.md — observation/precision overhaul for STS2FullCombatEnv

Plan from a design review (2026-07-06) of `sts2_rl/full_env.py` against the
engine and the decompiled game source. Goal: ensure the RL agent can access
**all information a human player sees**, with a **firm numeric grasp of entity
values** (lethal math, incoming damage, card values) so it can make precise
decisions.

Status: **ALL PHASES (1–4) DONE** (Phases 1–2 on 2026-07-06, shipped together
as observation schema v2 — `OBS_SCHEMA_VERSION = 2` in `full_env.py`; saved
models trained on v1 are invalid, retrain. Phases 3–4 on 2026-07-07 — no obs
change, no retrain needed, but Phase 3 rollouts differ from the
random-selector default).

2026-07-16 addendum — schema v3: every vocabulary-keyed segment is now sized
by the reserved capacities in `sts2_rl/vocab.py` (frozen append-only id
ordering persisted in `vocab.json`), not the live registry counts. Sized to
hold the complete game, so porting new content (cards, characters, relics,
monsters) never changes the obs/action layout again — checkpoints fine-tune
instead of retraining. One-time cost: hybrid 5699 → 17873 dims (features
4279 → 11473); the padded tail is constant (zeros / absent-encodings) until
content lands in those slots. References to "sorted" vocabularies below
predate this: ordering is now frozen-then-appended, sorted only at first
seed.

Implementation notes (where Phase 1–2 landed):

- `sts2_rl/previews.py` (new): pure-read preview helpers replaying DamageCmd/
  BlockCmd modifier stages — `preview_incoming_damage` (per-hit/hits/total/
  post-block, mirrors `AttackIntent.GetSingleDamage`), `preview_total_incoming`
  (block absorbed sequentially across enemies), `preview_card_damage` /
  `preview_card_block` / `preview_card_energy_cost`, `card_base_damage`.
  Purity + preview==reality property tests in `test/test_previews.py`.
- Card base stats (step 3a) needed **no per-card transcription**: every card
  already stores its printed numbers as instance vars in `_init_vars`
  (`self._damage` / `self._hits` / `self._block` / `self._hp_loss` + one
  magic amount), mutated by `_on_upgrade`. `Card` now exposes them as
  `base_damage` / `base_hits` / `base_block` / `base_hp_loss` /
  `magic_number` properties (upgrade-aware for free); the four dynamic cards
  (Body Slam, Bully, Ashen Strike, Perfected Strike) already had
  `calc_damage(ctx, target)`, which `card_base_damage` prefers.
- `full_env.py` schema v2: dual HP encoding on the shared `/100` + `/500`
  unit for HP/block/damage everywhere; pipeline-accurate intent previews and
  a per-(hand slot × enemy slot) effective-damage matrix aligned with the
  play actions; effective block + effective energy cost per slot; dexterity
  bug fixed (reads the `"dexterity"` power); full `ALL_POWERS` vocabulary
  (presence + signed amount at ±10/±50) for player and enemies; enemy
  identity one-hot from the `Monster.__subclasses__()` registry (covers
  summon-only enemies); history scalars (cards/attacks this turn, damage
  taken this combat); `enemy_hp_reward_scale` now normalized by the
  encounter's starting HP. Hybrid obs 4591 dims, features 3421, probe-
  measured as before.

Phases are ordered by value-per-effort; Phases 1–2 were done as ONE batched
observation-schema change (they all change the obs shape and invalidate saved
models — bump the schema version constant and retrain once, not
incrementally).

## Guiding principle

The agent currently sees strictly *less* numeric information than a human
looking at the game screen, which violates the repo's fidelity rule. The
decompiled source is the authority for what a player is shown:

- Intent damage: the game runs the **full modifier pipeline** for the displayed
  number — see `AttackIntent.GetSingleDamage` in
  `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\MonsterMoves\Intents\AttackIntent.cs`
  (lines 84–93): `Hook.ModifyDamage(..., ValueProp.Move, ..., ModifyDamageHookType.All, ...)`.
- Card numbers: the game prints fully modified values on card faces
  (`CardModel.UpdateDynamicVarPreview` / `CardPreviewMode`).

So pipeline-accurate previews in the observation are *fidelity*, not feature
engineering.

## What is already right (do not regress)

- Flat `Discrete` action space + MaskablePPO masks; untargeted cards collapsed
  to one canonical target (no duplicate-action bloat).
- Obs dimension measured from a probe combat at construction
  (`full_env.py` ~lines 171–175) — declared space can never drift from
  `_build_obs`. Keep this property through every change below.
- Pile-composition histograms (order-agnostic, base/upgraded split) — matches
  the player's information set without leaking shuffle order.
- Hybrid card encoding (one-hot identity + engineered features).
- Fixed slot bounds with summon headroom (`MAX_ENEMIES = 6`).
- Reward attribution: only `end turn` advances enemies.

## Findings (the gaps)

1. **Absolute HP unrecoverable — lethal is uncomputable.** Player/enemy HP are
   encoded only as `hp/max_hp`; `max_hp` appears nowhere. Incoming damage is
   absolute (`/60`). Ratios and absolutes are incomparable, so "will this hit
   kill me" / "is my Strike lethal" cannot be computed from the obs. Biggest
   single obstacle to precise play.
2. **Intent damage skips the modifier pipeline.** `full_env.py` `_enemy_row`
   computes `(intent.damage + e.strength) * intent.hits` — no Weak on the enemy
   (×0.75), no Vulnerable on the player (×1.5), no Intangible cap. The game
   shows the fully modified number (see AttackIntent.cs above).
3. **Card numeric values invisible.** `Card` base class has no damage/block
   attributes (numbers are hardcoded inside each `on_play`); obs has identity
   one-hot + cost/type/flags only. The net must memorize ~130 cards' values
   from reward alone.
4. **Dexterity bug (dead feature).** `full_env.py` line ~310:
   `_signed(getattr(p, "dexterity", 0), 30)` — no `dexterity` property exists
   anywhere in the engine (only `Creature.strength`, `creatures.py:29`;
   dexterity is a *power*, id `"dexterity"` in `powers.py`). The slot is frozen
   at 0.5, and `"dexterity"` was excluded from `PLAYER_POWER_IDS` because of
   this supposed dedicated slot → the agent is **completely blind to
   Dexterity**.
5. **Curated power lists + saturation lose information silently.**
   `PLAYER_POWER_IDS` (20) / `ENEMY_POWER_IDS` (18) vs ~50 registered powers;
   unlisted powers are invisible with no assertion guarding it. Amounts are
   `amount/20` clipped (Poison 25 ≡ Poison 45). Card feature f[0] is the *raw*
   energy cost, not the hook-modified effective cost (discounts only show as
   the binary affordable bit).

Secondary: enemy identity not observable (can't learn per-monster multi-turn
patterns); `card_selector` defaults to random (documented in RL.md);
`enemy_hp_reward_scale` defaults to 0 (no dense damage-dealt signal).

The toy `env.py` is intentionally minimal — leave it alone.

## Phase 1 — Restore absolute numbers; give the agent what the game shows — DONE

1. **Dual HP encoding.** For player and every enemy: keep the ratio, add `hp`
   and `max_hp` on ONE consistent absolute scale shared by every HP-like
   quantity (HP, block, damage) — `/100` clipped, plus a coarse `/500`
   companion so Act-2+ values don't saturate. One shared unit lets the network
   compare features (incoming vs remaining HP) with a single learned mapping.
2. **Pipeline-accurate incoming damage.** Engine helper
   `preview_incoming_damage(enemy) -> (per_hit, hits)` mirroring
   `AttackIntent.GetSingleDamage`: run `intent.damage` through
   `hooks.modify_damage_additive → multiplicative → cap` with `MOVE` props,
   exactly as `DamageCmd` will. Expose per-hit (modified), hits, and total per
   enemy row in the shared unit. Also expose a *post-block* preview
   (`max(0, total − player.block)` through `modify_hp_lost`) — the number the
   decision hinges on. Property-test: preview == damage actually dealt when the
   turn ends with no further plays.
3. **Card numbers in the observation.**
   - (a) Declarative base stats: optional `Card` class attrs (`base_damage`,
     `hits`, `base_block`, `magic`), transcribed across the ~110 cards from the
     values already hardcoded in `on_play` (already source-verified).
   - (b) Effective previews via the same hooks (Strength, Weak, target
     Vulnerable) — mirrors the game's on-card preview. Damage is
     target-dependent → per-slot × per-enemy effective-damage matrix
     (10×6 = 60 floats), aligned 1:1 with the `(slot, target)` action space.
     Effective block per slot (Dexterity/Frail-modified) is one float/slot.
4. **Effective energy cost per slot** (`hooks.modify_card_energy_cost`, `/6`)
   replacing the raw-cost feature; keep the affordability bit.

## Phase 2 — Close the coverage gaps — DONE

5. **Fix the dexterity bug** — read the `"dexterity"` power amount into the
   dedicated signed slot.
6. **Full power vocabulary.** Replace curated lists with the `ALL_POWERS`
   registry (sorted ids, same pattern as `CARD_IDS`): presence bit + amount at
   two scales (`/10` fine, `/50` coarse) per power per creature. (~1k extra
   dims — cheap next to the ~1300-dim hand block.) Alternative if staying
   curated: construction-time assertion that scans encounter pool + deck for
   reachable powers and fails loudly on an unlisted one.
7. **Enemy identity one-hot** from a sorted monster-class registry (the
   ENCOUNTERS registries give the classes) — lets the agent learn per-monster
   move distributions / multi-turn state-machine patterns.
8. **History scalars** only for what the deck can condition on (cards played
   this turn, attacks this turn, damage taken this combat) — `CombatHistory`
   already tracks these.

## Phase 3 — Decision-surface completeness — DONE

9. **Scripted `card_selector` as training default** (RL.md option 2):
   `"upgrade"` → highest-cost upgradable; `"exhaust"` → Status/Curse first;
   `"to_draw_top"` → cheapest attack. Deterministic, removes hidden
   stochasticity. Keep the two-phase on-policy env (RL.md option 4) as a later
   project only if selection-heavy cards become central to the training deck.

   Landed as `sts2_rl/selectors.py::scripted_card_selector` — a pure function
   of `(purpose, candidates, count)` (stable sorts over the offered order; no
   RNG, no state reads; X-cost ranks as the most expensive; unknown purposes
   keep the offered order). `"curse_of_knowledge"` picks the least crippling
   of the Knowledge Demon's pair (Sloth < Mind Rot < Disintegration <
   Waste Away — dodge Disintegration except against the energy loss, never
   stack two Disintegrations). Installed by
   `STS2FullCombatEnv` by default; `card_selector=None` opts back into the
   engine's seeded-random selection, any callable substitutes a policy.
   Tests in `test/test_selectors.py`.

## Phase 4 — Verify the model can actually use the numbers — DONE

10. **Observation pin tests:** constructed combats with fixed RNG asserting
    exact feature values, including the modifier previews (and the
    preview==reality property test from step 2).
11. **Lethal-arithmetic probe suite:** scripted micro-scenarios where optimal
    play requires exact numbers — enemy at 6 HP (Strike lethal, take it even
    eating a hit) vs 7 HP (Defend instead); incoming 12 vs 11 against 12 HP
    remaining; Weak/Vulnerable variants. Run the trained policy over the suite
    in `eval.py`; report probe accuracy as a first-class metric alongside win
    rate. This *measures* numeric grasp instead of inferring it from win rate.
12. **Ablation:** baseline-obs vs enhanced-obs on the same seeds/encounter
    pool; compare win-rate curves and probe accuracy so each obs change is
    justified by evidence.

Landed (2026-07-07):

- **Named observation layout** (`full_env.obs_segments` / `obs_slices`):
  a segment-name → slice map over the flat obs, so pin tests and the ablation
  address feature groups by name instead of magic indices. A pin test sums
  the segments against the probe-measured obs dimension, so layout/`_build_obs`
  drift fails loudly. No schema change — pure metadata.
- **Step 10** → `test/test_obs_pins.py`: exact-value pins for player vitals,
  intent previews through the modifier pipeline (Weak 15→11, block absorption
  per hit, Vulnerable-on-player 15×0.75×1.5→16, multi-hit 6×2 vs 4 block → 8),
  card numbers (Strike/Defend, Dexterity moving effective-but-not-base block),
  the damage matrix under Strength→Vulnerable ordering ((6+3)×1.5→13), pile
  histograms, and a preview==HP-actually-lost check through `env.step`.
- **Step 11** → `sts2_rl/probes.py`: 8 probes in 4 single-number pairs
  (enemy 6 vs 7 HP; telegraphed 12 vs 11 against 12 HP; Vulnerable present vs
  absent on a 9-HP enemy; player Weak vs not against a 5-HP enemy), each a
  one-dummy combat with hand=[Strike, Defend] and 1 energy, checked on
  turn-level outcomes (won untouched / survived / raced). `lethal_oracle` is
  the scripted numerate ceiling (verified 8/8; masked-random ~4/8);
  `test/test_probes.py` proves the suite is deterministic, solvable, and
  discriminating. Runners in `sts2_rl/evaluation.py`; the existing root
  `eval.py` grew a full-env mode — `py eval.py MODEL --env full [--ablated]
  [--baselines]` — reporting win rate and probe accuracy side by side (the
  PyTorch-2.12 load shim is untouched).
- **Step 12** → `full_env.AblatedObsEnv` (zeroes the Phase-1 absolute-number/
  preview features via `numeric_obs_indices`; same shape, same dynamics) +
  `py test/ablation.py`: trains full vs ablated MaskablePPO arms on identical
  seeds/hyperparameters and reports win-rate curves + final win rate + probe
  accuracy for both. Running the actual training comparison is an on-demand
  experiment, not part of the test suite.

## Architecture — the entity/embedding model (models.py) — DONE

The flat obs is dominated by sparse one-hots over capacity-padded
vocabularies (vocab.py: cards 640, relics 336, powers 288, monsters 144,
potions 80, events 96, purposes 24 — live counts far smaller), so a flat MLP
burns ~97% of its parameters on first-layer rows that rarely fire (column
layout: 29,190 floats, 15.4M params). `EntityActorCritic`
(`train_torch.py --arch entity`) replaces it, **model-side only** (strategy
(a) of prompts/embedding-model.md): env obs layouts, schema versions, action
spaces, and the PPO loop are all unchanged.

- **Per-segment encoders over the unchanged flat obs.** The model is built
  from the env's named layout (`obs_segments`; for the run-scale envs the
  trainer expands the trailing combat block via `train_torch.
  env_obs_segments`). `_SegmentEncoder` classifies each segment by name
  suffix + width (`models._segment_plan`): vocabulary segments multiply into
  embedding tables (a one-hot × table is a bias-free Linear over that slice;
  histograms become sums of embeddings — the right set pooling), everything
  else passes through raw. Column layout: 29,190 floats → 1,906 dense
  features.
- **One shared table per vocabulary kind**, `num rows = capacity(kind)`, so
  row *i* means frozen vocab id *i* forever and porting content appends rows
  without reshaping weights (same contract as the obs). The card table
  serves hand one-hots, draw/discard/exhaust/deck/select histograms, and
  shop/reward rows; base/upgraded status in the `2 × N_CARDS` histograms
  enters as a 2-row modifier table. Powers use 3 rows per id, matching the
  (presence, ±10, ±50) obs triples. Actor and critic keep fully separate
  encoders + trunks, mirroring the MLP baseline.
- **Checkpoints are arch-stamped** (`arch: "mlp" | "entity"`;
  `train_torch.check_checkpoint`): a checkpoint trained on one arch is
  refused by the other with a clear message — switching arch is a deliberate
  full retrain, there is no weight migration.
- **Measured (column layout, CPU):** 1.55M params vs 15.43M (first layer
  1.06M vs 14.95M); minibatch fwd+bwd(B=512) 93 ms vs 138 ms; rollout
  fwd(B=8) 8.2 ms vs 5.6 ms (per-segment Python overhead dominates at tiny
  batches — rollout inference is ~7% of an iteration, env stepping ~79%).
  Rollout obs buffers stay 29k floats by design; shrinking them is strategy
  (b) (env-side integer obs, both schema bumps), only worth doing if
  buffer/copy cost is ever the proven bottleneck.
- Tests: `test/test_models.py` (shapes, mask correctness, table sizes ==
  capacities, seed determinism, checkpoint round-trip + arch refusal).
  A/B: `py train_torch.py --env column --arch mlp|entity --fresh --save ...`.

## Reward (minor, alongside training runs)

- Enable a small `enemy_hp_reward_scale` for multi-encounter pools; normalize
  by the encounter's total starting HP rather than the arbitrary `/100`.

## Constraints

- Never mutate engine state from the env; previews must be pure reads /
  hook queries (no `DamageCmd` side effects).
- Keep the probe-measured obs-dim construction pattern.
- `py -m pytest test/ -q` must pass; new engine helpers get tests per repo
  convention (CLAUDE.md).
