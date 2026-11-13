"""Small, non-activating player-relative radar in the existing Qt presenter."""
import ctypes
import datetime
import os
import json
import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from scripts.waypoint_map import LocalMap, ZOOM_RADII, _clip_segment, _label_box
from scripts.waypoint_beacon_pose import _target
from scripts.waypoint_progress import write_json_atomic
from scripts.waypoint_height_context import height_context, height_cue


DEFAULT_CONFIG = {"version": 1, "enabled": False, "unlocked": False, "radius": 10, "opacity": .9}


def load_config(path, fallback=None):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1
                or type(data.get("enabled")) is not bool or type(data.get("unlocked")) is not bool
                or type(data.get("radius")) not in (int, float) or data["radius"] not in ZOOM_RADII
                or type(data.get("opacity")) not in (int, float) or not math.isfinite(data["opacity"])
                or not .2 <= data["opacity"] <= 1):
            return fallback
        position = data.get("position")
        if position is not None:
            revision = position.get("revision") if isinstance(position, dict) else None
            valid_revision = (type(revision) in (str, int)
                              and (not isinstance(revision, str) or 1 <= len(revision) <= 128))
            reset = isinstance(position, dict) and position.get("reset") is True
            coordinates = (isinstance(position, dict)
                           and type(position.get("x")) is int and type(position.get("y")) is int
                           and -100000 <= position["x"] <= 100000
                           and -100000 <= position["y"] <= 100000)
            if (not valid_revision or reset == coordinates
                    or reset and ("x" in position or "y" in position)):
                return fallback
        status_path = data.get("statusPath")
        if status_path is not None and (not isinstance(status_path, str) or not status_path
                or not Path(status_path).is_absolute() or status_path.startswith(("\\\\", "//"))):
            return fallback
        return data
    except (OSError, ValueError, TypeError):
        return fallback


def load_exploration(path, frame, session_id, max_age, *, now=None):
    """Accept feedback only for the current owner, session and source sample."""
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576:
            return None
        data = json.loads(raw)
        owner = data["owner"]
        acquired = data["acquiredMonotonic"]
        clock = time.monotonic() if now is None else now
        if (type(data.get("version")) is not int or data["version"] != 1
                or _target(owner["target"]) != _target(frame["target"])
                or owner["playerKey"] != frame["playerPose"]["playerKey"]
                or owner["sessionId"] != session_id
                or type(acquired) not in (int, float) or not math.isfinite(acquired)
                or not 0 <= clock - acquired <= max_age
                or not isinstance(data["trail"], list)
                or data["guidance"] is not None and not isinstance(data["guidance"], dict)):
            return None
        segments = []
        count = 0
        for segment in data["trail"]:
            if not isinstance(segment, list):
                return None
            clean = []
            for point in segment:
                x, z = point["x"], point["z"]
                if any(type(v) not in (int, float) or not math.isfinite(v) for v in (x, z)):
                    return None
                clean.append((x, z))
                count += 1
                if count > 2000:
                    return None
            segments.append(clean)
        return {"guidance": data["guidance"], "trail": segments}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def trail_lines(view, segments, bounds):
    """Clip each observed segment independently; never bridge discontinuities."""
    result = []
    for segment in segments:
        previous = None
        for x, z in segment:
            current = view.world_to_canvas(x, z)
            if previous is not None:
                line = _clip_segment(previous, current, bounds)
                if line is not None:
                    result.append(line)
            previous = current
    return result


def radar_height_contexts(points, frame):
    """Use the presenter's resolved estimates, retaining route measurement kinds."""
    player_y = frame['playerPose']['position'].get('y')
    projected = {point['number']: point for point in frame.get('points', [])}
    return {point['number']: height_context(
        projected[point['number']] if 'displayHeightCandidate' in projected.get(point['number'], {})
        else point, player_y) for point in points}


class CompactRadar(QWidget):
    def __init__(self, api):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowTitle("RR2 Compact Radar")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(264, 318)
        self.api, self.frame, self.points, self.config = api, None, [], None
        self.drag_offset = None
        self.exploration = None
        self.placed = False
        self.target_rect = None
        self.offset = None
        self.applied_revision = None
        self.status_path = None
        self.last_target = None
        self.last_status_at = 0.0
        self.hwnd = int(self.winId())
        if api.own_window(self.hwnd) != self.hwnd:
            raise ValueError("radar HWND identity changed")
        self._set_unlocked(False)

    def _set_unlocked(self, unlocked):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not unlocked)
        if __import__('os').name == 'nt':
            user32 = ctypes.windll.user32
            get = user32.GetWindowLongW
            set_ = user32.SetWindowLongW
            get.argtypes = [ctypes.c_void_p, ctypes.c_int]
            set_.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            style = get(self.hwnd, -20)
            set_(self.hwnd, -20, (style & ~0x20 if unlocked else style | 0x20) | 0x08000000)

    def present(self, frame, route, config, exploration=None):
        if config:
            self.status_path = config.get("statusPath")
        if frame:
            self.last_target = frame.get("target")
        if not config or not config["enabled"]:
            self.clear()
            return
        pose = frame["playerPose"]
        vals = [pose["position"]["x"], pose["position"]["z"], pose["bearing"]]
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in vals):
            self.clear()
            return
        change_unlock = self.config is None or self.config["unlocked"] != config["unlocked"]
        self.config, self.frame, self.points = dict(config), frame, route["points"]
        self.exploration = exploration
        self.setWindowOpacity(config["opacity"])
        rect = list(frame["clientRect"])
        position = config.get("position")
        new_position = position is not None and position["revision"] != self.applied_revision
        relocate = not self.placed or self.target_rect != rect or new_position
        if not self.isVisible():
            self.show()
        if relocate:
            x, y, w, h = rect
            ratio = self.devicePixelRatioF()
            width, height = round(self.width()*ratio), round(self.height()*ratio)
            # Keep signed physical coordinates and the user's relative placement.
            dx, dy = (((18, max(18, h-height-150)) if position.get("reset") else
                       (position["x"], position["y"])) if new_position
                      else self.offset or (18, max(18, h-height-150)))
            dx, dy = max(0, min(dx, w-width)), max(0, min(dy, h-height))
            self._set_unlocked(False)
            self.api.show(self.hwnd, [x+dx, y+dy, width, height])
            self.offset = (dx, dy)
            self.target_rect = rect
            self.placed = True
            if new_position:
                self.applied_revision = position["revision"]
        if change_unlock or relocate:
            self._set_unlocked(config["unlocked"])
        self.update()
        self._publish_status()

    def _publish_status(self, *, force=False):
        if not self.status_path:
            return
        now = time.monotonic()
        if not force and now - self.last_status_at < .2:
            return
        position = None
        if self.isVisible() and self.target_rect is not None and os.name == 'nt':
            try:
                from ctypes import wintypes
                rect = wintypes.RECT()
                with self.api.dpi():
                    if self.api.u.GetWindowRect(self.hwnd, ctypes.byref(rect)):
                        position = {"x": rect.left - self.target_rect[0], "y": rect.top - self.target_rect[1]}
            except (AttributeError, OSError):
                pass
        status = {"version": 1, "sampledAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "presenterPid": os.getpid(), "target": self.last_target,
                  "visible": self.isVisible(), "position": position,
                  "range": self.config.get("radius") if self.config else None,
                  "opacity": self.config.get("opacity") if self.config else None,
                  "unlocked": bool(self.config and self.config.get("unlocked")) if self.isVisible() else False,
                  "dragging": self.drag_offset is not None,
                  "appliedRevision": self.applied_revision}
        try:
            write_json_atomic(Path(self.status_path), status, durable=False)
            self.last_status_at = now
        except (OSError, ValueError, TypeError):
            pass  # Feedback is advisory; a bad destination must not crash the presenter.

    def clear(self):
        was_visible = self.isVisible()
        self.frame, self.points, self.exploration = None, [], None
        self.hide()
        self.update()
        self._publish_status(force=was_visible)

    def mousePressEvent(self, event):
        if self.config and self.config["unlocked"] and event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None and self.target_rect is not None:
            if __import__('os').name == 'nt':
                from ctypes import wintypes
                rect = wintypes.RECT()
                with self.api.dpi():
                    if self.api.u.GetWindowRect(self.hwnd, ctypes.byref(rect)):
                        self.offset = (rect.left-self.target_rect[0], rect.top-self.target_rect[1])
        self.drag_offset = None

    def paintEvent(self, event):
        if self.frame is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#385064'), 1))
        p.setBrush(QColor('#101e2b'))
        p.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 12, 12)
        font = QFont('Segoe UI', 9, QFont.Weight.DemiBold)
        p.setFont(font); p.setPen(QColor('#dce9ed'))
        p.drawText(QRectF(16, 8, 150, 22), Qt.AlignmentFlag.AlignVCenter, 'LOCAL RADAR')
        p.setPen(QColor('#96b0bd'))
        p.drawText(QRectF(155, 8, 92, 22), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f'{self.config["radius"]:g} units')
        p.save(); p.translate(0, 30)
        view = LocalMap(self.frame['playerPose']['position']['x'], self.frame['playerPose']['position']['z'],
                        self.frame['playerPose']['bearing'], 264, 250, self.config['radius'])
        cx, cy = view.width/2, view.height/2
        bounds = (12, 12, view.width-12, view.height-12)
        p.setClipRect(QRectF(*[bounds[0], bounds[1], bounds[2]-bounds[0], bounds[3]-bounds[1]]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for frac in (.5, 1):
            r = view.scale * view.radius * frac
            p.setPen(QPen(QColor('#304657'), 1)); p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor('#304657'), 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(cx, 12), QPointF(cx, 238)); p.drawLine(QPointF(12, cy), QPointF(252, cy))
        exploration = self.exploration or {}
        p.setPen(QPen(QColor('#4aa88f'), 2))
        for line in trail_lines(view, exploration.get('trail', []), bounds):
            p.drawLine(QPointF(*line[:2]), QPointF(*line[2:]))
        visible, prior = [], (cx, cy)
        contexts = radar_height_contexts(self.points, self.frame)
        guidance = exploration.get('guidance') or {}
        index = guidance.get('activeIndex') if guidance.get('status') == 'active' else None
        active = {index + 1} if type(index) is int and 0 <= index < len(self.points) else set()
        completed = {i + 1 for i in guidance.get('completedIndices', []) if type(i) is int and 0 <= i < len(self.points)} if isinstance(guidance.get('completedIndices', []), list) else set()
        if not active:
            active = {point['number'] for point in self.frame['points'] if point.get('displayLandmark') and not guidance}

        for point in self.points:
            xyz = point['xyz']; pos = view.world_to_canvas(float(xyz['x']), float(xyz['z']))
            segment = _clip_segment(prior, pos, bounds)
            if segment:
                p.setPen(QPen(QColor('#51859c'), 1.5)); p.drawLine(QPointF(*segment[:2]), QPointF(*segment[2:]))
            if bounds[0]+7 <= pos[0] <= bounds[2]-7 and bounds[1]+7 <= pos[1] <= bounds[3]-7:
                visible.append((point['number'], pos))
            prior = pos
        occupied = [(cx-20, cy-20, cx+20, cy+25)] + [(x-8,y-8,x+8,y+8) for _,(x,y) in visible]
        for number, pos in visible:
            marker_label = str(number) + height_cue(contexts[number])
            box = _label_box(pos, marker_label, (16, 16, 248, 234), occupied); occupied.append(box)
            endpoint = (max(box[0], min(box[2], pos[0])), max(box[1], min(box[3], pos[1])))
            p.setPen(QPen(QColor('#496172'), 1)); p.drawLine(QPointF(*pos), QPointF(*endpoint))
            p.setBrush(QColor('#1c3040')); p.drawRoundedRect(QRectF(box[0],box[1],box[2]-box[0],box[3]-box[1]), 4, 4)
            color = QColor('#f3c76a' if number in active else '#536b77' if number in completed else '#82bad0')
            p.setPen(color); p.drawText(QRectF(box[0],box[1],box[2]-box[0],box[3]-box[1]), Qt.AlignmentFlag.AlignCenter, marker_label)
            p.setBrush(color); p.setPen(QPen(QColor('#101e2b'), 2)); p.drawEllipse(QPointF(*pos), 5, 5)
        if active:
            target = next((point for point in self.points if point['number'] in active), None)
            if target:
                xy = view.world_to_canvas(float(target['xyz']['x']), float(target['xyz']['z']))
                dx, dy = xy[0]-cx, xy[1]-cy
                length = math.hypot(dx, dy)
                edge = view.scale * view.radius - 5
                if length > edge:
                    ux, uy = dx/length, dy/length
                    tip = QPointF(cx+ux*edge, cy+uy*edge)
                    arrow_edge = QPainterPath(tip)
                    arrow_edge.lineTo(tip.x()-ux*12-uy*5, tip.y()-uy*12+ux*5)
                    arrow_edge.lineTo(tip.x()-ux*12+uy*5, tip.y()-uy*12-ux*5)
                    arrow_edge.closeSubpath()
                    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#f3c76a')); p.drawPath(arrow_edge)
        arrow = QPainterPath(QPointF(cx,cy-11)); arrow.lineTo(cx-8,cy+8); arrow.lineTo(cx,cy+4); arrow.lineTo(cx+8,cy+8); arrow.closeSubpath()
        p.setBrush(QColor('#76e1bf')); p.setPen(QPen(QColor('#102b29'), 1)); p.drawPath(arrow)
        p.restore()
        p.setPen(QColor('#f3c76a' if active else '#8299a5'))
        name = guidance.get('activeName') if active else None
        distance = guidance.get('distance') if active else None
        footer = str(name)[:22] if isinstance(name, str) else 'PLAYER RELATIVE'
        if type(distance) in (int, float) and math.isfinite(distance) and distance >= 0:
            footer += f'  ·  {distance:.1f} units'
        p.drawText(QRectF(16, 281, 232, 20), Qt.AlignmentFlag.AlignVCenter, footer)
        destination = next((point for point in self.points if point['number'] in active), None)
        if destination:
            context = contexts[destination['number']]
            p.setFont(QFont('Segoe UI', 8))
            p.setPen(QColor('#f3c76a' if context['floorWarning'] else '#96b0bd'))
            p.drawText(QRectF(16, 301, 232, 15), Qt.AlignmentFlag.AlignVCenter,
                       context['label'])
        p.end()
