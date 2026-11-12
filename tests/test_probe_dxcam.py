"""Injected DXcam pilot checks; this module never imports dxcam or touches a desktop."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
import numpy as np

from scripts import probe_dxcam as probe


TARGET = {"hostName": "AMD-DESKTOP", "processId": 123, "processStartUtcTicks": "638000000000000001",
          "executablePath": r"C:\Games\rift_x64.exe", "executableSha256": "a" * 64, "hwnd": 456}
DISPLAY = r"\\.\DISPLAY5"
OUTPUT = {"deviceIndex": 1, "outputIndex": 2, "deviceName": DISPLAY, "adapter": "AMD test",
          "desktopRect": [-1920, -100, 0, 980], "attachedToDesktop": True, "rotationDegrees": 0}


class Clock:
    def __init__(self):
        self.value = 0
    def __call__(self):
        self.value += .001
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class Camera:
    def __init__(self):
        self.started = self.stopped = self.released = False
    def start(self, **kwargs):
        self.started = True
        self.options = kwargs
    def stop(self):
        self.stopped = True
    def release(self):
        self.released = True


class Backend:
    def __init__(self, ticks=(50, 100, 100, 200, 300)):
        self.rows = [deepcopy(OUTPUT)]
        self.ticks = iter(ticks)
        self.camera = Camera()
        self.last = None
    def outputs(self):
        return deepcopy(self.rows)
    def create(self, selected, crop):
        self.selected, self.crop = selected, crop
        return self.camera
    def peek(self, camera):
        tick = next(self.ticks, self.last)
        self.last = tick
        if tick is None:
            return None
        image = np.zeros((40, 60, 4), dtype=np.uint8)
        image[:] = [3, 5, 7, 255]
        return image, tick, tick / 1000, 1000


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock, self.backend = Clock(), Backend()
        self.target = deepcopy(TARGET)
        self.snapshot = {"clientRect": [-1900, -50, 60, 40], "foreground": True}
        self.select_calls = []
        self.loader_calls = 0
        patcher = patch.object(probe.socket, "gethostname", return_value="AMD-DESKTOP")
        patcher.start()
        self.addCleanup(patcher.stop)

    def select(self, host, pid):
        self.select_calls.append((host, pid))
        return {"status": "ready", "target": deepcopy(self.target)}

    def load(self):
        self.loader_calls += 1
        return self.backend

    def run_probe(self, **kwargs):
        return probe.probe("AMD-DESKTOP", 123, DISPLAY, self.root / "out",
            frames=kwargs.pop("frames", 3), timeout=kwargs.pop("timeout", 1),
            select=kwargs.pop("select", self.select),
            snapshot=kwargs.pop("snapshot", lambda _: deepcopy(self.snapshot)),
            backend_loader=self.load, clock=self.clock, sleep=self.clock.sleep, **kwargs)

    def test_negative_origin_crop_new_ticks_rgb_receipt_cleanup(self):
        result = self.run_probe()
        self.assertEqual(result["status"], "diagnostic-desktop-composite")
        self.assertEqual(result["outputLocalCrop"], [20, 50, 80, 90])
        self.assertEqual([r["backendTicks"] for r in result["frames"]], [100, 200, 300])
        self.assertEqual(result["duplicatePolls"], 1)
        self.assertEqual(result["targetBefore"], result["targetAfter"])
        self.assertEqual(self.select_calls, [("AMD-DESKTOP", 123)] * 2)
        self.assertEqual(result["warmupFrame"]["backendTicks"], 50)
        self.assertEqual(result["frames"][0]["backendGapSeconds"], .05)
        self.assertFalse(result["nativeCameraBracket"])
        self.assertIsNone(result["timestampAgeSeconds"])
        self.assertEqual(self.backend.camera.options, dict(target_fps=60, video_mode=False, delay=0))
        self.assertTrue(self.backend.camera.stopped and self.backend.camera.released)
        from PIL import Image
        for item in result["images"]:
            path = Path(item["path"])
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            with Image.open(path) as image:
                self.assertEqual(image.size, (60, 40))
                self.assertEqual(image.getpixel((0, 0)), (7, 5, 3))
        self.assertEqual(json.loads(Path(result["report"]).read_text())["acceptedFrames"], 3)

    def test_foreground_refusal_before_dxcam_load(self):
        self.snapshot["foreground"] = False
        result = self.run_probe()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.loader_calls, 0)
        self.assertNotIn("images", result)

    def test_no_fallback_on_missing_or_duplicate_display(self):
        for rows in ([], [deepcopy(OUTPUT), deepcopy(OUTPUT)]):
            with self.subTest(rows=rows):
                self.backend.rows = rows
                # Each trial has a fresh output directory.
                result = probe.probe("AMD-DESKTOP", 123, DISPLAY, self.root / str(len(rows)),
                    select=self.select, snapshot=lambda _: deepcopy(self.snapshot),
                    backend_loader=self.load, clock=self.clock, sleep=self.clock.sleep)
                self.assertEqual(result["reason"], "display-missing-or-ambiguous")
                self.assertFalse(self.backend.camera.started)

    def test_cross_monitor_rectangle_refused(self):
        self.snapshot["clientRect"] = [-20, -50, 60, 40]
        result = self.run_probe()
        self.assertEqual(result["reason"], "whole-client-must-fit-selected-monitor")
        self.assertFalse(self.backend.camera.started)

    def test_stale_duplicate_frames_timeout_and_cleanup(self):
        self.backend = Backend((100,))
        result = self.run_probe(timeout=.15)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["acceptedFrames"], 0)
        self.assertEqual(result["warmupFrame"]["backendTicks"], 100)
        self.assertGreater(result["duplicatePolls"], 0)
        self.assertTrue(self.backend.camera.stopped and self.backend.camera.released)
        self.assertNotIn("images", result)

    def test_empty_frames_timeout_and_cleanup(self):
        self.backend = Backend((None,))
        result = self.run_probe(timeout=.15)
        self.assertEqual(result["acceptedFrames"], 0)
        self.assertGreater(result["emptyPolls"], 0)
        self.assertTrue(self.backend.camera.released)

    def test_regressed_timestamp_refused(self):
        self.backend = Backend((100, 90))
        result = self.run_probe()
        self.assertEqual(result["reason"], "backend-timestamp-regressed")
        self.assertTrue(self.backend.camera.released)

    def test_changed_final_pid_start_hash_hwnd_rejected(self):
        for field, value in (("processId", 999), ("processStartUtcTicks", "2"),
                             ("executableSha256", "b"*64), ("hwnd", 999)):
            with self.subTest(field=field):
                count = 0
                def select(host, pid):
                    nonlocal count
                    count += 1
                    return {"status": "ready", "target": deepcopy(TARGET) if count == 1 else dict(TARGET, **{field: value})}
                backend, clock = Backend(), Clock()
                result = probe.probe("AMD-DESKTOP", 123, DISPLAY, self.root / field, frames=2,
                    select=select, snapshot=lambda _: deepcopy(self.snapshot), backend_loader=lambda: backend,
                    clock=clock, sleep=clock.sleep)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "final-target-identity-changed")
                self.assertNotIn("images", result)
                self.assertTrue(backend.camera.released)

    def test_changed_client_rect_during_capture_rejected(self):
        count = 0
        def snapshot(_):
            nonlocal count
            count += 1
            return deepcopy(self.snapshot) if count < 4 else dict(self.snapshot, clientRect=[-1899, -50, 60, 40])
        result = self.run_probe(snapshot=snapshot)
        self.assertEqual(result["reason"], "target-client-or-foreground-changed")
        self.assertTrue(self.backend.camera.released)

    def test_start_failure_still_stops_and_releases(self):
        def fail(**_):
            raise RuntimeError("fake start failure")
        self.backend.camera.start = fail
        result = self.run_probe()
        self.assertEqual(result["reason"], "fake start failure")
        self.assertTrue(self.backend.camera.stopped and self.backend.camera.released)

    def test_cleanup_failure_is_not_success(self):
        def fail():
            raise RuntimeError("fake stop failure")
        self.backend.camera.stop = fail
        result = self.run_probe()
        self.assertEqual(result["reason"], "camera-cleanup-failed")
        self.assertTrue(self.backend.camera.released)
        self.assertNotIn("images", result)

    def test_invalid_bounds_and_existing_output_do_not_initialize(self):
        for kwargs in (dict(frames=121), dict(frames=True), dict(timeout=31), dict(timeout=float("nan"))):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.run_probe(**kwargs)
        (self.root / "out").mkdir()
        with self.assertRaisesRegex(ValueError, "fresh-output"):
            self.run_probe()
        self.assertEqual(self.loader_calls, 0)

    def test_wrong_host_refused(self):
        with patch.object(probe.socket, "gethostname", return_value="LEGION"), self.assertRaises(ValueError):
            self.run_probe()
        self.assertEqual(self.loader_calls, 0)

    def test_atomic_nonblocking_peek_does_not_call_public_waiter(self):
        # Exercise installed-adapter strategy against an injected camera, not DXcam.
        class Runtime:
            def peek_latest_with_ticks(self, copy):
                self.copied = copy
                return "frame", 200
        class Dup:
            performance_frequency = 1000
            def ticks_to_seconds(self, ticks):
                return ticks / 1000
        camera = Camera()
        camera._DXCamera__lock = threading.Lock()
        camera._DXCamera__capture_runtime = Runtime()
        camera._duplicator = Dup()
        backend = object.__new__(probe._DXcamBackend)
        self.assertEqual(backend.peek(camera), ("frame", 200, .2, 1000))
        self.assertTrue(camera._DXCamera__capture_runtime.copied)
        camera._DXCamera__lock.acquire()
        try:
            self.assertIsNone(backend.peek(camera))
        finally:
            camera._DXCamera__lock.release()


if __name__ == "__main__":
    unittest.main()
