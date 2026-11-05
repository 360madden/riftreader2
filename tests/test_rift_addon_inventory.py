"""Offline tests for the non-hydrating three-machine AddOns inventory."""
from __future__ import annotations

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rift_addon_inventory", ROOT / "scripts" / "rift_addon_inventory.py")
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def report(machine, names):
    return {"schemaVersion": 1, "method": "metadata-only",
            "success": True, "complete": True, "machine": machine, "warnings": [],
            "timestampUtc": "2026-11-05T17:00:00Z", "addonRoot": "C:\\Test\\AddOns",
            "rootReparse": False,
            "entries": [{"name": n, "kind": "directory", "offline": False,
                         "reparse": False, "toc": [], "modifiedUtc": "2026-11-05T17:00:00Z"}
                        for n in names]}


class InventoryTests(unittest.TestCase):
    def test_validate_report_and_identity(self):
        result = inventory.validate_report(report("RIFT-LAB-1", ["RRECollector"]), "lab1")
        self.assertEqual(result["target"], "lab1")
        self.assertEqual(result["machine"], "RIFT-LAB-1")

    def test_duplicate_case_insensitive_name_rejected(self):
        with self.assertRaisesRegex(inventory.InventoryError, "duplicate-entry-name"):
            inventory.validate_report(report("PC", ["RiftReader2", "riftreader2"]), "pc")

    def test_guest_machine_binding(self):
        with self.assertRaisesRegex(inventory.InventoryError, "unexpected-guest-machine"):
            inventory.validate_report(report("RIFT-LAB-2", ["A"]), "lab1")

    def test_invalid_toc_metadata_and_duplicate_names(self):
        data = report("PC", ["AddOn"])
        sample = {"name": "MyAddon.toc", "bytes": 20,
                  "modifiedUtc": "2026-11-05T17:00:00Z", "offline": False,
                  "reparse": False}
        data["entries"][0]["toc"] = [sample, dict(sample, name="myaddon.TOC")]
        with self.assertRaisesRegex(inventory.InventoryError, "duplicate-toc-name"):
            inventory.validate_report(data, "pc")
        data["entries"][0]["toc"] = [dict(sample, name="../danger.toc")]
        with self.assertRaisesRegex(inventory.InventoryError, "invalid-toc-name"):
            inventory.validate_report(data, "pc")
        data["entries"][0]["toc"] = [dict(sample, bytes=-1)]
        with self.assertRaisesRegex(inventory.InventoryError, "invalid-toc-metadata"):
            inventory.validate_report(data, "pc")

    def test_report_provenance_required(self):
        data = report("PC", ["A"])
        data.pop("timestampUtc")
        with self.assertRaisesRegex(inventory.InventoryError, "invalid-report-provenance"):
            inventory.validate_report(data, "pc")

    def test_partial_inventory_exit_code_distinct_from_failure(self):
        with TemporaryDirectory() as temporary:
            partial = report("PC", ["OfflineAddon"])
            partial["complete"] = False
            partial["warnings"] = ["toc-uninspected:OfflineAddon"]
            with patch.object(inventory, "ROOT", Path(temporary)):
                with patch.object(inventory, "run_pc", return_value=partial):
                    with redirect_stdout(StringIO()) as output:
                        exit_code = inventory.main(["--target", "pc"])
            self.assertEqual(exit_code, 3)
            self.assertIn('"complete": false', output.getvalue())
            self.assertIn('"timestampUtc"', output.getvalue())

    def test_cloud_tag_mask_rejects_junctions(self):
        mask, cloud = 0xFFFF0FFF, 0x9000001A
        for tag in (0x9000001A, 0x9000601A, 0x9000E01A, 0x9000F01A):
            self.assertEqual(tag & mask, cloud)
        for tag in (0xA000000C, 0xA0000003, 0x80000017):
            self.assertNotEqual(tag & mask, cloud)

    def test_guest_inspector_has_no_content_reads_or_game_control(self):
        content = (ROOT / "scripts" / "rift_addon_inventory_guest.ps1").read_text(encoding="utf-8")
        for forbidden in ("Get-Content", "ReadAllBytes", "ReadAllText", "Start-Process",
                          "Stop-Process", "shutdown.exe", "Restart-Computer"):
            self.assertNotIn(forbidden, content)
        self.assertIn("Test-CloudReparse", content)

    def test_reparse_and_offline_markers_do_not_require_hashes(self):
        data = report("PC", ["OfflineAddon"])
        data["entries"][0]["offline"] = True
        data["entries"][0]["reparse"] = True
        data["complete"] = False
        data["warnings"] = ["toc-uninspected:OfflineAddon"]
        self.assertFalse(inventory.validate_report(data, "pc")["complete"])

    @staticmethod
    def _toc(name="Example.toc", bytes=10, modified="2026-11-05T17:00:00Z",
             offline=False, reparse=False):
        return {"name": name, "bytes": bytes, "modifiedUtc": modified,
                "offline": offline, "reparse": reparse}

    def test_toc_comparison_identical_casefolded_names(self):
        pc = report("PC", ["Example"])
        lab = report("RIFT-LAB-1", ["example"])
        pc["entries"][0]["toc"] = [self._toc("Example.TOC")]
        lab["entries"][0]["toc"] = [self._toc("example.toc")]
        results = {"pc": pc, "lab1": lab}
        for value in results.values():
            value["success"] = value["complete"] = True
        comparison = inventory.compare_toc_metadata(results)
        self.assertTrue(comparison["complete"])
        self.assertTrue(comparison["conclusive"])
        self.assertEqual(comparison["differences"], [])

    def test_subsecond_timestamp_only_is_low_significance(self):
        pc = report("PC", ["Example"])
        lab = report("RIFT-LAB-1", ["Example"])
        pc["entries"][0]["toc"] = [self._toc(modified="2026-11-05T17:00:00.9271270Z")]
        lab["entries"][0]["toc"] = [self._toc(modified="2026-11-05T17:00:00.0000000Z")]
        comparison = inventory.compare_toc_metadata({"pc": pc, "lab1": lab})
        fields = comparison["differences"][0]["tocDifferences"][0]["differingFields"]
        self.assertEqual(fields, ["modifiedUtcSubsecond"])

    def test_toc_drift_classifies_size_time_and_cloud_flags(self):
        pc = report("PC", ["Example"])
        lab = report("RIFT-LAB-1", ["Example"])
        pc["entries"][0]["toc"] = [self._toc()]
        lab["entries"][0]["toc"] = [self._toc(
            bytes=11, modified="2026-11-05T17:01:00Z", offline=True, reparse=True)]
        comparison = inventory.compare_toc_metadata({"pc": pc, "lab1": lab})
        difference = comparison["differences"][0]["tocDifferences"][0]
        self.assertEqual(difference["differingFields"],
                         ["bytes", "modifiedUtc", "offline", "reparse"])
        self.assertEqual(difference["missingOn"], [])

    def test_toc_comparison_detects_missing_toc_not_addon(self):
        pc = report("PC", ["Example"])
        lab = report("RIFT-LAB-1", ["Example"])
        pc["entries"][0]["toc"] = [self._toc()]
        comparison = inventory.compare_toc_metadata({"pc": pc, "lab1": lab})
        difference = comparison["differences"][0]["tocDifferences"][0]
        self.assertEqual(difference["differingFields"], ["presence"])
        self.assertEqual(difference["missingOn"], ["lab1"])

    def test_toc_comparison_excludes_partial_or_failed_targets(self):
        pc = report("PC", ["Example"])
        pc["entries"][0]["toc"] = [self._toc()]
        partial = report("RIFT-LAB-1", ["Example"])
        partial["complete"] = False
        partial["warnings"] = ["toc-uninspected:Example"]
        comparison = inventory.compare_toc_metadata({
            "pc": pc, "lab1": partial, "lab2": {"success": False, "error": "offline"}})
        self.assertFalse(comparison["complete"])
        self.assertFalse(comparison["conclusive"])
        self.assertEqual(comparison["comparedTargets"], ["pc"])
        self.assertEqual(comparison["excludedTargets"], ["lab1", "lab2"])
        self.assertEqual(comparison["differences"], [])

    def test_toc_comparison_reports_kind_mismatch(self):
        pc = report("PC", ["Example"])
        lab = report("RIFT-LAB-1", ["Example"])
        lab["entries"][0]["kind"] = "file"
        comparison = inventory.compare_toc_metadata({"pc": pc, "lab1": lab})
        self.assertEqual(comparison["differences"][0]["kindDifferences"],
                         {"pc": "directory", "lab1": "file"})

    def test_name_diff_is_presence_only_not_file_parity(self):
        values = {
            "pc": {"success": True, "entries": report("PC", ["RiftReader2", "RRECollector"])["entries"]},
            "lab1": {"success": True, "entries": report("L1", ["RiftReader2"])["entries"]},
            "lab2": {"success": True, "entries": report("L2", ["RRECollector"])["entries"]},
        }
        self.assertEqual(inventory.compare_names(values), [
            {"name": "RiftReader2", "presentOn": ["pc", "lab1"], "missingOn": ["lab2"]},
            {"name": "RRECollector", "presentOn": ["pc", "lab2"], "missingOn": ["lab1"]}
        ])

    def test_failed_target_does_not_fabricate_missing_names(self):
        values = {
            "pc": {"success": True, "entries": report("PC", ["A"])["entries"]},
            "lab1": {"success": False, "error": "offline"},
        }
        self.assertEqual(inventory.compare_names(values), [])


if __name__ == "__main__":
    unittest.main()

