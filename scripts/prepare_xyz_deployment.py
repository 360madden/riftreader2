"""Prepare a pinned, offline XYZ reader payload without running or deploying it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


MAX_MANIFEST_BYTES = 64 * 1024
MAX_EXECUTABLE_BYTES = 200 * 1024 * 1024
MAX_PROFILE_BYTES = 64 * 1024
SHA256_PATTERN = re.compile(r"[0-9A-F]{64}")
HEX_PATTERN = re.compile(r"0x(?:0|[1-9A-F][0-9A-F]*)")
PROFILE_KEYS = {
    "schemaVersion", "contractVersion", "fieldId", "executableSha256",
    "rootRva", "xyzOffsets", "qualification", "evidenceReference",
}
KNOWN_MANIFEST_KEYS = {
    "executable", "profile", "hostFullGate", "guestDeployment",
    "guestRestartValidation", "patchRecovery",
}


class PreparationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreparationError(message)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(data: bytes, description: str) -> dict:
    def reject(value: str):
        raise PreparationError(f"{description} contains non-JSON number: {value}")
    try:
        value = json.loads(data, object_pairs_hook=unique_object, parse_constant=reject)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PreparationError(f"{description} is not valid UTF-8 JSON") from error
    require(isinstance(value, dict), f"{description} must be a JSON object")
    return value


def is_reparse(path: Path) -> bool:
    info = path.lstat()
    attribute = getattr(info, "st_file_attributes", 0)
    return bool(attribute & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def require_plain_ancestors(path: Path, description: str) -> None:
    current = path.parent
    while current != current.parent:
        if current.exists():
            require(current.is_dir() and not current.is_symlink() and not is_reparse(current),
                    f"{description} has a symlink or reparse ancestor")
        current = current.parent


def read_regular(path: Path, maximum: int, description: str) -> bytes:
    require(path.is_absolute(), f"{description} path must be absolute")
    require_plain_ancestors(path, description)
    require(path.is_file() and not path.is_symlink() and not is_reparse(path),
            f"{description} must be a regular non-reparse file")
    size = path.stat().st_size
    require(0 < size <= maximum, f"{description} is outside its byte limit")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    require(len(data) == size and len(data) <= maximum,
            f"{description} changed or exceeded its byte limit while reading")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def validate_pin(manifest: dict, name: str, maximum: int) -> tuple[Path, bytes, str]:
    entry = manifest.get(name)
    require(isinstance(entry, dict) and set(entry) == {"path", "byteLength", "sha256"},
            f"{name} entry must contain only path, byteLength and sha256")
    require(isinstance(entry["path"], str) and entry["path"], f"invalid {name} path")
    require(type(entry["byteLength"]) is int and 0 < entry["byteLength"] <= maximum,
            f"invalid {name} byteLength")
    require(isinstance(entry["sha256"], str) and SHA256_PATTERN.fullmatch(entry["sha256"]),
            f"invalid {name} sha256")
    path = Path(entry["path"])
    data = read_regular(path, maximum, name)
    require(len(data) == entry["byteLength"], f"{name} byte length differs from pin")
    require(digest(data) == entry["sha256"], f"{name} SHA-256 differs from pin")
    return path, data, entry["sha256"]


def validate_profile(data: bytes) -> dict:
    require(len(data) <= 8192, "position profile exceeds the production 8192-byte limit")
    profile = parse_json(data, "position profile")
    require(set(profile) == PROFILE_KEYS, "position profile fields differ from contract v1")
    require(type(profile["schemaVersion"]) is int and profile["schemaVersion"] == 1 and
            profile["contractVersion"] == "native-position-profile/1",
            "unsupported position profile contract")
    require(profile["fieldId"] == "player.position.xyz", "unexpected position field")
    require(profile["qualification"] == "candidate-only", "unexpected position qualification")
    require(isinstance(profile["executableSha256"], str) and
            SHA256_PATTERN.fullmatch(profile["executableSha256"]), "invalid game executable SHA-256")
    require(isinstance(profile["rootRva"], str) and HEX_PATTERN.fullmatch(profile["rootRva"]),
            "invalid root RVA")
    require(isinstance(profile["xyzOffsets"], list) and len(profile["xyzOffsets"]) == 3 and
            all(isinstance(value, str) and HEX_PATTERN.fullmatch(value)
                for value in profile["xyzOffsets"]), "invalid XYZ offsets")
    offsets = [int(value, 16) for value in profile["xyzOffsets"]]
    require(offsets == sorted(set(offsets)), "XYZ offsets must be distinct and increasing")
    require(isinstance(profile["evidenceReference"], str) and profile["evidenceReference"],
            "missing profile evidence reference")
    require(profile["evidenceReference"].strip() == profile["evidenceReference"] and
            len(profile["evidenceReference"]) <= 256, "invalid profile evidence reference")
    root_rva = int(profile["rootRva"], 16)
    require(root_rva <= (1 << 64) - 1, "root RVA exceeds uint64")
    require(all(value <= (1 << 32) - 1 for value in offsets), "XYZ offset exceeds uint32")
    require(offsets[2] <= 4092 and all(value % 4 == 0 for value in offsets),
            "XYZ offsets must be float32-aligned within one 4096-byte terminal read")
    return profile


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        written = stream.write(data)
        require(written == len(data), f"short write while creating {path.name}")
        stream.flush()
        os.fsync(stream.fileno())


def remove_owned_stage(stage: Path, parent: Path, prefix: str) -> None:
    """Remove only the private stage created by this invocation."""
    if not stage.exists():
        return
    require(stage.name.startswith(prefix), "refusing unexpected staging directory name")
    require(not stage.is_symlink() and not is_reparse(stage), "refusing linked staging directory")
    require(stage.resolve(strict=True).parent == parent.resolve(strict=True),
            "refusing staging directory outside intended parent")
    shutil.rmtree(stage)


def clear_incomplete_output(output: Path, parent: Path, names: set[str]) -> None:
    """Clear only this invocation's exclusive, incomplete output reservation."""
    if not output.exists() or output.is_symlink() or is_reparse(output):
        return
    if output.resolve(strict=True).parent != parent.resolve(strict=True):
        return
    for name in names:
        candidate = output / name
        if candidate.is_file() and not candidate.is_symlink() and not is_reparse(candidate):
            candidate.unlink()
    try:
        output.rmdir()
    except OSError:
        # An unexpected file makes this visibly incomplete; bundle-manifest.json
        # was removed above, so it cannot be mistaken for an accepted bundle.
        pass


def prepare(manifest: Path, output: Path) -> dict:
    manifest = Path(manifest)
    output = Path(output)
    require(manifest.is_absolute(), "manifest path must be absolute")
    manifest_data = read_regular(manifest, MAX_MANIFEST_BYTES, "deployment manifest")
    source = parse_json(manifest_data, "deployment manifest")
    require(set(source).issubset(KNOWN_MANIFEST_KEYS) and
            {"executable", "profile"}.issubset(source),
            "deployment manifest contains unsupported payload entries")
    _executable_path, executable_data, executable_sha = validate_pin(
        source, "executable", MAX_EXECUTABLE_BYTES)
    _profile_path, profile_data, profile_sha = validate_pin(
        source, "profile", MAX_PROFILE_BYTES)
    profile = validate_profile(profile_data)

    require(output.is_absolute(), "output path must be absolute")
    require(output.name not in ("", ".", ".."), "output must name a new directory")
    require_plain_ancestors(output, "output")
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not is_reparse(output.parent), "output parent must be a regular directory")
    require(not os.path.lexists(output), "output already exists")

    source_manifest_sha = digest(manifest_data)
    instructions = (
        "RiftReader2 XYZ deployment payload\n\n"
        "This folder was prepared offline from SHA-256 and byte-length pinned inputs.\n"
        "It has not been deployed, run, or validated inside a guest.\n"
        "Use the reviewed guest-transfer and sole-controller workflow. Verify bundle-manifest.json\n"
        "and both file hashes before launch. Exact game-build checks remain mandatory.\n"
        "Patch recovery and direct ChatGPT Computer Use inside RIFT remain deferred.\n"
    ).encode("utf-8")
    file_values = [
        ("RiftReader2.Live.exe", executable_data, executable_sha),
        ("position-candidate-profile.json", profile_data, profile_sha),
        ("README.txt", instructions, digest(instructions)),
    ]
    result = {
        "schemaVersion": 1,
        "contractVersion": "xyz-deployment-bundle/1",
        "preparedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceManifestSha256": source_manifest_sha,
        "gameExecutableSha256": profile["executableSha256"],
        "fieldId": profile["fieldId"],
        "qualification": profile["qualification"],
        "files": [
            {"path": name, "byteLength": len(data), "sha256": expected}
            for name, data, expected in file_values
        ],
        "guestInstalled": False,
        "guestExecuted": False,
        "liveValidated": False,
        "patchRecovery": "deferred",
    }
    manifest_output = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode("utf-8")

    stage_prefix = f".{output.name}.stage-"
    stage = Path(tempfile.mkdtemp(prefix=stage_prefix, dir=output.parent))
    reserved = False
    completed = False
    output_names = {name for name, _data, _expected in file_values} | {"bundle-manifest.json"}
    try:
        for name, data, expected in file_values:
            destination = stage / name
            write_new(destination, data)
            require(digest(destination.read_bytes()) == expected,
                    f"staged {name} failed verification")
        output.mkdir()
        reserved = True
        for name, _data, _expected in file_values:
            os.replace(stage / name, output / name)
        for name, data, expected in file_values:
            final_data = read_regular(output / name, len(data), f"published {name}")
            require(len(final_data) == len(data) and digest(final_data) == expected,
                    f"published {name} failed final verification")
        stage.rmdir()
        write_new(output / "bundle-manifest.json", manifest_output)
        final_manifest = read_regular(
            output / "bundle-manifest.json", len(manifest_output), "published bundle manifest")
        require(final_manifest == manifest_output,
                "published bundle manifest failed final verification")
        completed = True
    finally:
        if not completed and reserved:
            clear_incomplete_output(output, output.parent, output_names)
        if stage.exists():
            remove_owned_stage(stage, output.parent, stage_prefix)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.manifest, args.output)
        print(json.dumps({
            "status": "prepared-offline-not-deployed",
            "output": str(args.output),
            "sourceManifestSha256": result["sourceManifestSha256"],
            "gameExecutableSha256": result["gameExecutableSha256"],
        }, separators=(",", ":")))
        return 0
    except (PreparationError, OSError, TypeError, KeyError, OverflowError) as error:
        print(f"XYZ deployment preparation rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
