"""Synthetic retained-orientation comparison tests; no game access."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

from scripts import summarize_native_orientation_track as s


def matrix(degrees, offset):
    theta = math.radians(degrees)
    c, si = math.cos(theta), math.sin(theta)
    values = [c, 0, -si, 0, 1, 0, si, 0, c]
    values = [struct.unpack("<f", struct.pack("<f", v))[0] for v in values]
    bits = [struct.unpack("<I", struct.pack("<f", v))[0] for v in values]
    angle = math.degrees(math.atan2(values[6], values[0]))
    return {"sourceOffset": offset, "rawBits": bits,
            "rowMajorF32": values, "status": s.STRUCTURAL,
            "planarAngleDegreesCandidate": angle}


def report(start, completed, angle=0, *, pid=123, ticks=639296903905448486,
           key="18446744073709551615", component=268435456):
    return {"schemaVersion": 1, "contractVersion": s.CONTRACT, "status": "complete",
            "observation": {
                "identity": {"processId": pid, "processStartUtcTicks": ticks,
                             "executableSha256": s.GAME_SHA, "processName": "rift_x64.exe",
                             "moduleBaseAddress": 0x140000000, "moduleSize": 67108864},
                "startedAtUtc": start, "completedAtUtc": completed,
                "unitKey": key, "componentAddress": component,
                "refreshHandleRaw": "0x0000000000000000", "refreshFlagRaw": 0,
                "primary": matrix(angle, 0x60), "secondary": matrix(angle, 0x94),
                "qualification": s.QUALIFICATION}}


class OrientationTrackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def save(self, index, value):
        path = self.directory / f"report-{index}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def pair(self, angle1=0, angle2=0):
        return (
            self.save(1, report("2026-11-08T01:00:00Z", "2026-11-08T01:00:00.1Z", angle1)),
            self.save(2, report("2026-11-08T01:00:01Z", "2026-11-08T01:00:01.1Z", angle2)),
        )

    def test_equal_matrix_is_not_claimed_fresh_or_facing(self):
        value = s.compare(self.pair())
        self.assertEqual(value["status"], "candidate-only")
        self.assertEqual(value["acceptedPairCount"], 1)
        self.assertEqual(value["primaryRawChangedPairs"], 0)
        self.assertEqual(value["secondaryRawChangedPairs"], 0)
        self.assertTrue(value["pairs"][0]["primary"]["rawBitsEqual"])
        self.assertAlmostEqual(value["pairs"][0]["primary"]["candidateMatrixAngleDeltaDegrees"], 0)
        self.assertEqual(value["freshness"], "unavailable-offline")
        self.assertEqual(value["facing"], "unqualified")
        self.assertEqual(value["worldIdentity"], "unavailable-in-source")
        self.assertIsInstance(value["processIdentity"]["processStartUtcTicks"], str)
        self.assertEqual(value["sampledUnitKey"], "18446744073709551615")
        self.assertEqual(len(value["sources"][0]["sha256"]), 64)

    def test_matrix_angle_wrap_and_branch_input_change(self):
        a, b = self.pair(170, -170)
        obj = json.loads(b.read_text(encoding="utf-8"))
        obj["observation"]["refreshFlagRaw"] = 1
        b.write_text(json.dumps(obj), encoding="utf-8")
        value = s.compare((a, b))
        self.assertEqual(value["primaryRawChangedPairs"], 1)
        self.assertEqual(value["secondaryRawChangedPairs"], 1)
        pair = value["pairs"][0]
        self.assertTrue(pair["refreshInputsChanged"])
        self.assertIs(pair["primary"]["rawBitsEqual"], False)
        self.assertAlmostEqual(pair["primary"]["candidateMatrixAngleDeltaDegrees"], 20, places=4)
        self.assertIn("NOT player body facing", value["limitations"][1])

    def test_boundary_withholds_pair_deltas(self):
        a, b = self.pair(0, 90)
        limited = s.compare((a, b), max_gap_seconds=0.5)
        self.assertEqual(limited["acceptedPairCount"], 0)
        self.assertEqual(limited["pairs"][0]["status"], "boundary-time-gap")
        self.assertIsNone(limited["pairs"][0]["primary"]["rawBitsEqual"])
        obj = json.loads(b.read_text(encoding="utf-8"))
        obj["observation"]["componentAddress"] += 32
        b.write_text(json.dumps(obj), encoding="utf-8")
        changed = s.compare((a, b), max_gap_seconds=3)
        self.assertEqual(changed["pairs"][0]["status"], "boundary-component-changed")
        self.assertIsNone(changed["pairs"][0]["primary"]["candidateMatrixAngleDeltaDegrees"])

    def test_process_owner_and_order_changes_fail_closed(self):
        a, b = self.pair()
        original = json.loads(b.read_text(encoding="utf-8"))
        for mutate in (
            lambda o: o["observation"]["identity"].update(processId=456),
            lambda o: o["observation"]["identity"].update(processStartUtcTicks=639296903905448487),
            lambda o: o["observation"]["identity"].update(executableSha256="F" * 64),
            lambda o: o["observation"]["identity"].update(moduleBaseAddress=0x150000000),
            lambda o: o["observation"]["identity"].update(moduleSize=33554432),
            lambda o: o["observation"].update(unitKey="1"),
            lambda o: o["observation"].update(startedAtUtc="2026-11-08T01:00:00.05Z"),
            lambda o: o["observation"].update(startedAtUtc="2026-11-07T20:00:01-05:00"),
        ):
            candidate = deepcopy(original)
            mutate(candidate)
            b.write_text(json.dumps(candidate), encoding="utf-8")
            with self.subTest(candidate=candidate["observation"]), self.assertRaises(ValueError):
                s.compare((a, b))

    def test_bad_matrix_fields_and_qualification_rejected(self):
        a, b = self.pair()
        original = json.loads(b.read_text(encoding="utf-8"))
        for mutate in (
            lambda o: o["observation"]["primary"]["rawBits"].__setitem__(0, -1),
            lambda o: o["observation"]["primary"]["rawBits"].__setitem__(0, 0),
            lambda o: o["observation"]["primary"].update(planarAngleDegreesCandidate=92),
            lambda o: o["observation"]["primary"].update(status="player-heading"),
            lambda o: o["observation"]["secondary"].update(sourceOffset=96),
            lambda o: o["observation"].update(qualification="qualified-player-facing"),
            lambda o: o["observation"].update(refreshFlagRaw=True),
            lambda o: o["observation"].update(unitKey="018446744073709551615"),
        ):
            candidate = deepcopy(original)
            mutate(candidate)
            b.write_text(json.dumps(candidate), encoding="utf-8")
            with self.subTest(mutate=str(mutate)), self.assertRaises(ValueError):
                s.compare((a, b))

    def test_nonfinite_matrix_never_becomes_angle(self):
        a, b = self.pair()
        obj = json.loads(b.read_text(encoding="utf-8"))
        primary = obj["observation"]["primary"]
        primary["rawBits"][0] = 0x7F800000
        primary.update(rowMajorF32=None, status="nonfinite-matrix", planarAngleDegreesCandidate=None)
        b.write_text(json.dumps(obj), encoding="utf-8")
        result = s.compare((a, b))
        self.assertEqual(result["primaryRawChangedPairs"], 1)
        self.assertIsNone(result["pairs"][0]["primary"]["candidateMatrixAngleDeltaDegrees"])

    def test_cli_bytes_sha_and_reject_duplicate_json(self):
        a, b = self.pair()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(s.main([str(a), str(b)]), 0)
        value = json.loads(out.getvalue())
        self.assertEqual(value["sources"][0]["sha256"], __import__("hashlib").sha256(a.read_bytes()).hexdigest().upper())
        b.write_text('{"status":"complete","status":"complete"}', encoding="utf-8")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(s.main([str(a), str(b)]), 2)

    def test_argument_bounds(self):
        a, b = self.pair()
        for files, gap in (([a], 5), ([a, b], 0), ([a, b], 301), ([a, b], float("nan"))):
            with self.subTest(files=files, gap=gap), self.assertRaises(ValueError):
                s.compare(files, max_gap_seconds=gap)


if __name__ == "__main__":
    unittest.main()
