"""Offline comparison of exact-build native zone and nonce-bound RR2R1 Lua zone.

This never reads a live game, binds an addon, or treats sequential candidates
as an atomic world/instance identity. The caller must supply actual retained
native and RR2R1 C# snapshot reports from the same process epoch.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.compare_physical_player_context_pair import load
from scripts.inspect_typed_resource import inspect, require_session_id


def require(ok, reason):
    if not ok:
        raise ValueError("native-lua-zone-" + reason)


def _instant(value, label):
    try:
        return physical_rift._utc_tick_order_key(value)
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise ValueError("native-lua-zone-" + label + "-invalid") from exc


def _interval(start, end, label):
    first, last = _instant(start, label), _instant(end, label)
    require(first <= last, label + "-reversed")
    return first, last


def compare(native_source, reference_source, nonce, *, max_gap_seconds=15.0):
    require(type(max_gap_seconds) in (int, float)
            and math.isfinite(max_gap_seconds) and 0 <= max_gap_seconds <= 30,
            "invalid-gap-budget")
    require_session_id(nonce)
    native_path, snapshot_path = Path(native_source), Path(reference_source)
    for path in (native_path, snapshot_path):
        require(path.is_file() and not path.is_symlink()
                and 0 < path.stat().st_size <= 8_000_000, "source-unavailable")
    native, native_hash = load(native_path)
    values = physical_rift._native_values("zone-context", native)
    require(values["status"] == "available-candidate", "native-zone-unavailable")
    observation = native["observation"]
    native_identity = observation["identity"]

    reference = inspect(snapshot_path, "zone", nonce)
    candidate = reference["selected"]
    api_identity = reference["identity"]
    require(isinstance(api_identity, dict)
            and api_identity.get("processId") == native_identity["processId"]
            and str(api_identity.get("processStartUtcTicks")) ==
                str(native_identity["processStartUtcTicks"])
            and str(api_identity.get("executableSha256", "")).upper() ==
                str(native_identity["executableSha256"]).upper(),
            "process-epoch-or-build-mismatch")
    for field in ("moduleBaseAddress", "moduleSize", "executablePath"):
        if field in api_identity:
            require(api_identity[field] == native_identity[field],
                    "module-identity-mismatch")
    self_key = values["selfKey"]
    require(candidate.get("playerUnitId") == f"u{int(self_key):016X}",
            "player-identity-mismatch")
    api_zone = candidate["current"]
    require(api_zone["status"] == "ok" and
            isinstance(api_zone.get("value"), str), "lua-zone-unavailable")
    lua_zone_id = api_zone["value"]
    native_zone_id = values["zoneIdCandidate"]
    require(re.fullmatch(r"z[0-9A-F]{16}", lua_zone_id) is not None,
            "lua-zone-not-canonical-id")
    require(re.fullmatch(r"z[0-9A-F]{16}", native_zone_id) is not None,
            "native-zone-not-canonical-id")

    n0, n1 = _interval(values["startedAtUtc"], values["sampledAtUtc"], "native-time")
    r0, r1 = _interval(reference["startedAtUtc"], reference["completedAtUtc"],
                       "reference-time")
    # _utc_tick_order_key returns (UTC datetime, 100 ns remainder), not a
    # scalar. Subtract its components exactly, retaining the seventh digit.
    later, earlier = max(n0, r0), min(n1, r1)
    gap = 0
    if later > earlier:
        span = later[0] - earlier[0]
        gap = ((span.days * 86_400 + span.seconds) * 10_000_000
               + span.microseconds * 10 + later[1] - earlier[1])
    require(gap <= round(max_gap_seconds * 10_000_000), "sample-gap-too-large")
    return {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-native-lua-zone-correlation/1",
        "status": ("matching-candidates" if lua_zone_id == native_zone_id
                   else "mismatched-candidates"),
        "nativeZoneIdCandidate": native_zone_id,
        "luaZoneIdCandidate": lua_zone_id,
        "worldInstanceStatus": "unavailable",
        "playerUnitId": candidate["playerUnitId"],
        "processId": native_identity["processId"],
        "processStartUtcTicks": str(native_identity["processStartUtcTicks"]),
        "executableSha256": str(native_identity["executableSha256"]).upper(),
        "nativeStartedAtUtc": values["startedAtUtc"],
        "nativeCompletedAtUtc": values["sampledAtUtc"],
        "referenceStartedAtUtc": reference["startedAtUtc"],
        "referenceCompletedAtUtc": reference["completedAtUtc"],
        "sampleGapMilliseconds": round(gap / 10_000, 3),
        "referenceSessionId": nonce,
        "referenceEpoch": candidate["epoch"],
        "referenceSequence": candidate["sequence"],
        "referenceFrameTimeCandidate": candidate["frameTime"],
        "nativeSourceSha256": native_hash,
        "referenceSnapshotSha256": reference["snapshotSha256"],
        "referenceWireSha256": candidate["wireSha256"],
        "qualification": (
            "Two individually SHA-checked, same-PID/start/build/player candidate "
            "sources within a bounded host capture window. RR2R1 is Lua API "
            "reference, not an atomic native/API sample; nonce is not independent "
            "authentication. Zone transition, uninterrupted freshness, world "
            "instance identity and navigation authority remain unverified."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-zone", type=Path, required=True)
    parser.add_argument("--reference-snapshot", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--max-gap-seconds", type=float, default=15.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            require(not args.output.exists() and not args.output.is_symlink(),
                    "output-exists")
        result = compare(args.native_zone, args.reference_snapshot,
                         args.session_id, max_gap_seconds=args.max_gap_seconds)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(result, handle, indent=2, allow_nan=False)
                handle.write("\n")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
