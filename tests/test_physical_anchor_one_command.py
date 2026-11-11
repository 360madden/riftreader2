"""Offline CLI routing tests for one-command physical XYZ -> anchor preview."""
import io
import json
from contextlib import redirect_stdout
from unittest import TestCase
from unittest.mock import patch

from scripts import physical_rift


class PhysicalAnchorOneCommandTests(TestCase):
    @staticmethod
    def invoke(arguments):
        with redirect_stdout(io.StringIO()) as output:
            code = physical_rift.main(arguments)
        return code, json.loads(output.getvalue())

    def test_missing_catalog_or_nonposition_kind_blocks_before_process_lookup(self):
        invalid = [
            ["--expected-host", "AMD-DESKTOP", "--read-native", "position",
             "--anchor-id", "gate"],
            ["--expected-host", "AMD-DESKTOP", "--read-native", "position",
             "--anchor-catalog", "catalog.json"],
            ["--expected-host", "AMD-DESKTOP", "--read-native", "orientation",
             "--anchor-catalog", "catalog.json", "--anchor-id", "gate"],
            ["--expected-host", "AMD-DESKTOP", "--anchor-catalog", "catalog.json",
             "--anchor-id", "gate"],
        ]
        with patch.object(physical_rift, "select_physical") as select:
            for args in invalid:
                with self.subTest(args=args):
                    code, result = self.invoke(args)
                    self.assertEqual(code, 2)
                    self.assertEqual(result["reason"],
                                     "anchor-preview-requires-position-catalog-and-id")
            select.assert_not_called()

    def test_success_reuses_fresh_read_receipt_for_offline_anchor_preview(self):
        selection = {"status": "ready", "ownerHost": "AMD-DESKTOP"}
        native = dict(selection, status="complete", nativeOutput="C:/capture.json")
        preview = {"status": "offline-candidate-preview", "movementEligible": False,
                   "arrivalQualified": False, "worldInstanceMatched": False}
        with patch.object(physical_rift, "select_physical", return_value=selection) as select, \
             patch.object(physical_rift, "read_native", return_value=native) as reader, \
             patch("scripts.physical_route_preview.preview", return_value=preview) as route:
            code, result = self.invoke([
                "--expected-host", "AMD-DESKTOP", "--physical-pid", "44888",
                "--read-native", "position", "--samples", "3",
                "--anchor-catalog", "catalog.json", "--anchor-id", "gate",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(result["offlineAnchorPreview"], preview)
        select.assert_called_once_with("AMD-DESKTOP", 44888)
        self.assertEqual(reader.call_args.args[:2], (selection, "position"))
        self.assertEqual(route.call_args.args[2], "gate")
        self.assertEqual(route.call_args.args[0], physical_rift.Path("C:/capture.json"))
        self.assertEqual(str(route.call_args.args[1]), "catalog.json")

    def test_invalid_anchor_stays_blocked_without_movement_fallback(self):
        native = {"status": "complete", "nativeOutput": "C:/capture.json"}
        with patch.object(physical_rift, "select_physical", return_value={"status": "ready"}), \
             patch.object(physical_rift, "read_native", return_value=native), \
             patch("scripts.physical_route_preview.preview", side_effect=ValueError("wrong build")):
            code, result = self.invoke([
                "--expected-host", "AMD-DESKTOP", "--read-native", "position",
                "--anchor-catalog", "catalog.json", "--anchor-id", "gate",
            ])
        self.assertEqual(code, 2)
        self.assertEqual(result["reason"], "offline-anchor-preview-failed")
        self.assertIn("wrong build", result["detail"])


if __name__ == "__main__":
    import unittest
    unittest.main()
