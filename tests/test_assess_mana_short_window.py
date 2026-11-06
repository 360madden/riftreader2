import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.assess_mana_short_window import ManaAssessmentError, assess
from scripts.native_mana_candidate import BUILD_SHA


IDENTITY = {"processId": 1, "processStartUtcTicks": 2, "executableSha256": BUILD_SHA,
            "moduleBaseAddress": 3, "moduleSize": 4}
PLAYER = "u035400012FA2D678"
VM = {"vmx": "lab1", "pid": 5, "startTicks": 6, "logEpoch": "epoch"}
READER_SHA = "C" * 64
WORKFLOW_SHA = "D" * 64
PROBE_SHA = "E" * 64


def api(start, completed, value=3980, sequence=10, frame_time=100.0):
    return {"schemaVersion": 1, "evidenceKind": "typed-resource-snapshot-inspection/1",
            "status": "available", "identity": IDENTITY, "startedAtUtc": start,
            "completedAtUtc": completed, "snapshotSha256": "A" * 64,
            "selected": {"resource": "mana", "playerUnitId": PLAYER,
                         "sequence": sequence, "frameTime": frame_time,
                         "wireSha256": "B" * 64,
                         "current": {"status": "ok", "value": value},
                         "maximum": {"status": "ok", "value": 3980}}}


def native(observed="2026-11-06T12:00:10Z"):
    return {"schemaVersion": 1, "status": "complete", "sourceStableAtPublish": True,
            "identity": IDENTITY, "nativePlayerUnitId": PLAYER, "vmIdentity": VM,
            "readerSha256": READER_SHA, "workflowSha256": WORKFLOW_SHA,
            "probeSha256": PROBE_SHA,
            "resourceRecordCandidate": {"kind": 3, "name": "mana", "inputsStable": True,
                "resourceWrapper": "0x20000000", "referenceSlot": "0x20000100",
                "record": "0x20000200",
                "observedAtUtc": observed,
                "observationIntervalUtc": {"startedAtUtc": observed,
                                           "completedAtUtc": "2026-11-06T12:00:11Z"},
                "recordVtableRva": "0x2A6ACD8",
                "candidateDescriptorGetterRva": "0x1CCB460", "gameClock": 100.0,
                "fields": {"rateRaw": 0, "baseRaw": 3980, "maximumRaw": 3980,
                           "recordRevision": 1, "wrapperRevision": 1, "wrapperClock": 100.0,
                           "expectedNativeResolverTypeUnverified": "0x072A"}}}


def descriptor():
    return {"schemaVersion": 1, "status": "type-checked-record-candidate",
            "identity": IDENTITY, "nativePlayerUnitId": PLAYER,
            "probeSha256": hashlib.sha256(
                Path("scripts/probe_native_mana_descriptor.py").read_bytes()).hexdigest().upper(),
            "readerSha256": READER_SHA, "workflowSha256": WORKFLOW_SHA,
            "ownerProbeSha256": PROBE_SHA,
            "fingerprint": {"typeCode": "0x072A", "recordVtableRva": "0x2A6ACD8",
                            "descriptorGetterRva": "0x1CCB460"}}


class ManaShortWindowTests(unittest.TestCase):
    def run_assess(self, *, before=None, native_value=None, descriptor_value=None, after=None, gap=10):
        values = [before or api("2026-11-06T12:00:00Z", "2026-11-06T12:00:05Z"),
                  native_value or native(), descriptor_value or descriptor(),
                  after or api("2026-11-06T12:00:15Z", "2026-11-06T12:00:16Z",
                               sequence=20, frame_time=110.0)]
        with tempfile.TemporaryDirectory() as folder:
            folder_path = Path(folder)
            owner_hashes = []
            owner_dirs = []
            for name in ("descriptor-before", "descriptor-after"):
                owner_dir = folder_path / name
                owner_dir.mkdir()
                owner_path = owner_dir / "review.json"
                owner_path.write_text(json.dumps(native()), encoding="utf-8")
                owner_hashes.append(hashlib.sha256(owner_path.read_bytes()).hexdigest().upper())
                owner_dirs.append(str(owner_dir))
            values[2]["beforeOwnerEvidence"] = owner_dirs[0]
            values[2]["afterOwnerEvidence"] = owner_dirs[1]
            values[2]["beforeOwnerReviewSha256"] = owner_hashes[0]
            values[2]["afterOwnerReviewSha256"] = owner_hashes[1]
            paths = []
            for index, value in enumerate(values):
                path = Path(folder) / f"{index}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
            return assess(*paths, gap)

    def test_stable_baseline_agreement(self):
        result = self.run_assess()
        self.assertEqual(result["status"], "stable-baseline-agreement")
        self.assertEqual(result["window"]["beforeSnapshotCompletionToNativeStartSeconds"], 5)
        self.assertEqual(result["values"]["native"]["current"], 3980)
        self.assertEqual(result["apiAdvance"]["sequenceDelta"], 10)

    def test_value_disagreement_is_explicit(self):
        result = self.run_assess(after=api("2026-11-06T12:00:15Z", "2026-11-06T12:00:16Z",
                                                  3979, sequence=20, frame_time=110.0))
        self.assertEqual(result["status"], "values-disagree")

    def test_outside_bracket_fails(self):
        with self.assertRaisesRegex(ManaAssessmentError, "not-api-bracketed"):
            self.run_assess(native_value=native("2026-11-06T11:59:59Z"))

    def test_native_interval_must_complete_before_after_snapshot(self):
        bad = native()
        bad["resourceRecordCandidate"]["observationIntervalUtc"]["completedAtUtc"] = (
            "2026-11-06T12:00:16Z")
        with self.assertRaisesRegex(ManaAssessmentError, "not-api-bracketed"):
            self.run_assess(native_value=bad)

    def test_exact_failed_attempt_times_use_full_native_interval(self):
        before = api("2026-11-06T12:52:16.8004260Z", "2026-11-06T12:52:16.8031192Z")
        native_value = native("2026-11-06T12:53:43.2816943Z")
        native_value["resourceRecordCandidate"]["observationIntervalUtc"] = {
            "startedAtUtc": "2026-11-06T12:53:43.2816943Z",
            "completedAtUtc": "2026-11-06T12:53:43.5850001Z",
        }
        after = api("2026-11-06T12:54:00Z", "2026-11-06T12:54:01Z",
                    sequence=20, frame_time=110.0)
        result = self.run_assess(before=before, native_value=native_value, after=after, gap=180)
        self.assertAlmostEqual(86.4785751,
            result["window"]["beforeSnapshotCompletionToNativeStartSeconds"], places=6)
        self.assertAlmostEqual(16.4149999,
            result["window"]["nativeCompletionToAfterSnapshotStartSeconds"], places=6)

    def test_gap_limit_fails(self):
        with self.assertRaisesRegex(ManaAssessmentError, "gap-exceeds"):
            self.run_assess(gap=4)

    def test_descriptor_type_or_owner_mismatch_fails(self):
        bad = descriptor()
        bad["fingerprint"]["typeCode"] = "0x072B"
        with self.assertRaisesRegex(ManaAssessmentError, "fingerprint"):
            self.run_assess(descriptor_value=bad)

    def test_stale_descriptor_producer_hash_fails_closed(self):
        bad = descriptor()
        bad["probeSha256"] = "F" * 64
        with self.assertRaisesRegex(ManaAssessmentError, "descriptor-producer-source"):
            self.run_assess(descriptor_value=bad)

    def test_stale_api_frame_fails_even_with_distinct_snapshot_times(self):
        stale = api("2026-11-06T12:00:15Z", "2026-11-06T12:00:16Z",
                    sequence=10, frame_time=100.0)
        with self.assertRaisesRegex(ManaAssessmentError, "not-advanced"):
            self.run_assess(after=stale)

    def test_nonfinite_frame_time_fails(self):
        bad = api("2026-11-06T12:00:15Z", "2026-11-06T12:00:16Z",
                  sequence=20, frame_time=float("inf"))
        with self.assertRaisesRegex(ManaAssessmentError, "source-sequence-or-clock-invalid"):
            self.run_assess(after=bad)

    def test_bad_snapshot_hash_fails(self):
        bad = api("2026-11-06T12:00:15Z", "2026-11-06T12:00:16Z",
                  sequence=20, frame_time=110.0)
        bad["snapshotSha256"] = "bad"
        with self.assertRaisesRegex(ManaAssessmentError, "sha256-invalid"):
            self.run_assess(after=bad)

    def test_descriptor_owner_vm_mismatch_fails(self):
        bad_native = native()
        bad_native["vmIdentity"] = dict(VM, logEpoch="other")
        with self.assertRaisesRegex(ManaAssessmentError, "vm-or-tool-identity-mismatch"):
            self.run_assess(native_value=bad_native)

    def test_descriptor_owner_route_mismatch_fails_without_using_mutable_revision_as_identity(self):
        bad_native = native()
        bad_native["resourceRecordCandidate"]["record"] = "0x20000300"
        with self.assertRaisesRegex(ManaAssessmentError, "descriptor-owner-route-mismatch"):
            self.run_assess(native_value=bad_native)
        advanced_native = native()
        advanced_native["resourceRecordCandidate"]["fields"].update(
            recordRevision=2, wrapperRevision=2, wrapperClock=101.0)
        advanced_native["resourceRecordCandidate"]["gameClock"] = 102.0
        self.assertEqual("stable-baseline-agreement",
                         self.run_assess(native_value=advanced_native)["status"])

    def test_boolean_native_integer_fails_structured(self):
        bad = native()
        bad["resourceRecordCandidate"]["fields"]["baseRaw"] = True
        with self.assertRaisesRegex(ManaAssessmentError, "int32-required"):
            self.run_assess(native_value=bad)

    def test_nonfinite_native_clock_fails_structured(self):
        bad = native()
        bad["resourceRecordCandidate"]["gameClock"] = float("inf")
        with self.assertRaisesRegex(ManaAssessmentError, "finite-number-required"):
            self.run_assess(native_value=bad)


if __name__ == "__main__":
    unittest.main()
