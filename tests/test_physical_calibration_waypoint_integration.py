"""One offline end-to-end physical XYZ -> W/Q calibration -> waypoint pulse."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import physical_calibration as calibration
from scripts import physical_waypoint_decision as waypoint
from tests.test_physical_waypoint_decision import position, catalog


class PhysicalPipelineTests(unittest.TestCase):
    def test_two_real_calibration_records_feed_one_waypoint_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def burst(name, second, x, z):
                report = position()
                for row in report["observations"]:
                    index = row["index"] - 1
                    row["startedAtUtc"] = f"2026-11-11T07:06:{second:02d}.{index * 200:03d}Z"
                    row["completedAtUtc"] = f"2026-11-11T07:06:{second:02d}.{index * 200 + 100:03d}Z"
                    row.update(x=x, y=0, z=z)
                path = root / f"{name}.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                return path

            captures = {
                "w_before": burst("w-before", 38, 0, 0),
                "w_after": burst("w-after", 39, 1, 0),
                "q_before": burst("q-before", 40, 1, 0),
                "q_after": burst("q-after", 41, 1, 1),
            }
            current = burst("current", 42, 1, 1)
            anchors = root / "anchors.json"
            anchors.write_text(json.dumps(catalog(x=1.8, z=1)), encoding="utf-8")
            vectors = {}
            for key in ("w", "q"):
                output = root / f"{key}-calibration.json"
                with redirect_stdout(io.StringIO()) as logged:
                    result = calibration.main([
                        "--before", str(captures[f"{key}_before"]),
                        "--after", str(captures[f"{key}_after"]),
                        "--key", key, "--hold-ms", "100", "--out", str(output),
                    ])
                self.assertEqual(result, 0, logged.getvalue())
                self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["key"], key)
                vectors[key] = output

            with redirect_stdout(io.StringIO()) as logged:
                exit_code = waypoint.main([
                    "--position-report", str(current), "--catalog", str(anchors),
                    "--anchor-id", "Near_Gate",
                    "--w-calibration", str(vectors["w"]),
                    "--q-calibration", str(vectors["q"]),
                ])
            self.assertEqual(exit_code, 0, logged.getvalue())
            result = json.loads(logged.getvalue())
            self.assertEqual(result["decision"], "suggested-one-pulse")
            self.assertEqual(result["candidateAction"]["key"], "w")
            self.assertEqual(result["candidateAction"]["holdMilliseconds"], 80)
            self.assertAlmostEqual(result["candidateAction"]["predictedProgressCandidate"], 0.8)
            self.assertFalse(result["movementEligible"])
            self.assertFalse(result["arrivalQualified"])


if __name__ == "__main__":
    unittest.main()
