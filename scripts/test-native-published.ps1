[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Executable,
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$captureExecutable = (Resolve-Path -LiteralPath $Executable).Path
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$runDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$currentProcess = [Diagnostics.Process]::GetCurrentProcess()
try {
    $request = [ordered]@{
        schemaVersion = 1
        evidenceKind = 'native-memory-read-request/1'
        target = [ordered]@{
            processId = $currentProcess.Id
            processStartUtcTicks = $currentProcess.StartTime.ToUniversalTime().Ticks
            executableSha256 = (Get-FileHash -LiteralPath $currentProcess.MainModule.FileName).Hash
        }
        sampling = [ordered]@{ sampleCount = 1; intervalMilliseconds = 0; maxDurationMilliseconds = 5000 }
        ranges = @([ordered]@{ id = 'synthetic-host-header'; addressKind = 'module-relative-rva'; address = '0x0'; byteLength = 2 })
    }
    $requestPath = Join-Path $runDirectory 'request.json'
    $reportPath = Join-Path $runDirectory 'capture.json'
    $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $requestPath -Encoding utf8
    & $captureExecutable capture-native --request $requestPath --output $reportPath > (Join-Path $runDirectory 'capture.stdout.json')
    if ($LASTEXITCODE -ne 0) { throw 'Published native capture failed.' }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($report.capture.status -ne 'complete' -or $report.implementation.deploymentKind -ne 'single-file-bundle') {
        throw 'Published native report did not identify a complete bundled capture.'
    }
    if ($report.implementation.bundleSha256 -ne (Get-FileHash -LiteralPath $captureExecutable).Hash -or
        $null -ne $report.implementation.assemblySha256) { throw 'Published bundle identity does not match the actual executable.' }
    $bytes = [Convert]::FromBase64String($report.capture.samples[0].ranges[0].bytesBase64)
    if ($bytes.Length -ne 2 -or $bytes[0] -ne 77 -or $bytes[1] -ne 90) { throw 'Published native capture did not read the PE header.' }
    $firstHash = (Get-FileHash -LiteralPath $reportPath).Hash
    & $captureExecutable capture-native --request $requestPath --output $reportPath > (Join-Path $runDirectory 'overwrite.stdout.txt') 2> (Join-Path $runDirectory 'overwrite.stderr.txt')
    if ($LASTEXITCODE -ne 2 -or (Get-FileHash -LiteralPath $reportPath).Hash -ne $firstHash) {
        throw 'Published native capture replaced existing evidence.'
    }
    $request.target.processStartUtcTicks++
    $staleRequest = Join-Path $runDirectory 'stale.request.json'
    $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $staleRequest -Encoding utf8
    $staleOutput = Join-Path $runDirectory 'stale.json'
    & $captureExecutable capture-native --request $staleRequest --output $staleOutput > (Join-Path $runDirectory 'stale.stdout.txt') 2> (Join-Path $runDirectory 'stale.stderr.txt')
    if ($LASTEXITCODE -ne 2 -or (Test-Path -LiteralPath $staleOutput)) { throw 'Published native capture accepted a stale epoch.' }
    $positionProfile = Join-Path (Split-Path -Parent $captureExecutable) 'position-candidate-profile.json'
    $trackedPositionProfile = Join-Path $PSScriptRoot '../config/position-candidate-profile.json'
    if (-not (Test-Path -LiteralPath $positionProfile) -or
        (Get-FileHash -LiteralPath $positionProfile).Hash -ne (Get-FileHash -LiteralPath $trackedPositionProfile).Hash) {
        throw 'Published position panel is missing its exact default profile sidecar.'
    }
    & $captureExecutable position-panel --output-directory $runDirectory > (Join-Path $runDirectory 'panel-existing.stdout.txt') 2> (Join-Path $runDirectory 'panel-existing.stderr.txt')
    if ($LASTEXITCODE -ne 2 -or
        (Get-Content -LiteralPath (Join-Path $runDirectory 'panel-existing.stderr.txt') -Raw) -notmatch 'evidence directory already exists') {
        throw 'Published panel did not load its default profile and reject an existing evidence directory before opening a window.'
    }
    Write-Output 'Published native smoke passed: synthetic host process only; bundle identity, PE header, stale epoch, and no-overwrite.'
}
finally {
    $currentProcess.Dispose()
}
