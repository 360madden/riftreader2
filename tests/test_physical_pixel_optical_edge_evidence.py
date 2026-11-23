"""Independent pixel brightness edge evidence remains candidate-only and pinned."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

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

    def test_unbracketed_neighbor_is_unknown_not_projected(self):
        image = Image.new("RGB", (128, 64), (45, 45, 45))
        boundaries = {-8: (59, 60), -4: None, 0: (59, 60),
                      4: (59, 60), 8: (59, 60)}
        result = edge.dark_gradient_profile(
            image, y=32, projected_boundary=(59, 60), bright_interior_x=75,
            neighbor_boundaries=boundaries)
        unknown = result["neighborRows"][1]
        self.assertEqual(unknown["projectionStatus"], "unavailable")
        self.assertIsNone(unknown["projectedLayerBoundaryPixels"])
        self.assertFalse(unknown["darkBandCandidate"])
        self.assertFalse(result["neighborRowsFullyReprojected"])
        self.assertFalse(result["opticalVisibilityQualified"])
        self.assertFalse(result["movementEligible"])

    def test_bad_hash_fails_closed(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "source.bin"
            path.write_bytes(b"source")
            with self.assertRaisesRegex(ValueError, "source-sha256-mismatch"):
                edge._pinned(path, "0" * 64)

    def test_cli_uses_explicit_archive_path_for_pinned_image(self):
        archive = Path(self.enterContext(TemporaryDirectory(prefix="rr2-copied-archive-")))
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = edge.main(["--view", "first", "--archive-dir", str(archive)])
        expected_image = archive / edge.VIEWS["first"]["capture"] / "image.png"
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["reason"],
                         f"optical-edge-source-sha256-mismatch: {expected_image}")


class RetainedRealImageOpticalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temple = edge.RIFTWORLD_ROOT / edge.TEMPLE_DIR
        paths = [edge.RIFTWORLD_ROOT / edge.TERRAIN_OBJ, edge.ARCHIVE_DIR / edge.TERRAIN_REG,
                 temple / "geometry.obj", temple / edge.TEMPLE_ANCHOR]
        for item in edge.VIEWS.values():
            frame_dir = edge.ARCHIVE_DIR / item["capture"]
            paths.extend((frame_dir / "image.png", frame_dir / "image.png.json",
                          edge.ARCHIVE_DIR / item["before"], edge.ARCHIVE_DIR / item["after"]))
        if not all(path.is_file() for path in paths):
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
            self.assertFalse(result["neighborRowsNotReprojected"])
            self.assertTrue(result["neighborRowsFullyReprojected"])
            self.assertEqual([r["projectionStatus"] for r in result["neighborRows"]],
                             ["candidate-bracketed"] * 5)
            self.assertFalse(result["opticalVisibilityQualified"])
            self.assertFalse(result["movementEligible"])

    def test_second_view_neighbor_boundaries_shift_with_y(self):
        upper, middle = self.second_dark["darkGradientProfiles"]
        self.assertEqual([row["projectedLayerBoundaryPixels"] for row in upper["neighborRows"]],
                         [[1967, 1968], [1966, 1967], [1966, 1967],
                          [1965, 1966], [1964, 1965]])
        self.assertEqual([row["projectedLayerBoundaryPixels"] for row in middle["neighborRows"]],
                         [[1947, 1948], [1946, 1947], [1946, 1947],
                          [1945, 1946], [1944, 1945]])
        self.assertFalse(upper["opticalVisibilityQualified"])
        self.assertFalse(middle["movementEligible"])

    def test_unbracketed_projected_neighbor_is_marked_unknown(self):
        original = edge._projected_boundary

        def missing_one_row(frame, layers, indices, y, left, right):
            if y == 408:  # second-view upper pillar, +8 from its central row
                raise ValueError("optical-edge-projection-bracket-invalid")
            return original(frame, layers, indices, y, left, right)

        with mock.patch.object(edge, "_projected_boundary", side_effect=missing_one_row):
            report = edge.analyze_view("second", dark_gradient=True)
        upper = report["darkGradientProfiles"][0]
        self.assertFalse(upper["neighborRowsFullyReprojected"])
        self.assertEqual(upper["neighborRows"][-1]["projectionStatus"], "unavailable")
        self.assertFalse(upper["neighborRows"][-1]["darkBandCandidate"])
        self.assertFalse(report["opticalVisibilityQualified"])
        self.assertFalse(report["navigationQualified"])

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
