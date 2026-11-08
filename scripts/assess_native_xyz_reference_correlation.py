"""Compare retained current-native XYZ against a pinned RR2R1 inspection.

Offline only. Snapshot file hashes are checked, but this utility does not
re-run the typed scanner or independently bind decoded fields to snapshot
bytes. API calls can refresh the native coordinate cache. No result establishes
passive freshness, independent native semantics, or changed-state causality.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.project_xyz_track import project, GAME_SHA

SHA = re.compile(r"[0-9A-F]{64}")
NONCE = re.compile(r"[0-9a-f]{32}")
UNIT = re.compile(r"u[0-9A-F]{16}")
MAX_REPORT = 8_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(value):
    require(isinstance(value, str) and SHA.fullmatch(value) is not None, "invalid SHA256 pin")
    return value


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "duplicate JSON key")
        out[key] = value
    return out


def read_report(path, expected):
    pin(expected)
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_REPORT + 1)
    require(len(data) <= MAX_REPORT, "report too large")
    actual = hashlib.sha256(data).hexdigest().upper()
    require(actual == expected, "report SHA256 mismatch")
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs)


def utc(value):
    """Return exact 100 ns ticks for .NET ISO UTC timestamps, without truncation."""
    require(isinstance(value, str), "timestamp missing")
    match = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:[.]([0-9]{1,7}))?(?:Z|[+]00:00)",
        value)
    require(match is not None, "timestamp must be UTC with at most seven fractional digits")
    try:
        whole = datetime.fromisoformat(match.group(1))
    except ValueError:
        raise ValueError("invalid timestamp") from None
    delta = whole - datetime(1, 1, 1)
    return ((delta.days * 86400 + delta.seconds) * 10_000_000
            + int((match.group(2) or "").ljust(7, "0")))


def finite(value):
    require(type(value) in (int, float), "invalid numeric field")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError("invalid numeric field") from None
    require(math.isfinite(result), "nonfinite numeric field")
    return result


def assess(native, typed, *, native_sha, typed_sha, before_snapshot_sha,
           after_snapshot_sha, max_lag_seconds, tolerance):
    """Assess caller-verified input bytes; all timing uses guest UTC, not sync proof."""
    for value in (native_sha, typed_sha, before_snapshot_sha, after_snapshot_sha):
        pin(value)
    max_lag_seconds = finite(max_lag_seconds)
    tolerance = finite(tolerance)
    require(0 < max_lag_seconds <= 300 and 0 <= tolerance <= 10, "invalid comparison bounds")
    projection = project(native, max_gap_seconds=300, max_speed_3d=1e100)
    require(projection["unitIdentity"] == "same-sampled-unit-key-candidate",
            "native sampled unit identity unavailable")
    require(isinstance(typed, dict) and type(typed.get("schemaVersion")) is int
            and typed["schemaVersion"] == 1
            and typed.get("evidenceKind") == "typed-wire-snapshot-inspection/1"
            and typed.get("operation") == "inspect-typed-wire"
            and typed.get("status") == "advanced-in-covered-scope",
            "typed inspection unavailable or not advancing")
    ti, ni = typed.get("identity"), native.get("identity")
    require(isinstance(ti, dict) and isinstance(ni, dict), "identity missing")
    for key in ("processId", "processStartUtcTicks", "executableSha256"):
        require(type(ti.get(key)) is type(ni.get(key)) and ti.get(key) == ni.get(key),
                "process or build identity mismatch")
    require(ti["executableSha256"] == GAME_SHA, "build mismatch")
    sources, selected = typed.get("source"), typed.get("selected")
    require(isinstance(sources, dict) and isinstance(selected, dict), "typed evidence missing")
    frames = []
    for stage, supplied_sha in (("before", before_snapshot_sha), ("after", after_snapshot_sha)):
        cap, frame = sources.get(stage), selected.get(stage)
        require(isinstance(cap, dict) and isinstance(frame, dict) and cap.get("status") == "complete",
                "snapshot or selected frame unavailable")
        require(cap.get("snapshotSha256") == supplied_sha, "snapshot SHA256 mismatch")
        start, end = utc(cap.get("startedAtUtc")), utc(cap.get("completedAtUtc"))
        require(start <= end, "snapshot timing reversed")
        require(cap.get("candidateLimitExceeded") is False
                and type(cap.get("malformedCompleteCount")) is int
                and cap["malformedCompleteCount"] == 0, "typed selection unsafe")
        wire_sha = pin(frame.get("wireSha256"))
        candidates = cap.get("candidates")
        require(isinstance(candidates, list) and any(
            isinstance(c, dict) and c.get("kind") == "valid"
            and all(c.get(k) == frame.get(k) for k in
                    ("address", "wireSha256", "sequence", "frameTime", "playerUnitId"))
            for c in candidates), "selected frame not listed as valid")
        require(frame.get("protocol") == "RR2R1" and frame.get("addon") == "RiftReader2"
                and frame.get("source") == "rift-api", "wrong reference protocol or producer")
        nonce, unit, epoch, sequence = (frame.get("sessionId"), frame.get("playerUnitId"),
                                        frame.get("epoch"), frame.get("sequence"))
        require(isinstance(nonce, str) and NONCE.fullmatch(nonce) is not None
                and isinstance(unit, str) and UNIT.fullmatch(unit) is not None
                and unit == projection["sampledUnitIdCandidate"]
                and type(epoch) is int and epoch > 0
                and type(sequence) is int and sequence > 0, "reference binding unavailable or mismatched")
        clock = finite(frame.get("frameTime"))
        fields, xyz = frame.get("fields"), frame.get("xyz")
        require(isinstance(fields, dict) and isinstance(xyz, dict), "typed XYZ unavailable")
        coords = {}
        for axis in "xyz":
            field = fields.get("coord" + axis.upper())
            require(isinstance(field, dict) and field.get("status") == "ok", "typed XYZ unavailable")
            value = finite(field.get("value"))
            require(value == finite(xyz.get(axis)), "typed XYZ representations disagree")
            coords[axis] = value
        frames.append(dict(start=start, end=end, nonce=nonce, unit=unit, epoch=epoch,
                           sequence=sequence, clock=clock, xyz=coords, wireSha256=wire_sha))
    a, b = frames
    require(before_snapshot_sha != after_snapshot_sha and a["wireSha256"] != b["wireSha256"]
            and a["end"] < b["start"] and a["nonce"] == b["nonce"]
            and a["unit"] == b["unit"] and a["epoch"] == b["epoch"]
            and a["sequence"] < b["sequence"] and a["clock"] < b["clock"],
            "typed source did not advance in same binding")
    native_rows = native["observations"]
    pairs = []
    for f in frames:
        row = min(native_rows, key=lambda n: abs(utc(n["completedAtUtc"]) - f["end"]))
        lag = (utc(row["completedAtUtc"]) - f["end"]) / 10_000_000
        require(abs(lag) <= max_lag_seconds, "native/reference capture lag exceeded")
        delta = {axis: finite(row[axis]) - f["xyz"][axis] for axis in "xyz"}
        pairs.append({"nativeIndex": row["index"], "lagSeconds": lag,
                      "nativeMinusReference": delta,
                      "allAxesWithinTolerance": all(abs(v) <= tolerance for v in delta.values())})
    require(pairs[0]["nativeIndex"] < pairs[1]["nativeIndex"], "native/reference pair ordering invalid")
    return {"schemaVersion": 1, "evidenceKind": "native-xyz-rr2r1-correlation/1",
            "status": "api-influenced-coordinate-correspondence" if all(p["allAxesWithinTolerance"] for p in pairs)
                      else "api-influenced-coordinate-disagreement",
            "qualification": "candidate-only; no independent passive freshness or native semantic proof",
            "playerUnitId": a["unit"], "sessionId": a["nonce"], "epoch": a["epoch"],
            "processIdentity": ni, "nativeReportSha256": native_sha, "typedInspectionSha256": typed_sha,
            "beforeSnapshotSha256": before_snapshot_sha, "afterSnapshotSha256": after_snapshot_sha,
            "sourceSequence": [a["sequence"], b["sequence"]], "pairs": pairs,
            "toleranceSourceUnits": tolerance, "maxLagSeconds": max_lag_seconds,
            "limitations": ["Snapshot digests are caller-asserted to assess(); the CLI hashes supplied files; decoded frames were not rescanned or byte-bound.",
                            "Inspection report is caller-pinned derived evidence; source frame hashes are declared, not reverified.",
                            "Inspect.Unit.Detail may refresh native cache; no independent passive freshness, motion causation or clock synchronization is established."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "typed", "before-snapshot", "after-snapshot"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--native-sha256", required=True)
    parser.add_argument("--typed-sha256", required=True)
    parser.add_argument("--max-lag-seconds", type=float, required=True)
    parser.add_argument("--tolerance", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        native = read_report(args.native, args.native_sha256)
        typed = read_report(args.typed, args.typed_sha256)
        result = assess(native, typed, native_sha=args.native_sha256, typed_sha=args.typed_sha256,
                        before_snapshot_sha=digest(args.before_snapshot),
                        after_snapshot_sha=digest(args.after_snapshot),
                        max_lag_seconds=args.max_lag_seconds, tolerance=args.tolerance)
        print(json.dumps(result, allow_nan=False))
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
