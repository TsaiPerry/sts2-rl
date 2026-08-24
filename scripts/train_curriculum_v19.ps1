<#
v19 asc-0 stage: one stage on top of the v18 s21 policy, changing exactly ONE
variable -- the training ascension, 10 -> 0. Reward function is v18's lean set
VERBATIM (change two things and you can attribute neither).

  Stage  Env  Asc  Steps  Notes
  s22    run    0    15M  continue runs/sts2_run_torch_v18_s21.pt (--resume
                          handoff, same kind, NO warm start). Same rewards as
                          v18 s21: floor-by-act 1/1.5/2, win 12, upgrade 1.5 +
                          knee-cap, elite 2 / boss 3 / attempt 1, hp-potential
                          4.0, energy-waste 0.02. No potion terms, no
                          remove/relic, no injections, no potion-ent.
                          --critic-warmup 8: NOT because rewards changed (they
                          didn't) but because the RETURN SCALE does -- asc-0
                          episodes run ~10 floors deeper and win 4-8%, so
                          per-episode return is much larger and the s21 critic
                          is stale in the resume-after-env-change way.

Why asc-0 (2026-08-18 discussion): at asc-10 the win reward is nearly
unlearnable -- greedy wins are 0/150 across v14-v18, so the +12 only fires on
rare sampled training wins. At asc-0 (4-8% win) it fires ~10-20x more often,
and the training distribution finally contains acts 2-4 and their bosses at
volume instead of ending ~30% of episodes at the floor-16 wall. This is the
first generation trained on the distribution the win metric is read on.

Known structural caveat, accepted going in: the obs schema carries NO
ascension feature, so the policy cannot condition on difficulty -- whatever
style asc-0 teaches is applied blindly at asc-10. Some asc-10 floor sag is
the expected COST of this stage, not a surprise; the pre-registered tolerance
below is the read, not a mid-run gate.

Pre-registered reads (post-run, human-read, vs the v18 s21 evals -- concrete
bars pinned 2026-08-19 from eval_v18_s21_*):
  * asc-0 win: must beat 8% (v18 got 6.67% as TRANSFER from asc-10 training;
    v16's 8% ATH likewise; s22 is ON-distribution, so anything <=8% is a
    null result). The interesting number is how far past it goes.
  * asc-10 floor: tolerance = 10% below v18 s21's 23.73 -> bar is 21.4
    (note v18 raised this baseline by +3.5 floors -- the blind-policy cost
    is measured against the campaign's strongest checkpoint). Worse than
    21.4 = the cost exceeds the win-signal benefit -> the durable fix is an
    ascension obs feature (v4->v5 schema migration), not more asc-0 steps.
  * rest-upgrade share + potions/ep: should HOLD at v18's levels (asc-10
    0.429 / asc-0 0.486 share; 6.49 / 9.73 potions/ep). The reward terms
    paying them are unchanged; asc-0 is easier, so a modest style drift
    toward greed is possible -- a collapse is news.
  * boss conversion at floor >=45 (asc-0): v16 26% -> v17 14% -> v18 19%
    (10/52). On-distribution boss exposure should move it further up. This
    is the mechanism read behind the win number.
  * energy unspent: NOT a read here -- v18 showed the re-added 0.02 term
    failed to reproduce its v16 effect (0.268 vs 0.136); the term rides
    along uncredited and should not be interpreted from this run.

No rest mask, no potion mask, ever.

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v19.ps1                # real run; auto-evals s22
  .\train_curriculum_v19.ps1 -Smoke         # 65536 steps, scratch tag
  .\train_curriculum_v19.ps1 -Resume        # continue an interrupted run
#>
param(
    [long]$S22Steps = 15000000,
    [string]$Device = "cuda",
    [string]$Tag = "v19",
    [string]$SeedCkpt = "runs/sts2_run_torch_v18_s21.pt",
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
    $S22Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{ 22 = Join-Path $runs "sts2_run_torch_${Tag}_s22.pt" }

if ((Test-Path $ckpt[22]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[22]) already exists." -ForegroundColor Red
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}
if (-not (Test-Path (Join-Path $root $SeedCkpt))) {
    Write-Host "SeedCkpt '$SeedCkpt' not found - nothing to extend." -ForegroundColor Red
    Write-Host "(v19 seeds from the v18 s21 checkpoint - has the v18 run finished?)"
    exit 1
}
$schema = & $py -c "import sys, torch; print(torch.load(sys.argv[1], map_location='cpu', weights_only=False).get('obs_schema'))" (Join-Path $root $SeedCkpt)
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not read SeedCkpt schema (python exited $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}
if (($schema | Select-Object -Last 1).Trim() -ne "12") {
    Write-Host "SeedCkpt is not schema 12 - run tools\migrate_handrow_v14.py first." -ForegroundColor Red
    exit 1
}

$nEnvs = 64
$nSteps = 512
$batchSize = [long]$nEnvs * $nSteps
$geom = @("--arch", "entset", "--shared-encoder", "--device", $Device,
          "--n-envs", "$nEnvs", "--n-steps", "$nSteps", "--minibatches", "8")

# v18's lean reward set, byte-identical -- the ONLY stage variable vs v18 is
# --ascension. The v11 elite-diving arithmetic note still applies: below
# ~12.5% HP the +1 attempt pay exceeds the remaining death penalty -- keep
# watching elites_fought minus elites in the s22 evals (asc-0 elites are
# weaker, so diving is cheaper here than it ever was at asc-10).
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "1.5", "--reward-elite", "2",
                "--reward-boss", "3",
                "--reward-elite-attempt", "1",
                "--hp-potential-scale", "4.0",
                "--rest-heal-shaping-knee-cap",
                "--energy-waste-penalty", "0.02")

# Long-horizon levers (spec 2026-08-13-aux-hp-head-gae-lambda-design).
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
# -WarmStart marks a kind-switch handoff (combat<->run): UNUSED in v19 -- an
# ascension change is NOT a kind switch (check_ascension prints and proceeds;
# a warm start would re-drop the run heads v11 rebuilt). Kept verbatim so the
# helper stays byte-identical with the v10..v18 scripts.
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
               "--ascension", "$Asc", "--csv", $Csv)
    $code = Invoke-Phase -Name $Name -PhaseArgs $args_
    if ($code -ne 0) { Write-Host "$Name exited $code (continuing)" -ForegroundColor Yellow }
}

# No between-stage gate: single-stage plan. Reads are post-run, human-read,
# vs the v18 s21 evals (pre-registered list in the header comment). The
# asc-10 eval matters MORE than usual here -- it prices the blind-policy cost.

# ── s22: same lean rewards, training distribution moved to ascension 0 ─────
Invoke-Stage -Name "s22-run-asc0-lean" -SaveCkpt $ckpt[22] -PrevCkpt $SeedCkpt `
    -Steps $S22Steps -CriticWarmup 8 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "0", "--lr", "3e-4") + $runRewards + $longHorizon)

if (Test-Path (Join-Path $root "runs/eval_${Tag}_s22_asc10.episodes.csv")) {
    Write-Host "s22-eval-asc10 already recorded - skipping." -ForegroundColor DarkGray
} else {
    Invoke-Eval -Name "s22-eval-asc10" -Ckpt $ckpt[22] -Asc 10 -Episodes 150 `
        -Csv "runs/eval_${Tag}_s22_asc10"
}
if (Test-Path (Join-Path $root "runs/eval_${Tag}_s22_asc0.episodes.csv")) {
    Write-Host "s22-eval-asc0 already recorded - skipping." -ForegroundColor DarkGray
} else {
    Invoke-Eval -Name "s22-eval-asc0" -Ckpt $ckpt[22] -Asc 0 -Episodes 150 `
        -Csv "runs/eval_${Tag}_s22_asc0"
}

Write-Host "v19 asc-0 run complete. Reads: docs/superpowers/plans/v19-run-log.md" -ForegroundColor Green
