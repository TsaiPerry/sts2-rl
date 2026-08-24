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
$root = Split-Path $PSScriptRoot -Parent  # scripts/ sits one level below repo root
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
# -WarmStart marks a kind-switch handoff (combat<->run): the four boundaries
# named in the T6b brief (seed->s0, s0->s1, s4->s5, s5->s6) use
# --warm-start $PrevCkpt instead of --resume $PrevCkpt, since $PrevCkpt was
# trained on the OTHER env kind. Every other handoff (s1->s2->s3->s4, s6->s7)
# is same-kind and keeps plain --resume. It also zeroes the step baseline,
# because train_torch restarts global_step on a warm start.
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
