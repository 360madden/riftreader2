"""Second physical Sanctum Watch view, pinned WGC/native bracket (offline only).

The temple model is rendered geometry, not proof of actual optical depth,
physics blocking, walkable floor, or navigation permission.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from scripts import physical_pixel_composite as composite


class RetainedSecondViewTests(unittest.TestCase):
    """Independent camera pose for the same AMD-DESKTOP RIFT process epoch."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.image = root / (
            "artifacts/observe-wgc-f37599014aaa422a94682503abb6d532/image.png")
        cls.receipt = cls.image.with_name("image.png.json")
        cls.before = root / (
            "artifacts/physical-native-facing-82c8b813f64e4b46903f11d267dd4cc4.json")
        cls.after = root / (
            "artifacts/physical-native-facing-dc22ffd6bcbe4518a167539b62f364a7.json")
        cls.terrain = Path(
            "C:/work/RiftWorld/artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj")
        cls.terrain_reg = root / (
            "artifacts/pixel-surface-p1-20261116/courtyard-identity-hypothesis.json")
        temple_root = Path(
            "C:/work/RiftWorld/artifacts/p0-watch-temple-source-render-20261116-agent-iso-r1")
        cls.temple = temple_root / "geometry.obj"
        cls.anchor = temple_root / "atank-source-floor-anchor-exact-r2.json"
        cls.image_sha = "5f09703eca7639f583e68bd40aea19d36d20483e3752ae743b776c90133c4c75"
        cls.receipt_sha = "414b10c7d78be9d397d460f4eb2e7296144e574486ac491fa30ca6ec3eb168f9"
        cls.before_sha = "d7a9f90fcaee7a18005dc2827faab1727a0ff93a6bde4b7e64e60be1074b8905"
        cls.after_sha = "89dad03250c429cbe2a28e8261a84f1324df76b49ab94fc2503fed0a851b8f03"
        cls.anchor_sha = "6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525"
        required = (cls.image, cls.receipt, cls.before, cls.after, cls.terrain,
                    cls.terrain_reg, cls.temple, cls.anchor)
        if not all(path.is_file() for path in required):
            raise unittest.SkipTest("exact retained AMD-DESKTOP second-view assets unavailable")
        for path, sha in ((cls.image, cls.image_sha), (cls.receipt, cls.receipt_sha),
                          (cls.before, cls.before_sha), (cls.after, cls.after_sha),
                          (cls.anchor, cls.anchor_sha)):
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise AssertionError("SHA-pinned historical evidence changed: " + str(path))

    @classmethod
    def _frame(cls):
        return composite.load_frame(
            cls.image, cls.receipt, cls.receipt_sha,
            cls.before, cls.before_sha, cls.after, cls.after_sha,
            expected_host="AMD-DESKTOP")

    def test_second_camera_pose_stable_two_sided_bracket_and_eight_points(self):
        frame = self._frame()
        self.assertEqual(frame["identity"]["host"], "AMD-DESKTOP")
        self.assertEqual(frame["identity"]["pid"], 77704)
        self.assertEqual(frame["identity"]["processStartUtcTicks"], 639304372516074064)
        self.assertEqual(frame["source"]["imageSha256"], self.image_sha)
        self.assertEqual(frame["source"]["nativeBeforeSha256"], self.before_sha)
        self.assertEqual(frame["source"]["nativeAfterSha256"], self.after_sha)
        self.assertGreater(frame["source"]["nativeBracketSeconds"], 0)
        self.assertLessEqual(frame["source"]["nativeBracketSeconds"], 5)
        self.assertAlmostEqual(frame["source"]["nativeAfterDeltaSeconds"],
                               1.014167, delta=0.03)
        before = json.loads(self.before.read_text(encoding="utf-8"))
        after = json.loads(self.after.read_text(encoding="utf-8"))
        self.assertEqual(before["identity"], after["identity"])
        self.assertEqual(before["observation"]["opticalCameraCandidate"],
                         after["observation"]["opticalCameraCandidate"])

        layers = [composite.load_terrain(self.terrain, self.terrain_reg),
                  composite.load_temple(self.temple, self.anchor, self.anchor_sha,
                                        frame["identity"])]
        samples = (
            ((2100, 400), "temple-render", 7.3348),
            ((1600, 700), "temple-render", 13.3537),
            ((1400, 1000), "temple-render", 10.2693),
            ((1400, 600), "terrain", 19.7401),
            ((1800, 1000), "temple-render", 9.1030),
            ((1900, 450), "terrain", 29.5956),
            ((800, 600), "terrain", 20.5401),
            ((1500, 1100), "temple-render", 8.4731),
        )
        report = composite.analyze_pixels(
            frame, layers, [point for point, _, _ in samples], max_distance=200)
        self.assertEqual(report["status"], "candidate-only")
        for row, (_, expected_layer, depth) in zip(report["pixels"], samples):
            with self.subTest(pixel=row["pixel"]):
                result = row["surfaceCandidates"]
                self.assertEqual(result["candidateFirst"]["layer"], expected_layer)
                self.assertAlmostEqual(
                    result["candidateFirst"]["distanceNative"], depth, delta=0.03)
                self.assertFalse(result["ambiguousFirstLayer"])
                self.assertFalse(result["visibleSurfaceQualified"])
                self.assertFalse(result["movementEligible"])
                self.assertLess(max(row["rayForwardReprojectionErrorPixels"]), 1e-7)
        for field in ("inputSent", "movementEligible", "visibleSurfaceQualified",
                      "physicalBlockingQualified", "navigationQualified"):
            self.assertFalse(report[field], field)

    def test_tampered_before_sha_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "native-before-sha256-mismatch"):
            composite.load_frame(
                self.image, self.receipt, self.receipt_sha,
                self.before, "0" * 64, self.after, self.after_sha,
                expected_host="AMD-DESKTOP")


if __name__ == "__main__":
    unittest.main()
