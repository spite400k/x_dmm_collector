# Register process pipelines in Task Scheduler (\fanza\ 配下)
#
# 加工 3 系統を 1 時間ずらして登録する（最早開始時刻）。
# run.py が収集 (run.lock) と加工の衝突を防ぐ:
#   - 加工は収集終了まで待ってからロック取得
#   - 収集は加工 3 系統のロックが空くまで待つ
# 収集を待ったあと process_actress +1h / process_mesugaki +2h の追加スリープあり。
# 詳細: リポジトリ直下 SCRIPTS.md「run.py の相手ジョブ待ち・加工ずらし」
#
# 収集・後埋め (23:00 / 00:30) は register_collect_backfill_tasks.ps1 で \fanza\ 配下に登録。
#
# Run once:
#   powershell -ExecutionPolicy Bypass -File scripts\manual\register_process_tasks.ps1
#
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_task_scheduler_common.ps1')

$base = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Test-Path (Join-Path $base 'run_process_main.bat'))) {
  throw "project root not found from $PSScriptRoot"
}

# 日次: 01:00 / 02:00 / 03:00（run.py が収集延長時にさらにずらす）
# 週次: 日曜 12:00 / 13:00
$tasks = @(
  @{ Name = 'x-dmm-collector-process-main'; Bat = 'run_process_main.bat'; At = '01:00' },
  @{ Name = 'x-dmm-collector-process-actress'; Bat = 'run_process_actress.bat'; At = '02:00' },
  @{ Name = 'x-dmm-collector-process-mesugaki'; Bat = 'run_process_mesugaki.bat'; At = '03:00' },
  @{ Name = 'x-dmm-collector-process-main-weekly'; Bat = 'run_process_main_weekly.bat'; At = '12:00'; Weekly = $true },
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

Ensure-XDmmTaskFolder

foreach ($t in $tasks) {
  $bat = Join-Path $base $t.Bat
  if (-not (Test-Path $bat)) { throw "missing: $bat" }
  if ($t.Weekly) {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $t.At
  } else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.At
  }
  Register-XDmmScheduledTask `
    -TaskName $t.Name `
    -BatPath $bat `
    -WorkingDirectory $base `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -AtLabel $t.At
}

try {
  Disable-LegacyModifyTask
} catch {
  Write-Warning "Could not disable x-dmm-collector-modify: $_"
  Write-Warning 'Disable it manually in Task Scheduler (conflicts with process-main at 01:00).'
}

Write-Host ''
Write-Host "All tasks registered under $Script:XDmmTaskPath"
Write-Host 'Collect/backfill: scripts\manual\register_collect_backfill_tasks.ps1'
Write-Host '  (23:00 collect, 00:30 backfill_tachiyomi)'
Write-Host 'Peer wait / stagger: see SCRIPTS.md'
Write-Host '---- verify ----'
Show-XDmmScheduledTasks
