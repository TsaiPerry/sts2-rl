# v20 drill-bank harvest (plan 2026-08-19-v20-drill-env-plan.md, Task 2/6).
#
# Harvests mid-run combat snapshots from the standing checkpoint (v18_s21,
# SAMPLING mode) at ASC-0 ONLY (Perry's call, 2026-08-19: asc-0 runs reach
# act 2/3 at 3-5x the asc-10 rate, so one wave clears every pool bar;
# snapshot STATES are ascension-agnostic -- deck/relics/gold carry over,
# hp is clamped on rebuild -- and the drilling env's own --ascension rules
# the fights), then merges every chunk into ONE schema-2 bank and enforces
# the five v20 pools' >=150-snapshot coverage bars. Chunked across parallel
# jobs because a full harvest is hours of single-core CPU inference; each
# chunk gets a disjoint seed range so the merged bank has no duplicate
# episodes.
#
#   .\harvest_banks.ps1                # full: 1500 asc-0 episodes
#   .\harvest_banks.ps1 -Smoke        # 6 episodes, bars skipped
#   .\harvest_banks.ps1 -Jobs 6       # more parallel workers
#
# Output: runs\snapshots\v20_bank.jsonl (+ per-chunk files kept for audit).

param(
    [int]$Episodes0 = 1500,
    [int]$Jobs = 4,
    # Torch intra-op threads PER WORKER. Default 1: batch-1 CPU inference
    # gains almost nothing from a full thread pool, but torch's default is
    # one thread per core, so 4 unconstrained workers oversubscribe every
    # core and hog the box far harder than a training run does.
    [int]$Threads = 1,
    # Windows priority class for the workers -- BelowNormal keeps the
    # machine responsive while they grind.
    [string]$Priority = "BelowNormal",
    [string]$Checkpoint = "runs\sts2_run_torch_v18_s21.pt",
    [string]$OutBank = "runs\snapshots\v20_bank.jsonl",
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent  # scripts/ sits one level below repo root
# CPU tooling env (.venv) on purpose: harvest is single-episode CPU
# inference; the CUDA env (venv, no dot) stays free for training.
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "missing $py" }
if (-not (Test-Path (Join-Path $root $Checkpoint))) {
    throw "missing checkpoint $Checkpoint - is v18_s21 in runs\?"
}
# Smoke mode is fully isolated from a real harvest: its own chunk-file
# prefix, its own output bank, and a far-away seed base -- so a smoke run
# can never collide with (or merge in) a real run's chunk files, even one
# currently in progress.
$prefix = "chunk"
$seedBase = 200000
if ($Smoke) {
    $Episodes0 = 6; $Jobs = 2
    $prefix = "smokechunk"
    $seedBase = 900000
    $OutBank = "runs\snapshots\v20_bank_smoke.jsonl"
}
New-Item -ItemType Directory -Force (Join-Path $root "runs\snapshots") | Out-Null

function Invoke-HarvestWave {
    param([int]$Ascension, [int]$Episodes, [int]$SeedBase)
    $chunk = [math]::Ceiling($Episodes / $Jobs)
    $workers = @()
    for ($i = 0; $i -lt $Jobs; $i++) {
        $n = [math]::Min($chunk, $Episodes - $i * $chunk)
        if ($n -le 0) { break }
        $seed = $SeedBase + $i * $chunk
        $out = Join-Path $root ("runs\snapshots\{0}_asc{1}_{2}.jsonl" -f $prefix, $Ascension, $seed)
        $log = "$out.log"
        Write-Host ("  chunk asc-{0} seeds {1}..{2} -> {3}" -f $Ascension, $seed, ($seed + $n - 1), (Split-Path $out -Leaf))
        $workers += Start-Job -ScriptBlock {
            param($py, $root, $n, $seed, $ckpt, $out, $log, $asc, $threads)
            Set-Location $root
            # Cap torch/MKL/OpenMP intra-op threads BEFORE python starts --
            # torch reads these at import time. Batch-1 CPU inference gains
            # almost nothing from a full per-core thread pool, and without
            # the cap N workers oversubscribe every core on the box.
            $env:OMP_NUM_THREADS = "$threads"
            $env:MKL_NUM_THREADS = "$threads"
            & $py harvest.py --episodes $n --seed $seed --checkpoint $ckpt `
                --ascension $asc --out $out --log $log
            if ($LASTEXITCODE -ne 0) { throw "harvest chunk seed $seed failed ($LASTEXITCODE)" }
        } -ArgumentList $py, $root, $n, $seed, $Checkpoint, $out, $log, $Ascension, $Threads
    }
    Write-Host ("  waiting on {0} jobs..." -f $workers.Count)
    # Deprioritize the worker pythons from OUT here (Start-Process inside a
    # PS background job does not work; a plain & call does, so the parent
    # sets the priority class on the spawned harvest.py processes instead).
    Start-Sleep -Seconds 5
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match "harvest\.py" } |
        ForEach-Object {
            try {
                (Get-Process -Id $_.ProcessId -ErrorAction Stop).PriorityClass = $Priority
            } catch {}
        }
    $workers | Wait-Job | Out-Null
    foreach ($j in $workers) {
        if ($j.State -ne "Completed") {
            Receive-Job $j -ErrorAction SilentlyContinue
            throw "a harvest chunk failed (state $($j.State)) - see its .log"
        }
    }
    $workers | Remove-Job
}

Write-Host "=== asc-0 harvest: $Episodes0 episodes across $Jobs jobs (threads/worker: $Threads, priority: $Priority) ==="
Invoke-HarvestWave -Ascension 0 -Episodes $Episodes0 -SeedBase $seedBase

# â”€â”€ merge + coverage bars â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Write-Host "=== merging chunks -> $OutBank ==="
$bars = if ($Smoke) { "0" } else { "150" }
& $py -c @"
import glob, json, os, sys
from collections import Counter

root = r'$root'
out = os.path.join(root, r'$OutBank')
chunks = sorted(glob.glob(os.path.join(root, 'runs', 'snapshots', '$prefix' + '_asc*.jsonl')))
if not chunks:
    sys.exit('no chunk files found')
lines = []
for path in chunks:
    with open(path, encoding='utf-8') as fh:
        body = [l for l in fh.read().splitlines() if l.strip()]
    header = json.loads(body[0])
    assert header.get('snapshot_schema') == 2, f'{path}: bad header {header}'
    lines.extend(body[1:])
census = Counter()
for line in lines:
    obj = json.loads(line)
    census[f\"a{obj['act'] + 1}{obj['room_type'].lower()}\"] += 1
with open(out, 'w', encoding='utf-8') as fh:
    fh.write(json.dumps({'snapshot_schema': 2}) + '\n')
    fh.write('\n'.join(lines) + '\n')
print(f'wrote {out}: {len(lines)} snapshots from {len(chunks)} chunks')
for key in sorted(census):
    print(f'  {key}: {census[key]}')
bars = int('$bars')
POOLS = ('a1boss', 'a2boss', 'a3boss', 'a2elite', 'a3elite')
short = {p: census.get(p, 0) for p in POOLS if census.get(p, 0) < bars}
if short:
    sys.exit(f'COVERAGE BARS FAILED (>={bars} per v20 pool): {short} - '
             f'harvest more episodes (raise -Episodes0) and rerun')
print(f'v20 pool coverage bars (>= {bars}): ALL PASS')
"@
if ($LASTEXITCODE -ne 0) { throw "merge/coverage step failed" }
Write-Host "DONE - bank ready for train_curriculum_v20.ps1"
