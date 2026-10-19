"""Fail-closed, offline tests for targeted health snapshot request preparation."""

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_native_field_evidence import (
    ROOT_RVA, _duplicate_health_group, _new_health_epoch, health_fixture,
    evidence,
)

FILE = Path(__file__).parents[1] / "scripts" / "plan-targeted-health-snapshot.py"
SPEC = importlib.util.spec_from_file_location("targeted_health_snapshot", FILE)
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class TargetedHealthPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        first = health_fixture()
        second = _new_health_epoch(first)
        _duplicate_health_group(first)
        _duplicate_health_group(second)
        self.old = first
        self.new = second
        self.previous = self.folder / "previous.json"
        self.report = self.folder / "health.json"
        self.cross = self.folder / "cross.json"
        self.receipt = self.folder / "receipt.json"
        self.now = datetime(2026, 10, 19, 9, 15, 0, tzinfo=timezone.utc)
        self._write_fixtures()

    def _write_fixtures(self):
        self.previous.write_text(json.dumps(self.old), encoding="utf-8")
        self.report.write_text(json.dumps(self.new), encoding="utf-8")
        comparison = evidence.compare_health_structures(
            [self.previous, self.report], ROOT_RVA, 45,
        )
        self.cross.write_text(json.dumps(comparison), encoding="utf-8")
        base = copy.deepcopy(self.new["referenceBefore"])
        base["riftProcessCount"] = 1
        self.receipt.write_text(json.dumps({
            "receivedAtUtc": (self.now - timedelta(milliseconds=300)).isoformat(),
            "observation": base,
        }), encoding="utf-8")

    def prepare(self, **overrides):
        opts = {
            "root_rva": ROOT_RVA, "level_hint": 45,
            "now_utc": self.now,
            "max_candidates": 8,
        }
        opts.update(overrides)
        return planner.prepare(self.report, self.cross, self.receipt, **opts)

    def test_two_source_report_marker_copies_create_bound_160_byte_request(self):
        request, manifest, receipt = self.prepare()
        self.assertEqual(request["evidenceKind"], "native-memory-snapshot-request/1")
        self.assertEqual(request["target"]["processId"], 8356)
        self.assertEqual(request["target"]["processStartUtcTicks"], 639279978665141458)
        self.assertEqual(len(request["ranges"]), 2)
        self.assertEqual(manifest["totalRequestedBytes"], 160)
        self.assertEqual(manifest["selectedCount"], 2)
        self.assertEqual(manifest["qualification"], "candidate-only")
        self.assertEqual(
            manifest["source"]["liveReceiptSha256"],
            hashlib.sha256(receipt).hexdigest().upper(),
        )
        self.assertEqual(manifest["typed"]["currentValues"]["health"], 18208)
        for item in request["ranges"]:
            self.assertEqual(item["byteLength"], 80)
            self.assertEqual(item["addressKind"], "absolute-session-address")
        for item in manifest["selections"]:
            self.assertEqual(
                [x["byteOffset"] for x in item["markerPositions"]],
                [16, 24, 32, 56],
            )

    def test_limit_reduces_to_one_group_not_a_wider_scan(self):
        request, manifest, _ = self.prepare(max_candidates=1)
        self.assertEqual(len(request["ranges"]), 1)
        self.assertEqual(manifest["totalRequestedBytes"], 80)

    def test_received_at_z_and_utc_offset_are_both_supported(self):
        request, manifest, _ = self.prepare()
        d = json.loads(self.receipt.read_bytes())
        d["receivedAtUtc"] = d["receivedAtUtc"].replace("+00:00", "Z")
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        second, newer, _ = self.prepare()
        self.assertEqual(request, second)
        self.assertEqual(
            manifest["selectedPatternSha256"], newer["selectedPatternSha256"]
        )

    def test_non_utc_timezone_is_rejected(self):
        d = json.loads(self.receipt.read_bytes())
        d["receivedAtUtc"] = "2026-10-19T05:14:59.700000-04:00"
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "UTC"):
            self.prepare()

    def test_stale_receipt_is_not_accepted(self):
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "stale"):
            self.prepare(now_utc=self.now + timedelta(seconds=10))

    def test_future_receipt_is_not_accepted(self):
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "future"):
            self.prepare(now_utc=self.now - timedelta(seconds=10))

    def test_wrong_game_pid_is_rejected(self):
        d = json.loads(self.receipt.read_bytes())
        d["observation"]["target"]["processId"] += 1
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "PID/start/build"):
            self.prepare()

    def test_wrong_game_start_is_rejected_even_with_correct_pid(self):
        d = json.loads(self.receipt.read_bytes())
        d["observation"]["target"]["processStartUtc"] = (
            "2026-10-19T04:35:29.3755454Z"
        )
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "PID/start/build"):
            self.prepare()

    def test_mismatched_build_rejected(self):
        d = json.loads(self.receipt.read_bytes())
        d["observation"]["target"]["executableSha256"] = "B" * 64
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "PID/start/build"):
            self.prepare()

    def test_different_player_rejected(self):
        d = json.loads(self.receipt.read_bytes())
        d["observation"]["readback"]["typedApi"]["snapshot"]["player"]["unitId"] = "other-player"
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "player identity"):
            self.prepare()

    def test_stale_readback_rejected(self):
        d = json.loads(self.receipt.read_bytes())
        d["observation"]["readback"]["typedApi"]["status"] = "stale"
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "freshness"):
            self.prepare()

    def test_changed_live_health_is_recorded_without_field_promotion(self):
        d = json.loads(self.receipt.read_bytes())
        d["observation"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]["health"]["value"] = 17000
        self.receipt.write_text(json.dumps(d), encoding="utf-8")
        _, manifest, _ = self.prepare()
        self.assertEqual(manifest["typed"]["currentValues"]["health"], 17000)
        self.assertEqual(manifest["typed"]["sourceHealthValues"]["health"], 18208)
        self.assertEqual(manifest["qualification"], "candidate-only")

    def test_wrong_cross_epoch_source_hash_rejected(self):
        d = json.loads(self.cross.read_bytes())
        d["sourceReports"][1]["reportSha256"] = "F" * 64
        self.cross.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "current source"):
            self.prepare()

    def test_missing_cross_epoch_pattern_rejected(self):
        d = json.loads(self.cross.read_bytes())
        d["sharedMarkerPatterns"] = []
        self.cross.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "exactly one shared"):
            self.prepare()

    def test_unreplicated_pattern_rejected(self):
        d = json.loads(self.cross.read_bytes())
        d["sharedMarkerPatterns"][0]["replicatedInEitherEpoch"] = False
        self.cross.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "replicated"):
            self.prepare()

    def test_missing_local_hit_context_bytes_rejected(self):
        d = json.loads(self.report.read_bytes())
        d["healthScan"]["hits"][0]["sha256"] = "0" * 64
        self.report.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "SHA-256"):
            self.prepare()

    def test_duplicate_source_json_properties_rejected(self):
        self.receipt.write_bytes(b'{"observation":{},"observation":{}}')
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "duplicate JSON"):
            self.prepare()

    def test_invalid_candidate_limits_rejected(self):
        for val in (0, -1, 17, True):
            with self.subTest(value=val):
                with self.assertRaisesRegex(planner.evidence.EvidenceError, "candidate count"):
                    self.prepare(max_candidates=val)

    def test_atomic_publication_three_new_files_and_no_overwrite(self):
        request, manifest, raw_receipt = self.prepare()
        paths = [self.folder / f"{n}.json" for n in ("request", "manifest", "pinned")]
        payloads = [
            (paths[0], (json.dumps(request) + "\n").encode()),
            (paths[1], (json.dumps(manifest) + "\n").encode()),
            (paths[2], raw_receipt),
        ]
        planner._publish_atomic_new(payloads)
        original = [path.read_bytes() for path in paths]
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "already exists"):
            planner._publish_atomic_new(payloads)
        self.assertEqual([p.read_bytes() for p in paths], original)

    def test_publication_failure_preserves_preexisting_and_no_partial(self):
        request, manifest, raw_receipt = self.prepare()
        existing = self.folder / "exists.json"
        existing.write_text("untouched", encoding="utf-8")
        other = self.folder / "new.json"
        with self.assertRaisesRegex(planner.evidence.EvidenceError, "already exists"):
            planner._publish_atomic_new([
                (other, (json.dumps(request) + "\n").encode()),
                (existing, (json.dumps(manifest) + "\n").encode()),
                (self.folder / "also-new.json", raw_receipt),
            ])
        self.assertEqual(existing.read_text(), "untouched")
        self.assertFalse(other.exists())

    def test_deterministic_given_same_receipt_and_timestamp(self):
        a = self.prepare()
        b = self.prepare()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
