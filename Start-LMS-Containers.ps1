$ErrorActionPreference = 'Stop'
$lmsDocker = Get-Command docker -ErrorAction SilentlyContinue
$lmsDockerPath = if ($lmsDocker) { $lmsDocker.Source } else { 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' }
if (-not (Test-Path -LiteralPath $lmsDockerPath)) { throw 'Install Docker Desktop first.' }
& $lmsDockerPath info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and finish WSL setup/reboot first.' }
$lmsFree = (Get-PSDrive C).Free
if ($lmsFree -lt 5GB) { throw 'At least 5 GiB of free disk space is required before building containers.' }
Push-Location $PSScriptRoot
try {
    & '.\backend\.venv\Scripts\python.exe' '.\backend\manage.py' migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    & $lmsDockerPath compose -f deployment/compose.yaml up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Container startup failed. Check Docker logs; do not delete database volumes.' }
    Write-Output 'BTBS: http://127.0.0.1:8080/ ; Redis is bound to 127.0.0.1:6379 only.'
} finally { Pop-Location }
