"""No-input regression tests for the two-lab managed observation receiver."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import ensure_receiver as receiver
from scripts.operation_dependencies import DependencyUnavailable


class ManagedReceiverTests(unittest.TestCase):
    def test_unknown_lab_fails_closed(self):
        with self.assertRaisesRegex(DependencyUnavailable, "unknown-lab"):
            receiver._config("lab3")

    def test_config_requires_exact_per_lab_address_and_port(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "receiver.json"
            conf = {"bindAddress": receiver.BIND, "port": receiver.PORTS["lab1"],
                    "guestSubnet": "192.168.56.0/24", "token": "a" * 40}
            source = Path(scratch) / "source.py"
            source.write_text("test-only")
            with mock.patch.dict(receiver.CONFIGS, {"lab1": path}), \
                 mock.patch.object(receiver, "SOURCE", source), \
                 mock.patch.object(receiver, "SOURCE_SHA256", receiver.sha(source)), \
                 mock.patch.object(receiver, "ENTRY", source), \
                 mock.patch.object(receiver, "MANAGER", source):
                path.write_text(json.dumps(conf))
                self.assertEqual(receiver._config("lab1"), path)
                conf["port"] = receiver.PORTS["lab2"]
                path.write_text(json.dumps(conf))
                with self.assertRaisesRegex(DependencyUnavailable, "private-config-mismatch"):
                    receiver._config("lab1")

    def test_probe_missing_listener_returns_none(self):
        with mock.patch.object(receiver, "_port_owners", return_value=[]):
            self.assertIsNone(receiver._probe("lab1", Path("not-read.json")))

    def test_probe_other_address_does_not_adopt_listener(self):
        with mock.patch.object(receiver, "_port_owners",
                               return_value=[("127.0.0.1", 123)]):
            with self.assertRaisesRegex(DependencyUnavailable, "receiver-listener-collision"):
                receiver._probe("lab1", Path("not-read.json"))

    def test_probe_refuses_unowned_receiver(self):
        candidate = {"pid": 123, "processStartUtcTicks": 1000, "image": "pythonw.exe"}
        with mock.patch.object(receiver, "_port_owners", return_value=[(receiver.BIND, 123)]), \
             mock.patch("scripts.launch_live_reader.receiver_preflight",
                        return_value=(candidate, "private-token", "endpoint")), \
             mock.patch.object(receiver, "_matching_receipt", return_value=False):
            with self.assertRaisesRegex(DependencyUnavailable, "receiver-listener-not-owned"):
                receiver._probe("lab1", Path("not-read.json"))

    def test_matching_receipt_pins_process_epoch_and_sources(self):
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch)
            output = base / "lab1" / "run1"
            output.mkdir(parents=True)
            config_path = base / "receiver.json"
            config_path.write_text("no-credential")
            expected = {"pid": 13, "processStartUtcTicks": 123 + receiver.WINDOWS_TICKS_OFFSET,
                        "image": "C:/Python314/pythonw.exe"}
            receipt = {"lab": "lab1", "pid": 13, "configSha256": "hash",
                       "sourceSha256": receiver.SOURCE_SHA256, "entrySha256": "hash",
                       "processIdentity": {"startTicks": 123,
                                           "image": expected["image"]}}
            (output / "process.json").write_text(json.dumps(receipt))
            with mock.patch.object(receiver, "TASKS", base), \
                 mock.patch.object(receiver, "sha", return_value="hash"):
                self.assertTrue(receiver._matching_receipt("lab1", expected, config_path))
                malformed_dir = base / "lab1" / "malformed"
                malformed_dir.mkdir()
                malformed_path = malformed_dir / "process.json"
                for malformed in (None, [], 1, "receipt", {"processIdentity": None},
                                  {"processIdentity": []},
                                  {"processIdentity": {"image": []}}):
                    with self.subTest(malformed=malformed):
                        malformed_path.write_text(json.dumps(malformed))
                        self.assertTrue(receiver._matching_receipt("lab1", expected, config_path))
                expected["processStartUtcTicks"] += 1
                self.assertFalse(receiver._matching_receipt("lab1", expected, config_path))

    def test_task_status_rejects_non_object_json(self):
        for value in (None, [], 1, "Running"):
            with self.subTest(value=value), \
                 mock.patch.object(receiver.subprocess, "run", return_value=mock.Mock(
                     returncode=0, stdout=json.dumps(value).encode("utf-8"))):
                with self.assertRaisesRegex(DependencyUnavailable, "managed-helper-status-invalid"):
                    receiver._task_status("lab1")

    def test_ensure_reuses_without_starting_duplicate(self):
        candidate = {"pid": 123}
        with mock.patch.object(receiver, "_config", return_value=Path("safe")), \
             mock.patch.object(receiver, "_probe", return_value=candidate), \
             mock.patch.object(receiver, "_launch") as launch:
            result = receiver.ensure("lab1")
            self.assertEqual(result["state"], "reused")
            launch.assert_not_called()

    def test_ensure_starts_once_and_verifies_postflight(self):
        candidate = {"pid": 123}
        from contextlib import nullcontext
        with mock.patch.object(receiver, "_config", return_value=Path("safe")), \
             mock.patch.object(receiver, "_probe",
                               side_effect=[None, None, candidate]) as probe, \
             mock.patch.object(receiver, "_launch", return_value="rr2-receiver-lab1") as launch, \
             mock.patch.object(receiver, "_launch_lock", return_value=nullcontext()), \
             mock.patch.object(receiver.time, "sleep"):
            result = receiver.ensure("lab1")
            self.assertEqual(result["state"], "started")
            self.assertEqual(result["receiver"], candidate)
            launch.assert_called_once_with("lab1")
            self.assertEqual(probe.call_count, 3)

    def test_ensure_does_not_launch_when_endpoint_collides(self):
        with mock.patch.object(receiver, "_config", return_value=Path("safe")), \
             mock.patch.object(receiver, "_probe",
                               side_effect=DependencyUnavailable("receiver", "receiver-listener-collision")), \
             mock.patch.object(receiver, "_launch") as launch:
            with self.assertRaisesRegex(DependencyUnavailable, "receiver-listener-collision"):
                receiver.ensure("lab1")
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
