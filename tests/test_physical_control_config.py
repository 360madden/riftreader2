"""Offline pairing of physical RIFT control host and .NET agent configuration."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_control_config as config
from scripts.control_host import HostConfig

HOST = socket.gethostname()
PID = 1876544
TICKS = 639299470183328173
SHA = "a" * 64
IP = "192.168.1.166"
INTERFACES = [
    {"IPAddress": IP, "InterfaceAlias": "Wi-Fi"},
    {"IPAddress": "192.168.56.1", "InterfaceAlias": "VMware Network Adapter VMnet8"},
]
TARGET = {
    "hostName": HOST,
    "processId": PID,
    "processStartUtcTicks": str(TICKS),
    "executablePath": r"C:\Games\RIFT\Live\rift_x64.exe",
    "executableSha256": SHA,
    "hwnd": 0,
}


def ready(**changes):
    return {"status": "ready", "workflow": "physical", "ownerHost": HOST,
            "target": {**TARGET, **changes}}


class PhysicalControlConfigTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.calls = []

    def selector(self, **kwargs):
        self.calls.append(kwargs)
        return ready()

    def make(self, **kwargs):
        return config.create_config(
            kwargs.pop("host", HOST), kwargs.pop("pid", PID),
            kwargs.pop("local_ip", IP), kwargs.pop("agent_port", 49001),
            kwargs.pop("ui_port", 49002), self.root,
            selector=kwargs.pop("selector", self.selector),
            interface_provider=kwargs.pop("interfaces", lambda: INTERFACES))

    def test_creates_compatible_pair_without_logging_secret(self):
        receipt = self.make()
        self.assertEqual(receipt["status"], "physical-config-pair-created")
        self.assertEqual(self.calls, [{"expected_host": HOST, "physical_pid": PID}] * 2)
        self.assertFalse(receipt["gameInputSent"])
        self.assertFalse(receipt["serviceStarted"])
        host = json.loads(Path(receipt["hostConfigPath"]).read_text(encoding="utf-8"))
        agent = json.loads(Path(receipt["agentConfigPath"]).read_text(encoding="utf-8"))
        self.assertEqual(host["bindAddress"], IP)
        self.assertEqual(host["guestAddress"], IP)
        self.assertEqual(agent["hostAddress"], IP)
        self.assertEqual(host["agentPort"], agent["port"])
        self.assertEqual(host["token"], agent["token"])
        self.assertEqual(host["outputDirectory"], agent["outputDirectory"])
        from scripts.nav_physical_reservation import PhysicalClientIdentity
        from scripts.physical_one_pulse_runner import _agent_config_matches
        _agent_config_matches(Path(receipt["agentConfigPath"]),
                              HostConfig.load(Path(receipt["hostConfigPath"])),
                              PhysicalClientIdentity(HOST, PID, TICKS, SHA))
        self.assertNotEqual(host["token"], host["operatorToken"])
        self.assertGreaterEqual(len(host["token"]), 32)
        self.assertEqual(agent["boundProcessId"], PID)
        self.assertEqual(agent["boundProcessStartUtcTicks"], TICKS)
        self.assertEqual(agent["processName"], "rift_x64")
        self.assertEqual(agent["executablePath"], TARGET["executablePath"])
        self.assertEqual(set(agent), {"schemaVersion", "hostAddress", "port", "token",
                                      "expectedMachineName", "processName", "executablePath",
                                      "executableSha256", "outputDirectory", "boundProcessId",
                                      "boundProcessStartUtcTicks"})
        self.assertFalse(any(key in host for key in ("vmx", "vmrun", "vncPort")))
        self.assertEqual(HostConfig.load(Path(receipt["hostConfigPath"])).physical_process_id, PID)
        self.assertNotIn(host["token"], json.dumps(receipt))
        self.assertNotIn(host["operatorToken"], json.dumps(receipt))
        self.assertTrue(Path(host["outputDirectory"]).is_dir())
        self.assertTrue(Path(agent["outputDirectory"]).is_dir())

    def test_session_directory_unique_and_files_never_overwritten(self):
        first = self.make()
        second = self.make()
        self.assertNotEqual(first["hostConfigPath"], second["hostConfigPath"])
        a = json.loads(Path(first["hostConfigPath"]).read_text(encoding="utf-8"))
        b = json.loads(Path(second["hostConfigPath"]).read_text(encoding="utf-8"))
        self.assertNotEqual(a["token"], b["token"])

    def test_host_ip_vm_adapter_and_port_refusals_precede_selection(self):
        for changes in (
            {"host": "LEGION"},
            {"pid": 0},
            {"pid": True},
            {"local_ip": "127.0.0.1"},
            {"local_ip": "192.168.56.1"},
            {"local_ip": "192.168.1.167"},
            {"agent_port": 80},
            {"agent_port": 49002},
        ):
            with self.subTest(changes=changes), self.assertRaises(config.PhysicalConfigError):
                self.make(**changes)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_process_epoch_drift_before_writing_is_blocked(self):
        def selector(**kwargs):
            self.calls.append(kwargs)
            return ready() if len(self.calls) == 1 else ready(processStartUtcTicks=str(TICKS + 1))
        with self.assertRaisesRegex(config.PhysicalConfigError, "changed"):
            self.make(selector=selector)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_executable_and_blocked_selector_are_refused(self):
        for report in (ready(executablePath=r"C:\bad.exe"),
                       {"status": "blocked", "workflow": "physical", "reason": "not-running"}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                self.make(selector=lambda **_: report)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cli_blocks_without_emitting_token(self):
        with patch.object(config, "create_config",
                          side_effect=config.PhysicalConfigError("test-blocked")):
            out = io.StringIO()
            with redirect_stdout(out):
                code = config.main(["--host", HOST, "--pid", str(PID),
                                    "--local-ip", IP, "--agent-port", "49001",
                                    "--ui-port", "49002", "--output-root", str(self.root)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "blocked")
        self.assertNotIn("token", out.getvalue())


if __name__ == "__main__":
    unittest.main()
