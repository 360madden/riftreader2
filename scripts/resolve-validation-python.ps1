function Get-ValidationPythonError {
    param([string]$Executable, [string]$RepositoryRoot)

    $PSNativeCommandUseErrorActionPreference = $false
    foreach ($probe in @('check_validation_python.py', 'check_lua_runtime.py')) {
        $scriptPath = Join-Path (Join-Path $RepositoryRoot 'scripts') $probe
        try {
            $messages = & $Executable -B $scriptPath 2>&1
            if ($LASTEXITCODE -ne 0) {
                return "$probe exited ${LASTEXITCODE}. $($messages -join [Environment]::NewLine)"
            }
        }
        catch {
            return "$probe failed. $($_.Exception.Message)"
        }
    }
}

function Resolve-ValidationPython {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [string]$Python
    )

    if ($Python) {
        $command = Get-Command -Name $Python -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $command) {
            throw "Configured Python executable was not found: $Python"
        }
        $failure = Get-ValidationPythonError -Executable $command.Source -RepositoryRoot $RepositoryRoot
        if ($failure) {
            throw "Configured Python '$($command.Source)' failed validation prerequisites. $failure"
        }
        return $command.Source
    }

    $candidates = @(
        Join-Path $RepositoryRoot 'artifacts/tools/lua-python/Scripts/python.exe'
        Join-Path $RepositoryRoot '.venv/Scripts/python.exe'
        if ($env:RIFTREADER2_PYTHON -and [IO.Path]::IsPathFullyQualified($env:RIFTREADER2_PYTHON)) {
            $env:RIFTREADER2_PYTHON
        }
        Get-Command -Name python -CommandType Application -All -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Source
    )
    $failed = [System.Collections.Generic.List[string]]::new()
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        # The Windows Store stub can open an installer when no interpreter is present.
        if ($candidate -match '(?i)[\\/]Microsoft[\\/]WindowsApps[\\/]python\.exe$') { continue }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $failure = Get-ValidationPythonError -Executable $candidate -RepositoryRoot $RepositoryRoot
        if (-not $failure) { return $candidate }
        $failed.Add("${candidate}: $failure")
    }

    $launcher = Get-Command -Name py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        # Listing registered paths avoids invoking the launcher in install mode.
        $installed = try {
            $listed = & $launcher.Source -0p 2>$null
            if ($LASTEXITCODE -eq 0) { $listed }
        }
        catch {
            # A broken launcher provides no additional candidates.
        }
        foreach ($line in $installed) {
            if ($line -notmatch '^\s*-\S+\s+(?:\*\s+)?(.+?\.exe)\s*$') { continue }
            $candidate = $Matches[1]
            if ($candidate -in $candidates -or -not [IO.Path]::IsPathFullyQualified($candidate) -or
                -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
            $candidates += $candidate
            $failure = Get-ValidationPythonError -Executable $candidate -RepositoryRoot $RepositoryRoot
            if (-not $failure) { return $candidate }
            $failed.Add("${candidate}: $failure")
        }
    }

    $details = $failed -join [Environment]::NewLine
    throw "No Python with the validation dependencies was found. Install requirements-validation.txt in a Python environment with Tcl/Tk, or set -LuaPython or RIFTREADER2_LUA_PYTHON to a prepared interpreter.`n$details"
}
