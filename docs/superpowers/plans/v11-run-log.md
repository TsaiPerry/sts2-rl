# v11 run log — combat detour + reward rebalance (spec: 2026-08-14-v11-combat-detour-design.md; plan: 2026-08-14-v11-combat-detour.md)

Round trip run→combat→run from `runs/sts2_run_torch_v10_s10.pt` (+6M, asc 10).
The combat→run warm-start fresh-initializes every run-only head (campfire menu
included) — a structural reset for the dead REST_SMITH logit that no reward
scalar could revive (v9 s8/s9: 0/1538 rest visits; v10 s10: 0/194 with ent
flat + k 0.5 + λ0.98 + aux). Rewards rebalanced: upgrade 0.5→1.5, elite
0.5→3, NEW --reward-boss 3 (final win pays 12+3), potion k rolled back to
0.15. Supersedes the never-run v10 s11-lowshare rung. No masks, ever.

## Launch

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -m pytest -q     # green first (test_train_io/test_live_onnx known-excluded)
.\train_curriculum_v11.ps1                # s12 2M combat + s13 4M run; auto-evals s13
# crash recovery: .\train_curriculum_v11.ps1 -Resume
```

## Corpus (regenerate if runs/v8_start_snapshots.jsonl ever changes)

`runs/v11_eliteboss_snapshots.jsonl` = schema header + the 195 rows of
`runs/v8_start_snapshots.jsonl` whose `encounter_id` ends `_elite` (90 rows,
12 encounters) or `_boss` (105 rows, 12 encounters). Filter (Git Bash):

```bash
cd /c/Users/Perry/Desktop/sts2-rl && .venv/Scripts/python.exe - <<'EOF'
import json
kept = 0
with open('runs/v8_start_snapshots.jsonl') as src, \
     open('runs/v11_eliteboss_snapshots.jsonl', 'w') as out:
    for line in src:
        d = json.loads(line)
        if 'snapshot_schema' in d:
            out.write(line)          # schema header: preserved verbatim
            continue
        e = d.get('encounter_id') or ''
        if e.endswith('_elite') or e.endswith('_boss'):
            out.write(line)
            kept += 1
print('kept', kept)
EOF
```

Expected: `kept 195`.

## Knobs / why

| Why | Knob |
|---|---|
| REST_SMITH logit dead — scalars falsified (v10 s10 gate) | the s12↔s13 warm-start round trip itself: fresh run heads = near-uniform campfire sampling |
| upgrade credit must outbid the heal habit the fresh head will re-learn | `--reward-upgrade 1.5` (was 0.5), `--reward-elite 3` (was 0.5), `--reward-boss 3` (new; act-boss kill = act_index advance; final win pays 12+3) |
| price-knob experiment over (two doublings, no timing signal) | `--potion-potential-scale 0.15` (Perry's rollback from 0.5) |
| long-horizon credit for rest/potion timing (kept from v10) | s13 `--gae-lambda 0.98` + `--aux-hp-coef 0.25`; s12 keeps combat defaults |
| fresh heads + rescaled returns | s13 `--critic-warmup 15`, ent FLAT 0.01, lr 3e-4 |
| elite wins are the only elite credit — pathing onto an elite and dying earned nothing toward the choice (v11.1, added before the s13 extension) | `--reward-elite-attempt 0.2`: +0.2 once per elite room ENTERED, win or lose; new `elites_fought` eval column (attempts) beside `elites` (wins — deaths at elites were invisible to it) |

## Gates (reference = v10 s10 / v9 s9 / v8 s7 evals)

| Stage | Gate | Result | Verdict |
|---|---|---|---|
| s12 (train CSV, report-only) | drill `ep_ret` rising; `win` on drill fights rising. No run-scale eval — the ckpt is combat-kind | ep_ret quarters 0.28→0.33→0.45→0.42; drill win 60.7%→67.7% (61 iters) | **PASS** (report-only) |
| s13 (150 eps, asc 10) | **rest_upgrades > 0 — THE question** (any nonzero = the reset worked); floor ≥ 20.1 (recovery to v9 s9; v10 s10's 22.26 is the report line, not the gate); `aux` CSV column falling over s13 (checkable post-hoc since the v10 session added it) | **rest_upgrades 104 / 356 rest visits (29.2%; 54/150 eps smith ≥once)** — first nonzero after v9 s8, v9 s9 (0/1538), v10 s10 (0/194); floor 14.24 (elites 0.80, hp_lost/floor 8.12 ✓≤8.4, energy_unspent/turn 0.531, 40/150 truncated at step cap); aux FLAT 0.041→0.044 over 122 iters (wired, nonzero, plateaued — report-only) | **rest gate PASS / floor gate FAIL** — reset worked; rebuild under-trained at 4M (train ep_ret still rising 17.5→18.5 in the last quarter) |
| s13 (150 eps, asc 0) | win ≥ 3.3% (v8 s7 level; v9 s9: 1.33%); floor report vs 31.44 | win 1.33% (2/150, = v9 s9); floor 23.73; rest_upgrades 112/649 visits (17.3%; 57/150 eps); elites 0.86, hp_lost/floor 7.56, energy 0.410, 14 truncated | **FAIL** (same under-trained story as asc-10) |
| potions (both arms) | report-only at k 0.15: potions_used/ep and hp_at_use vs hp_overall — no gate, the price-knob experiment is over | asc-10: got 4.62/used 0.12/ep, hp_at_use 0.771 vs overall 0.819; asc-0: got 8.36/used 0.20/ep, hp_at_use 0.857 vs 0.876 — drinks near-zero, timing still ≈random | reported (fresh potion-adjacent run heads; judge after any s13 extension) |

## Contingencies

- s13 STILL shows exactly 0 rest upgrades: with fresh heads and a 3× upgrade
  reward the failure is provably not exploration or reward scale — next is
  snapshot-seeded RUN starts (the v8 `--start-snapshots` machinery,
  run-scale port), planned as its own piece of work. Never masks.
- s13 floor badly under 20.1 at budget end: the rebuild ran out of steps —
  extend s13 (`-Resume` after raising `-S13Steps`) before concluding anything.
- ep_ret −50% from stage start, unrecovered in 100 iters → restart stage
  from previous ckpt, warmup doubled, lr halved (standing rule from v8).

## Log

- 2026-08-14: plan + `--reward-boss` + corpus + script implemented and
  staged (smoke exit 0, both cross-kind warm-starts confirmed). Awaiting
  Perry's launch.
- 2026-08-14 (run complete): **THE question answered YES — the combat-detour
  head reset revived REST_SMITH** (104 upgrades/356 visits asc-10, 112/649
  asc-0, after three straight generations of exactly 0; the structural-
  exploration diagnosis from v10 is confirmed). Floor/win gates FAIL (14.24
  vs ≥20.1; 1.33% vs ≥3.3%) with every under-trained signature: train ep_ret
  still rising at budget end, energy_unspent 0.53 (fresh actor.0 combat
  execution), 40/150 step-cap truncations (menu dithering), potions ~0.1/ep.
  This is the run log's second contingency, not a falsification — next step
  per ladder: extend s13 (`.\train_curriculum_v11.ps1 -Resume -S13Steps
  8000000` = +4M more) and re-gate; the rest-upgrade share to WATCH is
  whether it survives the extension (if it decays back toward 0 as capability
  recovers, the heal-farm equilibrium is re-forming and the reward balance
  needs another look). Perry decides; nothing launches itself.
  Eval-harness note: eval.py's run-scale masked-random arm was removed
  mid-eval-phase (halves eval wall time) — the asc-10 CSV still carries 150
  masked-random rows (old code), the asc-0 CSV is policy-only; `--baselines`
  is now inert for run-scale envs.
- 2026-08-14 (v11.1, pre-extension): `--reward-elite-attempt` env term +
  `elites_fought` attempts counter implemented, tested (8 new tests, suite
  5103/4xf) and staged; `$runRewards` in the v11 script now carries
  `--reward-elite-attempt 0.2`, so the s13 EXTENSION trains under it while
  s13's first 4M did not (mid-stage reward change, deliberate — the critic
  re-prices a +0.2-per-elite-room delta quickly at this scale). The eval
  CSV gains `elites_fought` after `elites`; pre-v11.1 CSVs lack the column,
  so elite ATTEMPT comparisons only exist from the extension's evals
  onward. A combat re-drill was considered for elite frequency and
  rejected: any run→combat warm-start drops ALL run-only heads and would
  erase exactly the run-decision knowledge (rest smithing included) this
  run just bought.
- 2026-08-14 (v12): the s13 extension is now its own script/tag —
  `train_curriculum_v12.ps1` (s14 = +8M run-only continuation of
  `sts2_run_torch_v11_s13.pt`, no combat stage, `--resume` handoff, warmup
  8) with gates in v12-run-log.md. Perry also raised
  `--reward-elite-attempt` to 1 (from the planned 0.2) in both scripts'
  reward arrays; the low-HP crossover arithmetic (entry pay vs remaining
  death penalty, ~12.5% HP at +1) is recorded there and in the v12 log's
  elite-diving report gate. The v11 tag is CLOSED — nothing further runs
  under it.
