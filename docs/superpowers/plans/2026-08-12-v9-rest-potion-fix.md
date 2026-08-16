# v9 Rest + Potion Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two v8 s7 gate failures — rest behavior collapsed to 100% heal / 0% upgrade when the curriculum mask came off, and potions are picked up but almost never drunk — via two targeted, default-off reward changes plus a +10M-step extension run (s8/s9) from the s7 checkpoint.

**Architecture:** Both failures are reward-design holes, not undertraining, so the fix is env-side. (1) HP-potential shaping (`run_env.py:1011-1023`) applies ΔΦ to every HP delta with no source distinction; because ΔΦ is undiscounted while future losses are discounted, "heal now at the campfire, lose the HP later" is net-positive — a farming attractor the 0.80 rest mask was suppressing. v9 caps rest-heal shaping at the knee (0.35): heals starting above it earn zero, heals from below earn only the below-knee climb. (2) The potion ledger (`run_env.py:1065-1103`) pays +k on pickup, −k on any belt decrease, and **nothing at episode end** — so hoard-until-death nets +k per potion and strictly dominates drinking (drink nets 0). Eval data confirms: potions picked up in 150/150 episodes, drunk in ~9–19%. v9 adds a death-only expiry of −k per still-held potion (full −k, not the plan-doc's −k/2: at −k/2 hoarding still nets +k/2 and still dominates). Training is a 2-stage resume extension, not a retrain: reward semantics changed → `--critic-warmup`; rest_upgrade sits at exactly 0% → entropy restored to 0.01 so the action gets sampled at all.

**Tech Stack:** Python 3.11, raw-PyTorch PPO (`train_torch.py`), gymnasium-style `STS2RunEnv`, pytest, PowerShell 5.1 curriculum script.

## Global Constraints

- **NEVER `git commit` or `git push` in this repo — `git add` (stage) only.** (Perry's standing rule; overrides any skill's commit steps.)
- Tests run under `.venv\Scripts\python.exe` (CPU torch). Training/eval run under `venv\Scripts\python.exe` (CUDA). Do not mix them.
- Known pre-existing failures to ignore: 4 in `test/test_train_io.py`, 2 in `test/test_live_onnx.py`.
- All new env knobs default OFF; a default-constructed `STS2RunEnv` must be bit-identical to today's (same rule every v7/v8 knob followed).
- Never re-introduce a rest-heal mask, potion mask, or room-type reward term (v8 plan Task 7, verbatim constraint).
- Subagents dispatched during execution use sonnet.
- Working dir for every task: `c:\Users\Perry\Desktop\sts2-rl`.

## Design decisions already made (do not re-litigate)

- Rest contingency: knee-cap on rest-heal shaping (the plan-doc's "no shaping on rest heals starting above the knee", extended so below-knee heals also stop earning at the knee). `hp_potential_low_share` stays 0.7 — one variable per failure mode; 0.7→0.8 is a documented follow-up contingency, not part of v9 (would need a new CLI flag; knee/low_share are not CLI-exposed today).
- Potion contingency: death-only −k expiry at full k=0.3. Not −k/2 (leaves hoarding dominant on deaths), not k→0.15 (the data refutes "pickup avoidance" — pickups happen every episode).
- Extension (10M) instead of retrain (40M); s8 entropy flat 0.01, s9 anneals 0.01→0.004.
- Gimmick-probe gate is dropped from v9 (run-kind checkpoints cannot drive the combat env, `checkpoints.py:235-247`; true of v6 too). The eval.py `SystemExit` escape gets fixed so `--gimmick-probes` degrades gracefully instead of killing the process, but no new probe tooling in v9.

---

### Task 1: Rest-heal shaping knee cap (`run_env.py`)

**Files:**
- Modify: `sts2_rl/run_env.py` (kwargs ~line 710-712, storage ~747-749, step() block at 1011-1023)
- Test: `test/test_v9_rewards.py` (new file)

**Interfaces:**
- Consumes: existing `_hp_potential(ratio, knee, low_share)` at `run_env.py:687`, `DecisionKind`, `REST_HEAL` (both already imported by `run_env.py` — the rest mask at ~1264 uses them).
- Produces: `STS2RunEnv(..., rest_heal_shaping_knee_cap: bool = False)` kwarg + `self._rest_heal_shaping_knee_cap` attr. Tasks 3 and 5 rely on this exact kwarg name.

- [ ] **Step 1: Write the failing tests**

Create `test/test_v9_rewards.py`. Copy the monkeypatch pattern from `test/test_v8_rewards.py` (read its `_hp_only_step` at lines 81-91 first). Note: if `DecisionRequest` has required fields beyond `(kind, run, combat)`, mirror whatever `test_v8_rewards.py`'s `_combat_request` does and default the extras.

```python
"""v9 reward fixes (plan 2026-08-12-v9-rest-potion-fix): rest-heal shaping
knee cap + death-only potion expiry. Both default OFF: a default env stays
bit-identical (test_v8_rewards pins the baseline)."""
from types import SimpleNamespace

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind, DecisionRequest, REST_HEAL, REST_SMITH
from sts2_rl.run_env import STS2RunEnv, _hp_potential

KNEE = 0.35
LOW_SHARE = 0.7


def _phi(r):
    return _hp_potential(r, KNEE, LOW_SHARE)


def _rest_step(env, hp_before, hp_after, answer, max_hp=100):
    """One step() answering a REST decision with `answer`, whose only run-state
    change is HP — same seam-monkeypatch isolation as test_v8_rewards.
    _build_obs is stubbed (as test_v8_rewards._combat_request does) because a
    hand-built REST request may lack fields the real obs writer reads."""
    env._run.hp = hp_before
    env._run.max_hp = max_hp
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run, combat=None)
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
    env._translate = lambda action, request: answer
    env._count_behavior = lambda request, answer: None
    env._switch = lambda a: setattr(env._run, "hp", hp_after)
    return env.step(0)


def test_rest_heal_above_knee_earns_zero_with_cap():
    env = STS2RunEnv(hp_potential_scale=4.0, rest_heal_shaping_knee_cap=True)
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=80, hp_after=100, answer=REST_HEAL)
    assert reward == pytest.approx(0.0, abs=1e-9)


def test_rest_heal_from_below_knee_caps_at_knee():
    env = STS2RunEnv(hp_potential_scale=4.0, rest_heal_shaping_knee_cap=True)
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=20, hp_after=100, answer=REST_HEAL)
    assert reward == pytest.approx(4.0 * (_phi(0.35) - _phi(0.20)), abs=1e-9)


def test_rest_smith_keeps_full_shaping():
    # Source-specificity: only the REST_HEAL answer is capped.
    env = STS2RunEnv(hp_potential_scale=4.0, rest_heal_shaping_knee_cap=True)
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=80, hp_after=100, answer=REST_SMITH)
    assert reward == pytest.approx(4.0 * (_phi(1.00) - _phi(0.80)), abs=1e-9)


def test_rest_heal_uncapped_without_flag():
    env = STS2RunEnv(hp_potential_scale=4.0)   # flag defaults off
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=80, hp_after=100, answer=REST_HEAL)
    assert reward == pytest.approx(4.0 * (_phi(1.00) - _phi(0.80)), abs=1e-9)


def test_v9_kwargs_default_inert():
    env = STS2RunEnv()
    assert env._rest_heal_shaping_knee_cap is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test/test_v9_rewards.py -v`
Expected: FAIL / ERROR with `TypeError: ... unexpected keyword argument 'rest_heal_shaping_knee_cap'` (and AttributeError on the inert test).

- [ ] **Step 3: Implement**

In `STS2RunEnv.__init__`, next to `hp_potential_low_share` (~line 712) add the kwarg, and next to its storage (~749) add:

```python
rest_heal_shaping_knee_cap: bool = False,
```
```python
self._rest_heal_shaping_knee_cap = bool(rest_heal_shaping_knee_cap)
```

In `step()`, replace the ΔΦ block at lines 1018-1023 with:

```python
        ratio_before = min(hp_before, max_hp_before) / max(1, max_hp_before)
        ratio_after = min(run.hp, run.max_hp) / max(1, run.max_hp)
        shaped_after = ratio_after
        if (self._rest_heal_shaping_knee_cap
                and request is not None
                and request.kind == DecisionKind.REST
                and answer == REST_HEAL):
            # v9 rest-collapse fix: a rest heal earns shaped reward only
            # inside the danger zone. ΔΦ is undiscounted while the healed
            # HP's later losses are discounted, so an uncapped campfire heal
            # is a net-positive farm that outbids REST_SMITH's flat
            # +reward_upgrade; capping the after-ratio at the knee (and
            # clamping to zero when the heal STARTS at/above it) removes
            # exactly that edge and nothing else.
            shaped_after = min(ratio_after, self._hp_potential_knee)
            if shaped_after < ratio_before:
                shaped_after = ratio_before
        reward += self._hp_potential_scale * (
            _hp_potential(shaped_after, self._hp_potential_knee, self._hp_potential_low_share)
            - _hp_potential(ratio_before, self._hp_potential_knee, self._hp_potential_low_share)
        )
```

(`answer` is only referenced when `request is not None` — short-circuit keeps the request-None branch safe, same as the potion block at 1084.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest test/test_v9_rewards.py test/test_v8_rewards.py -v`
Expected: all PASS (v8 file proves the default path is untouched).

- [ ] **Step 5: Stage (NO commit)**

```powershell
git add sts2_rl/run_env.py test/test_v9_rewards.py
```

---

### Task 2: Death-only potion expiry (`run_env.py`)

**Files:**
- Modify: `sts2_rl/run_env.py` (kwargs ~line 721, storage ~785, step() after line 1103)
- Test: `test/test_v9_rewards.py` (append)

**Interfaces:**
- Consumes: `self._potion_potential_scale`, `belt_now`, `terminated`/`self._result` — all already in scope at the insertion point.
- Produces: `STS2RunEnv(..., potion_death_expiry: bool = False)` kwarg + `self._potion_death_expiry` attr. Tasks 3 and 5 rely on this exact name.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_v9_rewards.py`. The paired-env pattern avoids depending on `reward_loss`/`reward_win` defaults: run the identical script on a flag-on and a flag-off env and assert on the difference.

```python
def _potion(env):
    run = env._run
    run.potions[run.potions.index(None)] = SimpleNamespace(id="__test_placeholder__")


def _pickup_step(env):
    """Real step() so _belt_base syncs (see test_v8_rewards._seed_potion)."""
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda a: _potion(env)
    env.step(0)


def _death_step(env):
    def _die(a):
        env._run.hp = 0
        env._result = SimpleNamespace(victory=False, hp=0, max_hp=env._run.max_hp)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = _die
    env._info = lambda: {}
    return env.step(0)


def _death_reward(expiry: bool) -> float:
    env = STS2RunEnv(potion_potential_scale=0.3, potion_death_expiry=expiry)
    env.reset(seed=0)
    _pickup_step(env)
    _pickup_step(env)
    _, reward, terminated, *_ = _death_step(env)
    assert terminated
    return reward


def test_death_expires_each_held_potion_at_minus_k():
    assert _death_reward(True) - _death_reward(False) == pytest.approx(-0.6)


def test_win_keeps_held_potion_credit():
    def _win_reward(expiry):
        env = STS2RunEnv(potion_potential_scale=0.3, potion_death_expiry=expiry)
        env.reset(seed=0)
        _pickup_step(env)

        def _w(a):
            env._result = SimpleNamespace(
                victory=True, hp=env._run.hp, max_hp=env._run.max_hp)
        env._translate = lambda action, request: 0
        env._count_behavior = lambda request, answer: None
        env._switch = _w
        env._info = lambda: {}
        _, reward, terminated, *_ = env.step(0)
        assert terminated
        return reward
    assert _win_reward(True) == pytest.approx(_win_reward(False))


def test_potion_death_expiry_default_off():
    assert STS2RunEnv()._potion_death_expiry is False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest test/test_v9_rewards.py -v`
Expected: new tests FAIL with `TypeError: ... 'potion_death_expiry'`.

- [ ] **Step 3: Implement**

Kwarg next to `potion_potential_scale` (~line 721) and storage (~785):

```python
potion_death_expiry: bool = False,
```
```python
self._potion_death_expiry = bool(potion_death_expiry)
```

In `step()`, immediately after `self._ep_potions_expired = belt_now` (line 1103), before the return:

```python
        if (self._potion_death_expiry and terminated
                and self._result is not None and not self._result.victory):
            # v9 never-drink fix: the ledger pays +k on pickup and nothing at
            # episode end, so hoard-until-death nets +k per potion and
            # strictly dominates drinking (drink = +k-k = 0). Forfeiting the
            # pickup credit on DEATH makes hoard-and-die net 0 too — the
            # tiebreaker becomes the potion's actual combat value. Wins keep
            # the credit (winning with a spare potion is not a sin), and
            # truncation is a harness artifact, so neither expires.
            reward -= self._potion_potential_scale * belt_now
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest test/test_v9_rewards.py test/test_v8_rewards.py test/test_v7_rewards.py -v`
Expected: all PASS.

- [ ] **Step 5: Stage (NO commit)**

```powershell
git add sts2_rl/run_env.py test/test_v9_rewards.py
```

---

### Task 3: CLI + EnvSpec wiring (`train_torch.py`, `vec_env.py`)

**Files:**
- Modify: `train_torch.py` (argparse near lines 202-205; EnvSpec construction near lines 475-477)
- Modify: `sts2_rl/vec_env.py` (EnvSpec dataclass ~line 86-87; `build_env` ~line 113-118)
- Test: `test/test_v9_rewards.py` (append)

**Interfaces:**
- Consumes: Task 1/2 env kwargs `rest_heal_shaping_knee_cap`, `potion_death_expiry`.
- Produces: CLI flags `--rest-heal-shaping-knee-cap` and `--potion-death-expiry` (both `store_true`); `EnvSpec.rest_heal_shaping_knee_cap: bool = False` and `EnvSpec.potion_death_expiry: bool = False`. Task 5's script passes these exact flags.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_v9_rewards.py`:

```python
from sts2_rl.vec_env import EnvSpec, build_env


def test_envspec_v9_flags_reach_run_env():
    spec = EnvSpec(kind="run", rest_heal_shaping_knee_cap=True,
                   potion_death_expiry=True)
    env = build_env(spec)
    assert env._rest_heal_shaping_knee_cap is True
    assert env._potion_death_expiry is True


def test_envspec_v9_flags_default_off():
    env = build_env(EnvSpec(kind="run"))
    assert env._rest_heal_shaping_knee_cap is False
    assert env._potion_death_expiry is False
```

(If `EnvSpec` requires positional fields beyond `kind`, mirror whatever the existing specs in `test/test_vec_env.py` construct.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest test/test_v9_rewards.py -v`
Expected: `TypeError: EnvSpec.__init__() got an unexpected keyword argument`.

- [ ] **Step 3: Implement**

`sts2_rl/vec_env.py`, after `potion_potential_scale: float = 0.0` (line 87):

```python
    # v9 reward fixes (plan 2026-08-12-v9-rest-potion-fix), both default OFF.
    rest_heal_shaping_knee_cap: bool = False
    potion_death_expiry: bool = False
```

In `build_env`, next to the `rest_heal_mask_above` only-when-set block (~line 115) — only-when-set so a default column spec can't break if `STS2CurriculumRunEnv` doesn't forward `**kwargs`:

```python
    if spec.rest_heal_shaping_knee_cap:
        v7_kwargs["rest_heal_shaping_knee_cap"] = True
    if spec.potion_death_expiry:
        v7_kwargs["potion_death_expiry"] = True
```

`train_torch.py`, after `--potion-potential-scale` (line 205):

```python
    ap.add_argument("--rest-heal-shaping-knee-cap", action="store_true",
                    help="v9: rest heals earn HP-potential shaping only below "
                         "the knee (zero when starting at/above it)")
    ap.add_argument("--potion-death-expiry", action="store_true",
                    help="v9: -potion_potential_scale per potion still held "
                         "when the run ends in death")
```

And in the EnvSpec construction (after line 477):

```python
        rest_heal_shaping_knee_cap=getattr(args, "rest_heal_shaping_knee_cap", False),
        potion_death_expiry=getattr(args, "potion_death_expiry", False),
```

- [ ] **Step 4: Run to verify pass, plus the neighbors**

Run: `.venv\Scripts\python.exe -m pytest test/test_v9_rewards.py test/test_vec_env.py -v`
Expected: PASS (ignore nothing here — test_vec_env has no known failures).

- [ ] **Step 5: Stage (NO commit)**

```powershell
git add train_torch.py sts2_rl/vec_env.py test/test_v9_rewards.py
```

---

### Task 4: eval.py gimmick-probe SystemExit fix

**Files:**
- Modify: `eval.py` (~line 262, inside `gimmick_probes`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `eval.py` exits 0 when `--gimmick-probes` is passed with a run-kind checkpoint (prints "probes skipped: ..." instead of dying). Task 5's script and the v9 gates rely on eval exit codes being meaningful again.

- [ ] **Step 1: Reproduce**

Run: `venv\Scripts\python.exe eval.py runs/sts2_run_torch_v8_s7.pt --env run --episodes 1 --gimmick-probes; echo "exit=$LASTEXITCODE"`
Expected: report prints, then the process dies at the probe step with the checkpoint-kind message; `exit=1`.

- [ ] **Step 2: Implement**

In `gimmick_probes` (~eval.py:262) the guard is `except Exception as exc:` — but `checkpoints.check_checkpoint` refuses with `SystemExit`, which is a `BaseException`, so it escapes and kills the whole process. Change:

```python
    except (SystemExit, Exception) as exc:
        print(f"  probes skipped: {exc}")
        return
```

- [ ] **Step 3: Verify**

Run the Step-1 command again.
Expected: same report, `probes skipped: checkpoint was trained on the 'run' env...`, `exit=0`.

- [ ] **Step 4: Stage (NO commit)**

```powershell
git add eval.py
```

---

### Task 5: `train_curriculum_v9.ps1`

**Files:**
- Create: `train_curriculum_v9.ps1`

**Interfaces:**
- Consumes: Task 3's CLI flags; `runs/sts2_run_torch_v8_s7.pt` (run-kind, iter 549) as seed; `train_torch.py` flags `--timesteps --save --resume --critic-warmup --ent-coef --ent-coef-final --lr --ascension --env`; Task 4's fixed eval exit codes.
- Produces: checkpoints `runs/sts2_run_torch_v9_s8.pt`, `runs/sts2_run_torch_v9_s9.pt`; eval CSVs `runs/eval_v9_s8_asc10.*`, `runs/eval_v9_s9_asc10.*`, `runs/eval_v9_s9_asc0.*`.

- [ ] **Step 1: Write the script**

Full content (helpers `Invoke-Phase`/`Get-CkptStep`/`Invoke-Stage` are copied VERBATIM from `train_curriculum_v8.ps1:140-255` — do not re-derive them; open that file and copy the three function bodies exactly):

```powershell
<#
v9 extension run (plan 2026-08-12-v9-rest-potion-fix): fix the two v8 s7
gate failures from the s7 checkpoint, +10M steps total.

  Stage  Env  Asc  Steps  Notes
  s8     run   10     5M  new reward fixes ON, critic-warmup 15, ent 0.01 flat
  s9     run   10     5M  same rewards, ent 0.01 -> 0.004 anneal

Reward changes vs v8 (both env-side, plan tasks 1-2):
- --rest-heal-shaping-knee-cap : rest heals earn HP shaping only below the
  0.35 knee (kills the discounted heal-now/lose-later campfire farm that
  outbid the +0.5 upgrade term the moment the mask came off).
- --potion-death-expiry        : -k per potion still held at death (hoarding
  netted +k per potion under the v8 ledger and strictly dominated drinking).
No rest mask, no potion mask, ever (v8 plan Task 7 constraint).

Why a resume, not a retrain: the failures are reward holes, not capacity.
--critic-warmup 15 because reward semantics changed under the checkpoint
(memory: resume-after-env-change = stale critic). s8 restores --ent-coef to
0.01 FLAT because rest_upgrade sits at exactly 0%: the policy has to sample
the action again before any gradient can prefer it.

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v9.ps1                 # real run (~4.5h at v8 throughput)
  .\train_curriculum_v9.ps1 -Smoke          # 65536 steps/stage, scratch tag
  .\train_curriculum_v9.ps1 -Resume         # continue an interrupted run
#>
param(
    [long]$S8Steps = 5000000,
    [long]$S9Steps = 5000000,
    [string]$Device = "cuda",
    [string]$Tag = "v9",
    [string]$SeedCkpt = "runs/sts2_run_torch_v8_s7.pt",
    [switch]$Resume,
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$runs = Join-Path $root "runs"
if (-not (Test-Path $runs)) { New-Item -ItemType Directory $runs | Out-Null }
$py = Join-Path $root "venv\Scripts\python.exe"

if ($Smoke) {
    $Tag = "${Tag}smoke"
    $S8Steps = 65536; $S9Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{}
foreach ($n in 8..9) { $ckpt[$n] = Join-Path $runs "sts2_run_torch_${Tag}_s$n.pt" }

if ((Test-Path $ckpt[8]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[8]) already exists." -ForegroundColor Red
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}
if (-not (Test-Path (Join-Path $root $SeedCkpt))) {
    Write-Host "SeedCkpt '$SeedCkpt' not found - nothing to extend." -ForegroundColor Red
    exit 1
}

$nEnvs = 64
$nSteps = 512
$batchSize = [long]$nEnvs * $nSteps
$geom = @("--arch", "entset", "--shared-encoder", "--device", $Device,
          "--n-envs", "$nEnvs", "--n-steps", "$nSteps", "--minibatches", "8")

# v8 run rewards + the two v9 fixes. Same k (0.3) and same hp scale (4.0):
# the FIXES change which behaviors those scales pay for, not the scales.
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "0.5", "--reward-elite", "0.5",
                "--reward-remove", "0.25", "--reward-relic", "0.25",
                "--hp-potential-scale", "4.0",
                "--potion-potential-scale", "0.3",
                "--rest-heal-shaping-knee-cap",
                "--potion-death-expiry")

# <<< COPY Invoke-Phase, Get-CkptStep, Invoke-Stage VERBATIM from
# train_curriculum_v8.ps1 lines 140-255 here >>>

function Invoke-Eval {
    param([string]$Name, [string]$Ckpt, [int]$Asc, [int]$Episodes, [string]$Csv)
    if ($Smoke) { Write-Host "$Name skipped (smoke mode)"; return }
    $args_ = @("eval.py", $Ckpt, "--env", "run", "--episodes", "$Episodes",
               "--baselines", "--ascension", "$Asc", "--csv", $Csv)
    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) { Write-Host "$Name exited $code (continuing)" -ForegroundColor Yellow }
}

# ── s8: reward fixes land; escape the heal attractor ───────────────────────
Invoke-Stage -Name "s8-run-asc10-fixes" -SaveCkpt $ckpt[8] -PrevCkpt $SeedCkpt `
    -Steps $S8Steps -CriticWarmup 15 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards)
Invoke-Eval -Name "s8-eval-asc10" -Ckpt $ckpt[8] -Asc 10 -Episodes 50 `
    -Csv "runs/eval_${Tag}_s8_asc10"

# ── s9: settle — anneal entropy back down ──────────────────────────────────
Invoke-Stage -Name "s9-run-asc10-settle" -SaveCkpt $ckpt[9] -PrevCkpt $ckpt[8] `
    -Steps $S9Steps -EntCoef 0.01 -EntCoefFinal 0.004 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards)
Invoke-Eval -Name "s9-eval-asc10" -Ckpt $ckpt[9] -Asc 10 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s9_asc10"
Invoke-Eval -Name "s9-eval-asc0" -Ckpt $ckpt[9] -Asc 0 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s9_asc0"

Write-Host "v9 extension complete. Gate table: docs/superpowers/plans/v9-run-log.md" -ForegroundColor Green
```

- [ ] **Step 2: Copy the three helper functions**

Open `train_curriculum_v8.ps1`, copy lines 140-255 (`Invoke-Phase`, `Get-CkptStep`, `Invoke-Stage` — all three, verbatim) into the marked placeholder. The placeholder comment must not survive.

- [ ] **Step 3: Syntax-check + smoke**

Run: `powershell -NoProfile -Command "& { $t = Get-Content -Raw train_curriculum_v9.ps1; [ScriptBlock]::Create($t) | Out-Null; 'parse ok' }"`
Expected: `parse ok`.

Then (GPU must be free — skip if Perry is using it, and note that in the run log):
Run: `.\train_curriculum_v9.ps1 -Smoke`
Expected: s8 prints `seeding from runs/sts2_run_torch_v8_s7.pt` and `--critic-warmup 15`; s9 prints the ent-anneal args; both exit 0; evals print "skipped (smoke mode)". Afterwards delete `runs/*v9smoke*`.

- [ ] **Step 4: Stage (NO commit)**

```powershell
git add train_curriculum_v9.ps1
```

---

### Task 6: v9 run log + gates

**Files:**
- Create: `docs/superpowers/plans/v9-run-log.md`
- Modify: `docs/superpowers/plans/v8-run-log.md` (one line in the Log section pointing forward)

**Interfaces:**
- Consumes: the s7 eval reference numbers (from `v8-run-log.md` + `runs/eval_v8_s7_asc{0,10}.episodes.csv`).
- Produces: the gate ledger Task 7 fills in.

- [ ] **Step 1: Write `docs/superpowers/plans/v9-run-log.md`**

```markdown
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
| s8 (50 eps, asc 10) | rest_upgrade_rate > 0 (attractor escaped — ANY nonzero); potions_used/ep ≥ 0.4; energy_unspent/turn ≤ 0.15 held | | |
| s9 (150 eps, asc 10) | rest_upgrade_rate ≥ 0.25 unmasked; potions_used/ep ≥ 1.0; hp_at_use < hp_overall; energy_unspent/turn ≤ 0.15; no regression vs s7: mean floor ≥ 21.0, elites/ep ≥ 1.0, hp_lost/floor ≤ 8.4 | | |
| s9 (150 eps, asc 0) | win ≥ 3.3% (v6/s7 level); mean floor ≥ 30.1; rest/potion gates as above | | |

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
```

- [ ] **Step 2: Cross-link from the v8 run log**

Append one line to the Log section of `docs/superpowers/plans/v8-run-log.md`:

```markdown
- 2026-08-12 (later): s7 FAIL follow-up planned + staged as v9 — rest-heal shaping knee cap + death-only potion expiry, +10M extension from s7. See 2026-08-12-v9-rest-potion-fix.md / v9-run-log.md.
```

- [ ] **Step 3: Stage (NO commit)**

```powershell
git add docs/superpowers/plans/v9-run-log.md docs/superpowers/plans/v8-run-log.md docs/superpowers/plans/2026-08-12-v9-rest-potion-fix.md
```

---

### Task 7: Full suite + launch handoff

**Files:**
- None created; verification + handoff only.

- [ ] **Step 1: Full test suite**

Run: `.venv\Scripts\python.exe -m pytest -q --ignore=test/test_train_io.py --ignore=test/test_live_onnx.py`
Expected: all green (the two ignored files carry the 6 known pre-existing failures).

- [x] **Step 2: Launch decision**

Training needs the CUDA GPU for ~4.5h (`venv`, not `.venv`). Precedent (v8): Perry launches so training never collides with him using the machine. Default: hand off with the launch command from the run log. Launch directly only if Perry has said the GPU is free.

- [x] **Step 3: After the run: fill the gate table** (2026-08-13: done — ALL gates FAIL, s10 contingency staged in v9-run-log.md)

The script auto-writes `runs/eval_v9_s8_asc10.*`, `runs/eval_v9_s9_asc10.*`, `runs/eval_v9_s9_asc0.*`. Copy the "v8 s7 gate summary" block values (the eval.py gate block from 2026-08-12 applies unchanged — same thresholds) into `v9-run-log.md`'s table, set verdicts, apply the contingency ladder if needed, and update memory (`v8-hp-economy-implemented.md` gets a v9 outcome line).
