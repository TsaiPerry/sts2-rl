<#
v27 (EXPERT ITERATION on search distillation): stage s29, three CYCLES on the
MERGED v24 s27 policy. This is a clone of scripts/train_curriculum_v26.ps1 with
the rewards, geometry, foresight coefs and every helper carried VERBATIM -- the
seed generation, v26 and this one all train under the SAME reward function on
purpose, so the only deltas vs v26_s28 are (a) the distillation coefficient,
(b) sharpened + decisiveness-FILTERED targets, and (c) the ExIt loop itself.

WHY v27 EXISTS. v26_s28 read NEGATIVE (08-28 diagnosis, verdict (b)
MEMORIZED): the policy learned its 5,004 shards (on-shard dCE 0.766,
decisive-flip agreement 0.710) while holdout generalization went the wrong way
(dCE -0.065, agree_flip 0.133 < the 0.19-0.21 null). Two fixes ride here:
sharper, decisive targets (a fixed batch of near-tied distributions is
memorizable and teaches nothing) and a fresh batch per cycle regenerated from
the LATEST policy (a static batch is an exam the student can only memorize).

  --distill <dir> --distill-coef 0.5
                              THE change vs v26 (which ran 0.1). A directory of
                              tools/search_worker.py .npz shards (obs, mask,
                              searched action distribution from a one-ply
                              expectimax). train_torch preloads the whole set
                              to the training device once and pays a bounded
                              masked cross-entropy toward those distributions
                              on every PPO minibatch. It is an ACTOR term: no
                              new parameters, no reward change, no obs change.
                              Ablation if a read is weird: drop both flags,
                              everything else identical.

  THE TARGET CALIBRATION (08-28, v27-run-log.md). Task 4's temperature sweep
                              was BLOCKED: NO temperature clears the
                              pre-registered "median top1-top2 target-mass gap
                              >= 0.25" bar, because the raw rollout scores are
                              near-tied (median gap ~0.016; 19.5% of records
                              score every candidate EXACTLY equal, where a
                              softmax is temperature-invariant). Task 4b
                              replaced it with a SOURCE filter: keep only
                              decisions whose raw top1-top2 score gap exceeds
                              0.05. That retains ~41% of searched decisions and
                              lifts the median target gap to 0.317 at T = 0.25.
                              So the pinned generator settings are
                              temperature 0.25 AND min_score_gap 0.05, and the
                              per-cycle pre-flight below REFUSES any shard set
                              whose provenance disagrees with either. A missing
                              min_score_gap key means 0.0 (pre-filter) and is
                              therefore a refusal, exactly as
                              merge_distill.py's MUST_MATCH_DEFAULTS reads it.

  # --quantile-critic 32      STILL deliberately out (v26's reasoning, 08-26,
                              unchanged): a scalar->quantile checkpoint has NO
                              --resume entry point, and this script's seed path
                              is --resume. Do not uncomment this line alone --
                              it will fail at load.

  --critic-warmup 4           (0 UNDER -Smoke -- see below.) Kept VERBATIM
                              from the v24/v26 scripts (the brief's
                              verbatim rule). v27 has NO fresh heads, so the
                              v24 justification (fresh aux tail heads
                              perturbing the shared critic encoder) does not
                              apply here. The v26/v27 justification is the
                              distillation gradient: it back-propagates
                              through the shared encoder + tied action heads
                              from update 1, which moves the representation
                              the critic reads. 4 iters = 262144 steps. NOTE
                              the flag's SEMANTICS changed on 2026-08-28 (the
                              critic-warmup-freeze plan: the encoder is now
                              FROZEN for the warmup iterations rather than
                              merely actor-suppressed). The value is kept as
                              v26 had it; the run log records the change.
                              Every cycle pays its own warmup -- each cycle
                              starts training against a NEW target
                              distribution, which is the same reason v26 paid
                              one at all.

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

THE CYCLE STRUCTURE (the ExIt loop). ONE INVOCATION RUNS ONE CYCLE and then
STOPS. Three cycles make a generation:

  Cycle  Resumes from                       Distills   Trains
  1      runs/sts2_run_torch_v24_s27.pt     batch 1    76 iters
  2      runs/sts2_run_torch_v27_s29.pt     batch 2    76 iters
  3      runs/sts2_run_torch_v27_s29.pt     batch 3    76 iters

  3 x 76 = 228 iterations = 14942208 steps -- byte-for-byte the same total a
  single v26 generation trained, so the two are comparable step-for-step.

  THE PER-CYCLE STEP BUDGET IS DERIVED, NOT TYPED. train_torch runs
  n_iters = timesteps // batch_size, so a hand-typed budget silently buys a
  DIFFERENT number of iterations than it names (this is the same truncation
  lesson as the seed floor below, where 15000000 buys 228 iterations = only
  14942208 steps). Here: 15000000 // 65536 = 228 iterations for a whole
  generation, 228 / 3 = 76 iterations per cycle, and 76 * 65536 = 4980736
  steps. NOTE: the v27 plan text names 5013504 for this number; that literal
  disagrees with its OWN arithmetic (76 x 65536 = 4980736, and 3 x 4980736 =
  14942208 = the stated total, whereas 3 x 5013504 = 15040512 is not
  reachable). Both literals floor to the same 76 iterations at this batch, so
  the choice is cosmetic to the trainer -- but 4980736 is the honest one and
  it keeps Invoke-Stage's remaining/done arithmetic exact, so that is what
  -CycleSteps defaults to.

BETWEEN CYCLES, THE OPERATOR WORKS (the script prints this block and exits;
it does NOT automate it, because harvest + generation is hours of GPU/CPU that
Perry schedules overnight, and RAM caps the wave width at 3):

  (1) harvest a FRESH bank from the LATEST checkpoint -- the 08-27 recipe,
      300 eps asc 10 + a 100-eps asc-0 top-up for act-2/3 coverage, with a NEW
      seed range per cycle so no cycle re-walks another cycle's episodes;
  (2) scripts\gen_distill_batch.ps1 -Ckpt <latest> -Bank <fresh>
      -TotalRecords 5000 -Temperature 0.25   (-MinScoreGap defaults to 0.05;
      -TotalRecords counts KEPT records since the 08-28 filter landed);
  (3) relaunch this script with -Cycle N+1 -DistillDir <the new merged dir>.

  The freshness contract is enforced MECHANICALLY, not by discipline: the
  pre-flight below refuses unless the shard set's provenance `ckpt` IS the
  checkpoint this cycle resumes from. A batch generated from last cycle's
  policy cannot be fed to this one by accident. CAVEAT: that gate is PATH-based
  -- between cycles 2 and 3 the provenance ckpt string is the same s29 path, so
  it cannot tell a stale cycle-2 batch from a fresh cycle-3 one; the operator
  block's "do not train into s29.pt between generate and relaunch" (printed at
  the end of each cycle) is load-bearing there.

Never mix batches written by different checkpoints in one directory; always
generate into a FRESH -OutDir and repoint -DistillDir. The trainer refuses an
obs-contract mismatch itself -- train_torch.check_distill_provenance compares
provenance.json's obs_schema and card_obs against this run's and exits fatally
on any difference (hybrid and features share f/i dims 4736/1533 at schema 13,
so no dim check could catch it). That check is NOT duplicated here; the
pre-flight below proves the directory, its provenance.json, its shards, and
the three generator stamps (ckpt / temperature / min_score_gap).

PER-CYCLE READ HOOK. After each cycle the script prints the two
tools/distill_diag.py commands that score the cycle-START and cycle-END
checkpoints against BOTH this cycle's training batch and its holdout exam, and
the pre-registered gate:

  holdout dCE >= 1/4 of the on-shard dCE  AND  holdout agree_flip up >= 0.05

Scoring needs the cycle's start checkpoint, but --save is overwritten IN
PLACE, so the script COPIES it to runs/sts2_run_torch_v27_s29.cycle<N>.pt
BEFORE training. That copy is write-once: an existing cycle<N>.pt is REUSED
(the interrupted-cycle resume path) and never overwritten, because overwriting
it would replace the "before" half of the cycle's own measurement with its
"after" half and no read downstream could tell. The v24_s27 seed file itself
is only ever READ.

FRESH CSV, REQUIRED: train_torch derives csv_path from --save and writes the
header only when the file is new, so runs/run_logs/sts2_run_torch_v27_s29.csv
must start FRESH -- never hand-copy, re-tag or append a v24/v25/v26-era CSV
into that path. Delete it instead. Cycle 1 REFUSES to launch if that file
already exists (cycles 2 and 3 append to the one cycle 1 created, which is the
whole point of a single --save path).

WATCH the elite-dive hole (inherited from v24, unchanged): elite entry pay is
unconditional, and at the act-3 entry of 2 the death break-even moves from
~12.5% to ~25% HP -- the agent is PAID to dive below quarter health. Read:
elites_fought minus elites in the s29 evals.

  Stage  Env  Asc   Steps  Notes
  s29    run  0-10  14.9M  three cycles of 4980736 steps. Cycle 1 --resumes
                           from $SeedCkpt (same kind, NO warm start); cycles
                           2-3 continue s29's own checkpoint. Search
                           distillation at coef 0.5 against a per-cycle FRESH
                           batch. --critic-warmup 4 per cycle (see above).

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
    (>= 3pt death-rate gap at >= 5% flip rate) before any v27 launch. It was
    measured GO on 2026-08-27 (+9.3 / +9.9 pts, flip 27.2%, 161 fights). If
    search does not beat the policy, there is nothing to distil.

Reads: docs/superpowers/plans/v27-run-log.md (pre-registered gates and the
08-28 calibration/amendment entries), with v26-run-log.md for the diagnosed
memorization failure this generation answers and v24/v25-run-log.md for the
inherited reward/foresight reads. Evals use --merge-duplicates (the live
decoder). No rest mask, no potion mask, ever.

  .venv\Scripts\python.exe -m pytest -q      # green before launching
  .\scripts\train_curriculum_v27.ps1 -Cycle 1 -DistillDir runs\distill\v27_batch1
  .\scripts\train_curriculum_v27.ps1 -Cycle 2 -DistillDir runs\distill\v27_batch2
  .\scripts\train_curriculum_v27.ps1 -Cycle 3 -DistillDir runs\distill\v27_batch3
  .\scripts\train_curriculum_v27.ps1 -Cycle 1 -DistillDir <dir> -Smoke
                                             # 131072 steps, scratch tag
  Re-running an interrupted cycle with the SAME -Cycle/-DistillDir resumes it.
#>
param(
    # 4980736 = 76 iterations x the 65536-step batch. DERIVED, not typed: see
    # the cycle-structure block in the header (and $cycleStepsCheck below,
    # which re-derives it and refuses a value that is not a whole number of
    # iterations of the generation budget).
    [long]$CycleSteps = 4980736,
    [ValidateRange(1, 3)][int]$Cycle = 1,
    [string]$Device = "cuda",
    [string]$Tag = "v27",
    [string]$SeedCkpt = "runs/sts2_run_torch_v24_s27.pt",
    # NO DEFAULT, deliberately -- the whole ExIt contract is that each cycle
    # distils a batch generated from THAT cycle's own starting policy, so a
    # default would let cycle 2 or 3 silently inherit cycle 1's stale shards.
    # The refusal below is explicit rather than [Parameter(Mandatory)] because
    # a mandatory parameter PROMPTS, and this script gets launched
    # non-interactively.
    [string]$DistillDir = "",
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

if ($DistillDir -eq "") {
    Write-Host "-DistillDir is required (there is no default, on purpose)." -ForegroundColor Red
    Write-Host "Every cycle distils a batch generated from THAT cycle's own starting" -ForegroundColor Red
    Write-Host "policy; a default would let a later cycle inherit stale shards silently." -ForegroundColor Red
    Write-Host "  .\scripts\train_curriculum_v27.ps1 -Cycle 1 -DistillDir runs\distill\v27_batch1" -ForegroundColor Red
    exit 1
}

if ($Smoke) {
    $Tag = "${Tag}smoke"
    $CycleSteps = 131072   # 2 batches at the new 65536-step batch
    Write-Host "SMOKE MODE: tag=$Tag, 131072 steps/cycle. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
    Write-Host "SMOKE MODE: --critic-warmup 0 (the real run uses 4) so the 2 smoke iterations actually reach the distillation term." -ForegroundColor Yellow
}

# See the header: at the real run's 4, both smoke iterations would be
# critic_only and train_torch skips distill there -- the smoke would never call
# distill_loss. 0 under -Smoke buys the code-path proof the smoke exists for.
$criticWarmup = 4
if ($Smoke) { $criticWarmup = 0 }

$ckpt = @{ 29 = Join-Path $runs "sts2_run_torch_${Tag}_s29.pt" }
# The cycle-START retention copy (see the header). One per cycle, write-once.
$cycleCkpt = Join-Path $runs "sts2_run_torch_${Tag}_s29.cycle$Cycle.pt"

# The save path is SHARED by all three cycles (one lineage, one CSV), so
# "already exists" means opposite things at cycle 1 and at cycles 2/3.
if ($Cycle -eq 1) {
    if ((Test-Path $ckpt[29]) -and -not $Resume -and -not $Smoke) {
        Write-Host "$($ckpt[29]) already exists." -ForegroundColor Red
        Write-Host "Pass -Resume to continue it, -Cycle 2/3 to run a later cycle, or -Tag <name> for a new checkpoint set."
        exit 1
    }
} elseif (-not (Test-Path $ckpt[29])) {
    Write-Host "-Cycle $Cycle asked for, but $($ckpt[29]) does not exist." -ForegroundColor Red
    Write-Host "Cycle $Cycle continues the checkpoint cycle $($Cycle - 1) produced." -ForegroundColor Red
    Write-Host "Run the earlier cycle(s) first: -Cycle 1 -DistillDir <batch 1>." -ForegroundColor Red
    exit 1
}

# ── FRESH CSV (see the header) ──
# train_torch derives its per-iteration CSV from --save and only writes the
# header when the file is NEW, so a pre-existing v27_s29.csv would silently
# append this generation's rows onto some other generation's columns. Cycle 1
# is the only cycle that may create it; cycles 2 and 3 append to the one cycle
# 1 wrote, which is exactly what a single --save lineage should do.
$runCsv = Join-Path $root "runs/run_logs/sts2_run_torch_${Tag}_s29.csv"
if ($Cycle -eq 1 -and (Test-Path $runCsv) -and -not $Resume -and -not $Smoke) {
    Write-Host "$runCsv already exists." -ForegroundColor Red
    Write-Host "train_torch writes the CSV header only for a NEW file, so this run's rows" -ForegroundColor Red
    Write-Host "would be appended under whatever header is already there. DELETE it (or" -ForegroundColor Red
    Write-Host "move it aside) before launching cycle 1." -ForegroundColor Red
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
    Write-Host "v27 seeds from the MERGED v24 s27 run (same seed v26 used). If v24 has not finished," -ForegroundColor Red
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

# ── the per-cycle budget, RE-DERIVED (see the header's cycle-structure block) ──
# The generation budget is v26's 15000000, which train_torch truncates to
# 15000000 // 65536 = 228 iterations = 14942208 steps; split three ways that is
# 76 iterations = 4980736 steps per cycle. Derived from the SAME fixed
# 65536-step geometry the floor above uses ($v24Batch, NOT this run's
# $batchSize): the three cycles must add up to one v26 generation no matter
# what -NEnvs this invocation runs, or the step-for-step comparison v27 exists
# to make is not a comparison. The check is a warning, not a refusal: a
# deliberate -CycleSteps override is a legitimate experiment, an accidental
# one should be loud.
$genIters = [long][math]::Floor([long]15000000 / ([long]64 * 1024))    # 228
$cycleStepsCheck = ([long][math]::Floor($genIters / 3)) * ([long]64 * 1024)  # 4980736
if (-not $Smoke -and $CycleSteps -ne $cycleStepsCheck) {
    Write-Host "-CycleSteps $CycleSteps is not the derived per-cycle budget $cycleStepsCheck" -ForegroundColor Yellow
    Write-Host "($genIters iters per generation / 3 cycles x 65536). Three cycles will NOT sum to" -ForegroundColor Yellow
    Write-Host "v26's 14942208 steps, so the step-for-step v26 comparison is off. Continuing." -ForegroundColor Yellow
}

# ── seed COMPLETION gate: existence is not completion ──
# train_torch rewrites its --save path every --save-every (5) iterations, so
# runs/sts2_run_torch_v24_s27.pt appears minutes after v24 launches and keeps
# MOVING for the rest of the run (measured at global_step 125108224 mid-run on
# 2026-08-26). Seeding v27 off a moving checkpoint -- while distilling shards
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
# The floor states what v24 already did, so a v27 -NEnvs must not rewrite v24's
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
        Write-Host "$why - continuing anyway. This is NOT a valid v27 generation." -ForegroundColor Yellow
    } else {
        Write-Host $msg -ForegroundColor Red
        Write-Host "Distilling from a moving seed silently confounds every read in v27-run-log.md." -ForegroundColor Red
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

# ── the two v27 provenance gates: FRESHNESS and CALIBRATION ──────────────────
# These are the mechanical half of the ExIt contract. v26 failed by MEMORIZING
# one static batch of near-tied targets; both of those failure modes are
# invisible at training time and only surface a night later, so they are
# refused HERE.
#
# GATE 1 (freshness): the shard set's provenance `ckpt` must BE the checkpoint
# this cycle resumes from -- the seed at cycle 1, s29's own save path at cycles
# 2-3 (which is what the operator points gen_distill_batch's -Ckpt at, and
# which the cycle-start copy below preserves). Nothing else can catch this:
# obs schema, dims and card_obs are all identical across cycles, so a cycle-1
# batch fed to cycle 3 loads and trains perfectly while teaching the policy a
# two-cycle-old expert.
#
# GATE 2 (calibration): temperature 0.25 AND min_score_gap 0.05, the pinned
# 08-28 values (Task 4 BLOCKED -> Task 4b's decisiveness filter; see the
# header). Float tolerance rather than -ne because the stamps made a round trip
# through JSON. A MISSING min_score_gap key reads as 0.0 -- an unfiltered,
# pre-08-28 shard set -- which is a refusal, and deliberately the same reading
# merge_distill.py's MUST_MATCH_DEFAULTS and gen_distill_batch.ps1's resume
# pre-flight take, so the three layers cannot disagree about an old directory.
$DistillTemperature = 0.25
$DistillMinScoreGap = 0.05
$expectedGenCkpt = if ($Cycle -eq 1) { $SeedCkpt } else { $ckpt[29] }
# provenance stamps whatever path the generator was handed. gen_distill_batch
# rooted it absolute, but a hand-run search_worker may have written a relative
# one; resolve those against the repo root (every generator runs from there),
# and compare case-insensitively with separators normalized -- Windows paths
# that differ only in slash or case are the same file, and a spurious refusal
# here costs a night of GPU.
function Resolve-ProvPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    $p = $Path
    if (-not [System.IO.Path]::IsPathRooted($p)) { $p = Join-Path $root $p }
    try { $p = [System.IO.Path]::GetFullPath($p) } catch { }
    return $p.Replace('/', '\').TrimEnd('\')
}
$provData = $null
try {
    $provData = Get-Content -LiteralPath $prov -Raw | ConvertFrom-Json
} catch {
    Write-Host "'$prov' is not readable JSON: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Cannot prove the shard set's generator, so refusing." -ForegroundColor Red
    exit 1
}
$provCkpt = Resolve-ProvPath ("$($provData.ckpt)")
$wantCkpt = Resolve-ProvPath $expectedGenCkpt
if ($provCkpt -ne $wantCkpt -and -not $provCkpt.Equals($wantCkpt, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "STALE SHARD SET: '$DistillDir' was generated from a DIFFERENT checkpoint." -ForegroundColor Red
    Write-Host "  provenance ckpt : $provCkpt" -ForegroundColor Red
    Write-Host "  cycle $Cycle resumes: $wantCkpt" -ForegroundColor Red
    Write-Host "Expert iteration only works if each cycle's targets come from the policy that" -ForegroundColor Red
    Write-Host "cycle STARTS from; distilling an older expert is what v26 did, and it memorized." -ForegroundColor Red
    Write-Host "Regenerate: scripts\gen_distill_batch.ps1 -Ckpt $expectedGenCkpt -Bank <fresh> -TotalRecords 5000 -Temperature $DistillTemperature" -ForegroundColor Red
    exit 1
}
$provTemp = $null
try { $provTemp = [double]$provData.temperature } catch { }
$provGap = 0.0   # a missing key means the pre-filter default, i.e. unfiltered
if ($null -ne $provData.min_score_gap) {
    try { $provGap = [double]$provData.min_score_gap } catch { $provGap = [double]::NaN }
}
$calBad = @()
if ($null -eq $provTemp -or [math]::Abs($provTemp - $DistillTemperature) -gt 1e-9) {
    $calBad += "temperature $($provData.temperature) (v27 requires $DistillTemperature)"
}
if ([double]::IsNaN($provGap) -or [math]::Abs($provGap - $DistillMinScoreGap) -gt 1e-9) {
    $shown = if ($null -eq $provData.min_score_gap) { "0.0 (key absent = pre-filter, unfiltered)" } else { "$($provData.min_score_gap)" }
    $calBad += "min_score_gap $shown (v27 requires $DistillMinScoreGap)"
}
if ($calBad.Count -gt 0) {
    Write-Host "UNCALIBRATED SHARD SET: '$DistillDir' was generated with the wrong target settings." -ForegroundColor Red
    foreach ($b in $calBad) { Write-Host "    $b" -ForegroundColor Red }
    Write-Host "The 08-28 calibration found NO temperature clears the sharpness bar on raw" -ForegroundColor Red
    Write-Host "rollout scores (median top1-top2 gap ~0.016; 19.5% exact ties). Only the" -ForegroundColor Red
    Write-Host "SOURCE filter does: -MinScoreGap 0.05 keeps ~41% of decisions and lifts the" -ForegroundColor Red
    Write-Host "median target gap to 0.317 at T = 0.25. Distilling anything else repeats v26." -ForegroundColor Red
    Write-Host "Regenerate: scripts\gen_distill_batch.ps1 -Ckpt $expectedGenCkpt -Bank <fresh> -TotalRecords 5000 -Temperature $DistillTemperature" -ForegroundColor Red
    exit 1
}
Write-Host ("  provenance OK: ckpt {0}, temperature {1}, min_score_gap {2}, {3} record(s)." -f `
    (Split-Path $provCkpt -Leaf), $provData.temperature, $provGap, $provData.records) -ForegroundColor Cyan

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

# THE v27 delta. Masked cross-entropy toward the searched action distribution,
# sampled (with replacement) up to train_torch.DISTILL_MAX_ROWS = 4096 rows per
# minibatch. Coef 0.5, up from v26's 0.1: v26's diagnosis was not that the term
# was too weak to bite (it learned its shards at 0.71 agreement) but that what
# it bit into was un-generalizable. With decisive targets and a fresh batch per
# cycle, the term is worth leaning on -- the policy gradient still owns the
# update at 0.5.
$distill = @("--distill", $DistillDir, "--distill-coef", "0.5")
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

# No between-cycle gate is ENFORCED: the per-cycle gate (below) is a human
# read of two distill_diag runs, and the operator holds the decision to spend
# another night. Reads are post-run, human-read, vs the v24_s27
# --merge-duplicates baselines (reads table in v27-run-log.md).

# ── the cycle-START retention copy, made BEFORE any training ──
# --save is overwritten in place, so without this copy the "before" half of
# this cycle's own measurement is gone the moment iteration 5 checkpoints. It
# also becomes -PrevCkpt below, which makes Invoke-Stage's done/remaining
# arithmetic exactly "steps trained in THIS cycle" for every cycle uniformly
# (v26 could use the seed for that because it had one cycle).
#
# WRITE-ONCE. An existing cycle<N>.pt is the interrupted-cycle resume path:
# it is REUSED, never overwritten. Overwriting it with the partially-trained
# save file would silently replace the cycle's "before" with a "during", and
# every diag number downstream would be wrong with no trace.
$cycleSource = if ($Cycle -eq 1) { $SeedCkpt } else { $ckpt[29] }
if (Test-Path $cycleCkpt) {
    Write-Host "Cycle $Cycle start checkpoint already retained: $cycleCkpt (reusing; NOT overwriting)." -ForegroundColor Cyan
    # Lineage sanity: the retained start must not be AHEAD of the live save
    # file. If it is, this cycle<N>.pt belongs to some other lineage (a
    # hand-copy, a re-tagged run) and the whole cycle's arithmetic is built on
    # sand -- Invoke-Stage would compute a negative `done` and re-train the
    # full budget on top of work already done.
    if (Test-Path $ckpt[29]) {
        $retainedStep = Get-CkptStep $cycleCkpt
        $liveStep = Get-CkptStep $ckpt[29]
        if ($retainedStep -gt $liveStep) {
            Write-Host "$cycleCkpt is at global_step $retainedStep, AHEAD of $($ckpt[29]) at $liveStep." -ForegroundColor Red
            Write-Host "That is not this run's lineage. Refusing rather than guessing." -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "Retaining cycle $Cycle start checkpoint: $cycleSource -> $cycleCkpt" -ForegroundColor Cyan
    # Copy, never move/rename: $cycleSource is the v24_s27 SEED at cycle 1 and
    # that file is read-only to this script forever.
    Copy-Item -LiteralPath $cycleSource -Destination $cycleCkpt
}

# ── s29 cycle N: v24's rewards/geometry/foresight VERBATIM + search distillation ──
Invoke-Stage -Name "s29-cycle$Cycle-run-search-distill" -SaveCkpt $ckpt[29] -PrevCkpt $cycleCkpt `
    -Steps $CycleSteps -CriticWarmup $criticWarmup -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension-random", "0", "10", "--lr", "3e-4") + $runRewards + $longHorizon + $foresight + $distill)

# ── the per-cycle READ HOOK ──────────────────────────────────────────────────
# Two distill_diag runs, each scoring the cycle-START and cycle-END checkpoints
# (start first: it is distill_diag's REFERENCE, which defines what a FLIP
# record is) -- one against the batch this cycle trained on, one against the
# holdout exam gen_distill_batch.ps1 wrote beside it. The holdout is the whole
# point: on-shard improvement alone is what v26 already achieved while
# generalizing negatively.
$holdoutDir = "${DistillDir}_holdout"
$diagPy = "venv\Scripts\python.exe tools\distill_diag.py"
Write-Host ""
Write-Host ("=" * 78) -ForegroundColor Green
Write-Host "CYCLE $Cycle TRAINED. Read it before spending another night:" -ForegroundColor Green
Write-Host ""
Write-Host "  $diagPy $DistillDir ``"
Write-Host "      $cycleCkpt $($ckpt[29]) ``"
Write-Host "      --device cuda --json $DistillDir\diag_cycle$Cycle.json"
Write-Host ""
Write-Host "  $diagPy $holdoutDir ``"
Write-Host "      $cycleCkpt $($ckpt[29]) ``"
Write-Host "      --device cuda --json $holdoutDir\diag_cycle$Cycle.json"
if (-not (Test-Path $holdoutDir -PathType Container)) {
    Write-Host ""
    Write-Host "  NOTE: $holdoutDir does not exist. gen_distill_batch.ps1 writes it next to" -ForegroundColor Yellow
    Write-Host "  the batch; without it the gate below cannot be measured at all." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  GATE (pre-registered, v27-run-log.md). BOTH must hold:" -ForegroundColor Green
Write-Host "    * holdout dCE  >= 1/4 of the on-shard dCE   (start -> end)"
Write-Host "    * holdout agree_flip up by >= 0.05          (start -> end)"
Write-Host "  On-shard movement WITHOUT the holdout half is the v26 memorization signature"
Write-Host "  (on-shard dCE 0.766 / agree_flip 0.710 vs holdout dCE -0.065 / 0.133 < null)."
Write-Host "  Record both rows in docs/superpowers/plans/v27-run-log.md before continuing."
Write-Host ("=" * 78) -ForegroundColor Green

if ($Cycle -lt 3) {
    # ── the inter-cycle OPERATOR block ──
    # Deliberately not automated: harvest + generation is hours of GPU/CPU that
    # Perry schedules overnight, and host RAM caps gen_distill_batch's waves at
    # 3 workers. The script stops here so the next cycle is launched against a
    # batch generated from the checkpoint it will actually resume from -- which
    # the pre-flight above then re-proves mechanically.
    $next = $Cycle + 1
    # A NEW seed range per cycle so no two cycles harvest the same episodes.
    # The 08-27 v24_s27 bank used 910000-910299 (asc 10) and 920000-920099
    # (asc 0), so v27's windows start ABOVE both and stay 10000 apart: cycle 2
    # gets 930000/960000, cycle 3 gets 940000/970000. Do not "simplify" this to
    # 910000 + 10000*Cycle -- that lands cycle 2's asc-10 window exactly on the
    # 08-27 asc-0 seeds.
    $ascSeed = 930000 + 10000 * ($Cycle - 1)
    $asc0Seed = 960000 + 10000 * ($Cycle - 1)
    $bankStem = "runs\snapshots\v27_c${next}_bank"
    $nextDir = "runs\distill\v27_batch$next"
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor Yellow
    Write-Host "STOP. Cycle $next is OPERATOR work (overnight); this script does not automate it." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  (1) harvest a FRESH bank from the checkpoint cycle $next will resume from"
    Write-Host "      (the 08-27 recipe: 300 eps asc 10 + a 100-eps asc-0 act-2/3 top-up,"
    Write-Host "      sampling mode, NEW seed range). harvest.py OVERWRITES --out, so the"
    Write-Host "      top-up is a second file concatenated WITHOUT its schema header line:"
    Write-Host ""
    Write-Host "      venv\Scripts\python.exe harvest.py --episodes 300 --seed $ascSeed ``"
    Write-Host "          --checkpoint $($ckpt[29]) --device cuda --ascension 10 ``"
    Write-Host "          --out ${bankStem}_asc10.jsonl"
    Write-Host "      venv\Scripts\python.exe harvest.py --episodes 100 --seed $asc0Seed ``"
    Write-Host "          --checkpoint $($ckpt[29]) --device cuda --ascension 0 ``"
    Write-Host "          --out ${bankStem}_asc0.jsonl"
    Write-Host "      Copy-Item ${bankStem}_asc10.jsonl ${bankStem}.jsonl"
    Write-Host "      Get-Content ${bankStem}_asc0.jsonl | Select-Object -Skip 1 |"
    Write-Host "          Add-Content ${bankStem}.jsonl"
    Write-Host ""
    Write-Host "  (2) generate the batch (KEPT records; -MinScoreGap defaults to $DistillMinScoreGap):"
    Write-Host ""
    Write-Host "      .\scripts\gen_distill_batch.ps1 -Ckpt $($ckpt[29]) ``"
    Write-Host "          -Bank ${bankStem}.jsonl -OutDir $nextDir ``"
    Write-Host "          -TotalRecords 5000 -Temperature $DistillTemperature"
    Write-Host ""
    Write-Host "  (3) relaunch:"
    Write-Host ""
    Write-Host "      .\scripts\train_curriculum_v27.ps1 -Cycle $next -DistillDir $nextDir"
    Write-Host ""
    Write-Host "  Generate BEFORE relaunching and do not train anything into $($ckpt[29]) in"
    Write-Host "  between: the cycle-$next pre-flight refuses unless provenance.ckpt is that"
    Write-Host "  exact path, and the batch is only honest if the file has not moved since."
    Write-Host ("=" * 78) -ForegroundColor Yellow
    exit 0
}

foreach ($asc in 10, 0) {
    # runs/run_logs/ (gitignored) is where every CSV lives now -- the eval
    # sidecars as well as train_torch's per-iteration log (train_torch.csv_path).
    if (Test-Path (Join-Path $root "runs/run_logs/eval_${Tag}_s29_asc${asc}.episodes.csv")) {
        Write-Host "s29-eval-asc$asc already recorded - skipping." -ForegroundColor DarkGray
    } else {
        Invoke-Eval -Name "s29-eval-asc$asc" -Ckpt $ckpt[29] -Asc $asc -Episodes 150 `
            -Csv "runs/run_logs/eval_${Tag}_s29_asc$asc"
    }
}
Write-Host "v27 ExIt run complete (3 cycles, 14942208 steps). Reads: docs/superpowers/plans/v27-run-log.md (and re-run the Tier-B tools/eval_search.py measurement against s29)" -ForegroundColor Green
