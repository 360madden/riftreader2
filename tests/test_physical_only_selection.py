"""Offline physical-only selection tests; no game input or VMware dependencies."""
import io
import json
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
        reader.assert_called_once_with(None)

    def test_legion_auto_selects_its_own_process(self):
        legion = {**IDENTITY, "hostName": "LEGION"}
        with patch.object(physical.socket, "gethostname", return_value="LEGION"), \
             patch.object(physical.observe_physical, "_identity", return_value=legion) as reader:
            result = physical.select_physical()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["targetId"], "physical-legion")
        self.assertEqual(result["ownerHost"], "LEGION")
        reader.assert_called_once_with(None)

    def test_explicit_pid_stays_bound_to_local_process(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY) as reader:
            result = physical.select_physical(physical_pid=123)
        self.assertEqual(result["status"], "ready")
        reader.assert_called_once_with(123)

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

    def test_cli_default_is_current_physical_host_and_json(self):
        with patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(physical.observe_physical, "_identity", return_value=IDENTITY), \
             redirect_stdout(io.StringIO()) as output:
            code = physical.main([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["targetId"], "physical-amd-desktop")


if __name__ == "__main__":
    unittest.main()
