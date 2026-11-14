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
        value = (self.observations.pop(0) if len(self.observations) > 1
                 else self.observations[0])
        if hasattr(self, "position"):
            value = dict(value, player=dict(value["player"], coordX=self.position[0],
                                            coordY=5, coordZ=self.position[1]))
        return value

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
        events, entered = kwargs.pop("events", []), []
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
            [("one", 4, 0), ("two", 8, 0)], backend, mover,
            goal_heights=[5, 5])
        self.assertEqual([(4.0, 0.0), (8.0, 0.0)], [(x, z) for x, z, _ in calls])
        self.assertTrue(all(call[2]["survival_guard"] is True for call in calls))
        self.assertEqual([5.0, 5.0], [call[2]["goal_y"] for call in calls])
        self.assertEqual(1, len(entered))
        self.assertEqual(["one", "two"], [event["name"] for event in events
                                           if event["status"] == "arrived"])
        self.assertEqual(2, len(results))

    def test_span_interruption_keeps_verified_prefix_and_retries_unfinished_guides(self):
        calls, events = [], []
        current = [0.0, 0.0]

        def mover(adapter, x, z, stop, emit, **options):
            guides = options.get("path_points", [])
            calls.append((x, [g["name"] for g in guides]))
            for number, guide in enumerate(guides[:1] if len(calls) == 1 else guides):
                emit({"status": "passed", "index": number, "name": guide["name"],
                      "goal": guide, "position": {"x": guide["x"], "y": 5, "z": guide["z"]},
                      "passageVerified": True, "releaseSucceeded": True, "desktopInputsDown": []})
            if len(calls) == 1:
                current[:] = [1.5, 0]
                receipt = {"status": "halted", "releaseSucceeded": True, "desktopInputsDown": [],
                           "path": [{"x": 0, "y": 5, "z": 0},
                                    {"x": 1.5, "y": 5, "z": 0}]}
                raise Interrupted(receipt, {"x": 1.5, "y": 5, "z": 0})
            result = arrived(x, z, *current)
            current[:] = [x, z]
            return result

        backend = Backend([observed(present=True, combat=True), observed(), observed(on=True)])
        backend.position = current
        results, _, _ = self.invoke([("one", 1, 0), ("two", 2, 0), ("end", 3, 0)],
                                    backend, mover, events=events,
                                    point_kinds=["pass", "pass", "stop"])
        self.assertEqual([(3.0, ["one", "two"]), (3.0, ["two"])], calls)
        self.assertEqual([("passed", "one"), ("passed", "two"), ("arrived", "end")],
                         [(e["status"], e["name"]) for e in events
                          if e["status"] in ("passed", "arrived")])
        self.assertEqual(1, len(results[-1]["survival"]["encounters"]))

    def test_interrupted_span_does_not_publish_passage_without_retained_path(self):
        events = []
        def mover(adapter, x, z, stop, emit, **options):
            guide = options["path_points"][0]
            emit({"status": "passed", "index": 0, "name": guide["name"], "goal": guide,
                  "position": {"x": guide["x"], "y": 5, "z": guide["z"]},
                  "passageVerified": True, "releaseSucceeded": True, "desktopInputsDown": []})
            raise Interrupted({"releaseSucceeded": True, "desktopInputsDown": [], "path": []},
                              {"x": 1, "y": 5, "z": 0})
        with self.assertRaisesRegex(Exception, "known traversed corridor"):
            self.invoke([("one", 1, 0), ("end", 2, 0)], Backend([observed()]), mover,
                        events=events, point_kinds=["pass", "stop"])
        self.assertFalse(any(e.get("status") == "passed" for e in events))

    def test_displacement_to_another_trail_point_does_not_authorize_rejoin(self):
        events, calls = [], []
        backend = Backend([observed(present=True, combat=True), observed()])
        # This is on the retained trail, but not at the interruption frontier.
        backend.position = [0, 0]
        def mover(adapter, x, z, stop, emit, **options):
            calls.append((x, z))
            receipt = {"releaseSucceeded": True, "desktopInputsDown": [],
                       "path": [{"x": 0, "y": 5, "z": 0},
                                {"x": 2, "y": 5, "z": 0},
                                {"x": 4, "y": 5, "z": 0}]}
            raise Interrupted(receipt, {"x": 4, "y": 5, "z": 0})
        with self.assertRaisesRegex(Exception, "retained rejoin frontier"):
            self.invoke([("end", 5, 0)], backend, mover, events=events)
        self.assertEqual([(5.0, 0.0)], calls)
        self.assertFalse(any(e.get("status") in ("arrived", "passed") for e in events))

    def test_retained_corridor_preserves_collinear_reversals_in_both_directions(self):
        points = [(0, 0, z) for z in (0, 1, 2, 1, 2, 3)]
        for trail in (points, list(reversed(points))):
            retained = _coalesce_retained_corridor(trail)
            self.assertEqual([trail[0], trail[2], trail[3], trail[-1]], retained)

    def test_stop_commits_only_verified_prefix_and_never_restarts(self):
        from scripts.physical_waypoints import Stopped
        from scripts.continuous_move import ContinuousStopped

        for valid_path in (True, False):
            with self.subTest(valid_path=valid_path):
                events, calls, stop = [], [], threading.Event()
                def mover(adapter, x, z, shared_stop, emit, **options):
                    calls.append((x, z))
                    for index, guide in enumerate(options["path_points"]):
                        emit({"status": "passed", "index": index, "name": guide["name"],
                              "goal": guide, "position": {"x": guide["x"], "y": 5, "z": guide["z"]},
                              "passageVerified": True, "releaseSucceeded": True,
                              "desktopInputsDown": []})
                    shared_stop.set()
                    raise ContinuousStopped("operator STOP", {"status": "stopped", "releaseSucceeded": True,
                        "desktopInputsDown": [], "position": {"x": 2.5, "y": 5, "z": 0},
                        "path": ([{"x": 0, "y": 5, "z": 0},
                                  {"x": 1.5, "y": 5, "z": 0},
                                  {"x": 2.5, "y": 5, "z": 0}] if valid_path else [])})
                backend = Backend([observed()])
                with self.assertRaises(Stopped):
                    self.invoke([("one", 1, 0), ("two", 2, 0), ("end", 3, 0)],
                                backend, mover, events=events, stop=stop,
                                point_kinds=["pass", "pass", "stop"])
                self.assertTrue(stop.is_set())
                self.assertEqual([(3.0, 0.0)], calls)
                self.assertEqual(["one", "two"] if valid_path else [],
                                 [e["name"] for e in events if e.get("status") == "passed"])
                self.assertEqual([], backend.calls)

    def test_arrived_without_confirmed_key_release_must_not_complete_route(self):
        def mover(adapter, x, z, stop, emit, **options):
            receipt = arrived(x, z)
            receipt["releaseSucceeded"] = False
            receipt["desktopInputsDown"] = ["w"]
            return receipt

        backend = Backend([observed()])
        with self.assertRaisesRegex(Exception, "arrived.*release"):
            self.invoke([("pending", 4, 0)], backend, mover)

    def test_arrived_at_wrong_destination_must_not_advance_checkpoint(self):
        def mover(adapter, x, z, stop, emit, **options):
            return arrived(1, 0)  # Valid-looking receipt for the wrong goal.

        backend = Backend([observed()])
        with self.assertRaisesRegex(Exception, "arrived.*destination"):
            self.invoke([("pending", 4, 0)], backend, mover)

    def test_arrived_callback_is_not_published_before_receipt_validation(self):
        cases = (
            ("release", lambda receipt: receipt.update(releaseSucceeded=False),
             "unverified input release"),
            ("destination", lambda receipt: receipt.update(
                position={"x": 1, "y": 5, "z": 0}),
             "not at the requested destination"),
            ("path", lambda receipt: receipt.update(path=[]),
             "cannot establish a known traversed corridor"),
        )
        for label, corrupt, reason in cases:
            with self.subTest(label=label):
                events = []

                def mover(adapter, x, z, stop, emit, **options):
                    receipt = arrived(x, z)
                    corrupt(receipt)
                    emit(dict(receipt))  # Native mover currently emits before returning.
                    return receipt

                with self.assertRaisesRegex(Exception, reason):
                    self.invoke([("pending", 4, 0)], Backend([observed()]),
                                mover, events=events)
                self.assertNotIn("arrived", [e.get("status") for e in events])

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
        backend.position = [5, 0]
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
            calls.append((x, z, options["survival_guard"], options["max_seconds"],
                          options["goal_y"]))
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
        guards = [call[2] for call in calls[1:-1]]
        self.assertIn("retreat", guards)
        self.assertIs(calls[-1][2], True)
        retreat_limits = [call[3] for call in calls if call[2] == "retreat"]
        self.assertEqual(1, len(retreat_limits))
        self.assertTrue(all(limit <= 12 for limit in retreat_limits))
        self.assertTrue(all(call[4] == 5.0 for call in calls[1:-1]))

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

    def test_initial_unsafe_encounter_retreats_safeward_and_recovers_before_route_travel(self):
        unsafe=observed(present=True,combat=True); unsafe["player"]["healthPct"]=20
        recovering=observed(); recovering["player"]["healthPct"]=50
        backend=Backend([observed(present=True,combat=True),unsafe,recovering,observed()])
        calls=[]; current=[4.0,0.0]
        def mover(adapter,x,z,stop,emit,**options):
            calls.append((x,z,options["survival_guard"]))
            result=arrived(x,z,*current); current[:]=[x,z]; emit(result); return result
        events=[]
        with patch("scripts.physical_waypoints.read_stationary",
                   side_effect=[pose(4,0),pose(0,0)]):
            results=run_survival_route(object(),[("hunt",4,0),("safe",0,0)],
                threading.Event(),events.append,profile=PROFILE,telemetry=backend.telemetry,
                action_backend=backend,mover=mover,encounter_error=Interrupted,wait_seconds=0,
                initial_retreat_trail=[{"x":0,"y":5,"z":0},{"x":2,"y":5,"z":0},
                                       {"x":4,"y":5,"z":0}],
                assess_before_travel=True,finish_after_retreat=True)
        self.assertEqual([(0.0,0.0,"retreat")],calls)
        self.assertTrue(results[0]["safeRetreat"])
        self.assertEqual({"x":0.0,"y":5.0,"z":0.0},results[0]["position"])
        self.assertIn(("recovery-start",),backend.calls)
        self.assertEqual("safe",results[0]["name"])

    def test_post_recovery_fresh_pose_off_safe_anchor_refuses_completion(self):
        unsafe=observed(present=True,combat=True); unsafe["player"]["healthPct"]=20
        recovering=observed(); recovering["player"]["healthPct"]=50
        backend=Backend([observed(present=True,combat=True),unsafe,recovering,observed()])
        current=[4.0,0.0]
        def mover(adapter,x,z,stop,emit,**options):
            result=arrived(x,z,*current); current[:]=[x,z]; emit(result); return result
        with patch("scripts.physical_waypoints.read_stationary",
                   side_effect=[pose(4,0),pose(1,0)]):
            with self.assertRaisesRegex(Exception,"did not finish at the retained safe endpoint"):
                run_survival_route(object(),[("hunt",4,0),("safe",0,0)],threading.Event(),
                    profile=PROFILE,telemetry=backend.telemetry,action_backend=backend,
                    mover=mover,encounter_error=Interrupted,wait_seconds=0,
                    initial_retreat_trail=[{"x":0,"y":5,"z":0},{"x":2,"y":5,"z":0},
                                           {"x":4,"y":5,"z":0}],
                    assess_before_travel=True,finish_after_retreat=True)

    def test_stop_during_terminal_safe_recovery_never_starts_ordinary_return(self):
        unsafe=observed(present=True,combat=True); unsafe["player"]["healthPct"]=20
        recovering=observed(); recovering["player"]["healthPct"]=50
        backend=Backend([observed(present=True,combat=True),unsafe,recovering,observed()])
        stop=threading.Event(); telemetry_calls=[0]; original=backend.telemetry
        def telemetry():
            telemetry_calls[0]+=1; value=original()
            if telemetry_calls[0] == 4: stop.set()
            return value
        backend.telemetry=telemetry
        calls=[]; current=[4.0,0.0]
        def mover(adapter,x,z,ignored_stop,emit,**options):
            calls.append((x,z,options["survival_guard"]))
            result=arrived(x,z,*current); current[:]=[x,z]; emit(result); return result
        with patch("scripts.physical_waypoints.read_stationary",return_value=pose(4,0)):
            with self.assertRaisesRegex(Exception,"Stopped"):
                run_survival_route(object(),[("hunt",4,0),("safe",0,0)],stop,
                    profile=PROFILE,telemetry=backend.telemetry,action_backend=backend,
                    mover=mover,encounter_error=Interrupted,wait_seconds=0,
                    initial_retreat_trail=[{"x":0,"y":5,"z":0},{"x":2,"y":5,"z":0},
                                           {"x":4,"y":5,"z":0}],
                    assess_before_travel=True,finish_after_retreat=True)
        self.assertEqual([(0.0,0.0,"retreat")],calls)
        self.assertTrue(stop.is_set())

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
            for index, guide in enumerate(options.get("path_points", [])):
                emit({"status": "passed", "index": index, "name": guide["name"],
                      "goal": guide, "position": {"x": guide["x"], "y": guide.get("y", 5), "z": guide["z"]},
                      "passageVerified": True, "releaseSucceeded": True, "desktopInputsDown": []})
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
