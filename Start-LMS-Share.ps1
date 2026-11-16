param([ValidateRange(1024,65535)][int]$Port = 8001, [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$shareRoot = $PSScriptRoot
$shareLocal = Join-Path $shareRoot '.local'
$shareRuntime = Join-Path $shareLocal 'runtime'
$shareStatePath = Join-Path $shareLocal 'share-state.json'
$sharePython = Join-Path $shareRoot 'backend\.venv\Scripts\python.exe'
$shareServerScript = Join-Path $shareRoot 'backend\serve_share.py'
$shareCloudflared = Join-Path $shareRuntime 'cloudflared.exe'
$shareVerifiedPath = Join-Path $shareRuntime 'cloudflared-verified.json'
New-Item -ItemType Directory -Path $shareRuntime -Force | Out-Null
& (Join-Path $shareRoot 'Start-LMS-Recovery.ps1')

if (Test-Path -LiteralPath $shareStatePath) {
    $shareOld = Get-Content -LiteralPath $shareStatePath -Raw | ConvertFrom-Json
    $shareOldTunnel = Get-CimInstance Win32_Process -Filter "ProcessId=$($shareOld.tunnel_pid)" -ErrorAction SilentlyContinue
    $shareOldServer = Get-CimInstance Win32_Process -Filter "ProcessId=$($shareOld.server_pid)" -ErrorAction SilentlyContinue
    if ($shareOldTunnel -and $shareOldTunnel.CommandLine -and $shareOldTunnel.CommandLine.Contains($shareCloudflared) -and $shareOldServer -and $shareOldServer.CommandLine -and $shareOldServer.CommandLine.Contains($shareServerScript)) {
        $shareExistingReady = $false
        for ($shareAttempt=0; $shareAttempt -lt 2; $shareAttempt++) {
            try {
                $shareExistingResponse = Invoke-WebRequest -UseBasicParsing -Uri "$($shareOld.url)/api/courses/" -TimeoutSec 5
                if ($shareExistingResponse.StatusCode -eq 200 -and $shareExistingResponse.Headers['Content-Type'] -like 'application/json*') { $shareExistingReady=$true; break }
            }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if ($shareExistingReady) {
            & $sharePython (Join-Path $shareRoot 'backend\manage.py') publish_temporary_url --url $shareOld.url
            if ($LASTEXITCODE -ne 0) { throw 'Cannot publish the public recovery address.' }
            Write-Output "Ссылка уже работает: $($shareOld.url)"; return }
        Write-Output 'Старая ссылка недоступна. Восстанавливаю внешний доступ...'
    }
    & (Join-Path $shareRoot 'Stop-LMS-Share.ps1')
}
$shareSocket = New-Object System.Net.Sockets.TcpClient
try { $shareSocket.Connect('127.0.0.1', $Port); throw "Порт $Port занят. Выберите другой через -Port." }
catch [System.Net.Sockets.SocketException] { }
finally { $shareSocket.Dispose() }

& $sharePython -c 'import waitress, whitenoise'
if ($LASTEXITCODE -ne 0) { throw 'Установите backend/requirements-share.txt в backend/.venv.' }
if (!$SkipBuild) {
    & npm.cmd --prefix (Join-Path $shareRoot 'frontend') run build
    if ($LASTEXITCODE -ne 0) { throw 'Сборка frontend завершилась ошибкой.' }
}
$shareBinaryVerified = $false
if ((Test-Path -LiteralPath $shareCloudflared) -and (Test-Path -LiteralPath $shareVerifiedPath)) {
    $shareVerified = Get-Content -LiteralPath $shareVerifiedPath -Raw | ConvertFrom-Json
    $shareBinaryVerified = $shareVerified.url -match '^https://github\.com/cloudflare/cloudflared/releases/download/' -and (Get-FileHash -LiteralPath $shareCloudflared -Algorithm SHA256).Hash.ToLowerInvariant() -eq $shareVerified.sha256
}
if (!$shareBinaryVerified) {
    Write-Output 'Загрузка официального Cloudflare Tunnel...'
    $shareRelease = Invoke-RestMethod 'https://api.github.com/repos/cloudflare/cloudflared/releases/latest'
    $shareAsset = $shareRelease.assets | Where-Object { $_.name -eq 'cloudflared-windows-amd64.exe' }
    if (!$shareAsset -or $shareAsset.browser_download_url -notmatch '^https://github\.com/cloudflare/cloudflared/releases/download/' -or $shareAsset.digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Не удалось проверить официальный файл Cloudflare.' }
    Invoke-WebRequest -UseBasicParsing -Uri $shareAsset.browser_download_url -OutFile $shareCloudflared
    $shareDigest = (Get-FileHash -LiteralPath $shareCloudflared -Algorithm SHA256).Hash.ToLowerInvariant()
    if ("sha256:$shareDigest" -ne $shareAsset.digest) { throw 'Контрольная сумма Cloudflare не совпала. Файл не запускался.' }
    @{version=$shareRelease.tag_name;url=$shareAsset.browser_download_url;sha256=$shareDigest} | ConvertTo-Json | Set-Content -LiteralPath $shareVerifiedPath -Encoding utf8
}
$shareTunnel = $null
$shareServer = $null
$shareOldHost = [Environment]::GetEnvironmentVariable('LMS_SHARE_HOST', 'Process')
try {
    $shareTunnelLog = Join-Path $shareLocal 'share-tunnel.log'
    $shareTunnel = Start-Process -FilePath $shareCloudflared -ArgumentList @('tunnel','--no-autoupdate','--url',"http://127.0.0.1:$Port",'--protocol','http2') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $shareLocal 'share-tunnel-output.log') -RedirectStandardError $shareTunnelLog -PassThru
    $shareUrl = $null
    for ($shareAttempt=0; $shareAttempt -lt 90; $shareAttempt++) {
        if (Test-Path -LiteralPath $shareTunnelLog) {
            $shareLogText = Get-Content -LiteralPath $shareTunnelLog -Raw
            if ($shareLogText) {
                $shareMatch = [regex]::Match($shareLogText, 'https://[a-z0-9-]+\.trycloudflare\.com')
                if ($shareMatch.Success) { $shareUrl = $shareMatch.Value; break }
            }
        }
        if ($shareTunnel.HasExited) { throw 'Cloudflare Tunnel не запустился. См. .local/share-tunnel.log.' }
        Start-Sleep -Milliseconds 500
    }
    if (!$shareUrl) { throw 'Cloudflare не выдал временный адрес. См. .local/share-tunnel.log.' }
    $env:LMS_SHARE_HOST = ([uri]$shareUrl).Host
    & $sharePython (Join-Path $shareRoot 'backend\manage.py') collectstatic --noinput --settings=config.share_settings
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось подготовить статические файлы.' }
    $shareServer = Start-Process -FilePath $sharePython -ArgumentList @(('"'+$shareServerScript+'"'),'--port',"$Port") -WorkingDirectory (Join-Path $shareRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $shareLocal 'share-server.log') -RedirectStandardError (Join-Path $shareLocal 'share-server-errors.log') -PassThru
    $shareReady = $false
    for ($shareAttempt=0; $shareAttempt -lt 30; $shareAttempt++) {
        try { if ((Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/courses/" -TimeoutSec 2).StatusCode -eq 200) { $shareReady=$true; break } }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (!$shareReady) { throw 'Сервер демонстрации не готов. См. .local/share-server-errors.log.' }
    $sharePublicReady = $false
    $sharePublicFailure = ''
    $sharePublicTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Output 'Проверяю регистрацию внешней ссылки...'
    while ($sharePublicTimer.Elapsed.TotalSeconds -lt 50) {
        try {
            $sharePublicResponse = Invoke-WebRequest -UseBasicParsing -Uri "$shareUrl/api/courses/" -TimeoutSec 3
            if ($sharePublicResponse.StatusCode -eq 200 -and $sharePublicResponse.Headers['Content-Type'] -like 'application/json*') { $sharePublicReady=$true; break }
        }
        catch { $sharePublicFailure = $_.Exception.Message }
        Start-Sleep -Seconds 1
    }
    if (!$sharePublicReady) { throw "Внешняя ссылка не отвечает: $sharePublicFailure" }
    @{url=$shareUrl;port=$Port;server_pid=$shareServer.Id;tunnel_pid=$shareTunnel.Id;started_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $shareStatePath -Encoding utf8
    $shareUrl | Set-Content -LiteralPath (Join-Path $shareLocal 'temporary-link.txt') -Encoding utf8
    & $sharePython (Join-Path $shareRoot 'backend\manage.py') publish_temporary_url --url $shareUrl
    if ($LASTEXITCODE -ne 0) { throw 'Cannot publish the public recovery address.' }
    Write-Output "Временная ссылка: $shareUrl"
    Write-Output 'Для отключения: .\Stop-LMS-Share.ps1'
}
catch {
    if ($shareServer) { Stop-Process -Id $shareServer.Id -ErrorAction SilentlyContinue }
    if ($shareTunnel) { Stop-Process -Id $shareTunnel.Id -ErrorAction SilentlyContinue }
    throw
}
finally { [Environment]::SetEnvironmentVariable('LMS_SHARE_HOST', $shareOldHost, 'Process') }
