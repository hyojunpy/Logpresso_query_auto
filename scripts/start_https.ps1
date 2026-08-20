param([switch]$Build)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$env:COMPOSE_PROJECT_NAME = "logpresso-dev"
$env:LOGPRESSO_DATA_DIR = ".docker-dev"
$binding = & (Join-Path $PSScriptRoot "sync_lan_bind.ps1")
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
if (-not (Test-Path $docker)) { $docker = (Get-Command docker).Source }
$bindAddress = $binding.Address
$args = @("compose", "-f", "docker-compose.yml", "-f", "docker-compose.https.yml", "up", "-d")
if ($Build) { $args += "--build" }
& $docker @args
if ($LASTEXITCODE -ne 0) { throw "HTTPS 서비스 시작에 실패했습니다." }
$certDir = Join-Path $repo ".docker-dev\certificates"
New-Item -ItemType Directory -Path $certDir -Force | Out-Null
& $docker compose -f docker-compose.yml -f docker-compose.https.yml cp `
    caddy:/data/caddy/pki/authorities/local/root.crt "$certDir\logpresso-local-ca.crt"
Write-Host "HTTPS UI: https://${bindAddress}:9443/"
Write-Host "CA 인증서: $certDir\logpresso-local-ca.crt (신뢰 저장소 설치는 배포 문서를 확인하세요.)"
