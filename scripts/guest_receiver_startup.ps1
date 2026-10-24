# Receiver bootstrap only: no game input, elevation, service or credential storage.
[CmdletBinding()]
param(
    [ValidateSet('Install','Run','Status','Remove')][string]$Mode = 'Status',
    [string]$Manifest,
    [string]$ReceiverPath,
    [string]$ConfigPath,
    [string]$ExpectedReceiverSha256,
    [string]$ExpectedMachineName,
    [ValidateRange(0,43200)][int]$WaitSeconds = 43200
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Use this interpreter's inbox modules, not an inherited PowerShell 7 module path.
foreach ($module in @('Microsoft.PowerShell.Utility','Microsoft.PowerShell.Management','CimCmdlets')) {
    Import-Module (Join-Path $PSHOME ('Modules\'+$module+'\'+$module+'.psd1')) -ErrorAction Stop
}

function Assert-RR2File([string]$Path, [string]$Hash) {
    if (-not [IO.Path]::IsPathRooted($Path) -or $Hash -notmatch '^[a-fA-F0-9]{64}$') { throw 'invalid-file-pin' }
    $f = Get-Item -LiteralPath $Path -Force
    if ($f.PSIsContainer -or ($f.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'nonregular-pinned-file' }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash) { throw 'pinned-file-changed' }
}
function Get-RR2Context {
    $p = Get-Process -Id $PID
    if (-not [Environment]::UserInteractive -or $p.SessionId -eq 0) { throw 'interactive-logon-required' }
    [pscustomobject]@{ machineName=$env:COMPUTERNAME; ownerSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; sessionId=$p.SessionId }
}
function Read-RR2Manifest([string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path)) { throw 'absolute-manifest-required' }
    $f = Get-Item -LiteralPath $Path
    if ($f.Length -gt 16384 -or $f.PSIsContainer -or ($f.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'invalid-manifest-file' }
    $m = [IO.File]::ReadAllText($Path) | ConvertFrom-Json
    $fields = @('schemaVersion','installationId','ownerSid','machineName','receiverPath','receiverSha256','configPath','configSha256','gamePath','gameSha256','launcherPath','launcherSha256','stateDirectory')
    if ($m.schemaVersion -ne 1 -or (Compare-Object @($m.PSObject.Properties.Name | Sort-Object) @($fields | Sort-Object))) { throw 'invalid-manifest-schema' }
    $c = Get-RR2Context
    if ($m.machineName -ne $c.machineName -or $m.ownerSid -ne $c.ownerSid) { throw 'installation-owner-mismatch' }
    if ([IO.Path]::GetFullPath($m.stateDirectory) -ne [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))) { throw 'manifest-location-mismatch' }
    Assert-RR2File $m.launcherPath $m.launcherSha256
    Assert-RR2File $m.receiverPath $m.receiverSha256
    Assert-RR2File $m.configPath $m.configSha256
    return $m
}
function Get-RR2Processes {
    $rows = @(Get-CimInstance Win32_Process -Filter "Name='rift_x64.exe' OR Name='RiftReader2.Live.exe'")
    $result = @()
    foreach ($row in $rows) {
        $p = Get-Process -Id $row.ProcessId
        if (-not $row.ExecutablePath -or -not $row.CommandLine -or $p.Path -ne $row.ExecutablePath) { throw 'process-inspection-unavailable' }
        $result += [pscustomobject]@{ name=$row.Name; pid=[int]$row.ProcessId; path=$p.Path; commandLine=$row.CommandLine; sessionId=$p.SessionId; window=[long]$p.MainWindowHandle; startUtc=$p.StartTime.ToUniversalTime().ToString('o') }
    }
    return $result
}
function Select-RR2LaunchDecision($Spec, $Context, [object[]]$Processes) {
    if ($Spec.machineName -ne $Context.machineName -or $Spec.ownerSid -ne $Context.ownerSid -or $Context.sessionId -le 0) { throw 'interactive-owner-mismatch' }
    $agents = @($Processes | Where-Object { $_.name -ieq 'RiftReader2.Live.exe' -and $_.commandLine -match '(?i)(^|\s)control-agent(\s|$)' })
    if ($agents.Count -gt 1) { throw 'multiple-receivers' }
    if ($agents.Count -eq 1) {
        $a = $agents[0]
        $r = [regex]::Escape($Spec.receiverPath); $c = [regex]::Escape($Spec.configPath)
        $exact = '^\s*(?:"' + $r + '"|' + $r + ')\s+control-agent\s+--config\s+(?:"' + $c + '"|' + $c + ')\s*$'
        if ($a.path -ine $Spec.receiverPath -or $a.sessionId -ne $Context.sessionId -or $a.commandLine -inotmatch $exact) { throw 'existing-receiver-conflict' }
        return [pscustomobject]@{ state='already-running'; receiverPid=$a.pid; receiverStartUtc=$a.startUtc }
    }
    $games = @($Processes | Where-Object { $_.name -ieq 'rift_x64.exe' })
    if ($games.Count -gt 1) { throw 'multiple-game-processes' }
    if ($games.Count -eq 0) { return [pscustomobject]@{ state='waiting-for-game' } }
    $g = $games[0]
    if ($g.path -ine $Spec.gamePath -or $g.sessionId -ne $Context.sessionId) { throw 'game-identity-conflict' }
    if ($g.window -eq 0) { return [pscustomobject]@{ state='waiting-for-game-window' } }
    return [pscustomobject]@{ state='start'; gamePid=$g.pid; gameStartUtc=$g.startUtc }
}
function Publish-RR2State($Spec, [string]$State, $Details) {
    $c = Get-RR2Context
    $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
    $v = [ordered]@{ schemaVersion=1; installationId=$Spec.installationId; observedUtc=[DateTime]::UtcNow.ToString('o'); bootUtc=$boot; machineName=$c.machineName; ownerSid=$c.ownerSid; sessionId=$c.sessionId; state=$State; details=$Details; connectionVerified=$false }
    $json = $v | ConvertTo-Json -Depth 6 -Compress
    $dest = Join-Path $Spec.stateDirectory 'status.json'; $tmp = $dest + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($tmp,$json,[Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $dest) { [IO.File]::Replace($tmp,$dest,[NullString]::Value) } else { [IO.File]::Move($tmp,$dest) }
    # Diagnostic only. GuestInfo failure must not prevent a local receiver launch.
    $tool = Join-Path $env:ProgramFiles 'VMware\VMware Tools\vmtoolsd.exe'
    if (Test-Path -LiteralPath $tool) {
        $child = $null
        try {
            $value = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
            $si = [Diagnostics.ProcessStartInfo]::new($tool, '--cmd "info-set guestinfo.rr2.receiver-startup ' + $value + '"')
            $si.UseShellExecute=$false; $si.CreateNoWindow=$true; $si.RedirectStandardOutput=$true; $si.RedirectStandardError=$true
            $child = [Diagnostics.Process]::Start($si)
            if (-not $child.WaitForExit(3000)) { $child.Kill(); $child.WaitForExit() }
        } catch { } finally { if ($null -ne $child) { $child.Dispose() } }
    }
    return [pscustomobject]$v
}
function Get-RR2ShortcutPath { Join-Path ([Environment]::GetFolderPath('Startup')) 'RiftReader2 Receiver.lnk' }
function Get-RR2Arguments([string]$ManifestPath, [string]$LauncherPath) {
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $LauncherPath + '" -Mode Run -Manifest "' + $ManifestPath + '"'
}
function Install-RR2Startup {
    $c = Get-RR2Context
    if ($ExpectedMachineName -ne $c.machineName) { throw 'wrong-guest-machine' }
    Assert-RR2File $ReceiverPath $ExpectedReceiverSha256
    $cfgFile=Get-Item -LiteralPath $ConfigPath
    if (-not [IO.Path]::IsPathRooted($ConfigPath) -or $cfgFile.Length -gt 65536 -or ($cfgFile.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'invalid-guest-config' }
    $cfg=[IO.File]::ReadAllText($ConfigPath) | ConvertFrom-Json
    if ($cfg.schemaVersion -ne 1 -or $cfg.expectedMachineName -ne $c.machineName -or $cfg.processName -ne 'rift_x64') { throw 'guest-config-binding-mismatch' }
    Assert-RR2File $cfg.executablePath $cfg.executableSha256
    $source=$script:RR2SourcePath; $hash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $dir=Join-Path $env:LOCALAPPDATA ('RiftReader2\ReceiverStartup\'+$hash.Substring(0,16))
    $target=Join-Path $dir 'guest_receiver_startup.ps1'; $specPath=Join-Path $dir 'manifest.json'; $link=Get-RR2ShortcutPath
    $shell=New-Object -ComObject WScript.Shell
    if (Test-Path -LiteralPath $link) {
        $prior=$shell.CreateShortcut($link)
        if ($prior.Arguments -ne (Get-RR2Arguments $specPath $target) -or $prior.TargetPath -ine (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -or $prior.WorkingDirectory -ine $dir) { throw 'startup-shortcut-conflict' }
        $old=Read-RR2Manifest $specPath
        if ($old.receiverPath -ine $ReceiverPath -or $old.configPath -ine $ConfigPath -or $old.receiverSha256 -ine $ExpectedReceiverSha256) { throw 'installation-conflict' }
        return Publish-RR2State $old 'already-installed' @{ shortcut=$link; manifest=$specPath }
    }
    if (Test-Path -LiteralPath $dir) { throw 'partial-installation-preserved' }
    [void][IO.Directory]::CreateDirectory($dir)
    [IO.File]::Copy($source,$target,$false)
    $m=[ordered]@{ schemaVersion=1; installationId=[Guid]::NewGuid().ToString('N'); ownerSid=$c.ownerSid; machineName=$c.machineName; receiverPath=[IO.Path]::GetFullPath($ReceiverPath); receiverSha256=$ExpectedReceiverSha256.ToLowerInvariant(); configPath=[IO.Path]::GetFullPath($ConfigPath); configSha256=(Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash.ToLowerInvariant(); gamePath=$cfg.executablePath; gameSha256=$cfg.executableSha256.ToLowerInvariant(); launcherPath=$target; launcherSha256=$hash; stateDirectory=$dir }
    [IO.File]::WriteAllText($specPath,($m|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
    $shortcut=$shell.CreateShortcut($link)
    $shortcut.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments=Get-RR2Arguments $specPath $target
    $shortcut.WorkingDirectory=$dir; $shortcut.WindowStyle=7
    $shortcut.Description='RiftReader2 receiver: wait for the pinned RIFT game; no gameplay input.'
    $shortcut.Save()
    return Publish-RR2State ([pscustomobject]$m) 'installed' @{ shortcut=$link; manifest=$specPath; waitSeconds=43200 }
}
function Invoke-RR2Startup([string]$SpecPath, [int]$Seconds) {
    $m=Read-RR2Manifest $SpecPath
    $name='Local\RiftReader2-Startup-'+$m.installationId
    $lock=[Threading.Mutex]::new($false,$name); $held=$false
    try {
        try { $held=$lock.WaitOne(0) } catch [Threading.AbandonedMutexException] { $held=$true }
        if (-not $held) { return Publish-RR2State $m 'launcher-already-running' @{} }
        $clock=[Diagnostics.Stopwatch]::StartNew(); $last=''
        while ($true) {
            if (Test-Path -LiteralPath (Join-Path $m.stateDirectory 'DISABLED')) { return Publish-RR2State $m 'disabled' @{} }
            $decision=Select-RR2LaunchDecision $m (Get-RR2Context) @(Get-RR2Processes)
            if ($decision.state -eq 'already-running') { return Publish-RR2State $m $decision.state $decision }
            if ($decision.state -eq 'start') {
                Assert-RR2File $m.configPath $m.configSha256
                Assert-RR2File $m.receiverPath $m.receiverSha256
                Assert-RR2File $m.gamePath $m.gameSha256
                # Re-observe after hashing. Never act on a process that changed meanwhile.
                $again=Select-RR2LaunchDecision $m (Get-RR2Context) @(Get-RR2Processes)
                if ($again.state -eq 'already-running') { return Publish-RR2State $m $again.state $again }
                if ($again.state -ne 'start' -or $again.gamePid -ne $decision.gamePid -or $again.gameStartUtc -ne $decision.gameStartUtc) { throw 'game-changed-before-start' }
                if (Test-Path -LiteralPath (Join-Path $m.stateDirectory 'DISABLED')) { return Publish-RR2State $m 'disabled' @{} }
                $stamp=[Guid]::NewGuid().ToString('N')
                $p=Start-Process -FilePath $m.receiverPath -ArgumentList ('control-agent --config "'+$m.configPath+'"') -WorkingDirectory ([IO.Path]::GetDirectoryName($m.receiverPath)) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $m.stateDirectory ($stamp+'.stdout.log')) -RedirectStandardError (Join-Path $m.stateDirectory ($stamp+'.stderr.log'))
                Start-Sleep -Milliseconds 400
                if ($p.HasExited) { throw 'receiver-exited-after-start' }
                return Publish-RR2State $m 'receiver-started' @{ receiverPid=$p.Id; receiverStartUtc=$p.StartTime.ToUniversalTime().ToString('o'); gamePid=$again.gamePid; gameStartUtc=$again.gameStartUtc }
            }
            if ($decision.state -ne $last) { [void](Publish-RR2State $m $decision.state @{}); $last=$decision.state }
            if ($clock.Elapsed.TotalSeconds -ge $Seconds) { return Publish-RR2State $m 'game-wait-expired' @{ waitSeconds=$Seconds } }
            Start-Sleep -Milliseconds 2000
        }
    } finally { if ($held) { $lock.ReleaseMutex() }; $lock.Dispose() }
}
function Remove-RR2Startup([string]$SpecPath) {
    $m=Read-RR2Manifest $SpecPath; $link=Get-RR2ShortcutPath
    if (Test-Path -LiteralPath $link) {
        $s=(New-Object -ComObject WScript.Shell).CreateShortcut($link)
        if ($s.Arguments -ne (Get-RR2Arguments $SpecPath $m.launcherPath) -or $s.TargetPath -ine (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -or $s.WorkingDirectory -ine $m.stateDirectory) { throw 'startup-shortcut-conflict' }
        [IO.File]::Delete($link)
    }
    [IO.File]::WriteAllText((Join-Path $m.stateDirectory 'DISABLED'),'Disabled by explicit remove.')
    return Publish-RR2State $m 'removed' @{ runningReceiverStopped=$false; filesRetained=$true }
}
$script:RR2SourcePath=$PSCommandPath
if ($MyInvocation.InvocationName -ne '.') {
    try {
        $answer=switch ($Mode) {
            'Install' { Install-RR2Startup }
            'Run' { Invoke-RR2Startup $Manifest $WaitSeconds }
            'Status' {
                $m=Read-RR2Manifest $Manifest
                $d=Select-RR2LaunchDecision $m (Get-RR2Context) @(Get-RR2Processes)
                Publish-RR2State $m $d.state $d
            }
            'Remove' { Remove-RR2Startup $Manifest }
        }
        $answer | ConvertTo-Json -Depth 6 -Compress
    } catch {
        # Do not publish config content or transport/OS exception strings.
        $known=@('invalid-file-pin','nonregular-pinned-file','pinned-file-changed','interactive-logon-required','absolute-manifest-required','invalid-manifest-file','invalid-manifest-schema','installation-owner-mismatch','manifest-location-mismatch','process-inspection-unavailable','interactive-owner-mismatch','multiple-receivers','existing-receiver-conflict','multiple-game-processes','game-identity-conflict','wrong-guest-machine','invalid-guest-config','guest-config-binding-mismatch','startup-shortcut-conflict','installation-conflict','partial-installation-preserved','game-changed-before-start','receiver-exited-after-start')
        $reason='startup-failed'; if ($known -contains $_.Exception.Message) { $reason=$_.Exception.Message }
        [pscustomobject]@{ state='blocked'; reason=$reason; connectionVerified=$false } | ConvertTo-Json -Compress
        exit 2
    }
}
