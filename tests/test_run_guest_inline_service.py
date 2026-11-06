"""Dry-run boundary tests for independent one-use native guest services."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import run_guest_inline_service as service
from scripts import run_guest_inline_trial as trial
from scripts.vm_console_native import Blocked


class GuardedServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def receipt_step(self, n):
        folder = self.home / (trial.PREFIX + f"{n:02}")
        folder.mkdir(exist_ok=True)
        (folder / "receipt.json").write_text(
            json.dumps({"status": "completed", "step": n}), encoding="utf-8")

    def test_phase_boundaries_require_previous_steps(self):
        with patch.object(service, "HOME", self.home):
            for phase in ("download", "claim", "upload"):
                with self.subTest(phase=phase), self.assertRaisesRegex(
                        Blocked, "step-boundary-invalid"):
                    service.phase_steps(phase)

    def test_phase_cannot_begin_if_guest_sent_future_step(self):
        self.receipt_step(2)
        self.receipt_step(3)
        with patch.object(service, "HOME", self.home):
            with self.assertRaisesRegex(Blocked, "step-boundary-invalid"):
                service.phase_steps("download")

    def test_download_boundary_accepts_only_step_two_receipt(self):
        self.receipt_step(2)
        with patch.object(service, "HOME", self.home):
            service.phase_steps("download")

    def test_claim_requires_download_server_exit(self):
        self.receipt_step(28)
        with patch.object(service, "HOME", self.home):
            with self.assertRaisesRegex(Blocked, "bundle-server-not-exited"):
                service.phase_steps("claim")
            (self.home / "rr2-inline-download-exited.json").write_text("{}")
            service.phase_steps("claim")

    def test_upload_requires_claim_server_exit(self):
        self.receipt_step(30)
        (self.home / "rr2-inline-download-exited.json").write_text("{}")
        with patch.object(service, "HOME", self.home):
            with self.assertRaisesRegex(Blocked, "claim-server-not-exited"):
                service.phase_steps("upload")
            (self.home / "rr2-inline-claim-exited.json").write_text("{}")
            service.phase_steps("upload")

    def valid_claim(self):
        return {
            "schemaVersion": 1, "evidenceKind": "guest-typed-inline-zip-claim/1",
            "source": "guest-declared-only", "guest": "192.168.56.128",
            "zipSha256": "A" * 64, "zipBytes": 123456,
            "bundleSha256": trial.BUNDLE_SHA,
            "target": {
                "processId": trial.PID, "processStartUtcTicks": trial.TICKS,
                "executableSha256": trial.GAME_SHA,
            },
        }

    def claim(self, value):
        target = self.home / "claim.json"
        target.write_text(json.dumps(value), encoding="utf-8")
        return target

    def patched_paths(self, claim):
        return (patch.object(service, "CLAIM_RECEIPT", claim),
                patch.object(service, "UPLOAD_ARCHIVE", self.home / "host.zip"),
                patch.object(service, "UPLOAD_RECEIPT", self.home / "uploaded.json"))

    def test_exact_64_bit_claim_is_accepted_only_as_digest(self):
        file = self.claim(self.valid_claim())
        a, b, c = self.patched_paths(file)
        with a, b, c:
            self.assertEqual(service.upload_digest(), "A" * 64)

    def test_truncated_epoch_claim_denied(self):
        value = self.valid_claim()
        value["target"]["processStartUtcTicks"] = 639284177321390000
        file = self.claim(value)
        a, b, c = self.patched_paths(file)
        with a, b, c, self.assertRaisesRegex(Blocked, "provenance-invalid"):
            service.upload_digest()

    def test_claim_cannot_have_wrong_guest_or_noncanonical_hex(self):
        for key, bad in (("guest", "192.168.56.200"),
                         ("zipSha256", "a" * 64),
                         ("bundleSha256", "B" * 64),
                         ("zipBytes", 16 * 1024 * 1024 + 1)):
            value = self.valid_claim()
            value[key] = bad
            file = self.claim(value)
            a, b, c = self.patched_paths(file)
            with a, b, c, self.subTest(key=key), self.assertRaisesRegex(
                    Blocked, "provenance-invalid"):
                service.upload_digest()

    def test_no_reused_destination(self):
        file = self.claim(self.valid_claim())
        (self.home / "host.zip").write_bytes(b"used")
        a, b, c = self.patched_paths(file)
        with a, b, c, self.assertRaisesRegex(Blocked, "target-used"):
            service.upload_digest()

    def test_tracked_sources_sha_pinned(self):
        # Live one-use claims now exist on the actual host; isolate test state.
        with patch.object(service, "CLAIM_RECEIPT", self.home / "claim.json"), patch.object(
                service, "UPLOAD_ARCHIVE", self.home / "archive.zip"), patch.object(
                service, "UPLOAD_RECEIPT", self.home / "upload.json"):
            for phase in ("download", "claim"):
                with self.subTest(phase=phase):
                    path, args = service.server_args(phase)
                    self.assertTrue(path.is_file())
                    self.assertIn("--serve", args)
                    self.assertIn("--seconds", args)
            with self.assertRaisesRegex(Blocked, "claim-receipt-missing"):
                service.server_args("upload")

    def test_no_in_job_terminal_service(self):
        with self.assertRaisesRegex(Blocked, "independent-signed-in"):
            service.require_independent_windows_user()


if __name__ == "__main__":
    unittest.main()
