"""Read-only paced native poses for passive route recording."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from scripts import physical_rift
from scripts.movement_controller import Position
from scripts.physical_waypoints import Snapshot, WaypointError, finite, capture_reason


def observe_batch(adapter, *, samples=8, interval_ms=100) -> list[Snapshot]:
    """Return every fresh validated pose in one burst; never send game input.

    Callers importing this from physical_waypoints must import it locally after
    that module has initialized. Sources identify the retained native report;
    list order identifies its observations without inventing per-row files.
    """
    if (type(samples) is not int or not 1 <= samples <= 30
            or type(interval_ms) is not int or not 0 <= interval_ms <= 2000):
        raise WaypointError("Invalid observation burst samples or interval")
    capture = physical_rift.read_native(adapter.selection, "facing", samples=samples,
                                        interval_ms=interval_ms, include_target=False)
    if capture.get("status") != "complete":
        raise WaypointError(capture_reason(capture))
    try:
        source = capture["nativeOutput"]
        report = json.loads(Path(source).read_text(encoding="utf-8"))
        identity = report["identity"]
        target = adapter.target
        if (identity.get("processId") != target["processId"]
                or str(identity.get("processStartUtcTicks")) != str(target["processStartUtcTicks"])
                or str(identity.get("executableSha256", "")).casefold()
                != target["executableSha256"].casefold()):
            raise ValueError("Observation process/build changed")
        # Full reducer proves ordering and stable native owners across the burst.
        physical_rift._native_values("facing", report)
        rows = report["observations"]
        if len(rows) != samples:
            raise ValueError("Incomplete observation burst")
        now, monotonic_now = datetime.now(timezone.utc), time.monotonic()
        result = []
        for row in rows:
            single = dict(report, observations=[row], observation=row,
                          requestedSamples=1, completedSamples=1)
            value = physical_rift._native_values("facing", single)
            sampled = datetime.fromisoformat(value["sampledAtUtc"].replace("Z", "+00:00"))
            age = (now - sampled).total_seconds()
            if not -.1 <= age <= 2 or value["playerKey"] != adapter.unit_key:
                raise ValueError("Stale observation or player changed")
            if value.get("positionSource") != "entity-owned-position-component+0x48":
                raise ValueError("Entity-owned position unavailable")
            point = value["positionXYZCandidate"]
            result.append(Snapshot(Position(*(finite(point[k]) for k in ("x", "y", "z"))),
                                   finite(value["bodyBearingDegreesCandidate"]),
                                   monotonic_now - max(0, age), source))
        return result
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise WaypointError(f"Invalid native observation burst: {exc}") from exc
