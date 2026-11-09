"""A prepared RR2 movement capture can be previewed in one command result."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

from scripts.run_movement_session import add_quick_review, build_parser


class QuickMovementReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        capture_dir = root / "capture"
        capture_dir.mkdir()
        image = capture_dir / "image.bmp"
        Image.new("RGB", (1211, 702), (17, 29, 43)).save(image, "BMP")
        digest = hashlib.sha256(image.read_bytes()).hexdigest().upper()
        metadata = capture_dir / "capture.json"
        self.metadata_path = metadata
        metadata.write_text(json.dumps({
            "capturedAtUtc": "2000-11-09T12:00:00Z",
            "reviewExpiresInSeconds": 45,
        }), encoding="utf-8")
        self.session_path = root / "session-plan.json"
        self.session_path.write_text(json.dumps({
            "sessionId": "test-session",
            "captureImageSha256": digest,
            "capture": {
                "captureId": "test-capture",
                "capture": str(metadata),
                "image": str(image),
            },
        }), encoding="utf-8")
        self.prepared = {
            "sessionPlan": str(self.session_path),
            "capture": str(image),
            "requestId": "request-1",
            "reviewRequired": True,
        }

    def test_preview_and_review_pins_share_one_prepared_result(self):
        result = add_quick_review(self.prepared)
        self.assertEqual(result["requestId"], self.prepared["requestId"])
        review = result["quickReview"]
        self.assertEqual(review["status"], "ready")
        self.assertEqual(review["sessionId"], "test-session")
        self.assertEqual(review["captureId"], "test-capture")
        self.assertEqual(review["reviewExpiresInSeconds"], 0)
        self.assertEqual(review["reviewDeadlineUtc"], "2000-11-09T12:00:45Z")
        self.assertEqual(review["reviewMaxAgeSeconds"], 45)
        self.assertEqual(
            review["sessionPlanSha256"],
            hashlib.sha256(self.session_path.read_bytes()).hexdigest().upper())
        self.assertTrue(review["preview"]["nonAuthoritative"])
        self.assertIn(review["preview"]["previewFormat"], ("webp", "jpeg"))
        size_limit = 4500 if review["preview"]["previewFormat"] == "webp" else 40_000
        self.assertLessEqual(len(base64.b64decode(review["preview"]["base64"])), size_limit)

    def test_old_preview_helper_uses_hash_checked_jpeg_fallback(self):
        jpeg = {"sourceSha256": "A" * 64, "previewFormat": "jpeg",
                "nonAuthoritative": True}
        with mock.patch("scripts.quick_review_capture.preview", side_effect=[
                TypeError("preview() got an unexpected keyword argument 'compact'"), jpeg]) as stub:
            review = add_quick_review(self.prepared)["quickReview"]
        self.assertEqual(review["preview"], jpeg)
        self.assertEqual(stub.call_count, 2)
        first, second = stub.call_args_list
        self.assertEqual(first.kwargs, {"compact": True})
        self.assertEqual(second.kwargs, {})
        self.assertEqual(first.args, second.args)

    def test_oversize_webp_falls_back_without_dropping_review(self):
        jpeg = {"previewFormat": "jpeg", "nonAuthoritative": True}
        with mock.patch("scripts.quick_review_capture.preview", side_effect=[
                ValueError("preview-too-large"), jpeg]) as stub:
            review = add_quick_review(self.prepared)["quickReview"]
        self.assertEqual(review["status"], "ready")
        self.assertEqual(review["preview"], jpeg)
        self.assertEqual(stub.call_count, 2)

    def test_source_hash_mismatch_never_falls_back(self):
        with mock.patch("scripts.quick_review_capture.preview",
                        side_effect=ValueError("capture-hash-mismatch")) as stub:
            review = add_quick_review(self.prepared)["quickReview"]
        self.assertEqual(review["status"], "unavailable")
        self.assertEqual(stub.call_count, 1)

    def test_fresh_preview_counts_down_without_resetting_capture_window(self):
        captured = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.metadata_path.write_text(json.dumps({
            "capturedAtUtc": captured.isoformat(),
            "reviewExpiresInSeconds": 45,
        }), encoding="utf-8")
        review = add_quick_review(self.prepared)["quickReview"]
        self.assertEqual(review["status"], "ready")
        self.assertEqual(datetime.fromisoformat(review["reviewDeadlineUtc"].replace("Z", "+00:00")),
                         captured + timedelta(seconds=45))
        self.assertGreater(review["reviewExpiresInSeconds"], 0)
        self.assertLessEqual(review["reviewExpiresInSeconds"], 40)

    def test_preview_failure_keeps_authoritative_preparation(self):
        self.session_path.unlink()
        result = add_quick_review(self.prepared)
        self.assertEqual(result["quickReview"]["status"], "unavailable")
        self.assertEqual(result["sessionPlan"], self.prepared["sessionPlan"])
        self.assertNotIn("quickReview", self.prepared)

    def test_opt_in_only_for_prepare(self):
        args = build_parser().parse_args([
            "prepare", "--managed-lab", "lab2", "--feedback-pin", "pin.json",
            "--output", "session", "--mode", "turn", "--keys", "a",
            "--quick-preview"])
        self.assertTrue(args.quick_preview)
        plain = build_parser().parse_args([
            "prepare", "--managed-lab", "lab2", "--feedback-pin", "pin.json",
            "--output", "session", "--mode", "turn", "--keys", "a"])
        self.assertFalse(plain.quick_preview)


if __name__ == "__main__":
    unittest.main()
