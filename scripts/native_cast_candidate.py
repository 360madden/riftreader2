"""Bounded passive cast topology candidate, supplied by an identity-pinned caller.

No process opening, game getters, reference-count operations or game input.
The caller owns current PID/start/SHA checks and player-key -> entity lookup.
This module exposes raw child IDs and an unknown DWORD; it cannot establish cast/timer semantics.
"""
from __future__ import annotations

import struct
import math
from typing import Callable

BUILD_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
SELECTOR_RVA = 0x2F57260
MAX_USER = 0x7FFFFFFFFFFF


def _pointer(address: int, length: int = 8) -> int:
    if (type(address) is not int or address < 0x10000 or address % 8
            or address + length - 1 > MAX_USER):
        raise ValueError("invalid-user-pointer")
    return address


def read_cast_topology(read: Callable[[int, int], bytes], *, module_base: int,
                       entity: int, build_sha: str) -> dict:
    """Read a candidate topology and recheck every consumed anchor.

    `read` must read only the already-validated, pinned process epoch. Entity
    ownership must be resolved/rechecked by the shared player lookup caller.
    Returning equal bytes rules out observed tearing, not ABA changes or stale
    game caches. Expected address/read failures become explicit unavailable data.
    """
    result = {"source": "native-memory", "qualification": "static-topology-candidate",
              "buildSha256": build_sha, "status": "unavailable",
              "reason": None, "children": [], "rawComponentDword2B8": None, "isCasting": None,
              "begin": None, "duration": None, "remaining": None,
              "uninterruptible": None,
              "durationCandidate": {"status": "unavailable", "reason": "not-observed",
                                    "beginRaw": None, "durationRaw": None}}
    if build_sha != BUILD_SHA:
        result["reason"] = "unsupported-build"
        return result
    anchors: dict[tuple[int, int], bytes] = {}

    def take(address: int, length: int) -> bytes:
        if address < 0x10000 or address + length - 1 > MAX_USER:
            raise ValueError("invalid-read-range")
        data = read(address, length)
        if not isinstance(data, bytes) or len(data) != length:
            raise ValueError("short-or-invalid-read")
        key = (address, length)
        if key in anchors and anchors[key] != data:
            raise ValueError("mutable-input-changed")
        anchors[key] = data
        return data

    try:
        _pointer(module_base)
        _pointer(entity, 128)
        index = struct.unpack("<i", take(module_base + SELECTOR_RVA, 4))[0]
        if not 0 <= index < 0x60:
            raise ValueError("component-index-outside-selector-area")
        slot = take(entity + 0x18 + index, 1)[0]
        result.update({"selectorIndex": index, "entity": entity, "slot": slot})
        if slot == 0xFF:
            status = "candidate-component-absent"
        else:
            table = _pointer(struct.unpack("<Q", take(entity + 0x78, 8))[0])
            component = _pointer(struct.unpack("<Q", take(table + slot * 8, 8))[0], 0x2BC)
            result["component"] = component
            # Copied by the producer before its child-ID gate; meaning unknown.
            result["rawComponentDword2B8"] = struct.unpack(
                "<I", take(component + 0x2B8, 4))[0]
            for offset in (0x280, 0x290):
                child = struct.unpack("<Q", take(component + offset, 8))[0]
                child_id = None
                if child:
                    _pointer(child, 12)
                    child_id = struct.unpack("<I", take(child + 8, 4))[0]
                result["children"].append({"offset": offset, "address": child,
                                           "rawId": child_id})
            ids = [child["rawId"] for child in result["children"]]
            status = ("candidate-nonzero-child" if any(ids)
                      else "candidate-no-nonzero-child")
            # Both controls are read even with null children, to reproduce the
            # producer's reference-selection guards without invoking it.
            controls = [struct.unpack("<Q", take(component + offset, 8))[0]
                        for offset in (0x288, 0x298)]
            candidate = result["durationCandidate"]
            if not any(ids):
                candidate["reason"] = "no-nonzero-child-id"
            else:
                selected = next(((child["address"], n) for n, child in
                                 enumerate(result["children"])
                                 if controls[n] and child["address"]), None)
                if selected is None:
                    candidate["reason"] = "no-selected-child"
                else:
                    child, branch = selected
                    try:
                        guard = _pointer(struct.unpack("<Q", take(child + 0x10, 8))[0], 0xC9)
                        if take(guard + 0xC8, 1) != b"\x00":
                            raise ValueError("producer-guard-set")
                        duration_object = struct.unpack("<Q", take(child + (0x20 if branch == 0 else 0x28), 8))[0]
                        if not duration_object:
                            raise ValueError("duration-object-absent")
                        _pointer(duration_object, 0x1C)
                        vtable = struct.unpack("<Q", take(duration_object, 8))[0]
                        if vtable != module_base + 0x26AA0E0:
                            raise ValueError("unsupported-duration-vtable")
                        if struct.unpack("<Q", take(vtable + 8, 8))[0] != module_base + 0x09D680:
                            raise ValueError("unsupported-duration-slot")
                        begin = struct.unpack("<f", take(child + (0x30 if branch == 0 else 0x34), 4))[0]
                        duration = struct.unpack("<f", take(duration_object + 0x18, 4))[0]
                        if not math.isfinite(begin) or not math.isfinite(duration):
                            raise ValueError("nonfinite-duration-input")
                        candidate.update(status="raw-fingerprint-candidate", reason=None,
                                         beginRaw=begin, durationRaw=duration)
                    except (ValueError, OSError) as exc:
                        candidate["reason"] = str(exc)
        for (address, length), expected in tuple(anchors.items()):
            actual = read(address, length)
            if actual != expected:
                raise ValueError("mutable-input-changed")
        result["status"] = status
    except (ValueError, OSError) as exc:
        # Discard partial topology; never present a torn record as a candidate.
        result.update({"status": "unavailable", "reason": str(exc), "children": [],
                       "rawComponentDword2B8": None,
                       "durationCandidate": {"status": "unavailable", "reason": str(exc),
                                             "beginRaw": None, "durationRaw": None}})
        result.pop("component", None)
    return result
