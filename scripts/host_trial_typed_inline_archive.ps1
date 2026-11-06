param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$TrialRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9A-F]{64}$')][string]$ExpectedBundleSha256,
    [ValidateSet('RR2R1|','RRAPIVAL2|')][string]$Marker = 'RR2R1|',
    [string]$Python = 'C:\Python314\python.exe'
)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitProcess) { throw '64-bit PowerShell is required.' }
if (Test-Path -LiteralPath $TrialRoot) { throw 'Trial root already exists.' }
if (-not (Test-Path -LiteralPath (Split-Path -Parent $TrialRoot) -PathType Container)) {
    throw 'Trial parent directory must exist.'
}
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf) -or
    -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Pinned executable or Python not found.'
}
$expectedBundle = $ExpectedBundleSha256
$bundle = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash
if ($bundle -ne $expectedBundle) { throw 'Published executable SHA-256 differs.' }

$utf8 = New-Object System.Text.UTF8Encoding($false)
$allocBytes = 65536 + 8192
$allocation = [Runtime.InteropServices.Marshal]::AllocHGlobal($allocBytes)
$current = [Diagnostics.Process]::GetCurrentProcess()
try {
    $raw = [UInt64]$allocation.ToInt64()
    $aligned = [UInt64]([Math]::Floor(([double]$raw + 4095.0) / 4096.0) * 4096.0)
    $data = New-Object byte[] $allocBytes
    $markerBytes = [Text.Encoding]::ASCII.GetBytes($Marker + '{')
    $markerOffset = 2 * 4096 + 100
    [Array]::Copy($markerBytes, 0, $data, $markerOffset, $markerBytes.Length)
    [Runtime.InteropServices.Marshal]::Copy($data, 0, [IntPtr]([Int64]$aligned), 65536)
    $expectedMarker = '0x' + ($aligned + $markerOffset).ToString('X')

    $trial = New-Item -ItemType Directory -Path $TrialRoot -ErrorAction Stop
    $requestPath = Join-Path $TrialRoot 'source.request.json'
    $req = [ordered]@{
        schemaVersion = 1
        evidenceKind = 'native-typed-inline-capture-request/1'
        marker = $Marker
        target = [ordered]@{
            processId = $current.Id
            processStartUtcTicks = $current.StartTime.ToUniversalTime().Ticks
            executableSha256 = (Get-FileHash -LiteralPath $current.MainModule.FileName -Algorithm SHA256).Hash
        }
        startAddress = '0x' + $aligned.ToString('X')
        maxScanBytes = 65536
        maxDurationMilliseconds = 20000
        maxRegionCount = 32768
        maxMatchCount = 8
        maxCopiedCandidates = 2
    }
    [IO.File]::WriteAllText($requestPath, ($req | ConvertTo-Json -Depth 8), $utf8)

    for ($runNo=1; $runNo -le 2; $runNo++) {
        $runName = ('run-{0:D2}' -f $runNo)
        $runPath = Join-Path $TrialRoot $runName
        $nativeOutput = & $Executable scout-copy-typed-native --request $requestPath --output $runPath 2>&1
        $nativeExit = $LASTEXITCODE
        if ($nativeExit -ne 0 -and $nativeExit -ne 3) {
            throw ($runName + ': published command failed: ' + $nativeExit + '; ' + ($nativeOutput -join ' '))
        }
        $indexPath = Join-Path $runPath 'index.json'
        if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) { throw 'Native manifest absent.' }
        $index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
        if ($index.implementation.bundleSha256 -ne $expectedBundle) {
            throw 'Published executable identity differs.'
        }
        $found = @($index.candidates | Where-Object {
            $_.markerAddress -eq $expectedMarker -and $_.status -eq 'complete'
        })
        if ($found.Count -ne 1) { throw ($runName + ': exact source marker not captured.') }
        $snapPath = Join-Path $runPath $found[0].snapshotFile
        $snap = Get-Content -LiteralPath $snapPath -Raw | ConvertFrom-Json
        if ($snap.status -ne 'complete' -or @($snap.chunks).Count -ne 7) {
            throw ($runName + ': seven-page snapshot incomplete.')
        }
        $copied = New-Object byte[] (7 * 4096)
        for ($i=0; $i -lt 7; $i++) {
            $chunk = [Convert]::FromBase64String($snap.chunks[$i].bytesBase64)
            if ($chunk.Length -ne 4096) { throw 'Incomplete published chunk.' }
            [Array]::Copy($chunk, 0, $copied, $i * 4096, 4096)
        }
        for ($i=0; $i -lt $copied.Length; $i++) {
            if ($copied[$i] -ne $data[$i]) { throw ($runName + ': byte mismatch at ' + $i) }
        }
        $destRequest = Join-Path $runPath 'input.request.json'
        if (Test-Path -LiteralPath $destRequest) { throw 'Request replay would overwrite.' }
        [IO.File]::WriteAllBytes($destRequest, [IO.File]::ReadAllBytes($requestPath))
        Write-Output ($runName + '=PASS;NATIVE_EXIT=' + $nativeExit +
            ';INDEX_SHA256=' + (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash)
        if ($runNo -eq 1) { Start-Sleep -Seconds 2 }
    }

    $archivePath = Join-Path $TrialRoot 'two-runs.zip'
    $runA = Join-Path $TrialRoot 'run-01'
    $runB = Join-Path $TrialRoot 'run-02'
    Compress-Archive -LiteralPath @($runA,$runB) -DestinationPath $archivePath -CompressionLevel Optimal
    if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) { throw 'Archive missing.' }
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    $recovered = Join-Path $TrialRoot 'recovered'
    $reviewArgs = @(
        '-m', 'scripts.verify_typed_inline_archive',
        '--archive', $archivePath,
        '--expected-sha256', $archiveHash,
        '--output', $recovered,
        '--process-id', ([string]$current.Id),
        '--process-start-ticks', ([string]$current.StartTime.ToUniversalTime().Ticks),
        '--game-sha256', $req.target.executableSha256,
        '--bundle-sha256', $expectedBundle,
        '--marker', $Marker
    )
    $review = & $Python @reviewArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('Archive verification failed: ' + ($review -join ' ')) }
    $proof = Get-Content -LiteralPath (Join-Path $recovered 'archive-proof.json') -Raw | ConvertFrom-Json
    if (@($proof.runs).Count -ne 2 -or
        @($proof.runs | Where-Object { $_.snapshotCount -ne 1 }).Count -ne 0) {
        throw 'Archive receipt does not prove two actual copies.'
    }
    Write-Output ('PUBLISHED_TWO_RUN_ARCHIVE=PASS;ARCHIVE_SHA256=' + $archiveHash +
        ';BYTES=' + (Get-Item -LiteralPath $archivePath).Length +
        ';RECOVERED_FILES=' + @($proof.files).Count)
}
finally {
    $current.Dispose()
    [Runtime.InteropServices.Marshal]::FreeHGlobal($allocation)
}
