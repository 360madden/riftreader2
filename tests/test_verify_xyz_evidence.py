"""Offline tests for strict XYZ returned-evidence package verification."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile, ZipInfo

import scripts.verify_xyz_evidence as verifier
from scripts.verify_xyz_evidence import EvidenceError, main, verify


READER = "A" * 64
PROFILE = "B" * 64
GAME = "C" * 64


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def target(pid: int) -> dict:
    return {
        "processId": pid,
        "processStartUtcTicks": 639285359295548343 + pid,
        "executablePath": "C:\\RIFT_TRANSFER\\RIFT\\rift_x64.exe",
        "executableSha256": GAME,
    }


def package(files: dict[str, bytes]) -> dict:
    return {
        "schemaVersion": 1,
        "purpose": "xyz-interface-full-game-restart-gui-evidence",
        "createdAtUtc": "2026-10-25T14:44:11.4145304Z",
        "qualification": "same-build validation only; patch recovery deferred",
        "transport": "pointer-named strict routes reused only as bounded ZIP transport",
        "readerSha256": READER,
        "profileSha256": PROFILE,
        "gameSha256": GAME,
        "oldTarget": target(11712),
        "afterTarget": target(1224),
        "panelExitCode": 0,
        "files": [{"path": name, "byteLength": len(raw), "sha256": digest(raw)}
                  for name, raw in sorted(files.items())],
    }


def archive_file(root: Path, files: dict[str, bytes] | None = None, *,
                 manifest: dict | bytes | None = None,
                 extra: list[tuple[str | ZipInfo, bytes]] | None = None,
                 compression=ZIP_DEFLATED) -> tuple[Path, str, int]:
    files = {"panel-01/panel-session.json": b'{"schemaVersion":1}\n',
             "empty.stdout.txt": b""} if files is None else files
    if manifest is None:
        manifest = package(files)
    manifest_raw = manifest if isinstance(manifest, bytes) else (
        json.dumps(manifest, separators=(",", ":")) + "\n").encode()
    path = root / "evidence.zip"
    with ZipFile(path, "x", compression=compression) as zipped:
        for name, raw in files.items():
            zipped.writestr(name, raw)
        zipped.writestr("package-manifest.json", manifest_raw)
        for name, raw in extra or []:
            zipped.writestr(name, raw)
    raw = path.read_bytes()
    return path, digest(raw), len(raw)


class XyzEvidenceVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_verify(self, archive: Path, sha: str, length: int, name="out"):
        return verify(archive, sha, length, self.root / name)

    def test_clean_package_preserves_every_original_byte(self):
        files = {"panel-01/panel-events.jsonl": b'{"kind":"closed"}\n',
                 "empty.stdout.txt": b""}
        archive, sha, length = archive_file(self.root, files)
        receipt = self.run_verify(archive, sha.lower(), length)
        output = self.root / "out"
        self.assertEqual(receipt["status"], "original-package-integrity-verified")
        for name, raw in files.items():
            self.assertEqual((output / "originals" / name).read_bytes(), raw)
        self.assertEqual(receipt["transportAuthenticated"], False)
        self.assertEqual(receipt["restartValidated"], False)
        self.assertEqual(json.loads((output / "verification.json").read_text()), receipt)
        self.assertFalse((output / "INCOMPLETE").exists())

    def test_archive_pin_mismatch_leaves_no_output(self):
        archive, sha, length = archive_file(self.root)
        for supplied_sha, supplied_length, reason in (
                ("D" * 64, length, "SHA-256"),
                (sha, length + 1, "byte length")):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(EvidenceError, reason):
                    self.run_verify(archive, supplied_sha, supplied_length, "failed")
                self.assertFalse((self.root / "failed").exists())

    def test_manifest_pin_mismatch_rejected(self):
        original = {"value.json": b"one"}
        manifest = package(original)
        archive, sha, length = archive_file(self.root, {"value.json": b"two"},
                                            manifest=manifest)
        with self.assertRaisesRegex(EvidenceError, "manifest pin mismatch"):
            self.run_verify(archive, sha, length)
        self.assertFalse((self.root / "out").exists())

    def test_extra_unreferenced_member_rejected(self):
        files = {"value.json": b"one"}
        archive, sha, length = archive_file(
            self.root, files, manifest=package(files), extra=[("extra.json", b"x")])
        with self.assertRaisesRegex(EvidenceError, "member sets differ"):
            self.run_verify(archive, sha, length)

    def test_missing_declared_member_rejected(self):
        manifest = package({"missing.json": b"expected"})
        archive, sha, length = archive_file(self.root, {}, manifest=manifest)
        with self.assertRaisesRegex(EvidenceError, "member missing"):
            self.run_verify(archive, sha, length)

    def test_wrong_package_contract_rejected(self):
        files = {"value.json": b"one"}
        manifest = package(files)
        manifest["purpose"] = "some-other-package"
        archive, sha, length = archive_file(self.root, files, manifest=manifest)
        with self.assertRaisesRegex(EvidenceError, "package purpose"):
            self.run_verify(archive, sha, length)

    def test_duplicate_manifest_json_key_rejected(self):
        files = {"value.json": b"one"}
        raw = json.dumps(package(files), separators=(",", ":"))
        raw = raw.replace('{"schemaVersion":1,', '{"schemaVersion":1,"schemaVersion":1,')
        archive, sha, length = archive_file(self.root, files, manifest=(raw + "\n").encode())
        with self.assertRaisesRegex(EvidenceError, "duplicate JSON key"):
            self.run_verify(archive, sha, length)

    def test_unsafe_and_nonportable_member_paths_rejected(self):
        names = ("../escape.json", "/absolute.json", "C:/drive.json", "a\\b.json",
                 "CON.txt", "con .txt", "folder/name:stream", "folder/trailing. ",
                 "folder/\u00e9.json", "folder/a<z.json", "folder/a>z.json",
                 'folder/a"z.json', "folder/a|z.json", "folder/a?z.json",
                 "folder/a*z.json")
        for index, name in enumerate(names):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                files = {name: b"x"}
                archive, sha, length = archive_file(root, files)
                with self.assertRaisesRegex(EvidenceError, "unsafe|portable|reserved"):
                    verify(archive, sha, length, root / "out")

    def test_case_collision_rejected(self):
        files = {"One.json": b"1", "one.JSON": b"2"}
        archive, sha, length = archive_file(self.root, files)
        with self.assertRaisesRegex(EvidenceError, "case-colliding"):
            self.run_verify(archive, sha, length)

    def test_file_parent_conflict_rejected(self):
        files = {"Panel-01": b"file", "panel-01/value.json": b"child"}
        archive, sha, length = archive_file(self.root, files)
        with self.assertRaisesRegex(EvidenceError, "file-parent"):
            self.run_verify(archive, sha, length)

    def test_directory_member_rejected(self):
        files = {"value.json": b"one"}
        archive, sha, length = archive_file(
            self.root, files, extra=[("unused/", b"")])
        with self.assertRaisesRegex(EvidenceError, "directory ZIP"):
            self.run_verify(archive, sha, length)

    def test_symlink_member_rejected(self):
        files = {"value.json": b"one"}
        link = ZipInfo("link.json")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive, sha, length = archive_file(
            self.root, files, extra=[(link, b"value.json")])
        with self.assertRaisesRegex(EvidenceError, "symbolic"):
            self.run_verify(archive, sha, length)

    def test_nonregular_and_dos_directory_attributes_rejected(self):
        files = {"value.json": b"one"}
        for label, attributes in (("fifo", 0o010644 << 16),
                                  ("dos-directory", 0x10)):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                special = ZipInfo("special.json")
                special.create_system = 3 if label == "fifo" else 0
                special.external_attr = attributes
                archive, sha, length = archive_file(
                    root, files, extra=[(special, b"value")])
                with self.assertRaisesRegex(EvidenceError, "nonregular"):
                    verify(archive, sha, length, root / "out")

    def test_unsupported_compression_rejected(self):
        files = {"value.json": b"one"}
        archive, sha, length = archive_file(self.root, files, compression=ZIP_BZIP2)
        with self.assertRaisesRegex(EvidenceError, "unsupported"):
            self.run_verify(archive, sha, length)

    def test_encrypted_member_flag_rejected_before_decode(self):
        archive, _sha, _length = archive_file(self.root)
        raw = bytearray(archive.read_bytes())
        for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            cursor = 0
            while True:
                cursor = raw.find(signature, cursor)
                if cursor < 0:
                    break
                flags = int.from_bytes(raw[cursor + flag_offset:cursor + flag_offset + 2], "little")
                raw[cursor + flag_offset:cursor + flag_offset + 2] = (flags | 1).to_bytes(2, "little")
                cursor += len(signature)
        archive.write_bytes(raw)
        with self.assertRaisesRegex(EvidenceError, "encrypted"):
            self.run_verify(archive, digest(raw), len(raw))

    def test_member_count_bound_rejected(self):
        archive, sha, length = archive_file(self.root)
        with patch("scripts.verify_xyz_evidence.MAX_MEMBERS", 2):
            with self.assertRaisesRegex(EvidenceError, "member count"):
                self.run_verify(archive, sha, length)

    def test_expansion_and_per_file_bounds_rejected(self):
        files = {"value.bin": b"1234567890"}
        archive, sha, length = archive_file(self.root, files)
        with patch("scripts.verify_xyz_evidence.MAX_EXPANDED_BYTES", 9):
            with self.assertRaisesRegex(EvidenceError, "expands beyond"):
                self.run_verify(archive, sha, length, "expanded")
        with patch("scripts.verify_xyz_evidence.MAX_FILE_BYTES", 9):
            with self.assertRaisesRegex(EvidenceError, "per-file bound"):
                self.run_verify(archive, sha, length, "file")

    def test_existing_output_is_preserved(self):
        archive, sha, length = archive_file(self.root)
        output = self.root / "out"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "must be new"):
            verify(archive, sha, length, output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_archive_and_output_parent_reparse_chains_rejected(self):
        archive, sha, length = archive_file(self.root)
        original = verifier._is_reparse_point
        for blocked, label in ((archive, "archive"),
                               (self.root, "output parent")):
            with self.subTest(label=label), patch(
                    "scripts.verify_xyz_evidence._is_reparse_point",
                    side_effect=lambda path, blocked=blocked: Path(path) == blocked
                    or original(Path(path))):
                with self.assertRaisesRegex(EvidenceError, label):
                    verify(archive, sha, length, self.root / "out")

    def test_output_appearing_after_validation_is_preserved_without_receipt(self):
        archive, sha, length = archive_file(self.root)
        output = self.root / "out"
        original = verifier._read_archive

        def race(*arguments):
            result = original(*arguments)
            output.mkdir()
            (output / "other-owner.txt").write_text("keep", encoding="utf-8")
            return result

        with patch("scripts.verify_xyz_evidence._read_archive", side_effect=race):
            with self.assertRaisesRegex(EvidenceError, "appeared during publication"):
                verify(archive, sha, length, output)
        self.assertEqual((output / "other-owner.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse((output / "verification.json").exists())

    def test_corrupt_receipt_readback_cannot_return_success(self):
        archive, sha, length = archive_file(self.root)
        output = self.root / "out"
        original = verifier._write_new

        def corrupt_receipt(path, raw):
            original(path, raw)
            if Path(path).name == "verification.json":
                Path(path).write_bytes(raw[:-1])

        with patch("scripts.verify_xyz_evidence._write_new", side_effect=corrupt_receipt):
            with self.assertRaisesRegex(EvidenceError, "verification receipt differs"):
                verify(archive, sha, length, output)
        self.assertTrue((output / "INCOMPLETE").is_file())
        self.assertTrue((output / "verification.json").is_file())

    def test_cli_success_and_no_overwrite_failure(self):
        archive, sha, length = archive_file(self.root)
        output = self.root / "out"
        arguments = ["--archive", str(archive), "--sha256", sha,
                     "--byte-length", str(length), "--output", str(output)]
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(arguments), 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"],
                         "original-package-integrity-verified")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 1)


if __name__ == "__main__":
    unittest.main()
