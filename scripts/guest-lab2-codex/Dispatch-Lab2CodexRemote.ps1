$ErrorActionPreference = 'Stop'
$link = 'C:\Users\mrkoo\AppData\Local\RiftLabTools\RIFT-LAB-2 Codex Remote.lnk'
$receipt = 'C:\Users\mrkoo\AppData\Local\RiftLabTools\codex-remote-dispatch.json'
$result = [ordered]@{ dispatchedAtUtc=[DateTimeOffset]::UtcNow.ToString('O'); sessionId=[Diagnostics.Process]::GetCurrentProcess().SessionId; success=$false; error=$null }
try {
  if (-not (Test-Path -LiteralPath $link -PathType Leaf)) { throw 'shortcut-missing' }
  Start-Process -FilePath (Join-Path $env:WINDIR 'explorer.exe') -ArgumentList @($link) -WindowStyle Hidden
  $result.success = $true
}
catch { $result.error = if ($_.Exception.Message -match '^[a-z-]+$') { $_.Exception.Message } else { 'dispatch-failed' } }
finally { [IO.File]::WriteAllText($receipt, ($result | ConvertTo-Json -Compress) + "`n", [Text.UTF8Encoding]::new($false)) }
if (-not $result.success) { exit 2 }
