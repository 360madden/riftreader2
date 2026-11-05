param(
    [Parameter(Mandatory=$true)][string]$AddonRoot,
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# Windows fsutil queries the reparse tag without opening cloud content.
# Cloud Files family tags are 0x9000001A through 0x9000F01A.
function Test-CloudReparse([string]$Path) {
    $fsutil = Join-Path $env:SystemRoot 'System32\fsutil.exe'
    $lines = @(& $fsutil reparsepoint query $Path 2>$null)
    if ($LASTEXITCODE -ne 0 -or $lines.Count -eq 0) { return $false }
    $match = [regex]::Match([string]$lines[0], '0x([0-9a-fA-F]{8})')
    if (-not $match.Success) { return $false }
    $tag = [Convert]::ToUInt32($match.Groups[1].Value, 16)
    # UInt64 decimal constants avoid signed high-bit hex behavior in PS 5.1.
    return (([uint64]$tag -band [uint64]4294905855) -eq [uint64]2415919130)
}
$result = [ordered]@{
    schemaVersion = 1
    method = 'metadata-only'
    machine = $env:COMPUTERNAME
    timestampUtc = [DateTime]::UtcNow.ToString('o')
    addonRoot = $AddonRoot
    rootReparse = $false
    complete = $false
    success = $false
    entries = @()
    warnings = @()
    error = $null
}
try {
    $root = Get-Item -LiteralPath $AddonRoot -Force -ErrorAction Stop
    if (-not $root.PSIsContainer) { throw 'addon-root-not-directory' }
    $result.rootReparse = (([int64]$root.Attributes -band 1024) -ne 0)
    if ($result.rootReparse -and -not (Test-CloudReparse $root.FullName)) {
        throw 'unsupported-addon-root-reparse'
    }
    $items = @(Get-ChildItem -LiteralPath $AddonRoot -Force -ErrorAction Stop)
    if ($items.Count -gt 300) { throw 'addon-root-too-many-entries' }
    $entries = @()
    $warnings = @()
    foreach ($item in ($items | Sort-Object Name)) {
        $attributes = [int64]$item.Attributes
        $offline = ($attributes -band 4096) -ne 0
        $reparse = ($attributes -band 1024) -ne 0
        # Only pinned, verified Cloud Files reparse directories are enumerated.
        # Get-ChildItem requests TOC metadata; no file content is opened.
        $cloudFolder = $item.PSIsContainer -and $reparse -and -not $offline -and
            (($attributes -band 524288) -ne 0) -and [string]::IsNullOrEmpty([string]$item.LinkType) -and
            (Test-CloudReparse $item.FullName)
        $canInspect = $item.PSIsContainer -and -not $offline -and (-not $reparse -or $cloudFolder)
        $kind = if ($item.PSIsContainer) { 'directory' } else { 'file' }
        $toc = @()
        if ($canInspect) {
            $tocFiles = @(Get-ChildItem -LiteralPath $item.FullName -Filter '*.toc' -File -Force -ErrorAction Stop)
            if ($tocFiles.Count -gt 20) { throw 'addon-too-many-toc-files' }
            foreach ($file in ($tocFiles | Sort-Object Name)) {
                $flags = [int64]$file.Attributes
                $toc += [pscustomobject]@{
                    name = [string]$file.Name
                    bytes = [long]$file.Length
                    modifiedUtc = $file.LastWriteTimeUtc.ToString('o')
                    offline = ($flags -band 4096) -ne 0
                    reparse = ($flags -band 1024) -ne 0
                }
            }
        }
        if ($item.PSIsContainer -and -not $canInspect) {
            $warnings += 'toc-uninspected:' + [string]$item.Name
        }
        $entries += [pscustomobject]@{
            name = [string]$item.Name
            kind = $kind
            modifiedUtc = $item.LastWriteTimeUtc.ToString('o')
            offline = $offline
            reparse = $reparse
            cloudReparse = [bool]$cloudFolder
            toc = @($toc)
        }
    }
    $result.entries = @($entries)
    $result.warnings = @($warnings)
    $result.complete = $warnings.Count -eq 0
    $result.success = $true
} catch {
    $result.error = 'inventory-failed:' + $_.Exception.GetType().Name
} finally {
    $parent = Split-Path -Parent $ReportPath
    [void](New-Item -ItemType Directory -Path $parent -Force -ErrorAction Stop)
    if ([IO.File]::Exists($ReportPath)) { throw 'inventory-report-exists' }
    [IO.File]::WriteAllText($ReportPath, (($result | ConvertTo-Json -Depth 7) + "`n"),
        (New-Object System.Text.UTF8Encoding($false)))
}

