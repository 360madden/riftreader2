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
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.waypoint_candidate_adoption import adopt_receipt_candidate, _adoption_digest
from scripts.waypoint_navigation_candidate import _read_document, inspect_candidate, MAX_CANDIDATE_BYTES
from scripts.waypoint_progress import write_json_atomic


SCHEMA = "rr2.destination-plan/1"
RIFTWORLD_ROOT = ROOT.parent / "RiftWorld"


def _read(path, limit=MAX_CANDIDATE_BYTES):
    value, digest = _read_document(path, limit)
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


def _publication(candidate_path, receipt_path, *, catalog_path, destination, start, inputs,
                 validator=None):
    candidate, candidate_hash = _read(candidate_path)
    review = inspect_candidate(candidate)
    receipt, receipt_hash = _read(receipt_path)
    publication_refs = {"candidate": {"path": str(candidate_path), "sha256": candidate_hash},
                        "receipt": {"path": str(receipt_path), "sha256": receipt_hash}}
    catalog, _ = _read(catalog_path)
    entry = next((row for row in catalog.get("destinations", [])
                  if isinstance(row, dict) and row.get("id") == destination), None)
    qualification = ({"destinationState": entry.get("derivationState"),
                      "destinationQualification": entry.get("qualification"),
                      "destinationEvidence": entry.get("evidence"),
                      "traversal": candidate["evidence"].get("traversal")} if entry else None)
    ref = receipt.get("candidate", {})
    if (receipt.get("schema") not in {"riftworld.destination-query-receipt/1", "riftworld.destination-query-receipt/2"}
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
        if _hash(reference["path"]).casefold() != str(reference["sha256"]).casefold():
            raise ValueError("planning-input-changed: " + name)
    patch, _ = _read(inputs["patch"]["path"])
    build, _ = _read(inputs["build"]["path"])
    if (candidate["patchId"] != patch.get("patchId")
            or candidate["planner"]["buildId"] != build.get("buildId")):
        raise ValueError("destination-publication-build-mismatch")
    if receipt["schema"] == "riftworld.destination-query-receipt/2":
        if validator is None:
            raise ValueError("source-destination-receipt-requires-authoritative-validation")
        validator(candidate, receipt, publication_refs)
    # Authoritative source validation can take substantial time. Retain the
    # original hashes, including candidate/receipt bytes used to build the
    # parsed objects, rather than accepting newly hashed replacement files.
    for name, reference in inputs.items():
        if _hash(reference["path"]).casefold() != str(reference["sha256"]).casefold():
            raise ValueError("planning-input-changed-during-validation: " + name)
    for name, reference in publication_refs.items():
        if _hash(reference["path"]).casefold() != reference["sha256"].casefold():
            raise ValueError("destination-publication-changed-during-validation: " + name)
    return candidate, receipt, review


def _inside_bounds(point, bounds):
    return (isinstance(bounds, list) and len(bounds) == 6
            and all(type(value) in (int, float) and math.isfinite(value) for value in bounds)
            and all(bounds[axis] <= point[axis] <= bounds[axis + 3] for axis in range(3)))


def _prepared_handoff(path, *, request_path, index_path, inputs, profile_path=None):
    """Read only the compact source-side contract; large descriptors are streamed."""
    handoff, _ = _read(path, 1024 * 1024)
    if handoff.get("schema") != "riftworld.prepared-navigation-handoff/1":
        raise ValueError("unsupported-prepared-navigation-handoff")
    for name, identity in (("preparation", "preparationId"), ("sourceIndex", "sourceIndexId"),
                           ("sourceCatalog", "catalogId"), ("areaRequest", "areaRequestId"),
                           ("patch", "patchId"), ("navigation", "buildId")):
        ref = handoff.get(name)
        if (not isinstance(ref, dict) or not isinstance(ref.get("descriptor"), str)
                or not re.fullmatch(r"[a-fA-F0-9]{64}", str(ref.get(identity, "")))
                or str(ref.get("descriptorSha256", "")).casefold()
                   != _hash(ref["descriptor"]).casefold()):
            raise ValueError("prepared-handoff-reference-mismatch: " + name)
    for name, input_name, expected_path in (("areaRequest", "areaRequest", request_path),
                                             ("sourceIndex", "sourceIndex", index_path)):
        ref = handoff[name]
        if (Path(ref["descriptor"]).resolve() != expected_path
                or ref["descriptorSha256"].casefold() != inputs[input_name]["sha256"].casefold()):
            raise ValueError("prepared-handoff-input-mismatch: " + name)
    request, _ = _read(request_path)
    if (request.get("areaRequestId") != handoff["areaRequest"]["areaRequestId"]
            or handoff.get("sourceWorld") != request.get("sourceWorld")):
        raise ValueError("prepared-handoff-request-identity-mismatch")
    patch_path = Path(handoff["patch"]["descriptor"]).resolve()
    build_path = Path(handoff["navigation"]["descriptor"]).resolve()
    patch, _ = _read(patch_path)
    build, _ = _read(build_path)
    if (request.get("sourceWorld", {}).get("key") != patch.get("sourceWorld")
            or any(patch.get("coordinates", {}).get(key) != value
                   for key, value in request.get("coordinateFrame", {}).items())
            or patch.get("patchId") != handoff["patch"]["patchId"]
            or patch.get("coordinates") != handoff.get("coordinates")
            or patch.get("requestedBounds") != handoff.get("requestedBounds")
            or build.get("buildId") != handoff["navigation"]["buildId"]
            or build.get("worldContext") != {"patchId": patch["patchId"],
                "sourceWorld": patch["sourceWorld"], "coordinates": patch["coordinates"]}
            or build.get("sourceObjSha256") != patch.get("content", {}).get("geometrySha256")):
        raise ValueError("prepared-handoff-patch-build-context-mismatch")
    profile = handoff.get("navigationProfile", {})
    if (profile.get("value") != build.get("profile") or
            str(profile.get("semanticSha256", "")).casefold() != _identity(profile.get("value")).casefold()):
        raise ValueError("prepared-handoff-navigation-profile-mismatch")
    profile_input = profile.get("input")
    if profile_path is None:
        if profile_input is not None:
            raise ValueError("prepared-handoff-unrequested-profile-input")
    else:
        if (not isinstance(profile_input, dict)
                or Path(str(profile_input.get("descriptor", ""))).resolve() != profile_path
                or str(profile_input.get("descriptorSha256", "")).casefold()
                   != inputs["navigationProfileInput"]["sha256"].casefold()):
            raise ValueError("prepared-handoff-profile-input-mismatch")
        overrides, _ = _read(profile_path, 1024 * 1024)
        if any(type(value) not in (int, float) or not math.isfinite(value)
               or key not in profile["value"] or profile["value"][key] != value
               for key, value in overrides.items()):
            raise ValueError("requested-profile-overrides-do-not-match-prepared-navigation")
    return handoff, patch_path, build_path


def _validated_destination(python, world_root, candidate_path, receipt_path, inputs, runner,
                           candidate, receipt, prepared=None, publication_refs=None):
    result = runner([str(python), "-m", "riftworld", "validate-destination-receipt",
                     "--candidate", str(candidate_path), "--receipt", str(receipt_path)],
                    cwd=world_root, text=True, capture_output=True, check=False)
    if len(result.stdout.encode("utf-8")) > 1024 * 1024:
        raise ValueError("authoritative-destination-validation-output-too-large")
    validation = json.loads(result.stdout)
    if not isinstance(validation, dict):
        raise ValueError("authoritative-destination-validation-must-be-an-object")
    if publication_refs is None:
        raise ValueError("original-destination-publication-hashes-required")
    expected_candidate = {**publication_refs["candidate"], "candidateId": candidate["candidateId"]}
    expected_navigation = {"descriptor": inputs["build"]["path"],
                           "descriptorSha256": inputs["build"]["sha256"],
                           "buildId": candidate["planner"]["buildId"]}
    if (result.returncode != 0 or validation.get("schema") != "riftworld.destination-receipt-validation/1"
            or validation.get("candidate") != expected_candidate
            or validation.get("receipt") != publication_refs["receipt"]
            or validation.get("patch") != receipt.get("patch")
            or validation.get("patch") != {"descriptor": inputs["patch"]["path"],
                "descriptorSha256": inputs["patch"]["sha256"], "patchId": candidate["patchId"]}
            or validation.get("navigation") != expected_navigation
            or receipt.get("navigation") != expected_navigation
            or validation.get("binding") != receipt.get("binding")
            or validation.get("qualification") != receipt.get("qualification")):
        raise ValueError("authoritative-destination-receipt-validation-mismatch")
    binding = validation["binding"]
    if (not isinstance(binding, dict) or binding.get("schema") != "riftworld.destination-patch-binding/1"
            or binding.get("mode") not in {"source-index", "exact-patch"}
            or binding.get("patchId") != candidate["patchId"]):
        raise ValueError("authoritative-destination-binding-invalid")
    if prepared and binding.get("mode") != "source-index":
        raise ValueError("prepared-destination-must-use-source-index-binding")
    if prepared:
        expected_preparation = {"descriptor": inputs["preparation"]["path"],
            "descriptorSha256": inputs["preparation"]["sha256"],
            "preparationId": prepared["preparation"]["preparationId"]}
        if (validation.get("preparation") != expected_preparation
                or receipt.get("preparation") != expected_preparation):
            raise ValueError("destination-preparation-proof-does-not-match-handoff")
        if (binding.get("sourceIndexId") != prepared["sourceIndex"]["sourceIndexId"]
                or binding.get("areaRequestId") not in {None, prepared["areaRequest"]["areaRequestId"]}
                or binding.get("requestedBounds") != prepared["requestedBounds"]):
            raise ValueError("destination-binding-does-not-match-prepared-area")
    return validation


def _session_state(session, runner, *, allow_latched=False, identity_out=None):
    command = [sys.executable, str(ROOT / "scripts" / "waypoints_cli.py"),
               "status", "--session", session, "--timeout", "1", "--json"]
    result = runner(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=2)
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
                or type(controls.get("stopLatched")) is not bool
                or not allow_latched and controls["stopLatched"]
                or controls.get("ownedActionActive") is not False
                or controls.get("inputReleaseFault") is not False
                or data.get("app", {}).get("busy") is not False
                or data["app"].get("closing") is not False
                or type(epoch) not in (int, float) or not math.isfinite(epoch)):
            raise ValueError("session-not-idle-or-stop-latched")
        admission = {"sessionId": session, "target": data["target"], "stopEpoch": epoch,
                     "stopLatched": controls["stopLatched"]}
        if identity_out is not None:
            pose = data.get("pose")
            if isinstance(pose, dict):
                owner = pose.get("runtimeIdentity")
                try:
                    limit, age = pose.get("freshForSeconds"), pose.get("ageSeconds")
                    stamp = datetime.fromisoformat(pose["sampledAtUtc"].replace("Z", "+00:00"))
                    elapsed = (datetime.now(timezone.utc) - stamp).total_seconds()
                    if (pose.get("status") == "fresh" and pose.get("sampleStatus") == "fresh"
                            and pose.get("target") == target and _identity_matches_target(owner, target)
                            and type(limit) in (int, float) and 0 < limit <= 2
                            and type(age) in (int, float) and 0 <= age <= limit
                            and -.1 <= elapsed <= limit and isinstance(pose.get("source"), str)):
                        identity_out.update(runtimeIdentity=deepcopy(owner), target=deepcopy(target),
                            sessionId=session, source=pose["source"], sampledAtUtc=pose["sampledAtUtc"],
                            ageSecondsAtValidation=elapsed, acquiredBy="session-status")
                except (KeyError, TypeError, ValueError):
                    pass  # An explicit input-free identity read is the fallback.
        return admission
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("execution-session-unavailable: " + str(exc)) from exc


def _same_runtime(left, right):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return all(left.get(key) is not None and right.get(key) is not None and
               (str(left[key]) == str(right[key]) if key == "unitKey" else
                str(left[key]).casefold() == str(right[key]).casefold())
               for key in ("machine", "processId", "processStartUtcTicks", "gameBuildSha256", "unitKey"))


def _identity_matches_target(identity, target):
    return (isinstance(identity, dict) and isinstance(identity.get("unitKey"), str)
            and bool(identity["unitKey"])
            and str(identity.get("machine", "")).casefold()
               == str(target.get("machineName") or target.get("hostName", "")).casefold()
            and str(identity.get("gameBuildSha256", "")).casefold()
               == str(target["executableSha256"]).casefold()
            and all(str(identity.get(key, "")) == str(target[key])
                    for key in ("processId", "processStartUtcTicks")))


def _current_pose(session, admission, runner, *, allow_latched):
    """Acquire one existing reader sample, with current process/player provenance."""
    command = [sys.executable, str(ROOT / "scripts" / "waypoints_cli.py"),
               "pose", "refresh", "--session", session, "--json"]
    result = runner(command, cwd=ROOT, text=True, capture_output=True, check=False)
    response = json.loads(result.stdout)
    data = response.get("data")
    if (result.returncode != 0 or response.get("ok") is not True
            or response.get("sessionId") != session or not isinstance(data, dict)):
        raise ValueError("current-native-pose-unavailable")
    position, identity = data.get("position"), data.get("runtimeIdentity")
    target = admission["target"]
    if data.get("target") != target or not _identity_matches_target(identity, target):
        raise ValueError("current-native-pose-owner-or-target-mismatch")
    age, limit = data.get("ageSeconds"), data.get("freshForSeconds")
    source, stamp = data.get("source"), data.get("sampledAtUtc")
    if (data.get("status") != "fresh" or data.get("sampleStatus") != "fresh"
            or type(age) not in (int, float) or not math.isfinite(age)
            or type(limit) not in (int, float) or not math.isfinite(limit)
            or not 0 < limit <= 2 or not 0 <= age <= limit
            or not isinstance(source, str) or not source.strip()
            or not isinstance(stamp, str)):
        raise ValueError("current-native-pose-stale-or-provenance-unavailable")
    try:
        sampled = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - sampled).total_seconds()
        if sampled.utcoffset() != timezone.utc.utcoffset(sampled) or not -.1 <= elapsed <= limit:
            raise ValueError("current-native-pose-stale")
    except (ValueError, TypeError) as exc:
        raise ValueError("current-native-pose-stale-or-invalid-timestamp") from exc
    if not isinstance(position, dict):
        raise ValueError("current-native-position-unavailable")
    xyz = _xyz([position.get(axis) for axis in "xyz"])
    current = _session_state(session, runner, allow_latched=allow_latched)
    if current != admission:
        raise ValueError("session-or-stop-epoch-changed-during-pose-acquisition")
    return {"nativeXYZ": xyz, "source": source, "sampledAtUtc": stamp,
            "validatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "ageSecondsAtValidation": elapsed, "readerReportedAgeSeconds": age,
            "freshForSeconds": limit, "runtimeIdentity": deepcopy(identity),
            "target": deepcopy(target), "sessionId": session,
            "poseRequestId": response.get("requestId"), "inputSent": False}


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


def plan_destination(*, catalog, destination, output_directory, patch=None, build=None,
                     prepare_request=None, source_index=None, allow_partial_navigation=False,
                     prepare_profile=None, prepare_timeout_seconds=600,
                     start=None, from_current=False,
                     riftworld_root=RIFTWORLD_ROOT, riftworld_python=None,
                     native_receipts=(), native_context=None, native_start=None,
                     native_end=None, candidate_start=0, candidate_end=None,
                     execute=False, session=None, search_extent=None,
                     runner=subprocess.run, preparation_runner=None):
    """Publish an offline destination plan, with optional scoped adoption/dispatch.

    A new output directory is mandatory. Query/adoption failures retain useful
    files and a structured plan. No operation replaces the current route.
    """
    if bool(from_current) == (start is not None):
        raise ValueError("choose exactly one explicit start or from-current")
    start = _xyz(start) if start is not None else None
    preparing = prepare_request is not None or source_index is not None
    if (preparing and (prepare_request is None or source_index is None or patch is not None or build is not None)
            or not preparing and (patch is None or build is None)):
        raise ValueError("choose prepared patch+build or prepare-request+source-index")
    if preparing and allow_partial_navigation is not True:
        raise ValueError("preparation navigation requires explicit allow-partial-navigation")
    if (type(prepare_timeout_seconds) not in (int, float) or not math.isfinite(prepare_timeout_seconds)
            or not 0 < prepare_timeout_seconds <= 3600):
        raise ValueError("prepare timeout must be finite and within 0..3600 seconds")
    if prepare_profile is not None and not preparing:
        raise ValueError("prepare-profile requires preparation mode")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("destination ID is required")
    if (execute or from_current) and (not isinstance(session, str) or not session.strip()):
        raise ValueError("execution or from-current requires an exact session")
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
    catalog = Path(catalog).resolve()
    inputs = {"catalog": _reference(catalog)}
    if preparing:
        destination_catalog, _ = _read(catalog)
        prepared_entry = next((entry for entry in destination_catalog.get("destinations", [])
                               if isinstance(entry, dict) and entry.get("id") == destination), None)
        declared_binding = prepared_entry.get("preparationBinding") if prepared_entry else None
        if (not isinstance(declared_binding, dict)
                or declared_binding.get("schema") != "riftworld.destination-source-binding/1"
                or declared_binding.get("kind") != "source-index"
                or set(declared_binding) - {"schema", "kind", "sourceIndexId", "areaRequestId"}
                or not re.fullmatch(r"[a-f0-9]{64}", str(declared_binding.get("sourceIndexId", "")))
                or "areaRequestId" in declared_binding and not re.fullmatch(
                    r"[a-f0-9]{64}", str(declared_binding["areaRequestId"]))):
            raise ValueError("preparation-mode-requires-predeclared-source-bound-destination")
        if any(isinstance(item, str) and item.startswith("patchId:")
               for item in prepared_entry.get("evidence", [])):
            raise ValueError("ambiguous-source-and-exact-patch-destination-binding")
        prepare_request, source_index = Path(prepare_request).resolve(), Path(source_index).resolve()
        inputs.update(areaRequest=_reference(prepare_request), sourceIndex=_reference(source_index))
        if prepare_profile is not None:
            prepare_profile = Path(prepare_profile).resolve()
            inputs["navigationProfileInput"] = _reference(prepare_profile)
    else:
        patch, build = Path(patch).resolve(), Path(build).resolve()
        build_file = build / "navigation.json" if build.is_dir() else build
        inputs.update(patch=_reference(patch), build=_reference(build_file))
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidate_path, receipt_path = output / "candidate.json", output / "destination.json"
    plan_path, route_path = output / "plan.json", output / "adopted-route.json"
    handoff_path, preparation_receipt = output / "prepared-navigation.json", output / "preparation-run.json"
    plan = {"schema": SCHEMA, "createdAtUtc": datetime.now(timezone.utc).isoformat(),
            "status": "blocked", "destinationId": destination, "requestedStartXYZ": start,
            "startSource": "current-native" if from_current else "explicit-source-coordinates",
            "inputs": inputs, "stages": {"query": "not-started", "adoption": "not-requested",
                                          "execution": "not-requested"},
            "blockers": [], "inputSent": False, "currentRouteChanged": False,
            "qualification": "Prepared-map planning and corresponding walked-corridor reuse only; "
                             "no global transform, collision, service-use or live authority."}
    if preparing:
        plan["stages"]["preparation"] = "pending"

    def publish():
        write_json_atomic(plan_path, plan)
        return deepcopy(plan)

    try:
        prepared = None
        preparation_owner = None
        identity_hint = {}
        if execute or from_current:
            admission = _session_state(session, runner, allow_latched=not execute,
                                       identity_out=identity_hint if preparing else None)
            plan["executionAdmission" if execute else "observationAdmission"] = admission
        if preparing:
            if execute or from_current:
                identity_sample = identity_hint or _current_pose(session, admission, runner, allow_latched=not execute)
                preparation_owner = identity_sample["runtimeIdentity"]
                plan["prePreparationIdentity"] = {key: value for key, value in identity_sample.items()
                                                  if key != "nativeXYZ"}
                plan["prePreparationIdentity"].update(purpose="identity-only", usedForQuery=False)

            last_poll, last_cancel_reason = float("-inf"), None
            post_preparation_identity = {}

            def cancel_preparation(*, force=False):
                nonlocal last_poll, last_cancel_reason
                if execute or from_current:
                    if last_cancel_reason:
                        return last_cancel_reason
                    now = time.monotonic()
                    if not force and now - last_poll < .75:
                        return None
                    last_poll = now
                    try:
                        current = _session_state(session, runner, allow_latched=not execute,
                            identity_out=post_preparation_identity if force else None)
                        if current != admission:
                            last_cancel_reason = "session-or-stop-epoch-changed-during-preparation"
                    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
                        last_cancel_reason = "session-unavailable-during-preparation"
                return last_cancel_reason

            prepare_command = [str(python), "-m", "riftworld", "prepare-area", "--request", str(prepare_request),
                               "--source-index", str(source_index), "--build-nav", "--allow-partial-navigation",
                               "--receipt", str(preparation_receipt), "--handoff", str(handoff_path)]
            if prepare_profile is not None:
                prepare_command += ["--profile", str(prepare_profile)]
            if preparation_runner is None:
                from scripts.owned_process import run_owned
                preparation_runner = run_owned
            plan["preparationLogDirectory"] = str(output / "preparation-process")
            try:
                process = preparation_runner(prepare_command, cwd=world_root,
                    log_directory=output / "preparation-process", timeout_seconds=prepare_timeout_seconds,
                    cancel_check=cancel_preparation, max_output_bytes=1024 * 1024)
                plan["preparationProcess"] = {"exitCode": process.returncode,
                    "metadata": process.metadata, "confirmedCleanup": process.confirmed_cleanup}
            except subprocess.SubprocessError as error:
                process = getattr(error, "result", None)
                plan["preparationProcess"] = {"metadata": getattr(error, "metadata", None),
                    "exitCode": getattr(process, "returncode", None),
                    "confirmedCleanup": getattr(process, "confirmed_cleanup", False)}
                if preparation_receipt.is_file():
                    plan["preparationRun"] = _reference(preparation_receipt)
                raise ValueError("preparation-process-failed: " + str(error)) from error
            if preparation_receipt.is_file():
                plan["preparationRun"] = _reference(preparation_receipt)
            if process.returncode != 0 or process.confirmed_cleanup is not True:
                raise ValueError("preparation-failed-or-cleanup-unverified")
            prepared, patch, build = _prepared_handoff(handoff_path, request_path=prepare_request,
                index_path=source_index, inputs=inputs, profile_path=prepare_profile)
            inputs.update(patch=_reference(patch), build=_reference(build),
                          preparationHandoff=_reference(handoff_path))
            for name in ("preparation", "sourceCatalog"):
                inputs[name] = {"path": str(Path(prepared[name]["descriptor"]).resolve()),
                                "sha256": prepared[name]["descriptorSha256"].upper()}
            plan["preparedNavigation"] = prepared
            plan["stages"]["preparation"] = "prepared"
            for name, reference in inputs.items():
                if _hash(reference["path"]).casefold() != str(reference["sha256"]).casefold():
                    raise ValueError("planning-input-changed-during-preparation: " + name)
            cancelled = cancel_preparation(force=True)
            if cancelled:
                raise ValueError(cancelled)
            if (declared_binding.get("sourceIndexId") != prepared["sourceIndex"]["sourceIndexId"]
                    or declared_binding.get("areaRequestId") not in {None, prepared["areaRequest"]["areaRequestId"]}):
                raise ValueError("declared-destination-binding-does-not-match-prepared-inputs")
            if preparation_owner is not None and post_preparation_identity:
                plan["postPreparationIdentity"] = {**post_preparation_identity,
                    "purpose": "identity-only-status", "usedForQuery": False}
                if not _same_runtime(preparation_owner, post_preparation_identity["runtimeIdentity"]):
                    raise ValueError("current-native-player-changed-during-preparation")
                plan["preparationOwnerCheck"] = "matching-fresh-status"
            if not from_current and not _inside_bounds(start, prepared["requestedBounds"]):
                raise ValueError("requested-start-outside-prepared-area")
            destinations, _ = _read(catalog)
            entry = next((entry for entry in destinations.get("destinations", [])
                          if isinstance(entry, dict) and entry.get("id") == destination), None)
            if not entry or entry.get("approachXYZ") is None or not _inside_bounds(
                    _xyz(entry["approachXYZ"]), prepared["requestedBounds"]):
                raise ValueError("destination-approach-outside-prepared-area-or-unavailable")
        if from_current:
            patch_document, _ = _read(patch)
            transform = patch_document.get("coordinates", {}).get("transformToRr2Native")
            if (not isinstance(transform, dict) or transform.get("kind") != "identity"
                    or transform.get("qualification") not in {"landmark-reprojection-candidate", "verified"}):
                if preparing and "preparationOwnerCheck" not in plan:
                    plan["preparationOwnerCheck"] = "skipped-unqualified-transform"
                raise ValueError("current-native-start-requires-explicit-qualified-identity-transform")
            observation = _current_pose(session, admission, runner, allow_latched=not execute)
            observation["transformToRr2Native"] = deepcopy(transform)
            observation["patch"] = inputs["patch"]
            observation["qualification"] = "Native start used through this patch's explicit identity transform; " \
                                           "no global coordinate or live world/floor qualification."
            plan["startObservation"] = observation
            if preparation_owner is not None and not _same_runtime(preparation_owner, observation["runtimeIdentity"]):
                raise ValueError("current-native-player-changed-during-preparation")
            if preparation_owner is not None:
                plan["preparationOwnerCheck"] = "matching-fresh-post-preparation-pose"
            start = observation["nativeXYZ"]
            plan["requestedStartXYZ"] = start
            if prepared and not _inside_bounds(start, prepared["requestedBounds"]):
                raise ValueError("current-start-outside-prepared-area")
        elif preparing and execute:
            identity_sample = _current_pose(session, admission, runner, allow_latched=False)
            plan["postPreparationIdentity"] = {key: value for key, value in identity_sample.items() if key != "nativeXYZ"}
            if not _same_runtime(preparation_owner, identity_sample["runtimeIdentity"]):
                raise ValueError("current-native-player-changed-during-preparation")
            plan["preparationOwnerCheck"] = "matching-fresh-post-preparation-pose"
        command = [str(python), str(query_tool), "--catalog", str(catalog),
                   "--destination", destination, "--patch", str(patch), "--build", str(build),
                   "--from", ",".join(format(axis, ".17g") for axis in start),
                   "--out", str(candidate_path), "--receipt", str(receipt_path)]
        if search_extent is not None:
            command += ["--search-extent", format(search_extent, ".17g")]
        if prepared:
            command += ["--preparation", prepared["preparation"]["descriptor"]]
        plan["stages"]["query"] = "pending"
        query = runner(command, cwd=world_root, text=True, capture_output=True, check=False)
        plan["queryProcess"] = {"exitCode": query.returncode, "stdout": query.stdout,
                                "stderr": query.stderr}
        if not candidate_path.is_file() or not receipt_path.is_file():
            raise ValueError("destination-query-did-not-publish")
        def validate_destination(candidate, receipt, publication_refs):
            validation = _validated_destination(python, world_root, candidate_path, receipt_path,
                inputs, runner, candidate, receipt, prepared, publication_refs)
            plan["destinationValidation"] = validation
            return validation

        candidate, receipt, review = _publication(candidate_path, receipt_path,
            catalog_path=catalog, destination=destination, start=start, inputs=inputs,
            validator=validate_destination)
        plan.update(candidate=_reference(candidate_path), destinationReceipt=_reference(receipt_path),
                    destination=deepcopy(receipt["destination"]), review=review)
        plan["stages"]["query"] = candidate["status"]
        if from_current:
            after = _current_pose(session, admission, runner, allow_latched=not execute)
            plan["postPlanningObservation"] = after
            if not _same_runtime(observation["runtimeIdentity"], after["runtimeIdentity"]):
                raise ValueError("current-native-player-changed-during-planning")
            a, b = start, after["nativeXYZ"]
            if math.hypot(a[0] - b[0], a[2] - b[2]) > .30 or abs(a[1] - b[1]) > .50:
                raise ValueError("current-native-player-moved-during-planning")
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
        if from_current:
            current_owner = observation["runtimeIdentity"]
            owner = route["candidateAdoption"]["owner"]
            if any((current_owner[key] != owner[key] if key == "unitKey" else
                    str(current_owner[key]).casefold() != str(owner[key]).casefold())
                   for key in ("machine", "gameBuildSha256", "unitKey")):
                raise ValueError("current-native-player-does-not-own-adopted-evidence")
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
    except KeyboardInterrupt:
        plan["status"] = "execution-unverified" if plan["stages"]["execution"] == "running" else "cancelled"
        plan["blockers"].append("operator-cancelled; no further destination continuation")
        if preparing and plan["stages"]["preparation"] == "pending":
            plan["stages"]["preparation"] = "cancelled"
            if preparation_receipt.is_file():
                plan["preparationRun"] = _reference(preparation_receipt)
        return publish()
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        plan["status"] = "execution-unverified" if plan["stages"]["execution"] == "running" else "blocked"
        if plan["stages"]["query"] == "pending":
            plan["stages"]["query"] = "failed"
        elif plan["stages"]["adoption"] == "pending":
            plan["stages"]["adoption"] = "blocked"
        if preparing and plan["stages"]["preparation"] == "pending":
            plan["stages"]["preparation"] = "blocked"
        plan["blockers"].append(str(exc))
        return publish()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--catalog", type=Path, required=True)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--patch", type=Path, help="Existing exact patch; requires --build")
    mode.add_argument("--prepare-request", type=Path,
                      help="Area-request recipe; requires --source-index and a predeclared source-bound destination")
    result.add_argument("--build", type=Path)
    result.add_argument("--source-index", type=Path)
    result.add_argument("--allow-partial-navigation", action="store_true")
    result.add_argument("--prepare-profile", type=Path)
    result.add_argument("--prepare-timeout-seconds", type=float, default=600)
    result.add_argument("--destination", required=True)
    starts = result.add_mutually_exclusive_group(required=True)
    starts.add_argument("--from", dest="start", type=_xyz)
    starts.add_argument("--from-current", action="store_true",
                        help="read fresh bound native XYZ through the exact --session; no game input")
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
        return 130 if result["status"] in {"stopped", "cancelled"} else 2 if result["status"] in {
            "blocked", "halted", "execution-unverified"} else 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "blockers": [str(exc)],
                          "inputSent": None if args.execute else False,
                          "currentRouteChanged": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
