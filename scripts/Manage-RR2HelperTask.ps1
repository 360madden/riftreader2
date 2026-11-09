[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Register','Start','Status')][string]$Action,
    [Parameter(Mandatory)][ValidateSet('rr2-receiver-lab1','rr2-receiver-lab2','rr2-controller-lab1','rr2-controller-lab2')][string]$HelperId,
    [string]$Executable,
    [string[]]$Argument = @(),
    [string]$WorkingDirectory,
    [switch]$InspectLab2Controller,
    [switch]$InspectController
)
$ErrorActionPreference = 'Stop'
# Import this Windows PowerShell interpreter's inbox modules by absolute path.
foreach ($module in @('Microsoft.PowerShell.Utility','Microsoft.PowerShell.Management','CimCmdlets')) {
    Import-Module ([IO.Path]::Combine($PSHOME, 'Modules', $module, ($module + '.psd1'))) -ErrorAction Stop
}
if ($InspectLab2Controller -and ($Action -cne 'Status' -or $HelperId -cne 'rr2-controller-lab2')) {
    throw 'Lab 2 inspection requires exact controller Status.'
}
if ($InspectController -and ($Action -cne 'Status' -or $HelperId -cnotin @('rr2-controller-lab1','rr2-controller-lab2'))) {
    throw 'Inspection requires exact allowlisted controller Status.'
}
$InspectController = $InspectController -or $InspectLab2Controller
function Assert-LocalPath([string]$Path) {
    if (![IO.Path]::IsPathRooted($Path)) { throw 'An absolute path is required.' }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $parent = $full
    while ($parent) {
        if ((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Paths cannot contain links or junctions.' }
        $parent = Split-Path -Parent $parent
    }
    return $full
}
function Write-Registration([string]$Path, $Value) {
    $temporary = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, (ConvertTo-Json -InputObject $Value -Depth 20), [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $Path) }
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}
$repo = Split-Path -Parent $PSScriptRoot
$state = Assert-LocalPath (Join-Path $repo ('.local/rr2-helpers/' + $HelperId))
$taskName = 'RiftReader2 Helper ' + $HelperId
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value

function Join-HelperArguments([string[]]$Values) {
    # Windows native argv quoting, not shell syntax. Task Scheduler invokes the
    # explicit executable directly; arguments never become PowerShell code here.
    $parts = foreach ($value in $Values) {
        if ($null -eq $value -or $value.Contains([char]0)) { throw 'Invalid argument.' }
        $builder = New-Object Text.StringBuilder
        [void]$builder.Append('"')
        $slashes = 0
        foreach ($character in $value.ToCharArray()) {
            if ($character -eq '\') { $slashes++; continue }
            if ($character -eq '"') {
                [void]$builder.Append(('\' * (2 * $slashes + 1)))
            } else { [void]$builder.Append(('\' * $slashes)) }
            [void]$builder.Append($character)
            $slashes = 0
        }
        [void]$builder.Append(('\' * (2 * $slashes)))
        [void]$builder.Append('"')
        $builder.ToString()
    }
    $line = $parts -join ' '
    if ($line.Length -gt 16000) { throw 'Arguments exceed this helper manager limit.' }
    return $line
}

function Get-TaskInstanceIdentity($Task) {
    $instances = $Task.GetInstances(0)
    if ($instances.Count -ne 1) { throw 'TASK_INSTANCE: expected exactly one running instance.' }
    $instance = $instances.Item(1)
    $pidValue = [long]$instance.EnginePID
    $guidValue = [guid]::Empty
    if ($pidValue -le 0 -or $pidValue -gt [int]::MaxValue -or
        ![guid]::TryParse([string]$instance.InstanceGuid, [ref]$guidValue) -or $guidValue -eq [guid]::Empty) { throw 'TASK_INSTANCE: invalid instance identity.' }
    return @{enginePid=[int]$pidValue; instanceGuid=$guidValue.ToString()}
}

function Assert-OwnedHelperTask($Task, $Config) {
    # Task Scheduler may normalize an input SID to a local account name.
    $taskSid = if ($Task.Principal.UserId -match '^S-1-') { $Task.Principal.UserId } else {
        (New-Object Security.Principal.NTAccount($Task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value
    }
    $triggers = @($Task.Triggers | Where-Object { $null -ne $_ })
    $triggerMatches = $triggers.Count -eq [int][bool]$Config.atLogon
    if ($triggerMatches -and $Config.atLogon) {
        $trigger = $triggers[0]
        $triggerSid = if ($trigger.UserId -match '^S-1-') { $trigger.UserId } elseif ($trigger.UserId) {
            (New-Object Security.Principal.NTAccount($trigger.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value
        } else { '' }
        $triggerMatches = $trigger.CimClass.CimClassName -ceq 'MSFT_TaskLogonTrigger' -and
            $trigger.Enabled -and $triggerSid -ieq $sid -and !$trigger.Delay -and
            !$trigger.StartBoundary -and !$trigger.EndBoundary -and !$trigger.Repetition.Interval
    }
    $settingsMatch = $null -ne $Task.Settings.DisallowStartIfOnBatteries -and
        $null -ne $Task.Settings.StopIfGoingOnBatteries -and $null -ne $Task.Settings.RestartCount -and
        $Task.Settings.ExecutionTimeLimit -ceq 'PT0S' -and
        [int]$Task.Settings.MultipleInstances -eq 2 -and $Task.Settings.Enabled -and
        !$Task.Settings.DisallowStartIfOnBatteries -and !$Task.Settings.StopIfGoingOnBatteries -and
        $Task.Settings.RestartCount -eq 0
    if ($Task.TaskPath -cne '\' -or $Task.TaskName -cne $taskName -or
        $Task.Description -cne $Config.description -or @($Task.Actions).Count -ne 1 -or
        $Task.Actions.Execute -ine $Config.executable -or
        [string]$Task.Actions.Arguments -cne [string]$Config.arguments -or
        $Task.Actions.WorkingDirectory -ine $Config.workingDirectory -or
        $taskSid -ine $sid -or $null -eq $Task.Principal.RunLevel -or [int]$Task.Principal.RunLevel -ne 0 -or
        [int]$Task.Principal.LogonType -ne 3 -or !$triggerMatches -or !$settingsMatch) {
        $differences = [ordered]@{
            path=($Task.TaskPath -cne '\'); name=($Task.TaskName -cne $taskName)
            description=($Task.Description -cne $Config.description); actionCount=@($Task.Actions).Count
            executable=($Task.Actions.Execute -ine $Config.executable)
            arguments=([string]$Task.Actions.Arguments -cne [string]$Config.arguments)
            directory=($Task.Actions.WorkingDirectory -ine $Config.workingDirectory)
            identity=($taskSid -ine $sid); runLevel=([int]$Task.Principal.RunLevel -ne 0)
            logonType=([int]$Task.Principal.LogonType -ne 3)
            triggers=(!$triggerMatches); settings=(!$settingsMatch)
        }
        throw ('TASK_OWNERSHIP: task differs; mismatch flags: ' + ($differences | ConvertTo-Json -Compress))
    }
}

$transitionDescription = $null
for ($attempt = 1; $attempt -le 3; $attempt++) {
$retryEligible = $false
$configPath = Assert-LocalPath (Join-Path $state 'registration.json')
$config = if (Test-Path -LiteralPath $configPath) {
    if ((Get-Item -LiteralPath $configPath).Length -gt 65536) { throw 'Invalid registration receipt size.' }
    Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else { $null }
if ((Test-Path -LiteralPath $configPath) -and !$config) { throw 'Invalid registration receipt.' }
if ($config -and ($config.schema -ne 1 -or $config.helperId -cne $HelperId -or $config.ownerSid -cne $sid -or $config.taskName -cne $taskName)) {
    throw 'Registration does not belong to this helper and Windows user.'
}
if ($config) {
    if ($config.atLogon -isnot [bool] -or $config.atLogon -or !$config.executable -or
        !$config.workingDirectory -or $config.arguments -isnot [string]) { throw 'Invalid registration receipt.' }
    $receipt = [ordered]@{schema=1; helperId=$HelperId; ownerSid=$sid; taskName=$taskName; executable=$config.executable; arguments=$config.arguments; workingDirectory=$config.workingDirectory; atLogon=$false}
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes(($receipt | ConvertTo-Json -Compress)))).Replace('-','') } finally { $hasher.Dispose() }
    if ($config.description -cne ('RiftReader2 user helper; registration SHA256 ' + $hash)) { throw 'Invalid registration receipt digest.' }
}
$lab = $HelperId.Substring($HelperId.Length - 4)
$kind = if ($HelperId.StartsWith('rr2-receiver-')) { 'receiver' } else { 'controller' }
$expectedArguments = Join-HelperArguments @((Join-Path $repo ('scripts/' + $kind + '_task_entry.py')), '--lab', $lab)
function Assert-HelperContract($Exe, $ArgsLine, $Directory) {
    if ([IO.Path]::GetFileName($Exe) -ine 'pythonw.exe' -or
        (Assert-LocalPath $Exe) -ine $Exe -or (Assert-LocalPath $Directory) -ine (Assert-LocalPath $repo) -or
        $ArgsLine -cne $expectedArguments) { throw 'HELPER_CONTRACT: executable, arguments or working directory differ.' }
}
if ($transitionDescription -and (!$config -or $config.description -cne $transitionDescription)) {
    throw 'TASK_OWNERSHIP: registration changed during status retry.'
}
if ($config) { Assert-HelperContract $config.executable $config.arguments $config.workingDirectory }
if ($InspectController -or ($Action -eq 'Status' -and $config)) {
    if (!$config) { throw 'Unknown helper registration.' }
    $scheduler = New-Object -ComObject Schedule.Service
    $scheduler.Connect()
    $folder = $scheduler.GetFolder('\')
    # Only a confirmed absent or non-running task falls through to the original
    # ScheduledTasks path. Unexpected COM errors never certify absence.
    $absent = $false
    try { $current = $folder.GetTask($taskName) }
    catch {
        if ($_.Exception.GetBaseException().HResult -ne -2147024894 -or $InspectController) { throw }
        $absent = $true; $current = $null
    }
    if (!$absent -and $null -eq $current) { throw 'TASK_OWNERSHIP: task query returned no object.' }
    $initialState = if ($current) { $current.State } else { $null }
    if (!$absent -and ($null -eq $initialState -or $initialState -notin @(1,2,3,4)) -and !$InspectController) { throw 'TASK_OWNERSHIP: unrecognized task state.' }
    $retryEligible = !$InspectController -and !$absent -and $initialState -in @(1,2,3)
    if ($InspectController -or (!$absent -and $initialState -eq 4)) {
    # Refresh both names twice; only ERROR_FILE_NOT_FOUND proves legacy absence.
    $priorInstance = $null
    foreach ($observation in 1..2) {
        try {
            $null = $folder.GetTask('Workbridge Helper ' + $HelperId)
            throw 'LEGACY_OWNER: competing or ambiguous legacy registration.'
        }
        catch {
            $cause = $_.Exception.GetBaseException()
            if ($cause.HResult -ne -2147024894) { throw }
        }
        if ($observation -eq 2) { $current = $folder.GetTask($taskName) }
        if ($current.Path -cne ('\' + $taskName) -or $current.Name -cne $taskName -or $current.State -ne 4) {
            throw 'TASK_OWNERSHIP: exact root task must be running.'
        }
        $definition = $current.Definition
        if ($null -eq $definition.Actions -or $definition.Actions.Count -ne 1 -or $definition.Actions.Item(1).Type -ne 0 -or
            $null -eq $definition.Triggers -or $null -eq $definition.Triggers.Count -or $definition.Triggers.Count -ne 0) { throw 'TASK_OWNERSHIP: expected one Exec action and no triggers.' }
        $execAction = $definition.Actions.Item(1)
        # Adapt ITaskDefinition to the same assertions used by ScheduledTasks.
        $task = [pscustomobject]@{
            TaskPath='\'; TaskName=$current.Name; Description=$definition.RegistrationInfo.Description
            Actions=@([pscustomobject]@{Execute=$execAction.Path; Arguments=$execAction.Arguments; WorkingDirectory=$execAction.WorkingDirectory})
            Principal=$definition.Principal; Triggers=@(); Settings=$definition.Settings
        }
        Assert-OwnedHelperTask $task $config
        $instance = Get-TaskInstanceIdentity $current
        if ($priorInstance -and ($priorInstance.enginePid -ne $instance.enginePid -or
            $priorInstance.instanceGuid -cne $instance.instanceGuid)) { throw 'TASK_INSTANCE: identity changed during inspection.' }
        $priorInstance = $instance
    }
    $lastTaskResult = $current.LastTaskResult
    if ($null -eq $lastTaskResult) { throw 'TASK_OWNERSHIP: task result unavailable.' }
    $output = [ordered]@{helperId=$HelperId; taskName=$taskName; state='Running'; runLevel='Limited';
        atLogon=$config.atLogon; lastTaskResult=$(if ($InspectController) { $lastTaskResult } else { [long]$lastTaskResult -band 0xffffffffL }); registration=$configPath;
        enginePid=$instance.enginePid; instanceGuid=$instance.instanceGuid}
    if (!$InspectController) { $output.note = 'Task state is not application health. Inspect the helper heartbeat/output; no elevation is granted.' }
    $output | ConvertTo-Json
    return
    }
}
Import-Module (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules/ScheduledTasks') -ErrorAction Stop
$tasks = @(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop)
$matches = @($tasks | Where-Object { $_.TaskName -ieq $taskName })
if ($matches.Count -gt 1) { throw 'TASK_COLLISION: duplicate task names.' }
$task = if ($matches.Count) { $matches[0] } else { $null }
$legacy = @($tasks | Where-Object { $_.TaskName -ieq ('Workbridge Helper ' + $HelperId) })
if ($legacy.Count) {
    throw 'LEGACY_OWNER: existing legacy registration requires an explicit ownership handoff.'
}
if ($Action -eq 'Register') {
    if (!$Executable -or !$WorkingDirectory) { throw 'Register needs absolute Executable and WorkingDirectory.' }
    $exe = Assert-LocalPath $Executable
    $cwd = Assert-LocalPath $WorkingDirectory
    if (!(Test-Path -LiteralPath $exe -PathType Leaf) -or [IO.Path]::GetExtension($exe) -ine '.exe') { throw 'Use an installed native .exe, or explicitly invoke an interpreter.' }
    if (!(Test-Path -LiteralPath $cwd -PathType Container)) { throw 'WorkingDirectory must exist.' }
    if ($Argument.Count -gt 100) { throw 'Too many arguments.' }
    $line = Join-HelperArguments $Argument
    Assert-HelperContract $exe $line $cwd
    $candidate = [ordered]@{schema=1; helperId=$HelperId; ownerSid=$sid; taskName=$taskName; executable=$exe; arguments=$line; workingDirectory=$cwd; atLogon=$false}
    $bytes = [Text.Encoding]::UTF8.GetBytes(($candidate | ConvertTo-Json -Compress))
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace('-','') } finally { $hasher.Dispose() }
    $candidate.description = 'RiftReader2 user helper; registration SHA256 ' + $digest
    if ($config -and $config.description -cne $candidate.description) { throw 'REGISTRATION_CONFLICT: remove the previous registration before changing it.' }
    if ($task -and !$config) { throw 'TASK_COLLISION: an existing task has this name; it was not modified.' }
    if ($task) { Assert-OwnedHelperTask $task $candidate }
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    Write-Registration $configPath $candidate
    $config = [pscustomobject]$candidate
    if (!$task) {
        $definition = @{
            TaskName=$taskName; TaskPath='\'
            Action=(New-ScheduledTaskAction -Execute $exe -Argument $line -WorkingDirectory $cwd)
            Principal=(New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited)
            Settings=(New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew)
            Description=$config.description
        }
        Register-ScheduledTask @definition | Out-Null
        $task = Get-ScheduledTask -TaskPath '\' -TaskName $taskName
    }
} elseif (!$config) { throw 'Unknown helper registration.' }

if ($task) { Assert-OwnedHelperTask $task $config }
if ($Action -eq 'Start') {
    if (!$task) { throw 'Task is not registered.' }
    if ($task.State -ne 'Running') { Start-ScheduledTask -TaskPath '\' -TaskName $taskName }
}
$tasks = @(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop)
if (@($tasks | Where-Object { $_.TaskName -ieq ('Workbridge Helper ' + $HelperId) }).Count) { throw 'LEGACY_OWNER: existing legacy registration requires an explicit ownership handoff.' }
$matches = @($tasks | Where-Object { $_.TaskName -ieq $taskName })
if ($matches.Count -gt 1) { throw 'TASK_COLLISION: duplicate task names.' }
$task = if ($matches.Count) { $matches[0] } else { $null }
if ($task) { Assert-OwnedHelperTask $task $config }
# A task becoming Running after the initial COM probe needs a fresh two-read proof.
if ($Action -eq 'Status' -and $task -and $task.State -eq 'Running') {
    if ($retryEligible) {
        $transitionDescription = $config.description
        continue
    }
    throw 'TASK_INSTANCE: task appeared after absence during status.'
}
if ($transitionDescription) { throw 'TASK_INSTANCE: running state lost during status retry.' }
$instance = $null
$info = if ($task) { Get-ScheduledTaskInfo -TaskPath '\' -TaskName $taskName } else { $null }
[ordered]@{
    helperId=$HelperId; taskName=$taskName; state=$(if ($task) { [string]$task.State } else { 'NotRegistered' })
    runLevel=$(if ($task) { 'Limited' } else { $null })
    lastTaskResult=$(if ($info) { $info.LastTaskResult } else { $null })
    atLogon=$config.atLogon; registration=$configPath
    enginePid=$(if ($instance) { $instance.enginePid } else { $null }); instanceGuid=$(if ($instance) { $instance.instanceGuid } else { $null })
    note='Task state is not application health. Inspect the helper heartbeat/output; no elevation is granted.'
} | ConvertTo-Json

return
}
throw 'TASK_INSTANCE: state changed during status; retry limit exceeded.'
