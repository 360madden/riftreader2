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


    def create_delivery_evidence(self):
        """Host-side receipts with a mock exact-VM handover identity."""
        plan = {"vmIdentity": {"vmx": "pinned-test-vmx", "epoch": 17}}
        events = (self.root / "artifacts" / "validation"
                  / "rr2-scout-copy-publish-oct24-01" / "transfer-events")
        events.mkdir(parents=True)
        process = {
            "pid": 31415, "purpose": "one-use-typed-inline-download",
            "vmIdentity": plan["vmIdentity"], "windowsSessionId": 2,
            "inJob": False,
        }
        exited = {"pid": 31415, "phase": "download"}
        delivered = {
            "serverPid": 31415, "state": "delivered", "bundle": "typed-inline",
            "path": "/rr2-typed-inline-oct24-01.exe",
            "sha256": trial.BUNDLE_SHA, "bytes": trial.BUNDLE_BYTES,
            "deliveredBytes": trial.BUNDLE_BYTES, "incompleteResponses": 0,
            "host": "192.168.56.1", "guest": "192.168.56.128",
        }
        process_path = self.root / "rr2-inline-download-process.json"
        exit_path = self.root / "rr2-inline-download-exited.json"
        event_path = events / "transfer.json"
        process_path.write_text(json.dumps(process))
        exit_path.write_text(json.dumps(exited))
        event_path.write_text(json.dumps(delivered))
        return plan, process_path, exit_path, event_path, process, exited, delivered

    def test_download_completion_accepts_exact_delivered_bundle_only(self):
        plan, *_ = self.create_delivery_evidence()
        with patch.object(trial, "ROOT", self.root), patch.object(
                trial, "HOME", self.root):
            trial.require_download_delivered(plan)

    def test_download_completion_blocks_missing_receipts_or_transfer_event(self):
        plan, process_path, exit_path, event_path, process, exited, delivered = (
            self.create_delivery_evidence())
        with patch.object(trial, "ROOT", self.root), patch.object(
                trial, "HOME", self.root):
            for file, value in ((event_path, delivered), (exit_path, exited),
                                (process_path, process)):
                with self.subTest(missing=file.name):
                    file.unlink()
                    with self.assertRaises(Blocked):
                        trial.require_download_delivered(plan)
                    file.write_text(json.dumps(value))

    def test_download_completion_rejects_partial_or_wrong_transfer(self):
        plan, process_path, exit_path, event_path, process, exited, delivered = (
            self.create_delivery_evidence())
        invalid = [
            (event_path, delivered, "state", "sending"),
            (event_path, delivered, "deliveredBytes", trial.BUNDLE_BYTES - 1),
            (event_path, delivered, "incompleteResponses", 1),
            (event_path, delivered, "sha256", "F" * 64),
            (event_path, delivered, "guest", "192.168.56.200"),
            (event_path, delivered, "serverPid", 31416),
            (process_path, process, "inJob", True),
            (process_path, process, "windowsSessionId", 0),
            (process_path, process, "vmIdentity", {"epoch": 18}),
            (exit_path, exited, "phase", "claim"),
        ]
        with patch.object(trial, "ROOT", self.root), patch.object(
                trial, "HOME", self.root):
            for file, baseline, key, bad in invalid:
                with self.subTest(file=file.name, key=key):
                    changed = dict(baseline)
                    changed[key] = bad
                    file.write_text(json.dumps(changed))
                    with self.assertRaises(Blocked):
                        trial.require_download_delivered(plan)
                    file.write_text(json.dumps(baseline))

    def test_step_four_cannot_issue_input_before_real_bundle_delivery(self):
        plan, *_ = self.create_delivery_evidence()
        event = (self.root / "artifacts" / "validation"
                 / "rr2-scout-copy-publish-oct24-01" / "transfer-events"
                 / "transfer.json")
        event.unlink()
        previous = self.root / (trial.PREFIX + "03")
        previous.mkdir()
        (previous / "receipt.json").write_text('{"status":"completed"}')
        with patch.object(trial, "HOME", self.root), patch.object(
                trial, "ROOT", self.root), patch.object(
                trial, "maintenance", return_value=plan), patch.object(
                trial, "commands", return_value=[("test", "Write-Output 1")] * 4):
            with self.assertRaisesRegex(Blocked, "guest-executable-download-event-scope-invalid"):
                trial.execute(4)
        self.assertFalse((self.root / (trial.PREFIX + "04")).exists())

    def test_upload_transition_requires_claim_exit_and_exact_claim(self):
        with patch.object(trial, "HOME", self.root):
            with self.assertRaisesRegex(Blocked, "claim-server-not-exited"):
                trial.require_claim_received()
            (self.root / "rr2-inline-claim-exited.json").write_text("{}")
            from scripts import run_guest_inline_service as service
            with patch.object(service, "upload_digest", return_value="A" * 64) as verified:
                trial.require_claim_received()
                verified.assert_called_once_with()
            with patch.object(service, "upload_digest",
                              side_effect=Blocked("claim-provenance-invalid")):
                with self.assertRaisesRegex(Blocked, "claim-provenance-invalid"):
                    trial.require_claim_received()


if __name__ == "__main__":
    unittest.main()
