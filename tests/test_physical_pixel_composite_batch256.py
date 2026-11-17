"""Opt-in offline 64/256-pixel CLI batches over two immutable native/WGC captures.

The accepted intersections are render-mesh candidates only, never optical
visibility, physical blocking, walkability, navigation, or movement permission.
No live process access or game input is performed.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

from scripts import physical_pixel_composite as composite
from scripts import physical_pixel_mesh_accel as mesh_accel
from scripts import physical_pixel_ray

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = Path("C:/work/RiftWorld/artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj")
REGISTRATION = ROOT / "artifacts/pixel-surface-p1-20261116/courtyard-identity-hypothesis.json"
TEMPLE_ROOT = Path(
    "C:/work/RiftWorld/artifacts/p0-watch-temple-source-render-20261116-agent-iso-r1")
TEMPLE = TEMPLE_ROOT / "geometry.obj"
ANCHOR = TEMPLE_ROOT / "atank-source-floor-anchor-exact-r2.json"
ANCHOR_SHA = "6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525"

VIEWS = {
    "first": {
        "image": ROOT / "artifacts/observe-wgc-27d58645e80e4880aa48faacb04ff743/image.png",
        "image_sha": "bf3d8d71703c9032cad3c507bf97d2e15f1cb669d3458939e0806158458382b6",
        "receipt_sha": "d4fafc4bb56a365b6a41cf76229e7cbbf2a9bb03867c558ca8601c06e977b4d6",
        "before": ROOT / "artifacts/physical-native-facing-bf8006fadcf04512a338a90ef534976e.json",
        "before_sha": "609037b2a0058a4ea7f16e2d0cbb1faae630c5cea4fad125a4603d0fb5c24ae7",
        "after": ROOT / "artifacts/physical-native-facing-24b80f583f3a49778dacf9b8337862aa.json",
        "after_sha": "88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f",
        "bounds": (500, 2400, 370, 1120),
        "counts64": {"terrain": 21, "temple-render": 32, "no-candidate": 11},
    },
    "second": {
        "image": ROOT / "artifacts/observe-wgc-f37599014aaa422a94682503abb6d532/image.png",
        "image_sha": "5f09703eca7639f583e68bd40aea19d36d20483e3752ae743b776c90133c4c75",
        "receipt_sha": "414b10c7d78be9d397d460f4eb2e7296144e574486ac491fa30ca6ec3eb168f9",
        "before": ROOT / "artifacts/physical-native-facing-82c8b813f64e4b46903f11d267dd4cc4.json",
        "before_sha": "d7a9f90fcaee7a18005dc2827faab1727a0ff93a6bde4b7e64e60be1074b8905",
        "after": ROOT / "artifacts/physical-native-facing-dc22ffd6bcbe4518a167539b62f364a7.json",
        "after_sha": "89dad03250c429cbe2a28e8261a84f1324df76b49ab94fc2503fed0a851b8f03",
        "bounds": (700, 2250, 360, 1100),
        "counts256": {"terrain": 104, "temple-render": 152, "no-candidate": 0},
    },
}


def grid(view, count):
    x0, x1, y0, y1 = VIEWS[view]["bounds"]
    xs = [round(x0 + (x1 - x0) * i / 15) for i in range(16)]
    ys = [round(y0 + (y1 - y0) * j / 15) for j in range(16)]
    if count == 64:
        return [(xs[i], ys[j]) for j in range(0, 16, 2)
                for i in range(0, 16, 2)]
    if count == 256:
        return [(xs[i], ys[j]) for j in range(16) for i in range(16)]
    raise ValueError("test-pixel-count-invalid")


def pinned_args(view, points, budget):
    entry = VIEWS[view]
    image = entry["image"]
    args = [
        "--image", str(image),
        "--receipt", str(image.with_name("image.png.json")),
        "--receipt-sha256", entry["receipt_sha"],
        "--native-before", str(entry["before"]),
        "--native-before-sha256", entry["before_sha"],
        "--native-after", str(entry["after"]),
        "--native-after-sha256", entry["after_sha"],
        "--expected-host", "AMD-DESKTOP",
        "--terrain-obj", str(TERRAIN),
        "--terrain-registration", str(REGISTRATION),
        "--temple-obj", str(TEMPLE),
        "--temple-anchor", str(ANCHOR),
        "--temple-anchor-sha256", ANCHOR_SHA,
        "--accel", "bvh",
        "--max-pixels", str(budget),
    ]
    for x, y in points:
        args.extend(("--pixel", str(x), str(y)))
    return args


class BatchBudgetTests(unittest.TestCase):
    """Reject invalid batches before touching any frame or mesh source."""

    def test_library_default_remains_32_and_large_batch_requires_bvh(self):
        for count, cap, mode, reason in (
            (33, 32, "bvh", "pixel-count-invalid"),
            (64, 64, "off", "composite-large-batch-requires-bvh"),
            (1, 257, "bvh", "composite-max-pixels-invalid"),
            (1, 31, "bvh", "composite-max-pixels-invalid"),
            (257, 256, "bvh", "pixel-count-invalid"),
        ):
            with self.subTest(count=count, cap=cap, mode=mode):
                with self.assertRaisesRegex(ValueError, reason):
                    composite.analyze_pixels({}, [], [(i, 50) for i in range(count)],
                                             accel_mode=mode, max_pixels=cap)

    def test_cli_budget_gate_precedes_source_io(self):
        args = pinned_args("first", [(i, 50) for i in range(64)], 64)
        args[args.index("--accel") + 1] = "off"
        output = StringIO()
        with mock.patch.object(composite, "load_frame",
                               side_effect=AssertionError("unexpected-source-access")):
            with redirect_stdout(output):
                exit_code = composite.main(args)
        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "composite-large-batch-requires-bvh")
        self.assertFalse(report["inputSent"])
        self.assertFalse(report["movementEligible"])


class PinnedBatchCliTests(unittest.TestCase):
    """True subprocess CLI acceptance with a separately validated camera per view."""

    @classmethod
    def setUpClass(cls):
        required = [TERRAIN, REGISTRATION, TEMPLE, ANCHOR]
        for view in VIEWS.values():
            required.extend((view["image"], view["image"].with_name("image.png.json"),
                             view["before"], view["after"]))
        if not all(path.is_file() for path in required):
            raise unittest.SkipTest("SHA-pinned historical AMD-DESKTOP evidence unavailable")
        for name, view in VIEWS.items():
            for path, expected in (
                (view["image"], view["image_sha"]),
                (view["image"].with_name("image.png.json"), view["receipt_sha"]),
                (view["before"], view["before_sha"]),
                (view["after"], view["after_sha"]),
                (ANCHOR, ANCHOR_SHA),
            ):
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != expected:
                    raise AssertionError(f"{name} source SHA changed: {path}")
        cls.frames = {}
        for name, view in VIEWS.items():
            cls.frames[name] = composite.load_frame(
                view["image"], view["image"].with_name("image.png.json"),
                view["receipt_sha"], view["before"], view["before_sha"],
                view["after"], view["after_sha"], expected_host="AMD-DESKTOP")
            if cls.frames[name]["identity"]["pid"] != 77704:
                raise AssertionError("pinned PID changed")
        cls.layers = [
            composite.load_terrain(TERRAIN, REGISTRATION),
            composite.load_temple(TEMPLE, ANCHOR, ANCHOR_SHA,
                                  cls.frames["first"]["identity"]),
        ]
        cls.indices = [mesh_accel.prepare(layer["vertices"], layer["faces"])
                       for layer in cls.layers]

    def _check_cli(self, view, count):
        points = grid(view, count)
        cmd = [sys.executable, "-m", "scripts.physical_pixel_composite",
               *pinned_args(view, points, count)]
        started = time.perf_counter()
        run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                             timeout=30, check=False)
        wall = time.perf_counter() - started
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout[-1200:])
        report = json.loads(run.stdout)
        self.assertEqual(report["status"], "candidate-only")
        self.assertEqual(len(report["pixels"]), count)
        self.assertEqual(report["identity"], self.frames[view]["identity"])
        self.assertEqual(report["source"], self.frames[view]["source"])
        self.assertEqual(report["sceneLayers"], [
            {"name": layer["name"], **layer["source"]} for layer in self.layers])
        for flag in ("inputSent", "movementEligible", "visibleSurfaceQualified",
                     "physicalBlockingQualified", "navigationQualified"):
            self.assertFalse(report[flag], flag)

        counts = {"terrain": 0, "temple-render": 0, "no-candidate": 0}
        for point, actual in zip(points, report["pixels"]):
            ray = physical_pixel_ray.pixel_ray(self.frames[view]["camera"],
                                              self.frames[view]["mapping"], *point)
            expected = composite.compare_layers(ray, self.layers, 200,
                                                indices=self.indices)
            self.assertEqual(actual, {
                "pixel": list(point),
                "rayForwardReprojectionErrorPixels":
                    ray["forwardReprojectionErrorPixels"],
                "surfaceCandidates": expected,
            })
            self.assertFalse(expected["visibleSurfaceQualified"])
            self.assertFalse(expected["movementEligible"])
            candidate = expected["candidateFirst"]
            counts[candidate["layer"] if candidate else "no-candidate"] += 1
        expected_counts = VIEWS[view]["counts" + str(count)]
        self.assertEqual(counts, expected_counts)
        print(f"PINNED_BATCH_CLI {view} {count} pixels {wall:.3f}s "
              f"counts={json.dumps(counts, sort_keys=True)}")

    def test_first_view_64(self):
        self._check_cli("first", 64)

    def test_second_view_256(self):
        self._check_cli("second", 256)


if __name__ == "__main__":
    unittest.main()
