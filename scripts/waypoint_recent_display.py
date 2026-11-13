"""Readable recent-route labels; full paths remain the loading authority."""
from collections import Counter
from pathlib import PureWindowsPath


def route_labels(paths):
    names = [PureWindowsPath(path).name for path in paths]
    counts = Counter(name.casefold() for name in names)
    labels = []
    for path, name in zip(paths, names):
        label = name if counts[name.casefold()] == 1 else f"{name} — {PureWindowsPath(path).parent.name}"
        candidate, suffix = label, 2
        while candidate.casefold() in {old.casefold() for old in labels}:
            candidate = f"{label} ({suffix})"
            suffix += 1
        labels.append(candidate)
    return labels


def attach_path_tooltip(widget, get_path):
    import tkinter as tk
    from scripts.waypoint_ui_theme import PALETTE
    popup = timer = None

    def hide(_=None):
        nonlocal popup, timer
        if timer is not None:
            widget.after_cancel(timer)
            timer = None
        if popup is not None:
            popup.destroy()
            popup = None

    def show():
        nonlocal popup, timer
        timer = None
        path = get_path()
        if not path or not widget.winfo_exists():
            return
        popup = tk.Toplevel(widget)
        popup.withdraw()
        popup.overrideredirect(True)
        label = tk.Label(popup, text=path, background=PALETTE['surface'], foreground=PALETTE['ink'],
                         font=('Segoe UI', 10), padx=10, pady=7, relief='solid', borderwidth=1,
                         wraplength=min(760, widget.winfo_screenwidth()-40), justify='left')
        label.pack()
        popup.update_idletasks()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty()+widget.winfo_height()+6
        popup.geometry(f'{x:+d}{y:+d}')
        popup.deiconify()

    def schedule(_):
        nonlocal timer
        hide()
        timer = widget.after(500, show)

    widget.bind('<Enter>', schedule, add='+')
    for event in ('<Leave>', '<ButtonPress>', '<KeyPress>', '<<ComboboxSelected>>', '<Destroy>'):
        widget.bind(event, hide, add='+')
