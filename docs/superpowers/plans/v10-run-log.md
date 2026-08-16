# v10 run log — escape and settle (plan: 2026-08-13-v10-escape-and-settle.md)

Extension from `runs/sts2_run_torch_v9_s9.pt` (+5M, asc 10). Ladder knobs:
potion k 0.3→0.5 (raise the bar) + s10 ent genuinely FLAT 0.01, with a
mid-script rest-upgrade gate (exit 3) so a failed escape can never anneal
into a wasted settle again. No masks, ever.

## Launch

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.\train_curriculum_v10.ps1          # ~2.5h; auto-evals; STOPS (exit 3) if s10 gate fails
# crash recovery / post-gate-fix continue: .\train_curriculum_v10.ps1 -Resume
```

## Knobs / why

| Why | Knob |
|---|---|
| long-horizon: credit half-life ~14 decisions (γλ=0.949) delegated rest/potion judgment to an uninformed critic | `--gae-lambda 0.98` (both stages) + aux head `--aux-hp-coef 0.25`: supervised "hp lost next 3 floors" off the shared encoder (spec 2026-08-13-aux-hp-head-gae-lambda-design.md) |

## Gates (reference = v8 s7 + v9 s9 evals, runs/eval_{v8_s7,v9_s9}_asc*.episodes.csv)

| Stage | Gate | Result | Verdict |
|---|---|---|---|
| s10 (50 eps, asc 10) | rest_upgrade_rate > 0 (ANY nonzero — enforced by the script, exit 3); potions_used/ep ≥ 0.4 (v9 s8: 0.10); hp_at_use < hp_overall (v9 s8: 0.96 vs 0.69); aux_loss (train log) falling over s10 — report-only wiring sanity; flat = broken plumbing, fix before s11 | rest_upgrades 0 / 194 rest visits (3.88/ep, 100% heals); potions_used 0.16/ep (DOWN from v9 s9 0.20); hp_at_use 0.846 ≈ hp_overall 0.820 (timing still random); aux_loss UNVERIFIABLE post-hoc (console-only, not in the iter CSV — add before next stage). Capability side: floor 22.26 (v9 s9 20.13), elites 1.16, hp_lost/floor 8.20, energy_unspent/turn 0.158 | **FAIL** (script exit 3 as designed; s11 not run; ckpt `runs/sts2_run_torch_v10_s10.pt` @ iter 913) |
| s11 (150 eps, asc 10) | rest_upgrade_rate ≥ 0.25; potions_used/ep ≥ 1.0 (v9 s9: 0.20); hp_at_use < hp_overall; energy_unspent/turn ≤ 0.15 (v9 s9: 0.178 — the anneal must claw this back); no regression vs s7: mean floor ≥ 21.0 (v9 s9: 20.13), elites/ep ≥ 1.0 (v9 s9: 0.97), hp_lost/floor ≤ 8.4 (v9 s9: 8.48) | | |
| s11 (150 eps, asc 0) | win ≥ 3.3% (v9 s9: 1.33%); mean floor ≥ 30.1 (v9 s9: 31.44 — report against both); rest/potion gates as above | | |

## Contingencies

- s10 gate trips (rest_upgrade STILL exactly 0 after a genuinely-held ent
  rung): the exploration story is falsified — entropy alone cannot reach
  REST_SMITH from this policy. Next rung: s11-lowshare = ent flat 0.01,
  same rewards + `--hp-potential-low-share 0.8` (flag exists, v10 Task 1),
  +2M. If THAT still shows 0: stop tuning scalars and bring data, not
  masks — e.g. seed a fraction of episodes from mid-run snapshots with
  upgradeable decks at low HP (the v8 `--start-snapshots` machinery,
  run-scale port needed) so REST_SMITH gets on-policy credit at least
  once. Perry's call either way. Never re-mask.
- Potions still < 0.5/ep at s11 with hp_at_use ≈ overall even at k 0.5:
  the price knob is refuted as a timing teacher (two doublings, no timing
  signal) — stop raising it; candidate next step is a state-dependent term
  (e.g. drink credit scaled by (1 − hp_ratio)) as its own planned stage.
- energy_unspent/turn > 0.15 at s11 despite the anneal: report-only unless
  it also regressed floor/elites — it tracks entropy, not capability.
- ep_ret −50% from stage start, unrecovered in 100 iters → restart stage
  from previous ckpt, warmup doubled, lr halved (standing rule from v8).

## Log

- 2026-08-13: plan + flag + script staged. Awaiting Perry's launch.
- 2026-08-14: Perry ran s10; **gate tripped (exit 3)**. rest_upgrades exactly 0
  after a genuinely-held ent-0.01 rung with k 0.5 + λ 0.98 + aux head — the
  scalar-exploration story for REST_SMITH is now falsified per the ladder.
  Potion price knob at two doublings: use rate fell (0.20→0.16/ep) with
  hp_at_use ≈ overall — s10 evidence already points at the "price knob
  refuted as a timing teacher" branch (formally conditioned at s11).
  General capability improved (floor 20.13→22.26 asc-10). Next rung per
  ladder = s11-lowshare (ent flat 0.01, same rewards, `--hp-potential-low-share
  0.8`, +2M from `sts2_run_torch_v10_s10.pt`); the post-scalar escalation
  (snapshot-seeded episodes with upgradeable decks at low HP) is queued
  behind it. Perry decides; nothing launches itself. Wiring note: `aux=`
  never reached the iter CSV (console-only) — add it before the next stage
  so the report-only sanity gate is checkable post-hoc.
- 2026-08-14 (later): ladder rung APPLIED, staged only: script's s11 is now
  **s11-lowshare** (ent FLAT 0.01, +2M, `--hp-potential-low-share 0.8`,
  same rewards + λ0.98 + aux 0.25, seed `sts2_run_torch_v10_s10.pt`); the
  tripped gate call retired (comment kept), s10 eval skip-guarded so
  `-Resume` goes straight to the rung; `aux` column added to the training
  CSV (NaN when coef 0) so the sanity gate is checkable next time. The s11
  gate row above reinterprets under the rung: rest_upgrade gate is ANY
  nonzero (the rung's question), the energy ≤0.15 and rest_upgrade ≥0.25
  targets were anneal-dependent settle gates — report-only until a future
  settle stage. Launch = `.\train_curriculum_v10.ps1 -Resume` (Perry).
- 2026-08-14 (later still): the staged s11-lowshare rung is RETIRED before
  running — superseded by v11 (spec 2026-08-14-v11-combat-detour-design.md,
  run log v11-run-log.md): the reward rebalance (upgrade 1.5 / elite 3 /
  boss 3) invalidates the rung's single-knob premise, and the combat-detour
  warm-start round trip is the structural exploration fix the ladder's
  post-scalar escalation called for. `train_curriculum_v10.ps1` stays as the
  historical record; nothing further runs under the v10 tag.
