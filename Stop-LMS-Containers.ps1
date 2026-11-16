$ErrorActionPreference = 'Stop'
$lmsDocker = Get-Command docker -ErrorAction SilentlyContinue
$lmsDockerPath = if ($lmsDocker) { $lmsDocker.Source } else { 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' }
& $lmsDockerPath compose -f (Join-Path $PSScriptRoot 'deployment\compose.yaml') down
