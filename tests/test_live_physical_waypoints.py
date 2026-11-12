"""Injected clocks/readers only: no native processes, GUI, capture or input."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from io import BytesIO
from pathlib import Path
import queue
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from scripts import live_physical_waypoints as live
from tests.test_physical_facing import report_with_target
from tests.test_physical_only_selection import IDENTITY


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native = report_with_target()
        self.native["observations"] = [self.native["observation"]]
        self.native["requestedSamples"] = self.native["completedSamples"] = 1
        self.path = self.root / "native.json"
        self.selection = dict(status="ready", ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY))
        self.route_document = dict(waypoints=[["One", 7427, 2946]], heights=[871],
            recording=dict(version=1, complete=True, identity=dict(runtimeIdentity=dict(
                machine="AMD-DESKTOP", gameBuildSha256=IDENTITY["executableSha256"],
                unitKey=self.native["observation"]["playerKeyDecimal"], processId=999))))
        self.route_path = self.root / "route.json"
        self.route_path.write_text(json.dumps(self.route_document))
        self.route = live.load_route(self.route_path)
        self.read = Mock(return_value=dict(self.selection, status="complete", nativeOutput=str(self.path)))
        self.snapshot = Mock(return_value=dict(foreground=True, clientRect=[100, 125, 1920, 1080]))
        self.now = datetime.fromisoformat(self.native["observation"]["completedAtUtc"].replace("Z", "+00:00"))

    def provider(self, clock=None, utcnow=None):
        self.path.write_text(json.dumps(self.native))
        return live.ProjectionProvider(self.selection, self.route, self.snapshot, read=self.read,
            clock=clock or Mock(side_effect=[10., 10.1]), utcnow=utcnow or (lambda: self.now), max_age=.8)

    def test_packet_uses_pre_read_timestamp_full_matrix_and_original_provenance(self):
        provider = self.provider()
        packet = provider.acquire()
        self.assertEqual(packet["acquiredMonotonic"], 10.)
        self.assertEqual(packet["target"], IDENTITY)
        self.assertEqual(packet["clientRect"], [100, 125, 1920, 1080])
        self.assertAlmostEqual(packet["points"][0]["ground"]["normalizedX"], .5)
        self.assertAlmostEqual(packet["points"][0]["ground"]["normalizedY"], .5)
        self.assertLess(packet["points"][0]["beaconTop"]["normalizedY"], .5)
        self.assertEqual(provider.route["recordingIdentity"]["runtimeIdentity"]["processId"], 999)
        self.read.assert_called_once_with(self.selection, "facing", samples=1, include_target=True)

    def test_background_target_never_starts_read(self):
        self.snapshot.return_value["foreground"] = False
        with self.assertRaisesRegex(ValueError, "not-foreground"):
            self.provider().acquire()
        self.read.assert_not_called()

    def test_saved_progress_updates_and_mismatch_clears_only_display_state(self):
        from scripts.waypoint_progress import RouteProgress
        frame = self.provider().acquire()
        geometry = deepcopy(frame)
        checkpoint = self.root / "progress.json"
        cursor = RouteProgress(self.route_document, identity=self.route["identity"])
        cursor.begin(dict(x=7427, y=871, z=2946))
        cursor.save(checkpoint)
        summary = live.apply_saved_progress(frame, checkpoint, self.route)
        self.assertEqual(summary["nextNumber"], 1)
        self.assertEqual(frame["points"][0]["routeState"], "next")
        cursor.confirm_arrival(0, self.route_document["waypoints"][0])
        cursor.save(checkpoint)
        summary = live.apply_saved_progress(frame, checkpoint, self.route)
        self.assertIsNone(summary["nextNumber"])
        self.assertEqual(frame["points"][0]["routeState"], "completed")
        payload = json.loads(checkpoint.read_text())
        payload["identity"]["unitKey"] = "another player"
        checkpoint.write_text(json.dumps(payload))
        summary = live.apply_saved_progress(frame, checkpoint, self.route)
        self.assertEqual(summary["status"], "unavailable")
        self.assertEqual(frame, geometry)

    def test_changed_geometry_foreground_and_slow_reads_refused(self):
        for second in (dict(foreground=False, clientRect=[100, 125, 1920, 1080]),
                       dict(foreground=True, clientRect=[101, 125, 1920, 1080])):
            self.snapshot.side_effect = [dict(foreground=True, clientRect=[100, 125, 1920, 1080]), second]
            with self.assertRaisesRegex(ValueError, "foreground-or-geometry"):
                self.provider().acquire()
        self.snapshot.side_effect = None
        with self.assertRaisesRegex(ValueError, "acquisition-expired"):
            self.provider(clock=Mock(side_effect=[10., 11.])).acquire()

    def test_stale_native_sample_and_changed_player_rejected(self):
        with self.assertRaisesRegex(ValueError, "sample-stale"):
            self.provider(utcnow=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)).acquire()
        self.route["identity"]["unitKey"] = "wrong"
        with self.assertRaisesRegex(ValueError, "recorded-player"):
            self.provider().acquire()

    def test_changed_process_and_unstable_camera_rejected(self):
        self.native["identity"] = dict(self.native["identity"], processId=999)
        with self.assertRaisesRegex(ValueError, "native-identity"):
            self.provider().acquire()
        self.native = report_with_target()
        self.native["observations"] = [self.native["observation"]]
        self.native["requestedSamples"] = self.native["completedSamples"] = 1
        self.native["observation"]["targetProjectionCameraStableCandidate"] = False
        with self.assertRaises(ValueError):
            self.provider().acquire()

    def test_bad_route_heights_and_host_build_refused(self):
        for height in (None, True, float("nan")):
            self.route_document["heights"] = [height]
            self.route_path.write_text(json.dumps(self.route_document))
            with self.assertRaises(ValueError):
                live.load_route(self.route_path)
        self.route["identity"]["gameBuildSha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "route-host-build"):
            self.provider()

    def test_worker_keeps_only_latest_packet_and_no_packet_after_cancel(self):
        channel, stop = queue.Queue(maxsize=1), threading.Event()
        channel.put({"old": True})
        live._latest(channel, {"new": True})
        self.assertEqual(channel.get_nowait(), {"new": True})
        provider = Mock()
        def read_then_cancel():
            stop.set()
            return {"target": IDENTITY}
        provider.acquire.side_effect = read_then_cancel
        counts = dict(attempts=0, acquired=0, failures=0)
        live.feed(provider, channel, stop, counts)
        self.assertTrue(channel.empty())
        self.assertEqual(counts["attempts"], 1)
        self.assertEqual(counts["acquired"], 0)

    def test_invalid_cli_limits_fail_before_selection(self):
        with patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(live.physical, "select_physical") as select:
            for kwargs in (dict(duration=601), dict(max_age=.01), dict(physical_pid=0)):
                arguments = dict(expected_host="AMD-DESKTOP", physical_pid=123, route_path=self.route_path)
                arguments.update(kwargs)
                with self.assertRaises(ValueError):
                    live.run(**arguments)
            select.assert_not_called()

    def test_owned_window_close_stops_and_joins_worker_before_close(self):
        events = []
        class Window:
            def protocol(self, name, callback):
                self.cancel = callback
            def after(self, delay, callback):
                pass
            def quit(self):
                events.append("quit")
        class Overlay:
            def __init__(self, target, max_age):
                self.window = Window()
            def hide(self, reason):
                events.append("hide:" + reason)
            def run(self):
                self.window.cancel()
            def close(self):
                events.append("close")
        class Worker:
            def __init__(self, **kwargs):
                self.stop = kwargs["args"][2]
            def start(self):
                events.append("start")
            def join(self):
                self.assert_stopped = self.stop.is_set()
                if not self.assert_stopped:
                    raise AssertionError("Worker must stop before join")
                events.append("join")
        presenter = types.SimpleNamespace(PhysicalWaypointOverlay=Overlay, target_snapshot=self.snapshot)
        with patch.dict("sys.modules", {"scripts.physical_waypoint_overlay": presenter}), \
             patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(live.physical, "select_physical", return_value=self.selection) as select, \
             patch.object(live.threading, "Thread", Worker):
            output = self.root / "summary.json"
            result = live.run("AMD-DESKTOP", 123, self.route_path, output=output)
        self.assertEqual(result["reason"], "window-closed")
        self.assertFalse(result["inputSent"])
        self.assertLess(events.index("hide:window-closed"), events.index("join"))
        self.assertLess(events.index("join"), events.index("close"))
        self.assertEqual(json.loads(output.read_text())["counts"]["attempts"], 0)
        select.assert_called_once_with("AMD-DESKTOP", 123)

    def test_expected_identity_and_stop_startup_refuse_before_overlay(self):
        expected = dict(expected_start_ticks=IDENTITY["processStartUtcTicks"],
                        expected_sha256=IDENTITY["executableSha256"], expected_hwnd=IDENTITY["hwnd"])
        overlay = Mock()
        presenter = types.SimpleNamespace(PhysicalWaypointOverlay=overlay, target_snapshot=self.snapshot)
        existing = self.root / "existing.stop"
        existing.write_text("stop")
        cases = [dict(expected_start_ticks=IDENTITY["processStartUtcTicks"]),
                 dict(expected, expected_start_ticks="0"), dict(expected, expected_sha256="bad"),
                 dict(expected, expected_hwnd=True), dict(expected, expected_hwnd=0),
                 dict(expected, expected_start_ticks="123"), dict(expected, expected_sha256="b" * 64),
                 dict(expected, expected_hwnd=999), dict(stop_file=existing), dict(stop_file=Path("relative.stop")),
                 dict(progress_file=Path("relative-progress.json"))]
        with patch.dict("sys.modules", {"scripts.physical_waypoint_overlay": presenter}), \
             patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(live.physical, "select_physical", return_value=self.selection):
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    live.run("AMD-DESKTOP", 123, self.route_path, **kwargs)
        overlay.assert_not_called()
        self.assertEqual(existing.read_text(), "stop")

    def test_stop_file_appearance_hides_joins_closes_and_preserves_file(self):
        stop_path, events = self.root / "request.stop", []
        class Window:
            def protocol(self, name, callback):
                pass
            def after(self, delay, callback):
                if delay == 0:
                    self.poll = callback
            def quit(self):
                events.append("quit")
        class Overlay:
            def __init__(self, target, max_age):
                self.window = Window()
            def run(self):
                stop_path.write_text("stop")
                self.window.poll()
            def hide(self, reason):
                events.append("hide:" + reason)
            def close(self):
                events.append("close")
        class Worker:
            def __init__(self, **kwargs):
                self.stop = kwargs["args"][2]
            def start(self):
                pass
            def join(self):
                if not self.stop.is_set():
                    raise AssertionError("Reader must receive cancellation before join")
                events.append("join")
        presenter = types.SimpleNamespace(PhysicalWaypointOverlay=Overlay, target_snapshot=self.snapshot)
        with patch.dict("sys.modules", {"scripts.physical_waypoint_overlay": presenter}), \
             patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(live.physical, "select_physical", return_value=self.selection), \
             patch.object(live.threading, "Thread", Worker), \
             patch.object(live.time, "monotonic", return_value=10.):
            result = live.run("AMD-DESKTOP", 123, self.route_path, stop_file=stop_path,
                expected_start_ticks=IDENTITY["processStartUtcTicks"],
                expected_sha256=IDENTITY["executableSha256"].upper(), expected_hwnd=IDENTITY["hwnd"])
        self.assertEqual(result["reason"], "stop-requested")
        self.assertEqual(result["stopFile"], str(stop_path))
        self.assertEqual(result["expectedTarget"]["hwnd"], IDENTITY["hwnd"])
        self.assertLess(events.index("hide:stop-requested"), events.index("join"))
        self.assertLess(events.index("join"), events.index("close"))
        self.assertEqual(stop_path.read_text(), "stop")

    def test_hwnd_cli_accepts_decimal_and_hex(self):
        self.assertEqual(live._hwnd_argument("456"), 456)
        self.assertEqual(live._hwnd_argument("0x1c8"), 456)

    def stream_packet(self):
        row = deepcopy(self.native["observation"])
        # Streaming has no target-pair scan; the raw camera is independently valid.
        for key in ("targetPositionPairCandidate", "opticalCameraAfterTargetCandidate", "targetProjectionCameraStableCandidate"):
            row.pop(key, None)
        return dict(recordType="native-current-facing-stream-row/1", sequence=0, status="candidate",
            identity=self.native["identity"], observation=row, emittedAtUtc=row["completedAtUtc"],
            captureElapsedMilliseconds=40)

    def child(self, packets, code=0):
        class Child:
            def __init__(self):
                self.stdout = BytesIO(b"".join(json.dumps(packet).encode() + b"\n" for packet in packets))
                self.stderr = BytesIO(b"bounded native diagnostic")
                self.code = None
                self.terminated = False
            def poll(self):
                return self.code
            def wait(self, timeout):
                self.code = code
                return self.code
            def terminate(self):
                self.terminated = True
                self.code = -15
            def kill(self):
                self.code = -9
        return Child()

    def test_stream_validates_fresh_row_and_end_without_target_pair(self):
        packet = self.stream_packet()
        child = self.child([packet, dict(recordType="native-current-facing-stream-end/1",
            status="complete", requestedSamples=1, completedSamples=1)])
        provider = self.provider(clock=lambda: 10.)
        channel, counts = queue.Queue(maxsize=1), dict(acquired=0)
        with patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"):
            live.stream_burst(provider, channel, threading.Event(), counts, popen=Mock(return_value=child), samples=1)
        frame = channel.get_nowait()["frame"]
        self.assertAlmostEqual(frame["acquiredMonotonic"], 9.96)
        self.assertEqual(provider.stream_rows, 1)
        self.assertEqual(provider.last_stream_receipt["status"], "complete")
        self.assertEqual(counts["acquired"], 1)
        self.assertIn("native diagnostic", provider.stream_stderr)
        self.assertTrue(child.stdout.closed)

    def test_stream_rejects_sequence_replay_and_old_rows(self):
        packet = self.stream_packet()
        provider = self.provider(clock=lambda: 10.)
        channel, counts = queue.Queue(maxsize=1), dict(acquired=0)
        child = self.child([packet, packet])
        with patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"):
            with self.assertRaisesRegex(ValueError, "sequence-invalid"):
                live.stream_burst(provider, channel, threading.Event(), counts, popen=Mock(return_value=child), samples=2)
        self.assertTrue(child.terminated)
        self.assertEqual(provider.stream_rows, 1)
        provider.utcnow = lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "row-expired"):
            provider.stream_frame(packet, self.snapshot.return_value)

    def test_stream_cancel_terminates_only_owned_child_and_emits_nothing(self):
        stop = threading.Event()
        child = self.child([])
        channel = queue.Queue(maxsize=1)
        def launch(*args, **kwargs):
            stop.set()
            return child
        with patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"):
            live.stream_burst(self.provider(), channel, stop, dict(acquired=0), popen=launch, samples=1)
        self.assertTrue(child.terminated)
        self.assertTrue(channel.empty())
        launch_mock = Mock()
        live.stream_burst(self.provider(), channel, stop, dict(acquired=0), popen=launch_mock, samples=1)
        launch_mock.assert_not_called()

    def test_stream_elapsed_order_end_and_exit_fail_closed(self):
        provider = self.provider(clock=lambda: 10.)
        packet = self.stream_packet()
        for elapsed in (None, 0, -1, float("nan")):
            bad = dict(packet, captureElapsedMilliseconds=elapsed)
            with self.assertRaisesRegex(ValueError, "elapsed-required"):
                provider.stream_frame(bad, self.snapshot.return_value)
        bad = dict(packet, emittedAtUtc="2020-01-01T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "acquisition-order"):
            provider.stream_frame(bad, self.snapshot.return_value)
        bad = dict(packet, emittedAtUtc="2030-01-01T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "clock-future"):
            provider.stream_frame(bad, self.snapshot.return_value)
        for packets, code, reason in (([packet], 0, "end-missing"),
            ([packet, dict(recordType="native-current-facing-stream-end/1", status="complete",
                           requestedSamples=1, completedSamples=0)], 0, "invalid-stream-end"),
            ([packet, dict(recordType="native-current-facing-stream-end/1", status="complete",
                           requestedSamples=1, completedSamples=1)], 2, "child-failed")):
            with patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"):
                with self.assertRaisesRegex(ValueError, reason):
                    live.stream_burst(provider, queue.Queue(maxsize=1), threading.Event(), dict(acquired=0),
                                      popen=Mock(return_value=self.child(packets, code)), samples=1)

    def test_stream_deadline_terminates_child_without_publishing(self):
        child = self.child([self.stream_packet()])
        provider = self.provider(clock=lambda: 10.)
        channel = queue.Queue(maxsize=1)
        with patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(live.time, "monotonic", side_effect=[0., 6.]):
            with self.assertRaisesRegex(ValueError, "child-timeout"):
                live.stream_burst(provider, channel, threading.Event(), dict(acquired=0),
                                  popen=Mock(return_value=child), samples=1)
        self.assertTrue(child.terminated)
        self.assertTrue(channel.empty())

    def test_epoch_confirmation_distinguishes_ended_alive_and_unknown(self):
        for result, expected in ((False, True), (True, False), (None, False)):
            alive = Mock(return_value=result)
            self.assertIs(live._pinned_process_ended(IDENTITY, alive), expected)
            alive.assert_called_once_with(IDENTITY["processId"], IDENTITY["processStartUtcTicks"])
        self.assertFalse(live._pinned_process_ended(IDENTITY, Mock(side_effect=OSError("unknown"))))

    def test_both_worker_modes_publish_terminal_once_without_stopping_main_consumer(self):
        for worker in (live.feed, live.stream_feed):
            with self.subTest(worker=worker.__name__):
                provider = Mock(target=IDENTITY)
                provider.acquire.side_effect = ValueError("original acquisition failure")
                channel, stop = queue.Queue(maxsize=1), threading.Event()
                channel.put({"frame": {"old": True}})
                counts = dict(attempts=0, acquired=0, failures=0, latestFailure=None)
                with patch.object(live, "_pinned_process_ended", return_value=True), \
                     patch.object(live, "stream_burst", side_effect=ValueError("original acquisition failure")):
                    worker(provider, channel, stop, counts)
                self.assertFalse(stop.is_set())
                self.assertEqual(channel.get_nowait(), dict(terminal=True, reason="target-process-ended"))
                self.assertTrue(channel.empty())
                self.assertEqual(counts["attempts"], 1)
                self.assertEqual(counts["failures"], 1)
                self.assertEqual(counts["latestFailure"], "original acquisition failure")

    def test_both_worker_modes_keep_transient_or_unknown_state_nonterminal(self):
        for worker in (live.feed, live.stream_feed):
            for alive in (Mock(return_value=True), Mock(side_effect=OSError("cannot establish epoch"))):
                with self.subTest(worker=worker.__name__, alive=alive):
                    provider = Mock(target=IDENTITY)
                    provider.acquire.side_effect = ValueError("target-not-foreground")
                    channel, stop = queue.Queue(maxsize=1), threading.Event()
                    counts = dict(attempts=0, acquired=0, failures=0, latestFailure=None)
                    actual_helper = live._pinned_process_ended
                    def check(target):
                        return actual_helper(target, alive)
                    # One ordinary retry wait ends the injected worker test.
                    with patch.object(live, "_pinned_process_ended", side_effect=check), \
                         patch.object(live, "stream_burst", side_effect=ValueError("target-not-foreground")), \
                         patch.object(stop, "wait", side_effect=lambda _: stop.set()) as wait:
                        worker(provider, channel, stop, counts)
                    self.assertEqual(channel.get_nowait(), {"reason": "target-not-foreground"})
                    wait.assert_called_once()
                    self.assertEqual(counts["failures"], 1)

    def test_terminal_packet_causes_main_hide_join_close(self):
        events = []
        class Window:
            def protocol(self, name, callback):
                pass
            def after(self, delay, callback):
                if delay == 0:
                    self.poll = callback
                else:
                    raise AssertionError("Terminal packet must not schedule another poll")
            def quit(self):
                events.append("quit")
        class Overlay:
            def __init__(self, target, max_age):
                self.window = Window()
            def run(self):
                self.window.poll()
            def hide(self, reason):
                events.append("hide:" + reason)
            def close(self):
                events.append("close")
        class Worker:
            def __init__(self, **kwargs):
                self.channel, self.stop = kwargs["args"][1:3]
            def start(self):
                live._latest(self.channel, {"terminal": True, "reason": "target-process-ended"})
                if self.stop.is_set():
                    raise AssertionError("Main must be allowed to consume terminal packet")
            def join(self):
                if not self.stop.is_set():
                    raise AssertionError("Main must cancel before joining")
                events.append("join")
        presenter = types.SimpleNamespace(PhysicalWaypointOverlay=Overlay, target_snapshot=self.snapshot)
        with patch.dict("sys.modules", {"scripts.physical_waypoint_overlay": presenter}), \
             patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(live.physical, "select_physical", return_value=self.selection), \
             patch.object(live.threading, "Thread", Worker), \
             patch.object(live.time, "monotonic", return_value=10.):
            result = live.run("AMD-DESKTOP", 123, self.route_path)
        self.assertEqual(result["reason"], "target-process-ended")
        self.assertLess(events.index("hide:target-process-ended"), events.index("join"))
        self.assertLess(events.index("join"), events.index("close"))


if __name__ == "__main__":
    unittest.main()
