"""Qt-owned transparent presenter window for the existing RR2 overlay feed.

Qt owns creation, painting and event dispatch. The supplied read-only/own-window
Win32 bridge keeps placement in signed physical pixels. No target focus or input.
"""
import ctypes
from ctypes import wintypes as W
import math
import threading

from PIL import Image, ImageChops, ImageQt
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QRectF, Qt, QThread, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget


_application_ref = None


def _application():
    global _application_ref
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Qt overlay construction requires the main GUI thread")
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    if not isinstance(instance, QApplication):
        raise ValueError("Overlay requires QApplication, not a core-only application")
    if instance.thread() != QThread.currentThread():
        raise RuntimeError("Qt application belongs to another GUI thread")
    _application_ref = instance
    return instance


def _transparent_image(image):
    if not isinstance(image, Image.Image) or image.mode != "RGB":
        raise ValueError("Overlay paint expects a Pillow RGB image or None")
    difference = ImageChops.difference(image, Image.new("RGB", image.size, (1, 2, 3)))
    red, green, blue = difference.split()
    mask = ImageChops.lighter(ImageChops.lighter(red, green), blue).point([0] + [255] * 255)
    rgba = image.convert("RGBA")
    rgba.putalpha(mask)
    # Detach from Pillow/ImageQt storage; the feed may release its input now.
    return ImageQt.ImageQt(rgba).copy()


class _OverlayWidget(QWidget):
    def __init__(self, on_close):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.image, self.on_close = None, on_close

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
            if self.image is not None:
                painter.drawImage(QRectF(self.rect()), self.image)
        finally:
            painter.end()

    def closeEvent(self, event):
        event.ignore()
        if self.on_close is not None:
            self.on_close()


class QtOwnedWindow:
    """Single owner-thread Qt widget implementing the overlay window interface."""
    def __init__(self, api, title):
        self.api, self.thread = api, threading.get_ident()
        self.app = _application()
        self.widget, self.hwnd = None, None
        self.destroyed, self.error, self.loop, self.on_close = False, None, None, None
        self._presented_rect = None
        self.callbacks, self.counter = {}, 0
        try:
            self.widget = _OverlayWidget(self._closed_by_window)
            self.widget.setWindowTitle(title)
            # All flags/attributes precede the FIRST native handle creation.
            self.hwnd = int(self.widget.winId())
            if api.own_window(self.hwnd) != self.hwnd:
                raise ValueError("Qt overlay HWND identity changed")
            if self.widget.isVisible():
                raise ValueError("Qt overlay unexpectedly visible during construction")
        except Exception:
            self.destroy()
            raise

    def _main(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Qt overlay requires its creating GUI thread")

    def _invoke(self, callback, args=()):
        try:
            callback(*args)
        except BaseException as exc:
            self.error = exc
            self.quit()

    def _closed_by_window(self):
        self._invoke(self.on_close if self.on_close is not None else self.quit)

    def _physical_rect(self):
        with self.api.dpi():
            rect, origin = W.RECT(), W.POINT()
            if not self.api.u.GetClientRect(self.hwnd, ctypes.byref(rect)):
                raise ValueError("Qt overlay client rectangle unavailable")
            origin.x, origin.y = rect.left, rect.top
            if not self.api.u.ClientToScreen(self.hwnd, ctypes.byref(origin)):
                raise ValueError("Qt overlay physical origin unavailable")
            return [origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top]

    def paint(self, image):
        self._main()
        if self.destroyed:
            return
        self.widget.image = None if image is None else _transparent_image(image)
        self.widget.update()

    def show(self, physicalrect):
        self._main()
        if self.destroyed:
            return
        if (not isinstance(physicalrect, (list, tuple)) or len(physicalrect) != 4
                or any(type(v) is not int for v in physicalrect) or min(physicalrect[2:]) <= 0):
            raise ValueError("Invalid physical overlay rectangle")
        cached = self.widget.image
        self.widget.image = None
        try:
            if self._presented_rect != tuple(physicalrect):
                self.hide()  # Never stretch an old frame during native placement.
            self.widget.show()  # Qt's precreation no-focus flags govern first show.
            if int(self.widget.winId()) != self.hwnd:
                raise ValueError("Qt recreated the overlay HWND")
            self.api.show(self.hwnd, physicalrect)  # OWN HWND only, signed pixels.
            actual = self._physical_rect()
            if actual != list(physicalrect):
                raise ValueError("Qt overlay physical geometry mismatch")
            ratio = self.widget.devicePixelRatioF()
            if (not math.isfinite(ratio) or ratio <= 0
                    or abs(self.widget.width() * ratio - actual[2]) > 1
                    or abs(self.widget.height() * ratio - actual[3]) > 1):
                raise ValueError("Qt overlay logical geometry has not settled to physical client")
            self.widget.image = cached
            self._presented_rect = tuple(physicalrect)
            self.widget.update()
        except Exception:
            self.hide()
            raise

    def hide(self):
        self._main()
        if not self.destroyed and self.widget is not None:
            self.widget.hide()
            self._presented_rect = None
            if self.hwnd is not None:
                self.api.hide(self.hwnd)

    def after(self, milliseconds, callback, *args):
        self._main()
        if self.destroyed:
            raise ValueError("Qt overlay closed")
        if (type(milliseconds) not in (int, float) or not math.isfinite(milliseconds)
                or not 0 <= milliseconds <= 2147483647 or not callable(callback)):
            raise ValueError("Invalid Qt overlay callback")
        self.counter += 1
        identifier = self.counter
        timer = QTimer(self.widget)
        timer.setSingleShot(True)

        def fire():
            self.callbacks.pop(identifier, None)
            timer.deleteLater()
            if not self.destroyed:
                self._invoke(callback, args)

        timer.timeout.connect(fire)
        self.callbacks[identifier] = timer
        timer.start(math.ceil(milliseconds))
        return identifier

    def after_cancel(self, identifier):
        self._main()
        timer = self.callbacks.pop(identifier, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def protocol(self, name, callback):
        self._main()
        if name != "WM_DELETE_WINDOW" or not callable(callback):
            raise ValueError("Unsupported Qt overlay protocol")
        self.on_close = callback

    def quit(self):
        self._main()
        if self.loop is not None:
            self.loop.quit()

    def mainloop(self):
        self._main()
        if not self.destroyed and self.error is None:
            self.loop = QEventLoop()
            try:
                self.loop.exec()
            finally:
                self.loop = None
        if self.error is not None:
            raise self.error

    def update(self):
        self._main()
        if not self.destroyed:
            self.app.processEvents()
        if self.error is not None:
            raise self.error

    def destroy(self):
        self._main()
        if self.destroyed:
            return
        try:
            self.hide()
        finally:
            self.quit()
            for identifier in list(self.callbacks):
                self.after_cancel(identifier)
            self.destroyed = True
            if self.widget is not None:
                self.widget.image, self.widget.on_close = None, None
                self.widget.deleteLater()
                QCoreApplication.sendPostedEvents(self.widget, QEvent.Type.DeferredDelete)
                self.widget = None
            self.on_close = None
