# Register collect + tachiyomi backfill in Task Scheduler (\fanza\ 配下)
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
. (Join-Path $PSScriptRoot '_task_scheduler_common.ps1')

$base = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Test-Path (Join-Path $base 'run_collect.bat'))) {
  throw "project root not found from $PSScriptRoot"
}

$tasks = @(
  @{ Name = 'x-dmm-collector-collect'; Bat = 'run_collect.bat'; At = '23:00' },
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

Ensure-XDmmTaskFolder

foreach ($t in $tasks) {
  $bat = Join-Path $base $t.Bat
  if (-not (Test-Path $bat)) { throw "missing: $bat" }
  $trigger = New-ScheduledTaskTrigger -Daily -At $t.At
  Register-XDmmScheduledTask `
    -TaskName $t.Name `
    -BatPath $bat `
    -WorkingDirectory $base `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -AtLabel $t.At
}

Write-Host ''
Write-Host "All tasks registered under $Script:XDmmTaskPath"
Write-Host 'Process tasks: scripts\manual\register_process_tasks.ps1 (01:00 / 02:00 / 03:00)'
Write-Host 'Details: SCRIPTS.md'
Write-Host '---- verify ----'
Show-XDmmScheduledTasks
