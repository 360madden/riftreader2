"""Independent analytic optical and triangle-boundary invariants (offline only).

The ray is checked against known world coordinates, not only its own forward
projector. Triangles are mathematical candidates: no scene, floor, obstacle,
collision, or movement qualification is asserted here.
"""
from __future__ import annotations

import math
import unittest

from scripts import physical_pixel_mesh_accel as accel
from scripts import physical_pixel_ray
from scripts import physical_pixel_surface as surface
from tests.test_physical_facing import optical_camera


MAPPING = {
    "status": "available-candidate",
    "frameWidth": 320, "frameHeight": 200,
    "clientLeft": 5, "clientTop": 25, "clientWidth": 310, "clientHeight": 170,
}


def unit_ray_at(x, y, z=10):
    length = math.hypot(x, y, z)
    return {"status": "available-candidate", "nativeEyeXYZ": [0, 0, 0],
            "unitDirectionXYZ": [x / length, y / length, z / length]}


class IndependentNumericInvariantTests(unittest.TestCase):
    def assert_exact_bvh_parity(self, vertices, faces, ray, **kwargs):
        direct = surface.intersect_prepared(vertices, faces, ray, **kwargs)
        fast = accel.intersect(accel.prepare(vertices, faces, leaf_size=4),
                               ray, **kwargs)
        self.assertEqual(direct, fast)
        self.assertFalse(direct["floorQualified"])
        self.assertFalse(direct["movementEligible"])
        self.assertFalse(direct["occlusionQualified"])
        return direct

    def test_known_screen_quadrants_hit_analytical_native_points(self):
        # Optical fixture's world eye is (7427,871,2936), facing +Z;
        # projection X is NEGATIVE world X (left image => +world X).
        # Positive world Y means up on the top-origin captured image.
        camera = optical_camera()
        eye = (7427, 871, 2936)
        cases = (("top_left", 82, 67, +5, +5),
                 ("top_right", 237, 67, -5, +5),
                 ("bottom_left", 82, 152, +5, -5),
                 ("bottom_right", 237, 152, -5, -5))
        vertices, faces = [], []
        for label, _x, _y, dx, dy in cases:
            wx, wy, wz = eye[0] + dx, eye[1] + dy, eye[2] + 10
            start = len(vertices)
            vertices.extend(((wx - .5, wy - .5, wz),
                             (wx + .5, wy - .5, wz),
                             (wx, wy + .5, wz)))
            faces.append(((start, start + 1, start + 2), label))
        expected_length = math.hypot(5, 5, 10)
        for label, x, y, dx, dy in cases:
            with self.subTest(label=label):
                ray = physical_pixel_ray.pixel_ray(camera, MAPPING, x, y)
                self.assertEqual(ray["nativeEyeXYZ"], list(eye))
                for actual, expected in zip(
                    ray["unitDirectionXYZ"],
                    (dx / expected_length, dy / expected_length,
                     10 / expected_length),
                ):
                    self.assertAlmostEqual(actual, expected, places=9)
                report = self.assert_exact_bvh_parity(
                    vertices, faces, ray, max_distance=20)
                self.assertEqual(report["hitCount"], 1)
                self.assertEqual(report["hits"][0]["meshGroup"], label)
                self.assertAlmostEqual(report["hits"][0]["distanceNative"],
                                       expected_length, places=8)
                for actual, expected in zip(report["candidateFirstXYZ"],
                                             (eye[0] + dx, eye[1] + dy,
                                              eye[2] + 10)):
                    self.assertAlmostEqual(actual, expected, places=8)

    def test_shared_edge_and_reverse_winding_keep_exact_tie_depth(self):
        # Ray at (1,1,10) lies exactly on the diagonal shared by faces 1/2;
        # face 3 reverses face 1, so only frontFacing may differ.
        vertices = ((0, 0, 10), (2, 0, 10), (0, 2, 10), (2, 2, 10))
        faces = (((0, 1, 2), "first"),
                 ((1, 3, 2), "second"),
                 ((0, 2, 1), "reverse"))
        report = self.assert_exact_bvh_parity(
            vertices, faces, unit_ray_at(1, 1),
            max_distance=20, selected_triangle=3)
        self.assertEqual(report["hitCount"], 3)
        self.assertEqual(report["distinctDepthGroups"], 1)
        self.assertEqual([item["triangleIndex"] for item in report["hits"]],
                         [1, 2, 3])
        self.assertEqual([item["coincidentGroupSize"] for item in report["hits"]],
                         [3, 3, 3])
        self.assertEqual([item["frontFacing"] for item in report["hits"]],
                         [False, False, True])
        self.assertEqual(report["selectedHit"]["triangleIndex"], 3)
        self.assertFalse(report["selectedHit"]["admissionEligible"])

    def test_barycentric_edge_epsilon_and_bvh_pad_stay_consistent(self):
        vertices = ((0, 0, 10), (2, 0, 10), (0, 2, 10))
        faces = (((0, 1, 2), "edge"),)
        on_edge = self.assert_exact_bvh_parity(
            vertices, faces, unit_ray_at(0, .6), max_distance=20)
        self.assertEqual(on_edge["hitCount"], 1)
        # u=x/2=-5e-11 is inside the explicitly allowed -1e-10 tolerance.
        near = self.assert_exact_bvh_parity(
            vertices, faces, unit_ray_at(-1e-10, .6), max_distance=20)
        self.assertEqual(near["hitCount"], 1)
        self.assertLess(near["hits"][0]["barycentric"][1], 0)
        # u=-2e-10 must be rejected by both exact and accelerated paths.
        far = self.assert_exact_bvh_parity(
            vertices, faces, unit_ray_at(-4e-10, .6), max_distance=20)
        self.assertEqual(far["hitCount"], 0)


if __name__ == "__main__":
    unittest.main()
