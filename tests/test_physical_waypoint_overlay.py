"""Overlay presenter tests: fake Tk and Win32 only; no desktop/native reads."""
from contextlib import nullcontext
from copy import deepcopy
import math
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoint_overlay as overlay


TARGET = dict(hostName="AMD-DESKTOP", processId=123, processStartUtcTicks="639300720494342174",
              executablePath=r"C:\Games\rift_x64.exe", executableSha256="a"*64, hwnd=999)


class FakeWindow:
    def __init__(self, api, title):
        self.calls, self.callbacks = [], {}
        self.api = api
        self.hwnd, self.images = api.own_window(42), []
        self.title = title
    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
    def after(self, ms, callback):
        self.callbacks[len(self.callbacks)+1] = callback
        return len(self.callbacks)
    def after_cancel(self, identifier): self.callbacks.pop(identifier, None)
    def paint(self, image): self.images.append(image)
    def show(self, rect): self.api.show(self.hwnd, rect)
    def hide(self): self.api.hide(self.hwnd)


class FakePrimitiveWindow(FakeWindow):
    def __init__(self, api, title):
        super().__init__(api, title)
        self.scenes = []
    def paint_scene(self, scene): self.scenes.append(scene)


class PolishedPrimitiveWindow(FakePrimitiveWindow):
    polished_visuals = True


def projection(x=.5, y=.5):
    return dict(status="available-candidate", normalizedX=x, normalizedY=y, clipW=1., insideViewportCandidate=True)


def frame():
    return dict(target=deepcopy(TARGET), acquiredMonotonic=99.8, clientRect=[-1920, -20, 1920, 1080],
                points=[dict(number=1, label="Corner", ground=projection(), beaconTop=projection(.5, .4))],
                playerGround=projection(.4, .6))


class PresenterTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(overlay.socket, "gethostname", return_value="AMD-DESKTOP"))
        self.clock = self.enterContext(patch.object(overlay.time, "monotonic", return_value=100.))
        self.api = NS(dpi=lambda: nullcontext(), own_window=Mock(return_value=42),
                      snapshot=Mock(return_value={"clientRect": [-1920, -20, 1920, 1080], "foreground": True}),
                      show=Mock(), hide=Mock())
        self.enterContext(patch.object(overlay, "_native", return_value=self.api))
        self.enterContext(patch.object(overlay, "_OwnedWindow", FakeWindow))
        self.presenter = overlay.PhysicalWaypointOverlay(TARGET)
        self.addCleanup(self.presenter.close)

    def test_signed_client_alignment_projection_and_owned_window_only(self):
        self.assertTrue(self.presenter.present(frame()))
        self.api.own_window.assert_called_once_with(42)
        self.api.show.assert_called_once_with(42, [-1920, -20, 1920, 1080])
        image = self.presenter.window.images[-1]
        self.assertEqual((255, 213, 79), image.getpixel((960, 540)))
        self.assertEqual((255, 213, 79), image.getpixel((960, 432)))
        self.assertEqual((81, 229, 255), image.getpixel((768, 648)))
        self.assertEqual((1, 2, 3), image.getpixel((10, 10)))
        self.assertEqual("RR2 Waypoint Overlay | PID 123", self.presenter.window.title)
        self.assertFalse(any("focus" in name or "geometry" == name for name, args, kwargs in self.presenter.window.calls))

    def test_explicit_primitive_window_avoids_full_frame_pillow_image(self):
        primitive = overlay.PhysicalWaypointOverlay(TARGET, window_factory=FakePrimitiveWindow)
        self.addCleanup(primitive.close)
        original = overlay.Image.new
        def tiny_images_only(mode, size, *args, **kwargs):
            self.assertEqual((1, 1), tuple(size))
            return original(mode, size, *args, **kwargs)
        with patch.object(overlay.Image, "new", side_effect=tiny_images_only):
            self.assertTrue(primitive.present(frame()))
        scene = primitive.window.scenes[-1]
        self.assertEqual((1920, 1080), scene["size"])
        self.assertEqual(["line", "text", "ellipse", "line", "line", "line"],
                         [command["kind"] for command in scene["commands"]])
        self.assertEqual([], primitive.window.images)
        primitive.hide("test")
        self.assertIsNone(primitive.window.scenes[-1])

    def test_polished_scene_reserves_pill_and_short_beam_for_active_marker(self):
        presenter = overlay.PhysicalWaypointOverlay(TARGET, window_factory=PolishedPrimitiveWindow)
        self.addCleanup(presenter.close)
        packet = frame()
        packet["points"] = [
            dict(number=1, label="Corner", routeState="next", horizontalDistanceCandidate=8.25,
                 ground=projection(.5, .5), beaconTop=projection(.5, .2)),
            dict(number=2, label="Recorded 2", routeState="pending",
                 ground=projection(.7, .6), beaconTop=projection(.7, .3)),
        ]
        self.assertTrue(presenter.present(packet))
        commands = presenter.window.scenes[-1]["commands"]
        self.assertEqual(1, sum(command["kind"] == "roundedRect" for command in commands))
        labels = [command["text"] for command in commands if command["kind"] == "text"]
        self.assertEqual(["NEXT · 1 Corner · 8.2u"], labels)
        # The active beam is deliberately bounded instead of spanning the full
        # world-height projection; the pending point remains a quiet pip.
        self.assertIn({"kind": "line", "xy": (960, 540, 960.0, 486.0),
                       "color": "#7cffff", "width": 2}, commands)
        self.assertTrue(any(command["kind"] == "ellipse" and command.get("width") == 1
                            and command["xy"] == (1340, 644, 1348, 652) for command in commands))
        first_lane = presenter._label_lanes[("route", 1)]
        packet["points"][0]["ground"] = projection(.501, .5)
        packet["points"][0]["beaconTop"] = projection(.501, .2)
        self.assertTrue(presenter.present(packet))
        self.assertEqual(first_lane, presenter._label_lanes[("route", 1)])
        for command in presenter.window.scenes[-1]["commands"]:
            if command["kind"] == "roundedRect":
                self.assertGreaterEqual(min(command["xy"]), 0)
                self.assertLessEqual(command["xy"][2], 1920)
                self.assertLessEqual(command["xy"][3], 1080)
        presenter.hide("reset")
        self.assertEqual({}, presenter._label_lanes)
        self.assertIsNone(presenter._label_rect)

    def test_polished_landmark_stays_gold_when_completed_and_target_uses_diamond(self):
        presenter = overlay.PhysicalWaypointOverlay(TARGET, window_factory=PolishedPrimitiveWindow)
        self.addCleanup(presenter.close)
        packet = frame()
        packet["points"][0].update(routeState="completed", displayLandmark=True,
                                   horizontalDistanceCandidate=2.5)
        packet["selectedTarget"] = {"status": "candidate", "targetKey": "99", "distance": 3.2,
                                    "cameraStableCandidate": True, "ground": projection(.7, .5),
                                    "beaconTop": projection(.7, .4)}
        self.assertTrue(presenter.present(packet))
        commands = presenter.window.scenes[-1]["commands"]
        self.assertTrue(any(command["kind"] == "ellipse" and command["color"] == "#ffd54f"
                            and command["width"] == 2 for command in commands))
        target_diamond = (1344, 530, 1354, 540, 1344, 550, 1334, 540, 1344, 530)
        self.assertTrue(any(command["kind"] == "line" and command["color"] == "#ff58db"
                            and command["xy"] == target_diamond for command in commands))
        self.assertFalse(any(command["kind"] == "ellipse" and command["color"] == "#ff58db"
                             for command in commands))

    def test_polished_label_avoids_top_chat_quiet_zone_without_moving_anchor(self):
        presenter = overlay.PhysicalWaypointOverlay(TARGET, window_factory=PolishedPrimitiveWindow)
        self.addCleanup(presenter.close)
        packet = frame()
        packet["points"][0].update(routeState="next", horizontalDistanceCandidate=4,
                                   ground=projection(.5, .12), beaconTop=projection(.5, .07))
        self.assertTrue(presenter.present(packet))
        commands = presenter.window.scenes[-1]["commands"]
        quiet = (.26 * 1920, 0, .77 * 1920, .26 * 1080)
        pill = next(command["xy"] for command in commands if command["kind"] == "roundedRect")
        self.assertEqual(0, overlay._overlap_area(pill, quiet))
        # The reticle remains at the exact projected ground point.
        reticle = next(command["xy"] for command in commands
                       if command["kind"] == "ellipse" and command["width"] == 2)
        self.assertAlmostEqual(960, (reticle[0] + reticle[2]) / 2)
        self.assertAlmostEqual(.12 * 1080, (reticle[1] + reticle[3]) / 2)

    def test_live_appearance_scales_beacons_hides_every_label_and_sets_scene_opacity(self):
        presenter = overlay.PhysicalWaypointOverlay(TARGET, window_factory=PolishedPrimitiveWindow)
        self.addCleanup(presenter.close)
        packet = frame()
        packet["appearance"] = {"schemaVersion": 1, "beaconScale": 2., "opacity": .4,
                                "labelsVisible": False}
        packet["points"][0].update(routeState="next", horizontalDistanceCandidate=4,
                                   ground=projection(.5, .5), beaconTop=projection(.5, .2))
        self.assertTrue(presenter.present(packet))
        scene = presenter.window.scenes[-1]
        self.assertEqual(.4, scene["opacity"])
        self.assertFalse(any(command["kind"] in ("text", "roundedRect") for command in scene["commands"]))
        reticle = next(command for command in scene["commands"]
                        if command["kind"] == "ellipse" and command["width"] == 4)
        self.assertEqual((940., 520., 980., 560.), reticle["xy"])
        self.assertEqual((960., 540.), ((reticle["xy"][0] + reticle["xy"][2]) / 2,
                                        (reticle["xy"][1] + reticle["xy"][3]) / 2))
        beam = next(command for command in scene["commands"]
                    if command["kind"] == "line" and command["width"] == 4
                    and command["xy"][:2] == (960., 540.))
        self.assertAlmostEqual(108, math.dist(beam["xy"][:2], beam["xy"][2:]))

        packet["viewportRectNormalized"] = [0, 0, 1, 1]
        packet["points"][0]["ground"] = projection(1.2, .5)
        packet["points"][0]["ground"]["insideViewportCandidate"] = False
        self.assertTrue(presenter.present(packet))
        commands = presenter.window.scenes[-1]["commands"]
        self.assertFalse(any(command["kind"] == "text" for command in commands))
        self.assertTrue(any(command["kind"] == "line" and command["color"] == "#7cffff"
                            for command in commands), "label-free edge arrow remains visible")

    def test_invalid_live_appearance_fails_closed(self):
        packet = frame()
        packet["appearance"] = {"schemaVersion": 1, "beaconScale": 3., "opacity": 1.,
                                "labelsVisible": True}
        self.assertFalse(self.presenter.present(packet))
        self.assertIn("beaconScale", self.presenter.reason)

    def test_named_landmark_offscreen_and_behind_without_progress(self):
        row = dict(number=8, label="3rd Guard Soldier", displayLandmark=True, horizontalDistanceCandidate=7.44,
                   ground=dict(status="available-candidate", normalizedX=2, normalizedY=.5, clipW=1,
                               insideViewportCandidate=False))
        hint = overlay.landmark_edge_hint([row], [0, 0, 1, 1], 500, 300)
        self.assertEqual(hint["kind"], "arrow")
        self.assertEqual(hint["color"], "#ffd54f")
        self.assertEqual(hint["text"], "3rd Guard Soldier · 7.4 units direct")
        self.assertEqual(hint["anchor"], (476., 150.))
        self.assertNotIn("routeState", row)
        row["ground"] = dict(status="nonpositive-or-small-clip-w", clipW=-1)
        self.assertIn("behind camera", overlay.landmark_edge_hint([row], [0, 0, 1, 1], 500, 300)["text"])
        row["ground"]["clipW"] = 0
        self.assertIn("outside camera view", overlay.landmark_edge_hint([row], [0, 0, 1, 1], 500, 300)["text"])

    def test_presenter_paints_gold_landmark_cue_without_playback_progress(self):
        packet = frame()
        packet["viewportRectNormalized"] = [0, 0, 1, 1]
        packet["points"][0].update(displayLandmark=True, horizontalDistanceCandidate=7.4,
            ground=dict(status="available-candidate", normalizedX=2, normalizedY=.5, clipW=1,
                        insideViewportCandidate=False))
        self.assertTrue(self.presenter.present(packet))
        self.assertEqual(self.presenter.window.images[-1].getpixel((1896, 540)), (255, 213, 79))
        self.assertNotIn("routeState", self.presenter.frame["points"][0])

    def test_landmark_duplicate_invalid_visible_and_next_priority(self):
        row = dict(number=1, label="Corner", displayLandmark=True, horizontalDistanceCandidate=2,
                   ground=dict(status="available-candidate", normalizedX=-1, normalizedY=.5, clipW=1,
                               insideViewportCandidate=False))
        self.assertIsNone(overlay.landmark_edge_hint([row, deepcopy(row)], [0, 0, 1, 1], 500, 300))
        for change in (dict(displayLandmark=1), dict(number=True), dict(routeState="next"), dict(ground=projection())):
            self.assertIsNone(overlay.landmark_edge_hint([dict(row, **change)], [0, 0, 1, 1], 500, 300))
        f = frame()
        f["points"][0]["displayLandmark"] = 1
        self.assertFalse(self.presenter.present(f))
        self.assertIn("displayLandmark", self.presenter.reason)

    def test_next_landmark_coexist_with_nonoverlapping_text_and_narrow_label(self):
        row = dict(number=1, label="Very long measured landmark name " * 4, displayLandmark=True,
                   horizontalDistanceCandidate=2, ground=dict(status="nonpositive-or-small-clip-w", clipW=-1))
        next_row = dict(row, number=2, label="Other", displayLandmark=False, routeState="next")
        image = overlay.Image.new("RGB", (300, 180))
        draw = overlay.ImageDraw.Draw(image)
        font = overlay.ImageFont.load_default(size=16)
        first = overlay._draw_next_edge_hint(draw, overlay.next_edge_hint([next_row], [0, 0, 1, 1], 300, 180), font)
        second = overlay._draw_next_edge_hint(draw, overlay.landmark_edge_hint([row], [0, 0, 1, 1], 300, 180),
                                              font, occupied=[first])
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)  # Truncates rather than vanishing on a narrow client.
        self.assertTrue(second[3] < first[1] or first[3] < second[1] or second[2] < first[0] or first[2] < second[0])
        self.assertEqual(row["label"], "Very long measured landmark name " * 4)

    def test_route_states_color_exact_anchors_and_thicken_next_with_label(self):
        for state, color, prefix in ((None, (255, 213, 79), "1 Corner"),
                                     ("pending", (179, 152, 82), "1 Corner"),
                                     ("completed", (101, 200, 138), "1 Corner"),
                                     ("next", (124, 255, 255), "NEXT 1 Corner")):
            with self.subTest(state=state):
                f = frame()
                if state is not None:
                    f["points"][0]["routeState"] = state
                with patch.object(overlay, "_label_layout", wraps=overlay._label_layout) as layout:
                    self.assertTrue(self.presenter.present(f))
                self.assertEqual(prefix, layout.call_args.args[0][0][1])
                image = self.presenter.window.images[-1]
                self.assertEqual(color, image.getpixel((960, 540)))
                self.assertEqual(color, image.getpixel((960, 432)))
                self.assertEqual(color, image.getpixel((967, 540)))
                # Same beam center/endpoints; only NEXT gets a wider beam.
                self.assertEqual(color if state == "next" else (1, 2, 3), image.getpixel((958, 480)))
                self.assertEqual((81, 229, 255), image.getpixel((768, 648)))
                self.assertEqual((1, 2, 3), image.getpixel((10, 10)))

    def test_optional_target_is_distinct_and_disappears_on_next_frame(self):
        f = frame()
        f["selectedTarget"] = {"status": "candidate", "targetKey": "99", "distance": 3.2,
                               "cameraStableCandidate": True, "ground": projection(.7, .5),
                               "beaconTop": projection(.7, .4)}
        with patch.object(overlay, "_label_layout", wraps=overlay._label_layout) as layout:
            self.assertTrue(self.presenter.present(f))
        self.assertEqual("Target · 3.2", layout.call_args.args[0][-1][1])
        self.assertEqual((255, 88, 219), self.presenter.window.images[-1].getpixel((int(.7*1920), 432)))
        del f["selectedTarget"]
        self.assertTrue(self.presenter.present(f))
        self.assertEqual((1, 2, 3), self.presenter.window.images[-1].getpixel((int(.7*1920), 432)))

    def test_invalid_optional_target_keeps_route_visible(self):
        f = frame()
        f["selectedTarget"] = {"status": "candidate", "targetKey": "invalid", "distance": 1,
                               "cameraStableCandidate": True, "ground": projection(), "beaconTop": projection()}
        self.assertTrue(self.presenter.present(f))
        self.assertEqual((255, 213, 79), self.presenter.window.images[-1].getpixel((960, 540)))

    def test_next_edge_hint_four_edges_and_offset_viewport(self):
        viewport = [.1, .2, .9, .8]
        for x, y, expected_axis, expected in ((1.2, .5, 0, 876), (-.2, .5, 0, 124),
                                               (.5, -.2, 1, 144), (.5, 1.2, 1, 456)):
            with self.subTest(x=x, y=y):
                row = dict(number=7, routeState="next", horizontalDistanceCandidate=12.34,
                           ground=dict(status="available-candidate", clipW=2, normalizedX=x,
                                       normalizedY=y, insideViewportCandidate=False))
                hint = overlay.next_edge_hint([row], viewport, 1000, 600)
                self.assertEqual("arrow", hint["kind"])
                self.assertAlmostEqual(expected, hint["anchor"][expected_axis])
                self.assertEqual("NEXT 7 · 12.3 units direct", hint["text"])
                image = overlay.Image.new("RGB", (1000, 600))
                overlay._draw_next_edge_hint(overlay.ImageDraw.Draw(image), hint,
                                             overlay.ImageFont.load_default(size=16))
                box = image.getbbox()
                self.assertTrue(100 <= box[0] < box[2] <= 900 and 120 <= box[1] < box[3] <= 480, box)

    def test_next_edge_corner_behind_and_near_zero_have_honest_cues(self):
        row = dict(number=3, routeState="next", horizontalDistanceCandidate=5,
                   ground=dict(status="available-candidate", clipW=1, normalizedX=2, normalizedY=-1,
                               insideViewportCandidate=False))
        hint = overlay.next_edge_hint([row], [0, 0, 1, 1], 500, 500)
        self.assertEqual("arrow", hint["kind"])
        self.assertAlmostEqual(476, hint["anchor"][0])
        self.assertAlmostEqual(24, hint["anchor"][1])
        for clip, phrase in ((-1., "behind camera"), (0., "outside camera view"), (1e-5, "outside camera view")):
            row["ground"] = {"status": "nonpositive-or-small-clip-w", "clipW": clip}
            hint = overlay.next_edge_hint([row], [0, 0, 1, 1], 500, 500)
            self.assertEqual("text", hint["kind"])
            self.assertIn(phrase, hint["text"])
            self.assertNotIn("anchor", hint)

    def test_next_edge_hint_withholds_visible_duplicate_or_invalid_metadata(self):
        row = dict(number=5, routeState="next", horizontalDistanceCandidate=1,
                   ground=dict(status="available-candidate", clipW=2, normalizedX=2, normalizedY=.5,
                               insideViewportCandidate=False))
        viewport = [0, 0, 1, 1]
        self.assertIsNone(overlay.next_edge_hint([row, deepcopy(row)], viewport, 500, 500))
        for field, value in (("horizontalDistanceCandidate", float("nan")), ("number", True),
                             ("routeState", "completed")):
            bad = deepcopy(row); bad[field] = value
            self.assertIsNone(overlay.next_edge_hint([bad], viewport, 500, 500))
        self.assertIsNone(overlay.next_edge_hint([row], None, 500, 500))
        self.assertIsNone(overlay.next_edge_hint([row], [.1, .2, .1, .8], 500, 500))
        visible = deepcopy(row); visible["ground"].update(normalizedX=.5, insideViewportCandidate=True)
        self.assertIsNone(overlay.next_edge_hint([visible], viewport, 500, 500))
        overflow = deepcopy(row); overflow["ground"]["normalizedX"] = 1e308
        self.assertIsNone(overlay.next_edge_hint([overflow], viewport, 500, 500))
        self.assertIsNone(overlay.next_edge_hint([], viewport, 500, 500))

    def test_next_hint_clears_when_saved_progress_disappears(self):
        f = frame()
        f["viewportRectNormalized"] = [0, 0, 1, 1]
        f["points"][0].update(routeState="next", horizontalDistanceCandidate=4)
        f["points"][0]["ground"] = projection(1.2, .5)
        f["points"][0]["ground"]["insideViewportCandidate"] = False
        self.assertTrue(self.presenter.present(f))
        self.assertEqual((124, 255, 255), self.presenter.window.images[-1].getpixel((1896, 540)))
        del f["points"][0]["routeState"]
        self.assertTrue(self.presenter.present(f))
        self.assertEqual((1, 2, 3), self.presenter.window.images[-1].getpixel((1896, 540)))

    def test_edge_hint_does_not_erase_player_reference_pixel(self):
        f = frame()
        f["viewportRectNormalized"] = [0, 0, 1, 1]
        f["points"][0].update(routeState="next", horizontalDistanceCandidate=4)
        f["points"][0]["ground"] = projection(1.2, .5)
        f["points"][0]["ground"]["insideViewportCandidate"] = False
        f["playerGround"] = projection(1896 / 1920, .5)
        self.assertTrue(self.presenter.present(f))
        self.assertEqual((81, 229, 255), self.presenter.window.images[-1].getpixel((1896, 540)))

    def test_expired_or_changed_frame_during_paint_is_never_shown(self):
        original = self.presenter.window.paint
        def slow_paint(image):
            original(image)
            if image is not None:
                self.clock.return_value = 101.
        self.presenter.window.paint = slow_paint
        self.assertFalse(self.presenter.present(frame()))
        self.api.show.assert_not_called()
        self.assertIsNone(self.presenter.frame)
        self.assertIn("Stale", self.presenter.reason)
        self.clock.return_value = 100.
        def changed_geometry(image):
            original(image)
            if image is not None:
                self.api.snapshot.return_value = {"clientRect": [-1919, -20, 1920, 1080], "foreground": True}
        self.presenter.window.paint = changed_geometry
        self.assertFalse(self.presenter.present(frame()))
        self.api.show.assert_not_called()
        self.assertIn("geometry", self.presenter.reason)
        self.clock.return_value = 100.
        self.presenter.window.paint = original
        snapshots = []
        def slow_snapshot(_):
            snapshots.append(True)
            if len(snapshots) == 2:
                self.clock.return_value = 101.
            return {"clientRect": [-1920, -20, 1920, 1080], "foreground": True}
        self.api.snapshot.side_effect = slow_snapshot
        self.assertFalse(self.presenter.present(frame()))
        self.api.show.assert_not_called()
        self.assertIn("Stale", self.presenter.reason)

    def test_invalid_present_route_state_refuses_frame(self):
        for state in (None, "unknown", "NEXT", 1, [], {}):
            f = frame()
            f["points"][0]["routeState"] = state
            self.assertFalse(self.presenter.present(f))
            self.assertIn("routeState", self.presenter.reason)
        self.api.show.assert_not_called()

    def test_stale_future_malformed_and_changed_target_hide(self):
        mutations = [lambda f: f.update(acquiredMonotonic=98.), lambda f: f.update(acquiredMonotonic=101.),
                     lambda f: f["target"].update(hwnd=1000), lambda f: f.update(clientRect=[0, 0, 1]),
                     lambda f: f["points"][0]["ground"].update(normalizedX=float("nan")),
                     lambda f: f.update(points=None)]
        for mutate in mutations:
            f = frame(); mutate(f)
            with self.subTest(frame=f):
                self.assertFalse(self.presenter.present(f))
                self.assertIsNone(self.presenter.frame)
        self.api.show.assert_not_called()

    def test_foreground_geometry_and_epoch_failure_hide(self):
        for snapshot in ({"clientRect": [-1920, -20, 1920, 1080], "foreground": False},
                         {"clientRect": [-1910, -20, 1920, 1080], "foreground": True}):
            self.api.snapshot.return_value = snapshot
            self.assertFalse(self.presenter.present(frame()))
        self.api.snapshot.side_effect = ValueError("Target process epoch changed")
        self.assertFalse(self.presenter.present(frame()))
        self.assertIn("epoch", self.presenter.reason)

    def test_companion_permission_allows_display_without_falsifying_rift_foreground(self):
        companion = {"processId": 456, "processStartUtcTicks": "639300720494342175", "hwnd": 777}
        presenter = overlay.PhysicalWaypointOverlay(TARGET, companion=companion)
        self.addCleanup(presenter.close)
        self.api.snapshot.return_value = {"clientRect": [-1920, -20, 1920, 1080],
                                          "foreground": False, "displayAllowed": True}
        self.assertTrue(presenter.present(frame()))
        self.api.snapshot.assert_called_with(TARGET, companion=companion)

        self.api.snapshot.return_value["displayAllowed"] = False
        self.assertFalse(presenter.present(frame()))
        self.assertIn("foreground", presenter.reason)

    def test_outside_active_viewport_skips_marker_and_missing_membership_refuses(self):
        f = frame()
        f["points"][0]["ground"]["insideViewportCandidate"] = False
        self.assertTrue(self.presenter.present(f))
        self.assertEqual((1, 2, 3), self.presenter.window.images[-1].getpixel((960, 540)))
        f = frame()
        del f["points"][0]["ground"]["insideViewportCandidate"]
        self.assertFalse(self.presenter.present(f))

    def test_captured_near_coincident_labels_separate_without_moving_world_anchors(self):
        # Normalized anchors retained from the seven-point live proof packet;
        # the test needs no artifact file, window or fresh native observation.
        anchors = [(.4985856943, .5717270670), (.5001097458, .6438167331),
                   (.5018158311, .7243812097), (.6174528778, .7093054045),
                   (.6074622950, .5721093843), (.5538553464, .5741758156),
                   (.5018598613, .5762331013)]
        f = frame()
        f["points"] = [dict(number=i, label=f"Recorded {i}", ground=projection(x, y),
                            beaconTop=projection(x, y-.05)) for i, (x, y) in enumerate(anchors, 1)]
        with patch.object(overlay, "_label_layout", wraps=overlay._label_layout) as layout:
            self.assertTrue(self.presenter.present(f))
        labels, width, height, font = layout.call_args.args
        self.assertEqual([str(i) for i in range(1, 8)], [text for anchor, text in labels])
        placed = overlay._label_layout(labels, width, height, font)
        self.assert_layout(placed, width, height)
        image = self.presenter.window.images[-1]
        for x, y in anchors:
            self.assertEqual((255, 213, 79), image.getpixel((int(x*width), int(y*height))))
            self.assertEqual((255, 213, 79), image.getpixel((int(x*width), int((y-.05)*height))))

    def assert_layout(self, placed, width, height):
        for index, (text, box, anchor) in enumerate(placed):
            self.assertTrue(0 <= box[0] < box[2] <= width)
            self.assertTrue(0 <= box[1] < box[3] <= height)
            for _, other, _ in placed[:index]:
                self.assertTrue(box[2] <= other[0] or other[2] <= box[0] or
                                box[3] <= other[1] or other[3] <= box[1], (box, other))

    def test_custom_label_names_preserved_and_edge_lanes_stay_inside_client(self):
        font = overlay.ImageFont.load_default(size=16)
        labels = [((319, 2), f"{i} Custom destination {i}") for i in range(1, 8)]
        placed = overlay._label_layout(labels, 320, 240, font)
        self.assert_layout(placed, 320, 240)
        self.assertEqual([text for anchor, text in labels], [text for text, box, anchor in placed])
        # If every pixel is reserved, retain a finite bounded best-effort label.
        fallback = overlay._label_layout([((160, 120), "Only label")], 320, 240, font,
                                         reserved=((0, 0, 320, 240),))
        self.assert_layout(fallback, 320, 240)

    def test_watchdog_hides_expired_frame_and_close_cancels_timer(self):
        self.assertTrue(self.presenter.present(frame()))
        self.clock.return_value = 101.
        self.presenter._tick()
        self.assertIsNone(self.presenter.frame)
        self.assertIn("Stale", self.presenter.reason)
        self.assertEqual({self.presenter.reason: 1}, self.presenter.hide_reasons)
        # Repeated hides without a visible accepted frame are not double-counted.
        self.presenter.hide(self.presenter.reason)
        self.assertEqual({self.presenter.reason: 1}, self.presenter.hide_reasons)
        self.presenter.close()
        calls = self.presenter.window.calls
        self.assertTrue(any(name == "destroy" for name, args, kwargs in calls))
        self.assertFalse(self.presenter.present(frame()))

    def test_hide_reason_telemetry_caps_distinct_strings(self):
        for index in range(70):
            self.presenter.frame = {}
            self.presenter.hide(f"unique-{index}")
        self.assertEqual(65, len(self.presenter.hide_reasons))
        self.assertEqual(6, self.presenter.hide_reasons["other"])

        self.presenter.frame = {}
        self.presenter.hide("unique-0")
        self.assertEqual(2, self.presenter.hide_reasons["unique-0"])
        self.assertEqual(6, self.presenter.hide_reasons["other"])

    def test_worker_calls_rejected_before_tk(self):
        errors = []
        def worker():
            try: self.presenter.present(frame())
            except RuntimeError as exc: errors.append(str(exc))
        thread = threading.Thread(target=worker); thread.start(); thread.join()
        self.assertEqual(1, len(errors))
        self.api.show.assert_not_called()

    def test_constructor_window_refusal_propagates(self):
        self.api.own_window.side_effect = ValueError("style refusal")
        with self.assertRaisesRegex(ValueError, "style refusal"):
            overlay.PhysicalWaypointOverlay(TARGET)

    def test_close_destroys_owned_window_even_if_native_hide_fails(self):
        self.api.hide.side_effect = ValueError("owned HWND unavailable")
        with self.assertRaises(ValueError): self.presenter.close()
        self.assertTrue(self.presenter.closed)
        self.assertTrue(any(name == "destroy" for name, args, kwargs in self.presenter.window.calls))


class NativeCallsTests(unittest.TestCase):
    def test_companion_value_validation_is_strict_and_returns_a_copy(self):
        value = {"processId": 456, "processStartUtcTicks": "639300720494342175", "hwnd": 777}
        result = overlay.validate_companion(value)
        self.assertEqual(value, result)
        self.assertIsNot(value, result)
        for invalid in (dict(value, extra=True), dict(value, processId=True),
                        dict(value, processStartUtcTicks="0"), dict(value, hwnd=0)):
            with self.assertRaisesRegex(ValueError, "companion"):
                overlay.validate_companion(invalid)

    def owned_api(self):
        user = NS(**{name: Mock(return_value=True) for name in (
            "RegisterClassW", "UnregisterClassW", "SetLayeredWindowAttributes", "DestroyWindow", "IsWindow",
            "InvalidateRect", "EndPaint", "TranslateMessage")})
        user.CreateWindowExW = Mock(return_value=42)
        user.DefWindowProcW = Mock(return_value=0)
        user.PeekMessageW = Mock(return_value=0)
        user.DispatchMessageW = Mock(return_value=0)
        user.BeginPaint = Mock(return_value=77)
        kernel = NS(GetModuleHandleW=Mock(return_value=55))
        gdi = NS(CreateSolidBrush=Mock(return_value=88), DeleteObject=Mock(return_value=True))
        api = NS(u=user, k=kernel, dpi=lambda: nullcontext(), own_window=Mock(return_value=42))
        return api, gdi

    def test_native_creation_styles_first_color_key_and_complete_cleanup(self):
        api, gdi = self.owned_api()
        with patch.object(overlay.ctypes, "WinDLL", return_value=gdi):
            window = overlay._OwnedWindow(api, "RR2 Waypoint Overlay | PID 123")
        args = api.u.CreateWindowExW.call_args.args
        self.assertEqual(overlay.OVERLAY_STYLES, args[0])
        self.assertEqual("RR2 Waypoint Overlay | PID 123", args[2])
        self.assertFalse(args[3] & 0x10000000, "Must be created hidden")
        api.u.SetLayeredWindowAttributes.assert_called_once_with(42, 0x030201, 255, 1)
        window.set_opacity(.5)
        api.u.SetLayeredWindowAttributes.assert_called_with(42, 0x030201, 128, 3)
        window.after(0, lambda: None)
        window.destroy()
        self.assertEqual({}, window.callbacks)
        api.u.DestroyWindow.assert_called_once_with(42)
        api.u.UnregisterClassW.assert_called_once_with(window.class_name, 55)
        gdi.DeleteObject.assert_called_once_with(88)
        window.destroy()
        self.assertEqual(1, api.u.DestroyWindow.call_count)

    def test_native_scheduler_filters_owned_hwnd_cancels_and_quits(self):
        api, gdi = self.owned_api()
        with patch.object(overlay.ctypes, "WinDLL", return_value=gdi):
            window = overlay._OwnedWindow(api, "test")
        try:
            cancelled, due = Mock(), Mock()
            identifier = window.after(0, cancelled)
            window.after_cancel(identifier)
            window.after(0, due)
            window.after(0, window.quit)
            window.mainloop()
            cancelled.assert_not_called()
            due.assert_called_once()
            self.assertEqual(42, api.u.PeekMessageW.call_args.args[1])
            self.assertFalse(window.running)
        finally:
            window.destroy()

    def test_cached_paint_uses_begin_end_and_closing_protocol(self):
        api, gdi = self.owned_api()
        with patch.object(overlay.ctypes, "WinDLL", return_value=gdi):
            window = overlay._OwnedWindow(api, "test")
        try:
            dib = NS(size=(100, 80), draw=Mock())
            with patch.object(overlay.ImageWin, "Dib", return_value=dib):
                window.paint(overlay.Image.new("RGB", (100, 80)))
            window._message(42, 0x000F, 0, 0)
            dib.draw.assert_called_once_with(77, (0, 0, 100, 80))
            api.u.EndPaint.assert_called_once()
            close = Mock()
            window.protocol("WM_DELETE_WINDOW", close)
            window._message(42, 0x0010, 0, 0)
            close.assert_called_once()
        finally:
            window.destroy()

    def test_native_partial_creation_failure_unregisters_and_releases_brush(self):
        api, gdi = self.owned_api()
        api.u.CreateWindowExW.return_value = 0
        with patch.object(overlay.ctypes, "WinDLL", return_value=gdi):
            with self.assertRaisesRegex(ValueError, "creation failed"):
                overlay._OwnedWindow(api, "test")
        api.u.DestroyWindow.assert_not_called()
        api.u.UnregisterClassW.assert_called_once()
        gdi.DeleteObject.assert_called_once_with(88)

    def test_styles_and_signed_show_never_address_game_hwnd(self):
        api = overlay._Win32.__new__(overlay._Win32)
        api.owner = Mock(return_value=overlay.os.getpid())
        api.dpi = lambda: nullcontext()
        api.u = NS(GetAncestor=Mock(return_value=42), GetWindowLongPtrW=Mock(side_effect=[0, overlay.OVERLAY_STYLES, overlay.OVERLAY_STYLES]),
                   SetWindowLongPtrW=Mock(), IsWindow=Mock(return_value=True),
                   SetWindowPos=Mock(return_value=True), ShowWindow=Mock())
        self.assertEqual(42, api.own_window(41))
        api.u.SetWindowLongPtrW.assert_called_once_with(42, -20, overlay.OVERLAY_STYLES)
        api.show(42, [-1920, -20, 1920, 1080])
        args = api.u.SetWindowPos.call_args.args
        self.assertEqual(42, args[0])
        self.assertEqual((-1920, -20, 1920, 1080), args[2:6])
        self.assertTrue(args[-1] & 0x10)
        api.u.ShowWindow.assert_called_once_with(42, 4)
        api.hide(42)
        self.assertEqual((42, 0), api.u.ShowWindow.call_args.args)

    def test_wrong_own_pid_refuses_styles_and_position(self):
        api = overlay._Win32.__new__(overlay._Win32)
        api.owner = lambda hwnd: 123456789
        api.u = NS(GetAncestor=lambda *_: 42, IsWindow=lambda _: True)
        with self.assertRaises(ValueError): api.own_window(41)
        with self.assertRaises(ValueError): api.show(42, [0, 0, 100, 100])

    def test_missing_clickthrough_style_refuses_owned_window(self):
        api = overlay._Win32.__new__(overlay._Win32)
        api.owner = lambda hwnd: overlay.os.getpid()
        api.u = NS(GetAncestor=lambda *_: 42, GetWindowLongPtrW=lambda *_: 0,
                   SetWindowLongPtrW=lambda *_: None)
        with self.assertRaisesRegex(ValueError, "styles"):
            api.own_window(41)

    def snapshot_api(self):
        api = overlay._Win32.__new__(overlay._Win32)
        api.owner = lambda hwnd: TARGET["processId"]
        api.dpi = lambda: nullcontext()
        def times(handle, first, *others):
            ticks = int(TARGET["processStartUtcTicks"]) - 504911232000000000
            first._obj.dwHighDateTime, first._obj.dwLowDateTime = ticks >> 32, ticks & 0xffffffff
            return True
        def path(handle, flags, buffer, size):
            buffer.value = TARGET["executablePath"]
            return True
        def rect(hwnd, output):
            output._obj.right, output._obj.bottom = 1920, 1080
            return True
        def origin(hwnd, point):
            point._obj.x, point._obj.y = -1920, -20
            return True
        api.u = NS(IsWindow=lambda _: True, IsWindowVisible=lambda _: True, IsIconic=lambda _: False,
                   GetClientRect=rect, ClientToScreen=origin, GetForegroundWindow=lambda: TARGET["hwnd"])
        api.k = NS(OpenProcess=lambda *_: 123, CloseHandle=Mock(), GetProcessTimes=times,
                   WaitForSingleObject=lambda *_: 258, QueryFullProcessImageNameW=path)
        api.d = NS(DwmGetWindowAttribute=lambda *_: 0)
        return api

    def test_snapshot_physical_negative_origin_and_epoch_refusal(self):
        api = self.snapshot_api()
        self.assertEqual({"clientRect": [-1920, -20, 1920, 1080], "foreground": True}, api.snapshot(TARGET))
        changed = dict(TARGET, processStartUtcTicks=str(int(TARGET["processStartUtcTicks"]) + 1))
        with self.assertRaisesRegex(ValueError, "epoch"):
            api.snapshot(changed)
        self.assertEqual(2, api.k.CloseHandle.call_count)

    def test_snapshot_hidden_minimized_cloaked_and_owner_refusal(self):
        api = self.snapshot_api()
        for name, result in (("IsWindow", False), ("IsWindowVisible", False), ("IsIconic", True)):
            original = getattr(api.u, name)
            setattr(api.u, name, lambda _, value=result: value)
            with self.assertRaises(ValueError): api.snapshot(TARGET)
            setattr(api.u, name, original)
        api.owner = lambda hwnd: 987
        with self.assertRaises(ValueError): api.snapshot(TARGET)
        api.owner = lambda hwnd: TARGET["processId"]
        def cloaked(hwnd, attribute, result, size):
            result._obj.value = 1
            return 0
        api.d.DwmGetWindowAttribute = cloaked
        with self.assertRaisesRegex(ValueError, "cloaked"): api.snapshot(TARGET)

    def test_companion_binding_and_snapshot_are_exact_epoch_scoped(self):
        api = self.snapshot_api()
        companion_pid, companion_hwnd = 456, 777
        companion_ticks = int(TARGET["processStartUtcTicks"]) + 1
        api.u.GetAncestor = lambda hwnd, kind: companion_hwnd
        api.u.GetForegroundWindow = lambda: companion_hwnd
        api.owner = lambda hwnd: TARGET["processId"] if hwnd == TARGET["hwnd"] else companion_pid
        api.k.OpenProcess = lambda access, inherit, pid: pid
        def times(handle, first, *others):
            ticks = (int(TARGET["processStartUtcTicks"]) if handle == TARGET["processId"]
                     else companion_ticks) - 504911232000000000
            first._obj.dwHighDateTime, first._obj.dwLowDateTime = ticks >> 32, ticks & 0xffffffff
            return True
        api.k.GetProcessTimes = times
        with patch.object(overlay.os, "getpid", return_value=companion_pid):
            companion = api.bind_companion_window(700)
        self.assertEqual({"processId": companion_pid, "processStartUtcTicks": str(companion_ticks),
                          "hwnd": companion_hwnd}, companion)

        result = api.snapshot(TARGET, companion=companion)
        self.assertFalse(result["foreground"])
        self.assertTrue(result["displayAllowed"])
        api.u.GetForegroundWindow = lambda: 888
        self.assertFalse(api.snapshot(TARGET, companion=companion)["displayAllowed"])

        # Normal RIFT foreground display never depends on companion availability.
        api.u.GetForegroundWindow = lambda: TARGET["hwnd"]
        api.owner = lambda hwnd: TARGET["processId"] if hwnd == TARGET["hwnd"] else 999
        api.u.IsIconic = lambda hwnd: hwnd == companion_hwnd
        result = api.snapshot(TARGET, companion=companion)
        self.assertTrue(result["foreground"])
        self.assertTrue(result["displayAllowed"])

        # Losing companion foreground during its validation does not retain permission.
        api.owner = lambda hwnd: TARGET["processId"] if hwnd == TARGET["hwnd"] else companion_pid
        api.u.IsIconic = lambda hwnd: False
        api.u.GetForegroundWindow = Mock(side_effect=[companion_hwnd, 888])
        self.assertFalse(api.snapshot(TARGET, companion=companion)["displayAllowed"])

        changed = dict(companion, processStartUtcTicks=str(companion_ticks + 1))
        api.u.GetForegroundWindow = lambda: companion_hwnd
        api.owner = lambda hwnd: TARGET["processId"] if hwnd == TARGET["hwnd"] else companion_pid
        api.u.IsIconic = lambda hwnd: False
        with self.assertRaisesRegex(ValueError, "epoch"):
            api.snapshot(TARGET, companion=changed)
        api.owner = lambda hwnd: TARGET["processId"] if hwnd == TARGET["hwnd"] else 999
        with self.assertRaisesRegex(ValueError, "owner"):
            api.snapshot(TARGET, companion=companion)
        api.owner = lambda hwnd: TARGET["processId"] if hwnd == TARGET["hwnd"] else companion_pid
        api.u.IsIconic = lambda hwnd: hwnd == companion_hwnd
        with self.assertRaisesRegex(ValueError, "minimized"):
            api.snapshot(TARGET, companion=companion)


if __name__ == "__main__":
    unittest.main()
