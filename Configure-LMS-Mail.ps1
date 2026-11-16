param([Parameter(Mandatory=$true)][string]$Sender, [switch]$Console)
$ErrorActionPreference = 'Stop'
if (!$Console) {
    if ($Sender -notmatch '^[a-zA-Z0-9._%+-]+@(gmail\.com|googlemail\.com)$') { throw 'Укажите адрес Gmail отправителя.' }
    $mailGuiShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $mailGuiScript = Join-Path $PSScriptRoot 'Configure-LMS-Mail-Window.ps1'
    Start-Process -FilePath $mailGuiShell -ArgumentList @('-STA','-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$mailGuiScript+'"'),'-Sender',$Sender) -WindowStyle Normal | Out-Null
    return
}
$mailSetupRoot = $PSScriptRoot
$mailSetupPython = Join-Path $mailSetupRoot 'backend\.venv\Scripts\python.exe'
Push-Location (Join-Path $mailSetupRoot 'backend')
try {
    & $mailSetupPython manage.py configure_gmail_mail --sender $Sender
    if ($LASTEXITCODE -ne 0) { throw 'Mail setup did not finish. No SMTP changes were applied.' }
    & (Join-Path $mailSetupRoot 'Start-LMS-Recovery.ps1') -RestartMail
    Write-Host 'Mail worker restarted. Return to the chat so we can verify the LMS backend and the recovery email.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Pop-Location
    Read-Host 'Press Enter to close this window' | Out-Null
}
