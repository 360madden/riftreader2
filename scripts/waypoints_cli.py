"""Console control for the existing Waypoints app; no independent game reader."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VERSION = "1.0"
MOVEMENT = {"move.to", "face", "route.run", "playback.start", "playback.resume"}
COMMON = {"session", "timeout", "json", "jsonl", "no_color"}


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.update(allow_abbrev=False)
        super().__init__(*args, **kwargs)
        self.suggest_on_error = True
        self.color = False

    def error(self, message):
        raise UsageError(message)


def number(value):
    try:
        result = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a finite number") from None
    if not math.isfinite(result):
        raise argparse.ArgumentTypeError("must be a finite number")
    return result


def bounded(low, high):
    def convert(value):
        result = number(value)
        if not low <= result <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return result
    return convert


def positive(value):
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer (one-based)") from None
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer (one-based)")
    return result


def common(parser):
    # Suppressed defaults let an option before a group survive leaf parsing.
    parser.add_argument("--session", default=argparse.SUPPRESS, help="select the exact helper session ID")
    parser.add_argument("--timeout", type=bounded(.05, 3600), default=argparse.SUPPRESS,
                        help="seconds to wait; default 150 for movement, 10 otherwise")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="one versioned JSON result")
    output.add_argument("--jsonl", action="store_true", default=argparse.SUPPRESS, help="explicit status/pose watch JSON lines")
    parser.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS, help="plain output (the default)")


def example(operation):
    return {
        "route.load":"route load route.json --discard", "route.save":"route save route.json",
        "route.list":"route list --file route.json", "route.validate":"route validate --file route.json",
        "route.add":"route add --current --name Camp", "route.update":"route update 1 --name Camp",
        "route.remove":"route remove 1", "route.reorder":"route reorder 1 --to 2",
        "route.select":"route select 1", "guide.start":"guide start --direction forward --from 1",
        "trail.save":"trail save trail.json --segment latest", "trail.clear":"trail clear --discard",
        "record.stop":"record stop recorded-route.json", "radar.set":"radar set --range 10 --opacity 85",
        "radar.move":"radar move --x 30 --y 50", "beacons.set":"beacons set --size 1 --labels on",
        "move.to":"move to 123 456 --execute", "face":"face 90 --execute",
        "playback.start":"playback start --direction forward --execute",
        "playback.resume":"playback resume --execute", "route.run":"route run --execute",
        "view.save":"view save view.json", "view.open":"view open view.json",
        "view.open-3d":"view open-3d view.json", "receipt.show":"receipt show waypoint-run-ID.json",
        "app.close":"app close --discard", "app.open":"app open --route route.json",
        "zone.refresh":"zone refresh", "route.tag-zone":"route tag-zone",
        "library.list":"library list --zone matching --search Camp",
        "library.save":"library save Camp --id camp", "library.import":"library import route.json --name Camp",
        "library.load":"library load camp --discard", "library.show":"library show camp",
    }.get(operation, operation.replace(".", " "))


def build_parser():
    parser = Parser(prog="rr2-waypoints", description="Control the existing Waypoints app from a console.",
                    epilog="Examples: rr2-waypoints status; rr2-waypoints radar show; rr2-waypoints guide start --from 1\n"
                           "rr2-waypoints route list --file route.json; rr2-waypoints playback start --execute")
    common(parser)
    parser.add_argument("--version", action="version", version=f"rr2-waypoints {VERSION}")
    groups = parser.add_subparsers(dest="group", title="Commands")
    leaves = {}

    def leaf(parent, name, operation, purpose, effects="Read-only; sends no game input."):
        p = parent.add_parser(name, help=purpose, description=purpose,
                              epilog=("Requires: no running helper; operates on local session metadata or explicit files.\n"
                                      if operation.startswith("receipt.") or operation in {"app.list", "app.open"}
                                      else "Requires: an unambiguous running Waypoints session; route list/validate support offline --file.\n")
                                     + f"Effects: {effects}\nDefaults: timeout {'150' if operation in MOVEMENT else '10'} seconds; one-based points/segments.\n"
                                     f"Example: rr2-waypoints {example(operation)}",
                              formatter_class=argparse.RawDescriptionHelpFormatter)
        common(p)
        p.set_defaults(operation=operation)
        leaves[operation] = p
        if operation in MOVEMENT:
            p.add_argument("--execute", action="store_true", help="explicitly authorize guarded game input")
        return p

    for name in ("status", "doctor", "capabilities", "stop"):
        p = leaf(groups, name, name, {"status":"Report actual helper state and display visibility.",
                 "doctor":"Explain helper readiness and recovery steps.", "capabilities":"List supported operations.",
                 "stop":"Latch owned STOP and report key release separately from stationary evidence."}[name],
                 "Requests owned cancellation and release; does not cancel arbitrary game autorun." if name == "stop" else "Read-only; sends no game input.")
        if name == "status":
            p.add_argument("--watch", action="store_true", help="poll until Ctrl+C; requires --jsonl for machine output")
            p.add_argument("--pose", action="store_true", help="include the existing reader's qualified pose")
            p.add_argument("--interval", type=bounded(.1, 60), default=1., help="watch interval seconds, default 1")
            p.add_argument("--count", type=positive, help="stop watch after this many reports")
    for group, verbs in {
        "app":"list open show hide close", "route":"list load save new add update remove reorder select undo validate run context tag-zone",
        "zone":"status refresh", "library":"list save import load show",
        "radar":"status show hide set move lock unlock", "beacons":"status show hide set",
        "guide":"status start stop", "trail":"status start stop list save clear", "record":"status start stop cancel",
        "move":"to", "playback":"start resume status", "view":"save open open-3d", "receipt":"list show"
    }.items():
        gp = groups.add_parser(group, help=f"{group.capitalize()} controls", description=f"{group.capitalize()} commands")
        common(gp)
        gp.set_defaults(help_parser=gp)
        sub = gp.add_subparsers(dest="verb", title="Commands")
        for verb in verbs.split():
            operation = f"{group}.{verb}"
            read_only = verb in {"status", "list", "validate"} or operation == "receipt.show"
            purpose = {
                "app.open":"Open Waypoints, or reuse the selected existing helper without replacing its route.",
                "app.show":"Show the selected helper window.", "app.hide":"Hide the selected helper window.",
                "app.close":"Close the selected helper after owned workers release; unsaved changes need --discard.",
                "route.add":"Add an estimated point with --x/--z, measured player XYZ with --current, or a qualified target candidate with --target.",
                "route.update":"Edit a point name or estimated X/Z; changed coordinates discard its prior measured height.",
                "zone.status":"Show the current zone candidate and freshness; a candidate is not proof of the actual world instance.",
                "zone.refresh":"Read a fresh native zone candidate under the helper's current identity; not proof of the actual world instance.",
                "route.context":"Show the loaded route's saved zone binding and comparison with current candidate context.",
                "route.tag-zone":"Explicitly attach the current fresh zone candidate to a legacy route; not proof of the actual world instance.",
                "library.list":"List routes in the owned library, optionally filtering current zone comparisons and searching names/IDs.",
                "library.save":"Copy the loaded route into the owned library with a display name; retain its context.",
                "library.import":"Copy the explicit source file into the owned library, preserving its saved context and source file.",
                "library.load":"Load a library route into the helper; unsaved changes require --discard.",
                "library.show":"Inspect one owned library route, its zone context and measured/unknown heights.",
                "beacons.show":"Start the owned shared beacon reader and wait for fresh pose; sends no game input.",
                "beacons.hide":"Stop the owned beacon reader and wait for its exit.",
                "view.save":"Save a JSON manifest at FILE referencing a newly captured image/3D bundle in artifacts.",
                "view.open":"Open a saved JSON view manifest or image file.",
                "view.open-3d":"Open a saved JSON view manifest or exported .rrd recording in the 3D viewer.",
                "record.start":"Start read-only route recording; capture continues until explicit stop or cancel.",
                "record.stop":"Stop recording and save its measured route at the explicit FILE.",
                "record.cancel":"Stop recording and discard its captured route.",
                "guide.start":"Start passive arrival guidance with fresh confirmation for 0.2 seconds; never sends game input.",
                "trail.start":"Start observing a breadcrumb trail from the existing owned pose feed.",
                "trail.stop":"Stop breadcrumb observation and retain its history.",
                "trail.save":"Export one observed trail segment to a separate existing-format route file.",
                "playback.start":"Replay the complete loaded route in forward or reverse order using face-then-walk mode.",
                "playback.resume":"Resume the saved checkpoint cursor and direction using face-then-walk mode.",
                "route.run":"Run the loaded route from a one-based point using face-then-walk mode.",
                "move.to":"Move to world X/Z using guarded face-then-walk mode.",
            }.get(operation, f"{verb.capitalize()} {group}.")
            effects = ("Read-only native candidate refresh; sends no game input." if operation == "zone.refresh"
                       else "Read-only; sends no game input." if read_only or operation in {"route.context", "library.show"}
                       else "Attaches fresh candidate provenance to the loaded route; sends no game input." if operation == "route.tag-zone"
                       else "Writes a copy in the owned route library; sends no game input." if operation in {"library.save", "library.import"}
                       else "Sends guarded game input only with --execute; uses face-then-walk and waits for a terminal result." if operation in MOVEMENT
                       else "Starts the owned shared reader; sends no game input." if operation == "beacons.show"
                       else "Changes helper visibility; sends no game input." if operation in {"app.show", "app.hide", "app.open"}
                       else "Writes the explicit JSON manifest and a new capture bundle; sends no game input." if operation == "view.save"
                       else "Opens a saved local asset in its viewer; sends no game input." if group == "view"
                       else "Changes helper state or the explicitly named file; sends no game input.")
            leaf(sub, verb, operation, purpose, effects)
    leaf(groups, "face", "face", "Face an absolute bearing in degrees (0 <= bearing < 360).",
         "Sends guarded turning input only with --execute; waits for a terminal result.")
    groups.add_parser("help", help="show the same help as COMMAND --help").add_argument("topic", nargs="*")

    def arg(op, *names, **kwargs): leaves[op].add_argument(*names, **kwargs)
    arg("library.list", "--zone", choices=("all", "matching", "mismatch", "unknown"), default="all",
        help="candidate comparison with current zone; default all; matching does not prove a world instance")
    arg("library.list", "--search", help="filter library names or IDs by text")
    arg("library.save", "name", help="display name for the saved copy")
    arg("library.import", "file", type=Path, help="explicit source route file to copy; retains saved context")
    arg("library.import", "--name", help="display name; defaults to source route name or filename")
    for op in ("library.save", "library.import"):
        arg(op, "--id", dest="route_id", help="library ID: 1-80 letters, digits, underscores or hyphens; starts with a letter or digit")
        arg(op, "--overwrite", action="store_true", help="allow replacement of the specified library ID")
    for op in ("library.load", "library.show"):
        arg(op, "route_id", metavar="ID", help="owned library route ID")
    arg("library.load", "--discard", action="store_true", help="explicitly discard unsaved route changes")
    for op in ("route.load", "route.save", "trail.save", "record.stop", "view.save", "view.open", "view.open-3d", "receipt.show"):
        arg(op, "file", type=Path, help="explicit file path; no file chooser")
    for op in ("route.save", "trail.save", "record.stop", "view.save"):
        arg(op, "--overwrite", action="store_true", help="allow replacement of an existing file")
    for op in ("route.load", "route.new", "app.close"):
        arg(op, "--discard", action="store_true", help="explicitly discard unsaved route changes")
    for op in ("route.list", "route.validate"):
        arg(op, "--file", type=Path, help="read and inspect a route offline; no live session required")
    for op in ("route.new", "route.add", "route.update"):
        arg(op, "--name", help="waypoint/route name")
    add = leaves["route.add"].add_mutually_exclusive_group()
    add.add_argument("--current", action="store_true", help="capture current measured player XYZ position")
    add.add_argument("--target", action="store_true", help="capture the qualified selected-target candidate")
    for op in ("route.add", "route.update"):
        for axis in "xz": arg(op, "--" + axis, type=number, help=f"world {axis.upper()} units; finite")
    for op in ("route.update", "route.remove", "route.reorder", "route.select"):
        arg(op, "point", type=positive, help="one-based waypoint number")
    arg("route.reorder", "--to", type=positive, required=True, help="one-based destination position")
    for op in ("route.load", "route.save", "route.new", "route.add", "route.update", "route.remove", "route.reorder", "route.select", "route.undo"):
        arg(op, "--revision", type=int, help="refuse if the route revision changed")
    for op in ("guide.start", "playback.start", "playback.resume", "route.run"):
        arg(op, "--direction", choices=("forward", "reverse"), default=None if op == "playback.resume" else "forward")
        if op in ("guide.start", "route.run"):
            arg(op, "--from", dest="from_point", type=positive, help="one-based starting waypoint; guide confirms fresh arrival for 0.2 seconds")
    arg("guide.start", "--radius", type=bounded(.05, 10), help="arrival radius in world units")

    for op in ("playback.start", "playback.resume"):
        arg(op, "--checkpoint", type=Path, help="explicit playback checkpoint path")
    arg("radar.set", "--range", type=number, choices=(2., 5., 10., 20.), help="radar radius in world units: 2, 5, 10 or 20")
    for op in ("radar.set", "beacons.set"):
        arg(op, "--opacity", type=bounded(20, 100), help="opacity percent 20-100")
    for axis in "xy": arg("radar.move", "--" + axis, type=number, required=True, help=f"relative game-client {axis.upper()} pixels")
    arg("beacons.set", "--size", type=bounded(.5, 2), help="marker size multiplier 0.5-2")
    for flag in ("labels", "target", "guide"):
        arg("beacons.set", "--" + flag, choices=("on", "off"))
    arg("trail.save", "--segment", default="latest", help="one-based segment number or latest (default)")
    arg("trail.clear", "--discard", action="store_true", required=True, help="explicitly discard trail history")
    arg("move.to", "x", type=number, help="destination world X")
    arg("move.to", "z", type=number, help="destination world Z")
    arg("face", "bearing", type=bounded(0, 359.999999999), help="absolute bearing degrees [0,360)")
    arg("app.open", "--pid", type=positive, help="explicit physical RIFT process ID")
    arg("app.open", "--route", type=Path)
    arg("app.open", "--basis", type=Path)
    arg("app.open", "--background", action="store_true", help="start the helper hidden")
    arg("app.show", "--tab", choices=("replay","edit","scene","explore","library","activity"), help="show a workspace tab")
    arg("receipt.list", "--directory", type=Path, default=ROOT / "artifacts", help="receipt directory; offline")
    return parser


def result(command, *, ok=True, status="completed", data=None, error=None, session=None):
    return dict(version=1, command=command, ok=ok, status=status, sessionId=session,
                target=None, data=data, error=error)


def human_radar(data):
    print(f"Radar requested: {'on' if data.get('enabled') else 'off'}, "
          f"range {data.get('range', '?')} units, opacity {data.get('opacity', '?')}%, "
          f"{'unlocked' if data.get('unlocked') else 'locked'}")
    observed = data.get("observed")
    if not observed:
        print("Radar observed: unavailable (no fresh owned presenter feedback)")
        return
    opacity = observed.get("opacity")
    opacity = round(opacity * 100) if isinstance(opacity, (int, float)) else "?"
    print(f"Radar observed: {'visible' if observed.get('visible') else 'hidden'}, "
          f"range {observed.get('range', '?')} units, opacity {opacity}%, "
          f"{'unlocked' if observed.get('unlocked') else 'locked'}")
    if observed.get("position"):
        p = observed["position"]
        print(f"Radar position: X {p.get('x')} / Y {p.get('y')} physical pixels relative to game client")


def human_pose(pose):
    age = pose.get("ageSeconds")
    age_text = f"{age:.2f}s old" if isinstance(age, (int, float)) else "age unavailable"
    print(f"Pose: {pose.get('status', 'unavailable')} | {pose.get('source', 'source unavailable')} | {age_text}")
    position = pose.get("position")
    if pose.get("status") == "fresh" and isinstance(position, dict):
        print("Position: " + " / ".join(f"{axis.upper()} {position.get(axis, '?')}" for axis in "xyz")
              + f" | facing {pose.get('bearing', '?')} degrees")
    elif pose.get("reason"):
        print("Pose reason: " + str(pose["reason"]))


def human_zone(context, *, label="Zone"):
    context = context or {}
    print(f"{label}: {context.get('zoneName') or context.get('zoneIdCandidate') or 'unknown'}"
          + (f" | source {context['source']}" if context.get("source") else "")
          + " | candidate; actual world instance unproven")


def human_data(command, data):
    if not isinstance(data, dict): return False
    if command in {"status", "doctor"}:
        target, app, route = data.get("target") or {}, data.get("app") or {}, data.get("route") or {}
        print(f"Host: {data.get('host', target.get('hostName', '?'))} | RIFT PID: {target.get('processId', 'unavailable')}")
        ready = data.get("ready", data.get("pose", {}).get("status") == "fresh")
        print(f"App: {'busy' if app.get('busy') else 'ready' if ready else 'waiting'} | "
              f"{'visible' if app.get('visible') else 'hidden'} | {app.get('state', '')}")
        print(f"Route: {route.get('count', 0)} points | {'unsaved changes' if route.get('dirty') else 'saved'} | {route.get('file') or 'no file'}")
        human_pose(data.get("pose") or {})
        human_radar(data.get("radar") or {})
        if data.get("zone"):
            zone = data["zone"]
            human_zone(zone.get("context", zone))
        if data.get("activeRequestId"): print("Active request: " + str(data["activeRequestId"]))
        for step in data.get("nextSteps", []): print("Next: " + str(step))
    elif command in {"route.list", "route.validate"}:
        points = data.get("points", [])
        print(f"Route: {data.get('file') or 'loaded in helper'} | {len(points)} points | "
              f"{'unsaved changes' if data.get('dirty') else 'saved'} | revision {data.get('revision', 'offline')}")
        if "measuredCount" in data:
            print(f"Heights: {data['measuredCount']} measured, {data['estimatedCount']} estimated/unknown")
        for p in points:
            height = next((h for h in data.get("heights",[]) if h.get("number")==p.get("number")),None)
            note = (" | "+height["label"]+" ["+height["heightKind"]+"]") if height else ""
            print(f"  {p.get('number')}. {p.get('name', '')}: X {p.get('x')} / Z {p.get('z')}{note}")
        if data.get("qualification"): print(data["qualification"])
    elif command in {"zone.status", "zone.refresh"}:
        human_zone(data.get("context"))
        age = data.get("currentAgeSeconds")
        age_text = f"{age:.2f}s old" if isinstance(age, (int, float)) else "age unavailable"
        print(f"Zone observation: {data.get('status', 'unavailable')} | {age_text}")
        if data.get("qualification"): print(data["qualification"])
    elif command in {"route.context", "route.tag-zone"}:
        human_zone(data.get("routeContext"), label="Route zone")
        human_zone(data.get("currentContext"), label="Current zone")
        print(f"Zone comparison: {data.get('comparison', 'unknown')} (candidate evidence only)")
        if data.get("qualification"): print(data["qualification"])
    elif command == "library.list":
        rows = data.get("routes", [])
        print(f"Route library: {len(rows)} routes | zone comparison is candidate evidence only")
        for row in rows:
            context = row.get("routeContext") or {}
            zone = context.get("zoneName") or context.get("zoneIdCandidate") or "unknown"
            print(f"  {row.get('id', '?')} | {row.get('name', '')} | zone {zone} ({row.get('contextStatus', 'unknown')}) | "
                  f"{row.get('waypointCount', '?')} points | heights {row.get('measuredHeightCount', '?')} measured, "
                  f"{row.get('estimatedHeightCount', '?')} estimated/unknown")
            if row.get("error"): print("    Unavailable: " + str(row["error"]))
    elif command == "library.show":
        document = data.get("document") or {}
        context = document.get("routeContext") or {}
        print(f"Library route: {data.get('routeId', '?')} | {document.get('routeName', '')} | "
              f"{len(document.get('waypoints', []))} points")
        print(f"Zone: {context.get('zoneName') or context.get('zoneIdCandidate') or 'unknown'} | "
              f"comparison {data.get('contextComparison', 'unknown')} (candidate evidence only)")
        from scripts.waypoint_measurements import document_measurements
        measured = sum(value is not None for value in document_measurements(document))
        print(f"Heights: {measured} measured, {len(document.get('waypoints', [])) - measured} estimated/unknown")
    elif command in {"library.save", "library.import"}:
        print(f"Saved library copy: {data.get('routeId', '?')} | {data.get('file', 'owned library')}")
        context = data.get("routeContext") or {}
        print(f"Zone: {context.get('zoneName') or context.get('zoneIdCandidate') or 'unknown'} (saved candidate context)")
    elif command.startswith("radar."):
        human_radar(data)
    elif command.startswith("beacons."):
        print(f"Beacon reader: {'running' if data.get('readerRunning') else 'stopped'}"
              + (" (closing)" if data.get('closing') else ''))
        print(f"Appearance: size {data.get('size', '?')}x, opacity {data.get('opacity', '?')}%, "
              f"labels {'on' if data.get('labels') else 'off'}, target {'on' if data.get('target') else 'off'}, "
              f"selected guide {'on' if data.get('guide') else 'off'}")
        human_pose(data.get("pose") or {})
        display = data.get("display") or {}
        if display:
            print("Beacon display: " + str(display.get("overlayReason") or display.get("feedHideReason") or
                                          ("frame available" if display.get("overlayHasFrame") else "no frame")))
        if data.get("qualification"): print(data["qualification"])
    elif command.startswith("guide."):
        index = data.get("activeIndex")
        point = index + 1 if isinstance(index, int) else "none"
        print(f"Manual guide: {data.get('status', '?')} | {data.get('direction', '?')} | next point {point}: {data.get('activeName') or ''}")
        if data.get("distance") is not None: print(f"Distance: {data['distance']} world units")
        print(f"Confirmed points: {len(data.get('completedIndices', []))} | no game input")
        if data.get("reason"): print("Reason: " + str(data["reason"]))
    elif command.startswith("trail."):
        if data.get("file"):
            print(f"Saved trail: {data['file']} | segment {data.get('segment', '?')} | {data.get('pointCount', '?')} points")
        else:
            segments = data.get("segments", [])
            print(f"Breadcrumb trail: {'recording' if data.get('active') else 'stopped'} | {len(segments)} retained segments | no game input")
            for segment in segments:
                print(f"  Segment {segment.get('number', '?')}: {segment.get('pointCount', len(segment.get('points', [])))} points")
    elif command in MOVEMENT:
        print(f"Movement: {data.get('operation', command)} | {data.get('state', '')}")
        if data.get("receipt"): print("Receipt: " + str(data["receipt"]))
        if data.get("failure"): print("Outcome: " + str(data["failure"].get("reason", data["failure"])))
        if data.get("stop"): print("STOP response: " + str(data["stop"].get("status", "unknown")) + "; use --json for release evidence")
    else:
        return False
    return True


def emit(envelope, machine=False):
    if machine:
        # Redirected Windows consoles may use a legacy encoding. JSON escapes
        # keep machine output valid UTF-8/ASCII even for Unicode UI messages.
        print(json.dumps(envelope, ensure_ascii=True, allow_nan=False, default=str))
        return
    command = envelope.get("command", "waypoints")
    data = envelope.get("data")
    if envelope.get("ok"):
        print(f"{command}: {envelope.get('status', 'completed')}"
              + (f" | session {envelope['sessionId']}" if envelope.get("sessionId") else ""))
        if data is not None and not human_data(command, data):
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        error = envelope.get("error") or {}
        print(f"{error.get('code', 'failed')}: {error.get('message', 'Operation failed')}", file=sys.stderr)
        if error.get("hint"): print(error["hint"], file=sys.stderr)
        if command in MOVEMENT and data: human_data(command, data)


def offline_route(path, operation):
    from scripts.physical_waypoints import route_points, validate_route_document
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_route_document(document)
    points = route_points(document["waypoints"])
    from scripts.waypoint_measurements import document_measurements
    measured = sum(value is not None for value in document_measurements(document))
    data = dict(file=str(path.resolve()), points=[dict(number=i, name=n, x=x, z=z) for i, (n,x,z) in enumerate(points, 1)],
                measuredCount=measured, estimatedCount=len(points)-measured,
                inputSent=False, qualification="Offline file validation; no live identity, terrain or playback admission.")
    if "recording" in document or measured == len(points):
        from scripts.waypoint_measurements import parse_projection_route
        data["projection"] = parse_projection_route(document)
    return result(operation, data=data)


def _launch(args, protocol):
    sessions = protocol.discover_sessions()
    selected_id = getattr(args, "session", None)
    existing = None
    state = None
    if selected_id is not None:
        existing = protocol.resolve_session(selected_id)
    elif args.pid is None:
        if len(sessions) > 1:
            raise protocol.CliError("ambiguous-session", "Multiple helpers are running; select --session ID or --pid PID.", exit_code=3)
        if sessions:
            existing = sessions[0]
    else:
        matches = []
        for candidate in sessions:
            reply = protocol.request(candidate, "status", {}, timeout=args.timeout)
            if not reply.get("ok"):
                raise protocol.CliError("session-status-unavailable", "Cannot inspect an existing helper's target; no additional helper launched.", exit_code=3)
            data = reply.get("data") or {}
            if (data.get("target") or {}).get("processId") == args.pid:
                matches.append((candidate, data))
        if len(matches) > 1:
            raise protocol.CliError("ambiguous-session", "Several helpers own this RIFT PID; specify --session ID.", exit_code=3)
        if matches:
            existing, state = matches[0]
    if existing is not None:
        if state is None:
            reply = protocol.request(existing, "status", {}, timeout=args.timeout)
            if not reply.get("ok"):
                return reply
            state = reply.get("data") or {}
        if args.pid is not None and (state.get("target") or {}).get("processId") != args.pid:
            raise protocol.CliError("session-target-mismatch", "The selected helper does not own --pid. Select its actual session or omit --session to open another target.", exit_code=3)
        if args.route is not None:
            route = state.get("route") or {}
            current = route.get("file") or route.get("path") or route.get("sourcePath") or state.get("routePath") or state.get("currentRoutePath")
            if current is None or Path(current).resolve() != args.route.resolve():
                raise protocol.CliError("route-load-required", "An existing helper has another route or no known source path.",
                                        "Use route load FILE [--discard] explicitly, then app open. No additional helper was launched.", exit_code=4)
        if args.basis is not None:
            raise protocol.CliError("basis-relaunch-required", "--basis applies only when opening a new helper; the selected helper is already running.", exit_code=4)
        shown = protocol.request(existing, "app.hide" if args.background else "app.show", {}, timeout=args.timeout)
        if not shown.get("ok"):
            return shown
        return result("app.open", data={"session":existing, "reused":True, "applied":shown}, session=existing["sessionId"])
    before = {s["sessionId"] for s in sessions}
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        raise protocol.CliError("launcher-unavailable", "pythonw.exe is unavailable", exit_code=3)
    launch_token = uuid.uuid4().hex
    command = [str(pythonw), str(ROOT / "scripts/launch_physical_waypoints.py"), "--cli", "--launch-token", launch_token]
    for flag, value in (("--physical-pid", args.pid), ("--route", args.route), ("--basis", args.basis)):
        if value is not None: command.extend((flag, str(value)))
    if args.background: command.append("--background")
    child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        sessions = [s for s in protocol.discover_sessions() if s["sessionId"] not in before and s.get("launchToken") == launch_token]
        if len(sessions) == 1: return result("app.open", data=sessions[0], session=sessions[0]["sessionId"])
        if child.poll() is not None:
            raise protocol.CliError("launch-failed", "Waypoints exited before publishing a session", exit_code=1)
        time.sleep(.1)
    raise protocol.CliError("outcome-unknown", "Launch deadline elapsed; the helper may still open. Inspect app list before retrying.", exit_code=5)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    machine = "--json" in argv or "--jsonl" in argv
    parser = build_parser()
    command = "help"
    try:
        if not argv:
            parser.print_help()
            return 0
        if argv[0] == "help":
            argv = argv[1:] + ["--help"]
        args = parser.parse_args(argv)
        if not hasattr(args, "operation"):
            getattr(args, "help_parser", parser).print_help()
            return 0
        command = args.operation
        args.timeout = getattr(args, "timeout", 150 if command in MOVEMENT else 10)
        if getattr(args, "json", False) and getattr(args, "jsonl", False):
            raise UsageError("--json and --jsonl are mutually exclusive")
        if getattr(args, "jsonl", False) and not (command == "status" and args.watch):
            raise UsageError("--jsonl requires status --watch (optionally --pose)")
        if command == "status" and args.watch and getattr(args, "json", False):
            raise UsageError("status --watch uses --jsonl, not --json")
        if command in MOVEMENT and not args.execute:
            raise UsageError("movement requires explicit --execute before dispatch")
        if command == "route.add":
            explicit = args.x is not None or args.z is not None
            if (args.current or args.target) and explicit:
                raise UsageError("--current/--target cannot be combined with explicit coordinates")
            if not (args.current or args.target) and (args.x is None or args.z is None):
                raise UsageError("route add requires --current, --target, or both --x and --z")
        if command == "route.update" and all(getattr(args,k) is None for k in ("name","x","z")):
            raise UsageError("route update requires a name or coordinate change")
        if command == "trail.save" and args.segment != "latest": args.segment = positive(args.segment)
        if command in {"route.list", "route.validate"} and args.file:
            envelope = offline_route(args.file, command)
        elif command == "receipt.show":
            raw = args.file.read_text(encoding="utf-8-sig")
            data = ([json.loads(row) for row in raw.splitlines() if row.strip()]
                    if args.file.suffix.lower() == ".jsonl" else json.loads(raw))
            envelope = result(command, data=data)
        elif command == "receipt.list":
            if not args.directory.is_dir(): raise ValueError("receipt directory does not exist")
            envelope = result(command, data={"files":[str(p.resolve()) for p in sorted({*args.directory.glob("waypoint-run-*.json"), *args.directory.glob("waypoint-input-*.jsonl")})], "inputSent":False})
        else:
            from scripts import waypoint_cli_protocol as protocol
            if command == "app.list": envelope = result(command, data={"sessions":protocol.discover_sessions()})
            elif command == "app.open": envelope = _launch(args, protocol)
            else:
                session = protocol.resolve_session(getattr(args, "session", None))
                payload = {k:str(v.resolve()) if isinstance(v,Path) else v for k,v in vars(args).items()
                           if k not in COMMON | {"operation", "group", "verb", "help_parser"} and v is not None}
                owned_id = uuid.uuid4().hex
                count = 0
                try:
                    while True:
                        envelope = protocol.request(session, command, payload, timeout=args.timeout, request_id=owned_id)
                        if command != "status" or not args.watch: break
                        emit(envelope, machine)
                        count += 1
                        if args.count and count >= args.count: return 0
                        time.sleep(args.interval)
                        owned_id = uuid.uuid4().hex
                except KeyboardInterrupt:
                    if command in MOVEMENT:
                        try:
                            stopped = protocol.request(session, "stop", {"requestId":owned_id}, timeout=15)
                            envelope = result(command, ok=False, status="cancelled", data={"stop":stopped},
                                              error={"code":"cancelled", "message":"Cancellation requested; inspect STOP result for release evidence."})
                        except Exception as exc:
                            envelope = result(command, ok=False, status="cancelled", error={"code":"cancel-release-unknown", "message":str(exc)})
                    else: envelope = result(command, ok=False, status="cancelled", error={"code":"cancelled", "message":"Cancelled."})
                    emit(envelope, machine)
                    return 130
        emit(envelope, machine)
        if envelope.get("ok"): return 0
        error = envelope.get("error") or {}
        return int(error.get("exitCode", 5 if error.get("code") == "expired" else 1))
    except SystemExit as exc:
        return int(exc.code or 0)
    except (UsageError, argparse.ArgumentTypeError) as exc:
        emit(result(command, ok=False, status="usage-error", error={"code":"usage", "message":str(exc), "hint":"Run rr2-waypoints help COMMAND."}), machine)
        return 2
    except KeyboardInterrupt:
        emit(result(command, ok=False, status="cancelled", error={"code":"cancelled", "message":"Cancelled."}), machine)
        return 130
    except Exception as exc:
        code = getattr(exc, "code", "operation-failed")
        emit(result(command, ok=False, status="failed", error={"code":code, "message":str(exc), "hint":getattr(exc,"hint",None)}), machine)
        return {"session-not-found":3, "ambiguous-session":3, "stale-session":3,
                "outcome-unknown":5}.get(code, getattr(exc, "exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
