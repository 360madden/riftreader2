"""Recheck a pinned physical WGC screenshot against manually picked source OBJ vertices.

Only historical, static landmark alignment is assessed. No pixel depth buffer,
obstacle contact, full-world registration, pathfinding authority or game input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_pixel_ray
from scripts import physical_pixel_surface as surface
from scripts import physical_rift
from scripts.waypoint_view_bundle import bundle_asset

SCHEMA = "rr2.retained-pixel-source-landmarks/1"
MAX_METADATA = 2 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
SHIFTS = ((10, 0, 0), (0, 1, 0), (0, 0, 10))
CAMERA_STABILITY = (
    "worldEyeXYZ", "renderOriginXYZ", "rotationRowMajor", "projectionRowMajor",
    "projectionRawBits", "rawBits", "viewportLeftRightTopBottom",
)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _read_pinned(path, max_bytes, label, expected_sha=None):
    path, raw, sha = surface._source_bytes(path, max_bytes, label)
    if expected_sha is not None:
        _require(isinstance(expected_sha, str)
                 and surface._HEX_SHA.fullmatch(expected_sha) is not None,
                 label + "-expected-sha-invalid")
        _require(sha == expected_sha.lower(), label + "-sha256-mismatch")
    return path, raw, {"path": str(path), "sha256": sha}


def _json(path, label, expected_sha=None):
    path, raw, source = _read_pinned(path, MAX_METADATA, label, expected_sha)
    data = surface._strict_json(raw)
    _require(type(data) in (dict, list), label + "-json-invalid")
    return data, source


def _utc(value, name):
    _require(isinstance(value, str), name + "-utc-invalid")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(name + "-utc-invalid") from error
    _require(dt.tzinfo is not None and dt.utcoffset() is not None,
             name + "-utc-without-zone")
    return dt.astimezone(timezone.utc)


def _frame_xy(camera, mapping, xyz):
    projection = physical_rift._project_world_point(camera, dict(zip("xyz", xyz)))
    _require(projection.get("status") == "available-candidate",
             "landmark-projection-unavailable")
    x = projection["normalizedX"] * mapping["clientWidth"] + mapping["clientLeft"]
    y = projection["normalizedY"] * mapping["clientHeight"] + mapping["clientTop"]
    _require(math.isfinite(x) and math.isfinite(y), "landmark-projection-nonfinite")
    return [x, y]


def replay(archive_dir, mesh_obj, expected_host=None, *, pins=None, retained_frame_dir=None):
    """Replay one immutable source-landmark/image/native bracket in a single call."""
    pins = {} if pins is None else pins
    _require(isinstance(pins, dict), "landmark-pins-invalid")
    retained = retained_frame_dir is not None
    if retained:
        _require(all(pins.get(key) for key in ("observation", "before", "after", "landmarks", "mesh", "receipt")),
                 "landmark-retained-replay-requires-all-source-hashes")
    archive_dir = Path(archive_dir)
    source, sources = {}, {}
    names = {
        "observation": "observation-final.json",
        "before": "native-final-before.json",
        "after": "native-final-after.json",
        "landmarks": "landmarks.json",
    }
    for kind, name in names.items():
        path = bundle_asset(archive_dir, name) if retained else archive_dir / name
        source[kind], sources[kind] = _json(path, kind, pins.get(kind))
    obs, before, after, landmarks = (source[k] for k in names)
    _require(type(obs) is dict and type(before) is dict and type(after) is dict,
             "native-or-image-report-invalid")
    source_host = obs.get("ownerHost")
    _require(physical_rift.valid_host_name(source_host)
             and (expected_host is None or (physical_rift.valid_host_name(expected_host)
                  and source_host.casefold() == expected_host.casefold())), "landmark-capture-host-mismatch")
    _require(obs.get("captureBackend") == "Windows.Graphics.Capture"
             and obs.get("foregroundMayChange") is False
             and obs.get("nativeFacing", {}).get("status") == "stable-bracket-candidate",
             "landmark-physical-wgc-not-admitted")
    target = obs.get("target")
    mapping = obs.get("clientFrameMapping")
    _require(type(target) is dict and type(mapping) is dict
             and mapping.get("status") == "available-candidate",
             "landmark-identity-or-client-mapping-missing")
    if retained:
        _require(physical_rift.valid_host_name(target.get("hostName"))
                 and target["hostName"].casefold() == source_host.casefold(), "landmark-target-host-mismatch")
    for kind, report in (("before", before), ("after", after)):
        ident = report.get("identity")
        _require(type(ident) is dict
                 and type(ident.get("processId")) is int
                 and ident["processId"] == target.get("processId")
                 and str(ident.get("processStartUtcTicks"))
                     == target.get("processStartUtcTicks")
                 and ident.get("executablePath") == target.get("executablePath")
                 and ident.get("executableSha256", "").lower()
                     == target.get("executableSha256", "").lower(),
                 "landmark-native-process-epoch-mismatch:" + kind)
        original = obs["nativeFacing"].get(kind + "Output")
        _require(isinstance(original, str) and original, "landmark-native-source-missing:" + kind)
        if not retained:
            _, _, original_ref = _read_pinned(original, MAX_METADATA, kind + "-original",
                                             sources[kind]["sha256"])
            original = original_ref["path"]
        sources[kind]["original"] = original
    first, last = before.get("observation"), after.get("observation")
    _require(type(first) is dict and type(last) is dict,
             "landmark-native-samples-missing")
    camera_before, camera_after = (x.get("opticalCameraCandidate") for x in (first, last))
    _require(type(camera_before) is dict and type(camera_after) is dict
             and camera_before.get("status") == camera_after.get("status")
                 == "available-candidate"
             and all(key in camera_before and key in camera_after
                     and camera_before[key] == camera_after[key]
                     for key in CAMERA_STABILITY),
             "landmark-camera-changed-across-wgc-bracket")
    capture_utc = _utc(obs.get("capturedAtUtc"), "landmark-capture")
    first_end = _utc(first.get("completedAtUtc"), "landmark-native-before")
    last_start = _utc(last.get("startedAtUtc"), "landmark-native-after")
    _require(first_end < capture_utc < last_start
             and (last_start - first_end).total_seconds() <= 10,
             "landmark-wgc-native-timing-invalid")
    image_path, receipt_path = obs.get("image"), obs.get("receipt")
    image_sha = obs.get("imageSha256")
    _require(isinstance(image_sha, str) and surface._HEX_SHA.fullmatch(image_sha),
             "landmark-image-expected-sha-invalid")
    if retained:
        _require(all(isinstance(path, str) and path for path in (image_path, receipt_path)),
                 "landmark-frame-source-missing")
        image_path = bundle_asset(retained_frame_dir, "image.png")
        receipt_path = bundle_asset(retained_frame_dir, "image.png.json")
    _, _, image_ref = _read_pinned(image_path, MAX_IMAGE, "landmark-image", image_sha)
    receipt, receipt_ref = _json(receipt_path, "landmark-receipt", pins.get("receipt"))
    _require(type(receipt) is dict and receipt.get("inputSent") is False
             and receipt.get("focusChangedByProbe") is False
             and receipt.get("imageSha256", "").lower() == image_ref["sha256"]
             and receipt.get("frameWidth") == mapping.get("frameWidth")
             and receipt.get("frameHeight") == mapping.get("frameHeight")
             and receipt.get("clientFrameMapping") == mapping,
             "landmark-wgc-receipt-unqualified")
    if retained:
        _require(physical_rift.valid_host_name(receipt.get("machine"))
                 and receipt["machine"].casefold() == source_host.casefold(), "landmark-receipt-host-mismatch")
        image_ref["original"], receipt_ref["original"] = obs["image"], obs["receipt"]
    for which in ("targetBefore", "targetAfter"):
        val = receipt.get(which)
        _require(type(val) is dict and val.get("pid") == target["processId"]
                 and str(val.get("startTicks")) == target["processStartUtcTicks"]
                 and val.get("sha256", "").lower()
                     == target["executableSha256"].lower()
                 and val.get("hwnd") == target["hwnd"],
                 "landmark-wgc-target-rebind:" + which)
    mesh_path, mesh_raw, mesh_ref = _read_pinned(
        mesh_obj, surface.MAX_MESH_BYTES, "landmark-mesh", pins.get("mesh"))
    _require(mesh_path.suffix.lower() == ".obj", "landmark-mesh-must-be-obj")
    vertices, faces = surface.parse_obj(
        mesh_raw, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]])
    _require(type(landmarks) is list and 3 <= len(landmarks) <= 16,
             "landmarks-require-three-to-sixteen-points")
    used = {i for indices, _ in faces for i in indices}
    model_points = {vertices[i] for i in used}
    results, positions, names_seen = [], [], set()
    for index, item in enumerate(landmarks, 1):
        _require(type(item) is dict and type(item.get("name")) is str
                 and item["name"] and item["name"] not in names_seen,
                 "landmark-name-invalid-or-duplicate")
        names_seen.add(item["name"])
        xyz = surface._xyz(item.get("sourceXYZ"), "landmark-source-xyz")
        _require(xyz in model_points, "landmark-not-an-exact-referenced-obj-vertex")
        pixel = item.get("frameXY")
        uncertainty = item.get("selectionUncertaintyPixels")
        _require(isinstance(pixel, list) and len(pixel) == 2
                 and all(type(value) is int for value in pixel)
                 and type(uncertainty) in (int, float)
                 and math.isfinite(uncertainty) and 0 < uncertainty <= 10,
                 "landmark-pixel-or-uncertainty-invalid")
        ray = physical_pixel_ray.pixel_ray(camera_after, mapping, *pixel)
        projected = _frame_xy(camera_after, mapping, xyz)
        error = math.dist(projected, pixel)
        origin = ray["nativeEyeXYZ"]
        direction = ray["unitDirectionXYZ"]
        delta = [xyz[i] - origin[i] for i in range(3)]
        depth = sum(a*b for a, b in zip(delta, direction))
        _require(depth > 0, "landmark-behind-native-camera")
        perpendicular = math.hypot(*[delta[i] - depth*direction[i] for i in range(3)])
        controls = {}
        for change in SHIFTS:
            changed = [xyz[i] + change[i] for i in range(3)]
            controls[str(change)] = math.dist(_frame_xy(camera_after, mapping, changed), pixel)
        positions.append(xyz)
        results.append({"name": item["name"], "framePixel": pixel,
                        "sourceXYZ": xyz, "meshVertexExact": True,
                        "projectedFrameXY": projected,
                        "pixelResidual": error, "selectionUncertaintyPixels": uncertainty,
                        "rayMissDistanceNative": perpendicular, "depthAlongRayNative": depth,
                        "shiftResidualPixels": controls,
                        "withinManualSelectionUncertainty": error <= uncertainty})
    a = surface._subtract(positions[1], positions[0])
    b = surface._subtract(positions[2], positions[0])
    _require(math.hypot(*surface._cross(a, b)) > 1e-4,
             "landmark-source-vertices-collinear")
    agreement = all(row["withinManualSelectionUncertainty"] for row in results)
    shifted_rejected = all(
        all(value > max(row["selectionUncertaintyPixels"], 10)
            for value in row["shiftResidualPixels"].values())
        for row in results)
    return {"schema": SCHEMA,
            "status": ("historical-landmark-frame-alignment-candidate"
                       if agreement and shifted_rejected else "inconclusive"),
            "identity": {"host": source_host, "processId": target["processId"],
                         "processStartUtcTicks": target["processStartUtcTicks"],
                         "executableSha256": target["executableSha256"]},
            "capturedAtUtc": capture_utc.isoformat(),
            "bracketSeconds": (last_start - first_end).total_seconds(),
            "sources": {**sources, "image": image_ref, "receipt": receipt_ref,
                        "mesh": mesh_ref},
            "modelVertexCount": len(vertices), "modelTriangleCount": len(faces),
            "landmarkCount": len(results), "landmarks": results,
            "reprojectionInsideManualUncertainty": agreement,
            "translationNegativeControlsRejected": shifted_rejected,
            "allSourceMeshRegistered": False,
            "independentDepthQualified": False, "occlusionQualified": False,
            "collisionQualified": False, "movementEligible": False, "inputSent": False,
            "qualification": "Three manually selected historical screenshot corners map to "
                             "exact source-OBJ vertices under an unchanged native optical "
                             "camera. Perturbation controls constrain local image alignment, "
                             "not arbitrary depth, mesh coverage, Havok world, or traversal."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--mesh-obj", type=Path, required=True)
    parser.add_argument("--expected-host", help="optional assertion of the original capture hostname")
    parser.add_argument("--retained-frame-dir", type=Path,
                        help="use copied image.png and image.png.json without opening the recorded source paths")
    parser.add_argument("--receipt-sha256", help="expected WGC receipt hash, required for --retained-frame-dir")
    parser.add_argument("--mesh-sha256", required=True)
    parser.add_argument("--landmarks-sha256", required=True)
    parser.add_argument("--observation-sha256", required=True)
    parser.add_argument("--native-before-sha256", required=True)
    parser.add_argument("--native-after-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = replay(args.archive_dir, args.mesh_obj, args.expected_host,
                        pins={"mesh": args.mesh_sha256, "landmarks": args.landmarks_sha256,
                              "observation": args.observation_sha256,
                              "before": args.native_before_sha256,
                              "after": args.native_after_sha256, "receipt": args.receipt_sha256},
                        retained_frame_dir=args.retained_frame_dir)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "reason": str(error),
                          "inputSent": False, "movementEligible": False}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
