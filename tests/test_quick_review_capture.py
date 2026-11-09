"""Quick screenshot transport stays read-only and source-hash pinned."""
import base64
import hashlib
import tempfile
from pathlib import Path
import unittest

from PIL import Image

from scripts.quick_review_capture import preview


class QuickReviewCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "capture.bmp"
        Image.new("RGB", (1211, 702), (24, 48, 96)).save(self.path, "BMP")
        self.source = self.path.read_bytes()
        self.digest = hashlib.sha256(self.source).hexdigest().upper()

    def test_preview_is_jpeg_and_never_changes_original(self):
        result = preview(self.path, self.digest)
        self.assertEqual(self.path.read_bytes(), self.source)
        self.assertEqual(result["sourceSha256"], self.digest)
        self.assertEqual(result["sourceDimensions"], [1211, 702])
        self.assertTrue(result["nonAuthoritative"])
        data = base64.b64decode(result["base64"], validate=True)
        self.assertLessEqual(len(data), 40_000)
        self.assertEqual(data[:2], b"\xff\xd8")
        self.assertEqual(result["previewFormat"], "jpeg")

    def test_mutated_capture_refused(self):
        self.path.write_bytes(self.source + b"x")
        with self.assertRaisesRegex(ValueError, "capture-hash-mismatch"):
            preview(self.path, self.digest)

    def test_invalid_hash_refused(self):
        with self.assertRaisesRegex(ValueError, "invalid-capture-hash"):
            preview(self.path, "not-a-sha")

    def test_oversized_width_refused(self):
        with self.assertRaisesRegex(ValueError, "invalid-preview-width"):
            preview(self.path, self.digest, width=9000)


if __name__ == "__main__":
    unittest.main()
