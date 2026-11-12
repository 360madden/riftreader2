"""Passive batches retain the actual native row cadence and reject bad evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.waypoint_observation import observe_batch
from scripts.physical_waypoints import WaypointError
from tests.test_physical_facing import report


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "native.json"
        self.source = report()
        now = datetime.now(timezone.utc)
        for i, row in enumerate(self.source["observations"]):
            begin = now - timedelta(milliseconds=400 - i * 100)
            row["startedAtUtc"] = begin.isoformat()
            row["completedAtUtc"] = (begin + timedelta(milliseconds=10)).isoformat()
            row["entityPositionCandidate"] = {"x": float(i), "y": 2., "z": 3.}
            row["entityPositionRawBits"] = [struct.unpack("<I", struct.pack("<f", v))[0]
                                              for v in row["entityPositionCandidate"].values()]
        ident = self.source["identity"]
        self.adapter = SimpleNamespace(selection={"status": "ready"}, target=deepcopy(ident),
                                       unit_key=self.source["observation"]["playerKeyDecimal"])

    def read(self):
        self.path.write_text(json.dumps(self.source), encoding="utf-8")
        with patch("scripts.waypoint_observation.physical_rift.read_native",
                   return_value={"status": "complete", "nativeOutput": str(self.path)}) as native:
            result = observe_batch(self.adapter, samples=3)
            native.assert_called_once_with(self.adapter.selection, "facing", samples=3,
                                            interval_ms=100, include_target=False)
            return result

    def test_every_row_and_actual_cadence_are_preserved(self):
        poses = self.read()
        self.assertEqual([0., 1., 2.], [p.position.x for p in poses])
        self.assertAlmostEqual(.1, poses[1].acquired - poses[0].acquired, places=5)
        self.assertEqual([str(self.path)] * 3, [p.source for p in poses])

    def test_invalid_middle_row_cannot_hide_behind_valid_final_row(self):
        self.source["observations"][1]["entityPositionRawBits"][0] = 0
        with self.assertRaises(WaypointError):
            self.read()

    def test_stale_middle_row_order_owner_and_identity_are_refused(self):
        original = deepcopy(self.source)
        target, unit_key = deepcopy(self.adapter.target), self.adapter.unit_key
        mutations = [
            lambda: self.source["observations"][0].update(startedAtUtc="2020-01-01T00:00:00Z",
                                                          completedAtUtc="2020-01-01T00:00:01Z"),
            lambda: self.source["observations"][1].update(startedAtUtc=self.source["observations"][0]["startedAtUtc"]),
            lambda: self.source["observations"][1].update(playerEntityDecimal="123"),
            lambda: self.adapter.target.update(processId=999999),
            lambda: setattr(self.adapter, "unit_key", "999"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.source = deepcopy(original)
                self.adapter.target, self.adapter.unit_key = deepcopy(target), unit_key
                mutate()
                with self.assertRaises(WaypointError):
                    self.read()

    def test_incomplete_burst_and_changed_build_are_refused(self):
        self.source["observations"].pop(0)
        with self.assertRaises(WaypointError):
            self.read()
        self.adapter.target["executableSha256"] = "0" * 64
        with self.assertRaises(WaypointError):
            self.read()

    def test_missing_entity_source_is_refused(self):
        del self.source["observations"][0]["entityPositionCandidate"]
        del self.source["observations"][0]["entityPositionRawBits"]
        with self.assertRaises(WaypointError):
            self.read()

    def test_invalid_sampling_never_calls_native(self):
        with patch("scripts.waypoint_observation.physical_rift.read_native") as native:
            for kwargs in ({"samples": 31}, {"samples": True}, {"interval_ms": -1}):
                with self.assertRaises(WaypointError):
                    observe_batch(self.adapter, **kwargs)
            native.assert_not_called()

    def test_native_failure_is_not_cached(self):
        with patch("scripts.waypoint_observation.physical_rift.read_native",
                   return_value={"status": "blocked", "reason": "process-exited"}):
            with self.assertRaisesRegex(WaypointError, "process-exited"):
                observe_batch(self.adapter)


if __name__ == "__main__":
    unittest.main()
