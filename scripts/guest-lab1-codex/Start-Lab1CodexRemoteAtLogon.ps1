$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'RiftLabTools';$resultPath=Join-Path $root 'codex-remote-autostart-lab1.json';[IO.Directory]::CreateDirectory($root)|Out-Null
$mutex=[Threading.Mutex]::new($false,'Local\RiftLab1-CodexRemoteAutostart');$owned=$false
$result=[ordered]@{schemaVersion=1;attemptedAtUtc=[DateTimeOffset]::UtcNow.ToString('O');machineName=[Environment]::MachineName;sessionId=[Diagnostics.Process]::GetCurrentProcess().SessionId;isAdministrator=$false;outcome=$null;exitCode=$null;status=$null;serverName=$null;environmentId=$null;error=$null}
try{
 $id=[Security.Principal.WindowsIdentity]::GetCurrent();$pr=[Security.Principal.WindowsPrincipal]::new($id);$result.isAdministrator=$pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
 if($result.isAdministrator){throw 'limited-token-required'};if($result.machineName -ne 'RIFT-LAB-1'){throw 'unexpected-machine-name'}
 try{$owned=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true};if(-not $owned){throw 'autostart-already-running'};Start-Sleep -Seconds 5
 $c=@(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin') -Filter codex.exe -File -Recurse -ErrorAction Stop|Where-Object FullName -Match '\\OpenAI\\Codex\\bin\\[A-Za-z0-9]+\\codex\.exe$'|Sort-Object LastWriteTimeUtc -Descending)
 if(-not $c.Count){throw 'codex-cli-unavailable'};$cli=$c[0].FullName;$i=[Diagnostics.ProcessStartInfo]::new();$i.FileName=$cli;$i.Arguments='remote-control start --json';$i.UseShellExecute=$false;$i.CreateNoWindow=$true;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
 $p=[Diagnostics.Process]::new();$p.StartInfo=$i;if(-not $p.Start()){throw 'codex-command-start-failed'};$o=$p.StandardOutput.ReadToEndAsync();$e=$p.StandardError.ReadToEndAsync();if(-not $p.WaitForExit(30000)){try{$p.Kill()}catch{};throw 'codex-command-timeout'}
 $result.exitCode=$p.ExitCode;$text=$o.GetAwaiter().GetResult().Trim();if($text){try{$v=$text|ConvertFrom-Json -ErrorAction Stop;$result.status=[string]$v.status;$result.serverName=[string]$v.serverName;$result.environmentId=[string]$v.environmentId}catch{}}
 if($p.ExitCode -ne 0){$combined=$text+$e.GetAwaiter().GetResult();if($combined -match 'Remote app server already online'){$result.outcome='existing-remote-conflict';throw 'independent-existing-host-verification-required'};throw 'codex-start-nonzero'}
 if($result.status -ne 'connected' -or $result.serverName -ne 'RIFT-LAB-1'){throw 'codex-start-not-connected'};$result.outcome='connected'
}catch{$result.error=if($_.Exception.Message -match '^[a-z-]+$'){$_.Exception.Message}else{'autostart-failed'}}
finally{$tmp=$resultPath+'.'+[Guid]::NewGuid().ToString('N')+'.tmp';[IO.File]::WriteAllText($tmp,($result|ConvertTo-Json -Depth 4 -Compress)+"`n",[Text.UTF8Encoding]::new($false));Move-Item -LiteralPath $tmp -Destination $resultPath -Force;if($owned){$mutex.ReleaseMutex()};$mutex.Dispose()}
