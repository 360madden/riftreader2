[CmdletBinding(DefaultParameterSetName = 'Publish')]
param(
    [Parameter(Mandatory)][string]$ExpectedHost,
    [Parameter(ParameterSetName = 'Publish')][string]$OutputDirectory,
    [Parameter(ParameterSetName = 'Publish')][string]$DotNet = $env:RIFTREADER2_DOTNET,
    [Parameter(ParameterSetName = 'Publish')][switch]$UseForCheckout,
    [Parameter(ParameterSetName = 'Register', Mandatory)][string]$RegisterBundle
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
$publish = $PSCmdlet.ParameterSetName -eq 'Publish'
if (-not $publish) {
    $OutputDirectory = $RegisterBundle
}
elseif (-not $OutputDirectory) {
    $runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $OutputDirectory = Join-Path $repoRoot "artifacts/tools/physical/$runId"
}
$bundle = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
if ($bundle -notmatch '^[A-Za-z]:\\' -or [IO.DriveInfo]::new([IO.Path]::GetPathRoot($bundle)).DriveType -eq 'Network') {
    throw 'Physical tools must use a local Windows drive.'
}

function Publish-PhysicalExecutable([string]$Project, [string]$Destination) {
    & $DotNet restore $Project --locked-mode -p:SelfContained=true | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Locked restore failed: $Project" }
    & $DotNet publish $Project --configuration Release --no-restore --self-contained true --output $Destination | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Publish failed: $Project" }
}

function Assert-PlainPath([string]$Path) {
    for ($current = $Path; $current; $current = [IO.Path]::GetDirectoryName($current)) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Physical tools paths cannot contain links or junctions: $current"
        }
    }
}

function Register-PhysicalTools([string]$Path, [string]$BundleRoot, [string]$ComputerName) {
    Assert-PlainPath $Path
    $directory = [IO.Path]::GetDirectoryName($Path)
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporary = Join-Path $directory ('.physical-tools-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $registration = @{schema = 'rr2-physical-tools/1'; host = $ComputerName; root = $BundleRoot} | ConvertTo-Json
        [IO.File]::WriteAllText($temporary, $registration)
        [IO.File]::Move($temporary, $Path, $true)
    }
    finally { [IO.File]::Delete($temporary) }
}

$readerDirectory = Join-Path $bundle 'native-reader'
$probeDirectory = Join-Path $bundle 'wgc-probe'
$reader = Join-Path $readerDirectory 'RiftReader2.Live.exe'
$probe = Join-Path $probeDirectory 'PhysicalWgcProbe.exe'
$sdk = $null
$registrationPath = $null
if (-not $publish -or $UseForCheckout) {
    $registrationPath = Join-Path $repoRoot '.local/physical-tools.json'
    Assert-PlainPath $registrationPath
}
Assert-PlainPath $reader
Assert-PlainPath $probe
$previousGuiErrors = $env:DOTNET_DISABLE_GUI_ERRORS
Push-Location -LiteralPath $repoRoot
try {
    if ($publish) {
        if (Test-Path -LiteralPath $bundle) { throw "Publish output already exists: $bundle" }
        . (Join-Path $PSScriptRoot 'resolve-validation-dotnet.ps1')
        $sdk = (Get-Content -LiteralPath (Join-Path $repoRoot 'global.json') -Raw | ConvertFrom-Json).sdk.version
        $DotNet = Resolve-ValidationDotNet -RepositoryRoot $repoRoot -PinnedSdk $sdk -DotNet $DotNet
        New-Item -ItemType Directory -Path $bundle | Out-Null
        Publish-PhysicalExecutable 'src/RiftReader2.Live/RiftReader2.Live.csproj' $readerDirectory
        Publish-PhysicalExecutable 'tools/physical-wgc-probe/PhysicalWgcProbe.csproj' $probeDirectory
    }
    if (-not (Test-Path -LiteralPath $reader -PathType Leaf) -or -not (Test-Path -LiteralPath $probe -PathType Leaf)) {
        throw "Physical tools bundle is missing the reader or WGC probe: $bundle"
    }

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
    if ($registrationPath) { Register-PhysicalTools $registrationPath $bundle $ownerHost }
    [pscustomobject]@{
        Host = $ownerHost
        Sdk = $sdk
        Directory = $bundle
        NativeReader = $reader
        WgcProbe = $probe
        WgcChecksPassed = $probeResult.passed
        Registration = $registrationPath
    }
}
finally {
    $env:DOTNET_DISABLE_GUI_ERRORS = $previousGuiErrors
    Pop-Location
}
