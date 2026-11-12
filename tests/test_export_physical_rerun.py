"""Actual retained-evidence validators with an injected sink; no SDK or viewer."""
from copy import deepcopy
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from scripts import export_physical_rerun as exporter
from tests import test_plot_physical_waypoints as plot_fixtures


class FakeSink:
    def __init__(self, path):
        self.events, self.closed, self.flushed = [], False, False
        Path(path).write_bytes(b"fake-rrd-test-payload")
    def log(self, entity, kind, data, **kwargs):
        self.events.append((entity, kind, data, kwargs))
    def configure_view(self, captures):
        self.captures = captures
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


if __name__ == "__main__":
    unittest.main()
