param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$name = "LogpressoQueryAssistant"
if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "자동 시작 작업을 제거했습니다."
    exit
}
$script = Join-Path $PSScriptRoot "start_dev.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Description "Start Logpresso Query Assistant containers" -Force | Out-Null
Write-Host "로그인 시 자동 시작 작업을 등록했습니다."
