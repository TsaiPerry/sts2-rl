<#
v26 (search distillation): one stage on the MERGED v24 s27 policy. This is a
clone of scripts/train_curriculum_v24.ps1 with the rewards, geometry and
foresight coefs carried VERBATIM -- the seed generation and this one train
under the SAME reward function on purpose, so the only delta vs v24_s27 is
the distillation gradient. Attribution is clean: any v26 read that moves is
the search term.

  --distill runs/distill/v26_batch1 --distill-coef 0.1
                              THE change this generation. A directory of
                              tools/search_worker.py .npz shards (obs, mask,
                              searched action distribution from a one-ply
                              expectimax). train_torch preloads the whole set
                              to the training device once and pays a bounded
                              masked cross-entropy toward those distributions
                              on every PPO minibatch. It is an ACTOR term: no
                              new parameters, no reward change, no obs change.
                              Ablation if a read is weird: drop both flags,
                              everything else identical.

  # --quantile-critic 32      DELIBERATELY OUT (decision 2026-08-26, recorded
                              per the Task-12 brief). The Phase-2 smoke gate
                              PASSED (v25-run-log.md: 2 iters, v 0.305 ->
                              0.233, sps ~343, no NaN), but the brief's second
                              condition -- v25's probe reads arguing for it --
                              cannot be met: the merged v24_s27 run has not
                              launched, so no foresight probe reads exist yet.
                              There is also a hard BLOCKER: a scalar->quantile
                              checkpoint has NO --resume entry point. The
                              n_quantiles stamp check refuses first, and this
                              script's seed path is --resume. Riding quantile
                              would need either a tools/migrate_quantile.py
                              restamp of the seed or a --warm-start handoff
                              (which drops the run heads). Revisit for v27
                              once the probe reads land AND one of those two
                              exists. Do not uncomment this line alone -- it
                              will fail at load.

  --critic-warmup 4           (0 UNDER -Smoke -- see below.) Kept VERBATIM
                              from the v24 script (the brief's
                              verbatim rule). v26 has NO fresh heads, so the
                              v24 justification (fresh aux tail heads
                              perturbing the shared critic encoder) does not
                              apply here. The v26 justification is the new
                              distillation gradient: it back-propagates
                              through the shared encoder + tied action heads
                              from update 1, which moves the representation
                              the critic reads. 4 iters = 262144 steps.

SMOKE USES --critic-warmup 0, DELIBERATELY. -Smoke buys 131072 steps =
exactly 2 iterations at the 65536-step batch, and train_torch skips the
distillation term entirely while `critic_only` (iteration < start_iter +
critic_warmup). At the real run's warmup of 4, BOTH smoke iterations would
be critic-only: distill_loss never called, the `distill` column NaN for the
whole smoke, and the three things the run actually risks -- the loss, the
gradient into the shared encoder, and the SPS tax -- never exercised. A
green smoke would have proven only the startup path. So the smoke sets the
warmup to 0 to reach the new code. This is the ONE knob where smoke and the
real run deliberately differ; smoke is a code-path proof, not a training
proof, so the missing critic rescale costs nothing.

NIGHTLY RHYTHM. The shard set is not a fixture. tools/search_worker.py
regenerates a FRESH batch from the LATEST checkpoint between training nights
(the search is only as good as the prior it expands), e.g.

  venv\Scripts\python.exe tools\search_worker.py runs\sts2_run_torch_v26_s28.pt `
      --bank <snapshot bank>.jsonl --out runs\distill\v26_batch2 `
      --decisions 5000 --k 5 --m 8

Regenerate into a FRESH --out directory and repoint -DistillDir; never mix
batches written by different checkpoints in one directory. The trainer
refuses an obs-contract mismatch itself -- train_torch.check_distill_provenance
compares provenance.json's obs_schema and card_obs against this run's and
exits fatally on any difference (hybrid and features share f/i dims 4736/1533
at schema 13, so no dim check could catch it). That check is NOT duplicated
here; the pre-flight below only proves the directory and its provenance.json
are THERE.

FRESH CSV, REQUIRED: train_torch derives csv_path from --save and writes the
header only when the file is new. CSV_FIELDS gained a `distill` column on top
of v25's aux_win/aux_turn, so runs/run_logs/sts2_run_torch_v26_s28.csv must
start FRESH -- never hand-copy, re-tag or append a v24/v25-era CSV into that
path. Delete it instead.

WATCH the elite-dive hole (inherited from v24, unchanged): elite entry pay is
unconditional, and at the act-3 entry of 2 the death break-even moves from
~12.5% to ~25% HP -- the agent is PAID to dive below quarter health. Read:
elites_fought minus elites in the s28 evals.

  Stage  Env  Asc   Steps  Notes
  s28    run  0-10    15M  --resume from $SeedCkpt (same kind, NO warm
                           start) + search distillation. --critic-warmup 4
                           (see above).

LAUNCH BLOCKERS (Perry's gate, both must clear first):
  * runs/sts2_run_torch_v24_s27.pt must be FINISHED. Existence is NOT
    completion: train_torch rewrites that path every --save-every (5)
    iterations, so the file appears within minutes of v24's launch (it was
    on disk mid-run at global_step 125108224 on 2026-08-26). This script
    ENFORCES completion -- the seed-completion gate below refuses any seed
    whose global_step is below v24's finish line. That line is its own
    seed's step plus the steps v24 ACTUALLY trains, which is NOT 15M:
    n_iters = 15000000 // 65536 = 228 iterations = 14942208 steps, so a
    finished v24_s27 lands at 120848384 + 14942208 = 135790592 and never
    goes higher. -AllowPartialSeed downgrades the gate to a warning (and
    -Smoke implies it, since a smoke is a code-path proof rather than a
    generation); do not pass it for a real run. -Smoke still needs the
    shard set, so it cannot run until a batch is generated either.
  * the Tier-B tools/eval_search.py measurement on v24_s27 must be GO
    (>= 3pt death-rate gap at >= 5% flip rate) before any v26 launch. If
    search does not beat the policy, there is nothing to distil.

Reads: docs/superpowers/plans/v26-run-log.md (pre-registered gates), with
v24-run-log.md + v25-run-log.md for the inherited reward/foresight reads.
Evals use --merge-duplicates (the live decoder). No rest mask, no potion
mask, ever.

  .venv\Scripts\python.exe -m pytest -q      # green before launching
  .\scripts\train_curriculum_v26.ps1         # real run; auto-evals s28
  .\scripts\train_curriculum_v26.ps1 -Smoke  # 131072 steps, scratch tag
  .\scripts\train_curriculum_v26.ps1 -Resume # continue an interrupted run
#>
param(
    [long]$S28Steps = 15000000,
    [string]$Device = "cuda",
    [string]$Tag = "v26",
    [string]$SeedCkpt = "runs/sts2_run_torch_v24_s27.pt",
    [string]$DistillDir = "runs/distill/v26_batch1",
    [int]$NEnvs = 64,
    [int]$NWorkers = 8,
    [switch]$Resume,
    [switch]$Smoke,
    [switch]$AllowPartialSeed
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
    $S28Steps = 131072   # 2 batches at the new 65536-step batch
    Write-Host "SMOKE MODE: tag=$Tag, 131072 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
    Write-Host "SMOKE MODE: --critic-warmup 0 (the real run uses 4) so the 2 smoke iterations actually reach the distillation term." -ForegroundColor Yellow
}

# See the header: at the real run's 4, both smoke iterations would be
# critic_only and train_torch skips distill there -- the smoke would never call
# distill_loss. 0 under -Smoke buys the code-path proof the smoke exists for.
$criticWarmup = 4
if ($Smoke) { $criticWarmup = 0 }

$ckpt = @{ 28 = Join-Path $runs "sts2_run_torch_${Tag}_s28.pt" }

if ((Test-Path $ckpt[28]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[28]) already exists." -ForegroundColor Red
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
    Write-Host "v26 seeds from the MERGED v24 s27 run. If v24 has not finished," -ForegroundColor Red
    Write-Host "this refusal is expected: launch scripts\train_curriculum_v24.ps1 first." -ForegroundColor Red
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

# The batch geometry, hoisted above the seed-completion gate because the floor
# arithmetic below needs $batchSize. Values are v23's, carried VERBATIM -- the
# rationale comment lives with $geom further down.
$nEnvs = $NEnvs
$nSteps = 1024
$batchSize = [long]$nEnvs * $nSteps

# ── seed COMPLETION gate: existence is not completion ──
# train_torch rewrites its --save path every --save-every (5) iterations, so
# runs/sts2_run_torch_v24_s27.pt appears minutes after v24 launches and keeps
# MOVING for the rest of the run (measured at global_step 125108224 mid-run on
# 2026-08-26). Seeding v26 off a moving checkpoint -- while distilling shards
# generated from a DIFFERENT moving snapshot of it -- would burn a 15M-step
# night on a confound that none of the four pre-registered reads could see.
# The Test-Path above cannot tell the difference; global_step can.
#
# Floor = v24's OWN seed's global_step + the steps v24 ACTUALLY trains. That is
# NOT its 15M --timesteps: train_torch runs n_iters = timesteps // batch_size,
# so 15000000 // 65536 = 228 iterations = 14942208 steps, and a FINISHED
# v24_s27 lands 57792 steps SHORT of 15M. It never climbs higher either --
# Invoke-Stage's "remaining < batchSize -> already complete" branch retires the
# stage on the truncated total. Comparing against a bare +15000000 would fail
# closed on the exact input this gate exists to permit.
#
# The floor is re-derived live from the v23 seed whenever it is still on disk;
# the constant is the same arithmetic as measured 2026-08-26
# (120848384 + 14942208), a fallback only.
$stageBudget = [long]15000000                                  # v24's $S27Steps
# v24's OWN batch geometry (64 envs x 1024 steps) -- NOT this run's $batchSize.
# The floor states what v24 already did, so a v26 -NEnvs must not rewrite v24's
# fixed history; at the default -NEnvs 64 this is byte-for-byte the same value.
$v24Batch = [long]64 * 1024
$stageSteps = ([long][math]::Floor($stageBudget / $v24Batch)) * $v24Batch
$seedFloor = [long]135790592                                   # = 120848384 + $stageSteps
$stepCode = "import sys, torch; print(int(torch.load(sys.argv[1], map_location='cpu', weights_only=False).get('global_step', 0)))"
$v23Seed = Join-Path $runs "sts2_run_torch_v23_s26_schema13.pt"
if (Test-Path $v23Seed) {
    $v23Step = & $py -c $stepCode $v23Seed
    if ($LASTEXITCODE -eq 0) {
        try {
            $seedFloor = [long](($v23Step | Select-Object -Last 1).Trim()) + $stageSteps
        } catch {
            Write-Host "The v23 seed's global_step is not a number - using the recorded floor $seedFloor." -ForegroundColor Yellow
        }
    } else {
        Write-Host "Could not read the v23 seed's global_step - using the recorded floor $seedFloor." -ForegroundColor Yellow
    }
}
$seedStepOut = & $py -c $stepCode $SeedCkpt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not read SeedCkpt global_step (python exited $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
# A non-numeric last line (a torch warning, a None, a truncated print) must take
# the same refusal path as any other unreadable seed, not throw a raw cast error.
$seedStep = $null
try {
    $seedStep = [long](($seedStepOut | Select-Object -Last 1).Trim())
} catch {
    Write-Host "SeedCkpt global_step is not a number: '$(($seedStepOut | Select-Object -Last 1))'." -ForegroundColor Red
    Write-Host "Cannot prove v24 finished, so refusing. Re-check the checkpoint." -ForegroundColor Red
    exit 1
}
# -Smoke is a code-path proof, not a generation, so an in-flight seed is fine.
$partialSeedOk = $AllowPartialSeed -or $Smoke
if ($seedStep -lt $seedFloor) {
    $msg = "SeedCkpt is at global_step $seedStep, below v24's finish line of $seedFloor - v24 is UNFINISHED (or still training right now)."
    if ($partialSeedOk) {
        Write-Host $msg -ForegroundColor Yellow
        $why = if ($AllowPartialSeed) { "-AllowPartialSeed given" } else { "smoke mode" }
        Write-Host "$why - continuing anyway. This is NOT a valid v26 generation." -ForegroundColor Yellow
    } else {
        Write-Host $msg -ForegroundColor Red
        Write-Host "Distilling from a moving seed silently confounds every read in v26-run-log.md." -ForegroundColor Red
        Write-Host "Wait for scripts\train_curriculum_v24.ps1 to finish, then regenerate the shard batch" -ForegroundColor Red
        Write-Host "from the FINISHED checkpoint. Pass -AllowPartialSeed only for a throwaway experiment." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "SeedCkpt at global_step $seedStep (>= v24 finish line $seedFloor)." -ForegroundColor Cyan
}

# ── distill shard-set pre-flight (mirrors the SeedCkpt gate above) ──
# Absolute for the same reason $SeedCkpt is: Test-Path here resolves against
# the CALLER's cwd, while the trainer runs with -WorkingDirectory $root. Pass
# the ABSOLUTE path to --distill so the two can never disagree.
if (-not [System.IO.Path]::IsPathRooted($DistillDir)) {
    $DistillDir = Join-Path $root $DistillDir
}
if (-not (Test-Path $DistillDir -PathType Container)) {
    Write-Host "DistillDir '$DistillDir' not found - nothing to distil from." -ForegroundColor Red
    Write-Host "Generate a shard batch from the LATEST checkpoint first, e.g." -ForegroundColor Red
    Write-Host "  venv\Scripts\python.exe tools\search_worker.py $SeedCkpt --bank <bank>.jsonl --out $DistillDir --decisions 5000 --k 5 --m 8" -ForegroundColor Red
    exit 1
}
$prov = Join-Path $DistillDir "provenance.json"
if (-not (Test-Path $prov)) {
    Write-Host "No provenance.json in '$DistillDir'." -ForegroundColor Red
    Write-Host "tools\search_worker.py always writes one; without it the shard set's" -ForegroundColor Red
    Write-Host "obs schema and card-obs mode cannot be checked, and a mismatch there is" -ForegroundColor Red
    Write-Host "dimensionally invisible (hybrid and features share 4736/1533 at schema 13)." -ForegroundColor Red
    exit 1
}
$shardCount = @(Get-ChildItem -Path $DistillDir -Filter *.npz -File -ErrorAction SilentlyContinue).Count
if ($shardCount -eq 0) {
    Write-Host "No .npz shards in '$DistillDir' (provenance.json alone is not a shard set)." -ForegroundColor Red
    exit 1
}
Write-Host "Distilling from $DistillDir ($shardCount shard(s))." -ForegroundColor Cyan
# The obs-contract check itself is train_torch.check_distill_provenance's job
# (obs_schema + card_obs vs THIS run's) and is deliberately not duplicated
# here -- a second copy would rot out of sync with the trainer's.

# v23's geometry, carried forward VERBATIM (this run changes the actor loss
# only): --n-steps 1024 with n-envs 64 so whole runs (~694 decisions mean) fit
# inside one rollout segment; --minibatches 16 keeps the minibatch at
# 4096; --save-every 5 keeps the ~327k-step checkpoint cadence at the
# 65536-step batch. The checkpoint stores n_steps, so a resume inherits
# 1024 even without the flag -- the explicit flags keep the script honest.
# ($nEnvs / $nSteps / $batchSize are assigned above the seed-completion gate,
# which needs $batchSize for its truncation arithmetic.)
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

# v24's reward set, VERBATIM. The seed policy was trained under exactly these
# terms, so v26 introduces no reward confound on top of the distillation term.
# Do not "tidy" a lever out of this block: any edit here re-opens attribution.
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

# Long-horizon levers, inherited from v23/v24 unchanged.
$longHorizon = @("--gae-lambda", "0.99", "--aux-hp-coef", "0.25", "--event-ent-coef", "0.01")

# The two foresight heads (merged into v24 on 2026-08-26), carried VERBATIM.
# Auxiliary LOSSES on the shared encoder only -- neither touches the reward
# function or the advantage. --aux-hp-coef (v10's head) stays in $longHorizon.
$foresight = @("--aux-win-coef", "0.5", "--aux-hpturn-coef", "0.5")

# THE v26 delta. Masked cross-entropy toward the searched action distribution,
# sampled (with replacement) up to train_torch.DISTILL_MAX_ROWS = 4096 rows per
# minibatch. Coef 0.1 is the plan's opening weight -- big enough to bend the
# actor, small enough that the policy gradient still owns the update.
$distill = @("--distill", $DistillDir, "--distill-coef", "0.1")
# See the header: --quantile-critic 32 is deliberately NOT here.
# $quantile = @("--quantile-critic", "32")

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
# vs the v24_s27 --merge-duplicates baselines (reads table in v26-run-log.md).

# ── s28: v24's rewards/geometry/foresight VERBATIM + search distillation ──
Invoke-Stage -Name "s28-run-search-distill" -SaveCkpt $ckpt[28] -PrevCkpt $SeedCkpt `
    -Steps $S28Steps -CriticWarmup $criticWarmup -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension-random", "0", "10", "--lr", "3e-4") + $runRewards + $longHorizon + $foresight + $distill)

foreach ($asc in 10, 0) {
    # runs/run_logs/ (gitignored) is where every CSV lives now -- the eval
    # sidecars as well as train_torch's per-iteration log (train_torch.csv_path).
    if (Test-Path (Join-Path $root "runs/run_logs/eval_${Tag}_s28_asc${asc}.episodes.csv")) {
        Write-Host "s28-eval-asc$asc already recorded - skipping." -ForegroundColor DarkGray
    } else {
        Invoke-Eval -Name "s28-eval-asc$asc" -Ckpt $ckpt[28] -Asc $asc -Episodes 150 `
            -Csv "runs/run_logs/eval_${Tag}_s28_asc$asc"
    }
}
Write-Host "v26 search-distillation run complete. Reads: docs/superpowers/plans/v26-run-log.md (and re-run the Tier-B tools/eval_search.py measurement against s28)" -ForegroundColor Green
