"""Offline software projection of recorded XYZ waypoints onto a retained WGC frame.

No capture, process access, input, terrain query or occlusion inference occurs here.
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
from scripts.physical_turn_visual_pair import (client_frame_mapping,
    project_client_point_to_frame, verified_frame, require, unique_fields)
from scripts.waypoint_progress import write_json_atomic


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_fields,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite-json")))


def _path(value, parent):
    path = Path(value)
    return path if path.is_absolute() else parent / path


def _number(value):
    require(type(value) in (int, float) and math.isfinite(value), "recorded-coordinate-or-height-required")
    return value


def project(camera, xyz, mapping):
    native = physical._project_world_point(camera, xyz)
    result = {"worldXYZ": xyz, "clientProjection": native, "status": "withheld"}
    if native.get("status") != "available-candidate":
        result["reason"] = native.get("reason", native.get("status"))
        return result
    frame = project_client_point_to_frame(native, mapping)
    result["frameProjection"] = frame
    if not native.get("insideViewportCandidate") or not frame["insideClientCandidate"] or not frame["insideFrameCandidate"]:
        result["reason"] = "outside-client-or-viewport"
        return result
    result.update(status="drawn-candidate", pixel=[round(frame["frameX"]), round(frame["frameY"])])
    # Rounding must not move an otherwise in-bounds point outside the client.
    result["pixel"] = [min(mapping["clientLeft"] + mapping["clientWidth"] - 1,
                           max(mapping["clientLeft"], result["pixel"][0])),
                       min(mapping["clientTop"] + mapping["clientHeight"] - 1,
                           max(mapping["clientTop"], result["pixel"][1]))]
    return result


def render(observation_path, route_path, output):
    observation_path, route_path, output = map(lambda p: Path(p).resolve(), (observation_path, route_path, output))
    require(not output.exists() and output.parent.is_dir(), "fresh-output-directory-required")
    observation, route = _read(observation_path), _read(route_path)
    require(observation.get("status") == "verified-awaiting-visual-review"
            and observation.get("workflow") == "physical", "physical-observation-required")
    bracket = observation.get("nativeFacing", {})
    require(bracket.get("status") == "stable-bracket-candidate", "stable-native-frame-bracket-required")
    reports = [_read(_path(bracket[key], observation_path.parent)) for key in ("beforeOutput", "afterOutput")]
    values = [physical._native_values("facing", report) for report in reports]
    first, last = [report["observation"] for report in reports]
    image_path = _path(observation["image"], observation_path.parent)
    receipt_path = _path(observation["receipt"], observation_path.parent)
    frame, image, digest, receipt_digest = verified_frame(image_path, receipt_path)
    mapping = client_frame_mapping(frame)
    require(mapping.get("status") == "available-candidate", "available-client-frame-mapping-required")
    target, identity = observation["target"], reports[0]["identity"]
    host = frame["machine"]
    require(host.casefold() == socket.gethostname().casefold()
            and target["hostName"].casefold() == host.casefold()
            and observation["ownerHost"].casefold() == host.casefold(), "observation-host-mismatch")
    pinned = frame["targetBefore"]
    require(reports[1]["identity"] == identity
            and target["processId"] == identity["processId"] == pinned["pid"]
            and str(target["processStartUtcTicks"]) == str(identity["processStartUtcTicks"]) == str(pinned["startTicks"])
            and target["executableSha256"].casefold() == identity["executableSha256"].casefold() == pinned["sha256"].casefold()
            and target["hwnd"] == pinned["hwnd"]
            and digest.casefold() == observation["imageSha256"].casefold(), "native-frame-identity-mismatch")
    stamp = physical._utc_tick_order_key
    require(stamp(first["completedAtUtc"]) <= stamp(frame["capturedStartedAtUtc"])
            <= stamp(frame["capturedCompletedAtUtc"]) <= stamp(last["startedAtUtc"]), "native-frame-acquisition-order-mismatch")
    require((stamp(last["completedAtUtc"])[0] - stamp(first["startedAtUtc"])[0]).total_seconds() <= 5,
            "native-frame-bracket-too-long")
    for field in ("playerKeyDecimal", "playerEntityDecimal", "playerSystemDecimal", "rawBits", "entityPositionRawBits", "opticalCameraCandidate"):
        require(first.get(field) == last.get(field), "native-frame-bracket-changed")
    for source in ("primary", "secondary"):
        require(first["positionOrientationCandidate"][source]["rawBits"] == last["positionOrientationCandidate"][source]["rawBits"],
                "native-frame-bracket-changed")
    require(all(row.get("targetProjectionCameraStableCandidate") is True for row in (first, last)), "native-camera-not-stable")
    target_fields = ("status", "reason", "targetKey", "positionXYZCandidate", "screenPointCandidate", "guardStatus")
    selected_targets = [{key: (value.get("selectedTargetProjectionCandidate") or {}).get(key)
                         for key in target_fields} for value in values]
    require(selected_targets[0] == selected_targets[1], "target-changed-across-frame")
    camera = last.get("opticalCameraCandidate")
    require(values[-1].get("opticalCamera", {}).get("projectionAvailableCandidate") is True, "full-camera-projection-required")
    recording = route.get("recording", {})
    recorded_identity = recording.get("identity", {})
    recorded_runtime = recorded_identity.get("runtimeIdentity", recorded_identity)
    require(recording.get("complete") is True and recording.get("version") == 1, "complete-recorded-route-required")
    require(recorded_runtime.get("machine", "").casefold() == host.casefold()
            and recorded_runtime.get("gameBuildSha256", "").casefold() == identity["executableSha256"].casefold()
            and recorded_runtime.get("unitKey") == values[-1]["playerKey"], "route-host-build-player-identity-mismatch")
    points, heights = route.get("waypoints"), route.get("heights")
    require(isinstance(points, list) and 1 <= len(points) <= 20 and isinstance(heights, list)
            and len(heights) == len(points), "recorded-heights-required")
    rows = []
    for index, (point, height) in enumerate(zip(points, heights), 1):
        require(isinstance(point, list) and len(point) == 3 and isinstance(point[0], str), "invalid-recorded-waypoint")
        xyz = dict(x=_number(point[1]), y=_number(height), z=_number(point[2]))
        ground = project(camera, xyz, mapping)
        beacon = project(camera, dict(x=xyz["x"], y=xyz["y"] + 1.5, z=xyz["z"]), mapping)
        rows.append({"number": index, "label": point[0], "ground": ground, "beaconTop": beacon,
                     "beaconLineDrawn": ground["status"] == beacon["status"] == "drawn-candidate"})
    player = project(camera, values[-1]["positionXYZCandidate"], mapping)
    # Draw into a client-only layer so labels/marker radii cannot enter window chrome.
    left, top = mapping["clientLeft"], mapping["clientTop"]
    layer = image.crop((left, top, left + mapping["clientWidth"], top + mapping["clientHeight"]))
    draw = ImageDraw.Draw(layer)
    def pixel(row):
        x, y = row["pixel"]
        return x - left, y - top
    for row in rows:
        if row["ground"]["status"] != "drawn-candidate":
            continue
        x, y = pixel(row["ground"])
        if row["beaconLineDrawn"]:
            draw.line((x, y, *pixel(row["beaconTop"])), fill="#ffcc33", width=2)
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="#ffcc33", outline="black", width=1)
        label = f'{row["number"]}: {row["label"]}'
        draw.text((x + 8, y - 6), label, fill="#ffcc33", stroke_width=1, stroke_fill="black")
    if player["status"] == "drawn-candidate":
        x, y = pixel(player)
        draw.line((x - 7, y, x + 7, y), fill="#00ffff", width=2)
        draw.line((x, y - 7, x, y + 7), fill="#00ffff", width=2)
        draw.text((x + 9, y + 8), "Player ground", fill="#00ffff", stroke_width=1, stroke_fill="black")
    draw.text((6, 6), "OFFLINE PROJECTION CANDIDATE | depth / terrain not checked", fill="white", stroke_width=1, stroke_fill="black")
    image.paste(layer, (left, top))
    result = {"status": "offline-waypoint-projection-candidate", "machine": host,
              "identity": identity, "recordingIdentity": recorded_identity,
              "observation": str(observation_path), "route": str(route_path),
              "capturedAtUtc": frame["capturedCompletedAtUtc"],
              "nativeBefore": str(_path(bracket["beforeOutput"], observation_path.parent)),
              "nativeAfter": str(_path(bracket["afterOutput"], observation_path.parent)),
              "routeSha256": hashlib.sha256(route_path.read_bytes()).hexdigest(),
              "originalImage": str(image_path.resolve()), "imageSha256": digest,
              "receiptSha256": receipt_digest, "annotatedImage": str(output / "waypoints.png"),
              "report": str(output / "waypoints.json"), "clientFrameMapping": mapping,
              "points": rows, "playerGround": player, "inputSent": False,
              "limitations": ["Software projection onto a retained snapshot; not a live overlay.",
                  "Occlusion, depth and terrain not checked; markers may cover foreground objects.",
                  "Source world/zone identity unavailable; matching host/build/player does not establish world identity.",
                  "Recording provenance preserved; recording process epoch may differ from snapshot."]}
    output.mkdir()
    image.save(output / "waypoints.png", "PNG")
    write_json_atomic(output / "waypoints.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = render(args.observation, args.route, args.output)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2
    print(json.dumps({key: result[key] for key in ("status", "machine", "identity", "originalImage", "annotatedImage", "report")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
