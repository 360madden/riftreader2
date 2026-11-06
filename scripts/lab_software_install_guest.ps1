param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Git.Git', 'Python.Python.3.14', 'Microsoft.DotNet.SDK.10', 'OpenJS.NodeJS.LTS', 'Microsoft.WinAppCli')]
    [string]$PackageId,
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Guest-only development lab setup. This deliberately never requests a reboot.
trap {
    [IO.File]::WriteAllText(($ReportPath + '.error.txt'),
        ('installer-script-error:' + $_.Exception.GetType().Name + ':line=' +
         $_.InvocationInfo.ScriptLineNumber))
    exit 1
}

$report = [ordered]@{
    schemaVersion = 1
    method = 'winget-guest-install'
    machine = $env:COMPUTERNAME
    packageId = $PackageId
    checkedUtc = [DateTime]::UtcNow.ToString('o')
    status = 'blocked'
    exitCode = $null
    rebootPerformed = $false
    outputTail = ''
    reason = ''
}
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
$winget = Get-Command winget.exe -ErrorAction SilentlyContinue | Select-Object -First 1
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
if (-not $admin) {
    $report.reason = 'administrator-token-unavailable'
} elseif ($null -eq $winget) {
    $report.reason = 'winget-unavailable'
} elseif ($null -eq $disk -or [double]$disk.FreeSpace -lt 8GB) {
    $report.reason = 'insufficient-free-space'
} else {
    $report.status = 'failed'
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& $winget.Source install --id $PackageId --exact --source winget `
            --silent --accept-package-agreements --accept-source-agreements `
            --disable-interactivity --no-upgrade 2>&1)
        $code = [int]$LASTEXITCODE
        $report.exitCode = $code
        $report.status = $(if ($code -eq 0) { 'passed' } else { 'failed' })
        $report.reason = $(if ($code -eq 0) { 'install-command-completed' } else { 'winget-returned-nonzero' })
        $lastLines = ($lines | Select-Object -Last 18 | ForEach-Object { [string]$_ }) -join "\n"
        if ($lastLines.Length -gt 2500) { $lastLines = $lastLines.Substring($lastLines.Length - 2500) }
        $report.outputTail = $lastLines
    } catch {
        $report.status = 'failed'
        $report.reason = 'winget-invocation-failed:' + $_.Exception.GetType().Name
    }
}
$parent = [IO.Path]::GetDirectoryName($ReportPath)
[void][IO.Directory]::CreateDirectory($parent)
[IO.File]::WriteAllText($ReportPath, ($report | ConvertTo-Json -Depth 5),
    (New-Object Text.UTF8Encoding($false)))
