"""Remove one known stale Lab 1 reader configuration after strict guards.

This helper intentionally has no lab or guest-path option.  It does not read
the configuration, send game input, stop a process, or recursively remove
anything.  The only mutation it can request is disposition of the fixed leaf
below after validating an exclusive native handle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.launch_live_reader import (
    LABS,
    VMRUN,
    collect_identity,
    fail,
    legacy_guest_target,
    no_prompt,
    quote,
    run_guest_script,
    validate_config,
    verify_identity,
    write_new,
)
from scripts.vmware_guest_session import GuestSession


LAB = "lab1"
GUEST_USER = r"RIFT-LAB-1\mrkoo"
GUEST_PARENT = (
    r"C:\Users\mrkoo\AppData\Local\RiftReader2\Hybrid"
    r"\lab1-fed73039b1614151bc92bda5b8501641"
)
GUEST_FILE = GUEST_PARENT + r"\riftreader2-live.json"
MAX_LENGTH = 65_536


def guest_body() -> str:
    """Return the fixed, metadata-only cleanup program for the guest."""
    return rf"""
$path={quote(GUEST_FILE)}
$expectedParent={quote(GUEST_PARENT)}
if($env:COMPUTERNAME -ne {quote(LABS[LAB]['machine'])}){{throw 'guest-machine-mismatch'}}
$guestUser=[Security.Principal.WindowsIdentity]::GetCurrent().Name
if($guestUser -ne {quote(GUEST_USER)}){{throw 'guest-user-mismatch'}}

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
    if receipt["status"] not in {"deleted", "already-absent"}:
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
    if (receipt["otherReaderCountBefore"] != 0
            or receipt["otherReaderCountAfter"] != 0
            or receipt["inputSent"] is not False):
        fail("cleanup-receipt-guard-failed")
    return dict(receipt)


def execute(output: Path) -> dict:
    output = output.resolve(strict=False)
    output.mkdir(parents=True, exist_ok=False)
    lab = LABS[LAB]
    cfg = validate_config(lab["vmx"], lab["port"], VMRUN, output, require_files=True)
    vm_before = collect_identity(cfg)
    write_new(output / "vm-before.json", vm_before)
    check = lambda: verify_identity(cfg, vm_before)
    run_id = f"cleanup-{uuid.uuid4().hex}"

    with GuestSession(
        cfg.vmrun,
        cfg.vmx,
        check,
        cache_guest_credentials=False,
        _guest_prompt=no_prompt,
        legacy_guest_credential_target=legacy_guest_target(LAB),
    ) as session:
        if session.credential_source != "cache":
            fail("noncached-credentials-blocked")
        receipt = validate_receipt(
            run_guest_script(session, output, guest_body(), run_id, "cleanup")
        )

    vm_after = verify_identity(cfg, vm_before)
    write_new(output / "vm-after.json", vm_after)
    summary = {
        **receipt,
        "lab": LAB,
        "vmIdentityStable": vm_after == vm_before,
        "atUtc": datetime.now(timezone.utc).isoformat(),
    }
    write_new(output / "summary.json", summary)
    return summary


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        summary = execute(args.output)
    except Exception as error:
        print(json.dumps({"status": "blocked", "reason": str(error).split(":", 1)[0]}))
        return 2
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
