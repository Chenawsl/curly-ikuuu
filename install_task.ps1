param(
    [string]$Time = "08:05",
    [string]$TaskName = "iKuuu-Daily-Checkin"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CheckinScript = Join-Path $ScriptDir "checkin.py"
$ConfigFile = Join-Path $ScriptDir "config.json"

if (-not (Test-Path -LiteralPath $CheckinScript)) {
    throw "checkin.py not found: $CheckinScript"
}
if (-not (Test-Path -LiteralPath $ConfigFile)) {
    throw "config.json not found: $ConfigFile"
}

$Config = Get-Content -LiteralPath $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
$Cookie = [string]$Config.cookie
if ([string]::IsNullOrWhiteSpace($Cookie) -or $Cookie -eq "PASTE_YOUR_COOKIE_HERE") {
    throw "config.json does not contain a Cookie. Follow README.md step 2 first."
}

$Python = (Get-Command python -ErrorAction Stop).Source
$Pythonw = Join-Path (Split-Path -Parent $Python) "pythonw.exe"
if (-not (Test-Path -LiteralPath $Pythonw)) {
    $Pythonw = $Python
}

$At = [datetime]::ParseExact($Time, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
$Action = New-ScheduledTaskAction `
    -Execute $Pythonw `
    -Argument "`"$CheckinScript`"" `
    -WorkingDirectory $ScriptDir
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "iKuuu daily check-in using a saved browser cookie" `
    -Force | Out-Null

$Info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Task registered: $TaskName"
Write-Host "Runs daily at:  $Time"
Write-Host "Next run:       $($Info.NextRunTime)"
Write-Host ""
Write-Host "Test now:  Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host "Log file:  $(Join-Path $ScriptDir 'checkin.log')"
