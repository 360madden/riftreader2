"""Export preserved route/native/WGC evidence to a new offline Rerun recording.

No viewer, server, capture, process access, input or inferred camera calibration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import plot_physical_waypoints as plot
from scripts.live_physical_waypoints import load_route

LIMITATIONS = [
    "Offline retained evidence; not a live overlay or qualified navigation map.",
    "Native and image timestamps remain distinct; a stable bracket is not simultaneous capture.",
    "No pinhole calibration or world-to-camera convention is invented; 2D points reuse RR2 projection.",
    "World/zone identity unavailable; matching host/build/player does not prove same world.",
    "Occlusion, depth and terrain not checked; original recording provenance preserved.",
    "Viewer timeline carry-forward is display behavior, not a new observation.",
    "Initial viewer playback follows latest evidence; pause/scrub to inspect earlier samples.",
    "3D view uses +Y up for height; this display orientation is not a camera calibration.",
    "Optional camera rays use display clip-W extent 20, not measured scene depth or game near/far planes.",
]


def timestamp_ns(value):
    parsed, remainder = plot.physical._utc_tick_order_key(value)
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return ((delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1000 + remainder * 100


def native_view_rays(camera):
    """Invert screen X/Y/W only; extent 20 is display geometry, never scene depth."""
    result = {"status": "unavailable", "clipWDisplayExtent": 20.,
              "label": "Native projection view rays — display extent 20 (clip W); no scene depth/occlusion",
              "qualification": "Screen-edge visualization rays to an explicit clip-W display plane; not game near/far clipping planes, terrain or a camera calibration."}
    try:
        import numpy as np
    except ImportError:
        return dict(result, reason="numpy-unavailable")
    try:
        optical = plot.physical._optical_camera_values(camera)
        plot.require(optical is not None and optical.get("status") == "available-candidate"
                     and optical.get("projectionAvailableCandidate") is True, "native-camera-projection-unavailable")
        transform = np.array([struct.unpack("<f", struct.pack("<I", bit))[0]
                              for bit in camera["rawBits"]], dtype=np.float64)
        matrix, viewport = plot.physical._optical_projection_values(camera, transform)
        matrix = np.array(matrix, dtype=np.float64).reshape(4, 4)
        origin, eye = transform[12:15], transform[9:12] + transform[12:15]
        plot.require(np.isfinite(matrix).all() and np.isfinite(origin).all() and np.isfinite(eye).all(),
                     "nonfinite-native-view-geometry")
        axes, translation = matrix[[0, 1, 3], :3], matrix[[0, 1, 3], 3]
        condition = float(np.linalg.cond(axes))
        plot.require(math.isfinite(condition) and condition <= 1e6, "unstable-native-view-inverse")
        implied_eye = np.linalg.solve(axes, -translation) + origin
        eye_error = float(np.max(np.abs(implied_eye - eye)))
        plot.require(math.isfinite(eye_error) and eye_error <= .001, "native-view-implied-eye-mismatch")
        corners = []
        for x, y in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
            clip_xyw = np.array([x * 20., y * 20., 20.])
            world = np.linalg.solve(axes, clip_xyw - translation) + origin
            plot.require(np.isfinite(world).all() and np.allclose(
                axes @ (world - origin) + translation, clip_xyw, rtol=1e-8, atol=1e-7),
                "native-view-inverse-roundtrip-failed")
            corners.append(world.tolist())
        left, right, top, bottom = viewport
        result.update(status="available-candidate", nativeEyeXYZ=eye.tolist(), cornersXYZ=corners,
            lineStrips=[[eye.tolist(), corner] for corner in corners] + [corners + [corners[0]]],
            viewportRectNormalized=[left, 1-top, right, 1-bottom],
            inverseConditionNumber=condition, impliedEyeMaximumError=eye_error)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, np.linalg.LinAlgError) as error:
        result.update(reason=str(error) or type(error).__name__)
    return result


class RerunSink:
    """Small adapter using the pinned 0.43.1 RecordingStream API only."""
    def __init__(self, path):
        plot.require(version("rerun-sdk") == "0.43.1", "rerun-sdk-0.43.1-required")
        # Official 0.43.1 re_analytics::disabled_reason: CI disables native
        # analytics unless FORCE_RERUN_ANALYTICS overrides it. Process only.
        self.previous_environment = {key: os.environ.get(key) for key in ("CI", "FORCE_RERUN_ANALYTICS")}
        os.environ["CI"] = "1"
        os.environ.pop("FORCE_RERUN_ANALYTICS", None)
        self.recording = None
        try:
            import rerun as rr
            self.rr = rr
            self.recording = rr.RecordingStream("rr2-offline-evidence", default_enabled=True)
            plot.require(rr.is_enabled(recording=self.recording), "rerun-recording-disabled")
            self.recording.save(path)
        except BaseException:
            self.close()
            raise

    def configure_view(self, captures, *, display_camera=None):
        import rerun.blueprint as rrb
        self.recording.send_blueprint(default_blueprint(self.rr, rrb, captures, display_camera=display_camera),
                                      make_active=True, make_default=True)

    def log(self, entity, kind, data, *, at=None, static=False):
        self.recording.reset_time()
        if at is not None:
            import numpy as np
            self.recording.set_time("evidence_utc", timestamp=np.datetime64(at, "ns"))
        rr = self.rr
        if kind == "text":
            archetype = rr.TextDocument(json.dumps(data, indent=2, allow_nan=False))
        elif kind == "points3d":
            archetype = rr.Points3D(data["positions"], labels=data["labels"],
                                    show_labels=data.get("show_labels", True))
        elif kind == "point-labels3d":
            archetype = rr.Points3D.from_fields(labels=data["labels"], show_labels=True)
        elif kind == "route3d":
            archetype = rr.LineStrips3D([data["positions"]])
        elif kind == "camera-rays3d":
            archetype = rr.LineStrips3D(data["lineStrips"],
                labels=["", "", "", "", "Camera view rays (display only)"], show_labels=True)
        elif kind == "clear":
            archetype = rr.Clear(recursive=True)
        elif kind == "bearing3d":
            archetype = rr.Arrows3D(origins=data["origins"], vectors=data["vectors"], labels=["Body bearing candidate (unit arrow)"])
        elif kind == "points2d":
            archetype = rr.Points2D(data["positions"], labels=data["labels"], show_labels=True, draw_order=10)
        elif kind == "png":
            archetype = rr.EncodedImage(contents=data, media_type="image/png")
        else:
            raise ValueError("unsupported-export-kind")
        self.recording.log(entity, archetype, static=static, strict=True)

    def flush(self):
        self.recording.flush(timeout_sec=30)

    def close(self):
        try:
            if self.recording is not None:
                self.recording.disconnect()
                self.recording = None
        finally:
            for key, value in self.previous_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def default_blueprint(rr, rrb, captures, *, display_camera=None):
    """File-only 0.43.1 blueprint: explicit views and latest-data following.

    TimePanel cannot encode a cursor position. Following is the supported
    file-only way to start at the end; no data timestamps are altered.
    """
    camera_options = {}
    if display_camera is not None:
        camera_options["eye_controls"] = rrb.EyeControls3D(kind=rrb.Eye3DKind.Orbital,
            position=display_camera["position"], look_target=display_camera["lookTarget"],
            eye_up=[0, 1, 0], spin_speed=0)
    world = rrb.Spatial3DView(origin="/world", name="Native XYZ route (+Y height)",
        spatial_information=rrb.SpatialInformation.from_fields(axes=rr.ViewCoordinates.RIGHT_HAND_Y_UP),
        **camera_options)
    views = [rrb.Spatial2DView(origin=entity, name=(f"Desktop candidate {index + 1} (UTC upper bound)"
             if entity.endswith("_desktop_upper_bound") else f"Capture {index + 1}"))
             for index, (entity, _) in enumerate(captures)]
    views.append(rrb.TextDocumentView(origin="/evidence", name="Source metadata"))
    active = max(range(len(captures)), key=lambda index: captures[index][1]) if captures else 0
    return rrb.Blueprint(rrb.Horizontal(world, rrb.Tabs(*views, active_tab=active), column_shares=[1, 1]),
        rrb.TimePanel(timeline="evidence_utc", play_state="Following", state="expanded"),
        rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"),
        auto_layout=False, auto_views=False)


def prepare(route_path, observations, scratch, *, images=True, desktop_pairs=(), camera_rays=True):
    """Reuse the existing complete bracket/image/projection validator unchanged."""
    route = load_route(route_path)
    plot.require(route["identity"]["machine"].casefold() == plot.socket.gethostname().casefold(),
                 "route-host-mismatch")
    frames = []
    sources = [(source, False) for source in observations] + [(source, True) for source in desktop_pairs]
    for index, (source, desktop) in enumerate(sources):
        renderer = plot.render_desktop_pair if desktop else plot.render
        result = renderer(source, route_path, Path(scratch) / str(index))
        if desktop:
            plot.require(result.get("sourceKind") == "desktop-composite-event-candidate"
                         and result.get("capturedAtUtc") is None
                         and result.get("capturedAtUtcKind") == "unavailable-exact-desktop-event-utc",
                         "explicit-desktop-upper-bound-contract-required")
        # The renderer's scratch outputs are not retained/exported source artifacts.
        result.pop("annotatedImage", None)
        result.pop("report", None)
        native = []
        for side in ("nativeBefore", "nativeAfter"):
            path = Path(result[side])
            report = plot._read(path)
            values = plot.physical._native_values("facing", report)
            plot.require(report["identity"] == result["identity"]
                         and values["positionXYZCandidate"] == result["playerGround"]["worldXYZ"],
                         "native-source-changed-during-export")
            native.append({"side": side, "source": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "values": values,
                "cameraViewRays": native_view_rays(report["observation"].get("opticalCameraCandidate"))
                    if camera_rays else {"status": "unavailable", "reason": "not-requested"}})
        if desktop:
            # Native sources keep their actual sample times. This bound only positions
            # composite pixels on a shared viewer timeline; it is not capture UTC.
            after_report = plot._read(result["nativeAfter"])
            plot.require(timestamp_ns(result["captureUpperBoundAtUtc"]) ==
                         timestamp_ns(after_report["observation"]["startedAtUtc"]),
                         "desktop-capture-upper-bound-must-match-native-after-start")
        evidence_at = result["captureUpperBoundAtUtc"] if desktop else result["capturedAtUtc"]
        time_kind = "upper-bound-native-after-start-not-exact-capture" if desktop else "capture-completed-at-utc"
        png = Path(result["originalImage"]).read_bytes() if images else None
        if png is not None:
            plot.require(hashlib.sha256(png).hexdigest().casefold() == result["imageSha256"].casefold(),
                         "image-source-changed-during-export")
        frames.append({"projection": result, "native": native, "png": png,
            "desktop": desktop, "evidenceAtUtc": evidence_at, "timeKind": time_kind,
            "sourceSha256": hashlib.sha256(Path(source).read_bytes()).hexdigest()})
    return route, frames


def prepare_unit_samples(paths, route, frames):
    """Admit independent retained scans, without borrowing a frame's bracket."""
    def saved(path):
        path = Path(path).resolve()
        plot.require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 8 * 1024 * 1024,
                     "unit-sample-source-missing-or-oversized")
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=plot.unique_fields,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite-json")))
        plot.require(isinstance(document, dict), "unit-sample-object-required")
        return document, dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())

    def epoch(identity):
        return identity.get("processId"), str(identity.get("processStartUtcTicks")), str(identity.get("executableSha256", "")).casefold()

    def names_for(link, position_wrapper, scan):
        result = dict(status="unavailable", reason="not-retained")
        if not isinstance(link, dict) or link.get("status") != "saved":
            result["reason"] = link.get("reason", "not-retained") if isinstance(link, dict) else "not-retained"
            return result
        result["sourceLink"] = dict(link)
        try:
            def relative(value, parent):
                path = Path(value)
                return path if path.is_absolute() else Path(parent).parent / path
            wrapper, wrapper_source = saved(relative(link["path"], position_wrapper["path"]))
            plot.require(wrapper.get("status") == "complete" and wrapper.get("workflow") == "physical"
                         and wrapper.get("nativeRead") == "unit-names" and wrapper.get("target") == scan["target"]
                         and str(wrapper.get("ownerHost", "")).casefold() == scan["target"]["hostName"].casefold(),
                         "unit-names-wrapper-identity-mismatch")
            raw, source = saved(relative(wrapper["nativeOutput"], wrapper_source["path"]))
            plot.require(source["path"] == str(relative(link["source"], position_wrapper["path"]).resolve())
                         and source["sha256"] == str(link["sha256"]).casefold()
                         and source["sha256"] == str(wrapper.get("nativeSourceSha256", "")).casefold(),
                         "unit-names-source-hash-mismatch")
            names = plot.physical._native_values("unit-names", raw)
            plot.require(names == wrapper.get("nativeValues"), "unit-names-source-values-mismatch")
            plot.require(epoch(raw["observation"]["identity"]) == epoch(scan["identity"])
                         and names["selfKey"] == scan["selfKey"], "unit-names-source-identity-mismatch")
            plot.require([row["unitKey"] for row in names["rows"]] == [unit["unitKey"] for unit in scan["units"]],
                         "unit-names-requested-keys-mismatch")
            plot.require(timestamp_ns(scan["completedAtUtc"]) <= timestamp_ns(names["startedAtUtc"]),
                         "unit-names-acquisition-order-mismatch")
            for unit, name in zip(scan["units"], names["rows"]):
                if name["status"] == "available-candidate":
                    plot.require(unit["entityAddressDecimal"] == name["entityAddressDecimal"],
                                 "unit-names-position-owner-mismatch")
                    plot.require(timestamp_ns(unit["sampledAtUtc"]) <= timestamp_ns(name["startedAtUtc"]),
                                 "unit-names-acquisition-order-mismatch")
            result = dict(status="saved", wrapperSource=wrapper_source, nativeSource=source, **names)
            # Validate the entire optional batch before publishing any joined name.
            for unit, name in zip(scan["units"], names["rows"]):
                if name["status"] == "available-candidate":
                    unit["nameCandidate"] = dict(name, qualification=names["qualification"])
        except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
            result["reason"] = str(error)
        return result

    scans = []
    for path in paths:
        wrapper, wrapper_source = saved(path)
        plot.require(wrapper.get("status") == "complete" and wrapper.get("workflow") == "physical"
                     and wrapper.get("nativeRead") == "unit-positions", "complete-unit-sample-wrapper-required")
        target = wrapper.get("target", {})
        expected = route["identity"]
        plot.require(isinstance(target, dict)
                     and str(target.get("hostName", "")).casefold() == expected["machine"].casefold()
                     and str(wrapper.get("ownerHost", "")).casefold() == expected["machine"].casefold()
                     and str(target.get("executableSha256", "")).casefold() == expected["gameBuildSha256"].casefold(),
                     "unit-sample-route-host-build-mismatch")
        plot.require(type(target.get("processId")) is int and target["processId"] > 0
                     and str(target.get("processStartUtcTicks", "")).isdecimal()
                     and int(target["processStartUtcTicks"]) > 0
                     and type(target.get("hwnd")) is int and target["hwnd"] > 0,
                     "unit-sample-target-identity-required")
        native_path = Path(wrapper["nativeOutput"])
        if not native_path.is_absolute():
            native_path = Path(wrapper_source["path"]).parent / native_path
        report, source = saved(native_path)
        values = plot.physical._native_values("unit-positions", report)
        row = report["observation"]
        plot.require(epoch(row["identity"]) == epoch(target), "unit-sample-wrapper-native-epoch-mismatch")
        plot.require(values["selfKey"] == expected["unitKey"], "unit-sample-route-player-mismatch")
        plot.require(all(epoch(frame["projection"]["identity"]) == epoch(target) for frame in frames),
                     "unit-sample-capture-epoch-mismatch")
        if "nativeSourceSha256" in wrapper:
            plot.require(str(wrapper["nativeSourceSha256"]).casefold() == source["sha256"],
                         "unit-sample-native-source-hash-mismatch")
        selected = sorted((unit for unit in values["units"] if unit["unitKey"] != values["selfKey"]
                           and unit["horizontalDistanceCandidate"] <= 35),
                          key=lambda unit: (unit["horizontalDistanceCandidate"], int(unit["unitKey"])))[:18]
        raw_rows = {unit["unitKey"]: unit for unit in row["rows"]}
        selected = [{**unit, "rawBits": raw_rows[unit["unitKey"]]["rawBits"],
                     "entityAddressDecimal": raw_rows[unit["unitKey"]]["entityAddressDecimal"],
                     "startedAtUtc": raw_rows[unit["unitKey"]]["startedAtUtc"]}
                    for unit in selected]
        scans.append(dict(wrapperSource=wrapper_source, nativeSource=source, identity=row["identity"],
            target=target, selfKey=values["selfKey"], startedAtUtc=row["startedAtUtc"],
            completedAtUtc=row["completedAtUtc"], units=selected, limit=18, maxDistance=35,
            sourceHashKind="retained-file-sha256-at-export-not-acquisition-proof",
            coverage={key: values[key] for key in ("unitsExamined", "positionsFound", "unitsWithoutPosition",
                "unavailableUnits", "unavailableChains", "bucketsExamined", "bucketCount", "startBucket",
                "unitLimitReached", "worldCoverage", "worldIdentityStatus")},
            timeKind="independent-sequential-native-row-acquisition-completion",
            qualification="Independent loaded-unit stored-position candidates; not screenshot aligned. "
                "Latest sample carries forward in the offline timeline, not live tracking or passive-freshness proof. "
                "Unit classification, world instance, terrain, collision and occlusion unavailable."))
        scans[-1]["names"] = names_for(wrapper.get("nameSample"), wrapper_source, scans[-1])
    scans.sort(key=lambda scan: timestamp_ns(scan["startedAtUtc"]))
    for first, second in zip(scans, scans[1:]):
        plot.require(timestamp_ns(first["completedAtUtc"]) <= timestamp_ns(second["startedAtUtc"]),
                     "unit-sample-overlapping-scans")
        names = first["names"]
        if names["status"] == "saved" and timestamp_ns(names["sampledAtUtc"]) > timestamp_ns(second["startedAtUtc"]):
            names.update(status="unavailable", reason="unit-names-overlap-next-position-scan")
            for unit in first["units"]:
                unit.pop("nameCandidate", None)
    return scans


def unit_scene_display_camera(route, scans, frames):
    """Conservative viewer pose from admitted geometry, independent of game camera."""
    points = [[point["xyz"][axis] for axis in ("x", "y", "z")] for point in route["points"]]
    points.extend([unit["positionXYZCandidate"][axis] for axis in ("x", "y", "z")]
                  for scan in scans for unit in scan["units"])
    for frame in frames:
        for native in frame["native"]:
            rays = native["cameraViewRays"]
            if rays["status"] == "available-candidate":
                points.extend([rays["nativeEyeXYZ"], *rays["cornersXYZ"]])
    plot.require(points and all(len(p) == 3 and all(type(v) in (int, float) and math.isfinite(v)
                 for v in p) for p in points), "finite-display-camera-geometry-required")
    lower = [min(p[axis] for p in points) for axis in range(3)]
    upper = [max(p[axis] for p in points) for axis in range(3)]
    center = [(a + b) / 2 for a, b in zip(lower, upper)]
    radius = max(1., max(math.dist(center, point) for point in points))
    position = [c + radius * offset for c, offset in zip(center, (3, 4, 3))]
    plot.require(all(math.isfinite(v) for v in [*center, radius, *position]), "finite-display-camera-required")
    return dict(position=position, lookTarget=center, eyeUp=[0, 1, 0], radius=radius,
                boundsMin=lower, boundsMax=upper, includedPointCount=len(points),
                qualification="Display viewer camera only, not the game camera. Conservative oblique pose "
                    "from admitted route/unit/view-ray bounds; not an exact viewport fit or scene-depth claim.")


def export(route_path, observations, output, *, images=True, sink_factory=RerunSink, desktop_pairs=(), camera_rays=True,
           unit_samples=()):
    route_path, output = Path(route_path).resolve(), Path(output).resolve()
    plot.require(output.suffix.lower() == ".rrd" and not output.exists() and output.parent.is_dir(),
                 "new-rrd-output-required")
    observations = [Path(path).resolve() for path in observations]
    desktop_pairs = [Path(path).resolve() for path in desktop_pairs]
    # Existing renderer writes a scratch annotated PNG; it is discarded after validation.
    with TemporaryDirectory(prefix="rr2-rerun-", dir=output.parent) as scratch:
        route, frames = prepare(route_path, observations, scratch, images=images, desktop_pairs=desktop_pairs,
                                camera_rays=camera_rays)
    unit_scans = prepare_unit_samples(unit_samples, route, frames)
    display_camera = unit_scene_display_camera(route, unit_scans, frames) if unit_scans else None
    result = {"status": "offline-rerun-evidence-export", "output": str(output), "inputSent": False,
              "route": route["path"], "routeSha256": route["sha256"],
              "recordingIdentity": route["recordingIdentity"], "observationCount": len(frames),
              "provenanceKind": route["provenanceKind"],
              "wgcObservationCount": len(observations), "desktopPairCount": len(desktop_pairs),
              "imagesIncluded": images, "limitations": LIMITATIONS}
    result["cameraViewRaysRequested"] = camera_rays
    result["unitSampleCount"] = len(unit_scans)
    result["unitSamples"] = unit_scans
    if display_camera is not None:
        result["displayCamera"] = display_camera
    result["toolStatus"] = "optional Rerun 0.43.1 alpha SDK pilot; API pinned"
    sink = None
    created = False
    try:
        # Reserve exclusively after all source validation, preserving existing output files.
        with output.open("xb"):
            created = True
        sink = sink_factory(output)
        sink.configure_view([(f"/captures/{number:04d}" + ("_desktop_upper_bound" if frame["desktop"] else ""),
                              timestamp_ns(frame["evidenceAtUtc"]))
                             for number, frame in enumerate(frames, 1)],
                            **({"display_camera": display_camera} if display_camera is not None else {}))
        sink.log("evidence/sources", "text", result, static=True)
        positions = [[p["xyz"][axis] for axis in ("x", "y", "z")] for p in route["points"]]
        labels = [f'{p["number"]}: {p["label"]}' for p in route["points"]]
        sink.log("world/route/points", "points3d", dict(positions=positions, labels=labels), static=True)
        if len(positions) > 1:
            sink.log("world/route/line", "route3d", dict(positions=positions), static=True)
        for number, frame in enumerate(frames, 1):
            projection = frame["projection"]
            capture_at = timestamp_ns(frame["evidenceAtUtc"])
            capture_entity = f"captures/{number:04d}" + ("_desktop_upper_bound" if frame["desktop"] else "")
            metadata = {"source": projection["observation"], "sourceSha256": frame["sourceSha256"],
                "timeKind": frame["timeKind"], "evidenceAtUtc": frame["evidenceAtUtc"],
                "sourceKind": "desktop-composite-event-candidate" if frame["desktop"] else "wgc-native-bracket-candidate",
                "projection": projection, "nativeSources": [{k: v for k, v in row.items() if k != "values"} for row in frame["native"]]}
            sink.log(f"evidence/observations/{number:04d}", "text", metadata, at=capture_at)
            if frame["png"] is not None:
                sink.log(capture_entity, "png", frame["png"], at=capture_at)
            projected = [row for row in projection["points"] if row["ground"]["status"] == "drawn-candidate"]
            xy = [[row["ground"]["frameProjection"][axis] for axis in ("frameX", "frameY")] for row in projected]
            point_labels = [f'{row["number"]}: {row["label"]}' for row in projected]
            player = projection["playerGround"]
            if player["status"] == "drawn-candidate":
                xy.append([player["frameProjection"][axis] for axis in ("frameX", "frameY")])
                point_labels.append("Player ground candidate")
            if xy:
                sink.log(capture_entity + "/projected", "points2d", dict(positions=xy, labels=point_labels), at=capture_at)
            for row in frame["native"]:
                values = row["values"]
                at = timestamp_ns(values["sampledAtUtc"])
                xyz = [values["positionXYZCandidate"][axis] for axis in ("x", "y", "z")]
                sink.log("world/player", "points3d", dict(positions=[xyz], labels=["Native player candidate"]), at=at)
                bearing = math.radians(values["bodyBearingDegreesCandidate"])
                sink.log("world/player/bearing", "bearing3d", dict(origins=[xyz], vectors=[[math.sin(bearing), 0, math.cos(bearing)]]), at=at)
                sink.log("evidence/native", "text", row, at=at)
                rays = row["cameraViewRays"]
                if rays["status"] == "available-candidate":
                    sink.log("world/camera/eye", "points3d", dict(positions=[rays["nativeEyeXYZ"]],
                        labels=["Native optical eye candidate"]), at=at)
                    sink.log("world/camera/view_rays", "camera-rays3d", rays, at=at)
                elif camera_rays:
                    # A failed later sample must not leave an older camera shape
                    # looking current through viewer timeline carry-forward.
                    sink.log("world/camera", "clear", {}, at=at)
        for number, scan in enumerate(unit_scans, 1):
            sink.log("world/loaded_units", "clear", {}, at=timestamp_ns(scan["startedAtUtc"]))
            sink.log(f"evidence/unit_samples/{number:04d}", "text", scan,
                     at=timestamp_ns(scan["completedAtUtc"]))
            for unit in scan["units"]:
                sink.log(f"world/loaded_units/{unit['unitKey']}", "points3d",
                         dict(positions=[[unit["positionXYZCandidate"][axis] for axis in ("x", "y", "z")]],
                              labels=[f"Loaded unit {unit['unitIdCandidate'][-6:]} (sample)"], show_labels=False),
                         at=timestamp_ns(unit["sampledAtUtc"]))
                name = unit.get("nameCandidate")
                if name is not None:
                    sink.log(f"world/loaded_units/{unit['unitKey']}", "point-labels3d",
                             dict(labels=[name["baseNameCandidate"] + " (candidate)"]),
                             at=timestamp_ns(name["sampledAtUtc"]))
        sink.flush()
        sink.close()
        sink = None
        plot.require(output.stat().st_size > 0, "empty-rerun-output")
    except BaseException:
        if sink is not None:
            try:
                sink.close()
            finally:
                if created:
                    output.unlink(missing_ok=True)
        elif created:
            output.unlink(missing_ok=True)
        raise
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--observation", type=Path, action="append", default=[])
    parser.add_argument("--desktop-pair", type=Path, action="append", default=[],
                        help="explicit retained DXcam/native candidate; capture UTC is only an upper bound")
    parser.add_argument("--unit-sample", type=Path, action="append", default=[],
                        help="retained physical unit-positions wrapper; independent 3D samples only")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-images", action="store_true", help="validate retained PNGs but omit image payloads")
    parser.add_argument("--no-camera-rays", action="store_true", help="omit optional native projection display rays")
    args = parser.parse_args(argv)
    try:
        result = export(args.route, args.observation, args.output, images=not args.no_images,
                        desktop_pairs=args.desktop_pair, camera_rays=not args.no_camera_rays,
                        unit_samples=args.unit_sample)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, ImportError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "inputSent": False}))
        return 2
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
