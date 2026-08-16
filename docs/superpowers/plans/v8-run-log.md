# v8 run log — HP economy curriculum (plan: 2026-08-10-v8-hp-economy-curriculum.md)

Status 2026-08-10: Phase B′ (Tasks 1-5) + Task 6/6b complete and staged. **Training NOT launched — Perry launches** (his call, 2026-08-10). This file is the launch handoff + the per-stage gate ledger to fill in as stages complete.

## Pre-launch checklist

- [ ] Close the game / free the GPU. The script uses `venv\Scripts\python.exe` (CUDA 2.13.0+cu130) — NOT `.venv` (CPU-only torch; tests still run under `.venv`).
- [ ] Snapshot corpus present: `runs/v8_start_snapshots.jsonl` (951 snapshots, v6-checkpoint rollouts, acts 0-2). Without it the script SKIPS combat stages s0/s5 with a warning.
- [ ] Seed checkpoint: script default `-SeedCkpt runs/sts2_run_torch_v6.pt` (v6 final, iter 1110). Consider `runs/mb8_probe.iter000320.pt` if you prefer the newer probe line — same entset/head_version 4 family, both warm-startable.
- [ ] Optional final smoke: `.\train_curriculum_v8.ps1 -Smoke` (65k steps/stage; cross-kind boundaries print a `warm-start: N/M keys transferred` line — s0 and s1 should each show one).

## Launch

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.\train_curriculum_v8.ps1            # full 40M-step run (~18h at v6 throughput)
# crash recovery: .\train_curriculum_v8.ps1 -Resume   (per-stage own-ckpt resume, same semantics as v7)
```

Cross-kind boundaries (v6→s0, s0→s1, s4→s5, s5→s6) use `--warm-start` (new in Task 6b): transfers pointer heads + vocab tables + logically-matched encoder blocks, reinitializes trunk first-layers and kind-specific heads, fresh optimizer, `--critic-warmup` applies. Expect a transfer-summary log line at each.

## Per-stage eval + gates (from plan Task 7)

Eval command per completed run stage (combat stages: eval the NEXT run stage instead):
```powershell
venv\Scripts\python.exe eval.py --env run --episodes 150 --baselines --ascension <asc> --load <ckpt> --csv runs/eval_v8_s<N> --gimmick-probes
```

| Stage | Gate | Result | Verdict |
|---|---|---|---|
| s1 | elites/ep ≥ v6's; hp_lost/floor falling vs v6 at similar elite counts; rest_upgrade_rate ≥ 0.15 (UNMASKED eval); win ≥ 0.03; ≥60% pool cards taken once | | |
| s2 | act-1 boss (floor-16 wall) clear rate > s1's | | |
| s3 | ep_ret ≥70% of s2 final; upgrades/ep not declining; potions_used ≥ ~1; potions_expired not rising | | |
| s4 | same as s3 vs s3 | | |
| s6 | same vs s4 | | |
| s7 | rest_upgrade_rate ≥ 0.25 unmasked; energy_unspent/turn ≤ 0.15; elites/ep ≥ s1 with hp_lost/floor ≤ s1's; potions_used ≥ 1 with potions_expired ≤ 1.5 on DEATHS; mean hp-at-use < mean hp overall; gimmick-probe wins > v6 on all three; win rate reported honestly | asc 10 (runs/eval_v8_s7_asc10.episodes.csv, 150 eps): rest_up **0.0% FAIL**; e_unspent/turn 0.116 PASS; elites/ep 1.03, hp_lost/floor 8.43 (no s1 eval to compare); potions_used **0.10 FAIL**, expired-on-deaths 0.007 PASS; hp-at-use 0.777 vs overall 0.709 **FAIL**; gimmick probes NOT rollable from a run-kind ckpt (checkpoints.py env-kind gate; v6 same, so the >v6 comparison was never rollable — s5 combat ckpt proxy: 0% on all three at asc 10); win 0.0%, mean floor 21.0, deaths walled at median 16. asc 0 (runs/eval_v8_s7_asc0.episodes.csv): win 3.3% (= v6), mean floor 30.1 (v6 26.6), e_unspent/turn 0.145 (v6 0.228), take 89% (v6 73%), rest still 100% heal / 0% up | **FAIL** — mask-off rest collapse (plan's predicted failure mode) + never-drink potions; apply Task 7 contingencies |

v6 baseline (runs/eval_v6_iter1110.episodes.csv, 150 eps): win 3.3%, mean hp_left 0.8, 726 heal / 2 upgrade rests, take-rate 73%, 9.8 energy unspent/ep, deaths walled at floors 31 & 16.

## Rollback / contingencies (plan Task 7)

- Any stage: ep_ret −50% from stage start, unrecovered in 100 iters → restart stage from previous ckpt, warmup doubled, lr halved.
- s7 mask-off collapse to always-heal → extend s7 +2M; if persists: no-shaping-on-above-knee-rest-heals (or half-ΔΦ), and/or low_share 0.7→0.8. Never re-mask.
- Potion chugging persists (hp-at-use ≈ hp overall) → potion_potential_scale 0.3→0.5. Never-drink hoarding (uses <1/ep, deaths with full belts) → 0.15, or death-only −k/2 expiry. No potion masks, no room terms.

## Log

- 2026-08-10: Phase B′ + script + warm-start staged; smoke gates (a)-(f) settled (c LOGGED: reward_win on act-1 boss source-confirmed, not empirically observed). Awaiting Perry launch.
- 2026-08-12: run completed through s7 (final ckpt runs/sts2_run_torch_v8_s7.pt, iter 549). eval.py gained a "v8 s7 gate summary" block (+ mean_elites, hp_lost/floor, potions_expired-on-deaths, hp-at-use vs pooled run.hp_ratio proxy, hp_ratio_mean CSV column; staged). s7 evaluated at asc 0 + asc 10, 150 eps each — gate row above filled in, verdict FAIL: rest behavior collapsed to 100% heal / 0% upgrade with the mask off (the plan's predicted mask-was-doing-all-the-work mode → contingency: extend s7 +2M, then no-shaping-on-above-knee-rest-heals / low_share 0.8, never re-mask) and potions are never drunk (0.10-0.21 uses/ep, hoarding contingency: k 0.3→0.15 or death-only −k/2 expiry). Real gains vs v6 at asc 0: floor 26.6→30.1, e_unspent/turn 0.228→0.145, take 73%→89%, elites 1.10/ep, hp_lost/floor 7.43; win unchanged 3.3%. Gimmick probes: run-kind ckpts can't drive the combat env (checkpoints.py:240) — the s7 gate's "> v6" comparison needs new tooling or combat-kind exports.
- 2026-08-12 (later): s7 FAIL follow-up planned + staged as v9 — rest-heal shaping knee cap + death-only potion expiry, +10M extension from s7. See 2026-08-12-v9-rest-potion-fix.md / v9-run-log.md.
