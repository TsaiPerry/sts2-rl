# v13 run log — hand-launched +20M extension of v12_s14 (no script)

Perry launched s15 directly with train_torch.py (from PSReadLine history,
2026-08-15): `--resume runs/sts2_run_torch_v12_s14.pt --timesteps 20000000`,
rewards identical to v12 s14 **except `--reward-elite 2` (down from 3)**;
everything else verbatim (upgrade 1.5, boss 3, elite-attempt 1, potion k
0.15, knee-cap, death-expiry, λ0.98 + aux 0.25, ent FLAT 0.01, lr 3e-4,
critic-warmup 8). Ran iters 366→975, 12.0M→32.0M cumulative steps. No
auto-evals; the 150-ep pair was run post-hoc (2026-08-15,
`runs/eval_v13_s15_asc{10,0}.*`).

## Training curve (octiles)

ep_ret 17.2 → 18.2, still inching up at budget end (soft plateau, same
shape as v12). upgrades/ep rose steadily 2.43 → 2.88. Entropy flat ~0.53,
aux 0.0443 → 0.0415. Potion use dipped to ~0.03/ep mid-run, partial
recovery to ~0.13 by the end.

## Gates (reference = v12 s14 evals; gates inherited from v12-run-log.md)

| Gate | v12 s14 | v13 s15 | Verdict |
|---|---|---|---|
| asc-10 rest-upgrade share ≥ 0.15 | **0.050** | **0.263** (138/525 visits, 75/150 eps) | **PASS — recovered to v11-revival level (0.292); the v12 collapse was TRANSIENT under-training, not a stable heal-farm equilibrium** |
| asc-10 floor ≥ 20.1 | 18.25 | 19.41 (p10 10, med 16, p90 31) | FAIL, narrowing; v10's 22.26 still the report line |
| asc-0 win ≥ 3.3% | 2.00% | **3.33%** (5/150) | **PASS** — first time back at the v6/v8 line since the reward redesigns began |
| asc-0 floor (report) | 27.29 | **32.36** (med 31, p90 45) | ALL-TIME HIGH — beats v9's 31.44 |
| asc-0 rest share (report) | 0.048 | 0.174 (164/943) | = v11's 0.173 |
| energy_unspent/turn ≤ 0.25 | 0.120 | 0.141 / 0.169 (asc10/asc0) | PASS |
| truncations < 40/150 | 11 | 7 / 3 | PASS |
| elite diving (report) | gap 0.31/ep, not HP-conc. | gap 0.25/ep (asc10), losers' hp_ratio 0.794 vs 0.801 overall; asc0 gap 0.12 | clean — elite 2 + attempt 1 not teaching diving |
| potions (report) | 0.16–0.31/ep at 0.92–0.95 HP | **0.11–0.21/ep at 0.97–1.01 HP** | still unlearned; slightly WORSE — drinks at effectively full HP |

## Reading

- THE correction: v12's rest-share 0.050 looked like the heal-farm
  equilibrium re-forming (the named contingency). v13 shows it was a
  transient dip — the share recovered to 0.263 with nothing but more
  steps and the elite 3→2 trim. The v12-run-log contingency ("revisit
  reward balance") was never executed and is no longer indicated.
  Confound: elite 3→2 and +20M steps changed together, so the trim's
  causal share is unknown.
- Capability is the best yet at asc-0 (win gate met, floor record);
  asc-10 floor 19.41 is 0.7 short of gate with the train curve still
  rising — the same "more budget still helps" shape as v12's end.
- Potions are the one flat-out dead term: k 0.15 + death-expiry has
  produced near-zero use at near-full HP across three generations.
  Next lever should target timing directly, not price.

## Log

- 2026-08-15: s15 complete (iters 366→975, 32.0M cumulative). Evals run
  post-hoc, gate table above filled. Best asc-0 model to date
  (`runs/sts2_run_torch_v13_s15.pt`).
