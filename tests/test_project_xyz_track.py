"""Synthetic-only offline native XYZ track projection tests."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import project_xyz_track as p


def fixture():
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-position-candidate-samples/1",
        "qualification": p.QUALIFICATION, "sourceBuildSha256": p.GAME_SHA,
        "identity": {"processId": 123, "processStartUtcTicks": 456, "executableSha256": p.GAME_SHA},
        "requestedSamples": 2, "completedSamples": 2, "status": "complete",
        "observations": [
            {"index": 1, "startedAtUtc": "2026-11-08T00:00:00Z",
             "completedAtUtc": "2026-11-08T00:00:00.100Z",
             "monotonicStartMilliseconds": 0, "monotonicEndMilliseconds": 100,
             "x": 0, "y": 0, "z": 0},
            {"index": 2, "startedAtUtc": "2026-11-08T00:00:02Z",
             "completedAtUtc": "2026-11-08T00:00:02.100Z",
             "monotonicStartMilliseconds": 2000, "monotonicEndMilliseconds": 2100,
             "x": 3, "y": 4, "z": 4},
        ],
    }


def project(report, **kwargs):
    return p.project(report, max_gap_seconds=kwargs.get("gap", 5), max_speed_3d=kwargs.get("speed", 10))


class ProjectTrackTests(unittest.TestCase):
    def test_project_ordered_values_and_disclosed_unknowns(self):
        result = project(fixture())
        self.assertEqual(result["freshness"], "unavailable-offline")
        self.assertEqual(result["zoneBoundaries"], "undetectable-in-source")
        self.assertEqual(result["unitIdentity"], "unavailable-in-source")
        self.assertEqual(result["coordinateUnits"], "unverified")
        rows = result["observations"]
        self.assertEqual(rows[0]["reduction"]["reason"], "first-sample")
        self.assertEqual(rows[1]["elapsedStartMilliseconds"], 2000)
        self.assertEqual(rows[1]["reduction"]["displacement"], (3, 4, 4))
        self.assertEqual(rows[1]["reduction"]["planar_distance"], 5)
        self.assertEqual(rows[1]["reduction"]["velocity"], (1.5, 2, 2))
        self.assertNotIn("fresh", rows[1]["reduction"])

    def test_sampled_unit_keys_preserve_uint64_as_strings(self):
        for key in (1, 2**63 + 42, 2**64 - 1):
            r = fixture()
            for row in r["observations"]:
                row.update(unitKey=str(key), unitIdCandidate=f"u{key:016X}",
                           ownerIdentityStatus="player-component-chain-anchored")
            result = project(r)
            self.assertEqual(result["unitIdentity"], "same-sampled-unit-key-candidate")
            self.assertEqual(result["sampledUnitKey"], str(key))
            self.assertEqual(result["sampledUnitIdCandidate"], f"u{key:016X}")
            self.assertEqual(result["freshness"], "unavailable-offline")
            self.assertIn("not proof of uninterrupted", result["limitations"][0])

    def test_reject_partial_mixed_bad_and_changed_unit_keys(self):
        def tagged():
            r = fixture()
            for row in r["observations"]:
                row.update(unitKey="1", unitIdCandidate="u0000000000000001",
                           ownerIdentityStatus="player-component-chain-anchored")
            return r
        mutations = (
            lambda r: r["observations"][1].pop("unitKey"),
            lambda r: r["observations"][1].clear(),
            lambda r: r["observations"][1].update(unitKey="0"),
            lambda r: r["observations"][1].update(unitKey="01"),
            lambda r: r["observations"][1].update(unitKey=1),
            lambda r: r["observations"][1].update(unitKey=str(2**64)),
            lambda r: r["observations"][1].update(unitIdCandidate="u000000000000000a"),
            lambda r: r["observations"][1].update(unitIdCandidate="u0000000000000002"),
            lambda r: r["observations"][1].update(ownerIdentityStatus="unavailable"),
            lambda r: r["observations"][1].update(unitKey="2", unitIdCandidate="u0000000000000002"),
            lambda r: [r["observations"][1].pop(k) for k in
                       ("unitKey", "unitIdCandidate", "ownerIdentityStatus")],
        )
        for mutate in mutations:
            r = tagged()
            mutate(r)
            with self.subTest(row=r["observations"][1]), self.assertRaises(ValueError):
                project(r)

    def test_axis_travel_bearing_and_no_planar_movement(self):
        for x, y, z, expected in ((1, 0, 0, 0), (0, 0, 1, 90),
                                  (-1, 0, 0, 180), (0, 0, -1, 270),
                                  (0, 0, 0, None), (0, 4, 0, None)):
            r = fixture()
            r["observations"][1].update(x=x, y=y, z=z)
            points = project(r)["observations"]
            self.assertIsNone(points[0]["reduction"]["coordinateAxisTravelBearingDegrees"])
            self.assertEqual(points[1]["reduction"]["coordinateAxisTravelBearingDegrees"], expected)
        self.assertIn("not body yaw", project(fixture())["limitations"][-1])

    def test_gap_and_speed_boundaries_withhold_values(self):
        for kwargs, reason in (({"gap": 1}, "sample-gap"), ({"speed": 1}, "teleport-or-speed-limit")):
            out = project(fixture(), **kwargs)["observations"][1]["reduction"]
            self.assertEqual(out["reason"], reason)
            self.assertIsNone(out["displacement"])
            self.assertIsNone(out["coordinateAxisTravelBearingDegrees"])

    def test_bad_contract_identity_and_sequence(self):
        for mutate in (
            lambda r: r.update(contractVersion="other"),
            lambda r: r.update(schemaVersion=True),
            lambda r: r.update(sourceBuildSha256="B"*64),
            lambda r: r["identity"].update(processId=True),
            lambda r: r["identity"].update(processStartUtcTicks=0),
            lambda r: r["identity"].update(executableSha256="B"*64),
            lambda r: r["observations"][1].update(index=1),
            lambda r: r["observations"].pop(),
        ):
            r = fixture()
            mutate(r)
            with self.assertRaises(ValueError):
                project(r)

    def test_invalid_times_values_thresholds(self):
        for mutate in (
            lambda r: r["observations"][1].update(monotonicStartMilliseconds=50),
            lambda r: r["observations"][1].update(startedAtUtc="2026-11-07T19:00:02-05:00"),
            lambda r: r["observations"][1].update(x=2**-127),
            lambda r: r["observations"][1].update(x=float("nan")),
        ):
            r = fixture()
            mutate(r)
            with self.assertRaises(ValueError):
                project(r)
        with self.assertRaises(ValueError):
            project(fixture(), gap=0)

    def test_cli_pins_source_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(p.main([str(path), "--max-gap-seconds", "5", "--max-speed-3d", "10"]), 0)
            self.assertEqual(len(json.loads(out.getvalue())["sourceSha256"]), 64)
            path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(p.main([str(path), "--max-gap-seconds", "5", "--max-speed-3d", "10"]), 2)


if __name__ == "__main__":
    unittest.main()
