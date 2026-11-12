"""Two no-input physical RR2A1 Lua scans between verified native player brackets.

Reuses the existing C# typed-memory scanner, native bracket and SHA-checked
offline comparator. A completed result is candidate-only: unbound RR2A1 is
neither a nonce-authenticated source nor proof of action-associated movement.
Raw files survive failure, and every process read is confined to AMD-DESKTOP.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (compare_physical_rr2a1_passes as compare,
                     physical_player_xyz_bracket as bracket,
                     physical_rift,
                     probe_physical_rr2r1 as probe)

HOST = "AMD-DESKTOP"
MARKER = "RR2A1|"


def require(ok, reason):
    if not ok:
        raise ValueError("physical-rr2a1-collect-" + reason)


def same_process(pid, original, reader_sha):
    current = probe.pinned_selection(pid)
    require(current["target"] == original["target"], "process-epoch-changed")
    require(probe.digest(physical_rift.NATIVE_EXE) == reader_sha,
            "native-reader-changed")
    return current


def scan_once(pid, selection, reader_sha, directory, *, scan_bytes, scan_ms,
              start_address="0x10000"):
    same_process(pid, selection, reader_sha)
    directory.mkdir(parents=True, exist_ok=False)
    target = selection["target"]
    request = {
        "schemaVersion": 1,
        "evidenceKind": "native-typed-inline-capture-request/1",
        "target": {
            "processId": pid,
            "processStartUtcTicks": int(target["processStartUtcTicks"]),
            "executableSha256": target["executableSha256"].upper(),
        },
        "startAddress": start_address,
        "maxScanBytes": scan_bytes,
        "maxDurationMilliseconds": scan_ms,
        "maxRegionCount": 32768,
        "maxMatchCount": 128,
        "maxCopiedCandidates": 8,
        "marker": MARKER,
    }
    request_path = directory / "request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n",
                            encoding="utf-8")
    scan_dir = directory / "scan"
    process = subprocess.run(
        [str(physical_rift.NATIVE_EXE), "scout-copy-typed-native",
         "--request", str(request_path), "--output", str(scan_dir)],
        cwd=ROOT, capture_output=True, text=True, timeout=scan_ms / 1000 + 30,
        check=False,
    )
    require(process.returncode in (0, 3), "native-scanner-exit-" +
            str(process.returncode))
    receipt = probe.check_index(
        scan_dir / "index.json", request, probe.digest(request_path), selection)
    same_process(pid, selection, reader_sha)
    return scan_dir / "index.json", receipt


def focused_second_pass(index_path, receipt):
    """Use only this run's source-pinned copied markers, never a saved address."""
    require(probe.digest(index_path) == receipt["indexSha256"],
            "first-scan-index-changed")
    index = json.loads(index_path.read_text(encoding="utf-8"),
                       object_pairs_hook=probe.unique)
    addresses = [int(row["markerAddress"], 16)
                 for row in index.get("candidates", [])
                 if row.get("status") == "complete" and row.get("snapshotSha256")]
    if len(addresses) < 2:
        return None
    start = max(0x10000, min(addresses) - 1_048_576) & ~4095
    # One-epoch memory locality only; any missing data fails the usual replay.
    if max(addresses) + 1_048_576 - start > 33_554_432:
        return None
    return f"0x{start:X}", 33_554_432


def collect(pid, output_dir, *, scan_bytes=268_435_456, scan_ms=15_000,
            samples=3, interval_ms=150, focus_second_pass=False):
    require(socket.gethostname().upper() == HOST, "wrong-host")
    require(type(pid) is int and 0 < pid < 2**31, "explicit-pid-required")
    require(type(scan_bytes) is int and
            1_048_576 <= scan_bytes <= 536_870_912 and
            scan_bytes % 4096 == 0 and
            type(scan_ms) is int and 1000 <= scan_ms <= 30_000 and
            type(samples) is int and 1 <= samples <= 30 and
            type(interval_ms) is int and 0 <= interval_ms <= 2000 and
            type(focus_second_pass) is bool,
            "invalid-collection-bounds")
    selection = probe.pinned_selection(pid)
    reader = physical_rift.NATIVE_EXE
    require(reader.is_file(), "native-reader-unavailable")
    reader_sha = probe.digest(reader)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)

    # Both native brackets and both Lua scans carry the same rechecked PID,
    # process start, exact executable SHA and C# reader binary identity.
    before, _ = bracket.collect(
        pid, output_dir / "native-before", samples=samples,
        interval_ms=interval_ms)
    same_process(pid, selection, reader_sha)
    first, first_receipt = scan_once(
        pid, selection, reader_sha, output_dir / "pass-01",
        scan_bytes=scan_bytes, scan_ms=scan_ms)
    focus = (focused_second_pass(first, first_receipt)
             if focus_second_pass else None)
    if focus is not None and focus[1] > scan_bytes:
        focus = None  # Never exceed the caller's scan-byte budget.
    second, second_receipt = scan_once(
        pid, selection, reader_sha, output_dir / "pass-02",
        scan_bytes=focus[1] if focus else scan_bytes, scan_ms=scan_ms,
        start_address=focus[0] if focus else "0x10000")
    failed_focused_index_sha = None
    if focus is not None and second_receipt["publishedSnapshots"] < 2:
        # Marker memory may move between independent reads. Keep the failed
        # focused receipt intact and try the original bounded broad route once.
        failed_focused_index_sha = second_receipt["indexSha256"]
        second, second_receipt = scan_once(
            pid, selection, reader_sha, output_dir / "pass-02-broad",
            scan_bytes=scan_bytes, scan_ms=scan_ms, start_address="0x10000")
    after, _ = bracket.collect(
        pid, output_dir / "native-after", samples=samples,
        interval_ms=interval_ms)
    same_process(pid, selection, reader_sha)

    # Source replay must pass before we describe any Lua/native agreement.
    try:
        paired = compare.compare(first, second, before, after)
    except ValueError as exc:
        # A focused scan can copy eight *old* frames, so its successful copy
        # count alone does not establish two newly advancing producer frames.
        # Retry the original bounded broad scope once, then take a NEW final
        # native bracket so source chronology remains valid.
        stale_focused = str(exc) in (
            "physical-rr2a1-pair-nonadvancing-or-overlapping-passes",
            "physical-rr2a1-pair-insufficient-new-frames",
        )
        if not (focus is not None and failed_focused_index_sha is None
                and stale_focused):
            raise
        failed_focused_index_sha = second_receipt["indexSha256"]
        second, second_receipt = scan_once(
            pid, selection, reader_sha, output_dir / "pass-02-broad",
            scan_bytes=scan_bytes, scan_ms=scan_ms, start_address="0x10000")
        after, _ = bracket.collect(
            pid, output_dir / "native-after-broad", samples=samples,
            interval_ms=interval_ms)
        same_process(pid, selection, reader_sha)
        paired = compare.compare(first, second, before, after)
    paired["captureOrder"] = compare.verify_capture_order(first, second, before, after)
    summary = {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-rr2a1-bracketed-two-pass/1",
        "status": paired["status"],
        "ownerHost": HOST,
        "target": selection["target"],
        "readerSha256": reader_sha,
        "nativeBracketSha256": {
            "before": probe.digest(before),
            "after": probe.digest(after),
        },
        "scanIndexSha256": {
            "first": first_receipt["indexSha256"],
            "second": second_receipt["indexSha256"],
        },
        "scanSnapshots": [first_receipt["publishedSnapshots"],
                          second_receipt["publishedSnapshots"]],
        "secondPassFocus": {"requested": focus_second_pass,
                            "used": focus is not None,
                            "selected": focus is not None and
                                        failed_focused_index_sha is None,
                            "fallbackUsed": failed_focused_index_sha is not None,
                            "failedFocusedIndexSha256": failed_focused_index_sha,
                            "startAddress": focus[0] if focus else "0x10000",
                            "maxScanBytes": focus[1] if focus else scan_bytes},
        "comparison": paired,
        "qualification": ("Real independent RR2A1 baseline Lua frames and native "
                          "candidate brackets in one verified physical process "
                          "epoch; no nonce, action causation, atomic freshness, "
                          "target semantics or automatic restart qualification."),
    }
    path = output_dir / "summary.json"
    with path.open("x", encoding="utf-8", newline="\n") as out:
        json.dump(summary, out, indent=2, allow_nan=False)
        out.write("\n")
    return path, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" /
                        ("physical-rr2a1-bracketed-" + uuid.uuid4().hex))
    parser.add_argument("--scan-bytes", type=int, default=268_435_456)
    parser.add_argument("--scan-ms", type=int, default=15_000)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=150)
    parser.add_argument("--focus-second-pass", action="store_true",
                        help="Re-scan first-pass marker window (same-epoch experiment)")
    args = parser.parse_args(argv)
    try:
        path, result = collect(
            args.physical_pid, args.output_dir,
            scan_bytes=args.scan_bytes, scan_ms=args.scan_ms,
            samples=args.samples, interval_ms=args.interval_ms,
            focus_second_pass=args.focus_second_pass)
    except (OSError, ValueError, KeyError, TypeError, OverflowError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220],
                          "qualification": "No fresh qualified Lua/native result"}))
        return 2
    print(json.dumps({
        "status": result["status"], "summary": str(path),
        "snapshots": result["scanSnapshots"],
        "sequenceWindows": result["comparison"]["sequenceWindows"],
        "coordinateAgreementScreen":
            result["comparison"]["coordinateAgreementScreen"]["result"],
    }))
    return 0 if result["status"] == "candidate-only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
