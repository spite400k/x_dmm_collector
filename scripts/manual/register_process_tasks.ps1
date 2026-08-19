# Register process pipelines in Task Scheduler (1h stagger)
# Run once: powershell -ExecutionPolicy Bypass -File scripts\manual\register_process_tasks.ps1
$ErrorActionPreference = 'Stop'
$base = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Test-Path (Join-Path $base 'run_process_main.bat'))) {
  throw "project root not found from $PSScriptRoot"
}

$tasks = @(
  @{ Name = 'x-dmm-collector-process-main';     Bat = 'run_process_main.bat';     At = '01:00' },
  @{ Name = 'x-dmm-collector-process-actress';  Bat = 'run_process_actress.bat';  At = '02:00' },
  @{ Name = 'x-dmm-collector-process-mesugaki'; Bat = 'run_process_mesugaki.bat'; At = '03:00' },
  @{ Name = 'x-dmm-collector-process-main-weekly';     Bat = 'run_process_main_weekly.bat';     At = '12:00'; Weekly = $true },
  @{ Name = 'x-dmm-collector-process-mesugaki-weekly'; Bat = 'run_process_mesugaki_weekly.bat'; At = '13:00'; Weekly = $true }
)

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries:$false `
  -DontStopIfGoingOnBatteries:$false `
  -ExecutionTimeLimit (New-TimeSpan -Hours 72) `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
  -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive `
  -RunLevel Limited

foreach ($t in $tasks) {
  $bat = Join-Path $base $t.Bat
  if (-not (Test-Path $bat)) { throw "missing: $bat" }
  $action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $base
  if ($t.Weekly) {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $t.At
  } else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.At
  }
  Register-ScheduledTask `
    -TaskName $t.Name `
    -TaskPath '\self\' `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null
  Write-Host "OK $($t.Name) @ $($t.At) -> $($t.Bat)"
}

try {
  Disable-ScheduledTask -TaskName 'x-dmm-collector-modify' -TaskPath '\self\' | Out-Null
  Write-Host 'Disabled: \self\x-dmm-collector-modify (old run_process.bat)'
} catch {
  Write-Warning "Could not disable x-dmm-collector-modify: $_"
  Write-Warning 'Disable it manually in Task Scheduler (conflicts with process-main at 01:00).'
}

Write-Host '---- verify ----'
Get-ScheduledTask -TaskPath '\self\' | Where-Object {
  $_.TaskName -like 'x-dmm-collector*'
} | ForEach-Object {
  $info = $_ | Get-ScheduledTaskInfo
  $tr = ($_.Triggers | ForEach-Object { $_.StartBoundary }) -join ','
  $action = ($_.Actions | ForEach-Object { $_.Execute }) -join ','
  [PSCustomObject]@{
    TaskName = $_.TaskName
    State    = $_.State
    NextRun  = $info.NextRunTime
    Trigger  = $tr
    Action   = $action
  }
} | Format-Table -AutoSize
