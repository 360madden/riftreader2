"""Build an identity source pin from a verified live-reader launch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for search_path in (ROOT, ROOT / "scripts"):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from scripts import addon_command_console as console
from scripts import movement_feedback as movement
from scripts.live_reader_config import MAX_SCAN_BYTES, MIN_SCAN_BYTES


REQUIRED_SUMMARY = {
    "status", "lab", "runId", "readerPid", "readerStartUtcTicks",
    "readerSha256", "nonce", "expiresAtUtc", "guestDirectory",
    "guestOutput", "gamePid", "gameStartUtcTicks", "gameSha256",
    "receiver", "vmIdentityStable", "inputSent", "controlAgentStopped",
    "cleanup", "atUtc",
}
OPTIONAL_SUMMARY = {"maxScanBytes", "maxScanSeconds"}
RECEIVER_FIELDS = {
    "pid", "processStartUtcTicks", "image", "address", "port", "configSha256",
}


def fail(message: str) -> None:
    raise ValueError(message)


def read_json(path: Path) -> tuple[dict, bytes]:
    resolved = path.resolve(strict=True)
    data = resolved.read_bytes()
    return console._strict_json_bytes(data, "invalid-json"), data


def validate_reader_summary(summary: dict) -> None:
    fields = set(summary)
    if not REQUIRED_SUMMARY.issubset(fields) or fields - REQUIRED_SUMMARY - OPTIONAL_SUMMARY:
        fail("reader summary has unexpected fields")
    if summary["status"] != "reader-running-postflight-verified" \
            or summary["lab"] not in ("lab1", "lab2") \
            or summary["vmIdentityStable"] is not True \
            or summary["inputSent"] is not False \
            or summary["controlAgentStopped"] is not False:
        fail("reader summary is not a verified no-input running-reader result")
    if not isinstance(summary["receiver"], dict) or set(summary["receiver"]) != RECEIVER_FIELDS:
        fail("receiver summary has unexpected fields")
    if "maxScanBytes" in summary:
        value = summary["maxScanBytes"]
        if isinstance(value, bool) or not isinstance(value, int) \
                or not MIN_SCAN_BYTES <= value <= MAX_SCAN_BYTES:
            fail("reader summary maxScanBytes is invalid")
    if "maxScanSeconds" in summary:
        value = summary["maxScanSeconds"]
        if isinstance(value, bool) or not isinstance(value, int) \
                or not 1 <= value <= 60:
            fail("reader summary maxScanSeconds is invalid")


def build_pin(summary: dict, vm_identity: dict, receipt_path: Path, receipt: dict) -> dict:
    validate_reader_summary(summary)
    observation = receipt.get("observation")
    target = observation.get("target") if isinstance(observation, dict) else None
    if not isinstance(target, dict):
        fail("receipt target is unavailable")

    game_pid = int(summary["gamePid"])
    game_start = int(summary["gameStartUtcTicks"])
    game_sha = str(summary["gameSha256"]).lower()
    if target.get("processId") != game_pid \
            or target.get("processStartUtcTicks") != game_start \
            or str(target.get("executableSha256", "")).lower() != game_sha:
        fail("reader summary and receipt game identities disagree")
    if observation.get("nonce") != summary["nonce"] \
            or target.get("readerSessionNonce") != summary["nonce"]:
        fail("reader summary and receipt nonces disagree")

    receiver = summary["receiver"]
    receiver_image = Path(receiver["image"]).resolve(strict=True)
    receipt_path = receipt_path.resolve(strict=True)
    receipt_bytes = receipt_path.read_bytes()
    return {
        "schemaVersion": 1,
        "lab": summary["lab"],
        "vmIdentity": vm_identity,
        "gameIdentity": {
            "processId": game_pid,
            "processStartUtcTicks": game_start,
            "executablePath": target["executablePath"],
            "executableSha256": game_sha,
        },
        "reader": {
            "processId": int(summary["readerPid"]),
            "processStartUtcTicks": int(summary["readerStartUtcTicks"]),
            "executableSha256": str(summary["readerSha256"]).lower(),
            "instanceId": observation["instanceId"],
            "nonce": summary["nonce"],
            "sourceAddress": receipt["sourceAddress"],
        },
        "receiver": {
            "instanceId": receipt["receiverInstance"],
            "processId": int(receiver["pid"]),
            "processStartUtcTicks": int(receiver["processStartUtcTicks"]),
            "executablePath": str(receiver_image),
            "executableSha256": console._sha(receiver_image),
            "endpoint": f'{receiver["address"]}:{int(receiver["port"])}',
        },
        "receiptPath": str(receipt_path),
        "receiptSha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }


def _bootstrap_source(gate: dict) -> dict:
    block = gate.get("sourceBlock")
    if block == "riftReader2":
        return {
            "sourceBlock": block,
            "scope": "whole-readable-private",
            "provenance": "nonce-bound-complete-process-scan/1",
        }
    if block == "fastObservation" \
            and gate.get("scope") == "candidate-regions" \
            and gate.get("provenance") \
            == "recent-full-scan-anchored-candidate-regions/1":
        return {
            "sourceBlock": block,
            "scope": gate["scope"],
            "provenance": gate["provenance"],
        }
    fail("validated receipt source is unavailable")


def publish(path: Path, value: dict) -> dict:
    destination = path.resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        fail("output already exists")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                prefix=f".{destination.name}.", suffix=".tmp",
                dir=destination.parent, delete=False) as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            temporary = Path(stream.name)
        loaded, _ = console.load_source_pin(temporary)
        _, _, gate = movement._movement_receipt(loaded, initial=True)
        bootstrap_source = _bootstrap_source(gate)
        os.replace(temporary, destination)
        temporary = None
        return bootstrap_source
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader-summary", type=Path, required=True)
    parser.add_argument("--vm-identity", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary, _ = read_json(args.reader_summary)
        vm_identity, _ = read_json(args.vm_identity)
        receipt, _ = read_json(args.receipt)
        pin = build_pin(summary, vm_identity, args.receipt, receipt)
        bootstrap_source = publish(args.output, pin)
        print(json.dumps({"status": "created", "output": str(args.output.resolve()),
                          "bootstrapSource": bootstrap_source}))
        return 0
    except (OSError, ValueError, console.Blocked, movement._console.Blocked) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
