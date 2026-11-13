"""Owned file feedback changes display only; no duplicate native sampler or input authority."""
from datetime import datetime, timedelta, timezone
import json
import time
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_beacon_pose import write_pose, write_unavailable
from tests import test_waypoint_marker_sync as sync
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class BeaconPoseWindowTests(unittest.TestCase):
    setUp = sync.MarkerSyncTests.setUp
    cleanup_gui = sync.MarkerSyncTests.cleanup_gui
    widgets = sync.MarkerSyncTests.widgets
    button = sync.MarkerSyncTests.button
    launch = sync.MarkerSyncTests.launch
    enter = sync.MarkerSyncTests.enter

    def ready(self):
        self.pose_tooltips = {}
        self.stack.enter_context(patch("scripts.waypoint_recent_display.attach_path_tooltip",
            side_effect=lambda widget, getter: self.pose_tooltips.__setitem__(widget, getter)))
        sync.MarkerSyncTests.ready(self)
        self.adapter.target.update(hostName="AMD-DESKTOP", executablePath=r"C:\RIFT\rift_x64.exe")
        self.reader = Mock(return_value=app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "idle fake"))
        self.adapter.read = self.reader
        self.initial_pose = object()
        self.adapter.initial_pose = self.initial_pose
        self.pose_label = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Label)
                               and w["textvariable"] and str(self.root.getvar(w["textvariable"])).startswith(("Position ", "X ")))

    def header(self):
        return str(self.root.getvar(self.pose_label["textvariable"]))

    def pose_metadata(self):
        return json.loads(self.pose_tooltips[self.pose_label]())

    def pump_until(self, predicate, timeout=1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return
            time.sleep(.01)
        self.fail("beacon display did not reach expected state: " + self.header())

    def packet(self, sequence=1, *, x=2, y=11, z=3, bearing=45, old=0, unit="player"):
        stamp = (datetime.now(timezone.utc) - timedelta(seconds=old)).isoformat()
        return write_pose(self.owned.pose_path, dict(target=self.adapter.target, acquiredMonotonic=time.monotonic(),
            playerPose=dict(playerKey=unit, position=dict(x=x, y=y, z=z), bearing=bearing, sampledAtUtc=stamp)), sequence)

    def test_fresh_owned_pose_changes_header_radar_and_facing_without_promoting_authority(self):
        self.ready()
        packet = self.packet()
        with patch.object(app, "draw_route", wraps=app.draw_route) as draw:
            self.pump_until(lambda: "X 2.000" in self.header())
            view = draw.call_args.args[1]
            self.assertEqual((2, 3, 45), (view.x, view.z, view.bearing))
        metadata = self.pose_metadata()
        self.assertEqual(packet["sampledAtUtc"], metadata["sampledAtUtc"])
        self.assertEqual(packet["source"], metadata["source"])
        self.assertEqual("fresh", metadata["sampleStatus"])
        self.assertGreaterEqual(metadata["ageSeconds"], 0)
        self.assertIn("Y 11.000   Z 3.000   Facing 45.00\u00b0", self.header())
        self.assertIs(self.initial_pose, self.adapter.initial_pose)
        self.reader.assert_not_called()
        self.assertFalse((self.path / "artifacts" / "waypoint-current-progress.json").exists())

    def test_repeat_packet_does_not_retimestamp_then_ages_out_and_clears_radar(self):
        self.ready()
        packet = self.packet(old=.4)
        self.pump_until(lambda: "X 2.000" in self.header())
        variable = fixture.tk.StringVar(master=self.root, name=str(self.pose_label["textvariable"]))
        writes = Mock()
        variable.trace_add("write", writes)
        deadline = time.monotonic() + .25
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        writes.assert_not_called()
        with patch.object(app, "draw_route", wraps=app.draw_route) as draw:
            self.pump_until(lambda: "beacon-pose-stale-or-future" in self.header())
            self.assertIsNone(draw.call_args.args[1])
        self.assertEqual(packet["sampledAtUtc"], self.pose_metadata()["sampledAtUtc"])
        self.assertNotIn("updated ", self.header())
        self.reader.assert_not_called()

    def test_missing_wrong_owner_and_unavailable_packets_fail_closed(self):
        self.ready()
        self.pump_until(lambda: "Position unavailable \u2014" in self.header())
        self.packet()
        self.pump_until(lambda: "X 2.000" in self.header())
        self.packet(2, unit="other")
        self.pump_until(lambda: "session-or-owner-mismatch" in self.header())
        self.packet(3, x=4)
        self.pump_until(lambda: "X 4.000" in self.header())
        write_unavailable(self.owned.pose_path, self.adapter.target, "player", 4, "fresh pose withheld")
        self.pump_until(lambda: "fresh pose withheld" in self.header())
        self.reader.assert_not_called()

    def test_hide_clears_stream_display_then_resumes_regular_idle_read(self):
        self.ready()
        self.packet()
        self.pump_until(lambda: "X 2.000" in self.header())
        self.button("Hide markers").invoke()
        self.child.returncode = 0
        self.pump_until(lambda: "beacon reader ended" in self.header())
        self.pump_until(lambda: self.reader.called, timeout=3)
        self.pump_until(lambda: "X 0.000" in self.header())
        self.assertEqual("existing-idle-reader", self.pose_metadata()["source"])
        self.assertIn("X 0.000", self.header())

    def test_repeated_same_payload_redraws_do_not_starve_pending_route_update(self):
        self.ready()
        self.packet()
        self.pump_until(lambda: "X 2.000" in self.header())
        self.enter("Timed add", 7, 1)
        self.button("Add X / Z").invoke()
        deadline = time.monotonic() + .45
        arrived = False
        import json
        while time.monotonic() < deadline:
            self.table.selection_set(self.table.get_children()[-1])
            self.root.update()
            if len(json.loads(self.owned.route_updates_path.read_text())["route"]["waypoints"]) == 8:
                arrived = True
                break
            time.sleep(.02)
        self.assertTrue(arrived, "unchanged selection/pose redraws reset the route debounce")
        self.assertEqual(1, self.popen.call_count)


if __name__ == "__main__":
    unittest.main()
