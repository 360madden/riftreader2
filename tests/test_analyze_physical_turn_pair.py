"""Focused offline checks for physical native turn-pair arithmetic."""
from __future__ import annotations

from copy import deepcopy
import contextlib
from io import StringIO
import json
import math
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from scripts import analyze_physical_turn_pair as turn

IDENTITY = {
    "processId": 44888,
    "processStartUtcTicks": 639299470183328173,
    "executablePath": r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
    "executableSha256": "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8",
    "moduleBaseAddress": 140701863903232,
    "moduleSize": 63164416,
}
KEY = "239816685251645959"
POS_COMPONENT = 1779061326720
ACTOR_COMPONENT = "1779162622528"
PLAYER_ENTITY = "1779162488336"


def matrix(angle, offset):
    rad = math.radians(angle)
    values = [math.cos(rad), 0.0, -math.sin(rad), 0.0, 1.0, 0.0,
              math.sin(rad), 0.0, math.cos(rad)]
    bits = [struct.unpack("<I", struct.pack("<f", v))[0] for v in values]
    floats = [struct.unpack("<f", struct.pack("<I", bit))[0] for bit in bits]
    return {
        "sourceOffset": offset, "rawBits": bits, "rowMajorF32": floats,
        "status": "structural-y-planar-matrix-candidate",
        "planarAngleDegreesCandidate": math.degrees(
            math.atan2(floats[6], floats[0])),
    }


def timestamp(sec, micro=0):
    return f"2026-11-11T02:00:{sec:02d}.{micro:06d}+00:00"


def sample(kind, sec, angle, *, identity=None):
    item = {
        "identity": deepcopy(identity or IDENTITY),
        "startedAtUtc": timestamp(sec),
        "completedAtUtc": timestamp(sec, 1000),
        "qualification": "matrix-descriptor-candidate-only",
    }
    if kind == "orientation":
        item.update({
            "unitKey": KEY,
            "componentAddress": POS_COMPONENT,
            "refreshHandleRaw": "0x0000000000000000",
            "refreshFlagRaw": 0,
            "primary": matrix(angle, 96),
            "secondary": matrix(angle, 148),
        })
    else:
        item.update({
            "playerKeyDecimal": KEY,
            "playerEntityDecimal": PLAYER_ENTITY,
            "actorComponentDecimal": ACTOR_COMPONENT,
            "positionComponentDecimal": str(POS_COMPONENT),
            "actorHeadingQualified": False,
            "renderStatus": "alternate-reference-branch-not-followed",
            "actorMatrix": matrix(angle, 920),
            "modelMatrix": matrix(0, 1004),
            "renderMatrix": None,
        })
    return item


def report(kind, seconds, angles, *, identity=None):
    rows = [sample(kind, sec, angle, identity=identity)
            for sec, angle in zip(seconds, angles)]
    burst = len(rows) > 1
    value = {
        "schemaVersion": 1,
        "contractVersion": f"native-current-{kind}-candidate"
                           + ("-burst/1" if burst else "/1"),
        "status": "complete",
        "identity": deepcopy(identity or IDENTITY),
        "observation": deepcopy(rows[-1]),
    }
    if burst:
        value.update({
            "requestedSamples": len(rows),
            "completedSamples": len(rows),
            "observations": rows,
        })
    return value


class PhysicalTurnPairTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
        return path

    def pair(self, before=None, after=None):
        left = self.save("before.json", before or report(
            "orientation", [1, 2], [179, 179]))
        right = self.save("after.json", after or report(
            "orientation", [4, 5], [-179, -179]))
        return left, right

    def test_rapid_100ns_spaced_orientation_burst_keeps_precise_order(self):
        source = report("orientation", [1, 2, 3], [10, 15, 20])
        for i, row in enumerate(source["observations"]):
            row["startedAtUtc"] = f"2026-11-11T02:00:00.100000{i*2+1}+00:00"
            row["completedAtUtc"] = f"2026-11-11T02:00:00.100000{i*2+2}+00:00"
        source["observation"] = deepcopy(source["observations"][-1])
        path = self.save("fast-candidate.json", source)
        loaded = turn._load(path)
        self.assertEqual(3, loaded["samples"])
        self.assertEqual("orientation", loaded["kind"])
        # A genuinely repeated 100ns timestamp must still fail closed.
        source["observations"][1]["startedAtUtc"] = source["observations"][0]["completedAtUtc"]
        path = self.save("fast-candidate-invalid.json", source)
        with self.assertRaisesRegex(ValueError, "turn-capture-time-order-invalid"):
            turn._load(path)

    def test_cross_file_gap_preserves_one_native_tick(self):
        left = report("orientation", [1], [10])
        right = report("orientation", [1], [20])
        for row, digit in ((left["observation"], 1), (right["observation"], 3)):
            row["startedAtUtc"] = f"2026-11-11T02:00:00.100000{digit}Z"
            row["completedAtUtc"] = f"2026-11-11T02:00:00.100000{digit+1}Z"
        self.assertEqual(turn.compare(*self.pair(left, right))["captureGapSeconds"], 1e-7)
        right["observation"]["startedAtUtc"] = left["observation"]["completedAtUtc"]
        with self.assertRaisesRegex(ValueError, "turn-capture-time-order-invalid"):
            turn.compare(*self.pair(left, right))

    def test_orientation_wrap_and_endpoints(self):
        output = turn.compare(*self.pair())
        self.assertEqual(output["status"], "candidate-only")
        self.assertEqual(output["sourceKind"], "orientation")
        self.assertEqual(output["beforeSamples"], 2)
        self.assertEqual(output["afterSamples"], 2)
        self.assertAlmostEqual(
            output["matrixComparisons"]["secondary"]
            ["toAfterStartDeltaDegreesCandidate"], 2, places=3)
        self.assertTrue(output["matrixComparisons"]["secondary"]
                        ["rawBitsChangedAtAfterEnd"])
        self.assertFalse(output["actorHeadingQualified"])
        self.assertFalse(output["inputResponseVerified"])

    def test_actor_pose_reports_with_null_render(self):
        before, after = self.pair(
            report("actor-pose", [1], [10]),
            report("actor-pose", [4, 5], [30, 30]))
        output = turn.compare(before, after)
        self.assertAlmostEqual(
            output["matrixComparisons"]["actor"]
            ["toAfterEndDeltaDegreesCandidate"], 20, places=3)
        self.assertIsNone(output["matrixComparisons"]["render"]
                          ["toAfterEndDeltaDegreesCandidate"])
        self.assertIsNone(output["matrixComparisons"]["render"]
                          ["rawBitsChangedAtAfterEnd"])
        self.assertEqual(output["matrixComparisons"]["model"]
                         ["toAfterStartDeltaDegreesCandidate"], 0)

    def test_single_report_with_observation_only_identity(self):
        before = report("orientation", [1], [10])
        after = report("orientation", [4], [20])
        del before["identity"]
        del after["identity"]
        output = turn.compare(*self.pair(before, after))
        self.assertAlmostEqual(output["matrixComparisons"]["primary"]
                               ["toAfterEndDeltaDegreesCandidate"], 10, places=3)

    def test_exact_half_turn_is_ambiguous(self):
        result = turn.compare(*self.pair(
            report("orientation", [1], [0]),
            report("orientation", [4], [180])))
        self.assertIsNone(result["matrixComparisons"]["primary"]
                          ["toAfterEndDeltaDegreesCandidate"])

    def test_changed_process_epoch_is_blocked(self):
        changed = deepcopy(IDENTITY)
        changed["processStartUtcTicks"] += 1
        before, after = self.pair(after=report(
            "orientation", [4], [20], identity=changed))
        with self.assertRaisesRegex(ValueError, "turn-process-epoch-changed"):
            turn.compare(before, after)

    def test_changed_component_is_blocked(self):
        after = report("actor-pose", [4], [20])
        after["observation"]["actorComponentDecimal"] = str(int(ACTOR_COMPONENT) + 8)
        before, after = self.pair(
            report("actor-pose", [1], [0]), after)
        with self.assertRaisesRegex(ValueError, "turn-player-or-component-changed"):
            turn.compare(before, after)

    def test_reordered_or_overlapping_capture_is_blocked(self):
        before, after = self.pair(after=report(
            "orientation", [2], [0]))
        with self.assertRaisesRegex(ValueError, "turn-capture-time-order-invalid"):
            turn.compare(before, after)

    def test_gap_exceedance_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "turn-capture-gap-exceeded"):
            turn.compare(*self.pair(), max_gap_seconds=1)

    def test_source_kind_mismatch_is_blocked(self):
        before, after = self.pair(after=report(
            "actor-pose", [4], [20]))
        with self.assertRaisesRegex(ValueError, "turn-source-kind-mismatch"):
            turn.compare(before, after)

    def test_corrupt_raw_bits_is_blocked(self):
        after = report("orientation", [4], [20])
        after["observation"]["primary"]["rawBits"][0] ^= 1
        before, after = self.pair(after=after)
        with self.assertRaisesRegex(ValueError, "invalid-native-orientation-matrix-bits"):
            turn.compare(before, after)

    def test_incomplete_burst_is_blocked(self):
        after = report("orientation", [4, 5], [20, 20])
        after["completedSamples"] = 1
        before, after = self.pair(after=after)
        with self.assertRaisesRegex(ValueError, "invalid-physical-turn-count"):
            turn.compare(before, after)

    def test_reusing_same_source_is_blocked(self):
        before, _ = self.pair()
        with self.assertRaisesRegex(ValueError, "turn-identical-sources"):
            turn.compare(before, before)

    def test_cli_returns_clean_block_reason(self):
        buffer = StringIO()
        with contextlib.redirect_stdout(buffer):
            code = turn.main(["--before", str(self.root / "missing.json"),
                              "--after", str(self.root / "also-missing.json")])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(buffer.getvalue())["reason"],
                         "turn-source-missing-or-oversized")




class BurstStabilityTests(unittest.TestCase):
    def assess(self, angles, seconds=.4):
        from datetime import datetime, timedelta, timezone
        start = datetime(2026, 11, 11, tzinfo=timezone.utc)
        stamps = [start + timedelta(seconds=seconds*i/max(1, len(angles)-1))
                  for i in range(len(angles))]
        capture = {
            "matrices": [{"actor": {"angle": angle}} for angle in angles],
            "times": [(stamp, stamp) for stamp in stamps],
        }
        return turn.burst_stability(capture, "actor")

    def test_stable_sampled_interval(self):
        result = self.assess([-40.0] * 5)
        self.assertTrue(result["sampledPoseStableCandidate"])
        self.assertEqual(result["angularSpanDegreesCandidate"], 0)

    def test_turning_and_insufficient_samples_are_unstable(self):
        self.assertFalse(self.assess([-40, -42, -44])["sampledPoseStableCandidate"])
        self.assertFalse(self.assess([-40])["sampledPoseStableCandidate"])
        self.assertFalse(self.assess([-40] * 5, .01)["sampledPoseStableCandidate"])
        self.assertFalse(self.assess([-40] * 5, 4)["sampledPoseStableCandidate"])
        self.assertFalse(self.assess([None] * 5)["sampledPoseStableCandidate"])

    def test_wrap_boundary_has_small_angular_span(self):
        result = self.assess([179.999, -179.999, 180.0])
        self.assertAlmostEqual(result["angularSpanDegreesCandidate"], .002)
        self.assertTrue(result["sampledPoseStableCandidate"])


if __name__ == "__main__":
    unittest.main()
