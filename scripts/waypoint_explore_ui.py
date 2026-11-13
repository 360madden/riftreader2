"""Read-only exploration controls in the existing Waypoints window."""
import json
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from scripts.waypoint_progress import write_json_atomic


RADAR_DEFAULTS = dict(version=1, enabled=False, unlocked=False, radius=10, opacity=.85)


def write_feedback(path, document):
    """A Windows reader may briefly deny replacement; retry only this display file."""
    for attempt in range(3):
        try:
            write_json_atomic(path, document, durable=False)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(.005)


def radar_settings(path):
    result = dict(RADAR_DEFAULTS)
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        if saved.get("radius") in (2, 5, 10, 20):
            result["radius"] = saved["radius"]
        if type(saved.get("opacity")) in (int, float) and .2 <= saved["opacity"] <= 1:
            result["opacity"] = saved["opacity"]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return result


class ExploreControls:
    def __init__(self, parent, markers, ensure_feed, status, *, get_document=None,
                 get_selected_index=None, get_binding=None, on_navigation=None):
        import tkinter as tk
        from tkinter import ttk
        from scripts.waypoint_manual_guidance import ManualGuidance
        from scripts.waypoint_breadcrumbs import BreadcrumbTrail
        self.parent, self.markers, self.ensure_feed, self.status = parent, markers, ensure_feed, status
        self.get_document = get_document or (lambda: {"waypoints": []})
        self.get_selected_index = get_selected_index or (lambda: None)
        self.get_binding = get_binding
        self.on_navigation = on_navigation
        self.guidance, self.trail = ManualGuidance(), BreadcrumbTrail()
        self.latest_pose = None
        self.last_unavailable_reason = None
        self._pose_caption = "Waiting for live pose"
        self._route_signature = None
        self.path = markers.radar_path
        self.extra_settings = {}
        settings = radar_settings(self.path)
        self.enabled = tk.BooleanVar(master=parent, value=False)
        self.unlocked = tk.BooleanVar(master=parent, value=False)
        self.radius = tk.StringVar(master=parent, value=str(settings["radius"]))
        self.opacity = tk.DoubleVar(master=parent, value=settings["opacity"] * 100)
        self.opacity_text = tk.StringVar(master=parent)
        self.direction = tk.StringVar(master=parent, value="Forward")
        self.start_selected = tk.BooleanVar(master=parent, value=False)
        self.guide_text = tk.StringVar(master=parent, value="Walk manually; guidance sends no input.")
        self.trail_text = tk.StringVar(master=parent, value="Record only observed movement; gaps stay separate.")
        self.segment_choice = tk.StringVar(master=parent)
        self.pending = None
        self._segment_count = 0
        write_json_atomic(self.path, settings)
        for column in range(3):
            parent.columnconfigure(column, weight=1, uniform="explore")
        cards = []
        for column, title in enumerate(("COMPACT RADAR", "MANUAL GUIDE", "BREADCRUMB TRAIL")):
            card = ttk.LabelFrame(parent, text=title, padding=(8, 6), style="Card.TLabelframe")
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 8 if column < 2 else 0))
            card.columnconfigure(0, weight=1)
            cards.append(card)
        radar, guide, trail = cards
        switches = ttk.Frame(radar, style="Surface.TFrame")
        switches.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(switches, text="Show radar", variable=self.enabled, command=self.toggle).pack(side="left")
        ttk.Checkbutton(switches, text="Unlock to move", variable=self.unlocked, command=self.save).pack(side="left", padx=(6, 0))
        range_row = ttk.Frame(radar, style="Surface.TFrame")
        range_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(range_row, text="Range", style="Surface.Micro.TLabel").pack(side="left", padx=(0, 5))
        ranges = ttk.Combobox(range_row, textvariable=self.radius, values=(2, 5, 10, 20), state="readonly", width=3)
        ranges.pack(side="left")
        ranges.bind("<<ComboboxSelected>>", lambda _: self.save())
        ttk.Label(range_row, text="Opacity", style="Surface.Micro.TLabel").pack(side="left", padx=(10, 5))
        ttk.Label(range_row, textvariable=self.opacity_text, width=4, style="Surface.Micro.TLabel").pack(side="left")
        opacity = ttk.Scale(radar, from_=20, to=100, variable=self.opacity, length=160,
                            command=self.changed, style="Beacon.Horizontal.TScale")
        opacity.grid(row=2, column=0, sticky="ew", pady=5)
        ttk.Label(radar, text="Locked: click-through · uses the beacon reader", wraplength=255,
                  style="Surface.Micro.TLabel").grid(row=3, column=0, sticky="w")
        direction_row = ttk.Frame(guide, style="Surface.TFrame")
        direction_row.grid(row=0, column=0, sticky="ew")
        ttk.Combobox(direction_row, textvariable=self.direction, values=("Forward", "Reverse"),
                     state="readonly", width=7).pack(side="left")
        ttk.Checkbutton(direction_row, text="Start at selected", variable=self.start_selected).pack(side="left", padx=(5, 0))
        guide_buttons = ttk.Frame(guide, style="Surface.TFrame")
        guide_buttons.grid(row=1, column=0, sticky="ew", pady=(7, 6))
        self.start_guide_button = ttk.Button(guide_buttons, text="Start guide", command=self.start_guidance, style="Primary.TButton")
        self.start_guide_button.pack(side="left", padx=(0, 6))
        self.stop_guide_button = ttk.Button(guide_buttons, text="Stop guide", command=self.stop_guidance, state="disabled")
        self.stop_guide_button.pack(side="left")
        ttk.Label(guide, textvariable=self.guide_text, wraplength=255,
                  style="Surface.Micro.TLabel").grid(row=2, column=0, sticky="w")
        trail_buttons = ttk.Frame(trail, style="Surface.TFrame")
        trail_buttons.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.record_trail_button = ttk.Button(trail_buttons, text="Record trail", command=self.start_trail)
        self.record_trail_button.pack(side="left", padx=(0, 5))
        self.stop_trail_button = ttk.Button(trail_buttons, text="Stop trail", command=self.stop_trail, state="disabled")
        self.stop_trail_button.pack(side="left", padx=(0, 5))
        self.clear_trail_button = ttk.Button(trail, text="Clear", command=self.clear_trail, style="Ghost.TButton", width=5)
        self.clear_trail_button.grid(row=2, column=1, sticky="ne", padx=(5, 0))
        export_row = ttk.Frame(trail, style="Surface.TFrame")
        export_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 6))
        export_row.columnconfigure(0, weight=1)
        self.segment_dropdown = ttk.Combobox(export_row, textvariable=self.segment_choice, values=(), state="readonly", width=14)
        self.segment_dropdown.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.save_trail_button = ttk.Button(export_row, text="Save segment", command=self.save_trail, state="disabled")
        self.save_trail_button.grid(row=0, column=1)
        ttk.Label(trail, textvariable=self.trail_text, wraplength=180,
                  style="Surface.Micro.TLabel").grid(row=2, column=0, sticky="w")
        self.save()
        self._refresh()

    def changed(self, _=None):
        self.opacity_text.set(f"{round(self.opacity.get())}%")
        if self.pending is not None:
            self.parent.after_cancel(self.pending)
        self.pending = self.parent.after(100, self.save)

    def save(self):
        if self.pending is not None:
            self.parent.after_cancel(self.pending)
            self.pending = None
        self.opacity_text.set(f"{round(self.opacity.get())}%")
        try:
            write_json_atomic(self.path, dict(self.extra_settings, version=1, enabled=self.enabled.get(),
                unlocked=self.unlocked.get(), radius=int(self.radius.get()), opacity=round(self.opacity.get()) / 100))
        except (OSError, ValueError, TypeError) as exc:
            self.status.set("Cannot update radar: " + str(exc))

    def toggle(self):
        self.save()
        if self.enabled.get():
            self.ensure_feed()
            if not self.markers.running():
                self.enabled.set(False)
                self.save()
                return
        self.status.set("Compact radar enabled; unlock to reposition." if self.enabled.get() else "Compact radar hidden.")

    def _owner(self):
        self.ensure_feed()
        if self.latest_pose is None:
            raise ValueError("Waiting for a fresh beacon pose; choose Start again when it is available.")
        try:
            stamp = datetime.fromisoformat(self.latest_pose["sampledAtUtc"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            if not -.1 <= age <= 1.:
                raise ValueError("expired")
        except (ValueError, KeyError, TypeError):
            self.unavailable("live-pose-expired")
            raise ValueError("Wait for a fresh live pose before starting.") from None
        if self.get_binding is not None:
            binding = self.get_binding()
            if binding is None:
                raise ValueError("The owned beacon reader is unavailable.")
            from scripts.waypoint_manual_guidance import _owner
            if _owner(binding) != _owner(self.latest_pose):
                raise ValueError("Player or beacon session changed; wait for a fresh pose.")
        return deepcopy(self.latest_pose)

    def start_guidance(self):
        from scripts.waypoint_height_context import measured_heights
        try:
            document = deepcopy(self.get_document())
            points = document["waypoints"]
            direction = self.direction.get().lower()
            index = self.get_selected_index() if self.start_selected.get() else (0 if direction == "forward" else len(points)-1)
            owner = self._owner()
            self.guidance.begin(points, direction, index, owner, measured_heights=measured_heights(document))
            self._route_signature = json.dumps(document, sort_keys=True, allow_nan=False)
            self.guidance.observe(owner)
            self.status.set("Manual route guidance started; walk using the game controls. No input is sent.")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.status.set("Cannot start manual guide: " + str(exc))
        self._refresh()
        self._notify()

    def stop_guidance(self):
        self.guidance.stop("user-stopped")
        self._refresh()
        self._notify()

    def start_trail(self):
        try:
            packet = self._owner()
            self.trail.start(packet)
            self.trail.observe(packet)
            self.status.set("Recording observed breadcrumb trail; no movement is sent.")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.status.set("Cannot record trail: " + str(exc))
        self._refresh()
        self._notify()

    def stop_trail(self):
        self.trail.stop()
        self._refresh()
        self._notify()

    def clear_trail(self):
        if self.trail.snapshot()["active"]:
            return
        self.trail.clear()
        self._refresh()
        self._notify()

    def save_trail(self):
        from tkinter import filedialog, messagebox
        try:
            index = self.segment_dropdown.current()
            if index < 0:
                raise ValueError("Choose a recorded segment to save.")
            document = self.trail.export_segment(index)
            path = filedialog.asksaveasfilename(parent=self.parent.winfo_toplevel(), defaultextension=".json",
                initialfile=f"breadcrumb-segment-{index+1}.json", title="Save observed trail segment",
                filetypes=[("Waypoint route", "*.json")])
            if path:
                write_json_atomic(path, document)
                self.status.set("Trail segment saved separately: " + str(path))
        except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
            messagebox.showerror("Cannot save trail segment", str(exc), parent=self.parent.winfo_toplevel())

    def on_pose(self, packet):
        if packet.get("status") != "fresh":
            self.unavailable("pose-not-fresh")
            return
        self.latest_pose = deepcopy(packet)
        self._pose_caption = None
        self.route_changed()
        self.guidance.observe(packet)
        self.trail.observe(packet)
        self._refresh()
        self._notify()

    def unavailable(self, reason):
        self.latest_pose = None
        self.last_unavailable_reason = str(reason)
        text = self.last_unavailable_reason.casefold()
        self._pose_caption = ("Waiting for live pose" if any(term in text for term in
                              ("no such file", "cannot find", "waiting", "reader ended")) else "Live pose unavailable")
        self.guidance.unavailable(reason)
        self.trail.unavailable(reason)
        self._refresh()
        self._notify()

    def route_changed(self, document=None):
        try:
            signature = json.dumps(self.get_document() if document is None else document, sort_keys=True, allow_nan=False)
        except (ValueError, KeyError, TypeError):
            signature = None
        if self._route_signature is not None and signature != self._route_signature:
            self.guidance.stop("route-changed")
            self._route_signature = signature
            self._refresh()
            self._notify()

    def navigation_state(self):
        return self.guidance.as_dict()

    def set_on_navigation(self, callback):
        self.on_navigation = callback

    def _notify(self):
        if self.on_navigation is not None:
            try:
                self.on_navigation(self.navigation_state(), [s["points"] for s in self.trail.snapshot()["segments"]])
            except (OSError, ValueError, TypeError) as exc:
                self.status.set("Cannot update exploration display: " + str(exc))

    def _refresh(self):
        state = self.guidance.as_dict()
        active = state["status"] in ("active", "unavailable")
        self.stop_guide_button.configure(state="normal" if active else "disabled")
        name = " ".join((state["activeName"] or "Next waypoint").split())
        name = name if len(name) <= 42 else name[:39] + "…"
        distance = (self._pose_caption or "Waiting for live pose") if state["distance"] is None else f"{state['distance']:.2f} units"
        if state["status"] == "complete":
            text = f"Route complete · {len(state['completedIndices'])} points confirmed."
        elif active:
            text = f"{name}\n{distance}"
            if state.get('heightWarning'):
                text += f" · possible other floor ({state['heightSeparation']:+.1f}u)"
        else:
            text = "Manual guide stopped" + (" · route changed" if state["reason"] == "route-changed" else "; no input sent.")
        self.guide_text.set(text)
        trail = self.trail.snapshot()
        count = len(trail["segments"])
        labels = [f"Segment {i+1} · {len(s['points'])} pts" for i,s in enumerate(trail["segments"])]
        selected = self.segment_dropdown.current()
        self.segment_dropdown.configure(values=labels)
        if count and (count != self._segment_count or selected < 0):
            self.segment_dropdown.current(count-1)
        elif count and selected >= 0:
            self.segment_dropdown.current(min(selected, count-1))
        else:
            self.segment_choice.set("")
        self._segment_count = count
        self.clear_trail_button.configure(state="disabled" if trail["active"] else "normal")
        self.stop_trail_button.configure(state="normal" if trail["active"] else "disabled")
        self.record_trail_button.configure(state="disabled" if trail["active"] else "normal")
        self.save_trail_button.configure(state="normal" if count else "disabled")
        label = "Recording" if trail["active"] else "Stopped"
        caption = "\n" + self._pose_caption if trail["active"] and self._pose_caption else ""
        self.trail_text.set(f"{label} · {trail['pointCount']} samples · {count} segments" + caption)

    def shutdown(self):
        self.guidance.stop("window-closing")
        self.trail.stop()
        self.latest_pose = None
        self.enabled.set(False)
        self.unlocked.set(False)
        self.save()
        self._refresh()
        self._notify()
