"""Overlay presenter tests: fake Tk and Win32 only; no desktop/native reads."""
from contextlib import nullcontext
from copy import deepcopy
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

    def test_watchdog_hides_expired_frame_and_close_cancels_timer(self):
        self.assertTrue(self.presenter.present(frame()))
        self.clock.return_value = 101.
        self.presenter._tick()
        self.assertIsNone(self.presenter.frame)
        self.assertIn("Stale", self.presenter.reason)
        self.presenter.close()
        calls = self.presenter.window.calls
        self.assertTrue(any(name == "destroy" for name, args, kwargs in calls))
        self.assertFalse(self.presenter.present(frame()))

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


if __name__ == "__main__":
    unittest.main()
