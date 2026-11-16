"""Offline screenshot-pixel ray inversion; no RIFT process or input access."""
from copy import deepcopy
import contextlib
import io
import json
import math
from pathlib import Path
import unittest

from scripts import physical_pixel_ray as pick
from scripts import physical_rift
from tests.test_export_physical_rerun import replace_projection
from tests.test_physical_facing import optical_camera
from tests.test_plot_physical_waypoints import PlotTests


def mapping():
    return {"status": "available-candidate", "frameWidth": 320, "frameHeight": 200,
            "clientLeft": 5, "clientTop": 25, "clientWidth": 310, "clientHeight": 170}


class PixelRayMathTests(unittest.TestCase):
    def test_pixel_center_inverse_matches_native_forward_projector(self):
        camera = optical_camera()
        for x, y in ((160, 110), (10, 40), (310, 188)):
            with self.subTest(pixel=(x, y)):
                result = pick.pixel_ray(camera, mapping(), x, y)
                self.assertFalse(result["movementEligible"])
                self.assertIsNone(result["worldSurfaceXYZ"])
                self.assertEqual([x + .5, y + .5], result["framePixelCenter"])
                self.assertAlmostEqual(math.hypot(*result["unitDirectionXYZ"]), 1)
                forward = physical_rift._project_world_point(camera, dict(zip(
                    ("x", "y", "z"), result["displayPlanePointXYZ"])))
                self.assertAlmostEqual((forward["normalizedX"] * 310 + 5), x + .5, places=8)
                self.assertAlmostEqual((forward["normalizedY"] * 170 + 25), y + .5, places=8)
                self.assertLess(max(result["forwardReprojectionErrorPixels"]), 1e-6)

    def test_asymmetric_native_viewport_offsets_and_inverted_y(self):
        camera = optical_camera()
        matrix = camera["projectionRowMajor"]
        xrow = [1.7*a + .2*b for a, b in zip(matrix[:4], matrix[12:16])]
        yrow = [.9*a - .15*b for a, b in zip(matrix[4:8], matrix[12:16])]
        replace_projection(camera, xrow + yrow + matrix[8:], [.125, .875, .75, .125])
        result = pick.pixel_ray(camera, mapping(), 160, 110)
        self.assertEqual(result["status"], "available-candidate")
        self.assertNotAlmostEqual(result["viewportUV"][0], result["normalizedClientXY"][0])
        for x, y in ((5, 100), (160, 25), (314, 100), (160, 194)):
            with self.subTest(outside=(x, y)), self.assertRaisesRegex(
                    ValueError, "pixel-outside-native-camera-viewport"):
                pick.pixel_ray(camera, mapping(), x, y)

    def test_bad_mapping_pixel_and_camera_refuse_without_world_guess(self):
        camera = optical_camera()
        cases = ((-1, 110, mapping(), "outside-captured-client"),
                 (160, 24, mapping(), "outside-captured-client"),
                 (315, 110, mapping(), "outside-captured-client"),
                 (True, 110, mapping(), "pixel-coordinates-must-be-integers"),
                 (160, 110, {"status": "unavailable"}, "validated-client-frame"),
                 (160, 110, dict(mapping(), clientWidth=True), "validated-client-frame"),
                 (160, 110, dict(mapping(), clientWidth=400), "invalid-client-frame-bounds"))
        for x, y, bounds, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                pick.pixel_ray(camera, bounds, x, y)
        camera = deepcopy(camera)
        camera["projectionRowMajor"][3] += 1
        with self.assertRaisesRegex(ValueError, "native-view-rays-unavailable"):
            pick.pixel_ray(camera, mapping(), 160, 110)


class RetainedPixelRayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = PlotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.run_render()

    def test_saved_wgc_native_bracket_produces_hash_bound_candidate(self):
        before = self.fixture.image.read_bytes()
        result = pick.pick_retained(self.fixture.root / "observation.json",
                                    self.fixture.root / "route.json", 160, 110)
        self.assertEqual("rr2.retained-frame-pixel-ray/1", result["schema"])
        self.assertEqual("available-candidate", result["status"])
        self.assertEqual([160, 110], result["ray"]["framePixel"])
        self.assertEqual(self.fixture.before["identity"]["processId"], result["identity"]["processId"])
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["movementEligible"])
        self.assertEqual(before, self.fixture.image.read_bytes())

    def test_changed_mapping_is_refused_by_existing_wgc_admission(self):
        frame = json.loads(self.fixture.receipt.read_text())
        frame["clientFrameMapping"]["clientLeft"] += 1
        self.fixture.receipt.write_text(json.dumps(frame))
        with self.assertRaisesRegex(ValueError, "visual-client-frame-bounds-mismatch"):
            pick.pick_retained(self.fixture.root / "observation.json",
                               self.fixture.root / "route.json", 160, 110)

    def test_cli_emits_machine_readable_response_and_fails_closed(self):
        obs = self.fixture.root / "observation.json"
        route = self.fixture.root / "route.json"
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            code = pick.main(["--observation", str(obs), "--route", str(route),
                              "--pixel-x", "160", "--pixel-y", "110"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(sink.getvalue())["ray"]["framePixel"], [160, 110])
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            code = pick.main(["--observation", str(obs), "--route", str(route),
                              "--pixel-x", "0", "--pixel-y", "0"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(sink.getvalue())["status"], "blocked")
