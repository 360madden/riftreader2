#!/usr/bin/env python3
"""Run one explicit selected-target safe-to-hunt-to-safe mission."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.survival_profile import load_survival_profile
from scripts.survival_route_runner import _coalesce_retained_corridor
from scripts.survival_waypoints import _read_route
from scripts.waypoint_limits import MAX_TRIP_SECONDS, MAX_WAYPOINTS
from scripts.waypoint_progress import write_json_atomic

SCHEMA = "rr2-hunt-mission/1"
CHECKPOINT_SCHEMA = "rr2-hunt-mission-progress/1"
MAX_MISSION_BYTES = 64 * 1024


class MissionError(ValueError): pass


class MissionExecutionError(RuntimeError):
    def __init__(self, cause, checkpoint):
        super().__init__(str(cause)); self.cause, self.checkpoint = cause, checkpoint


class _DeadlineStop:
    """Event-compatible mission budget that permanently latches the shared STOP."""
    def __init__(self, event, deadline, clock):
        self.event, self.deadline, self.clock = event, deadline, clock
    def set(self): self.event.set()
    def is_set(self):
        if not self.event.is_set() and self.clock() >= self.deadline: self.event.set()
        return self.event.is_set()
    def wait(self, timeout=None):
        remaining = self.deadline - self.clock()
        if remaining <= 0: self.event.set(); return True
        requested = remaining if timeout is None else min(max(0, timeout), remaining)
        result = self.event.wait(requested)
        if not result and self.clock() >= self.deadline: self.event.set(); result = True
        return result


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False); super().__init__(*args, **kwargs)
        self.suggest_on_error, self.color = True, False
    def error(self, message): raise MissionError(message)


def _path(value): return Path(value).expanduser().absolute()
def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MissionError(f"{label} must be a finite number")
    return float(value)
def _sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_json(path, maximum, label):
    try: raw = path.read_bytes()
    except OSError as exc: raise MissionError(f"{label} is unreadable: {exc}") from None
    if len(raw) > maximum: raise MissionError(f"{label} exceeds {maximum} bytes")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise MissionError(f"{label} has duplicate key {key!r}")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
            parse_constant=lambda item: (_ for _ in ()).throw(
                MissionError(f"{label} has non-finite value {item}")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MissionError(f"{label} is invalid JSON: {exc}") from None
    if not isinstance(value, dict): raise MissionError(f"{label} must be an object")
    return value


def _point(value, label):
    if not isinstance(value, dict): raise MissionError(f"{label} must be an object")
    return {axis: _finite(value.get(axis), f"{label}.{axis}") for axis in ("x", "y", "z")}


def _normalize_mission(document, route_sha, profile_sha, route_document):
    if document.get("schema") != SCHEMA: raise MissionError(f"mission schema must be {SCHEMA}")
    if document.get("mode") != "explicit-selected-target":
        raise MissionError("only explicit-selected-target missions are supported")
    name = document.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 128:
        raise MissionError("mission name must be 1-128 characters")
    binding = document.get("binding")
    if not isinstance(binding, dict): raise MissionError("mission binding must be an object")
    for key, actual in (("routeSha256", route_sha), ("profileSha256", profile_sha)):
        expected = binding.get(key)
        if not isinstance(expected, str) or expected.upper() != actual:
            raise MissionError(f"mission {key} does not match the selected file")
    safe = _point(document.get("safeAnchor"), "safeAnchor")
    safe["planarTolerance"] = _finite(document["safeAnchor"].get("planarTolerance", .5),
                                       "safeAnchor.planarTolerance")
    safe["heightTolerance"] = _finite(document["safeAnchor"].get("heightTolerance", .75),
                                       "safeAnchor.heightTolerance")
    if not (0 < safe["planarTolerance"] <= 1 and 0 < safe["heightTolerance"] <= 2):
        raise MissionError("safe anchor tolerances exceed supported bounds")
    hunt = document.get("hunt")
    if not isinstance(hunt, dict): raise MissionError("hunt must be an object")
    expected = hunt.get("expectedTargetId")
    if (not isinstance(expected, str) or len(expected) != 17 or expected[:1] != "u"
            or any(c not in "0123456789abcdefABCDEF" for c in expected[1:])
            or int(expected[1:],16) == 0):
        raise MissionError("hunt.expectedTargetId must be one exact u + 16-hex ID")
    center = _point({"x": hunt.get("centerX"), "y": hunt.get("centerY", safe["y"]),
                     "z": hunt.get("centerZ")}, "hunt.center")
    radius = _finite(hunt.get("radius"), "hunt.radius")
    seconds, kills = hunt.get("maximumSeconds", 120), hunt.get("maximumKills", 2)
    if not 0 < radius <= 50: raise MissionError("hunt.radius must be greater than 0 and at most 50")
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 120:
        raise MissionError("hunt.maximumSeconds must be 1-120")
    if isinstance(kills, bool) or not isinstance(kills, int) or not 1 <= kills <= 2:
        raise MissionError("hunt.maximumKills must be 1-2")
    trip = document.get("maximumMissionSeconds", MAX_TRIP_SECONDS)
    if isinstance(trip, bool) or not isinstance(trip, int) or not 1 <= trip <= MAX_TRIP_SECONDS:
        raise MissionError(f"maximumMissionSeconds must be 1-{MAX_TRIP_SECONDS}")
    if document.get("return", {}).get("mode") != "reverse-verified-walked-corridor":
        raise MissionError("return.mode must be reverse-verified-walked-corridor")
    from scripts.physical_waypoints import route_points
    rows = route_points(route_document.get("waypoints"))
    heights = route_document.get("heights")
    first_y = heights[0] if isinstance(heights, list) and heights and heights[0] is not None else safe["y"]
    if (math.hypot(rows[0][1]-safe["x"], rows[0][2]-safe["z"]) > safe["planarTolerance"]
            or abs(float(first_y)-safe["y"]) > safe["heightTolerance"]):
        raise MissionError("outbound route does not begin at the safe anchor")
    if math.hypot(rows[-1][1]-center["x"], rows[-1][2]-center["z"]) > radius:
        raise MissionError("outbound route does not end inside the bounded hunt area")
    return {"schema": SCHEMA, "name": name, "mode": document["mode"],
        "binding": {"routeSha256": route_sha, "profileSha256": profile_sha},
        "safeAnchor": safe, "hunt": {"expectedTargetId": expected, "center": center,
        "radius": radius, "maximumSeconds": seconds, "maximumKills": kills},
        "return": {"mode": "reverse-verified-walked-corridor"}, "maximumMissionSeconds": trip}


def load_definition(mission_path, route_path, profile_path):
    route, profile = _read_route(route_path, "forward"), load_survival_profile(profile_path)
    mission = _normalize_mission(_load_json(mission_path, MAX_MISSION_BYTES, "mission"),
        _sha(route_path), _sha(profile_path), route)
    return mission, route, profile


def _walked_corridor(legs):
    corridor = []
    for number, leg in enumerate(legs, 1):
        if not isinstance(leg, dict) or leg.get("status") != "arrived":
            raise MissionError("outbound leg is not a verified arrival")
        release = [leg.get(key) for key in ("releaseSucceeded", "allInputsReleased") if key in leg]
        if not release or not all(value is True for value in release) or leg.get("desktopInputsDown", []) != []:
            raise MissionError("outbound leg input release is not verified")
        path = leg.get("path")
        if not isinstance(path, list) or not 1 <= len(path) <= 8192:
            raise MissionError("outbound leg has no bounded native path")
        # The completed forward leg begins at its last rejoin point. Earlier
        # interruptions carry the verified path from the preceding waypoint.
        prior_paths = []
        for encounter in (leg.get("survival") or {}).get("encounters", []):
            walked = encounter.get("traversedPath")
            if not isinstance(walked,list) or not 1 <= len(walked) <= 8192:
                raise MissionError("outbound interruption has no verified traversed path")
            prior_paths.extend(walked)
        settled = leg.get("position")
        for item in [*prior_paths, *path, *([settled] if settled is not None else [])]:
            point = _point(item, f"outbound leg {number} path")
            if corridor:
                planar = math.hypot(point["x"]-corridor[-1][0], point["z"]-corridor[-1][2])
                height = abs(point["y"]-corridor[-1][1])
                if planar > 2 or height > 1: raise MissionError("outbound native path is discontinuous")
                if planar <= .01 and height <= .01: continue
            corridor.append((point["x"], point["y"], point["z"]))
    if len(corridor) < 2: raise MissionError("outbound native path is too short for return")
    retained = _coalesce_retained_corridor(corridor)
    if len(retained) > MAX_WAYPOINTS: raise MissionError("return corridor exceeds waypoint limit")
    return retained


def _return_document(corridor, identity=None):
    # RouteProgress.begin admits a new route at its first waypoint.
    destinations = list(reversed(corridor))
    if not destinations: raise MissionError("verified return corridor has no destination")
    provenance={"kind":"native-retained-walked-corridor","retainedPoints":len(corridor)}
    if identity is not None: provenance["runtimeIdentity"]=deepcopy(identity)
    return {"waypoints": [[f"Return {i}", p[0], p[2]] for i,p in enumerate(destinations,1)],
        "heights": [p[1] for p in destinations],
        "provenance": provenance}


def _verify_return_identity(document, adapter):
    expected=((document.get("provenance") or {}).get("runtimeIdentity")
              if isinstance(document,dict) else None)
    actual=((getattr(adapter,"binding",None) or {}).get("runtimeIdentity"))
    keys=("machine","gameBuildSha256","unitKey")
    if (not isinstance(expected,dict) or not isinstance(actual,dict)
            or any(not isinstance(expected.get(key),str) or not expected[key]
                   or expected[key].casefold() != str(actual.get(key,"")).casefold()
                   for key in keys)):
        raise MissionError("verified return corridor belongs to another runtime identity")


def _release_verified(value):
    return isinstance(value, dict) and value.get("releaseSucceeded") is True and value.get("desktopInputsDown") == []


def _verify_return(legs, cursor):
    if not isinstance(legs,list) or not legs:
        raise MissionError("return route produced no verified legs")
    for leg in legs:
        if not isinstance(leg,dict) or leg.get("status") != "arrived":
            raise MissionError("return leg is not a verified arrival")
        if not _release_verified(leg) or leg.get("allInputsReleased",True) is not True:
            raise MissionError("return leg input release is unverified")
    if (not hasattr(cursor,"next_index") or not hasattr(cursor,"ordered_points")
            or cursor.next_index != len(cursor.ordered_points)):
        raise MissionError("return route is incomplete")


def _kill_proof(value, expected):
    proof = value.get("killProof") if isinstance(value, dict) else None
    if not isinstance(proof, dict) or proof.get("qualified") is not True: return None
    if proof.get("targetId", "").casefold() != expected.casefold():
        raise MissionError("kill proof belongs to another target")
    if proof.get("kind") != "player-kill-confirmed":
        raise MissionError("kill proof kind is not qualified for kill credit")
    return deepcopy(proof)


def _checkpoint_paths(path):
    return path.with_name(path.stem+".outbound.json"), path.with_name(path.stem+".return.json")


def _new_progress(mission, route_path, profile_path):
    return {"schema": CHECKPOINT_SCHEMA, "mission": mission["name"],
        "missionBinding": deepcopy(mission["binding"]), "routePath": str(route_path),
        "profilePath": str(profile_path), "stage": "outbound", "killCount": 0,
        "killProofs": [], "encounter": None, "returnDocument": None, "completed": False}


def _load_progress(path, mission):
    value = _load_json(path, 2*1024*1024, "mission checkpoint")
    if (value.get("schema") != CHECKPOINT_SCHEMA or value.get("missionBinding") != mission["binding"]
            or value.get("mission") != mission["name"]):
        raise MissionError("mission checkpoint does not match this mission")
    if value.get("stage") not in {"outbound","encounter","encounter-started","return",
                                  "safe-retreat-started","complete"}:
        raise MissionError("mission checkpoint stage is invalid")
    if value.get("stage") in {"encounter-started","safe-retreat-started"}:
        raise MissionError("prior encounter or retreat outcome is ambiguous; do not retry or count a kill")
    return value


def _emit(value, stream=None):
    print(json.dumps(value, sort_keys=True, separators=(",",":"), allow_nan=False),
          file=stream or sys.stdout, flush=True)


def run_mission(*, mission, route_document, route_path, profile_path, checkpoint,
                adapter, runtime, stop, playback, emit, resume=False, clock=time.monotonic):
    if stop.is_set(): raise MissionError("STOP is latched")
    outbound_checkpoint, return_checkpoint = _checkpoint_paths(checkpoint)
    if resume:
        if not checkpoint.is_file(): raise MissionError("mission checkpoint does not exist")
        progress = _load_progress(checkpoint, mission)
    else:
        if checkpoint.exists() or outbound_checkpoint.exists() or return_checkpoint.exists():
            raise MissionError("new mission checkpoint paths must not already exist")
        progress = _new_progress(mission, route_path, profile_path); write_json_atomic(checkpoint, progress)
    deadline = clock() + mission["maximumMissionSeconds"]
    mission_stop = _DeadlineStop(stop, deadline, clock)
    def require_budget(stage):
        if mission_stop.is_set():
            reason = "STOP is latched" if clock() < deadline else "mission deadline expired"
            raise MissionError(f"{reason} during {stage}")
    def event(stage): return lambda value: emit({"type":"event","stage":stage,**value})
    runtime.configure(profile_path, adapter)
    ready = runtime.preflight(adapter, mission_stop)
    if not isinstance(ready, dict) or ready.get("status") != "ready":
        raise MissionError("survival runtime preflight is not ready")
    if progress["stage"] == "outbound":
        legs, cursor = playback(adapter, route_document, mission_stop, event("outbound"),
            runner=runtime.route_runner, checkpoint=outbound_checkpoint, direction="forward",
            resume=resume and outbound_checkpoint.is_file(), face_waypoints=True)
        require_budget("outbound")
        corridor = _walked_corridor(legs)
        safe = mission["safeAnchor"]
        if (math.hypot(corridor[0][0]-safe["x"],corridor[0][2]-safe["z"]) > safe["planarTolerance"]
                or abs(corridor[0][1]-safe["y"]) > safe["heightTolerance"]):
            raise MissionError("retained outbound corridor does not reach the safe anchor")
        progress.update(stage="encounter", outboundNextIndex=cursor.next_index,
                        returnDocument=_return_document(
                            corridor,adapter.binding["runtimeIdentity"])); write_json_atomic(checkpoint, progress)
    if progress["stage"] == "encounter":
        if clock() >= deadline: raise MissionError("mission deadline expired before encounter")
        progress["stage"]="encounter-started"; write_json_atomic(checkpoint, progress)
        hunt=mission["hunt"]
        encounter=runtime.selected_encounter(adapter, stop=mission_stop,
            deadline=min(deadline,clock()+hunt["maximumSeconds"]), emit=event("encounter"),
            expected_target_id=hunt["expectedTargetId"],
            hunt_center=(hunt["center"]["x"],hunt["center"]["z"]), hunt_radius=hunt["radius"])
        if not isinstance(encounter,dict): raise MissionError("encounter returned no structured result")
        progress["encounter"]=deepcopy(encounter)
        write_json_atomic(checkpoint, progress)
        require_budget("encounter")
        if encounter.get("status") in {"stopped", "halted"}:
            mission_stop.set()
            raise MissionError("encounter stopped or halted; return movement blocked")
        status, reason = encounter.get("status"), encounter.get("reason")
        if not (status == "completed" or
                status == "blocked" and reason in {
                    "kill-credit-unverified", "selected-encounter-unsafe",
                    "encounter-deadline"}):
            raise MissionError("encounter outcome is not authorized for automatic return")
        selected = encounter.get("selectedTargetId")
        target_matches = (isinstance(selected, str)
                          and selected.casefold() == hunt["expectedTargetId"].casefold())
        if not target_matches and not (encounter.get("inputSent") is False
                                       and _release_verified(encounter)):
            write_json_atomic(checkpoint, progress)
            raise MissionError("encounter selected target changed after input or without verified release")
        proof=_kill_proof(encounter,hunt["expectedTargetId"]) if target_matches else None
        if status == "completed" and proof is None:
            raise MissionError("completed encounter has no qualified kill proof")
        if proof is not None: progress["killProofs"].append(proof); progress["killCount"]+=1
        if not _release_verified(encounter):
            write_json_atomic(checkpoint,progress)
            raise MissionError("encounter input release is unverified; return movement blocked")
        progress["stage"]=("safe-retreat-started" if encounter.get("reason") in {
                           "selected-encounter-unsafe","encounter-deadline"} else "return")
        write_json_atomic(checkpoint,progress)
    if progress["stage"] == "safe-retreat-started":
        document=progress.get("returnDocument")
        if not isinstance(document,dict): raise MissionError("verified return corridor is unavailable")
        _verify_return_identity(document,adapter)
        waypoints=document.get("waypoints"); heights=document.get("heights")
        if (not isinstance(waypoints,list) or not isinstance(heights,list)
                or len(waypoints) != len(heights)):
            raise MissionError("verified safe-retreat corridor is invalid")
        trail=[{"x":point[1],"y":height,"z":point[2]}
               for point,height in zip(reversed(waypoints),reversed(heights))]
        legs=runtime.route_runner(adapter,waypoints,mission_stop,event("safe-retreat"),
            face_waypoints=True,initial_retreat_trail=trail,
            assess_before_travel=True,finish_after_retreat=True)
        require_budget("safe retreat")
        if not legs or legs[-1].get("safeRetreat") is not True:
            raise MissionError("unsafe encounter did not complete the verified safe retreat")
        point=_point(legs[-1].get("position"),"safe retreat final position")
        safe=mission["safeAnchor"]
        if (math.hypot(point["x"]-safe["x"],point["z"]-safe["z"])>safe["planarTolerance"]
                or abs(point["y"]-safe["y"])>safe["heightTolerance"]):
            raise MissionError("safe retreat did not finish at the safe anchor")
        progress.update(stage="complete",completed=True,finalPosition=point,
                        safeRetreat=deepcopy(legs[-1])); write_json_atomic(checkpoint,progress)
    if progress["stage"] == "return":
        if clock() >= deadline: raise MissionError("mission deadline expired before return")
        document=progress.get("returnDocument")
        if not isinstance(document,dict): raise MissionError("verified return corridor is unavailable")
        _verify_return_identity(document,adapter)
        legs,cursor=playback(adapter,document,mission_stop,event("return"),runner=runtime.route_runner,
            checkpoint=return_checkpoint,direction="forward",
            resume=resume and return_checkpoint.is_file(),face_waypoints=True)
        require_budget("return")
        _verify_return(legs,cursor)
        final=legs[-1].get("position") if legs else None; point=_point(final,"return final position")
        safe=mission["safeAnchor"]
        if (math.hypot(point["x"]-safe["x"],point["z"]-safe["z"])>safe["planarTolerance"]
                or abs(point["y"]-safe["y"])>safe["heightTolerance"]):
            raise MissionError("return did not finish at safe anchor")
        progress.update(stage="complete",completed=True,returnNextIndex=cursor.next_index,
                        finalPosition=point); write_json_atomic(checkpoint,progress)
    outcome = ("completed" if progress.get("killCount",0) > 0 else
               "retreated-no-qualified-kill" if progress.get("safeRetreat") else
               "returned-no-qualified-kill")
    return {"status":outcome,"mission":mission["name"],"safeReturned":progress.get("completed") is True,
        "killCount":progress.get("killCount",0),"maximumKills":mission["hunt"]["maximumKills"],
        "additionalTargetSelection":"unsupported-explicit-selected-target-only",
        "checkpoint":str(checkpoint),"inputSent":True,"progress":progress}


def build_parser():
    from scripts import physical_rift
    parser=Parser(description=__doc__); parser.add_argument("--version",action="version",version="hunt-mission 1")
    commands=parser.add_subparsers(dest="command",required=True)
    for name in ("dry-run","preflight","run","resume"):
        command=commands.add_parser(name)
        for option in ("mission","route","profile"):
            command.add_argument("--"+option,required=True,type=_path)
        if name!="dry-run":
            command.add_argument("--expected-host",required=True,choices=physical_rift.SUPPORTED_HOSTS)
            command.add_argument("--physical-pid",required=True,type=int)
        if name in {"run","resume"}:
            command.add_argument("--checkpoint",required=True,type=_path)
            command.add_argument("--execute",action="store_true")
    return parser


def execute(args, *, adapter_factory=None, runtime_factory=None, playback=None,
            stop=None, stop_controls=None, emit=_emit, clock=time.monotonic):
    mission,route_document,_=load_definition(args.mission,args.route,args.profile)
    summary={"status":"valid","mission":mission,"route":str(args.route),
             "profile":str(args.profile),"inputSent":False}
    if args.command=="dry-run": emit(summary); return 0,summary
    if args.physical_pid<1: raise MissionError("--physical-pid must be positive")
    if args.command in {"run","resume"} and not args.execute:
        raise MissionError(f"{args.command} requires --execute")
    if adapter_factory is None:
        from scripts.physical_waypoints import DEFAULT_BASIS,PhysicalAdapter
        adapter_factory=lambda host,pid: PhysicalAdapter(host,pid,DEFAULT_BASIS)
    if runtime_factory is None:
        from scripts.waypoint_survival_runtime import WaypointSurvivalRuntime
        runtime_factory=WaypointSurvivalRuntime
    if playback is None:
        from scripts.waypoint_playback import play_route
        playback=play_route
    if stop_controls is None:
        from scripts.physical_waypoints import cli_stop_controls
        stop_controls=cli_stop_controls
    adapter,runtime=adapter_factory(args.expected_host,args.physical_pid),runtime_factory()
    shared_stop=stop or threading.Event()
    if args.command=="preflight":
        runtime.configure(args.profile,adapter)
        value=runtime.preflight(adapter,shared_stop)
        result={**summary,"status":"ready","preflight":value,
                "encounterAdmission":"rechecked-at-execution","inputSent":False}
        emit(result); return 0,result
    try:
        # Own both Ctrl+C and F8 for the complete mission, including stationary
        # encounter/recovery intervals between movement children. The context
        # and every stage receive the same underlying latch.
        with stop_controls(shared_stop):
            result=run_mission(mission=mission,route_document=route_document,route_path=args.route,
                profile_path=args.profile,checkpoint=args.checkpoint,adapter=adapter,runtime=runtime,
                stop=shared_stop,playback=playback,emit=emit,resume=args.command=="resume",clock=clock)
    except BaseException as exc: raise MissionExecutionError(exc,args.checkpoint) from exc
    emit(result); return 0,result


def main(argv=None):
    try: return execute(build_parser().parse_args(argv))[0]
    except MissionError as exc:
        _emit({"status":"invalid","reason":str(exc),"inputSent":False},sys.stderr); return 2
    except MissionExecutionError as exc:
        stopped="stop" in str(exc.cause).casefold()
        _emit({"status":"stopped" if stopped else "refused","reason":str(exc.cause),
               "checkpoint":str(exc.checkpoint),"inputSent":None},sys.stderr)
        return 130 if stopped else 3
    except Exception as exc:
        _emit({"status":"refused","reason":str(exc),"inputSent":None},sys.stderr); return 3


if __name__=="__main__": raise SystemExit(main())
