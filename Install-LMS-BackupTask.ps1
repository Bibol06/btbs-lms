$ErrorActionPreference = 'Stop'
$backupTaskName = 'BTBS-LMS-DailyBackup'
$backupTaskScript = Join-Path $PSScriptRoot 'backend\run_backup.py'
$backupTaskPython = Join-Path $PSScriptRoot 'backend\.venv\Scripts\pythonw.exe'
if (!(Test-Path -LiteralPath $backupTaskPython)) { throw 'Python virtual environment is missing.' }
$backupTaskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$backupTaskAction = New-ScheduledTaskAction -Execute $backupTaskPython -Argument ('"' + $backupTaskScript + '"') -WorkingDirectory (Join-Path $PSScriptRoot 'backend')
$backupTaskTriggers = @((New-ScheduledTaskTrigger -Daily -At '03:00'), (New-ScheduledTaskTrigger -AtLogOn -User $backupTaskUser))
$backupTaskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15)
$backupTaskPrincipal = New-ScheduledTaskPrincipal -UserId $backupTaskUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $backupTaskName -Action $backupTaskAction -Trigger $backupTaskTriggers -Settings $backupTaskSettings -Principal $backupTaskPrincipal -Description 'Encrypted BTBS LMS backup with referenced local and S3 media. Runs only while this Windows user is signed in.' -Force | Out-Null
Write-Output 'BTBS-LMS-DailyBackup installed: daily at 03:00 and catch-up at sign-in; no stored Windows password.'
