[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('snapshot','stop','delete')][string]$Action,
 [Parameter(Mandatory)][ValidateSet('lab1','lab2')][string]$Lab,
 [string]$XmlFile, [string]$Instance, [int]$PidValue, [long]$StartTicks, [string]$RegistrationSha256)
$ErrorActionPreference = 'Stop'
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
$name = 'Workbridge Helper rr2-receiver-' + $Lab
$task = $folder.GetTask($name)
function Instances {
  $running = $service.GetRunningTasks(1)
  return @($running | Where-Object { $_.Path -ceq ('\' + $name) } | ForEach-Object {
    [ordered]@{guid=[string]$_.InstanceGuid; pid=[int]$_.EnginePID}
  })
}
if ($Action -eq 'snapshot') {
  [ordered]@{xml=[string]$task.Xml; instances=@(Instances)} | ConvertTo-Json -Depth 5 -Compress
  exit
}
$registration = Join-Path 'C:\work\workbridge-mcp\.local\helpers' ('rr2-receiver-' + $Lab + '/registration.json')
function Assert-Registration {
  if ($RegistrationSha256 -cnotmatch '^[0-9A-F]{64}$') { throw 'registration-pin-invalid' }
  $stream = [IO.File]::Open($registration, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
  try {
    if ($stream.Length -gt 65536) { throw 'registration-too-large' }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '') } finally { $hasher.Dispose() }
  } finally { $stream.Dispose() }
  if ($actual -cne $RegistrationSha256) { throw 'registration-changed' }
}
Assert-Registration
$expected = [IO.File]::ReadAllText($XmlFile, [Text.Encoding]::UTF8)
if ([string]$task.Xml -cne $expected) { throw 'task-xml-changed' }
if ($Action -eq 'stop') {
  $instances = @(Instances)
  if ($instances.Count -ne 1 -or $instances[0].guid -cne $Instance -or $instances[0].pid -ne $PidValue) { throw 'task-instance-changed' }
  $process = Get-Process -Id $PidValue -ErrorAction Stop
  if ($process.StartTime.ToUniversalTime().Ticks -ne $StartTicks) { throw 'process-start-changed' }
  # Acquire the actual process handle before the stop; WaitForExit then tracks
  # this process object even if Windows recycles its numeric PID.
  $null = $process.Handle
  $running = $service.GetRunningTasks(1)
  $matches = @($running | Where-Object { $_.Path -ceq ('\' + $name) -and $_.InstanceGuid -ceq $Instance -and $_.EnginePID -eq $PidValue })
  if ($matches.Count -ne 1) { throw 'task-instance-changed' }
  Assert-Registration
  $matches[0].Stop()
  if (-not $process.WaitForExit(15000)) { throw 'old-process-still-running' }
  '{"stopped":true}'
  exit
}
if (@(Instances).Count -ne 0) { throw 'task-still-running' }
if ([string]$folder.GetTask($name).Xml -cne $expected) { throw 'task-xml-changed' }
Assert-Registration
$folder.DeleteTask($name, 0)
'{"deleted":true}'
