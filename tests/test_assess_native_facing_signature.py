"""Focused, self-contained facing signature regression fixtures."""
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import hashlib

from scripts import assess_native_facing_signature as facing
from scripts import fresh_native_actor_pose as pose
from tests.test_compare_native_actor_pose_turn import report, stamp
from tests.test_sample_current_native_vitals import EXPECTED_GAME

VM = {"vmx": "lab2.vmx", "pid": 77, "startTicks": 100}
UNIT = "123"
AGENT = "a" * 32


class FacingSignatureTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.capture_counter = 0

    def capture(self, i, angle, *, x=0.0, z=0.0, unit=UNIT, game_pid=None):
        folder = self.root / f"frame-{i}-{self.capture_counter}"
        self.capture_counter += 1
        folder.mkdir()
        native = report(angle, start=10*i, end=10*i+1)
        raw = (json.dumps(native, sort_keys=True, separators=(",", ":")) + "\n").encode()
        sample = folder / "samples.json"
        sample.write_bytes(raw)
        pid = game_pid if game_pid is not None else EXPECTED_GAME["processId"]
        metrics = pose.validate_report(native, pid=EXPECTED_GAME["processId"],
                                       ticks=EXPECTED_GAME["processStartUtcTicks"])
        self.assertEqual(metrics["playerKeyDecimal"], UNIT)
        common = {
            "schemaVersion": 1, "status": "candidate-only", "lab": "lab2",
            "transport": "persistent-control-agent", "vmIdentity": dict(VM),
            "gameProcessId": pid,
            "gameProcessStartUtcTicks": EXPECTED_GAME["processStartUtcTicks"],
            "gameSha256": EXPECTED_GAME["executableSha256"],
            "activeAgentInstanceId": AGENT, "observedAtUtc": stamp(10*i+2),
        }
        summary = {
            **common, "sourceReport": str(sample),
            "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
            "metrics": dict(metrics, unitKey=UNIT),
        }
        summary_path = folder / "summary.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        position = {
            **common, "sourceReportSha256": hashlib.sha256(
                f"native-position-{i}".encode()).hexdigest().upper(),
            "metrics": {"unitKey": unit,
                        "ownerIdentityStatus": "player-component-chain-anchored",
                        "x": x, "y": 0.0, "z": z, "freshness": "unqualified"},
        }
        root = {
            "schemaVersion": 1, "status": "candidate-only",
            "targetId": "lab2", "ownerHost": "AMD-DESKTOP",
            "mode": "native-read-only", "atomic": False,
            "luaReaderUsed": False, "screenshotUsed": False,
            "unitKey": unit, "position": position,
            "actor-pose": {**summary, "summaryPath": str(summary_path)},
        }
        path = folder / "readout.json"
        path.write_text(json.dumps(root), encoding="utf-8")
        return path

    def sequence(self, angles=(30, 30, 0, 30, 30), forward=True):
        return [self.capture(i, angle,
                             x=(math.cos(math.radians(30)) if i == 4 and forward else 0),
                             z=(math.sin(math.radians(30)) if i == 4 and forward else 0))
                for i, angle in enumerate(angles)]

    def test_v1_historical_radian_formula_and_controls(self):
        original = (-2.2959280014038086, -2.2959280014038086,
                    -1.6913222074508667, -2.291287422180176)
        yaws = list(map(facing.v1_body_yaw_degrees, original))
        self.assertAlmostEqual(yaws[0], yaws[1], places=9)
        self.assertAlmostEqual(facing.wrap180(yaws[2]-yaws[1]),
                               -34.641360262659816, places=5)
        self.assertAlmostEqual(facing.wrap180(yaws[3]-yaws[2]),
                               34.37547465864952, places=5)
        self.assertAlmostEqual(yaws[3], -138.7189010576659, places=5)
        self.assertAlmostEqual(-138.72031892901367-yaws[3],
                               -0.0014178713477690508, places=5)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            facing.v1_body_yaw_degrees(float("nan"))

    def test_actual_source_hashes_join_and_provisional_actor_sign(self):
        result = facing.assess(self.sequence())
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(len(result["readoutSha256"]), 5)
        self.assertTrue(all(row["stationaryCandidate"] for row in
                            result["stationaryControlPhases"].values()))
        actor = result["matrixCandidates"]["actorMatrix"]
        self.assertEqual(actor["status"], "provisional-behavior-consistent")
        self.assertTrue(actor["cameraInvariantCandidate"])
        self.assertEqual(actor["signMultiplierCandidate"], 1)
        self.assertAlmostEqual(actor["turnLeftDeltaDegreesCandidate"], -30)
        self.assertAlmostEqual(actor["turnRightDeltaDegreesCandidate"], 30)
        self.assertAlmostEqual(actor["forwardTravelDegreesCandidate"], 30)
        self.assertAlmostEqual(actor["singleForwardOffsetFitDegreesCandidate"], 0)
        self.assertFalse(actor["absoluteFacingQualified"])
        self.assertEqual(result["matrixCandidates"]["modelMatrix"]["status"],
                         "inconclusive")
        self.assertFalse(result["bodyFacingQualified"])
        self.assertFalse(result["historicalReference"]["currentLocatorReused"])

    def test_opposite_matrix_sign_is_detectable_without_claiming_facing(self):
        result = facing.assess(self.sequence(angles=(30,30,60,30,30)))
        actor = result["matrixCandidates"]["actorMatrix"]
        self.assertEqual(actor["status"], "provisional-behavior-consistent")
        self.assertEqual(actor["signMultiplierCandidate"], -1)
        self.assertFalse(actor["absoluteFacingQualified"])

    def test_camera_change_and_zero_travel_are_not_promoted(self):
        wrong_camera = facing.assess(self.sequence(angles=(30,35,0,30,30)))
        self.assertEqual(wrong_camera["matrixCandidates"]["actorMatrix"]["status"],
                         "inconclusive")
        stopped = facing.assess(self.sequence(forward=False))
        self.assertEqual(stopped["matrixCandidates"]["actorMatrix"]["status"],
                         "inconclusive")
        self.assertIsNone(stopped["matrixCandidates"]["actorMatrix"][
            "singleForwardOffsetFitDegreesCandidate"])

    def test_translation_during_any_control_prevents_false_facing_consistency(self):
        # Keep A/D matrix deltas and the W course plausible while translating
        # during a nominal camera-only, A, or D phase. Old code promoted all
        # three to behavior-consistent despite nonstationary turn controls.
        for moved_phase in (1, 2, 3):
            with self.subTest(phase=facing.PHASES[moved_phase]):
                paths = []
                for i, angle in enumerate((30, 30, 0, 30, 30)):
                    x = .25 if i >= moved_phase else 0.0
                    z = 0.0
                    if i == 4:
                        x += math.cos(math.radians(30))
                        z += math.sin(math.radians(30))
                    paths.append(self.capture(i, angle, x=x, z=z))
                result = facing.assess(paths)
                self.assertFalse(result["stationaryControlPhases"][
                    facing.PHASES[moved_phase]]["stationaryCandidate"])
                self.assertEqual(result["matrixCandidates"]["actorMatrix"]["status"],
                                 "inconclusive")

    def test_unavailable_control_xyz_prevents_false_facing_consistency(self):
        paths = self.sequence()
        raw = json.loads(paths[1].read_text(encoding="utf-8"))
        raw["position"]["metrics"]["ownerIdentityStatus"] = "unanchored"
        paths[1].write_text(json.dumps(raw), encoding="utf-8")
        result = facing.assess(paths)
        self.assertIsNone(result["stationaryControlPhases"]["camera-only"][
            "horizontalXZDistanceCandidate"])
        self.assertFalse(result["stationaryControlPhases"]["camera-only"][
            "stationaryCandidate"])
        self.assertEqual(result["matrixCandidates"]["actorMatrix"]["status"],
                         "inconclusive")

    def test_identity_and_order_fail_closed(self):
        paths = self.sequence()
        wrong = json.loads(paths[3].read_text())
        wrong["unitKey"] = "124"
        paths[3].write_text(json.dumps(wrong))
        with self.assertRaisesRegex(ValueError, "unit"):
            facing.assess(paths)
        with self.assertRaisesRegex(ValueError, "five-distinct"):
            facing.assess([paths[0]] * 5)

    def test_nonadjacent_position_source_replay_is_rejected(self):
        paths = self.sequence()
        first = json.loads(paths[0].read_text(encoding="utf-8"))
        replayed = json.loads(paths[2].read_text(encoding="utf-8"))
        # Adjacent pair hashes still differ. The older source is reused
        # nonadjacently despite newer timestamps and plausible XYZ values.
        replayed["position"]["sourceReportSha256"] = (
            first["position"]["sourceReportSha256"].lower())
        paths[2].write_text(json.dumps(replayed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "facing-repeated-position-source"):
            facing.assess(paths)

    def test_cli_emits_candidate_only(self):
        paths = self.sequence()
        args = [value for key, path in zip(facing.PHASES, paths)
                for value in ("--" + key, str(path))]
        output = io.StringIO()
        with redirect_stdout(output):
            status = facing.main(args)
        self.assertEqual(status, 0)
        self.assertFalse(json.loads(output.getvalue())["bodyFacingQualified"])


if __name__ == "__main__":
    unittest.main()
