$ErrorActionPreference = 'Stop'
$originalModulePath = $env:PSModulePath
$env:PSModulePath = 'C:\rr2-test-invalid-module-path'
$originalAutoload = $PSModuleAutoloadingPreference
$PSModuleAutoloadingPreference = 'None'
foreach ($module in @('Microsoft.PowerShell.Utility','Microsoft.PowerShell.Management','CimCmdlets')) {
    Import-Module ([IO.Path]::Combine($PSHOME, 'Modules', $module, ($module + '.psd1'))) -ErrorAction Stop
}
try {
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
$source = $source.Replace("New-Object -ComObject 'Schedule.Service'", '$global:mockService')
[IO.File]::WriteAllText($manager, $source)
$global:mockInstances = @([pscustomobject]@{EnginePID=123; InstanceGuid='4a048a33-b778-4f2f-9a90-e139cd4ce100'})
$global:collection = [pscustomobject]@{}
$collection = $global:collection
$collection | Add-Member ScriptProperty Count { $global:mockInstances.Count }
$collection | Add-Member ScriptMethod Item { param($index) $global:mockInstances[$index-1] }
$registeredTask = [pscustomobject]@{collection=$collection}
$registeredTask | Add-Member ScriptMethod GetInstances { param($flags) $this.collection }
$folder = [pscustomobject]@{registeredTask=$registeredTask}
$folder | Add-Member ScriptMethod GetTask { param($name) $this.registeredTask }
$global:mockService = [pscustomobject]@{folder=$folder}
$global:mockService | Add-Member ScriptMethod Connect { }
$global:mockService | Add-Member ScriptMethod GetFolder { param($path) $this.folder }
$id = 'rr2-receiver-lab1'
$global:mockTasks = @()
$global:mockStarts = 0
$global:mockRegistrations = 0
$global:queryFailure = $false
$global:scheduledQueries = 0
function global:Get-ScheduledTask {
    param($TaskPath, $TaskName, $ErrorAction)
    $global:scheduledQueries++
    if ($global:scheduledHook) { & $global:scheduledHook }
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
function global:Get-Item {
    param($LiteralPath,[switch]$Force)
    if ($global:retryReparse -and $global:scheduledQueries -ge 2 -and $LiteralPath -ceq $global:retryReceipt) { return [pscustomobject]@{Attributes=[IO.FileAttributes]::ReparsePoint} }
    Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath -Force:$Force
}
$global:mockMutations=0
function global:Stop-ScheduledTask { $global:mockMutations++; throw 'Status attempted Stop-ScheduledTask' }
function global:Unregister-ScheduledTask { $global:mockMutations++; throw 'Status attempted Unregister-ScheduledTask' }
function global:Set-ScheduledTask { $global:mockMutations++; throw 'Status attempted Set-ScheduledTask' }
function global:Get-ScheduledTaskInfo { param($TaskPath,$TaskName) [pscustomobject]@{LastTaskResult=0} }
function Must-Fail([scriptblock]$Block) { try { & $Block | Out-Null } catch { return }; throw ('Expected refusal at ' + (Get-PSCallStack | Select-Object -Skip 1 -First 1).ScriptLineNumber) }
function Register-Test { & $manager -Action Register -HelperId $id -Executable (Join-Path $root 'pythonw.exe') -Argument @((Join-Path $scripts 'receiver_task_entry.py'),'--lab','lab1') -WorkingDirectory $root }
function New-InspectionTask($registration) {
    $actions = [pscustomobject]@{Count=1; First=[pscustomobject]@{Type=0; Path=$registration.Actions[0].Execute;
        Arguments=$registration.Actions[0].Arguments; WorkingDirectory=$registration.Actions[0].WorkingDirectory}}
    $actions | Add-Member ScriptMethod Item { param($index) if ($index -ne 1) { throw 'invalid action index' }; $this.First }
    $definition = [pscustomobject]@{Actions=$actions; Principal=$registration.Principal.PSObject.Copy();
        Triggers=[pscustomobject]@{Count=0}; Settings=$registration.Settings.PSObject.Copy();
        RegistrationInfo=[pscustomobject]@{Description=$registration.Description}}
    $result = [pscustomobject]@{Path=('\' + $registration.TaskName); Name=$registration.TaskName;
        State=4; Definition=$definition; LastTaskResult=0}
    $result.State = if ($registration.State -ceq 'Running') { 4 } else { 3 }
    $result | Add-Member ScriptMethod GetInstances { param($flags) $global:collection }
    return $result
}
$global:mockScheduler = [pscustomobject]@{Folder=[pscustomobject]@{}}
$global:mockScheduler | Add-Member ScriptMethod Connect {}
$global:mockScheduler | Add-Member ScriptMethod GetFolder { param($path) $this.Folder }
$global:mockScheduler.Folder | Add-Member ScriptMethod GetTask {
    param($name)
    if ($global:queryFailure) { throw [UnauthorizedAccessException]::new('denied') }
    $matches = @($global:mockTasks | Where-Object TaskName -IEQ $name)
    if ($matches.Count -eq 0) { throw [IO.FileNotFoundException]::new('absent') }
    if ($matches.Count -ne 1) { throw 'ambiguous' }
    if ($name -like 'Workbridge Helper *') { return $matches[0] }
    return New-InspectionTask $matches[0]
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
    $status = & $manager -Action Status -HelperId $id | ConvertFrom-Json
    if ($status.enginePid -ne 123 -or !$status.instanceGuid) { throw 'Instance identity missing' }
    $instance = $global:mockInstances[0]
    $global:mockInstances = @(); Must-Fail { & $manager -Action Status -HelperId $id }
    $global:mockInstances = @($instance, $instance); Must-Fail { & $manager -Action Status -HelperId $id }
    $global:mockInstances = @($instance)
    & $manager -Action Start -HelperId $id | Out-Null
    if ($global:mockStarts -ne 1) { throw 'Start was not idempotent.' }
    # All four allowlisted running helpers use COM; Ready and absent use the
    # existing ScheduledTasks path, without starting any owner.
    foreach ($other in @('rr2-receiver-lab1','rr2-receiver-lab2','rr2-controller-lab1','rr2-controller-lab2')) {
        $id = $other; $kind = $id.Split('-')[1]; $lab = $id.Split('-')[2]
        $global:mockTasks = @()
        & $manager -Action Register -HelperId $id -Executable (Join-Path $root 'pythonw.exe') -Argument @((Join-Path $scripts ($kind + '_task_entry.py')),'--lab',$lab) -WorkingDirectory $root | Out-Null
        $registeredOther = $global:mockTasks[0]
        $global:scheduledQueries = 0
        $ready = & $manager -Action Status -HelperId $id | ConvertFrom-Json
        if ($ready.state -cne 'Ready' -or $global:scheduledQueries -lt 1) { throw 'Ready fallback failed' }
        $global:mockTasks = @(); $global:scheduledQueries = 0
        $absent = & $manager -Action Status -HelperId $id | ConvertFrom-Json
        if ($absent.state -cne 'NotRegistered' -or $global:scheduledQueries -lt 1 -or $null -ne $absent.enginePid -or $null -ne $absent.instanceGuid -or $null -ne $absent.runLevel -or $null -ne $absent.lastTaskResult -or !$absent.note) { throw 'Absent fallback failed' }
        $registeredOther.State = 'Running'; $global:mockTasks = @($registeredOther); $global:scheduledQueries = 0
        $running = & $manager -Action Status -HelperId $id | ConvertFrom-Json
        if ($running.enginePid -ne 123 -or !$running.instanceGuid -or $global:scheduledQueries -ne 0) { throw 'Running COM path failed' }
    }
    # Script the actual manager across a late ScheduledTasks Running transition.
    # Every exact COM read creates a fresh task/definition; counters forbid cached
    # proofs and retries of ownership errors. No real scheduler module is loaded.
    $savedScheduler = $global:mockScheduler
    $id = 'rr2-receiver-lab1'; $task.State = 'Running'; $global:mockTasks = @($task)
    $global:retryTask = $task
    $global:retryInstance = $global:mockInstances[0]
    $global:retryScheduler = [pscustomobject]@{Folder=[pscustomobject]@{}}
    $global:retryScheduler | Add-Member ScriptMethod Connect {}
    $global:retryScheduler | Add-Member ScriptMethod GetFolder { param($path) $this.Folder }
    $global:retryScheduler.Folder | Add-Member ScriptMethod GetTask {
        param($name)
        if ($name -ceq ('Workbridge Helper ' + $global:retryTask.TaskName.Substring(19))) {
            $global:retryLegacyReads++
            if ($global:retryLegacy -or ($global:retryLateLegacy -and $global:retryLegacyReads -eq 2)) { return [pscustomobject]@{Name=$name} }
            if ($global:retryLegacyDenied) { throw [UnauthorizedAccessException]::new('denied') }
            throw [IO.FileNotFoundException]::new('absent')
        }
        if ($name -cne $global:retryTask.TaskName) { throw 'foreign task' }
        $global:retryReads++
        $fresh = New-InspectionTask $global:retryTask
        $fresh.State = $global:retryStates[[Math]::Min($global:retryReads-1, $global:retryStates.Count-1)]
        $global:mockInstances = @($global:retryInstance)
        if ($global:retryHook) { & $global:retryHook $fresh $global:retryReads }
        return $fresh
    }
    function Reset-RetryMock($states) {
        $global:retryStates = @($states); $global:retryReads=0; $global:retryLegacyReads=0
        $global:scheduledQueries=0; $global:retryHook=$null; $global:scheduledHook=$null
        $global:retryLegacy=$false; $global:retryLegacyDenied=$false; $global:retryLateLegacy=$false; $global:retryReparse=$false
        $global:mockTasks=@($global:retryTask); $global:retryTask.State='Running'
        $global:mockInstances=@($global:retryInstance)
        $global:mockScheduler=$global:retryScheduler
    }
    function Assert-RetryCounts($reads,$queries,$legacy) {
        if ($global:retryReads -ne $reads -or $global:scheduledQueries -ne $queries -or $global:retryLegacyReads -ne $legacy) {
            throw "Retry proof calls differ: COM=$global:retryReads ScheduledTasks=$global:scheduledQueries legacy=$global:retryLegacyReads; expected $reads/$queries/$legacy"
        }
    }
    $startsBeforeRetry=$global:mockStarts; $registrationsBeforeRetry=$global:mockRegistrations
    Reset-RetryMock @(3,4,4)
    $late = & $manager -Action Status -HelperId $id | ConvertFrom-Json
    if ($late.state -cne 'Running' -or $late.enginePid -ne 123 -or $late.instanceGuid -cne $global:retryInstance.InstanceGuid -or !$late.note) { throw 'Late Running identity proof missing.' }
    Assert-RetryCounts 3 2 2
    Reset-RetryMock @(3,3,4,4)
    $late = & $manager -Action Status -HelperId $id | ConvertFrom-Json
    if ($late.enginePid -ne 123 -or $late.instanceGuid -cne $global:retryInstance.InstanceGuid) { throw 'Third-attempt proof missing.' }
    Assert-RetryCounts 4 4 2
    Reset-RetryMock @(3,3,3)
    Must-Fail { & $manager -Action Status -HelperId $id }
    Assert-RetryCounts 3 6 0
    # Every retry still demands a complete two-read proof; errors never consume
    # another attempt. A second-read state change cannot be promoted to Running.
    Reset-RetryMock @(3,4,3)
    Must-Fail { & $manager -Action Status -HelperId $id }
    Assert-RetryCounts 3 2 2
    foreach ($changed in @([pscustomobject]@{EnginePID=124; InstanceGuid=$global:retryInstance.InstanceGuid},
                            [pscustomobject]@{EnginePID=123; InstanceGuid='1a048a33-b778-4f2f-9a90-e139cd4ce100'})) {
        Reset-RetryMock @(3,4,4)
        $global:retryChanged=$changed
        $global:retryHook={ param($fresh,$read) if ($read -eq 3) { $global:mockInstances=@($global:retryChanged) } }
        Must-Fail { & $manager -Action Status -HelperId $id }
        Assert-RetryCounts 3 2 2
    }
    foreach ($damage in @(
        { param($fresh,$read) if ($read -eq 2) { $fresh.Definition.Actions.First.Arguments='wrong' } },
        { param($fresh,$read) if ($read -eq 2) { $global:mockInstances=@($global:retryInstance,$global:retryInstance) } },
        { param($fresh,$read) if ($read -eq 2) { $global:mockInstances=@([pscustomobject]@{EnginePID=0; InstanceGuid='invalid'}) } },
        { param($fresh,$read) if ($read -eq 2) { $fresh.Definition.Triggers=$null } }
    )) {
        Reset-RetryMock @(3,4,4); $global:retryHook=$damage
        Must-Fail { & $manager -Action Status -HelperId $id }
        Assert-RetryCounts 2 2 1
    }
    foreach ($legacyDenied in @($false,$true)) {
        Reset-RetryMock @(3,4,4)
        $global:retryLegacy=!$legacyDenied; $global:retryLegacyDenied=$legacyDenied
        Must-Fail { & $manager -Action Status -HelperId $id }
        Assert-RetryCounts 2 2 1
    }
    # Initial denied/malformed reads are hard failures, without fallback/retry.
    foreach ($damage in @(
        { param($fresh,$read) throw [UnauthorizedAccessException]::new('denied') },
        { param($fresh,$read) $fresh.State=0 }
    )) {
        Reset-RetryMock @(3); $global:retryHook=$damage
        Must-Fail { & $manager -Action Status -HelperId $id }
        Assert-RetryCounts 1 0 0
    }
    # Once Running was observed through ScheduledTasks, a later Ready/missing
    # fallback must refuse admission instead of silently downgrading the result.
    foreach ($missing in @($false,$true)) {
        Reset-RetryMock @(3,3)
        $global:retryMissing=$missing
        $global:retryHook={ param($fresh,$read) if ($read -eq 2) {
            if ($global:retryMissing) { $global:mockTasks=@() } else { $global:retryTask.State='Ready' }
        } }
        Must-Fail { & $manager -Action Status -HelperId $id }
        Assert-RetryCounts 2 4 0
    }
    # Re-reading COM alone is insufficient: the registration receipt must also
    # be read afresh before retry, even if the cached task still matches it.
    Reset-RetryMock @(3,4,4)
    $retryReceipt = Join-Path $root ('.local/rr2-helpers/' + $id + '/registration.json')
    $savedReceipt = [IO.File]::ReadAllText($retryReceipt)
    $global:retryReceipt=$retryReceipt
    $global:scheduledHook={ if ($global:scheduledQueries -eq 2) { [IO.File]::WriteAllText($global:retryReceipt, '{}') } }
    try {
        Must-Fail { & $manager -Action Status -HelperId $id }
        Assert-RetryCounts 1 2 0
    } finally { [IO.File]::WriteAllText($retryReceipt,$savedReceipt) }
    Reset-RetryMock @(3,4,4); $global:retryReparse=$true
    Must-Fail { & $manager -Action Status -HelperId $id }
    Assert-RetryCounts 1 2 0
    Reset-RetryMock @(3,4,4); $global:retryLateLegacy=$true
    Must-Fail { & $manager -Action Status -HelperId $id }
    Assert-RetryCounts 2 2 2
    # Initial COM absence is not the eligible non-running-to-running race.
    Reset-RetryMock @(3)
    $global:retryHook={ param($fresh,$read) throw [IO.FileNotFoundException]::new('absent') }
    Must-Fail { & $manager -Action Status -HelperId $id }
    Assert-RetryCounts 1 2 0
    Reset-RetryMock @(3); $global:retryTask.State='Ready'
    $ready = & $manager -Action Status -HelperId $id | ConvertFrom-Json
    if ($ready.state -cne 'Ready' -or $null -ne $ready.enginePid -or $null -ne $ready.instanceGuid -or $ready.runLevel -cne 'Limited' -or !$ready.note) { throw 'Ordinary Ready contract changed.' }
    Assert-RetryCounts 1 2 0
    if ($global:mockStarts -ne $startsBeforeRetry -or $global:mockRegistrations -ne $registrationsBeforeRetry -or $global:mockMutations -ne 0) { throw 'Status mutated scheduler ownership.' }
    $global:mockScheduler=$savedScheduler; $global:mockInstances=@($global:retryInstance)
    $task.State='Running'
    $id = 'rr2-receiver-lab1'; $global:mockTasks = @($task)
    $receipt = Join-Path $root ('.local/rr2-helpers/' + $id + '/registration.json')
    $data = Get-Content $receipt -Raw | ConvertFrom-Json
    $data.arguments = 'forged'
    $data | ConvertTo-Json | Set-Content $receipt
    Must-Fail { & $manager -Action Status -HelperId $id }
    $id = 'rr2-controller-lab2'
    $global:mockTasks = @()
    & $manager -Action Register -HelperId $id -Executable (Join-Path $root 'pythonw.exe') -Argument @((Join-Path $scripts 'controller_task_entry.py'),'--lab','lab2') -WorkingDirectory $root | Out-Null
    $registered = $global:mockTasks[0]
    $registered.State = 'Running'
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
        if ($global:currentNull) { return $null }
        if ($global:currentDenied) { throw [UnauthorizedAccessException]::new('denied') }
        if ($global:currentMissing) { throw [IO.FileNotFoundException]::new('absent') }
        $global:mockReads++
        if ($global:nullSecond -and $global:mockReads -eq 2) { return $null }
        if ($global:changeDefinition -and $global:mockReads -eq 2) { $global:inspectionTask.Definition.Actions.First.Arguments = 'changed' }
        if ($global:changeIdentity -and $global:mockReads -eq 2) { $global:mockInstances=@($global:changeIdentity) }
        if ($global:changeOnSecondRead -and $global:mockReads -eq 2) { $global:inspectionTask.State = 3 }
        return $global:inspectionTask
    }
    $inspect = { & $manager -Action Status -HelperId $id -InspectLab2Controller }
    $fast = { & $manager -Action Status -HelperId $id }
    $global:inspectionTask = New-InspectionTask $registered
    $normalProof = & $fast | ConvertFrom-Json
    if ($normalProof.enginePid -ne 123 -or !$normalProof.instanceGuid -or !$normalProof.note) { throw 'Normal COM proof missing' }
    $global:inspectionTask.LastTaskResult = -2147024891
    if ((& $fast | ConvertFrom-Json).lastTaskResult -ne 2147942405) { throw 'Unsigned result mismatch' }
    if ((& $inspect | ConvertFrom-Json).lastTaskResult -ne -2147024891) { throw 'Inspection result changed' }
    $global:inspectionTask.LastTaskResult = 0
    $global:currentNull=$true; Must-Fail $fast; $global:currentNull=$false
    $global:mockReads=0; $global:nullSecond=$true; Must-Fail $fast; $global:nullSecond=$false
    $global:currentDenied=$true; Must-Fail $fast; $global:currentDenied=$false
    $global:currentMissing=$true; Must-Fail $fast; $global:currentMissing=$false
    $global:inspectionTask.State=0; Must-Fail $fast; $global:inspectionTask.State=4
    $global:mockReads = 0
    $proof = & $inspect | ConvertFrom-Json
    if ($proof.enginePid -ne 123 -or !$proof.instanceGuid) { throw 'Inspection instance identity missing' }
    if ($proof.state -cne 'Running' -or $global:mockReads -ne 2) { throw 'Two fresh task proofs required.' }
    $instance = $global:mockInstances[0]
    $global:mockInstances=@(); Must-Fail $inspect; Must-Fail $fast
    $global:mockInstances=@($instance,$instance); Must-Fail $inspect; Must-Fail $fast
    foreach ($bad in @([pscustomobject]@{EnginePID=0; InstanceGuid=$instance.InstanceGuid},
                         [pscustomobject]@{EnginePID=123; InstanceGuid='invalid'})) {
        $global:mockInstances=@($bad); Must-Fail $inspect; Must-Fail $fast
    }
    $global:mockInstances=@($instance)
    foreach ($alter in @(
        {$t.Path='\other\task'}, {$t.Name='wrong'}, {$t.State=3}, {$d.RegistrationInfo.Description='wrong'},
        {$d.Actions.Count=2}, {$d.Actions.First.Type=5}, {$d.Actions.First.Path='foreign.exe'},
        {$d.Actions.First.Arguments='wrong'}, {$d.Actions.First.WorkingDirectory='wrong'},
        {$d.Principal.UserId='S-1-5-18'}, {$d.Principal.RunLevel=1}, {$d.Principal.RunLevel=$null}, {$d.Principal.LogonType=0},
        {$d.Triggers.Count=1}, {$d.Triggers=$null}, {$d.Triggers=[pscustomobject]@{Count=$null}}, {$d.Settings.ExecutionTimeLimit='PT1M'}, {$d.Settings.MultipleInstances=0},
        {$d.Settings.Enabled=$false}, {$d.Settings.DisallowStartIfOnBatteries=$true},
        {$d.Settings.StopIfGoingOnBatteries=$true}, {$d.Settings.RestartCount=1},
        {$d.Settings.DisallowStartIfOnBatteries=$null}, {$d.Settings.StopIfGoingOnBatteries=$null},
        {$d.Settings.RestartCount=$null}, {$t.LastTaskResult=$null}
    )) {
        $global:inspectionTask = New-InspectionTask $registered
        $t=$global:inspectionTask; $d=$t.Definition
        & $alter
        Must-Fail $inspect; Must-Fail $fast
    }
    $global:inspectionTask = New-InspectionTask $registered
    $global:mockReads = 0; $global:changeOnSecondRead = $true
    Must-Fail $inspect
    $global:changeOnSecondRead = $false
    $global:inspectionTask = New-InspectionTask $registered; $global:mockReads=0; $global:changeDefinition=$true
    Must-Fail $fast
    $global:changeDefinition=$false
    foreach ($changed in @([pscustomobject]@{EnginePID=124; InstanceGuid=$instance.InstanceGuid},
                            [pscustomobject]@{EnginePID=123; InstanceGuid='1a048a33-b778-4f2f-9a90-e139cd4ce100'})) {
        $global:mockInstances=@($instance); $global:mockReads=0; $global:changeIdentity=$changed
        Must-Fail $inspect
        $global:mockInstances=@($instance); $global:mockReads=0; Must-Fail $fast
    }
    $global:changeIdentity=$null; $global:mockInstances=@($instance)
    $global:inspectionTask = New-InspectionTask $registered
    $global:mockLegacy = $true; Must-Fail $inspect; Must-Fail $fast; $global:mockLegacy = $false
    $global:mockDenied = $true; Must-Fail $inspect; Must-Fail $fast; $global:mockDenied = $false
    Must-Fail { & $manager -Action Start -HelperId $id -InspectLab2Controller }
    Must-Fail { & $manager -Action Register -HelperId $id -InspectLab2Controller }
    Must-Fail { & $manager -Action Status -HelperId 'rr2-controller-lab1' -InspectLab2Controller }
    Must-Fail { & $manager -Action Status -HelperId 'rr2-receiver-lab2' -InspectLab2Controller }
    'RR2 helper manager mocked tests passed.'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}

} finally {
    $env:PSModulePath = $originalModulePath
    $PSModuleAutoloadingPreference = $originalAutoload
}
