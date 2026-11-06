param(
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProgressPreference = 'SilentlyContinue'

$source = 'https://download.sysinternals.com/files/SysinternalsSuite.zip'
$target = 'C:\Tools\Sysinternals'
$report = [ordered]@{
    schemaVersion = 1
    method = 'official-microsoft-portable-zip'
    machine = $env:COMPUTERNAME
    source = $source
    target = $target
    checkedUtc = [DateTime]::UtcNow.ToString('o')
    status = 'failed'
    reason = ''
    zipSha256 = ''
    rebootPerformed = $false
    tools = @()
}
$scratch = $null

function Verify-Tools([string]$Directory) {
    $names = [ordered]@{
        'Process Explorer' = @('procexp64.exe', 'procexp.exe')
        'Process Monitor'  = @('procmon64.exe', 'procmon.exe')
        'Autoruns'         = @('Autoruns64.exe', 'Autoruns.exe')
        'TCPView'          = @('Tcpview64.exe', 'Tcpview.exe')
        'ProcDump'         = @('procdump64.exe', 'procdump.exe')
    }
    $files = @(Get-ChildItem -LiteralPath $Directory -File -Recurse)
    $results = @()
    foreach ($label in $names.Keys) {
        $allowed = $names[$label]
        $file = $files | Where-Object { $allowed -contains $_.Name } | Select-Object -First 1
        if ($null -eq $file) { throw "missing-tool:$label" }
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        if ($signature.Status -ne 'Valid' -or
            $null -eq $signature.SignerCertificate -or
            $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
            throw "invalid-microsoft-signature:$($label):$($signature.Status)"
        }
        $results += [ordered]@{
            name = $label
            file = $file.Name
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
            signature = 'Valid'
            signer = $signature.SignerCertificate.Subject
        }
    }
    return $results
}

try {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { throw 'administrator-token-unavailable' }
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    if ($null -eq $disk -or [double]$disk.FreeSpace -lt 1GB) { throw 'insufficient-free-space' }
    if (Test-Path -LiteralPath $target) {
        $report.tools = @(Verify-Tools $target)
        $report.status = 'passed'
        $report.reason = 'already-present-and-verified'
    } else {
        $scratch = Join-Path $env:TEMP ('sysinternals-portable-' + [guid]::NewGuid().ToString('N'))
        [void][IO.Directory]::CreateDirectory($scratch)
        $zip = Join-Path $scratch 'SysinternalsSuite.zip'
        $unpacked = Join-Path $scratch 'unpacked'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $source -UseBasicParsing -OutFile $zip -TimeoutSec 240
        $zipFile = Get-Item -LiteralPath $zip
        if ($zipFile.Length -lt 50MB -or $zipFile.Length -gt 500MB) { throw 'unexpected-zip-size' }
        $report.zipSha256 = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
        Expand-Archive -LiteralPath $zip -DestinationPath $unpacked
        $report.tools = @(Verify-Tools $unpacked)
        [void][IO.Directory]::CreateDirectory('C:\Tools')
        if (Test-Path -LiteralPath $target) { throw 'target-created-concurrently' }
        [IO.Directory]::Move($unpacked, $target)
        $report.tools = @(Verify-Tools $target)
        $report.status = 'passed'
        $report.reason = 'installed-and-microsoft-signatures-verified'
    }
} catch {
    $report.status = 'failed'
    $report.reason = [string]$_.Exception.Message
} finally {
    if ($null -ne $scratch -and (Test-Path -LiteralPath $scratch)) {
        try { [IO.Directory]::Delete($scratch, $true) } catch {}
    }
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($ReportPath))
    [IO.File]::WriteAllText($ReportPath, ($report | ConvertTo-Json -Depth 6),
        (New-Object Text.UTF8Encoding($false)))
}
