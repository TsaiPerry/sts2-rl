# v11: Combat detour + reward rebalance — design

**Date:** 2026-08-14
**Status:** approved by Perry (approach A of A/B/C)
**Supersedes:** the staged-but-never-run v10 s11-lowshare rung (retire it in
`v10-run-log.md`; leave `train_curriculum_v10.ps1` itself untouched as the
historical record of what ran).

## Problem

v10 s10 ("escape") failed its gate: **rest_upgrades exactly 0 over 194 rest
visits / 50 eval episodes**, after 2M steps with entropy genuinely held flat
at 0.01, potion k 0.5, λ 0.98, and the aux HP head. The v9 s9 seed policy was
already 0-for-1538. REST_SMITH's sampling probability is effectively zero, so
it never gets on-policy credit, so it never recovers — held entropy can only
re-inflate an action whose probability is merely small, not one that is dead.
The scalar-exploration story is falsified; per the v10 ladder, the next step
must bring structural change, not another reward scalar.

## Mechanism: the warm-start round trip is a targeted head reset

Verified against `checkpoints.warm_start_agent` (docstring + transfer rules):

- **Kept across run→combat→run:** every vocab embedding table
  (`actor_encoder.tables.*` — card/relic/power identities), the encoder
  row-projection `_blocks.*` whose LOGICAL segment name matches on both
  sides (all combat-relevant segments), the fixed-shape combat heads
  (`play_head`/`end_turn_head`/`potion_head`), and the deeper trunk layers
  (`actor.2`/`critic.2`/`critic.4`).
- **Fresh-initialized on the combat→run hop:** every run-only head
  (`positional_heads`, run `pointer_heads`, `choice_row_overlay_heads`,
  `choice_float_overlay_heads` — the campfire heal/smith menu lives here),
  run-only encoder segments (map, shop, …), `actor.0`/`critic.0` (pooled
  width differs: 747 combat vs 3253 run), and the aux head (same width
  reason). Optimizer state and `global_step` reset at each hop (v8's
  `$prevKind` `-WarmStart` plumbing already handles this).

Consequence: the returned run policy samples the campfire menu near-uniformly
— REST_SMITH finally gets sampled and can collect reward — at the cost of
re-learning all run-level knowledge (pathing/shop behavior behind s10's
floor 22.26). That cost is accepted and budgeted (s13 = 4M steps).

## Components

### 1. `--reward-boss` (the only env code change)

- `STS2RunEnv(reward_boss: float = 0.0)` — **default 0.0 = default env
  bit-identical.**
- Fires **+reward_boss once per act boss defeated**, detected in the step
  reward block as `run.act_index` advancing past the pre-step value; the
  final boss (a win, where the act index does not advance) also pays it, ON
  TOP of `--reward-win` — a v11 win pays 12 + 3.
- Threading identical to the v10 Task 1 pattern: `EnvSpec.reward_boss=0.0` →
  `build_env` passthrough → `train_torch.py --reward-boss` (guarded run-only,
  same guard style as the other run reward flags) → `env_spec()` getattr.
- Tests mirror `test_v10_lowshare.py` (threading + bit-identical default)
  plus reward-behavior tests in the style of the existing act/floor reward
  tests: boss kill mid-run pays once, non-boss act play pays nothing, final
  win pays `reward_win + reward_boss`.

### 2. Elite/boss snapshot corpus (no env code)

- Offline filter: `runs/v8_start_snapshots.jsonl` →
  `runs/v11_eliteboss_snapshots.jsonl`.
- **Line 1 of the corpus is a schema header row (`snapshot_schema`) — it must
  be preserved verbatim.** Keep the 195 data rows whose `encounter_id` ends
  `_elite` (90 rows, 12 encounters) or `_boss` (105 rows, 12 encounters).
- The filter is a one-off inline command executed during implementation (no
  new tool file — YAGNI); the exact command is recorded in `v11-run-log.md`
  so it can be re-run if the source corpus is ever regenerated.

### 3. `train_curriculum_v11.ps1`

Helpers (`Invoke-Phase`, `Get-CkptStep`, `Invoke-Stage`, `Invoke-Eval`)
byte-copied from the v10 script; `$prevKind` warm-start tracking copied from
the v8 script. Seed: `runs/sts2_run_torch_v10_s10.pt`. Stage numbering
continues: s12, s13.

- **s12 combat drill (2M, asc 10):** `-WarmStart` from the seed, `--env
  combat --ascension 10 --start-snapshots runs/v11_eliteboss_snapshots.jsonl
  --lr 3e-4`. Native HP-delta combat reward. NO run-only flags, NO
  `--aux-hp-coef` (run-env-only guard), NO `--gae-lambda` override (combat
  episodes are short; default 0.95 stands, matching v8's drills).
- **s13 run rebuild (4M, asc 10):** `-WarmStart` from s12 (the reset
  moment). Rewards: `--floor-rewards 1.0 1.5 2.0 --reward-win 12
  --reward-upgrade 1.5 --reward-elite 3 --reward-boss 3 --reward-remove 0.25
  --reward-relic 0.25 --hp-potential-scale 4.0 --potion-potential-scale 0.15
  --rest-heal-shaping-knee-cap --potion-death-expiry` + `--gae-lambda 0.98
  --aux-hp-coef 0.25`. `--ent-coef 0.01` flat, `--critic-warmup 15`
  (fresh heads + rescaled returns), lr 3e-4.
- **Evals:** s13 at 150 eps asc-10 and 150 eps asc-0 (with `--baselines`).
  An s12 eval is meaningless in run terms (combat kind) — the s12 sanity
  check is its training `ep_ret` trend, report-only.
- Smoke mode, resume arithmetic, and the exists-guard as in v10.

### 4. `v11-run-log.md` gates

| Stage | Gate |
|---|---|
| s12 (train log) | report-only: drill `ep_ret` rising; `win` on drill fights rising |
| s13 (150 eps, asc 10) | **rest_upgrades > 0 — THE question** (any nonzero = the reset worked); floor ≥ 20.1 (recovery to v9 s9 level; s10's 22.26 is the report line, not the gate); aux column falling (now checkable post-hoc in the CSV) |
| s13 (150 eps, asc 0) | win ≥ 3.3% (v8 s7 level); floor report vs 31.4 |
| potions | report-only at k 0.15 — the price-knob experiment is over (two doublings taught nothing; Perry rolled it back) |

Contingency if s13 STILL shows exactly 0 rest upgrades: with fresh heads and
a 3× upgrade reward the failure is provably not exploration or reward scale —
next is snapshot-seeded RUN starts (the v8 `--start-snapshots` machinery,
run-scale port), planned as its own piece of work. Never masks.

## Constraints (standing)

- Stage only, never commit; Perry launches all real training (native
  PowerShell, CUDA venv); `-Smoke` allowed for script verification.
- Default env bit-identical: every new knob defaults to today's behavior.
- Tests on `.venv`; known-excluded: `test_train_io.py`, `test_live_onnx.py`.
- No masks, ever.

## Rejected alternatives

- **B — surgical head reset** (re-init run choice heads in a checkpoint copy,
  no combat stage): cheaper, keeps map knowledge, but no combat gains and
  needs new checkpoint-surgery tooling; warm-start gives the reset for free.
- **C — A + act-1-only bridge stage:** held as a contingency if s13's
  rebuild flounders, not the opening move.
- **s11-lowshare rung:** superseded before running; the reward rebalance
  invalidates its single-knob premise.
