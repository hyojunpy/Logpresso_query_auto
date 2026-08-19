param([int]$TimeoutSeconds = 10)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $repo ".env"
$values = @{}
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^([^#=]+)=(.*)$') { $values[$matches[1].Trim()] = $matches[2].Trim("'", '"') }
    }
}
$failures = [Collections.Generic.List[string]]::new()
function Test-Endpoint([string]$Uri) {
    foreach ($attempt in 1..3) {
        try { Invoke-RestMethod $Uri -TimeoutSec $TimeoutSeconds | Out-Null; return $true }
        catch { if ($attempt -lt 3) { Start-Sleep -Seconds 3 } }
    }
    return $false
}
if (-not (Test-Endpoint "http://127.0.0.1:8000/api/v1/health")) { $failures.Add("API health check failed") }
if (-not (Test-Endpoint "http://127.0.0.1:11434/api/tags")) { $failures.Add("Ollama connection failed") }
if (-not $failures.Count) { Write-Host "All services are healthy."; exit 0 }
$message = "Logpresso Query Assistant: " + ($failures -join "; ")
Write-Warning $message
if ($values["ALERT_WEBHOOK_URL"]) {
    Invoke-RestMethod -Method Post -Uri $values["ALERT_WEBHOOK_URL"] -ContentType "application/json" `
        -Body (ConvertTo-Json @{ text = $message } -Compress) -TimeoutSec $TimeoutSeconds | Out-Null
}
exit 1
