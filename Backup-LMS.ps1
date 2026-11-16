$ErrorActionPreference = 'Stop'
$backupLmsRoot = $PSScriptRoot
$backupLmsPython = Join-Path $backupLmsRoot 'backend\.venv\Scripts\python.exe'
Push-Location (Join-Path $backupLmsRoot 'backend')
try {
    & $backupLmsPython manage.py backup_lms --if-due
    if ($LASTEXITCODE -ne 0) { throw 'LMS backup failed. Open System and storage in LMS for status.' }
} finally { Pop-Location }
