from types import SimpleNamespace
import math
import threading
import unittest
from unittest.mock import patch

from scripts.survival_route_runner import (_coalesce_retained_corridor,
                                            _corridor_arrival,
                                            run_survival_route)
from scripts.waypoint_survival import VerifiedBindingProfile


PROFILE = VerifiedBindingProfile(damage="ability:actual-damage-id")


def observed(*, present=False, combat=False, on=False):
    return {"fresh": True, "identityValid": True, "readinessFresh": True,
            "player": {"dead": False, "inCombat": combat,
                       "healthPct": 100, "resourcePct": 100},
            "encounter": {"present": present, "casting": False,
                          "threatKnown": True, "levelDelta": 0, "losing": False,
                          "offCorridor": False, "onCorridor": on},
            "abilities": {PROFILE.damage: {"learned": True, "ready": True,
                                            "usable": True, "resourceCostPct": 0}}}


class Backend:
    def __init__(self, observations):
        self.observations = list(observations)
        self.calls = []

    def telemetry(self):
        if len(self.observations) > 1:
            return self.observations.pop(0)
        return self.observations[0]

    def cast(self, binding):
        self.calls.append(("cast", binding))
        return {"accepted": True}

    def start_combat(self):
        self.calls.append(("combat-start",))

    def release_combat(self, reason):
        self.calls.append(("combat-release", reason))
        return {"releaseSucceeded": True, "desktopInputsDown": []}

    def start_recovery(self):
        self.calls.append(("recovery-start",))

    def release_recovery(self, reason):
        self.calls.append(("recovery-release", reason))
        return {"releaseSucceeded": True, "desktopInputsDown": []}

    def corridor_reachable(self, points):
        self.calls.append(("reachable", points))
        return bool(points)


class Interrupted(RuntimeError):
    def __init__(self, receipt, position):
        self.receipt, self.position = receipt, position


def pose(x=0, z=0):
    return SimpleNamespace(position=SimpleNamespace(x=x, y=5, z=z), bearing=0, acquired=1)


def arrived(x, z, start_x=0, start_z=0):
    distance = math.hypot(x - start_x, z - start_z)
    steps = max(1, math.ceil(distance))
    path = [{"x": start_x + (x - start_x) * index / steps, "y": 5,
             "z": start_z + (z - start_z) * index / steps}
            for index in range(steps + 1)]
    return {"status": "arrived", "name": "CLI destination",
            "goal": {"x": x, "y": 5, "z": z},
            "start": {"x": start_x, "y": 5, "z": start_z},
            "position": {"x": x, "y": 5, "z": z}, "bearing": 0,
            "distance": 0, "pulses": 1, "observedAtUtc": "now",
            "releaseSucceeded": True, "desktopInputsDown": [], "inputSent": True,
            "path": path}


class SurvivalRouteRunnerTests(unittest.TestCase):
    def invoke(self, points, backend, mover, **kwargs):
        events, entered = [], []
        stop = kwargs.pop("stop", threading.Event())
        with patch("scripts.physical_waypoints.read_stationary", return_value=pose()):
            result = run_survival_route(
                object(), points, stop, events.append, profile=PROFILE,
                telemetry=backend.telemetry, action_backend=backend, mover=mover,
                encounter_error=Interrupted, entry_check=lambda value: entered.append(value),
                wait_seconds=0, **kwargs)
        return result, events, entered

    def test_normal_route_calls_one_real_leg_at_a_time_and_emits_arrivals(self):
        calls = []
        current = [0.0, 0.0]

        def mover(adapter, x, z, stop, emit, **options):
            calls.append((x, z, options))
            result = arrived(x, z, *current)
            current[:] = [x, z]
            emit(result)
            return result

        backend = Backend([observed()])
        results, events, entered = self.invoke(
            [("one", 4, 0), ("two", 8, 0)], backend, mover)
        self.assertEqual([(4.0, 0.0), (8.0, 0.0)], [(x, z) for x, z, _ in calls])
        self.assertTrue(all(call[2]["survival_guard"] is True for call in calls))
        self.assertEqual(1, len(entered))
        self.assertEqual(["one", "two"], [event["name"] for event in events
                                           if event["status"] == "arrived"])
        self.assertEqual(2, len(results))

    def test_encounter_releases_then_fights_rejoins_and_retries_same_leg(self):
        calls = []
        interrupted = {"releaseSucceeded": True, "desktopInputsDown": [],
                       "status": "halted", "reason": "survival-combat",
                       "path": [
                           {"x": 0, "y": 5, "z": 0}, {"x": 2, "y": 5, "z": 0},
                           {"x": 4, "y": 5, "z": 0}, {"x": 5, "y": 5, "z": 0}]}

        def mover(adapter, x, z, stop, emit, **options):
            calls.append((x, z))
            if calls == [(10.0, 0.0)]:
                raise Interrupted(interrupted, {"x": 5, "y": 5, "z": 0})
            result = arrived(x, z, 5, 0)
            emit(result)
            return result

        backend = Backend([
            observed(present=True, combat=True),
            observed(present=True, combat=True),
            observed(present=False, combat=False),
            observed(present=False, combat=False, on=True),
        ])
        results, events, _ = self.invoke([("pending", 10, 0)], backend, mover)
        self.assertEqual([(10.0, 0.0), (10.0, 0.0)], calls)
        self.assertEqual(1, len([event for event in events if event["status"] == "arrived"]))
        self.assertEqual("pending", [event for event in events
                                     if event["status"] == "arrived"][0]["name"])
        self.assertEqual(1, len(results[0]["survival"]["encounters"]))
        self.assertEqual(("combat-start",), backend.calls[0])
        self.assertIn(("combat-release", "combat-complete"), backend.calls)
        transitions = [event["survival"] for event in events
                       if event.get("status") == "survival-state"]
        self.assertEqual(["travel", "fight", "rejoin", "travel"],
                         [item["state"] for item in transitions])
        self.assertTrue(all(set(("owner", "lastAction", "reason", "encounterCount"))
                            <= set(item) for item in transitions))
        self.assertEqual(1, transitions[-1]["encounterCount"])

    def test_unverified_native_release_never_starts_combat_or_retries(self):
        def mover(adapter, x, z, stop, emit, **options):
            raise Interrupted({"releaseSucceeded": False, "desktopInputsDown": ["w"]},
                              {"x": 1, "y": 5, "z": 0})

        backend = Backend([observed(present=True, combat=True)])
        with self.assertRaisesRegex(Exception, "uncertain-release"):
            self.invoke([("pending", 10, 0)], backend, mover)
        self.assertNotIn(("combat-start",), backend.calls)

    def test_policy_halt_preserves_telemetry_refusal_detail(self):
        receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                   "path": [{"x": 0, "y": 5, "z": 0},
                            {"x": 1, "y": 5, "z": 0}]}

        def mover(adapter, x, z, stop, emit, **options):
            raise Interrupted(receipt, {"x": 1, "y": 5, "z": 0})

        stale = observed()
        stale["fresh"] = False
        backend = Backend([stale])
        with self.assertRaisesRegex(
                Exception,
                "critical-unavailable; SurvivalPolicyError: critical telemetry unavailable"):
            self.invoke([("pending", 10, 0)], backend, mover)

    def test_discontinuous_or_wrong_height_native_path_cannot_become_corridor(self):
        receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                   "path": [{"x": 0, "y": 9, "z": 0},
                            {"x": 1, "y": 9, "z": 0}]}

        def mover(adapter, x, z, stop, emit, **options):
            raise Interrupted(receipt, {"x": 1, "y": 9, "z": 0})

        backend = Backend([observed(present=True, combat=True)])
        with self.assertRaisesRegex(Exception, "known traversed corridor"):
            self.invoke([("pending", 10, 0)], backend, mover)
        self.assertNotIn(("combat-start",), backend.calls)

    def test_stop_during_combat_still_runs_release_cleanup(self):
        stop = threading.Event()
        receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                   "path": [{"x": 0, "y": 5, "z": 0},
                            {"x": 1, "y": 5, "z": 0}]}

        def mover(adapter, x, z, ignored_stop, emit, **options):
            raise Interrupted(receipt, {"x": 1, "y": 5, "z": 0})

        backend = Backend([observed(present=True, combat=True)])
        original = backend.telemetry
        calls = {"count": 0}

        def telemetry():
            calls["count"] += 1
            value = original()
            if calls["count"] == 2:
                stop.set()
            return value

        backend.telemetry = telemetry
        with self.assertRaisesRegex(Exception, "Stopped"):
            self.invoke([("pending", 10, 0)], backend, mover, stop=stop)
        self.assertIn(("combat-start",), backend.calls)
        self.assertIn(("combat-release", "operator-stop"), backend.calls)

    def test_global_stop_wins_before_movement_or_combat(self):
        stop = threading.Event()
        stop.set()
        calls = []
        backend = Backend([observed(present=True, combat=True)])
        with self.assertRaisesRegex(Exception, "Stopped"):
            self.invoke([("pending", 1, 0)], backend,
                        lambda *args, **kwargs: calls.append(args), stop=stop)
        self.assertEqual([], calls)
        self.assertEqual([], backend.calls)

    def test_total_route_distance_is_checked_before_input(self):
        calls = []
        backend = Backend([observed()])
        with self.assertRaisesRegex(Exception, "Route exceeds"):
            self.invoke([("far", 1001, 0)], backend,
                        lambda *args, **kwargs: calls.append(args))
        self.assertEqual([], calls)

    def test_shared_deadline_is_passed_as_decreasing_leg_budget(self):
        ticks = iter((0, 0, 1, 1, 4, 4, 4))
        budgets = []
        current = [0.0, 0.0]

        def mover(adapter, x, z, stop, emit, **options):
            budgets.append(options["max_seconds"])
            result = arrived(x, z, *current)
            current[:] = [x, z]
            emit(result)
            return result

        backend = Backend([observed()])
        self.invoke([("one", 1, 0), ("two", 2, 0)], backend, mover,
                    clock=lambda: next(ticks), max_seconds=10)
        self.assertGreater(budgets[0], budgets[1])

    def test_corridor_arrival_requires_planar_and_height_agreement(self):
        self.assertTrue(_corridor_arrival({"x": 1.4, "y": 5.4, "z": 2}, 1, 5, 2))
        self.assertFalse(_corridor_arrival({"x": 1.6, "y": 5, "z": 2}, 1, 5, 2))
        self.assertFalse(_corridor_arrival({"x": 1, "y": 5.6, "z": 2}, 1, 5, 2))

    def test_retained_collinear_samples_coalesce_to_one_auxiliary_leg(self):
        samples = [(float(x), 5.0, 0.0) for x in range(10, -1, -1)]
        self.assertEqual([samples[0], samples[-1]],
                         _coalesce_retained_corridor(samples))

    def test_retained_corridor_corner_and_height_change_are_preserved(self):
        samples = [(5.0, 5.0, 5.0), (5.0, 5.0, 2.0),
                   (5.0, 5.0, 0.0), (2.0, 5.0, 0.0),
                   (0.0, 5.4, 0.0)]
        simplified = _coalesce_retained_corridor(samples)
        self.assertIn((5.0, 5.0, 0.0), simplified)
        self.assertIn((0.0, 5.4, 0.0), simplified)

    def test_retreat_uses_native_retreat_guard_but_rejoin_keeps_full_guard(self):
        calls = []
        current = [0.0, 0.0]
        receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                   "path": [{"x": x / 2, "y": 5, "z": 0}
                            for x in range(11)]}

        def mover(adapter, x, z, stop, emit, **options):
            calls.append((x, z, options["survival_guard"], options["max_seconds"]))
            if len(calls) == 1:
                current[:] = [5.0, 0.0]
                raise Interrupted(receipt, {"x": 5, "y": 5, "z": 0})
            result = arrived(x, z, *current)
            current[:] = [x, z]
            emit(result)
            return result

        unknown = observed(present=True, combat=True); unknown["encounter"]["threatKnown"] = False
        backend = Backend([
            observed(present=True, combat=True), unknown,
            observed(present=False, combat=False),
            observed(present=False, combat=False, on=True),
        ])
        self.invoke([("pending", 10, 0)], backend, mover,
                    retreat_max_seconds=12, minimum_trail_points=4)
        guards = [guard for _x, _z, guard, _limit in calls[1:-1]]
        self.assertIn("retreat", guards)
        self.assertIs(calls[-1][2], True)
        retreat_limits = [limit for _x, _z, guard, limit in calls if guard == "retreat"]
        self.assertEqual(1, len(retreat_limits))
        self.assertTrue(all(limit <= 12 for limit in retreat_limits))

    def test_configured_minimum_retreat_trail_is_enforced(self):
        receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                   "path": [{"x": 0, "y": 5, "z": 0},
                            {"x": 1, "y": 5, "z": 0}]}
        calls = []

        def mover(adapter, x, z, stop, emit, **options):
            calls.append((x, z))
            raise Interrupted(receipt, {"x": 1, "y": 5, "z": 0})

        unknown = observed(present=True, combat=True); unknown["encounter"]["threatKnown"] = False
        backend = Backend([observed(present=True, combat=True), unknown])
        with self.assertRaisesRegex(Exception, "too few retained points"):
            self.invoke([("pending", 10, 0)], backend, mover,
                        minimum_trail_points=3)
        self.assertEqual([(10.0, 0.0)], calls)

    def test_healthy_retreat_rejoins_any_retained_sample_and_resumes_pending_leg(self):
        from scripts.waypoint_survival_runtime import _PolicyBackend

        current = {"x": 0.0, "y": 5.0, "z": 0.0}
        receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                   "path": [{"x": x * .2, "y": 5, "z": 5}
                            for x in range(11)]}
        unknown = observed(present=True, combat=True)
        unknown["encounter"]["threatKnown"] = False
        observations = [observed(present=True, combat=True), unknown,
                        observed(), observed()]

        class Runtime:
            _target_id = "target"

            def __init__(self):
                self._latest_report = {"snapshot": {"player": {
                    "coordX": 0.0, "coordY": 5.0, "coordZ": 0.0}}}

            def _next_telemetry(self):
                value = observations.pop(0) if len(observations) > 1 else observations[0]
                value = {key: (dict(item) if isinstance(item, dict) else item)
                         for key, item in value.items()}
                value["player"].update(coordX=current["x"], coordY=current["y"],
                                       coordZ=current["z"])
                self._latest_report = {"snapshot": {
                    "player": {"coordX": current["x"], "coordY": current["y"],
                               "coordZ": current["z"]}}}
                return value

            @staticmethod
            def _release_receipt(_result, reason):
                return {"releaseSucceeded": True, "desktopInputsDown": [],
                        "inputSent": False, "reason": reason}

        class ActionOwner:
            def begin_encounter(self):
                return None

            def cancel(self):
                return {"status": "already-clean", "inputSent": False}

        runtime = Runtime()
        actions = ActionOwner()
        backend = _PolicyBackend(runtime, actions)
        calls = []

        def mover(adapter, x, z, stop, emit, **options):
            calls.append((x, z, options["survival_guard"]))
            if len(calls) == 2:
                current.update(x=2.0, z=5.0)
                raise Interrupted(receipt, dict(current))
            start_x, start_z = current["x"], current["z"]
            current.update(x=x, z=z)
            result = arrived(x, z, start_x, start_z)
            emit(result)
            return result

        with patch("scripts.physical_waypoints.read_stationary", return_value=pose()):
            results = run_survival_route(
                object(), [("first", 0, 5), ("pending", 5, 5)], threading.Event(),
                profile=PROFILE, telemetry=backend.telemetry,
                action_backend=backend, mover=mover,
                encounter_error=Interrupted, wait_seconds=0)
        self.assertEqual([(0.0, 5.0, True), (5.0, 5.0, True),
                          (0.0, 5.0, "retreat"), (0.0, 0.0, "retreat"),
                          (0.0, 5.0, True), (2.0, 5.0, True),
                          (5.0, 5.0, True)], calls)
        self.assertGreater(len(backend.corridor_points), 2)
        self.assertEqual((2.0, 5.0, 5.0), backend.corridor_points[0])
        self.assertEqual((0.0, 5.0, 0.0), backend.corridor_points[-1])
        self.assertEqual(["arrived", "arrived"],
                         [result["status"] for result in results])
        self.assertEqual(1, results[-1]["survival"]["state"]["checkpoint"])


if __name__ == "__main__":
    unittest.main()
