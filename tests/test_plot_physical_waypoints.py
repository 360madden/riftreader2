"""Synthetic saved-snapshot checks; no process, capture or input calls."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from scripts import plot_physical_waypoints as plot
from tests.test_physical_facing import report, optical_camera
from tests.test_physical_only_selection import IDENTITY
from tests.test_physical_turn_visual_pair import make_receipt


class PlotTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(plot.socket, "gethostname", return_value="AMD-DESKTOP").start()
        self.image = self.root / "image.png"
        Image.new("RGB", (320, 200), "#222222").save(self.image)
        self.receipt = self.root / "image.png.json"
        frame = make_receipt(self.receipt, self.image, 0)
        native = report()
        # Use a single sample for each side of the retained image.
        native["observations"] = [native["observation"]]
        native["requestedSamples"] = native["completedSamples"] = 1
        row = native["observation"]
        row["startedAtUtc"] = "2026-11-11T18:59:59.8Z"
        row["completedAtUtc"] = "2026-11-11T18:59:59.9Z"
        row["opticalCameraCandidate"] = optical_camera()
        row["opticalCameraAfterTargetCandidate"] = optical_camera()
        row["targetProjectionCameraStableCandidate"] = True
        row["targetPositionPairCandidate"] = dict(identity=row["identity"],
            startedAtUtc="2026-11-11T18:59:59.81Z", completedAtUtc="2026-11-11T18:59:59.82Z",
            self=dict(unitKey=row["playerKeyDecimal"], position=row["positionCandidate"]),
            target=None, beforeGuardStatus="fallback-key-candidate", afterGuardStatus="fallback-key-candidate",
            targetStatus="unavailable", acquisitionSpanMilliseconds=10)
        self.before = native
        self.after = deepcopy(native)
        self.after["observation"]["startedAtUtc"] = "2026-11-11T19:00:00.3Z"
        self.after["observation"]["completedAtUtc"] = "2026-11-11T19:00:00.4Z"
        self.after["observation"]["targetPositionPairCandidate"].update(
            startedAtUtc="2026-11-11T19:00:00.31Z", completedAtUtc="2026-11-11T19:00:00.32Z")
        geo = dict(coordinateSpace="physical-screen-pixels", visibleFrameLeft=100,
                   visibleFrameTop=100, visibleFrameRight=420, visibleFrameBottom=300,
                   clientScreenLeft=105, clientScreenTop=125, clientWidth=310, clientHeight=170)
        for target in (frame["targetBefore"], frame["targetAfter"]):
            target.update(pid=IDENTITY["processId"], startTicks=int(IDENTITY["processStartUtcTicks"]),
                          sha256=IDENTITY["executableSha256"], hwnd=IDENTITY["hwnd"],
                          width=310, height=170, windowGeometry=geo)
        frame["capturedCompletedAtUtc"] = "2026-11-11T19:00:00.25Z"
        frame["clientFrameMapping"] = dict(status="available-candidate", unavailableReason=None,
            coordinateSpace="top-left-frame-physical-pixels", basis="matching-dwm-visible-frame-size",
            frameWidth=320, frameHeight=200, clientLeft=5, clientTop=25, clientWidth=310, clientHeight=170)
        self.frame = frame
        self.observation = dict(status="verified-awaiting-visual-review", workflow="physical",
            ownerHost="AMD-DESKTOP", target=IDENTITY, image=str(self.image), receipt=str(self.receipt),
            imageSha256=frame["imageSha256"], nativeFacing=dict(status="stable-bracket-candidate",
                beforeOutput=str(self.root / "before.json"), afterOutput=str(self.root / "after.json")))
        self.route = dict(waypoints=[["Center", 7427, 2946], ["Behind", 7427, 2930], ["Outside", 7500, 2946]],
            heights=[871, 871, 871], recording=dict(version=1, complete=True,
                identity=dict(mode="reused-seed", runtimeIdentity=dict(machine="AMD-DESKTOP",
                    gameBuildSha256=IDENTITY["executableSha256"], unitKey=row["playerKeyDecimal"], processId=999))))
        self.output = self.root / "output"

    def run_render(self):
        for name, data in (("before.json", self.before), ("after.json", self.after),
                           ("observation.json", self.observation), ("route.json", self.route),
                           ("image.png.json", self.frame)):
            (self.root / name).write_text(json.dumps(data), encoding="utf-8")
        return plot.render(self.root / "observation.json", self.root / "route.json", self.output)

    def test_actual_placement_uses_client_offset_and_preserves_original(self):
        original = self.image.read_bytes()
        result = self.run_render()
        self.assertEqual(result["points"][0]["ground"]["pixel"], [160, 110])
        self.assertTrue(result["points"][0]["beaconLineDrawn"])
        self.assertEqual(result["points"][1]["ground"]["reason"], "nonpositive-or-small-clip-w")
        self.assertEqual(result["points"][2]["ground"]["reason"], "outside-client-or-viewport")
        self.assertEqual(result["recordingIdentity"]["runtimeIdentity"]["processId"], 999)
        self.assertIn("world/zone", " ".join(result["limitations"]))
        self.assertEqual(original, self.image.read_bytes())
        with Image.open(result["annotatedImage"]) as image:
            self.assertEqual(image.getpixel((160, 110)), (255, 204, 51))
            self.assertEqual(image.getpixel((160, 0)), (34, 34, 34))
        self.assertEqual(json.loads(Path(result["report"]).read_text())["playerGround"]["worldXYZ"],
                         plot.physical._native_values("facing", self.after)["positionXYZCandidate"])

    def test_missing_or_nonfinite_height_rejected_without_output(self):
        for height in (None, float("nan"), True):
            with self.subTest(height=height):
                self.route["heights"][0] = height
                with self.assertRaises(ValueError):
                    self.run_render()
                self.assertFalse(self.output.exists())

    def test_route_identity_mismatch_rejected_without_output(self):
        original = deepcopy(self.route["recording"]["identity"]["runtimeIdentity"])
        for key in ("machine", "gameBuildSha256", "unitKey"):
            with self.subTest(key=key):
                self.route["recording"]["identity"]["runtimeIdentity"] = dict(original, **{key: "wrong"})
                with self.assertRaisesRegex(ValueError, "route-host-build-player"):
                    self.run_render()
                self.assertFalse(self.output.exists())

    def test_unstable_or_stale_bracket_rejected_without_output(self):
        self.observation["nativeFacing"]["status"] = "unavailable"
        with self.assertRaisesRegex(ValueError, "stable-native-frame"):
            self.run_render()
        self.assertFalse(self.output.exists())
        self.observation["nativeFacing"]["status"] = "stable-bracket-candidate"
        self.after["observation"]["startedAtUtc"] = "2026-11-11T18:59:59.95Z"
        with self.assertRaisesRegex(ValueError, "acquisition-order"):
            self.run_render()
        self.assertFalse(self.output.exists())

    def test_missing_mapping_or_projection_refused(self):
        mapping = self.frame.pop("clientFrameMapping")
        with self.assertRaisesRegex(ValueError, "available-client-frame"):
            self.run_render()
        self.assertFalse(self.output.exists())
        self.frame["clientFrameMapping"] = mapping
        for native in (self.before, self.after):
            for name in ("opticalCameraCandidate", "opticalCameraAfterTargetCandidate"):
                for field in ("projectionRowMajor", "viewportLeftRightTopBottom", "projectionRawBits"):
                    native["observation"][name].pop(field)
        with self.assertRaises(ValueError):
            self.run_render()
        self.assertFalse(self.output.exists())

    def test_frame_identity_and_long_bracket_refused(self):
        self.observation["target"] = dict(IDENTITY, processId=999)
        with self.assertRaisesRegex(ValueError, "native-frame-identity"):
            self.run_render()
        self.assertFalse(self.output.exists())
        self.observation["target"] = IDENTITY
        row = self.after["observation"]
        row["startedAtUtc"] = "2026-11-11T19:00:10.3Z"
        row["completedAtUtc"] = "2026-11-11T19:00:10.4Z"
        row["targetPositionPairCandidate"].update(startedAtUtc="2026-11-11T19:00:10.31Z",
                                               completedAtUtc="2026-11-11T19:00:10.32Z")
        with self.assertRaisesRegex(ValueError, "bracket-too-long"):
            self.run_render()
        self.assertFalse(self.output.exists())

    def test_changed_camera_and_tampered_image_refused(self):
        self.after["observation"]["opticalCameraCandidate"] = None
        with self.assertRaises(ValueError):
            self.run_render()
        self.assertFalse(self.output.exists())
        self.after["observation"]["opticalCameraCandidate"] = optical_camera()
        Image.new("RGB", (320, 200), "red").save(self.image)
        with self.assertRaisesRegex(ValueError, "image-hash-or-size"):
            self.run_render()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
