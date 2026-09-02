# Harvest MC value-regression targets. Perry launches the full runs (train +
# holdout seed ranges, disjoint). -Smoke does 1 CPU episode.
[CmdletBinding()]
param(
  [string]$Ckpt = "runs\sts2_run_torch_v24_s27.pt",
  [int]$Episodes = 500, [int]$Seed, [string]$Out,
  [double]$Gamma = 0.999, [int]$Ascension = 10,
  [string]$Device = "cuda", [switch]$Smoke
)
$ErrorActionPreference = "Stop"; $py = "venv\Scripts\python.exe"
if ($Smoke) { $Episodes = 1; $Device = "cpu" }
& $py -u tools\harvest_values.py --episodes $Episodes --seed $Seed --out $Out `
  --gamma $Gamma --ascension $Ascension --checkpoint $Ckpt --device $Device --shard-size 4096
if ($LASTEXITCODE -ne 0) { throw "harvest_values exited $LASTEXITCODE" }
