"""Prepare one nonce-bound, read-only NPC survey from fresh native nearby data.

No game input is sent. The one in-game /rr2survey bind command is printed;
subsequent native/Lua acquisitions still require fresh exact-process verification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_nearby_units as nearby
from scripts import join_physical_nearby_npc_survey as join
from scripts import observe_physical
from scripts import physical_rift

SCHEMA = "rr2-npc-survey-preparation/2"
LEGACY_SCHEMA = "rr2-npc-survey-preparation/1"
ADDON_EVIDENCE = "addon-evidence"
MANIFEST_NAME = "RiftAddon.toc"
# Retained plans use this filename regardless of the installed addon's layout.
MODULE_NAME = "npc_survey.lua"
SURVEY_ADDON_ID = "RiftReader2NpcSurvey"
CASTING_ADDON_ID = "RiftReader2Casting"
INSTALLED_MODULES = {SURVEY_ADDON_ID: "survey.lua", CASTING_ADDON_ID: MODULE_NAME}


def require(condition, reason):
    if not condition:
        raise ValueError("npc-survey-prepare-" + reason)


def _local_survey_directories():
    try:
        addons = observe_physical.local_rift_addons_root()
    except ValueError as error:
        raise ValueError(f"npc-survey-prepare-provide-installed-addon-directory: {error}") from error
    manifests = (addons / identifier / MANIFEST_NAME for identifier in INSTALLED_MODULES)
    return [path.parent for path in manifests if path.exists() or path.is_symlink()]


def _manifest_survey_module(raw):
    manifest = raw.decode("utf-8-sig")
    manifest = re.sub(r'"[^"\r\n]*"|--[^\r\n]*',
                      lambda token: "" if token[0].startswith("--") else token[0], manifest)
    identifiers = re.findall(r'(?m)^[ \t]*Identifier[ \t]*=[ \t]*"([^"\r\n]+)"', manifest)
    startup = re.findall(r'(?m)^[ \t]*RunOnStartup[ \t]*=\s*\{([^}]*)\}', manifest)
    require(len(identifiers) == 1 and identifiers[0] in INSTALLED_MODULES and len(startup) == 1,
            "npc-survey-not-listed-in-addon-manifest")
    identifier = identifiers[0]
    module_name = INSTALLED_MODULES[identifier]
    occurrences = re.findall(r'"([^"\r\n]+)"', startup[0]).count(module_name)
    require(occurrences <= 1, "npc-survey-listed-more-than-once")
    return identifier, module_name if occurrences == 1 else None


def _asset(path, limit):
    require(path.is_file() and not path.is_symlink(), "addon-source-unavailable")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, "addon-source-size-invalid")
    return raw, hashlib.sha256(raw).hexdigest().upper()


def installed_survey(addon_dir=None):
    """Read the installed configuration and confirm the module matches this checkout."""
    directories = _local_survey_directories() if addon_dir is None else [Path(addon_dir)]
    require(directories, "addon-source-unavailable")
    installations = []
    for directory in directories:
        toc = directory / MANIFEST_NAME
        manifest, manifest_sha = _asset(toc, 64 * 1024)
        identifier, module_name = _manifest_survey_module(manifest)
        if addon_dir is None:
            require(directory.name == identifier, "addon-directory-identifier-mismatch")
        if module_name is not None:
            installations.append((identifier, toc, directory / module_name, manifest, manifest_sha))
    require(len(installations) <= 1, "npc-survey-multiple-configured-addons")
    require(installations, "npc-survey-not-listed-in-addon-manifest")
    identifier, toc, lua, manifest, manifest_sha = installations[0]
    original = ROOT / "addon" / SURVEY_ADDON_ID / INSTALLED_MODULES[SURVEY_ADDON_ID]
    module, installed = _asset(lua, 256 * 1024)
    _, expected = _asset(original, 256 * 1024)
    require(installed == expected, "installed-npc-survey-source-mismatch")
    return {"installedManifest": str(toc),
            "installedLua": str(lua),
            "installedAddonId": identifier,
            "installedManifestSha256": manifest_sha,
            "installedLuaSha256": installed,
            "configurationVerified": True,
            "runningAddonLoaded": "unverified"}, manifest, module


def _named_unit_ids(report, limit):
    ids = [row["unitIdCandidate"] for row in report["samples"]
           if row["nameStatus"] == "available-candidate"][:limit]
    require(ids, "no-named-unit-candidates")
    require(len(set(ids)) == len(ids) and all(re.fullmatch(r"u[0-9A-F]{16}", x) for x in ids),
            "invalid-native-unit-ids")
    return ids


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def prepare(host, pid, destination, *, radius=35.0, limit=12, include_levels=False,
            casting_dir=None, native_reader=None, nonce_factory=secrets.token_hex,
            capture_nearby=nearby.capture,
            select=physical_rift.select_physical,
            now=lambda: datetime.now(timezone.utc)):
    """Persist a fresh native source, exact IDs, and copyable activation commands."""
    require(physical_rift.valid_host_name(host)
            and type(pid) is int and 0 < pid < 2**31
            and type(limit) is int and 1 <= limit <= 12
            and type(include_levels) is bool
            and type(radius) in (int, float) and not isinstance(radius, bool)
            and 0 < radius <= 50,
            "invalid-host-pid-or-bounds")
    require(physical_rift.is_local_host(host), "wrong-host")
    native_reader = physical_rift._native_reader_path(native_reader)
    require(native_reader.is_file(), "native-reader-not-built")
    addon, manifest, module = installed_survey(casting_dir)
    output = Path(destination)
    if not output.is_absolute():
        output = ROOT / output
    require(not output.exists() and not output.is_symlink()
            and output.parent.is_dir(),
            "new-output-directory-required")
    output.mkdir()
    try:
        # Lookup a wider bounded native name batch; bind only the first
        # `limit` named IDs. Nearby position candidates may include cache misses.
        nearby_path, native_report = capture_nearby(
            host, pid, output/"native", radius=radius,
            limit=max(18, limit), include_levels=include_levels, native_reader=native_reader)
        checked, native_sha, (native_started, native_at) = join.original_native_nearby(nearby_path)
        require(native_report == checked, "native-summary-changed")
        identity = checked["process"]
        selected = select(host, pid)
        owner = selected.get("target", {})
        actual_host = owner.get("hostName")
        require(selected.get("status") == "ready"
                and owner.get("processId") == pid
                and physical_rift.valid_host_name(actual_host)
                and actual_host.casefold() == host.casefold()
                and checked.get("host") == actual_host
                and str(identity.get("processStartUtcTicks")) ==
                    str(owner.get("processStartUtcTicks"))
                and str(identity.get("executableSha256", "")).casefold() ==
                    str(owner.get("executableSha256", "")).casefold(),
                "physical-process-changed")
        host = actual_host
        ids = _named_unit_ids(checked, limit)
        nonce = nonce_factory(16)
        require(type(nonce) is str
                and re.fullmatch(r"[0-9a-f]{32}", nonce),
                "invalid-nonce")
        created = now()
        observed = datetime.fromisoformat(native_started.replace("Z", "+00:00"))
        require(created.tzinfo is not None and observed.tzinfo is not None
                and 0 <= (created-observed).total_seconds() <= 30,
                "native-observation-no-longer-fresh")
        command = "/rr2survey bind " + nonce + " " + ",".join(ids)
        require(len(command) <= 270, "in-game-command-too-long")
        capture_deadline = (observed + timedelta(seconds=120)).isoformat()
        dest = output/"plan.json"
        npc_path = output/"npc-api"
        joined_path = output/"joined-native-api.json"
        capture_command = ("& " + _quote(sys.executable)
            + " -B " + _quote(ROOT / "scripts/npc_survey_live.py")
            + " --bind-plan " + _quote(dest)
            + " --output " + _quote(npc_path)
            + " --native-reader " + _quote(native_reader))
        compare_command = ("& " + _quote(sys.executable)
            + " -B " + _quote(ROOT / "scripts/join_physical_nearby_npc_survey.py")
            + " --nearby " + _quote(nearby_path)
            + " --npc-survey " + _quote(npc_path/"result.json")
            + " --max-gap-seconds 120 --position-tolerance 5"
            + " --output " + _quote(joined_path))
        report = {
            "schema": SCHEMA, "status": "prepared-not-activated",
            "ownerHost": host, "processId": pid,
            "processStartUtcTicks": str(identity["processStartUtcTicks"]),
            "executableSha256": str(identity["executableSha256"]).upper(),
            "nativeSourceSha256": native_sha,
            "nativePositionCaptureStartedAtUtc": native_started,
            "nativeSampledAtUtc": native_at,
            "preparedAtUtc": created.isoformat(),
            "nativeJoinDeadlineUtc": capture_deadline,
            "nonce": nonce, "unitIds": ids,
            "installedAddon": addon,
            "inGameBindCommand": command,
            "captureCommand": capture_command,
            "joinCommand": compare_command,
            "inputSent": False, "addonActivated": False,
            "combatAuthorized": False,
            "qualification": ("The installed manifest lists the verified NPC survey Lua source. "
                              "After a manual bind, advancing nonce/player-bound frames confirm "
                              "publication in the running client. Sequential "
                              "native/API names, level and relation remain candidates "
                              "without combat or movement authorization.")
        }
        evidence = output / ADDON_EVIDENCE
        evidence.mkdir()
        for name, raw in ((MANIFEST_NAME, manifest), (MODULE_NAME, module)):
            with (evidence / name).open("xb") as stream:
                stream.write(raw)
        with dest.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return dest, report
    except Exception as exc:
        with (output/"failure.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump({"schema": SCHEMA, "status": "blocked",
                       "reason": str(exc)[:240], "inputSent": False},
                      stream, indent=2)
            stream.write("\n")
        raise


def replay_plan(path):
    """Audit saved preparation evidence without reading the current game or addon install."""
    path = Path(path)
    plan, digest = nearby.read_hashed_json(path, 256 * 1024)
    require(plan.get("schema") in (SCHEMA, LEGACY_SCHEMA)
            and plan.get("status") == "prepared-not-activated"
            and plan.get("inputSent") is False and plan.get("addonActivated") is False
            and plan.get("combatAuthorized") is False,
            "plan-schema-or-status-invalid")
    native, native_sha, (started, completed) = join.original_native_nearby(path.parent / "native/nearby-report.json")
    owner = native["process"]
    require(physical_rift.valid_host_name(plan.get("ownerHost")) and plan["ownerHost"] == native.get("host")
            and type(plan.get("processId")) is int and plan["processId"] == owner["processId"]
            and plan.get("processStartUtcTicks") == str(owner["processStartUtcTicks"])
            and plan.get("executableSha256") == owner["executableSha256"].upper()
            and plan.get("nativeSourceSha256") == native_sha
            and plan.get("nativePositionCaptureStartedAtUtc") == started
            and plan.get("nativeSampledAtUtc") == completed,
            "plan-native-evidence-mismatch")
    observed = datetime.fromisoformat(started.replace("Z", "+00:00"))
    prepared_at, deadline_at = plan.get("preparedAtUtc"), plan.get("nativeJoinDeadlineUtc")
    require(isinstance(prepared_at, str) and isinstance(deadline_at, str), "plan-time-mismatch")
    prepared = datetime.fromisoformat(prepared_at.replace("Z", "+00:00"))
    deadline = datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
    require(prepared.utcoffset() == timedelta(0) and deadline.utcoffset() == timedelta(0)
            and 0 <= (prepared - observed).total_seconds() <= 30
            and deadline == observed + timedelta(seconds=120), "plan-time-mismatch")

    ids = plan.get("unitIds")
    nonce = plan.get("nonce")
    require(isinstance(ids, list) and 1 <= len(ids) <= 12 and ids == _named_unit_ids(native, len(ids)),
            "plan-unit-selection-mismatch")
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce)
            and plan.get("inGameBindCommand") == "/rr2survey bind " + nonce + " " + ",".join(ids),
            "plan-bind-command-mismatch")

    addon = plan.get("installedAddon")
    require(isinstance(addon, dict) and addon.get("configurationVerified") is True
            and addon.get("runningAddonLoaded") == "unverified"
            and isinstance(addon.get("installedLuaSha256"), str)
            and re.fullmatch(r"[0-9A-F]{64}", addon["installedLuaSha256"]), "plan-addon-metadata-invalid")
    addon_status = "recorded-only"
    if plan["schema"] == SCHEMA:
        evidence = path.parent / ADDON_EVIDENCE
        manifest, manifest_sha = _asset(evidence / MANIFEST_NAME, 64 * 1024)
        _, module_sha = _asset(evidence / MODULE_NAME, 256 * 1024)
        require(addon.get("installedManifestSha256") == manifest_sha
                and addon["installedLuaSha256"] == module_sha, "plan-addon-evidence-mismatch")
        identifier, module_name = _manifest_survey_module(manifest)
        require(module_name is not None and addon.get("installedAddonId", identifier) == identifier,
                "plan-addon-evidence-mismatch")
        addon_status = "retained-bytes-verified"
    planned = set(ids)
    return {"status": "replayed-plan-candidate", "planSha256": digest,
            "host": plan["ownerHost"], "process": owner, "nativeSourceSha256": native_sha,
            "nonce": nonce, "playerKey": native["selfKey"],
            "unitIds": ids, "unitIdCount": len(ids),
            "nativeLevelCandidateCount": sum(row["unitIdCandidate"] in planned
                                             and row.get("numericLevelCandidate") is not None for row in native["samples"]),
            "addonEvidenceStatus": addon_status, "nativeJoinDeadlineUtc": plan["nativeJoinDeadlineUtc"],
            "inputSent": False, "addonActivated": False, "combatAuthorized": False}


def _check_dependencies(host, casting_dir, native_reader, *, include_levels=False):
    kinds = ("unit-positions", "unit-names", "player-context")
    if include_levels:
        kinds += ("unit-levels",)
    reader = physical_rift.check_native_reader(host, native_reader, kind=kinds)
    try:
        addon, _, _ = installed_survey(casting_dir)
        addon["status"] = "addon-configuration-ready"
    except (OSError, ValueError) as exc:
        addon = {"status": "blocked", "reason": str(exc)[:240]}
    ready = reader["status"] == "ready" and addon["status"] == "addon-configuration-ready"
    return {"status": "survey-dependencies-ready" if ready else "blocked",
            "ownerHost": host, "nativeReader": reader, "installedAddon": addon, "inputSent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay-plan", type=Path, help="validate a saved plan and its retained sources offline")
    mode.add_argument("--check-addon", action="store_true",
                      help="verify installed NPC survey files without selecting a game process")
    mode.add_argument("--check-dependencies", action="store_true",
                      help="check the installed NPC addon and native reader without selecting a game process")
    parser.add_argument("--expected-host")
    parser.add_argument("--physical-pid", type=int)
    parser.add_argument("--radius", type=float, default=35)
    parser.add_argument("--max-ids", type=int, default=12)
    parser.add_argument("--include-levels", action="store_true",
                        help="collect native numeric-level candidates for NPC comparison")
    parser.add_argument("--installed-addon-dir", "--installed-casting-dir", type=Path,
                        help="local standalone NPC survey or Casting addon directory")
    parser.add_argument("--native-reader", type=Path, help="absolute path to a local published reader")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    acquisition_requested = (args.physical_pid is not None or args.output_dir is not None
                             or args.radius != 35 or args.max_ids != 12)
    reader_options = args.native_reader is not None or args.include_levels
    if args.replay_plan:
        if (acquisition_requested or reader_options or args.expected_host is not None
                or args.installed_addon_dir is not None):
            parser.error("--replay-plan uses only the saved plan and its sibling evidence files")
    elif args.check_addon:
        if acquisition_requested or reader_options:
            parser.error("--check-addon accepts only --expected-host and --installed-addon-dir")
    elif args.check_dependencies:
        if acquisition_requested:
            parser.error("--check-dependencies does not accept a game PID, output directory, radius or ID limit")
    elif args.expected_host is None or args.physical_pid is None or args.output_dir is None:
        parser.error("supply --expected-host, --physical-pid and --output-dir, or use a check or replay mode")
    try:
        if args.replay_plan:
            print(json.dumps(replay_plan(args.replay_plan), allow_nan=False))
            return 0
        if args.check_addon or args.check_dependencies:
            host = socket.gethostname()
            require(physical_rift.is_local_host(host if args.expected_host is None else args.expected_host),
                    "wrong-host")
            if args.check_dependencies:
                dependencies = _check_dependencies(host, args.installed_addon_dir, args.native_reader,
                                                   include_levels=args.include_levels)
                print(json.dumps(dependencies))
                return 0 if dependencies["status"] == "survey-dependencies-ready" else 2
            addon, _, _ = installed_survey(args.installed_addon_dir)
            print(json.dumps(dict(addon, status="addon-configuration-ready", ownerHost=host, inputSent=False)))
            return 0
        path, report = prepare(args.expected_host, args.physical_pid,
                               args.output_dir, radius=args.radius,
                               limit=args.max_ids, include_levels=args.include_levels,
                               casting_dir=args.installed_addon_dir, native_reader=args.native_reader)
    except (ValueError, TypeError, OSError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": str(exc)[:240],
                          "inputSent": False}))
        return 2
    print(json.dumps({"status": report["status"],
                      "unitIdCount": len(report["unitIds"]),
                      "inGameBindCommand": report["inGameBindCommand"],
                      "captureCommand": report["captureCommand"],
                      "joinCommand": report["joinCommand"],
                      "plan": str(path), "inputSent": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
