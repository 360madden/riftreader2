"""No-game-input tests for immutable, paired RR2 screenshot review."""
import hashlib
from pathlib import Path
import tempfile
import unittest

try:
    from PIL import Image
except ImportError:
    Image = None

from scripts import compare_turn_frames as frames
from scripts.run_movement_session import add_turn_visual_comparison


@unittest.skipIf(Image is None, "Pillow is optional outside screenshot environments")
class CompareTurnFramesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.before = self.folder / "before.png"
        self.after = self.folder / "after.png"
        self.output = self.folder / "review.png"
        self._save(self.before, (0, 0, 0))
        self._save(self.after, (255, 255, 255))

    def _save(self, path, color):
        Image.new("RGB", (100, 80), color).save(path)

    def _hash(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest().upper()

    def _compare(self, **kwargs):
        return frames.compare(self.before, self._hash(self.before),
                              self.after, self._hash(self.after),
                              self.output, **kwargs)

    def test_pair_creates_hash_pinned_readable_preview(self):
        before = self.before.read_bytes()
        after = self.after.read_bytes()
        result = self._compare(crop=(20, 10, 80, 70))
        self.assertEqual("visual-difference-candidate", result["status"])
        self.assertEqual(1, result["changedPixelFraction"])
        self.assertEqual(255, result["meanAbsoluteChannelDelta"])
        self.assertFalse(result["sourceBytesEqual"])
        self.assertIn("unqualified", result["qualification"])
        self.assertEqual([20, 10, 80, 70], result["comparisonCrop"])
        self.assertEqual(before, self.before.read_bytes())
        self.assertEqual(after, self.after.read_bytes())
        self.assertEqual(self._hash(self.output), result["previewSha256"])
        with Image.open(self.output) as image:
            self.assertEqual((120, 85), image.size)

    def test_reviewed_turn_auto_compares_hash_pinned_frames(self):
        turn = {"mode": "turn", "beforeTurnCapture": {
            "image": str(self.before), "imageSha256": self._hash(self.before)},
            "afterTurnCapture": {"status": "captured", "image": str(self.after),
                                 "imageSha256": self._hash(self.after)}}
        result = add_turn_visual_comparison(turn, self.folder)
        review = result["turnVisualComparison"]
        self.assertEqual(review["status"], "visual-difference-candidate")
        self.assertEqual(review["changedPixelFraction"], 1)
        self.assertTrue((self.folder / "turn-before-after.png").is_file())
        self.assertEqual(review["previewSha256"], self._hash(self.folder / "turn-before-after.png"))
        self.assertEqual(turn["afterTurnCapture"]["status"], "captured")
        turn["afterTurnCapture"]["imageSha256"] = "F" * 64
        blocked = add_turn_visual_comparison(turn, self.folder)
        self.assertEqual(blocked["turnVisualComparison"]["status"], "unavailable")
        self.assertIn("hash-mismatch", blocked["turnVisualComparison"]["reason"])

    def test_no_after_frame_reports_unavailable_without_creating_preview(self):
        result = add_turn_visual_comparison({"mode": "turn",
            "beforeTurnCapture": {"image": str(self.before), "imageSha256": self._hash(self.before)},
            "afterTurnCapture": {"status": "unavailable"}}, self.folder)
        self.assertEqual(result["turnVisualComparison"]["reason"], "after-turn-frame-unavailable")
        self.assertFalse((self.folder / "turn-before-after.png").exists())

    def test_identical_frames_do_not_claim_turn(self):
        self._save(self.after, (0, 0, 0))
        result = self._compare()
        self.assertTrue(result["sourceBytesEqual"])
        self.assertEqual(0, result["changedPixelFraction"])
        self.assertEqual("no-visual-difference-observed", result["status"])
        self.assertIn("visual-pixel-difference-only", result["qualification"])

    def test_below_threshold_pixels_do_not_claim_change(self):
        self._save(self.after, (10, 0, 0))
        below = self._compare()
        self.assertFalse(below["sourceBytesEqual"])
        self.assertEqual(0, below["changedPixelFraction"])
        self.assertEqual("no-visual-difference-observed", below["status"])
        self.output.unlink()
        visible = self._compare(threshold=10)
        self.assertEqual(1, visible["changedPixelFraction"])
        self.assertEqual("visual-difference-candidate", visible["status"])

    def test_changed_hash_and_dimensions_are_rejected_without_output(self):
        with self.assertRaisesRegex(ValueError, "hash-mismatch"):
            frames.compare(self.before, "A" * 64, self.after, self._hash(self.after), self.output)
        self._save(self.after, (255, 255, 255))
        self.after.unlink()
        Image.new("RGB", (90, 80), "white").save(self.after)
        with self.assertRaisesRegex(ValueError, "dimensions-mismatch"):
            self._compare()
        self.assertFalse(self.output.exists())

    def test_invalid_crop_threshold_and_existing_output_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "crop"):
            self._compare(crop=(0, 0, 200, 20))
        with self.assertRaisesRegex(ValueError, "threshold"):
            self._compare(threshold=0)
        first = self._compare()
        with self.assertRaises(FileExistsError):
            self._compare()
        self.assertEqual(first["previewSha256"], self._hash(self.output))


if __name__ == "__main__":
    unittest.main()
