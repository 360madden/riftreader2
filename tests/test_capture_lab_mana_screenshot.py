"""Offline safety tests for the capture-only Mana screenshot helper."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import capture_lab_mana_screenshot as cap
from tests.test_nav_control_watchdog import TARGET, VM


class FakeQueue:
    def __init__(self, epoch, *, wrong_grant=False):
        self.epoch = epoch
        self.wrong_grant = wrong_grant
        self.request = self.outcome = None
        self.finished = self.cancelled = self.stop_seen = False

    def dispatch_fence(self):
        return nullcontext()

    def status(self, **_kwargs):
        row = {"name": "vm:rift-lab-1", "epoch": self.epoch, "blocked": 0,
               "holder": None if self.finished or self.request is None else self.request,
               "cleanup_receipt": "watchdog-attested" if self.finished else None}
        requests = [] if self.request is None else [{
            "request_id": self.request,
            "state": self.outcome if self.finished else "active",
            "specification": {"resources": {"vm:rift-lab-1": self.epoch}},
        }]
        return {"resources": [row], "requests": requests, "next_sequence": None}

    def submit(self, request_id, owner, track, resources, **kwargs):
        assert owner == "mana-screenshot" and track == "C"
        assert resources == {"vm:rift-lab-1": self.epoch}
        self.request = request_id

    def dispatch(self):
        return {"request_id": "other" if self.wrong_grant else self.request,
                "token": "a" * 64,
                "lease": {"vm:rift-lab-1": {"epoch": self.epoch}}}

    def cancel(self, request_id, owner):
        assert request_id == self.request and owner == "mana-screenshot"
        self.cancelled = True
        self.finished = True
        self.outcome = "cancelled"

    def heartbeat(self, request_id, token):
        assert request_id == self.request and token == "a" * 64

    def finish(self, request_id, token, outcome, evidence):
        assert self.stop_seen and request_id == self.request and token == "a" * 64
        assert evidence
        self.finished = True
        self.outcome = outcome


class ManaScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        original_root = cap.ROOT
        cap.ROOT = self.root
        self.addCleanup(setattr, cap, "ROOT", original_root)
        self.now = datetime.now(timezone.utc)
        self.identity = {
            "processId": TARGET["processId"],
            "processStartUtcTicks": TARGET["processStartUtcTicks"],
            "executableSha256": cap.BUILD_SHA,
            "moduleBaseAddress": 0x140000000,
            "moduleSize": 0x4000000,
        }
        self.vm = deepcopy(VM)
        self.player = "u035400012FA2D678"
        self.review_path = self.make_evidence()
        self.review = cap.mana_review("lab1", self.review_path, self.now)
        self.status = self.bound_status()
        self.epoch = self.status["host"]["coordination"]["supervisor"]["epoch"]

    def make_evidence(self, *, age=0, type_code="0x072A", owner_sha=True):
        owner_dir = self.root / "artifacts/native-unit-manager/lab1/owner"
        descriptor_dir = self.root / "artifacts/native-mana-descriptor/lab1/descriptor"
        owner_dir.mkdir(parents=True, exist_ok=True)
        descriptor_dir.mkdir(parents=True, exist_ok=True)
        owner = {
            "schemaVersion": 1, "lab": "lab1", "status": "complete",
            "sourceStableAtPublish": True, "identity": self.identity,
            "vmIdentity": self.vm, "nativePlayerUnitId": self.player,
            "readerSha256": "A" * 64, "workflowSha256": "B" * 64,
            "probeSha256": cap.OWNER_PROBE_SHA256,
            "resourceRecordCandidate": {
                "kind": 3, "name": "mana", "status": "untyped-record-candidate",
                "observedAtUtc": (self.now - timedelta(seconds=age)).isoformat().replace(
                    "+00:00", "Z"),
                "inputsStable": True, "recordVtableRva": "0x2A6ACD8",
                "candidateDescriptorGetterRva": "0x1CCB460",
                "gameClock": 101.0,
                "mutableInputsChanged": False,
                "observationIntervalUtc": {
                    "startedAtUtc": (self.now - timedelta(seconds=age + 1)).isoformat().replace(
                        "+00:00", "Z"),
                    "completedAtUtc": (self.now - timedelta(seconds=age)).isoformat().replace(
                        "+00:00", "Z"),
                },
                "fields": {"baseRaw": 3980, "maximumRaw": 3980, "rateRaw": 9807,
                           "recordRevision": 8, "wrapperRevision": 8,
                           "wrapperClock": 100.0, "revisionConsistent": True},
                "mutableTransition": {
                    "status": "unchanged", "afterSecondaryRevision": 10,
                    "afterFields": {
                        "baseRaw": 3980, "maximumRaw": 3980, "rateRaw": 9807,
                        "recordRevision": 8, "wrapperRevision": 8,
                        "wrapperClock": 100.0, "revisionConsistent": True,
                    },
                },
            },
        }
        owner_path = owner_dir / "review.json"
        owner_path.write_text(json.dumps(owner), encoding="utf-8")
        digest = hashlib.sha256(owner_path.read_bytes()).hexdigest().upper()
        descriptor = {
            "schemaVersion": 1, "lab": "lab1",
            "status": "type-checked-record-candidate", "identity": self.identity,
            "nativePlayerUnitId": self.player,
            "fingerprint": {**cap.EXACT_FINGERPRINT, "typeCode": type_code},
            "afterOwnerEvidence": str(owner_dir),
            "afterOwnerReviewSha256": digest if owner_sha else "F" * 64,
            "probeSha256": cap.DESCRIPTOR_PROBE_SHA256,
            "ownerProbeSha256": cap.OWNER_PROBE_SHA256,
            "readerSha256": "A" * 64, "workflowSha256": "B" * 64,
        }
        path = descriptor_dir / "review.json"
        path.write_text(json.dumps(descriptor), encoding="utf-8")
        return path

    def bound_status(self):
        target = deepcopy(TARGET)
        target.update(processId=self.identity["processId"],
                      processStartUtcTicks=self.identity["processStartUtcTicks"],
                      executableSha256=cap.BUILD_SHA, isForeground=True)
        host = {
            "connected": True, "instanceId": "guest-one", "machineName": "RIFT-LAB-1",
            "vmIdentity": deepcopy(self.vm),
            "consoleReservation": {"held": True, "required": True,
                                   "faulted": False, "closing": False},
            "coordination": {"state": "ready", "shutdownRequested": False,
                             "safeToClose": False, "resource": "vm:rift-lab-1"},
        }
        guest = {"instanceId": "guest-one", "target": target, "armed": False,
                 "busy": False, "recoveryRequired": False, "desktopInputsDown": []}
        host["coordination"]["supervisor"] = {
            "state": "running", "threadAlive": True, "initialCleanupVerified": True,
            "resource": "vm:rift-lab-1",
            "epoch": cap.resource_epoch(cap.bind_identity(host, guest)),
        }
        return {"host": host, "guest": guest}

    def test_review_binds_descriptor_owner_hash_type_and_age(self):
        self.assertEqual({"current": 3980, "maximum": 3980},
                         self.review["rawManaCandidate"])
        with patch.object(cap, "ROOT", self.root):
            stale = self.make_evidence(age=301)
            with self.assertRaisesRegex(cap.CaptureBlocked, "too old"):
                cap.mana_review("lab1", stale, self.now)
            wrong_type = self.make_evidence(type_code="0x072B")
            with self.assertRaisesRegex(cap.CaptureBlocked, "not type-checked"):
                cap.mana_review("lab1", wrong_type, self.now)
            wrong_hash = self.make_evidence(owner_sha=False)
            with self.assertRaisesRegex(cap.CaptureBlocked, "hash differs"):
                cap.mana_review("lab1", wrong_hash, self.now)

    def test_review_rejects_player_tool_vm_or_value_drift(self):
        owner_path = Path(self.review["ownerReview"])
        descriptor = json.loads(self.review_path.read_text(encoding="utf-8"))
        original = json.loads(owner_path.read_text(encoding="utf-8"))
        mutations = (
            lambda value: value.update(nativePlayerUnitId="uOTHER"),
            lambda value: value.update(readerSha256="C" * 64),
            lambda value: value.update(vmIdentity={}),
            lambda value: value.update(probeSha256="D" * 64),
            lambda value: value["resourceRecordCandidate"]["fields"].update(baseRaw=-1),
        )
        with patch.object(cap, "ROOT", self.root):
            for mutate in mutations:
                with self.subTest(mutate=mutate):
                    value = json.loads(json.dumps(original))
                    mutate(value)
                    owner_path.write_text(json.dumps(value), encoding="utf-8")
                    descriptor["afterOwnerReviewSha256"] = hashlib.sha256(
                        owner_path.read_bytes()).hexdigest().upper()
                    self.review_path.write_text(json.dumps(descriptor), encoding="utf-8")
                    with self.assertRaises(cap.CaptureBlocked):
                        cap.mana_review("lab1", self.review_path, self.now)
            owner_path.write_text(json.dumps(original), encoding="utf-8")

    def test_review_requires_current_descriptor_and_owner_probe_sources(self):
        owner_path = Path(self.review["ownerReview"])
        descriptor = json.loads(self.review_path.read_text(encoding="utf-8"))
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        with patch.object(cap, "ROOT", self.root):
            for field in ("probeSha256", "ownerProbeSha256"):
                with self.subTest(field=field):
                    changed = deepcopy(descriptor)
                    changed[field] = "D" * 64
                    self.review_path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaisesRegex(cap.CaptureBlocked, "producer sources"):
                        cap.mana_review("lab1", self.review_path, self.now)
            self.review_path.write_text(json.dumps(descriptor), encoding="utf-8")
            owner["probeSha256"] = "D" * 64
            owner_path.write_text(json.dumps(owner), encoding="utf-8")
            descriptor["afterOwnerReviewSha256"] = hashlib.sha256(
                owner_path.read_bytes()).hexdigest().upper()
            self.review_path.write_text(json.dumps(descriptor), encoding="utf-8")
            with self.assertRaisesRegex(cap.CaptureBlocked, "not bound"):
                cap.mana_review("lab1", self.review_path, self.now)

    def test_review_rejects_changed_local_probe_source(self):
        descriptor_source = self.root / "descriptor-probe.py"
        owner_source = self.root / "owner-probe.py"
        descriptor_source.write_bytes(cap.PROBE_SOURCES["descriptor"].read_bytes())
        owner_source.write_bytes(cap.PROBE_SOURCES["owner"].read_bytes())
        sources = {"descriptor": descriptor_source, "owner": owner_source}
        with patch.object(cap, "PROBE_SOURCES", sources):
            cap.mana_review("lab1", self.review_path, self.now)
            descriptor_source.write_bytes(descriptor_source.read_bytes() + b"\n# drift\n")
            with self.assertRaisesRegex(cap.CaptureBlocked, "descriptor probe source changed"):
                cap.mana_review("lab1", self.review_path, self.now)

    def test_review_requires_coherent_value_interval_and_mutable_transition(self):
        owner_path = Path(self.review["ownerReview"])
        descriptor = json.loads(self.review_path.read_text(encoding="utf-8"))
        original = json.loads(owner_path.read_text(encoding="utf-8"))
        mutations = (
            lambda value: value["resourceRecordCandidate"].pop("observationIntervalUtc"),
            lambda value: value["resourceRecordCandidate"].pop("mutableTransition"),
            lambda value: value["resourceRecordCandidate"]["mutableTransition"].update(
                afterSecondaryRevision=True),
            lambda value: value["resourceRecordCandidate"]["mutableTransition"][
                "afterFields"].update(recordRevision=9),
            lambda value: value["resourceRecordCandidate"]["observationIntervalUtc"].update(
                completedAtUtc=(self.now + timedelta(seconds=1)).isoformat().replace(
                    "+00:00", "Z")),
            lambda value: value["resourceRecordCandidate"].update(mutableInputsChanged=True),
        )
        with patch.object(cap, "ROOT", self.root):
            for mutate in mutations:
                with self.subTest(mutate=mutate):
                    value = deepcopy(original)
                    mutate(value)
                    owner_path.write_text(json.dumps(value), encoding="utf-8")
                    descriptor["afterOwnerReviewSha256"] = hashlib.sha256(
                        owner_path.read_bytes()).hexdigest().upper()
                    self.review_path.write_text(json.dumps(descriptor), encoding="utf-8")
                    with self.assertRaises(cap.CaptureBlocked):
                        cap.mana_review("lab1", self.review_path, self.now)
            owner_path.write_text(json.dumps(original), encoding="utf-8")

    def test_review_requires_every_exact_fingerprint_slot(self):
        descriptor = json.loads(self.review_path.read_text(encoding="utf-8"))
        with patch.object(cap, "ROOT", self.root):
            for key in cap.EXACT_FINGERPRINT:
                with self.subTest(key=key):
                    changed = json.loads(json.dumps(descriptor))
                    changed["fingerprint"][key] = "0xDEAD"
                    self.review_path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaisesRegex(cap.CaptureBlocked, "not type-checked"):
                        cap.mana_review("lab1", self.review_path, self.now)
            self.review_path.write_text(json.dumps(descriptor), encoding="utf-8")

    def test_receipts_are_each_read_once_and_reject_duplicate_properties(self):
        owner_path = Path(self.review["ownerReview"])
        original = Path.read_bytes
        counts = {}

        def counted(path):
            resolved = str(path.resolve())
            counts[resolved] = counts.get(resolved, 0) + 1
            return original(path)

        with patch.object(Path, "read_bytes", counted):
            cap.mana_review("lab1", self.review_path, self.now)
        self.assertEqual(1, counts[str(self.review_path.resolve())])
        self.assertEqual(1, counts[str(owner_path.resolve())])

        duplicate = self.review_path.read_text(encoding="utf-8")
        duplicate = duplicate.replace('{"schemaVersion": 1,',
                                      '{"schemaVersion": 1, "schemaVersion": 1,', 1)
        self.review_path.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(cap.CaptureBlocked, "duplicate JSON property"):
            cap.mana_review("lab1", self.review_path, self.now)

    def test_status_requires_exact_vm_process_foreground_and_idle(self):
        self.assertEqual(self.epoch,
                         cap.ready_epoch(self.status, self.review, "vm:rift-lab-1"))
        changes = (
            ("host", "vmIdentity", {**self.vm, "startTicks": 999}),
            ("guest", "desktopInputsDown", ["W"]),
        )
        for section, key, value in changes:
            with self.subTest(key=key):
                changed = deepcopy(self.status)
                changed[section][key] = value
                with self.assertRaises(cap.CaptureBlocked):
                    cap.ready_epoch(changed, self.review, "vm:rift-lab-1")

    def test_capture_uses_lease_capture_stop_and_watchdog_without_arm(self):
        output = self.root / "capture"
        queue = FakeQueue(self.epoch)
        calls = []

        class FakeClient:
            def __init__(_self, _config, access=None):
                _self.access = access

            def request(_self, path, *, method, payload=None):
                calls.append(path)
                if path == "/api/status":
                    return self.status
                if path == "/api/stop":
                    queue.stop_seen = True
                    return {"stopped": True, "recoveryRequired": False}
                raise AssertionError(path)

        def fake_capture(client, destination):
            self.assertEqual({"request_id": queue.request, "token": "a" * 64},
                             client.access)
            destination.mkdir()
            (destination / "capture.json").write_text(
                json.dumps({"target": self.status["guest"]["target"]}), encoding="utf-8")
            return {"captureId": "fixture", "capture": str(destination / "capture.json"),
                    "image": str(destination / "image.bmp")}

        with (patch("scripts.ensure_guest_agent.ensure"),
              patch.object(cap.HostConfig, "load", return_value=object()),
              patch.object(cap, "ControlClient", FakeClient),
              patch.object(cap, "AccessQueue", return_value=queue),
              patch.object(cap, "_capture", side_effect=fake_capture),
              patch.object(cap, "require_recent")):
            result = cap.capture_once("lab1", self.review, output)
        self.assertEqual("captured-after-watchdog-release", result["status"])
        self.assertEqual(cap.DESCRIPTOR_PROBE_SHA256,
                         result["manaDescriptorProbeSha256"])
        self.assertEqual(cap.OWNER_PROBE_SHA256, result["manaOwnerProbeSha256"])
        self.assertEqual(self.review["observationIntervalUtc"],
                         result["nativeObservationIntervalUtc"])
        self.assertTrue(queue.stop_seen and queue.finished)
        self.assertEqual("succeeded", queue.outcome)
        self.assertNotIn("/api/arm", calls)
        self.assertNotIn("/api/action", calls)

    def test_wrong_grant_cancels_without_capture_or_stop(self):
        queue = FakeQueue(self.epoch, wrong_grant=True)

        class FakeClient:
            def __init__(_self, _config, access=None):
                self.assertIsNone(access)

            def request(_self, path, *, method, payload=None):
                self.assertEqual("/api/status", path)
                return self.status

        with (patch("scripts.ensure_guest_agent.ensure"),
              patch.object(cap.HostConfig, "load", return_value=object()),
              patch.object(cap, "ControlClient", FakeClient),
              patch.object(cap, "AccessQueue", return_value=queue),
              patch.object(cap, "_capture", side_effect=AssertionError("must not capture")),
              patch.object(cap, "require_recent")):
            with self.assertRaisesRegex(cap.CaptureBlocked, "own request cancelled"):
                cap.capture_once("lab1", self.review, self.root / "capture")
        self.assertTrue(queue.cancelled)


if __name__ == "__main__":
    unittest.main()
