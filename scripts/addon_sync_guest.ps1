param(
    [Parameter(Mandatory=$true)][ValidateSet('check','sync','verify')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$SourceDirectory,
    [Parameter(Mandatory=$true)][string]$Destination,
    [Parameter(Mandatory=$true)][string]$ManifestPath,
    [Parameter(Mandatory=$true)][string]$ReportPath,
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [switch]$NoPin
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$names = @('RiftAddon.toc','wire.lua','producer.lua','reference.lua','live.lua','guidance.lua','main.lua')
$manifest=$null
$phase='initial'
$result = [ordered]@{ schemaVersion=1; mode=$Mode; machine=$env:COMPUTERNAME;
    timestampUtc=[DateTime]::UtcNow.ToString('o'); destination=$Destination;
    before=@(); after=@(); updated=@(); backups=@(); success=$false; error=$null }
function Hash-File([string]$Path) {
    $stream=[IO.File]::OpenRead($Path)
    $hasher=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
function Inspect-Installed([string]$Name,[string]$Expected) {
    $p = Join-Path $Destination $Name
    $entry = [ordered]@{name=$Name; present=$false; offline=$false; pinned=$false;
        unpinned=$false; recallOnOpen=$false; recallOnDataAccess=$false;
        sha256=$null; expectedSha256=$Expected; matches=$false; reason='missing'}
    if ([IO.File]::Exists($p)) {
        $i=Get-Item -LiteralPath $p -Force -ErrorAction Stop
        $entry.present=$true
        $flags=[int64]$i.Attributes
        $entry.offline=($flags -band 4096) -ne 0
        $entry.pinned=($flags -band 524288) -ne 0
        $entry.unpinned=($flags -band 1048576) -ne 0
        $entry.recallOnOpen=($flags -band 262144) -ne 0
        $entry.recallOnDataAccess=($flags -band 4194304) -ne 0
        if ($entry.offline) { $entry.reason='offline' }
        elseif ($entry.unpinned) { $entry.reason='not-pinned' }
        elseif ($entry.recallOnOpen -or $entry.recallOnDataAccess) {
            # Never invoke Hash-File on files Windows says may require recall.
            $entry.reason='cloud-recall-risk'
        }
        else {
            try {
                $entry.sha256=Hash-File $p
                if ($entry.sha256 -ne $Expected) { $entry.reason='hash-mismatch' }
                elseif (-not $NoPin -and -not $entry.pinned) { $entry.reason='not-pinned' }
                else { $entry.matches=$true; $entry.reason='ok' }
            } catch { $entry.reason='unreadable' }
        }
    }
    return [pscustomobject]$entry
}
try {
    $manifest=Get-Content -LiteralPath $ManifestPath -Raw -ErrorAction Stop | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1 -or $null -eq $manifest.files) { throw 'manifest-invalid' }
    foreach ($n in $names) {
        $property=$manifest.files.PSObject.Properties[$n]
        if ($null -eq $property -or [string]$property.Value -notmatch '^[0-9A-Fa-f]{64}$') {
            throw 'manifest-file-invalid'
        }
    }
    if (-not [IO.Directory]::Exists($Destination)) { throw 'addon-directory-missing' }
    $result.before=@(foreach ($n in $names) { Inspect-Installed $n ([string]$manifest.files.$n) })
    if ($Mode -eq 'sync') {
        # Verify the complete candidate set before changing any installed file.
        foreach ($n in $names) {
            $source=Join-Path $SourceDirectory $n
            if (-not [IO.File]::Exists($source) -or (Hash-File $source) -ne [string]$manifest.files.$n) {
                throw 'staged-source-mismatch'
            }
        }
        foreach ($n in $names) {
            $phase='inspect-current:'+$n
            $current=@($result.before | Where-Object { $_.name -eq $n })[0]
            if ($current.matches) { continue }
            $dst=Join-Path $Destination $n
            if ($current.reason -eq 'not-pinned') {
                if (-not $NoPin) { & attrib.exe +P -U $dst | Out-Null; if ($LASTEXITCODE -ne 0) {throw 'pin-failed'} }
                $result.updated+=($n + ':pinned')
                continue
            }
            $candidate=Join-Path $SourceDirectory $n
            $staged=$dst + '.addon-sync-stage-' + [Guid]::NewGuid().ToString('N')
            $oldBackup=$null
            try {
                $phase='copy-stage:'+$n
                Copy-Item -LiteralPath $candidate -Destination $staged -ErrorAction Stop
                $phase='hash-stage:'+$n
                if ((Hash-File $staged) -ne [string]$manifest.files.$n) { throw 'staging-hash-mismatch' }
                if ([IO.File]::Exists($dst)) {
                    if ($current.offline) {
                        # An unhydrated OneDrive placeholder may refuse a move out
                        # of its sync provider. Rename it beside the original,
                        # as established by the October 30 Lab 1 repair.
                        $oldBackup=$dst + '.offline-backup-' + [Guid]::NewGuid().ToString('N')
                    } else {
                        $phase='create-backup-dir:'+$n
                        [void](New-Item -ItemType Directory -Path $BackupDirectory -Force -ErrorAction Stop)
                        $oldBackup=Join-Path $BackupDirectory ($n + '.' + [Guid]::NewGuid().ToString('N') + '.backup')
                    }
                    $phase='move-old:'+$n
                    Move-Item -LiteralPath $dst -Destination $oldBackup -ErrorAction Stop
                    $result.backups+=@{name=$n;path=$oldBackup}
                }
                $phase='promote:'+$n
                Move-Item -LiteralPath $staged -Destination $dst -ErrorAction Stop
                if (-not $NoPin) {
                    & attrib.exe +P -U $dst | Out-Null
                    if ($LASTEXITCODE -ne 0) { throw 'pin-failed' }
                }
                $verified=Inspect-Installed $n ([string]$manifest.files.$n)
                if (-not $verified.matches) { throw 'installed-verification-failed' }
                $result.updated+=$n
            } catch {
                if ($null -ne $oldBackup -and [IO.File]::Exists($oldBackup)) {
                    try {
                        if ([IO.File]::Exists($dst)) {
                            Move-Item -LiteralPath $dst -Destination ($dst + '.failed-' + [Guid]::NewGuid().ToString('N')) -ErrorAction Stop
                        }
                        Move-Item -LiteralPath $oldBackup -Destination $dst -ErrorAction Stop
                    } catch { }
                }
                throw
            } finally {
                if ([IO.File]::Exists($staged)) { Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue }
            }
        }
    }
    $result.after=@(foreach ($n in $names) { Inspect-Installed $n ([string]$manifest.files.$n) })
    $result.success=@($result.after | Where-Object { -not $_.matches }).Count -eq 0
} catch {
    $result.error=$phase + ':' + $_.Exception.GetType().Name
    $result.hresult=$_.Exception.HResult
    if ($null -ne $manifest) {
        $result.after=@(foreach ($n in $names) { Inspect-Installed $n ([string]$manifest.files.$n) })
    }
} finally {
    $parent=Split-Path -Parent $ReportPath
    [void](New-Item -ItemType Directory -Path $parent -Force -ErrorAction Stop)
    if ([IO.File]::Exists($ReportPath)) { throw 'report-exists' }
    [IO.File]::WriteAllText($ReportPath, (($result | ConvertTo-Json -Depth 8) + "`n"), (New-Object System.Text.UTF8Encoding($false)))
}
