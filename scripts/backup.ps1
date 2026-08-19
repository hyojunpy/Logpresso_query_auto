param([string]$Destination, [int]$RetentionDays = 14, [int]$LogRetentionDays = 30)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
if (-not $Destination) { $Destination = Join-Path $repo "backups" }
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = Join-Path $Destination "logpresso-data-$stamp.zip"
$data = Join-Path $repo ".docker-dev"
if (-not (Test-Path $data)) { $data = Join-Path $repo "data" }
if (-not (Test-Path $data)) { throw "백업할 데이터 디렉터리가 없습니다." }
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
if (-not (Test-Path $docker)) { $docker = (Get-Command docker).Source }
$env:COMPOSE_PROJECT_NAME = "logpresso-dev"
$env:LOGPRESSO_DATA_DIR = ".docker-dev"
Set-Location $repo
& $docker compose stop | Out-Host
try {
    Compress-Archive -LiteralPath $data -DestinationPath $archive -CompressionLevel Optimal
} finally {
    & $docker compose start | Out-Host
}
Get-FileHash -Algorithm SHA256 $archive | Format-List
Get-ChildItem -LiteralPath $Destination -Filter "logpresso-data-*.zip" -File |
    Where-Object LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) | Remove-Item -Force
$logDir = Join-Path $data "logs"
if (Test-Path $logDir) {
    Get-ChildItem -LiteralPath $logDir -File |
        Where-Object LastWriteTime -lt (Get-Date).AddDays(-$LogRetentionDays) | Remove-Item -Force
}
Write-Host "백업 완료: $archive"
