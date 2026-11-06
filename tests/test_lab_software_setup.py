"""Offline provenance tests for RIFT lab software inventory and installer."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lab_software_inventory import MAX_REPORT_BYTES, TOOLS, validate_report as validate_inventory
from lab_software_install import PACKAGES as INSTALL_PACKAGES, validate_report as validate_install


class InventoryReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {
            "schemaVersion": 1,
            "method": "read-only-software-inventory",
            "machine": "RIFT-LAB-1",
            "memoryGiB": 8.0,
            "diskCFreeGiB": 39.5,
            "vmwareTools": {"present": True, "status": "Running", "version": None},
            "tools": {name: {"present": False} for name in TOOLS},
        }

    def test_accepts_valid_report(self):
        self.assertIs(validate_inventory(self.report, "lab1"), self.report)

    def test_rejects_wrong_guest(self):
        self.report["machine"] = "RIFT-LAB-2"
        with self.assertRaises(ValueError):
            validate_inventory(self.report, "lab1")

    def test_rejects_missing_required_probe(self):
        del self.report["tools"]["winget"]
        with self.assertRaises(ValueError):
            validate_inventory(self.report, "lab1")

    def test_rejects_nonboolean_presence(self):
        self.report["tools"]["git"]["present"] = 1
        with self.assertRaises(ValueError):
            validate_inventory(self.report, "lab1")

    def test_rejects_negative_capacity(self):
        self.report["diskCFreeGiB"] = -1
        with self.assertRaises(ValueError):
            validate_inventory(self.report, "lab1")

    def discovery(self):
        self.report["discovery"] = {
            "method": "file-and-uninstall-metadata-only",
            "portableRoots": [r"C:\Tools\Sysinternals"],
            "sysinternalsFiles": [{"name": "procexp64.exe", "path": r"C:\Tools\Sysinternals\procexp64.exe",
                                   "version": "17.0", "sha256": "A" * 64}],
            "uninstallScopes": [{"path": str(n), "examined": 2, "truncated": False} for n in range(3)],
            "applications": [{"name": "Unexpected discovery tool", "version": "1.0", "publisher": "Vendor", "registryRoot": "0"}],
            "applicationLimitReached": False,
        }
        return self.report["discovery"]

    def test_accepts_optional_discovery(self):
        self.discovery()
        self.assertIs(validate_inventory(self.report, "lab1"), self.report)

    def test_rejects_discovery_bad_hash_or_path(self):
        for key, value in (("sha256", "bad"), ("path", r"C:\Other\procexp64.exe")):
            with self.subTest(key=key):
                self.discovery()["sysinternalsFiles"][0][key] = value
                with self.assertRaises(ValueError):
                    validate_inventory(self.report, "lab1")

    def test_rejects_discovery_bounds_and_scope_flags(self):
        self.discovery()["applications"] *= 129
        with self.assertRaises(ValueError):
            validate_inventory(self.report, "lab1")
        self.discovery()["uninstallScopes"][0]["truncated"] = 1
        with self.assertRaises(ValueError):
            validate_inventory(self.report, "lab1")

    def test_accepts_explicit_metadata_failure(self):
        entry = self.discovery()["sysinternalsFiles"][0]
        del entry["sha256"]
        del entry["version"]
        entry["error"] = "metadata-read-failed"
        self.assertIs(validate_inventory(self.report, "lab1"), self.report)

    def test_maximum_application_text_fits_report_cap(self):
        discovery = self.discovery()
        discovery["applications"] = [{"name": "😀" * 200, "version": "😀" * 100,
                                      "publisher": "😀" * 100, "registryRoot": "x" * 100}
                                     for _ in range(128)]
        self.assertLess(len(json.dumps(self.report, ensure_ascii=False, indent=4).encode("utf-8")), MAX_REPORT_BYTES)


class InstallerReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {
            "schemaVersion": 1,
            "method": "winget-guest-install",
            "machine": "RIFT-LAB-2",
            "packageId": "Git.Git",
            "status": "passed",
            "rebootPerformed": False,
            "exitCode": 0,
        }

    def test_accepts_valid_install(self):
        self.assertIs(validate_install(self.report, "lab2", "Git.Git"), self.report)

    def test_winappcli_allowlisted(self):
        self.assertIn("Microsoft.WinAppCli", INSTALL_PACKAGES)

    def test_rejects_wrong_package(self):
        with self.assertRaises(ValueError):
            validate_install(self.report, "lab2", "OpenJS.NodeJS.LTS")

    def test_rejects_wrong_machine(self):
        with self.assertRaises(ValueError):
            validate_install(self.report, "lab1", "Git.Git")

    def test_rejects_reboot(self):
        self.report["rebootPerformed"] = True
        with self.assertRaises(ValueError):
            validate_install(self.report, "lab2", "Git.Git")

    def test_rejects_unknown_status(self):
        self.report["status"] = "maybe"
        with self.assertRaises(ValueError):
            validate_install(self.report, "lab2", "Git.Git")


if __name__ == "__main__":
    unittest.main()
