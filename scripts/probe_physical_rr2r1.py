"""Read-only bounded RR2R1 candidate search on the verified local RIFT host.

Reuses the existing C# scout-copy-typed-native collector. A prefix match is
NOT a decoded, fresh Lua frame; use the existing typed inspector to qualify it.
No addon binding, game input, focus changes, or VM access.
"""
from __future__ import annotations

import argparse
from collections import Counter
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

# The native prefix scout uses no build-specific RVAs. Both exact executable
# builds are already qualified for process/epoch pinning; unknown hashes refuse.
UPDATED_SHA = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
SUPPORTED_SHAS = frozenset((BUILD_SHA, UPDATED_SHA))

MARKER = "RR2R1|"
SCAN_BYTES = 256 * 1024 * 1024
SCAN_MS = 15_000
SCAN_COUNT = 8
DECODER_CLI = ROOT / "src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll"


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


def pinned_selection(pid, expected_host=None):
    host = socket.gethostname()
    require(physical_rift.valid_host_name(host)
            and (expected_host is None or (physical_rift.valid_host_name(expected_host)
                 and expected_host.casefold() == host.casefold())), "wrong-host")
    selection = physical_rift.select_physical(host, pid)
    require(selection.get("status") == "ready" and selection.get("ownerHost") == host,
            "physical-selection-unavailable")
    identity = selection.get("target")
    require(isinstance(identity, dict) and identity.get("processId") == pid
            and str(identity.get("hostName", "")).casefold() == host.casefold()
            and str(identity.get("executableSha256", "")).upper() in SUPPORTED_SHAS
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
            and str(observed.get("executableSha256", "")).upper()
                == str(target["executableSha256"]).upper(),
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
            and all(isinstance(row, dict)
                    and isinstance(row.get("status"), str)
                    and 1 <= len(row["status"]) <= 80 for row in candidates),
            "scan-candidates-invalid")
    status_counts = dict(sorted(Counter(row["status"] for row in candidates).items()))
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
                    "executableSha256": str(target["executableSha256"]).upper(),
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
        "candidateStatusCounts": status_counts,
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
                "executableSha256": str(target["executableSha256"]).upper()}
    require(summary.get("schemaVersion") == 1 and
            summary.get("evidenceKind") == "amd-physical-rr2r1-prefix-scan/1" and
            physical_rift.valid_host_name(summary.get("ownerHost")) and
            summary["ownerHost"].casefold() == selection["ownerHost"].casefold()
            and summary.get("target") == expected and
            summary.get("readerSha256") == reader_sha and
            summary.get("status") == "no-copied-candidate-in-bounded-scopes",
            "resume-epoch-reader-or-status-mismatch")
    rows = summary.get("runs")
    require(isinstance(rows, list) and 1 <= len(rows) <= 16,
            "resume-runs-invalid")
    prior = None
    initial_cursor = checked_cursor(summary.get("initialCursor"))
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
                request["startAddress"] == (
                    initial_cursor if prior is None else prior),
                "resume-request-chain-mismatch")
        receipt_path = path.parent / f"run-{number:02d}" / "index.json"
        verified = check_index(receipt_path, request, request_sha, selection)
        require(all(verified.get(key) == row.get(key) for key in
                    ("indexSha256", "status", "publishedSnapshots", "prefixCount",
                     "startAddress", "nextAddress", "scanStatus", "scanReason",
                     "examinedBytes")), "resume-receipt-mismatch")
        prior = checked_cursor(row.get("nextAddress"), row["startAddress"])
    return prior, hashlib.sha256(raw).hexdigest().upper()


def assess_saved(summary_path, output_dir, session_id=None, *,
                 decoder_cli=DECODER_CLI, dotnet="dotnet"):
    """Audit retained RR2R1 sources offline; decode only with an authentic nonce.

    The saved capture identity is historical, never a current-process pin.
    Rechecks every original request, index and copied snapshot before decoding.
    """
    if session_id is not None:
        require_session_id(session_id)
    summary_path = Path(summary_path)
    raw = summary_path.read_bytes()
    require(len(raw) <= 1_000_000, "saved-summary-too-large")
    summary = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    require(isinstance(summary, dict)
            and summary.get("schemaVersion") == 1
            and summary.get("evidenceKind") == "amd-physical-rr2r1-prefix-scan/1"
            and physical_rift.valid_host_name(summary.get("ownerHost")),
            "saved-summary-invalid")
    target = summary.get("target")
    require(isinstance(target, dict)
            and type(target.get("processId")) is int and target["processId"] > 0
            and type(target.get("processStartUtcTicks")) is int
            and target["processStartUtcTicks"] > 0
            and str(target.get("executableSha256", "")).upper() in SUPPORTED_SHAS,
            "saved-target-invalid")
    rows = summary.get("runs")
    require(isinstance(rows, list) and 1 <= len(rows) <= 16,
            "saved-runs-invalid")
    copied = []
    run_diagnostics = []
    expected_cursor = checked_cursor(summary.get("initialCursor"))
    for number, row in enumerate(rows, 1):
        require(isinstance(row, dict) and row.get("run") == number,
                "saved-run-invalid")
        request_path = summary_path.parent / f"request-{number:02d}.json"
        request_raw = request_path.read_bytes()
        require(len(request_raw) <= 16_384, "saved-request-too-large")
        request = json.loads(request_raw.decode("utf-8-sig"), object_pairs_hook=unique)
        request_sha = hashlib.sha256(request_raw).hexdigest().upper()
        require(expected_cursor is not None and request.get("startAddress") == expected_cursor,
                "saved-cursor-chain-mismatch")
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
        run_diagnostics.append({
            "run": number,
            "scanStatus": verified["scanStatus"],
            "scanReason": verified["scanReason"],
            "examinedBytes": verified["examinedBytes"],
            "prefixCount": verified["prefixCount"],
            "candidateStatusCounts": verified["candidateStatusCounts"],
            "sourceVerifiedSnapshots": verified["sourceVerifiedSnapshots"],
        })
        if verified["sourceVerifiedSnapshots"] > 0:
            copied.append(number)
        if verified["publishedSnapshots"] == 0:
            following = verified["nextAddress"]
            expected_cursor = (checked_cursor(following, expected_cursor)
                               if following is not None else None)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    reference = {"status": "insufficient-independent-copied-runs",
                 "runsWithCopiedSnapshots": len(copied)}
    if len(copied) >= 2 and session_id is None:
        reference = {"status": "nonce-unavailable-source-only",
                     "runsWithCopiedSnapshots": len(copied)}
    if len(copied) >= 2 and session_id is not None:
        earlier, later = copied[-2:]
        assessment_dir = output_dir / "reference-assessment"
        result = assess_typed_wire_runs.assess(
            summary_path.parent / f"run-{earlier:02d}",
            summary_path.parent / f"run-{later:02d}",
            Path(decoder_cli),
            assessment_dir, maximum_run_gap_seconds=120.0,
            dotnet=dotnet, session_id=session_id)
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
        "ownerHost": summary["ownerHost"],
        "historicalTarget": target,
        "sourceSummarySha256": hashlib.sha256(raw).hexdigest().upper(),
        "sourceVerifiedRuns": len(rows),
        "runsWithCopiedSnapshots": len(copied),
        "runDiagnostics": run_diagnostics,
        "referenceAssessment": reference,
        "qualification": (
            "Offline source-integrity audit only; no nonce decoding, authenticated freshness, current process, loaded-addon attestation, native XYZ semantics or movement"
            if session_id is None else
            "Offline retained Lua-reference assessment only; not live process freshness, loaded-addon attestation, native XYZ semantics or movement"),
    }
    receipt = output_dir / "summary.json"
    with receipt.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")
    return receipt, result


def collect(pid, output_dir, *, scan_bytes=SCAN_BYTES, scan_ms=SCAN_MS,
            max_scans=SCAN_COUNT, gap_seconds=1.0, resume_summary=None,
            session_id=None, start_address="0x10000", expected_host=None,
            native_reader=None, decoder_cli=DECODER_CLI, dotnet="dotnet"):
    if session_id is not None:
        require_session_id(session_id)
    require(type(pid) is int and 0 < pid < 2**31, "explicit-pid-required")
    checked_cursor(start_address)
    require(start_address == f"0x{int(start_address[2:], 16):X}",
            "noncanonical-start-address")
    require(resume_summary is None or start_address == "0x10000",
            "start-address-conflicts-with-resume")
    require(type(scan_bytes) is int and 1_048_576 <= scan_bytes <= 536_870_912
            and scan_bytes % 4096 == 0
            and type(scan_ms) is int and 1000 <= scan_ms <= 30_000
            and type(max_scans) is int and 1 <= max_scans <= 16
            and type(gap_seconds) in (int, float) and 0 <= gap_seconds <= 10,
            "scan-bounds-invalid")
    reader = physical_rift._native_reader_path(native_reader)
    require(reader.is_file(), "existing-dotnet-reader-unavailable")
    selection = pinned_selection(pid, expected_host)
    host = selection["ownerHost"]
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
            "executableSha256": str(target["executableSha256"]).upper(),
        },
        "startAddress": "0x10000",
        "maxScanBytes": scan_bytes,
        "maxDurationMilliseconds": scan_ms,
        "maxRegionCount": 32768,
        "maxMatchCount": 128,
        "maxCopiedCandidates": 8,
        "marker": MARKER,
    }
    output_dir = Path(output_dir).absolute()
    output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    cursor = resume[0] if resume else start_address
    initial_cursor = cursor
    for number in range(1, max_scans + 1):
        require(pinned_selection(pid, host)["target"] == target, "epoch-changed-before-scan")
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
        require(pinned_selection(pid, host)["target"] == target, "epoch-changed-after-scan")
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
                Path(decoder_cli),
                assessment_dir, maximum_run_gap_seconds=120.0,
                dotnet=dotnet, session_id=session_id)
            reference_assessment = {
                "status": assessment["status"],
                "runs": [earlier["run"], later["run"]],
                "summarySha256": digest(assessment_dir / "summary.json"),
                "advancingComparisons": assessment["diagnostics"]["advancing"],
                "withinPairingWindow": assessment["pairingWindow"]["withinWindow"],
            }
    statuses = Counter()
    for row in results:
        statuses.update(row["candidateStatusCounts"])
    measured_bytes = [row["examinedBytes"] for row in results]
    next_resume = (checked_cursor(results[-1]["nextAddress"], results[-1]["startAddress"])
                   if not any(row["publishedSnapshots"] for row in results)
                   and results[-1]["nextAddress"] is not None else None)
    # This is cumulative work, not unique memory coverage: copied candidates
    # deliberately cause rescanning of the same address scope.
    scan_work = {
        "scansCompleted": len(results),
        "examinedBytes": (sum(measured_bytes) if all(
            type(value) is int and value >= 0 for value in measured_bytes) else None),
        "prefixesObserved": sum(row["prefixCount"] for row in results),
        "copiedSnapshots": sum(row["sourceVerifiedSnapshots"] for row in results),
        "candidateStatusCounts": dict(sorted(statuses.items())),
        "nextResumeCursor": next_resume,
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
        "ownerHost": host,
        "target": request["target"],
        "readerSha256": reader_sha,
        "initialCursor": initial_cursor,
        "resumeSourceSha256": resume[1] if resume else None,
        "runs": results,
        "scanWork": scan_work,
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
                        help="Offline source audit; --session-id optionally enables strict nonce-bound pair assessment")
    parser.add_argument("--expected-host", help="require this local Windows hostname for capture")
    parser.add_argument("--native-reader", type=Path,
                        help="absolute local path to a published RiftReader2.Live.exe for capture")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-rr2r1-" + uuid.uuid4().hex))
    parser.add_argument("--scan-bytes", type=int, default=SCAN_BYTES)
    parser.add_argument("--start-address", default="0x10000",
                        help="canonical exact-process user-space scan cursor, e.g. 0x13300000; cannot combine with --resume-summary")
    parser.add_argument("--scan-ms", type=int, default=SCAN_MS)
    parser.add_argument("--max-scans", type=int, default=SCAN_COUNT)
    parser.add_argument("--resume-summary", type=Path,
                        help="Prior exact-epoch scanner summary; its requests/index files are reverified")
    parser.add_argument("--session-id",
                        help="Exact already-bound RR2R1 reader nonce for offline pair assessment")
    parser.add_argument("--cli", type=Path, default=DECODER_CLI,
                        help="published RiftReader2.Cli.dll for nonce-bound assessment")
    parser.add_argument("--dotnet", default="dotnet",
                        help="local .NET host for nonce-bound assessment")
    args = parser.parse_args(argv)
    try:
        if args.replay_summary is not None:
            require(args.expected_host is None, "replay-does-not-select-live-host")
            require(args.native_reader is None, "replay-does-not-select-native-reader")
            require(args.resume_summary is None, "replay-cannot-resume-scanning")
            require(args.start_address == "0x10000", "replay-cannot-select-start-address")
            path, result = assess_saved(args.replay_summary, args.output_dir,
                                        args.session_id, decoder_cli=args.cli, dotnet=args.dotnet)
        else:
            path, result = collect(args.physical_pid, args.output_dir,
                                   scan_bytes=args.scan_bytes, scan_ms=args.scan_ms,
                                   max_scans=args.max_scans,
                                   resume_summary=args.resume_summary,
                                   session_id=args.session_id, start_address=args.start_address,
                                   expected_host=args.expected_host, native_reader=args.native_reader,
                                   decoder_cli=args.cli, dotnet=args.dotnet)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({"status": result["status"], "summary": str(path),
                      "snapshots": [r["publishedSnapshots"] for r in result.get("runs", [])],
                       "candidateStatusCounts": [r["candidateStatusCounts"] for r in
                                                 result.get("runs", result.get("runDiagnostics", []))],
                      "qualification": result["qualification"],
                      "referenceAssessment": result["referenceAssessment"],
                      "scanWork": result.get("scanWork")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
