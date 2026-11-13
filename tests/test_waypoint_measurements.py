"""Offline provenance admission, including honest conversion after GUI edits."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.waypoint_measurements import (measurement, document_measurements,
                                           parse_marker_projection_route, parse_projection_route)
from scripts.live_physical_waypoints import load_route


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.identity = dict(runtimeIdentity=dict(machine="AMD-DESKTOP", gameBuildSha256="a" * 64,
                             unitKey="18446744073709551615", processId=10, processStartUtcTicks="123"))
        self.xyz = dict(x=1.12345649, y=8.12345649, z=-2.12345649)
        self.receipt = measurement(self.xyz, self.identity, "native-a.json", "2026-11-12T20:00:00Z")
        self.document = dict(waypoints=[["First", 1.123456, -2.123456]], heights=[8.123456],
                             pointMeasurements=[self.receipt])

    def test_measured_roundtrip_preserves_exact_xyz_and_historical_epoch(self):
        parsed = parse_projection_route(self.document)
        self.assertEqual(parsed["provenanceKind"], "independent-point-observations")
        self.assertEqual(parsed["identity"], self.identity["runtimeIdentity"])
        retained = parsed["recordingIdentity"]["pointMeasurements"][0]
        self.assertEqual(retained["position"], self.xyz)
        self.assertEqual(document_measurements(self.document), [self.receipt])
        retained["identity"]["runtimeIdentity"]["processId"] = 999
        self.assertEqual(self.receipt["identity"]["runtimeIdentity"]["processId"], 10)

    def test_selected_target_receipt_preserves_static_xyz_observer_and_lossless_key(self):
        position = deepcopy(self.xyz)
        receipt = measurement(position, self.identity, "target-native.json", "2026-11-12T20:00:00Z",
                              kind="native-selected-target-position", target_key="9223372045797034555")
        position["y"] = 999
        document = dict(self.document, pointMeasurements=[receipt])
        parsed = parse_projection_route(document)
        retained = parsed["recordingIdentity"]["pointMeasurements"][0]
        self.assertEqual(retained["targetKey"], "9223372045797034555")
        self.assertIsInstance(retained["targetKey"], str)
        self.assertEqual(retained["position"], self.xyz)
        self.assertEqual(parsed["identity"], self.identity["runtimeIdentity"])
        self.assertEqual(document_measurements(json.loads(json.dumps(document))), [receipt])
        self.assertIn("Static selected-target", retained["qualification"])
        self.assertIn("no live-follow", retained["qualification"])
        self.assertNotIn("recording", document)

    def test_selected_target_key_requires_positive_canonical_uint64_string(self):
        for key in (None, True, False, 42, 42., -1, "-1", "0", "01", " 42", "+42", "4.2",
                    "18446744073709551616", "", "9" * 200):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "target-key-required"):
                measurement(self.xyz, self.identity, "target.json", "2026-11-12T20:00:00Z",
                            kind="native-selected-target-position", target_key=key)

    def test_selected_target_malformed_saved_receipt_and_other_kind_key_refuse(self):
        receipt = measurement(self.xyz, self.identity, "target.json", "2026-11-12T20:00:00Z",
                              kind="native-selected-target-position", target_key="18446744073709551615")
        for change in (lambda r: r.update(targetKey=9223372045797034555.),
                       lambda r: r.pop("qualification"), lambda r: r.update(kind="native-player-position")):
            invalid = deepcopy(receipt)
            change(invalid)
            document = dict(self.document, pointMeasurements=[invalid])
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_projection_route(document)
            self.assertEqual(document_measurements(document), [None])
        with self.assertRaisesRegex(ValueError, "kind-mismatch"):
            measurement(self.xyz, self.identity, "a", "2026-11-12T20:00:00Z", target_key="42")
        with self.assertRaisesRegex(ValueError, "kind-unsupported"):
            measurement(self.xyz, self.identity, "a", "2026-11-12T20:00:00Z", kind="unknown")

    def test_epochs_may_differ_but_host_build_player_must_match(self):
        second = deepcopy(self.receipt)
        second["identity"]["runtimeIdentity"]["processId"] = 20
        self.document["waypoints"] *= 2
        self.document["heights"] *= 2
        self.document["pointMeasurements"].append(second)
        self.assertEqual(len(parse_projection_route(self.document)["points"]), 2)
        for field, value in (("machine", "OTHER"), ("gameBuildSha256", "b" * 64), ("unitKey", "42")):
            with self.subTest(field=field):
                changed = deepcopy(self.document)
                changed["pointMeasurements"][1]["identity"]["runtimeIdentity"][field] = value
                with self.assertRaisesRegex(ValueError, "identity-mismatch"):
                    parse_projection_route(changed)

    def test_missing_receipt_height_and_coordinate_mismatch_refuse(self):
        for change in (lambda d: d.pop("pointMeasurements"), lambda d: d.update(heights=[None]),
                       lambda d: d["waypoints"][0].__setitem__(1, 1.2),
                       lambda d: d["pointMeasurements"][0].update(position=dict(x=1, y=float("nan"), z=2))):
            with self.subTest(change=change):
                changed = deepcopy(self.document)
                change(changed)
                with self.assertRaises(ValueError):
                    parse_projection_route(changed)
                self.assertEqual(document_measurements(changed), [None])

    def test_partial_measurements_remain_aligned_for_gui(self):
        self.document["waypoints"].append(["Unknown", 5, 6])
        self.document["heights"].append(None)
        self.document["pointMeasurements"].append(None)
        self.assertEqual(document_measurements(self.document), [self.receipt, None])
        with self.assertRaises(ValueError):
            parse_projection_route(self.document)

    def test_marker_preview_admits_mixed_seven_points_without_mutating_source(self):
        document = {"waypoints": [[f"P{i}", i, -i] for i in range(1, 8)],
                    "heights": [10, None, None, None, 20, None, None],
                    "pointMeasurements": [None] * 7}
        document["pointMeasurements"][0] = measurement(
            dict(x=1, y=10, z=-1), self.identity, "one.json", "2026-11-12T20:00:00Z")
        document["pointMeasurements"][4] = measurement(
            dict(x=5, y=20, z=-5), self.identity, "five.json", "2026-11-12T20:00:01Z")
        original = deepcopy(document)

        parsed = parse_marker_projection_route(document, self.identity)

        self.assertEqual("estimated-height-beacon-preview", parsed["provenanceKind"])
        self.assertEqual(["measured", "unresolved-estimate", "unresolved-estimate",
                          "unresolved-estimate", "measured", "unresolved-estimate",
                          "unresolved-estimate"], [point["displayHeightKind"] for point in parsed["points"]])
        self.assertEqual([10, None, None, None, 20, None, None],
                         [point["xyz"]["y"] for point in parsed["points"]])
        self.assertEqual(2, parsed["recordingIdentity"]["measuredPointCount"])
        self.assertEqual([1, 5], parsed["recordingIdentity"]["measuredPointNumbers"])
        self.assertEqual(original, document)

    def test_marker_preview_zero_measurements_uses_expected_identity_only(self):
        document = {"waypoints": [["A", 1, 2], ["B", 3, 4]]}
        parsed = parse_marker_projection_route(document, self.identity)
        self.assertEqual(self.identity["runtimeIdentity"], parsed["identity"])
        self.assertEqual([None, None], [point["xyz"]["y"] for point in parsed["points"]])
        self.assertEqual(0, parsed["recordingIdentity"]["measuredPointCount"])

    def test_marker_preview_empty_route_requires_explicit_opt_in(self):
        document = {"waypoints": []}
        with self.assertRaises(ValueError):
            parse_marker_projection_route(document, self.identity)
        parsed = parse_marker_projection_route(document, self.identity, allow_empty=True)
        self.assertEqual([], parsed["points"])
        self.assertEqual(self.identity["runtimeIdentity"], parsed["identity"])
        self.assertEqual("estimated-height-beacon-preview", parsed["provenanceKind"])
        self.assertEqual({"kind": "map-waypoint-beacon-preview",
                          "identity": self.identity["runtimeIdentity"],
                          "measuredPointCount": 0, "pointCount": 0, "measuredPointNumbers": []},
                         parsed["recordingIdentity"])
        for invalid in ({"waypoints": [], "heights": [1]},
                        {"waypoints": [], "pointMeasurements": [None]},
                        {"waypoints": [], "recording": {"complete": True}}):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "empty-marker"):
                parse_marker_projection_route(invalid, self.identity, allow_empty=True)

    def test_marker_preview_rejects_bad_or_foreign_receipts_but_bare_y_is_unmeasured(self):
        bare = deepcopy(self.document)
        bare["pointMeasurements"] = [None]
        parsed = parse_marker_projection_route(bare, self.identity)
        self.assertIsNone(parsed["points"][0]["xyz"]["y"])
        self.assertEqual("unresolved-estimate", parsed["points"][0]["displayHeightKind"])
        with self.assertRaises(ValueError):
            parse_projection_route(bare)

        malformed = deepcopy(self.document)
        malformed["pointMeasurements"] = [{"broken": True}]
        with self.assertRaises(ValueError):
            parse_marker_projection_route(malformed, self.identity)
        foreign = deepcopy(self.document)
        foreign["pointMeasurements"][0]["identity"]["runtimeIdentity"]["unitKey"] = "42"
        with self.assertRaisesRegex(ValueError, "owner-identity"):
            parse_marker_projection_route(foreign, self.identity)

    def test_marker_preview_preserves_strict_recorded_semantics_and_owner(self):
        parsed = parse_marker_projection_route(self.recorded(), self.identity)
        self.assertEqual("recorded-route", parsed["provenanceKind"])
        self.assertEqual("measured", parsed["points"][0]["displayHeightKind"])
        foreign = deepcopy(self.identity)
        foreign["runtimeIdentity"]["unitKey"] = "42"
        with self.assertRaisesRegex(ValueError, "owner-identity"):
            parse_marker_projection_route(self.recorded(), foreign)

    def recorded(self):
        doc = deepcopy(self.document)
        doc.pop("pointMeasurements")
        doc["recording"] = dict(version=1, complete=True, identity=self.identity,
            sources=["native-a.json", "native-b.json"], firstObservedAtUtc="2026-11-12T20:00:00Z",
            lastObservedAtUtc="2026-11-12T20:00:02Z")
        return doc

    def test_recorded_derived_receipts_preserve_interval_not_exact_time(self):
        doc = self.recorded()
        self.assertEqual(parse_projection_route(doc)["provenanceKind"], "recorded-route")
        receipts = document_measurements(doc)
        self.assertEqual(receipts[0]["kind"], "recorded-route-point")
        self.assertEqual(receipts[0]["sourceTimeKind"], "route-observation-interval")
        self.assertEqual(receipts[0]["sources"], doc["recording"]["sources"])
        doc.pop("recording")
        doc["pointMeasurements"] = receipts
        self.assertEqual(parse_projection_route(doc)["provenanceKind"], "independent-point-observations")

    def test_incomplete_recording_never_falls_back(self):
        self.document["recording"] = dict(version=1, complete=False, identity=self.identity)
        with self.assertRaisesRegex(ValueError, "complete-recorded-route-required"):
            parse_projection_route(self.document)
        self.assertEqual(document_measurements(self.document), [None])

    def test_weak_legacy_recording_stays_usable_but_not_convertible(self):
        doc = self.recorded()
        del doc["recording"]["firstObservedAtUtc"]
        self.assertEqual(len(parse_projection_route(doc)["points"]), 1)
        self.assertEqual(document_measurements(doc), [None])
        self.assertEqual(document_measurements(dict(waypoints=[["Manual", 1, 2]])), [None])

    def test_receipt_requires_utc_source_and_complete_identity(self):
        for field, value in (("observedAtUtc", "2026-11-12T20:00:00"), ("source", " "),
                             ("identity", {}), ("observedAtUtc", "2026-11-12T20:00:00-05:00")):
            changed = deepcopy(self.receipt)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                parse_projection_route(dict(self.document, pointMeasurements=[changed]))

    def test_file_loader_admits_measured_mode_with_original_document_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            path.write_text(json.dumps(self.document))
            loaded = load_route(path)
            self.assertEqual(loaded["document"], self.document)
            self.assertEqual(loaded["recordingIdentity"]["kind"], "independent-point-observations")
            self.assertEqual(len(loaded["sha256"]), 64)

    def test_measured_points_use_same_saved_frame_projection(self):
        from tests.test_plot_physical_waypoints import PlotTests
        fixture = PlotTests(methodName="test_actual_placement_uses_client_offset_and_preserves_original")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        identity = fixture.route.pop("recording")["identity"]
        fixture.route["pointMeasurements"] = [measurement(dict(x=p[1], y=y, z=p[2]), identity,
            "native-point.json", "2026-11-11T18:59:00Z")
            for p, y in zip(fixture.route["waypoints"], fixture.route["heights"])]
        original = fixture.image.read_bytes()
        result = fixture.run_render()
        self.assertEqual(result["points"][0]["ground"]["pixel"], [160, 110])
        self.assertEqual(result["recordingIdentity"]["kind"], "independent-point-observations")
        self.assertEqual(fixture.image.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
