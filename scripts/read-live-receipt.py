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
SHA256 = re.compile(r"^[0-9A-Fa-f]{64}$")
FAST_PROVENANCE = "recent-full-scan-anchored-candidate-regions/1"
FAST_SCOPE = "candidate-regions"
FAST_MAX_ANCHOR_AGE_MILLISECONDS = 10_000
FAST_MAX_REGION_BYTES = 1024 * 1024 * 1024


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


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise GateError(f"{name} must be an integer at least {minimum}")
    return value


def _sha256(value, name):
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise GateError(f"{name} must be a SHA-256 hexadecimal string")
    return value.lower()


def _evaluate_outer(
    receipt,
    expected_nonce,
    expected_receiver,
    now_monotonic_ns,
    now_utc,
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
    return receipt, receiver, receipt_age, utc_now, captured_utc, observation


def evaluate_receipt(
    receipt,
    expected_nonce: str,
    expected_receiver: str | None = None,
    *,
    now_monotonic_ns: int | None = None,
    now_utc: datetime | None = None,
):
    receipt, receiver, receipt_age, utc_now, captured_utc, observation = _evaluate_outer(
        receipt, expected_nonce, expected_receiver, now_monotonic_ns, now_utc)

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


def evaluate_fast_observation(
    receipt,
    expected_nonce: str,
    expected_receiver: str | None = None,
    *,
    now_monotonic_ns: int | None = None,
    now_utc: datetime | None = None,
):
    """Gate the explicitly reduced movement scope without changing the full gate."""
    receipt, receiver, receipt_age, utc_now, captured_utc, observation = _evaluate_outer(
        receipt, expected_nonce, expected_receiver, now_monotonic_ns, now_utc)
    fast = _object(observation.get("fastObservation"), "observation.fastObservation")
    expected_fast = {
        "schemaVersion", "provenance", "bindingStatus", "freshnessStatus", "reason",
        "anchor", "selectionStatus", "envelopeSha256", "addonFrameSha256",
        "candidateSequence", "candidateEpoch", "observation", "scan",
        "publishedAtTimestamp", "lastAdvanceAtTimestamp",
        "lastAdvanceAgeMilliseconds", "freshnessTimeoutMilliseconds",
    }
    if set(fast) != expected_fast or fast.get("schemaVersion") != 1 \
            or fast.get("provenance") != FAST_PROVENANCE:
        raise GateError("fast observation contract is invalid")
    if fast.get("bindingStatus") != "bound-scoped" \
            or fast.get("freshnessStatus") != "fresh-scoped" \
            or fast.get("selectionStatus") != "selected-scoped" \
            or fast.get("reason") is not None:
        raise GateError("fast observation is not bound, fresh, and selected")

    anchor = _object(fast.get("anchor"), "observation.fastObservation.anchor")
    expected_anchor = {
        "fullScanStartedAtTimestamp", "fullScanCompletedAtTimestamp", "timestampFrequency",
        "envelopeSha256", "addonFrameSha256", "candidateSequence", "candidateEpoch",
        "candidateClock", "playerId", "regionCount", "totalRegionBytes", "maxAgeMilliseconds",
    }
    if set(anchor) != expected_anchor:
        raise GateError("fast observation anchor contract is invalid")
    started = _integer(anchor.get("fullScanStartedAtTimestamp"), "anchor full scan start", 1)
    anchored = _integer(anchor.get("fullScanCompletedAtTimestamp"), "anchor full scan completion", 1)
    frequency = _integer(anchor.get("timestampFrequency"), "anchor timestamp frequency", 1)
    if anchored < started:
        raise GateError("fast observation anchor interval is invalid")
    anchor_envelope = _sha256(anchor.get("envelopeSha256"), "anchor envelopeSha256")
    anchor_frame = _sha256(anchor.get("addonFrameSha256"), "anchor addonFrameSha256")
    anchor_sequence = _integer(anchor.get("candidateSequence"), "anchor candidate sequence", 0)
    anchor_epoch = _integer(anchor.get("candidateEpoch"), "anchor candidate epoch", 0)
    anchor_clock = _finite_number(anchor.get("candidateClock"), "anchor candidate clock")
    player_id = anchor.get("playerId")
    if not isinstance(player_id, str) or not player_id:
        raise GateError("anchor playerId is invalid")
    region_count = _integer(anchor.get("regionCount"), "anchor region count", 1)
    region_bytes = _integer(anchor.get("totalRegionBytes"), "anchor total region bytes", 1)
    if region_bytes > FAST_MAX_REGION_BYTES:
        raise GateError("fast observation anchor exceeds the region-byte bound")
    if anchor.get("maxAgeMilliseconds") != FAST_MAX_ANCHOR_AGE_MILLISECONDS:
        raise GateError("fast observation anchor age bound is invalid")

    scan = _object(fast.get("scan"), "observation.fastObservation.scan")
    expected_scan = {
        "scope", "status", "completed", "startedAtTimestamp", "completedAtTimestamp",
        "plannedBytes", "scannedBytes", "regionCount", "elapsedMilliseconds",
        "endpointCandidateCount", "malformedCandidateCount", "matchingCandidateCount",
        "identicalCopyCount", "reason",
    }
    if set(scan) != expected_scan or scan.get("scope") != FAST_SCOPE \
            or scan.get("status") != "complete" or scan.get("completed") is not True \
            or scan.get("reason") is not None:
        raise GateError("fast candidate-region scan is not complete")
    scan_started = _integer(scan.get("startedAtTimestamp"), "fast scan start", 1)
    scan_completed = _integer(scan.get("completedAtTimestamp"), "fast scan completion", 1)
    if not anchored <= scan_started <= scan_completed:
        raise GateError("fast scan interval predates its anchor")
    planned = _integer(scan.get("plannedBytes"), "fast scan planned bytes", 1)
    scanned = _integer(scan.get("scannedBytes"), "fast scan scanned bytes", 1)
    scan_regions = _integer(scan.get("regionCount"), "fast scan region count", 1)
    if planned != scanned or planned != region_bytes or scan_regions != region_count:
        raise GateError("fast scan does not completely cover its anchored scope")
    _finite_number(scan.get("elapsedMilliseconds"), "fast scan elapsedMilliseconds")
    for field in ("endpointCandidateCount", "malformedCandidateCount",
                  "matchingCandidateCount", "identicalCopyCount"):
        _integer(scan.get(field), f"fast scan {field}", 0)
    if scan.get("matchingCandidateCount") < 1 or scan.get("identicalCopyCount") < 1:
        raise GateError("fast scan did not select an exact candidate")

    selected = _object(fast.get("observation"), "observation.fastObservation.observation")
    if set(selected) != {"schemaVersion", "addonVersion", "sequence", "epoch", "clock",
            "player", "fields"} or selected.get("schemaVersion") != 1 \
            or not isinstance(selected.get("addonVersion"), str) \
            or not isinstance(selected.get("fields"), dict):
        raise GateError("fast selected observation contract is invalid")
    selected_sequence = _integer(selected.get("sequence"), "fast candidate sequence", 0)
    selected_epoch = _integer(selected.get("epoch"), "fast candidate epoch", 0)
    selected_clock = _object(selected.get("clock"), "fast candidate clock")
    selected_player = _object(selected.get("player"), "fast candidate player")
    if set(selected_clock) != {"status", "value"} or set(selected_player) != {"status", "value"}:
        raise GateError("fast selected producer identity contract is invalid")
    clock = _finite_number(selected_clock.get("value"), "fast candidate clock value")
    if selected_clock.get("status") != "ok" or selected_player.get("status") != "ok" \
            or selected_player.get("value") != player_id:
        raise GateError("fast candidate source identity is invalid")
    if selected_epoch != anchor_epoch or selected_sequence <= anchor_sequence or clock <= anchor_clock:
        raise GateError("fast candidate did not strictly advance from its full-scan anchor")
    if fast.get("candidateSequence") != selected_sequence or fast.get("candidateEpoch") != selected_epoch:
        raise GateError("fast candidate summary disagrees with its observation")
    if _sha256(fast.get("envelopeSha256"), "fast envelopeSha256") == anchor_envelope \
            or _sha256(fast.get("addonFrameSha256"), "fast addonFrameSha256") == anchor_frame:
        raise GateError("fast candidate hashes did not advance from their anchor")

    last_advance = _integer(
        fast.get("lastAdvanceAtTimestamp"), "fast last advance timestamp", 1)
    published = _integer(fast.get("publishedAtTimestamp"), "fast published timestamp", 1)
    reported_age_ms = _finite_number(
        fast.get("lastAdvanceAgeMilliseconds"), "fast last advance age")
    timeout_ms = _finite_number(
        fast.get("freshnessTimeoutMilliseconds"), "fast freshness timeout", minimum=0.001)
    if not scan_started <= last_advance <= scan_completed <= published:
        raise GateError("fast freshness timestamps are outside the scoped scan interval")
    timestamp_age_ms = (published - last_advance) * 1000 / frequency
    if not math.isclose(reported_age_ms, timestamp_age_ms, rel_tol=1e-9, abs_tol=0.001):
        raise GateError("fast reported age disagrees with its monotonic timestamps")
    elapsed_since_capture = max(0.0, (utc_now - captured_utc).total_seconds())
    effective_age_ms = reported_age_ms + (elapsed_since_capture + CLOCK_SKEW_SECONDS) * 1000
    if effective_age_ms >= timeout_ms:
        raise GateError("fast last advance is expired under the synchronized-clock bound")
    anchor_age_ms = (published - anchored) * 1000 / frequency \
        + (elapsed_since_capture + CLOCK_SKEW_SECONDS) * 1000
    if not 0 <= anchor_age_ms <= FAST_MAX_ANCHOR_AGE_MILLISECONDS:
        raise GateError("fast observation anchor is expired")

    return {
        "status": "fresh-scoped",
        "scope": FAST_SCOPE,
        "provenance": FAST_PROVENANCE,
        "snapshotOnly": True,
        "gameReady": False,
        "expectedNonce": expected_nonce,
        "receiverInstance": receiver,
        "receiptAgeMilliseconds": receipt_age * 1000,
        "anchorAgeMilliseconds": anchor_age_ms,
        "anchorMaxAgeMilliseconds": FAST_MAX_ANCHOR_AGE_MILLISECONDS,
        "effectiveInnerAgeMilliseconds": effective_age_ms,
        "freshnessTimeoutMilliseconds": timeout_ms,
        "assumption": "Movement-only candidate-region receipt anchored to a recent exact full scan.",
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
