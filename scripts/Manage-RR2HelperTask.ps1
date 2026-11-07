[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Register','Start','Status')][string]$Action,
    [Parameter(Mandatory)][ValidateSet('rr2-receiver-lab1','rr2-receiver-lab2','rr2-controller-lab1','rr2-controller-lab2')][string]$HelperId,
    [string]$Executable,
    [string[]]$Argument = @(),
    [string]$WorkingDirectory
)
$ErrorActionPreference = 'Stop'
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
Import-Module (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules/ScheduledTasks') -ErrorAction Stop
$repo = Split-Path -Parent $PSScriptRoot
$state = Assert-LocalPath (Join-Path $repo ('.local/rr2-helpers/' + $HelperId))
$configPath = Assert-LocalPath (Join-Path $state 'registration.json')
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
    $settingsMatch = $Task.Settings.ExecutionTimeLimit -ceq 'PT0S' -and
        [int]$Task.Settings.MultipleInstances -eq 2 -and $Task.Settings.Enabled -and
        !$Task.Settings.DisallowStartIfOnBatteries -and !$Task.Settings.StopIfGoingOnBatteries -and
        $Task.Settings.RestartCount -eq 0
    if ($Task.TaskPath -cne '\' -or $Task.TaskName -cne $taskName -or
        $Task.Description -cne $Config.description -or @($Task.Actions).Count -ne 1 -or
        $Task.Actions.Execute -ine $Config.executable -or
        [string]$Task.Actions.Arguments -cne [string]$Config.arguments -or
        $Task.Actions.WorkingDirectory -ine $Config.workingDirectory -or
        $taskSid -ine $sid -or [int]$Task.Principal.RunLevel -ne 0 -or
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
if ($config) { Assert-HelperContract $config.executable $config.arguments $config.workingDirectory }
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
$info = if ($task) { Get-ScheduledTaskInfo -TaskPath '\' -TaskName $taskName } else { $null }
[ordered]@{
    helperId=$HelperId; taskName=$taskName; state=$(if ($task) { [string]$task.State } else { 'NotRegistered' })
    runLevel=$(if ($task) { 'Limited' } else { $null })
    lastTaskResult=$(if ($info) { $info.LastTaskResult } else { $null })
    atLogon=$config.atLogon; registration=$configPath
    note='Task state is not application health. Inspect the helper heartbeat/output; no elevation is granted.'
} | ConvertTo-Json
