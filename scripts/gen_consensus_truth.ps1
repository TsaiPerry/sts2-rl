# Generate R gold search runs that all walk the SAME decisions (--seed 0, so
# the collection pass and its recorded `f` are identical across runs) but
# differ only in rollout noise (--search-seed $k, an independent salt band per
# run), then grade a candidate critic's steps=0 run against the consensus.
# Reuses scripts\mcheck_run.ps1's worker invocation for each gold run.
[CmdletBinding()]
param(
  [string]$Ckpt = "runs\sts2_run_torch_v24_s27.pt",
  [string]$Bank, [string]$OutRoot = "runs\distill\v28_consensus",
  [int]$Decisions = 175, [int]$R = 3, [int]$GoldM = 64, [switch]$Smoke
)
$ErrorActionPreference = "Stop"; $py = "venv\Scripts\python.exe"
if ($Smoke) { $Decisions = 6; $R = 3; $GoldM = 16 }
$golds = @()
for ($k = 0; $k -lt $R; $k++) {
  $d = Join-Path $OutRoot ("gold$k")
  if (-not (Test-Path (Join-Path $d "provenance.json"))) {
    & $py -u tools\search_worker.py $Ckpt --bank $Bank --out $d `
      --decisions $Decisions --shard-size 256 --k 5 --m $GoldM --mass-cap 0.92 `
      --asc 10 --seed 0 --search-seed $k --gamma 0.999 --rollout-steps 120 --card-obs hybrid `
      --device cuda --temperature 0.25 --min-score-gap 0.0
    if ($LASTEXITCODE -ne 0) { throw "gold$k exited $LASTEXITCODE" }
  }
  $golds += "--gold"; $golds += $d
}
Write-Host "consensus truth built in $OutRoot ; grade a critic with:" -ForegroundColor Green
Write-Host "  $py tools\consensus_truth.py $($golds -join ' ') --est <crit_steps0_dir>"
