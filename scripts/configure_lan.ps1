param([switch]$FirewallOnly, [switch]$DisableFirewall)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
if (-not $FirewallOnly) {
    $binding = & (Join-Path $PSScriptRoot "sync_lan_bind.ps1")
    Write-Host "LAN UI: http://$($binding.Address):8501/"
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $switches = if ($DisableFirewall) { "-FirewallOnly -DisableFirewall" } else { "-FirewallOnly" }
    $process = Start-Process powershell.exe -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" $switches" -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "관리자 방화벽 설정에 실패했습니다." }
    exit
}
$rule = "Logpresso Query UI (Private LAN)"
Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
if (-not $DisableFirewall) {
    New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort 8501,9443 -RemoteAddress LocalSubnet | Out-Null
    Write-Host "방화벽에서 현재 로컬 서브넷의 TCP 8501, 9443을 허용했습니다."
}
