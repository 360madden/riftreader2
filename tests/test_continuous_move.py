import io
from copy import deepcopy
import json
import math
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from contextlib import nullcontext, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import continuous_move as move


@dataclass
class Position:
    x: float = 0
    y: float = 10
    z: float = 0


class Adapter:
    host = "AMD-DESKTOP"
    pid = 123
    unit_key = "456"
    target = {"processStartUtcTicks": "789", "executableSha256": "a" * 64, "hwnd": 99}
    binding = {"runtimeIdentity": {"machine": host, "processId": pid,
               "processStartUtcTicks": "789", "gameBuildSha256": "a" * 64, "unitKey": unit_key}}

    def __init__(self, root):
        self.input_receipt_path = root / "inputs.jsonl"
        self.last_input_receipt = None
        self.reservations = 0

    def reserve(self):
        self.reservations += 1
        return nullcontext(SimpleNamespace(check=lambda: None))


def receipt(status="arrived", *, reason=None):
    value = {"status": status, "reason": reason,
             "target": {"machineName": "AMD-DESKTOP", "processId": 123,
                        "processStartUtcTicks": "789", "executableSha256": "a" * 64,
                        "windowHandle": "0x63"},
             "playerKey": "456", "goal": {"x": 100.0, "z": 0.0},
             "position": {"x": 100.0 if status == "arrived" else 5.0, "y": 10.0, "z": 0.0},
             "bodyBearingDegreesCandidate": 90.0, "initialDistance": 100.0,
             "finalDistance": 0.1 if status == "arrived" else 95.0, "readCount": 10,
             "path": [{"x": 100.0, "y": 10.0, "z": 0.0, "bearing": 90.0,
                       "distance": 0.1, "observedAtUtc": "2026-11-14T12:00:00.0000000Z"}],
             "elapsedMilliseconds": 1000, "inputSent": status != "blocked",
             "releaseSucceeded": True, "keySendEvents": [
                 {"key": "W", "phase": "key-down", "callStartedAtUtc": "2026-11-14T12:00:00Z",
                  "callCompletedAtUtc": "2026-11-14T12:00:00.010000Z", "inserted": True},
                 {"key": "W", "phase": "key-up", "callStartedAtUtc": "2026-11-14T12:00:00.510000Z",
                  "callCompletedAtUtc": "2026-11-14T12:00:00.520000Z", "inserted": True}],
             "releaseFallbacks": 0,
             "desktopInputsDown": [], "stopFile": "STOP", "owner": {
                 "processId": 55, "processStartUtcTicks": "66"},
             "watchdog": {"poseTimeoutMilliseconds": 800, "pollMilliseconds": 25,
                          "maxSeconds": 1800}}
    return value


def recovery_receipt(key):
    return {"status": "windows-keyup-inserted-game-state-unverified",
            "machine": "AMD-DESKTOP", "processId": 123,
            "processStartUtcTicks": "789", "executableSha256": "a" * 64,
            "keys": [key], "releaseOnly": True, "keyDownAttempts": 0,
            "keySendEvents": [{"key": key, "phase": "key-up", "inserted": True}],
            "desktopInputsDown": [], "gameResponseVerified": False}


def successful_recovery(command, **kwargs):
    key = command[command.index("--key") + 1]
    return SimpleNamespace(returncode=0, stdout=json.dumps(recovery_receipt(key)), stderr="")


class FakeProcess:
    def __init__(self, command, final, *, polls=0):
        self.command, self._remaining, self.returncode = command, polls, None
        self.stdout = io.StringIO(json.dumps(final))
        self.stderr = io.StringIO("")

    def poll(self):
        if self._remaining:
            self._remaining -= 1
            return None
        if self.returncode is None:
            status = json.loads(self.stdout.getvalue())["status"]
            self.returncode = 0 if status in ("arrived", "stopped") else 2 if status == "blocked" else 3
        return self.returncode


class ContinuousMoveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = __import__("tempfile").TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.adapter = Adapter(self.root)
        self.start = SimpleNamespace(position=Position(), bearing=0.0, acquired=time.monotonic(), source="fresh")

    def tearDown(self): self.temporary.cleanup()

    def run_move(self, final, stop=None, polls=0, recovery_run=successful_recovery):
        stop_path = self.root / "owned.stop"
        final["stopFile"] = str(stop_path.absolute())
        processes = []
        def popen(command, **kwargs):
            child = FakeProcess(command, final, polls=polls); processes.append(child); return child
        events = []
        settled = SimpleNamespace(position=Position(100, 10, 0), bearing=90.0,
                                  acquired=time.monotonic(), source="fresh-after-release")
        with patch("scripts.physical_waypoints.read_stationary", side_effect=[self.start, settled]):
            result = move.move_to(self.adapter, 100, 0, stop or threading.Event(), events.append,
                                  popen=popen, native_exe=self.root / "native.exe",
                                  owner_identity=(55, 66), stop_path=stop_path,
                                  recovery_run=recovery_run)
        return result, events, processes[0], stop_path

    def test_arrival_uses_exact_pins_retains_receipt_and_emits_state(self):
        result, events, child, stop_path = self.run_move(receipt())
        self.assertEqual(("moving", "arrived"), (events[0]["status"], events[-1]["status"]))
        self.assertEqual((0.0, 1, 90.0, 500.0),
                         (result["distance"], result["pulses"], result["bearing"],
                          result["heldInputMilliseconds"]))
        self.assertEqual(result["observedAtUtc"], "2026-11-14T12:00:00.0000000Z")
        self.assertIn("acquired", result)
        self.assertFalse(stop_path.exists())
        command = child.command
        for pair in (("--expected-host", "AMD-DESKTOP"), ("--pid", "123"),
                     ("--expect-start-ticks", "789"), ("--expect-sha256", "a" * 64),
                     ("--expect-hwnd", "0x63"), ("--expect-player-key", "456"),
                     ("--owner-pid", "55"), ("--owner-start-ticks", "66"),
                     ("--max-seconds", "1800")):
            self.assertEqual(command[command.index(pair[0]) + 1], pair[1])
        self.assertEqual((1, "native-continuous-move", "arrived"),
                         (self.adapter.last_input_receipt["version"],
                          self.adapter.last_input_receipt["kind"],
                          self.adapter.last_input_receipt["status"]))
        self.assertEqual(json.loads(self.adapter.input_receipt_path.read_text()), self.adapter.last_input_receipt)
        self.assertNotIn("--goal-y", command)
        self.assertNotIn("y", self.adapter.last_input_receipt["goal"])

    def test_explicit_goal_height_is_pinned_and_freshly_rechecked(self):
        final = receipt()
        final["goal"]["y"] = 10.0
        stop_path = self.root / "height.stop"
        final["stopFile"] = str(stop_path.absolute())
        children = []
        settled = SimpleNamespace(position=Position(100, 10, 0), bearing=90.0,
                                  acquired=time.monotonic(), source="fresh-after-release")
        with patch("scripts.physical_waypoints.read_stationary",
                   side_effect=[self.start, settled]):
            result = move.move_to(
                self.adapter, 100, 0, threading.Event(),
                popen=lambda command, **kwargs: children.append(
                    FakeProcess(command, final)) or children[-1],
                native_exe=self.root / "native.exe", owner_identity=(55, 66),
                stop_path=stop_path, goal_y=10)
        command = children[0].command
        self.assertEqual("10.0", command[command.index("--goal-y") + 1])
        self.assertEqual(10.0, self.adapter.last_input_receipt["goal"]["y"])
        self.assertEqual(10.0, result["goal"]["y"])
        self.assertEqual(10, result["position"]["y"])

    def test_explicit_goal_height_rejects_fresh_off_height_pose(self):
        final = receipt()
        final["goal"]["y"] = 10.0
        stop_path = self.root / "off-height.stop"
        final["stopFile"] = str(stop_path.absolute())
        off_height = SimpleNamespace(position=Position(100, 10.51, 0), bearing=90.0,
                                     acquired=time.monotonic(), source="fresh-after-release")
        with patch("scripts.physical_waypoints.read_stationary",
                   side_effect=[self.start, off_height]), \
             self.assertRaisesRegex(Exception, "destination height"):
            move.move_to(
                self.adapter, 100, 0, threading.Event(),
                popen=lambda command, **kwargs: FakeProcess(command, final),
                native_exe=self.root / "native.exe", owner_identity=(55, 66),
                stop_path=stop_path, goal_y=10)
        self.assertEqual("arrived", self.adapter.last_input_receipt["status"])

    def test_nonfinite_goal_height_never_reads_or_launches(self):
        with patch("scripts.physical_waypoints.read_stationary") as read, \
             patch("subprocess.Popen") as popen, \
             self.assertRaisesRegex(ValueError, "goal Y must be finite"):
            move.move_to(self.adapter, 1, 2, threading.Event(), goal_y=float("nan"))
        read.assert_not_called()
        popen.assert_not_called()

    def test_stop_file_created_only_after_stop_and_stopped_receipt_retained(self):
        stopped = threading.Event()
        final = receipt("stopped", reason="operator STOP")
        stop_path = self.root / "owned.stop"; final["stopFile"] = str(stop_path.absolute())
        created = []
        class StoppingProcess(FakeProcess):
            def poll(self):
                if not stopped.is_set(): stopped.set()
                if stop_path.exists(): return super().poll()
                return None
        def popen(command, **kwargs):
            child = StoppingProcess(command, final); created.append(child); return child
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start):
            with self.assertRaisesRegex(move.ContinuousStopped, "operator STOP") as caught:
                move.move_to(self.adapter, 100, 0, stopped, popen=popen,
                             native_exe=self.root / "native.exe", owner_identity=(55, 66),
                             stop_path=stop_path)
        self.assertTrue(stop_path.exists())
        from scripts.physical_waypoints import Stopped
        self.assertIsInstance(caught.exception, Stopped)
        self.assertEqual("stopped", caught.exception.receipt["status"])
        self.assertTrue(caught.exception.receipt["releaseSucceeded"])
        self.assertEqual(final["path"], caught.exception.receipt["path"])
        self.assertEqual(self.adapter.last_input_receipt["status"], "stopped")

    def test_stop_racing_post_arrival_verification_never_emits_arrived(self):
        stopped = threading.Event()
        final = receipt("arrived")
        stop_path = self.root / "arrival-race.stop"
        final["stopFile"] = str(stop_path.absolute())
        events = []
        settled = SimpleNamespace(position=Position(100, 10, 0), bearing=90.0,
                                  acquired=time.monotonic(), source="fresh-after-release")
        def second_read(*args, **kwargs):
            stopped.set()
            return settled
        # Use a callable side effect so STOP changes during the second read.
        def read_side_effect(*args, **kwargs):
            if read_side_effect.calls == 0:
                read_side_effect.calls += 1
                return self.start
            return second_read()
        read_side_effect.calls = 0
        with patch("scripts.physical_waypoints.read_stationary", side_effect=read_side_effect):
            with self.assertRaisesRegex(Exception, "post-arrival verification"):
                move.move_to(self.adapter, 100, 0, stopped, events.append,
                    popen=lambda command, **kwargs: FakeProcess(command, final),
                    native_exe=self.root / "native.exe", owner_identity=(55, 66),
                    stop_path=stop_path, recovery_run=successful_recovery)
        self.assertEqual([event["status"] for event in events], ["moving"])
        self.assertEqual(self.adapter.last_input_receipt["status"], "arrived")

    def test_trusted_native_encounter_interrupt_bridges_without_operator_stop(self):
        for reason in ("survival-combat", "survival-hp-drop"):
            with self.subTest(reason=reason):
                final = receipt("halted", reason=reason)
                final["survivalInterrupt"] = True
                final["survivalSnapshot"] = {
                    "status": "available-candidate", "healthCurrent": 99,
                    "healthMaximum": 100, "combatCandidate": reason == "survival-combat",
                    "rawCombat": 1 if reason == "survival-combat" else 0}
                stop = threading.Event()
                stop_path = self.root / (reason + ".stop")
                final["stopFile"] = str(stop_path.absolute())
                children = []
                def launch(command, **kwargs):
                    child = FakeProcess(command, final); children.append(child); return child
                with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
                     self.assertRaises(move.EncounterInterrupted) as caught:
                    move.move_to(self.adapter, 100, 0, stop, popen=launch,
                        native_exe=self.root / "native.exe", owner_identity=(55, 66),
                        stop_path=stop_path, survival_guard=True)
                self.assertFalse(stop.is_set())
                self.assertFalse(stop_path.exists())
                self.assertIn("--survival-interrupt", children[0].command)
                self.assertEqual(reason, caught.exception.receipt["reason"])
                self.assertEqual("halted", caught.exception.receipt["status"])
                self.assertEqual(final["survivalSnapshot"],
                                 caught.exception.receipt["survivalSnapshot"])
                self.assertTrue(caught.exception.receipt["releaseSucceeded"])
                self.assertTrue(self.adapter._continuous_move_receipt_trusted)
                self.assertFalse(self.adapter._continuous_input_release_fault)
                self.assertEqual(reason, self.adapter.last_input_receipt["reason"])

    def test_operator_stop_wins_race_with_trusted_encounter_interrupt(self):
        from scripts.physical_waypoints import Stopped
        final = receipt("halted", reason="survival-combat")
        stop = threading.Event()
        stop_path = self.root / "stop-wins-encounter.stop"
        final["stopFile"] = str(stop_path.absolute())
        children = []
        def launch(command, **kwargs):
            stop.set()
            child = FakeProcess(command, final); children.append(child); return child
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             self.assertRaises(Stopped):
            move.move_to(self.adapter, 100, 0, stop, popen=launch,
                native_exe=self.root / "native.exe", owner_identity=(55, 66),
                stop_path=stop_path, survival_guard=True)
        self.assertIn("--survival-interrupt", children[0].command)
        self.assertTrue(self.adapter.last_input_receipt["releaseSucceeded"])
        self.assertFalse(self.adapter._continuous_input_release_fault)

    def test_dead_and_unavailable_survival_halts_remain_ordinary_critical_failures(self):
        from scripts.physical_waypoints import WaypointError
        for reason in ("survival-dead", "survival-unavailable"):
            with self.subTest(reason=reason):
                final = receipt("halted", reason=reason)
                stop_path = self.root / (reason + ".stop")
                final["stopFile"] = str(stop_path.absolute())
                children = []
                def launch(command, **kwargs):
                    child = FakeProcess(command, final); children.append(child); return child
                with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
                     self.assertRaisesRegex(WaypointError, reason):
                    move.move_to(self.adapter, 100, 0, threading.Event(), popen=launch,
                        native_exe=self.root / "native.exe", owner_identity=(55, 66),
                        stop_path=stop_path, survival_guard=True)
                self.assertIn("--survival-interrupt", children[0].command)
                self.assertEqual(reason, self.adapter.last_input_receipt["reason"])
                self.assertTrue(self.adapter.last_input_receipt["releaseSucceeded"])
                self.assertFalse(self.adapter._continuous_input_release_fault)

    def test_preset_stop_and_far_goal_never_launch(self):
        for stopped, goal, reason in ((True, 1, "Stopped"), (False, 1001, "exceeds 1000")):
            with self.subTest(reason=reason), patch("scripts.physical_waypoints.read_stationary",
                    return_value=self.start), patch("subprocess.Popen") as popen:
                event = threading.Event()
                if stopped: event.set()
                with self.assertRaisesRegex(Exception, reason):
                    move.move_to(self.adapter, goal, 0, event, popen=popen,
                                 owner_identity=(55, 66), stop_path=self.root / (reason + ".stop"))
                popen.assert_not_called()

    def test_identity_mismatch_fails_after_retaining_no_untrusted_receipt(self):
        final = receipt(); final["playerKey"] = "other"
        with self.assertRaisesRegex(Exception, "key-up recovery verified"):
            self.run_move(final)
        self.assertIsNone(self.adapter.last_input_receipt)
        recovery = self.adapter._continuous_move_recovery
        self.assertTrue(recovery["releaseSucceeded"])
        self.assertEqual([item["key"] for item in recovery["keys"]], ["w", "a", "d"])

    def test_reviewed_origin_is_checked_before_launch_and_pinned_for_native_recheck(self):
        final = receipt()
        stop_path = self.root / "origin.stop"; final["stopFile"] = str(stop_path.absolute())
        children = []
        def popen(command, **kwargs):
            child = FakeProcess(command, final); children.append(child); return child
        settled = SimpleNamespace(position=Position(100, 10, 0), bearing=90.0,
                                  acquired=time.monotonic(), source="fresh-after-release")
        with patch("scripts.physical_waypoints.read_stationary", side_effect=[self.start, settled]):
            result = move.move_to(self.adapter, 100, 0, threading.Event(), popen=popen,
                         native_exe=self.root / "native.exe", owner_identity=(55, 66),
                         stop_path=stop_path, expected_origin={"x": 0, "z": 0, "bearing": 0})
        command = children[0].command
        self.assertEqual((command[command.index("--expect-x") + 1],
                          command[command.index("--expect-z") + 1],
                          command[command.index("--expect-bearing") + 1]),
                         ("0.0", "0.0", "0.0"))
        self.assertEqual(result["motionMode"], "held-forward")
        self.assertIn("not started", result["autorunQualification"])
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch("subprocess.Popen") as rejected:
            with self.assertRaisesRegex(Exception, "reviewed movement origin"):
                move.move_to(self.adapter, 100, 0, threading.Event(), popen=rejected,
                             owner_identity=(55, 66), stop_path=self.root / "stale.stop",
                             expected_origin={"x": .06, "z": 0, "bearing": 0})
            rejected.assert_not_called()

    def test_all_terminal_receipts_require_release_and_empty_pressed_inputs(self):
        for status in ("arrived", "stopped", "halted", "blocked"):
            for field, value in (("releaseSucceeded", False), ("desktopInputsDown", ["W"]),
                                 ("desktopInputsDown", False)):
                final = receipt(status, reason="terminal")
                final[field] = value
                if status == "blocked":
                    final.update(target=None, playerKey=None, position=None,
                                 bodyBearingDegreesCandidate=None, initialDistance=None,
                                 finalDistance=None, path=[])
                with self.subTest(status=status, field=field, value=value), \
                     self.assertRaisesRegex(Exception, "release is not verified"):
                    self.run_move(final)

    def test_rejected_release_retains_bounded_untrusted_diagnostic_before_recovery(self):
        final = receipt()
        final["releaseSucceeded"] = False
        final["desktopInputsDown"] = ["mouse-left"]
        final["diagnosticPadding"] = "x" * 40_000

        with self.assertRaisesRegex(Exception, "release is not verified.*recovery verified"):
            self.run_move(final)

        rows = [json.loads(line) for line in
                self.adapter.input_receipt_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(2, len(rows))
        rejected, recovery = rows
        self.assertEqual("native-continuous-move-untrusted", rejected["kind"])
        self.assertIs(rejected["trusted"], False)
        self.assertEqual("rejected", rejected["status"])
        self.assertEqual(0, rejected["childExitCode"])
        self.assertIn("release is not verified", rejected["validationError"])
        self.assertEqual({"status": "arrived", "reason": None,
                          "inputSent": True, "inputSentType": "bool",
                          "releaseSucceeded": False, "releaseSucceededType": "bool",
                          "desktopInputsDown": ["mouse-left"],
                          "desktopInputsDownType": "list",
                          "desktopInputsDownTruncated": False},
                         rejected["parsedReleaseFields"])
        self.assertTrue(rejected["rawStdout"]["truncated"])
        self.assertGreater(rejected["rawStdout"]["originalCharacters"],
                           move._UNTRUSTED_OUTPUT_CHARACTERS)
        self.assertLessEqual(len(rejected["rawStdout"]["text"]),
                             move._UNTRUSTED_OUTPUT_CHARACTERS + 64)
        self.assertEqual("native-continuous-move-recovery", recovery["kind"])
        self.assertTrue(recovery["releaseSucceeded"])
        self.assertIsNone(self.adapter.last_input_receipt)
        self.assertFalse(self.adapter._continuous_move_receipt_trusted)
        self.assertEqual(self.adapter._continuous_move_untrusted, rejected)

    def test_blocked_before_first_pose_allows_null_pose_but_retains_trusted_receipt(self):
        final = receipt("blocked", reason="target unavailable")
        final.update(target=None, playerKey=None, position=None,
                     bodyBearingDegreesCandidate=None, initialDistance=None,
                     finalDistance=None, path=[])
        with self.assertRaisesRegex(Exception, "target unavailable"):
            self.run_move(final)
        self.assertEqual(("blocked", False),
                         (self.adapter.last_input_receipt["status"],
                          self.adapter.last_input_receipt["inputSent"]))

    def test_duplicate_native_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            move._parse_final('{"status":"arrived","status":"stopped"}')

    def test_stop_wait_keeps_ownership_until_native_publishes_release(self):
        stopped = threading.Event()
        final = receipt("stopped", reason="operator STOP")
        stop_path = self.root / "slow-stop.flag"; final["stopFile"] = str(stop_path.absolute())
        class SlowRelease(FakeProcess):
            after_stop = 3
            def poll(self):
                stopped.set()
                if not stop_path.exists(): return None
                if self.after_stop:
                    self.after_stop -= 1
                    return None
                return super().poll()
        events = []
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "_RELEASE_GRACE_SECONDS", 0):
            with self.assertRaisesRegex(Exception, "operator STOP"):
                move.move_to(self.adapter, 100, 0, stopped, events.append,
                    popen=lambda command, **kwargs: SlowRelease(command, final),
                    native_exe=self.root / "native.exe", owner_identity=(55, 66),
                    stop_path=stop_path)
        self.assertIn("stopping", [event["status"] for event in events])
        self.assertTrue(self.adapter.last_input_receipt["releaseSucceeded"])

    def test_cli_input_sent_is_false_before_launch_unknown_after_untrusted_launch(self):
        from scripts.physical_waypoints import Stopped, WaypointError
        def preset(*args, **kwargs):
            self.adapter._continuous_move_launched = False
            self.adapter._continuous_move_receipt_trusted = False
            raise Stopped("preset STOP")
        def invalid(*args, **kwargs):
            self.adapter._continuous_move_launched = True
            self.adapter._continuous_move_receipt_trusted = False
            raise WaypointError("invalid receipt after launch")
        def trusted_halt(*args, **kwargs):
            self.adapter._continuous_move_launched = True
            self.adapter._continuous_move_receipt_trusted = True
            self.adapter.last_input_receipt = {"status": "halted", "inputSent": True,
                                               "releaseSucceeded": True,
                                               "desktopInputsDown": []}
            raise WaypointError("native halt")
        def native_arrived_but_wrapper_rejects(*args, **kwargs):
            self.adapter._continuous_move_launched = True
            self.adapter._continuous_move_receipt_trusted = True
            self.adapter.last_input_receipt = {"status": "arrived", "inputSent": True,
                                               "releaseSucceeded": True,
                                               "desktopInputsDown": []}
            raise WaypointError("post-arrival pose did not confirm arrival")
        for implementation, status, input_sent in (
                (preset, "stopped", False), (invalid, "halted", None),
                (trusted_halt, "halted", True),
                (native_arrived_but_wrapper_rejects, "halted", True)):
            output = io.StringIO()
            with self.subTest(status=status), patch(
                    "scripts.physical_waypoints.PhysicalAdapter", return_value=self.adapter), \
                 patch.object(move, "move_to", side_effect=implementation), redirect_stdout(output):
                move.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                           "--x", "100", "--z", "0", "--execute", "--json"])
            result = json.loads(output.getvalue())
            self.assertEqual((status, input_sent), (result["status"], result["inputSent"]))

    def test_native_crash_runs_no_focus_exact_keyup_recovery_and_never_claims_success(self):
        class Crashed:
            returncode = -1073741819
            stdout = io.StringIO("")
            stderr = io.StringIO("native crash")
            def poll(self): return self.returncode
        commands = []
        def recover(command, **kwargs):
            commands.append(command)
            return successful_recovery(command, **kwargs)
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start):
            with self.assertRaisesRegex(Exception, "result unavailable.*key-up recovery verified"):
                move.move_to(self.adapter, 100, 0, threading.Event(),
                    popen=lambda *args, **kwargs: Crashed(),
                    native_exe=self.root / "native.exe", owner_identity=(55, 66),
                    stop_path=self.root / "crash.stop", recovery_run=recover)
        self.assertFalse(self.adapter._continuous_move_receipt_trusted)
        self.assertIsNone(self.adapter.last_input_receipt)
        self.assertEqual([command[command.index("--key") + 1] for command in commands],
                         ["w", "a", "d"])
        self.assertTrue(all("--no-focus" in command for command in commands))

    def test_untrusted_receipt_recovery_failure_remains_halted_and_unknown_input(self):
        def unsafe_recovery(command, **kwargs):
            key = command[command.index("--key") + 1]
            value = recovery_receipt(key)
            value["desktopInputsDown"] = ["W"]
            return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr="")
        final = receipt(); final["playerKey"] = "other"
        with self.assertRaisesRegex(Exception, "recovery is unverified"):
            self.run_move(final, recovery_run=unsafe_recovery)
        self.assertFalse(self.adapter._continuous_move_recovery["releaseSucceeded"])
        launched = Mock()
        with self.assertRaisesRegex(Exception, "cleanup remains unverified"):
            move.move_to(self.adapter, 100, 0, threading.Event(), popen=launched,
                         owner_identity=(55, 66), stop_path=self.root / "next.stop")
        launched.assert_not_called()
        with patch("scripts.physical_waypoints.read_stationary") as read:
            with self.assertRaisesRegex(Exception, "cleanup remains unverified"):
                move.run_continuous_route(self.adapter, [["Next", 100, 0]],
                                          threading.Event())
            read.assert_not_called()

        recovered = move.retry_release(self.adapter, native_exe=self.root / "native.exe",
                                       run=successful_recovery)
        self.assertTrue(recovered["releaseSucceeded"])
        self.assertFalse(self.adapter._continuous_input_release_fault)

    def test_stop_file_error_forces_bounded_exit_then_keyup_recovery(self):
        class Wedged:
            def __init__(self):
                self.returncode = None
                self.stdout, self.stderr = io.StringIO(""), io.StringIO("")
                self.killed = False
            def poll(self): return self.returncode
            def kill(self):
                self.killed = True
                self.returncode = -9
        child = Wedged()
        stopped = threading.Event(); stopped.set()
        # The preset STOP admission normally prevents launch, so set it only
        # once the child has been created and the mover loop is active.
        stopped.clear()
        def launch(*args, **kwargs):
            stopped.set()
            return child
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "_create_stop", side_effect=OSError("disk unavailable")), \
             patch.object(move, "_FORCED_EXIT_GRACE_SECONDS", 0):
            with self.assertRaisesRegex(Exception, "Could not publish native STOP.*recovery verified"):
                move.move_to(self.adapter, 100, 0, stopped, popen=launch,
                    native_exe=self.root / "native.exe", owner_identity=(55, 66),
                    stop_path=self.root / "unwritable.stop",
                    recovery_run=successful_recovery)
        self.assertTrue(child.killed)

    def test_continuous_route_over_twenty_units_uses_real_points_and_one_reservation(self):
        points = [[f"Point {index}", index * 2, 0] for index in range(31)]
        events, calls = [], []
        entry = Mock()
        def one_leg(adapter, x, z, stop, emit, **kwargs):
            calls.append((x, z, kwargs["reservation"], kwargs["max_seconds"],
                          kwargs["goal_y"], kwargs["path_points"]))
            adapter.last_input_receipt = {"version": 1, "status": "arrived"}
            for index, guide in enumerate(kwargs["path_points"]):
                emit({"status": "passed", "index": index, "name": guide["name"],
                      "goal": guide, "position": {"x": guide["x"], "y": guide.get("y", 10), "z": guide["z"]},
                      "releaseSucceeded": True, "desktopInputsDown": [], "passageVerified": True})
            result = {"status": "arrived", "name": "CLI destination",
                      "start": {"x": x - 2, "y": 10, "z": z},
                      "goal": {"x": x, "y": 10, "z": z},
                      "position": {"x": x, "y": 10, "z": z}, "bearing": 90,
                      "distance": 0, "pulses": 2, "elapsedMilliseconds": 100,
                      "heldInputMilliseconds": 75}
            adapter.last_input_receipt = {"version": 1, "status": "arrived"}
            emit(result)
            return result
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to", side_effect=one_leg):
            legs = move.run_continuous_route(self.adapter, points, threading.Event(),
                                             events.append, entry_check=entry,
                                             goal_heights=[10 + index / 10
                                                           for index in range(len(points))])
        self.assertEqual((31, 1, 1), (len(legs), len(calls), self.adapter.reservations))
        self.assertEqual([row["name"] for row in legs], [row[0] for row in points])
        self.assertEqual([event["name"] for event in events], [row[0] for row in points])
        self.assertTrue(all(call[2] is calls[0][2] for call in calls))
        self.assertEqual([10 + index / 10 for index in range(len(points))],
                         [guide["y"] for guide in calls[0][5]] + [calls[0][4]])
        self.assertEqual((75, .1), (legs[-1]["totalHoldMs"], legs[-1]["elapsedSeconds"]))
        entry.assert_called_once_with(self.start.position)

    def test_corner_planner_splits_sharp_bend_but_not_gentle_or_collinear(self):
        sharp = [("A", 0, 0), ("B", 10, 0), ("C", 10, 10)]
        gentle = [("A", 0, 0), ("B", 10, 0), ("C", 19.063, 4.226)]
        dense = [(str(i), i * .1, 0) for i in range(40)]
        for rows, expected in ((sharp, [(0, 1, True), (2, 2, False)]),
                               (gentle, [(0, 2, False)]),
                               (dense, [(0, 39, False)])):
            with self.subTest(rows=rows):
                self.assertEqual(expected, move.route_spans(rows, [None]*len(rows),
                                                            ["pass"]*len(rows)))

    def test_measured_response_can_increase_corner_runout(self):
        rows = [("A", 0, 0), ("B", .8, 0),
                ("C", .8 + .8*math.cos(math.radians(25)), .8*math.sin(math.radians(25)))]
        self.assertEqual([(0, 2, False)], move.route_spans(rows, [None]*3, ["pass"]*3))
        self.assertEqual([(0, 1, True), (2, 2, False)],
                         move.route_spans(rows, [None]*3, ["pass"]*3, response_delay=.4))
        self.assertEqual([(0, 1, True), (2, 2, False)],
                         move.route_spans(rows, [None]*3, ["pass"]*3, observed_coast=.5))

    def test_sampled_feasible_curve_remains_continuous(self):
        rows = [(str(i), 4 * math.sin(i * .16), 4 * (1-math.cos(i * .16)))
                for i in range(12)]
        self.assertEqual([(0, 11, False)],
                         move.route_spans(rows, [None]*12, ["pass"]*12))

    def test_motion_seed_uses_slower_turn_and_faster_calibrated_speed(self):
        adapter = SimpleNamespace(
            calibrations=lambda _: {"w": SimpleNamespace(dx_per_ms=.007, dz_per_ms=0)},
            turn_rates=lambda: {"a": .15, "d": -.18})
        self.assertEqual((7, 150), move.route_motion_seed(adapter, object()))

    def test_sharp_corner_releases_then_continues_with_same_lease(self):
        events, calls = [], []
        def mover(adapter, x, z, stop, emit, **kwargs):
            calls.append((x, z, kwargs["reservation"], kwargs["path_points"]))
            for index, guide in enumerate(kwargs["path_points"]):
                emit({"status": "passed", "name": guide["name"], "index": index})
            adapter.last_input_receipt = {"status": "arrived"}
            emit({"status": "arrived", "name": "CLI destination"})
            return {"status": "arrived", "position": {"x": x, "y": 10, "z": z},
                    "releaseSucceeded": True, "desktopInputsDown": []}
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to", side_effect=mover):
            legs = move.run_continuous_route(self.adapter,
                [["A", 0, 0], ["B", 10, 0], ["C", 10, 10]],
                threading.Event(), events.append)
        self.assertEqual([(10, 10)], [(x, z) for x, z, _, _ in calls])
        self.assertTrue(calls[0][3][1]["controlPause"])
        self.assertEqual(1, self.adapter.reservations)
        self.assertEqual(["passed", "passed", "arrived"], [e["status"] for e in events])
        self.assertEqual(["A", "B", "C"], [leg["name"] for leg in legs])

    def test_auto_corner_preserves_pass_and_stop_between_spans(self):
        from scripts.physical_waypoints import Stopped
        events, calls = [], []
        stop = threading.Event()
        lease = SimpleNamespace(check=lambda: None)
        def mover(adapter, x, z, stop_flag, emit, **kwargs):
            calls.append((x, z, kwargs))
            adapter.last_input_receipt = {"status": "stopped"}
            emit({"status": "passed", "index": 0, "name": "A"})
            emit({"status": "passed", "index": 1, "name": "B",
                  "source": "settled-corner", "releaseSucceeded": True})
            stop_flag.set()
            raise Stopped("Stopped; no continuation")
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to", side_effect=mover):
            with self.assertRaisesRegex(Stopped, "Stopped"):
                move.run_continuous_route(self.adapter,
                    [["A", 0, 0], ["B", 10, 0], ["C", 10, 10]], stop, events.append,
                    reservation=lease, deadline=time.monotonic()+20)
        self.assertEqual(1, len(calls))
        self.assertIs(lease, calls[0][2]["reservation"])
        self.assertTrue(calls[0][2]["control_pauses"])
        self.assertLessEqual(calls[0][2]["max_seconds"], 20)
        self.assertEqual(0, self.adapter.reservations)
        self.assertEqual(["A", "B"], [e["name"] for e in events])

    def test_control_pause_stopped_receipt_commits_only_validated_prefix(self):
        now = datetime.now(timezone.utc)
        final = receipt("stopped", reason="operator STOP")
        stop_path = self.root / "protocol-prefix.stop"
        final["stopFile"] = str(stop_path.absolute())
        point = {"x": 5.0, "y": 10.0, "z": 0.0}
        before, after = (now-timedelta(seconds=.4)).isoformat(), (now-timedelta(seconds=.2)).isoformat()
        final["passedWaypoints"] = [{"index": 0, "name": "B", "position": point,
                                      "observedAtUtc": after, "source": "settled-corner"}]
        final.update(controlPauseVersion=1, pathTruncated=False, controlPauseReceipts=[{
            "index": 0, "name": "B", "position": point, "observedAtUtc": after,
            "releaseSucceeded": True, "desktopInputsDown": [],
            "stationaryBefore": {"position": point, "bearingDegrees": 90, "observedAtUtc": before},
            "stationaryAfter": {"position": point, "bearingDegrees": 90, "observedAtUtc": after}}])
        events = []
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             self.assertRaises(move.ContinuousStopped) as error:
            move.move_to(self.adapter, 100, 0, threading.Event(), events.append,
                path_points=[{"name": "B", "x": 5, "z": 0, "controlPause": True},
                             {"name": "later", "x": 10, "z": 0}],
                control_pauses=True, popen=lambda cmd, **kw: FakeProcess(cmd, final),
                native_exe=self.root / "native.exe", owner_identity=(55, 66),
                stop_path=stop_path, recovery_run=successful_recovery)
        self.assertEqual(["B"], [event["name"] for event in events if event["status"] == "passed"])
        self.assertEqual(1, error.exception.receipt["controlPauseVersion"])
        self.assertTrue(error.exception.receipt["releaseSucceeded"])

    def test_control_pause_missing_protocol_never_emits_passage(self):
        now = datetime.now(timezone.utc)
        final = receipt("stopped", reason="operator STOP")
        stop_path = self.root / "protocol.stop"
        final["stopFile"] = str(stop_path.absolute())
        final["passedWaypoints"] = [{"index": 0, "name": "B", "position":
            {"x": 5, "y": 10, "z": 0}, "observedAtUtc": now.isoformat(),
            "source": "settled-corner"}]
        events, commands = [], []
        def spawn(command, **kwargs):
            commands.append(command)
            return FakeProcess(command, final)
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             self.assertRaisesRegex(Exception, "control-pause protocol"):
            move.move_to(self.adapter, 100, 0, threading.Event(), events.append,
                path_points=[{"name": "B", "x": 5, "z": 0, "controlPause": True}],
                control_pauses=True, popen=spawn, native_exe=self.root / "native.exe",
                owner_identity=(55, 66), stop_path=stop_path, recovery_run=successful_recovery)
        self.assertIn("--control-pauses", commands[0])
        self.assertFalse(any(event["status"] == "passed" for event in events))
        self.assertFalse(self.adapter._continuous_move_receipt_trusted)

    def test_continuous_route_rejects_total_distance_before_native_launch(self):
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to") as native:
            with self.assertRaisesRegex(Exception, "exceeds 1000"):
                move.run_continuous_route(self.adapter,
                    [["Start", 0, 0], ["Too far", 1001, 0]], threading.Event())
        native.assert_not_called()

    def test_explicit_stops_split_batches_and_final_always_stops(self):
        calls, events = [], []
        def batch(adapter, x, z, stop, emit, **kwargs):
            calls.append((x, [p["name"] for p in kwargs["path_points"]]))
            for index, guide in enumerate(kwargs["path_points"]):
                emit({"status": "route-progress", "index": index, "name": guide["name"],
                      "position": {"x": guide["x"], "y": 10, "z": guide["z"]}, "trusted": False})
                emit({"status": "route-progress", "index": index, "name": guide["name"],
                      "position": {"x": float("nan"), "y": 10, "z": guide["z"]}})
                emit({"status": "passed", "index": index, "name": guide["name"],
                      "goal": guide, "position": {"x": guide["x"], "y": 10, "z": guide["z"]}})
            adapter.last_input_receipt = {"status": "arrived"}
            return {"status": "arrived", "heldInputMilliseconds": 0}
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to", side_effect=batch):
            legs = move.run_continuous_route(self.adapter,
                [["A", 1, 0], ["B", 2, 0], ["C", 3, 0], ["D", 4, 0]],
                threading.Event(), events.append, point_kinds=["pass", "stop", "pass", "pass"])
        self.assertEqual([(2.0, ["A"]), (4.0, ["C"])], calls)
        self.assertEqual(["A", "B", "C", "D"], [leg["name"] for leg in legs])
        progress = [event for event in events if event["status"] == "route-progress"]
        self.assertEqual([(0, 1, 4), (2, 3, 4)],
                         [(event["index"], event["observedPointNumber"], event["waypointCount"]
                           ) for event in progress])

    def test_passage_indices_are_global_across_explicit_stops_with_duplicate_names(self):
        events = []
        def mover(adapter, x, z, stop, emit, **kwargs):
            for index, guide in enumerate(kwargs["path_points"]):
                emit({"status": "passed", "index": index, "name": guide["name"]})
            adapter.last_input_receipt = {"status": "arrived"}
            return {"status": "arrived", "position": {"x": x, "y": 10, "z": z}}
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to", side_effect=mover):
            move.run_continuous_route(self.adapter,
                [["same", 1, 0], ["stop", 2, 0], ["same", 3, 0], ["end", 4, 0]],
                threading.Event(), events.append, point_kinds=["pass", "stop", "pass", "pass"])
        self.assertEqual([(0, 0, "same"), (2, 0, "same")],
                         [(e["index"], e["batchIndex"], e["name"]) for e in events])

    def test_guides_require_valid_final_release_before_passage_events(self):
        for valid in (True, False):
            with self.subTest(valid=valid):
                final = receipt("stopped", reason="operator STOP")
                final["releaseSucceeded"] = valid
                stop_path = self.root / f"pass-{valid}.stop"
                final["stopFile"] = str(stop_path.absolute())
                passage = {"index": 0, "name": "A", "position": {"x": 5, "y": 10, "z": 0},
                           "observedAtUtc": datetime.now(timezone.utc).isoformat(),
                           "source": "segment-crossing"}
                final["passedWaypoints"] = [passage]
                events, paths = [], []
                def launch(command, **kwargs):
                    path = Path(command[command.index("--path-file") + 1])
                    paths.append(path)
                    self.assertEqual({"waypoints": [{"name": "A", "x": 5.0, "z": 0.0, "y": 10.0}]},
                                     json.loads(path.read_text()))
                    return FakeProcess(command, final)
                with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
                     self.assertRaises(Exception):
                    move.move_to(self.adapter, 100, 0, threading.Event(), events.append,
                                 popen=launch, native_exe=self.root / "native.exe",
                                 owner_identity=(55, 66), stop_path=stop_path,
                                 recovery_run=successful_recovery,
                                 path_points=[{"name": "A", "x": 5, "z": 0, "y": 10}])
                passed = [event for event in events if event["status"] == "passed"]
                self.assertEqual(1 if valid else 0, len(passed))
                if valid:
                    self.assertTrue(passed[0]["passageVerified"])
                    self.assertTrue(passed[0]["releaseSucceeded"])
                    self.assertEqual("segment-crossing", passed[0]["source"])
                for path in paths:
                    path.unlink()

    def test_partial_passes_are_ordered_fresh_and_within_height(self):
        started = datetime.now(timezone.utc)
        guides = [{"name": "A", "x": 5, "z": 0, "y": 10},
                  {"name": "B", "x": 10, "z": 0}]
        passage = {"index": 0, "name": "A", "position": {"x": 5, "y": 10, "z": 0},
                   "observedAtUtc": started.isoformat()}
        value = {"status": "stopped", "passedWaypoints": [passage]}
        self.assertEqual([passage], move._validate_passes(value, guides, started))
        with self.assertRaisesRegex(ValueError, "omitted"):
            move._validate_passes(dict(value, status="arrived"), guides, started)
        for changed in (dict(passage, index=1), dict(passage, name="B"),
                        dict(passage, position={"x": 5, "y": 11, "z": 0}),
                        dict(passage, observedAtUtc="2000-01-01T00:00:00Z")):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                move._validate_passes({"status": "stopped", "passedWaypoints": [changed]},
                                      guides, started)

    def test_playback_stop_then_resume_uses_saved_real_waypoint_cursor(self):
        from scripts.physical_waypoints import Stopped
        from scripts.waypoint_playback import play_route
        from scripts.waypoint_progress import RouteProgress
        document = {"waypoints": [["A", 0, 0], ["B", 30, 0], ["C", 60, 0]]}
        checkpoint = self.root / "progress.json"
        stop_once = {"value": True}
        def one_leg(adapter, x, z, stop, emit, **kwargs):
            if stop_once["value"]:
                stop_once["value"] = False
                guide = kwargs["path_points"][0]
                emit({"status": "passed", "index": 0, "name": guide["name"],
                      "goal": guide, "position": {"x": guide["x"], "y": 10, "z": guide["z"]},
                      "releaseSucceeded": True, "desktopInputsDown": [], "passageVerified": True})
                raise Stopped("operator STOP")
            for index, guide in enumerate(kwargs["path_points"]):
                emit({"status": "passed", "index": index, "name": guide["name"],
                      "goal": guide, "position": {"x": guide["x"], "y": 10, "z": guide["z"]},
                      "releaseSucceeded": True, "desktopInputsDown": [], "passageVerified": True})
            result = {"status": "arrived", "name": "CLI destination",
                      "start": {"x": 0, "y": 10, "z": 0},
                      "goal": {"x": x, "y": 10, "z": z},
                      "position": {"x": x, "y": 10, "z": z}, "bearing": 90,
                      "distance": 0, "pulses": 1, "elapsedMilliseconds": 10}
            adapter.last_input_receipt = {"version": 1, "status": "arrived"}
            emit(result)
            return result
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to", side_effect=one_leg):
            with self.assertRaises(Stopped):
                play_route(self.adapter, document, threading.Event(), lambda event: None,
                           runner=move.run_continuous_route, checkpoint=checkpoint, pass_through=True)
            saved = RouteProgress.load(checkpoint, document,
                                       self.adapter.binding["runtimeIdentity"])
            self.assertEqual((1, "B"), (saved.next_index, saved.remaining_points()[0][0]))
            legs, completed = play_route(self.adapter, document, threading.Event(),
                lambda event: None, runner=move.run_continuous_route,
                checkpoint=checkpoint, resume=True, pass_through=True)
        self.assertEqual((2, 3), (len(legs), completed.next_index))

    def test_preview_cli_path_is_input_free(self):
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start):
            value = move.preview_move(self.adapter, 100, 0, threading.Event())
        self.assertEqual(("preview-only", False, 100.0),
                         (value["status"], value["inputSent"], value["distance"]))

    def test_standalone_cli_without_execute_returns_json_preview(self):
        preview = {"status": "preview-only", "distance": 100.0, "inputSent": False}
        output = io.StringIO()
        with patch("scripts.physical_waypoints.PhysicalAdapter", return_value=self.adapter), \
             patch("scripts.physical_waypoints.cli_stop_controls") as stop_controls, \
             patch.object(move, "preview_move", return_value=preview) as planned, \
             patch.object(move, "move_to") as executed, redirect_stdout(output):
            code = move.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                              "--x", "100", "--z", "0", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), preview)
        planned.assert_called_once()
        executed.assert_not_called()
        stop_controls.assert_not_called()

    def test_standalone_execute_installs_stop_controls_around_move(self):
        result = {"status": "arrived", "distance": .1, "inputSent": True}
        entered = []
        class Controls:
            def __init__(self, stop): self.stop = stop
            def __enter__(self):
                entered.append(("enter", self.stop))
            def __exit__(self, *args):
                entered.append(("exit", self.stop))
        def execute(adapter, x, z, stop):
            self.assertEqual(entered, [("enter", stop)])
            self.assertFalse(stop.is_set())
            return result
        output = io.StringIO()
        with patch("scripts.physical_waypoints.PhysicalAdapter", return_value=self.adapter), \
             patch("scripts.physical_waypoints.cli_stop_controls", side_effect=Controls) as controls, \
             patch.object(move, "move_to", side_effect=execute) as executed, \
             patch.object(move, "preview_move") as previewed, redirect_stdout(output):
            code = move.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                              "--x", "100", "--z", "0", "--execute", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), result)
        controls.assert_called_once()
        executed.assert_called_once()
        previewed.assert_not_called()
        self.assertEqual([state for state, _ in entered], ["enter", "exit"])


class ControlPauseProofTests(unittest.TestCase):
    def fixture(self):
        now = datetime.now(timezone.utc)
        before = now - timedelta(seconds=.3)
        after = now - timedelta(seconds=.1)
        pos = {"x": 10.0, "y": 10.0, "z": 0.0}
        sample1 = {"position": pos.copy(), "bearingDegrees": 30.0,
                   "observedAtUtc": before.isoformat()}
        sample2 = {"position": pos.copy(), "bearingDegrees": 30.2,
                   "observedAtUtc": after.isoformat()}
        guides = [{"name": "corner", "x": 10.0, "y": 10.0, "z": 0.0, "controlPause": True},
                  {"name": "later", "x": 20.0, "z": 0.0}]
        passes = [{"index": 0, "name": "corner", "source": "settled-corner",
                   "position": pos.copy(), "observedAtUtc": after.isoformat()}]
        proof = {"index": 0, "name": "corner", "position": pos.copy(),
                 "observedAtUtc": after.isoformat(), "releaseSucceeded": True,
                 "desktopInputsDown": [], "stationaryBefore": sample1,
                 "stationaryAfter": sample2}
        receipt = {"status": "stopped", "controlPauseVersion": 1,
                   "controlPauseReceipts": [proof], "pathTruncated": False}
        return receipt, guides, passes, now-timedelta(seconds=1)

    def test_release_validated_stop_prefix(self):
        receipt, guides, passes, start = self.fixture()
        move._validate_control_pauses(receipt, guides, passes, start)
        receipt["controlPauseReceipts"] = []
        move._validate_control_pauses(receipt, guides, [], start)

    def test_missing_protocol_and_false_settlement_fail_closed(self):
        original, guides, passes, start = self.fixture()
        for mutate in (
            lambda r: r.pop("controlPauseVersion"),
            lambda r: r.update(controlPauseVersion=True),
            lambda r: r.update(controlPauseReceipts=[]),
            lambda r: r["controlPauseReceipts"][0].update(index=1),
            lambda r: r["controlPauseReceipts"][0].update(releaseSucceeded=False),
            lambda r: r["controlPauseReceipts"][0].update(desktopInputsDown=["W"]),
            lambda r: r["controlPauseReceipts"][0]["stationaryBefore"]["position"].update(x=11),
            lambda r: r["controlPauseReceipts"][0]["stationaryAfter"].update(bearingDegrees=31),
            lambda r: r["controlPauseReceipts"][0]["stationaryBefore"].update(
                observedAtUtc=r["controlPauseReceipts"][0]["observedAtUtc"]),
        ):
            receipt = deepcopy(original); mutate(receipt)
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                move._validate_control_pauses(receipt, guides, passes, start)

    def test_truncated_path_is_not_a_survival_trail(self):
        receipt, guides, passes, start = self.fixture()
        receipt["pathTruncated"] = False
        receipt["readCount"] = 3
        receipt["path"] = [{}, {}]
        with self.assertRaisesRegex(ValueError, "survival trail"):
            move._validate_control_pauses(receipt, guides, passes, start, survival_guard=True)
        receipt["pathTruncated"] = True
        move._validate_control_pauses(receipt, guides, passes, start)
        with self.assertRaisesRegex(ValueError, "survival trail"):
            move._validate_control_pauses(receipt, guides, passes, start, survival_guard=True)


class ResponseEstimateTests(unittest.TestCase):
    def example(self, key="W"):
        base = datetime(2026, 11, 14, tzinfo=timezone.utc)
        def t(seconds):
            return (base + timedelta(seconds=seconds)).isoformat()
        def pose(seconds, x, bearing=90):
            return {"observedAtUtc": t(seconds), "x": x, "z": 0, "bearing": bearing}
        def event(seconds, phase, selected=key):
            return {"key": selected, "phase": phase, "inserted": True,
                    "callStartedAtUtc": t(seconds), "callCompletedAtUtc": t(seconds+.001)}
        if key == "W":
            path = [pose(0,0), pose(.05,0), pose(.15,0), pose(.22,.1),
                    pose(.30,.55), pose(.40,1.0), pose(.45,1.05), pose(.52,1.05)]
        else:
            path = [pose(0,0,179), pose(.05,0,179), pose(.15,0,179), pose(.22,0,-176),
                    pose(.30,0,-166), pose(.40,0,-156), pose(.45,0,-155), pose(.52,0,-155)]
        return {"status": "arrived", "path": path,
                "keySendEvents": [event(.10,"key-down"), event(.42,"key-up")]}

    def test_sampled_onset_and_censored_coast_are_reported(self):
        estimate = move.response_estimate(self.example())
        onset = estimate["onsetIntervalsSeconds"][0]
        self.assertEqual("W", onset["key"])
        self.assertEqual(0, onset["lower"])
        self.assertAlmostEqual(.049, onset["thresholdLower"], places=5)
        self.assertAlmostEqual(.12, onset["upper"], places=5)
        coast = estimate["coastObservations"][0]
        self.assertAlmostEqual(.05, coast["sampledDistance"])
        self.assertTrue(coast["censored"])

    def test_wraparound_turn_rates_update_only_conservative_seed(self):
        sample = self.example("A")
        delay, rate, estimate = move.merge_response_seed(sample, .1, 175)
        self.assertGreater(delay, .1)
        self.assertLess(rate, 175)
        self.assertGreater(len(estimate["turnRatesDegreesPerSecond"]), 1)
        self.assertAlmostEqual(.12, delay, places=5)

    def test_evolving_coast_and_wrong_sign_turn(self):
        sample = self.example()
        final = sample["path"][-1]
        base = datetime.fromisoformat(final["observedAtUtc"])
        sample["path"][-2]["x"] = 1.1
        final["x"] = 1.2
        sample["path"].append(dict(final, observedAtUtc=(base + timedelta(seconds=.07)).isoformat()))
        coast = move.response_estimate(sample)["coastObservations"][0]
        self.assertFalse(coast["immediate"])
        self.assertAlmostEqual(.2, coast["sampledDistance"])
        turn = self.example("D")  # Fixture turns in A's positive direction.
        observation = move.response_estimate(turn)
        self.assertEqual([], observation["onsetIntervalsSeconds"])
        self.assertEqual([], observation["turnRatesDegreesPerSecond"])
        self.assertEqual([], observation["coastObservations"])

    def test_stationary_before_release_does_not_train_coast(self):
        sample = self.example()
        sample["path"][4]["x"] = sample["path"][5]["x"]
        self.assertEqual([], move.response_estimate(sample)["coastObservations"])

    def test_unmoving_unordered_truncated_stopped_and_overlap_are_not_overclaimed(self):
        sample = self.example()
        for pose in sample["path"]:
            pose["x"] = 0
        self.assertEqual([], move.response_estimate(sample)["onsetIntervalsSeconds"])
        sample = self.example(); sample["path"][2], sample["path"][3] = sample["path"][3], sample["path"][2]
        self.assertEqual([], move.response_estimate(sample)["coastObservations"])
        sample = self.example(); sample["path"] *= 100
        self.assertEqual([], move.response_estimate(sample)["onsetIntervalsSeconds"])
        sample = self.example(); sample["status"] = "stopped"
        self.assertEqual([], move.response_estimate(sample)["coastObservations"])
        sample = self.example(); first, last = sample["keySendEvents"]
        sample["keySendEvents"] = [first, dict(first, key="A"), dict(last, key="A"), last]
        self.assertEqual([], move.response_estimate(sample)["onsetIntervalsSeconds"])


if __name__ == "__main__":
    unittest.main()
