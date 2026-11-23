[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ExpectedHost,
    [string]$OutputDirectory,
    [string]$DotNet = $env:RIFTREADER2_DOTNET
)

$ErrorActionPreference = 'Stop'
$ownerHost = [Environment]::MachineName
if ($ExpectedHost -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$' -or $ExpectedHost -ine $ownerHost) {
    throw "Physical host mismatch. Expected '$ExpectedHost'; local host is '$ownerHost'."
}
if (-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Publishing the physical tools requires a 64-bit Windows host.'
}

$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'resolve-validation-dotnet.ps1')
if (-not $OutputDirectory) {
    $runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $OutputDirectory = Join-Path $repoRoot "artifacts/tools/physical/$runId"
}
$bundle = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
if ($bundle -notmatch '^[A-Za-z]:\\' -or [IO.DriveInfo]::new([IO.Path]::GetPathRoot($bundle)).DriveType -eq 'Network') {
    throw 'Publish output must use a local Windows drive.'
}
if (Test-Path -LiteralPath $bundle) {
    throw "Publish output already exists: $bundle"
}

$sdk = (Get-Content -LiteralPath (Join-Path $repoRoot 'global.json') -Raw | ConvertFrom-Json).sdk.version
$DotNet = Resolve-ValidationDotNet -RepositoryRoot $repoRoot -PinnedSdk $sdk -DotNet $DotNet

function Publish-PhysicalExecutable([string]$Project, [string]$Destination) {
    & $DotNet restore $Project --locked-mode -p:SelfContained=true | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Locked restore failed: $Project" }
    & $DotNet publish $Project --configuration Release --no-restore --self-contained true --output $Destination | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Publish failed: $Project" }
}

$readerDirectory = Join-Path $bundle 'native-reader'
$probeDirectory = Join-Path $bundle 'wgc-probe'
$reader = Join-Path $readerDirectory 'RiftReader2.Live.exe'
$probe = Join-Path $probeDirectory 'PhysicalWgcProbe.exe'
$previousGuiErrors = $env:DOTNET_DISABLE_GUI_ERRORS
Push-Location -LiteralPath $repoRoot
try {
    New-Item -ItemType Directory -Path $bundle | Out-Null
    Publish-PhysicalExecutable 'src/RiftReader2.Live/RiftReader2.Live.csproj' $readerDirectory
    Publish-PhysicalExecutable 'tools/physical-wgc-probe/PhysicalWgcProbe.csproj' $probeDirectory

    $env:DOTNET_DISABLE_GUI_ERRORS = '1'
    $readerHelp = & $reader --help
    if ($LASTEXITCODE -ne 0 -or $readerHelp[0] -cne 'RiftReader2.Live native tools') {
        throw 'Published native reader failed its startup check.'
    }
    $probeOutput = & $probe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Published WGC probe failed its offline self-test.' }
    $probeResult = $probeOutput | ConvertFrom-Json
    if ($probeResult.status -cne 'offline-self-test-passed' -or $probeResult.passed -lt 1 -or
        $probeResult.outputCheckoutDiscovery -ne $true -or
        $probeResult.inputSent -ne $false -or $probeResult.frameCaptured -ne $false) {
        throw 'Published WGC probe returned an invalid offline self-test report.'
    }
    [pscustomobject]@{
        Host = $ownerHost
        Sdk = $sdk
        Directory = $bundle
        NativeReader = $reader
        WgcProbe = $probe
        WgcChecksPassed = $probeResult.passed
    }
}
finally {
    $env:DOTNET_DISABLE_GUI_ERRORS = $previousGuiErrors
    Pop-Location
}
