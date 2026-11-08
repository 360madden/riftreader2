"""Bounded location/pair CLI wrapper; OFFLINE-TESTED ONLY, no live readiness claim.

IMPORTANT: LabCodex._session verifies VM identity and cached credentials, NOT the
persistent agent activeNativeRead lane. This standalone guest CLI does not acquire
that lane or exclusive capture ownership. A caller must independently establish
cooperative exclusion before live use; never overlap agent/native readers merely
because this wrapper performs no game input. Root did not authorize live use here.
Candidate sources never establish navigation readiness or atomic world identity.
Wrapper JSON schemaVersion=2 encodes gameProcessStartUtcTicks as a lossless decimal
string; the native reader's original report contract is unchanged.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex, SessionError
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import GAME_SHA, digest
from scripts.sample_current_native_vitals import checked_expected_vm, checked_expected_game, guest_reader_check, staged_script
from scripts.control_host import decode_json

READER = ROOT / "artifacts/native-xyz-lease-20261108-0213z-7b942e6a/publish/RiftReader2.Live.exe"
READER_SHA = "DCFC17E18A4F361095B5701AB31CDF566664178781E0740FCC8969D2C61957FD"
READER_LENGTH = 117966688
# New command only: historical location/pair modes retain their original binary.
REFRESH_READER = ROOT / "artifacts/native-refresh-branch-20261108-01/publish/RiftReader2.Live.exe"
REFRESH_READER_SHA = "E9F0A3F4EC45A1C9F565A8322DEFAA6CB62A674D3B6EE9A2B27C5A43262BFBF2"
REFRESH_READER_LENGTH = 118011744
EVIDENCE = ROOT / "artifacts/native-xyz-lease-20261108-0213z-7b942e6a/runs"
MAX_REPORT_BYTES = 2 * 1024 * 1024
LOCATION_QUALIFICATION = "cached XYZ and zone candidates; sequential, not atomic; world instance, API correspondence, passive freshness and restart unverified"
PAIR_QUALIFICATION = "candidate-only; sequential acquisition, position semantics and passive freshness unverified"
ZONE_QUALIFICATION = "zone ID candidate only; API correspondence, name, freshness and restart unverified"


def invalid():
    raise ValueError("location-pair-report-invalid")


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def stamp(value):
    if not isinstance(value, str):
        invalid()
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?(?:Z|\+00:00)", value)
    if match is None:
        invalid()
    date = datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
    delta = date - datetime(1, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + int((match.group(2) or "").ljust(7, "0"))


def interval(row, outer=None, prefix=""):
    if not isinstance(row, dict):
        invalid()
    start, end = stamp(row[prefix + "startedAtUtc"]), stamp(row[prefix + "completedAtUtc"])
    if end < start or (outer is not None and not outer[0] <= start <= end <= outer[1]):
        invalid()
    return start, end


def unit(row):
    key = row.get("unitKey")
    if (not isinstance(key, str) or re.fullmatch(r"[1-9][0-9]{0,19}", key) is None
            or int(key) > 2**64 - 1 or row.get("unitIdCandidate") != f"u{int(key):016X}"):
        invalid()
    return key


def position(value):
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        invalid()
    if any(type(value[axis]) not in (int, float) or not math.isfinite(value[axis]) for axis in ("x", "y", "z")):
        invalid()
    return dict(value)


def identity(value, pid, ticks):
    fields = {"processId", "processStartUtcTicks", "executablePath", "executableSha256", "moduleBaseAddress", "moduleSize"}
    if (not isinstance(value, dict) or set(value) != fields
            or type(value["processId"]) is not int or value["processId"] != pid
            or type(value["processStartUtcTicks"]) is not int or value["processStartUtcTicks"] != ticks
            or value["executableSha256"] != GAME_SHA
            or not isinstance(value["executablePath"], str) or not value["executablePath"]
            or not integer(value["moduleBaseAddress"], 0x10000, 0x7FFFFFFFFFFF)
            or value["moduleBaseAddress"] % 8
            or not integer(value["moduleSize"], 0x34731B8, 0x7FFFFFFFFFFF - value["moduleBaseAddress"])):
        invalid()
    return value


def native_hash(key):
    """Exact unchecked uint/int arithmetic from AbilityRecords.Hash."""
    low = key if key < 2**31 else key - 2**32
    quotient = (abs(low) // 127773) * (-1 if low < 0 else 1)
    remainder = low - quotient * 127773
    signed = (remainder * 16807 - quotient * 2836) & 0xFFFFFFFF
    if signed >= 2**31:
        signed -= 2**32
    return (signed if signed >= 0 else signed + 2147483647) & 0xFFFFFFFF


def zone_candidate(zone):
    status, child = zone.get("status"), zone.get("childStatus")
    if status not in {"null-provider", "null-registry", "cache-miss", "null-holder",
                      "null-record", "unqualified-cache-record", "type-0073-candidate"}:
        invalid()
    key, candidate = zone.get("childKey"), zone.get("zoneIdCandidate")
    if child == "null":
        if key is not None:
            invalid()
        term = 0
    elif child == "type-1e17-raw-candidate":
        if not integer(key, 0, 2**32 - 1):
            invalid()
        term = native_hash(key)
    elif child in (None, "unverified-type"):
        if key is not None:
            invalid()
        term = None
    else:
        invalid()
    if status not in ("unqualified-cache-record", "type-0073-candidate"):
        if child is not None:
            invalid()
    elif child is None:
        invalid()
    if status == "type-0073-candidate" and term is not None:
        total = (term + 0x7A6F656E) & 0xFFFFFFFF
        low = (native_hash(total) + total) & 0xFFFFFFFF
        expected = f"z{zone['rawZoneKey']:08X}{low:08X}"
        if candidate != expected:
            invalid()
    elif candidate is not None:
        invalid()
    return candidate



REFRESH_QUALIFICATION = "branch-inputs-and-0x6136B0-predicate-only; no writer execution, independently fresh XYZ, world position or facing proven"


def refresh_report(report, pid, ticks):
    """Validate native /2 evidence without interpreting eligibility as freshness."""
    if (type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 2
            or report.get("contractVersion") != "native-current-position-refresh-branch-candidate/2"
            or report.get("status") != "complete" or report.get("qualification") != REFRESH_QUALIFICATION
            or report.get("processRevalidationStatus") != "passed-before-publication"
            or report.get("sourceBuildSha256") != GAME_SHA):
        invalid()

    def decimal(value, low, high):
        if (not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]{0,19}", value) is None
                or not low <= int(value) <= high):
            invalid()
        return int(value)

    def hexadecimal(value, pointer=False):
        if not isinstance(value, str) or re.fullmatch(r"0x[0-9A-F]{16}", value) is None:
            invalid()
        number = int(value, 16)
        if pointer and (not 0x10000 <= number <= 0x7FFFFFFFFFFF or number % 8):
            invalid()
        return number

    process = report["processIdentity"]
    if (set(process) != {"processId", "processStartUtcTicks", "executableSha256", "moduleBaseAddressHex", "moduleSize"}
            or type(process["processId"]) is not int or process["processId"] != pid
            or decimal(process["processStartUtcTicks"], 1, 3155378975999999999) != ticks
            or process["executableSha256"] != GAME_SHA):
        invalid()
    base = hexadecimal(process["moduleBaseAddressHex"], True)
    if not integer(process["moduleSize"], 0x2F5791C, 0x7FFFFFFFFFFF - base):
        invalid()
    row = report["observation"]
    fields = {"startedAtUtc", "completedAtUtc", "playerKeyDecimal", "playerUnitIdCandidate",
              "playerEntityHex", "positionComponentHex", "referencedHandleHex", "referencedHandleDecimal",
              "referencedEntityHex", "flag", "sourceSelector", "status", "sourceComponentHex",
              "sourceGuardContextHex", "sourceGuardValue", "sourceProviderPresent", "sourceGuardStatus",
              "sourceGuardEligible"}
    if not isinstance(row, dict) or set(row) != fields:
        invalid()
    interval(row)
    key = decimal(row["playerKeyDecimal"], 1, 2**64 - 1)
    if row["playerUnitIdCandidate"] != f"u{key:016X}":
        invalid()
    for name in ("playerEntityHex", "positionComponentHex"):
        hexadecimal(row[name], True)
    for name in ("referencedEntityHex", "sourceComponentHex", "sourceGuardContextHex"):
        if row[name] is not None:
            hexadecimal(row[name], True)
    handle = row["referencedHandleDecimal"]
    if handle is None:
        if row["referencedHandleHex"] is not None:
            invalid()
    elif decimal(handle, 0, 2**64 - 1) != hexadecimal(row["referencedHandleHex"]):
        invalid()
    flag, selector, value = row["flag"], row["sourceSelector"], row["sourceGuardValue"]
    if ((flag is not None and not integer(flag, 0, 255))
            or (selector is not None and not integer(selector, -2**31, 2**31-1))
            or (value is not None and not integer(value, -2**31, 2**31-1))
            or (row["sourceProviderPresent"] is not None and type(row["sourceProviderPresent"]) is not bool)):
        invalid()
    status, guard = row["status"], row["sourceGuardStatus"]
    source, context, provider = row["sourceComponentHex"], row["sourceGuardContextHex"], row["sourceProviderPresent"]
    ref = row["referencedEntityHex"]
    # Each tuple specifies the exact nullable operands available at the native read stage.
    states = {
        "unavailable": ("not-applicable", None, None, None, None),
        "position-owner-mismatch": ("not-applicable", None, None, None, None),
        "guard-ineligible-candidate": ("not-evaluated-flag-zero", None, None, None, None),
        "flag-branch-selector-unavailable": ("unavailable-invalid-selector", None, None, None, None),
        "flag-branch-self-source-unavailable": ("unavailable-source-component", None, None, None, None),
        "flag-branch-source-owner-unavailable": ("unavailable-source-owner", None, None, None, None),
        "flag-branch-source-owner-mismatch": ("unavailable-source-owner-mismatch", None, None, None, None),
        "handle-branch-selector-unavailable": ("not-applicable-handle-branch", None, None, None, None),
        "handle-branch-referenced-entity-unavailable": ("not-applicable-handle-branch", None, None, None, None),
    }
    eligible = None
    if status in states:
        if (guard, source, context, value, provider) != states[status] or ref is not None:
            invalid()
    elif status == "handle-branch-referenced-source-present-candidate":
        if guard != "not-applicable-handle-branch" or source is None or ref is None or any(
                x is not None for x in (context, value, provider)):
            invalid()
    elif status == "flag-branch-guard-unavailable":
        if source is None or ref is not None:
            invalid()
        if guard in ("unavailable-context-pointer", "unavailable-null-context"):
            allowed = context is None and value is None and provider is None
        elif guard == "unavailable-nested-value":
            allowed = context is not None and value is None and provider is None
        elif guard == "unavailable-provider-pointer":
            allowed = context is not None and value is not None and value >= 0 and provider is None
        else:
            allowed = False
        if not allowed:
            invalid()
    elif status in ("flag-branch-guard-ineligible-candidate", "flag-branch-guard-eligible-candidate"):
        if source is None or context is None or ref is not None or value is None:
            invalid()
        if guard == "ineligible-negative-context":
            allowed, eligible = value < 0 and provider is None, False
        elif guard == "ineligible-null-provider":
            allowed, eligible = value >= 0 and provider is False, False
        elif guard == "eligible-candidate":
            allowed, eligible = value >= 0 and provider is True, True
        else:
            allowed = False
        if not allowed or (status == "flag-branch-guard-eligible-candidate") != (eligible is True):
            invalid()
    else:
        invalid()
    if row["sourceGuardEligible"] is not eligible:
        invalid()
    if status == "position-owner-mismatch":
        if any(x is not None for x in (handle, flag, selector)):
            invalid()
    elif status == "unavailable":
        if selector is not None or (handle is None and flag is not None) or (handle is not None and handle != "0"):
            invalid()
    elif status.startswith("handle-branch-"):
        if handle is None or int(handle) == 0 or flag is not None:
            invalid()
        if status == "handle-branch-selector-unavailable":
            if selector is None or 0 <= selector < 0x60:
                invalid()
        elif status.endswith("present-candidate") and (selector is None or not 0 <= selector < 0x60):
            invalid()
        elif status.endswith("entity-unavailable") and selector is not None and not 0 <= selector < 0x60:
            invalid()
    else:
        if handle != "0":
            invalid()
        if status == "guard-ineligible-candidate":
            if flag != 0 or selector is not None:
                invalid()
        elif flag is None or flag == 0:
            invalid()
        elif status == "flag-branch-selector-unavailable":
            if selector is None or 0 <= selector < 0x60:
                invalid()
        elif selector is None or not 0 <= selector < 0x60:
            invalid()
    return {**row, "qualification": REFRESH_QUALIFICATION,
            "passiveFreshness": "unqualified", "movementEligible": False}


def _validate_report(report, *, mode, pid, ticks):
    if (mode not in ("location-context", "paired-position") or not isinstance(report, dict)
            or type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 1
            or report.get("status") != "complete"):
        invalid()
    expected_contract = ("native-current-location-context-candidate/1" if mode == "location-context"
                         else "native-current-paired-position-candidate-sample/1")
    if report.get("contractVersion") != expected_contract:
        invalid()
    row = report.get("observation")
    if not isinstance(row, dict):
        invalid()
    process = identity(row.get("identity"), pid, ticks)
    outer = interval(row)
    if mode == "location-context":
        key = unit(row)
        if (row.get("status") != "candidate-only" or row.get("qualification") != LOCATION_QUALIFICATION
                or row.get("worldInstanceStatus") != "unavailable"):
            invalid()
        own = {"startedAtUtc": row["positionStartedAtUtc"], "completedAtUtc": row["positionCompletedAtUtc"]}
        position_interval = interval(own, outer)
        xyz = position(row.get("position"))
        zone = row.get("zone")
        if (not isinstance(zone, dict) or zone.get("identity") != process
                or type(zone.get("selfKey")) is not int or zone["selfKey"] != int(key)
                or zone.get("qualification") != ZONE_QUALIFICATION
                or not isinstance(zone.get("status"), str) or not zone["status"]
                or not integer(zone.get("rawZoneKey"), 0, 2**32 - 1)):
            invalid()
        zone_interval = interval(zone, outer)
        if zone_interval[0] < position_interval[1]:
            invalid()
        zone_id = zone_candidate(zone)
        timing_fields = ("acquisitionElapsedMilliseconds", "acquisitionElapsedClock", "acquisitionElapsedKind")
        timing = {}
        if any(name in zone for name in timing_fields):
            if not all(name in zone for name in timing_fields):
                invalid()
            elapsed, clock, kind = (zone[name] for name in timing_fields)
            if any(value is not None for value in (elapsed, clock, kind)):
                if (type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0
                        or clock != "monotonic-stopwatch" or kind != "zone-read-including-final-validation"):
                    invalid()
                # Independent diagnostic clock/scope: not a UTC gap, atomicity proof or admission threshold.
                # Excludes lease/session acquisition and command-level revalidation.
                timing = {"zoneAcquisitionElapsedMilliseconds": elapsed,
                          "zoneAcquisitionElapsedClock": clock,
                          "zoneAcquisitionElapsedKind": kind}
        return {"unitKey": key, "unitIdCandidate": row["unitIdCandidate"], "position": xyz,
                "zoneIdCandidate": zone_id, "zoneStatus": zone["status"],
                **timing,
                "crossFieldTemporalStatus": "unqualified-sequential",
                "crossFieldGapKind": "position-complete-to-zone-start",
                "crossFieldGapMeasurementClock": "utc-wall-clock",
                "crossFieldGapMilliseconds": (zone_interval[0] - position_interval[1]) / 10_000,
                "worldInstanceStatus": "unavailable", "qualification": LOCATION_QUALIFICATION}
    if (row.get("qualification") != PAIR_QUALIFICATION or report.get("qualification") != PAIR_QUALIFICATION
            or report.get("processRevalidationStatus") != "passed-before-publication"
            or row.get("zoneIdentityStatus") != "unavailable" or row.get("worldIdentityStatus") != "unavailable"
            or row.get("atomicityQualified") is not False
            or not isinstance(row.get("clockDomain"), str) or re.fullmatch(r"[0-9a-f]{32}", row["clockDomain"]) is None
            or not isinstance(row.get("beforeGuardStatus"), str)
            or row["beforeGuardStatus"] != row.get("afterGuardStatus")):
        invalid()
    span = row.get("acquisitionSpanMilliseconds")
    if type(span) not in (int, float) or not math.isfinite(span) or not 0 <= span <= 1000:
        invalid()

    def sample(value, self_row=False):
        if not isinstance(value, dict):
            invalid()
        key = unit(value)
        interval(value, outer)
        start, end = value.get("monotonicStartMilliseconds"), value.get("monotonicEndMilliseconds")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end)) or not 0 <= start <= end:
            invalid()
        status = value.get("status")
        if status == "candidate":
            xyz = position(value.get("position"))
        elif status == "component-unavailable" and not self_row and value.get("position") is None:
            xyz = None
        else:
            invalid()
        return {"status": status, "unitKey": key, "unitIdCandidate": value["unitIdCandidate"],
                "position": xyz}, start, end

    own, self_start, self_end = sample(row.get("self"), True)
    if self_end - self_start > span:
        invalid()
    target = row.get("target")
    cross_field_gap = None
    guard = row["beforeGuardStatus"]
    if (guard not in {"fallback-key-candidate", "raw-getter-zero-candidate",
                      "override-unavailable", "guard-unreadable-or-invalid"}
            or (guard == "fallback-key-candidate") != (target is not None)):
        invalid()
    if target is None:
        if (row.get("status") != "target-unavailable" or row.get("targetStatus") != "unavailable"
                or row.get("startSkewMilliseconds") is not None
                or row.get("maximumSampleSeparationMilliseconds") is not None):
            invalid()
        selected = None
    else:
        selected, target_start, target_end = sample(target)
        if (target_start < self_end or row.get("targetStatus") != selected["status"]
                or stamp(row["self"]["completedAtUtc"]) > stamp(target["startedAtUtc"])):
            invalid()
        cross_field_gap = target_start - self_end
        expected_status = "paired-candidate" if selected["status"] == "candidate" else "target-unavailable"
        if row.get("status") != expected_status:
            invalid()
        for name, expected in (("startSkewMilliseconds", target_start - self_start),
                               ("maximumSampleSeparationMilliseconds", target_end - self_start)):
            value = row.get(name)
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value - expected) > 1e-6 or value > span:
                invalid()
    return {"self": own, "target": selected, "targetStatus": row["targetStatus"],
            "acquisitionSpanMilliseconds": span, "zoneIdentityStatus": "unavailable",
            "crossFieldTemporalStatus": "unqualified-sequential",
            "crossFieldGapKind": "self-position-complete-to-target-start",
            "crossFieldGapMeasurementClock": "source-monotonic-milliseconds",
            "crossFieldGapMilliseconds": cross_field_gap,
            "worldIdentityStatus": "unavailable", "atomicityQualified": False, "qualification": PAIR_QUALIFICATION}

def validate_report(report, *, mode, pid, ticks):
    try:
        if mode == "refresh-branch":
            if not isinstance(report, dict):
                invalid()
            return refresh_report(report, pid, ticks)
        return _validate_report(report, mode=mode, pid=pid, ticks=ticks)
    except (KeyError, TypeError, AttributeError, OverflowError):
        invalid()


def run(lab: str, mode: str, *, expected_vm=None, expected_game=None) -> dict:
    if lab not in ("lab1", "lab2") or mode not in ("location-context", "paired-position", "refresh-branch"):
        raise ValueError("location-pair-options-invalid")
    reader, reader_sha, reader_length = ((REFRESH_READER, REFRESH_READER_SHA, REFRESH_READER_LENGTH)
                                         if mode == "refresh-branch" else (READER, READER_SHA, READER_LENGTH))
    command = "position-refresh-branch" if mode == "refresh-branch" else mode
    vm_pin = checked_expected_vm(expected_vm)
    game_pin = checked_expected_game(lab, expected_game)
    source_path = Path(__file__).resolve()
    source_sha = digest(source_path)
    if not reader.is_file() or reader.is_symlink() or reader.stat().st_size != reader_length or digest(reader) != reader_sha:
        raise ValueError("published-native-reader-sha-or-path-mismatch")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    if vm_pin is not None and vm != vm_pin:
        raise ValueError("location-pair-vm-pin-mismatch")
    token = uuid.uuid4().hex
    output = EVIDENCE / mode / lab / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + r"\current-location-pair-" + reader_sha[:16]
    guest_exe = guest_root + r"\RiftReader2.Live.exe"
    guest_report = guest_root + r"\sample-" + token + ".json"
    guest_probe = guest_root + r"\identity-" + token + ".json"

    with api._session(config, settings, vm, output) as guest:
        preflight = (
            "$ErrorActionPreference='Stop';"
            "$folder=" + ps_literal(guest_root) + ";"
            "[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$game=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);"
            "if($game.Count -ne 1){throw 'exactly-one-game-required'};"
            "$p=$game[0];$sha=(Get-FileHash -LiteralPath $p.Path -Algorithm SHA256).Hash;"
            "if($sha -cne " + ps_literal(GAME_SHA) + "){throw 'rift-build-mismatch'};"
            "$exe=" + ps_literal(guest_exe) + ";"
            "$installed=Test-Path -LiteralPath $exe -PathType Leaf;"
            "if($installed -and (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
            + ps_literal(reader_sha) + "){throw 'guest-reader-hash-collision'};"
            "$data=[ordered]@{pid=[int]$p.Id;ticks=[long]$p.StartTime.ToUniversalTime().Ticks;"
            "sha=$sha;installed=[bool]$installed};"
            "$bytes=[Text.Encoding]::UTF8.GetBytes(($data|ConvertTo-Json -Compress));"
            "$f=[IO.File]::Open(" + ps_literal(guest_probe) + ",[IO.FileMode]::CreateNew,[IO.FileAccess]::Write);"
            "try{$f.Write($bytes,0,$bytes.Length)}finally{$f.Dispose()}"
        )
        staged_script(guest, preflight, output / "preflight.ps1",
                      settings["guestRoot"] + "\\preflight-location-pair-" + token + ".ps1", timeout=80)
        guest.copy_from_guest(guest_probe, output / "identity.json", timeout=50)
        with (output / "identity.json").open("rb") as stream:
            probe_raw = stream.read(8193)
        if not probe_raw or len(probe_raw) > 8192:
            raise ValueError("location-pair-probe-size-invalid")
        identity = decode_json(probe_raw.decode("utf-8-sig").encode("utf-8"))
        if not isinstance(identity, dict) or set(identity) != {"pid", "ticks", "sha", "installed"}:
            raise ValueError("location-pair-probe-invalid")
        pid, ticks = identity["pid"], identity["ticks"]
        if (not integer(pid, 1, 2147483647) or not integer(ticks, 1, 3155378975999999999)
                or identity.get("sha") != GAME_SHA or type(identity.get("installed")) is not bool):
            raise ValueError("guest-native-sampler-identity-invalid")
        if game_pin is not None and (pid != game_pin["processId"] or ticks != game_pin["processStartUtcTicks"]):
            raise ValueError("location-pair-game-pin-mismatch")
        installed = identity["installed"]
        if not installed:
            guest.run("copyFileFromHostToGuest", str(reader), guest_exe, timeout=180)
        launch = (
            "$ErrorActionPreference='Stop';"
            + guest_reader_check(guest_exe, reader_sha, hold_open=True)
            + "try{"
            "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
            "if($g.ProcessName -cne 'rift_x64' -or "
            "[long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks)
            + "){throw 'game-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
            + ps_literal(GAME_SHA) + "){throw 'rift-build-changed'};"
            "$out=" + ps_literal(guest_report) + ";"
            "if(Test-Path -LiteralPath $out){throw 'guest-report-exists'};"
            "& $exe sample-current-" + command + " --pid " + str(pid) + " --start-ticks " + str(ticks)
            + " --output $out | Out-Null;"
            "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};"
            "if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'}"
            "}finally{$readerGuard.Dispose()}"
        )
        try:
            staged_script(guest, launch, output / "capture.ps1",
                          guest_root + "\\capture-" + token + ".ps1", timeout=130)
        except SessionError as exc:
            if not str(exc).startswith("guest-command-timeout:runProgramInGuest"):
                raise
            # A vmrun timeout does not terminate or drain the guest child.
            uncertain = output / "execution-uncertain.json"
            receipt = {
                "schemaVersion": 2, "status": "guest-execution-uncertain",
                "guestDrainStatus": "unverified", "automaticRetry": False,
                "cooperativeExclusionReleaseAllowed": False,
                "lab": lab, "mode": mode, "vmIdentity": vm,
                "gameProcessId": pid, "gameProcessStartUtcTicks": str(ticks),
                "readerExecutableSha256": reader_sha, "guestExecutable": guest_exe,
                "guestReport": guest_report, "guestProcessId": None,
                "requiredAction": "Retain exclusion; verify the exact guest invocation has finished before retry or release.",
            }
            try:
                with uncertain.open("x", encoding="utf-8") as stream:
                    json.dump(receipt, stream, indent=2, allow_nan=False)
            except OSError:
                raise RuntimeError("location-pair-guest-execution-uncertain:no-drain-proof:no-retry:receipt-unavailable; retain exclusion") from None
            raise RuntimeError("location-pair-guest-execution-uncertain:no-drain-proof:no-retry; retain exclusion; " + str(uncertain)) from None
        guest.copy_from_guest(guest_report, output / "samples.json", timeout=70)
    with (output / "samples.json").open("rb") as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if not raw or len(raw) > MAX_REPORT_BYTES:
        raise ValueError("location-pair-report-size-invalid")
    parsed = decode_json(raw.decode("utf-8-sig").encode("utf-8"))
    metrics = validate_report(parsed, mode=mode, pid=pid, ticks=ticks)
    if digest(source_path) != source_sha or digest(reader) != reader_sha:
        raise ValueError("location-pair-source-changed")
    summary = {
        "schemaVersion": 2,
        "mode": mode,
        "sourceScriptSha256": source_sha,
        "cooperativeExclusionStatus": "unverified-not-acquired-by-wrapper",
        "liveReadiness": "unqualified",
        "status": "candidate-only",
        "lab": lab,
        "vmIdentity": vm,
        "gameProcessId": pid,
        "gameProcessStartUtcTicks": str(ticks),
        "gameSha256": GAME_SHA,
        "readerExecutableSha256": reader_sha,
        "guestReaderReused": installed,
        "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
        "sourceReport": str(output / "samples.json"),
        "metrics": metrics,
        "limitation": REFRESH_QUALIFICATION if mode == "refresh-branch" else "Candidate sources are sequential, not atomic; nullable zone/target remain unavailable; world identity, API correspondence, passive freshness and restart unverified."
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    parser.add_argument("--mode", choices=("location-context", "paired-position", "refresh-branch"), required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.lab, args.mode), allow_nan=False), flush=True)
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:160]}), flush=True)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
