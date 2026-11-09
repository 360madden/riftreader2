"""Quick screenshot transport stays read-only and source-hash pinned."""
import base64
import hashlib
from io import BytesIO
from unittest.mock import patch
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

    def test_png_preview_is_hash_pinned_and_preserves_original(self):
        path = self.path.with_suffix(".png")
        Image.new("RGB", (720, 480), (24, 48, 96)).save(path, "PNG")
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest().upper()
        result = preview(path, digest)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(result["sourceSha256"], digest)
        self.assertEqual(result["sourceDimensions"], [720, 480])
        self.assertTrue(result["nonAuthoritative"])

    def test_other_image_formats_are_not_silently_accepted(self):
        path = self.path.with_suffix(".jpg")
        Image.new("RGB", (720, 480)).save(path, "JPEG")
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        with self.assertRaisesRegex(ValueError, "capture-image-invalid"):
            preview(path, digest)

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

    def test_compact_webp_is_bounded_and_both_hashes_are_pinned(self):
        result = preview(self.path, self.digest, compact=True)
        data = base64.b64decode(result['base64'], validate=True)
        self.assertEqual('webp', result['previewFormat'])
        self.assertLessEqual(len(data), 4500)
        self.assertEqual(hashlib.sha256(data).hexdigest().upper(), result['previewSha256'])
        self.assertEqual(self.digest, result['sourceSha256'])
        self.assertEqual([0, 0, 1211, 702], result['sourceCrop'])
        self.assertEqual(self.source, self.path.read_bytes())
        self.assertTrue(result['nonAuthoritative'])
        self.assertEqual('WEBP', Image.open(BytesIO(data)).format)
        self.assertNotIn('reviewedAtUtc', result)
        self.assertNotIn('decision', result)

    def test_compact_crop_reports_original_coordinates_and_dimensions(self):
        result = preview(self.path, self.digest, compact=True, crop=(200, 210, 1000, 290))
        self.assertEqual([1211, 702], result['sourceDimensions'])
        self.assertEqual([200, 210, 1000, 290], result['sourceCrop'])
        self.assertEqual([540, 54], result['previewDimensions'])
        self.assertEqual(self.source, self.path.read_bytes())

    def test_compact_bad_crop_fails_instead_of_padding_or_guessing(self):
        for crop in ((-1, 0, 100, 100), (0, 0, 1212, 702), (1, 1, 1, 20),
                     (0, 0, 20, 703), (0, 0, True, 20), (0, 0, 1.5, 20),
                     '0,0,100,100', (0, 0, 20)):
            with self.subTest(crop=crop), self.assertRaisesRegex(ValueError, 'invalid-preview-crop'):
                preview(self.path, self.digest, compact=True, crop=crop)

    def test_crop_requires_explicit_compact_mode(self):
        with self.assertRaisesRegex(ValueError, 'invalid-preview-mode'):
            preview(self.path, self.digest, crop=(0, 0, 100, 100))
        with self.assertRaisesRegex(ValueError, 'invalid-preview-mode'):
            preview(self.path, self.digest, compact=1)

    def test_compact_rejects_hash_drift_and_unsupported_source(self):
        with self.assertRaisesRegex(ValueError, 'capture-hash-mismatch'):
            preview(self.path, '0' * 64, compact=True)
        path = self.path.with_suffix('.jpg')
        Image.new('RGB', (100, 100)).save(path)
        with self.assertRaisesRegex(ValueError, 'capture-image-invalid'):
            preview(path, hashlib.sha256(path.read_bytes()).hexdigest(), compact=True)

    def test_compact_overflow_is_explicit_not_truncated(self):
        def oversized(image, stream, **kwargs):
            stream.write(b'x' * 4501)
        with patch.object(Image.Image, 'save', oversized):
            with self.assertRaisesRegex(ValueError, 'preview-too-large'):
                preview(self.path, self.digest, compact=True)


if __name__ == "__main__":
    unittest.main()
