param([Parameter(Mandatory=$true)][string]$Archive, [switch]$ConfirmRestore)
$ErrorActionPreference = "Stop"
if (-not $ConfirmRestore) { throw "복원은 기존 데이터를 덮어쓸 수 있습니다. -ConfirmRestore를 지정하세요." }
$repo = Split-Path $PSScriptRoot -Parent
$target = Join-Path $repo ".docker-dev"
if (Test-Path $target) { throw "안전을 위해 기존 $target 을 별도 위치로 옮긴 뒤 다시 실행하세요." }
Expand-Archive -LiteralPath $Archive -DestinationPath $repo
Write-Host "복원 완료. scripts/start_dev.ps1 로 서비스를 시작하세요."
