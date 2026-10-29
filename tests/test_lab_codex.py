from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lab_codex", ROOT / "scripts" / "lab_codex.py")
lab_codex = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab_codex)


class FakeTransport:
    def __init__(self):
        self.files = {}
        self.calls = []
        self.copy_from_count = 0
        self.doctor_result = None

    def factory(self, *args, **kwargs):
        return FakeSession(self, args, kwargs)


class FakeSession:
    def __init__(self, transport, args, kwargs):
        self.transport = transport
        self.check = args[2]

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *_):
        return False

    def run(self, command, *arguments, timeout=60):
        self.check()
        self.transport.calls.append((command, arguments, timeout))
        if command == "copyFileFromHostToGuest":
            self.transport.files[arguments[1]] = Path(arguments[0]).read_bytes()
        elif command == "runProgramInGuest" and "-ResultPath" in arguments:
            result_path = arguments[arguments.index("-ResultPath") + 1]
            value = self.transport.doctor_result or {
                "schemaVersion": 1, "byteLength": 123456, "sha256": "B" * 64,
                "version": "codex-cli 0.165.0", "versionExitCode": 0,
                "loginExitCode": 0, "loginAvailable": True, "errorCode": None,
                "phase": "completed", "exceptionType": None,
                "fullyQualifiedErrorId": None, "scriptLine": None,
            }
            self.transport.files[result_path] = (json.dumps(value) + "\n").encode()
        return ""

    def powershell(self, script, timeout=150):
        self.check()
        self.transport.calls.append(("powershell", (script,), timeout))
        if ".probe-" in script and "WriteAllText" in script:
            target = script.split("$t='", 1)[1].split("'", 1)[0]
            output = script.split("$o='", 1)[1].split("'", 1)[0]
            value = {"schemaVersion": 1, "present": target in self.transport.files}
            self.transport.files[output] = json.dumps(value).encode()
        if "cancel.request.incoming" in script:
            incoming = next(key for key in self.transport.files if key.endswith("cancel.request.incoming"))
            self.transport.files[incoming.removesuffix(".incoming")] = self.transport.files.pop(incoming)
        return ""

    def copy_from_guest(self, guest_path, destination, timeout=60):
        self.check()
        self.transport.copy_from_count += 1
        if guest_path not in self.transport.files:
            raise lab_codex.SessionError("guest-command-failed:copyFileFromGuestToHost")
        Path(destination).write_bytes(self.transport.files[guest_path])
        return Path(destination)


class Fixture:
    def __init__(self, root: Path):
        self.base = root
        self.repo = root / "repo"; self.repo.mkdir()
        self.runs = root / "runs"
        self.worker = root / "Invoke-LabCodexJob.ps1"
        self.worker.write_text("param($JobDirectory,$RequestSha256)\n", encoding="utf-8")
        self.vmx = root / "lab.vmx"; self.vmx.write_text("vm", encoding="utf-8")
        self.vmx2 = root / "lab2.vmx"; self.vmx2.write_text("vm2", encoding="utf-8")
        self.vmrun = root / "vmrun.exe"; self.vmrun.write_text("exe", encoding="utf-8")
        (self.repo / "task.md").write_text("Review input.\n", encoding="utf-8")
        (self.repo / "input.txt").write_text("tracked bytes\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "task.md", "input.txt"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "fixture"], check=True)
        self.config = root / "config.json"
        self.config.write_text(json.dumps({
            "schemaVersion": 1, "vmrun": str(self.vmrun), "labs": {
                "lab1": {"vmx": str(self.vmx), "vncPort": 5905,
                         "cliPath": r"C:\Tools\codex.exe", "guestRoot": r"C:\Jobs"},
                "lab2": {"vmx": str(self.vmx2), "vncPort": 5906,
                         "cliPath": r"C:\Tools\codex.exe", "guestRoot": r"C:\Jobs2"},
            }}, indent=2), encoding="utf-8")
        self.transport = FakeTransport()
        self.identity = {"pid": 42, "startTicks": 99, "vmx": "fixture"}
        self.verify_calls = []
        self.tool = lab_codex.LabCodex(
            self.config, repo_root=self.repo, run_root=self.runs, worker_path=self.worker,
            session_factory=self.transport.factory,
            collect=lambda _native: dict(self.identity),
            verify=self.verify,
            sleep=lambda _seconds: None,
        )

    def verify(self, _native, expected):
        self.verify_calls.append(expected)
        return dict(expected)

    def dispatch(self, lab="lab1"):
        return self.tool.dispatch(lab, "task.md", ["input.txt"], 30)

    def state(self, receipt, status="running", report=None, **updates):
        value = {
            "schemaVersion": 1, "jobId": receipt["jobId"], "lab": receipt["lab"],
            "requestSha256": receipt["requestSha256"],
            "workerSha256": receipt["workerSha256"], "status": status,
            "workerPid": 100, "workerStartUtcTicks": 200, "cliPid": 101,
            "cliStartUtcTicks": 201, "cliSha256": "A" * 64,
            "cliVersion": "codex-cli 0.165.0", "cliExitCode": None,
            "errorCode": None, "startedAtUtc": "2026-10-29T00:00:00Z",
            "updatedAtUtc": "2026-10-29T00:00:01Z",
            "completedAtUtc": ("2026-10-29T00:00:02Z"
                               if status in lab_codex.TERMINAL else None),
            "report": report,
        }
        value.update(updates)
        path = receipt["guestJobDirectory"] + r"\state.json"
        self.transport.files[path] = (json.dumps(value) + "\n").encode()
        return value


class LabCodexTests(unittest.TestCase):
    def test_dispatch_pins_provenance_stages_verified_bundle_and_launches_fixed_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            result = fixture.dispatch()
            run = Path(result["run"]); receipt = result["provenance"]
            self.assertEqual("dispatched", result["status"])
            self.assertEqual(fixture.identity, receipt["vmIdentity"])
            self.assertEqual(40, len(receipt["git"]["head"]))
            self.assertEqual(lab_codex._sha((fixture.repo / "input.txt").read_bytes()),
                             receipt["inputs"][0]["sha256"])
            with zipfile.ZipFile(run / "workspace.zip") as archive:
                self.assertEqual(["workspace/", "workspace/input.txt"], archive.namelist())
                self.assertEqual((fixture.repo / "input.txt").read_bytes(),
                                 archive.read("workspace/input.txt"))
            launch = [call for call in fixture.transport.calls
                      if call[0] == "runProgramInGuest" and "-noWait" in call[1]][0]
            self.assertIn(r"C:\Jobs" + "\\" + receipt["jobId"] +
                          r"\Invoke-LabCodexJob.ps1", launch[1])
            self.assertIn("-WindowStyle", launch[1])
            self.assertIn("Hidden", launch[1])
            self.assertEqual(receipt, json.loads((run / "run.json").read_text()))
            powershell_scripts = [call[1][0] for call in fixture.transport.calls
                                  if call[0] == "powershell"]
            self.assertFalse(any("Get-FileHash" in script for script in powershell_scripts))
            self.assertTrue(all(len(__import__("base64").b64encode(
                script.encode("utf-16-le"))) <= 4096 for script in powershell_scripts))

    def test_missing_worker_and_untracked_input_fail_before_guest_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory)); fixture.worker.unlink()
            with self.assertRaisesRegex(lab_codex.LabCodexError, "worker-unavailable"):
                fixture.dispatch()
            fixture.worker.write_text("worker", encoding="utf-8")
            (fixture.repo / "untracked.txt").write_text("no", encoding="utf-8")
            with self.assertRaisesRegex(lab_codex.LabCodexError, "untracked-input"):
                fixture.tool.dispatch("lab1", "task.md", ["untracked.txt"], 30)
            self.assertEqual([], fixture.transport.calls)

    def test_ad_hoc_untracked_task_is_snapshotted_but_untracked_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            task = fixture.repo / "ad-hoc.md"; task.write_text("One-off analysis.\n")
            dispatched = fixture.tool.dispatch("lab1", "ad-hoc.md", ["input.txt"], 30)
            receipt = dispatched["provenance"]
            self.assertEqual("ad-hoc.md", receipt["task"]["path"])
            self.assertEqual(lab_codex._sha(task.read_bytes()), receipt["task"]["sha256"])

    def test_status_rejects_config_drift_vm_drift_and_state_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory)); dispatched = fixture.dispatch()
            run = Path(dispatched["run"]); receipt = dispatched["provenance"]
            fixture.state(receipt)
            self.assertEqual("running", fixture.tool.status(run)["status"])
            original = fixture.config.read_text(); fixture.config.write_text(original + " ")
            with self.assertRaisesRegex(lab_codex.LabCodexError, "config-drift"):
                fixture.tool.status(run)
            fixture.config.write_text(original)
            fixture.tool.verify_identity = lambda *_: {"pid": 999}
            with self.assertRaisesRegex(lab_codex.LabCodexError, "vm-identity-drift"):
                fixture.tool.status(run)
            fixture.tool.verify_identity = fixture.verify
            fixture.state(receipt, lab="wrong")
            with self.assertRaisesRegex(lab_codex.LabCodexError, "state-identity-invalid"):
                fixture.tool.status(run)

    def test_collect_validates_report_and_is_repeatable_without_guest_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory)); dispatched = fixture.dispatch()
            run = Path(dispatched["run"]); receipt = dispatched["provenance"]
            report = {"schemaVersion": 1, "summary": "Observed source.",
                      "findings": [{"claim": "A", "confidence": "observed",
                                    "evidence": ["input.txt:1"]}],
                      "limitations": ["Guest claim requires host review."]}
            report_bytes = (json.dumps(report) + "\n").encode()
            ref = {"path": "report.json", "byteLength": len(report_bytes),
                   "sha256": lab_codex._sha(report_bytes)}
            fixture.state(receipt, "succeeded", ref, cliExitCode=0,
                          completedAtUtc="2026-10-29T00:00:02Z")
            fixture.transport.files[receipt["guestJobDirectory"] + r"\report.json"] = report_bytes
            first = fixture.tool.collect(run); copies = fixture.transport.copy_from_count
            second = fixture.tool.collect(run)
            self.assertEqual(first, second)
            self.assertEqual(copies, fixture.transport.copy_from_count)
            self.assertEqual("guest-report-requires-main-host-review", first["evidenceBoundary"])
            self.assertEqual(report_bytes, (run / "report.json").read_bytes())

    def test_invalid_report_and_failed_terminal_state_are_retained_honestly(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory)); one = fixture.dispatch()
            run = Path(one["run"]); receipt = one["provenance"]
            bad = b'{"schemaVersion":1}\n'
            ref = {"path": "report.json", "byteLength": len(bad), "sha256": lab_codex._sha(bad)}
            fixture.state(receipt, "succeeded", ref, cliExitCode=0)
            fixture.transport.files[receipt["guestJobDirectory"] + r"\report.json"] = bad
            with self.assertRaisesRegex(lab_codex.LabCodexError, "report-validation-failed"):
                fixture.tool.collect(run)
            two = fixture.dispatch("lab2"); second_run = Path(two["run"])
            fixture.state(two["provenance"], "failed", None, cliExitCode=7,
                          errorCode="cli-nonzero")
            collected = fixture.tool.collect(second_run)
            self.assertEqual("failed", collected["status"])
            self.assertIsNone(collected["report"])
            self.assertEqual(7, collected["state"]["cliExitCode"])

    def test_cancel_publishes_only_exact_job_and_request_hash_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory)); dispatched = fixture.dispatch()
            run = Path(dispatched["run"]); receipt = dispatched["provenance"]
            fixture.state(receipt)
            first = fixture.tool.cancel(run); second = fixture.tool.cancel(run)
            self.assertEqual(first, second)
            request = json.loads((run / "cancel.request").read_text())
            self.assertEqual({"jobId": receipt["jobId"],
                              "requestSha256": receipt["requestSha256"]}, request)
            guest = receipt["guestJobDirectory"] + r"\cancel.request"
            self.assertEqual(request, json.loads(fixture.transport.files[guest]))

    def test_cancel_is_noop_after_terminal_state(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory)); dispatched = fixture.dispatch()
            run = Path(dispatched["run"]); receipt = dispatched["provenance"]
            fixture.state(receipt, "cancelled", None, cliExitCode=130)
            result = fixture.tool.cancel(run)
            self.assertEqual("cancelled", result["status"])
            self.assertFalse(result["cancelRequested"])
            self.assertFalse((run / "cancel.request").exists())

    def test_doctor_sanitizes_cli_output_and_never_returns_account_text(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory)); result = fixture.tool.doctor("lab1")
            encoded = json.dumps(result)
            self.assertEqual("ready", result["status"])
            self.assertEqual("codex-cli 0.165.0", result["cli"]["version"])
            self.assertEqual("B" * 64, result["cli"]["sha256"])
            self.assertNotIn("example.test", encoded)
            self.assertEqual("available", result["login"])
            staged = [data.decode("utf-8") for path, data in fixture.transport.files.items()
                      if path.endswith(".ps1") and "doctor-" in path]
            self.assertEqual(1, len(staged))
            self.assertIn("ProcessStartInfo", staged[0])
            self.assertIn("RedirectStandardError=$true", staged[0])
            self.assertIn("ReadToEndAsync", staged[0])
            self.assertIn("WaitForExit(15000)", staged[0])
            self.assertIn("$o.Length-gt4096", staged[0])
            self.assertNotIn("AssignProcessToJobObject", staged[0])
            self.assertNotIn("& $CliPath login status", staged[0])
            self.assertNotIn("function R(", staged[0])
            self.assertNotIn("function H(", staged[0])
            self.assertIn("Invoke-Rr2DoctorProcess", staged[0])

    def test_doctor_returns_typed_failure_without_native_output(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            fixture.transport.doctor_result = {
                "schemaVersion": 1, "byteLength": 123456, "sha256": "B" * 64,
                "version": "codex-cli 0.165.0", "versionExitCode": 0,
                "loginExitCode": 1, "loginAvailable": False,
                "errorCode": "cli-login-unavailable",
                "phase": "cli-login", "exceptionType": None,
                "fullyQualifiedErrorId": None, "scriptLine": None,
            }
            with self.assertRaisesRegex(lab_codex.LabCodexError,
                                        "doctor-cli-login-unavailable"):
                fixture.tool.doctor("lab1")

    def test_doctor_rejects_unsanitized_diagnostic_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            fixture.transport.doctor_result = {
                "schemaVersion": 1, "byteLength": 123456, "sha256": "B" * 64,
                "version": None, "versionExitCode": None, "loginExitCode": None,
                "loginAvailable": False, "errorCode": "cli-doctor-failed",
                "phase": "secret text from guest", "exceptionType": "raw message with spaces",
                "fullyQualifiedErrorId": None, "scriptLine": 12,
            }
            with self.assertRaisesRegex(lab_codex.LabCodexError, "doctor-result-invalid"):
                fixture.tool.doctor("lab1")

    def test_doctor_collector_is_valid_windows_powershell(self):
        encoded = base64.b64encode(lab_codex.DOCTOR_COLLECTOR.encode("utf-8")).decode("ascii")
        command = (
            "$s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded +
            "'));$t=$null;$e=$null;[Management.Automation.Language.Parser]::ParseInput(" +
            "$s,[ref]$t,[ref]$e)|Out-Null;if($e.Count){exit 1}"
        )
        result = subprocess.run(
            [lab_codex.POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_guest_powershell_helpers_do_not_collide_with_history_aliases(self):
        self.assertNotIn("function h(", lab_codex.PS_SHA256.casefold())
        self.assertIn("get-labcodexsha256", lab_codex.PS_SHA256.casefold())
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            source.write_bytes(b"alias precedence regression")
            expected = lab_codex._sha(source.read_bytes())
            command = (lab_codex.PS_SHA256 + "$k=(Get-Command h).CommandType.ToString();" +
                       "$d=Get-LabCodexSha256 '" + str(source) + "';$k+'|'+$d")
            completed = subprocess.run(
                [lab_codex.POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True,
            )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("Alias|" + expected, completed.stdout.strip())

    def test_batch_rejects_same_lab_and_runs_distinct_labs(self):
        class BatchTool(lab_codex.LabCodex):
            def __init__(self, run_root):
                self.run_root = run_root; self.seen = []; self.lock = threading.Lock()
            def run(self, lab, task, inputs, timeout_seconds=300, poll_seconds=1.0):
                with self.lock: self.seen.append(lab)
                return {"lab": lab, "status": "succeeded"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); tool = BatchTool(root / "runs"); plan = root / "plan.json"
            value = {"schemaVersion": 1, "jobs": [
                {"lab": "lab1", "task": "a", "inputs": [], "timeoutSeconds": 30},
                {"lab": "lab2", "task": "b", "inputs": [], "timeoutSeconds": 30}]}
            plan.write_text(json.dumps(value), encoding="utf-8")
            result = tool.batch(plan)
            self.assertEqual({"lab1", "lab2"}, set(tool.seen))
            self.assertEqual("succeeded", result["status"])
            self.assertEqual(["succeeded", "succeeded"], [item["status"] for item in result["jobs"]])
            self.assertTrue(Path(result["index"]).is_file())
            self.assertEqual(result, json.loads(Path(result["index"]).read_text()))
            value["jobs"][1]["lab"] = "lab1"; plan.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(lab_codex.LabCodexError, "batch-lab-duplicate"):
                tool.batch(plan)

    def test_global_config_parses_before_or_after_command(self):
        before = lab_codex._parser().parse_args(["--config", "one.json", "doctor", "--lab", "lab1"])
        after = lab_codex._parser().parse_args(["doctor", "--config", "two.json", "--lab", "lab1"])
        self.assertEqual(Path("one.json"), before.config)
        self.assertEqual(Path("two.json"), after.config)

    def test_config_rejects_duplicate_canonical_vmx_or_vnc_port(self):
        for field in ("vmx", "vncPort"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(Path(directory))
                value = json.loads(fixture.config.read_text())
                value["labs"]["lab2"][field] = value["labs"]["lab1"][field]
                if field == "vmx":
                    value["labs"]["lab2"][field] = value["labs"]["lab2"][field].upper()
                fixture.config.write_text(json.dumps(value))
                with self.assertRaisesRegex(
                    lab_codex.LabCodexError,
                    "duplicate-vmx" if field == "vmx" else "duplicate-vnc-port",
                ):
                    lab_codex.load_config(fixture.config)

    def test_run_and_batch_exit_nonzero_for_honest_terminal_failures(self):
        for command in ("run", "batch"):
            with self.subTest(command=command):
                self.assertEqual(0, lab_codex._result_exit_code(command, {"status": "succeeded"}))
                self.assertEqual(2, lab_codex._result_exit_code(
                    command, {"status": "completed-with-failures"}))
                self.assertEqual(2, lab_codex._result_exit_code(command, {"status": "timed-out"}))
        self.assertEqual(0, lab_codex._result_exit_code("collect", {"status": "failed"}))


if __name__ == "__main__":
    unittest.main()
