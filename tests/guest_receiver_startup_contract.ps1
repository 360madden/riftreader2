param([Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference='Stop'
. $Source
$script:Checks=0
function Check([bool]$Condition,[string]$Name) { if(-not $Condition){throw ('FAIL: '+$Name)}; $script:Checks++ }
function Throws([scriptblock]$Action,[string]$Reason) { $seen=$false; try { & $Action | Out-Null } catch { if($_.Exception.Message -ne $Reason){throw}; $seen=$true }; Check $seen $Reason }
$ctx=[pscustomobject]@{machineName='TEST-GUEST';ownerSid='S-1-5-21-fixture';sessionId=1}
$spec=[pscustomobject]@{machineName=$ctx.machineName;ownerSid=$ctx.ownerSid;receiverPath='C:\Receiver Space\RiftReader2.Live.exe';configPath='C:\Receiver Space\control-agent.json';gamePath='C:\RIFT\rift_x64.exe'}
$game=[pscustomobject]@{name='rift_x64.exe';path=$spec.gamePath;pid=123;sessionId=1;window=55;startUtc='2026-01-01T00:00:00Z';commandLine='rift_x64.exe'}
$agent=[pscustomobject]@{name='RiftReader2.Live.exe';path=$spec.receiverPath;pid=456;sessionId=1;window=0;startUtc='2026-01-01T00:00:01Z';commandLine='"C:\Receiver Space\RiftReader2.Live.exe" control-agent --config "C:\Receiver Space\control-agent.json"'}
Check ((Select-RR2LaunchDecision $spec $ctx @()).state -eq 'waiting-for-game') 'no game waits'
Check ((Select-RR2LaunchDecision $spec $ctx @($game)).state -eq 'start') 'one exact game starts'
$game.window=0;Check ((Select-RR2LaunchDecision $spec $ctx @($game)).state -eq 'waiting-for-game-window') 'window not ready waits';$game.window=55
Check ((Select-RR2LaunchDecision $spec $ctx @($agent)).state -eq 'already-running') 'existing receiver is retained'
Check ((Select-RR2LaunchDecision $spec $ctx @($agent,$game)).receiverPid -eq 456) 'existing receiver never duplicated'
Throws {Select-RR2LaunchDecision $spec $ctx @($game,$game)} 'multiple-game-processes'
Throws {Select-RR2LaunchDecision $spec $ctx @($agent,$agent)} 'multiple-receivers'
$game.sessionId=2;Throws {Select-RR2LaunchDecision $spec $ctx @($game)} 'game-identity-conflict';$game.sessionId=1
$game.path='C:\different\rift_x64.exe';Throws {Select-RR2LaunchDecision $spec $ctx @($game)} 'game-identity-conflict';$game.path=$spec.gamePath
$agent.sessionId=2;Throws {Select-RR2LaunchDecision $spec $ctx @($agent)} 'existing-receiver-conflict';$agent.sessionId=1
$agent.commandLine+=' extra';Throws {Select-RR2LaunchDecision $spec $ctx @($agent)} 'existing-receiver-conflict';$agent.commandLine=$agent.commandLine.Substring(0,$agent.commandLine.Length-6)
$ctx.sessionId=0;Throws {Select-RR2LaunchDecision $spec $ctx @($game)} 'interactive-owner-mismatch';$ctx.sessionId=1
$ctx.machineName='OTHER';Throws {Select-RR2LaunchDecision $spec $ctx @($game)} 'interactive-owner-mismatch';$ctx.machineName=$spec.machineName
$ctx.ownerSid='OTHER';Throws {Select-RR2LaunchDecision $spec $ctx @($game)} 'interactive-owner-mismatch';$ctx.ownerSid=$spec.ownerSid

$root=Join-Path ([IO.Path]::GetTempPath()) ('rr2-startup-test-'+[Guid]::NewGuid().ToString('N'))
$oldLocal=$env:LOCALAPPDATA;$oldProgram=$env:ProgramFiles
try {
    [void][IO.Directory]::CreateDirectory($root)
    $env:LOCALAPPDATA=$root;$env:ProgramFiles=$root
    # Only redirect the test process's per-user paths. No real Startup link is written.
    function Get-RR2ShortcutPath { Join-Path $root 'fixture-startup.lnk' }
    $ReceiverPath=Join-Path $root 'RiftReader2.Live.exe';$ConfigPath=Join-Path $root 'control-agent.json';$gp=Join-Path $root 'rift_x64.exe'
    [IO.File]::WriteAllText($ReceiverPath,'fixture receiver - never executed');[IO.File]::WriteAllText($gp,'fixture game - never executed')
    $ExpectedReceiverSha256=(Get-FileHash $ReceiverPath).Hash;$ExpectedMachineName=$env:COMPUTERNAME
    $conf=@{schemaVersion=1;expectedMachineName=$env:COMPUTERNAME;processName='rift_x64';executablePath=$gp;executableSha256=(Get-FileHash $gp).Hash;token='SECRET_MUST_NOT_BE_COPIED'}
    [IO.File]::WriteAllText($ConfigPath,($conf|ConvertTo-Json))
    Assert-RR2File $ReceiverPath $ExpectedReceiverSha256;Check $true 'exact pin accepted'
    Throws {Assert-RR2File $ReceiverPath ('0'*64)} 'pinned-file-changed'
    $one=Install-RR2Startup;Check ($one.state -eq 'installed') 'installer runs in disposable paths'
    $mp=$one.details.manifest;$m=Read-RR2Manifest $mp
    Check (([IO.File]::ReadAllText($mp)) -notmatch 'SECRET_MUST_NOT_BE_COPIED') 'no secret in manifest'
    Check (Test-Path -LiteralPath (Get-RR2ShortcutPath)) 'real COM shortcut exists only in fixture'
    $link=(New-Object -ComObject WScript.Shell).CreateShortcut((Get-RR2ShortcutPath))
    Check ($link.Arguments -eq (Get-RR2Arguments $mp $m.launcherPath)) 'shortcut launches tested entrypoint'
    Check ($link.TargetPath -ieq (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')) 'shortcut uses builtin interactive powershell'
    $repeat=Install-RR2Startup;Check ($repeat.state -eq 'already-installed') 'repeat install does not overwrite'
    $priorTarget=$link.TargetPath;$link.TargetPath=Join-Path $env:SystemRoot 'System32\cmd.exe';$link.Save()
    Throws {Install-RR2Startup} 'startup-shortcut-conflict'
    Throws {Remove-RR2Startup $mp} 'startup-shortcut-conflict'
    Check (Test-Path (Get-RR2ShortcutPath)) 'changed shortcut is preserved'
    $link.TargetPath=$priorTarget;$link.Save()
    $saved=[IO.File]::ReadAllBytes($ConfigPath);[IO.File]::AppendAllText($ConfigPath,' ')
    Throws {Read-RR2Manifest $mp} 'pinned-file-changed';[IO.File]::WriteAllBytes($ConfigPath,$saved)
    $actualContext=Get-RR2Context
    $script:FakeProcesses=@();$script:Starts=0
    function Get-RR2Processes { return $script:FakeProcesses }
    function Start-Process { param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,[switch]$PassThru,$RedirectStandardOutput,$RedirectStandardError)
        $script:Starts++;Check ($FilePath -eq $m.receiverPath) 'only pinned executable launched';Check ($ArgumentList -eq ('control-agent --config "'+$m.configPath+'"')) 'no arbitrary launch arguments'
        [pscustomobject]@{HasExited=$false;Id=777;StartTime=[DateTime]::UtcNow}
    }
    $out=Invoke-RR2Startup $mp 0;Check ($out.state -eq 'game-wait-expired' -and $script:Starts -eq 0) 'absent game cannot launch'
    $script:FakeProcesses=@([pscustomobject]@{name='rift_x64.exe';path=$m.gamePath;pid=123;sessionId=$actualContext.sessionId;window=55;startUtc='2026-01-01T00:00:00Z';commandLine='fixture'})
    $out=Invoke-RR2Startup $mp 0;Check ($out.state -eq 'receiver-started' -and $script:Starts -eq 1 -and -not $out.connectionVerified) 'one launch is not claimed as connection'
    $script:FakeProcesses+= [pscustomobject]@{name='RiftReader2.Live.exe';path=$m.receiverPath;pid=777;sessionId=$actualContext.sessionId;window=0;startUtc='2026-01-01T00:00:01Z';commandLine=('"'+$m.receiverPath+'" control-agent --config "'+$m.configPath+'"')}
    $out=Invoke-RR2Startup $mp 0;Check ($out.state -eq 'already-running' -and $script:Starts -eq 1) 'repeated invocation never launches another receiver'
    $out=Remove-RR2Startup $mp;Check ($out.state -eq 'removed') 'explicit removal works'
    Check (-not (Test-Path (Get-RR2ShortcutPath))) 'removal deletes only owned shortcut'
    Check (Test-Path $m.launcherPath) 'removal retains evidence and code'
    $out=Invoke-RR2Startup $mp 0;Check ($out.state -eq 'disabled' -and $script:Starts -eq 1) 'removed startup cannot restart receiver'
    Check (Test-Path $ReceiverPath) 'existing binary untouched'
    Check ([IO.File]::ReadAllText($ReceiverPath) -eq 'fixture receiver - never executed') 'binary bytes preserved'
    $status=[IO.File]::ReadAllText((Join-Path $m.stateDirectory 'status.json'))|ConvertFrom-Json
    Check ($status.state -eq 'disabled' -and -not $status.connectionVerified) 'durable status is explicit'
} finally {
    $env:LOCALAPPDATA=$oldLocal;$env:ProgramFiles=$oldProgram
    if ($root -notlike ([IO.Path]::GetTempPath()+'rr2-startup-test-*')) { throw 'unexpected-fixture-path' }
    Remove-Item -LiteralPath $root -Recurse -Force
}
[pscustomobject]@{passed=$true;checks=$script:Checks;realGuestAccess=$false;realStartupChanged=$false;receiverExecuted=$false}|ConvertTo-Json -Compress
