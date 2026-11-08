"""Synthetic offline segment summaries, with no game access."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import summarize_native_xyz_track as s
from tests.test_project_xyz_track import fixture


def summarize(report, gap=5, speed=10):
    return s.summarize(report, max_gap_seconds=gap, max_speed_3d=speed)


class SegmentSummaryTests(unittest.TestCase):
    def test_candidate_path_and_identity_are_preserved(self):
        r = fixture()
        r["identity"]["processStartUtcTicks"] = 639296903905448486
        for row in r["observations"]:
            row.update(unitKey="1", unitIdCandidate="u0000000000000001",
                       ownerIdentityStatus="player-component-chain-anchored")
        out = summarize(r)
        segment = out["segments"][0]
        self.assertEqual(segment["pathPlanar"], 5)
        self.assertAlmostEqual(segment["path3d"], 41**.5)
        self.assertEqual(segment["netDisplacement"], {"x":3,"y":4,"z":4})
        self.assertEqual(segment["zeroDeltaPairCount"], 0)
        self.assertEqual(segment["nonzeroDeltaPairCount"], 1)
        self.assertEqual(segment["coordinateDeltaStatus"], "candidate-nonzero-within-segment")
        self.assertEqual(out["observedCoordinateDeltaStatus"], "candidate-nonzero-within-admitted-segments")
        self.assertEqual(out["sampledUnitKey"], "1")
        self.assertEqual(out["processIdentity"]["processStartUtcTicks"], "639296903905448486")
        self.assertEqual(out["freshness"], "unavailable-offline")
        self.assertEqual(out["zoneBoundaries"], "undetectable-in-source")

    def test_boundaries_never_become_total_or_zero(self):
        for kwargs in ({"gap":1}, {"speed":1}):
            out = summarize(fixture(), **kwargs)
            self.assertEqual(len(out["segments"]), 2)
            self.assertIsNone(out["overallPath3d"])
            for seg in out["segments"]:
                self.assertIsNone(seg["path3d"])
                self.assertNotIn("_3d", seg)
                self.assertEqual(seg["distanceStatus"], "unavailable-no-accepted-pair")
                self.assertEqual(seg["coordinateDeltaStatus"], "unavailable-no-accepted-pair")
            self.assertEqual(out["observedCoordinateDeltaStatus"], "unavailable-no-accepted-pairs")

    def test_stationary_is_zero_only_with_two_valid_samples(self):
        report = fixture()
        report["observations"][1].update(x=0,y=0,z=0)
        out = summarize(report)
        self.assertEqual(out["overallPath3d"], 0)
        self.assertEqual(out["segments"][0]["zeroDeltaPairCount"], 1)
        self.assertEqual(out["segments"][0]["nonzeroDeltaPairCount"], 0)
        self.assertEqual(out["segments"][0]["coordinateDeltaStatus"], "candidate-equal-within-segment")
        self.assertEqual(out["observedCoordinateDeltaStatus"], "candidate-equal-within-admitted-segments")
        report["observations"].pop()
        report["requestedSamples"] = report["completedSamples"] = 1
        out = summarize(report)
        self.assertIsNone(out["overallPath3d"])
        self.assertEqual(out["overallPathStatus"], "unavailable-boundary-or-single-sample")
        self.assertEqual(out["observedCoordinateDeltaStatus"], "unavailable-no-accepted-pairs")

    def test_round_trip_with_zero_net_retains_nonzero_candidate_deltas(self):
        report = fixture()
        report["requestedSamples"] = report["completedSamples"] = 3
        report["observations"].append({
            "index": 3, "startedAtUtc": "2026-11-08T00:00:04Z",
            "completedAtUtc": "2026-11-08T00:00:04.100Z",
            "monotonicStartMilliseconds": 4000, "monotonicEndMilliseconds": 4100,
            "x": 0, "y": 0, "z": 0,
        })
        out = summarize(report)
        segment = out["segments"][0]
        self.assertEqual(segment["acceptedPairCount"], 2)
        self.assertEqual(segment["nonzeroDeltaPairCount"], 2)
        self.assertEqual(segment["zeroDeltaPairCount"], 0)
        self.assertEqual(segment["net3d"], 0)
        self.assertAlmostEqual(segment["path3d"], 2 * 41**.5)
        self.assertEqual(out["observedCoordinateDeltaStatus"], "candidate-nonzero-within-admitted-segments")

    def test_invalid_and_mixed_identity_rejected(self):
        report = fixture()
        report["observations"][0]["unitKey"] = "1"
        with self.assertRaises(ValueError): summarize(report)
        with self.assertRaises(ValueError): summarize(fixture(), speed=0)

    def test_cli_hashes_input_and_refuses_invalid_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            args = [str(path),"--max-gap-seconds","5","--max-speed-3d","10"]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(s.main(args), 0)
            self.assertEqual(len(json.loads(output.getvalue())["sourceSha256"]), 64)
            path.write_text('{"a":1,"a":2}',encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(s.main(args), 2)


if __name__ == "__main__":
    unittest.main()
