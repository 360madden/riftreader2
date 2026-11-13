"""Run with QT_QPA_PLATFORM=offscreen; fake Win32 bridge, no desktop actions."""
from contextlib import nullcontext
import os
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

# These tests must never accidentally create a desktop Qt platform window.
if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
    raise unittest.SkipTest("Qt pilot tests require QT_QPA_PLATFORM=offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from scripts import qt_waypoint_overlay as overlay


class QtWindowTests(unittest.TestCase):
    def setUp(self):
        self.rect = [-1920, -20, 320, 240]
        def rect(hwnd, output):
            output._obj.right, output._obj.bottom = self.rect[2:]
            return True
        def origin(hwnd, output):
            output._obj.x, output._obj.y = self.rect[:2]
            return True
        self.creation = []
        def own(hwnd):
            widget = overlay._application().topLevelWidgets()[-1]
            self.creation.append((hwnd, widget.windowFlags(), widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground),
                                  widget.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating), widget.isVisible()))
            return hwnd
        self.api = NS(own_window=Mock(side_effect=own), show=Mock(), hide=Mock(), dpi=lambda: nullcontext(),
                      u=NS(GetClientRect=rect, ClientToScreen=origin, IsWindowVisible=Mock(return_value=True)))
        self.window = overlay.QtOwnedWindow(self.api, "RR2 Waypoint Overlay | PID 123")
        self.addCleanup(self.window.destroy)
        def place(hwnd, physicalrect):
            ratio = self.window.widget.devicePixelRatioF()
            self.window.widget.resize(round(physicalrect[2] / ratio), round(physicalrect[3] / ratio))
        self.api.show.side_effect = place

    def test_precreation_flags_hidden_initial_state_and_signed_physical_show(self):
        hwnd, flags, translucent, no_activate, visible = self.creation[0]
        for flag in (Qt.WindowType.Tool, Qt.WindowType.FramelessWindowHint,
                     Qt.WindowType.WindowStaysOnTopHint, Qt.WindowType.WindowTransparentForInput,
                     Qt.WindowType.WindowDoesNotAcceptFocus):
            self.assertEqual(flag, flags & flag)
        self.assertTrue(translucent)
        self.assertTrue(no_activate)
        self.assertFalse(visible)
        self.window.show(self.rect)
        self.api.show.assert_called_once_with(hwnd, self.rect)
        self.assertEqual(hwnd, int(self.window.widget.winId()))
        self.assertTrue(self.window.widget.isVisible())
        self.window.hide()
        self.assertFalse(self.window.widget.isVisible())
        self.api.hide.assert_called_with(hwnd)

    def test_true_alpha_key_tiny_color_difference_and_detached_cache(self):
        image = Image.new("RGB", (3, 1), (1, 2, 3))
        image.putpixel((1, 0), (1, 2, 4))
        image.putpixel((2, 0), (255, 213, 79))
        self.window.paint(image)
        cached = self.window.widget.image
        self.assertEqual(0, cached.pixelColor(0, 0).alpha())
        self.assertEqual(255, cached.pixelColor(1, 0).alpha())
        self.assertEqual((255, 213, 79, 255), cached.pixelColor(2, 0).getRgb())
        image.putpixel((2, 0), (0, 0, 0))
        self.assertEqual((255, 213, 79, 255), cached.pixelColor(2, 0).getRgb())
        self.window.paint(None)
        self.assertIsNone(self.window.widget.image)

    def test_primitive_scene_uses_widget_cache_and_unchanged_show_skips_reposition(self):
        scene = {"size": (320, 240), "commands": [
            {"kind": "line", "xy": (10, 10, 50, 50), "color": "#7cffff", "width": 3},
            {"kind": "ellipse", "xy": (42, 42, 58, 58), "color": "#ffd54f", "width": 2},
            {"kind": "roundedRect", "xy": (56, 34, 130, 64), "radius": 7,
             "color": "#80ffffff", "fill": "#dc111821", "width": 1},
            {"kind": "text", "xy": (60, 40), "text": "NEXT 1", "color": "#ffd54f",
             "strokeWidth": 1, "strokeColor": "#151515", "fontSize": 16, "spacing": 0},
        ]}
        self.window.paint_scene(scene)
        scene["commands"].clear()  # The cached frame is detached from its producer.
        self.assertIsNone(self.window.widget.image)
        self.assertEqual(4, len(self.window.widget.scene["commands"]))
        self.window.show(self.rect)
        rendered = self.window.widget.grab().toImage()  # Executes the direct QPainter primitive path.
        # The colored glyph fill must survive its dark readability outline.
        self.assertTrue(any(rendered.pixelColor(x, y).red() > 220
                            and rendered.pixelColor(x, y).green() > 170
                            and rendered.pixelColor(x, y).blue() < 130
                            for y in range(35, 65) for x in range(58, 130)))
        self.window.show(self.rect)
        self.api.show.assert_called_once_with(self.window.hwnd, self.rect)
        self.assertIsNotNone(self.window.widget.scene)
        self.window.paint(None)
        self.assertIsNone(self.window.widget.scene)

    def test_same_geometry_recovers_native_hidden_window_on_next_frame(self):
        self.window.paint_scene({"size": (320, 240), "commands": []})
        self.window.show(self.rect)
        self.assertTrue(self.window.widget.isVisible())
        self.api.u.IsWindowVisible.return_value = False
        self.window.show(self.rect)
        self.assertEqual(2, self.api.show.call_count)
        self.api.show.assert_called_with(self.window.hwnd, self.rect)
        self.assertIsNotNone(self.window.widget.scene)

    def test_text_measurement_uses_painted_pixel_font_and_multiline_spacing(self):
        single = self.window.measure_text("NEXT 1", spacing=2, stroke_width=0)
        multiline = self.window.measure_text("NEXT 1\nCorner", spacing=2, stroke_width=1)
        self.assertGreater(single[0], 0)
        self.assertGreater(single[1], 0)
        self.assertGreater(multiline[1], single[1] * 2)
        self.assertGreaterEqual(multiline[0], single[0])

    def test_scene_opacity_applies_after_transparent_clear(self):
        scene = {"size": (320, 240), "opacity": .4, "commands": [
            {"kind": "ellipse", "xy": (40, 40, 80, 80), "color": "#ffd54f",
             "fill": "#ffd54f", "width": 2},
        ]}
        self.window.paint_scene(scene)
        self.window.show(self.rect)
        rendered = self.window.widget.grab().toImage()
        center = rendered.pixelColor(60, 60)
        self.assertAlmostEqual(round(.4 * 255), center.alpha(), delta=2)
        for actual, expected in zip((center.red(), center.green(), center.blue()), (255, 213, 79)):
            self.assertAlmostEqual(expected, actual, delta=1)

    def test_flags_and_attributes_exist_before_first_explicit_native_handle_request(self):
        original = overlay._OverlayWidget.winId
        checks = []
        def guarded(widget):
            self.assertTrue(widget.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
            self.assertTrue(widget.windowFlags() & Qt.WindowType.WindowTransparentForInput)
            self.assertTrue(widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
            self.assertTrue(widget.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
            self.assertFalse(widget.isVisible())
            checks.append(True)
            return original(widget)
        with patch.object(overlay._OverlayWidget, "winId", guarded):
            window = overlay.QtOwnedWindow(self.api, "flag-order pilot")
        try:
            self.assertEqual([True], checks)
        finally:
            window.destroy()

    def test_timer_cancel_and_owner_local_event_loop(self):
        called, cancelled = Mock(), Mock()
        identifier = self.window.after(0, cancelled)
        self.window.after_cancel(identifier)
        self.window.after(0, called, "value")
        self.window.after(1, self.window.quit)
        with patch.object(self.window.app, "quit") as global_quit:
            self.window.mainloop()
        called.assert_called_once_with("value")
        cancelled.assert_not_called()
        global_quit.assert_not_called()
        self.assertEqual({}, self.window.callbacks)

    def test_callback_keyboard_interrupt_is_raised_to_feed_cleanup(self):
        def interrupted(): raise KeyboardInterrupt("stop feed")
        self.window.after(0, interrupted)
        with self.assertRaisesRegex(KeyboardInterrupt, "stop feed"):
            self.window.mainloop()
        self.window.destroy()
        self.assertTrue(self.window.destroyed)

    def test_close_callback_error_is_captured_and_destroy_clears_timers(self):
        def failed(): raise ValueError("close callback failed")
        self.window.protocol("WM_DELETE_WINDOW", failed)
        self.window.widget.close()
        with self.assertRaisesRegex(ValueError, "close callback failed"):
            self.window.mainloop()
        timer = self.window.after(1000, lambda: None)
        self.window.destroy()
        self.assertEqual({}, self.window.callbacks)
        self.assertIsNone(self.window.widget)
        self.assertTrue(self.window.destroyed)
        self.window.destroy()

    def test_geometry_mismatch_hides_instead_of_showing_misaligned_frame(self):
        with self.assertRaisesRegex(ValueError, "geometry mismatch"):
            self.window.show([-1910, -20, 320, 240])
        self.assertFalse(self.window.widget.isVisible())
        self.api.hide.assert_called_with(self.window.hwnd)

    def test_first_stale_logical_geometry_withholds_image_then_fresh_frame_can_show(self):
        image = Image.new("RGB", (320, 240), (255, 213, 79))
        self.window.paint(image)
        self.api.show.side_effect = None  # Native physical rect changes; Qt remains stale.
        self.window.widget.resize(640, 480)
        with self.assertRaisesRegex(ValueError, "logical geometry"):
            self.window.show(self.rect)
        self.assertFalse(self.window.widget.isVisible())
        self.assertIsNone(self.window.widget.image)
        ratio = self.window.widget.devicePixelRatioF()
        self.window.widget.resize(round(320 / ratio), round(240 / ratio))
        # Only a new frame supplies an image after refused placement.
        self.window.paint(image)
        self.window.show(self.rect)
        self.assertTrue(self.window.widget.isVisible())
        self.assertEqual((255, 213, 79, 255), self.window.widget.image.pixelColor(0, 0).getRgb())

    def test_blank_during_placement_restored_without_global_event_processing(self):
        self.window.paint(Image.new("RGB", (320, 240), (255, 213, 79)))
        original = self.api.show.side_effect
        def place(hwnd, physicalrect):
            self.assertIsNone(self.window.widget.image)
            original(hwnd, physicalrect)
        self.api.show.side_effect = place
        with patch.object(self.window.app, "processEvents") as process:
            self.window.show(self.rect)
            self.window.show(self.rect)
        process.assert_not_called()
        self.assertIsNotNone(self.window.widget.image)

    def test_fractional_scale_geometry_allows_only_one_physical_pixel_rounding(self):
        self.window.widget.resize(256, 192)
        self.api.show.side_effect = None
        with patch.object(self.window.widget, "devicePixelRatioF", return_value=1.25):
            self.window.show(self.rect)
            self.window.widget.resize(255, 192)  # 1.25 physical pixels short.
            with self.assertRaisesRegex(ValueError, "logical geometry"):
                self.window.show(self.rect)

    def test_gui_thread_guards_run_before_bridge_or_widget_changes(self):
        errors = []
        def worker():
            for operation in (lambda: self.window.paint(None), self.window.hide, self.window.destroy,
                              lambda: self.window.after(0, lambda: None)):
                try: operation()
                except RuntimeError as exc: errors.append(str(exc))
        thread = threading.Thread(target=worker)
        thread.start(); thread.join()
        self.assertEqual(4, len(errors))
        self.api.show.assert_not_called()
        self.api.hide.assert_not_called()


if __name__ == "__main__":
    unittest.main()
