<#
estcheck_run.ps1 - variance-vs-more-rollouts diagnostic for the v27 targets.

Generates estimator variants over the SAME bank/seed (collection walk is
independent of both --m and --rollout-steps, so every variant is record-aligned
and unfiltered), then grades each against a high-m gold standard with
tools/estcheck_analyze.py. Sequential (one GPU job at a time). Reuses the two
mcheck runs (m=8/steps=120 and m=32/steps=120) as extra reference estimators.

Read-only w.r.t. the seed and batch; writes only under runs/distill/v27_estcheck/.

    scripts\estcheck_run.ps1 [-Decisions 60] [-GoldM 64] [-Smoke]
#>
[CmdletBinding()]
param(
    [string]$Ckpt = "runs\sts2_run_torch_v24_s27.pt",
    [string]$Bank = "runs\snapshots\v27_batch1_bank_asc10.jsonl",
    [string]$OutRoot = "runs\distill\v27_estcheck",
    [int]$Decisions = 60,
    [int]$GoldM = 64,
    [int]$Seed = 0,
    [int]$CritSteps = 0,
    [switch]$Smoke
)
$ErrorActionPreference = "Stop"
$py = "venv\Scripts\python.exe"
if ($Smoke) { $Decisions = 5; $GoldM = 16 }

function Invoke-Worker {
    param([int]$M, [int]$Steps, [string]$Out)
    if (Test-Path (Join-Path $Out "provenance.json")) {
        Write-Host "  $Out already complete - skipping (resume)." -ForegroundColor Yellow
        return
    }
    Write-Host "[$([DateTime]::Now.ToString('s'))] m=$M steps=$Steps -> $Out" -ForegroundColor Cyan
    & $py -u tools\search_worker.py $Ckpt `
        --bank $Bank --out $Out `
        --decisions $Decisions --shard-size 256 `
        --k 5 --m $M --mass-cap 0.92 --asc 10 `
        --seed $Seed --gamma 0.999 --rollout-steps $Steps `
        --card-obs hybrid --device cuda `
        --temperature 0.25 --min-score-gap 0.0
    if ($LASTEXITCODE -ne 0) { throw "search_worker m=$M steps=$Steps exited $LASTEXITCODE" }
}

$gold = Join-Path $OutRoot ("gold_m{0}_s120" -f $GoldM)
$crit = Join-Path $OutRoot ("crit_m8_s{0}" -f $CritSteps)
$s10  = Join-Path $OutRoot "mid_m8_s10"
$m8   = Join-Path $OutRoot "m8_s120"
$m32  = Join-Path $OutRoot "m32_s120"

# ALL variants at the SAME -Decisions: the collection walk is m/steps-independent
# BUT the selection median depends on how many fights were collected, so runs at
# different -Decisions select different decisions. Same -Decisions => aligned.
Write-Host "estcheck: $Decisions decisions, gold m=$GoldM/steps120 vs crit(steps=$CritSteps) + short/rollout ladder" -ForegroundColor Green
Invoke-Worker -M $GoldM -Steps 120 -Out $gold          # gold standard (slow, do first)
Invoke-Worker -M 8      -Steps $CritSteps -Out $crit   # 1-ply critic (near-free)
Invoke-Worker -M 8      -Steps 10  -Out $s10           # short rollout
Invoke-Worker -M 8      -Steps 120 -Out $m8            # current batch estimator (baseline)
Invoke-Worker -M 32     -Steps 120 -Out $m32           # more rollouts (does m help?)

$estArgs = @(
    "--est", ("crit_m8_s{0}={1}" -f $CritSteps, $crit),
    "--est", ("mid_m8_s10=" + $s10),
    "--est", ("m8_s120=" + $m8),
    "--est", ("m32_s120=" + $m32)
)
Write-Host ""
Write-Host "[$([DateTime]::Now.ToString('s'))] grading vs gold ..." -ForegroundColor Green
& $py -u tools\estcheck_analyze.py $gold @estArgs `
    --temperature 0.25 --thresholds 0.1,0.3,0.5 `
    --json (Join-Path $OutRoot "estcheck_result.json")
