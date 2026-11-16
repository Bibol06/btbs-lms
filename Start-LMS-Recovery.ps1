param([switch]$RestartMail)
$ErrorActionPreference = 'Stop'
$recoveryRoot = $PSScriptRoot
$recoveryBackend = Join-Path $recoveryRoot 'backend'
$recoveryLocal = Join-Path $recoveryRoot '.local'
$recoveryPython = Join-Path $recoveryBackend '.venv\Scripts\python.exe'
$recoveryPidFile = Join-Path $recoveryLocal 'server-pids.json'
New-Item -ItemType Directory -Path $recoveryLocal -Force | Out-Null
$recoveryPids = @{}
if (Test-Path -LiteralPath $recoveryPidFile) {
    $recoveryPrevious = Get-Content -LiteralPath $recoveryPidFile -Raw | ConvertFrom-Json
    foreach ($recoveryEntry in $recoveryPrevious.PSObject.Properties) { $recoveryPids[$recoveryEntry.Name] = $recoveryEntry.Value }
}
foreach ($recoveryService in @(@{ Name='recovery'; Command='maintenance_worker'; Extra=@() }, @{ Name='backup'; Command='backup_lms'; Extra=@('--loop') })) {
    $recoveryRunning = $false
    if ($recoveryPids.ContainsKey($recoveryService.Name)) {
        $recoveryProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($recoveryPids[$recoveryService.Name])" -ErrorAction SilentlyContinue
        $recoveryRunning = $recoveryProcess -and $recoveryProcess.CommandLine -and $recoveryProcess.CommandLine.Contains($recoveryPython) -and $recoveryProcess.CommandLine.Contains($recoveryService.Command)
    }
    if ($RestartMail -and $recoveryService.Name -eq 'recovery' -and $recoveryRunning) {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$($recoveryProcess.ProcessId)" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($recoveryPython) -and $_.CommandLine.Contains($recoveryService.Command) } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $recoveryProcess.ProcessId -ErrorAction SilentlyContinue
        $recoveryRunning = $false
    }
    if (!$recoveryRunning) {
        $recoveryProcess = Start-Process -FilePath $recoveryPython -ArgumentList (@('manage.py', $recoveryService.Command) + $recoveryService.Extra) -WorkingDirectory $recoveryBackend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $recoveryLocal ($recoveryService.Name+'.log')) -RedirectStandardError (Join-Path $recoveryLocal ($recoveryService.Name+'-errors.log')) -PassThru
        $recoveryPids[$recoveryService.Name] = $recoveryProcess.Id
    }
}
$recoveryPids | ConvertTo-Json | Set-Content -LiteralPath $recoveryPidFile -Encoding utf8
