# Offline tests: extract function definitions; no entry point or Scheduler calls execute.
$ErrorActionPreference = 'Stop'
$originalModulePath = $env:PSModulePath
$env:PSModulePath = 'C:\rr2-test-invalid-module-path'
$originalAutoload = $PSModuleAutoloadingPreference
$PSModuleAutoloadingPreference = 'None'
foreach ($module in @('Microsoft.PowerShell.Utility','Microsoft.PowerShell.Management','CimCmdlets')) {
    Import-Module ([IO.Path]::Combine($PSHOME, 'Modules', $module, ($module + '.psd1'))) -ErrorAction Stop
}
try {
$path = Join-Path $PSScriptRoot '../scripts/Verify-RR2LegacyHelperTask.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Verifier parse errors' }
$ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]}, $false) | ForEach-Object { Invoke-Expression $_.Extent.Text }
function Must-Fail([scriptblock]$Block) { try { & $Block | Out-Null } catch { return }; throw ('Expected refusal at ' + (Get-PSCallStack | Select-Object -Skip 1 -First 1).ScriptLineNumber) }
$expected = [ordered]@{schema=1; helperId='rr2-receiver-lab1'; ownerSid='S-1-5-21-1'; taskName='Workbridge Helper rr2-receiver-lab1'; executable='C:\Python314\pythonw.exe'; arguments='"C:\work\riftreader2\scripts\receiver_task_entry.py" "--lab" "lab1"'; workingDirectory='C:\work\riftreader2'; atLogon=$false; description='expected digest'}
$config = [pscustomobject]$expected
$task = [pscustomobject]@{TaskPath='\'; TaskName=$expected.taskName; Description=$expected.description; State='Running'; Actions=@([pscustomobject]@{Execute=$expected.executable; Arguments=$expected.arguments; WorkingDirectory=$expected.workingDirectory}); Principal=[pscustomobject]@{UserId=$expected.ownerSid; RunLevel=0; LogonType=3}; Triggers=@(); Settings=[pscustomobject]@{ExecutionTimeLimit='PT0S'; MultipleInstances=2; Enabled=$true; DisallowStartIfOnBatteries=$false; StopIfGoingOnBatteries=$false; RestartCount=0}}
Assert-LegacyHelper $task $config $expected $expected.ownerSid
foreach ($field in @($expected.Keys)) {
    $bad = $config | ConvertTo-Json | ConvertFrom-Json
    $bad.$field = 'tampered'
    Must-Fail { Assert-LegacyHelper $task $bad $expected $expected.ownerSid }
}
foreach ($change in @(@('TaskPath','\foreign\'), @('TaskName','other'), @('Description','other'), @('State','Ready'))) {
    $old = $task.($change[0]); $task.($change[0]) = $change[1]
    Must-Fail { Assert-LegacyHelper $task $config $expected $expected.ownerSid }
    $task.($change[0]) = $old
}
foreach ($object in @($task.Actions[0], $task.Principal, $task.Settings)) {
    foreach ($field in @($object.PSObject.Properties.Name)) {
        $old = $object.$field
        $object.$field = if ($old -is [bool]) { !$old } elseif ($old -is [int]) { $old + 1 } else { 'tampered' }
        Must-Fail { Assert-LegacyHelper $task $config $expected $expected.ownerSid }
        $object.$field = $old
    }
}
$task.Triggers = @([pscustomobject]@{Enabled=$false})
Must-Fail { Assert-LegacyHelper $task $config $expected $expected.ownerSid }
$task.Triggers = @()
$task.Actions = @($task.Actions[0], $task.Actions[0])
Must-Fail { Assert-LegacyHelper $task $config $expected $expected.ownerSid }
$global:legacyTestTasks = @($task)
$global:legacyQueryFailed = $false
function global:Get-ScheduledTask { param($TaskPath,$ErrorAction) if ($global:legacyQueryFailed) { throw 'access denied' }; return $global:legacyTestTasks }
if ((Get-LegacyTask $expected.helperId).TaskName -cne $expected.taskName) { throw 'Task selection failed' }
$global:legacyQueryFailed = $true
Must-Fail { Get-LegacyTask $expected.helperId }
$global:legacyQueryFailed = $false
foreach ($tasks in @(@(), @($task,$task), @($task, [pscustomobject]@{TaskName='RIFTREADER2 HELPER rr2-receiver-lab1';State='Ready'}))) {
    $global:legacyTestTasks = $tasks
    Must-Fail { Get-LegacyTask $expected.helperId }
}
$temp = Join-Path ([IO.Path]::GetTempPath()) ('rr2-legacy-' + [guid]::NewGuid().ToString('N') + '.json')
try {
    Must-Fail { Read-LegacyRegistration $temp }
    foreach ($bad in @('null','[]','1','"text"','{broken', ('x' * 65537))) {
        [IO.File]::WriteAllText($temp, $bad)
        Must-Fail { Read-LegacyRegistration $temp }
    }
    [IO.File]::WriteAllText($temp, ($config | ConvertTo-Json))
    if ((Read-LegacyRegistration $temp).helperId -cne $expected.helperId) { throw 'Read failed' }
} finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }
$source = [IO.File]::ReadAllText($path)
if ($source -match '(?i)(Start|Stop|Register|Unregister)-ScheduledTask|Manage-HelperTask|Workbridge-Update') { throw 'Unexpected mutating/external code dependency' }
'Legacy helper verifier offline tests PASS'


# Whole-entrypoint fixture: replace environment boundaries in a temporary copy only.
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('rr2-legacy-entry-' + [guid]::NewGuid().ToString('N'))
try {
    $fixtureScripts = Join-Path $fixture 'scripts'
    [IO.Directory]::CreateDirectory($fixtureScripts) | Out-Null
    $fixtureReceipts = Join-Path $fixture 'legacy'
    $id = 'rr2-controller-lab2'
    $folder = Join-Path $fixtureReceipts $id
    [IO.Directory]::CreateDirectory($folder) | Out-Null
    $exe = Join-Path $fixture 'pythonw.exe'
    [IO.File]::WriteAllText($exe, 'not executed')
    $script = [IO.File]::ReadAllText($path)
    $script = $script.Replace("Import-Module (Join-Path `$env:WINDIR 'System32/WindowsPowerShell/v1.0/Modules/ScheduledTasks') -ErrorAction Stop", '# mocked module boundary')
    $script = $script.Replace('$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value', '$sid = ''S-1-5-21-1''')
    $script = $script.Replace('C:\work\workbridge-mcp\.local\helpers', $fixtureReceipts)
    $script = $script.Replace("New-Object -ComObject 'Schedule.Service'", '$global:mockService')
    $global:mockInstances = @([pscustomobject]@{EnginePID=123; InstanceGuid='4a048a33-b778-4f2f-9a90-e139cd4ce100'})
    $collection = [pscustomobject]@{}
    $collection | Add-Member ScriptProperty Count { $global:mockInstances.Count }
    $collection | Add-Member ScriptMethod Item { param($index) $global:mockInstances[$index-1] }
    $registeredTask = [pscustomobject]@{collection=$collection}
    $registeredTask | Add-Member ScriptMethod GetInstances { param($flags) $this.collection }
    $folderMock = [pscustomobject]@{registeredTask=$registeredTask}
    $folderMock | Add-Member ScriptMethod GetTask { param($name) $this.registeredTask }
    $global:mockService = [pscustomobject]@{folder=$folderMock}
    $global:mockService | Add-Member ScriptMethod Connect { }
    $global:mockService | Add-Member ScriptMethod GetFolder { param($path) $this.folder }
    $fixtureScript = Join-Path $fixtureScripts 'Verify-RR2LegacyHelperTask.ps1'
    [IO.File]::WriteAllText($fixtureScript, $script)
    $expect = [ordered]@{schema=1;helperId=$id;ownerSid='S-1-5-21-1';taskName=('Workbridge Helper ' + $id);executable=$exe;arguments=('"' + (Join-Path $fixture 'scripts/controller_task_entry.py') + '" "--lab" "lab2"');workingDirectory=$fixture;atLogon=$false}
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($expect | ConvertTo-Json -Compress)))).Replace('-','') } finally { $hash.Dispose() }
    $expect.description = 'Workbridge user helper; registration SHA256 ' + $digest
    [IO.File]::WriteAllText((Join-Path $folder 'registration.json'), ($expect | ConvertTo-Json))
    $fullTask = $task | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $fullTask.TaskName=$expect.taskName; $fullTask.Description=$expect.description
    $fullTask.Actions=@([pscustomobject]@{Execute=$exe;Arguments=$expect.arguments;WorkingDirectory=$fixture})
    $global:legacyTestTasks=@($fullTask)
    $result = & $fixtureScript -HelperId $id -Executable $exe | ConvertFrom-Json
    if ($result.ownership -cne 'verified-legacy-read-only' -or $result.state -cne 'Running') { throw 'Full verification failed' }
    if ($result.enginePid -ne 123 -or !$result.instanceGuid) { throw 'Instance identity missing' }
    $instance = $global:mockInstances[0]
    $global:mockInstances = @(); Must-Fail { & $fixtureScript -HelperId $id -Executable $exe }
    $global:mockInstances = @($instance, $instance); Must-Fail { & $fixtureScript -HelperId $id -Executable $exe }
    $global:mockInstances = @($instance)
    # Explicit Ready inspection is limited to controllers and cannot certify Running.
    Must-Fail { & $fixtureScript -HelperId $id -Executable $exe -InspectReadyController }
    $fullTask.State='Ready'
    Must-Fail { & $fixtureScript -HelperId $id -Executable $exe }
    $ready = & $fixtureScript -HelperId $id -Executable $exe -InspectReadyController | ConvertFrom-Json
    if ($ready.state -cne 'Ready' -or $ready.ownership -cne 'verified-legacy-ready-read-only') { throw 'Ready verification failed' }
    foreach ($invalidState in @('Disabled','Unknown','Queued')) {
        $fullTask.State=$invalidState
        Must-Fail { & $fixtureScript -HelperId $id -Executable $exe -InspectReadyController }
    }
    $fullTask.State='Ready'
    $global:legacyTestTasks=@($fullTask, [pscustomobject]@{TaskName=('RiftReader2 Helper ' + $id);State='Ready'})
    Must-Fail { & $fixtureScript -HelperId $id -Executable $exe -InspectReadyController }
    $global:legacyTestTasks=@($fullTask)
    Must-Fail { & $fixtureScript -HelperId 'rr2-receiver-lab2' -Executable $exe -InspectReadyController }
    $fullTask.TaskPath='\foreign\'
    Must-Fail { & $fixtureScript -HelperId $id -Executable $exe -InspectReadyController }
    $fullTask.TaskPath='\'
    $fullTask.State='Running'
    foreach ($state in @('Ready','Running','Disabled','Unknown')) {
        $global:legacyTestTasks=@($fullTask, [pscustomobject]@{TaskName=('RIFTREADER2 HELPER ' + $id);State=$state})
        Must-Fail { & $fixtureScript -HelperId $id -Executable $exe }
    }
    $global:legacyTestTasks=@($fullTask)
    $fullTask.TaskName=$fullTask.TaskName.ToUpperInvariant()
    Must-Fail { & $fixtureScript -HelperId $id -Executable $exe }
    $fullTask.TaskName=$expect.taskName
    $expect.description='wrong digest'
    [IO.File]::WriteAllText((Join-Path $folder 'registration.json'), ($expect | ConvertTo-Json))
    Must-Fail { & $fixtureScript -HelperId $id -Executable $exe }
} finally {
    # The only recursive deletion target is the exact temporary fixture just created.
    if ($fixture -and [IO.Path]::GetFullPath($fixture).StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
'Legacy full-entrypoint mocks PASS'

} finally {
    $env:PSModulePath = $originalModulePath
    $PSModuleAutoloadingPreference = $originalAutoload
}
