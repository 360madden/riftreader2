"""Offline audit of a completed position-panel session, without game/VM access.

Checks recorded evidence only; a clean audit is not restart or field qualification.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import sys

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_EVENTS = 100_000
MIN_NORMAL_FLOAT32 = 2 ** -126


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(data):
    def reject(value):
        raise ValueError(f"Non-JSON number: {value}")
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject)


def read_file(path):
    require(not path.is_symlink(), f"Symlink is not an evidence file: {path.name}")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    require(len(data) <= MAX_FILE_BYTES, f"File exceeds limit: {path.name}")
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def utc(value):
    require(isinstance(value, str), "Missing UTC timestamp")
    stamp = datetime.fromisoformat(value)
    require(stamp.utcoffset() == timedelta(0), "Timestamp must use UTC")
    return stamp


def subnormal(observation):
    values = [observation[axis] for axis in ("x", "y", "z")]
    require(all(type(v) in (int, float) and math.isfinite(v) for v in values),
            "Coordinates must be finite numbers")
    return any(0 < abs(v) < MIN_NORMAL_FLOAT32 for v in values)


def review_session(directory: Path) -> dict:
    directory = Path(directory).resolve(strict=True)
    session_bytes = read_file(directory / "panel-session.json")
    journal_bytes = read_file(directory / "panel-events.jsonl")
    session = parse(session_bytes)
    require(session["schemaVersion"] == 1 and
            session["contractVersion"] == "native-position-panel-session/1",
            "Unsupported session contract")
    require(session["qualification"] == "candidate-only", "Unexpected qualification")
    require(session["noGameInput"] is True, "Unexpected game-input declaration")
    require(re.fullmatch(r"[0-9A-F]{64}", session["sourceSha256"]), "Invalid profile SHA")
    require(re.fullmatch(r"[0-9A-F]{64}", session["profile"]["executableSha256"]), "Invalid build SHA")
    lines = journal_bytes.splitlines()
    require(0 < len(lines) <= MAX_EVENTS, "Empty or oversized journal")
    events = [parse(line) for line in lines]
    require(events[0]["kind"] == "opened", "Journal must begin with opened")
    require(events[-1]["kind"] == "closed", "Session is not closed; review a finished copy")
    reports = {}
    latest_report = None
    previous_time = utc(session["startedAtUtc"])
    previous_read_index = 0
    epoch_identities = {}
    consumed_reports = set()
    counts = Counter()
    epochs = {}
    findings = []
    last_state = None
    for line_number, event in enumerate(events, 1):
        kind, value = event["kind"], event["value"]
        require(kind in {"opened", "closed", "start", "stop", "read", "report", "state"},
                f"Unknown event kind on line {line_number}")
        timestamp = utc(event["atUtc"])
        require(timestamp >= previous_time, "Journal timestamps are reversed")
        previous_time = timestamp
        require(latest_report is None or kind == "state", "Report must have an immediate state outcome")
        if kind == "opened":
            require(line_number == 1, "Repeated opened event")
        if kind == "closed":
            require(line_number == len(events), "Events after closed")
        counts[kind] += 1
        if kind == "report":
            name = value["path"]
            require(isinstance(name, str) and re.fullmatch(r"read-[0-9]{5,}\.json", name),
                    "Report path must be a local read-NNNNN.json filename")
            require(name not in reports, "Duplicate report reference")
            read_index = int(name[5:-5])
            require(read_index > previous_read_index, "Report numbers must increase")
            previous_read_index = read_index
            data = read_file(directory / name)
            require(sha(data) == value["sha256"], f"Report hash mismatch: {name}")
            report = parse(data)
            require(report["schemaVersion"] == 1 and
                    report["contractVersion"] == "native-position-samples/1", "Unsupported report")
            require(report["qualification"] == "candidate-only-not-motion-or-update-qualified",
                    "Unexpected report qualification")
            require(report["profileSha256"] == session["sourceSha256"] and
                    report["profile"] == session["profile"], "Report profile mismatch")
            samples = report["samples"]
            require(samples["identity"] == value["identity"], "Report identity mismatch")
            identity = samples["identity"]
            require(identity["executableSha256"] == session["profile"]["executableSha256"],
                    "Report build mismatch")
            require(type(identity["processId"]) is int and identity["processId"] > 0 and
                    type(identity["processStartUtcTicks"]) is int and identity["processStartUtcTicks"] > 0,
                    "Invalid process identity")
            epoch_key = (identity["processId"], identity["processStartUtcTicks"])
            require(epoch_identities.setdefault(epoch_key, identity) == identity,
                    "Conflicting identity within process epoch")
            epoch = epochs.setdefault(epoch_key, {"processId": epoch_key[0],
                "processStartUtcTicks": epoch_key[1], "reports": 0, "liveStates": 0})
            epoch["reports"] += 1
            require(samples["requestedSamples"] == 1, "Expected single-sample panel report")
            for observation in samples["observations"]:
                if observation["status"] == "complete" and subnormal(observation):
                    counts["subnormalRawObservations"] += 1
            reports[name] = value["sha256"]
            latest_report = (name, samples, epoch)
        elif kind == "state":
            paired_report = latest_report
            latest_report = None
            last_state = value
            status = value["status"]
            require(status in {"stopped", "waiting", "reading", "live", "stale", "expired", "unavailable"},
                    "Unknown panel state")
            counts["state:" + status] += 1
            if value.get("reason") == "position-values-not-ready":
                counts["startupWithheldStates"] += 1
            if status != "live":
                if value["identity"] is not None or value["observation"] is not None:
                    findings.append({"line": line_number, "reason": "non-live-state-retained-values"})
                if paired_report:
                    name, samples, _epoch = paired_report
                    if any(o["status"] == "complete" and subnormal(o) for o in samples["observations"]):
                        if status != "unavailable" or value.get("reason") != "position-values-not-ready":
                            findings.append({"line": line_number, "report": name,
                                             "reason": "subnormal-withholding-not-established"})
                continue
            require(paired_report is not None, "Live state has no preceding report")
            name, samples, epoch = paired_report
            require(name not in consumed_reports, "Report published live more than once")
            require(samples["status"] == "complete" and samples["completedSamples"] == 1 and
                    len(samples["observations"]) == 1, "Live state references incomplete report")
            require(value["identity"] == samples["identity"] and
                    value["observation"] == samples["observations"][0],
                    "Live state does not match preceding original report")
            require(value["observation"]["status"] == "complete", "Live observation is incomplete")
            consumed_reports.add(name)
            epoch["liveStates"] += 1
            if subnormal(value["observation"]):
                findings.append({"line": line_number, "report": name, "reason": "subnormal-published-live"})
    actual_names = {p.name for p in directory.glob("read-*.json")}
    require(actual_names == set(reports), "Unreferenced or missing report files")
    if not last_state or last_state["status"] != "stopped":
        findings.append({"reason": "session-did-not-end-stopped"})
    if not consumed_reports:
        findings.append({"reason": "no-live-observations"})
    return {"schemaVersion": 1, "contractVersion": "position-panel-evidence-review/1",
        "status": "recorded-checks-passed" if not findings else "recorded-checks-failed",
        "qualification": "candidate-only", "sessionSha256": sha(session_bytes),
        "journalSha256": sha(journal_bytes), "reportSha256": reports,
        "counts": dict(sorted(counts.items())), "epochs": list(epochs.values()),
        "findings": findings, "limitations": [
            "Offline review of recorded events, not proof of rendered UI or monotonic freshness timing.",
            "Multiple process identities alone do not prove full game exit/relaunch or process absence.",
            "No independent Lua, movement, raw pointer, guest deployment or cleanup verification.",
            "Recorded hashes establish local consistency, not authenticity; retain externally pinned originals.",
            "No field promotion, memory scanning, live process access or patch recovery."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), "Output already exists")
        report = review_session(args.session_dir)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(report["status"])
        return 0 if not report["findings"] else 2
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
        print(f"Position panel review rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
