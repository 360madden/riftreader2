"""Player-oriented waypoint preview math and a small Tk canvas renderer."""
from dataclasses import dataclass
import math

from scripts.waypoint_ui_theme import PALETTE

ZOOM_RADII = (2, 5, 10, 20)


def fit_route_radius(x, z, points):
    """Fit (name, X, Z) points around the player with 10% radial headroom.

    Empty routes use radius 2. Radius is capped at 20, so farther points can
    remain offscreen; this preview does not change movement limits.
    """
    x, z = float(x), float(z)
    if not math.isfinite(x) or not math.isfinite(z):
        raise ValueError("Preview origin must be finite")
    farthest = 0.0
    for _, px, pz in points:
        px, pz = float(px), float(pz)
        if not math.isfinite(px) or not math.isfinite(pz):
            raise ValueError("Preview points must be finite")
        farthest = max(farthest, math.hypot(px - x, pz - z))
    required = farthest * 1.1
    return next((radius for radius in ZOOM_RADII if radius >= required), ZOOM_RADII[-1])


@dataclass(frozen=True)
class LocalMap:
    x: float
    z: float
    bearing: float
    width: float
    height: float
    radius: float = 10.0

    @property
    def scale(self):
        return max(1, min(self.width, self.height) / 2 - 26) / self.radius

    def world_to_canvas(self, x, z):
        angle = math.radians(self.bearing)
        dx, dz = x - self.x, z - self.z
        right = -dx * math.cos(angle) + dz * math.sin(angle)
        forward = dx * math.sin(angle) + dz * math.cos(angle)
        return self.width / 2 + right * self.scale, self.height / 2 - forward * self.scale

    def canvas_to_world(self, x, y):
        angle = math.radians(self.bearing)
        right = (x - self.width / 2) / self.scale
        forward = (self.height / 2 - y) / self.scale
        return (self.x - right * math.cos(angle) + forward * math.sin(angle),
                self.z + right * math.sin(angle) + forward * math.cos(angle))


def route_length(x, z, points):
    length = 0.0
    for _, px, pz in points:
        px, pz = float(px), float(pz)
        length += math.hypot(px - x, pz - z)
        x, z = px, pz
    return length


def _clip_segment(a, b, bounds):
    """Clip only displayed connector pixels; world points are never clamped."""
    x, y = a
    dx, dy = b[0] - x, b[1] - y
    start, end = 0., 1.
    for direction, distance in ((-dx, x-bounds[0]), (dx, bounds[2]-x),
                                (-dy, y-bounds[1]), (dy, bounds[3]-y)):
        if direction == 0:
            if distance < 0:
                return None
        elif direction < 0:
            start = max(start, distance / direction)
        else:
            end = min(end, distance / direction)
        if start > end:
            return None
    return x+start*dx, y+start*dy, x+end*dx, y+end*dy


def _label_box(point, number, bounds, occupied):
    width, height = max(22, 8 * len(str(number)) + 10), 22
    px, py = point
    candidates = []
    for radius in (20, 40, 62, 86, 112):
        for dx, dy in ((1, -1), (-1, -1), (1, 1), (-1, 1), (0, -1), (0, 1), (1, 0), (-1, 0)):
            x = max(bounds[0], min(bounds[2]-width, px + dx*radius - width/2))
            y = max(bounds[1], min(bounds[3]-height, py + dy*radius - height/2))
            box = (x, y, x+width, y+height)
            overlap = sum(max(0, min(box[2]+3, b[2])-max(box[0]-3, b[0])) *
                          max(0, min(box[3]+3, b[3])-max(box[1]-3, b[1])) for b in occupied)
            candidates.append((overlap, math.hypot(x+width/2-px, y+height/2-py), box))
            if overlap == 0:
                return box
    return min(candidates, key=lambda c: (c[0], c[1]))[2]


def draw_route(canvas, view, points, selected, *, completed=None, active=None):
    """Player-relative reference diagram only; no terrain or clearance imagery."""
    canvas.delete("all")
    c = PALETTE
    if view is None:
        canvas.create_text(canvas.winfo_width()/2, canvas.winfo_height()/2,
                           text="Refresh position to show waypoints", fill=c["muted"], font=("Segoe UI", 10))
        return
    cx, cy = view.width/2, view.height/2
    bounds = (12, 12, view.width-12, view.height-12)
    canvas.create_rectangle(*bounds, fill=c["inset"], outline=c["line"], width=1, tags="map-inset")
    radius = view.scale * view.radius
    for fraction in (.25, .5, .75, 1.):
        r = radius*fraction
        canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=c["line"] if fraction in (.5, 1.) else c["surface"],
                           width=1, tags="range-ring")
    for dx, dy in ((radius, 0), (0, radius)):
        canvas.create_line(cx-dx, cy-dy, cx+dx, cy+dy, fill=c["line"], dash=(2, 6), tags="radar-axis")
    for distance in (view.radius/2, view.radius):
        r = view.scale*distance
        canvas.create_text(cx+r-7, cy+12, text=f"{distance:g}", fill=c["dim"],
                           font=("Segoe UI", 10), anchor="e", tags="range-label")
    canvas.create_text(cx, 20, text="FORWARD", fill=c["muted"], font=("Segoe UI", 10), tags="heading")
    angle = math.radians(view.bearing)
    nx, ny = cx+math.sin(angle)*(radius-12), cy-math.cos(angle)*(radius-12)
    if abs(nx-cx) < 36 and ny < 48:
        nx += 40  # Keep the world-axis tag apart from the forward heading.
    canvas.create_text(nx, ny, text="+Z", fill=c["dim"], font=("Segoe UI", 10), tags="world-axis")
    visible = []
    prior = (cx, cy)
    for number, (identifier, label, x, z) in enumerate(points, 1):
        point = view.world_to_canvas(float(x), float(z))
        segment = _clip_segment(prior, point, bounds)
        if segment is not None and (number > 1 or not completed):
            canvas.create_line(*segment, fill=c["surface"], width=5, tags="route-shadow")
            canvas.create_line(*segment, fill=c["blue"], width=2,
                               dash=(3, 5) if number == 1 else (), tags="route-connector")
        if bounds[0]+7 <= point[0] <= bounds[2]-7 and bounds[1]+7 <= point[1] <= bounds[3]-7:
            color = (c["gold"] if identifier == active else c["mint"] if identifier in (completed or ())
                     else c["gold"] if identifier in selected else c["blue"])
            visible.append((number, identifier, point, color))
        prior = point
    # Reserve every true node and the player, then find quiet nearby number lanes.
    occupied = [(cx-20, cy-20, cx+20, cy+37)]
    occupied += [(p[0]-8, p[1]-8, p[0]+8, p[1]+8) for _, _, p, _ in visible]
    occupied += [(cx-42, 12, cx+42, 32)]
    for number, identifier, point, color in visible:
        box = _label_box(point, number, (16, 36, view.width-16, view.height-16), occupied)
        occupied.append(box)
        endpoint = (max(box[0], min(box[2], point[0])), max(box[1], min(box[3], point[1])))
        canvas.create_line(*point, *endpoint, fill=c["line"], width=1, tags="number-leader")
        canvas.create_rectangle(*box, fill=c["surface"], outline=c["gold"] if identifier in selected else c["line"],
                                width=1, tags="number-badge")
        canvas.create_text((box[0]+box[2])/2, (box[1]+box[3])/2, text=str(number), fill=color,
                           font=("Segoe UI", 10, "bold"), tags="waypoint-number")
    for number, identifier, (x, y), color in visible:
        if identifier in selected or identifier == active:
            canvas.create_oval(x-10, y-10, x+10, y+10, outline=c["gold"], width=1, tags="selection-ring")
        canvas.create_oval(x-5, y-5, x+5, y+5, fill=color, outline=c["inset"], width=2, tags="waypoint-node")
    canvas.create_oval(cx-16, cy-16, cx+16, cy+16, fill=c["surface"], outline=c["line"], tags="player-halo")
    canvas.create_polygon(cx, cy-11, cx-8, cy+8, cx, cy+4, cx+8, cy+8,
                          fill=c["mint"], outline=c["ink"], width=1, tags="player-arrow")
    canvas.create_text(cx, cy+26, text="YOU", fill=c["mint"], font=("Segoe UI", 10), tags="player-label")
