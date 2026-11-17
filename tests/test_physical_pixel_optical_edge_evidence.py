"""Independent pixel brightness edge evidence remains candidate-only and pinned."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from scripts import physical_pixel_optical_edge_evidence as edge


class BrightInteriorMathTests(unittest.TestCase):
    def test_synthetic_stable_bright_onset(self):
        image = Image.new("RGB", (120, 32), (25, 25, 25))
        for x in range(60, 120):
            for y in range(32):
                image.putpixel((x, y), (200, 200, 200))
        result = edge.bright_interior_onset(
            image, y=16, search=(40, 80), background=(20, 35),
            foreground=(90, 105))
        self.assertEqual(result["brightInteriorOnsetX"], 60)
        self.assertIn("not-outer-silhouette", result["measurement"])

    def test_weak_contrast_fails_closed(self):
        image = Image.new("RGB", (120, 32), (40, 40, 40))
        with self.assertRaisesRegex(ValueError, "contrast-insufficient"):
            edge.bright_interior_onset(
                image, y=16, search=(40, 80), background=(20, 35),
                foreground=(90, 105))

    def test_bad_hash_fails_closed(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "source.bin"
            path.write_bytes(b"source")
            with self.assertRaisesRegex(ValueError, "source-sha256-mismatch"):
                edge._pinned(path, "0" * 64)


class RetainedRealImageOpticalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for item in edge.VIEWS.values():
            image = edge.ROOT / "artifacts" / item["capture"] / "image.png"
            before = edge.ROOT / "artifacts" / item["before"]
            after = edge.ROOT / "artifacts" / item["after"]
            if not all(path.is_file() for path in (image, before, after, edge.TERRAIN,
                                                   edge.TERRAIN_REG, edge.TEMPLE_ROOT / "geometry.obj")):
                raise unittest.SkipTest("retained AMD-DESKTOP WGC/source files unavailable")
        cls.first = edge.analyze_view("first")
        cls.second = edge.analyze_view("second")
        cls.first_dark = edge.analyze_view("first", dark_gradient=True)
        cls.second_dark = edge.analyze_view("second", dark_gradient=True)

    def test_first_view_two_very_close_bright_boundaries(self):
        rows = self.first["rows"]
        self.assertEqual([r["name"] for r in rows],
                         ["left-pillar", "right-pillar"])
        self.assertEqual([r["brightInteriorOnsetX"] for r in rows], [843, 2156])
        self.assertLessEqual(max(abs(r["brightInteriorMinusProjectedPixels"])
                                 for r in rows), 4)
        self.assertFalse(self.first["visibleSurfaceQualified"])
        self.assertFalse(self.first["movementEligible"])

    def test_second_view_bright_interior_lags_candidate_edge(self):
        rows = self.second["rows"]
        self.assertEqual([r["brightInteriorOnsetX"] for r in rows], [1998, 1985])
        self.assertTrue(all(r["brightInteriorMinusProjectedPixels"] > 20
                            for r in rows))
        self.assertTrue(all(r["measurement"].endswith("not-outer-silhouette")
                            for r in rows))
        self.assertFalse(self.second["opticalDepthQualified"])
        self.assertFalse(self.second["physicalBlockingQualified"])

    def test_ui_control_is_not_world_fragment(self):
        for report in (self.first, self.second):
            control = report["hudOcclusionControl"]
            self.assertTrue(control["manualUiMask"])
            self.assertFalse(control["pixelIsQualifiedWorldFragment"])
            self.assertFalse(control["visibleSurfaceQualified"])
            self.assertIn(control["underlyingWorldCandidateLayer"],
                          {"terrain", "temple-render"})
            self.assertFalse(report["inputSent"])
            self.assertFalse(report["navigationQualified"])


    def test_dark_gradient_opt_in_preserves_default_output(self):
        self.assertNotIn("darkGradientProfiles", self.first)
        self.assertNotIn("darkGradientProfiles", self.second)
        for original, profiled in ((self.first, self.first_dark),
                                   (self.second, self.second_dark)):
            self.assertEqual(original["rows"], profiled["rows"])
            self.assertEqual(original["hudOcclusionControl"],
                             profiled["hudOcclusionControl"])
            self.assertFalse(profiled["opticalVisibilityQualified"])
            self.assertFalse(profiled["movementEligible"])

    def test_second_view_dark_boundary_is_near_projection_not_bright_onset(self):
        profiles = self.second_dark["darkGradientProfiles"]
        self.assertEqual(len(profiles), 2)
        for result in profiles:
            self.assertGreaterEqual(result["brightInteriorMinusProjectedPixels"], 30)
            self.assertLessEqual(result["brightInteriorMinusProjectedPixels"], 40)
            self.assertGreaterEqual(result["darkTroughMinusProjectedPixels"], 2)
            self.assertLessEqual(result["darkTroughMinusProjectedPixels"], 5)
            self.assertTrue(result["darkBandCandidate"])
            self.assertLess(result["strongestNegativeGradientDelta4Px"], -8)
            self.assertIn("not-outer-silhouette", result["measurement"])
            self.assertTrue(result["neighborRowsNotReprojected"])
            self.assertFalse(result["opticalVisibilityQualified"])
            self.assertFalse(result["movementEligible"])

    def test_first_view_does_not_infer_dark_silhouette(self):
        for result in self.first_dark["darkGradientProfiles"]:
            self.assertLessEqual(abs(result["brightInteriorMinusProjectedPixels"]), 4)
            self.assertFalse(result["darkBandCandidate"])
            self.assertFalse(result["opticalVisibilityQualified"])

    def test_hud_gradient_false_positive_is_explicitly_blocked(self):
        first = self.first_dark["hudGradientFalsePositiveControl"]
        second = self.second_dark["hudGradientFalsePositiveControl"]
        self.assertTrue(first["manualUiMask"])
        self.assertTrue(second["manualUiMask"])
        self.assertGreater(second["horizontalLuminanceRange21Px"], 50)
        for item in (first, second):
            self.assertTrue(item["opticalGradientMayComeFromHud"])
            self.assertFalse(item["pixelIsQualifiedWorldFragment"])
            self.assertFalse(item["opticalVisibilityQualified"])
            self.assertFalse(item["movementEligible"])



if __name__ == "__main__":
    unittest.main()
