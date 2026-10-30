from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_movement_session import (
    MovementSessionError, _require_feedback_target, build_parser, calibrated_relative_goal,
    execute_armed_session, require_post_turn_calibration, sha,
    validate_session_pins,
)
from scripts.movement_controller import MovementError


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
        self.on_next = None
    def read(self, _label): return next(self.samples)
    def wait_initial(self, timeout_seconds=4.5):
        self.initial_timeouts.append(timeout_seconds)
        return next(self.samples)
    def wait_after(self, _completed, _prior, timeout_seconds=3.0):
        self.waits += 1; self.wait_timeouts.append(timeout_seconds)
        if self.failure is not None: raise self.failure
        return next(self.samples)
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
    def __init__(self, ambiguous=False, arm_expired=False, stop_fails=False):
        self.ambiguous = ambiguous; self.arm_expired = arm_expired
        self.stop_fails = stop_fails
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
                            "stateUncertain": self.ambiguous},
                "recoveryRequired": self.ambiguous,
                "completedAtUtc": NOW.isoformat()}
    def stop(self):
        self.stops += 1
        return {"stopped": not self.stop_fails, "recoveryRequired": self.stop_fails}


def session(mode, profile=None, goal=None, keys=("w", "q"), dimension="2d",
            turn_hold_ms=None):
    return {"sessionId": "a" * 32, "sessionPlanSha256": "A" * 64,
            "mode": mode, "capture": {"captureId": "c" * 32, "capture": "capture.json"},
            "captureImageSha256": "B" * 64, "calibrationProfile": str(profile) if profile else None,
            "goal": goal, "allowedKeys": list(keys), "target": dict(GAME_TARGET),
            "movementDimension": dimension, "turnHoldMs": turn_hold_ms}


def review():
    return {"schemaVersion": 1, "decision": "approve", "sessionId": "a" * 32,
            "sessionPlanSha256": "A" * 64, "captureId": "c" * 32,
            "captureImageSha256": "B" * 64, "note": "Reviewed bounded empty-world movement batch."}


class MovementSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

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

    def test_calibration_arms_once_and_measures_only_reviewed_w_q(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2), Sample(.5, 0, .5, 3)])
        result = execute_armed_session(session=session("calibration"), review=review(),
            output=self.root / "run", host=host, lease=lease, feedback=feedback,
            clock=lambda: 1.0, now=lambda: NOW)
        self.assertTrue(result["success"]); self.assertEqual(result["status"], "calibrated")
        self.assertEqual([a.key for a in host.actions], ["w", "q"])
        self.assertEqual(feedback.initial_timeouts, [4.5])
        self.assertEqual(feedback.wait_timeouts, [6.0, 6.0])
        self.assertEqual(host.arms, 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

    def test_armed_run_clock_does_not_include_prearm_setup(self):
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2),
                             Sample(.5, 0, .5, 3)])
        result = execute_armed_session(session=session("calibration"), review=review(),
            output=self.root / "run", host=host, lease=lease, feedback=feedback,
            clock=lambda: 0.0 if host.arms == 1 else (_ for _ in ()).throw(
                AssertionError("run clock sampled before ARM")), now=lambda: NOW)
        self.assertTrue(result["success"])

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
        ticks = iter((0.0, 1.0, 4.0, 5.0, 9.0))
        result = execute_armed_session(session=session("movement", profile,
                    {"x": 1.2, "y": 0, "z": 0}), review=review(),
                    output=self.root / "run", host=host, lease=lease, feedback=feedback,
                    clock=lambda: next(ticks), now=lambda: NOW)
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
        files[4].write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(MovementSessionError, "turn result changed"):
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
        self.assertFalse(result["headingClaimed"])
        self.assertEqual(result["profileInvalidationScope"],
                         "explicit-after-turn-result-chain-only")
        self.assertEqual(result["nextStep"],
                         "review a fresh screenshot before forward calibration")
        self.assertEqual([(action.key, action.hold_ms) for action in host.actions], [("d", 100)])
        self.assertEqual(feedback.wait_timeouts, [6.0])
        self.assertEqual(host.arms, 1); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "succeeded")

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
            session=session("movement", profile, {"x": .61, "y": 0, "z": 0},
                            keys=("s",), dimension="1d"),
            review=review(), output=self.root / "one-action-1d", host=host,
            lease=lease, feedback=Feedback([Sample(0, 0, 0, 1),
                                            Sample(.4, 0, 0, 2),
                                            Sample(.4, 0, 0, 3)]),
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

    def test_calibration_cannot_succeed_after_elapsed_budget(self):
        ticks = iter((0.0, 0.0, 0.0, 0.0, 13.0))
        host, lease = Host(), Lease()
        feedback = Feedback([Sample(0, 0, 0, 1), Sample(.5, 0, 0, 2),
                             Sample(.5, 0, .5, 3)])
        with self.assertRaisesRegex(MovementSessionError, "elapsed budget"):
            execute_armed_session(session=session("calibration"), review=review(),
                output=self.root / "run", host=host, lease=lease, feedback=feedback,
                clock=lambda: next(ticks), now=lambda: NOW)
        self.assertEqual(len(host.actions), 2); self.assertEqual(host.stops, 1)
        self.assertEqual(lease.finishes[0][0], "failed")


if __name__ == "__main__":
    unittest.main()
