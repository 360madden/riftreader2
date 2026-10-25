"""Offline tests for configurable Courier compilation and its own preflight."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import prepare_xyz_courier as courier

GAME_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def profile(game_sha=GAME_SHA):
    return {
        "schemaVersion": 1,
        "contractVersion": "native-position-profile/1",
        "fieldId": "player.position.xyz",
        "executableSha256": game_sha,
        "rootRva": "0x32E0200",
        "xyzOffsets": ["0x320", "0x324", "0x328"],
        "qualification": "candidate-only",
        "evidenceReference": "docs/validation/synthetic.md",
    }


class PrepareXyzCourierTests(unittest.TestCase):
    def setUp(self):
        if os.name != "nt":
            self.skipTest("Courier compilation is Windows-only")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bundle = self.root / "prepared"
        self.bundle.mkdir()
        self.marker = self.root / "reader-executed.txt"
        self.reader_data = (b"synthetic executable bytes; if run this is not a valid PE; marker=" +
                            str(self.marker).encode())
        self.profile_data = (json.dumps(profile(), indent=2) + "\n").encode()
        self.readme_data = b"synthetic prepared payload\n"
        (self.bundle / courier.READER_NAME).write_bytes(self.reader_data)
        (self.bundle / courier.PROFILE_NAME).write_bytes(self.profile_data)
        (self.bundle / "README.txt").write_bytes(self.readme_data)
        self.output = self.root / "courier"
        self.write_manifest()

    def write_manifest(self):
        value = {
            "schemaVersion": 1,
            "contractVersion": "xyz-deployment-bundle/1",
            "preparedAtUtc": "2026-10-25T15:00:00+00:00",
            "sourceManifestSha256": "A" * 64,
            "gameExecutableSha256": GAME_SHA,
            "fieldId": "player.position.xyz",
            "qualification": "candidate-only",
            "files": [
                {"path": courier.READER_NAME, "byteLength": len(self.reader_data),
                 "sha256": sha(self.reader_data)},
                {"path": courier.PROFILE_NAME, "byteLength": len(self.profile_data),
                 "sha256": sha(self.profile_data)},
                {"path": "README.txt", "byteLength": len(self.readme_data),
                 "sha256": sha(self.readme_data)},
            ],
            "guestInstalled": False,
            "guestExecuted": False,
            "liveValidated": False,
            "patchRecovery": "deferred",
        }
        (self.bundle / "bundle-manifest.json").write_text(
            json.dumps(value) + "\n", encoding="utf-8")

    def prepare(self, run_id="test-courier-01"):
        return courier.prepare(self.bundle, run_id, self.output)

    def run_preflight(self):
        return subprocess.run([str(self.output / courier.COURIER_NAME), "--preflight"],
                              cwd=self.output, capture_output=True, text=True,
                              timeout=30, check=False)

    def compile_harness(self):
        source = self.root / "CourierHarness.cs"
        source.write_text(r'''
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Reflection;
using System.Text;

internal static class CourierHarness
{
    private static string Hash(byte[] value)
    {
        using (SHA256 algorithm = SHA256.Create())
        {
            StringBuilder text = new StringBuilder();
            foreach (byte item in algorithm.ComputeHash(value))
                text.Append(item.ToString("X2", CultureInfo.InvariantCulture));
            return text.ToString();
        }
    }

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "process")
        {
            using (Process current = Process.GetCurrentProcess())
            {
                long ticks = current.StartTime.ToUniversalTime().Ticks;
                return ValidationCourierForm.ProcessMatchesStart(current, ticks) &&
                    !ValidationCourierForm.ProcessMatchesStart(current, ticks + 1) ? 0 : 10;
            }
        }
        if (args.Length == 2 && args[0] == "archive-mutation")
        {
            string source = Path.Combine(args[1], "source.json");
            string archive = Path.Combine(args[1], "evidence.zip");
            byte[] before = Encoding.UTF8.GetBytes("before");
            File.WriteAllBytes(source, before);
            List<FileRecord> files = new List<FileRecord> {
                new FileRecord(source, "source.json", before.Length, Hash(before))
            };
            File.WriteAllText(source, "changed");
            try
            {
                ValidationCourierForm.CreateVerifiedArchive(archive, files, 1024 * 1024);
                return 20;
            }
            catch (InvalidOperationException)
            {
                return File.Exists(archive) ? 21 : 0;
            }
        }
        if (args.Length == 2 && args[0] == "manifest-mismatch")
        {
            string source = Path.Combine(args[1], "current.json");
            string manifest = Path.Combine(args[1], "package-manifest.json");
            byte[] current = Encoding.UTF8.GetBytes("current");
            File.WriteAllBytes(source, current);
            File.WriteAllText(manifest,
                "{\"files\":[{\"path\":\"current.json\",\"byteLength\":3,\"sha256\":\"" +
                new string('A', 64) + "\"}]}");
            List<FileRecord> files = new List<FileRecord> {
                new FileRecord(source, "current.json", current.Length, Hash(current)),
                new FileRecord(manifest, "package-manifest.json", new FileInfo(manifest).Length,
                    Hash(File.ReadAllBytes(manifest)))
            };
            MethodInfo method = typeof(ValidationCourierForm).GetMethod(
                "VerifyPackageManifestPins", BindingFlags.NonPublic | BindingFlags.Static);
            try
            {
                method.Invoke(null, new object[] { manifest, files });
                return 40;
            }
            catch (TargetInvocationException error)
            {
                return error.InnerException is InvalidOperationException ? 0 : 41;
            }
        }
        return 30;
    }
}
''', encoding="utf-8")
        executable = self.root / "CourierHarness.exe"
        compiler = courier.compiler_path()
        command = [str(compiler), "/nologo", "/target:exe", "/main:CourierHarness",
                   f"/out:{executable}", "/reference:System.dll", "/reference:System.Core.dll",
                   "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                   "/reference:System.Web.Extensions.dll", "/reference:System.IO.Compression.dll",
                   "/reference:System.IO.Compression.FileSystem.dll", str(courier.SOURCE), str(source)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return executable

    def test_compiles_and_preflights_without_executing_reader(self):
        result = self.prepare()
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.output / "INCOMPLETE.txt").exists())
        self.assertEqual({item.name for item in self.output.iterdir()},
                         {courier.READER_NAME, courier.PROFILE_NAME,
                          courier.CONFIG_NAME, courier.COURIER_NAME,
                          "courier-manifest.json"})
        self.assertEqual(result["preflight"]["readerExecuted"], False)
        self.assertEqual(result["guestInstallRoot"],
                         r"C:\RIFT_TRANSFER\XYZ\test-courier-01")
        again = self.run_preflight()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(again.stdout)["status"],
                         "preflight-passed-no-install-performed")
        self.assertFalse(json.loads(again.stdout)["installationPerformed"])
        self.assertFalse(self.marker.exists())

    def test_config_wire_and_pins_match_manifest(self):
        result = self.prepare("abc-123")
        config = (self.output / courier.CONFIG_NAME).read_text(encoding="ascii")
        reader = next(item for item in result["files"] if item["path"] == courier.READER_NAME)
        profile_pin = next(item for item in result["files"] if item["path"] == courier.PROFILE_NAME)
        self.assertEqual(config,
            f"RR2XYZCOURIER1|abc-123|{reader['sha256']}|{reader['byteLength']}|"
            f"{profile_pin['sha256']}|{profile_pin['byteLength']}|{GAME_SHA}\n")

    def test_duplicate_separator_is_rejected_by_compiled_parser(self):
        self.prepare()
        path = self.output / courier.CONFIG_NAME
        path.write_text(path.read_text(encoding="ascii").replace("|test-courier-01|", "||test-courier-01|"),
                        encoding="ascii")
        outcome = self.run_preflight()
        self.assertEqual(outcome.returncode, 1)
        self.assertEqual(json.loads(outcome.stdout)["status"], "rejected")

    def test_extra_line_is_rejected_by_compiled_parser(self):
        self.prepare()
        path = self.output / courier.CONFIG_NAME
        path.write_text(path.read_text(encoding="ascii") + "extra\n", encoding="ascii")
        self.assertEqual(self.run_preflight().returncode, 1)

    def test_crlf_is_accepted_by_compiled_parser(self):
        self.prepare()
        path = self.output / courier.CONFIG_NAME
        path.write_bytes(path.read_bytes().rstrip(b"\n") + b"\r\n")
        self.assertEqual(self.run_preflight().returncode, 0)

    def test_reader_hash_drift_is_rejected_without_execution(self):
        self.prepare()
        (self.output / courier.READER_NAME).write_bytes(self.reader_data + b"drift")
        outcome = self.run_preflight()
        self.assertEqual(outcome.returncode, 1)
        self.assertIn("byte length differs", outcome.stderr)
        self.assertFalse(self.marker.exists())

    def test_profile_game_build_mismatch_is_rejected_by_actual_preflight(self):
        self.profile_data = (json.dumps(profile("B" * 64)) + "\n").encode()
        (self.bundle / courier.PROFILE_NAME).write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(courier.CourierPreparationError, "preflight failed"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_profile_duplicate_property_is_rejected_by_actual_preflight(self):
        original = json.dumps(profile())
        self.profile_data = original.replace('{', '{"schemaVersion":1,', 1).encode()
        (self.bundle / courier.PROFILE_NAME).write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(courier.CourierPreparationError, "preflight failed"):
            self.prepare()

    def test_different_pointer_recipe_is_rejected_by_actual_preflight(self):
        value = profile()
        value["rootRva"] = "0x32E0208"
        self.profile_data = (json.dumps(value) + "\n").encode()
        (self.bundle / courier.PROFILE_NAME).write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(courier.CourierPreparationError, "preflight failed"):
            self.prepare()

    def test_invalid_and_reserved_run_ids_are_rejected_before_output(self):
        for value in ("Upper", "bad_underscore", "-bad", "bad-", "con", "x" * 49):
            with self.subTest(value=value):
                with self.assertRaisesRegex(courier.CourierPreparationError, "run ID"):
                    courier.prepare(self.bundle, value, self.output)
                self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(courier.CourierPreparationError, "output must be new"):
            self.prepare()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_output_inside_prepared_bundle_is_rejected(self):
        with self.assertRaisesRegex(courier.CourierPreparationError, "must be separate"):
            courier.prepare(self.bundle, "nested-01", self.bundle / "courier")

    def test_competing_final_file_is_not_overwritten(self):
        original_write = courier.write_new
        injected = False

        def race(path, data):
            nonlocal injected
            if path == self.output / courier.READER_NAME and not injected:
                injected = True
                path.write_bytes(b"other-owner")
            return original_write(path, data)

        with mock.patch.object(courier, "write_new", side_effect=race):
            with self.assertRaises(FileExistsError):
                self.prepare()
        self.assertEqual((self.output / courier.READER_NAME).read_bytes(), b"other-owner")
        self.assertTrue((self.output / "INCOMPLETE.txt").exists())
        self.assertFalse((self.output / "courier-manifest.json").exists())

    def test_bundle_tamper_is_rejected_before_compiler_or_output(self):
        (self.bundle / courier.READER_NAME).write_bytes(self.reader_data + b"tamper")
        with mock.patch.object(courier.subprocess, "run") as invoke:
            with self.assertRaisesRegex(courier.CourierPreparationError, "differs from its pin"):
                self.prepare()
            invoke.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_profile_over_production_8k_limit_is_rejected(self):
        value = profile()
        value["evidenceReference"] = "x" * 9000
        self.profile_data = (json.dumps(value) + "\n").encode()
        (self.bundle / courier.PROFILE_NAME).write_bytes(self.profile_data)
        self.write_manifest()
        with self.assertRaisesRegex(courier.CourierPreparationError, "byte limit"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_process_continuity_and_archive_mutation_seams(self):
        harness = self.compile_harness()
        process = subprocess.run([str(harness), "process"], timeout=30)
        self.assertEqual(process.returncode, 0)
        archive = subprocess.run([str(harness), "archive-mutation", str(self.root)], timeout=30)
        self.assertEqual(archive.returncode, 0)
        self.assertFalse((self.root / "evidence.zip").exists())
        self.assertFalse((self.root / "evidence.zip.incomplete").exists())
        manifest = subprocess.run([str(harness), "manifest-mismatch", str(self.root)], timeout=30)
        self.assertEqual(manifest.returncode, 0)

    def test_manifest_is_acceptance_record_and_payloads_recheck(self):
        result = self.prepare()
        saved = json.loads((self.output / "courier-manifest.json").read_text())
        self.assertEqual(saved, result)
        self.assertFalse(saved["guestInstalled"])
        self.assertFalse(saved["networkUsed"])
        self.assertFalse(saved["liveValidated"])
        self.assertTrue(saved["pinsEstablishIntegrityNotAuthenticity"])
        self.assertTrue(saved["trustedExternalFinalBundlePinRequired"])
        for entry in saved["files"]:
            data = (self.output / entry["path"]).read_bytes()
            self.assertEqual((len(data), sha(data)),
                             (entry["byteLength"], entry["sha256"]))

    def test_cli_reports_preflight_passed_and_refuses_reuse(self):
        command = [sys.executable, str(courier.Path(courier.__file__)),
                   "--bundle", str(self.bundle), "--run-id", "cli-01",
                   "--output", str(self.output)]
        first = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["status"],
                         "courier-prepared-preflight-passed-not-deployed")
        second = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(second.returncode, 1)
        self.assertIn("output must be new", second.stderr)


if __name__ == "__main__":
    unittest.main()
