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


    def _new_epoch_fixture(self):
        newer = fixture("b" * 32, time="2026-10-19T09:13:17Z")
        newer["completedAtUtc"] = "2026-10-19T09:14:00Z"
        newer["identity"]["processId"] = 8356
        newer["identity"]["processStartUtcTicks"] = 639279978665141458
        new_owner = OWNER + 0x101000
        root_bytes = base64.b64encode(new_owner.to_bytes(8, "little")).decode()
        newer["rootRead"]["bytes"] = root_bytes
        newer["ownerAddress"] = f"0x{new_owner:X}"
        newer["windows"][0]["address"] = f"0x{new_owner:X}"
        newer["windows"][0]["hops"][0]["read"]["bytes"] = root_bytes
        for which in ("referenceBefore", "referenceAfter"):
            newer[which]["target"]["processId"] = 8356
            newer[which]["target"]["processStartUtc"] = "2026-10-19T09:11:06.5141458Z"
        return newer

    def test_cross_epoch_evidence_preserves_candidate_and_changed_heap(self):
        result = self.review(fixture(), self._new_epoch_fixture())
        self.assertEqual(result["processEpochCount"], 2)
        self.assertEqual(result["restartSurvival"], "same-build-candidate-observed")
        self.assertEqual(result["qualification"], "candidate-only")
        self.assertEqual(result["updateSurvival"], "not-assessed")
        self.assertEqual(result["oldEpochRequestRejection"], "not-tested-by-this-tool")
        self.assertTrue(result["crossEpochSameBuildComparisons"][0]["ownerSessionAddressChanged"])
        self.assertTrue(result["crossEpochSameBuildComparisons"][0]["eachRootAndLuaCheckPassed"])

    def test_cross_epoch_unstable_root_not_restart_evidence(self):
        data = self._new_epoch_fixture()
        data["windows"][0]["stable"] = False
        result = self.review(fixture(), data)
        self.assertEqual(result["restartSurvival"], "not-assessed")
        self.assertFalse(result["crossEpochSameBuildComparisons"][0]["eachRootAndLuaCheckPassed"])

    def test_cross_epoch_different_player_not_restart_evidence(self):
        data = self._new_epoch_fixture()
        for ref in ("referenceBefore", "referenceAfter"):
            data[ref]["readback"]["typedApi"]["snapshot"]["player"]["unitId"] = "different-player"
        result = self.review(fixture(), data)
        self.assertEqual(result["restartSurvival"], "not-assessed")
        self.assertEqual(result["crossEpochSameBuildComparisons"], [])

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



def health_fixture():
    report = fixture()
    report["plan"]["healthScan"] = True
    for key in ("referenceBefore", "referenceAfter"):
        fields = report[key]["readback"]["typedApi"]["snapshot"]["player"]["fields"]
        fields.update({
            "health": {"status": "ok", "value": 18208},
            "healthMax": {"status": "ok", "value": 18208},
            "power": {"status": "ok", "value": 100},
        })
    memory = bytearray(256)
    for off, value in ((40, 45), (64, 18208), (72, 18208),
                       (80, 18208), (104, 100)):
        struct.pack_into("<i", memory, off, value)
    base = 0x216A3D77000
    encoded = base64.b64encode(memory).decode()
    sha = hashlib.sha256(memory).hexdigest().upper()
    report["healthScan"] = {
        "referenceHealth": 18208,
        "regions": [], "bytesScanned": 4096, "failedChunks": 0,
        "seconds": 0.25, "truncated": True,
        "hits": [
            {
                "address": f"0x{base + off:X}", "contextAddress": f"0x{base:X}",
                "int32": True, "float32": False, "float64": False,
                "read": {"status": "success", "bytes": encoded},
                "sha256": sha,
            } for off in (64, 72, 80)
        ],
    }
    return report


class NativeHealthEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def assess(self, report, level_hint=45):
        path = self.folder / "report.json"
        path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        return evidence.evaluate_health_scan(path, ROOT_RVA, level_hint)

    def test_groups_adjacent_hits_without_qualifying_meaning(self):
        report = self.assess(health_fixture())
        self.assertEqual(report["candidateGroupCount"], 1)
        self.assertEqual(report["scanCoverage"]["matchingHitCount"], 3)
        self.assertEqual(report["scanCoverage"]["recordedHitCount"], 3)
        self.assertEqual(report["typedReference"]["health"], [18208, 18208])
        self.assertEqual(report["typedReference"]["rawPower"], [100, 100])
        group = report["candidateGroups"][0]
        self.assertEqual(group["addressCount"], 3)
        self.assertTrue(group["nearbyTypedPowerValue"])
        self.assertTrue(group["nearbyLevelHintValue"])
        self.assertEqual(report["qualification"], "candidate-only")
        self.assertEqual(report["restartSurvival"], "not-assessed")
        self.assertFalse(report["scanCoverage"]["completeMemoryCoverage"])

    def test_level_hint_is_optional_and_not_inferred(self):
        group = self.assess(health_fixture(), level_hint=None)["candidateGroups"][0]
        self.assertIsNone(group["nearbyLevelHintValue"])
        self.assertTrue(group["nearbyTypedPowerValue"])

    def test_changed_health_is_recorded_not_promoted(self):
        data = health_fixture()
        fields = data["referenceAfter"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]
        fields["health"]["value"] = 17000
        result = self.assess(data)
        self.assertTrue(result["typedReference"]["healthChangedDuringScan"])
        self.assertEqual(result["qualification"], "candidate-only")

    def test_incomplete_context_is_retained_but_not_ranked(self):
        data = health_fixture()
        data["healthScan"]["hits"][0]["read"]["status"] = "unavailable"
        result = self.assess(data)
        self.assertEqual(result["scanCoverage"]["matchingHitCount"], 2)
        self.assertEqual(result["scanCoverage"]["incompleteContextCount"], 1)
        self.assertEqual(result["candidateGroups"][0]["addressCount"], 2)

    def test_changed_context_value_is_not_ranked(self):
        data = health_fixture()
        hit = data["healthScan"]["hits"][0]
        mem = bytearray(base64.b64decode(hit["read"]["bytes"]))
        struct.pack_into("<i", mem, 64, 17000)
        hit["read"]["bytes"] = base64.b64encode(mem).decode()
        hit["sha256"] = hashlib.sha256(mem).hexdigest().upper()
        result = self.assess(data)
        self.assertEqual(result["scanCoverage"]["matchingHitCount"], 2)
        self.assertEqual(result["incompleteContexts"][0]["reason"], "int32-context-value-changed")

    def test_tampered_context_hash_is_rejected(self):
        data = health_fixture()
        data["healthScan"]["hits"][0]["sha256"] = "B" * 64
        with self.assertRaisesRegex(evidence.EvidenceError, "SHA-256 mismatch"):
            self.assess(data)

    def test_wrong_scan_health_reference_is_rejected(self):
        data = health_fixture()
        data["healthScan"]["referenceHealth"] = 100
        with self.assertRaisesRegex(evidence.EvidenceError, "does not match"):
            self.assess(data)

    def test_unavailable_health_is_rejected_not_zero(self):
        data = health_fixture()
        f = data["referenceBefore"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]
        f["health"] = {"status": "unavailable", "value": 0}
        with self.assertRaisesRegex(evidence.EvidenceError, "unavailable"):
            self.assess(data)

    def test_duplicate_hit_addresses_are_rejected(self):
        data = health_fixture()
        data["healthScan"]["hits"].append(copy.deepcopy(data["healthScan"]["hits"][0]))
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate health"):
            self.assess(data)

    def test_excessive_raw_hit_count_is_rejected(self):
        data = health_fixture()
        data["healthScan"]["hits"] *= 44
        with self.assertRaisesRegex(evidence.EvidenceError, "exceeds"):
            self.assess(data)

    def test_noninteger_level_hint_is_rejected(self):
        with self.assertRaisesRegex(evidence.EvidenceError, "level hint"):
            self.assess(health_fixture(), level_hint=True)

    def test_missing_health_scan_plan_is_rejected(self):
        data = health_fixture()
        data["plan"]["healthScan"] = False
        with self.assertRaisesRegex(evidence.EvidenceError, "did not request"):
            self.assess(data)

    def test_invalid_root_identity_is_rejected(self):
        data = health_fixture()
        data["referenceBefore"]["target"]["processId"] = 999
        with self.assertRaisesRegex(evidence.EvidenceError, "identity mismatch"):
            self.assess(data)

    def test_invalid_mode_combinations_are_rejected(self):
        data = health_fixture()
        file = self.folder / "report.json"
        file.write_text(json.dumps(data), encoding="utf-8")
        result = evidence.main([
            "--health-hits", "--report", str(file),
            "--root-rva", "0x32E0200",
            "--xyz-offsets", "0x320", "0x324", "0x328",
        ])
        self.assertEqual(result, 2)

    def test_health_report_replay_deterministic(self):
        data = health_fixture()
        first = self.assess(data)
        second = self.assess(data)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )



def _new_health_epoch(report):
    """Move a synthetic report to a distinct process without altering copied bytes."""
    newer = copy.deepcopy(report)
    newer["runId"] = "c" * 32
    newer["startedAtUtc"] = "2026-10-19T09:13:17Z"
    newer["completedAtUtc"] = "2026-10-19T09:14:00Z"
    newer["identity"]["processId"] = 8356
    newer["identity"]["processStartUtcTicks"] = 639279978665141458
    new_owner = OWNER + 0x101000
    root = base64.b64encode(new_owner.to_bytes(8, "little")).decode()
    newer["rootRead"]["bytes"] = root
    newer["ownerAddress"] = f"0x{new_owner:X}"
    newer["windows"][0]["address"] = f"0x{new_owner:X}"
    newer["windows"][0]["hops"][0]["read"]["bytes"] = root
    for name in ("referenceBefore", "referenceAfter"):
        newer[name]["target"]["processId"] = 8356
        newer[name]["target"]["processStartUtc"] = "2026-10-19T09:11:06.5141458Z"
        newer[name]["readback"]["typedApi"]["generation"] = 2
    # The raw 256-byte windows are identical, but source-session addresses differ.
    for hit in newer["healthScan"]["hits"]:
        for name in ("address", "contextAddress"):
            hit[name] = f"0x{int(hit[name], 16) + 0x500000:X}"
    return newer


def _duplicate_health_group(report):
    """Include another complete copy of the same three-hit structural pattern."""
    original = copy.deepcopy(report["healthScan"]["hits"])
    for hit in original:
        for key in ("address", "contextAddress"):
            hit[key] = f"0x{int(hit[key], 16) + 0x10000:X}"
        report["healthScan"]["hits"].append(hit)


class NativeHealthCrossEpochTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def compare(self, old, new, level_hint=45, *, reverse=False):
        paths = [self.root / "old.json", self.root / "new.json"]
        for path, report in zip(paths, (old, new)):
            path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        return evidence.compare_health_structures(
            paths[::-1] if reverse else paths, ROOT_RVA, level_hint
        )

    def test_two_distinct_epochs_share_one_static_structure(self):
        before = health_fixture()
        after = _new_health_epoch(before)
        result = self.compare(before, after)
        self.assertEqual(result["evidenceKind"], "native-health-cross-epoch-structure-review/1")
        self.assertEqual(result["comparisonStatus"], "static-marker-layout-comparison")
        self.assertEqual(result["sharedPatternCount"], 1)
        self.assertEqual(result["eligibleMarkerGroupsByEpoch"], [1, 1])
        pattern = result["sharedMarkerPatterns"][0]
        self.assertEqual(pattern["firstEpochInstances"], 1)
        self.assertEqual(pattern["secondEpochInstances"], 1)
        self.assertTrue(pattern["uniqueInBothEpochs"])
        self.assertEqual(result["qualification"], "candidate-only")
        self.assertFalse(result["healthValueChangeValidated"])
        self.assertFalse(result["resourceValueChangeValidated"])
        self.assertEqual(result["restartSurvival"], "not-qualified")

    def test_repeated_copy_is_reported_as_replicated_not_unique(self):
        before = health_fixture()
        after = _new_health_epoch(before)
        _duplicate_health_group(before)
        result = self.compare(before, after)
        self.assertEqual(result["sharedPatternCount"], 1)
        pattern = result["sharedMarkerPatterns"][0]
        self.assertEqual(pattern["firstEpochInstances"], 2)
        self.assertEqual(pattern["secondEpochInstances"], 1)
        self.assertTrue(pattern["replicatedInEitherEpoch"])
        self.assertFalse(pattern["uniqueInBothEpochs"])

    def test_report_order_does_not_change_result(self):
        first = health_fixture()
        second = _new_health_epoch(first)
        self.assertEqual(
            self.compare(first, second),
            self.compare(first, second, reverse=True),
        )

    def test_matching_without_optional_level_hint(self):
        first = health_fixture()
        second = _new_health_epoch(first)
        result = self.compare(first, second, level_hint=None)
        self.assertEqual(result["sharedPatternCount"], 1)
        tags = [
            value
            for point in result["sharedMarkerPatterns"][0]["typedMarkerLayout"]
            for value in point["tags"]
        ]
        self.assertNotIn("visualLevelHint", tags)
        self.assertIn("rawPower", tags)

    def test_changed_health_during_scan_blocks_static_comparison(self):
        first = health_fixture()
        second = _new_health_epoch(first)
        second["referenceAfter"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]["health"]["value"] = 17000
        result = self.compare(first, second)
        self.assertEqual(result["comparisonStatus"], "reference-changed-or-different-values")
        self.assertEqual(result["sharedMarkerPatterns"], [])
        self.assertFalse(result["healthValueChangeValidated"])

    def test_distinct_reference_values_block_static_pattern_matches(self):
        first = health_fixture()
        second = _new_health_epoch(first)
        for name in ("referenceBefore", "referenceAfter"):
            second[name]["readback"]["typedApi"]["snapshot"]["player"]["fields"]["power"]["value"] = 88
        result = self.compare(first, second)
        self.assertEqual(result["comparisonStatus"], "reference-changed-or-different-values")
        self.assertFalse(result["resourceValueChangeValidated"])
        self.assertEqual(result["sharedPatternCount"], 0)

    def test_same_epoch_is_rejected(self):
        first = health_fixture()
        second = copy.deepcopy(first)
        second["runId"] = "d" * 32
        with self.assertRaisesRegex(evidence.EvidenceError, "distinct process epochs"):
            self.compare(first, second)

    def test_duplicate_reports_are_not_two_epochs(self):
        data = health_fixture()
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate reports"):
            self.compare(data, data)

    def test_player_change_rejected(self):
        first = health_fixture()
        second = _new_health_epoch(first)
        for name in ("referenceBefore", "referenceAfter"):
            second[name]["readback"]["typedApi"]["snapshot"]["player"]["unitId"] = "other-player"
        with self.assertRaisesRegex(evidence.EvidenceError, "different players"):
            self.compare(first, second)

    def test_build_change_rejected(self):
        first = health_fixture()
        second = _new_health_epoch(first)
        second["plan"]["buildSha256"] = "B" * 64
        second["identity"]["executableSha256"] = "B" * 64
        for name in ("referenceBefore", "referenceAfter"):
            second[name]["target"]["executableSha256"] = "B" * 64
        with self.assertRaisesRegex(evidence.EvidenceError, "different game builds"):
            self.compare(first, second)

    def test_tampered_context_rejected_before_pattern_matching(self):
        first = health_fixture()
        second = _new_health_epoch(first)
        second["healthScan"]["hits"][1]["sha256"] = "0" * 64
        with self.assertRaisesRegex(evidence.EvidenceError, "SHA-256 mismatch"):
            self.compare(first, second)

    def test_repeated_report_only_with_changed_filename_is_rejected(self):
        first = health_fixture()
        second = copy.deepcopy(first)
        second["runId"] = "d" * 32
        with self.assertRaisesRegex(evidence.EvidenceError, "distinct process epochs"):
            self.compare(first, second)

    def test_cli_rejects_wrong_number_of_reports(self):
        path = self.root / "only.json"
        path.write_text(json.dumps(health_fixture()) + "\n", encoding="utf-8")
        result = evidence.main([
            "--compare-health-hits", "--report", str(path),
            "--root-rva", "0x32E0200",
        ])
        self.assertEqual(result, 2)

    def test_cli_rejects_combined_modes(self):
        path = self.root / "only.json"
        path.write_text(json.dumps(health_fixture()) + "\n", encoding="utf-8")
        result = evidence.main([
            "--compare-health-hits", "--health-hits", "--report", str(path),
            "--root-rva", "0x32E0200",
        ])
        self.assertEqual(result, 2)

    def test_cli_writes_one_atomic_no_overwrite_comparison(self):
        first, second = health_fixture(), _new_health_epoch(health_fixture())
        paths = (self.root / "a.json", self.root / "b.json")
        for path, data in zip(paths, (first, second)):
            path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        output = self.root / "comparison.json"
        arguments = [
            "--compare-health-hits", "--report", str(paths[0]),
            "--report", str(paths[1]), "--root-rva", "0x32E0200",
            "--level-hint", "45", "--output", str(output),
        ]
        self.assertEqual(evidence.main(arguments), 0)
        saved = json.loads(output.read_bytes())
        self.assertEqual(saved["sharedPatternCount"], 1)
        first_data = output.read_bytes()
        self.assertEqual(evidence.main(arguments), 2)
        self.assertEqual(output.read_bytes(), first_data)

if __name__ == "__main__":
    unittest.main()
