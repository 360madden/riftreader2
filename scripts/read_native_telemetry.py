"""Read Lab 2 native position, vitals, pose and optional scalar without game input.

Reuses the managed controller and bounded, identity-checked native queries.
Selected reads are sequential, NOT atomic or qualified movement feedback.
Each source keeps its own timestamp and hashed raw report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient
from scripts.control_host import HostConfig
from scripts.ensure_controller import CONFIGS
from scripts.ensure_guest_agent import ensure, _idle
from scripts.operation_dependencies import DependencyUnavailable
from scripts.managed_controller_receipt import resolve_current_managed_controller
from scripts.vm_console_native import Blocked, validate_config
from scripts.sample_current_native_vitals import checked_expected_game
from scripts.fresh_native_xyz import query as query_xyz
from scripts.fresh_native_vitals import query as query_vitals
from scripts.fresh_native_actor_pose import query as query_actor_pose
from scripts.compare_native_actor_pose_turn import compare as compare_pose_turn
from scripts.compare_native_player_reads import compare as compare_readouts, load as load_readout
from scripts.fresh_native_smoothed_scalar import query as query_smoothed_scalar

OWNER_HOST = "AMD-DESKTOP"
NATIVE_FIELDS = ("position", "vitals", "actor-pose", "smoothed-scalar")
DEFAULT_FIELDS = ("position", "vitals")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def target_identity(status):
    require(isinstance(status, dict) and _idle(status), "native-read-controller-not-idle")
    host, guest = status["host"], status["guest"]
    require(host.get("machineName") == "RIFT-LAB-2", "native-read-guest-mismatch")
    instance = guest.get("instanceId")
    require(isinstance(instance, str) and re.fullmatch(r"[0-9a-f]{32}", instance)
            and host.get("instanceId") == instance, "native-read-agent-mismatch")
    target = guest.get("target")
    require(isinstance(target, dict) and target.get("machineName") == "RIFT-LAB-2",
            "native-read-target-unavailable")
    game = checked_expected_game("lab2", {key: target.get(key) for key in
        ("processId", "processStartUtcTicks", "executableSha256")})
    return game, instance


def unit_key(value):
    require(type(value) in (int, str), "native-read-unit-key-invalid")
    text = str(value)
    require(re.fullmatch(r"[1-9][0-9]{0,19}", text) and int(text) <= 2**64 - 1,
            "native-read-unit-key-invalid")
    return text


def validate_sources(rows, game, instance, vm):
    """Check every requested source; never merge across owners or epochs."""
    keys = []
    for row in rows:
        require(isinstance(row, dict) and row.get("schemaVersion") == 1
                and row.get("status") == "candidate-only" and row.get("lab") == "lab2"
                and row.get("transport") == "persistent-control-agent"
                and row.get("vmIdentity") == vm
                and row.get("activeAgentInstanceId") == instance
                and type(row.get("gameProcessId")) is int
                and row["gameProcessId"] == game["processId"]
                and type(row.get("gameProcessStartUtcTicks")) is int
                and row["gameProcessStartUtcTicks"] == game["processStartUtcTicks"]
                and row.get("gameSha256", "").upper() == game["executableSha256"].upper(),
                "native-read-source-identity-mismatch")
        keys.append(unit_key(row["metrics"]["unitKey"]))
    require(bool(keys) and len(set(keys)) == 1, "native-read-unit-changed")
    return keys[0]


def validate_pair(position, vitals, game, instance, vm):
    return validate_sources((position, vitals), game, instance, vm)


def selected_fields(fields):
    require(isinstance(fields, (tuple, list)) and 1 <= len(fields) <= len(NATIVE_FIELDS)
            and all(isinstance(field, str) and field in NATIVE_FIELDS for field in fields),
            "native-read-fields-invalid")
    require(len(set(fields)) == len(fields), "native-read-fields-duplicated")
    # Stable order, independent of CLI argument order. No automatic source fallback.
    return tuple(field for field in NATIVE_FIELDS if field in fields)


def read_once(lab: str, expected_host: str, *, fields=DEFAULT_FIELDS) -> dict:
    # Reject a wrong machine/target before starting any dependency.
    require(lab == "lab2", "native-read-target-not-supported")
    require(isinstance(expected_host, str) and expected_host.casefold() == OWNER_HOST.casefold()
            and socket.gethostname().casefold() == OWNER_HOST.casefold(), "native-read-host-mismatch")
    fields = selected_fields(fields)
    started = time.perf_counter()
    ensure(lab)
    receipt_path, receipt, _ = resolve_current_managed_controller(lab)
    config = HostConfig.load(CONFIGS[lab])
    require(config.expected_machine_name == "RIFT-LAB-2", "native-read-config-lab-mismatch")
    client = ControlClient(config)
    before = client.request("/api/status", method="GET")
    game, instance = target_identity(before)
    vm = receipt["vmIdentity"]
    require(before["host"].get("vmIdentity") == vm, "native-read-vm-mismatch")
    native = validate_config(config.vmx, config.vnc_port, config.vmrun,
                             config.output_directory, require_files=True)
    sources = {}
    if "position" in fields:
        sources["position"] = query_xyz(native, vm, game, CONFIGS[lab], lab=lab)
        validate_sources((sources["position"],), game, instance, vm)
    if "vitals" in fields:
        sources["vitals"] = query_vitals(native, vm, game, CONFIGS[lab])
    if "actor-pose" in fields:
        sources["actor-pose"] = query_actor_pose(native, vm, game, CONFIGS[lab], lab=lab)
    if "smoothed-scalar" in fields:
        sources["smoothed-scalar"] = query_smoothed_scalar(native, vm, game, CONFIGS[lab], lab=lab)
    key = validate_sources(sources.values(), game, instance, vm)
    after = client.request("/api/status", method="GET")
    require(target_identity(after) == (game, instance)
            and after["host"].get("vmIdentity") == vm, "native-read-postflight-changed")
    resolve_current_managed_controller(lab, expected_receipt_path=receipt_path)
    # Keep large unit keys lossless for JavaScript and other JSON consumers.
    sources = {field: dict(row, metrics=dict(row["metrics"], unitKey=key))
               for field, row in sources.items()}
    for field, label in (("actor-pose", "pose"), ("smoothed-scalar", "scalar")):
        if field in sources:
            source = Path(sources[field]["sourceReport"])
            require(source.is_absolute() and source.name == "samples.json",
                    f"native-read-{label}-source-invalid")
            sources[field]["summaryPath"] = str(source.with_name("summary.json"))
    return {"schemaVersion": 1, "status": "candidate-only", "targetId": lab,
            "ownerHost": OWNER_HOST, "mode": "native-read-only", "atomic": False,
            "luaReaderUsed": False, "screenshotUsed": False,
            "unitKey": key, **sources,
            "elapsedSeconds": round(time.perf_counter() - started, 6),
            "qualification": "acquisition-checked; field semantics, passive freshness and restart recovery unqualified"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", required=True, choices=("lab2",))
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--fields", nargs="+", choices=NATIVE_FIELDS, default=DEFAULT_FIELDS,
                        help="read only these sources; defaults to position and vitals")
    parser.add_argument("--compare-pose-before", type=Path,
                        help="compare the new actor-pose capture to a saved before summary.json")
    parser.add_argument("--output-json", type=Path,
                        help="save the complete native readout as new JSON (never overwrite)")
    parser.add_argument("--compare-readout-before", type=Path,
                        help="compare a new saved readout with a previously saved baseline")
    args = parser.parse_args(argv)
    try:
        if args.output_json is not None:
            require(args.output_json.parent.is_dir() and not args.output_json.exists()
                    and not args.output_json.is_symlink(), "native-read-output-unavailable")
        baseline = None
        if args.compare_readout_before is not None:
            require(args.output_json is not None, "native-read-comparison-output-required")
            baseline, baseline_sha = load_readout(args.compare_readout_before)
            require(tuple(field for field in NATIVE_FIELDS if field in baseline)
                    == selected_fields(args.fields), "native-read-baseline-fields-mismatch")
        if args.compare_pose_before is not None:
            require("actor-pose" in selected_fields(args.fields),
                    "native-read-pose-compare-requires-pose")
        result = read_once(args.lab, args.expected_host, fields=args.fields)
        if args.compare_pose_before is not None:
            pose = result.get("actor-pose")
            require(isinstance(pose, dict) and isinstance(pose.get("summaryPath"), str),
                    "native-read-pose-summary-missing")
            result["poseTurnComparison"] = compare_pose_turn(
                args.compare_pose_before, Path(pose["summaryPath"]))
        serialized = json.dumps(result, allow_nan=False, separators=(",", ":"))
        displayed = result
        if baseline is not None:
            after_sha = hashlib.sha256((serialized + "\n").encode("utf-8")).hexdigest().upper()
            displayed = dict(result, readoutComparison=compare_readouts(
                baseline, result, baseline_sha, after_sha))
        if args.output_json is not None:
            try:
                with args.output_json.open("x", encoding="utf-8", newline="\n") as saved:
                    saved.write(serialized + "\n")
            except OSError:
                raise ValueError("native-read-output-unavailable") from None
        print(json.dumps(displayed, allow_nan=False, separators=(",", ":"))
              if baseline is not None else serialized)
        return 0
    except Exception as error:
        # Never print transport configuration, credentials or arbitrary tracebacks.
        if isinstance(error, DependencyUnavailable):
            reason = error.code
        else:
            reason = str(error) if isinstance(error, (Blocked, ValueError)) else "native-read-unavailable"
        if not isinstance(reason, str) or re.fullmatch(r"[a-z0-9-]{1,100}", reason) is None:
            reason = "native-read-unavailable"
        print(json.dumps({"status": "blocked", "targetId": args.lab, "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
