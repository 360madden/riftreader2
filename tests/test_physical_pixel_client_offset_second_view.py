"""Offline second-view screen/client calibration, SHA-pinned native evidence.

This protects *candidate* projection alignment only; it never proves optical
visibility, collision/obstacle response, or permission to move the character.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import unittest

from scripts import physical_pixel_composite as composite
from scripts import physical_pixel_ray


class SecondViewClientOffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.image = cls.root / (
            "artifacts/observe-wgc-f37599014aaa422a94682503abb6d532/image.png")
        cls.receipt = cls.image.with_name("image.png.json")
        cls.native_before = cls.root / (
            "artifacts/physical-native-facing-82c8b813f64e4b46903f11d267dd4cc4.json")
        cls.native_after = cls.root / (
            "artifacts/physical-native-facing-dc22ffd6bcbe4518a167539b62f364a7.json")
        cls.temple = Path(
            "C:/work/RiftWorld/artifacts/"
            "p0-watch-temple-source-render-20261116-agent-iso-r1/geometry.obj")
        cls.anchor = cls.temple.with_name("atank-source-floor-anchor-exact-r2.json")
        cls.pins = (
            (cls.image, "5f09703eca7639f583e68bd40aea19d36d20483e3752ae743b776c90133c4c75"),
            (cls.receipt, "414b10c7d78be9d397d460f4eb2e7296144e574486ac491fa30ca6ec3eb168f9"),
            (cls.native_before, "d7a9f90fcaee7a18005dc2827faab1727a0ff93a6bde4b7e64e60be1074b8905"),
            (cls.native_after, "89dad03250c429cbe2a28e8261a84f1324df76b49ab94fc2503fed0a851b8f03"),
            (cls.anchor, "6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525"),
        )
        if not all(path.is_file() for path in
                   (cls.image, cls.receipt, cls.native_before, cls.native_after,
                    cls.temple, cls.anchor)):
            raise unittest.SkipTest("exact AMD-DESKTOP retained second-view assets unavailable")
        for path, expected in cls.pins:
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise AssertionError("historical source SHA changed: " + str(path))

        cls.frame = composite.load_frame(
            cls.image, cls.receipt, cls.pins[1][1],
            cls.native_before, cls.pins[2][1],
            cls.native_after, cls.pins[3][1],
            expected_host="AMD-DESKTOP")

    def test_client_top_23_pixel_centers_and_native_ray_inversion(self):
        frame = self.frame
        mapping = frame["mapping"]
        self.assertEqual(
            (mapping["frameWidth"], mapping["frameHeight"],
             mapping["clientLeft"], mapping["clientTop"],
             mapping["clientWidth"], mapping["clientHeight"]),
            (2560, 1392, 0, 23, 2560, 1369))
        self.assertEqual(frame["identity"]["host"], "AMD-DESKTOP")
        self.assertEqual(frame["identity"]["pid"], 77704)
        self.assertLessEqual(frame["source"]["nativeBracketSeconds"], 5)

        pixel = (1950, 400)
        correct = physical_pixel_ray.pixel_ray(frame["camera"], mapping, *pixel)
        self.assertEqual(correct["framePixelCenter"], [1950.5, 400.5])
        self.assertAlmostEqual(
            correct["normalizedClientXY"][1], (400.5 - 23) / 1369, places=12)
        self.assertLess(max(correct["forwardReprojectionErrorPixels"]), 1e-7)
        self.assertFalse(correct["movementEligible"])
        self.assertIsNone(correct["worldSurfaceXYZ"])

        with self.assertRaisesRegex(ValueError, "pixel-outside-captured-client"):
            physical_pixel_ray.pixel_ray(frame["camera"], mapping, 1950, 22)
        physical_pixel_ray.pixel_ray(frame["camera"], mapping, 1950, 23)

        # Counterfactual intentionally bypasses admitted Win32 geometry.
        # It demonstrates the material projection error if clientTop is lost.
        wrong = physical_pixel_ray.pixel_ray(
            frame["camera"], {**mapping, "clientTop": 0}, *pixel)
        pixel_y_drift = (wrong["normalizedClientXY"][1]
                         - correct["normalizedClientXY"][1]) * 1369
        self.assertAlmostEqual(pixel_y_drift, 23.0, places=10)
        dot = sum(a*b for a, b in zip(
            correct["unitDirectionXYZ"], wrong["unitDirectionXYZ"]))
        angular_error_deg = math.degrees(math.acos(max(-1., min(1., dot))))
        self.assertAlmostEqual(angular_error_deg, 0.73608856, delta=.0001)

    def test_render_temple_edge_candidate_shifts_without_client_top(self):
        frame = self.frame
        temple = composite.load_temple(
            self.temple, self.anchor, self.pins[4][1], frame["identity"])

        def temple_candidate(mapping, x):
            ray = physical_pixel_ray.pixel_ray(frame["camera"], mapping, x, 400)
            result = composite.compare_layers(ray, [temple], max_distance=200)
            self.assertFalse(result["visibleSurfaceQualified"])
            self.assertFalse(result["movementEligible"])
            return result["candidateFirst"]

        correct = frame["mapping"]
        # On the retained second view at y=400, x=1967 is the first
        # render-mesh temple candidate hit; x=1966 has no temple intersection.
        self.assertIsNone(temple_candidate(correct, 1966))
        first = temple_candidate(correct, 1967)
        self.assertIsNotNone(first)
        self.assertEqual(first["layer"], "temple-render")
        self.assertAlmostEqual(first["distanceNative"], 7.84562243, delta=.001)

        # Deliberately wrong mappings locate the same candidate edge 5px or
        # 4px earlier. Neither counterfactual is a visibility qualification.
        missing_top = {**correct, "clientTop": 0}
        self.assertIsNone(temple_candidate(missing_top, 1961))
        self.assertEqual(
            temple_candidate(missing_top, 1962)["layer"], "temple-render")
        wrong_full_frame = {**correct, "clientTop": 0, "clientHeight": 1392}
        self.assertIsNone(temple_candidate(wrong_full_frame, 1962))
        self.assertEqual(
            temple_candidate(wrong_full_frame, 1963)["layer"], "temple-render")


if __name__ == "__main__":
    unittest.main()
