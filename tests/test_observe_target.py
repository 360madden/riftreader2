"""The common entry point must never cross target or backend boundaries."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import observe_target as tool


class TargetRoutingTests(unittest.TestCase):
    def setUp(self):
        self.hostname = patch.object(tool.socket, "gethostname", return_value="AMD-DESKTOP")
        self.hostname.start()
        self.addCleanup(self.hostname.stop)

    def result(self, target="lab2", workflow="vmware"):
        return {"status": "verified-awaiting-visual-review", "targetId": target,
                "workflow": workflow, "image": "image.bmp", "imageSha256": "A" * 64}

    def test_wrong_machine_blocks_before_either_adapter(self):
        with patch.object(tool.socket, "gethostname", return_value="LEGION"), patch.object(
                tool, "_capture_vmware") as vm, patch.object(tool, "_capture_physical") as physical:
            with self.assertRaisesRegex(ValueError, "host-mismatch"):
                tool.observe("lab2", "AMD-DESKTOP")
            vm.assert_not_called()
            physical.assert_not_called()

    def test_wrong_expected_owner_cannot_redirect_target(self):
        with patch.object(tool, "_capture_vmware") as vm, patch.object(tool, "_capture_physical") as physical:
            with self.assertRaisesRegex(ValueError, "target-host-mismatch"):
                tool.observe("lab2", "LEGION")
            vm.assert_not_called()
            physical.assert_not_called()

    def test_lab2_defaults_to_capture_only_once(self):
        with patch.object(tool, "_capture_vmware", return_value=self.result()) as vm, patch.object(
                tool, "_capture_physical") as physical:
            result = tool.observe("lab2", "amd-desktop", Path("fresh"))
        vm.assert_called_once_with("lab2", Path("fresh"), False)
        physical.assert_not_called()
        self.assertEqual(result["ownerHost"], "AMD-DESKTOP")

    def test_native_read_is_explicit(self):
        with patch.object(tool, "_capture_vmware", return_value=self.result()) as vm:
            tool.observe("lab2", "AMD-DESKTOP", native_vitals=True)
        vm.assert_called_once_with("lab2", None, True)

    def test_physical_does_not_touch_vmware(self):
        with patch.object(tool, "_capture_vmware") as vm, patch.object(tool, "_capture_physical",
                return_value=self.result("physical-amd-desktop", "physical")) as physical:
            tool.observe("physical-amd-desktop", "AMD-DESKTOP", allow_foreground_change=True)
        vm.assert_not_called()
        physical.assert_called_once_with("AMD-DESKTOP", None, True)

    def test_legion_requires_actual_legion(self):
        with patch.object(tool.socket, "gethostname", return_value="LEGION"), patch.object(
                tool, "_capture_physical", return_value=self.result("physical-legion", "physical")) as physical:
            tool.observe("physical-legion", "LEGION")
        physical.assert_called_once_with("LEGION", None, False)

    def test_unqualified_requests_fail_without_fallback(self):
        for target, opts in (("lab1", {"native_vitals": True}), ("physical-amd-desktop", {"native_vitals": True})):
            with self.subTest(target=target), patch.object(tool, "_capture_vmware") as vm, patch.object(
                    tool, "_capture_physical") as physical:
                with self.assertRaisesRegex(ValueError, "not-yet-qualified"):
                    tool.observe(target, "AMD-DESKTOP", **opts)
                vm.assert_not_called()
                physical.assert_not_called()

    def test_invalid_preview_width_does_not_capture(self):
        with patch.object(tool, "_capture_vmware") as vm:
            with self.assertRaisesRegex(ValueError, "invalid-preview-width"):
                tool.observe("lab2", "AMD-DESKTOP", with_preview=True, preview_width=10)
            vm.assert_not_called()

    def test_wrong_target_receipt_is_not_published(self):
        with patch.object(tool, "_capture_vmware", return_value=self.result("lab1")):
            with self.assertRaisesRegex(ValueError, "adapter-target-mismatch"):
                tool.observe("lab2", "AMD-DESKTOP")

    def test_blocked_adapter_is_preserved_without_retry_or_preview(self):
        blocked = {"status": "blocked", "reason": "UI_TURN_BUSY",
                   "targetId": "physical-amd-desktop", "workflow": "physical"}
        with patch.object(tool, "_capture_physical", return_value=blocked) as physical, patch.object(
                tool, "_preview") as preview:
            result = tool.observe("physical-amd-desktop", "AMD-DESKTOP", with_preview=True)
        self.assertEqual(result["reason"], "UI_TURN_BUSY")
        physical.assert_called_once()
        preview.assert_not_called()

    def test_preview_attaches_to_single_verified_capture(self):
        with patch.object(tool, "_capture_vmware", return_value=self.result()) as vm, patch.object(
                tool, "_preview", return_value={"nonAuthoritative": True}) as preview:
            result = tool.observe("lab2", "AMD-DESKTOP", with_preview=True)
        vm.assert_called_once()
        preview.assert_called_once()
        self.assertTrue(result["preview"]["nonAuthoritative"])

    def test_cli_failure_retains_sanitized_workflow_reason(self):
        failure = ValueError("active request prevents capture")
        failure.details = {"phase": "run", "errorType": "InspectionBlocked"}
        out = io.StringIO()
        with patch.object(tool, "_capture_vmware", side_effect=failure), redirect_stdout(out):
            code = tool.main(["--target", "lab2", "--expected-host", "AMD-DESKTOP"])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["reason"], "active request prevents capture")
        self.assertEqual(result["workflowFailure"]["phase"], "run")
        self.assertNotIn("image", result)


if __name__ == "__main__":
    unittest.main()
