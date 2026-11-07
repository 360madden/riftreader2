"""Metadata-only cleanup of a generated RR2 guest staging configuration."""
import re

MAX_LENGTH = 65_536

def quote(value):
    return "'" + value.replace("'", "''") + "'"

def fail(reason):
    raise RuntimeError(reason)


def guest_body(lab: str, run_id: str) -> str:
    """Return the fixed, metadata-only cleanup program for the guest."""
    if lab not in ("lab1", "lab2") or not re.fullmatch(rf"{lab}-[0-9a-f]{{32}}", run_id):
        raise RuntimeError("cleanup-run-id-invalid")
    machine = "RIFT-LAB-" + lab[-1]
    guest_user = machine + r"\mrkoo"
    parent = r"C:\Users\mrkoo\AppData\Local\RiftReader2\Hybrid" + "\\" + run_id
    guest_file = parent + r"\riftreader2-live.json"
    return rf"""
$path={quote(guest_file)}
$expectedParent={quote(parent)}
if($env:COMPUTERNAME -ne {quote(machine)}){{throw 'guest-machine-mismatch'}}
$guestUser=[Security.Principal.WindowsIdentity]::GetCurrent().Name
if($guestUser -ne {quote(guest_user)}){{throw 'guest-user-mismatch'}}

function Get-OtherReaderCount {{
    return @(
        Get-CimInstance Win32_Process -Filter "Name='RiftReader2.Live.exe'" |
        Where-Object {{ $_.CommandLine -notmatch '(?i)(^|\s)control-agent(\s|$)' }}
    ).Count
}}

$beforeCount=Get-OtherReaderCount
if($beforeCount -ne 0){{throw 'live-reader-or-unknown-command-already-running'}}
$existed=Test-Path -LiteralPath $path -PathType Leaf
$deleted=$false
if($existed){{
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class RR2FixedLeafDelete
{{
    private const uint DELETE = 0x00010000;
    private const uint FILE_READ_ATTRIBUTES = 0x00000080;
    private const uint OPEN_EXISTING = 3;
    private const uint FILE_ATTRIBUTE_NORMAL = 0x00000080;
    private const uint FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400;
    private const uint FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000;
    private static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential)]
    private struct BY_HANDLE_FILE_INFORMATION
    {{
        public uint FileAttributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }}

    [StructLayout(LayoutKind.Sequential)]
    private struct FILE_DISPOSITION_INFO
    {{
        [MarshalAs(UnmanagedType.Bool)] public bool DeleteFile;
    }}

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateFile(
        string name, uint access, uint share, IntPtr security,
        uint creation, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(
        IntPtr handle, out BY_HANDLE_FILE_INFORMATION information);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetFileInformationByHandle(
        IntPtr handle, int informationClass,
        ref FILE_DISPOSITION_INFO information, uint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    public static void DeleteAfterHandleChecks(string path, long expectedLength)
    {{
        IntPtr handle = CreateFile(
            path, DELETE | FILE_READ_ATTRIBUTES, 0, IntPtr.Zero,
            OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
            IntPtr.Zero);
        if (handle == INVALID_HANDLE_VALUE)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "fixed-leaf-open-failed");
        try
        {{
            BY_HANDLE_FILE_INFORMATION actual;
            if (!GetFileInformationByHandle(handle, out actual))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "fixed-leaf-info-failed");
            if ((actual.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0)
                throw new InvalidOperationException("fixed-leaf-handle-reparse-point");
            long actualLength = ((long)actual.FileSizeHigh << 32) | actual.FileSizeLow;
            if (actualLength != expectedLength || actualLength > {MAX_LENGTH})
                throw new InvalidOperationException("fixed-leaf-handle-length-mismatch");

            // FileDispositionInfo is 4.  This is the first operation that
            // requests deletion; every failed check above merely closes the
            // exclusive handle and leaves the file in place.
            FILE_DISPOSITION_INFO disposition = new FILE_DISPOSITION_INFO {{ DeleteFile = true }};
            if (!SetFileInformationByHandle(
                    handle, 4, ref disposition,
                    (uint)Marshal.SizeOf(typeof(FILE_DISPOSITION_INFO))))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "fixed-leaf-disposition-failed");
        }}
        finally
        {{
            CloseHandle(handle);
        }}
    }}
}}
'@
    $parent=Get-Item -LiteralPath $expectedParent -Force -ErrorAction Stop
    $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if($parent.PSIsContainer -ne $true){{throw 'staging-parent-not-directory'}}
    if($item.PSIsContainer){{throw 'staging-leaf-not-file'}}
    if(-not [string]::Equals($parent.FullName,$expectedParent,[StringComparison]::OrdinalIgnoreCase)){{
        throw 'staging-parent-path-mismatch'
    }}
    if(-not [string]::Equals($item.FullName,$path,[StringComparison]::OrdinalIgnoreCase)){{
        throw 'staging-leaf-path-mismatch'
    }}
    if(($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){{
        throw 'staging-parent-reparse-point'
    }}
    if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){{
        throw 'staging-leaf-reparse-point'
    }}
    if($item.Length -gt {MAX_LENGTH}){{throw 'staging-leaf-too-large'}}

    # The native helper opens this exact leaf with share mode zero and only
    # DELETE + FILE_READ_ATTRIBUTES.  It validates the handle before setting
    # FileDispositionInfo and never requests content access.
    [RR2FixedLeafDelete]::DeleteAfterHandleChecks($path,[long]$item.Length)
    $deleted=$true
}}
if(Test-Path -LiteralPath $path){{throw 'staging-leaf-still-present'}}
$afterCount=Get-OtherReaderCount
if($afterCount -ne 0){{throw 'reader-process-appeared-during-cleanup'}}
$payload=@{{
    status=$(if($deleted){{'deleted'}}else{{'already-absent'}})
    fileExisted=[bool]$existed
    deleted=[bool]$deleted
    otherReaderCountBefore=[int]$beforeCount
    otherReaderCountAfter=[int]$afterCount
    inputSent=$false
}}
"""


def validate_receipt(receipt: object) -> dict:
    """Accept only the small, content-free receipt emitted by ``guest_body``."""
    if not isinstance(receipt, dict) or set(receipt) != {
        "status", "fileExisted", "deleted", "otherReaderCountBefore",
        "otherReaderCountAfter", "inputSent",
    }:
        fail("cleanup-receipt-fields")
    if type(receipt["status"]) is not str or receipt["status"] not in {"deleted", "already-absent"}:
        fail("cleanup-receipt-status")
    existed = receipt["fileExisted"]
    deleted = receipt["deleted"]
    if type(existed) is not bool or type(deleted) is not bool:
        fail("cleanup-receipt-types")
    if (receipt["status"], existed, deleted) not in {
        ("deleted", True, True),
        ("already-absent", False, False),
    }:
        fail("cleanup-receipt-inconsistent")
    if (type(receipt["otherReaderCountBefore"]) is not int
            or type(receipt["otherReaderCountAfter"]) is not int
            or receipt["otherReaderCountBefore"] != 0
            or receipt["otherReaderCountAfter"] != 0
            or receipt["inputSent"] is not False):
        fail("cleanup-receipt-guard-failed")
    return dict(receipt)


