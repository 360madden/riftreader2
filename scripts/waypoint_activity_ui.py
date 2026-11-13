"""Compact, read-only Activity view for Joey D's Waypoints.

The diagnostic JSON-lines files remain the source of truth.  This widget only
keeps a bounded, filterable presentation of ``Diagnostics.events()`` and never
deletes or rewrites saved logs.
"""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Any, Callable, Mapping


MAX_DISPLAY_CHARS = 64 * 1024
MAX_EVENTS = 100
MAX_EVENT_DETAILS = 8 * 1024
MAX_SEARCH_CHARS = 200


def _local_time(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return "--:--:--"


def _level_name(value: Any) -> str:
    level = str(value or "INFO").upper()
    return "WARN" if level == "WARNING" else level[:5]


def _summary(entry: Mapping[str, Any]) -> str:
    message = str(entry.get("message") or "Activity")
    if message == "Activity" and entry.get("status"):
        message = str(entry["status"])
    extras = []
    for key in ("command", "operation", "reason", "code", "exceptionType", "exceptionMessage", "requestId"):
        value = entry.get(key)
        if value not in (None, "") and str(value) not in message:
            extras.append(f"{key}: {value}")
    prefix = "[memory only] " if entry.get("persisted") is False else ""
    return prefix + message + (" · " + " · ".join(extras) if extras else "")


def _details(entry: Mapping[str, Any]) -> str:
    fields = {
        str(key): value
        for key, value in entry.items()
        if key not in {"eventId", "timestamp", "level", "message", "status", "threadName", "traceback"}
    }
    traceback_text = str(entry.get("traceback") or "")
    if not fields and not traceback_text:
        return ""
    parts = [json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True)] if fields else []
    if traceback_text:
        parts.append("Traceback:\n" + traceback_text)
    rendered = "\n".join(parts)
    if len(rendered) > MAX_EVENT_DETAILS:
        suffix = "\n... [details truncated in Activity; use CLI diagnostics or available log files]"
        rendered = rendered[: MAX_EVENT_DETAILS - len(suffix)] + suffix
    return rendered


class ActivityControls:
    """Two-row Activity toolbar plus a bounded read-only text display."""

    def __init__(
        self,
        parent: tk.Misc,
        diagnostics: Any,
        *,
        open_logs: Callable[[], Any],
        copy_diagnostics: Callable[[], Any],
        attach_path_tooltip: Callable[[tk.Misc, Callable[[], str]], Any] | None = None,
    ) -> None:
        self.parent = parent
        self.diagnostics = diagnostics
        self._open_logs = open_logs
        self._copy_diagnostics = copy_diagnostics
        self._last_revision: Any = None
        self._last_query: tuple[str, str, bool, int | None] | None = None
        self._last_rendered_event_id: int | None = None
        self._cleared_through: int | None = None
        self._unseen = 0
        self._shown = 0
        self._matched = 0
        self._buffered = 0
        self._setting_scroll = False

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        first = ttk.Frame(parent)
        first.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Button(first, text="Open logs", command=open_logs).pack(side="left", padx=(0, 6))
        ttk.Button(first, text="Copy diagnostics", command=copy_diagnostics, style="Primary.TButton").pack(side="left", padx=(0, 10))
        self.health = tk.StringVar(master=parent, value="Logging active")
        self.health_label = ttk.Label(first, textvariable=self.health, style="Muted.TLabel")
        self.health_label.pack(side="left", fill="x", expand=True)
        if attach_path_tooltip is not None:
            attach_path_tooltip(self.health_label, self._health_detail)
        self.clear_label = tk.StringVar(master=parent, value="Clear view")
        ttk.Button(first, textvariable=self.clear_label, command=self._toggle_clear).pack(side="right")

        second = ttk.Frame(parent)
        second.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Label(second, text="Severity").pack(side="left", padx=(0, 4))
        self.severity = tk.StringVar(master=parent, value="All")
        severity = ttk.Combobox(
            second,
            textvariable=self.severity,
            values=("All", "Warnings + errors", "Errors"),
            state="readonly",
            width=17,
        )
        severity.pack(side="left", padx=(0, 8))
        severity.bind("<<ComboboxSelected>>", lambda _event: self.refresh(force=True))
        ttk.Label(second, text="Find").pack(side="left", padx=(0, 4))
        self.search = tk.StringVar(master=parent)
        validate_search = (parent.register(lambda value: len(value) <= MAX_SEARCH_CHARS), "%P")
        find = ttk.Entry(
            second, textvariable=self.search, width=21, validate="key", validatecommand=validate_search
        )
        find.pack(side="left", fill="x", expand=True, padx=(0, 8))
        find.bind("<Return>", lambda _event: self.refresh(force=True))
        find.bind("<Escape>", self._clear_search)
        self.follow = tk.BooleanVar(master=parent, value=True)
        ttk.Checkbutton(second, text="Follow latest", variable=self.follow, command=self._follow_changed).pack(
            side="left", padx=(0, 8)
        )
        self.show_details = tk.BooleanVar(master=parent, value=False)
        ttk.Checkbutton(second, text="Details", variable=self.show_details, command=lambda: self.refresh(force=True)).pack(
            side="left"
        )

        self.text = tk.Text(
            parent,
            height=5,
            state="disabled",
            font=("Consolas", 10),
            background="#101d26",
            foreground="#d8e6ec",
            insertbackground="#d8e6ec",
            selectbackground="#31566b",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=7,
            wrap="word",
        )
        self.text.grid(row=2, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(parent, command=self._scrollbar_command)
        self.scrollbar.grid(row=2, column=1, sticky="ns")
        self.text.configure(yscrollcommand=lambda first, last: self._scroll_changed(self.scrollbar, first, last))
        self.text.tag_configure("INFO", foreground="#d8e6ec")
        self.text.tag_configure("WARNING", foreground="#f4ca64")
        self.text.tag_configure("ERROR", foreground="#ff8c85")
        self.text.tag_configure("DETAIL", foreground="#8faab7", lmargin1=20, lmargin2=20)
        self.text.tag_configure("NOTICE", foreground="#7fc5c0")
        self.text.bind("<MouseWheel>", self._manual_scroll, add="+")
        self.text.bind("<Button-4>", self._manual_scroll, add="+")
        self.text.bind("<Button-5>", self._manual_scroll, add="+")
        self.text.bind("<Button-1>", self._manual_scroll, add="+")
        self.text.bind("<KeyPress>", self._key_scroll, add="+")

        self.footer = tk.StringVar(master=parent, value="No activity yet.")
        ttk.Label(parent, textvariable=self.footer, style="Muted.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )

    def _level(self) -> str:
        return {"Warnings + errors": "warning", "Errors": "error"}.get(self.severity.get(), "all")

    def _clear_search(self, _event: tk.Event[Any]) -> str:
        self.search.set("")
        self.refresh(force=True)
        return "break"

    def _follow_changed(self) -> None:
        if self.follow.get():
            self._unseen = 0
            self.refresh(force=True)
        else:
            self._update_footer()

    def _manual_scroll(self, _event: tk.Event[Any]) -> None:
        if self.follow.get():
            self.follow.set(False)
            self._update_footer()

    def _key_scroll(self, event: tk.Event[Any]) -> None:
        if event.keysym in {"Up", "Down", "Prior", "Next", "Home", "End"}:
            self._manual_scroll(event)

    def _scrollbar_command(self, *arguments: str) -> None:
        if self.follow.get():
            self.follow.set(False)
            self._update_footer()
        self.text.yview(*arguments)

    def _scroll_changed(self, scrollbar: ttk.Scrollbar, first: str, last: str) -> None:
        scrollbar.set(first, last)

    def _health_detail(self) -> str:
        try:
            status = self.diagnostics.status()
        except Exception:
            return "Diagnostics status unavailable"
        return str(status.get("error") or status.get("logFile") or "Diagnostics status unavailable")

    def _toggle_clear(self) -> None:
        if self._cleared_through is None:
            self.clear_view()
        else:
            self._cleared_through = None
            self.clear_label.set("Clear view")
            self.refresh(force=True)

    def clear_view(self) -> None:
        """Hide current records without mutating the diagnostic store."""
        snapshot = self.diagnostics.events(limit=1, level="all", search="")
        entries = snapshot.get("entries") or []
        self._cleared_through = int(entries[0]["eventId"]) if entries else 0
        self.clear_label.set("Show history")
        self._unseen = 0
        self._last_revision = None
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        level = self._level()
        search = self.search.get().strip()[:MAX_SEARCH_CHARS]
        query = (level, search.casefold(), bool(self.show_details.get()), self._cleared_through)

        try:
            status = self.diagnostics.status()
        except Exception:
            status = {}
        status_revision = status.get("eventRevision")
        available = bool(status.get("available", True))
        self.health.set("Logging active" if available else "Logging unavailable")
        if not force and query == self._last_query and status_revision is not None and status_revision == self._last_revision:
            return

        try:
            result = self.diagnostics.events(limit=MAX_EVENTS, level=level, search=search)
        except ValueError as exc:
            self.health.set("Activity filter unavailable")
            self.footer.set(f"Activity filter was not applied: {exc}")
            return
        entries = list(result.get("entries") or [])
        revision = result.get("revision", status_revision)

        available = bool(result.get("available", available))
        self.health.set("Logging active" if available else "Logging unavailable")
        self._matched = int(result.get("matchedCount", len(entries)))
        self._buffered = int(result.get("totalBuffered", self._matched))

        if not force and query == self._last_query and revision == self._last_revision:
            return
        if not force and query == self._last_query and not self.follow.get() and self._last_revision is not None:
            if self._last_rendered_event_id is not None:
                self._unseen = sum(
                    1 for entry in entries if int(entry.get("eventId", 0)) > self._last_rendered_event_id
                )
            self._last_revision = revision
            self._update_footer()
            return

        visible = [
            entry
            for entry in entries
            if self._cleared_through is None or int(entry.get("eventId", 0)) > self._cleared_through
        ]
        self._render(list(reversed(visible)))
        self._shown = len(visible)
        self._last_revision = revision
        self._last_query = query
        self._last_rendered_event_id = max(
            (int(entry.get("eventId", 0)) for entry in visible), default=self._last_rendered_event_id
        )
        if self.follow.get():
            self._unseen = 0
        self._update_footer()

    def _render(self, chronological: list[Mapping[str, Any]]) -> None:
        old_y = self.text.yview()[0]
        try:
            old_selection = (self.text.index("sel.first"), self.text.index("sel.last"))
        except tk.TclError:
            old_selection = None

        chunks: list[tuple[str, str]] = []
        for entry in chronological:
            level = str(entry.get("level") or "INFO").upper()
            chunks.append((f"{_local_time(entry.get('timestamp'))}  {_level_name(level):<5}  {_summary(entry)}\n", level))
            if self.show_details.get():
                detail = _details(entry)
                if detail:
                    chunks.append((detail + "\n", "DETAIL"))

        omitted = False
        total = sum(len(text) for text, _tag in chunks)
        while chunks and total > MAX_DISPLAY_CHARS:
            text, _tag = chunks.pop(0)
            total -= len(text)
            omitted = True
        notice = "Earlier activity omitted from this bounded view; inspect CLI diagnostics or available saved logs.\n" if omitted else ""
        while chunks and total + len(notice) > MAX_DISPLAY_CHARS:
            text, _tag = chunks.pop(0)
            total -= len(text)

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if self._cleared_through is not None and not chunks:
            self.text.insert(
                "end", "Activity view cleared. Saved logs were not changed; new events will appear here.\n", "NOTICE"
            )
        elif not chunks:
            self.text.insert("end", "No activity matches this view.\n", "NOTICE")
        else:
            if notice:
                self.text.insert("end", notice, "NOTICE")
            for text, tag in chunks:
                self.text.insert("end", text, tag if tag in {"INFO", "WARNING", "ERROR", "DETAIL"} else "INFO")
        self.text.configure(state="disabled")

        self._setting_scroll = True
        try:
            if self.follow.get():
                self.text.see("end")
            else:
                self.text.yview_moveto(old_y)
                if old_selection is not None:
                    try:
                        self.text.tag_add("sel", *old_selection)
                    except tk.TclError:
                        pass
        finally:
            self._setting_scroll = False

    def _update_footer(self) -> None:
        parts = [f"Current session · Showing {self._shown} of {self._matched} matching events", f"{self._buffered} retained"]
        if self._unseen:
            parts.append(f"{self._unseen} new — enable Follow latest to view")
        if self._cleared_through is not None:
            parts.append("view cleared only; saved logs unchanged")
        self.footer.set(" · ".join(parts))

    def view_state(self) -> dict[str, Any]:
        return {
            "severity": self._level(),
            "search": self.search.get().strip(),
            "followLatest": bool(self.follow.get()),
            "details": bool(self.show_details.get()),
            "clearedThroughEventId": self._cleared_through,
            "unseenCount": self._unseen,
            "shownCount": self._shown,
            "matchedCount": self._matched,
            "retainedEvents": self._buffered,
            "eventRevision": self._last_revision,
        }
