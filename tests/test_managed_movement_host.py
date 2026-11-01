"""Offline fail-closed checks for one managed movement controller generation."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import scripts.run_movement_session as runner


def ready_status():
    return {
        "host": {
            "instanceId": "guest-1",
            "consoleReservation": {"closing": False},
            "coordination": {
                "hostInstance": "host-1", "connection": 3, "errorCode": None,
                "shutdownRequested": False,
                "supervisor": {
                    "epoch": "epoch-1", "state": "running", "threadAlive": True,
                    "initialCleanupVerified": True, "errorCode": None,
                    "terminationPending": False,
                },
            },
        },
        "guest": {"instanceId": "guest-1"},
    }


def managed_host():
    host = runner.ManagedPinnedHost.__new__(runner.ManagedPinnedHost)
    host.plan = {
        "hostInstance": "host-1", "connection": 3,
        "supervisorEpoch": "epoch-1", "guestInstance": "guest-1",
    }
    return host


class ManagedStatusTests(unittest.TestCase):
    def status(self, value):
        with patch.object(runner.PinnedHost, "status", return_value=value):
            return managed_host().status(require_armed=False)

    def test_exact_generation_and_running_supervisor_pass(self):
        self.assertEqual(self.status(ready_status())["guest"]["instanceId"], "guest-1")

    def test_changed_host_generation_is_rejected(self):
        state = ready_status()
        state["host"]["coordination"]["hostInstance"] = "host-2"
        with self.assertRaisesRegex(runner.MovementSessionError, "generation"):
            self.status(state)

    def test_reconnection_is_rejected(self):
        state = ready_status()
        state["host"]["coordination"]["connection"] = 4
        with self.assertRaisesRegex(runner.MovementSessionError, "generation"):
            self.status(state)

    def test_unverified_supervisor_cleanup_is_rejected(self):
        state = ready_status()
        state["host"]["coordination"]["supervisor"]["initialCleanupVerified"] = False
        with self.assertRaisesRegex(runner.MovementSessionError, "supervisor"):
            self.status(state)

    def test_stopped_supervisor_is_rejected(self):
        state = ready_status()
        state["host"]["coordination"]["supervisor"]["threadAlive"] = False
        with self.assertRaisesRegex(runner.MovementSessionError, "supervisor"):
            self.status(state)

    def test_changed_guest_agent_is_rejected(self):
        state = ready_status()
        state["guest"]["instanceId"] = "guest-2"
        with self.assertRaisesRegex(runner.MovementSessionError, "generation"):
            self.status(state)

    def test_controller_closing_is_rejected(self):
        state = ready_status()
        state["host"]["consoleReservation"]["closing"] = True
        with self.assertRaisesRegex(runner.MovementSessionError, "closing"):
            self.status(state)

    def test_supervisor_termination_is_rejected(self):
        state = ready_status()
        state["host"]["coordination"]["supervisor"]["terminationPending"] = True
        with self.assertRaisesRegex(runner.MovementSessionError, "terminating"):
            self.status(state)


class ManagedReceiptTests(unittest.TestCase):
    def fixture(self):
        host = managed_host()
        vm = {"pid": 21, "startTicks": 42}
        identity = {"pid": 123, "creationTime": 100}
        source = {"scripts/file%d.py" % i: "A" * 64 for i in range(8)}
        host.plan.update({
            "lab": "lab2", "receiptSha256": "A" * 64,
            "configPath": "config", "configSha256": "A" * 64,
            "sourceHashes": source, "vmIdentity": vm,
        })
        host.receipt = {
            "lab": "lab2", "task": "rr2-controller-lab2",
            "vmIdentity": vm, "configSha256": "A" * 64,
            "sourceHashes": source, "pid": 123, "session": 1,
            "processIdentity": identity,
        }
        host.receipt_path = Path("artifacts/controller-tasks/lab2/one/process.json")
        host.config = SimpleNamespace(ui_port=49921)
        return host, vm, identity

    def verify(self, host, vm, identity, *, listener_pid=123):
        guard = SimpleNamespace(
            enabled=True,
            config="native-config",
            module=SimpleNamespace(collect_identity=lambda config: vm),
        )
        with patch.object(runner, "sha", return_value="A" * 64), \
             patch.object(runner, "process_identity", return_value=identity), \
             patch.object(runner, "listener_owner", return_value=listener_pid), \
             patch.object(runner, "VmEpochGuard", return_value=guard), \
             patch.object(Path, "exists", return_value=False):
            host.check()

    def test_exact_live_task_receipt_passes(self):
        host, vm, identity = self.fixture()
        self.verify(host, vm, identity)

    def test_changed_task_source_hashes_are_rejected(self):
        host, vm, identity = self.fixture()
        host.receipt["sourceHashes"] = {"scripts/other.py": "A" * 64}
        with self.assertRaisesRegex(runner.MovementSessionError, "differs"):
            self.verify(host, vm, identity)

    def test_process_epoch_mismatch_is_rejected(self):
        host, vm, identity = self.fixture()
        with self.assertRaisesRegex(runner.MovementSessionError, "process epoch"):
            self.verify(host, vm, {"pid": 123, "creationTime": 101})

    def test_foreign_operator_listener_owner_is_rejected(self):
        host, vm, identity = self.fixture()
        with self.assertRaisesRegex(runner.MovementSessionError, "listener owner"):
            self.verify(host, vm, identity, listener_pid=999)


class ManagedCliTests(unittest.TestCase):
    def test_managed_lab_accepted_without_legacy_plan(self):
        parsed = runner.build_parser().parse_args([
            "prepare", "--managed-lab", "lab2", "--feedback-pin", "pin",
            "--output", "out", "--mode", "turn", "--keys", "a",
        ])
        self.assertEqual(parsed.managed_lab, "lab2")
        self.assertIsNone(parsed.host_plan)

    def test_legacy_plan_remains_available(self):
        parsed = runner.build_parser().parse_args([
            "prepare", "--host-plan", "old.json", "--feedback-pin", "pin",
            "--output", "out", "--mode", "turn", "--keys", "d",
        ])
        self.assertEqual(parsed.host_plan, Path("old.json"))
        self.assertIsNone(parsed.managed_lab)


class ManagedPlanDiscoveryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        import json
        import scripts.ensure_controller as dependency

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.source_hashes = {}
        for i in range(8):
            relative = "scripts/file%d.py" % i
            path = self.root / relative
            path.write_text("stable source %d\n" % i, encoding="utf-8")
            self.source_hashes[relative] = runner.sha(path)
        self.config_path = self.root / "host.json"
        self.config_path.write_text("{}", encoding="utf-8")
        self.queue_path = self.root / "queue.sqlite3"
        self.queue_path.write_bytes(b"fixture")
        self.vm = {"pid": 21, "startTicks": 42}
        self.identity = {"pid": 123, "creationTime": 100}
        self.status_value = ready_status()
        self.status_value["host"].update({"connected": True, "vmIdentity": self.vm})
        self.status_value["host"]["coordination"].update({
            "resource": "vm:rift-lab-2", "state": "ready",
        })
        self.status_value["guest"]["target"] = {
            "processId": 99, "processStartUtcTicks": 100,
            "executableSha256": "B" * 64, "windowHandle": "0x10",
        }
        self.task_dir = self.root / "artifacts/controller-tasks/lab2"
        self.task_dir.mkdir(parents=True)
        self.receipt = {
            "lab": "lab2", "task": "rr2-controller-lab2",
            "vmIdentity": self.vm, "configSha256": runner.sha(self.config_path),
            "sourceHashes": self.source_hashes, "pid": 123, "session": 1,
            "processIdentity": self.identity,
        }
        self.create_receipt("first")
        self.output = self.root / "output"
        self.output.mkdir()
        self.dependency = dependency

    def create_receipt(self, name):
        import json
        folder = self.task_dir / name
        folder.mkdir()
        (folder / "process.json").write_text(json.dumps(self.receipt), encoding="utf-8")

    def generate(self):
        fake_guard = SimpleNamespace(
            enabled=True, config="native-config",
            module=SimpleNamespace(collect_identity=lambda config: self.vm),
        )
        fake_client = SimpleNamespace(request=lambda path, method: self.status_value)
        with patch.object(runner, "ROOT", self.root), \
             patch.dict(self.dependency.CONFIGS, {"lab2": self.config_path}, clear=True), \
             patch.object(self.dependency, "QUEUE", self.queue_path), \
             patch.object(runner.HostConfig, "load", return_value=SimpleNamespace(ui_port=49921)), \
             patch.object(runner, "ControlClient", return_value=fake_client), \
             patch.object(runner, "listener_owner", return_value=123), \
             patch.object(runner, "process_identity", return_value=self.identity), \
             patch.object(runner, "VmEpochGuard", return_value=fake_guard), \
             patch.object(runner.PinnedHost, "status", return_value=self.status_value):
            return runner.write_managed_host_plan("lab2", self.output)

    def test_discovers_unique_matching_live_receipt_and_writes_exact_plan(self):
        import json
        saved = self.generate()
        plan = json.loads(saved.read_text(encoding="utf-8"))
        self.assertEqual(plan["kind"], "managed-controller/1")
        self.assertEqual(plan["hostInstance"], "host-1")
        self.assertEqual(plan["receiptSha256"], runner.sha(
            self.task_dir / "first/process.json"))

    def test_ambiguous_live_receipts_are_rejected(self):
        self.create_receipt("second")
        with self.assertRaisesRegex(runner.MovementSessionError, "ambiguous"):
            self.generate()

    def test_exited_receipt_is_not_reused(self):
        (self.task_dir / "first/exited.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(runner.MovementSessionError, "missing or ambiguous"):
            self.generate()


if __name__ == "__main__":
    unittest.main()
