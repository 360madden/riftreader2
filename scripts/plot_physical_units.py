"""Project stable saved nearby-unit observations onto their retained WGC frame.

Offline only: no process access, capture, selection or input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import socket
import sys

from PIL import ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift as physical
from scripts.plot_physical_waypoints import project, _path
from scripts.physical_turn_visual_pair import (
    client_frame_mapping, verified_frame, require, unique_fields)
from scripts.waypoint_progress import write_json_atomic


def _saved(path):
    path = Path(path).resolve()
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 8 * 1024 * 1024,
            "saved-json-missing-or-oversized")
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_fields,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite-json")))
    require(type(value) is dict, "saved-json-object-required")
    return value, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def render(bracket_path, output, *, limit=18, max_distance=35):
    require(type(limit) is int and 1 <= limit <= 40, "limit-must-be-1-through-40")
    require(type(max_distance) in (int, float) and math.isfinite(max_distance)
            and 0 < max_distance <= 100, "max-distance-must-be-positive-through-100")
    bracket_path, output = Path(bracket_path).resolve(), Path(output).resolve()
    require(not output.exists() and output.parent.is_dir(), "fresh-output-directory-required")
    bracket, bracket_source = _saved(bracket_path)
    sides = [bracket[name] for name in ("before", "after")]
    reports, sources = [], []
    for side in sides:
        require(side.get("status") == "complete" and side.get("workflow") == "physical"
                and side.get("nativeRead") == "unit-positions", "complete-unit-scan-required")
        report, source = _saved(_path(side["nativeOutput"], bracket_path.parent))
        reports.append(report)
        sources.append(source)
    values = [physical._native_values("unit-positions", report) for report in reports]
    first, last = [report["observation"] for report in reports]
    capture = bracket["frame"]
    require(capture.get("status") == "verified-awaiting-visual-review"
            and capture.get("workflow") == "physical" and capture.get("foregroundMayChange") is False,
            "focus-neutral-physical-frame-required")
    image_path = _path(capture["image"], bracket_path.parent).resolve()
    receipt_path = _path(capture["receipt"], bracket_path.parent).resolve()
    frame, image, image_sha, receipt_sha = verified_frame(image_path, receipt_path)
    mapping = client_frame_mapping(frame)
    require(mapping.get("status") == "available-candidate", "available-client-frame-mapping-required")
    host, identity, pinned = frame["machine"], first["identity"], frame["targetBefore"]
    require(host.casefold() == socket.gethostname().casefold()
            and host.upper() in physical.SUPPORTED_HOSTS
            and frame["requestedBackend"] == "wgc", "frame-host-or-backend-mismatch")
    require(last["identity"] == identity, "native-frame-identity-mismatch")
    for side in (*sides, capture):
        target = side["target"]
        require(target["hostName"].casefold() == host.casefold()
                and side.get("ownerHost", host).casefold() == host.casefold(),
                "native-frame-host-mismatch")
        require(target["processId"] == identity["processId"] == pinned["pid"]
                and str(target["processStartUtcTicks"]) == str(identity["processStartUtcTicks"]) == str(pinned["startTicks"])
                and target["executableSha256"].casefold() == identity["executableSha256"].casefold() == pinned["sha256"].casefold()
                and target["hwnd"] == pinned["hwnd"], "native-frame-identity-mismatch")
    require(capture["imageSha256"].casefold() == image_sha.casefold(), "capture-image-hash-mismatch")
    stamp = physical._utc_tick_order_key
    require(stamp(first["completedAtUtc"]) <= stamp(frame["capturedStartedAtUtc"])
            <= stamp(frame["capturedCompletedAtUtc"]) <= stamp(last["startedAtUtc"]),
            "native-frame-acquisition-order-mismatch")
    start, end = stamp(first["startedAtUtc"]), stamp(last["completedAtUtc"])
    span = (end[0] - start[0]).total_seconds() + (end[1] - start[1]) / 10000000
    require(0 < span <= 5, "native-frame-bracket-too-long")
    cameras = [row[name] for row in (first, last)
               for name in ("opticalCameraCandidate", "opticalCameraAfterCandidate")]
    require(all(row["cameraStableCandidate"] is True for row in (first, last))
            and cameras[0].get("status") == "available-candidate"
            and all(camera == cameras[0] for camera in cameras[1:]),
            "native-camera-bracket-changed")
    require(first["selfKey"] == last["selfKey"]
            and first["selfPositionRawBits"] == last["selfPositionRawBits"],
            "native-self-bracket-changed")
    require(values[-1]["opticalCamera"].get("projectionAvailableCandidate") is True,
            "full-camera-projection-required")
    before_rows = {row["unitKey"]: row for row in first["rows"]}
    after_rows = {row["unitKey"]: row for row in last["rows"]}
    projected = {row["unitKey"]: row for row in values[-1]["units"]}
    rows = []
    for key in sorted(before_rows.keys() | after_rows.keys(), key=int):
        a, b = before_rows.get(key), after_rows.get(key)
        result = {"unitKey": key, "unitIdCandidate": (b or a)["unitIdCandidate"], "status": "withheld",
                  "horizontalDistanceCandidate": (b or a)["horizontalDistanceCandidate"],
                  "sourcePositions": {name: None if native is None else {
                      "worldXYZ": native["positionCandidate"], "rawBits": native["rawBits"],
                      "entityAddressDecimal": native["entityAddressDecimal"],
                      "sampledAtUtc": native["completedAtUtc"]}
                      for name, native in (("before", a), ("after", b))}}
        if key == last["selfKey"]:
            result["reason"] = "self-excluded"
        elif a is None or b is None:
            result["reason"] = "unit-not-present-in-both-scans"
        elif a["entityAddressDecimal"] != b["entityAddressDecimal"]:
            result["reason"] = "unit-entity-owner-changed-across-frame"
        elif a["rawBits"] != b["rawBits"]:
            result["reason"] = "unit-position-changed-across-frame"
        else:
            unit = projected[key]
            result.update(worldXYZ=unit["positionXYZCandidate"], rawBits=b["rawBits"],
                          horizontalDistanceCandidate=unit["horizontalDistanceCandidate"],
                          sampledAtUtc=b["completedAtUtc"])
            if unit["horizontalDistanceCandidate"] > max_distance:
                result["reason"] = "outside-max-distance"
            else:
                projection = project(cameras[0], unit["positionXYZCandidate"], mapping)
                result["projection"] = projection
                result["reason"] = projection.get("reason")
                if projection["status"] == "drawn-candidate":
                    result.update(status="eligible-candidate", pixel=projection["pixel"])
                    result.pop("reason", None)
        rows.append(result)
    rows.sort(key=lambda row: (row["horizontalDistanceCandidate"], int(row["unitKey"])))
    eligible = sorted((row for row in rows if row["status"] == "eligible-candidate"),
                      key=lambda row: (row["horizontalDistanceCandidate"], int(row["unitKey"])))
    for index, row in enumerate(eligible):
        if index >= limit:
            row.update(status="withheld", reason="marker-limit")
        else:
            row.update(status="drawn-candidate", number=index + 1,
                       label=f'{index + 1} {row["unitIdCandidate"][-6:]}')
    left, top = mapping["clientLeft"], mapping["clientTop"]
    layer = image.crop((left, top, left + mapping["clientWidth"], top + mapping["clientHeight"]))
    draw = ImageDraw.Draw(layer)
    for row in eligible[:limit]:
        x, y = row["pixel"][0] - left, row["pixel"][1] - top
        draw.line((x - 6, y, x + 6, y), fill="#ffcc33", width=2)
        draw.line((x, y - 6, x, y + 6), fill="#ffcc33", width=2)
        draw.text((x + 8, y - 10), row["label"], fill="#ffcc33", stroke_width=1, stroke_fill="black")
    draw.text((6, 6), "OFFLINE UNIT CANDIDATES | stored positions; depth not checked",
              fill="white", stroke_width=1, stroke_fill="black")
    image.paste(layer, (left, top))
    result = {"status": "offline-unit-projection-candidate", "machine": host, "identity": identity,
              "frameIdentity": pinned, "capturedAtUtc": frame["capturedCompletedAtUtc"],
              "bracketSpanSeconds": span, "sourceBracket": bracket_source,
              "sourceNativeBefore": sources[0], "sourceNativeAfter": sources[1],
              "sourceReceipt": {"path": str(receipt_path), "sha256": receipt_sha},
              "originalImage": str(image_path), "imageSha256": image_sha,
              "annotatedImage": str(output / "units.png"), "report": str(output / "units.json"),
              "limit": limit, "maxDistance": max_distance, "clientFrameMapping": mapping,
              "scanCoverage": [{name: value[name] for name in (
                  "unitsExamined", "positionsFound", "unitsWithoutPosition", "unavailableUnits",
                  "unavailableChains", "bucketsExamined", "bucketCount", "startBucket", "unitLimitReached")}
                  for value in values],
              "drawnCount": min(limit, len(eligible)), "rows": rows, "inputSent": False,
              "qualification": ["Retained snapshot projection candidate; not a live overlay.",
                  "Stored unit positions may be stale; unchanged values do not prove freshness.",
                  "Unit names and types unavailable; labels do not identify NPCs or dummies.",
                  "Depth, occlusion, terrain, obstacles and world/zone identity not checked.",
                  "Bounded loaded-unit subset; no complete world coverage or restart qualification."]}
    output.mkdir()
    image.save(output / "units.png", "PNG")
    write_json_atomic(output / "units.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bracket", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=18)
    parser.add_argument("--max-distance", type=float, default=35)
    args = parser.parse_args(argv)
    try:
        result = render(args.bracket, args.output, limit=args.limit, max_distance=args.max_distance)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2
    print(json.dumps({key: result[key] for key in ("status", "drawnCount", "annotatedImage", "report")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
