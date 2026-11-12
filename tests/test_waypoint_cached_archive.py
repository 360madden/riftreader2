"""Default cached-route startup restores archived progress only for a fresh owner."""
import json
import time
import unittest
from types import SimpleNamespace

from scripts import physical_waypoints as app
from scripts.waypoint_progress import select_route_progress
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class CachedArchiveTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def archived_cache(self):
        self.document = {"waypoints": [["Main start", 0, 0], ["Main end", 1, 0]], "heights": [10, 10]}
        self.active = fixture.PlaybackWindowStateTests.write_checkpoint(self, self.document, "forward", 1)
        self.original = self.active.read_bytes()
        self.archive = self.path / "artifacts" / "waypoint-progress"
        select_route_progress(self.active, self.archive, {"waypoints": [["Beacon", 2, 0]]}, fixture.TEST_IDENTITY)
        self.slot, = self.archive.glob("*.json")
        self.cache = self.path / "artifacts" / "waypoint-last-route.json"
        self.cache.write_text(json.dumps({"version": 1, "route": self.document}), encoding="utf-8")

    def adapter(self, identity=None):
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        return SimpleNamespace(pid=123, initial_pose=pose, read=lambda **kwargs: pose,
                               binding={"runtimeIdentity": dict(fixture.TEST_IDENTITY if identity is None else identity)})

    def test_cached_route_restores_exact_archived_cursor_on_default_startup(self):
        self.archived_cache()
        self.launch(self.adapter())
        self.assertEqual(self.original, self.active.read_bytes())
        self.assertFalse(self.slot.exists())
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))

    def test_unknown_identity_defers_until_fresh_idle_observation(self):
        self.archived_cache()
        adapter = self.adapter({})
        self.launch(adapter)
        self.assertFalse(self.active.exists())
        self.assertEqual(self.original, self.slot.read_bytes())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        adapter.binding["runtimeIdentity"] = dict(fixture.TEST_IDENTITY)
        adapter.initial_pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fresh fake")
        adapter.read = lambda **kwargs: adapter.initial_pose
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while not self.active.exists() and time.monotonic() < deadline:
            self.roots[0].update()
            time.sleep(.01)
        self.assertEqual(self.original, self.active.read_bytes())
        self.assertFalse(self.slot.exists())

    def test_bad_measurement_cache_cannot_promote_geometry_matching_archive(self):
        self.archived_cache()
        bad = dict(self.document, pointMeasurements=[{"broken": True}, None])
        self.cache.write_text(json.dumps({"version": 1, "route": bad}), encoding="utf-8")
        self.launch(self.adapter())
        self.assertFalse(self.active.exists())
        self.assertEqual(self.original, self.slot.read_bytes())
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, fixture.ttk.Treeview))
        self.assertEqual((), table.get_children())

    def test_wrong_owner_does_not_promote_other_players_archive(self):
        self.archived_cache()
        self.launch(self.adapter(dict(fixture.TEST_IDENTITY, unitKey="other")))
        self.assertFalse(self.active.exists())
        self.assertEqual(self.original, self.slot.read_bytes())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))

    def test_stale_pose_does_not_promote_archive(self):
        self.archived_cache()
        adapter = self.adapter()
        adapter.initial_pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic() - 10, "stale fake")
        adapter.read = lambda **kwargs: adapter.initial_pose
        self.launch(adapter)
        self.assertFalse(self.active.exists())
        self.assertEqual(self.original, self.slot.read_bytes())

    def test_manual_unknown_receipts_do_not_block_archive_recovery(self):
        self.archived_cache()
        partial = dict(self.document, pointMeasurements=[None, None])
        self.cache.write_text(json.dumps({"version": 1, "route": partial}), encoding="utf-8")
        self.launch(self.adapter())
        self.assertEqual(self.original, self.active.read_bytes())
        self.assertFalse(self.slot.exists())

    def test_explicit_route_takes_precedence_over_cached_archive(self):
        self.archived_cache()
        explicit = self.path / "explicit.json"
        explicit.write_text(json.dumps({"waypoints": [["Explicit", 2, 0]]}), encoding="utf-8")
        self.launch(self.adapter(), explicit)
        self.assertFalse(self.active.exists())
        self.assertEqual(self.original, self.slot.read_bytes())
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, fixture.ttk.Treeview))
        self.assertEqual("Explicit", table.item(table.get_children()[0], "values")[0])

    def test_invalid_active_checkpoint_is_preserved_during_cache_fallback(self):
        self.archived_cache()
        self.active.write_text("invalid checkpoint", encoding="utf-8")
        before = self.active.read_bytes()
        self.launch(self.adapter())
        self.assertEqual(before, self.active.read_bytes())
        self.assertEqual(self.original, self.slot.read_bytes())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))


if __name__ == "__main__":
    unittest.main()
