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
]


def timestamp_ns(value):
    parsed, remainder = plot.physical._utc_tick_order_key(value)
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return ((delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1000 + remainder * 100


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

    def configure_view(self, captures):
        import rerun.blueprint as rrb
        self.recording.send_blueprint(default_blueprint(self.rr, rrb, captures),
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
            archetype = rr.Points3D(data["positions"], labels=data["labels"], show_labels=True)
        elif kind == "route3d":
            archetype = rr.LineStrips3D([data["positions"]])
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


def default_blueprint(rr, rrb, captures):
    """File-only 0.43.1 blueprint: explicit views and latest-data following.

    TimePanel cannot encode a cursor position. Following is the supported
    file-only way to start at the end; no data timestamps are altered.
    """
    world = rrb.Spatial3DView(origin="/world", name="Native XYZ route (+Y height)",
        spatial_information=rrb.SpatialInformation.from_fields(axes=rr.ViewCoordinates.RIGHT_HAND_Y_UP))
    views = [rrb.Spatial2DView(origin=entity, name=f"Capture {index + 1}")
             for index, (entity, _) in enumerate(captures)]
    views.append(rrb.TextDocumentView(origin="/evidence", name="Source metadata"))
    active = max(range(len(captures)), key=lambda index: captures[index][1]) if captures else 0
    return rrb.Blueprint(rrb.Horizontal(world, rrb.Tabs(*views, active_tab=active), column_shares=[1, 1]),
        rrb.TimePanel(timeline="evidence_utc", play_state="Following", state="expanded"),
        rrb.BlueprintPanel(state="collapsed"), rrb.SelectionPanel(state="collapsed"),
        auto_layout=False, auto_views=False)


def prepare(route_path, observations, scratch, *, images=True):
    """Reuse the existing complete bracket/image/projection validator unchanged."""
    route = load_route(route_path)
    plot.require(route["identity"]["machine"].casefold() == plot.socket.gethostname().casefold(),
                 "route-host-mismatch")
    frames = []
    for index, source in enumerate(observations):
        result = plot.render(source, route_path, Path(scratch) / str(index))
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
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "values": values})
        png = Path(result["originalImage"]).read_bytes() if images else None
        if png is not None:
            plot.require(hashlib.sha256(png).hexdigest().casefold() == result["imageSha256"].casefold(),
                         "image-source-changed-during-export")
        frames.append({"projection": result, "native": native, "png": png,
            "sourceSha256": hashlib.sha256(Path(source).read_bytes()).hexdigest()})
    return route, frames


def export(route_path, observations, output, *, images=True, sink_factory=RerunSink):
    route_path, output = Path(route_path).resolve(), Path(output).resolve()
    plot.require(output.suffix.lower() == ".rrd" and not output.exists() and output.parent.is_dir(),
                 "new-rrd-output-required")
    observations = [Path(path).resolve() for path in observations]
    # Existing renderer writes a scratch annotated PNG; it is discarded after validation.
    with TemporaryDirectory(prefix="rr2-rerun-", dir=output.parent) as scratch:
        route, frames = prepare(route_path, observations, scratch, images=images)
    result = {"status": "offline-rerun-evidence-export", "output": str(output), "inputSent": False,
              "route": route["path"], "routeSha256": route["sha256"],
              "recordingIdentity": route["recordingIdentity"], "observationCount": len(frames),
              "imagesIncluded": images, "limitations": LIMITATIONS}
    result["toolStatus"] = "optional Rerun 0.43.1 alpha SDK pilot; API pinned"
    sink = None
    created = False
    try:
        # Reserve exclusively after all source validation, preserving existing output files.
        with output.open("xb"):
            created = True
        sink = sink_factory(output)
        sink.configure_view([(f"/captures/{number:04d}", timestamp_ns(frame["projection"]["capturedAtUtc"]))
                             for number, frame in enumerate(frames, 1)])
        sink.log("evidence/sources", "text", result, static=True)
        positions = [[p["xyz"][axis] for axis in ("x", "y", "z")] for p in route["points"]]
        labels = [f'{p["number"]}: {p["label"]}' for p in route["points"]]
        sink.log("world/route/points", "points3d", dict(positions=positions, labels=labels), static=True)
        if len(positions) > 1:
            sink.log("world/route/line", "route3d", dict(positions=positions), static=True)
        for number, frame in enumerate(frames, 1):
            projection = frame["projection"]
            capture_at = timestamp_ns(projection["capturedAtUtc"])
            capture_entity = f"captures/{number:04d}"
            metadata = {"source": projection["observation"], "sourceSha256": frame["sourceSha256"],
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-images", action="store_true", help="validate retained PNGs but omit image payloads")
    args = parser.parse_args(argv)
    try:
        result = export(args.route, args.observation, args.output, images=not args.no_images)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, ImportError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "inputSent": False}))
        return 2
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
