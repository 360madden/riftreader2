"""Offline, no-game tests for one exact on-demand controller generation receipt."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

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

    def verify_owner(self, lab, expected_pid):
        self.assertEqual(expected_pid, 321)
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

    def test_legacy_verification_only_after_exact_runtime_checks(self):
        legacy = Mock()
        with patch.object(self, "verify_owner", side_effect=RuntimeError("not-rr2")):
            self.resolve(verify_legacy=legacy)
            legacy.assert_called_once_with("lab2", self.identity["image"], self.root, 321)
            legacy.reset_mock()
            (self.root / self.sources[0]).write_bytes(b"changed")
            with self.assertRaisesRegex(managed.ManagedReceiptError, "managed-runtime-changed"):
                self.resolve(verify_legacy=legacy)
            legacy.assert_not_called()

    def test_legacy_failure_is_not_accepted(self):
        with patch.object(self, "verify_owner", side_effect=RuntimeError("not-rr2")):
            with self.assertRaisesRegex(managed.ManagedReceiptError, "managed-task-ownership-refused"):
                self.resolve(verify_legacy=Mock(side_effect=RuntimeError("ambiguous")))

    def test_inspection_owner_refusal_never_queries_legacy_registration(self):
        legacy = Mock()
        with patch.object(self, "verify_owner", side_effect=RuntimeError("inspection-denied")):
            with self.assertRaisesRegex(managed.ManagedReceiptError, "managed-task-ownership-refused"):
                self.resolve(allow_legacy=False, verify_legacy=legacy)
        legacy.assert_not_called()

    def test_inspection_task_binds_instance_to_receipt_pid(self):
        status = {"helperId": "rr2-controller-lab2", "taskName": "RiftReader2 Helper rr2-controller-lab2",
                  "state": "Running", "runLevel": "Limited", "atLogon": False,
                  "enginePid": 321, "instanceGuid": "4a048a33-b778-4f2f-9a90-e139cd4ce100"}
        with patch.object(managed.subprocess, "run") as run:
            run.return_value = Mock(returncode=0, stdout=json.dumps(status).encode())
            managed.verify_lab2_inspection_task("lab2", 321)
            for invalid in (dict(status, enginePid=322), dict(status, enginePid=0),
                            dict(status, instanceGuid="bad"), dict(status, instanceGuid=None)):
                run.return_value.stdout = json.dumps(invalid).encode()
                with self.assertRaises(managed.ManagedReceiptError):
                    managed.verify_lab2_inspection_task("lab2", 321)
            with self.assertRaises(managed.ManagedReceiptError):
                managed.verify_lab2_inspection_task("lab1", 321)

    def test_legacy_inspector_requires_strict_status_and_image(self):
        inspector = self.root / "scripts" / "Verify-RR2LegacyHelperTask.ps1"
        inspector.write_text("offline mock")
        status = {"helperId": "rr2-controller-lab2", "state": "Running", "atLogon": False,
                  "runLevel": "Limited", "ownership": "verified-legacy-read-only", "enginePid": 321, "instanceGuid": "4a048a33-b778-4f2f-9a90-e139cd4ce100"}
        with patch.object(managed.subprocess, "run") as run:
            run.return_value = Mock(returncode=0, stdout=json.dumps(status).encode())
            managed._verify_legacy_owner("lab2", self.identity["image"], self.root, 321)
            self.assertEqual(run.call_args.args[0][-4:],
                             ["-HelperId", "rr2-controller-lab2", "-Executable", self.identity["image"]])
            for invalid in ([], dict(status, helperId="rr2-controller-lab1"),
                            dict(status, state="Ready"), dict(status, atLogon=True),
                            dict(status, ownership="unknown"), dict(status, enginePid=322), dict(status, instanceGuid="bad")):
                run.return_value.stdout = json.dumps(invalid).encode()
                with self.subTest(invalid=invalid), self.assertRaises(managed.ManagedReceiptError):
                    managed._verify_legacy_owner("lab2", self.identity["image"], self.root, 321)
            run.return_value = Mock(returncode=1, stdout=b"")
            with self.assertRaises(managed.ManagedReceiptError):
                managed._verify_legacy_owner("lab2", self.identity["image"], self.root, 321)
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


class PreparedInspectionTaskTests(unittest.TestCase):
    status = {"helperId": "rr2-controller-lab2", "taskName": "RiftReader2 Helper rr2-controller-lab2",
              "state": "Running", "runLevel": "Limited", "atLogon": False, "enginePid": 321,
              "instanceGuid": "4a048a33-b778-4f2f-9a90-e139cd4ce100"}

    @contextmanager
    def fake_helper(self, mutate=lambda value: value):
        child = MagicMock()
        child.__enter__.return_value = child
        child.poll.return_value = None
        child.wait.return_value = 0
        pending = bytearray()
        def write(signal):
            ordinal, token = signal.decode().strip().split(":")
            value = mutate({"ordinal": int(ordinal), "token": token, "status": dict(self.status)})
            pending.extend(value if isinstance(value, bytes) else json.dumps(value).encode() + b"\n")
            return len(signal)
        def read(_fd, count):
            value = bytes(pending[:count]); del pending[:count]
            return value
        child.stdin.write.side_effect = write
        with patch.object(managed.subprocess, "Popen", return_value=child), \
             patch.object(managed, "_pipe_available", side_effect=lambda _: len(pending)), \
             patch.object(managed.os, "read", side_effect=read):
            yield child, pending

    def test_two_separate_single_use_signals_and_no_escaped_callbacks(self):
        with self.fake_helper() as (child, _):
            with managed.prepared_lab2_inspection_pair() as (first, second):
                child.stdin.write.assert_not_called()
                first("lab2", 321)
                self.assertEqual(child.stdin.write.call_count, 1)
                second("lab2", 321)
                self.assertEqual(child.stdin.write.call_count, 2)
                with self.assertRaises(managed.ManagedReceiptError): first("lab2", 321)
            for callback in (first, second):
                with self.assertRaises(managed.ManagedReceiptError): callback("lab2", 321)
            self.assertNotEqual(*[call.args[0].split(b":")[1] for call in child.stdin.write.call_args_list])

    def test_order_failure_invalidates_both_and_cleanup_kills_reaps(self):
        with self.fake_helper() as (child, _):
            with self.assertRaises(managed.ManagedReceiptError):
                with managed.prepared_lab2_inspection_pair() as (_first, second): second("lab2", 321)
            child.kill.assert_called_once()
            child.wait.assert_called_once_with(timeout=5)
            child.stdin.write.assert_not_called()

    def test_unused_failure_cleanup_and_compatibility_single_proof(self):
        with self.fake_helper() as (child, _):
            with self.assertRaisesRegex(RuntimeError, "discovery"):
                with managed.prepared_lab2_inspection_pair(): raise RuntimeError("discovery")
            child.kill.assert_called_once()
        with self.fake_helper() as (child, _):
            with managed.prepared_lab2_inspection_task() as verify: verify("lab2", 321)
            self.assertEqual(child.stdin.write.call_count, 1)
            child.kill.assert_called_once()

    def test_wrong_token_ordinal_pid_guid_partial_and_extra_frames_fail(self):
        mutations = [lambda f: dict(f, token="stale"), lambda f: dict(f, ordinal=2),
                     lambda f: dict(f, status=dict(f["status"], enginePid=322)),
                     lambda f: dict(f, status=dict(f["status"], instanceGuid="bad")),
                     lambda f: b"{}\n{}\n", lambda f: b"x" * 65537]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.fake_helper(mutate) as (child, _):
                with self.assertRaises(managed.ManagedReceiptError):
                    with managed.prepared_lab2_inspection_pair() as (first, _second): first("lab2", 321)
                child.kill.assert_called_once()
        with self.fake_helper(lambda f: b"partial") as (child, _):
            child.poll.return_value = 1
            with self.assertRaisesRegex(managed.ManagedReceiptError, "partial-frame"):
                with managed.prepared_lab2_inspection_pair() as (first, _second): first("lab2", 321)

    def test_second_proof_cannot_reuse_or_change_instance(self):
        def change(frame):
            if frame["ordinal"] == 2:
                frame["status"]["instanceGuid"] = "4a048a33-b778-4f2f-9a90-e139cd4ce101"
            return frame
        with self.fake_helper(change):
            with self.assertRaisesRegex(managed.ManagedReceiptError, "instance-changed"):
                with managed.prepared_lab2_inspection_pair() as (first, second):
                    first("lab2", 321); second("lab2", 321)
        with self.fake_helper() as (_child, pending):
            with self.assertRaisesRegex(managed.ManagedReceiptError, "unsolicited"):
                with managed.prepared_lab2_inspection_pair() as (first, second):
                    first("lab2", 321); pending.extend(b"stale\n"); second("lab2", 321)

    def test_expiry_before_either_signal_and_timeout_kill_reap(self):
        for boundary in (1, 2):
            with self.subTest(boundary=boundary), self.fake_helper() as (child, _):
                with managed.prepared_lab2_inspection_pair() as (first, second):
                    if boundary == 2: first("lab2", 321)
                    with patch.object(managed.time, "monotonic", return_value=float("inf")):
                        with self.assertRaisesRegex(managed.ManagedReceiptError, "expired"):
                            (first if boundary == 1 else second)("lab2", 321)
                self.assertEqual(child.stdin.write.call_count, boundary - 1)
                child.kill.assert_called_once()
        with self.fake_helper() as (child, _):
            with patch.object(managed, "_inspection_frame", side_effect=managed.subprocess.TimeoutExpired("fixture", 1)):
                with self.assertRaisesRegex(managed.ManagedReceiptError, "expired"):
                    with managed.prepared_lab2_inspection_pair() as (first, _): first("lab2", 321)
            child.kill.assert_called_once()
            child.wait.assert_called_once_with(timeout=5)

    def test_exit_racing_empty_peek_still_drains_final_frame(self):
        child = MagicMock()
        child.poll.return_value = 0
        with patch.object(managed, "_pipe_available", side_effect=[0, 3, 3]), \
             patch.object(managed.os, "read", return_value=b"{}\n"):
            self.assertEqual(managed._inspection_frame(child, managed.time.monotonic() + 1), b"{}")

    def test_caught_out_of_order_attempt_invalidates_all_callbacks(self):
        with self.fake_helper():
            with managed.prepared_lab2_inspection_pair() as (first, second):
                for callback in (second, first, second):
                    with self.assertRaises(managed.ManagedReceiptError): callback("lab2", 321)

    def test_second_wrong_token_and_response_timeouts_fail_closed(self):
        def stale_second(frame):
            return dict(frame, token="stale") if frame["ordinal"] == 2 else frame
        with self.fake_helper(stale_second):
            with self.assertRaisesRegex(managed.ManagedReceiptError, "frame-invalid"):
                with managed.prepared_lab2_inspection_pair() as (first, second):
                    first("lab2", 321); second("lab2", 321)
        for boundary in (1, 2):
            with self.subTest(boundary=boundary), self.fake_helper() as (child, _):
                with self.assertRaisesRegex(managed.ManagedReceiptError, "expired"):
                    with managed.prepared_lab2_inspection_pair() as (first, second):
                        if boundary == 2: first("lab2", 321)
                        with patch.object(managed, "_inspection_frame", side_effect=
                                          managed.subprocess.TimeoutExpired("fixture", 1)):
                            (first if boundary == 1 else second)("lab2", 321)
                child.kill.assert_called_once()
                child.wait.assert_called_once_with(timeout=5)

    def test_late_frame_and_invalid_targets_never_admit(self):
        child = MagicMock()
        with patch.object(managed.time, "monotonic", side_effect=[0, 2]), \
             patch.object(managed, "_pipe_available", return_value=3), \
             patch.object(managed.os, "read", return_value=b"{}\n"):
            with self.assertRaisesRegex(managed.ManagedReceiptError, "expired"):
                managed._inspection_frame(child, 1)
        for lab, pid in (("lab1", 321), ("lab2", True), ("lab2", 0)):
            with self.subTest(lab=lab, pid=pid), self.fake_helper() as (child, _):
                with self.assertRaisesRegex(managed.ManagedReceiptError, "target-invalid"):
                    with managed.prepared_lab2_inspection_pair() as (first, _): first(lab, pid)
                child.stdin.write.assert_not_called()

    def test_second_requires_successful_exit(self):
        with self.fake_helper() as (child, _):
            child.wait.side_effect = [1, 0]
            with self.assertRaisesRegex(managed.ManagedReceiptError, "ownership-refused"):
                with managed.prepared_lab2_inspection_pair() as (first, second):
                    first("lab2", 321); second("lab2", 321)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell required")
    def test_real_interpreter_two_triggers_fresh_fixture_results_and_cleanup(self):
        from scripts import ensure_controller
        with tempfile.TemporaryDirectory() as folder:
            scripts = Path(folder) / "fixture's scripts"
            scripts.mkdir()
            manager = scripts / "Manage-RR2HelperTask.ps1"
            invoked = scripts / "invoked"
            manager.write_text(
                "param($Action, $HelperId, [switch]$InspectLab2Controller)\n"
                "if ($Action -cne 'Status' -or $HelperId -cne 'rr2-controller-lab2' "
                "-or !$InspectLab2Controller) { throw 'unexpected invocation' }\n"
                "[IO.File]::AppendAllText((Join-Path $PSScriptRoot 'invoked'), 'x')\n"
                f"'{json.dumps(self.status)}'\n", encoding="ascii")
            with patch.object(ensure_controller, "MANAGER", manager):
                with managed.prepared_lab2_inspection_pair() as (first, second):
                    self.assertFalse(invoked.exists())
                    first("lab2", 321)
                    self.assertEqual(invoked.read_text(), "x")
                    second("lab2", 321)
                    self.assertEqual(invoked.read_text(), "xx")
                # A second invocation must read changed fixture output, not cached state.
                with managed.prepared_lab2_inspection_pair() as (first, second):
                    first("lab2", 321)
                    manager.write_text("throw 'fresh failure'", encoding="ascii")
                    with self.assertRaises(managed.ManagedReceiptError): second("lab2", 321)


if __name__ == "__main__":
    unittest.main()
