"""One read-only HP/Mana/Energy candidate capture using an explicitly SHA-pinned reader.

No publishing, game input, addon dependency or semantic qualification. LabCodex's
session checks the VM-specific cached credential source before each guest logon.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import GAME_SHA, digest
from scripts.vmware_guest_session import POWERSHELL, SessionError

EVIDENCE = ROOT / "artifacts/native-current-vitals/runs"
QUALIFICATION = "candidate-only; semantics/passive-freshness/restart-unverified"
IDENTITY_MAX_BYTES = 8192
REPORT_MAX_BYTES = 262144
HASH_MAX_BYTES = 256
GUEST_READER = re.compile(
    r"C:\\RIFT_TRANSFER\\RiftReader2Control\\managed-fleet-20261029\\releases\\"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\\RiftReader2\.Live\.exe", re.IGNORECASE)


def checked_guest_reader(lab: str, value: str | None) -> str | None:
    if value is None:
        return None
    if lab != "lab2" or not isinstance(value, str) or GUEST_READER.fullmatch(value) is None:
        raise ValueError("guest-reader-path-not-allowed")
    return value


def checked_expected_game(lab: str, value: dict | None) -> dict | None:
    if value is None:
        return None
    required = {"processId", "processStartUtcTicks", "executableSha256"}
    if (not isinstance(value, dict) or set(value) not in (required, required | {"lab"})
            or value.get("lab", lab) != lab
            or type(value.get("processId")) is not int or not 1 <= value["processId"] <= 2147483647
            or type(value.get("processStartUtcTicks")) is not int
            or not 1 <= value["processStartUtcTicks"] <= 3155378975999999999):
        raise ValueError("expected-game-identity-invalid")
    sha = checked_sha(value["executableSha256"])
    if sha != GAME_SHA:
        raise ValueError("expected-game-build-mismatch")
    return {"processId": value["processId"], "processStartUtcTicks": value["processStartUtcTicks"],
            "executableSha256": sha}


def checked_expected_vm(value: dict | None) -> dict | None:
    if value is None:
        return None
    fields = {"vmx", "port", "logEpoch", "listenerPid", "pid", "image", "startTicks"}
    if (not isinstance(value, dict) or set(value) != fields
            or any(not isinstance(value[key], str) or not value[key]
                   or len(value[key]) > 32768 for key in ("vmx", "image", "logEpoch"))
            or any(type(value[key]) is not int or value[key] <= 0
                   for key in ("port", "listenerPid", "pid", "startTicks"))
            or value["port"] > 65535):
        raise ValueError("expected-vm-identity-invalid")
    return dict(value)


def guest_reader_check(guest_exe: str, reader_sha256: str, *, hold_open: bool = False) -> str:
    # Check the file and every existing ancestor using literal paths. A canonical
    # spelling alone cannot establish that a release directory is not a junction.
    ancestry = (
        "$exe=" + ps_literal(guest_exe) + ";"
        "$item=Get-Item -LiteralPath $exe -Force -ErrorAction Stop;"
        "if($item.PSIsContainer){throw 'guest-reader-not-file'};"
        "$part=$item;while($null -ne $part){"
        "if(($part.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)"
        "{throw 'guest-reader-reparse-point'};"
        "$parent=[IO.Path]::GetDirectoryName($part.FullName);"
        "if([string]::IsNullOrEmpty($parent)){break};"
        "$part=Get-Item -LiteralPath $parent -Force -ErrorAction Stop};"
    )
    if hold_open:
        # Share.Read permits the image loader but denies replacement/deletion and
        # byte changes until the synchronous native command and report checks end.
        return ancestry + (
            "$readerGuard=[IO.File]::Open($exe,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read);"
            "try{$hasher=[Security.Cryptography.SHA256]::Create();"
            "try{$readerHash=[BitConverter]::ToString($hasher.ComputeHash($readerGuard)).Replace('-','')}"
            "finally{$hasher.Dispose()};"
            "if($readerHash -cne " + ps_literal(reader_sha256)
            + "){throw 'guest-reader-sha-mismatch'}}catch{$readerGuard.Dispose();throw};"
        )
    return ancestry + (
        "if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
        + ps_literal(reader_sha256) + "){throw 'guest-reader-sha-mismatch'};"
    )


def checked_sha(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("invalid-sha256")
    return value.upper()


def reject_nonfinite(value: str):
    raise ValueError("native-vitals-report-nonfinite-json")


def finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        reject_nonfinite(value)
    return result


def require_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        reject_nonfinite(str(value))
    elif isinstance(value, dict):
        for item in value.values():
            require_finite(item)
    elif isinstance(value, list):
        for item in value:
            require_finite(item)


def bounded_read(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if not raw or len(raw) > maximum:
        raise ValueError("native-vitals-evidence-size-invalid")
    return raw


def staged_script(guest, script: str, host_path: Path, guest_path: str, *, timeout: int):
    # EncodedCommand has a 4096-character cap in GuestSession. Keep this
    # bounded script as a unique file so long SHA-pinned paths fit reliably.
    raw = script.encode("utf-8-sig")
    if len(raw) > 65536:
        raise ValueError("native-vitals-staged-script-too-large")
    with host_path.open("xb") as stream:
        stream.write(raw)
    guest.run("copyFileFromHostToGuest", str(host_path), guest_path, timeout=50)
    return guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                     "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
                     "-File", guest_path, timeout=timeout)


def validate_report(report: dict, *, pid: int, ticks: int) -> dict:
    require_finite(report)
    if (not isinstance(report, dict) or type(report.get("schemaVersion")) is not int
            or report.get("schemaVersion") != 1
            or report.get("contractVersion") not in (
                "native-current-vitals-candidate-sample/1",
                "native-current-vitals-candidate-sample/2")
            or report.get("status") != "complete" or report.get("sourceBuildSha256") != GAME_SHA
            or report.get("qualification") != QUALIFICATION
            or report.get("source") != "native-process-memory"):
        raise ValueError("native-vitals-report-contract-invalid")
    row = report.get("observation")
    if not isinstance(row, dict) or row.get("source") != "native-process-memory" or row.get("qualification") != QUALIFICATION:
        raise ValueError("native-vitals-observation-invalid")
    identity = row.get("identity")
    if (not isinstance(identity, dict) or type(identity.get("processId")) is not int
            or identity.get("processId") != pid or type(identity.get("processStartUtcTicks")) is not int
            or identity.get("processStartUtcTicks") != ticks or identity.get("executableSha256") != GAME_SHA):
        raise ValueError("native-vitals-game-epoch-mismatch")
    if type(row.get("unitKey")) is not int or not 0 < row["unitKey"] < 1 << 64:
        raise ValueError("native-vitals-unit-key-invalid")
    try:
        start = datetime.fromisoformat(row["startedAtUtc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(row["completedAtUtc"].replace("Z", "+00:00"))
        if start.utcoffset() is None or end.utcoffset() is None or end < start:
            raise ValueError("invalid-clock")
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise ValueError("native-vitals-acquisition-time-invalid") from exc
    contract = report["contractVersion"]
    values = {}
    names = ("health", "energy") if contract.endswith("/1") else ("health", "mana", "energy")
    for name in names:
        field = row.get(name)
        if not isinstance(field, dict):
            raise ValueError("native-vitals-field-missing")
        status, reason = field.get("status"), field.get("unavailableReason")
        if status == "calculated-candidate":
            current, maximum = field.get("current"), field.get("maximum")
            if (reason is not None or type(current) is not int or type(maximum) is not int
                    or not 0 <= current <= maximum or maximum <= 0 or not isinstance(field.get("inputs"), dict)):
                raise ValueError("native-vitals-candidate-value-invalid")
        elif status == "unavailable":
            if not isinstance(reason, str) or not reason or field.get("current") is not None or field.get("maximum") is not None:
                raise ValueError("native-vitals-unavailable-field-invalid")
        else:
            raise ValueError("native-vitals-field-status-invalid")
        values[name] = field
    if contract.endswith("/2"):
        mana_calculated = values["mana"]["status"] == "calculated-candidate"
        energy_calculated = values["energy"]["status"] == "calculated-candidate"
        if mana_calculated and energy_calculated:
            raise ValueError("native-vitals-resource-kind-conflict")
        if (mana_calculated and
                values["mana"]["inputs"].get("verifiedTypeCode") != "0x072A"):
            raise ValueError("native-vitals-mana-type-evidence-invalid")
        if (energy_calculated and
                values["energy"]["inputs"].get("verifiedTypeCode") != "0x072B"):
            raise ValueError("native-vitals-energy-type-evidence-invalid")
        if mana_calculated and values["energy"].get("unavailableReason") != "not-energy-kind-four":
            raise ValueError("native-vitals-mana-energy-exclusion-invalid")
        if energy_calculated and values["mana"].get("unavailableReason") != "not-mana-kind-three":
            raise ValueError("native-vitals-energy-mana-exclusion-invalid")
    if "mana" not in values:
        # Contract v1 predates the distinct Mana field. Preserve replay
        # compatibility without implying that the old report observed Mana.
        values["mana"] = {"status": "unavailable",
                          "unavailableReason": "legacy-contract-v1-without-mana",
                          "current": None, "maximum": None, "inputs": None}
    return {"unitKey": row["unitKey"], "health": values["health"], "mana": values["mana"],
            "energy": values["energy"], "contractVersion": contract,
            "readMilliseconds": (end - start).total_seconds() * 1000,
            "qualification": QUALIFICATION}


def run(lab: str, reader: Path, reader_sha256: str, guest_reader: str | None = None,
        expected_game: dict | None = None, expected_vm: dict | None = None) -> dict:
    started = phase_started = time.perf_counter()
    timings = {}
    if lab not in ("lab1", "lab2"):
        raise ValueError("invalid-lab")
    reader = Path(reader).absolute()
    reader_sha256 = checked_sha(reader_sha256)
    if not reader.is_file() or reader.is_symlink() or reader.name != "RiftReader2.Live.exe" or digest(reader) != reader_sha256:
        raise ValueError("published-native-reader-sha-or-path-mismatch")
    guest_reader = checked_guest_reader(lab, guest_reader)
    expected_game = checked_expected_game(lab, expected_game)
    expected_vm = checked_expected_vm(expected_vm)
    if guest_reader is not None and expected_game is None:
        raise ValueError("guest-reader-reuse-requires-expected-game")
    timings["hostReaderHash"] = time.perf_counter() - phase_started
    phase_started = time.perf_counter()
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    if expected_vm is not None and vm != expected_vm:
        raise ValueError("expected-vm-epoch-mismatch")
    timings["vmPreflight"] = time.perf_counter() - phase_started
    token = uuid.uuid4().hex
    output = EVIDENCE / lab / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + r"\current-vitals-" + reader_sha256 + "\\" + token
    guest_exe = guest_reader or (guest_root + r"\RiftReader2.Live.exe")
    guest_report = guest_root + r"\sample-" + token + ".json"
    guest_probe = guest_root + r"\identity-" + token + ".json"

    phase_started = time.perf_counter()
    with api._session(config, settings, vm, output) as guest:
        timings["sessionOpen"] = time.perf_counter() - phase_started
        phase_started = time.perf_counter()
        preflight = (
            "$ErrorActionPreference='Stop';"
            "$folder=" + ps_literal(guest_root) + ";"
            "if(Test-Path -LiteralPath $folder){throw 'guest-staging-exists'};"
            "[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$game=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);"
            "if($game.Count -ne 1){throw 'exactly-one-game-required'};"
            "$p=$game[0];$sha=(Get-FileHash -LiteralPath $p.Path -Algorithm SHA256).Hash;"
            "if($sha -cne " + ps_literal(GAME_SHA) + "){throw 'rift-build-mismatch'};"
            "$exe=" + ps_literal(guest_exe) + ";"
            "$installed=Test-Path -LiteralPath $exe;"
            + (guest_reader_check(guest_exe, reader_sha256) if guest_reader is not None
               else "if($installed){throw 'guest-reader-exists'};") +
            "$data=[ordered]@{pid=[int]$p.Id;ticks=[long]$p.StartTime.ToUniversalTime().Ticks;"
            "sha=$sha;installed=[bool]$installed};"
            "[IO.File]::WriteAllText(" + ps_literal(guest_probe) + ","
            "($data|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)));"
            "if((Get-Item -LiteralPath " + ps_literal(guest_probe) + ").Length -gt "
            + str(IDENTITY_MAX_BYTES) + "){throw 'guest-identity-size-invalid'}"
        )
        staged_script(guest, preflight, output / "preflight.ps1",
                      settings["guestRoot"] + "\\vitals-preflight-" + token + ".ps1", timeout=80)
        timings["guestPreflight"] = time.perf_counter() - phase_started
        phase_started = time.perf_counter()
        guest.copy_from_guest(guest_probe, output / "identity.json", timeout=50)
        identity = json.loads(bounded_read(output / "identity.json", IDENTITY_MAX_BYTES).decode("utf-8-sig"),
                              parse_constant=reject_nonfinite, parse_float=finite_float)
        if not isinstance(identity, dict):
            raise ValueError("guest-native-sampler-identity-invalid")
        pid, ticks = identity.get("pid"), identity.get("ticks")
        if (type(pid) is not int or pid <= 0 or type(ticks) is not int or ticks <= 0
                or identity.get("sha") != GAME_SHA or identity.get("installed") is not (guest_reader is not None)):
            raise ValueError("guest-native-sampler-identity-invalid")
        if expected_game is not None and (pid != expected_game["processId"]
                or ticks != expected_game["processStartUtcTicks"]
                or identity["sha"] != expected_game["executableSha256"]):
            raise ValueError("expected-game-epoch-mismatch")
        timings["identityTransferAndValidation"] = time.perf_counter() - phase_started
        phase_started = time.perf_counter()
        if guest_reader is None:
            guest.run("copyFileFromHostToGuest", str(reader), guest_exe, timeout=180)
        timings["readerCopy"] = time.perf_counter() - phase_started
        launch = (
            "$ErrorActionPreference='Stop';"
            + (guest_reader_check(guest_exe, reader_sha256, hold_open=True) + "try{"
               if guest_reader is not None else (
                "$exe=" + ps_literal(guest_exe) + ";"
                "if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
                + ps_literal(reader_sha256) + "){throw 'guest-reader-sha-mismatch'};")) +
            "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
            "if($g.ProcessName -cne 'rift_x64' -or "
            "[long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks)
            + "){throw 'game-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
            + ps_literal(GAME_SHA) + "){throw 'rift-build-changed'};"
            "$out=" + ps_literal(guest_report) + ";"
            "if(Test-Path -LiteralPath $out){throw 'guest-report-exists'};"
            "& $exe sample-current-vitals --pid " + str(pid) + " --start-ticks " + str(ticks)
            + " --output $out | Out-Null;"
            "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};"
            "if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'};"
            "if((Get-Item -LiteralPath $out).Length -gt " + str(REPORT_MAX_BYTES)
            + "){throw 'guest-report-size-invalid'};"
            "[IO.File]::WriteAllText(" + ps_literal(guest_report + ".sha256") + ","
            "(Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash)"
        )
        if guest_reader is not None:
            launch += "}finally{$readerGuard.Dispose()}"
        try:
            phase_started = time.perf_counter()
            staged_script(guest, launch, output / "capture.ps1",
                          settings["guestRoot"] + "\\vitals-capture-" + token + ".ps1", timeout=130)
            timings["guestLaunch"] = time.perf_counter() - phase_started
        except SessionError as exc:
            if "timeout" in str(exc).lower():
                raise SessionError("native-vitals-command-timeout; guest-reader-process-cleanup-unverified") from None
            raise
        phase_started = time.perf_counter()
        guest.copy_from_guest(guest_report, output / "samples.json", timeout=70)
        guest.copy_from_guest(guest_report + ".sha256", output / "samples.sha256", timeout=50)
        timings["reportTransfer"] = time.perf_counter() - phase_started
        phase_started = time.perf_counter()
    timings["sessionClose"] = time.perf_counter() - phase_started
    phase_started = time.perf_counter()
    raw = bounded_read(output / "samples.json", REPORT_MAX_BYTES)
    report_sha = bounded_read(output / "samples.sha256", HASH_MAX_BYTES).decode("utf-8-sig").strip()
    if hashlib.sha256(raw).hexdigest().upper() != checked_sha(report_sha):
        raise ValueError("guest-report-sha-mismatch")
    parsed = json.loads(raw.decode("utf-8-sig"), parse_constant=reject_nonfinite, parse_float=finite_float)
    metrics = validate_report(parsed, pid=pid, ticks=ticks)
    timings["reportValidation"] = time.perf_counter() - phase_started
    summary = {
        "schemaVersion": 1,
        "status": "candidate-only",
        "lab": lab,
        "vmIdentity": vm,
        "gameProcessId": pid,
        "gameProcessStartUtcTicks": ticks,
        "gameSha256": GAME_SHA,
        "readerExecutableSha256": reader_sha256,
        "guestReaderReused": guest_reader is not None,
        "guestReaderPath": guest_exe,
        "phaseWallSeconds": timings,
        "wallSecondsBeforeSummaryWrite": time.perf_counter() - started,
        "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
        "sourceReport": str(output / "samples.json"),
        "metrics": metrics,
        "limitation": "Current-process HP/Mana/Energy candidates only; independent changed-state, passive freshness and restart proof pending."
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    parser.add_argument("--reader", type=Path, required=True)
    parser.add_argument("--reader-sha256", required=True)
    parser.add_argument("--guest-reader", help="Explicit SHA-verified existing Lab2 managed release executable")
    parser.add_argument("--expected-game-pid", type=int)
    parser.add_argument("--expected-game-start-ticks", type=int)
    parser.add_argument("--expected-game-sha256")
    args = parser.parse_args()
    try:
        pin = (args.expected_game_pid, args.expected_game_start_ticks, args.expected_game_sha256)
        if any(value is not None for value in pin) and not all(value is not None for value in pin):
            raise ValueError("expected-game-fields-required-together")
        expected = None if pin[0] is None else {"processId": pin[0], "processStartUtcTicks": pin[1],
                                               "executableSha256": pin[2]}
        print(json.dumps(run(args.lab, args.reader, args.reader_sha256, args.guest_reader, expected)), flush=True)
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:160]}), flush=True)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
