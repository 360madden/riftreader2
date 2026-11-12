"""Actual retained-evidence validators with an injected sink; no SDK or viewer."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import types
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from scripts import export_physical_rerun as exporter
from tests import test_plot_physical_waypoints as plot_fixtures
from tests.test_physical_facing import optical_camera


def replace_projection(camera, matrix, viewport=None):
    values = list(matrix) + list(viewport or camera["viewportLeftRightTopBottom"])
    exact = [struct.unpack("<f", struct.pack("<f", value))[0] for value in values]
    camera["projectionRowMajor"] = exact[:16]
    camera["viewportLeftRightTopBottom"] = exact[16:]
    camera["projectionRawBits"] = [struct.unpack("<I", struct.pack("<f", value))[0] for value in exact]


class FakeSink:
    def __init__(self, path):
        self.events, self.closed, self.flushed = [], False, False
        Path(path).write_bytes(b"fake-rrd-test-payload")
    def log(self, entity, kind, data, **kwargs):
        self.events.append((entity, kind, data, kwargs))
    def configure_view(self, captures, *, display_camera=None):
        self.captures = captures
        self.display_camera = display_camera
    def flush(self):
        self.flushed = True
    def close(self):
        self.closed = True


class ExportTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing synthetic stable native/WGC/titlebar-offset fixture.
        self.fixture = plot_fixtures.PlotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.run_render()
        self.root = self.fixture.root
        self.route = self.root / "route.json"
        self.observation = self.root / "observation.json"
        self.output = self.root / "evidence.rrd"
        self.sinks = []
    def sink(self, path):
        sink = FakeSink(path)
        self.sinks.append(sink)
        return sink
    def run_export(self, observations=None, **kwargs):
        return exporter.export(self.route, [self.observation] if observations is None else observations,
                               self.output, sink_factory=self.sink, **kwargs)

    def test_xyz_projection_and_distinct_actual_timestamps_preserved(self):
        original = self.fixture.image.read_bytes()
        result = self.run_export()
        sink = self.sinks[0]
        route_event = next(event for event in sink.events if event[0] == "world/route/points")
        self.assertEqual(route_event[2]["positions"][0], [7427, 871, 2946])
        points = next(event for event in sink.events if event[1] == "points2d")
        self.assertEqual(points[2]["positions"][0], [160., 110.])
        capture_at = exporter.timestamp_ns("2026-11-11T19:00:00.25Z")
        self.assertEqual(points[3]["at"], capture_at)
        native_events = [event for event in sink.events if event[0] == "world/player"]
        self.assertEqual([event[3]["at"] for event in native_events], [
            exporter.timestamp_ns("2026-11-11T18:59:59.9Z"), exporter.timestamp_ns("2026-11-11T19:00:00.4Z")])
        self.assertNotEqual(native_events[-1][3]["at"], capture_at)
        self.assertEqual(original, self.fixture.image.read_bytes())
        self.assertEqual(result["recordingIdentity"]["runtimeIdentity"]["processId"], 999)
        self.assertTrue(sink.flushed and sink.closed)
        self.assertEqual(sink.captures, [("/captures/0001", capture_at)])
        self.assertFalse(result["inputSent"])

    def test_route_only_and_optional_image_payload(self):
        result = self.run_export(observations=[])
        self.assertEqual(result["observationCount"], 0)
        self.assertFalse(any(event[1] == "png" for event in self.sinks[0].events))
        self.output.unlink()
        result = self.run_export(images=False)
        self.assertFalse(result["imagesIncluded"])
        self.assertFalse(any(event[1] == "png" for event in self.sinks[-1].events))
        self.assertTrue(any(event[1] == "points2d" for event in self.sinks[-1].events))

    def unit_wrapper(self, name="units", *, wrong_epoch=False, camera_changed=False):
        from tests.test_physical_unit_positions import report
        raw = report()
        row = raw["observation"]
        key = self.fixture.route["recording"]["identity"]["runtimeIdentity"]["unitKey"]
        row["selfKey"] = row["rows"][0]["unitKey"] = key
        row["rows"][0]["unitIdCandidate"] = f"u{int(key):016X}"
        target = deepcopy(self.fixture.observation["target"])
        if wrong_epoch:
            target["processStartUtcTicks"] = str(int(target["processStartUtcTicks"]) + 1)
        row["identity"] = dict(processId=target["processId"], processStartUtcTicks=int(target["processStartUtcTicks"]),
                               executableSha256=target["executableSha256"])
        if camera_changed:
            row["opticalCameraAfterCandidate"]["cameraAddressDecimal"] = "2096815868168"
            row["cameraStableCandidate"] = False
        native_path = self.root / (name + "-raw.json")
        native_path.write_text(json.dumps(raw))
        wrapper = dict(status="complete", workflow="physical", nativeRead="unit-positions",
                       ownerHost="AMD-DESKTOP", target=target, nativeOutput=native_path.name)
        path = self.root / (name + "-wrapper.json")
        path.write_text(json.dumps(wrapper))
        return path, native_path, raw, wrapper

    def test_unit_samples_keep_independent_times_keys_hashes_and_camera_change(self):
        path, native, raw, wrapper = self.unit_wrapper(camera_changed=True)
        result = self.run_export(unit_samples=[path])
        scan = result["unitSamples"][0]
        self.assertEqual(result["unitSampleCount"], 1)
        self.assertEqual(len(scan["units"]), 1)  # self excluded
        self.assertEqual(scan["units"][0]["unitKey"], "18446744073709551615")
        self.assertEqual(scan["nativeSource"]["sha256"], hashlib.sha256(native.read_bytes()).hexdigest())
        self.assertEqual(scan["wrapperSource"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        event = next(e for e in self.sinks[-1].events if e[0].startswith("world/loaded_units/") and e[1] == "points3d")
        self.assertEqual(event[2]["positions"], [[7430., 871., 2950.]])
        self.assertFalse(event[2]["show_labels"])  # Nearby samples must not obscure the route.
        self.assertEqual(event[3]["at"], exporter.timestamp_ns(raw["observation"]["rows"][1]["completedAtUtc"]))
        self.assertNotEqual(event[3]["at"], exporter.timestamp_ns("2026-11-11T19:00:00.25Z"))
        self.assertIn("not screenshot aligned", scan["qualification"])
        self.assertIn("carries forward", scan["qualification"])
        self.assertEqual(scan["coverage"]["unitsExamined"], 3)

    def test_unit_sample_capture_epoch_refuses_before_output_creation(self):
        path, _, _, _ = self.unit_wrapper(wrong_epoch=True)
        with self.assertRaisesRegex(ValueError, "capture-epoch-mismatch"):
            self.run_export(unit_samples=[path])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.sinks)
        # A route-only scene has no capture epoch to equate; stable actor/build still required.
        self.assertEqual(self.run_export(observations=[], unit_samples=[path])["unitSampleCount"], 1)

    def test_unit_sample_wrong_observer_host_build_hash_and_bits_refuse(self):
        path, native, raw, wrapper = self.unit_wrapper()
        for fault in ("host", "build", "observer", "bits", "epoch", "hash"):
            a, b = deepcopy(raw), deepcopy(wrapper)
            if fault == "host": b["ownerHost"] = "OTHER"
            if fault == "build": b["target"]["executableSha256"] = "b" * 64
            if fault == "observer": a["observation"]["selfKey"] = "42"
            if fault == "bits": a["observation"]["rows"][1]["rawBits"] = [0, 0, 0]
            if fault == "epoch": a["observation"]["identity"]["processId"] += 1
            if fault == "hash": b["nativeSourceSha256"] = "0" * 64
            path.write_text(json.dumps(b)); native.write_text(json.dumps(a))
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.run_export(unit_samples=[path])
            self.assertFalse(self.output.exists())

    def test_unit_samples_sort_scans_and_clear_previous_subtree(self):
        first, _, _, _ = self.unit_wrapper()
        second, native, raw, _ = self.unit_wrapper("later")
        row = raw["observation"]
        for value in [row, *row["rows"]]:
            for field in ("startedAtUtc", "completedAtUtc"):
                value[field] = value[field].replace("04:00:00", "04:00:01")
        native.write_text(json.dumps(raw))
        self.run_export(unit_samples=[second, first])
        events = self.sinks[-1].events
        clears = [e for e in events if e[0] == "world/loaded_units"]
        self.assertEqual([e[1] for e in clears], ["clear", "clear"])
        self.assertLess(clears[0][3]["at"], clears[1][3]["at"])
        self.assertTrue(all(e[3].get("static") is not True for e in clears))
        self.output.unlink()
        with self.assertRaisesRegex(ValueError, "overlapping-scans"):
            self.run_export(unit_samples=[first, first])

    def test_unit_sample_subset_is_nearest_18_within_35(self):
        from tests.test_physical_unit_positions import bits
        path, native, raw, _ = self.unit_wrapper()
        row = raw["observation"]
        template = deepcopy(row["rows"][1])
        row["rows"] = [row["rows"][0]]
        for i in range(25):
            unit = deepcopy(template)
            distance = i + 1 if i < 24 else 36
            unit.update(unitKey=str(i + 100), unitIdCandidate=f"u{i + 100:016X}",
                        positionCandidate=dict(x=7427 + distance, y=871, z=2946), horizontalDistanceCandidate=distance)
            unit["startedAtUtc"] = unit["completedAtUtc"]
            unit["rawBits"] = bits(unit["positionCandidate"])
            row["rows"].append(unit)
        row["examined"] = len(row["rows"]) + row["noPosition"]
        native.write_text(json.dumps(raw))
        scan = self.run_export(unit_samples=[path])["unitSamples"][0]
        self.assertEqual(len(scan["units"]), 18)
        self.assertEqual([u["horizontalDistanceCandidate"] for u in scan["units"]], list(range(1, 19)))

    def test_unit_sample_outside_distance_still_clears_old_scan(self):
        from tests.test_physical_unit_positions import bits
        path, native, raw, _ = self.unit_wrapper()
        unit = raw["observation"]["rows"][1]
        unit.update(positionCandidate=dict(x=7463, y=871, z=2946), horizontalDistanceCandidate=36)
        unit["rawBits"] = bits(unit["positionCandidate"])
        native.write_text(json.dumps(raw))
        scan = self.run_export(observations=[], unit_samples=[path])["unitSamples"][0]
        self.assertEqual(scan["units"], [])
        events = self.sinks[-1].events
        self.assertTrue(any(e[0] == "world/loaded_units" and e[1] == "clear" for e in events))
        self.assertFalse(any(e[0].startswith("world/loaded_units/") for e in events))

    def test_unit_scene_display_camera_bounds_all_admitted_geometry(self):
        route = dict(points=[dict(xyz=dict(x=-2, y=0, z=1)), dict(xyz=dict(x=2, y=0, z=1))])
        scans = [dict(units=[dict(positionXYZCandidate=dict(x=0, y=0, z=5))])]
        frames = [dict(native=[dict(cameraViewRays=dict(status="available-candidate",
                  nativeEyeXYZ=[0, 4, 0], cornersXYZ=[[-6, -2, 2], [6, -2, 2], [6, 2, 2], [-6, 2, 2]]))])]
        camera = exporter.unit_scene_display_camera(route, scans, frames)
        self.assertEqual(camera["boundsMin"], [-6, -2, 0])
        self.assertEqual(camera["boundsMax"], [6, 4, 5])
        self.assertEqual(camera["lookTarget"], [0, 1, 2.5])
        self.assertEqual(camera["includedPointCount"], 8)
        self.assertAlmostEqual(camera["radius"], math.sqrt(36 + 9 + .25))
        self.assertEqual(camera["position"], [c + o * camera["radius"] for c, o in zip([0, 1, 2.5], [3, 4, 3])])
        self.assertIn("not the game camera", camera["qualification"])
        single = exporter.unit_scene_display_camera(dict(points=[dict(xyz=dict(x=1, y=2, z=3))]), [], [])
        self.assertEqual(single["radius"], 1.)
        self.assertEqual(single["position"], [4., 6., 6.])
        frames[0]["native"][0]["cameraViewRays"]["nativeEyeXYZ"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite-display-camera"):
            exporter.unit_scene_display_camera(route, scans, frames)

    def test_explicit_display_camera_only_for_unit_scenes_passes_to_blueprint(self):
        path, _, _, _ = self.unit_wrapper()
        result = self.run_export(unit_samples=[path])
        camera = result["displayCamera"]
        self.assertEqual(self.sinks[-1].display_camera, camera)
        rrb = Mock()
        rr = Mock()
        exporter.default_blueprint(rr, rrb, [], display_camera=camera)
        rrb.EyeControls3D.assert_called_once_with(kind=rrb.Eye3DKind.Orbital,
            position=camera["position"], look_target=camera["lookTarget"], eye_up=[0, 1, 0], spin_speed=0)
        self.assertEqual(rrb.Spatial3DView.call_args.kwargs["eye_controls"], rrb.EyeControls3D.return_value)
        self.output.unlink()
        result = self.run_export(observations=[])
        self.assertNotIn("displayCamera", result)
        self.assertIsNone(self.sinks[-1].display_camera)

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "optional NumPy environment required")
    def test_native_view_rays_use_exact_native_times_and_source_hashes(self):
        self.run_export()
        events = self.sinks[-1].events
        rays = [event for event in events if event[1] == "camera-rays3d"]
        self.assertEqual(len(rays), 2)
        self.assertEqual([event[3]["at"] for event in rays], [
            exporter.timestamp_ns(self.fixture.before["observation"]["completedAtUtc"]),
            exporter.timestamp_ns(self.fixture.after["observation"]["completedAtUtc"])])
        self.assertTrue(all(len(event[2]["lineStrips"]) == 5 for event in rays))
        native = [event[2] for event in events if event[0] == "evidence/native"]
        self.assertTrue(all(row["cameraViewRays"]["status"] == "available-candidate" for row in native))
        self.assertEqual(native[0]["source"], str(self.root / "before.json"))
        self.assertEqual(len(native[0]["sha256"]), 64)
        self.assertIn("display extent 20 (clip W); no scene depth/occlusion", rays[0][2]["label"])

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "optional NumPy environment required")
    def test_singular_optional_inverse_preserves_valid_route_and_clears_camera(self):
        for filename in ("before.json", "after.json"):
            path = self.root / filename
            report = json.loads(path.read_text())
            for row in [report["observation"], *report["observations"]]:
                for name in ("opticalCameraCandidate", "opticalCameraAfterTargetCandidate"):
                    camera = row[name]
                    matrix = list(camera["projectionRowMajor"])
                    matrix[:4] = matrix[4:8]
                    replace_projection(camera, matrix)
            path.write_text(json.dumps(report))
        result = self.run_export()
        self.assertEqual(result["status"], "offline-rerun-evidence-export")
        events = self.sinks[-1].events
        self.assertTrue(any(event[0] == "world/route/points" for event in events))
        self.assertFalse(any(event[1] == "camera-rays3d" for event in events))
        self.assertEqual(len([event for event in events if event[0] == "world/camera" and event[1] == "clear"]), 2)
        row = next(event[2] for event in events if event[0] == "evidence/native")
        self.assertEqual(row["cameraViewRays"]["reason"], "unstable-native-view-inverse")

    def test_missing_numpy_or_disabled_camera_is_optional_for_fake_sink_export(self):
        with patch.dict("sys.modules", {"numpy": None}):
            result = self.run_export()
        self.assertEqual(result["status"], "offline-rerun-evidence-export")
        events = self.sinks[-1].events
        row = next(event[2] for event in events if event[0] == "evidence/native")
        self.assertEqual(row["cameraViewRays"]["reason"], "numpy-unavailable")
        self.assertFalse(any(event[1] == "camera-rays3d" for event in events))
        self.output.unlink()
        self.run_export(camera_rays=False)
        events = self.sinks[-1].events
        self.assertFalse(any(event[0].startswith("world/camera") for event in events))
        row = next(event[2] for event in events if event[0] == "evidence/native")
        self.assertEqual(row["cameraViewRays"]["reason"], "not-requested")

    def test_multiple_observations_use_separate_capture_entities(self):
        result = self.run_export(observations=[self.observation, self.observation])
        images = [event[0] for event in self.sinks[0].events if event[1] == "png"]
        self.assertEqual(images, ["captures/0001", "captures/0002"])
        self.assertEqual(result["observationCount"], 2)

    def test_tampered_image_is_refused_even_when_omitted(self):
        Image.new("RGB", (320, 200), "red").save(self.fixture.image)
        with self.assertRaisesRegex(ValueError, "hash-or-size"):
            self.run_export(images=False)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.sinks, [])

    def test_bad_bracket_identity_and_height_refused_without_output(self):
        observation = json.loads(self.observation.read_text())
        observation["nativeFacing"]["status"] = "unavailable"
        self.observation.write_text(json.dumps(observation))
        with self.assertRaises(ValueError):
            self.run_export()
        self.assertFalse(self.output.exists())
        route = json.loads(self.route.read_text())
        route["heights"][0] = None
        self.route.write_text(json.dumps(route))
        with self.assertRaises(ValueError):
            self.run_export(observations=[])
        self.assertFalse(self.output.exists())

    def test_sink_failure_closes_and_removes_own_partial_output(self):
        def factory(path):
            sink = self.sink(path)
            sink.flush = Mock(side_effect=RuntimeError("flush failed"))
            return sink
        with self.assertRaisesRegex(RuntimeError, "flush failed"):
            exporter.export(self.route, [], self.output, sink_factory=factory)
        self.assertTrue(self.sinks[0].closed)
        self.assertFalse(self.output.exists())
        self.output.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "new-rrd"):
            self.run_export(observations=[])
        self.assertEqual(self.output.read_bytes(), b"preserve")

    def test_timestamp_keeps_dotnet_seventh_digit(self):
        self.assertEqual(exporter.timestamp_ns("2026-11-11T19:00:00.1234567Z") -
                         exporter.timestamp_ns("2026-11-11T19:00:00.1234560Z"), 700)

    def test_real_sink_api_disables_process_analytics_and_restores_environment(self):
        recording = Mock()
        def create(*args, **kwargs):
            self.assertEqual(os.environ["CI"], "1")
            self.assertNotIn("FORCE_RERUN_ANALYTICS", os.environ)
            return recording
        sdk = types.SimpleNamespace(RecordingStream=Mock(side_effect=create), is_enabled=lambda **kwargs: True)
        with patch.dict(os.environ, {"CI": "prior", "FORCE_RERUN_ANALYTICS": "1"}), \
             patch.dict("sys.modules", {"rerun": sdk}), patch.object(exporter, "version", return_value="0.43.1"):
            sink = exporter.RerunSink(self.output)
            recording.save.assert_called_once_with(self.output)
            sink.flush()
            sink.close()
            self.assertEqual(os.environ["CI"], "prior")
            self.assertEqual(os.environ["FORCE_RERUN_ANALYTICS"], "1")
        recording.flush.assert_called_once_with(timeout_sec=30)
        recording.disconnect.assert_called_once()

    def test_blueprint_uses_y_up_two_panes_and_latest_capture_without_retiming(self):
        def constructor(name):
            return Mock(side_effect=lambda *args, **kwargs: dict(kind=name, args=args, kwargs=kwargs))
        rrb = types.SimpleNamespace(**{name: constructor(name) for name in (
            "Spatial3DView", "Spatial2DView", "TextDocumentView", "Tabs", "Horizontal", "TimePanel",
            "Blueprint", "BlueprintPanel", "SelectionPanel")})
        rrb.SpatialInformation = types.SimpleNamespace(from_fields=constructor("SpatialInformation"))
        rr = types.SimpleNamespace(ViewCoordinates=types.SimpleNamespace(RIGHT_HAND_Y_UP="Y-up-display"))
        blueprint = exporter.default_blueprint(rr, rrb, [("/captures/0001", 30), ("/captures/0002", 20)])
        self.assertEqual(blueprint["kwargs"], dict(auto_layout=False, auto_views=False))
        rrb.TimePanel.assert_called_once_with(timeline="evidence_utc", play_state="Following", state="expanded")
        self.assertEqual(rrb.Tabs.call_args.kwargs["active_tab"], 0)
        rrb.SpatialInformation.from_fields.assert_called_once_with(axes="Y-up-display")
        self.assertEqual(rrb.Spatial2DView.call_count, 2)
        self.assertEqual(rrb.Horizontal.call_args.kwargs["column_shares"], [1, 1])

    def desktop_source(self):
        source = self.root / "pair.json"
        source.write_text(json.dumps({"explicit": "fake-pipeline-desktop-source"}))
        result = json.loads((self.fixture.output / "waypoints.json").read_text())
        result.update(observation=str(source), sourceKind="desktop-composite-event-candidate",
            capturedAtUtc=None, capturedAtUtcKind="unavailable-exact-desktop-event-utc",
            captureUpperBoundAtUtc=self.fixture.after["observation"]["startedAtUtc"])
        return source, result

    def test_explicit_desktop_logs_pixels_at_upper_bound_and_native_at_actual_times(self):
        source, projection = self.desktop_source()
        original = self.fixture.image.read_bytes()
        with patch.object(exporter.plot, "render_desktop_pair", return_value=projection, create=True) as renderer:
            result = self.run_export(observations=[], desktop_pairs=[source])
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.args[:2], (source, self.route))
        self.assertEqual(result["desktopPairCount"], 1)
        self.assertEqual(result["wgcObservationCount"], 0)
        sink = self.sinks[-1]
        upper = exporter.timestamp_ns(self.fixture.after["observation"]["startedAtUtc"])
        images = [event for event in sink.events if event[1] == "png"]
        self.assertEqual(images[0][0], "captures/0001_desktop_upper_bound")
        self.assertEqual(images[0][3]["at"], upper)
        points = next(event for event in sink.events if event[1] == "points2d")
        self.assertEqual(points[3]["at"], upper)
        self.assertEqual(points[2]["positions"][0], [160., 110.])
        metadata = next(event[2] for event in sink.events if event[0] == "evidence/observations/0001")
        self.assertEqual(metadata["timeKind"], "upper-bound-native-after-start-not-exact-capture")
        self.assertIsNone(metadata["projection"]["capturedAtUtc"])
        self.assertEqual(metadata["projection"]["capturedAtUtcKind"], "unavailable-exact-desktop-event-utc")
        actual_native = [event[3]["at"] for event in sink.events if event[0] == "world/player"]
        self.assertEqual(actual_native, [
            exporter.timestamp_ns(self.fixture.before["observation"]["completedAtUtc"]),
            exporter.timestamp_ns(self.fixture.after["observation"]["completedAtUtc"])])
        self.assertNotIn(upper, actual_native)
        self.assertEqual(original, self.fixture.image.read_bytes())

    def test_combined_wgc_and_desktop_keep_distinct_entities_and_time_kinds(self):
        source, projection = self.desktop_source()
        with patch.object(exporter.plot, "render_desktop_pair", return_value=projection, create=True):
            result = self.run_export(desktop_pairs=[source])
        sink = self.sinks[-1]
        self.assertEqual(result["observationCount"], 2)
        self.assertEqual([event[0] for event in sink.events if event[1] == "png"],
                         ["captures/0001", "captures/0002_desktop_upper_bound"])
        self.assertEqual([event[2]["timeKind"] for event in sink.events
                          if event[0].startswith("evidence/observations/")],
                         ["capture-completed-at-utc", "upper-bound-native-after-start-not-exact-capture"])
        self.assertEqual(sink.captures[-1], ("/captures/0002_desktop_upper_bound",
            exporter.timestamp_ns(projection["captureUpperBoundAtUtc"])))

    def test_desktop_wrong_time_contract_or_bound_refused_before_sink(self):
        source, original = self.desktop_source()
        for change in (dict(capturedAtUtc="2026-11-11T19:00:00.25Z"),
                       dict(capturedAtUtcKind="exact"),
                       dict(sourceKind="wgc"),
                       dict(captureUpperBoundAtUtc="2026-11-11T19:00:00.4Z")):
            with self.subTest(change=change), patch.object(exporter.plot, "render_desktop_pair",
                    return_value=dict(deepcopy(original), **change), create=True):
                with self.assertRaises(ValueError):
                    self.run_export(observations=[], desktop_pairs=[source])
                self.assertFalse(self.output.exists())
        self.assertEqual(self.sinks, [])

    def test_desktop_renderer_failure_never_falls_back_to_wgc(self):
        source, _ = self.desktop_source()
        with patch.object(exporter.plot, "render_desktop_pair", side_effect=ValueError("withheld"), create=True), \
             patch.object(exporter.plot, "render") as wgc:
            with self.assertRaisesRegex(ValueError, "withheld"):
                self.run_export(observations=[], desktop_pairs=[source])
            wgc.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_desktop_omitted_images_still_validate_and_log_projection(self):
        source, projection = self.desktop_source()
        with patch.object(exporter.plot, "render_desktop_pair", return_value=projection, create=True):
            self.run_export(observations=[], desktop_pairs=[source], images=False)
        self.assertFalse(any(event[1] == "png" for event in self.sinks[-1].events))
        self.assertTrue(any(event[1] == "points2d" for event in self.sinks[-1].events))

    def test_desktop_repeatable_cli_forwards_only_explicit_pairs(self):
        with patch.object(exporter, "export", return_value={"status": "fake-export"}) as export:
            code = exporter.main(["--route", str(self.route), "--output", str(self.output),
                                  "--desktop-pair", "a.json", "--desktop-pair", "b.json"])
        self.assertEqual(code, 0)
        self.assertEqual(export.call_args.kwargs["desktop_pairs"], [Path("a.json"), Path("b.json")])
        self.assertEqual(export.call_args.args[1], [])

    def test_blueprint_names_desktop_candidate_upper_bound_explicitly(self):
        def constructor(name):
            return Mock(side_effect=lambda *args, **kwargs: dict(kind=name, args=args, kwargs=kwargs))
        rrb = types.SimpleNamespace(**{name: constructor(name) for name in (
            "Spatial3DView", "Spatial2DView", "TextDocumentView", "Tabs", "Horizontal", "TimePanel",
            "Blueprint", "BlueprintPanel", "SelectionPanel")})
        rrb.SpatialInformation = types.SimpleNamespace(from_fields=constructor("SpatialInformation"))
        rr = types.SimpleNamespace(ViewCoordinates=types.SimpleNamespace(RIGHT_HAND_Y_UP="Y-up"))
        exporter.default_blueprint(rr, rrb, [("/captures/0001_desktop_upper_bound", 30)])
        self.assertEqual(rrb.Spatial2DView.call_args.kwargs["name"], "Desktop candidate 1 (UTC upper bound)")


@unittest.skipUnless(importlib.util.find_spec("numpy"), "optional NumPy environment required")
class NativeViewRayTests(unittest.TestCase):
    def test_screen_corners_and_known_xyz_roundtrip_for_asymmetric_offset_projection(self):
        camera = optical_camera()
        matrix = camera["projectionRowMajor"]
        # Preserve the exact eye while introducing scale and principal-point offsets.
        x = [1.7 * a + .2 * b for a, b in zip(matrix[:4], matrix[12:16])]
        y = [.9 * a - .15 * b for a, b in zip(matrix[4:8], matrix[12:16])]
        replace_projection(camera, x + y + matrix[8:], [.125, .875, .75, .125])
        rays = exporter.native_view_rays(camera)
        self.assertEqual(rays["status"], "available-candidate", rays)
        self.assertEqual(rays["nativeEyeXYZ"], [7427., 871., 2936.])
        expected = [(.125, .25), (.875, .25), (.875, .875), (.125, .875)]
        for corner, (u, v) in zip(rays["cornersXYZ"], expected):
            projected = exporter.plot.physical._project_world_point(camera, dict(zip("xyz", corner)))
            self.assertAlmostEqual(projected["normalizedX"], u, places=10)
            self.assertAlmostEqual(projected["normalizedY"], v, places=10)
            self.assertAlmostEqual(projected["clipW"], 20., places=10)
        # Pixel coordinates plus a known original clipW reconstruct this actual
        # XYZ by interpolation on the display plane; this does not infer depth.
        xyz = dict(x=7425., y=872., z=2946.)
        projected = exporter.plot.physical._project_world_point(camera, xyz)
        pixel = [1920 * projected["normalizedX"], 23 + 1009 * projected["normalizedY"]]
        u = (pixel[0] / 1920 - .125) / .75
        v = ((pixel[1] - 23) / 1009 - .25) / .625
        weights = [(1-u)*(1-v), u*(1-v), u*v, (1-u)*v]
        plane = [sum(weight * corner[axis] for weight, corner in zip(weights, rays["cornersXYZ"])) for axis in range(3)]
        restored = [eye + (point-eye) * projected["clipW"] / 20
                    for eye, point in zip(rays["nativeEyeXYZ"], plane)]
        for actual, wanted in zip(restored, xyz.values()):
            self.assertAlmostEqual(actual, wanted, places=5)

    def test_implied_eye_mismatch_and_malformed_camera_only_withhold_rays(self):
        camera = optical_camera()
        matrix = list(camera["projectionRowMajor"])
        matrix[3] += 1  # Native reader validates forward row, not this translation.
        replace_projection(camera, matrix)
        rays = exporter.native_view_rays(camera)
        self.assertEqual(rays["status"], "unavailable")
        self.assertEqual(rays["reason"], "native-view-implied-eye-mismatch")
        self.assertNotIn("lineStrips", rays)
        self.assertEqual(exporter.native_view_rays(None)["status"], "unavailable")
        self.assertEqual(exporter.native_view_rays({"rawBits": [float("nan")]})["status"], "unavailable")

    def test_sink_builds_five_line_strips_and_recursive_clear_with_existing_sdk_api(self):
        # Test adapter calls, without constructing a real recording or viewer.
        sdk = types.SimpleNamespace(LineStrips3D=Mock(return_value="lines"), Clear=Mock(return_value="clear"))
        sink = object.__new__(exporter.RerunSink)
        sink.rr, sink.recording = sdk, Mock()
        rays = exporter.native_view_rays(optical_camera())
        sink.log("world/camera/view_rays", "camera-rays3d", rays)
        sdk.LineStrips3D.assert_called_once()
        self.assertEqual(len(sdk.LineStrips3D.call_args.args[0]), 5)
        self.assertEqual(len(sdk.LineStrips3D.call_args.kwargs["labels"]), 5)
        self.assertEqual(sdk.LineStrips3D.call_args.kwargs["labels"][-1], "Camera view rays (display only)")
        self.assertIn("display extent 20 (clip W); no scene depth/occlusion", rays["label"])
        sink.log("world/camera", "clear", {})
        sdk.Clear.assert_called_once_with(recursive=True)


if __name__ == "__main__":
    unittest.main()
