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
    cross_epoch_pairs = []
    for i, first in enumerate(samples):
        for second in samples[i + 1:]:
            if (first["processId"], first["processStartUtcTicks"]) == (
                second["processId"], second["processStartUtcTicks"]
            ) or first["unitId"] != second["unitId"]:
                continue
            supported = all(
                item["withinTolerance"] and item["rootWindowStability"] == "verified"
                for item in (first, second)
            )
            cross_epoch_pairs.append({
                "firstRunId": first["runId"],
                "secondRunId": second["runId"],
                "differentProcessEpochs": True,
                "samePlayerAndBuild": True,
                "ownerSessionAddressChanged": (
                    first["ownerSessionAddress"] != second["ownerSessionAddress"]
                ),
                "eachRootAndLuaCheckPassed": supported,
            })
    restart_observed = not disagreements and any(
        pair["eachRootAndLuaCheckPassed"] for pair in cross_epoch_pairs
    )
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
        "restartSurvival": (
            "same-build-candidate-observed" if restart_observed else "not-assessed"
        ),
        "updateSurvival": "not-assessed",
        "oldEpochRequestRejection": "not-tested-by-this-tool",
        "limitations": [
            "A numeric match does not establish a field's meaning.",
            "A saved heap address is not a durable locator.",
            "Cross-epoch matches are candidate restart evidence, not automatic field qualification.",
            "Update survival and invalid-old-epoch request rejection require separate validation.",
            "Host/guest sampling is not atomic; stale or moving references are inconclusive.",
        ],
        "captures": samples,
        "withinEpochMovementComparisons": pairs,
        "crossEpochSameBuildComparisons": cross_epoch_pairs,
    }



def _typed_numeric_field(reference, name, *, required=True):
    typed = _object(_object(reference.get("readback"), "readback").get("typedApi"), "typedApi")
    player = _object(_object(typed.get("snapshot"), "snapshot").get("player"), "player")
    fields = _object(player.get("fields"), "player.fields")
    field = _object(fields.get(name), f"player.{name}")
    if field.get("status") != "ok":
        if required:
            raise EvidenceError(f"typed reference {name} is unavailable")
        return None
    return _integer(field.get("value"), f"typed.{name}")


def evaluate_health_scan(path, root_rva, level_hint=None):
    """Reduce bounded raw health hits; never imply field identity or coverage."""
    if level_hint is not None and (type(level_hint) is not int or not 1 <= level_hint <= 255):
        raise EvidenceError("level hint must be an integer between 1 and 255")
    # Reuse the field-lab identity, root stability, SHA-256 and typed-Lua checks.
    position = inspect_report(Path(path), root_rva, (0x320, 0x324, 0x328), 0.02)
    report, report_hash = load_report(Path(path))
    if report.get("plan", {}).get("healthScan") is not True:
        raise EvidenceError("field-lab plan did not request a health scan")
    before, after = report["referenceBefore"], report["referenceAfter"]
    current = _typed_numeric_field(before, "health")
    current_after = _typed_numeric_field(after, "health")
    maximum = _typed_numeric_field(before, "healthMax")
    maximum_after = _typed_numeric_field(after, "healthMax")
    power = _typed_numeric_field(before, "power", required=False)
    power_after = _typed_numeric_field(after, "power", required=False)
    scan = _object(report.get("healthScan"), "healthScan")
    if (_integer(scan.get("referenceHealth"), "healthScan.referenceHealth")
            != current):
        raise EvidenceError("health scan does not match typed reference health")
    bytes_scanned = _integer(scan.get("bytesScanned"), "healthScan.bytesScanned")
    failures = _integer(scan.get("failedChunks"), "healthScan.failedChunks")
    seconds = _number(scan.get("seconds"), "healthScan.seconds")
    if (bytes_scanned > 1024 ** 3 or seconds < 0 or seconds > 120
            or type(scan.get("truncated")) is not bool):
        raise EvidenceError("invalid health scan bounds or truncation")
    hits = scan.get("hits")
    if not isinstance(hits, list) or len(hits) > 128:
        raise EvidenceError("health scan hit array exceeds documented bounds")
    if not isinstance(scan.get("regions"), list) or len(scan["regions"]) > 32768:
        raise EvidenceError("invalid or unbounded region count")

    matched = []
    incomplete = []
    seen = set()
    for index, entry in enumerate(hits):
        hit = _object(entry, f"hit[{index}]")
        at = _hex(hit.get("address"), f"hit[{index}].address")
        start = _hex(hit.get("contextAddress"), f"hit[{index}].contextAddress")
        if at in seen:
            raise EvidenceError(f"duplicate health hit address: 0x{at:X}")
        seen.add(at)
        flags = {k: hit.get(k) for k in ("int32", "float32", "float64")}
        if any(type(v) is not bool for v in flags.values()) or not any(flags.values()):
            raise EvidenceError("hit must declare at least one typed encoding")
        read = _object(hit.get("read"), "health hit context")
        data = _bytes(read.get("bytes"), "health hit context bytes")
        declared_hash = _hash(hit.get("sha256"), "health hit context hash")
        if hashlib.sha256(data).hexdigest().upper() != declared_hash:
            raise EvidenceError(f"health hit context SHA-256 mismatch: 0x{at:X}")
        offset = at - start
        if (len(data) > 256 or offset < 0 or offset >= len(data)
                or at >= 1 << 64):
            raise EvidenceError("health hit is outside bounded context")
        if read.get("status") != "success":
            incomplete.append({"address": f"0x{at:X}", "reason": "context-read-incomplete"})
            continue
        formats = (("int32", "<i"), ("float32", "<f"), ("float64", "<d"))
        agreed = []
        for kind, fmt in formats:
            if not flags[kind]:
                continue
            if offset + struct.calcsize(fmt) > len(data) or struct.unpack_from(fmt, data, offset)[0] != current:
                incomplete.append({"address": f"0x{at:X}", "reason": f"{kind}-context-value-changed"})
            else:
                agreed.append(kind)
        if not agreed:
            continue
        matched.append({"address": at, "encodings": agreed,
                        "contextAddress": start, "contextBytes": data,
                        "contextSha256": declared_hash})
    matched.sort(key=lambda x: x["address"])
    # An address cluster merely reduces duplicates from adjacent health slots.
    clusters = []
    for row in matched:
        if clusters and row["address"] - clusters[-1]["addresses"][-1] <= 32:
            clusters[-1]["addresses"].append(row["address"])
            clusters[-1]["rows"].append(row)
        else:
            clusters.append({"addresses": [row["address"]], "rows": [row]})
    structured = []
    for group in clusters:
        start, end = group["addresses"][0], group["addresses"][-1]
        nearby_power = False
        nearby_level = False
        for row in group["rows"]:
            data = row["contextBytes"]
            context_base = row["contextAddress"]
            lower = max(context_base, start - 64)
            upper = min(context_base + len(data) - 4, end + 64)
            first = lower + ((4 - lower % 4) % 4)
            for address in range(first, upper + 1, 4):
                value = struct.unpack_from("<i", data, address - context_base)[0]
                nearby_power = nearby_power or (power is not None and value == power)
                nearby_level = nearby_level or (level_hint is not None and value == level_hint)
        structured.append({
            "firstSessionAddress": f"0x{start:X}",
            "lastSessionAddress": f"0x{end:X}",
            "addressCount": len(group["rows"]),
            "encodings": sorted(set(kind for row in group["rows"] for kind in row["encodings"])),
            "nearbyTypedPowerValue": nearby_power,
            "nearbyLevelHintValue": nearby_level if level_hint is not None else None,
            "contextHashes": sorted({row["contextSha256"] for row in group["rows"]}),
        })
    # Structural ordering, never a confidence or field-identification score.
    structured.sort(key=lambda g: (
        -g["addressCount"], -int(g["nearbyTypedPowerValue"]),
        -int(g["nearbyLevelHintValue"] is True), g["firstSessionAddress"]
    ))
    return {
        "schemaVersion": 1,
        "evidenceKind": "native-health-hit-review/1",
        "sourcePath": str(path),
        "sourceSha256": report_hash,
        "runId": position["runId"],
        "buildSha256": position["buildSha256"],
        "processId": position["processId"],
        "processStartUtcTicks": position["processStartUtcTicks"],
        "ownerSessionAddress": position["ownerSessionAddress"],
        "rootWindowStability": position["rootWindowStability"],
        "typedReference": {
            "health": [current, current_after],
            "healthMax": [maximum, maximum_after],
            "rawPower": [power, power_after],
            "levelHint": level_hint,
            "healthChangedDuringScan": current != current_after,
            "powerChangedDuringScan": power != power_after,
            "sourceSequences": position["sourceSequences"],
        },
        "scanCoverage": {
            "bytesScanned": bytes_scanned,
            "failedChunks": failures,
            "seconds": seconds,
            "truncated": scan["truncated"],
            "regionCount": len(scan["regions"]),
            "recordedHitCount": len(hits),
            "matchingHitCount": len(matched),
            "incompleteContextCount": len(incomplete),
            "completeMemoryCoverage": False,
        },
        "incompleteContexts": incomplete,
        "candidateGroups": structured,
        "candidateGroupCount": len(structured),
        "qualification": "candidate-only",
        "fieldMeaning": "unqualified",
        "restartSurvival": "not-assessed",
        "updateSurvival": "not-assessed",
        "limitations": [
            "Adjacent matches and nearby values can be cached or copied observations.",
            "Health equal to healthMax cannot distinguish current from maximum.",
            "Optional level hint is caller-supplied, not validated by typed Lua.",
            "Scan regions were budget-limited and not atomically acquired.",
            "Context reads after matches can change and are not field attestation.",
            "Addresses are process-specific and must not be reused after restart.",
        ],
    }


def _health_marker_groups(review, report):
    """Summarize stable integer-marker layouts, not pointer relationships."""
    refs = review["typedReference"]
    current, maximum = refs["health"][0], refs["healthMax"][0]
    power = refs["rawPower"][0]
    level = refs["levelHint"]
    values = (("currentHealth", current), ("maximumHealth", maximum),
              ("rawPower", power), ("visualLevelHint", level))
    hits = {
        _hex(hit["address"], "health-hit.address"): hit
        for hit in report["healthScan"]["hits"]
    }
    grouped = {}
    eligible = 0
    for group in review["candidateGroups"]:
        first = _hex(group["firstSessionAddress"], "candidate group address")
        hit = hits[first]
        if hit.get("int32") is not True or hit["read"].get("status") != "success":
            continue
        raw = _bytes(hit["read"]["bytes"], "validated hit context")
        start = _hex(hit["contextAddress"], "context start")
        sites = []
        families = set()
        # Compare bounded typed reference markers only; never normalize arbitrary
        # pointers, offsets, non-finite floats, or unknown integer constants.
        for delta in range(-16, 65, 4):
            index = first + delta - start
            if index < 0 or index + 4 > len(raw):
                continue
            word = struct.unpack_from("<i", raw, index)[0]
            tags = [name for name, value in values
                    if value is not None and word == value]
            if not tags:
                continue
            sites.append({"delta": delta, "tags": tags})
            families.update("health" if tag in ("currentHealth", "maximumHealth")
                            else "power" if tag == "rawPower" else "level"
                            for tag in tags)
        if len(sites) < 3 or len(families) < 2:
            continue
        eligible += 1
        key = json.dumps(sites, separators=(",", ":"), sort_keys=True)
        grouped.setdefault(key, []).append(group["firstSessionAddress"])
    return ({key: sorted(addresses) for key, addresses in grouped.items()}, eligible)


def compare_health_structures(paths, root_rva, level_hint=None):
    """Compare marker-layout multiplicity across two exact process epochs.

    Repeats can reveal likely copies, never an authoritative memory field.
    """
    if len(paths) != 2:
        raise EvidenceError("health structure comparison requires exactly two reports")
    sources = []
    for path in paths:
        review = evaluate_health_scan(Path(path), root_rva, level_hint)
        report, digest = load_report(Path(path))
        if digest != review["sourceSha256"]:
            raise EvidenceError("health source changed between validation and comparison")
        snapshot = _object(
            report["referenceBefore"]["readback"]["typedApi"]["snapshot"], "typed snapshot"
        )
        player = _object(snapshot.get("player"), "player")
        sources.append({"review": review, "report": report,
                        "playerId": player.get("unitId")})
    sources.sort(key=lambda item: (
        _utc_ticks(item["report"]["startedAtUtc"], "report startedAtUtc"),
        item["review"]["runId"],
    ))
    first, second = sources
    a, b = first["review"], second["review"]
    if (a["sourceSha256"] == b["sourceSha256"] or a["runId"] == b["runId"]):
        raise EvidenceError("duplicate reports cannot establish independent epochs")
    if a["buildSha256"] != b["buildSha256"]:
        raise EvidenceError("health reports have different game builds")
    if (a["processId"], a["processStartUtcTicks"]) == (
        b["processId"], b["processStartUtcTicks"]
    ):
        raise EvidenceError("health structure comparison needs distinct process epochs")
    if (not first["playerId"] or first["playerId"] != second["playerId"]):
        raise EvidenceError("health observations belong to different players")
    references = (a["typedReference"], b["typedReference"])
    changed_during = any(
        x["healthChangedDuringScan"] or x["powerChangedDuringScan"]
        or x["healthMax"][0] != x["healthMax"][1]
        for x in references
    )
    same_static_values = all(
        references[0][name][0] == references[1][name][0]
        for name in ("health", "healthMax", "rawPower")
    )
    comparable = not changed_during and same_static_values
    patterns = []
    eligible_counts = [0, 0]
    if comparable:
        layouts = []
        for i, item in enumerate(sources):
            matches, count = _health_marker_groups(item["review"], item["report"])
            layouts.append(matches)
            eligible_counts[i] = count
        for shape in layouts[0].keys() & layouts[1].keys():
            sites = json.loads(shape)
            left, right = layouts[0][shape], layouts[1][shape]
            patterns.append({
                "signatureSha256": hashlib.sha256(shape.encode("utf-8")).hexdigest().upper(),
                "typedMarkerLayout": sites,
                "firstEpochInstances": len(left),
                "secondEpochInstances": len(right),
                "firstEpochExamples": left[:5],
                "secondEpochExamples": right[:5],
                "replicatedInEitherEpoch": len(left) > 1 or len(right) > 1,
                "uniqueInBothEpochs": len(left) == len(right) == 1,
            })
        patterns.sort(key=lambda item: (
            -min(item["firstEpochInstances"], item["secondEpochInstances"]),
            -len(item["typedMarkerLayout"]),
            item["signatureSha256"],
        ))
    source_summary = []
    for item in sources:
        review = item["review"]
        source_summary.append({
            "runId": review["runId"],
            "reportSha256": review["sourceSha256"],
            "reportPath": review["sourcePath"],
            "processId": review["processId"],
            "processStartUtcTicks": review["processStartUtcTicks"],
            "playerId": item["playerId"],
            "rawMatchCount": review["scanCoverage"]["recordedHitCount"],
            "candidateGroupCount": review["candidateGroupCount"],
            "scanTruncated": review["scanCoverage"]["truncated"],
            "incompleteContextCount": review["scanCoverage"]["incompleteContextCount"],
        })
    return {
        "schemaVersion": 1,
        "evidenceKind": "native-health-cross-epoch-structure-review/1",
        "rootRva": f"0x{root_rva:X}",
        "buildSha256": a["buildSha256"],
        "referenceValues": {
            "health": [x["health"] for x in references],
            "healthMax": [x["healthMax"] for x in references],
            "rawPower": [x["rawPower"] for x in references],
            "levelHint": level_hint,
        },
        "comparisonStatus": ("static-marker-layout-comparison" if comparable
                             else "reference-changed-or-different-values"),
        "sourceReports": source_summary,
        "eligibleMarkerGroupsByEpoch": eligible_counts,
        "sharedPatternCount": len(patterns),
        "sharedMarkerPatterns": patterns,
        "qualification": "candidate-only",
        "healthValueChangeValidated": False,
        "resourceValueChangeValidated": False,
        "restartSurvival": "not-qualified",
        "updateSurvival": "not-assessed",
        "limitations": [
            "The two scans are truncated and do not cover identical heap allocations.",
            "Marker layouts match data shapes, not pointer chains or object identities.",
            "Repeated layouts may be UI, network, serializer, or cache copies.",
            "Health equals maximum in these observations and does not distinguish the two.",
            "Static matches without changed values do not identify gameplay health or power.",
            "Session addresses in examples must never be reused after a restart.",
            "The optional visual level is a caller-provided hint, not typed API evidence.",
        ],
    }


def review_old_epoch_probe(previous_path, probe_path, root_rva):
    """Verify a lab's negative native-session open against a retained prior epoch.

    The lab check uses WindowsNativeMemorySession.OpenAsync, not a direct
    invocation of the public follow-pointer command.
    """
    offsets = (0x320, 0x324, 0x328)
    previous = inspect_report(Path(previous_path), root_rva, offsets, 0.02)
    current = inspect_report(Path(probe_path), root_rva, offsets, 0.02)
    report, digest = load_report(Path(probe_path))
    if digest != current["sourceSha256"]:
        raise EvidenceError("probe report bytes changed during review")
    if (previous["runId"] == current["runId"]
            or previous["sourceSha256"] == current["sourceSha256"]):
        raise EvidenceError("prior and probe must be independent captures")
    if previous["buildSha256"] != current["buildSha256"]:
        raise EvidenceError("prior and probe executable builds differ")
    if previous["unitId"] != current["unitId"]:
        raise EvidenceError("prior and probe character identities differ")
    if ((previous["processId"], previous["processStartUtcTicks"])
            == (current["processId"], current["processStartUtcTicks"])):
        raise EvidenceError("probe must run in a different process epoch")
    if _utc_ticks(previous["captureStartUtc"], "prior timestamp") >= _utc_ticks(
        current["captureStartUtc"], "probe timestamp"
    ):
        raise EvidenceError("prior capture must precede the probe")
    if not all(s["rootWindowStability"] == "verified" and s["withinTolerance"]
               for s in (previous, current)):
        raise EvidenceError("both root and typed Lua checks must be verified")

    plan = _object(report.get("plan"), "probe plan")
    old_pid = _integer(plan.get("oldPid"), "plan.oldPid", 1)
    old_start = _integer(plan.get("oldStartTicks"), "plan.oldStartTicks", 1)
    if old_start != previous["processStartUtcTicks"]:
        raise EvidenceError("probe start does not match independent prior-epoch evidence")
    if old_start == current["processStartUtcTicks"]:
        raise EvidenceError("probe start is not stale")
    if report.get("oldEpochRejected") is not True:
        raise EvidenceError("field lab did not explicitly reject the old epoch")
    reason = report.get("oldEpochError")
    if not isinstance(reason, str) or not reason or len(reason) > 512:
        raise EvidenceError("missing or oversized negative-check reason")
    if old_pid == previous["processId"]:
        mode = "retired-pid-open-rejected"
        expected = "OpenProcess failed with Win32 error 87."
    elif old_pid == current["processId"]:
        mode = "live-pid-stale-start-rejected"
        expected = "The process start identity does not match the capture request."
    else:
        raise EvidenceError("probe PID does not match the prior or current game process")
    if reason != expected:
        raise EvidenceError("the reported rejection reason does not match the planned mode")

    return {
        "schemaVersion": 1,
        "evidenceKind": "native-field-lab-old-epoch-probe-review/1",
        "testMode": mode,
        "rootRva": f"0x{root_rva:X}",
        "buildSha256": current["buildSha256"],
        "sourceReports": [
            {"role": "prior", "runId": previous["runId"],
             "path": previous["sourcePath"], "sha256": previous["sourceSha256"],
             "pid": previous["processId"],
             "startUtcTicks": previous["processStartUtcTicks"]},
            {"role": "probe", "runId": current["runId"],
             "path": current["sourcePath"], "sha256": current["sourceSha256"],
             "pid": current["processId"],
             "startUtcTicks": current["processStartUtcTicks"]}
        ],
        "requestedOldPid": old_pid,
        "requestedOldStartUtcTicks": old_start,
        "oldEpochRejected": True,
        "rejectionReason": reason,
        "currentRootStability": current["rootWindowStability"],
        "currentPositionWithinTolerance": current["withinTolerance"],
        "currentNativeXyz": current["nativeXyz"],
        "currentLuaXyz": current["luaBeforeXyz"],
        "qualification": "candidate-only",
        "updateSurvival": "not-assessed",
        "limitations": [
            "This is a field-lab Windows session-open rejection, not a direct live follow-pointer CLI test.",
            "An unopenable retired PID alone does not establish PID reuse or start-time validation.",
            "A same-build successful pointer read does not qualify field meaning or update survival."
        ]
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--root-rva", required=True)
    parser.add_argument("--xyz-offsets", nargs=3)
    parser.add_argument("--health-hits", action="store_true", help="Review typed health matches from one field-lab report")
    parser.add_argument("--compare-health-hits", action="store_true", help="Compare bounded health marker shapes across two game epochs")
    parser.add_argument("--verify-old-epoch", action="store_true", help="Check one lab rejection against independently retained prior-epoch evidence")
    parser.add_argument("--prior-report", type=Path, help="Prior game epoch for --verify-old-epoch")
    parser.add_argument("--level-hint", type=int, help="Optional visually observed level, not verified by typed Lua")
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        root = _hex(args.root_rva, "root-rva")
        if sum((args.health_hits, args.compare_health_hits, args.verify_old_epoch)) > 1:
            raise EvidenceError("choose exactly one review mode")
        if args.verify_old_epoch:
            if (len(args.report) != 1 or args.prior_report is None
                    or args.xyz_offsets is not None or args.level_hint is not None
                    or args.tolerance != 0.02):
                raise EvidenceError("old-epoch review requires one probe, one prior, and default tolerance")
            evaluation = review_old_epoch_probe(args.prior_report, args.report[0], root)
        elif args.compare_health_hits:
            if len(args.report) != 2 or args.xyz_offsets is not None or args.prior_report is not None:
                raise EvidenceError("health comparison requires two reports without XYZ arguments")
            evaluation = compare_health_structures(args.report, root, args.level_hint)
        elif args.health_hits:
            if len(args.report) != 1 or args.xyz_offsets is not None or args.prior_report is not None:
                raise EvidenceError("health review requires exactly one report and no XYZ arguments")
            evaluation = evaluate_health_scan(args.report[0], root, args.level_hint)
        else:
            if args.xyz_offsets is None or args.level_hint is not None or args.prior_report is not None:
                raise EvidenceError("position review requires three XYZ offsets without a level hint")
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
