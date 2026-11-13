"""Qt-owned transparent presenter window for the existing RR2 overlay feed.

Qt owns creation, painting and event dispatch. The supplied read-only/own-window
Win32 bridge keeps placement in signed physical pixels. No target focus or input.
"""
import ctypes
from ctypes import wintypes as W
import math
import threading
from copy import deepcopy

from PIL import Image, ImageChops, ImageQt
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QPointF, QRectF, Qt, QThread, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
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
        self.image, self.scene, self.on_close = None, None, on_close

    def _paint_scene(self, painter):
        width, height = self.scene["size"]
        painter.save()
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setOpacity(self.scene.get("opacity", 1.))
            painter.scale(self.width() / width, self.height() / height)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            for command in self.scene["commands"]:
                color = QColor(command["color"]) if command.get("color") else QColor(0, 0, 0, 0)
                pen = QPen(color, command.get("width", 1)) if command.get("color") else QPen(Qt.PenStyle.NoPen)
                pen.setCosmetic(False)
                painter.setPen(pen)
                kind, xy = command["kind"], command["xy"]
                if kind == "line":
                    path = QPainterPath(QPointF(xy[0], xy[1]))
                    for index in range(2, len(xy), 2):
                        path.lineTo(xy[index], xy[index + 1])
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)
                elif kind == "ellipse":
                    painter.setBrush(QBrush(QColor(command["fill"])) if command.get("fill")
                                     else Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QRectF(xy[0], xy[1], xy[2] - xy[0], xy[3] - xy[1]))
                elif kind == "roundedRect":
                    painter.setBrush(QBrush(QColor(command["fill"])))
                    painter.drawRoundedRect(QRectF(xy[0], xy[1], xy[2] - xy[0], xy[3] - xy[1]),
                                            command["radius"], command["radius"])
                elif kind == "text":
                    font = QFont("Segoe UI")
                    font.setPixelSize(command["fontSize"])
                    painter.setFont(font)
                    metrics = painter.fontMetrics()
                    baseline = xy[1] + metrics.ascent()
                    for line in command["text"].split("\n"):
                        path = QPainterPath()
                        path.addText(QPointF(xy[0], baseline), font, line)
                        stroke_width = command.get("strokeWidth", 0)
                        if stroke_width:
                            painter.strokePath(path, QPen(QColor(command.get("strokeColor") or "#151515"),
                                                         stroke_width * 2))
                        # Fill after the outline so a 2 px keyline cannot cover
                        # the fine stems of a 16 px glyph.
                        painter.fillPath(path, QBrush(color))
                        baseline += metrics.height() + command.get("spacing", 0)
        finally:
            painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
            if self.scene is not None:
                self._paint_scene(painter)
            elif self.image is not None:
                painter.drawImage(QRectF(self.rect()), self.image)
        finally:
            painter.end()

    def closeEvent(self, event):
        event.ignore()
        if self.on_close is not None:
            self.on_close()


class QtOwnedWindow:
    """Single owner-thread Qt widget implementing the overlay window interface."""
    polished_visuals = True
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
        self.widget.scene = None
        self.widget.image = None if image is None else _transparent_image(image)
        self.widget.update()

    def paint_scene(self, scene):
        """Cache renderer-neutral primitives without a full-frame Pillow conversion."""
        self._main()
        if self.destroyed:
            return
        if scene is not None:
            if (not isinstance(scene, dict) or not isinstance(scene.get("size"), (list, tuple))
                    or len(scene["size"]) != 2 or any(type(value) is not int or value <= 0 for value in scene["size"])
                    or not isinstance(scene.get("commands"), list)
                    or type(scene.get("opacity", 1.)) not in (int, float)
                    or not math.isfinite(scene.get("opacity", 1.)) or not 0.2 <= scene.get("opacity", 1.) <= 1.):
                raise ValueError("Invalid Qt overlay primitive scene")
        self.widget.image = None
        self.widget.scene = deepcopy(scene)
        self.widget.update()

    def measure_text(self, text, *, spacing=0, stroke_width=0):
        """Measure labels with the same Qt pixel font used by direct painting."""
        self._main()
        if (not isinstance(text, str) or type(spacing) not in (int, float)
                or type(stroke_width) not in (int, float)):
            raise ValueError("Invalid Qt overlay text measurement")
        font = QFont("Segoe UI")
        font.setPixelSize(16)
        metrics, lines = QFontMetricsF(font), text.split("\n")
        width = max((metrics.horizontalAdvance(line) for line in lines), default=0)
        height = len(lines) * metrics.height() + max(0, len(lines) - 1) * spacing
        padding = max(0, stroke_width) * 2
        return math.ceil(width + padding), math.ceil(height + padding)

    def show(self, physicalrect):
        self._main()
        if self.destroyed:
            return
        if (not isinstance(physicalrect, (list, tuple)) or len(physicalrect) != 4
                or any(type(v) is not int for v in physicalrect) or min(physicalrect[2:]) <= 0):
            raise ValueError("Invalid physical overlay rectangle")
        cached = self.widget.image, self.widget.scene
        self.widget.image, self.widget.scene = None, None
        try:
            if self._presented_rect != tuple(physicalrect):
                self.hide()  # Never stretch an old frame during native placement.
            self.widget.show()  # Qt's precreation no-focus flags govern first show.
            if int(self.widget.winId()) != self.hwnd:
                raise ValueError("Qt recreated the overlay HWND")
            if self._presented_rect != tuple(physicalrect):
                self.api.show(self.hwnd, physicalrect)  # OWN HWND only, signed pixels.
            actual = self._physical_rect()
            if actual != list(physicalrect):
                raise ValueError("Qt overlay physical geometry mismatch")
            ratio = self.widget.devicePixelRatioF()
            if (not math.isfinite(ratio) or ratio <= 0
                    or abs(self.widget.width() * ratio - actual[2]) > 1
                    or abs(self.widget.height() * ratio - actual[3]) > 1):
                raise ValueError("Qt overlay logical geometry has not settled to physical client")
            self.widget.image, self.widget.scene = cached
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
                self.widget.image, self.widget.scene, self.widget.on_close = None, None, None
                self.widget.deleteLater()
                QCoreApplication.sendPostedEvents(self.widget, QEvent.Type.DeferredDelete)
                self.widget = None
            self.on_close = None
