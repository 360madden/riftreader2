param(
    [Parameter(Mandatory=$true)][string]$AddonDirectory,
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Fixed allowlist: never read SavedVariables or descend into fonts.
$names = @('RiftAddon.toc','Version.lua','Bootstrap.lua','Theme.lua',
           'Collector.lua','Navigation.lua','Presentation.lua','UI.lua','Public.lua')
$maxFile = 131072
$maxTotal = 262144

function Test-CloudReparse([string]$Path) {
    $fsutil = Join-Path $env:SystemRoot 'System32\fsutil.exe'
    $lines = @(& $fsutil reparsepoint query $Path 2>$null)
    if ($LASTEXITCODE -ne 0 -or $lines.Count -eq 0) { return $false }
    $match = [regex]::Match([string]$lines[0], '0x([0-9a-fA-F]{8})')
    if (-not $match.Success) { return $false }
    $tag = [Convert]::ToUInt32($match.Groups[1].Value, 16)
    return (([uint64]$tag -band [uint64]4294905855) -eq [uint64]2415919130)
}

$result = [ordered]@{
    schemaVersion = 1
    method = 'sha256-read-only'
    addon = 'ApiAtlas'
    machine = $env:COMPUTERNAME
    timestampUtc = [DateTime]::UtcNow.ToString('o')
    addonDirectory = $AddonDirectory
    complete = $false
    files = @()
    error = $null
}
try {
    $directory = Get-Item -LiteralPath $AddonDirectory -Force
    if (-not $directory.PSIsContainer) { throw 'not-an-addon-directory' }
    $rootFlags = [int64]$directory.Attributes
    if (($rootFlags -band 4096) -or ($rootFlags -band 1048576) -or
        ($rootFlags -band 262144) -or ($rootFlags -band 4194304)) {
        throw 'addon-directory-cloud-recall-risk'
    }
    if ($directory.LinkType) { throw 'unsupported-addon-directory-link' }
    if (($rootFlags -band 1024) -and
        ((($rootFlags -band 524288) -eq 0) -or -not (Test-CloudReparse $directory.FullName))) {
        throw 'unsupported-addon-directory-reparse'
    }

    # Inspect all nine sizes before opening any content.
    $items = @()
    $total = [long]0
    foreach ($name in $names) {
        $path = Join-Path $directory.FullName $name
        $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        if ($null -eq $item) {
            $items += $null
        } else {
            $items += $item
            if (-not $item.PSIsContainer) { $total += [long]$item.Length }
        }
    }
    if ($total -gt $maxTotal) { throw 'total-file-bytes-limit' }

    for ($index = 0; $index -lt $names.Count; $index++) {
        $name = [string]$names[$index]
        $item = $items[$index]
        $row = [ordered]@{
            name = $name
            status = 'missing'
            bytes = $null
            modifiedUtc = $null
            pinned = $false
            reparse = $false
            sha256 = $null
        }
        if ($null -ne $item) {
            $flags = [int64]$item.Attributes
            $row.bytes = $(if ($item.PSIsContainer) { $null } else { [long]$item.Length })
            $row.modifiedUtc = $item.LastWriteTimeUtc.ToString('o')
            $row.pinned = ($flags -band 524288) -ne 0
            $row.reparse = ($flags -band 1024) -ne 0
            $unsafe = ($flags -band 4096) -or ($flags -band 1048576) -or
                      ($flags -band 262144) -or ($flags -band 4194304) -or
                      ($row.reparse -and -not $row.pinned) -or
                      ($row.reparse -and -not (Test-CloudReparse $item.FullName))
            if ($item.PSIsContainer -or $unsafe -or $item.LinkType -or $item.Name -cne $name) {
                $row.status = 'unsafe'
            } elseif ($row.bytes -le 0 -or $row.bytes -gt $maxFile) {
                $row.status = 'too-large'
            } else {
                try {
                    # Pinned cloud files may still hydrate; read only this bounded file.
                    $row.sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
                    $after = Get-Item -LiteralPath $item.FullName -Force
                    if ($after.Length -ne $row.bytes -or
                        $after.LastWriteTimeUtc.Ticks -ne $item.LastWriteTimeUtc.Ticks -or
                        $after.Attributes -ne $item.Attributes) {
                        $row.sha256 = $null
                        $row.status = 'changed-during-read'
                    } else {
                        $row.status = 'hashed'
                    }
                } catch {
                    $row.sha256 = $null
                    $row.status = 'read-error'
                }
            }
        }
        $result.files += [pscustomobject]$row
    }
    $incomplete = @($result.files | Where-Object { $_.status -ne 'hashed' })
    $result.complete = ($incomplete.Count -eq 0)
} catch {
    $result.error = 'hash-failed:' + $_.Exception.GetType().Name + ':' + $_.Exception.Message
} finally {
    $parent = Split-Path -Parent $ReportPath
    [void](New-Item -ItemType Directory -Path $parent -Force)
    if ([IO.File]::Exists($ReportPath)) { throw 'hash-report-exists' }
    [IO.File]::WriteAllText($ReportPath,
        (($result | ConvertTo-Json -Depth 5) + [Environment]::NewLine),
        (New-Object System.Text.UTF8Encoding($false)))
}
