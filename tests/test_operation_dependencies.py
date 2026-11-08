"""Focused no-game-input tests for on-demand operational dependencies."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch, Mock

from scripts.operation_dependencies import Dependency, DependencyUnavailable, ensure_ready
from scripts import ensure_controller
from scripts import controller_task_entry
import json


@contextmanager
def _folder():
    yield "not-used"


class DependencyGateTests(unittest.TestCase):
    def test_reuse_existing(self):
        recovered = Mock()
        self.assertEqual(ensure_ready([Dependency("host", lambda: True, recovered)]), ["host"])
        recovered.assert_not_called()

    def test_recover_then_recheck(self):
        probe = Mock(side_effect=[False, True])
        recover = Mock()
        self.assertEqual(ensure_ready([Dependency("receiver", probe, recover)]), ["receiver"])
        self.assertEqual(probe.call_count, 2)
        recover.assert_called_once()

    def test_no_recovery_blocks_following_operations(self):
        subsequent = Mock()
        with self.assertRaisesRegex(DependencyUnavailable, "recovery-not-available"):
            ensure_ready([Dependency("reader", lambda: False),
                          Dependency("controller", subsequent)])
        subsequent.assert_not_called()

    def test_unhealthy_after_recovery_fails_closed(self):
        with self.assertRaisesRegex(DependencyUnavailable, "not-ready-after-recovery"):
            ensure_ready([Dependency("controller", lambda: False, lambda: None)])

    def test_exception_redacts_details(self):
        def fail():
            raise RuntimeError("token-should-not-print")
        with self.assertRaises(DependencyUnavailable) as caught:
            ensure_ready([Dependency("host", fail)])
        self.assertNotIn("token-should", str(caught.exception))

    def test_nonboolean_health_does_not_pass(self):
        with self.assertRaisesRegex(DependencyUnavailable, "invalid-health-result"):
            ensure_ready([Dependency("host", lambda: "yes")])


class ControllerEnsureTests(unittest.TestCase):
    @staticmethod
    def _listening_with_rows(rows, *, code=10035):
        with patch.object(ensure_controller.socket, "socket") as factory, \
             patch("scripts.vm_console_native.tcp_listener_rows", return_value=rows) as table:
            factory.return_value.__enter__.return_value.connect_ex.return_value = code
            result = ensure_controller._listening(49811)
            if code == 10035:
                table.assert_called_once_with(49811)
            else:
                table.assert_not_called()
            return result

    def test_windows_10035_uses_exact_listener_table_to_prove_absence(self):
        self.assertFalse(self._listening_with_rows([]))
        # Ordinary connection refusal still requires no native table query.
        self.assertFalse(self._listening_with_rows([("127.0.0.1", 111)], code=10061))

    def test_windows_10035_single_loopback_listener_remains_occupied(self):
        self.assertTrue(self._listening_with_rows([("127.0.0.1", 111)]))

    def test_windows_10035_ambiguous_listener_table_fails_closed(self):
        for rows in (
            [("0.0.0.0", 111)],
            [("127.0.0.1", 111), ("127.0.0.1", 222)],
            [("127.0.0.1", 0)],
        ):
            with self.subTest(rows=rows), self.assertRaisesRegex(
                DependencyUnavailable, "listener-state-uncertain"
            ):
                self._listening_with_rows(rows)

    def test_windows_10035_failed_native_query_fails_closed(self):
        with patch.object(ensure_controller.socket, "socket") as factory, \
             patch("scripts.vm_console_native.tcp_listener_rows", side_effect=OSError("unavailable")):
            factory.return_value.__enter__.return_value.connect_ex.return_value = 10035
            with self.assertRaisesRegex(DependencyUnavailable, "listener-state-uncertain"):
                ensure_controller._listening(49811)

    def test_task_entry_checks_rr2_manager_and_rejects_malformed_status(self):
        with patch("pathlib.Path.is_file", return_value=True), \
             patch.object(controller_task_entry.subprocess, "run", return_value=Mock(
                 returncode=0, stdout=json.dumps([]).encode())) as run:
            with self.assertRaisesRegex(RuntimeError, "managed-helper-status-invalid"):
                controller_task_entry._require_owned_task("lab1", 123)
        args = run.call_args.args[0]
        self.assertIn(str(ensure_controller.ROOT / "scripts" / "Manage-RR2HelperTask.ps1"), args)
        self.assertEqual(args[-4:], ["-Action", "Status", "-HelperId", "rr2-controller-lab1"])

    def test_task_instance_must_match_expected_process(self):
        status = {"state": "Running", "atLogon": False, "runLevel": "Limited",
                  "enginePid": 123, "instanceGuid": "4a048a33-b778-4f2f-9a90-e139cd4ce100"}
        with patch("pathlib.Path.is_file", return_value=True), \
             patch.object(controller_task_entry.subprocess, "run") as run:
            run.return_value = Mock(returncode=0, stdout=json.dumps(status).encode())
            controller_task_entry._require_owned_task("lab1", 123)
            with self.assertRaisesRegex(RuntimeError, "managed-helper-not-running"):
                controller_task_entry._require_owned_task("lab1", 124)

    @patch.object(ensure_controller, "_verify_existing_owner", return_value=None)
    @patch.object(ensure_controller.HostConfig, "load")
    @patch.object(ensure_controller, "_probe")
    @patch.object(ensure_controller, "_launch")
    def test_healthy_existing_host_is_reused(self, launch, probe, config, verify):
        probe.return_value = {"host": {"connected": True}}
        value = ensure_controller.ensure("lab1")
        self.assertEqual(value["state"], "reused")
        launch.assert_not_called()

    @patch.object(ensure_controller, "_verify_existing_owner", return_value=None)
    @patch.object(ensure_controller.HostConfig, "load")
    @patch.object(ensure_controller, "_probe")
    @patch.object(ensure_controller, "_launch_lock", side_effect=lambda _: _folder())
    @patch.object(ensure_controller, "_launch", return_value="rr2-controller-lab2")
    @patch.object(ensure_controller.time, "sleep")
    def test_missing_host_started_only_once(self, sleep, launch, lock, probe, config, verify):
        probe.side_effect = [None, None, {"host": {"connected": False}}]
        value = ensure_controller.ensure("lab2")
        self.assertEqual(value["state"], "started")
        self.assertEqual(value["helper"], "rr2-controller-lab2")
        launch.assert_called_once()
        self.assertEqual(probe.call_count, 3)

    @patch.object(ensure_controller, "_verify_existing_owner", return_value=None)
    @patch.object(ensure_controller.HostConfig, "load")
    @patch.object(ensure_controller, "_probe")
    @patch.object(ensure_controller, "_launch_lock", side_effect=lambda _: _folder())
    @patch.object(ensure_controller, "_launch", return_value="rr2-controller-lab1")
    @patch.object(ensure_controller.time, "sleep")
    def test_new_listener_warmup_does_not_create_duplicate(self, sleep, launch, lock, probe, config, verify):
        probe.side_effect = [
            None, None,
            DependencyUnavailable("controller", "existing-endpoint-unhealthy"),
            {"host": {"connected": False}},
        ]
        value = ensure_controller.ensure("lab1")
        self.assertEqual(value["state"], "started")
        self.assertEqual(probe.call_count, 4)
        launch.assert_called_once()

    @patch("scripts.control_client.ControlClient")
    def test_authenticated_listener_with_failed_supervisor_is_not_reused(self, client):
        client.return_value.request.return_value = {
            "host": {"connected": True, "coordination": {
                "state": "blocked", "errorCode": "watchdog-blocked",
                "supervisor": {"state": "blocked", "threadAlive": False}}}}
        with self.assertRaisesRegex(DependencyUnavailable, "supervision-blocked"):
            ensure_controller._probe(Mock())

    @patch("scripts.control_client.ControlClient")
    def test_waiting_controller_can_be_recovered_by_guest_dependency(self, client):
        status = {"host": {"connected": False, "coordination": {
            "state": "waiting", "errorCode": None, "supervisor": None}}}
        client.return_value.request.return_value = status
        self.assertIs(ensure_controller._probe(Mock()), status)

    def test_listener_and_scheduler_must_both_match_receipt(self):
        config = Mock(ui_port=1234)
        with patch("scripts.managed_controller_receipt.resolve_current_managed_controller", return_value=(None, {"pid": 123}, None)) as resolve, \
             patch("scripts.vm_console_native.listener_owner", return_value=124):
            with self.assertRaisesRegex(DependencyUnavailable, "managed-owner-refused"):
                ensure_controller._verify_existing_owner("lab1", config)
            resolve.side_effect = ValueError("no task")
            with self.assertRaisesRegex(DependencyUnavailable, "managed-owner-refused"):
                ensure_controller._verify_existing_owner("lab1", config)

    def test_unowned_healthy_listener_is_never_replaced(self):
        with patch.object(ensure_controller.HostConfig, "load"), \
             patch.object(ensure_controller, "_probe", return_value={"host": {}}), \
             patch.object(ensure_controller, "_verify_existing_owner", side_effect=DependencyUnavailable("controller", "managed-owner-refused")), \
             patch.object(ensure_controller, "_launch") as launch:
            with self.assertRaisesRegex(DependencyUnavailable, "managed-owner-refused"):
                ensure_controller.ensure("lab1")
            launch.assert_not_called()

    def test_existing_only_never_launches(self):
        with patch.object(ensure_controller.HostConfig, "load"), \
             patch.object(ensure_controller, "_probe", return_value=None), \
             patch.object(ensure_controller, "_launch") as launch:
            with self.assertRaisesRegex(DependencyUnavailable, "existing-endpoint-missing"):
                ensure_controller.ensure_existing("lab1")
            launch.assert_not_called()

    def test_unknown_lab_never_launches(self):
        with self.assertRaisesRegex(DependencyUnavailable, "unknown-lab"):
            ensure_controller.ensure("lab3")

    @patch.object(ensure_controller.HostConfig, "load")
    @patch.object(ensure_controller, "_probe", side_effect=DependencyUnavailable("controller", "existing-endpoint-unhealthy"))
    @patch.object(ensure_controller, "_launch")
    def test_unhealthy_listening_endpoint_not_replaced(self, launch, probe, config):
        with self.assertRaisesRegex(DependencyUnavailable, "existing-endpoint-unhealthy"):
            ensure_controller.ensure("lab1")
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
