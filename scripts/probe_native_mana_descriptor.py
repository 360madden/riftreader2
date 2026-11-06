"""Bracket the exact-build kind-3 Mana descriptor fingerprint on Lab 1.

This opt-in probe composes the existing full player/resource owner probe with a
tiny descriptor-slot snapshot.  It performs no game input, process write,
native getter call, addon action, service start, or broad memory scan.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path, PureWindowsPath
import re
import struct
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import probe_native_unit_manager as owner_probe
from scripts.inventory_passive_rift_sources import ps_literal


BUILD_SHA = owner_probe.BUILD_SHA
RECORD_VTABLE_RVA = 0x2A6ACD8
DESCRIPTOR_GETTER_RVA = 0x1CCB460
DESCRIPTOR_GLOBAL_RVA = 0x34D8990
DESCRIPTOR_VTABLE_RVA = 0x2A7C418
TYPE_GETTER_RVA = 0x1CF9F10
MANA_TYPE = 0x072A
MAX_REPORT_BYTES = 1024 * 1024
OWNER_PHASE_INITIATION_DEADLINE_SECONDS = 240
DESCRIPTOR_PHASE_INITIATION_DEADLINE_SECONDS = 120


def require_source_unchanged(path: Path, expected_sha: str) -> None:
    if owner_probe.sha(path.read_bytes()) != expected_sha:
        raise ValueError("mana-probe-source-changed-during-run")


def checked_mana_type(module: int, record_vtable: int, descriptor_getter: int,
                      descriptor_vtable: int, type_getter: int) -> int:
    expected = (module + RECORD_VTABLE_RVA, module + DESCRIPTOR_GETTER_RVA,
                module + DESCRIPTOR_VTABLE_RVA, module + TYPE_GETTER_RVA)
    if (type(module) is not int or module < 0x10000 or
            (record_vtable, descriptor_getter, descriptor_vtable, type_getter) != expected):
        raise ValueError("mana-type-fingerprint-mismatch")
    return MANA_TYPE


def owner_signature(report: dict) -> dict:
    if not isinstance(report, dict) or report.get("status") != "complete":
        raise ValueError("mana-owner-probe-incomplete")
    identity = report.get("identity")
    resource = report.get("resourceRecordCandidate")
    if (not isinstance(identity, dict) or identity.get("executableSha256") != BUILD_SHA or
            not isinstance(resource, dict) or resource.get("kind") != 3 or
            resource.get("name") != "mana" or resource.get("status") != "untyped-record-candidate" or
            resource.get("recordVtableRva") != f"0x{RECORD_VTABLE_RVA:X}" or
            resource.get("candidateDescriptorGetterRva") != f"0x{DESCRIPTOR_GETTER_RVA:X}" or
            resource.get("inputsStable") is not True or report.get("sourceStableAtPublish") is not True):
        raise ValueError("mana-owner-or-static-path-mismatch")
    fields = resource.get("fields")
    if (not isinstance(fields, dict) or fields.get("revisionConsistent") is not True or
            fields.get("expectedNativeResolverTypeUnverified") != "0x072A"):
        raise ValueError("mana-record-inputs-unavailable")
    required_strings = ("nativePlayerUnitId", "readerSha256", "workflowSha256", "probeSha256")
    if any(not isinstance(report.get(name), str) or not report[name] for name in required_strings):
        raise ValueError("mana-player-owner-missing")
    for name in ("resourceWrapper", "referenceSlot", "record"):
        if not isinstance(resource.get(name), str) or not re.fullmatch(r"0x[0-9A-F]+", resource[name]):
            raise ValueError("mana-record-owner-address-invalid")
    return {
        "identity": identity,
        "vmIdentity": report.get("vmIdentity"),
        "nativePlayerUnitId": report["nativePlayerUnitId"],
        "readerSha256": report["readerSha256"],
        "workflowSha256": report["workflowSha256"],
        "ownerProbeSha256": report["probeSha256"],
        "resourceWrapper": resource["resourceWrapper"],
        "referenceSlot": resource["referenceSlot"],
        "record": resource["record"],
        "recordVtableRva": resource["recordVtableRva"],
        "descriptorGetterRva": resource["candidateDescriptorGetterRva"],
    }


def _utc_timestamp(value: object, reason: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(reason)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError(reason) from None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(reason)
    return value, parsed


def owner_mutable_observation(report: dict) -> dict:
    """Extract one coherent cache epoch without treating it as owner identity."""
    resource = report.get("resourceRecordCandidate")
    fields = resource.get("fields") if isinstance(resource, dict) else None
    transition = resource.get("mutableTransition") if isinstance(resource, dict) else None
    interval = resource.get("observationIntervalUtc") if isinstance(resource, dict) else None
    if not isinstance(fields, dict) or not isinstance(transition, dict) or not isinstance(interval, dict):
        raise ValueError("mana-owner-mutable-observation-missing")
    integer_names = ("baseRaw", "maximumRaw", "rateRaw", "recordRevision", "wrapperRevision")
    if any(type(fields.get(name)) is not int or not -(1 << 31) <= fields[name] < (1 << 31)
           for name in integer_names):
        raise ValueError("mana-owner-mutable-integer-invalid")
    secondary_revision = transition.get("afterSecondaryRevision")
    if type(secondary_revision) is not int or not -(1 << 31) <= secondary_revision < (1 << 31):
        raise ValueError("mana-owner-secondary-revision-invalid")
    if (fields["recordRevision"] != fields["wrapperRevision"] or
            transition.get("afterFields") != fields):
        raise ValueError("mana-owner-mutable-revision-incoherent")
    wrapper_clock, game_clock = fields.get("wrapperClock"), resource.get("gameClock")
    if (type(wrapper_clock) not in (int, float) or type(game_clock) not in (int, float) or
            not math.isfinite(wrapper_clock) or not math.isfinite(game_clock)):
        raise ValueError("mana-owner-mutable-clock-invalid")
    started_raw, started = _utc_timestamp(
        interval.get("startedAtUtc"), "mana-owner-observation-time-invalid")
    completed_raw, completed = _utc_timestamp(
        interval.get("completedAtUtc"), "mana-owner-observation-time-invalid")
    observed_raw, observed = _utc_timestamp(
        resource.get("observedAtUtc"), "mana-owner-observation-time-invalid")
    if completed < started or observed != completed:
        raise ValueError("mana-owner-observation-interval-invalid")
    return {
        "observedAtUtc": observed_raw,
        "observationIntervalUtc": {"startedAtUtc": started_raw, "completedAtUtc": completed_raw},
        "fields": {name: fields[name] for name in integer_names},
        "wrapperClock": wrapper_clock,
        "gameClock": game_clock,
        "secondaryRevision": secondary_revision,
    }


def verify_phase_bindings(signature: dict, vm_identity: dict, reader_sha: str,
                          workflow_sha: str, owner_probe_sha: str) -> None:
    if (not isinstance(signature.get("vmIdentity"), dict) or not signature["vmIdentity"] or
            vm_identity != signature["vmIdentity"]):
        raise ValueError("mana-vm-epoch-changed-across-phases")
    if (reader_sha != signature.get("readerSha256") or
            workflow_sha != signature.get("workflowSha256") or
            owner_probe_sha != signature.get("ownerProbeSha256")):
        raise ValueError("mana-reader-workflow-or-owner-source-changed-across-phases")


def verify_owner_bracket(before: dict, after: dict) -> dict:
    first, second = owner_signature(before), owner_signature(after)
    if first != second:
        raise ValueError("mana-owner-or-process-changed-across-descriptor-read")
    before_observation = owner_mutable_observation(before)
    after_observation = owner_mutable_observation(after)
    before_completed = _utc_timestamp(
        before_observation["observationIntervalUtc"]["completedAtUtc"],
        "mana-owner-observation-time-invalid")[1]
    after_started = _utc_timestamp(
        after_observation["observationIntervalUtc"]["startedAtUtc"],
        "mana-owner-observation-time-invalid")[1]
    if after_started < before_completed:
        raise ValueError("mana-owner-observation-bracket-overlap")
    if (after_observation["fields"]["recordRevision"] <
            before_observation["fields"]["recordRevision"] or
            after_observation["secondaryRevision"] < before_observation["secondaryRevision"] or
            after_observation["wrapperClock"] < before_observation["wrapperClock"] or
            after_observation["gameClock"] < before_observation["gameClock"]):
        raise ValueError("mana-owner-mutable-epoch-backward")
    return {**first, "ownerBracket": {
        "status": ("unchanged-cache-values" if all(
            before_observation[name] == after_observation[name]
            for name in ("fields", "wrapperClock", "gameClock", "secondaryRevision"))
                   else "coherent-cache-epoch-advanced"),
        "before": before_observation,
        "after": after_observation,
        "gapSeconds": (after_started - before_completed).total_seconds(),
        "limitations": [
            "Owner probes and descriptor reads are sequential, not an atomic snapshot.",
            "Coherent nondecreasing revisions and clocks do not exclude an ABA transition.",
            "Cache evolution is retained as evidence and is not a semantic Mana-freshness claim.",
        ],
    }}


def verify_descriptor_bytes(module: int, captured: dict[int, bytes]) -> dict:
    required = {
        module + RECORD_VTABLE_RVA + 0x40: module + DESCRIPTOR_GETTER_RVA,
        module + DESCRIPTOR_GLOBAL_RVA: module + DESCRIPTOR_VTABLE_RVA,
        module + DESCRIPTOR_VTABLE_RVA + 0x08: module + TYPE_GETTER_RVA,
    }
    if set(captured) != set(required):
        raise ValueError("mana-descriptor-ranges-incomplete")
    values = {}
    for address, expected in required.items():
        raw = captured[address]
        if not isinstance(raw, bytes) or len(raw) != 8:
            raise ValueError("mana-descriptor-read-incomplete")
        value = struct.unpack("<Q", raw)[0]
        if value != expected:
            raise ValueError("mana-descriptor-live-slot-mismatch")
        values[address] = value
    type_code = checked_mana_type(
        module, module + RECORD_VTABLE_RVA, values[module + RECORD_VTABLE_RVA + 0x40],
        values[module + DESCRIPTOR_GLOBAL_RVA], values[module + DESCRIPTOR_VTABLE_RVA + 0x08])
    return {"typeCode": f"0x{type_code:04X}",
            "recordVtableRva": f"0x{RECORD_VTABLE_RVA:X}",
            "descriptorGetterRva": f"0x{DESCRIPTOR_GETTER_RVA:X}",
            "descriptorGlobalRva": f"0x{DESCRIPTOR_GLOBAL_RVA:X}",
            "descriptorVtableRva": f"0x{DESCRIPTOR_VTABLE_RVA:X}",
            "typeGetterRva": f"0x{TYPE_GETTER_RVA:X}"}


def run(lab: str = "lab1") -> dict:
    if lab != "lab1":
        raise ValueError("mana-descriptor-probe-requires-kind-three-lab1")
    probe_path = Path(__file__)
    owner_probe_path = Path(owner_probe.__file__)
    probe_sha = owner_probe.sha(probe_path.read_bytes())
    owner_probe_sha = owner_probe.sha(owner_probe_path.read_bytes())
    require_source_unchanged(probe_path, probe_sha)
    require_source_unchanged(owner_probe_path, owner_probe_sha)
    before = owner_probe.run(lab, resource_record=True)
    require_source_unchanged(probe_path, probe_sha)
    require_source_unchanged(owner_probe_path, owner_probe_sha)
    signature = owner_signature(before)
    identity = signature["identity"]
    module = identity["moduleBaseAddress"]

    from scripts.lab_codex import LabCodex
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm_identity = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    folder = ROOT / "artifacts" / "native-mana-descriptor" / lab / token
    folder.mkdir(parents=True, exist_ok=False)
    workflow_path = ROOT / "artifacts" / "control-fleet-live" / lab / "workflow.json"
    workflow_raw = workflow_path.read_bytes()
    workflow = json.loads(workflow_raw)
    reader = str(PureWindowsPath(workflow["guestDirectory"]) / "RiftReader2.Live.exe")
    reader_sha = workflow["readerSha256"]
    if not re.fullmatch(r"[0-9A-F]{64}", reader_sha):
        raise ValueError("invalid-reader-sha")
    workflow_sha = owner_probe.sha(workflow_raw)
    verify_phase_bindings(signature, vm_identity, reader_sha, workflow_sha, owner_probe_sha)
    require_source_unchanged(probe_path, probe_sha)
    require_source_unchanged(owner_probe_path, owner_probe_sha)
    prefix = settings["guestRoot"] + "\\mana-descriptor-" + token
    deadline = time.monotonic() + DESCRIPTOR_PHASE_INITIATION_DEADLINE_SECONDS
    evidence = {}

    with api._session(config, settings, vm_identity, folder) as guest:
        def native(mode: str, name: str, request: dict | None = None) -> dict:
            if time.monotonic() >= deadline:
                raise ValueError("mana-descriptor-operation-budget-exceeded")
            output = folder / (name + ".json")
            guest_output = prefix + "-" + name + ".json"
            command = ("$ErrorActionPreference='Stop';$e=" + ps_literal(reader) + ";"
                       "if(!(Test-Path -LiteralPath $e -PathType Leaf)){throw 'reader-missing'};"
                       "if((Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -ne " +
                       ps_literal(reader_sha) + "){throw 'reader-sha-mismatch'};"
                       "if(Test-Path -LiteralPath " + ps_literal(guest_output) + "){throw 'output-exists'};")
            arguments = ""
            if request is not None:
                request_path = folder / (name + "-request.json")
                payload = owner_probe.encoded(request)
                with request_path.open("xb") as stream:
                    stream.write(payload)
                guest_request = prefix + "-" + name + "-request.json"
                guest.run("copyFileFromHostToGuest", str(request_path), guest_request)
                command += ("if((Get-FileHash -LiteralPath " + ps_literal(guest_request) +
                            ").Hash -ne " + ps_literal(owner_probe.sha(payload)) +
                            "){throw 'request-sha-mismatch'};")
                arguments = " --request " + ps_literal(guest_request)
                evidence[request_path.name] = owner_probe.sha(payload)
            command += ("& $e " + mode + arguments + " --output " + ps_literal(guest_output) +
                        " | Out-Null;if($LASTEXITCODE -notin @(0,3)){throw 'native-command-failed'}")
            guest.powershell(command, timeout=60)
            guest.copy_from_guest(guest_output, output, timeout=60)
            raw = output.read_bytes()
            if not raw or len(raw) > MAX_REPORT_BYTES:
                raise ValueError("mana-descriptor-report-size-invalid")
            evidence[output.name] = owner_probe.sha(raw)
            return json.loads(raw.decode("utf-8-sig"))

        inspect_before = native("inspect-native", "inspect-before")
        current_identity, target = owner_probe.inspection_identity(inspect_before)
        if current_identity != identity:
            raise ValueError("mana-process-epoch-changed-before-descriptor-read")
        request = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot-request/1",
                   "target": target, "maxDurationMilliseconds": 10000,
                   "ranges": [{"addressKind": "module-relative-rva", "address": f"0x{rva:X}",
                               "byteLength": 8} for rva in
                              (RECORD_VTABLE_RVA + 0x40, DESCRIPTOR_GLOBAL_RVA,
                               DESCRIPTOR_VTABLE_RVA + 0x08)]}
        first = owner_probe.snapshot_bytes(native("snapshot-native", "descriptor-before", request),
                                            request, identity)
        second = owner_probe.snapshot_bytes(native("snapshot-native", "descriptor-after", request),
                                             request, identity)
        if first != second:
            raise ValueError("mana-descriptor-slots-changed-during-capture")
        fingerprint = verify_descriptor_bytes(module, first)
        inspect_after = native("inspect-native", "inspect-after")
        after_identity, _ = owner_probe.inspection_identity(inspect_after)
        if after_identity != identity:
            raise ValueError("mana-process-epoch-changed-after-descriptor-read")

    require_source_unchanged(probe_path, probe_sha)
    require_source_unchanged(owner_probe_path, owner_probe_sha)
    after = owner_probe.run(lab, resource_record=True)
    require_source_unchanged(probe_path, probe_sha)
    require_source_unchanged(owner_probe_path, owner_probe_sha)
    stable_owner = verify_owner_bracket(before, after)
    verify_phase_bindings(stable_owner, vm_identity, reader_sha, workflow_sha, owner_probe_sha)
    before_review = Path(before["output"]) / "review.json"
    after_review = Path(after["output"]) / "review.json"
    result = {"schemaVersion": 1, "status": "type-checked-record-candidate", "lab": lab,
              "identity": identity, "nativePlayerUnitId": stable_owner["nativePlayerUnitId"],
              "fingerprint": fingerprint, "beforeOwnerEvidence": before["output"],
              "descriptorEvidence": str(folder), "afterOwnerEvidence": after["output"],
              "ownerBracket": stable_owner["ownerBracket"],
              "probeSha256": probe_sha,
              "ownerProbeSha256": owner_probe_sha,
              "readerSha256": reader_sha,
              "workflowSha256": workflow_sha,
              "beforeOwnerReviewSha256": owner_probe.sha(before_review.read_bytes()),
              "afterOwnerReviewSha256": owner_probe.sha(after_review.read_bytes()),
              "evidence": evidence,
              "qualification": "exact-build live descriptor candidate; semantics/freshness/restart-unverified",
              "phaseInitiationDeadlines": {
                  "ownerBeforeSeconds": OWNER_PHASE_INITIATION_DEADLINE_SECONDS,
                  "descriptorSeconds": DESCRIPTOR_PHASE_INITIATION_DEADLINE_SECONDS,
                  "ownerAfterSeconds": OWNER_PHASE_INITIATION_DEADLINE_SECONDS,
                  "semantics": ("checked before each operation; an admitted operation may finish "
                                "under its own bounded timeout; not a hard phase or overall wall-time")},
              "limitations": ["Sequential reads do not exclude ABA changes.",
                              "No independent Lua/UI Mana change was observed.",
                              "No native function was invoked and no process memory was written."]}
    output = folder / "review.json"
    require_source_unchanged(probe_path, probe_sha)
    require_source_unchanged(owner_probe_path, owner_probe_sha)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    result["output"] = str(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1",), default="lab1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.lab), indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:200]}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
