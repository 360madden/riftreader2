from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_movement_session import (
    LiveHostAdapter, MovementSessionError, _require_feedback_target, build_parser, calibrated_relative_goal,
    execute_armed_session, require_post_turn_calibration, sha, _require_key_hold_timing,
    validate_session_pins,
)
from scripts.movement_controller import MovementAction, MovementError
from scripts.nav_access_queue import QueueError


NOW = datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc)
GAME_TARGET = {"processId": 111, "processStartUtcTicks": 222,
               "executableSha256": "C" * 64}


class Sample:
    def __init__(self, x, y, z, sequence):
        self.xyz = (x, y, z); self.sequence = sequence
    def to_dict(self):
        return {"xyz": {"x": self.xyz[0], "y": self.xyz[1], "z": self.xyz[2]},
                "outerSequence": self.sequence, "lab": "lab1", "player": "unit-1",
                "addonEpoch": 7, "addonSequence": self.sequence,
                "addonClock": float(self.sequence), "sourceAddress": "192.168.56.128",
                "readerProcessId": 333, "readerProcessStartUtcTicks": 444,
                "readerExecutableSha256": "D" * 64, "readerInstance": "reader-1",
                "readerNonce": "nonce-1", "receiverInstance": "receiver-1",
                "target": dict(GAME_TARGET)}


def sample_identity():
    value = Sample(0, 0, 0, 1).to_dict()
    return {key: value[key] for key in (
        "lab", "player", "addonEpoch", "sourceAddress", "readerProcessId",
        "readerProcessStartUtcTicks", "readerExecutableSha256", "readerInstance",
        "readerNonce", "receiverInstance", "target")}


def profile_document():
    return {"schemaVersion": 1, "evidenceKind": "empirical-movement-calibration/1",
            "mode": "calibration", "status": "calibrated", "normalizedCross": 1.0,
            "calibrationKeys": ["w", "q"], "calibrationIdentity": sample_identity(),
            "calibrations": {
                "w": {"key": "w", "dx_per_ms": .005, "dz_per_ms": 0,
                      "calibration_hold_ms": 150, "horizontal_displacement": .75,
                      "vertical_displacement": 0},
                "q": {"key": "q", "dx_per_ms": 0, "dz_per_ms": .005,
                      "calibration_hold_ms": 150, "horizontal_displacement": .75,
                      "vertical_displacement": 0}}}


class Feedback:
    def __init__(self, samples, failure=None):
        self.samples = iter(samples); self.failure = failure; self.waits = 0; self.next_waits = 0
        self.initial_timeouts = []; self.wait_timeouts = []; self.next_wait_timeouts = []
        self.ready_timeouts = []
        self.on_next = None; self.on_ready = None; self.current = None
    def read(self, _label): return next(self.samples)
    def wait_initial(self, timeout_seconds=4.5):
        self.initial_timeouts.append(timeout_seconds)
        self.current = next(self.samples)
        return self.current
    def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
        self.ready_timeouts.append(timeout_seconds)
        if self.on_ready is not None: self.on_ready(len(self.ready_timeouts))
        return self.current
    def wait_after(self, _completed, _prior, timeout_seconds=3.0):
        self.waits += 1; self.wait_timeouts.append(timeout_seconds)
        if self.failure is not None: raise self.failure
        self.current = next(self.samples)
        return self.current
    def wait_next(self, _prior, timeout_seconds=3.0):
        self.next_waits += 1; self.next_wait_timeouts.append(timeout_seconds)
        if self.on_next is not None: self.on_next()
        if self.failure is not None: raise self.failure
        return next(self.samples)


class Lease:
    def __init__(self, fail_check=None):
        self.checks = 0; self.heartbeats = 0; self.finishes = []; self.fail_check = fail_check
    def check(self):
        self.checks += 1
        if self.fail_check == self.checks: raise RuntimeError("lease lost")
    def heartbeat(self): self.heartbeats += 1
    def finish(self, outcome, evidence): self.finishes.append((outcome, evidence))


class Host:
    def __init__(self, ambiguous=False, arm_expired=False, stop_fails=False, measured_hold_ms=None):
        self.ambiguous = ambiguous; self.arm_expired = arm_expired
        self.stop_fails = stop_fails
        self.measured_hold_ms = measured_hold_ms
        self.arms = 0; self.actions = []; self.stops = 0
    def status(self, require_armed=None, **_kwargs):
        if require_armed and self.arm_expired: raise RuntimeError("arm expired")
        return {"guest": {"busy": False, "armed": bool(require_armed),
                          "recoveryRequired": False, "desktopInputsDown": []}}
    def arm(self, _capture, _note, output):
        self.arms += 1; Path(output).write_text("private", encoding="utf-8")
    def action(self, action, _output):
        self.actions.append(action)
        return {"result": {"deliverySucceeded": True,
                            "releaseSucceeded": not self.ambiguous,
                            "cancelled": False, "targetLost": False,
                            "observedKeyHoldMilliseconds": (action.hold_ms if self.measured_hold_ms is None else self.measured_hold_ms),
                            "stateUncertain": self.ambiguous},
                "recoveryRequired": self.ambiguous,
                "completedAtUtc": NOW.isoformat()}
    def stop(self):
        self.stops += 1
        return {"stopped": not self.stop_fails, "recoveryRequired": self.stop_fails}


def session(mode, profile=None, goal=None, keys=("w", "q"), dimension="2d",
            turn_hold_ms=None, calibration_hold_ms=150):
    return {"sessionId": "a" * 32, "sessionPlanSha256": "A" * 64,
            "mode": mode, "capture": {"captureId": "c" * 32, "capture": "capture.json", "image": "screen.bmp"},
            "captureImageSha256": "B" * 64, "calibrationProfile": str(profile) if profile else None,
            "goal": goal, "allowedKeys": list(keys), "target": dict(GAME_TARGET),
            "movementDimension": dimension, "turnHoldMs": turn_hold_ms,
            "calibrationPulseMs": calibration_hold_ms}


def review():
    return {"schemaVersion": 1, "decision": "approve", "sessionId": "a" * 32,
            "sessionPlanSha256": "A" * 64, "captureId": "c" * 32,
            "captureImageSha256": "B" * 64, "note": "Reviewed bounded empty-world movement batch."}


class KeyHoldTimingTests(unittest.TestCase):
    def receipt(self, hold, down=366.2, up=537.2, key="s"):
        return {"action": {"keys": [key], "holdMilliseconds": hold},
                "inputEvents": [
                    {"kind": "keyDownInserted", "value": key, "elapsedMilliseconds": down},
                    {"kind": "keyUpInserted", "value": key, "elapsedMilliseconds": up}]}

    def test_accepts_measured_calibration_hold(self):
        self.assertAlmostEqual(_require_key_hold_timing(self.receipt(150), "s", 150), 171)

    def test_real_receipt_key_events_must_fit_action_duration(self):
        receipt = self.receipt(100, down=45.0, up=152.0)
        receipt["elapsedMilliseconds"] = 170.0
        self.assertAlmostEqual(_require_key_hold_timing(receipt, "s", 100), 107.0)
        receipt["elapsedMilliseconds"] = 140.0
        with self.assertRaisesRegex(MovementSessionError, "exceed receipt duration"):
            _require_key_hold_timing(receipt, "s", 100)
        for invalid in ("170", float("nan"), -1):
            receipt["elapsedMilliseconds"] = invalid
            with self.subTest(elapsed=invalid), self.assertRaisesRegex(
                    MovementSessionError, "exceed receipt duration"):
                _require_key_hold_timing(receipt, "s", 100)

    def test_rejects_live_oversized_vm_hold(self):
        with self.assertRaisesRegex(MovementSessionError, "action key hold timing drifted"):
            _require_key_hold_timing(self.receipt(126, 366.2, 654.5), "s", 126)

    def test_rejects_missing_or_conflicting_events(self):
        receipt = self.receipt(150)
        receipt["inputEvents"].pop()
        with self.assertRaisesRegex(MovementSessionError, "incomplete or ambiguous"):
            _require_key_hold_timing(receipt, "s", 150)
        with self.assertRaisesRegex(MovementSessionError, "does not match"):
            _require_key_hold_timing(self.receipt(150), "w", 150)


    def test_live_host_adapter_places_actual_hold_inside_action_result(self):
        receipt = {
            "action": {"keys": ["w"], "holdMilliseconds": 100},
            "result": {"deliverySucceeded": True, "releaseSucceeded": True,
                       "cancelled": False, "targetLost": False, "stateUncertain": False},
            "recoveryRequired": False,
            "completedAtUtc": NOW.isoformat(),
            "inputEvents": [
                {"kind": "keyDownInserted", "value": "w", "elapsedMilliseconds": 75.4093},
                {"kind": "keyUpInserted", "value": "w", "elapsedMilliseconds": 188.4930},
            ],
        }
        host = LiveHostAdapter(None, None)
        with patch("scripts.run_movement_session._action", return_value={"result": receipt}):
            actual = host.action(MovementAction("w", 100, 0, 0), Path("unused/action-1.json"))
        self.assertAlmostEqual(actual["result"]["observedKeyHoldMilliseconds"], 113.0837)
        self.assertNotIn("observedKeyHoldMilliseconds", actual)

class MovementSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _capture_pins(self):
        metadata = self.root / "capture.json"
        image = self.root / "screen.png"
        metadata.write_text('{"captureId":"reviewed"}', encoding="utf-8")
        image.write_bytes(b"reviewed-image")
        return {"capture": {"capture": str(metadata), "image": str(image)},
                "captureMetadataSha256": sha(metadata), "captureImageSha256": sha(image)}

    def test_prepare_cli_exposes_relative_goal_and_reviewed_turn(self):
        common = ["prepare", "--host-plan", "host.json", "--feedback-pin", "pin.json",
                  "--output", "out"]
        relative = build_parser().parse_args(common + ["--mode", "movement",
            "--dimension", "1d", "--keys", "w", "--calibration-profile", "profile.json",
            "--calibrated-displacements", "2.0"])
        self.assertEqual(relative.calibrated_displacements, 2.0)
        turn = build_parser().parse_args(common + ["--mode", "turn", "--keys", "d",
                                                   "--turn-hold-ms", "100"])
        self.assertEqual(turn.keys, ["d"]); self.assertEqual(turn.turn_hold_ms, 100)
        calibration = build_parser().parse_args(
            common + ["--mode", "calibration", "--dimension", "1d", "--keys", "w",
                      "--calibration-hold-ms", "100"])
        self.assertEqual(calibration.calibration_hold_ms, 100)
        self.assertEqual(build_parser().parse_args(common + ["--mode", "calibration"]).calibration_hold_ms, 150)

    def test_calibration_arms_once_and_measures_only_reviewed_w_q(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2), Sample(.5, 0, .5, 3)])
        result = execute_armed_session(session=session("calibration"), review=review(),
            output=self.root / "run", host=host, lease=lease, feedback=feedback,
            clock=lambda: 1.0, now=lambda: NOW)
        self.assertTrue(result["success"]); self.assertEqual(result["status"], "calibrated")
        self.assertEqual([a.key for a in host.actions], ["w", "q"])
        self.assertEqual(feedback.initial_timeouts, [4.5])
        self.assertEqual(feedback.ready_timeouts, [10.0, 10.0])
        self.assertEqual(feedback.wait_timeouts, [6.0, 6.0])
        self.assertEqual(host.arms, 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_1d_forward_calibration_uses_reviewed_100ms_pulse(self):
        host, lease = Host(measured_hold_ms=117.6375), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.4, 0, 0, 2)])
        result = execute_armed_session(
            session=session("calibration", keys=("w",), dimension="1d", calibration_hold_ms=100),
            review=review(), output=self.root / "short-calibration",
            host=host, lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(feedback.ready_timeouts, [20.0, 5.0])
        self.assertEqual([(action.key, action.hold_ms) for action in host.actions], [("w", 100)])
        self.assertEqual(result["calibrations"]["w"]["calibration_hold_ms"], 118)
        self.assertAlmostEqual(result["calibrations"]["w"]["dx_per_ms"], .4 / 118)
        self.assertEqual(result["actionEvidence"][0]["result"]["result"]["observedKeyHoldMilliseconds"], 117.6375)
        self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_missing_or_unusable_measured_hold_stops_without_calibration(self):
        class MissingTimingHost(Host):
            def action(self, action, output):
                receipt = super().action(action, output)
                receipt["result"].pop("observedKeyHoldMilliseconds")
                return receipt

        cases = (("missing", MissingTimingHost()),
                 ("nonfinite", Host(measured_hold_ms=float("nan"))),
                 ("over-bound", Host(measured_hold_ms=172)))
        for name, host in cases:
            lease = Lease()
            with self.subTest(name=name), self.assertRaisesRegex(
                    MovementSessionError, "calibration measured hold"):
                execute_armed_session(
                    session=session("calibration", keys=("w",), dimension="1d",
                                    calibration_hold_ms=150),
                    review=review(), output=self.root / f"bad-measured-hold-{name}",
                    host=host, lease=lease, feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
            self.assertEqual(len(host.actions), 1)
            self.assertEqual(host.stops, 1)
            self.assertEqual(lease.finishes[0][0], "failed")

    def test_invalid_calibration_holds_reject_before_arm(self):
        for index, hold in enumerate((None, True, "100", 0, 151)):
            host, lease = Host(), Lease()
            with self.subTest(hold=hold), self.assertRaisesRegex(
                    MovementSessionError, "session calibration hold is invalid"):
                execute_armed_session(
                    session=session("calibration", keys=("w",), dimension="1d",
                                    calibration_hold_ms=hold),
                    review=review(), output=self.root / f"invalid-hold-{index}",
                    host=host, lease=lease, feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
            self.assertEqual(host.arms, 0)
            self.assertEqual(host.actions, [])
            self.assertEqual(host.stops, 1)

    def test_armed_run_clock_does_not_include_prearm_setup(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2),
                             Sample(.5, 0, .5, 3)])
        result = execute_armed_session(session=session("calibration"), review=review(),
            output=self.root / "run", host=host, lease=lease, feedback=feedback,
            clock=lambda: 0.0 if host.arms == 1 else (_ for _ in ()).throw(
                AssertionError("run clock sampled before ARM")), now=lambda: NOW)
        self.assertTrue(result["success"])

    def test_in_arm_readiness_failure_stops_without_input_or_rearm(self):
        class ExpiringFeedback(Feedback):
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                if len(self.ready_timeouts) == 0:
                    self.ready_timeouts.append(timeout_seconds)
                    raise MovementSessionError("movement-feedback-anchor-budget-timeout")
                return super().wait_action_ready(timeout_seconds)

        host, lease = Host(), Lease()
        feedback = ExpiringFeedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(MovementSessionError, "anchor-budget-timeout"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "ready-fail", host=host,
                lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(feedback.ready_timeouts, [10.0])
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_unready_source_arms_but_never_sends_input_and_releases(self):
        class UnreadyFeedback(Feedback):
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                self.ready_timeouts.append(timeout_seconds)
                raise MovementSessionError("movement-feedback-anchor-budget-timeout")

        host, lease = Host(), Lease()
        feedback = UnreadyFeedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(MovementSessionError, "anchor-budget-timeout"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "prearm-ready-fail", host=host,
                lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_expired_lease_finish_preserves_original_expiration_and_stops(self):
        class ExpiredLease(Lease):
            def check(self):
                self.checks += 1
                raise QueueError("lease expired during review")
            def finish(self, outcome, evidence):
                self.finishes.append((outcome, evidence))
                raise QueueError("request is no longer running")

        host, lease = Host(), ExpiredLease()
        with self.assertRaisesRegex(QueueError, "lease expired during review"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "expired-lease", host=host, lease=lease,
                feedback=Feedback([]), clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 0)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_expired_lease_finish_never_masks_failed_stop(self):
        class ExpiredLease(Lease):
            def check(self): raise QueueError("lease expired during review")
            def finish(self, outcome, evidence):
                raise QueueError("request is no longer running")

        host = Host(stop_fails=True)
        with self.assertRaisesRegex(MovementSessionError, "STOP did not verify release"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "failed-stop", host=host, lease=ExpiredLease(),
                feedback=Feedback([]), clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 0)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_finish_failure_after_success_remains_a_hard_failure(self):
        class FinishFailedLease(Lease):
            def finish(self, outcome, evidence):
                raise QueueError("queue cleanup unavailable")

        host = Host()
        with self.assertRaisesRegex(QueueError, "queue cleanup unavailable"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "finish-failed",
                host=host, lease=FinishFailedLease(),
                feedback=Feedback([Sample(0, 0, 0, 1), Sample(0, 0, 0, 2)]),
                clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.stops, 1)
        self.assertEqual(len(host.actions), 1)

    def test_lease_is_revalidated_after_initial_feedback_before_arm(self):
        host, lease = Host(), Lease(fail_check=2)
        feedback = Feedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(RuntimeError, "lease lost"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "lease-expired-during-ready", host=host,
                lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 0)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_arm_is_revalidated_after_readiness_wait_before_input(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1)])
        feedback.on_ready = lambda call: setattr(host, "arm_expired", True) if call == 1 else None
        with self.assertRaisesRegex(RuntimeError, "arm expired"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "arm-expired-during-ready", host=host,
                lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_lease_is_revalidated_after_in_arm_readiness_wait(self):
        host, lease = Host(), Lease(fail_check=4)
        feedback = Feedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(RuntimeError, "lease lost"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "in-arm-lease-expired", host=host,
                lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_first_action_ready_position_drift_stops_without_input(self):
        class DriftFeedback(Feedback):
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                self.ready_timeouts.append(timeout_seconds)
                return Sample(.051, 0, 0, 2)

        host, lease = Host(), Lease()
        feedback = DriftFeedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(MovementSessionError, "position drifted"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "prearm-position-drift", host=host,
                lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_in_arm_ready_position_drift_stops_without_input(self):
        class DriftFeedback(Feedback):
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                self.ready_timeouts.append(timeout_seconds)
                return Sample(.051, 0, 0, 2)

        host, lease = Host(), Lease()
        feedback = DriftFeedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(MovementSessionError, "position drifted"):
            execute_armed_session(session=session("turn", keys=("d",), turn_hold_ms=100),
                review=review(), output=self.root / "in-arm-position-drift", host=host,
                lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_allowed_ready_drift_becomes_exact_calibration_baseline(self):
        class SettlingFeedback(Feedback):
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                self.ready_timeouts.append(timeout_seconds)
                if len(self.ready_timeouts) == 1:
                    self.current = Sample(.04, 0, 0, 2)
                    return self.current
                return self.current

        host, lease = Host(), Lease()
        feedback = SettlingFeedback([Sample(0, 0, 0, 1), Sample(.54, 0, 0, 3)])
        result = execute_armed_session(
            session=session("calibration", keys=("w",), dimension="1d"),
            review=review(), output=self.root / "ready-calibration-baseline",
            host=host, lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(.04, result["samples"][0]["xyz"]["x"])
        self.assertEqual(.04, result["actionEvidence"][0]["before"]["xyz"]["x"])
        self.assertEqual(.54, result["samples"][-1]["xyz"]["x"])
        self.assertAlmostEqual(.5 / 150,
            result["calibrations"]["w"]["dx_per_ms"], places=12)

    def test_1d_prewarm_precedes_arm_and_post_arm_check_is_bounded(self):
        host, lease = Host(), Lease()
        observations = []

        class TimedFeedback(Feedback):
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                observations.append((timeout_seconds, host.arms,
                                     kwargs.get("minimum_fast_anchor_remaining_milliseconds")))
                return super().wait_action_ready(timeout_seconds)

        feedback = TimedFeedback([Sample(0, 0, 0, 1), Sample(.35, 0, 0, 2)])
        result = execute_armed_session(
            session=session("calibration", keys=("w",), dimension="1d",
                            calibration_hold_ms=100),
            review=review(), output=self.root / "prewarmed-forward",
            host=host, lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertTrue(result["success"])
        self.assertEqual(observations, [(20.0, 0, 6250.0), (5.0, 1, None)])
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(host.stops, 1)

    def test_1d_post_arm_freshness_gap_releases_without_input(self):
        host, lease = Host(), Lease()

        class GapFeedback(Feedback):
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                if self.ready_timeouts:
                    self.ready_timeouts.append(timeout_seconds)
                    raise MovementSessionError("post-arm-source-not-fresh")
                return super().wait_action_ready(timeout_seconds)

        feedback = GapFeedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(MovementSessionError, "post-arm-source-not-fresh"):
            execute_armed_session(
                session=session("calibration", keys=("w",), dimension="1d"),
                review=review(), output=self.root / "no-post-arm-source",
                host=host, lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(feedback.ready_timeouts, [20.0, 5.0])
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.actions, [])
        self.assertEqual(host.stops, 1)

    def test_readiness_precedes_slow_armed_status_then_status_precedes_input(self):
        events = []
        class TimingHost(Host):
            def __init__(self):
                super().__init__()
                self.armed_status_calls = 0
            def status(self, require_armed=None, **kwargs):
                if require_armed:
                    self.armed_status_calls += 1
                    events.append("armed-status")
                return super().status(require_armed=require_armed, **kwargs)
            def action(self, action, output):
                events.append("action")
                return super().action(action, output)

        class NarrowWindowFeedback(Feedback):
            def __init__(self, samples, host):
                super().__init__(samples)
                self.host = host
            def wait_action_ready(self, timeout_seconds=10.0, **kwargs):
                self.ready_timeouts.append(timeout_seconds)
                events.append(f"ready-{len(self.ready_timeouts)}")
                if len(self.ready_timeouts) == 1 and self.host.armed_status_calls:
                    raise MovementSessionError("same-anchor readiness window missed")
                return self.current

        host, lease = TimingHost(), Lease()
        feedback = NarrowWindowFeedback(
            [Sample(0, 0, 0, 1), Sample(0, 0, 0, 2)], host)
        result = execute_armed_session(
            session=session("turn", keys=("d",), turn_hold_ms=100),
            review=review(), output=self.root / "same-anchor-window",
            host=host, lease=lease, feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertTrue(result["success"])
        self.assertEqual(host.armed_status_calls, 1)
        self.assertEqual(len(host.actions), 1)
        self.assertLess(events.index("ready-1"), events.index("armed-status"))
        self.assertLess(events.index("armed-status"), events.index("action"))

    def test_goal_run_stops_then_confirms_one_advancing_released_settle(self):
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"calibrations": {
            "w": {"key": "w", "dx_per_ms": .005, "dz_per_ms": 0,
                  "calibration_hold_ms": 150, "horizontal_displacement": .75,
                  "vertical_displacement": 0},
            "q": {"key": "q", "dx_per_ms": 0, "dz_per_ms": .005,
                  "calibration_hold_ms": 150, "horizontal_displacement": .75,
                  "vertical_displacement": 0}},
            "schemaVersion": 1, "evidenceKind": "empirical-movement-calibration/1",
            "mode": "calibration", "status": "calibrated", "normalizedCross": 1.0,
            "calibrationKeys": ["w", "q"], "calibrationIdentity": sample_identity()}),
            encoding="utf-8")
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.75, 0, 0, 2),
                             Sample(1.2, 0, 0, 3), Sample(1.2, 0, 0, 4)])
        feedback.on_next = lambda: self.assertEqual(host.stops, 1)
        result = execute_armed_session(session=session("movement", profile,
                    {"x": 1.2, "y": 0, "z": 0}), review=review(),
                    output=self.root / "run", host=host, lease=lease, feedback=feedback,
                    clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(result["status"], "arrived"); self.assertEqual(result["settles"], 1)
        self.assertEqual(result["arrivalObservations"], 2); self.assertEqual(feedback.next_waits, 1)
        self.assertEqual(feedback.wait_timeouts, [6.0, 6.0])
        self.assertEqual(feedback.next_wait_timeouts, [3.0])
        self.assertEqual(len(host.actions), 2); self.assertEqual(result["feedbackIterations"], 2)
        self.assertEqual(host.arms, 1)
        self.assertEqual(host.stops, 1); self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_one_action_arrival_stops_then_requires_distinct_stationary_settle(self):
        profile = self.root / "profile.json"
        profile.write_text(json.dumps(profile_document()), encoding="utf-8")
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.8, 0, 0, 2),
                             Sample(.81, 0, 0, 3)])
        feedback.on_next = lambda: self.assertEqual(host.stops, 1)
        result = execute_armed_session(session=session("movement", profile,
                    {"x": 1, "y": 0, "z": 0}), review=review(),
                    output=self.root / "one-action", host=host, lease=lease,
                    feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(result["status"], "arrived")
        self.assertEqual(result["feedbackIterations"], 1)
        self.assertEqual(result["settles"], 1)
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_first_anchor_wait_does_not_consume_movement_action_budget(self):
        profile = self.root / "profile.json"
        profile.write_text(json.dumps(profile_document()), encoding="utf-8")
        elapsed = [0.0]

        class SlowFirstAnchorFeedback(Feedback):
            def wait_after(self, completed, prior, timeout_seconds=6.0):
                result = super().wait_after(completed, prior, timeout_seconds)
                elapsed[0] = 12.3
                return result

        host, lease = Host(), Lease()
        feedback = SlowFirstAnchorFeedback([Sample(0, 0, 0, 1),
                                            Sample(.8, 0, 0, 2), Sample(.81, 0, 0, 3)])
        feedback.on_ready = lambda _n: elapsed.__setitem__(0, 9.0)
        result = execute_armed_session(session=session("movement", profile,
                    {"x": 1, "y": 0, "z": 0}), review=review(),
                    output=self.root / "late-initial-anchor", host=host, lease=lease,
                    feedback=feedback, clock=lambda: elapsed[0], now=lambda: NOW)
        self.assertEqual(result["status"], "arrived")
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(host.stops, 1)

    def test_retained_lab1_short_final_geometry_selects_bounded_96ms_pulse(self):
        profile = self.root / "lab1-short-profile.json"
        document = {"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "movementDimension": "1d", "normalizedCross": None,
            "calibrationIdentity": sample_identity(), "calibrationKeys": ["w"],
            "calibrationEnd": {"xyz": {"x": 7416.93994140625,
                "y": 863.5799560546875, "z": 2926.919921875}},
            "calibrations": {"w": {"key": "w",
                "dx_per_ms": .005602213541666666, "dz_per_ms": -.003466796875,
                "calibration_hold_ms": 150, "horizontal_displacement": .9882197304376293,
                "vertical_displacement": 0}}}
        profile.write_text(json.dumps(document), encoding="utf-8")
        current = Sample(7416.93994140625, 863.5799560546875, 2926.919921875, 1)
        goal = {"x": 7417.5, "y": 863.5799560546875, "z": 2926.62}
        host, lease = Host(), Lease()
        result = execute_armed_session(session=session("movement", profile, goal,
                    keys=("w",), dimension="1d"), review=review(),
                    output=self.root / "lab1-short", host=host, lease=lease,
                    feedback=Feedback([current,
                        Sample(goal["x"], goal["y"], goal["z"], 2),
                        Sample(goal["x"], goal["y"], goal["z"], 3)]),
                    clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(result["status"], "arrived")
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(host.actions[0].hold_ms, 96)
        self.assertAlmostEqual(host.actions[0].distance_before, .6353099712241329)
        self.assertAlmostEqual(host.actions[0].predicted_distance_after,
                               .039707453960399305)

    def test_one_action_arrival_rejects_stale_or_moving_released_settle(self):
        profile = self.root / "profile.json"
        profile.write_text(json.dumps(profile_document()), encoding="utf-8")
        cases = (("stale", Sample(.81, 0, 0, 2), MovementSessionError,
                  "feedback did not advance"),
                 ("moving", Sample(.86, 0, 0, 3), MovementError,
                  "not planar-stationary"))
        for name, settle, error, message in cases:
            host, lease = Host(), Lease()
            feedback = Feedback([Sample(0, 0, 0, 1), Sample(.8, 0, 0, 2), settle])
            with self.subTest(name=name), self.assertRaisesRegex(error, message):
                execute_armed_session(session=session("movement", profile,
                    {"x": 1, "y": 0, "z": 0}), review=review(),
                    output=self.root / f"one-action-{name}", host=host, lease=lease,
                    feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
            self.assertEqual(len(host.actions), 1)
            self.assertEqual(host.stops, 1)
            self.assertEqual(lease.finishes[0][0], "failed")

    def test_ambiguous_action_stops_fails_and_never_retries(self):
        host, lease = Host(ambiguous=True), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(MovementSessionError, "ambiguous"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "run", host=host, lease=lease, feedback=feedback,
                clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(len(host.actions), 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_feedback_failure_stops_fails_and_never_retries(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1)], failure=RuntimeError("stale feedback"))
        with self.assertRaisesRegex(RuntimeError, "stale feedback"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "run", host=host, lease=lease, feedback=feedback,
                clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(len(host.actions), 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_arm_expiry_prevents_action_and_cleans_once(self):
        host, lease = Host(arm_expired=True), Lease()
        with self.assertRaisesRegex(RuntimeError, "arm expired"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "run", host=host, lease=lease,
                feedback=Feedback([Sample(0, 0, 0, 1)]), clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.actions, []); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_queue_loss_prevents_action_and_cleans_once(self):
        host, lease = Host(), Lease(fail_check=2)
        with self.assertRaisesRegex(RuntimeError, "lease lost"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "run", host=host, lease=lease,
                feedback=Feedback([Sample(0, 0, 0, 1)]), clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.actions, []); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_cleanup_failure_forces_failed_finish(self):
        host, lease = Host(stop_fails=True), Lease()
        with self.assertRaisesRegex(MovementSessionError, "STOP"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "run", host=host, lease=lease,
                feedback=Feedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2),
                                   Sample(.5, 0, .5, 3)]), clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_reduced_calibration_profile_is_rejected(self):
        profile = self.root / "reduced.json"
        profile.write_text(json.dumps({"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "normalizedCross": 1.0,
            "calibrationKeys": ["w", "q"], "calibrations": {
                "w": {"key": "w", "dx_per_ms": .005, "dz_per_ms": 0,
                      "calibration_hold_ms": 150, "horizontal_displacement": .75,
                      "vertical_displacement": 0}}}), encoding="utf-8")
        host, lease = Host(), Lease()
        with self.assertRaisesRegex(MovementSessionError, "reviewed keys"):
            execute_armed_session(session=session("movement", profile,
                    {"x": 1, "y": 0, "z": 0}), review=review(), output=self.root / "run",
                    host=host, lease=lease, feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.actions, []); self.assertEqual(lease.finishes[0][0], "failed")

    def test_calibration_profile_mutation_breaks_session_pin(self):
        files = []
        for name in ("host-plan.json", "host-receipt.json", "feedback.json", "profile.json"):
            path = self.root / name; path.write_text('{}', encoding="utf-8"); files.append(path)
        pinned = {"mode": "movement", "hostPlan": str(files[0]), "hostPlanSha256": sha(files[0]),
                  "hostReceipt": str(files[1]), "hostReceiptSha256": sha(files[1]),
                  "feedbackPin": str(files[2]), "feedbackPinSha256": sha(files[2]),
                  "calibrationProfile": str(files[3]), "calibrationProfileSha256": sha(files[3])}
        pinned.update(self._capture_pins())
        files[3].write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "calibration profile changed"):
            validate_session_pins(pinned)

    def test_turn_result_mutation_breaks_post_turn_session_pin(self):
        files = []
        for name in ("host-plan.json", "host-receipt.json", "feedback.json",
                     "profile.json", "turn.json"):
            path = self.root / name; path.write_text('{}', encoding="utf-8"); files.append(path)
        pinned = {"mode": "movement", "hostPlan": str(files[0]),
                  "hostPlanSha256": sha(files[0]), "hostReceipt": str(files[1]),
                  "hostReceiptSha256": sha(files[1]), "feedbackPin": str(files[2]),
                  "feedbackPinSha256": sha(files[2]), "calibrationProfile": str(files[3]),
                  "calibrationProfileSha256": sha(files[3]), "afterTurnResult": str(files[4]),
                  "afterTurnResultSha256": sha(files[4])}
        pinned.update(self._capture_pins())
        files[4].write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "turn result changed"):
            validate_session_pins(pinned)

    def test_modified_reviewed_capture_files_fail_before_arm(self):
        source_paths = []
        for name in ("host-plan.json", "host-receipt.json", "feedback.json"):
            path = self.root / name
            path.write_text("{}", encoding="utf-8")
            source_paths.append(path)
        base = {"mode": "turn", "hostPlan": str(source_paths[0]),
                "hostPlanSha256": sha(source_paths[0]),
                "hostReceipt": str(source_paths[1]),
                "hostReceiptSha256": sha(source_paths[1]),
                "feedbackPin": str(source_paths[2]),
                "feedbackPinSha256": sha(source_paths[2])}
        for target in ("capture", "image"):
            with self.subTest(target=target):
                pinned = {**base, **self._capture_pins()}
                validate_session_pins(pinned)
                Path(pinned["capture"][target]).write_bytes(b"tampered-after-review")
                with self.assertRaisesRegex(MovementSessionError, "reviewed capture artifact changed"):
                    validate_session_pins(pinned)

    def test_missing_reviewed_capture_pin_is_rejected(self):
        source_paths = []
        for name in ("host-plan.json", "host-receipt.json", "feedback.json"):
            path = self.root / name
            path.write_text("{}", encoding="utf-8")
            source_paths.append(path)
        pinned = {"mode": "turn", "hostPlan": str(source_paths[0]),
                  "hostPlanSha256": sha(source_paths[0]),
                  "hostReceipt": str(source_paths[1]),
                  "hostReceiptSha256": sha(source_paths[1]),
                  "feedbackPin": str(source_paths[2]),
                  "feedbackPinSha256": sha(source_paths[2])}
        with self.assertRaisesRegex(MovementSessionError, "reviewed capture pin missing"):
            validate_session_pins(pinned)

    def test_collinear_calibration_profile_is_rejected(self):
        vector = {"key": "w", "dx_per_ms": .005, "dz_per_ms": 0,
                  "calibration_hold_ms": 150, "horizontal_displacement": .75,
                  "vertical_displacement": 0}
        profile = self.root / "collinear.json"
        profile.write_text(json.dumps({"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "normalizedCross": 0, "calibrationKeys": ["w", "q"],
            "calibrationIdentity": sample_identity(),
            "calibrations": {"w": vector, "q": {**vector, "key": "q"}}}), encoding="utf-8")
        host, lease = Host(), Lease()
        with self.assertRaisesRegex(ValueError, "collinear"):
            execute_armed_session(session=session("movement", profile,
                    {"x": 1, "y": 0, "z": 0}), review=review(), output=self.root / "run",
                    host=host, lease=lease, feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.actions, []); self.assertEqual(lease.finishes[0][0], "failed")

    def test_calibration_supports_reviewed_s_q_without_inferring_opposites(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(-.5, 0, 0, 2),
                             Sample(-.5, 0, .5, 3)])
        result = execute_armed_session(session=session("calibration", keys=("s", "q")),
            review=review(), output=self.root / "run", host=host, lease=lease,
            feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual([action.key for action in host.actions], ["s", "q"])
        self.assertEqual(result["calibrationKeys"], ["s", "q"])
        self.assertEqual(set(result["calibrations"]), {"s", "q"})
        self.assertNotIn("w", result["calibrations"])

    def test_explicit_1d_calibration_measures_only_reviewed_s(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.4, 0, 0, 2)])
        result = execute_armed_session(
            session=session("calibration", keys=("s",), dimension="1d"), review=review(),
            output=self.root / "run", host=host, lease=lease, feedback=feedback,
            clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual([action.key for action in host.actions], ["s"])
        self.assertEqual(result["movementDimension"], "1d")
        self.assertEqual(result["calibrationKeys"], ["s"])
        self.assertEqual(set(result["calibrations"]), {"s"})
        self.assertIsNone(result["normalizedCross"])
        self.assertEqual(feedback.initial_timeouts, [4.5])

    def test_calibrated_relative_goal_uses_one_measured_vector_and_endpoint(self):
        profile = self.root / "profile-relative.json"
        profile.write_text(json.dumps({"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "movementDimension": "1d", "normalizedCross": None,
            "calibrationIdentity": sample_identity(), "calibrationKeys": ["w"],
            "calibrationEnd": {"xyz": {"x": 10, "y": 3, "z": 20}},
            "calibrations": {"w": {"key": "w", "dx_per_ms": .002,
                "dz_per_ms": -.004, "calibration_hold_ms": 150,
                "horizontal_displacement": .67, "vertical_displacement": 0}}}),
            encoding="utf-8")
        goal = calibrated_relative_goal(profile, "w", 2.0)
        self.assertAlmostEqual(goal.x, 10.6)
        self.assertEqual(goal.y, 3)
        self.assertAlmostEqual(goal.z, 18.8)

    def test_calibrated_relative_goal_rejects_bad_scale_or_profile(self):
        profile = self.root / "profile-relative.json"
        profile.write_text(json.dumps({"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "movementDimension": "1d", "calibrationKeys": ["w"],
            "calibrationEnd": {"xyz": {"x": 0, "y": 0, "z": 0}},
            "calibrations": {"w": {"key": "w", "dx_per_ms": .002,
                "dz_per_ms": 0, "calibration_hold_ms": 150}}}), encoding="utf-8")
        for scale in (True, 1.49, 2.51, float("inf")):
            with self.subTest(scale=scale), self.assertRaises(MovementSessionError):
                calibrated_relative_goal(profile, "w", scale)
        with self.assertRaisesRegex(MovementSessionError, "matching 1d"):
            calibrated_relative_goal(profile, "s", 2.0)

    def test_turn_sends_one_reviewed_pulse_gets_fresh_feedback_and_stops(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(10, 2, 20, 1), Sample(10.02, 2, 20.01, 2)])
        result = execute_armed_session(
            session=session("turn", keys=("d",), turn_hold_ms=100), review=review(),
            output=self.root / "turn", host=host, lease=lease, feedback=feedback,
            clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(result["status"], "turn-input-completed")
        self.assertEqual(result["observedKeyHoldMilliseconds"], 100.0)
        self.assertFalse(result["headingClaimed"])
        self.assertEqual(result["profileInvalidationScope"],
                         "explicit-after-turn-result-chain-only")
        self.assertEqual(result["nextStep"],
                         "review a fresh screenshot before forward calibration")
        self.assertEqual([(action.key, action.hold_ms) for action in host.actions], [("d", 100)])
        self.assertEqual(feedback.wait_timeouts, [6.0])
        self.assertEqual(host.arms, 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_post_stop_capture_pins_exact_game_target(self):
        target = {**GAME_TARGET, "windowHandle": 333}
        class Pinned:
            def __init__(self): self.target = target; self.checks = 0
            def status(self, *, require_armed):
                self.checks += 1
                self.assert_disarmed = require_armed is False
                return {"guest": {"target": self.target}}
        pinned = Pinned()
        adapter = LiveHostAdapter(pinned, client=None)
        image = self.root / "after.bmp"; image.write_bytes(b"BMtest-frame")
        metadata = self.root / "after.json"
        metadata.write_text(json.dumps({"target": target, "capturedAtUtc": NOW.isoformat()}),
                            encoding="utf-8")
        captured = {"capture": str(metadata), "image": str(image)}
        with patch("scripts.run_movement_session._capture", return_value=captured) as take:
            value = adapter.capture_after_stop(self.root / "after-capture")
            take.assert_called_once()
        self.assertEqual(value["imageSha256"], sha(image))
        self.assertEqual(pinned.checks, 2)
        self.assertTrue(pinned.assert_disarmed)
        metadata.write_text(json.dumps({"target": {**target, "processId": 999},
                                        "capturedAtUtc": NOW.isoformat()}), encoding="utf-8")
        with patch("scripts.run_movement_session._capture", return_value=captured):
            with self.assertRaisesRegex(MovementSessionError, "target changed"):
                adapter.capture_after_stop(self.root / "wrong-target")

    def test_turn_captures_after_verified_stop_before_lease_finish(self):
        host, lease = Host(), Lease()
        observed = []
        def after_capture(path):
            observed.append((host.stops, len(lease.finishes), Path(path).name))
            return {"image": str(path / "image.bmp"), "imageSha256": "F" * 64}
        result = execute_armed_session(
            session=session("turn", keys=("a",), turn_hold_ms=100), review=review(),
            output=self.root / "turn-with-after-frame", host=host, lease=lease,
            feedback=Feedback([Sample(0, 0, 0, 1), Sample(0, 0, 0, 2)]),
            clock=lambda: 1.0, now=lambda: NOW, post_turn_capture=after_capture)
        self.assertEqual(observed, [(1, 0, "after-capture")])
        self.assertEqual(result["afterTurnCapture"]["status"], "captured")
        self.assertEqual(result["afterTurnCapture"]["imageSha256"], "F" * 64)
        self.assertEqual(result["beforeTurnCapture"]["imageSha256"], "B" * 64)
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_turn_does_not_capture_if_stop_is_unverified(self):
        host, lease = Host(stop_fails=True), Lease()
        called = []
        with self.assertRaisesRegex(MovementSessionError, "STOP"):
            execute_armed_session(
                session=session("turn", keys=("a",), turn_hold_ms=100),
                review=review(), output=self.root / "turn-stop-failed",
                host=host, lease=lease,
                feedback=Feedback([Sample(0, 0, 0, 1), Sample(0, 0, 0, 2)]),
                clock=lambda: 1.0, now=lambda: NOW,
                post_turn_capture=lambda path: called.append(path))
        self.assertEqual(called, [])
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_failed_after_turn_capture_does_not_replay_action(self):
        host, lease = Host(), Lease()
        def failed_capture(_path):
            self.assertEqual(host.stops, 1)
            self.assertEqual(lease.finishes, [])
            raise RuntimeError("after-frame capture unavailable")
        result = execute_armed_session(
            session=session("turn", keys=("a",), turn_hold_ms=100), review=review(),
            output=self.root / "turn-no-after-frame", host=host, lease=lease,
            feedback=Feedback([Sample(0, 0, 0, 1), Sample(0, 0, 0, 2)]),
            clock=lambda: 1.0, now=lambda: NOW, post_turn_capture=failed_capture)
        self.assertTrue(result["success"])
        self.assertEqual(result["afterTurnCapture"]["status"], "unavailable")
        self.assertIn("after-frame", result["afterTurnCapture"]["reason"])
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_turn_requires_valid_measured_hold_and_stops_on_failure(self):
        for index, observed in enumerate((None, 0, 20, 160, True, "100")):
            with self.subTest(observed=observed):
                host, lease = Host(), Lease()
                original_action = host.action
                def corrupted_action(action, output):
                    receipt = original_action(action, output)
                    if observed is None:
                        receipt["result"].pop("observedKeyHoldMilliseconds")
                    else:
                        receipt["result"]["observedKeyHoldMilliseconds"] = observed
                    return receipt
                host.action = corrupted_action
                with self.assertRaisesRegex(MovementSessionError,
                                            "turn measured hold is missing or drifted"):
                    execute_armed_session(
                        session=session("turn", keys=("a",), turn_hold_ms=100),
                        review=review(), output=self.root / f"turn-hold-{index}",
                        host=host, lease=lease,
                        feedback=Feedback([Sample(0, 0, 0, 1), Sample(0, 0, 0, 2)]),
                        clock=lambda: 1.0, now=lambda: NOW)
                self.assertEqual(len(host.actions), 1)
                self.assertEqual(host.stops, 1)
                self.assertEqual(lease.finishes[0][0], "failed")

    def test_turn_rejects_excess_translation_and_stops(self):
        host, lease = Host(), Lease()
        with self.assertRaisesRegex(MovementSessionError, "excessive planar"):
            execute_armed_session(
                session=session("turn", keys=("a",), turn_hold_ms=100), review=review(),
                output=self.root / "turn", host=host, lease=lease,
                feedback=Feedback([Sample(0, 0, 0, 1), Sample(.051, 0, 0, 2)]),
                clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(len(host.actions), 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_invalid_turn_key_or_hold_is_rejected_before_arm(self):
        for index, candidate in enumerate((
                session("turn", keys=("w",), turn_hold_ms=100),
                session("turn", keys=("a", "d"), turn_hold_ms=100),
                session("turn", keys=("a",), turn_hold_ms=151))):
            host, lease = Host(), Lease()
            with self.subTest(candidate=candidate), self.assertRaises(MovementSessionError):
                execute_armed_session(session=candidate, review=review(),
                    output=self.root / f"bad-turn-{index}", host=host, lease=lease,
                    feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
            self.assertEqual(host.arms, 0); self.assertEqual(host.actions, [])
            self.assertEqual(host.stops, 1); self.assertEqual(lease.finishes[0][0], "failed")

    def test_post_turn_workflow_requires_newer_same_identity_calibration(self):
        turn_path = self.root / "turn-result.json"
        profile_path = self.root / "post-turn-calibration.json"
        turn = {"success": True, "mode": "turn", "status": "turn-input-completed",
                "turnKey": "d", "headingClaimed": False,
                "samples": [Sample(10, 0, 20, 8).to_dict(), Sample(10.01, 0, 20, 9).to_dict()]}
        profile = {"schemaVersion": 1, "evidenceKind": "empirical-movement-calibration/1",
                   "mode": "calibration", "status": "calibrated", "movementDimension": "1d",
                   "calibrationIdentity": sample_identity(), "calibrationKeys": ["w"],
                   "calibrationEnd": Sample(10.5, 0, 20, 11).to_dict(),
                   "calibrations": {"w": {"key": "w", "dx_per_ms": .49 / 150,
                       "dz_per_ms": 0, "calibration_hold_ms": 150,
                       "horizontal_displacement": .49, "vertical_displacement": 0}},
                   "normalizedCross": None,
                   "samples": [Sample(10.01, 0, 20, 10).to_dict(),
                               Sample(10.5, 0, 20, 11).to_dict()]}
        turn_path.write_text(json.dumps(turn), encoding="utf-8")
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        require_post_turn_calibration(turn_path, profile_path)
        profile["samples"][0]["outerSequence"] = 9
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "newer producer feedback"):
            require_post_turn_calibration(turn_path, profile_path)

        profile["samples"][0] = Sample(10.01, 0, 20, 10).to_dict()
        profile["samples"][0]["addonSequence"] = 9
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "newer producer feedback"):
            require_post_turn_calibration(turn_path, profile_path)

        profile["samples"][0] = Sample(10.01, 0, 20, 10).to_dict()
        profile["samples"][0]["addonClock"] = 9.0
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "newer producer feedback"):
            require_post_turn_calibration(turn_path, profile_path)

    def test_post_turn_workflow_rejects_foreign_or_moved_calibration(self):
        turn_path = self.root / "turn-result.json"
        profile_path = self.root / "post-turn-calibration.json"
        turn = {"success": True, "mode": "turn", "status": "turn-input-completed",
                "turnKey": "a", "headingClaimed": False,
                "samples": [Sample(0, 0, 0, 1).to_dict(), Sample(0, 0, 0, 2).to_dict()]}
        start = Sample(.11, 0, 0, 3).to_dict()
        profile = {"samples": [start, Sample(.5, 0, 0, 4).to_dict()]}
        turn_path.write_text(json.dumps(turn), encoding="utf-8")
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "moved away"):
            require_post_turn_calibration(turn_path, profile_path)
        profile["samples"][0] = Sample(0, 0, 0, 3).to_dict()
        profile["samples"][0]["readerNonce"] = "other-reader"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "identity differs"):
            require_post_turn_calibration(turn_path, profile_path)

    def test_explicit_1d_goal_uses_only_positive_measured_vector(self):
        profile = self.root / "profile-1d.json"
        document = {"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "movementDimension": "1d", "normalizedCross": None,
            "calibrationIdentity": sample_identity(), "calibrationKeys": ["s"],
            "calibrationEnd": {"xyz": {"x": 0, "y": 0, "z": 0}},
            "calibrations": {"s": {"key": "s", "dx_per_ms": .4 / 150,
                "dz_per_ms": 0, "calibration_hold_ms": 150,
                "horizontal_displacement": .4, "vertical_displacement": 0}}}
        profile.write_text(json.dumps(document), encoding="utf-8")
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.4, 0, 0, 2),
                             Sample(.8, 0, 0, 3), Sample(.8, 0, 0, 4)])
        result = execute_armed_session(
            session=session("movement", profile, {"x": 1, "y": 0, "z": 0},
                            keys=("s",), dimension="1d"),
            review=review(), output=self.root / "run", host=host, lease=lease,
            feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(result["movementDimension"], "1d")
        self.assertEqual([action.key for action in host.actions], ["s", "s"])
        self.assertEqual(result["feedbackIterations"], 2)

    def test_1d_goal_allows_one_action_arrival_but_rejects_off_axis(self):
        profile = self.root / "profile-1d.json"
        document = {"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "movementDimension": "1d", "normalizedCross": None,
            "calibrationIdentity": sample_identity(), "calibrationKeys": ["s"],
            "calibrationEnd": {"xyz": {"x": 0, "y": 0, "z": 0}},
            "calibrations": {"s": {"key": "s", "dx_per_ms": .4 / 150,
                "dz_per_ms": 0, "calibration_hold_ms": 150,
                "horizontal_displacement": .4, "vertical_displacement": 0}}}
        profile.write_text(json.dumps(document), encoding="utf-8")
        host, lease = Host(), Lease()
        result = execute_armed_session(
            session=session("movement", profile, {"x": .31, "y": 0, "z": 0},
                            keys=("s",), dimension="1d"),
            review=review(), output=self.root / "one-action-1d", host=host,
            lease=lease, feedback=Feedback([Sample(0, 0, 0, 1),
                                            Sample(.31, 0, 0, 2),
                                            Sample(.31, 0, 0, 3)]),
            clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(result["feedbackIterations"], 1)
        self.assertEqual(len(host.actions), 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

        for index, goal in enumerate(({"x": 1, "y": 0, "z": .06},)):
            host, lease = Host(), Lease()
            with self.subTest(goal=goal), self.assertRaises(MovementSessionError):
                execute_armed_session(
                    session=session("movement", profile, goal, keys=("s",), dimension="1d"),
                    review=review(), output=self.root / f"run-{index}", host=host,
                    lease=lease, feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
            self.assertEqual(host.arms, 0); self.assertEqual(host.actions, [])

    def test_1d_goal_rejects_in_tolerance_or_minimum_pulse_overshoot_before_arm(self):
        base = {"schemaVersion": 1, "evidenceKind": "empirical-movement-calibration/1",
            "mode": "calibration", "status": "calibrated", "movementDimension": "1d",
            "normalizedCross": None, "calibrationIdentity": sample_identity(),
            "calibrationKeys": ["s"], "calibrationEnd": {"xyz": {"x": 0, "y": 0, "z": 0}}}
        cases = (
            ("in-tolerance", {"key": "s", "dx_per_ms": .01, "dz_per_ms": 0,
                              "calibration_hold_ms": 100, "horizontal_displacement": 1,
                              "vertical_displacement": 0}, {"x": .3, "y": 0, "z": 0},
             "arrival tolerance"),
            ("overshoot", {"key": "s", "dx_per_ms": .1, "dz_per_ms": 0,
                            "calibration_hold_ms": 20, "horizontal_displacement": 2,
                            "vertical_displacement": 0}, {"x": .5, "y": 0, "z": 0},
             "no bounded 1d pulse"),
        )
        for name, vector, goal, message in cases:
            profile = self.root / f"profile-{name}.json"
            profile.write_text(json.dumps({**base, "calibrations": {"s": vector}}),
                               encoding="utf-8")
            host, lease = Host(), Lease()
            with self.subTest(name=name), self.assertRaisesRegex(MovementSessionError, message):
                execute_armed_session(session=session("movement", profile, goal,
                    keys=("s",), dimension="1d"), review=review(),
                    output=self.root / f"run-{name}", host=host, lease=lease,
                    feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
            self.assertEqual(host.arms, 0)
            self.assertEqual(host.actions, [])

    def test_initial_in_tolerance_cannot_succeed_without_action_feedback(self):
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"schemaVersion": 1,
            "evidenceKind": "empirical-movement-calibration/1", "mode": "calibration",
            "status": "calibrated", "normalizedCross": 1.0, "calibrationKeys": ["w", "q"],
            "calibrationIdentity": sample_identity(),
            "calibrations": {
                "w": {"key": "w", "dx_per_ms": .005, "dz_per_ms": 0,
                      "calibration_hold_ms": 150, "horizontal_displacement": .75,
                      "vertical_displacement": 0},
                "q": {"key": "q", "dx_per_ms": 0, "dz_per_ms": .005,
                      "calibration_hold_ms": 150, "horizontal_displacement": .75,
                      "vertical_displacement": 0}}}), encoding="utf-8")
        host, lease, feedback = Host(), Lease(), Feedback([Sample(0, 0, 0, 1)])
        with self.assertRaisesRegex(MovementSessionError, "post-action feedback"):
            execute_armed_session(session=session("movement", profile, {"x": 0, "y": 0, "z": 0}),
                review=review(), output=self.root / "run", host=host, lease=lease,
                feedback=feedback, clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.actions, []); self.assertEqual(feedback.next_waits, 0)
        self.assertEqual(host.stops, 1); self.assertEqual(lease.finishes[0][0], "failed")

    def test_foreign_calibration_identity_is_rejected_before_arm(self):
        profile = self.root / "foreign.json"
        document = profile_document(); document["calibrationIdentity"]["lab"] = "lab2"
        profile.write_text(json.dumps(document), encoding="utf-8")
        host, lease = Host(), Lease()
        with self.assertRaisesRegex(MovementSessionError, "identity differs"):
            execute_armed_session(session=session("movement", profile,
                    {"x": 1, "y": 0, "z": 0}), review=review(), output=self.root / "run",
                    host=host, lease=lease, feedback=Feedback([Sample(0, 0, 0, 1)]),
                    clock=lambda: 1.0, now=lambda: NOW)
        self.assertEqual(host.arms, 0); self.assertEqual(host.actions, [])
        self.assertEqual(lease.finishes[0][0], "failed")

    def test_feedback_pin_target_must_match_reviewed_guest_target(self):
        pin = {"gameIdentity": dict(GAME_TARGET)}
        _require_feedback_target({"target": dict(GAME_TARGET)}, pin)
        pin["gameIdentity"]["processId"] = 999
        with self.assertRaisesRegex(MovementSessionError, "another game process"):
            _require_feedback_target({"target": dict(GAME_TARGET)}, pin)

    def test_calibration_accepts_late_final_feedback_without_late_input(self):
        elapsed = [0.0]

        class LateFinalFeedback(Feedback):
            def wait_after(self, completed, prior, timeout_seconds=3.0):
                result = super().wait_after(completed, prior, timeout_seconds)
                if self.waits == 2:
                    elapsed[0] = 13.0  # after both released input pulses
                return result

        host, lease = Host(), Lease()
        feedback = LateFinalFeedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2),
                                      Sample(.5, 0, .5, 3)])
        result = execute_armed_session(session=session("calibration"), review=review(),
            output=self.root / "late-final", host=host, lease=lease, feedback=feedback,
            clock=lambda: elapsed[0], now=lambda: NOW)
        self.assertEqual(result["status"], "calibrated")
        self.assertEqual(len(host.actions), 2)
        self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_calibration_cannot_send_another_key_after_elapsed_budget(self):
        elapsed = [0.0]

        class LateFirstFeedback(Feedback):
            def wait_after(self, completed, prior, timeout_seconds=3.0):
                result = super().wait_after(completed, prior, timeout_seconds)
                if self.waits == 1:
                    elapsed[0] = 13.0
                return result

        host, lease = Host(), Lease()
        feedback = LateFirstFeedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2),
                                      Sample(.5, 0, .5, 3)])
        with self.assertRaisesRegex(MovementSessionError, "elapsed budget"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "late-first", host=host, lease=lease, feedback=feedback,
                clock=lambda: elapsed[0], now=lambda: NOW)
        self.assertEqual(len(host.actions), 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")


if __name__ == "__main__":
    unittest.main()
