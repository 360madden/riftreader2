import io
import json
import threading
import time
import unittest
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
            with self.assertRaisesRegex(Exception, "operator STOP"):
                move.move_to(self.adapter, 100, 0, stopped, popen=popen,
                             native_exe=self.root / "native.exe", owner_identity=(55, 66),
                             stop_path=stop_path)
        self.assertTrue(stop_path.exists())
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
            calls.append((x, z, kwargs["reservation"], kwargs["max_seconds"]))
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
                                             events.append, entry_check=entry)
        self.assertEqual((31, 31, 1), (len(legs), len(calls), self.adapter.reservations))
        self.assertEqual([row["name"] for row in legs], [row[0] for row in points])
        self.assertEqual([event["name"] for event in events], [row[0] for row in points])
        self.assertTrue(all(call[2] is calls[0][2] for call in calls))
        self.assertEqual((75, .1), (legs[-1]["totalHoldMs"], legs[-1]["elapsedSeconds"]))
        entry.assert_called_once_with(self.start.position)

    def test_continuous_route_rejects_total_distance_before_native_launch(self):
        with patch("scripts.physical_waypoints.read_stationary", return_value=self.start), \
             patch.object(move, "move_to") as native:
            with self.assertRaisesRegex(Exception, "exceeds 1000"):
                move.run_continuous_route(self.adapter,
                    [["Start", 0, 0], ["Too far", 1001, 0]], threading.Event())
        native.assert_not_called()

    def test_playback_stop_then_resume_uses_saved_real_waypoint_cursor(self):
        from scripts.physical_waypoints import Stopped
        from scripts.waypoint_playback import play_route
        from scripts.waypoint_progress import RouteProgress
        document = {"waypoints": [["A", 0, 0], ["B", 30, 0], ["C", 60, 0]]}
        checkpoint = self.root / "progress.json"
        stop_once = {"value": True}
        def one_leg(adapter, x, z, stop, emit, **kwargs):
            if x == 30 and stop_once["value"]:
                stop_once["value"] = False
                raise Stopped("operator STOP")
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
                           runner=move.run_continuous_route, checkpoint=checkpoint)
            saved = RouteProgress.load(checkpoint, document,
                                       self.adapter.binding["runtimeIdentity"])
            self.assertEqual((1, "B"), (saved.next_index, saved.remaining_points()[0][0]))
            legs, completed = play_route(self.adapter, document, threading.Event(),
                lambda event: None, runner=move.run_continuous_route,
                checkpoint=checkpoint, resume=True)
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


if __name__ == "__main__":
    unittest.main()
