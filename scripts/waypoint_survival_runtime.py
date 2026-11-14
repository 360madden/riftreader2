"""Shared fail-closed survival runtime for the Waypoints CLI and window.

Configuration is read-only.  Preflight performs two independent live telemetry
acquisitions and constructs the action owner, but sends no input.  Route combat
is admitted only with the same exact process/player/target/session identity and
an explicitly qualified UIParent-to-client coordinate basis.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import threading
import time
import uuid

from scripts.survival_live import SurvivalLiveConsumer, assess_incoming, assess_outcome
from scripts.survival_profile import load_survival_profile
from scripts.survival_route_runner import run_survival_route
from scripts.waypoint_survival import VerifiedBindingProfile


ROOT = Path(__file__).resolve().parents[1]


class WaypointSurvivalRuntimeError(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise WaypointSurvivalRuntimeError(reason)


def _finite(value, reason):
    _require(type(value) in (int, float) and math.isfinite(value), reason)
    return float(value)


def _same(left, right):
    return (left.casefold() == right.casefold()
            if isinstance(left, str) and isinstance(right, str) else left == right)


def _geometry_only(frame, ability_id, basis, target):
    """Validate a configured protected rectangle without claiming cast readiness."""
    controls = frame.get("controls") if isinstance(frame, dict) else None
    item = ((controls.get("actions") or {}).get(ability_id)
            if isinstance(controls, dict) else None)
    _require(isinstance(item, dict) and item.get("mapped") is True
             and item.get("abilityId") == ability_id
             and item.get("uniqueLearnedName") is True,
             "configured-action-geometry-unavailable")
    _require(controls.get("space") == "UIParent"
             and controls.get("viewportWidth") == basis["viewportWidth"]
             and controls.get("viewportHeight") == basis["viewportHeight"],
             "ui-parent-client-basis-mismatch")
    left, top, width, height = (_finite(item.get(name), "invalid-action-geometry")
                                for name in ("left", "top", "width", "height"))
    rectangle = {
        "x": round(basis["offsetX"] + left * basis["scaleX"]),
        "y": round(basis["offsetY"] + top * basis["scaleY"]),
        "width": round(width * basis["scaleX"]),
        "height": round(height * basis["scaleY"]),
    }
    _require(rectangle["width"] >= 4 and rectangle["height"] >= 4
             and rectangle["x"] >= 0 and rectangle["y"] >= 0
             and rectangle["x"] + rectangle["width"] <= target["clientWidth"]
             and rectangle["y"] + rectangle["height"] <= target["clientHeight"],
             "configured-action-geometry-outside-client")
    return rectangle


def _player_id(adapter):
    value = getattr(adapter, "unit_key", None)
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        value = 0
    _require(0 < value < 2**64, "survival-player-identity-unavailable")
    return f"u{value:016X}"


def _target(adapter):
    value = getattr(adapter, "target", None)
    _require(isinstance(value, dict), "survival-process-identity-unavailable")
    return value


def _binding(adapter):
    target = _target(adapter)
    host = target.get("machineName", getattr(adapter, "host", None))
    start = target.get("processStartUtcTicks")
    try:
        start = int(start)
    except (TypeError, ValueError):
        start = 0
    result = {"hostName": str(host).upper() if host else None,
              "processId": target.get("processId", getattr(adapter, "pid", None)),
              "processStartUtcTicks": start, "playerId": _player_id(adapter)}
    _require(isinstance(result["hostName"], str) and result["hostName"]
             and type(result["processId"]) is int and result["processId"] > 0
             and result["processStartUtcTicks"] > 0,
             "survival-process-identity-unavailable")
    return result


class _PolicyBackend:
    """Complete policy port built over the single protected action owner."""

    def __init__(self, runtime, actions):
        self.runtime, self.actions = runtime, actions
        self.mode = None
        self.recovery_cast = False
        self.corridor_points = None
        self.faced_target = False

    def telemetry(self):
        value = self.runtime._next_telemetry()
        if self.corridor_points:
            player = value["player"]
            value["encounter"]["onCorridor"] = any(
                math.hypot(player["coordX"] - point[0],
                           player["coordZ"] - point[2]) <= .5
                and abs(player["coordY"] - point[1]) <= .5
                for point in self.corridor_points)
        return value

    def cast(self, ability_id):
        frame = ((self.runtime._latest_report or {}).get("snapshot") or {})
        deadline_seconds = min(5, self.runtime._profile["timing"][
            "actionDeadlineMilliseconds"] / 1000)
        target_id = frame.get("targetId")
        role = next((name for name, configured in self.runtime._profile["abilities"].items()
                     if configured == ability_id), None)
        action = ((self.runtime._latest_report or {}).get("actions") or {}).get(ability_id)
        ability = action.get("ability") if isinstance(action, dict) else None
        ability_target = ability.get("target") if isinstance(ability, dict) else None
        _require(role in {"heal", "defense", "interrupt", "damage"},
                 "survival-action-role-unavailable")
        if role in {"heal", "defense"}:
            _require(_same(ability_target, self.runtime._player_id),
                     "survival-self-action-target-mismatch")
            outcome_target = self.runtime._player_id
        else:
            _require(isinstance(target_id, str) and target_id
                     and _same(target_id, self.runtime._target_id)
                     and _same(ability_target, target_id),
                     "survival-selected-target-unavailable")
            outcome_target = target_id
            if not self.faced_target:
                target = frame.get("target")
                _require(isinstance(target, dict), "survival-target-position-unavailable")
                point = (_finite(target.get("coordX"), "survival-target-position-unavailable"),
                         _finite(target.get("coordZ"), "survival-target-position-unavailable"))
                self.runtime._face_target(point)
                self.faced_target = True
        receipt = self.actions.cast(ability_id)
        baseline = receipt.get("outcomeBaseline") if isinstance(receipt, dict) else None
        baseline_clock = receipt.get("admissionFrameTime") if isinstance(receipt, dict) else None
        _require(type(receipt.get("admissionEpoch")) is int
                 and type(receipt.get("admissionSequence")) is int
                 and type(baseline_clock) in (int, float)
                 and math.isfinite(baseline_clock),
                 "survival-action-admission-generation-unavailable")
        _require(baseline is None or (isinstance(baseline, dict)
                 and type(baseline.get("sequence")) is int
                 and type(baseline.get("clock")) in (int, float)),
                 "survival-action-outcome-baseline-unavailable")
        self.recovery_cast = self.mode == "recovery"
        wall_deadline = self.runtime.clock() + deadline_seconds
        outcome = {"status": "unavailable", "reason": "outcome-window-not-sampled"}
        try:
            while True:
                post = self.runtime._next_telemetry()
                frame = self.runtime._latest_report["snapshot"]
                outcome = assess_outcome(
                    baseline, frame, player_id=self.runtime._player_id,
                    encounter_target_id=target_id, effect_target_id=outcome_target,
                    submission_frame_time=baseline_clock,
                    outcome_deadline_frame_time=baseline_clock + deadline_seconds,
                    ability_id=ability_id,
                    effect_ability_ids=self.runtime._profile["outcomeAbilityIds"][ability_id])
                event = outcome.get("event") if isinstance(outcome, dict) else None
                selection_bound = bool(
                    frame.get("eventScope") == "selected-or-self/1"
                    and _same(frame.get("targetId"), target_id)
                    and isinstance(event, dict)
                    and _same(event.get("selectedTargetId"), target_id)
                    and type(event.get("clock")) in (int, float)
                    and type(baseline_clock) in (int, float)
                    and event["clock"] >= baseline_clock)
                accepted = selection_bound and outcome.get("status") in {
                    "intended-hit-confirmed", "intended-heal-confirmed"}
                if accepted:
                    return {"accepted": True, "delivery": receipt, "outcome": outcome}
                source_expired = (type(frame.get("frameTime")) in (int, float)
                                  and frame["frameTime"] >= baseline_clock + deadline_seconds)
                if post["player"]["dead"] or source_expired or self.runtime.clock() >= wall_deadline:
                    break
                if self.runtime._stop.wait(
                        self.runtime._profile["timing"]["pollMilliseconds"] / 1000):
                    raise WaypointSurvivalRuntimeError("survival-stopped-during-outcome-wait")
        except Exception:
            self.actions.cancel()
            raise
        cleanup = self.actions.cancel()
        return {"accepted": False, "delivery": receipt, "outcome": outcome,
                "cleanup": cleanup}

    def start_combat(self):
        begin = getattr(self.actions, "begin_encounter", None)
        _require(callable(begin), "survival-encounter-reset-unavailable")
        begin()
        self.faced_target = False
        self.mode = "combat"

    def release_combat(self, reason):
        result = self.actions.cancel()
        self.mode = None
        receipt = self.runtime._release_receipt(result, reason)
        if receipt["releaseSucceeded"]:
            self.runtime._target_id = None
        return receipt

    def start_recovery(self):
        self.mode, self.recovery_cast = "recovery", False

    def release_recovery(self, reason):
        if self.recovery_cast:
            result = self.actions.cancel()
            self.recovery_cast = False
            receipt = self.runtime._release_receipt(result, reason)
        else:
            receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                       "inputSent": False, "reason": reason}
        self.mode = None
        return receipt

    def finalize(self, reason="route-finally"):
        """Release any surviving action owner without clearing the STOP latch."""
        if self.mode == "combat":
            return self.release_combat(reason)
        if self.mode == "recovery":
            return self.release_recovery(reason)
        return {"releaseSucceeded": True, "desktopInputsDown": [],
                "inputSent": False, "reason": reason}

    def corridor_reachable(self, points):
        frame = ((self.runtime._latest_report or {}).get("snapshot") or {})
        player = frame.get("player")
        if not isinstance(player, dict) or not isinstance(points, list) or not points:
            return False
        try:
            x, y, z = (float(player[name]) for name in ("coordX", "coordY", "coordZ"))
        except (KeyError, TypeError, ValueError):
            return False
        if not all(math.isfinite(value) for value in (x, y, z)):
            return False
        normalized = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                return False
            try:
                item = tuple(float(value) for value in point)
            except (TypeError, ValueError):
                return False
            if not all(math.isfinite(value) for value in item):
                return False
            normalized.append(item)
        valid = all(math.hypot(b[0] - a[0], b[2] - a[2]) <= 2
                    and abs(b[1] - a[1]) <= 1 for a, b in zip(normalized, normalized[1:]))
        if not valid:
            return False
        nearby = [point for point in normalized
                  if math.hypot(point[0] - x, point[2] - z) <= .5
                  and abs(point[1] - y) <= .5]
        if not nearby:
            return False
        self.corridor_points = normalized
        return True


class WaypointSurvivalRuntime:
    """Own one configured profile and one exact live action session."""

    def __init__(self, *, consumer_factory=SurvivalLiveConsumer,
                 action_factory=None,
                 native_context_reader=None, artifact_root=None,
                 clock=time.monotonic, facing_runner=None):
        self.consumer_factory = consumer_factory
        self.action_factory = action_factory
        self.native_context_reader = native_context_reader
        self.artifact_root = Path(artifact_root or ROOT / "artifacts" / "waypoint-survival")
        self.clock = clock
        self.facing_runner = facing_runner
        self._profile = None
        self._configured_binding = None
        self._configured_target = None
        self._basis = None
        self._consumer = None
        self._adapter = None
        self._latest_report = None
        self._latest_telemetry = None
        self._backend = None
        self._player_id = None
        self._target_id = None
        self._stop = None
        self._no_action_since = None
        self._health_observation = None
        self._active = False
        self._state = "unconfigured"
        self._owner = None
        self._last_action = None
        self._action_diagnostic = None
        self._last_reason = None
        self._encounter_count = 0
        self._lock = threading.RLock()

    def status(self):
        with self._lock:
            diagnostic = getattr(self._backend, "action_diagnostic", None)
            if diagnostic is None:
                diagnostic = self._action_diagnostic
            return {
                "configured": self._profile is not None,
                "profileSource": (self._profile or {}).get("source"),
                "binding": deepcopy(self._configured_binding),
                "coordinateBasisQualified": self._basis is not None,
                "preflightReady": self._backend is not None,
                "active": self._active,
                "state": self._state,
                "owner": self._owner,
                "lastAction": deepcopy(self._last_action),
                "actionDiagnostic": deepcopy(diagnostic),
                "lastReason": self._last_reason,
                "encounterCount": self._encounter_count,
                "sessionId": (self._profile or {}).get("nonce"),
                "inputSent": False,
            }

    def set_coordinate_basis(self, basis):
        # Reuse the profile loader's strict normalized shape indirectly: this
        # setter is for an already qualified runtime result, never calibration.
        required = {"qualified", "space", "viewportWidth", "viewportHeight",
                    "clientWidth", "clientHeight", "scaleX", "scaleY",
                    "offsetX", "offsetY"}
        _require(isinstance(basis, dict) and set(basis) == required
                 and basis.get("qualified") is True
                 and basis.get("space") == "UIParent-to-client-pixels",
                 "ui-parent-client-basis-unqualified")
        normalized = deepcopy(basis)
        for name in ("viewportWidth", "viewportHeight", "scaleX", "scaleY",
                     "offsetX", "offsetY"):
            normalized[name] = _finite(normalized[name], "invalid-ui-parent-basis")
        for name in ("clientWidth", "clientHeight"):
            _require(type(normalized[name]) is int and 64 <= normalized[name] <= 8192,
                     "invalid-ui-parent-basis")
        _require(normalized["viewportWidth"] > 0 and normalized["viewportHeight"] > 0
                 and normalized["scaleX"] > 0 and normalized["scaleY"] > 0,
                 "invalid-ui-parent-basis")
        with self._lock:
            self._basis = normalized
            self._backend = None
        return deepcopy(normalized)

    def configure(self, path, adapter):
        binding = _binding(adapter)
        value = load_survival_profile(path)
        if value["binding"] is not None:
            value = load_survival_profile(path, expected_binding=binding)
        basis = value.get("coordinateBasis")
        with self._lock:
            self._profile = value
            self._configured_binding = binding
            target = _target(adapter)
            self._configured_target = {
                "executableSha256": target.get("executableSha256"),
                "hwnd": target.get("hwnd", target.get("windowHandle")),
            }
            self._basis = deepcopy(basis)
            self._consumer = self._backend = self._latest_report = None
            self._latest_telemetry = None
            self._target_id = None
            self._health_observation = None
            self._active = False
            self._state = "configured"
            self._owner = self._last_action = self._last_reason = None
            self._action_diagnostic = None
            self._encounter_count = 0
        return self.status()

    def _observe_state(self, event):
        if not isinstance(event, dict):
            return
        survival = event.get("survival")
        if event.get("status") != "survival-state" or not isinstance(survival, dict):
            return
        with self._lock:
            self._active = survival.get("active") is True
            self._state = str(survival.get("state", self._state))
            self._owner = survival.get("owner")
            self._last_action = deepcopy(survival.get("lastAction"))
            self._last_reason = survival.get("reason")
            if "actionDiagnostic" in survival:
                self._action_diagnostic = deepcopy(survival.get("actionDiagnostic"))
            count = survival.get("encounterCount")
            if type(count) is int and count >= 0:
                self._encounter_count = count

    def _assert_identity(self, adapter):
        current = _binding(adapter)
        _require(current == self._configured_binding,
                 "survival-configured-identity-changed")
        target = _target(adapter)
        _require(_same(target.get("executableSha256"),
                       self._configured_target.get("executableSha256"))
                 and str(target.get("hwnd", target.get("windowHandle")))
                     == str(self._configured_target.get("hwnd")),
                 "survival-build-or-window-identity-changed")
        return current

    def _consumer_for(self, adapter):
        target = _target(adapter)
        output = self.artifact_root / ("preflight-" + uuid.uuid4().hex)
        return self.consumer_factory(
            expected_host=self._configured_binding["hostName"],
            physical_pid=target["processId"], session_id=self._profile["nonce"],
            seed_index=None, output=output)

    def cancel_reference(self, *, max_age_seconds=5.0):
        """Forward cached cleanup geometry without acquiring another live frame."""
        with self._lock:
            _require(self._consumer is not None, "survival-preflight-required")
            reference = getattr(self._consumer, "cancel_reference", None)
            _require(callable(reference), "survival-cancel-reference-unavailable")
            return reference(max_age_seconds=max_age_seconds)

    def _native_context(self, adapter):
        if self.native_context_reader is not None:
            return self.native_context_reader(adapter)
        from scripts import physical_rift
        target = _target(adapter)
        command = [str(physical_rift.NATIVE_EXE), "sample-current-survival",
                   "--expected-host", self._configured_binding["hostName"],
                   "--pid", str(target["processId"]), "--expect-start-ticks",
                   str(target["processStartUtcTicks"]), "--expect-sha256",
                   target["executableSha256"], "--expect-player-key",
                   str(getattr(adapter, "unit_key")), "--json"]
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=3)
        try:
            result = json.loads(completed.stdout.splitlines()[-1])
        except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WaypointSurvivalRuntimeError(
                "native-survival-context-unavailable") from exc
        requested = result.get("requested")
        _require(completed.returncode == 0 and result.get("status") == "complete"
                 and result.get("inputSent") is False and isinstance(requested, dict)
                 and _same(requested.get("host"), self._configured_binding["hostName"])
                 and requested.get("pid") == target["processId"]
                 and str(requested.get("processStartUtcTicks"))
                     == str(target["processStartUtcTicks"])
                 and _same(requested.get("executableSha256"),
                           target["executableSha256"])
                 and str(requested.get("playerKey")) == str(adapter.unit_key),
                 "native-survival-context-identity-mismatch")
        return result.get("nativeValues")

    def _validate_report(self, report):
        _require(isinstance(report, dict) and report.get("telemetryReady") is True,
                 "advancing-survival-telemetry-unavailable")
        _require(report.get("sessionId") == self._profile["nonce"]
                 and _same(report.get("playerId"), self._player_id)
                 and isinstance(report.get("snapshot"), dict)
                 and report["snapshot"].get("status") == "observed"
                 and report["snapshot"].get("eventScope") == "selected-or-self/1",
                 "survival-telemetry-identity-mismatch")
        catalog = report.get("catalog")
        _require(isinstance(catalog, dict), "learned-ability-catalog-unavailable")
        actions = report.get("actions")
        _require(isinstance(actions, dict), "profile-action-readiness-unavailable")
        for ability_id in self._profile["actions"]:
            action = actions.get(ability_id)
            ability = action.get("ability") if isinstance(action, dict) else None
            _require(isinstance(action, dict) and isinstance(ability, dict)
                     and action.get("abilityId") == ability_id
                     and ability.get("idNew", ability.get("id")) == ability_id
                     and action.get("uniqueLearnedName") is True
                     and action.get("mapped") is True,
                     "configured-learned-action-unavailable")

    def _action_target(self, adapter):
        target = deepcopy(_target(adapter))
        target["clientWidth"] = self._basis["clientWidth"]
        target["clientHeight"] = self._basis["clientHeight"]
        return target

    def _normalize(self, report, native):
        frame = report["snapshot"]
        player, target = frame.get("player"), frame.get("target")
        _require(isinstance(player, dict) and (target is None or isinstance(target, dict))
                 and isinstance(native, dict), "survival-policy-telemetry-unavailable")
        target = target or {}
        native_player = native.get("player")
        selected = native.get("selectedTarget")
        _require(isinstance(native_player, dict) and isinstance(selected, dict),
                 "native-survival-context-unavailable")
        _require(str(native_player.get("key")) == str(getattr(self._adapter, "unit_key", "")),
                 "native-survival-player-mismatch")
        native_target_key = selected.get("key")
        try:
            native_target_number = int(native_target_key)
        except (TypeError, ValueError, OverflowError):
            native_target_number = 0
        native_target = (f"u{native_target_number:016X}"
                         if 0 < native_target_number < 2**64 else None)
        _require(_same(native_target, frame.get("targetId")),
                 "native-survival-target-mismatch")
        combat = (native_player.get("combat") or {}).get("value")
        _require(type(combat) is bool, "native-survival-combat-unavailable")
        addon_health = _finite(player.get("health"), "player-health-unavailable")
        addon_health_max = _finite(player.get("healthMax"), "player-health-unavailable")
        _require(addon_health_max > 0 and 0 <= addon_health <= addon_health_max,
                 "player-health-unavailable")
        native_health = native_player.get("health") or {}
        native_current = native_health.get("current")
        native_maximum = native_health.get("maximum")
        _require(native_health.get("available") is True
                 and type(native_current) in (int, float)
                 and type(native_maximum) in (int, float)
                 and math.isfinite(native_current) and math.isfinite(native_maximum)
                 and native_maximum > 0 and 0 <= native_current <= native_maximum
                 and native_maximum == addon_health_max,
                 "native-addon-health-mismatch")
        native_dead = native_health.get("dead")
        _require(native_health.get("deadAvailable") is True
                 and type(native_dead) is bool,
                 "native-survival-death-unavailable")
        dead = native_dead or native_current == 0
        result_player = {"dead": dead, "inCombat": combat,
                         "healthPct": native_current * 100.0 / native_maximum,
                         "healthReconciliation": (
                             "matched" if native_current == addon_health
                             else "changed-during-acquisition"),
                         "coordX": _finite(player.get("coordX"), "player-coordinate-unavailable"),
                         "coordY": _finite(player.get("coordY"), "player-coordinate-unavailable"),
                         "coordZ": _finite(player.get("coordZ"), "player-coordinate-unavailable")}
        resource_kind = self._profile["resourceKind"]
        if resource_kind == "absolute-power":
            result_player.update(resourceKind="absolute-power",
                                 resourceCurrent=_finite(
                                     player.get("power"), "player-power-unavailable"))
            _require(result_player["resourceCurrent"] >= 0,
                     "player-power-unavailable")
        else:
            power = _finite(player.get("power"), "player-power-unavailable")
            maximum = _finite(player.get("powerMax"), "player-power-max-unavailable")
            _require(maximum > 0 and 0 <= power <= maximum,
                     "player-power-max-unavailable")
            result_player["resourcePct"] = power * 100.0 / maximum

        target_id = frame.get("targetId")
        selected_exists = target_id is not None
        player_level = player.get("level")
        target_level = target.get("level")
        native_player_level = native_player.get("level") or {}
        native_target_level = selected.get("level") or {}
        _require(native_player_level.get("available") is True
                 and native_player_level.get("value") == player_level,
                 "native-addon-level-mismatch")
        _require(not selected_exists or (native_target_level.get("available") is True
                 and native_target_level.get("value") == target_level),
                 "native-addon-target-level-mismatch")
        known = (type(player_level) in (int, float)
                 and type(target_level) in (int, float)
                 and math.isfinite(player_level) and math.isfinite(target_level))
        target_health, target_max = target.get("health"), target.get("healthMax")
        target_pct = None
        native_target_health = selected.get("health") or {}
        target_reconciliation = None
        if selected_exists:
            native_target_current = native_target_health.get("current")
            native_target_maximum = native_target_health.get("maximum")
            _require(type(target_health) in (int, float)
                     and type(target_max) in (int, float)
                     and math.isfinite(target_health) and math.isfinite(target_max)
                     and target_max > 0 and 0 <= target_health <= target_max
                     and selected.get("available") is True
                     and native_target_health.get("available") is True
                     and type(native_target_current) in (int, float)
                     and type(native_target_maximum) in (int, float)
                     and math.isfinite(native_target_current)
                     and math.isfinite(native_target_maximum)
                     and native_target_maximum > 0
                     and 0 <= native_target_current <= native_target_maximum
                     and native_target_maximum == target_max,
                     "native-addon-target-health-mismatch")
            target_pct = native_target_current * 100.0 / native_target_maximum
            target_reconciliation = ("matched"
                                     if native_target_current == target_health
                                     else "changed-during-acquisition")
            native_target_dead = native_target_health.get("dead")
            _require(native_target_health.get("deadAvailable") is True
                     and type(native_target_dead) is bool,
                     "native-survival-target-death-unavailable")
            target_dead = native_target_dead or native_target_current == 0
        else:
            target_dead = False
        relation = target.get("relation")
        hostile = isinstance(relation, str) and relation.casefold() == "hostile"
        incoming_exact = bool(isinstance(target_id, str) and assess_incoming(
            frame, player_id=self._player_id,
            encounter_target_id=target_id).get("status") == "incoming-damage-observed")
        # Combat without the configured live hostile target is deliberately an
        # unknown encounter: policy retreats and cannot select a cast role.
        present = combat and not target_dead
        if (present and selected_exists and self._target_id is None
                and (hostile or incoming_exact)):
            self._target_id = target_id
        configured = self._target_id is not None and _same(target_id, self._target_id)
        threat_known = bool(present and selected_exists and configured and known
                            and (hostile or incoming_exact))
        encounter = {"present": present, "casting": False,
                     "threatKnown": threat_known,
                     "levelDelta": (float(target_level - player_level)
                                    if threat_known else None),
                     "losing": False, "incomingDamageObserved": incoming_exact,
                     "targetHealthReconciliation": target_reconciliation}
        if self._profile["abilities"].get("interrupt") is not None and threat_known:
            _require(type(target.get("casting")) is bool,
                     "target-cast-state-unavailable")
            encounter["casting"] = target["casting"]

        abilities = {}
        for ability_id in self._profile["actions"]:
            action = report.get("actions", {}).get(ability_id)
            _require(isinstance(action, dict), "profile-action-readiness-unavailable")
            ability = action.get("ability")
            _require(isinstance(ability, dict), "profile-action-readiness-unavailable")
            learned = (action.get("abilityId") == ability_id
                       and ability.get("idNew", ability.get("id")) == ability_id
                       and action.get("uniqueLearnedName") is True
                       and action.get("mapped") is True)
            record = {"learned": learned,
                      "ready": (action.get("readiness") or {}).get("status") == "ready",
                      "usable": action.get("visible") is True and action.get("mapped") is True}
            if resource_kind == "absolute-power":
                record["resourceCost"] = _finite(
                    ability.get("costPower"), "ability-power-cost-unavailable")
            else:
                _require(False, "percentage-ability-cost-normalization-unavailable")
            abilities[ability_id] = record
        now = self.clock()
        prior_health = self._health_observation
        declining = False
        if prior_health is not None:
            prior_pct, prior_at = prior_health
            drop = prior_pct - result_player["healthPct"]
            declining = bool(drop > 0 and (result_player["healthPct"] < 65
                                           or drop >= 15 and now - prior_at <= 5))
        self._health_observation = (result_player["healthPct"], now)
        ready_action = any(record["learned"] and record["ready"] and record["usable"]
                           and record["resourceCost"] <= result_player["resourceCurrent"]
                           for record in abilities.values())
        if present and not ready_action:
            if self._no_action_since is None:
                self._no_action_since = now
        else:
            self._no_action_since = None
        no_action_timeout = bool(self._no_action_since is not None
                                 and now - self._no_action_since >= 3)
        encounter["losing"] = declining or no_action_timeout
        encounter["healthDeclining"] = declining
        encounter["noActionTimedOut"] = no_action_timeout
        return {"fresh": True, "identityValid": True, "readinessFresh": True,
                "player": result_player, "encounter": encounter,
                "abilities": abilities}

    def _next_telemetry(self):
        _require(self._consumer is not None and self._adapter is not None,
                 "survival-preflight-required")
        report = self._consumer.snapshot()
        self._validate_report(report)
        telemetry = self._normalize(report, self._native_context(self._adapter))
        self._latest_report, self._latest_telemetry = report, telemetry
        return deepcopy(telemetry)

    def _fresh_action_report(self):
        """Acquire and publish a newer admitted frame immediately before an action."""
        self._next_telemetry()
        return deepcopy(self._latest_report)

    def _build_actions(self, adapter, stop):
        if self.action_factory is not None:
            return self.action_factory(
                adapter=adapter, snapshot=self._fresh_action_report,
                profile=deepcopy(self._profile), stop=stop)
        from scripts.survival_actions import build_survival_actions
        return build_survival_actions(
            adapter, self._fresh_action_report, deepcopy(self._profile), stop)

    def _face_target(self, point):
        _require(self._adapter is not None and self._stop is not None
                 and not self._stop.is_set(), "survival-stopped-before-facing")
        runner = self.facing_runner
        if runner is None:
            from scripts.physical_waypoints import run_facing
            runner = run_facing
        result = runner(self._adapter, self._stop, point=point)
        _require(isinstance(result, dict) and result.get("status") == "facing"
                 and result.get("allPulsesReleased") is True,
                 "survival-facing-release-unverified")
        return result

    @staticmethod
    def _release_receipt(value, reason):
        if isinstance(value, dict) and value.get("status") == "already-clean":
            return {"releaseSucceeded": True, "desktopInputsDown": [],
                    "inputSent": False, "reason": reason}
        receipt = value.get("receipt") if isinstance(value, dict) else None
        return {"releaseSucceeded": bool(isinstance(receipt, dict)
                                          and receipt.get("releaseSucceeded") is True
                                          and receipt.get("desktopInputsDown") == []),
                "desktopInputsDown": (receipt or {}).get("desktopInputsDown", ["unknown"]),
                "inputSent": (receipt or {}).get("inputSent", False), "reason": reason}

    def preflight(self, adapter, stop):
        _require(hasattr(stop, "is_set") and not stop.is_set(),
                 "survival-stopped-before-preflight")
        with self._lock:
            _require(self._profile is not None, "survival-profile-not-configured")
            _require(self._basis is not None, "ui-parent-client-basis-unqualified")
            self._assert_identity(adapter)
            self._adapter, self._player_id = adapter, _player_id(adapter)
            self._stop = stop
            consumer = self._consumer_for(adapter)
            baseline = consumer.snapshot()
            _require(baseline.get("baseline") is True
                     and baseline.get("telemetryReady") is False,
                     "survival-baseline-unavailable")
            _require(not stop.is_set(), "survival-stopped-during-preflight")
            current = consumer.snapshot()
            self._consumer = consumer
            self._latest_report = current
            self._validate_report(current)
            telemetry = self._normalize(current, self._native_context(adapter))
            self._latest_telemetry = telemetry
            frame = current["snapshot"]
            controls = frame.get("controls") or {}
            _require(controls.get("viewportWidth") == self._basis["viewportWidth"]
                     and controls.get("viewportHeight") == self._basis["viewportHeight"],
                     "ui-parent-client-basis-mismatch")
            target = self._action_target(adapter)
            for ability_id in self._profile["actions"]:
                _geometry_only(frame, ability_id, self._basis, target)
            actions = self._build_actions(adapter, stop)
            self._backend = _PolicyBackend(self, actions)
            self._active = False
            self._state = "ready"
            self._owner = None
            self._last_reason = None
            return {"status": "ready", "telemetryReady": True,
                    "coordinateBasisQualified": True,
                    "playerId": self._player_id, "targetId": frame.get("targetId"),
                    "sequence": current.get("sequence"), "inputSent": False}

    def _verified_profile(self):
        abilities, thresholds = self._profile["abilities"], self._profile["thresholds"]
        return VerifiedBindingProfile(
            damage=abilities["damage"], heal=abilities.get("heal"),
            defense=abilities.get("defense"), interrupt=abilities.get("interrupt"),
            resource_kind=self._profile["resourceKind"],
            heal_below=thresholds["healBelowPct"],
            defend_below=thresholds["defendBelowPct"],
            retreat_below=thresholds["retreatBelowPct"],
            recover_health=thresholds["recoverHealthPct"],
            recover_resource=thresholds["recoverResourcePct"],
            recover_resource_absolute=thresholds.get("recoverResourceAbsolute", 20),
            maximum_level_delta=thresholds["maximumLevelDelta"])

    def route_runner(self, adapter, points, stop, emit, face_waypoints=True,
                     entry_check=None):
        self.preflight(adapter, stop)
        with self._lock:
            self._active, self._state, self._owner = True, "travel", "movement"
            self._last_reason = None

        def observed(event):
            self._observe_state(event)
            emit(event)

        terminal, reason = "completed", None
        try:
            return run_survival_route(
                adapter, points, stop, observed, profile=self._verified_profile(),
                telemetry=self._backend.telemetry, action_backend=self._backend,
                face_waypoints=face_waypoints, entry_check=entry_check,
                wait_seconds=self._profile["timing"]["pollMilliseconds"] / 1000,
                retreat_max_seconds=self._profile["retreat"]["maximumSeconds"],
                minimum_trail_points=self._profile["retreat"]["minimumTrailPoints"])
        except BaseException as exc:
            from scripts.physical_waypoints import Stopped
            terminal = "stopped" if isinstance(exc, Stopped) else "halted"
            reason = str(exc)
            raise
        finally:
            cleanup_error = None
            try:
                self._backend.finalize()
            except BaseException as exc:
                cleanup_error = exc
                terminal, reason = "halted", "cleanup failed: " + str(exc)
            terminal_event = {"status": "survival-state", "survival": {
                "active": False, "state": terminal, "owner": None,
                "lastAction": deepcopy(self._last_action), "reason": reason,
                "actionDiagnostic": deepcopy(
                    getattr(self._backend, "action_diagnostic", None)),
                "encounterCount": self._encounter_count, "inputSent": False}}
            self._observe_state(terminal_event)
            emit(terminal_event)
            if cleanup_error is not None:
                raise cleanup_error
