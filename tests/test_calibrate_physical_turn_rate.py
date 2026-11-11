"""Offline candidate A/D turn rate from physical orientation and actor-pose reports."""
from copy import deepcopy
import io
import json
import math
from contextlib import redirect_stdout
from pathlib import Path
import struct
import tempfile
import unittest

from scripts import calibrate_physical_turn_rate as rate


IDENTITY = {
    "processId": 44888,
    "processStartUtcTicks": 639299470183328173,
    "executablePath": r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
    "executableSha256": "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8",
    "moduleBaseAddress": 140701863903232,
    "moduleSize": 63164416,
}
KEY = "239816685251645959"


def matrix(angle, offset):
    theta = math.radians(angle)
    values = [math.cos(theta), 0, -math.sin(theta), 0, 1, 0,
              math.sin(theta), 0, math.cos(theta)]
    bits = [struct.unpack("<I", struct.pack("<f", f))[0] for f in values]
    floats = [struct.unpack("<f", struct.pack("<I", bit))[0] for bit in bits]
    return {
        "sourceOffset": offset,
        "rawBits": bits,
        "rowMajorF32": floats,
        "status": "structural-y-planar-matrix-candidate",
        "planarAngleDegreesCandidate": math.degrees(math.atan2(floats[6], floats[0])),
    }


def report(kind, second, angle, *, identity=None):
    actual = deepcopy(identity or IDENTITY)
    rows = []
    for index, offset in enumerate((0, 1)):
        sec = second + offset
        row = {
            "identity": deepcopy(actual),
            "startedAtUtc": f"2026-11-11T02:00:{sec:02d}.000000+00:00",
            "completedAtUtc": f"2026-11-11T02:00:{sec:02d}.001000+00:00",
            "qualification": "matrix-descriptor-candidate-only",
        }
        if kind == "orientation":
            row.update({
                "unitKey": KEY, "componentAddress": 1779061326720,
                "refreshHandleRaw": "0x0000000000000000",
                "refreshFlagRaw": 0,
                "primary": matrix(angle, 96),
                "secondary": matrix(angle, 148),
            })
        else:
            row.update({
                "playerKeyDecimal": KEY,
                "playerEntityDecimal": "1779162488336",
                "actorComponentDecimal": "1779162622528",
                "positionComponentDecimal": "1779061326720",
                "actorHeadingQualified": False,
                "renderStatus": "alternate-reference-branch-not-followed",
                "actorMatrix": matrix(angle, 920),
                "modelMatrix": matrix(0, 1004),
                "renderMatrix": None,
            })
        rows.append(row)
    return {
        "schemaVersion": 1,
        "contractVersion": f"native-current-{kind}-candidate-burst/1",
        "status": "complete",
        "identity": actual,
        "requestedSamples": 2,
        "completedSamples": 2,
        "observations": rows,
        "observation": deepcopy(rows[-1]),
    }


class PhysicalTurnRateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.before = self.root / "before.json"
        self.after = self.root / "after.json"

    def pair(self, first=179, last=-179, *, kind="orientation", after_identity=None):
        self.before.write_text(json.dumps(report(kind, 1, first)), encoding="utf-8")
        self.after.write_text(json.dumps(
            report(kind, 4, last, identity=after_identity)), encoding="utf-8")
        return self.before, self.after

    def test_wrapped_left_candidate_rate_and_unqualified_labels(self):
        result = rate.calibrate(*self.pair(), key="a", hold_ms=100,
                                matrix_source="secondary")
        self.assertAlmostEqual(result["toAfterEndDeltaDegreesCandidate"], 2, places=3)
        self.assertAlmostEqual(result["signedDegreesPerDeclaredMillisecondCandidate"],
                               0.02, places=5)
        self.assertIs(result["turnResponseVerified"], False)
        self.assertIs(result["actorHeadingQualified"], False)
        self.assertIs(result["cameraYawQualified"], False)
        self.assertIs(result["movementEligible"], False)
        self.assertEqual(result["holdTimingSource"], "declared-only-unverified")
        self.assertRegex(result["beforeSourceSha256"], "^[A-F0-9]{64}$")
        self.assertEqual(result["key"], "a")

    def test_wrapped_right_negative_candidate_and_zero(self):
        result = rate.calibrate(*self.pair(-179, 179), key="d", hold_ms=100,
                                matrix_source="primary")
        self.assertAlmostEqual(result["signedDegreesPerDeclaredMillisecondCandidate"],
                               -0.02, places=5)
        result = rate.calibrate(*self.pair(10, 10), key="a", hold_ms=100,
                                matrix_source="primary")
        self.assertEqual(result["signedDegreesPerDeclaredMillisecondCandidate"], 0)
        self.assertIs(result["turnResponseVerified"], False)

    def test_actor_pose_candidate_and_wrong_source_block(self):
        result = rate.calibrate(*self.pair(15, 45, kind="actor-pose"),
                                key="a", hold_ms=100, matrix_source="actor")
        self.assertAlmostEqual(result["signedDegreesPerDeclaredMillisecondCandidate"],
                               0.3, places=4)
        with self.assertRaisesRegex(rate.PhysicalTurnRateError, "matrix source"):
            rate.calibrate(self.before, self.after, key="a", hold_ms=100,
                           matrix_source="secondary")

    def test_exact_180_alias_and_wrong_holds_block(self):
        with self.assertRaisesRegex(rate.PhysicalTurnRateError, "ambiguous"):
            rate.calibrate(*self.pair(0, 180), key="a", hold_ms=100,
                           matrix_source="secondary")
        self.pair()
        for key, hold in (("w", 100), ("a", 0), ("d", 151), ("a", True)):
            with self.subTest(key=key, hold=hold):
                with self.assertRaises(rate.PhysicalTurnRateError):
                    rate.calibrate(self.before, self.after, key=key, hold_ms=hold,
                                   matrix_source="secondary")

    def test_changed_epoch_and_player_block_from_existing_analyzer(self):
        changed = deepcopy(IDENTITY)
        changed["processStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "turn-process-epoch-changed"):
            rate.calibrate(*self.pair(after_identity=changed), key="a", hold_ms=100,
                           matrix_source="secondary")
        self.pair()
        raw = json.loads(self.after.read_text(encoding="utf-8"))
        for row in raw["observations"]:
            row["unitKey"] = "2"
        raw["observation"] = deepcopy(raw["observations"][-1])
        self.after.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "turn-player-or-component-changed"):
            rate.calibrate(self.before, self.after, key="a", hold_ms=100,
                           matrix_source="secondary")

    def test_bad_capture_gap_and_cli_block(self):
        with self.assertRaisesRegex(ValueError, "turn-capture-gap-exceeded"):
            rate.calibrate(*self.pair(), key="a", hold_ms=100,
                           matrix_source="secondary", max_gap_seconds=1)
        args = ["--before", str(self.before), "--after", str(self.after),
                "--key", "d", "--hold-ms", "100", "--matrix-source", "secondary"]
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(rate.main(args), 0)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "offline-physical-yaw-rate-candidate")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(rate.main(args[:-2] + ["--matrix-source", "actor"]), 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
