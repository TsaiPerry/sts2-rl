# Unattended obs-v4 rebuild: column curriculum -> run env, ~11h.
#
# Both existing v4 checkpoints carry the migration's zero-spliced map grid,
# which collapsed training twice. This rebuilds from scratch so the grid is
# live from step 0, and gates the handoff on that actually being true.
#
#   powershell -ExecutionPolicy Bypass -File .\train_v4_pipeline.ps1
Set-Location $PSScriptRoot

$col = "runs/sts2_column_v4.pt"
$run = "runs/sts2_run_v4.pt"
$log = "runs/pipeline_v4.log"

function Say($msg) {
    $line = "[{0}] === {1} ===" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

Say "PHASE 1/2  column curriculum, fresh on v4 (~3h, target ep_ret ~14)"
py train_torch.py --env column --arch entity --device cuda `
    --n-envs 32 --n-steps 512 --timesteps 14000000 `
    --save $col --fresh | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    Say "PHASE 1 FAILED (exit $LASTEXITCODE) - stopping before phase 2"
    exit 1
}

# Hard gate. If the grid is the zero-splice, phase 2 spends 8 hours
# reproducing the exact bug this rebuild exists to escape.
Say "GATE  map-grid must be live before the handoff"
py check_grid_live.py $col | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    Say "GATE FAILED - refusing to start phase 2"
    exit 1
}

Say "PHASE 2/2  run env from the column checkpoint (~8h, target ep_ret 20+)"
py train_torch.py --env run --arch entity --device cuda `
    --n-envs 32 --n-steps 512 --timesteps 18000000 `
    --resume $col --save $run | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    Say "PHASE 2 FAILED (exit $LASTEXITCODE)"
    exit 1
}

Say "DONE  final checkpoint $run"
