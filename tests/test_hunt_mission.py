from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from scripts import hunt_mission as cli


TARGET = "u800000020502E041"
ABILITY = "A05213A7D60B13F6B"
NONCE = "0123456789abcdef0123456789abcdef"


class Adapter:
    binding = {"runtimeIdentity": {"machine": "AMD-DESKTOP",
               "gameBuildSha256": "a" * 64, "unitKey": "1"}}


class Runtime:
    def __init__(self, encounter=None):
        self.calls = []
        self.encounter = encounter or {
            "status": "blocked", "reason": "kill-credit-unverified",
            "selectedTargetId": TARGET, "encounterEnded": True,
            "killProof": {"qualified": False}, "releaseSucceeded": True,
            "desktopInputsDown": [], "recovered": True}
    def configure(self, profile, adapter): self.calls.append(("configure", profile, adapter))
    def preflight(self, adapter, stop):
        self.calls.append(("preflight", adapter, stop)); return {"status": "ready", "inputSent": False}
    def route_runner(self, *_args, **_kwargs): raise AssertionError("playback owns runner invocation")
    def selected_encounter(self, adapter, **kwargs):
        self.calls.append(("encounter", adapter, kwargs)); return self.encounter


class HuntMissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.route, self.profile, self.mission = (self.root/name for name in
                                                   ("route.json","profile.json","mission.json"))
        self.checkpoint = self.root / "mission-progress.json"
        self.route.write_text(json.dumps({
            "waypoints": [["Safe", 1.0, 2.0], ["Hunt", 4.0, 6.0]],
            "heights": [5.0, 5.0]}), encoding="utf-8")
        self.profile.write_text(json.dumps({
            "schemaVersion":1,"nonce":NONCE,"resourceKind":"absolute-power",
            "coordinateBasis":{"qualified":True,"space":"UIParent-to-client-pixels",
                "viewportWidth":1000,"viewportHeight":800,"clientWidth":1000,
                "clientHeight":800,"scaleX":1,"scaleY":1,"offsetX":0,"offsetY":0},
            "abilities":{"damage":ABILITY},"actions":[ABILITY],
            "thresholds":{"healBelowPct":45,"defendBelowPct":65,"retreatBelowPct":25,
                "recoverHealthPct":80,"recoverResourcePct":35,"recoverResourceAbsolute":20,
                "maximumLevelDelta":2},"retreat":{"maximumSeconds":20,"minimumTrailPoints":1},
            "timing":{"pollMilliseconds":100,"actionDeadlineMilliseconds":3000}}),encoding="utf-8")
        self.write_mission()
        self.outputs=[]; self.adapters=[]; self.runtimes=[]

    def write_mission(self, **changes):
        value={"schema":"rr2-hunt-mission/1","name":"Watch Stalker out and back",
            "mode":"explicit-selected-target",
            "binding":{"routeSha256":hashlib.sha256(self.route.read_bytes()).hexdigest(),
                       "profileSha256":hashlib.sha256(self.profile.read_bytes()).hexdigest()},
            "safeAnchor":{"x":1.0,"y":5.0,"z":2.0},
            "hunt":{"expectedTargetId":TARGET,"centerX":4.0,"centerY":5.0,"centerZ":6.0,
                    "radius":5.0},
            "return":{"mode":"reverse-verified-walked-corridor"},"maximumMissionSeconds":1800}
        value.update(changes); self.mission.write_text(json.dumps(value),encoding="utf-8")

    def parse(self,*values): return cli.build_parser().parse_args(values)
    def factories(self, encounter=None):
        def adapter(*values): self.adapters.append(values); return Adapter()
        def runtime():
            value=Runtime(encounter); self.runtimes.append(value); return value
        return adapter,runtime

    def playback(self, adapter, document, stop, emit, **options):
        if document.get("provenance",{}).get("kind")=="native-retained-walked-corridor":
            self.assertEqual([["Return 1",4.0,6.0],["Return 2",1.0,2.0]],document["waypoints"])
            from scripts.waypoint_progress import RouteProgress
            cursor = RouteProgress(document, "forward", adapter.binding["runtimeIdentity"])
            cursor.begin({"x":4.0,"y":5.0,"z":6.0})
            return ([{"status":"arrived","releaseSucceeded":True,"desktopInputsDown":[],
                      "position":{"x":4.0,"y":5.0,"z":6.0}},
                     {"status":"arrived","releaseSucceeded":True,"desktopInputsDown":[],
                      "position":{"x":1.0,"y":5.0,"z":2.0}}],
                    SimpleNamespace(next_index=2,direction="forward",ordered_points=document["waypoints"]))
        leg={"status":"arrived","position":{"x":4.0,"y":5.0,"z":6.0},
             "releaseSucceeded":True,"desktopInputsDown":[],
             "path":[{"x":1.0,"y":5.0,"z":2.0},{"x":2.0,"y":5.0,"z":3.3},
                     {"x":3.0,"y":5.0,"z":4.6},
                     {"x":4.0,"y":5.0,"z":6.0}]}
        return [leg],SimpleNamespace(next_index=2,direction="forward",ordered_points=document["waypoints"])

    def test_dry_run_is_offline_strict_and_defaults_are_bounded(self):
        args=self.parse("dry-run","--mission",str(self.mission),"--route",str(self.route),
                        "--profile",str(self.profile))
        adapter,runtime=self.factories()
        code,result=cli.execute(args,adapter_factory=adapter,runtime_factory=runtime,emit=self.outputs.append)
        self.assertEqual(0,code); self.assertFalse(result["inputSent"])
        self.assertEqual(2,result["mission"]["hunt"]["maximumKills"])
        self.assertEqual([],self.adapters)
        bad=json.loads(self.mission.read_text()); bad["mode"]="nearby-target-search"
        self.mission.write_text(json.dumps(bad))
        with self.assertRaisesRegex(cli.MissionError,"explicit-selected-target"):
            cli.load_definition(self.mission,self.route,self.profile)

    def test_run_requires_execute_before_adapter(self):
        args=self.parse("run","--mission",str(self.mission),"--route",str(self.route),
            "--profile",str(self.profile),"--expected-host","AMD-DESKTOP",
            "--physical-pid","21672","--checkpoint",str(self.checkpoint))
        adapter,runtime=self.factories()
        with self.assertRaisesRegex(cli.MissionError,"requires --execute"):
            cli.execute(args,adapter_factory=adapter,runtime_factory=runtime)
        self.assertEqual([],self.adapters)

    def test_preflight_does_not_install_execution_stop_controls(self):
        args=self.parse("preflight","--mission",str(self.mission),"--route",str(self.route),
            "--profile",str(self.profile),"--expected-host","AMD-DESKTOP","--physical-pid","21672")
        adapter,runtime=self.factories()
        def controls(_stop): raise AssertionError("preflight installed execution controls")
        code,result=cli.execute(args,adapter_factory=adapter,runtime_factory=runtime,
            stop_controls=controls,emit=self.outputs.append)
        self.assertEqual(0,code); self.assertEqual("ready",result["status"])
        self.assertFalse(result["inputSent"])

    def test_target_end_without_death_credit_returns_safe_and_counts_zero(self):
        args=self.parse("run","--mission",str(self.mission),"--route",str(self.route),
            "--profile",str(self.profile),"--expected-host","AMD-DESKTOP","--physical-pid","21672",
            "--checkpoint",str(self.checkpoint),"--execute")
        adapter,runtime=self.factories()
        code,result=cli.execute(args,adapter_factory=adapter,runtime_factory=runtime,
            playback=self.playback,emit=self.outputs.append,clock=lambda:10.0)
        self.assertEqual(0,code); self.assertTrue(result["safeReturned"])
        self.assertEqual("returned-no-qualified-kill",result["status"])
        self.assertEqual(0,result["killCount"])
        progress=json.loads(self.checkpoint.read_text())
        self.assertEqual("complete",progress["stage"])
        self.assertEqual("kill-credit-unverified",progress["encounter"]["reason"])
        call=self.runtimes[0].calls[-1][2]
        self.assertEqual((4.0,6.0),call["hunt_center"]); self.assertEqual(5.0,call["hunt_radius"])

    def test_only_exact_player_death_credit_counts(self):
        encounter={"status":"completed","selectedTargetId":TARGET,"releaseSucceeded":True,
            "desktopInputsDown":[],"killProof":{"qualified":True,"targetId":TARGET,
                "kind":"player-kill-confirmed","sequence":9}}
        adapter,runtime=self.factories(encounter)
        args=self.parse("run","--mission",str(self.mission),"--route",str(self.route),
            "--profile",str(self.profile),"--expected-host","AMD-DESKTOP","--physical-pid","21672",
            "--checkpoint",str(self.checkpoint),"--execute")
        _,result=cli.execute(args,adapter_factory=adapter,runtime_factory=runtime,
            playback=self.playback,emit=self.outputs.append,clock=lambda:10.0)
        self.assertEqual(1,result["killCount"])
        self.assertEqual("unsupported-explicit-selected-target-only",result["additionalTargetSelection"])

    def test_unverified_encounter_release_blocks_return_and_resume_retry(self):
        encounter={"status":"halted","selectedTargetId":TARGET,"releaseSucceeded":False,
                   "desktopInputsDown":["mouse-left"],"killProof":{"qualified":False}}
        adapter,runtime=self.factories(encounter)
        mission,route,_=cli.load_definition(self.mission,self.route,self.profile)
        with self.assertRaisesRegex(cli.MissionError,"return movement blocked"):
            cli.run_mission(mission=mission,route_document=route,route_path=self.route,
                profile_path=self.profile,checkpoint=self.checkpoint,adapter=Adapter(),runtime=runtime(),
                stop=threading.Event(),playback=self.playback,emit=self.outputs.append,clock=lambda:10.0)
        progress=json.loads(self.checkpoint.read_text()); self.assertEqual("encounter-started",progress["stage"])
        with self.assertRaisesRegex(cli.MissionError,"ambiguous"):
            cli.run_mission(mission=mission,route_document=route,route_path=self.route,
                profile_path=self.profile,checkpoint=self.checkpoint,adapter=Adapter(),runtime=Runtime(),
                stop=threading.Event(),playback=self.playback,emit=self.outputs.append,
                resume=True,clock=lambda:10.0)

    def test_selection_or_identity_failure_cannot_become_automatic_return(self):
        for reason in ("selection-changed-during-recovery","survival-frame-target-mismatch",
                       "selected-hostile-alive-target-required"):
            with self.subTest(reason=reason):
                mission,route,_=cli.load_definition(self.mission,self.route,self.profile)
                checkpoint=self.root/(reason+".json")
                runtime=Runtime({"status":"blocked","reason":reason,
                    "selectedTargetId":TARGET,"releaseSucceeded":True,
                    "desktopInputsDown":[],"killProof":{"qualified":False}})
                calls=[]
                def playback(*args,**kwargs):
                    calls.append("return" if args[1].get("provenance") else "outbound")
                    return self.playback(*args,**kwargs)
                with self.assertRaisesRegex(cli.MissionError,"not authorized for automatic return"):
                    cli.run_mission(mission=mission,route_document=route,route_path=self.route,
                        profile_path=self.profile,checkpoint=checkpoint,adapter=Adapter(),runtime=runtime,
                        stop=threading.Event(),playback=playback,emit=self.outputs.append,clock=lambda:10.0)
                self.assertEqual(["outbound"],calls)

    def test_stop_and_discontinuous_path_refuse(self):
        mission,route,_=cli.load_definition(self.mission,self.route,self.profile)
        stop=threading.Event(); stop.set()
        with self.assertRaisesRegex(cli.MissionError,"STOP"):
            cli.run_mission(mission=mission,route_document=route,route_path=self.route,
                profile_path=self.profile,checkpoint=self.checkpoint,adapter=Adapter(),runtime=Runtime(),
                stop=stop,playback=self.playback,emit=self.outputs.append)
        with self.assertRaisesRegex(cli.MissionError,"discontinuous"):
            cli._walked_corridor([{"status":"arrived","releaseSucceeded":True,
                "desktopInputsDown":[],"path":[{"x":0,"y":0,"z":0},{"x":3,"y":0,"z":0}]}])
        now=[9.0]; event=threading.Event(); budget=cli._DeadlineStop(event,10.0,lambda:now[0])
        self.assertFalse(budget.is_set()); now[0]=10.0
        self.assertTrue(budget.is_set()); self.assertTrue(event.is_set())

    def test_interrupted_outbound_and_settled_hunt_pose_are_in_return_corridor(self):
        def point(x,z):
            return {"x":x,"y":5,"z":z}
        leg = {"status":"arrived","releaseSucceeded":True,"desktopInputsDown":[],
               "survival":{"encounters":[{"traversedPath":[point(0,0),point(0,2)]}]},
               "path":[point(0,2),point(2,2)],"position":point(2.4,2)}
        document = cli._return_document(cli._walked_corridor([leg]))
        self.assertEqual(document["waypoints"],[
            ["Return 1",2.4,2],["Return 2",0,2],["Return 3",0,0]])

    def test_stop_after_encounter_retains_its_release_receipt_without_return(self):
        mission,route,_=cli.load_definition(self.mission,self.route,self.profile)
        stop=threading.Event()
        class StoppedRuntime(Runtime):
            def selected_encounter(self,adapter,**kwargs):
                stop.set()
                return {"status":"stopped","releaseSucceeded":True,"desktopInputsDown":[],
                        "selectedTargetId":TARGET,"killProof":{"qualified":False}}
        with self.assertRaisesRegex(cli.MissionError,"STOP"):
            cli.run_mission(mission=mission,route_document=route,route_path=self.route,
                profile_path=self.profile,checkpoint=self.checkpoint,adapter=Adapter(),
                runtime=StoppedRuntime(),stop=stop,playback=self.playback,emit=self.outputs.append)
        progress=json.loads(self.checkpoint.read_text())
        self.assertEqual("encounter-started",progress["stage"])
        self.assertTrue(progress["encounter"]["releaseSucceeded"])
        self.assertFalse(progress["completed"])

    def test_global_deadline_is_rechecked_after_outbound(self):
        mission,route,_=cli.load_definition(self.mission,self.route,self.profile)
        now=[10.0]
        def playback(*args, **kwargs):
            result=self.playback(*args, **kwargs); now[0]=1810.0; return result
        stop=threading.Event()
        with self.assertRaisesRegex(cli.MissionError,"deadline expired during outbound"):
            cli.run_mission(mission=mission,route_document=route,route_path=self.route,
                profile_path=self.profile,checkpoint=self.checkpoint,adapter=Adapter(),runtime=Runtime(),
                stop=stop,playback=playback,emit=self.outputs.append,clock=lambda:now[0])
        self.assertTrue(stop.is_set())

    def test_whole_mission_f8_stop_context_latches_during_encounter_and_skips_return(self):
        calls=[]
        @contextmanager
        def controls(shared_stop):
            calls.append(("controls-enter",shared_stop))
            controls.press_f8=lambda:shared_stop.set()
            try: yield
            finally: calls.append(("controls-exit",shared_stop))
        class F8Runtime(Runtime):
            def selected_encounter(self, adapter, **kwargs):
                self.calls.append(("encounter",adapter,kwargs))
                controls.press_f8()
                return {"status":"stopped","reason":"STOP requested","inputSent":False,
                    "selectedTargetId":TARGET,"releaseSucceeded":True,"desktopInputsDown":[],
                    "killProof":{"qualified":False}}
        play_stages=[]
        def playback(adapter, document, stop, emit, **options):
            play_stages.append("return" if document.get("provenance") else "outbound")
            return self.playback(adapter,document,stop,emit,**options)
        args=self.parse("run","--mission",str(self.mission),"--route",str(self.route),
            "--profile",str(self.profile),"--expected-host","AMD-DESKTOP","--physical-pid","21672",
            "--checkpoint",str(self.checkpoint),"--execute")
        shared_stop=threading.Event()
        with self.assertRaises(cli.MissionExecutionError) as caught:
            cli.execute(args,adapter_factory=lambda *_:Adapter(),runtime_factory=F8Runtime,
                playback=playback,stop=shared_stop,stop_controls=controls,
                emit=self.outputs.append,clock=lambda:10.0)
        self.assertRegex(str(caught.exception),"STOP is latched during encounter")
        self.assertTrue(shared_stop.is_set())
        self.assertEqual(["outbound"],play_stages)
        self.assertEqual(["controls-enter","controls-exit"],[item[0] for item in calls])
        self.assertIs(calls[0][1],shared_stop); self.assertIs(calls[1][1],shared_stop)

    def test_unsafe_encounter_uses_verified_safeward_trail_before_any_normal_return(self):
        encounter={"status":"blocked","reason":"selected-encounter-unsafe",
            "selectedTargetId":TARGET,"releaseSucceeded":True,"desktopInputsDown":[],
            "killProof":{"qualified":False}}
        class RetreatRuntime(Runtime):
            def route_runner(self,adapter,points,stop,emit,**kwargs):
                self.calls.append(("safe-retreat",points,kwargs))
                self.assertions=(points,kwargs)
                return [{"status":"arrived","safeRetreat":True,"releaseSucceeded":True,
                    "desktopInputsDown":[],"position":{"x":1.0,"y":5.0,"z":2.0}}]
        runtime=RetreatRuntime(encounter); playback_calls=[]
        def playback(*args,**kwargs):
            playback_calls.append("return" if args[1].get("provenance") else "outbound")
            return self.playback(*args,**kwargs)
        mission,route,_=cli.load_definition(self.mission,self.route,self.profile)
        result=cli.run_mission(mission=mission,route_document=route,route_path=self.route,
            profile_path=self.profile,checkpoint=self.checkpoint,adapter=Adapter(),runtime=runtime,
            stop=threading.Event(),playback=playback,emit=self.outputs.append,clock=lambda:10.0)
        self.assertEqual(["outbound"],playback_calls)
        points,options=runtime.assertions
        self.assertEqual([["Return 1",4.0,6.0],["Return 2",1.0,2.0]],points)
        self.assertEqual([(1.0,5.0,2.0),(4.0,5.0,6.0)],
            [(p["x"],p["y"],p["z"]) for p in options["initial_retreat_trail"]])
        self.assertTrue(options["assess_before_travel"] and options["finish_after_retreat"])
        self.assertEqual("retreated-no-qualified-kill",result["status"])
        self.assertEqual(0,result["killCount"]); self.assertTrue(result["safeReturned"])

    def test_safe_retreat_corridor_identity_is_exact(self):
        document={"provenance":{"runtimeIdentity":dict(
            Adapter.binding["runtimeIdentity"],unitKey="2")}}
        with self.assertRaisesRegex(cli.MissionError,"another runtime identity"):
            cli._verify_return_identity(document,Adapter())

    def test_local_hunt_deadline_retreats_but_global_deadline_forbids_return(self):
        mission,route,_=cli.load_definition(self.mission,self.route,self.profile)
        local={"status":"blocked","reason":"encounter-deadline","selectedTargetId":TARGET,
               "releaseSucceeded":True,"desktopInputsDown":[],"killProof":{"qualified":False}}
        class DeadlineRuntime(Runtime):
            def route_runner(self,adapter,points,stop,emit,**kwargs):
                self.calls.append(("safe-retreat",kwargs))
                return [{"status":"arrived","safeRetreat":True,"releaseSucceeded":True,
                    "desktopInputsDown":[],"position":{"x":1.0,"y":5.0,"z":2.0}}]
        runtime=DeadlineRuntime(local)
        result=cli.run_mission(mission=mission,route_document=route,route_path=self.route,
            profile_path=self.profile,checkpoint=self.checkpoint,adapter=Adapter(),runtime=runtime,
            stop=threading.Event(),playback=self.playback,emit=self.outputs.append,clock=lambda:10.0)
        self.assertEqual("retreated-no-qualified-kill",result["status"])
        self.assertEqual(1,len([call for call in runtime.calls if call[0]=="safe-retreat"]))

        checkpoint=self.root/"global-deadline.json"; now=[10.0]; runtime=Runtime(local)
        original=runtime.selected_encounter
        def encounter(*args,**kwargs):
            value=original(*args,**kwargs); now[0]=1810.0; return value
        runtime.selected_encounter=encounter; playback_calls=[]
        def playback(*args,**kwargs):
            playback_calls.append("return" if args[1].get("provenance") else "outbound")
            return self.playback(*args,**kwargs)
        stop=threading.Event()
        with self.assertRaisesRegex(cli.MissionError,"deadline expired during encounter"):
            cli.run_mission(mission=mission,route_document=route,route_path=self.route,
                profile_path=self.profile,checkpoint=checkpoint,adapter=Adapter(),runtime=runtime,
                stop=stop,playback=playback,emit=self.outputs.append,clock=lambda:now[0])
        self.assertEqual(["outbound"],playback_calls); self.assertTrue(stop.is_set())


if __name__=="__main__": unittest.main()
