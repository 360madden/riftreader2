"""P1 candidate intersections; synthetic and optional archived offline RIFT evidence."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_pixel_surface as surface
from scripts import physical_pixel_ray
from tests.test_plot_physical_waypoints import PlotTests

IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
RAY = {"status": "available-candidate", "nativeEyeXYZ": [0, 0, 0],
       "unitDirectionXYZ": [0, 0, 1]}
LAYERS = b"""g near
v -2 -2 5
v 2 -2 5
v 0 2 5
f 1 2 3
g shared
f 1 2 3
g farther
v -2 -2 8
v 0 2 8
v 2 -2 8
f 4 5 6
g behind
v -2 -2 -2
v 2 -2 -2
v 0 2 -2
f 7 8 9
g degenerate
v 0 0 6
v 1 0 6
v 2 0 6
f 10 11 12
"""


def registration(mesh_bytes, **changes):
    data = {"schema": surface.REGISTRATION_SCHEMA,
            "meshSha256": hashlib.sha256(mesh_bytes).hexdigest(),
            "sourceFrame": "riftworld-source-xyz-y-up",
            "sourceToNativeRows": IDENTITY,
            "qualification": "candidate-only"}
    data.update(changes)
    return data


class TriangleRayTests(unittest.TestCase):
    def test_near_duplicate_and_far_floor_stay_separate_and_sorted(self):
        result = surface.intersect_obj(LAYERS, RAY, IDENTITY)
        self.assertEqual(result["status"], "candidate-hits")
        self.assertEqual((result["verticesChecked"], result["trianglesChecked"]), (12, 5))
        self.assertEqual(result["degenerateTriangles"], 1)
        self.assertEqual((result["hitCount"], result["distinctDepthGroups"]), (3, 2))
        self.assertEqual([hit["distanceNative"] for hit in result["hits"]], [5, 5, 8])
        self.assertEqual([hit["depthGroup"] for hit in result["hits"]], [1, 1, 2])
        self.assertEqual([hit["coincidentGroupSize"] for hit in result["hits"]], [2, 2, 1])
        self.assertEqual([hit["meshGroup"] for hit in result["hits"]],
                         ["near", "shared", "farther"])
        self.assertFalse(result["hits"][0]["frontFacing"])
        self.assertTrue(result["hits"][2]["frontFacing"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["floorQualified"])
        self.assertFalse(result["occlusionQualified"])
        self.assertFalse(result["sourceCoverageComplete"])

    def test_explicit_selection_requires_actual_hit_without_floor_promotion(self):
        chosen = surface.intersect_obj(LAYERS, RAY, IDENTITY, selected_triangle=3)
        self.assertEqual(chosen["selectedTriangleIndex"], 3)
        self.assertEqual(chosen["selectedHit"]["candidateXYZ"], [0.0, 0.0, 8.0])
        self.assertEqual(chosen["selectedHit"]["depthGroup"], 2)
        self.assertFalse(chosen["selectedHit"]["admissionEligible"])
        self.assertFalse(chosen["selectedHit"]["worldSurfaceVerified"])
        self.assertFalse(chosen["movementEligible"])
        self.assertIsNone(surface.intersect_obj(LAYERS, RAY, IDENTITY)["selectedHit"])
        for index, reason in ((0, "selected-triangle-index-invalid"),
                              (True, "selected-triangle-index-invalid"),
                              (4, "selected-triangle-not-intersected"),
                              (6, "selected-triangle-out-of-mesh")):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, reason):
                surface.intersect_obj(LAYERS, RAY, IDENTITY, selected_triangle=index)

    def test_distance_clip_and_parallel_ray_do_not_invent_surface(self):
        clipped = surface.intersect_obj(LAYERS, RAY, IDENTITY, max_distance=6)
        self.assertEqual([hit["distanceNative"] for hit in clipped["hits"]], [5, 5])
        missed = surface.intersect_obj(LAYERS, dict(RAY, unitDirectionXYZ=[0, 1, 0]),
                                       IDENTITY)
        self.assertEqual(missed["status"], "no-candidate-intersection")
        self.assertIsNone(missed["candidateFirstXYZ"])
        self.assertEqual(missed["hitCount"], 0)

    def test_affine_translation_changes_candidate_world_position(self):
        translated = [[1, 0, 0, 10], [0, 1, 0, -3], [0, 0, 1, 0]]
        eye = dict(RAY, nativeEyeXYZ=[10, -3, 0])
        result = surface.intersect_obj(LAYERS, eye, translated)
        self.assertEqual(result["candidateFirstXYZ"], [10.0, -3.0, 5.0])

    def test_invalid_unit_ray_distance_nonfinite_or_empty_mesh_refuse(self):
        for ray, depth, reason in (
            (dict(RAY, unitDirectionXYZ=[0, 0, 2]), 20, "ray-not-unit-length"),
            (RAY, float("inf"), "max-distance-invalid"),
            (RAY, -1, "max-distance-invalid"),
            (dict(RAY, nativeEyeXYZ=[float("nan"), 0, 0]), 20,
             "native-eye-must-be-finite-xyz"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                surface.intersect_obj(LAYERS, ray, IDENTITY, depth)
        for raw, reason in ((b"f 1 2 3\n", "face-forward-index"),
                            (b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3 1\n",
                             "mesh-non-triangle"),
                            (b"v nan 0 0\nf 1 1 1\n", "mesh-vertex-invalid"),
                            (b"v 0 0 0\n", "mesh-has-no-triangles"),
                            (b"v 0 0 0\nl 1 2\nf 1 1 1\n",
                             "unsupported-mesh-primitive")):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, reason):
                surface.parse_obj(raw, IDENTITY)

    def test_many_identical_hits_report_truncation_but_exact_counts(self):
        raw = b"v -1 -1 5\nv 1 -1 5\nv 0 1 5\n" + b"f 1 2 3\n" * 90
        result = surface.intersect_obj(raw, RAY, IDENTITY, selected_triangle=90)
        self.assertEqual(result["hitCount"], 90)
        self.assertEqual(result["selectedHit"]["triangleIndex"], 90)
        self.assertFalse(result["selectedHit"]["admissionEligible"])
        self.assertEqual(result["distinctDepthGroups"], 1)
        self.assertTrue(result["hitsTruncated"])
        self.assertEqual(len(result["hits"]), surface.MAX_REPORTED_HITS)
        self.assertEqual(result["hits"][0]["coincidentGroupSize"], 90)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="rr2-p1-reg-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "registration.json"

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_sha_pinned_candidate_only_source_registration(self):
        self.write(registration(LAYERS))
        loaded = surface.load_registration(self.path, hashlib.sha256(LAYERS).hexdigest())
        self.assertEqual(loaded["sourceToNativeRows"], IDENTITY)
        self.assertEqual(loaded["qualification"], "candidate-only")
        self.assertEqual(loaded["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_wrong_hash_fake_qualification_and_singular_transform_refuse(self):
        cases = (
            (registration(LAYERS), "0" * 64, "registration-mesh-sha256-mismatch"),
            (registration(LAYERS, qualification="verified"),
             hashlib.sha256(LAYERS).hexdigest(), "registration-must-be-candidate-only"),
            (registration(LAYERS, sourceToNativeRows=[[1, 0, 0, 0]] * 3),
             hashlib.sha256(LAYERS).hexdigest(), "registration-affine-transform-singular"),
        )
        for data, expected_sha, reason in cases:
            with self.subTest(reason=reason):
                self.write(data)
                with self.assertRaisesRegex(ValueError, reason):
                    surface.load_registration(self.path, expected_sha)

    def test_duplicate_json_key_and_nonfinite_transform_refuse(self):
        self.path.write_text('{"schema":"foo","schema":"bar"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate-registration-key"):
            surface.load_registration(self.path, hashlib.sha256(LAYERS).hexdigest())
        self.path.write_text('{"schema":NaN}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "non-finite-registration"):
            surface.load_registration(self.path, hashlib.sha256(LAYERS).hexdigest())


def perpendicular(direction):
    trial = (0, 1, 0) if abs(direction[1]) < .9 else (1, 0, 0)
    u = surface._cross(direction, trial)
    norm = math.hypot(*u)
    u = tuple(value / norm for value in u)
    v = surface._cross(direction, u)
    return u, v


def centered_triangle(ray, distance):
    eye = ray["nativeEyeXYZ"]
    direction = ray["unitDirectionXYZ"]
    u, v = perpendicular(direction)
    center = [eye[i] + direction[i] * distance for i in range(3)]
    return [[center[i] - 2 * u[i] - 2 * v[i] for i in range(3)],
            [center[i] + 2 * u[i] - 2 * v[i] for i in range(3)],
            [center[i] + 4 * v[i] for i in range(3)]]


class RetainedMeshTests(unittest.TestCase):
    def setUp(self):
        self.fixture = PlotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.run_render()
        self.obs = self.fixture.root / "observation.json"
        self.route = self.fixture.root / "route.json"
        self.mesh = self.fixture.root / "synthetic.obj"
        self.reg = self.fixture.root / "mesh-registration.json"
        saved_ray = physical_pixel_ray.pick_retained(self.obs, self.route, 160, 110)["ray"]
        points = centered_triangle(saved_ray, 12) + centered_triangle(saved_ray, 18)
        lines = ["# Synthetic fixture geometry only", "g synthetic_first"]
        lines.extend("v " + " ".join(f"{c:.17g}" for c in p) for p in points)
        lines += ["f 1 2 3", "g synthetic_second", "f 4 5 6"]
        self.mesh.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.reg.write_text(json.dumps(registration(self.mesh.read_bytes())),
                            encoding="utf-8")

    def test_full_retained_wgc_to_two_mesh_depths_without_movement(self):
        before = self.mesh.read_bytes()
        result = surface.pick_retained(self.obs, self.route, 160, 110, self.mesh, self.reg,
                                       selected_triangle=2)
        self.assertEqual(result["schema"], surface.SCHEMA)
        self.assertEqual(result["surface"]["selectedHit"]["triangleIndex"], 2)
        self.assertAlmostEqual(result["surface"]["selectedHit"]["distanceNative"], 18)
        self.assertEqual(result["status"], "candidate-hits")
        self.assertEqual(result["surface"]["distinctDepthGroups"], 2)
        for hit, expected in zip(result["surface"]["hits"], (12, 18)):
            self.assertAlmostEqual(hit["distanceNative"], expected, places=6)
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["surface"]["floorQualified"])
        self.assertIsNone(result["ray"]["worldSurfaceXYZ"])
        self.assertEqual(self.mesh.read_bytes(), before)

    def test_cli_json_result_and_changed_sha_blocks(self):
        argv = ["--observation", str(self.obs), "--route", str(self.route),
                "--pixel-x", "160", "--pixel-y", "110",
                "--mesh-obj", str(self.mesh), "--registration-json", str(self.reg)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(surface.main(argv), 0)
        self.assertEqual(json.loads(output.getvalue())["surface"]["hitCount"], 2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(surface.main(argv + ["--select-triangle-index", "2"]), 0)
        self.assertEqual(json.loads(output.getvalue())["surface"]["selectedHit"]["triangleIndex"], 2)
        self.mesh.write_text(self.mesh.read_text() + "# tampered\n", encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(surface.main(argv), 2)
        self.assertEqual(json.loads(output.getvalue())["reason"],
                         "registration-mesh-sha256-mismatch")


class ArchivedSourceMeshTests(unittest.TestCase):
    """Optional historical AMD replay; never contacts a current RIFT process."""

    def test_eight_saved_ground_pixels_replay_against_real_riftworld_terrain(self):
        root = Path(__file__).resolve().parents[1]
        capture = root / "artifacts/waypoint-view-a07ef160cdd34d5f9465b13e372c44fb"
        mesh = Path("C:/work/RiftWorld/artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj")
        registration_path = root / "artifacts/pixel-surface-p1-20261116/courtyard-identity-hypothesis.json"
        projection_path = capture / "projection/waypoints.json"
        sources = (capture / "observation.json", capture / "route.json", mesh,
                   registration_path, projection_path)
        if not all(path.is_file() for path in sources):
            self.skipTest("exact historical AMD-DESKTOP capture/RiftWorld OBJ not installed")
        raw = mesh.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "9638697914900f3098fbae11d3b6cabe95c663c954898fa6ca589ee759861dec")
        self.assertEqual(hashlib.sha256(projection_path.read_bytes()).hexdigest(),
                         "9fd64ba6f67d6a6d715d9101f25293dca313829b620ccd1cae9ee5debde68053")
        registration = surface.load_registration(registration_path, hashlib.sha256(raw).hexdigest())
        self.assertEqual(registration["qualification"], "candidate-only")
        vertices, faces = surface.parse_obj(raw, registration["sourceToNativeRows"])
        self.assertEqual((len(vertices), len(faces)), (198644, 227051))
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        self.assertEqual(projection["machine"], "AMD-DESKTOP")
        self.assertEqual(len(projection["points"]), 8)
        errors, rays = [], []
        for point in projection["points"]:
            with self.subTest(point=point["number"]):
                ground = point["ground"]
                self.assertEqual(ground["status"], "drawn-candidate")
                x, y = ground["pixel"]
                ray = physical_pixel_ray.pick_retained(
                    capture / "observation.json", capture / "route.json", x, y)["ray"]
                rays.append(ray)
                result = surface.intersect_prepared(vertices, faces, ray, max_distance=200)
                self.assertFalse(result["movementEligible"])
                self.assertIsNone(result["selectedHit"])
                self.assertGreaterEqual(result["distinctDepthGroups"], 2)
                nearest = result["hits"][0]
                self.assertTrue(nearest["meshGroup"].startswith("world_terrain_"))
                recorded = [ground["worldXYZ"][axis] for axis in ("x", "y", "z")]
                error = math.dist(nearest["candidateXYZ"], recorded)
                self.assertLess(error, .11)
                errors.append(error)
        self.assertAlmostEqual(min(errors), .034596216488, delta=1e-5)
        self.assertAlmostEqual(max(errors), .092417715537, delta=1e-5)
        # Negative control: flat ground yields the SAME intersection even when
        # source geometry is displaced 10 units horizontally. This cannot
        # independently establish native/source X registration or occlusion.
        shifted, shifted_faces = surface.parse_obj(
            raw, [[1, 0, 0, 10], [0, 1, 0, 0], [0, 0, 1, 0]])
        for ray, point, baseline in zip(rays, projection["points"], errors):
            with self.subTest(negative_x_control=point["number"]):
                shifted_hits = surface.intersect_prepared(
                    shifted, shifted_faces, ray, max_distance=200)["hits"]
                recorded = [point["ground"]["worldXYZ"][axis]
                            for axis in ("x", "y", "z")]
                self.assertAlmostEqual(math.dist(shifted_hits[0]["candidateXYZ"], recorded),
                                       baseline, delta=1e-7)
        raised, raised_faces = surface.parse_obj(
            raw, [[1, 0, 0, 0], [0, 1, 0, 1], [0, 0, 1, 0]])
        height_hits = surface.intersect_prepared(
            raised, raised_faces, rays[0], max_distance=200)["hits"]
        first_saved = [projection["points"][0]["ground"]["worldXYZ"][axis]
                       for axis in ("x", "y", "z")]
        self.assertGreater(math.dist(height_hits[0]["candidateXYZ"], first_saved), 1.0)


if __name__ == "__main__":
    unittest.main()
