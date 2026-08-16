# v10 Escape-and-Settle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the v9 contingency ladder — potion k 0.3→0.5 + a genuinely-held ent-0.01 escape stage — with a mid-script gate so a failed escape can never silently anneal into a wasted settle stage again, plus the `--hp-potential-low-share` CLI flag so the next rung needs no new code.

**Amendment 2026-08-13 (Perry):** Tasks 5–8 fold in the long-horizon levers from `docs/superpowers/specs/2026-08-13-aux-hp-head-gae-lambda-design.md` — GAE λ 0.95→0.98 and a supervised aux head predicting HP lost over the next 3 floors — so the v10 run carries them. **Launch is blocked until Tasks 5–8 are done** (the script gains two new flags in Task 8). Tasks 1–3 are complete; Task 4 Step 2 remains the post-run step.

**Architecture:** A +5M-step extension from `runs/sts2_run_torch_v9_s9.pt`: s10 "escape" (2M, ent FLAT 0.01, k 0.5) → automated rest-upgrade gate on the s10 eval CSV → s11 "settle" (3M, ent 0.01→0.004). The gate is the structural fix for v9's core process failure: s9 annealed entropy back down even though the s8 gate had already failed, because gates were only checked post-run.

**Tech Stack:** PowerShell curriculum script (byte-copied helpers from `train_curriculum_v9.ps1`), `train_torch.py` PPO, `eval.py`, pytest.

## Global Constraints

- **Never commit in this repo — stage only** (`git add`, no `git commit`).
- **Never launch real training** — Perry launches (`venv` CUDA GPU, ~2.5h). `-Smoke` runs are allowed for script verification.
- **No masks, ever** (v8 plan Task 7 constraint; `rest_heal_mask_above` stays unset).
- Default env must stay **bit-identical**: every new knob defaults to today's behavior.
- Tests run on `.venv\Scripts\python.exe` (CPU torch); training/eval on `venv\Scripts\python.exe` (CUDA).
- Known pre-existing failures: 4 in `test/test_train_io.py` (Perry-local), 2 in `test/test_live_onnx.py` (no onnx pkg) — exclude, don't fix.
- Launch/eval must run from **native PowerShell** (Git-Bash→powershell.exe boundary hangs multiprocessing spawns).

## Why these knobs (v9 post-run evidence, `v9-run-log.md`)

| v9 failure | v10 answer |
|---|---|
| rest_upgrade_rate exactly 0 (1538 visits, all heals) — s9 annealed ent to 0.004 before the gate was ever read, so the "hold ent 0.01" rung was never truly exercised | s10 holds ent FLAT 0.01 for its whole 2M; script **stops** before s11 if the s10 eval still shows 0 rest upgrades |
| potions 0.20–0.36/ep with hp_at_use ≈ hp_overall (drinks exist, timing random) | ladder's "raise the bar" branch: `--potion-potential-scale` 0.3→0.5 (drink price and death forfeit scale together) |
| energy_unspent/turn regressed to 0.178/0.157 (> 0.15) under held-high entropy | not a knob: s11's anneal to 0.004 is the recovery mechanism (v8 s7 under the same anneal hit 0.116); gated at s11 |
| next contingency rung (`hp_potential_low_share` 0.7→0.8) has no CLI flag | Task 1 exposes it now, default 0.7 = bit-identical, so the rung is a script-arg edit |

---

### Task 1: `--hp-potential-low-share` CLI flag

**Files:**
- Modify: `sts2_rl/vec_env.py` (EnvSpec field ~line 91, `build_env` passthrough ~line 113)
- Modify: `train_torch.py` (arg ~line 201, `env_spec()` ~line 483)
- Test: `test/test_v10_lowshare.py` (new)

**Interfaces:**
- Consumes: `STS2RunEnv(hp_potential_low_share: float = 0.7)` — already exists (`run_env.py:639`), stored as `env._hp_potential_low_share`.
- Produces: `EnvSpec(hp_potential_low_share: float = 0.7)`; `train_torch.py --hp-potential-low-share <float>`. Task 2's contingency instructions name the flag.

- [x] **Step 1: Write the failing tests**

Create `test/test_v10_lowshare.py`:

```python
"""v10 (plan 2026-08-13-v10-escape-and-settle Task 1): --hp-potential-low-share.

The env kwarg has existed since v8 (`run_env.py` `_hp_potential`); v10 only
threads it EnvSpec -> build_env -> CLI so the s11-lowshare contingency rung
(0.7 -> 0.8, steeper danger zone) is a script-arg edit, not a code change.
"""
import argparse

from sts2_rl.vec_env import EnvSpec, build_env


def test_envspec_low_share_reaches_run_env():
    env = build_env(EnvSpec(kind="run", hp_potential_low_share=0.8))
    assert env._hp_potential_low_share == 0.8


def test_envspec_low_share_default_bit_identical():
    # 0.7 is the env's own default -- a default spec must build the same env.
    assert build_env(EnvSpec(kind="run"))._hp_potential_low_share == 0.7


def test_env_spec_threads_low_share():
    import train_torch
    ns = argparse.Namespace(env="run", acts=None, card_obs="hybrid",
                            encounter=None, enemy_hp_reward=0.0,
                            win_hp_bonus=0.0, branch_prob=0.0,
                            hp_potential_low_share=0.8)
    assert train_torch.env_spec(ns).hp_potential_low_share == 0.8
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test/test_v10_lowshare.py -v`
Expected: FAIL — `TypeError: EnvSpec.__init__() got an unexpected keyword argument 'hp_potential_low_share'` (first) and `AttributeError` on the third; the default test passes trivially. (Observed exactly that: 2 failed, 1 passed. `card_obs="hybrid"` is `--card-obs`'s parse_args default.)

- [x] **Step 3: Implement**

`sts2_rl/vec_env.py`, after `potion_death_expiry: bool = False` (line 91):

```python
    # v10 (plan 2026-08-13-v10-escape-and-settle Task 1): share of the HP
    # potential below the knee. 0.7 = the env's own default, so a default
    # spec stays bit-identical; the s11-lowshare contingency rung runs 0.8.
    hp_potential_low_share: float = 0.7
```

`build_env`, inside the `v7_kwargs` dict next to `hp_potential_scale=spec.hp_potential_scale,` (line 113):

```python
        hp_potential_low_share=spec.hp_potential_low_share,
```

(Unconditional passthrough is safe: the value equals the env default when untouched, and it's inert unless `hp_potential_scale` is nonzero.)

`train_torch.py`, after the `--hp-potential-scale` argument (line 201) — also trim that argument's now-stale help text `"knee/low_share stay at the env's own defaults -- not exposed as flags"` down to `"knee stays at the env's own default"`:

```python
    ap.add_argument("--hp-potential-low-share", type=float, default=0.7,
                    help="v10: share of the HP-potential value below the "
                         "knee (env default 0.7; the s11-lowshare "
                         "contingency rung runs 0.8 -- steeper danger zone)")
```

`env_spec()`, after the `potion_death_expiry` line (line 486):

```python
        hp_potential_low_share=getattr(args, "hp_potential_low_share", 0.7),
```

Deliberately NOT added to the `--env combat` rejection guard (train_torch.py:363): its nonzero default would trip a truthiness check, the v9 booleans aren't in it either, and the knob is inert without `--hp-potential-scale`, which IS guarded.

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest test/test_v10_lowshare.py test/test_v9_rewards.py test/test_v8_rewards.py -v`
Expected: all PASS (v8/v9 files prove the default env is untouched). Observed: 46 passed.

- [x] **Step 5: Full suite, then stage**

Run: `.venv\Scripts\python.exe -m pytest -q --ignore=test/test_train_io.py --ignore=test/test_live_onnx.py`
Expected: all green. Observed: 5078 passed, 4 xfailed.

```powershell
git add test/test_v10_lowshare.py sts2_rl/vec_env.py train_torch.py
```

---

### Task 2: `train_curriculum_v10.ps1`

**Files:**
- Create: `train_curriculum_v10.ps1` (copy `train_curriculum_v9.ps1`, then apply the diffs below)

**Interfaces:**
- Consumes: `runs/sts2_run_torch_v9_s9.pt` (seed); `--hp-potential-low-share` (named in the gate-fail message only — not passed by any v10 stage).
- Produces: `runs/sts2_run_torch_v10_s10.pt`, `..._s11.pt`; `runs/eval_v10_s10_asc10.*`, `eval_v10_s11_asc10.*`, `eval_v10_s11_asc0.*`. Exit 3 = s10 rest-upgrade gate fail (s11 not run).

- [x] **Step 1: Copy the v9 script**

```powershell
Copy-Item train_curriculum_v9.ps1 train_curriculum_v10.ps1
```

`Invoke-Phase`, `Get-CkptStep`, `Invoke-Stage`, `Invoke-Eval` stay byte-identical.

- [x] **Step 2: Header + params + ckpt map**

Replace the comment header with:

```
v10 extension run (plan 2026-08-13-v10-escape-and-settle): apply the v9
contingency ladder from the s9 checkpoint, +5M steps total.

  Stage  Env  Asc  Steps  Notes
  s10    run   10     2M  escape: ent 0.01 FLAT (no anneal), k 0.5, warmup 8
  gate   --    --     --  s10 eval must show >0 rest upgrades or STOP (exit 3)
  s11    run   10     3M  settle: ent 0.01 -> 0.004 anneal, same rewards

Knob changes vs v9 (ladder, v9-run-log.md "Contingency applied"):
- --potion-potential-scale 0.3 -> 0.5 : hp_at_use ~= hp_overall at s9 =
  drinks exist but timing is random -> raise the bar (drink price and the
  death forfeit scale together; the death-expiry mechanism itself worked:
  expired-on-deaths 0.19 -> 0.03/ep).
- s10 ent is genuinely FLAT: v9's s9 annealed to 0.004 before anyone read
  the failed s8 gate. The Test-RestUpgradeGate check between s10 and s11
  makes that mistake structurally impossible now.
No rest mask, no potion mask, ever (v8 plan Task 7 constraint).

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v10.ps1                # real run (~2.5h at v9 throughput)
  .\train_curriculum_v10.ps1 -Smoke         # 65536 steps/stage, scratch tag
  .\train_curriculum_v10.ps1 -Resume        # continue an interrupted run
```

Params and checkpoint map:

```powershell
param(
    [long]$S10Steps = 2000000,
    [long]$S11Steps = 3000000,
    [string]$Device = "cuda",
    [string]$Tag = "v10",
    [string]$SeedCkpt = "runs/sts2_run_torch_v9_s9.pt",
    [switch]$Resume,
    [switch]$Smoke
)
```

- Smoke block: `$S10Steps = 65536; $S11Steps = 65536`.
- `foreach ($n in 10..11)` in the `$ckpt` map; the exists-guard checks `$ckpt[10]`.

- [x] **Step 3: Rewards — the k change**

```powershell
# v9 rewards with the ladder's one potion-knob change: k 0.3 -> 0.5 ("raise
# the bar" branch -- s9 hp_at_use 0.791 ~= hp_overall 0.796, drinks random).
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "0.5", "--reward-elite", "0.5",
                "--reward-remove", "0.25", "--reward-relic", "0.25",
                "--hp-potential-scale", "4.0",
                "--potion-potential-scale", "0.5",
                "--rest-heal-shaping-knee-cap",
                "--potion-death-expiry")
```

- [x] **Step 4: The mid-script gate + stages**

After `Invoke-Eval`'s definition add:

```powershell
# v10's structural fix: v9 wasted its whole settle stage annealing entropy
# down onto a policy that had never once upgraded, because gates were only
# read post-run. Settling is provably pointless while rest_upgrades == 0,
# so that one gate is enforced HERE. Exit 3 leaves everything resumable:
# fix per v10-run-log.md, then re-run with -Resume (s10 skips, s11 runs).
function Test-RestUpgradeGate {
    param([string]$Csv)
    if ($Smoke) { Write-Host "rest-upgrade gate skipped (smoke mode)"; return }
    $code = "import csv, sys; " +
            "rows = [r for r in csv.DictReader(open(sys.argv[1], newline='')) " +
            "if r['policy'] != 'masked-random']; " +
            "n = sum(int(float(r['rest_upgrades'])) for r in rows); " +
            "print(f'policy rest_upgrades total: {n} over {len(rows)} episodes'); " +
            "sys.exit(0 if n > 0 else 3)"
    & $py -c $code "$Csv.episodes.csv"
    if ($LASTEXITCODE -eq 3) {
        Write-Host "s10 GATE FAIL: rest_upgrade_rate still exactly 0 after the ent-hold rung." -ForegroundColor Red
        Write-Host "NOT settling (that was v9's mistake). Next rung per v10-run-log.md:"
        Write-Host "  s11-lowshare = ent flat 0.01, same rewards + --hp-potential-low-share 0.8."
        Write-Host "Perry decides; nothing launches itself."
        exit 3
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "gate check errored (exit $LASTEXITCODE) - continuing to s11" -ForegroundColor Yellow
    }
}
```

Replace the s8/s9 stage section:

```powershell
# ── s10: escape — ent held FLAT, potion bar raised ─────────────────────────
Invoke-Stage -Name "s10-run-asc10-escape" -SaveCkpt $ckpt[10] -PrevCkpt $SeedCkpt `
    -Steps $S10Steps -CriticWarmup 8 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards)
Invoke-Eval -Name "s10-eval-asc10" -Ckpt $ckpt[10] -Asc 10 -Episodes 50 `
    -Csv "runs/eval_${Tag}_s10_asc10"
Test-RestUpgradeGate -Csv "runs/eval_${Tag}_s10_asc10"

# ── s11: settle — anneal entropy back down ─────────────────────────────────
Invoke-Stage -Name "s11-run-asc10-settle" -SaveCkpt $ckpt[11] -PrevCkpt $ckpt[10] `
    -Steps $S11Steps -EntCoef 0.01 -EntCoefFinal 0.004 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards)
Invoke-Eval -Name "s11-eval-asc10" -Ckpt $ckpt[11] -Asc 10 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s11_asc10"
Invoke-Eval -Name "s11-eval-asc0" -Ckpt $ckpt[11] -Asc 0 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s11_asc0"

Write-Host "v10 extension complete. Gate table: docs/superpowers/plans/v10-run-log.md" -ForegroundColor Green
```

Critic warmup 8 (not v9's 15): the reward-semantics delta is one scalar on the potion terms, much smaller than v9's two new mechanisms, and 15 iters would freeze the actor for 25% of s10's 2M budget.

- [x] **Step 5: Parse check**

Run: `powershell -NoProfile -Command "& { $t = Get-Content -Raw train_curriculum_v10.ps1; [ScriptBlock]::Create($t) | Out-Null; 'parse ok' }"`
Expected: `parse ok`. Observed: `parse ok` (run in-session; the nested-quoting form strips `$t`).

- [x] **Step 6: Smoke run**

Run (native PowerShell, GPU, ~5 min): `.\train_curriculum_v10.ps1 -Smoke`
Expected: both stages train 65536 steps from the v9_s9 seed and exit 0; evals + gate report "skipped (smoke mode)". Then delete the scraps: `Remove-Item runs\*v10smoke*`. Observed 2026-08-13: exit 0 end-to-end, scraps deleted.

- [x] **Step 7: Stage**

```powershell
git add train_curriculum_v10.ps1
```

---

### Task 3: `v10-run-log.md` gate ledger

**Files:**
- Create: `docs/superpowers/plans/v10-run-log.md`

**Interfaces:**
- Consumes: gate thresholds (unchanged from v8 Task 7 / v9 for comparability; `ep_potions_used` counts actual drinks — comparable within v8/v9/v10 only).
- Produces: the post-run fill-in target and the next contingency ladder.

- [x] **Step 1: Write the log**

Written as `docs/superpowers/plans/v10-run-log.md`: launch commands, the three-row gate table (s10 50-ep asc-10 escape gates; s11 150-ep asc-10 with the anneal-recovery energy gate and no-regression-vs-s7 floors; s11 150-ep asc-0 win/floor), and the next contingency ladder (s11-lowshare 0.8 rung → snapshot-seeded exploration as the post-scalar escalation; potion price-knob refutation criterion; energy report-only rule; the standing ep_ret collapse rule).

- [x] **Step 2: Stage**

```powershell
git add docs/superpowers/plans/v10-run-log.md docs/superpowers/plans/2026-08-13-v10-escape-and-settle.md
```

---

### Task 4: Handoff

**Files:**
- Modify: memory `v9-rest-potion-fix-plan.md` (v10 pointer), `MEMORY.md` index line

- [x] **Step 1: Launch decision**

Perry launches (standing rule — GPU collisions). Hand off `.\train_curriculum_v10.ps1` + the run-log link. Do not launch.

- [ ] **Step 2: After the run: fill the gate table**

Copy the eval gate-block values into `v10-run-log.md`, set verdicts, apply the contingency ladder if needed (stage only), and update memory.

---

### Task 5: Aux target computation (`sts2_rl/aux_targets.py`)

**Files:**
- Create: `sts2_rl/aux_targets.py`
- Test: `test/test_aux_targets.py` (new)

**Interfaces:**
- Consumes: nothing project-specific (pure numpy over rollout-buffer columns).
- Produces: `hp_lost_next_floors(floor_col, hp_col, done_col, horizon_floors=3) -> (targets, valid)`, both `[N, E]` (`float32`, `bool`). Task 7 calls it with obs-buffer slices.

Semantics (spec §2): per `(t, e)`, cumulative `run.hp_ratio` DROPS (heals don't cancel damage) from t until the first in-window step whose floor advanced ≥ 3, or the episode's last in-window step; `valid=False` only when the rollout window ends before either stop. `done[t]==1` means obs t is a FRESH episode's first obs (same-slot auto-reset) — accumulation must never cross it. Known, accepted limitation: the lethal blow itself is not in the obs stream (the done slot already holds the next episode's obs), so death labels undercount the final hit.

- [x] **Step 1: Write the failing tests**

Create `test/test_aux_targets.py`:

```python
"""v10 aux-head targets (spec 2026-08-13-aux-hp-head-gae-lambda-design):
hp-lost-over-next-3-floors labels from rollout obs columns."""
import numpy as np

from sts2_rl.aux_targets import hp_lost_next_floors


def _cols(floors, hp, done):
    f = (np.array(floors, dtype=np.float32) / 50.0)[:, None]
    h = np.array(hp, dtype=np.float32)[:, None]
    d = np.array(done, dtype=np.float32)[:, None]
    return f, h, d


def test_horizon_reached_sums_only_drops():
    # floors 0..4; hp 1.0 .9 .95 .7 .6 -> drops .1, 0 (heal), .25, .1
    f, h, d = _cols([0, 1, 2, 3, 4], [1.0, .9, .95, .7, .6], [0, 0, 0, 0, 0])
    t, v = hp_lost_next_floors(f, h, d)
    assert v[0, 0] and abs(t[0, 0] - 0.35) < 1e-6   # stop at floor>=3
    assert v[1, 0] and abs(t[1, 0] - 0.35) < 1e-6   # stop at floor>=4


def test_window_end_invalidates():
    f, h, d = _cols([0, 0, 1, 1, 2], [1.0] * 5, [0] * 5)
    t, v = hp_lost_next_floors(f, h, d)
    assert not v.any()   # never advances 3 floors, no episode end in window


def test_episode_end_is_a_valid_stop_and_no_leak():
    # done at index 3: obs 3 is a NEW episode (fresh hp, low floor)
    f, h, d = _cols([10, 10, 11, 0, 3], [0.5, 0.4, 0.4, 1.0, 0.2], [0, 0, 0, 1, 0])
    t, v = hp_lost_next_floors(f, h, d)
    assert v[0, 0] and abs(t[0, 0] - 0.1) < 1e-6    # closed episode: lost-until-end
    assert v[3, 0] and abs(t[3, 0] - 0.8) < 1e-6    # new episode reaches +3 at idx 4
    assert not v[4, 0]                              # open tail, horizon unreached


def test_tail_open_segment_invalid():
    f, h, d = _cols([0, 1, 1, 2, 2], [1.0, .9, .8, .7, .6], [0] * 5)
    t, v = hp_lost_next_floors(f, h, d)
    assert not v[4, 0]
```

- [x] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest test/test_aux_targets.py -v`
Expected: `ModuleNotFoundError: No module named 'sts2_rl.aux_targets'`.

- [x] **Step 3: Implement**

Create `sts2_rl/aux_targets.py`:

```python
"""v10 aux-head targets (spec 2026-08-13-aux-hp-head-gae-lambda-design).

Computed post-rollout from the stored observation buffers alone: the rollout
keeps no per-step info dicts, and both scalars are already obs slots
(run.floor = total_floor/50 clipped at its write site run_env.py:1322,
run.hp_ratio = hp/max_hp clipped). done[t]==1 marks obs t as the FIRST obs
of a new episode (the vec env auto-resets into the same buffer slot), so no
window may cross a done flag - the next episode's floors/HP would leak in.
"""
from __future__ import annotations

import numpy as np

FLOOR_SCALE = 50.0


def hp_lost_next_floors(
    floor_col: np.ndarray,
    hp_col: np.ndarray,
    done_col: np.ndarray,
    horizon_floors: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """targets[t,e] = cumulative hp_ratio DROPS from t until the first step
    whose floor advanced >= horizon_floors, or the episode's last in-window
    step, whichever comes first. valid[t,e] is False only when the rollout
    window ends before either stopping point. The lethal blow itself is not
    observable (the done slot already holds the next episode's obs), so
    death labels undercount the final hit - accepted, documented in spec."""
    N, E = floor_col.shape
    floors = np.rint(floor_col * FLOOR_SCALE).astype(np.int64)
    targets = np.zeros((N, E), dtype=np.float32)
    valid = np.zeros((N, E), dtype=bool)
    done = np.asarray(done_col, dtype=bool)
    for e in range(E):
        starts = np.flatnonzero(done[:, e])
        bounds = np.concatenate(([0], starts, [N]))
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            if hi <= lo:
                continue
            f = floors[lo:hi, e]
            h = hp_col[lo:hi, e]
            drops = np.maximum(0.0, h[:-1] - h[1:])
            cum = np.concatenate(([0.0], np.cumsum(drops)))
            # floors are nondecreasing within an episode, so the first index
            # at +horizon is a searchsorted per segment, vectorized over i.
            stop = np.searchsorted(f, f + horizon_floors, side="left")
            seg_end = hi - lo - 1
            closed = hi < N   # segment ended by a done INSIDE the window
            for i in range(hi - lo):
                s = stop[i]
                if s <= seg_end:
                    targets[lo + i, e] = cum[s] - cum[i]
                    valid[lo + i, e] = True
                elif closed:
                    targets[lo + i, e] = cum[seg_end] - cum[i]
                    valid[lo + i, e] = True
    return targets, valid
```

(The inner loop is ~N iterations per env total — ~33k trivial ops per rollout, negligible next to a PPO iteration.)

- [x] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest test/test_aux_targets.py -v`
Expected: 4 passed.

- [x] **Step 5: Stage (NO commit)**

```powershell
git add sts2_rl/aux_targets.py test/test_aux_targets.py
```

---

### Task 6: Aux head on the model + lenient checkpoint load

**Files:**
- Modify: `sts2_rl/models.py` (`EntitySetActorCritic.__init__` end ~line 1293; new method after `get_value` ~line 1296; `get_action_and_value` ~line 1384)
- Modify: `sts2_rl/checkpoints.py` (`load_agent` ~line 625)
- Test: `test/test_aux_head.py` (new)

**Interfaces:**
- Consumes: `self.critic_encoder` (aliased to `actor_encoder` under `--shared-encoder`), `_EntsetEncoder.out_dim`.
- Produces: `self.aux_hp3_head` (registered LAST); `get_action_and_value(obs, mask, action=None, with_aux=False)` returning the existing 4-tuple, or a 5-tuple `(action, log_prob, entropy, value, aux_pred)` when `with_aux=True`; `load_agent` accepting checkpoints whose ONLY missing keys are `aux_*` (fresh-init overlay). `head_version` stays 4 — the action-head layout is unchanged; old checkpoints must keep loading everywhere (spec §3).

- [x] **Step 1: Write the failing tests**

Create `test/test_aux_head.py`. Build the entset agent the same way `test/test_warm_start.py` does (reuse its spec/obs-dim helpers — read that file first and mirror its construction; don't invent a new fixture path). Tests:

```python
"""v10 aux head (spec 2026-08-13-aux-hp-head-gae-lambda-design):
module registration order, with_aux contract, lenient checkpoint load."""
import torch

# mirror test_warm_start.py's helpers to build a small run-kind entset agent
# and a dummy (obs, mask) batch -- reuse, don't reinvent.


def test_aux_head_params_registered_last(run_agent):
    names = [n for n, _ in run_agent.named_parameters()]
    first_aux = next(i for i, n in enumerate(names) if n.startswith("aux_"))
    assert all(n.startswith("aux_") for n in names[first_aux:])


def test_get_action_and_value_contracts(run_agent, dummy_obs_mask):
    obs, mask = dummy_obs_mask
    out4 = run_agent.get_action_and_value(obs, mask)
    assert len(out4) == 4                      # existing call sites untouched
    out5 = run_agent.get_action_and_value(obs, mask, with_aux=True)
    assert len(out5) == 5
    assert out5[4].shape == out5[3].shape      # aux pred shaped like value


def test_load_agent_accepts_pre_aux_checkpoint(tmp_path, run_agent_factory):
    # save a state_dict WITHOUT aux keys (an old checkpoint), reload
    agent = run_agent_factory()
    state = {k: v for k, v in agent.state_dict().items()
             if not k.startswith("aux_")}
    # ...write a minimal ckpt dict the way test_warm_start.py builds one,
    # call checkpoints.load_agent, assert it succeeds and aux params exist.


def test_load_agent_still_rejects_non_aux_missing_keys(tmp_path, run_agent_factory):
    # same, but ALSO drop a critic key -> expect the load to raise as today.
```

(The last two bodies follow whatever checkpoint-dict shape `test_warm_start.py` already builds — same `env_kind`/`obs_schema`/`arch`/`head_version` stamps so `check_checkpoint` passes.)

- [x] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest test/test_aux_head.py -v`
Expected: FAIL — no `aux_` parameters exist, `with_aux` is an unexpected keyword.

- [x] **Step 3: Implement — models.py**

At the very END of `EntitySetActorCritic.__init__` (after every existing head assignment, ~line 1293):

```python
        # v10 aux head (spec 2026-08-13-aux-hp-head-gae-lambda-design):
        # supervised "hp lost over the next 3 floors" prediction off the
        # critic/shared encoder. MUST stay registered LAST: Adam state is
        # positional; checkpoints.load_agent's aux-lenient overlay and
        # train_torch's optimizer-group patch both assume pre-existing
        # params keep their positions and aux params occupy the tail.
        self.aux_hp3_head = nn.Sequential(
            nn.Linear(self.critic_encoder.out_dim, 64), nn.Tanh(),
            nn.Linear(64, 1),
        )
```

In `get_action_and_value` (~1384-1395): add `with_aux: bool = False` as the last keyword. If the body currently gets the value via `self.get_value(obs)` or an inline `self.critic(self.critic_encoder(obs))`, hoist the encoder features once:

```python
        cf = self.critic_encoder(obs)
        value = self.critic(cf).squeeze(-1)
        ...
        if with_aux:
            return action, log_prob, entropy, value, self.aux_hp3_head(cf).squeeze(-1)
        return action, log_prob, entropy, value
```

`action_logits`/`get_value` untouched (ONNX export and eval parity depend on them only).

- [x] **Step 4: Implement — checkpoints.py lenient load**

In `load_agent`, replace the bare `model.load_state_dict(ckpt["model"])` (~line 625):

```python
    state = ckpt["model"]
    own = model.state_dict()
    missing = [k for k in own if k not in state]
    if missing and all(k.startswith("aux_") for k in missing):
        # v10 (spec 2026-08-13-aux-hp-head-gae-lambda-design): checkpoint
        # predates the aux heads. Overlay onto the fresh model's own full
        # state dict (warm_start_agent's pattern) so strict-load semantics
        # are preserved; only the aux tail keeps its fresh init.
        full = dict(own)
        full.update(state)
        model.load_state_dict(full)
        print(f"aux heads fresh-initialized ({len(missing)} params not in checkpoint)")
    else:
        model.load_state_dict(state)
```

Any other missing key, and any unexpected key, still fails exactly as today.

- [x] **Step 5: Run to verify pass, plus neighbors**

Run: `.venv\Scripts\python.exe -m pytest test/test_aux_head.py test/test_warm_start.py -v`
Expected: all PASS (warm_start builds `full_state` from the new model's own state dict, so the aux tail is covered there automatically — verify no failure appears).

- [x] **Step 6: Stage (NO commit)**

```powershell
git add sts2_rl/models.py sts2_rl/checkpoints.py test/test_aux_head.py
```

---

### Task 7: Trainer integration (`train_torch.py`)

**Files:**
- Modify: `train_torch.py` (argparse ~line 205; combat-rejection guard ~line 363; post-GAE block ~line 803; minibatch loss ~line 844-859; optimizer-state restore on resume; per-iter log line)

**Interfaces:**
- Consumes: Task 5's `hp_lost_next_floors`, Task 6's `with_aux=True` 5-tuple, `run_env.run_obs_layout(args.card_obs).f_slices["run.floor"]` / `["run.hp_ratio"]`.
- Produces: `--aux-hp-coef` (float, default 0.0 = fully off, bit-identical); aux MSE in the loss and in the per-iteration log. Task 8's script passes `--aux-hp-coef 0.25`.

- [x] **Step 1: Argparse + guards**

After `--potion-death-expiry`'s argument (~line 205):

```python
    ap.add_argument("--aux-hp-coef", type=float, default=0.0,
                    help="v10: weight of the auxiliary 'hp lost over the "
                         "next 3 floors' MSE (0 = head unused; run env + "
                         "entset only)")
```

Where the run-only flags are validated (the `--env combat` rejection around line 363), add:

```python
    if args.aux_hp_coef and args.env != "run":
        raise SystemExit("--aux-hp-coef needs --env run (targets read the "
                         "run obs layout's run.floor / run.hp_ratio slots)")
    if args.aux_hp_coef and args.arch != "entset":
        raise SystemExit("--aux-hp-coef needs --arch entset (aux head lives "
                         "on EntitySetActorCritic)")
```

- [x] **Step 2: Slice resolution + post-GAE targets**

Once, before the training loop (near where the layout/obs dims are already established):

```python
    aux_slices = None
    if args.aux_hp_coef > 0:
        from sts2_rl.run_env import run_obs_layout
        _l = run_obs_layout(args.card_obs)
        aux_slices = (_l.f_slices["run.floor"], _l.f_slices["run.hp_ratio"])
```

Immediately after the GAE block's `returns = advantages + val_buf` (~line 803) and next to the existing flattening (~806-812):

```python
        b_auxt = b_auxv = None
        if args.aux_hp_coef > 0:
            from sts2_rl.aux_targets import hp_lost_next_floors
            fl = obs_buf.f[:, :, aux_slices[0]].squeeze(-1).cpu().numpy()
            hp = obs_buf.f[:, :, aux_slices[1]].squeeze(-1).cpu().numpy()
            aux_t, aux_v = hp_lost_next_floors(fl, hp, done_buf.cpu().numpy())
            b_auxt = torch.as_tensor(aux_t, device=device).reshape(-1)
            b_auxv = torch.as_tensor(aux_v, device=device, dtype=torch.float32).reshape(-1)
```

- [x] **Step 3: Minibatch loss**

In the minibatch loop (~844-859), branch the forward and add the masked MSE to BOTH the normal loss and the critic-warmup loss (aux is supervised — it trains during warmup too, spec §2):

```python
            if args.aux_hp_coef > 0:
                _, newlogp, entropy, newval, aux_pred = agent.get_action_and_value(
                    b_obs[mb], b_mask[mb], b_act[mb], with_aux=True)
            else:
                _, newlogp, entropy, newval = agent.get_action_and_value(
                    b_obs[mb], b_mask[mb], b_act[mb])
            ...
            aux_loss = torch.zeros((), device=device)
            if args.aux_hp_coef > 0:
                m = b_auxv[mb]
                aux_loss = ((aux_pred - b_auxt[mb]).pow(2) * m).sum() / m.sum().clamp(min=1.0)
            # normal branch:  loss = pg_loss - ent*entropy + vf_coef*v_loss + args.aux_hp_coef*aux_loss
            # warmup branch:  loss = vf_coef*v_loss + args.aux_hp_coef*aux_loss
```

Append the aux value to the existing per-iteration log print (find the line printing pg/v/ent losses; add `aux=<mean over epoch>` when the coef is nonzero) — the s10 sanity gate reads this.

- [x] **Step 4: Optimizer-state patch on resume**

At the optimizer-state restore for `--resume` (where `ckpt["optim"]` is loaded): the saved Adam state indexes params positionally; a pre-aux checkpoint has P entries while the live model has P+n (aux registered last, Task 6). Patch before loading:

```python
        opt_state = ckpt["optim"]
        n_live = sum(1 for _ in agent.parameters())
        groups = opt_state["param_groups"]
        if len(groups) == 1 and len(groups[0]["params"]) < n_live:
            n_aux = sum(1 for n, _ in agent.named_parameters() if n.startswith("aux_"))
            saved = groups[0]["params"]
            if len(saved) + n_aux == n_live:
                # pre-aux checkpoint: old params keep their moments, aux
                # params take the tail ids with no state (Adam lazily
                # initializes them on first step).
                groups[0]["params"] = list(saved) + list(range(len(saved), n_live))
                print(f"optimizer state patched: {n_aux} fresh aux params appended")
        optimizer.load_state_dict(opt_state)
```

Any other shape mismatch still fails exactly as today (the patch only fires when the shortfall equals the aux param count in a single-group optimizer).

- [x] **Step 5: Verify**

Run: `.venv\Scripts\python.exe -m pytest test/test_aux_targets.py test/test_aux_head.py test/test_v10_lowshare.py test/test_v9_rewards.py -v` — all PASS.
Then the full suite: `.venv\Scripts\python.exe -m pytest -q --ignore=test/test_train_io.py --ignore=test/test_live_onnx.py` — all green.
Then a 2-minute CPU integration check that the whole path (lenient load → optimizer patch → targets → aux loss) runs end-to-end from the real pre-aux seed:

```powershell
venv\Scripts\python.exe train_torch.py --env run --ascension 10 --arch entset --shared-encoder `
  --resume runs/sts2_run_torch_v9_s9.pt --save runs/aux_wiring_check.pt `
  --timesteps 32768 --n-envs 8 --n-steps 128 --minibatches 4 `
  --gae-lambda 0.98 --aux-hp-coef 0.25 --device cpu
```

Expected in the output: `aux heads fresh-initialized (...)`, `optimizer state patched: ... fresh aux params appended`, and a finite, nonzero `aux=` term in the iteration log. Delete `runs/aux_wiring_check.pt` afterwards.

- [x] **Step 6: Stage (NO commit)**

```powershell
git add train_torch.py
```

---

### Task 8: Fold the levers into the script + run log

**Files:**
- Modify: `train_curriculum_v10.ps1` (rewards block + both stage invocations + header)
- Modify: `docs/superpowers/plans/v10-run-log.md` (knob table + s10 gate row)

**Interfaces:**
- Consumes: `--gae-lambda` (existing), `--aux-hp-coef` (Task 7).
- Produces: the launchable v10 script; launch unblocks after this task.

- [x] **Step 1: Script edits**

After the `$runRewards` block add:

```powershell
# Long-horizon levers (spec 2026-08-13-aux-hp-head-gae-lambda-design):
# lambda 0.95 -> 0.98 stretches actual-return credit ~14 -> ~50 decisions;
# the aux head supervises "hp lost over the next 3 floors" off the shared
# encoder so rest/potion decisions can price the upcoming map.
$longHorizon = @("--gae-lambda", "0.98", "--aux-hp-coef", "0.25")
```

Append `+ $longHorizon` to BOTH stages' `-StageArgs` parenthesized arrays (s10 and s11). Update the header comment's stage table notes (`s10 ... + gae 0.98 + aux 0.25`, same for s11) and add one line under "Knob changes vs v9" naming the spec.

- [x] **Step 2: Parse check + re-smoke**

Run: `powershell -NoProfile -Command "& { $t = Get-Content -Raw train_curriculum_v10.ps1; [ScriptBlock]::Create($t) | Out-Null; 'parse ok' }"` → `parse ok`.
Then (native PowerShell, GPU free): `.\train_curriculum_v10.ps1 -Smoke` → exit 0; expect the `aux heads fresh-initialized` + `optimizer state patched` lines on the s10 smoke stage. Delete `runs/*v10smoke*`.

- [x] **Step 3: Run-log edits**

In `docs/superpowers/plans/v10-run-log.md`: add to the knob/why table —

```markdown
| long-horizon: credit half-life ~14 decisions (γλ=0.949) delegated rest/potion judgment to an uninformed critic | `--gae-lambda 0.98` (both stages) + aux head `--aux-hp-coef 0.25`: supervised "hp lost next 3 floors" off the shared encoder (spec 2026-08-13-aux-hp-head-gae-lambda-design.md) |
```

and extend the s10 gate row with: `aux_loss (train log) falling over s10 — report-only wiring sanity; flat = broken plumbing, fix before s11`.

- [x] **Step 4: Stage (NO commit)**

```powershell
git add train_curriculum_v10.ps1 docs/superpowers/plans/v10-run-log.md docs/superpowers/plans/2026-08-13-v10-escape-and-settle.md docs/superpowers/specs/2026-08-13-aux-hp-head-gae-lambda-design.md
```

---

## Self-review notes

- Spec coverage: k change (Task 2 Step 3), ent-hold escape + structural gate (Task 2 Step 4), low-share flag for the next rung (Task 1), energy regression handled via s11 anneal + gate row (Task 3), no masks anywhere. The asc-0 win-rate drop has no dedicated knob on purpose: it rides on the rest/potion capability unlocks, and 2/150 vs 5/150 is inside noise.
- Type consistency: `hp_potential_low_share` spelled identically in EnvSpec, `build_env`, `env_spec`, and the CLI flag (`--hp-potential-low-share`); script names `$ckpt[10]`/`$ckpt[11]`, tags `v10_s10`/`v10_s11` used consistently.
- No placeholders: every code block is complete; the only "copy verbatim" is the four helper functions from v9, named explicitly.
- Amendment (Tasks 5–8) self-review: `aux_` prefix is load-bearing in three places (module name in models.py, lenient-load allowlist in checkpoints.py, optimizer-patch count in train_torch.py) — spelled identically in all; `with_aux` default False keeps every existing 4-tuple call site; the only delegated-to-implementer piece is test_aux_head.py's agent-construction fixtures, which must mirror test_warm_start.py's existing helpers rather than invent new ones (assertions are fully specified).
