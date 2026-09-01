# Register collect + tachiyomi backfill in Task Scheduler
#
# 収集は API + DB のみ（Chrome なし）。立ち読みは backfill が担当。
# 推奨スケジュール:
#   23:00  run_collect.bat
#   00:30  run_backfill_tachiyomi.bat  （収集完了後。加工 01:00 より前）
#
# run.py の相手ジョブ待ち:
#   - backfill は collect (run.lock) と加工 3 系統を待ってから開始
#   - collect は加工 3 系統を待ってから開始
#
# Run once:
#   powershell -ExecutionPolicy Bypass -File scripts\manual\register_collect_backfill_tasks.ps1
#
$ErrorActionPreference = 'Stop'
$base = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Test-Path (Join-Path $base 'run_collect.bat'))) {
  throw "project root not found from $PSScriptRoot"
}

$tasks = @(
  @{ Name = 'x-dmm-collector-collect';          Bat = 'run_collect.bat';          At = '23:00' },
  @{ Name = 'x-dmm-collector-backfill-tachiyomi'; Bat = 'run_backfill_tachiyomi.bat'; At = '00:30' }
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
  $trigger = New-ScheduledTaskTrigger -Daily -At $t.At
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

Write-Host ''
Write-Host 'Process tasks: scripts\manual\register_process_tasks.ps1 (01:00 / 02:00 / 03:00)'
Write-Host 'Details: SCRIPTS.md'
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
