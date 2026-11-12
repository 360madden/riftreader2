"""Injected HWND diagnostic tests; never import windows_capture or access desktop."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from scripts import probe_windows_capture as pilot


TARGET = dict(hostName="AMD-DESKTOP", processId=123, processStartUtcTicks="638000000000000001",
              executablePath=r"C:\Games\rift_x64.exe", executableSha256="a"*64, hwnd=456)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory())
        self.output = Path(self.temp) / "probe"
        self.enterContext(patch.object(pilot.socket, "gethostname", return_value="AMD-DESKTOP"))
        self.geometry = dict(clientRect=[-1920, 404, 80, 64], foreground=True)
        self.buffer = np.zeros((70, 84, 4), dtype=np.uint8)
        self.buffer[:] = [3, 2, 1, 255]
        self.buffer[10:50, 10:60] = [30, 100, 220, 255]
        self.frame = NS(frame_buffer=self.buffer, width=84, height=70, timespan=10000000)
        self.internal = NS(stop=Mock())
        self.control = NS(stop=Mock(), wait=Mock())
        self.start = Mock(side_effect=self.deliver)
        self.backend = NS(start=self.start)
        self.select_calls = 0
        self.time = 1.

    def deliver(self, hwnd, on_frame, on_closed):
        self.assertEqual(456, hwnd)
        on_frame(self.frame, self.internal)
        return object(), self.control

    def select(self, host, pid):
        self.select_calls += 1
        return dict(status="ready", target=deepcopy(TARGET))

    def run_probe(self, **kwargs):
        return pilot.probe("AMD-DESKTOP", 123, self.output,
            select=kwargs.pop("select", self.select), snapshot=kwargs.pop("snapshot", lambda _: deepcopy(self.geometry)),
            backend_loader=lambda: self.backend, clock=lambda: self.time, **kwargs)

    def test_exact_hwnd_single_copied_frame_pixels_metadata_hash_cleanup(self):
        original = self.deliver
        def mutate_after_callback(*args):
            result = original(*args)
            self.buffer[:] = 0  # Copied inside callback, before this storage changes.
            return result
        self.start.side_effect = mutate_after_callback
        result = self.run_probe()
        self.assertEqual("diagnostic-hwnd-frame-candidate", result["status"])
        self.assertEqual(result["targetBefore"], result["targetAfter"])
        self.assertEqual(result["snapshotBefore"], result["snapshotAfter"])
        self.assertEqual((84, 70, 10000000), (result["frameWidth"], result["frameHeight"], result["frameTimespan"]))
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["focusChanged"])
        self.assertFalse(result["nativeCameraBracket"])
        self.assertIsNone(result["timestampAgeSeconds"])
        with Image.open(result["image"]) as image:
            self.assertEqual((220, 100, 30), image.getpixel((20, 20)))
        self.assertEqual(result["imageSha256"], hashlib.sha256(Path(result["image"]).read_bytes()).hexdigest())
        self.internal.stop.assert_called_once()
        self.control.stop.assert_called_once()
        self.control.wait.assert_called_once()
        self.assertEqual(2, self.select_calls)

    def test_black_frame_truthfully_withheld_without_png(self):
        self.buffer[:] = 0
        result = self.run_probe()
        self.assertEqual("withheld", result["status"])
        self.assertEqual("frame-blank-or-uninformative", result["reason"])
        self.assertTrue(result["quality"]["potentiallyBlankOrBlack"])
        self.assertFalse((self.output / "frame.png").exists())
        self.assertTrue((self.output / "probe.json").is_file())

    def test_colored_chrome_cannot_qualify_black_client_interior(self):
        self.buffer[:] = 0
        self.buffer[:5, :] = [180, 30, 130, 255]
        result = self.run_probe()
        self.assertEqual("withheld", result["status"])
        self.assertEqual("frame-interior-blank-or-uninformative", result["reason"])
        self.assertFalse(result["quality"]["wholeSurfacePotentiallyBlankOrBlack"])
        self.assertTrue(result["quality"]["potentiallyBlankOrBlack"])
        self.assertTrue(result["quality"]["interiorHeuristic"]["potentiallyBlankOrBlack"])
        self.assertIn("not verified client mapping", result["quality"]["interiorHeuristic"]["basis"])
        self.assertFalse((self.output / "frame.png").exists())

    def test_invalid_shape_timespan_or_dimensions_stop_and_withhold(self):
        cases = [dict(width=0), dict(timespan=-1), dict(frame_buffer=np.zeros((2, 2, 4), dtype=np.uint8)),
                 dict(frame_buffer=np.zeros((70, 84, 4), dtype=np.float32))]
        for index, changes in enumerate(cases):
            self.output = Path(self.temp) / f"case{index}"
            self.frame = NS(frame_buffer=self.buffer, width=84, height=70, timespan=1000)
            self.frame.__dict__.update(changes)
            result = self.run_probe()
            self.assertEqual("withheld", result["status"])
            self.assertFalse((self.output / "frame.png").exists())
        self.assertEqual(len(cases), self.control.stop.call_count)
        self.assertEqual(len(cases), self.control.wait.call_count)

    def test_no_frame_timeout_cooperative_cleanup_and_closed_event(self):
        def no_frame(hwnd, on_frame, on_closed):
            self.time += 10
            return object(), self.control
        self.start.side_effect = no_frame
        result = self.run_probe(timeout=.01)
        self.assertEqual("withheld", result["status"])
        self.assertTrue(result["deadlineExceeded"])
        self.control.stop.assert_called_once()
        self.control.wait.assert_called_once()
        self.output = Path(self.temp) / "closed"
        self.time = 1
        def closed(hwnd, on_frame, on_closed):
            on_closed()
            return object(), self.control
        self.start.side_effect = closed
        self.assertEqual("capture-closed-before-frame", self.run_probe()["reason"])

    def test_target_or_geometry_change_and_cleanup_error_withhold(self):
        def changed(host, pid):
            self.select_calls += 1
            return dict(status="ready", target=dict(TARGET, hwnd=456 if self.select_calls == 1 else 999))
        result = self.run_probe(select=changed)
        self.assertEqual("final-target-identity-changed", result["reason"])
        self.output = Path(self.temp) / "cleanup"
        self.control.stop.side_effect = RuntimeError("stop failed")
        result = self.run_probe()
        self.assertEqual("capture-cleanup-failed", result["reason"])
        self.assertIn("stop failed", result["cleanupErrors"][0])
        self.assertFalse((self.output / "frame.png").exists())

    def test_foreground_loss_refuses_before_backend_and_version_adapter_exact_flags(self):
        self.geometry["foreground"] = False
        self.assertEqual("target-not-foreground", self.run_probe()["reason"])
        self.start.assert_not_called()
        module = NS(WindowsCapture=Mock(return_value=NS(start_free_threaded=Mock(return_value=self.control))))
        with patch.object(pilot.importlib.metadata, "version", return_value="2.0.1"), \
                patch.dict("sys.modules", windows_capture=module):
            capture, control = pilot._WindowsCaptureBackend().start(456, lambda *_: None, lambda: None)
        module.WindowsCapture.assert_called_once_with(window_hwnd=456, cursor_capture=False)
        self.assertIs(control, self.control)

    def test_client_geometry_change_after_callback_refuses_retained_pixels(self):
        original = self.deliver
        def moved(*args):
            result = original(*args)
            self.geometry["clientRect"][1] += 20
            return result
        self.start.side_effect = moved
        result = self.run_probe()
        self.assertEqual("withheld", result["status"])
        self.assertEqual("client-or-foreground-changed", result["reason"])
        self.assertFalse((self.output / "frame.png").exists())
        self.control.stop.assert_called_once()
        self.control.wait.assert_called_once()

    def test_png_encode_failure_or_size_limit_keeps_withheld_report_without_png(self):
        with patch.object(Image.Image, "save", side_effect=OSError("encoder failed")):
            result = self.run_probe()
        self.assertEqual("withheld", result["status"])
        self.assertIn("encoder failed", result["reason"])
        self.assertFalse((self.output / "frame.png").exists())
        self.assertEqual("withheld", json.loads((self.output / "probe.json").read_text())["status"])
        self.output = Path(self.temp) / "oversized"
        with patch.object(pilot, "MAX_PNG_BYTES", 16):
            result = self.run_probe()
        self.assertEqual("withheld", result["status"])
        self.assertIn("oversized", result["reason"])
        self.assertFalse((self.output / "frame.png").exists())
        self.assertTrue((self.output / "probe.json").is_file())


if __name__ == "__main__":
    unittest.main()
