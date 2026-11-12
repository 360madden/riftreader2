"""Player-oriented waypoint preview math and a small Tk canvas renderer."""
from dataclasses import dataclass
import math


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


def draw_route(canvas, view, points, selected, *, completed=None, active=None):
    """Draw only; dots/lines do not imply terrain or obstacle knowledge."""
    canvas.delete("all")
    if view is None:
        canvas.create_text(canvas.winfo_width()/2, canvas.winfo_height()/2,
                           text="Refresh position to show waypoints", fill="#b2bec9")
        return
    cx, cy = view.width/2, view.height/2
    for distance in (5, 10):
        radius = view.scale * distance
        canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius,
                           outline="#354957", dash=(3, 4))
        canvas.create_text(cx+radius-10, cy+10, text=str(distance), fill="#8b9da9")
    canvas.create_line(cx, 18, cx, view.height-18, fill="#253843")
    canvas.create_line(18, cy, view.width-18, cy, fill="#253843")
    canvas.create_text(cx, 13, text="FORWARD", fill="#b2bec9", font=("Segoe UI", 9))
    prior = (cx, cy)
    for index, (identifier, label, x, z) in enumerate(points, 1):
        point = view.world_to_canvas(float(x), float(z))
        if index > 1 or not completed:
            canvas.create_line(*prior, *point, fill="#63b3ed", width=2, dash=(4, 3))
        playback = completed is not None or active is not None
        if playback:
            color = ("#ffb454" if identifier == active else
                     "#719c88" if identifier in (completed or ()) else "#63b3ed")
            outline = "#ffffff" if identifier in selected else "#101c25"
        else:
            color = "#ffb454" if identifier in selected else "#63b3ed"
            outline = "#101c25"
        canvas.create_oval(point[0]-6, point[1]-6, point[0]+6, point[1]+6,
                           fill=color, outline=outline, width=2)
        canvas.create_text(point[0]+10, point[1]-9, text=str(index),
                           anchor="sw", fill=color, font=("Segoe UI", 9))
        prior = point
    canvas.create_polygon(cx, cy-10, cx-7, cy+7, cx+7, cy+7,
                          fill="#3bd6a5", outline="#e1fff4")
    canvas.create_text(cx, cy+21, text="Player", fill="#3bd6a5", font=("Segoe UI", 9))
