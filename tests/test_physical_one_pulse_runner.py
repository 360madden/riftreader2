"""Offline protocol checks for a single reviewed physical W/Q pulse; NO RIFT input."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import tempfile
import unittest

from scripts import control_host
from scripts import physical_one_pulse_runner as pulse

HOST = socket.gethostname()
PID = 1876545
TICKS = 639299470183328173
SHA = "a" * 64
TOKEN = "t" * 32


def target():
    return {"machineName": HOST, "processId": PID,
            "processStartUtcTicks": TICKS, "executableSha256": SHA.upper()}


def selector(**_):
    return {"status": "ready", "workflow": "physical", "ownerHost": HOST,
            "target": {"hostName": HOST, "processId": PID,
                       "processStartUtcTicks": str(TICKS),
                       "executableSha256": SHA,
                       "executablePath": r"C:\RIFT\rift_x64.exe", "hwnd": 1}}


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.waited = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        self.waited = True


class FakeGateway:
    def __init__(self, config, journal, **kwargs):
        self.calls = []
        self.started = False
        self.closed = False
        self.stop_fails = False
        self.action_fails = False
        self.dirty_status = False
        self.armed = False

    def start(self):
        self.started = True

    def session(self):
        return self

    def command(self, operation, payload):
        self.calls.append((operation, payload))
        if operation == "status":
            return {"target": target(), "armed": self.armed,
                    "recoveryRequired": False, "busy": False,
                    "nativeReadBusy": False,
                    "desktopInputsDown": ["w"] if self.dirty_status else []}
        if operation == "identity":
            return {"target": target()}
        if operation == "arm":
            self.armed = True
            return {"armToken": "token", "expiresInSeconds": 15, "target": target()}
        if operation == "action":
            if self.action_fails:
                raise control_host.ControlHostError("fake uncertain delivery")
            return {"result": {"deliverySucceeded": True, "releaseSucceeded": True},
                    "recoveryRequired": False}
        if operation == "release":
            return {"released": True, "recoveryRequired": False}
        if operation == "stop":
            self.armed = False
            if self.stop_fails:
                raise control_host.ControlHostError("fake stop failure")
            return {"stopped": True, "recoveryRequired": False}
        raise AssertionError(operation)

    def capture(self):
        self.calls.append(("capture", {}))
        return {"target": target(), "captureId": "a" * 32, "imageFormat": "bmp",
                "sha256": "B" * 64,
                "artifact": {"path": r"C:\temp\review.bmp", "sha256": "B" * 64}}

    def close(self):
        self.closed = True


@unittest.skipUnless(os.name == "nt", "Windows reservation only")
class OnePulseTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder = Path(td.name)
        self.config = control_host.HostConfig(
            bind_address="192.168.1.166", agent_port=52001, ui_port=52002,
            guest_address="192.168.1.166", expected_machine_name=HOST,
            token=TOKEN, operator_token="o" * 32,
            output_directory=self.folder, physical_process_id=PID,
            physical_process_start_utc_ticks=TICKS, physical_executable_sha256=SHA)
        self.agent_config = self.folder / "agent.json"
        self.agent_config.write_text(json.dumps({
            "schemaVersion": 1, "hostAddress": "192.168.1.166", "port": 52001,
            "token": TOKEN, "outputDirectory": str(self.folder),
            "expectedMachineName": HOST, "processName": "rift_x64",
            "boundProcessId": PID, "boundProcessStartUtcTicks": TICKS,
            "executablePath": r"C:\RIFT\rift_x64.exe", "executableSha256": SHA,
        }), encoding="utf-8")
        self.proc = FakeProcess()
        self.gateway = FakeGateway(self.config, None)
        self.messages = []
        self.approval = self.folder / "approval.json"

    def run_pulse(self, *, reviewer=None, key="w", hold_ms=80):
        return pulse.run_once(self.config, self.agent_config, HOST, PID, hold_ms,
                              self.approval, key=key, selector=selector,
                              gateway_factory=lambda *_args, **_kw: self.gateway,
                              launch_agent=lambda *_args: self.proc,
                              wait_session=lambda _: self.gateway,
                              reviewer=(reviewer if reviewer is not None
                                        else lambda *_: "Reviewed clear walk lane"),
                              announce=lambda line, **_: self.messages.append(json.loads(line)))

    def test_malformed_target_is_a_clean_refusal(self):
        from scripts.nav_physical_reservation import PhysicalClientIdentity
        pinned = PhysicalClientIdentity(HOST, PID, TICKS, SHA)
        self.assertFalse(pulse._same_target({"machineName": 123, "processId": PID}, pinned))
        self.assertFalse(pulse._same_target({"machineName": HOST, "processId": True}, pinned))

    def test_one_reviewed_pulse_and_verified_stop(self):
        result = self.run_pulse()
        self.assertEqual(result["status"], "pulse-inserted-unverified-game-response")
        self.assertFalse(result["gameResponseVerified"])
        operations = [name for name, _ in self.gateway.calls]
        self.assertEqual(operations, ["status", "identity", "capture", "identity",
                                      "arm", "action", "release", "stop", "status"])
        action = dict(self.gateway.calls)["action"]["action"]
        self.assertEqual(action["keys"], ["w"])
        self.assertEqual(action["holdMilliseconds"], 80)
        self.assertTrue(self.gateway.closed and self.proc.terminated and self.proc.waited)
        self.assertEqual(self.messages[0]["status"], "awaiting-review")

    def test_review_refusal_never_sends_input(self):
        def refuse(*_):
            raise pulse.PhysicalPulseError("no visual review")
        with self.assertRaisesRegex(pulse.PhysicalPulseError, "no visual review"):
            self.run_pulse(reviewer=refuse)
        operations = [name for name, _ in self.gateway.calls]
        self.assertNotIn("arm", operations)
        self.assertNotIn("action", operations)
        self.assertEqual(operations[-3:], ["release", "stop", "status"])
        self.assertTrue(self.proc.terminated)

    def test_dirty_initial_input_rejected_before_capture(self):
        self.gateway.dirty_status = True
        with self.assertRaisesRegex(pulse.PhysicalPulseError, "initial-control-status-not-clean"):
            self.run_pulse()
        self.assertNotIn("capture", [op for op, _ in self.gateway.calls])

    def test_cleanup_unknown_quarantines_after_possible_action(self):
        self.gateway.stop_fails = True
        with self.assertRaisesRegex(pulse.PhysicalPulseError, "cleanup-uncertain"):
            self.run_pulse()
        marker = self.folder / "physical-pulse-cleanup-uncertain.json"
        self.assertTrue(marker.is_file())
        self.assertEqual(json.loads(marker.read_text())["processId"], PID)
        with self.assertRaisesRegex(pulse.PhysicalPulseError, "quarantine-existing"):
            self.run_pulse()

    def test_bad_agent_binding_refused_without_gateway(self):
        raw = json.loads(self.agent_config.read_text())
        raw["boundProcessId"] += 1
        self.agent_config.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(pulse.PhysicalPulseError, "agent-config-identity"):
            self.run_pulse()
        self.assertFalse(self.gateway.started)

    def test_approval_file_binds_exact_capture_and_epoch(self):
        from scripts.nav_physical_reservation import PhysicalClientIdentity
        identity = PhysicalClientIdentity(HOST, PID, TICKS, SHA)
        capture = {"captureId": "a" * 32, "sha256": "B" * 64}
        approved = {"captureId": capture["captureId"], "sha256": capture["sha256"],
                    "machineName": HOST, "processId": PID,
                    "processStartUtcTicks": str(TICKS),
                    "key": "w", "holdMilliseconds": 80,
                    "reviewNote": "Reviewed physical RIFT lane"}

        def write_approval(_):
            self.approval.write_text(json.dumps(approved), encoding="utf-8")

        self.assertEqual(pulse._approval(self.approval, capture, identity,
                                         key="w", hold_ms=80, sleep=write_approval), approved["reviewNote"])
        self.approval.unlink()
        approved["sha256"] = "C" * 64
        with self.assertRaisesRegex(pulse.PhysicalPulseError, "approval-capture-or-target"):
            pulse._approval(self.approval, capture, identity,
                            key="w", hold_ms=80, sleep=write_approval)


    def test_q_pulse_preserves_exact_key_and_duration(self):
        reviewed = []
        def review(capture, pinned, key, hold_ms):
            reviewed.append((key, hold_ms))
            return "Reviewed clear strafe lane"
        result = self.run_pulse(reviewer=review, key="q", hold_ms=60)
        self.assertEqual(reviewed, [("q", 60)])
        self.assertEqual(result["key"], "q")
        self.assertEqual(result["holdMilliseconds"], 60)
        self.assertEqual(self.messages[0]["key"], "q")
        action = dict(self.gateway.calls)["action"]["action"]
        self.assertEqual(action["keys"], ["q"])
        self.assertEqual(action["holdMilliseconds"], 60)

    def file_reviewer(self, approved_key="w", approved_hold=80, omit_action=False):
        def review(capture, pinned, key, hold_ms):
            approved = {"captureId": capture["captureId"], "sha256": capture["sha256"],
                        "machineName": HOST, "processId": PID,
                        "processStartUtcTicks": str(TICKS),
                        "key": approved_key, "holdMilliseconds": approved_hold,
                        "reviewNote": "Reviewed physical RIFT lane"}
            if omit_action:
                del approved["key"]
                del approved["holdMilliseconds"]
            def write(_):
                self.approval.write_text(json.dumps(approved), encoding="utf-8")
            return pulse._approval(self.approval, capture, pinned,
                                   key=key, hold_ms=hold_ms, sleep=write)
        return review

    def assert_approval_refused(self, reviewer, reason):
        with self.assertRaisesRegex(pulse.PhysicalPulseError, reason):
            self.run_pulse(reviewer=reviewer)
        operations = [name for name, _ in self.gateway.calls]
        self.assertNotIn("arm", operations)
        self.assertNotIn("action", operations)
        self.assertEqual(operations[-3:], ["release", "stop", "status"])

    def test_approval_key_mismatch_refused_before_arm(self):
        self.assert_approval_refused(self.file_reviewer(approved_key="q"),
                                     "approval-action-mismatch")

    def test_approval_hold_mismatch_refused_before_arm(self):
        self.assert_approval_refused(self.file_reviewer(approved_hold=60),
                                     "approval-action-mismatch")

    def test_approval_noninteger_hold_refused_before_arm(self):
        self.assert_approval_refused(self.file_reviewer(approved_hold=80.0),
                                     "approval-action-mismatch")

    def test_legacy_approval_refused_before_arm(self):
        self.assert_approval_refused(self.file_reviewer(omit_action=True),
                                     "approval-fields-invalid")

    def test_file_approval_accepts_exact_action(self):
        result = self.run_pulse(reviewer=self.file_reviewer())
        self.assertEqual(result["key"], "w")

    def test_invalid_key_and_duration_refused_before_gateway(self):
        for key, hold_ms in (("a", 80), ("Q", 80), ("w", 19), ("q", 101), ("w", True)):
            with self.subTest(key=key, hold_ms=hold_ms):
                with self.assertRaisesRegex(pulse.PhysicalPulseError, "invalid-one-pulse"):
                    self.run_pulse(key=key, hold_ms=hold_ms)
                self.assertFalse(self.gateway.started)


if __name__ == "__main__":
    unittest.main()
