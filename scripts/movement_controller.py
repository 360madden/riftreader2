#!/usr/bin/env python3
"""Pure bounded waypoint decisions from empirically calibrated RIFT movement.

This module performs no input or acquisition.  Its caller owns fresh receipt,
identity, lease, review/arm, action delivery/release, and cleanup checks.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


MOVEMENT_KEYS = frozenset(("w", "q", "s", "e"))


class MovementError(ValueError):
    pass


class MovementHalted(RuntimeError):
    pass


@dataclass(frozen=True)
class Position:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Calibration:
    key: str
    dx_per_ms: float
    dz_per_ms: float
    calibration_hold_ms: int
    horizontal_displacement: float
    vertical_displacement: float


@dataclass(frozen=True)
class MovementAction:
    key: str
    hold_ms: int
    distance_before: float
    predicted_distance_after: float


@dataclass(frozen=True)
class FeedbackResult:
    distance_before: float
    distance_after: float
    progress: float
    status: str
    arrival_confirmations: int
    feedback_iterations: int


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MovementError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise MovementError(f"{name} must be finite")
    return result


def _position(value: Position, name: str) -> Position:
    if not isinstance(value, Position):
        raise MovementError(f"{name} must be a Position")
    return Position(
        _finite(value.x, f"{name}.x"),
        _finite(value.y, f"{name}.y"),
        _finite(value.z, f"{name}.z"),
    )


def planar_distance(a: Position, b: Position) -> float:
    a, b = _position(a, "a"), _position(b, "b")
    return math.hypot(b.x - a.x, b.z - a.z)


def calibrate_displacement(
    key: str,
    before: Position,
    after: Position,
    hold_ms: int,
    *,
    minimum_horizontal: float = 0.05,
    maximum_horizontal: float = 2.0,
    maximum_vertical: float = 0.75,
    maximum_calibration_hold_ms: int = 150,
) -> Calibration:
    """Derive one measured key vector; never infer an opposite key."""
    if key not in MOVEMENT_KEYS:
        raise MovementError("calibration key must be one of w/q/s/e")
    if (type(maximum_calibration_hold_ms) is not int
            or not 150 <= maximum_calibration_hold_ms <= 1000):
        raise MovementError("maximum calibration hold must be from 150 through 1000 ms")
    if type(hold_ms) is not int or not 20 <= hold_ms <= maximum_calibration_hold_ms:
        raise MovementError(
            f"calibration hold_ms must be an integer from 20 through {maximum_calibration_hold_ms}")
    before, after = _position(before, "before"), _position(after, "after")
    minimum_horizontal = _finite(minimum_horizontal, "minimum_horizontal")
    maximum_horizontal = _finite(maximum_horizontal, "maximum_horizontal")
    maximum_vertical = _finite(maximum_vertical, "maximum_vertical")
    if not 0 < minimum_horizontal < maximum_horizontal or maximum_vertical < 0:
        raise MovementError("calibration plausibility bounds are invalid")
    dx, dz, dy = after.x - before.x, after.z - before.z, after.y - before.y
    horizontal = math.hypot(dx, dz)
    if not minimum_horizontal <= horizontal <= maximum_horizontal:
        raise MovementError("calibration horizontal displacement is implausible")
    if abs(dy) > maximum_vertical:
        raise MovementError("calibration vertical displacement is implausible")
    return Calibration(key, dx / hold_ms, dz / hold_ms, hold_ms, horizontal, dy)


def validate_noncollinear(
    calibrations: dict[str, Calibration],
    first: str = "w",
    second: str = "q",
    *,
    minimum_normalized_cross: float = 0.25,
) -> float:
    """Return normalized 2-D cross magnitude for two independently measured keys."""
    if not isinstance(calibrations, dict):
        raise MovementError("calibrations must be a dictionary")
    try:
        a, b = calibrations[first], calibrations[second]
    except KeyError as error:
        raise MovementError("both requested calibration keys are required") from error
    if a.key != first or b.key != second:
        raise MovementError("calibration dictionary key mismatch")
    threshold = _finite(minimum_normalized_cross, "minimum_normalized_cross")
    if not 0 < threshold <= 1:
        raise MovementError("minimum_normalized_cross must be in (0, 1]")
    a_norm = math.hypot(a.dx_per_ms, a.dz_per_ms)
    b_norm = math.hypot(b.dx_per_ms, b.dz_per_ms)
    if a_norm == 0 or b_norm == 0:
        raise MovementError("calibration vector is zero")
    normalized = abs(a.dx_per_ms * b.dz_per_ms - a.dz_per_ms * b.dx_per_ms) / (a_norm * b_norm)
    if normalized < threshold:
        raise MovementError("calibration vectors are too nearly collinear")
    return normalized


class WaypointController:
    """Greedy one-pulse-at-a-time XZ controller with explicit bounded state."""

    def __init__(
        self,
        calibrations: dict[str, Calibration],
        start: Position,
        goal: Position,
        *,
        tolerance: float = 0.30,
        minimum_pulse_ms: int = 20,
        maximum_pulse_ms: int = 150,
        max_goal_actions: int = 6,
        max_elapsed_seconds: float = 12.0,
        max_total_hold_ms: int = 900,
        max_radius: float = 6.0,
        max_cross_track: float = 0.50,
        max_vertical_drift: float = 1.5,
        minimum_progress: float = 0.03,
        no_progress_limit: int = 2,
        divergence_limit: int = 2,
    ):
        if not isinstance(calibrations, dict) or not calibrations:
            raise MovementError("at least one empirical calibration is required")
        copied = {}
        for key, value in calibrations.items():
            if key not in MOVEMENT_KEYS or not isinstance(value, Calibration) or value.key != key:
                raise MovementError("calibrations must be measured w/q/s/e vectors keyed by key")
            if not all(math.isfinite(v) for v in (value.dx_per_ms, value.dz_per_ms)):
                raise MovementError("calibration vector must be finite")
            if math.hypot(value.dx_per_ms, value.dz_per_ms) == 0:
                raise MovementError("calibration vector must be nonzero")
            copied[key] = value
        self.calibrations = copied
        self.start, self.goal = _position(start, "start"), _position(goal, "goal")
        self.tolerance = _finite(tolerance, "tolerance")
        self.max_elapsed_seconds = _finite(max_elapsed_seconds, "max_elapsed_seconds")
        self.max_radius = _finite(max_radius, "max_radius")
        self.max_cross_track = _finite(max_cross_track, "max_cross_track")
        self.max_vertical_drift = _finite(max_vertical_drift, "max_vertical_drift")
        self.minimum_progress = _finite(minimum_progress, "minimum_progress")
        if not 0.25 <= self.tolerance <= 0.35:
            raise MovementError("tolerance must be from 0.25 through 0.35")
        if (type(minimum_pulse_ms) is not int or type(maximum_pulse_ms) is not int
                or not 20 <= minimum_pulse_ms <= maximum_pulse_ms <= 150):
            raise MovementError("pulse bounds must be integers within 20 through 150 ms")
        if type(max_goal_actions) is not int or not 1 <= max_goal_actions <= 6:
            raise MovementError("max_goal_actions must be from 1 through 6")
        if type(max_total_hold_ms) is not int or not 20 <= max_total_hold_ms <= 900:
            raise MovementError("max_total_hold_ms must be from 20 through 900")
        if not 0 < self.max_elapsed_seconds <= 12 or not 0 < self.max_radius <= 6:
            raise MovementError("time and radius budgets must be positive and bounded")
        if not 0 < self.max_cross_track <= 0.50:
            raise MovementError("max_cross_track must be in (0, 0.50]")
        if self.max_vertical_drift < 0 or self.minimum_progress <= 0:
            raise MovementError("drift and progress bounds are invalid")
        if type(no_progress_limit) is not int or no_progress_limit < 1:
            raise MovementError("no_progress_limit must be positive")
        if type(divergence_limit) is not int or divergence_limit < 1:
            raise MovementError("divergence_limit must be positive")
        if planar_distance(self.start, self.goal) > self.max_radius:
            raise MovementError("goal exceeds the movement radius")
        self.minimum_pulse_ms = minimum_pulse_ms
        self.maximum_pulse_ms = maximum_pulse_ms
        self.max_goal_actions = max_goal_actions
        self.max_total_hold_ms = max_total_hold_ms
        self.no_progress_limit = no_progress_limit
        self.divergence_limit = divergence_limit
        self.action_count = 0
        self.total_hold_ms = 0
        self.feedback_iterations = 0
        self.no_progress_count = 0
        self.divergence_count = 0
        self.arrival_confirmations = 0
        self.status = "active"
        self.halt_reason: str | None = None
        self.pending: tuple[MovementAction, Position] | None = None
        self.current = self.start

    def _halt(self, reason: str):
        self.status, self.halt_reason = "halted", reason
        raise MovementHalted(reason)

    def _check_observation(self, position: Position, elapsed_seconds: float) -> Position:
        elapsed = _finite(elapsed_seconds, "elapsed_seconds")
        if elapsed < 0 or elapsed > self.max_elapsed_seconds:
            self._halt("elapsed-budget")
        return self._check_position(position)

    def _check_position(self, position: Position) -> Position:
        position = _position(position, "position")
        if planar_distance(self.start, position) > self.max_radius:
            self._halt("radius-budget")
        if self._cross_track(position) > self.max_cross_track:
            self._halt("cross-track")
        if abs(position.y - self.start.y) > self.max_vertical_drift:
            self._halt("vertical-drift")
        return position

    def confirm_released_settle(self, position: Position,
                                action_feedback_position: Position) -> None:
        """Confirm arrival after the caller has stopped and verified input release.

        The movement elapsed budget deliberately does not apply to this no-input
        confirmation phase.  Callers must establish that the action phase ended
        in tolerance, STOP/disarm succeeded, and no desktop input remains down.
        """
        if self.status == "halted":
            raise MovementHalted(self.halt_reason or "halted")
        if self.pending is not None:
            raise MovementError("pending action cannot enter released settle phase")
        if self.status != "confirming-arrival" or self.arrival_confirmations != 1:
            raise MovementError("released settle requires one in-tolerance action feedback")
        prior = self._check_position(action_feedback_position)
        settle = self._check_position(position)
        if planar_distance(prior, settle) > .05:
            raise MovementError("released settle was not planar-stationary")
        self.current = settle
        self._note_arrival(self.current)

    def _cross_track(self, position: Position) -> float:
        goal_x, goal_z = self.goal.x - self.start.x, self.goal.z - self.start.z
        length = math.hypot(goal_x, goal_z)
        if length == 0:
            return planar_distance(self.start, position)
        point_x, point_z = position.x - self.start.x, position.z - self.start.z
        return abs(goal_x * point_z - goal_z * point_x) / length

    def _note_arrival(self, position: Position) -> None:
        if planar_distance(position, self.goal) <= self.tolerance:
            self.arrival_confirmations += 1
            self.status = "arrived" if self.arrival_confirmations >= 2 else "confirming-arrival"
        else:
            self.arrival_confirmations = 0
            self.status = "active"

    def observe(self, position: Position, elapsed_seconds: float) -> None:
        """Record a fresh no-input observation, chiefly the second arrival proof."""
        if self.status == "halted":
            raise MovementHalted(self.halt_reason or "halted")
        if self.pending is not None:
            raise MovementError("pending action requires record_feedback")
        self.current = self._check_observation(position, elapsed_seconds)
        self._note_arrival(self.current)

    def decide(self, position: Position, elapsed_seconds: float) -> MovementAction | None:
        """Choose the single calibrated pulse with the best predicted reduction."""
        if self.status == "halted":
            raise MovementHalted(self.halt_reason or "halted")
        if self.pending is not None:
            raise MovementError("previous action has no fresh feedback")
        if self.status == "arrived":
            return None
        self.current = self._check_observation(position, elapsed_seconds)
        distance = planar_distance(self.current, self.goal)
        if distance <= self.tolerance:
            # A decision call is not evidence of a new observation.  Only
            # record_feedback/observe may advance arrival confirmations.
            self.status = "confirming-arrival"
            return None
        self.arrival_confirmations = 0
        self.status = "active"
        if self.action_count >= self.max_goal_actions:
            self._halt("action-budget")
        remaining_hold = self.max_total_hold_ms - self.total_hold_ms
        if remaining_hold < self.minimum_pulse_ms:
            self._halt("hold-budget")
        maximum_hold = min(self.maximum_pulse_ms, remaining_hold)
        error_x, error_z = self.goal.x - self.current.x, self.goal.z - self.current.z
        best = None
        for key, vector in sorted(self.calibrations.items()):
            # The tiny bounded range is enumerated so a pulse can approach the
            # reviewed corridor edge without stepping across it.
            candidates = range(self.minimum_pulse_ms, maximum_hold + 1)
            for hold in candidates:
                predicted_position = Position(
                    self.current.x + vector.dx_per_ms * hold,
                    self.current.y,
                    self.current.z + vector.dz_per_ms * hold,
                )
                # Keep 10% of the verified corridor for feedback quantization,
                # animation settling and measured-vs-predicted displacement error.
                # Observed positions still enforce the full hard limit.
                if self._cross_track(predicted_position) > self.max_cross_track * 0.90:
                    continue
                predicted = math.hypot(
                    error_x - vector.dx_per_ms * hold,
                    error_z - vector.dz_per_ms * hold,
                )
                candidate = (predicted, key, hold)
                if best is None or candidate < best:
                    best = candidate
        if best is None:
            self._halt("no-corridor-safe-action")
        predicted, key, hold = best
        if distance - predicted < self.minimum_progress:
            self._halt("no-useful-calibrated-action")
        action = MovementAction(key, hold, distance, predicted)
        self.action_count += 1
        self.total_hold_ms += hold
        self.pending = (action, self.current)
        return action

    def record_feedback(self, position: Position, elapsed_seconds: float) -> FeedbackResult:
        """Apply the next fresh post-release position to the pending decision."""
        if self.status == "halted":
            raise MovementHalted(self.halt_reason or "halted")
        if self.pending is None:
            raise MovementError("there is no pending movement action")
        after = self._check_observation(position, elapsed_seconds)
        action, _before = self.pending
        self.pending = None
        after_distance = planar_distance(after, self.goal)
        progress = action.distance_before - after_distance
        self.feedback_iterations += 1
        self.current = after
        self.no_progress_count = 0 if progress >= self.minimum_progress else self.no_progress_count + 1
        self.divergence_count = 0 if progress >= -self.minimum_progress else self.divergence_count + 1
        if self.divergence_count >= self.divergence_limit:
            self._halt("divergence")
        if self.no_progress_count >= self.no_progress_limit:
            self._halt("no-progress")
        self._note_arrival(after)
        return FeedbackResult(
            action.distance_before,
            after_distance,
            progress,
            self.status,
            self.arrival_confirmations,
            self.feedback_iterations,
        )

