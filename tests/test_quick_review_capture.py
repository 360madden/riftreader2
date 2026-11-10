"""Quick screenshot transport stays read-only and source-hash pinned."""
import base64
from contextlib import redirect_stdout
import hashlib
from io import BytesIO, StringIO
import json
from unittest.mock import patch
import tempfile
from pathlib import Path
import unittest

from PIL import Image

from scripts.quick_review_capture import MAX_PAIR_JPEG_BYTES, main, preview, review_pair


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

    def test_jpeg_crop_keeps_readable_source_detail_and_original_hash(self):
        box = (200, 210, 1000, 290)
        result = preview(self.path, self.digest, width=1000, crop=box)
        self.assertEqual("jpeg", result["previewFormat"])
        self.assertEqual([800, 80], result["previewDimensions"])
        self.assertEqual(list(box), result["sourceCrop"])
        self.assertEqual([1211, 702], result["sourceDimensions"])
        data = base64.b64decode(result["base64"], validate=True)
        self.assertEqual(self.digest, result["sourceSha256"])
        self.assertEqual(hashlib.sha256(data).hexdigest().upper(), result["previewSha256"])
        self.assertEqual(self.source, self.path.read_bytes())
        self.assertTrue(result["nonAuthoritative"])
        self.assertNotIn("reviewedAtUtc", result)

    def test_pair_returns_full_frame_and_readable_detail_from_same_source(self):
        box = (200, 210, 1000, 290)
        result = review_pair(self.path, self.digest, box, width=1000)
        full, detail = result["fullFrame"], result["detail"]
        self.assertTrue(result["nonAuthoritative"])
        self.assertEqual(self.digest, result["sourceSha256"])
        self.assertEqual(self.digest, full["sourceSha256"])
        self.assertEqual(self.digest, detail["sourceSha256"])
        self.assertEqual([0, 0, 1211, 702], full["sourceCrop"])
        self.assertEqual(list(box), detail["sourceCrop"])
        self.assertEqual("webp", full["previewFormat"])
        self.assertEqual("jpeg", detail["previewFormat"])
        self.assertLessEqual(len(base64.b64decode(detail["base64"])), MAX_PAIR_JPEG_BYTES)
        self.assertGreater(detail["previewDimensions"][0],
                           full["previewDimensions"][0])
        self.assertEqual(self.source, self.path.read_bytes())
        for preview_result in (full, detail):
            data = base64.b64decode(preview_result["base64"], validate=True)
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(),
                             preview_result["previewSha256"])
            self.assertNotIn("reviewedAtUtc", preview_result)
            self.assertNotIn("decision", preview_result)

    def test_pair_requires_explicit_valid_crop_and_matching_hash(self):
        with self.assertRaisesRegex(ValueError, 'review-pair-requires-crop'):
            review_pair(self.path, self.digest, None)
        with self.assertRaisesRegex(ValueError, 'invalid-preview-crop'):
            review_pair(self.path, self.digest, (0, 0, 1212, 100))
        with self.assertRaisesRegex(ValueError, 'capture-hash-mismatch'):
            review_pair(self.path, "0" * 64, (0, 0, 100, 100))
        with self.assertRaisesRegex(ValueError, 'invalid-preview-mode'):
            preview(self.path, self.digest, compact=1)
        for limit in (True, -1, 40001):
            with self.subTest(limit=limit), self.assertRaisesRegex(
                    ValueError, 'invalid-preview-budget'):
                preview(self.path, self.digest, jpeg_byte_limit=limit)

    def test_pair_cli_is_one_json_response_without_review_authorization(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--capture", str(self.path), "--sha256", self.digest,
                         "--pair", "--crop", "200", "210", "1000", "290",
                         "--width", "1000"])
        self.assertEqual(0, code)
        result = json.loads(output.getvalue())
        self.assertEqual([800, 80], result["detail"]["previewDimensions"])
        self.assertEqual("webp", result["fullFrame"]["previewFormat"])
        self.assertNotIn("reviewedAtUtc", output.getvalue())
        self.assertNotIn("decision", output.getvalue())
        blocked = StringIO()
        with redirect_stdout(blocked):
            code = main(["--capture", str(self.path), "--sha256", self.digest,
                         "--pair", "--compact", "--crop", "0", "0", "100", "100"])
        self.assertEqual(2, code)
        self.assertEqual("invalid-preview-mode", json.loads(blocked.getvalue())["reason"])

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
