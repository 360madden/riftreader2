"""Offline admission, identity pairing and no-input tests for the native CLI."""
import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import read_native_telemetry as cli
from scripts.sample_current_native_vitals import GAME_SHA

INSTANCE = "a" * 32
GAME = {"processId": 123, "processStartUtcTicks": 639000000000000001,
        "executableSha256": GAME_SHA}
VM = {"vmx": "lab2.vmx", "port": 5962, "logEpoch": "epoch", "pid": 4,
      "listenerPid": 4, "image": "vmware-vmx.exe", "startTicks": 12}
KEY = "18446744073709551615"


def status():
    return {"host": {"connected": True, "machineName": "RIFT-LAB-2",
            "instanceId": INSTANCE, "vmIdentity": dict(VM),
            "coordination": {"state": "ready"},
            "consoleReservation": {"held": True, "faulted": False}},
            "guest": {"armed": False, "busy": False, "recoveryRequired": False,
                      "desktopInputsDown": [], "instanceId": INSTANCE,
                      "target": {**GAME, "machineName": "RIFT-LAB-2"}}}


def sample(kind):
    row = {"schemaVersion": 1, "status": "candidate-only", "lab": "lab2",
           "transport": "persistent-control-agent", "vmIdentity": dict(VM),
           "activeAgentInstanceId": INSTANCE, "gameProcessId": GAME["processId"],
           "gameProcessStartUtcTicks": GAME["processStartUtcTicks"], "gameSha256": GAME_SHA,
           "observedAtUtc": "2026-11-09T15:50:00.0000001Z",
           "sourceReport": kind + ".json", "sourceReportSha256": "B" * 64,
           "limitation": "candidate-only"}
    row["metrics"] = ({"unitKey": KEY, "x": 1.5, "y": 2.5, "z": 3.5,
                       "freshness": "unqualified"} if kind == "position" else
                      {"unitKey": int(KEY), "health": {"current": 100, "maximum": 100},
                       "mana": {"current": None, "status": "unavailable"}})
    return row


class NativeTelemetryCommandTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.before, self.after = status(), status()
        self.position, self.vitals = sample("position"), sample("vitals")
        self.host = SimpleNamespace(expected_machine_name="RIFT-LAB-2", vmx=Path("lab2.vmx"),
                                    vnc_port=5962, vmrun=Path("vmrun.exe"), output_directory=Path("output"))
        self.client = Mock()
        self.client.request.side_effect = [self.before, self.after]
        self.hostname = stack.enter_context(patch.object(cli.socket, "gethostname", return_value="AMD-DESKTOP"))
        self.ensure = stack.enter_context(patch.object(cli, "ensure"))
        self.resolve = stack.enter_context(patch.object(cli, "resolve_current_managed_controller",
            return_value=(Path("process.json"), {"vmIdentity": dict(VM)}, {})))
        stack.enter_context(patch.object(cli.HostConfig, "load", return_value=self.host))
        stack.enter_context(patch.object(cli, "ControlClient", return_value=self.client))
        stack.enter_context(patch.object(cli, "validate_config", return_value="native-config"))
        self.xyz_query = stack.enter_context(patch.object(cli, "query_xyz", return_value=self.position))
        self.vitals_query = stack.enter_context(patch.object(cli, "query_vitals", return_value=self.vitals))

    def run_read(self):
        return cli.read_once("lab2", "AMD-DESKTOP")

    def test_success_preserves_candidates_sources_nulls_and_lossless_unit(self):
        original = copy.deepcopy(self.vitals)
        result = self.run_read()
        self.assertEqual("candidate-only", result["status"])
        self.assertFalse(result["atomic"])
        self.assertFalse(result["luaReaderUsed"])
        self.assertFalse(result["screenshotUsed"])
        self.assertEqual(KEY, result["unitKey"])
        self.assertEqual(KEY, result["vitals"]["metrics"]["unitKey"])
        self.assertIsNone(result["vitals"]["metrics"]["mana"]["current"])
        self.assertEqual(original, self.vitals)
        self.assertEqual("position.json", result["position"]["sourceReport"])
        self.assertEqual("unqualified", result["position"]["metrics"]["freshness"])
        self.ensure.assert_called_once_with("lab2")
        self.assertEqual(2, self.resolve.call_count)
        self.assertEqual([("/api/status",), ("/api/status",)],
                         [call.args for call in self.client.request.call_args_list])
        self.assertTrue(all(call.kwargs == {"method": "GET"}
                            for call in self.client.request.call_args_list))
        self.xyz_query.assert_called_once_with("native-config", VM, GAME, cli.CONFIGS["lab2"], lab="lab2")

    def test_wrong_machine_rejected_before_dependency_start(self):
        self.hostname.return_value = "LEGION"
        with self.assertRaisesRegex(ValueError, "host-mismatch"):
            self.run_read()
        self.ensure.assert_not_called()
        self.xyz_query.assert_not_called()

    def test_wrong_expected_host_rejected_before_dependency_start(self):
        with self.assertRaisesRegex(ValueError, "host-mismatch"):
            cli.read_once("lab2", "LEGION")
        self.ensure.assert_not_called()

    def test_unsupported_lab_has_no_fallback(self):
        with self.assertRaisesRegex(ValueError, "target-not-supported"):
            cli.read_once("lab1", "AMD-DESKTOP")
        self.ensure.assert_not_called()

    def test_armed_controller_blocks_reads(self):
        self.before["guest"]["armed"] = True
        with self.assertRaisesRegex(ValueError, "not-idle"):
            self.run_read()
        self.xyz_query.assert_not_called()

    def test_wrong_guest_blocks_reads(self):
        self.before["host"]["machineName"] = "RIFT-LAB-1"
        with self.assertRaisesRegex(ValueError, "guest-mismatch"):
            self.run_read()
        self.xyz_query.assert_not_called()

    def test_changed_build_blocks_reads(self):
        self.before["guest"]["target"]["executableSha256"] = "C" * 64
        with self.assertRaisesRegex(ValueError, "build-mismatch"):
            self.run_read()
        self.xyz_query.assert_not_called()

    def test_different_unit_keys_are_not_merged(self):
        self.vitals["metrics"]["unitKey"] = 999
        with self.assertRaisesRegex(ValueError, "unit-changed"):
            self.run_read()

    def test_wrong_process_epoch_is_not_merged(self):
        self.position["gameProcessStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            self.run_read()

    def test_changed_agent_is_not_merged(self):
        self.vitals["activeAgentInstanceId"] = "b" * 32
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            self.run_read()

    def test_changed_vm_is_not_merged(self):
        self.position["vmIdentity"]["startTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            self.run_read()

    def test_postflight_target_change_blocks_publication(self):
        self.after["guest"]["target"]["processId"] += 1
        with self.assertRaisesRegex(ValueError, "postflight-changed"):
            self.run_read()

    def test_no_fallback_after_native_query_failure(self):
        self.xyz_query.side_effect = cli.Blocked("native-xyz-response-stale")
        with self.assertRaises(cli.Blocked):
            self.run_read()
        self.vitals_query.assert_not_called()

    def test_unit_key_validation_rejects_invalid_types_and_ranges(self):
        for value in (True, 0, -1, "01", "1.0", 2**64, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "unit-key-invalid"):
                cli.unit_key(value)

    def test_cli_sanitizes_unexpected_errors(self):
        output = io.StringIO()
        with patch.object(cli, "read_once", side_effect=RuntimeError("private transport value")), redirect_stdout(output):
            code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP"])
        self.assertEqual(2, code)
        self.assertEqual("native-read-unavailable", json.loads(output.getvalue())["reason"])
        self.assertNotIn("private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
