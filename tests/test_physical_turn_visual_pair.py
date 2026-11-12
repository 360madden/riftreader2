"""Synthetic, offline checks for WGC receipt-bound before/after view comparison."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from scripts import physical_turn_visual_pair as visual

BASE_TIME = datetime(2026, 11, 11, 19, 0, tzinfo=timezone.utc)
IDENTITY = {
    "pid": 1234, "startTicks": 639299470183328173,
    "sha256": "A" * 64, "hwnd": 5678,
    "processName": "rift_x64", "width": 320, "height": 200,
    "foreground": True, "isCloaked": False,
}


def draw_scene(path: Path, shift: int = 0):
    image = Image.new("RGB", (320, 200))
    pixels = image.load()
    for y in range(200):
        for x in range(320):
            xx = (x + shift) % 320
            pixels[x, y] = ((xx * 17 + y * 3) % 256,
                            ((xx // 12) * 37 + y) % 256,
                            ((xx // 7) * 41 + y * 5) % 256)
    image.save(path, "PNG")


def make_receipt(path: Path, image_path: Path, offset: int):
    raw = image_path.read_bytes()
    start = BASE_TIME + timedelta(seconds=offset)
    completed = start + timedelta(milliseconds=250)
    report = {
        "schemaVersion": 1, "status": "unqualified-gpu-window-frame",
        "machine": "AMD-DESKTOP", "requestedBackend": "wgc",
        "targetBefore": deepcopy(IDENTITY), "targetAfter": deepcopy(IDENTITY),
        "capturedStartedAtUtc": start.isoformat().replace("+00:00", "Z"),
        "capturedCompletedAtUtc": completed.isoformat().replace("+00:00", "Z"),
        "frameWidth": 320, "frameHeight": 200,
        "imageSha256": hashlib.sha256(raw).hexdigest().upper(),
        "imageBytes": len(raw), "outputPath": str(image_path),
        "quality": {"potentiallyBlankOrBlack": False},
        "inputSent": False, "focusChangedByProbe": False,
        "bodyHeadingVerified": False, "gameResponseVerified": False,
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    return report


class VisualPairTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.before = self.root / "before.png"
        self.after = self.root / "after.png"
        self.bjson = self.root / "before.png.json"
        self.ajson = self.root / "after.png.json"
        draw_scene(self.before, 0)
        draw_scene(self.after, 32)
        self.breport = make_receipt(self.bjson, self.before, 0)
        self.areport = make_receipt(self.ajson, self.after, 2)

    def assess(self):
        return visual.visual_compare(self.before, self.after, self.bjson, self.ajson)

    def update(self, report, path):
        path.write_text(json.dumps(report), encoding="utf-8")

    def test_changed_scene_produces_visual_candidate_only(self):
        result = self.assess()
        self.assertTrue(result["visibleViewChangeCandidate"])
        self.assertGreater(result["changedPixelFractionCandidate"], .18)
        self.assertEqual(result["sampledPixels"], 96 * 64)
        self.assertFalse(result["gameResponseVerified"])
        self.assertFalse(result["actorHeadingQualified"])
        self.assertFalse(result["cameraHeadingQualified"])
        self.assertFalse(result["inputSent"])

    def test_dark_changed_scene_uses_bounded_common_exposure_gain(self):
        for path in (self.before, self.after):
            with Image.open(path) as image:
                image.point(lambda value: value // 7).save(path)
        make_receipt(self.bjson, self.before, 0)
        make_receipt(self.ajson, self.after, 2)
        result = self.assess()
        self.assertTrue(result["visibleViewChangeCandidate"])
        self.assertLess(result["meanAbsoluteChannelDeltaCandidate"], 15)
        self.assertGreater(result["exposureAdjustedMeanAbsoluteChannelDeltaCandidate"], 15)
        self.assertEqual(result["comparisonExposureGain"], 4)

    def test_dark_identical_scene_and_small_noise_do_not_claim_change(self):
        for path, color in ((self.before, (8, 8, 8)), (self.after, (9, 9, 9))):
            Image.new("RGB", (320, 200), color).save(path)
        make_receipt(self.bjson, self.before, 0)
        make_receipt(self.ajson, self.after, 2)
        self.assertFalse(self.assess()["visibleViewChangeCandidate"])

    def test_landmark_offset_recovers_translation_and_refuses_flat_patches(self):
        import random
        from PIL import ImageChops
        original = Image.frombytes("L", (320, 200), random.Random(12).randbytes(320 * 200))
        moved = ImageChops.offset(original, -11, 1)
        region = (64, 40, 256, 150)
        shift = visual.local_return_offset(original, moved, region)
        self.assertEqual((shift["medianHorizontalPixels"], shift["medianVerticalPixels"]), (-11, 1))
        flat = Image.new("L", original.size, 50)
        ambiguous = visual.local_return_offset(flat, flat, region)
        self.assertEqual(ambiguous["matchedPatches"], 0)
        self.assertIsNone(ambiguous["medianHorizontalPixels"])

    def test_unchanged_scene_does_not_claim_change(self):
        draw_scene(self.after, 0)
        self.areport = make_receipt(self.ajson, self.after, 2)
        result = self.assess()
        self.assertFalse(result["visibleViewChangeCandidate"])
        self.assertEqual(result["changedPixelFractionCandidate"], 0)
        self.assertEqual(result["meanAbsoluteChannelDeltaCandidate"], 0)

    def test_mismatched_build_pid_or_window_blocks(self):
        for key, value in (("pid", 4321), ("sha256", "B" * 64),
                           ("hwnd", 8900), ("startTicks", 1)):
            with self.subTest(key=key):
                report = deepcopy(self.areport)
                report["targetBefore"][key] = report["targetAfter"][key] = value
                self.update(report, self.ajson)
                with self.assertRaisesRegex(ValueError, "visual-session-or-window-changed"):
                    self.assess()
        self.update(self.areport, self.ajson)

    def test_corrupted_image_hash_and_mismatched_path_block(self):
        self.after.write_bytes(self.after.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "visual-image-hash-or-size-mismatch"):
            self.assess()
        draw_scene(self.after, 32)
        self.areport = make_receipt(self.ajson, self.after, 2)
        report = deepcopy(self.areport)
        report["outputPath"] = str(self.before)
        self.update(report, self.ajson)
        with self.assertRaisesRegex(ValueError, "visual-receipt-path-mismatch"):
            self.assess()

    def test_stale_reversed_or_long_capture_block(self):
        for started in (-2, 40):
            report = deepcopy(self.areport)
            t = BASE_TIME + timedelta(seconds=started)
            report["capturedStartedAtUtc"] = t.isoformat().replace("+00:00", "Z")
            report["capturedCompletedAtUtc"] = (
                t + timedelta(milliseconds=250)).isoformat().replace("+00:00", "Z")
            self.update(report, self.ajson)
            with self.assertRaisesRegex(ValueError, "visual-pair-time-gap-invalid"):
                self.assess()
        self.update(self.areport, self.ajson)

    def test_blank_or_unqualified_receipt_blocks(self):
        report = deepcopy(self.areport)
        report["quality"]["potentiallyBlankOrBlack"] = True
        self.update(report, self.ajson)
        with self.assertRaisesRegex(ValueError, "visual-unusable-capture-quality"):
            self.assess()
        report = deepcopy(self.areport)
        report["inputSent"] = True
        self.update(report, self.ajson)
        with self.assertRaisesRegex(ValueError, "visual-capture-receipt-unqualified"):
            self.assess()

    def test_comparison_uses_verified_bytes_if_sources_change_during_decode(self):
        expected = self.assess()
        decode = Image.open
        first = True

        def replace_sources_then_decode(source):
            nonlocal first
            if first:
                first = False
                self.before.write_bytes(self.after.read_bytes())
                self.bjson.write_text("{}", encoding="utf-8")
            return decode(source)

        with patch.object(visual.Image, "open", side_effect=replace_sources_then_decode):
            self.assertEqual(self.assess(), expected)

    def test_duplicate_json_key_is_refused(self):
        self.ajson.write_text('{"schemaVersion":1,"schemaVersion":1}',
                              encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "visual-duplicate-json-key"):
            self.assess()

    def test_cli_outputs_new_only_json_without_input(self):
        args = ["--before-png", str(self.before), "--after-png", str(self.after),
                "--before-receipt", str(self.bjson), "--after-receipt", str(self.ajson),
                "--out", str(self.root / "comparison.json")]
        with redirect_stdout(StringIO()) as printed:
            self.assertEqual(visual.main(args), 0)
        result = json.loads(printed.getvalue())
        self.assertTrue(result["visibleViewChangeCandidate"])
        self.assertFalse(result["inputSent"])
        self.assertEqual(json.loads((self.root / "comparison.json").read_text()), result)
        with redirect_stdout(StringIO()) as printed:
            self.assertEqual(visual.main(args), 2)
        self.assertEqual(json.loads(printed.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
