"""Plan a saved RiftWorld destination and optionally adopt a walked corridor.

The default is offline: it prepares distinct output files and never changes the
loaded Waypoints route. Native receipts qualify only their corresponding route
section. Execution requires --execute and an exact existing --session, and uses
the existing Waypoints route runner rather than another input controller.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.waypoint_candidate_adoption import adopt_receipt_candidate, _adoption_digest
from scripts.waypoint_navigation_candidate import _read_document, inspect_candidate, MAX_CANDIDATE_BYTES
from scripts.waypoint_progress import write_json_atomic


SCHEMA = "rr2.destination-plan/1"
RIFTWORLD_ROOT = ROOT.parent / "RiftWorld"


def _read(path):
    value, digest = _read_document(path, MAX_CANDIDATE_BYTES)
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value, digest


def _hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _reference(path):
    return {"path": str(Path(path).resolve()), "sha256": _hash(path)}


def _xyz(value):
    values = value.split(",") if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError("start requires X,Y,Z")
    if any(isinstance(axis, bool) for axis in values):
        raise ValueError("start requires finite X,Y,Z")
    result = [float(axis) for axis in values]
    if any(not math.isfinite(axis) for axis in result):
        raise ValueError("start requires finite X,Y,Z")
    return result


def _publication(candidate_path, receipt_path, *, catalog_path, destination, start, inputs):
    candidate, candidate_hash = _read(candidate_path)
    review = inspect_candidate(candidate)
    receipt, _ = _read(receipt_path)
    catalog, _ = _read(catalog_path)
    entry = next((row for row in catalog.get("destinations", [])
                  if isinstance(row, dict) and row.get("id") == destination), None)
    qualification = ({"destinationState": entry.get("derivationState"),
                      "destinationQualification": entry.get("qualification"),
                      "destinationEvidence": entry.get("evidence"),
                      "traversal": candidate["evidence"].get("traversal")} if entry else None)
    ref = receipt.get("candidate", {})
    if (receipt.get("schema") != "riftworld.destination-query-receipt/1"
            or not entry or receipt.get("destination", {}).get("entry") != entry
            or receipt["destination"].get("entryHash") != _identity(entry)
            or receipt.get("catalog") != inputs["catalog"]
            or Path(str(ref.get("path", ""))).resolve() != candidate_path
            or str(ref.get("sha256", "")).casefold() != candidate_hash.casefold()
            or ref.get("candidateId") != candidate["candidateId"]
            or ref.get("status") != candidate["status"]
            or ref.get("evidence") != candidate["evidence"]
            or receipt.get("patchId") != candidate["patchId"]
            or receipt.get("buildId") != candidate["planner"]["buildId"]
            or receipt.get("qualification") != qualification
            or receipt.get("query", {}).get("requestedStartXYZ") != start
            or candidate["query"]["requestedStartXYZ"] != start
            or receipt["query"].get("selectedApproachXYZ") != entry.get("approachXYZ")
            or candidate["query"]["requestedGoalXYZ"] != entry.get("approachXYZ")):
        raise ValueError("destination-publication-context-mismatch")
    for name, reference in inputs.items():
        if _hash(reference["path"]) != reference["sha256"]:
            raise ValueError("planning-input-changed: " + name)
    patch, _ = _read(inputs["patch"]["path"])
    build, _ = _read(inputs["build"]["path"])
    if (candidate["patchId"] != patch.get("patchId")
            or candidate["planner"]["buildId"] != build.get("buildId")):
        raise ValueError("destination-publication-build-mismatch")
    return candidate, receipt, review


def _session_state(session, runner):
    command = [sys.executable, str(ROOT / "scripts" / "waypoints_cli.py"),
               "status", "--session", session, "--json"]
    result = runner(command, cwd=ROOT, text=True, capture_output=True, check=False)
    try:
        response = json.loads(result.stdout)
        data = response["data"]
        controls = data["controls"]
        target = data["target"]
        epoch = controls["stopEpoch"]
        if (result.returncode != 0 or response.get("ok") is not True
                or response.get("sessionId") != session or not isinstance(target, dict)
                or str(target.get("machineName") or target.get("hostName", "")).casefold()
                   != platform.node().casefold()
                or any(target.get(key) is None for key in
                       ("processId", "processStartUtcTicks", "executableSha256"))
                or controls.get("stopLatched") is not False
                or controls.get("ownedActionActive") is not False
                or controls.get("inputReleaseFault") is not False
                or data.get("app", {}).get("busy") is not False
                or data["app"].get("closing") is not False
                or type(epoch) not in (int, float) or not math.isfinite(epoch)):
            raise ValueError("session-not-idle-or-stop-latched")
        return {"sessionId": session, "target": data["target"], "stopEpoch": epoch}
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("execution-session-unavailable: " + str(exc)) from exc


def _dispatch(route_path, session, epoch, runner):
    """Use the session's existing external-file route action; never loads a route."""
    command = [sys.executable, str(ROOT / "scripts" / "waypoints_cli.py"),
               "route", "run", "--file", str(route_path), "--route-sha256", _hash(route_path),
               "--stop-epoch", str(epoch), "--session", session,
               "--execute", "--json"]
    result = runner(command, cwd=ROOT, text=True, capture_output=True, check=False)
    try:
        response = json.loads(result.stdout)
    except (ValueError, TypeError):
        response = None
    return {"exitCode": result.returncode, "response": response,
            "stdout": result.stdout, "stderr": result.stderr}


def _execution_result(plan, route_path):
    execution = plan["execution"]
    response = execution.get("response")
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or str(data.get("executedRouteSha256", "")).casefold() != _hash(route_path).casefold():
        plan["status"], plan["stages"]["execution"] = "blocked", "dispatch-refused-or-unverified"
        plan["blockers"].append("external-route-dispatch-refused-or-route-hash-unverified")
        return
    receipt_path = Path(str(data.get("receipt", ""))).resolve()
    receipt, _ = _read(receipt_path)
    execution["receipt"] = _reference(receipt_path)
    route, _ = _read(route_path)
    owner = route["candidateAdoption"]["owner"]
    target = plan["executionAdmission"]["target"]
    runtime = (receipt.get("calibrationBinding") or {}).get("runtimeIdentity")
    expected = {"machine": target.get("machineName") or target.get("hostName"),
                "gameBuildSha256": target.get("executableSha256"),
                "processId": target.get("processId"),
                "processStartUtcTicks": target.get("processStartUtcTicks"),
                "unitKey": owner["unitKey"]}
    if (str(receipt.get("externalRouteSha256", "")).casefold() != _hash(route_path).casefold()
            or not isinstance(response.get("requestId"), str) or not response["requestId"]
            or receipt.get("requestId") != response["requestId"]
            or response.get("sessionId") != plan["executionAdmission"]["sessionId"]
            or receipt.get("operation") != "go"
            or receipt.get("movementEngine") not in {"continuous", "survival"}
            or not isinstance(runtime, dict)
            or any(expected[key] is None or
                   (str(runtime.get(key, "")) != str(value) if key == "unitKey" else
                    str(runtime.get(key, "")).casefold() != str(value).casefold())
                   for key, value in expected.items())
            or any(str(runtime.get(key, "")).casefold() != str(owner[key]).casefold()
                   for key in ("machine", "gameBuildSha256"))):
        raise ValueError("execution-receipt-route-request-or-runtime-mismatch")
    failure = receipt.get("failure")
    legs = receipt.get("result")
    observed = list(legs) if isinstance(legs, list) else []
    observed += receipt.get("completedLegs", [])
    plan["inputSent"] = any(row.get("inputSent") is True or row.get("pulses", 0) > 0
                            or row.get("totalHoldMs", 0) > 0
                            for row in observed if isinstance(row, dict)) or None
    if failure or response.get("ok") is not True or execution["exitCode"] != 0:
        status = failure.get("status") if isinstance(failure, dict) else None
        plan["status"] = status if status in {"stopped", "halted", "blocked"} else "execution-unverified"
        plan["stages"]["execution"] = plan["status"]
        plan["blockers"].append("route-dispatch-did-not-complete")
        return
    if (receipt.get("status") != "completed" or receipt.get("inputReleaseFault") is not False
            or not isinstance(legs, list) or not legs
            or any(not isinstance(leg, dict) or leg.get("status") != "arrived"
                   or leg.get("releaseSucceeded") is not True or leg.get("desktopInputsDown") != []
                   for leg in legs)):
        raise ValueError("route-completion-or-input-release-unverified")
    position = legs[-1].get("position")
    if not isinstance(position, dict):
        raise ValueError("destination-arrival-pose-unavailable")
    xyz = _xyz([position.get(axis) for axis in "xyz"])
    approach = plan["destination"]["entry"]["approachXYZ"]
    tolerance = plan["destination"]["entry"].get("arrivalTolerance") or .30
    distance = math.hypot(xyz[0] - approach[0], xyz[2] - approach[2])
    height_error = abs(xyz[1] - approach[1])
    arrived = plan["destinationCovered"] and distance <= tolerance + 1e-9 and height_error <= .5 + 1e-9
    plan["arrival"] = {"status": "arrived-at-approach" if arrived else "route-complete-only",
                       "positionXYZ": xyz, "planarDistance": distance,
                       "planarTolerance": tolerance, "heightError": height_error,
                       "heightTolerance": .5, "serviceInteraction": "not-attempted"}
    plan["status"] = plan["stages"]["execution"] = plan["arrival"]["status"]


def plan_destination(*, catalog, destination, patch, build, start, output_directory,
                     riftworld_root=RIFTWORLD_ROOT, riftworld_python=None,
                     native_receipts=(), native_context=None, native_start=None,
                     native_end=None, candidate_start=0, candidate_end=None,
                     execute=False, session=None, search_extent=None,
                     runner=subprocess.run):
    """Publish an offline destination plan, with optional scoped adoption/dispatch.

    A new output directory is mandatory. Query/adoption failures retain useful
    files and a structured plan. No operation replaces the current route.
    """
    start = _xyz(start)
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("destination ID is required")
    if execute and (not isinstance(session, str) or not session.strip()):
        raise ValueError("execution requires an exact session")
    supplied = bool(native_receipts) or any(value is not None for value in
                                          (native_context, native_start, native_end))
    if supplied and (not native_receipts or native_context is None
                     or native_start is None or native_end is None):
        raise ValueError("native adoption requires receipts, context and inclusive native range")
    if search_extent is not None and (isinstance(search_extent, bool)
                                     or not math.isfinite(search_extent) or search_extent <= 0):
        raise ValueError("search extent must be finite and positive")
    world_root = Path(riftworld_root).resolve()
    python = Path(riftworld_python or world_root / ".venv" / "Scripts" / "python.exe").resolve()
    query_tool = world_root / "tools" / "query_destination.py"
    if not python.is_file() or not query_tool.is_file():
        raise ValueError("RiftWorld Python or destination query tool is unavailable")
    catalog, patch, build = (Path(value).resolve() for value in (catalog, patch, build))
    build_file = build / "navigation.json" if build.is_dir() else build
    inputs = {name: _reference(path) for name, path in
              (("catalog", catalog), ("patch", patch), ("build", build_file))}
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidate_path, receipt_path = output / "candidate.json", output / "destination.json"
    plan_path, route_path = output / "plan.json", output / "adopted-route.json"
    plan = {"schema": SCHEMA, "createdAtUtc": datetime.now(timezone.utc).isoformat(),
            "status": "blocked", "destinationId": destination, "requestedStartXYZ": start,
            "inputs": inputs, "stages": {"query": "pending", "adoption": "not-requested",
                                          "execution": "not-requested"},
            "blockers": [], "inputSent": False, "currentRouteChanged": False,
            "qualification": "Prepared-map planning and corresponding walked-corridor reuse only; "
                             "no global transform, collision, service-use or live authority."}

    def publish():
        write_json_atomic(plan_path, plan)
        return deepcopy(plan)

    command = [str(python), str(query_tool), "--catalog", str(catalog),
               "--destination", destination, "--patch", str(patch), "--build", str(build),
               "--from", ",".join(format(axis, ".17g") for axis in start),
               "--out", str(candidate_path), "--receipt", str(receipt_path)]
    if search_extent is not None:
        command += ["--search-extent", format(search_extent, ".17g")]
    try:
        if execute:
            plan["executionAdmission"] = _session_state(session, runner)
        query = runner(command, cwd=world_root, text=True, capture_output=True, check=False)
        plan["queryProcess"] = {"exitCode": query.returncode, "stdout": query.stdout,
                                "stderr": query.stderr}
        if not candidate_path.is_file() or not receipt_path.is_file():
            raise ValueError("destination-query-did-not-publish")
        candidate, receipt, review = _publication(candidate_path, receipt_path,
            catalog_path=catalog, destination=destination, start=start, inputs=inputs)
        plan.update(candidate=_reference(candidate_path), destinationReceipt=_reference(receipt_path),
                    destination=deepcopy(receipt["destination"]), review=review)
        plan["stages"]["query"] = candidate["status"]
        if candidate["status"] != "complete":
            raise ValueError("complete-candidate-required")
        if query.returncode != 0:
            raise ValueError("destination-query-returned-failure")
        plan["status"] = "planned"
        if not supplied:
            plan["stages"]["adoption"] = "native-evidence-required"
            plan["blockers"].append("independent-native-evidence-required-for-adoption")
            if execute:
                plan["status"] = "blocked"
                plan["stages"]["execution"] = "blocked"
            return publish()
        plan["stages"]["adoption"] = "pending"
        end = len(candidate["points"]) - 1 if candidate_end is None else candidate_end
        route = adopt_receipt_candidate(candidate, [Path(path).resolve() for path in native_receipts],
            Path(native_context).resolve(), candidate_start=candidate_start, candidate_end=end,
            native_start=native_start, native_end=native_end, direction="forward")
        route["candidateAdoption"]["destinationProvenance"] = {
            "receipt": _reference(receipt_path), "destination": deepcopy(receipt["destination"]),
            "qualification": deepcopy(receipt["qualification"])}
        route["candidateAdoption"]["integritySha256"] = _adoption_digest(route)
        write_json_atomic(route_path, route)
        plan.update(status="adoptable", adoptedRoute=_reference(route_path),
                    destinationCovered=candidate_start == 0 and end == len(candidate["points"]) - 1)
        plan["stages"]["adoption"] = "adopted-corresponding-corridor"
        if execute:
            current = _session_state(session, runner)
            if current != plan["executionAdmission"]:
                raise ValueError("execution-session-or-stop-epoch-changed-during-planning")
            plan["status"], plan["stages"]["execution"] = "running", "running"
            plan["inputSent"] = None
            publish()
            plan["execution"] = _dispatch(route_path, session, current["stopEpoch"], runner)
            _execution_result(plan, route_path)
        return publish()
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        plan["status"] = "execution-unverified" if plan["stages"]["execution"] == "running" else "blocked"
        if plan["stages"]["query"] == "pending":
            plan["stages"]["query"] = "failed"
        elif plan["stages"]["adoption"] == "pending":
            plan["stages"]["adoption"] = "blocked"
        plan["blockers"].append(str(exc))
        return publish()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("catalog", "patch", "build"):
        result.add_argument("--" + name, type=Path, required=True)
    result.add_argument("--destination", required=True)
    result.add_argument("--from", dest="start", type=_xyz, required=True)
    result.add_argument("--out-dir", dest="output_directory", type=Path, required=True)
    result.add_argument("--riftworld-root", type=Path, default=RIFTWORLD_ROOT)
    result.add_argument("--riftworld-python", type=Path)
    result.add_argument("--native-receipt", dest="native_receipts", type=Path, action="append", default=[])
    result.add_argument("--native-context", type=Path)
    for name, default in (("native-start", None), ("native-end", None),
                          ("candidate-start", 0), ("candidate-end", None)):
        result.add_argument("--" + name, type=int, default=default,
                            help="zero-based inclusive evidence index")
    result.add_argument("--search-extent", type=float)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--session")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = plan_destination(**vars(args))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 130 if result["status"] == "stopped" else 2 if result["status"] in {
            "blocked", "halted", "execution-unverified"} else 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "blockers": [str(exc)],
                          "inputSent": None if args.execute else False,
                          "currentRouteChanged": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
