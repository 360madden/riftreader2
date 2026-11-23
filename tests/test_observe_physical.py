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
NODE_VERSION = (0, "v24.20.0\n")


class PhysicalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.enterContext(patch.object(physical.os, "environ", dict(physical.os.environ)))
        physical.os.environ.pop("RR2_WORKBRIDGE_ROOT", None)
        physical.os.environ.pop("RR2_WORKBRIDGE_CLI_ROOT", None)
        physical.os.environ.pop("RR2_WORKBRIDGE_NODE", None)
        self.node = self.root / "system-node.exe"
        self.node.touch()
        self.enterContext(patch.object(physical, "NODE", self.node))
        self.enterContext(patch.object(physical, "BRIDGE", self.root / "default-bridge"))
        self.install_cli(physical.BRIDGE)
        self.install_desktop_files(physical.BRIDGE)
        self.alternate = self.root / "alternate install" / "workbridge"
        self.install_cli(self.alternate)
        self.install_desktop_files(self.alternate)
        self.host = patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP")
        self.host.start()
        self.addCleanup(self.host.stop)
        self.addCleanup(self.tmp.cleanup)

    def capture(self, **kwargs):
        return physical.capture_physical("AMD-DESKTOP", self.root / "run",
                                         allow_foreground_change=True, **kwargs)

    @staticmethod
    def install_cli(root):
        (root / "scripts").mkdir(parents=True)
        (root / "scripts/workbridge-cli.mjs").touch()
        (root / ".local").mkdir()

    @staticmethod
    def install_desktop_files(root):
        (root / "dist").mkdir()
        for name in ("desktop-ui.mjs", "desktop-capture.mjs"):
            (root / "dist" / name).touch()

    def test_desktop_turn_check_refuses_missing_directory_locks_and_quarantine(self):
        evidence = self.root / ".tools" / "desktop-evidence"
        with patch.object(physical, "BRIDGE", self.root):
            with self.assertRaisesRegex(ValueError, "shared-gui-evidence-directory-missing"):
                physical.require_clear_desktop_turn()
            evidence.mkdir(parents=True)
            for filename in ("desktop-input-turn.lock", "desktop-turn-admission.lock",
                             "desktop-turn-quarantine-test.json"):
                with self.subTest(filename=filename):
                    blocker = evidence / filename
                    blocker.touch()
                    with self.assertRaisesRegex(ValueError, "desktop-turn-recovery-required"):
                        physical.require_clear_desktop_turn()
                    blocker.unlink()
            physical.require_clear_desktop_turn()
            self.assertEqual(list(evidence.iterdir()), [])

    def test_configured_root_checks_its_guard_without_falling_back(self):
        (physical.BRIDGE / ".tools" / "desktop-evidence").mkdir(parents=True)
        bridge = self.root / "alternate install" / "workbridge"
        physical.os.environ["RR2_WORKBRIDGE_ROOT"] = str(bridge)
        with self.assertRaisesRegex(ValueError, "shared-gui-evidence-directory-missing"):
            physical.require_clear_desktop_turn()
        evidence = bridge / ".tools" / "desktop-evidence"
        evidence.mkdir(parents=True)
        blocker = evidence / "DESKTOP-TURN-ADMISSION.LOCK"
        blocker.mkdir()
        with self.assertRaisesRegex(ValueError, "desktop-turn-recovery-required"):
            physical.require_clear_desktop_turn()
        blocker.rmdir()
        physical.require_clear_desktop_turn()

    def test_workbridge_root_rejects_relative_and_parent_paths(self):
        for path in ("", "relative", str(self.root / "placeholder" / ".." / "bridge")):
            with self.subTest(path=path), patch.dict(physical.os.environ, RR2_WORKBRIDGE_ROOT=path):
                with self.assertRaisesRegex(ValueError, "invalid-workbridge-root"):
                    physical.workbridge_root()

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

    def test_other_local_host_still_requires_foreground_authority(self):
        with patch.object(physical.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(physical, "_identity") as identity, patch.object(physical, "_call") as call:
            result = physical.capture_physical("rift-station", self.root / "run")
        self.assertEqual(result["reason"], "desktop-ownership-required")
        self.assertEqual(result["targetId"], "physical-rift-station")
        identity.assert_not_called()
        call.assert_not_called()

    def test_workbridge_can_use_node_from_path(self):
        response = json.dumps({"tool": "desktop_windows", "index": 0,
                               "ok": True, "result": {"windows": []}})
        with patch.object(physical, "NODE", self.root / "missing-node.exe"), \
             patch.object(physical.shutil, "which", return_value="node-from-path.exe"), \
             patch.object(physical, "_run", return_value=(0, response)) as runner:
            command = physical._workbridge_command(physical.workbridge_root())
            result = physical._call(command, "desktop_windows", {}, self.root)
        self.assertEqual(result, {"windows": []})
        self.assertEqual(runner.call_args.args[0][0], "node-from-path.exe")

    def test_configured_node_does_not_fall_back_or_select_rift_when_invalid(self):
        cases = (("", "invalid-workbridge-node-path"), ("relative.exe", "invalid-workbridge-node-path"),
                 (str(self.root / "node.cmd"), "invalid-workbridge-node-path"),
                 (str(self.root / "missing-node.exe"), "desktop-node-runtime-unavailable"))
        for path, reason in cases:
            with self.subTest(path=path), patch.dict(physical.os.environ, RR2_WORKBRIDGE_NODE=path), \
                 patch.object(physical, "_identity") as identity, patch.object(physical, "_run") as run:
                self.assertEqual(physical.check_workbridge_capture_service(physical.BRIDGE),
                                 {"status": "blocked", "reason": reason})
                self.assertEqual(self.capture()["reason"], reason)
                self.assertFalse((self.root / "run").exists())
                identity.assert_not_called()
                run.assert_not_called()

    def test_workbridge_preflight_blocks_an_old_or_unusable_node_before_catalog_discovery(self):
        for output, reason in (((0, "v22.4.1\n"), "desktop-node-version-unsupported"),
                               ((1, "bad runtime"), "desktop-node-version-unavailable"),
                               ((0, "not node"), "desktop-node-version-unavailable")):
            with self.subTest(output=output), patch.object(physical, "_run", return_value=output) as run:
                result = physical.check_workbridge_capture_service(physical.BRIDGE)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["nodeExecutable"], str(self.node))
                run.assert_called_once_with([self.node, "--version"], 5)
                if reason == "desktop-node-version-unsupported":
                    self.assertEqual(result["nodeVersion"], "v22.4.1")
                    self.assertEqual(result["minimumNodeMajor"], 24)

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

    def backend(self, command, tool, args, output):
        if tool == "desktop_windows":
            return {"truncated": False, "windows": [WINDOW]}
        self.assertEqual(tool, "desktop_capture_window")
        source = command[3].parent / ".tools/desktop-evidence" / ("capture-" + args["requestId"] + ".png")
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
        node = self.root / "installed with spaces" / "node.exe"
        node.parent.mkdir()
        node.touch()
        with patch.dict(physical.os.environ, RR2_WORKBRIDGE_ROOT=str(self.alternate),
                        RR2_WORKBRIDGE_NODE=str(node)), \
             patch.object(physical, "_identity", return_value=IDENTITY), \
             patch.object(physical, "_call", side_effect=self.backend) as call:
            result = self.capture()
            self.assertEqual(result["status"], "verified-awaiting-visual-review")
            self.assertEqual(result["targetId"], "physical-amd-desktop")
            self.assertEqual(result["target"], IDENTITY)
            self.assertEqual(Path(result["image"]).read_bytes(), PNG)
            self.assertEqual(result["imageSha256"], sha256(PNG).hexdigest().upper())
            self.assertEqual([entry.args[0] for entry in call.call_args_list], [
                [node, self.alternate / "scripts/workbridge-cli.mjs", "--service-state", self.alternate / ".local"]
            ] * 2)

    def test_rejects_capture_evidence_from_different_installation(self):
        def backend(command, tool, args, output):
            return self.backend([*command[:3], self.alternate / ".local"], tool, args, output)

        with patch.dict(physical.os.environ, RR2_WORKBRIDGE_CLI_ROOT=str(self.alternate)), \
             patch.object(physical, "_identity", return_value=IDENTITY), \
             patch.object(physical, "_call", side_effect=backend):
            self.assertEqual(self.capture()["reason"], "unexpected-image-path")

    def test_selected_pid_is_checked_at_all_three_identity_gates(self):
        with patch.object(physical, "BRIDGE", self.alternate), \
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
        with patch.object(physical, "BRIDGE", self.alternate), \
             patch.object(physical, "_identity", side_effect=[IDENTITY, IDENTITY, {**IDENTITY, "hwnd": 999}]), \
             patch.object(physical, "_call", side_effect=self.backend):
            self.assertEqual(self.capture()["reason"], "stale-identity")
            self.assertFalse((self.root / "run/image.png").exists())

    def test_corrupt_hash_rejected(self):
        def backend(*args, **kwargs):
            value = self.backend(*args, **kwargs)
            if args[1] == "desktop_capture_window":
                value["sha256"] = "0" * 64
            return value
        with patch.object(physical, "BRIDGE", self.alternate), \
             patch.object(physical, "_identity", return_value=IDENTITY), \
             patch.object(physical, "_call", side_effect=backend):
            self.assertEqual(self.capture()["reason"], "image-evidence-mismatch")

    def test_replayed_and_stale_receipts_rejected(self):
        for field, value, reason in (
                ("replayed", True, "capture-receipt-mismatch"),
                ("capturedUtc", "2000-01-01T00:00:00.000Z", "stale-capture")):
            def backend(*args, **kwargs):
                receipt = self.backend(*args, **kwargs)
                if args[1] == "desktop_capture_window":
                    receipt[field] = value
                return receipt
            with self.subTest(field=field), patch.object(physical, "BRIDGE", self.alternate), \
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
        bridge = self.alternate
        with patch.dict(physical.os.environ, RR2_WORKBRIDGE_ROOT=str(bridge)), \
             patch.object(physical, "_run", return_value=(0, json.dumps(response))) as run:
            command = physical._workbridge_command(physical.workbridge_root())
            self.assertEqual(physical._call(command, "desktop_windows", {"app": "123"}, self.root), value)
            command = run.call_args.args[0]
            self.assertIn("--service-state", command)
            self.assertEqual(command[1:4], [bridge / "scripts" / "workbridge-cli.mjs",
                                           "--service-state", bridge / ".local"])
            self.assertNotIn("--root", command)
            self.assertNotIn("--state-dir", command)

    def test_separate_cli_uses_the_active_service_for_discovery_and_calls(self):
        cli_root = self.root / "compatible Workbridge CLI"
        cli = cli_root / "scripts" / "workbridge-cli.mjs"
        cli.parent.mkdir(parents=True)
        cli.touch()
        catalog = {"ok": True, "discovery": "tools", "serverVersion": "0.16.4-dev",
                   "tools": [{"name": "desktop_windows"}, {"name": "desktop_capture_window"}]}
        windows = {"schemaVersion": 1, "index": 0, "tool": "desktop_windows", "ok": True,
                   "result": {"truncated": False, "windows": [WINDOW]}}
        with patch.dict(physical.os.environ, RR2_WORKBRIDGE_CLI_ROOT=str(cli_root)), \
             patch.object(physical, "_run", side_effect=[
                 NODE_VERSION, (0, json.dumps(catalog)), (0, json.dumps(windows))]) as run:
            service = physical.check_workbridge_capture_service(physical.workbridge_root())
            self.assertEqual(service, {"status": "available", "runtimeVersion": "0.16.4-dev", "cliPath": str(cli),
                                       "nodeExecutable": str(self.node), "nodeVersion": "v24.20.0"})
            command = physical._workbridge_command(physical.workbridge_root())
            self.assertEqual(physical._call(command, "desktop_windows", {"app": "123"}, self.root), windows["result"])
        for call in run.call_args_list[1:]:
            self.assertEqual(call.args[0][1:4], [cli, "--service-state", physical.BRIDGE / ".local"])
        self.assertFalse((cli_root / ".local").exists())
        self.assertFalse((cli_root / ".tools").exists())

    def test_staged_cli_runners_do_not_replace_deployed_files(self):
        (physical.BRIDGE / "dist/desktop-capture.mjs").unlink()
        cli = self.alternate / "scripts/workbridge-cli.mjs"
        with patch.dict(physical.os.environ, RR2_WORKBRIDGE_CLI_ROOT=str(self.alternate)), \
             patch.object(physical, "_run", return_value=NODE_VERSION) as run, \
             patch.object(physical, "_identity") as identity, patch.object(physical, "_call") as call:
            result = physical.check_workbridge_capture_service(physical.BRIDGE)
            self.assertEqual(self.capture()["reason"], "desktop-workbridge-runner-files-missing")
            identity.assert_not_called()
            call.assert_not_called()
            self.assertFalse((self.root / "run").exists())
        self.assertEqual(result, {"status": "blocked", "reason": "desktop-workbridge-runner-files-missing",
                                  "cliPath": str(cli),
                                  "nodeExecutable": str(self.node), "nodeVersion": "v24.20.0",
                                  "missingFiles": ["dist/desktop-capture.mjs"]})
        run.assert_called_once_with([self.node, "--version"], 5)

    def test_runner_gaps_are_reported_even_when_node_is_missing(self):
        (physical.BRIDGE / "dist/desktop-ui.mjs").unlink()
        with patch.dict(physical.os.environ, RR2_WORKBRIDGE_NODE=str(self.root / "missing.exe")), \
             patch.object(physical, "_run") as run:
            result = physical.check_workbridge_capture_service(physical.BRIDGE)
        self.assertEqual(result, {"status": "blocked", "reason": "desktop-node-runtime-unavailable",
                                  "missingFiles": ["dist/desktop-ui.mjs"]})
        run.assert_not_called()

    def test_explicit_invalid_or_missing_cli_refuses_without_using_default(self):
        cases = (("", "invalid-workbridge-cli-root"), ("relative", "invalid-workbridge-cli-root"),
                 (str(self.root / "placeholder" / ".." / "cli"), "invalid-workbridge-cli-root"),
                 (str(self.root / "absent"), "desktop-workbridge-cli-unavailable"))
        for path, reason in cases:
            with self.subTest(path=path), patch.dict(physical.os.environ, RR2_WORKBRIDGE_CLI_ROOT=path), \
                 patch.object(physical, "_run") as run:
                self.assertEqual(physical.check_workbridge_capture_service(physical.BRIDGE),
                                 {"status": "blocked", "reason": reason})
                self.assertEqual(self.capture()["reason"], reason)
                run.assert_not_called()
                self.assertFalse((self.root / "run").exists())

    def test_workbridge_preflight_discovers_both_tools_and_reports_missing_tools_and_versions(self):
        bridge = self.root / "install" / "workbridge"
        cli = bridge / "scripts" / "workbridge-cli.mjs"
        cli.parent.mkdir(parents=True)
        cli.touch()
        (bridge / ".local").mkdir()
        self.install_desktop_files(bridge)
        cases = (
            (0, {"ok": True, "discovery": "tools", "serverVersion": "0.16.5-dev",
                 "tools": [{"name": "desktop_windows"}, {"name": "desktop_capture_window"}, {"name": "other"}]},
             {"status": "available", "runtimeVersion": "0.16.5-dev"}),
            (0, {"ok": True, "discovery": "tools", "serverVersion": "0.16.5-dev",
                 "tools": [{"name": "desktop_capture_window"}]},
             {"status": "blocked", "reason": "TOOL_NOT_FOUND", "runtimeVersion": "0.16.5-dev",
              "missingTools": ["desktop_windows"]}),
            (2, {"ok": False, "error": {"code": "RUNTIME_MISMATCH",
                                       "expectedVersion": "0.16.5-dev", "runtimeVersion": "0.16.4-dev",
                                       "message": "text not needed in the preflight receipt"}},
             {"status": "blocked", "reason": "RUNTIME_MISMATCH",
              "expectedVersion": "0.16.5-dev", "runtimeVersion": "0.16.4-dev"}),
        )
        for code, response, expected in cases:
            with self.subTest(expected=expected), \
                 patch.object(physical, "NODE", self.root / "no-system-node.exe"), \
                 patch.object(physical.shutil, "which", return_value="node-from-path.exe"), \
                 patch.object(physical, "_run", side_effect=[NODE_VERSION, (code, json.dumps(response))]) as run:
                self.assertEqual(physical.check_workbridge_capture_service(bridge), {
                    **expected, "cliPath": str(cli), "nodeExecutable": "node-from-path.exe", "nodeVersion": "v24.20.0"})
                command = run.call_args.args[0]
                self.assertEqual(command[1:], [cli, "--service-state", bridge / ".local",
                                                "--list-tools", "--timeout", "6", "--json"])
                self.assertEqual(run.call_args.args[1], 10)

    def test_cli_error_code_preserved(self):
        response = {"schemaVersion": 1, "index": 0, "tool": "desktop_capture_window", "ok": False,
                    "result": {"error": {"code": "UI_TURN_BUSY"}}}
        with patch.object(physical, "_run", return_value=(1, json.dumps(response))):
            with self.assertRaisesRegex(ValueError, "^UI_TURN_BUSY$"):
                command = physical._workbridge_command(physical.workbridge_root())
                physical._call(command, "desktop_capture_window", {}, self.root)

    def test_existing_output_rejected(self):
        (self.root / "run").mkdir()
        with patch.object(physical, "_identity") as identity:
            self.assertEqual(self.capture()["reason"], "fresh-output-required")
            identity.assert_not_called()


if __name__ == "__main__":
    unittest.main()
