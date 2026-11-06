"""Offline provenance tests for RIFT lab software inventory and installer."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lab_software_inventory import TOOLS, validate_report as validate_inventory
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
