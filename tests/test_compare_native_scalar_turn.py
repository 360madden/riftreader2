"""Offline comparisons for exact pinned scalar samples; no VM or game required."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
from contextlib import redirect_stdout
import unittest

from scripts import compare_native_scalar_turn as turns
from scripts import fresh_native_smoothed_scalar as scalar
from scripts.sample_current_native_vitals import GAME_SHA


PID = 123
TICKS = 639298670575905950
VM = {"vmx": "lab2.vmx", "startTicks": 639298660000000000}
INSTANCE = "a" * 32


def stamp(seconds):
    return (datetime(2026, 11, 10, 11, 30, tzinfo=timezone.utc)
            + timedelta(seconds=seconds)).isoformat()


def report(current, *, factor=0.25, start=0, end=1):
    fields = (current, 1.5, 2.5, factor)
    return {"identity": {"processId": PID, "processStartUtcTicks": TICKS,
                         "executablePath": r"C:\RIFT\rift_x64.exe",
                         "executableSha256": GAME_SHA,
                         "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000},
            "startedAtUtc": stamp(start), "completedAtUtc": stamp(end),
            "playerKeyDecimal": "123", "playerEntityDecimal": "2097152",
            "componentAddressDecimal": "4194304",
            "rawBits": [struct.unpack("<I", struct.pack("<f", x))[0] for x in fields],
            "currentCandidate": fields[0], "sourceCandidate": fields[1],
            "targetCandidate": fields[2], "factorCandidate": fields[3],
            "headingQualified": False, "qualification": scalar.QUALIFICATION}


class ScalarTurnCompareTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.a = report(0.5)
        self.b = report(0.75, factor=-0.0, start=3, end=4)
        self.before = self.write("before", self.a, observed=2)
        self.after = self.write("after", self.b, observed=5)

    def write(self, label, row, *, observed):
        folder = self.root / label
        folder.mkdir(exist_ok=True)
        samples = folder / "samples.json"
        raw = (json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
               + "\n").encode()
        samples.write_bytes(raw)
        summary = {"schemaVersion": 1, "status": "candidate-only", "lab": "lab2",
                   "transport": "persistent-control-agent",
                   "vmIdentity": copy.deepcopy(VM), "gameProcessId": PID,
                   "gameProcessStartUtcTicks": TICKS, "gameSha256": GAME_SHA,
                   "activeAgentInstanceId": INSTANCE, "sourceReport": str(samples),
                   "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
                   "observedAtUtc": stamp(observed),
                   "metrics": scalar.validate_report(row, pid=PID, ticks=TICKS)}
        path = folder / "summary.json"
        path.write_text(json.dumps(summary))
        return path

    def mutate_summary(self, path, change):
        summary = json.loads(path.read_text())
        change(summary)
        path.write_text(json.dumps(summary))

    def test_candidate_delta_distinguishes_changed_float_bits_from_numeric_delta(self):
        result = turns.compare(self.before, self.after)
        self.assertEqual("candidate-only", result["status"])
        self.assertFalse(result["headingQualified"])
        self.assertEqual(2, result["changedFieldCount"])
        self.assertAlmostEqual(0.25, result["fields"]["currentCandidate"]["deltaCandidate"])
        self.assertTrue(result["fields"]["factorCandidate"]["rawBitsChanged"])
        self.assertEqual(-0.25, result["fields"]["factorCandidate"]["deltaCandidate"])
        self.assertEqual(3, result["timeBetweenCaptureEndsSeconds"])
        self.assertIn("no independently verified turn", result["limitation"])

    def test_same_epoch_requires_same_agent_player_and_component(self):
        for field, replacement in (("gameProcessStartUtcTicks", TICKS + 1),
                                   ("activeAgentInstanceId", "b" * 32),
                                   ("vmIdentity", {"vmx": "other"})):
            with self.subTest(field=field):
                self.mutate_summary(self.after, lambda data: data.__setitem__(field, replacement))
                reason = ("game-identity-mismatch" if field == "gameProcessStartUtcTicks"
                          else "process-or-controller-changed")
                try:
                    with self.assertRaisesRegex(scalar.Blocked, reason):
                        turns.compare(self.before, self.after)
                finally:
                    self.after = self.write("after", self.b, observed=5)
        original = copy.deepcopy(self.b)
        self.b["componentAddressDecimal"] = "5242880"
        self.after = self.write("after", self.b, observed=5)
        with self.assertRaisesRegex(scalar.Blocked, "player-or-component-changed"):
            turns.compare(self.before, self.after)
        self.b = original

    def test_modified_source_bytes_or_hashed_metrics_refuse_comparison(self):
        source = self.after.parent / "samples.json"
        source.write_bytes(source.read_bytes() + b" ")
        with self.assertRaisesRegex(scalar.Blocked, "source-hash-mismatch"):
            turns.compare(self.before, self.after)
        self.after = self.write("after", self.b, observed=5)
        self.mutate_summary(self.after, lambda value: value["metrics"].__setitem__("currentCandidate", 99))
        with self.assertRaisesRegex(scalar.Blocked, "summary-source-mismatch"):
            turns.compare(self.before, self.after)

    def test_wrong_sibling_path_does_not_read_external_file(self):
        self.mutate_summary(self.after, lambda value: value.__setitem__(
            "sourceReport", str(self.before.parent / "samples.json")))
        with self.assertRaisesRegex(scalar.Blocked, "source-path-invalid"):
            turns.compare(self.before, self.after)

    def test_reversed_time_or_nonfinite_values_refuse(self):
        with self.assertRaisesRegex(scalar.Blocked, "capture-order-invalid"):
            turns.compare(self.after, self.before)
        self.b["completedAtUtc"] = stamp(10)
        self.after = self.write("after", self.b, observed=5)
        with self.assertRaisesRegex(scalar.Blocked, "time-order-invalid"):
            turns.compare(self.before, self.after)
        self.b = report(0.75, start=3, end=4)
        self.b["targetCandidate"] = float("inf")
        with self.assertRaisesRegex(scalar.Blocked, "value-invalid"):
            scalar.validate_report(self.b, pid=PID, ticks=TICKS)

    def test_cli_outputs_json_only_and_failure_is_sanitized(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = turns.main(["--before", str(self.before), "--after", str(self.after)])
        self.assertEqual(0, code)
        self.assertEqual("candidate-only", json.loads(output.getvalue())["status"])
        output = io.StringIO()
        with redirect_stdout(output):
            code = turns.main(["--before", str(self.before), "--after", str(self.root / "missing")])
        self.assertEqual(2, code)
        self.assertEqual({"status": "blocked", "reason": "scalar-turn-unavailable"},
                         json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
