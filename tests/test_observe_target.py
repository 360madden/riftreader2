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

    def test_paired_preview_uses_single_verified_capture(self):
        pair = {"fullFrame": {"nonAuthoritative": True, "previewFormat": "webp",
                              "sourceSha256": "A" * 64},
                "detail": {"nonAuthoritative": True, "previewFormat": "jpeg",
                           "sourceSha256": "A" * 64}}
        with patch.object(tool, "_capture_vmware", return_value=self.result()) as capture, \
             patch.object(tool, "_paired_preview", return_value=pair) as paired, \
             patch.object(tool, "_preview") as old_preview:
            result = tool.observe("lab2", "AMD-DESKTOP", with_preview=True,
                                  preview_detail_crop=(0, 0, 850, 250))
        capture.assert_called_once()
        paired.assert_called_once_with(result, 840, (0, 0, 850, 250))
        old_preview.assert_not_called()
        self.assertEqual(result["preview"], pair["fullFrame"])
        self.assertEqual(result["detailPreview"], pair["detail"])

    def test_paired_preview_is_only_read_after_verified_capture(self):
        blocked = {"status": "blocked", "reason": "owner-busy",
                   "targetId": "lab2", "workflow": "vmware"}
        with patch.object(tool, "_capture_vmware", return_value=blocked) as capture, \
             patch.object(tool, "_paired_preview") as paired:
            result = tool.observe("lab2", "AMD-DESKTOP", with_preview=True,
                                  preview_detail_crop=(0, 0, 850, 250))
        capture.assert_called_once()
        paired.assert_not_called()
        self.assertNotIn("detailPreview", result)

    def test_detail_crop_requires_explicit_preview_before_capture(self):
        with patch.object(tool, "_capture_vmware") as capture:
            with self.assertRaisesRegex(ValueError, "detail-crop-requires-preview"):
                tool.observe("lab2", "AMD-DESKTOP", preview_detail_crop=(0, 0, 850, 250))
            capture.assert_not_called()

    def test_invalid_detail_crop_fails_before_capture(self):
        for crop in ((-1, 0, 200, 300), (0, 0, 0, 300),
                     (0, 0, 8193, 200), (0, 0, True, 200),
                     ("0", 0, 200, 300), (0, 0, 200), [0, 0, 200, -1]):
            with self.subTest(crop=crop), patch.object(tool, "_capture_vmware") as capture:
                with self.assertRaisesRegex(ValueError, "invalid-preview-crop"):
                    tool.observe("lab2", "AMD-DESKTOP", with_preview=True,
                                 preview_detail_crop=crop)
                capture.assert_not_called()

    def test_cli_rejects_crop_without_preview_before_capture(self):
        out = io.StringIO()
        with patch.object(tool, "_capture_vmware") as capture, redirect_stdout(out):
            code = tool.main(["--target", "lab2", "--expected-host", "AMD-DESKTOP",
                              "--preview-detail-crop", "0", "0", "850", "250"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["reason"], "detail-crop-requires-preview")
        capture.assert_not_called()

    def test_cli_paired_preview_one_capture_result(self):
        out = io.StringIO()
        pair = {"fullFrame": {"nonAuthoritative": True, "previewFormat": "webp"},
                "detail": {"nonAuthoritative": True, "previewFormat": "jpeg"}}
        with patch.object(tool, "_capture_vmware", return_value=self.result()) as capture, \
             patch.object(tool, "_paired_preview", return_value=pair) as paired, \
             redirect_stdout(out):
            code = tool.main(["--target", "lab2", "--expected-host", "AMD-DESKTOP",
                              "--preview", "--preview-detail-crop", "0", "0", "850", "250"])
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        capture.assert_called_once()
        paired.assert_called_once()
        self.assertEqual(result["preview"]["previewFormat"], "webp")
        self.assertEqual(result["detailPreview"]["previewFormat"], "jpeg")

    def test_fast_host_preview_is_separate_from_game_capture(self):
        receipt = {"status": "captured-nonauthoritative", "lab": "lab2",
                   "image": "host-image.png", "movementEligible": False,
                   "gameProcessIdentityVerified": False, "gameInputSent": False}
        with patch.object(tool, "_capture_host_preview", return_value=receipt) as host, \
             patch.object(tool, "_capture_vmware") as vm, \
             patch.object(tool, "_capture_physical") as physical:
            result = tool.observe("lab2", "AMD-DESKTOP", host_preview=True)
        host.assert_called_once_with("lab2", "AMD-DESKTOP", None)
        vm.assert_not_called()
        physical.assert_not_called()
        self.assertEqual(result["status"], "captured-nonauthoritative")
        self.assertEqual(result["targetId"], "lab2")
        self.assertEqual(result["workflow"], "vmware")
        self.assertEqual(result["ownerHost"], "AMD-DESKTOP")
        self.assertFalse(result["movementEligible"])
        self.assertNotIn("captureId", result)

    def test_host_preview_rejects_conflicting_modes_before_capture(self):
        cases = (("lab2", {"native_vitals": True}),
                 ("lab2", {"with_preview": True}),
                 ("lab2", {"allow_foreground_change": True}),
                 ("physical-amd-desktop", {}))
        for target, options in cases:
            with self.subTest(target=target, options=options), \
                 patch.object(tool, "_capture_host_preview") as host, \
                 patch.object(tool, "_capture_vmware") as vm:
                with self.assertRaisesRegex(ValueError, "host-preview-incompatible-options"):
                    tool.observe(target, "AMD-DESKTOP", host_preview=True, **options)
                host.assert_not_called()
                vm.assert_not_called()

    def test_host_preview_rejects_authoritative_or_mismatched_receipts(self):
        baseline = {"status": "captured-nonauthoritative", "lab": "lab2",
                    "movementEligible": False, "gameProcessIdentityVerified": False}
        variants = ({"lab": "lab1"}, {"movementEligible": True},
                    {"gameProcessIdentityVerified": True},
                    {"status": "verified-awaiting-visual-review"})
        for changes in variants:
            with self.subTest(changes=changes), \
                 patch.object(tool, "_capture_host_preview",
                              return_value=dict(baseline, **changes)):
                with self.assertRaisesRegex(ValueError, "host-preview-invalid-receipt"):
                    tool.observe("lab2", "AMD-DESKTOP", host_preview=True)

    def test_host_preview_cli_preserves_non_authoritative_status(self):
        receipt = {"status": "captured-nonauthoritative", "lab": "lab1",
                   "movementEligible": False, "gameProcessIdentityVerified": False}
        out = io.StringIO()
        with patch.object(tool, "_capture_host_preview", return_value=receipt), \
             patch.object(tool, "_capture_vmware") as vm, redirect_stdout(out):
            code = tool.main(["--target", "lab1", "--expected-host", "AMD-DESKTOP",
                              "--host-preview"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "captured-nonauthoritative")
        self.assertFalse(json.loads(out.getvalue())["movementEligible"])
        vm.assert_not_called()

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
