[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$ResultPath,
    [Parameter(Mandatory)][ValidateRange(1,65535)][int]$ExpectedPort,
    [Parameter(Mandatory)][ValidatePattern('^RIFT-LAB-[12]$')][string]$ExpectedMachine
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$taskName = 'RiftReader2 OnDemand Control Agent'
$description = 'RiftReader2 on-demand guest control agent; no automatic trigger'
$report = [ordered]@{
    schemaVersion = 1; state = 'blocked'; errorCode = $null
    taskName = $taskName; noAutomaticTrigger = $true
    session = (Get-Process -Id $PID).SessionId
    created = $false; started = $false
}

function Require-Rr2($condition, [string]$reason) {
    if (-not $condition) { throw $reason }
}
function Get-Rr2Sha([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}
try {
    $canonical = 'C:\RIFT_TRANSFER\RiftReader2Control\managed-fleet-20261029'
    Require-Rr2 ($Root -ieq $canonical) 'unknown-guest-agent-root'
    Require-Rr2 ($env:COMPUTERNAME -ieq $ExpectedMachine) 'guest-machine-mismatch'
    $launcher = Join-Path $Root 'Start-GuestAgentLauncher.ps1'
    Require-Rr2 (Test-Path -LiteralPath $launcher -PathType Leaf) 'launcher-missing'
    Require-Rr2 ((Get-Rr2Sha $launcher) -eq '981E31C061CAFCEE1546DAC4FE6E68A49BF7C2010E0D5D810B2172688A013746') 'launcher-hash-mismatch'
    $profile = Get-Content -LiteralPath (Join-Path $Root 'config-template.private.json') -Raw | ConvertFrom-Json
    Require-Rr2 ($profile.port -eq $ExpectedPort -and $profile.expectedMachineName -ieq $ExpectedMachine -and
                 $profile.hostAddress -eq '192.168.56.1') 'guest-profile-mismatch'
    Require-Rr2 (Test-Path -LiteralPath $profile.executablePath -PathType Leaf) 'game-executable-missing'
    Require-Rr2 ((Get-Rr2Sha $profile.executablePath) -eq $profile.executableSha256) 'game-executable-hash-mismatch'
    & $launcher -Root $Root -ValidateOnly | Out-Null
    $stateFile = Join-Path $Root 'launcher-state.json'
    if (Test-Path -LiteralPath $stateFile) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        if ($state.runDirectory) {
            Require-Rr2 ($state.runDirectory.StartsWith($Root + '\runs\', [StringComparison]::OrdinalIgnoreCase)) 'prior-run-path-invalid'
            Require-Rr2 (-not (Test-Path -LiteralPath (Join-Path $state.runDirectory 'pending.json'))) 'prior-input-uncertain'
        }
    }
    $game = @(Get-Process -Name rift_x64 -ErrorAction SilentlyContinue)
    $explorer = @(Get-Process -Name explorer -ErrorAction SilentlyContinue)
    Require-Rr2 ($game.Count -eq 1 -and $game[0].SessionId -gt 0 -and
                 @($explorer | Where-Object SessionId -eq $game[0].SessionId).Count -gt 0) 'interactive-game-unavailable'
    Require-Rr2 (@(Get-Process -Name RiftReader2.Live -ErrorAction SilentlyContinue).Count -eq 0) 'agent-already-present'
    $launchers = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Root) -and
            $_.CommandLine.Contains('Start-GuestAgentLauncher.ps1') })
    Require-Rr2 ($launchers.Count -eq 0) 'launcher-already-present'

    Import-Module (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\Modules\ScheduledTasks') -ErrorAction Stop
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $exe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "' + $launcher + '" -Root "' + $Root + '"'
    $task = Get-ScheduledTask -TaskPath '\' -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        $taskSid = if ($task.Principal.UserId -match '^S-1-') { $task.Principal.UserId } else {
            (New-Object Security.Principal.NTAccount($task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value
        }
        $triggers = @($task.Triggers | Where-Object { $null -ne $_ })
        Require-Rr2 ($task.TaskPath -ceq '\' -and $task.TaskName -ceq $taskName -and
            $task.Description -ceq $description -and @($task.Actions).Count -eq 1 -and
            $task.Actions.Execute -ieq $exe -and $task.Actions.Arguments -ceq $arguments -and
            $task.Actions.WorkingDirectory -ieq $Root -and $taskSid -eq $sid -and
            [int]$task.Principal.LogonType -eq 3 -and [int]$task.Principal.RunLevel -eq 0 -and
            $triggers.Count -eq 0 -and $task.Settings.ExecutionTimeLimit -ceq 'PT0S' -and
            [int]$task.Settings.MultipleInstances -eq 2 -and $task.Settings.Enabled) 'task-registration-collision'
    } else {
        $definition = @{
            TaskPath = '\'; TaskName = $taskName
            Action = (New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $Root)
            Principal = (New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited)
            Settings = (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew)
            Description = $description
        }
        Register-ScheduledTask @definition | Out-Null
        $report.created = $true
        $task = Get-ScheduledTask -TaskPath '\' -TaskName $taskName
    }
    if ($task.State -ne 'Running') {
        Start-ScheduledTask -TaskPath '\' -TaskName $taskName
        $report.started = $true
    }
    $report.state = 'accepted'
} catch {
    $known = @('unknown-guest-agent-root','guest-machine-mismatch','launcher-missing','launcher-hash-mismatch',
               'guest-profile-mismatch','game-executable-missing','game-executable-hash-mismatch',
               'prior-run-path-invalid','prior-input-uncertain','interactive-game-unavailable',
               'agent-already-present','launcher-already-present','task-registration-collision')
    $report.errorCode = if ($_.Exception.Message -in $known) { $_.Exception.Message } else { 'guest-task-command-failed' }
} finally {
    [IO.File]::WriteAllText($ResultPath, ($report | ConvertTo-Json -Depth 4 -Compress), [Text.UTF8Encoding]::new($false))
}
if ($report.state -ne 'accepted') { exit 2 }
