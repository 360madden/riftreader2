"""Saved real-shape unit/frame receipts; never capture or read a process."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image

from scripts import plot_physical_units as plot
from tests import test_plot_physical_waypoints as waypoint_fixture
from tests.test_physical_unit_positions import report as unit_report, bits
from tests.test_physical_only_selection import IDENTITY


class UnitPlotTests(unittest.TestCase):
    def setUp(self):
        # Reuse the established offset-client PNG/receipt fixture, not a mocked projector.
        fixture = waypoint_fixture.PlotTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root, self.image, self.frame = fixture.root, fixture.image, fixture.frame
        self.receipt = fixture.receipt
        self.before = unit_report()
        self.after = deepcopy(self.before)
        for native, second in ((self.before, False), (self.after, True)):
            row = native["observation"]
            row["startedAtUtc"] = "2026-11-11T19:00:00.3Z" if second else "2026-11-11T18:59:59.8Z"
            row["completedAtUtc"] = "2026-11-11T19:00:00.4Z" if second else "2026-11-11T18:59:59.9Z"
            for index, unit in enumerate(row["rows"]):
                base = "2026-11-11T19:00:00." if second else "2026-11-11T18:59:59."
                tick = (31 if second else 81) + index * 2
                unit["startedAtUtc"] = base + str(tick) + "Z"
                unit["completedAtUtc"] = base + str(tick + 1) + "Z"
        def side(name):
            return dict(status="complete", workflow="physical", nativeRead="unit-positions",
                        ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY),
                        nativeOutput=str(self.root / name))
        self.bracket = dict(before=side("before.json"), after=side("after.json"),
            frame=dict(status="verified-awaiting-visual-review", workflow="physical",
                       foregroundMayChange=False, target=deepcopy(IDENTITY), image=str(self.image),
                       receipt=str(self.receipt), imageSha256=self.frame["imageSha256"]), elapsed=.6)
        self.output = self.root / "unit-output"

    def render(self, **kwargs):
        for name, value in (("before.json", self.before), ("after.json", self.after),
                            ("bracket.json", self.bracket), ("image.png.json", self.frame)):
            (self.root / name).write_text(json.dumps(value), encoding="utf-8")
        return plot.render(self.root / "bracket.json", self.output, **kwargs)

    def test_offcenter_actual_pixels_hashes_chrome_and_original(self):
        original = self.image.read_bytes()
        result = self.render()
        drawn = [row for row in result["rows"] if row["status"] == "drawn-candidate"]
        self.assertEqual(len(drawn), 1)
        self.assertEqual(drawn[0]["unitKey"], str(2**64 - 1))
        self.assertEqual(drawn[0]["worldXYZ"], dict(x=7430, y=871, z=2950))
        self.assertEqual(drawn[0]["pixel"], [127, 110])
        self.assertEqual(result["rows"][0]["reason"], "self-excluded")
        self.assertFalse(result["inputSent"])
        self.assertEqual(self.image.read_bytes(), original)
        self.assertEqual(result["sourceNativeBefore"]["sha256"],
                         hashlib.sha256((self.root / "before.json").read_bytes()).hexdigest())
        with Image.open(result["annotatedImage"]) as image:
            self.assertEqual(image.getpixel((127, 110)), (255, 204, 51))
            self.assertEqual(image.getpixel((127, 0)), (34, 34, 34))
        saved = json.loads(Path(result["report"]).read_text())
        self.assertEqual(saved["drawnCount"], 1)
        self.assertIn("stale", " ".join(saved["qualification"]))

    def test_changed_position_is_withheld_without_losing_other_evidence(self):
        row = self.after["observation"]["rows"][1]
        row["positionCandidate"]["x"] = 7431
        row["rawBits"] = bits(row["positionCandidate"])
        row["horizontalDistanceCandidate"] = 32**.5
        result = self.render()
        self.assertEqual(result["drawnCount"], 0)
        self.assertEqual(result["rows"][1]["reason"], "unit-position-changed-across-frame")

    def test_missing_unit_withheld(self):
        self.after["observation"]["rows"].pop()
        self.after["observation"]["examined"] -= 1
        result = self.render()
        self.assertEqual(result["rows"][1]["reason"], "unit-not-present-in-both-scans")

    def test_distance_limit_withholds_and_existing_output_refused(self):
        result = self.render(max_distance=4)
        self.assertEqual(result["drawnCount"], 0)
        self.assertEqual(result["rows"][1]["reason"], "outside-max-distance")
        with self.assertRaisesRegex(ValueError, "fresh-output"):
            self.render()

    def test_sorted_marker_limit(self):
        for native in (self.before, self.after):
            row = native["observation"]
            new = deepcopy(row["rows"][0])
            new.update(unitKey="43", unitIdCandidate="u000000000000002B",
                       entityAddressDecimal=str(0x20006000))
            new["startedAtUtc"] = new["completedAtUtc"] = row["rows"][-1]["completedAtUtc"]
            row["rows"].append(new)
            row["examined"] += 1
        result = self.render(limit=1)
        rows = {row["unitKey"]: row for row in result["rows"]}
        self.assertEqual(rows["43"]["number"], 1)
        self.assertEqual(rows["43"]["pixel"], [160, 110])
        self.assertEqual(rows[str(2**64 - 1)]["reason"], "marker-limit")

    def test_changed_camera_rejected_even_when_each_scan_internally_stable(self):
        for name in ("opticalCameraCandidate", "opticalCameraAfterCandidate"):
            self.after["observation"][name]["cameraAddressDecimal"] = "2096815868168"
        with self.assertRaisesRegex(ValueError, "camera-bracket-changed"):
            self.render()
        self.assertFalse(self.output.exists())

    def test_bad_position_bits_rejected(self):
        self.after["observation"]["rows"][1]["rawBits"] = [0, 0, 0]
        with self.assertRaises(ValueError):
            self.render()
        self.assertFalse(self.output.exists())

    def test_changed_self_key_rejected(self):
        self.after["observation"]["selfKey"] = "41"
        with self.assertRaisesRegex(ValueError, "self-bracket-changed"):
            self.render()
        self.assertFalse(self.output.exists())

    def test_identity_and_host_changes_rejected(self):
        for key, value in (("processId", 999), ("processStartUtcTicks", "2"),
                           ("executableSha256", "b"*64), ("hwnd", 999),
                           ("hostName", "LEGION")):
            with self.subTest(key=key):
                self.bracket["after"]["target"] = dict(IDENTITY, **{key: value})
                with self.assertRaises(ValueError):
                    self.render()
                self.assertFalse(self.output.exists())

    def test_image_tampering_rejected_and_original_left_alone(self):
        Image.new("RGB", (320, 200), "red").save(self.image)
        original = self.image.read_bytes()
        with self.assertRaisesRegex(ValueError, "image-hash-or-size"):
            self.render()
        self.assertEqual(original, self.image.read_bytes())
        self.assertFalse(self.output.exists())

    def test_acquisition_order_and_long_bracket_rejected(self):
        original = deepcopy(self.after)
        self.after["observation"]["startedAtUtc"] = "2026-11-11T18:59:59.95Z"
        with self.assertRaises(ValueError):
            self.render()
        self.after = original
        row = self.before["observation"]
        row["startedAtUtc"] = "2026-11-11T18:59:54Z"
        with self.assertRaisesRegex(ValueError, "bracket-too-long"):
            self.render()
        self.assertFalse(self.output.exists())

    def test_options_rejected_before_output(self):
        for kwargs in (dict(limit=0), dict(limit=41), dict(limit=True),
                       dict(max_distance=0), dict(max_distance=101), dict(max_distance=float("nan"))):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.render(**kwargs)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
