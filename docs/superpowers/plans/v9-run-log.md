# v9 run log — rest + potion fix (plan: 2026-08-12-v9-rest-potion-fix.md)

Extension run from `runs/sts2_run_torch_v8_s7.pt` (+10M steps, asc 10). Two
env-side reward fixes: rest-heal shaping capped at the knee
(`--rest-heal-shaping-knee-cap`) and death-only potion expiry
(`--potion-death-expiry`). No masks, ever.

## Launch

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.\train_curriculum_v9.ps1          # ~4.5h; auto-evals after s8 and s9
# crash recovery: .\train_curriculum_v9.ps1 -Resume
```

## Gates (reference = the s7 eval, runs/eval_v8_s7_asc{0,10}.episodes.csv)

| Stage | Gate | Result | Verdict |
|---|---|---|---|
| s8 (50 eps, asc 10) | rest_upgrade_rate > 0 (attractor escaped — ANY nonzero); potions_used/ep ≥ 0.4; energy_unspent/turn ≤ 0.15 held | rest_upgrade_rate 0.000 (0 of 169 visits, 169 heals); potions_used/ep 0.10 (hp_at_use 0.96 vs hp_overall 0.69 — drinks at full HP); energy_unspent/turn 0.165 | **FAIL** (0/3) |
| s9 (150 eps, asc 10) | rest_upgrade_rate ≥ 0.25 unmasked; potions_used/ep ≥ 1.0; hp_at_use < hp_overall; energy_unspent/turn ≤ 0.15; no regression vs s7: mean floor ≥ 21.0, elites/ep ≥ 1.0, hp_lost/floor ≤ 8.4 | rest_upgrade_rate 0.000 (0 of 524 visits, 524 heals); potions_used/ep 0.20; hp_at_use 0.791 vs hp_overall 0.796 (technically <, but ≈ equal — drink timing is random); energy_unspent/turn 0.178; floor 20.13 (s7: 20.95), elites/ep 0.97 (s7: 1.03), hp_lost/floor 8.48 (s7: 8.43) — mild regression on all three | **FAIL** (1/7, and that 1 is marginal) |
| s9 (150 eps, asc 0) | win ≥ 3.3% (v6/s7 level); mean floor ≥ 30.1; rest/potion gates as above | win 1.33% (2/150; s7: 5/150); mean floor 31.44 (s7: 30.14) PASS; rest_upgrade_rate 0.000 (0 of 845 visits); potions_used/ep 0.36 (s7: 0.21 — up, still far under 1.0); hp_at_use 0.878 vs hp_overall 0.899; energy_unspent/turn 0.157; potions_expired/ep 0.03 (s7: 0.19 — death expiry did bite) | **FAIL** (floor gate only) |

Gimmick-probe gate: DROPPED for v9 (run-kind ckpts can't drive the combat
env — checkpoints.py:235; open tooling gap, applies to v6/v8 equally).

## Contingencies

- s8 eval shows rest_upgrade still exactly 0 → the fix landed but the policy
  can't find the action: hold ent at 0.01 through s9 (drop -EntCoefFinal),
  +2M on s9. If STILL 0 after that: expose `--hp-potential-low-share` and run
  0.7→0.8 (steeper danger zone) as s10. Never re-mask.
- Potions still < 0.5 uses/ep at s9: check hp_at_use first. If at_use ≈
  overall (drinks exist but are random), k 0.3→0.5 (raise the bar); if uses
  simply stay near zero despite the death expiry, k 0.3→0.15 (lower the
  friction). One knob per follow-up stage.
- ep_ret −50% from stage start, unrecovered in 100 iters → restart stage from
  previous ckpt, warmup doubled, lr halved (standing rule from v8).

## Log

- 2026-08-12: plan + env fixes + script staged. Awaiting launch.
- 2026-08-13: run COMPLETE (s8 iter 701, s9 iter 853, ~10M steps). The two s9
  evals never ran from the script (Perry closed the in-flight eval; re-run
  manually from native PowerShell, same commands). ALL THREE GATES FAIL:
  rest_upgrade_rate exactly 0 at every stage (0 upgrades across 1538 policy
  rest visits over the three evals) — the knee cap landed but the policy never
  found REST_SMITH even at ent 0.01; potions 0.20/ep (asc 10) / 0.36/ep
  (asc 0) vs the 1.0 gate — death expiry DID move hoarding (potions_expired on
  asc 0: 0.19 → 0.03/ep) and asc-0 use nearly doubled (0.21 → 0.36), but
  drink timing stayed random (hp_at_use ≈ hp_overall both arms); asc-0 win
  halved 3.33% → 1.33% (2/150, inside binomial noise of 3.3%·150, but no
  gain), asc-10 floor/elites/hp_lost all a hair worse than s7. Verdict: v9
  reward fixes are directionally right on potions, inert on rests.

## Contingency applied (2026-08-13) — s10 plan, STAGED ONLY, not launched

Per the ladder above, both first rungs trigger:

1. rest_upgrade still exactly 0 → the "hold ent 0.01" rung was never actually
   exercised: s9 annealed 0.01→0.004 as scripted because gates are only
   checked post-run. s10 = +2M extension from `sts2_run_torch_v9_s9.pt`, ent
   FLAT 0.01 (no `-EntCoefFinal`), same env flags. If rest_upgrade is STILL 0
   after s10: expose `--hp-potential-low-share` and run 0.7→0.8 as s11.
   Never re-mask.
2. potions < 0.5/ep with hp_at_use ≈ hp_overall (0.791 vs 0.796 asc 10) →
   the "drinks exist but are random" branch: k 0.3→0.5 (raise the bar).

Tension flagged for Perry: the ladder's one-knob-per-stage rule was written
inside the potion branch (0.5 vs 0.15, pick one). Combining rung 1 (ent hold,
a training hyperparam) with rung 2 (k, a reward knob) in one s10 stage is two
changes at once; splitting them costs another ~2h stage. Recommendation: run
s10 with BOTH (they target disjoint failure modes and rung 1 changes no
reward), but Perry decides at launch. No script or env change staged yet —
awaiting that call.
