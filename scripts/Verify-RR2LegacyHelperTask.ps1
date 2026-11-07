[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('rr2-receiver-lab1','rr2-receiver-lab2','rr2-controller-lab1','rr2-controller-lab2')][string]$HelperId,
    [Parameter(Mandatory)][string]$Executable
)
# Compatibility inspection only: never invokes Workbridge code or changes a task.
$ErrorActionPreference = 'Stop'
function Read-LegacyRegistration([string]$Path) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        if ($stream.Length -gt 65536) { throw 'legacy-registration-too-large' }
        $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true)
        try { $value = $reader.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
    if ($null -eq $value -or $value.GetType().FullName -cne 'System.Management.Automation.PSCustomObject') { throw 'legacy-registration-invalid' }
    return $value
}
function Assert-LegacyHelper($Task, $Config, $Expected, [string]$Sid) {
    foreach ($name in $Expected.Keys) {
        $actual = $Config.PSObject.Properties[$name]
        if ($null -eq $actual -or ($name -eq 'schema' -and $actual.Value -isnot [int] -and $actual.Value -isnot [long]) -or ($name -ne 'schema' -and ($null -eq $actual.Value -or $actual.Value.GetType() -ne $Expected[$name].GetType())) -or $actual.Value -cne $Expected[$name]) { throw 'legacy-registration-mismatch' }
    }
    if (@($Config.PSObject.Properties).Count -ne $Expected.Count) { throw 'legacy-registration-mismatch' }
    $principalSid = $Task.Principal.UserId
    if ($principalSid -notmatch '^S-1-') {
        $principalSid = ([Security.Principal.NTAccount]::new($principalSid)).Translate([Security.Principal.SecurityIdentifier]).Value
    }
    $settings = $Task.Settings
    if ($Task.TaskPath -cne '\' -or $Task.TaskName -cne $Expected.taskName -or
        $Task.Description -cne $Expected.description -or $Task.State -cne 'Running' -or
        @($Task.Actions).Count -ne 1 -or $Task.Actions.Execute -ine $Expected.executable -or
        [string]$Task.Actions.Arguments -cne $Expected.arguments -or
        $Task.Actions.WorkingDirectory -ine $Expected.workingDirectory -or
        $principalSid -cne $Sid -or [int]$Task.Principal.RunLevel -ne 0 -or
        [int]$Task.Principal.LogonType -ne 3 -or @($Task.Triggers | Where-Object { $null -ne $_ }).Count -ne 0 -or
        $settings.ExecutionTimeLimit -cne 'PT0S' -or [int]$settings.MultipleInstances -ne 2 -or
        $settings.Enabled -ne $true -or $settings.DisallowStartIfOnBatteries -ne $false -or
        $settings.StopIfGoingOnBatteries -ne $false -or $settings.RestartCount -ne 0) { throw 'legacy-task-ownership-refused' }
}
function Get-LegacyTask([string]$Id) {
    # Access denied and query failure throw; only successful enumeration is authoritative.
    $tasks = @(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop)
    $legacy = @($tasks | Where-Object TaskName -IEQ ('Workbridge Helper ' + $Id))
    $new = @($tasks | Where-Object TaskName -IEQ ('RiftReader2 Helper ' + $Id))
    if ($legacy.Count -ne 1 -or $new.Count -ne 0) { throw 'legacy-owner-absent-or-ambiguous' }
    return $legacy[0]
}
Import-Module (Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules/ScheduledTasks') -ErrorAction Stop
$repo = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
if (![IO.Path]::IsPathRooted($Executable) -or [IO.Path]::GetFileName($Executable) -ine 'pythonw.exe' -or !(Test-Path -LiteralPath $Executable -PathType Leaf -ErrorAction Stop)) { throw 'legacy-executable-invalid' }
$exe = [IO.Path]::GetFullPath($Executable)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$parts = $HelperId.Split('-')
$entry = Join-Path $repo ('scripts/' + $parts[1] + '_task_entry.py')
# Fixed arguments contain no user text. Quote each native argument exactly as legacy registration did.
$arguments = '"' + $entry + '" "--lab" "' + $parts[2] + '"'
$expected = [ordered]@{schema=1; helperId=$HelperId; ownerSid=$sid; taskName=('Workbridge Helper ' + $HelperId); executable=$exe; arguments=$arguments; workingDirectory=$repo; atLogon=$false}
$hasher = [Security.Cryptography.SHA256]::Create()
try { $digest = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes(($expected | ConvertTo-Json -Compress)))).Replace('-','') } finally { $hasher.Dispose() }
$expected.description = 'Workbridge user helper; registration SHA256 ' + $digest
$legacyTask = Get-LegacyTask $HelperId
$config = Read-LegacyRegistration (Join-Path 'C:\work\workbridge-mcp\.local\helpers' ($HelperId + '/registration.json'))
Assert-LegacyHelper $legacyTask $config $expected $sid
[ordered]@{helperId=$HelperId; taskName=$expected.taskName; state='Running'; atLogon=$false; runLevel='Limited'; ownership='verified-legacy-read-only'} | ConvertTo-Json -Compress
