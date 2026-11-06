"""Offline, fail-closed comparison of two native pointer windows with typed Lua.

No process, VM, network, game input, or private host service is accessed.
Reports remain source evidence; the output is candidate-only because typed
Lua memory snapshots and pointer reads are not synchronized wall-clock samples.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT_RVA = 0x32E0200
XYZ_OFFSETS = (0x320, 0x324, 0x328)
WINDOW_BYTES = 816
SOURCE_KIND = "typed-wire-snapshot-inspection/1"
POINTER_KIND = "native-pointer-follow/1"
REQUEST_KIND = "native-pointer-follow-request/1"
MAX_FILE_BYTES = 8 * 1024 * 1024
SHA_ALPHABET = set("0123456789ABCDEF")


class EvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str):
    raise EvidenceError("nonfinite JSON literal: " + value)


def read_source(path: Path) -> tuple[dict, str]:
    _require(path.is_file() and not path.is_symlink(), "source file missing or symlink")
    _require(0 < path.stat().st_size <= MAX_FILE_BYTES, "source file size outside bound")
    data = path.read_bytes()
    try:
        report = json.loads(data, object_pairs_hook=_duplicates,
                            parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError("source JSON invalid") from error
    _require(isinstance(report, dict), "source must be JSON object")
    return report, hashlib.sha256(data).hexdigest().upper()


def _pin_sha(value: str) -> None:
    _require(isinstance(value, str) and len(value) == 64
             and set(value) <= SHA_ALPHABET, "invalid uppercase SHA-256")


def _time(value: object) -> datetime:
    _require(isinstance(value, str), "invalid UTC sample time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError("unparseable UTC sample time") from error
    _require(parsed.tzinfo is not None
             and parsed.utcoffset().total_seconds() == 0, "sample timestamp is not UTC")
    return parsed


def _bytes64(value: object, length: int) -> bytes:
    _require(isinstance(value, str), "expected Base64 memory bytes")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise EvidenceError("malformed Base64 memory bytes") from error
    _require(len(data) == length, "native read byte length mismatch")
    return data


def _target(request: dict) -> dict:
    _require(request.get("schemaVersion") == 1
             and request.get("evidenceKind") == REQUEST_KIND
             and request.get("rootRva") == "0x32E0200"
             and request.get("offsets") == ["0x0"]
             and request.get("terminalByteLength") == WINDOW_BYTES
             and type(request.get("maxDurationMilliseconds")) is int
             and 1 <= request["maxDurationMilliseconds"] <= 30000,
             "pointer request is not exact bounded root-and-window contract")
    t = request.get("target")
    _require(isinstance(t, dict) and set(t) == {
        "processId", "processStartUtcTicks", "executableSha256"
    } and type(t["processId"]) is int and t["processId"] > 0
        and type(t["processStartUtcTicks"]) is int
        and t["processStartUtcTicks"] > 0, "invalid exact game-process target")
    _pin_sha(t["executableSha256"])
    return t


def _identity(value: object, target: dict) -> dict:
    _require(isinstance(value, dict), "native identity is missing")
    for key in ("processId", "processStartUtcTicks", "executableSha256"):
        _require(value.get(key) == target[key], "native process epoch/build differs")
    module = value.get("moduleBaseAddress")
    size = value.get("moduleSize")
    _require(type(module) is int and type(size) is int and module >= 0x10000
             and size > ROOT_RVA + 8, "native main module cannot contain root RVA")
    return value


def _source_xyz(source: dict, target: dict, tolerance: float = 0.02) -> tuple[dict, str, datetime]:
    _require(source.get("schemaVersion") == 1
             and source.get("evidenceKind") == SOURCE_KIND
             and source.get("status") == "advanced-in-covered-scope",
             "source is not a qualified advancing typed frame pair")
    sid = source.get("identity")
    _require(isinstance(sid, dict), "typed source lacks process identity")
    for k in target:
        _require(sid.get(k) == target[k], "typed source is from another game epoch")
    selected = source.get("selected")
    _require(isinstance(selected, dict), "typed selected source absent")
    before, after = selected.get("before"), selected.get("after")
    _require(isinstance(before, dict) and isinstance(after, dict),
             "typed selected source incomplete")
    unit = before.get("playerUnitId")
    _require(isinstance(unit, str) and unit.startswith("u") and unit == after.get("playerUnitId"),
             "typed source player identity changed")
    _require(type(before.get("sequence")) is int
             and type(after.get("sequence")) is int
             and 0 < before["sequence"] < after["sequence"]
             and type(before.get("frameTime")) in (float, int)
             and type(after.get("frameTime")) in (float, int)
             and math.isfinite(float(before["frameTime"]))
             and math.isfinite(float(after["frameTime"]))
             and before["frameTime"] < after["frameTime"],
             "typed source did not independently advance")
    for sample in (before, after):
        xyz = sample.get("xyz")
        _require(isinstance(xyz, dict)
                 and all(type(xyz.get(axis)) in (int, float)
                         and math.isfinite(float(xyz[axis])) for axis in ("x", "y", "z")),
                 "source coordinates incomplete or nonfinite")
    _require(all(abs(float(before["xyz"][axis]) - float(after["xyz"][axis])) <= tolerance
                 for axis in ("x", "y", "z")),
             "typed source position changed during purported stationary reference")
    s = source.get("source")
    _require(isinstance(s, dict) and isinstance(s.get("after"), dict),
             "typed capture completion time is absent")
    return after["xyz"], unit, _time(s["after"].get("completedAtUtc"))


def _native(report: dict, digest: str, request_sha: str, target: dict) -> dict:
    _require(report.get("schemaVersion") == 1
             and report.get("evidenceKind") == POINTER_KIND
             and report.get("requestSha256") == request_sha,
             "native pointer report does not match verified request")
    chain = report.get("chain")
    _require(isinstance(chain, dict) and chain.get("rootRva") == ROOT_RVA
             and chain.get("offsets") == [0], "unexpected native pointer chain")
    result = report.get("resolution")
    _require(isinstance(result, dict) and result.get("status") == "complete"
             and result.get("reason") is None, "native pointer did not resolve completely")
    identity = _identity(result.get("expectedIdentity"), target)
    other = _identity(result.get("observedIdentity"), target)
    _require(identity == other, "observed native identity differs from expected")
    hops = result.get("hops")
    _require(isinstance(hops, list) and len(hops) == 1, "native pointer hop count differs")
    hop = hops[0]
    _require(isinstance(hop, dict) and hop.get("level") == 1
             and hop.get("pointerAddress") == identity["moduleBaseAddress"] + ROOT_RVA
             and hop.get("offset") == 0, "native pointer root/hop differs")
    pointer = hop.get("pointerValue")
    _require(type(pointer) is int and 0x10000 <= pointer <= 0x7FFFFFFFFFFF
             and hop.get("resolvedAddress") == pointer
             and result.get("terminalAddress") == pointer, "native owner pointer invalid")
    _require(struct.unpack("<Q", _bytes64(hop.get("pointerBytes"), 8))[0] == pointer,
             "raw native root pointer does not match resolved address")
    terminal = result.get("terminalRead")
    _require(isinstance(terminal, dict) and terminal.get("status") == "success",
             "terminal native owner read is incomplete")
    blob = _bytes64(terminal.get("bytes"), WINDOW_BYTES)
    xyz = dict(zip(("x", "y", "z"), struct.unpack_from("<fff", blob, XYZ_OFFSETS[0])))
    _require(all(math.isfinite(v) for v in xyz.values()), "native XYZ contains nonfinite float32")
    _require(result.get("failedRead") is None and result.get("failedReadAddress") is None,
             "native complete report includes inconsistent failure")
    when = _time(report.get("completedAtUtc"))
    return {
        "sourceSha256": digest,
        "completedAtUtc": when.isoformat(),
        "ownerSessionAddress": f"0x{pointer:X}",
        "mainModuleBaseAddress": f"0x{identity['moduleBaseAddress']:X}",
        "rootPointerAddress": f"0x{hop['pointerAddress']:X}",
        "xyz": xyz,
    }


def review(before: Path, after: Path, request: Path, source: Path,
           pinned_source_sha256: str, tolerance: float) -> dict:
    _pin_sha(pinned_source_sha256)
    _require(0 < tolerance <= 0.1 and math.isfinite(tolerance),
             "XYZ comparison tolerance outside bound")
    req, req_sha = read_source(request)
    target = _target(req)
    typed, typed_sha = read_source(source)
    _require(typed_sha == pinned_source_sha256,
             "advancing Lua source has changed since qualification")
    xyz, unit, source_time = _source_xyz(typed, target, tolerance)
    observations = []
    for path in (before, after):
        report, digest = read_source(path)
        observations.append(_native(report, digest, req_sha, target))
    _require(observations[0]["sourceSha256"] != observations[1]["sourceSha256"],
             "two native reports cannot be the same bytes")
    times = [_time(item["completedAtUtc"]) for item in observations]
    _require(times[0] < times[1], "native reports are not chronologically distinct")
    comparisons = []
    for item, instant in zip(observations, times):
        errors = {k: round(item["xyz"][k] - float(xyz[k]), 10)
                  for k in ("x", "y", "z")}
        comparisons.append({
            "nativeCompletedAtUtc": instant.isoformat(),
            "sourceToNativeSeconds": round((instant - source_time).total_seconds(), 3),
            "perAxisNativeMinusLua": errors,
            "allAxesWithinTolerance": all(abs(e) <= tolerance for e in errors.values()),
        })
    agree = all(c["allAxesWithinTolerance"] for c in comparisons)
    return {
        "schemaVersion": 1,
        "evidenceKind": "native-pointer-versus-typed-wire-review/1",
        "status": "candidate-compatible" if agree else "candidate-disagrees",
        "qualification": "candidate-only-not-synchronized",
        "target": target,
        "playerUnitId": unit,
        "rootRva": "0x32E0200",
        "xyzOffsets": [f"0x{x:X}" for x in XYZ_OFFSETS],
        "sourceComparisonSha256": typed_sha,
        "pointerRequestSha256": req_sha,
        "tolerance": tolerance,
        "sourceLuaXYZ": xyz,
        "nativeSamples": observations,
        "comparisons": comparisons,
        "limitations": [
            "Native and Lua observations were not simultaneous: elapsed seconds are explicit.",
            "A numeric match alone cannot qualify semantic field meaning, movement or patch resilience.",
            "Only one root dereference and exactly 816 terminal owner bytes were read per native report.",
            "Raw originals and their SHA-256 hashes must remain available for independent review."
        ]
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "request", "source", "source-sha256", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args(argv)
    try:
        dest = Path(args.output)
        _require(dest.parent.is_dir() and not dest.exists() and not dest.is_symlink(),
                 "output parent missing or output already exists")
        result = review(Path(args.before), Path(args.after), Path(args.request),
                        Path(args.source), args.source_sha256, args.tolerance)
        with dest.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
    except (EvidenceError, OSError, TypeError, KeyError, OverflowError, ValueError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "output": str(dest),
                      "qualification": result["qualification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
