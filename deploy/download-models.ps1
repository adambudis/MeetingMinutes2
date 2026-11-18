<#
.SYNOPSIS
  Download the NeMo speech-to-text models into .\models (online setup phase).
  Partial downloads are resumed when the script is run again.
.EXAMPLE
  .\deploy\download-models.ps1
  .\deploy\download-models.ps1 -Only canary
#>
param([ValidateSet('all', 'canary', 'parakeet')][string]$Only = 'all')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$models = Join-Path $root 'models'
New-Item -ItemType Directory -Force -Path $models | Out-Null

function Get-Model([string]$Repo, [string]$File) {
    $target = Join-Path $models $File
    if (Test-Path $target) { Write-Host "==> $File already present"; return }
    Write-Host "==> downloading $File"
    & curl.exe -fL --retry 5 -C - -o "$target.part" "https://huggingface.co/$Repo/resolve/main/$File"
    if ($LASTEXITCODE -ne 0) { throw "download of $File failed (exit code $LASTEXITCODE)" }
    Move-Item "$target.part" $target
}

if ($Only -in 'all', 'canary') { Get-Model 'nvidia/canary-1b-v2' 'canary-1b-v2.nemo' }
if ($Only -in 'all', 'parakeet') { Get-Model 'nvidia/parakeet-tdt-0.6b-v3' 'parakeet-tdt-0.6b-v3.nemo' }

if (-not (Test-Path (Join-Path $models 'pyannote\hub'))) {
    Write-Warning 'models\pyannote is missing - copy MeetingMinutes.Client\python\Models\pyannote from the WPF project'
}
Get-ChildItem $models | Format-Table Name, @{ n = 'Size (MB)'; e = { [math]::Round($_.Length / 1MB) } }
