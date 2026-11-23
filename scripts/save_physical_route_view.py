"""Save one guarded physical route view and optional offline RRD.

The caller owns desktop access. Explicit desktop capture requests pinned focus
without keys; the separate WGC path is focus-neutral. Capture never rebinds a
target, installs packages or opens a viewer. The separate viewer helper runs
only after an explicit user action.
"""
from __future__ import annotations

from copy import deepcopy
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess

from scripts import observe_physical, observe_target, physical_rift, physical_view_tools, plot_physical_waypoints
from scripts.live_physical_waypoints import load_route
from scripts.physical_turn_visual_pair import MAX_PNG_BYTES, MAX_RECEIPT_BYTES, read_receipt
from scripts.waypoint_progress import write_json_atomic
from scripts.waypoint_view_bundle import bundle_reference

ROOT = Path(__file__).resolve().parents[1]
TARGET_FIELDS = {"hostName", "processId", "processStartUtcTicks", "executablePath", "executableSha256", "hwnd"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def launch_saved_rerun(path):
    """Explicit user action: open one local saved recording in the optional viewer."""
    recording = Path(path)
    require(recording.is_absolute() and recording.suffix.casefold() == ".rrd"
            and not str(recording).startswith("\\\\"), "absolute-local-rerun-recording-required")
    require(recording.is_file() and recording.stat().st_size > 0, "saved-rerun-recording-unavailable")
    viewer, environment, _ = physical_view_tools.check_rerun_viewer()
    return subprocess.Popen([*viewer, "--bind", "127.0.0.1", "--port", "auto", str(recording)],
                            cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _relative_fields(mapping, directory, *fields):
    for key in fields:
        if mapping.get(key):
            mapping[key] = bundle_reference(directory, mapping[key])


def _save_manifest(directory, result):
    manifest = deepcopy(result)
    _relative_fields(manifest, directory, "route", "observation", "image", "projection", "focusReceipt")
    _relative_fields(manifest["rerun"], directory, "path")
    for source in manifest.get("nativeSources", {}).values():
        _relative_fields(source, directory, "retained")
    for side in ("before", "after"):
        entry = manifest.get("zoneContextCandidate", {}).get(side, {})
        _relative_fields(entry, directory, "source")
    sample = manifest.get("unitSample", {})
    _relative_fields(sample, directory, "path", "source")
    _relative_fields(sample.get("names", {}), directory, "path", "source", "receiptPath")
    manifest.update(bundleVersion=1, directory=".")
    write_json_atomic(directory / "view.json", manifest)


def _retain_capture_asset(path, directory, filename, limit):
    source = Path(path)
    require(source.is_absolute() and source.is_file() and not source.is_symlink()
            and 0 < source.stat().st_size <= limit, "invalid-capture-source")
    source = source.resolve()
    if not source.is_relative_to(directory.resolve()):
        with source.open("rb") as original, (directory / filename).open("xb") as retained:
            shutil.copyfileobj(original, retained)
        source = directory / filename
    return bundle_reference(directory, source)


def _retain_wgc_frame(observation, directory):
    original_image, original_receipt = Path(observation["image"]), Path(observation["receipt"])
    receipt, digest = read_receipt(original_receipt)
    require(Path(receipt["outputPath"]).resolve() == original_image.resolve(), "visual-receipt-path-mismatch")
    image = _retain_capture_asset(original_image, directory, "frame.png", MAX_PNG_BYTES)
    receipt_path = _retain_capture_asset(original_receipt, directory, "frame.receipt.json", MAX_RECEIPT_BYTES)
    observation.update(image=image, receipt=receipt_path,
                       retainedFrame={"originalOutputPath": receipt["outputPath"], "receiptSha256": digest})


def _retain_native_sources(observation, directory, sources):
    bracket = observation.get("nativeFacing")
    if not isinstance(bracket, dict):
        return
    for field, filename in (("beforeOutput", "native-before.json"), ("afterOutput", "native-after.json")):
        original = bracket.get(field)
        if original is None:
            continue
        require(isinstance(original, str) and original, "invalid-native-source-path")
        source, retained = Path(original), directory / filename
        sources[field] = {"source": original}
        require(source.is_absolute(), "absolute-native-source-required")
        raw = source.read_bytes()
        sources[field]["sha256"] = hashlib.sha256(raw).hexdigest()
        with retained.open("xb") as stream:
            stream.write(raw)
        sources[field]["retained"] = str(retained)
        bracket[field] = filename


def _zone_context(selection, route, path, *, native_reader=None):
    """Optional new acquisition only; retain failures without borrowing old context."""
    entry = {"status": "unavailable", "source": str(path)}
    try:
        receipt = physical_rift.read_native(selection, "zone-context", output=path, native_reader=native_reader)
        entry["receipt"] = deepcopy(receipt)
        require(receipt.get("status") == "complete", receipt.get("reason", "zone-acquisition-unavailable"))
        require(receipt.get("target") == selection["target"], "zone-target-identity-mismatch")
        require(receipt.get("nativeOutput") == str(path), "zone-source-path-mismatch")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == receipt.get("nativeSourceSha256"), "zone-source-hash-mismatch")
        report = plot_physical_waypoints._read(path)
        values = physical_rift._native_values("zone-context", report)
        identity, target = report["observation"]["identity"], selection["target"]
        require(identity["processId"] == target["processId"]
                and str(identity["processStartUtcTicks"]) == target["processStartUtcTicks"]
                and identity["executableSha256"].casefold() == target["executableSha256"].casefold(),
                "zone-source-identity-mismatch")
        require(values == receipt.get("nativeValues"), "zone-source-values-mismatch")
        entry.update(status=values["status"], reason=values["reason"], sha256=digest, values=values,
                     startedAtUtc=values["startedAtUtc"], sampledAtUtc=values["sampledAtUtc"],
                     routePlayerMatches=values["selfKey"] == route["identity"]["unitKey"])
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        entry.update(status="unavailable", reason=str(error))
    return entry


def _compare_zone_context(before, after):
    result = {"status": "unavailable", "before": before, "after": after,
              "worldInstanceStatus": "unavailable",
              "qualification": "Zone-context candidates only; API correspondence, passive freshness and uninterrupted equality unqualified; no movement or map-reuse authority."}
    for entry in (before, after):
        if entry.get("sha256") is not None:
            try:
                require(hashlib.sha256(Path(entry["source"]).read_bytes()).hexdigest() == entry["sha256"],
                        "zone-source-changed-after-acquisition")
            except (ValueError, OSError) as error:
                entry.update(status="unavailable", reason=str(error))
    if before["status"] != "available-candidate" or after["status"] != "available-candidate":
        result["reason"] = "zone-candidate-unavailable"
        return result
    if physical_rift._utc_tick_order_key(before["sampledAtUtc"]) > physical_rift._utc_tick_order_key(after["startedAtUtc"]):
        result["reason"] = "zone-acquisition-order-invalid"
        return result
    fields = ("rawZoneKey", "zoneIdCandidate", "selfKey")
    matches = (all(before["values"][field] == after["values"][field] for field in fields)
               and before["routePlayerMatches"] and after["routePlayerMatches"])
    result.update(status="matching-candidates" if matches else "changed-candidates",
                  reason="matching-zone-candidates-not-world-proof" if matches else "zone-or-player-candidate-changed")
    return result


def _unit_names_sample(selection, values, positions, directory, *, native_reader=None):
    """One optional explicit batch for only the positions already chosen for display."""
    source, wrapper = directory / "unit-names-native.json", directory / "unit-names-sample.json"
    entry = {"status": "unavailable"}
    chosen = sorted((row for row in values["units"] if row["unitKey"] != values["selfKey"]
                     and row["horizontalDistanceCandidate"] <= 35),
                    key=lambda row: (row["horizontalDistanceCandidate"], int(row["unitKey"])))[:18]
    keys = [row["unitKey"] for row in chosen]
    if not keys:
        return dict(entry, reason="no-displayed-units")
    try:
        receipt = physical_rift.read_native(selection, "unit-names", output=source, unit_keys=keys,
                                            native_reader=native_reader)
        retained = deepcopy(receipt)
        if retained.get("nativeOutput") == str(source):
            retained["nativeOutput"] = source.name
        write_json_atomic(wrapper, retained)
        entry["receiptPath"] = str(wrapper)
        require(receipt.get("status") == "complete", receipt.get("reason", "unit-names-unavailable"))
        require(receipt.get("workflow") == "physical" and receipt.get("nativeRead") == "unit-names"
                and receipt.get("target") == selection["target"]
                and str(receipt.get("ownerHost", "")).casefold() == selection["target"]["hostName"].casefold(),
                "unit-names-wrapper-identity-mismatch")
        require(receipt.get("nativeOutput") == str(source), "unit-names-source-path-mismatch")
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(receipt.get("nativeSourceSha256") == digest, "unit-names-source-hash-mismatch")
        report = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=plot_physical_waypoints.unique_fields,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite-json")))
        names = physical_rift._native_values("unit-names", report)
        identity, target = report["observation"]["identity"], selection["target"]
        require(identity["processId"] == target["processId"]
                and str(identity["processStartUtcTicks"]) == target["processStartUtcTicks"]
                and identity["executableSha256"].casefold() == target["executableSha256"].casefold(),
                "unit-names-source-identity-mismatch")
        require(names == receipt.get("nativeValues") and names["selfKey"] == values["selfKey"]
                and [row["unitKey"] for row in names["rows"]] == keys, "unit-names-source-values-mismatch")
        stamp = physical_rift._utc_tick_order_key
        require(stamp(positions["completedAtUtc"]) <= stamp(names["startedAtUtc"]),
                "unit-names-acquisition-order-mismatch")
        owners = {row["unitKey"]: row["entityAddressDecimal"] for row in positions["rows"]}
        require(all(row["status"] != "available-candidate" or owners[row["unitKey"]] == row["entityAddressDecimal"]
                    for row in names["rows"]), "unit-names-position-owner-mismatch")
        entry.update(status="saved", path=str(wrapper), source=str(source), sha256=digest)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        entry["reason"] = str(error)
    return entry


def _unit_sample(selection, route, directory, *, native_reader=None):
    """Retain one independent optional scan bound to the captured process and player."""
    source, wrapper = directory / "units-native.json", directory / "units-sample.json"
    entry = {"status": "unavailable"}
    try:
        receipt = physical_rift.read_native(selection, "unit-positions", output=source,
                                            unit_limit=512, start_bucket=0, native_reader=native_reader)
        require(receipt.get("status") == "complete", receipt.get("reason", "unit-acquisition-unavailable"))
        require(receipt.get("workflow") == "physical" and receipt.get("nativeRead") == "unit-positions"
                and str(receipt.get("ownerHost", "")).casefold() == route["identity"]["machine"].casefold(),
                "unit-wrapper-identity-mismatch")
        target = selection["target"]
        require(receipt.get("target") == target, "unit-target-identity-mismatch")
        require(receipt.get("nativeOutput") == str(source), "unit-source-path-mismatch")
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        report = plot_physical_waypoints._read(source)
        values = physical_rift._native_values("unit-positions", report)
        identity = report["observation"]["identity"]
        require(identity["processId"] == target["processId"]
                and str(identity["processStartUtcTicks"]) == target["processStartUtcTicks"]
                and identity["executableSha256"].casefold() == target["executableSha256"].casefold(),
                "unit-source-identity-mismatch")
        require(values == receipt.get("nativeValues"), "unit-source-values-mismatch")
        require(values["selfKey"] == route["identity"]["unitKey"], "unit-route-player-mismatch")
        retained = deepcopy(receipt)
        retained["nativeOutput"] = source.name
        retained["nativeSourceSha256"] = digest
        names = _unit_names_sample(selection, values, report["observation"], directory, native_reader=native_reader)
        retained["nameSample"] = deepcopy(names)
        _relative_fields(retained["nameSample"], directory, "path", "source", "receiptPath")
        write_json_atomic(wrapper, retained)
        entry.update(status="saved", path=str(wrapper), source=str(source), sha256=digest, names=names)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        entry["reason"] = str(error)
    return entry


def _optional_rerun(route_path, observation_path, directory, enabled, *, desktop=False, unit_sample=None):
    if not enabled:
        return {"status": "unavailable", "reason": "not-requested"}
    output = directory / "view.rrd"
    environment = dict(os.environ, CI="1")
    environment.pop("FORCE_RERUN_ANALYTICS", None)
    try:
        python = physical_view_tools.local_python(os.environ.get("RR2_RERUN_PYTHON"),
                                                 physical_view_tools.VISUALIZATION_PYTHON,
                                                 "invalid-rerun-python-path")
        if not python.is_file():
            return {"status": "unavailable", "reason": "visualization-environment-unavailable"}
        command = [str(python), str(ROOT / "scripts/export_physical_rerun.py"),
            "--route", str(route_path), "--desktop-pair" if desktop else "--observation", str(observation_path),
            "--output", str(output)]
        if unit_sample is not None:
            command.extend(["--unit-sample", str(unit_sample)])
        completed = subprocess.run(command,
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        lines = completed.stdout.splitlines()
        summary = json.loads(lines[-1]) if lines else {}
        require(completed.returncode == 0 and summary.get("status") == "offline-rerun-evidence-export"
                and summary.get("output") == str(output) and output.is_file() and output.stat().st_size > 0,
                summary.get("reason") or "rerun-export-failed")
        return {"status": "saved", "path": str(output)}
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        return {"status": "failed", "reason": str(error)}


def _monitor_name(hwnd):
    """Get the current Windows display name; never assume its origin or index."""
    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT),
                    ("dwFlags", W.DWORD), ("szDevice", W.WCHAR * 32)]
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.MonitorFromWindow.argtypes, user.MonitorFromWindow.restype = [W.HWND, W.DWORD], W.HANDLE
    user.GetMonitorInfoW.argtypes, user.GetMonitorInfoW.restype = [W.HANDLE, ctypes.POINTER(MonitorInfo)], W.BOOL
    monitor = user.MonitorFromWindow(hwnd, 0)
    info = MonitorInfo(); info.cbSize = ctypes.sizeof(info)
    require(monitor and user.GetMonitorInfoW(monitor, ctypes.byref(info)), "target-display-unavailable")
    return info.szDevice


def _desktop_capture(host, pid, pinned, directory, result, *, native_reader=None):
    observe_physical.require_clear_desktop_turn()
    capture_python = physical_view_tools.local_python(os.environ.get("RR2_DXCAM_PYTHON"),
                                                       physical_view_tools.CAPTURE_PYTHON,
                                                       "invalid-dxcam-python-path")
    require(capture_python.is_file(), "desktop-capture-environment-unavailable")
    executable = physical_rift._native_reader_path(native_reader)
    probe_script = str(ROOT / "scripts/probe_dxcam_native_pair.py")
    reader_args = ("--native-reader", str(executable)) if native_reader is not None else ()
    dependencies = subprocess.run([str(capture_python), probe_script, "--check-dependencies",
                                  "--expected-host", host, *reader_args],
                                  cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        report = json.loads(dependencies.stdout)
    except ValueError as error:
        raise ValueError("desktop-capture-dependency-check-failed") from error
    require(isinstance(report, dict), "desktop-capture-dependency-check-failed")
    result["desktopDependencies"] = report
    require(dependencies.returncode == 0 and report.get("status") == "ready",
            report.get("reason", "desktop-capture-dependency-check-failed"))
    observe_physical.require_clear_desktop_turn()
    result.update(focusRequested=True, focusMayChange=True, focusChanged=None)
    command = [str(executable), "move-key", "--focus-only", "--pid", str(pid),
               "--expect-start-ticks", pinned["processStartUtcTicks"], "--expect-sha256", pinned["executableSha256"],
               "--expect-hwnd", hex(pinned["hwnd"]), "--json"]
    focused = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    focus = json.loads(focused.stdout)
    write_json_atomic(directory / "focus.json", focus)
    result["focusReceipt"] = str(directory / "focus.json")
    require(focused.returncode == 0 and focus.get("status") == "focused-target"
            and focus.get("inputSent") is False and focus.get("desktopInputsDown") == [],
            focus.get("reason", "focus-only-unavailable"))
    target = focus.get("target", {})
    require(target.get("machineName", "").casefold() == host.casefold()
            and target.get("processId") == pid
            and str(target.get("processStartUtcTicks")) == pinned["processStartUtcTicks"]
            and target.get("executablePath", "").casefold() == pinned["executablePath"].casefold()
            and target.get("executableSha256", "").casefold() == pinned["executableSha256"].casefold()
            and int(target.get("windowHandle", "0"), 16) == pinned["hwnd"]
            and target.get("isForeground") is True, "focus-target-identity-mismatch")
    result["focusChanged"] = focus.get("focusAttempt") is not None
    display = _monitor_name(pinned["hwnd"])
    capture = directory / "capture"
    command = [str(capture_python), probe_script,
               "--expected-host", host, "--physical-pid", str(pid), "--display", display,
               "--output", str(capture), "--timeout", "10",
               "--expect-start-ticks", pinned["processStartUtcTicks"],
               "--expect-sha256", pinned["executableSha256"], "--expect-hwnd", hex(pinned["hwnd"]), *reader_args]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    pair_path = capture / "pair.json"
    require(pair_path.is_file(), "desktop-pair-unavailable: " + completed.stdout[-1024:])
    pair = plot_physical_waypoints._read(pair_path)
    require(completed.returncode == 0 and pair.get("status") == "stable-native-composite-event-candidate",
            pair.get("reason", "desktop-pair-withheld"))
    require(pair.get("targetBefore") == pinned and pair.get("targetAfter") == pinned,
            "captured-target-identity-mismatch")
    sources = {}
    for number, (field, filename) in enumerate((("nativeBeforeOutput", "native-before.json"),
                                               ("nativeAfterOutput", "native-after.json"))):
        source = pair["nativeSources"][number]
        require(source["path"] == pair[field], "desktop-native-source-mismatch")
        raw = Path(source["path"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == source["sha256"], "desktop-native-source-hash-mismatch")
        retained = directory / filename
        with retained.open("xb") as stream:
            stream.write(raw)
        sources[field] = dict(source=source["path"], sha256=source["sha256"], retained=str(retained))
        source["path"] = pair[field] = filename
    pair["retainedNativeSources"] = deepcopy(sources)
    for source in pair["retainedNativeSources"].values():
        _relative_fields(source, directory, "retained")
    pair["image"] = _retain_capture_asset(pair["image"], directory, "frame.png", MAX_PNG_BYTES)
    pair.update(bundleVersion=1, report="desktop-pair.json")
    write_json_atomic(directory / "desktop-pair.json", pair)
    result.update(nativeSources=sources, requestedDisplay=display, sourceKind="desktop-composite-event-candidate")
    return directory / "desktop-pair.json"


def save_route_view(expected_host, physical_pid, document, output, *, expected_target, export_rerun=True,
                    capture_backend="wgc", include_units=False, native_reader=None):
    """Return saved-route-view-candidate or blocked, retaining acquired evidence.

    Output is a fresh absolute directory. Full recorded heights and exact caller
    process/window identity are mandatory. Optional Rerun failure is nonfatal.
    """
    result = {"status": "blocked", "inputSent": False, "focusChanged": False,
              "rerun": {"status": "unavailable", "reason": "core-view-unavailable"}}
    directory = None
    created = False
    try:
        directory = Path(output)
        result["directory"] = str(directory)
        require(directory.is_absolute() and not directory.exists() and directory.parent.is_dir(),
                "fresh-absolute-output-directory-required")
        require(physical_rift.valid_host_name(expected_host)
                and expected_host.casefold() == socket.gethostname().casefold(), "host-mismatch")
        require(type(physical_pid) is int and 1 <= physical_pid <= 4294967295, "explicit-physical-pid-required")
        require(type(export_rerun) is bool, "invalid-export-rerun-option")
        require(type(include_units) is bool, "invalid-include-units-option")
        require(capture_backend in ("wgc", "desktop"), "explicit-capture-backend-required")
        if native_reader is not None:
            native_reader = physical_rift._native_reader_path(native_reader)
            require(native_reader.is_file(), "native-reader-not-built")
        pinned = deepcopy(expected_target)
        require(isinstance(pinned, dict) and set(pinned) == TARGET_FIELDS
                and isinstance(pinned["hostName"], str) and pinned["hostName"].casefold() == expected_host.casefold()
                and type(pinned["processId"]) is int and pinned["processId"] == physical_pid
                and isinstance(pinned["processStartUtcTicks"], str) and pinned["processStartUtcTicks"].isdecimal()
                and int(pinned["processStartUtcTicks"]) > 0
                and isinstance(pinned["executableSha256"], str)
                and re.fullmatch(r"[a-fA-F0-9]{64}", pinned["executableSha256"]) is not None
                and isinstance(pinned["executablePath"], str) and pinned["executablePath"]
                and type(pinned["hwnd"]) is int and pinned["hwnd"] > 0, "complete-expected-target-required")
        selection = physical_rift.select_physical(expected_host, physical_pid)
        require(selection.get("status") == "ready", selection.get("reason", "physical-selection-unavailable"))
        require(selection.get("target") == pinned, "expected-target-identity-mismatch")
        directory.mkdir()
        created = True
        route_path, observation_path = directory / "route.json", directory / "observation.json"
        write_json_atomic(route_path, deepcopy(document))
        route = load_route(route_path)
        require(route["identity"]["machine"].casefold() == expected_host.casefold()
                and route["identity"]["gameBuildSha256"].casefold() == pinned["executableSha256"].casefold(),
                "route-host-build-mismatch")
        result["target"] = pinned
        result["route"] = str(route_path)
        result["recordingIdentity"] = route["recordingIdentity"]
        result["provenanceKind"] = route["provenanceKind"]
        result["captureBackend"] = capture_backend
        zone_before = _zone_context(selection, route, directory / "zone-before.json", native_reader=native_reader)
        try:
            if capture_backend == "desktop":
                observation_path = _desktop_capture(expected_host, physical_pid, pinned, directory, result,
                                                    native_reader=native_reader)
                result["observation"] = str(observation_path)
            else:
                observation = deepcopy(observe_target.observe("physical-" + expected_host.lower(), expected_host,
                    output=directory / "capture", physical_pid=physical_pid,
                    native_facing=True, physical_capture_backend="wgc", native_reader=native_reader))
                result["nativeSources"] = {}
                try:
                    _retain_native_sources(observation, directory, result["nativeSources"])
                    if (observation.get("status") == "verified-awaiting-visual-review"
                            and observation.get("target") == pinned):
                        _retain_wgc_frame(observation, directory)
                finally:
                    observation["retainedNativeSources"] = deepcopy(result["nativeSources"])
                    for source in observation["retainedNativeSources"].values():
                        _relative_fields(source, directory, "retained")
                    write_json_atomic(observation_path, observation)
                    result["observation"] = str(observation_path)
                require(observation.get("status") == "verified-awaiting-visual-review",
                        observation.get("reason", "physical-observation-unavailable"))
                require(observation.get("target") == pinned, "captured-target-identity-mismatch")
        finally:
            zone_after = _zone_context(selection, route, directory / "zone-after.json", native_reader=native_reader)
            result["zoneContextCandidate"] = _compare_zone_context(zone_before, zone_after)
        require(result["zoneContextCandidate"]["status"] != "changed-candidates", "context-changed-candidate")
        if include_units:
            result["unitSample"] = _unit_sample(selection, route, directory, native_reader=native_reader)
        unit_sample = result.get("unitSample", {}).get("path")
        desktop = capture_backend == "desktop"
        render = plot_physical_waypoints.render_desktop_pair if desktop else plot_physical_waypoints.render
        projection = render(observation_path, route_path, directory / "projection")
        projection_summary = dict(projection, bundleVersion=1, bundleRoot="..")
        _relative_fields(projection_summary, directory, "observation", "route", "nativeBefore", "nativeAfter",
                         "originalImage", "frameReceipt", "annotatedImage", "report")
        write_json_atomic(Path(projection["report"]), projection_summary)
        result.update(status="saved-route-view-candidate", image=projection["annotatedImage"],
                      projection=projection["report"])
        result["rerun"] = _optional_rerun(route_path, observation_path, directory, export_rerun,
                                          desktop=desktop, unit_sample=unit_sample)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        result.update(status="blocked", reason=str(error))
    if created:
        try:
            _save_manifest(directory, result)
        except (OSError, ValueError, TypeError) as error:
            result.update(status="blocked", reason="view-summary-write-failed", summaryWriteError=str(error))
    return result
