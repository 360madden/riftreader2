"""Reviewed, single-command RIFT addon console helper.

This is deliberately narrower than the general VM console helper.  It can only
type one validated RiftReader2 guidance command into an already reviewed RIFT
console.  Preparation captures the console without input; execution requires a
fresh, exact review receipt and revalidates both VM and game epochs.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import importlib.util
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
import uuid

from vm_console_native import (
    Blocked, Config, ControlMutex, _atomic_json, _capture, _type_text,
    collect_identity, connect, parse_tcp_listener_rows, path_key, process_identity,
    text_keypress, utc_now, validate_config, verify_identity,
)
from vmware_guest_session import GuestSession, SessionError


MAX_COMMAND_LENGTH = 512
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_REVIEW_AGE_SECONDS = 60
MAX_FAST_RESULT_AGE_SECONDS = 8.0
MAX_SOURCE_PIN_BYTES = 32 * 1024
MAX_INTENT_BYTES = 64 * 1024
CALCULATOR_FILES = frozenset({
    "RiftReader2.Cli.dll", "RiftReader2.Application.dll", "RiftReader2.Domain.dll",
    "RiftReader2.Infrastructure.dll", "RiftReader2.Cli.runtimeconfig.json",
    "RiftReader2.Cli.deps.json",
})
SHA256 = re.compile(r"[0-9a-f]{64}")
NONCE = re.compile(r"[0-9a-f]{32}")
PLAYER = re.compile(r"[A-Za-z0-9_]{1,128}")
NUMBER = re.compile(r"[0-9eE+.-]{1,32}")
SIMPLE = frozenset({"/reloadui", "/rr2guide status", "/rr2guide clear"})

_GATE_SPEC = importlib.util.spec_from_file_location(
    "rr2_read_live_receipt", Path(__file__).with_name("read-live-receipt.py"))
_live_gate = importlib.util.module_from_spec(_GATE_SPEC)
_GATE_SPEC.loader.exec_module(_live_gate)


def _fail(reason: str):
    raise Blocked(reason)


def _uint(value: str, *, positive: bool = False) -> int:
    if not value.isascii() or not value.isdecimal() or len(value) > 16:
        _fail("invalid-addon-result-integer")
    number = int(value)
    if number > MAX_SAFE_INTEGER or (positive and number < 1):
        _fail("invalid-addon-result-integer")
    return number


def _number(value: str, minimum: float, maximum: float) -> float:
    if NUMBER.fullmatch(value) is None:
        _fail("invalid-addon-result-number")
    try:
        number = float(value)
    except ValueError:
        _fail("invalid-addon-result-number")
    if not math.isfinite(number) or not minimum <= number <= maximum:
        _fail("invalid-addon-result-number")
    return number


def validate_addon_command(command: str, expected_lab: str | None = None) -> str:
    """Return one exact, printable, allowlisted addon command."""
    if (not isinstance(command, str) or not 1 <= len(command) <= MAX_COMMAND_LENGTH
            or not command.isascii() or any(ord(char) < 32 or ord(char) > 126 for char in command)):
        _fail("invalid-addon-command-text")
    if command in SIMPLE:
        return command
    bind = re.fullmatch(r"/rr2guide bind (lab1|lab2) ([0-9a-f]{32})", command)
    if bind:
        if expected_lab is not None and bind.group(1) != expected_lab:
            _fail("addon-command-lab-mismatch")
        return command
    parts = command.split(" ")
    if len(parts) != 16 or parts[:2] != ["/rr2guide", "result"]:
        _fail("unsupported-addon-command")
    lab, nonce, result_seq, epoch, source_seq, source_clock, player = parts[2:9]
    if lab not in ("lab1", "lab2") or NONCE.fullmatch(nonce) is None or PLAYER.fullmatch(player) is None:
        _fail("invalid-addon-result-identity")
    if expected_lab is not None and lab != expected_lab:
        _fail("addon-command-lab-mismatch")
    _uint(result_seq, positive=True)
    _uint(epoch, positive=True)
    _uint(source_seq, positive=True)
    _number(source_clock, 0, MAX_SAFE_INTEGER)
    x, y, z = (_number(value, -10_000_000, 10_000_000) for value in parts[9:12])
    distance = _number(parts[12], 0, 30_000_000)
    dx, dz, dy = (_number(value, -20_000_000, 20_000_000) for value in parts[13:16])
    del x, y, z, dy
    if abs(math.hypot(dx, dz) - distance) > max(0.01, distance * 1e-9):
        _fail("inconsistent-addon-result-distance")
    return command


def validate_expected_game(lab: str, pid: int, start_ticks: int, sha256: str) -> dict:
    if lab not in ("lab1", "lab2"):
        _fail("invalid-lab")
    if type(pid) is not int or pid < 1:
        _fail("invalid-game-pid")
    if type(start_ticks) is not int or start_ticks < 1:
        _fail("invalid-game-start-ticks")
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9A-Fa-f]{64}", sha256) is None:
        _fail("invalid-game-sha256")
    return {"lab": lab, "processId": pid, "processStartUtcTicks": start_ticks,
            "executableSha256": sha256.lower()}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def query_game_identity(config: Config, expected_vm: dict) -> dict:
    """Read the exact native process StartTime ticks and executable hash in guest."""
    token = uuid.uuid4().hex
    guest_path = rf"C:\Users\Public\Documents\rr2-game-{token}.json"
    host_path = config.output / f".game-{token}.json"
    quoted = guest_path.replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        "$p=@(Get-Process -Name rift_x64 -ErrorAction Stop);"
        "if($p.Count -ne 1){throw 'exactly-one-game-required'};"
        "$path=$p[0].MainModule.FileName;"
        "$o=[ordered]@{processId=[int]$p[0].Id;"
        "processStartUtcTicks=[long]$p[0].StartTime.ToUniversalTime().Ticks;"
        "executableSha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()};"
        f"$o|ConvertTo-Json -Compress|Set-Content -LiteralPath '{quoted}' -Encoding ASCII"
    )
    cleanup = f"Remove-Item -LiteralPath '{quoted}' -Force -ErrorAction SilentlyContinue"
    try:
        with GuestSession(config.vmrun, config.vmx,
                          lambda: verify_identity(config, expected_vm)) as session:
            session.powershell(script)
            session.copy_from_guest(guest_path, host_path)
            session.powershell(cleanup)
        payload = json.loads(host_path.read_text(encoding="ascii"))
        if set(payload) != {"processId", "processStartUtcTicks", "executableSha256"}:
            _fail("invalid-game-identity")
        if (type(payload["processId"]) is not int or payload["processId"] < 1
                or type(payload["processStartUtcTicks"]) is not int
                or payload["processStartUtcTicks"] < 1
                or not isinstance(payload["executableSha256"], str)
                or SHA256.fullmatch(payload["executableSha256"]) is None):
            _fail("invalid-game-identity")
        return payload
    except (SessionError, OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        _fail("game-identity-unavailable")
    finally:
        host_path.unlink(missing_ok=True)


def _require_game(actual: dict, expected: dict) -> None:
    comparable = {key: expected[key] for key in
                  ("processId", "processStartUtcTicks", "executableSha256")}
    if actual != comparable:
        _fail("game-identity-drift")


def validate_operation(command: str | None, ui_step: str | None, lab: str,
                       hide_frame: str | None = None, hide_x: int | None = None,
                       hide_y: int | None = None) -> dict:
    if (command is None) == (ui_step is None):
        _fail("exactly-one-operation-required")
    if command is not None:
        if hide_frame is not None or hide_x is not None or hide_y is not None:
            _fail("hide-target-requires-hide-addon")
        return {"type": "command", "command": validate_addon_command(command, lab)}
    if ui_step not in ("open-chat", "close-ui", "hide-addon"):
        _fail("unsupported-ui-step")
    if ui_step == "hide-addon":
        if hide_frame not in ("readiness", "casting") or type(hide_x) is not int \
                or type(hide_y) is not int or not 0 <= hide_x < 16384 or not 0 <= hide_y < 16384:
            _fail("invalid-hide-addon-target")
        return {"type": "ui-step", "step": ui_step, "frame": hide_frame,
                "x": hide_x, "y": hide_y}
    if hide_frame is not None or hide_x is not None or hide_y is not None:
        _fail("hide-target-requires-hide-addon")
    return {"type": "ui-step", "step": ui_step}


def _read_regular(path: Path, maximum: int, reason: str) -> bytes:
    try:
        info = path.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if not stat.S_ISREG(info.st_mode) or path.is_symlink() or reparse or not 0 < info.st_size <= maximum:
            _fail(reason)
        data = path.read_bytes()
    except OSError:
        _fail(reason)
    if len(data) != info.st_size:
        _fail(reason)
    return data


def _strict_json_bytes(data: bytes, reason: str) -> dict:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_live_gate._unique_object,
                           parse_constant=_live_gate._reject_constant)
    except (UnicodeError, json.JSONDecodeError, _live_gate.GateError):
        _fail(reason)
    if not isinstance(value, dict):
        _fail(reason)
    return value


def load_source_pin(path: Path) -> tuple[dict, str]:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        _fail("source-pin-unavailable")
    data = _read_regular(resolved, MAX_SOURCE_PIN_BYTES, "source-pin-unavailable")
    pin = _strict_json_bytes(data, "invalid-source-pin")
    required = {"schemaVersion", "lab", "vmIdentity", "gameIdentity", "reader",
                "receiver", "receiptPath", "receiptSha256"}
    if set(pin) != required or pin["schemaVersion"] != 1 or pin["lab"] not in ("lab1", "lab2"):
        _fail("invalid-source-pin")
    if not isinstance(pin["receiptPath"], str) or not Path(pin["receiptPath"]).is_absolute():
        _fail("invalid-source-pin")
    if not isinstance(pin["receiptSha256"], str) or SHA256.fullmatch(pin["receiptSha256"].lower()) is None:
        _fail("invalid-source-pin")
    return pin, hashlib.sha256(data).hexdigest()


def load_deferred_intent(path: Path) -> tuple[dict, str]:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        _fail("deferred-intent-unavailable")
    data = _read_regular(resolved, MAX_INTENT_BYTES, "deferred-intent-unavailable")
    intent = _strict_json_bytes(data, "invalid-deferred-intent")
    if set(intent) != {"schemaVersion", "lab", "nonce", "resultSequence", "destination",
                       "seed", "calculator"} or intent["schemaVersion"] != 1:
        _fail("invalid-deferred-intent")
    if intent["lab"] not in ("lab1", "lab2") or NONCE.fullmatch(intent.get("nonce", "")) is None:
        _fail("invalid-deferred-intent")
    _uint(str(intent["resultSequence"]), positive=True)
    destination, seed, calculator = intent["destination"], intent["seed"], intent["calculator"]
    if not isinstance(destination, dict) or set(destination) != {"x", "y", "z"}:
        _fail("invalid-deferred-intent")
    for value in destination.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or abs(value) > 10_000_000:
            _fail("invalid-deferred-intent")
    if not isinstance(seed, dict) or set(seed) != {"player", "epoch", "x", "y", "z"} \
            or PLAYER.fullmatch(seed.get("player", "")) is None:
        _fail("invalid-deferred-intent")
    _uint(str(seed["epoch"]), positive=True)
    for key in ("x", "y", "z"):
        if isinstance(seed[key], bool) or not isinstance(seed[key], (int, float)) \
                or not math.isfinite(seed[key]) or abs(seed[key]) > 10_000_000:
            _fail("invalid-deferred-intent")
    if not isinstance(calculator, dict) or set(calculator) != {
            "dotnetPath", "dotnetSha256", "directory", "files"}:
        _fail("invalid-deferred-intent")
    files = calculator["files"]
    if not isinstance(files, dict) or set(files) != CALCULATOR_FILES \
            or any(not isinstance(value, str) or SHA256.fullmatch(value.lower()) is None
                   for value in files.values()):
        _fail("invalid-deferred-intent")
    for key in ("dotnetPath", "directory"):
        if not isinstance(calculator[key], str) or not Path(calculator[key]).is_absolute():
            _fail("invalid-deferred-intent")
    if not isinstance(calculator["dotnetSha256"], str) \
            or SHA256.fullmatch(calculator["dotnetSha256"].lower()) is None:
        _fail("invalid-deferred-intent")
    expected_directory = (Path(__file__).resolve().parents[1] / "src" / "RiftReader2.Cli"
                          / "bin" / "Release" / "net10.0").resolve(strict=False)
    try:
        if Path(calculator["directory"]).resolve(strict=True) != expected_directory:
            _fail("invalid-deferred-intent")
        Path(calculator["dotnetPath"]).resolve(strict=True)
    except OSError:
        _fail("invalid-deferred-intent")
    return intent, hashlib.sha256(data).hexdigest()


def _validate_receiver_host(receiver: dict) -> None:
    required = {"instanceId", "processId", "processStartUtcTicks", "executablePath",
                "executableSha256", "endpoint"}
    if not isinstance(receiver, dict) or set(receiver) != required:
        _fail("invalid-receiver-pin")
    try:
        host, port_text = receiver["endpoint"].rsplit(":", 1)
        port = int(port_text)
    except (AttributeError, ValueError):
        _fail("invalid-receiver-pin")
    if host not in ("127.0.0.1", "192.168.56.1") or not 1 <= port <= 65535:
        _fail("invalid-receiver-pin")
    if type(receiver["processId"]) is not int or receiver["processId"] < 1 \
            or type(receiver["processStartUtcTicks"]) is not int or receiver["processStartUtcTicks"] < 1:
        _fail("invalid-receiver-pin")
    if _receiver_listener_owner(host, port) != receiver["processId"]:
        _fail("receiver-host-identity-mismatch")
    before = process_identity(receiver["processId"])
    image = Path(before["image"])
    try:
        digest = _sha(image)
    except OSError:
        _fail("receiver-host-identity-mismatch")
    after = process_identity(receiver["processId"])
    owner_after = _receiver_listener_owner(host, port)
    dotnet_ticks = before["startTicks"] + 504_911_232_000_000_000
    if (after != before or owner_after != receiver["processId"]
            or dotnet_ticks != receiver["processStartUtcTicks"]
            or path_key(image) != path_key(Path(receiver["executablePath"]))
            or digest != receiver["executableSha256"].lower()):
        _fail("receiver-host-identity-mismatch")


def _receiver_listener_owner(host: str, port: int) -> int:
    if os.name != "nt":
        _fail("windows-required")
    api = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = api.GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                          wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    size = wintypes.DWORD()
    get_table(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    if not size.value:
        _fail("receiver-listener-query-failed")
    data = ctypes.create_string_buffer(size.value)
    if get_table(data, ctypes.byref(size), False, socket.AF_INET, 3, 0):
        _fail("receiver-listener-query-failed")
    matches = _parse_receiver_listener_rows(bytes(data.raw[:size.value]), port)
    return _select_receiver_listener(matches, host)


def _parse_receiver_listener_rows(table: bytes, port: int) -> list[tuple[str, int]]:
    return parse_tcp_listener_rows(table, port, listener_table=True)


def _select_receiver_listener(matches: list[tuple[str, int]], host: str) -> int:
    if len(matches) != 1 or matches[0][0] != host:
        _fail("receiver-listener-not-unique")
    return matches[0][1]


def _fast_receipt(pin: dict, *, initial: bool) -> tuple[dict, bytes, dict]:
    _validate_receiver_host(pin["receiver"])
    receipt_path = Path(pin["receiptPath"])
    data = _read_regular(receipt_path, _live_gate.MAX_RECEIPT_BYTES, "live-receipt-unavailable")
    if hashlib.sha256(data).hexdigest() != pin["receiptSha256"].lower() and initial:
        _fail("live-receipt-sha256-mismatch")
    receipt = _strict_json_bytes(data, "invalid-live-receipt")
    if set(receipt) != {"schemaVersion", "receiverInstance", "receivedAtUtc",
            "receivedMonotonicNs", "sourceAddress", "observation", "gameReady", "note"}:
        _fail("unexpected-live-receipt-fields")
    reader, receiver = pin["reader"], pin["receiver"]
    if not isinstance(reader, dict) or set(reader) != {"processId", "processStartUtcTicks",
            "executableSha256", "instanceId", "nonce", "sourceAddress"}:
        _fail("invalid-reader-pin")
    try:
        gate = _live_gate.evaluate_receipt(receipt, reader["nonce"], receiver["instanceId"])
    except _live_gate.GateError:
        _fail("live-receipt-not-fresh")
    observation = receipt.get("observation")
    if not isinstance(observation, dict) or set(observation) != {"schemaVersion", "instanceId",
            "nonce", "sequence", "capturedAtUtc", "monotonicMilliseconds", "readerStatus",
            "readerReason", "target", "riftReader2", "delivery", "nativePower"}:
        _fail("unexpected-live-observation-fields")
    if (receipt.get("sourceAddress") != reader["sourceAddress"]
            or observation.get("instanceId") != reader["instanceId"]):
        _fail("live-reader-identity-mismatch")
    target = observation.get("target")
    if not isinstance(target, dict) or set(target) != {"processId", "processStartUtcTicks",
            "executablePath", "executableSha256", "readerSessionNonce"}:
        _fail("unexpected-live-target-fields")
    expected_target = pin["gameIdentity"]
    if not isinstance(expected_target, dict) or set(expected_target) != {
            "processId", "processStartUtcTicks", "executablePath", "executableSha256"}:
        _fail("invalid-source-pin")
    if not isinstance(target, dict) or any(
            target.get(key).casefold() != value.casefold()
            if key in ("executablePath", "executableSha256") else target.get(key) != value
            for key, value in expected_target.items()):
        _fail("live-target-identity-mismatch")
    selected = observation["riftReader2"].get("observation")
    if not isinstance(selected, dict) or set(selected) != {"schemaVersion", "addonVersion",
            "sequence", "epoch", "clock", "player", "fields"} \
            or set(selected.get("clock", {})) != {"status", "value"} \
            or set(selected.get("player", {})) != {"status", "value"}:
        _fail("unexpected-live-selected-fields")
    return receipt, data, gate


def _require_result_matches(command: str, pin: dict, receipt: dict) -> None:
    parts = command.split(" ")
    observation = receipt["observation"]["riftReader2"]["observation"]
    fields = observation["fields"]
    expected = [pin["lab"], pin["reader"]["nonce"], str(observation["epoch"]),
                str(observation["sequence"]), observation["clock"]["value"],
                observation["player"]["value"], fields["coordX"]["value"],
                fields["coordY"]["value"], fields["coordZ"]["value"]]
    actual = [parts[2], parts[3], parts[5], parts[6], float(parts[7]), parts[8],
              float(parts[9]), float(parts[10]), float(parts[11])]
    normalized = [expected[0], expected[1], str(expected[2]), str(expected[3]), float(expected[4]),
                  expected[5], float(expected[6]), float(expected[7]), float(expected[8])]
    if actual != normalized:
        _fail("result-source-mismatch")


def _selected(receipt: dict) -> dict:
    return receipt["observation"]["riftReader2"]["observation"]


def _require_seed(intent: dict, pin: dict, receipt: dict, *, exact_origin: bool = False) -> None:
    selected = _selected(receipt)
    fields, seed = selected["fields"], intent["seed"]
    if (intent["lab"] != pin["lab"] or intent["nonce"] != pin["reader"]["nonce"]
            or selected["player"]["value"] != seed["player"] or selected["epoch"] != seed["epoch"]
            or any((float(fields[f"coord{axis.upper()}"]["value"]) != float(seed[axis])
                    if exact_origin else
                    abs(float(fields[f"coord{axis.upper()}"]["value"]) - float(seed[axis])) > 0.5)
                   for axis in ("x", "y", "z"))):
        _fail("deferred-intent-seed-mismatch")


def _verify_calculator(calculator: dict, directory_override: Path | None = None) -> tuple[Path, Path]:
    dotnet = Path(calculator["dotnetPath"])
    directory = directory_override or Path(calculator["directory"])
    if not dotnet.is_file() or not directory.is_dir() or _sha(dotnet) != calculator["dotnetSha256"].lower():
        _fail("calculator-pin-mismatch")
    for name, digest in calculator["files"].items():
        path = directory / name
        if not path.is_file() or path.is_symlink() or _sha(path) != digest.lower():
            _fail("calculator-pin-mismatch")
    return dotnet, directory


def _freeze_calculator(calculator: dict, output: Path) -> Path:
    _, source = _verify_calculator(calculator)
    frozen = output / "calculator"
    frozen.mkdir()
    for name in sorted(CALCULATOR_FILES):
        (frozen / name).write_bytes((source / name).read_bytes())
    _verify_calculator(calculator, frozen)
    return frozen


def _calculate_deferred(intent: dict, pin: dict, receipt: dict, output: Path,
                        frozen_directory: Path) -> tuple[str, dict]:
    dotnet, directory = _verify_calculator(intent["calculator"], frozen_directory)
    snapshot = output / "deferred-source-snapshot.json"
    report_path = output / "deferred-guidance-report.json"
    snapshot_bytes = json.dumps(receipt["observation"], ensure_ascii=True, sort_keys=True,
                                separators=(",", ":")).encode("ascii")
    snapshot.write_bytes(snapshot_bytes)
    destination = intent["destination"]
    argv = [str(dotnet), str(directory / "RiftReader2.Cli.dll"), "guide-addon",
            "--snapshot", str(snapshot), "--lab", intent["lab"], "--session-id", intent["nonce"],
            "--result-sequence", str(intent["resultSequence"]),
            "--destination-x", str(destination["x"]), "--destination-y", str(destination["y"]),
            "--destination-z", str(destination["z"]), "--output", str(report_path)]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        _fail("calculator-execution-failed")
    if result.returncode != 0 or not report_path.is_file():
        _fail("calculator-execution-failed")
    _verify_calculator(intent["calculator"], frozen_directory)
    report_bytes = _read_regular(report_path, 256 * 1024, "calculator-report-unavailable")
    report = _strict_json_bytes(report_bytes, "invalid-calculator-report")
    if set(report) != {"schemaVersion", "evidenceKind", "lab", "sessionId", "resultSequence",
            "sourceEpoch", "sourceSequence", "sourceClock", "playerId", "source", "destination",
            "calculation", "origin", "freshnessStatus", "deliveryMode", "slashCommand"} \
            or report.get("schemaVersion") != 1 \
            or report.get("evidenceKind") != "calculated-addon-guidance/1":
        _fail("invalid-calculator-report")
    command = validate_addon_command(report.get("slashCommand"), intent["lab"])
    _require_result_matches(command, pin, receipt)
    parts = command.split(" ")
    if int(parts[4]) != intent["resultSequence"]:
        _fail("calculator-report-intent-mismatch")
    selected, fields = _selected(receipt), _selected(receipt)["fields"]
    dx = float(destination["x"]) - float(fields["coordX"]["value"])
    dy = float(destination["y"]) - float(fields["coordY"]["value"])
    dz = float(destination["z"]) - float(fields["coordZ"]["value"])
    expected = (math.hypot(dx, dz), dx, dz, dy)
    actual = tuple(float(parts[index]) for index in (12, 13, 14, 15))
    source_expected = {"x": fields["coordX"]["value"], "y": fields["coordY"]["value"],
                       "z": fields["coordZ"]["value"]}
    if (report.get("lab") != intent["lab"] or report.get("sessionId") != intent["nonce"]
            or report.get("resultSequence") != intent["resultSequence"]
            or report.get("sourceEpoch") != selected["epoch"]
            or report.get("sourceSequence") != selected["sequence"]
            or report.get("sourceClock") != selected["clock"]["value"]
            or report.get("playerId") != selected["player"]["value"]
            or report.get("source") != source_expected or report.get("destination") != destination
            or not isinstance(report.get("calculation"), dict)
            or set(report["calculation"]) != {"deltaX", "deltaY", "deltaZ", "verticalDelta",
                    "planarDistance", "coordinateAxisBearingDegrees", "bearingMeaning"}
            or tuple(float(report["calculation"][key]) for key in
                     ("planarDistance", "deltaX", "deltaZ", "deltaY")) != actual
            or report["calculation"]["verticalDelta"] != report["calculation"]["deltaY"]):
        _fail("calculator-report-intent-mismatch")
    if any(abs(a - b) > max(1e-9, abs(b) * 1e-12) for a, b in zip(actual, expected)):
        _fail("calculator-report-vector-mismatch")
    origin = report.get("origin")
    if (not isinstance(origin, dict) or origin.get("snapshotFileSha256", "").lower()
            != hashlib.sha256(snapshot_bytes).hexdigest()
            or origin.get("sourcePath", "").casefold() != str(snapshot.resolve()).casefold()
            or origin.get("sourceKind") != "live-reader-snapshot"
            or origin.get("bindingStatus") != "bound"):
        _fail("calculator-report-source-mismatch")
    (output / "deferred-command.txt").write_text(command, encoding="ascii", newline="\n")
    evidence = {"schemaVersion": 1,
                "reportSha256": hashlib.sha256(report_bytes).hexdigest(),
                "snapshotSha256": hashlib.sha256(snapshot_bytes).hexdigest(),
                "commandSha256": hashlib.sha256(command.encode("ascii")).hexdigest()}
    _atomic_json(output / "deferred-calculation-evidence.json", evidence)
    return command, evidence


def _fast_age(receipt: dict) -> None:
    now_ns = time.monotonic_ns()
    received_ns = receipt.get("receivedMonotonicNs")
    if type(received_ns) is not int or not 0 <= (now_ns - received_ns) / 1e9 <= MAX_FAST_RESULT_AGE_SECONDS:
        _fail("fast-result-source-expired")
    captured = _parse_time(receipt["observation"]["capturedAtUtc"])
    age = (datetime.now(timezone.utc) - captured).total_seconds() + _live_gate.CLOCK_SKEW_SECONDS
    if not 0 <= age <= MAX_FAST_RESULT_AGE_SECONDS:
        _fail("fast-result-source-expired")
    advance_ms = receipt["observation"]["riftReader2"].get("lastAdvanceAgeMilliseconds")
    if (isinstance(advance_ms, bool) or not isinstance(advance_ms, (int, float))
            or not math.isfinite(float(advance_ms)) or advance_ms < 0
            or advance_ms + age * 1000 >= MAX_FAST_RESULT_AGE_SECONDS * 1000):
        _fail("fast-result-source-expired")


def _require_continuity(frozen: dict, current: dict) -> None:
    old = frozen["observation"]["riftReader2"]["observation"]
    new = current["observation"]["riftReader2"]["observation"]
    if (new.get("epoch") != old.get("epoch") or new.get("player", {}).get("value") != old.get("player", {}).get("value")
            or type(new.get("sequence")) is not int or new["sequence"] < old.get("sequence", 0)
            or not isinstance(new.get("clock", {}).get("value"), (int, float))
            or new["clock"]["value"] < old.get("clock", {}).get("value", math.inf)):
        _fail("fast-result-source-continuity-lost")


def _require_origin_near(source: dict, current: dict) -> None:
    old_fields = _selected(source)["fields"]
    new_fields = _selected(current)["fields"]
    if any(abs(float(new_fields[f"coord{axis}"]["value"])
               - float(old_fields[f"coord{axis}"]["value"])) > 0.5
           for axis in ("X", "Y", "Z")):
        _fail("fast-result-source-position-changed")


def prepare(config: Config, command: str | None, ui_step: str | None,
            expected_game: dict, fast_source_pin_path: Path | None = None,
            guidance_report_path: Path | None = None, hide_frame: str | None = None,
            hide_x: int | None = None, hide_y: int | None = None,
            deferred_intent_path: Path | None = None) -> dict:
    if deferred_intent_path is not None:
        if command is not None or ui_step is not None or any(
                value is not None for value in (hide_frame, hide_x, hide_y)):
            _fail("deferred-intent-operation-conflict")
        intent, intent_sha = load_deferred_intent(deferred_intent_path)
        operation = {"type": "deferred-result", "intent": intent,
                     "intentSha256": intent_sha}
    else:
        operation = validate_operation(command, ui_step, expected_game["lab"],
                                       hide_frame, hide_x, hide_y)
    if fast_source_pin_path is not None and (operation["type"] != "command"
            or not operation["command"].startswith("/rr2guide result ")) \
            and operation["type"] != "deferred-result":
        _fail("fast-source-requires-result-command")
    if operation["type"] == "deferred-result" and fast_source_pin_path is None:
        _fail("deferred-intent-requires-fast-source")
    if guidance_report_path is not None and fast_source_pin_path is None:
        _fail("guidance-report-requires-fast-source")
    if guidance_report_path is not None and operation["type"] == "deferred-result":
        _fail("deferred-intent-operation-conflict")
    config.output.mkdir(parents=True, exist_ok=False)
    if operation["type"] == "deferred-result":
        frozen = _freeze_calculator(operation["intent"]["calculator"], config.output)
        operation["frozenCalculatorDirectory"] = str(frozen)
    screen = config.output / "review-screen.png"
    plan_path = config.output / "plan.json"
    with ControlMutex(config.vmx):
        vm_before = collect_identity(config)
        fast_source = None
        if fast_source_pin_path is None:
            game_before = query_game_identity(config, vm_before)
            _require_game(game_before, expected_game)
        else:
            pin, pin_sha = load_source_pin(fast_source_pin_path)
            if pin["lab"] != expected_game["lab"] or pin["vmIdentity"] != vm_before:
                _fail("fast-source-target-mismatch")
            target = pin["gameIdentity"]
            if any(target.get(key) != expected_game[key] for key in
                   ("processId", "processStartUtcTicks")) \
                    or target.get("executableSha256", "").lower() != expected_game["executableSha256"]:
                _fail("fast-source-target-mismatch")
            receipt, receipt_bytes, gate = _fast_receipt(pin, initial=True)
            if operation["type"] == "deferred-result":
                if operation["intent"]["lab"] != expected_game["lab"]:
                    _fail("deferred-intent-seed-mismatch")
                _require_seed(operation["intent"], pin, receipt, exact_origin=True)
            else:
                _require_result_matches(operation["command"], pin, receipt)
                _fast_age(receipt)
            snapshot_bytes = json.dumps(receipt["observation"], ensure_ascii=True,
                                        sort_keys=True, separators=(",", ":")).encode("ascii")
            snapshot_sha = hashlib.sha256(snapshot_bytes).hexdigest()
            report_evidence = None
            if guidance_report_path is not None:
                report_bytes = _read_regular(guidance_report_path.resolve(strict=True),
                                             256 * 1024, "guidance-report-unavailable")
                guidance = _strict_json_bytes(report_bytes, "invalid-guidance-report")
                if guidance.get("slashCommand") != operation["command"]:
                    _fail("guidance-report-command-mismatch")
                origin = guidance.get("origin")
                if not isinstance(origin, dict) or origin.get("snapshotFileSha256", "").lower() != snapshot_sha:
                    _fail("guidance-report-source-mismatch")
                report_evidence = {"sha256": hashlib.sha256(report_bytes).hexdigest(),
                                   "path": str(guidance_report_path.resolve(strict=True))}
            (config.output / "source-receipt.json").write_bytes(receipt_bytes)
            (config.output / "source-snapshot.json").write_bytes(snapshot_bytes)
            fast_source = {"sourcePin": pin, "sourcePinSha256": pin_sha,
                           "readerProcessIdentityProvenance": "reviewed-startup-attestation-not-http-proven",
                           "receiptSha256": hashlib.sha256(receipt_bytes).hexdigest(),
                           "snapshotSha256": snapshot_sha,
                           "receivedMonotonicNs": receipt["receivedMonotonicNs"],
                           "receivedAtUtc": receipt["receivedAtUtc"],
                           "capturedAtUtc": receipt["observation"]["capturedAtUtc"],
                           "initialGate": gate}
            if report_evidence is not None:
                fast_source["guidanceReport"] = report_evidence
        client = None
        try:
            client = connect(config)
            screen_size = _capture(client, screen)
            captured_at = utc_now()
        finally:
            if client is not None:
                try:
                    client.disconnect()
                except BaseException:
                    pass
        # The exact game identity was acquired immediately before capture.
        # Recheck the VM epoch after capture, but leave the next exact game
        # query to execute's mandatory last-moment pre-input gate.  A second
        # GuestSession query here adds 10-12 seconds without protecting input.
        verify_identity(config, vm_before)
    if operation.get("step") == "hide-addon":
        width, height = screen_size
        if not 0 <= operation["x"] < width or not 0 <= operation["y"] < height:
            _fail("hide-target-outside-screen")
        operation["screenWidth"], operation["screenHeight"] = width, height
    plan = {"schemaVersion": 1, "captureId": uuid.uuid4().hex,
            "capturedAtUtc": captured_at, "screen": str(screen),
            "screenSha256": _sha(screen), "operation": operation,
            "vmIdentity": vm_before, "gameIdentity": expected_game}
    if fast_source is not None:
        plan["fastResultSource"] = fast_source
    plan["planSha256"] = _plan_sha(plan)
    _atomic_json(plan_path, plan)
    return plan


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        _fail("invalid-review-time")
    if parsed.tzinfo is None:
        _fail("invalid-review-time")
    return parsed.astimezone(timezone.utc)


def validate_review(plan: dict, receipt: dict, now: datetime | None = None) -> None:
    if plan.get("planSha256") != _plan_sha(plan):
        _fail("plan-changed")
    keys = {"schemaVersion", "captureId", "screenSha256", "planSha256", "reviewedAtUtc",
            "decision", "gameForeground", "textEntryClosed", "chatEntryOpen", "chatEntryEmpty",
            "chatEntryFocused", "panelOpen", "soleControllerIdle",
            "knownControllerIdle", "queueIdle", "reviewer", "note"}
    if plan.get("operation", {}).get("step") == "hide-addon":
        keys.update({"hideButtonReviewed", "hideFrameReviewed", "hideXReviewed", "hideYReviewed"})
    if plan.get("operation", {}).get("type") == "deferred-result":
        keys.update({"deferredIntentReviewed", "deferredResultSequenceReviewed",
                     "deferredDestinationXReviewed", "deferredDestinationYReviewed",
                     "deferredDestinationZReviewed"})
    if not isinstance(receipt, dict) or set(receipt) != keys or receipt["schemaVersion"] != 1:
        _fail("invalid-review-receipt")
    if (receipt["captureId"] != plan["captureId"]
            or receipt["screenSha256"] != plan["screenSha256"]
            or receipt["planSha256"] != plan["planSha256"]):
        _fail("review-capture-mismatch")
    if (receipt["decision"] != "approved" or receipt["gameForeground"] is not True
            or receipt["soleControllerIdle"] is not True
            or receipt["knownControllerIdle"] is not True
            or receipt["queueIdle"] is not True):
        _fail("capture-not-approved")
    operation = plan.get("operation")
    if isinstance(operation, dict) and operation.get("step") == "hide-addon":
        valid_ui = (set(operation) == {"type", "step", "frame", "x", "y",
                    "screenWidth", "screenHeight"}
                    and receipt["panelOpen"] is True and receipt["chatEntryOpen"] is False
                    and receipt["chatEntryEmpty"] is False and receipt["chatEntryFocused"] is False
                    and receipt["textEntryClosed"] is True
                    and receipt["hideButtonReviewed"] is True
                    and receipt["hideFrameReviewed"] == operation["frame"]
                    and receipt["hideXReviewed"] == operation["x"]
                    and receipt["hideYReviewed"] == operation["y"])
    elif operation == {"type": "ui-step", "step": "close-ui"}:
        valid_ui = (receipt["panelOpen"] is True and receipt["chatEntryOpen"] is False
                    and receipt["chatEntryEmpty"] is False and receipt["chatEntryFocused"] is False
                    and receipt["textEntryClosed"] is True)
    elif operation == {"type": "ui-step", "step": "open-chat"}:
        valid_ui = (receipt["panelOpen"] is False and receipt["chatEntryOpen"] is False
                    and receipt["chatEntryEmpty"] is False and receipt["chatEntryFocused"] is False
                    and receipt["textEntryClosed"] is True)
    elif isinstance(operation, dict) and operation.get("type") in ("command", "deferred-result"):
        valid_ui = (receipt["panelOpen"] is False and receipt["chatEntryOpen"] is True
                    and receipt["chatEntryEmpty"] is True and receipt["chatEntryFocused"] is True
                    and receipt["textEntryClosed"] is False)
        if operation.get("type") == "deferred-result":
            intent = operation.get("intent", {})
            if not isinstance(intent, dict):
                _fail("invalid-plan")
            destination = intent.get("destination", {})
            valid_ui = (valid_ui and receipt["deferredIntentReviewed"] is True
                        and receipt["deferredResultSequenceReviewed"] == intent.get("resultSequence")
                        and receipt["deferredDestinationXReviewed"] == destination.get("x")
                        and receipt["deferredDestinationYReviewed"] == destination.get("y")
                        and receipt["deferredDestinationZReviewed"] == destination.get("z"))
    else:
        _fail("invalid-plan")
    if not valid_ui:
        _fail("reviewed-ui-state-mismatch")
    if receipt["reviewer"] != "root-agent" or not isinstance(receipt["note"], str) \
            or not 1 <= len(receipt["note"]) <= 256:
        _fail("invalid-review-receipt")
    current = now or datetime.now(timezone.utc)
    captured = _parse_time(plan["capturedAtUtc"])
    reviewed = _parse_time(receipt["reviewedAtUtc"])
    if not captured <= reviewed <= current or (current - captured).total_seconds() > MAX_REVIEW_AGE_SECONDS:
        _fail("stale-review-capture")


def _load_json(path: Path, reason: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail(reason)
    if not isinstance(value, dict):
        _fail(reason)
    return value


def _plan_sha(plan: dict) -> str:
    value = dict(plan)
    value.pop("planSha256", None)
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _release_keys(client, command: str = "") -> bool:
    keys = {"enter", "esc", "shift", "ctrl", "alt", "super"}
    for character in command:
        chord = text_keypress(character).split("-")
        keys.update(chord)
    succeeded = True
    for key in sorted(keys):
        try:
            client.keyUp(key)
        except BaseException:
            succeeded = False
    return succeeded


def _release_operation(client, command: str, operation: dict) -> bool:
    succeeded = _release_keys(client, command)
    if operation.get("step") == "hide-addon":
        try:
            client.mouseUp(1)
        except BaseException:
            succeeded = False
    return succeeded


def _send_operation(client, operation: dict, command: str) -> None:
    if operation["type"] in ("command", "deferred-result"):
        _type_text(client, command)
        client.keyPress("enter")
    elif operation["step"] == "open-chat":
        client.keyPress("enter")
    elif operation["step"] == "close-ui":
        client.keyPress("esc")
    else:
        client.mouseMove(operation["x"], operation["y"])
        client.mousePress(1)


def execute(config: Config, plan_path: Path, review_path: Path) -> dict:
    try:
        if plan_path.resolve(strict=True) != (config.output / "plan.json").resolve(strict=True):
            _fail("plan-output-mismatch")
    except OSError:
        _fail("plan-unavailable")
    plan = _load_json(plan_path, "plan-unavailable")
    required = {"schemaVersion", "captureId", "capturedAtUtc", "screen",
                "screenSha256", "operation", "vmIdentity", "gameIdentity", "planSha256"}
    fast_mode = "fastResultSource" in plan
    if set(plan) != required | ({"fastResultSource"} if fast_mode else set()) or plan["schemaVersion"] != 1:
        _fail("invalid-plan")
    if not isinstance(plan["planSha256"], str) or SHA256.fullmatch(plan["planSha256"]) is None \
            or _plan_sha(plan) != plan["planSha256"]:
        _fail("plan-changed")
    screen = Path(plan["screen"])
    try:
        expected_screen = (config.output / "review-screen.png").resolve(strict=True)
        actual_screen = screen.resolve(strict=True)
    except OSError:
        _fail("review-screen-changed")
    if actual_screen != expected_screen or _sha(screen) != plan["screenSha256"]:
        _fail("review-screen-changed")
    game_plan = plan["gameIdentity"]
    if not isinstance(game_plan, dict) or set(game_plan) != {
            "lab", "processId", "processStartUtcTicks", "executableSha256"}:
        _fail("invalid-plan")
    validate_expected_game(game_plan["lab"], game_plan["processId"],
                           game_plan["processStartUtcTicks"], game_plan["executableSha256"])
    operation = plan["operation"]
    if not isinstance(operation, dict):
        _fail("invalid-plan")
    if operation.get("type") == "command" and set(operation) == {"type", "command"}:
        command = validate_addon_command(operation["command"], game_plan["lab"])
    elif (operation.get("type") == "deferred-result"
            and set(operation) == {"type", "intent", "intentSha256", "frozenCalculatorDirectory"}
            and isinstance(operation["intent"], dict)
            and isinstance(operation["intentSha256"], str)
            and SHA256.fullmatch(operation["intentSha256"]) is not None
            and operation["intent"].get("lab") == game_plan["lab"]):
        command = ""
    elif operation in ({"type": "ui-step", "step": "open-chat"},
                       {"type": "ui-step", "step": "close-ui"}):
        command = ""
    elif (operation.get("type") == "ui-step" and operation.get("step") == "hide-addon"
            and set(operation) == {"type", "step", "frame", "x", "y", "screenWidth", "screenHeight"}
            and operation["frame"] in ("readiness", "casting")
            and all(type(operation[key]) is int for key in ("x", "y", "screenWidth", "screenHeight"))
            and 0 <= operation["x"] < operation["screenWidth"] <= 16384
            and 0 <= operation["y"] < operation["screenHeight"] <= 16384):
        command = ""
    else:
        _fail("invalid-plan")
    review = _load_json(review_path, "review-unavailable")
    validate_review(plan, review)
    report_path = config.output / "execution.json"
    if report_path.exists():
        _fail("operation-already-attempted")
    report = {"schemaVersion": 1, "startedAtUtc": utc_now(), "status": "failed",
              "captureId": plan["captureId"], "operation": operation,
              "inputMayHaveBeenSent": False, "inputSent": False,
              "releaseSucceeded": False,
              "before": None, "after": None}
    operation_error = None
    try:
        with ControlMutex(config.vmx):
            vm = collect_identity(config)
            if vm != plan["vmIdentity"]:
                _fail("target-drift")
            if fast_mode:
                source = plan["fastResultSource"]
                if not isinstance(source, dict) or not isinstance(source.get("sourcePin"), dict):
                    _fail("invalid-fast-result-source")
                pin = source["sourcePin"]
                frozen_data = _read_regular(config.output / "source-receipt.json",
                                            _live_gate.MAX_RECEIPT_BYTES, "frozen-receipt-unavailable")
                frozen_snapshot = _read_regular(config.output / "source-snapshot.json",
                                                _live_gate.MAX_RECEIPT_BYTES, "frozen-snapshot-unavailable")
                if (hashlib.sha256(frozen_data).hexdigest() != source.get("receiptSha256")
                        or hashlib.sha256(frozen_snapshot).hexdigest() != source.get("snapshotSha256")):
                    _fail("frozen-source-changed")
                frozen_receipt = _strict_json_bytes(frozen_data, "invalid-frozen-receipt")
                if json.loads(frozen_snapshot) != frozen_receipt["observation"]:
                    _fail("frozen-source-changed")
                if operation["type"] == "deferred-result":
                    intent = operation["intent"]
                    _require_seed(intent, pin, frozen_receipt, exact_origin=True)
                    current_receipt, current_bytes, _ = _fast_receipt(pin, initial=False)
                    _require_seed(intent, pin, current_receipt)
                    (config.output / "deferred-source-receipt.json").write_bytes(current_bytes)
                    command, calculation_evidence = _calculate_deferred(
                        intent, pin, current_receipt, config.output,
                        Path(operation["frozenCalculatorDirectory"]))
                    calculation_receipt = current_receipt
                    report["calculationEvidence"] = calculation_evidence
                else:
                    _require_result_matches(command, pin, frozen_receipt)
                    _fast_age(frozen_receipt)
                    current_receipt, _, _ = _fast_receipt(pin, initial=False)
                    _require_continuity(frozen_receipt, current_receipt)
                game = {key: pin["gameIdentity"][key] for key in
                        ("processId", "processStartUtcTicks", "executableSha256")}
            else:
                game = query_game_identity(config, vm)
                _require_game(game, plan["gameIdentity"])
            report["before"] = {"vm": vm, "game": game}
            client = None
            try:
                client = connect(config)
                # The guest identity/hash query can be slow.  Recheck freshness
                # at the last possible point before the first key event.
                validate_review(plan, review)
                if fast_mode:
                    if operation["type"] == "deferred-result":
                        _fast_age(calculation_receipt)
                        current_receipt, _, _ = _fast_receipt(pin, initial=False)
                        _require_continuity(calculation_receipt, current_receipt)
                        _require_seed(intent, pin, current_receipt)
                        _require_origin_near(calculation_receipt, current_receipt)
                    else:
                        _fast_age(frozen_receipt)
                        current_receipt, _, _ = _fast_receipt(pin, initial=False)
                        _require_continuity(frozen_receipt, current_receipt)
                report["inputMayHaveBeenSent"] = True
                # Commands reach only a reviewed open, focused, empty chat
                # entry. UI steps are exactly one reviewed key attempt.
                _send_operation(client, operation, command)
                report["inputSent"] = True
                time.sleep(0.5)
                _capture(client, config.output / "after-screen.png")
            finally:
                if client is not None:
                    report["releaseSucceeded"] = _release_operation(client, command, operation)
                    try:
                        client.disconnect()
                    except BaseException:
                        pass
            if not report["releaseSucceeded"]:
                _fail("input-release-uncertain")
            verify_identity(config, vm)
            game_after = query_game_identity(config, vm)
            _require_game(game_after, plan["gameIdentity"])
            report["after"] = {"vm": vm, "game": game_after}
            report["status"] = "completed"
    except Blocked as exc:
        operation_error = exc
        report["status"] = "blocked"
        report["reason"] = str(exc)
    except BaseException:
        operation_error = Blocked("console-operation-failed")
        report["status"] = "blocked"
        report["reason"] = str(operation_error)
    report["completedAtUtc"] = utc_now()
    _atomic_json(report_path, report)
    if operation_error:
        raise operation_error
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vmx", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--vmrun", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--lab", required=True)
    prepare_parser.add_argument("--expected-game-pid", required=True, type=int)
    prepare_parser.add_argument("--expected-game-start-ticks", required=True, type=int)
    prepare_parser.add_argument("--expected-game-sha256", required=True)
    operation = prepare_parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--command")
    operation.add_argument("--ui-step", choices=("open-chat", "close-ui", "hide-addon"))
    operation.add_argument("--deferred-result-intent", type=Path)
    prepare_parser.add_argument("--hide-frame", choices=("readiness", "casting"))
    prepare_parser.add_argument("--hide-x", type=int)
    prepare_parser.add_argument("--hide-y", type=int)
    prepare_parser.add_argument("--fast-source-pin", type=Path)
    prepare_parser.add_argument("--guidance-report", type=Path)
    execute_parser = commands.add_parser("execute")
    execute_parser.add_argument("--plan", required=True, type=Path)
    execute_parser.add_argument("--review", required=True, type=Path)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = validate_config(args.vmx, args.port, args.vmrun, args.output,
                                 require_files=True)
        if args.action == "prepare":
            expected = validate_expected_game(args.lab, args.expected_game_pid,
                                              args.expected_game_start_ticks,
                                              args.expected_game_sha256)
            result = prepare(config, args.command, args.ui_step, expected,
                             args.fast_source_pin, args.guidance_report,
                             args.hide_frame, args.hide_x, args.hide_y,
                             args.deferred_result_intent)
            print(json.dumps({"status": "prepared", "captureId": result["captureId"],
                              "screen": result["screen"], "plan": str(config.output / "plan.json")}))
        else:
            result = execute(config, args.plan, args.review)
            print(json.dumps({"status": result["status"], "output": str(config.output)}))
        return 0
    except Blocked as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2
    except BaseException:
        print(json.dumps({"status": "failed", "reason": "unexpected-error"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
