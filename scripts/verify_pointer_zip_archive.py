"""Strict recovery of two native pointer originals and SHA-linked Lua comparison.

Requires an exact three-member guest ZIP. Reuses the existing one-use claim /
upload cross-receipt verifier, then independently reviews both raw pointer
windows without ever reading a game process or contacting VMware.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from scripts.review_current_pointer_xyz import EvidenceError, review
from scripts.verify_typed_inline_archive import (
    ArchiveError, _sha, _sha_match, _transfer_proof,
)

ALLOWED = {
    "rr2-v16ptr-a.json",
    "rr2-v16ptr-a-report.json",
    "rr2-v16ptr-b-report.json",
}
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_JSON_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 384 * 1024
MIN_CAPTURE_SEPARATION_SECONDS = 3.0


def read_archive(archive: Path, expected_digest: str) -> tuple[dict[str, bytes], str, int]:
    if not archive.is_file() or archive.is_symlink():
        raise ArchiveError("pointer archive must be a real file")
    size = archive.stat().st_size
    if not 0 < size <= MAX_ARCHIVE_BYTES:
        raise ArchiveError("pointer archive outside 2 MiB bound")
    raw = archive.read_bytes()
    sha = _sha(raw)
    if not _sha_match(expected_digest, sha):
        raise ArchiveError("pointer ZIP differs from guest-declared SHA-256")
    contents = {}
    try:
        with ZipFile(BytesIO(raw)) as src:
            info = src.infolist()
            if len(info) != len(ALLOWED) or {x.filename for x in info} != ALLOWED:
                raise ArchiveError("pointer ZIP requires exactly three distinct known names")
            total = 0
            for entry in info:
                if (entry.is_dir() or entry.flag_bits & 0x1
                        or entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
                        or stat.S_ISLNK((entry.external_attr >> 16) & 0xFFFF)
                        or not 0 < entry.file_size <= MAX_JSON_BYTES
                        or entry.filename.startswith((".", "/", "\\"))
                        or "/" in entry.filename or "\\" in entry.filename):
                    raise ArchiveError("pointer ZIP contains unsafe member metadata")
                total += entry.file_size
                if total > MAX_TOTAL_BYTES:
                    raise ArchiveError("pointer ZIP expands beyond 384 KiB")
                with src.open(entry) as stream:
                    body = stream.read(entry.file_size + 1)
                if len(body) != entry.file_size:
                    raise ArchiveError("pointer ZIP member length inconsistent")
                contents[entry.filename] = body
    except (BadZipFile, EOFError) as err:
        raise ArchiveError("pointer ZIP corrupt") from err
    return contents, sha, len(raw)


def verify_and_publish(archive: Path, archive_sha: str, request: Path,
                       source: Path, source_sha: str, output: Path, *,
                       pid: int, ticks: int, game_sha: str, bundle_sha: str,
                       claim_path: Path | None = None,
                       upload_path: Path | None = None,
                       expected_guest: str = "192.168.56.128",
                       tolerance: float = 0.02) -> dict:
    if not output.parent.is_dir() or output.exists() or output.is_symlink():
        raise ArchiveError("pointer recovery output folder must be new")
    files, actual_sha, byte_length = read_archive(archive, archive_sha)
    if not request.is_file() or request.is_symlink():
        raise ArchiveError("original canonical pointer request absent")
    requested = request.read_bytes()
    if files["rr2-v16ptr-a.json"] != requested:
        raise ArchiveError("guest pointer request bytes differ from pinned host original")
    transfer = _transfer_proof(
        archive, actual_sha, byte_length, claim_path=claim_path,
        upload_path=upload_path, pid=pid, ticks=ticks,
        game_sha=game_sha, bundle_sha=bundle_sha,
        expected_guest=expected_guest, claim_kind="pointer",
    )
    with TemporaryDirectory(prefix=".rr2-v16-pointer-stage-", dir=output.parent) as temp:
        stage = Path(temp)
        for name, data in sorted(files.items()):
            with (stage / name).open("xb") as dest:
                dest.write(data)
                dest.flush()
                os.fsync(dest.fileno())
        source_reports = []
        for name in ("rr2-v16ptr-a-report.json", "rr2-v16ptr-b-report.json"):
            from scripts.review_current_pointer_xyz import read_source
            report, digest = read_source(stage / name)
            implementation = report.get("implementation")
            if (not isinstance(implementation, dict)
                    or not _sha_match(implementation.get("bundleSha256"), bundle_sha)):
                raise ArchiveError("pointer report's actual executable bundle differs")
            source_reports.append((name, digest))
        derived = review(
            stage / "rr2-v16ptr-a-report.json",
            stage / "rr2-v16ptr-b-report.json",
            stage / "rr2-v16ptr-a.json",
            source, source_sha, tolerance,
        )
        t0, t1 = [item["completedAtUtc"] for item in derived["nativeSamples"]]
        from datetime import datetime
        separation = (datetime.fromisoformat(t1) - datetime.fromisoformat(t0)).total_seconds()
        if separation < MIN_CAPTURE_SEPARATION_SECONDS:
            raise ArchiveError("native reports not separated by three seconds")
        target = derived["target"]
        if (target != {"processId": pid, "processStartUtcTicks": ticks,
                       "executableSha256": game_sha}):
            raise ArchiveError("pointer request differs from declared guest game epoch")
        proof = {
            "schemaVersion": 1,
            "evidenceKind": "native-pointer-two-run-archive-proof/1",
            "archiveSha256": actual_sha,
            "archiveBytes": byte_length,
            "target": target,
            "bundleSha256": bundle_sha,
            "files": [
                {"path": name, "sha256": _sha(body), "bytes": len(body)}
                for name, body in sorted(files.items())
            ],
            "nativeAcquisitions": source_reports,
            "separationSeconds": separation,
            "reviewStatus": derived["status"],
            "qualification": derived["qualification"],
            "transferEvidence": (
                transfer if transfer is not None else
                {"state": "host-fixture-only-no-guest-provenance"}
            ),
        }
        for name, content in (
                ("archive-proof.json", proof), ("position-review.json", derived)):
            with (stage / name).open("x", encoding="utf-8", newline="\n") as dest:
                json.dump(content, dest, indent=2, allow_nan=False)
                dest.write("\n")
                dest.flush()
                os.fsync(dest.fileno())
        if output.exists() or output.is_symlink():
            raise ArchiveError("pointer recovery output appeared during validation")
        os.rename(stage, output)
    return proof


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--process-start-ticks", type=int, required=True)
    parser.add_argument("--game-sha256", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--claim-receipt", type=Path)
    parser.add_argument("--upload-receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        proof = verify_and_publish(
            args.archive, args.expected_sha256, args.request, args.source,
            args.source_sha256, args.output, pid=args.process_id,
            ticks=args.process_start_ticks, game_sha=args.game_sha256,
            bundle_sha=args.bundle_sha256, claim_path=args.claim_receipt,
            upload_path=args.upload_receipt)
    except (ArchiveError, EvidenceError, ValueError, TypeError, KeyError,
            OSError, BadZipFile, OverflowError) as err:
        print(json.dumps({"status": "blocked", "reason": str(err)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "verified-pointer-archive",
                      "reviewStatus": proof["reviewStatus"],
                      "qualification": proof["qualification"],
                      "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
