"""Read-only exploration controls in the existing Waypoints window."""
import json
import math
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
        position = saved.get("position")
        if (isinstance(position, dict) and type(position.get("x")) is int
                and type(position.get("y")) is int
                and -100000 <= position["x"] <= 100000
                and -100000 <= position["y"] <= 100000):
            result["position"] = dict(x=position["x"], y=position["y"], revision="restored")
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return result


class ExploreControls:
    def __init__(self, parent, markers, ensure_feed, status, *, get_document=None,
                 get_selected_index=None, get_binding=None, get_block_reason=None,
                 on_navigation=None, on_error=None):
        import tkinter as tk
        from tkinter import ttk
        from scripts.waypoint_manual_guidance import ManualGuidance
        from scripts.waypoint_breadcrumbs import BreadcrumbTrail
        self.parent, self.markers, self.ensure_feed, self.status = parent, markers, ensure_feed, status
        self.get_document = get_document or (lambda: {"waypoints": []})
        self.get_selected_index = get_selected_index or (lambda: None)
        self.get_binding = get_binding
        self.get_block_reason = get_block_reason
        self.on_navigation = on_navigation
        self.on_error = on_error
        self.guidance, self.trail = ManualGuidance(), BreadcrumbTrail()
        self.latest_pose = None
        self.last_unavailable_reason = None
        self._pose_caption = "Waiting for live pose"
        self._route_signature = None
        self.path = markers.radar_path
        settings = radar_settings(self.path)
        self.extra_settings = ({"position": settings["position"]} if settings.get("position") else {})
        self.enabled = tk.BooleanVar(master=parent, value=False)
        self.unlocked = tk.BooleanVar(master=parent, value=False)
        self.radius = tk.StringVar(master=parent, value=str(settings["radius"]))
        self.opacity = tk.DoubleVar(master=parent, value=settings["opacity"] * 100)
        self.opacity_text = tk.StringVar(master=parent)
        self.direction = tk.StringVar(master=parent, value="Forward")
        self.start_selected = tk.BooleanVar(master=parent, value=False)
        self.arrival_radius = tk.StringVar(master=parent, value="0.60")
        self.guide_text = tk.StringVar(master=parent, value="Walk manually; guidance sends no input.")
        self.trail_text = tk.StringVar(master=parent, value="Record only observed movement; gaps stay separate.")
        self.radar_text = tk.StringVar(master=parent, value="Radar hidden · uses the beacon reader")
        self.segment_choice = tk.StringVar(master=parent)
        self.pending = None
        self._segment_count = 0
        self._saved_enabled = False
        write_json_atomic(self.path, dict(settings, enabled=False, unlocked=False))
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
        radar_footer = ttk.Frame(radar, style="Surface.TFrame")
        radar_footer.grid(row=3, column=0, sticky="ew")
        ttk.Label(radar_footer, textvariable=self.radar_text, wraplength=185,
                  style="Surface.Micro.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(radar_footer, text="Recenter", command=self.reset_position,
                   style="Ghost.TButton", width=9).pack(side="right", padx=(5, 0))
        direction_row = ttk.Frame(guide, style="Surface.TFrame")
        direction_row.grid(row=0, column=0, sticky="ew")
        self.direction_dropdown = ttk.Combobox(direction_row, textvariable=self.direction,
            values=("Forward", "Reverse"), state="readonly", width=7)
        self.direction_dropdown.pack(side="left")
        self.start_selected_button = ttk.Checkbutton(direction_row, text="From selected",
            variable=self.start_selected, command=self.refresh_context)
        self.start_selected_button.pack(side="left", padx=(5, 0))
        ttk.Label(direction_row, text="Arrive", style="Surface.Micro.TLabel").pack(side="left", padx=(6, 2))
        self.arrival_entry = ttk.Entry(direction_row, textvariable=self.arrival_radius, width=4)
        self.arrival_entry.pack(side="left")
        self.arrival_entry.bind("<FocusOut>", lambda _event: self.refresh_context())
        self.arrival_entry.bind("<Return>", lambda _event: self.start_guidance())
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
        self.segment_dropdown.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
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
            self._saved_enabled = self.enabled.get()
            return True
        except (OSError, ValueError, TypeError) as exc:
            if self.on_error is not None:
                self.on_error("Unable to save compact radar settings", exc)
            self.status.set("Cannot update radar: " + str(exc))
            return False

    def reset_position(self, *, revision=None):
        previous = self.extra_settings.get("position")
        self.extra_settings["position"] = dict(
            reset=True, revision=revision or f"reset-{time.monotonic_ns()}")
        if not self.save():
            if previous is None:
                self.extra_settings.pop("position", None)
            else:
                self.extra_settings["position"] = previous
            return False
        self.status.set("Radar position reset to its default corner.")
        return True

    def set_radar_observed(self, observed):
        if not self.enabled.get():
            text = "Radar hidden · uses the beacon reader"
        elif not isinstance(observed, dict):
            text = "Radar requested · waiting for display"
        elif not observed.get("visible"):
            text = "Radar hidden by presenter"
        else:
            text = "Radar visible · " + ("drag to move" if observed.get("unlocked") else "click-through")
        self.radar_text.set(text)
        if (not isinstance(observed, dict) or not observed.get("visible")
                or not observed.get("unlocked") or observed.get("dragging") is not False):
            return False
        position = observed.get("position")
        if (not isinstance(position, dict) or type(position.get("x")) is not int
                or type(position.get("y")) is not int):
            return False
        requested = self.extra_settings.get("position")
        if (isinstance(requested, dict) and observed.get("appliedRevision") != requested.get("revision")):
            return False
        if (isinstance(requested, dict) and not requested.get("reset")
                and requested.get("x") == position["x"] and requested.get("y") == position["y"]):
            return False
        revision = (observed.get("appliedRevision")
                    or f"drag-{time.monotonic_ns()}")
        previous = requested
        self.extra_settings["position"] = dict(x=position["x"], y=position["y"], revision=revision)
        if self.save():
            return True
        if previous is None:
            self.extra_settings.pop("position", None)
        else:
            self.extra_settings["position"] = previous
        return False

    def toggle(self):
        requested = self.enabled.get()
        if not self.save():
            self.enabled.set(self._saved_enabled)
            return False
        if self.enabled.get():
            self.ensure_feed()
            if not self.markers.running():
                self.enabled.set(False)
                self.save()
                return False
        self.status.set("Compact radar enabled; unlock to reposition." if self.enabled.get() else "Compact radar hidden.")
        return self.enabled.get() == requested

    def _block_reason(self, operation):
        if self.get_block_reason is None:
            return None
        try:
            return self.get_block_reason(operation)
        except TypeError:
            return self.get_block_reason()

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

    def _guide_readiness(self, *, direction=None, start_index=None, radius=None):
        state = self.guidance.as_dict()
        if state["status"] in ("active", "unavailable"):
            return dict(ready=False, reason="Stop the current guide before starting another.")
        try:
            document = self.get_document()
            points = document["waypoints"]
            if not isinstance(points, list) or not points:
                raise ValueError("Load or add at least one waypoint.")
            chosen_direction = (direction or self.direction.get()).lower()
            if chosen_direction not in ("forward", "reverse"):
                raise ValueError("Choose Forward or Reverse.")
            configured_radius = float(self.arrival_radius.get() if radius is None else radius)
            if not math.isfinite(configured_radius) or not .05 <= configured_radius <= 10:
                raise ValueError("Arrival radius must be 0.05 to 10 units.")
            chosen_index = start_index
            if chosen_index is None:
                chosen_index = (self.get_selected_index() if self.start_selected.get()
                                else 0 if chosen_direction == "forward" else len(points)-1)
            if type(chosen_index) is not int or not 0 <= chosen_index < len(points):
                raise ValueError("Select a route point or turn off Start at selected.")
            for row in points:
                if (not isinstance(row, (list, tuple)) or len(row) != 3
                        or not isinstance(row[0], str)
                        or any(type(value) not in (int, float) or not math.isfinite(value) for value in row[1:])):
                    raise ValueError("Guidance points require a name and finite X/Z coordinates.")
            from scripts.waypoint_height_context import measured_heights
            heights = measured_heights(document)
            if len(heights) != len(points) or any(
                    value is not None and (type(value) not in (int, float) or not math.isfinite(value))
                    for value in heights):
                raise ValueError("Guidance height evidence does not match the route.")
            reason = self._block_reason("guide")
            if reason:
                raise ValueError(str(reason))
            return dict(ready=True, reason=None, direction=chosen_direction,
                        startIndex=chosen_index, radius=configured_radius, pointCount=len(points))
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
            return dict(ready=False, reason=str(exc))

    def validate_guidance(self, *, direction=None, start_index=None, radius=None):
        """Validate a GUI or CLI start without starting the reader or mutating guidance."""
        readiness = self._guide_readiness(direction=direction, start_index=start_index, radius=radius)
        if not readiness["ready"]:
            raise ValueError(readiness["reason"])
        return readiness

    def start_guidance(self, *, direction=None, start_index=None, radius=None, raise_errors=False):
        from scripts.waypoint_height_context import measured_heights
        try:
            readiness = self.validate_guidance(direction=direction, start_index=start_index, radius=radius)
            document = deepcopy(self.get_document())
            points = document["waypoints"]
            owner = self._owner()
            old_radius = self.guidance.radius
            self.guidance.radius = readiness["radius"]
            try:
                self.guidance.begin(points, readiness["direction"], readiness["startIndex"], owner,
                                    measured_heights=measured_heights(document))
            except Exception:
                self.guidance.radius = old_radius
                raise
            self.direction.set(readiness["direction"].title())
            self.arrival_radius.set(f"{readiness['radius']:.2f}")
            self._route_signature = json.dumps(document, sort_keys=True, allow_nan=False)
            self.guidance.observe(owner)
            self.status.set("Manual route guidance started; walk using the game controls. No input is sent.")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            if self.on_error is not None:
                self.on_error("Unable to start manual guidance", exc)
            self.status.set("Cannot start manual guide: " + str(exc))
            if raise_errors:
                self._refresh()
                self._notify()
                raise
        self._refresh()
        self._notify()
        return self.navigation_state()

    def stop_guidance(self):
        self.guidance.stop("user-stopped")
        self._refresh()
        self._notify()

    def start_trail(self):
        try:
            reason = self._block_reason("trail")
            if reason:
                raise ValueError(str(reason))
            packet = self._owner()
            self.trail.start(packet)
            self.trail.observe(packet)
            self.status.set("Recording observed breadcrumb trail; no movement is sent.")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            if self.on_error is not None:
                self.on_error("Unable to start breadcrumb trail", exc)
            self.status.set("Cannot record trail: " + str(exc))
        self._refresh()
        self._notify()

    def stop_trail(self):
        self.trail.stop()
        self.status.set("Breadcrumb trail stopped; retained segments are ready to review.")
        self._refresh()
        self._notify()

    def clear_trail(self, *, discard=False):
        from tkinter import messagebox
        snapshot = self.trail.snapshot()
        if snapshot["active"]:
            return False
        if snapshot["pointCount"] and not discard and not messagebox.askyesno(
                "Clear breadcrumb trail?",
                f"Discard {snapshot['pointCount']} retained samples across {len(snapshot['segments'])} segments?",
                parent=self.parent.winfo_toplevel()):
            return False
        self.trail.clear()
        self.status.set("Breadcrumb trail cleared.")
        self._refresh()
        self._notify()
        return True

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
            if self.on_error is not None:
                self.on_error("Unable to save breadcrumb segment", exc)
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
        state = self.guidance.as_dict()
        readiness = self._guide_readiness()
        state["configuredRadius"] = readiness.get("radius", self.guidance.radius)
        state["readiness"] = dict(ready=readiness["ready"], reason=readiness.get("reason"))
        return state

    def refresh_context(self):
        self._refresh()
        return self.navigation_state()

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
        readiness = self._guide_readiness()
        self.start_guide_button.configure(state="disabled" if active or not readiness["ready"] else "normal")
        self.stop_guide_button.configure(state="normal" if active else "disabled")
        self.direction_dropdown.configure(state="disabled" if active else "readonly")
        self.start_selected_button.configure(state="disabled" if active else "normal")
        self.arrival_entry.configure(state="disabled" if active else "normal")
        name = " ".join((state["activeName"] or "Next waypoint").split())
        name = name if len(name) <= 30 else name[:27] + "…"
        distance = (self._pose_caption or "Waiting for live pose") if state["distance"] is None else f"{state['distance']:.2f} units"
        if state["status"] == "complete":
            text = f"Route complete · {len(state['completedIndices'])} points confirmed."
        elif active:
            progress = (state["order"].index(state["activeIndex"]) + 1
                        if state["activeIndex"] in state["order"] else len(state["completedIndices"]) + 1)
            text = f"Next {progress}/{len(state['order'])} · {name}\n{distance} · {len(state['completedIndices'])} confirmed"
            if state.get('heightWarning'):
                text += f" · possible other floor ({state['heightSeparation']:+.1f}u)"
        else:
            if readiness["ready"]:
                text = f"Ready · {readiness['pointCount']} points · {readiness['radius']:.2f}u arrival"
            else:
                reason = " ".join((readiness.get("reason") or "Guide unavailable").split())
                text = reason if len(reason) <= 70 else reason[:67] + "…"
            if state["reason"] == "route-changed":
                text += " · route changed"
        self.guide_text.set(text)
        trail = self.trail.snapshot()
        summaries = self.trail.segment_summaries()
        count = len(summaries)
        labels = [f"Segment {s['number']} · {s['pointCount']} pts" for s in summaries]
        selected = self.segment_dropdown.current()
        self.segment_dropdown.configure(values=labels)
        if count and selected < 0:
            self.segment_dropdown.current(count-1)
        elif count and selected >= 0:
            self.segment_dropdown.current(min(selected, count-1))
        else:
            self.segment_choice.set("")
        self._segment_count = count
        self.clear_trail_button.configure(state="normal" if trail["pointCount"] and not trail["active"] else "disabled")
        self.stop_trail_button.configure(state="normal" if trail["active"] else "disabled")
        trail_blocked = bool(self._block_reason("trail"))
        self.record_trail_button.configure(state="disabled" if trail["active"] or trail_blocked else "normal")
        selected = self.segment_dropdown.current()
        summary = summaries[selected] if 0 <= selected < count else None
        self.save_trail_button.configure(state="normal" if summary and summary["exportable"] else "disabled")
        label = "Recording" if trail["active"] else "Stopped"
        caption = "\n" + self._pose_caption if trail["active"] and self._pose_caption else ""
        retained = f"{label} · {trail['pointCount']} pts · {count} seg"
        if trail["discardedPointCount"]:
            retained += f" · {trail['discardedPointCount']} old dropped"
        if summary is not None:
            if summary["exportable"]:
                detail = (f"Segment {summary['number']} · {summary['observedPathLength']:.1f}u · "
                          f"{summary['waypointCount']} saved points")
            else:
                reason = " ".join((summary["exportReason"] or "Not ready to save").split())
                detail = ("No movement yet" if "no useful movement" in reason.casefold()
                          else reason if len(reason) <= 34 else reason[:31] + "…")
            caption += "\n" + detail
        self.trail_text.set(retained + caption)

    def shutdown(self):
        self.guidance.stop("window-closing")
        self.trail.stop()
        self.latest_pose = None
        self.enabled.set(False)
        self.unlocked.set(False)
        self.save()
        self._refresh()
        self._notify()
