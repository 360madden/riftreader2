"""Display-only feedback keeps native sample time, identity and session provenance."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import waypoint_beacon_pose as pose
from tests.test_physical_only_selection import IDENTITY


class BeaconPoseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "owned-session.json"
        self.now = datetime.now(timezone.utc)
        self.key = "239816685251645959"
        self.target = dict(IDENTITY, executablePath=r"C:\Games\rift_x64.exe")
        self.frame = dict(target=deepcopy(self.target), acquiredMonotonic=123.25,
            playerPose=dict(position=dict(x=7423.4, y=863.5, z=2937.6), bearing=44.4,
                            playerKey=self.key, sampledAtUtc=self.now.isoformat()))

    def read(self, **kwargs):
        kwargs.setdefault("now", self.now)
        return pose.read_pose(self.path, self.target, self.key, **kwargs)

    def test_fresh_round_trip_preserves_original_native_pose_and_time(self):
        written = pose.write_pose(self.path, self.frame, 1)
        read = self.read()
        self.assertEqual(read, written)
        self.assertEqual(read["position"], self.frame["playerPose"]["position"])
        self.assertEqual(read["bearing"], 44.4)
        self.assertEqual(read["sampledAtUtc"], self.frame["playerPose"]["sampledAtUtc"])
        self.assertEqual(read["acquiredMonotonic"], 123.25)
        self.assertEqual(read["sessionId"], self.path.stem)

    def test_repeated_sequence_never_refreshes_native_age_and_regression_refuses(self):
        pose.write_pose(self.path, self.frame, 5)
        first = self.read(last_sequence=5)
        second = self.read(now=self.now + timedelta(seconds=.5), last_sequence=5)
        self.assertEqual(first, second)
        os.utime(self.path, None)
        with self.assertRaisesRegex(ValueError, "stale-or-future"):
            self.read(now=self.now + timedelta(seconds=1.01), last_sequence=5)
        with self.assertRaisesRegex(ValueError, "sequence-regressed"):
            self.read(last_sequence=6)
        with self.assertRaisesRegex(ValueError, "stale-or-future"):
            self.read(now=self.now - timedelta(seconds=.2))

    def test_wrong_epoch_owner_session_or_source_never_becomes_a_pose(self):
        original = pose.write_pose(self.path, self.frame, 1)
        for change in (lambda d: d["target"].update(processId=99999),
                       lambda d: d["target"].update(processStartUtcTicks="42"),
                       lambda d: d["target"].update(hwnd=123),
                       lambda d: d["target"].update(executableSha256="f" * 64),
                       lambda d: d.update(playerKey="other"), lambda d: d.update(sessionId="old-session"),
                       lambda d: d.update(source="cached-ui"), lambda d: d.update(qualification="unverified")):
            bad = deepcopy(original)
            change(bad)
            self.path.write_text(json.dumps(bad), encoding="utf-8")
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.read()

    def test_malformed_future_unqualified_numeric_data_refuses(self):
        original = pose.write_pose(self.path, self.frame, 1)
        for change in (lambda d: d["position"].update(x=float("nan")),
                       lambda d: d["position"].update(y=True), lambda d: d.update(bearing=float("inf")),
                       lambda d: d.update(acquiredMonotonic=-1), lambda d: d.update(sequence=True),
                       lambda d: d.update(sampledAtUtc="2026-11-13T00:00:00"),
                       lambda d: d.update(extra="unexpected")):
            bad = deepcopy(original)
            change(bad)
            self.path.write_text(json.dumps(bad), encoding="utf-8")
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.read()
        for raw in ("{", " " * 9000):
            self.path.write_text(raw, encoding="utf-8")
            with self.assertRaises(ValueError):
                self.read()

    def test_unavailable_has_no_coordinates_and_cannot_relabel_last_good_sample(self):
        pose.write_pose(self.path, self.frame, 1)
        unavailable = pose.write_unavailable(self.path, self.target, self.key, 2, "target-not-foreground")
        self.assertNotIn("position", unavailable)
        self.assertNotIn("sampledAtUtc", unavailable)
        with self.assertRaisesRegex(ValueError, "target-not-foreground"):
            self.read(last_sequence=1)
        pose.write_pose(self.path, self.frame, 3)
        self.assertEqual(self.read(last_sequence=1)["sampledAtUtc"], self.frame["playerPose"]["sampledAtUtc"])


if __name__ == "__main__":
    unittest.main()
