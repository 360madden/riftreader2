"""Bounded exploration history from already validated beacon packets; no input or reads."""
from copy import deepcopy
import math
import time
from types import SimpleNamespace as NS

from scripts.waypoint_beacon_pose import SOURCE, QUALIFICATION, _target, _utc, _validate_pose
from scripts.waypoint_measurements import measurement, parse_projection_route
from scripts.waypoint_progress import write_json_atomic
from scripts.waypoint_recording import RecordingError, RouteRecorder


class BreadcrumbTrail:
    """Caller validates packet freshness/ownership using read_pose before observe.

    Segments never span unavailable data, epochs or discontinuities. The 20-unit
    segment limit matches the existing recorder/replay format. Snapshot data are
    copies; clearing/stopping never modifies a route or playback checkpoint.
    """
    def __init__(self, *, max_points=2000, max_gap_seconds=3.):
        if type(max_points) is not int or max_points < 2:
            raise ValueError("breadcrumb point cap must be at least two")
        if type(max_gap_seconds) not in (int, float) or not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
            raise ValueError("breadcrumb gap must be positive")
        self.max_points = max_points
        self.max_gap = max_gap_seconds
        self._segments = []
        self._active = False
        self._owner = None
        self._last = None
        self._pending = "started"
        self._reason = "stopped"
        self._discarded = 0

    @staticmethod
    def _owner_key(owner):
        target = _target(owner["target"])
        if not isinstance(owner.get("playerKey"), str) or not owner["playerKey"] or not isinstance(owner.get("sessionId"), str) or not owner["sessionId"]:
            raise ValueError("breadcrumb owner required")
        return target, owner["playerKey"], owner["sessionId"]

    def start(self, owner):
        key = self._owner_key(owner)
        if self._active and key == self._owner:
            return self.snapshot()
        self._owner = key
        self._active = True
        self._pending = "started"
        self._reason = "recording"
        # Keep the last sample across stop/start to reject the same cached packet.
        return self.snapshot()

    def unavailable(self, reason):
        self._reason = str(reason)[:160] or "unavailable"
        self._pending = self._reason
        return self.snapshot()

    def stop(self):
        self._active = False
        self._reason = "stopped"
        self._pending = "stopped"
        return self.snapshot()

    def clear(self):
        self._segments.clear()
        self._discarded = 0
        self._pending = "cleared"
        return self.snapshot()

    def observe(self, packet):
        if not self._active:
            return False
        try:
            key = self._owner_key(packet)
            if packet.get("status") != "fresh" or packet.get("source") != SOURCE or packet.get("qualification") != QUALIFICATION:
                raise ValueError("breadcrumb requires validated fresh beacon pose")
            _validate_pose(packet)
            sequence = packet["sequence"]
            if type(sequence) is not int or sequence <= 0:
                raise ValueError("breadcrumb sequence invalid")
        except (ValueError, TypeError, KeyError) as exc:
            self.unavailable(str(exc))
            return False
        last = self._last
        reason = self._pending
        if last and key == last["key"]:
            # Neither sequence nor either source clock can be reused/regressed.
            if sequence <= last["sequence"] or packet["acquiredMonotonic"] <= last["acquiredMonotonic"] or _utc(packet["sampledAtUtc"]) <= _utc(last["sampledAtUtc"]):
                return False
            dt = packet["acquiredMonotonic"] - last["acquiredMonotonic"]
            if dt > self.max_gap:
                reason = "sample-gap"
            elif math.dist(tuple(packet["position"][a] for a in "xyz"), tuple(last["position"][a] for a in "xyz")) > 12 * dt + .20:
                reason = "teleport-or-discontinuity"
        elif last:
            reason = "owner-or-session-change"
        if key != self._owner:
            reason = "owner-or-session-change"
        self._owner = key
        point = dict(packet["position"], bearing=packet["bearing"], acquired=packet["acquiredMonotonic"],
                     sampledAtUtc=packet["sampledAtUtc"], sequence=sequence, source=packet["source"],
                     qualification=packet["qualification"])
        segment = self._segments[-1] if self._segments and not reason else None
        if segment:
            previous = segment["points"][-1]
            heartbeat = min(1., self.max_gap / 2)
            if (all(point[a] == previous[a] for a in "xyz")
                    and point["acquired"] - previous["acquired"] < heartbeat):
                # A fresh unchanged sample advances admission clocks, never the
                # original observation's timestamp. Keep periodic real samples
                # so later recorder export has no artificial timing gap.
                self._last = dict(deepcopy(packet), key=key)
                self._reason = "recording"
                return False
            if point["acquired"] - previous["acquired"] > self.max_gap:
                # A slower subsequent poll can exceed the retained heartbeat
                # gap despite continuous input. Keep the final skipped sample
                # (with its original clocks) before the new point.
                bridge = dict(last["position"], bearing=last["bearing"],
                    acquired=last["acquiredMonotonic"], sampledAtUtc=last["sampledAtUtc"],
                    sequence=last["sequence"], source=last["source"], qualification=last["qualification"])
                segment["points"].append(bridge)
                previous = bridge
            distance = math.hypot(point["x"] - previous["x"], point["z"] - previous["z"])
            if segment["observedPathLength"] + distance > 20:
                # The boundary is an actual observed point, never interpolation.
                reason = "route-length-limit"
                segment = self._new_segment(key, reason)
                if distance <= 20:
                    segment["points"].append(deepcopy(previous))
                else:
                    distance = 0.
            segment["observedPathLength"] += distance
        else:
            segment = self._new_segment(key, reason or "started")
        segment["points"].append(point)
        self._last = dict(deepcopy(packet), key=key)
        self._pending = None
        self._reason = "recording"
        self._trim()
        return True

    def _new_segment(self, key, reason):
        target, player, session = key
        identity = dict(machine=target["hostName"], gameBuildSha256=target["executableSha256"], unitKey=player,
                        processId=target["processId"], processStartUtcTicks=target["processStartUtcTicks"],
                        executablePath=target["executablePath"], hwnd=target["hwnd"], sessionId=session)
        segment = dict(identity=identity, reason=reason, points=[], observedPathLength=0.)
        self._segments.append(segment)
        return segment

    def _trim(self):
        excess = sum(len(s["points"]) for s in self._segments) - self.max_points
        while excess > 0:
            segment = self._segments[0]
            count = min(excess, len(segment["points"]))
            del segment["points"][:count]
            excess -= count
            self._discarded += count
            if not segment["points"]:
                self._segments.pop(0)
            else:
                segment["reason"] = "retention-limit"
                segment["observedPathLength"] = sum(math.hypot(b["x"]-a["x"], b["z"]-a["z"])
                    for a, b in zip(segment["points"], segment["points"][1:]))

    def snapshot(self):
        return dict(active=self._active, reason=self._reason, segments=deepcopy(self._segments),
                    pointCount=sum(len(s["points"]) for s in self._segments), discardedPointCount=self._discarded)

    def export_segment(self, index=-1):
        """Export exactly the chosen retained segment; never bridge other segments."""
        if not self._segments:
            raise RecordingError("Breadcrumb trail has no segment")
        segment = self._segments[index]
        points = segment["points"]
        # Reuse the recorder's planar corner/reversal simplification and limits.
        # Shift only its transient monotonic clock so historical samples can be
        # exported later. Saved receipts retain the original source clocks.
        offset = time.monotonic() - points[-1]["acquired"]
        age = points[-1]["acquired"] - points[0]["acquired"] + 10
        recorder = RouteRecorder(segment["identity"], max_gap_seconds=self.max_gap, max_age_seconds=age)
        # Add mandatory 3D corners; the reused recorder simplifies in XZ only.
        vertical_boundaries = set()
        stack = [(0, len(points)-1)]
        while stack:
            first, last = stack.pop()
            if last <= first+1:
                continue
            a, b = points[first], points[last]
            vector = [b[k]-a[k] for k in "xyz"]
            length2 = sum(v*v for v in vector)
            errors = []
            for i in range(first+1, last):
                p = points[i]
                fraction = max(0., min(1., sum((p[k]-a[k])*v for k,v in zip("xyz", vector))/length2)) if length2 else 0.
                error = math.dist(tuple(p[k] for k in "xyz"), tuple(a[k]+fraction*v for k,v in zip("xyz",vector)))
                errors.append((error,i))
            error, index = max(errors)
            if error > .05:
                vertical_boundaries.add(index)
                stack.extend(((first,index),(index,last)))
        for i, p in enumerate(points):
            recorder.observe(NS(position=NS(**{a:p[a] for a in "xyz"}), bearing=p["bearing"],
                                acquired=p["acquired"]+offset, source=p["source"]), boundary=i in vertical_boundaries)
        simplified = recorder.finish()
        # Existing measured-point format preserves exact per-point source times.
        retained_indices = {0, len(points)-1} | vertical_boundaries
        cursor = 0
        for row, height in zip(simplified["waypoints"], simplified["heights"]):
            while cursor < len(points):
                p = points[cursor]
                cursor += 1
                if all(abs(p[a]-v) <= 1e-6 for a,v in zip("xyz", (row[1], height, row[2]))):
                    retained_indices.add(cursor-1)
                    break
            else:
                raise RecordingError("Breadcrumb retained-point provenance missing")
        retained = [points[i] for i in sorted(retained_indices)]
        # The recorder deduplicates XZ; restore genuine measured vertical corners.
        if len(retained) > 20:
            raise RecordingError("Breadcrumb segment requires more than 20 genuine waypoints")
        document = dict(waypoints=[[f"Trail {i+1}", round(p["x"],6), round(p["z"],6)]
                                   for i,p in enumerate(retained)],
                        heights=[round(p["y"],6) for p in retained], pointMeasurements=[])
        for row, height, p in zip(document["waypoints"], document["heights"], retained):
            receipt = measurement(dict(x=row[1], y=height, z=row[2]), segment["identity"], p["source"], p["sampledAtUtc"])
            receipt.update(sourceTimeKind="beacon-sample", acquiredMonotonic=p["acquired"], sequence=p["sequence"], qualification=p["qualification"])
            document["pointMeasurements"].append(receipt)
        parse_projection_route(document)
        return document

    def save_segment(self, path, index=-1):
        document = self.export_segment(index)
        write_json_atomic(path, document)
        return document
