"""ZIP and two-receipt boundary tests for current RIFT native pointer capture."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from scripts import verify_pointer_zip_archive as recovered
from scripts.verify_typed_inline_archive import ArchiveError
from tests.test_review_current_pointer_xyz import CurrentPointerReviewTests

BUNDLE = "70553F4CE4A9C73C5043CCA16622084734E6C69B1C9E49132C9F622A5F821E4E"


class NativePointerArchiveTests(unittest.TestCase):
    def setUp(self):
        fixture = CurrentPointerReviewTests("test_exact_source_and_two_native_windows_candidate_match")
        fixture.setUp()
        fixture.sync_reports()
        self.addCleanup(fixture.doCleanups)
        self.fx = fixture
        self.root = fixture.root
        for path in (self.fx.beforefile, self.fx.afterfile):
            report = json.loads(path.read_text())
            report["implementation"] = {
                "deploymentKind": "single-file-bundle", "bundleSha256": BUNDLE,
            }
            path.write_text(json.dumps(report))
        self.archive = self.root / "pointer.zip"
        self.write_archive()
        self.output = self.root / "recovered"
        self.source_sha = hashlib.sha256(self.fx.sourcefile.read_bytes()).hexdigest().upper()

    def write_archive(self, *, members=None):
        pairs = {
            "rr2-v16ptr-a.json": self.fx.reqfile,
            "rr2-v16ptr-a-report.json": self.fx.beforefile,
            "rr2-v16ptr-b-report.json": self.fx.afterfile,
        } if members is None else members
        with ZipFile(self.archive, "w", compression=ZIP_DEFLATED) as zipped:
            for name, path in pairs.items():
                zipped.write(path, arcname=name)
        self.zipsha = hashlib.sha256(self.archive.read_bytes()).hexdigest().upper()

    def validate(self, *, claim=None, uploaded=None):
        return recovered.verify_and_publish(
            self.archive, self.zipsha, self.fx.reqfile, self.fx.sourcefile,
            self.source_sha, self.output, pid=self.fx.target["processId"],
            ticks=self.fx.target["processStartUtcTicks"],
            game_sha=self.fx.target["executableSha256"],
            bundle_sha=BUNDLE, claim_path=claim, upload_path=uploaded,
            expected_guest="127.0.0.1",
        )

    def claim_receipts(self):
        claim = self.root / "pointer-claim-receipt.json"
        upload = self.root / "pointer-upload-receipt.json"
        claim.write_text(json.dumps({
            "schemaVersion": 1, "evidenceKind": "guest-native-pointer-zip-claim/1",
            "source": "guest-declared-only", "guest": "127.0.0.1",
            "target": self.fx.target, "bundleSha256": BUNDLE,
            "zipSha256": self.zipsha, "zipBytes": self.archive.stat().st_size,
        }))
        upload.write_text(json.dumps({
            "schemaVersion": 1, "purpose": "content-addressed-guest-pointer-transfer",
            "state": "received", "guest": "127.0.0.1",
            "destination": str(self.archive),
            "sha256": self.zipsha, "bytes": self.archive.stat().st_size,
        }))
        return claim, upload

    def test_verified_zip_recovers_exact_three_originals_and_xyz_review(self):
        proof = self.validate()
        self.assertEqual(proof["reviewStatus"], "candidate-compatible")
        self.assertEqual(proof["transferEvidence"]["state"], "host-fixture-only-no-guest-provenance")
        self.assertEqual(len(proof["files"]), 3)
        self.assertEqual((self.output / "rr2-v16ptr-a-report.json").read_bytes(),
                         self.fx.beforefile.read_bytes())
        derived = json.loads((self.output / "position-review.json").read_text())
        self.assertEqual(derived["qualification"], "candidate-only-not-synchronized")
        self.assertGreaterEqual(proof["separationSeconds"], 3)

    def test_wrong_archive_hash_refuses_any_publication(self):
        self.zipsha = "F" * 64
        with self.assertRaisesRegex(ArchiveError, "SHA-256"):
            self.validate()
        self.assertFalse(self.output.exists())

    def test_rejects_unknown_or_missing_zip_members(self):
        for members in (
            {"../escape.json": self.fx.reqfile},
            {"rr2-v16ptr-a.json": self.fx.reqfile},
            {"rr2-v16ptr-a.json": self.fx.reqfile,
             "rr2-v16ptr-a-report.json": self.fx.beforefile,
             "rr2-v16ptr-b-report.json": self.fx.afterfile,
             "extra.json": self.fx.afterfile},
        ):
            with self.subTest(members=tuple(members)):
                self.write_archive(members=members)
                with self.assertRaisesRegex(ArchiveError, "exactly three"):
                    self.validate()
                self.assertFalse(self.output.exists())

    def test_original_request_must_match_host_pinned_bytes(self):
        self.fx.reqfile.write_text('{"changed":true}')
        with self.assertRaisesRegex(ArchiveError, "request bytes differ"):
            self.validate()

    def test_untrusted_published_tool_bundle_rejected(self):
        original = json.loads(self.fx.beforefile.read_text())
        original["implementation"]["bundleSha256"] = "F" * 64
        self.fx.beforefile.write_text(json.dumps(original))
        self.write_archive()
        with self.assertRaisesRegex(ArchiveError, "bundle differs"):
            self.validate()

    def test_claim_and_content_receipts_cross_verify_and_wrong_peer_blocks(self):
        claim, upload = self.claim_receipts()
        proof = self.validate(claim=claim, uploaded=upload)
        self.assertEqual(proof["transferEvidence"]["state"],
                         "claim-upload-and-extracted-bytes-agree")
        self.assertEqual(proof["transferEvidence"]["guest"], "127.0.0.1")

    def test_claim_upload_mismatch_has_no_recovery_output(self):
        claim, upload = self.claim_receipts()
        value = json.loads(upload.read_text())
        value["purpose"] = "content-addressed-guest-map-transfer"
        upload.write_text(json.dumps(value))
        with self.assertRaisesRegex(ArchiveError, "upload receipt differs"):
            self.validate(claim=claim, uploaded=upload)
        self.assertFalse(self.output.exists())

    def test_second_publication_cannot_replace_originals(self):
        self.validate()
        first = (self.output / "archive-proof.json").read_bytes()
        with self.assertRaisesRegex(ArchiveError, "folder must be new"):
            self.validate()
        self.assertEqual((self.output / "archive-proof.json").read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
