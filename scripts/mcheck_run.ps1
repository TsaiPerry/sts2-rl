<#
mcheck_run.ps1 - rollout-reliability probe for the v27 batch-1 targets.

Runs tools/search_worker.py twice over the SAME bank / seed / candidates,
differing ONLY in --m (8, then a larger reference), both UNFILTERED
(--min-score-gap 0) so the m-independent collection walk scores the identical
decisions in the identical order and record n aligns across the two runs.
Sequential (never two workers at once) - one GPU job at a time, same RAM
discipline as gen_distill_batch.ps1. Then tools/mcheck_analyze.py compares them.

Read-only w.r.t. the seed and the batch: writes only under
runs/distill/v27_mcheck/ and reads runs/sts2_run_torch_v24_s27.pt.

    scripts\mcheck_run.ps1 [-Decisions 150] [-RefM 32] [-Smoke]
#>
[CmdletBinding()]
param(
    [string]$Ckpt = "runs\sts2_run_torch_v24_s27.pt",
    [string]$Bank = "runs\snapshots\v27_batch1_bank_asc10.jsonl",
    [string]$OutRoot = "runs\distill\v27_mcheck",
    [int]$Decisions = 150,
    [int]$RefM = 32,
    [int]$Seed = 0,
    [switch]$Smoke
)
$ErrorActionPreference = "Stop"
$py = "venv\Scripts\python.exe"
if ($Smoke) { $Decisions = 6 }

function Invoke-Worker {
    param([int]$M, [string]$Out)
    if (Test-Path (Join-Path $Out "provenance.json")) {
        Write-Host "  $Out already complete (provenance.json) - skipping (resume)." -ForegroundColor Yellow
        return
    }
    Write-Host "[$([DateTime]::Now.ToString('s'))] search m=$M -> $Out" -ForegroundColor Cyan
    & $py -u tools\search_worker.py $Ckpt `
        --bank $Bank --out $Out `
        --decisions $Decisions --shard-size 256 `
        --k 5 --m $M --mass-cap 0.92 --asc 10 `
        --seed $Seed --gamma 0.999 --rollout-steps 120 `
        --card-obs hybrid --device cuda `
        --temperature 0.25 --min-score-gap 0.0
    if ($LASTEXITCODE -ne 0) { throw "search_worker m=$M exited $LASTEXITCODE" }
}

$m8Dir  = Join-Path $OutRoot "m8"
$refDir = Join-Path $OutRoot ("m{0}" -f $RefM)

Write-Host "mcheck: $Decisions decisions, m=8 vs m=$RefM, seed $Seed, UNFILTERED (aligned)" -ForegroundColor Green
Invoke-Worker -M 8     -Out $m8Dir
Invoke-Worker -M $RefM -Out $refDir

Write-Host ""
Write-Host "[$([DateTime]::Now.ToString('s'))] analyzing ..." -ForegroundColor Green
& $py -u tools\mcheck_analyze.py $m8Dir $refDir `
    --temperature 0.25 --min-score-gap 0.05 `
    --json (Join-Path $OutRoot "mcheck_result.json")
