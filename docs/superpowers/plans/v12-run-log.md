# v12 run log — run-only extension of the v11 rebuild (script: train_curriculum_v12.ps1)

Continue `runs/sts2_run_torch_v11_s13.pt` (+8M, asc 10, run env only, no
combat stage — a run→combat warm-start would drop every run-only head and
erase the v11 reset's gains). v11 answered THE question (REST_SMITH revived:
104 upgrades/356 rest visits) but ended under-trained (floor 14.24, train
ep_ret still rising). v12 buys the capability recovery. Rewards = v11
rebuild's, incl. `--reward-elite-attempt 1` (Perry raised the planned 0.2;
s13's first 4M trained without the term entirely). No masks, ever.

## Launch

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -m pytest -q     # green first (test_train_io/test_live_onnx known-excluded)
.\train_curriculum_v12.ps1                # s14 8M; auto-evals (150 eps asc 10 + asc 0)
# crash recovery: .\train_curriculum_v12.ps1 -Resume
```

## Knobs / why

| Why | Knob |
|---|---|
| v11 rebuild rewards carried unchanged | upgrade 1.5, elite 3, boss 3, potion k 0.15, λ0.98 + aux 0.25, ent FLAT 0.01, lr 3e-4 |
| elite pathing: entry credit, win or lose (`elites` counts wins only — deaths at elites were invisible and unrewarded) | `--reward-elite-attempt 1`; below ~12.5% HP the +1 exceeds the remaining death penalty (4·φ(r)) — watch the elite-diving signal below |
| heads live, only the reward delta (attempt 0→1) needs re-pricing | `--critic-warmup 8` (v10 same-kind-extension precedent, not v11's 15) |

## Gates (reference = v11 s13 evals, runs/eval_v11_s13_asc{10,0}.episodes.csv)

| Stage | Gate | Result | Verdict |
|---|---|---|---|
| s14 (150 eps, asc 10) | **rest-upgrade share SURVIVES: rest_upgrades/visits ≥ 0.15** (v11 s13: 0.292 — decay toward 0 as capability recovers = heal-farm equilibrium re-forming, reward balance needs another look); floor ≥ 20.1 (v11 s13: 14.24; v10 s10's 22.26 is the report line); energy_unspent/turn ≤ 0.25 report vs 0.531; truncations < 40/150 | share **0.050** (24/479 — collapsed from 0.292); floor 18.25 (p10 7, med 16, p90 31); energy 0.120; trunc 11/150 | **FAIL** — exactly the predicted heal-farm re-forming; floor gate also missed but recovering, ep_ret still inching up (16.98 last-50 vs 16.15 prev-50) |
| s14 (150 eps, asc 0) | win ≥ 3.3% (v11 s13: 1.33%); floor report vs 23.73 / v9's 31.44; rest share report (v11 s13: 0.173) | win 2.00%; floor 27.29 (med 31, p90 45); rest share 0.048 (37/767) | FAIL (improved vs v11, still under v9-era 3.3%) |
| elite diving (both arms) | report-only, NEW `elites_fought` column: elites_fought/ep vs elites/ep (wins) — a large fought−won gap concentrated at low HP means the +1 entry pay is teaching suicide-pathing → drop toward 0.2 | asc10 fought 1.66 vs won 1.35 (gap 0.31/ep, 46 eps); asc0 gap 0.15. Losing eps' hp_ratio_mean 0.820 vs 0.818 overall (asc0: 0.882 vs 0.868) — NOT low-HP-concentrated | PASS — no suicide-pathing; keep attempt reward at 1 |
| potions (both arms) | report-only at k 0.15 (v11 s13: 0.12/0.20 used/ep, timing ≈ random) | used/ep 0.16 (asc10) / 0.31 (asc0); mean use HP 0.92–0.95 → drunk at near-full HP, timing still unlearned | unchanged — k 0.15 not moving behavior |

## Contingencies

- Rest share collapses toward 0 while floor recovers: the heal-farm
  equilibrium is re-forming under capability pressure — revisit reward
  balance (upgrade vs heal shaping), do NOT re-run a combat detour for this.
- Floor still < 20.1 with ep_ret plateaued: capability ceiling under these
  rewards — profile before adding steps (more budget only helps while the
  curve still climbs).
- elites_fought − elites gap large and low-HP-concentrated: reduce
  `--reward-elite-attempt` (1 → 0.2) and resume.
- ep_ret −50% from stage start, unrecovered in 100 iters → restart from
  previous ckpt, warmup doubled, lr halved (standing rule from v8).

## Log

- 2026-08-14: v12 script created (v11 minus the combat stage, s14 = +8M
  run-only continuation of v11_s13, `--resume` handoff — deliberately NOT
  `-WarmStart`). Awaiting Perry's launch.
- 2026-08-15: s14 COMPLETE (iters 122→365, 12.0M cumulative steps) and
  evaluated. **Primary gate FAIL**: asc-10 rest-upgrade share 0.050
  (24/479) — the v11 revival decayed 0.292→0.05 as capability recovered,
  i.e. the heal-farm equilibrium re-formed exactly as the contingency
  predicted. Per contingency: revisit reward balance (upgrade vs heal
  shaping), do NOT re-run a combat detour. Secondary: asc-10 floor 18.25
  (< 20.1 gate but well up from v11's 14.24), asc-0 win 2.00% (< 3.3%,
  up from 1.33%), asc-0 floor 27.29 (> v11's 23.73). Energy 0.120 ✓,
  trunc 11/150 ✓. Elite-diving check PASSES cleanly (gap 0.31/ep not
  HP-concentrated) — `--reward-elite-attempt 1` is safe to keep. Potions
  unchanged: 0.16–0.31 used/ep at 0.92–0.95 HP (drunk near-full, timing
  unlearned). ep_ret still creeping up at end (16.15→16.98 last 100
  iters) — not hard-plateaued, but the rest-share collapse is the
  standing issue, not step count.
