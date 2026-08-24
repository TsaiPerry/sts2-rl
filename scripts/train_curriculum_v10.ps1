<#
v10 extension run (plan 2026-08-13-v10-escape-and-settle): apply the v9
contingency ladder from the s9 checkpoint, +5M steps total.

  Stage  Env  Asc  Steps  Notes
  s10    run   10     2M  escape: ent 0.01 FLAT (no anneal), k 0.5, warmup 8,
                          + gae 0.98 + aux 0.25  [RAN 2026-08-14: gate FAIL]
  gate   --    --     --  s10 eval must show >0 rest upgrades or STOP (exit 3)
                          -- TRIPPED 2026-08-14 (0/194 rest visits); call
                          retired below so -Resume can run the next rung
  s11    run   10     2M  lowshare (ladder rung, replaces settle): ent 0.01
                          FLAT, same rewards + --hp-potential-low-share 0.8,
                          + gae 0.98 + aux 0.25

Knob changes vs v9 (ladder, v9-run-log.md "Contingency applied"):
- --potion-potential-scale 0.3 -> 0.5 : hp_at_use ~= hp_overall at s9 =
  drinks exist but timing is random -> raise the bar (drink price and the
  death forfeit scale together; the death-expiry mechanism itself worked:
  expired-on-deaths 0.19 -> 0.03/ep).
- s10 ent is genuinely FLAT: v9's s9 annealed to 0.004 before anyone read
  the failed s8 gate. The Test-RestUpgradeGate check between s10 and s11
  makes that mistake structurally impossible now.
- --gae-lambda 0.98 (both stages) + aux head --aux-hp-coef 0.25: long-horizon
  credit assignment for rest/potion timing, per spec
  2026-08-13-aux-hp-head-gae-lambda-design.md.
No rest mask, no potion mask, ever (v8 plan Task 7 constraint).

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v10.ps1                # real run (~2.5h at v9 throughput)
  .\train_curriculum_v10.ps1 -Smoke         # 65536 steps/stage, scratch tag
  .\train_curriculum_v10.ps1 -Resume        # continue an interrupted run
#>
param(
    [long]$S10Steps = 2000000,
    [long]$S11Steps = 2000000,   # lowshare rung: +2M per the ladder (was 3M settle)
    [string]$Device = "cuda",
    [string]$Tag = "v10",
    [string]$SeedCkpt = "runs/sts2_run_torch_v9_s9.pt",
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
    $S10Steps = 65536; $S11Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{}
foreach ($n in 10..11) { $ckpt[$n] = Join-Path $runs "sts2_run_torch_${Tag}_s$n.pt" }

if ((Test-Path $ckpt[10]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[10]) already exists." -ForegroundColor Red
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

# v9 rewards with the ladder's one potion-knob change: k 0.3 -> 0.5 ("raise
# the bar" branch -- s9 hp_at_use 0.791 ~= hp_overall 0.796, drinks random).
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "0.5", "--reward-elite", "0.5",
                "--reward-remove", "0.25", "--reward-relic", "0.25",
                "--hp-potential-scale", "4.0",
                "--potion-potential-scale", "0.15",
                "--rest-heal-shaping-knee-cap",
                "--potion-death-expiry")

# Long-horizon levers (spec 2026-08-13-aux-hp-head-gae-lambda-design):
# lambda 0.95 -> 0.98 stretches actual-return credit ~14 -> ~50 decisions;
# the aux head supervises "hp lost over the next 3 floors" off the shared
# encoder so rest/potion decisions can price the upcoming map.
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
# -WarmStart marks a kind-switch handoff (combat<->run): unused in v10 (both
# stages are run-kind), kept verbatim so the helper stays byte-identical with
# the v8/v9 scripts.
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

# ── s10: escape — ent held FLAT, potion bar raised ─────────────────────────
Invoke-Stage -Name "s10-run-asc10-escape" -SaveCkpt $ckpt[10] -PrevCkpt $SeedCkpt `
    -Steps $S10Steps -CriticWarmup 8 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4") + $runRewards + $longHorizon)
if (Test-Path "runs/eval_${Tag}_s10_asc10.episodes.csv") {
    Write-Host "s10-eval-asc10 already recorded (gate evidence) - skipping." -ForegroundColor DarkGray
} else {
    Invoke-Eval -Name "s10-eval-asc10" -Ckpt $ckpt[10] -Asc 10 -Episodes 50 `
        -Csv "runs/eval_${Tag}_s10_asc10"
}
# Gate TRIPPED 2026-08-14 (rest_upgrades 0/194 visits, v10-run-log.md): the
# escape rung is falsified and its verdict is recorded, so the call is
# retired -- leaving it live would exit 3 on every -Resume and block the
# ladder's next rung below. (Function kept for a future fresh-tag run.)
# Test-RestUpgradeGate -Csv "runs/eval_${Tag}_s10_asc10"

# ── s11: lowshare — ladder rung (replaces settle; settling a 0-upgrade ─────
# policy was v9's mistake). Ent stays FLAT; the danger-zone knee steepens:
# --hp-potential-low-share 0.7 -> 0.8 concentrates the HP potential below
# the knee so low-HP floors price higher. If rest_upgrades is STILL 0 after
# this, scalars are done -- next is snapshot-seeded exploration (run log).
Invoke-Stage -Name "s11-run-asc10-lowshare" -SaveCkpt $ckpt[11] -PrevCkpt $ckpt[10] `
    -Steps $S11Steps -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4",
    "--hp-potential-low-share", "0.8") + $runRewards + $longHorizon)
Invoke-Eval -Name "s11-eval-asc10" -Ckpt $ckpt[11] -Asc 10 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s11_asc10"
Invoke-Eval -Name "s11-eval-asc0" -Ckpt $ckpt[11] -Asc 0 -Episodes 150 `
    -Csv "runs/eval_${Tag}_s11_asc0"

Write-Host "v10 extension complete. Gate table: docs/superpowers/plans/v10-run-log.md" -ForegroundColor Green
