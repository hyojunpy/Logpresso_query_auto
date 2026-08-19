param([switch]$DisableFirewall)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $repo ".env"
$route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
$address = Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1
if (-not $address) { throw "활성 LAN IPv4 주소를 찾지 못했습니다." }
$ip = $address.IPAddress
$prefix = $address.PrefixLength

$values = @{}
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^([^#=]+)=(.*)$') { $values[$matches[1].Trim()] = $matches[2] }
    }
}
$values["API_BIND_ADDRESS"] = "127.0.0.1"
$values["UI_BIND_ADDRESS"] = $ip
$content = $values.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }
Set-Content -LiteralPath $envFile -Value $content -Encoding utf8

$rule = "Logpresso Query UI (Private LAN)"
$remote = "$ip/$prefix"
if ($DisableFirewall) {
    Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
} else {
    Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Allow -Protocol TCP `
        -LocalAddress $ip -LocalPort 8501 -RemoteAddress $remote | Out-Null
}
Write-Host "LAN UI: http://${ip}:8501/"
Write-Host "설정을 적용하려면 scripts/start_dev.ps1 를 실행하세요."
