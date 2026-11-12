"""Owned, focus-neutral desktop presentation of already-projected RIFT markers.

No memory reader, game input, focus request or RIFT window mutation lives here.
All public presenter calls (including close) belong to its creating thread.
"""
from contextlib import contextmanager
from copy import deepcopy
import ctypes
from ctypes import wintypes as W
from functools import lru_cache
import math
import os
import socket
import threading
import time
import uuid

from PIL import Image, ImageDraw, ImageFont, ImageWin


OVERLAY_STYLES = 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080


def _target(value):
    fields = ("hostName", "processId", "processStartUtcTicks", "executablePath", "executableSha256", "hwnd")
    if not isinstance(value, dict) or any(k not in value for k in fields):
        raise ValueError("Missing pinned target identity")
    result = {k: value[k] for k in fields}
    if (not isinstance(result["hostName"], str) or result["hostName"].upper() != "AMD-DESKTOP"
            or result["hostName"].casefold() != socket.gethostname().casefold()
            or any(type(result[k]) is not int or result[k] <= 0 for k in ("processId", "hwnd"))
            or not isinstance(result["processStartUtcTicks"], str)
            or not result["processStartUtcTicks"].isdecimal() or int(result["processStartUtcTicks"]) <= 0
            or not isinstance(result["executablePath"], str) or not result["executablePath"]
            or not isinstance(result["executableSha256"], str) or len(result["executableSha256"]) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in result["executableSha256"])):
        raise ValueError("Invalid or wrong-host pinned target")
    return result


class _Win32:
    def __init__(self):
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.d = ctypes.WinDLL("dwmapi", use_last_error=True)
        signatures = [
            (self.u, "IsWindow", [W.HWND], W.BOOL),
            (self.u, "IsWindowVisible", [W.HWND], W.BOOL),
            (self.u, "IsIconic", [W.HWND], W.BOOL),
            (self.u, "GetForegroundWindow", [], W.HWND),
            (self.u, "GetWindowThreadProcessId", [W.HWND, ctypes.POINTER(W.DWORD)], W.DWORD),
            (self.u, "GetClientRect", [W.HWND, ctypes.POINTER(W.RECT)], W.BOOL),
            (self.u, "ClientToScreen", [W.HWND, ctypes.POINTER(W.POINT)], W.BOOL),
            (self.u, "SetThreadDpiAwarenessContext", [ctypes.c_void_p], ctypes.c_void_p),
            (self.u, "GetAncestor", [W.HWND, W.UINT], W.HWND),
            (self.u, "GetWindowLongPtrW", [W.HWND, ctypes.c_int], ctypes.c_ssize_t),
            (self.u, "SetWindowLongPtrW", [W.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t),
            (self.u, "SetWindowPos", [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT], W.BOOL),
            (self.u, "ShowWindow", [W.HWND, ctypes.c_int], W.BOOL),
            (self.k, "OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            (self.k, "CloseHandle", [W.HANDLE], W.BOOL),
            (self.k, "GetProcessTimes", [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4, W.BOOL),
            (self.k, "WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD),
            (self.k, "QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)], W.BOOL),
            (self.d, "DwmGetWindowAttribute", [W.HWND, W.DWORD, ctypes.c_void_p, W.DWORD], ctypes.c_long),
        ]
        for library, name, args, result in signatures:
            fn = getattr(library, name)
            fn.argtypes, fn.restype = args, result

    @contextmanager
    def dpi(self):
        previous = self.u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        if not previous:
            raise ValueError("Physical DPI context unavailable")
        try:
            yield
        finally:
            self.u.SetThreadDpiAwarenessContext(previous)

    def owner(self, hwnd):
        pid = W.DWORD()
        if not self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise ValueError("Window owner unavailable")
        return pid.value

    def snapshot(self, target):
        hwnd, pid = target["hwnd"], target["processId"]
        if (not self.u.IsWindow(hwnd) or not self.u.IsWindowVisible(hwnd)
                or self.u.IsIconic(hwnd) or self.owner(hwnd) != pid):
            raise ValueError("Target window absent, hidden, minimized or owner changed")
        cloaked = W.DWORD()
        if self.d.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4) != 0 or cloaked.value:
            raise ValueError("Target cloaked or cloak status unavailable")
        process = self.k.OpenProcess(0x1000 | 0x100000, False, pid)
        if not process:
            raise ValueError("Target process unavailable")
        try:
            stamps = [W.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(process, *(ctypes.byref(s) for s in stamps)):
                raise ValueError("Target process epoch unavailable")
            ticks = (stamps[0].dwHighDateTime << 32) + stamps[0].dwLowDateTime + 504911232000000000
            path, size = ctypes.create_unicode_buffer(32768), W.DWORD(32768)
            if (ticks != int(target["processStartUtcTicks"]) or self.k.WaitForSingleObject(process, 0) != 258
                    or not self.k.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size))
                    or path.value.casefold() != target["executablePath"].casefold()):
                raise ValueError("Target process epoch or executable path changed")
        finally:
            self.k.CloseHandle(process)
        with self.dpi():
            rect, origin = W.RECT(), W.POINT()
            if not self.u.GetClientRect(hwnd, ctypes.byref(rect)):
                raise ValueError("Client rectangle unavailable")
            origin.x, origin.y = rect.left, rect.top
            if not self.u.ClientToScreen(hwnd, ctypes.byref(origin)):
                raise ValueError("Client origin unavailable")
            width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise ValueError("Invalid client dimensions")
        return {"clientRect": [origin.x, origin.y, width, height],
                "foreground": self.u.GetForegroundWindow() == hwnd}

    def own_window(self, tk_id):
        hwnd = self.u.GetAncestor(tk_id, 2)
        if not hwnd or self.owner(hwnd) != os.getpid():
            raise ValueError("Overlay HWND is not owned by this process")
        style = self.u.GetWindowLongPtrW(hwnd, -20)
        ctypes.set_last_error(0)
        self.u.SetWindowLongPtrW(hwnd, -20, style | OVERLAY_STYLES)
        if ctypes.get_last_error() or self.u.GetWindowLongPtrW(hwnd, -20) & OVERLAY_STYLES != OVERLAY_STYLES:
            raise ValueError("Overlay click-through/no-activation styles unavailable")
        return hwnd

    def show(self, hwnd, rect):
        if not self.u.IsWindow(hwnd) or self.owner(hwnd) != os.getpid():
            raise ValueError("Owned overlay window changed")
        if self.u.GetWindowLongPtrW(hwnd, -20) & OVERLAY_STYLES != OVERLAY_STYLES:
            raise ValueError("Owned overlay styles changed")
        with self.dpi():
            # Signed physical coordinates, including monitors left/above origin.
            # HWND_TOPMOST=-1; SWP_NOACTIVATE|SWP_SHOWWINDOW|SWP_FRAMECHANGED.
            if not self.u.SetWindowPos(hwnd, W.HWND(-1), *rect, 0x10 | 0x40 | 0x20):
                raise ValueError("Overlay placement unavailable")
            self.u.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE, OWN window only.

    def hide(self, hwnd):
        if self.u.IsWindow(hwnd) and self.owner(hwnd) == os.getpid():
            self.u.ShowWindow(hwnd, 0)


@lru_cache(maxsize=1)
def _native():
    return _Win32()


def target_snapshot(target):
    """Read exact process/window epoch and physical client geometry; never focus."""
    return _native().snapshot(_target(target))


def _projection(point, width, height):
    if not isinstance(point, dict):
        raise ValueError("Malformed projection")
    if point.get("status") == "nonpositive-or-small-clip-w":
        w = point.get("clipW")
        if type(w) not in (int, float) or not math.isfinite(w) or w > 1e-5:
            raise ValueError("Malformed clipped projection")
        return None
    if point.get("status") != "available-candidate":
        raise ValueError("Projection unavailable or malformed")
    values = [point.get(k) for k in ("normalizedX", "normalizedY", "clipW")]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Malformed projection coordinates")
    x, y, w = values
    inside = point.get("insideViewportCandidate")
    if type(inside) is not bool:
        raise ValueError("Malformed viewport membership")
    if not inside or w <= 1e-5 or not 0 <= x <= 1 or not 0 <= y <= 1:
        return None
    return x * width, y * height


_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)


class _WindowClass(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("procedure", _WNDPROC), ("classExtra", ctypes.c_int),
                ("windowExtra", ctypes.c_int), ("instance", W.HINSTANCE), ("icon", W.HANDLE),
                ("cursor", W.HANDLE), ("background", W.HBRUSH), ("menu", W.LPCWSTR), ("name", W.LPCWSTR)]


class _Paint(ctypes.Structure):
    _fields_ = [("dc", W.HDC), ("erase", W.BOOL), ("rect", W.RECT),
                ("restore", W.BOOL), ("update", W.BOOL), ("reserved", W.BYTE * 32)]


class _OwnedWindow:
    """One native overlay HWND and its small owner-thread callback/message loop."""
    def __init__(self, api, title):
        self.api, self.thread = api, threading.get_ident()
        self.hwnd, self.brush, self.atom = None, None, None
        self.callbacks, self.counter, self.on_close = {}, 0, None
        self.running, self.destroyed, self.error, self.dib = False, False, None, None
        self.class_name = "RR2WaypointOverlay_" + uuid.uuid4().hex
        self.u, self.k = api.u, api.k
        self.g = ctypes.WinDLL("gdi32", use_last_error=True)
        for lib, name, args, result in [
            (self.k, "GetModuleHandleW", [W.LPCWSTR], W.HMODULE),
            (self.u, "RegisterClassW", [ctypes.POINTER(_WindowClass)], W.WORD),
            (self.u, "UnregisterClassW", [W.LPCWSTR, W.HINSTANCE], W.BOOL),
            (self.u, "CreateWindowExW", [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, ctypes.c_void_p], W.HWND),
            (self.u, "DefWindowProcW", [W.HWND, W.UINT, W.WPARAM, W.LPARAM], ctypes.c_ssize_t),
            (self.u, "DestroyWindow", [W.HWND], W.BOOL),
            (self.u, "SetLayeredWindowAttributes", [W.HWND, W.DWORD, W.BYTE, W.DWORD], W.BOOL),
            (self.u, "InvalidateRect", [W.HWND, ctypes.c_void_p, W.BOOL], W.BOOL),
            (self.u, "BeginPaint", [W.HWND, ctypes.POINTER(_Paint)], W.HDC),
            (self.u, "EndPaint", [W.HWND, ctypes.POINTER(_Paint)], W.BOOL),
            (self.u, "PeekMessageW", [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT], W.BOOL),
            (self.u, "TranslateMessage", [ctypes.POINTER(W.MSG)], W.BOOL),
            (self.u, "DispatchMessageW", [ctypes.POINTER(W.MSG)], ctypes.c_ssize_t),
            (self.g, "CreateSolidBrush", [W.DWORD], W.HBRUSH),
            (self.g, "DeleteObject", [W.HANDLE], W.BOOL),
        ]:
            fn = getattr(lib, name)
            fn.argtypes, fn.restype = args, result
        self.instance = self.k.GetModuleHandleW(None)
        self.procedure = _WNDPROC(self._message)  # Keep callback alive until unregister.
        try:
            with api.dpi():
                self.brush = self.g.CreateSolidBrush(0x030201)
                if not self.brush:
                    raise ValueError("Overlay background brush unavailable")
                cls = _WindowClass(0, self.procedure, 0, 0, self.instance, None, None,
                                   self.brush, None, self.class_name)
                self.atom = self.u.RegisterClassW(ctypes.byref(cls))
                if not self.atom:
                    raise ValueError("Overlay window class unavailable")
                # Styles are present at creation. No Tk wrapper or first-window
                # activation, and no WS_VISIBLE until an admitted fresh frame.
                self.hwnd = self.u.CreateWindowExW(OVERLAY_STYLES, self.class_name, title,
                    0x80000000, 0, 0, 1, 1, None, None, self.instance, None)
                if not self.hwnd:
                    raise ValueError("Overlay window creation failed")
                if not self.u.SetLayeredWindowAttributes(self.hwnd, 0x030201, 255, 1):
                    raise ValueError("Overlay color-key transparency unavailable")
                api.own_window(self.hwnd)
        except Exception:
            self.destroy()
            raise

    def _main(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Overlay window operations require its creating thread")

    def _message(self, hwnd, message, wparam, lparam):
        try:
            if message == 0x000F:  # WM_PAINT, cached image only; no acquisition.
                paint = _Paint()
                dc = self.u.BeginPaint(hwnd, ctypes.byref(paint))
                try:
                    if dc and self.dib is not None:
                        self.dib.draw(dc, (0, 0, *self.dib.size))
                finally:
                    self.u.EndPaint(hwnd, ctypes.byref(paint))
                return 0
            if message == 0x0010:  # WM_CLOSE
                if self.on_close is not None:
                    self.on_close()
                else:
                    self.quit()
                return 0
            if message == 0x0002:  # WM_DESTROY
                self.running = False
                return 0
            if message == 0x0084:  # HTTRANSPARENT; layered style also passes clicks.
                return -1
            if message == 0x0021:  # MA_NOACTIVATE, own window only.
                return 3
            return self.u.DefWindowProcW(hwnd, message, wparam, lparam)
        except BaseException as exc:
            self.error, self.running = exc, False
            return 0

    def paint(self, image):
        self._main()
        self.dib = ImageWin.Dib(image) if image is not None else None
        if self.hwnd and not self.destroyed:
            self.u.InvalidateRect(self.hwnd, None, True)

    def after(self, milliseconds, callback, *args):
        self._main()
        if self.destroyed:
            raise ValueError("Overlay window closed")
        if type(milliseconds) not in (int, float) or not math.isfinite(milliseconds) or milliseconds < 0 or not callable(callback):
            raise ValueError("Invalid overlay callback")
        self.counter += 1
        self.callbacks[self.counter] = (time.monotonic() + milliseconds / 1000, callback, args)
        return self.counter

    def after_cancel(self, identifier):
        self._main()
        self.callbacks.pop(identifier, None)

    def protocol(self, name, callback):
        self._main()
        if name != "WM_DELETE_WINDOW" or not callable(callback):
            raise ValueError("Unsupported overlay window protocol")
        self.on_close = callback

    def update(self):
        self._main()
        if self.destroyed:
            return
        message = W.MSG()
        # Filter to our HWND; do not consume another application's messages.
        while not self.destroyed and self.u.PeekMessageW(ctypes.byref(message), self.hwnd, 0, 0, 1):
            self.u.TranslateMessage(ctypes.byref(message))
            self.u.DispatchMessageW(ctypes.byref(message))
        if self.error is not None:
            raise self.error
        now = time.monotonic()
        due = [key for key, (deadline, _, _) in self.callbacks.items() if deadline <= now]
        for key in due:
            entry = self.callbacks.pop(key, None)
            if entry is not None and not self.destroyed:
                entry[1](*entry[2])

    def mainloop(self):
        self._main()
        self.running = True
        while self.running and not self.destroyed:
            self.update()
            if self.running and not self.destroyed:
                time.sleep(.01)

    def quit(self):
        self._main()
        self.running = False

    def destroy(self):
        self._main()
        if self.destroyed:
            return
        self.running, self.destroyed = False, True
        self.callbacks.clear()
        if self.hwnd and self.u.IsWindow(self.hwnd):
            self.u.DestroyWindow(self.hwnd)
        if self.atom:
            self.u.UnregisterClassW(self.class_name, self.instance)
        if self.brush:
            self.g.DeleteObject(self.brush)
        self.dib = None


class PhysicalWaypointOverlay:
    def __init__(self, target, *, max_age=.8):
        self.target = _target(target)
        if type(max_age) not in (int, float) or not math.isfinite(max_age) or max_age <= 0:
            raise ValueError("Invalid overlay freshness limit")
        self.max_age, self.thread = max_age, threading.get_ident()
        self.frame, self.closed, self.reason = None, False, "waiting-for-frame"
        self.api, self.window, self.hwnd, self.timer = _native(), None, None, None
        try:
            self.window = _OwnedWindow(self.api, f"RR2 Waypoint Overlay | PID {self.target['processId']}")
            self.hwnd = self.window.hwnd
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.timer = self.window.after(50, self._tick)
        except Exception:
            if self.window is not None:
                self.window.destroy()
            raise

    def _main(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Overlay operations require the creating thread")

    def _validate(self, frame):
        if not isinstance(frame, dict) or _target(frame.get("target")) != self.target:
            raise ValueError("Overlay target mismatch")
        acquired = frame.get("acquiredMonotonic")
        if type(acquired) not in (int, float) or not math.isfinite(acquired) or not 0 <= time.monotonic() - acquired <= self.max_age:
            raise ValueError("Stale or future overlay frame")
        rect = frame.get("clientRect")
        if (not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect)
                or rect[2] <= 0 or rect[3] <= 0):
            raise ValueError("Malformed physical client rectangle")
        snapshot = target_snapshot(self.target)
        if snapshot["foreground"] is not True or snapshot["clientRect"] != rect:
            raise ValueError("Target foreground or client geometry changed")
        if not isinstance(frame.get("points"), list):
            raise ValueError("Malformed marker list")
        for row in frame["points"]:
            if not isinstance(row, dict) or type(row.get("number")) is not int or row["number"] <= 0 or not isinstance(row.get("label"), str):
                raise ValueError("Malformed marker")
            _projection(row.get("ground"), *rect[2:])
            _projection(row.get("beaconTop"), *rect[2:])
        _projection(frame.get("playerGround"), *rect[2:])
        return rect

    def present(self, frame):
        self._main()
        if self.closed:
            return False
        try:
            rect = self._validate(frame)
            image = Image.new("RGB", tuple(rect[2:]), (1, 2, 3))
            draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=16)
            for marker in frame["points"]:
                ground = _projection(marker["ground"], *rect[2:])
                top = _projection(marker["beaconTop"], *rect[2:])
                if ground is not None:
                    x, y = ground
                    draw.ellipse((x-7, y-7, x+7, y+7), outline="#ffd54f", width=2)
                    draw.text((x+10, y-10), f"{marker['number']} {marker['label']}", fill="#ffd54f", font=font, anchor="ls")
                    if top is not None:
                        draw.line((*ground, *top), fill="#ffd54f", width=2)
            player = _projection(frame["playerGround"], *rect[2:])
            if player is not None:
                x, y = player
                draw.line((x-6, y, x+6, y), fill="#51e5ff", width=2)
                draw.line((x, y-6, x, y+6), fill="#51e5ff", width=2)
            self.window.paint(image)
            self.api.show(self.hwnd, rect)
            self.frame, self.reason = deepcopy(frame), None
            return True
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.hide(str(exc))
            return False

    def hide(self, reason):
        self._main()
        if not self.closed:
            try:
                self.api.hide(self.hwnd)
            finally:
                self.window.paint(None)
                self.frame, self.reason = None, str(reason)

    def _tick(self):
        self._main()
        if self.closed:
            return
        if self.frame is not None:
            try:
                self._validate(self.frame)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.hide(str(exc))
        self.timer = self.window.after(50, self._tick)

    def close(self):
        self._main()
        if not self.closed:
            try:
                self.hide("closed")
            finally:
                self.closed = True
                try:
                    if self.timer is not None:
                        self.window.after_cancel(self.timer)
                finally:
                    self.window.destroy()

    def run(self):
        self._main()
        if not self.closed:
            try:
                self.window.mainloop()
            finally:
                self.close()
