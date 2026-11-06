"""Offline-only tests for strict two-run native typed inline ZIP recovery."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import warnings
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from scripts.verify_typed_inline_archive import (
    ArchiveError, verify_archive, verify_and_publish,
)

PID = 6940
TICKS = 639284177321390013
GAME = "A" * 64
BUNDLE = "B" * 64


def encode(value: object) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def request() -> dict:
    return {
        "schemaVersion": 1,
        "evidenceKind": "native-typed-inline-capture-request/1",
        "target": {
            "processId": PID, "processStartUtcTicks": TICKS,
            "executableSha256": GAME,
        },
        "startAddress": "0x10000",
        "maxScanBytes": 536870912,
        "maxDurationMilliseconds": 30000,
        "maxRegionCount": 32768,
        "maxMatchCount": 128,
        "maxCopiedCandidates": 8,
    }


def capture_pair() -> tuple[bytes, bytes]:
    src = {
        "schemaVersion": 1,
        "evidenceKind": "native-memory-snapshot-request/1",
        "target": request()["target"],
        "maxDurationMilliseconds": 30000,
        "ranges": [{
            "addressKind": "absolute-session-address",
            "address": "0xD3D9000",
            "byteLength": 28672,
        }],
    }
    src_bytes = encode(src)
    chunks = []
    for index in range(7):
        raw = bytearray(4096)
        if index == 2:
            raw[128:139] = b"RRAPIVAL2|{"
        chunks.append({
            "address": hex(0xD3D9000 + index * 4096),
            "requestedByteLength": 4096,
            "status": "success",
            "bytesRead": 4096,
            "bytesBase64": base64.b64encode(raw).decode("ascii"),
            "bytesSha256": digest(raw),
            "win32ErrorCode": None,
            "reason": None,
        })
    snapshot = {
        "schemaVersion": 1,
        "evidenceKind": "native-memory-snapshot/1",
        "source": {
            "requestEvidenceKind": "native-memory-snapshot-request/1",
            "requestSha256": digest(src_bytes),
            "requestSha256Verification": "producer-declared",
            "implementation": {
                "deploymentKind": "single-file-bundle",
                "bundleSha256": BUNDLE,
            },
        },
        "identity": request()["target"],
        "status": "complete",
        "chunks": chunks,
    }
    return src_bytes, encode(snapshot)


def members(*, with_capture: bool = True) -> dict[str, bytes]:
    result = {}
    for ordinal, run in enumerate(("run-01", "run-02")):
        original = request()
        original_bytes = encode(original)
        start = "2026-10-24T12:00:00Z" if ordinal == 0 else "2026-10-24T12:00:04Z"
        end = "2026-10-24T12:00:01Z" if ordinal == 0 else "2026-10-24T12:00:05Z"
        report = {
            "schemaVersion": 1,
            "evidenceKind": "native-typed-inline-capture/1",
            "requestSha256": digest(original_bytes),
            "request": original,
            "identity": request()["target"],
            "implementation": {"deploymentKind": "single-file-bundle", "bundleSha256": BUNDLE},
            "startedAtUtc": start,
            "completedAtUtc": end,
            "status": "partial",
            "reason": "byte-budget-exceeded",
            "candidates": [],
            "publishedSnapshots": 0,
        }
        result[f"{run}/input.request.json"] = original_bytes
        if with_capture:
            src, snap = capture_pair()
            result[f"{run}/capture-01.request.json"] = src
            result[f"{run}/capture-01.snapshot.json"] = snap
            report["publishedSnapshots"] = 1
            report["candidates"].append({
                "markerAddress": "0xD3DB080",
                "status": "complete",
                "requestFile": "capture-01.request.json",
                "requestSha256": digest(src),
                "snapshotFile": "capture-01.snapshot.json",
                "snapshotSha256": digest(snap),
            })
        result[f"{run}/index.json"] = encode(report)
    return result


def archive_file(folder: Path, payload: dict[str, bytes]) -> tuple[Path, str]:
    path = folder / "evidence.zip"
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        for name, contents in payload.items():
            archive.writestr(name, contents)
    return path, digest(path.read_bytes())


def update_json(payload: dict[str, bytes], key: str, apply):
    data = json.loads(payload[key])
    apply(data)
    payload[key] = encode(data)


def verify(path: Path, sha: str):
    return verify_archive(path, sha, pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)


class TypedInlineArchiveTests(unittest.TestCase):
    def test_two_exact_capture_runs_publish_all_originals_with_receipt(self):
        original = members()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive, sha = archive_file(base, original)
            output = base / "recovered"
            proof = verify_and_publish(archive, sha, output,
                                       pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
            self.assertEqual([x["snapshotCount"] for x in proof["runs"]], [1, 1])
            self.assertEqual(len(proof["files"]), 8)
            self.assertFalse(proof["typedFrameQualified"])
            self.assertFalse(proof["nativeXyzQualified"])
            for name, raw in original.items():
                self.assertEqual((output / name).read_bytes(), raw)
            self.assertEqual(json.loads((output / "archive-proof.json").read_text())["archiveSha256"], sha)
            before = (output / "archive-proof.json").read_bytes()
            with self.assertRaisesRegex(ArchiveError, "output must be absent"):
                verify_and_publish(archive, sha, output,
                                   pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
            self.assertEqual((output / "archive-proof.json").read_bytes(), before)

    def test_partial_scans_with_zero_copies_preserved_without_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive, sha = archive_file(base, members(with_capture=False))
            files, proof = verify(archive, sha)
            self.assertEqual(len(files), 4)
            self.assertEqual([x["snapshotCount"] for x in proof["runs"]], [0, 0])
            self.assertEqual([x["status"] for x in proof["runs"]], ["partial", "partial"])

    def test_bad_expected_archive_hash_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive, sha = archive_file(base, members())
            with self.assertRaisesRegex(ArchiveError, "ZIP SHA-256"):
                verify_and_publish(archive, "0" * 64, base / "out",
                                   pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
            self.assertFalse((base / "out").exists())
            self.assertNotEqual(sha, "0" * 64)

    def test_unknown_paths_and_extra_files_are_rejected(self):
        for invalid in ("../escape.json", "/absolute.json", "run-01/other.json",
                        "run-01/../../run-02/index.json", "run-03/index.json"):
            with self.subTest(path=invalid), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                data = members()
                data[invalid] = b"{}"
                archive, sha = archive_file(base, data)
                with self.assertRaisesRegex(ArchiveError, "unexpected ZIP member"):
                    verify(archive, sha)

    def test_duplicate_zip_path_rejected_even_if_contents_equal(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive = base / "evidence.zip"
            data = members()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with ZipFile(archive, "x", compression=ZIP_DEFLATED) as destination:
                    for name, content in data.items():
                        destination.writestr(name, content)
                    destination.writestr("run-01/index.json", data["run-01/index.json"])
            with self.assertRaisesRegex(ArchiveError, "duplicate ZIP member"):
                verify(archive, digest(archive.read_bytes()))

    def test_exact_game_identity_and_bundle_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive, sha = archive_file(base, members())
            for options in ({"pid": PID + 1}, {"ticks": TICKS + 1},
                            {"game_sha": "C" * 64}, {"bundle_sha": "D" * 64}):
                with self.subTest(options=options):
                    args = {"pid": PID, "ticks": TICKS, "game_sha": GAME, "bundle_sha": BUNDLE}
                    args.update(options)
                    with self.assertRaisesRegex(ArchiveError, "target process epoch|bundle"):
                        verify_archive(archive, sha, **args)

    def test_manifest_snapshot_digest_tamper_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = members()
            data["run-01/capture-01.snapshot.json"] += b"\n"
            archive, sha = archive_file(base, data)
            with self.assertRaisesRegex(ArchiveError, "original snapshot hash"):
                verify(archive, sha)

    def test_chunk_tamper_detected_even_when_outer_manifest_hash_updated(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = members()
            snap_name = "run-01/capture-01.snapshot.json"
            index_name = "run-01/index.json"
            update_json(data, snap_name, lambda doc: doc["chunks"][0].update(bytesSha256="F" * 64))
            update_json(data, index_name, lambda doc: doc["candidates"][0].update(
                snapshotSha256=digest(data[snap_name])))
            archive, sha = archive_file(base, data)
            with self.assertRaisesRegex(ArchiveError, "chunk 0: byte length or SHA"):
                verify(archive, sha)

    def test_stale_embedded_request_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = members()
            update_json(data, "run-01/index.json",
                        lambda doc: doc.update(requestSha256="F" * 64))
            archive, sha = archive_file(base, data)
            with self.assertRaisesRegex(ArchiveError, "original input request SHA"):
                verify(archive, sha)

    def test_same_or_reversed_acquisition_rejected(self):
        for start in ("2026-10-24T12:00:01Z", "2026-10-24T11:59:01Z"):
            with self.subTest(start=start), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                data = members()
                update_json(data, "run-02/index.json",
                            lambda doc: doc.update(startedAtUtc=start, completedAtUtc="2026-10-24T12:00:06Z"))
                archive, sha = archive_file(base, data)
                with self.assertRaisesRegex(ArchiveError, "not sufficiently separated"):
                    verify(archive, sha)

    def test_missing_original_input_request_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = members()
            del data["run-02/input.request.json"]
            archive, sha = archive_file(base, data)
            with self.assertRaisesRegex(ArchiveError, "original input request"):
                verify(archive, sha)

    def test_extra_unreferenced_capture_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            data = members()
            data["run-01/capture-02.request.json"] = data["run-01/capture-01.request.json"]
            archive, sha = archive_file(base, data)
            with self.assertRaisesRegex(ArchiveError, "unreferenced run files"):
                verify(archive, sha)

    def test_archive_symlink_member_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive = base / "evidence.zip"
            with ZipFile(archive, "x", compression=ZIP_DEFLATED) as zipped:
                for name, raw in members().items():
                    if name == "run-01/index.json":
                        meta = ZipInfo(name)
                        meta.create_system = 3
                        meta.external_attr = (0o120777 << 16)
                        zipped.writestr(meta, raw)
                    else:
                        zipped.writestr(name, raw)
            with self.assertRaisesRegex(ArchiveError, "symbolic ZIP member"):
                verify(archive, digest(archive.read_bytes()))


    def test_real_guest_claim_and_upload_receipts_must_match_every_byte(self):
        def receipts(base, path, sha):
            size = path.stat().st_size
            claim = {
                "schemaVersion": 1,
                "evidenceKind": "guest-typed-inline-zip-claim/1",
                "source": "guest-declared-only",
                "guest": "192.168.56.128",
                "zipSha256": sha,
                "zipBytes": size,
                "target": request()["target"],
                "bundleSha256": BUNDLE,
            }
            upload = {
                "schemaVersion": 1,
                "purpose": "content-addressed-guest-map-transfer",
                "state": "received",
                "destination": str(path),
                "bytes": size,
                "sha256": sha.lower(),
                "guest": "192.168.56.128",
            }
            return claim, upload

        mutations = (
            ("claim-size", lambda a, b: a.update(zipBytes=a["zipBytes"] + 1)),
            ("received-size", lambda a, b: b.update(bytes=b["bytes"] + 1)),
            ("wrong-receiver-peer", lambda a, b: b.update(guest="192.0.2.33")),
            ("wrong-source-bundle", lambda a, b: a.update(bundleSha256="C" * 64)),
            ("wrong-zip-path", lambda a, b: b.update(destination=str(Path(b["destination"]).with_name("other.zip")))),
        )
        for case, mutate in (*mutations, ("valid", lambda a, b: None)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                original, sha = archive_file(base, members())
                claim, upload = receipts(base, original, sha)
                mutate(claim, upload)
                claim_path = base / "claim.json"
                upload_path = base / "upload.json"
                claim_path.write_text(json.dumps(claim), encoding="utf-8")
                upload_path.write_text(json.dumps(upload), encoding="utf-8")
                output = base / "recover"
                kwargs = dict(pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE,
                              claim_path=claim_path, upload_path=upload_path)
                if case == "valid":
                    result = verify_and_publish(original, sha, output, **kwargs)
                    self.assertEqual(result["guestTransfer"]["zipBytes"], original.stat().st_size)
                    self.assertEqual(result["guestTransfer"]["guest"], "192.168.56.128")
                    self.assertEqual(result["guestTransfer"]["state"],
                                     "claim-upload-and-extracted-bytes-agree")
                else:
                    with self.assertRaises((ArchiveError, OSError)):
                        verify_and_publish(original, sha, output, **kwargs)
                    self.assertFalse(output.exists())

    def test_partial_guest_transfer_receipts_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive, sha = archive_file(base, members())
            fake = base / "claim.json"
            fake.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ArchiveError, "both claim and upload"):
                verify_and_publish(archive, sha, base / "out",
                                   pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE,
                                   claim_path=fake)

if __name__ == "__main__":
    unittest.main()
