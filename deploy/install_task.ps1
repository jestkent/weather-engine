# Registers a Windows Scheduled Task that keeps the collector running 24/7:
# starts at logon and auto-restarts if it ever exits.
#
# Run ONCE in an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File deploy\install_task.ps1
#
# Manage afterwards:
#   Start-ScheduledTask  -TaskName WeatherEngineCollector
#   Stop-ScheduledTask   -TaskName WeatherEngineCollector
#   Get-ScheduledTaskInfo -TaskName WeatherEngineCollector   # LastRunTime / LastTaskResult
#   Unregister-ScheduledTask -TaskName WeatherEngineCollector -Confirm:$false

$taskName = "WeatherEngineCollector"
$proj = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $proj "deploy\run_collector.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wrapper`""

$trigger = New-ScheduledTaskTrigger -AtLogOn

# Restart on failure, run on battery, and no execution time limit (it runs forever).
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Weather Engine 24/7 collector" -Force

Write-Host "Registered '$taskName'. Start it now with:"
Write-Host "  Start-ScheduledTask -TaskName $taskName"
Write-Host ""
Write-Host "NOTE: a sleeping laptop still pauses collection. For true 24/7, either disable"
Write-Host "sleep (powercfg /change standby-timeout-ac 0) or run the Docker image on an"
Write-Host "always-on host (see deploy/README.md)."
