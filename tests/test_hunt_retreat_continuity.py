"""Offline hunt-to-survival continuity checks across the production handoff."""
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import hunt_mission as hunt
from scripts.survival_route_runner import run_survival_route
from scripts.waypoint_survival_runtime import _PolicyBackend
from scripts.waypoint_survival import SurvivalPolicyError, SurvivalPorts, WaypointSurvivalRunner
from tests.test_survival_route_runner import PROFILE, Interrupted, observed, pose


IDENTITY = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64, "unitKey": "1"}
TARGET = "u800000020502E041"


class ContinuityTests(unittest.TestCase):
    def exercise(self, coordinates):
        samples = [{"x": x, "y": 5, "z": z} for x, z in coordinates]
        current = dict(samples[-1]); calls = []
        mission = {"name": "offline", "binding": {}, "maximumMissionSeconds": 1800,
                   "safeAnchor": dict(samples[0], planarTolerance=.5, heightTolerance=.5),
                   "hunt": {"maximumSeconds": 30, "maximumKills": 2, "expectedTargetId": TARGET,
                            "center": dict(samples[-1]), "radius": 10}}
        adapter = SimpleNamespace(binding={"runtimeIdentity": IDENTITY})

        class Actions:
            def begin_encounter(self): pass
            def cancel(self): return {"status": "already-clean", "inputSent": False}

        class Runtime:
            _target_id = None
            def __init__(self):
                self._latest_report = None
                self.backend = _PolicyBackend(self, Actions())
            def configure(self, *_): pass
            def preflight(self, *_): return {"status": "ready"}
            def _next_telemetry(self):
                value = observed()
                value["player"].update(coordX=current["x"], coordY=current["y"], coordZ=current["z"])
                self._latest_report = {"snapshot": {"player": value["player"]}}
                return value
            def selected_encounter(self, *_args, **_kwargs):
                return {"status": "blocked", "reason": "selected-encounter-unsafe",
                        "selectedTargetId": TARGET, "releaseSucceeded": True,
                        "desktopInputsDown": []}
            def route_runner(self, adapter, rows, stop, emit, **options):
                def mover(_adapter, x, z, _stop, emit_move, **kw):
                    calls.append((x, z, kw))
                    path = list(reversed(samples))
                    for i, guide in enumerate(kw.get("path_points", [])):
                        point = {axis: guide[axis] for axis in ("x", "y", "z")}
                        emit_move({"status": "passed", "index": i, "name": guide["name"],
                                   "position": point, "passageVerified": True,
                                   "releaseSucceeded": True, "desktopInputsDown": [],
                                   "source": "settled-corner" if guide.get("controlPause") else "pose"})
                    current.update(x=x, y=kw["goal_y"], z=z)
                    return {"status": "arrived", "position": dict(current), "path": path,
                            "releaseSucceeded": True, "desktopInputsDown": []}
                with patch("scripts.physical_waypoints.read_stationary",
                           side_effect=lambda *_: pose(current["x"], current["z"])):
                    return run_survival_route(adapter, rows, stop, emit, profile=PROFILE,
                        telemetry=self.backend.telemetry, action_backend=self.backend,
                        mover=mover, encounter_error=Interrupted, wait_seconds=0, **options)

        def playback(*_args, **_kwargs):
            return ([{"status": "arrived", "releaseSucceeded": True, "desktopInputsDown": [],
                      "path": samples, "position": samples[-1]}], SimpleNamespace(next_index=2))

        with tempfile.TemporaryDirectory() as tmp:
            result = hunt.run_mission(mission=mission, route_document={},
                route_path=Path(tmp) / "route", profile_path=Path(tmp) / "profile",
                checkpoint=Path(tmp) / "checkpoint.json", adapter=adapter, runtime=Runtime(),
                stop=threading.Event(), playback=playback, emit=lambda _: None)
        return result, calls, samples

    def test_straight_compact_route_retains_continuous_actual_samples(self):
        result, calls, samples = self.exercise([(x, 0) for x in range(11)])
        doc = result["progress"]["returnDocument"]
        self.assertEqual(2, len(doc["waypoints"]))
        seed = doc["provenance"]["retreatTrail"]
        self.assertGreater(len(seed), 2)
        self.assertTrue(all(point in samples for point in seed))
        self.assertEqual((0.0, 0.0), calls[0][:2])
        self.assertTrue(result["safeReturned"])

    def test_260_turns_preserve_safe_anchor_through_real_policy(self):
        result, calls, _ = self.exercise([(x, x % 2) for x in range(260)])
        self.assertEqual(260, len(result["progress"]["returnDocument"]["provenance"]["retreatTrail"]))
        self.assertEqual((0.0, 0.0), calls[0][:2])
        self.assertEqual(0, result["progress"]["finalPosition"]["x"])

    def test_old_sparse_and_malformed_seed_refuse(self):
        safe = {"safeAnchor": {"x": 0, "y": 5, "z": 0,
                               "planarTolerance": .5, "heightTolerance": .5}}
        document = hunt._return_document([(0, 5, 0), (10, 5, 0)], IDENTITY)
        with self.assertRaisesRegex(hunt.MissionError, "discontinuous"):
            hunt._verified_retreat_seed(document, safe)
        for invalid in (None, [], [{"x": 0, "y": 5, "z": 0}, {"x": 10, "y": 6, "z": 0}]):
            document["provenance"]["retreatTrail"] = invalid
            with self.assertRaises(hunt.MissionError):
                hunt._verified_retreat_seed(document, safe)

    def test_checkpoint_seed_rejects_detours_height_and_reversal(self):
        safe = {"safeAnchor": {"x": 0, "y": 5, "z": 0,
                               "planarTolerance": .5, "heightTolerance": .5}}
        compact = [(0, 5, 0), (10, 5, 0)]
        document = hunt._return_document(compact, IDENTITY)
        invalid = [
            [(0,5,0),(0,5,2),(0,5,4), *[(x,5,4) for x in range(2,11,2)], (10,5,2),(10,5,0)],
            [(0,5,0),(1,6,0),(2,5,0), *[(x,5,0) for x in range(4,11,2)]],
            [(0,5,0),(2,5,0),(1,5,0), *[(x,5,0) for x in range(3,10,2)],(10,5,0)],
        ]
        for seed in invalid:
            with self.subTest(seed=seed):
                restored = json.loads(json.dumps(document))
                restored["provenance"]["retreatTrail"] = [dict(zip(("x","y","z"), p)) for p in seed]
                with self.assertRaises(hunt.MissionError):
                    hunt._verified_retreat_seed(restored, safe)

    def test_valid_sample_shapes_roundtrip_checkpoint_validation(self):
        cases = [
            [(x, 5+.02*x, .1 if x%2 else 0) for x in range(11)],
            [(0, y, 0) for y in range(5, 10)],
            [(0,5,0),(1,5,0),(2,5,0),(1,5,0),(0,5,0),(0,5,1),(0,5,2)],
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                leg = {"status":"arrived", "releaseSucceeded":True, "desktopInputsDown":[],
                       "path":[dict(zip(("x","y","z"),p)) for p in raw]}
                compact, samples = hunt._walked_corridor([leg], include_samples=True)
                doc = json.loads(json.dumps(hunt._return_document(compact, IDENTITY, samples)))
                safe = {"safeAnchor":dict(zip(("x","y","z"),raw[0]), planarTolerance=.5,heightTolerance=.5)}
                seed = hunt._verified_retreat_seed(doc,safe)
                self.assertTrue(all(tuple(p[a] for a in ("x","y","z")) in raw for p in seed))

    def test_corrupt_resumed_checkpoint_refuses_before_encounter_or_movement(self):
        safe = {"x":0,"y":5,"z":0,"planarTolerance":.5,"heightTolerance":.5}
        mission = {"name":"resume", "binding":{}, "safeAnchor":safe, "maximumMissionSeconds":30}
        raw = [(x,5,0) for x in range(11)]
        doc = hunt._return_document([raw[0],raw[-1]], IDENTITY, raw)
        detour = [(0,5,0),(0,5,2),(0,5,4), *[(x,5,4) for x in range(2,11,2)],(10,5,2),(10,5,0)]
        doc["provenance"]["retreatTrail"] = [dict(zip(("x","y","z"),p)) for p in detour]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint = root/'checkpoint.json'
            progress = hunt._new_progress(mission,root/'route',root/'profile')
            progress.update(stage="encounter",returnDocument=doc)
            checkpoint.write_text(json.dumps(progress))
            original = checkpoint.read_bytes()
            def prohibited(*_args, **_kwargs): self.fail('input-capable stage was invoked')
            runtime = SimpleNamespace(configure=lambda *_:None, preflight=lambda *_:{"status":"ready"},
                                      selected_encounter=prohibited,route_runner=prohibited)
            with self.assertRaisesRegex(hunt.MissionError, 'leaves the retained'):
                hunt.run_mission(mission=mission,route_document={},route_path=root/'route',
                    profile_path=root/'profile',checkpoint=checkpoint,adapter=SimpleNamespace(binding={"runtimeIdentity":IDENTITY}),
                    runtime=runtime,stop=threading.Event(),playback=prohibited,emit=lambda _:None,resume=True)
            self.assertEqual(original,checkpoint.read_bytes())

    def test_terminal_capacity_refuses_without_losing_anchor_and_ordinary_rolls(self):
        ports = SurvivalPorts(*([lambda *_: None] * 10))
        terminal = WaypointSurvivalRunner(PROFILE, ports, finish_after_retreat=True)
        ordinary = WaypointSurvivalRunner(PROFILE, ports)
        for i in range(500):
            terminal.record_route_trail_point((i, 5, 0))
            ordinary.record_route_trail_point((i, 5, 0))
        with self.assertRaisesRegex(SurvivalPolicyError, "exceeds 500"):
            terminal.record_route_trail_point((500, 5, 0))
        self.assertEqual(500, len(terminal.trail))
        self.assertEqual((0.0, 5.0, 0.0), terminal.trail[0])
        self.assertEqual(256, len(ordinary.trail))
        self.assertEqual((244.0, 5.0, 0.0), ordinary.trail[0])


if __name__ == "__main__":
    unittest.main()
