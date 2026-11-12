import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
import time

from scripts import physical_waypoints as app


class TargetNameTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.key = "9223372045797034555"
        self.target = {"hostName": "AMD-DESKTOP", "processId": 17, "processStartUtcTicks": "99",
                       "executableSha256": "a" * 64, "hwnd": 42}
        self.observer = {"machine": "AMD-DESKTOP", "processId": 17, "processStartUtcTicks": "99",
                         "gameBuildSha256": "A" * 64, "unitKey": "123"}
        self.first = self.pose(.12, self.key, 0, "first-xyz.json")
        self.last = self.pose(.02, self.key, 1, "last-xyz.json")
        self.values = {"status": "available-candidate", "selfKey": "123", "targetKey": self.key,
                       "selectedBaseNameCandidate": "3rd Guard Soldier", "qualification": "cache-only raw candidate",
                       "startedAtUtc": self.stamp(.09), "sampledAtUtc": self.stamp(.06)}
        self.report = {"status": "complete", "workflow": "physical", "ownerHost": "AMD-DESKTOP",
                       "nativeRead": "target-name", "target": dict(self.target),
                       "nativeOutput": "name.json", "nativeSourceSha256": "b"*64, "nativeValues": self.values}
        self.adapter = SimpleNamespace(binding={"runtimeIdentity": self.observer}, target=self.target,
                                       read_target_name=Mock(return_value=self.report), read=Mock(return_value=self.last))

    def stamp(self, seconds_ago):
        return (self.now - timedelta(seconds=seconds_ago)).isoformat()

    def pose(self, age, key, x, source):
        return app.Snapshot(app.Position(0, 5, 1), 0, time.monotonic()-age, source,
                            {"status": "candidate", "targetKey": key, "sampledAtUtc": self.stamp(age),
                             "positionXYZCandidate": {"x": x, "y": 5, "z": 2}})

    def test_bracketed_name_keeps_separate_position_and_name_provenance(self):
        pose, _, name = app._read_target_waypoint(self.adapter, self.first)
        self.assertIs(pose, self.last)
        self.assertEqual("last-xyz.json", pose.source)
        self.assertEqual(("3rd Guard Soldier", "name.json", "b"*64, self.key, "123", self.target),
                         tuple(name[k] for k in ("text", "source", "sourceSha256", "targetKey", "observerKey",
                                                 "processIdentity")))
        self.assertEqual(self.values["qualification"], name["qualification"])
        self.assertEqual(self.values["sampledAtUtc"], name["sampledAtUtc"])
        self.adapter.read.assert_called_once_with(include_target=True)

    def test_invalid_name_preserves_fresh_generic_waypoint(self):
        for field, bad in (("selfKey", "555"), ("targetKey", "001"), ("status", "unavailable"),
                           ("sampledAtUtc", self.stamp(.01)), ("startedAtUtc", self.stamp(9)),
                           ("sampledAtUtc", "2026-01-01T12:00:00"), ("selectedBaseNameCandidate", "Guard\n1"),
                           ("selectedBaseNameCandidate", "x"*81)):
            with self.subTest(field=field), patch.dict(self.values, {field: bad}):
                pose, waypoint, name = app._read_target_waypoint(self.adapter, self.first)
                self.assertEqual(("Selected target", 1, 2), waypoint)
                self.assertIs(self.last, pose)
                self.assertIsNone(name)
        for field, bad in (("nativeSourceSha256", "truncated"), ("workflow", "archival"),
                           ("ownerHost", "LEGION"), ("target", {**self.target, "processStartUtcTicks": "98"})):
            with self.subTest(field=field), patch.dict(self.report, {field: bad}):
                self.assertIsNone(app._read_target_waypoint(self.adapter, self.first)[2])
        self.adapter.read_target_name.side_effect = OSError("unavailable")
        self.assertIs(self.last, app._read_target_waypoint(self.adapter, self.first)[0])

    def test_changed_target_refuses_entire_point_even_if_name_lookup_failed(self):
        self.adapter.read_target_name.side_effect = OSError("not cached")
        self.adapter.read.return_value = self.pose(.01, "777", 8, "other-xyz.json")
        with self.assertRaisesRegex(app.WaypointError, "changed"):
            app._read_target_waypoint(self.adapter, self.first)

    def test_adapter_uses_explicit_read_only_name_command(self):
        selection = {"target": self.target}
        with patch.object(app.physical_rift, "read_native", return_value=self.report) as read:
            self.assertIs(self.report, app.PhysicalAdapter.read_target_name(SimpleNamespace(selection=selection)))
            read.assert_called_once_with(selection, "target-name")


if __name__ == "__main__":
    unittest.main()
