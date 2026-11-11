"""Offline physical native host-route tests; no socket, reader, VM or input."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import control_host as host

PID = 44888
TICKS = 639299470183328173
SHA = "a" * 64
MACHINE = "AMD-DESKTOP"
TARGET = {"hostName": MACHINE, "processId": PID,
          "processStartUtcTicks": str(TICKS), "executableSha256": SHA,
          "hwnd": 123}
REQUEST = {"machineName": MACHINE, "processId": PID,
           "processStartUtcTicks": TICKS, "executableSha256": SHA}


def physical_config(directory):
    return host.HostConfig(
        "192.168.1.5", 49920, 49921, "192.168.1.5",
        MACHINE, "T" * 32, "O" * 32, Path(directory),
        physical_process_id=PID, physical_process_start_utc_ticks=TICKS,
        physical_executable_sha256=SHA)


class PhysicalNativeHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        hostname = patch.object(host.socket, "gethostname", return_value=MACHINE)
        hostname.start()
        self.addCleanup(hostname.stop)

    def gateway(self, config=None):
        config = config or physical_config(self.temp.name)
        journal = host.EvidenceJournal(Path(self.temp.name) / "journal")
        return host.AgentGateway(config, journal)

    def load(self, **overrides):
        payload = {
            "schemaVersion": 1, "bindAddress": "192.168.1.5",
            "agentPort": 49920, "uiPort": 49921,
            "guestAddress": "192.168.1.5", "expectedMachineName": MACHINE,
            "token": "T" * 32, "operatorToken": "O" * 32,
            "outputDirectory": self.temp.name,
            "physicalProcessId": PID, "physicalProcessStartUtcTicks": TICKS,
            "physicalExecutableSha256": SHA,
        }
        payload.update(overrides)
        path = Path(self.temp.name) / "physical-config.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return host.HostConfig.load(path)

    def test_explicit_local_physical_config_loads_without_vm(self):
        config = self.load()
        self.assertEqual(config.physical_process_id, PID)
        self.assertEqual(config.physical_process_start_utc_ticks, TICKS)
        self.assertEqual(config.physical_executable_sha256, SHA)
        self.assertIsNone(config.vmx)

    def test_incomplete_or_mixed_or_cross_host_config_rejected(self):
        cases = [
            {"physicalProcessId": None},
            {"physicalProcessStartUtcTicks": None},
            {"physicalExecutableSha256": None},
            {"physicalProcessId": True},
            {"physicalExecutableSha256": "g" * 64},
            {"expectedMachineName": "LEGION"},
            {"guestAddress": "192.168.1.6"},
            {"vmx": "C:/vm.vmx", "vmrun": "C:/vmrun.exe", "vncPort": 5901},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(host.ControlHostError):
                self.load(**change)

    def test_xyz_and_orientation_return_distinct_candidate_receipts(self):
        for operation, kind in (("native-xyz", "position"),
                                ("native-orientation", "orientation")):
            calls = []
            summary = {"recordType": host._physical_rift_module().NATIVE_RECEIPTS[kind]}
            selection = {"status": "ready", "target": dict(TARGET)}
            def select_physical(**kwargs):
                calls.append(("select", kwargs))
                return selection
            def read_native(actual, requested):
                calls.append(("read", requested))
                return {"status": "complete", "nativeRead": requested,
                        "target": dict(TARGET), "nativeSummary": summary,
                        "nativeValues": {"unitKey": "239816685251645959"},
                        "nativeOutput": "artifacts/test-native.json"}
            fake = SimpleNamespace(select_physical=select_physical,
                                   read_native=read_native,
                                   NATIVE_RECEIPTS={kind: summary["recordType"]})
            with self.subTest(operation=operation), patch.object(
                    host, "_physical_rift_module", return_value=fake):
                result = self.gateway().command(operation, dict(REQUEST))
            self.assertEqual([entry[0] for entry in calls], ["select", "read", "select"])
            self.assertEqual(result["recordType"], "physical-host-native-candidate/1")
            self.assertEqual(result["nativeKind"], kind)
            self.assertIs(result["movementEligible"], False)
            self.assertIs(result["headingQualified"], False)
            self.assertEqual(result["target"], TARGET)

    def test_wrong_requested_pid_epoch_sha_or_machine_refuses_before_reader(self):
        for field, value in (("processId", PID + 1),
                             ("processStartUtcTicks", TICKS + 1),
                             ("executableSha256", "b" * 64),
                             ("machineName", "LEGION")):
            fake = SimpleNamespace(select_physical=lambda **_: self.fail("read probed"))
            with self.subTest(field=field), patch.object(
                    host, "_physical_rift_module", return_value=fake), self.assertRaisesRegex(
                    host.ControlHostError, "configured process epoch"):
                self.gateway().command("native-xyz", {**REQUEST, field: value})

    def test_changed_selection_or_native_receipt_refuses_without_success(self):
        base = {"status": "ready", "target": dict(TARGET)}
        changed = {"status": "ready", "target": {**TARGET, "processStartUtcTicks": str(TICKS + 1)}}
        for case in ("first", "second", "receipt"):
            selection_count = 0
            def select_physical(**_):
                nonlocal selection_count
                selection_count += 1
                return changed if case == "first" or (case == "second" and selection_count == 2) else base
            def read_native(*_):
                return {"status": "complete", "nativeRead": "position",
                        "target": changed["target"] if case == "receipt" else TARGET,
                        "nativeSummary": {"recordType": "native-current-position-candidate-summary/1"},
                        "nativeValues": {"unitKey": "1"}}
            fake = SimpleNamespace(select_physical=select_physical,
                                   read_native=read_native,
                                   NATIVE_RECEIPTS={"position": "native-current-position-candidate-summary/1"})
            with self.subTest(case=case), patch.object(host, "_physical_rift_module",
                    return_value=fake), self.assertRaises(host.ControlHostError):
                self.gateway().command("native-xyz", dict(REQUEST))

    def test_legacy_unbound_route_still_requires_guest_session(self):
        unbound = host.HostConfig(
            "192.168.1.5", 49920, 49921, "192.168.1.6",
            MACHINE, "T" * 32, "O" * 32, Path(self.temp.name))
        with patch.object(host, "_physical_rift_module",
                          side_effect=AssertionError("must not call physical reader")):
            with self.assertRaisesRegex(host.ControlHostError,
                                        "no authenticated guest"):
                self.gateway(unbound).command("native-xyz", dict(REQUEST))


if __name__ == "__main__":
    unittest.main()
