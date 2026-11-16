"""Offline screenshot-pixel to native camera viewing ray, never a world-surface pick.

Requires an already validated WGC + native-facing bracket and matching saved
route for the CLI. Pixels are integer indices, sampled at pixel centers.
No game reads, movement, terrain guesses, focus changes, or input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import export_physical_rerun as rerun


SCHEMA = "rr2.retained-frame-pixel-ray/1"


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pixel_ray(camera, mapping, x, y):
    """Invert one validated native screen projection, without assuming scene depth."""
    _require(type(x) is int and type(y) is int, "pixel-coordinates-must-be-integers")
    fields = ("frameWidth", "frameHeight", "clientLeft", "clientTop",
              "clientWidth", "clientHeight")
    _require(isinstance(mapping, dict) and mapping.get("status") == "available-candidate"
             and all(type(mapping.get(key)) is int for key in fields),
             "validated-client-frame-mapping-required")
    width, height = mapping["frameWidth"], mapping["frameHeight"]
    left, top, cw, ch = (mapping[key] for key in fields[2:])
    _require(0 < width <= 4096 and 0 < height <= 2160 and 0 <= left < width
             and 0 <= top < height and 0 < cw <= width - left and 0 < ch <= height - top,
             "invalid-client-frame-bounds")
    _require(left <= x < left + cw and top <= y < top + ch,
             "pixel-outside-captured-client")
    rays = rerun.native_view_rays(camera)
    _require(rays["status"] == "available-candidate",
             "native-view-rays-unavailable: " + rays.get("reason", "unknown"))
    nx, ny = (x + .5 - left) / cw, (y + .5 - top) / ch
    bounds = rays["viewportRectNormalized"]
    _require(isinstance(bounds, list) and len(bounds) == 4
             and all(type(n) in (int, float) and math.isfinite(n) for n in bounds)
             and 0 <= bounds[0] < bounds[2] <= 1
             and 0 <= bounds[1] < bounds[3] <= 1,
             "native-view-viewport-invalid")
    vx0, vy0, vx1, vy1 = bounds
    _require(vx0 <= nx <= vx1 and vy0 <= ny <= vy1,
             "pixel-outside-native-camera-viewport")
    u, v = (nx - vx0) / (vx1 - vx0), (ny - vy0) / (vy1 - vy0)
    weights = ((1-u)*(1-v), u*(1-v), u*v, (1-u)*v)
    corners = rays["cornersXYZ"]  # TL, TR, BR, BL on one arbitrary clip-W plane.
    point = [sum(w * corner[axis] for w, corner in zip(weights, corners))
             for axis in range(3)]
    eye = rays["nativeEyeXYZ"]
    delta = [point[axis] - eye[axis] for axis in range(3)]
    distance = math.hypot(*delta)
    _require(math.isfinite(distance) and distance > 1e-9, "degenerate-native-view-ray")
    projected = rerun.plot.physical._project_world_point(
        camera, dict(zip(("x", "y", "z"), point)))
    extent = rays["clipWDisplayExtent"]
    _require(projected.get("status") == "available-candidate"
             and abs(projected["normalizedX"] - nx) <= 1e-8
             and abs(projected["normalizedY"] - ny) <= 1e-8
             and abs(projected["clipW"] - extent) <= 1e-5,
             "pixel-ray-forward-projection-mismatch")
    return {"status": "available-candidate", "framePixel": [x, y],
            "framePixelCenter": [x + .5, y + .5],
            "normalizedClientXY": [nx, ny], "viewportUV": [u, v],
            "nativeEyeXYZ": eye, "unitDirectionXYZ": [axis / distance for axis in delta],
            "displayPlanePointXYZ": point, "clipWDisplayExtent": extent,
            "inverseConditionNumber": rays["inverseConditionNumber"],
            "forwardReprojectionErrorPixels": [
                abs(projected["normalizedX"] - nx) * cw,
                abs(projected["normalizedY"] - ny) * ch],
            "worldSurfaceXYZ": None, "movementEligible": False,
            "qualification": "candidate viewing ray only; no depth, geometry intersection, "
                             "terrain floor, occlusion, world-instance or route clearance proof"}


def pick_retained(observation, route, x, y):
    """Reuse existing complete same-host saved-route/WGC/native bracket admission."""
    observation, route = Path(observation).resolve(), Path(route).resolve()
    with TemporaryDirectory(prefix="rr2-pixel-ray-") as scratch:
        _, frames = rerun.prepare(route, [observation], scratch, images=False)
        _require(len(frames) == 1 and not frames[0]["desktop"],
                 "exact-physical-wgc-frame-required")
        frame = frames[0]
        before, after = frame["native"]
        report_path = Path(after["source"])
        raw = report_path.read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == after["sha256"],
                 "native-after-source-changed")
        camera = rerun.plot._read(report_path)["observation"].get("opticalCameraCandidate")
        ray = pixel_ray(camera, frame["projection"]["clientFrameMapping"], x, y)
        _require(hashlib.sha256(observation.read_bytes()).hexdigest() == frame["sourceSha256"]
                 and hashlib.sha256(route.read_bytes()).hexdigest()
                     == frame["projection"]["routeSha256"]
                 and hashlib.sha256(Path(before["source"]).read_bytes()).hexdigest()
                     == before["sha256"], "retained-projection-source-changed")
        return {"schema": SCHEMA, "status": "available-candidate",
                "source": {"observation": str(observation), "sha256": frame["sourceSha256"],
                           "route": str(route), "routeSha256": frame["projection"]["routeSha256"],
                           "nativeBeforeSha256": before["sha256"],
                           "nativeAfterSha256": after["sha256"],
                           "imageSha256": frame["projection"]["imageSha256"],
                           "receiptSha256": frame["projection"]["receiptSha256"]},
                "identity": frame["projection"]["identity"],
                "capturedAtUtc": frame["projection"]["capturedAtUtc"],
                "ray": ray, "inputSent": False, "movementEligible": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True, help="retained physical WGC bracket")
    parser.add_argument("--route", type=Path, required=True, help="matching saved native route")
    parser.add_argument("--pixel-x", type=int, required=True, help="zero-based screenshot column")
    parser.add_argument("--pixel-y", type=int, required=True, help="zero-based screenshot row")
    args = parser.parse_args(argv)
    try:
        result = pick_retained(args.observation, args.route, args.pixel_x, args.pixel_y)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "reason": str(error),
                          "inputSent": False, "movementEligible": False}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
