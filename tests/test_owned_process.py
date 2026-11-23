import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

from scripts import owned_process
from scripts.owned_process import OwnedProcessError, run_owned


@unittest.skipUnless(os.name == "nt", "Windows Job Objects are required")
class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.cleanup_temporary)
        self.root = Path(self.temporary.name)
        self.counter = 0

    def cleanup_temporary(self):
        # A just-terminated Windows process can release its cwd a few milliseconds
        # after the Job Object reports zero active processes.
        for attempt in range(20):
            try:
                self.temporary.cleanup()
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.05)

    def logs(self):
        self.counter += 1
        return self.root / f"logs-{self.counter}"

    def run_python(self, source, **options):
        return run_owned([sys.executable, "-c", source], cwd=self.root,
                         log_directory=self.logs(), timeout_seconds=5, **options)

    def test_normal_exit_captures_separate_bounded_logs(self):
        result = self.run_python(
            "import sys; print('hello'); print('warning', file=sys.stderr); raise SystemExit(7)")
        self.assertEqual(7, result.returncode)
        self.assertEqual(["hello"], result.stdout.splitlines())
        self.assertEqual(["warning"], result.stderr.splitlines())
        self.assertTrue(result.confirmed_cleanup)
        self.assertEqual("completed", result.metadata["status"])
        self.assertNotIn("command", result.metadata)
        for name in ("stdout", "stderr"):
            self.assertTrue(Path(result.metadata["logs"][name]).is_file())
            self.assertEqual(64, len(result.metadata["logs"][name + "Sha256"]))

    def test_exit_code_259_is_preserved_after_process_is_signalled(self):
        result = self.run_python("raise SystemExit(259)")
        self.assertEqual(259, result.returncode)
        self.assertTrue(result.confirmed_cleanup)

    def test_owned_child_receives_a_unicode_environment_without_changing_the_parent(self):
        java_home = str(self.root / "JDK with spacés")
        parent = os.environ.get("JAVA_HOME")
        result = self.run_python("import os; print(ascii(os.environ['JAVA_HOME']))",
                                 env=dict(os.environ, JAVA_HOME=java_home))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), ascii(java_home))
        self.assertEqual(os.environ.get("JAVA_HOME"), parent)

    def test_exit_code_query_failure_is_not_reported_as_completion(self):
        real = owned_process._kernel32()

        class KernelProxy:
            def __getattr__(self, name):
                return getattr(real, name)

            def GetExitCodeProcess(self, process, code):
                return False

        with mock.patch.object(owned_process, "_kernel32", return_value=KernelProxy()):
            with self.assertRaises(OwnedProcessError) as caught:
                self.run_python("raise SystemExit(0)")
        self.assertEqual("exit-code-unavailable", caught.exception.metadata["status"])
        self.assertTrue(caught.exception.result.confirmed_cleanup)
        self.assertIsNone(caught.exception.result.returncode)

    def test_failed_attribute_list_initialization_is_not_deleted(self):
        real = owned_process._kernel32()

        class KernelProxy:
            def __init__(self):
                self.initialize_calls = 0
                self.delete_calls = 0

            def __getattr__(self, name):
                return getattr(real, name)

            def InitializeProcThreadAttributeList(self, attribute_list, count, flags, size):
                self.initialize_calls += 1
                if self.initialize_calls == 2:
                    return False
                return real.InitializeProcThreadAttributeList(attribute_list, count, flags, size)

            def DeleteProcThreadAttributeList(self, attribute_list):
                self.delete_calls += 1
                return real.DeleteProcThreadAttributeList(attribute_list)

        proxy = KernelProxy()
        with mock.patch.object(owned_process, "_kernel32", return_value=proxy):
            with self.assertRaises(OwnedProcessError) as caught:
                self.run_python("raise SystemExit(0)")
        self.assertEqual("failed", caught.exception.metadata["status"])
        self.assertIsNone(caught.exception.metadata["launcherPid"])
        self.assertEqual(0, proxy.delete_calls)

    def test_launcher_exit_waits_for_owned_descendant(self):
        marker = self.root / "descendant-finished"
        child = "import pathlib,time; time.sleep(.35); pathlib.Path(r'%s').write_text('done')" % marker
        launcher = "import subprocess,sys; subprocess.Popen([sys.executable,'-c',%r])" % child
        started = time.monotonic()
        result = self.run_python(launcher)
        self.assertGreaterEqual(time.monotonic() - started, .25)
        self.assertEqual("done", marker.read_text())
        self.assertGreaterEqual(result.metadata["totalProcesses"], 2)
        self.assertTrue(result.confirmed_cleanup)

    def test_timeout_terminates_launcher_child_and_grandchild(self):
        marker = self.root / "must-not-exist"
        grandchild = "import pathlib,time; time.sleep(2); pathlib.Path(r'%s').write_text('escaped')" % marker
        child = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(3)" % grandchild
        launcher = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(3)" % child
        with self.assertRaises(OwnedProcessError) as caught:
            run_owned([sys.executable, "-c", launcher], cwd=self.root,
                      log_directory=self.logs(), timeout_seconds=.2)
        self.assertEqual("timed-out", caught.exception.metadata["status"])
        self.assertTrue(caught.exception.result.confirmed_cleanup)
        self.assertGreaterEqual(caught.exception.metadata["totalProcesses"], 2)
        time.sleep(.35)
        self.assertFalse(marker.exists())

    def test_cancel_reason_terminates_owned_job(self):
        calls = 0
        def cancel():
            nonlocal calls
            calls += 1
            return "session-stop-epoch-changed" if calls >= 3 else None
        with self.assertRaises(OwnedProcessError) as caught:
            run_owned([sys.executable, "-c", "import time; time.sleep(5)"], cwd=self.root,
                      log_directory=self.logs(), timeout_seconds=5, cancel_check=cancel)
        self.assertEqual("cancelled", caught.exception.metadata["status"])
        self.assertEqual("session-stop-epoch-changed", caught.exception.metadata["reason"])
        self.assertTrue(caught.exception.result.confirmed_cleanup)

    def test_cancel_callback_error_still_terminates_owned_job(self):
        marker = self.root / "callback-error-escaped"
        source = "import pathlib,time; time.sleep(2); pathlib.Path(r'%s').write_text('bad')" % marker
        def broken():
            raise RuntimeError("cancel-state-unavailable")
        with self.assertRaises(OwnedProcessError) as caught:
            run_owned([sys.executable, "-c", source], cwd=self.root,
                      log_directory=self.logs(), timeout_seconds=5, cancel_check=broken)
        self.assertEqual("failed", caught.exception.metadata["status"])
        self.assertIn("cancel-state-unavailable", caught.exception.metadata["reason"])
        self.assertTrue(caught.exception.result.confirmed_cleanup)
        time.sleep(.1)
        self.assertFalse(marker.exists())

    def test_keyboard_interrupt_still_terminates_owned_job_then_propagates(self):
        marker = self.root / "interrupt-escaped"
        source = "import pathlib,time; time.sleep(2); pathlib.Path(r'%s').write_text('bad')" % marker
        def interrupt():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run_owned([sys.executable, "-c", source], cwd=self.root,
                      log_directory=self.logs(), timeout_seconds=5, cancel_check=interrupt)
        time.sleep(.1)
        self.assertFalse(marker.exists())

    def test_windows_command_line_quoting_preserves_arguments(self):
        script = self.root / "script with spaces.py"
        script.write_text("import sys; print(repr(sys.argv[1:]))")
        result = run_owned([sys.executable, script, "space value", 'quote"value'], cwd=self.root,
                           log_directory=self.logs(), timeout_seconds=5)
        self.assertEqual(["space value", 'quote"value'], __import__("ast").literal_eval(result.stdout.strip()))

    def test_output_limit_terminates_tree_and_retains_bounded_result(self):
        with self.assertRaises(OwnedProcessError) as caught:
            run_owned([sys.executable, "-c",
                       "import sys,time; sys.stdout.write('x'*200000); sys.stdout.flush(); time.sleep(5)"],
                      cwd=self.root, log_directory=self.logs(), timeout_seconds=5,
                      max_output_bytes=1024)
        result = caught.exception.result
        self.assertEqual("output-limit-exceeded", result.metadata["status"])
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 1024)
        self.assertTrue(result.metadata["logs"]["stdoutTruncated"])
        self.assertGreater(result.metadata["logs"]["stdoutObservedBytes"], 1024)
        self.assertLessEqual(
            Path(result.metadata["logs"]["stdout"]).stat().st_size
            + Path(result.metadata["logs"]["stderr"]).stat().st_size,
            1024,
        )
        self.assertTrue(result.confirmed_cleanup)

    def test_existing_log_directory_is_never_reused_or_deleted(self):
        logs = self.logs()
        logs.mkdir()
        sentinel = logs / "keep.txt"
        sentinel.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "already exists"):
            run_owned([sys.executable, "-c", "print('no')"], cwd=self.root,
                      log_directory=logs, timeout_seconds=1)
        self.assertEqual("preserve", sentinel.read_text())

    def test_invalid_inputs_fail_before_log_creation(self):
        cases = [
            ([sys.executable], {"timeout_seconds": 0}),
            ([sys.executable], {"timeout_seconds": float("inf")}),
            ([sys.executable], {"timeout_seconds": 1, "max_output_bytes": 0}),
            ([sys.executable], {"timeout_seconds": 1, "cancel_check": "not-callable"}),
            ("not-a-sequence", {"timeout_seconds": 1}),
            (["missing-owned-process-executable.exe"], {"timeout_seconds": 1}),
        ]
        for index, (command, options) in enumerate(cases):
            logs = self.root / f"invalid-{index}"
            with self.subTest(index=index), self.assertRaises(ValueError):
                run_owned(command, cwd=self.root, log_directory=logs, **options)
            self.assertFalse(logs.exists())


if __name__ == "__main__":
    unittest.main()
