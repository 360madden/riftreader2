"""Withdrawn Tk save-view tests with fake backend and no native access."""
import json
import os
from pathlib import Path, PureWindowsPath
import sys
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_view_bundle import saved_scene_asset
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class ViewWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def prepare(self, document=None, *, view_native_reader=None):
        runtime_identity = dict(fixture.TEST_IDENTITY, processId=123, processStartUtcTicks="99")
        self.document = document or {
            "waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11],
            "recording": {"version": 1, "complete": True,
                          "identity": {"mode": "recorded", "runtimeIdentity": runtime_identity},
                          "sources": ["retained-native-route.json"],
                          "firstObservedAtUtc": "2026-11-13T12:00:00Z",
                          "lastObservedAtUtc": "2026-11-13T12:00:01Z"}}
        path = self.path / "route.json"
        path.write_text(json.dumps(self.document), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.target = {"processId": 123, "processStartUtcTicks": "99", "hwnd": 100}
        self.adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123, target=self.target,
                                       input_receipt_path=self.path / "unused.jsonl")
        self.launch(self.adapter, path, view_native_reader=view_native_reader)

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if (all(not thread.is_alive() for thread in self.threads)
                    and str(self.button("Refresh")["state"]) != "disabled"):
                return
            time.sleep(.01)
        self.fail("view worker did not settle")

    def labels(self):
        return [str(self.roots[0].getvar(str(w.cget("textvariable")))) for w in self.widgets(self.roots[0])
                if isinstance(w, fixture.ttk.Label) and w.cget("textvariable")]

    def test_save_view_captures_snapshot_and_opens_only_on_click(self):
        published = self.path / "RiftReader2.Live.exe"
        self.prepare(view_native_reader=published)
        entered, release = threading.Event(), threading.Event()
        def save(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("test did not release backend")
            return {"status": "saved-route-view-candidate", "image": str(self.path / "view.png"),
                    "inputSent": False, "focusChanged": False,
                    "rerun": {"status": "unavailable", "reason": "not installed"}}
        backend = Mock(side_effect=save)
        fake_module = SimpleNamespace(save_route_view=backend)
        with patch.dict(sys.modules, {"scripts.save_physical_route_view": fake_module}), \
             patch.object(os, "startfile") as open_file:
            self.button("Save view").invoke()
            self.assertTrue(entered.wait(2))
            self.assertEqual("disabled", str(self.button("Save view")["state"]))
            self.assertEqual("disabled", str(self.button("Open view")["state"]))
            option = next(w for w in self.widgets(self.roots[0]) if isinstance(w, fixture.ttk.Checkbutton)
                          and str(w["text"]) == "Bring RIFT forward for capture")
            self.assertEqual("disabled", str(option["state"]))
            release.set()
            self.wait_idle()
            open_file.assert_not_called()
            self.assertNotEqual("disabled", str(self.button("Open view")["state"]))
            self.button("Open view").invoke()
            open_file.assert_called_once_with(str(self.path / "view.png"))
        args, kwargs = backend.call_args
        self.assertEqual(("AMD-DESKTOP", 123, self.document), args[:3])
        self.assertTrue(str(args[3]).startswith(str(self.path / "artifacts" / "waypoint-view-")))
        self.assertEqual(self.target, kwargs["expected_target"])
        self.assertIsNot(self.target, kwargs["expected_target"])
        self.assertTrue(kwargs["export_rerun"])
        self.assertFalse(kwargs.get("include_units", False))
        self.assertEqual("wgc", kwargs["capture_backend"])
        self.assertEqual(kwargs["native_reader"], published)
        self.assertTrue(any("Rerun unavailable: not installed" in value for value in self.labels()))

    def test_capture_is_disabled_when_route_has_estimated_heights_only(self):
        self.prepare({"waypoints": [["A", 0, 0], ["B", 1, 0]],
                      "heights": [None, None], "pointMeasurements": [None, None]})
        root = self.roots[0]
        notebook = next(w for w in self.widgets(root) if isinstance(w, fixture.ttk.Notebook))
        scene = next(tab for tab in notebook.tabs() if notebook.tab(tab, "text") == "Scene & beacons")
        notebook.select(scene)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            root.update()
            if self.button("Save view").instate(["disabled"]):
                break
            time.sleep(.01)
        self.assertTrue(self.button("Save view").instate(["disabled"]))
        self.assertTrue(any("Capture needs measured XYZ for all points (0/2)" in value
                            for value in self.labels()))

    def test_nearby_units_are_requested_only_on_save_and_unavailable_keeps_view(self):
        self.prepare()
        backend = Mock(return_value={"status": "saved-route-view-candidate", "image": str(self.path / "view.png"),
                                     "inputSent": False, "focusChanged": False,
                                     "rerun": {"status": "saved", "path": "scene.rrd"},
                                     "unitSample": {"status": "unavailable", "reason": "sample expired"}})
        window = self.roots[0]
        option = next(w for w in self.widgets(window) if isinstance(w, fixture.ttk.Checkbutton)
                      and str(w["text"]) == "Nearby units in 3D")
        self.assertFalse(option.instate(["selected"]))
        with patch.dict(sys.modules, {"scripts.save_physical_route_view": SimpleNamespace(save_route_view=backend)}):
            option.invoke()
            backend.assert_not_called()
            self.button("Save view").invoke()
            self.assertTrue(option.instate(["disabled"]))
            window.setvar(str(option.cget("variable")), False)
            self.wait_idle()
        self.assertIs(backend.call_args.kwargs["include_units"], True)
        self.assertFalse(option.instate(["disabled"]))
        self.assertFalse(self.button("Open view").instate(["disabled"]))
        self.assertFalse(self.button("Open 3D view").instate(["disabled"]))
        self.assertTrue(any("View saved" in value and "Nearby units unavailable (sample expired)" in value
                            for value in self.labels()))

    def test_explicit_focus_capture_failure_keeps_prior_view(self):
        self.prepare()
        backend = Mock(side_effect=[{"status": "saved-route-view-candidate", "image": str(self.path / "old.png"),
                                     "inputSent": False, "focusChanged": False, "rerun": {"status": "saved"}},
                                    {"status": "saved-route-view-candidate", "image": str(self.path / "focused.png"),
                                     "inputSent": False, "focusChanged": True, "rerun": {"status": "saved"}},
                                    {"status": "blocked", "reason": "capture unavailable", "inputSent": False,
                                     "focusChanged": True}])
        with patch.dict(sys.modules, {"scripts.save_physical_route_view": SimpleNamespace(save_route_view=backend)}), \
             patch.object(os, "startfile") as open_file:
            self.button("Save view").invoke()
            self.wait_idle()
            option = next(w for w in self.widgets(self.roots[0]) if isinstance(w, fixture.ttk.Checkbutton)
                          and str(w["text"]) == "Bring RIFT forward for capture")
            option.invoke()
            self.button("Save view").invoke()
            self.wait_idle()
            self.button("Save view").invoke()
            self.wait_idle()
            self.assertNotEqual("disabled", str(self.button("Open view")["state"]))
            self.button("Open view").invoke()
            open_file.assert_called_once_with(str(self.path / "focused.png"))
        self.assertEqual(["wgc", "desktop", "desktop"], [call.kwargs["capture_backend"] for call in backend.call_args_list])
        self.assertTrue(any("capture unavailable" in value for value in self.labels()))

    def test_failed_capture_keeps_prior_working_image_and_3d_view(self):
        self.prepare()
        prior_image = self.path / "prior.png"
        prior_rerun = self.path / "prior.rrd"
        prior_image.write_bytes(b"png")
        prior_rerun.write_bytes(b"rrd")
        backend = Mock(side_effect=[
            {"status": "saved-route-view-candidate", "image": str(prior_image),
             "inputSent": False, "focusChanged": False,
             "rerun": {"status": "saved", "path": str(prior_rerun)}},
            {"status": "blocked", "reason": "capture failed", "inputSent": False,
             "focusChanged": False},
        ])
        launched = Mock(return_value=SimpleNamespace(poll=Mock(return_value=None)))
        with patch.dict(sys.modules, {"scripts.save_physical_route_view": SimpleNamespace(
                save_route_view=backend, launch_saved_rerun=launched)}), \
             patch.object(os, "startfile") as open_file:
            self.button("Save view").invoke()
            self.wait_idle()
            self.button("Save view").invoke()
            self.wait_idle()
            self.assertFalse(self.button("Open view").instate(["disabled"]))
            self.assertFalse(self.button("Open 3D view").instate(["disabled"]))
            self.assertTrue(any("capture failed" in value for value in self.labels()))
            self.button("Open view").invoke()
            self.button("Open 3D view").invoke()
        open_file.assert_called_once_with(str(prior_image))
        launched.assert_called_once_with(str(prior_rerun))

    def test_open_saved_manifest_loads_assets_without_opening_them(self):
        self.prepare()
        image = self.path / "saved.png"
        rerun = self.path / "saved.rrd"
        image.write_bytes(b"png")
        rerun.write_bytes(b"rrd")
        manifest = self.path / "saved-view.json"
        manifest.write_text(json.dumps({
            "status": "saved-route-view-candidate", "image": str(image),
            "rerun": {"status": "saved", "path": str(rerun)}}), encoding="utf-8")
        launched = Mock(return_value=SimpleNamespace(poll=Mock(return_value=None)))
        with patch("tkinter.filedialog.askopenfilename", return_value=str(manifest)), \
             patch.object(os, "startfile") as open_file, \
             patch("scripts.save_physical_route_view.launch_saved_rerun", launched):
            self.button("Open saved…").invoke()
            open_file.assert_not_called()
            launched.assert_not_called()
            self.assertTrue(any("Saved scene loaded" in value for value in self.labels()))
            self.assertFalse(self.button("Open view").instate(["disabled"]))
            self.assertFalse(self.button("Open 3D view").instate(["disabled"]))
            self.button("Open view").invoke()
            self.button("Open 3D view").invoke()
        open_file.assert_called_once_with(str(image))
        launched.assert_called_once_with(str(rerun))


    def test_open_copied_legacy_scene_uses_the_copied_image_and_recording(self):
        self.prepare()
        original = PureWindowsPath(r"D:\RIFT evidence\Old view")
        copied = self.path / "Copied view"
        image = copied / "projection" / "waypoints.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"png")
        rerun = copied / "view.rrd"
        rerun.write_bytes(b"rrd")
        manifest = copied / "view.json"
        manifest.write_text(json.dumps({
            "status": "saved-route-view-candidate", "directory": str(original),
            "image": str(original / "projection" / "waypoints.png"),
            "rerun": {"status": "saved", "path": str(original / "view.rrd")},
        }), encoding="utf-8")
        launched = Mock(return_value=SimpleNamespace(poll=Mock(return_value=None)))
        with patch("tkinter.filedialog.askopenfilename", return_value=str(manifest)), \
             patch.object(os, "startfile") as open_file, \
             patch("scripts.save_physical_route_view.launch_saved_rerun", launched):
            self.button("Open saved…").invoke()
            open_file.assert_not_called()
            launched.assert_not_called()
            self.assertTrue(any("Saved scene loaded" in value for value in self.labels()))
            self.button("Open view").invoke()
            self.button("Open 3D view").invoke()
        open_file.assert_called_once_with(str(image))
        launched.assert_called_once_with(str(rerun))


class SavedSceneAssetTests(unittest.TestCase):
    def test_moved_legacy_manifest_uses_only_copies_of_internal_paths(self):
        with TemporaryDirectory() as temporary:
            copied = Path(temporary)
            manifest = {"directory": r"D:\RIFT evidence\Old view"}
            self.assertEqual(saved_scene_asset(copied, manifest, r"d:\rift evidence\old view\view.rrd"),
                             copied.resolve() / "view.rrd")
            self.assertIsNone(saved_scene_asset(copied, manifest, r"D:\RIFT evidence\Other view\view.rrd"))
            with self.assertRaisesRegex(ValueError, "view-bundle-path-outside-directory"):
                saved_scene_asset(copied, manifest, r"D:\RIFT evidence\Old view\..\view.rrd")


if __name__ == "__main__":
    unittest.main()
