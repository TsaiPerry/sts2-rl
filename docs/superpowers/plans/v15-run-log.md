# v15 run log — extension, hi-HP rest metric, mid-run injection (script: train_curriculum_v15.ps1)

Continue from `runs/sts2_run_torch_v14_s16.pt` — v14's checkpoint (all-time-first
asc-10 floor gate pass 20.86, rest-upgrade share ATH 0.404, asc-0 win 3.33% and
floor 32.02 both held). v15 does two things: s17 is a pure +8M extension of
v14 s16 to confirm the first-ever floor pass is sustained and not a peak,
before touching anything; s18 then adds mid-run injection of the 9 hard-zero
cards from the v14 draft (`--deck-inject-midrun`) at a low probability, plus
new hi-HP rest metrics (`rest_visits_hihp` / `rest_upgrades_hihp`, threshold
0.65) to measure — rather than eyeball — whether rest behavior at high HP
differs from the unconditional share. s19 (linear HP-potential curve) is
decision-gated, not scheduled. No masks, ever.

Rest-behavior numbers from ANY live SpireBot session are untrusted until
Task 1's Smith-loop fix is live-verified (the loop manufactured heal-heavy
observations); sim evals are the only rest-economy evidence source this
generation.

## Launch

```powershell
cd c:\Users\Perry\Desktop\sts2-rl
.venv\Scripts\python.exe -m pytest -q     # green first (test_train_io/test_live_onnx known-excluded)
.\train_curriculum_v15.ps1 -Smoke         # NOT run this session — run this first before a real launch
.\train_curriculum_v15.ps1                # s17 +8M extension, then s18 +8M w/ mid-run injection; auto-evals (150 eps asc 10 + asc 0) per stage
# crash recovery: .\train_curriculum_v15.ps1 -Resume   (gate-abort exit code 3, resumable; s17 evals skip-if-present on retry)
```

Native PowerShell only.

## Knobs / why

| Why | Knob |
|---|---|
| confirm v14 s16's first-ever asc-10 floor pass (20.86) is sustained, not a peak, before changing anything else | s17: +8M extension of `runs/sts2_run_torch_v14_s16.pt` via `--resume`; knobs unchanged (incl. `--deck-inject runs/inject_v14.json` at prob 0.5) EXCEPT the potion-death penalty below |
| dying while holding a potion must price strictly below drinking it and dying anyway — `--potion-death-expiry` alone only nets hoard-and-die back to 0, tying it with drink-and-die (+k−k); the flat term breaks the tie | `--potion-death-penalty 0.3` (flat −0.3 per potion still held at death, stacked on the expiry forfeiture; wins/truncations uncharged). Perry's post-plan addition 2026-08-16, applied to BOTH stages — supersedes the plan's "s17 changes nothing" rule, so read s17-vs-v14 deltas (floor, win, potion counters) knowing they conflate the extension with this term |
| move the 9 cards still hard-zero after v14's starter-deck injection (burning_pact, drum_of_battle, expect_a_fight, forgotten_ritual, howl_from_beyond, pyre, rupture, second_wind, vicious) without forcing every episode through them | s18: `--deck-inject-midrun runs/inject_v15_dead.json --deck-inject-midrun-prob 0.05` (~1.5 injected packages per 30-floor run), on top of s17's ckpt |
| exact exposure accounting note (harmless at prob 0.05) | when a mid-run inject roll lands on a floor advance that resolves directly into combat, the injected card first appears in the FOLLOWING combat, not the one the floor transition triggers — combat decks are copied at combat start, before the inject is applied |
| the mid-run injection changes the env's state distribution mid-episode; heads need to re-price V under the new distribution rather than carry a stale critic forward | s18: `--critic-warmup 8` |
| gate the s17→s18 transition on measured survival, not elapsed steps | between-stage gate: `rest_upgrade_rate ≥ 0.15` AND mean floor `≥ 19.0` on s17's asc-10 episodes CSV |
| measure whether rest preference concentrates at high HP rather than eyeballing it from aggregate share | new eval columns `rest_visits_hihp` / `rest_upgrades_hihp` (threshold 0.65, `HIHP_REST_THRESHOLD` in `run_env.py`) — baseline-setting this generation, no gate |
| deliberately NOT added: a "resting refunds nothing" knob — the existing knee-cap already zeroes hi-HP heals, so a second mechanism would be redundant with (and could fight) the knee-cap rather than adding information | none — recorded here per the plan's Self-Review |

## Gates

| Stage | Gate |
|---|---|
| s17 (150 eps, asc 10) | SURVIVAL: rest-upgrade share ≥ 0.15 (v14: 0.404); floor ≥ 20.1 SUSTAINED (v14: 20.86 — first-ever pass must not be a peak); truncations < 40/150 (v14: 13). asc 0: win ≥ 3.3% (v14: 3.33%), floor report vs 32.02 |
| s17 first-class report | **hp_lost/floor vs 7.94 (asc10) / 7.30 (asc0)** — this number IS the danger-zone position; the rest-economy question is closed or opened by it, not by rest shares alone. energy_unspent/turn vs 0.199/0.233 — a further rise makes energy the v16 headline. NEW: `rest_upgrades_hihp / rest_visits_hihp` (hi-HP upgrade share, threshold 0.65) — baseline-setting this generation, no gate |
| s18 (150 eps, asc 10) | same survival gates as s17; dead-9 movement: count of the 9 with take_rate > 0 (v14: 0/9) — ANY movement is signal; report per-card like the v14 analysis |
| s18 contingency | dead-9 fully unmoved after 8M → raise `--deck-inject-midrun-prob` to 0.15 (+4M, same stage pattern); do NOT reach for action-forcing |
| s19 (DECISION-GATED, not scheduled) | linear HP curve: `--hp-potential-low-share 0.35` (+8M from s18's ckpt, `--critic-warmup 8`, everything else unchanged). Launch ONLY if, after the SpireBot Smith fix is live-verified and s17/s18 are read, the SIM evals still show hi-HP heal preference (rest_upgrades_hihp share materially below the unconditional share) OR chip-damage sloppiness persists with hp_lost/floor flat. Gates if launched: floor and win survival as above; elite gap/ep ≤ 0.3 and hp_lost/floor not rising >10% (defend-spam/passivity check). Rationale: the 0.35 knee hard-codes a danger threshold the agent's own value function contradicts (behavioral crossover ~0.6, set by its bleed rate); linear shaping prices HP uniformly and lets the critic supply the danger structure — and taxes high-HP chip damage ~2×, pressuring the sloppiness directly |

## NEXT (Perry)

- Commit the staged v15 work in both repos (this run log plus the other v15-plan files staged this session).
- Run `.\train_curriculum_v15.ps1 -Smoke` first (not exercised this session) to confirm the script before a real launch.
- Launch training: `.\train_curriculum_v15.ps1` (see Launch block above; `-Resume` for crash recovery — gate abort exits 3, resumable, s17 evals skip-if-present on retry).
- Post-run: fill in the gate table above with s17/s18 results, then decide the v16 direction between potion-timing and energy-discipline per which report line (hp_lost/floor vs energy_unspent/turn) moved more.

## Post-run handoff checklist

- [ ] After s18 passes gates: re-export the winning checkpoint for SpireBot —
  `.venv\Scripts\python.exe -m sts2_rl.live.export_onnx runs\sts2_run_torch_v15_s18.pt --out runs\v15_s18_model.onnx`
  (parity gate must pass < 1e-4), back up `D:\...\mods\SpireBot\model\model.onnx`
  (`.bak_v14_s16` suffix), copy the new export over it, hash-verify. Contract
  is unchanged (schema 12) — no contract redeploy.
- [ ] The live obs-parity diff (`compare_obs` vs a fresh PassiveDump of a
  recorded replay) is STILL the open trust item for schema 12 — it rides the
  same showcase session as Task 1 Step 6.

## Log

- 2026-08-16: v15 run log assembled (Task 6). s17/s18 have not launched yet;
  awaiting Perry's `-Smoke` check and launch per the NEXT section above.
- 2026-08-17: `--potion-death-penalty 0.3` added to `$runRewards` (both
  stages) at Perry's request; env term + CLI + tests landed and staged
  (`test_v9_rewards.py` / `test_train_io.py` additions, 6/6 green, suite at
  baseline). s17 is no longer a knob-identical A/B vs v14 s16.
- 2026-08-17: script `$py` reverted to `venv\Scripts\python.exe` (no dot) —
  the repo has TWO envs: `venv` = torch 2.13.0+cu130 (CUDA, the training
  env, no onnx), `.venv` = torch 2.13.0+cpu (plain-PyPI install 2026-08-09)
  + onnx/onnxruntime (tooling/pytest/export env). Yesterday's ".venv
  normalization" would have trained s17/s18 on CPU. Pytest and the ONNX
  export in the handoff checklist correctly stay on `.venv`.
