param([Parameter(Mandatory)][string]$Root, [switch]$InstallStartup, [switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Record($path, $value) {
    $temp = $path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($temp, ($value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $path) {
        # Windows PowerShell 5 converts a null string argument into an empty path.
        $backup = $temp + '.bak'
        [IO.File]::Replace($temp, $path, $backup)
        [IO.File]::Delete($backup)
    }
    else { [IO.File]::Move($temp, $path) }
}
function Read-Record($path) { Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
function Get-Sha256($path) {
    $stream = [IO.File]::OpenRead($path); $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $hash.Dispose() }
}
function Assert-Release($release) {
    if (@($release.PSObject.Properties.Name).Count -ne 2 -or
        $release.release -notmatch '^[a-z0-9-]{1,64}$' -or $release.sha256 -notmatch '^[A-Fa-f0-9]{64}$') {
        throw 'invalid-release'
    }
    $directory = Join-Path (Join-Path $Root 'releases') $release.release
    $exe = Join-Path $directory 'RiftReader2.Live.exe'
    foreach ($path in @($Root, (Join-Path $Root 'releases'), $directory, $exe)) {
        if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'linked-release-refused' }
    }
    if ((Get-Sha256 $exe) -ne $release.sha256) { throw 'release-hash-mismatch' }
    return $exe
}
function Write-State($state) {
    Write-Record (Join-Path $Root 'launcher-state.json') @{
        state = $state; launcherPid = $PID; sessionId = (Get-Process -Id $PID).SessionId
        agentPid = $(if ($null -ne $script:agent) { $script:agent.Id } else { $null })
        agentStartTicks = $script:agentStartTicks
        runDirectory = $script:runDirectory; release = $script:release; utc = [DateTime]::UtcNow.ToString('o')
    }
}
function Stop-Agent {
    if ($null -eq $script:agent) { return }
    if (-not $script:agent.HasExited) {
        [IO.File]::WriteAllText((Join-Path $script:runDirectory 'shutdown.request'), 'launcher shutdown')
        if (-not $script:agent.WaitForExit(15000)) { throw 'agent-shutdown-timeout' }
    }
    $receipt = Read-Record (Join-Path $script:runDirectory 'shutdown-complete.json')
    if (-not $receipt.clean -or $receipt.processId -ne $script:agent.Id -or
        $receipt.processStartUtcTicks -ne $script:agentStartTicks -or
        (Test-Path -LiteralPath (Join-Path $script:runDirectory 'pending.json'))) { throw 'agent-cleanup-unverified' }
    $script:agent.Dispose(); $script:agent = $null
    Write-State 'stopped'
}
function Start-Agent($next) {
    $exe = Assert-Release $next
    if ($null -ne $script:agent) { throw 'agent-already-owned' }
    $script:runDirectory = Join-Path (Join-Path $Root 'runs') ([Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $script:runDirectory | Out-Null
    $config = Read-Record (Join-Path $Root 'config-template.private.json')
    $config.outputDirectory = $script:runDirectory
    $configPath = Join-Path $script:runDirectory 'agent.private.json'
    Write-Record $configPath $config
    $script:agent = Start-Process -FilePath $exe -ArgumentList @('control-agent', '--config', ('"' + $configPath + '"')) -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $script:runDirectory 'stdout.private.log') -RedirectStandardError (Join-Path $script:runDirectory 'stderr.private.log')
    $script:agentStartTicks = $script:agent.StartTime.ToUniversalTime().Ticks
    $script:release = $next
    Write-State 'starting'
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $readyPath = Join-Path $script:runDirectory 'ready.json'
    while (-not (Test-Path -LiteralPath $readyPath)) {
        if ($script:agent.HasExited) { throw 'agent-start-exited' }
        if ([DateTime]::UtcNow -ge $deadline) { throw 'agent-ready-timeout' }
        Start-Sleep -Milliseconds 100
    }
    $ready = Read-Record $readyPath
    if ($ready.processId -ne $script:agent.Id -or $ready.processStartUtcTicks -ne $script:agentStartTicks -or
        $ready.gracefulShutdownVersion -ne 1 -or $script:agent.HasExited) { throw 'agent-readiness-mismatch' }
    Write-State 'running'
}

if (-not [IO.Path]::IsPathRooted($Root) -or $Root.StartsWith('\\') -or $Root -match '["\r\n]') { throw 'invalid-launcher-root' }
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
$initial = Read-Record (Join-Path $Root 'current.json')
$null = Assert-Release $initial
if ($ValidateOnly) { Write-Output 'Release hash and paths verified; no process started'; return }
$script:agent = $null; $script:release = $initial; $script:runDirectory = $null; $script:agentStartTicks = 0
$nameHash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant()))).Replace('-', '')
$mutex = [Threading.Mutex]::new($false, ('Local\RiftReader2-AgentLauncher-' + $nameHash.Substring(0,16)))
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { throw 'launcher-already-running' }
    foreach ($directory in @('runs','results')) { New-Item -ItemType Directory -Path (Join-Path $Root $directory) -Force | Out-Null }
    $statePath = Join-Path $Root 'launcher-state.json'
    if (Test-Path -LiteralPath $statePath) {
        $prior = Read-Record $statePath
        if ($prior.runDirectory -and (Test-Path -LiteralPath (Join-Path $prior.runDirectory 'pending.json'))) { throw 'prior-release-uncertain' }
    }
    if ($InstallStartup) {
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'RiftReader2 Agent.lnk'))
        $shortcut.TargetPath = Join-Path $Root 'Launch-Agent.cmd'; $shortcut.WorkingDirectory = $Root; $shortcut.WindowStyle = 7; $shortcut.Save()
    }
    Start-Agent $initial
    $exitRequested = $false
    while (-not $exitRequested) {
        $requestPath = Join-Path $Root 'request.json'
        if (Test-Path -LiteralPath $requestPath) {
            $request = Read-Record $requestPath
            if ($request.id -notmatch '^[a-f0-9]{32}$' -or $request.operation -notin @('start','stop','restart','update','exit')) { throw 'invalid-launcher-request' }
            $resultPath = Join-Path (Join-Path $Root 'results') ($request.id + '.json')
            if (Test-Path -LiteralPath $resultPath) { throw 'duplicate-launcher-request' }
            $acceptedPath = Join-Path (Join-Path $Root 'results') ($request.id + '.request.json')
            [IO.File]::Move($requestPath, $acceptedPath)
            $result = @{ id=$request.id; operation=$request.operation; success=$false; oldRun=$script:runDirectory }
            try {
                $next = if ($request.operation -eq 'update') { $request.release } else { Read-Record (Join-Path $Root 'current.json') }
                if ($request.operation -in @('start','restart','update')) { $null = Assert-Release $next }
                if ($request.operation -in @('stop','restart','update','exit')) { Stop-Agent }
                if ($request.operation -in @('start','restart','update')) {
                    Start-Agent $next
                    Write-Record (Join-Path $Root 'current.json') $next
                }
                $exitRequested = $request.operation -eq 'exit'
                $result.success=$true
            } catch {
                $result.errorType=$_.Exception.GetType().Name
                $result.errorCode=if ($_.Exception.Message -match '^[a-z-]+$') { $_.Exception.Message } else { 'launcher-operation-failed' }
                Write-State 'blocked'
            }
            $result.newRun=$script:runDirectory; $result.utc=[DateTime]::UtcNow.ToString('o')
            Write-Record $resultPath $result
        }
        Start-Sleep -Milliseconds 250
    }
} catch {
    if ($owned) {
        Write-Record (Join-Path $Root 'launcher-failure.json') @{
            errorType=$_.Exception.GetType().Name; message=$_.Exception.Message
            line=$_.InvocationInfo.ScriptLineNumber; utc=[DateTime]::UtcNow.ToString('o')
        }
    }
    throw
} finally {
    if ($owned) {
        try { Stop-Agent } finally { $mutex.ReleaseMutex() }
    }
    $mutex.Dispose()
}
