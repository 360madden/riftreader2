"""Build and preflight a configurable XYZ guest Courier entirely offline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "xyz-courier" / "ValidationCourier.cs"
CONFIG_NAME = "courier-config.txt"
READER_NAME = "RiftReader2.Live.exe"
PROFILE_NAME = "position-candidate-profile.json"
COURIER_NAME = "ValidationCourier.exe"
MAX_READER = 200 * 1024 * 1024
MAX_PROFILE = 8 * 1024
MAX_MANIFEST = 64 * 1024
SHA = re.compile(r"[0-9A-F]{64}\Z")
RUN_ID = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?\Z")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}
BUNDLE_KEYS = {"schemaVersion", "contractVersion", "preparedAtUtc",
               "sourceManifestSha256", "gameExecutableSha256", "fieldId",
               "qualification", "files", "guestInstalled", "guestExecuted",
               "liveValidated", "patchRecovery"}
FILE_KEYS = {"path", "byteLength", "sha256"}


class CourierPreparationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CourierPreparationError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(data, label):
    try:
        value = json.loads(data, object_pairs_hook=unique_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               CourierPreparationError(f"{label}: invalid number {value}")))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CourierPreparationError(f"{label}: invalid UTF-8 JSON") from error
    require(isinstance(value, dict), f"{label}: JSON object required")
    return value


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def is_reparse(path):
    info = path.lstat()
    return bool(getattr(info, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def require_plain_ancestors(path, label):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if os.path.lexists(item):
            require(not item.is_symlink() and not is_reparse(item),
                    f"{label} has a symlink or reparse ancestor")


def read_regular(path, maximum, label):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and not is_reparse(path),
            f"{label} must be a regular non-reparse file")
    size = path.stat().st_size
    require(0 < size <= maximum, f"{label} is outside its byte limit")
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    require(len(data) == size and len(data) <= maximum,
            f"{label} changed or exceeded its byte limit")
    return data


def write_new(path, data):
    with Path(path).open("xb") as destination:
        require(destination.write(data) == len(data), "incomplete Courier output write")
        destination.flush()
        os.fsync(destination.fileno())
    require(Path(path).read_bytes() == data, "Courier output write differs")


def validate_run_id(value):
    require(isinstance(value, str) and RUN_ID.fullmatch(value) and
            value.casefold() not in RESERVED, "invalid Courier run ID")
    return value


def compiler_path():
    candidates = [
        Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink() and not is_reparse(candidate):
            return candidate
    raise CourierPreparationError("installed .NET Framework compiler is unavailable")


def load_bundle(bundle):
    bundle = Path(bundle)
    require(bundle.is_absolute(), "prepared bundle path must be absolute")
    require_plain_ancestors(bundle, "prepared bundle")
    require(bundle.is_dir(), "prepared bundle directory is missing")
    manifest_data = read_regular(bundle / "bundle-manifest.json", MAX_MANIFEST,
                                 "prepared bundle manifest")
    manifest = parse_json(manifest_data, "prepared bundle manifest")
    require(set(manifest) == BUNDLE_KEYS and
            type(manifest["schemaVersion"]) is int and manifest["schemaVersion"] == 1 and
            manifest["contractVersion"] == "xyz-deployment-bundle/1",
            "unsupported prepared bundle contract")
    require(manifest["fieldId"] == "player.position.xyz" and
            manifest["qualification"] == "candidate-only" and
            manifest["guestInstalled"] is False and manifest["guestExecuted"] is False and
            manifest["liveValidated"] is False and manifest["patchRecovery"] == "deferred",
            "prepared bundle scope differs")
    game_sha = manifest["gameExecutableSha256"]
    require(isinstance(game_sha, str) and SHA.fullmatch(game_sha), "invalid game SHA-256")
    entries = manifest["files"]
    require(isinstance(entries, list), "prepared bundle files must be a list")
    declared = {}
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == FILE_KEYS,
                "invalid prepared bundle file entry")
        name = entry["path"]
        require(name in {READER_NAME, PROFILE_NAME, "README.txt"} and name not in declared,
                "unexpected or duplicate prepared bundle file")
        maximum = MAX_READER if name == READER_NAME else MAX_PROFILE if name == PROFILE_NAME else 64 * 1024
        require(type(entry["byteLength"]) is int and 0 < entry["byteLength"] <= maximum and
                isinstance(entry["sha256"], str) and SHA.fullmatch(entry["sha256"]),
                "invalid prepared bundle file pin or byte limit")
        data = read_regular(bundle / name, maximum, f"prepared {name}")
        require(len(data) == entry["byteLength"] and sha(data) == entry["sha256"],
                f"prepared {name} differs from its pin")
        declared[name] = (data, entry)
    require(set(declared) == {READER_NAME, PROFILE_NAME, "README.txt"},
            "prepared bundle file set differs")
    return manifest_data, manifest, declared


def prepare(bundle: Path, run_id: str, output: Path) -> dict:
    run_id = validate_run_id(run_id)
    output = Path(output)
    require(output.is_absolute() and output.name not in ("", ".", ".."),
            "output must be a new absolute directory")
    require_plain_ancestors(output, "output")
    require(output.parent.is_dir() and not os.path.lexists(output),
            "output must be new under an existing parent")
    output = output.parent.resolve(strict=True) / output.name
    bundle = Path(bundle).resolve(strict=True)
    require(not output.is_relative_to(bundle) and not bundle.is_relative_to(output),
            "Courier output and prepared bundle must be separate")
    manifest_data, bundle_manifest, declared = load_bundle(bundle)
    source_data = read_regular(SOURCE, 256 * 1024, "Courier source")
    compiler = compiler_path()
    compiler_data = read_regular(compiler, 8 * 1024 * 1024, "Framework compiler")
    reader_data, reader_pin = declared[READER_NAME]
    profile_data, profile_pin = declared[PROFILE_NAME]
    config = ("RR2XYZCOURIER1|{}|{}|{}|{}|{}|{}\n".format(
        run_id, reader_pin["sha256"], reader_pin["byteLength"],
        profile_pin["sha256"], profile_pin["byteLength"],
        bundle_manifest["gameExecutableSha256"])).encode("ascii")
    require(len(config) <= 512, "generated Courier configuration exceeds bound")

    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.courier-stage-", dir=output.parent))
    reserved = False
    complete = False
    published = {COURIER_NAME, CONFIG_NAME, READER_NAME, PROFILE_NAME,
                 "courier-manifest.json", "INCOMPLETE.txt"}
    try:
        staged_source = stage / "ValidationCourier.cs"
        write_new(staged_source, source_data)
        write_new(stage / READER_NAME, reader_data)
        write_new(stage / PROFILE_NAME, profile_data)
        write_new(stage / CONFIG_NAME, config)
        courier_path = stage / COURIER_NAME
        command = [str(compiler), "/nologo", "/target:winexe", "/optimize+",
                   f"/out:{courier_path}", "/reference:System.dll",
                   "/reference:System.Core.dll", "/reference:System.Drawing.dll",
                   "/reference:System.Windows.Forms.dll", "/reference:System.Web.Extensions.dll",
                   "/reference:System.IO.Compression.dll",
                   "/reference:System.IO.Compression.FileSystem.dll", str(staged_source)]
        compiled = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                  timeout=60, check=False, shell=False)
        require(compiled.returncode == 0 and courier_path.is_file(),
                "Courier compilation failed: " + (compiled.stderr or compiled.stdout)[-1000:])
        require(sha(read_regular(staged_source, len(source_data), "staged Courier source")) == sha(source_data) and
                sha(read_regular(compiler, len(compiler_data), "Framework compiler after build")) == sha(compiler_data),
                "Courier source or compiler changed during compilation")
        preflight = subprocess.run([str(courier_path), "--preflight"], cwd=stage,
                                   capture_output=True, text=True, timeout=30,
                                   check=False, shell=False)
        require(preflight.returncode == 0, "compiled Courier preflight failed: " + preflight.stderr[-1000:])
        outcome = parse_json(preflight.stdout.encode("utf-8"), "Courier preflight output")
        require(outcome == {"status": "preflight-passed-no-install-performed", "runId": run_id,
                            "gameSha256": bundle_manifest["gameExecutableSha256"],
                            "installationPerformed": False, "readerExecuted": False,
                            "networkUsed": False}, "Courier preflight claims differ")
        courier_data = read_regular(courier_path, 8 * 1024 * 1024, "compiled Courier")
        result = {
            "schemaVersion": 1,
            "contractVersion": "xyz-courier-bundle/1",
            "preparedAtUtc": datetime.now(timezone.utc).isoformat(),
            "runId": run_id,
            "guestInstallRoot": rf"C:\RIFT_TRANSFER\XYZ\{run_id}",
            "sourceBundleManifestSha256": sha(manifest_data),
            "courierSourceSha256": sha(source_data),
            "compilerSha256": sha(compiler_data),
            "claimEndpoint": "http://192.168.56.1:8765/rr2-native-pointer-zip-claim-oct24-01",
            "uploadEndpoint": "http://192.168.56.1:8765/rr2-native-pointer-oct24-01-report.zip",
            "files": [
                {"path": READER_NAME, "byteLength": len(reader_data), "sha256": sha(reader_data)},
                {"path": PROFILE_NAME, "byteLength": len(profile_data), "sha256": sha(profile_data)},
                {"path": CONFIG_NAME, "byteLength": len(config), "sha256": sha(config)},
                {"path": COURIER_NAME, "byteLength": len(courier_data), "sha256": sha(courier_data)},
            ],
            "preflight": outcome,
            "guestInstalled": False,
            "networkUsed": False,
            "liveValidated": False,
            "patchRecovery": "deferred",
            "pinsEstablishIntegrityNotAuthenticity": True,
            "trustedExternalFinalBundlePinRequired": True,
        }
        manifest_output = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode("utf-8")
        output.mkdir()
        reserved = True
        write_new(output / "INCOMPLETE.txt",
                  b"Courier bundle preparation did not complete. Use a new output directory.\n")
        for name in (READER_NAME, PROFILE_NAME, CONFIG_NAME, COURIER_NAME):
            write_new(output / name, (stage / name).read_bytes())
        for entry in result["files"]:
            data = read_regular(output / entry["path"], entry["byteLength"],
                                f"published {entry['path']}")
            require(len(data) == entry["byteLength"] and sha(data) == entry["sha256"],
                    f"published {entry['path']} differs")
        write_new(output / "courier-manifest.json", manifest_output)
        require((output / "courier-manifest.json").read_bytes() == manifest_output,
                "published Courier manifest differs")
        (output / "INCOMPLETE.txt").unlink()
        complete = True
        return result
    finally:
        for name in ("ValidationCourier.cs", READER_NAME, PROFILE_NAME, CONFIG_NAME, COURIER_NAME):
            candidate = stage / name
            if candidate.is_file() and not candidate.is_symlink():
                candidate.unlink()
        if stage.exists():
            stage.rmdir()
        if reserved and not complete:
            # Leave the bounded output and marker for diagnosis. It cannot be
            # mistaken for an accepted bundle because the marker takes precedence.
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.bundle, args.run_id, args.output)
        print(json.dumps({"status": "courier-prepared-preflight-passed-not-deployed",
                          "output": str(args.output), "runId": result["runId"],
                          "courierSha256": next(item["sha256"] for item in result["files"]
                                                if item["path"] == COURIER_NAME)}))
        return 0
    except (CourierPreparationError, OSError, subprocess.SubprocessError,
            TypeError, KeyError, OverflowError) as error:
        print(f"XYZ Courier preparation rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
