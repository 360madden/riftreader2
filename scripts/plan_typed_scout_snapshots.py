#!/usr/bin/env python3
"""Plan two bounded, exact-epoch snapshot requests from a pinned scout report.

Offline-only: does not contact VMware, launch RIFT, or read game memory. The
result is a *plan*, never proof of current process identity or live Lua data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

MAX_SCOUT_REPORT_BYTES = 1024 * 1024
PAGE_BYTES = 4096
BEFORE_PAGES = 2
AFTER_PAGES = 4
SNAPSHOT_BYTE_CAP = 64 * 1024 * 1024
SNAPSHOT_CHUNK_CAP = 16384
SNAPSHOT_RANGE_CAP = 256
USER_ADDRESS_END = 0x00007FFFFFFFFFFF
SHA_PATTERN = re.compile(r"[0-9A-F]{64}\Z")
ADDRESS_PATTERN = re.compile(r"0x(?:0|[1-9A-F][0-9A-F]*)\Z")


class PlanError(ValueError):
    """A source-evidence or bounded-request precondition failed."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise PlanError(f"Duplicate JSON field: {name}")
        result[name] = value
    return result


def _reject_constant(value: str) -> None:
    raise PlanError(f"Non-finite JSON constant: {value}")


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise PlanError(f"{label} must be an object")
    return value


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise PlanError(f"{label} must be a positive exact integer")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA_PATTERN.fullmatch(value) is None:
        raise PlanError(f"{label} must be 64 uppercase hexadecimal digits")
    return value


def _address(value: object, label: str) -> int:
    if not isinstance(value, str) or ADDRESS_PATTERN.fullmatch(value) is None:
        raise PlanError(f"{label} must be canonical uppercase 0x hexadecimal")
    number = int(value[2:], 16)
    if number < 0x10000 or number >= USER_ADDRESS_END:
        raise PlanError(f"{label} is outside supported user memory")
    return number


def _interval(value: object, label: str) -> tuple[int, int]:
    item = _object(value, label)
    start = _address(item.get("baseAddress"), f"{label}.baseAddress")
    length = _positive_int(item.get("byteLength"), f"{label}.byteLength")
    end = start + length
    if end > USER_ADDRESS_END:
        raise PlanError(f"{label} exceeds user memory")
    return start, end


def _bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
            + "\n").encode("utf-8")


def _hex(value: int) -> str:
    return f"0x{value:X}"


def build_plan(report_bytes: bytes, expected_sha256: str) -> tuple[dict, dict, bytes]:
    """Verify a pinned original scout and construct manifest, request, request bytes."""
    _sha(expected_sha256, "expected SHA-256")
    if not 0 < len(report_bytes) <= MAX_SCOUT_REPORT_BYTES:
        raise PlanError("Scout JSON must be 1 through 1048576 bytes")
    actual = hashlib.sha256(report_bytes).hexdigest().upper()
    if actual != expected_sha256:
        raise PlanError("Original scout report SHA-256 does not match its pin")
    try:
        report = _object(json.loads(report_bytes.decode("utf-8"),
                                    object_pairs_hook=_unique_object,
                                    parse_constant=_reject_constant), "scout report")
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PlanError(f"Invalid scout JSON: {error}") from error
    if report.get("schemaVersion") != 1 or report.get("evidenceKind") != "native-typed-prefix-scout/1":
        raise PlanError("Not a native-typed-prefix-scout/1 version 1 report")
    if report.get("marker") != "RRAPIVAL2|":
        raise PlanError("Not the exact typed marker")
    if report.get("scope") != "committed-readable-nonguard-MEM_PRIVATE-at-or-after-startAddress":
        raise PlanError("Scout scope is not the expected readable private memory")
    if report.get("status") not in ("complete", "partial"):
        raise PlanError("Scout result is not valid for candidate planning")
    if report.get("status") == "partial" and not isinstance(report.get("reason"), str):
        raise PlanError("Partial scan reason is missing")
    _sha(report.get("requestSha256"), "original request hash")
    _sha(report.get("coverageContentSha256"), "scout content hash")
    implementation = _object(report.get("implementation"), "implementation")
    _sha(implementation.get("bundleSha256"), "scanner executable hash")
    request = _object(report.get("request"), "scout request")
    if request.get("schemaVersion") != 1 or request.get("evidenceKind") != "native-typed-prefix-scout-request/1":
        raise PlanError("Embedded scout request has an unexpected schema")
    target = _object(request.get("target"), "original request target")
    identity = _object(report.get("identity"), "observed process identity")
    for field in ("processId", "processStartUtcTicks"):
        if _positive_int(target.get(field), f"target.{field}") != _positive_int(identity.get(field), f"identity.{field}"):
            raise PlanError(f"Scout request and observed identity disagree: {field}")
    if (_sha(target.get("executableSha256"), "target SHA") !=
            _sha(identity.get("executableSha256"), "identity SHA")):
        raise PlanError("Scout request and observed executable hashes differ")

    covered = report.get("coveredSpans")
    holes = report.get("holes")
    candidates = report.get("prefixAddresses")
    if not isinstance(covered, list) or not 1 <= len(covered) <= 32768:
        raise PlanError("Expected a bounded, nonempty covered-spans list")
    if not isinstance(holes, list) or len(holes) > 32768:
        raise PlanError("Expected a bounded holes list")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 128:
        raise PlanError("Expected 1–128 candidate prefix addresses")
    spans = sorted(_interval(item, f"coveredSpans[{index}]")
                   for index, item in enumerate(covered))
    for previous, following in zip(spans, spans[1:]):
        if previous[1] > following[0]:
            raise PlanError("Scout covered spans overlap")
    unreadable = [_interval(item, f"holes[{index}]") for index, item in enumerate(holes)]

    addresses = [_address(candidate, f"prefixAddresses[{index}]")
                 for index, candidate in enumerate(candidates)]
    if len(set(addresses)) != len(addresses):
        raise PlanError("Duplicate reported prefix address")
    windows = []
    for address in sorted(addresses):
        page = address // PAGE_BYTES * PAGE_BYTES
        start = page - BEFORE_PAGES * PAGE_BYTES
        end = page + (1 + AFTER_PAGES) * PAGE_BYTES
        if start < 0x10000 or end > USER_ADDRESS_END:
            raise PlanError("Snapshot window exceeds supported user memory")
        if not any(start >= low and end <= high for low, high in spans):
            raise PlanError(f"Prefix {_hex(address)} has no fully covered snapshot window")
        if any(start < high and low < end for low, high in unreadable):
            raise PlanError(f"Prefix {_hex(address)} overlaps an unreadable scout hole")
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))

    total_bytes = sum(end - start for start, end in windows)
    total_chunks = sum((end - start + PAGE_BYTES - 1) // PAGE_BYTES for start, end in windows)
    if (len(windows) > SNAPSHOT_RANGE_CAP or total_bytes > SNAPSHOT_BYTE_CAP
            or total_chunks > SNAPSHOT_CHUNK_CAP):
        raise PlanError("Selected ranges exceed snapshot-native hard limits")
    ranges = [{"addressKind": "absolute-session-address",
               "address": _hex(start), "byteLength": end - start}
              for start, end in windows]
    snapshot_request = {"schemaVersion": 1,
                        "evidenceKind": "native-memory-snapshot-request/1",
                        "target": {field: target[field] for field in
                                   ("processId", "processStartUtcTicks", "executableSha256")},
                        "maxDurationMilliseconds": 10000,
                        "ranges": ranges}
    request_bytes = _bytes(snapshot_request)
    request_hash = hashlib.sha256(request_bytes).hexdigest().upper()
    if len(request_bytes) > 65536:
        raise PlanError("Snapshot request exceeds 64 KiB JSON cap")
    manifest = {
        "schemaVersion": 1,
        "evidenceKind": "typed-scout-snapshot-followup-plan/1",
        "sourceScout": {
            "originalReportSha256": actual,
            "requestSha256": report["requestSha256"],
            "coverageContentSha256": report["coverageContentSha256"],
            "scannerBundleSha256": implementation["bundleSha256"],
            "scanStatus": report["status"],
            "scanReason": report.get("reason"),
            "sourceStartedAtUtc": report.get("startedAtUtc"),
            "sourceCompletedAtUtc": report.get("completedAtUtc"),
            "candidateAddresses": [_hex(address) for address in sorted(addresses)],
        },
        "exactProcessEpoch": snapshot_request["target"],
        "windowPolicy": {"pageBytes": PAGE_BYTES, "pagesBeforeMarker": BEFORE_PAGES,
                         "pagesAfterMarker": AFTER_PAGES,
                         "minimumTrailingBytesAtMarker": AFTER_PAGES * PAGE_BYTES},
        "snapshot": {"rangeCount": len(ranges), "totalRequestedBytes": total_bytes,
                     "chunkCount": total_chunks, "ranges": ranges},
        "independentSamples": [
            {"requestFile": f"sample-0{index}.request.json",
             "requestSha256": request_hash,
             "suggestedGuestReportFile": f"sample-0{index}.json"}
            for index in (1, 2)
        ],
        "limitations": [
            "This is an offline request plan, not a game-memory snapshot or verified frame.",
            "Do not reuse these absolute addresses if RIFT PID, exact start ticks, or executable SHA changes.",
            "Before acquisition, independently reverify VM and game epoch and acquire exclusive guest console via normal coordinator STOP/release.",
            "Run two time-separated no-overwrite guest captures and retain original bytes and hashes before strict inspect-typed-wire.",
            "A prefix or even a complete typed frame does not itself qualify native player XYZ.",
        ],
    }
    return manifest, snapshot_request, request_bytes


def publish_plan(directory: Path, manifest: dict, request_bytes: bytes) -> None:
    """Create only a new directory, then publish no-overwrite files in it."""
    directory.mkdir(parents=False, exist_ok=False)
    for filename, data in (
        ("sample-01.request.json", request_bytes),
        ("sample-02.request.json", request_bytes),
        ("plan.json", _bytes(manifest)),
    ):
        with (directory / filename).open("xb") as stream:
            stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scout-report", type=Path, required=True)
    parser.add_argument("--expected-scout-sha256", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and print the plan without writing any files")
    args = parser.parse_args(argv)
    try:
        with args.scout_report.open("rb") as stream:
            original = stream.read(MAX_SCOUT_REPORT_BYTES + 1)
        plan, _, request_bytes = build_plan(original, args.expected_scout_sha256)
        if not args.dry_run:
            publish_plan(args.output_directory, plan, request_bytes)
        print(json.dumps(plan, indent=2))
    except (PlanError, OSError, ValueError) as error:
        print(f"typed snapshot plan rejected: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
