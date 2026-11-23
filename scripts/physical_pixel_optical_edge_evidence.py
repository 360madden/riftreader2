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

ARCHIVE_DIR = ROOT / "artifacts"
RIFTWORLD_ROOT = ROOT.parent / "RiftWorld"
TEMPLE_DIR = Path("artifacts/p0-watch-temple-source-render-20261116-agent-iso-r1")
TEMPLE_ANCHOR = "atank-source-floor-anchor-exact-r2.json"
TERRAIN_OBJ = Path("artifacts/geometry-workflow-courtyard-20261114-r1/geometry.obj")
TERRAIN_REG = Path("pixel-surface-p1-20261116/courtyard-identity-hypothesis.json")
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

def _median_rgb(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    """Channel-wise median of a 5x5 retained screenshot neighborhood."""
    return tuple(int(median(image.getpixel((xx, yy))[channel]
                            for xx in range(x - 2, x + 3)
                            for yy in range(y - 2, y + 3)))
                 for channel in range(3))


def _rgb_luminance(rgb: tuple[int, int, int]) -> float:
    return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]


def _dark_profile_row(image: Image.Image, y: int, projected_terrain_x: int) -> dict:
    """Image-only local dark trough and four-pixel derivative; NOT a silhouette."""
    p = projected_terrain_x
    if not (2 <= y < image.height - 2 and 26 <= p < image.width - 24):
        raise ValueError("optical-dark-gradient-roi-out-of-bounds")
    colors = {x: _median_rgb(image, x, y) for x in range(p - 24, p + 21)}
    values = {x: _rgb_luminance(color) for x, color in colors.items()}
    pre = median(values[x] for x in range(p - 16, p - 6))
    trough = min(range(p - 4, p + 11), key=lambda x: (values[x], x))
    slope = min(range(p - 8, p + 11),
                key=lambda x: (values[x + 2] - values[x - 2], x))
    drop = pre - values[trough]
    delta = values[slope + 2] - values[slope - 2]
    before_rgb = tuple(int(median(colors[x][c] for x in range(p - 16, p - 6)))
                       for c in range(3))
    return {
        "darkTroughX": trough,
        "darkTroughMinusTerrainPixel": trough - p,
        "darkTroughRGB": list(colors[trough]),
        "precedingMedianRGB": list(before_rgb),
        "precedingMedianLuminance": round(pre, 2),
        "darkTroughLuminance": round(values[trough], 2),
        "darkDropFromPrecedingLuminance": round(drop, 2),
        "strongestNegativeGradientX": slope,
        "strongestNegativeGradientDelta4Px": round(delta, 2),
        "darkBandCandidate": bool(drop >= 8 and delta <= -8 and trough >= p - 1),
    }


def dark_gradient_profile(image: Image.Image, *, y: int, projected_boundary: tuple[int, int],
                          bright_interior_x: int,
                          neighbor_boundaries: dict[int, tuple[int, int] | None]) -> dict:
    """Opt-in candidate-only optical evidence with row-specific ray projections."""
    left, right = projected_boundary
    if right != left + 1:
        raise ValueError("optical-dark-gradient-nonadjacent-projected-boundary")
    offsets = (-8, -4, 0, 4, 8)
    if (set(neighbor_boundaries) != set(offsets)
            or neighbor_boundaries[0] != projected_boundary):
        raise ValueError("optical-dark-gradient-neighbor-projections-invalid")
    center = (left + right) / 2
    measured = _dark_profile_row(image, y, left)
    neighbors = []
    for offset in offsets:
        boundary = neighbor_boundaries[offset]
        if boundary is None:
            neighbors.append({
                "y": y + offset, "projectionStatus": "unavailable",
                "projectedLayerBoundaryPixels": None,
                "darkBandCandidate": False,
                "reason": "optical-edge-neighbor-projection-unavailable",
            })
            continue
        a, b = boundary
        if type(a) is not int or type(b) is not int or b != a + 1:
            raise ValueError("optical-dark-gradient-neighbor-projections-invalid")
        row = _dark_profile_row(image, y + offset, a)
        midpoint = (a + b) / 2
        neighbors.append({
            "y": y + offset, "projectionStatus": "candidate-bracketed",
            "projectedLayerBoundaryPixels": [a, b],
            "projectedBoundaryMidpointX": midpoint,
            "darkTroughX": row["darkTroughX"],
            "darkTroughMinusTerrainPixel": row["darkTroughMinusTerrainPixel"],
            "darkTroughMinusProjectedPixels": round(row["darkTroughX"] - midpoint, 2),
            "darkDropFromPrecedingLuminance": row["darkDropFromPrecedingLuminance"],
            "darkBandCandidate": row["darkBandCandidate"],
        })
    measured.update({
        "y": y,
        "projectedLayerBoundaryPixels": [left, right],
        "projectedBoundaryMidpointX": center,
        "darkTroughMinusProjectedPixels": round(measured["darkTroughX"] - center, 2),
        "brightInteriorOnsetX": bright_interior_x,
        "brightInteriorMinusProjectedPixels": round(bright_interior_x - center, 2),
        "brightInteriorRGB": list(_median_rgb(image, bright_interior_x, y)),
        "neighborRows": neighbors,
        "neighborRowsNotReprojected": False,
        "neighborRowsFullyReprojected":
            all(row["projectionStatus"] == "candidate-bracketed" for row in neighbors),
        "measurement": "image-only-dark-gradient-candidate-not-outer-silhouette",
        "uncertainty": "Manual ROI; dark trough may be shadow or terrain texture, not an "
                       "outer silhouette. Five-by-five filtering shifts edges; each "
                       "neighbor uses its own candidate ray projection, where available.",
        "opticalVisibilityQualified": False,
        "visibleSurfaceQualified": False,
        "opticalDepthQualified": False,
        "physicalBlockingQualified": False,
        "movementEligible": False,
    })
    return measured


def hud_gradient_false_positive_control(image: Image.Image, *, point: tuple[int, int],
                                        ui_rect: tuple[int, int, int, int]) -> dict:
    x, y = point
    x0, y0, x1, y1 = ui_rect
    if not (x0 <= x < x1 and y0 <= y < y1 and
            x >= 12 and y >= 2 and x < image.width - 12 and y < image.height - 2):
        raise ValueError("optical-dark-gradient-hud-control-invalid")
    profile = [_rgb_luminance(_median_rgb(image, xx, y))
               for xx in range(x - 10, x + 11)]
    return {
        "pixel": [x, y],
        "manualUiMask": True,
        "horizontalLuminanceRange21Px": round(max(profile) - min(profile), 2),
        "opticalGradientMayComeFromHud": True,
        "pixelIsQualifiedWorldFragment": False,
        "opticalVisibilityQualified": False,
        "movementEligible": False,
    }




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


def analyze_view(view_name: str, *, dark_gradient: bool = False,
                 archive_dir: Path = ARCHIVE_DIR,
                 riftworld_root: Path = RIFTWORLD_ROOT) -> dict:
    if view_name not in VIEWS:
        raise ValueError("optical-edge-unknown-view")
    entry = VIEWS[view_name]
    image_path = archive_dir / entry["capture"] / "image.png"
    receipt_path = image_path.with_name("image.png.json")
    before_path = archive_dir / entry["before"]
    after_path = archive_dir / entry["after"]
    _pinned(image_path, entry["imageSha"])
    frame = composite.load_frame(
        image_path, receipt_path, entry["receiptSha"], before_path, entry["beforeSha"],
        after_path, entry["afterSha"], expected_host="AMD-DESKTOP", retained=True)
    temple_dir = riftworld_root / TEMPLE_DIR
    layers = [composite.load_terrain(riftworld_root / TERRAIN_OBJ, archive_dir / TERRAIN_REG),
              composite.load_temple(temple_dir / "geometry.obj", temple_dir / TEMPLE_ANCHOR,
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
        if dark_gradient:
            dark_profiles = []
            # Neighbor rows need their own geometry rays: fixed-pixel dark
            # gradients are not necessarily aligned to the projected edge.
            for row, (_, y, left, right, *_roi) in zip(results, entry["rows"]):
                neighbors = {0: tuple(row["projectedLayerBoundaryPixels"])}
                for offset in (-8, -4, 4, 8):
                    try:
                        # The bounded +/-16px bracket tolerates a sloping edge;
                        # the monotonic-layer test still refuses multiple crossings.
                        neighbors[offset] = _projected_boundary(
                            frame, layers, indices, y + offset, left - 16, right + 16)
                    except ValueError as error:
                        if str(error) not in {
                            "optical-edge-geometry-layer-ambiguous",
                            "optical-edge-projection-bracket-invalid",
                            "optical-edge-projection-not-monotonic",
                        }:
                            raise
                        neighbors[offset] = None
                dark_profiles.append(dark_gradient_profile(
                    image, y=y,
                    projected_boundary=tuple(row["projectedLayerBoundaryPixels"]),
                    bright_interior_x=row["brightInteriorOnsetX"],
                    neighbor_boundaries=neighbors))
            hud_gradient = hud_gradient_false_positive_control(
                image, point=entry["uiProbe"], ui_rect=entry["uiRect"])
    for path, digest in ((image_path, entry["imageSha"]),
                         (receipt_path, entry["receiptSha"]),
                         (before_path, entry["beforeSha"]),
                         (after_path, entry["afterSha"])):
        _pinned(path, digest)
    for layer in layers:
        for path, digest in layer["pins"]:
            _pinned(Path(path), digest)
    report = {"schema": SCHEMA, "status": "candidate-only", "view": view_name,
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
    if dark_gradient:
        report.update({"darkGradientProfiles": dark_profiles,
                       "hudGradientFalsePositiveControl": hud_gradient,
                       "opticalVisibilityQualified": False})
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", choices=("first", "second", "both"), default="both")
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR,
                        help="RiftReader2 artifacts directory or a copy with the same layout")
    parser.add_argument("--riftworld-root", type=Path, default=RIFTWORLD_ROOT,
                        help="RiftWorld checkout or archive root containing its artifacts directory")
    parser.add_argument("--dark-gradient", action="store_true",
                        help="Opt-in retained-PNG dark-trough optical candidate profile")
    args = parser.parse_args(argv)
    try:
        names = list(VIEWS) if args.view == "both" else [args.view]
        results = [analyze_view(name, dark_gradient=args.dark_gradient,
                                archive_dir=args.archive_dir, riftworld_root=args.riftworld_root)
                   for name in names]
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "reason": str(error),
                          "inputSent": False, "movementEligible": False}))
        return 2
    output = {"schema": SCHEMA, "status": "candidate-only",
              "views": results, "inputSent": False,
              "visibleSurfaceQualified": False, "movementEligible": False}
    if args.dark_gradient:
        output["opticalVisibilityQualified"] = False
    print(json.dumps(output, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
