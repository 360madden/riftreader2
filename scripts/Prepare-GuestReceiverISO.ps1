# Verified RIFT-Lab-1 receiver installer disc, built with inbox Windows IMAPI2.
# This host-only command never attaches media or sends input to the VM.
[CmdletBinding()]
param([string]$OutputDirectory = '', [string]$OutputName = 'RR2-Guest-Startup-v2.iso')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$artifacts = Join-Path $repo 'artifacts\receiver-milestones-20261022-01'
$zip = Join-Path $artifacts 'host-only-download\RR2-Guest-Startup-v2.zip'
$zipSha = 'AB5242D0317257DC2B2328F0BC1DA98CC24088A2140EA4D968A29C86C23F708F'
if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) { throw 'Pinned v2 ZIP unavailable' }
$bytes = (Get-Item -LiteralPath $zip).Length
if ($bytes -lt 1024 -or $bytes -gt 65536) { throw 'Pinned ZIP size outside allowed bounds' }
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne $zipSha) { throw 'Pinned ZIP hash mismatch' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    $expected = @(
        'RR2-Guest-Startup-v2/CHECK-STATUS.cmd',
        'RR2-Guest-Startup-v2/guest_receiver_startup.ps1',
        'RR2-Guest-Startup-v2/INSTALL-ONCE.cmd',
        'RR2-Guest-Startup-v2/README.txt',
        'RR2-Guest-Startup-v2/REMOVE-STARTUP.cmd',
        'RR2-Guest-Startup-v2/VERIFY-LAUNCHER.cmd'
    ) | Sort-Object
    $actual = @($archive.Entries | ForEach-Object { $_.FullName } | Sort-Object)
    if (@(Compare-Object -ReferenceObject $expected -DifferenceObject $actual).Count -ne 0) {
        throw 'Pinned ZIP entry list differs from tested v2 installer'
    }
} finally { $archive.Dispose() }

if (-not $OutputDirectory) { $OutputDirectory = $artifacts }
$root = [IO.Path]::GetFullPath($artifacts).TrimEnd('\')
$destination = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $OutputDirectory).Path).TrimEnd('\')
if ($destination -ne $root -and
    -not $destination.StartsWith(($root + '\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Output must stay under the receiver artifact directory'
}
if ($OutputName -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{4,90}\.iso$') { throw 'Invalid output ISO name' }
$iso = Join-Path $destination $OutputName
$receiptFile = $iso + '.receipt.json'
if ((Test-Path -LiteralPath $iso) -or (Test-Path -LiteralPath $receiptFile)) {
    throw 'ISO or receipt already exists; will not overwrite'
}
$wrapper = @'
@echo off
setlocal EnableExtensions DisableDelayedExpansion
title RIFT-Lab-1 receiver startup v2
echo Verified offline RIFT-Lab-1 receiver startup installer
echo Run as the signed-in Windows guest user; no administrator rights required.
set "RR2_ZIP=%~dp0RR2-Guest-Startup-v2.zip"
set "RR2_DEST=%LOCALAPPDATA%\RiftReader2\ReceiverStartup\ISO-v2"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; if ((Get-FileHash -LiteralPath $env:RR2_ZIP -Algorithm SHA256).Hash -ne 'AB5242D0317257DC2B2328F0BC1DA98CC24088A2140EA4D968A29C86C23F708F') { throw 'ZIP HASH MISMATCH' }; if (Test-Path -LiteralPath $env:RR2_DEST) { throw 'Existing extraction directory; inspect before retrying' }; Expand-Archive -LiteralPath $env:RR2_ZIP -DestinationPath $env:RR2_DEST -ErrorAction Stop"
if errorlevel 1 (
  echo Extraction failed or the destination already exists. No installer was run.
  pause
  exit /b 11
)
call "%RR2_DEST%\RR2-Guest-Startup-v2\INSTALL-ONCE.cmd"
set "RR2_RESULT=%ERRORLEVEL%"
echo Installer exit code: %RR2_RESULT%
if not "%RR2_RESULT%"=="0" echo Review installer output; do not blindly retry.
pause
exit /b %RR2_RESULT%
'@
$stage = Join-Path $destination ('iso-stage-' + [guid]::NewGuid().ToString('N'))
$tempIso = Join-Path $destination ('.' + $OutputName + '.' + [guid]::NewGuid().ToString('N') + '.partial')
$stageOwned = $false
$tempOwned = $false
try {
    $null = New-Item -ItemType Directory -Path $stage -ErrorAction Stop
    $stageOwned = $true
    Copy-Item -LiteralPath $zip -Destination (Join-Path $stage 'RR2-Guest-Startup-v2.zip') -ErrorAction Stop
    [IO.File]::WriteAllText(
        (Join-Path $stage 'START-HERE.cmd'),
        ($wrapper -replace '(?<!\r)\n', ([string][char]13 + [string][char]10)),
        [Text.Encoding]::ASCII
    )
    $fsi = New-Object -ComObject 'IMAPI2FS.MsftFileSystemImage'
    $fsi.FileSystemsToCreate = 3 # ISO9660 + Joliet
    $fsi.VolumeName = 'RR2_STARTUP'
    $fsi.Root.AddTree($stage, $false)
    $image = $fsi.CreateResultImage()
    $total = [int64]$image.TotalBlocks * 2048
    if ($total -lt 40960 -or $total -gt 2097152) { throw 'Image size outside allowed bounds' }
    # Windows PowerShell's COM binder cannot cast ImageStream directly to IStream.
    # Compile one narrow, managed adapter that performs the COM QueryInterface.
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class ReceiverIsoComCopy
{
    public static void Save(object raw, string path, long expectedBytes)
    {
        IStream source = (IStream)raw;
        byte[] buffer = new byte[65536];
        IntPtr count = Marshal.AllocHGlobal(4);
        try
        {
            using (FileStream sink = new FileStream(
                path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                long remaining = expectedBytes;
                while (remaining > 0)
                {
                    int requested = (int)Math.Min(remaining, buffer.Length);
                    Marshal.WriteInt32(count, 0);
                    source.Read(buffer, requested, count);
                    int received = Marshal.ReadInt32(count);
                    if (received < 1 || received > requested)
                        throw new IOException("Invalid ISO stream byte count");
                    sink.Write(buffer, 0, received);
                    remaining -= received;
                }
                sink.Flush(true);
            }
        }
        finally { Marshal.FreeHGlobal(count); }
    }
}
'@
    $tempOwned = $true
    [ReceiverIsoComCopy]::Save($image.ImageStream, $tempIso, $total)
    if ((Get-Item -LiteralPath $tempIso).Length -ne $total) { throw 'Image block-count mismatch' }
    $file = [IO.File]::OpenRead($tempIso)
    try {
        $file.Position = 32769
        $marker = [byte[]]::new(5)
        if ($file.Read($marker, 0, 5) -ne 5 -or
            [Text.Encoding]::ASCII.GetString($marker) -ne 'CD001') {
            throw 'ISO9660 primary volume descriptor missing'
        }
    } finally { $file.Dispose() }
    $digest = (Get-FileHash -LiteralPath $tempIso -Algorithm SHA256).Hash
    [IO.File]::Move($tempIso, $iso)
    $tempOwned = $false
    $receipt = [ordered]@{
        schemaVersion = 1
        purpose = 'verified-guest-receiver-install-media'
        generatedUtc = [DateTime]::UtcNow.ToString('o')
        isoPath = $iso
        isoBytes = $total
        isoSha256 = $digest
        zipSha256 = $zipSha
        volumeName = 'RR2_STARTUP'
        rootFiles = @('RR2-Guest-Startup-v2.zip','START-HERE.cmd')
        vmMediaModified = $false
        guestInputSent = $false
        guestInstalled = $false
    }
    [IO.File]::WriteAllText($receiptFile,
        (($receipt | ConvertTo-Json -Depth 3) + [Environment]::NewLine),
        [Text.Encoding]::UTF8)
    $receipt | ConvertTo-Json -Compress -Depth 3
} finally {
    if ($stageOwned -and (Test-Path -LiteralPath $stage -PathType Container)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    if ($tempOwned -and (Test-Path -LiteralPath $tempIso -PathType Leaf)) {
        Remove-Item -LiteralPath $tempIso -Force
    }
}
