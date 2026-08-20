param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
if (-not $env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME = "logpresso-dev" }
if (-not $env:LOGPRESSO_DATA_DIR) { $env:LOGPRESSO_DATA_DIR = ".docker-dev" }
$binding = & (Join-Path $PSScriptRoot "sync_lan_bind.ps1")
Write-Host "현재 LAN UI 주소: http://$($binding.Address):8501/"

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) {
    $dockerCommand.Source
} else {
    "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
}

if (-not (Test-Path $docker)) {
    throw "Docker CLI를 찾을 수 없습니다. Docker Desktop을 실행했는지 확인하세요."
}

& $docker rm -f "${env:COMPOSE_PROJECT_NAME}-caddy-1" 2>$null | Out-Null

if ($Build) {
    & $docker compose up -d --build
} else {
    & $docker compose up -d --no-build
    if ($LASTEXITCODE -ne 0) {
        throw "로컬 이미지가 없습니다. 네트워크 연결 후 scripts/start_dev.ps1 -Build를 실행하세요."
    }
}

& $docker compose ps
