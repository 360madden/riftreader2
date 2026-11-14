"""Record and explicitly replay routes through the existing bounded runner."""
from dataclasses import asdict
import math

from scripts.waypoint_recording import RouteRecorder
from scripts.waypoint_limits import MAX_ROUTE_DISTANCE
from scripts.waypoint_progress import RouteProgress, ProgressError, _position


MAX_START_APPROACH_DISTANCE = 20.0
MAX_START_APPROACH_HEIGHT_DELTA = 1.5


def assess_start_approach(cursor, position):
    """Assess a fresh Play start without changing or saving the route cursor."""
    if cursor.start is not None or cursor.next_index != 0:
        raise ProgressError("Start approach requires a new playback cursor")
    pos = _position(position)
    points = cursor.remaining_points()
    _, x, z = points[0]
    y = cursor.heights[0 if cursor.direction == "forward" else -1] if cursor.heights else None
    distance = math.hypot(pos["x"] - x, pos["z"] - z)
    required = distance > .30 + 1e-9
    if required:
        if distance > MAX_START_APPROACH_DISTANCE:
            raise ProgressError(f"Route start is {distance:.2f}u away; approach limit is {MAX_START_APPROACH_DISTANCE:g}u")
        if y is not None and ("y" not in pos or abs(pos["y"] - y) > MAX_START_APPROACH_HEIGHT_DELTA):
            raise ProgressError("Route start approach is on a different or unknown current height")
    elif y is not None and ("y" not in pos or abs(pos["y"] - y) > 1.0):
        raise ProgressError("position is on a different height")
    remaining = distance + sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(points, points[1:]))
    if remaining > MAX_ROUTE_DISTANCE:
        raise ProgressError(f"Remaining route including approach exceeds {MAX_ROUTE_DISTANCE:g} world units")
    return {"required": required, "distance": distance, "goalHeight": y, "remainingDistance": remaining}


class RecordingAdapter:
    def __init__(self, adapter, recorder):
        self.adapter, self.recorder, self.latest = adapter, recorder, None

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def read(self, **kwargs):
        snapshot = self.adapter.read(**kwargs)
        self.recorder.observe(snapshot)
        self.latest = snapshot
        return snapshot


def teach_route(adapter, points, stop, emit, *, runner, face_waypoints=True):
    recorder = RouteRecorder(adapter.binding)
    wrapped = RecordingAdapter(adapter, recorder)

    def progress(event):
        if event["status"] in ("leg", "arrived", "segment-arrived", "turning") and wrapped.latest is not None:
            recorder.observe(wrapped.latest, boundary=True)
        emit(dict(event, recordingProgress=recorder.progress))

    legs = runner(wrapped, points, stop, progress, face_waypoints=face_waypoints)
    return legs, recorder.finish()


def validate_playback_document(document, identity):
    """Share saved evidence admission between read-only readiness and execution."""
    if not isinstance(document, dict):
        raise ProgressError("route document must be an object")
    if not isinstance(identity, dict) or not all(isinstance(identity.get(key), str) and identity[key]
            for key in ("machine", "gameBuildSha256", "unitKey")):
        raise ProgressError("identity requires machine, build and player")
    recording = document.get("recording")
    if recording is not None:
        if not isinstance(recording, dict) or recording.get("complete") is not True:
            raise ProgressError("Recording is incomplete")
        recorded_identity = recording.get("identity", {})
        if not isinstance(recorded_identity, dict):
            raise ProgressError("Recording identity is invalid")
        recorded_identity = recorded_identity.get("runtimeIdentity", recorded_identity)
        if not isinstance(recorded_identity, dict):
            raise ProgressError("Recording identity is invalid")
        if any(str(recorded_identity.get(k, "")).casefold() != str(identity[k]).casefold()
               for k in ("machine", "gameBuildSha256", "unitKey")):
            raise ProgressError("Recording belongs to another host, build or player")
    elif "pointMeasurements" in document:
        from scripts.waypoint_measurements import document_measurements
        raw = document["pointMeasurements"]
        points = document.get("waypoints")
        if not isinstance(raw, list) or not isinstance(points, list) or len(raw) != len(points):
            raise ProgressError("Invalid waypoint measurement list")
        measured = document_measurements(document)
        if len(measured) != len(raw):
            raise ProgressError("Invalid waypoint measurement list")
        for original, receipt in zip(raw, measured):
            if original is None:
                continue  # Existing manually entered points retain unknown height.
            if receipt is None:
                raise ProgressError("Invalid waypoint measurement")
            observed_identity = receipt["identity"]
            observed_identity = observed_identity.get("runtimeIdentity", observed_identity)
            if any(str(observed_identity.get(k, "")).casefold() != str(identity[k]).casefold()
                   for k in ("machine", "gameBuildSha256", "unitKey")):
                raise ProgressError("Measured waypoint belongs to another host, build or player")


def play_route(adapter, document, stop, emit, *, runner, checkpoint,
               direction="forward", resume=False, face_waypoints=True,
               approach_start=False):
    identity = adapter.binding["runtimeIdentity"]
    validate_playback_document(document, identity)
    cursor = (RouteProgress.load(checkpoint, document, identity) if resume else
              RouteProgress(document, direction, identity))
    if cursor.direction != direction:
        raise ProgressError("Resume direction does not match saved progress")
    if cursor.next_index >= len(cursor.ordered_points):
        raise ProgressError("route already complete")

    approach = None

    def enter(position):
        nonlocal approach
        actual = asdict(position)
        if approach_start and not resume:
            assessment = assess_start_approach(cursor, actual)
            if assessment["required"]:
                approach = assessment
                emit({"status": "approaching-route", "name": cursor.remaining_points()[0][0],
                      "position": actual, "approachDistance": approach["distance"],
                      "nextWaypoint": 0, "waypointCount": len(cursor.ordered_points)})
                return
        cursor.begin(actual)
        cursor.save(checkpoint)

    def progress(event):
        nonlocal approach
        if event["status"] == "arrived":
            expected = cursor.remaining_points()[0]
            goal = event["goal"]
            if (event.get("name"), goal["x"], goal["z"]) != expected:
                raise ProgressError("Runner arrival does not match the route cursor")
            actual = _position(event["position"])
            if math.hypot(actual["x"]-expected[1], actual["z"]-expected[2]) > .30 + 1e-9:
                raise ProgressError("Settled position is outside the waypoint arrival radius")
            heights = document.get("heights")
            if heights is not None:
                original_index = (cursor.next_index if direction == "forward" else
                                  len(cursor.ordered_points)-1-cursor.next_index)
                y = heights[original_index]
                if y is not None and abs(actual["y"]-y) > 1:
                    raise ProgressError("Settled waypoint is on a different height")
            if approach is not None:
                if "releaseSucceeded" in event or "desktopInputsDown" in event:
                    released = event.get("releaseSucceeded") is True and event.get("desktopInputsDown") == []
                else:
                    released = event.get("allPulsesReleased") is True
                if not released:
                    raise ProgressError("Route start approach input release is unverified")
                if stop.is_set():
                    from scripts.physical_waypoints import Stopped
                    raise Stopped("Stopped before route start approach was confirmed")
                cursor.begin(actual)
            cursor.confirm_arrival(cursor.next_index, expected)
            cursor.save(checkpoint)
            if approach is not None:
                emit(dict(event, status="route-approach-complete", approachDistance=approach["distance"],
                          nextWaypoint=cursor.next_index, waypointCount=len(cursor.ordered_points)))
                approach = None
        emit(dict(event, nextWaypoint=cursor.next_index, waypointCount=len(cursor.ordered_points)))

    legs = runner(adapter, cursor.remaining_points(), stop, progress,
                  face_waypoints=face_waypoints, entry_check=enter)
    return legs, cursor
