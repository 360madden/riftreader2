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

from scripts import assess_typed_wire_runs, physical_rift
from scripts.inspect_typed_resource import require_session_id
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
    # A copied-frame claim is not evidence unless its actual capture files are
    # present and match the C# scanner's hashes and process identity. This gate
    # also protects the RR2A1 physical collector, which reuses check_index().
    candidates = index.get("candidates")
    require(isinstance(candidates, list) and len(candidates) <= 128
            and all(isinstance(row, dict) for row in candidates),
            "scan-candidates-invalid")
    complete = [row for row in candidates if row.get("status") == "complete"]
    require(len(complete) == index["publishedSnapshots"],
            "scan-copy-count-mismatch")
    for number, row in enumerate(complete, 1):
        for kind in ("request", "snapshot"):
            name = row.get(kind + "File")
            expected_hash = row.get(kind + "Sha256")
            require(name == f"capture-{number:02d}.{kind}.json"
                    and isinstance(expected_hash, str)
                    and len(expected_hash) == 64
                    and all(c in "0123456789ABCDEFabcdef" for c in expected_hash),
                    "scan-copy-binding-invalid")
            source = Path(path).parent / name
            require(source.is_file() and not source.is_symlink(),
                    "scan-copy-source-missing")
            raw = source.read_bytes()
            require(len(raw) <= 8_000_000
                    and hashlib.sha256(raw).hexdigest().upper() == expected_hash.upper(),
                    "scan-copy-source-hash-mismatch")
            parsed = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
            if kind == "request":
                expected_target = {
                    "processId": target["processId"],
                    "processStartUtcTicks": int(target["processStartUtcTicks"]),
                    "executableSha256": BUILD_SHA,
                }
                require(parsed.get("schemaVersion") == 1
                        and parsed.get("evidenceKind") == "native-memory-snapshot-request/1"
                        and parsed.get("target") == expected_target,
                        "scan-copy-request-target-mismatch")
            else:
                require(parsed.get("status") == "complete"
                        and parsed.get("evidenceKind") == "native-memory-snapshot/1"
                        and parsed.get("identity") == observed,
                        "scan-copy-snapshot-identity-mismatch")
                source = parsed.get("source")
                require(isinstance(source, dict)
                        and source.get("requestEvidenceKind") == "native-memory-snapshot-request/1"
                        and str(source.get("requestSha256", "")).upper()
                            == str(row["requestSha256"]).upper(),
                        "scan-copy-source-request-mismatch")
    return {
        "status": index["status"],
        "indexSha256": hashlib.sha256(data).hexdigest().upper(),
        "prefixCount": len(scan["prefixAddresses"]),
        "publishedSnapshots": index["publishedSnapshots"],
        "sourceVerifiedSnapshots": len(complete),
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


def assess_saved(summary_path, output_dir, session_id):
    """Reassess source-verified retained RR2R1 runs without any process access.

    The saved capture identity is historical, never a current-process pin.
    Rechecks every original request, index and copied snapshot before decoding.
    """
    require_session_id(session_id)
    require(socket.gethostname().upper() == HOST, "wrong-host")
    summary_path = Path(summary_path)
    raw = summary_path.read_bytes()
    require(len(raw) <= 1_000_000, "saved-summary-too-large")
    summary = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    require(isinstance(summary, dict)
            and summary.get("schemaVersion") == 1
            and summary.get("evidenceKind") == "amd-physical-rr2r1-prefix-scan/1"
            and summary.get("ownerHost") == HOST,
            "saved-summary-invalid")
    target = summary.get("target")
    require(isinstance(target, dict)
            and type(target.get("processId")) is int and target["processId"] > 0
            and type(target.get("processStartUtcTicks")) is int
            and target["processStartUtcTicks"] > 0
            and str(target.get("executableSha256", "")).upper() == BUILD_SHA,
            "saved-target-invalid")
    rows = summary.get("runs")
    require(isinstance(rows, list) and 1 <= len(rows) <= 16,
            "saved-runs-invalid")
    copied = []
    for number, row in enumerate(rows, 1):
        require(isinstance(row, dict) and row.get("run") == number,
                "saved-run-invalid")
        request_path = summary_path.parent / f"request-{number:02d}.json"
        request_raw = request_path.read_bytes()
        require(len(request_raw) <= 16_384, "saved-request-too-large")
        request = json.loads(request_raw.decode("utf-8-sig"), object_pairs_hook=unique)
        request_sha = hashlib.sha256(request_raw).hexdigest().upper()
        require(request.get("target") == target and request.get("marker") == MARKER
                and request_sha == row.get("requestSha256"),
                "saved-request-mismatch")
        run_dir = summary_path.parent / f"run-{number:02d}"
        verified = check_index(run_dir / "index.json", request, request_sha,
                               {"target": target})
        require(all(verified.get(key) == row.get(key) for key in (
            "indexSha256", "status", "publishedSnapshots",
            "sourceVerifiedSnapshots", "prefixCount", "startAddress",
            "nextAddress", "scanStatus", "scanReason", "examinedBytes")),
            "saved-index-mismatch")
        if verified["sourceVerifiedSnapshots"] > 0:
            copied.append(number)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    reference = {"status": "insufficient-independent-copied-runs",
                 "runsWithCopiedSnapshots": len(copied)}
    if len(copied) >= 2:
        earlier, later = copied[-2:]
        assessment_dir = output_dir / "reference-assessment"
        result = assess_typed_wire_runs.assess(
            summary_path.parent / f"run-{earlier:02d}",
            summary_path.parent / f"run-{later:02d}",
            ROOT / "src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll",
            assessment_dir, maximum_run_gap_seconds=120.0,
            session_id=session_id)
        reference = {
            "status": result["status"],
            "runs": [earlier, later],
            "summarySha256": digest(assessment_dir / "summary.json"),
            "advancingComparisons": result["diagnostics"]["advancing"],
            "withinPairingWindow": result["pairingWindow"]["withinWindow"],
        }
    result = {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-rr2r1-retained-assessment/1",
        "status": reference["status"],
        "ownerHost": HOST,
        "historicalTarget": target,
        "sourceSummarySha256": hashlib.sha256(raw).hexdigest().upper(),
        "sourceVerifiedRuns": len(rows),
        "runsWithCopiedSnapshots": len(copied),
        "referenceAssessment": reference,
        "qualification": "Offline retained Lua-reference assessment only; not live process freshness, loaded-addon attestation, native XYZ semantics or movement",
    }
    receipt = output_dir / "summary.json"
    with receipt.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")
    return receipt, result


def collect(pid, output_dir, *, scan_bytes=SCAN_BYTES, scan_ms=SCAN_MS,
            max_scans=SCAN_COUNT, gap_seconds=1.0, resume_summary=None,
            session_id=None):
    if session_id is not None:
        require_session_id(session_id)
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
    # Only an explicit already-bound nonce enables strict offline RR2R1
    # frame assessment; a copied prefix is never a decoded observation.
    reference_assessment = None
    if session_id is not None:
        copied = [row for row in results if row["publishedSnapshots"] > 0]
        if len(copied) < 2:
            reference_assessment = {"status": "insufficient-independent-copied-runs",
                                    "runsWithCopiedSnapshots": len(copied)}
        else:
            earlier, later = copied[-2:]
            assessment_dir = output_dir / "reference-assessment"
            assessment = assess_typed_wire_runs.assess(
                output_dir / f"run-{earlier['run']:02d}",
                output_dir / f"run-{later['run']:02d}",
                ROOT / "src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll",
                assessment_dir, maximum_run_gap_seconds=120.0,
                session_id=session_id)
            reference_assessment = {
                "status": assessment["status"],
                "runs": [earlier["run"], later["run"]],
                "summarySha256": digest(assessment_dir / "summary.json"),
                "advancingComparisons": assessment["diagnostics"]["advancing"],
                "withinPairingWindow": assessment["pairingWindow"]["withinWindow"],
            }
    summary = {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-rr2r1-prefix-scan/1",
        "status": "candidate-captures-available" if any(
            row["publishedSnapshots"] for row in results) else "no-copied-candidate-in-bounded-scopes",
        "qualification": (
            "Optional nonce-selected strict offline Lua/API reference assessment; "
            "no loaded-addon attestation, native XYZ meaning, atomic freshness or movement causation"
            if session_id is not None else
            "prefix/snapshot evidence only; no decoded Lua frame, nonce/sequence, or freshness acceptance"),
        "ownerHost": HOST,
        "target": request["target"],
        "readerSha256": reader_sha,
        "initialCursor": initial_cursor,
        "resumeSourceSha256": resume[1] if resume else None,
        "runs": results,
        "referenceAssessment": reference_assessment,
        "limitations": [
            "Each no-snapshot scan advances the C# memory cursor; a candidate scan is repeated to seek an advancing frame.",
            "Only bounded private-memory portions were examined; zero prefixes do not imply addon absence. Introducing a new cursor does not prove complete process coverage.",
            "Copied snapshots alone do not establish advancing RR2R1 frames; strict pair assessment requires the exact already-bound reader nonce.",
            "A nonce-matching pair remains Lua/API reference evidence, not native XYZ meaning, loaded-addon attestation, atomic freshness, or movement causation.",
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--physical-pid", type=int)
    source.add_argument("--replay-summary", type=Path,
                        help="Offline revalidate retained RR2R1 runs; requires --session-id")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-rr2r1-" + uuid.uuid4().hex))
    parser.add_argument("--scan-bytes", type=int, default=SCAN_BYTES)
    parser.add_argument("--scan-ms", type=int, default=SCAN_MS)
    parser.add_argument("--max-scans", type=int, default=SCAN_COUNT)
    parser.add_argument("--resume-summary", type=Path,
                        help="Prior exact-epoch scanner summary; its requests/index files are reverified")
    parser.add_argument("--session-id",
                        help="Exact already-bound RR2R1 reader nonce for offline pair assessment")
    args = parser.parse_args(argv)
    try:
        if args.replay_summary is not None:
            require(args.session_id is not None, "replay-requires-session-id")
            require(args.resume_summary is None, "replay-cannot-resume-scanning")
            path, result = assess_saved(args.replay_summary, args.output_dir,
                                        args.session_id)
        else:
            path, result = collect(args.physical_pid, args.output_dir,
                                   scan_bytes=args.scan_bytes, scan_ms=args.scan_ms,
                                   max_scans=args.max_scans,
                                   resume_summary=args.resume_summary,
                                   session_id=args.session_id)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({"status": result["status"], "summary": str(path),
                      "snapshots": [r["publishedSnapshots"] for r in result.get("runs", [])],
                      "qualification": result["qualification"],
                      "referenceAssessment": result["referenceAssessment"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
