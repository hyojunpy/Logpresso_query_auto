$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
if (-not (Test-Path $docker)) { $docker = (Get-Command docker).Source }
& $docker compose ps
& $docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read().decode())"
Write-Host "최근 API 로그:"
& $docker compose logs --tail 20 api
