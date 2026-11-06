"""Verify and recover a pinned XYZ panel evidence ZIP entirely offline.

The caller supplies the expected archive hash and byte length.  This command
checks ZIP safety and the embedded package manifest, then publishes original
member bytes plus a derived integrity receipt in a new directory.  It does not
authenticate transport or establish restart, UI, Lua, movement, or field claims.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from tempfile import TemporaryDirectory
import zlib
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_MEMBERS = 2048
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
SHA256 = re.compile(r"[0-9A-Fa-f]{64}\Z")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}
MANIFEST_KEYS = {"schemaVersion", "purpose", "createdAtUtc", "qualification",
                 "transport", "readerSha256", "profileSha256", "gameSha256",
                 "oldTarget", "afterTarget", "panelExitCode", "files"}
TARGET_KEYS = {"processId", "processStartUtcTicks", "executablePath",
               "executableSha256"}
FILE_KEYS = {"path", "byteLength", "sha256"}
PORTABLE_PART = re.compile(r"[A-Za-z0-9._ -]+\Z")


class EvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               EvidenceError(f"{label}: invalid number {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"{label}: invalid JSON") from error
    _require(isinstance(value, dict), f"{label}: JSON object required")
    return value


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        written = destination.write(raw)
        _require(written == len(raw), f"short write: {path.name}")
        destination.flush()
        os.fsync(destination.fileno())


def _read_published(path: Path, maximum: int) -> bytes:
    with path.open("rb") as source:
        return source.read(maximum + 1)


def _portable_name(name: str) -> tuple[str, ...]:
    _require(isinstance(name, str) and name and "\\" not in name,
             "unsafe ZIP member path")
    _require(not name.startswith("/") and not re.match(r"^[A-Za-z]:", name),
             "unsafe ZIP member path")
    path = PurePosixPath(name)
    parts = path.parts
    _require(parts and path.as_posix() == name and all(part not in ("", ".", "..")
             for part in parts), "unsafe ZIP member path")
    for part in parts:
        _require(PORTABLE_PART.fullmatch(part) is not None
                 and not part.endswith((" ", ".")),
                 "ZIP member name is not Windows-portable")
        _require(part.split(".", 1)[0].rstrip(" ").casefold() not in RESERVED,
                 "ZIP member uses a reserved Windows name")
    return parts


def _is_reparse_point(path: Path) -> bool:
    try:
        details = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


def _reject_reparse_chain(path: Path, label: str) -> None:
    absolute = path.absolute()
    chain = [absolute, *absolute.parents]
    for item in reversed(chain):
        _require(not _is_reparse_point(item), f"{label} path contains a link or reparse point")


def _utc(value: object, label: str) -> str:
    _require(isinstance(value, str), f"{label}: UTC timestamp required")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise EvidenceError(f"{label}: invalid UTC timestamp") from error
    _require(stamp.utcoffset() == timedelta(0), f"{label}: timestamp must use UTC")
    return value


def _digest(value: object, label: str) -> str:
    _require(isinstance(value, str) and SHA256.fullmatch(value),
             f"{label}: SHA-256 required")
    return value.upper()


def _target(value: object, game_sha: str, label: str) -> dict:
    _require(isinstance(value, dict) and set(value) == TARGET_KEYS,
             f"{label}: invalid target fields")
    _require(type(value["processId"]) is int and value["processId"] > 0
             and type(value["processStartUtcTicks"]) is int
             and value["processStartUtcTicks"] > 0
             and isinstance(value["executablePath"], str)
             and value["executablePath"], f"{label}: invalid target identity")
    _require(_digest(value["executableSha256"], label) == game_sha,
             f"{label}: target build differs from package build")
    return value


def _manifest(raw: bytes, members: dict[str, bytes]) -> tuple[dict, list[dict]]:
    _require(0 < len(raw) <= MAX_MANIFEST_BYTES, "package manifest outside bound")
    value = _json(raw, "package manifest")
    _require(set(value) == MANIFEST_KEYS, "package manifest fields differ")
    _require(value["schemaVersion"] == 1, "unsupported package manifest schema")
    _require(value["purpose"] == "xyz-interface-full-game-restart-gui-evidence",
             "unexpected package purpose")
    _utc(value["createdAtUtc"], "package manifest")
    _require(value["qualification"] ==
             "same-build validation only; patch recovery deferred",
             "unexpected package qualification")
    _require(value["transport"] ==
             "pointer-named strict routes reused only as bounded ZIP transport",
             "unexpected package transport declaration")
    reader_sha = _digest(value["readerSha256"], "reader")
    profile_sha = _digest(value["profileSha256"], "profile")
    game_sha = _digest(value["gameSha256"], "game")
    _target(value["oldTarget"], game_sha, "old target")
    _target(value["afterTarget"], game_sha, "after target")
    _require(type(value["panelExitCode"]) is int, "invalid panel exit code")
    files = value["files"]
    _require(isinstance(files, list) and 0 < len(files) < MAX_MEMBERS,
             "invalid manifest file list")
    declared: dict[str, dict] = {}
    folded: set[str] = set()
    for entry in files:
        _require(isinstance(entry, dict) and set(entry) == FILE_KEYS,
                 "invalid manifest file entry")
        path = entry["path"]
        _portable_name(path)
        fold = path.casefold()
        _require(path != "package-manifest.json" and fold not in folded,
                 "duplicate or self-declared manifest path")
        folded.add(fold)
        _require(type(entry["byteLength"]) is int and
                 0 <= entry["byteLength"] <= MAX_FILE_BYTES,
                 "invalid manifest file length")
        digest = _digest(entry["sha256"], path)
        _require(path in members, f"manifest member missing: {path}")
        body = members[path]
        _require(len(body) == entry["byteLength"] and _sha(body) == digest,
                 f"manifest pin mismatch: {path}")
        declared[path] = {"path": path, "byteLength": len(body), "sha256": digest}
    _require(set(members) == set(declared) | {"package-manifest.json"},
             "archive and manifest member sets differ")
    return value, [declared[name] for name in sorted(declared)]


def _read_archive(archive: Path, expected_sha: str,
                  expected_bytes: int) -> tuple[bytes, dict[str, bytes]]:
    _require(isinstance(expected_sha, str) and SHA256.fullmatch(expected_sha),
             "expected SHA-256 is invalid")
    _require(type(expected_bytes) is int and 0 < expected_bytes <= MAX_ARCHIVE_BYTES,
             "expected byte length is invalid")
    _reject_reparse_chain(archive, "archive")
    _require(archive.is_file() and not archive.is_symlink(),
             "archive must be an existing non-symlink file")
    with archive.open("rb") as source:
        raw = source.read(MAX_ARCHIVE_BYTES + 1)
    _require(len(raw) <= MAX_ARCHIVE_BYTES, "archive exceeds 16 MiB")
    _require(len(raw) == expected_bytes, "archive byte length differs from expected")
    _require(_sha(raw) == expected_sha.upper(), "archive SHA-256 differs from expected")
    members: dict[str, bytes] = {}
    folded: set[str] = set()
    files: set[tuple[str, ...]] = set()
    try:
        with ZipFile(BytesIO(raw)) as zipped:
            infos = zipped.infolist()
            _require(0 < len(infos) <= MAX_MEMBERS, "invalid ZIP member count")
            total = 0
            for info in infos:
                _require(not info.is_dir(), "directory ZIP members are not accepted")
                _require(info.orig_filename == info.filename,
                         "ZIP member name contains an ambiguous terminator")
                parts = _portable_name(info.filename)
                folded_parts = tuple(part.casefold() for part in parts)
                fold = info.filename.casefold()
                _require(info.filename not in members and fold not in folded,
                         "duplicate or case-colliding ZIP member")
                _require(not any(folded_parts[:index] in files
                                 for index in range(1, len(folded_parts))),
                         "ZIP file-parent path conflict")
                _require(not any(existing[:len(folded_parts)] == folded_parts
                                 for existing in files),
                         "ZIP file-parent path conflict")
                _require(not info.flag_bits & 0x1 and
                         info.compress_type in (ZIP_STORED, ZIP_DEFLATED),
                         "unsupported or encrypted ZIP member")
                mode = (info.external_attr >> 16) & 0xFFFF
                _require(not stat.S_ISLNK(mode), "symbolic ZIP member refused")
                _require(stat.S_IFMT(mode) in (0, stat.S_IFREG)
                         and not info.external_attr & 0x10,
                         "nonregular ZIP member refused")
                _require(0 <= info.file_size <= MAX_FILE_BYTES,
                         "ZIP member exceeds per-file bound")
                total += info.file_size
                _require(total <= MAX_EXPANDED_BYTES, "ZIP expands beyond 16 MiB")
                with zipped.open(info) as source:
                    body = source.read(info.file_size + 1)
                _require(len(body) == info.file_size,
                         "ZIP member decoded length differs")
                members[info.filename] = body
                folded.add(fold)
                files.add(folded_parts)
    except (BadZipFile, EOFError, RuntimeError, zlib.error) as error:
        raise EvidenceError("archive is corrupt") from error
    return raw, members


def verify(archive: Path, expected_sha: str, expected_bytes: int,
           output: Path) -> dict:
    """Verify *archive*, publish originals, then write the completion receipt."""
    archive = Path(archive)
    output = Path(output)
    _reject_reparse_chain(output.parent, "output parent")
    _require(not _is_reparse_point(output), "output directory must not be a link")
    _require(output.name not in ("", ".", "..") and output.parent.is_dir()
             and not output.exists() and not output.is_symlink(),
             "output directory must be new with an existing parent")
    raw, members = _read_archive(archive, expected_sha, expected_bytes)
    _require("package-manifest.json" in members, "package manifest missing")
    package, declared = _manifest(members["package-manifest.json"], members)
    receipt = {
        "schemaVersion": 1,
        "evidenceKind": "xyz-panel-package-integrity/1",
        "status": "original-package-integrity-verified",
        "archive": {"byteLength": len(raw), "sha256": _sha(raw)},
        "packageManifest": {
            "byteLength": len(members["package-manifest.json"]),
            "sha256": _sha(members["package-manifest.json"]),
        },
        "package": {
            "createdAtUtc": package["createdAtUtc"],
            "readerSha256": package["readerSha256"].upper(),
            "profileSha256": package["profileSha256"].upper(),
            "gameSha256": package["gameSha256"].upper(),
            "panelExitCode": package["panelExitCode"],
            "oldTarget": package["oldTarget"],
            "afterTarget": package["afterTarget"],
        },
        "files": declared + [{
            "path": "package-manifest.json",
            "byteLength": len(members["package-manifest.json"]),
            "sha256": _sha(members["package-manifest.json"]),
        }],
        "scope": "offline-caller-pinned-package-integrity-only",
        "transportAuthenticated": False,
        "restartValidated": False,
        "panelBehaviorValidated": False,
        "fieldQualified": False,
    }
    with TemporaryDirectory(prefix=".rr2-xyz-evidence-", dir=output.parent) as temporary:
        stage = Path(temporary)
        originals = stage / "originals"
        originals.mkdir()
        for name, body in sorted(members.items()):
            target = originals.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            _write_new(target, body)
        _reject_reparse_chain(output.parent, "output parent")
        try:
            output.mkdir()
        except FileExistsError as error:
            raise EvidenceError("output directory appeared during publication") from error
        marker = output / "INCOMPLETE"
        marker_raw = (b"XYZ evidence recovery is incomplete. Only an absent marker plus a "
                      b"verified verification.json indicates completion.\n")
        _write_new(marker, marker_raw)
        _require(_read_published(marker, len(marker_raw)) == marker_raw,
                 "incomplete marker readback differs")
        originals.replace(output / "originals")
        for entry in receipt["files"]:
            recovered = output / "originals" / Path(*PurePosixPath(entry["path"]).parts)
            _require(recovered.is_file() and not recovered.is_symlink()
                     and recovered.stat().st_size == entry["byteLength"]
                     and _sha(_read_published(recovered, entry["byteLength"]))
                     == entry["sha256"],
                     f"published original differs: {entry['path']}")
        receipt_raw = (json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode()
        receipt_path = output / "verification.json"
        _write_new(receipt_path, receipt_raw)
        _require(_read_published(receipt_path, len(receipt_raw)) == receipt_raw,
                 "published verification receipt differs")
        marker.unlink()
        _require(not marker.exists() and not marker.is_symlink(),
                 "incomplete marker could not be cleared")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--byte-length", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = verify(args.archive, args.sha256, args.byte_length, args.output)
    except (EvidenceError, OSError, OverflowError, TypeError) as error:
        print(f"XYZ evidence verification rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": receipt["status"], "output": str(args.output),
                      "archiveSha256": receipt["archive"]["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
