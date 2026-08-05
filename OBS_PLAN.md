# OBS_PLAN.md — observation/precision overhaul for STS2FullCombatEnv

**History, not a live contract.** This records the 2026-07-06 design review of
`sts2_rl/full_env.py` against the engine and the decompiled game source, and
what each of its four phases shipped. All four are DONE. Code across the repo
cites its phase/step numbers (`OBS_PLAN Phase 4, step 11`), which is why the
headings below stay.

For what the environments emit **today**, read
[OBS_SCHEMA.md](OBS_SCHEMA.md) — the normative contract. The schema numbers
this plan shipped (v2, v3) are long superseded: the flat float `Box` was
replaced by the `{"f", "i"}` Dict contract, and `OBS_SCHEMA_VERSION` is now 6
(combat) / 9 (run). For the model side, read
[RL_ARCHITECTURE.md](RL_ARCHITECTURE.md).

## Guiding principle

The agent must not see strictly *less* numeric information than a human looking
at the game screen — that would violate the repo's fidelity rule. The
decompiled source is the authority for what a player is shown:

- Intent damage: the game runs the **full modifier pipeline** for the displayed
  number — `AttackIntent.GetSingleDamage`
  (`src/Core/MonsterMoves/Intents/AttackIntent.cs:84-93`):
  `Hook.ModifyDamage(..., ValueProp.Move, ..., ModifyDamageHookType.All, ...)`.
- Card numbers: the game prints fully modified values on card faces
  (`CardModel.UpdateDynamicVarPreview` / `CardPreviewMode`).

So pipeline-accurate previews in the observation are *fidelity*, not feature
engineering. This is the part of the document that still governs.

## Phase 1 — absolute numbers — DONE

Dual HP encoding (ratio + absolutes on one shared unit for HP/block/damage),
pipeline-accurate incoming-damage previews, card base stats exposed off the
`_init_vars` values each card already stored, and effective (hook-modified)
energy cost per slot.

Landed as `sts2_rl/previews.py` — pure-read helpers replaying the DamageCmd /
BlockCmd modifier stages (`preview_incoming_damage`, `preview_total_incoming`,
`preview_card_damage` / `_block` / `_energy_cost`, `card_base_damage`), with
purity and preview==reality property tests in `test/test_previews.py`.

## Phase 2 — coverage gaps — DONE

Fixed the dead `dexterity` slot (it read a nonexistent attribute, so the agent
was blind to Dexterity), replaced the curated power lists with the full
`ALL_POWERS` vocabulary, added enemy identity, and added the history scalars
`CombatHistory` already tracked.

## Phase 3 — decision-surface completeness — DONE

`sts2_rl/selectors.py::scripted_card_selector` — a pure function of
`(purpose, candidates, count)` (stable sorts over the offered order; no RNG, no
state reads; X-cost ranks as most expensive; unknown purposes keep the offered
order). `"curse_of_knowledge"` picks the least crippling of the Knowledge
Demon's pair. Installed by `STS2FullCombatEnv` by default; `card_selector=None`
opts back into the engine's seeded-random selection, and any callable
substitutes a policy. Tests in `test/test_selectors.py`.

## Phase 4 — verify the model can use the numbers — DONE

- **Step 10** → `test/test_obs_pins.py`: exact-value pins for player vitals,
  intent previews through the modifier pipeline, card numbers, the damage
  matrix under Strength→Vulnerable ordering, and a preview==HP-actually-lost
  check through `env.step`.
- **Step 11** → `sts2_rl/probes.py`: 8 probes in 4 single-number pairs (enemy
  6 vs 7 HP; telegraphed 12 vs 11 against 12 HP; Vulnerable present vs absent
  on a 9-HP enemy; player Weak vs not against a 5-HP enemy), each a one-dummy
  combat with hand=[Strike, Defend] and 1 energy. `lethal_oracle` is the
  scripted numerate ceiling (8/8; masked-random ~4/8); `test/test_probes.py`
  proves the suite is deterministic, solvable and discriminating. Runners live
  in `sts2_rl/evaluation.py`; `py eval.py MODEL --env full [--ablated]
  [--baselines]` reports win rate and probe accuracy side by side.
  `sts2_rl/run_probes.py` is the run-scale rider added later.
- **Step 12** → `full_env.AblatedObsEnv` (zeroes the Phase-1 absolute-number /
  preview features via `numeric_obs_indices`; same shape, same dynamics) plus
  `py test/ablation.py`, which trains full vs ablated arms on identical seeds
  and hyperparameters. Running the comparison is an on-demand experiment, not
  part of the test suite.

## Architecture — the entity/embedding model — DONE, then superseded

The flat obs was dominated by sparse one-hots over capacity-padded
vocabularies, so a flat MLP burned most of its parameters on first-layer rows
that rarely fire. `EntityActorCritic` (`--arch entity`) replaced it model-side
only, reading the env's named segment layout and multiplying vocabulary
segments into shared embedding tables — one table per vocabulary kind, rows =
`vocab.py` capacities, so porting content appends rows without reshaping
weights.

**That arch no longer runs.** The v4-generation `{f, i}` Dict observation made
`--arch mlp` and `--arch entity` unusable (unnormalized ids would swamp the
numeric features), and `sts2_rl/checkpoints.py::make_model` refuses both
outright against the current envs. `--arch entset` (`EntitySetActorCritic`) is
the default and the only arch `make_model` still builds; the embedding-table
contract above carried over to it unchanged. See
[RL_ARCHITECTURE.md](RL_ARCHITECTURE.md) for the current model.

Checkpoints are arch-stamped and there is no weight migration between
architectures — switching arch is a deliberate full retrain.

## Constraints (still binding)

- Never mutate engine state from the env; previews must be pure reads / hook
  queries (no `DamageCmd` side effects).
- Keep the probe-measured obs-dim construction pattern, so the declared space
  can never drift from `_build_obs`.
- `py -m pytest test/ -q` must pass; new engine helpers get tests per repo
  convention (CLAUDE.md).
