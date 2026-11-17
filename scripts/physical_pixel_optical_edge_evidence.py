"""Pinned offline RIFT screenshot brightness-edge vs source-render ray candidate checks.

This measures *bright interior onset*, not a segmentation of the outer silhouette.
It never reads live RIFT, sends input, or qualifies optical depth/physics/nav.
The four manually selected rows are visible temple ROIs in two retained frames.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_pixel_composite as composite
from scripts import physical_pixel_mesh_accel as accel
from scripts import physical_pixel_ray

TEMPLE_ROOT = Path(
    "C:/work/RiftWorld/artifacts/p0-watch-temple-source-render-20261116-agent-iso-r1")
TERRAIN = Path(
    "C:/work/RiftWorld/artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj")
TERRAIN_REG = ROOT / "artifacts/pixel-surface-p1-20261116/courtyard-identity-hypothesis.json"
TEMPLE_ANCHOR_SHA = "6be1402cb71e1f5ddae18cc8634aa5d479e414afdda640757d879aea5380a525"
SCHEMA = "rr2.retained-wgc-bright-interior-edge-evidence/1"

# The background/interior windows and UI masks were selected by manual inspection
# of these exact PNGs. They are not algorithmically identified ground truth.
VIEWS = {
    "first": {
        "capture": "observe-wgc-27d58645e80e4880aa48faacb04ff743",
        "imageSha": "bf3d8d71703c9032cad3c507bf97d2e15f1cb669d3458939e0806158458382b6",
        "receiptSha": "d4fafc4bb56a365b6a41cf76229e7cbbf2a9bb03867c558ca8601c06e977b4d6",
        "before": "physical-native-facing-bf8006fadcf04512a338a90ef534976e.json",
        "beforeSha": "609037b2a0058a4ea7f16e2d0cbb1faae630c5cea4fad125a4603d0fb5c24ae7",
        "after": "physical-native-facing-24b80f583f3a49778dacf9b8337862aa.json",
        "afterSha": "88c69d36ebbf1722d83869e288b01446240492f45b051dc5e0dca5ad8e893e0f",
        "rows": [
            ("left-pillar", 530, 841, 844, (820, 875), (800, 830), (860, 900)),
            ("right-pillar", 500, 2153, 2156, (2130, 2200), (2115, 2150), (2180, 2240)),
        ],
        "uiProbe": (1520, 700),
        "uiRect": (1340, 620, 1740, 960),
    },
    "second": {
        "capture": "observe-wgc-f37599014aaa422a94682503abb6d532",
        "imageSha": "5f09703eca7639f583e68bd40aea19d36d20483e3752ae743b776c90133c4c75",
        "receiptSha": "414b10c7d78be9d397d460f4eb2e7296144e574486ac491fa30ca6ec3eb168f9",
        "before": "physical-native-facing-82c8b813f64e4b46903f11d267dd4cc4.json",
        "beforeSha": "d7a9f90fcaee7a18005dc2827faab1727a0ff93a6bde4b7e64e60be1074b8905",
        "after": "physical-native-facing-dc22ffd6bcbe4518a167539b62f364a7.json",
        "afterSha": "89dad03250c429cbe2a28e8261a84f1324df76b49ab94fc2503fed0a851b8f03",
        "rows": [
            ("right-pillar-upper", 400, 1966, 1970, (1940, 2040), (1900, 1950), (2010, 2050)),
            ("right-pillar-middle", 500, 1940, 1960, (1930, 2030), (1880, 1940), (2000, 2040)),
        ],
        "uiProbe": (2200, 1000),
        "uiRect": (1900, 800, 2560, 1392),
    },
}


def _pinned(path: Path, expected: str) -> None:
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("optical-edge-source-sha256-mismatch: " + str(path))


def _median_luminance(image: Image.Image, x: int, y: int) -> float:
    pixels = (image.getpixel((xx, yy))
              for xx in range(x - 2, x + 3)
              for yy in range(y - 2, y + 3))
    return float(median(.2126 * r + .7152 * g + .0722 * b for r, g, b in pixels))


def bright_interior_onset(image: Image.Image, *, y: int, search: tuple[int, int],
                          background: tuple[int, int],
                          foreground: tuple[int, int]) -> dict:
    """Independent image-only 5x5 median luminance, calibrated to visible ROIs."""
    x_lo = min(search[0], background[0], foreground[0]) - 2
    x_hi = max(search[1], background[1], foreground[1]) + 5
    if not (2 <= y < image.height - 2 and 2 <= x_lo and x_hi < image.width - 2
            and search[1] - search[0] >= 5):
        raise ValueError("optical-edge-roi-out-of-bounds")
    values = {x: _median_luminance(image, x, y) for x in range(x_lo, x_hi + 1)}
    base = median(values[x] for x in range(background[0], background[1] + 1))
    bright = median(values[x] for x in range(foreground[0], foreground[1] + 1))
    if bright - base <= 12:
        raise ValueError("optical-edge-bright-contrast-insufficient")
    threshold = (base + bright) / 2
    edge = next((x for x in range(search[0], search[1] - 3)
                 if values[x] >= threshold and
                 sum(values[q] >= threshold for q in range(x, x + 5)) >= 4), None)
    if edge is None:
        raise ValueError("optical-edge-bright-onset-unavailable")
    return {"brightInteriorOnsetX": edge, "backgroundLuminance": round(base, 2),
            "interiorLuminance": round(bright, 2),
            "brightnessThreshold": round(threshold, 2),
            "measurement": "independent-screenshot-bright-interior-not-outer-silhouette",
            "uncertainty": "Manual ROI calibration; texture, shadows, outlines, "
                           "antialiasing and lighting shift bright onset."}


def _first_layer(frame, layers, indices, x: int, y: int) -> str:
    ray = physical_pixel_ray.pixel_ray(frame["camera"], frame["mapping"], x, y)
    result = composite.compare_layers(ray, layers, max_distance=200, indices=indices)
    hit = result["candidateFirst"]
    if result["ambiguousFirstLayer"] or hit is None:
        raise ValueError("optical-edge-geometry-layer-ambiguous")
    return hit["layer"]


def _projected_boundary(frame, layers, indices, y: int,
                        terrain_x: int, temple_x: int) -> tuple[int, int]:
    """Check each pixel of a short bracket; refuse an assumed monotonic boundary."""
    states = [_first_layer(frame, layers, indices, x, y)
              for x in range(terrain_x, temple_x + 1)]
    if states[0] != "terrain" or states[-1] != "temple-render":
        raise ValueError("optical-edge-projection-bracket-invalid")
    first_temple = states.index("temple-render")
    if any(value != "terrain" for value in states[:first_temple]) or any(
            value != "temple-render" for value in states[first_temple:]):
        raise ValueError("optical-edge-projection-not-monotonic")
    return terrain_x + first_temple - 1, terrain_x + first_temple


def analyze_view(view_name: str) -> dict:
    if view_name not in VIEWS:
        raise ValueError("optical-edge-unknown-view")
    entry = VIEWS[view_name]
    source_dir = ROOT / "artifacts"
    image_path = source_dir / entry["capture"] / "image.png"
    receipt_path = image_path.with_name("image.png.json")
    before_path = source_dir / entry["before"]
    after_path = source_dir / entry["after"]
    _pinned(image_path, entry["imageSha"])
    frame = composite.load_frame(
        image_path, receipt_path, entry["receiptSha"], before_path, entry["beforeSha"],
        after_path, entry["afterSha"], expected_host="AMD-DESKTOP")
    layers = [composite.load_terrain(TERRAIN, TERRAIN_REG),
              composite.load_temple(TEMPLE_ROOT / "geometry.obj",
                                    TEMPLE_ROOT / "atank-source-floor-anchor-exact-r2.json",
                                    TEMPLE_ANCHOR_SHA, frame["identity"])]
    indices = [accel.prepare(layer["vertices"], layer["faces"]) for layer in layers]
    results = []
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        for name, y, left, right, search, background, foreground in entry["rows"]:
            optical = bright_interior_onset(
                image, y=y, search=search, background=background,
                foreground=foreground)
            p_left, p_right = _projected_boundary(
                frame, layers, indices, y, left, right)
            midpoint = (p_left + p_right) / 2
            optical.update({
                "name": name, "y": y, "projectedLayerBoundaryPixels": [p_left, p_right],
                "projectedBoundaryMidpointX": midpoint,
                "brightInteriorMinusProjectedPixels":
                    round(optical["brightInteriorOnsetX"] - midpoint, 2),
                "searchWindowPixels": list(search),
                "backgroundCalibrationPixels": list(background),
                "interiorCalibrationPixels": list(foreground),
                "hudMasked": False, "visibleSurfaceQualified": False})
            results.append(optical)
        px, py = entry["uiProbe"]
        x0, y0, x1, y1 = entry["uiRect"]
        if not (x0 <= px < x1 and y0 <= py < y1):
            raise ValueError("optical-edge-hud-control-outside-mask")
        hud = {"pixel": [px, py], "imageRGB": list(image.getpixel((px, py))),
               "manualUiRect": [x0, y0, x1, y1],
               "manualUiMask": True,
               "underlyingWorldCandidateLayer":
                   _first_layer(frame, layers, indices, px, py),
               "pixelIsQualifiedWorldFragment": False,
               "visibleSurfaceQualified": False}
    for path, digest in ((image_path, entry["imageSha"]),
                         (receipt_path, entry["receiptSha"]),
                         (before_path, entry["beforeSha"]),
                         (after_path, entry["afterSha"])):
        _pinned(path, digest)
    for layer in layers:
        for path, digest in layer["pins"]:
            _pinned(Path(path), digest)
    return {"schema": SCHEMA, "status": "candidate-only", "view": view_name,
            "host": frame["identity"]["host"], "pid": frame["identity"]["pid"],
            "frameSha256": entry["imageSha"], "nativeBracketSeconds":
                frame["source"]["nativeBracketSeconds"], "rows": results,
            "hudOcclusionControl": hud, "noLiveCapture": True,
            "inputSent": False, "visibleSurfaceQualified": False,
            "opticalDepthQualified": False, "physicalBlockingQualified": False,
            "navigationQualified": False, "movementEligible": False,
            "qualification": "The image itself supplies brightness onset independent "
                             "of the source mesh; bright interior is not the outer "
                             "silhouette, physical collision, or a visibility proof."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", choices=("first", "second", "both"), default="both")
    args = parser.parse_args(argv)
    try:
        names = list(VIEWS) if args.view == "both" else [args.view]
        results = [analyze_view(name) for name in names]
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "reason": str(error),
                          "inputSent": False, "movementEligible": False}))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": "candidate-only",
                      "views": results, "inputSent": False,
                      "visibleSurfaceQualified": False,
                      "movementEligible": False}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
