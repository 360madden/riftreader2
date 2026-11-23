"""Compare nine installed ApiAtlas code files with a local source folder, read-only.

Installed files are read, never modified. Pinned OneDrive files may hydrate.
Historical VMware targets are available through explicit selection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import uuid

from rift_addon_inventory import GUEST_ADDONS, HOST_PS, observe_physical

ROOT = Path(__file__).resolve().parents[1]
GUEST_SCRIPT = ROOT / "scripts" / "rift_addon_hash_guest.ps1"
GUEST_LOCAL = r"C:\Users\mrkoo\AppData\Local\RiftReader2\addon-hash"
FILES = (
    "RiftAddon.toc", "Version.lua", "Bootstrap.lua", "Theme.lua",
    "Collector.lua", "Navigation.lua", "Presentation.lua", "UI.lua", "Public.lua",
)
MAX_FILE = 131072
MAX_TOTAL = 262144


class HashError(RuntimeError):
    pass


def _source_path(override: Path | None = None) -> Path:
    if override is not None:
        return override
    configured = os.environ.get("RR2_APIATLAS_SOURCE")
    return Path(configured) if configured else ROOT.parent / "API Atlas/addon/ApiAtlas"


def _source_git_head(source: Path) -> str | None:
    """Report a checkout revision only when Git tracks the compared files."""
    git = ["git", "-C", str(source)]
    try:
        tracked = subprocess.run([*git, "ls-files", "--error-unmatch", "--", *FILES],
                                 capture_output=True, encoding="utf-8", errors="replace", timeout=15, check=False)
        if tracked.returncode != 0:
            return None
        head = subprocess.run([*git, "rev-parse", "--verify", "HEAD"],
                              capture_output=True, encoding="utf-8", errors="replace", timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return head.stdout.strip() if head.returncode == 0 else None


def source_manifest(source: Path | None = None) -> dict:
    source = _source_path(source)
    files, total = {}, 0
    for name in FILES:
        path = source / name
        if not path.is_file() or path.is_symlink():
            raise HashError("invalid-source:" + name)
        size = path.stat().st_size
        total += size
        if not 0 < size <= MAX_FILE or total > MAX_TOTAL:
            raise HashError("source-size-limit:" + name)
        files[name] = {"bytes": size,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper()}
    return {"source": str(source), "sourceGitHead": _source_git_head(source), "files": files}


def validate_report(data: dict, target: str) -> dict:
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise HashError("invalid-schema:" + target)
    if data.get("method") != "sha256-read-only" or data.get("addon") != "ApiAtlas":
        raise HashError("invalid-method:" + target)
    machine = data.get("machine")
    if not isinstance(machine, str) or not machine:
        raise HashError("missing-machine:" + target)
    if target in ("lab1", "lab2") and machine.casefold() != ("RIFT-LAB-" + target[-1]).casefold():
        raise HashError("wrong-guest-machine:" + target)
    if type(data.get("complete")) is not bool or not isinstance(data.get("timestampUtc"), str):
        raise HashError("invalid-provenance:" + target)
    records = data.get("files")
    if records == [] and not data["complete"] and isinstance(data.get("error"), str):
        return data
    if not isinstance(records, list) or len(records) != len(FILES):
        raise HashError("invalid-count:" + target)
    if [r.get("name") for r in records if isinstance(r, dict)] != list(FILES):
        raise HashError("invalid-order:" + target)
    for row in records:
        if row.get("status") not in ("hashed", "missing", "unsafe", "too-large",
                                     "changed-during-read", "read-error"):
            raise HashError("invalid-status:" + target)
        sha = row.get("sha256")
        if row["status"] == "hashed":
            if not isinstance(sha, str) or not re.fullmatch("[0-9A-F]{64}", sha):
                raise HashError("invalid-hash:" + target)
        elif sha is not None:
            raise HashError("unexpected-hash:" + target)
    if data["complete"] != all(row["status"] == "hashed" for row in records):
        raise HashError("invalid-completeness:" + target)
    return data


def read_report(path: Path, target: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise HashError("invalid-report:" + target) from error
    return validate_report(data, target)


def run_pc(run_root: Path, folder: Path | None = None) -> dict:
    addon = (observe_physical.local_rift_addons_root() / "ApiAtlas"
             if folder is None else folder.absolute())
    if addon.drive.startswith(("\\", "/")):
        raise HashError("pc-addon-folder-must-be-local")
    report = run_root / "pc.json"
    args = [HOST_PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(GUEST_SCRIPT), "-AddonDirectory", str(addon),
            "-ReportPath", str(report)]
    job = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)
    if job.returncode:
        raise HashError("pc-helper-exit:" + str(job.returncode))
    result = read_report(report, "pc")
    if result["machine"].casefold() != socket.gethostname().casefold():
        raise HashError("unexpected-local-machine")
    addon_directory = result.get("addonDirectory")
    if not isinstance(addon_directory, str) or Path(addon_directory) != addon:
        raise HashError("unexpected-local-addon-directory")
    return result


def run_lab(target: str, run_root: Path) -> dict:
    from lab_codex import LabCodex
    from vmware_guest_session import POWERSHELL

    lab = LabCodex()
    _, _, config, settings = lab._configuration(target)
    doctor = lab.run_root / ".doctor"
    native = lab._native(config, settings, doctor)
    identity = lab.collect_identity(native)
    work = GUEST_LOCAL + "\\hash-" + uuid.uuid4().hex
    guest_script = work + r"\rift_addon_hash_guest.ps1"
    guest_report = work + r"\report.json"
    output = run_root / (target + ".json")
    # _session checks the correct VM-specific cached credentials on each entry.
    with lab._session(config, settings, identity, doctor) as guest:
        guest.powershell("$ErrorActionPreference='Stop';[void](New-Item -ItemType Directory "
                         "-Path '" + work + "' -Force)", timeout=90)
        guest.run("copyFileFromHostToGuest", str(GUEST_SCRIPT), guest_script, timeout=90)
        guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                  "-ExecutionPolicy", "Bypass", "-File", guest_script,
                  "-AddonDirectory", GUEST_ADDONS + r"\ApiAtlas",
                  "-ReportPath", guest_report, timeout=150)
        guest.copy_from_guest(guest_report, output, timeout=90)
    return read_report(output, target)


def compare(source: dict, results: dict) -> dict:
    rows = []
    for name in FILES:
        hashes = {}
        for target in ("pc", "lab1", "lab2"):
            report = results.get(target, {})
            row = next((r for r in report.get("files", []) if r["name"] == name), None)
            hashes[target] = row["sha256"] if row and row["status"] == "hashed" else None
        unique = set(h for h in hashes.values() if h)
        rows.append({
            "file": name,
            "sourceBytes": source["files"][name]["bytes"],
            "matchesSource": {t: (h == source["files"][name]["sha256"]) if h else None
                              for t, h in hashes.items()},
            "threeMachineParity": len(unique) == 1 and all(hashes.values()),
            "distinctInstalledHashes": len(unique),
        })
    return {"files": rows,
            "allCheckedTargetsMatchSource": bool(results) and all(
                result.get("complete") is True and all(
                    row["matchesSource"].get(target) is True for row in rows)
                for target, result in results.items()),
            "allMachinesMatchSource": all(row["threeMachineParity"] and
                                         all(row["matchesSource"].values()) for row in rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("pc", "lab1", "lab2", "all"), default="pc")
    parser.add_argument("--expected-host", help="Verify the requested Windows hostname for the pc target")
    parser.add_argument("--pc-folder", type=Path, help="Override the detected local ApiAtlas addon folder")
    parser.add_argument("--source", type=Path,
                        help="Local ApiAtlas source folder containing RiftAddon.toc "
                             "(default: RR2_APIATLAS_SOURCE or a sibling API Atlas checkout)")
    args = parser.parse_args(argv)
    if args.expected_host is not None:
        if args.target != "pc" or not observe_physical.valid_host_name(args.expected_host):
            parser.error("--expected-host requires the pc target and a valid Windows hostname")
        actual_host = socket.gethostname()
        if actual_host.casefold() != args.expected_host.casefold():
            print(json.dumps({"targets": {"pc": {"complete": False, "error": "host-mismatch",
                                                "machine": actual_host, "expectedHost": args.expected_host}}}))
            return 2

    source_path = _source_path(args.source)
    try:
        source_folder = source_path.absolute()
        if source_folder.drive.startswith(("\\", "/")):
            raise HashError("source-folder-must-be-local")
        source = source_manifest(source_folder)
    except (HashError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"source": str(source_path), "error": str(error)}))
        return 2
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_root = ROOT / "artifacts" / "addon-hash" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    results = {}
    for target in (("pc", "lab1", "lab2") if args.target == "all" else (args.target,)):
        try:
            result = run_pc(run_root, args.pc_folder) if target == "pc" else run_lab(target, run_root)
            result["report"] = str(run_root / (target + ".json"))
            results[target] = result
        except Exception as error:
            results[target] = {"complete": False, "error": str(error)}
    comparison = compare(source, results)
    summary = {"schemaVersion": 1, "method": "sha256-read-only",
               "source": source, "reportRoot": str(run_root),
               "targets": results, "comparison": comparison,
               "unverified": ["ApiAtlas/fonts subtree", "live game-loaded Lua"],
               "note": "No addon modifications; pinned OneDrive files may hydrate when hashed."}
    (run_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                            encoding="utf-8")
    print(json.dumps({"run": str(run_root),
                      "targets": {t: {"complete": r.get("complete"), "machine": r.get("machine"),
                                      "error": r.get("error"), "report": r.get("report"),
                                      "statuses": {f["name"]: f["status"] for f in r.get("files", [])}}
                                  for t, r in results.items()},
                      "comparison": comparison,
                      "unverified": summary["unverified"]}, indent=2))
    return 0 if all(r.get("complete") is True for r in results.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
