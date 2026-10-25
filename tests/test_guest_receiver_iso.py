"""Offline verification of the bounded, Windows-native guest receiver installer ISO.

The ISO/ZIP are ignored host artifacts; tests that need them skip on fresh
checkouts. No test connects to VMware, modifies its media, or enters the guest.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "receiver-milestones-20261022-01"
ISO = ARTIFACTS / "RR2-Guest-Startup-v2.iso"
RECEIPT = ARTIFACTS / "RR2-Guest-Startup-v2.iso.receipt.json"
BUILDER = ROOT / "scripts" / "Prepare-GuestReceiverISO.ps1"
ZIP = ARTIFACTS / "host-only-download" / "RR2-Guest-Startup-v2.zip"
PINNED_ZIP_SHA256 = "ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f"
SECTOR = 2048


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def root_files(image: bytes) -> dict[str, bytes]:
    assert len(image) >= 19 * SECTOR and len(image) % SECTOR == 0
    primary = image[16 * SECTOR:17 * SECTOR]
    joliet = image[17 * SECTOR:18 * SECTOR]
    assert primary[:7] == b"\x01CD001\x01"
    assert joliet[:7] == b"\x02CD001\x01"
    assert joliet[88:91] == b"%/E", "Joliet filenames were not preserved"
    root = joliet[156:190]
    start = int.from_bytes(root[2:6], "little") * SECTOR
    length = int.from_bytes(root[10:14], "little")
    assert 0 < length <= 2 * SECTOR and start + length <= len(image)
    directory = image[start:start + length]
    files = {}
    offset = 0
    while offset < len(directory):
        record_length = directory[offset]
        if record_length == 0:
            offset = (offset // SECTOR + 1) * SECTOR
            continue
        record = directory[offset:offset + record_length]
        name = record[33:33 + record[32]]
        if name not in (b"\x00", b"\x01"):
            label = name.decode("utf-16-be").removesuffix(";1")
            extent = int.from_bytes(record[2:6], "little") * SECTOR
            byte_length = int.from_bytes(record[10:14], "little")
            assert extent >= 19 * SECTOR and extent + byte_length <= len(image)
            assert label not in files
            files[label] = image[extent:extent + byte_length]
        offset += record_length
    return files


class GuestReceiverIsoTests(unittest.TestCase):
    def test_builder_contains_no_guest_input_or_vm_configuration_operation(self):
        text = BUILDER.read_text(encoding="utf-8")
        self.assertIn("IMAPI2FS.MsftFileSystemImage", text)
        self.assertIn(PINNED_ZIP_SHA256.upper(), text)
        self.assertIn("CreateNew", text)
        self.assertIn("guestInstalled = $false", text)
        self.assertIn("vmMediaModified = $false", text)
        for forbidden in ("vmrun.exe", "SendInput(", "Mount-DiskImage", "Stop-VM"):
            self.assertNotIn(forbidden, text)

    @unittest.skipUnless(ISO.is_file() and ZIP.is_file(), "generated ISO and pinned local ZIP required")
    def test_joliet_root_contains_only_signed_zip_and_one_click_entrypoint(self):
        embedded = root_files(ISO.read_bytes())
        self.assertEqual(set(embedded), {"RR2-Guest-Startup-v2.zip", "START-HERE.cmd"})
        self.assertEqual(sha(embedded["RR2-Guest-Startup-v2.zip"]), PINNED_ZIP_SHA256)
        self.assertEqual(embedded["RR2-Guest-Startup-v2.zip"], ZIP.read_bytes())
        cmd = embedded["START-HERE.cmd"].decode("ascii")
        self.assertIn("Expand-Archive", cmd)
        self.assertIn("INSTALL-ONCE.cmd", cmd)
        self.assertIn(PINNED_ZIP_SHA256.upper(), cmd)
        self.assertIn("if errorlevel 1", cmd)
        self.assertIn("No installer was run", cmd)

    @unittest.skipUnless(ISO.is_file() and RECEIPT.is_file(), "generated ISO receipt required")
    def test_iso_header_bytes_and_receipt_are_consistent(self):
        data = ISO.read_bytes()
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8-sig"))
        self.assertEqual(sha(data), receipt["isoSha256"].lower())
        self.assertEqual(len(data), receipt["isoBytes"])
        self.assertEqual(receipt["zipSha256"].lower(), PINNED_ZIP_SHA256)
        self.assertEqual(receipt["volumeName"], "RR2_STARTUP")
        self.assertEqual(receipt["vmMediaModified"], False)
        self.assertEqual(receipt["guestInputSent"], False)
        self.assertEqual(receipt["guestInstalled"], False)

    @unittest.skipUnless(ISO.is_file(), "generated ISO required")
    def test_repeat_invocation_refuses_overwrite(self):
        old_hash = sha(ISO.read_bytes())
        # Use the repository's supported PowerShell 7 runtime when available.
        # PS5.1 has a separate execution policy and may reject local scripts.
        powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
        if powershell is None:
            self.skipTest("PowerShell required for builder invocation")
        env = os.environ.copy()
        if Path(powershell).name.casefold() == "powershell.exe":
            ps51_modules = (Path(env.get("SystemRoot", r"C:\Windows")) / "System32"
                            / "WindowsPowerShell" / "v1.0" / "Modules")
            env["PSModulePath"] = str(ps51_modules) + os.pathsep + env.get("PSModulePath", "")
        result = subprocess.run(
            [
                powershell, "-NoProfile", "-NonInteractive",
                "-File", str(BUILDER),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", (result.stdout + result.stderr).lower())
        self.assertEqual(sha(ISO.read_bytes()), old_hash)


if __name__ == "__main__":
    unittest.main()
