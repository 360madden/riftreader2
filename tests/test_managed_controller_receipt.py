"""Offline, no-game tests for one exact on-demand controller generation receipt."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import managed_controller_receipt as managed


def digest(data):
    return hashlib.sha256(data).hexdigest().upper()


class ManagedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "artifacts" / "control-fleet-live" / "lab2" / "host.json"
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(b'{"config":"current"}')
        self.queue = self.root / "artifacts" / "native-coordination-live" / "queue.sqlite3"
        self.queue.parent.mkdir(parents=True)
        self.queue.write_bytes(b"synthetic canonical queue")
        self.sources = ("scripts/control_host.py", "scripts/controller_task_entry.py")
        for source in self.sources:
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.encode("ascii"))
        self.receipts = self.root / "artifacts" / "controller-tasks" / "lab2"
        self.receipts.mkdir(parents=True)
        self.identity = {"pid": 321, "image": "C:/Python314/pythonw.exe", "startTicks": 555}
        self.verified = []
        self.live = {321: self.identity}
        self.original = self.create_receipt()

    def create_receipt(self, generation="a" * 32, *, pid=321, overrides=None):
        folder = self.receipts / generation
        folder.mkdir(parents=True, exist_ok=True)
        value = {
            "lab": "lab2", "pid": pid, "session": 1,
            "processIdentity": {"pid": pid, "image": "C:/Python314/pythonw.exe",
                                "startTicks": 555},
            "vmIdentity": {"vmx": "exact-lab2", "processStartTicks": 123},
            "configSha256": digest(self.config.read_bytes()),
            "sourceHashes": {source: digest((self.root / source).read_bytes())
                             for source in self.sources},
            "task": "rr2-controller-lab2", "atUtc": datetime.now(timezone.utc).isoformat(),
        }
        value.update(overrides or {})
        path = folder / "process.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def resolve(self, **kwargs):
        return managed.resolve_current_managed_controller(
            "lab2", root=self.root, configs={"lab2": self.config},
            queue_path=self.queue, runtime_files=self.sources,
            identity_reader=self.identity_reader, verify_owner=self.verify_owner,
            **kwargs)

    def identity_reader(self, pid):
        if pid not in self.live:
            raise RuntimeError("process-unavailable")
        return self.live[pid]

    def verify_owner(self, lab):
        self.verified.append(lab)

    def test_one_live_receipt_builds_canonical_no_start_host_plan(self):
        path, receipt, plan = self.resolve()
        self.assertEqual(path, self.original)
        self.assertEqual(receipt["processIdentity"], self.identity)
        self.assertEqual(plan["resource"], "vm:rift-lab-2")
        self.assertEqual(plan["database"], str(self.queue))
        self.assertEqual(plan["runtimeHashes"], receipt["sourceHashes"])
        self.assertEqual(plan["expectedWindowsSession"], 1)
        self.assertEqual(self.verified, ["lab2"])

    def test_reviewed_exact_generation_can_be_reopened(self):
        self.assertEqual(self.resolve(expected_receipt_path=self.original)[0], self.original)
        other = self.receipts / ("f" * 32) / "process.json"
        with self.assertRaisesRegex(managed.ManagedReceiptError,
                                    "managed-reviewed-generation-changed"):
            self.resolve(expected_receipt_path=other)

    def test_reused_pid_with_new_start_is_not_the_original_generation(self):
        self.live[321] = dict(self.identity, startTicks=556)
        with self.assertRaisesRegex(managed.ManagedReceiptError,
                                    "managed-live-generation-not-unique"):
            self.resolve()
        self.assertEqual(self.verified, [])

    def test_two_live_receipts_are_ambiguous_even_if_both_have_matching_pid(self):
        self.create_receipt("b" * 32)
        with self.assertRaisesRegex(managed.ManagedReceiptError,
                                    "managed-live-generation-not-unique"):
            self.resolve()

    def test_wrong_task_or_lab_is_refused(self):
        for bad in ({"task": "rr2-controller-lab1"}, {"lab": "lab1"}):
            self.create_receipt(overrides=bad)
            with self.assertRaisesRegex(managed.ManagedReceiptError,
                                        "managed-receipt-lab-or-task-mismatch"):
                self.resolve()

    def test_config_or_source_change_is_refused(self):
        self.config.write_bytes(b"modified config")
        with self.assertRaisesRegex(managed.ManagedReceiptError, "managed-config-changed"):
            self.resolve()
        self.config.write_bytes(b'{"config":"current"}')
        (self.root / self.sources[0]).write_bytes(b"modified source")
        with self.assertRaisesRegex(managed.ManagedReceiptError, "managed-runtime-changed"):
            self.resolve()

    def test_missing_or_extra_source_hashes_are_refused(self):
        for bad in ({"sourceHashes": {self.sources[0]: "a" * 64}},
                    {"sourceHashes": {"extra": "a" * 64,
                                      **{s: digest((self.root / s).read_bytes())
                                         for s in self.sources}}}):
            self.create_receipt(overrides=bad)
            with self.assertRaisesRegex(managed.ManagedReceiptError,
                                        "managed-source-list-changed"):
                self.resolve()

    def test_exit_marker_refuses_live_generation(self):
        (self.original.parent / "exited.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(managed.ManagedReceiptError,
                                    "managed-live-generation-exiting"):
            self.resolve()

    def test_missing_process_is_skipped_not_promoted(self):
        self.live.clear()
        with self.assertRaisesRegex(managed.ManagedReceiptError,
                                    "managed-live-generation-not-unique"):
            self.resolve()

    def test_uncertain_process_inspection_fails_closed(self):
        def bad_identity(_pid):
            raise RuntimeError("access-denied")
        with self.assertRaisesRegex(managed.ManagedReceiptError,
                                    "managed-process-identity-uncertain"):
            managed.resolve_current_managed_controller(
                "lab2", root=self.root, configs={"lab2": self.config},
                queue_path=self.queue, runtime_files=self.sources,
                identity_reader=bad_identity, verify_owner=self.verify_owner)

    def test_malformed_receipt_and_invalid_lab_fail_closed(self):
        self.original.write_text('{"lab":"lab2","lab":"lab1"}', encoding="utf-8")
        with self.assertRaisesRegex(managed.ManagedReceiptError,
                                    "managed-receipt-malformed"):
            self.resolve()
        with self.assertRaisesRegex(managed.ManagedReceiptError, "managed-lab-invalid"):
            managed.resolve_current_managed_controller("lab3")

    def test_symlink_generation_is_refused_when_supported(self):
        target = self.receipts / "not-a-generation"
        target.mkdir()
        alias = self.receipts / ("b" * 32)
        alias.mkdir()
        # Model a symlink deterministically even when this account lacks Windows
        # Developer Mode or SeCreateSymbolicLinkPrivilege.
        with patch.object(Path, "is_symlink", autospec=True,
                          side_effect=lambda path: path == alias):
            with self.assertRaisesRegex(managed.ManagedReceiptError,
                                        "managed-generation-symlink"):
                self.resolve()


if __name__ == "__main__":
    unittest.main()
