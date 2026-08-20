param([string]$EnvFile)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
if (-not $EnvFile) { $EnvFile = Join-Path $repo ".env" }
$route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric,InterfaceMetric | Select-Object -First 1
if (-not $route) { throw "기본 IPv4 경로를 찾지 못했습니다." }
$address = Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.AddressState -ne "Duplicate" } |
    Select-Object -First 1
if (-not $address) { throw "활성 LAN IPv4 주소를 찾지 못했습니다." }
$values = [ordered]@{}
if (Test-Path -LiteralPath $EnvFile) {
    foreach ($line in Get-Content -LiteralPath $EnvFile) {
        if ($line -match '^([^#=]+)=(.*)$') { $values[$matches[1].Trim()] = $matches[2] }
    }
}
$previous = $values["UI_BIND_ADDRESS"]
$values["API_BIND_ADDRESS"] = "127.0.0.1"
$values["UI_BIND_ADDRESS"] = $address.IPAddress
$content = $values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
Set-Content -LiteralPath $EnvFile -Value $content -Encoding utf8
[pscustomobject]@{ Address=$address.IPAddress; PrefixLength=$address.PrefixLength; InterfaceAlias=$address.InterfaceAlias; Changed=$previous -ne $address.IPAddress }
