<#
gen_distill_batch.ps1 - generate ONE search-distillation batch as sequential,
RAM-throttled waves of tools/search_worker.py workers, then merge the parts
into a single shard set and generate the matching HELD-OUT exam set.

WHY WAVES. Each search_worker holds its own sim forks, its own copy of the
policy and its own rollout buffers; the v26 batch-1 generation showed the box
runs out of RAM (and the GPU out of headroom) somewhere past three of them.
So the workers run in waves of -WaveWidth, one wave at a time, and the wave is
not finished until EVERY worker in it has written a provenance.json. The width
is hard-capped at 3 unless -AllowWide is passed; that cap is the whole point of
this script, so do not raise the default.

WHY SPLIT THE BANK. search_worker has no --shard flag and always walks its bank
from line 0 (snap_idx = fight % len(snaps)), so N workers pointed at the SAME
bank replay the SAME leading snapshots N times -- N stochastic redraws of a
narrow slice instead of N times the coverage. tools/split_bank.py hands each
worker a disjoint round-robin part.

WHY A HOLDOUT, AND WHERE THE SKIP COMES FROM. The 08-28 v26 diagnosis found the
distilled policy had MEMORIZED batch 1 (train agreement 0.71, holdout agreement
0.13 < the 0.19-0.21 null): without an exam drawn from snapshots no training
worker ever touched, "it learned the shards" is indistinguishable from "it
learned the task". tools/holdout_bank.py builds that exam by dropping a common
PREFIX from every part bank and pooling the tails -- correct precisely because
consumption is a prefix walk from line 0.

  skip = ceil(ceil(PerWorker / (RecordsPerFight * EstKeepRate)) * 1.25)

  The inner term is a per-part CONSUMPTION BOUND in fights. Since the 08-28
  decisiveness amendment, `--decisions` counts KEPT records, so a worker walks
  further into its bank than the raw record rate suggests: batch 1 measured
  10.6 searched records per fight, and the v27 calibration measured a keep rate
  of ~0.41 at -MinScoreGap 0.05, i.e. ~4.3 KEPT records per fight. The 1.25 is
  safety on top of that. At the default -PerWorker 840 this is
  ceil(194 * 1.25) = 243 fights skipped per part (it was 132 under the old
  unfiltered derivation). A holdout contaminated by even a slice of training
  snapshots reads as generalization that is not there, and snapshots are the
  cheap resource here.

  $EstKeepRate is an ESTIMATE (v27 temperature calibration, n = 200 decisions,
  reconstructed from the measured rollout scores -- see v27-run-log.md 08-28).
  If the true keep rate is LOWER than 0.41, a worker consumes more fights than
  the bound and WRAPS around its part bank (search_worker's fight list is
  positional: snap_idx = fight % len(snaps)), re-walking snapshots it already
  used -- and, past `skip` fights, it walks into the SNAPSHOTS THE HOLDOUT IS
  DRAWN FROM. holdout_bank.py only COPIES the tail (`pooled.extend(
  snaps[skip:])`); it does not remove it from the part bank, and search_worker
  walks the FULL part file. So the skip x 1.25 margin is the ONLY thing
  protecting the exam, and an overrun is train/holdout contamination, not just
  a diversity loss. It is DETECTABLE after the fact: each part's
  provenance.json records `stats.fights`, and the guard below refuses to launch
  the holdout wave if any part's fights exceeds $skip. The
  hard stop is unchanged: if a part bank has fewer than `skip` snapshots,
  holdout_bank.py refuses outright rather than emptying the bank. That means
  the bank is too small for this many workers, so harvest more snapshots (or
  lower -TotalRecords), never lower the skip.

  WALL CLOCK. The filter rejects a decision only AFTER its rollouts are paid
  for, so at a 0.41 keep rate a worker searches ~2.4x as many decisions for the
  same -PerWorker as it did before the amendment. Budget accordingly: 15000
  kept / 840 = 18 workers is unchanged, but each worker takes ~2.4x as long.

RESUME + THE MERGE REFUSAL. Re-running the script with the same -OutDir picks
up where it stopped:
  * a worker directory that already holds a provenance.json is SKIPPED (that
    worker finished; its shards are on disk);
  * the part banks and holdout banks are rebuilt every run -- both splitters
    are deterministic pure functions of the bank, so this is a no-op that keeps
    a resumed run from depending on files it cannot verify;
  * tools/merge_distill.py REFUSES an --out that already holds any .npz (it
    would mix shard sets), so the merge step is skipped when
    <OutDir>/provenance.json already exists, and the existing merge is reported
    instead. A directory holding .npz files but NO provenance.json is a
    half-built merge: this script does not guess, merge_distill fails loudly,
    and the fix is to delete the directory and re-run.

  .\scripts\gen_distill_batch.ps1 -Ckpt runs\sts2_run_torch_v24_s27.pt `
      -Bank runs\snapshots\v24s27_bank_asc10.jsonl `
      -OutDir runs\distill\v27_batch1 -Temperature 0.5

  .\scripts\gen_distill_batch.ps1 ... -Temperature 0.5 -Smoke   # 2x24 + 24

-Temperature has NO DEFAULT on purpose. It is the sharpening knob the v27 plan
exists to exercise (T<1 sharpens the searched targets toward the search's own
pick); a default would let a generation inherit a calibration nobody chose, and
the value is stamped into provenance.json where merge_distill.py refuses to mix
two temperatures. Pick it deliberately. The pinned v27 value is 0.25.

-MinScoreGap DOES default (0.05, the v27 spec value), because unlike the
temperature it has a measured, non-arbitrary answer. The 08-28 calibration
found temperature alone could not clear the pre-registered "median top1-top2
target-mass gap >= 0.25" bar at ANY T -- the raw rollout scores are near-tied
(median gap ~0.016; 19.5% of records have every candidate scored exactly equal,
where a softmax is temperature-invariant). Filtering the SOURCE fixes it:
keeping only decisions with a raw score gap > 0.05 retains ~41% of records and
lifts the median target gap to 0.317 at T = 0.25. It is threaded to every
worker, holdout wave included, and stamped into provenance.json where
merge_distill.py refuses to mix a filtered part with an unfiltered one.
#>
param(
    [Parameter(Mandatory = $true)][string]$Ckpt,
    [Parameter(Mandatory = $true)][string]$Bank,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [Parameter(Mandatory = $true)][double]$Temperature,
    [double]$MinScoreGap = 0.05,
    [int]$TotalRecords = 15000,
    [int]$WaveWidth = 3,
    [int]$PerWorker = 840,
    [int]$HoldoutRecords = 500,
    [switch]$AllowWide,
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent   # scripts/ sits one level below the repo root
# venv (no dot) is the CUDA env: torch 2.13.0+cu130. The dotted .venv twin is
# torch+cpu (pytest/onnx tooling) and would take the search off the GPU.
$py = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "No CUDA python at '$py'." -ForegroundColor Red
    exit 1
}

function Resolve-Rooted {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    return (Join-Path $root $Path)
}

# Absolute everywhere: every python child runs with -WorkingDirectory $root
# while Test-Path here resolves against the CALLER's cwd, so a relative path
# would mean two different files depending on where the script was launched.
$Ckpt = Resolve-Rooted $Ckpt
$Bank = Resolve-Rooted $Bank
$OutDir = Resolve-Rooted $OutDir

if (-not (Test-Path $Ckpt -PathType Leaf)) {
    Write-Host "Ckpt '$Ckpt' not found - nothing to search with." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Bank -PathType Leaf)) {
    Write-Host "Bank '$Bank' not found - nothing to search over." -ForegroundColor Red
    exit 1
}

if ($Smoke) {
    # A code-path proof, not a generation: same flags, same wave machinery, same
    # split/holdout/merge steps, just small enough to finish in minutes.
    $PerWorker = 24
    $TotalRecords = 48          # -> ceil(48/24) = 2 workers
    $HoldoutRecords = 24
    $WaveWidth = 2
    Write-Host "SMOKE MODE: 2 workers x 24 decisions, holdout 24. Delete '$OutDir'* afterwards." -ForegroundColor Yellow
}

if ($TotalRecords -lt 1) { Write-Host "-TotalRecords must be >= 1." -ForegroundColor Red; exit 1 }
if ($PerWorker -lt 1) { Write-Host "-PerWorker must be >= 1." -ForegroundColor Red; exit 1 }
if ($HoldoutRecords -lt 2) { Write-Host "-HoldoutRecords must be >= 2 (it is split over 2 workers)." -ForegroundColor Red; exit 1 }
if ($WaveWidth -lt 1) { Write-Host "-WaveWidth must be >= 1." -ForegroundColor Red; exit 1 }
if ($MinScoreGap -lt 0) { Write-Host "-MinScoreGap must be >= 0 (0 = no filter)." -ForegroundColor Red; exit 1 }
if ($WaveWidth -gt 3 -and -not $AllowWide) {
    Write-Host "-WaveWidth $WaveWidth exceeds the 3-worker cap." -ForegroundColor Red
    Write-Host "Four concurrent search workers exhausted host RAM during the v26 batch-1" -ForegroundColor Red
    Write-Host "generation. Pass -AllowWide if you have measured headroom for more." -ForegroundColor Red
    exit 1
}

$nWorkers = [int][math]::Ceiling($TotalRecords / [double]$PerWorker)

# ── the skip derivation's two measured inputs ────────────────────────────────
# $RecordsPerFight: searched records per fight, MEASURED on the v26 batch-1
#   generation (10.6).
# $EstKeepRate: the share of searched decisions that survive -MinScoreGap 0.05,
#   ESTIMATED from the v27 temperature calibration (n = 200 decisions,
#   reconstructed from the measured rollout scores; v27-run-log.md 08-28).
# Their product is KEPT records per fight (~4.3), and -PerWorker now counts
# KEPT records, so PerWorker / (product) is the fights a worker consumes.
# Deliberately NOT derived from $MinScoreGap: 0.41 was measured at 0.05 and
# only at 0.05. Change the gap and this number is a guess -- which is why the
# holdout skip is NOT stamped as a function of the gap (see bank.stamp below)
# and why a lower true keep rate is handled by wrapping, not by refusal.
$RecordsPerFight = 10.6
$EstKeepRate = 0.41
$skip = [int][math]::Ceiling(
    [math]::Ceiling($PerWorker / ($RecordsPerFight * $EstKeepRate)) * 1.25)
# InvariantCulture: a comma decimal separator on a localized box would hand
# argparse "0,5" and it would die -- or worse, parse as something else.
$tempStr = $Temperature.ToString("0.########", [Globalization.CultureInfo]::InvariantCulture)
$gapStr = $MinScoreGap.ToString("0.########", [Globalization.CultureInfo]::InvariantCulture)

Write-Host ("=" * 72)
Write-Host "distill batch -> $OutDir"
Write-Host "  ckpt        $Ckpt"
Write-Host "  bank        $Bank"
Write-Host "  workers     $nWorkers x $PerWorker KEPT records (target $TotalRecords records)"
Write-Host "  waves       width $WaveWidth"
Write-Host "  temperature $tempStr"
Write-Host "  min gap     $gapStr (est keep rate $EstKeepRate -> ~2.4x searches per kept record)"
Write-Host "  holdout     $HoldoutRecords records over 2 workers, bank skip $skip"
Write-Host ("=" * 72)

$sw = [System.Diagnostics.Stopwatch]::StartNew()

function Invoke-Py {
    param([string]$Name, [string[]]$PyArgs)
    Write-Host "[$(Get-Date -Format s)] $Name"
    $p = Start-Process -FilePath $py -ArgumentList $PyArgs `
                       -WorkingDirectory $root -NoNewWindow -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Write-Host "$Name failed (exit $($p.ExitCode)). Stopping." -ForegroundColor Red
        exit $p.ExitCode
    }
}

# ── (1) part banks + the reserved holdout tails ──────────────────────────────
# Both splitters are deterministic functions of $Bank, so re-running them on a
# resume rewrites byte-identical files. Cheap, and it means a resumed run never
# trusts split files it did not just produce.
#
# The bank is COPIED into this run's own parts directory first, and split
# there. split_bank.py derives its output names from the INPUT path
# (bank.jsonl -> bank.p0.jsonl ...), so splitting the shared bank in place
# would overwrite a previous batch's part banks whenever the two runs disagree
# on worker count -- silently rewriting the evidence of what an earlier
# generation actually consumed. Per-run copies cost one file and make each
# batch's inputs self-contained.
$partRoot = "${OutDir}_parts"
if (-not (Test-Path $partRoot)) { New-Item -ItemType Directory $partRoot -Force | Out-Null }
$workBank = Join-Path $partRoot ([System.IO.Path]::GetFileName($Bank))

# ── the bank IDENTITY stamp: what makes a resume safe ────────────────────────
# A resume re-splits the bank AS IT IS NOW. If the bank grew between the first
# run and the resume -- and this script's own header tells you to harvest more
# snapshots when holdout_bank refuses -- then `Copy-Item -Force` would silently
# replace the parts copy, the round-robin assignment (line i -> part i % n)
# would shift under every already-FINISHED worker, and the tails
# holdout_bank.py carves would no longer be the tails those workers left
# unconsumed. The exam would then contain snapshots the training set was
# written from: silent holdout contamination, which is the one failure this
# whole holdout apparatus exists to rule out, and it would leave no trace in
# any provenance.json.
#
# So the first run stamps the source bank's identity (path, byte length, line
# count, SHA256) into <OutDir>_parts\bank.stamp, and every later run refuses if
# the current -Bank does not match it. The split geometry (-PerWorker's worker
# count and the derived skip) is stamped for the same reason: re-splitting the
# SAME bank into a different number of parts reshuffles it just as badly.
#
# -MinScoreGap is deliberately NOT in this stamp. The stamp exists to protect
# the SPLIT GEOMETRY, and the gap does not enter it: $skip is derived from
# $PerWorker and the two fixed measured constants above, never from the gap.
# What the gap changes is the CONTENT of the parts, and that is caught one
# layer down -- Invoke-Waves refuses a finished worker dir whose provenance
# stamps a different min_score_gap, exactly as it does for ckpt/temperature.
$stampPath = Join-Path $partRoot "bank.stamp"
$bankFile = Get-Item -LiteralPath $Bank
$bankHash = (Get-FileHash -LiteralPath $Bank -Algorithm SHA256).Hash
$bankLines = (Get-Content -LiteralPath $Bank | Measure-Object -Line).Lines
$stamp = [ordered]@{
    bank      = $Bank
    length    = [long]$bankFile.Length
    lines     = [int]$bankLines
    sha256    = $bankHash
    n_workers = $nWorkers
    skip      = $skip
}
if (Test-Path $stampPath) {
    $prevStamp = $null
    try {
        $prevStamp = Get-Content -LiteralPath $stampPath -Raw | ConvertFrom-Json
    } catch {
        Write-Host "'$stampPath' is not readable JSON: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Cannot prove the resumed run's bank matches the one the finished workers" -ForegroundColor Red
        Write-Host "consumed. Use a fresh -OutDir." -ForegroundColor Red
        exit 1
    }
    $diffs = @()
    if ([long]$prevStamp.length -ne $stamp.length) { $diffs += "byte length $($prevStamp.length) -> $($stamp.length)" }
    if ([int]$prevStamp.lines -ne $stamp.lines) { $diffs += "line count $($prevStamp.lines) -> $($stamp.lines)" }
    if ("$($prevStamp.sha256)" -ne $stamp.sha256) { $diffs += "sha256 $($prevStamp.sha256) -> $($stamp.sha256)" }
    if ([int]$prevStamp.n_workers -ne $stamp.n_workers) { $diffs += "worker count $($prevStamp.n_workers) -> $($stamp.n_workers)" }
    if ([int]$prevStamp.skip -ne $stamp.skip) { $diffs += "holdout skip $($prevStamp.skip) -> $($stamp.skip)" }
    if ($diffs.Count -gt 0) {
        Write-Host "The bank/split geometry has CHANGED since '$OutDir' was started:" -ForegroundColor Red
        foreach ($d in $diffs) { Write-Host "    $d" -ForegroundColor Red }
        Write-Host "  stamped bank: $($prevStamp.bank)" -ForegroundColor Red
        Write-Host "  current bank: $Bank" -ForegroundColor Red
        Write-Host "Re-splitting now would reshuffle the round-robin assignment under the workers" -ForegroundColor Red
        Write-Host "that already FINISHED, so the holdout tails would no longer be snapshots those" -ForegroundColor Red
        Write-Host "workers left unconsumed - the exam would be contaminated with training data and" -ForegroundColor Red
        Write-Host "nothing downstream could tell. Start a FRESH -OutDir (a resume must re-use the" -ForegroundColor Red
        Write-Host "exact bank and geometry it started with), or delete '$OutDir'* to regenerate." -ForegroundColor Red
        exit 1
    }
    Write-Host "  bank stamp matches ($($stamp.lines) lines, sha256 $($stamp.sha256.Substring(0, 12))...)." -ForegroundColor DarkGray
} else {
    ($stamp | ConvertTo-Json) | Set-Content -LiteralPath $stampPath -Encoding UTF8
    Write-Host "  bank stamped ($($stamp.lines) lines, sha256 $($stamp.sha256.Substring(0, 12))...) -> $stampPath" -ForegroundColor DarkGray
}

Copy-Item -LiteralPath $Bank -Destination $workBank -Force
$bankStem = [System.IO.Path]::Combine(
    [System.IO.Path]::GetDirectoryName($workBank),
    [System.IO.Path]::GetFileNameWithoutExtension($workBank))
$bankExt = [System.IO.Path]::GetExtension($workBank)

$partBanks = @()
if ($nWorkers -ge 2) {
    Invoke-Py -Name "split-bank ($nWorkers parts)" -PyArgs @("tools\split_bank.py", $workBank, "$nWorkers")
    for ($i = 0; $i -lt $nWorkers; $i++) { $partBanks += "$bankStem.p$i$bankExt" }
} else {
    # split_bank.py refuses parts < 2, and rightly: with one worker there is
    # nothing to make disjoint. It gets the whole bank.
    $partBanks += $workBank
}
foreach ($pb in $partBanks) {
    if (-not (Test-Path $pb -PathType Leaf)) {
        Write-Host "Expected part bank '$pb' was not written." -ForegroundColor Red
        exit 1
    }
}

$holdoutStem = "$bankStem.holdout"
Invoke-Py -Name "holdout-bank (skip $skip)" -PyArgs (
    @("tools\holdout_bank.py") + $partBanks + @("--skip", "$skip", "--parts", "2",
                                                "--out-stem", $holdoutStem))
$holdoutBanks = @("$holdoutStem.p0.jsonl", "$holdoutStem.p1.jsonl")
foreach ($hb in $holdoutBanks) {
    if (-not (Test-Path $hb -PathType Leaf)) {
        Write-Host "Expected holdout bank '$hb' was not written." -ForegroundColor Red
        exit 1
    }
}

# ── the wave runner ──────────────────────────────────────────────────────────
# One job = one worker: its bank, its own --out directory, its own log. A job
# whose directory already holds a provenance.json is finished and is skipped.
function Invoke-Waves {
    param([string]$Label, [array]$Jobs, [int]$Width, [int]$Decisions)

    # ── resume pre-flight: the finished parts must have been written under THIS
    # run's ckpt and temperature. merge_distill.py catches a mismatch too (both
    # are in its MUST_MATCH set), but only AFTER every remaining worker has been
    # searched -- hours of GPU for a merge that was doomed before it started.
    # The stamp is already on disk here, so the check costs a file read.
    foreach ($job in $Jobs) {
        $donePr = Join-Path $job.Dir "provenance.json"
        if (-not (Test-Path $donePr)) { continue }
        $pr = $null
        try {
            $pr = Get-Content -LiteralPath $donePr -Raw | ConvertFrom-Json
        } catch {
            Write-Host "'$donePr' is not readable JSON: $($_.Exception.Message)" -ForegroundColor Red
            exit 1
        }
        $bad = @()
        # Tolerance rather than -ne: the stamped value made a float round trip
        # through JSON, and 0.5 vs 0.5000000000000001 is not a real mismatch.
        if ([math]::Abs([double]$pr.temperature - $Temperature) -gt 1e-9) {
            $bad += "temperature $($pr.temperature) (this run: $tempStr)"
        }
        # A part written before the decisiveness filter existed carries no
        # min_score_gap key at all, and those runs kept every searched
        # decision -- i.e. 0.0, which is what merge_distill.py's
        # MUST_MATCH_DEFAULTS assumes too. Read a missing key the same way
        # here so the two layers cannot disagree about an old part dir.
        $prGap = 0.0
        if ($null -ne $pr.min_score_gap) { $prGap = [double]$pr.min_score_gap }
        if ([math]::Abs($prGap - $MinScoreGap) -gt 1e-9) {
            $bad += "min-score-gap $prGap (this run: $gapStr)"
        }
        if ("$($pr.ckpt)" -ne $Ckpt) {
            $bad += "ckpt $($pr.ckpt) (this run: $Ckpt)"
        }
        if ($bad.Count -gt 0) {
            Write-Host "$($job.Name) was already generated under a DIFFERENT generator:" -ForegroundColor Red
            foreach ($b in $bad) { Write-Host "    $b" -ForegroundColor Red }
            Write-Host "Parts that disagree on ckpt, temperature or min-score-gap are not two halves of one" -ForegroundColor Red
            Write-Host "dataset; merge_distill.py would refuse them - but only after the remaining" -ForegroundColor Red
            Write-Host "workers had burned their GPU hours. Re-run with the original -Ckpt," -ForegroundColor Red
            Write-Host "-Temperature and -MinScoreGap, or start a FRESH -OutDir." -ForegroundColor Red
            exit 1
        }
    }

    $todo = @()
    foreach ($job in $Jobs) {
        if (Test-Path (Join-Path $job.Dir "provenance.json")) {
            Write-Host "  $($job.Name) already done (provenance.json present) - skipping." -ForegroundColor DarkGray
        } else {
            $todo += $job
        }
    }
    if ($todo.Count -eq 0) {
        Write-Host "  all $Label workers already done."
        return
    }

    $nWaves = [int][math]::Ceiling($todo.Count / [double]$Width)
    for ($w = 0; $w -lt $nWaves; $w++) {
        $wave = @($todo[($w * $Width) .. ([math]::Min(($w + 1) * $Width, $todo.Count) - 1)])
        Write-Host "[$(Get-Date -Format s)] $Label wave $($w + 1)/$nWaves : $($wave.Count) worker(s)" -ForegroundColor Cyan
        $procs = @()
        foreach ($job in $wave) {
            if (-not (Test-Path $job.Dir)) { New-Item -ItemType Directory $job.Dir -Force | Out-Null }
            # -u first: without it the worker's stdout is block-buffered into
            # the redirected file and w*.log sits at 0 bytes until exit, which
            # is exactly when a human wants to watch a multi-hour wave.
            $wArgs = @("-u", "tools\search_worker.py", $Ckpt,
                       "--bank", $job.Bank,
                       "--out", $job.Dir,
                       "--decisions", "$Decisions",
                       "--shard-size", "256",
                       "--k", "5", "--m", "8",
                       "--mass-cap", "0.92",
                       "--asc", "10",
                       "--seed", "0",
                       "--gamma", "0.999",
                       "--rollout-steps", "120",
                       "--card-obs", "hybrid",
                       "--device", "cuda",
                       "--temperature", $tempStr,
                       "--min-score-gap", $gapStr)
            Write-Host "    $($job.Name) -> $($job.Dir)  (log $($job.Log))"
            $p = Start-Process -FilePath $py -ArgumentList $wArgs `
                               -WorkingDirectory $root -NoNewWindow -PassThru `
                               -RedirectStandardOutput $job.Log `
                               -RedirectStandardError $job.ErrLog
            # Touching .Handle CACHES the process handle. Without it, PS 5.1's
            # Start-Process -PassThru (no -Wait) hands back an object whose
            # ExitCode reads back $null once the process is gone -- the failure
            # report would then say "exited " with nothing after it, exactly
            # when the number matters most. Measured on this box, 2026-08-28.
            $null = $p.Handle
            $procs += @{ Job = $job; Proc = $p }
        }
        foreach ($entry in $procs) { $entry.Proc.WaitForExit() }
        # The wave is done only when every worker in it WROTE ITS PROVENANCE.
        # A zero exit with no provenance.json would be a silently empty part
        # that merge_distill refuses much later, after the next waves burned
        # hours; catch it here, at the worker whose log explains it.
        $failed = $false
        foreach ($entry in $procs) {
            $job = $entry.Job
            $code = $entry.Proc.ExitCode
            if (Test-Path (Join-Path $job.Dir "provenance.json")) {
                if ($code -ne 0) {
                    # provenance.json is written before the worker's closing
                    # prints, so this shape is "wrote its shards, then tripped
                    # on the way out". The part is usable (merge_distill
                    # re-verifies its record count against the arrays), but the
                    # log is worth a human's eye.
                    Write-Host "    $($job.Name) exited $code but DID write provenance - part kept; check $($job.ErrLog)" -ForegroundColor Yellow
                } else {
                    Write-Host "    $($job.Name) exited $code, provenance written." -ForegroundColor DarkGray
                }
            } else {
                Write-Host "    $($job.Name) exited $code with NO provenance.json - see $($job.Log) / $($job.ErrLog)" -ForegroundColor Red
                $failed = $true
            }
        }
        if ($failed) {
            Write-Host "$Label wave $($w + 1) incomplete. Fix the cause and re-run: finished worker dirs are skipped." -ForegroundColor Red
            exit 1
        }
    }
}

# ── merge, with the "already merged" case handled explicitly ─────────────────
function Invoke-Merge {
    param([string]$Label, [array]$PartDirs, [string]$Dest)
    if (Test-Path (Join-Path $Dest "provenance.json")) {
        # merge_distill.py refuses an --out holding any .npz. On a resume that
        # already produced this directory the merge is DONE, so report it and
        # move on rather than tripping that refusal.
        Write-Host "  $Label already merged into $Dest (provenance.json present) - skipping merge." -ForegroundColor DarkGray
        return
    }
    Invoke-Py -Name "merge $Label -> $Dest" -PyArgs (
        @("tools\merge_distill.py") + $PartDirs + @("--out", $Dest))
}

# Provenance -> the summary numbers. PS 5.1's ConvertFrom-Json returns a
# PSCustomObject, so the fields are read by name, not by key lookup.
function Write-SetSummary {
    param([string]$Label, [string]$Dir)
    $provPath = Join-Path $Dir "provenance.json"
    if (-not (Test-Path $provPath)) {
        Write-Host "  $Label : no provenance.json at $provPath" -ForegroundColor Yellow
        return
    }
    $prov = Get-Content $provPath -Raw | ConvertFrom-Json
    $records = [int]$prov.records
    $fights = [int]$prov.stats.fights
    $flips = [int]$prov.stats.flips
    $rate = 0.0
    if ($records -gt 0) { $rate = 100.0 * $flips / $records }
    $shards = @($prov.shards).Count
    Write-Host ("  {0,-8} {1} records / {2} fights / flip {3}/{4} ({5:N1}%) in {6} shard(s)" -f `
        $Label, $records, $fights, $flips, $records, $rate, $shards)
    # min_score_gap is absent from pre-4b parts; report it as 0.0 (unfiltered),
    # the same reading merge_distill.py and the resume pre-flight take.
    $gap = 0.0
    if ($null -ne $prov.min_score_gap) { $gap = [double]$prov.min_score_gap }
    $searched = 0
    if ($null -ne $prov.stats.decisions_searched) { $searched = [int]$prov.stats.decisions_searched }
    $skipped = 0
    if ($null -ne $prov.stats.skipped_indecisive) { $skipped = [int]$prov.stats.skipped_indecisive }
    $keepRate = 0.0
    if ($searched -gt 0) { $keepRate = 100.0 * $records / $searched }
    Write-Host ("           temperature {0}  min-gap {1}  k {2}  ckpt {3}" -f $prov.temperature, $gap, $prov.k, $prov.ckpt)
    Write-Host ("           searched {0}, skipped indecisive {1} -> keep rate {2:N1}% (est {3:P0})" -f `
        $searched, $skipped, $keepRate, $EstKeepRate)
}

# ── (2) the training batch: sequential waves ─────────────────────────────────
$jobs = @()
for ($i = 0; $i -lt $nWorkers; $i++) {
    $jobs += @{
        Name   = "w$i"
        Bank   = $partBanks[$i]
        Dir    = (Join-Path $partRoot "w$i")
        Log    = (Join-Path $partRoot "w$i.log")
        ErrLog = (Join-Path $partRoot "w$i.err.log")
    }
}
Invoke-Waves -Label "batch" -Jobs $jobs -Width $WaveWidth -Decisions $PerWorker

# ── (2b) the overrun guard: did any worker walk into the holdout tail? ────────
# holdout_bank.py COPIES snaps[skip:]; it does not remove that tail from the
# part bank, and search_worker walks the whole part file (snap_idx = fight %
# len(snaps)). A worker that ran past $skip fights therefore SEARCHED the exact
# snapshots the exam is drawn from, and every generalization number downstream
# would be measuring memorization again -- the one thing this apparatus exists
# to rule out. stats.fights is the receipt, so check it before the exam is
# written. This sits AFTER Invoke-Waves (which returns early when every worker
# is already done), so a resumed run that skips straight to the merges still
# evaluates it, after the fact, before the holdout wave.
$overrun = @()
foreach ($job in $jobs) {
    $prPath = Join-Path $job.Dir "provenance.json"
    if (-not (Test-Path $prPath)) { continue }
    $pr = $null
    try {
        $pr = Get-Content -LiteralPath $prPath -Raw | ConvertFrom-Json
    } catch {
        Write-Host "'$prPath' is not readable JSON: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
    $fights = [int]$pr.stats.fights
    if ($fights -gt $skip) {
        $overrun += @{ Name = $job.Name; Fights = $fights }
    }
}
if ($overrun.Count -gt 0) {
    Write-Host "HOLDOUT WOULD BE CONTAMINATED: a worker consumed past the reserved tail." -ForegroundColor Red
    foreach ($o in $overrun) {
        Write-Host ("    part {0}: fights {1} > skip {2}" -f $o.Name, $o.Fights, $skip) -ForegroundColor Red
    }
    $maxFights = ($overrun | ForEach-Object { $_.Fights } | Measure-Object -Maximum).Maximum
    Write-Host "holdout would be contaminated - rebuild holdout banks with --skip $maxFights" -ForegroundColor Red
    Write-Host "(--skip <max observed fights>; headroom: pooled tail must stay >= 300) and" -ForegroundColor Red
    Write-Host "regenerate the exam into a fresh _holdout dir." -ForegroundColor Red
    exit 1
}
Write-Host "  holdout margin OK: no part exceeded $skip fights." -ForegroundColor DarkGray

# ── (3) merge the batch ──────────────────────────────────────────────────────
Invoke-Merge -Label "batch" -PartDirs @($jobs | ForEach-Object { $_.Dir }) -Dest $OutDir

# ── (4) the holdout exam: 2 workers, ONE wave, same ckpt + temperature ───────
# Same generator settings on purpose: an exam written under a different
# temperature or a different checkpoint measures a different thing than the
# training set, and merge_distill would (rightly) refuse to see them as kin.
$holdoutDir = "${OutDir}_holdout"
$holdoutPartRoot = "${holdoutDir}_parts"
if (-not (Test-Path $holdoutPartRoot)) { New-Item -ItemType Directory $holdoutPartRoot -Force | Out-Null }
$holdoutPerWorker = [int][math]::Ceiling($HoldoutRecords / 2.0)
$holdoutJobs = @()
for ($i = 0; $i -lt 2; $i++) {
    $holdoutJobs += @{
        Name   = "h$i"
        Bank   = $holdoutBanks[$i]
        Dir    = (Join-Path $holdoutPartRoot "h$i")
        Log    = (Join-Path $holdoutPartRoot "h$i.log")
        ErrLog = (Join-Path $holdoutPartRoot "h$i.err.log")
    }
}
Invoke-Waves -Label "holdout" -Jobs $holdoutJobs -Width 2 -Decisions $holdoutPerWorker
Invoke-Merge -Label "holdout" -PartDirs @($holdoutJobs | ForEach-Object { $_.Dir }) -Dest $holdoutDir

# ── (5) summary ──────────────────────────────────────────────────────────────
$sw.Stop()
$wall = $sw.Elapsed
Write-Host ""
Write-Host ("=" * 72) -ForegroundColor Green
Write-Host "distill batch complete" -ForegroundColor Green
Write-SetSummary -Label "batch" -Dir $OutDir
Write-SetSummary -Label "holdout" -Dir $holdoutDir
Write-Host ("  wall     {0:hh\:mm\:ss} ({1:N0}s)" -f $wall, $wall.TotalSeconds)
Write-Host ""
Write-Host "  train    $OutDir"
Write-Host "  holdout  $holdoutDir"
Write-Host ("=" * 72) -ForegroundColor Green
Write-Host "Point the trainer at the train dir (--distill) and score the holdout with" -ForegroundColor Green
Write-Host "tools/distill_diag.py; a shard set is STALE the moment a newer ckpt exists." -ForegroundColor Green
