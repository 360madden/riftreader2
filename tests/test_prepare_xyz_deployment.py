"""Offline tests for the pinned XYZ deployment bundle preparer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "prepare_xyz_deployment.py"
SPEC = importlib.util.spec_from_file_location("prepare_xyz_deployment", SCRIPT)
preparer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparer)

BUILD_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def profile() -> dict:
    return {
        "schemaVersion": 1,
        "contractVersion": "native-position-profile/1",
        "fieldId": "player.position.xyz",
        "executableSha256": BUILD_SHA,
        "rootRva": "0x32E0200",
        "xyzOffsets": ["0x320", "0x324", "0x328"],
        "qualification": "candidate-only",
        "evidenceReference": "docs/validation/evidence.md",
    }


class PrepareXyzDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.marker = self.root / "binary-ran.txt"
        self.executable = self.root / "source-reader.exe"
        self.executable_data = (
            b"#!/usr/bin/env python\nfrom pathlib import Path\n"
            + f"Path({str(self.marker)!r}).write_text('ran')\n".encode()
        )
        self.executable.write_bytes(self.executable_data)
        if os.name != "nt":
            self.executable.chmod(0o755)
        self.profile = self.root / "source-profile.json"
        self.profile_data = (json.dumps(profile(), indent=2) + "\n").encode()
        self.profile.write_bytes(self.profile_data)
        self.manifest = self.root / "deployment.json"
        self.output = self.root / "prepared"
        self.write_manifest()

    def write_manifest(self, *, executable_sha=None, profile_sha=None, extra=None):
        value = {
            "executable": {
                "path": str(self.executable),
                "byteLength": len(self.executable_data),
                "sha256": executable_sha or sha(self.executable_data),
            },
            "profile": {
                "path": str(self.profile),
                "byteLength": len(self.profile_data),
                "sha256": profile_sha or sha(self.profile_data),
            },
            "hostFullGate": {"exitCode": 0},
            "guestDeployment": "not-performed",
            "guestRestartValidation": "pending",
            "patchRecovery": "deferred",
        }
        if extra:
            value.update(extra)
        self.manifest.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def test_prepares_exact_offline_bundle_without_executing_binary(self):
        result = preparer.prepare(self.manifest, self.output)
        self.assertFalse(self.marker.exists())
        self.assertEqual(result["contractVersion"], "xyz-deployment-bundle/1")
        self.assertEqual(result["gameExecutableSha256"], BUILD_SHA)
        self.assertFalse(result["guestInstalled"])
        self.assertFalse(result["guestExecuted"])
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"RiftReader2.Live.exe", "position-candidate-profile.json",
             "README.txt", "bundle-manifest.json"},
        )
        self.assertEqual((self.output / "RiftReader2.Live.exe").read_bytes(),
                         self.executable_data)
        saved = json.loads((self.output / "bundle-manifest.json").read_text())
        self.assertEqual(saved, result)
        self.assertEqual(saved["sourceManifestSha256"], sha(self.manifest.read_bytes()))
        for entry in saved["files"]:
            data = (self.output / entry["path"]).read_bytes()
            self.assertEqual((len(data), sha(data)),
                             (entry["byteLength"], entry["sha256"]))

    def test_content_tamper_is_rejected_before_output(self):
        self.executable.write_bytes(self.executable_data + b"tamper")
        with self.assertRaisesRegex(preparer.PreparationError, "byte length differs"):
            preparer.prepare(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_wrong_hash_is_rejected_before_output(self):
        self.write_manifest(executable_sha="A" * 64)
        with self.assertRaisesRegex(preparer.PreparationError, "SHA-256 differs"):
            preparer.prepare(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_malformed_profile_contract_is_rejected(self):
        value = profile()
        value["contractVersion"] = "native-position-profile/2"
        self.profile_data = (json.dumps(value) + "\n").encode()
        self.profile.write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(preparer.PreparationError, "unsupported position profile"):
            preparer.prepare(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_unknown_profile_field_is_rejected(self):
        value = profile()
        value["surprise"] = True
        self.profile_data = (json.dumps(value) + "\n").encode()
        self.profile.write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(preparer.PreparationError, "fields differ"):
            preparer.prepare(self.manifest, self.output)

    def test_profile_must_match_production_address_rules(self):
        value = profile()
        value["xyzOffsets"] = ["0x320", "0x322", "0x328"]
        self.profile_data = (json.dumps(value) + "\n").encode()
        self.profile.write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(preparer.PreparationError, "float32-aligned"):
            preparer.prepare(self.manifest, self.output)

    def test_boolean_schema_version_is_rejected(self):
        value = profile()
        value["schemaVersion"] = True
        self.profile_data = (json.dumps(value) + "\n").encode()
        self.profile.write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(preparer.PreparationError, "unsupported position profile"):
            preparer.prepare(self.manifest, self.output)

    def test_unknown_payload_entry_is_rejected(self):
        self.write_manifest(extra={"courier": {
            "path": str(self.executable), "byteLength": len(self.executable_data),
            "sha256": sha(self.executable_data)}})
        with self.assertRaisesRegex(preparer.PreparationError, "unsupported payload"):
            preparer.prepare(self.manifest, self.output)

    def test_existing_directory_is_not_modified(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(preparer.PreparationError, "already exists"):
            preparer.prepare(self.manifest, self.output)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_existing_file_collision_is_not_modified(self):
        self.output.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(preparer.PreparationError, "already exists"):
            preparer.prepare(self.manifest, self.output)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "keep")

    def test_output_appearing_during_preparation_is_not_overwritten(self):
        original_mkdir = Path.mkdir

        def race(path, *args, **kwargs):
            if path == self.output:
                original_mkdir(path)
                (path / "other-owner.txt").write_text("keep", encoding="utf-8")
                raise FileExistsError("simulated output race")
            return original_mkdir(path, *args, **kwargs)

        with mock.patch.object(Path, "mkdir", autospec=True, side_effect=race):
            with self.assertRaises(FileExistsError):
                preparer.prepare(self.manifest, self.output)
        self.assertEqual((self.output / "other-owner.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse((self.output / "bundle-manifest.json").exists())
        self.assertEqual(list(self.root.glob(".prepared.stage-*")), [])

    def test_failure_after_reservation_leaves_no_partial_bundle(self):
        original_replace = os.replace
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated copy publication failure")
            return original_replace(source, destination)

        with mock.patch.object(preparer.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated copy"):
                preparer.prepare(self.manifest, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".prepared.stage-*")), [])

    def test_corrupt_final_payload_is_rejected_before_manifest(self):
        original_replace = os.replace
        calls = 0

        def corrupt_first(source, destination):
            nonlocal calls
            calls += 1
            original_replace(source, destination)
            if calls == 1:
                Path(destination).write_bytes(b"corrupt")

        with mock.patch.object(preparer.os, "replace", side_effect=corrupt_first):
            with self.assertRaisesRegex(preparer.PreparationError, "final verification"):
                preparer.prepare(self.manifest, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".prepared.stage-*")), [])

    def test_corrupt_final_manifest_is_rejected_and_removed(self):
        original_write = preparer.write_new

        def corrupt_manifest(path, data):
            original_write(path, data)
            if path.name == "bundle-manifest.json":
                path.write_bytes(b"!" + data[1:])

        with mock.patch.object(preparer, "write_new", side_effect=corrupt_manifest):
            with self.assertRaisesRegex(preparer.PreparationError, "manifest failed"):
                preparer.prepare(self.manifest, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".prepared.stage-*")), [])

    def test_source_symlink_ancestor_is_rejected(self):
        linked = self.root / "linked-source"
        try:
            linked.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {error}")
        with self.assertRaisesRegex(preparer.PreparationError, "symlink or reparse ancestor"):
            preparer.prepare(linked / "deployment.json", self.output)

    def test_output_symlink_ancestor_is_rejected(self):
        target = self.root / "actual-output-parent"
        target.mkdir()
        linked = self.root / "linked-output-parent"
        try:
            linked.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {error}")
        with self.assertRaisesRegex(preparer.PreparationError, "symlink or reparse ancestor"):
            preparer.prepare(self.manifest, linked / "prepared")

    def test_cli_reports_prepared_then_refuses_overwrite(self):
        first = subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", str(self.manifest),
             "--output", str(self.output)], capture_output=True, text=True, check=False)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["status"], "prepared-offline-not-deployed")
        second = subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", str(self.manifest),
             "--output", str(self.output)], capture_output=True, text=True, check=False)
        self.assertEqual(second.returncode, 1)
        self.assertIn("already exists", second.stderr)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
