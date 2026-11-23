[CmdletBinding()]
param(
    [string]$LuaPython = $env:RIFTREADER2_LUA_PYTHON,
    [string]$DotNet = $env:RIFTREADER2_DOTNET,
    [switch]$CheckPrerequisites
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    if (-not $LuaPython) {
        $localLuaPython = Join-Path $repoRoot 'artifacts/tools/lua-python/Scripts/python.exe'
        $LuaPython = if (Test-Path -LiteralPath $localLuaPython) { $localLuaPython } else { 'python' }
    }
    if (-not $DotNet) { $DotNet = 'dotnet' }
    if (-not (Get-Command -Name $LuaPython -CommandType Application -ErrorAction SilentlyContinue)) {
        throw 'Python executable not found. Pass -LuaPython or set RIFTREADER2_LUA_PYTHON.'
    }
    & $LuaPython scripts/check_validation_python.py
    if ($LASTEXITCODE -ne 0) { throw 'Host test dependencies unavailable. Install requirements-validation.txt in the selected Python and include Tcl/Tk.' }
    & $LuaPython scripts/check_lua_runtime.py
    if ($LASTEXITCODE -ne 0) { throw 'Lua 5.1 test runtime missing. Install requirements-lua-tests.txt or pass -LuaPython; see docs/workflows/development.md.' }
    $pinnedSdk = (Get-Content -LiteralPath global.json -Raw | ConvertFrom-Json).sdk.version
    $dotnetCommand = Get-Command -Name $DotNet -CommandType Application -ErrorAction SilentlyContinue
    if (-not $dotnetCommand) {
        throw ".NET SDK $pinnedSdk executable not found. Pass -DotNet or set RIFTREADER2_DOTNET."
    }
    $DotNet = $dotnetCommand.Source
    # A resolver failure reports installed SDKs and exits nonzero when the pin is unavailable.
    $selectedSdk = & $DotNet --version
    if ($LASTEXITCODE -ne 0 -or ($selectedSdk -join "`n").Trim() -ne $pinnedSdk) {
        throw "Validation requires .NET SDK $pinnedSdk from global.json. Pass -DotNet or set RIFTREADER2_DOTNET to its executable."
    }
    if ($CheckPrerequisites) {
        Write-Output "Validation prerequisites available on $([Environment]::MachineName): .NET SDK $pinnedSdk and host Python test dependencies."
        return
    }
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

    & $DotNet restore $solution --locked-mode
    if ($LASTEXITCODE -ne 0) { throw 'Locked restore failed.' }
    & $DotNet build $solution --configuration Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Release build failed.' }
    & $DotNet build tools/RiftUpdateAnalyzer/RiftUpdateAnalyzer.csproj --configuration Release -p:RestoreLockedMode=true
    if ($LASTEXITCODE -ne 0) { throw 'RIFT Update Analyzer build for the Python tests failed.' }
    & $DotNet test $solution --configuration Release --no-build --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $DotNet format $solution --verify-no-changes --no-restore --verbosity minimal
    if ($LASTEXITCODE -ne 0) { throw 'Formatting verification failed.' }

    $cli = 'src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll'
    $runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $runDirectory = Join-Path 'artifacts/validation' $runId
    New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
    $nativePublish = Join-Path $runDirectory 'native-published'
    & $DotNet publish src/RiftReader2.Live/RiftReader2.Live.csproj --configuration Release --no-restore --output $nativePublish
    if ($LASTEXITCODE -ne 0) { throw 'Native executable publication failed.' }
    & (Join-Path $PSScriptRoot 'test-native-published.ps1') -Executable (Join-Path $nativePublish 'RiftReader2.Live.exe') -OutputDirectory (Join-Path $runDirectory 'native-smoke')
    $catalogArgs = @('qualify-fields', '--catalog', 'samples/catalog/catalog.json', '--build-sha256', ('A' * 64), '--session-id', 'synthetic-session-a', '--as-of', '2026-10-19T00:00:00Z')
    $catalogReport = Join-Path $runDirectory 'catalog.json'
    $catalogReplay = Join-Path $runDirectory 'catalog-replay.json'
    & $DotNet $cli @catalogArgs --output $catalogReport | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Catalog qualification smoke failed.' }
    & $DotNet $cli @catalogArgs --output $catalogReplay | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Catalog replay smoke failed.' }
    if ((Get-FileHash -LiteralPath $catalogReport).Hash -ne (Get-FileHash -LiteralPath $catalogReplay).Hash) {
        throw 'Catalog replay produced different report bytes.'
    }
    $catalogFields = (Get-Content -LiteralPath $catalogReport -Raw | ConvertFrom-Json).evaluation.fields
    if ($catalogFields.Count -ne 3 -or $catalogFields[0].status -ne 'supported-by-recorded-assessment' -or
        $catalogFields[1].status -ne 'contradicted' -or $catalogFields[2].status -ne 'unqualified') {
        throw 'Synthetic catalog qualification differs from expected scoped outcomes.'
    }
    & $LuaPython scripts/test-addon-contract.py --dotnet $DotNet --cli $cli --output-directory (Join-Path $runDirectory 'addon')
    if ($LASTEXITCODE -ne 0) { throw 'Real Lua/C# contract validation failed.' }
    # Run scheduler mocks in isolated Windows PowerShell processes. They replace
    # Scheduler functions in memory and never register or start real tasks.
    $windowsPowerShell = Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/powershell.exe'
    foreach ($helperTest in @('rr2_helper_manager_mock.ps1', 'rr2_legacy_helper_mock.ps1')) {
        & $windowsPowerShell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $repoRoot ('tests/' + $helperTest))
        if ($LASTEXITCODE -ne 0) { throw "Helper ownership mock failed: $helperTest" }
    }
    # Collect both unittest cases and pytest functions. Keep Qt off the desktop.
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    $previousDotNet = $env:RIFTREADER2_DOTNET
    try {
        $env:QT_QPA_PLATFORM = 'offscreen'
        $env:RIFTREADER2_DOTNET = $DotNet
        & $LuaPython -m pytest --disable-plugin-autoload -q tests
        if ($LASTEXITCODE -ne 0) { throw 'Host Python test suite failed.' }
    }
    finally {
        $env:QT_QPA_PLATFORM = $previousQtPlatform
        $env:RIFTREADER2_DOTNET = $previousDotNet
    }
    $reportPath = Join-Path $runDirectory 'analysis.json'
    $replayPath = Join-Path $runDirectory 'replay.json'
    $argsCommon = @('--manifest', 'samples/demo/capture.json', '--config', 'config/default.json')
    $validation = & $DotNet $cli validate-capture @argsCommon
    if ($LASTEXITCODE -ne 0) { throw 'Capture validation smoke failed.' }
    if (-not (($validation -join "`n" | ConvertFrom-Json).valid)) { throw 'Capture did not report valid.' }
    & $DotNet $cli analyze @argsCommon --output $reportPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Analysis smoke failed.' }
    & $DotNet $cli analyze @argsCommon --output $replayPath | Out-Null
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
