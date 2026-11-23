"""Fenced-pair tests inject every clock/device/native/desktop dependency."""
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from scripts import probe_dxcam as capture, probe_dxcam_native_pair as pair
from tests import test_plot_physical_waypoints as fixtures
from tests import test_probe_dxcam as device_fixture


class DependencyTests(unittest.TestCase):
    def test_dependency_cli_checks_the_selected_reader_without_a_game_process(self):
        with (patch.object(pair.socket, "gethostname", return_value="RIFT-STATION"),
              patch.object(pair, "check_capture_python", return_value={"dxcamVersion": capture.DXCAM_VERSION}),
              patch.object(pair.native, "check_native_reader", return_value={"status": "ready"}) as reader,
              patch.object(pair.native, "select_physical") as select,
              redirect_stdout(StringIO()) as output):
            options = ["--expected-host", "rift-station", "--check-dependencies",
                       "--native-reader", "published reader.exe"]
            self.assertEqual(pair.main(options), 0)
        reader.assert_called_once_with("rift-station", Path("published reader.exe"), kind="facing")
        select.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertFalse(report["inputSent"] or report["focusChanged"])

    def test_missing_packages_and_wrong_host_skip_reader_startup(self):
        with (patch.object(pair.socket, "gethostname", return_value="RIFT-STATION"),
              patch.object(capture.importlib.util, "find_spec", return_value=None) as find_spec,
              patch.object(pair.native, "check_native_reader") as reader):
            wrong_host = pair.check_dependencies("OTHER-PC")
            find_spec.assert_not_called()
            report = pair.check_dependencies("RIFT-STATION")
        reader.assert_not_called()
        self.assertEqual(wrong_host["reason"], "host-mismatch")
        self.assertEqual(report["reason"], "dxcam-python-dependencies-missing")
        self.assertEqual(report["missingPackages"], ["dxcam", "Pillow", "numpy", "comtypes"])

    def test_dxcam_inventory_detects_missing_files_and_shadowed_packages(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initializer = root / "dxcam/__init__.py"
            backend = root / "dxcam/core/dxgi_duplicator.py"
            backend.parent.mkdir(parents=True)
            initializer.touch()
            metadata = root / "dxcam-0.3.0.dist-info"
            metadata.mkdir()
            (metadata / "METADATA").write_text("Name: dxcam\nVersion: 0.3.0\n", encoding="utf-8")
            (metadata / "RECORD").write_text(
                "dxcam/__init__.py,sha256=placeholder,0\n"
                "dxcam/core/dxgi_duplicator.py,sha256=placeholder,0\n", encoding="utf-8")
            distribution = capture.importlib.metadata.PathDistribution(metadata)
            with (patch.object(pair.socket, "gethostname", return_value="RIFT-STATION"),
                  patch.object(capture.importlib.metadata, "distribution", return_value=distribution),
                  patch.object(capture.importlib.util, "find_spec",
                               return_value=SimpleNamespace(origin=str(initializer))) as spec,
                  patch.object(pair.native, "check_native_reader", return_value={"status": "ready"}) as reader):
                result = pair.check_dependencies("RIFT-STATION")
                self.assertEqual(result["reason"], "dxcam-python-installation-incomplete")
                self.assertEqual(result["missingFiles"], ["dxcam/core/dxgi_duplicator.py"])
                backend.touch()
                spec.return_value = SimpleNamespace(origin=str(root / "other/dxcam/__init__.py"))
                result = pair.check_dependencies("RIFT-STATION")
                self.assertEqual(result["reason"], "dxcam-python-package-location-mismatch")
                reader.assert_not_called()
                spec.return_value = SimpleNamespace(origin=str(initializer))
                self.assertEqual(pair.check_dependencies("RIFT-STATION")["status"], "ready")
                reader.assert_called_once()


class Qpc:
    def __init__(self):
        self.value = 1000
        self.freq = 1000
    def read(self):
        self.value += 10
        return self.value
    def frequency(self):
        return self.freq
    def perf_ns(self):
        return (self.value + 5) * 10**6


class Backend(device_fixture.Backend):
    def __init__(self, qpc):
        super().__init__()
        self.qpc = qpc
        self.mode = "new"
    def peek(self, camera):
        tick = self.qpc.value + 2
        if self.mode == "old":
            tick = 100
        if self.mode == "future":
            tick += 10000
        if self.mode == "empty":
            return None
        frame = np.zeros((40, 60, 4), dtype=np.uint8)
        frame[:] = [3, 5, 7, 255]
        return frame, tick, tick / self.qpc.freq, self.qpc.freq


class PairTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.PlotTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.target = deepcopy(device_fixture.TARGET)
        self.clock, self.qpc = device_fixture.Clock(), Qpc()
        self.backend = Backend(self.qpc)
        self.info = SimpleNamespace(monotonic=True, adjustable=False, implementation="fake QPC")
        self.snap = {"clientRect": [-1900, -50, 60, 40], "foreground": True}
        self.reports = [deepcopy(fixture.before), deepcopy(fixture.after)]
        self.native_calls = []
        self.select_calls = 0
        self.native_duration = 0
        self.enterContext(patch.object(pair.observe_physical, "require_clear_desktop_turn"))

    def select(self, host, pid):
        self.select_calls += 1
        return {"status": "ready", "target": deepcopy(self.target)}

    def read_native(self, selection, kind, **kwargs):
        index = len(self.native_calls)
        self.native_calls.append((kind, kwargs))
        path = self.root / ("native" + str(index) + ".json")
        path.write_text(json.dumps(self.reports[index]))
        self.clock.value += self.native_duration
        return {"status": "complete", "target": deepcopy(self.target), "nativeOutput": str(path)}

    def run_pair(self, **kwargs):
        return pair.probe(kwargs.pop("expected_host", "AMD-DESKTOP"), 123, device_fixture.DISPLAY, self.root / "out",
            timeout=kwargs.pop("timeout", 1), select=kwargs.pop("select", self.select),
            snapshot=kwargs.pop("snapshot", lambda _: deepcopy(self.snap)), backend_loader=lambda: self.backend,
            read_native=self.read_native, qpc=self.qpc, perf_ns=self.qpc.perf_ns,
            clock=self.clock, sleep=self.clock.sleep, clock_info=self.info, **kwargs)

    def test_fenced_pair_accepts_another_verified_local_host(self):
        self.target["hostName"] = "RIFT-STATION"
        reader = self.root / "published reader.exe"
        reader.touch()
        with patch.object(pair.socket, "gethostname", return_value=self.target["hostName"]):
            result = self.run_pair(expected_host="rift-station", native_reader=reader)
        self.assertEqual(result["status"], "stable-native-composite-event-candidate")
        self.assertEqual(result["targetBefore"]["hostName"], self.target["hostName"])
        self.assertEqual(result["targetBefore"], result["targetAfter"])
        self.assertEqual([options["native_reader"] for _, options in self.native_calls], [reader, reader])

    def test_fenced_event_order_age_calibration_pixels_hash_and_cleanup(self):
        result = self.run_pair()
        self.assertEqual(result["status"], "stable-native-composite-event-candidate")
        self.assertEqual(result["outputLocalCrop"], [20, 50, 80, 90])
        marks, event = result["qpcMarks"], result["event"]
        self.assertGreater(event["backendTicks"], marks["nativeBeforeReturnedFence"] + 1)
        self.assertLessEqual(event["backendTicks"], marks["frameAccepted"] + 1)
        self.assertLessEqual(marks["frameAccepted"], marks["nativeAfterInvoked"])
        self.assertEqual(len(result["clockBefore"]["samples"]), 8)
        self.assertEqual(len(result["clockAfter"]["samples"]), 8)
        self.assertEqual(event["backendEventAgeBoundsSeconds"], [0, .009])
        self.assertEqual(self.native_calls, [("facing", dict(samples=1, include_target=True))] * 2)
        self.assertEqual(self.select_calls, 2)
        self.assertTrue(self.backend.camera.stopped and self.backend.camera.released)
        self.assertEqual(result["targetBefore"], result["targetAfter"])
        from PIL import Image
        with Image.open(result["image"]) as image:
            self.assertEqual(image.getpixel((0, 0)), (7, 5, 3))
        self.assertEqual(result["imageSha256"], hashlib.sha256(Path(result["image"]).read_bytes()).hexdigest())
        self.assertEqual(len(result["nativeSources"]), 2)
        self.assertFalse(result["inputSent"])

    def test_calibration_rejects_epoch_mismatch_and_adjustable_clock(self):
        with self.assertRaisesRegex(ValueError, "incompatible"):
            pair.calibrate(self.qpc, lambda: 0, self.info)
        with self.assertRaisesRegex(ValueError, "monotonic"):
            pair.calibrate(self.qpc, self.qpc.perf_ns, SimpleNamespace(monotonic=True, adjustable=True))
        self.assertFalse(self.backend.camera.started)

    def test_stale_buffer_cannot_pass_post_native_fence(self):
        original = self.backend.peek
        count = 0
        def peek(camera):
            nonlocal count
            count += 1
            if count > 1:
                self.backend.mode = "old"
            return original(camera)
        self.backend.peek = peek
        result = self.run_pair(timeout=.15)
        self.assertEqual(result["status"], "withheld")
        self.assertEqual(result["reason"], "cooperative-deadline-expired")
        self.assertEqual(len(self.native_calls), 1)
        self.assertTrue(self.backend.camera.released)
        self.assertNotIn("image", result)

    def test_future_event_refused(self):
        self.backend.mode = "future"
        result = self.run_pair()
        self.assertEqual(result["reason"], "future-backend-event")
        self.assertTrue(self.backend.camera.released)

    def test_camera_change_with_each_side_internally_stable_refused(self):
        for name in ("opticalCameraCandidate", "opticalCameraAfterTargetCandidate"):
            self.reports[1]["observation"][name]["cameraAddressDecimal"] = "2096815868168"
        result = self.run_pair()
        self.assertEqual(result["status"], "withheld")
        self.assertEqual(result["reason"], "native-camera-player-bracket-changed")
        self.assertNotIn("image", result)

    def test_native_identity_mismatch_refused(self):
        report = self.reports[1]
        report["identity"]["processId"] = 999
        result = self.run_pair()
        self.assertEqual(result["status"], "withheld")
        self.assertNotIn("image", result)

    def test_final_process_identity_change_refused(self):
        count = 0
        def select(host, pid):
            nonlocal count
            count += 1
            return {"status": "ready", "target": deepcopy(self.target) if count == 1 else dict(self.target, processStartUtcTicks="2")}
        result = self.run_pair(select=select)
        self.assertEqual(result["reason"], "final-target-changed")
        self.assertNotIn("image", result)

    def test_foreground_changed_before_native_read_withheld(self):
        self.snap["foreground"] = False
        result = self.run_pair()
        self.assertEqual(result["reason"], "target-not-foreground")
        self.assertFalse(self.backend.camera.started)
        self.assertEqual(self.native_calls, [])

    def test_native_pair_longer_than_five_seconds_withheld(self):
        self.native_duration = 2.6
        result = self.run_pair(timeout=10)
        self.assertEqual(result["reason"], "native-bracket-exceeded-five-seconds")
        self.assertTrue(self.backend.camera.released)

    def test_cleanup_error_withholds_success(self):
        def fail():
            raise RuntimeError("fake release failure")
        self.backend.camera.release = fail
        result = self.run_pair()
        self.assertEqual(result["reason"], "camera-cleanup-failed")
        self.assertTrue(self.backend.camera.stopped)
        self.assertNotIn("image", result)

    def test_display_mismatch_refuses_camera_without_fallback(self):
        self.backend.rows = []
        result = self.run_pair()
        self.assertEqual(result["reason"], "display-missing-or-ambiguous")
        self.assertFalse(self.backend.camera.started)

    def test_client_change_withheld(self):
        count = 0
        def snapshot(_):
            nonlocal count
            count += 1
            return deepcopy(self.snap) if count < 4 else dict(self.snap, clientRect=[-1899, -50, 60, 40])
        result = self.run_pair(snapshot=snapshot)
        self.assertEqual(result["reason"], "client-or-foreground-changed")
        self.assertTrue(self.backend.camera.released)

    def test_wrong_host_and_timeout_refused(self):
        with patch.object(pair.socket, "gethostname", return_value="LEGION"), self.assertRaises(ValueError):
            self.run_pair()
        with self.assertRaises(ValueError):
            self.run_pair(timeout=31)
        self.assertFalse(self.backend.camera.started)

    def test_expected_epoch_mismatch_refused_before_device_initialization(self):
        result = self.run_pair(expected_start_ticks="1", expected_sha256=self.target["executableSha256"],
                               expected_hwnd=self.target["hwnd"])
        self.assertEqual(result["reason"], "expected-target-identity-mismatch")
        self.assertFalse(self.backend.camera.started)
        self.assertEqual(self.native_calls, [])
        self.assertNotIn("image", result)

    def test_partial_expectations_refused_before_selection(self):
        with self.assertRaisesRegex(ValueError, "together"):
            self.run_pair(expected_start_ticks=self.target["processStartUtcTicks"])
        self.assertEqual(self.select_calls, 0)


if __name__ == "__main__":
    unittest.main()
