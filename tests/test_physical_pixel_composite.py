"""Offline composite terrain + render placement regressions; no live game access."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from scripts import physical_pixel_mesh_accel as mesh_accel
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

    def test_footprint_radius_is_bounded_before_any_ray(self):
        with self.assertRaisesRegex(ValueError, "pixel-selection-radius-invalid"):
            composite.analyze_pixels({}, [], [(10, 10)], pixel_selection_radius=4)

    def test_bvh_exact_synthetic_depth_ties_and_no_hits(self):
        for case_layers in (
                [layer("terrain", 25), layer("temple-render", 8)],
                [layer("terrain", 10), layer("temple-render", 10)],
                [layer("terrain", 10, shift_x=10),
                 layer("temple-render", 8, shift_x=10)],
                [layer("terrain", 25), layer("temple-render", 8, shift_x=10)]):
            with self.subTest(depths=[
                    row["faces"][0][1] for row in case_layers]):
                baseline = composite.compare_layers(RAY, case_layers, max_distance=200)
                indices = [mesh_accel.prepare(row["vertices"], row["faces"])
                           for row in case_layers]
                fast = composite.compare_layers(
                    RAY, case_layers, max_distance=200, indices=indices)
                self.assertEqual(fast, baseline)
                for flag in ("movementEligible", "visibleSurfaceQualified",
                             "obstacleQualified", "sourceCoverageComplete"):
                    self.assertFalse(fast[flag])

    def test_accel_mode_rejected_before_source_access(self):
        with self.assertRaisesRegex(ValueError, "composite-accel-mode-invalid"):
            composite.analyze_pixels({}, [], [(10, 10)], accel_mode="unexpected")

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
        cls.native_before = cls.root / (
            "artifacts/physical-native-facing-bf8006fadcf04512a338a90ef534976e.json")
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
        cls.before_sha = "609037b2a0058a4ea7f16e2d0cbb1faae630c5cea4fad125a4603d0fb5c24ae7"
        cls.native_sha = "88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f"
        cls.anchor_sha = "6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525"
        files = (cls.image, cls.receipt, cls.native_before, cls.native,
                 cls.terrain, cls.terrain_reg, cls.temple, cls.anchor)
        if not all(path.is_file() for path in files):
            raise unittest.SkipTest("exact historical AMD-DESKTOP WGC/RiftWorld sources absent")
        for path, sha in ((cls.receipt, cls.receipt_sha),
                          (cls.native_before, cls.before_sha),
                          (cls.native, cls.native_sha), (cls.anchor, cls.anchor_sha)):
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise unittest.SkipTest("historical source has changed: " + str(path))

    def test_same_process_frame_and_four_landmark_composite(self):
        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha,
            self.native_before, self.before_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        self.assertEqual(frame["identity"]["pid"], 77704)
        self.assertEqual(frame["source"]["nativeBeforeSha256"], self.before_sha)
        self.assertLess(frame["source"]["nativeBracketSeconds"], 5)
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

    def test_pinned_horizontal_pillar_edge_candidates(self):
        """Replay candidate layer changes at pictured pillar edges, not optical depth."""
        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha,
            self.native_before, self.before_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        layers = [composite.load_terrain(self.terrain, self.terrain_reg),
                  composite.load_temple(self.temple, self.anchor, self.anchor_sha,
                                        frame["identity"])]
        # The retained left pillar has candidates between x=835..850 and
        # x=950..980 at y=530; the right pillar begins between x=2150..2200.
        # These are renderer-space hypotheses, never physics or nav evidence.
        points = [(835, 530), (850, 530), (950, 530), (980, 530),
                  (2150, 500), (2200, 500), (2500, 500)]
        expected = ("terrain", "temple-render", "temple-render", "terrain",
                    "terrain", "temple-render", "temple-render")
        report = composite.analyze_pixels(frame, layers, points, max_distance=200)
        self.assertEqual(report["status"], "candidate-only")
        for row, layer_name in zip(report["pixels"], expected):
            with self.subTest(pixel=row["pixel"]):
                candidates = row["surfaceCandidates"]
                self.assertEqual(candidates["candidateFirst"]["layer"], layer_name)
                self.assertFalse(candidates["ambiguousFirstLayer"])
                self.assertFalse(candidates["visibleSurfaceQualified"])
        self.assertFalse(report["physicalBlockingQualified"])
        self.assertFalse(report["navigationQualified"])
        self.assertFalse(report["inputSent"])

    def test_reused_cardinal_footprint_keeps_candidate_only(self):
        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha,
            self.native_before, self.before_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        layers = [composite.load_terrain(self.terrain, self.terrain_reg),
                  composite.load_temple(self.temple, self.anchor, self.anchor_sha,
                                        frame["identity"])]
        result = composite.analyze_pixels(
            frame, layers, [(850, 530), (1100, 640)],
            pixel_selection_radius=2)
        for row, expected in zip(result["pixels"], ("temple-render", "terrain")):
            footprint = row["pixelFootprint"]
            self.assertEqual(footprint["sampleCount"], 9)
            self.assertEqual(footprint["radiusPixels"], 2)
            self.assertEqual(footprint["samples"][0]["firstMeshGroup"], expected)
            self.assertFalse(footprint["visibleSurfaceQualified"])
            self.assertFalse(footprint["movementEligible"])
        self.assertFalse(result["movementEligible"])

    def test_bvh_exact_full_reports_on_pinned_edges_and_radius_two(self):
        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha,
            self.native_before, self.before_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        layers = [composite.load_terrain(self.terrain, self.terrain_reg),
                  composite.load_temple(self.temple, self.anchor, self.anchor_sha,
                                        frame["identity"])]
        # 26 edge pixels + four physical landmarks; scan remains candidate-only.
        edge_pixels = ([(x, 530) for x in
                        (600, 700, 760, 800, 820, 835, 850, 880, 920,
                         950, 980, 1010, 1050, 1100)] +
                       [(x, 500) for x in
                        (1800, 1900, 1980, 2020, 2060, 2100, 2150, 2200,
                         2250, 2300, 2400, 2500)])
        landmarks = [(850, 530), (2200, 500), (1280, 1200), (1100, 640)]
        self.assertEqual(len(edge_pixels), 26)
        for points, radius in ((edge_pixels, 0), (landmarks, 2)):
            with self.subTest(pixels=len(points), radius=radius):
                baseline = composite.analyze_pixels(
                    frame, layers, points, max_distance=200,
                    pixel_selection_radius=radius)
                fast = composite.analyze_pixels(
                    frame, layers, points, max_distance=200,
                    pixel_selection_radius=radius, accel_mode="bvh")
                self.assertEqual(fast, baseline)
                self.assertEqual(fast["status"], "candidate-only")
                for flag in ("inputSent", "navigationQualified",
                             "movementEligible", "physicalBlockingQualified",
                             "visibleSurfaceQualified"):
                    self.assertFalse(fast[flag])
                if radius:
                    self.assertTrue(all(
                        row["pixelFootprint"]["sampleCount"] == 9
                        for row in fast["pixels"]))

    def test_preview_is_separate_and_does_not_overwrite_source(self):
        from PIL import Image

        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha,
            self.native_before, self.before_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        layers = [composite.load_terrain(self.terrain, self.terrain_reg),
                  composite.load_temple(self.temple, self.anchor, self.anchor_sha,
                                        frame["identity"])]
        report = composite.analyze_pixels(frame, layers, [(850, 530)])
        with TemporaryDirectory() as folder:
            output = Path(folder) / "candidate-preview.png"
            preview = composite.render_preview(frame, report, output)
            self.assertTrue(output.is_file())
            self.assertEqual(preview["status"], "offline-candidate-preview")
            self.assertEqual(preview["sha256"],
                             hashlib.sha256(output.read_bytes()).hexdigest())
            with Image.open(output) as rendered:
                self.assertEqual(rendered.size, (2560, 1392))
            self.assertEqual(hashlib.sha256(self.image.read_bytes()).hexdigest(),
                             frame["source"]["imageSha256"])
            with self.assertRaisesRegex(
                    ValueError, "preview-output-must-be-new-png-in-existing-directory"):
                composite.render_preview(frame, report, output)
            # Simulate TOCTOU: another writer creates the target after a stale
            # existence precheck. Exclusive 'xb' open must preserve its bytes.
            before = output.read_bytes()
            real_exists = Path.exists
            def stale_exists(path):
                return False if str(path) == str(output) else real_exists(path)
            with mock.patch.object(Path, "exists", stale_exists):
                with self.assertRaises(FileExistsError):
                    composite.render_preview(frame, report, output)
            self.assertEqual(output.read_bytes(), before)

    def test_native_before_hash_and_camera_stability_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "native-before-sha256-mismatch"):
            composite.load_frame(
                self.image, self.receipt, self.receipt_sha,
                self.native_before, "0" * 64, self.native, self.native_sha,
                expected_host="AMD-DESKTOP")
        with TemporaryDirectory() as folder:
            path = Path(folder) / "unstable-before.json"
            data = json.loads(self.native_before.read_text(encoding="utf-8"))
            data["observation"]["targetProjectionCameraStableCandidate"] = False
            data["observations"][-1]["targetProjectionCameraStableCandidate"] = False
            path.write_text(json.dumps(data), encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "camera"):
                composite.load_frame(
                    self.image, self.receipt, self.receipt_sha,
                    path, digest, self.native, self.native_sha,
                    expected_host="AMD-DESKTOP")

    def test_native_before_wgc_after_timestamp_order_required(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "late-before.json"
            data = json.loads(self.native_before.read_text(encoding="utf-8"))
            stamp = "2026-11-16T23:49:44.5000000+00:00"
            data["observation"]["completedAtUtc"] = stamp
            data["observations"][-1]["completedAtUtc"] = stamp
            path.write_text(json.dumps(data), encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "native-before-wgc-after-bracket-invalid"):
                composite.load_frame(
                    self.image, self.receipt, self.receipt_sha,
                    path, digest, self.native, self.native_sha,
                    expected_host="AMD-DESKTOP")

    def test_actual_png_dimensions_must_match_pinned_receipt(self):
        from PIL import Image

        with TemporaryDirectory() as folder:
            directory = Path(folder)
            small = directory / "tiny.png"
            Image.new("RGB", (64, 64), (32, 80, 150)).save(small)
            receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
            raw = small.read_bytes()
            receipt["outputPath"] = str(small.resolve())
            receipt["imageSha256"] = hashlib.sha256(raw).hexdigest().upper()
            receipt["imageBytes"] = len(raw)
            receipt_path = directory / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            digest = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "visual-png-dimensions-mismatch"):
                composite.load_frame(
                    small, receipt_path, digest, self.native_before,
                    self.before_sha, self.native, self.native_sha,
                    expected_host="AMD-DESKTOP")

    def test_rejects_wrong_process_and_native_source(self):
        frame = composite.load_frame(
            self.image, self.receipt, self.receipt_sha,
            self.native_before, self.before_sha, self.native, self.native_sha,
            expected_host="AMD-DESKTOP")
        wrong = {**frame["identity"], "pid": 77705}
        with self.assertRaisesRegex(ValueError, "temple-anchor-process-epoch-mismatch"):
            composite.load_temple(self.temple, self.anchor, self.anchor_sha, wrong)
        with self.assertRaisesRegex(ValueError, "native-after-sha256-mismatch"):
            composite.load_frame(self.image, self.receipt, self.receipt_sha,
                                 self.native_before, self.before_sha,
                                 self.native, "0" * 64, expected_host="AMD-DESKTOP")


if __name__ == "__main__":
    unittest.main()
