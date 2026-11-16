"""Offline, hash-pinned audit of a RiftWorld fixed-source anchor against one RR2 screenshot.

A matching RIFT build is not a matching process epoch or active Havok world.
This audit never qualifies a screenshot mesh frame, visible depth or movement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from scripts import physical_pixel_surface as surface

SCHEMA = "rr2.retained-pixel-source-anchor-audit/1"
JOIN_SCHEMA = "riftworld.p0-same-world-source-anchor-bracket/1"
RACK_SCHEMA = "riftworld.p0-live-mopp-calibration/1"
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _pinned_json(path, sha256, label):
    _require(isinstance(sha256, str)
             and surface._HEX_SHA.fullmatch(sha256) is not None,
             label + "-sha256-pin-required")
    path, raw, digest = surface._source_bytes(path, MAX_REPORT_BYTES, label)
    _require(digest.lower() == sha256.lower(), label + "-sha256-mismatch")
    value = surface._strict_json(raw)
    _require(type(value) is dict, label + "-must-be-object")
    return value, {"path": str(path), "sha256": digest}


def _utc(value, label):
    _require(isinstance(value, str), label + "-utc-invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(label + "-utc-invalid") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             label + "-utc-missing-zone")
    return parsed.astimezone(timezone.utc)


def _validated_anchor(join, rack, rack_sha):
    _require(join.get("schema") == JOIN_SCHEMA
             and join.get("status") == "same-havok-world-source-anchor-consistent",
             "source-anchor-join-contract-invalid")
    _require(rack.get("schema") == RACK_SCHEMA and rack.get("status") == "complete",
             "source-anchor-rack-contract-invalid")
    report_rows = join.get("inputReports")
    _require(isinstance(report_rows, list) and len(report_rows) == 3
             and sum(type(row) is dict and row.get("sha256") == rack_sha
                     for row in report_rows) == 1,
             "source-anchor-rack-not-pinned-by-join")
    for key, expected in (
        ("sameProcessEpochReaderPlayerAndHavokWorld", True),
        ("sourceNativeRackPoseMatchedWithinBracket", True),
        ("capturesSimultaneous", False),
        ("passivePlayerPositionFreshnessQualified", False),
        ("watchSourceFrameQualified", False),
        ("watchLocalityQualified", False),
        ("watchNativePadPresentQualified", False),
        ("contactOrBlockingQualified", False),
        ("watchScanAuthorized", False),
        ("navigationAdmissionQualified", False),
    ):
        _require(join.get(key) is expected, "source-anchor-join-flag-invalid:" + key)
    _require(rack.get("navigationQualified") is False
             and rack.get("nativeContactOrBlocking") == "unknown",
             "source-anchor-rack-admission-inconsistent")
    native_identity = rack.get("identity")
    owner, instance, source = (rack.get(k) for k in
                               ("ownerChain", "instance", "sourceJoin"))
    _require(all(type(obj) is dict for obj in
                 (native_identity, owner, instance, source)),
             "source-anchor-rack-identity-or-pose-missing")
    for key in ("processId", "processStartUtcTicks"):
        _require(type(join.get(key)) is int
                 and join[key] == native_identity.get(key),
                 "source-anchor-process-identity-inconsistent:" + key)
    _require(isinstance(join.get("ownedHavokWorld"), str)
             and join["ownedHavokWorld"].startswith("0x")
             and join["ownedHavokWorld"] == owner.get("worldAddress"),
             "source-anchor-havok-world-inconsistent")
    for key, other in (
        ("rackSourcePlacement", "sourcePlacement"),
        ("rackSourceHkxSha256", "sourceHkxSha256"),
        ("sourceMoppCodeSha256", "sourceMoppCodeSha256"),
    ):
        _require(isinstance(join.get(key), str)
                 and join[key] == source.get(other),
                 "source-anchor-rack-source-inconsistent:" + key)
    _require(source.get("status")
             == "source-MOPP-pose-and-complete-code-matched-with-sibling-box-control"
             and source.get("observedContact") is False
             and source.get("observedBlocking") is False
             and instance.get("codeReadCoverage") == "complete"
             and instance.get("completeCodeSha256") == join["sourceMoppCodeSha256"],
             "source-anchor-rack-native-control-unqualified")
    pose = instance.get("bodyWorldPose3x4")
    _require(isinstance(pose, list) and len(pose) == 3
             and all(isinstance(row, list) and len(row) == 4 for row in pose),
             "source-anchor-native-pose-missing")
    source_xyz = surface._xyz(join.get("sourceRackTranslationXYZ"), "source-anchor-source")
    observed_xyz = surface._xyz(join.get("nativeRackTranslationXYZ"), "source-anchor-native")
    body_xyz = surface._xyz([row[3] for row in pose], "source-anchor-body")
    _require(max(abs(a - b) for a, b in zip(observed_xyz, body_xyz)) <= 1e-6,
             "source-anchor-native-body-translation-inconsistent")
    translation = join.get("sourceToNativeRackMaxTranslationError")
    basis = join.get("sourceToNativeRackMaxBasisError")
    _require(type(translation) in (int, float) and 0 <= translation <= .002
             and type(basis) in (int, float) and 0 <= basis <= .00002
             and abs(max(abs(a-b) for a, b in zip(source_xyz, observed_xyz))
                     - translation) <= 1e-7,
             "source-anchor-native-source-residual-inconsistent")
    interval = join.get("bracketWindowUtc")
    _require(isinstance(interval, list) and len(interval) == 2,
             "source-anchor-bracket-missing")
    begin, end = (_utc(value, "source-anchor-bracket") for value in interval)
    elapsed = (end - begin).total_seconds()
    recorded = join.get("totalBracketSeconds")
    _require(0 < elapsed <= 120 and type(recorded) in (int, float)
             and abs(elapsed - recorded) <= .005,
             "source-anchor-bracket-duration-inconsistent")
    _require(isinstance(native_identity.get("executableSha256"), str)
             and surface._HEX_SHA.fullmatch(native_identity["executableSha256"])
             and isinstance(native_identity.get("executablePath"), str)
             and bool(native_identity["executablePath"]),
             "source-anchor-native-build-missing")
    return native_identity, begin, end


def audit(retained_ray, join_path, join_sha256, rack_path, rack_sha256):
    """Compare exact screenshot identity/UTC to a separately verified source/rack join.

    Even all identity/time predicates passing cannot establish screenshot-world
    membership, terrain mesh registration, rendered depth or contact.
    """
    identity = retained_ray.get("identity")
    _require(type(identity) is dict and type(identity.get("processId")) is int
             and type(identity.get("processStartUtcTicks")) is int,
             "retained-ray-process-identity-missing")
    capture_utc = _utc(retained_ray.get("capturedAtUtc"), "retained-ray")
    join, join_ref = _pinned_json(join_path, join_sha256, "source-anchor-join")
    rack, rack_ref = _pinned_json(rack_path, rack_sha256, "source-anchor-rack")
    native_identity, begin, end = _validated_anchor(join, rack, rack_ref["sha256"])
    epoch_match = (identity["processId"] == native_identity["processId"]
                   and identity["processStartUtcTicks"]
                       == native_identity["processStartUtcTicks"])
    build_match = (identity.get("executableSha256", "").lower()
                   == native_identity["executableSha256"].lower()
                   and identity.get("executablePath") == native_identity["executablePath"]
                   and identity.get("moduleSize") == native_identity.get("moduleSize"))
    module_mapping_match = (type(identity.get("moduleBaseAddress")) is int
                            and type(native_identity.get("moduleBaseAddress")) is int
                            and identity["moduleBaseAddress"]
                                == native_identity["moduleBaseAddress"])
    time_match = begin <= capture_utc <= end
    blockers = []
    if not epoch_match:
        blockers.append("screenshot-process-epoch-differs-from-rack-anchor")
    if not build_match:
        blockers.append("screenshot-executable-build-differs-from-rack-anchor")
    if not time_match:
        blockers.append("screenshot-outside-rack-owner-bracket")
    if not module_mapping_match:
        blockers.append("screenshot-module-mapping-differs-from-rack-anchor")
    blockers.extend((
        "screenshot-has-no-independent-owned-havok-world-identity",
        "one-rack-anchor-does-not-register-the-entire-screenshot-obj",
        "no-independent-visible-depth-or-occlusion-witness",
    ))
    return {
        "schema": SCHEMA,
        "status": ("candidate-context-only" if epoch_match and build_match
                   and module_mapping_match and time_match else "blocked"),
        "source": {"join": join_ref, "rack": rack_ref},
        "screenshot": {"processId": identity["processId"],
                       "processStartUtcTicks": identity["processStartUtcTicks"],
                       "capturedAtUtc": capture_utc.isoformat()},
        "anchor": {"processId": native_identity["processId"],
                   "processStartUtcTicks": native_identity["processStartUtcTicks"],
                   "ownedHavokWorld": join["ownedHavokWorld"],
                   "rackSourcePlacement": join["rackSourcePlacement"],
                   "sourceToNativeRackMaxTranslationError":
                       join["sourceToNativeRackMaxTranslationError"],
                   "sourceToNativeRackMaxBasisError":
                       join["sourceToNativeRackMaxBasisError"]},
        "processEpochMatches": epoch_match,
        "executableBuildMatches": build_match,
        "moduleMappingMatches": module_mapping_match,
        "captureInsideAnchorBracket": time_match,
        "screenshotWorldMembershipProven": False,
        "sourceMeshFrameQualified": False,
        "visibleSurfaceDepthQualified": False,
        "occlusionQualified": False,
        "movementEligible": False,
        "inputSent": False,
        "blockers": blockers,
    }
