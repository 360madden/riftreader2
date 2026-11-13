"""Focused offline coverage for live marker-route revisions; no native process or UI input."""
from copy import deepcopy
import json
from pathlib import Path
import queue
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from scripts import live_physical_waypoints as live
from scripts.waypoint_progress import write_json_atomic
from tests import test_live_physical_waypoints as feed_fixture


class Clock:
    def __init__(self, value=10.):
        self.value = value
    def __call__(self):
        return self.value
    def advance(self):
        self.value += .21


class LiveRouteUpdateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = feed_fixture.FeedTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.identity = deepcopy(self.fixture.route["identity"])
        self.updates = (self.root / "updates.json").absolute()
        self.clock = Clock()

    def publish(self, document, landmark=None):
        write_json_atomic(self.updates, {"route": document, "landmarkNumber": landmark})

    def provider(self, document, landmark=None):
        self.publish(document, landmark)
        route, selected = live.load_route_update(self.updates, self.identity)
        self.fixture.path.write_text(json.dumps(self.fixture.native))
        return live.ProjectionProvider(
            self.fixture.selection, route, self.fixture.snapshot, read=self.fixture.read,
            clock=self.clock, utcnow=lambda: self.fixture.now, max_age=.8,
            landmark_number=selected, route_updates_file=self.updates)

    def frame(self, provider, *, values=None):
        before = self.fixture.snapshot.return_value
        report = self.fixture.native
        if values is None:
            return provider.build_frame(report, self.clock(), before, stream=True)
        with patch.object(live.physical, "_native_values", return_value=values):
            return provider.build_frame(report, self.clock(), before, stream=True)

    @staticmethod
    def map_route(rows):
        return {"waypoints": [list(row) for row in rows], "heights": [None] * len(rows),
                "pointMeasurements": [None] * len(rows)}

    def test_add_rename_move_reorder_remove_clear_readd_keeps_packets_immutable(self):
        initial = self.map_route([["A", 7427, 2946]])
        provider = self.provider(initial, 1)
        first = self.frame(provider)
        first_packet = live._frame_packet(provider, first)
        original_revision = first["routeRevision"]
        original_document = deepcopy(first_packet["route"]["document"])

        revisions = []
        updates = [
            (self.map_route([["A", 7427, 2946], ["B", 7428, 2947]]), 2),       # add
            (self.map_route([["Renamed", 7427, 2946], ["B", 7428, 2947]]), 2), # rename
            (self.map_route([["Renamed", 7430, 2950], ["B", 7428, 2947]]), 1), # move
            (self.map_route([["B", 7428, 2947], ["Renamed", 7430, 2950]]), 2), # reorder
            (self.map_route([["Renamed", 7430, 2950]]), 1),                     # remove
            ({"waypoints": [], "heights": [], "pointMeasurements": []}, None),# clear
            (self.map_route([["Again", 7431, 2951]]), 1),                       # re-add
        ]
        for document, landmark in updates:
            self.publish(document, landmark)
            self.clock.advance()
            frame = self.frame(provider)
            revisions.append(frame["routeRevision"])
            self.assertEqual([point[0] for point in provider.route["document"].get("waypoints", [])],
                             [point[0] for point in document["waypoints"]])
            self.assertEqual(provider.landmark_number, landmark)

        self.assertEqual(len(set(revisions + [original_revision])), len(revisions) + 1)
        self.assertEqual(provider.route_update_count, len(updates))
        self.assertEqual(first_packet["route"]["document"], original_document)
        self.assertEqual(first_packet["frame"]["routeRevision"], original_revision)
        self.assertEqual(first_packet["frame"]["points"][0]["label"], "A")

    def test_invalid_or_foreign_update_retains_last_revision_then_repair_recovers(self):
        valid = self.map_route([["Stable", 7427, 2946]])
        provider = self.provider(valid)
        first = self.frame(provider)
        revision, route = provider.route_revision, provider.route

        malformed = self.root / "malformed-update.tmp"
        malformed.write_text("{broken", encoding="utf-8")
        malformed.replace(self.updates)
        self.clock.advance()
        with self.assertRaisesRegex(ValueError, "route-update-unavailable"):
            self.frame(provider)
        self.assertIs(provider.route, route)
        self.assertEqual(provider.route_revision, revision)

        foreign = deepcopy(self.fixture.route_document)
        foreign["recording"]["identity"]["runtimeIdentity"]["unitKey"] = "foreign-player"
        self.publish(foreign)
        self.clock.advance()
        with self.assertRaisesRegex(ValueError, "route-update-unavailable"):
            self.frame(provider)
        self.assertEqual(provider.route_revision, revision)
        self.assertEqual(first["points"][0]["label"], "Stable")

        repaired = self.map_route([["Repaired", 7429, 2949]])
        self.publish(repaired)
        self.clock.advance()
        recovered = self.frame(provider)
        self.assertNotEqual(recovered["routeRevision"], revision)
        self.assertIsNone(provider.route_update_error)
        self.assertEqual(recovered["points"][0]["label"], "Repaired")

    def test_startup_height_stays_frozen_across_revisions(self):
        provider = self.provider(self.map_route([["First", 7427, 2946]]))
        first = self.frame(provider)
        startup_y = first["points"][0]["displayHeightCandidate"]
        values = live.physical._native_values("facing", self.fixture.native)
        values["positionXYZCandidate"]["y"] += 50

        from scripts.waypoint_measurements import measurement
        measured = {"waypoints": [["Measured", 7430, 2950], ["Nearby", 7431, 2951]],
                    "heights": [880, None],
                    "pointMeasurements": [measurement(
                        dict(x=7430, y=880, z=2950), self.identity, "fixture.json",
                        "2026-11-12T20:00:00+00:00"), None]}
        self.publish(measured)
        self.clock.advance()
        nearest = self.frame(provider, values=values)
        self.assertEqual([point["displayHeightCandidate"] for point in nearest["points"]], [880, 880])
        self.assertEqual(nearest["points"][1]["displayHeightKind"], "nearest-measured-estimate")

        self.publish(self.map_route([["Second", 7430, 2950], ["Third", 7431, 2951]]))
        self.clock.advance()
        second = self.frame(provider, values=values)
        self.assertEqual([point["displayHeightCandidate"] for point in second["points"]],
                         [startup_y, startup_y])
        self.assertEqual([point["displayHeightKind"] for point in second["points"]],
                         ["startup-player-estimate", "startup-player-estimate"])
        self.assertEqual(provider._startup_player_y, startup_y)

    def test_one_stream_child_projects_three_route_revisions_without_restart(self):
        provider = self.provider(self.map_route([["One", 7427, 2946]]))
        packets = []
        for sequence in range(3):
            packet = self.fixture.stream_packet()
            packet["sequence"] = sequence
            packets.append(packet)
        packets.append({"recordType": "native-current-facing-stream-end/1", "status": "complete",
                        "requestedSamples": 3, "completedSamples": 3})
        child = self.fixture.child(packets)
        launch = Mock(return_value=child)
        provider.stream_row_timing = Mock(side_effect=[(10., 1), (10.21, 2), (10.42, 3)])
        original_build = provider.build_frame
        calls = 0
        def build(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.publish(self.map_route([["Two", 7428, 2947], ["Three", 7429, 2948]]), 2)
                self.clock.advance()
            elif calls == 3:
                self.publish(self.map_route([["Final", 7430, 2949]]), 1)
                self.clock.advance()
            return original_build(*args, **kwargs)
        provider.build_frame = Mock(side_effect=build)
        channel, counts = queue.Queue(maxsize=1), {"acquired": 0, "failures": 0}
        published = []
        actual_latest = live._latest
        def latest(target, packet):
            published.append(packet)
            actual_latest(target, packet)
        with patch.object(live.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(live, "_latest", side_effect=latest):
            live.stream_burst(provider, channel, threading.Event(), counts,
                              popen=launch, samples=3)
        launch.assert_called_once()
        frames = [packet for packet in published if "frame" in packet]
        self.assertEqual(len(frames), 3)
        self.assertEqual(len({packet["frame"]["routeRevision"] for packet in frames}), 3)
        self.assertEqual([[point["label"] for point in packet["frame"]["points"]] for packet in frames],
                         [["One"], ["Two", "Three"], ["Final"]])
        self.assertEqual(counts["acquired"], 3)


if __name__ == "__main__":
    unittest.main()
