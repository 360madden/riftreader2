"""Offline XYZ/refresh-guard observations from one retained native sampler report.

Usage: python -B scripts/summarize_native_xyz_guard_track.py samples.json
       --max-gap-seconds 5 --max-speed-3d 100
No live reads; no writer, movement, facing or passive-freshness inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.project_xyz_track import MAX_BYTES, _pairs
from scripts.summarize_native_xyz_track import summarize as summarize_xyz

GUARD_FIELDS = ("refreshHandleHex", "refreshFlagRaw", "refreshGuardStatus")


def _guard(row):
    present = tuple(field in row for field in GUARD_FIELDS)
    if not any(present):
        return {"guardAvailability": "unavailable-legacy-fields-absent",
                **dict.fromkeys(GUARD_FIELDS)}
    if not all(present):
        raise ValueError("partial refresh guard fields")
    handle, flag, status = (row[field] for field in GUARD_FIELDS)
    if (not isinstance(handle, str) or re.fullmatch(r"0x[0-9A-F]{16}", handle) is None
            or type(flag) is not int or not 0 <= flag <= 255):
        raise ValueError("invalid raw refresh guard fields")
    expected = ("handle-present-guard-candidate" if int(handle, 16) else
                "alternate-flag-guard-candidate" if flag else "guard-ineligible-candidate")
    if status != expected:
        raise ValueError("refresh guard status contradicts raw fields")
    return {"guardAvailability": "same-component-buffer-candidate",
            **{field: row[field] for field in GUARD_FIELDS}}


def summarize(report, *, max_gap_seconds, max_speed_3d):
    """Project 2-30 rows within ONE validated report; never join process epochs."""
    out = summarize_xyz(report, max_gap_seconds=max_gap_seconds, max_speed_3d=max_speed_3d)
    rows = report["observations"]
    if len(rows) < 2:
        raise ValueError("guard track requires 2-30 samples in one report")
    boundaries = {segment["firstIndex"]: segment["startReason"] for segment in out["segments"]}
    observations = []
    counts = {key: 0 for key in (
        "xyz-and-guard-unchanged", "guard-only-change", "xyz-only-change",
        "xyz-and-guard-change", "xyz-unchanged-guard-unknown", "xyz-changed-guard-unknown")}
    prior = prior_guard = None
    for row in rows:
        guard = _guard(row)
        xyz = {axis: row[axis] for axis in "xyz"}
        xyz_changed = guard_changed = None
        reason = boundaries.get(row["index"])
        if reason is not None:
            comparison = "unavailable-boundary"
        else:
            xyz_changed = any(row[axis] != prior[axis] for axis in "xyz")
            if (guard["guardAvailability"] == "same-component-buffer-candidate"
                    and prior_guard["guardAvailability"] == "same-component-buffer-candidate"):
                guard_changed = any(guard[field] != prior_guard[field] for field in GUARD_FIELDS[:2])
                comparison = (
                    "xyz-and-guard-change" if xyz_changed and guard_changed else
                    "xyz-only-change" if xyz_changed else
                    "guard-only-change" if guard_changed else "xyz-and-guard-unchanged")
            else:
                comparison = "xyz-changed-guard-unknown" if xyz_changed else "xyz-unchanged-guard-unknown"
            counts[comparison] += 1
        observations.append({
            "index": row["index"], "startedAtUtc": row["startedAtUtc"],
            "completedAtUtc": row["completedAtUtc"],
            "monotonicStartMilliseconds": row["monotonicStartMilliseconds"],
            "monotonicEndMilliseconds": row["monotonicEndMilliseconds"],
            "xyz": xyz,
            "unitKey": row.get("unitKey"), "unitIdCandidate": row.get("unitIdCandidate"),
            "ownerIdentityStatus": row.get("ownerIdentityStatus", "unavailable-in-source"),
            **guard, "pairComparison": comparison, "boundaryReason": reason,
            "xyzChanged": xyz_changed, "guardChanged": guard_changed,
        })
        prior, prior_guard = row, guard
    out.update(contractVersion="native-xyz-guard-track-candidate/1",
               sourceContractVersion=report["contractVersion"],
               sourceBuildSha256=report["sourceBuildSha256"],
               sourceQualification=report["qualification"],
               ownerIdentityStatus=rows[0].get("ownerIdentityStatus", "unavailable-in-source"),
               observations=observations, pairCounts=counts,
               refreshGuardFieldsPresentCount=sum(
                   row["guardAvailability"] == "same-component-buffer-candidate" for row in observations),
               writerExecution="unavailable-in-source", passiveFreshness="unqualified",
               facing="unqualified")
    out["limitations"].extend([
        "Refresh guard bytes accompany XYZ in the same 0x110-byte component buffer; guards are not independently reread.",
        "Raw guard eligibility or changes do not prove a writer ran, passive freshness, motion or facing.",
        "Legacy absent guard fields remain unknown, never explicit zero.",
        "No comparison across reports, process epochs or projector boundaries.",
    ])
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--max-gap-seconds", type=float, required=True)
    parser.add_argument("--max-speed-3d", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        with args.report.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("input report exceeds size limit")
        report = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs)
        output = summarize(report, max_gap_seconds=args.max_gap_seconds, max_speed_3d=args.max_speed_3d)
        output["sourceSha256"] = hashlib.sha256(data).hexdigest().upper()
        print(json.dumps(output, allow_nan=False))
        return 0
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "unavailable", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
