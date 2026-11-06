param(
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# VMware vmrun hides failed guest program output. Record sanitized diagnostics.
trap {
    $kind = $_.Exception.GetType().Name
    $line = $_.InvocationInfo.ScriptLineNumber
    [IO.File]::WriteAllText(($ReportPath + '.error.txt'),
        ('guest-script-error:' + $kind + ':line=' + $line))
    exit 1
}

function Get-VersionProbe {
    param([string]$Name, [string[]]$Arguments)
    $entry = Get-Command -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $entry) { return @{ present = $false } }
    $path = [string]$entry.Source
    try {
        # Drain native output completely before truncating text. Early pipeline closure can
        # make a chatty CLI (e.g. WinApp) report a false nonzero exit code.
        $lines = @(& $path @Arguments 2>&1)
        $result = (($lines | ForEach-Object { [string]$_ }) -join ' ').Trim()
        if ($result.Length -gt 600) { $result = $result.Substring(0, 600) }
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
        return @{ present = $true; path = $path; output = $result; exitCode = [int]$code }
    } catch {
        return @{ present = $true; path = $path; error = 'version-probe-failed' }
    }
}


function Get-FirstVersionProbe {
    param([string[]]$Candidates, [string[]]$Arguments)
    foreach ($candidate in $Candidates) {
        $probe = Get-VersionProbe -Name $candidate -Arguments $Arguments
        if ($probe.present -and -not $probe.ContainsKey('error') -and $probe.exitCode -eq 0) {
            return $probe
        }
    }
    return @{ present = $false }
}

$tools = [ordered]@{
    powershell51 = @{ present = $true; output = [string]$PSVersionTable.PSVersion }
    pwsh = Get-VersionProbe 'pwsh.exe' @('--version')
    python = Get-VersionProbe 'python.exe' @('--version')
    python314 = Get-FirstVersionProbe @('C:\Python314\python.exe', "$env:ProgramFiles\Python314\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe") @('--version')
    pip = Get-FirstVersionProbe @('C:\Python314\python.exe', "$env:ProgramFiles\Python314\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe") @('-m', 'pip', '--version')
    pyLauncher = Get-VersionProbe 'py.exe' @('--list-paths')
    dotnetSdk = Get-FirstVersionProbe @("$env:ProgramFiles\dotnet\dotnet.exe", 'dotnet.exe') @('--list-sdks')
    dotnetRuntimes = Get-FirstVersionProbe @("$env:ProgramFiles\dotnet\dotnet.exe", 'dotnet.exe') @('--list-runtimes')
    node = Get-FirstVersionProbe @("$env:ProgramFiles\nodejs\node.exe", 'node.exe') @('--version')
    npm = Get-FirstVersionProbe @("$env:ProgramFiles\nodejs\npm.cmd", 'npm.cmd') @('--version')
    git = Get-FirstVersionProbe @("$env:ProgramFiles\Git\cmd\git.exe", 'git.exe') @('--version')
    ssh = Get-VersionProbe 'ssh.exe' @('-V')
    winapp = Get-VersionProbe 'winapp.exe' @('--version')
    winget = Get-VersionProbe 'winget.exe' @('--version')
}
# Metadata only: never invoke discovery/debugging executables or query Win32_Product.
$portableRoots = @('C:\Tools\Sysinternals')
$portableNames = @('procmon', 'procexp', 'procdump', 'handle', 'listdlls',
    'vmmap', 'rammap', 'sigcheck', 'tcpview', 'autoruns')
$portableFiles = @()
foreach ($root in $portableRoots) {
    foreach ($name in $portableNames) {
        foreach ($suffix in @('.exe', '64.exe', '64a.exe')) {
            $candidate = Join-Path $root ($name + $suffix)
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                try {
                    $file = Get-Item -LiteralPath $candidate -ErrorAction Stop
                    $portableFiles += @{ path = $candidate; name = $file.Name;
                        version = [string]$file.VersionInfo.FileVersion;
                        sha256 = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256 -ErrorAction Stop).Hash }
                } catch {
                    $portableFiles += @{ path = $candidate; name = ($name + $suffix); error = 'metadata-read-failed' }
                }
            }
        }
    }
}
$uninstallRoots = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')
$applications = @()
$registryScopes = @()
foreach ($root in $uninstallRoots) {
    $keys = @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue | Select-Object -First 1025)
    $registryScopes += @{ path = $root; examined = [math]::Min($keys.Count, 1024); truncated = ($keys.Count -gt 1024) }
    foreach ($key in ($keys | Select-Object -First 1024)) {
        $item = Get-ItemProperty -LiteralPath $key.PSPath -ErrorAction SilentlyContinue
        if ($null -eq $item) { continue }
        $displayName = $item.PSObject.Properties['DisplayName']
        if ($null -eq $displayName) { continue }
        $name = [string]$displayName.Value
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        if ($applications.Count -ge 128) { continue }
        $version = $item.PSObject.Properties['DisplayVersion']
        $publisher = $item.PSObject.Properties['Publisher']
        $applications += @{ name = $name.Substring(0, [math]::Min(200, $name.Length));
            version = $(if ($version) { ([string]$version.Value).Substring(0, [math]::Min(100, ([string]$version.Value).Length)) } else { '' });
            publisher = $(if ($publisher) { ([string]$publisher.Value).Substring(0, [math]::Min(100, ([string]$publisher.Value).Length)) } else { '' });
            registryRoot = $root }
    }
}
$discovery = @{ method = 'file-and-uninstall-metadata-only'; portableRoots = $portableRoots;
    sysinternalsFiles = $portableFiles; uninstallScopes = $registryScopes;
    applications = $applications; applicationLimitReached = ($applications.Count -ge 128) }
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction Stop
$vmtools = Get-Service -Name VMTools -ErrorAction SilentlyContinue
$vmtoolsVersion = $null
$vmtoolsReg = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\VMware, Inc.\VMware Tools' -ErrorAction SilentlyContinue
if ($null -ne $vmtoolsReg -and $null -ne $vmtoolsReg.PSObject.Properties['Version']) {
    $vmtoolsVersion = [string]$vmtoolsReg.PSObject.Properties['Version'].Value
}
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$report = [ordered]@{
    schemaVersion = 1
    method = 'read-only-software-inventory'
    machine = $env:COMPUTERNAME
    checkedUtc = [DateTime]::UtcNow.ToString('o')
    os = @{ caption = [string]$os.Caption; version = [string]$os.Version; build = [string]$os.BuildNumber; architecture = [string]$os.OSArchitecture }
    memoryGiB = [math]::Round(([double]$computer.TotalPhysicalMemory / 1GB), 2)
    diskCFreeGiB = [math]::Round(([double]$disk.FreeSpace / 1GB), 2)
    vmwareTools = @{ present = ($null -ne $vmtools); status = $(if ($vmtools) { [string]$vmtools.Status } else { 'absent' }); version = $vmtoolsVersion }
    elevatedToken = [bool]$admin
    tools = $tools
    discovery = $discovery
}
$directory = [IO.Path]::GetDirectoryName($ReportPath)
[void][IO.Directory]::CreateDirectory($directory)
[IO.File]::WriteAllText($ReportPath, ($report | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
