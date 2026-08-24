<#
v17 bare-bones settle run: one stage on top of the v16 s19 policy, with
EVERY shaped reward term removed (spec
docs/superpowers/specs/2026-08-18-v17-bare-bones-settle-design.md).

  Stage  Env  Asc  Steps  Notes
  s20    run   10    15M  continue runs/sts2_run_torch_v16_s19.pt (--resume
                          handoff, same kind, NO warm start); rewards are the
                          env CONSTRUCTOR DEFAULTS only -- flat +1/floor
                          (--floor-rewards omitted on purpose; no flat flag
                          exists) and --reward-win 3 (passed explicitly,
                          self-documenting). No upgrade/elite/boss/attempt/
                          remove/relic terms, no HP potential or knee-cap, no
                          potion terms, no energy penalty, no potion-ent, no
                          starter/midrun inject. Trainer machinery kept:
                          --gae-lambda 0.98, --aux-hp-coef 0.25, ent 0.01,
                          lr 3e-4. --critic-warmup 8: reward function changed.
                          15M UNINTERRUPTED (Perry): no mid-run gates, a decay
                          is a RESULT -- nothing aborts on metrics.

Defaults audit (2026-08-18, run before this script was written): omitting a
reward flag == the env constructor default for every run-scale knob
(EnvSpec fields default off/None; build_env forwards only when set).
--win-hp-bonus argparse-defaults to 1.0 but is deliberately never routed to
run-scale envs (combat only) -- omission is safe.

Training-CSV notes, recorded in advance: potion_ent reads NaN (coef 0 --
expected, not a bug); ep_ret is NOT comparable to v16's curve (different
reward function, no injection tax). With bare rewards and no injects,
training ep_ret ~= eval floor + 3*win for the first time since v14.

No rest mask, no potion mask, ever.

  .venv\Scripts\python.exe -m pytest -q     # green before launching
  .\train_curriculum_v17.ps1                # real run; auto-evals s20
  .\train_curriculum_v17.ps1 -Smoke         # 65536 steps, scratch tag
  .\train_curriculum_v17.ps1 -Resume        # continue an interrupted run
#>
param(
    [long]$S20Steps = 15000000,
    [string]$Device = "cuda",
    [string]$Tag = "v17",
    [string]$SeedCkpt = "runs/sts2_run_torch_v16_s19.pt",
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
    $S20Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{ 20 = Join-Path $runs "sts2_run_torch_${Tag}_s20.pt" }

if ((Test-Path $ckpt[20]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[20]) already exists." -ForegroundColor Red
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}
if (-not (Test-Path (Join-Path $root $SeedCkpt))) {
    Write-Host "SeedCkpt '$SeedCkpt' not found - nothing to extend." -ForegroundColor Red
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

# THE POINT OF v17: there is no $runRewards block. The only reward flag
# passed anywhere in this script is --reward-win 3 (== the constructor
# default, explicit for self-documentation). Long-horizon trainer levers are
# kept -- they are learning machinery, not reward (spec decisions table).
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
# -WarmStart marks a kind-switch handoff (combat<->run): UNUSED in v17 -- the
# whole point of this script is that there is no kind switch (a warm start
# here would re-drop the run heads v11 rebuilt). Kept verbatim so the helper
# stays byte-identical with the v10/v11/v14/v15/v16 scripts.
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

# No between-stage gate, no mid-run gate of any kind: 15M uninterrupted
# (Perry, spec decisions table). Reads are post-run, human-read, against the
# CORRECTED (potfix) v16 baselines -- a decay is a RESULT, not a forfeit.

# ── s20: bare-bones settle — constructor-default rewards, bare asc-10 ──────
Invoke-Stage -Name "s20-run-asc10-bare" -SaveCkpt $ckpt[20] -PrevCkpt $SeedCkpt `
    -Steps $S20Steps -CriticWarmup 8 -EntCoef 0.01 -StageArgs (@(
    "--env", "run", "--ascension", "10", "--lr", "3e-4",
    "--reward-win", "3") + $longHorizon)

if (Test-Path (Join-Path $root "runs/eval_${Tag}_s20_asc10.episodes.csv")) {
    Write-Host "s20-eval-asc10 already recorded - skipping." -ForegroundColor DarkGray
} else {
    Invoke-Eval -Name "s20-eval-asc10" -Ckpt $ckpt[20] -Asc 10 -Episodes 150 `
        -Csv "runs/eval_${Tag}_s20_asc10"
}
if (Test-Path (Join-Path $root "runs/eval_${Tag}_s20_asc0.episodes.csv")) {
    Write-Host "s20-eval-asc0 already recorded - skipping." -ForegroundColor DarkGray
} else {
    Invoke-Eval -Name "s20-eval-asc0" -Ckpt $ckpt[20] -Asc 0 -Episodes 150 `
        -Csv "runs/eval_${Tag}_s20_asc0"
}

Write-Host "v17 bare-bones settle run complete. Decay table: docs/superpowers/plans/v17-run-log.md" -ForegroundColor Green
