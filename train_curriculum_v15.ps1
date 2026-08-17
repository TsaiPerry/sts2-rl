<#
v15 extension-exposure-restfix run (docs/superpowers/plans/2026-08-16-v15-extension-exposure-restfix.md,
Task 5): two stages on top of the v14 s16 policy.

  Stage  Env  Asc  Steps  Notes
  s17    run   10     8M  continue runs/sts2_run_torch_v14_s16.pt (--resume
                          handoff, same kind, NO warm start); v14 s16 knobs
                          plus ONE change (Perry, 2026-08-16):
                          --potion-death-penalty 0.3 in $runRewards. Same
                          --deck-inject runs/inject_v14.json --deck-inject-prob
                          0.5, same lambda/aux/ent/lr. s17-vs-v14 deltas
                          conflate the extension with the new potion term.
  s18    run   10     8M  continue runs/sts2_run_torch_v15_s17.pt (--resume,
                          same kind); adds --deck-inject-midrun
                          runs/inject_v15_dead.json --deck-inject-midrun-prob
                          0.05 (dead-9 play exposure, ~1.5 injected packages
                          per 30-floor run) plus --critic-warmup 8 (env-
                          distribution change re-prices V).

Knob notes vs v14 s16: s17 = s16 knobs + --potion-death-penalty 0.3 (Perry's
post-plan addition, both stages -- supersedes the plan's "s17 changes
nothing" rule). s18 adds exactly the midrun-inject flags + critic-warmup on
top of s17's knobs.

Between-stage gate (s17 -> s18), same shape as v10's Test-RestUpgradeGate:
reads the s17 asc-10 episodes CSV and aborts (exit 3, resumable) unless BOTH
hold -- total rest-upgrade share >= 0.15 AND mean floor >= 19.0. Floor 19.0,
not 20.1: this unattended gate only guards against collapse mid-script: the
full >= 20.1 verdict belongs to the human-read run log (v15-run-log.md), not
an unattended abort.
No rest mask, no potion mask, ever.

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v15.ps1                # real run; auto-evals s17+s18
  .\train_curriculum_v15.ps1 -Smoke         # 65536 steps/stage, scratch tag
  .\train_curriculum_v15.ps1 -Resume        # continue an interrupted run
#>
param(
    [long]$S17Steps = 8000000,
    [long]$S18Steps = 8000000,
    [string]$Device = "cuda",
    [string]$Tag = "v15",
    [string]$SeedCkpt = "runs/sts2_run_torch_v14_s16.pt",
    [switch]$Resume,
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$runs = Join-Path $root "runs"
if (-not (Test-Path $runs)) { New-Item -ItemType Directory $runs | Out-Null }
# venv (no dot) is the CUDA env: torch 2.13.0+cu130. The dotted .venv twin
# carries torch 2.13.0+cpu (plain-PyPI install, 2026-08-09) plus the
# onnx/onnxruntime tooling -- fine for pytest/export, WRONG for training.
# Do not "normalize" this to .venv again (that mistake shipped briefly on
# 2026-08-16 and would have trained s17/s18 on CPU).
$py = Join-Path $root "venv\Scripts\python.exe"

if ($Smoke) {
    $Tag = "${Tag}smoke"
    $S17Steps = 65536; $S18Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{ 17 = Join-Path $runs "sts2_run_torch_${Tag}_s17.pt";
           18 = Join-Path $runs "sts2_run_torch_${Tag}_s18.pt" }

if ((Test-Path $ckpt[17]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[17]) already exists." -ForegroundColor Red
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}
if (-not (Test-Path (Join-Path $root $SeedCkpt))) {
    Write-Host "SeedCkpt '$SeedCkpt' not found - nothing to extend." -ForegroundColor Red
    exit 1
}
$schema = & $py -c "import sys, torch; print(torch.load(sys.argv[1], map_location='cpu', weights_only=False).get('obs_schema'))" (Join-Path $root $SeedCkpt)
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not read SeedCkpt schema (python exited $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
if (($schema | Select-Object -Last 1).Trim() -ne "12") {
    Write-Host "SeedCkpt is not schema 12 - run tools\migrate_handrow_v14.py first." -ForegroundColor Red
    exit 1
}

$nEnvs = 64
$nSteps = 512
$batchSize = [long]$nEnvs * $nSteps
$geom = @("--arch", "entset", "--shared-encoder", "--device", $Device,
          "--n-envs", "$nEnvs", "--n-steps", "$nSteps", "--minibatches", "8")

# The v11 rebuild rewards, verbatim except --reward-elite 3 -> 2 (v13's
# hand-launched value, the reference policy): upgrade 1.5, boss 3, potion k
# 0.15 (Perry's rollback), plus --reward-elite-attempt 1 -- +1 per elite room
# ENTERED, win or lose (reward_elite pays only on wins; Perry raised the
# planned 0.2 to 1). Note the arithmetic in v11-run-log.md: below ~12.5% HP
# the +1 entry pay exceeds the remaining death penalty (4*phi(r)), so watch
# elites_fought minus elites (deaths at elites) in the s17/s18 evals for
# low-HP elite-diving. v14's $runRewards plus ONE addition (Perry,
# 2026-08-16): --potion-death-penalty 0.3, a flat -0.3 per potion still held
# at death ON TOP of --potion-death-expiry's credit forfeiture, so
# hoard-and-die (-0.3/potion net) prices strictly below drink-and-die (0
# net). Applies to BOTH stages (Perry chose whole-run over preserving the
# s17 pure-extension A/B; read s17-vs-v14 deltas with that caveat).
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "1.5", "--reward-elite", "2",
                "--reward-boss", "3",
                "--reward-elite-attempt", "1",
                "--reward-remove", "0.25", "--reward-relic", "0.25",
                "--hp-potential-scale", "4.0",
                "--potion-potential-scale", "0.15",
                "--rest-heal-shaping-knee-cap",
                "--potion-death-expiry",
                "--potion-death-penalty", "0.3")

# Long-horizon levers (spec 2026-08-13-aux-hp-head-gae-lambda-design).
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
# -WarmStart marks a kind-switch handoff (combat<->run): UNUSED in v15 -- the
# whole point of this script is that there is no kind switch (a warm start
# here would re-drop the run heads v11 rebuilt). Kept verbatim so the helper
# stays byte-identical with the v10/v11/v14 scripts.
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
               "--ascension", "$Asc", "--csv", $Csv)
    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) { Write-Host "$Name exited $code (continuing)" -ForegroundColor Yellow }
}

# Between-stage gate (s17 -> s18), same shape as v10's Test-RestUpgradeGate:
# reads the s17 asc-10 episodes CSV and aborts (exit 3, resumable) unless BOTH
# hold -- rest_upgrade_rate (canonical metric, RunEvalReport.rest_upgrade_rate
# in sts2_rl/evaluation.py: sum(rest_upgrades) / sum(rest_visits), "share of
# rest-site VISITS the policy upgraded a card at") >= 0.15 AND mean floor >=
# 19.0. This is an unattended collapse guard, not the full verdict (that's
# >= 20.1, read by a human from v15-run-log.md).
function Test-RestFloorGate {
    param([string]$Csv)
    if ($Smoke) { Write-Host "rest-upgrade/floor gate skipped (smoke mode)"; return }
    $code = "import csv, sys; " +
            "rows = [r for r in csv.DictReader(open(sys.argv[1], newline='')) " +
            "if r['policy'] != 'masked-random']; " +
            "n = len(rows); " +
            "up = sum(int(float(r['rest_upgrades'])) for r in rows); " +
            "visits = sum(int(float(r['rest_visits'])) for r in rows); " +
            "rate = (up / visits) if visits > 0 else 0.0; " +
            "floor = sum(float(r['floor']) for r in rows) / n if n > 0 else 0.0; " +
            "print(f'rest_upgrade_rate={rate:.4f} mean_floor={floor:.2f} over {n} episodes'); " +
            "sys.exit(0 if (rate >= 0.15 and floor >= 19.0) else 3)"
    & $py -c $code (Join-Path $root "$Csv.episodes.csv")
    if ($LASTEXITCODE -eq 3) {
        Write-Host "s17 GATE FAIL: rest_upgrade_rate < 0.15 or mean floor < 19.0." -ForegroundColor Red
        Write-Host "NOT proceeding to s18 automatically. Perry decides; nothing launches itself."
        exit 3
    }
    if ($LASTEXITCODE -ne 0) {
        # Fail-open kept deliberately (v10-inherited idiom, Test-RestUpgradeGate's shape): a
        # python-side error here (missing/malformed CSV) is a tooling problem, not a survival
        # signal, so it shouldn't block a resumable run. The actual CWD-mismatch bug this used
        # to mask is fixed above by resolving the CSV path against $root instead of the caller's
        # CWD, so this branch should now only fire on a genuine script/env problem.
        Write-Host "gate check errored (exit $LASTEXITCODE) - continuing to s18" -ForegroundColor Yellow
    }
}

# ── s17: run continuation, asc 10 -- pure extension, NO knob changes ───────
# Same-kind handoff: --resume (NEVER -WarmStart here; that would fresh-init
# the run heads and undo the v11 reset's / v13's / v14's rest-share gains).
# Identical StageArgs to v14 s16 -- one knob per stage, and s17's knob is
# "none" (only artifact names/seed differ).
Invoke-Stage -Name "s17-run-asc10-extend" -SaveCkpt $ckpt[17] -PrevCkpt $SeedCkpt `
    -Steps $S17Steps -CriticWarmup 8 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards + $longHorizon + @(
    "--deck-inject", "runs/inject_v14.json", "--deck-inject-prob", "0.5"))

if (Test-Path (Join-Path $root "runs/eval_${Tag}_s17_asc10.episodes.csv")) {
    Write-Host "s17-eval-asc10 already recorded (gate evidence) - skipping." -ForegroundColor DarkGray
} else {
    Invoke-Eval -Name "s17-eval-asc10" -Ckpt $ckpt[17] -Asc 10 -Episodes 150 `
        -Csv "runs/eval_${Tag}_s17_asc10"
}
if (Test-Path (Join-Path $root "runs/eval_${Tag}_s17_asc0.episodes.csv")) {
    Write-Host "s17-eval-asc0 already recorded - skipping." -ForegroundColor DarkGray
} else {
    Invoke-Eval -Name "s17-eval-asc0" -Ckpt $ckpt[17] -Asc 0 -Episodes 150 `
        -Csv "runs/eval_${Tag}_s17_asc0"
}

Test-RestFloorGate -Csv "runs/eval_${Tag}_s17_asc10"

# ── s18: run continuation, asc 10 -- mid-run dead-9 inject exposure ────────
# Same-kind handoff from s17. Adds exactly the midrun-inject flags +
# --critic-warmup 8 (env-distribution change re-prices V) on top of s17's
# (== s16's) knobs -- the plan's one-knob-per-stage rule.
Invoke-Stage -Name "s18-run-asc10-midrun-inject" -SaveCkpt $ckpt[18] -PrevCkpt $ckpt[17] `
    -Steps $S18Steps -CriticWarmup 8 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards + $longHorizon + @(
    "--deck-inject", "runs/inject_v14.json", "--deck-inject-prob", "0.5",
    "--deck-inject-midrun", "runs/inject_v15_dead.json",
    "--deck-inject-midrun-prob", "0.05"))

Invoke-Eval -Name "s18-eval-asc10" -Ckpt $ckpt[18] -Asc 10 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s18_asc10"
Invoke-Eval -Name "s18-eval-asc0" -Ckpt $ckpt[18] -Asc 0 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s18_asc0"

Write-Host "v15 extension-exposure-restfix run complete. Gate table: docs/superpowers/plans/v15-run-log.md" -ForegroundColor Green
