<#
.SYNOPSIS
  Build all images for the server's CPU architecture and pack them into an offline bundle
  (run on a machine with internet; copy the resulting folder to the server).
.EXAMPLE
  .\deploy\build-bundle.ps1 -Platform linux/arm64     # DGX Spark / Grace
  .\deploy\build-bundle.ps1 -Platform linux/amd64     # x86 server
.NOTES
  Cross-building arm64 on an x86 PC works (Docker Desktop ships QEMU emulation) but is slow.
#>
param(
    [ValidateSet('linux/amd64', 'linux/arm64')][string]$Platform = 'linux/amd64',
    [string]$Tag = (Get-Date -Format 'yyyyMMdd-HHmm'),
    [string]$OllamaVersion = '0.40.16',
    [ValidateSet('cu130', 'cu128')][string]$TorchCuda = 'cu130'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$out = Join-Path $root "bundle\meetingminutes-$Tag"
New-Item -ItemType Directory -Force -Path (Join-Path $out 'deploy'), (Join-Path $out 'models') | Out-Null

function Invoke-Native([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker $($Arguments -join ' ') failed (exit code $LASTEXITCODE)" }
}

Write-Host "==> building images for $Platform (tag $Tag, $TorchCuda)"
$env:DOCKER_DEFAULT_PLATFORM = $Platform
$env:TAG = $Tag
$env:TORCH_CUDA = $TorchCuda
try {
    Invoke-Native @('compose', 'build', 'backend', 'frontend')
} finally {
    Remove-Item Env:DOCKER_DEFAULT_PLATFORM, Env:TAG, Env:TORCH_CUDA -ErrorAction SilentlyContinue
}
Invoke-Native @('pull', '--platform', $Platform, "ollama/ollama:$OllamaVersion")

$images = @("meetingminutes-backend:$Tag", "meetingminutes-frontend:$Tag", "ollama/ollama:$OllamaVersion")
Write-Host "==> saving $($images -join ', ')"
Invoke-Native (@('save', '--platform', $Platform, '-o', (Join-Path $out 'images.tar')) + $images)

Copy-Item docker-compose.yml, docker-compose.cpu.yml, .env.example, README.md -Destination $out
Copy-Item deploy\install-bundle.sh, deploy\pull-llm-models.sh -Destination (Join-Path $out 'deploy')
Copy-Item models\README.md -Destination (Join-Path $out 'models')
# LF line endings + no BOM: the Linux install script sources this file.
[IO.File]::WriteAllText((Join-Path $out 'bundle.env'), "TAG=$Tag`nOLLAMA_VERSION=$OllamaVersion`nPLATFORM=$Platform`n")

$size = [math]::Round(((Get-ChildItem $out -Recurse | Measure-Object Length -Sum).Sum) / 1GB, 1)
Write-Host "==> bundle ready: $out ($size GB)"
Write-Host '    copy it to the server (e.g. scp -r) and run: sudo bash <bundle>/deploy/install-bundle.sh /opt/meetingminutes'
