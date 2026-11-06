"""Assess a type-checked native Mana sample bracketed by two API frames.

All inputs are retained JSON. The operation is offline and no-overwrite. A
matching stable baseline is useful correlation evidence, not changed-state,
freshness, continuity, or restart qualification.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import struct
from pathlib import Path
import sys

from scripts.native_mana_candidate import BUILD_SHA, calculate_mana_candidate
from scripts.inspect_typed_resource import require_reference_binding, require_session_id


DESCRIPTOR_PROBE_PATH = Path(__file__).with_name("probe_native_mana_descriptor.py")


class ManaAssessmentError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManaAssessmentError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _load(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ManaAssessmentError(f"{path}:invalid-json") from exc
    if not isinstance(value, dict):
        raise ManaAssessmentError(f"{path}:object-required")
    return value, hashlib.sha256(raw).hexdigest().upper()


def _utc(value, label: str) -> datetime:
    if not isinstance(value, str):
        raise ManaAssessmentError(f"{label}:utc-required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManaAssessmentError(f"{label}:utc-invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ManaAssessmentError(f"{label}:utc-required")
    return parsed


def _identity(value, label: str) -> tuple:
    if not isinstance(value, dict):
        raise ManaAssessmentError(f"{label}:identity-required")
    keys = ("processId", "processStartUtcTicks", "executableSha256",
            "moduleBaseAddress", "moduleSize")
    try:
        result = tuple(value[key] for key in keys)
    except KeyError as exc:
        raise ManaAssessmentError(f"{label}:identity-incomplete") from exc
    if result[2] != BUILD_SHA:
        raise ManaAssessmentError(f"{label}:unsupported-build")
    if (isinstance(result[0], bool) or not isinstance(result[0], int) or result[0] <= 0
            or isinstance(result[1], bool) or not isinstance(result[1], int) or result[1] <= 0
            or isinstance(result[3], bool) or not isinstance(result[3], int) or result[3] <= 0
            or isinstance(result[4], bool) or not isinstance(result[4], int) or result[4] <= 0):
        raise ManaAssessmentError(f"{label}:identity-invalid")
    return result


def _sha(value, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789ABCDEF" for c in value)):
        raise ManaAssessmentError(f"{label}:sha256-invalid")
    return value


def _owner_tool_signature(value: dict, label: str) -> tuple:
    vm = value.get("vmIdentity")
    if not isinstance(vm, dict) or not vm:
        raise ManaAssessmentError(f"{label}:vm-identity-required")
    try:
        vm_signature = json.dumps(vm, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ManaAssessmentError(f"{label}:vm-identity-invalid") from exc
    return (
        vm_signature,
        _sha(value.get("readerSha256"), label + ":reader"),
        _sha(value.get("workflowSha256"), label + ":workflow"),
        _sha(value.get("probeSha256"), label + ":probe"),
    )


def _owner_resource_signature(value: dict, label: str) -> tuple:
    resource = value.get("resourceRecordCandidate")
    fields = resource.get("fields") if isinstance(resource, dict) else None
    if (not isinstance(resource, dict) or resource.get("kind") != 3
            or resource.get("name") != "mana" or resource.get("inputsStable") is not True
            or not isinstance(fields, dict)
            or fields.get("expectedNativeResolverTypeUnverified") != "0x072A"):
        raise ManaAssessmentError(label + ":mana-owner-route-invalid")
    addresses = []
    for name in ("resourceWrapper", "referenceSlot", "record"):
        address = resource.get(name)
        if (not isinstance(address, str) or not address.startswith("0x")
                or len(address) <= 2 or any(c not in "0123456789ABCDEF" for c in address[2:])):
            raise ManaAssessmentError(label + ":mana-owner-address-invalid")
        addresses.append(address)
    return (*addresses, resource.get("recordVtableRva"),
            resource.get("candidateDescriptorGetterRva"))


def _descriptor_owner_reviews(descriptor: dict) -> tuple[dict, dict, str, str]:
    reviews = []
    hashes = []
    for prefix in ("before", "after"):
        location = descriptor.get(prefix + "OwnerEvidence")
        expected = _sha(descriptor.get(prefix + "OwnerReviewSha256"),
                        "descriptor:" + prefix + "-owner-review")
        if not isinstance(location, str):
            raise ManaAssessmentError("descriptor:" + prefix + "-owner-evidence-path-required")
        folder = Path(location)
        review_path = folder / "review.json"
        if not folder.is_dir() or folder.is_symlink() or not review_path.is_file() or review_path.is_symlink():
            raise ManaAssessmentError("descriptor:" + prefix + "-owner-evidence-invalid")
        review, actual = _load(review_path)
        if actual != expected:
            raise ManaAssessmentError("descriptor:" + prefix + "-owner-review-sha256-mismatch")
        reviews.append(review)
        hashes.append(actual)
    return reviews[0], reviews[1], hashes[0], hashes[1]


def _i32(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not -(1 << 31) <= value < (1 << 31):
        raise ManaAssessmentError(label + ":int32-required")
    return value


def _finite(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ManaAssessmentError(label + ":finite-number-required")
    try:
        result = struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise ManaAssessmentError(label + ":float32-required") from exc
    if not math.isfinite(result):
        raise ManaAssessmentError(label + ":float32-required")
    return value


def _api(value: dict, label: str) -> tuple:
    if (value.get("schemaVersion") != 1
            or value.get("evidenceKind") != "typed-resource-snapshot-inspection/1"
            or value.get("status") != "available"):
        raise ManaAssessmentError(f"{label}:api-report-not-available")
    selected = value.get("selected")
    if not isinstance(selected, dict) or selected.get("resource") != "mana":
        raise ManaAssessmentError(f"{label}:mana-selection-required")
    current, maximum = selected.get("current"), selected.get("maximum")
    if (not isinstance(current, dict) or current.get("status") != "ok"
            or not isinstance(maximum, dict) or maximum.get("status") != "ok"):
        raise ManaAssessmentError(f"{label}:mana-values-required")
    current_value, maximum_value = current.get("value"), maximum.get("value")
    if (isinstance(current_value, bool) or not isinstance(current_value, (int, float))
            or not math.isfinite(current_value)
            or isinstance(maximum_value, bool) or not isinstance(maximum_value, (int, float))
            or not math.isfinite(maximum_value)):
        raise ManaAssessmentError(f"{label}:numeric-mana-required")
    player = selected.get("playerUnitId")
    if not isinstance(player, str) or not player.startswith("u"):
        raise ManaAssessmentError(f"{label}:player-required")
    sequence, frame_time = selected.get("sequence"), selected.get("frameTime")
    if (isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0
            or isinstance(frame_time, bool) or not isinstance(frame_time, (int, float))
            or not math.isfinite(frame_time)):
        raise ManaAssessmentError(f"{label}:source-sequence-or-clock-invalid")
    snapshot_sha = _sha(value.get("snapshotSha256"), label + ":snapshot")
    wire_sha = _sha(selected.get("wireSha256"), label + ":wire")
    started = _utc(value.get("startedAtUtc"), label + ":started")
    completed = _utc(value.get("completedAtUtc"), label + ":completed")
    if completed < started:
        raise ManaAssessmentError(f"{label}:snapshot-time-order-invalid")
    return (_identity(value.get("identity"), label), player, current_value, maximum_value,
            sequence, frame_time, snapshot_sha, wire_sha, started, completed)


def assess(api_before_path: Path, native_path: Path, descriptor_path: Path,
           api_after_path: Path, maximum_gap_seconds: float, session_id: str | None = None) -> dict:
    if not 0 < maximum_gap_seconds <= 300:
        raise ManaAssessmentError("maximum-gap-seconds-out-of-range")
    before, before_sha = _load(api_before_path)
    native, native_sha = _load(native_path)
    descriptor, descriptor_sha = _load(descriptor_path)
    after, after_sha = _load(api_after_path)
    if session_id is not None:
        require_session_id(session_id)
        for value in (before, after):
            require_reference_binding(value.get("selected"), session_id)
        if before["selected"]["epoch"] != after["selected"]["epoch"]:
            raise ManaAssessmentError("api-reference-epoch-changed")
    (before_id, before_player, before_current, before_max, before_sequence,
     before_frame, before_snapshot_sha, before_wire_sha, _, before_end) = _api(before, "before")
    (after_id, after_player, after_current, after_max, after_sequence,
     after_frame, after_snapshot_sha, after_wire_sha, after_start, _) = _api(after, "after")
    if before_id != after_id or before_player != after_player:
        raise ManaAssessmentError("api-identity-or-player-changed")
    if after_sequence <= before_sequence or after_frame <= before_frame:
        raise ManaAssessmentError("api-source-sequence-or-clock-not-advanced")
    if (native.get("schemaVersion") != 1 or native.get("status") != "complete"
            or native.get("sourceStableAtPublish") is not True):
        raise ManaAssessmentError("native-owner-review-incomplete")
    native_id = _identity(native.get("identity"), "native")
    native_player = native.get("nativePlayerUnitId")
    if native_id != before_id or native_player != before_player:
        raise ManaAssessmentError("native-identity-or-player-mismatch")
    resource = native.get("resourceRecordCandidate")
    if (not isinstance(resource, dict) or resource.get("kind") != 3
            or resource.get("name") != "mana" or resource.get("inputsStable") is not True):
        raise ManaAssessmentError("native-mana-record-invalid")
    fields = resource.get("fields")
    if not isinstance(fields, dict):
        raise ManaAssessmentError("native-mana-fields-missing")
    interval = resource.get("observationIntervalUtc")
    if not isinstance(interval, dict) or set(interval) != {"startedAtUtc", "completedAtUtc"}:
        raise ManaAssessmentError("native:observation-interval-required")
    native_start = _utc(interval.get("startedAtUtc"), "native:started")
    native_complete = _utc(interval.get("completedAtUtc"), "native:completed")
    if native_complete < native_start:
        raise ManaAssessmentError("native:observation-interval-invalid")
    if not before_end <= native_start <= native_complete <= after_start:
        raise ManaAssessmentError("native-observation-not-api-bracketed")
    before_gap = (native_start - before_end).total_seconds()
    after_gap = (after_start - native_complete).total_seconds()
    if before_gap > maximum_gap_seconds or after_gap > maximum_gap_seconds:
        raise ManaAssessmentError("native-api-gap-exceeds-limit")

    if (descriptor.get("schemaVersion") != 1
            or descriptor.get("status") != "type-checked-record-candidate"
            or _identity(descriptor.get("identity"), "descriptor") != native_id
            or descriptor.get("nativePlayerUnitId") != native_player):
        raise ManaAssessmentError("descriptor-identity-or-status-invalid")
    current_descriptor_probe_sha = hashlib.sha256(
        DESCRIPTOR_PROBE_PATH.read_bytes()).hexdigest().upper()
    if (_sha(descriptor.get("probeSha256"), "descriptor:probe") !=
            current_descriptor_probe_sha):
        raise ManaAssessmentError("descriptor-producer-source-sha256-mismatch")
    fingerprint = descriptor.get("fingerprint")
    if (not isinstance(fingerprint, dict) or fingerprint.get("typeCode") != "0x072A"
            or fingerprint.get("recordVtableRva") != resource.get("recordVtableRva")
            or fingerprint.get("descriptorGetterRva") != resource.get("candidateDescriptorGetterRva")):
        raise ManaAssessmentError("descriptor-fingerprint-does-not-cover-record-type")
    descriptor_before, descriptor_after, descriptor_before_sha, descriptor_after_sha = (
        _descriptor_owner_reviews(descriptor))
    native_tools = _owner_tool_signature(native, "native")
    native_owner_route = _owner_resource_signature(native, "native")
    expected_probe_sha = _sha(descriptor.get("ownerProbeSha256"), "descriptor:owner-probe")
    expected_reader_sha = _sha(descriptor.get("readerSha256"), "descriptor:reader")
    expected_workflow_sha = _sha(descriptor.get("workflowSha256"), "descriptor:workflow")
    for label, owner in (("descriptor-before-owner", descriptor_before),
                         ("descriptor-after-owner", descriptor_after)):
        if (owner.get("status") != "complete" or owner.get("sourceStableAtPublish") is not True
                or _identity(owner.get("identity"), label) != native_id
                or owner.get("nativePlayerUnitId") != native_player):
            raise ManaAssessmentError(label + ":identity-or-status-invalid")
        tools = _owner_tool_signature(owner, label)
        if tools != native_tools:
            raise ManaAssessmentError(label + ":vm-or-tool-identity-mismatch")
        if tools[1:] != (expected_reader_sha, expected_workflow_sha, expected_probe_sha):
            raise ManaAssessmentError(label + ":descriptor-tool-pins-mismatch")
        if _owner_resource_signature(owner, label) != native_owner_route:
            raise ManaAssessmentError(label + ":descriptor-owner-route-mismatch")

    rate = _i32(fields.get("rateRaw"), "native:rate")
    base = _i32(fields.get("baseRaw"), "native:base")
    revision = _i32(fields.get("recordRevision"), "native:record-revision")
    maximum = _i32(fields.get("maximumRaw"), "native:maximum")
    wrapper_revision = _i32(fields.get("wrapperRevision"), "native:wrapper-revision")
    wrapper_clock = _finite(fields.get("wrapperClock"), "native:wrapper-clock")
    game_clock = _finite(resource.get("gameClock"), "native:game-clock")
    record = bytearray(64)
    wrapper = bytearray(48)
    struct.pack_into("<i", record, 0x18, rate)
    struct.pack_into("<i", record, 0x1C, base)
    struct.pack_into("<i", record, 0x20, revision)
    struct.pack_into("<i", record, 0x24, maximum)
    struct.pack_into("<i", wrapper, 0x1C, wrapper_revision)
    struct.pack_into("<f", wrapper, 0x24, wrapper_clock)
    candidate = calculate_mana_candidate(
        bytes(record), bytes(wrapper), game_clock, build_sha=BUILD_SHA,
        resource_kind=3, verified_type_code=0x072A)
    if candidate.get("status") != "calculated-candidate":
        raise ManaAssessmentError("native-mana-calculation-unavailable:" + str(candidate.get("reason")))
    values_match = (before_current == candidate["current"] == after_current
                    and before_max == candidate["maximum"] == after_max)
    return {
        "schemaVersion": 1,
        "evidenceKind": "mana-short-window-assessment/1",
        "status": "stable-baseline-agreement" if values_match else "values-disagree",
        "identity": native.get("identity"),
        "playerUnitId": native_player,
        "window": {
            "maximumGapSeconds": maximum_gap_seconds,
            "beforeSnapshotCompletionToNativeStartSeconds": before_gap,
            "nativeStartedAtUtc": interval["startedAtUtc"],
            "nativeCompletedAtUtc": interval["completedAtUtc"],
            "nativeCompletionToAfterSnapshotStartSeconds": after_gap,
            "timestampSemantics": "host snapshot acquisition timestamps; no direct synchronization with Inspect.Time.Frame",
        },
        "apiAdvance": {
            "sequenceBefore": before_sequence,
            "sequenceAfter": after_sequence,
            "sequenceDelta": after_sequence - before_sequence,
            "frameTimeBefore": before_frame,
            "frameTimeAfter": after_frame,
            "frameTimeDelta": after_frame - before_frame,
        },
        "values": {
            "apiBefore": {"current": before_current, "maximum": before_max},
            "native": {"current": candidate["current"], "maximum": candidate["maximum"]},
            "apiAfter": {"current": after_current, "maximum": after_max},
        },
        "sources": {
            "apiBeforeReportSha256": before_sha,
            "apiBeforeSnapshotSha256": before_snapshot_sha,
            "apiBeforeWireSha256": before_wire_sha,
            "nativeReviewSha256": native_sha,
            "descriptorReviewSha256": descriptor_sha,
            "descriptorBeforeOwnerReviewSha256": descriptor_before_sha,
            "descriptorAfterOwnerReviewSha256": descriptor_after_sha,
            "apiAfterReportSha256": after_sha,
            "apiAfterSnapshotSha256": after_snapshot_sha,
            "apiAfterWireSha256": after_wire_sha,
        },
        "qualification": "advancing API source and stable baseline only; source clock is not directly synchronized to host/native timestamps; changed-state/freshness/continuity/restart-unverified",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-before", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--api-after", required=True, type=Path)
    parser.add_argument("--maximum-gap-seconds", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--session-id")
    args = parser.parse_args(argv)
    try:
        result = assess(args.api_before, args.native, args.descriptor, args.api_after,
                        args.maximum_gap_seconds, args.session_id)
        args.output.open("x", encoding="utf-8", newline="\n").write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (OSError, ManaAssessmentError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
