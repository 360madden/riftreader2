"""The common entry point must never cross target or backend boundaries."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import observe_target as tool
from scripts import observe_gpu, observe_physical, physical_rift, physical_turn_visual_pair


OFFLINE_PROBE_REPORT = {"status": "offline-self-test-passed", "passed": 31,
                        "inputSent": False, "frameCaptured": False}


class TargetRoutingTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict("os.environ", {"RR2_WGC_PROBE": "", "RR2_PHYSICAL_TOOLS_ROOT": ""}))
        self.hostname = patch.object(tool.socket, "gethostname", return_value="AMD-DESKTOP")
        self.hostname.start()
        self.addCleanup(self.hostname.stop)

    def result(self, target="lab2", workflow="vmware"):
        return {"status": "verified-awaiting-visual-review", "targetId": target,
                "workflow": workflow, "image": "image.bmp", "imageSha256": "A" * 64}

    def test_wgc_route_calls_local_gpu_adapter_without_legacy_capture(self):
        with patch("scripts.observe_gpu.capture_gpu", return_value=self.result(
                "physical-amd-desktop", "physical")) as gpu, patch.object(
                tool, "_capture_physical") as legacy:
            result = tool.observe("physical-amd-desktop", "AMD-DESKTOP",
                                  physical_pid=123, physical_capture_backend="wgc")
        self.assertEqual(result["workflow"], "physical")
        self.assertEqual(gpu.call_args.kwargs["physical_pid"], 123)
        legacy.assert_not_called()

    def test_wgc_route_rejects_vm_target(self):
        with self.assertRaisesRegex(ValueError, "invalid-physical-capture-backend"):
            tool.observe("lab2", "AMD-DESKTOP", historical_vm=True,
                         physical_capture_backend="wgc")

    def test_generic_and_named_physical_routes_pin_the_same_local_host(self):
        host = "RIFT-STATION"
        target_id = "physical-rift-station"
        for target in ("physical", target_id):
            with self.subTest(target=target), \
                 patch.object(tool.socket, "gethostname", return_value=host), \
                 patch.object(observe_gpu, "capture_gpu", return_value=self.result(target_id, "physical")) as gpu:
                result = tool.observe(target, "rift-station", physical_pid=123,
                                      physical_capture_backend="wgc")
            self.assertEqual(result["ownerHost"], host)
            self.assertEqual(result["targetId"], target_id)
            self.assertEqual(gpu.call_args.args[0], host)
            self.assertEqual(gpu.call_args.kwargs["physical_pid"], 123)

    def test_named_physical_route_cannot_redirect_through_local_expected_host(self):
        with patch.object(tool.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(observe_gpu, "capture_gpu") as gpu:
            with self.assertRaisesRegex(ValueError, "target-host-mismatch"):
                tool.observe("physical-legion", "RIFT-STATION", physical_capture_backend="wgc")
            gpu.assert_not_called()

    def test_cli_reports_capture_dependencies_without_game_or_desktop_access(self):
        with TemporaryDirectory() as temp, \
             patch.object(tool.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(observe_physical, "_identity") as identity, \
             patch.object(observe_gpu, "capture_gpu") as capture_gpu, \
             patch.object(observe_physical, "capture_physical") as capture_physical, \
             patch.object(observe_physical, "workbridge_root", return_value=Path(temp) / "bridge"), \
             patch.object(observe_physical, "check_workbridge_capture_service") as service, \
             patch.object(observe_gpu, "_run", return_value=(0, json.dumps(OFFLINE_PROBE_REPORT))) as probe_runner:
            probe = Path(temp) / "wgc.exe"
            probe.touch()
            with patch.object(observe_gpu, "PROBE", probe), redirect_stdout(io.StringIO()) as output:
                service.return_value = {"status": "blocked", "reason": "RUNTIME_MISMATCH"}
                args = ["--target", "physical", "--expected-host", "rift-station", "--check-dependencies"]
                self.assertEqual(tool.main(args), 2)
                result = json.loads(output.getvalue())
            self.assertEqual(result["ownerHost"], "RIFT-STATION")
            self.assertEqual(result["backendScope"], "all")
            self.assertEqual(result["wgcProbe"]["status"], "available")
            self.assertEqual(result["wgcProbe"]["checksPassed"], 31)
            self.assertEqual(probe_runner.call_args.args[0], [probe, "--self-test"])
            self.assertEqual(probe_runner.call_args.kwargs["env"]["DOTNET_DISABLE_GUI_ERRORS"], "1")
            self.assertEqual(result["desktopTurn"]["reason"], "shared-gui-evidence-directory-missing")
            self.assertEqual(result["workbridgeService"]["reason"], "RUNTIME_MISMATCH")
            self.assertFalse(result["captureAttempted"])
            identity.assert_not_called()
            capture_gpu.assert_not_called()
            capture_physical.assert_not_called()

            Path(result["desktopTurn"]["path"]).mkdir(parents=True)
            service.return_value = {"status": "available", "runtimeVersion": "0.16.5-dev"}
            with patch.object(observe_gpu, "PROBE", probe), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tool.main(args), 0)
                self.assertEqual(json.loads(output.getvalue())["status"], "capture-dependencies-ready")

    def test_backend_checks_ignore_dependencies_for_the_unselected_backend(self):
        with TemporaryDirectory() as temp, \
             patch.object(tool.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(observe_physical, "workbridge_root", return_value=Path(temp)), \
             patch.object(observe_physical, "check_workbridge_capture_service") as service, \
             patch.object(observe_gpu, "_run", return_value=(0, json.dumps(OFFLINE_PROBE_REPORT))) as probe_runner:
            (Path(temp) / ".tools" / "desktop-evidence").mkdir(parents=True)
            probe = Path(temp) / "wgc.exe"
            args = ["--target", "physical", "--expected-host", "RIFT-STATION",
                    "--check-dependencies", "--physical-capture-backend"]

            with patch.object(observe_gpu, "PROBE", probe), redirect_stdout(io.StringIO()) as output:
                service.return_value = {"status": "available", "runtimeVersion": "0.16.5-dev"}
                self.assertEqual(tool.main([*args, "workbridge"]), 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result["backendScope"], "workbridge")
                self.assertNotIn("wgcProbe", result)
                probe_runner.assert_not_called()

            probe.touch()
            service.reset_mock()
            with patch.dict("os.environ", {"RR2_WGC_PROBE": str(probe)}), \
                 redirect_stdout(io.StringIO()) as output:
                self.assertEqual(tool.main([*args, "wgc"]), 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result["backendScope"], "wgc")
                self.assertEqual(result["wgcProbe"]["path"], str(probe))
                self.assertNotIn("workbridgeService", result)
            probe_runner.assert_called_once()
            self.assertEqual(probe_runner.call_args.args[0], [probe, "--self-test"])
            service.assert_not_called()

    def test_wgc_startup_checks_use_both_tools_from_the_copied_bundle(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "Copied physical tools"
            reader = bundle / "native-reader" / "RiftReader2.Live.exe"
            probe = bundle / "wgc-probe" / "PhysicalWgcProbe.exe"
            for tool_path in (reader, probe):
                tool_path.parent.mkdir(parents=True)
                tool_path.touch()
            (root / ".tools" / "desktop-evidence").mkdir(parents=True)
            help_text = "RiftReader2.Live native tools\nsample-current-facing --pid N"
            with patch.dict("os.environ", {"RR2_NATIVE_READER": "", "RR2_PHYSICAL_TOOLS_ROOT": str(bundle)}), \
                 patch.object(observe_physical, "workbridge_root", return_value=root), \
                 patch.object(observe_physical, "_run", return_value=(0, help_text)) as reader_runner, \
                 patch.object(observe_gpu, "_run", return_value=(0, json.dumps(OFFLINE_PROBE_REPORT))) as probe_runner:
                result = tool.observe("physical", "AMD-DESKTOP", check_dependencies=True, native_facing=True)
                self.assertEqual(result["status"], "capture-dependencies-ready")
                self.assertEqual(result["nativeReader"]["nativeReaderPath"], str(reader))
                self.assertEqual(result["wgcProbe"]["path"], str(probe))
                reader_runner.assert_called_once()
                self.assertEqual(reader_runner.call_args.args[0], [reader, "--help"])
                self.assertEqual(probe_runner.call_args.args[0], [probe, "--self-test"])
                with patch.object(physical_rift, "read_native") as native:
                    physical_rift.bind_native_reader(native, None)({}, "facing")
                    native.assert_called_once_with({}, "facing", native_reader=reader)

    def test_individual_overrides_take_precedence_over_bundle_root(self):
        with TemporaryDirectory() as temp:
            reader = Path(temp) / "RiftReader2.Live.exe"
            probe = Path(temp) / "PhysicalWgcProbe.exe"
            with patch.dict("os.environ", {"RR2_PHYSICAL_TOOLS_ROOT": "relative-bundle",
                                           "RR2_NATIVE_READER": str(reader), "RR2_WGC_PROBE": str(probe)}):
                self.assertEqual(physical_rift._native_reader_path(), reader)
                self.assertEqual(observe_gpu._probe_path(), probe)

    def test_incomplete_bundle_does_not_fall_back_to_a_default_probe(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            available_default = root / "default.exe"
            available_default.touch()
            with patch.dict("os.environ", {"RR2_PHYSICAL_TOOLS_ROOT": str(root / "incomplete")}), \
                 patch.object(observe_gpu, "PROBE", available_default), patch.object(observe_gpu, "_run") as run:
                result = observe_gpu.check_probe()
            self.assertEqual(result["reason"], "gpu-probe-build-required")
            self.assertEqual(result["path"], str(root / "incomplete" / "wgc-probe" / "PhysicalWgcProbe.exe"))
            run.assert_not_called()

    def test_invalid_probe_override_refuses_preflight_and_capture(self):
        with TemporaryDirectory() as temp, \
             patch.dict("os.environ", {"RR2_WGC_PROBE": "relative/PhysicalWgcProbe.exe"}), \
             patch.object(observe_gpu, "_identity") as identity, \
             patch.object(observe_gpu, "_run") as runner:
            output = Path(temp) / "capture"
            preflight = observe_gpu.check_probe()
            capture = observe_gpu.capture_gpu("AMD-DESKTOP", output)
            self.assertFalse(output.exists())
        self.assertEqual(preflight["reason"], "invalid-gpu-probe-path")
        self.assertEqual(capture["reason"], "invalid-gpu-probe-path")
        identity.assert_not_called()
        runner.assert_not_called()

    def test_present_wgc_executable_must_pass_offline_self_test(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".tools" / "desktop-evidence").mkdir(parents=True)
            probe = root / "probe.exe"
            probe.touch()
            for code, response, reason in (
                    (0x80008083, "", "gpu-probe-dotnet-runtime-unavailable"),
                    (-2147450730, "", "gpu-probe-dotnet-runtime-unavailable"),
                    (0x8000809A, "", "gpu-probe-publish-incomplete"),
                    (2, "", "gpu-probe-self-test-failed"),
                    (0, "", "gpu-probe-self-test-report-invalid"),
                    (0, json.dumps({**OFFLINE_PROBE_REPORT, "frameCaptured": True}),
                     "gpu-probe-self-test-report-invalid")):
                with self.subTest(code=code, response=response), \
                     patch.object(observe_physical, "workbridge_root", return_value=root), \
                     patch.object(observe_gpu, "PROBE", probe), \
                     patch.object(observe_gpu, "_run", return_value=(code, response)):
                    result = tool.observe("physical", "AMD-DESKTOP", check_dependencies=True,
                                          physical_capture_backend="wgc")
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["wgcProbe"]["reason"], reason)
                if code:
                    self.assertEqual(result["wgcProbe"]["exitCode"], code)

    def test_explicit_workbridge_capture_keeps_the_foreground_admission_check(self):
        result = tool.observe("physical", "AMD-DESKTOP", physical_capture_backend="workbridge")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "desktop-ownership-required")
        with self.assertRaisesRegex(ValueError, "native-facing-requires-focus-neutral-physical-capture"):
            tool.observe("physical", "AMD-DESKTOP", physical_capture_backend="workbridge", native_facing=True)

    def test_missing_wgc_python_dependency_is_reported_without_hiding_workbridge_status(self):
        with TemporaryDirectory() as temp, \
             patch.object(observe_physical, "workbridge_root", return_value=Path(temp)), \
             patch.object(observe_physical, "check_workbridge_capture_service", return_value={"status": "available"}), \
             patch.object(observe_gpu, "frame_tools", side_effect=ValueError("wgc-python-pillow-unavailable")), \
             patch.object(observe_gpu, "PROBE", Path(temp) / "probe.exe"), \
             patch.object(observe_gpu, "_run", return_value=(0, json.dumps(OFFLINE_PROBE_REPORT))), \
             patch.object(observe_gpu, "_identity") as identity:
            observe_gpu.PROBE.touch()
            (Path(temp) / ".tools" / "desktop-evidence").mkdir(parents=True)
            result = tool.observe("physical", "AMD-DESKTOP", check_dependencies=True)
            capture = observe_gpu.capture_gpu("AMD-DESKTOP", Path(temp) / "capture")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["wgcImageVerifier"]["reason"], "wgc-python-pillow-unavailable")
        self.assertEqual(result["workbridgeService"]["status"], "available")
        self.assertEqual(capture["reason"], "wgc-python-pillow-unavailable")
        identity.assert_not_called()

    def test_capture_dependency_check_rejects_foreign_host_and_capture_options(self):
        for target, host, extra, reason in (
                ("physical", "LEGION", [], "host-mismatch"),
                ("lab1", "AMD-DESKTOP", [], "capture-dependency-check-incompatible-options"),
                ("physical", "AMD-DESKTOP", ["--allow-foreground-change"],
                 "capture-dependency-check-incompatible-options")):
            with self.subTest(target=target, host=host), redirect_stdout(io.StringIO()) as output, \
                 patch.object(tool, "_check_capture_dependencies") as check:
                self.assertEqual(tool.main(["--target", target, "--expected-host", host,
                                            "--check-dependencies", *extra]), 2)
                self.assertEqual(json.loads(output.getvalue())["reason"], reason)
                check.assert_not_called()

    def test_wgc_backend_passes_local_identity_and_checks_receipt(self):
        target = {"hostName": "RIFT-STATION", "processId": 123, "hwnd": 456,
                  "processStartUtcTicks": "638000000000000001", "executableSha256": "a" * 64}
        report = {"machine": "RIFT-STATION", "requestedBackend": "wgc",
                  "capturedCompletedAtUtc": "2026-11-22T19:00:00Z",
                  "targetBefore": {"pid": 123, "hwnd": 456, "startTicks": 638000000000000001,
                                   "sha256": "A" * 64}}
        with TemporaryDirectory() as folder:
            root = Path(folder)
            probe = root / "probe.exe"
            probe.touch()
            with patch.dict("os.environ", {"RR2_WGC_PROBE": str(probe)}), \
                 patch.object(observe_gpu.socket, "gethostname", return_value="RIFT-STATION"), \
                 patch.object(observe_gpu, "_identity", return_value=target) as identity, \
                 patch.object(observe_gpu, "_run", return_value=(0, "")) as runner, \
                 patch.object(physical_turn_visual_pair, "read_frame", return_value=(report, None, "B" * 64)):
                result = observe_gpu.capture_gpu("rift-station", root / "output", physical_pid=123)
        self.assertEqual(result["status"], "verified-awaiting-visual-review")
        self.assertEqual(result["targetId"], "physical-rift-station")
        self.assertFalse(result["foregroundMayChange"])
        self.assertEqual(identity.call_count, 2)
        command = runner.call_args.args[0]
        self.assertEqual(command[0], probe)
        self.assertEqual(command[command.index("--host") + 1], "RIFT-STATION")
        self.assertEqual(command[command.index("--pid") + 1], 123)
        self.assertEqual(runner.call_args.kwargs["env"]["DOTNET_DISABLE_GUI_ERRORS"], "1")

    def test_capture_reports_runtime_startup_failure_without_reading_image(self):
        target = {"hostName": "RIFT-STATION", "processId": 123, "hwnd": 456,
                  "processStartUtcTicks": "638000000000000001", "executableSha256": "a" * 64}
        with TemporaryDirectory() as folder:
            root = Path(folder)
            probe = root / "probe.exe"
            probe.touch()
            with patch.dict("os.environ", {"RR2_WGC_PROBE": str(probe)}), \
                 patch.object(observe_gpu.socket, "gethostname", return_value="RIFT-STATION"), \
                 patch.object(observe_gpu, "_identity", return_value=target), \
                 patch.object(observe_gpu, "_run", return_value=(0x80008083, "")), \
                 patch.object(physical_turn_visual_pair, "read_frame") as read_frame:
                result = observe_gpu.capture_gpu("rift-station", root / "output", physical_pid=123)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "gpu-probe-dotnet-runtime-unavailable")
        read_frame.assert_not_called()

    def test_retired_vm_targets_are_denied_by_default_without_adapter_calls(self):
        for target in ("lab1", "lab2"):
            with self.subTest(target=target), \
                 patch.object(tool, "_capture_vmware") as vm, \
                 patch.object(tool, "_capture_host_preview") as host:
                with self.assertRaisesRegex(ValueError, "vmware-retired-use-physical-rift"):
                    tool.observe(target, "AMD-DESKTOP")
                vm.assert_not_called()
                host.assert_not_called()

    def test_vm_cli_requires_explicit_archival_flag(self):
        output = io.StringIO()
        with patch.object(tool, "_capture_vmware") as vm, \
             patch.object(tool, "_capture_host_preview") as host, redirect_stdout(output):
            code = tool.main(["--target", "lab2", "--expected-host", "AMD-DESKTOP"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["reason"], "vmware-retired-use-physical-rift")
        vm.assert_not_called()
        host.assert_not_called()

    def test_wrong_machine_blocks_before_either_adapter(self):
        with patch.object(tool.socket, "gethostname", return_value="LEGION"), patch.object(
                tool, "_capture_vmware") as vm, patch.object(tool, "_capture_physical") as physical:
            with self.assertRaisesRegex(ValueError, "host-mismatch"):
                tool.observe("lab2", "AMD-DESKTOP", historical_vm=True)
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
            result = tool.observe("lab2", "amd-desktop", Path("fresh"), historical_vm=True)
        vm.assert_called_once_with("lab2", Path("fresh"), False)
        physical.assert_not_called()
        self.assertEqual(result["ownerHost"], "AMD-DESKTOP")

    def test_native_read_is_explicit(self):
        with patch.object(tool, "_capture_vmware", return_value=self.result()) as vm:
            tool.observe("lab2", "AMD-DESKTOP", native_vitals=True, historical_vm=True)
        vm.assert_called_once_with("lab2", None, True)

    def test_physical_does_not_touch_vmware(self):
        with patch.object(tool, "_capture_vmware") as vm, patch.object(tool, "_capture_physical",
                return_value=self.result("physical-amd-desktop", "physical")) as physical:
            tool.observe("physical-amd-desktop", "AMD-DESKTOP", allow_foreground_change=True)
        vm.assert_not_called()
        physical.assert_called_once_with("AMD-DESKTOP", None, True, None)

    def test_physical_pid_routes_to_exact_adapter_only(self):
        with patch.object(tool, "_capture_vmware") as vm, patch.object(tool, "_capture_physical",
                 return_value=self.result("physical-amd-desktop", "physical")) as physical:
            result = tool.observe("physical-amd-desktop", "AMD-DESKTOP",
                                  allow_foreground_change=True, physical_pid=123)
        vm.assert_not_called()
        physical.assert_called_once_with("AMD-DESKTOP", None, True, 123)
        self.assertEqual(result["targetId"], "physical-amd-desktop")

    def test_physical_pid_is_rejected_for_labs_and_invalid_values(self):
        with patch.object(tool, "_capture_vmware") as vm, \
             patch.object(tool, "_capture_physical") as physical:
            with self.assertRaisesRegex(ValueError, "physical-pid-incompatible-target"):
                tool.observe("lab2", "AMD-DESKTOP", physical_pid=123, historical_vm=True)
            for pid in (True, 0, -1, 4294967296, "123"):
                with self.subTest(pid=pid), self.assertRaisesRegex(ValueError, "invalid-physical-pid"):
                    tool.observe("physical-amd-desktop", "AMD-DESKTOP", physical_pid=pid)
            vm.assert_not_called()
            physical.assert_not_called()

    def test_cli_passes_physical_pid(self):
        out = io.StringIO()
        with patch.object(tool, "_capture_physical",
                 return_value=self.result("physical-amd-desktop", "physical")) as physical, \
             redirect_stdout(out):
            code = tool.main(["--target", "physical-amd-desktop", "--expected-host", "AMD-DESKTOP",
                              "--allow-foreground-change", "--physical-pid", "123"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "verified-awaiting-visual-review")
        physical.assert_called_once_with("AMD-DESKTOP", None, True, 123)

    def test_legion_requires_actual_legion(self):
        with patch.object(tool.socket, "gethostname", return_value="LEGION"), patch.object(
                tool, "_capture_physical", return_value=self.result("physical-legion", "physical")) as physical:
            tool.observe("physical-legion", "LEGION")
        physical.assert_called_once_with("LEGION", None, False, None)

    def test_unqualified_requests_fail_without_fallback(self):
        for target, opts in (("lab1", {"native_vitals": True}), ("physical-amd-desktop", {"native_vitals": True})):
            with self.subTest(target=target), patch.object(tool, "_capture_vmware") as vm, patch.object(
                    tool, "_capture_physical") as physical:
                with self.assertRaisesRegex(ValueError, "not-yet-qualified"):
                    tool.observe(target, "AMD-DESKTOP", historical_vm=(target == "lab1"), **opts)
                vm.assert_not_called()
                physical.assert_not_called()

    def test_invalid_preview_width_does_not_capture(self):
        with patch.object(tool, "_capture_vmware") as vm:
            with self.assertRaisesRegex(ValueError, "invalid-preview-width"):
                tool.observe("lab2", "AMD-DESKTOP", with_preview=True, preview_width=10, historical_vm=True)
            vm.assert_not_called()

    def test_wrong_target_receipt_is_not_published(self):
        with patch.object(tool, "_capture_vmware", return_value=self.result("lab1")):
            with self.assertRaisesRegex(ValueError, "adapter-target-mismatch"):
                tool.observe("lab2", "AMD-DESKTOP", historical_vm=True)

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
            result = tool.observe("lab2", "AMD-DESKTOP", with_preview=True, historical_vm=True)
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
                                  preview_detail_crop=(0, 0, 850, 250), historical_vm=True)
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
                                  preview_detail_crop=(0, 0, 850, 250), historical_vm=True)
        capture.assert_called_once()
        paired.assert_not_called()
        self.assertNotIn("detailPreview", result)

    def test_detail_crop_requires_explicit_preview_before_capture(self):
        with patch.object(tool, "_capture_vmware") as capture:
            with self.assertRaisesRegex(ValueError, "detail-crop-requires-preview"):
                tool.observe("lab2", "AMD-DESKTOP", preview_detail_crop=(0, 0, 850, 250), historical_vm=True)
            capture.assert_not_called()

    def test_invalid_detail_crop_fails_before_capture(self):
        for crop in ((-1, 0, 200, 300), (0, 0, 0, 300),
                     (0, 0, 8193, 200), (0, 0, True, 200),
                     ("0", 0, 200, 300), (0, 0, 200), [0, 0, 200, -1]):
            with self.subTest(crop=crop), patch.object(tool, "_capture_vmware") as capture:
                with self.assertRaisesRegex(ValueError, "invalid-preview-crop"):
                    tool.observe("lab2", "AMD-DESKTOP", with_preview=True,
                                 preview_detail_crop=crop, historical_vm=True)
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
                              "--allow-historical-vm", "--preview", "--preview-detail-crop", "0", "0", "850", "250"])
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
            result = tool.observe("lab2", "AMD-DESKTOP", host_preview=True, historical_vm=True)
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
                    tool.observe(target, "AMD-DESKTOP", host_preview=True, historical_vm=(target != "physical-amd-desktop"), **options)
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
                    tool.observe("lab2", "AMD-DESKTOP", host_preview=True, historical_vm=True)

    def test_host_preview_cli_preserves_non_authoritative_status(self):
        receipt = {"status": "captured-nonauthoritative", "lab": "lab1",
                   "movementEligible": False, "gameProcessIdentityVerified": False}
        out = io.StringIO()
        with patch.object(tool, "_capture_host_preview", return_value=receipt), \
             patch.object(tool, "_capture_vmware") as vm, redirect_stdout(out):
            code = tool.main(["--target", "lab1", "--expected-host", "AMD-DESKTOP",
                              "--allow-historical-vm", "--host-preview"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "captured-nonauthoritative")
        self.assertFalse(json.loads(out.getvalue())["movementEligible"])
        vm.assert_not_called()

    def test_cli_failure_retains_sanitized_workflow_reason(self):
        failure = ValueError("active request prevents capture")
        failure.details = {"phase": "run", "errorType": "InspectionBlocked"}
        out = io.StringIO()
        with patch.object(tool, "_capture_vmware", side_effect=failure), redirect_stdout(out):
            code = tool.main(["--target", "lab2", "--expected-host", "AMD-DESKTOP",
                              "--allow-historical-vm"])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["reason"], "active request prevents capture")
        self.assertEqual(result["workflowFailure"]["phase"], "run")
        self.assertNotIn("image", result)


if __name__ == "__main__":
    unittest.main()
