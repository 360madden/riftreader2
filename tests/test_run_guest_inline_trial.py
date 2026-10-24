"""Offline fail-closed tests for the exact-epoch typed-inline VM guest stepper."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import run_guest_inline_trial as trial
from scripts.vm_console_native import Blocked


class InlineGuestTrialTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.request = self.root / "request.json"
        self.record = {
            "schemaVersion": 1,
            "evidenceKind": "native-typed-inline-capture-request/1",
            "target": {
                "processId": trial.PID,
                "processStartUtcTicks": trial.TICKS,
                "executableSha256": trial.GAME_SHA,
            },
            "startAddress": "0x10000", "maxScanBytes": 536870912,
            "maxDurationMilliseconds": 30000, "maxRegionCount": 32768,
            "maxMatchCount": 128, "maxCopiedCandidates": 8,
        }
        self.use_record()

    def use_record(self):
        self.request.write_text(
            json.dumps(self.record, indent=2) + "\n", encoding="utf-8")

    def patched_request(self):
        return (
            patch.object(trial, "REQUEST", self.request),
            patch.object(trial, "REQUEST_SHA",
                         trial.sha(self.request.read_bytes())),
        )

    def test_valid_exact_64_bit_epoch(self):
        a, b = self.patched_request()
        with a, b:
            data = trial.check_request()
            self.assertEqual(json.loads(data)["target"]["processStartUtcTicks"],
                             639284177321390013)

    def test_truncated_64_bit_epoch_fails_even_with_matching_file_hash(self):
        self.record["target"]["processStartUtcTicks"] = 639284177321390000
        self.use_record()
        a, b = self.patched_request()
        with a, b, self.assertRaisesRegex(Blocked, "epoch-or-bounds"):
            trial.check_request()

    def test_wrong_game_sha_fails_even_with_matching_file_hash(self):
        self.record["target"]["executableSha256"] = "A" * 64
        self.use_record()
        a, b = self.patched_request()
        with a, b, self.assertRaisesRegex(Blocked, "epoch-or-bounds"):
            trial.check_request()

    def test_expanded_read_scope_fails_even_with_matching_file_hash(self):
        self.record["maxScanBytes"] += 65536
        self.use_record()
        a, b = self.patched_request()
        with a, b, self.assertRaisesRegex(Blocked, "epoch-or-bounds"):
            trial.check_request()

    def test_modified_request_bytes_fail_pin(self):
        a, _ = self.patched_request()
        with a, self.assertRaisesRegex(Blocked, "content-changed"):
            trial.check_request()

    def test_generated_commands_have_bounded_stages_and_strict_routes(self):
        a, b = self.patched_request()
        with a, b:
            commands = trial.commands()
            self.assertEqual(len(commands), 31)
            self.assertEqual([x[0] for x in commands][-6:],
                             ["claim", "claim", "claim", "claim", "upload", "upload"])
            self.assertLessEqual(max(map(lambda x: len(x[1]), commands)), 350)
            self.assertIn("scout-copy-typed-native",
                          " ".join(command for _, command in commands))
            joined = "\n".join(command for _, command in commands)
            self.assertIn("/rr2-typed-inline-oct24-01.exe", joined)
            self.assertIn("/rr2-typed-inline-zip-claim-oct24-01", joined)
            self.assertIn("/rr2-map-oct24-01-report.json", joined)
            self.assertNotIn("Set-Process", joined)
            self.assertNotIn("WriteProcessMemory", joined)
            self.assertNotIn("SendKeys", joined)

    def test_no_guest_input_before_normal_v14_exit(self):
        with patch.object(trial, "HOME", self.root):
            with self.assertRaisesRegex(Blocked, "normal-stop-marker-missing"):
                trial.maintenance()
            (self.root / "STOP-NATIVE-20261024-V14.request").write_text("")
            with self.assertRaisesRegex(Blocked, "normal-exit-receipt-missing"):
                trial.maintenance()

    def test_reject_active_v15_owner(self):
        (self.root / "STOP-NATIVE-20261024-V14.request").write_text("")
        (self.root / "coordinated-host-v14-exited.json").write_text("{}")
        (self.root / "coordinated-host-v15-process.json").write_text("{}")
        with patch.object(trial, "HOME", self.root):
            with self.assertRaisesRegex(Blocked, "v15-already-started"):
                trial.maintenance()

    def test_authority_requires_blocked_unheld_no_cleanup(self):
        (self.root / "STOP-NATIVE-20261024-V14.request").write_text("")
        (self.root / "coordinated-host-v14-exited.json").write_text("{}")
        plan = {"configSha256":
                "90F2B8AB6F575C776941F0B160FF4CE1D8BC8575408975FE7645ADDED5325A2C",
                "database": str(self.root / "queue.sqlite3"),
                "resource": "vm:rift-lab-1", "vmIdentity": {}}
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan))
        with patch.object(trial, "HOME", self.root), patch.object(trial, "PLAN", path):
            for returned in ((0, None, "receipt"), (1, "owner", None),
                             (1, None, "receipt")):
                with self.subTest(returned=returned), patch.object(
                        trial, "authority_snapshot", return_value=returned):
                    with self.assertRaisesRegex(Blocked, "not-quarantined"):
                        trial.maintenance()
            with patch.object(trial, "authority_snapshot",
                              return_value=(1, None, None)):
                self.assertEqual(trial.maintenance(), plan)


if __name__ == "__main__":
    unittest.main()
