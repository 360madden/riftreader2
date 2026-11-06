"""Exact-build kind-3 Mana arithmetic for a caller-verified native record.

This module never opens a process or invokes a game getter.  The caller must
pin the process/build/player owner, prove the kind-3 record's exact descriptor
fingerprint, and bracket the supplied record/cache bytes.  Until that separate
type proof exists, the result stays explicitly unavailable.
"""
from __future__ import annotations

import math
import struct


BUILD_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
MANA_KIND = 3
MANA_TYPE = 0x072A
FORMULA_RVA = 0x133DD10
_NATIVE_RATE_SCALE = struct.unpack("<f", bytes.fromhex("0ad723bc"))[0]


def _f32(value: float | int) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def calculate_mana_candidate(record: bytes, wrapper: bytes, game_clock: float,
                             *, build_sha: str, resource_kind: int,
                             verified_type_code: int | None) -> dict:
    """Replay the ordinary finite-value path of native RVA ``0x133DD10``.

    ``verified_type_code`` must come from a separately bracketed, exact-build
    descriptor/vtable check.  Supplying the resolver's expected constant alone
    is not type proof and must be represented as ``None``.
    """
    result = {
        "status": "unavailable",
        "reason": None,
        "current": None,
        "maximum": None,
        "source": "native-record-replay",
        "qualification": "candidate-only; descriptor/semantics/freshness/restart-unverified",
        "formulaRva": f"0x{FORMULA_RVA:X}",
    }
    if build_sha != BUILD_SHA:
        result["reason"] = "unsupported-build"
        return result
    if type(resource_kind) is not int or resource_kind != MANA_KIND:
        result["reason"] = "not-mana-kind-three"
        return result
    if type(verified_type_code) is not int or verified_type_code != MANA_TYPE:
        result["reason"] = "mana-type-fingerprint-unverified"
        return result
    if not isinstance(record, bytes) or len(record) != 64 or not isinstance(wrapper, bytes) or len(wrapper) != 48:
        result["reason"] = "mana-input-size"
        return result

    rate = struct.unpack_from("<i", record, 0x18)[0]
    baseline = struct.unpack_from("<i", record, 0x1C)[0]
    revision = struct.unpack_from("<i", record, 0x20)[0]
    maximum = struct.unpack_from("<i", record, 0x24)[0]
    cached_revision = struct.unpack_from("<i", wrapper, 0x1C)[0]
    cached_clock = struct.unpack_from("<f", wrapper, 0x24)[0]
    clock_valid = type(game_clock) in (int, float)
    if clock_valid:
        try:
            clock_valid = math.isfinite(game_clock)
        except (OverflowError, TypeError, ValueError):
            clock_valid = False
    inputs = {
        "baseRaw": baseline,
        "maximumRaw": maximum,
        "rateRaw": rate,
        "recordRevision": revision,
        "wrapperRevision": cached_revision,
        "wrapperClock": cached_clock if math.isfinite(cached_clock) else None,
        "gameClock": game_clock if clock_valid else None,
        "verifiedTypeCode": f"0x{verified_type_code:04X}",
    }
    result["inputs"] = inputs
    if revision != cached_revision:
        result["reason"] = "revision-mismatch-needs-native-cache-write"
        return result
    if baseline < 0 or maximum <= 0:
        result["reason"] = "outside-normal-integer-domain"
        return result
    if not clock_valid or not math.isfinite(cached_clock):
        result["reason"] = "invalid-float-input"
        return result
    try:
        elapsed = _f32(_f32(game_clock) - _f32(cached_clock))
        scaled_rate = _f32(_f32(rate) * _NATIVE_RATE_SCALE)
        product = _f32(scaled_rate * elapsed)
    except (OverflowError, struct.error):
        result["reason"] = "float32-overflow"
        return result
    if not math.isfinite(elapsed) or elapsed < 0 or elapsed >= 2147483648:
        result["reason"] = "clock-delta-outside-normal-domain"
        return result
    if not math.isfinite(product) or product <= -(1 << 31) or product >= (1 << 31) - 1:
        result["reason"] = "int32-conversion-overflow-or-sentinel"
        return result
    adjustment = math.trunc(product)
    adjusted = baseline - adjustment
    if adjusted < -(1 << 31) or adjusted >= 1 << 31:
        result["reason"] = "signed32-subtraction-overflow"
        return result
    result.update({
        "status": "calculated-candidate",
        "reason": None,
        "current": min(max(adjusted, 0), maximum),
        "maximum": maximum,
        "elapsedSeconds": elapsed,
        "truncatedRateAdjustment": adjustment,
    })
    return result
