"""Read-only bounded RR2R1 candidate search on verified AMD-DESKTOP physical RIFT.

Reuses the existing C# scout-copy-typed-native collector. A prefix match is
NOT a decoded, fresh Lua frame; use the existing typed inspector to qualify it.
No addon binding, game input, focus changes, or VM access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.compare_physical_player_context_pair import BUILD_SHA

HOST = "AMD-DESKTOP"
MARKER = "RR2R1|"
SCAN_BYTES = 256 * 1024 * 1024
SCAN_MS = 15_000
SCAN_COUNT = 8


def require(condition, reason):
    if not condition:
        raise ValueError("physical-rr2r1-" + reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-field")
        result[key] = value
    return result


def pinned_selection(pid):
    require(socket.gethostname().upper() == HOST, "wrong-host")
    selection = physical_rift.select_physical(HOST, pid)
    require(selection.get("status") == "ready" and selection.get("ownerHost") == HOST,
            "physical-selection-unavailable")
    identity = selection.get("target")
    require(isinstance(identity, dict) and identity.get("processId") == pid
            and str(identity.get("executableSha256", "")).upper() == BUILD_SHA
            and str(identity.get("processStartUtcTicks", "")).isdecimal(),
            "physical-build-or-epoch-invalid")
    return selection


def check_index(path, request, request_sha, selection):
    data = Path(path).read_bytes()
    require(len(data) <= 8_000_000, "index-too-large")
    index = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique)
    target = selection["target"]
    observed = index.get("identity")
    require(index.get("schemaVersion") == 1
            and index.get("evidenceKind") == "native-typed-inline-capture/1"
            and index.get("requestSha256") == request_sha
            and index.get("request") == request
            and isinstance(observed, dict)
            and observed.get("processId") == target["processId"]
            and str(observed.get("processStartUtcTicks")) == str(target["processStartUtcTicks"])
            and str(observed.get("executableSha256", "")).upper() == BUILD_SHA,
            "scan-evidence-identity-mismatch")
    require(index.get("status") in ("complete", "partial")
            and type(index.get("publishedSnapshots")) is int
            and 0 <= index["publishedSnapshots"] <= 8
            and isinstance(index.get("scan"), dict),
            "scan-evidence-unusable")
    scan = index["scan"]
    require(isinstance(scan.get("prefixAddresses"), list)
            and len(scan["prefixAddresses"]) <= 128,
            "scan-prefix-inventory-invalid")
    return {
        "status": index["status"],
        "indexSha256": hashlib.sha256(data).hexdigest().upper(),
        "prefixCount": len(scan["prefixAddresses"]),
        "publishedSnapshots": index["publishedSnapshots"],
        "scanStatus": scan.get("status"),
        "scanReason": scan.get("reason"),
        "examinedBytes": scan.get("examinedBytes"),
        "startAddress": scan.get("startAddress"),
        "nextAddress": scan.get("nextAddress"),
    }


def checked_cursor(text, previous=None):
    require(isinstance(text, str) and text.startswith("0x"), "invalid-next-cursor")
    try:
        number = int(text[2:], 16)
    except ValueError as exc:
        raise ValueError("physical-rr2r1-invalid-next-cursor") from exc
    require(0x10000 <= number < 2**47 and
            (previous is None or number > int(previous, 16)), "invalid-next-cursor")
    return text


def resume_cursor(path, selection, reader_sha):
    """Resume only after checking saved C# receipts against this *live* epoch.

    A bare historical cursor or summary is not proof of process identity or scan
    completion; reject changed readers, copied candidates and broken source chains.
    """
    path = Path(path)
    raw = path.read_bytes()
    require(len(raw) <= 1_000_000, "resume-summary-too-large")
    summary = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    target = selection["target"]
    expected = {"processId": target["processId"],
                "processStartUtcTicks": int(target["processStartUtcTicks"]),
                "executableSha256": BUILD_SHA}
    require(summary.get("schemaVersion") == 1 and
            summary.get("evidenceKind") == "amd-physical-rr2r1-prefix-scan/1" and
            summary.get("ownerHost") == HOST and summary.get("target") == expected and
            summary.get("readerSha256") == reader_sha and
            summary.get("status") == "no-copied-candidate-in-bounded-scopes",
            "resume-epoch-reader-or-status-mismatch")
    rows = summary.get("runs")
    require(isinstance(rows, list) and 1 <= len(rows) <= 16,
            "resume-runs-invalid")
    prior = None
    for number, row in enumerate(rows, 1):
        require(isinstance(row, dict) and row.get("run") == number and
                row.get("publishedSnapshots") == 0, "resume-run-unusable")
        request_path = path.parent / f"request-{number:02d}.json"
        request_raw = request_path.read_bytes()
        require(len(request_raw) <= 16_384, "resume-request-too-large")
        request = json.loads(request_raw.decode("utf-8-sig"), object_pairs_hook=unique)
        request_sha = hashlib.sha256(request_raw).hexdigest().upper()
        require(request.get("target") == expected and request.get("marker") == MARKER and
                request.get("startAddress") == row.get("startAddress") and
                request_sha == row.get("requestSha256") and
                (prior is None or request["startAddress"] == prior),
                "resume-request-chain-mismatch")
        receipt_path = path.parent / f"run-{number:02d}" / "index.json"
        verified = check_index(receipt_path, request, request_sha, selection)
        require(all(verified.get(key) == row.get(key) for key in
                    ("indexSha256", "status", "publishedSnapshots", "prefixCount",
                     "startAddress", "nextAddress", "scanStatus", "scanReason",
                     "examinedBytes")), "resume-receipt-mismatch")
        prior = checked_cursor(row.get("nextAddress"), row["startAddress"])
    return prior, hashlib.sha256(raw).hexdigest().upper()


def collect(pid, output_dir, *, scan_bytes=SCAN_BYTES, scan_ms=SCAN_MS,
            max_scans=SCAN_COUNT, gap_seconds=1.0, resume_summary=None):
    require(type(pid) is int and 0 < pid < 2**31, "explicit-pid-required")
    require(type(scan_bytes) is int and 1_048_576 <= scan_bytes <= 536_870_912
            and scan_bytes % 4096 == 0
            and type(scan_ms) is int and 1000 <= scan_ms <= 30_000
            and type(max_scans) is int and 1 <= max_scans <= 16
            and type(gap_seconds) in (int, float) and 0 <= gap_seconds <= 10,
            "scan-bounds-invalid")
    selection = pinned_selection(pid)
    reader = physical_rift.NATIVE_EXE
    require(reader.is_file(), "existing-dotnet-reader-unavailable")
    reader_sha = digest(reader)
    target = selection["target"]
    resume = (resume_cursor(resume_summary, selection, reader_sha)
              if resume_summary is not None else None)
    request_template = {
        "schemaVersion": 1,
        "evidenceKind": "native-typed-inline-capture-request/1",
        "target": {
            "processId": pid,
            "processStartUtcTicks": int(target["processStartUtcTicks"]),
            "executableSha256": BUILD_SHA,
        },
        "startAddress": "0x10000",
        "maxScanBytes": scan_bytes,
        "maxDurationMilliseconds": scan_ms,
        "maxRegionCount": 32768,
        "maxMatchCount": 128,
        "maxCopiedCandidates": 8,
        "marker": MARKER,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    cursor = resume[0] if resume else "0x10000"
    initial_cursor = cursor
    for number in range(1, max_scans + 1):
        require(pinned_selection(pid)["target"] == target, "epoch-changed-before-scan")
        require(digest(reader) == reader_sha, "reader-changed")
        # No usable copied frame: advance the native reader's bounded cursor.
        # Copied candidates: resample the same scope to seek an advancing frame.
        request = dict(request_template, startAddress=cursor)
        request_path = output_dir / f"request-{number:02d}.json"
        request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        request_sha = digest(request_path)
        directory = output_dir / f"run-{number:02d}"
        process = subprocess.run(
            [str(reader), "scout-copy-typed-native",
             "--request", str(request_path), "--output", str(directory)],
            cwd=ROOT, capture_output=True, text=True,
            timeout=scan_ms / 1000 + 30, check=False,
        )
        # Exit 3 means the C# collector recorded a partial scope, not an error.
        require(process.returncode in (0, 3), "native-scanner-failed")
        result = check_index(directory / "index.json", request, request_sha, selection)
        require(pinned_selection(pid)["target"] == target, "epoch-changed-after-scan")
        require(digest(reader) == reader_sha, "reader-changed-after-scan")
        result["run"] = number
        result["requestSha256"] = request_sha
        require(result["startAddress"] == cursor, "scan-cursor-mismatch")
        results.append(result)
        if result["publishedSnapshots"] == 0:
            next_cursor = result["nextAddress"]
            if next_cursor is None:
                break
            cursor = checked_cursor(next_cursor, cursor)
        if number < max_scans and gap_seconds:
            time.sleep(gap_seconds)
    summary = {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-rr2r1-prefix-scan/1",
        "status": "candidate-captures-available" if any(
            row["publishedSnapshots"] for row in results) else "no-copied-candidate-in-bounded-scopes",
        "qualification": "prefix/snapshot evidence only; no decoded Lua frame, nonce/sequence, or freshness acceptance",
        "ownerHost": HOST,
        "target": request["target"],
        "readerSha256": reader_sha,
        "initialCursor": initial_cursor,
        "resumeSourceSha256": resume[1] if resume else None,
        "runs": results,
        "limitations": [
            "Each no-snapshot scan advances the C# memory cursor; a candidate scan is repeated to seek an advancing frame.",
            "Only bounded private-memory portions were examined; zero prefixes do not imply addon absence. Introducing a new cursor does not prove complete process coverage.",
            "Even two changing copied snapshots are not independently validated advancing RR2R1 frames.",
            "No addon command, reload, desktop focus, or game input was used.",
        ],
    }
    summary_path = output_dir / "summary.json"
    with summary_path.open("x", encoding="utf-8") as out:
        json.dump(summary, out, indent=2, allow_nan=False)
        out.write("\n")
    return summary_path, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-rr2r1-" + uuid.uuid4().hex))
    parser.add_argument("--scan-bytes", type=int, default=SCAN_BYTES)
    parser.add_argument("--scan-ms", type=int, default=SCAN_MS)
    parser.add_argument("--max-scans", type=int, default=SCAN_COUNT)
    parser.add_argument("--resume-summary", type=Path,
                        help="Prior exact-epoch scanner summary; its requests/index files are reverified")
    args = parser.parse_args(argv)
    try:
        path, result = collect(args.physical_pid, args.output_dir,
                               scan_bytes=args.scan_bytes, scan_ms=args.scan_ms,
                               max_scans=args.max_scans,
                               resume_summary=args.resume_summary)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({"status": result["status"], "summary": str(path),
                      "snapshots": [r["publishedSnapshots"] for r in result["runs"]],
                      "qualification": result["qualification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
