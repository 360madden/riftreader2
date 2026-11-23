function Resolve-ValidationDotNet {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$PinnedSdk,
        [string]$DotNet
    )

    Push-Location -LiteralPath $RepositoryRoot
    try {
        if ($DotNet) {
            $command = Get-Command -Name $DotNet -CommandType Application -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if (-not $command) {
                throw "Configured .NET executable was not found: $DotNet"
            }
            $candidates = @($command.Source)
        }
        else {
            $candidates = @(
                Get-Command -Name dotnet -CommandType Application -All -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty Source
                foreach ($root in @($env:DOTNET_ROOT_X64, $env:DOTNET_ROOT)) {
                    if ($root) { [IO.Path]::Combine($root, 'dotnet.exe') }
                }
                [IO.Path]::Combine($RepositoryRoot, 'artifacts', 'tools', 'dotnet', $PinnedSdk, 'dotnet.exe')
                [IO.Path]::Combine($RepositoryRoot, 'artifacts', 'tools', 'dotnet', 'dotnet.exe')
                foreach ($programDirectory in @($env:ProgramW6432, $env:ProgramFiles)) {
                    if ($programDirectory) { [IO.Path]::Combine($programDirectory, 'dotnet', 'dotnet.exe') }
                }
                if ($env:LOCALAPPDATA) { [IO.Path]::Combine($env:LOCALAPPDATA, 'Microsoft', 'dotnet', 'dotnet.exe') }
            )
            # Some developers keep each SDK in its own version-named installation.
            # Probe only the pinned sibling of an identified layout, without a disk scan.
            $candidates += @(
                foreach ($candidate in $candidates) {
                    $installDirectory = Split-Path -Parent $candidate
                    if ((Split-Path -Leaf $installDirectory) -match '^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$') {
                        $sdkParent = Split-Path -Parent $installDirectory
                        Join-Path (Join-Path $sdkParent $PinnedSdk) (Split-Path -Leaf $candidate)
                    }
                }
            )
        }

        foreach ($candidate in ($candidates | Select-Object -Unique)) {
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
            try {
                # Run from the repository so the CLI applies its global.json pin.
                $selectedSdk = & $candidate --version 2>$null
                if ($LASTEXITCODE -eq 0 -and ($selectedSdk -join "`n").Trim() -ceq $PinnedSdk) {
                    return (Get-Item -LiteralPath $candidate -ErrorAction Stop).FullName
                }
            }
            catch {
                # A failed native resolver is one unsuitable installation.
                continue
            }
        }
        if ($DotNet) {
            throw "Configured .NET executable '$DotNet' does not resolve SDK $PinnedSdk from global.json."
        }
        throw "Could not resolve .NET SDK $PinnedSdk from global.json. Pass -DotNet or set RIFTREADER2_DOTNET to the pinned executable."
    }
    finally {
        Pop-Location
    }
}
