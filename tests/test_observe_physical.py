"""Offline physical adapter checks: never call a desktop or guest service."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import observe_physical as physical


IDENTITY = {"hostName": "AMD-DESKTOP", "processId": 123, "hwnd": 456,
            "processStartUtcTicks": "638000000000000001",
            "executablePath": r"C:\Games\RIFT\rift_x64.exe", "executableSha256": "a" * 64}
WINDOW = {"pid": 123, "hwnd": 456, "process": "rift_x64", "title": "RIFT",
          "className": "RIFTWindow", "width": 800, "height": 600}
PNG = bytes.fromhex("89504e470d0a1a0a") + (13).to_bytes(4, "big") + b"IHDR" + (800).to_bytes(4, "big") + (600).to_bytes(4, "big") + b"\x00" * 15 + b"IEND" + b"\x00" * 8


class PhysicalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.host = patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP")
        self.host.start()
        self.addCleanup(self.host.stop)
        self.addCleanup(self.tmp.cleanup)

    def capture(self, **kwargs):
        return physical.capture_physical("AMD-DESKTOP", self.root / "run",
                                         allow_foreground_change=True, **kwargs)

    def test_wrong_host_calls_nothing(self):
        with patch.object(physical.socket, "gethostname", return_value="LEGION"), \
             patch.object(physical, "_identity") as identity, patch.object(physical, "_call") as call:
            self.assertEqual(self.capture()["reason"], "host-mismatch")
            identity.assert_not_called()
            call.assert_not_called()
            self.assertFalse((self.root / "run").exists())

    def test_default_denies_foreground(self):
        with patch.object(physical, "_identity") as identity, patch.object(physical, "_call") as call:
            result = physical.capture_physical("AMD-DESKTOP", self.root / "run")
            self.assertEqual(result["reason"], "desktop-ownership-required")
            identity.assert_not_called()
            call.assert_not_called()

    def test_invalid_pid_blocks_before_creating_output_or_capture(self):
        for pid in (True, 0, -1, 4294967296, "123"):
            with self.subTest(pid=pid), patch.object(physical, "_identity") as identity, \
                 patch.object(physical, "_call") as call:
                result = physical.capture_physical(
                    "AMD-DESKTOP", self.root / "run", allow_foreground_change=True,
                    physical_pid=pid)
                self.assertEqual(result["reason"], "invalid-physical-pid")
                self.assertFalse((self.root / "run").exists())
                identity.assert_not_called()
                call.assert_not_called()

    def test_identity_selects_requested_rift_pid_without_fallback(self):
        with patch.object(physical, "_run", return_value=(0, json.dumps(IDENTITY))) as run:
            self.assertEqual(physical._identity(123), IDENTITY)
            script = run.call_args.args[0][-1]
            self.assertIn("Get-Process -Name rift_x64", script)
            self.assertIn("Where-Object {$_.Id -eq 123}", script)
            self.assertIn("[Security.Cryptography.SHA256]::Create()", script)
            self.assertIn("[IO.File]::Open($path", script)
            self.assertIn("executableSha256=$exeHash", script)
            self.assertNotIn("Get-FileHash", script)
        with patch.object(physical, "_run", return_value=(0, '{"status":"not-running"}')):
            with self.assertRaisesRegex(ValueError, "^not-running$"):
                physical._identity(999)

    def test_screenshot_identity_still_requires_visible_window(self):
        invisible = {**IDENTITY, "hwnd": 0}
        with patch.object(physical, "_run", return_value=(0, json.dumps(invisible))):
            with self.assertRaisesRegex(ValueError, "no-window-or-invalid-identity"):
                physical._identity(123)
        with patch.object(physical, "_run", return_value=(0, json.dumps(invisible))):
            value = physical._identity(123, require_window=False)
        self.assertEqual(value["hwnd"], 0)

    def test_no_pid_still_rejects_multibox_ambiguity(self):
        with patch.object(physical, "_run", return_value=(0, '{"status":"ambiguous-process"}')) as run:
            with self.assertRaisesRegex(ValueError, "^ambiguous-process$"):
                physical._identity()
            self.assertNotIn("Where-Object", run.call_args.args[0][-1])

    def test_not_running(self):
        with patch.object(physical, "_identity", side_effect=ValueError("not-running")), \
             patch.object(physical, "_call") as call:
            self.assertEqual(self.capture()["reason"], "not-running")
            call.assert_not_called()

    def test_stale_before_capture(self):
        with patch.object(physical, "_identity", side_effect=[IDENTITY, {**IDENTITY, "processStartUtcTicks": "2"}]), \
             patch.object(physical, "_call", return_value={"truncated": False, "windows": [WINDOW]}) as call:
            self.assertEqual(self.capture()["reason"], "stale-identity")
            self.assertEqual(call.call_count, 1)

    def test_busy_and_quarantine_are_not_retried(self):
        for reason in ("UI_TURN_BUSY", "UI_TURN_RECOVERY_REQUIRED", "DESKTOP_TREE_UNSETTLED"):
            with self.subTest(reason=reason), patch.object(physical, "_identity", return_value=IDENTITY), \
                 patch.object(physical, "_call", side_effect=[
                     {"truncated": False, "windows": [WINDOW]}, ValueError(reason)]) as call:
                result = physical.capture_physical("AMD-DESKTOP", self.root / reason,
                                                   allow_foreground_change=True)
                self.assertEqual(result["reason"], reason)
                self.assertEqual(call.call_count, 2)

    def backend(self, tool, args, output):
        if tool == "desktop_windows":
            return {"truncated": False, "windows": [WINDOW]}
        self.assertEqual(tool, "desktop_capture_window")
        source = physical.BRIDGE / ".tools/desktop-evidence" / ("capture-" + args["requestId"] + ".png")
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(PNG)
        digest = sha256(PNG).hexdigest()
        return {"ok": True, "replayed": False, "requestId": args["requestId"], "pid": 123,
                "hwnd": 456, "process": "rift_x64", "title": "RIFT", "expectedClass": "RIFTWindow",
                "inputInjected": False, "foregroundMayChange": True,
                "capturedUtc": datetime.now(timezone.utc).isoformat(),
                "imagePath": str(source), "sha256": digest, "imageSha256Verified": digest,
                "sizeBytes": len(PNG), "imageBytesVerified": len(PNG), "width": 800, "height": 600,
                "imageDimensionsVerified": {"width": 800, "height": 600}, "mimeType": "image/png"}

    def test_success(self):
        with patch.object(physical, "BRIDGE", self.root / "bridge"), \
             patch.object(physical, "_identity", return_value=IDENTITY), \
             patch.object(physical, "_call", side_effect=self.backend):
            result = self.capture()
            self.assertEqual(result["status"], "verified-awaiting-visual-review")
            self.assertEqual(result["targetId"], "physical-amd-desktop")
            self.assertEqual(result["target"], IDENTITY)
            self.assertEqual(Path(result["image"]).read_bytes(), PNG)
            self.assertEqual(result["imageSha256"], sha256(PNG).hexdigest().upper())

    def test_selected_pid_is_checked_at_all_three_identity_gates(self):
        with patch.object(physical, "BRIDGE", self.root / "bridge"), \
             patch.object(physical, "_identity", return_value=IDENTITY) as identity, \
             patch.object(physical, "_call", side_effect=self.backend):
            result = physical.capture_physical(
                "AMD-DESKTOP", self.root / "selected", allow_foreground_change=True,
                physical_pid=123)
            self.assertEqual(result["status"], "verified-awaiting-visual-review")
            self.assertEqual(identity.call_count, 3)
            self.assertTrue(all(call.args == (123,) for call in identity.call_args_list))

    def test_selected_pid_receipt_mismatch_never_captures(self):
        with patch.object(physical, "_identity", return_value=IDENTITY), \
             patch.object(physical, "_call") as call:
            result = physical.capture_physical(
                "AMD-DESKTOP", self.root / "different", allow_foreground_change=True,
                physical_pid=999)
            self.assertEqual(result["reason"], "physical-pid-mismatch")
            call.assert_not_called()

    def test_post_capture_drift_rejects_image(self):
        with patch.object(physical, "BRIDGE", self.root / "bridge"), \
             patch.object(physical, "_identity", side_effect=[IDENTITY, IDENTITY, {**IDENTITY, "hwnd": 999}]), \
             patch.object(physical, "_call", side_effect=self.backend):
            self.assertEqual(self.capture()["reason"], "stale-identity")
            self.assertFalse((self.root / "run/image.png").exists())

    def test_corrupt_hash_rejected(self):
        def backend(*args):
            value = self.backend(*args)
            if args[0] == "desktop_capture_window":
                value["sha256"] = "0" * 64
            return value
        with patch.object(physical, "BRIDGE", self.root / "bridge"), \
             patch.object(physical, "_identity", return_value=IDENTITY), \
             patch.object(physical, "_call", side_effect=backend):
            self.assertEqual(self.capture()["reason"], "image-evidence-mismatch")

    def test_replayed_and_stale_receipts_rejected(self):
        for field, value, reason in (
                ("replayed", True, "capture-receipt-mismatch"),
                ("capturedUtc", "2000-01-01T00:00:00.000Z", "stale-capture")):
            def backend(*args):
                receipt = self.backend(*args)
                if args[0] == "desktop_capture_window":
                    receipt[field] = value
                return receipt
            with self.subTest(field=field), patch.object(physical, "BRIDGE", self.root / "bridge"), \
                 patch.object(physical, "_identity", return_value=IDENTITY), \
                 patch.object(physical, "_call", side_effect=backend):
                result = physical.capture_physical("AMD-DESKTOP", self.root / field,
                                                   allow_foreground_change=True)
                self.assertEqual(result["reason"], reason)
                self.assertFalse((self.root / field / "image.png").exists())

    def test_wrong_window_is_not_selected(self):
        with patch.object(physical, "_identity", return_value=IDENTITY), \
             patch.object(physical, "_call", return_value={"truncated": False,
                 "windows": [{**WINDOW, "hwnd": 999}]}) as call:
            self.assertEqual(self.capture()["reason"], "no-exact-window")
            self.assertEqual(call.call_count, 1)

    def test_cli_flattened_result_and_existing_service(self):
        value = {"truncated": False, "windows": [WINDOW]}
        response = {"schemaVersion": 1, "index": 0, "tool": "desktop_windows", "ok": True, "result": value}
        with patch.object(physical, "_run", return_value=(0, json.dumps(response))) as run:
            self.assertEqual(physical._call("desktop_windows", {"app": "123"}, self.root), value)
            command = run.call_args.args[0]
            self.assertIn("--service-state", command)
            self.assertNotIn("--state-dir", command)

    def test_cli_error_code_preserved(self):
        response = {"schemaVersion": 1, "index": 0, "tool": "desktop_capture_window", "ok": False,
                    "result": {"error": {"code": "UI_TURN_BUSY"}}}
        with patch.object(physical, "_run", return_value=(1, json.dumps(response))):
            with self.assertRaisesRegex(ValueError, "^UI_TURN_BUSY$"):
                physical._call("desktop_capture_window", {}, self.root)

    def test_existing_output_rejected(self):
        (self.root / "run").mkdir()
        with patch.object(physical, "_identity") as identity:
            self.assertEqual(self.capture()["reason"], "fresh-output-required")
            identity.assert_not_called()


if __name__ == "__main__":
    unittest.main()
