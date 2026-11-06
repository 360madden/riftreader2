"""Bounded passive cast topology candidate, supplied by an identity-pinned caller.

No process opening, game getters, reference-count operations or game input.
The caller owns current PID/start/SHA checks and player-key -> entity lookup.
This module exposes raw child IDs only; it cannot establish cast/timer semantics.
"""
from __future__ import annotations

import struct
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
              "reason": None, "children": [], "isCasting": None,
              "begin": None, "duration": None, "remaining": None,
              "uninterruptible": None}
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
            component = _pointer(struct.unpack("<Q", take(table + slot * 8, 8))[0], 0x298)
            result["component"] = component
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
        for (address, length), expected in tuple(anchors.items()):
            actual = read(address, length)
            if actual != expected:
                raise ValueError("mutable-input-changed")
        result["status"] = status
    except (ValueError, OSError) as exc:
        # Discard partial topology; never present a torn record as a candidate.
        result.update({"status": "unavailable", "reason": str(exc), "children": []})
        result.pop("component", None)
    return result
