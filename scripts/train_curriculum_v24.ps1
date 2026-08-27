<#
v24 per-act elite ramp: one stage on top of the v23 s26 policy, keeping
v23's long-horizon geometry (n-steps 1024 / minibatches 16 / gae-lambda
0.99) VERBATIM so the only variable is the reward change.

ONE reward change vs v23. The flat elite pay is replaced by a per-act ramp
tracking --floor-rewards' own 1.0/1.5/2.0 multipliers:

    --reward-elite 2          ->  --elite-rewards         2 3 4
    --reward-elite-attempt 1  ->  --elite-attempt-rewards 1 1.5 2

Motivation: the floor pay already scales by act, so a FLAT elite pay made
deep elites steadily worse value per unit of risk than the floors around
them -- an act-3 elite cost act-3 HP for act-1 money. The ramp holds the
elite:floor ratio constant across acts (a won act-3 elite now pays 4+2=6
vs act-1's 2+1=3). Everything else in $runRewards is v22/v23's set verbatim.

WATCH the elite-dive hole: the entry pay is unconditional, and the implicit
death price is the forfeited HP potential, 4.0*phi(ratio). At the flat entry
of 1 the break-even sat at ~12.5% HP; at the act-3 entry of 2 it moves up to
~25% HP (phi(0.25)=0.5, *4.0 = 2.0). So in act 3 the agent is paid to dive
into an elite below a QUARTER health. `elites_fought` minus `elites` in the
s27 evals is the read that catches it; if it opens up, the fix is the
win-only ramp (flat entry 1) rather than a smaller win ramp.

FOUR more knobs turn on this generation, on top of the elite ramp above,
plus the foresight aux heads merged in below (SIX changes total vs v23 --
see the run log's attribution caveat):
  --ascension-random 0 10   Training samples ascension uniformly in [0,10]
                             per episode instead of fixing 10. The v19 mixed-
                             ascension caveat (deferred back then: obs did not
                             carry which ascension was in play, so a mixed
                             policy could not condition on it) is now RESOLVED
                             -- run.ascension rides in the obs (schema 13),
                             so mixed-ascension training is coherent this time.
  --reward-elite-escalator 0.5   Extra per-elite bonus that escalates within
                             a run (on top of the act ramp above), to keep
                             pressure on taking elites late in a run where
                             the ramp alone under-pays relative to accumulated
                             deck power.
  --event-ent-coef 0.01      Entropy bonus scoped to event-choice decisions
                             only, to counter the option-concentration read
                             flagged (untested) in the v23 log.
  --potion-timing-refund 0.25   Refunds part of the on-drink release penalty
                             for AnyTime potions used in elite/boss combat,
                             carried over from v22 (was already proven inert
                             on its own; this generation re-tests it stacked
                             with the other four levers).
  --hp-potential-low-share 0.5   Softens the HP-potential shaping curve's
                             concavity below half health, retired from the
                             s19 rung and revived here now that the elite-pay
                             passivity guards it was meant to police are live
                             reads again (see v24-run-log.md).

FORESIGHT HEADS (merged from the v25 plan, 2026-08-26 -- the standalone
train_curriculum_v25.ps1 was deleted; this run carries both generations).
Two new self-supervised aux heads ride the shared critic encoder alongside
v10's 3-floor HP-loss head. They are auxiliary LOSSES only: no reward term,
no advantage, no obs change.

    --aux-hp-coef      0.25   v10's head, unchanged (in $longHorizon below)
    --aux-win-coef     0.5    NEW: P(win | state), BCE
    --aux-hpturn-coef  0.5    NEW: HP lost before my next turn, MSE

The merge deliberately trades v25's clean single-lever attribution for one
saved 15M-step generation. Disentangling ablation, if a read comes back
weird: rerun with the two new coefs at 0, everything else identical.
SYNERGY: --ascension-random 0 10 is also the fix for the aux_win
positive-label starvation flagged in v25-run-log.md read #1 -- at fixed
asc-10 the v23 policy wins 0/150 so the win head collapses to "always
lose"; the ascension mix supplies real positive labels (asc-0 wins ~4.7%).

FRESH CSV, REQUIRED: train_torch's per-iteration log path is derived from
--save (train_torch.csv_path: runs/x.pt -> runs/run_logs/x.csv) and a row is
appended with the CURRENT CSV_FIELDS header only when the file is new. The
column list gained `aux_win` and `aux_turn` with the foresight heads, so
appending onto an older CSV would silently write rows under the wrong
header. runs/run_logs/sts2_run_torch_v24_s27.csv starts fresh -- but if you
re-tag or hand-copy a CSV into place, DELETE it first.

Post-run foresight reads (pre-registered in v25-run-log.md, amended for the
merged provenance) gate the Phase-4 search work: tools/foresight_probe.py
gates + the overnight tools/eval_search.py Tier-B measurement.

  Stage  Env  Asc  Steps  Notes
  s27    run   10    15M  continue runs/sts2_run_torch_v23_s26.pt
                          (--resume handoff, same kind, NO warm start).
                          v23 geometry verbatim; elite pay ramped by act.
                          --critic-warmup 4: reward function changed AND
                          the fresh aux tail heads perturb the shared
                          critic encoder from the first update (262144
                          steps, same as v22's 8 iters at batch 32768).

Pre-registered reads = docs/superpowers/plans/v24-run-log.md. Evals with
--merge-duplicates (the live decoder).

No rest mask, no potion mask, ever.

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .	rain_curriculum_v24.ps1                # real run; auto-evals s27
  .	rain_curriculum_v24.ps1 -Smoke         # 131072 steps, scratch tag
  .	rain_curriculum_v24.ps1 -Resume        # continue an interrupted run
#>
param(
    [long]$S27Steps = 15000000,
    [string]$Device = "cuda",
    [string]$Tag = "v24",
    [string]$SeedCkpt = "runs/sts2_run_torch_v23_s26_schema13.pt",
    [int]$NEnvs = 64,
    [int]$NWorkers = 8,
    [switch]$Resume,
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent  # scripts/ sits one level below repo root
$runs = Join-Path $root "runs"
if (-not (Test-Path $runs)) { New-Item -ItemType Directory $runs | Out-Null }
# venv (no dot) is the CUDA env: torch 2.13.0+cu130. The dotted .venv twin
# carries torch 2.13.0+cpu (plain-PyPI install, 2026-08-09) plus the
# onnx/onnxruntime tooling -- fine for pytest/export, WRONG for training.
# Do not "normalize" this to .venv again (that mistake shipped briefly on
# 2026-08-16 and would have trained s17/s18 on CPU).
$py = Join-Path $root "venv\Scripts\python.exe"

if ($Smoke) {
    $Tag = "${Tag}smoke"
    $S27Steps = 131072   # 2 batches at the new 65536-step batch
    Write-Host "SMOKE MODE: tag=$Tag, 131072 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{ 27 = Join-Path $runs "sts2_run_torch_${Tag}_s27.pt" }

if ((Test-Path $ckpt[27]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[27]) already exists." -ForegroundColor Red
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}
# Normalize to an ABSOLUTE path FIRST. $SeedCkpt is passed to Invoke-Stage as
# -PrevCkpt, whose `Test-Path $PrevCkpt` resolves against the CALLER's cwd --
# so a relative default silently fails that test when the script is launched
# from anywhere but the repo root (e.g. from inside scripts\), skipping the
# --resume branch and training 15M steps from random init. Join only when the
# caller did not already pass an absolute path.
if (-not [System.IO.Path]::IsPathRooted($SeedCkpt)) {
    $SeedCkpt = Join-Path $root $SeedCkpt
}
if (-not (Test-Path $SeedCkpt)) {
    Write-Host "SeedCkpt '$SeedCkpt' not found - nothing to extend." -ForegroundColor Red
    exit 1
}
$schema = & $py -c "import sys, torch; print(torch.load(sys.argv[1], map_location='cpu', weights_only=False).get('obs_schema'))" $SeedCkpt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not read SeedCkpt schema (python exited $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
if (($schema | Select-Object -Last 1).Trim() -ne "13") {
    Write-Host "SeedCkpt is not schema 13 - run tools\migrate_runobs_v24.py first." -ForegroundColor Red
    exit 1
}
$headVersion = & $py -c "import sys, torch; print(torch.load(sys.argv[1], map_location='cpu', weights_only=False).get('head_version'))" $SeedCkpt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not read SeedCkpt head_version (python exited $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
if (($headVersion | Select-Object -Last 1).Trim() -ne "5") {
    Write-Host "SeedCkpt is not head_version 5 - run tools\migrate_headv5.py first." -ForegroundColor Red
    exit 1
}

# v23's geometry, carried forward VERBATIM (this run changes reward only):
# --n-steps 1024 with n-envs 64 so whole runs (~694 decisions mean) fit
# inside one rollout segment; --minibatches 16 keeps the minibatch at
# 4096; --save-every 5 keeps the ~327k-step checkpoint cadence at the
# 65536-step batch. The checkpoint stores n_steps, so a resume inherits
# 1024 even without the flag -- the explicit flags keep the script honest.
$nEnvs = $NEnvs
$nSteps = 1024
$batchSize = [long]$nEnvs * $nSteps
# --n-workers 8 (vec_env AUTO_N_WORKERS is 4, tuned 2026-08-02 at 32 envs;
# this runs 64). Each worker steps its share of envs SEQUENTIALLY
# (vec_env._EnvGroup.step), so the rollout step waits on the slowest
# chain: 64/4 = 16 envs deep today, 64/8 = 8 deep here -- an even split,
# unlike 6 workers (11/10). Throughput-only: env seeding is by GLOBAL env
# index, so the worker layout cannot shift which stream an env gets, and
# n_workers is not stored in the checkpoint -- changing it mid-run does
# NOT confound the geometry experiment. Measured baseline at 4 workers:
# ~550 sps. Host cost: ~520 MB resident per worker.
$geom = @("--arch", "entset", "--shared-encoder", "--device", $Device,
          "--n-envs", "$nEnvs", "--n-steps", "$nSteps", "--minibatches", "16",
          "--n-workers", "$NWorkers",
          "--save-every", "5")

# v23's reward set with ONE change: the two flat elite terms become per-act
# ramps mirroring --floor-rewards' 1.0/1.5/2.0 multipliers. The by-act tuples
# REPLACE the flat scalars (run_env._elite_pay), so --reward-elite /
# --reward-elite-attempt are deliberately absent rather than left in as dead
# flags. Everything else is v22/v23 verbatim.
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "1.5",
                "--elite-rewards", "2", "3", "4",
                "--elite-attempt-rewards", "1", "1.5", "2",
                "--reward-boss", "3",
                "--hp-potential-scale", "4.0",
                "--rest-heal-shaping-knee-cap",
                "--energy-waste-penalty", "0.02",
                "--potion-potential-scale", "0.5", "--potion-death-expiry",
                "--potion-timing-refund", "0.25",
                "--reward-elite-escalator", "0.5",
                "--hp-potential-low-share", "0.5")

# Long-horizon levers, inherited from v23 unchanged, plus --event-ent-coef
# (new this generation: extra entropy bonus scoped to event-choice decisions).
$longHorizon = @("--gae-lambda", "0.99", "--aux-hp-coef", "0.25", "--event-ent-coef", "0.01")

# The two foresight heads merged from the v25 plan (see header). Auxiliary
# LOSSES on the shared encoder only -- neither touches the reward function or
# the advantage. --aux-hp-coef (v10's head) stays in $longHorizon above.
$foresight = @("--aux-win-coef", "0.5", "--aux-hpturn-coef", "0.5")

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
# train_torch saves its --save checkpoint every --save-every (5) iterations,
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
# -WarmStart marks a kind-switch handoff (combat<->run): UNUSED in v24 -- no
# kind switch here (a warm start would re-drop the run heads v11 rebuilt; the
# boss-drill option was deferred over exactly this cost). Kept verbatim so the
# helper stays byte-identical with the v10..v23 scripts.
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
               "--ascension", "$Asc", "--csv", $Csv, "--merge-duplicates")
    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) { Write-Host "$Name exited $code (continuing)" -ForegroundColor Yellow }
}

# No between-stage gate: single-stage plan. Reads are post-run, human-read,
# vs the v23_s26 --merge-duplicates baselines (reads table in v24-run-log.md).

# ── s27: v23 geometry verbatim + per-act elite ramp (2/3/4, 1/1.5/2)
#         + the two foresight aux heads ──
Invoke-Stage -Name "s27-run-asc10-elite-ramp" -SaveCkpt $ckpt[27] -PrevCkpt $SeedCkpt `
    -Steps $S27Steps -CriticWarmup 4 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension-random", "0", "10", "--lr", "3e-4") + $runRewards + $longHorizon + $foresight)

foreach ($asc in 10, 0) {
    # runs/run_logs/ (gitignored) is where every CSV lives now -- the eval
    # sidecars as well as train_torch's per-iteration log (train_torch.csv_path).
    if (Test-Path (Join-Path $root "runs/run_logs/eval_${Tag}_s27_asc${asc}.episodes.csv")) {
        Write-Host "s27-eval-asc$asc already recorded - skipping." -ForegroundColor DarkGray
    } else {
        Invoke-Eval -Name "s27-eval-asc$asc" -Ckpt $ckpt[27] -Asc $asc -Episodes 150 `
            -Csv "runs/run_logs/eval_${Tag}_s27_asc$asc"
    }
}
Write-Host "v24 elite-ramp + foresight run complete. Reads: docs/superpowers/plans/v24-run-log.md + v25-run-log.md (foresight probe/search gates)" -ForegroundColor Green
