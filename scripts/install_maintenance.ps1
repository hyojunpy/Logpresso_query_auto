param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$tasks = @("LogpressoQueryBackup", "LogpressoQueryMonitor")
if ($Uninstall) {
    $tasks | ForEach-Object { Unregister-ScheduledTask -TaskName $_ -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "유지관리 작업을 제거했습니다."
    exit
}
$backupAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot 'backup.ps1')`""
$backupTrigger = New-ScheduledTaskTrigger -Daily -At "02:00"
Register-ScheduledTask -TaskName $tasks[0] -Action $backupAction -Trigger $backupTrigger -Description "Daily Logpresso data backup" -Force | Out-Null
$monitorAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot 'monitor.ps1')`""
$monitorTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $tasks[1] -Action $monitorAction -Trigger $monitorTrigger -Description "Logpresso API and Ollama monitor" -Force | Out-Null
Write-Host "매일 02:00 백업과 5분 간격 상태 점검을 등록했습니다."
