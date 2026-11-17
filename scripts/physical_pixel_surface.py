"""Offline native-camera ray vs explicitly pinned Wavefront OBJ candidate surfaces.

The mesh-to-native transform is a stated *hypothesis*, not verified world
registration. Never infer reachability, floor authority or live RIFT input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_pixel_ray

SCHEMA = "rr2.retained-frame-pixel-surface/1"
REGISTRATION_SCHEMA = "rr2.mesh-frame-hypothesis/1"
MAX_MESH_BYTES = 16 * 1024 * 1024
MAX_REGISTRATION_BYTES = 16 * 1024
MAX_VERTICES = 250_000
MAX_TRIANGLES = 400_000
MAX_REPORTED_HITS = 64
MAX_FOOTPRINT_RADIUS = 3
MAX_FOOTPRINT_SAMPLES = 1 + 4 * MAX_FOOTPRINT_RADIUS
MAX_FOOTPRINT_REPORT_BYTES = 2 * 1024 * 1024
_HEX_SHA = re.compile(r"[0-9a-fA-F]{64}\Z")
_INDEX = re.compile(r"[1-9][0-9]*\Z")


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _xyz(value, name):
    _require(isinstance(value, (tuple, list)) and len(value) == 3
             and all(type(a) in (int, float) and math.isfinite(a) for a in value),
             name + "-must-be-finite-xyz")
    return tuple(float(a) for a in value)


def _strict_json(data):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate-registration-key: " + key)
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError("non-finite-registration-value: " + value)))


def _source_bytes(path, max_bytes, label):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    _require(0 < len(raw) <= max_bytes, label + "-size-out-of-bounds")
    return path, raw, hashlib.sha256(raw).hexdigest()


def load_registration(path, mesh_sha256):
    """Require a SHA-pinned mesh and explicit affine source-to-native hypothesis."""
    path, raw, digest = _source_bytes(path, MAX_REGISTRATION_BYTES, "registration")
    data = _strict_json(raw)
    _require(isinstance(data, dict)
             and set(data) == {"schema", "meshSha256", "sourceFrame",
                               "sourceToNativeRows", "qualification"},
             "registration-fields-invalid")
    _require(data["schema"] == REGISTRATION_SCHEMA
             and data["qualification"] == "candidate-only",
             "registration-must-be-candidate-only")
    _require(isinstance(data["meshSha256"], str)
             and _HEX_SHA.fullmatch(data["meshSha256"]) is not None
             and data["meshSha256"].lower() == mesh_sha256.lower(),
             "registration-mesh-sha256-mismatch")
    frame = data["sourceFrame"]
    _require(isinstance(frame, str) and 1 <= len(frame) <= 100
             and frame == frame.strip() and all(32 <= ord(c) < 127 for c in frame),
             "registration-source-frame-invalid")
    rows = data["sourceToNativeRows"]
    _require(isinstance(rows, list) and len(rows) == 3
             and all(isinstance(row, list) and len(row) == 4
                     and all(type(v) in (int, float) and math.isfinite(v) for v in row)
                     for row in rows),
             "registration-source-to-native-affine-invalid")
    a, b, c = (tuple(float(v) for v in row) for row in rows)
    determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                   - a[1] * (b[0] * c[2] - b[2] * c[0])
                   + a[2] * (b[0] * c[1] - b[1] * c[0]))
    _require(math.isfinite(determinant) and abs(determinant) > 1e-12,
             "registration-affine-transform-singular")
    _require(all(abs(v) <= 1e7 for row in rows for v in row),
             "registration-affine-transform-out-of-bounds")
    return {"path": str(path), "sha256": digest, "sourceFrame": frame,
            "sourceToNativeRows": rows, "qualification": "candidate-only"}


def _transform(vertex, rows):
    point = tuple(sum(row[i] * vertex[i] for i in range(3)) + row[3]
                  for row in rows)
    _require(all(math.isfinite(v) and abs(v) <= 1e9 for v in point),
             "transformed-mesh-vertex-out-of-bounds")
    return point


def parse_obj(raw, source_to_native):
    """Parse RiftWorld-compatible triangular OBJ with bounded, explicit geometry."""
    _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_MESH_BYTES,
             "mesh-size-out-of-bounds")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("mesh-must-be-utf8") from error
    vertices, faces = [], []
    group = "unnamed"
    for line_no, line in enumerate(lines, 1):
        parts = line.strip().split()
        if not parts or parts[0].startswith("#"):
            continue
        kind = parts[0]
        if kind == "v":
            _require(len(parts) == 4, "mesh-vertex-not-xyz-at-line-" + str(line_no))
            try:
                vertex = _xyz([float(v) for v in parts[1:]], "mesh-vertex")
            except (OverflowError, ValueError) as error:
                raise ValueError("mesh-vertex-invalid-at-line-" + str(line_no)) from error
            vertices.append(_transform(vertex, source_to_native))
            _require(len(vertices) <= MAX_VERTICES, "mesh-vertex-limit-exceeded")
        elif kind == "f":
            _require(len(parts) == 4, "mesh-non-triangle-at-line-" + str(line_no))
            indexes = []
            for token in parts[1:]:
                first = token.split("/")[0]
                _require(_INDEX.fullmatch(first) is not None,
                         "mesh-face-index-invalid-at-line-" + str(line_no))
                index = int(first) - 1
                _require(index < len(vertices),
                         "mesh-face-forward-index-at-line-" + str(line_no))
                indexes.append(index)
            faces.append((tuple(indexes), group))
            _require(len(faces) <= MAX_TRIANGLES, "mesh-triangle-limit-exceeded")
        elif kind in {"g", "o"}:
            group = " ".join(parts[1:])[:80] or "unnamed"
        elif kind in {"vt", "vn", "s", "usemtl", "mtllib"}:
            continue
        else:
            raise ValueError("unsupported-mesh-primitive-" + kind + "-at-line-" + str(line_no))
    _require(bool(vertices) and bool(faces), "mesh-has-no-triangles")
    return vertices, faces


def _subtract(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _intersect(origin, direction, a, b, c, max_distance):
    """Two-sided Möller-Trumbore: backfaces are evidence, never discarded."""
    edge1, edge2 = _subtract(b, a), _subtract(c, a)
    normal = _cross(edge1, edge2)
    normal_length = math.hypot(*normal)
    if normal_length <= 1e-12:
        return None, True
    p = _cross(direction, edge2)
    det = _dot(edge1, p)
    if abs(det) <= 1e-12 * normal_length:
        return None, False
    inv = 1 / det
    tvec = _subtract(origin, a)
    u = _dot(tvec, p) * inv
    if not -1e-10 <= u <= 1 + 1e-10:
        return None, False
    q = _cross(tvec, edge1)
    v = _dot(direction, q) * inv
    if v < -1e-10 or u + v > 1 + 1e-10:
        return None, False
    t = _dot(edge2, q) * inv
    if not 1e-6 < t <= max_distance:
        return None, False
    point = [origin[i] + direction[i] * t for i in range(3)]
    _require(all(math.isfinite(value) for value in point), "mesh-hit-nonfinite")
    n = [value / normal_length for value in normal]
    return {"distanceNative": t, "candidateXYZ": point,
            "barycentric": [1 - u - v, u, v],
            "normalXYZ": n, "frontFacing": _dot(n, direction) < 0}, False


def intersect_obj(raw, ray, source_to_native, max_distance=2000.0, selected_triangle=None):
    """Parse one mesh and intersect one ray; use intersect_prepared for repeated pixels."""
    vertices, faces = parse_obj(raw, source_to_native)
    return intersect_prepared(vertices, faces, ray, max_distance=max_distance,
                              selected_triangle=selected_triangle)


def intersect_prepared(vertices, faces, ray, max_distance=2000.0, selected_triangle=None):
    """Intersect a previously checked mesh without reparsing it for every pixel."""
    _require(type(max_distance) in (int, float) and math.isfinite(max_distance)
             and 0 < max_distance <= 10000, "max-distance-invalid")
    _require(selected_triangle is None or
             (type(selected_triangle) is int and 1 <= selected_triangle <= MAX_TRIANGLES),
             "selected-triangle-index-invalid")
    _require(isinstance(ray, dict) and ray.get("status") == "available-candidate",
             "validated-pixel-ray-required")
    origin = _xyz(ray.get("nativeEyeXYZ"), "native-eye")
    direction = _xyz(ray.get("unitDirectionXYZ"), "ray-direction")
    _require(abs(math.hypot(*direction) - 1) <= 1e-6, "ray-not-unit-length")
    hits, degenerates = [], 0
    for face_index, (indices, group) in enumerate(faces, 1):
        a, b, c = (vertices[i] for i in indices)
        hit, degenerate = _intersect(origin, direction, a, b, c, max_distance)
        degenerates += degenerate
        if hit is not None:
            hit["triangleIndex"] = face_index
            hit["meshGroup"] = group
            hits.append(hit)
    hits.sort(key=lambda item: (item["distanceNative"], item["triangleIndex"]))
    groups = []
    for hit in hits:
        # Shared mesh edges can produce multiple triangles at one depth.
        if not groups or hit["distanceNative"] - groups[-1][0] > 1e-4:
            groups.append([hit["distanceNative"], 0])
        groups[-1][1] += 1
        hit["depthGroup"] = len(groups)
    for hit in hits:
        hit["coincidentGroupSize"] = groups[hit["depthGroup"] - 1][1]
    selected_hit = None
    if selected_triangle is not None:
        _require(selected_triangle <= len(faces), "selected-triangle-out-of-mesh")
        selected_hit = next((dict(hit) for hit in hits
                             if hit["triangleIndex"] == selected_triangle), None)
        _require(selected_hit is not None, "selected-triangle-not-intersected")
        selected_hit.update(admissionEligible=False, worldSurfaceVerified=False,
                            qualification="Explicit display-only triangle candidate; "
                                          "not a qualified floor or route destination")
    return {"status": "candidate-hits" if hits else "no-candidate-intersection",
            "trianglesChecked": len(faces), "verticesChecked": len(vertices),
            "degenerateTriangles": degenerates, "hitCount": len(hits),
            "distinctDepthGroups": len(groups), "hitsTruncated": len(hits) > MAX_REPORTED_HITS,
            "candidateFirstXYZ": hits[0]["candidateXYZ"] if hits else None,
            "selectedTriangleIndex": selected_triangle, "selectedHit": selected_hit,
            "hits": hits[:MAX_REPORTED_HITS],
            "sourceCoverageComplete": False, "floorQualified": False,
            "movementEligible": False,
            "obstacleQualified": False, "occlusionQualified": False,
            "qualification": "Offline ray/mesh mathematical candidates only; OBJ source-frame "
                             "registration, world instance, mesh coverage, rendered depth, "
                             "collision response, stacked floor choice and route clearance "
                             "are not independently qualified."}



def _verified_footprint_camera(observation_path, retained_ray, x, y):
    """Recover only the same hash-admitted native camera and WGC client mapping."""
    _, raw, observation_sha = _source_bytes(
        observation_path, MAX_FOOTPRINT_REPORT_BYTES, "footprint-observation")
    _require(observation_sha == retained_ray["source"]["sha256"],
             "footprint-observation-changed-after-admission")
    observation = _strict_json(raw)
    _require(type(observation) is dict
             and type(observation.get("nativeFacing")) is dict,
             "footprint-native-bracket-missing")
    after_path = observation["nativeFacing"].get("afterOutput")
    _require(isinstance(after_path, str) and bool(after_path),
             "footprint-native-after-path-missing")
    _, after_bytes, after_sha = _source_bytes(
        after_path, MAX_FOOTPRINT_REPORT_BYTES, "footprint-native-after")
    _require(after_sha == retained_ray["source"]["nativeAfterSha256"],
             "footprint-native-after-changed-after-admission")
    native = _strict_json(after_bytes)
    _require(type(native) is dict and type(native.get("observation")) is dict,
             "footprint-native-after-report-invalid")
    camera = native["observation"].get("opticalCameraCandidate")
    receipt_path = observation.get("receipt")
    _require(isinstance(receipt_path, str) and bool(receipt_path),
             "footprint-wgc-receipt-path-missing")
    _, receipt_raw, receipt_sha = _source_bytes(
        receipt_path, MAX_FOOTPRINT_REPORT_BYTES, "footprint-wgc-receipt")
    _require(receipt_sha == retained_ray["source"]["receiptSha256"].lower(),
             "footprint-wgc-receipt-changed-after-admission")
    receipt = _strict_json(receipt_raw)
    _require(type(receipt) is dict, "footprint-wgc-receipt-invalid")
    mapping = receipt.get("clientFrameMapping")
    if "clientFrameMapping" in observation:
        _require(observation["clientFrameMapping"] == mapping,
                 "footprint-client-mapping-source-mismatch")
    center = physical_pixel_ray.pixel_ray(camera, mapping, x, y)
    _require(center == retained_ray["ray"], "footprint-center-ray-mismatch")
    return camera, mapping


def sample_pixel_footprint(vertices, faces, camera, mapping, x, y, radius, *,
                           center_ray, center_surface, max_distance=2000.0,
                           intersector=None):
    """Report candidate first-surface disagreement across bounded cardinal pixels.

    This is not a screen-space depth buffer or a visible-surface decision. Offsets
    are center, then left/right/up/down at each integer step through radius.
    """
    _require(type(radius) is int and 1 <= radius <= MAX_FOOTPRINT_RADIUS,
             "pixel-selection-radius-invalid")
    offsets = [(0, 0)]
    for step in range(1, radius + 1):
        offsets.extend(((-step, 0), (step, 0), (0, -step), (0, step)))
    _require(len(offsets) <= MAX_FOOTPRINT_SAMPLES, "pixel-footprint-cap-exceeded")
    rays = []
    for dx, dy in offsets:
        try:
            candidate = physical_pixel_ray.pixel_ray(camera, mapping, x + dx, y + dy)
        except ValueError as error:
            raise ValueError("pixel-footprint-neighbor-invalid: " + str(error)) from error
        rays.append(candidate)
    _require(rays[0] == center_ray, "pixel-footprint-center-ray-mismatch")
    samples, group_counts, depths = [], {}, []
    missing = 0
    query = intersect_prepared if intersector is None else intersector
    _require(callable(query), "pixel-footprint-intersector-invalid")
    for (dx, dy), ray in zip(offsets, rays):
        intersection = (center_surface if dx == 0 and dy == 0
                        else query(vertices, faces, ray, max_distance=max_distance))
        hits = intersection["hits"]
        nearest = hits[0] if hits else None
        if nearest is None:
            missing += 1
        else:
            group = nearest["meshGroup"]
            group_counts[group] = group_counts.get(group, 0) + 1
            depths.append(nearest["distanceNative"])
        samples.append({"offsetPixels": [dx, dy], "framePixel": [x + dx, y + dy],
                        "status": ("first-candidate-hit" if nearest else
                                   "no-candidate-intersection"),
                        "firstMeshGroup": nearest["meshGroup"] if nearest else None,
                        "firstTriangleIndex": nearest["triangleIndex"] if nearest else None,
                        "firstDistanceNative": (nearest["distanceNative"]
                                                if nearest else None)})
    mixed = len(group_counts) > 1 or 0 < missing < len(samples)
    return {"schema": "rr2.retained-pixel-footprint/1",
            "status": ("ambiguous-first-surface" if mixed else
                       "no-candidate-intersection" if missing == len(samples) else
                       "single-first-group-candidate"),
            "radiusPixels": radius, "pattern": "center-plus-cardinals-at-each-integer-step",
            "sampleCount": len(samples), "maxSampleCount": MAX_FOOTPRINT_SAMPLES,
            "firstMeshGroupCounts": [{"meshGroup": group, "count": group_counts[group]}
                                     for group in sorted(group_counts)],
            "missingFirstHitCount": missing,
            "firstDistanceRangeNative": [min(depths), max(depths)] if depths else None,
            "ambiguousFirstSurface": mixed, "samples": samples,
            "visibleSurfaceQualified": False, "movementEligible": False,
            "qualification": "Candidate first hits are sampled at nearby pixels; "
                             "neighbor samples cannot prove visible geometry, rendered "
                             "depth, obstacle response, world registration or route clearance."}


def pick_retained(observation, route, x, y, mesh_path, registration_path,
                  max_distance=2000.0, selected_triangle=None,
                  anchor_join_path=None, anchor_join_sha256=None,
                  rack_report_path=None, rack_report_sha256=None,
                  pixel_selection_radius=0):
    """Pair admitted saved physical screenshot with explicitly SHA-pinned mesh."""
    ray = physical_pixel_ray.pick_retained(observation, route, x, y)
    audit_fields = (anchor_join_path, anchor_join_sha256,
                    rack_report_path, rack_report_sha256)
    _require(not any(value is not None for value in audit_fields)
             or all(value is not None for value in audit_fields),
             "source-anchor-audit-requires-all-four-arguments")
    anchor_audit = None
    if all(value is not None for value in audit_fields):
        from scripts import physical_pixel_anchor
        anchor_audit = physical_pixel_anchor.audit(
            ray, anchor_join_path, anchor_join_sha256,
            rack_report_path, rack_report_sha256)
    mesh_path, raw, digest = _source_bytes(mesh_path, MAX_MESH_BYTES, "mesh")
    _require(mesh_path.suffix.lower() == ".obj", "mesh-must-be-obj")
    registration = load_registration(registration_path, digest)
    _require(type(pixel_selection_radius) is int
             and 0 <= pixel_selection_radius <= MAX_FOOTPRINT_RADIUS,
             "pixel-selection-radius-invalid")
    footprint = None
    if pixel_selection_radius:
        camera, mapping = _verified_footprint_camera(observation, ray, x, y)
        vertices, faces = parse_obj(raw, registration["sourceToNativeRows"])
        intersections = intersect_prepared(
            vertices, faces, ray["ray"], max_distance=max_distance,
            selected_triangle=selected_triangle)
        footprint = sample_pixel_footprint(
            vertices, faces, camera, mapping, x, y, pixel_selection_radius,
            center_ray=ray["ray"], center_surface=intersections,
            max_distance=max_distance)
    else:
        intersections = intersect_obj(raw, ray["ray"], registration["sourceToNativeRows"],
                                      max_distance=max_distance, selected_triangle=selected_triangle)
    _require(hashlib.sha256(mesh_path.read_bytes()).hexdigest() == digest
             and hashlib.sha256(Path(registration["path"]).read_bytes()).hexdigest()
                 == registration["sha256"], "mesh-or-registration-changed-during-raycast")
    result = {"schema": SCHEMA, "status": intersections["status"],
            "source": ray["source"], "identity": ray["identity"],
            "capturedAtUtc": ray["capturedAtUtc"], "ray": ray["ray"],
            "mesh": {"path": str(mesh_path), "sha256": digest,
                     "sourceFrame": registration["sourceFrame"]},
            "registration": {"path": registration["path"], "sha256": registration["sha256"],
                             "sourceToNativeRows": registration["sourceToNativeRows"],
                             "qualification": "candidate-only"},
            "surface": intersections, "inputSent": False, "movementEligible": False}
    if anchor_audit is not None:
        result["anchorAudit"] = anchor_audit
    if footprint is not None:
        result["pixelFootprint"] = footprint
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--pixel-x", type=int, required=True)
    parser.add_argument("--pixel-y", type=int, required=True)
    parser.add_argument("--mesh-obj", type=Path, required=True)
    parser.add_argument("--registration-json", type=Path, required=True,
                        help="SHA-pinned candidate-only source-to-native affine hypothesis")
    parser.add_argument("--max-distance", type=float, default=2000.0,
                        help="maximum ray depth in hypothetical native units (default 2000)")
    parser.add_argument("--pixel-selection-radius", type=int, default=0,
                        help="0..3 candidate-pixel cardinal footprint; 0 keeps single-ray output")
    parser.add_argument("--select-triangle-index", type=int,
                        help="exact one-based OBJ triangle ID from hits; display-only, no movement")
    parser.add_argument("--anchor-join-json", type=Path,
                        help="optional RiftWorld rack bracket; requires all anchor flags")
    parser.add_argument("--anchor-join-sha256", help="hash pin for rack bracket")
    parser.add_argument("--rack-report-json", type=Path,
                        help="RiftWorld rack report pinned by the bracket")
    parser.add_argument("--rack-report-sha256", help="hash pin for rack report")
    args = parser.parse_args(argv)
    try:
        result = pick_retained(args.observation, args.route, args.pixel_x, args.pixel_y,
                               args.mesh_obj, args.registration_json, args.max_distance,
                               selected_triangle=args.select_triangle_index,
                               anchor_join_path=args.anchor_join_json,
                               anchor_join_sha256=args.anchor_join_sha256,
                               rack_report_path=args.rack_report_json,
                               rack_report_sha256=args.rack_report_sha256,
                               pixel_selection_radius=args.pixel_selection_radius)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "reason": str(error),
                          "inputSent": False, "movementEligible": False}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
