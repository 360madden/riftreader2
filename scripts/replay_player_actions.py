"""Headless offline replay of RR2's movement/combat/recovery action ownership.

No game process, desktop, input controller or live action adapter is accessed.
Receipts supplied in the plan are *simulated* and cannot establish real release.
Example:
  python scripts/replay_player_actions.py --events artifacts/action-plan.json
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.player_action_coordinator import ActionCoordinationError, PlayerActionCoordinator

STARTS = {
    "new-run": ("new_run", "movement"),
    "resume": ("resume", "movement"),
    "encounter": ("encounter", "combat"),
    "combat-ready": ("combat_ready", "movement"),
    "combat-needs-recovery": ("combat_needs_recovery", "recovery"),
    "recovery-ready": ("recovery_ready", "movement"),
}


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-json-key:" + key)
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError("nonfinite-json-number:" + value)


def _receipt(value):
    if (not isinstance(value, dict)
            or set(value) - {"releaseSucceeded", "allInputsReleased", "desktopInputsDown"}
            or "desktopInputsDown" not in value
            or (not isinstance(value["desktopInputsDown"], list))
            or any(not isinstance(v, str) or not v or len(v) > 32
                   for v in value["desktopInputsDown"])
            or len(value["desktopInputsDown"]) > 32
            or not ({"releaseSucceeded", "allInputsReleased"} & set(value))
            or any(type(value[k]) is not bool
                   for k in ("releaseSucceeded", "allInputsReleased") if k in value)):
        raise ValueError("invalid-simulated-release-receipt")
    return deepcopy(value)


def replay(plan):
    if (not isinstance(plan, dict) or set(plan) != {"schemaVersion", "events"}
            or type(plan["schemaVersion"]) is not int or plan["schemaVersion"] != 1
            or not isinstance(plan["events"], list) or not 1 <= len(plan["events"]) <= 64):
        raise ValueError("invalid-action-plan")
    coordinator = PlayerActionCoordinator()
    trace = []
    states = []
    for index, event in enumerate(plan["events"]):
        try:
            if (not isinstance(event, dict) or "action" not in event
                    or type(event["action"]) is not str):
                raise ValueError("invalid-action-event")
            action = event["action"]
            allowed = ({"action", "release"} if action in STARTS or action == "retry-release"
                       else {"action", "reason"} if action == "critical"
                       else {"action"} if action in ("operator-stop", "status")
                       else set())
            if not allowed or set(event) != allowed:
                raise ValueError("invalid-event-fields")
            if action in STARTS:
                method, owner = STARTS[action]
                simulated = _receipt(event["release"])

                def start(owner=owner):
                    trace.append({"callback": "start", "owner": owner})

                def release(reason, owner=owner, simulated=simulated):
                    trace.append({"callback": "release", "owner": owner, "reason": reason})
                    return deepcopy(simulated)

                state = getattr(coordinator, method)(start, release)
            elif action == "retry-release":
                simulated = _receipt(event["release"])
                state = coordinator.retry_release(lambda reason, simulated=simulated:
                    deepcopy(simulated))
            elif action == "operator-stop":
                state = coordinator.operator_stop()
            elif action == "critical":
                state = coordinator.critical(event["reason"])
            else:
                state = coordinator.snapshot()
            states.append({"step": index + 1, "event": action, "state": state})
        except (ActionCoordinationError, ValueError, TypeError) as exc:
            return {"schemaVersion": 1, "mode": "offline-scripted-receipts-only",
                    "status": "blocked", "failedStep": index + 1, "event": event.get("action")
                    if isinstance(event, dict) else None, "reason": str(exc),
                    "final": coordinator.snapshot(), "states": states, "callbackTrace": trace,
                    "gameInputSent": False}
    return {"schemaVersion": 1, "mode": "offline-scripted-receipts-only",
            "status": "complete", "final": coordinator.snapshot(), "states": states,
            "callbackTrace": trace, "gameInputSent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True,
                        help="JSON file containing schemaVersion=1 and 1–64 scripted events")
    args = parser.parse_args(argv)
    try:
        if args.events.stat().st_size > 65536:
            raise ValueError("action-plan-too-large")
        plan = json.loads(args.events.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        result = replay(plan)
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        result = {"schemaVersion": 1, "mode": "offline-scripted-receipts-only",
                  "status": "blocked", "reason": str(exc), "gameInputSent": False}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
