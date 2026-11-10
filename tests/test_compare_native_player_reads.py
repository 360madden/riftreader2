"""Offline native Lab2 player-read comparison tests: no game/controller operations."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts import compare_native_player_reads as tool

UNIT = "18446744073709551615"
SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
VM = {"vmx": "c:/lab2.vmx", "pid": 14, "startTicks": 141}
AGENT = "a" * 32


def source(field, *, at="2026-11-09T17:00:00Z", report_sha="A" * 64):
    metrics = {"unitKey": UNIT}
    if field == "position":
        metrics.update({"x": 10.0, "y": 20.0, "z": 30.0,
                        "ownerIdentityStatus": "player-component-chain-anchored",
                        "freshness": "unqualified"})
    else:
        def metric(value):
            return {"status": "calculated-candidate", "current": value, "maximum": 100}
        metrics.update({"health": metric(100), "energy": metric(90),
                        "mana": {"status": "unavailable", "current": None, "maximum": None}})
    return {
        "schemaVersion": 1, "status": "candidate-only", "lab": "lab2",
        "transport": "persistent-control-agent",
        "vmIdentity": copy.deepcopy(VM), "gameProcessId": 10876,
        "gameProcessStartUtcTicks": 639297512883473394,
        "gameSha256": SHA,
        "activeAgentInstanceId": AGENT, "observedAtUtc": at,
        "sourceReportSha256": report_sha, "metrics": metrics,
    }


def readout(fields=("position", "vitals"), *, at="2026-11-09T17:00:00Z",
            report_sha="A" * 64):
    root = {
        "schemaVersion": 1, "status": "candidate-only", "targetId": "lab2",
        "ownerHost": "AMD-DESKTOP", "mode": "native-read-only", "atomic": False,
        "luaReaderUsed": False, "screenshotUsed": False, "unitKey": UNIT,
    }
    root.update({f: source(f, at=at, report_sha=report_sha) for f in fields})
    return root


def pair(fields=("position", "vitals")):
    before = readout(fields)
    after = readout(fields, at="2026-11-09T17:00:10Z", report_sha="B" * 64)
    if "position" in fields:
        after["position"]["metrics"].update(x=13.0, y=24.0, z=42.0)
    if "vitals" in fields:
        after["vitals"]["metrics"]["health"]["current"] = 85
        after["vitals"]["metrics"]["energy"]["current"] = 80
    return before, after


def compare(a=None, b=None):
    orig_a, orig_b = pair()
    return tool.compare(a if a is not None else orig_a,
                        b if b is not None else orig_b, "C" * 64, "D" * 64)


class CompareNativePlayerReadsTests(unittest.TestCase):
    def test_combined_candidate_xyz_and_vitals(self):
        first, second = pair()
        original = copy.deepcopy((first, second))
        result = compare(first, second)
        self.assertEqual(result["fieldsCompared"], ["position", "vitals"])
        position = result["comparison"]["position"]
        self.assertEqual(position["status"], "same-owner-displacement-candidate")
        self.assertEqual(position["deltaCandidate"], {"x": 3.0, "y": 4.0, "z": 12.0})
        self.assertAlmostEqual(position["distance3dCandidate"], 13.0)
        self.assertAlmostEqual(position["horizontalXZDistanceCandidate"], (153) ** .5)
        self.assertEqual(result["comparison"]["vitals"]["health"]["deltaCurrentCandidate"], -15)
        self.assertIsNone(result["comparison"]["vitals"]["mana"]["deltaCurrentCandidate"])
        self.assertIn("NOT movement proof", result["qualification"])
        self.assertEqual((first, second), original)

    def test_selective_position_and_vitals_only(self):
        for fields, key in ((("position",), "position"), (("vitals",), "vitals")):
            with self.subTest(fields=fields):
                first, second = pair(fields)
                out = compare(first, second)
                self.assertEqual(list(out["comparison"]), [key])
                self.assertEqual(out["fieldsCompared"], list(fields))

    def test_mismatched_selective_fields_fail_no_fake_pair(self):
        first = readout(("position",))
        second = readout(("vitals",), at="2026-11-09T17:00:10Z", report_sha="B" * 64)
        with self.assertRaisesRegex(ValueError, "field-selection-mismatch"):
            compare(first, second)

    def test_changed_owner_or_vm_or_build_or_unit_fail(self):
        for field, val in (
            ("activeAgentInstanceId", "b" * 32),
            ("gameProcessId", 10877),
            ("gameProcessStartUtcTicks", 639297512883473395),
            ("gameSha256", "F" * 64),
            ("vmIdentity", {"vmx": "c:/other.vmx", "pid": 14, "startTicks": 141}),
        ):
            first, second = pair()
            second["position"][field] = val
            second["vitals"][field] = val
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "process-vm-or-agent-changed"):
                compare(first, second)

        first, second = pair()
        second["unitKey"] = "18446744073709551614"
        second["position"]["metrics"]["unitKey"] = second["unitKey"]
        second["vitals"]["metrics"]["unitKey"] = second["unitKey"]
        with self.assertRaisesRegex(ValueError, "unit-changed"):
            compare(first, second)

    def test_inconsistent_sources_in_one_bundle_fail(self):
        first, second = pair()
        second["vitals"]["gameProcessId"] += 1
        with self.assertRaisesRegex(ValueError, "mixed-source-identity"):
            compare(first, second)

    def test_repeated_source_report_and_nonadvancing_times_fail(self):
        first, second = pair()
        second["position"]["sourceReportSha256"] = "A" * 64
        with self.assertRaisesRegex(ValueError, "reused-position-report"):
            compare(first, second)

        first, second = pair()
        second["position"]["observedAtUtc"] = first["position"]["observedAtUtc"]
        with self.assertRaisesRegex(ValueError, "nonadvancing-position"):
            compare(first, second)

        with self.assertRaisesRegex(ValueError, "identical-source"):
            tool.compare(first, second, "F" * 64, "f" * 64)

    def test_invalid_boolean_or_float_unit_never_promotes_large_integer(self):
        for unit in (True, 5.5, -1, "01", "18446744073709551616", 100):
            first, second = pair()
            first["unitKey"] = unit
            with self.subTest(unit=unit), self.assertRaisesRegex(ValueError, "unit-key-invalid"):
                compare(first, second)

    def test_nonfinite_missing_and_unanchored_position_withheld(self):
        first, second = pair()
        second["position"]["metrics"]["x"] = 1e308
        first["position"]["metrics"]["x"] = -1e308
        self.assertEqual(compare(first, second)["comparison"]["position"]["status"],
                         "unavailable-overflow")
        first, second = pair()
        second["position"]["metrics"]["x"] = None
        self.assertEqual(compare(first, second)["comparison"]["position"]["status"],
                         "unavailable-xyz")
        first, second = pair()
        second["position"]["metrics"]["ownerIdentityStatus"] = "unknown"
        self.assertEqual(compare(first, second)["comparison"]["position"]["status"],
                         "unavailable-owner-anchor")

    def test_unavailable_resource_is_not_zero_or_a_change(self):
        first, second = pair()
        second["vitals"]["metrics"]["health"] = {
            "status": "unavailable", "current": None, "maximum": None,
            "unavailableReason": "not-readable"
        }
        result = compare(first, second)["comparison"]["vitals"]["health"]
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["deltaCurrentCandidate"])
        self.assertIsNone(result["afterCandidate"])

    def test_cli_hashes_exact_file_bytes_and_no_overwrite(self):
        before, after = pair()
        with TemporaryDirectory() as folder:
            a, b = Path(folder) / "before.json", Path(folder) / "after.json"
            a.write_text(json.dumps(before), encoding="utf-8")
            b.write_text(json.dumps(after), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = tool.main(["--before", str(a), "--after", str(b)])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["beforeSourceSha256"], hashlib.sha256(a.read_bytes()).hexdigest().upper())
            self.assertEqual(result["afterSourceSha256"], hashlib.sha256(b.read_bytes()).hexdigest().upper())
            self.assertEqual(result["unitKey"], UNIT)
            self.assertEqual(json.loads(a.read_bytes()), before)

    def test_bad_report_returns_sanitized_block_without_input(self):
        with TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.json", Path(folder) / "b.json"
            a.write_text("{}", encoding="utf-8")
            b.write_text("not json", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = tool.main(["--before", str(a), "--after", str(b)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out.getvalue()),
                             {"status": "blocked", "reason": "native-player-compare-unavailable"})

    def test_cli_direct_entrypoint(self):
        result = subprocess.run([sys.executable, str(Path(tool.__file__).resolve()), "--help"],
                                cwd=Path(tool.__file__).resolve().parents[1],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
