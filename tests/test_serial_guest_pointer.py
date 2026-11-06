"""Bounded Windows-Run transport plans must be reproducible and fail closed."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_serial_guest_pointer.py"
SPEC = importlib.util.spec_from_file_location("rr2_serial_guest_pointer", SCRIPT)
plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan)

BUILD = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
EXECUTABLE = r"C:\RIFT_TRANSFER\RiftReader2Control\build-5ae1b56791ad\RiftReader2.Live.exe"
TARGET = {
    "processId": 2768,
    "processStartUtcTicks": 639282812576974124,
    "executableSha256": BUILD
}


class SerialGuestPointerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def create(self, **changes):
        target = dict(TARGET)
        target.update(changes)
        return plan.build(target, "test", EXECUTABLE)

    def test_exact_request_and_short_commands(self):
        request, commands = self.create()
        self.assertEqual(request["target"], TARGET)
        self.assertEqual(request["rootRva"], "0x32E0200")
        self.assertEqual(request["offsets"], ["0x0"])
        self.assertEqual(request["terminalByteLength"], 816)
        self.assertLessEqual(len(commands), plan.MAX_STEPS)
        self.assertLessEqual(max(map(len, commands)), plan.MAX_COMMAND)
        self.assertTrue(commands[-3].startswith("cmd.exe /c certutil -f -decode "))
        self.assertTrue(commands[-2].startswith("cmd.exe /k certutil -hashfile "))
        self.assertIn("follow-pointer --request ", commands[-1])
        self.assertTrue(all("\n" not in cmd for cmd in commands))

    def test_generated_commands_are_not_sent_to_a_vm(self):
        request, commands = self.create()
        result = plan.publish(self.folder, request, commands)
        self.assertEqual(result["nativeResult"], "unverified-until-real-guest-report")
        self.assertTrue(result["neverTreatWindowsRunSuccessAsNativeSuccess"])
        self.assertTrue(result["processIdentityMustBeReverifiedBeforeRun"])
        self.assertTrue(result["lastCommandRequiresDecodedRequestVerification"])
        self.assertEqual(result["commandCount"], len(commands))
        self.assertEqual(
            result["requestSha256"],
            hashlib.sha256(plan.canonical(request)).hexdigest().upper()
        )
        for i in range(len(commands)):
            step = json.loads((self.folder / f"step-{i+1:02}.json").read_bytes())
            self.assertEqual(step["actions"], [{"type": "windowsRunText", "text": commands[i]}])
        self.assertFalse(any(p.name.endswith("-result.json") for p in self.folder.iterdir()))

    def test_publish_refuses_to_replace_any_artifact(self):
        request, commands = self.create()
        plan.publish(self.folder, request, commands)
        initial = {
            p.name: hashlib.sha256(p.read_bytes()).digest()
            for p in self.folder.iterdir() if p.is_file()
        }
        with self.assertRaisesRegex(plan.TransportPlanError, "already exist"):
            plan.publish(self.folder, request, commands)
        self.assertEqual(initial, {
            p.name: hashlib.sha256(p.read_bytes()).digest()
            for p in self.folder.iterdir() if p.is_file()
        })

    def test_missing_directory_is_rejected(self):
        request, commands = self.create()
        with self.assertRaisesRegex(plan.TransportPlanError, "already exist"):
            plan.publish(self.folder / "absent", request, commands)

    def test_wrong_identity_or_build_rejected(self):
        for changes in (
            {"processId": 0}, {"processId": True},
            {"processStartUtcTicks": 0}, {"processStartUtcTicks": True},
            {"executableSha256": "a" * 64},
            {"executableSha256": "0" * 63},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(plan.TransportPlanError):
                    self.create(**changes)

    def test_rejects_shell_metacharacters_and_bad_paths(self):
        for exe in (
            r"C:\RIFT_TRANSFER\RiftReader2.Live.exe & whoami",
            r"C:\RIFT TRANSFER\RiftReader2.Live.exe",
            r"C:\RIFT_TRANSFER\not-the-reader.exe",
            r"..\RiftReader2.Live.exe",
        ):
            with self.subTest(exe=exe):
                with self.assertRaises(plan.TransportPlanError):
                    plan.build(TARGET, "valid", exe)

    def test_rejects_unsafe_output_names(self):
        for name in ("../escape", "foo_bar", "", "a" * 25, "bad name", "x&calc"):
            with self.subTest(name=name):
                with self.assertRaises(plan.TransportPlanError):
                    plan.build(TARGET, name, EXECUTABLE)

    def test_rejects_unbounded_terminal_or_noncanonical_rva(self):
        for length in (0, 811, 1025, True):
            with self.subTest(length=length):
                with self.assertRaises(plan.TransportPlanError):
                    plan.build(TARGET, "valid", EXECUTABLE, terminal_bytes=length)
        for rva in ("0X32E0200", "0x00032E0200", "0xzz", "0x32E0200;echo"):
            with self.subTest(rva=rva):
                with self.assertRaises(plan.TransportPlanError):
                    plan.build(TARGET, "valid", EXECUTABLE, root_rva=rva)

    @unittest.skipUnless(sys.platform == "win32", "Windows CMD/certutil integration")
    def test_actual_windows_cmd_and_certutil_reconstruct_identical_request(self):
        request, commands = self.create()
        for command in commands[:-2]:
            # The last command executes the real native reader and the prior
            # command opens an interactive hash display. Neither belongs here.
            on_host = command.replace(r"%TEMP%", str(self.folder))
            proc = subprocess.run(
                ["cmd.exe", "/d", "/c", on_host.removeprefix("cmd.exe /c ")],
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
        produced = self.folder / "rr2-test.json"
        self.assertEqual(produced.read_bytes(), plan.canonical(request))
        self.assertEqual(
            hashlib.sha256(produced.read_bytes()).hexdigest().upper(),
            hashlib.sha256(plan.canonical(request)).hexdigest().upper(),
        )

    def test_deterministic_plan_ignores_unrelated_worktree_changes(self):
        one = self.create()
        two = self.create()
        self.assertEqual(one, two)

    def test_cli_can_publish_but_not_execute_any_guest_command(self):
        argv = [
            str(SCRIPT), "--pid", str(TARGET["processId"]),
            "--start-ticks", str(TARGET["processStartUtcTicks"]),
            "--build", BUILD, "--name", "cli-test",
            "--guest-exe", EXECUTABLE, "--out-dir", str(self.folder)
        ]
        with patch.object(sys, "argv", argv):
            self.assertEqual(plan.main(), 0)
        self.assertTrue((self.folder / "request.json").is_file())
        with patch.object(sys, "argv", argv):
            self.assertEqual(plan.main(), 2)


if __name__ == "__main__":
    unittest.main()
