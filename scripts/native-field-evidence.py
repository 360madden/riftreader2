#!/usr/bin/env python3
"""Review retained RIFT native-position candidate reports without promoting fields.

Consumes exact field-lab reports, checks selected raw-byte integrity and identity,
and compares native XYZ against fresh typed Lua references. No live game access.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import tempfile

MAX_REPORT_BYTES = 96 * 1024 * 1024
HEX_ADDRESS = re.compile(r"^0x(?:0|[1-9A-F][0-9A-F]*)$")
SHA256 = re.compile(r"^[0-9A-F]{64}$")
COORDS = ("coordX", "coordY", "coordZ")


class EvidenceError(ValueError):
    """The report or requested comparison cannot be trusted."""


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise EvidenceError(f"duplicate JSON property: {key}")
        obj[key] = value
    return obj


def _bad_constant(value):
    raise EvidenceError(f"non-finite JSON constant: {value}")


def _object(value, label):
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise EvidenceError(f"{label} must be an integer >= {minimum}")
    return value


def _hex(value, label):
    if not isinstance(value, str) or not HEX_ADDRESS.fullmatch(value):
        raise EvidenceError(f"{label} must be canonical uppercase hex")
    return int(value, 16)


def _hash(value, label):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise EvidenceError(f"{label} must be uppercase SHA-256")
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise EvidenceError(f"{label} must be a finite number")
    if not math.isfinite(value):
        raise EvidenceError(f"{label} must be finite")
    return float(value)


def _bytes(value, label):
    if not isinstance(value, str):
        raise EvidenceError(f"{label} must be base64")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise EvidenceError(f"{label} is not strict base64") from error


def _utc_ticks(value, label):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError(f"{label} must be an exact UTC timestamp")
    match = re.fullmatch(r"(.+?)(?:\.(\d{1,7}))?Z", value)
    if match is None:
        raise EvidenceError(f"{label} is invalid")
    try:
        whole = datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise EvidenceError(f"{label} is invalid") from error
    if whole.microsecond:
        raise EvidenceError(f"{label} must have one fractional component")
    elapsed = whole - datetime(1, 1, 1, tzinfo=timezone.utc)
    return ((elapsed.days * 86400 + elapsed.seconds) * 10_000_000
            + int((match.group(2) or "").ljust(7, "0") or 0))


def load_report(path):
    if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        raise EvidenceError(f"missing or oversized native report: {path}")
    with path.open("rb") as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES or stream.read(1):
            raise EvidenceError(f"native report exceeds {MAX_REPORT_BYTES} bytes")
    try:
        report = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_bad_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"invalid UTF-8 JSON: {path}") from error
    return _object(report, "report"), hashlib.sha256(raw).hexdigest().upper()


def _reference(value, identity, label):
    value = _object(value, label)
    target = _object(value.get("target"), f"{label}.target")
    if (_integer(target.get("processId"), f"{label}.pid", 1)
            != identity["processId"]
            or _utc_ticks(target.get("processStartUtc"), f"{label}.start")
            != identity["processStartUtcTicks"]
            or _hash(target.get("executableSha256"), f"{label}.build")
            != identity["executableSha256"]):
        raise EvidenceError(f"{label}: target identity mismatch")
    readback = _object(value.get("readback"), f"{label}.readback")
    typed = _object(readback.get("typedApi"), f"{label}.typedApi")
    if readback.get("status") != "fresh" or typed.get("status") != "fresh":
        raise EvidenceError(f"{label}: reference is not fresh")
    if typed.get("sequenceAdvanced") is not True or typed.get("frameTimeAdvanced") is not True:
        raise EvidenceError(f"{label}: source did not advance")
    player = _object(_object(typed.get("snapshot"), "snapshot").get("player"), "player")
    unit_id = player.get("unitId")
    if not isinstance(unit_id, str) or not unit_id:
        raise EvidenceError(f"{label}: missing player identity")
    fields = _object(player.get("fields"), "player.fields")
    values = []
    for field_name in COORDS:
        field = _object(fields.get(field_name), f"player.{field_name}")
        if field.get("status") != "ok":
            raise EvidenceError(f"{label}: {field_name} is unavailable")
        values.append(_number(field.get("value"), field_name))
    return {
        "observer": value.get("instanceId"),
        "generation": _integer(typed.get("generation"), f"{label}.generation"),
        "sequence": _integer(typed.get("selectedSequence"), f"{label}.sequence"),
        "unitId": unit_id,
        "xyz": values,
    }


def inspect_report(path, root_rva, offsets, tolerance):
    report, digest = load_report(path)
    if (report.get("schemaVersion") != 1
            or type(report.get("schemaVersion")) is not int
            or report.get("evidenceKind") != "native-field-discovery/1"
            or report.get("status") != "complete"):
        raise EvidenceError(f"{path}: not a completed field-discovery/1 report")
    run_id = report.get("runId")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise EvidenceError(f"{path}: invalid run ID")
    plan = _object(report.get("plan"), "plan")
    if _hex(plan.get("rootRva"), "plan.rootRva") != root_rva:
        raise EvidenceError(f"{path}: root RVA differs from requested candidate")
    identity = _object(report.get("identity"), "identity")
    _integer(identity.get("processId"), "identity.pid", 1)
    _integer(identity.get("processStartUtcTicks"), "identity.startTicks", 1)
    _integer(identity.get("moduleBaseAddress"), "identity.moduleBase", 1)
    module_size = _integer(identity.get("moduleSize"), "identity.moduleSize", 8)
    if root_rva > module_size - 8:
        raise EvidenceError("root RVA falls outside main executable")
    identity["executableSha256"] = _hash(identity.get("executableSha256"), "identity.build")
    if _hash(plan.get("buildSha256"), "plan.build") != identity["executableSha256"]:
        raise EvidenceError(f"{path}: declared build mismatch")
    before = _reference(report.get("referenceBefore"), identity, "before")
    after = _reference(report.get("referenceAfter"), identity, "after")
    if (not isinstance(before["observer"], str) or not before["observer"]
            or before["observer"] != after["observer"]
            or before["generation"] != after["generation"]
            or before["unitId"] != after["unitId"]
            or after["sequence"] <= before["sequence"]):
        raise EvidenceError(f"{path}: observer, unit, generation, or sequence changed")
    if _utc_ticks(report.get("completedAtUtc"), "completedAtUtc") < _utc_ticks(
        report.get("startedAtUtc"), "startedAtUtc"
    ):
        raise EvidenceError(f"{path}: capture time reversed")
    root_read = _object(report.get("rootRead"), "rootRead")
    if root_read.get("status") != "success":
        raise EvidenceError(f"{path}: root pointer unavailable")
    root_bytes = _bytes(root_read.get("bytes"), "rootRead.bytes")
    if len(root_bytes) != 8:
        raise EvidenceError(f"{path}: root pointer length is not eight bytes")
    owner = int.from_bytes(root_bytes, "little")
    if _hex(report.get("ownerAddress"), "ownerAddress") != owner:
        raise EvidenceError(f"{path}: root pointer and owner disagree")
    windows = report.get("windows")
    if not isinstance(windows, list):
        raise EvidenceError(f"{path}: windows must be an array")
    candidate = [w for w in windows if isinstance(w, dict) and w.get("offsets") == ["0x0"]]
    if len(candidate) != 1:
        raise EvidenceError(f"{path}: expected exactly one root-owner window")
    window = candidate[0]
    if _hex(window.get("address"), "window.address") != owner:
        raise EvidenceError(f"{path}: captured window is not the root owner")
    read = _object(window.get("read"), "window.read")
    if read.get("status") != "success":
        raise EvidenceError(f"{path}: owner bytes unavailable")
    raw = _bytes(read.get("bytes"), "window.read.bytes")
    if _hash(window.get("sha256"), "window.sha256") != hashlib.sha256(raw).hexdigest().upper():
        raise EvidenceError(f"{path}: captured owner bytes fail SHA-256")
    if max(offsets) + 4 > len(raw):
        raise EvidenceError(f"{path}: owner window does not cover requested XYZ offsets")
    stable = window.get("stable")
    if stable is not None and type(stable) is not bool:
        raise EvidenceError(f"{path}: invalid root stability flag")
    if stable is True:
        hops = window.get("hops")
        if not isinstance(hops, list) or len(hops) != 1:
            raise EvidenceError(f"{path}: missing root stability readback")
        hop = _object(hops[0], "rootHop")
        if (_hex(hop.get("address"), "rootHop.address")
                != identity["moduleBaseAddress"] + root_rva
                or _hex(hop.get("offset"), "rootHop.offset") != 0
                or _object(hop.get("read"), "rootHop.read").get("status") != "success"
                or _bytes(hop["read"].get("bytes"), "rootHop.bytes") != root_bytes):
            raise EvidenceError(f"{path}: root stability hop differs")
    native = [struct.unpack_from("<f", raw, offset)[0] for offset in offsets]
    if not all(map(math.isfinite, native)):
        raise EvidenceError(f"{path}: native position is nonfinite")
    deltas = [n - v for n, v in zip(native, before["xyz"])]
    reference_changed = any(
        abs(v - w) > tolerance for v, w in zip(before["xyz"], after["xyz"])
    )
    close = all(abs(delta) <= tolerance for delta in deltas)
    return {
        "runId": run_id,
        "sourcePath": str(path),
        "sourceSha256": digest,
        "captureStartUtc": report["startedAtUtc"],
        "processId": identity["processId"],
        "processStartUtcTicks": identity["processStartUtcTicks"],
        "buildSha256": identity["executableSha256"],
        "moduleBaseAddress": f"0x{identity['moduleBaseAddress']:X}",
        "ownerSessionAddress": f"0x{owner:X}",
        "observer": before["observer"],
        "unitId": before["unitId"],
        "sourceSequences": [before["sequence"], after["sequence"]],
        "nativeXyz": native,
        "luaBeforeXyz": before["xyz"],
        "luaAfterXyz": after["xyz"],
        "nativeMinusLua": deltas,
        "referenceChangedDuringCapture": reference_changed,
        "withinTolerance": close and not reference_changed,
        "rootWindowStability": (
            "verified" if stable is True else "failed" if stable is False else "unrecorded"
        ),
    }


def evaluate(paths, root_rva, offsets, tolerance=0.02):
    if (not paths or len(paths) > 32
            or type(root_rva) is not int or root_rva < 0
            or len(offsets) != 3 or any(type(x) is not int or x < 0 or x > 4092 for x in offsets)
            or len(set(offsets)) != 3
            or isinstance(tolerance, bool) or not math.isfinite(tolerance)
            or tolerance <= 0 or tolerance > 1):
        raise EvidenceError("invalid report count, RVA, XYZ offsets, or tolerance")
    samples = [inspect_report(Path(path), root_rva, offsets, tolerance) for path in paths]
    digests = [item["sourceSha256"] for item in samples]
    ids = [item["runId"] for item in samples]
    if len(set(digests)) != len(digests) or len(set(ids)) != len(ids):
        raise EvidenceError("duplicate capture or run identity; not independent evidence")
    builds = {sample["buildSha256"] for sample in samples}
    if len(builds) != 1:
        raise EvidenceError("builds differ; analyze each executable separately")
    samples.sort(key=lambda x: (x["captureStartUtc"], x["runId"]))
    pairs = []
    for i, first in enumerate(samples):
        for second in samples[i + 1:]:
            same_process = (
                first["processId"] == second["processId"]
                and first["processStartUtcTicks"] == second["processStartUtcTicks"]
                and first["unitId"] == second["unitId"]
            )
            if not same_process or first["referenceChangedDuringCapture"] or second["referenceChangedDuringCapture"]:
                continue
            lua_change = [b - a for a, b in zip(first["luaBeforeXyz"], second["luaBeforeXyz"])]
            native_change = [b - a for a, b in zip(first["nativeXyz"], second["nativeXyz"])]
            if not any(abs(x) > 2 * tolerance for x in lua_change):
                continue
            pairs.append({
                "fromRunId": first["runId"],
                "toRunId": second["runId"],
                "luaDisplacement": lua_change,
                "nativeDisplacement": native_change,
                "displacementAgrees": all(
                    abs(x - y) <= 2 * tolerance for x, y in zip(lua_change, native_change)
                ),
                "bothRootReadsStable": (
                    first["rootWindowStability"] == "verified"
                    and second["rootWindowStability"] == "verified"
                ),
            })
    disagreements = any(
        not s["withinTolerance"] or s["rootWindowStability"] == "failed"
        for s in samples
    ) or any(not p["displacementAgrees"] for p in pairs)
    agreement_pairs = [p for p in pairs if p["displacementAgrees"]]
    if disagreements:
        assessment = "contradictory-or-inconclusive"
    elif any(p["bothRootReadsStable"] for p in agreement_pairs):
        assessment = "movement-consistent-same-process"
    elif agreement_pairs:
        assessment = "movement-consistent-stability-unverified"
    else:
        assessment = "stationary-only"
    sessions = {
        (item["processId"], item["processStartUtcTicks"]) for item in samples
    }
    return {
        "schemaVersion": 1,
        "evidenceKind": "native-position-candidate-review/1",
        "requested": {
            "rootRva": f"0x{root_rva:X}",
            "xyzOffsets": [f"0x{x:X}" for x in offsets],
            "absoluteTolerance": tolerance,
        },
        "buildSha256": next(iter(builds)),
        "captureCount": len(samples),
        "processEpochCount": len(sessions),
        "assessment": assessment,
        "qualification": "candidate-only",
        "restartSurvival": "not-assessed",
        "updateSurvival": "not-assessed",
        "limitations": [
            "A numeric match does not establish a field's meaning.",
            "A saved heap address is not a durable locator.",
            "Restart and update survival require separately reviewed evidence.",
            "Host/guest sampling is not atomic; stale or moving references are inconclusive.",
        ],
        "captures": samples,
        "withinEpochMovementComparisons": pairs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--root-rva", required=True)
    parser.add_argument("--xyz-offsets", nargs=3, required=True)
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        root = _hex(args.root_rva, "root-rva")
        offsets = [_hex(value, "xyz-offset") for value in args.xyz_offsets]
        evaluation = evaluate(args.report, root, offsets, args.tolerance)
        payload = (json.dumps(evaluation, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if args.output:
            staging_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=args.output.parent,
                    prefix=f".{args.output.name}.", suffix=".tmp", delete=False,
                ) as staging:
                    staging_path = Path(staging.name)
                    staging.write(payload)
                    staging.flush()
                    os.fsync(staging.fileno())
                # Same-directory hard link creates the final name atomically and
                # refuses to replace an existing report, including under races.
                os.link(staging_path, args.output)
            except FileExistsError as error:
                raise EvidenceError(f"output already exists: {args.output}") from error
            finally:
                if staging_path is not None:
                    staging_path.unlink(missing_ok=True)
        else:
            sys.stdout.buffer.write(payload)
        return 0
    except (EvidenceError, OSError, OverflowError, KeyError, TypeError, ValueError) as error:
        print(f"Native evidence review failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
