"""Offline tests for native field evidence integrity and conservative claims."""

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "native-field-evidence.py"
SPEC = importlib.util.spec_from_file_location("native_field_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)

BUILD = "A" * 64
ROOT_RVA = 0x32E0200
OFFSETS = (0x320, 0x324, 0x328)
OWNER = 0x216ECFE06A0
TICKS = 639279813293755454
START = "2026-10-19T04:35:29.3755454Z"


def reference(xyz, seq):
    fields = {
        key: {"status": "ok", "value": val}
        for key, val in zip(evidence.COORDS, xyz)
    }
    return {
        "instanceId": "observer-123",
        "target": {
            "processId": 11620, "processStartUtc": START,
            "executableSha256": BUILD,
        },
        "readback": {
            "status": "fresh",
            "typedApi": {
                "status": "fresh", "sequenceAdvanced": True,
                "frameTimeAdvanced": True, "generation": 1,
                "selectedSequence": seq,
                "snapshot": {"player": {"unitId": "player-1", "fields": fields}},
            },
        },
    }


def fixture(
    run_id="a" * 32, xyz=(7297.3599, 876.2899, 3054.29),
    native=None, stable=True, time="2026-10-19T05:45:07.8918123Z"
):
    native = native or xyz
    owner_bytes = bytearray(0x330)
    for offset, value in zip(OFFSETS, native):
        struct.pack_into("<f", owner_bytes, offset, value)
    root_bytes = OWNER.to_bytes(8, "little")
    root_read = {
        "status": "success", "bytes": base64.b64encode(root_bytes).decode()
    }
    window = {
        "address": f"0x{OWNER:X}", "offsets": ["0x0"],
        "read": {
            "status": "success",
            "bytes": base64.b64encode(owner_bytes).decode(),
        },
        "sha256": hashlib.sha256(owner_bytes).hexdigest().upper(),
    }
    if stable is not None:
        window["stable"] = stable
        if stable:
            window["hops"] = [{
                "address": f"0x{0x7FF6B6EE0000 + ROOT_RVA:X}",
                "offset": "0x0", "read": copy.deepcopy(root_read),
            }]
    return {
        "schemaVersion": 1, "evidenceKind": "native-field-discovery/1",
        "status": "complete", "runId": run_id,
        "startedAtUtc": time, "completedAtUtc": "2026-10-19T06:05:00Z",
        "plan": {"rootRva": f"0x{ROOT_RVA:X}", "buildSha256": BUILD},
        "identity": {
            "processId": 11620, "processStartUtcTicks": TICKS,
            "executableSha256": BUILD, "moduleBaseAddress": 0x7FF6B6EE0000,
            "moduleSize": 62611456,
        },
        "referenceBefore": reference(xyz, 10),
        "referenceAfter": reference(xyz, 12),
        "rootRead": root_read, "ownerAddress": f"0x{OWNER:X}",
        "windows": [window],
    }


class NativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def save(self, report, name):
        path = self.path / name
        path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        return path

    def review(self, *reports):
        paths = [self.save(report, f"{i}.json") for i, report in enumerate(reports)]
        return evidence.evaluate(paths, ROOT_RVA, OFFSETS)

    def test_exact_timestamp_ticks_preserve_seventh_digit(self):
        self.assertEqual(evidence._utc_ticks(START, "start"), TICKS)

    def test_single_capture_cannot_prove_movement(self):
        report = self.review(fixture())
        self.assertEqual(report["assessment"], "stationary-only")
        self.assertEqual(report["processEpochCount"], 1)
        self.assertEqual(report["restartSurvival"], "not-assessed")
        self.assertTrue(report["captures"][0]["withinTolerance"])
        self.assertEqual(report["captures"][0]["rootWindowStability"], "verified")

    def test_two_moved_stable_captures_correlate_displacement(self):
        result = self.review(
            fixture(),
            fixture("b" * 32, xyz=(7296.4, 876.32, 3054.38),
                    time="2026-10-19T06:00:00Z"),
        )
        self.assertEqual(result["assessment"], "movement-consistent-same-process")
        pair = result["withinEpochMovementComparisons"][0]
        self.assertTrue(pair["displacementAgrees"])
        self.assertTrue(pair["bothRootReadsStable"])
        self.assertEqual(result["qualification"], "candidate-only")

    def test_legacy_window_missing_stability_never_claims_stable(self):
        result = self.review(
            fixture(stable=None),
            fixture("b" * 32, xyz=(7296.4, 876.32, 3054.38),
                    time="2026-10-19T06:00:00Z"),
        )
        self.assertEqual(result["assessment"], "movement-consistent-stability-unverified")
        self.assertFalse(result["withinEpochMovementComparisons"][0]["bothRootReadsStable"])
        self.assertEqual(result["captures"][0]["rootWindowStability"], "unrecorded")

    def test_explicitly_unstable_root_is_not_supported(self):
        result = self.review(fixture(stable=False))
        self.assertEqual(result["assessment"], "contradictory-or-inconclusive")
        self.assertEqual(result["captures"][0]["rootWindowStability"], "failed")

    def test_mismatched_root_window_hash_is_rejected(self):
        data = fixture()
        data["windows"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(evidence.EvidenceError, "SHA-256"):
            self.review(data)

    def test_root_owner_mismatch_is_rejected(self):
        data = fixture()
        data["ownerAddress"] = "0x12345"
        with self.assertRaisesRegex(evidence.EvidenceError, "root pointer and owner"):
            self.review(data)

    def test_stable_root_hop_mismatch_is_rejected(self):
        data = fixture()
        data["windows"][0]["hops"][0]["address"] = "0x1000"
        with self.assertRaisesRegex(evidence.EvidenceError, "root stability hop"):
            self.review(data)

    def test_wrong_process_epoch_is_rejected(self):
        data = fixture()
        data["referenceAfter"]["target"]["processId"] = 999
        with self.assertRaisesRegex(evidence.EvidenceError, "target identity mismatch"):
            self.review(data)

    def test_reference_not_advanced_is_rejected(self):
        data = fixture()
        data["referenceAfter"]["readback"]["typedApi"]["selectedSequence"] = 10
        with self.assertRaisesRegex(evidence.EvidenceError, "sequence changed"):
            self.review(data)

    def test_reference_unavailable_is_rejected_not_treated_as_zero(self):
        data = fixture()
        data["referenceBefore"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]["coordX"] = {
            "status": "unavailable", "value": 0,
        }
        with self.assertRaisesRegex(evidence.EvidenceError, "unavailable"):
            self.review(data)

    def test_conflicting_native_values_are_exposed(self):
        report = self.review(fixture(native=(15.0, 876.29, 3054.29)))
        self.assertEqual(report["assessment"], "contradictory-or-inconclusive")
        self.assertFalse(report["captures"][0]["withinTolerance"])

    def test_changed_reference_during_capture_is_inconclusive(self):
        data = fixture()
        data["referenceAfter"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]["coordX"]["value"] += 1
        result = self.review(data)
        self.assertEqual(result["assessment"], "contradictory-or-inconclusive")
        self.assertTrue(result["captures"][0]["referenceChangedDuringCapture"])

    def test_repeated_report_is_not_independent_evidence(self):
        data = fixture()
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate capture"):
            self.review(data, data)

    def test_identical_run_ids_are_rejected_even_with_distinct_bytes(self):
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate capture"):
            self.review(fixture(), fixture(xyz=(7296.4, 876.32, 3054.38)))

    def test_mixed_builds_must_be_reviewed_separately(self):
        second = fixture("b" * 32)
        second["identity"]["executableSha256"] = "B" * 64
        second["plan"]["buildSha256"] = "B" * 64
        for ref in ("referenceBefore", "referenceAfter"):
            second[ref]["target"]["executableSha256"] = "B" * 64
        with self.assertRaisesRegex(evidence.EvidenceError, "builds differ"):
            self.review(fixture(), second)

    def test_strict_json_rejects_duplicate_properties(self):
        path = self.path / "duplicate.json"
        path.write_bytes(b'{"schemaVersion":1,"schemaVersion":1}')
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate JSON"):
            evidence.load_report(path)

    def test_existing_output_is_not_overwritten(self):
        report_path = self.save(fixture(), "capture.json")
        output_path = self.path / "existing.json"
        output_path.write_text("preserve me", encoding="utf-8")
        result = evidence.main([
            "--report", str(report_path),
            "--root-rva", "0x32E0200",
            "--xyz-offsets", "0x320", "0x324", "0x328",
            "--output", str(output_path),
        ])
        self.assertEqual(result, 2)
        self.assertEqual(output_path.read_text(encoding="utf-8"), "preserve me")

    def test_new_output_can_be_reloaded_without_live_game(self):
        report_path = self.save(fixture(), "capture.json")
        output_path = self.path / "review.json"
        result = evidence.main([
            "--report", str(report_path),
            "--root-rva", "0x32E0200",
            "--xyz-offsets", "0x320", "0x324", "0x328",
            "--output", str(output_path),
        ])
        self.assertEqual(result, 0)
        decoded = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(decoded["qualification"], "candidate-only")
        self.assertEqual(decoded["captureCount"], 1)


if __name__ == "__main__":
    unittest.main()
