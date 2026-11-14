#!/usr/bin/env python3
"""Headless survival-aware Waypoints CLI using the shared guarded runtime."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import signal
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.survival_profile import SurvivalProfileError, load_survival_profile
from scripts.waypoint_limits import MAX_WAYPOINTS
from scripts.waypoint_progress import ProgressError, RouteProgress, write_json_atomic


MAX_ROUTE_BYTES = 1024 * 1024
MAX_FAILURE_EVENT_BYTES = 256 * 1024


class UsageError(ValueError):
    pass


class ExecutionFailure(RuntimeError):
    def __init__(self, cause, receipt, status):
        super().__init__(str(cause))
        self.cause, self.receipt, self.status = cause, receipt, status


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)
        self.suggest_on_error = True
        self.color = False

    def error(self, message):
        raise UsageError(message)


def _path(value):
    return Path(value).expanduser().absolute()


def _profile_argument(parser):
    parser.add_argument("--profile", required=True, type=_path,
                        help="strict schemaVersion 1 survival profile JSON")


def _live_arguments(parser, *, route=False):
    from scripts import physical_rift
    from scripts.physical_waypoints import DEFAULT_BASIS
    parser.add_argument("--expected-host", required=True,
                        choices=physical_rift.SUPPORTED_HOSTS,
                        help="exact current physical host")
    parser.add_argument("--physical-pid", required=True, type=int,
                        help="exact current rift_x64 PID")
    _profile_argument(parser)
    parser.add_argument("--basis", type=_path, default=DEFAULT_BASIS,
                        help="movement calibration basis (default: repository AMD basis)")
    if route:
        parser.add_argument("--route", required=True, type=_path,
                            help=f"route JSON containing 1-{MAX_WAYPOINTS} waypoints")
        parser.add_argument("--checkpoint", type=_path,
                            help="durable progress JSON; defaults beside the route")
        parser.add_argument("--direction", choices=("forward", "reverse"),
                            default="forward")
        parser.add_argument("--face-waypoints", action=argparse.BooleanOptionalAction, default=True,
                            help="face each route waypoint before forward travel (default)")
        parser.add_argument("--execute", action="store_true",
                            help="authorize this bounded route execution")


def build_parser():
    parser = Parser(description=__doc__)
    parser.add_argument("--version", action="version", version="survival-waypoints 1")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser(
        "status-profile", help="validate and summarize a profile without reading RIFT")
    _profile_argument(status)
    preflight = commands.add_parser(
        "preflight", help="perform read-only identity, telemetry and control checks")
    _live_arguments(preflight)
    for name, help_text in (
        ("run", "start a new survival-aware route run"),
        ("resume", "resume the exact saved route checkpoint"),
    ):
        command = commands.add_parser(name, help=help_text)
        _live_arguments(command, route=True)
    return parser


def _read_route(path, direction):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UsageError(f"route is unreadable: {exc}") from None
    if len(raw) > MAX_ROUTE_BYTES:
        raise UsageError(f"route exceeds {MAX_ROUTE_BYTES} bytes")
    try:
        document = json.loads(raw.decode("utf-8-sig"),
                              parse_constant=lambda value: (_ for _ in ()).throw(
                                  ValueError("non-finite JSON number " + value)))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise UsageError(f"route is invalid JSON: {exc}") from None
    # RouteProgress owns the same bounded route/height/direction validation used
    # during real playback. Identity and recorded provenance are rechecked live.
    RouteProgress(document, direction, {
        "machine": "offline-validation", "gameBuildSha256": "offline-validation",
        "unitKey": "offline-validation"})
    return document


def _checkpoint(args):
    value = args.checkpoint or args.route.with_suffix(".survival-progress.json")
    if not value.parent.is_dir():
        raise UsageError(f"checkpoint parent does not exist: {value.parent}")
    if args.command == "resume" and not value.is_file():
        raise UsageError(f"resume checkpoint does not exist: {value}")
    return value


def _emit(value, *, stream=None):
    print(json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False),
          file=stream or sys.stdout, flush=True)


def _bounded_events(values):
    """Retain the newest useful event summaries within a finite receipt budget."""
    retained, used = [], 0
    for value in reversed(values[-256:]):
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
        if len(encoded) > 32 * 1024:
            value = {"type": value.get("type"), "status": value.get("status"),
                     "oversizedEvent": True, "originalBytes": len(encoded)}
            encoded = json.dumps(value, separators=(",", ":")).encode("ascii")
        if used + len(encoded) > MAX_FAILURE_EVENT_BYTES:
            break
        retained.append(value)
        used += len(encoded)
    retained.reverse()
    return retained


def _short_text(value, maximum=2000):
    if value is None:
        return None, False
    text = str(value)
    return (text, False) if len(text) <= maximum else (text[:maximum], True)


def _bounded_action_diagnostic(value):
    if value is None or not isinstance(value, dict):
        return None
    operation, operation_cut = _short_text(value.get("operation"), 256)
    stage, stage_cut = _short_text(value.get("stage"), 256)
    error = value.get("error") if isinstance(value.get("error"), dict) else {}
    error_type, type_cut = _short_text(error.get("type"), 256)
    reason, reason_cut = _short_text(error.get("reason"), 2000)
    raw = value.get("rawNativeReceipt")
    compact_raw, raw_cut = None, False
    if isinstance(raw, dict):
        compact_raw = {}
        for key in ("status", "reason", "errorType", "actionId"):
            if key in raw:
                compact_raw[key], cut = _short_text(raw[key], 1000)
                raw_cut = raw_cut or cut
        for key in ("cleanup", "inputSent", "releaseSucceeded", "responseVerified"):
            if key in raw:
                compact_raw[key] = raw[key] is True
        down = raw.get("desktopInputsDown")
        if isinstance(down, list):
            compact_raw["desktopInputsDown"] = [str(item)[:128] for item in down[:32]]
            raw_cut = raw_cut or len(down) > 32 or any(len(str(item)) > 128 for item in down[:32])
        target = raw.get("target")
        if isinstance(target, dict):
            compact_target = {}
            for key in ("machineName", "processId", "processStartUtcTicks",
                        "executableSha256", "windowHandle", "hwnd"):
                if key not in target:
                    continue
                item = target[key]
                if isinstance(item, str):
                    compact_target[key], cut = _short_text(item, 256)
                    raw_cut = raw_cut or cut
                elif isinstance(item, (int, float)) and not isinstance(item, bool):
                    compact_target[key] = item
                else:
                    raw_cut = True
            compact_raw["target"] = compact_target
        allowed = {"status", "reason", "errorType", "actionId", "cleanup", "inputSent",
                   "releaseSucceeded", "desktopInputsDown", "responseVerified", "target"}
        raw_cut = raw_cut or bool(set(raw) - allowed)
    return {"operation": operation, "stage": stage,
            "error": {"type": error_type, "reason": reason,
                      "truncated": operation_cut or stage_cut or type_cut or reason_cut},
            "nativeReceiptFromAttempt": value.get("nativeReceiptFromAttempt") is True,
            "rawNativeReceipt": compact_raw,
            "rawNativeReceiptTruncated": raw_cut}


def _bounded_runtime_status(value):
    result = dict(value)
    if "actionDiagnostic" in result:
        result["actionDiagnostic"] = _bounded_action_diagnostic(result["actionDiagnostic"])
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(encoded) <= 32 * 1024:
        return result
    return {**{key: result.get(key) for key in (
        "configured", "active", "state", "owner", "lastReason",
        "encounterCount", "inputSent")},
        "actionDiagnostic": result.get("actionDiagnostic"),
        "runtimeStatusTruncated": True}


@contextmanager
def signal_stop(stop):
    """Latch STOP on process signals while allowing owned cleanup to finish."""
    previous = {}
    signals = [signal.SIGINT]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)

    def latch(_number, _frame):
        stop.set()

    try:
        if threading.current_thread() is threading.main_thread():
            for item in signals:
                previous[item] = signal.signal(item, latch)
        yield
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


def _profile_summary(profile):
    return {"status": "valid", "schemaVersion": profile["schemaVersion"],
            "source": profile["source"], "binding": profile["binding"],
            "resourceKind": profile["resourceKind"],
            "coordinateBasisQualified": profile["coordinateBasis"] is not None,
            "roles": {key: value for key, value in profile["abilities"].items()
                      if value is not None},
            "actionCount": len(profile["actions"]), "inputSent": False}


def execute(args, *, adapter_factory=None, runtime_factory=None,
            playback=None, stop=None, emit=_emit, receipt_root=None):
    """Execute one parsed command; injectable dependencies keep tests offline."""
    profile = load_survival_profile(args.profile)
    if args.command == "status-profile":
        result = _profile_summary(profile)
        emit(result)
        return 0, result
    if args.physical_pid < 1:
        raise UsageError("--physical-pid must be positive")
    if args.command in ("run", "resume") and not args.execute:
        raise UsageError(f"{args.command} requires --execute before an adapter or input owner is created")
    document = _read_route(args.route, args.direction) if args.command in ("run", "resume") else None
    checkpoint = _checkpoint(args) if document is not None else None

    if adapter_factory is None:
        from scripts.physical_waypoints import PhysicalAdapter
        adapter_factory = PhysicalAdapter
    if runtime_factory is None:
        from scripts.waypoint_survival_runtime import WaypointSurvivalRuntime
        runtime_factory = WaypointSurvivalRuntime
    if playback is None:
        from scripts.waypoint_playback import play_route
        playback = play_route

    shared_stop = stop or threading.Event()
    runtime = runtime_factory()
    adapter = adapter_factory(args.expected_host, args.physical_pid, args.basis)
    receipt_directory = Path(receipt_root or ROOT / "artifacts")
    events = []

    def event(value):
        row = {"type": "event", **value}
        events.append(row)
        del events[:-256]
        emit(row)

    try:
        runtime.configure(args.profile, adapter)
        with signal_stop(shared_stop):
            if args.command == "preflight":
                value = runtime.preflight(adapter, shared_stop)
                result = {"status": "ready", "command": "preflight",
                          "preflight": value, "inputSent": False}
            else:
                legs, cursor = playback(
                    adapter, document, shared_stop, event,
                    runner=runtime.route_runner, checkpoint=checkpoint,
                    direction=args.direction, resume=args.command == "resume",
                    face_waypoints=args.face_waypoints)
                if shared_stop.is_set():
                    from scripts.physical_waypoints import Stopped
                    raise Stopped("STOP requested; owned cleanup completed")
                if getattr(adapter, "_continuous_input_release_fault", False):
                    raise RuntimeError("survival input release is unverified; movement remains blocked")
                sent = [leg.get("inputSent") for leg in legs if isinstance(leg, dict)]
                result = {"status": "arrived", "command": args.command,
                          "direction": cursor.direction, "nextIndex": cursor.next_index,
                          "waypointCount": len(cursor.ordered_points), "legs": legs,
                          "checkpoint": str(checkpoint),
                          "inputSent": (True if any(value is True for value in sent)
                                        else False if sent and all(value is False for value in sent)
                                        else None)}
    except BaseException as exc:
        from scripts.physical_waypoints import Stopped
        stopped = isinstance(exc, Stopped) or shared_stop.is_set()
        try:
            runtime_status = _bounded_runtime_status(runtime.status())
        except Exception as status_error:
            runtime_status = {"available": False, "reason": str(status_error)[:1000]}
        receipt_path = getattr(adapter, "input_receipt_path", None)
        failure = {
            "status": "stopped" if stopped else "refused",
            "error": {"type": type(exc).__name__, "reason": str(exc)[:4000]},
            "runtime": runtime_status,
            "checkpointPath": str(checkpoint) if checkpoint is not None else None,
            "latestNativeInputReceiptPath": str(receipt_path) if receipt_path else None,
            "events": _bounded_events(events),
            "exactTarget": getattr(adapter, "target", None),
            "releaseFault": bool(getattr(adapter, "_survival_input_release_fault", False)
                                 or getattr(adapter, "_survival_cleanup_uncertain", False)
                                 or getattr(adapter, "_continuous_input_release_fault", False)),
            "stopLatched": shared_stop.is_set(),
        }
        output = receipt_directory / ("survival-waypoint-failure-" + uuid.uuid4().hex + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(output, failure)
        raise ExecutionFailure(exc, output, failure["status"]) from exc

    output = receipt_directory / ("survival-waypoint-run-" + uuid.uuid4().hex + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output, result)
    summary = dict(result, receipt=str(output))
    emit(summary)
    return 0, summary


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        code, _ = execute(args)
        return code
    except UsageError as exc:
        _emit({"status": "usage-error", "reason": str(exc), "inputSent": False},
              stream=sys.stderr)
        return 2
    except (SurvivalProfileError, ProgressError, OSError, UnicodeError,
            json.JSONDecodeError) as exc:
        _emit({"status": "invalid", "reason": str(exc), "inputSent": False},
              stream=sys.stderr)
        return 2
    except ExecutionFailure as exc:
        _emit({"status": exc.status, "reason": str(exc.cause),
               "receipt": str(exc.receipt), "inputSent": None,
               "inputQualification": "Inspect the bounded failure receipt and native input receipt."},
              stream=sys.stderr)
        return 130 if exc.status == "stopped" else 3
    except Exception as exc:
        try:
            from scripts.physical_waypoints import Stopped
            stopped = isinstance(exc, Stopped)
        except ImportError:
            stopped = False
        _emit({"status": "stopped" if stopped else "refused",
               "reason": str(exc), "inputSent": None,
               "inputQualification": "Inspect native action and movement receipts."},
              stream=sys.stderr)
        return 130 if stopped else 3


if __name__ == "__main__":
    raise SystemExit(main())
