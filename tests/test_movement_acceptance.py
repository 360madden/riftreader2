"""Offline acceptance traces for the bounded movement feedback loop.

These tests compose the real controller and session orchestrator.  They do not
open a VM, receiver, queue database, or control host and never send input.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_movement_session import (
    MovementSessionError,
    execute_armed_session,
)


NOW = datetime(2026, 10, 29, 20, 30, tzinfo=timezone.utc)


class TraceSample:
    def __init__(self, xyz, sequence, lab):
        self.xyz = xyz
        self.sequence = sequence
        self.lab = lab

    def to_dict(self):
        lab_number = 1 if self.lab == "lab1" else 2
        return {
            "xyz": {"x": self.xyz[0], "y": self.xyz[1], "z": self.xyz[2]},
            "outerSequence": self.sequence,
            "addonSequence": self.sequence * 10,
            "addonClock": float(self.sequence),
            "lab": self.lab,
            "player": f"unit-{lab_number}",
            "addonEpoch": 7,
            "sourceAddress": f"192.168.56.{127 + lab_number}",
            "readerProcessId": 300 + lab_number,
            "readerProcessStartUtcTicks": 400 + lab_number,
            "readerExecutableSha256": "D" * 64,
            "readerInstance": f"reader-{lab_number}",
            "readerNonce": f"nonce-{lab_number}",
            "receiverInstance": f"receiver-{lab_number}",
            "target": {
                "processId": 100 + lab_number,
                "processStartUtcTicks": 200 + lab_number,
                "executableSha256": "C" * 64,
            },
        }


class TraceFeedback:
    def __init__(self, samples):
        self.samples = iter(samples)
        self.current = None

    def read(self, _label):
        self.current = next(self.samples)
        return self.current

    def wait_initial(self, timeout_seconds=4.5):
        if timeout_seconds != 4.5:
            raise AssertionError("unexpected initial feedback timeout")
        self.current = next(self.samples)
        return self.current

    def wait_action_ready(self, timeout_seconds=10.0):
        if timeout_seconds != 10.0:
            raise AssertionError("unexpected action-readiness timeout")
        return self.current

    def wait_after(self, _completed, _prior, timeout_seconds=6.0):
        if timeout_seconds != 6.0:
            raise AssertionError("unexpected feedback timeout")
        self.current = next(self.samples)
        return self.current

    def wait_next(self, _prior, timeout_seconds=3.0):
        if timeout_seconds != 3.0:
            raise AssertionError("unexpected feedback timeout")
        return next(self.samples)


class TraceLease:
    def __init__(self):
        self.finished = []

    def check(self):
        return {"state": "active"}

    def heartbeat(self):
        return {"state": "active"}

    def finish(self, outcome, evidence):
        self.finished.append((outcome, list(evidence)))
        return {"state": "finished", "outcome": outcome}


class TraceHost:
    def __init__(self):
        self.actions = []
        self.arm_count = 0
        self.stop_count = 0

    def status(self, require_armed=None, **_kwargs):
        return {"guest": {
            "armed": bool(require_armed),
            "busy": False,
            "recoveryRequired": False,
            "desktopInputsDown": [],
        }}

    def arm(self, _capture, _note, output):
        self.arm_count += 1
        Path(output).write_text("private-test-capability", encoding="utf-8")

    def action(self, action, _output):
        self.actions.append(action)
        return {
            "result": {
                "deliverySucceeded": True,
                "releaseSucceeded": True,
                "cancelled": False,
                "targetLost": False,
                "stateUncertain": False,
            },
            "recoveryRequired": False,
            "completedAtUtc": NOW.isoformat(),
        }

    def stop(self):
        self.stop_count += 1
        return {"stopped": True, "recoveryRequired": False}


def reviewed_session(mode, *, profile=None, goal=None, keys=("w", "q")):
    return {
        "sessionId": "a" * 32,
        "sessionPlanSha256": "A" * 64,
        "mode": mode,
        "capture": {"captureId": "c" * 32, "capture": "capture.json"},
        "captureImageSha256": "B" * 64,
        "calibrationProfile": str(profile) if profile else None,
        "goal": goal,
        "allowedKeys": list(keys),
    }


def review():
    return {
        "schemaVersion": 1,
        "decision": "approve",
        "sessionId": "a" * 32,
        "sessionPlanSha256": "A" * 64,
        "captureId": "c" * 32,
        "captureImageSha256": "B" * 64,
        "note": "Reviewed clear bounded calibration-aligned corridor.",
    }


class MovementAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_session(self, name, mode, samples, *, profile=None, goal=None,
                    keys=("w", "q"), lab="lab1"):
        host, lease = TraceHost(), TraceLease()
        result = execute_armed_session(
            session=reviewed_session(mode, profile=profile, goal=goal, keys=keys),
            review=review(),
            output=self.root / name,
            host=host,
            lease=lease,
            feedback=TraceFeedback([TraceSample(xyz, sequence, lab)
                                    for sequence, xyz in enumerate(samples, 1)]),
            clock=lambda: 1.0,
            now=lambda: NOW,
        )
        return result, host, lease

    def calibration_profile(self, name, samples, keys=("w", "q"), lab="lab1"):
        result, host, lease = self.run_session(
            name, "calibration", samples, keys=keys, lab=lab)
        self.assertEqual(list(keys), [action.key for action in host.actions])
        self.assertEqual(1, host.arm_count)
        self.assertEqual(1, host.stop_count)
        self.assertEqual("succeeded", lease.finished[0][0])
        profile = self.root / f"{name}-profile.json"
        profile.write_text(json.dumps(result), encoding="utf-8")
        return profile

    def test_two_distinct_lab_geometries_arrive_and_replay_deterministically(self):
        cases = {
            "lab1": {
                "keys": ("w", "q"),
                "calibration": [(0, 0, 0), (.75, 0, 0), (.75, 0, .75)],
                "goal": {"x": 1.2, "y": 0, "z": 0},
                "movement": [(0, 0, 0), (.75, 0, 0), (1.2, 0, 0),
                             (1.2, 0, 0), (1.2, 0, 0)],
            },
            "lab2": {
                "keys": ("s", "q"),
                "calibration": [(10, 2, 20), (10, 2, 20.75), (9.25, 2, 20.75)],
                "goal": {"x": 10, "y": 2, "z": 21.2},
                "movement": [(10, 2, 20), (10, 2, 20.75), (10, 2, 21.2),
                             (10, 2, 21.2), (10, 2, 21.2)],
            },
        }
        for lab, case in cases.items():
            with self.subTest(lab=lab):
                profile = self.calibration_profile(
                    f"{lab}-calibration", case["calibration"], case["keys"], lab)
                first, host, lease = self.run_session(
                    f"{lab}-movement-a", "movement", case["movement"],
                    profile=profile, goal=case["goal"], keys=case["keys"], lab=lab)
                replay, replay_host, replay_lease = self.run_session(
                    f"{lab}-movement-b", "movement", case["movement"],
                    profile=profile, goal=case["goal"], keys=case["keys"], lab=lab)

                self.assertEqual("arrived", first["status"])
                self.assertGreaterEqual(first["feedbackIterations"], 2)
                self.assertEqual(1, first["settles"])
                self.assertEqual(2, first["arrivalObservations"])
                self.assertEqual(
                    [(a.key, a.hold_ms) for a in host.actions],
                    [(a.key, a.hold_ms) for a in replay_host.actions],
                )
                self.assertEqual(first["goal"], replay["goal"])
                self.assertEqual(1, host.arm_count)
                self.assertEqual(1, host.stop_count)
                self.assertEqual("succeeded", lease.finished[0][0])
                self.assertEqual("succeeded", replay_lease.finished[0][0])

    def test_stuck_feedback_halts_without_a_third_action_and_cleans_up(self):
        profile = self.calibration_profile(
            "stuck-calibration", [(0, 0, 0), (.75, 0, 0), (.75, 0, .75)])
        host, lease = TraceHost(), TraceLease()
        with self.assertRaisesRegex(RuntimeError, "no-progress"):
            execute_armed_session(
                session=reviewed_session(
                    "movement", profile=profile, goal={"x": 1.5, "y": 0, "z": 0}),
                review=review(), output=self.root / "stuck-run", host=host, lease=lease,
                feedback=TraceFeedback([
                    TraceSample((0, 0, 0), 1, "lab1"),
                    TraceSample((0, 0, 0), 2, "lab1"),
                    TraceSample((0, 0, 0), 3, "lab1"),
                ]),
                clock=lambda: 1.0, now=lambda: NOW,
            )
        self.assertEqual(2, len(host.actions))
        self.assertEqual(1, host.stop_count)
        self.assertEqual("failed", lease.finished[0][0])

    def test_arrival_settle_that_leaves_tolerance_fails_closed(self):
        profile = self.calibration_profile(
            "settle-calibration", [(0, 0, 0), (.75, 0, 0), (.75, 0, .75)])
        host, lease = TraceHost(), TraceLease()
        with self.assertRaisesRegex(MovementSessionError, "settle left tolerance"):
            execute_armed_session(
                session=reviewed_session(
                    "movement", profile=profile, goal={"x": 1.2, "y": 0, "z": 0}),
                review=review(), output=self.root / "bad-settle-run", host=host, lease=lease,
                feedback=TraceFeedback([
                    TraceSample((0, 0, 0), 1, "lab1"),
                    TraceSample((.75, 0, 0), 2, "lab1"),
                    TraceSample((1.2, 0, 0), 3, "lab1"),
                    TraceSample((1.6, 0, 0), 4, "lab1"),
                ]),
                clock=lambda: 1.0, now=lambda: NOW,
            )
        self.assertEqual(2, len(host.actions))
        self.assertEqual(1, host.stop_count)
        self.assertEqual("failed", lease.finished[0][0])


if __name__ == "__main__":
    unittest.main()
