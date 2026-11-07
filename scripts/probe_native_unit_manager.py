"""Read-only, exact-build native player-to-component probe for either lab.

Uses the existing native reader and VM credential/identity workflow. No game
input, addon call, service startup, injection, or process write. Cached XYZ is
reported as a candidate, not qualified passive-fresh/restart-safe telemetry.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import struct
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BUILD_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
MANAGER_RVA = 0x33624A8
PLAYER_SYSTEM_RVA = 0x33623E0
POSITION_INDEX_RVA = 0x2F588A0
HEALTH_INDEX_RVA = 0x2F57850
MAX_USER = 0x7FFFFFFFFFFF


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def encoded(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def pointer(value: int, length: int = 8) -> int:
    if type(value) is not int or value < 0x10000 or value + length - 1 > MAX_USER:
        raise ValueError("invalid-user-pointer")
    if value % 8:
        raise ValueError("unaligned-pointer")
    return value


def signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def entity_hash(key: int) -> int:
    """Exact Windows ldiv/IMUL/SUB/CMOVNS pipeline at current RVA 0x58C990."""
    seed = signed32(key)
    quotient = abs(seed) // 127773
    if seed < 0:
        quotient = -quotient
    remainder = seed - quotient * 127773
    value = signed32(signed32(remainder * 16807) - signed32(quotient * 2836))
    return (value if value >= 0 else value + 2147483647) & 0xFFFFFFFF


def find_entity(header: bytes, key: int, read, *, max_nodes: int = 8) -> dict:
    """Read only the computed bucket and bounded collision chain; no scan."""
    if len(header) != 24 or type(key) is not int or not 0 < key <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("invalid-table-header-or-player-key")
    if not 1 <= max_nodes <= 64:
        raise ValueError("invalid-node-budget")
    buckets, stride, count = struct.unpack("<QQQ", header)
    if not 24 <= stride <= 4096 or stride % 8 or not 1 <= count <= 1 << 24:
        raise ValueError("invalid-table-shape")
    pointer(buckets)
    index = entity_hash(key) % count
    bucket = pointer(buckets + index * stride, 24)
    seen = set()
    path = []
    current = bucket
    for ordinal in range(max_nodes):
        if current in seen:
            raise ValueError("lookup-pointer-cycle")
        seen.add(current)
        raw = read(current, 24)
        if len(raw) != 24:
            raise ValueError("lookup-read-hole")
        path.append({"address": current, "bytes": raw.hex()})
        link, stored_key, entity = struct.unpack("<QQQ", raw)
        if (ordinal != 0 or not link & 1) and stored_key == key:
            return {"bucket": bucket, "bucketIndex": index, "node": current,
                    "entity": pointer(entity, 128), "visitedNodes": len(seen),
                    "nodeBytes": raw.hex(), "bucketCount": count, "stride": stride, "path": path}
        current = link & ~1
        if not current:
            raise ValueError("player-key-not-found")
        pointer(current, 24)
    raise ValueError("lookup-node-budget-exceeded")


def inspection_identity(report: dict) -> tuple[dict, dict]:
    if report.get("schemaVersion") != 1 or report.get("contractVersion") != "native-target-inspection/1":
        raise ValueError("invalid-inspection-kind")
    identity = dict(report["target"])
    target = report["suggestedRequest"]["target"]
    if (identity["executableSha256"] != BUILD_SHA or
            any(identity[k] != target[k] for k in ("processId", "processStartUtcTicks", "executableSha256")) or
            type(target["processId"]) is not int or target["processId"] <= 0 or
            type(target["processStartUtcTicks"]) is not int or target["processStartUtcTicks"] <= 0):
        raise ValueError("wrong-build-or-process-identity")
    identity["moduleBaseAddress"] = int(identity["moduleBaseAddress"], 16)
    pointer(identity["moduleBaseAddress"], identity["moduleSize"])
    return identity, dict(target)


def snapshot_bytes(report: dict, request: dict, identity: dict) -> dict[int, bytes]:
    if (report.get("schemaVersion") != 1 or report.get("evidenceKind") != "native-memory-snapshot/1"
            or report.get("status") != "complete" or report.get("identity") != identity):
        raise ValueError("snapshot-incomplete-or-identity-mismatch")
    if report["source"]["requestSha256"] != sha(encoded(request)):
        raise ValueError("snapshot-request-hash-mismatch")
    expected = {}
    for region in request["ranges"]:
        address = int(region["address"], 16)
        if region["addressKind"] == "module-relative-rva":
            address += identity["moduleBaseAddress"]
        length = region["byteLength"]
        if not 1 <= length <= 4096 or address in expected:
            raise ValueError("unsupported-probe-range")
        expected[address] = length
    chunks = {}
    for chunk in report["chunks"]:
        address = int(chunk["address"], 16)
        length = expected.get(address)
        if (address in chunks or length is None or chunk["status"] != "success" or
                chunk["requestedByteLength"] != length or chunk["bytesRead"] != length):
            raise ValueError("snapshot-chunk-hole-or-shape")
        raw = base64.b64decode(chunk["bytesBase64"], validate=True)
        if len(raw) != length or sha(raw) != chunk["bytesSha256"]:
            raise ValueError("snapshot-chunk-hash-mismatch")
        chunks[address] = raw
    if set(chunks) != set(expected):
        raise ValueError("snapshot-missing-chunk")
    return chunks



def health_record_fields(record: bytes, wrapper: bytes) -> dict:
    """Raw code-derived candidates only; a type check is still required."""
    if len(record) != 128 or len(wrapper) != 56:
        raise ValueError("health-candidate-read-hole")
    caps = struct.unpack_from("<ff", record, 0x6C)
    cached_clock = struct.unpack_from("<f", wrapper, 0x34)[0]
    if not all(math.isfinite(value) for value in (*caps, cached_clock)):
        raise ValueError("health-candidate-nonfinite")
    return {
        "baseRaw": struct.unpack_from("<q", record, 0x48)[0],
        "maximumRaw": struct.unpack_from("<q", record, 0x50)[0],
        "modifierRaw": struct.unpack_from("<q", record, 0x60)[0],
        "recordRevision": struct.unpack_from("<i", record, 0x68)[0],
        "wrapperRevision": struct.unpack_from("<i", wrapper, 0x30)[0],
        "wrapperClock": cached_clock,
        "caps": list(caps),
    }


def checked_health_type(base: int, record_vtable: int, descriptor_getter: int,
                        descriptor_vtable: int, type_getter: int) -> int:
    # Exact-SHA static path: 20CCC60 -> 20E0DE0 returns &355F430;
    # descriptor vtable 2C281B0 +8 ->20F2480, seed00560291 ->20E64C0
    # returns6A3BBB7C, XOR low16 B9BE ->02C2. Never call these functions.
    if (record_vtable != base + 0x2C0EE88 or descriptor_getter != base + 0x20CCC60
            or descriptor_vtable != base + 0x2C281B0 or type_getter != base + 0x20F2480):
        raise ValueError("health-type-fingerprint-mismatch")
    return (0x6A3BBB7C ^ 0xB9BE) & 0xFFFF


def checked_energy_type(base: int, record_vtable: int, descriptor_getter: int,
                        descriptor_vtable: int, type_getter: int) -> int:
    """Pure-read Energy type guard for the exact SHA; no game helper is invoked.

    The installed PE proves 231BEB0 -> 232FDC0 -> 35AEB80, whose initialized
    vtable is 2D1D420 and +8 type getter 233E9B0. The leaf passes seed
    002239C5 to 23354F0. Its first unsigned compare is <=17E6D245 and that
    taken branch returns 2DD59D90; low16 XOR 9ABB yields 072B.
    """
    if (record_vtable != base + 0x2D19498 or descriptor_getter != base + 0x231BEB0
            or descriptor_vtable != base + 0x2D1D420 or type_getter != base + 0x233E9B0):
        raise ValueError("energy-type-fingerprint-mismatch")
    return (0x2DD59D90 ^ 0x9ABB) & 0xFFFF


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def position_transform_candidates(component: bytes, post_read: bytes) -> dict:
    """Raw cached 3x3 transforms only; neither matrix is qualified player facing."""
    if len(component) < 0xB8 or len(post_read) != 0x70:
        raise ValueError("position-transform-read-hole")
    scope = "candidate-only; facing/axis/passive-freshness/restart-unverified"
    if component[0x48:0xB8] != post_read:
        return {"status": "changed-during-probe", "scope": scope,
                "inputsStable": False}
    primary_xyz = struct.unpack_from("<fff", component, 0x48)
    secondary_xyz = struct.unpack_from("<fff", component, 0x88)
    for label, xyz in (("primary", primary_xyz), ("secondary", secondary_xyz)):
        if not all(math.isfinite(value) for value in xyz):
            return {"status": "unavailable", "reason": f"nonfinite-{label}-xyz",
                    "inputsStable": True, "scope": scope}
    result = {"scope": scope, "inputsStable": True,
              "secondaryCachedXyzCandidate": dict(zip(("x", "y", "z"), secondary_xyz))}
    matrices = []
    for offset in (0x60, 0x94):
        values = struct.unpack_from("<9f", component, offset)
        if not all(math.isfinite(value) for value in values):
            return {"status": "unavailable", "reason": "nonfinite-transform",
                    "inputsStable": True, "scope": scope}
        rows = [list(values[i:i + 3]) for i in (0, 3, 6)]
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))
        orthonormal_error = max(
            abs(dot(rows[i], rows[j]) - (1 if i == j else 0))
            for i in range(3) for j in range(3))
        a, b, c, d, e, f, g, h, k = values
        determinant = a * (e * k - f * h) - b * (d * k - f * g) + c * (d * h - e * g)
        y_rotation_error = max(abs(b), abs(d), abs(f), abs(h), abs(e - 1),
                               abs(k - a), abs(c + g))
        matrices.append({"sourceOffset": f"0x{offset:X}", "rowsF32": rows,
                         "orthonormalError": orthonormal_error,
                         "determinant": determinant, "yRotationError": y_rotation_error,
                         "planarAngleDegreesCandidate": math.degrees(math.atan2(g, a))
                         if max(orthonormal_error, abs(determinant - 1),
                                y_rotation_error) < 0.01 else None})
    result["matrices"] = matrices
    result["status"] = ("structural-rotation-candidate"
                        if all(matrix["planarAngleDegreesCandidate"] is not None
                               for matrix in matrices) else "unqualified-matrix-shape")
    return result


def actor_render_pose_candidates(position_pose: bytes, actor_pose: bytes,
                                 model_matrix: bytes, offset_a: bytes,
                                 offset_b: bytes, render_pose: bytes | None,
                                 *, normal_render_branch: bool) -> dict:
    """Compose saved float32 pose fragments; never resolve or read live pointers."""
    scope = "candidate-only; owner/facing/passive-freshness/restart-unverified"
    if type(normal_render_branch) is not bool:
        raise ValueError("actor-render-branch-flag")
    required = ((position_pose, 0x70), (actor_pose, 0x30),
                (model_matrix, 0x24), (offset_a, 0x0C), (offset_b, 0x0C))
    if any(len(data) != size for data, size in required) or (
            render_pose is not None and len(render_pose) != 0x30):
        raise ValueError("actor-render-read-hole")
    if render_pose is not None and not normal_render_branch:
        raise ValueError("actor-render-alternate-branch")

    fields = {"position": struct.unpack("<28f", position_pose),
              "actor": struct.unpack("<12f", actor_pose),
              "model": struct.unpack("<9f", model_matrix),
              "offsetA": struct.unpack("<3f", offset_a),
              "offsetB": struct.unpack("<3f", offset_b)}
    if render_pose is not None:
        fields["render"] = struct.unpack("<12f", render_pose)
    for name, values in fields.items():
        if not all(math.isfinite(value) for value in values):
            return {"status": "unavailable", "reason": f"nonfinite-{name}",
                    "scope": scope}

    def rows(values: tuple) -> list[list[float]]:
        return [list(values[start:start + 3]) for start in (0, 3, 6)]

    def shape(matrix: list[list[float]]) -> dict:
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))
        orthogonal_error = max(abs(dot(matrix[i], matrix[j]) - (i == j))
                               for i in range(3) for j in range(3))
        (a, b, c), (d, e, f), (g, h, k) = matrix
        determinant = a * (e * k - f * h) - b * (d * k - f * g) + c * (d * h - e * g)
        return {"orthonormalError": orthogonal_error, "determinant": determinant}

    position = fields["position"]
    secondary_matrix = rows(position[0x4C // 4:])
    secondary_xyz = position[0x40 // 4:0x4C // 4]
    actor_matrix = rows(fields["actor"][:9])
    actor_xyz = fields["actor"][9:12]
    model = rows(fields["model"])
    composed = [[sum(actor_matrix[i][k] * model[k][j] for k in range(3))
                 for j in range(3)] for i in range(3)]
    expected_xyz = [secondary_xyz[i] + fields["offsetA"][i] + fields["offsetB"][i]
                    for i in range(3)]
    matrix_delta = lambda a, b: max(abs(a[i][j] - b[i][j])
                                   for i in range(3) for j in range(3))
    xyz_delta = lambda a, b: max(abs(a[i] - b[i]) for i in range(3))
    comparison = {"status": ("not-captured" if normal_render_branch
                             else "alternate-branch-unqualified")}
    if render_pose is not None:
        render_matrix = rows(fields["render"][:9])
        render_xyz = fields["render"][9:12]
        comparison = {"status": "normal-branch-numeric-candidate",
                      "matrixMaxAbsDelta": matrix_delta(composed, render_matrix),
                      "xyzMaxAbsDelta": xyz_delta(expected_xyz, render_xyz),
                      "matrixShape": shape(render_matrix)}
    return {"status": "candidate-only", "scope": scope,
            "normalRenderBranch": normal_render_branch,
            "primaryXyzCandidate": list(position[:3]),
            "secondaryXyzCandidate": list(secondary_xyz),
            "computedActorXyz": expected_xyz,
            "computedRenderRows": composed,
            "positionToActorMatrixMaxAbsDelta": matrix_delta(secondary_matrix, actor_matrix),
            "actorXyzMaxAbsDelta": xyz_delta(expected_xyz, actor_xyz),
            "matrixShape": {"positionSecondary": shape(secondary_matrix),
                            "actor": shape(actor_matrix), "model": shape(model),
                            "composition": shape(composed)},
            "renderComparison": comparison}


RESOURCE_LAYOUTS = {
    3: {"name": "mana", "resolverType": "0x072A", "base": 0x1C,
        "maximum": 0x24, "rate": 0x18, "revision": 0x20,
        "wrapperRevision": 0x1C, "wrapperClock": 0x24},
    4: {"name": "energy", "resolverType": "0x072B", "base": 0x20,
        "maximum": 0x24, "rate": 0x28, "revision": 0x34,
        "wrapperRevision": 0x18, "wrapperClock": 0x1C},
}


def require_disjoint_records(health_address: int | None, resource_address: int | None) -> None:
    """Distinct resolver types must never alias the same live record address."""
    if health_address is not None and resource_address is not None and health_address == resource_address:
        raise ValueError("health-resource-record-alias")


def resource_record_fields(kind: int, record: bytes, wrapper: bytes) -> dict:
    """Untyped native resource candidates; never treat a resolver constant as type proof."""
    layout = RESOURCE_LAYOUTS.get(kind) if type(kind) is int else None
    if layout is None:
        return {"status": "not-applicable", "kind": kind}
    if len(record) != 64 or len(wrapper) != 48:
        raise ValueError("resource-candidate-read-hole")
    cached_clock = struct.unpack_from("<f", wrapper, layout["wrapperClock"])[0]
    if not math.isfinite(cached_clock):
        raise ValueError("resource-candidate-nonfinite-clock")
    fields = {"kind": kind, "name": layout["name"],
              "expectedNativeResolverTypeUnverified": layout["resolverType"],
              "baseRaw": struct.unpack_from("<i", record, layout["base"])[0],
              "maximumRaw": struct.unpack_from("<i", record, layout["maximum"])[0],
              "rateRaw": struct.unpack_from("<i", record, layout["rate"])[0],
              "recordRevision": struct.unpack_from("<i", record, layout["revision"])[0],
              "wrapperRevision": struct.unpack_from("<i", wrapper, layout["wrapperRevision"])[0],
              "wrapperClock": cached_clock}
    fields["revisionConsistent"] = fields["recordRevision"] == fields["wrapperRevision"]
    return fields


def coherent_mana_resource_transition(before_record: bytes, before_wrapper: bytes,
                                      after_record: bytes, after_wrapper: bytes) -> dict:
    """Validate one kind-3 cache epoch transition without relaxing owner identity.

    Mana's whole wrapper and record contain clocks/revisions that can advance
    during a bounded read. Immutable bytes and two paired revision counters stay
    strict; both clock fields must remain finite and nondecreasing.
    """
    if any(len(value) != expected for value, expected in (
            (before_record, 64), (after_record, 64),
            (before_wrapper, 48), (after_wrapper, 48))):
        raise ValueError("mana-transition-read-hole")
    if (before_wrapper[:0x18] != after_wrapper[:0x18]
            or before_wrapper[0x28:] != after_wrapper[0x28:]
            or before_record[:0x18] != after_record[:0x18]
            or before_record[0x38:] != after_record[0x38:]):
        raise ValueError("mana-immutable-owner-or-record-changed")
    before_fields = resource_record_fields(3, before_record, before_wrapper)
    after_fields = resource_record_fields(3, after_record, after_wrapper)
    before_secondary = (struct.unpack_from("<i", before_wrapper, 0x18)[0],
                        struct.unpack_from("<i", before_record, 0x28)[0])
    after_secondary = (struct.unpack_from("<i", after_wrapper, 0x18)[0],
                       struct.unpack_from("<i", after_record, 0x28)[0])
    if (not before_fields["revisionConsistent"] or not after_fields["revisionConsistent"]
            or before_secondary[0] != before_secondary[1]
            or after_secondary[0] != after_secondary[1]):
        raise ValueError("mana-transition-mixed-revisions")
    before_clocks = tuple(struct.unpack_from("<f", before_wrapper, offset)[0]
                          for offset in (0x20, 0x24))
    after_clocks = tuple(struct.unpack_from("<f", after_wrapper, offset)[0]
                         for offset in (0x20, 0x24))
    if (not all(math.isfinite(value) for value in (*before_clocks, *after_clocks))
            or any(after < before for before, after in zip(before_clocks, after_clocks))):
        raise ValueError("mana-transition-clock-invalid-or-backward")
    return {
        "status": "unchanged" if (before_record == after_record and
                                     before_wrapper == after_wrapper) else "coherent-cache-transition",
        "beforeFields": before_fields,
        "afterFields": after_fields,
        "beforeSecondaryRevision": before_secondary[0],
        "afterSecondaryRevision": after_secondary[0],
        "beforeClocks": list(before_clocks),
        "afterClocks": list(after_clocks),
    }


def require_resource_owner_anchors(expected: dict[int, bytes], actual: dict[int, bytes],
                                   reason: str = "resource-ownership-anchor-changed") -> None:
    """Require an exact, complete reread of every resource owner/type anchor."""
    if set(actual) != set(expected) or any(actual[address] != raw
                                           for address, raw in expected.items()):
        raise ValueError(reason)


def calculate_health(fields: dict, clock: float) -> dict:
    """Current-build arithmetic for finite ordinary inputs, never a cache write."""
    unavailable = lambda reason: {"status": "unavailable", "reason": reason}
    if fields["recordRevision"] != fields["wrapperRevision"]:
        return unavailable("revision-mismatch")
    base, maximum, modifier = (fields[key] for key in ("baseRaw", "maximumRaw", "modifierRaw"))
    if (any(type(value) is not int or not -(1 << 31) <= value < 1 << 31
            for value in (base, maximum, modifier)) or maximum <= 0):
        return unavailable("outside-normal-integer-domain")
    caps = fields["caps"]
    cached = fields["wrapperClock"]
    if (len(caps) != 2 or not all(math.isfinite(value) for value in (*caps, clock, cached))
            or not all(0 <= cap <= 1 for cap in caps)):
        return unavailable("invalid-float-input")
    try:
        delta = f32(f32(clock) - f32(cached))
    except (OverflowError, struct.error):
        return unavailable("float32-overflow")
    if not 0 <= delta < 2147483647:
        return unavailable("clock-delta-outside-normal-domain")
    elapsed = f32(math.floor(delta))
    rate = f32(modifier)
    adjustment = math.trunc(float(rate) * -0.009999999776482582 * float(elapsed))
    adjusted = base - adjustment
    if not -(1 << 63) <= adjusted < 1 << 63:
        return unavailable("integer-conversion-or-subtraction-overflow")
    cap = min(caps)
    value = min(max(adjusted, 0), maximum)
    if base == 0:
        value = 0
    elif float(value) / float(maximum) > cap:
        value = math.trunc(float(maximum) * float(cap))
    elif base > 0 and value <= 0:
        value = 1
    return {"status": "calculated-candidate", "current": value, "maximum": maximum,
            "clock": clock, "elapsedWholeSeconds": elapsed,
            "formulaRva": "0x133B150", "scope": "finite-normal-values-only"}


def calculate_energy(fields: dict, clock: float) -> dict:
    """Read-only ordinary-domain emulation of exact RVA 133F2C0 (kind-4 Energy).

    Native uses CVTDQ2PS, two separately rounded MULSS operations, CVTTSS2SI
    and signed 32-bit SUB before clamping. We reject overflow/undefined cases,
    never call the native getter or update its revision/clock cache.
    """
    unavailable = lambda reason: {"status": "unavailable", "reason": reason}
    if fields.get("kind") != 4:
        return unavailable("not-energy-kind-four")
    if fields["recordRevision"] != fields["wrapperRevision"]:
        return unavailable("revision-mismatch-needs-native-cache-write")
    base, maximum, rate = (fields[key] for key in ("baseRaw", "maximumRaw", "rateRaw"))
    if (any(type(value) is not int or not -(1 << 31) <= value < 1 << 31
            for value in (base, maximum, rate)) or base < 0 or maximum <= 0):
        return unavailable("outside-normal-integer-domain")
    cached = fields["wrapperClock"]
    if not all(type(value) in (int, float) and math.isfinite(value)
               for value in (clock, cached)):
        return unavailable("invalid-float-input")
    try:
        elapsed = f32(f32(clock) - f32(cached))
        native_multiplier = struct.unpack("<f", bytes.fromhex("0ad723bc"))[0]
        product = f32(f32(f32(rate) * native_multiplier) * elapsed)
    except (OverflowError, struct.error, ValueError):
        return unavailable("float32-overflow")
    if not (math.isfinite(elapsed) and 0 <= elapsed < (1 << 31)):
        return unavailable("clock-delta-outside-normal-domain")
    if not math.isfinite(product) or not -(1 << 31) < product < (1 << 31) - 1:
        return unavailable("int32-conversion-overflow-or-sentinel")
    change = math.trunc(product)
    adjusted = base - change
    if not -(1 << 31) <= adjusted < (1 << 31):
        return unavailable("signed32-subtraction-overflow")
    return {"status": "calculated-candidate", "current": min(max(adjusted, 0), maximum),
            "maximum": maximum, "clock": clock, "elapsedSeconds": elapsed,
            "truncatedRateAdjustment": change, "formulaRva": "0x133F2C0",
            "scope": "finite-normal-int32-values-only"}


def run(lab: str, *, health_record: bool = False, resource_record: bool = False,
        cast_record: bool = False, cooldown_roots: bool = False,
        cooldown_collections: bool = False, cooldown_cache: bool = False,
        ability_seeds: bool = False, ability_keys: tuple[int, ...] = (),
        player_ability_maps: bool = False, ability_localization: bool = False,
        ability_dictionary: bool = False) -> dict:
    if lab not in ("lab1", "lab2"):
        raise ValueError("unknown-lab")
    if (len(ability_keys) > 8 or len(set(ability_keys)) != len(ability_keys) or
            any(type(key) is not int or not 0 <= key <= 0xFFFFFFFF for key in ability_keys)):
        raise ValueError("invalid-ability-key-selection")
    ability_localization = ability_localization or ability_dictionary
    ability_seeds = ability_seeds or bool(ability_keys) or ability_localization
    cooldown_cache = cooldown_cache or ability_seeds
    cooldown_collections = cooldown_collections or cooldown_cache
    cooldown_roots = cooldown_roots or cooldown_collections
    probe_path = Path(__file__)
    probe_sha = sha(probe_path.read_bytes())
    sys.path.insert(0, str(ROOT))
    from scripts.lab_codex import LabCodex
    from scripts.inventory_passive_rift_sources import ps_literal
    from scripts.vmware_guest_session import SessionError
    from scripts.native_cast_candidate import read_cast_topology

    workflow_path = ROOT / "artifacts" / "control-fleet-live" / lab / "workflow.json"
    workflow_raw = workflow_path.read_bytes()
    workflow = json.loads(workflow_raw)
    reader = str(PureWindowsPath(workflow["guestDirectory"]) / "RiftReader2.Live.exe")
    reader_sha = workflow["readerSha256"]
    if not re.fullmatch(r"[0-9A-F]{64}", reader_sha):
        raise ValueError("invalid-reader-sha")

    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm_identity = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    folder = ROOT / "artifacts" / "native-unit-manager" / lab / token
    folder.mkdir(parents=True, exist_ok=False)
    prefix = settings["guestRoot"] + "\\unit-manager-" + token
    evidence = {}
    observation_times = {}
    observation_intervals = {}
    deadline = time.monotonic() + 240
    review = {"schemaVersion": 1, "lab": lab, "output": str(folder),
              "vmIdentity": vm_identity,
              "readerExe": reader, "readerSha256": reader_sha,
              "workflowSha256": sha(workflow_raw), "probeSha256": probe_sha,
              "operationInitiationDeadlineSeconds": 240,
              "deadlineSemantics": "checked-before-each-operation; admitted operations use separate bounded timeouts",
              "status": "incomplete",
              "qualification": "candidate-only; no passive-freshness or restart qualification"}
    helper_names = []
    if cooldown_collections:
        helper_names += ["native_thread_metadata.py", "native_tls_collections.py"]
    if cooldown_cache or player_ability_maps:
        helper_names.append("native_resolver_cache.py")
    if ability_seeds:
        helper_names.append("native_ability_record_seed.py")
    if ability_localization:
        helper_names.append("native_localization_seed.py")
    if player_ability_maps:
        helper_names.append("native_player_ability_maps.py")
    if cast_record:
        helper_names.append("native_cast_candidate.py")
    helper_sources = {ROOT / "scripts" / name: sha((ROOT / "scripts" / name).read_bytes())
                      for name in dict.fromkeys(helper_names)}
    if helper_sources:
        review["helperSourceSha256"] = {path.name: value for path, value in helper_sources.items()}
    try:
        with api._session(config, settings, vm_identity, folder) as guest:
            def native(mode: str, name: str, request: dict | None = None) -> dict:
                if time.monotonic() >= deadline:
                    raise ValueError("probe-operation-budget-exceeded")
                if mode not in ("inspect-native", "snapshot-native"):
                    raise ValueError("unsupported-native-mode")
                output = folder / (name + ".json")
                guest_output = prefix + "-" + name + ".json"
                command = (
                    "$ErrorActionPreference='Stop';$e=" + ps_literal(reader) + ";"
                    "if(!(Test-Path -LiteralPath $e -PathType Leaf)){throw 'reader-missing'};"
                    "if((Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -ne " +
                    ps_literal(reader_sha) + "){throw 'reader-sha-mismatch'};"
                    "if(Test-Path -LiteralPath " + ps_literal(guest_output) +
                    "){throw 'output-exists'};"
                )
                arguments = ""
                if request is not None:
                    request_path = folder / (name + "-request.json")
                    payload = encoded(request)
                    with request_path.open("xb") as stream:
                        stream.write(payload)
                    guest_request = prefix + "-" + name + "-request.json"
                    guest.run("copyFileFromHostToGuest", str(request_path), guest_request)
                    command += ("if((Get-FileHash -LiteralPath " + ps_literal(guest_request) +
                                ").Hash -ne " + ps_literal(sha(payload)) +
                                "){throw 'request-sha-mismatch'};")
                    arguments = " --request " + ps_literal(guest_request)
                    evidence[request_path.name] = sha(payload)
                command += ("& $e " + mode + arguments + " --output " +
                            ps_literal(guest_output) +
                            " | Out-Null;if($LASTEXITCODE -notin @(0,3)){throw 'native-command-failed'}")
                guest.powershell(command, timeout=60)
                guest.copy_from_guest(guest_output, output, timeout=60)
                raw = output.read_bytes()
                if len(raw) > 1024 * 1024:
                    raise ValueError("probe-report-size-exceeded")
                evidence[output.name] = sha(raw)
                parsed = json.loads(raw.decode("utf-8-sig"))
                observation_times[name] = parsed.get("completedAtUtc", parsed.get("capturedAtUtc"))
                observation_intervals[name] = {
                    "startedAtUtc": parsed.get("startedAtUtc", parsed.get("capturedAtUtc")),
                    "completedAtUtc": parsed.get("completedAtUtc", parsed.get("capturedAtUtc")),
                }
                return parsed

            before = native("inspect-native", "inspect-before")
            identity, target = inspection_identity(before)
            review["identity"] = identity
            base = identity["moduleBaseAddress"]

            def take(name: str, ranges: list[tuple[int, int]], *, relative=False):
                request = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot-request/1",
                           "target": target, "maxDurationMilliseconds": 10000,
                           "ranges": [{"addressKind": ("module-relative-rva" if relative else
                                                     "absolute-session-address"),
                                       "address": f"0x{address:X}", "byteLength": length}
                                      for address, length in ranges]}
                return snapshot_bytes(native("snapshot-native", name, request), request, identity)

            thread_query_exe = None

            def thread_metadata(name: str) -> dict:
                nonlocal thread_query_exe
                from scripts.native_thread_metadata import build_thread_metadata_executable
                if time.monotonic() >= deadline:
                    raise ValueError("probe-operation-budget-exceeded")
                guest_report = prefix + "-" + name + ".json"
                guest_query = prefix + "-thread-query.exe"
                if thread_query_exe is None:
                    thread_query_exe = build_thread_metadata_executable(folder / "thread-query.exe")
                    evidence[thread_query_exe.name] = sha(thread_query_exe.read_bytes())
                    evidence["thread-query.cs"] = sha(thread_query_exe.with_suffix(".cs").read_bytes())
                    guest.run("copyFileFromHostToGuest", str(thread_query_exe), guest_query)
                arguments = [str(identity["processId"]), str(identity["processStartUtcTicks"]),
                             identity["executableSha256"], identity["executablePath"], guest_report]
                guest.powershell(
                    "$ErrorActionPreference='Stop';if((Get-FileHash -LiteralPath " +
                    ps_literal(guest_query) + ").Hash -ne " + ps_literal(evidence[thread_query_exe.name]) +
                    "){throw 'thread-query-source-mismatch'};& " + ps_literal(guest_query) + " " +
                    " ".join(ps_literal(value) for value in arguments) +
                    ";if($LASTEXITCODE -ne 0){throw 'thread-query-failed'}",
                    timeout=60)
                output = folder / (name + ".json")
                guest.copy_from_guest(guest_report, output, timeout=60)
                raw = output.read_bytes()
                if len(raw) > 256 * 1024:
                    raise ValueError("thread-metadata-report-size-exceeded")
                evidence[output.name] = sha(raw)
                data = json.loads(raw.decode("utf-8-sig"))
                if (data.get("processId") != identity["processId"] or
                        data.get("processStartUtcTicks") != str(identity["processStartUtcTicks"]) or
                        data.get("executableSha256") != identity["executableSha256"] or
                        data.get("executablePath") != identity["executablePath"]):
                    raise ValueError("thread-metadata-process-epoch-mismatch")
                return data

            roots_ranges = [(MANAGER_RVA, 8), (PLAYER_SYSTEM_RVA, 8),
                            (POSITION_INDEX_RVA, 4), (HEALTH_INDEX_RVA, 4)]
            if health_record or resource_record or player_ability_maps:
                roots_ranges.append((0x33DC2B0, 8))
            if health_record:
                roots_ranges += [(0x355F430, 8), (0x2C281B8, 8)]
            if cooldown_roots:
                roots_ranges += [(0x33624C8, 8), (0x3372C18, 8)]
            if cooldown_cache:
                roots_ranges.append((0x33DC1B8, 8))
            if player_ability_maps:
                roots_ranges.append((0x2F57260, 4))
            roots = take("roots", roots_ranges, relative=True)
            manager = pointer(struct.unpack("<Q", roots[base + MANAGER_RVA])[0])
            player_system = pointer(struct.unpack("<Q", roots[base + PLAYER_SYSTEM_RVA])[0])
            position_index = struct.unpack("<i", roots[base + POSITION_INDEX_RVA])[0]
            health_index = struct.unpack("<i", roots[base + HEALTH_INDEX_RVA])[0]
            if not all(0 <= value < 0x60 for value in (position_index, health_index)):
                raise ValueError("component-index-outside-selector-area")
            owner_ranges = [(manager + 0x50, 8), (player_system + 0x360, 8)]
            if player_ability_maps:
                owner_ranges.append((player_system + 0x3F8, 8))
            owner = take("owner", owner_ranges)
            table = pointer(struct.unpack("<Q", owner[manager + 0x50])[0], 24)
            key = struct.unpack("<Q", owner[player_system + 0x360])[0]
            header = take("table", [(table, 24)])[table]
            lookup_counter = 0

            def read_node(address: int, length: int) -> bytes:
                nonlocal lookup_counter
                lookup_counter += 1
                return take("lookup-" + str(lookup_counter), [(address, length)])[address]

            found = find_entity(header, key, read_node)
            entity = found["entity"]
            entity_bytes = take("entity", [(entity, 128)])[entity]
            component_table = pointer(struct.unpack_from("<Q", entity_bytes, 0x78)[0])
            slots = {"position": entity_bytes[0x18 + position_index],
                     "health": entity_bytes[0x18 + health_index]}
            if 0xFF in slots.values():
                raise ValueError("required-component-missing")
            component_addresses = sorted({component_table + slot * 8 for slot in slots.values()})
            component_raw = take("component-pointers", [(p, 8) for p in component_addresses])
            components = {kind: pointer(struct.unpack("<Q", component_raw[
                          component_table + slot * 8])[0]) for kind, slot in slots.items()}
            value_ranges = [(components["position"], 0x110)]
            if health_record or resource_record:
                value_ranges.append((components["health"], 0x48 if resource_record else 0x38))
            values = take("component-values", value_ranges)
            xyz = struct.unpack_from("<fff", values[components["position"]], 0x48)
            if not all(math.isfinite(value) for value in xyz):
                raise ValueError("nonfinite-position-candidate")


            health = None
            health_anchors = {}
            if health_record:
                wrapper = values[components["health"]]
                owner_object = pointer(struct.unpack_from("<Q", wrapper, 0x28)[0])
                owner_slot = owner_object + 0x40
                owner_raw = take("health-owner", [(owner_slot, 8)])[owner_slot]
                container = pointer(struct.unpack("<Q", owner_raw)[0])
                record_slot = container + 0x640
                slot_raw = take("health-slot", [(record_slot, 8)])[record_slot]
                record_address = pointer(struct.unpack("<Q", slot_raw)[0], 128)
                clock_object = pointer(struct.unpack("<Q", roots[base + 0x33DC2B0])[0])
                record_capture = take("health-record", [(record_address, 128), (clock_object + 0x18, 4)])
                record_raw = record_capture[record_address]
                game_clock = struct.unpack("<f", record_capture[clock_object + 0x18])[0]
                vtable = pointer(struct.unpack_from("<Q", record_raw)[0])
                if not base <= vtable < base + identity["moduleSize"] - 0x48:
                    raise ValueError("health-vtable-outside-exact-module")
                getter_slot = vtable + 0x40
                getter_raw = take("health-type-getter", [(getter_slot, 8)])[getter_slot]
                getter = struct.unpack("<Q", getter_raw)[0]  # x64 code need not be 8-byte aligned.
                if not base <= getter < base + identity["moduleSize"]:
                    raise ValueError("health-type-getter-outside-exact-module")
                type_code = checked_health_type(
                    base, vtable, getter, struct.unpack("<Q", roots[base + 0x355F430])[0],
                    struct.unpack("<Q", roots[base + 0x2C281B8])[0])
                health = {
                    "status": "type-checked-record-candidate",
                    "record": f"0x{record_address:X}",
                    "ownerObject": f"0x{owner_object:X}", "container": f"0x{container:X}",
                    "vtableRva": f"0x{vtable - base:X}",
                    "descriptorGetterRva": f"0x{getter - base:X}",
                    "fields": health_record_fields(record_raw, wrapper[:0x38]),
                    "typeValidation": "exact-build-vtable-and-metadata-path; no native function called",
                    "typeCode": f"0x{type_code:X}", "observedAtUtc": observation_times["health-record"],
                    "gameClock": game_clock,
                }
                health_anchors = {owner_slot: owner_raw, record_slot: slot_raw,
                                  getter_slot: getter_raw,
                                  components["health"] + 0x28: wrapper[0x28:0x38]}

            resource = None
            resource_anchors = {}
            resource_record_address = None
            resource_record_raw = None
            resource_wrapper = None
            resource_wrapper_raw = None
            resource_clock_address = None
            resource_game_clock_raw = None
            if resource_record:
                component = values[components["health"]]
                kind_owner = pointer(struct.unpack_from("<Q", component, 0x40)[0])
                kind_raw = take("resource-kind", [(kind_owner + 0x168, 4)])[kind_owner + 0x168]
                kind = struct.unpack("<i", kind_raw)[0]
                resource_anchors[components["health"] + 0x40] = component[0x40:0x48]
                resource_anchors[kind_owner + 0x168] = kind_raw
                resource = {"kind": kind, "status": "not-applicable",
                            "observedAtUtc": observation_times["resource-kind"],
                            "qualifier": "current-build-static-kind-only; no typed live resource"}
                if kind in RESOURCE_LAYOUTS:
                    resource_wrapper = pointer(struct.unpack_from("<Q", component, 0x38)[0], 48)
                    resource_anchors[components["health"] + 0x38] = component[0x38:0x40]
                    resource_wrapper_raw = take(
                        "resource-wrapper", [(resource_wrapper, 48)])[resource_wrapper]
                    ref_slot = pointer(struct.unpack_from("<Q", resource_wrapper_raw, 0x10)[0], 8)
                    ref_raw = take("resource-ref-slot", [(ref_slot, 8)])[ref_slot]
                    resource_record_address = pointer(struct.unpack("<Q", ref_raw)[0], 64)
                    clock_owner = pointer(struct.unpack("<Q", roots[base + 0x33DC2B0])[0])
                    resource_capture = take(
                        "resource-record", [(resource_record_address, 64),
                                            (clock_owner + 0x18, 4)])
                    resource_record_raw = resource_capture[resource_record_address]
                    resource_clock_address = clock_owner + 0x18
                    resource_game_clock_raw = resource_capture[resource_clock_address]
                    game_clock = struct.unpack("<f", resource_game_clock_raw)[0]
                    vtable = pointer(struct.unpack_from("<Q", resource_record_raw)[0], 72)
                    if not base <= vtable < base + identity["moduleSize"] - 0x48:
                        raise ValueError("resource-vtable-outside-exact-module")
                    getter_slot = vtable + 0x40
                    getter_raw = take("resource-type-getter", [(getter_slot, 8)])[getter_slot]
                    getter = struct.unpack("<Q", getter_raw)[0]
                    if not base <= getter < base + identity["moduleSize"]:
                        raise ValueError("resource-type-getter-outside-exact-module")
                    fields = resource_record_fields(kind, resource_record_raw, resource_wrapper_raw)
                    energy_type_code = None
                    if kind == 4:
                        # The Energy descriptor singleton is read, never initialized.
                        # Mana kind 3 has a DIFFERENT, still-untraced type chain.
                        energy_slots = take("energy-static-type", [(0x35AEB80, 8),
                                                                    (0x2D1D428, 8)], relative=True)
                        energy_type_code = checked_energy_type(
                            base, vtable, getter,
                            struct.unpack("<Q", energy_slots[base + 0x35AEB80])[0],
                            struct.unpack("<Q", energy_slots[base + 0x2D1D428])[0])
                        resource_anchors.update(energy_slots)
                    stable_inputs = fields["revisionConsistent"] and math.isfinite(game_clock)
                    resource.update({
                        "status": ("type-checked-raw-record-candidate" if energy_type_code is not None
                                   else "untyped-record-candidate") if stable_inputs else "unavailable",
                        "reason": None if stable_inputs else "inconsistent-revision-or-game-clock",
                        "name": fields["name"],
                        "qualifier": ("exact-build-type-matched-energy-raw-record; current-value-unqualified"
                                      if energy_type_code is not None else
                                      "current-build-static-kind-only; no typed live resource"),
                        "resourceWrapper": f"0x{resource_wrapper:X}",
                        "referenceSlot": f"0x{ref_slot:X}",
                        "record": f"0x{resource_record_address:X}",
                        "recordVtableRva": f"0x{vtable - base:X}",
                        "candidateDescriptorGetterRva": f"0x{getter - base:X}",
                        "fields": fields, "gameClock": game_clock,
                        "observedAtUtc": observation_times["resource-record"],
                        "typeCode": f"0x{energy_type_code:04X}" if energy_type_code is not None else None,
                        "typeValidation": ("exact-build-vtable-and-metadata-path; no native function called"
                                           if energy_type_code is not None else
                                           "NOT PERFORMED; vtable/descriptor/type fingerprints pending"),
                    })
                    if kind == 3:
                        # Kind-3 Mana cache revisions/clocks at +0x18..+0x27 may
                        # advance coherently. Its full wrapper is reread below;
                        # immutable bytes and the mutable state are validated as
                        # one transition rather than stored as a whole anchor.
                        pass
                    else:
                        resource_anchors[resource_wrapper] = resource_wrapper_raw
                    resource_anchors[ref_slot] = ref_raw
                    resource_anchors[getter_slot] = getter_raw

            require_disjoint_records(
                record_address if health is not None else None, resource_record_address)

            cooldown_anchors = {}
            if cooldown_roots:
                selector_owner = struct.unpack("<Q", roots[base + 0x33624C8])[0]
                lookup_wrapper = struct.unpack("<Q", roots[base + 0x3372C18])[0]
                cooldown = {"qualification": "static-resolver-root-candidate",
                            "status": "unavailable", "selectorOwner": selector_owner,
                            "lookupWrapper": lookup_wrapper, "lookupOwner": None, "selector": None,
                            "playerOwnershipEstablished": False}
                if selector_owner and lookup_wrapper:
                    pointer(selector_owner, 0x42)
                    pointer(lookup_wrapper)
                    cooldown_ranges = [(selector_owner + 0x40, 2), (lookup_wrapper, 8)]
                    cooldown_anchors = take("cooldown-selector", cooldown_ranges)
                    lookup_owner = struct.unpack("<Q", cooldown_anchors[lookup_wrapper])[0]
                    cooldown.update({"lookupOwner": lookup_owner,
                                     "selector": struct.unpack(
                                         "<H", cooldown_anchors[selector_owner + 0x40])[0]})
                    if lookup_owner:
                        pointer(lookup_owner, 0x278)
                        cooldown["status"] = "candidate-roots-present"
                        if cooldown_collections:
                            cooldown_anchors.update(take("cooldown-owner", [(lookup_owner + 0x274, 4)]))
                    else:
                        cooldown["reason"] = "null-resolver-owner-no-game-initialization"
                else:
                    cooldown["reason"] = "null-resolver-root-no-game-initialization"
                cooldown["observedAtUtc"] = observation_times.get(
                    "cooldown-selector", observation_times["roots"])
                review["cooldownResolverCandidate"] = cooldown
                if cooldown_cache and cooldown["status"] == "candidate-roots-present":
                    store_fields = take("cooldown-store-fields", [(lookup_owner + 4, 8)])
                    cooldown_anchors.update(store_fields)
                    store_mode, store_kind = struct.unpack("<II", store_fields[lookup_owner + 4])
                    store = lookup_owner + (0x110 if store_mode == 0 else 0x20)
                    compression = take("cooldown-store-compression", [(store + 0x83, 1)])
                    cooldown_anchors.update(compression)
                    path_address = struct.unpack("<Q", roots[base + 0x33DC1B8])[0]
                    path_text = None
                    path_interpretation = "null-path-global"
                    if path_address:
                        if not 0x10000 <= path_address <= MAX_USER - 255:
                            raise ValueError("invalid-database-path-address")
                        path_length = min(256, 4096 - (path_address & 4095))
                        path_bytes = take("cooldown-database-path", [(path_address, path_length)])
                        cooldown_anchors.update(path_bytes)
                        raw_path = path_bytes[path_address]
                        if b"\x00" in raw_path:
                            try:
                                path_text = raw_path.split(b"\x00", 1)[0].decode("utf-8")
                                path_interpretation = "utf8-candidate-not-selected-store-proof"
                            except UnicodeDecodeError:
                                path_interpretation = "not-a-valid-utf8-path"
                        else:
                            path_interpretation = "no-terminator-in-bounded-read"
                    cooldown["datasetStoreCandidate"] = {
                        "ownerMode": store_mode, "ownerKind": store_kind,
                        "storeAddress": store, "compressionByte": compression[store + 0x83][0],
                        "configuredPathTextCandidate": path_text,
                        "configuredPathInterpretation": path_interpretation,
                        "configuredPathAddress": path_address,
                        "selectedStoreMayBeMemoryOnly": store_mode == 0 and store_kind == 2}
                if cooldown_collections and cooldown["status"] == "candidate-roots-present":
                    from scripts.native_tls_collections import read_tls_collections
                    metadata = thread_metadata("threads-before")
                    tls_index = struct.unpack("<I", cooldown_anchors[lookup_owner + 0x274])[0]
                    threads = [{**row, "tebAddress": int(row["tebAddress"], 16)}
                               for row in metadata["threads"]]
                    tls_read_count = 0
                    tls_observed = {}

                    def read_tls(name, ranges):
                        nonlocal tls_read_count
                        tls_read_count += 1
                        captured = take(f"{name}-{tls_read_count}", ranges)
                        for address, raw in captured.items():
                            if address in tls_observed and tls_observed[address] != raw:
                                raise ValueError("tls-input-changed")
                            tls_observed[address] = raw
                        return captured

                    selected = read_tls_collections(
                        read_tls, threads=threads, process_id=identity["processId"],
                        tls_index=tls_index, embedded_collection=lookup_owner + 0x200)

                    def same_threads(current_metadata):
                        return (metadata.get("partial") is False and
                                current_metadata.get("partial") is False and
                                sorted(metadata["threads"], key=lambda row: row["threadId"]) ==
                                sorted(current_metadata["threads"], key=lambda row: row["threadId"]))

                    after_metadata = None
                    cooldown.update({"tlsIndex": tls_index, "collections": selected,
                                     "threadCoverageBefore": metadata["enumerated"]})
                    if selected["status"] == "candidate":
                        collections = sorted({row["selectedCollection"] for row in selected["threads"]})
                        if len(collections) <= 32:
                            headers = take("cooldown-cache-headers", [
                                (pointer(address, 0x40) + 0x20, 32) for address in collections])
                            cooldown_anchors.update(headers)
                            cooldown["cacheHeaders"] = [
                                {"collection": address, "rawHex": headers[address + 0x20].hex(),
                                 "bucketBase": struct.unpack_from("<Q", headers[address + 0x20])[0],
                                 "stride": struct.unpack_from("<Q", headers[address + 0x20], 8)[0],
                                 "count": struct.unpack_from("<Q", headers[address + 0x20], 16)[0]}
                                for address in collections]
                        else:
                            cooldown["cacheHeadersOmitted"] = "collection-count-exceeds-32"
                        if cooldown_cache and len(collections) == 1:
                            from scripts.native_resolver_cache import (
                                SnapshotPageReader, lookup_resolver_cache, read_resolver_cache)
                            cache_read_count = 0

                            def read_cache(name, ranges):
                                nonlocal cache_read_count
                                cache_read_count += 1
                                return take(f"{name}-{cache_read_count}", ranges)

                            page_reader = SnapshotPageReader(read_cache)
                            cooldown["cacheInventory"] = (
                                lookup_resolver_cache(
                                    page_reader, collection=collections[0], selector=cooldown["selector"],
                                    keys=ability_keys, key_hash=entity_hash)
                                if ability_keys else read_resolver_cache(
                                    page_reader, collection=collections[0],
                                    selector=cooldown["selector"], max_chain_nodes=2048))
                            cooldown["cacheInventory"]["snapshotReadCalls"] = page_reader.read_calls
                            cooldown["cacheInventory"]["snapshotPages"] = len(page_reader.pages)
                            cooldown["cacheInventory"]["collectionAddress"] = collections[0]
                            if ability_seeds and cooldown["cacheInventory"]["status"] == "complete":
                                from scripts.native_ability_record_seed import read_ability_record_seeds
                                entries = cooldown["cacheInventory"]["entries"]
                                seed_entries = ([entry for key in ability_keys for entry in entries
                                                 if entry["key"] == key] if ability_keys else
                                                sorted(entries, key=lambda entry: entry["key"]))
                                seed_reader = SnapshotPageReader(read_cache)
                                seed_rows = read_ability_record_seeds(
                                    seed_reader, entries=seed_entries, module_base=base,
                                    module_size=identity["moduleSize"],
                                    build_sha=identity["executableSha256"], key_hash=entity_hash)
                                cooldown["abilityRecordSeeds"] = {
                                    "qualification": "raw-record-and-fallback-text-candidates",
                                    "requestedKeys": list(ability_keys),
                                    "missingFromThisCache": [key for key in ability_keys
                                                             if not any(entry["key"] == key for entry in entries)],
                                    "records": seed_rows, "snapshotReadCalls": seed_reader.read_calls,
                                    "snapshotPages": len(seed_reader.pages)}
                                if ability_localization:
                                    from scripts.native_localization_seed import (
                                        read_localization_context, read_localization_seeds)
                                    try:
                                        localized_rows = [row for row in seed_rows
                                                          if row.get("child_type_verified") and
                                                          row.get("localization_key_candidate")]
                                        localization_keys = list(dict.fromkeys(
                                            row["localization_key_candidate"] for row in localized_rows))
                                        if not localization_keys:
                                            raise ValueError("no-typed-nonzero-localization-keys")
                                        context_reader = SnapshotPageReader(read_cache)
                                        localization_context = read_localization_context(
                                            context_reader, module_base=base, module_size=identity["moduleSize"],
                                            dictionary_mode=ability_dictionary)
                                        localization_lookup_reader = SnapshotPageReader(read_cache)
                                        localization_lookup = lookup_resolver_cache(
                                            localization_lookup_reader, collection=collections[0],
                                            selector=localization_context["selector"], keys=localization_keys,
                                            key_hash=entity_hash)
                                        if localization_lookup["status"] != "complete":
                                            raise ValueError("localization-cache-lookup-incomplete")
                                        text_reader = SnapshotPageReader(read_cache)
                                        localization = read_localization_seeds(
                                            text_reader, module_base=base, module_size=identity["moduleSize"],
                                            entries=[entry for entry in localization_lookup["entries"]
                                                     if entry.get("result_pointer")],
                                            dictionary_mode=ability_dictionary)
                                        if (localization.get("status") == "complete" and
                                                localization.get("context") != localization_context):
                                            raise ValueError("localization-context-changed")
                                        # Bind the later translation back to the original
                                        # typed record/name child, without reusing cached bytes.
                                        bindings = {}
                                        keyed_entries = {entry["key"]: entry for entry in seed_entries}
                                        for row in localized_rows:
                                            entry = keyed_entries[row["key"]]
                                            bindings[entry["node_address"] + 8] = (
                                                bytes.fromhex(entry["raw_key"]) +
                                                struct.pack("<Q", entry["holder_address"]))
                                            bindings[row["result_slot_address"]] = struct.pack("<Q", row["record_address"])
                                            bindings[row["record_address"] + 0x8E0] = struct.pack("<Q", row["child_address"])
                                            bindings[row["child_address"] + 0x18] = struct.pack("<I", row["localization_key_candidate"])
                                        binding_reader = SnapshotPageReader(read_cache)
                                        current_bindings = binding_reader("localization-source-binding", [
                                            (address, len(raw)) for address, raw in bindings.items()])
                                        if any(current_bindings[address] != raw for address, raw in bindings.items()):
                                            raise ValueError("ability-localization-binding-changed")
                                        localization.update({
                                            "qualification": ("dictionary-only-text-candidates-types-unverified" if ability_dictionary
                                                              else "raw-localized-text-candidates-types-unverified"),
                                            "missingFromThisCache": localization_lookup.get("missingKeys", []),
                                            "abilityLocalizationKeys": {f"0x{row['key']:08X}": row["localization_key_candidate"]
                                                                        for row in localized_rows},
                                            "sourceBindingRechecked": True})
                                        cooldown["abilityLocalizationSeeds"] = localization
                                    except ValueError as error:
                                        cooldown["abilityLocalizationSeeds"] = {
                                            "status": "unavailable", "reason": str(error)[:160], "records": []}
                            post_walk_metadata = thread_metadata("threads-post-walk")
                            if same_threads(post_walk_metadata):
                                tls_items = list(tls_observed.items())
                                for start in range(0, len(tls_items), 128):
                                    batch = tls_items[start:start + 128]
                                    current = take(f"tls-post-cache-{start}", [
                                        (address, len(raw)) for address, raw in batch])
                                    if any(current[address] != raw for address, raw in batch):
                                        raise ValueError("tls-selection-changed-during-cache-walk")
                            else:
                                # Do not touch TEBs whose thread lifetime ended.
                                # Embedded collection bytes can remain raw candidates;
                                # an execution-thread selection claim cannot survive.
                                after_metadata = post_walk_metadata
                        elif cooldown_cache:
                            cooldown["cacheInventory"] = {"status": "partial",
                                                          "reason": "ambiguous-thread-collections", "entries": []}
                    if after_metadata is None:
                        after_metadata = thread_metadata("threads-after")
                    cooldown["threadCoverageAfter"] = after_metadata["enumerated"]
                    selection_verified = selected["status"] == "candidate" and same_threads(after_metadata)
                    if not same_threads(after_metadata):
                        cooldown["collections"] = {"status": "unavailable",
                                                   "reason": "thread-coverage-or-epoch-changed", "threads": []}
                        if "cacheInventory" in cooldown:
                            inventory = cooldown["cacheInventory"]
                            if (inventory.get("status") != "complete" or
                                    inventory.get("collectionAddress") != lookup_owner + 0x200):
                                cooldown["cacheInventory"] = {"status": "partial",
                                                              "reason": "thread-coverage-or-epoch-changed", "entries": []}
                    if "cacheInventory" in cooldown:
                        cooldown["cacheInventory"]["threadSelectionVerified"] = selection_verified
                        cooldown["cacheInventory"]["qualification"] = (
                            "thread-selected-cache-candidate" if selection_verified else "collection-only-candidate")
                        if ("abilityRecordSeeds" in cooldown and
                                cooldown["cacheInventory"]["status"] != "complete"):
                            cooldown["abilityRecordSeeds"] = {
                                "qualification": "unavailable", "reason": "cache-owner-or-selection-unverified",
                                "records": []}
                            if "abilityLocalizationSeeds" in cooldown:
                                cooldown["abilityLocalizationSeeds"] = {
                                    "status": "unavailable", "reason": "cache-owner-or-selection-unverified", "records": []}

            player_map_anchors = {}
            if player_ability_maps:
                from scripts.native_player_ability_maps import read_player_ability_maps
                from scripts.native_resolver_cache import SnapshotPageReader
                cached_entity = struct.unpack("<Q", owner[player_system + 0x3F8])[0]
                player_map_anchors[player_system + 0x3F8] = owner[player_system + 0x3F8]
                if cached_entity != entity:
                    review["playerAbilityMapsCandidate"] = {
                        "status": "unavailable", "reason": "cached-player-entity-differs-from-self-lookup",
                        "cachedEntity": cached_entity, "maps": []}
                else:
                    ability_index = struct.unpack("<i", roots[base + 0x2F57260])[0]
                    if not 0 <= ability_index < 0x60:
                        raise ValueError("ability-component-index-outside-selector-area")
                    ability_slot = entity_bytes[0x18 + ability_index]
                    player_map_anchors[entity + 0x18 + ability_index] = bytes([ability_slot])
                    if ability_slot == 0xFF:
                        review["playerAbilityMapsCandidate"] = {
                            "status": "unavailable", "reason": "ability-component-absent", "maps": []}
                    else:
                        ability_slot_address = component_table + ability_slot * 8
                        player_map_anchors.update(take("player-ability-context", [(ability_slot_address, 8)]))
                        context = pointer(struct.unpack("<Q", player_map_anchors[ability_slot_address])[0], 0x260)
                        map_read_count = 0

                        def read_player_map(name, ranges):
                            nonlocal map_read_count
                            map_read_count += 1
                            return take(f"player-map-{name}-{map_read_count}", ranges)

                        map_reader = SnapshotPageReader(read_player_map)
                        candidate = read_player_ability_maps(
                            map_reader, context=context, clock_root_address=base + 0x33DC2B0)
                        candidate.update({"context": context, "selectorIndex": ability_index,
                                          "slot": ability_slot, "cachedEntityMatchesSelfLookup": True,
                                          "snapshotReadCalls": map_reader.read_calls,
                                          "snapshotPages": len(map_reader.pages)})
                        review["playerAbilityMapsCandidate"] = candidate

            if cast_record:
                cast_read_count = 0

                def read_cast(address: int, length: int) -> bytes:
                    nonlocal cast_read_count
                    cast_read_count += 1
                    return take(f"cast-read-{cast_read_count}", [(address, length)])[address]

                review["castCandidate"] = read_cast_topology(
                    read_cast, module_base=base, entity=entity,
                    build_sha=identity["executableSha256"])

            # Recheck every ownership anchor after staged reads. This is NOT an
            # atomic snapshot or proof that no transient ABA change occurred.
            checks = {base + rva: length for rva, length in roots_ranges}
            checks.update({manager + 0x50: 8, player_system + 0x360: 8, table: 24,
                           found["node"]: 24, entity: 128})
            checks.update({step["address"]: 24 for step in found["path"]})
            checks.update({p: 8 for p in component_addresses})
            checks.update({address: len(raw) for address, raw in health_anchors.items()})
            checks.update({address: len(raw) for address, raw in resource_anchors.items()})
            checks.update({address: len(raw) for address, raw in cooldown_anchors.items()})
            checks.update({address: len(raw) for address, raw in player_map_anchors.items()
                           if not entity <= address < entity + 128})
            checks[components["position"] + 0x48] = 0x70
            if health is not None:
                checks[record_address] = 128
            if resource_record_raw is not None:
                if resource["kind"] != 3:
                    checks[resource_record_address] = 64
                    checks[resource_clock_address] = 4
            final = take("anchors-after", sorted(checks.items()))
            resource_final = (take("resource-final", [
                (resource_wrapper, 48), (resource_record_address, 64),
                (resource_clock_address, 4)])
                if resource_record_raw is not None and resource["kind"] == 3 else None)
            resource_post_anchors = None
            if resource_final is not None:
                resource_post_anchors = dict(roots)
                resource_post_anchors.update(owner)
                resource_post_anchors[table] = header
                resource_post_anchors.update({step["address"]: bytes.fromhex(step["bytes"])
                                              for step in found["path"]})
                resource_post_anchors[entity + 0x78] = entity_bytes[0x78:0x80]
                resource_post_anchors[entity + 0x18 + position_index] = bytes([
                    entity_bytes[0x18 + position_index]])
                resource_post_anchors[entity + 0x18 + health_index] = bytes([
                    entity_bytes[0x18 + health_index]])
                resource_post_anchors.update(component_raw)
                resource_post_anchors.update(resource_anchors)
            resource_owner_final = (take(
                "resource-owner-final",
                sorted((address, len(raw)) for address, raw in resource_post_anchors.items()))
                if resource_final is not None else None)
            if any(final[address] != raw for address, raw in roots.items()):
                raise ValueError("module-root-changed")
            if any(final[address] != raw for address, raw in cooldown_anchors.items()):
                raise ValueError("cooldown-selector-changed")
            if any((final[entity][address - entity:address - entity + len(raw)]
                    if entity <= address < entity + 128 else final[address]) != raw
                   for address, raw in player_map_anchors.items()):
                raise ValueError("player-ability-context-changed")
            if (final[manager + 0x50] != owner[manager + 0x50] or
                    final[player_system + 0x360] != owner[player_system + 0x360] or
                    final[table] != header or
                    any(final[step["address"]].hex() != step["bytes"] for step in found["path"]) or
                    final[entity][0x78:0x80] != entity_bytes[0x78:0x80] or
                    any(final[entity][0x18 + index] != entity_bytes[0x18 + index]
                        for index in (position_index, health_index)) or
                    any(final[p] != component_raw[p] for p in component_addresses)):
                raise ValueError("player-ownership-anchor-changed")
            transform = position_transform_candidates(
                values[components["position"]], final[components["position"] + 0x48])
            transform["observedAtUtc"] = observation_times["component-values"]
            review["positionTransformCandidate"] = transform
            if health is not None:
                if (any(final[address] != raw for address, raw in health_anchors.items()) or
                        final[record_address][:8] != record_raw[:8]):
                    raise ValueError("health-ownership-anchor-changed")
                health["inputsStable"] = final[record_address][0x48:0x74] == record_raw[0x48:0x74]
                if not health["inputsStable"]:
                    health["status"] = "changed-input-record-candidate"
                health["calculatedHealth"] = (calculate_health(health["fields"], health["gameClock"])
                    if health["inputsStable"] else {"status": "unavailable", "reason": "inputs-changed"})
                review["healthRecordCandidate"] = health
            if resource is not None:
                require_resource_owner_anchors(
                    resource_anchors, {address: final[address] for address in resource_anchors})
                if resource_owner_final is not None:
                    require_resource_owner_anchors(
                        resource_post_anchors, resource_owner_final,
                        "resource-owner-detached-after-final")
                if resource_record_raw is not None:
                    final_resource = resource_final or final
                    if final_resource[resource_record_address][:8] != resource_record_raw[:8]:
                        raise ValueError("resource-record-vtable-changed")
                    if resource["kind"] == 3:
                        transition = coherent_mana_resource_transition(
                            resource_record_raw, resource_wrapper_raw,
                            final_resource[resource_record_address], final_resource[resource_wrapper])
                        final_game_clock = struct.unpack("<f", final_resource[resource_clock_address])[0]
                        if (not math.isfinite(final_game_clock) or final_game_clock < resource["gameClock"]):
                            raise ValueError("mana-transition-game-clock-invalid-or-backward")
                        resource.update({
                            "initialObservedAtUtc": resource["observedAtUtc"],
                            "observedAtUtc": observation_times["resource-final"],
                            "observationIntervalUtc": observation_intervals["resource-final"],
                            "fields": transition["afterFields"],
                            "gameClock": final_game_clock,
                            "inputsStable": True,
                            "mutableInputsChanged": transition["status"] != "unchanged",
                            "mutableTransition": transition,
                            "mutableTransitionLimitations": [
                                "The three final ranges are sequential ReadProcessMemory results, not an atomic snapshot.",
                                "Matching paired revisions and nondecreasing clocks do not exclude an ABA transition between reads.",
                            ],
                        })
                    else:
                        resource["inputsStable"] = (final[resource_record_address][0x18:0x38]
                                                     == resource_record_raw[0x18:0x38])
                        if not resource["inputsStable"]:
                            resource["status"] = "changed-input-record-candidate"
                if resource["kind"] == 4:
                    resource["calculatedEnergy"] = (
                        calculate_energy(resource["fields"], resource["gameClock"])
                        if (resource.get("inputsStable") and resource.get("typeCode") == "0x072B")
                        else {"status": "unavailable", "reason": "untyped-or-changed-energy-inputs"})
                review["resourceRecordCandidate"] = resource
            after = native("inspect-native", "inspect-after")
            after_identity, after_target = inspection_identity(after)
            if after_identity != identity or after_target != target:
                raise ValueError("process-epoch-changed")
            if sha(probe_path.read_bytes()) != probe_sha:
                raise ValueError("probe-source-changed-during-run")
            review.update({"status": "complete", "nativePlayerUnitId": f"u{key:016X}",
                           "manager": f"0x{manager:X}", "playerSystem": f"0x{player_system:X}",
                           "table": f"0x{table:X}", "lookup": found,
                           "componentTable": f"0x{component_table:X}",
                           "componentIndexes": {"position": position_index, "health": health_index},
                           "componentSlots": slots,
                           "components": {k: f"0x{v:X}" for k, v in components.items()},
                           "cachedXyzCandidate": dict(zip(("x", "y", "z"), xyz)),
                           "cachedXyzInputsStable": (final[components["position"] + 0x48][:12]
                                                      == values[components["position"]][0x48:0x54]),
                           "cachedXyzObservedAtUtc": observation_times["component-values"],
                           "completedAtUtc": after.get("capturedAtUtc"),
                           "limitations": ["Sequential reads are not atomic; ABA changes are not excluded.",
                                           "Native self key was not independently correlated with Lua in this run.",
                                           "No Lua query was made; cache passive freshness is unproven.",
                                           "No independent HP/API change or full-game restart was qualified."]})
    except Exception as error:
        review["errorType"] = type(error).__name__
        # Existing session errors are sanitized; don't serialize arbitrary exceptions.
        if isinstance(error, (ValueError, SessionError)):
            review["error"] = str(error)[:200]
        raise
    finally:
        source_stable = (sha(probe_path.read_bytes()) == probe_sha and
                         all(sha(path.read_bytes()) == value for path, value in helper_sources.items()))
        review["sourceStableAtPublish"] = source_stable
        if not source_stable:
            review["status"] = "failed"
            review["errorType"] = "ValueError"
            review["error"] = "probe-source-changed-during-run"
        review["evidence"] = evidence
        with (folder / "review.json").open("xb") as stream:
            stream.write(json.dumps(review, indent=2).encode("utf-8"))
        if not source_stable and sys.exc_info()[0] is None:
            raise ValueError("probe-source-changed-during-run")
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2", "all"), required=True)
    parser.add_argument("--health-record", action="store_true",
                        help="Also capture/type-check the health record and calculate ordinary-value HP candidates.")
    parser.add_argument("--resource-record", action="store_true",
                        help="Capture raw resource records; Energy gets exact-build type/ordinary-value candidates, not production-qualified current.")
    parser.add_argument("--cast-record", action="store_true",
                        help="Capture read-only cast topology candidates; cast semantics remain unqualified.")
    parser.add_argument("--cooldown-roots", action="store_true",
                        help="Read candidate cooldown resolver roots and selector, not cooldown values.")
    parser.add_argument("--cooldown-collections", action="store_true",
                        help="Observe per-thread TLS collection candidates without calling game code.")
    parser.add_argument("--cooldown-cache", action="store_true",
                        help="Inventory one unanimous selected resolver cache and raw dataset-store metadata.")
    parser.add_argument("--ability-seeds", action="store_true",
                        help="Capture up to eight raw ability-record/name/type seeds from the verified cache.")
    parser.add_argument("--ability-key", action="append", type=lambda value: int(value, 0), default=[],
                        help="Select a raw native key for seed capture (up to eight; implies --ability-seeds).")
    parser.add_argument("--player-ability-maps", action="store_true",
                        help="Read raw player-associated ability/cooldown maps and bracketed game clock.")
    parser.add_argument("--ability-localization", action="store_true",
                        help="Follow the default-provider localization route for typed ability name keys.")
    parser.add_argument("--ability-dictionary", action="store_true",
                        help="Explore cached localization-key matches independently of an uninitialized API provider.")
    args = parser.parse_args()
    labs = ("lab1", "lab2") if args.lab == "all" else (args.lab,)
    for lab in labs:
        print(json.dumps(run(lab, health_record=args.health_record,
                             resource_record=args.resource_record,
                             cast_record=args.cast_record,
                             cooldown_roots=args.cooldown_roots,
                             cooldown_collections=args.cooldown_collections,
                             cooldown_cache=args.cooldown_cache,
                             ability_seeds=args.ability_seeds,
                             ability_keys=tuple(args.ability_key),
                             player_ability_maps=args.player_ability_maps,
                             ability_localization=args.ability_localization,
                             ability_dictionary=args.ability_dictionary), indent=2), flush=True)


if __name__ == "__main__":
    main()
