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
$root = Split-Path $PSScriptRoot -Parent  # scripts/ sits one level below repo root
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
                # v11.1 (added 2026-08-14 AFTER s13's first 4M ran without
                # it): +1 per elite room ENTERED, win or lose -- reward_elite
                # pays only on wins, so the pathing choice itself earned
                # nothing when the fight was lost. Perry raised the planned
                # 0.2 to 1; below ~12.5% HP the entry pay exceeds the
                # remaining death penalty (see v12-run-log.md's elite-diving
                # report gate). Extension runs moved to train_curriculum_v12
                # -- the v11 tag is closed.
                "--reward-elite-attempt", "1",
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
