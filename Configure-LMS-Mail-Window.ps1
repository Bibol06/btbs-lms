param([Parameter(Mandatory=$true)][string]$Sender, [switch]$SelfTest)
$ErrorActionPreference = 'Stop'
if ($Sender -notmatch '^[a-zA-Z0-9._%+-]+@(gmail\.com|googlemail\.com)$') { throw 'Укажите адрес Gmail отправителя.' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$mailUiRoot = $PSScriptRoot
$mailUiPython = Join-Path $mailUiRoot 'backend\.venv\Scripts\python.exe'
$mailUiForm = New-Object System.Windows.Forms.Form
$mailUiForm.Text = 'BTBS - Настройка почты'
$mailUiForm.ClientSize = New-Object System.Drawing.Size(620,480)
$mailUiForm.StartPosition = 'CenterScreen'
$mailUiForm.FormBorderStyle = 'FixedDialog'
$mailUiForm.MaximizeBox = $false
$mailUiForm.Font = New-Object System.Drawing.Font('Segoe UI',10)

$mailUiHeading = New-Object System.Windows.Forms.Label
$mailUiHeading.Text = 'Подключение Gmail к BTBS'
$mailUiHeading.Font = New-Object System.Drawing.Font('Segoe UI',16,[System.Drawing.FontStyle]::Bold)
$mailUiHeading.SetBounds(24,20,570,35)
$mailUiForm.Controls.Add($mailUiHeading)
$mailUiSender = New-Object System.Windows.Forms.Label
$mailUiSender.Text = 'Отправитель: ' + $Sender
$mailUiSender.SetBounds(24,65,570,25)
$mailUiForm.Controls.Add($mailUiSender)
$mailUiHelp = New-Object System.Windows.Forms.Label
$mailUiHelp.Text = "Вставьте 16-символьный пароль приложения Google через Ctrl+V.`r`nКод скрыт точками. Пробелы между группами не учитываются."
$mailUiHelp.SetBounds(24,100,570,48)
$mailUiForm.Controls.Add($mailUiHelp)
$mailUiLabel = New-Object System.Windows.Forms.Label
$mailUiLabel.Text = 'Пароль приложения Google'
$mailUiLabel.SetBounds(24,160,570,25)
$mailUiForm.Controls.Add($mailUiLabel)
$mailUiPassword = New-Object System.Windows.Forms.TextBox
$mailUiPassword.UseSystemPasswordChar = $true
$mailUiPassword.MaxLength = 128
$mailUiPassword.SetBounds(24,190,570,32)
$mailUiForm.Controls.Add($mailUiPassword)
$mailUiCount = New-Object System.Windows.Forms.Label
$mailUiCount.SetBounds(24,230,570,25)
$mailUiForm.Controls.Add($mailUiCount)
$mailUiConnect = New-Object System.Windows.Forms.Button
$mailUiConnect.Text = 'Проверить и подключить'
$mailUiConnect.SetBounds(24,268,280,42)
$mailUiConnect.Enabled = $false
$mailUiForm.Controls.Add($mailUiConnect)
$mailUiClose = New-Object System.Windows.Forms.Button
$mailUiClose.Text = 'Закрыть'
$mailUiClose.SetBounds(440,268,154,42)
$mailUiForm.Controls.Add($mailUiClose)
$mailUiStatus = New-Object System.Windows.Forms.TextBox
$mailUiStatus.Multiline = $true
$mailUiStatus.ReadOnly = $true
$mailUiStatus.ScrollBars = 'Vertical'
$mailUiStatus.SetBounds(24,330,570,125)
$mailUiStatus.Text = 'После подключения тестовое письмо придёт на почту отправителя.'
$mailUiForm.Controls.Add($mailUiStatus)
$mailUiForm.AcceptButton = $mailUiConnect
$mailUiForm.CancelButton = $mailUiClose
$script:mailUiProcess = $null
$script:mailUiOutput = $null
$script:mailUiError = $null

function Get-MailUiCode {
    return [regex]::Replace($mailUiPassword.Text,'[\s\p{Cf}]','')
}
function Update-MailUiCount {
    $mailUiCode = Get-MailUiCode
    $mailUiValid = $mailUiCode -cmatch '^[A-Za-z0-9]{16}$'
    $mailUiCount.Text = 'Символов: ' + $mailUiCode.Length + '/16' + $(if($mailUiValid){' — код вставлен'}else{''})
    $mailUiCount.ForeColor = $(if($mailUiValid){[System.Drawing.Color]::DarkGreen}else{[System.Drawing.Color]::DarkOrange})
    $mailUiConnect.Enabled = $mailUiValid -and (!$script:mailUiProcess -or $script:mailUiProcess.HasExited)
    $mailUiCode = $null
}
$mailUiPassword.Add_TextChanged({ Update-MailUiCount })
Update-MailUiCount
$mailUiClose.Add_Click({ $mailUiPassword.Clear(); $mailUiForm.Close() })
$mailUiForm.Add_FormClosing({ param($source,$event) if($script:mailUiProcess -and !$script:mailUiProcess.HasExited){ $event.Cancel=$true; $mailUiStatus.Text='Проверка ещё выполняется. Дождитесь результата.' } })
$mailUiTimer = New-Object System.Windows.Forms.Timer
$mailUiTimer.Interval = 250
$mailUiTimer.Add_Tick({
    if (!$script:mailUiProcess -or !$script:mailUiProcess.HasExited) { return }
    $mailUiTimer.Stop()
    $mailUiOut = $script:mailUiOutput.GetAwaiter().GetResult()
    $mailUiErr = $script:mailUiError.GetAwaiter().GetResult()
    $mailUiStatus.Text = ($mailUiOut + "`r`n" + $mailUiErr).Trim()
    $mailUiClose.Enabled = $true
    if ($script:mailUiProcess.ExitCode -eq 0) {
        $mailUiStatus.ForeColor = [System.Drawing.Color]::DarkGreen
        $mailUiPassword.Clear()
        $mailUiPassword.Enabled = $false
        $mailUiConnect.Enabled = $false
        & (Join-Path $mailUiRoot 'Start-LMS-Recovery.ps1') -RestartMail
        $mailUiStatus.AppendText("`r`nГотово. Вернитесь в чат для проверки письма восстановления.")
    } else {
        $mailUiStatus.ForeColor = [System.Drawing.Color]::Firebrick
        $mailUiPassword.Enabled = $true
        Update-MailUiCount
    }
})
$mailUiConnect.Add_Click({
    $mailUiCode = Get-MailUiCode
    if ($mailUiCode -cnotmatch '^[A-Za-z0-9]{16}$') { return }
    try {
        $mailUiInfo = New-Object System.Diagnostics.ProcessStartInfo
        $mailUiInfo.FileName = $mailUiPython
        $mailUiInfo.Arguments = 'manage.py configure_gmail_mail --sender "' + $Sender + '" --password-stdin'
        $mailUiInfo.WorkingDirectory = Join-Path $mailUiRoot 'backend'
        $mailUiInfo.UseShellExecute = $false
        $mailUiInfo.CreateNoWindow = $true
        $mailUiInfo.RedirectStandardInput = $true
        $mailUiInfo.RedirectStandardOutput = $true
        $mailUiInfo.RedirectStandardError = $true
        $mailUiInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $mailUiInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
        $mailUiInfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
        $script:mailUiProcess = New-Object System.Diagnostics.Process
        $script:mailUiProcess.StartInfo = $mailUiInfo
        [void]$script:mailUiProcess.Start()
        $script:mailUiOutput = $script:mailUiProcess.StandardOutput.ReadToEndAsync()
        $script:mailUiError = $script:mailUiProcess.StandardError.ReadToEndAsync()
        $script:mailUiProcess.StandardInput.WriteLine($mailUiCode)
        $script:mailUiProcess.StandardInput.Close()
        $mailUiCode = $null
        $mailUiPassword.Enabled = $false
        $mailUiConnect.Enabled = $false
        $mailUiClose.Enabled = $false
        $mailUiStatus.ForeColor = [System.Drawing.Color]::Black
        $mailUiStatus.Text = 'Проверяем защищённое соединение и отправляем тестовое письмо. Подождите…'
        $mailUiTimer.Start()
    } catch {
        $mailUiCode = $null
        $mailUiStatus.Text = 'Не удалось запустить проверку. Закройте окно и запустите настройку заново.'
        $mailUiStatus.ForeColor = [System.Drawing.Color]::Firebrick
        $mailUiPassword.Enabled = $true
        $mailUiClose.Enabled = $true
        Update-MailUiCount
    }
})
if ($SelfTest) {
    $mailUiEmptyDisabled = !$mailUiConnect.Enabled
    $mailUiPassword.Text = 'abcd efgh ijkl mnop'
    $mailUiValidEnabled = $mailUiConnect.Enabled -and (Get-MailUiCode).Length -eq 16
    $mailUiPassword.Text = '123456'
    $mailUiShortDisabled = !$mailUiConnect.Enabled
    $mailUiPassword.Clear()
    @{ masked=$mailUiPassword.UseSystemPasswordChar; empty_disabled=$mailUiEmptyDisabled; valid_enabled=$mailUiValidEnabled; short_disabled=$mailUiShortDisabled; cleared=$mailUiPassword.Text.Length -eq 0 } | ConvertTo-Json
    $mailUiTimer.Dispose(); $mailUiForm.Dispose()
    exit
}
$mailUiForm.Add_Shown({ $mailUiPassword.Focus() })
try { [void]$mailUiForm.ShowDialog() } finally { $mailUiPassword.Clear(); $mailUiTimer.Dispose(); $mailUiForm.Dispose() }
