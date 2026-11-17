"""BVH candidate-only parity against the authoritative unaccelerated ray contract."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from scripts import physical_pixel_composite as composite
from scripts import physical_pixel_mesh_accel as accel
from scripts import physical_pixel_ray
from scripts import physical_pixel_surface as surface

IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]


def _ray(x=0.0, y=0.0, z=0.0):
    return {"status": "available-candidate", "nativeEyeXYZ": [x, y, z],
            "unitDirectionXYZ": [0.0, 0.0, 1.0]}


class SyntheticBvhTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (b"g close\nv 0 -1 5\nv 1 -1 5\nv 0 1 5\nf 1 2 3\n"
               b"g backface\nf 1 3 2\n"
               b"g far\nv -1 -1 10\nv 1 -1 10\nv 0 1 10\nf 4 5 6\n"
               b"g degenerate\nv 10 10 12\nf 7 7 7\n")
        cls.vertices, cls.faces = surface.parse_obj(raw, IDENTITY)
        cls.index = accel.prepare(cls.vertices, cls.faces, leaf_size=4)

    def test_duplicate_front_and_back_edge_hits_preserve_contract(self):
        ray = _ray()
        expected = surface.intersect_prepared(self.vertices, self.faces, ray)
        actual = accel.intersect(self.index, ray)
        self.assertEqual(actual, expected)
        self.assertEqual(actual["degenerateTriangles"], 1)
        self.assertEqual(actual["hitCount"], 3)
        self.assertEqual(actual["hits"][0]["coincidentGroupSize"], 2)
        self.assertFalse(actual["movementEligible"])

    def test_selected_triangle_and_no_hit_match_exact(self):
        for ray, selected in ((_ray(), 2), (_ray(40, 40), None)):
            with self.subTest(ray=ray):
                expected = surface.intersect_prepared(
                    self.vertices, self.faces, ray, selected_triangle=selected)
                actual = accel.intersect(self.index, ray, selected_triangle=selected)
                self.assertEqual(actual, expected)

    def test_near_edge_tolerance_never_drops_an_exact_hit(self):
        for x in (-5e-11, 0.0, 5e-11, 5e-10):
            ray = _ray(x)
            with self.subTest(x=x):
                self.assertEqual(
                    accel.intersect(self.index, ray),
                    surface.intersect_prepared(self.vertices, self.faces, ray))

    def test_invalid_config_and_selected_miss_refuse(self):
        with self.assertRaisesRegex(ValueError, "bvh-leaf-size-invalid"):
            accel.prepare(self.vertices, self.faces, leaf_size=3)
        ray = _ray()
        with self.assertRaisesRegex(ValueError, "selected-triangle-not-intersected"):
            accel.intersect(self.index, ray, selected_triangle=4)

    def test_prepared_geometry_does_not_alias_mutable_caller_inputs(self):
        mutable_vertices = [list(point) for point in self.vertices]
        mutable_faces = [(list(indices), group) for indices, group in self.faces]
        index = accel.prepare(mutable_vertices, mutable_faces, leaf_size=4)
        ray = _ray()
        before = surface.intersect_prepared(mutable_vertices, mutable_faces, ray)
        self.assertEqual(accel.intersect(index, ray), before)
        self.assertIsInstance(index.vertices, tuple)
        self.assertIsInstance(index.vertices[0], tuple)
        self.assertIsInstance(index.faces, tuple)
        self.assertIsInstance(index.faces[0][0], tuple)
        mutable_vertices[0][0] = 1000.0
        mutable_faces[0][0][0] = 6
        mutable_vertices.clear()
        mutable_faces.clear()
        self.assertEqual(accel.intersect(index, ray), before)
        with self.assertRaises(AttributeError):
            index.faces = ()
        with self.assertRaises(TypeError):
            index.vertices[0][0] = 200.0


class RetainedWatchBvhParityTests(unittest.TestCase):
    """Only runs with the exact preserved AMD frame and source geometry."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        shot = root / "artifacts/observe-wgc-27d58645e80e4880aa48faacb04ff743"
        native_before = root / "artifacts/physical-native-facing-bf8006fadcf04512a338a90ef534976e.json"
        native = root / "artifacts/physical-native-facing-24b80f583f3a49778dacf9b8337862aa.json"
        terrain = Path(
            "C:/work/RiftWorld/artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj")
        reg = root / "artifacts/pixel-surface-p1-20261116/courtyard-identity-hypothesis.json"
        temple_root = Path(
            "C:/work/RiftWorld/artifacts/p0-watch-temple-source-render-20261116-agent-iso-r1")
        temple = temple_root / "geometry.obj"
        anchor = temple_root / "atank-source-floor-anchor-exact-r2.json"
        inputs = (shot/"image.png", shot/"image.png.json", native_before, native,
                  terrain, reg, temple, anchor)
        if not all(path.is_file() for path in inputs):
            raise unittest.SkipTest("pinned AMD Watch evidence unavailable")
        receipt_sha = "d4fafc4bb56a365b6a41cf76229e7cbbf2a9bb03867c558ca8601c06e977b4d6"
        before_sha = "609037b2a0058a4ea7f16e2d0cbb1faae630c5cea4fad125a4603d0fb5c24ae7"
        native_sha = "88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f"
        anchor_sha = "6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525"
        for path, sha in ((shot/"image.png.json", receipt_sha),
                          (native_before, before_sha),
                          (native, native_sha), (anchor, anchor_sha)):
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise unittest.SkipTest("retained source hash changed")
        cls.frame = composite.load_frame(shot/"image.png", shot/"image.png.json",
                                         receipt_sha, native_before, before_sha, native, native_sha,
                                         expected_host="AMD-DESKTOP")
        cls.layers = (composite.load_terrain(terrain, reg),
                      composite.load_temple(temple, anchor, anchor_sha,
                                            cls.frame["identity"]))
        cls.indices = [accel.prepare(item["vertices"], item["faces"])
                       for item in cls.layers]

    def test_real_landmark_and_edge_rays_exactly_match_both_layers(self):
        for pixel in ((835,530), (850,530), (950,530), (980,530),
                      (1100,640), (1280,1200), (2150,500), (2200,500)):
            ray = physical_pixel_ray.pixel_ray(
                self.frame["camera"], self.frame["mapping"], *pixel)
            for layer, index in zip(self.layers, self.indices):
                with self.subTest(pixel=pixel, layer=layer["name"]):
                    baseline = surface.intersect_prepared(
                        layer["vertices"], layer["faces"], ray, max_distance=200)
                    result = accel.intersect(index, ray, max_distance=200)
                    self.assertEqual(result, baseline)
                    self.assertLess(accel.candidate_count(
                        index, ray, max_distance=200), len(layer["faces"]))
