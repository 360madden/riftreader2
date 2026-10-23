"""Direct-shell request transport: safe validation and real PowerShell roundtrip."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).parents[1] / "scripts" / "prepare_direct_shell_pointer.py"
SPEC = importlib.util.spec_from_file_location("rr2_direct_ps", SOURCE)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
BUILD = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
TARGET = {"processId": 2768, "processStartUtcTicks": 639282812576974124, "executableSha256": BUILD}
EXE = r"C:\RIFT_TRANSFER\RiftReader2Control\build-5ae1b56791ad\RiftReader2.Live.exe"

class DirectShellPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_exact_identity_request(self):
        request, commands = module.prepare(TARGET, "example", EXE)
        self.assertEqual(request["target"], TARGET)
        self.assertEqual(request["rootRva"], "0x32E0200")
        self.assertEqual(request["terminalByteLength"], 816)
        self.assertTrue(commands[0].startswith("Set-Content "))
        self.assertTrue(all(cmd.startswith("Add-Content ") for cmd in commands[1:-3]))
        self.assertTrue(commands[-3].startswith("certutil -f -decode "))
        self.assertTrue(commands[-2].startswith("Get-FileHash "))
        self.assertIn("follow-pointer", commands[-1])
        self.assertLessEqual(max(map(len, commands)), 220)

    def test_rejects_invalid_target(self):
        for field, value in [("processId", 0), ("processId", True),
                             ("processStartUtcTicks", 0), ("executableSha256", "0"*63)]:
            with self.subTest(field=field, value=value):
                target = dict(TARGET); target[field] = value
                with self.assertRaises(module.PlanError):
                    module.prepare(target, "test", EXE)

    def test_rejects_shell_metacharacters(self):
        for exe in (EXE+" & calc", EXE.replace("RIFT_TRANSFER", "RIFT TRANSFER"),
                    "../RiftReader2.Live.exe", EXE + chr(96)):
            with self.subTest(exe=exe):
                with self.assertRaises(module.PlanError):
                    module.prepare(TARGET, "test", exe)

    def test_unsafe_output_names_fail(self):
        for name in ("", "../escape", "space name", "x&x", "x"*25):
            with self.subTest(name=name):
                with self.assertRaises(module.PlanError):
                    module.prepare(TARGET, name, EXE)

    def test_atomic_publication_and_no_overwrite(self):
        req, commands = module.prepare(TARGET, "test", EXE)
        manifest = module.publish(self.root, req, commands)
        self.assertFalse(manifest["readerExecuted"])
        self.assertTrue(manifest["verifyGuestHashBeforeReader"])
        originals = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in self.root.iterdir()}
        with self.assertRaises(module.PlanError):
            module.publish(self.root, req, commands)
        self.assertEqual(originals, {p.name: hashlib.sha256(p.read_bytes()).digest() for p in self.root.iterdir()})

    def test_missing_output_directory_rejected(self):
        req, commands = module.prepare(TARGET, "test", EXE)
        with self.assertRaises(module.PlanError):
            module.publish(self.root/"missing", req, commands)

    @unittest.skipUnless(sys.platform=="win32", "Requires Windows PowerShell and CertUtil")
    def test_actual_powershell_content_and_certutil_roundtrip(self):
        req, commands = module.prepare(TARGET, "roundtrip", EXE)
        powershell = [
            c.replace("$env:TEMP\\rr2-roundtrip", str(self.root/"rr2-roundtrip"))
            for c in commands[:-2]
        ]
        # The final two commands are inspection and native execution. Neither
        # belongs in an automated real-OS roundtrip test.
        for cmd in powershell:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                "-Command", cmd], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root/"rr2-roundtrip.json").read_bytes(), module.encode(req))

    def test_deterministic_output(self):
        self.assertEqual(module.prepare(TARGET, "same", EXE), module.prepare(dict(TARGET), "same", EXE))

if __name__=="__main__":
    unittest.main()
