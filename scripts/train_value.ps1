# Fit the value head. Head-only by default; -TrainEncoder for the escalation.
[CmdletBinding()]
param(
  [string]$Targets, [string]$Holdout, [string]$Out,
  [string]$Ckpt = "runs\sts2_run_torch_v24_s27.pt",
  [int]$Epochs = 10, [double]$Lr = 1e-3, [int]$Batch = 4096,
  [string]$Device = "cuda", [switch]$TrainEncoder, [switch]$Smoke
)
$ErrorActionPreference = "Stop"; $py = "venv\Scripts\python.exe"
if ($Smoke) { $Epochs = 2; $Batch = 32; $Device = "cpu" }
$enc = @(); if ($TrainEncoder) { $enc = @("--train-encoder") }
& $py -u tools\train_value.py --targets $Targets --holdout $Holdout --out $Out `
  --ckpt $Ckpt --epochs $Epochs --lr $Lr --batch $Batch --device $Device @enc
if ($LASTEXITCODE -ne 0) { throw "train_value exited $LASTEXITCODE" }
