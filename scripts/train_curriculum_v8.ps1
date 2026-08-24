<#
v8 curriculum: HP economy + potion timing + early-game credit, then the
ascension ramp. (Plan: docs/superpowers/plans/2026-08-10-v8-hp-economy-curriculum.md.
Supersedes train_curriculum_v7.ps1's stage table; requires the plan's
Phase B' env knobs: --hp-potential-scale, --potion-potential-scale,
--reward-relic, --rest-heal-mask-above.)

  Stage  Env               Asc  Steps  deck-rand  rest-mask  Extra
  s0     combat(snapshots)   0     3M          -          -  lr 6e-4
  s1     run                 0     4M       0.50       0.80  lr 6e-4, warmup 40
  s2     run --acts 1        4     3M       0.50       0.80  lr 6e-4, warmup 20
  s3     run                 4     5M       0.50       0.80  lr 6e-4, warmup 15
  s4     run                 7     5M       0.25       0.80  lr 6e-4, warmup 15
  s5     combat(snapshots)  10     2M          -          -  lr 3e-4
  s6     run                10     8M       0.25       0.85  lr 3e-4, warmup 15
  s7     run                10    10M       0.00        OFF  lr 3e-4, ent 0.01->0.004, warmup 10

Design notes (keep in sync with the plan):
- s0/s5 drill combat efficiency on realistic mid-run decks (R11 snapshot
  start states); the combat env's native HP-delta reward prices every
  unnecessary point of damage. This attacks the ROOT CAUSE of rest-heal
  dominance: the policy heals everywhere because it bleeds everywhere.
- --critic-warmup at EVERY env-kind or reward-scale boundary is load-bearing:
  combat returns are ~+/-1 while run returns are ~80, and one bad epoch on a
  mis-scaled critic costs more than the warmup ever does.
- --hp-potential-scale is CONCAVE potential shaping (knee 0.35): top-half HP
  is cheap currency (-20% of the bar costs ~0.37, so elite-greed at +0.75 is
  net-positive and PAID), low HP is precious (~4x the marginal cost), heals
  earn back exactly the potential they restore (rest-heal at 20% HP ~ +1.5,
  at 85% ~ +0.3 < the +0.5 upgrade term), and the act-entry Ancient heal
  (full missing HP; x0.8 at asc 2+) REFUNDS the act's HP spending — spend
  health on elites, keep just enough to reach the next Ancient, collect the
  refund. Death forfeits it. Potential-based, so the optimal policy is
  unchanged; only the signal densifies.
- --rest-heal-mask-above 0.8 is a TRAINING constraint (forbids near-wasted
  heals so upgrade data actually gets generated); it anneals OFF in s7 so
  the shipped policy is unconstrained, and eval NEVER sets it.
- Potion ledger (Perry's design): --potion-potential-scale 0.3 pays +0.3
  when a potion enters the belt and -0.3 when it leaves (use, sell, or
  full-belt discard), with NO terminal payback — an unused potion keeps its
  +0.3 forever, so k is the minimum effect a drink must deliver to be worth
  throwing the potion away. The bar interacts with the concave HP shaping to
  define "key moment" endogenously: a ~10%-max-HP save prices ~0.8 below the
  knee (drink) vs ~0.18 at high HP in a chump fight (hold), and a run-saving
  drink clears any bar. No room labels, no potion masks, no use terms.
  Watch both edges via ep_potions_used_{elite,boss,normal}, ep_potion_use_hp
  and ep_potions_expired: chugging persists -> raise k to 0.5; never-drink
  hoarding -> halve k to 0.15 (or death-only -k/2 expiry).
- s2 (--acts 1) makes the act-1 boss the episode terminal so draft/pathing
  credit lands ~15 floors away instead of ~45; asc 4 for elite-dense maps.
- The shipping artifact is s7 (env_kind "run"). Combat checkpoints are means.
- Interruptions resume at ITERATION granularity, not stage granularity: each
  stage credits the steps its own checkpoint already carries (global_step minus
  the handoff point's) and asks train_torch only for the remainder, skipping
  finished stages outright. Re-launching with -Resume therefore costs at most
  the last --save-every (10) iterations, not a whole re-run of the stage.

  .venv\Scripts\python.exe -m pytest -q      # green before launching, please
  .\train_curriculum_v8.ps1                  # real run
  .\train_curriculum_v8.ps1 -Smoke           # dry-run gate (plan Task 6 step 2)
#>
param(
    [long]$S0Steps = 3000000,
    [long]$S1Steps = 4000000,
    [long]$S2Steps = 3000000,
    [long]$S3Steps = 5000000,
    [long]$S4Steps = 5000000,
    [long]$S5Steps = 2000000,
    [long]$S6Steps = 8000000,
    [long]$S7Steps = 10000000,
    [string]$Device = "cuda",
    [string]$Tag = "v8",
    # Stage 0 seeds from this checkpoint (the v6 run-scale policy). --resume
    # only READS it; every write goes to this script's own --save paths.
    [string]$SeedCkpt = "runs/sts2_run_torch_v6.pt",
    # R11 run-state snapshot corpus for the combat stages (plan Task 6 step 1).
    # If the file is missing the combat stages are SKIPPED with a warning and
    # the run stages chain directly.
    [string]$SnapshotPath = "runs/v8_start_snapshots.jsonl",
    # Required to continue an interrupted run: without it, an existing stage-0
    # checkpoint is treated as an accident rather than a resume point. With it,
    # every stage picks up from its last saved iteration (see Invoke-Stage).
    [switch]$Resume,
    # Dry-run gate: 65536 steps per stage against a scratch tag.
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent  # scripts/ sits one level below repo root
$runs = Join-Path $root "runs"
if (-not (Test-Path $runs)) { New-Item -ItemType Directory $runs | Out-Null }
$py = Join-Path $root "venv\Scripts\python.exe"

if ($Smoke) {
    $Tag = "${Tag}smoke"
    $S0Steps = 65536; $S1Steps = 65536; $S2Steps = 65536; $S3Steps = 65536
    $S4Steps = 65536; $S5Steps = 65536; $S6Steps = 65536; $S7Steps = 65536
    Write-Host "SMOKE MODE: tag=$Tag, 65536 steps/stage. Delete runs/*${Tag}* afterwards." -ForegroundColor Yellow
}

$ckpt = @{}
foreach ($n in 0..7) { $ckpt[$n] = Join-Path $runs "sts2_run_torch_${Tag}_s$n.pt" }

if ((Test-Path $ckpt[0]) -and -not $Resume -and -not $Smoke) {
    Write-Host "$($ckpt[0]) already exists." -ForegroundColor Red
    Write-Host "Training it further would continue that model, not start a fresh v8 run."
    Write-Host "Pass -Resume to continue it, or -Tag <name> for a new checkpoint set."
    exit 1
}

$haveSnapshots = Test-Path (Join-Path $root $SnapshotPath)
if (-not $haveSnapshots) {
    Write-Host "SnapshotPath '$SnapshotPath' not found: SKIPPING combat stages s0/s5." -ForegroundColor Yellow
    Write-Host "Generate the corpus first (plan Task 6 step 1) for the full curriculum."
}

# Geometry/arch: explicit on every stage (stages resume across env kinds and
# ascension bumps; the stamped geometry must not drift).
$nEnvs = 64
$nSteps = 512
$batchSize = [long]$nEnvs * $nSteps      # steps per iteration (train_torch n_iters = timesteps // batch)
$geom = @("--arch", "entset", "--shared-encoder", "--device", $Device,
          "--n-envs", "$nEnvs", "--n-steps", "$nSteps", "--minibatches", "8")

# v8 run-stage rewards: v7 spec (act-scaled floors, win 12, upgrade/elite 0.5,
# remove 0.25) + relic 0.25 + concave HP-potential shaping + potion ledger.
# These flags are run/column-only; combat stages must NOT receive them.
$runRewards = @("--floor-rewards", "1.0", "1.5", "2.0", "--reward-win", "12",
                "--reward-upgrade", "0.5", "--reward-elite", "0.5",
                "--reward-remove", "0.25", "--reward-relic", "0.25",
                "--hp-potential-scale", "4.0",
                "--potion-potential-scale", "0.3")

# Rest-heal curriculum mask: on for s1-s4 and s6, OFF in s7 so the shipped
# policy is unconstrained. Eval never sets it. Potion actions are NEVER
# masked (the ledger prices them instead).
$masks = @("--rest-heal-mask-above", "0.80")
$masksS6 = @("--rest-heal-mask-above", "0.85")

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
# -WarmStart marks a kind-switch handoff (combat<->run): the four boundaries
# named in the T6b brief (seed->s0, s0->s1, s4->s5, s5->s6) use
# --warm-start $PrevCkpt instead of --resume $PrevCkpt, since $PrevCkpt was
# trained on the OTHER env kind. Every other handoff (s1->s2->s3->s4, s6->s7)
# is same-kind and keeps plain --resume. It also zeroes the step baseline,
# because train_torch restarts global_step on a warm start.
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

# $prevKind tracks which env kind $prev was actually trained on, so each
# Invoke-Stage call below can pass -WarmStart exactly when that's true
# (cross-kind) rather than by a fixed stage number -- e.g. s1 hands off from
# combat (s0) when the snapshot corpus is present, but from the run-scale
# $SeedCkpt directly (same kind as s1 itself) when s0 was skipped.
$prev = $SeedCkpt
$prevKind = "run"          # $SeedCkpt (runs/sts2_run_torch_v6.pt) is run-scale

# ── s0: combat drill, asc 0, snapshot start states ────────────────────────
if ($haveSnapshots) {
    Invoke-Stage -Name "s0-combat-asc0" -SaveCkpt $ckpt[0] -PrevCkpt $prev -Steps $S0Steps -StageArgs @(
        "--env", "combat", "--ascension", "0",
        "--start-snapshots", $SnapshotPath, "--lr", "6e-4") -WarmStart:($prevKind -ne "combat")
    $prev = $ckpt[0]
    $prevKind = "combat"
}

# ── s1: run asc 0, reward re-baseline + rest mask on ──────────────────────
Invoke-Stage -Name "s1-run-asc0" -SaveCkpt $ckpt[1] -PrevCkpt $prev -Steps $S1Steps -CriticWarmup 40 -StageArgs (@(
    "--env", "run", "--ascension", "0",
    "--deck-random-prob", "0.50",
    "--lr", "6e-4") + $masks + $runRewards) -WarmStart:($prevKind -ne "run")
$prevKind = "run"

# ── s2: act-1 only, asc 4 — early-game credit assignment ──────────────────
Invoke-Stage -Name "s2-act1-asc4" -SaveCkpt $ckpt[2] -PrevCkpt $ckpt[1] -Steps $S2Steps -CriticWarmup 20 -StageArgs (@(
    "--env", "run", "--acts", "overgrowth", "--ascension", "4",
    "--deck-random-prob", "0.50",
    "--lr", "6e-4") + $masks + $runRewards)

# ── s3: full runs, asc 4 ──────────────────────────────────────────────────
Invoke-Stage -Name "s3-run-asc4" -SaveCkpt $ckpt[3] -PrevCkpt $ckpt[2] -Steps $S3Steps -CriticWarmup 15 -StageArgs (@(
    "--env", "run", "--ascension", "4",
    "--deck-random-prob", "0.50",
    "--lr", "6e-4") + $masks + $runRewards)

# ── s4: asc 7, + inflation/scarcity ───────────────────────────────────────
Invoke-Stage -Name "s4-run-asc7" -SaveCkpt $ckpt[4] -PrevCkpt $ckpt[3] -Steps $S4Steps -CriticWarmup 15 -StageArgs (@(
    "--env", "run", "--ascension", "7",
    "--deck-random-prob", "0.25",
    "--lr", "6e-4") + $masks + $runRewards)

$prev = $ckpt[4]
$prevKind = "run"

# ── s5: combat re-drill vs tough/deadly enemies, asc 10 ───────────────────
if ($haveSnapshots) {
    Invoke-Stage -Name "s5-combat-asc10" -SaveCkpt $ckpt[5] -PrevCkpt $prev -Steps $S5Steps -StageArgs @(
        "--env", "combat", "--ascension", "10",
        "--start-snapshots", $SnapshotPath, "--lr", "3e-4") -WarmStart:($prevKind -ne "combat")
    $prev = $ckpt[5]
    $prevKind = "combat"
}

# ── s6: asc 10, + tough/deadly, double boss ───────────────────────────────
Invoke-Stage -Name "s6-run-asc10" -SaveCkpt $ckpt[6] -PrevCkpt $prev -Steps $S6Steps -CriticWarmup 15 -StageArgs (@(
    "--env", "run", "--ascension", "10",
    "--deck-random-prob", "0.25",
    "--lr", "3e-4") + $masksS6 + $runRewards) -WarmStart:($prevKind -ne "run")
$prevKind = "run"

# ── s7: asc 10 polish — mask OFF, on-policy decks, entropy anneal ─────────
Invoke-Stage -Name "s7-run-asc10-polish" -SaveCkpt $ckpt[7] -PrevCkpt $ckpt[6] -Steps $S7Steps `
    -CriticWarmup 10 -EntCoef 0.01 -EntCoefFinal 0.004 -StageArgs (@(
    "--env", "run", "--ascension", "10",
    "--deck-random-prob", "0.00",
    "--lr", "3e-4") + $runRewards)

Write-Host "[$(Get-Date -Format s)] v8 curriculum complete: $($ckpt[7])"
exit 0
