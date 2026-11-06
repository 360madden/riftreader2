"""Offline reconstruction of the current-build cooldown field arithmetic.

The caller supplies already-observed float inputs.  This module opens no process,
locates no owner, invokes no game function, and does not claim cooldown semantics.
It mirrors only the instruction-derived float32 calculations that are currently
understood for the pinned RIFT build.
"""
from __future__ import annotations

import math
import struct


BUILD_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"


def _f32(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}-not-numeric")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name}-outside-float32") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name}-not-finite")
    try:
        result = struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError as exc:
        raise ValueError(f"{name}-outside-float32") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name}-outside-float32")
    return result


def _sub(left: float, right: float, name: str) -> float:
    return _f32(left - right, name)


def reconstruct_cooldown_fields(*, timer: float, duration: float,
                                game_clock: float, remaining_floor: float,
                                build_sha: str) -> dict:
    """Reconstruct only the statically verified field-builder arithmetic.

    `timer`, `duration`, `game_clock`, and `remaining_floor` are raw candidate
    inputs supplied by a separate, identity-pinned acquisition.  Their ownership,
    units, and meanings are not established here.  The positive expired branch
    and paused predicate remain unknown and therefore stay null.
    """
    result = {
        "source": "offline-native-arithmetic",
        "qualification": "static-arithmetic-candidate",
        "buildSha256": build_sha,
        "status": "unavailable",
        "reason": None,
        "currentCooldownBegin": None,
        "currentCooldownDuration": None,
        "currentCooldownExpired": None,
        "currentCooldownRemaining": None,
        "currentCooldownPaused": None,
    }
    if build_sha != BUILD_SHA:
        result["reason"] = "unsupported-build"
        return result
    try:
        timer32 = _f32(timer, "timer")
        duration32 = _f32(duration, "duration")
        clock32 = _f32(game_clock, "game-clock")
        floor32 = _f32(remaining_floor, "remaining-floor")
        begin = _sub(timer32, duration32, "begin")
        clock_delta = _sub(timer32, clock32, "clock-delta")
    except ValueError as exc:
        result["reason"] = str(exc)
        return result

    result.update({
        "status": "candidate-arithmetic",
        "inputs": {
            "timer": timer32,
            "duration": duration32,
            "gameClock": clock32,
            "remainingFloor": floor32,
        },
        "currentCooldownBegin": begin,
        "currentCooldownDuration": duration32,
        "currentCooldownExpired": _f32(-clock_delta, "expired") if clock_delta < 0 else None,
        "currentCooldownRemaining": max(clock_delta, floor32),
        "clockDelta": clock_delta,
    })
    return result

