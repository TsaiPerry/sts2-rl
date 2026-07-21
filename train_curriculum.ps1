<#
Five-stage curriculum training, unattended.

  Stage 1  --env column  --branch-prob 0.00  5M steps  (pure single-column)
  Stage 2  --env column  --branch-prob 0.25  3M steps
  Stage 3  --env column  --branch-prob 0.50  3M steps
  Stage 4  --env column  --branch-prob 0.75  3M steps
  Stage 5  --env run                         15M steps (full branching maps)

Each stage resumes the previous stage's checkpoint. One checkpoint per stage
(..._s1.pt … sts2_run_torch_<tag>.pt), so each gets its own CSV and doubles
as a rollback point. Total 29M steps, wall clock ~13h on this machine.

Stage 5 switches env kind because env_kind is stamped into the checkpoint and
eval.py reads it — the evaluated artifact should be a genuine run checkpoint.
By stage 4 the policy is already seeing 75% branching maps, so the switch is
distributionally near-invisible.

Re-running is safe: each stage auto-resumes its own --save checkpoint, and
only hands off from the prior stage the first time.

  py -m pytest test/ -q          # green before launching, please
  .\train_curriculum.ps1         # real run
  .\train_curriculum.ps1 -S1Steps 33000 -S2Steps 33000 -S3Steps 33000 -S4Steps 33000 -RunSteps 33000 -Tag smoke
#>
param(
    [long]$S1Steps  = 7000000,
    [long]$S2Steps  = 3000000,
    [long]$S3Steps  = 3000000,
    [long]$S4Steps  = 3000000,
    [long]$RunSteps = 13000000,
    # Off by default: both envs use the SAME floor-only reward (STS2RunEnv's
    # defaults; the curriculum env overrides no reward parameter), so the
    # critic's scale carries over and advantages are not mis-signed. What does
    # shift is the state distribution — branching maps, real MAP choices, a
    # non-degenerate run.map.grid. Reach for a warm-up only if stage 5's early
    # value loss spikes.
    [int]$CriticWarmup = 0,
    [string]$Device    = "cuda",
    # Checkpoint name suffix. Defaults to a NEW name so a fresh curriculum
    # cannot auto-resume the previous generation's runs/sts2_*_torch.pt.
    [string]$Tag       = "v5",
    # Required to continue an interrupted run: without it, an existing stage-1
    # checkpoint is treated as an accident rather than a resume point.
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$runs = Join-Path $root "runs"
if (-not (Test-Path $runs)) { New-Item -ItemType Directory $runs | Out-Null }

$suffix  = if ($Tag) { "_$Tag" } else { "" }
$s1Ckpt  = Join-Path $runs "sts2_column_torch${suffix}_s1.pt"
$s2Ckpt  = Join-Path $runs "sts2_column_torch${suffix}_s2.pt"
$s3Ckpt  = Join-Path $runs "sts2_column_torch${suffix}_s3.pt"
$s4Ckpt  = Join-Path $runs "sts2_column_torch${suffix}_s4.pt"
$runCkpt = Join-Path $runs "sts2_run_torch$suffix.pt"

# train_torch.py auto-resumes whatever sits at --save. That is what makes this
# script restartable, and also what would silently continue a PREVIOUS model
# instead of training a fresh one — so an existing checkpoint has to be an
# explicit choice.
if ((Test-Path $s1Ckpt) -and -not $Resume) {
    Write-Host "$s1Ckpt already exists." -ForegroundColor Red
    Write-Host "Training it further would continue that model, not start a fresh run."
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint pair."
    exit 1
}

# Shared across all stages. n-envs/n-steps are passed explicitly on stage 1 so
# the geometry is recorded in the checkpoint; later stages inherit it on resume.
$common = @("--arch", "entity", "--device", $Device,
            "--n-envs", "32", "--n-steps", "512")

function Invoke-Phase {
    param([string]$Name, [string[]]$PhaseArgs)

    Write-Host "[$(Get-Date -Format s)] $Name starting"

    # Start-Process -NoNewWindow without redirect flags: output prints to the
    # console in real time (the original script redirected to log files, which
    # hid it).  Per-stage CSV files (<stem>.csv) capture all training metrics.
    $p = Start-Process -FilePath "py" -ArgumentList $PhaseArgs `
                       -WorkingDirectory $root -NoNewWindow -Wait -PassThru
    Write-Host "[$(Get-Date -Format s)] $Name exited $($p.ExitCode)"
    return $p.ExitCode
}

# Helper: run a column stage, resuming from $PrevCkpt if this stage's own
# checkpoint doesn't already exist.
function Invoke-ColumnStage {
    param([string]$Name, [string]$SaveCkpt, [string]$PrevCkpt,
          [long]$Steps, [double]$BranchProb)

    $args_ = @("train_torch.py", "--env", "column",
               "--timesteps", $Steps,
               "--branch-prob", $BranchProb,
               "--save", $SaveCkpt) + $common
    if (-not (Test-Path $SaveCkpt) -and (Test-Path $PrevCkpt)) {
        $args_ += @("--resume", $PrevCkpt)
    }
    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) {
        Write-Host "$Name failed (exit $code). Stopping." -ForegroundColor Red
        exit $code
    }
}

# ── Stage 1: pure column (branch_prob=0.00) ──────────────────────────────
$s1Args = @("train_torch.py", "--env", "column",
            "--timesteps", $S1Steps,
            "--branch-prob", "0.0",
            "--save", $s1Ckpt) + $common
$code = Invoke-Phase -Name "s1-column-bp0.00" -PhaseArgs $s1Args
if ($code -ne 0) {
    Write-Host "Stage 1 failed (exit $code). Stopping." -ForegroundColor Red
    exit $code
}

# ── Stage 2: branch_prob=0.25 ────────────────────────────────────────────
Invoke-ColumnStage -Name "s2-column-bp0.25" -SaveCkpt $s2Ckpt `
                   -PrevCkpt $s1Ckpt -Steps $S2Steps -BranchProb 0.25

# ── Stage 3: branch_prob=0.50 ────────────────────────────────────────────
Invoke-ColumnStage -Name "s3-column-bp0.50" -SaveCkpt $s3Ckpt `
                   -PrevCkpt $s2Ckpt -Steps $S3Steps -BranchProb 0.50

# ── Stage 4: branch_prob=0.75 ────────────────────────────────────────────
Invoke-ColumnStage -Name "s4-column-bp0.75" -SaveCkpt $s4Ckpt `
                   -PrevCkpt $s3Ckpt -Steps $S4Steps -BranchProb 0.75

# ── Stage 5: full-run env ────────────────────────────────────────────────
# Same reward function as the column stages — this is a map-distribution
# change, not a reward change. See -CriticWarmup above.
$phase5 = @("train_torch.py", "--env", "run",
            "--timesteps", $RunSteps, "--save", $runCkpt) + $common
if ($CriticWarmup -gt 0) {
    $phase5 += @("--critic-warmup", $CriticWarmup)
}
if (-not (Test-Path $runCkpt)) {
    $phase5 += @("--resume", $s4Ckpt)   # first launch: hand off from stage 4
} else {
    Write-Host "$runCkpt exists - continuing stage 5 rather than re-handing off."
}
$code = Invoke-Phase -Name "s5-run" -PhaseArgs $phase5
exit $code
