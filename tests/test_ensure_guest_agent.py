"""Offline contracts for the two-lab, on-demand guest agent dependency."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import ensure_guest_agent as agent
from scripts.operation_dependencies import DependencyUnavailable


@contextmanager
def _no_lock(*_args, **_kwargs):
    yield


def _status(*, connected=True, armed=False, coordination=None, held=True):
    return {
        "host": {
            "connected": connected,
            "coordination": {"state": coordination or ("ready" if connected else "waiting")},
            "consoleReservation": {"held": held, "faulted": False},
        },
        "guest": ({
            "armed": armed, "busy": False, "recoveryRequired": False,
            "desktopInputsDown": [], "target": {"processId": 123},
        } if connected else {}),
    }


class GuestAgentDependencyTests(unittest.TestCase):
    def test_idle_requires_authenticated_ready_and_disarmed(self):
        self.assertTrue(agent._idle(_status()))
        self.assertFalse(agent._idle(_status(connected=False)))
        self.assertFalse(agent._idle(_status(armed=True)))
        self.assertFalse(agent._idle(_status(coordination="waiting")))
        self.assertFalse(agent._idle(_status(held=False)))

    def test_unknown_lab_does_not_touch_controller(self):
        with patch.object(agent, "ensure_controller") as controller:
            with self.assertRaisesRegex(DependencyUnavailable, "unknown-lab"):
                agent.ensure("lab3")
            controller.assert_not_called()

    def test_healthy_guest_reused_without_staging(self):
        with TemporaryDirectory() as directory, \
             patch.object(agent, "ROOT", Path(directory)), \
             patch.object(agent, "ensure_controller") as controller, \
             patch.object(agent, "_launch_lock", side_effect=_no_lock), \
             patch.object(agent.HostConfig, "load"), \
             patch.object(agent, "ControlClient") as client, \
             patch.object(agent, "_stage_and_request") as stage:
            client.return_value.request.return_value = _status()
            result = agent.ensure("lab1")
            self.assertEqual(result["state"], "reused")
            self.assertTrue(result["guestDisarmedIdle"])
            controller.assert_called_once_with("lab1")
            stage.assert_not_called()
            self.assertFalse((Path(directory) / "artifacts").exists())

    def test_missing_guest_starts_once_and_reprobes(self):
        with TemporaryDirectory() as directory, \
             patch.object(agent, "ROOT", Path(directory)), \
             patch.object(agent, "ensure_controller"), \
             patch.object(agent, "_launch_lock", side_effect=_no_lock), \
             patch.object(agent.HostConfig, "load"), \
             patch.object(agent, "ControlClient") as client, \
             patch.object(agent, "_stage_and_request") as stage:
            client.return_value.request.side_effect = [
                _status(connected=False), _status(coordination="starting"), _status()]
            stage.return_value = {
                "taskName": "RiftReader2 OnDemand Control Agent",
                "noAutomaticTrigger": True, "created": True, "started": True,
            }
            result = agent.ensure("lab2")
            self.assertEqual(result["state"], "started")
            stage.assert_called_once()
            self.assertEqual(client.return_value.request.call_count, 3)

    def test_existing_connection_starting_is_reused_without_staging(self):
        with patch.object(agent, "ensure_controller"), \
             patch.object(agent, "_launch_lock", side_effect=_no_lock), \
             patch.object(agent.HostConfig, "load"), \
             patch.object(agent, "ControlClient") as client, \
             patch.object(agent, "_stage_and_request") as stage, \
             patch.object(agent.time, "sleep"):
            client.return_value.request.side_effect = [
                _status(coordination="waiting"), _status(coordination="starting"), _status()]
            self.assertEqual(agent.ensure("lab1")["state"], "reused")
            stage.assert_not_called()

    def test_starting_connection_times_out_without_staging(self):
        with patch.object(agent, "ensure_controller"), \
             patch.object(agent, "_launch_lock", side_effect=_no_lock), \
             patch.object(agent.HostConfig, "load"), \
             patch.object(agent, "ControlClient") as client, \
             patch.object(agent, "_stage_and_request") as stage, \
             patch.object(agent.time, "sleep"), \
             patch.object(agent.time, "monotonic", side_effect=[0, 0, 2]):
            client.return_value.request.return_value = _status(coordination="starting")
            with self.assertRaisesRegex(DependencyUnavailable, "agent-connection-timeout"):
                agent.ensure("lab1", timeout_seconds=1)
            stage.assert_not_called()

    def test_starting_connection_rejects_unsafe_or_failed_status(self):
        cases = []
        armed = _status(coordination="starting", armed=True)
        cases.append(armed)
        faulted = _status(coordination="starting")
        faulted["host"]["consoleReservation"]["faulted"] = True
        cases.append(faulted)
        blocked = _status(coordination="starting")
        blocked["host"]["coordination"]["errorCode"] = "failure"
        cases.append(blocked)
        for key, value in (("busy", True), ("recoveryRequired", True),
                           ("desktopInputsDown", ["W"])):
            unsafe = _status(coordination="starting")
            unsafe["guest"][key] = value
            cases.append(unsafe)
        for key in ("closing", "acquiring"):
            unsafe = _status(coordination="starting")
            unsafe["host"]["consoleReservation"][key] = True
            cases.append(unsafe)
        for supervisor in ({"state": "blocked"}, {"errorCode": "failure"}, []):
            unsafe = _status(coordination="starting")
            unsafe["host"]["coordination"]["supervisor"] = supervisor
            cases.append(unsafe)
        cases.extend([None, {}, {"host": []}, {"host": {"coordination": [],
                      "consoleReservation": {}}}, {"host": {"coordination": {},
                      "consoleReservation": []}}])
        for guest in (None, [], "invalid"):
            malformed = _status(coordination="starting")
            malformed["guest"] = guest
            cases.append(malformed)
        for status in cases:
            with self.subTest(status=status):
                with self.assertRaises(DependencyUnavailable):
                    agent._check_waiting(status)
        disconnected = _status(connected=False)
        del disconnected["guest"]
        self.assertFalse(agent._check_waiting(disconnected))

    def test_connected_but_armed_does_not_launch(self):
        with TemporaryDirectory() as directory, \
             patch.object(agent, "ROOT", Path(directory)), \
             patch.object(agent, "ensure_controller"), \
             patch.object(agent, "_launch_lock", side_effect=_no_lock), \
             patch.object(agent.HostConfig, "load"), \
             patch.object(agent, "ControlClient") as client, \
             patch.object(agent, "_stage_and_request") as stage:
            client.return_value.request.return_value = _status(armed=True)
            with self.assertRaisesRegex(DependencyUnavailable, "connected-but-not-idle"):
                agent.ensure("lab1")
            stage.assert_not_called()

    def test_controller_without_console_does_not_launch(self):
        with TemporaryDirectory() as directory, \
             patch.object(agent, "ROOT", Path(directory)), \
             patch.object(agent, "ensure_controller"), \
             patch.object(agent, "_launch_lock", side_effect=_no_lock), \
             patch.object(agent.HostConfig, "load"), \
             patch.object(agent, "ControlClient") as client, \
             patch.object(agent, "_stage_and_request") as stage:
            client.return_value.request.return_value = _status(connected=False, held=False)
            with self.assertRaisesRegex(DependencyUnavailable, "controller-not-waiting-safely"):
                agent.ensure("lab2")
            stage.assert_not_called()

    def test_guest_task_contract_is_triggerless_and_interactive(self):
        source = (Path(__file__).parents[1] / "scripts/Ensure-GuestAgentTask.ps1").read_text()
        self.assertIn("-LogonType Interactive -RunLevel Limited", source)
        self.assertIn("$triggers.Count -eq 0", source)
        self.assertIn("-ExecutionTimeLimit ([TimeSpan]::Zero)", source)
        self.assertIn("-MultipleInstances IgnoreNew", source)
        self.assertIn("'prior-input-uncertain'", source)
        self.assertNotIn("New-ScheduledTaskTrigger", source)


class ClientWiringTests(unittest.TestCase):
    def test_capture_ensures_controller_and_guest(self):
        from types import SimpleNamespace
        from scripts import control_client
        args = SimpleNamespace(
            command="capture", config=agent.CONFIGS["lab1"],
            no_auto_start=False, lease=None, output=Path("unused"),
        )
        with patch.object(control_client.HOST.HostConfig, "load"), \
             patch("scripts.ensure_controller.ensure") as host, \
             patch.object(agent, "ensure") as guest, \
             patch.object(control_client, "ControlClient"), \
             patch.object(control_client, "_capture", return_value={"ok": True}):
            self.assertEqual(control_client.run(args), {"ok": True})
            host.assert_called_once_with("lab1")
            guest.assert_called_once_with("lab1")

    def test_status_does_not_start_guest_and_opt_out_skips_both(self):
        from types import SimpleNamespace
        from scripts import control_client
        args = SimpleNamespace(
            command="status", config=agent.CONFIGS["lab2"],
            no_auto_start=False, lease=None,
        )
        with patch.object(control_client.HOST.HostConfig, "load"), \
             patch("scripts.ensure_controller.ensure") as host, \
             patch.object(agent, "ensure") as guest, \
             patch.object(control_client, "ControlClient") as client:
            client.return_value.request.return_value = {"host": {}}
            control_client.run(args)
            host.assert_called_once_with("lab2")
            guest.assert_not_called()
            args.no_auto_start = True
            host.reset_mock()
            control_client.run(args)
            host.assert_not_called()
            guest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
