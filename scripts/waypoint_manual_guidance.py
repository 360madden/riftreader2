"""Passive ordered route guidance from caller-validated beacon pose packets.

The caller must use waypoint_beacon_pose.read_pose for identity and age validation
before observe(), and call unavailable() on any read failure. This module has no
file, native reader, playback checkpoint, or input dependencies.
"""
from copy import deepcopy
from datetime import datetime
import math
from scripts.waypoint_height_context import HEIGHT_CAUTION_UNITS


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("guidance requires finite numeric coordinates and times")
    return float(value)


def _owner(packet):
    target = deepcopy(packet["target"])
    for key in ("hostName", "executablePath", "executableSha256"):
        target[key] = target[key].casefold()
    if not packet["playerKey"] or not packet["sessionId"]:
        raise ValueError("guidance requires player and beacon session")
    return dict(target=target, playerKey=packet["playerKey"], sessionId=packet["sessionId"])


class ManualGuidance:
    """Advance only the current original route index after sustained proximity.

    points are [name, x, z] rows. start_index is an original zero-based route
    index; earlier points in the selected direction are excluded, not completed.
    owner contains target, playerKey and sessionId from the owned beacon packet.
    A stopped owner/session cannot resume without an explicit begin().
    """

    def __init__(self, *, radius=.6, confirmation_seconds=.2, max_sample_gap=1.):
        self.radius = _number(radius)
        self.confirmation_seconds = _number(confirmation_seconds)
        self.max_sample_gap = _number(max_sample_gap)
        if (self.radius <= 0 or self.confirmation_seconds <= 0
                or self.max_sample_gap < self.confirmation_seconds):
            raise ValueError("guidance radius/timing configuration is invalid")
        self._status = "stopped"
        self._reason = "not-started"
        self._points = []
        self._order = []
        self._completed = []
        self._cursor = 0
        self._direction = None
        self._distance = None
        self._owner = None
        self._last = None
        self._inside_since = None
        self._measured_heights = []
        self._height_separation = None
        self._height_warning = False

    @property
    def status(self):
        return self._status

    def begin(self, points, direction="forward", start_index=0, owner=None, *, measured_heights=None):
        if direction not in ("forward", "reverse"):
            raise ValueError("guidance direction must be forward or reverse")
        if not points or type(start_index) is not int or not 0 <= start_index < len(points):
            raise ValueError("guidance requires an explicit valid starting route index")
        snapshot = []
        for row in points:
            if len(row) != 3 or not isinstance(row[0], str):
                raise ValueError("guidance points require name, x, z")
            snapshot.append((row[0], _number(row[1]), _number(row[2])))
        bound_owner = _owner(owner)
        heights = [None] * len(points) if measured_heights is None else list(measured_heights)
        if len(heights) != len(points):
            raise ValueError("guidance measured heights must align with route points")
        heights = [None if height is None else _number(height) for height in heights]
        self._points = snapshot
        self._measured_heights = heights
        self._height_separation, self._height_warning = None, False
        self._direction = direction
        self._order = list(range(start_index, len(points))) if direction == "forward" else list(range(start_index, -1, -1))
        self._owner = bound_owner
        self._completed = []
        self._cursor = 0
        self._last = None
        self._inside_since = None
        self._distance = None
        self._status, self._reason = "unavailable", "awaiting-fresh-pose"
        return self.as_dict()

    def unavailable(self, reason="pose-unavailable"):
        self._inside_since = None
        self._distance = None
        self._height_separation, self._height_warning = None, False
        if self._status not in ("stopped", "complete"):
            self._status, self._reason = "unavailable", str(reason)
        return self.as_dict()

    def stop(self, reason="stopped"):
        self._inside_since = None
        self._distance = None
        self._height_separation, self._height_warning = None, False
        self._status, self._reason = "stopped", str(reason)
        return self.as_dict()

    def observe(self, packet):
        """Consume one fresh, age/identity-validated read_pose result.

        Sequence, native sample timestamp and acquisition time must all increase.
        Re-reading the same packet never confirms arrival or refreshes progress.
        """
        if self._status in ("stopped", "complete"):
            return self.as_dict()
        try:
            if _owner(packet) != self._owner:
                return self.stop("pose-owner-or-session-changed")
            if packet.get("status") != "fresh":
                return self.unavailable("pose-not-fresh")
            sequence = packet["sequence"]
            if type(sequence) is not int or sequence <= 0:
                raise ValueError("invalid sequence")
            acquired = _number(packet["acquiredMonotonic"])
            stamp = datetime.fromisoformat(packet["sampledAtUtc"].replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError("sample timestamp must include timezone")
            x, z = (_number(packet["position"][axis]) for axis in ("x", "z"))
            # Legacy planar-only guides do not require Y. A measured route does.
            y = _number(packet['position']['y']) if any(
                height is not None for height in self._measured_heights) else None
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return self.unavailable("invalid-pose-packet")
        if self._last is not None:
            seq0, acquired0, stamp0 = self._last
            if (sequence, acquired, stamp) == self._last:
                return self.as_dict()
            if sequence <= seq0 or acquired <= acquired0 or stamp <= stamp0:
                return self.unavailable("repeated-or-regressed-pose")
            if (acquired - acquired0 > self.max_sample_gap
                    or (stamp - stamp0).total_seconds() > self.max_sample_gap):
                self._inside_since = None
        self._last = (sequence, acquired, stamp)
        self._status, self._reason = "active", None
        index = self._order[self._cursor]
        _, px, pz = self._points[index]
        self._distance = math.hypot(x - px, z - pz)
        self._update_height(index, y)
        if self._distance > self.radius or self._height_warning:
            self._inside_since = None
        elif self._inside_since is None:
            self._inside_since = (acquired, stamp)
        elif min(acquired - self._inside_since[0],
                 (stamp - self._inside_since[1]).total_seconds()) + 1e-9 >= self.confirmation_seconds:
            self._completed.append(index)
            self._cursor += 1
            self._inside_since = None
            if self._cursor == len(self._order):
                self._status = "complete"
                self._distance = None
                self._height_separation, self._height_warning = None, False
            else:
                index = self._order[self._cursor]
                _, px, pz = self._points[index]
                self._distance = math.hypot(x - px, z - pz)
                self._update_height(index, y)
        return self.as_dict()

    def _update_height(self, index, player_y):
        target_y = self._measured_heights[index]
        self._height_separation = None if target_y is None else target_y - player_y
        self._height_warning = (self._height_separation is not None
                                and abs(self._height_separation) > HEIGHT_CAUTION_UNITS)

    def as_dict(self):
        index = self._order[self._cursor] if self._cursor < len(self._order) else None
        return dict(status=self._status, reason=self._reason, direction=self._direction,
                    order=list(self._order), activeIndex=index,
                    activeName=self._points[index][0] if index is not None else None,
                    completedIndices=list(self._completed), distance=self._distance,
                    complete=self._status == "complete", pointCount=len(self._points),
                    arrivalRadius=self.radius, heightSeparation=self._height_separation,
                    heightWarning=self._height_warning)
