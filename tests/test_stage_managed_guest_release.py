"""Offline guards for managed VMware release staging; never touches a VM."""
import base64
from pathlib import Path
import unittest

from scripts.ensure_guest_agent import GUEST_ROOT
from scripts.stage_managed_guest_release import _preflight, _finalize, _quoted, stage
from scripts.vmware_guest_session import MAX_ENCODED_POWERSHELL_CHARS


class ManagedReleaseStagingTests(unittest.TestCase):
    def test_powershell_literal_quote_escapes_apostrophe(self):
        self.assertEqual(_quoted("a'b"), "'a''b'")

    def test_preflight_requires_running_matching_active_release_and_empty_request(self):
        script = _preflight(GUEST_ROOT, "agent-5ac456958028")
        for guard in ("active-descriptor-mismatch", "active-hash-mismatch",
                      "active-process-mismatch", "launcher-busy", "candidate-exists"):
            self.assertIn(guard, script)

    def test_finalize_verifies_transferred_and_staged_hash_without_activation(self):
        sha = "A" * 64
        script = _finalize(GUEST_ROOT, "agent-aaaaaaaaaaaa", sha, 118028128,
                           GUEST_ROOT + "\\stage-agent-" + "b" * 32 + ".incoming",
                           GUEST_ROOT + "\\stage-proof-" + "b" * 32 + ".json")
        self.assertIn("incoming-hash-mismatch", script)
        self.assertIn("staged-hash-mismatch", script)
        self.assertIn("active-release-changed", script)
        self.assertIn("[IO.File]::Move", script)
        self.assertNotIn("Stop-Process", script)
        self.assertNotIn("current.json')|Set-", script)

    def test_real_length_scripts_fit_safe_vmware_encoded_argv_limit(self):
        sha = "5AC4569580282DDB97BA2A9DCB08AEC2B626FCF97C4EDD04DBA08E5EC18998A3"
        scripts = (
            _preflight(GUEST_ROOT, "agent-5ac456958028"),
            _finalize(GUEST_ROOT, "agent-5ac456958028", sha, 118028128,
                      GUEST_ROOT + "\\stage-agent-" + "f" * 32 + ".incoming",
                      GUEST_ROOT + "\\stage-proof-" + "f" * 32 + ".json"),
        )
        for script in scripts:
            with self.subTest(length=len(script)):
                self.assertLessEqual(len(base64.b64encode(script.encode("utf-16-le"))),
                                     MAX_ENCODED_POWERSHELL_CHARS)

    def test_invalid_lab_fails_before_any_executable_or_vm_action(self):
        with self.assertRaisesRegex(Exception, "Invalid managed lab"):
            stage("wrong-lab", Path("not-present.exe"), Path("not-created"))


if __name__ == "__main__":
    unittest.main()
