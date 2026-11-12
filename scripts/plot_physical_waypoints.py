"""Offline software projection of recorded XYZ waypoints onto a retained WGC frame.

No capture, process access, input, terrain query or occlusion inference occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import socket
import sys

from PIL import Image, ImageDraw, ImageStat

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
    return _render_validated(observation_path, route_path, output, route, host=host, identity=identity,
        values=values[-1], camera=camera, mapping=mapping, image=image, image_path=image_path, digest=digest,
        receipt_digest=receipt_digest, captured_at=frame["capturedCompletedAtUtc"],
        native_before=_path(bracket["beforeOutput"], observation_path.parent),
        native_after=_path(bracket["afterOutput"], observation_path.parent))


def render_desktop_pair(pair_path, route_path, output):
    """Admit a retained DXcam/native event pair without constructing a WGC receipt."""
    from scripts.probe_dxcam import _output
    from scripts.probe_dxcam_native_pair import compare
    from scripts.plot_physical_units import _saved

    pair_path, route_path, output = (Path(p).resolve() for p in (pair_path, route_path, output))
    require(not output.exists() and output.parent.is_dir(), "fresh-output-directory-required")
    pair, pair_source = _saved(pair_path)
    route = _read(route_path)
    require(pair.get("status") == "stable-native-composite-event-candidate"
            and pair.get("diagnosticKind") == "dxcam-native-event-pair/1"
            and pair.get("inputSent") is False and pair.get("focusChanged") is False
            and pair.get("cleanupErrors") == [], "stable-desktop-event-pair-required")
    host = pair.get("machine")
    require(host == "AMD-DESKTOP" and host.casefold() == socket.gethostname().casefold(), "desktop-pair-host-mismatch")
    target = pair.get("targetBefore")
    require(isinstance(target, dict) and target == pair.get("targetAfter")
            and target.get("hostName", "").casefold() == host.casefold()
            and type(target.get("hwnd")) is int and target["hwnd"] > 0
            and type(target.get("processId")) is int and target["processId"] > 0
            and isinstance(target.get("executablePath"), str) and target["executablePath"], "desktop-pair-target-changed")
    require(isinstance(target.get("processStartUtcTicks"), str) and target["processStartUtcTicks"].isdecimal()
            and int(target["processStartUtcTicks"]) > 0 and isinstance(target.get("executableSha256"), str)
            and len(target["executableSha256"]) == 64
            and all(c in "0123456789abcdefABCDEF" for c in target["executableSha256"]), "invalid-desktop-process-identity")
    snapshot = pair.get("snapshotBefore")
    require(isinstance(snapshot, dict) and snapshot == pair.get("snapshotAfter")
            and snapshot.get("foreground") is True and pair["snapshotAfter"].get("foreground") is True,
            "desktop-pair-snapshot-changed")
    rect = snapshot.get("clientRect")
    require(isinstance(rect, list) and len(rect) == 4 and all(type(n) is int for n in rect)
            and 0 < rect[2] <= 4096 and 0 < rect[3] <= 2160, "invalid-desktop-client")
    selected = pair.get("selectedOutput")
    require(isinstance(selected, dict) and isinstance(selected.get("desktopRect"), list)
            and len(selected["desktopRect"]) == 4 and all(type(n) is int for n in selected["desktopRect"])
            and all(type(selected.get(k)) is int and selected[k] >= 0 for k in ("deviceIndex", "outputIndex"))
            and selected.get("rotationDegrees") == 0 and isinstance(pair.get("requestedDisplay"), str),
            "invalid-selected-desktop-output")
    _, crop = _output([selected], pair["requestedDisplay"], rect)
    require(crop == pair.get("outputLocalCrop"), "desktop-client-crop-mismatch")

    def integer(value):
        require(type(value) is int and value >= 0, "invalid-desktop-clock-integer")
        return value

    frequency = integer(pair["clockBefore"]["frequency"])
    require(frequency > 0 and integer(pair["clockAfter"]["frequency"]) == frequency, "desktop-clock-frequency-changed")
    calibration_edges = []
    for calibration in (pair["clockBefore"], pair["clockAfter"]):
        require(type(calibration.get("orderingAllowanceTicks")) is int and calibration["orderingAllowanceTicks"] == 1
                and isinstance(calibration.get("samples"), list) and len(calibration["samples"]) == 8,
                "invalid-desktop-clock-calibration")
        end = None
        for sample in calibration["samples"]:
            begin, perf, finish = (integer(sample[k]) for k in ("qpcBefore", "perfCounterNs", "qpcAfter"))
            require(begin <= finish and (end is None or begin >= end)
                    and (begin - 1) * 10**9 <= perf * frequency <= (finish + 1) * 10**9,
                    "desktop-clock-calibration-incompatible")
            require(type(sample.get("bracketWidthSeconds")) in (int, float)
                    and math.isclose(sample["bracketWidthSeconds"], (finish-begin)/frequency, abs_tol=1e-12),
                    "desktop-clock-calibration-width-mismatch")
            end = finish
        calibration_edges.append((calibration["samples"][0]["qpcBefore"], end))

    def event_values(event):
        ticks, begin, end = (integer(event[k]) for k in ("backendTicks", "qpcPeekBefore", "qpcPeekAfter"))
        seconds, ages = event.get("backendSeconds"), event.get("backendEventAgeBoundsSeconds")
        require(ticks > 0 and begin <= end and ticks <= end + 1
                and type(seconds) in (int, float) and math.isfinite(seconds)
                and abs(seconds - ticks/frequency) < 1e-8, "invalid-desktop-event-timebase")
        expected = [max(0, (begin-ticks-1)/frequency), (end-ticks+1)/frequency]
        require(isinstance(ages, list) and len(ages) == 2
                and all(type(v) in (int, float) and math.isfinite(v) for v in ages)
                and all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(ages, expected))
                and 0 <= ages[0] <= ages[1] <= 5, "desktop-event-age-mismatch")
        return ticks, begin, end

    warm_ticks, warm_begin, warm_end = event_values(pair["warmupFrame"])
    ticks, peek_begin, peek_end = event_values(pair["event"])
    before, fence, accepted, after, returned = (integer(pair["qpcMarks"][k]) for k in
        ("nativeBeforeInvoked", "nativeBeforeReturnedFence", "frameAccepted", "nativeAfterInvoked", "nativeAfterReturned"))
    span = pair.get("nativeBracketSpanSeconds")
    require(calibration_edges[0][1] <= warm_begin <= warm_end <= before <= fence
            and fence + 1 < ticks <= peek_end + 1 and fence <= peek_begin <= peek_end <= accepted <= after <= returned
            and returned <= calibration_edges[1][0] and returned-before <= 5*frequency
            and type(span) in (int, float) and math.isfinite(span) and 0 <= span <= 5
            and span + 2/frequency >= (returned-before)/frequency,
            "desktop-native-event-order-or-span-invalid")
    sources = pair.get("nativeSources")
    require(isinstance(sources, list) and len(sources) == 2, "desktop-native-sources-required")
    reports, paths = [], []
    for source, key in zip(sources, ("nativeBeforeOutput", "nativeAfterOutput")):
        path = _path(source["path"], pair_path.parent).resolve()
        require(path == _path(pair[key], pair_path.parent).resolve(), "desktop-native-source-path-mismatch")
        report, actual = _saved(path)
        require(actual["sha256"].casefold() == source["sha256"].casefold(), "desktop-native-source-hash-mismatch")
        reports.append(report)
        paths.append(path)
    values = compare(reports, target)
    first, last = (report["observation"] for report in reports)
    stamp = physical._utc_tick_order_key
    require(0 <= (stamp(last["completedAtUtc"])[0] - stamp(first["startedAtUtc"])[0]).total_seconds() <= 5,
            "desktop-native-UTC-bracket-too-long")
    image_path = _path(pair["image"], pair_path.parent).resolve()
    require(image_path.is_file() and not image_path.is_symlink() and image_path.stat().st_size <= 12*1024*1024,
            "desktop-image-missing-or-oversized")
    raw = image_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest.casefold() == pair["imageSha256"].casefold(), "desktop-image-hash-mismatch")
    with Image.open(BytesIO(raw)) as original:
        require(original.format == "PNG" and original.mode == "RGB" and original.size == tuple(rect[2:]),
                "desktop-image-format-or-size-mismatch")
        image = original.convert("RGB")
    stats = ImageStat.Stat(image.resize((96, 64)))
    require(max(stats.extrema[i][1] for i in range(3)) > 16 and max(stats.var) > 1,
            "desktop-image-blank-or-uninformative")
    mapping = dict(status="available-candidate", coordinateSpace="top-left-frame-physical-pixels",
                   basis="verified-desktop-client-crop", frameWidth=rect[2], frameHeight=rect[3],
                   clientLeft=0, clientTop=0, clientWidth=rect[2], clientHeight=rect[3])
    return _render_validated(pair_path, route_path, output, route, host=host, identity=reports[0]["identity"],
        values=values, camera=last["opticalCameraCandidate"], mapping=mapping, image=image,
        image_path=image_path, digest=digest, receipt_digest=pair_source["sha256"], captured_at=None,
        native_before=paths[0], native_after=paths[1], source_metadata={
            "sourceKind": "desktop-composite-event-candidate",
            "capturedAtUtcKind": "unavailable-exact-desktop-event-utc",
            "captureUpperBoundAtUtc": last["startedAtUtc"],
            "desktopEvent": pair["event"], "desktopQpcMarks": pair["qpcMarks"],
            "desktopSourceLimitations": pair.get("limitations", [])})


def _render_validated(observation_path, route_path, output, route, *, host, identity, values,
                      camera, mapping, image, image_path, digest, receipt_digest, captured_at,
                      native_before, native_after, source_metadata=None):
    """Shared projection/drawing only after the selected source's own admission."""
    recording = route.get("recording", {})
    recorded_identity = recording.get("identity", {})
    recorded_runtime = recorded_identity.get("runtimeIdentity", recorded_identity)
    require(recording.get("complete") is True and recording.get("version") == 1, "complete-recorded-route-required")
    require(recorded_runtime.get("machine", "").casefold() == host.casefold()
            and recorded_runtime.get("gameBuildSha256", "").casefold() == identity["executableSha256"].casefold()
            and recorded_runtime.get("unitKey") == values["playerKey"], "route-host-build-player-identity-mismatch")
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
    player = project(camera, values["positionXYZCandidate"], mapping)
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
              "capturedAtUtc": captured_at,
              "nativeBefore": str(native_before), "nativeAfter": str(native_after),
              "routeSha256": hashlib.sha256(route_path.read_bytes()).hexdigest(),
              "originalImage": str(image_path.resolve()), "imageSha256": digest,
              "receiptSha256": receipt_digest, "annotatedImage": str(output / "waypoints.png"),
              "report": str(output / "waypoints.json"), "clientFrameMapping": mapping,
              "points": rows, "playerGround": player, "inputSent": False,
              "limitations": ["Software projection onto a retained snapshot; not a live overlay.",
                  "Occlusion, depth and terrain not checked; markers may cover foreground objects.",
                  "Source world/zone identity unavailable; matching host/build/player does not establish world identity.",
                  "Recording provenance preserved; recording process epoch may differ from snapshot."]}
    result.update(source_metadata or {})
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
