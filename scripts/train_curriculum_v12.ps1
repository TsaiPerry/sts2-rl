<#
v12 extension run: v11 minus the combat detour, with a bigger budget. The
v11 round trip already did its one job — the fresh run heads revived
REST_SMITH (104 upgrades/356 rest visits at s13, after three generations of
exactly 0) — but s13's 4M ended with train ep_ret still climbing and the
capability gates unmet (asc-10 floor 14.24 vs >=20.1). v12 continues that
SAME policy in the run env only; re-running a combat stage here would
warm-start run->combat and drop every run-only head, erasing exactly the
run knowledge v11 bought.

  Stage  Env  Asc  Steps  Notes
  s14    run   10     8M  continue runs/sts2_run_torch_v11_s13.pt (--resume
                          handoff, same kind, NO warm start); same rewards
                          as the v11 rebuild incl. --reward-elite-attempt 1
                          (raised from 0.2 by Perry before this run — the
                          first 4M of s13 trained without the term at all)

Knob notes vs v11 s13:
- Same $runRewards / lambda 0.98 / aux 0.25 / ent FLAT 0.01 / lr 3e-4.
- --critic-warmup 8 (not 15): the heads are no longer fresh; the small
  warmup only re-prices the reward delta (elite-attempt 0 -> 1), v10's
  same-kind-extension precedent.
- Gates to read post-run (docs/superpowers/plans/v12-run-log.md): does the
  rest-upgrade share SURVIVE continued training, and does floor recover?
No rest mask, no potion mask, ever.

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v12.ps1                # real run; auto-evals s14
  .\train_curriculum_v12.ps1 -Smoke         # 65536 steps, scratch tag
  .\train_curriculum_v12.ps1 -Resume        # continue an interrupted run
#>
param(
    [long]$S14Steps = 8000000,
    [string]$Device = "cuda",
    [string]$Tag = "v12",
    [string]$SeedCkpt = "runs/sts2_run_torch_v11_s13.pt",
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
    $S14Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{ 14 = Join-Path $runs "sts2_run_torch_${Tag}_s14.pt" }

if ((Test-Path $ckpt[14]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[14]) already exists." -ForegroundColor Red
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

# The v11 rebuild rewards, verbatim: upgrade 1.5, elite 3, boss 3, potion k
# 0.15 (Perry's rollback), plus --reward-elite-attempt 1 — +1 per elite room
# ENTERED, win or lose (reward_elite pays only on wins; Perry raised the
# planned 0.2 to 1). Note the arithmetic in v11-run-log.md: below ~12.5% HP
# the +1 entry pay exceeds the remaining death penalty (4*phi(r)), so watch
# elites_fought minus elites (deaths at elites) in the s14 evals for
# low-HP elite-diving.
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "1.5", "--reward-elite", "3",
                "--reward-boss", "3",
                "--reward-elite-attempt", "1",
                "--reward-remove", "0.25", "--reward-relic", "0.25",
                "--hp-potential-scale", "4.0",
                "--potion-potential-scale", "0.15",
                "--rest-heal-shaping-knee-cap",
                "--potion-death-expiry")

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
# -WarmStart marks a kind-switch handoff (combat<->run): UNUSED in v12 — the
# whole point of this script is that there is no kind switch (a warm start
# here would re-drop the run heads v11 just rebuilt). Kept verbatim so the
# helper stays byte-identical with the v10/v11 scripts.
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

# ── s14: run continuation, asc 10 — capability recovery on live heads ──────
# Same-kind handoff: --resume (NEVER -WarmStart here; that would fresh-init
# the run heads and undo the v11 reset's gains).
Invoke-Stage -Name "s14-run-asc10-continue" -SaveCkpt $ckpt[14] -PrevCkpt $SeedCkpt `
    -Steps $S14Steps -CriticWarmup 8 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards + $longHorizon)

Invoke-Eval -Name "s14-eval-asc10" -Ckpt $ckpt[14] -Asc 10 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s14_asc10"
Invoke-Eval -Name "s14-eval-asc0" -Ckpt $ckpt[14] -Asc 0 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s14_asc0"

Write-Host "v12 extension complete. Gate table: docs/superpowers/plans/v12-run-log.md" -ForegroundColor Green
