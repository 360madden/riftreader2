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
$source = $source.Replace('New-Object -ComObject Schedule.Service', '$global:mockScheduler')
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
function New-InspectionTask($registration) {
    $actions = [pscustomobject]@{Count=1; First=[pscustomobject]@{Type=0; Path=$registration.Actions[0].Execute;
        Arguments=$registration.Actions[0].Arguments; WorkingDirectory=$registration.Actions[0].WorkingDirectory}}
    $actions | Add-Member ScriptMethod Item { param($index) if ($index -ne 1) { throw 'invalid action index' }; $this.First }
    $definition = [pscustomobject]@{Actions=$actions; Principal=$registration.Principal.PSObject.Copy();
        Triggers=[pscustomobject]@{Count=0}; Settings=$registration.Settings.PSObject.Copy();
        RegistrationInfo=[pscustomobject]@{Description=$registration.Description}}
    return [pscustomobject]@{Path=('\' + $registration.TaskName); Name=$registration.TaskName;
        State=4; Definition=$definition; LastTaskResult=0}
}
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
    $id = 'rr2-controller-lab2'
    $global:mockTasks = @()
    & $manager -Action Register -HelperId $id -Executable (Join-Path $root 'pythonw.exe') -Argument @((Join-Path $scripts 'controller_task_entry.py'),'--lab','lab2') -WorkingDirectory $root | Out-Null
    $registered = $global:mockTasks[0]
    $global:mockLegacy = $false
    $global:mockDenied = $false
    $global:mockReads = 0
    $global:changeOnSecondRead = $false
    $global:mockScheduler = [pscustomobject]@{Folder=[pscustomobject]@{}}
    $global:mockScheduler | Add-Member ScriptMethod Connect {}
    $global:mockScheduler | Add-Member ScriptMethod GetFolder { param($path) if ($path -cne '\') { throw 'foreign folder' }; $this.Folder }
    $global:mockScheduler.Folder | Add-Member ScriptMethod GetTask {
        param($name)
        if ($name -ceq 'Workbridge Helper rr2-controller-lab2') {
            if ($global:mockDenied) { throw [UnauthorizedAccessException]::new('denied') }
            if ($global:mockLegacy) { return [pscustomobject]@{Name=$name} }
            throw [IO.FileNotFoundException]::new('absent')
        }
        if ($name -cne 'RiftReader2 Helper rr2-controller-lab2') { throw 'foreign task' }
        $global:mockReads++
        if ($global:changeOnSecondRead -and $global:mockReads -eq 2) { $global:inspectionTask.State = 3 }
        return $global:inspectionTask
    }
    $inspect = { & $manager -Action Status -HelperId $id -InspectLab2Controller }
    $global:inspectionTask = New-InspectionTask $registered
    $proof = & $inspect | ConvertFrom-Json
    if ($proof.state -cne 'Running' -or $global:mockReads -ne 2) { throw 'Two fresh task proofs required.' }
    foreach ($alter in @(
        {$t.Path='\other\task'}, {$t.Name='wrong'}, {$t.State=3}, {$d.RegistrationInfo.Description='wrong'},
        {$d.Actions.Count=2}, {$d.Actions.First.Type=5}, {$d.Actions.First.Path='foreign.exe'},
        {$d.Actions.First.Arguments='wrong'}, {$d.Actions.First.WorkingDirectory='wrong'},
        {$d.Principal.UserId='S-1-5-18'}, {$d.Principal.RunLevel=1}, {$d.Principal.LogonType=0},
        {$d.Triggers.Count=1}, {$d.Settings.ExecutionTimeLimit='PT1M'}, {$d.Settings.MultipleInstances=0},
        {$d.Settings.Enabled=$false}, {$d.Settings.DisallowStartIfOnBatteries=$true},
        {$d.Settings.StopIfGoingOnBatteries=$true}, {$d.Settings.RestartCount=1}
    )) {
        $global:inspectionTask = New-InspectionTask $registered
        $t=$global:inspectionTask; $d=$t.Definition
        & $alter
        Must-Fail $inspect
    }
    $global:inspectionTask = New-InspectionTask $registered
    $global:mockReads = 0; $global:changeOnSecondRead = $true
    Must-Fail $inspect
    $global:changeOnSecondRead = $false
    $global:inspectionTask = New-InspectionTask $registered
    $global:mockLegacy = $true; Must-Fail $inspect; $global:mockLegacy = $false
    $global:mockDenied = $true; Must-Fail $inspect; $global:mockDenied = $false
    Must-Fail { & $manager -Action Start -HelperId $id -InspectLab2Controller }
    Must-Fail { & $manager -Action Register -HelperId $id -InspectLab2Controller }
    Must-Fail { & $manager -Action Status -HelperId 'rr2-controller-lab1' -InspectLab2Controller }
    Must-Fail { & $manager -Action Status -HelperId 'rr2-receiver-lab2' -InspectLab2Controller }
    'RR2 helper manager mocked tests passed.'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
