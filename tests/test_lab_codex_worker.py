import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts" / "Invoke-LabCodexJob.ps1"
SCHEMA = ROOT / "contracts" / "lab-codex" / "report.schema.json"
FIXTURE_SOURCE = ROOT / "tests" / "fixtures" / "lab-codex" / "FakeCodexCli.cs"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def active_process(pid: int) -> bool:
    if os.name != "nt" or pid <= 0:
        return False
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        return False
    try:
        code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(code)):
            return False
        return code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


@unittest.skipUnless(os.name == "nt" and CSC.is_file() and POWERSHELL,
                     "requires Windows PowerShell and the installed .NET Framework C# compiler")
class LabCodexWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WORKER.is_file():
            raise AssertionError(f"worker is missing: {WORKER}")
        cls.build_temp = tempfile.TemporaryDirectory(prefix="rr2-fake-codex-build-")
        cls.fake_cli = Path(cls.build_temp.name) / "FakeCodexCLI.exe"
        compiled = subprocess.run(
            [str(CSC), "/nologo", "/target:exe", f"/out:{cls.fake_cli}",
             str(FIXTURE_SOURCE)],
            capture_output=True, text=True, timeout=30,
        )
        if compiled.returncode:
            raise AssertionError(f"fake CLI compilation failed:\n{compiled.stdout}\n{compiled.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.build_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rr2-lab-codex-worker-")
        self.root = Path(self.temp.name)
        self.job = self.root / "job"
        self.job.mkdir()
        (self.job / "workspace").mkdir()
        shutil.copyfile(SCHEMA, self.job / "report.schema.json")
        self.job_id = "test-job-" + hashlib.sha256(str(self.root).encode()).hexdigest()[:12]
        self.request = {
            "schemaVersion": 1,
            "jobId": self.job_id,
            "lab": "lab1",
            "cliPath": str(self.fake_cli),
            "timeoutSeconds": 20,
        }
        self.pids = set()

    def tearDown(self):
        for name in ("fake-cli.pid", "fake-child.pid"):
            path = self.job / name
            if path.is_file():
                try:
                    self.pids.add(int(path.read_text().strip()))
                except (OSError, ValueError):
                    pass
        for pid in self.pids:
            if active_process(pid):
                subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=10)
        self.temp.cleanup()

    @staticmethod
    def valid_report(summary="synthetic success"):
        return {
            "schemaVersion": 1,
            "summary": summary,
            "findings": [{
                "claim": "The disposable fake CLI completed.",
                "confidence": "observed",
                "evidence": ["synthetic fixture only"],
            }],
            "limitations": ["No real Codex, RIFT, VM, or network operation was used."],
        }

    def prepare(self, task, *, timeout=20, request_mutator=None):
        self.request["timeoutSeconds"] = timeout
        if request_mutator:
            request_mutator(self.request)
        write_json(self.job / "request.json", self.request)
        (self.job / "task.md").write_text(
            task if isinstance(task, str) else json.dumps(task, separators=(",", ":")),
            encoding="utf-8",
        )
        return file_sha256(self.job / "request.json")

    def command(self, request_sha):
        return [
            POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(WORKER), "-JobDirectory", str(self.job),
            "-RequestSha256", request_sha,
        ]

    def run_worker(self, request_sha, timeout=35):
        return subprocess.run(self.command(request_sha), capture_output=True, text=True,
                              timeout=timeout, cwd=str(ROOT))

    def state(self):
        return json.loads((self.job / "state.json").read_text(encoding="utf-8-sig"))

    def worker_diagnostic(self, completed):
        state = self.job / "state.json"
        state_text = state.read_text(encoding="utf-8-sig") if state.is_file() else "<state missing>"
        return f"stdout={completed.stdout!r} stderr={completed.stderr!r} state={state_text}"

    def assert_terminal_common(self, state, expected):
        self.assertEqual(expected, state["status"])
        self.assertEqual(self.job_id, state["jobId"])
        self.assertEqual("lab1", state["lab"])
        self.assertEqual(file_sha256(self.job / "request.json"), state["requestSha256"])
        self.assertEqual(file_sha256(WORKER), state["workerSha256"])
        self.assertIn("workerPid", state)
        self.assertIn("workerStartUtcTicks", state)
        self.assertIsNotNone(state["startedAtUtc"])
        self.assertIsNotNone(state["updatedAtUtc"])
        self.assertIsNotNone(state["completedAtUtc"])
        serialized = json.dumps(state).lower()
        self.assertNotIn("do_not_report_stderr_sentinel", serialized)
        self.assertNotIn("password", serialized)

    def remember_fixture_pids(self):
        for name in ("fake-cli.pid", "fake-child.pid"):
            path = self.job / name
            if path.is_file():
                self.pids.add(int(path.read_text().strip()))

    def wait_for_fixture(self, process, *, child=False, timeout=12):
        deadline = time.monotonic() + timeout
        required = [self.job / "fake-cli.pid"]
        if child:
            required.append(self.job / "fake-child.pid")
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            if all(path.is_file() for path in required):
                self.remember_fixture_pids()
                return
            time.sleep(0.05)
        stdout, stderr = process.communicate(timeout=5)
        self.fail(f"fixture did not start; exit={process.returncode} stdout={stdout!r} stderr={stderr!r}")

    def assert_fixture_tree_stopped(self):
        self.remember_fixture_pids()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(active_process(pid) for pid in self.pids):
            time.sleep(0.05)
        self.assertTrue(self.pids, "fixture PID evidence was not written")
        self.assertFalse([pid for pid in self.pids if active_process(pid)],
                         "worker left its fake CLI process tree running")

    def test_success_publishes_hash_bound_schema_valid_report(self):
        request_sha = self.prepare(self.valid_report())
        completed = self.run_worker(request_sha)
        self.assertEqual(0, completed.returncode, self.worker_diagnostic(completed))
        state = self.state()
        self.assert_terminal_common(state, "succeeded")
        self.assertEqual(0, state["cliExitCode"])
        self.assertEqual(file_sha256(self.fake_cli), state["cliSha256"])
        self.assertIn("0.165.0-fake", state["cliVersion"])
        self.assertEqual({"path": "report.json", "byteLength": (self.job / "report.json").stat().st_size,
                          "sha256": file_sha256(self.job / "report.json")}, state["report"])
        self.assertEqual(self.valid_report(), json.loads((self.job / "report.json").read_text()))

    def test_request_sha_parameter_mismatch_fails_closed(self):
        actual_sha = self.prepare(self.valid_report())
        wrong_sha = ("0" if actual_sha[0] != "0" else "1") + actual_sha[1:]
        completed = self.run_worker(wrong_sha)
        self.assertNotEqual(0, completed.returncode)
        self.assertFalse((self.job / "state.json").exists(),
                         "untrusted request identity must not be published as state")
        self.assertFalse((self.job / "fake-cli.pid").exists(), "CLI ran despite request hash mismatch")

    def test_nonzero_cli_exit_is_failed_and_stderr_is_not_reported(self):
        request_sha = self.prepare("MODE_NONZERO")
        completed = self.run_worker(request_sha)
        self.assertNotEqual(0, completed.returncode)
        state = self.state()
        self.assert_terminal_common(state, "failed")
        self.assertEqual(23, state["cliExitCode"])
        self.assertIsNone(state["report"])
        self.assertEqual("cli-nonzero-exit", state["errorCode"])
        self.assertNotIn("DO_NOT_REPORT_STDERR_SENTINEL", completed.stdout + completed.stderr)

    def test_preexisting_report_is_refused_before_cli_and_cannot_be_reused(self):
        stale = self.valid_report("stale report must not survive")
        write_json(self.job / "report.json", stale)
        stale_hash = file_sha256(self.job / "report.json")
        request_sha = self.prepare("MODE_INVALID_JSON")
        completed = self.run_worker(request_sha)
        self.assertNotEqual(0, completed.returncode)
        self.assertFalse((self.job / "state.json").exists())
        self.assertFalse((self.job / "fake-cli.pid").exists())
        self.assertEqual(stale_hash, file_sha256(self.job / "report.json"),
                         "worker must refuse rather than bless or rewrite a stale report")

    def test_zero_exit_invalid_json_publishes_failed_terminal_state(self):
        request_sha = self.prepare("MODE_INVALID_JSON")
        completed = self.run_worker(request_sha)
        self.assertNotEqual(0, completed.returncode)
        state = self.state()
        self.assert_terminal_common(state, "failed")
        self.assertEqual(0, state["cliExitCode"])
        self.assertIsNone(state["report"])
        self.assertEqual("report-invalid", state["errorCode"])

    def test_schema_invalid_report_is_not_success(self):
        request_sha = self.prepare({"schemaVersion": 1, "summary": "missing arrays"})
        completed = self.run_worker(request_sha)
        self.assertNotEqual(0, completed.returncode)
        state = self.state()
        self.assert_terminal_common(state, "failed")
        self.assertIsNone(state["report"])
        self.assertEqual("report-invalid", state["errorCode"])

    def test_timeout_terminates_owned_cli_and_child(self):
        request_sha = self.prepare("MODE_HANG", timeout=5)
        completed = self.run_worker(request_sha, timeout=20)
        self.assertNotEqual(0, completed.returncode)
        state = self.state()
        self.assert_terminal_common(state, "timed-out")
        self.assertIsNone(state["report"])
        self.assertEqual("timed-out", state["errorCode"])
        self.assert_fixture_tree_stopped()

    def test_matching_cancel_request_terminates_owned_cli_and_child(self):
        request_sha = self.prepare("MODE_HANG", timeout=30)
        process = subprocess.Popen(self.command(request_sha), cwd=str(ROOT),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.wait_for_fixture(process, child=True)
        write_json(self.job / "cancel.request", {
            "jobId": self.job_id,
            "requestSha256": request_sha,
        })
        stdout, stderr = process.communicate(timeout=15)
        self.assertNotEqual(0, process.returncode, stdout + stderr)
        state = self.state()
        self.assert_terminal_common(state, "cancelled")
        self.assertIsNone(state["report"])
        self.assertEqual("cancelled", state["errorCode"])
        self.assert_fixture_tree_stopped()

    def test_mismatched_cancel_request_does_not_cancel_another_job(self):
        request_sha = self.prepare("MODE_HANG", timeout=5)
        process = subprocess.Popen(self.command(request_sha), cwd=str(ROOT),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.wait_for_fixture(process, child=True)
        write_json(self.job / "cancel.request", {
            "jobId": "different-job",
            "requestSha256": "F" * 64,
        })
        stdout, stderr = process.communicate(timeout=15)
        self.assertNotEqual(0, process.returncode, stdout + stderr)
        state = self.state()
        self.assert_terminal_common(state, "timed-out")
        self.assertEqual("timed-out", state["errorCode"])
        self.assert_fixture_tree_stopped()


if __name__ == "__main__":
    unittest.main()
