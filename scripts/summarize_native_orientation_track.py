"""Compare retained exact-current-build orientation snapshots without live access.

Raw 3x3 matrix changes and planar angle arithmetic are CANDIDATES, never
body/camera heading, player facing, movement, or passive freshness proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.project_xyz_track import _pairs, _utc

GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
QUALIFICATION = "matrix-descriptor-candidate-only; body-facing/axis/sign/passive-freshness/restart-unverified"
CONTRACT = "native-current-orientation-candidate/1"
MAX_FILES, MAX_BYTES_PER_FILE, MAX_TOTAL_BYTES = 30, 256_000, 4_000_000
STRUCTURAL = "structural-y-planar-matrix-candidate"


def _matrix(value, offset):
    if not isinstance(value, dict) or type(value.get("sourceOffset")) is not int or value["sourceOffset"] != offset:
        raise ValueError("invalid matrix source offset")
    bits = value.get("rawBits")
    if (not isinstance(bits, list) or len(bits) != 9
            or any(type(b) is not int or not 0 <= b <= 0xFFFFFFFF for b in bits)):
        raise ValueError("invalid raw matrix bits")
    floats = [struct.unpack("<f", struct.pack("<I", b))[0] for b in bits]
    finite = all(math.isfinite(f) for f in floats)
    status = value.get("status")
    rows = value.get("rowMajorF32")
    angle = value.get("planarAngleDegreesCandidate")
    if status == "nonfinite-matrix":
        if finite or rows is not None or angle is not None:
            raise ValueError("inconsistent nonfinite matrix")
    elif status in (STRUCTURAL, "unqualified-matrix-shape"):
        if not finite or not isinstance(rows, list) or len(rows) != 9:
            raise ValueError("inconsistent finite matrix")
        for v, bit in zip(rows, bits):
            if type(v) not in (int, float) or not math.isfinite(v):
                raise ValueError("invalid decoded matrix")
            try:
                if struct.unpack("<I", struct.pack("<f", v))[0] != bit:
                    raise ValueError("raw and decoded matrix disagree")
            except (OverflowError, struct.error):
                raise ValueError("invalid decoded matrix") from None
        if status == STRUCTURAL:
            if type(angle) not in (int, float) or not math.isfinite(angle):
                raise ValueError("invalid structural matrix angle")
            source_angle = math.degrees(math.atan2(floats[6], floats[0]))
            if abs(source_angle - angle) > 0.001:
                raise ValueError("inconsistent structural matrix angle")
        elif angle is not None:
            raise ValueError("unqualified matrix cannot yield angle")
    else:
        raise ValueError("unknown matrix status")
    return {"bits": bits, "angle": float(angle) if status == STRUCTURAL else None, "status": status}


def _read(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_BYTES_PER_FILE + 1)
    if len(raw) > MAX_BYTES_PER_FILE:
        raise ValueError("orientation report exceeds size limit")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs)
    if (not isinstance(value, dict) or type(value.get("schemaVersion")) is not int
            or value["schemaVersion"] != 1 or value.get("contractVersion") != CONTRACT
            or value.get("status") != "complete"):
        raise ValueError("invalid orientation report contract")
    ob = value.get("observation")
    if not isinstance(ob, dict) or ob.get("qualification") != QUALIFICATION:
        raise ValueError("missing candidate qualification")
    identity = ob.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("missing process identity")
    pid, ticks = identity.get("processId"), identity.get("processStartUtcTicks")
    base, size = identity.get("moduleBaseAddress"), identity.get("moduleSize")
    if (type(pid) is not int or not 0 < pid < 2**31
            or type(ticks) is not int or not 0 < ticks < 2**63
            or type(base) is not int or not 0 < base <= 2**64 - 1
            or type(size) is not int or not 0 < size < 2**63
            or base + size > 2**64 or identity.get("executableSha256") != GAME_SHA):
        raise ValueError("invalid current-build epoch")
    key = ob.get("unitKey")
    if (not isinstance(key, str) or re.fullmatch(r"[1-9][0-9]{0,19}", key) is None
            or int(key) > 2**64 - 1):
        raise ValueError("invalid sampled unit key")
    component = ob.get("componentAddress")
    if type(component) is not int or not 0 < component <= 2**64 - 1:
        raise ValueError("invalid component address")
    handle, flag = ob.get("refreshHandleRaw"), ob.get("refreshFlagRaw")
    if (not isinstance(handle, str) or re.fullmatch(r"0x[0-9A-F]{16}", handle) is None
            or type(flag) is not int or not 0 <= flag <= 255):
        raise ValueError("invalid refresh input")
    started, completed = _utc(ob.get("startedAtUtc")), _utc(ob.get("completedAtUtc"))
    if completed < started:
        raise ValueError("orientation sample time reversed")
    return {"identity": identity, "unitKey": key, "component": component,
            "refresh": (handle, flag), "started": started, "completed": completed,
            "primary": _matrix(ob.get("primary"), 0x60),
            "secondary": _matrix(ob.get("secondary"), 0x94),
            "sourceSha256": hashlib.sha256(raw).hexdigest().upper(),
            "sourceBytes": len(raw)}


def compare(paths, *, max_gap_seconds=5.0):
    if not 2 <= len(paths) <= MAX_FILES:
        raise ValueError("requires 2..30 retained reports")
    if type(max_gap_seconds) not in (int, float) or not math.isfinite(max_gap_seconds) or not 0 < max_gap_seconds <= 300:
        raise ValueError("invalid gap limit")
    samples = [_read(path) for path in paths]
    if sum(s["sourceBytes"] for s in samples) > MAX_TOTAL_BYTES:
        raise ValueError("combined reports exceed size limit")
    first = samples[0]
    pairs = []
    for index, sample in enumerate(samples[1:], 2):
        prev = samples[index - 2]
        if (sample["identity"]["processId"], sample["identity"]["processStartUtcTicks"],
            sample["identity"]["executableSha256"], sample["identity"]["moduleBaseAddress"],
            sample["identity"]["moduleSize"], sample["unitKey"]) != (
            first["identity"]["processId"], first["identity"]["processStartUtcTicks"],
            first["identity"]["executableSha256"], first["identity"]["moduleBaseAddress"],
            first["identity"]["moduleSize"], first["unitKey"]):
            raise ValueError("process epoch or sampled unit key changed")
        if sample["started"] <= prev["started"] or sample["started"] < prev["completed"]:
            raise ValueError("orientation reports overlap or are unordered")
        gap = (sample["started"] - prev["completed"]).total_seconds()
        boundary = (sample["component"] != prev["component"] or gap > max_gap_seconds)
        pair = {"from": index - 1, "to": index, "intervalGapSeconds": gap,
                "status": ("boundary-component-changed" if sample["component"] != prev["component"]
                           else "boundary-time-gap" if boundary else "candidate-comparable"),
                "refreshInputsChanged": sample["refresh"] != prev["refresh"]}
        for name in ("primary", "secondary"):
            before, after = prev[name], sample[name]
            equal = None if boundary else before["bits"] == after["bits"]
            angles = (before["angle"], after["angle"])
            # Signed shortest angular displacement in matrix-axis convention ONLY.
            delta = ((angles[1] - angles[0] + 180) % 360 - 180) if (
                not boundary and None not in angles) else None
            pair[name] = {"rawBitsEqual": equal,
                          "candidateMatrixAngleDeltaDegrees": delta,
                          "angleStatus": "candidate-structural-matrix-arithmetic" if delta is not None
                                         else "unavailable-unqualified-or-boundary"}
        pairs.append(pair)
    admitted = [p for p in pairs if p["status"] == "candidate-comparable"]
    identity = dict(first["identity"])
    identity["processStartUtcTicks"] = str(identity["processStartUtcTicks"])
    return {"schemaVersion": 1,
            "contractVersion": "native-orientation-crossreport-comparison-candidate/1",
            "status": "candidate-only",
            "sourceBuildSha256": GAME_SHA, "processIdentity": identity,
            "sampledUnitKey": first["unitKey"], "sourceCount": len(samples),
            "sources": [{"index": i, "sha256": s["sourceSha256"], "bytes": s["sourceBytes"],
                         "startedAtUtc": s["started"].isoformat()} for i, s in enumerate(samples, 1)],
            "acceptedPairCount": len(admitted),
            "primaryRawChangedPairs": sum(p["primary"]["rawBitsEqual"] is False for p in admitted),
            "secondaryRawChangedPairs": sum(p["secondary"]["rawBitsEqual"] is False for p in admitted),
            "pairs": pairs,
            "freshness": "unavailable-offline", "zoneIdentity": "unavailable-in-source",
            "worldIdentity": "unavailable-in-source", "facing": "unqualified",
            "limitations": [
                "Raw matrix equality/change is candidate arithmetic, not passive freshness or observed turning.",
                "Structural matrix angle is NOT player body facing, public heading, camera yaw or compass bearing.",
                "Only same sampled process epoch/key/component and bounded nonoverlapping UTC intervals are compared.",
                "No continuity or movement is inferred across component changes or time-gap boundaries.",
                "Source hashes preserve retained bytes, not authenticity or loaded-module identity."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--max-gap-seconds", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(compare(args.reports, max_gap_seconds=args.max_gap_seconds), allow_nan=False))
        return 0
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "unavailable", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
