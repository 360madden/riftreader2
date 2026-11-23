"""Offline WGC pixel rays through a SHA-pinned terrain + placed temple scene.

This tool does not read a live game or establish visible fragments, collision,
walkable floor, path clearance, or movement permission. Reuses RR2 ray/OBJ code.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_pixel_mesh_accel as mesh_accel
from scripts import physical_pixel_ray, physical_pixel_surface as surface

SCHEMA = "rr2.retained-wgc-composite-candidates/1"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_RECEIPT_BYTES = 32 * 1024
MAX_NATIVE_BYTES = 2 * 1024 * 1024
MAX_ANCHOR_BYTES = 32 * 1024
MAX_PIXELS = 32
MAX_BATCH_PIXELS = 256
MAX_STDOUT_REPORT_BYTES = 512 * 1024
SHA = re.compile(r"[0-9a-fA-F]{64}\Z")


def _read_pinned(path, expected, cap, label):
    surface._require(isinstance(expected, str) and SHA.fullmatch(expected) is not None,
                     label + "-expected-sha256-invalid")
    path = Path(path).resolve()
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    surface._require(0 < len(raw) <= cap, label + "-size-out-of-bounds")
    digest = hashlib.sha256(raw).hexdigest()
    surface._require(digest == expected.lower(), label + "-sha256-mismatch")
    return path, raw, digest


def _json_pinned(path, expected, cap, label):
    path, raw, digest = _read_pinned(path, expected, cap, label)
    obj = surface._strict_json(raw)
    surface._require(type(obj) is dict, label + "-object-required")
    return path, obj, digest


def _iso(value):
    surface._require(isinstance(value, str), "capture-timestamp-invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    surface._require(parsed.tzinfo is not None, "capture-timestamp-unzoned")
    return parsed


def load_frame(image_path, receipt_path, receipt_sha, native_before_path,
               native_before_sha, native_path, native_sha, *, expected_host,
               retained=False):
    """Admit a stable native/WGC/native camera bracket, including SHA-pinned copies."""
    from scripts import physical_rift
    from scripts.physical_turn_visual_pair import verified_frame

    receipt_path, receipt, receipt_digest = _json_pinned(
        receipt_path, receipt_sha, MAX_RECEIPT_BYTES, "wgc-receipt")
    before_path, native_before, before_digest = _json_pinned(
        native_before_path, native_before_sha, MAX_NATIVE_BYTES, "native-before")
    native_path, native, native_digest = _json_pinned(
        native_path, native_sha, MAX_NATIVE_BYTES, "native-after")
    surface._require(receipt.get("schemaVersion") == 1
                     and receipt.get("requestedBackend") == "wgc"
                     and receipt.get("status") == "unqualified-gpu-window-frame"
                     and receipt.get("machine") == expected_host
                     and physical_rift.valid_host_name(expected_host),
                     "wgc-host-or-backend-invalid")
    surface._require(receipt.get("inputSent") is False
                     and receipt.get("focusChangedByProbe") is False,
                     "wgc-unexpected-input-or-focus")
    target_before, target_after = receipt.get("targetBefore"), receipt.get("targetAfter")
    surface._require(type(target_before) is dict and type(target_after) is dict,
                     "wgc-target-identity-missing")
    keys = ("pid", "startTicks", "sha256", "hwnd", "processName")
    surface._require(all(target_before.get(k) == target_after.get(k) for k in keys)
                     and target_before.get("processName") == "rift_x64"
                     and type(target_before.get("pid")) is int
                     and target_before["pid"] > 0
                     and type(target_before.get("startTicks")) is int
                     and target_before["startTicks"] > 0
                     and type(target_before.get("hwnd")) is int
                     and target_before["hwnd"] > 0,
                     "wgc-target-changed-or-invalid")
    reports = (native_before, native)
    surface._require(all(report.get("status") == "complete"
                         and type(report.get("identity")) is dict
                         and type(report.get("observation")) is dict
                         for report in reports), "native-bracket-incomplete")
    n_id = native["identity"]
    surface._require(native_before["identity"] == n_id
                     and all(report["observation"].get("identity") == n_id
                             for report in reports)
                     and n_id.get("processId") == target_before["pid"]
                     and n_id.get("processStartUtcTicks") == target_before["startTicks"]
                     and str(n_id.get("executableSha256", "")).lower()
                         == str(target_before["sha256"]).lower(),
                     "native-wgc-identity-mismatch")
    # Reuse native facing schema/bits/owner validation; never read live memory.
    for report in reports:
        physical_rift._native_values("facing", report)
    first, last = (report["observation"] for report in reports)
    t0, t1 = _iso(first["startedAtUtc"]), _iso(first["completedAtUtc"])
    t2, t3 = (_iso(receipt[key]) for key in
              ("capturedStartedAtUtc", "capturedCompletedAtUtc"))
    t4, t5 = _iso(last["startedAtUtc"]), _iso(last["completedAtUtc"])
    bracket_seconds = (t5 - t0).total_seconds()
    surface._require(t0 < t1 <= t2 <= t3 <= t4 < t5
                     and 0 < bracket_seconds <= 5,
                     "native-before-wgc-after-bracket-invalid")
    for field in ("playerKeyDecimal", "playerEntityDecimal", "playerSystemDecimal",
                  "rawBits", "entityPositionRawBits", "opticalCameraCandidate"):
        surface._require(first.get(field) == last.get(field),
                         "native-frame-player-or-camera-changed")
    for name in ("primary", "secondary"):
        surface._require(
            first["positionOrientationCandidate"][name]["rawBits"]
            == last["positionOrientationCandidate"][name]["rawBits"],
            "native-frame-orientation-changed")
    camera = last.get("opticalCameraCandidate")
    surface._require(type(camera) is dict and camera.get("status") == "available-candidate"
                     and all(row.get("targetProjectionCameraStableCandidate") is True
                             and row.get("opticalCameraCandidate")
                                 == row.get("opticalCameraAfterTargetCandidate")
                             for row in (first, last)),
                     "native-frame-camera-unstable")
    # Existing verified_frame checks PNG decoding/IHDR dimensions, image byte count,
    # WGC receipt timing/quality and exact target-frame mapping.
    image_path = Path(image_path)
    retained_frame = None
    if retained:
        # A copied frame can use the original path recorded in the verified receipt.
        retained_frame = {"originalOutputPath": receipt.get("outputPath"),
                          "receiptSha256": receipt_digest.upper()}
    verified_receipt, decoded, image_digest, checked_receipt_sha = verified_frame(
        image_path, receipt_path, retained_frame=retained_frame)
    decoded.close()
    surface._require(verified_receipt == receipt
                     and checked_receipt_sha.lower() == receipt_digest
                     and image_digest.lower() == str(receipt.get("imageSha256", "")).lower(),
                     "validated-wgc-receipt-or-image-mismatch")
    image_path = image_path.resolve()
    mapping = receipt["clientFrameMapping"]
    return {"camera": camera, "mapping": mapping,
            "identity": {"host": expected_host, "pid": target_before["pid"],
                         "processStartUtcTicks": target_before["startTicks"],
                         "executableSha256": target_before["sha256"]},
            "source": {"imageSha256": image_digest.lower(),
                       "receiptSha256": receipt_digest,
                       "nativeBeforeSha256": before_digest,
                       "nativeAfterSha256": native_digest,
                       "capturedAtUtc": receipt["capturedCompletedAtUtc"],
                       "nativeBracketSeconds": bracket_seconds,
                       "nativeAfterDeltaSeconds": (t4 - t3).total_seconds(),
                       "imagePath": str(image_path),
                       "receiptPath": str(receipt_path),
                       "nativeBeforePath": str(before_path),
                       "nativeAfterPath": str(native_path)}}

def load_terrain(path, registration_path):
    mesh_path, raw, digest = surface._source_bytes(path, surface.MAX_MESH_BYTES,
                                                   "terrain-mesh")
    surface._require(mesh_path.suffix.lower() == ".obj", "terrain-must-be-obj")
    reg = surface.load_registration(registration_path, digest)
    vertices, faces = surface.parse_obj(raw, reg["sourceToNativeRows"])
    return {"name": "terrain", "vertices": vertices, "faces": faces,
            "source": {"meshPath": str(mesh_path), "meshSha256": digest,
                       "registrationSha256": reg["sha256"],
                       "sourceFrame": reg["sourceFrame"]},
            "pins": [(mesh_path, digest), (Path(reg["path"]), reg["sha256"])]}


def load_temple(path, anchor_path, anchor_sha, frame_identity):
    anchor_path, anchor, digest_anchor = _json_pinned(
        anchor_path, anchor_sha, MAX_ANCHOR_BYTES, "temple-anchor")
    src = anchor.get("source")
    surface._require(anchor.get("status") == "source-render-facet-proximity-not-physics-contact"
                     and anchor.get("host") == frame_identity["host"]
                     and type(src) is dict and src.get("renderOnly") is True
                     and src.get("sourcePlacementKey") == "world_7168_2816.cdr|223"
                     and src.get("sourceModel") == "A_F_temple_small_01.nif",
                     "temple-anchor-source-or-host-invalid")
    samples = anchor.get("samples")
    surface._require(isinstance(samples, list) and len(samples) >= 1
                     and all(type(s) is dict and s.get("pid") == frame_identity["pid"]
                             and s.get("processStartUtcTicks")
                                 == frame_identity["processStartUtcTicks"]
                             for s in samples), "temple-anchor-process-epoch-mismatch")
    source_matrix = src.get("sourceMatrixRowMajor")
    surface._require(type(source_matrix) is list and len(source_matrix) == 16
                     and all(type(v) in (float, int) and math.isfinite(v)
                             for v in source_matrix)
                     and source_matrix[12:] == [0, 0, 0, 1]
                     and src.get("sourceScale") == 1,
                     "temple-anchor-affine-invalid")
    rows = [source_matrix[0:4], source_matrix[4:8], source_matrix[8:12]]
    a, b, c = rows
    determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                   - a[1] * (b[0] * c[2] - b[2] * c[0])
                   + a[2] * (b[0] * c[1] - b[1] * c[0]))
    surface._require(abs(determinant) > 1e-12, "temple-anchor-matrix-singular")
    mesh_path, raw, digest = surface._source_bytes(path, surface.MAX_MESH_BYTES,
                                                   "temple-mesh")
    surface._require(mesh_path.suffix.lower() == ".obj"
                     and str(src.get("objSha256", "")).lower() == digest,
                     "temple-anchor-mesh-sha256-mismatch")
    vertices, faces = surface.parse_obj(raw, rows)
    return {"name": "temple-render", "vertices": vertices, "faces": faces,
            "source": {"meshPath": str(mesh_path), "meshSha256": digest,
                       "anchorPath": str(anchor_path), "anchorSha256": digest_anchor,
                       "sourcePlacementKey": src["sourcePlacementKey"],
                       "sourceToNativeRows": rows, "renderOnly": True},
            "pins": [(mesh_path, digest), (anchor_path, digest_anchor)]}


def compare_layers(ray, layers, max_distance=200.0, *, indices=None):
    """Depth-order first hits per layer; never infer optical visibility from them."""
    if indices is not None:
        surface._require(len(indices) == len(layers), "composite-index-count-mismatch")
    found, summary = [], []
    for layer_index, layer in enumerate(layers):
        result = (mesh_accel.intersect(indices[layer_index], ray,
                                       max_distance=max_distance)
                  if indices is not None else
                  surface.intersect_prepared(layer["vertices"], layer["faces"], ray,
                                             max_distance=max_distance))
        nearest = result["hits"][0] if result["hits"] else None
        candidate = ({"layer": layer["name"], "distanceNative": nearest["distanceNative"],
                      "candidateXYZ": nearest["candidateXYZ"],
                      "triangleIndex": nearest["triangleIndex"],
                      "meshGroup": nearest["meshGroup"]} if nearest else None)
        if candidate:
            found.append(candidate)
        summary.append({"layer": layer["name"], "candidateFirst": candidate,
                        "triangleCount": result["trianglesChecked"],
                        "hitCount": result["hitCount"]})
    found.sort(key=lambda candidate: (candidate["distanceNative"], candidate["layer"]))
    tied = len(found) >= 2 and abs(
        found[0]["distanceNative"] - found[1]["distanceNative"]) <= 1e-4
    return {"status": "candidate-hits" if found else "no-candidate-intersection",
            "candidateFirst": None if tied or not found else found[0],
            "orderedLayerCandidates": found, "layers": summary,
            "ambiguousFirstLayer": tied, "sourceCoverageComplete": False,
            "visibleSurfaceQualified": False, "occlusionQualified": False,
            "obstacleQualified": False, "floorQualified": False,
            "movementEligible": False}


def _validate_pixel_budget(count, max_pixels, accel_mode):
    """Fail before opening captured sources when an opt-in batch is invalid."""
    surface._require(type(accel_mode) is str and accel_mode in ("off", "bvh"),
                     "composite-accel-mode-invalid")
    surface._require(type(max_pixels) is int
                     and MAX_PIXELS <= max_pixels <= MAX_BATCH_PIXELS,
                     "composite-max-pixels-invalid")
    surface._require(max_pixels == MAX_PIXELS or accel_mode == "bvh",
                     "composite-large-batch-requires-bvh")
    surface._require(1 <= count <= max_pixels, "pixel-count-invalid")


def analyze_pixels(frame, layers, pixels, max_distance=200.0,
                   pixel_selection_radius=0, *, accel_mode="off",
                   max_pixels=MAX_PIXELS):
    _validate_pixel_budget(len(pixels), max_pixels, accel_mode)
    surface._require(type(pixel_selection_radius) is int
                     and 0 <= pixel_selection_radius <= surface.MAX_FOOTPRINT_RADIUS,
                     "pixel-selection-radius-invalid")
    seen = set()
    for x, y in pixels:
        surface._require((x, y) not in seen, "duplicate-pixel")
        seen.add((x, y))
    # The opt-in BVH uses the same exact narrowphase and local face ordinals.
    prepared_indices = ([mesh_accel.prepare(layer["vertices"], layer["faces"])
                         for layer in layers] if accel_mode == "bvh" else None)
    # Reuse the footprint algorithm on a joined, layer-labelled mesh.
    # Vertex indices are shifted only in this transient read-only representation.
    merged_vertices, merged_faces = [], []
    if pixel_selection_radius:
        for layer in layers:
            offset = len(merged_vertices)
            merged_vertices.extend(layer["vertices"])
            merged_faces.extend((tuple(i + offset for i in indices), layer["name"])
                                for indices, _ in layer["faces"])
        surface._require(len(merged_vertices) <= surface.MAX_VERTICES
                         and len(merged_faces) <= surface.MAX_TRIANGLES,
                         "composite-footprint-mesh-limit-exceeded")
    merged_index = (mesh_accel.prepare(merged_vertices, merged_faces)
                    if pixel_selection_radius and accel_mode == "bvh" else None)
    footprint_intersector = None
    if merged_index is not None:
        def footprint_intersector(_vertices, _faces, ray, *, max_distance):
            return mesh_accel.intersect(merged_index, ray, max_distance=max_distance)
    result = []
    for x, y in pixels:
        ray = physical_pixel_ray.pixel_ray(frame["camera"], frame["mapping"], x, y)
        record = {"pixel": [x, y],
                  "rayForwardReprojectionErrorPixels":
                      ray["forwardReprojectionErrorPixels"],
                  "surfaceCandidates": compare_layers(
                      ray, layers, max_distance, indices=prepared_indices)}
        if pixel_selection_radius:
            center = (footprint_intersector(
                merged_vertices, merged_faces, ray, max_distance=max_distance)
                if footprint_intersector is not None else
                surface.intersect_prepared(merged_vertices, merged_faces, ray,
                                           max_distance=max_distance))
            record["pixelFootprint"] = surface.sample_pixel_footprint(
                merged_vertices, merged_faces, frame["camera"], frame["mapping"],
                x, y, pixel_selection_radius, center_ray=ray,
                center_surface=center, max_distance=max_distance,
                intersector=footprint_intersector)
        result.append(record)
    # Refuse to return a clean result if a source changed during offline work.
    for layer in layers:
        for path, digest in layer["pins"]:
            surface._require(hashlib.sha256(Path(path).read_bytes()).hexdigest()
                             == digest, "scene-source-changed-during-query")
    for name, digest in (("image", "imageSha256"), ("receipt", "receiptSha256"),
                         ("nativeBefore", "nativeBeforeSha256"),
                         ("nativeAfter", "nativeAfterSha256")):
        source_path = Path(frame["source"][name + "Path"])
        surface._require(hashlib.sha256(source_path.read_bytes()).hexdigest()
                         == frame["source"][digest],
                         "frame-source-changed-during-query")
    return {"schema": SCHEMA, "status": "candidate-only",
            "identity": frame["identity"], "source": frame["source"],
            "sceneLayers": [{"name": layer["name"], **layer["source"]}
                            for layer in layers],
            "pixels": result, "inputSent": False, "movementEligible": False,
            "visibleSurfaceQualified": False, "physicalBlockingQualified": False,
            "navigationQualified": False,
            "qualification": "Offline render-mesh ray depths only; independent screen-space "
                             "depth, visual fragment identity, native collision response, "
                             "completeness and route clearance remain unverified."}


def render_preview(frame, report, output_path):
    """Optional separate annotated PNG for human review; never overwrite inputs."""
    from PIL import Image, ImageDraw, ImageFont

    source = Path(frame["source"]["imagePath"]).resolve()
    output = Path(output_path).resolve()
    surface._require(output.suffix.lower() == ".png" and output != source
                     and not output.exists() and output.parent.is_dir(),
                     "preview-output-must-be-new-png-in-existing-directory")
    surface._require(hashlib.sha256(source.read_bytes()).hexdigest()
                     == frame["source"]["imageSha256"],
                     "preview-source-image-changed")
    with Image.open(source) as original:
        image = original.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=17)
    draw.rectangle((0, 0, image.width - 1, 43), fill="#13202b")
    draw.text((12, 9),
              "RR2 OFFLINE CANDIDATES | no optical depth, blocking, or route proof",
              fill="#ffffff", font=font)
    for row in report["pixels"]:
        x, y = row["pixel"]
        result = row["surfaceCandidates"]
        hit = result["candidateFirst"]
        if hit is None:
            label, color = "UNKNOWN / AMBIGUOUS", "#ffda4d"
        else:
            kind = "TEMPLE" if hit["layer"] == "temple-render" else "TERRAIN"
            color = "#ff9a30" if kind == "TEMPLE" else "#52d7f9"
            label = f"{kind} {hit['distanceNative']:.2f}u (candidate)"
        footprint = row.get("pixelFootprint")
        if footprint is not None:
            group = hit["layer"] if hit is not None else None
            count = next((item["count"] for item in footprint["firstMeshGroupCounts"]
                          if item["meshGroup"] == group), 0)
            label += f" | {count}/{footprint['sampleCount']} neighbors"
        bbox = draw.textbbox((0, 0), label, font=font)
        width = bbox[2] - bbox[0]
        tx = max(2, min(image.width - width - 10, x + 14))
        ty = max(46, min(image.height - 28, y - 24))
        draw.line((x, y, tx, ty + 12), fill=color, width=2)
        draw.rectangle((tx - 3, ty - 2, tx + width + 5, ty + 24),
                       fill="#13202b", outline=color, width=1)
        draw.text((tx, ty), label, fill=color, font=font)
        draw.ellipse((x - 6, y - 6, x + 6, y + 6),
                     fill=color, outline="#101010", width=2)
    # Exclusive creation closes the check/create race: never overwrite another file.
    with output.open("xb") as stream:
        image.save(stream, format="PNG")
    return {"status": "offline-candidate-preview", "path": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "inputSent": False, "visibleSurfaceQualified": False,
            "movementEligible": False}

def _json_output_target(path):
    """Require a new JSON file inside an existing directory, before source reads."""
    output = Path(path).resolve()
    surface._require(output.suffix.lower() == ".json" and output.parent.is_dir()
                     and not output.exists(),
                     "output-json-must-be-new-json-in-existing-directory")
    return output


def _write_json_report(output, serialized):
    """Stage and verify bytes, then atomically publish without clobbering a target."""
    raw = serialized.encode("utf-8")
    expected_sha = hashlib.sha256(raw).hexdigest()
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=output.parent, delete=False,
                                         prefix=".rr2-composite-json-",
                                         suffix=".tmp") as stream:
            staged = Path(stream.name)
            written = stream.write(raw)
            surface._require(written == len(raw), "output-json-stage-short-write")
            stream.flush()
            os.fsync(stream.fileno())
        persisted = staged.read_bytes()
        persisted_sha = hashlib.sha256(persisted).hexdigest()
        surface._require(len(persisted) == len(raw) and persisted_sha == expected_sha,
                         "output-json-stage-verification-failed")
        # Hardlink on the same directory/volume is atomic and never replaces
        # an existing destination. If unsupported, fail; do not rename over it.
        try:
            os.link(staged, output)
        except OSError as error:
            raise OSError("output-json-atomic-publish-failed: " + str(error)) from error
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return {"schema": SCHEMA, "status": "candidate-only-json-written",
            "outputJson": {"status": "written", "path": str(output),
                           "sha256": persisted_sha, "byteCount": len(persisted)},
            "inputSent": False, "movementEligible": False,
            "visibleSurfaceQualified": False,
            "physicalBlockingQualified": False, "navigationQualified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--native-before", type=Path, required=True)
    parser.add_argument("--native-before-sha256", required=True)
    parser.add_argument("--native-after", type=Path, required=True)
    parser.add_argument("--native-after-sha256", required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--terrain-obj", type=Path, required=True)
    parser.add_argument("--terrain-registration", type=Path, required=True)
    parser.add_argument("--temple-obj", type=Path, required=True)
    parser.add_argument("--temple-anchor", type=Path, required=True)
    parser.add_argument("--temple-anchor-sha256", required=True)
    parser.add_argument("--pixel", type=int, nargs=2, action="append", required=True,
                        metavar=("X", "Y"), help="repeat for frame pixels (default cap 32)")
    parser.add_argument("--max-pixels", type=int, default=MAX_PIXELS,
                        help="opt-in pixel cap up to 256 requires --accel bvh; "
                             "default stays at 32")
    parser.add_argument("--max-distance", type=float, default=200.0)
    parser.add_argument("--pixel-selection-radius", type=int, default=0,
                        help="0..3 cardinal neighbor candidates per pixel; never depth proof")
    parser.add_argument("--accel", choices=("off", "bvh"), default="off",
                        help="opt-in offline BVH acceleration (default: off)")
    parser.add_argument("--preview-png", type=Path,
                        help="write an annotated candidate-only PNG to a new path")
    parser.add_argument("--output-json", type=Path,
                        help="write full candidate JSON to a new file; emit a small SHA receipt")
    args = parser.parse_args(argv)
    try:
        _validate_pixel_budget(len(args.pixel), args.max_pixels, args.accel)
        json_output = (_json_output_target(args.output_json)
                       if args.output_json is not None else None)
        frame = load_frame(args.image, args.receipt, args.receipt_sha256,
                           args.native_before, args.native_before_sha256,
                           args.native_after, args.native_after_sha256,
                           expected_host=args.expected_host)
        layers = [load_terrain(args.terrain_obj, args.terrain_registration),
                  load_temple(args.temple_obj, args.temple_anchor,
                              args.temple_anchor_sha256, frame["identity"])]
        result = analyze_pixels(frame, layers, args.pixel, args.max_distance,
                                args.pixel_selection_radius, accel_mode=args.accel,
                                max_pixels=args.max_pixels)
        serialized = json.dumps(result, allow_nan=False)
        if json_output is None:
            # Reject oversize stdout before an optional PNG preview creates a file.
            preview_reserve = 8192 if args.preview_png is not None else 0
            surface._require(len(serialized.encode("utf-8"))
                             <= MAX_STDOUT_REPORT_BYTES - preview_reserve,
                             "stdout-json-exceeds-512KiB: rerun with --output-json NEW.json")
        if args.preview_png is not None:
            result["preview"] = render_preview(frame, result, args.preview_png)
            serialized = json.dumps(result, allow_nan=False)
        if json_output is not None:
            print(json.dumps(_write_json_report(json_output, serialized),
                             allow_nan=False))
        else:
            surface._require(len(serialized.encode("utf-8")) <= MAX_STDOUT_REPORT_BYTES,
                             "stdout-json-exceeds-512KiB: rerun with --output-json NEW.json")
            print(serialized)
    except (ValueError, KeyError, OSError, TypeError, OverflowError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "reason": str(error),
                          "inputSent": False, "movementEligible": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
