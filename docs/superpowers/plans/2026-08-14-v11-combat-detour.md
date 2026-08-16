# v11 Combat Detour + Reward Rebalance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reset the run policy's dead campfire heads by warm-start round-tripping through the combat env (elite/boss drill), then rebuild run play under rebalanced rewards (`--reward-upgrade 1.5`, `--reward-elite 3`, new `--reward-boss 3`).

**Architecture:** One new env reward term (`reward_boss`, threaded EnvSpec → build_env → CLI exactly like v10's `hp_potential_low_share`), one offline snapshot-corpus filter (no env code), and one new curriculum script (`train_curriculum_v11.ps1`: s12 combat drill 2M → s13 run rebuild 4M) whose combat→run `-WarmStart` hop is the head reset. Spec: `docs/superpowers/specs/2026-08-14-v11-combat-detour-design.md`.

**Tech Stack:** Python 3 (gymnasium env, raw-PyTorch PPO in `train_torch.py`), pytest, PowerShell 5.1 curriculum script.

## Global Constraints

- **Stage only, NEVER commit or push.** Every "commit" step in this plan is `git add` only — this repo's standing rule overrides the usual commit convention. No `Co-Authored-By` trailers ever (moot, since no commits).
- **Never launch real training.** Perry launches. `-Smoke` runs are allowed for script verification.
- **Native PowerShell only** for launching the curriculum script or evals (running `powershell.exe` from Git Bash hangs multiprocessing worker spawns). Use the PowerShell tool, not Bash, for those steps.
- **Default env bit-identical:** every new knob defaults to today's behavior. `reward_boss` defaults to `0.0`.
- **No masks, ever** (no rest mask, no potion mask).
- **Tests run on the CPU venv:** `.venv\Scripts\python.exe -m pytest ...`. The `venv\` (no dot) CUDA venv is for training only. Bare `python` is a broken Microsoft Store alias — never use it.
- Known pre-existing failures excluded from "suite green": `test/test_train_io.py` (4 fails from Perry's lr/env default changes), `test/test_live_onnx.py`.
- **s13 reward args, verbatim** (any task or review that touches them must match exactly): `--floor-rewards 1.0 1.5 2.0 --reward-win 12 --reward-upgrade 1.5 --reward-elite 3 --reward-boss 3 --reward-remove 0.25 --reward-relic 0.25 --hp-potential-scale 4.0 --potion-potential-scale 0.15 --rest-heal-shaping-knee-cap --potion-death-expiry` plus `--gae-lambda 0.98 --aux-hp-coef 0.25`, `--ent-coef 0.01` flat (no final), `--critic-warmup 15`, `--lr 3e-4`.
- **Do not modify `train_curriculum_v10.ps1`** (it is the historical record of what ran). The only v10 file that changes is `docs/superpowers/plans/v10-run-log.md` (one log line, Task 5).
- Subagent dispatches in this project run on **sonnet** (Perry's standing rule).

---

### Task 1: `reward_boss` env term

**Files:**
- Modify: `sts2_rl/run_env.py` (kwarg ~line 646, assignment ~line 696, step-reward ~line 975, win branch ~line 980)
- Create: `test/test_v11_rewards.py`

**Interfaces:**
- Consumes: existing `STS2RunEnv` internals — `run.act_index`/`act_before` (already captured at `run_env.py:932/937`), the `self._result.victory` terminal branch, and the scripted-step test idiom from `test/test_v8_rewards.py` (monkeypatch `_translate`/`_count_behavior`/`_switch`).
- Produces: `STS2RunEnv(reward_boss: float = 0.0)` keyword arg and `env._reward_boss` attribute. Semantics: `+reward_boss * (act_index_after - act_index_before)` per step, plus `+reward_boss` inside the victory terminal branch (a win pays `reward_win + reward_boss`). Task 2 threads this kwarg; Task 4's script passes `--reward-boss 3`.

**Background for the implementer:** an act-boss kill in this sim is exactly an `act_index` advance — act entry lands on the next act's Ancient node in the same transition (`reward += self._act_reward * (run.act_index - act_before)` at line 974 already uses this signal). The FINAL boss ends the run (`self._result.victory`) without advancing `act_index`, so the win branch pays that boss's share — exactly once per boss either way, no double payment possible.

- [ ] **Step 1: Write the failing tests**

Create `test/test_v11_rewards.py`:

```python
"""v11 reward term (plan 2026-08-14-v11-combat-detour Task 1): reward_boss.
Default OFF: a default-constructed env must be bit-identical to today's
behavior. Scripted the same way as the v8 reward tests: monkeypatch
`_translate`/`_count_behavior`/`_switch` so a single step() call is driven
entirely by the test."""
import numpy as np
import pytest

from sts2_rl.driver import RunResult
from sts2_rl.run_env import STS2RunEnv


def _scripted_step(env, mutate):
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = mutate
    return env.step(0)


def _roll(env, seed, steps=400):
    obs, _ = env.reset(seed=seed)
    total = 0.0
    for _ in range(steps):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        obs, r, term, trunc, info = env.step(a)
        total += r
        if term or trunc:
            break
    return total


def test_default_kwargs_inert_boss():
    env = STS2RunEnv()
    assert env._reward_boss == 0.0


def test_boss_reward_fires_once_on_act_advance():
    env = STS2RunEnv(reward_boss=3.0)
    env.reset(seed=0)

    def _advance(answer):
        env._run.act_index += 1

    _, reward, terminated, truncated, _ = _scripted_step(env, _advance)
    assert not terminated and not truncated
    assert reward == pytest.approx(3.0)


def test_boss_reward_pays_nothing_on_ordinary_step():
    env = STS2RunEnv(reward_boss=3.0)
    env.reset(seed=0)
    _, reward, terminated, truncated, _ = _scripted_step(env, lambda answer: None)
    assert not terminated and not truncated
    assert reward == 0.0


def test_final_win_pays_reward_win_plus_reward_boss():
    env = STS2RunEnv(reward_boss=3.0, reward_win=12.0, win_hp_bonus=0.0)
    env.reset(seed=0)

    def _end(answer):
        env._result = RunResult(victory=True, hp=env._run.hp, max_hp=env._run.max_hp,
                                gold=0, floor=env._run.total_floor,
                                act_index=env._run.act_index,
                                deck_size=len(env._run.deck), decisions=1)
        env._request = None

    _, reward, terminated, _, _ = _scripted_step(env, _end)
    assert terminated
    assert reward == pytest.approx(15.0)     # 12 win + 3 boss, no double-pay


def test_loss_pays_no_boss_reward():
    env = STS2RunEnv(reward_boss=3.0, reward_win=12.0, reward_loss=0.0)
    env.reset(seed=0)

    def _end(answer):
        env._result = RunResult(victory=False, hp=0, max_hp=env._run.max_hp,
                                gold=0, floor=env._run.total_floor,
                                act_index=env._run.act_index,
                                deck_size=len(env._run.deck), decisions=1)
        env._request = None

    _, reward, terminated, _, _ = _scripted_step(env, _end)
    assert terminated
    assert reward == pytest.approx(0.0)


def test_default_env_reward_unchanged_with_reward_boss_off():
    r_a = _roll(STS2RunEnv(), seed=7)
    r_b = _roll(STS2RunEnv(reward_boss=0.0), seed=7)
    assert r_a == r_b
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test/test_v11_rewards.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'reward_boss'` (and `AttributeError: _reward_boss` for the default test).

- [ ] **Step 3: Implement the term in `sts2_rl/run_env.py`**

Three edits. (a) In `STS2RunEnv.__init__`'s signature, directly after `reward_elite: float = 0.0,` (line 646):

```python
        reward_elite: float = 0.0,
        reward_boss: float = 0.0,
```

(b) Directly after `self._reward_elite = reward_elite` (line 696):

```python
        self._reward_elite = reward_elite
        # v11: +reward_boss per act boss defeated (an act_index advance; the
        # FINAL boss ends the run without advancing, so the win branch pays
        # its share instead). Default OFF.
        self._reward_boss = reward_boss
```

(c) In `step()`, extend the reward block. After `reward += self._reward_elite * (self._ep_elites_won - elites_before)` (line 975):

```python
        reward += self._reward_elite * (self._ep_elites_won - elites_before)
        # v11: an act-boss kill IS the act_index advance (act entry lands on
        # the next act's Ancient node in the same transition); the final
        # boss pays via the win branch below — exactly once per boss.
        reward += self._reward_boss * (run.act_index - act_before)
```

And in the victory branch (line 980), change:

```python
                reward += self._reward_win + self._win_hp_bonus * (
                    self._result.hp / max(1, self._result.max_hp)
                )
```

to:

```python
                reward += self._reward_win + self._reward_boss + self._win_hp_bonus * (
                    self._result.hp / max(1, self._result.max_hp)
                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest test/test_v11_rewards.py test/test_v7_rewards.py test/test_v8_rewards.py -v`
Expected: all PASS (the v7/v8 files are the bit-identity regression net for the untouched defaults).

- [ ] **Step 5: Stage (never commit)**

```bash
git add sts2_rl/run_env.py test/test_v11_rewards.py
```

---

### Task 2: Thread `--reward-boss` EnvSpec → build_env → CLI

**Files:**
- Modify: `sts2_rl/vec_env.py` (EnvSpec field ~line 78, `v7_kwargs` ~line 116)
- Modify: `train_torch.py` (argparse ~line 194, combat guard ~lines 376–386, `env_spec()` ~line 499)
- Create: `test/test_v11_boss_threading.py`

**Interfaces:**
- Consumes: Task 1's `STS2RunEnv(reward_boss=...)` kwarg.
- Produces: `EnvSpec.reward_boss: float = 0.0` and the `train_torch.py --reward-boss` flag (guarded run-only). Task 4's script relies on the flag name `--reward-boss`.

- [ ] **Step 1: Write the failing tests**

Create `test/test_v11_boss_threading.py` (mirrors `test/test_v10_lowshare.py`):

```python
"""v11 (plan 2026-08-14-v11-combat-detour Task 2): --reward-boss threading.

The env kwarg lands in Task 1 (`run_env.py` reward_boss); this only threads
it EnvSpec -> build_env -> CLI, same pattern as v10's hp_potential_low_share.
"""
import argparse

from sts2_rl.vec_env import EnvSpec, build_env


def test_envspec_reward_boss_reaches_run_env():
    env = build_env(EnvSpec(kind="run", reward_boss=3.0))
    assert env._reward_boss == 3.0


def test_envspec_reward_boss_default_bit_identical():
    # 0.0 is the env's own default -- a default spec must build the same env.
    assert build_env(EnvSpec(kind="run"))._reward_boss == 0.0


def test_env_spec_threads_reward_boss():
    import train_torch
    ns = argparse.Namespace(env="run", acts=None, card_obs="hybrid",
                            encounter=None, enemy_hp_reward=0.0,
                            win_hp_bonus=0.0, branch_prob=0.0,
                            reward_boss=3.0)
    assert train_torch.env_spec(ns).reward_boss == 3.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest test/test_v11_boss_threading.py -v`
Expected: FAIL — `TypeError: EnvSpec.__init__() got an unexpected keyword argument 'reward_boss'` (first two) and `AttributeError`/spec-default mismatch (third).

- [ ] **Step 3: Implement the threading**

(a) `sts2_rl/vec_env.py` — add the field directly after `reward_relic: float = 0.0` (line 78):

```python
    reward_elite: float = 0.0
    reward_relic: float = 0.0
    # v11 (plan 2026-08-14-v11-combat-detour Task 2): +reward_boss per act
    # boss defeated; the final win pays reward_win + reward_boss. 0.0 = the
    # env's own default, so a default spec stays bit-identical.
    reward_boss: float = 0.0
```

(b) `sts2_rl/vec_env.py` — add to `v7_kwargs` in `build_env` (after `reward_relic=spec.reward_relic,`, line 116):

```python
        reward_elite=spec.reward_elite,
        reward_relic=spec.reward_relic,
        reward_boss=spec.reward_boss,
```

(c) `train_torch.py` — argparse, directly after the `--reward-relic` argument (ends line 197):

```python
    ap.add_argument("--reward-boss", type=float, default=0.0,
                    help="v11: reward per act boss defeated (the final win "
                         "pays --reward-win plus this on top)")
```

(d) `train_torch.py` — the run-only guard (lines 376–386): add `or args.reward_boss` to the condition and name the flag in the message. The block becomes:

```python
    if args.env == "combat" and (
            args.floor_rewards is not None or args.reward_win is not None
            or args.reward_upgrade or args.reward_remove or args.reward_elite
            or args.reward_relic or args.reward_boss
            or args.rest_heal_mask_above is not None
            or args.hp_potential_scale or args.potion_potential_scale
            or args.deck_random_prob):
        raise SystemExit(
            "--floor-rewards/--reward-win/--reward-upgrade/--reward-remove/"
            "--reward-elite/--reward-relic/--reward-boss/"
            "--rest-heal-mask-above/"
            "--hp-potential-scale/--potion-potential-scale/"
            "--deck-random-prob apply to the run-scale envs only.")
```

(e) `train_torch.py` — `env_spec()`, after the `reward_relic` line (499):

```python
        reward_elite=getattr(args, "reward_elite", 0.0),
        reward_relic=getattr(args, "reward_relic", 0.0),
        reward_boss=getattr(args, "reward_boss", 0.0),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest test/test_v11_boss_threading.py test/test_v10_lowshare.py test/test_vec_env.py -v`
Expected: all PASS.

- [ ] **Step 5: Stage (never commit)**

```bash
git add sts2_rl/vec_env.py train_torch.py test/test_v11_boss_threading.py
```

---

### Task 3: Elite/boss snapshot corpus

**Files:**
- Create: `runs/v11_eliteboss_snapshots.jsonl` (from `runs/v8_start_snapshots.jsonl`; `runs/` is gitignored — do NOT `git add` it)

**Interfaces:**
- Consumes: `runs/v8_start_snapshots.jsonl` (952 lines: 1 `snapshot_schema` header + 951 data rows keyed by `encounter_id`).
- Produces: `runs/v11_eliteboss_snapshots.jsonl` — 196 lines: the schema header verbatim as line 1 + the 195 rows whose `encounter_id` ends `_elite` (90 rows, 12 encounters) or `_boss` (105 rows, 12 encounters). Task 4's script points `--start-snapshots` here; Task 5 records the filter command in `v11-run-log.md`.

This is a one-off inline command, not a new tool file (YAGNI, per spec §2).

- [ ] **Step 1: Run the filter**

Run (Bash tool is fine here — no multiprocessing involved):

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

Expected: `kept 195`

- [ ] **Step 2: Verify the corpus**

```bash
cd /c/Users/Perry/Desktop/sts2-rl && .venv/Scripts/python.exe - <<'EOF'
import json
from collections import Counter
rows = [json.loads(l) for l in open('runs/v11_eliteboss_snapshots.jsonl')]
assert 'snapshot_schema' in rows[0], 'schema header must be line 1'
kinds = Counter('elite' if r['encounter_id'].endswith('_elite') else 'boss'
                for r in rows[1:])
encs = {r['encounter_id'] for r in rows[1:]}
assert len(rows) - 1 == 195 and kinds['elite'] == 90 and kinds['boss'] == 105
assert len(encs) == 24
print('corpus OK:', len(rows) - 1, 'rows,', dict(kinds), ',', len(encs), 'encounters')
EOF
```

Expected: `corpus OK: 195 rows, {'elite': 90, 'boss': 105} , 24 encounters` (dict key order may differ).

- [ ] **Step 3: Loadability smoke — the combat env accepts the corpus**

```bash
cd /c/Users/Perry/Desktop/sts2-rl && .venv/Scripts/python.exe -c "from sts2_rl.snapshots import load_snapshots; ds = load_snapshots('runs/v11_eliteboss_snapshots.jsonl'); print('loaded', len(ds), 'snapshots')"
```

Expected: `loaded 195 snapshots`. `load_snapshots` (`sts2_rl/snapshots.py:450`) is the exact loader `--start-snapshots` uses, and it is loud on a missing/mismatched `snapshot_schema` header — this proves the training path parses the filtered corpus.

Nothing to stage — `runs/` is gitignored by design (local training artifacts).

---

### Task 4: `train_curriculum_v11.ps1` + smoke run

**Files:**
- Create: `train_curriculum_v11.ps1`
- Read-only reference: `train_curriculum_v10.ps1` (helpers copied verbatim), `train_curriculum_v8.ps1` (the `$prevKind` pattern this script revives)

**Interfaces:**
- Consumes: `--reward-boss` (Task 2), `runs/v11_eliteboss_snapshots.jsonl` (Task 3), seed `runs/sts2_run_torch_v10_s10.pt`, `train_torch.py`'s existing `--warm-start`/`--start-snapshots`/`--gae-lambda`/`--aux-hp-coef` flags, `eval.py`.
- Produces: checkpoints `runs/sts2_run_torch_v11_s12.pt` / `..._s13.pt` and evals `runs/eval_v11_s13_asc{10,0}.*` when Perry launches it.

- [ ] **Step 1: Write the script**

Create `train_curriculum_v11.ps1` with exactly this content. The four helper functions (`Invoke-Phase`, `Get-CkptStep`, `Invoke-Stage`, `Invoke-Eval`) are byte-identical to `train_curriculum_v10.ps1`'s (which the content below reproduces); `Test-RestUpgradeGate` is deliberately NOT carried over — s13 is the final stage, there is nothing downstream for a mid-script gate to protect, and its gate is read post-run from `v11-run-log.md`.

```powershell
<#
v11 combat-detour run (spec 2026-08-14-v11-combat-detour-design.md): the v10
s10 gate fail proved REST_SMITH's logit is dead — held entropy cannot revive
an action whose sampling probability is zero. This run resets it structurally:
warm-starting run->combat drops every run-only head; warm-starting combat->run
fresh-initializes them (campfire menu included), so the returned policy
samples the rest menu near-uniformly and REST_SMITH finally collects its
(now 3x) reward on-policy.

  Stage  Env     Asc  Steps  Notes
  s12    combat   10     2M  elite/boss drill (runs/v11_eliteboss_snapshots
                             .jsonl, 195 starts); native HP-delta reward; the
                             warm-start INTO combat is half the reset
  s13    run      10     4M  rebuild: warm-start OUT of combat fresh-inits
                             the run heads; rebalanced rewards (upgrade
                             0.5->1.5, elite 0.5->3, NEW --reward-boss 3),
                             ent FLAT 0.01, lambda 0.98 + aux 0.25 kept

Knob changes vs v10 (spec "Components"):
- --reward-upgrade 1.5, --reward-elite 3, --reward-boss 3 (new term: +3 per
  act boss; the final win pays 12 + 3).
- --potion-potential-scale 0.15 (Perry's rollback; the price-knob experiment
  is over — two doublings taught no timing).
- s13 --critic-warmup 15: fresh run heads + rescaled returns.
No rest mask, no potion mask, ever.

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v11.ps1                # real run; auto-evals s13
  .\train_curriculum_v11.ps1 -Smoke         # 65536 steps/stage, scratch tag
  .\train_curriculum_v11.ps1 -Resume        # continue an interrupted run
#>
param(
    [long]$S12Steps = 2000000,
    [long]$S13Steps = 4000000,
    [string]$Device = "cuda",
    [string]$Tag = "v11",
    [string]$SeedCkpt = "runs/sts2_run_torch_v10_s10.pt",
    [string]$SnapshotPath = "runs/v11_eliteboss_snapshots.jsonl",
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
    $S12Steps = 65536; $S13Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{}
foreach ($n in 12..13) { $ckpt[$n] = Join-Path $runs "sts2_run_torch_${Tag}_s$n.pt" }

if ((Test-Path $ckpt[12]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[12]) already exists." -ForegroundColor Red
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}
if (-not (Test-Path (Join-Path $root $SeedCkpt))) {
    Write-Host "SeedCkpt '$SeedCkpt' not found - nothing to extend." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $root $SnapshotPath))) {
    Write-Host "SnapshotPath '$SnapshotPath' not found - run the corpus filter first (docs/superpowers/plans/v11-run-log.md, Corpus section)." -ForegroundColor Red
    exit 1
}

$nEnvs = 64
$nSteps = 512
$batchSize = [long]$nEnvs * $nSteps
$geom = @("--arch", "entset", "--shared-encoder", "--device", $Device,
          "--n-envs", "$nEnvs", "--n-steps", "$nSteps", "--minibatches", "8")

# v10 rewards with the v11 rebalance: upgrade 0.5 -> 1.5, elite 0.5 -> 3,
# NEW --reward-boss 3, potion k rolled back to 0.15 (Perry, 2026-08-14).
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "1.5", "--reward-elite", "3",
                "--reward-boss", "3",
                "--reward-remove", "0.25", "--reward-relic", "0.25",
                "--hp-potential-scale", "4.0",
                "--potion-potential-scale", "0.15",
                "--rest-heal-shaping-knee-cap",
                "--potion-death-expiry")

# Long-horizon levers (spec 2026-08-13-aux-hp-head-gae-lambda-design), run
# stage only — the aux head and lambda 0.98 are run-env levers; the combat
# drill keeps train_torch defaults (short episodes, lambda 0.95).
$longHorizon = @("--gae-lambda", "0.98", "--aux-hp-coef", "0.25")

function Invoke-Phase {
    param([string]$Name, [string[]]$PhaseArgs)
    Write-Host "[$(Get-Date -Format s)] $Name starting"
    $p = Start-Process -FilePath $py -ArgumentList $PhaseArgs `
                       -WorkingDirectory $root -NoNewWindow -Wait -PassThru
    Write-Host "[$(Get-Date -Format s)] $Name exited $($p.ExitCode)"
    return $p.ExitCode
}

# `global_step` out of a checkpoint. train_torch carries it across a --resume
# (and RESETS it to 0 on a --warm-start), so the difference between a stage's
# own checkpoint and the one it handed off from is exactly how many steps THIS
# stage has trained -- the number the resume arithmetic below is built on.
function Get-CkptStep {
    param([string]$Path)
    $code = "import sys, torch; " +
            "c = torch.load(sys.argv[1], map_location='cpu', weights_only=False); " +
            "print(int(c.get('global_step', 0)))"
    $out = & $py -c $code $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read global_step from $Path (python exit $LASTEXITCODE)."
    }
    return [long]($out | Select-Object -Last 1).Trim()
}

# One stage, resumable at ITERATION granularity rather than stage granularity.
# train_torch saves its --save checkpoint every --save-every (10) iterations,
# so an interrupted stage has already banked most of its progress; re-running
# the script must credit that progress instead of re-spending the stage's whole
# --timesteps budget on top of it (which is what the old "checkpoint exists ->
# continue it" branch did -- it also re-trained every ALREADY-FINISHED stage a
# second time). So:
#   * no checkpoint yet   -> hand off from $PrevCkpt, full $Steps budget;
#   * partially trained   -> self-resume (train_torch auto-resumes --save; no
#                            --resume/--warm-start flag, and none would be
#                            right) for the REMAINING steps only, with
#                            --critic-warmup and the entropy anneal advanced to
#                            where the interruption left them;
#   * budget spent        -> skip entirely and move to the next stage.
# -WarmStart marks a kind-switch handoff (combat<->run): BOTH v11 boundaries
# use it — that round trip IS this run's mechanism (fresh run heads).
function Invoke-Stage {
    param([string]$Name, [string]$SaveCkpt, [string]$PrevCkpt, [long]$Steps,
          [string[]]$StageArgs, [switch]$WarmStart,
          [int]$CriticWarmup = 0, [double]$EntCoef = 0, [double]$EntCoefFinal = 0)

    # How far this stage already got, in its own steps.
    $done = [long]0
    if (Test-Path $SaveCkpt) {
        $base = [long]0
        if (-not $WarmStart -and (Test-Path $PrevCkpt)) { $base = Get-CkptStep $PrevCkpt }
        $done = (Get-CkptStep $SaveCkpt) - $base
        if ($done -lt 0) { $done = [long]0 }   # hand-edited/replaced lineage: re-train the budget
    }
    $remaining = $Steps - $done

    # < one batch left buys 0 iterations (n_iters = timesteps // batch_size),
    # so that stage is finished -- launching it would only burn startup time.
    if ($remaining -lt $batchSize) {
        Write-Host "$Name already complete ($done/$Steps steps) - skipping." -ForegroundColor DarkGray
        return
    }

    $args_ = @("train_torch.py", "--save", $SaveCkpt, "--timesteps", $remaining) + $StageArgs + $geom

    if ($done -gt 0) {
        Write-Host "$Name resuming $SaveCkpt at $done/$Steps steps ($remaining to go)."
    } elseif (Test-Path $PrevCkpt) {
        if ($WarmStart) {
            Write-Host "$Name warm-starting from $PrevCkpt (cross-kind handoff)"
            $args_ += @("--warm-start", $PrevCkpt)
        } else {
            Write-Host "$Name seeding from $PrevCkpt"
            $args_ += @("--resume", $PrevCkpt)
        }
    }

    # The warmup buys a critic rescaled to this stage's returns; a resume has
    # already served some or all of those iterations, and re-freezing the actor
    # for another full warmup is pure loss.
    if ($CriticWarmup -gt 0) {
        $served = [long][math]::Floor($done / $batchSize)
        $warm = $CriticWarmup - $served
        if ($warm -gt 0) {
            $args_ += @("--critic-warmup", $warm)
            if ($served -gt 0) { Write-Host "  critic warmup: $warm of $CriticWarmup iters left" }
        } else {
            Write-Host "  critic warmup already served ($CriticWarmup iters)"
        }
    }

    # anneal_fraction restarts over each invocation's own budget, so a resumed
    # anneal has to START where the interruption left it rather than back at
    # --ent-coef.
    if ($EntCoef -gt 0) {
        $start = $EntCoef
        if ($done -gt 0 -and $EntCoefFinal -gt 0) {
            $start = $EntCoef + ($EntCoefFinal - $EntCoef) * ($done / $Steps)
            Write-Host ("  entropy anneal resumes at {0:g4} (of {1:g4} -> {2:g4})" -f $start, $EntCoef, $EntCoefFinal)
        }
        $args_ += @("--ent-coef", $start.ToString("0.########", [Globalization.CultureInfo]::InvariantCulture))
        if ($EntCoefFinal -gt 0) {
            $args_ += @("--ent-coef-final", $EntCoefFinal.ToString("0.########", [Globalization.CultureInfo]::InvariantCulture))
        }
    }

    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) {
        Write-Host "$Name failed (exit $code). Stopping." -ForegroundColor Red
        exit $code
    }
}

function Invoke-Eval {
    param([string]$Name, [string]$Ckpt, [int]$Asc, [int]$Episodes, [string]$Csv)
    if ($Smoke) { Write-Host "$Name skipped (smoke mode)"; return }
    $args_ = @("eval.py", $Ckpt, "--env", "run", "--episodes", "$Episodes",
               "--baselines", "--ascension", "$Asc", "--csv", $Csv)
    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) { Write-Host "$Name exited $code (continuing)" -ForegroundColor Yellow }
}

# $prevKind tracks which env kind $prev was actually trained on, so each
# Invoke-Stage call below passes -WarmStart exactly when the handoff crosses
# kinds (v8's pattern). In v11 both boundaries cross by design.
$prev = $SeedCkpt
$prevKind = "run"          # $SeedCkpt (runs/sts2_run_torch_v10_s10.pt) is run-scale

# ── s12: combat drill, asc 10, elite/boss snapshot starts ──────────────────
# The warm-start INTO combat keeps vocab tables, shared encoder blocks, the
# combat heads and the deep trunk; run-only heads/segments are dropped here
# and rebuilt fresh at s13 — that round trip is the REST_SMITH reset.
# Native HP-delta combat reward; NO run-only flags, NO aux, default lambda.
Invoke-Stage -Name "s12-combat-asc10-eliteboss" -SaveCkpt $ckpt[12] -PrevCkpt $prev `
    -Steps $S12Steps -StageArgs @(
    "--env", "combat", "--ascension", "10",
    "--start-snapshots", $SnapshotPath, "--lr", "3e-4") -WarmStart:($prevKind -ne "combat")
$prev = $ckpt[12]
$prevKind = "combat"

# ── s13: run rebuild, asc 10 — the reset moment ────────────────────────────
# Fresh run heads sample the campfire menu near-uniformly; REST_SMITH now
# earns +1.5/upgrade under a critic warmed up on the rescaled returns.
Invoke-Stage -Name "s13-run-asc10-rebuild" -SaveCkpt $ckpt[13] -PrevCkpt $prev `
    -Steps $S13Steps -CriticWarmup 15 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards + $longHorizon) `
    -WarmStart:($prevKind -ne "run")
$prevKind = "run"

Invoke-Eval -Name "s13-eval-asc10" -Ckpt $ckpt[13] -Asc 10 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s13_asc10"
Invoke-Eval -Name "s13-eval-asc0" -Ckpt $ckpt[13] -Asc 0 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s13_asc0"

Write-Host "v11 complete. Gate table: docs/superpowers/plans/v11-run-log.md" -ForegroundColor Green
```

- [ ] **Step 2: Parse check (native PowerShell tool, NOT nested through Bash)**

Run via the PowerShell tool:

```powershell
$t = Get-Content -Raw c:\Users\Perry\Desktop\sts2-rl\train_curriculum_v11.ps1; [ScriptBlock]::Create($t) | Out-Null; 'parse ok'
```

Expected: `parse ok` (a parse error throws instead).

- [ ] **Step 3: Smoke run (native PowerShell tool; allowed — `-Smoke` only)**

Run via the PowerShell tool from `c:\Users\Perry\Desktop\sts2-rl` with a 600000 ms timeout:

```powershell
.\train_curriculum_v11.ps1 -Smoke
```

Expected: both stages run 65536 steps and exit 0 — the s12 line prints `warm-starting from runs/sts2_run_torch_v10_s10.pt (cross-kind handoff)` and s13 prints `warm-starting from ...v11smoke_s12.pt (cross-kind handoff)` (both boundaries MUST warm-start — that is the mechanism under test); evals print `skipped (smoke mode)`; final line `v11 complete...`. If it exceeds the timeout, re-run with `run_in_background` and wait. This smoke also transitively exercises Task 2's flag (`--reward-boss 3` inside `$runRewards`) and Task 3's corpus end-to-end on the real training path.

- [ ] **Step 4: Clean up smoke artifacts**

```powershell
Remove-Item c:\Users\Perry\Desktop\sts2-rl\runs\*v11smoke* -Confirm:$false
```

- [ ] **Step 5: Stage (never commit)**

```bash
git add train_curriculum_v11.ps1
```

---

### Task 5: `v11-run-log.md`, v10 rung retirement, full suite

**Files:**
- Create: `docs/superpowers/plans/v11-run-log.md`
- Modify: `docs/superpowers/plans/v10-run-log.md` (append ONE log entry; touch nothing else in it)

**Interfaces:**
- Consumes: the spec's gate table (§4), Task 3's filter command (recorded verbatim so the corpus can be regenerated), Task 4's launch commands.
- Produces: the run log Perry fills after launching; the superseded-rung record in the v10 log.

- [ ] **Step 1: Write `docs/superpowers/plans/v11-run-log.md`**

```markdown
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

## Gates (reference = v10 s10 / v9 s9 / v8 s7 evals)

| Stage | Gate | Result | Verdict |
|---|---|---|---|
| s12 (train CSV, report-only) | drill `ep_ret` rising; `win` on drill fights rising. No run-scale eval — the ckpt is combat-kind | | |
| s13 (150 eps, asc 10) | **rest_upgrades > 0 — THE question** (any nonzero = the reset worked); floor ≥ 20.1 (recovery to v9 s9; v10 s10's 22.26 is the report line, not the gate); `aux` CSV column falling over s13 (checkable post-hoc since the v10 session added it) | | |
| s13 (150 eps, asc 0) | win ≥ 3.3% (v8 s7 level; v9 s9: 1.33%); floor report vs 31.44 | | |
| potions (both arms) | report-only at k 0.15: potions_used/ep and hp_at_use vs hp_overall — no gate, the price-knob experiment is over | | |

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
```

- [ ] **Step 2: Append the rung-retirement entry to `docs/superpowers/plans/v10-run-log.md`**

Append exactly this to the end of its `## Log` section (touch nothing else in the file; `train_curriculum_v10.ps1` itself stays untouched as the historical record):

```markdown
- 2026-08-14 (later still): the staged s11-lowshare rung is RETIRED before
  running — superseded by v11 (spec 2026-08-14-v11-combat-detour-design.md,
  run log v11-run-log.md): the reward rebalance (upgrade 1.5 / elite 3 /
  boss 3) invalidates the rung's single-knob premise, and the combat-detour
  warm-start round trip is the structural exploration fix the ladder's
  post-scalar escalation called for. `train_curriculum_v10.ps1` stays as the
  historical record; nothing further runs under the v10 tag.
```

- [ ] **Step 3: Full suite**

Run: `.venv\Scripts\python.exe -m pytest -q --ignore=test/test_train_io.py --ignore=test/test_live_onnx.py`
Expected: 0 failed, 4 xfailed, everything else passed (5086 passed before this plan; the new v11 test files add ~9).

- [ ] **Step 4: Stage (never commit)**

```bash
git add docs/superpowers/plans/v11-run-log.md docs/superpowers/plans/v10-run-log.md docs/superpowers/plans/2026-08-14-v11-combat-detour.md docs/superpowers/specs/2026-08-14-v11-combat-detour-design.md
```
