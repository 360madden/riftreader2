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
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_pixel_ray, physical_pixel_surface as surface

SCHEMA = "rr2.retained-wgc-composite-candidates/1"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_RECEIPT_BYTES = 32 * 1024
MAX_NATIVE_BYTES = 2 * 1024 * 1024
MAX_ANCHOR_BYTES = 32 * 1024
MAX_PIXELS = 32
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


def load_frame(image_path, receipt_path, receipt_sha, native_path, native_sha,
               *, expected_host):
    """Admit only a preserved same-process WGC image/native-after candidate."""
    receipt_path, receipt, receipt_digest = _json_pinned(
        receipt_path, receipt_sha, MAX_RECEIPT_BYTES, "wgc-receipt")
    native_path, native, native_digest = _json_pinned(
        native_path, native_sha, MAX_NATIVE_BYTES, "native-after")
    surface._require(receipt.get("schemaVersion") == 1
                     and receipt.get("requestedBackend") == "wgc"
                     and receipt.get("status") == "unqualified-gpu-window-frame"
                     and receipt.get("machine") == expected_host
                     and expected_host in {"AMD-DESKTOP", "LEGION"},
                     "wgc-host-or-backend-invalid")
    surface._require(receipt.get("inputSent") is False
                     and receipt.get("focusChangedByProbe") is False,
                     "wgc-unexpected-input-or-focus")
    before, after = receipt.get("targetBefore"), receipt.get("targetAfter")
    surface._require(type(before) is dict and type(after) is dict,
                     "wgc-target-identity-missing")
    keys = ("pid", "startTicks", "sha256", "hwnd", "processName")
    surface._require(all(before.get(k) == after.get(k) for k in keys)
                     and before.get("processName") == "rift_x64"
                     and type(before.get("pid")) is int
                     and type(before.get("startTicks")) is int
                     and type(before.get("hwnd")) is int,
                     "wgc-target-changed-or-invalid")
    surface._require(native.get("status") == "complete"
                     and type(native.get("identity")) is dict
                     and type(native.get("observation")) is dict,
                     "native-after-incomplete")
    n_id = native["identity"]
    o_id = native["observation"].get("identity")
    surface._require(type(o_id) is dict and all(
        n_id.get(k) == o_id.get(k) for k in (
            "processId", "processStartUtcTicks", "executableSha256"))
        and n_id.get("processId") == before["pid"]
        and n_id.get("processStartUtcTicks") == before["startTicks"]
        and str(n_id.get("executableSha256", "")).lower()
            == str(before["sha256"]).lower(), "native-wgc-identity-mismatch")
    delta = (_iso(native["observation"]["startedAtUtc"])
             - _iso(receipt["capturedCompletedAtUtc"])).total_seconds()
    surface._require(0 <= delta <= 30, "native-after-wgc-bracket-invalid")
    surface._require(native["observation"].get("headingQualified") is False
                     and native["observation"].get("cameraYawQualified") is False,
                     "unexpected-native-facing-contract")
    camera = native["observation"].get("opticalCameraCandidate")
    mapping = receipt.get("clientFrameMapping")
    surface._require(type(camera) is dict and type(mapping) is dict
                     and mapping.get("frameWidth") == receipt.get("frameWidth")
                     and mapping.get("frameHeight") == receipt.get("frameHeight"),
                     "wgc-camera-or-mapping-invalid")
    image_path = Path(image_path).resolve()
    surface._require(image_path == Path(receipt.get("outputPath", "")).resolve(),
                     "wgc-image-path-mismatch")
    image_sha = receipt.get("imageSha256")
    _, raw_image, image_digest = _read_pinned(
        image_path, image_sha, MAX_IMAGE_BYTES, "wgc-image")
    surface._require(raw_image.startswith(b"\x89PNG\r\n\x1a\n"),
                     "wgc-image-not-png")
    return {"camera": camera, "mapping": mapping,
            "identity": {"host": expected_host, "pid": before["pid"],
                         "processStartUtcTicks": before["startTicks"],
                         "executableSha256": before["sha256"]},
            "source": {"imageSha256": image_digest,
                       "receiptSha256": receipt_digest,
                       "nativeAfterSha256": native_digest,
                       "capturedAtUtc": receipt["capturedCompletedAtUtc"],
                       "nativeAfterDeltaSeconds": delta,
                       "imagePath": str(image_path),
                       "receiptPath": str(receipt_path),
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


def compare_layers(ray, layers, max_distance=200.0):
    """Depth-order first hits per layer; never infer optical visibility from them."""
    found, summary = [], []
    for layer in layers:
        result = surface.intersect_prepared(layer["vertices"], layer["faces"], ray,
                                            max_distance=max_distance)
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


def analyze_pixels(frame, layers, pixels, max_distance=200.0,
                   pixel_selection_radius=0):
    surface._require(1 <= len(pixels) <= MAX_PIXELS, "pixel-count-invalid")
    surface._require(type(pixel_selection_radius) is int
                     and 0 <= pixel_selection_radius <= surface.MAX_FOOTPRINT_RADIUS,
                     "pixel-selection-radius-invalid")
    seen = set()
    for x, y in pixels:
        surface._require((x, y) not in seen, "duplicate-pixel")
        seen.add((x, y))
    # Reuse the existing footprint algorithm on a joined, layer-labelled mesh.
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
    result = []
    for x, y in pixels:
        ray = physical_pixel_ray.pixel_ray(frame["camera"], frame["mapping"], x, y)
        record = {"pixel": [x, y],
                  "rayForwardReprojectionErrorPixels":
                      ray["forwardReprojectionErrorPixels"],
                  "surfaceCandidates": compare_layers(ray, layers, max_distance)}
        if pixel_selection_radius:
            center = surface.intersect_prepared(
                merged_vertices, merged_faces, ray, max_distance=max_distance)
            record["pixelFootprint"] = surface.sample_pixel_footprint(
                merged_vertices, merged_faces, frame["camera"], frame["mapping"],
                x, y, pixel_selection_radius, center_ray=ray,
                center_surface=center, max_distance=max_distance)
        result.append(record)
    # Refuse to return a clean result if a source changed during offline work.
    for layer in layers:
        for path, digest in layer["pins"]:
            surface._require(hashlib.sha256(Path(path).read_bytes()).hexdigest()
                             == digest, "scene-source-changed-during-query")
    for name, digest in (("image", "imageSha256"), ("receipt", "receiptSha256"),
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
    image.save(output, format="PNG")
    return {"status": "offline-candidate-preview", "path": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "inputSent": False, "visibleSurfaceQualified": False,
            "movementEligible": False}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--native-after", type=Path, required=True)
    parser.add_argument("--native-after-sha256", required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--terrain-obj", type=Path, required=True)
    parser.add_argument("--terrain-registration", type=Path, required=True)
    parser.add_argument("--temple-obj", type=Path, required=True)
    parser.add_argument("--temple-anchor", type=Path, required=True)
    parser.add_argument("--temple-anchor-sha256", required=True)
    parser.add_argument("--pixel", type=int, nargs=2, action="append", required=True,
                        metavar=("X", "Y"), help="repeat for 1..32 frame pixel pairs")
    parser.add_argument("--max-distance", type=float, default=200.0)
    parser.add_argument("--pixel-selection-radius", type=int, default=0,
                        help="0..3 cardinal neighbor candidates per pixel; never depth proof")
    parser.add_argument("--preview-png", type=Path,
                        help="write an annotated candidate-only PNG to a new path")
    args = parser.parse_args(argv)
    try:
        frame = load_frame(args.image, args.receipt, args.receipt_sha256,
                           args.native_after, args.native_after_sha256,
                           expected_host=args.expected_host)
        layers = [load_terrain(args.terrain_obj, args.terrain_registration),
                  load_temple(args.temple_obj, args.temple_anchor,
                              args.temple_anchor_sha256, frame["identity"])]
        result = analyze_pixels(frame, layers, args.pixel, args.max_distance,
                                args.pixel_selection_radius)
        if args.preview_png is not None:
            result["preview"] = render_preview(frame, result, args.preview_png)
    except (ValueError, KeyError, OSError, TypeError, OverflowError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "reason": str(error),
                          "inputSent": False, "movementEligible": False}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
