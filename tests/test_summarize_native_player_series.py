"""Offline-only series summaries; no controller, VM, network or game calls."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts import summarize_native_player_series as tool

UNIT = "18446744073709551615"
GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"


def sample(index, fields=("position", "vitals")):
    stamp = f"2026-11-09T17:00:{index:02d}Z"
    report_sha = f"{index+1:064x}"
    result = {
        "schemaVersion": 1, "status": "candidate-only",
        "targetId": "lab2", "ownerHost": "AMD-DESKTOP",
        "mode": "native-read-only", "atomic": False,
        "luaReaderUsed": False, "screenshotUsed": False, "unitKey": UNIT,
    }
    for field in fields:
        metrics = {"unitKey": UNIT}
        if field == "position":
            xyz = ((0, 0, 0), (3, 0, 4), (0, 0, 8))[index]
            metrics.update(dict(zip(("x", "y", "z"), xyz)))
            metrics["ownerIdentityStatus"] = "player-component-chain-anchored"
        else:
            metrics.update({
                "health": {"status": "calculated-candidate", "current": (90, 85, 70)[index],
                           "maximum": 100},
                "energy": {"status": "calculated-candidate", "current": 100, "maximum": 100},
                "mana": {"status": "unavailable", "current": None, "maximum": None},
            })
        result[field] = {
            "schemaVersion": 1, "status": "candidate-only",
            "lab": "lab2", "transport": "persistent-control-agent",
            "vmIdentity": {"vmx": "lab2.vmx", "pid": 77, "startTicks": 99},
            "gameProcessId": 42, "gameProcessStartUtcTicks": 456789,
            "gameSha256": GAME_SHA, "activeAgentInstanceId": "a" * 32,
            "observedAtUtc": stamp, "sourceReportSha256": report_sha,
            "metrics": metrics,
        }
    return result


def reads(fields=("position", "vitals")):
    return [(sample(i, fields), f"{i+10:064x}") for i in range(3)]


class NativePlayerSeriesTests(unittest.TestCase):
    def test_path_vs_net_with_real_turn_like_sequence(self):
        originals = reads()
        prior = copy.deepcopy(originals)
        result = tool.summarize(originals)
        pos = result["positionSummary"]
        self.assertEqual(result["readCount"], 3)
        self.assertEqual(result["fieldsCompared"], ["position", "vitals"])
        self.assertEqual(pos["status"], "complete-candidate")
        self.assertEqual(pos["validSegmentCount"], 2)
        self.assertEqual(pos["cumulativeHorizontalXZDistanceCandidate"], 10)
        self.assertEqual(pos["netHorizontalXZDistanceCandidate"], 8)
        self.assertEqual(pos["netDeltaCandidate"], {"x": 0.0, "y": 0.0, "z": 8.0})
        self.assertEqual([s["horizontalXZDistanceCandidate"] for s in result["segments"]], [5, 5])
        self.assertEqual(result["vitalsEndpointDeltasCandidate"]["health"]["deltaCurrentCandidate"], -20)
        self.assertEqual(result["vitalsEndpointDeltasCandidate"]["energy"]["deltaCurrentCandidate"], 0)
        self.assertIsNone(result["vitalsEndpointDeltasCandidate"]["mana"]["deltaCurrentCandidate"])
        self.assertIn("NOT independent movement proof", result["qualification"])
        self.assertEqual(originals, prior)

    def test_translating_course_and_change_are_coordinate_relative(self):
        result = tool.summarize(reads(("position",)))
        first, second = result["segments"]
        self.assertAlmostEqual(first["travelCourseDegreesCandidate"], 53.1301023542)
        self.assertIsNone(first["travelCourseChangeDegreesCandidate"])
        self.assertAlmostEqual(second["travelCourseDegreesCandidate"], 126.8698976458)
        self.assertAlmostEqual(second["travelCourseChangeDegreesCandidate"], 73.7397952916)
        self.assertIn("NOT player-facing yaw", result["qualification"])
        self.assertIn("NOT independent movement proof", result["qualification"])

    def test_course_change_wraps_through_zero_without_false_large_turn(self):
        items = reads(("position",))
        dz = math.tan(math.radians(10))
        items[1][0]["position"]["metrics"].update({"x": 1, "z": -dz})
        items[2][0]["position"]["metrics"].update({"x": 2, "z": 0})
        result = tool.summarize(items)
        self.assertAlmostEqual(result["segments"][0]["travelCourseDegreesCandidate"], 350)
        self.assertAlmostEqual(result["segments"][1]["travelCourseDegreesCandidate"], 10)
        self.assertAlmostEqual(result["segments"][1]["travelCourseChangeDegreesCandidate"], 20)

    def test_stationary_and_missing_segments_never_claim_travel_course(self):
        items = reads(("position",))
        items[1][0]["position"]["metrics"].update({"x": 0, "z": 0})
        result = tool.summarize(items)
        self.assertIsNone(result["segments"][0]["travelCourseDegreesCandidate"])
        self.assertIsNone(result["segments"][1]["travelCourseChangeDegreesCandidate"])
        self.assertEqual(result["segments"][0]["horizontalXZDistanceCandidate"], 0)
        items = reads(("position",))
        items[1][0]["position"]["metrics"]["ownerIdentityStatus"] = "unqualified"
        result = tool.summarize(items)
        self.assertIsNone(result["segments"][0]["travelCourseDegreesCandidate"])
        self.assertIsNone(result["segments"][1]["travelCourseChangeDegreesCandidate"])

    def test_vitals_only_preserves_unavailable_position(self):
        result = tool.summarize(reads(("vitals",)))
        self.assertIsNone(result["positionSummary"])
        self.assertEqual(result["vitalsEndpointDeltasCandidate"]["health"]["deltaCurrentCandidate"], -20)
        self.assertTrue(all(s["positionStatus"] == "not-selected" for s in result["segments"]))

    def test_missing_middle_anchor_prevents_path_length_without_faking_zero(self):
        items = reads(("position",))
        items[1][0]["position"]["metrics"]["ownerIdentityStatus"] = "unqualified"
        result = tool.summarize(items)
        self.assertEqual(result["positionSummary"]["status"], "incomplete-segment-candidates")
        self.assertIsNone(result["positionSummary"]["cumulativeHorizontalXZDistanceCandidate"])
        self.assertEqual(result["positionSummary"]["validSegmentCount"], 0)
        # Both endpoints remain same-owner, so net endpoint displacement is valid.
        self.assertEqual(result["positionSummary"]["netHorizontalXZDistanceCandidate"], 8)

    def test_changed_agent_and_discontinuous_timestamp_fail_closed(self):
        items = reads()
        items[2][0]["position"]["activeAgentInstanceId"] = "b" * 32
        items[2][0]["vitals"]["activeAgentInstanceId"] = "b" * 32
        with self.assertRaisesRegex(ValueError, "process-vm-or-agent-changed"):
            tool.summarize(items)
        items = reads()
        items[2][0]["position"]["observedAtUtc"] = items[1][0]["position"]["observedAtUtc"]
        with self.assertRaisesRegex(ValueError, "nonadvancing-position"):
            tool.summarize(items)

    def test_reused_nonadjacent_source_sha_fails(self):
        items = reads()
        # Add a distinct final capture: the repeated source is now interior,
        # not the same first/last report (which the pair validator also rejects).
        last = copy.deepcopy(items[2][0])
        for field in ("position", "vitals"):
            last[field]["observedAtUtc"] = "2026-11-09T17:00:03Z"
            last[field]["sourceReportSha256"] = f"{4:064x}"
        items.append((last, f"{14:064x}"))
        items[2][0]["position"]["sourceReportSha256"] = items[0][0]["position"]["sourceReportSha256"]
        with self.assertRaisesRegex(ValueError, "repeated-position-report"):
            tool.summarize(items)

    def test_unavailable_geometry_and_overflow_never_promoted_to_distance(self):
        items = reads(("position",))
        items[1][0]["position"]["metrics"]["x"] = None
        result = tool.summarize(items)
        self.assertIsNone(result["positionSummary"]["cumulativeHorizontalXZDistanceCandidate"])
        self.assertIsNone(result["segments"][0]["horizontalXZDistanceCandidate"])

        items = reads(("position",))
        items[0][0]["position"]["metrics"]["x"] = -1e308
        items[1][0]["position"]["metrics"]["x"] = 1e308
        result = tool.summarize(items)
        self.assertIsNone(result["positionSummary"]["cumulativeHorizontalXZDistanceCandidate"])
        self.assertEqual(result["segments"][0]["positionStatus"], "unavailable-overflow")

    def test_mixed_fields_or_count_outside_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, "length-invalid"):
            tool.summarize(reads()[:1])
        with self.assertRaisesRegex(ValueError, "length-invalid"):
            tool.summarize(reads() * 11)
        items = reads()
        del items[1][0]["vitals"]
        with self.assertRaisesRegex(ValueError, "field-selection-mismatch"):
            tool.summarize(items)

    def test_cli_reads_exact_files_and_blocks_invalid_file(self):
        with TemporaryDirectory() as folder:
            files = []
            for i in range(3):
                path = Path(folder) / f"read-{i}.json"
                path.write_text(json.dumps(sample(i)), encoding="utf-8")
                files.append(path)
            output = io.StringIO()
            with redirect_stdout(output):
                code = tool.main(["--reads", *map(str, files)])
            self.assertEqual(code, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["readCount"], 3)
            self.assertEqual(result["firstSourceSha256"],
                             hashlib.sha256(files[0].read_bytes()).hexdigest().upper())
            output = io.StringIO()
            with redirect_stdout(output):
                code = tool.main(["--reads", str(files[0]), str(files[0])])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue()),
                             {"status": "blocked", "reason": "native-player-series-unavailable"})

    def test_script_direct_cli_help(self):
        result = subprocess.run(
            [sys.executable, str(Path(tool.__file__).resolve()), "--help"],
            cwd=Path(tool.__file__).resolve().parents[1], capture_output=True,
            text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
