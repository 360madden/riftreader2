import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from scripts.waypoint_breadcrumbs import BreadcrumbTrail
from scripts.waypoint_beacon_pose import SOURCE, QUALIFICATION
from scripts.waypoint_measurements import parse_projection_route
from scripts.waypoint_limits import MAX_ROUTE_DISTANCE, MAX_WAYPOINTS
from scripts.live_physical_waypoints import load_route
from scripts.waypoint_recording import RecordingError


def packet(i, x=0, z=0, y=0, **changes):
    result = dict(version=1, status="fresh", sessionId="reader-1", sequence=i,
        target=dict(hostName="AMD-DESKTOP", processId=5, processStartUtcTicks="123",
                    executablePath="C:/rift.exe", executableSha256="a"*64, hwnd=8),
        playerKey="123", source=SOURCE, qualification=QUALIFICATION,
        position=dict(x=x,y=y,z=z), bearing=0, acquiredMonotonic=100.+i,
        sampledAtUtc=f"2026-11-13T01:{i//60:02d}:{i%60:02d}+00:00")
    result.update(changes)
    return result


class BreadcrumbTests(unittest.TestCase):
    def trail(self, **options):
        trail=BreadcrumbTrail(**options)
        trail.start(packet(1))
        return trail

    def test_corners_xyz_source_time_and_existing_loader(self):
        trail=self.trail()
        for p in (packet(1),packet(2,1),packet(3,2,y=1),packet(4,2,z=1),packet(5,2,z=2)):
            self.assertTrue(trail.observe(p))
        document=trail.export_segment()
        self.assertEqual(document["waypoints"][0][1:],[0,0])
        self.assertIn([2,0], [p[1:] for p in document["waypoints"]])
        self.assertIn(1,document["heights"])
        for receipt in document["pointMeasurements"]:
            self.assertEqual(receipt["observedAtUtc"],packet(receipt["sequence"])["sampledAtUtc"])
            self.assertEqual(receipt["source"],SOURCE)
        self.assertEqual(parse_projection_route(document)["provenanceKind"],"independent-point-observations")
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"segment.json"
            trail.save_segment(path)
            self.assertEqual(load_route(path)["document"],document)

    def test_gap_and_missing_samples_never_bridge(self):
        trail=self.trail()
        trail.observe(packet(1)); trail.observe(packet(2,1))
        trail.unavailable("stale")
        trail.observe(packet(3,2)); trail.observe(packet(4,3))
        trail.observe(packet(8,4)); trail.observe(packet(9,5))
        segments=trail.snapshot()["segments"]
        self.assertEqual([[p["x"] for p in s["points"]] for s in segments],[[0,1],[2,3],[4,5]])
        self.assertEqual([p[1] for p in trail.export_segment()["waypoints"]],[4,5])

    def test_segment_summaries_report_export_readiness_and_split_indices(self):
        trail=self.trail()
        trail.observe(packet(1))
        stationary=trail.segment_summaries()
        self.assertEqual([(s["index"],s["number"]) for s in stationary],[(0,1)])
        self.assertFalse(stationary[0]["exportable"])
        self.assertIn("no useful movement",stationary[0]["exportReason"])
        self.assertIsNone(stationary[0]["waypointCount"])

        trail.observe(packet(2,1))
        moved=trail.segment_summaries()
        self.assertTrue(moved[0]["exportable"])
        self.assertIsNone(moved[0]["exportReason"])
        self.assertEqual(moved[0]["waypointCount"],2)
        self.assertEqual(moved[0]["pointCount"],2)
        self.assertEqual(moved[0]["observedPathLength"],1.)

        trail.unavailable("gap")
        trail.observe(packet(3,2))
        split=trail.segment_summaries()
        self.assertEqual([s["number"] for s in split],[1,2])
        self.assertEqual(split[1]["reason"],"gap")
        self.assertFalse(split[1]["exportable"])
        self.assertIn("no useful movement",split[1]["exportReason"])

        trail.clear()
        self.assertEqual(trail.segment_summaries(),[])

    def test_teleport_and_epoch_owner_split(self):
        trail=self.trail()
        trail.observe(packet(1)); trail.observe(packet(2,100))
        trail.observe(packet(1,101,sessionId="reader-2"))
        other=packet(2,102,sessionId="reader-2",playerKey="456")
        trail.observe(other)
        self.assertEqual(len(trail.snapshot()["segments"]),4)
        self.assertEqual(trail.snapshot()["segments"][-1]["identity"]["unitKey"],"456")

    def test_duplicates_and_timestamps_do_not_advance(self):
        trail=self.trail(); first=packet(1)
        trail.observe(first)
        self.assertFalse(trail.observe(first))
        self.assertFalse(trail.observe(packet(2,1,acquiredMonotonic=101)))
        self.assertFalse(trail.observe(packet(2,1,sampledAtUtc=first["sampledAtUtc"])))
        self.assertEqual(trail.snapshot()["pointCount"],1)
        trail.unavailable("gap")
        self.assertFalse(trail.observe(first))
        trail.observe(packet(2,1))
        self.assertEqual(len(trail.snapshot()["segments"]),2)

    def test_stop_clear_bounded_retention_and_snapshot_copy(self):
        trail=self.trail(max_points=4)
        for i in range(1,8): trail.observe(packet(i,i))
        state=trail.snapshot()
        self.assertEqual(state["pointCount"],4)
        self.assertEqual(state["discardedPointCount"],3)
        state["segments"][0]["points"].clear()
        self.assertEqual(trail.snapshot()["pointCount"],4)
        trail.stop(); self.assertFalse(trail.observe(packet(8,8)))
        trail.clear(); self.assertEqual(trail.snapshot()["segments"],[])
        with self.assertRaises(RecordingError): trail.export_segment()

    def test_length_limit_uses_real_shared_endpoint(self):
        trail=self.trail()
        step=10
        count=int(MAX_ROUTE_DISTANCE/step)+3
        for i in range(1,count): trail.observe(packet(i,step*i))
        segments=trail.snapshot()["segments"]
        self.assertEqual(len(segments),2)
        self.assertEqual(segments[0]["points"][-1],segments[1]["points"][0])
        self.assertEqual(segments[1]["reason"],"route-length-limit")
        self.assertLessEqual(segments[0]["observedPathLength"],MAX_ROUTE_DISTANCE)
        self.assertLessEqual(segments[1]["observedPathLength"],MAX_ROUTE_DISTANCE)
        parse_projection_route(trail.export_segment())

    def test_invalid_unmeasured_pose_rejected(self):
        trail=self.trail()
        self.assertFalse(trail.observe(packet(1,position=dict(x=0,y=None,z=0))))
        self.assertFalse(trail.observe(packet(2,qualification="estimate")))
        self.assertEqual(trail.snapshot()["pointCount"],0)

    def test_vertical_corner_and_out_back_retained(self):
        trail=self.trail()
        for p in (packet(1),packet(2,1,y=1),packet(3,2),packet(4,1),packet(5)):
            trail.observe(p)
        doc=trail.export_segment()
        self.assertIn(1,doc["heights"])
        self.assertEqual([p[1] for p in doc["waypoints"]],[0,1,2,0])

    def test_gradual_height_curve_and_colocated_height_are_preserved(self):
        trail=self.trail()
        for i in range(1,10):
            trail.observe(packet(i, i*.2, y=.2*math.sin((i-1)*math.pi/8)))
        document=trail.export_segment()
        self.assertGreater(max(document["heights"]),.15)
        trail=self.trail()
        for p in (packet(1),packet(2,1),packet(3,1,y=1),packet(4,2,y=1)):
            trail.observe(p)
        doc=trail.export_segment()
        self.assertIn((1.,0.),list(zip([p[1] for p in doc["waypoints"]],doc["heights"])))
        self.assertIn((1.,1.),list(zip([p[1] for p in doc["waypoints"]],doc["heights"])))

    def test_source_clock_regression_and_more_than_twenty_corners_export(self):
        trail=self.trail()
        trail.observe(packet(2))
        self.assertFalse(trail.observe(packet(3,1,sampledAtUtc=packet(1)["sampledAtUtc"])))
        trail=self.trail()
        for i in range(1,32):
            trail.observe(packet(i,i*.1,z=(i%2)*.1))
        document=trail.export_segment()
        self.assertGreater(len(document["waypoints"]),20)
        self.assertLessEqual(len(document["waypoints"]),MAX_WAYPOINTS)
        parse_projection_route(document)

    def test_more_than_twenty_units_export_without_synthesized_points(self):
        trail=self.trail()
        for i in range(1,32):
            trail.observe(packet(i,i))
        segment=trail.snapshot()["segments"][0]
        source=segment["points"]
        document=trail.export_segment()
        self.assertGreater(segment["observedPathLength"],20)
        self.assertEqual([row[1] for row in document["waypoints"]], [1, 6, 11, 16, 21, 26, 31])
        actual_positions = {(point["x"], point["y"], point["z"]) for point in source}
        for row, height in zip(document["waypoints"], document["heights"]):
            self.assertIn((row[1], height, row[2]), actual_positions)
        parse_projection_route(document)

    def test_stationary_heartbeat_keeps_walk_and_real_source_times(self):
        trail=self.trail()
        origin=datetime(2026,11,13,tzinfo=timezone.utc)
        def sample(i,x):
            return packet(i,x,acquiredMonotonic=100+i*.2,
                          sampledAtUtc=(origin+timedelta(seconds=i*.2)).isoformat())
        for i in range(1,11):
            self.assertTrue(trail.observe(sample(i,i*.1)))
        before=trail.snapshot()["segments"][0]["points"][:]
        # Six minutes at 5 Hz would otherwise nearly fill the entire cap.
        for i in range(11,1811):
            trail.observe(sample(i,1.))
        state=trail.snapshot()
        self.assertLess(state["pointCount"],400)
        self.assertEqual(state["discardedPointCount"],0)
        self.assertEqual(state["segments"][0]["points"][:10],before)
        trail.observe(sample(1811,1.1))
        document=trail.export_segment()
        self.assertEqual(document["waypoints"][0][1],.1)
        self.assertEqual(document["waypoints"][-1][1],1.1)
        for receipt in document["pointMeasurements"]:
            self.assertEqual(receipt["observedAtUtc"],sample(receipt["sequence"],0)["sampledAtUtc"])

    def test_stationary_skip_updates_admission_without_hiding_gap(self):
        trail=self.trail()
        trail.observe(packet(1))
        self.assertFalse(trail.observe(packet(2,acquiredMonotonic=101.2)))
        self.assertFalse(trail.observe(packet(2,1,acquiredMonotonic=101.3)))
        trail.unavailable("missing")
        self.assertTrue(trail.observe(packet(3,acquiredMonotonic=101.4)))
        self.assertEqual(len(trail.snapshot()["segments"]),2)
        self.assertTrue(trail.observe(packet(4,acquiredMonotonic=105.)))
        self.assertEqual(len(trail.snapshot()["segments"]),3)

    def test_small_movements_never_coalesce_and_custom_heartbeat_exports(self):
        trail=self.trail(max_gap_seconds=.5)
        for i in range(1,31):
            trail.observe(packet(i,i*1e-7,acquiredMonotonic=100+i*.1))
        self.assertEqual(trail.snapshot()["pointCount"],30)
        for i in range(31,101):
            trail.observe(packet(i,30e-7,acquiredMonotonic=100+i*.1))
        points=trail.snapshot()["segments"][0]["points"]
        self.assertTrue(all(b["acquired"]-a["acquired"] <= .5 for a,b in zip(points,points[1:])))

    def test_slow_poll_after_skipped_sample_keeps_real_timing_endpoint(self):
        trail=self.trail()
        trail.observe(packet(1))
        trail.observe(packet(2,acquiredMonotonic=101.8))
        trail.observe(packet(3,1,acquiredMonotonic=104.5))
        points=trail.snapshot()["segments"][0]["points"]
        self.assertEqual([p["acquired"] for p in points],[101.,101.8,104.5])
        parse_projection_route(trail.export_segment())


if __name__ == "__main__": unittest.main()
