<#
v7 curriculum: reward redesign + ascension ramp, unattended. (Plan Task 11,
docs/superpowers/plans/2026-08-09-v7-ascension-curriculum.md.)

  Stage   Asc  deck-random  Steps  Extra                       Purpose
  s1        0         0.50     4M  lr 6e-4, critic-warmup 40   reward re-baseline on known
                                                               difficulty; seeds from v6
  s2        4         0.50     5M  lr 6e-4, critic-warmup 15   map/economy ascensions (8 elites,
                                                               80% heal, -gold, -1 belt, Bane)
  s3        7         0.25     5M  lr 6e-4, critic-warmup 15   + inflation, scarcity
  s4       10         0.25     8M  lr 3e-4, critic-warmup 15   + tough/deadly enemies, double boss
  s5       10         0.00    10M  lr 3e-4, ent 0.01->0.004    polish: on-policy decks only,
                                                               entropy anneal

Design notes (from the plan; keep in sync with it):
- Fixed ascension per stage -- no obs field (RUN_OBS_SCHEMA_VERSION stays 11),
  so mixed-asc sampling would be unobservable noise. Difficulty is implicitly
  visible: enemy HP, attack previews, belt slot_exists flags, the Bane card.
- --critic-warmup at EVERY boundary: s1 because the reward scale roughly
  triples (train_torch.py's warmup exists precisely for this), s2-s4 because
  each asc bump shifts the return distribution down.
- --reward-win 12 is ~15% of a full-clear return (~78), vs v6's 6% -- dying
  to the final boss must actually sting.
- Same env_kind="run" throughout, so checkpoints resume freely; the
  checkpoint ascension stamp only WARNS on mismatch (deliberate).
- v6's stage-5 checkpoint is the seed: 35M steps of asc-0 competence is a far
  better prior than --fresh, and the reward change mostly REORDERS good
  behaviors rather than redefining them. If s1 collapses (ep_ret down >50%
  from its start and not recovered in 100 iters): restart s1 --fresh and
  accept the longer schedule.

Each stage saves its own checkpoint (runs/sts2_run_torch_<tag>_sN.pt) with its
own CSV, and hands off from the previous stage's checkpoint only when its own
file doesn't exist yet -- re-running the script resumes wherever it stopped.

  .venv\Scripts\python.exe -m pytest -q      # green before launching, please
  .\train_curriculum_v7.ps1                  # real run
  .\train_curriculum_v7.ps1 -S1Steps 65536 -Tag v7smoke -SeedCkpt runs/sts2_run_torch_v6.pt   # dry run
#>
param(
    [long]$S1Steps = 4000000,
    [long]$S2Steps = 5000000,
    [long]$S3Steps = 5000000,
    [long]$S4Steps = 8000000,
    [long]$S5Steps = 10000000,
    [string]$Device = "cuda",
    # Checkpoint name tag: runs/sts2_run_torch_<tag>_sN.pt.
    [string]$Tag = "v7",
    # Stage 1 seeds from this checkpoint (the v6 run-scale policy). --resume
    # only READS it; every write goes to this script's own --save paths.
    [string]$SeedCkpt = "runs/sts2_run_torch_v6.pt",
    # Required to continue an interrupted run: without it, an existing stage-1
    # checkpoint is treated as an accident rather than a resume point.
    [switch]$Resume,
    # Dry-run helper: run stage 1 ONLY (the plan's dry-run gate).
    [switch]$Stage1Only
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$runs = Join-Path $root "runs"
if (-not (Test-Path $runs)) { New-Item -ItemType Directory $runs | Out-Null }

$py = Join-Path $root ".venv\Scripts\python.exe"

$ckpt = @{}
foreach ($n in 1..5) { $ckpt[$n] = Join-Path $runs "sts2_run_torch_${Tag}_s$n.pt" }

if ((Test-Path $ckpt[1]) -and -not $Resume) {
    Write-Host "$($ckpt[1]) already exists." -ForegroundColor Red
    Write-Host "Training it further would continue that model, not start a fresh v7 run."
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}

# Shared by every stage. The v7 reward terms (Perry's spec): act-scaled floors
# 1.0/1.5/2.0, win 12, upgrade 0.5, elite 0.5, remove 0.25. Geometry is passed
# explicitly on every stage (they resume across ascension bumps, and the
# stamped geometry must not drift).
$common = @("--env", "run", "--arch", "entset", "--shared-encoder",
            "--device", $Device, "--n-envs", "64", "--n-steps", "512",
            "--minibatches", "8",
            "--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
            "--reward-upgrade", "0.5", "--reward-elite", "0.5",
            "--reward-remove", "0.25")

function Invoke-Phase {
    param([string]$Name, [string[]]$PhaseArgs)

    Write-Host "[$(Get-Date -Format s)] $Name starting"
    $p = Start-Process -FilePath $py -ArgumentList $PhaseArgs `
                       -WorkingDirectory $root -NoNewWindow -Wait -PassThru
    Write-Host "[$(Get-Date -Format s)] $Name exited $($p.ExitCode)"
    return $p.ExitCode
}

# One curriculum stage: hands off from $PrevCkpt only when its own --save
# checkpoint doesn't exist yet (first launch); after that it self-resumes.
function Invoke-Stage {
    param([string]$Name, [string]$SaveCkpt, [string]$PrevCkpt,
          [long]$Steps, [int]$Ascension, [double]$DeckRandom,
          [string[]]$Extra)

    $args_ = @("train_torch.py",
               "--timesteps", $Steps,
               "--ascension", $Ascension,
               "--deck-random-prob", $DeckRandom,
               "--save", $SaveCkpt) + $common + $Extra
    if (-not (Test-Path $SaveCkpt) -and (Test-Path $PrevCkpt)) {
        Write-Host "$Name seeding from $PrevCkpt"
        $args_ += @("--resume", $PrevCkpt)
    } elseif (Test-Path $SaveCkpt) {
        Write-Host "$SaveCkpt exists - continuing it rather than re-handing off."
    }
    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) {
        Write-Host "$Name failed (exit $code). Stopping." -ForegroundColor Red
        exit $code
    }
}

# ── s1: asc 0, reward re-baseline (seeds from the v6 checkpoint) ──────────
Invoke-Stage -Name "s1-asc0" -SaveCkpt $ckpt[1] -PrevCkpt $SeedCkpt `
             -Steps $S1Steps -Ascension 0 -DeckRandom 0.50 `
             -Extra @("--lr", "6e-4", "--critic-warmup", "40")
if ($Stage1Only) {
    Write-Host "-Stage1Only set: stopping after s1 (dry-run gate)."
    exit 0
}

# ── s2: asc 4, map/economy ascensions ────────────────────────────────────
Invoke-Stage -Name "s2-asc4" -SaveCkpt $ckpt[2] -PrevCkpt $ckpt[1] `
             -Steps $S2Steps -Ascension 4 -DeckRandom 0.50 `
             -Extra @("--lr", "6e-4", "--critic-warmup", "15")

# ── s3: asc 7, + inflation/scarcity ──────────────────────────────────────
Invoke-Stage -Name "s3-asc7" -SaveCkpt $ckpt[3] -PrevCkpt $ckpt[2] `
             -Steps $S3Steps -Ascension 7 -DeckRandom 0.25 `
             -Extra @("--lr", "6e-4", "--critic-warmup", "15")

# ── s4: asc 10, + tough/deadly enemies, double boss ──────────────────────
Invoke-Stage -Name "s4-asc10" -SaveCkpt $ckpt[4] -PrevCkpt $ckpt[3] `
             -Steps $S4Steps -Ascension 10 -DeckRandom 0.25 `
             -Extra @("--lr", "3e-4", "--critic-warmup", "15")

# ── s5: asc 10 polish, on-policy decks only, entropy anneal ──────────────
Invoke-Stage -Name "s5-asc10-polish" -SaveCkpt $ckpt[5] -PrevCkpt $ckpt[4] `
             -Steps $S5Steps -Ascension 10 -DeckRandom 0.00 `
             -Extra @("--lr", "3e-4", "--ent-coef", "0.01", "--ent-coef-final", "0.004")

Write-Host "[$(Get-Date -Format s)] v7 curriculum complete: $($ckpt[5])"
exit 0
