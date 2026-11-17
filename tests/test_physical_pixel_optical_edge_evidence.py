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


if __name__ == "__main__":
    unittest.main()
