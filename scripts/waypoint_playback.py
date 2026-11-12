"""Record and explicitly replay short routes through the existing runner."""
from dataclasses import asdict
import math

from scripts.waypoint_recording import RouteRecorder
from scripts.waypoint_progress import RouteProgress, ProgressError


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


def play_route(adapter, document, stop, emit, *, runner, checkpoint,
               direction="forward", resume=False, face_waypoints=True):
    identity = adapter.binding["runtimeIdentity"]
    recording = document.get("recording")
    if recording is not None:
        if not isinstance(recording, dict) or recording.get("complete") is not True:
            raise ProgressError("Recording is incomplete")
        recorded_identity = recording.get("identity", {})
        recorded_identity = recorded_identity.get("runtimeIdentity", recorded_identity)
        if any(str(recorded_identity.get(k, "")).casefold() != str(identity[k]).casefold()
               for k in ("machine", "gameBuildSha256", "unitKey")):
            raise ProgressError("Recording belongs to another host, build or player")
    cursor = (RouteProgress.load(checkpoint, document, identity) if resume else
              RouteProgress(document, direction, identity))
    if cursor.direction != direction:
        raise ProgressError("Resume direction does not match saved progress")

    def enter(position):
        cursor.begin(asdict(position))
        cursor.save(checkpoint)

    def progress(event):
        if event["status"] == "arrived":
            expected = cursor.remaining_points()[0]
            goal = event["goal"]
            if (event.get("name"), goal["x"], goal["z"]) != expected:
                raise ProgressError("Runner arrival does not match the route cursor")
            actual = event["position"]
            if math.hypot(actual["x"]-expected[1], actual["z"]-expected[2]) > .30 + 1e-9:
                raise ProgressError("Settled position is outside the waypoint arrival radius")
            heights = document.get("heights")
            if heights is not None:
                original_index = (cursor.next_index if direction == "forward" else
                                  len(cursor.ordered_points)-1-cursor.next_index)
                y = heights[original_index]
                if y is not None and abs(actual["y"]-y) > 1:
                    raise ProgressError("Settled waypoint is on a different height")
            cursor.confirm_arrival(cursor.next_index, expected)
            cursor.save(checkpoint)
        emit(dict(event, nextWaypoint=cursor.next_index, waypointCount=len(cursor.ordered_points)))

    legs = runner(adapter, cursor.remaining_points(), stop, progress,
                  face_waypoints=face_waypoints, entry_check=enter)
    return legs, cursor
