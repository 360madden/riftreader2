"""Offline physical-only selection tests; no game input or VMware dependencies."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import physical_rift as physical

IDENTITY = {
    "hostName": "AMD-DESKTOP",
    "processId": 123,
    "hwnd": 456,
    "processStartUtcTicks": "638000000000000001",
    "executableSha256": "a" * 64,
}
REPORT_IDENTITY = {
    "processId": IDENTITY["processId"],
    "processStartUtcTicks": int(IDENTITY["processStartUtcTicks"]),
    "executableSha256": IDENTITY["executableSha256"],
}


class PhysicalOnlySelectionTests(unittest.TestCase):
    def test_amd_desktop_auto_selects_local_process(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY) as reader:
            result = physical.select_physical()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["workflow"], "physical")
        self.assertEqual(result["targetId"], "physical-amd-desktop")
        self.assertEqual(result["ownerHost"], "AMD-DESKTOP")
        self.assertEqual(result["target"], IDENTITY)
        reader.assert_called_once_with(None, require_window=False)

    def test_legion_auto_selects_its_own_process(self):
        legion = {**IDENTITY, "hostName": "LEGION"}
        with patch.object(physical.socket, "gethostname", return_value="LEGION"), \
             patch.object(physical.observe_physical, "_identity", return_value=legion) as reader:
            result = physical.select_physical()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["targetId"], "physical-legion")
        self.assertEqual(result["ownerHost"], "LEGION")
        reader.assert_called_once_with(None, require_window=False)

    def test_explicit_pid_stays_bound_to_local_process(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY) as reader:
            result = physical.select_physical(physical_pid=123)
        self.assertEqual(result["status"], "ready")
        reader.assert_called_once_with(123, require_window=False)

    def test_windowless_identity_is_usable_for_read_only_selection(self):
        # A valid process epoch must not require screenshot eligibility.
        identity = {**IDENTITY, "executablePath": r"C:\Games\RIFT\rift_x64.exe",
                    "hwnd": 0}
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_run",
                          return_value=(0, json.dumps(identity))):
            result = physical.select_physical(expected_host="AMD-DESKTOP",
                                              physical_pid=123)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["target"]["processId"], 123)
        self.assertEqual(result["target"]["processStartUtcTicks"],
                         "638000000000000001")
        self.assertEqual(result["target"]["executableSha256"], "a" * 64)
        self.assertEqual(result["target"]["hwnd"], 0)

    def test_wrong_expected_host_blocks_before_process_probe(self):
        with patch.object(physical.socket, "gethostname", return_value="LEGION"), \
             patch.object(physical.observe_physical, "_identity") as reader:
            result = physical.select_physical(expected_host="AMD-DESKTOP")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "host-mismatch")
        reader.assert_not_called()

    def test_unsupported_host_blocks_before_process_probe(self):
        with patch.object(physical.socket, "gethostname", return_value="OTHER-PC"), \
             patch.object(physical.observe_physical, "_identity") as reader:
            result = physical.select_physical()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "unsupported-host")
        reader.assert_not_called()

    def test_invalid_pid_blocks_before_process_probe(self):
        for pid in (True, 0, -1, 4294967296, "123"):
            with self.subTest(pid=pid), \
                 patch.object(physical.socket, "gethostname", return_value="LEGION"), \
                 patch.object(physical.observe_physical, "_identity") as reader:
                result = physical.select_physical(physical_pid=pid)
                self.assertEqual(result["reason"], "invalid-physical-pid")
                reader.assert_not_called()

    def test_missing_or_ambiguous_rift_fails_without_fallback(self):
        for failure in ("not-running", "ambiguous-process"):
            with self.subTest(failure=failure), \
                 patch.object(physical.socket, "gethostname", return_value="LEGION"), \
                 patch.object(physical.observe_physical, "_identity", side_effect=ValueError(failure)):
                result = physical.select_physical()
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], failure)
            self.assertEqual(result["workflow"], "physical")

    def test_cross_host_identity_and_pid_mismatch_are_blocked(self):
        for identity, kwargs, reason in (
            ({**IDENTITY, "hostName": "LEGION"}, {}, "identity-host-mismatch"),
            (IDENTITY, {"physical_pid": 999}, "physical-pid-mismatch"),
        ):
            with self.subTest(reason=reason), \
                 patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(physical.observe_physical, "_identity", return_value=identity):
                result = physical.select_physical(**kwargs)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], reason)

    def test_native_vitals_reads_only_selected_local_pid_and_epoch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "candidate.json"
            def fake_run(command, **kwargs):
                self.assertEqual(command[0], str(executable))
                self.assertEqual(command[1:6], ["sample-current-vitals", "--pid", "123",
                                                 "--start-ticks", IDENTITY["processStartUtcTicks"]])
                self.assertEqual(command[-2:], ["--output", str(destination)])
                self.assertFalse(kwargs.get("shell", False))
                destination.write_text(json.dumps({"status": "complete", "observation": {
                    "identity": REPORT_IDENTITY, "unitKey": 239816685251645959,
                    "health": {"status": "calculated-candidate", "current": 100, "maximum": 150},
                    "energy": {"status": "unavailable", "current": None, "maximum": None},
                    "mana": {"status": "unavailable", "current": None, "maximum": None}}}),
                    encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                                                   json.dumps({"status": "complete", "output": str(destination),
                                                               "recordType": "native-current-vitals-candidate-summary/2"}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "vitals", destination)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeRead"], "vitals")
        self.assertEqual(result["nativeValues"]["health"]["current"], 100)
        self.assertEqual(result["nativeValues"]["unitKey"], "239816685251645959")
        self.assertIn("candidate-only", result["qualification"])

    def test_native_read_fails_closed_before_launch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "existing.json"
            destination.write_text("original", encoding="utf-8")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run") as runner:
                result = physical.read_native(selected, "vitals", destination)
                self.assertEqual(result["reason"], "native-output-exists")
                result = physical.read_native({**selected, "target": {**IDENTITY,
                                              "hostName": "LEGION"}}, "vitals")
                self.assertEqual(result["reason"], "invalid-local-process-identity")
                result = physical.read_native({**selected, "status": "blocked"}, "vitals")
                self.assertEqual(result["status"], "blocked")
                runner.assert_not_called()
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")

    def test_native_reader_failure_never_promotes_candidate(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", return_value=subprocess.CompletedProcess(
                     [], 2, "", "wrong-build")):
                result = physical.read_native(selected, "position", Path(temporary) / "new.json")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "native-reader-failed")
        self.assertEqual(result["exitCode"], 2)

    def test_position_stream_uses_final_summary_not_first_sample(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "position.json"
            def fake_run(command, **kwargs):
                destination.write_text(json.dumps({"status": "complete",
                    "identity": REPORT_IDENTITY, "observations": [{"unitKey": "239816685251645959",
                    "x": 1.5, "y": 2.5, "z": 3.5, "completedAtUtc": "now"}]}), encoding="utf-8")
                samples = [json.dumps({"recordType": "native-current-position-candidate/1",
                                       "observation": {"x": 1}})]
                samples.append(json.dumps({"recordType": "native-current-position-candidate-summary/1",
                                           "status": "complete", "output": str(destination)}))
                return subprocess.CompletedProcess(command, 0, "\n".join(samples) + "\n", "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selected, "position", destination)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeSummary"]["recordType"],
                         "native-current-position-candidate-summary/1")
        self.assertEqual(result["nativeValues"]["x"], 1.5)
        self.assertEqual(result["nativeValues"]["unitKey"], "239816685251645959")

    def test_native_report_rejects_wrong_type_or_process_epoch(self):
        selected = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": IDENTITY}
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(temporary) / "candidate.json"
            def wrong_type(command, **kwargs):
                destination.write_text(json.dumps({"status": "complete", "identity": REPORT_IDENTITY}),
                                       encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                    json.dumps({"recordType": "native-current-stats-summary/1",
                                "status": "complete", "output": str(destination)}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=wrong_type):
                result = physical.read_native(selected, "position", destination)
            self.assertEqual(result["reason"], "invalid-native-reader-receipt")
            destination.unlink()
            def wrong_epoch(command, **kwargs):
                destination.write_text(json.dumps({"status": "complete", "observation": {
                    "identity": {**REPORT_IDENTITY, "processStartUtcTicks": 1},
                    "unitKey": 123, "health": {"status": "unavailable"},
                    "energy": {"status": "unavailable"}, "mana": {"status": "unavailable"}}}),
                    encoding="utf-8")
                return subprocess.CompletedProcess(command, 0,
                    json.dumps({"recordType": "native-current-vitals-candidate-summary/2",
                                "status": "complete", "output": str(destination)}), "")
            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.subprocess, "run", side_effect=wrong_epoch):
                result = physical.read_native(selected, "vitals", destination)
            self.assertEqual(result["reason"], "invalid-native-reader-report")

    def test_native_read_requires_explicit_host_before_process_probe(self):
        with patch.object(physical, "select_physical") as selector, \
             redirect_stdout(io.StringIO()) as output:
            code = physical.main(["--read-native", "vitals"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["reason"],
                         "native-read-requires-expected-host")
        selector.assert_not_called()

    def test_native_read_cli_keeps_json_receipt(self):
        with patch.object(physical, "select_physical", return_value={"status": "ready"}), \
             patch.object(physical, "read_native", return_value={"status": "complete", "nativeRead": "stats"}) as reader, \
             redirect_stdout(io.StringIO()) as output:
            code = physical.main(["--expected-host", "AMD-DESKTOP", "--read-native", "stats"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["nativeRead"], "stats")
        reader.assert_called_once_with({"status": "ready"}, "stats", None)

    def test_cli_default_is_current_physical_host_and_json(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY), \
             redirect_stdout(io.StringIO()) as output:
            code = physical.main([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["targetId"], "physical-amd-desktop")


if __name__ == "__main__":
    unittest.main()
