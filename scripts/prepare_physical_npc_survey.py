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
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_nearby_units as nearby
from scripts import join_physical_nearby_npc_survey as join
from scripts import observe_physical
from scripts import physical_rift

SCHEMA = "rr2-npc-survey-preparation/1"


def require(condition, reason):
    if not condition:
        raise ValueError("npc-survey-prepare-" + reason)


def default_casting_directory():
    code, text = observe_physical._run([
        observe_physical.POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "[Environment]::GetFolderPath('MyDocuments')"
    ], timeout=10)
    documents = Path(text.strip())
    require(code == 0 and documents.is_absolute(), "provide-installed-casting-directory")
    return documents / "RIFT" / "Interface" / "AddOns" / "RiftReader2Casting"


def installed_survey(casting_dir):
    """Verify the active candidate deployment, never copy or reload the addon."""
    casting_dir = Path(casting_dir)
    toc = casting_dir / "RiftAddon.toc"
    lua = casting_dir / "npc_survey.lua"
    original = ROOT / "addon" / "RiftReader2NpcSurvey" / "survey.lua"
    require(all(p.is_file() and not p.is_symlink() for p in (toc, lua, original)),
            "installed-addon-files-unavailable")
    manifest = toc.read_text(encoding="utf-8-sig")
    identifier = any(
        line.strip() == 'Identifier = "RiftReader2Casting"'
        for line in manifest.splitlines())
    startup = re.search(
        r'(?m)^\s*RunOnStartup\s*=\s*\{([^}]*)\}', manifest)
    require(identifier and startup is not None
            and re.search(r'"npc_survey\.lua"', startup.group(1)) is not None,
            "npc-survey-not-listed-in-casting-manifest")
    installed = hashlib.sha256(lua.read_bytes()).hexdigest().upper()
    expected = hashlib.sha256(original.read_bytes()).hexdigest().upper()
    require(installed == expected, "installed-npc-survey-source-mismatch")
    return {"installedManifest": str(toc),
            "installedLua": str(lua),
            "installedLuaSha256": installed,
            "configurationVerified": True,
            "runningAddonLoaded": "unverified"}


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def prepare(host, pid, destination, *, radius=35.0, limit=12,
            casting_dir=None, nonce_factory=secrets.token_hex,
            capture_nearby=nearby.capture,
            select=physical_rift.select_physical,
            now=lambda: datetime.now(timezone.utc)):
    """Persist a fresh native source, exact IDs, and copyable activation commands."""
    require(physical_rift.valid_host_name(host)
            and type(pid) is int and 0 < pid < 2**31
            and type(limit) is int and 1 <= limit <= 12
            and type(radius) in (int, float) and not isinstance(radius, bool)
            and 0 < radius <= 50,
            "invalid-host-pid-or-bounds")
    addon = installed_survey(default_casting_directory() if casting_dir is None else casting_dir)
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
            limit=max(18, limit))
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
        active = [row["unitIdCandidate"] for row in checked["samples"]
                  if row["nameStatus"] == "available-candidate"]
        require(active, "no-named-unit-candidates")
        ids = active[:limit]
        require(len(set(ids)) == len(ids)
                and all(re.fullmatch(r"u[0-9A-F]{16}", x) for x in ids),
                "invalid-native-unit-ids")
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
        npc_path = output/"npc-api"
        joined_path = output/"joined-native-api.json"
        capture_command = ("& " + _quote(sys.executable)
            + " -B " + _quote("scripts/npc_survey_live.py")
            + " --expected-host " + _quote(host)
            + " --physical-pid " + str(pid)
            + " --session-id " + _quote(nonce)
            + " --unit-ids " + _quote(",".join(ids))
            + " --auto-map --max-attempts 5 --output " + _quote(npc_path))
        compare_command = ("& " + _quote(sys.executable)
            + " -B " + _quote("scripts/join_physical_nearby_npc_survey.py")
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
            "nativeJoinDeadlineUtc": (observed + timedelta(seconds=120)).isoformat(),
            "nonce": nonce, "unitIds": ids,
            "installedAddon": addon,
            "inGameBindCommand": command,
            "captureCommand": capture_command,
            "joinCommand": compare_command,
            "inputSent": False, "addonActivated": False,
            "combatAuthorized": False,
            "qualification": ("Installed Casting manifest and NPC survey Lua source "
                              "bytes match repository, not proof the running client "
                              "loaded or bound the addon. In-game bind is a separate "
                              "user action; capture must independently observe "
                              "advancing nonce/player-bound frames. Sequential "
                              "native/API names, level and relation remain candidates "
                              "without combat or movement authorization.")
        }
        dest = output/"plan.json"
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--radius", type=float, default=35)
    parser.add_argument("--max-ids", type=int, default=12)
    parser.add_argument("--installed-casting-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        path, report = prepare(args.expected_host, args.physical_pid,
                               args.output_dir, radius=args.radius,
                               limit=args.max_ids,
                               casting_dir=args.installed_casting_dir)
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
