# Start the isolated QA environment: backend on 127.0.0.1:8100 (config.qa_settings, database lms_qa)
# and the Vite frontend on 127.0.0.1:5174 proxying to it. The dev servers (8000/5173) are untouched.
#   powershell -File tools/qa/start_qa.ps1 [-Reset]
param([switch]$Reset)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$logs = Join-Path $root '.local\qa'
New-Item -ItemType Directory -Force $logs | Out-Null
$python = Join-Path $backend '.venv\Scripts\python.exe'
$env:DJANGO_SETTINGS_MODULE = 'config.qa_settings'
$env:PYTHONIOENCODING = 'utf-8'

function Test-Port($port) { [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) }

if ($Reset) {
  foreach ($port in 8100, 5174) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  }
  & $python (Join-Path $backend 'manage.py') shell -c "from django.db import connection; assert connection.settings_dict['NAME'].startswith('lms_qa'); print('ok')" | Out-Null
  Push-Location $backend
  & $python -c "import os,django;os.environ['DJANGO_SETTINGS_MODULE']='config.qa_settings';django.setup();from django.db import connection;n=connection.settings_dict['NAME'];assert n.startswith('lms_qa');c=connection._nodb_cursor().__enter__();c.execute('DROP DATABASE IF EXISTS '+n+' WITH (FORCE)');c.execute('CREATE DATABASE '+n);print('recreated',n)"
  Remove-Item -Recurse -Force (Join-Path $logs 'media'), (Join-Path $logs 'qa-accounts.json'), (Join-Path $logs 'demo-access.json') -ErrorAction SilentlyContinue
  & $python manage.py migrate -v0
  $video = Get-ChildItem (Join-Path $backend 'media\lesson_materials') -Filter *.mp4 -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($video) { & $python manage.py seed_qa --video $video.FullName } else { & $python manage.py seed_qa }
  & $python manage.py seed_demo; & $python manage.py seed_platform_demo; & $python manage.py seed_deadlines_demo | Out-Null
  Pop-Location
}

if (!(Test-Port 8100)) {
  Start-Process -FilePath $python -ArgumentList @('manage.py', 'runserver', '127.0.0.1:8100', '--noreload') -WorkingDirectory $backend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'backend.log') -RedirectStandardError (Join-Path $logs 'backend-errors.log') | Out-Null
}
if (!(Test-Port 5174)) {
  $env:VITE_API_TARGET = 'http://127.0.0.1:8100'
  $node = (Get-Command node).Source
  Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5174', '--strictPort') -WorkingDirectory $frontend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs 'frontend.log') -RedirectStandardError (Join-Path $logs 'frontend-errors.log') | Out-Null
}
Write-Output 'QA: http://127.0.0.1:5174 (backend 127.0.0.1:8100, database lms_qa). Accounts: .local/qa/qa-accounts.json'
