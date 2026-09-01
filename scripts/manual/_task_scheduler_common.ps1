# Task Scheduler 共通: タスクは必ず \fanza\ 配下に登録する

$Script:XDmmTaskPath = '\fanza\'
$Script:XDmmLegacyTaskPaths = @('\', '\self\')

function Ensure-XDmmTaskFolder {
    $service = New-Object -ComObject Schedule.Service
    $service.Connect()
    $root = $service.GetFolder('\')
    try {
        $null = $root.GetFolder('fanza')
    } catch {
        $root.CreateFolder('fanza', $null) | Out-Null
        Write-Host "Created Task Scheduler folder: $Script:XDmmTaskPath"
    }
}

function Remove-LegacyScheduledTask {
    param(
        [Parameter(Mandatory)][string]$TaskName,
        [Parameter(Mandatory)][string]$TaskPath
    )
    try {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false -ErrorAction Stop
        Write-Host "Removed legacy task: ${TaskPath}${TaskName}"
    } catch {
        # 同名タスクがなければ無視
    }
}

function Register-XDmmScheduledTask {
    param(
        [Parameter(Mandatory)][string]$TaskName,
        [Parameter(Mandatory)][string]$BatPath,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)]$Trigger,
        [Parameter(Mandatory)]$Settings,
        [Parameter(Mandatory)]$Principal,
        [Parameter(Mandatory)][string]$AtLabel
    )
    foreach ($legacyPath in $Script:XDmmLegacyTaskPaths) {
        Remove-LegacyScheduledTask -TaskName $TaskName -TaskPath $legacyPath
    }
    $action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $WorkingDirectory
    Register-ScheduledTask `
        -TaskName $TaskName `
        -TaskPath $Script:XDmmTaskPath `
        -Action $action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Force | Out-Null
    Write-Host "OK $Script:XDmmTaskPath$TaskName @ $AtLabel -> $(Split-Path -Leaf $BatPath)"
}

function Show-XDmmScheduledTasks {
    Get-ScheduledTask -TaskPath $Script:XDmmTaskPath | Where-Object {
        $_.TaskName -like 'x-dmm-collector*'
    } | ForEach-Object {
        $info = $_ | Get-ScheduledTaskInfo
        $tr = ($_.Triggers | ForEach-Object { $_.StartBoundary }) -join ','
        $action = ($_.Actions | ForEach-Object { $_.Execute }) -join ','
        [PSCustomObject]@{
            TaskPath = $_.TaskPath
            TaskName = $_.TaskName
            State    = $_.State
            NextRun  = $info.NextRunTime
            Trigger  = $tr
            Action   = $action
        }
    } | Format-Table -AutoSize
}

function Disable-LegacyModifyTask {
    foreach ($taskPath in @($Script:XDmmTaskPath, '\self\')) {
        try {
            Disable-ScheduledTask -TaskName 'x-dmm-collector-modify' -TaskPath $taskPath | Out-Null
            Write-Host "Disabled: ${taskPath}x-dmm-collector-modify (old run_process.bat)"
        } catch {
            # 存在しなければ無視
        }
    }
}
