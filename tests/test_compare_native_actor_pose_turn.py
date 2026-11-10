"""Offline checks for comparing two actor-pose source reports after a turn."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from scripts import compare_native_actor_pose_turn as turns
from scripts import fresh_native_actor_pose as pose
from tests.test_fresh_native_actor_pose import matrix
from tests.test_sample_current_native_vitals import EXPECTED_GAME


VM = {"vmx": "lab2.vmx", "startTicks": 639298660000000000}
INSTANCE = "a" * 32
IDENTITY = [1., 0., 0., 0., 1., 0., 0., 0., 1.]


def stamp(seconds):
    return (datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
            + timedelta(seconds=seconds)).isoformat()


def rotation(degrees):
    radians = math.radians(degrees)
    return [math.cos(radians), 0., -math.sin(radians),
            0., 1., 0., math.sin(radians), 0., math.cos(radians)]


def report(degrees, *, start=0, end=1, render=True):
    oriented = rotation(degrees)
    return {
        "identity": {**EXPECTED_GAME, "executablePath": r"C:\RIFT\rift_x64.exe",
                     "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000},
        "startedAtUtc": stamp(start), "completedAtUtc": stamp(end),
        "playerKeyDecimal": "123", "playerEntityDecimal": "2097152",
        "actorComponentDecimal": "4194304", "positionComponentDecimal": "3145728",
        "actorFlags": 0 if render else 1,
        "actorMatrix": matrix(0x398, oriented, degrees),
        "modelMatrix": matrix(0x3EC, IDENTITY, 0),
        "renderMatrix": matrix(0xA0, oriented, degrees) if render else None,
        "renderStatus": ("normal-render-matrix-candidate" if render
                         else "alternate-reference-branch-not-followed"),
        "renderCompositionMaxAbsDelta": 0.0 if render else None,
        "normalRenderBranch": render,
        "actorHeadingQualified": False, "qualification": pose.QUALIFICATION,
    }


class NativePoseTurnCompareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.before_report = report(179)
        self.after_report = report(-179, start=3, end=4)
        self.before = self.write("before", self.before_report, observed=2)
        self.after = self.write("after", self.after_report, observed=5)

    def write(self, folder_name, content, *, observed):
        folder = self.root / folder_name
        folder.mkdir(exist_ok=True)
        sample = folder / "samples.json"
        raw = (json.dumps(content, sort_keys=True, separators=(",", ":"),
                          allow_nan=False) + "\n").encode()
        sample.write_bytes(raw)
        metrics = pose.validate_report(content, pid=EXPECTED_GAME["processId"],
                                       ticks=EXPECTED_GAME["processStartUtcTicks"])
        summary = {
            "schemaVersion": 1, "status": "candidate-only", "lab": "lab2",
            "transport": "persistent-control-agent", "vmIdentity": copy.deepcopy(VM),
            "gameProcessId": EXPECTED_GAME["processId"],
            "gameProcessStartUtcTicks": EXPECTED_GAME["processStartUtcTicks"],
            "gameSha256": EXPECTED_GAME["executableSha256"],
            "activeAgentInstanceId": INSTANCE, "observedAtUtc": stamp(observed),
            "sourceReport": str(sample),
            "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
            "metrics": dict(metrics, unitKey=metrics["playerKeyDecimal"]),
        }
        result = folder / "summary.json"
        result.write_text(json.dumps(summary), encoding="utf-8")
        return result

    def change_summary(self, path, edit):
        summary = json.loads(path.read_text(encoding="utf-8"))
        edit(summary)
        path.write_text(json.dumps(summary), encoding="utf-8")

    def test_wraparound_is_small_candidate_and_model_did_not_change(self):
        result = turns.compare(self.before, self.after)
        self.assertEqual("candidate-only", result["status"])
        self.assertEqual(VM, result["vmIdentity"])
        self.assertEqual(INSTANCE, result["activeAgentInstanceId"])
        self.assertEqual(EXPECTED_GAME["executableSha256"], result["gameSha256"])
        self.assertFalse(result["actorHeadingQualified"])
        self.assertEqual(2, result["changedMatrixCount"])
        self.assertEqual(3, result["timeBetweenCaptureEndsSeconds"])
        self.assertAlmostEqual(2, result["matrices"]["actorMatrix"]["deltaDegreesCandidate"])
        self.assertAlmostEqual(2, result["matrices"]["renderMatrix"]["deltaDegreesCandidate"])
        self.assertFalse(result["matrices"]["modelMatrix"]["rawBitsChanged"])
        self.assertEqual(0, result["matrices"]["modelMatrix"]["deltaDegreesCandidate"])
        self.assertIn("no independently reviewed turn", result["limitation"])

    def test_alternate_render_branch_is_reported_without_inferred_angle(self):
        after = self.write("alternate", report(-179, start=3, end=4, render=False),
                           observed=5)
        result = turns.compare(self.before, after)
        rendered = result["matrices"]["renderMatrix"]
        self.assertTrue(rendered["rawBitsChanged"])
        self.assertIsNone(rendered["afterAngleDegreesCandidate"])
        self.assertIsNone(rendered["deltaDegreesCandidate"])
        self.assertEqual("alternate-reference-branch-not-followed",
                         result["renderStatusAfter"])
        self.assertFalse(result["actorHeadingQualified"])

    def test_replay_and_overlapping_capture_windows_refused(self):
        with self.assertRaisesRegex(pose.Blocked, "identical-sources"):
            turns.compare(self.before, self.before)
        replay = self.write("replay", self.before_report, observed=2)
        with self.assertRaisesRegex(pose.Blocked, "identical-sources"):
            turns.compare(self.before, replay)
        overlapping = self.write("overlap", report(-179, start=1, end=2), observed=3)
        with self.assertRaisesRegex(pose.Blocked, "capture-order-invalid"):
            turns.compare(self.before, overlapping)
        with self.assertRaisesRegex(pose.Blocked, "capture-order-invalid"):
            turns.compare(self.after, self.before)

    def test_changed_epoch_controller_player_and_component_refused(self):
        for field, replacement in (("activeAgentInstanceId", "b" * 32),
                                   ("vmIdentity", {"vmx": "different"})):
            with self.subTest(field=field):
                self.change_summary(self.after, lambda row: row.__setitem__(field, replacement))
                try:
                    with self.assertRaisesRegex(pose.Blocked, "process-or-controller-changed"):
                        turns.compare(self.before, self.after)
                finally:
                    self.after = self.write("after", self.after_report, observed=5)
        changed_owner = copy.deepcopy(self.after_report)
        changed_owner["actorComponentDecimal"] = "5242880"
        path = self.write("other-owner", changed_owner, observed=5)
        with self.assertRaisesRegex(pose.Blocked, "player-or-component-changed"):
            turns.compare(self.before, path)

    def test_source_mutation_and_summary_mismatch_refused(self):
        sample = self.after.parent / "samples.json"
        sample.write_bytes(sample.read_bytes() + b" ")
        with self.assertRaisesRegex(pose.Blocked, "source-hash-mismatch"):
            turns.compare(self.before, self.after)
        self.after = self.write("after", self.after_report, observed=5)
        self.change_summary(self.after, lambda row: row["metrics"].__setitem__(
            "actorAngleDegreesCandidate", 0))
        with self.assertRaisesRegex(pose.Blocked, "summary-source-mismatch"):
            turns.compare(self.before, self.after)

    def test_duplicate_json_keys_rejected_in_summary_and_hashed_source(self):
        # Duplicate metadata is ambiguous even if the last parsed value fits.
        original = self.after.read_text(encoding="utf-8")
        self.assertIn('"lab": "lab2"', original)
        self.after.write_text(
            original.replace('"lab": "lab2"', '"lab": "lab1", "lab": "lab2"', 1),
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            turns.compare(self.before, self.after)

        self.after.write_text(original, encoding="utf-8")
        source = self.after.parent / "samples.json"
        payload = source.read_text(encoding="utf-8")
        self.assertIn('"actorFlags":0', payload)
        source.write_text(
            payload.replace('"actorFlags":0', '"actorFlags":1,"actorFlags":0', 1),
            encoding="utf-8")
        self.change_summary(self.after, lambda row: row.__setitem__(
            "sourceReportSha256", hashlib.sha256(source.read_bytes()).hexdigest().upper()))
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            turns.compare(self.before, self.after)

    def test_cli_json_and_generic_missing_file_failure(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(0, turns.main(["--before", str(self.before),
                                             "--after", str(self.after)]))
        self.assertEqual(2, json.loads(stream.getvalue())["changedMatrixCount"])
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(2, turns.main(["--before", str(self.before),
                                             "--after", str(self.root / "missing")]))
        self.assertEqual({"status": "blocked", "reason": "pose-turn-unavailable"},
                         json.loads(stream.getvalue()))


if __name__ == "__main__":
    unittest.main()
