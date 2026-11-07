$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('rr2-helper-test-' + [guid]::NewGuid().ToString('N'))
$scripts = Join-Path $root 'scripts'
New-Item -ItemType Directory -Path $scripts -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot '../scripts/Manage-RR2HelperTask.ps1') $scripts
$manager = Join-Path $scripts 'Manage-RR2HelperTask.ps1'
# Do not import the real scheduler module into the script scope; all scheduler
# operations below are in-memory functions and cannot mutate Windows tasks.
$source = Get-Content -LiteralPath $manager -Raw
$source = $source -replace '(?m)^Import-Module .*ScheduledTasks.*\r?\n', ''
[IO.File]::WriteAllText($manager, $source)
$id = 'rr2-receiver-lab1'
$global:mockTasks = @()
$global:mockStarts = 0
$global:mockRegistrations = 0
$global:queryFailure = $false
function global:Get-ScheduledTask {
    param($TaskPath, $TaskName, $ErrorAction)
    if ($global:queryFailure) { throw 'mock query failure' }
    if ($TaskName) { return @($global:mockTasks | Where-Object TaskName -CEQ $TaskName) }
    return $global:mockTasks
}
function global:New-ScheduledTaskAction { param($Execute,$Argument,$WorkingDirectory) [pscustomobject]@{Execute=$Execute; Arguments=$Argument; WorkingDirectory=$WorkingDirectory} }
function global:New-ScheduledTaskPrincipal { param($UserId,$LogonType,$RunLevel) [pscustomobject]@{UserId=$UserId; LogonType=3; RunLevel=0} }
function global:New-ScheduledTaskSettingsSet { param([switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries,$ExecutionTimeLimit,$MultipleInstances) [pscustomobject]@{ExecutionTimeLimit='PT0S'; MultipleInstances=2; Enabled=$true; DisallowStartIfOnBatteries=$false; StopIfGoingOnBatteries=$false; RestartCount=0} }
function global:Register-ScheduledTask {
    param($TaskName,$TaskPath,$Action,$Principal,$Settings,$Description)
    $global:mockRegistrations++
    $global:mockTasks += [pscustomobject]@{TaskName=$TaskName; TaskPath=$TaskPath; Actions=@($Action); Principal=$Principal; Settings=$Settings; Description=$Description; Triggers=@(); State='Ready'}
}
function global:Start-ScheduledTask { param($TaskPath,$TaskName) $global:mockStarts++; ($global:mockTasks | Where-Object TaskName -CEQ $TaskName).State = 'Running' }
function global:Get-ScheduledTaskInfo { param($TaskPath,$TaskName) [pscustomobject]@{LastTaskResult=0} }
function Must-Fail([scriptblock]$Block) { try { & $Block | Out-Null } catch { return }; throw 'Expected refusal' }
function Register-Test { & $manager -Action Register -HelperId $id -Executable (Join-Path $root 'pythonw.exe') -Argument @((Join-Path $scripts 'receiver_task_entry.py'),'--lab','lab1') -WorkingDirectory $root }
try {
    [IO.File]::WriteAllText((Join-Path $root 'pythonw.exe'), '')
    Must-Fail { & $manager -Action Status -HelperId 'other' }
    $global:queryFailure = $true
    Must-Fail { Register-Test }
    $global:queryFailure = $false
    $global:mockTasks = @([pscustomobject]@{TaskName=('Workbridge Helper ' + $id); State='Running'})
    Must-Fail { Register-Test }
    $global:mockTasks[0].State = 'Unknown'
    Must-Fail { Register-Test }
    $global:mockTasks[0].State = 'Ready'
    Must-Fail { Register-Test }
    if ($global:mockRegistrations -ne 0) { throw 'Legacy owner was modified or bypassed.' }
    $global:mockTasks = @()
    Must-Fail { & $manager -Action Register -HelperId $id -Executable (Join-Path $root 'pythonw.exe') -Argument @('wrong') -WorkingDirectory $root }
    $global:mockTasks = @([pscustomobject]@{TaskName=('riftreader2 helper ' + $id); State='Ready'})
    Must-Fail { Register-Test }
    $global:mockTasks = @()
    $registered = Register-Test | ConvertFrom-Json
    if ($registered.state -cne 'Ready' -or $registered.atLogon -ne $false -or $global:mockRegistrations -ne 1) { throw 'Registration failed.' }
    Register-Test | Out-Null
    if ($global:mockRegistrations -ne 1) { throw 'Registration was not idempotent.' }
    $task = $global:mockTasks[0]
    $arguments = $task.Actions[0].Arguments
    $task.Actions[0].Arguments = 'tampered'
    Must-Fail { & $manager -Action Start -HelperId $id }
    $task.Actions[0].Arguments = $arguments
    $task.Principal.RunLevel = 1
    Must-Fail { & $manager -Action Status -HelperId $id }
    $task.Principal.RunLevel = 0
    $task.Settings.MultipleInstances = 0
    Must-Fail { & $manager -Action Status -HelperId $id }
    $task.Settings.MultipleInstances = 2
    $task.Principal.UserId = 'S-1-5-18'
    Must-Fail { & $manager -Action Status -HelperId $id }
    $task.Principal.UserId = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $global:mockTasks += [pscustomobject]@{TaskName=('Workbridge Helper ' + $id); State='Running'}
    Must-Fail { & $manager -Action Start -HelperId $id }
    Must-Fail { & $manager -Action Status -HelperId $id }
    $global:mockTasks = @($task)
    & $manager -Action Start -HelperId $id | Out-Null
    & $manager -Action Start -HelperId $id | Out-Null
    if ($global:mockStarts -ne 1) { throw 'Start was not idempotent.' }
    $receipt = Join-Path $root ('.local/rr2-helpers/' + $id + '/registration.json')
    $data = Get-Content $receipt -Raw | ConvertFrom-Json
    $data.arguments = 'forged'
    $data | ConvertTo-Json | Set-Content $receipt
    Must-Fail { & $manager -Action Status -HelperId $id }
    'RR2 helper manager mocked tests passed.'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
