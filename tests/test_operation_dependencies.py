"""Focused no-game-input tests for on-demand operational dependencies."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch, Mock

from scripts.operation_dependencies import Dependency, DependencyUnavailable, ensure_ready
from scripts import ensure_controller


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
    @patch.object(ensure_controller.HostConfig, "load")
    @patch.object(ensure_controller, "_probe")
    @patch.object(ensure_controller, "_launch")
    def test_healthy_existing_host_is_reused(self, launch, probe, config):
        probe.return_value = {"host": {"connected": True}}
        value = ensure_controller.ensure("lab1")
        self.assertEqual(value["state"], "reused")
        launch.assert_not_called()

    @patch.object(ensure_controller.HostConfig, "load")
    @patch.object(ensure_controller, "_probe")
    @patch.object(ensure_controller, "_launch_lock", side_effect=lambda _: _folder())
    @patch.object(ensure_controller, "_launch", return_value=123)
    @patch.object(ensure_controller.time, "sleep")
    def test_missing_host_started_only_once(self, sleep, launch, lock, probe, config):
        probe.side_effect = [None, None, {"host": {"connected": False}}]
        value = ensure_controller.ensure("lab2")
        self.assertEqual(value["state"], "started")
        self.assertEqual(value["pid"], 123)
        launch.assert_called_once()
        self.assertEqual(probe.call_count, 3)

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
