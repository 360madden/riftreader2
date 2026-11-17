"""Offline composite terrain + render placement regressions; no live game access."""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_pixel_composite as composite
from scripts import physical_pixel_ray
from scripts import physical_pixel_surface as surface


RAY = {"status": "available-candidate", "nativeEyeXYZ": [0, 0, 0],
       "unitDirectionXYZ": [0, 0, 1]}
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]


def layer(name, depth, shift_x=0):
    raw = (f"g {name}\nv {shift_x - 1} -1 {depth}\n"
           f"v {shift_x + 1} -1 {depth}\nv {shift_x} 1 {depth}\nf 1 2 3\n")
    vertices, faces = surface.parse_obj(raw.encode(), IDENTITY)
    return {"name": name, "vertices": vertices, "faces": faces,
            "source": {"testOnly": True}, "pins": []}


class CompositeMathTests(unittest.TestCase):
    def test_depth_order_picks_near_render_not_terrain(self):
        result = composite.compare_layers(RAY, [layer("terrain", 25),
                                                layer("temple-render", 8)])
        self.assertEqual(result["candidateFirst"]["layer"], "temple-render")
        self.assertEqual([r["distanceNative"] for r in result["orderedLayerCandidates"]],
                         [8, 25])
        self.assertEqual(result["layers"][0]["hitCount"], 1)
        self.assertFalse(result["obstacleQualified"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["visibleSurfaceQualified"])

    def test_open_path_and_displaced_temple_have_only_terrain(self):
        result = composite.compare_layers(RAY, [layer("terrain", 25),
                                                layer("temple-render", 8, shift_x=10)])
        self.assertEqual(result["candidateFirst"]["layer"], "terrain")
        self.assertEqual(result["layers"][1]["hitCount"], 0)

    def test_same_depth_across_layers_keeps_ambiguous(self):
        result = composite.compare_layers(RAY, [layer("terrain", 10),
                                                layer("temple-render", 10)])
        self.assertTrue(result["ambiguousFirstLayer"])
        self.assertIsNone(result["candidateFirst"])
        self.assertEqual(len(result["orderedLayerCandidates"]), 2)

    def test_no_hit_does_not_claim_clearance(self):
        result = composite.compare_layers(RAY, [layer("terrain", 10, shift_x=10),
                                                layer("temple-render", 8, shift_x=10)])
        self.assertEqual(result["status"], "no-candidate-intersection")
        self.assertIsNone(result["candidateFirst"])
        self.assertFalse(result["sourceCoverageComplete"])

    def test_pinned_image_hash_and_duplicate_json_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "receipt.json"
            path.write_bytes(b'{"x":1,"x":2}')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "duplicate-registration-key"):
                composite._json_pinned(path, digest, 1000, "receipt")
            with self.assertRaisesRegex(ValueError, "sha256-mismatch"):
                composite._read_pinned(path, "0" * 64, 1000, "receipt")


class RetainedSanctumWatchTests(unittest.TestCase):
    """Optional exact SHA-pinned local AMD capture/source reuse, offline only."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.capture = cls.root / (
            "artifacts/observe-wgc-27d58645e80e4880aa48faacb04ff743")
        cls.image = cls.capture / "image.png"
        cls.receipt = cls.capture / "image.png.json"
        cls.native = cls.root / (
            "artifacts/physical-native-facing-24b80f583f3a49778dacf9b8337862aa.json")
        cls.terrain = Path(
            "C:/work/RiftWorld/artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj")
        cls.terrain_reg = cls.root / (
            "artifacts/pixel-surface-p1-20261116/courtyard-identity-hypothesis.json")
        cls.temple_root = Path(
            "C:/work/RiftWorld/artifacts/p0-watch-temple-source-render-20261116-agent-iso-r1")
        cls.temple = cls.temple_root / "geometry.obj"
        cls.anchor = cls.temple_root / "atank-source-floor-anchor-exact-r2.json"
        cls.receipt_sha = "d4fafc4bb56a365b6a41cf76229e7cbbf2a9bb03867c558ca8601c06e977b4d6"
        cls.native_sha = "88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f"
        cls.anchor_sha = "6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525"
        files = (cls.image, cls.receipt, cls.native, cls.terrain, cls.terrain_reg,
                 cls.temple, cls.anchor)
        if not all(path.is_file() for path in files):
            raise unittest.SkipTest("exact historical AMD-DESKTOP WGC/RiftWorld sources absent")
        for path, sha in ((cls.receipt, cls.receipt_sha),
                          (cls.native, cls.native_sha), (cls.anchor, cls.anchor_sha)):
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise unittest.SkipTest("historical source has changed: " + str(path))

    def test_same_process_frame_and_four_landmark_composite(self):
        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        self.assertEqual(frame["identity"]["pid"], 77704)
        layers = [composite.load_terrain(self.terrain, self.terrain_reg),
                  composite.load_temple(self.temple, self.anchor, self.anchor_sha,
                                        frame["identity"])]
        self.assertEqual([len(layer["faces"]) for layer in layers], [227051, 1805])
        pixels = [(850, 530), (2200, 500), (1280, 1200), (1100, 640)]
        result = composite.analyze_pixels(frame, layers, pixels, 200)
        for row, expected_layer, expected_depth in zip(
                result["pixels"], ("temple-render", "temple-render",
                                   "temple-render", "terrain"),
                (13.8198, 6.0409, 8.6406, 32.8338)):
            with self.subTest(pixel=row["pixel"]):
                candidate = row["surfaceCandidates"]["candidateFirst"]
                self.assertEqual(candidate["layer"], expected_layer)
                self.assertAlmostEqual(candidate["distanceNative"], expected_depth, delta=.02)
                self.assertFalse(row["surfaceCandidates"]["visibleSurfaceQualified"])
                self.assertLess(max(row["rayForwardReprojectionErrorPixels"]), 1e-7)
        self.assertEqual(result["status"], "candidate-only")
        self.assertFalse(result["physicalBlockingQualified"])
        self.assertFalse(result["navigationQualified"])
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["movementEligible"])

        # Controls are intentionally NOT called blocking, depth, or physics evidence.
        raw = self.temple.read_bytes()
        rows = layers[1]["source"]["sourceToNativeRows"]
        for axis in (0, 2):
            shifted = [list(row) for row in rows]
            shifted[axis][3] += 10
            v, f = surface.parse_obj(raw, shifted)
            for pixel in pixels[:2]:
                ray = physical_pixel_ray.pixel_ray(frame["camera"], frame["mapping"],
                                                   *pixel)
                negative = surface.intersect_prepared(v, f, ray, max_distance=200)
                self.assertEqual(negative["hitCount"], 0)

    def test_rejects_wrong_process_and_native_source(self):
        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        wrong = {**frame["identity"], "pid": 77705}
        with self.assertRaisesRegex(ValueError, "temple-anchor-process-epoch-mismatch"):
            composite.load_temple(self.temple, self.anchor, self.anchor_sha, wrong)
        with self.assertRaisesRegex(ValueError, "native-after-sha256-mismatch"):
            composite.load_frame(self.image, self.receipt, self.receipt_sha,
                                 self.native, "0" * 64, expected_host="AMD-DESKTOP")


if __name__ == "__main__":
    unittest.main()
