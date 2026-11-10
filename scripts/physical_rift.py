"""Select a real, locally running RIFT process; never discover VMware guests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import observe_physical

SUPPORTED_HOSTS = ("AMD-DESKTOP", "LEGION")
NATIVE_READS = {
    "position": "sample-current-position",
    "vitals": "sample-current-vitals",
    "orientation": "sample-current-orientation",
    "player-context": "sample-current-player-context",
    "selected-target": "sample-current-selected-target",
    "stats": "sample-current-stats",
}
NATIVE_RECEIPTS = {
    "position": "native-current-position-candidate-summary/1",
    "vitals": "native-current-vitals-candidate-summary/2",
    "orientation": "native-current-orientation-summary/1",
    "player-context": "native-current-player-context-candidate-summary/1",
    "selected-target": "native-current-selected-target-candidate-summary/1",
    "stats": "native-current-stats-summary/1",
}
NATIVE_EXE = (ROOT / "src" / "RiftReader2.Live" / "bin" / "Debug" /
              "net10.0-windows" / "win-x64" / "RiftReader2.Live.exe")


def select_physical(expected_host=None, physical_pid=None):
    """Return a fail-closed, PID/start/SHA-pinned physical process selection."""
    actual = socket.gethostname()
    target_id = "physical-" + actual.lower()
    try:
        if actual.upper() not in SUPPORTED_HOSTS:
            raise ValueError("unsupported-host")
        if expected_host is not None:
            if not isinstance(expected_host, str) or expected_host.upper() not in SUPPORTED_HOSTS:
                raise ValueError("invalid-expected-host")
            if actual.casefold() != expected_host.casefold():
                raise ValueError("host-mismatch")
        if physical_pid is not None and (type(physical_pid) is not int or not 1 <= physical_pid <= 4294967295):
            raise ValueError("invalid-physical-pid")
        # Selection needs a verified process, not an interactive game window.
        identity = observe_physical._identity(physical_pid, require_window=False)
        if identity.get("hostName", "").casefold() != actual.casefold():
            raise ValueError("identity-host-mismatch")
        if physical_pid is not None and identity.get("processId") != physical_pid:
            raise ValueError("physical-pid-mismatch")
        return {"status": "ready", "workflow": "physical", "targetId": target_id,
                "ownerHost": actual, "target": identity}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {"status": "blocked", "workflow": "physical", "targetId": target_id,
                "ownerHost": actual, "reason": str(exc)}


def _native_values(kind, report):
    """Project immediate useful values; preserve exact large unit keys as text."""
    if kind == "vitals":
        observation = report.get("observation")
        if not isinstance(observation, dict) or type(observation.get("unitKey")) is not int:
            raise ValueError("invalid-native-vitals-report")
        result = {"unitKey": str(observation["unitKey"])}
        for resource in ("health", "energy", "mana"):
            entry = observation.get(resource)
            if not isinstance(entry, dict) or not isinstance(entry.get("status"), str):
                raise ValueError("invalid-native-vitals-report")
            result[resource] = {name: entry.get(name) for name in
                                ("status", "current", "maximum", "unavailableReason")}
        return result
    if kind == "position":
        observations = report.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError("invalid-native-position-report")
        last = observations[-1]
        if not isinstance(last, dict) or any(type(last.get(axis)) not in (float, int)
                                               for axis in ("x", "y", "z")):
            raise ValueError("invalid-native-position-report")
        return {"sampleCount": len(observations), "unitKey": str(last.get("unitKey")),
                "x": last["x"], "y": last["y"], "z": last["z"],
                "sampledAtUtc": last.get("completedAtUtc"),
                "refreshGuardStatus": last.get("refreshGuardStatus")}
    return None


def read_native(selection, kind, output=None, *, samples=None, interval_ms=None):
    """Read a candidate from the exact selected LOCAL physical process, without input."""
    if selection.get("status") != "ready":
        return selection
    if kind not in NATIVE_READS:
        return dict(selection, status="blocked", reason="unknown-native-read")
    if kind != "position" and (samples is not None or interval_ms is not None):
        return dict(selection, status="blocked", reason="sampling-options-require-position")
    if ((samples is not None and (type(samples) is not int or not 1 <= samples <= 30))
            or (interval_ms is not None and (type(interval_ms) is not int or not 0 <= interval_ms <= 2000))):
        return dict(selection, status="blocked", reason="invalid-position-sampling")
    target = selection.get("target", {})
    pid, ticks = target.get("processId"), target.get("processStartUtcTicks")
    if (type(pid) is not int or pid <= 0 or not isinstance(ticks, str)
            or not ticks.isdecimal() or int(ticks) <= 0
            or target.get("hostName", "").casefold() != selection["ownerHost"].casefold()):
        return dict(selection, status="blocked", reason="invalid-local-process-identity")
    if not NATIVE_EXE.is_file():
        return dict(selection, status="blocked", reason="native-reader-not-built",
                    buildHint="dotnet build src/RiftReader2.Live")
    path = (Path(output) if output is not None else
            ROOT / "artifacts" / ("physical-native-" + kind + "-" + uuid.uuid4().hex + ".json"))
    if not path.is_absolute():
        path = ROOT / path
    if path.exists():
        return dict(selection, status="blocked", reason="native-output-exists")
    command = [str(NATIVE_EXE), NATIVE_READS[kind], "--pid", str(pid),
               "--start-ticks", ticks, "--output", str(path)]
    if samples is not None:
        command.extend(("--samples", str(samples)))
    if interval_ms is not None:
        command.extend(("--interval-ms", str(interval_ms)))
    # Long, explicitly requested intervals must not hit the wrapper's timeout.
    timeout = (30 + ((samples if samples is not None else 3) - 1)
               * (interval_ms if interval_ms is not None else 500) / 1000
               if kind == "position" else 30)
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                   text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(selection, status="blocked", reason="native-reader-launch-failed",
                    errorType=type(exc).__name__)
    if completed.returncode != 0:
        return dict(selection, status="blocked", reason="native-reader-failed",
                    exitCode=completed.returncode,
                    detail=completed.stderr.strip()[-240:])
    try:
        # Position emits per-sample JSON lines before its final summary receipt.
        lines = completed.stdout.splitlines()
        summary = json.loads(lines[-1]) if lines else None
    except (ValueError, TypeError):
        return dict(selection, status="blocked", reason="invalid-native-reader-receipt")
    if (not isinstance(summary, dict) or not path.is_file()
            or summary.get("recordType") != NATIVE_RECEIPTS[kind]
            or not isinstance(summary.get("output"), str)
            or Path(summary["output"]).resolve() != path.resolve()
            or summary.get("status") != (None if kind == "stats" else "complete")):
        return dict(selection, status="blocked", reason="invalid-native-reader-receipt")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        observation = report.get("observation")
        identity = report.get("identity") or (observation.get("identity")
                                                if isinstance(observation, dict) else None)
        if (report.get("status") != "complete" or not isinstance(identity, dict)
                or identity.get("processId") != pid
                or str(identity.get("processStartUtcTicks")) != ticks
                or str(identity.get("executableSha256", "")).casefold()
                    != str(target.get("executableSha256", "")).casefold()):
            raise ValueError("report-identity-or-status-mismatch")
        values = _native_values(kind, report)
    except (OSError, ValueError, TypeError, AttributeError):
        return dict(selection, status="blocked", reason="invalid-native-reader-report")
    return dict(selection, status="complete", nativeRead=kind,
                nativeOutput=str(path), nativeSummary=summary, nativeValues=values,
                qualification="candidate-only; changed-state/freshness/restart-unverified")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", choices=SUPPORTED_HOSTS,
                        help="optional guard: refuse a different physical PC")
    parser.add_argument("--physical-pid", type=int,
                        help="pin one local rift_x64.exe PID; required if multiple exist")
    parser.add_argument("--read-native", choices=tuple(NATIVE_READS),
                        help="read one candidate from the pinned physical process; no input")
    parser.add_argument("--output", type=Path,
                        help="new JSON file for --read-native (default: unique artifacts path)")
    parser.add_argument("--samples", type=int,
                        help="position only: 1-30 native samples (default: 3)")
    parser.add_argument("--interval-ms", type=int,
                        help="position only: 0-2000ms between reads (default: 500)")
    args = parser.parse_args(argv)
    if args.read_native is not None and args.expected_host is None:
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "native-read-requires-expected-host"}
    elif (args.samples is not None or args.interval_ms is not None) and args.read_native != "position":
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "sampling-options-require-position"}
    else:
        result = select_physical(args.expected_host, args.physical_pid)
    if args.output is not None and args.read_native is None:
        result = dict(result, status="blocked", reason="output-requires-native-read")
    elif args.read_native:
        result = read_native(result, args.read_native, args.output,
                             samples=args.samples, interval_ms=args.interval_ms)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("ready", "complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
