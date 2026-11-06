"""Disposable read-only recovery acceptance tests; no real VM or guest calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.nav_access_queue import AccessQueue
from scripts.verify_guest_recovery import (
    RecoveryCheckError, REQUIRED_TARGET, compare_observations,
    normalized_observation, queue_snapshot, save_once, main,
)


def sample_observation():
    target = {
        "machineName": "RIFT-LAB-1", "executablePath": "C:\\RIFT\\rift_x64.exe",
        "executableSha256": "A" * 64, "processId": 234,
        "processStartUtcTicks": 10000, "windowHandle": "0xA12",
        "clientWidth": 1200, "clientHeight": 680, "clientX": 0, "clientY": 22,
    }
    return {
        "schemaVersion": 1, "kind": "rr2-guest-recovery-observation",
        "observedUtc": "2026-10-22T00:00:00+00:00",
        "configSha256": "b" * 64, "authorityPath": "C:\\temp\\authority.sqlite3",
        "vmIdentity": {"vmx": "c:\\vms\\lab.vmx", "pid": 5, "startTicks": 1},
        "host": {"hostInstance": "host-a", "connection": 1},
        "guest": {"instanceId": "rx-1", "target": target, "foreground": False},
        "queue": {"resource": "vm:lab", "epoch": "nav-epoch-a", "generation": 4,
                  "cleanupReceiptHash": "c" * 64, "requestHistoryCount": 2,
                  "lastEventSequence": 5, "blocked": False, "holder": None, "pending": 0},
        "nativeReady": True, "noGameplayInputSent": True,
        "guestWindowsBootVerified": False, "unattendedShortcutLaunchVerified": False,
    }


def recovered(before, *, restart_game=False):
    after = deepcopy(before)
    after["host"]["connection"] += 1
    after["guest"]["instanceId"] = "rx-2"
    after["queue"].update(epoch="nav-epoch-b", generation=6,
                          cleanupReceiptHash="d" * 64, lastEventSequence=12)
    if restart_game:
        after["guest"]["target"]["processId"] = 987
        after["guest"]["target"]["processStartUtcTicks"] = 20000
        after["guest"]["target"]["windowHandle"] = "0xB33"
    return after


class RecoveryComparisonTests(unittest.TestCase):
    def test_receiver_only_replacement_passes_with_same_game(self):
        baseline = sample_observation()
        result = compare_observations(baseline, recovered(baseline), "receiver")
        self.assertTrue(result["passed"])
        self.assertFalse(result["windowsBootIndependentlyVerified"])
        self.assertFalse(result["shortcutAutoLaunchIndependentlyVerified"])
        self.assertFalse(result["guestGameProcessChanged"])

    def test_guest_game_restart_passes_but_not_as_reboot_proof(self):
        baseline = sample_observation()
        result = compare_observations(baseline, recovered(baseline, restart_game=True), "guest-restart")
        self.assertTrue(result["guestGameProcessChanged"])
        self.assertFalse(result["windowsBootIndependentlyVerified"])

    def reject(self, baseline, after, mode, code):
        with self.assertRaisesRegex(RecoveryCheckError, "^" + code + "$"):
            compare_observations(baseline, after, mode)

    def test_no_change_or_plain_transport_reconnect_cannot_pass(self):
        base = sample_observation()
        after = recovered(base)
        after["guest"]["instanceId"] = base["guest"]["instanceId"]
        self.reject(base, after, "receiver", "receiver-not-restarted")
        after = recovered(base)
        after["host"]["connection"] = base["host"]["connection"]
        self.reject(base, after, "receiver", "native-connection-not-advanced")

    def test_expected_receiver_only_test_refuses_game_change(self):
        base = sample_observation()
        self.reject(base, recovered(base, restart_game=True), "receiver",
                    "game-restarted-in-receiver-only-test")

    def test_new_receiver_but_unchanged_game_cannot_pass_restart_mode(self):
        base = sample_observation()
        self.reject(base, recovered(base), "guest-restart",
                    "guest-game-process-not-restarted")

    def test_vm_host_and_config_change_fail_closed(self):
        base = sample_observation()
        for section, field, changed, code in (
            ("host", "hostInstance", "host-b", "native-host-restarted"),
            ("", "configSha256", "e"*64, "configSha256-changed"),
            ("", "vmIdentity", {"vmx": "new"}, "vmIdentity-changed"),
            ("", "authorityPath", "other.sqlite3", "authorityPath-changed"),
        ):
            with self.subTest(field=field):
                after = recovered(base)
                (after[section] if section else after)[field] = changed
                self.reject(base, after, "receiver", code)

    def test_authority_not_reconciled_or_history_lost(self):
        base = sample_observation()
        for field, wrong in (
            ("epoch", "nav-epoch-a"), ("generation", 4),
            ("cleanupReceiptHash", "c"*64), ("lastEventSequence", 5),
            ("requestHistoryCount", 1), ("pending", 1), ("blocked", True),
            ("holder", "stale"),
        ):
            with self.subTest(field=field):
                after = recovered(base)
                after["queue"][field] = wrong
                self.reject(base, after, "receiver", "authority-did-not-reconcile")

    def test_game_hash_change_refused(self):
        base = sample_observation()
        after = recovered(base, restart_game=True)
        after["guest"]["target"]["executableSha256"] = "f"*64
        self.reject(base, after, "guest-restart", "game-build-or-machine-changed")

    def test_wrong_mode_and_schema_refused(self):
        base = sample_observation()
        self.reject(base, recovered(base), "unattended", "invalid-verification-mode")
        other = recovered(base)
        other["schemaVersion"] = 3
        self.reject(base, other, "receiver", "observation-schema-invalid")


class RecoveryStatusTests(unittest.TestCase):
    def setUp(self):
        self.baseline = sample_observation()
        self.vm = self.baseline["vmIdentity"]
        self.queue = self.baseline["queue"]
        self.game = deepcopy(self.baseline["guest"]["target"])
        self.game["isForeground"] = False
        self.status = {
            "guest": {"instanceId": "rx-1",
                      "target": self.game, "armed": False, "busy": False,
                      "recoveryRequired": False, "desktopInputsDown": [],
                      "token": "NEVER-SERIALIZE"},
            "host": {"connected": True, "instanceId": "rx-1", "machineName": "RIFT-LAB-1",
                     "vmIdentity": self.vm, "token": "NEVER-SERIALIZE",
                     "consoleReservation": {"held": True, "required": True,
                                            "closing": False, "faulted": False},
                     "coordination": {"state": "ready", "hostInstance": "host-a",
                                      "connection": 1, "resource": "vm:lab",
                                      "shutdownRequested": False, "safeToClose": False,
                                      "supervisor": {"state": "running", "threadAlive": True,
                                                     "initialCleanupVerified": True,
                                                     "epoch": "nav-epoch-a",
                                                     "resource": "vm:lab"}}},
        }

    def normalized(self):
        return normalized_observation(self.status, self.vm, self.queue,
                                      config_sha="b"*64,
                                      authority_path="C:\\temp\\authority.sqlite3")

    def test_valid_status_does_not_advertise_foreground_or_boot_confirmation(self):
        record = self.normalized()
        self.assertFalse(record["guest"]["foreground"])
        self.assertFalse(record["guestWindowsBootVerified"])
        self.assertFalse(record["unattendedShortcutLaunchVerified"])
        self.assertEqual(set(record["guest"]["target"]), set(REQUIRED_TARGET))
        self.assertNotIn("NEVER-SERIALIZE", json.dumps(record))

    def test_guest_not_disarmed_or_input_held_fail(self):
        for field, wrong in (
            ("armed", True), ("busy", True),
            ("recoveryRequired", True), ("desktopInputsDown", ["w"])
        ):
            with self.subTest(field=field):
                fresh = deepcopy(self.status)
                fresh["guest"][field] = wrong
                with self.assertRaisesRegex(RecoveryCheckError, "guest-input-not-released"):
                    normalized_observation(fresh, self.vm, self.queue,
                                           config_sha="b"*64, authority_path="fixture")

    def test_supervisor_or_console_not_ready_fail(self):
        for section, field, wrong, reason in (
            ("coordination", "state", "blocked", "supervisor-not-ready"),
            ("supervisor", "threadAlive", False, "supervisor-not-verified"),
            ("consoleReservation", "held", False, "console-not-excluded"),
            ("consoleReservation", "faulted", True, "console-not-excluded"),
        ):
            with self.subTest(field=field):
                fresh = deepcopy(self.status)
                target = fresh["host"].get(section)
                if section == "supervisor":
                    target = fresh["host"]["coordination"]["supervisor"]
                target[field] = wrong
                with self.assertRaisesRegex(RecoveryCheckError, reason):
                    normalized_observation(fresh, self.vm, self.queue,
                                           config_sha="b"*64, authority_path="fixture")

    def test_epoch_or_vm_identity_mismatch_fail(self):
        bad = deepcopy(self.status)
        bad["host"]["coordination"]["supervisor"]["epoch"] = "wrong"
        with self.assertRaisesRegex(RecoveryCheckError, "supervisor-queue-epoch-mismatch"):
            normalized_observation(bad, self.vm, self.queue,
                                   config_sha="b"*64, authority_path="fixture")
        bad = deepcopy(self.status)
        bad["host"]["vmIdentity"] = {"pid": 7}
        with self.assertRaisesRegex(RecoveryCheckError, "native-vm-not-matched"):
            normalized_observation(bad, self.vm, self.queue,
                                   config_sha="b"*64, authority_path="fixture")


class QueueReadOnlyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "authority.sqlite3"
        self.q = AccessQueue(self.path, create=True)
        self.q.register("vm:lab", "nav-epoch-a")
        row = self.q.status()["resources"][0]
        evidence_ms = self.q.status()["as_of_ms"]
        self.q.cleanup("vm:lab", "nav-epoch-a", row["generation"],
                       evidence_ms, "verified-cleanup-receipt",
                       stopped=True, released=True, in_flight=False)

    def test_read_only_queue_snapshot_does_not_write_history(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        snapshot = queue_snapshot(self.path, "vm:lab")
        after = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(snapshot["pending"], 0)
        self.assertGreaterEqual(snapshot["generation"], 0)
        self.assertNotIn("verified-cleanup-receipt", json.dumps(snapshot))

    def test_queued_work_refused_without_queue_cleanup(self):
        self.q.submit("queued-task", "worker", "A", {"vm:lab":"nav-epoch-a"})
        before = self.q.status()["requests"][0]["state"]
        with self.assertRaisesRegex(RecoveryCheckError, "pending-ownership-requests"):
            queue_snapshot(self.path, "vm:lab")
        after = self.q.status()["requests"][0]["state"]
        self.assertEqual(before, after)

    def test_invalid_missing_corrupt_db_fail_closed(self):
        with self.assertRaisesRegex(RecoveryCheckError, "authority-path-invalid"):
            queue_snapshot(self.path.parent/"missing.sqlite3", "vm:lab")
        other = self.path.parent/"corrupt.sqlite3"
        other.write_text("fake", encoding="utf-8")
        with self.assertRaisesRegex(RecoveryCheckError, "authority-read-unavailable"):
            queue_snapshot(other, "vm:lab")
        with self.assertRaisesRegex(RecoveryCheckError, "resource-name-invalid"):
            queue_snapshot(self.path, "../../../unsafe")


class EvidenceFileTests(unittest.TestCase):
    def test_single_use_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.json"
            sample = sample_observation()
            save_once(path, sample)
            value = path.read_bytes()
            with self.assertRaises(FileExistsError):
                save_once(path, sample)
            self.assertEqual(path.read_bytes(), value)

    def test_reboot_acceptance_cli_with_stub_no_guest_access(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            base = sample_observation()
            ready = recovered(base, restart_game=True)
            cfg = path / "fixture.json"
            db = path / "authority.sqlite3"
            cfg.touch()
            with patch("scripts.verify_guest_recovery.observe", side_effect=(base, ready)):
                opts = ["--host-config", str(cfg.resolve()), "--database", str(db.resolve()),
                        "--resource", "vm:lab"]
                with patch("builtins.print"):
                    self.assertEqual(main(opts + ["baseline", "--output", str((path/"baseline.json").resolve())]), 0)
                    self.assertEqual(main(opts + ["verify", "--baseline", str((path/"baseline.json").resolve()),
                                                   "--mode", "guest-restart",
                                                   "--output", str((path/"after.json").resolve())]), 0)
            result = json.loads((path/"after.json").read_text())
            self.assertTrue(result["comparison"]["passed"])
            self.assertFalse(result["comparison"]["windowsBootIndependentlyVerified"])


if __name__ == "__main__":
    unittest.main()
