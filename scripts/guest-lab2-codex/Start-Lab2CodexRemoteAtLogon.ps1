$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA 'RiftLabTools'
$resultPath = Join-Path $root 'codex-remote-autostart.json'
[IO.Directory]::CreateDirectory($root) | Out-Null
$mutex = [Threading.Mutex]::new($false, 'Local\RiftLab2-CodexRemoteAutostart')
$owned = $false
$result = [ordered]@{
  schemaVersion = 1
  attemptedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
  machineName = [Environment]::MachineName
  sessionId = [Diagnostics.Process]::GetCurrentProcess().SessionId
  isAdministrator = $false
  outcome = $null
  exitCode = $null
  status = $null
  serverName = $null
  environmentId = $null
  error = $null
}
try {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  $result.isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if ($result.isAdministrator) { throw 'limited-token-required' }
  if ($result.machineName -ne 'RIFT-LAB-2') { throw 'unexpected-machine-name' }
  try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
  if (-not $owned) { throw 'autostart-already-running' }
  Start-Sleep -Seconds 15
  $candidates = @(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin') -Filter codex.exe -File -Recurse -ErrorAction Stop |
      Where-Object FullName -Match '\\OpenAI\\Codex\\bin\\[A-Za-z0-9]+\\codex\.exe$' | Sort-Object LastWriteTimeUtc -Descending)
  if (-not $candidates.Count) { throw 'codex-cli-unavailable' }
  $cli = $candidates[0].FullName
  function Invoke-Codex([string]$arguments, [int]$timeoutMs) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $cli
    $info.Arguments = $arguments
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $info
    if (-not $process.Start()) { throw 'codex-command-start-failed' }
    $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($timeoutMs)) { try { $process.Kill() } catch {}; throw 'codex-command-timeout' }
    return [ordered]@{exitCode=$process.ExitCode;stdout=$stdout.GetAwaiter().GetResult();stderr=$stderr.GetAwaiter().GetResult()}
  }
  $invocation = Invoke-Codex 'remote-control start --json' 30000
  $result.exitCode = $invocation.exitCode
  $text = ([string]$invocation.stdout).Trim()
    if ($text) {
      try {
        $value = $text | ConvertFrom-Json -ErrorAction Stop
        $result.status = [string]$value.status
        $result.serverName = [string]$value.serverName
        $result.environmentId = [string]$value.environmentId
      } catch {}
    }
  if ($invocation.exitCode -ne 0) {
    $combined = ([string]$invocation.stdout) + ([string]$invocation.stderr)
    if ($combined -match 'Remote app server already online') {
      $stop = Invoke-Codex 'remote-control stop --json' 15000
      if ($stop.exitCode -ne 0) { throw 'duplicate-daemon-stop-failed' }
      $result.outcome = 'existing-remote-already-online'
    }
    else { throw 'codex-start-nonzero' }
  }
  else {
    if ($result.status -ne 'connected' -or $result.serverName -ne 'RIFT-LAB-2') { throw 'codex-start-not-connected' }
    $result.outcome = 'connected'
  }
}
catch { $result.error = if ($_.Exception.Message -match '^[a-z-]+$') { $_.Exception.Message } else { 'autostart-failed' } }
finally {
  $temp = $resultPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
  [IO.File]::WriteAllText($temp, ($result | ConvertTo-Json -Depth 4 -Compress) + "`n", [Text.UTF8Encoding]::new($false))
  Move-Item -LiteralPath $temp -Destination $resultPath -Force
  if ($owned) { $mutex.ReleaseMutex() }; $mutex.Dispose()
}
