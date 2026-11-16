$ErrorActionPreference = 'Stop'
$shareStatePath = Join-Path $PSScriptRoot '.local\share-state.json'
if (!(Test-Path -LiteralPath $shareStatePath)) { Write-Output 'Активная ссылка не найдена.'; return }
$shareState = Get-Content -LiteralPath $shareStatePath -Raw | ConvertFrom-Json
$shareTargets = @(
    @{Pid=$shareState.tunnel_pid;Marker=(Join-Path $PSScriptRoot '.local\runtime\cloudflared.exe')},
    @{Pid=$shareState.server_pid;Marker=(Join-Path $PSScriptRoot 'backend\serve_share.py')}
)
foreach ($shareTarget in $shareTargets) {
    $shareProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($shareTarget.Pid)" -ErrorAction SilentlyContinue
    if ($shareProcess -and $shareProcess.CommandLine -and $shareProcess.CommandLine.Contains($shareTarget.Marker)) {
        $shareDescendants = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($shareTarget.Marker) -and $_.ProcessId -ne $shareProcess.ProcessId -and $_.Name -match '^(python|cloudflared).*\.exe$' })
        foreach ($shareChild in $shareDescendants) { Stop-Process -Id $shareChild.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $shareProcess.ProcessId -ErrorAction SilentlyContinue
    }
}
& (Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'backend\manage.py') publish_temporary_url --url $shareState.url --clear
if ($LASTEXITCODE -ne 0) { throw 'Cannot clear the stopped public recovery address.' }
$shareState | Add-Member -NotePropertyName stopped_at -NotePropertyValue (Get-Date).ToString('o') -Force
$shareState | ConvertTo-Json | Set-Content -LiteralPath $shareStatePath -Encoding utf8
Write-Output 'Временная ссылка отключена. Локальная LMS продолжает работать.'
