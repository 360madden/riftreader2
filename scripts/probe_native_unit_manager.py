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


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


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

def run(lab: str, *, health_record: bool = False, resource_record: bool = False) -> dict:
    if lab not in ("lab1", "lab2"):
        raise ValueError("unknown-lab")
    sys.path.insert(0, str(ROOT))
    from scripts.lab_codex import LabCodex
    from scripts.inventory_passive_rift_sources import ps_literal
    from scripts.vmware_guest_session import SessionError

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
    deadline = time.monotonic() + 240
    review = {"schemaVersion": 1, "lab": lab, "output": str(folder),
              "readerExe": reader, "readerSha256": reader_sha,
              "workflowSha256": sha(workflow_raw), "probeSha256": sha(Path(__file__).read_bytes()),
              "status": "incomplete",
              "qualification": "candidate-only; no passive-freshness or restart qualification"}
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

            roots_ranges = [(MANAGER_RVA, 8), (PLAYER_SYSTEM_RVA, 8),
                            (POSITION_INDEX_RVA, 4), (HEALTH_INDEX_RVA, 4)]
            if health_record or resource_record:
                roots_ranges.append((0x33DC2B0, 8))
            if health_record:
                roots_ranges += [(0x355F430, 8), (0x2C281B8, 8)]
            roots = take("roots", roots_ranges, relative=True)
            manager = pointer(struct.unpack("<Q", roots[base + MANAGER_RVA])[0])
            player_system = pointer(struct.unpack("<Q", roots[base + PLAYER_SYSTEM_RVA])[0])
            position_index = struct.unpack("<i", roots[base + POSITION_INDEX_RVA])[0]
            health_index = struct.unpack("<i", roots[base + HEALTH_INDEX_RVA])[0]
            if not all(0 <= value < 0x60 for value in (position_index, health_index)):
                raise ValueError("component-index-outside-selector-area")
            owner = take("owner", [(manager + 0x50, 8), (player_system + 0x360, 8)])
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
                    game_clock = struct.unpack("<f", resource_capture[clock_owner + 0x18])[0]
                    vtable = pointer(struct.unpack_from("<Q", resource_record_raw)[0], 72)
                    if not base <= vtable < base + identity["moduleSize"] - 0x48:
                        raise ValueError("resource-vtable-outside-exact-module")
                    getter_slot = vtable + 0x40
                    getter_raw = take("resource-type-getter", [(getter_slot, 8)])[getter_slot]
                    getter = struct.unpack("<Q", getter_raw)[0]
                    if not base <= getter < base + identity["moduleSize"]:
                        raise ValueError("resource-type-getter-outside-exact-module")
                    fields = resource_record_fields(kind, resource_record_raw, resource_wrapper_raw)
                    resource.update({
                        "status": ("untyped-record-candidate" if fields["revisionConsistent"]
                                   and math.isfinite(game_clock) else "unavailable"),
                        "reason": (None if fields["revisionConsistent"] and math.isfinite(game_clock)
                                   else "inconsistent-revision-or-game-clock"),
                        "name": fields["name"],
                        "resourceWrapper": f"0x{resource_wrapper:X}",
                        "referenceSlot": f"0x{ref_slot:X}",
                        "record": f"0x{resource_record_address:X}",
                        "recordVtableRva": f"0x{vtable - base:X}",
                        "candidateDescriptorGetterRva": f"0x{getter - base:X}",
                        "fields": fields, "gameClock": game_clock,
                        "observedAtUtc": observation_times["resource-record"],
                        "typeValidation": "NOT PERFORMED; vtable/descriptor/type fingerprints pending",
                    })
                    resource_anchors[resource_wrapper] = resource_wrapper_raw
                    resource_anchors[ref_slot] = ref_raw
                    resource_anchors[getter_slot] = getter_raw

            require_disjoint_records(
                record_address if health is not None else None, resource_record_address)

            # Recheck every ownership anchor after staged reads. This is NOT an
            # atomic snapshot or proof that no transient ABA change occurred.
            checks = {base + rva: length for rva, length in roots_ranges}
            checks.update({manager + 0x50: 8, player_system + 0x360: 8, table: 24,
                           found["node"]: 24, entity: 128})
            checks.update({step["address"]: 24 for step in found["path"]})
            checks.update({p: 8 for p in component_addresses})
            checks.update({address: len(raw) for address, raw in health_anchors.items()})
            checks.update({address: len(raw) for address, raw in resource_anchors.items()})
            if health is not None:
                checks[record_address] = 128
            if resource_record_raw is not None:
                checks[resource_record_address] = 64
            final = take("anchors-after", sorted(checks.items()))
            if any(final[address] != raw for address, raw in roots.items()):
                raise ValueError("module-root-changed")
            if (final[manager + 0x50] != owner[manager + 0x50] or
                    final[player_system + 0x360] != owner[player_system + 0x360] or
                    final[table] != header or
                    any(final[step["address"]].hex() != step["bytes"] for step in found["path"]) or
                    final[entity][0x78:0x80] != entity_bytes[0x78:0x80] or
                    any(final[entity][0x18 + index] != entity_bytes[0x18 + index]
                        for index in (position_index, health_index)) or
                    any(final[p] != component_raw[p] for p in component_addresses)):
                raise ValueError("player-ownership-anchor-changed")
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
                if any(final[address] != raw for address, raw in resource_anchors.items()):
                    raise ValueError("resource-ownership-anchor-changed")
                if resource_record_raw is not None:
                    if final[resource_record_address][:8] != resource_record_raw[:8]:
                        raise ValueError("resource-record-vtable-changed")
                    resource["inputsStable"] = (final[resource_record_address][0x18:0x38]
                                                 == resource_record_raw[0x18:0x38])
                    if not resource["inputsStable"]:
                        resource["status"] = "changed-input-record-candidate"
                review["resourceRecordCandidate"] = resource
            after = native("inspect-native", "inspect-after")
            after_identity, after_target = inspection_identity(after)
            if after_identity != identity or after_target != target:
                raise ValueError("process-epoch-changed")
            review.update({"status": "complete", "nativePlayerUnitId": f"u{key:016X}",
                           "manager": f"0x{manager:X}", "playerSystem": f"0x{player_system:X}",
                           "table": f"0x{table:X}", "lookup": found,
                           "componentTable": f"0x{component_table:X}",
                           "componentIndexes": {"position": position_index, "health": health_index},
                           "componentSlots": slots,
                           "components": {k: f"0x{v:X}" for k, v in components.items()},
                           "cachedXyzCandidate": dict(zip(("x", "y", "z"), xyz)),
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
        review["evidence"] = evidence
        with (folder / "review.json").open("xb") as stream:
            stream.write(json.dumps(review, indent=2).encode("utf-8"))
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2", "all"), required=True)
    parser.add_argument("--health-record", action="store_true",
                        help="Also capture/type-check the health record and calculate ordinary-value HP candidates.")
    parser.add_argument("--resource-record", action="store_true",
                        help="Capture raw, UNTYPECHECKED mana/energy candidates; never calculate trusted values.")
    args = parser.parse_args()
    labs = ("lab1", "lab2") if args.lab == "all" else (args.lab,)
    for lab in labs:
        print(json.dumps(run(lab, health_record=args.health_record,
                             resource_record=args.resource_record), indent=2), flush=True)


if __name__ == "__main__":
    main()
