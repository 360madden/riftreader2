"""Coordinate existing file-only patch tools; never launch, modify or read game processes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {"game", "rr2-addon", "rr2-config", "rr2-calibration"}
PREFIX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
ADDON_FILES = {"RiftAddon.toc", "wire.lua", "producer.lua", "reference.lua", "live.lua", "guidance.lua", "main.lua"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path, expected=None):
    # Hash and parse one byte sequence; reject ambiguous duplicate fields.
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if expected is not None:
        require(actual == expected.lower(), f"SHA-256 mismatch: {path}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON field: {key}")
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique), actual


def run_command(argv, cwd, logs, label, *, timeout=120, accepted=(0,)):
    """Keep separate receipts for failed and successful commands."""
    print(f"Running {label}", file=sys.stderr, flush=True)
    try:
        result = subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        (logs / f"{label}.stdout").write_bytes(exc.stdout or b"")
        (logs / f"{label}.stderr").write_bytes(exc.stderr or b"")
        raise
    (logs / f"{label}.stdout").write_bytes(result.stdout)
    (logs / f"{label}.stderr").write_bytes(result.stderr)
    require(result.returncode in accepted, f"{label} exited {result.returncode}; see {logs}")
    return result


def safe_prefix(value):
    require(isinstance(value, str) and PREFIX.fullmatch(value), "Invalid attempt or shared prefix")
    return value


def exe_fact(snapshot):
    return snapshot["Files"]["game/rift_x64.exe"]["Sha256"].lower()


def read_shared_cycle(shared, prefix, before_sha, old_exe):
    """Require a complete, linked shared capture; no inference from a change list."""
    safe_prefix(prefix)
    changes, changes_sha = read_json(shared / f"{prefix}-changes.json")
    require(changes["schema"] == "update-helper.comparison.v1", "Unsupported shared comparison")
    require(changes["before_manifest_sha256"] == before_sha, "Shared baseline link mismatch")
    consistency, _ = read_json(shared / f"{prefix}-consistency.json",
                               changes["consistency_manifest_sha256"])
    require(consistency["schema"] == changes["schema"], "Shared consistency schema mismatch")
    require(all(consistency["counts"][k] == 0 for k in ("added", "removed", "modified")),
            "Shared installation snapshots disagree")
    a = shared / f"{prefix}-after-a.json"
    b = shared / f"{prefix}-after-b.json"
    _, a_sha = read_json(a, consistency["before_manifest_sha256"])
    after, b_sha = read_json(b, consistency["after_manifest_sha256"])
    require(b_sha == changes["after_manifest_sha256"], "Shared after link mismatch")
    require(changes["before_executable_sha256"] == old_exe, "Shared old executable mismatch")
    require(after["host"] == changes["host"] == consistency["host"], "Shared host mismatch")
    require(after["root"] == changes["root"] == consistency["root"], "Shared root mismatch")
    require(after["complete"] is True and after["phase"] == "after", "Incomplete shared snapshot")
    game = [r for r in after["files"] if r["path"].casefold() == "rift_x64.exe"]
    require(len(game) == 1 and game[0]["sha256"] == changes["after_executable_sha256"],
            "Shared executable fact mismatch")
    return changes, changes_sha, a, a_sha, b, b_sha


def check_current_metadata(root, manifest):
    """Detect ordinary stale/reused captures without a second full content scan."""
    expected = {r["path"]: (r["size"], r["mtime_ns"]) for r in manifest["files"]}
    actual = {}
    def visit(directory):
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                path = Path(entry.path)
                require(not stat.S_ISLNK(info.st_mode) and
                        not getattr(info, "st_file_attributes", 0) & 0x400,
                        f"Reparse point in current installation: {path}")
                if stat.S_ISDIR(info.st_mode):
                    visit(path)
                else:
                    require(stat.S_ISREG(info.st_mode), f"Unexpected installation file: {path}")
                    actual[path.relative_to(root).as_posix()] = (info.st_size, info.st_mtime_ns)
    visit(root)
    require(actual == expected, "Current installation inventory/metadata differs from shared snapshot; take a fresh shared capture")


def addon_facts(receipt, host):
    require(receipt["mode"] == "check" and receipt["machine"].upper() == host,
            "Addon receipt identity mismatch")
    facts = {item["name"]: item for item in receipt["after"]}
    require(set(facts) == ADDON_FILES and len(receipt["after"]) == len(ADDON_FILES),
            "Incomplete addon receipt")
    return facts


def installed_addon_baseline(cfg, root, host):
    path = root / cfg["installedAddonReceipt"]
    receipt, sha = read_json(path, cfg["installedAddonReceiptSha256"])
    facts = addon_facts(receipt, host)
    for name, item in facts.items():
        require(item["present"] and item["pinned"] and not item["offline"] and
                digest(path.parent / name) == item["sha256"].lower(),
                f"Installed addon baseline copy mismatch: {name}")
    return receipt, facts, sha


def compare_installed_addon(result, root, host, baseline, facts):
    # An unavailable installed addon is a separate blocker, not a failed
    # installation-file comparison. Never label missing evidence unchanged.
    try:
        target = json.loads(result.stdout)["targets"]["pc"]
        report_path = Path(target["report"])
        require(report_path.is_absolute() and report_path.is_relative_to(root / "artifacts" / "addon-sync"),
                "Unexpected addon report path")
        current, sha = read_json(report_path)
        require(Path(current["destination"]) == Path(baseline["destination"]),
                "Installed addon location changed")
        observed = addon_facts(current, host)
        changed = sorted(name for name in facts if
                         observed[name]["present"] != facts[name]["present"] or
                         observed[name]["sha256"] != facts[name]["sha256"])
        unavailable = sorted(name for name, item in observed.items() if not item["present"] or
                             item["offline"] or not item["pinned"] or not item["sha256"])
        return {"status": "changed-or-unavailable" if unavailable else "changed" if changed else "unchanged",
                "changed": changed, "unavailable": unavailable,
                "lineEndingOnlyVsRepo": target.get("lineEndingOnly", []),
                "exactRepositoryMatch": target["success"], "reportSha256": sha,
                "report": str(report_path)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "unavailable", "reason": str(exc)}


def recover(checkpoint, attempt, reuse=None, *, root=ROOT):
    safe_prefix(attempt)
    require(len(attempt) <= 44, "Attempt prefix too long")
    if reuse:
        safe_prefix(reuse)
    cfg, cfg_sha = read_json(checkpoint)
    require(cfg["schemaVersion"] == 1, "Unsupported recovery checkpoint")
    host = socket.gethostname().upper()
    require(host == cfg["expectedHost"].upper(), f"Wrong host: {host}")
    shared_before = Path(cfg["sharedBefore"])
    shared = shared_before.parent
    before_path = root / cfg["rr2Before"]
    baseline, baseline_sha = read_json(before_path, cfg["rr2BeforeSha256"])
    shared_baseline, shared_sha = read_json(shared_before, cfg["sharedBeforeSha256"])
    require(baseline["Machine"].upper() == shared_baseline["host"].upper() == host,
            "Baseline host mismatch")
    old_exe = exe_fact(baseline)
    require(old_exe == cfg["beforeExeSha256"].lower(), "RR2 baseline executable mismatch")
    archived = Path(cfg["archivedExe"])
    require(digest(archived) == old_exe, "Archived pre-patch executable mismatch")
    addon_before, addon_before_facts, addon_before_sha = installed_addon_baseline(cfg, root, host)

    # Derive the exact selected source groups from the pinned RR2 baseline.
    # Never change source coverage silently, even when the checkout has moved.
    sources = {item["Group"]: Path(item["Origin"]) for item in baseline["Sources"]}
    require(set(sources) == GROUPS and len(baseline["Sources"]) == len(GROUPS),
            "Unexpected RR2 source coverage")
    require(all(item["Status"] == "present" for item in baseline["Sources"]),
            "Incomplete RR2 baseline")
    game = sources["game"]
    require(game == Path(shared_baseline["root"]) / "rift_x64.exe", "Game root mismatch")
    require(sources["rr2-addon"] == root / "addon" and sources["rr2-config"] == root / "config"
            and sources["rr2-calibration"] == root / ".local" / "waypoints-calibration",
            "RR2 baseline checkout mismatch")
    require(all(p.exists() for p in sources.values()), "Required RR2 source missing")

    output = root / "artifacts" / "patch-recovery" / attempt
    output.mkdir(parents=True, exist_ok=False)
    logs = output / "logs"
    logs.mkdir()
    python = sys.executable
    helper = shared / "update_helper.py"
    dotnet = Path(cfg["dotnet"])
    project = root / "tools" / "RiftUpdateAnalyzer" / "RiftUpdateAnalyzer.csproj"
    dll = project.parent / "bin" / "Release" / "net10.0" / "RiftUpdateAnalyzer.dll"

    verify = run_command([python, "-B", helper, "verify", shared_before,
                          "--expected-sha256", shared_sha], shared, logs, "shared-verify")
    verified = json.loads(verify.stdout)
    require(verified["valid"] and verified["phase"] == "before" and
            verified["exe_sha256"] == old_exe and verified["host"].upper() == host,
            "Shared pre-patch verification failed")
    sdk = run_command([dotnet, "--version"], root, logs, "sdk")
    require(sdk.stdout.decode().strip() == cfg["sdkVersion"], "Incorrect .NET SDK")
    run_command([dotnet, "build", project, "-c", "Release", "-p:RestoreLockedMode=true"],
                root, logs, "build")

    prefix = reuse or f"rr2-{attempt}"
    # The helper's actual prefix is allowed to be up to 80 characters;
    # our attempts are shorter, so this remains within its supported range.
    safe_prefix(prefix)
    if not reuse:
        run_command([python, "-B", shared / "post_patch.py", "--expected-host", host,
                     "--before", shared_before, "--expected-before-sha256", shared_sha,
                     "--prefix", prefix], shared, logs, "shared-capture", timeout=480)
    changes, changes_sha, a, a_sha, b, b_sha = read_shared_cycle(
        shared, prefix, shared_sha, old_exe)
    require(changes["host"].upper() == host and Path(changes["root"]) == game.parent,
            "Wrong shared recovery source")

    if reuse:
        # Revalidate the reused evidence with the authoritative helper; avoid
        # rehashing the installation but never trust an unlinked report alone.
        for label, left, left_sha, same in (
            ("consistency", a, a_sha, True), ("changes", shared_before, shared_sha, False)
        ):
            dest = shared / f"rr2-{attempt}-recheck-{label}.json"
            args = [python, "-B", helper, "compare", "--before", left, "--after", b,
                    "--expected-before-sha256", left_sha, "--expected-after-sha256", b_sha,
                    "--out", dest]
            if same:
                args.append("--consistency")
            run_command(args, shared, logs, f"recheck-{label}")
            replay, _ = read_json(dest)
            original, _ = read_json(shared / f"{prefix}-{label}.json")
            require(all(replay[k] == original[k] for k in (
                "host", "root", "before_utc", "after_utc", "counts", "changes",
                "before_executable_sha256", "after_executable_sha256")),
                f"Reused shared {label} report disagrees with recomputation")

    shared_after, _ = read_json(b, b_sha)
    expected_new = changes["after_executable_sha256"]
    check_current_metadata(game.parent, shared_after)
    # A metadata check is not a full content rehash. Check the installed
    # executable by SHA-256 before and after selected scans as well.
    require(digest(game) == expected_new, "Installed executable no longer matches shared capture")
    capture_args = [dotnet, dll, "capture", "--expected-host", host]
    for group, path in sources.items():
        capture_args += ["--source", f"{group}={path}"]
    after_a, after_b = output / "after-a.json", output / "after-b.json"
    for label, dest in (("rr2-capture-a", after_a), ("rr2-capture-b", after_b)):
        run_command([*capture_args, "--out", dest], root, logs, label)
        selected, _ = read_json(dest)
        require(exe_fact(selected) == expected_new, "Selected and shared executable disagree")
    run_command([dotnet, dll, "compare", "--before", after_a, "--after", after_b,
                 "--out", output / "consistency.json"], root, logs, "rr2-consistency")
    result = run_command([dotnet, dll, "compare", "--before", before_path, "--after", after_b,
                          "--out", output / "changes.json"], root, logs, "rr2-compare", accepted=(0, 1))
    run_command([dotnet, dll, "report", "--comparison", output / "changes.json",
                 "--out", output / "REPORT.md"], root, logs, "rr2-report", accepted=(0, 1))

    # Archive a changed executable for offline comparison; never execute it.
    archive = archived
    if expected_new != old_exe:
        archive = output / "new-build" / "rift_x64.exe"
        archive.parent.mkdir()
        with game.open("rb") as src, archive.open("xb") as dest:
            shutil.copyfileobj(src, dest)
        require(digest(archive) == expected_new, "New executable copy mismatch")
    require(digest(game) == expected_new, "Game executable changed during recovery")
    require(digest(before_path) == baseline_sha and digest(shared_before) == shared_sha and
            digest(archived) == old_exe, "Pre-patch evidence changed during recovery")
    require(digest(shared / f"{prefix}-changes.json") == changes_sha and
            digest(shared / f"{prefix}-consistency.json") == changes["consistency_manifest_sha256"] and
            digest(a) == a_sha and digest(b) == b_sha, "Shared evidence changed during recovery")

    # The check is intentionally not a deployment, reload, or runtime test.
    addon = run_command([python, "-B", root / "scripts" / "addon_sync.py", "check",
                         "--target", "pc", "--expected-host", host], root, logs,
                        "installed-addon-check", accepted=(0, 2))
    addon_comparison = compare_installed_addon(addon, root, host, addon_before, addon_before_facts)
    check_current_metadata(game.parent, shared_after)
    require(digest(game) == expected_new, "Executable changed after addon check")
    summary = {
        "status": "file-evidence-complete", "host": host,
        "checkpointSha256": cfg_sha, "sharedPrefix": prefix, "sharedEvidenceReused": bool(reuse),
        "sharedReportSha256": changes_sha, "sharedCounts": changes["counts"],
        "sharedCaptureFinishedUtc": shared_after["finished_utc"],
        "beforeExeSha256": old_exe, "afterExeSha256": expected_new,
        "archivedExe": str(archive), "rr2ChangesDetected": result.returncode == 1,
        "rr2ReportSha256": digest(output / "changes.json"),
        "addonCheckExit": addon.returncode, "installedAddonBeforeReceiptSha256": addon_before_sha,
        "installedAddonComparison": addon_comparison, "runtimeCompatibilityEstablished": False,
        "coverage": "Shared full-content capture at recorded time; current metadata rechecked, not a full rehash. Repeated current RR2 selected files.",
        "output": str(output),
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--reuse-shared-prefix", help="Reuse a completed shared Update Helper cycle")
    args = parser.parse_args()
    try:
        print(json.dumps(recover(args.checkpoint, args.attempt, args.reuse_shared_prefix), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"Recovery incomplete: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
