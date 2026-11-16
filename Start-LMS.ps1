$ErrorActionPreference = 'Stop'
$lmsRoot = $PSScriptRoot
$lmsBackend = Join-Path $lmsRoot 'backend'
$lmsFrontend = Join-Path $lmsRoot 'frontend'
$lmsLogs = Join-Path $lmsRoot '.local'
New-Item -ItemType Directory -Path $lmsLogs -Force | Out-Null
$lmsPython = Join-Path $lmsBackend '.venv\Scripts\python.exe'
$lmsNode = (Get-Command node.exe -ErrorAction Stop).Source
if (!(Test-Path -LiteralPath $lmsPython)) { throw 'Не найден backend/.venv/Scripts/python.exe' }
if (!(Test-Path -LiteralPath (Join-Path $lmsFrontend 'node_modules\vite\bin\vite.js'))) { throw 'Установите frontend зависимости: npm.cmd ci' }

function Test-LmsPort([int]$port) {
    $lmsSocket = New-Object System.Net.Sockets.TcpClient
    try { $lmsSocket.Connect('127.0.0.1', $port); return $true }
    catch { return $false }
    finally { $lmsSocket.Dispose() }
}

$lmsPids = @{}
$lmsPidFile = Join-Path $lmsLogs 'server-pids.json'
if (Test-Path -LiteralPath $lmsPidFile) {
    $lmsOldPids = Get-Content -LiteralPath $lmsPidFile | ConvertFrom-Json
    foreach ($lmsEntry in $lmsOldPids.PSObject.Properties) { $lmsPids[$lmsEntry.Name] = $lmsEntry.Value }
}
if (!(Test-LmsPort 8000)) {
    $lmsProcess = Start-Process -FilePath $lmsPython -ArgumentList @('manage.py', 'runserver', '127.0.0.1:8000', '--noreload') -WorkingDirectory $lmsBackend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $lmsLogs 'backend.log') -RedirectStandardError (Join-Path $lmsLogs 'backend-errors.log') -PassThru
    $lmsPids.backend = $lmsProcess.Id
} else { Write-Output 'Порт 8000 уже занят: новый backend не запускался.' }
if (!(Test-LmsPort 5173)) {
    $lmsProcess = Start-Process -FilePath $lmsNode -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $lmsFrontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $lmsLogs 'frontend.log') -RedirectStandardError (Join-Path $lmsLogs 'frontend-errors.log') -PassThru
    $lmsPids.frontend = $lmsProcess.Id
} else { Write-Output 'Порт 5173 уже занят: новый frontend не запускался.' }
$lmsWorkerRunning = $false
if ($lmsPids.ContainsKey('worker')) {
    $lmsWorker = Get-CimInstance Win32_Process -Filter "ProcessId=$($lmsPids.worker)" -ErrorAction SilentlyContinue
    $lmsWorkerRunning = $lmsWorker -and $lmsWorker.CommandLine -like '*notification_worker*'
}
if (!$lmsWorkerRunning) {
    $lmsWorker = Start-Process -FilePath $lmsPython -ArgumentList @('manage.py', 'notification_worker') -WorkingDirectory $lmsBackend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $lmsLogs 'notifications.log') -RedirectStandardError (Join-Path $lmsLogs 'notifications-errors.log') -PassThru
    $lmsPids.worker = $lmsWorker.Id
}
$lmsAnalyticsRunning = $false
if ($lmsPids.ContainsKey('analytics')) {
    $lmsAnalyticsProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($lmsPids.analytics)" -ErrorAction SilentlyContinue
    $lmsAnalyticsRunning = $lmsAnalyticsProcess -and $lmsAnalyticsProcess.CommandLine -like '*analytics_snapshots*' -and $lmsAnalyticsProcess.CommandLine.Contains($lmsPython)
}
if (!$lmsAnalyticsRunning) {
    $lmsAnalyticsProcess = Start-Process -FilePath $lmsPython -ArgumentList @('manage.py', 'analytics_snapshots', '--loop') -WorkingDirectory $lmsBackend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $lmsLogs 'analytics.log') -RedirectStandardError (Join-Path $lmsLogs 'analytics-errors.log') -PassThru
    $lmsPids.analytics = $lmsAnalyticsProcess.Id
}
if ($lmsPids.Count -gt 0) { $lmsPids | ConvertTo-Json | Set-Content -Encoding utf8 $lmsPidFile }
& (Join-Path $lmsRoot 'Start-LMS-Recovery.ps1')
Write-Output 'LMS: http://127.0.0.1:5173'
Write-Output 'Логи: .local/backend-errors.log и .local/frontend-errors.log'
