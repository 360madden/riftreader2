"""Offline tests for the reusable XYZ claim/upload service lifecycle."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_xyz_transfer_service as service
from scripts.vm_console_native import Blocked


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class FakeMutex:
    abandoned = False
    def __init__(self):
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        self.closed = True


class TransferServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=service.ARTIFACTS)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "host.json"
        self.config.write_text("{}\n", encoding="utf-8")
        self.queue = self.root / "queue.sqlite3"
        self.queue.write_bytes(b"queue fixture")
        self.stop_prior = self.root / "STOP-prior.request"
        self.stop_successor = self.root / "STOP-successor.request"
        self.maintenance_path = self.root / "coordinated-host-plan-v99.json"
        runtime = service.ROOT / "scripts/control_host.py"
        self.vm_identity = {"vmx": "c:\\vm\\lab.vmx", "port": 5905,
                            "logEpoch": "epoch", "listenerPid": 88, "pid": 88,
                            "image": "vmware-vmx.exe", "startTicks": 123}
        maintenance = {"schemaVersion": 1, "configPath": str(self.config),
            "configSha256": hashlib.sha256(self.config.read_bytes()).hexdigest(),
            "database": str(self.queue), "resource": "vm:test",
            "shutdownFile": str(self.stop_successor), "vmIdentity": self.vm_identity,
            "runtimeHashes": {"scripts/control_host.py":
                hashlib.sha256(runtime.read_bytes()).hexdigest()},
            "expectedWindowsSession": 2}
        write(self.maintenance_path, maintenance)
        self.prior_path = self.root / "prior-process.json"
        self.prior = {"schemaVersion": 1, "pid": 44,
            "processIdentity": {"pid": 44, "image": "pythonw.exe", "startTicks": 456},
            "windowsSessionId": 2, "inJob": False, "vmIdentity": self.vm_identity,
            "shutdownMarker": str(self.stop_prior)}
        write(self.prior_path, self.prior)
        self.exit_path = self.root / "prior-exited.json"
        write(self.exit_path, {"pid": 44, "utc": "2026-10-25T00:00:00Z"})
        self.plan_path = self.root / "transfer-plan.json"
        self.target = {"processId": 1224, "processStartUtcTicks": 639285359295548343,
                       "executableSha256": "A" * 64}
        self.plan = {"schemaVersion": 1, "contractVersion": "xyz-transfer-plan/1",
            "runId": "xyz-run-01", "target": self.target, "readerSha256": "B" * 64,
            "maintenancePlan": {"path": str(self.maintenance_path),
                                "sha256": digest(self.maintenance_path)},
            "priorProcess": {"path": str(self.prior_path), "sha256": digest(self.prior_path)},
            "priorExit": {"path": str(self.exit_path), "sha256": digest(self.exit_path)}}
        write(self.plan_path, self.plan)

    def paths(self):
        return service._paths(self.plan_path, self.plan["runId"])

    def complete_claim(self):
        paths = self.paths()
        plan_sha = digest(self.plan_path)
        write(paths["claim"], {"schemaVersion": 1,
            "evidenceKind": "guest-native-pointer-zip-claim/1", "source": "guest-declared-only",
            "guest": service.GUEST, "zipSha256": "C" * 64, "zipBytes": 123,
            "target": self.target, "bundleSha256": self.plan["readerSha256"]})
        process = {"schemaVersion": 1, "phase": "claim", "pid": 55,
                   "contractVersion": "xyz-transfer-process/1",
                   "processIdentity": {"pid": 55, "image": "pythonw.exe", "startTicks": 789},
                   "windowsSessionId": 2, "inJob": False, "bind": service.BIND,
                   "guest": service.GUEST, "port": service.PORT,
                   "vmIdentity": self.vm_identity,
                   "planSha256": plan_sha}
        write(paths["claimProcess"], process)
        write(paths["claimExit"], {"schemaVersion": 1,
              "contractVersion": "xyz-transfer-exit/1", "phase": "claim", "pid": 55,
              "planSha256": plan_sha, "state": "claim-received", "listenerClosed": True,
              "mutexReleased": True, "vmIdentity": self.vm_identity})
        return paths

    def test_claim_preview_is_static_and_explicit(self):
        with patch.object(service, "_live_gate") as live:
            result = service.preview(self.plan_path, "claim", 300)
        live.assert_not_called()
        self.assertEqual(result["state"], "verified-not-serving")
        self.assertTrue(result["liveNotChecked"])
        self.assertFalse(result["listenerStarted"])

    def test_preview_cli_never_serves(self):
        with patch.object(service, "serve") as serve:
            with redirect_stdout(io.StringIO()):
                code = service.main(["--plan", str(self.plan_path), "--phase", "claim"])
        self.assertEqual(code, 0)
        serve.assert_not_called()

    def test_boolean_schema_is_rejected(self):
        self.plan["schemaVersion"] = True
        write(self.plan_path, self.plan)
        with self.assertRaisesRegex(service.TransferBlocked, "unsupported"):
            service.preview(self.plan_path, "claim", 300)

    def test_reserved_and_trailing_hyphen_run_ids_are_rejected(self):
        for run_id in ("con", "bad-"):
            self.plan["runId"] = run_id
            write(self.plan_path, self.plan)
            with self.assertRaisesRegex(service.TransferBlocked, "runId"):
                service.preview(self.plan_path, "claim", 300)

    def test_changed_pinned_plan_is_rejected(self):
        maintenance = json.loads(self.maintenance_path.read_text())
        maintenance["resource"] = "changed"
        write(self.maintenance_path, maintenance)
        with self.assertRaisesRegex(service.TransferBlocked, "hash differs"):
            service.preview(self.plan_path, "claim", 300)

    def test_claim_refuses_any_prior_phase_output(self):
        self.paths()["claimProcess"].write_text("reserved")
        with self.assertRaisesRegex(service.TransferBlocked, "already exists"):
            service.preview(self.plan_path, "claim", 300)

    def test_upload_requires_matching_completed_claim(self):
        self.complete_claim()
        result = service.preview(self.plan_path, "upload", 600)
        self.assertEqual(result["phase"], "upload")
        claim = json.loads(self.paths()["claim"].read_text())
        claim["bundleSha256"] = "D" * 64
        write(self.paths()["claim"], claim)
        with self.assertRaisesRegex(service.TransferBlocked, "provenance"):
            service.preview(self.plan_path, "upload", 600)

    def test_duration_is_bounded(self):
        for value in (29, 601, True):
            with self.assertRaisesRegex(service.TransferBlocked, "lifetime"):
                service.preview(self.plan_path, "claim", value)

    def test_prior_process_access_failure_is_not_treated_as_exit(self):
        with patch.object(service, "_prior_process_identity",
                          side_effect=service.TransferBlocked("Win32 error 5")):
            with self.assertRaisesRegex(service.TransferBlocked, "Win32 error 5"):
                service._prior_epoch_exited(self.prior)

    def test_prior_process_absence_and_pid_reuse_prove_old_epoch_exit(self):
        with patch.object(service, "_prior_process_identity", return_value=None):
            service._prior_epoch_exited(self.prior)
        with patch.object(service, "_prior_process_identity",
                          return_value={"pid": 44, "startTicks": 999}):
            service._prior_epoch_exited(self.prior)

    def test_changed_image_path_does_not_prove_process_exit(self):
        same_epoch = dict(self.prior["processIdentity"], image="renamed-pythonw.exe")
        with patch.object(service, "_prior_process_identity", return_value=same_epoch):
            with self.assertRaisesRegex(service.TransferBlocked, "still alive"):
                service._prior_epoch_exited(self.prior)
    def test_claim_serve_uses_test_seams_without_network(self):
        mutex = FakeMutex()
        fake_result = {"target": self.target, "bundleSha256": self.plan["readerSha256"],
                       "zipSha256": "C" * 64, "zipBytes": 123,
                       "schemaVersion": 1,
                       "evidenceKind": "guest-native-pointer-zip-claim/1",
                       "source": "guest-declared-only", "guest": service.GUEST}
        current = {"pid": 777, "image": "pythonw.exe", "startTicks": 321}
        def publish_claim(*_args, **_kwargs):
            write(self.paths()["claim"], fake_result)
            return object()
        with patch.object(service, "_live_gate", return_value=(mutex, object())), \
             patch.object(service, "require_independent_windows_user", return_value=(2, False)), \
             patch.object(service, "process_identity", return_value=current), \
             patch.object(service, "claim_handler", side_effect=publish_claim), \
             patch.object(service, "_serve_once", return_value=fake_result), \
             patch.object(service, "collect_identity", return_value=self.vm_identity), \
             patch.object(service, "_listener_rows", return_value=[]):
            code, result = service.serve(self.plan_path, "claim", 30)
        self.assertEqual(code, 0)
        self.assertEqual(result["state"], "claim-received")
        self.assertTrue(mutex.closed)
        self.assertTrue(self.paths()["claimExit"].is_file())

    def test_claim_expiry_records_closed_listener(self):
        mutex = FakeMutex()
        current = {"pid": 777, "image": "pythonw.exe", "startTicks": 321}
        with patch.object(service, "_live_gate", return_value=(mutex, object())), \
             patch.object(service, "require_independent_windows_user", return_value=(2, False)), \
             patch.object(service, "process_identity", return_value=current), \
             patch.object(service, "claim_handler", return_value=object()), \
             patch.object(service, "_serve_once", return_value=None), \
             patch.object(service, "collect_identity", return_value=self.vm_identity), \
             patch.object(service, "_listener_rows", return_value=[]):
            code, result = service.serve(self.plan_path, "claim", 30)
        self.assertEqual(code, 3)
        self.assertEqual(result["state"], "expired-no-claim")
        exit_receipt = json.loads(self.paths()["claimExit"].read_text())
        self.assertTrue(exit_receipt["listenerClosed"])
        self.assertTrue(exit_receipt["mutexReleased"])

    def test_post_listener_vm_failure_cannot_record_claim_success(self):
        mutex = FakeMutex()
        fake_result = {"schemaVersion": 1,
            "evidenceKind": "guest-native-pointer-zip-claim/1",
            "source": "guest-declared-only", "guest": service.GUEST,
            "target": self.target, "bundleSha256": self.plan["readerSha256"],
            "zipSha256": "C" * 64, "zipBytes": 123}
        current = {"pid": 777, "image": "pythonw.exe", "startTicks": 321}
        def publish_claim(*_args, **_kwargs):
            write(self.paths()["claim"], fake_result)
            return object()
        with patch.object(service, "_live_gate", return_value=(mutex, object())), \
             patch.object(service, "require_independent_windows_user", return_value=(2, False)), \
             patch.object(service, "process_identity", return_value=current), \
             patch.object(service, "claim_handler", side_effect=publish_claim), \
             patch.object(service, "_serve_once", return_value=fake_result), \
             patch.object(service, "collect_identity", return_value={"changed": True}), \
             patch.object(service, "_listener_rows", return_value=[]):
            with self.assertRaisesRegex(service.TransferBlocked, "VM identity changed"):
                service.serve(self.plan_path, "claim", 30)
        outcome = json.loads(self.paths()["claimExit"].read_text())
        self.assertEqual(outcome["state"], "blocked")
        with self.assertRaisesRegex(service.TransferBlocked, "provenance"):
            service.preview(self.plan_path, "upload", 30)

    def test_raced_process_receipt_is_preserved_without_exit(self):
        paths = self.paths()
        def race(_context):
            paths["claimProcess"].write_text("competitor")
            return FakeMutex(), object()
        with patch.object(service, "_live_gate", side_effect=race), \
             patch.object(service, "require_independent_windows_user", return_value=(2, False)), \
             patch.object(service, "process_identity", return_value={
                 "pid": 777, "image": "pythonw.exe", "startTicks": 321}):
            with self.assertRaises(FileExistsError):
                service.serve(self.plan_path, "claim", 30)
        self.assertEqual(paths["claimProcess"].read_text(), "competitor")
        self.assertFalse(paths["claimExit"].exists())

    def test_upload_must_match_declared_length(self):
        self.complete_claim()
        mutex = FakeMutex()
        current = {"pid": 777, "image": "pythonw.exe", "startTicks": 321}
        with patch.object(service, "_live_gate", return_value=(mutex, object())), \
             patch.object(service, "require_independent_windows_user", return_value=(2, False)), \
             patch.object(service, "process_identity", return_value=current), \
             patch.object(service, "upload_handler", return_value=object()), \
             patch.object(service, "_serve_once", return_value={"bytes": 122, "sha256": "c" * 64}), \
             patch.object(service, "_listener_rows", return_value=[]):
            with self.assertRaisesRegex(service.TransferBlocked, "length differs"):
                service.serve(self.plan_path, "upload", 30)
        exit_receipt = json.loads(self.paths()["uploadExit"].read_text())
        self.assertEqual(exit_receipt["state"], "blocked")

    def test_abandoned_controller_mutex_blocks_live_gate(self):
        self.stop_prior.write_text("stop")
        context = service.load_plan(self.plan_path, "claim")
        config = SimpleNamespace(vmx=Path("C:/vm/lab.vmx"),
            vmrun=Path("C:/vm/vmrun.exe"), vnc_port=5905,
            output_directory=self.root)
        native = SimpleNamespace(vmx=config.vmx)
        mutex = FakeMutex()
        mutex.abandoned = True
        with patch.object(service, "require_independent_windows_user"), \
             patch.object(service, "_prior_epoch_exited"), \
             patch.object(service, "authority_snapshot", return_value=(1, None, None)), \
             patch.object(service, "_listener_rows", return_value=[]), \
             patch.object(service.HostConfig, "load", return_value=config), \
             patch.object(service, "validate_config", return_value=native), \
             patch.object(service, "ControlMutex", return_value=mutex):
            with self.assertRaisesRegex(service.TransferBlocked, "abandoned"):
                service._live_gate(context)
        self.assertTrue(mutex.closed)

    def test_absolute_deadline_closes_partial_header_connection(self):
        destination = self.root / "slow-claim.json"
        handler = service.claim_handler(destination, "127.0.0.1", pid=1, ticks=2,
            game_sha="A" * 64, bundle_sha="B" * 64, kind="pointer")
        client_done = threading.Event()
        def ready(address):
            def trickle():
                try:
                    with socket.create_connection(address, timeout=1) as client:
                        client.sendall(b"POST /slow HTTP/1.1\r\nX-Slow: ")
                        while True:
                            time.sleep(.03)
                            client.sendall(b"x")
                except OSError:
                    pass
                finally:
                    client_done.set()
            threading.Thread(target=trickle, daemon=True).start()
        started = time.monotonic()
        with patch.object(service, "BIND", "127.0.0.1"), patch.object(service, "PORT", 0):
            result = service._serve_once(handler, .25, upload=False, ready=ready)
        self.assertIsNone(result)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertTrue(client_done.wait(1))

    def test_deadline_expired_before_accept_never_runs_handler(self):
        class CountingHandler:
            calls = 0
            def __init__(self, *_args):
                CountingHandler.calls += 1
        with service._DeadlineServer(("127.0.0.1", 0), CountingHandler,
                                     time.monotonic() + 5) as server:
            server.timeout = .2
            server.expire()
            with socket.create_connection(server.server_address, timeout=1) as client:
                client.sendall(b"GET / HTTP/1.0\r\n\r\n")
                server.handle_request()
        self.assertEqual(CountingHandler.calls, 0)

    def test_loopback_claim_handler_roundtrip(self):
        destination = self.root / "loopback-claim.json"
        handler = service.claim_handler(destination, "127.0.0.1", pid=1, ticks=2,
            game_sha="A" * 64, bundle_sha="B" * 64, kind="pointer")
        request_done = threading.Event()
        status = []
        wire = ("RR2PTRZIP1|" + "C" * 64 + "|123|1|2|" +
                "A" * 64 + "|" + "B" * 64).encode("ascii")
        def ready(address):
            def send():
                try:
                    connection = HTTPConnection(address[0], address[1], timeout=2)
                    connection.request("POST", "/rr2-native-pointer-zip-claim-oct24-01",
                                       body=wire, headers={"Content-Type": "text/plain"})
                    response = connection.getresponse()
                    status.append(response.status)
                    response.read()
                    connection.close()
                finally:
                    request_done.set()
            threading.Thread(target=send, daemon=True).start()
        with patch.object(service, "BIND", "127.0.0.1"), patch.object(service, "PORT", 0):
            result = service._serve_once(handler, 2, upload=False, ready=ready)
        self.assertTrue(request_done.wait(1))
        self.assertEqual(status, [201])
        self.assertEqual(result["zipBytes"], 123)
        self.assertEqual(json.loads(destination.read_text())["zipSha256"], "C" * 64)

    def test_plan_drift_after_listener_blocks_success(self):
        mutex = FakeMutex()
        original_paths = self.paths()
        fake_result = {"schemaVersion": 1,
            "evidenceKind": "guest-native-pointer-zip-claim/1",
            "source": "guest-declared-only", "guest": service.GUEST,
            "target": self.target, "bundleSha256": self.plan["readerSha256"],
            "zipSha256": "C" * 64, "zipBytes": 123}
        current = {"pid": 777, "image": "pythonw.exe", "startTicks": 321}
        def publish_claim(*_args, **_kwargs):
            write(self.paths()["claim"], fake_result)
            return object()
        def drift(*_args, **_kwargs):
            self.plan["runId"] = "changed-run"
            write(self.plan_path, self.plan)
            return fake_result
        with patch.object(service, "_live_gate", return_value=(mutex, object())), \
             patch.object(service, "require_independent_windows_user", return_value=(2, False)), \
             patch.object(service, "process_identity", return_value=current), \
             patch.object(service, "claim_handler", side_effect=publish_claim), \
             patch.object(service, "_serve_once", side_effect=drift), \
             patch.object(service, "_listener_rows", return_value=[]):
            with self.assertRaisesRegex(service.TransferBlocked, "plan changed"):
                service.serve(self.plan_path, "claim", 30)
        outcome = json.loads(original_paths["claimExit"].read_text())
        self.assertEqual(outcome["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
