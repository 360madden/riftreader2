"""Exact historical three-landmark WGC/OBJ validation and refusal regressions."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_pixel_landmarks as landmarks
from scripts import physical_pixel_ray, physical_pixel_surface


ROOT = Path(r"C:\work\RiftWorld\artifacts\thedeor-20261113-r4")
MESH_SHA = "9638697914900f3098fbae11d3b6cabe95c663c954898fa6ca589ee759861dec"
LANDMARK_SHA = "61d81c7649674b80c5855975f2f235d124fde699552665e13998a45c8a73348e"
OBS_SHA = "666f650f3e11fff325acaab56413203b1966274d7af7776c1a3755197ca68601"
BEFORE_SHA = "00a2c4e060dba5f4f767b6e7d2a8432f4fda1cf32599a31b6021c82bc3e0348d"
AFTER_SHA = "d6effc47840c64610c7dd2b1e754d0ba13b794310c2a5fb67b25032e84c479ff"
PINS = {
    "mesh": MESH_SHA, "landmarks": LANDMARK_SHA,
    "observation": OBS_SHA, "before": BEFORE_SHA, "after": AFTER_SHA,
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@unittest.skipUnless(
    all((ROOT / name).is_file() for name in (
        "landmarks.json", "observation-final.json", "native-final-before.json",
        "native-final-after.json", "riftworld-patch.obj")),
    "historical AMD-DESKTOP RIFT alignment archive unavailable",
)
class ArchivedLandmarkProofTests(unittest.TestCase):
    def run_fixture(self, directory, pins=None):
        if pins is None:
            pins = {key: digest(Path(directory) / filename) for key, filename in (
                ("landmarks", "landmarks.json"),
                ("observation", "observation-final.json"),
                ("before", "native-final-before.json"),
                ("after", "native-final-after.json"))}
            pins["mesh"] = MESH_SHA
        return landmarks.replay(directory, ROOT / "riftworld-patch.obj", pins=pins)

    def copy_small_sources(self):
        temp = TemporaryDirectory(prefix="rr2-landmark-proof-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name in ("landmarks.json", "observation-final.json",
                     "native-final-before.json", "native-final-after.json"):
            shutil.copy2(ROOT / name, root / name)
        return root

    @staticmethod
    def mutate(path, action):
        data = json.loads(path.read_text(encoding="utf-8"))
        action(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_three_exact_obj_vertices_and_negative_controls(self):
        result = self.run_fixture(ROOT, PINS)
        self.assertEqual(result["status"], "historical-landmark-frame-alignment-candidate")
        self.assertEqual(result["landmarkCount"], 3)
        self.assertTrue(result["reprojectionInsideManualUncertainty"])
        self.assertTrue(result["translationNegativeControlsRejected"])
        self.assertEqual(result["modelTriangleCount"], 227051)
        self.assertLess(result["bracketSeconds"], 3)
        self.assertEqual(result["identity"]["processId"], 34468)
        errors = [x["pixelResidual"] for x in result["landmarks"]]
        misses = [x["rayMissDistanceNative"] for x in result["landmarks"]]
        self.assertAlmostEqual(min(errors), 1.534018473, delta=1e-5)
        self.assertAlmostEqual(max(errors), 2.921243516, delta=1e-5)
        self.assertAlmostEqual(min(misses), .040095639, delta=1e-6)
        self.assertAlmostEqual(max(misses), .081042719, delta=1e-6)
        self.assertTrue(all(
            all(shift > 30 for shift in row["shiftResidualPixels"].values())
            for row in result["landmarks"]))
        self.assertFalse(result["allSourceMeshRegistered"])
        self.assertFalse(result["independentDepthQualified"])
        self.assertFalse(result["occlusionQualified"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["inputSent"])

    def test_cli_outputs_schema_and_does_not_send_game_input(self):
        argv = [
            "--archive-dir", str(ROOT), "--mesh-obj", str(ROOT/"riftworld-patch.obj"),
            "--mesh-sha256", MESH_SHA, "--landmarks-sha256", LANDMARK_SHA,
            "--observation-sha256", OBS_SHA, "--native-before-sha256", BEFORE_SHA,
            "--native-after-sha256", AFTER_SHA,
        ]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = landmarks.main(argv)
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(parsed["schema"], landmarks.SCHEMA)
        self.assertEqual(parsed["landmarkCount"], 3)
        self.assertFalse(parsed["movementEligible"])
        argv[argv.index("--mesh-sha256") + 1] = "0" * 64
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = landmarks.main(argv)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["reason"],
                         "landmark-mesh-sha256-mismatch")

    def test_mutated_source_vertex_refuses_even_with_new_report_hash(self):
        folder = self.copy_small_sources()
        lm = folder / "landmarks.json"
        self.mutate(lm, lambda data: data[0]["sourceXYZ"].__setitem__(
            0, data[0]["sourceXYZ"][0] + .25))
        with self.assertRaisesRegex(ValueError, "landmark-not-an-exact-referenced"):
            self.run_fixture(folder)

    def test_manually_moved_pixel_becomes_inconclusive(self):
        folder = self.copy_small_sources()
        self.mutate(folder / "landmarks.json",
                    lambda data: data[1]["frameXY"].__setitem__(
                        0, data[1]["frameXY"][0] + 100))
        result = self.run_fixture(folder)
        self.assertEqual(result["status"], "inconclusive")
        self.assertFalse(result["reprojectionInsideManualUncertainty"])

    def test_thin_wall_exact_pixel_misses_but_two_pixel_neighbor_hits(self):
        # A 1.55-pixel manual corner mismatch is enough for a narrow wall
        # silhouette to fall behind the first-hit terrain ray at the mark.
        # Never auto-promote the terrain as the visibly selected wall surface.
        obs = json.loads((ROOT / "observation-final.json").read_text())
        camera = json.loads((ROOT / "native-final-after.json").read_text())[
            "observation"]["opticalCameraCandidate"]
        target = json.loads((ROOT / "landmarks.json").read_text())[1]["sourceXYZ"]
        raw = (ROOT / "riftworld-patch.obj").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), MESH_SHA)
        vertices, faces = physical_pixel_surface.parse_obj(
            raw, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]])
        def first_hits(x, y):
            ray = physical_pixel_ray.pixel_ray(camera, obs["clientFrameMapping"], x, y)
            return physical_pixel_surface.intersect_prepared(
                vertices, faces, ray, max_distance=42)
        exact = first_hits(1115, 286)
        nearby = first_hits(1113, 286)
        self.assertTrue(exact["hits"][0]["meshGroup"].startswith("world_terrain_"))
        self.assertTrue(nearby["hits"][0]["meshGroup"].startswith(
            "A_F_terrace_wall_curved_02"))
        wall_hits = [hit for hit in nearby["hits"]
                     if hit["meshGroup"].startswith("A_F_terrace_wall_curved_02")]
        self.assertEqual(len(wall_hits), 2)
        self.assertLess(min(sum((a-b)**2 for a, b in zip(hit["candidateXYZ"], target))**.5
                            for hit in wall_hits), .01)
        self.assertFalse(exact["movementEligible"])
        self.assertFalse(nearby["movementEligible"])
        center_ray = physical_pixel_ray.pixel_ray(
            camera, obs["clientFrameMapping"], 1115, 286)
        footprint = physical_pixel_surface.sample_pixel_footprint(
            vertices, faces, camera, obs["clientFrameMapping"], 1115, 286, 2,
            center_ray=center_ray, center_surface=exact, max_distance=42)
        self.assertEqual(footprint["sampleCount"], 9)
        self.assertTrue(footprint["ambiguousFirstSurface"])
        self.assertEqual(footprint["samples"][0]["firstMeshGroup"],
                         exact["hits"][0]["meshGroup"])
        left = next(row for row in footprint["samples"]
                    if row["offsetPixels"] == [-2, 0])
        self.assertTrue(left["firstMeshGroup"].startswith(
            "A_F_terrace_wall_curved_02"))
        self.assertFalse(footprint["movementEligible"])

    def test_changed_native_camera_across_wgc_bracket_refuses(self):
        folder = self.copy_small_sources()
        before = folder / "native-final-before.json"
        self.mutate(before, lambda data: data["observation"][
            "opticalCameraCandidate"]["worldEyeXYZ"].__setitem__(
                0, data["observation"]["opticalCameraCandidate"]["worldEyeXYZ"][0] + 1))
        self.mutate(folder / "observation-final.json",
                    lambda data: data["nativeFacing"].update(beforeOutput=str(before)))
        with self.assertRaisesRegex(ValueError, "landmark-camera-changed"):
            self.run_fixture(folder)

    def test_process_epoch_mismatch_refuses(self):
        folder = self.copy_small_sources()
        self.mutate(folder / "observation-final.json",
                    lambda data: data["target"].update(processId=99999))
        with self.assertRaisesRegex(ValueError, "landmark-native-process-epoch-mismatch"):
            self.run_fixture(folder)

    def test_wgc_receipt_claiming_input_refuses(self):
        folder = self.copy_small_sources()
        original = json.loads((ROOT / "observation-final.json").read_text())
        receipt = folder / "receipt-changed.json"
        receipt.write_text(Path(original["receipt"]).read_text(), encoding="utf-8")
        self.mutate(receipt, lambda data: data.update(inputSent=True))
        self.mutate(folder / "observation-final.json",
                    lambda data: data.update(receipt=str(receipt)))
        with self.assertRaisesRegex(ValueError, "landmark-wgc-receipt-unqualified"):
            self.run_fixture(folder)

    def test_mutated_archived_native_file_fails_original_pinned_link(self):
        folder = self.copy_small_sources()
        self.mutate(folder / "native-final-after.json",
                    lambda data: data["observation"].update(
                        qualification="not-original"))
        with self.assertRaisesRegex(ValueError, "after-original-sha256-mismatch"):
            self.run_fixture(folder)


if __name__ == "__main__":
    unittest.main()
