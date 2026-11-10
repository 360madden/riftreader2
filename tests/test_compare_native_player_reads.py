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
from unittest.mock import patch

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
    elif field == "actor-pose":
        metrics.update({"actorAngleDegreesCandidate": 45.0, "actorHeadingQualified": False})
    elif field == "smoothed-scalar":
        metrics.update({"currentCandidate": 0.5, "headingQualified": False})
    else:
        def metric(value):
            return {"status": "calculated-candidate", "current": value, "maximum": 100}
        metrics.update({"health": metric(100), "energy": metric(90),
                        "mana": {"status": "unavailable", "current": None, "maximum": None}})
    detail = Path.cwd() / "artifacts" / (field + "-test")
    detail_paths = ({"sourceReport": str(detail / "samples.json"),
                     "summaryPath": str(detail / "summary.json")}
                    if field in ("actor-pose", "smoothed-scalar") else {})
    return {
        **detail_paths,
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
    for field in ("actor-pose", "smoothed-scalar"):
        if field in fields:
            folder = Path.cwd() / "artifacts" / (field + "-test-after")
            after[field].update(sourceReport=str(folder / "samples.json"),
                                summaryPath=str(folder / "summary.json"))
    return before, after


def compare(a=None, b=None):
    orig_a, orig_b = pair()
    return tool.compare(a if a is not None else orig_a,
                        b if b is not None else orig_b, "C" * 64, "D" * 64)


class CompareNativePlayerReadsTests(unittest.TestCase):
    def lab1_pair(self, fields=("position",)):
        before, after = pair(fields)
        for readout in (before, after):
            readout["targetId"] = "lab1"
            for field in fields:
                readout[field]["lab"] = "lab1"
        return before, after

    def test_lab1_position_before_after_is_comparable(self):
        first, second = self.lab1_pair()
        result = compare(first, second)
        self.assertEqual(result["targetId"], "lab1")
        self.assertEqual(result["fieldsCompared"], ["position"])
        self.assertEqual(result["comparison"]["position"]["deltaCandidate"],
                         {"x": 3.0, "y": 4.0, "z": 12.0})
        self.assertEqual(result["status"], "candidate-only")

    def test_lab1_pose_scalar_join_require_matching_lab(self):
        first, second = self.lab1_pair(("position", "actor-pose", "smoothed-scalar"))
        pose, scalar = self.pose_result(), self.scalar_result()
        pose["lab"] = scalar["lab"] = "lab1"
        with patch.object(tool, "compare_pose_turn", return_value=pose), \
             patch.object(tool, "compare_scalar_turn", return_value=scalar):
            result = compare(first, second)
        self.assertIs(result["comparison"]["actor-pose"], pose)
        self.assertIs(result["comparison"]["smoothed-scalar"], scalar)
        self.assertEqual(result["targetId"], "lab1")
        pose["lab"] = "lab2"
        with patch.object(tool, "compare_pose_turn", return_value=pose), \
             self.assertRaisesRegex(ValueError, "pose-identity-mismatch"):
            compare(first, second)

    def test_mixed_lab_readouts_and_lab1_vitals_are_rejected(self):
        first, second = self.lab1_pair()
        second["targetId"] = "lab2"
        second["position"]["lab"] = "lab2"
        with self.assertRaisesRegex(ValueError, "target-changed"):
            compare(first, second)
        first, second = self.lab1_pair()
        first["position"]["lab"] = "lab2"
        with self.assertRaisesRegex(ValueError, "source-invalid"):
            compare(first, second)
        first, second = self.lab1_pair(("position", "vitals"))
        with self.assertRaisesRegex(ValueError, "lab1-vitals-not-supported"):
            compare(first, second)

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
        self.assertAlmostEqual(position["xzTravelAngleDegreesCandidate"], 75.96375653207352)
        self.assertEqual(result["comparison"]["vitals"]["health"]["deltaCurrentCandidate"], -15)
        self.assertIsNone(result["comparison"]["vitals"]["mana"]["deltaCurrentCandidate"])
        self.assertIn("NOT movement proof", result["qualification"])
        self.assertEqual((first, second), original)

    def test_xz_travel_vector_angle_is_not_actor_facing(self):
        for dx, dz, expected in ((2, 0, 0), (0, 2, 90),
                                 (-2, 0, 180), (0, -2, -90),
                                 (2, 2, 45), (0, 0, None)):
            before, after = pair(("position",))
            current = before["position"]["metrics"]
            after["position"]["metrics"]["x"] = current["x"] + dx
            after["position"]["metrics"]["z"] = current["z"] + dz
            after["position"]["metrics"]["y"] = current["y"]
            candidate = tool.compare(before, after, "C" * 64, "D" * 64)["comparison"]["position"]
            angle = candidate["xzTravelAngleDegreesCandidate"]
            with self.subTest(dx=dx, dz=dz):
                if expected is None:
                    self.assertIsNone(angle)
                else:
                    self.assertAlmostEqual(expected, angle)
                self.assertEqual("same-owner-displacement-candidate", candidate["status"])

    def pose_result(self):
        return {"status": "candidate-only", "lab": "lab2", "vmIdentity": copy.deepcopy(VM),
                "gameProcessId": 10876, "gameProcessStartUtcTicks": 639297512883473394,
                "gameSha256": SHA,
                "activeAgentInstanceId": AGENT, "playerKeyDecimal": UNIT,
                "beforeSourceSha256": "A" * 64, "afterSourceSha256": "B" * 64,
                "matrices": {"actorMatrix": {"deltaDegreesCandidate": 2.0}},
                "actorHeadingQualified": False}

    def test_pose_and_displacement_join_saved_candidates(self):
        first, second = pair(("position", "actor-pose"))
        pose = self.pose_result()
        with patch.object(tool, "compare_pose_turn", return_value=pose) as joined:
            result = compare(first, second)
        self.assertEqual(["position", "actor-pose"], result["fieldsCompared"])
        self.assertAlmostEqual(75.96375653207352,
                               result["comparison"]["position"]["xzTravelAngleDegreesCandidate"])
        self.assertIs(result["comparison"]["actor-pose"], pose)
        self.assertFalse(result["comparison"]["actor-pose"]["actorHeadingQualified"])
        joined.assert_called_once_with(Path(first["actor-pose"]["summaryPath"]),
                                       Path(second["actor-pose"]["summaryPath"]))

    def test_pose_join_rejects_source_identity_and_path_mismatch(self):
        first, second = pair(("position", "actor-pose"))
        first["actor-pose"]["sourceReport"] = str(Path.cwd() / "wrong.json")
        with patch.object(tool, "compare_pose_turn") as joined, self.assertRaisesRegex(
                ValueError, "pose-source-path-invalid"):
            compare(first, second)
        joined.assert_not_called()
        for field, replacement, reason in (
                ("beforeSourceSha256", "F" * 64, "pose-source-hash-mismatch"),
                ("activeAgentInstanceId", "b" * 32, "pose-identity-mismatch"),
                ("gameSha256", "F" * 64, "pose-identity-mismatch")):
            first, second = pair(("position", "actor-pose"))
            pose = self.pose_result()
            pose[field] = replacement
            with self.subTest(field=field), patch.object(
                    tool, "compare_pose_turn", return_value=pose), self.assertRaisesRegex(
                        ValueError, reason):
                compare(first, second)
        first, second = pair(("position", "actor-pose"))
        with patch.object(tool, "compare_pose_turn",
                          side_effect=tool.Blocked("pose-turn-source-hash-mismatch")), \
                self.assertRaisesRegex(ValueError, "pose-source-invalid"):
            compare(first, second)

    def test_real_saved_pose_reports_join_position_displacement(self):
        from scripts import fresh_native_actor_pose as pose_client
        from tests.test_compare_native_actor_pose_turn import (
            report as actor_report, stamp as actor_stamp, VM as actor_vm)
        from tests.test_sample_current_native_vitals import EXPECTED_GAME

        with TemporaryDirectory() as temporary:
            before, after = pair(("position", "actor-pose"))
            for index, (readout, actor, observed) in enumerate((
                    (before, actor_report(179), 2),
                    (after, actor_report(-179, start=3, end=4), 5))):
                folder = Path(temporary) / str(index)
                folder.mkdir()
                source = folder / "samples.json"
                raw = (json.dumps(actor, sort_keys=True, separators=(",", ":")) + "\n").encode()
                source.write_bytes(raw)
                source_hash = hashlib.sha256(raw).hexdigest().upper()
                metrics = pose_client.validate_report(
                    actor, pid=EXPECTED_GAME["processId"],
                    ticks=EXPECTED_GAME["processStartUtcTicks"])
                summary = {"schemaVersion": 1, "status": "candidate-only", "lab": "lab2",
                           "transport": "persistent-control-agent",
                           "vmIdentity": copy.deepcopy(actor_vm),
                           "gameProcessId": EXPECTED_GAME["processId"],
                           "gameProcessStartUtcTicks": EXPECTED_GAME["processStartUtcTicks"],
                           "gameSha256": EXPECTED_GAME["executableSha256"],
                           "activeAgentInstanceId": AGENT,
                           "observedAtUtc": actor_stamp(observed),
                           "sourceReport": str(source),
                           "sourceReportSha256": source_hash,
                           "metrics": dict(metrics, unitKey="123")}
                summary_path = folder / "summary.json"
                summary_path.write_text(json.dumps(summary), encoding="utf-8")
                readout["unitKey"] = "123"
                for field in ("position", "actor-pose"):
                    row = readout[field]
                    row.update(vmIdentity=copy.deepcopy(actor_vm),
                               gameProcessId=EXPECTED_GAME["processId"],
                               gameProcessStartUtcTicks=EXPECTED_GAME["processStartUtcTicks"],
                               gameSha256=EXPECTED_GAME["executableSha256"],
                               observedAtUtc=actor_stamp(observed))
                    row["metrics"]["unitKey"] = "123"
                readout["actor-pose"].update(
                    sourceReport=str(source), summaryPath=str(summary_path),
                    sourceReportSha256=source_hash)
            result = compare(before, after)
            self.assertEqual(["position", "actor-pose"], result["fieldsCompared"])
            self.assertAlmostEqual(
                2., result["comparison"]["actor-pose"]["matrices"][
                    "actorMatrix"]["deltaDegreesCandidate"])
            self.assertAlmostEqual(
                75.96375653207352,
                result["comparison"]["position"]["xzTravelAngleDegreesCandidate"])
            self.assertFalse(result["comparison"]["actor-pose"]["actorHeadingQualified"])

    def scalar_result(self):
        return {"status": "candidate-only", "lab": "lab2", "vmIdentity": copy.deepcopy(VM),
                "gameProcessId": 10876, "gameProcessStartUtcTicks": 639297512883473394,
                "gameSha256": SHA, "activeAgentInstanceId": AGENT,
                "playerKeyDecimal": UNIT, "beforeSourceSha256": "A" * 64,
                "afterSourceSha256": "B" * 64, "changedFieldCount": 1,
                "fields": {"currentCandidate": {"deltaCandidate": 0.25}},
                "headingQualified": False}

    def test_position_pose_and_scalar_join_same_readouts(self):
        first, second = pair(("position", "actor-pose", "smoothed-scalar"))
        scalar = self.scalar_result()
        with patch.object(tool, "compare_pose_turn", return_value=self.pose_result()), \
                patch.object(tool, "compare_scalar_turn", return_value=scalar) as joined:
            result = compare(first, second)
        self.assertEqual(["position", "actor-pose", "smoothed-scalar"],
                         result["fieldsCompared"])
        self.assertAlmostEqual(75.96375653207352,
                               result["comparison"]["position"]["xzTravelAngleDegreesCandidate"])
        self.assertEqual(2.0, result["comparison"]["actor-pose"]["matrices"][
            "actorMatrix"]["deltaDegreesCandidate"])
        self.assertIs(scalar, result["comparison"]["smoothed-scalar"])
        self.assertFalse(scalar["headingQualified"])
        joined.assert_called_once_with(Path(first["smoothed-scalar"]["summaryPath"]),
                                       Path(second["smoothed-scalar"]["summaryPath"]))

    def test_scalar_join_refuses_wrong_source_and_identity(self):
        first, second = pair(("position", "smoothed-scalar"))
        first["smoothed-scalar"]["summaryPath"] = "relative/summary.json"
        with patch.object(tool, "compare_scalar_turn") as joined, \
                self.assertRaisesRegex(ValueError, "scalar-source-path-invalid"):
            compare(first, second)
        joined.assert_not_called()
        for field, replacement, reason in (
                ("beforeSourceSha256", "F" * 64, "scalar-source-hash-mismatch"),
                ("gameSha256", "F" * 64, "scalar-identity-mismatch"),
                ("activeAgentInstanceId", "b" * 32, "scalar-identity-mismatch")):
            first, second = pair(("position", "smoothed-scalar"))
            scalar = self.scalar_result()
            scalar[field] = replacement
            with self.subTest(field=field), patch.object(
                    tool, "compare_scalar_turn", return_value=scalar), self.assertRaisesRegex(
                        ValueError, reason):
                compare(first, second)
        first, second = pair(("position", "smoothed-scalar"))
        with patch.object(tool, "compare_scalar_turn",
                          side_effect=tool.Blocked("scalar-turn-source-hash-mismatch")), \
                self.assertRaisesRegex(ValueError, "scalar-source-invalid"):
            compare(first, second)

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
        unavailable = compare(first, second)["comparison"]["position"]
        self.assertEqual(unavailable["status"], "unavailable-xyz")
        self.assertIsNone(unavailable["xzTravelAngleDegreesCandidate"])
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
