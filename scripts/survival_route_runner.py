"""Playback-compatible, encounter-aware route runner."""
from __future__ import annotations

from dataclasses import asdict
import math
import time

from scripts.waypoint_limits import MAX_ROUTE_DISTANCE, MAX_TRIP_SECONDS
from scripts.waypoint_survival import SurvivalPorts, WaypointSurvivalRunner


class _OperatorStopped(RuntimeError):
    pass


def _position(value):
    if isinstance(value, dict):
        raw = value
    elif hasattr(value, "position"):
        point = value.position
        raw = {axis: getattr(point, axis) for axis in ("x", "y", "z")}
    else:
        raw = {axis: getattr(value, axis) for axis in ("x", "y", "z")}
    try:
        result = {axis: float(raw[axis]) for axis in ("x", "y", "z")}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Movement position is unavailable") from exc
    if any(not math.isfinite(item) for item in result.values()):
        raise ValueError("Movement position is unavailable")
    return result


def _traversed_path(receipt, final_position, anchor):
    """Admit only the native-retained, continuous corridor actually traversed."""
    raw = receipt.get("path") if isinstance(receipt, dict) else None
    if not isinstance(raw, list) or not 1 <= len(raw) <= 8192:
        raise ValueError("Native encounter receipt has no bounded traversed path")
    points = [_position(item) for item in raw]

    def near(left, right, planar, height):
        return (math.hypot(left["x"] - right["x"], left["z"] - right["z"]) <= planar
                and abs(left["y"] - right["y"]) <= height)

    if not near(points[0], anchor, .5, 1.0):
        raise ValueError("Native traversed path does not join the confirmed route corridor")
    if not near(points[-1], final_position, .5, .5):
        raise ValueError("Native traversed path does not end at the interruption pose")
    if any(not near(earlier, later, 2.0, 1.0)
           for earlier, later in zip(points, points[1:])):
        raise ValueError("Native traversed path is discontinuous in distance or height")
    return points


def _release_confirmed(receipt):
    if not isinstance(receipt, dict):
        return False
    evidence = [receipt.get(key) for key in ("releaseSucceeded", "allInputsReleased")
                if key in receipt]
    return (bool(evidence) and all(value is True for value in evidence)
            and receipt.get("desktopInputsDown", []) == [])


def _corridor_arrival(position, x, y, z):
    return (math.hypot(position["x"] - x, position["z"] - z) <= .5
            and abs(position["y"] - y) <= .5)


def _coalesce_retained_corridor(points, planar_tolerance=.2, height_tolerance=.3):
    """Return original corridor points that bound verified straight sub-segments.

    Every omitted retained sample remains within the given planar and height
    tolerances of its replacement segment.  Endpoints and out-of-tolerance
    corners are original samples; this never invents an unobserved waypoint.
    """
    if len(points) <= 2:
        return list(points)

    def error(point, start, end):
        dx, dz = end[0] - start[0], end[2] - start[2]
        length_squared = dx * dx + dz * dz
        if length_squared == 0:
            along = 0.0
        else:
            along = ((point[0] - start[0]) * dx
                     + (point[2] - start[2]) * dz) / length_squared
            along = min(1.0, max(0.0, along))
        projected_x = start[0] + along * dx
        projected_z = start[2] + along * dz
        projected_y = start[1] + along * (end[1] - start[1])
        planar = math.hypot(point[0] - projected_x, point[2] - projected_z)
        height = abs(point[1] - projected_y)
        return max(planar / planar_tolerance, height / height_tolerance)

    retained = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        start_index, end_index = pending.pop()
        if end_index <= start_index + 1:
            continue
        worst_index, worst_error = max(
            ((index, error(points[index], points[start_index], points[end_index]))
             for index in range(start_index + 1, end_index)),
            key=lambda item: item[1])
        if worst_error > 1.0:
            retained.add(worst_index)
            pending.extend(((start_index, worst_index), (worst_index, end_index)))
    return [points[index] for index in sorted(retained)]


def run_survival_route(adapter, points, stop, emit=lambda event: None, *,
                       profile, telemetry, action_backend, face_waypoints=True,
                       entry_check=None, mover=None, encounter_error=None,
                       clock=time.monotonic, wait_seconds=.05,
                       max_seconds=MAX_TRIP_SECONDS, retreat_max_seconds=30,
                       minimum_trail_points=1, initial_retreat_trail=None,
                       assess_before_travel=False, finish_after_retreat=False):
    """Run one pending real route leg at a time with a shared trip budget.

    The injected mover has ``continuous_move.move_to``'s contract. Encounter
    interrupts do not touch the operator STOP event and never advance the leg.
    """
    from scripts.physical_waypoints import Stopped, WaypointError, read_stationary, route_points
    if mover is None or encounter_error is None:
        from scripts import continuous_move
        mover = mover or continuous_move.move_to
        encounter_error = encounter_error or continuous_move.EncounterInterrupted
    if type(max_seconds) is not int or not 1 <= max_seconds <= MAX_TRIP_SECONDS:
        raise WaypointError(f"Survival trip time must be 1-{MAX_TRIP_SECONDS} seconds")
    if (type(retreat_max_seconds) not in (int, float)
            or not math.isfinite(retreat_max_seconds) or not 1 <= retreat_max_seconds <= 300
            or type(minimum_trail_points) is not int
            or not 1 <= minimum_trail_points <= 256):
        raise WaypointError("Invalid configured retreat bounds")
    rows = route_points(points)
    callbacks = ("cast", "start_combat", "release_combat", "start_recovery",
                 "release_recovery", "corridor_reachable")
    if any(not callable(getattr(action_backend, name, None)) for name in callbacks):
        raise TypeError("Survival action backend is incomplete")
    if stop.is_set():
        raise Stopped("Stopped; no movement helper launched")
    started = clock()
    initial = read_stationary(adapter, stop)
    if entry_check is not None:
        entry_check(initial.position)
    current = _position(initial)
    seeded_trail = None
    if initial_retreat_trail is not None:
        if (not isinstance(initial_retreat_trail, (list, tuple))
                or not 2 <= len(initial_retreat_trail) <= 500):
            raise WaypointError("Initial retreat trail must contain 2-500 retained points")
        seeded_trail = []
        seeded_distance = 0.0
        for item in initial_retreat_trail:
            point = _position(item)
            if seeded_trail:
                seeded_distance += math.hypot(point["x"]-seeded_trail[-1]["x"],
                                              point["z"]-seeded_trail[-1]["z"])
            seeded_trail.append(point)
        if seeded_distance > MAX_ROUTE_DISTANCE:
            raise WaypointError("Initial retreat trail exceeds the route distance limit")
        if not _corridor_arrival(current, seeded_trail[-1]["x"],
                                 seeded_trail[-1]["y"], seeded_trail[-1]["z"]):
            raise WaypointError("Current pose is not at the retained retreat trail endpoint")
        safe = seeded_trail[0]
        if not _corridor_arrival(safe, rows[-1][1], safe["y"], rows[-1][2]):
            raise WaypointError("Return route does not end at the retained safe endpoint")
    if finish_after_retreat and seeded_trail is None:
        raise WaypointError("Terminal safe retreat requires a retained trail")
    original_distance = math.hypot(rows[0][1] - current["x"], rows[0][2] - current["z"])
    original_distance += sum(math.hypot(b[1] - a[1], b[2] - a[2])
                             for a, b in zip(rows, rows[1:]))
    if original_distance > MAX_ROUTE_DISTANCE:
        raise WaypointError(f"Route exceeds {MAX_ROUTE_DISTANCE:g} world units")

    requested_moves = []
    movement_release = ({"releaseSucceeded": True, "desktopInputsDown": [],
                         "inputSent": False,
                         "reason": "No route movement input launched before initial assessment"}
                        if assess_before_travel else
                        {"releaseSucceeded": False,
                         "reason": "No verified native encounter release"})

    def request_move(mode, requested, pending):
        if mode == "rejoin":
            nearby = []
            for index, point in enumerate(requested):
                if not isinstance(point, (list, tuple)) or len(point) != 3:
                    continue
                try:
                    x, y, z = (float(value) for value in point)
                except (TypeError, ValueError):
                    continue
                planar = math.hypot(x - current["x"], z - current["z"])
                height = abs(y - current["y"])
                if (all(math.isfinite(value) for value in (x, y, z))
                        and planar <= .5 and height <= .5):
                    nearby.append((planar, height, index))
            if not nearby:
                raise WaypointError(
                    "Current pose is not on the retained rejoin corridor")
            # The policy supplies interruption->origin reverse trail order.
            # Begin at the nearest current sample and replay that exact
            # retained corridor forward to the interruption point before the
            # pending real route leg may resume.
            nearest_index = min(nearby, key=lambda item: item[:2])[2]
            requested = list(reversed(requested[:nearest_index + 1]))
        requested_moves.append((mode, requested, pending))

    def release_move(reason):
        return dict(movement_release, reason=movement_release.get("reason", reason))

    def guarded_telemetry():
        if stop.is_set():
            raise _OperatorStopped("Stopped before survival telemetry")
        value = telemetry()
        if stop.is_set():
            raise _OperatorStopped("Stopped after survival telemetry; no action started")
        return value

    def guarded(action):
        def call(*args):
            if stop.is_set():
                raise _OperatorStopped("Stopped; no survival action started")
            return action(*args)
        return call

    ports = SurvivalPorts(
        guarded_telemetry, guarded(action_backend.cast), request_move, release_move, request_move,
        guarded(action_backend.start_combat), action_backend.release_combat,
        guarded(action_backend.start_recovery), action_backend.release_recovery,
        action_backend.corridor_reachable)
    all_encounters = []
    policy = WaypointSurvivalRunner(profile, ports, checkpoint=0,
                                    pending_leg=list(rows[0]),
                                    finish_after_retreat=finish_after_retreat)
    last_published_state = None

    def publish_policy_state(snapshot=None):
        nonlocal last_published_state
        snapshot = snapshot or policy.snapshot()
        current_state = snapshot["state"]
        if current_state == last_published_state:
            return
        last_published_state = current_state
        coordinator = snapshot["coordinator"]
        emit({"status": "survival-state", "survival": {
            "active": current_state not in ("halt",),
            "state": current_state,
            "owner": coordinator.get("activeAction"),
            "lastAction": snapshot.get("lastAction"),
            "reason": coordinator.get("latchReason"),
            "encounterCount": len(all_encounters),
            "inputSent": False,
        }})

    for point in (seeded_trail or [current]):
        policy.record_route_trail_point((point["x"], point["y"], point["z"]))
    policy.start()
    publish_policy_state()
    requested_moves.clear()  # The outer loop owns ordinary forward travel.
    auxiliary_distance = 0.0

    def remaining_seconds():
        if stop.is_set():
            raise Stopped("Stopped; no further input")
        remaining = math.floor(max_seconds - (clock() - started))
        if remaining < 1:
            raise WaypointError(f"Trip exceeded {max_seconds} seconds")
        return remaining

    def move(row, *, forward, expected_height=None, guard_mode=True,
             operation_max_seconds=None):
        nonlocal current, movement_release, auxiliary_distance
        label, x, z = row
        movement_start = dict(current)
        if not forward:
            auxiliary_distance += math.hypot(x - current["x"], z - current["z"])
            if original_distance + auxiliary_distance > MAX_ROUTE_DISTANCE:
                raise WaypointError(
                    f"Survival travel exceeds {MAX_ROUTE_DISTANCE:g} world units")

        def named(event):
            event = dict(event, name=label)
            # The mover emits arrival before its final receipt is validated.
            # Never publish an unverified route or auxiliary arrival.
            if event.get("status") != "arrived":
                emit(event)

        try:
            limit = remaining_seconds()
            if operation_max_seconds is not None:
                limit = min(limit, operation_max_seconds)
            if limit < 1:
                raise WaypointError("Configured retreat time was exceeded")
            result = mover(adapter, x, z, stop, named,
                           max_seconds=limit, survival_guard=guard_mode)
        except encounter_error as exc:
            movement_release = (exc.receipt if isinstance(exc.receipt, dict) else
                                {"releaseSucceeded": False,
                                 "reason": "Encounter release receipt unavailable"})
            current = _position(exc.position)
            evidence = {"pendingLeg": list(row), "receipt": movement_release,
                        "position": dict(current)}
            all_encounters.append(evidence)
            emit({"status": "encounter-interrupted", "name": label,
                  "goal": {"x": x, "z": z}, "position": dict(current),
                  "releaseSucceeded": _release_confirmed(movement_release)})
            if not _release_confirmed(movement_release):
                return None  # Coordinator records the uncertain release before any combat.
            try:
                traversed = _traversed_path(movement_release, current,
                                             {"x": policy.trail[-1][0],
                                              "y": policy.trail[-1][1],
                                              "z": policy.trail[-1][2]})
            except (ValueError, IndexError) as invalid:
                policy.coordinator.critical("critical-unavailable")
                policy.state = "halt"
                raise WaypointError(
                    "Encounter path cannot establish a known traversed corridor: "
                    + str(invalid)) from invalid
            for point in traversed:
                policy.record_route_trail_point((point["x"], point["y"], point["z"]))
            evidence.update(traversedPath=traversed,
                            corridorQualification="native-retained traversed samples")
            return None
        if not isinstance(result, dict) or result.get("status") != "arrived":
            raise WaypointError("Survival movement did not return an arrived leg")
        if not _release_confirmed(result):
            policy.coordinator.critical("critical-unavailable")
            policy.state = "halt"
            raise WaypointError("Survival arrived leg has unverified input release")
        current = _position(result.get("position"))
        if forward and math.hypot(current["x"] - x, current["z"] - z) > .5:
            policy.coordinator.critical("critical-unavailable")
            policy.state = "halt"
            raise WaypointError("Survival arrived leg is not at the requested destination")
        if (not forward and expected_height is not None
                and not _corridor_arrival(current, x, expected_height, z)):
            raise WaypointError(
                "Survival rejoin did not confirm the retained corridor distance and height")
        movement_release = result
        if forward:
            try:
                traversed = _traversed_path(result, current, movement_start)
            except ValueError as invalid:
                policy.coordinator.critical("critical-unavailable")
                policy.state = "halt"
                raise WaypointError(
                    "Arrived leg cannot establish a known traversed corridor: "
                    + str(invalid)) from invalid
            for point in traversed:
                policy.record_route_trail_point((point["x"], point["y"], point["z"]))
            # The post-release stationary endpoint may be slightly newer than
            # the native movement path's final sample; retain both.
            policy.record_route_trail_point((current["x"], current["y"], current["z"]))
        verified = dict(result, name=label)
        if forward:
            emit(verified)
        return verified

    def execute_requested_moves():
        while requested_moves:
            mode, requested, _ = requested_moves.pop(0)
            if mode not in {"retreat", "rejoin"}:
                continue
            if mode == "retreat" and len(requested) < minimum_trail_points:
                policy.coordinator.critical("critical-unavailable")
                policy.state = "halt"
                raise WaypointError("Known retreat trail has too few retained points")
            normalized = []
            for coordinates in requested:
                if (not isinstance(coordinates, (list, tuple))
                        or len(coordinates) not in (2, 3)):
                    raise WaypointError("Survival policy returned an invalid route point")
                point = (float(coordinates[0]),
                         float(coordinates[1]) if len(coordinates) == 3 else current["y"],
                         float(coordinates[-1]))
                if any(not math.isfinite(value) for value in point):
                    raise WaypointError("Survival policy returned an invalid route point")
                normalized.append(point)
            execution_points = _coalesce_retained_corridor(normalized)
            retreat_started = clock() if mode == "retreat" else None
            for number, coordinates in enumerate(execution_points, 1):
                x, expected_height, z = coordinates
                if math.hypot(x - current["x"], z - current["z"]) <= .30:
                    continue
                retreat_remaining = None
                if retreat_started is not None:
                    retreat_remaining = math.floor(
                        retreat_max_seconds - (clock() - retreat_started))
                if move((f"{mode} {number}", x, z), forward=False,
                        expected_height=expected_height,
                        guard_mode="retreat" if mode == "retreat" else True,
                        operation_max_seconds=retreat_remaining) is None:
                    policy.coordinator.critical("critical-unavailable")
                    policy.state = "halt"
                    raise WaypointError("Encounter recurred during survival rejoin")

    def handle_encounter():
        for _ in range(1000):
            remaining_seconds()
            try:
                state = policy.step()
            except _OperatorStopped as stopped:
                policy.operator_stop()  # Release/cancel is allowed cleanup after STOP.
                publish_policy_state()
                raise Stopped(str(stopped)) from stopped
            coordinator = state["coordinator"]
            if state["state"] == "halt" or coordinator["latchReason"] is not None:
                publish_policy_state(state)
                detail = state.get("failureDetail")
                raise WaypointError(
                    "Survival policy halted: "
                    + str(coordinator["latchReason"] or "unknown")
                    + ("; " + detail if isinstance(detail, str) and detail else ""))
            execute_requested_moves()
            publish_policy_state()
            if policy.state == "travel":
                return
            if stop.wait(wait_seconds):
                policy.operator_stop()  # Idempotent cleanup must not be blocked by STOP.
                publish_policy_state()
                raise Stopped("Stopped during encounter handling")
        raise WaypointError("Survival policy step budget exceeded")

    results = []
    if assess_before_travel:
        if finish_after_retreat:
            state = policy.begin_safe_retreat()
            if state["state"] == "halt":
                detail = state.get("failureDetail")
                raise WaypointError("Safe retreat admission halted: "
                    + str(state["coordinator"].get("latchReason") or "unknown")
                    + ("; " + detail if isinstance(detail,str) and detail else ""))
            execute_requested_moves()
        handle_encounter()
        if policy.safe_retreat_completed:
            safe = seeded_trail[0]
            # Recovery may outlast the last movement receipt. Reacquire after
            # recovery so knockback or outside displacement cannot inherit the
            # earlier safe pose.
            final_stationary = read_stationary(adapter, stop)
            current = _position(final_stationary)
            if not _corridor_arrival(current, safe["x"], safe["y"], safe["z"]):
                raise WaypointError("Safe retreat did not finish at the retained safe endpoint")
            if not _release_confirmed(movement_release):
                raise WaypointError("Safe retreat input release is unverified")
            label, x, z = rows[-1]
            verified = dict(movement_release, status="arrived", name=label,
                            goal={"x":x,"z":z}, position=dict(current), safeRetreat=True,
                            survival={"encounters":all_encounters,"state":policy.snapshot(),
                                      "sharedElapsedSeconds":round(clock()-started,3),
                                      "plannedRouteDistance":original_distance,
                                      "auxiliaryDistance":auxiliary_distance})
            emit(verified)
            return [verified]
    for index, row in enumerate(rows):
        policy.pending_leg = list(row)
        encounter_start = len(all_encounters)
        while True:
            result = move(row, forward=True)
            if result is None:
                handle_encounter()
                continue  # The cursor and pending leg are deliberately unchanged.
            result["survival"] = {"encounters": all_encounters[encounter_start:],
                                  "state": policy.snapshot(),
                                  "sharedElapsedSeconds": round(clock() - started, 3),
                                  "plannedRouteDistance": original_distance,
                                  "auxiliaryDistance": auxiliary_distance}
            results.append(result)
            if index + 1 < len(rows):
                policy.route_checkpoint_advanced(index + 1, list(rows[index + 1]))
            break
    return results
