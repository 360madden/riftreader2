"""Offline physical native XYZ to one candidate W/Q waypoint decision."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from scripts import navigation_anchors as anchors
from scripts import physical_waypoint_decision as decision


BUILD = "A" * 64
UNIT = "239816685251645959"
START_TICKS = 639299470183328173


def position():
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-position-candidate-samples/1",
        "qualification": "candidate-only-not-passive-fresh-or-player-semantic-qualified",
        "status": "complete",
        "sourceBuildSha256": BUILD,
        "identity": {
            "processId": 44888, "processStartUtcTicks": START_TICKS,
            "executablePath": "C:\\Program Files (x86)\\Glyph\\Games\\RIFT\\Live\\rift_x64.exe",
            "executableSha256": BUILD,
        },
        "requestedSamples": 2, "completedSamples": 2,
        "observations": [
            {
                "index": 1, "unitKey": UNIT,
                "ownerIdentityStatus": "player-component-chain-anchored",
                "startedAtUtc": "2026-11-11T07:06:42.000Z",
                "completedAtUtc": "2026-11-11T07:06:42.100Z",
                "x": 0, "y": 0, "z": 0,
            },
            {
                "index": 2, "unitKey": UNIT,
                "ownerIdentityStatus": "player-component-chain-anchored",
                "startedAtUtc": "2026-11-11T07:06:42.200Z",
                "completedAtUtc": "2026-11-11T07:06:42.300Z",
                "x": 0, "y": 0, "z": 0,
            },
        ],
    }


def catalog(x=0.8, z=0):
    return {
        "schemaVersion": 1, "coordinateFrame": anchors.COORDINATE_FRAME,
        "anchors": [{
            "id": "Near_Gate", "label": "Near gate",
            "position": {"x": x, "y": 0, "z": z},
            "zoneLabel": None,
            "source": {
                "kind": "native-cache-candidate",
                "gameBuildSha256": BUILD,
                "evidenceSha256": "B" * 64,
                "capturedAtUtc": "2026-11-08T13:00:00Z",
            },
            "qualification": "offline-reference-only",
        }],
    }


def empirical(key):
    dx, dz = (0.01, 0.0) if key == "w" else (0.0, 0.01)
    return {
        "schemaVersion": 1,
        "status": "offline-physical-calibration-candidate",
        "movementEligible": False,
        "actionVerified": False,
        "qualification": "nominal-key-hold-and-two-native-position-candidates-only",
        "key": key,
        "dx_per_ms": dx,
        "dz_per_ms": dz,
        "calibration_hold_ms": 100,
        "horizontal_displacement": 1.0,
        "vertical_displacement": 0.0,
        "processId": 44888,
        "processStartUtcTicks": str(START_TICKS),
        "gameBuildSha256": BUILD,
        "unitKey": UNIT,
        "beforeReportSha256": "C" * 64,
        "afterReportSha256": "D" * 64,
        "beforeSampleUtc": "2026-11-11T07:06:41.000Z",
        "afterSampleUtc": "2026-11-11T07:06:41.500Z",
    }


class PhysicalWaypointDecisionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.native_path = self.root / "native.json"
        self.catalog_path = self.root / "catalog.json"
        self.w_path = self.root / "w.json"
        self.q_path = self.root / "q.json"
        self.store()

    def store(self, *, source=None, anchors_value=None, calibrations=None):
        self.native_path.write_text(json.dumps(position() if source is None else source),
                                    encoding="utf-8")
        self.catalog_path.write_text(json.dumps(catalog() if anchors_value is None
                                                else anchors_value), encoding="utf-8")
        records = calibrations or {"w": empirical("w"), "q": empirical("q")}
        self.w_path.write_text(json.dumps(records["w"]), encoding="utf-8")
        self.q_path.write_text(json.dumps(records["q"]), encoding="utf-8")

    def plan(self):
        return decision.decide(self.native_path, self.catalog_path,
                               "Near_Gate", self.w_path, self.q_path)

    def test_toward_anchor_produces_one_bounded_w_pulse(self):
        result = self.plan()
        self.assertEqual(result["status"], "offline-candidate-decision")
        self.assertEqual(result["decision"], "suggested-one-pulse")
        self.assertEqual(result["candidateAction"]["key"], "w")
        self.assertEqual(result["candidateAction"]["holdMilliseconds"], 80)
        self.assertAlmostEqual(result["candidateAction"]["distanceBeforeCandidate"], 0.8)
        self.assertLess(result["candidateAction"]["predictedDistanceAfterCandidate"], .001)
        self.assertIs(result["movementEligible"], False)
        self.assertIs(result["arrivalQualified"], False)
        self.assertIs(result["worldInstanceMatched"], False)
        self.assertIs(result["headingQualified"], False)
        self.assertNotIn("runner", result)
        self.assertNotIn("inputCommand", result)
        self.assertEqual(set(result["calibrationReportSha256"]), {"w", "q"})

    def test_imports_400_500_ms_calibrations_but_retains_150_ms_action_cap(self):
        w, q = empirical("w"), empirical("q")
        w.update(calibration_hold_ms=400, dx_per_ms=0.0025,
                 dz_per_ms=0.0, horizontal_displacement=1.0)
        q.update(calibration_hold_ms=500, dx_per_ms=0.0,
                 dz_per_ms=0.002, horizontal_displacement=1.0)
        self.store(calibrations={"w": w, "q": q})
        result = self.plan()
        self.assertEqual("suggested-one-pulse", result["decision"])
        self.assertEqual("w", result["candidateAction"]["key"])
        self.assertEqual(150, result["candidateAction"]["holdMilliseconds"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["arrivalQualified"])
        q["calibration_hold_ms"] = 1001
        self.store(calibrations={"w": w, "q": q})
        with self.assertRaisesRegex(decision.PhysicalWaypointError, "invalid"):
            self.plan()

    def test_away_from_both_calibrated_keys_blocks(self):
        self.store(anchors_value=catalog(x=-.8))
        with self.assertRaisesRegex(Exception, "no-useful-calibrated-action"):
            self.plan()

    def test_within_tolerance_candidate_is_not_arrival(self):
        self.store(anchors_value=catalog(x=.1))
        result = self.plan()
        self.assertEqual(result["decision"], "within-tolerance-candidate")
        self.assertIs(result["candidateWithinTolerance"], True)
        self.assertIsNone(result["candidateAction"])
        self.assertIs(result["arrivalQualified"], False)

    def test_calibration_process_unit_and_build_mismatches_block(self):
        cases = {
            "pid": ("processId", 123),
            "start": ("processStartUtcTicks", str(START_TICKS + 1)),
            "unit": ("unitKey", "2"),
            "build": ("gameBuildSha256", "C" * 64),
        }
        for label, (key, value) in cases.items():
            with self.subTest(label=label):
                q = empirical("q")
                q[key] = value
                self.store(calibrations={"w": empirical("w"), "q": q})
                with self.assertRaisesRegex(decision.PhysicalWaypointError, "mismatch"):
                    self.plan()

    def test_anchor_build_and_invalid_calibration_rejected(self):
        wrong_anchor = catalog()
        wrong_anchor["anchors"][0]["source"]["gameBuildSha256"] = "C" * 64
        self.store(anchors_value=wrong_anchor)
        with self.assertRaisesRegex(Exception, "different game builds"):
            self.plan()
        q = empirical("q")
        q["dx_per_ms"], q["dz_per_ms"] = 0.01, 0.0
        self.store(calibrations={"w": empirical("w"), "q": q})
        with self.assertRaisesRegex(Exception, "collinear"):
            self.plan()

    def test_future_calibration_and_false_action_verification_rejected(self):
        q = empirical("q")
        q["afterSampleUtc"] = "2026-11-11T07:06:43.000Z"
        self.store(calibrations={"w": empirical("w"), "q": q})
        with self.assertRaisesRegex(decision.PhysicalWaypointError, "chronology"):
            self.plan()
        q = empirical("q")
        q["actionVerified"] = True
        self.store(calibrations={"w": empirical("w"), "q": q})
        with self.assertRaisesRegex(decision.PhysicalWaypointError, "contract"):
            self.plan()

    def test_cli_returns_blocked_not_exception(self):
        args = ["--position-report", str(self.native_path),
                "--catalog", str(self.catalog_path), "--anchor-id", "Near_Gate",
                "--w-calibration", str(self.w_path),
                "--q-calibration", str(self.q_path)]
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(decision.main(args), 0)
        self.assertEqual(json.loads(printed.getvalue())["decision"], "suggested-one-pulse")
        q = empirical("q")
        q["unitKey"] = "2"
        self.store(calibrations={"w": empirical("w"), "q": q})
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(decision.main(args), 2)
        self.assertEqual(json.loads(printed.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
