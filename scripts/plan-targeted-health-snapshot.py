#!/usr/bin/env python3
"""Prepare a small, epoch-bound native-memory snapshot of repeated health layouts.

This is a read-only request generator. It never accesses RIFT or infers the
meaning of a field; run the existing RiftReader2.Live snapshot-native command
in the same guest process epoch to acquire actual bytes.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile


_SCRIPT = Path(__file__).with_name("native-field-evidence.py")
_SPEC = importlib.util.spec_from_file_location("rr2_saved_evidence", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("native field evidence validator is unavailable")
evidence = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(evidence)

MAX_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 16
BEFORE = 16
AFTER = 64
CAPTURE_BYTES = BEFORE + AFTER
CANONICAL_HEX = evidence.HEX_ADDRESS
SHA256 = evidence.SHA256


class SnapshotPlanError(evidence.EvidenceError):
    """A source, identity, or publication constraint was not satisfied."""


def _int(value, label, minimum=0):
    return evidence._integer(value, label, minimum)


def _hash(value, label):
    return evidence._hash(value, label)


def _obj(value, label):
    return evidence._object(value, label)


def _read_unique_json(path, byte_limit, label):
    path = Path(path)
    if not path.is_file():
        raise SnapshotPlanError(f"{label} is missing: {path}")
    with path.open("rb") as stream:
        raw = stream.read(byte_limit + 1)
    if len(raw) > byte_limit:
        raise SnapshotPlanError(f"{label} exceeds {byte_limit} bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=evidence._unique_object,
            parse_constant=evidence._bad_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotPlanError(f"invalid {label} JSON") from error
    return _obj(value, label), raw, hashlib.sha256(raw).hexdigest().upper()


def _timestamp(value, label):
    if not isinstance(value, str):
        raise SnapshotPlanError(f"{label} must be UTC")
    if value.endswith("+00:00"):
        value = value[:-6] + "Z"
    if not value.endswith("Z"):
        raise SnapshotPlanError(f"{label} must be UTC (Z or +00:00)")
    return evidence._utc_ticks(value, label)


def _numeric_field(fields, name):
    field = _obj(fields.get(name), f"typed.{name}")
    if field.get("status") != "ok":
        raise SnapshotPlanError(f"typed.{name} is not available")
    value = field.get("value")
    if type(value) is not int or value < 0:
        raise SnapshotPlanError(f"typed.{name} must be a nonnegative integer")
    return value


def prepare(health_report_path, cross_review_path, receiver_receipt_path,
            root_rva=0x32E0200, level_hint=45, max_candidates=8,
            age_limit_seconds=4.0, now_utc=None):
    if (type(root_rva) is not int or root_rva < 0 or
            type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES or
            not isinstance(age_limit_seconds, (int, float)) or isinstance(age_limit_seconds, bool) or
            not math.isfinite(age_limit_seconds) or not 0 < age_limit_seconds <= 30):
        raise SnapshotPlanError("invalid root, candidate count or receipt age limit")
    current = evidence.evaluate_health_scan(
        Path(health_report_path), root_rva, level_hint,
    )
    raw_health, raw_health_hash = evidence.load_report(Path(health_report_path))
    if raw_health_hash != current["sourceSha256"]:
        raise SnapshotPlanError("health report changed between reads")
    review, review_raw, review_hash = _read_unique_json(
        cross_review_path, MAX_RECEIPT_BYTES, "cross-epoch marker review",
    )
    if review.get("evidenceKind") != "native-health-cross-epoch-structure-review/1":
        raise SnapshotPlanError("incorrect cross-epoch review kind")
    if review.get("comparisonStatus") != "static-marker-layout-comparison":
        raise SnapshotPlanError("cross-epoch structure comparison is not available")
    if review.get("rootRva") != f"0x{root_rva:X}":
        raise SnapshotPlanError("root RVA differs from the cross-epoch review")
    if _hash(review.get("buildSha256"), "cross-epoch build") != current["buildSha256"]:
        raise SnapshotPlanError("cross-epoch build differs from source")
    sources = review.get("sourceReports")
    if not isinstance(sources, list) or len(sources) != 2:
        raise SnapshotPlanError("expected two cross-epoch source reports")
    source = [
        entry for entry in sources
        if isinstance(entry, dict) and entry.get("runId") == current["runId"]
        and entry.get("reportSha256") == current["sourceSha256"]
        and entry.get("processId") == current["processId"]
        and entry.get("processStartUtcTicks") == current["processStartUtcTicks"]
    ]
    if len(source) != 1:
        raise SnapshotPlanError("cross-epoch review does not pin the current source")
    patterns = review.get("sharedMarkerPatterns")
    if not isinstance(patterns, list) or len(patterns) != 1:
        raise SnapshotPlanError("exactly one shared marker pattern must be selected")
    pattern = _obj(patterns[0], "shared marker pattern")
    signature = _hash(pattern.get("signatureSha256"), "shared marker signature")
    if pattern.get("replicatedInEitherEpoch") is not True:
        raise SnapshotPlanError("requested workflow requires a replicated structure")
    layouts, _ = evidence._health_marker_groups(current, raw_health)
    available = []
    for shape, addresses in layouts.items():
        if hashlib.sha256(shape.encode("utf-8")).hexdigest().upper() == signature:
            if json.loads(shape) != pattern.get("typedMarkerLayout"):
                raise SnapshotPlanError("marker pattern content does not match hash")
            available.extend(addresses)
    if len(available) != pattern.get("secondEpochInstances"):
        raise SnapshotPlanError("current source pattern multiplicity differs from saved review")
    if not available:
        raise SnapshotPlanError("no matching health marker layouts remain")
    # Do not turn this into a wider scan: a capped, deterministic subset only.
    selected_addresses = sorted({evidence._hex(value, "marker address") for value in available})
    selected_addresses = selected_addresses[:max_candidates]

    receipt, receipt_raw, receipt_hash = _read_unique_json(
        receiver_receipt_path, MAX_RECEIPT_BYTES, "receiver receipt",
    )
    observation = _obj(receipt.get("observation"), "observation")
    target = _obj(observation.get("target"), "guest target")
    typed = _obj(_obj(observation.get("readback"), "readback").get("typedApi"), "typedApi")
    if (observation.get("riftProcessCount") != 1
            or observation.get("readback", {}).get("status") != "fresh"
            or typed.get("status") != "fresh"
            or typed.get("sequenceAdvanced") is not True
            or typed.get("frameTimeAdvanced") is not True):
        raise SnapshotPlanError("guest process count or typed API freshness invalid")
    if (type(target.get("processId")) is not int
            or target["processId"] != current["processId"]
            or _timestamp(target.get("processStartUtc"), "target start")
            != current["processStartUtcTicks"]
            or _hash(target.get("executableSha256"), "target build") != current["buildSha256"]):
        raise SnapshotPlanError("current game PID/start/build differs from candidate source")
    reported_time = _timestamp(receipt.get("receivedAtUtc"), "receipt time")
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        raise SnapshotPlanError("now_utc must be timezone-aware")
    now_ticks = evidence._utc_ticks(
        now_utc.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "evaluation time",
    )
    age = (now_ticks - reported_time) / 10_000_000
    if age < -0.5 or age > age_limit_seconds:
        raise SnapshotPlanError("receiver receipt is stale or dated in the future")
    current_unit = _obj(_obj(typed.get("snapshot"), "typed snapshot").get("player"), "typed player")
    if current_unit.get("unitId") != source[0].get("playerId"):
        raise SnapshotPlanError("player identity differs from candidate source")
    if type(typed.get("selectedSequence")) is not int or typed["selectedSequence"] < 1:
        raise SnapshotPlanError("missing advancing typed sequence")
    fields = _obj(current_unit.get("fields"), "typed player fields")
    current_values = {
        name: _numeric_field(fields, name)
        for name in ("health", "healthMax", "power")
    }

    hits = {
        evidence._hex(hit["address"], "health hit"): hit
        for hit in raw_health["healthScan"]["hits"]
    }
    ranges = []
    selections = []
    previous_end = 0
    for address in selected_addresses:
        hit = _obj(hits.get(address), f"health hit 0x{address:X}")
        if hit.get("int32") is not True:
            raise SnapshotPlanError("noninteger marker cannot seed an int32 snapshot")
        source_context = evidence._bytes(hit["read"].get("bytes"), "source context bytes")
        if (hit["read"].get("status") != "success"
                or hashlib.sha256(source_context).hexdigest().upper() != _hash(hit.get("sha256"), "source context hash")):
            raise SnapshotPlanError("source marker context is unavailable or changed")
        context_base = evidence._hex(hit["contextAddress"], "source context base")
        start = address - BEFORE
        end = start + CAPTURE_BYTES
        if start < context_base or end > context_base + len(source_context):
            raise SnapshotPlanError("source context does not cover the bounded target window")
        if start < previous_end:
            raise SnapshotPlanError("candidate snapshot ranges overlap")
        previous_end = end
        expected = source_context[start - context_base:end - context_base]
        ranges.append({
            "addressKind": "absolute-session-address",
            "address": f"0x{start:X}",
            "byteLength": CAPTURE_BYTES,
        })
        selections.append({
            "firstHealthHitSessionAddress": f"0x{address:X}",
            "rangeSessionAddress": f"0x{start:X}",
            "byteLength": CAPTURE_BYTES,
            "sourceWindowSha256": hashlib.sha256(expected).hexdigest().upper(),
            "markerPositions": [
                {"byteOffset": int(site["delta"]) + BEFORE, "tags": site["tags"]}
                for site in pattern["typedMarkerLayout"]
            ],
        })
    request = {
        "schemaVersion": 1,
        "evidenceKind": "native-memory-snapshot-request/1",
        "target": {
            "processId": current["processId"],
            "processStartUtcTicks": current["processStartUtcTicks"],
            "executableSha256": current["buildSha256"],
        },
        "maxDurationMilliseconds": 5_000,
        "ranges": ranges,
    }
    manifest = {
        "schemaVersion": 1,
        "evidenceKind": "native-health-targeted-snapshot-plan/1",
        "qualification": "candidate-only",
        "source": {
            "healthRunId": current["runId"],
            "healthReportSha256": current["sourceSha256"],
            "crossEpochReviewSha256": review_hash,
            "liveReceiptSha256": receipt_hash,
        },
        "target": request["target"],
        "typed": {
            "observer": observation.get("instanceId"),
            "generation": _int(typed.get("generation"), "typed.generation"),
            "selectedSequence": typed["selectedSequence"],
            "unitId": current_unit["unitId"],
            "receiptAgeSeconds": age,
            "currentValues": current_values,
            "sourceHealthValues": {
                "health": current["typedReference"]["health"][0],
                "healthMax": current["typedReference"]["healthMax"][0],
                "power": current["typedReference"]["rawPower"][0],
            },
        },
        "selectedPatternSha256": signature,
        "selectedCount": len(selections),
        "totalRequestedBytes": sum(x["byteLength"] for x in ranges),
        "selections": selections,
        "limitWarnings": [
            "Absolute session addresses are valid only for the exact PID/start/build in the request.",
            "A byte match is a cached/copy candidate, not proof of health or power field identity.",
            "Matching old source values is not evidence that the current bytes stayed unchanged.",
            "Any gameplay value or field meaning remains unqualified until changed-state evidence.",
            "Execute the existing snapshot-native command in the game guest; this host script does not read game memory.",
        ],
    }
    return request, manifest, receipt_raw


def _publish_atomic_new(files):
    """Publish multiple new files safely, rejecting any existing destination.

    The files must share one directory. Stage all data, hard-link each final
    name with no replace, and roll back only names created by this invocation.
    """
    parents = {Path(path).parent.resolve() for path, _ in files}
    if len(parents) != 1:
        raise SnapshotPlanError("all outputs must share an existing directory")
    if len(set(Path(path).name.lower() for path, _ in files)) != len(files):
        raise SnapshotPlanError("output paths must be distinct")
    for path, _ in files:
        if Path(path).exists():
            raise SnapshotPlanError(f"output already exists: {path}")
    staged = []
    published = []
    try:
        for destination, data in files:
            with tempfile.NamedTemporaryFile(
                dir=Path(destination).parent, prefix=".rr2-health-", suffix=".tmp",
                delete=False, mode="wb",
            ) as stream:
                stage = Path(stream.name)
                staged.append(stage)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(stage, destination)
            published.append(Path(destination))
    except BaseException:
        for final in published:
            final.unlink(missing_ok=True)
        raise
    finally:
        for temp in staged:
            temp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-report", type=Path, required=True)
    parser.add_argument("--cross-epoch-review", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--root-rva", default="0x32E0200")
    parser.add_argument("--level-hint", type=int, default=45)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--request-out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rva = evidence._hex(args.root_rva, "root-rva")
        request, manifest, receipt_bytes = prepare(
            args.health_report, args.cross_epoch_review, args.receipt,
            root_rva=rva, level_hint=args.level_hint,
            max_candidates=args.max_candidates,
        )
        files = [
            (args.request_out, (json.dumps(request, indent=2) + "\n").encode("utf-8")),
            (args.manifest_out, (json.dumps(manifest, indent=2) + "\n").encode("utf-8")),
            (args.receipt_out, receipt_bytes),
        ]
        _publish_atomic_new(files)
        print(json.dumps({
            "status": "prepared",
            "epochPid": request["target"]["processId"],
            "candidateGroups": manifest["selectedCount"],
            "requestedBytes": manifest["totalRequestedBytes"],
            "qualification": manifest["qualification"],
            "request": str(args.request_out),
            "manifest": str(args.manifest_out),
        }, separators=(",", ":")))
        return 0
    except (SnapshotPlanError, evidence.EvidenceError, OSError, ValueError,
            TypeError, KeyError, OverflowError) as error:
        print(f"Targeted health snapshot preparation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
