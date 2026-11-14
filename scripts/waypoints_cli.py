"""Console control for the existing Waypoints app; no independent game reader."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.waypoint_brand import APP_NAME, APP_VERSION
from scripts.waypoint_limits import MAX_TRIP_SECONDS
from scripts.waypoint_map import ZOOM_RADII

VERSION = APP_VERSION
MOVEMENT = {"move.to", "move.pick", "face", "route.run", "playback.start", "playback.resume"}
LONG_ROUTE_MOVEMENT = {"move.to", "move.pick", "route.run", "playback.start", "playback.resume"}
COMMON = {"session", "timeout", "json", "jsonl", "no_color"}
LONG_ROUTE_TIMEOUT = MAX_TRIP_SECONDS + 30
PREVIEW_RANGES = ", ".join(str(radius) for radius in ZOOM_RADII[:-1]) + f" or {ZOOM_RADII[-1]}"


def default_timeout(operation):
    """One timeout policy for parsing, help and dispatch."""
    return (LONG_ROUTE_TIMEOUT if operation in LONG_ROUTE_MOVEMENT else
            150 if operation in MOVEMENT else
            120 if operation == "view.save" else 10)


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


def bounded_integer(low, high):
    def convert(value):
        try:
            result = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("must be an integer") from None
        if not low <= result <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return result
    return convert


def bounded_text(maximum):
    def convert(value):
        if len(value) > maximum:
            raise argparse.ArgumentTypeError(f"must be at most {maximum} characters")
        return value
    return convert


def positive(value):
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer (one-based)") from None
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer (one-based)")
    return result


def common(parser, operation=None):
    # Suppressed defaults let an option before a group survive leaf parsing.
    parser.add_argument("--session", default=argparse.SUPPRESS, help="select the exact helper session ID")
    timeout_help = (f"seconds to wait; default {default_timeout(operation)} for this command" if operation else
                    f"seconds to wait; defaults: route playback {LONG_ROUTE_TIMEOUT}, "
                    "facing 150, view save 120, other commands 10")
    parser.add_argument("--timeout", type=bounded(.05, 3600), default=argparse.SUPPRESS, help=timeout_help)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="one versioned JSON result")
    output.add_argument("--jsonl", action="store_true", default=argparse.SUPPRESS, help="explicit status/pose watch JSON lines")
    parser.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS, help="plain output (the default)")


def example(operation):
    return {
        "route.load":"route load route.json --discard", "route.save":"route save route.json",
        "route.list":"route list --file route.json", "route.validate":"route validate --file route.json",
        "route.add":"route add --current --name Camp", "route.update":"route update 1 --current",
        "route.remove":"route remove 1", "route.reorder":"route reorder 1 --to 2",
        "route.select":"route select 1", "guide.start":"guide start --direction forward --from 1",
        "trail.save":"trail save trail.json --segment latest", "trail.clear":"trail clear --discard",
        "record.stop":"record stop recorded-route.json", "radar.set":"radar set --range 10 --opacity 85",
        "radar.move":"radar move --x 30 --y 50", "beacons.set":"beacons set --size 1 --labels on",
        "radar.reset-position":"radar reset-position",
        "beacons.reset":"beacons reset", "view.status":"view status",
        "diagnostics.status":"diagnostics status", "diagnostics.show":"diagnostics show",
        "diagnostics.events":"diagnostics events --level warning --limit 50",
        "diagnostics.copy":"diagnostics copy", "diagnostics.open":"diagnostics open",
        "move.to":"move to 123 456 --execute", "move.pick":"move pick --canvas-x 220 --canvas-y 120 --execute",
        "move.mode":"move mode --engine continuous",
        "face":"face 90 --execute",
        "playback.start":"playback start --direction forward --execute",
        "playback.resume":"playback resume --execute", "route.run":"route run --execute",
        "view.save":"view save view.json", "view.load":"view load view.json", "view.open":"view open view.json",
        "view.open-3d":"view open-3d view.json", "receipt.show":"receipt show waypoint-run-ID.json",
        "app.close":"app close --discard", "app.open":"app open --route route.json",
        "zone.refresh":"zone refresh", "route.tag-zone":"route tag-zone",
        "library.list":"library list --zone matching --search Camp",
        "library.save":"library save Camp --id camp", "library.import":"library import route.json --name Camp",
        "library.load":"library load camp --discard", "library.show":"library show camp",
        "library.select":"library select camp",
        "preview.status":"preview status", "preview.set":"preview set --range 10",
        "preview.fit":"preview fit", "preview.project":"preview project --canvas-x 220 --canvas-y 120",
        "pose.status":"pose status", "pose.set":"pose set --live on", "pose.refresh":"pose refresh",
    }.get(operation, operation.replace(".", " "))


def build_parser():
    parser = Parser(prog="rr2-waypoints", description=f"Control {APP_NAME} from a console.",
                    epilog="Examples: rr2-waypoints status; rr2-waypoints radar show; rr2-waypoints guide start --from 1\n"
                           "rr2-waypoints route list --file route.json; rr2-waypoints playback start --execute")
    common(parser)
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION} (rr2-waypoints)")
    groups = parser.add_subparsers(dest="group", title="Commands")
    leaves = {}

    def leaf(parent, name, operation, purpose, effects="Read-only; sends no game input."):
        p = parent.add_parser(name, help=purpose, description=purpose,
                              epilog=("Requires: no running helper; operates on local session metadata or explicit files.\n"
                                      if operation.startswith("receipt.") or operation in {"app.list", "app.open"}
                                      else "Requires: uses saved logs when no helper is running; select --session when several helpers exist.\n"
                                      if operation.startswith("diagnostics.")
                                      else "Requires: an unambiguous running Waypoints session; route list/validate support offline --file.\n")
                                     + f"Effects: {effects}\nDefaults: timeout {default_timeout(operation)} seconds; one-based points/segments.\n"
                                     f"Example: rr2-waypoints {example(operation)}",
                              formatter_class=argparse.RawDescriptionHelpFormatter)
        common(p, operation)
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
            p.add_argument("--pose", action="store_true", help="include the existing reader's qualified pose, source and sample age; reads no new pose")
            p.add_argument("--interval", type=bounded(.1, 60), default=1., help="watch interval seconds, default 1")
            p.add_argument("--count", type=positive, help="stop watch after this many reports")
    for group, verbs in {
        "app":"list open show hide close", "route":"list load save new add update remove reorder select undo validate run context tag-zone",
        "zone":"status refresh", "library":"list save import load show select",
        "preview":"status set fit project", "pose":"status set refresh",
        "diagnostics":"status show events copy open",
        "radar":"status show hide set move reset-position lock unlock", "beacons":"status show hide set reset",
        "guide":"status start stop", "trail":"status start stop list save clear", "record":"status start stop cancel",
        "move":"to pick mode", "playback":"start resume status", "view":"status save load open open-3d", "receipt":"list show"
    }.items():
        gp = groups.add_parser(group, help=f"{group.capitalize()} controls", description=f"{group.capitalize()} commands")
        common(gp)
        gp.set_defaults(help_parser=gp)
        sub = gp.add_subparsers(dest="verb", title="Commands")
        for verb in verbs.split():
            operation = f"{group}.{verb}"
            read_only = verb in {"status", "list", "validate"} or operation in {"receipt.show", "diagnostics.show", "diagnostics.events", "preview.project"}
            purpose = {
                "app.open":"Open Waypoints, or reuse the selected existing helper without replacing its route.",
                "app.show":"Show the selected helper window.", "app.hide":"Hide the selected helper window.",
                "app.close":"Close the selected helper after owned workers release; unsaved changes need --discard.",
                "route.add":"Add an estimated point with --x/--z, measured player XYZ with --current, or a qualified target candidate with --target.",
                "route.update":"Edit a point name/manual X/Z, or use --current to replace its coordinates with freshly measured player XYZ.",
                "route.select":"Select one waypoint, or use --clear to prepare the Add X/Z form; pending fields require --discard-draft.",
                "zone.status":"Show the current zone candidate and freshness; a candidate is not proof of the actual world instance.",
                "zone.refresh":"Read a fresh native zone candidate under the helper's current identity; not proof of the actual world instance.",
                "route.context":"Show the loaded route's saved zone binding and comparison with current candidate context.",
                "route.tag-zone":"Explicitly attach the current fresh zone candidate to a legacy route; not proof of the actual world instance.",
                "library.list":"List routes in the owned library, optionally filtering current zone comparisons and searching names, IDs or saved zone context.",
                "library.save":"Copy the loaded route into the owned library with a display name; retain its context.",
                "library.import":"Copy the explicit source file into the owned library, preserving its saved context and source file.",
                "library.load":"Load a library route into the helper; unsaved changes require --discard.",
                "library.show":"Inspect one owned library route, its zone context and measured/unknown heights.",
                "library.select":"Select a library entry and show its details without replacing the loaded route; clears filters if needed.",
                "preview.status":"Show the local route preview range, cached-pose availability and off-screen point summary.",
                "preview.set":"Set the local route preview range without reading RIFT or sending game input.",
                "preview.fit":f"Fit the local route preview to the loaded route using only the helper's cached finite pose; the preview remains capped at {ZOOM_RADII[-1]} units.",
                "preview.project":"Project owned-preview canvas pixels to flat world X/Z without reading RIFT or sending game input.",
                "pose.status":"Show Live pose refresh, current or cached sample freshness and the existing reader source.",
                "pose.set":"Turn the helper's Live pose refresh on or off; retained samples remain subject to freshness checks.",
                "pose.refresh":"Refresh pose with one fresh read through the existing native reader; sends no game input.",
                "beacons.show":"Start the owned shared beacon reader and wait for fresh pose; sends no game input.",
                "beacons.hide":"Stop the owned beacon reader and wait for its exit.",
                "beacons.set":"Adjust beacon appearance and optional target/guide layers; target changes can restart the owned reader and are refused during manual guide/trail use.",
                "beacons.reset":"Reset size, opacity and labels while preserving target, selected guide and enabled state.",
                "view.status":"Show focus/capture options and availability of the last image and 3D rerun assets.",
                "view.save":"Capture a JSON/image/3D bundle; every route point must have measured XYZ evidence.",
                "view.load":"Load saved image and 3D asset references into Scene & beacons without opening a viewer.",
                "view.open":"Open a saved JSON view manifest or image file.",
                "view.open-3d":"Open a saved JSON view manifest or exported .rrd recording in the 3D viewer.",
                "diagnostics.status":"Show diagnostics logging availability and the owned log path; saved logs work without a Waypoints window.",
                "diagnostics.show":"Print the current diagnostics report; saved logs work without a Waypoints window.",
                "diagnostics.events":"List recent structured log events with bounded severity and text filters; saved logs work without a Waypoints window.",
                "diagnostics.copy":"Copy diagnostics to the Windows clipboard; saved logs work without a Waypoints window.",
                "diagnostics.open":"Open the diagnostics log directory in Windows Explorer; saved logs work without a Waypoints window.",
                "record.start":"Start read-only route recording; capture continues until explicit stop or cancel.",
                "record.stop":"Stop recording and save its measured route at the explicit FILE.",
                "record.cancel":"Stop recording and discard its captured route.",
                "radar.show":"Show the compact radar, starting the owned shared reader when needed.",
                "radar.hide":"Hide the compact radar while retaining its range, opacity and position.",
                "radar.reset-position":"Remove the saved manual radar position and return it to its default game-relative location.",
                "guide.start":"Start passive arrival guidance with fresh confirmation for 0.2 seconds; waits up to 4 seconds for a fresh pose, then refuses without applying and requires an explicit retry.",
                "trail.start":"Start observing a breadcrumb trail from the existing owned pose feed.",
                "trail.stop":"Stop breadcrumb observation and retain its history.",
                "trail.save":"Export one observed trail segment to a separate existing-format route file.",
                "playback.start":"Start a new Forward or Reverse run at its route endpoint; replaces saved progress only after fresh admission. Faces before each leg and supports a full bounded long route.",
                "playback.resume":"Resume the validated saved direction and next unfinished waypoint. An explicit direction must match the saved direction. Faces before each leg and supports the remaining bounded long route.",
                "playback.status":"Show Forward, Reverse and Resume readiness from the helper's existing pose; execution rechecks live admission.",
                "route.run":"Run the loaded route from a one-based point using face-then-walk mode, with the full bounded long-route deadline.",
                "move.to":"Move to world X/Z using guarded face-then-walk mode.",
                "move.pick":"Project owned-preview canvas pixels and move there through the guarded route runner.",
                "move.mode":"Choose continuous held-forward or legacy pulse movement for subsequent runs.",
            }.get(operation, f"{verb.capitalize()} {group}.")
            effects = ("Read-only native candidate refresh; sends no game input." if operation in {"zone.refresh", "pose.refresh"}
                       else "Read-only; sends no game input." if read_only or operation in {"route.context", "library.show"}
                       else "Attaches fresh candidate provenance to the loaded route; sends no game input." if operation == "route.tag-zone"
                       else "Changes the helper's library selection only; sends no game input." if operation == "library.select"
                       else "Projects the helper's owned local map only; reads no new pose and sends no game input." if operation == "preview.project"
                       else "Changes only the local preview display; reads no new pose and sends no game input." if operation in {"preview.set", "preview.fit"}
                       else "Changes the helper's idle pose refresh setting; sends no game input." if operation == "pose.set"
                       else "Changes the helper's movement engine setting; sends no game input." if operation == "move.mode"
                       else "Writes a copy in the owned route library; sends no game input." if operation in {"library.save", "library.import"}
                       else "Sends guarded game input only with --execute; uses face-then-walk and waits for a terminal result." if operation in MOVEMENT
                       else "Starts the owned shared reader when needed; sends no game input." if operation in {"beacons.show", "radar.show", "guide.start", "trail.start"}
                       else "Removes only the saved manual radar position; retains range, opacity and enabled state; sends no game input." if operation == "radar.reset-position"
                       else "Changes helper visibility; sends no game input." if operation in {"app.show", "app.hide", "app.open"}
                       else "Writes the explicit JSON manifest and a new capture bundle; sends no game input." if operation == "view.save"
                       else "Loads saved asset references into the helper; opens no viewer and sends no game input." if operation == "view.load"
                       else "Writes diagnostics text to the Windows clipboard; does not change RIFT or send game input." if operation == "diagnostics.copy"
                       else "Opens the diagnostics directory in Windows Explorer; does not change RIFT or send game input." if operation == "diagnostics.open"
                       else "Opens a saved local asset in its viewer; sends no game input." if group == "view"
                       else "Changes helper state or the explicitly named file; sends no game input.")
            leaf(sub, verb, operation, purpose, effects)
    leaf(groups, "face", "face", "Face an absolute bearing in degrees (0 <= bearing < 360).",
         "Sends guarded turning input only with --execute; waits for a terminal result.")
    groups.add_parser("help", help="show the same help as COMMAND --help").add_argument("topic", nargs="*")

    def arg(op, *names, **kwargs): leaves[op].add_argument(*names, **kwargs)
    arg("pose.set", "--live", choices=("on", "off"), required=True,
        help="enable or disable the helper's Live pose refresh")
    arg("library.list", "--zone", choices=("all", "matching", "mismatch", "unknown"), default="all",
        help="candidate comparison with current zone; default all; matching does not prove a world instance")
    arg("library.list", "--search", help="case-insensitive text match in route name, ID or saved zone context; combines with --zone")
    arg("library.save", "name", help="display name for a new saved copy; an ID is generated unless --id is supplied")
    arg("library.import", "file", type=Path, help="explicit source route file to copy; retains saved context")
    arg("library.import", "--name", help="display name; defaults to source route name or filename")
    for op in ("library.save", "library.import"):
        arg(op, "--id", dest="route_id", help="library ID: 1-80 letters, digits, underscores or hyphens; starts with a letter or digit")
        arg(op, "--overwrite", action="store_true", help="explicitly allow replacement when --id names an existing entry")
    for op in ("library.load", "library.show", "library.select"):
        arg(op, "route_id", metavar="ID", help="owned library route ID")
    arg("library.load", "--discard", action="store_true", help="explicitly discard unsaved route changes")
    arg("preview.set", "--range", dest="range", type=number, choices=tuple(float(radius) for radius in ZOOM_RADII), required=True,
        help=f"preview radius in world units: {PREVIEW_RANGES}")
    for op in ("preview.project", "move.pick"):
        arg(op, "--canvas-x", dest="canvas_x", type=number, required=True,
            help="physical X pixel in the helper-owned local preview canvas")
        arg(op, "--canvas-y", dest="canvas_y", type=number, required=True,
            help="physical Y pixel in the helper-owned local preview canvas")
    arg("diagnostics.events", "--level", choices=("all", "warning", "error"), default="all",
        help="minimum severity: all, warning (includes errors), or error; default all")
    arg("diagnostics.events", "--limit", type=bounded_integer(1, 200), default=100,
        help="maximum newest matching events to return, 1-200; default 100")
    arg("diagnostics.events", "--search", type=bounded_text(200), default="",
        help="case-insensitive text match in event details, at most 200 characters")
    for op in ("route.load", "route.save", "trail.save", "record.stop", "view.save", "view.load", "view.open", "view.open-3d", "receipt.show"):
        arg(op, "file", type=Path, help="explicit file path; no file chooser")
    for op in ("route.save", "trail.save", "record.stop", "view.save"):
        arg(op, "--overwrite", action="store_true", help="allow replacement of an existing file")
    for op in ("route.load", "route.new"):
        arg(op, "--discard", action="store_true", help="explicitly discard unsaved route changes")
    arg("app.close", "--discard", action="store_true",
        help="explicitly discard unsaved route changes and retained breadcrumb trail history")
    for op in ("route.list", "route.validate"):
        arg(op, "--file", type=Path, help="read and inspect a route offline; no live session required")
    for op in ("route.new", "route.add", "route.update"):
        arg(op, "--name", help="waypoint/route name")
    add = leaves["route.add"].add_mutually_exclusive_group()
    add.add_argument("--current", action="store_true", help="capture current measured player XYZ position")
    add.add_argument("--target", action="store_true", help="capture the qualified selected-target candidate")
    arg("route.update", "--current", action="store_true",
        help="replace coordinates and height with a fresh measured player XYZ capture; may be combined with --name, not --x/--z")
    for op in ("route.add", "route.update"):
        for axis in "xz": arg(op, "--" + axis, type=number, help=f"world {axis.upper()} units; finite")
    for op in ("route.update", "route.remove", "route.reorder"):
        arg(op, "point", type=positive, help="one-based waypoint number")
    arg("route.select", "point", nargs="?", type=positive, help="one-based waypoint number; omit with --clear")
    arg("route.select", "--clear", action="store_true", help="clear selection to prepare a new Add X/Z point")
    arg("route.select", "--discard-draft", action="store_true",
        help="explicitly discard unapplied Edit waypoint fields before selecting the point")
    arg("route.reorder", "--to", type=positive, required=True, help="one-based destination position")
    for op in ("route.load", "route.save", "route.new", "route.add", "route.update", "route.remove", "route.reorder", "route.select", "route.undo"):
        arg(op, "--revision", type=int, help="refuse if the route revision changed")
    for op in ("guide.start", "playback.start", "playback.resume", "route.run"):
        arg(op, "--direction", choices=("forward", "reverse"), default=None if op == "playback.resume" else "forward",
            help="default: saved checkpoint direction; explicit value must match it" if op == "playback.resume"
                 else "route traversal order; default forward")
        if op in ("guide.start", "route.run"):
            arg(op, "--from", dest="from_point", type=positive, help="one-based starting waypoint; guide confirms fresh arrival for 0.2 seconds")
    arg("guide.start", "--radius", type=bounded(.05, 10),
        help="arrival radius in world units; defaults to the session's configured value (0.6 at startup)")

    for op in ("playback.start", "playback.resume"):
        arg(op, "--checkpoint", type=Path,
            help="select the helper's checkpoint path; Resume reads matching saved progress, Play saves a new run after admission")
    arg("radar.set", "--range", type=number, choices=(2., 5., 10., 20.), help="radar radius in world units: 2, 5, 10 or 20")
    for op in ("radar.set", "beacons.set"):
        arg(op, "--opacity", type=bounded(20, 100), help="opacity percent 20-100")
    for axis in "xy": arg("radar.move", "--" + axis, type=number, required=True, help=f"relative game-client {axis.upper()} pixels")
    arg("beacons.set", "--size", type=bounded(.5, 2), help="marker size multiplier 0.5-2")
    for flag in ("labels", "target", "guide"):
        arg("beacons.set", "--" + flag, choices=("on", "off"))
    arg("view.save", "--bring-forward", action="store_true",
        help="opt in to bringing RIFT forward for capture; default is focus-neutral")
    arg("view.save", "--nearby-units", action="store_true",
        help="opt in to sampling nearby units for this capture; default is no nearby-unit sample")
    arg("trail.save", "--segment", default="latest", help="one-based segment number or latest (default)")
    arg("trail.clear", "--discard", action="store_true", required=True, help="explicitly discard trail history")
    arg("move.to", "x", type=number, help="destination world X")
    arg("move.to", "z", type=number, help="destination world Z")
    arg("move.mode", "--engine", choices=("continuous", "pulse"), required=True,
        help="movement engine for subsequent runs: continuous (default) or legacy pulse")
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
        if data.get("displayPending"):
            print("Radar display pending: settings saved; visibility is unconfirmed. Keep RIFT or Waypoints foreground, then check radar status.")
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
    if "liveEnabled" in pose:
        print(f"Live pose: {'on' if pose['liveEnabled'] else 'off'}"
              + (f" | {'updating' if pose['updating'] else 'not updating'}" if "updating" in pose else "")
              + (f" | sample {pose['sampleStatus']}" if pose.get("sampleStatus") else ""))
    elif pose.get("sampleStatus"):
        print("Pose sample: " + str(pose["sampleStatus"]))
    if pose.get("sampledAtUtc"):
        print("Pose observed: " + str(pose["sampledAtUtc"]))
    position = pose.get("position")
    if pose.get("status") == "fresh" and isinstance(position, dict):
        print("Position: " + " / ".join(f"{axis.upper()} {position.get(axis, '?')}" for axis in "xyz")
              + f" | facing {pose.get('bearing', '?')} degrees")
    if pose.get("reason"):
        print("Pose reason: " + str(pose["reason"]))
    if pose.get("qualification"):
        print("Pose qualification: " + str(pose["qualification"]))


def human_controls(controls, *, stopping=False):
    latch = controls.get("stopLatched")
    latch_text = "latched" if latch is True else "clear" if latch is False else "unknown"
    active = controls.get("ownedActionActive")
    action = "active" if active is True else "idle" if active is False else "unknown"
    print(f"STOP: {latch_text} | owned action {action}"
          + (f" | F8 {controls['f8']}" if controls.get("f8") else ""))
    print(f"Key release evidence: {controls.get('keyReleaseEvidence') or 'not-measured'}"
          + f" | stationary evidence: {controls.get('stationaryEvidence') or 'not-measured'}")
    if stopping and controls.get("ownedActionEnded") is not None:
        print("Owned action ended: " + ("yes" if controls["ownedActionEnded"] else "no"))
    if stopping and controls.get("queuedRequestRetired"):
        print("Queued request retired: " + str(controls.get("requestId", "unknown")))
    operation = controls.get("result")
    if stopping and isinstance(operation, dict) and operation.get("receipt"):
        print("Receipt: " + str(operation["receipt"]))
    if stopping and controls.get("qualification"):
        print(str(controls["qualification"]))


def human_edit_draft(draft):
    if isinstance(draft, dict) and draft.get("pending"):
        point = draft.get("point") if draft.get("point") is not None else "unselected"
        validity = "valid" if draft.get("valid") else "invalid"
        reason = f" | {draft['reason']}" if draft.get("reason") else ""
        print(f"Edit draft: pending for point {point} | {validity}{reason} | apply it or select with --discard-draft")


def human_zone(context, *, label="Zone"):
    context = context or {}
    print(f"{label}: {context.get('zoneName') or context.get('zoneIdCandidate') or 'unknown'}"
          + (f" | source {context['source']}" if context.get("source") else "")
          + " | candidate; actual world instance unproven")


def _library_zone(context):
    context = context or {}
    name, candidate = context.get("zoneName"), context.get("zoneIdCandidate")
    return f"{name} [{candidate}]" if name and candidate else str(name or candidate or "unknown")


def _playback_readiness_line(label, readiness):
    """Compact, stable human rendering for one read-only Replay admission result."""
    readiness = readiness if isinstance(readiness, dict) else {}
    ready = readiness.get("ready") is True
    direction = readiness.get("direction") or label.casefold()
    complete = readiness.get("complete") is True
    number = readiness.get("nextPointNumber")
    cursor = "route complete" if complete else f"point {number}" if isinstance(number, int) and number > 0 else "cursor unavailable"
    name = readiness.get("nextName")
    cursor += f" ({name})" if not complete and isinstance(name, str) and name else ""
    completed, total = readiness.get("completedCount"), readiness.get("pointCount")
    progress = f" | {completed}/{total} points confirmed" if isinstance(completed, int) and isinstance(total, int) else ""
    remaining = readiness.get("remainingDistance")
    distance = f" | {remaining:.2f} units remaining" if isinstance(remaining, (int, float)) else ""
    reason = readiness.get("reason")
    detail = f" | {reason}" if isinstance(reason, str) and reason else ""
    start = readiness.get("startPointNumber")
    start_name = readiness.get("startName")
    endpoint = (f" | start point {start}" + (f" ({start_name})" if start_name else "")) if isinstance(start, int) else ""
    return f"{label}: {'complete' if complete else 'ready' if ready else 'blocked'} | {direction} | {cursor}{endpoint}{progress}{distance}{detail}"


def human_playback(data, *, compact=False):
    """Render the same GUI-owned readiness in both status and playback status."""
    playback = data if isinstance(data, dict) else {}
    readiness = playback.get("readiness") if isinstance(playback.get("readiness"), dict) else {}
    progress = playback.get("progress") if isinstance(playback.get("progress"), dict) else {}
    state = "active" if playback.get("active") else "idle"
    if compact:
        pieces = []
        for key, short in (("forward", "F"), ("reverse", "R"), ("resume", "Resume")):
            entry = readiness.get(key)
            if isinstance(entry, dict): pieces.append(f"{short} {'complete' if entry.get('complete') is True else 'ready' if entry.get('ready') is True else 'blocked'}")
        print(f"Replay: {state}" + (" | " + " | ".join(pieces) if pieces else ""))
        return
    print(f"Replay: {state} | face before each leg | checkpoint {playback.get('checkpoint', 'unavailable')}")
    if playback.get("active") and progress:
        index = progress.get("nextIndex")
        count = readiness.get(progress.get("direction"), {}).get("pointCount")
        if isinstance(index, int) and isinstance(count, int) and 0 <= index <= count:
            print(f"Active progress: {progress.get('direction', '?')} | {index}/{count} points confirmed")
    saved = readiness.get("resume")
    if isinstance(saved, dict) and saved.get("direction"):
        print(_playback_readiness_line("Saved progress", saved))
    for key, label in (("forward", "Forward"), ("reverse", "Reverse"), ("resume", "Resume")):
        if key in readiness:
            print(_playback_readiness_line(label, readiness[key]))


def human_preview(preview):
    """Render bounded local-preview state without implying terrain awareness."""
    radius = preview.get("radius", "?")
    visible = preview.get("visibleCount")
    total = preview.get("routeCount")
    offscreen = preview.get("offscreenCount")
    counts = (f" | {visible}/{total} points visible" if isinstance(visible, int) and isinstance(total, int)
              else f" | {total} route points" if isinstance(total, int) else "")
    if isinstance(offscreen, int):
        counts += f" | {offscreen} off-screen"
    print(f"Local preview: {radius} units{counts}")
    pose_status = preview.get("poseStatus", "available" if preview.get("poseAvailable") else "unavailable")
    age = preview.get("poseAgeSeconds")
    age_text = f" | {age:.2f}s old" if isinstance(age, (int, float)) else ""
    print(f"Preview pose: {pose_status}{age_text} | Fit {'available' if preview.get('fitAvailable') else 'unavailable'}")
    if preview.get("fitLimited"):
        required = preview.get("requiredRadius")
        detail = f"; route requires about {required:g} units" if isinstance(required, (int, float)) else ""
        print(f"Fit limited: preview is capped at {ZOOM_RADII[-1]} units{detail}")
    points = preview.get("offscreenPoints")
    if points:
        labels = []
        for point in points:
            if isinstance(point, dict):
                number, name = point.get("number"), point.get("name")
                labels.append(f"{number} ({name})" if number is not None and name else str(number or name or "?"))
            else:
                labels.append(str(point))
        print("Off-screen points: " + ", ".join(labels))
    if preview.get("qualification"):
        print(str(preview["qualification"]))


def human_data(command, data):
    if not isinstance(data, dict): return False
    if command in {"status", "doctor"}:
        target, app, route = data.get("target") or {}, data.get("app") or {}, data.get("route") or {}
        print(f"Host: {data.get('host', target.get('hostName', '?'))} | RIFT PID: {target.get('processId', 'unavailable')}")
        ready = data.get("ready", data.get("pose", {}).get("status") == "fresh")
        print(f"App: {'busy' if app.get('busy') else 'ready' if ready else 'waiting'} | "
              f"{'visible' if app.get('visible') else 'hidden'} | {app.get('state', '')}"
              + (f" | tab {app['tab']}" if app.get("tab") else ""))
        print(f"Route: {route.get('count', 0)} points | {'unsaved changes' if route.get('dirty') else 'saved'} | {route.get('file') or 'no file'}")
        if isinstance(data.get("movementEngine"), str):
            print("Movement engine: " + data["movementEngine"])
        human_edit_draft(route.get("editDraft"))
        human_pose(data.get("pose") or {})
        if isinstance(data.get("controls"), dict):
            human_controls(data["controls"])
        human_radar(data.get("radar") or {})
        if data.get("preview"):
            human_preview(data["preview"])
        if data.get("playback"):
            human_playback(data["playback"], compact=True)
        diagnostics = data.get("diagnostics")
        if isinstance(diagnostics, dict):
            available = diagnostics.get("loggingAvailable", diagnostics.get("available"))
            print(f"Diagnostics: {'logging available' if available is True else 'logging unavailable' if available is False else 'availability unknown'}"
                  + (f" | {diagnostics['logFile']}" if diagnostics.get("logFile") else ""))
        if data.get("zone"):
            zone = data["zone"]
            human_zone(zone.get("context", zone))
        if data.get("activeRequestId"): print("Active request: " + str(data["activeRequestId"]))
        for step in data.get("nextSteps", []): print("Next: " + str(step))
    elif command in {"pose.status", "pose.set", "pose.refresh"}:
        human_pose(data)
    elif command == "stop":
        human_controls(data, stopping=True)
    elif command in {"route.list", "route.validate"}:
        points = data.get("points", [])
        selected = set(data.get("selected", []))
        print(f"Route: {data.get('file') or 'loaded in helper'} | {len(points)} points | "
              f"{'unsaved changes' if data.get('dirty') else 'saved'} | revision {data.get('revision', 'offline')}")
        if selected: print("Selected: " + ", ".join(str(number) for number in sorted(selected)))
        human_edit_draft(data.get("editDraft"))
        if "measuredCount" in data:
            print(f"Heights: {data['measuredCount']} measured, {data['estimatedCount']} estimated/unknown")
        if data.get("preview"):
            human_preview(data["preview"])
        for p in points:
            height = next((h for h in data.get("heights",[]) if h.get("number")==p.get("number")),None)
            note = (" | "+height["label"]+" ["+height["heightKind"]+"]") if height else ""
            marker = "*" if p.get("number") in selected else " "
            print(f" {marker}{p.get('number')}. {p.get('name', '')}: X {p.get('x')} / Z {p.get('z')}{note}")
        if data.get("qualification"): print(data["qualification"])
    elif command in {"route.update", "route.add", "route.remove", "route.reorder", "route.select", "route.undo"}:
        selected = data.get("selected") or []
        if selected: print("Selected waypoint" + ("s" if len(selected) != 1 else "") + ": " + ", ".join(map(str, selected)))
        elif command == "route.select": print("Waypoint selection cleared; Add X/Z form is ready.")
        change = data.get("change")
        if isinstance(change, dict):
            details = []
            if change.get("nameChanged"): details.append("name updated")
            if change.get("coordinatesChanged"): details.append("coordinates updated")
            if change.get("measurementReplaced"): details.append("fresh measured XYZ captured")
            elif change.get("measurementDiscarded"): details.append("prior measured height discarded")
            if change.get("recordingDiscarded"): details.append("recording provenance discarded")
            print("Change: " + ("; ".join(details) if details else "no effective change"))
        if data.get("revision") is not None: print(f"Route revision: {data['revision']}")
    elif command in {"preview.status", "preview.set", "preview.fit"}:
        human_preview(data)
    elif command == "preview.project":
        projection = data.get("projection", data)
        print(f"Map projection: canvas X {projection.get('canvasX', '?')} / Y {projection.get('canvasY', '?')}"
              f" -> world X {projection.get('x', '?')} / Z {projection.get('z', '?')}")
        print("Height: unknown | terrain/clearance: unavailable | no game input")
        if projection.get("qualification"): print(str(projection["qualification"]))
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
        counts = (f"{data.get('shownCount', len(rows))} of {data['totalCount']} routes"
                  if "totalCount" in data else f"{len(rows)} routes")
        print(f"Route library: {counts} | zone comparison is candidate evidence only")
        if data.get("directory"): print("Directory: " + str(data["directory"]))
        filters = []
        zone_filter = data.get("filter", data.get("zone"))
        if zone_filter: filters.append("zone " + str(zone_filter))
        if data.get("search"): filters.append("search " + repr(data["search"]))
        if filters: print("Filters: " + " | ".join(filters))
        if data.get("selectedId"): print("Selected: " + str(data["selectedId"]))
        if not rows: print("No library routes match. Save the loaded route with library save NAME, or import FILE with library import FILE.")
        for row in rows:
            zone = _library_zone(row.get("routeContext"))
            print(f"  {row.get('id', '?')} | {row.get('name', '')} | zone {zone} ({row.get('contextStatus', 'unknown')}) | "
                  f"{row.get('waypointCount', '?')} points | heights {row.get('measuredHeightCount', '?')} measured, "
                  f"{row.get('estimatedHeightCount', '?')} estimated/unknown")
            if row.get("file") or row.get("path"): print("    File: " + str(row.get("file") or row["path"]))
            if row.get("error"): print("    Unavailable: " + str(row["error"]))
    elif command in {"library.show", "library.select"}:
        document = data.get("document") or {}
        row = data.get("row") or data
        route_id = data.get("routeId") or row.get("id", "?")
        context = document.get("routeContext") or row.get("routeContext") or {}
        count = row.get("waypointCount", len(document.get("waypoints", [])) if document else "?")
        print(f"Library route: {route_id} | {document.get('routeName') or row.get('name') or route_id} | {count} points")
        file = data.get("file") or row.get("file") or row.get("path")
        if file: print("File: " + str(file))
        print(f"Zone: {_library_zone(context)} | "
              f"comparison {data.get('contextComparison', row.get('contextStatus', 'unknown'))} (candidate evidence only)")
        if context.get("source"): print("Context source: " + str(context["source"]))
        if context.get("observedAtUtc"): print("Context observed: " + str(context["observedAtUtc"]))
        if row.get("modifiedAtUtc"): print("File modified: " + str(row["modifiedAtUtc"]))
        if isinstance(row.get("planarDistance"), (int, float)):
            print(f"Route distance: {row['planarDistance']:.2f} world units in X/Z")
        from scripts.waypoint_measurements import document_measurements
        try:
            measured = row.get("measuredHeightCount")
            estimated = row.get("estimatedHeightCount")
            if measured is None and document:
                measured = sum(value is not None for value in document_measurements(document))
                estimated = len(document.get("waypoints", [])) - measured
            print(f"Heights: {measured if measured is not None else '?'} measured, {estimated if estimated is not None else '?'} estimated/unknown")
        except (ValueError, TypeError, KeyError) as error:
            print("Heights: unavailable | " + str(error))
        if row.get("error") or data.get("error"): print("Unavailable: " + str(row.get("error") or data["error"]))
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
        visibility = data.get("visibility")
        if isinstance(visibility, dict):
            observed = "visible" if visibility.get("visible") is True else "hidden" if visibility.get("visible") is False else "unknown"
            state = visibility.get("state") or "unavailable"
            reason = f" | {visibility['reason']}" if visibility.get("reason") else ""
            print(f"Beacon visibility: {observed} | {state}{reason}")
        if data.get("qualification"): print(data["qualification"])
    elif command in {"view.status", "view.load"}:
        options = data.get("options") or {}
        readiness = data.get("readiness") or {}
        print(f"Capture options: {'bring RIFT forward' if options.get('bringForward') else 'focus-neutral'} | "
              f"nearby units {'on' if options.get('nearbyUnits') else 'off'}")
        if readiness:
            measured, total = readiness.get("measured", "?"), readiness.get("total", "?")
            reason = f" | {readiness['reason']}" if readiness.get("reason") else ""
            print(f"Capture readiness: {'ready' if readiness.get('ready') is True else 'blocked'} | "
                  f"{measured}/{total} measured points{reason}")
        print(f"Last image: {'available' if data.get('imageAvailable') else 'unavailable'}"
              + (f" | {data['image']}" if data.get('image') else ""))
        print(f"3D rerun: {'available' if data.get('rerunAvailable') else 'unavailable'}"
              + (f" | {data['rerun']}" if data.get('rerun') else ""))
        print("Last capture: " + str(data.get("lastCaptureState") or "none"))
        if data.get("lastCaptureError"):
            print("Capture error: " + str(data["lastCaptureError"]))
        if data.get("nearbySample") is not None:
            available = data.get("nearbyAvailable")
            state = "available" if available is True else "unavailable" if available is False else "availability unknown"
            print(f"Nearby sample: {state} | {data['nearbySample']}")
    elif command == "diagnostics.status":
        available = data.get("loggingAvailable", data.get("available"))
        scope = " | saved/offline logs" if data.get("offline") else ""
        print(f"Diagnostics logging: {'available' if available is True else 'unavailable' if available is False else 'unknown'}{scope}")
        if available is False and data.get("error"): print("Logging error: " + str(data["error"]))
        if data.get("logFile"): print("Log file: " + str(data["logFile"]))
        if data.get("directory"): print("Directory: " + str(data["directory"]))
    elif command == "diagnostics.events":
        entries = data.get("entries") if isinstance(data.get("entries"), list) else []
        shown = data.get("shownCount", len(entries))
        matched = data.get("matchedCount", shown)
        scope = "saved log" if data.get("offline") else "current log"
        print(f"Diagnostic events: {shown} shown / {matched} matched | {scope}")
        if not entries:
            print("No diagnostic events match the filters.")
        for entry in entries:
            timestamp = entry.get("timestamp") or "time unavailable"
            level = str(entry.get("level") or "info").upper()
            message = str(entry.get("message") or "(no message)").replace("\r", " ").replace("\n", " ")
            details = []
            for key, label in (("status", "status"), ("command", "command"), ("operation", "operation"),
                               ("reason", "reason"), ("code", "code"),
                               ("exceptionType", "exception"), ("exceptionMessage", "error"),
                               ("requestId", "request")):
                value = entry.get(key)
                if value not in (None, "") and str(value) not in message:
                    details.append(f"{label} {str(value).replace(chr(10), ' ')}")
            if entry.get("persisted") is False: details.append("memory only")
            suffix = " | " + " | ".join(details) if details else ""
            print(f"  {timestamp} | {level:<7} | {message}{suffix}")
        if any(entry.get("traceback") for entry in entries):
            print("Tracebacks are retained in --json output and the full diagnostics report.")
        if data.get("logFile"): print("Log file: " + str(data["logFile"]))
    elif command == "diagnostics.copy":
        print(f"Diagnostics copied: {data.get('characters', '?')} characters"
              + (f" | {data['logFile']}" if data.get("logFile") else ""))
    elif command == "diagnostics.open":
        print("Diagnostics directory opened: " + str(data.get("directory", "unknown")))
    elif command.startswith("guide."):
        index = data.get("activeIndex")
        point = index + 1 if isinstance(index, int) else "none"
        print(f"Manual guide: {data.get('status', '?')} | {data.get('direction', '?')} | next point {point}: {data.get('activeName') or ''}")
        if data.get("distance") is not None: print(f"Distance: {data['distance']} world units")
        radius = data.get("arrivalRadius")
        total = data.get("pointCount")
        confirmed = len(data.get("completedIndices", []))
        print(f"Confirmed points: {confirmed}" + (f"/{total}" if isinstance(total, int) else "")
              + (f" | arrival radius {radius} units" if radius is not None else "") + " | no game input")
        if data.get("heightWarning"):
            separation = data.get("heightSeparation")
            detail = f" ({separation:+.1f} units)" if isinstance(separation, (int, float)) else ""
            print("Floor warning: waypoint may be on another floor" + detail)
        if data.get("reason"): print("Reason: " + str(data["reason"]))
    elif command.startswith("trail."):
        if data.get("file"):
            print(f"Saved trail: {data['file']} | segment {data.get('segment', '?')} | {data.get('pointCount', '?')} points")
        else:
            segments = data.get("segments", [])
            print(f"Breadcrumb trail: {'recording' if data.get('active') else 'stopped'} | {len(segments)} retained segments | no game input")
            if data.get("discardedPointCount"):
                print(f"Retention: {data['discardedPointCount']} older samples discarded")
            for segment in segments:
                points = segment.get('pointCount', len(segment.get('points', [])))
                distance = segment.get('observedPathLength')
                detail = f" | {distance:.2f} units" if isinstance(distance, (int, float)) else ""
                if segment.get("exportable") is True:
                    readiness = f"ready to save as {segment.get('waypointCount', '?')} waypoints"
                elif segment.get("exportable") is False:
                    readiness = "not ready to save" + (f": {segment['exportReason']}" if segment.get("exportReason") else "")
                else:
                    readiness = "save readiness unknown"
                reason = f" | split: {segment['reason']}" if segment.get("reason") else ""
                print(f"  Segment {segment.get('number', '?')}: {points} samples{detail} | {readiness}{reason}")
    elif command == "playback.status":
        human_playback(data)
    elif command == "move.mode":
        print("Movement engine: " + str(data.get("movementEngine", data.get("engine", "unknown"))))
    elif command in MOVEMENT:
        print(f"Movement: {data.get('operation', command)} | {data.get('state', '')}")
        if data.get("receipt"): print("Receipt: " + str(data["receipt"]))
        if data.get("failure"): print("Outcome: " + str(data["failure"].get("reason", data["failure"])))
        if data.get("stop"):
            stopped = data["stop"]
            print("STOP response: " + str(stopped.get("status", "unknown")))
            if isinstance(stopped.get("data"), dict):
                human_controls(stopped["data"], stopping=True)
            if stopped.get("error"):
                print("STOP error: " + str(stopped["error"].get("message", stopped["error"])))
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
    if command == "diagnostics.show" and envelope.get("ok") and isinstance(data, dict):
        print(str(data.get("text", "")), end="" if str(data.get("text", "")).endswith("\n") else "\n")
        return
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


def offline_diagnostics(command, payload=None):
    """Use existing owned logs when startup failed before a helper was published."""
    from scripts.waypoint_diagnostics import existing_report, existing_status
    payload = payload or {}
    status = existing_status(ROOT)
    if command == "diagnostics.status":
        return result(command, data=status)
    if command == "diagnostics.show":
        text = existing_report(ROOT)
        return result(command, data={"text": text, **status})
    if command == "diagnostics.events":
        from scripts.waypoint_diagnostics import existing_events
        data = existing_events(ROOT, limit=payload.get("limit", 100),
                               level=payload.get("level", "all"), search=payload.get("search", ""))
        return result(command, data=data)
    if command == "diagnostics.copy":
        text = existing_report(ROOT)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(["clip.exe"], input=b"\xff\xfe" + text.encode("utf-16le"), check=True,
                       shell=False, creationflags=creationflags)
        return result(command, data={"copied": True, "characters": len(text),
                                     "logFile": status.get("logFile")})
    if command == "diagnostics.open":
        directory = Path(status["directory"])
        if not directory.is_dir():
            raise ValueError("diagnostics directory is unavailable")
        os.startfile(directory)
        return result(command, data={"opened": True, "directory": str(directory)})
    raise UsageError("unsupported offline diagnostics command")


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
        args.timeout = getattr(args, "timeout", default_timeout(command))
        if getattr(args, "json", False) and getattr(args, "jsonl", False):
            raise UsageError("--json and --jsonl are mutually exclusive")
        if getattr(args, "jsonl", False) and not (command == "status" and args.watch):
            raise UsageError("--jsonl requires status --watch (optionally --pose)")
        if command == "status" and args.watch and getattr(args, "json", False):
            raise UsageError("status --watch uses --jsonl, not --json")
        if command in MOVEMENT and not args.execute:
            raise UsageError("movement requires explicit --execute before dispatch")
        if command == "route.select" and (args.point is None) == (not args.clear):
            raise UsageError("route select requires one waypoint number or --clear")
        if command == "route.add":
            explicit = args.x is not None or args.z is not None
            if (args.current or args.target) and explicit:
                raise UsageError("--current/--target cannot be combined with explicit coordinates")
            if not (args.current or args.target) and (args.x is None or args.z is None):
                raise UsageError("route add requires --current, --target, or both --x and --z")
        if command == "route.update":
            explicit = args.x is not None or args.z is not None
            if args.current and explicit:
                raise UsageError("route update --current cannot be combined with --x/--z")
            if not args.current and all(getattr(args,k) is None for k in ("name","x","z")):
                raise UsageError("route update requires --name, --current, or a manual --x/--z coordinate change")
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
        elif command.startswith("diagnostics.") and getattr(args, "session", None) is None:
            from scripts import waypoint_cli_protocol as protocol
            sessions = protocol.discover_sessions()
            payload = ({"level": args.level, "limit": args.limit, "search": args.search}
                       if command == "diagnostics.events" else {})
            if not sessions:
                envelope = offline_diagnostics(command, payload)
            else:
                session = protocol.resolve_session(None)
                envelope = protocol.request(session, command, payload, timeout=args.timeout, request_id=uuid.uuid4().hex)
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
