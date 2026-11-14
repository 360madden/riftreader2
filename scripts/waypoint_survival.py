"""Small callback-driven survival policy for supervised waypoint playback.

This module owns no reader, key sender, route store, GUI, or reservation.  Its
ports must retain those existing contracts.  It never invents ability names or
targets: the sole profile is constructed from exact, externally verified
learned bindings.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Callable

from scripts.player_action_coordinator import PlayerActionCoordinator


class SurvivalPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedBindingProfile:
    """One explicit role profile populated from a verified learned inventory."""

    damage: str
    heal: str | None = None
    defense: str | None = None
    interrupt: str | None = None
    resource_kind: str = "percent"
    heal_below: float = 45.0
    defend_below: float = 65.0
    retreat_below: float = 25.0
    recover_health: float = 80.0
    recover_resource: float = 35.0
    recover_resource_absolute: float = 20.0
    maximum_level_delta: int = 2

    def __post_init__(self):
        if not isinstance(self.damage, str) or not self.damage.strip():
            raise ValueError("an exact learned damage binding is required")
        optional = (self.heal, self.defense, self.interrupt)
        if any(value is not None and (not isinstance(value, str) or not value.strip())
               for value in optional):
            raise ValueError("optional bindings must be absent or exact learned identifiers")
        bindings = [value for value in (*optional, self.damage) if value is not None]
        if len(set(bindings)) != len(bindings):
            raise ValueError("present learned bindings must be distinct")
        if self.resource_kind not in {"percent", "percentage", "absolute-power"}:
            raise ValueError("resource kind must be percent or absolute-power")
        values = (self.heal_below, self.defend_below, self.retreat_below, self.recover_health,
                  self.recover_resource)
        if (any(type(value) not in (int, float) or not math.isfinite(value)
                or not 0 <= value <= 100 for value in values)
                or self.heal_below > self.defend_below
                or self.defend_below > self.recover_health):
            raise ValueError("invalid survival thresholds")
        if type(self.maximum_level_delta) is not int or self.maximum_level_delta < 0:
            raise ValueError("invalid maximum level delta")
        if (type(self.recover_resource_absolute) not in (int, float)
                or not math.isfinite(self.recover_resource_absolute)
                or self.recover_resource_absolute < 0):
            raise ValueError("invalid absolute recovery resource threshold")

    @property
    def roles(self):
        return {role: binding for role, binding in
                (("heal", self.heal), ("defense", self.defense),
                 ("interrupt", self.interrupt), ("damage", self.damage))
                if binding is not None}


@dataclass(frozen=True)
class SurvivalPorts:
    telemetry: Callable[[], dict]
    cast: Callable[[str], dict]
    start_movement: Callable[[str, list, object], None]
    release_movement: Callable[[str], dict]
    redirect_movement: Callable[[str, list, object], None]
    start_combat: Callable[[], None]
    release_combat: Callable[[str], dict]
    start_recovery: Callable[[], None]
    release_recovery: Callable[[str], dict]
    corridor_reachable: Callable[[list], bool]

    def __post_init__(self):
        if any(not callable(getattr(self, name)) for name in self.__dataclass_fields__):
            raise TypeError("all survival ports must be callable")


def _percent(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        raise SurvivalPolicyError("invalid-" + name)
    return float(value)


class WaypointSurvivalRunner:
    STATES = {"travel", "encounter", "fight", "retreat", "recover", "rejoin", "halt"}

    def __init__(self, profile: VerifiedBindingProfile, ports: SurvivalPorts,
                 *, coordinator=None, checkpoint=None, pending_leg=None,
                 finish_after_retreat=False):
        if not isinstance(profile, VerifiedBindingProfile) or not isinstance(ports, SurvivalPorts):
            raise TypeError("verified profile and survival ports are required")
        self.profile, self.ports = profile, ports
        self.coordinator = coordinator or PlayerActionCoordinator()
        self.state = "travel"
        self.checkpoint = deepcopy(checkpoint)
        self.pending_leg = deepcopy(pending_leg)
        self.trail = []
        self.last_action = None
        self.steps = 0
        self.interrupted_state = None
        self.failure_detail = None
        self.finish_after_retreat = finish_after_retreat is True
        self.safe_retreat_completed = False

    def snapshot(self):
        return {"version": 1, "state": self.state, "checkpoint": deepcopy(self.checkpoint),
                "pendingLeg": deepcopy(self.pending_leg), "knownTrailPoints": len(self.trail),
                "lastAction": deepcopy(self.last_action), "steps": self.steps,
                "interruptedState": self.interrupted_state,
                "failureDetail": self.failure_detail,
                "safeRetreatCompleted": self.safe_retreat_completed,
                "coordinator": self.coordinator.snapshot(), "inputSent": False}

    def _start_move(self, mode, points):
        return lambda: self.ports.start_movement(
            mode, deepcopy(points), deepcopy(self.pending_leg))

    def start(self):
        self.state = "travel"
        self.interrupted_state = None
        self.failure_detail = None
        self.coordinator.new_run(self._start_move("travel", []), self.ports.release_movement)
        return self.snapshot()

    def resume(self):
        mode = ("rejoin" if self.interrupted_state in
                {"encounter", "fight", "retreat", "recover", "rejoin"} else "travel")
        points = self._reverse_trail() if mode == "rejoin" else []
        if mode == "rejoin" and not self._reachable(points):
            raise SurvivalPolicyError("known rejoin corridor unavailable")
        self.state = mode
        self.interrupted_state = None
        self.coordinator.resume(self._start_move(mode, points), self.ports.release_movement)
        return self.snapshot()

    def operator_stop(self):
        self.interrupted_state = self.state
        self.state = "halt"
        self.coordinator.operator_stop()
        return self.snapshot()

    def retry_release(self, release=None):
        """Explicitly retry uncertain cleanup; successful cleanup still needs Resume/new run."""
        self.coordinator.retry_release(release or self.ports.release_movement)
        return self.snapshot()

    def route_checkpoint_advanced(self, checkpoint, pending_leg):
        """Accept playback-owned progress only during ordinary forward travel."""
        if self.state != "travel" or self.coordinator.snapshot()["activeAction"] != "movement":
            raise SurvivalPolicyError("route checkpoint cannot advance while interrupted")
        self.checkpoint, self.pending_leg = deepcopy(checkpoint), deepcopy(pending_leg)

    def record_route_trail_point(self, point):
        """Retain a playback-confirmed, already reached route point for reverse travel."""
        if (not isinstance(point, (list, tuple)) or len(point) not in (2, 3)
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in point)):
            raise ValueError("trail point must contain finite coordinates")
        value = tuple(float(item) for item in point)
        if not self.trail or self.trail[-1] != value:
            self.trail.append(value)
            self.trail = self.trail[-256:]

    def _reverse_trail(self):
        return [list(point) for point in reversed(self.trail)]

    def _reachable(self, points):
        if not points:
            self.failure_detail = "corridor-unavailable: retained trail is empty"
            return False
        try:
            reachable = self.ports.corridor_reachable(deepcopy(points))
        except (KeyError, TypeError, ValueError, SurvivalPolicyError) as exc:
            self.failure_detail = f"{type(exc).__name__}: {exc}"
            return False
        if reachable is not True:
            self.failure_detail = (
                "corridor-unavailable: retained corridor qualification returned false")
            return False
        self.failure_detail = None
        return True

    def _critical(self, reason, detail=None):
        if detail is not None:
            self.failure_detail = f"{type(detail).__name__}: {detail}"
        self.interrupted_state = self.state
        self.state = "halt"
        self.coordinator.critical(reason)

    def _telemetry(self):
        value = self.ports.telemetry()
        if (not isinstance(value, dict) or value.get("fresh") is not True
                or value.get("identityValid") is not True
                or value.get("readinessFresh") is not True):
            raise SurvivalPolicyError("critical telemetry unavailable")
        player, encounter, abilities = (value.get(name) for name in
                                         ("player", "encounter", "abilities"))
        if not all(isinstance(item, dict) for item in (player, encounter, abilities)):
            raise SurvivalPolicyError("critical telemetry unavailable")
        if type(player.get("dead")) is not bool or type(player.get("inCombat")) is not bool:
            raise SurvivalPolicyError("critical telemetry unavailable")
        player = dict(player)
        abilities = dict(abilities)
        player["healthPct"] = _percent(player.get("healthPct"), "health")
        if "resourcePct" in player:
            player["resourcePct"] = _percent(player.get("resourcePct"), "resource")
            player["resourceMode"] = "percent"
            player["resourceAvailable"] = player["resourcePct"]
        elif (player.get("resourceKind") == "absolute-power"
              and type(player.get("resourceCurrent")) in (int, float)
              and math.isfinite(player["resourceCurrent"])
              and player["resourceCurrent"] >= 0):
            player["resourceMode"] = "absolute-power"
            player["resourceAvailable"] = float(player["resourceCurrent"])
        else:
            raise SurvivalPolicyError("invalid-resource")
        expected_resource = ("percent" if self.profile.resource_kind == "percentage"
                             else self.profile.resource_kind)
        if player["resourceMode"] != expected_resource:
            raise SurvivalPolicyError("profile-resource-kind-mismatch")
        if type(encounter.get("present")) is not bool:
            raise SurvivalPolicyError("critical telemetry unavailable")
        for binding in self.profile.roles.values():
            record = abilities.get(binding)
            if (not isinstance(record, dict) or record.get("learned") is not True
                    or type(record.get("ready")) is not bool
                    or type(record.get("usable")) is not bool):
                raise SurvivalPolicyError("verified binding readiness unavailable")
            cost_key = ("resourceCost" if player["resourceMode"] == "absolute-power"
                        else "resourceCostPct")
            cost = record.get(cost_key)
            if (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0
                    or player["resourceMode"] == "percent" and cost > 100):
                raise SurvivalPolicyError("verified binding resource cost unavailable")
            record = dict(record, resourceCostNormalized=float(cost))
            abilities[binding] = record
        return value, player, encounter, abilities

    @staticmethod
    def _available(record, resource):
        return (record["learned"] is True and record["ready"] is True
                and record["usable"] is True and record["resourceCostNormalized"] <= resource)

    def _resource_recovered(self, player):
        threshold = (self.profile.recover_resource_absolute
                     if player["resourceMode"] == "absolute-power"
                     else self.profile.recover_resource)
        return player["resourceAvailable"] >= threshold

    def _choose_action(self, player, encounter, abilities):
        roles = self.profile.roles
        if ("interrupt" in roles and encounter.get("casting") is True and self._available(
                abilities[roles["interrupt"]], player["resourceAvailable"])):
            return "interrupt", roles["interrupt"]
        if ("heal" in roles and player["healthPct"] <= self.profile.heal_below and self._available(
                abilities[roles["heal"]], player["resourceAvailable"])):
            return "heal", roles["heal"]
        if ("defense" in roles and player["healthPct"] <= self.profile.defend_below and self._available(
                abilities[roles["defense"]], player["resourceAvailable"])):
            return "defense", roles["defense"]
        if self._available(abilities[roles["damage"]], player["resourceAvailable"]):
            return "damage", roles["damage"]
        return None

    def _unsafe(self, player, encounter):
        known = encounter.get("threatKnown")
        delta, losing = encounter.get("levelDelta"), encounter.get("losing")
        if known is not True or type(losing) is not bool:
            return True
        if type(delta) not in (int, float) or not math.isfinite(delta):
            return True
        return (player["healthPct"] <= self.profile.retreat_below or losing
                or delta > self.profile.maximum_level_delta)

    def _begin_retreat(self):
        points = self._reverse_trail()
        if not self._reachable(points):
            self._critical("critical-unavailable")
            return
        self.state = "retreat"
        self.coordinator.combat_ready(self._start_move("retreat", points),
                                      self.ports.release_movement)

    def begin_safe_retreat(self):
        """Start a caller-qualified safeward retreat without another combat action."""
        if not self.finish_after_retreat or self.state != "travel":
            raise SurvivalPolicyError("terminal safe retreat is unavailable")
        try:
            _, player, _encounter, _abilities = self._telemetry()
        except (SurvivalPolicyError, KeyError, TypeError, ValueError) as exc:
            self._critical("critical-unavailable", exc)
            return self.snapshot()
        if player["dead"]:
            self._critical("death")
            return self.snapshot()
        points = self._reverse_trail()
        if not self._reachable(points):
            self._critical("critical-unavailable")
            return self.snapshot()
        self.state = "retreat"
        self.ports.redirect_movement("retreat", points, deepcopy(self.pending_leg))
        return self.snapshot()

    def _begin_recovery_from_movement(self):
        # The coordinator has no movement→recovery shortcut.  Use its two
        # confirmed handoffs; the combat start callback does not send an action.
        self.coordinator.encounter(self.ports.start_combat, self.ports.release_combat)
        if self.coordinator.snapshot()["activeAction"] == "combat":
            self.state = "recover"
            self.coordinator.combat_needs_recovery(
                self.ports.start_recovery, self.ports.release_recovery)

    def step(self):
        if self.coordinator.snapshot()["latchReason"] is not None:
            self.state = "halt"
            return self.snapshot()
        self.steps += 1
        try:
            _, player, encounter, abilities = self._telemetry()
        except (SurvivalPolicyError, KeyError, TypeError, ValueError) as exc:
            self._critical("critical-unavailable", exc)
            return self.snapshot()
        if player["dead"]:
            self._critical("death")
            return self.snapshot()

        if self.state == "travel":
            if encounter["present"]:
                self.state = "encounter"
                state = self.coordinator.encounter(
                    self.ports.start_combat, self.ports.release_combat)
                if state["activeAction"] == "combat":
                    self.state = "fight"
                else:
                    self.interrupted_state, self.state = "encounter", "halt"
            elif encounter.get("offCorridor") is True:
                points = self._reverse_trail()
                if not self._reachable(points):
                    self._critical("critical-unavailable")
                else:
                    self.state = "rejoin"
                    self.ports.redirect_movement("rejoin", points, deepcopy(self.pending_leg))

        elif self.state == "fight":
            if not encounter["present"] and not player["inCombat"]:
                if (player["healthPct"] < self.profile.recover_health
                        or not self._resource_recovered(player)):
                    self.state = "recover"
                    self.coordinator.combat_needs_recovery(
                        self.ports.start_recovery, self.ports.release_recovery)
                else:
                    points = self._reverse_trail()
                    if not self._reachable(points):
                        self._critical("critical-unavailable")
                    else:
                        self.state = "rejoin"
                        self.coordinator.combat_ready(self._start_move("rejoin", points),
                                                      self.ports.release_movement)
            elif self._unsafe(player, encounter):
                self._begin_retreat()
            else:
                chosen = self._choose_action(player, encounter, abilities)
                if chosen is not None:
                    role, binding = chosen
                    receipt = self.ports.cast(binding)
                    if (isinstance(receipt, dict)
                            and receipt.get("encounterEnded") is True
                            and receipt.get("accepted") is False):
                        # A fresh action admission may observe that the target
                        # ended after policy selection but before any owned
                        # input.  The next fresh step performs the ordinary
                        # fight-end/recovery handoff.
                        pass
                    elif (not isinstance(receipt, dict)
                          or receipt.get("accepted") is not True):
                        self._critical("critical-unavailable")
                    else:
                        self.last_action = {"role": role, "binding": binding,
                                            "receipt": deepcopy(receipt)}

        elif self.state == "retreat":
            if not encounter["present"] and not player["inCombat"]:
                if (player["healthPct"] < self.profile.recover_health
                        or not self._resource_recovered(player)):
                    self._begin_recovery_from_movement()
                elif self.finish_after_retreat:
                    self.state = "travel"
                    self.safe_retreat_completed = True
                    self.ports.redirect_movement(
                        "travel", [], deepcopy(self.pending_leg))
                else:
                    self.state = "rejoin"
                    self.ports.redirect_movement(
                        "rejoin", self._reverse_trail(), deepcopy(self.pending_leg))

        elif self.state == "recover":
            ready = (not encounter["present"] and not player["inCombat"]
                     and player["healthPct"] >= self.profile.recover_health
                     and self._resource_recovered(player))
            if ready:
                if self.finish_after_retreat:
                    self.state = "travel"
                    self.safe_retreat_completed = True
                    self.coordinator.recovery_ready(
                        self._start_move("travel", []), self.ports.release_movement)
                else:
                    points = self._reverse_trail()
                    if not self._reachable(points):
                        self._critical("critical-unavailable")
                    else:
                        self.state = "rejoin"
                        self.coordinator.recovery_ready(self._start_move("rejoin", points),
                                                        self.ports.release_movement)

        elif self.state == "rejoin":
            if encounter["present"]:
                self.state = "encounter"
                state = self.coordinator.encounter(
                    self.ports.start_combat, self.ports.release_combat)
                if state["activeAction"] == "combat":
                    self.state = "fight"
                else:
                    self.interrupted_state, self.state = "encounter", "halt"
            elif encounter.get("onCorridor") is True:
                self.ports.redirect_movement("travel", [], deepcopy(self.pending_leg))
                self.state = "travel"
        return self.snapshot()

    def run(self, max_steps=100):
        if type(max_steps) is not int or not 1 <= max_steps <= 10000:
            raise ValueError("max_steps must be in 1..10000")
        result = self.snapshot()
        for _ in range(max_steps):
            result = self.step()
            if result["state"] == "halt":
                break
        return result
