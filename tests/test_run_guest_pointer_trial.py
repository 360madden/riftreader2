"""Fail-closed offline tests for the V15 -> V16 guest pointer trial and services."""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_guest_pointer_trial as trial
from scripts import run_guest_pointer_service as service
from scripts.prepare_direct_shell_pointer import prepare, publish
from scripts.vm_console_native import Blocked


class V16GuestPointerSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.vm = {"vmx": "test-vmx", "port": 5905, "epoch": 20261024}
        self.plan = {"vmIdentity": self.vm, "configSha256": trial.CONFIG_SHA,
                     "expectedWindowsSession": 2, "database": str(self.root / "queue"),
                     "resource": "vm:rift-lab-1"}
        self.claim = self.root / "claim.json"
        self.archive = self.root / "pointer.zip"
        self.upload = self.root / "upload.json"

    def service_paths(self):
        return (
            patch.object(trial, "HOME", self.root),
            patch.object(service, "HOME", self.root),
            patch.object(service, "CLAIM_RECEIPT", self.claim),
            patch.object(service, "UPLOAD_ARCHIVE", self.archive),
            patch.object(service, "UPLOAD_RECEIPT", self.upload),
        )

    def fake_plan_command(self, suffix):
        final = (
            f'& "{trial.BINARY}" follow-pointer --request '
            f'"$env:TEMP\\rr2-v16ptr-{suffix}.json" '
            f'--output "$env:TEMP\\rr2-v16ptr-{suffix}-report.json"')
        return ["Write-Output 'safe-test'"] * 9 + [final]

    def action_receipt(self, n, entries):
        return {
            "schemaVersion": 1,
            "purpose": "v16-exact-native-pointer-guest-action",
            "status": "console-action-completed", "step": n,
            "stage": "bootstrap" if n == 0 else entries[n - 1][0],
            "commandSha256": (None if n == 0 else trial.sha(entries[n - 1][1].encode("ascii"))),
            "requestSha256": trial.REQUEST_SHA, "vmIdentity": self.vm,
            "mutexExclusive": True, "consoleActionCompleted": True,
            "guestCommandCompletionVerified": False,
        }

    def test_steps_are_bounded_and_native_reads_are_exe_request_gated(self):
        with patch.object(trial, "checked_request",
                          side_effect=[self.fake_plan_command("a"),
                                       self.fake_plan_command("b")]):
            commands = trial.commands()
        self.assertEqual(len(commands), 33)
        self.assertEqual(commands[12][0], "pointer-a")
        self.assertIn("follow-pointer", commands[12][1])
        self.assertIn("$exeok -and", commands[12][1])
        self.assertIn(trial.REQUEST_SHA, commands[12][1])
        self.assertIn("$aok -and", commands[23][1])
        self.assertEqual(commands[30][0], "claim")
        self.assertIn("RR2PTRZIP1", commands[28][1])
        self.assertEqual(commands[32][0], "upload")
        self.assertLessEqual(max(len(x[1]) for x in commands), 490)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell parser required")
    def test_host_powershell_ast_parses_commands_but_does_not_execute(self):
        with patch.object(trial, "checked_request",
                          side_effect=[self.fake_plan_command("a"),
                                       self.fake_plan_command("b")]):
            commands = trial.commands()
        self.assertEqual(trial.parse_powershell(commands)["parsedCommands"], 33)
        with self.assertRaisesRegex(Blocked, "PowerShell-syntax-invalid"):
            trial.parse_powershell([("invalid", "if ($false) {")])

    def test_every_transported_step_is_regenerated_and_tamper_rejected(self):
        target = {"processId": trial.PID, "processStartUtcTicks": trial.TICKS,
                  "executableSha256": trial.GAME_SHA}
        request, steps = prepare(target, "v16ptr-a", trial.BINARY)
        publish(self.root, request, steps)
        self.assertEqual(trial.checked_request(self.root, "a"), steps)
        intermediate = self.root / "step-03.json"
        altered = json.loads(intermediate.read_bytes())
        altered["text"] = "Write-Output 'unexpected-step'"
        intermediate.write_text(json.dumps(altered))
        with self.assertRaisesRegex(Blocked, "pointer-transport-step-source-drift"):
            trial.checked_request(self.root, "a")

    def test_source_manifest_or_binary_change_fails_before_guest_input(self):
        with patch.object(trial, "A", self.root / "missing"):
            with self.assertRaises(OSError):
                trial.checked_request(trial.A, "a")
        with patch.object(trial, "MANIFEST_SHA", "F" * 64):
            # The original real plan is optional to tests; when unavailable it still fails.
            with self.assertRaises((Blocked, OSError)):
                trial.checked_request(trial.A, "a")

    def test_requires_v15_normal_stop_and_quarantine_before_any_console(self):
        with patch.object(trial, "HOME", self.root):
            with self.assertRaisesRegex(Blocked, "normal-stop-or-exit"):
                trial.maintenance()
            (self.root / "STOP-NATIVE-20261024-V15.request").write_text("")
            (self.root / "coordinated-host-v15-exited.json").write_text('{"pid":27856}')
            (self.root / "coordinated-host-v15-process.json").write_text(
                json.dumps({"pid": 27856, "vmIdentity": self.vm}))
            p = self.root / "v16.json"
            p.write_text(json.dumps(self.plan))
            with patch.object(trial, "PLAN", p):
                for snapshot in ((0, None, "cleanup"), (1, "busy", None)):
                    with self.subTest(snapshot=snapshot), patch.object(
                            trial, "authority_snapshot", return_value=snapshot):
                        with self.assertRaisesRegex(Blocked, "not-quarantined"):
                            trial.maintenance()
                with patch.object(trial, "authority_snapshot",
                                  return_value=(1, None, None)):
                    self.assertEqual(trial.maintenance(), self.plan)
                    (self.root / "coordinated-host-v16-process.json").write_text("{}")
                    with self.assertRaisesRegex(Blocked, "v16-already-started"):
                        trial.maintenance()

    def test_prev_step_receipts_must_be_action_not_guest_completion_claim(self):
        entries = [("test", "Write-Output 1")] * 33
        with patch.object(trial, "HOME", self.root):
            with self.assertRaisesRegex(Blocked, "not-receipted"):
                trial.require_previous_step(1, entries, self.vm)
            old = self.root / (trial.PREFIX + "00")
            old.mkdir()
            receipt = old / "receipt.json"
            receipt.write_text('{"status":"completed"}')
            with self.assertRaisesRegex(Blocked, "not-receipted"):
                trial.require_previous_step(1, entries, self.vm)
            record = self.action_receipt(0, entries)
            receipt.write_text(json.dumps(record))
            trial.require_previous_step(1, entries, self.vm)
            record["vmIdentity"] = {"epoch": -1}
            receipt.write_text(json.dumps(record))
            with self.assertRaisesRegex(Blocked, "not-receipted"):
                trial.require_previous_step(1, entries, self.vm)

    def test_service_phase_boundaries_fail_on_missing_or_future_action(self):
        a, b, c, d, e = self.service_paths()
        entries = [("claim", "Write-Output 1")] * 33
        with a, b, c, d, e, patch.object(trial, "commands", return_value=entries):
            with self.assertRaisesRegex(Blocked, "step-boundary"):
                service.phase_steps("claim", self.plan)
            done = self.root / (trial.PREFIX + "30")
            done.mkdir()
            receipt = done / "receipt.json"
            receipt.write_text(json.dumps(self.action_receipt(30, entries)))
            service.phase_steps("claim", self.plan)
            forged = self.action_receipt(30, entries)
            forged["commandSha256"] = "0" * 64
            receipt.write_text(json.dumps(forged))
            with self.assertRaisesRegex(Blocked, "not-receipted"):
                service.phase_steps("claim", self.plan)
            receipt.write_text(json.dumps(self.action_receipt(30, entries)))
            future = self.root / (trial.PREFIX + "31")
            future.mkdir()
            (future / "receipt.json").write_text('{"status":"console-action-completed"}')
            with self.assertRaisesRegex(Blocked, "step-boundary"):
                service.phase_steps("claim", self.plan)

    def owner(self, phase, *, exited=True):
        info = {
            "schemaVersion": 1, "purpose": "one-use-v16-native-pointer-" + phase,
            "pid": 32001 if phase == "claim" else 32002,
            "phase": phase, "sourceSha256": service.SERVER_FILES[phase][1],
            "processIdentity": {"pid": 32001 if phase == "claim" else 32002,
                                "image": "test-pythonw.exe", "startTicks": 12345},
            "requestSha256": trial.REQUEST_SHA, "vmIdentity": self.vm,
            "windowsSessionId": 2, "inJob": False,
            "bind": "192.168.56.1", "allowedGuest": "192.168.56.128", "port": 8765,
        }
        p = service.paths_for(phase)
        p["process"].write_text(json.dumps(info))
        if exited:
            p["exit"].write_text(json.dumps({"pid": info["pid"], "phase": phase}))
        return info

    def real_claim(self, data=b"fixture-zip"):
        digest = hashlib.sha256(data).hexdigest().upper()
        self.claim.write_text(json.dumps({
            "schemaVersion": 1, "evidenceKind": "guest-native-pointer-zip-claim/1",
            "source": "guest-declared-only", "guest": "192.168.56.128",
            "zipSha256": digest, "zipBytes": len(data),
            "bundleSha256": trial.BUNDLE_SHA,
            "target": {"processId": trial.PID, "processStartUtcTicks": trial.TICKS,
                       "executableSha256": trial.GAME_SHA},
        }))
        return digest

    def test_claim_must_match_same_vm_service_process_exit_and_guest_epoch(self):
        a, b, c, d, e = self.service_paths()
        with a, b, c, d, e:
            self.real_claim()
            with self.assertRaisesRegex(Blocked, "never-started"):
                service.claim_digest(self.plan)
            self.owner("claim")
            self.assertEqual(service.claim_digest(self.plan)[1], len(b"fixture-zip"))
            claim = json.loads(self.claim.read_text())
            claim["target"]["processStartUtcTicks"] -= 100
            self.claim.write_text(json.dumps(claim))
            with self.assertRaisesRegex(Blocked, "provenance-differs"):
                service.claim_digest(self.plan)

    def test_claim_service_cannot_act_after_exit_or_from_different_vm(self):
        a, b, c, d, e = self.service_paths()
        with a, b, c, d, e:
            info = self.owner("claim", exited=False)
            with patch.object(service, "process_identity", return_value=info["processIdentity"]), patch.object(
                    service, "_listener_rows", return_value=[("192.168.56.1", info["pid"])]):
                service.service_started("claim", self.plan)
                with self.assertRaisesRegex(Blocked, "provenance-invalid"):
                    service.service_started("claim", {"vmIdentity": {"epoch": -1}})
                with patch.object(service, "_listener_rows", return_value=[]):
                    with self.assertRaisesRegex(Blocked, "pid-or-listener-not-ready"):
                        service.service_started("claim", self.plan)
                with patch.object(service, "process_identity", return_value={"startTicks": -1}):
                    with self.assertRaisesRegex(Blocked, "pid-or-listener-not-ready"):
                        service.service_started("claim", self.plan)
                service.paths_for("claim")["exit"].write_text('{"pid":32001,"phase":"claim"}')
                with self.assertRaisesRegex(Blocked, "exited-before"):
                    service.service_started("claim", self.plan)

    def test_upload_requires_matching_claim_content_and_real_received_zip(self):
        a, b, c, d, e = self.service_paths()
        with a, b, c, d, e:
            data = b"finite synthetic ZIP claim not raw gameplay memory"
            digest = self.real_claim(data)
            self.owner("claim")
            self.archive.write_bytes(data)
            self.upload.write_text(json.dumps({
                "schemaVersion": 1,
                "purpose": "content-addressed-guest-pointer-transfer",
                "state": "received",
                "destination": str(self.archive),
                "guest": "192.168.56.128",
                "sha256": digest, "bytes": len(data),
            }))
            self.owner("upload")
            service.upload_received(self.plan)
            self.archive.write_bytes(data + b"tampered")
            with self.assertRaisesRegex(Blocked, "length-differs"):
                service.upload_received(self.plan)

    def test_guest_post_upload_stage_fails_before_vnc_on_missing_receiver(self):
        with patch.object(trial, "HOME", self.root), patch.object(
                trial, "commands", return_value=[("upload", "Write-Output 1")] * 33), patch.object(
                trial, "maintenance", return_value=self.plan), patch.object(
                trial, "require_previous_step"), patch.object(
                trial, "require_claim_received"):
            with self.assertRaisesRegex(Blocked, "never-started"):
                trial.execute(33)
        self.assertFalse((self.root / (trial.PREFIX + "33")).exists())

    def test_abort_refuses_live_service_and_live_listener_before_vm_input(self):
        a, b, c, d, e = self.service_paths()
        with a, b, c, d, e, patch.object(
                trial, "commands", return_value=[("safe", "Write-Output 1")] * 33), patch.object(
                trial, "maintenance", return_value=self.plan), patch.object(
                service, "_listener_rows", return_value=[]):
            with self.assertRaisesRegex(Blocked, "bootstrap-not-attempted"):
                trial.execute(None, abort=True)
            (self.root / (trial.PREFIX + "00")).mkdir()
            paths = service.paths_for("claim")
            paths["process"].write_text('{"pid":32001}')
            with self.assertRaisesRegex(Blocked, "service-not-finished"):
                trial.execute(None, abort=True)
            paths["exit"].write_text('{"pid":32001}')
            with patch.object(service, "_listener_rows",
                              return_value=[("192.168.56.1", 32001)]):
                with self.assertRaisesRegex(Blocked, "listener-still-present"):
                    trial.execute(None, abort=True)
            self.assertFalse((self.root / "rr2-v16-pointer-guest-abort-01").exists())

    def test_abort_closes_verified_shell_and_records_no_upload_claim(self):
        class FakeConsole:
            def keyPress(self, name):
                if name != "enter":
                    raise AssertionError("unexpected guest input")
            def disconnect(self):
                pass

        entries = [("safe", "Write-Output 1")] * 33
        a, b, c, d, e = self.service_paths()
        with a, b, c, d, e, patch.object(
                trial, "commands", return_value=entries), patch.object(
                trial, "maintenance", return_value=self.plan), patch.object(
                trial, "validate_config", return_value=SimpleNamespace(vmx="test-vmx")), patch.object(
                trial, "ControlMutex", return_value=nullcontext()), patch.object(
                trial, "collect_identity", return_value=self.vm), patch.object(
                trial, "connect", return_value=FakeConsole()), patch.object(
                trial, "_capture", side_effect=lambda _client, path: path.write_bytes(b"fixture")), patch.object(
                trial, "shell_foreground", return_value=True), patch.object(
                trial, "_type_text") as sent, patch.object(
                trial.time, "sleep"), patch.object(
                service, "_listener_rows", return_value=[]):
            (self.root / (trial.PREFIX + "00")).mkdir()
            result = trial.execute(None, abort=True)
            self.assertEqual(result["status"], "guest-shell-aborted")
            sent.assert_called_once_with(unittest.mock.ANY, "exit")
            receipt = json.loads((self.root / "rr2-v16-pointer-guest-abort-01" /
                                  "receipt.json").read_bytes())
            self.assertTrue(receipt["trialAbortedWithoutUploadProof"])
            with self.assertRaisesRegex(Blocked, "already-aborted"):
                trial.execute(1)

    def test_close_guest_shell_requires_upload_bytes_not_just_claim(self):
        with patch.object(trial, "HOME", self.root), patch.object(
                trial, "commands", return_value=[("upload", "Write-Output 1")] * 33), patch.object(
                trial, "maintenance", return_value=self.plan), patch.object(
                trial, "require_upload_received", side_effect=Blocked("upload-incomplete")):
            with self.assertRaisesRegex(Blocked, "upload-incomplete"):
                trial.execute(None, close=True)
        self.assertFalse((self.root / "rr2-v16-pointer-guest-close-01").exists())


if __name__ == "__main__":
    unittest.main()
