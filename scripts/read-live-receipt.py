#!/usr/bin/env python3
"""Fail-closed snapshot gate for a nonce-bound RiftReader2 host receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import time

MAX_RECEIPT_BYTES = 128 * 1024 + 2048
MAX_RECEIPT_AGE_SECONDS = 2.0
CLOCK_SKEW_SECONDS = 0.250
NONCE = re.compile(r"^[0-9a-f]{32}$")


class GateError(ValueError):
    pass


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise GateError(f"duplicate JSON property: {key}")
        value[key] = item
    return value


def _reject_constant(value):
    raise GateError(f"non-finite JSON number: {value}")


def load_receipt(path: Path):
    with path.open("rb") as stream:
        data = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(data) > MAX_RECEIPT_BYTES or stream.read(1):
            raise GateError(f"receipt exceeds {MAX_RECEIPT_BYTES} bytes")
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError("receipt is not strict UTF-8 JSON") from error


def _object(value, name):
    if not isinstance(value, dict):
        raise GateError(f"{name} must be an object")
    return value


def _finite_number(value, name, minimum=0.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise GateError(f"{name} is outside its valid range")
    return number


def _utc(value, name):
    if not isinstance(value, str):
        raise GateError(f"{name} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GateError(f"{name} is invalid") from error
    if parsed.tzinfo is None:
        raise GateError(f"{name} must include an offset")
    return parsed.astimezone(timezone.utc)


def evaluate_receipt(
    receipt,
    expected_nonce: str,
    expected_receiver: str | None = None,
    *,
    now_monotonic_ns: int | None = None,
    now_utc: datetime | None = None,
):
    if not NONCE.fullmatch(expected_nonce):
        raise GateError("expected nonce must be 32 lowercase hexadecimal characters")
    receipt = _object(receipt, "receipt")
    if receipt.get("schemaVersion") != 1 or isinstance(receipt.get("schemaVersion"), bool):
        raise GateError("unsupported receipt schema")
    receiver = receipt.get("receiverInstance")
    if not isinstance(receiver, str) or not receiver:
        raise GateError("receiverInstance is missing")
    if expected_receiver is not None and receiver != expected_receiver:
        raise GateError("receiver instance mismatch")

    monotonic_now = time.monotonic_ns() if now_monotonic_ns is None else now_monotonic_ns
    received_ns = receipt.get("receivedMonotonicNs")
    if type(received_ns) is not int or received_ns <= 0:
        raise GateError("receivedMonotonicNs is invalid")
    receipt_age = (monotonic_now - received_ns) / 1_000_000_000
    if receipt_age < 0 or receipt_age > MAX_RECEIPT_AGE_SECONDS:
        raise GateError("outer receipt is stale or from a different host monotonic epoch")

    utc_now = (datetime.now(timezone.utc) if now_utc is None else now_utc).astimezone(timezone.utc)
    received_utc = _utc(receipt.get("receivedAtUtc"), "receivedAtUtc")
    host_utc_age = (utc_now - received_utc).total_seconds()
    if host_utc_age < -CLOCK_SKEW_SECONDS or abs(host_utc_age - receipt_age) > CLOCK_SKEW_SECONDS:
        raise GateError("host UTC and receipt monotonic ages are inconsistent")

    observation = _object(receipt.get("observation"), "observation")
    if observation.get("readerStatus") != "running":
        raise GateError("reader is not running")
    if observation.get("nonce") != expected_nonce:
        raise GateError("reader nonce mismatch")
    target = _object(observation.get("target"), "observation.target")
    if target.get("readerSessionNonce") != expected_nonce:
        raise GateError("target nonce mismatch")

    captured_utc = _utc(observation.get("capturedAtUtc"), "observation.capturedAtUtc")
    transport_age = (received_utc - captured_utc).total_seconds()
    if transport_age < -CLOCK_SKEW_SECONDS or transport_age > MAX_RECEIPT_AGE_SECONDS + CLOCK_SKEW_SECONDS:
        raise GateError("guest capture clock or delivery delay is outside the synchronized-clock bound")

    report = _object(observation.get("riftReader2"), "observation.riftReader2")
    if report.get("bindingStatus") != "bound" or report.get("freshnessStatus") != "fresh":
        raise GateError("inner observation is not bound and fresh")
    if report.get("selectionStatus") != "selected" or report.get("observation") is None:
        raise GateError("inner observation is not selected")
    scan = _object(report.get("scan"), "observation.riftReader2.scan")
    if scan.get("completed") is not True or scan.get("status") != "complete":
        raise GateError("memory scan is not complete")

    reported_age_ms = _finite_number(
        report.get("lastAdvanceAgeMilliseconds"), "lastAdvanceAgeMilliseconds"
    )
    timeout_ms = _finite_number(
        report.get("freshnessTimeoutMilliseconds"), "freshnessTimeoutMilliseconds", minimum=0.001
    )
    elapsed_since_capture = max(0.0, (utc_now - captured_utc).total_seconds())
    effective_age_ms = reported_age_ms + (elapsed_since_capture + CLOCK_SKEW_SECONDS) * 1000
    if effective_age_ms >= timeout_ms:
        raise GateError("inner last advance is expired under the synchronized-clock bound")

    return {
        "status": "fresh",
        "snapshotOnly": True,
        "gameReady": False,
        "expectedNonce": expected_nonce,
        "receiverInstance": receiver,
        "receiptAgeMilliseconds": receipt_age * 1000,
        "effectiveInnerAgeMilliseconds": effective_age_ms,
        "freshnessTimeoutMilliseconds": timeout_ms,
        "clockSkewBoundMilliseconds": CLOCK_SKEW_SECONDS * 1000,
        "assumption": (
            "Synchronized-clock assumption: guest and host UTC clocks differ by at most 250 ms; "
            "this is a snapshot-only "
            "conditional freshness result, not exact remote age or game-readiness proof."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--expected-nonce", required=True)
    parser.add_argument("--expected-receiver")
    args = parser.parse_args(argv)
    try:
        result = evaluate_receipt(
            load_receipt(args.receipt), args.expected_nonce, args.expected_receiver
        )
    except (GateError, OSError) as error:
        print(json.dumps({
            "status": "not-fresh",
            "snapshotOnly": True,
            "gameReady": False,
            "reason": str(error),
        }))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
