"""Offline checks for complete, exclusive controller startup receipts."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import controller_task_entry as entry


class FaultyStream:
    def __init__(self, stream, fault):
        self.stream, self.fault = stream, fault

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def write(self, payload):
        if self.fault in ("write", "short-write"):
            count = self.stream.write(payload[:7])
            if self.fault == "write":
                raise OSError("injected partial write")
            return count
        return self.stream.write(payload)

    def flush(self):
        if self.fault == "flush":
            raise OSError("injected flush failure")
        return self.stream.flush()

    def fileno(self):
        return self.stream.fileno()


class ControllerReceiptPublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name)
        self.receipt = {"lab": "lab2", "pid": 12, "sourceHashes": {"source": "A" * 64}}

    def test_success_publishes_complete_json_after_fsync(self):
        events = []
        fsync, link = os.fsync, os.link

        def sync(fd):
            self.assertFalse((self.output / "process.json").exists())
            fsync(fd)
            events.append("fsync")

        def publish(source, target):
            self.assertEqual(json.loads(Path(source).read_bytes()), self.receipt)
            self.assertEqual(events, ["fsync"])
            link(source, target)
            events.append("publish")

        with patch.object(entry.os, "fsync", side_effect=sync), \
                patch.object(entry.os, "link", side_effect=publish):
            entry._publish_process_receipt(self.output, self.receipt)
        self.assertEqual(events, ["fsync", "publish"])
        self.assertEqual(json.loads((self.output / "process.json").read_bytes()), self.receipt)
        self.assertEqual([path.name for path in self.output.iterdir()], ["process.json"])

    def test_serialization_failure_creates_no_file(self):
        with self.assertRaises(TypeError):
            entry._publish_process_receipt(self.output, {"bad": object()})
        self.assertEqual(list(self.output.iterdir()), [])

    def test_nonfinite_duplicate_and_nonobject_json_are_rejected_before_staging(self):
        for value in ({"bad": float("nan")}, {"bad": float("inf")},
                      {"nested": {1: "numeric", "1": "string"}}, ["not an object"]):
            with self.subTest(value=value), patch.object(entry.tempfile, "mkstemp") as create:
                with self.assertRaises(ValueError):
                    entry._publish_process_receipt(self.output, value)
                create.assert_not_called()
                self.assertEqual(list(self.output.iterdir()), [])

    def test_serialized_byte_limit_accepts_boundary_and_rejects_excess(self):
        overhead = len(json.dumps({"value": ""}, indent=2).encode("utf-8"))
        boundary = {"value": "a" * (65_536 - overhead)}
        entry._publish_process_receipt(self.output, boundary)
        final = self.output / "process.json"
        self.assertEqual(final.stat().st_size, 65_536)
        self.assertEqual(json.loads(final.read_bytes()), boundary)
        original = final.read_bytes()
        with patch.object(entry.tempfile, "mkstemp") as create:
            with self.assertRaises(ValueError):
                entry._publish_process_receipt(self.output, {"value": boundary["value"] + "a"})
            create.assert_not_called()
        self.assertEqual(final.read_bytes(), original)

    def test_partial_write_short_write_and_flush_fail_without_final(self):
        fdopen = os.fdopen
        for fault in ("write", "short-write", "flush"):
            with self.subTest(fault=fault), \
                    patch.object(entry.os, "fdopen", side_effect=lambda *a: FaultyStream(fdopen(*a), fault)), \
                    patch.object(entry.os, "link") as publish:
                with self.assertRaises(OSError):
                    entry._publish_process_receipt(self.output, self.receipt)
                publish.assert_not_called()
                self.assertEqual(list(self.output.iterdir()), [])

    def test_fsync_failure_never_publishes(self):
        with patch.object(entry.os, "fsync", side_effect=OSError("sync failed")), \
                patch.object(entry.os, "link") as publish:
            with self.assertRaises(OSError):
                entry._publish_process_receipt(self.output, self.receipt)
        publish.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_publish_failure_removes_owned_staging_only(self):
        unrelated = self.output / ".process-unrelated.tmp"
        unrelated.write_bytes(b"other owner")
        with patch.object(entry.os, "link", side_effect=OSError("publish failed")):
            with self.assertRaises(OSError):
                entry._publish_process_receipt(self.output, self.receipt)
        self.assertEqual(list(self.output.iterdir()), [unrelated])
        self.assertEqual(unrelated.read_bytes(), b"other owner")

    def test_existing_final_is_never_replaced(self):
        final = self.output / "process.json"
        final.write_bytes(b"existing owner bytes")
        with self.assertRaises(FileExistsError):
            entry._publish_process_receipt(self.output, self.receipt)
        self.assertEqual(final.read_bytes(), b"existing owner bytes")
        self.assertEqual(list(self.output.iterdir()), [final])

    def test_fdopen_failure_closes_descriptor_and_cleans_staging(self):
        close = os.close
        with patch.object(entry.os, "fdopen", side_effect=OSError("open failed")), \
                patch.object(entry.os, "close", wraps=close) as closed:
            with self.assertRaises(OSError):
                entry._publish_process_receipt(self.output, self.receipt)
        closed.assert_called_once()
        self.assertEqual(list(self.output.iterdir()), [])


class ControllerStartupReceiptTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / "config.json"
        self.config.write_bytes(b"synthetic config")
        self.queue = self.root / "queue.sqlite3"
        self.queue.write_bytes(b"synthetic queue")
        self.source = self.root / "scripts/control_host.py"
        self.source.parent.mkdir()
        self.source.write_bytes(b"synthetic source")
        self.events = []
        self.stack = self.enterContext(ExitStack())
        values = {
            "ROOT": self.root, "CONFIGS": {"lab2": self.config}, "QUEUE": self.queue,
            "RUNTIME_FILES": ("scripts/control_host.py",),
            "_require_owned_task": Mock(), "_listening": Mock(return_value=False),
            "_session_id": Mock(side_effect=lambda: self.record("session", 4)),
            "process_identity": Mock(side_effect=lambda pid: self.record("process", {"pid": pid, "startTicks": 123})),
            "now": Mock(return_value="2026-11-07T12:00:00+00:00"),
        }
        for name, value in values.items():
            self.stack.enter_context(patch.object(entry, name, value))
        self.stack.enter_context(patch.object(entry.HostConfig, "load", return_value=SimpleNamespace(ui_port=12345)))
        guard = self.stack.enter_context(patch.object(entry, "VmEpochGuard"))
        guard.return_value.collect.side_effect = lambda: self.record("vm", {"vmx": "synthetic-vm"})
        self.run = self.stack.enter_context(patch.object(entry.runpy, "run_path", side_effect=self.host_run))
        self.stack.enter_context(patch.object(entry.sys, "argv", []))
        sha = entry.sha
        self.stack.enter_context(patch.object(entry, "sha", side_effect=lambda path: self.record("config-hash" if path == self.config else "source-hash", sha(path))))

    def record(self, event, result):
        self.assertEqual(list(self.root.rglob("process.json")), [])
        self.events.append(event)
        return result

    def host_run(self, *args, **kwargs):
        finals = list(self.root.rglob("process.json"))
        self.assertEqual(len(finals), 1)
        value = json.loads(finals[0].read_bytes())
        self.assertEqual(set(value), {"lab", "pid", "session", "processIdentity", "vmIdentity", "configSha256", "sourceHashes", "task", "atUtc"})
        self.assertEqual(value["session"], 4)
        self.assertEqual(value["processIdentity"]["pid"], os.getpid())
        self.assertEqual(value["task"], "rr2-controller-lab2")
        self.assertEqual(set(value["sourceHashes"]), {"scripts/control_host.py", "scripts/controller_task_entry.py"})
        self.events.append("run")

    def test_success_collects_all_metadata_and_syncs_before_host_run(self):
        fsync = os.fsync
        dumps = json.dumps
        def serialize(value, *args, **kwargs):
            self.assertTrue({"vm", "source-hash", "session", "process", "config-hash"}.issubset(self.events))
            self.events.append("serialize")
            return dumps(value, *args, **kwargs)
        def sync(fd):
            self.assertTrue({"vm", "source-hash", "session", "process", "config-hash"}.issubset(self.events))
            fsync(fd)
            self.events.append("fsync")
        with patch.object(entry.os, "fsync", side_effect=sync), \
                patch.object(entry.json, "dumps", side_effect=serialize):
            entry.start("lab2")
        self.run.assert_called_once_with(str(self.source), run_name="__main__")
        self.assertLess(self.events.index("serialize"), self.events.index("fsync"))
        self.assertLess(self.events.index("fsync"), self.events.index("run"))
        self.assertEqual(list(self.root.rglob(".process-*.tmp")), [])

    def test_metadata_failures_leave_no_final_and_never_run_host(self):
        for name in ("_session_id", "process_identity", "sha"):
            with self.subTest(collaborator=name), patch.object(entry, name, side_effect=RuntimeError("injected metadata failure")):
                with self.assertRaises(RuntimeError):
                    entry.start("lab2")
                self.assertEqual(list(self.root.rglob("process.json")), [])
                self.run.assert_not_called()

    def test_config_hash_failure_leaves_no_empty_process_artifact(self):
        original = entry.sha
        def hash_source(path):
            if path == self.config:
                raise OSError("config unreadable")
            return original(path)
        with patch.object(entry, "sha", side_effect=hash_source):
            with self.assertRaises(OSError):
                entry.start("lab2")
        self.run.assert_not_called()
        self.assertEqual(list(self.root.rglob("process.json")), [])

    def test_interrupted_identity_collection_leaves_no_final(self):
        with patch.object(entry, "process_identity", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                entry.start("lab2")
        self.run.assert_not_called()
        self.assertEqual(list(self.root.rglob("process.json")), [])
        self.assertEqual(list(self.root.rglob(".process-*.tmp")), [])

    def test_publication_failure_never_runs_host(self):
        with patch.object(entry.os, "link", side_effect=OSError("publication failed")):
            with self.assertRaises(OSError):
                entry.start("lab2")
        self.run.assert_not_called()
        self.assertEqual(list(self.root.rglob("process.json")), [])
        self.assertEqual(list(self.root.rglob(".process-*.tmp")), [])

    def test_serialization_and_persistence_failures_never_run_host(self):
        fdopen = os.fdopen
        faults = (
            (entry.json, "dumps", Mock(side_effect=TypeError("serialization failed"))),
            (entry.os, "fdopen", Mock(side_effect=lambda *a: FaultyStream(fdopen(*a), "write"))),
            (entry.os, "fdopen", Mock(side_effect=lambda *a: FaultyStream(fdopen(*a), "short-write"))),
            (entry.os, "fdopen", Mock(side_effect=lambda *a: FaultyStream(fdopen(*a), "flush"))),
            (entry.os, "fsync", Mock(side_effect=OSError("sync failed"))),
        )
        for owner, name, replacement in faults:
            with self.subTest(failure=name, replacement=replacement), patch.object(owner, name, replacement):
                with self.assertRaises((TypeError, OSError)):
                    entry.start("lab2")
                self.run.assert_not_called()
                self.assertEqual(list(self.root.rglob("process.json")), [])
                self.assertEqual(list(self.root.rglob(".process-*.tmp")), [])


class ControllerTaskOwnershipQueryTests(unittest.TestCase):
    STATUS = {"state": "Running", "atLogon": False, "runLevel": "Limited",
              "enginePid": 123, "instanceGuid": "4a048a33-b778-4f2f-9a90-e139cd4ce100"}

    def query(self, payload, returncode=0):
        with patch.object(Path, "is_file", return_value=True), \
                patch.object(entry.subprocess, "run", return_value=Mock(
                    returncode=returncode, stdout=payload)) as run:
            try:
                entry._require_owned_task("lab2", 123)
            finally:
                run.assert_called_once()
                self.assertEqual(run.call_args.args[0][-4:],
                                 ["-Action", "Status", "-HelperId", "rr2-controller-lab2"])
                self.assertEqual(run.call_args.kwargs["timeout"], 20)
                self.assertEqual(run.call_args.kwargs["stdin"], entry.subprocess.DEVNULL)
                self.assertTrue(run.call_args.kwargs["capture_output"])
                self.assertFalse(run.call_args.kwargs["check"])

    def test_verified_status_requires_one_read_only_manager_call(self):
        self.query(json.dumps(self.STATUS).encode("utf-8"))

    def test_identity_and_registration_mismatches_fail_without_python_retry(self):
        for field, value in (("state", "Ready"), ("atLogon", True), ("atLogon", 0),
                             ("runLevel", "Highest"), ("enginePid", 124),
                             ("enginePid", "123"), ("enginePid", True),
                             ("instanceGuid", "bad"),
                             ("instanceGuid", "00000000-0000-0000-0000-000000000000")):
            with self.subTest(field=field, value=value), \
                    self.assertRaisesRegex(RuntimeError, "managed-helper-not-running-or-not-on-demand"):
                self.query(json.dumps(dict(self.STATUS, **{field: value})).encode("utf-8"))

    def test_malformed_or_failed_manager_response_is_fatal_without_retry(self):
        for payload, returncode, reason in ((b"{", 0, "status-invalid"),
                                            (b"[]", 0, "status-invalid"),
                                            (b"\xff", 0, "status-invalid"),
                                            (json.dumps(self.STATUS).encode(), 1, "ownership-refused")):
            with self.subTest(payload=payload, returncode=returncode), \
                    self.assertRaisesRegex(RuntimeError, "managed-helper-" + reason):
                self.query(payload, returncode)


if __name__ == "__main__":
    unittest.main()
