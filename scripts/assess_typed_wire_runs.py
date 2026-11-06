"""Assess every strict typed-wire pairing across two retained capture runs.

This is an offline evidence operation. It invokes the existing C#
``inspect-typed-wire`` command for each cross-run snapshot pair, publishes the
unchanged diagnostics in a new directory, and adds one bounded summary. It does
not read a live process, contact a VM, or turn scoped typed frames into native
field qualification.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.inspect_typed_resource import require_reference_binding, require_session_id


class AssessmentError(ValueError):
    """The retained runs cannot support a strict cross-run assessment."""


def _json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AssessmentError(f"{path}: duplicate JSON property {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text("utf-8-sig"), object_pairs_hook=unique)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AssessmentError(f"{path}: invalid JSON ({type(exc).__name__})") from exc
    if not isinstance(value, dict):
        raise AssessmentError(f"{path}: object JSON required")
    return value


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise AssessmentError(f"{label}: UTC timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssessmentError(f"{label}: invalid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise AssessmentError(f"{label}: timestamp must be UTC")
    return parsed


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _run(path: Path, label: str) -> tuple[dict, list[Path], dict[str, str]]:
    if not path.is_dir() or path.is_symlink():
        raise AssessmentError(f"{label}: capture run must be a real directory")
    index = _json(path / "index.json")
    if index.get("schemaVersion") != 1 or index.get("evidenceKind") != "native-typed-inline-capture/1":
        raise AssessmentError(f"{label}: unsupported capture index")
    if index.get("status") == "identity-invalidated":
        raise AssessmentError(f"{label}: identity-invalidated capture cannot be paired")
    candidates = index.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 128:
        raise AssessmentError(f"{label}: invalid capture candidate inventory")
    bindings: dict[str, str] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise AssessmentError(f"{label}: capture candidate must be an object")
        snapshot_name = candidate.get("snapshotFile")
        request_name = candidate.get("requestFile")
        if snapshot_name is None and request_name is None:
            continue
        if (not isinstance(snapshot_name, str) or not isinstance(request_name, str)
                or snapshot_name in bindings):
            raise AssessmentError(f"{label}: invalid or duplicate capture binding")
        snapshot = path / snapshot_name
        request = path / request_name
        if (snapshot.parent != path or request.parent != path or snapshot.is_symlink()
                or request.is_symlink() or not snapshot.is_file() or not request.is_file()
                or _sha(snapshot) != candidate.get("snapshotSha256")
                or _sha(request) != candidate.get("requestSha256")):
            raise AssessmentError(f"{label}: manifest-bound capture bytes differ")
        bindings[snapshot_name] = candidate["snapshotSha256"]
    snapshots = sorted(path.glob("capture-??.snapshot.json"))
    if (not 1 <= len(snapshots) <= 8 or any(item.is_symlink() for item in snapshots)
            or {item.name for item in snapshots} != set(bindings)
            or index.get("publishedSnapshots") != len(snapshots)):
        raise AssessmentError(f"{label}: expected one to eight retained snapshots")
    return index, snapshots, bindings


def _snapshot_gap(report: dict) -> float:
    source = report.get("source")
    if not isinstance(source, dict):
        raise AssessmentError("strict diagnostic lacks source snapshot timing")
    before, after = source.get("before"), source.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise AssessmentError("strict diagnostic lacks source snapshot timing")
    gap = (_utc(after.get("startedAtUtc"), "diagnostic after startedAtUtc")
           - _utc(before.get("completedAtUtc"), "diagnostic before completedAtUtc")).total_seconds()
    if gap <= 0:
        raise AssessmentError("strict diagnostic snapshot windows overlap or reverse")
    return gap


def _validate_report(report: dict, session_id: str | None = None) -> None:
    if (report.get("schemaVersion") != 1
            or report.get("evidenceKind") != "typed-wire-snapshot-inspection/1"
            or report.get("status") not in (
                "advanced-in-covered-scope", "blocked", "unavailable")
            or not isinstance(report.get("reason"), str)
            or not isinstance(report.get("identity"), dict)):
        raise AssessmentError("strict diagnostic contract or status is invalid")
    source = report.get("source")
    if (not isinstance(source, dict) or not isinstance(source.get("before"), dict)
            or not isinstance(source.get("after"), dict)):
        raise AssessmentError("strict diagnostic source shape is invalid")
    for name in ("before", "after"):
        item = source[name]
        if (not isinstance(item.get("snapshotSha256"), str)
                or len(item["snapshotSha256"]) != 64
                or any(char not in "0123456789ABCDEFabcdef" for char in item["snapshotSha256"])
                or not isinstance(item.get("startedAtUtc"), str)
                or not isinstance(item.get("completedAtUtc"), str)):
            raise AssessmentError("strict diagnostic source identity or timing is invalid")
    if report["status"] == "advanced-in-covered-scope":
        selected = report.get("selected")
        advances = report.get("advances")
        if (not isinstance(selected, dict) or not isinstance(selected.get("before"), dict)
                or not isinstance(selected.get("after"), dict) or not isinstance(advances, dict)):
            raise AssessmentError("advancing diagnostic lacks selected frames")
        before, after = selected["before"], selected["after"]
        if session_id is not None:
            for item in (before, after):
                require_reference_binding(item, session_id)
            if before["epoch"] != after["epoch"]:
                raise AssessmentError("reference-epoch-changed")
        before_time, after_time = before.get("frameTime"), after.get("frameTime")
        if (type(before.get("sequence")) is not int or type(after.get("sequence")) is not int
                or after["sequence"] <= before["sequence"]
                or type(before_time) not in (int, float) or type(after_time) not in (int, float)
                or not math.isfinite(before_time) or not math.isfinite(after_time)
                or after_time <= before_time
                or not isinstance(before.get("playerUnitId"), str)
                or not before.get("playerUnitId")
                or before.get("playerUnitId") != after.get("playerUnitId")):
            raise AssessmentError("advancing diagnostic selected frame shape is invalid")


def summarize(reports: list[tuple[str, dict]], *, maximum_run_gap_seconds: float,
              session_id: str | None = None) -> dict:
    for _, report in reports:
        _validate_report(report, session_id)
    if session_id is not None:
        bindings = set()
        for _, report in reports:
            reason = report["reason"]
            if report["status"] != "advanced-in-covered-scope" and not any(
                    allowed in reason for allowed in ("no-complete-usable-frame-in-covered-scope", "incomplete-typed-fragment-in-covered-scope")):
                raise AssessmentError("reference-diagnostic-failed:" + reason)
            selected = report.get("selected")
            if isinstance(selected, dict):
                for row in selected.values():
                    if row is not None:
                        require_reference_binding(row, session_id)
                        bindings.add((row["epoch"], row.get("playerUnitId")))
        if len(bindings) > 1:
            raise AssessmentError("reference-epoch-or-player-conflict-across-pairs")
    evaluated = [(name, report, _snapshot_gap(report)) for name, report in reports]
    advancing = [(name, report, gap) for name, report, gap in evaluated
                 if report.get("status") == "advanced-in-covered-scope"]
    if session_id is not None:
        bindings = {(report["selected"]["after"]["epoch"], report["selected"]["after"]["playerUnitId"])
                    for _, report, _ in advancing}
        if len(bindings) > 1:
            raise AssessmentError("reference-epoch-or-player-conflict-across-pairs")
    blocked = sum(report.get("status") == "blocked" for _, report in reports)
    unavailable = sum(report.get("status") == "unavailable" for _, report in reports)
    in_window = [item for item in advancing if item[2] <= maximum_run_gap_seconds]
    selected_name = None
    selected = None
    selected_gap = None
    selection_pool = in_window or advancing
    if selection_pool:
        selected_name, selected, selected_gap = max(
            selection_pool,
            key=lambda item: (
                item[1]["selected"]["after"]["frameTime"],
                item[1]["selected"]["after"]["sequence"],
                item[1]["selected"]["before"]["frameTime"],
            ),
        )
    within_window = selected_gap is not None and selected_gap <= maximum_run_gap_seconds
    status = "advancing-reference-in-pairing-window" if selected and within_window else (
        "advancing-reference-outside-pairing-window" if selected else "no-advancing-reference")
    identity = selected.get("identity") if selected else None
    player = selected["selected"]["after"]["playerUnitId"] if selected else None
    return {
        "schemaVersion": 1,
        "evidenceKind": "typed-wire-run-assessment/1",
        "status": status,
        "pairingWindow": {
            "maximumRunGapSeconds": maximum_run_gap_seconds,
            "selectedSnapshotGapSeconds": selected_gap,
            "withinWindow": within_window,
        },
        "diagnostics": {
            "total": len(reports),
            "advancing": len(advancing),
            "advancingWithinWindow": len(in_window),
            "blocked": blocked,
            "unavailable": unavailable,
        },
        "selectedDiagnostic": selected_name,
        "identity": identity,
        "playerUnitId": player,
        "selected": selected.get("selected") if selected else None,
        "advances": selected.get("advances") if selected else None,
        "limitations": [
            "The pairing window is a caller-declared comparison bound, not measured clock synchronization.",
            "Advancing RRAPIVAL2 frames are independent Lua/API source evidence, not native field semantics.",
            "The underlying scans remain bounded; absent frames apply only to their covered bytes.",
            "A stable player ID is not proof that a separately acquired native sample belongs to that player.",
        ],
    }


def assess(before_run: Path, after_run: Path, cli: Path, output: Path,
           maximum_run_gap_seconds: float, dotnet: str = "dotnet",
           session_id: str | None = None) -> dict:
    if session_id is not None:
        require_session_id(session_id)
    if not 0 < maximum_run_gap_seconds <= 3600:
        raise AssessmentError("maximum run gap must be in (0, 3600] seconds")
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise AssessmentError("output must be absent and its parent must exist")
    if not cli.is_file() or cli.is_symlink():
        raise AssessmentError("existing non-symlink C# CLI DLL required")
    before_index, before_snapshots, before_bindings = _run(before_run, "before")
    after_index, after_snapshots, after_bindings = _run(after_run, "after")
    before_end = _utc(before_index.get("completedAtUtc"), "before completedAtUtc")
    after_start = _utc(after_index.get("startedAtUtc"), "after startedAtUtc")
    run_gap = (after_start - before_end).total_seconds()
    if run_gap <= 0:
        raise AssessmentError("capture runs must be chronological and nonoverlapping")

    with tempfile.TemporaryDirectory(prefix=".rr2-typed-assess-", dir=output.parent) as temporary:
        stage = Path(temporary)
        reports: list[tuple[str, dict]] = []
        for before in before_snapshots:
            for after in after_snapshots:
                name = f"{before.stem.removesuffix('.snapshot')}-to-{after.stem.removesuffix('.snapshot')}.json"
                destination = stage / name
                result = subprocess.run(
                    [dotnet, str(cli), "inspect-typed-wire", "--before", str(before),
                     "--after", str(after), "--output", str(destination)]
                    + (["--session-id", session_id] if session_id is not None else []),
                    capture_output=True, text=True, timeout=30, check=False,
                )
                if result.returncode != 0 or not destination.is_file():
                    raise AssessmentError(
                        f"strict inspector failed for {before.name} -> {after.name} "
                        f"(exit {result.returncode})")
                report = _json(destination)
                _validate_report(report, session_id)
                source = report.get("source")
                if (not isinstance(source, dict) or not isinstance(source.get("before"), dict)
                        or not isinstance(source.get("after"), dict)
                        or source["before"].get("snapshotSha256") != before_bindings[before.name]
                        or source["after"].get("snapshotSha256") != after_bindings[after.name]):
                    raise AssessmentError(f"{destination}: diagnostic snapshot is not manifest-bound")
                reports.append((name, report))
        summary = summarize(
            reports, maximum_run_gap_seconds=maximum_run_gap_seconds, session_id=session_id)
        summary["sourceRuns"] = {
            "before": str(before_run.resolve()),
            "after": str(after_run.resolve()),
            "beforeStatus": before_index.get("status"),
            "afterStatus": after_index.get("status"),
            "indexEnvelopeGapSeconds": run_gap,
        }
        (stage / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
        if output.exists() or output.is_symlink():
            raise AssessmentError("output appeared during assessment")
        os.rename(stage, output)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-run", required=True, type=Path)
    parser.add_argument("--after-run", required=True, type=Path)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--maximum-run-gap-seconds", required=True, type=float)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--session-id")
    args = parser.parse_args(argv)
    try:
        result = assess(
            args.before_run, args.after_run, args.cli, args.output,
            args.maximum_run_gap_seconds, args.dotnet, args.session_id)
    except (AssessmentError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
