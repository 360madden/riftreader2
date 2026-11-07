"""Offline fail-closed checks for one managed movement controller generation."""
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import scripts.run_movement_session as runner
from scripts import vm_console_native as native


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


class ForegroundPolicyTests(unittest.TestCase):
    def setUp(self):
        self.host = runner.PinnedHost.__new__(runner.PinnedHost)
        self.host.plan = {'vmIdentity': {'pid': 21}, 'resource': 'vm:rift-lab-2'}
        self.host.check = MagicMock()
        self.host.target = {'processId': 99, 'processStartUtcTicks': 100,
                            'executableSha256': 'B' * 64, 'windowHandle': '0x10'}
        self.value = {
            'host': {'connected': True, 'vmIdentity': {'pid': 21},
                     'consoleReservation': {'held': True, 'faulted': False},
                     'coordination': {'state': 'ready', 'resource': 'vm:rift-lab-2',
                                      'supervisor': {'epoch': 'epoch'}}},
            'guest': {'target': {**self.host.target, 'isForeground': False},
                      'recoveryRequired': False, 'desktopInputsDown': [],
                      'busy': False, 'armed': False},
        }
        self.host.client = SimpleNamespace(request=lambda *args, **kwargs: self.value)

    def status(self, **kwargs):
        with (patch.object(runner, 'bind_identity', return_value={}),
              patch.object(runner, 'resource_epoch', return_value='epoch')):
            return self.host.status(require_armed=False, **kwargs)

    def test_default_movement_status_still_requires_foreground(self):
        with self.assertRaisesRegex(runner.MovementSessionError, 'not foreground'):
            self.status()

    def test_explicit_maintenance_status_accepts_background_and_rechecks_identity(self):
        self.assertEqual(self.status(require_foreground=False), self.value)
        self.assertEqual(self.host.check.call_count, 2)

    def test_background_maintenance_keeps_target_and_idle_guards(self):
        self.value['guest']['target']['processId'] = 100
        with self.assertRaisesRegex(runner.MovementSessionError, 'game target changed'):
            self.status(require_foreground=False)
        self.value['guest']['target']['processId'] = 99
        self.value['guest']['desktopInputsDown'] = ['w']
        with self.assertRaisesRegex(runner.MovementSessionError, 'input down'):
            self.status(require_foreground=False)
        self.value['guest']['desktopInputsDown'] = []
        self.value['guest']['armed'] = True
        with self.assertRaisesRegex(runner.MovementSessionError, 'arm state'):
            self.status(require_foreground=False)


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

    def verify(self, host, vm, identity, *, listener_pid=123,
               required_sources=None, stop_requested=False):
        import scripts.ensure_controller as dependency
        guard = SimpleNamespace(
            enabled=True,
            config="native-config",
            module=SimpleNamespace(collect_identity=lambda config: vm),
        )
        sources = (tuple(host.plan["sourceHashes"]) if required_sources is None
                   else tuple(required_sources))
        with patch.object(runner, "sha", return_value="A" * 64), \
             patch.object(runner, "process_identity", return_value=identity), \
             patch.object(runner, "listener_owner", return_value=listener_pid), \
             patch.object(runner, "VmEpochGuard", return_value=guard), \
             patch.object(dependency, "RUNTIME_FILES", sources), \
             patch.object(Path, "exists", autospec=True,
                          side_effect=lambda path: stop_requested and path.name == "stop.request"):
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

    def test_missing_one_runtime_source_is_rejected_even_with_eight_hashes(self):
        host, vm, identity = self.fixture()
        required = tuple(host.plan["sourceHashes"]) + ("scripts/required.py",)
        with self.assertRaisesRegex(runner.MovementSessionError, "source hash set invalid"):
            self.verify(host, vm, identity, required_sources=required)

    def test_stop_requested_live_task_is_refused(self):
        host, vm, identity = self.fixture()
        with self.assertRaisesRegex(runner.MovementSessionError, "exited or failed"):
            self.verify(host, vm, identity, stop_requested=True)


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


class PreparedTaskVerifierScopeTests(unittest.TestCase):
    def test_inspection_second_proof_keeps_full_resolver_and_exact_receipt_comparison(self):
        import tempfile
        from scripts import managed_controller_receipt as managed
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "process.json"
            receipt_path.write_text("{}", encoding="utf-8")
            receipt = {"pid": 123}
            verifier = MagicMock()
            with patch.object(managed, "resolve_current_managed_controller",
                              return_value=(receipt_path, receipt, {})) as resolver:
                runner._require_exact_managed_task(
                    "lab2", receipt_path, receipt, inspect_lab2=True,
                    _inspection_task_verifier=verifier)
                resolver.assert_called_once_with(
                    "lab2", expected_receipt_path=receipt_path,
                    verify_owner=verifier, allow_legacy=False)
                resolver.return_value = (receipt_path, {"pid": 124}, {})
                with self.assertRaisesRegex(runner.MovementSessionError, "receipt was altered"):
                    runner._require_exact_managed_task(
                        "lab2", receipt_path, receipt, inspect_lab2=True,
                        _inspection_task_verifier=verifier)

    def test_prepared_verifier_cannot_enter_ordinary_or_lab1_proof(self):
        from scripts import managed_controller_receipt as managed
        with patch.object(managed, "resolve_current_managed_controller") as resolver:
            for lab, inspection in (("lab1", False), ("lab2", False), ("lab1", True)):
                with self.subTest(lab=lab, inspection=inspection):
                    with self.assertRaises(runner.MovementSessionError):
                        runner._require_exact_managed_task(
                            lab, Path("unused"), {}, inspect_lab2=inspection,
                            _inspection_task_verifier=MagicMock())
            resolver.assert_not_called()


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
        self.vm = {"pid": 21, "listenerPid": 21, "startTicks": 42, "port": 5962,
                   "image": "vmware-vmx.exe", "vmx": "lab2.vmx", "logEpoch": "boot-1"}
        self.identity = {"pid": 123, "creationTime": 100}
        self.status_value = ready_status()
        self.status_value["host"].update({"connected": True, "machineName": "RIFT-LAB-2",
                                          "vmIdentity": self.vm})
        self.status_value["host"]["consoleReservation"].update({"held": True, "faulted": False})
        self.status_value["host"]["coordination"].update({
            "resource": "vm:rift-lab-2", "state": "ready",
        })
        self.status_value["guest"].update({"recoveryRequired": False, "desktopInputsDown": [],
                                           "busy": False, "armed": False})
        self.status_value["guest"]["target"] = {
            "processId": 99, "processStartUtcTicks": 100,
            "executableSha256": "B" * 64, "windowHandle": "0x10",
            "machineName": "RIFT-LAB-2", "executablePath": "rift.exe", "isForeground": True,
            "clientWidth": 800, "clientHeight": 600, "clientX": 0, "clientY": 0,
        }
        identity = runner.bind_identity(self.status_value["host"], self.status_value["guest"])
        self.status_value["host"]["coordination"]["supervisor"]["epoch"] = runner.resource_epoch(identity)
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
        self.admission_calls = []
        self.inspection_task_checks = []
        self.inventory = MagicMock(return_value=self.vm)
        self.direct_identity = MagicMock(return_value=self.vm)
        self.proof_events = []
        self.prepared_verifier = MagicMock()
        self.prepared_first = MagicMock()

    def create_receipt(self, name):
        import json
        folder = self.task_dir / name
        folder.mkdir()
        (folder / "process.json").write_text(json.dumps(self.receipt), encoding="utf-8")

    def generate(self, *, reject_strict=False, require_foreground=True, return_host=False,
                 inspection=False):
        from scripts import managed_controller_receipt as managed
        fake_guard = SimpleNamespace(
            enabled=True, config="native-config",
            module=SimpleNamespace(collect_identity=self.inventory, verify_identity=native.verify_identity),
        )
        fake_client = SimpleNamespace(request=lambda path, method: self.status_value)
        def admission(*args, inspect_lab2=False, _inspection_task_verifier=None):
            self.admission_calls.append(args)
            self.inspection_task_checks.append(inspect_lab2)
            self.proof_events.append("second-proof" if _inspection_task_verifier is self.prepared_verifier
                                     else "first-proof")
            if reject_strict:
                raise runner.MovementSessionError("managed task ownership refused")
            if _inspection_task_verifier is not None:
                _inspection_task_verifier(args[0], args[2]["pid"])
        @contextmanager
        def prepared():
            self.proof_events.append("prepare")
            try:
                yield self.prepared_first, self.prepared_verifier
            finally:
                self.proof_events.append("close")
        with patch.object(runner, "ROOT", self.root), \
             patch.dict(self.dependency.CONFIGS, {"lab2": self.config_path}, clear=True), \
             patch.object(self.dependency, "QUEUE", self.queue_path), \
             patch.object(self.dependency, "RUNTIME_FILES", tuple(self.source_hashes)), \
             patch.object(runner.HostConfig, "load", return_value=SimpleNamespace(ui_port=49921)), \
             patch.object(runner, "ControlClient", return_value=fake_client), \
             patch.object(runner, "listener_owner", return_value=123), \
             patch.object(runner, "process_identity", return_value=self.identity), \
             patch.object(runner, "VmEpochGuard", return_value=fake_guard), \
             patch.object(managed, "prepared_lab2_inspection_pair", side_effect=prepared), \
             patch.object(native, "_direct_identity", self.direct_identity), \
             patch.object(runner.PinnedHost, "status", autospec=True,
                          side_effect=runner.PinnedHost.status) as status, \
             patch.object(runner, "_require_exact_managed_task",
                          side_effect=admission):
            if inspection:
                result = runner.admit_lab2_inspection_host(self.output)
                result.final_inventory_check()
            else:
                factory = runner.admit_managed_host if return_host else runner.write_managed_host_plan
                result = factory("lab2", self.output, require_foreground=require_foreground)
            status.assert_called_once()
            self.assertEqual(status.call_args.kwargs,
                             {"require_armed": False, "require_foreground": require_foreground})
            if return_host or inspection:
                self.assertIs(result, status.call_args.args[0])
            return result

    def test_factory_returns_validated_host_with_both_ownership_proofs(self):
        host = self.generate(return_host=True)
        self.assertIsInstance(host, runner.ManagedPinnedHost)
        self.assertEqual(host.plan_path, self.output / "managed-host-plan.json")
        self.assertEqual(host.plan, runner.load(host.plan_path))
        self.assertEqual([call[0] for call in self.admission_calls], ["lab2", "lab2"])
        self.assertEqual(self.inspection_task_checks, [False, False])
        self.assertEqual(self.inventory.call_count, 3)
        self.direct_identity.assert_not_called()
        self.prepared_verifier.assert_not_called()
        self.assertEqual(self.proof_events, ["first-proof", "first-proof"])

    def test_inspection_checks_inventory_at_both_boundaries_and_epoch_around_status(self):
        host = self.generate(inspection=True)
        self.assertIsInstance(host, runner.Lab2InspectionHost)
        self.assertEqual(len(self.admission_calls), 2)
        self.assertEqual(self.inspection_task_checks, [True, True])
        self.assertEqual(self.inventory.call_count, 2)
        self.assertEqual(self.direct_identity.call_count, 2)
        self.assertEqual(self.proof_events, ["prepare", "first-proof", "second-proof", "close"])
        self.prepared_first.assert_called_once_with("lab2", 123)
        self.prepared_verifier.assert_called_once_with("lab2", 123)

    def test_inspection_second_task_instance_failure_denies_admission(self):
        self.prepared_verifier.side_effect = runner.MovementSessionError("task instance changed")
        with self.assertRaisesRegex(runner.MovementSessionError, "task instance changed"):
            self.generate(inspection=True)
        self.assertEqual(self.proof_events, ["prepare", "first-proof", "second-proof", "close"])
        self.inventory.assert_not_called()
        self.direct_identity.assert_not_called()

    def test_inspection_first_proof_failure_closes_unused_preparation(self):
        with self.assertRaisesRegex(runner.MovementSessionError, "ownership refused"):
            self.generate(inspection=True, reject_strict=True)
        self.assertEqual(self.proof_events, ["prepare", "first-proof", "close"])
        self.prepared_verifier.assert_not_called()
        self.assertFalse((self.output / "managed-host-plan.json").exists())

    def test_ordinary_constructor_refuses_prepared_inspection_verifier_before_io(self):
        with self.assertRaisesRegex(runner.MovementSessionError, "requires Lab 2 inspection"):
            runner.ManagedPinnedHost(self.output / "absent.json",
                                     _inspection_task_verifier=self.prepared_verifier)
        self.prepared_verifier.assert_not_called()

    def test_inspection_requires_running_vm_at_admission(self):
        self.inventory.side_effect = native.Blocked("target-vm-not-running")
        with self.assertRaisesRegex(native.Blocked, "target-vm-not-running"):
            self.generate(inspection=True)
        self.direct_identity.assert_not_called()

    def test_inspection_refuses_ambiguous_final_membership(self):
        self.inventory.side_effect = [self.vm, native.Blocked("target-vm-shared-log-ambiguous")]
        with self.assertRaisesRegex(native.Blocked, "target-vm-shared-log-ambiguous"):
            self.generate(inspection=True)
        self.assertEqual(self.direct_identity.call_count, 2)

    def test_inspection_direct_checks_reject_changed_pid_start_listener_or_log(self):
        for key, other in (("pid", 22), ("startTicks", 43), ("listenerPid", 22), ("logEpoch", "boot-2")):
            with self.subTest(key=key):
                self.output = self.root / key
                self.output.mkdir()
                self.direct_identity.return_value = {**self.vm, key: other}
                with self.assertRaisesRegex(native.Blocked, "target-drift"):
                    self.generate(inspection=True)

    def test_inspection_refuses_lab1_before_resolving_any_dependencies(self):
        plan_path = self.output / 'plan.json'
        runner.save(plan_path, {"kind": "managed-controller/1", "lab": "lab1"})
        with self.assertRaisesRegex(runner.MovementSessionError, "managed host plan is invalid"):
            runner.Lab2InspectionHost(plan_path)

    def test_factory_refuses_nonforeground_game_by_default(self):
        self.status_value["guest"]["target"]["isForeground"] = False
        with self.assertRaisesRegex(runner.MovementSessionError, "not foreground"):
            self.generate(return_host=True)

    def test_maintenance_plan_explicitly_accepts_background_without_changing_plan_schema(self):
        self.status_value['guest']['target']['isForeground'] = False
        saved = self.generate(require_foreground=False)
        self.assertNotIn('requireForeground', runner.load(saved))

    def test_discovers_unique_matching_live_receipt_and_writes_exact_plan(self):
        import json
        saved = self.generate()
        plan = json.loads(saved.read_text(encoding="utf-8"))
        self.assertEqual(plan["kind"], "managed-controller/1")
        self.assertEqual(plan["hostInstance"], "host-1")
        self.assertEqual(plan["receiptSha256"], runner.sha(
            self.task_dir / "first/process.json"))
        self.assertEqual(len(self.admission_calls), 2)
        self.assertEqual([call[0] for call in self.admission_calls], ["lab2", "lab2"])

    def test_missing_owned_task_refuses_plan_before_publishing(self):
        with self.assertRaisesRegex(runner.MovementSessionError, "ownership refused"):
            self.generate(reject_strict=True)
        self.assertFalse((self.output / "managed-host-plan.json").exists())

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
