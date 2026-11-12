"""Measured waypoint GUI provenance with fake poses and no native input."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class MeasurementWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def prepare(self, route=None):
        self.identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                         "unitKey": "123", "processId": 55, "processStartUtcTicks": "22"}
        pose = app.Snapshot(app.Position(1.1234564, 17.25, 2.25), 3, time.monotonic(), "native-source.json")
        self.adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123,
                                       binding={"runtimeIdentity": self.identity},
                                       input_receipt_path=self.path / "unused")
        self.launch(self.adapter, route)
        self.window = self.roots[0]
        self.table = next(w for w in self.widgets(self.window) if isinstance(w, fixture.ttk.Treeview))
        self.entries = [w for w in self.widgets(self.window) if isinstance(w, fixture.ttk.Entry)]

    def wait_rows(self, count):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.window.update()
            if len(self.table.get_children()) == count and str(self.button("Refresh")["state"]) != "disabled":
                return
            time.sleep(.01)
        self.fail("fake read did not settle")

    def edit(self, name, x, z):
        for widget, value in zip(self.entries, (name, x, z)):
            widget.delete(0, "end")
            widget.insert(0, value)

    def save_copy(self):
        output = self.path / "saved.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(output)):
            self.button("Save As").invoke()
        return json.loads(output.read_text(encoding="utf-8"))

    def test_save_current_measured_and_manual_point_unknown_survive_save(self):
        self.prepare()
        self.button("Save Current").invoke()
        self.wait_rows(1)
        self.edit("Manual", "4", "5")
        self.button("Add X / Z").invoke()
        self.window.update()
        result = self.save_copy()
        self.assertEqual([17.25, None], result["heights"])
        self.assertEqual("native-player-position", result["pointMeasurements"][0]["kind"])
        self.assertEqual("native-source.json", result["pointMeasurements"][0]["source"])
        self.assertEqual(self.identity, result["pointMeasurements"][0]["identity"]["runtimeIdentity"])
        self.assertIn("+00:00", result["pointMeasurements"][0]["observedAtUtc"])
        self.assertEqual(1.1234564, result["pointMeasurements"][0]["position"]["x"])
        self.assertIsNone(result["pointMeasurements"][1])
        self.assertNotIn("recording", result)
        values = [str(self.window.getvar(str(w.cget("textvariable")))) for w in self.widgets(self.window)
                  if isinstance(w, fixture.ttk.Label) and w.cget("textvariable")]
        self.assertTrue(any("3D: measured heights 1 / 2" in value for value in values), values)

    def test_coordinate_change_clears_only_that_receipt_and_undo_restores(self):
        self.prepare()
        self.button("Save Current").invoke(); self.wait_rows(1)
        item = self.table.get_children()[0]
        self.table.selection_set(item); self.window.update()
        self.edit("Renamed", "1.123456", "2.25")
        self.button("Update Selected").invoke()
        renamed = self.save_copy()
        self.assertEqual([17.25], renamed["heights"])
        self.edit("Renamed", "1.5", "2.25")
        self.button("Update Selected").invoke()
        changed = self.save_copy()
        self.assertNotIn("pointMeasurements", changed)
        self.button("Undo").invoke()
        values = [str(self.window.getvar(str(w.cget("textvariable")))) for w in self.widgets(self.window)
                  if isinstance(w, fixture.ttk.Label) and w.cget("textvariable")]
        self.assertTrue(any("3D: measured heights 1 / 1" in value for value in values), values)
        restored = self.save_copy()
        self.assertEqual([17.25], restored["heights"])
        self.assertEqual("native-source.json", restored["pointMeasurements"][0]["source"])

    def test_reorder_and_coordinate_edit_keep_other_point_receipts(self):
        self.prepare()
        self.button("Save Current").invoke(); self.wait_rows(1)
        second_pose = app.Snapshot(app.Position(4, 23, 5), 3, time.monotonic(), "second-source.json")
        self.adapter.read = lambda **kwargs: second_pose
        self.button("Save Current").invoke(); self.wait_rows(2)
        first, second = self.table.get_children()
        self.table.selection_set(second); self.window.update()
        self.button("Up").invoke()
        reordered = self.save_copy()
        self.assertEqual([23, 17.25], reordered["heights"])
        self.assertEqual(["second-source.json", "native-source.json"],
                         [receipt["source"] for receipt in reordered["pointMeasurements"]])
        self.table.selection_set(first); self.window.update()
        name = self.table.item(first, "values")[0]
        self.edit(name, "1.5", "2.25")
        self.button("Update Selected").invoke()
        changed = self.save_copy()
        self.assertEqual([23, None], changed["heights"])
        self.assertEqual("second-source.json", changed["pointMeasurements"][0]["source"])
        self.assertIsNone(changed["pointMeasurements"][1])

    def test_recording_roundtrip_and_reorder_preserves_point_provenance(self):
        identity = {"runtimeIdentity": {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                                       "unitKey": "123", "processId": 55, "processStartUtcTicks": "22"}}
        document = {"waypoints": [["A", 1, 2], ["B", 4, 5]], "heights": [17.25, 23],
                    "recording": {"complete": True, "version": 1, "identity": identity,
                                  "sources": ["old-native.json"], "firstObservedAtUtc": "2026-11-12T10:00:00Z",
                                  "lastObservedAtUtc": "2026-11-12T10:00:05Z"}}
        path = self.path / "recorded.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        self.prepare(path)
        self.assertEqual(document, self.save_copy())
        self.table.selection_set(self.table.get_children()[1]); self.window.update()
        self.button("Up").invoke()
        result = self.save_copy()
        self.assertNotIn("recording", result)
        self.assertEqual([23, 17.25], result["heights"])
        self.assertEqual(["recorded-route-point", "recorded-route-point"],
                         [receipt["kind"] for receipt in result["pointMeasurements"]])
        self.assertEqual("route-observation-interval", result["pointMeasurements"][0]["sourceTimeKind"])

    def test_add_target_saves_own_xyz_and_lossless_target_identity(self):
        self.prepare()
        key = "18446744073709551614"
        target = {"status": "candidate", "targetKey": key,
                  "positionXYZCandidate": {"x": 3.125, "y": 17.75, "z": 4.5},
                  "sampledAtUtc": datetime.now(timezone.utc).isoformat()}
        pose = app.Snapshot(app.Position(1, 17.25, 2), 3, time.monotonic(), "target-native.json", target)
        self.adapter.read = lambda **kwargs: pose
        self.button("Add Target").invoke(); self.wait_rows(1)
        result = self.save_copy()
        self.assertEqual([["Selected target", 3.125, 4.5]], result["waypoints"])
        self.assertEqual([17.75], result["heights"])
        receipt = result["pointMeasurements"][0]
        self.assertEqual("native-selected-target-position", receipt["kind"])
        self.assertEqual(key, receipt["targetKey"])
        self.assertEqual(self.identity, receipt["identity"]["runtimeIdentity"])
        self.assertEqual(target["positionXYZCandidate"], receipt["position"])
        self.assertEqual("target-native.json", receipt["source"])
        self.assertNotIn("recording", result)

    def test_unavailable_target_is_not_added_and_missing_key_stays_unmeasured(self):
        self.prepare()
        unavailable = app.Snapshot(app.Position(1, 17.25, 2), 3, time.monotonic(), "target-native.json", None)
        self.adapter.read = lambda **kwargs: unavailable
        self.button("Add Target").invoke(); self.wait_rows(0)
        self.assertEqual(0, len(self.table.get_children()))
        target = {"status": "candidate", "positionXYZCandidate": {"x": 3, "y": 17.5, "z": 4},
                  "sampledAtUtc": datetime.now(timezone.utc).isoformat()}
        pose = app.Snapshot(app.Position(1, 17.25, 2), 3, time.monotonic(), "target-native.json", target)
        self.adapter.read = lambda **kwargs: pose
        self.button("Add Target").invoke(); self.wait_rows(1)
        result = self.save_copy()
        self.assertNotIn("heights", result)
        self.assertNotIn("pointMeasurements", result)

    def test_named_target_saves_separate_lookup_and_latest_xyz_receipts(self):
        self.prepare()
        now = datetime.now(timezone.utc)
        stamp = lambda age: (now - timedelta(seconds=age)).isoformat()
        key = "9223372045797034555"
        self.adapter.pid = self.identity["processId"]
        self.adapter.target = {"processId": self.adapter.pid, "hostName": self.identity["machine"],
                               "processStartUtcTicks": self.identity["processStartUtcTicks"],
                               "executableSha256": self.identity["gameBuildSha256"], "hwnd": 11}
        def pose(x, age):
            return app.Snapshot(app.Position(1, 17.25, 2), 3, time.monotonic()-age, f"target-{x}.json",
                                {"status": "candidate", "targetKey": key, "sampledAtUtc": stamp(age),
                                 "positionXYZCandidate": {"x": x, "y": 17.75, "z": 4.5}})
        observations = iter([pose(1, .18), pose(2, .03)])
        self.adapter.read = lambda **kwargs: next(observations)
        self.adapter.read_target_name = lambda: {
            "status": "complete", "workflow": "physical", "ownerHost": "AMD-DESKTOP",
            "nativeRead": "target-name", "target": self.adapter.target,
            "nativeOutput": "target-name.json", "nativeSourceSha256": "b"*64,
            "nativeValues": {"status": "available-candidate", "selfKey": self.identity["unitKey"], "targetKey": key,
                             "selectedBaseNameCandidate": "3rd Guard Soldier", "qualification": "cache-only raw candidate",
                             "startedAtUtc": stamp(.14), "sampledAtUtc": stamp(.08)}}
        self.button("Add Target").invoke()
        self.wait_rows(1)
        saved = self.save_copy()
        self.assertEqual([["3rd Guard Soldier", 2, 4.5]], saved["waypoints"])
        self.assertEqual([17.75], saved["heights"])
        receipt, = saved["pointMeasurements"]
        self.assertEqual(("target-2.json", stamp(.03), key), (receipt["source"], receipt["observedAtUtc"], receipt["targetKey"]))
        candidate = receipt["nameCandidate"]
        self.assertEqual(("target-name.json", stamp(.08), key, "b"*64),
                         (candidate["source"], candidate["sampledAtUtc"], candidate["targetKey"], candidate["sourceSha256"]))


if __name__ == "__main__":
    unittest.main()
