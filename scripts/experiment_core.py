#!/usr/bin/env python3
"""Small fail-closed runner for one guarded RIFT input experiment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re


PLAN_FIELDS = {
    "schemaVersion",
    "experimentId",
    "key",
    "holdMilliseconds",
    "expectedVmIdentity",
    "expectedGameBinding",
    "reviewedCaptureId",
    "configSha256",
}
EXPERIMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9A-Fa-f]{64}$")


class ExperimentError(ValueError):
    pass


def _canonical(value) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ExperimentError("experiment data must be finite JSON") from error


def _validate_plan(plan: dict) -> None:
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise ExperimentError("plan must contain exactly the version 1 fields")
    if type(plan["schemaVersion"]) is not int or plan["schemaVersion"] != 1:
        raise ExperimentError("unsupported plan schema")
    if not isinstance(plan["experimentId"], str) or not EXPERIMENT_ID.fullmatch(
        plan["experimentId"]
    ):
        raise ExperimentError("experimentId is not a safe identifier")
    if plan["key"] not in ("w", "a", "s", "d"):
        raise ExperimentError("key must be one of w, a, s, or d")
    hold = plan["holdMilliseconds"]
    if type(hold) is not int or not 20 <= hold <= 250:
        raise ExperimentError("holdMilliseconds must be an integer from 20 through 250")
    for name in ("expectedVmIdentity", "expectedGameBinding"):
        if not isinstance(plan[name], dict) or not plan[name]:
            raise ExperimentError(f"{name} must be a non-empty object")
    capture_id = plan["reviewedCaptureId"]
    if not isinstance(capture_id, str) or not capture_id or len(capture_id) > 128:
        raise ExperimentError("reviewedCaptureId must be a non-empty bounded string")
    if not isinstance(plan["configSha256"], str) or not SHA256.fullmatch(
        plan["configSha256"]
    ):
        raise ExperimentError("configSha256 must be 64 hexadecimal characters")
    _canonical(plan)


def _record_identity(result: dict, adapter, plan: dict, stage: str) -> bool:
    vm_identity, game_binding = adapter.identity()
    check = {
        "stage": stage,
        "vmIdentity": vm_identity,
        "gameBinding": game_binding,
        "matchesExpected": vm_identity == plan["expectedVmIdentity"]
        and game_binding == plan["expectedGameBinding"],
    }
    _canonical(check)
    result["identityChecks"].append(check)
    return check["matchesExpected"]


def _recover(adapter) -> dict:
    recovery = {"stopRequested": True, "stop": None, "recover": None}
    try:
        recovery["stop"] = adapter.stop()
    except Exception as error:  # Recovery failures belong in the durable result.
        recovery["stop"] = {"status": "failed", "error": str(error)}
    try:
        recovery["recover"] = adapter.recover()
    except Exception as error:
        recovery["recover"] = {"status": "failed", "error": str(error)}
    return recovery


def _write_result(output: Path, result: dict) -> None:
    data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = output / "result.json.tmp"
    temporary.write_text(data, encoding="utf-8", newline="\n")
    os.replace(temporary, output / "result.json")


def run_experiment(plan: dict, adapter, output: Path, stop_requested=lambda: False) -> dict:
    """Run one pulse without retries and save its finite result in a new directory."""

    _validate_plan(plan)
    output = Path(output)
    try:
        output.mkdir(parents=False, exist_ok=False)
    except FileExistsError as error:
        raise ExperimentError("experiment output already exists; plans are single-use") from error

    result = {
        "schemaVersion": 1,
        "evidenceKind": "guarded-input-experiment/1",
        "experimentId": plan["experimentId"],
        "planSha256": hashlib.sha256(_canonical(plan)).hexdigest().upper(),
        "plan": plan,
        "status": "failed",
        "identityChecks": [],
        "before": None,
        "pulse": None,
        "after": None,
        "recovery": None,
        "error": None,
        "uncertainties": [
            "Completion only means the reviewed stimulus was delivered and sampled.",
            "This result does not verify a game response or any native field meaning.",
        ],
    }
    input_may_have_happened = False
    cancellation_seen = False

    def monitored_stop() -> bool:
        nonlocal cancellation_seen
        cancellation_seen = cancellation_seen or bool(stop_requested())
        return cancellation_seen

    try:
        if not _record_identity(result, adapter, plan, "before-capture"):
            result["status"] = "refused"
            result["uncertainties"].append("VM or game identity differed before capture.")
        elif monitored_stop():
            result["status"] = "cancelled"
        else:
            result["before"] = adapter.capture_before()
            _canonical(result["before"])
            if not _record_identity(result, adapter, plan, "before-pulse"):
                result["status"] = "refused"
                result["uncertainties"].append("VM or game identity changed before input.")
            elif monitored_stop():
                result["status"] = "cancelled"
            else:
                # An exception from pulse cannot prove whether input was delivered.
                input_may_have_happened = True
                result["pulse"] = adapter.pulse(
                    plan["key"],
                    plan["holdMilliseconds"],
                    plan["reviewedCaptureId"],
                    monitored_stop,
                )
                _canonical(result["pulse"])
                if not isinstance(result["pulse"], dict):
                    raise ExperimentError("pulse result must be an object")
                sent = result["pulse"].get("inputSent")
                released = result["pulse"].get("releaseSent")
                if type(sent) is not bool or type(released) is not bool:
                    raise ExperimentError("pulse must report boolean inputSent and releaseSent")
                may_have_been_sent = result["pulse"].get("inputMayHaveBeenSent", False)
                if type(may_have_been_sent) is not bool:
                    raise ExperimentError("inputMayHaveBeenSent must be boolean when present")
                input_may_have_happened = (
                    input_may_have_happened or sent or may_have_been_sent
                )
                if monitored_stop():
                    result["status"] = "cancelled"
                    result["uncertainties"].append("Cancellation was observed during the pulse.")
                elif not sent:
                    result["uncertainties"].append("The adapter reported that input was not sent.")
                elif not released:
                    result["uncertainties"].append("Input release was not confirmed.")
                else:
                    result["after"] = adapter.capture_after()
                    _canonical(result["after"])
                    if not _record_identity(result, adapter, plan, "after-capture"):
                        result["uncertainties"].append("VM or game identity changed after input.")
                    elif monitored_stop():
                        result["status"] = "cancelled"
                        result["uncertainties"].append(
                            "Cancellation was observed during after-capture checks."
                        )
                    else:
                        result["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        result["uncertainties"].append(
            "The experiment was interrupted."
            if isinstance(error, KeyboardInterrupt)
            else "The experiment ended with an exception."
        )

    if result["status"] != "completed" and input_may_have_happened:
        result["recovery"] = _recover(adapter)
    _write_result(output, result)
    return result
