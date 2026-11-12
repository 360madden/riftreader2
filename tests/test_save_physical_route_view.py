"""Injected acquisition/subprocess checks for one-click saved route evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from scripts import save_physical_route_view as saved
from tests import test_plot_physical_waypoints as fixtures


class SaveViewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PlotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.target = dict(self.fixture.observation["target"], executablePath=r"C:\RIFT\rift_x64.exe")
        self.fixture.observation["target"] = deepcopy(self.target)
        self.fixture.run_render()
        self.document = deepcopy(self.fixture.route)
        self.output = self.root / "saved-view"
        self.selection = dict(status="ready", target=deepcopy(self.target))
        self.select = patch.object(saved.physical_rift, "select_physical", return_value=self.selection).start()
        self.capture = patch.object(saved.observe_target, "observe", return_value=deepcopy(self.fixture.observation)).start()
        self.process = patch.object(saved.subprocess, "run", side_effect=AssertionError("No real subprocess allowed")).start()
        self.python = self.root / "optional-python.exe"
        patch.object(saved, "VISUALIZATION_PYTHON", self.python).start()

    def save(self, **kwargs):
        values = dict(expected_host="AMD-DESKTOP", physical_pid=self.target["processId"],
            document=self.document, output=self.output, expected_target=self.target)
        values.update(kwargs)
        return saved.save_route_view(**values)

    def test_core_saved_view_uses_focus_neutral_pinned_capture_and_preserves_snapshot(self):
        original = deepcopy(self.document)
        original_observation = deepcopy(self.capture.return_value)
        native_sources = {field: Path(original_observation["nativeFacing"][field]).read_bytes()
                          for field in ("beforeOutput", "afterOutput")}
        result = self.save()
        self.assertEqual(result["status"], "saved-route-view-candidate")
        self.assertTrue(Path(result["image"]).is_file())
        self.assertTrue(Path(result["projection"]).is_file())
        self.assertEqual(result["rerun"], dict(status="unavailable", reason="visualization-environment-unavailable"))
        self.assertFalse(result["inputSent"] or result["focusChanged"])
        self.assertEqual(self.document, original)
        self.assertEqual(json.loads((self.output / "route.json").read_text()), original)
        self.assertEqual(json.loads((self.output / "view.json").read_text()), result)
        retained_observation = json.loads(Path(result["observation"]).read_text())
        for field, filename in (("beforeOutput", "native-before.json"), ("afterOutput", "native-after.json")):
            self.assertEqual((self.output / filename).read_bytes(), native_sources[field])
            self.assertEqual(retained_observation["nativeFacing"][field], str(self.output / filename))
            self.assertEqual(result["nativeSources"][field]["source"], original_observation["nativeFacing"][field])
            self.assertEqual(result["nativeSources"][field]["sha256"], hashlib.sha256(native_sources[field]).hexdigest())
            self.assertEqual(Path(original_observation["nativeFacing"][field]).read_bytes(), native_sources[field])
        self.assertEqual(self.capture.return_value, original_observation)
        self.select.assert_called_once_with("AMD-DESKTOP", self.target["processId"])
        self.capture.assert_called_once_with("physical-amd-desktop", "AMD-DESKTOP",
            output=self.output / "capture", physical_pid=self.target["processId"],
            native_facing=True, physical_capture_backend="wgc")
        self.process.assert_not_called()

    def test_stale_or_incomplete_expected_identity_and_wrong_host_prevent_capture(self):
        for field, value in (("hwnd", 999), ("processStartUtcTicks", "123"),
                             ("executableSha256", "b" * 64), ("executablePath", "different.exe")):
            with self.subTest(field=field):
                result = self.save(expected_target=dict(self.target, **{field: value}))
                self.assertEqual(result["status"], "blocked")
                self.assertIn("identity-mismatch", result["reason"])
        incomplete = dict(self.target)
        incomplete.pop("executablePath")
        self.assertEqual(self.save(expected_target=incomplete)["reason"], "complete-expected-target-required")
        self.assertEqual(self.save(expected_host="LEGION")["reason"], "host-mismatch")
        self.capture.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_missing_height_blocks_before_capture_and_retains_document(self):
        self.document["heights"][0] = None
        result = self.save()
        self.assertEqual(result["status"], "blocked")
        self.capture.assert_not_called()
        self.assertTrue((self.output / "route.json").is_file())
        self.assertTrue((self.output / "view.json").is_file())
        self.assertNotIn("image", result)

    def test_failed_or_unstable_capture_retains_evidence_without_claiming_saved_projection(self):
        self.capture.return_value = dict(status="blocked", reason="gpu-capture-returned-no-frame")
        result = self.save()
        self.assertEqual(result["reason"], "gpu-capture-returned-no-frame")
        self.assertTrue((self.output / "observation.json").is_file())
        self.assertNotIn("image", result)
        self.assertNotIn("projection", result)
        second = self.root / "unstable-view"
        self.capture.return_value = deepcopy(self.fixture.observation)
        self.capture.return_value["nativeFacing"]["status"] = "unavailable"
        result = self.save(output=second)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("stable-native-frame", result["reason"])
        self.assertFalse((second / "projection").exists())
        self.assertTrue((second / "observation.json").is_file())
        self.process.assert_not_called()

    def test_returned_target_change_blocks_projection(self):
        self.capture.return_value["target"]["hwnd"] = 999
        result = self.save()
        self.assertEqual(result["reason"], "captured-target-identity-mismatch")
        self.assertNotIn("image", result)
        self.assertFalse((self.output / "projection").exists())

    def test_partial_native_evidence_is_retained_without_inventing_missing_source(self):
        original = self.capture.return_value["nativeFacing"]["beforeOutput"]
        self.capture.return_value = dict(status="blocked", reason="gpu-capture-returned-no-frame",
            nativeFacing=dict(status="unavailable", beforeOutput=original))
        result = self.save()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual((self.output / "native-before.json").read_bytes(), Path(original).read_bytes())
        self.assertFalse((self.output / "native-after.json").exists())
        observation = json.loads((self.output / "observation.json").read_text())
        self.assertNotIn("afterOutput", observation["nativeFacing"])
        self.assertEqual(set(result["nativeSources"]), {"beforeOutput"})

    def test_missing_report_file_blocks_but_keeps_observation_and_copied_before(self):
        self.capture.return_value["nativeFacing"]["afterOutput"] = str(self.root / "missing-native.json")
        result = self.save()
        self.assertEqual(result["status"], "blocked")
        self.assertTrue((self.output / "native-before.json").is_file())
        self.assertTrue((self.output / "observation.json").is_file())
        self.assertTrue((self.output / "view.json").is_file())
        self.assertNotIn("projection", result)

    def test_optional_export_saved_hidden_bounded_offline_only(self):
        self.python.write_bytes(b"not-executed")
        def export(command, **kwargs):
            output = self.output / "view.rrd"
            self.assertEqual(command[:2], [str(self.python), str(saved.ROOT / "scripts/export_physical_rerun.py")])
            self.assertIn(str(self.output / "observation.json"), command)
            self.assertNotIn("--spawn", command)
            self.assertEqual(kwargs["timeout"], 60)
            self.assertEqual(kwargs["env"]["CI"], "1")
            self.assertNotIn("FORCE_RERUN_ANALYTICS", kwargs["env"])
            self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))
            output.write_bytes(b"fake-rrd")
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(dict(
                status="offline-rerun-evidence-export", output=str(output))))
        self.process.side_effect = export
        result = self.save()
        self.assertEqual(result["status"], "saved-route-view-candidate")
        self.assertEqual(result["rerun"], dict(status="saved", path=str(self.output / "view.rrd")))

    def test_optional_export_timeout_or_failure_is_nonfatal(self):
        self.python.write_bytes(b"not-executed")
        self.process.side_effect = subprocess.TimeoutExpired("offline-export", 60)
        result = self.save()
        self.assertEqual(result["status"], "saved-route-view-candidate")
        self.assertEqual(result["rerun"]["status"], "failed")
        self.assertTrue(Path(result["image"]).is_file())
        self.process.side_effect = None
        self.process.return_value = types.SimpleNamespace(returncode=2, stdout=json.dumps(
            dict(status="blocked", reason="rerun-sdk-0.43.1-required")))
        result = self.save(output=self.root / "export-failure")
        self.assertEqual(result["status"], "saved-route-view-candidate")
        self.assertEqual(result["rerun"], dict(status="failed", reason="rerun-sdk-0.43.1-required"))

    def test_existing_or_relative_output_refused_and_disabled_export_not_started(self):
        self.output.mkdir()
        (self.output / "preserve.txt").write_text("preserve")
        self.assertEqual(self.save()["status"], "blocked")
        self.assertEqual((self.output / "preserve.txt").read_text(), "preserve")
        self.assertEqual(self.save(output=Path("relative"))["status"], "blocked")
        self.capture.assert_not_called()
        self.python.write_bytes(b"not-executed")
        result = self.save(output=self.root / "no-export", export_rerun=False)
        self.assertEqual(result["rerun"], dict(status="unavailable", reason="not-requested"))
        self.process.assert_not_called()


class DesktopSaveViewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DesktopPairPlotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.output = self.root / "desktop-view"
        self.target = deepcopy(self.fixture.pair["targetBefore"])
        self.document = deepcopy(self.fixture.route)
        self.capture_python = self.root / "capture-python.exe"
        self.capture_python.write_bytes(b"not-executed")
        self.visualization_python = self.root / "visualization-python.exe"
        patch.object(saved, "CAPTURE_PYTHON", self.capture_python).start()
        patch.object(saved, "VISUALIZATION_PYTHON", self.visualization_python).start()
        patch.object(saved.physical_rift, "select_physical", return_value=dict(status="ready", target=self.target)).start()
        self.wgc = patch.object(saved.observe_target, "observe", side_effect=AssertionError("No implicit WGC fallback")).start()
        self.monitor = patch.object(saved, "_monitor_name", return_value=self.fixture.pair["requestedDisplay"]).start()
        self.focus = dict(status="focused-target", inputSent=False, desktopInputsDown=[], focusAttempt=dict(attempted=True),
            target=dict(machineName=self.target["hostName"], processId=self.target["processId"],
                processStartUtcTicks=self.target["processStartUtcTicks"], executablePath=self.target["executablePath"],
                executableSha256=self.target["executableSha256"], windowHandle=hex(self.target["hwnd"]), isForeground=True))
        self.pair = deepcopy(self.fixture.pair)
        self.export_commands = []
        self.process = patch.object(saved.subprocess, "run", side_effect=self.subprocess).start()

    def save(self, **kwargs):
        values = dict(expected_host="AMD-DESKTOP", physical_pid=self.target["processId"], document=self.document,
                      output=self.output, expected_target=self.target, capture_backend="desktop")
        values.update(kwargs)
        return saved.save_route_view(**values)

    def subprocess(self, command, **kwargs):
        self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if command[1] == "move-key":
            self.assertEqual(command, [str(saved.physical_rift.NATIVE_EXE), "move-key", "--focus-only",
                "--pid", str(self.target["processId"]), "--expect-start-ticks", self.target["processStartUtcTicks"],
                "--expect-sha256", self.target["executableSha256"], "--expect-hwnd", hex(self.target["hwnd"]), "--json"])
            self.assertEqual(kwargs["timeout"], 10)
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(self.focus))
        if command[1].endswith("probe_dxcam_native_pair.py"):
            self.assertEqual(command, [str(self.capture_python), str(saved.ROOT / "scripts/probe_dxcam_native_pair.py"),
                "--expected-host", "AMD-DESKTOP", "--physical-pid", str(self.target["processId"]),
                "--display", self.fixture.pair["requestedDisplay"], "--output", str(self.output / "capture"),
                "--timeout", "10", "--expect-start-ticks", self.target["processStartUtcTicks"],
                "--expect-sha256", self.target["executableSha256"], "--expect-hwnd", hex(self.target["hwnd"])])
            self.assertEqual(kwargs["timeout"], 30)
            capture = self.output / "capture"
            capture.mkdir()
            image = capture / "image.png"
            image.write_bytes(self.fixture.image.read_bytes())
            pair = deepcopy(self.pair)
            pair["image"] = str(image)
            (capture / "pair.json").write_text(json.dumps(pair))
            return types.SimpleNamespace(returncode=0, stdout="{}")
        if command[1].endswith("export_physical_rerun.py"):
            self.export_commands.append(command)
            self.assertEqual(kwargs["timeout"], 60)
            output = self.output / "view.rrd"
            output.write_bytes(b"fake-rrd")
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(dict(
                status="offline-rerun-evidence-export", output=str(output))))
        raise AssertionError("Unexpected subprocess command: " + repr(command))

    def test_desktop_focus_only_copies_exact_sources_and_renders_real_bundle(self):
        original_pair = deepcopy(self.pair)
        sources = [Path(row["path"]).read_bytes() for row in self.pair["nativeSources"]]
        result = self.save(export_rerun=False)
        self.assertEqual(result["status"], "saved-route-view-candidate", result)
        self.assertEqual(result["sourceKind"], "desktop-composite-event-candidate")
        self.assertEqual(result["captureBackend"], "desktop")
        self.assertTrue(result["focusRequested"] and result["focusChanged"])
        self.assertFalse(result["inputSent"])
        self.assertEqual(self.process.call_count, 2)
        self.monitor.assert_called_once_with(self.target["hwnd"])
        self.wgc.assert_not_called()
        pair = json.loads(Path(result["observation"]).read_text())
        self.assertEqual(pair["inputSent"], False)
        self.assertTrue(Path(pair["image"]).is_relative_to(self.output))
        for index, (field, filename) in enumerate((("nativeBeforeOutput", "native-before.json"),
                                                   ("nativeAfterOutput", "native-after.json"))):
            retained = self.output / filename
            self.assertEqual(retained.read_bytes(), sources[index])
            self.assertEqual(pair[field], str(retained))
            self.assertEqual(pair["nativeSources"][index]["path"], str(retained))
            self.assertEqual(pair["nativeSources"][index]["sha256"], hashlib.sha256(sources[index]).hexdigest())
            self.assertEqual(result["nativeSources"][field]["source"], original_pair[field])
            self.assertEqual(Path(original_pair[field]).read_bytes(), sources[index])
        self.assertEqual(self.pair, original_pair)
        projection = json.loads(Path(result["projection"]).read_text())
        self.assertEqual(projection["sourceKind"], "desktop-composite-event-candidate")
        self.assertIsNone(projection["capturedAtUtc"])
        self.assertEqual(projection["points"][0]["ground"]["pixel"], [160, 100])
        with Image.open(result["image"]) as image:
            self.assertEqual(image.size, (320, 200))
            self.assertEqual(image.getpixel((160, 100)), (255, 204, 51))

    def test_held_input_or_wrong_focus_identity_refuses_before_desktop_capture(self):
        self.focus["desktopInputsDown"] = ["W"]
        result = self.save()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.process.call_count, 1)
        self.monitor.assert_not_called()
        self.assertFalse((self.output / "capture").exists())
        self.assertTrue((self.output / "focus.json").is_file())
        self.wgc.assert_not_called()
        self.focus["desktopInputsDown"] = []
        self.focus["target"]["processStartUtcTicks"] = "123"
        result = self.save(output=self.root / "wrong-focus-target")
        self.assertEqual(result["reason"], "focus-target-identity-mismatch")
        self.assertEqual(self.process.call_count, 2)
        self.wgc.assert_not_called()

    def test_desktop_failure_or_tampered_source_never_falls_back_to_wgc(self):
        self.pair.update(status="withheld", reason="desktop-event-not-bracketed")
        result = self.save()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "desktop-event-not-bracketed")
        self.assertTrue((self.output / "capture/pair.json").is_file())
        self.assertNotIn("projection", result)
        self.wgc.assert_not_called()
        self.pair = deepcopy(self.fixture.pair)
        self.pair["nativeSources"][0]["sha256"] = "0" * 64
        self.output = self.root / "bad-hash"
        result = self.save()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "desktop-native-source-hash-mismatch")
        self.assertFalse((self.output / "projection").exists())
        self.wgc.assert_not_called()

    def test_desktop_optional_export_uses_explicit_pair_flag(self):
        self.visualization_python.write_bytes(b"not-executed")
        result = self.save()
        self.assertEqual(result["status"], "saved-route-view-candidate", result)
        self.assertEqual(result["rerun"]["status"], "saved")
        self.assertEqual(len(self.export_commands), 1)
        command = self.export_commands[0]
        self.assertIn("--desktop-pair", command)
        self.assertNotIn("--observation", command)
        self.assertEqual(command[command.index("--desktop-pair") + 1], str(self.output / "desktop-pair.json"))
        self.wgc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
