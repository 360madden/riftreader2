[CmdletBinding()]
param([string]$LuaPython = $env:RIFTREADER2_LUA_PYTHON)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    if (-not $LuaPython) {
        $localLuaPython = Join-Path $repoRoot 'artifacts/tools/lua-python/Scripts/python.exe'
        $LuaPython = if (Test-Path -LiteralPath $localLuaPython) { $localLuaPython } else { 'python' }
    }
    & $LuaPython -c 'import lupa; from lupa.lua51 import LuaRuntime; assert lupa.__version__ == "2.8"; assert LuaRuntime().eval("_VERSION") == "Lua 5.1"'
    if ($LASTEXITCODE -ne 0) { throw 'Lua 5.1 test runtime missing. Install requirements-lua-tests.txt or pass -LuaPython; see docs/workflows/development.md.' }
    $solution = 'RiftReader2.slnx'
    $allowed = @{
        'RiftReader2.Domain' = @()
        'RiftReader2.Application' = @('RiftReader2.Domain')
        'RiftReader2.Infrastructure' = @('RiftReader2.Domain')
        'RiftReader2.Cli' = @('RiftReader2.Domain', 'RiftReader2.Application', 'RiftReader2.Infrastructure')
        'RiftReader2.Live' = @('RiftReader2.Domain', 'RiftReader2.Application', 'RiftReader2.Infrastructure')
    }
    $projects = @(Get-ChildItem -LiteralPath src -Filter *.csproj -Recurse)
    if ($projects.Count -ne $allowed.Count) { throw 'Update the reviewed dependency rules for new modules.' }
    foreach ($project in $projects) {
        [xml]$xml = Get-Content -LiteralPath $project.FullName -Raw
        $actual = @($xml.SelectNodes('//ProjectReference') | ForEach-Object {
            [IO.Path]::GetFileNameWithoutExtension($_.Include)
        } | Sort-Object)
        $expected = @($allowed[$project.BaseName] | Sort-Object)
        if (-not $allowed.ContainsKey($project.BaseName) -or (($actual -join ',') -ne ($expected -join ','))) {
            throw "Module dependency violation: $($project.BaseName)"
        }
        if ($xml.SelectNodes('//PackageReference').Count -ne 0) {
            throw "Production package dependency requires an architecture review: $($project.BaseName)"
        }
    }

    dotnet restore $solution --locked-mode
    if ($LASTEXITCODE -ne 0) { throw 'Locked restore failed.' }
    dotnet build $solution --configuration Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Release build failed.' }
    dotnet test $solution --configuration Release --no-build --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    dotnet format $solution --verify-no-changes --no-restore --verbosity minimal
    if ($LASTEXITCODE -ne 0) { throw 'Formatting verification failed.' }

    $cli = 'src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll'
    $runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $runDirectory = Join-Path 'artifacts/validation' $runId
    New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
    $nativePublish = Join-Path $runDirectory 'native-published'
    dotnet publish src/RiftReader2.Live/RiftReader2.Live.csproj --configuration Release --no-restore --output $nativePublish
    if ($LASTEXITCODE -ne 0) { throw 'Native executable publication failed.' }
    & (Join-Path $PSScriptRoot 'test-native-published.ps1') -Executable (Join-Path $nativePublish 'RiftReader2.Live.exe') -OutputDirectory (Join-Path $runDirectory 'native-smoke')
    $catalogArgs = @('qualify-fields', '--catalog', 'samples/catalog/catalog.json', '--build-sha256', ('A' * 64), '--session-id', 'synthetic-session-a', '--as-of', '2026-10-19T00:00:00Z')
    $catalogReport = Join-Path $runDirectory 'catalog.json'
    $catalogReplay = Join-Path $runDirectory 'catalog-replay.json'
    & dotnet $cli @catalogArgs --output $catalogReport | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Catalog qualification smoke failed.' }
    & dotnet $cli @catalogArgs --output $catalogReplay | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Catalog replay smoke failed.' }
    if ((Get-FileHash -LiteralPath $catalogReport).Hash -ne (Get-FileHash -LiteralPath $catalogReplay).Hash) {
        throw 'Catalog replay produced different report bytes.'
    }
    $catalogFields = (Get-Content -LiteralPath $catalogReport -Raw | ConvertFrom-Json).evaluation.fields
    if ($catalogFields.Count -ne 3 -or $catalogFields[0].status -ne 'supported-by-recorded-assessment' -or
        $catalogFields[1].status -ne 'contradicted' -or $catalogFields[2].status -ne 'unqualified') {
        throw 'Synthetic catalog qualification differs from expected scoped outcomes.'
    }
    & $LuaPython scripts/test-addon-contract.py --cli $cli --output-directory (Join-Path $runDirectory 'addon')
    if ($LASTEXITCODE -ne 0) { throw 'Real Lua/C# contract validation failed.' }
    & $LuaPython -m unittest tests.test_read_live_receipt tests.test_experiment_core tests.test_experiment_adapter tests.test_native_field_evidence tests.test_native_old_epoch tests.test_targeted_health_snapshot tests.test_control_host tests.test_control_client tests.test_vm_console_native tests.test_nav_access_queue tests.test_nav_gateway_fence tests.test_nav_control_watchdog tests.test_control_transport tests.test_nav_startup_preflight tests.test_nav_supervisor_bootstrap tests.test_nav_owned_supervisor tests.test_control_lease_access tests.test_control_deny_first tests.test_vm_console_reservation tests.test_nav_host_runtime tests.test_coordinated_host_process tests.test_guest_receiver_startup tests.test_verify_guest_recovery tests.test_prepare_native_handover tests.test_compare_native_frames tests.test_serve_guest_native_scout
    if ($LASTEXITCODE -ne 0) { throw 'Host receipt, experiment, native-field evidence, targeted snapshot, native control, or navigation access queue tests failed.' }
    $reportPath = Join-Path $runDirectory 'analysis.json'
    $replayPath = Join-Path $runDirectory 'replay.json'
    $argsCommon = @('--manifest', 'samples/demo/capture.json', '--config', 'config/default.json')
    $validation = & dotnet $cli validate-capture @argsCommon
    if ($LASTEXITCODE -ne 0) { throw 'Capture validation smoke failed.' }
    if (-not (($validation -join "`n" | ConvertFrom-Json).valid)) { throw 'Capture did not report valid.' }
    & dotnet $cli analyze @argsCommon --output $reportPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Analysis smoke failed.' }
    & dotnet $cli analyze @argsCommon --output $replayPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Replay smoke failed.' }
    if ((Get-FileHash -LiteralPath $reportPath).Hash -ne (Get-FileHash -LiteralPath $replayPath).Hash) {
        throw 'Repeated analysis produced different report bytes.'
    }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $summary = $report.summary
    if ($report.evidenceKind -ne 'derived-motion' -or $summary.sampleCount -ne 5 -or
        $summary.missingSequenceCount -ne 1 -or $summary.sequenceGapCount -ne 1 -or
        $summary.timingGapCount -ne 1 -or $summary.derivedIntervalCount -ne 2 -or
        $summary.skippedDerivativeIntervalCount -ne 2 -or
        [Math]::Abs($summary.maxHorizontalDerivedSpeed - 5) -gt 0.000001 -or
        [Math]::Abs($summary.maxAbsoluteDerivedYawRate - 1) -gt 0.000001) {
        throw 'Synthetic analysis differs from independently calculated expectations.'
    }

    $linksChecked = 0
    $documents = @('README.md', 'AGENTS.md', 'artifacts/README.md') + @(Get-ChildItem -LiteralPath docs,samples,addon,contracts -Filter *.md -Recurse | ForEach-Object { $_.FullName })
    foreach ($document in $documents) {
        $fullPath = (Resolve-Path -LiteralPath $document).Path
        foreach ($match in [regex]::Matches((Get-Content -LiteralPath $fullPath -Raw), '\]\(([^)]+)\)')) {
            $target = $match.Groups[1].Value
            if ($target -match '^(https?://|#|[A-Za-z]:)') { continue }
            $target = ($target -split '#', 2)[0]
            if (-not $target) { continue }
            $linksChecked++
            if (-not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $fullPath) $target))) {
                throw "Broken link in ${document}: $target"
            }
        }
    }
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'Git whitespace check failed.' }
    git diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'Staged Git whitespace check failed.' }
    # Include untracked source files; git diff alone does not inspect new files.
    $repositoryFiles = @(git ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) { throw 'Git file enumeration failed.' }
    foreach ($file in $repositoryFiles) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
        if ([IO.Path]::GetExtension($file) -notin @('.cs', '.csproj', '.props', '.json', '.jsonl', '.slnx', '.ps1', '.md', '.Config', '.lua', '.toc', '.py', '.txt')) { continue }
        $content = [IO.File]::ReadAllText((Join-Path $repoRoot $file))
        if ($content -match '(?m)[ \t]+\r?$') { throw "Trailing whitespace: $file" }
        # NuGet owns lock-file formatting and emits these files without a final newline.
        if ([IO.Path]::GetFileName($file) -ne 'packages.lock.json' -and $content.Length -gt 0 -and -not $content.EndsWith("`n")) {
            throw "Missing final newline: $file"
        }
    }
    Write-Output "Validation passed: dependencies, locked restore, build, tests, format, Lua/C# contracts, deterministic demo, $linksChecked relative links. Evidence: $runDirectory"
}
finally {
    Pop-Location
}
