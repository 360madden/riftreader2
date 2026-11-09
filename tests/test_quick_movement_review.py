"""A prepared RR2 movement capture can be previewed in one command result."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

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
        metadata.write_text(json.dumps({
            "capturedAtUtc": "2026-11-09T12:00:00Z",
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
        self.assertEqual(review["reviewExpiresInSeconds"], 45)
        self.assertEqual(
            review["sessionPlanSha256"],
            hashlib.sha256(self.session_path.read_bytes()).hexdigest().upper())
        self.assertTrue(review["preview"]["nonAuthoritative"])
        self.assertLess(len(base64.b64decode(review["preview"]["base64"])), 40_001)

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
