"""Calculate candidate turn rates from saved bounded pulses and native body bearings."""

import math

from scripts.compare_physical_player_context_pair import load
from scripts.physical_move_key_calibration import verified_single_key_pulse
from scripts.physical_rift import _facing_entity_position, _native_values, _utc_tick_order_key
from scripts.waypoint_heading import heading_error


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def settled_facing(path):
    report, digest = load(path)
    projected = _native_values("facing", report)
    rows = report["observations"]
    bearings = projected["bodyBearingSeriesDegreesCandidate"]
    points = [_facing_entity_position(row) for row in rows]
    require(len(rows) >= 2 and all(point is not None for point in points)
            and all(bearing is not None for bearing in bearings), "turn-basis-facing-burst-required")
    positions = [tuple(point[axis] for axis in ("x", "y", "z")) for point in points]
    require(all(abs(heading_error(bearing, bearings[-1])) <= .5 for bearing in bearings)
            and all(math.dist(point, positions[-1]) <= .08 for point in positions),
            "turn-basis-facing-burst-unsettled")
    return {"identity": report["identity"], "sha256": digest,
            "owner": tuple(rows[-1][key] for key in ("playerKeyDecimal", "playerEntityDecimal", "playerSystemDecimal")),
            "start": _utc_tick_order_key(rows[0]["startedAtUtc"]),
            "end": _utc_tick_order_key(rows[-1]["completedAtUtc"]),
            "completedAtUtc": rows[-1]["completedAtUtc"],
            "bearing": bearings[-1], "position": positions[-1]}


def measure_turn(key, paths, basis_identity):
    before_path, pulse_path, after_path = paths
    pulse, duration = verified_single_key_pulse(pulse_path, {key})
    hold = duration["observedHoldMilliseconds"]
    # At the accepted upper rate of 0.5 degrees/ms, 300 ms stays below the 180-degree alias.
    require(duration["holdMeasurementSource"] == "sendinput-keydown-keyup-bounded-midpoint"
            and duration["holdBoundsCandidate"]["maximumMillisecondsCandidate"] <= 300,
            "turn-basis-bounded-hold-required")
    require(pulse["machine"].casefold() == basis_identity["machine"].casefold()
            and pulse["processId"] == basis_identity["processId"]
            and str(pulse["processStartUtcTicks"]) == basis_identity["processStartUtcTicks"]
            and pulse["executableSha256"].casefold() == basis_identity["gameBuildSha256"].casefold(),
            "turn-basis-pulse-identity-mismatch")

    before, after = settled_facing(before_path), settled_facing(after_path)
    identity = before["identity"]
    require(before["sha256"] != after["sha256"] and identity == after["identity"]
            and isinstance(identity, dict) and type(identity.get("processId")) is int
            and identity["processId"] == pulse["processId"]
            and type(identity.get("processStartUtcTicks")) is int
            and identity.get("processStartUtcTicks") == pulse["processStartUtcTicks"]
            and str(identity.get("executableSha256", "")).casefold() == pulse["executableSha256"].casefold()
            and before["owner"] == after["owner"] and before["owner"][0] == basis_identity["unitKey"],
            "turn-basis-facing-identity-mismatch")
    timing = pulse["inputCallTiming"]
    start = _utc_tick_order_key(timing["startedAtUtc"])
    end = _utc_tick_order_key(timing["completedAtUtc"])
    require(before["end"] <= start < end <= after["start"]
            and (after["start"][0] - before["end"][0]).total_seconds() <= 10,
            "turn-basis-facing-pulse-order-invalid")
    require(math.dist(before["position"], after["position"]) <= .08, "turn-basis-position-drift")

    delta = heading_error(after["bearing"], before["bearing"])
    rate = delta / hold
    direction = 1 if key == "a" else -1
    require(.05 <= direction * rate <= .5, "turn-basis-rate-unqualified")
    candidate = {"degreesPerMillisecondCandidate": rate, "bodyBearingDeltaDegreesCandidate": delta,
                 "observedHoldMidpointMsCandidate": hold, "pulseSha256": duration["sourceReceiptSha256"],
                 "beforePoseSha256": before["sha256"], "afterPoseSha256": after["sha256"]}
    return candidate, (before["start"], start, end, after["end"])


def turn_calibration(basis_identity, sources, *, not_before=None):
    require(set(sources) == {"a", "d"}, "turn-basis-both-keys-required")
    rates = {}
    intervals = []
    for key in ("a", "d"):
        rates[key], interval = measure_turn(key, sources[key], basis_identity)
        intervals.append(interval)
    first, second = sorted(intervals, key=lambda interval: interval[1])
    require(first[2] <= second[0] and first[3] <= second[1], "turn-basis-overlapping-trials")
    require(not_before is None or first[1] >= not_before, "turn-basis-measurement-predates-preflight")
    return {"method": "independent-exact-build-facing-samples-and-bounded-A-D-input-receipts",
            "turnResponseQualified": False, "headingQualified": False, "rates": rates}
