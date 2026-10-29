import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("control_fleet", ROOT / "scripts" / "control_fleet.py")
fleet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fleet)


class ControlFleetTests(unittest.TestCase):
    def write_config(self, root: Path, number: int, *, agent=None, ui=None, guest=None,
                     machine=None, vmx=None, vnc=None, output=None,
                     guest_token=None, operator_token=None):
        lab = f"lab{number}"
        path = root / f"{lab}.json"
        vmx_path = root / (vmx or f"vm-{number}.vmx")
        vmrun = root / "vmrun.exe"
        vmx_path.touch(exist_ok=True); vmrun.touch(exist_ok=True)
        value = {"schemaVersion": 1, "bindAddress": f"192.168.56.{10 + number}",
                 "agentPort": agent or 50000 + number, "uiPort": ui or 51000 + number,
                 "guestAddress": guest or f"192.168.56.{100 + number}",
                 "expectedMachineName": machine or f"RIFT-LAB-{number}",
                 "token": guest_token or f"guest-token-{number:04d}-xxxx",
                 "operatorToken": operator_token or f"operator-token-{number:04d}",
                 "outputDirectory": output or f"output-{number}", "vmx": vmx_path.name,
                 "vmrun": vmrun.name, "vncPort": vnc or 5900 + number}
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def manifest(self, root: Path, configs, reserved=()):
        path = root / "fleet.json"
        path.write_text(json.dumps({"schemaVersion": 1,
            "hosts": [{"lab": f"Lab-{index + 1}", "configPath": config.name}
                      for index, config in enumerate(configs)],
            "reservedEndpoints": list(reserved)}), encoding="utf-8")
        return path

    def test_five_distinct_configs_are_ready_without_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configs = [self.write_config(root, index) for index in range(1, 6)]
            result = fleet.validate_fleet(self.manifest(root, configs, [
                {"address": "192.168.56.1", "port": 49712, "purpose": "live telemetry"}]))
        self.assertEqual("configuration-valid", result["status"])
        self.assertEqual("static-only", result["scope"])
        self.assertEqual(5, result["hostCount"])
        encoded = json.dumps(result)
        self.assertNotIn("guest-token", encoded)
        self.assertNotIn("operator-token", encoded)
        self.assertTrue(all(item["launchArgs"][-2] == "--config" for item in result["assignments"]))

    def test_old_49712_reserved_listener_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.write_config(root, 1, agent=49712)
            manifest = self.manifest(root, [config], [
                {"address": "192.168.56.11", "port": 49712, "purpose": "old receiver"}])
            with self.assertRaisesRegex(fleet.FleetError, "listener-collision"):
                fleet.validate_fleet(manifest)

    def test_rejects_duplicate_vm_vnc_output_guest_machine_and_config(self):
        cases = ("vmx", "vnc", "output", "guest", "machine", "config")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                first = self.write_config(root, 1)
                if case == "config":
                    second = first
                else:
                    kwargs = {case: {"vmx": "vm-1.vmx", "vnc": 5901,
                                     "output": "output-1", "guest": "192.168.56.101",
                                     "machine": "rift-lab-1"}[case]}
                    second = self.write_config(root, 2, **kwargs)
                with self.assertRaises(fleet.FleetError):
                    fleet.validate_fleet(self.manifest(root, [first, second]))

    def test_rejects_incomplete_vm_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.write_config(root, 1)
            value = json.loads(config.read_text(encoding="utf-8"))
            del value["vmrun"]
            config.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(fleet.FleetError):
                fleet.validate_fleet(self.manifest(root, [config]))

    def test_rejects_reserved_port_zero_with_nonempty_valid_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.write_config(root, 1)
            manifest = self.manifest(root, [config], [
                {"address": "127.0.0.1", "port": 0, "purpose": "bad"}])
            with self.assertRaisesRegex(fleet.FleetError, "invalid-reserved-port"):
                fleet.validate_fleet(manifest)

    def test_rejects_reserved_extra_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.write_config(root, 1)
            manifest = root / "bad.json"
            manifest.write_text(json.dumps({"schemaVersion": 1,
                "hosts": [{"lab": "lab1", "configPath": config.name}],
                "reservedEndpoints": [{"address": "127.0.0.1", "port": 52000,
                                       "purpose": "bad", "extra": True}]}), encoding="utf-8")
            with self.assertRaises(fleet.FleetError):
                fleet.validate_fleet(manifest)

    def test_loopback_ui_collision_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.write_config(root, 1, ui=52000)
            second = self.write_config(root, 2, ui=52000)
            with self.assertRaisesRegex(fleet.FleetError, "listener-collision"):
                fleet.validate_fleet(self.manifest(root, [first, second]))

    def test_wildcard_reserved_endpoint_collides_with_specific_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.write_config(root, 1, ui=52000)
            manifest = self.manifest(root, [config], [
                {"address": "0.0.0.0", "port": 52000, "purpose": "wildcard reservation"}])
            with self.assertRaisesRegex(fleet.FleetError, "listener-collision"):
                fleet.validate_fleet(manifest)

    def test_rejects_reused_guest_or_operator_secret_without_disclosure(self):
        for field in ("guest_token", "operator_token"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                secret = "shared-secret-value-12345"
                first = self.write_config(root, 1, **{field: secret})
                second = self.write_config(root, 2, **{field: secret})
                with self.assertRaises(fleet.FleetError) as caught:
                    fleet.validate_fleet(self.manifest(root, [first, second]))
                self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
