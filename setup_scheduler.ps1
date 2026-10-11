# setup_scheduler.ps1
# Register Windows Task Scheduler to run fetch_emails every 15 minutes

$TaskName  = "FinanceDashboard-FetchEmails"
$PythonExe = "C:\finance-dashboard\.venv\Scripts\python.exe"
$Script    = "C:\finance-dashboard\run_fetch.py"
$WorkDir   = "C:\finance-dashboard"

Write-Host "Setting up Task Scheduler: $TaskName" -ForegroundColor Cyan

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $Script `
    -WorkingDirectory $WorkDir

$Trigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -Once `
    -At (Get-Date).Date

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Finance Dashboard: fetch KBank emails every 15 minutes"

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null

Write-Host ""
Write-Host "Done! Task registered:" -ForegroundColor Green
Write-Host "  Name     : $TaskName"
Write-Host "  Schedule : every 15 minutes"
Write-Host "  Missed   : will run when available (StartWhenAvailable)"
Write-Host "  Overlap  : new runs ignored if previous still running (IgnoreNew)"
Write-Host "  Log      : C:\finance-dashboard\logs\fetch_YYYYMMDD.log"
Write-Host ""

$t = Get-ScheduledTask -TaskName $TaskName
$i = $t | Get-ScheduledTaskInfo
Write-Host "Status      : $($t.State)"
Write-Host "Last run    : $($i.LastRunTime)"
Write-Host "Next run    : $($i.NextRunTime)"
