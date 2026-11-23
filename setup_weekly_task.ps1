# Registra uma tarefa agendada semanal no Windows (todo domingo as 03:00)
# Execute no PowerShell (como Administrador se necessario):
#   .\scripts\osm\setup_weekly_task.ps1

$TaskName = "AnaliseUrbana_OSM_Weekly_Update"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$PythonExe = (Get-Command python).Source
$ScriptPath = Join-Path $RepoRoot "scripts\osm\run_weekly_osm_update.py"

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`"" -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 03:00AM
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Tarefa '$TaskName' registrada para rodar todo domingo as 03:00 AM."
Write-Host "Para testar manualmente agora: Start-ScheduledTask -TaskName '$TaskName'"
