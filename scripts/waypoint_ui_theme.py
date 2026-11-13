"""Tk styling shared by the physical waypoint window and its local dialogs."""

PALETTE = {
    "base": "#08131e", "surface": "#101f2c", "inset": "#0a1722", "line": "#23394b",
    "ink": "#edf4f7", "muted": "#a3b5c4", "dim": "#71899c", "mint": "#7fe3c3",
    "gold": "#ffc278", "blue": "#82bdf6", "danger": "#d04457",
}


def summarize_status(text):
    """Shorten a routine path receipt for the header; keep operational reasons intact."""
    for prefix, label in (("Run receipt: ", "Run receipt saved"),
                          ("Recorded route saved: ", "Recorded route saved"), ("Route saved: ", "Route saved"),
                          ("Route loaded: ", "Route loaded"), ("View saved: ", "Snapshot saved"),
                          ("3D view opened: ", "3D view opened")):
        if text.startswith(prefix):
            remainder = text[len(prefix):]
            # Capture and cache results may append a separate failure/status after the path.
            if "; " in remainder or " · " in remainder or " — " in remainder:
                return text
            if remainder.strip():
                return label
    return text


def apply_theme(window):
    """Configure this Tk interpreter's clam widgets before creating the window's controls."""
    from tkinter import ttk

    p = PALETTE
    base, surface, inset, line = (p[k] for k in ("base", "surface", "inset", "line"))
    ink, muted, dim, mint = (p[k] for k in ("ink", "muted", "dim", "mint"))
    body, bold = ("Segoe UI", 10), ("Segoe UI", 10, "bold")
    hover, pressed, selection = "#243d50", "#173043", "#24534f"
    field_border = "#526f83"
    style = ttk.Style(window)
    style.theme_use("clam")
    window.configure(background=base)
    style.configure(".", background=surface, foreground=ink, font=body, bordercolor=line,
                    lightcolor=line, darkcolor=line, focuscolor=mint, focusthickness=1)

    style.configure("TFrame", background=base)
    style.configure("Surface.TFrame", background=surface)
    style.configure("Card.TFrame", background=surface, bordercolor=line, borderwidth=1, relief="solid")
    style.configure("Inset.TFrame", background=inset)
    style.configure("TLabel", background=base, foreground=ink)
    for name, background in (("Base", base), ("Surface", surface), ("Card", surface), ("Inset", inset)):
        style.configure(f"{name}.TLabel", background=background)
        for role in ("Title", "Heading", "Muted", "Micro"):
            style.configure(f"{name}.{role}.TLabel", background=background)
    style.configure("Title.TLabel", background=base, font=("Segoe UI", 21, "bold"))
    style.configure("Brand.TLabel", background=base, font=("Segoe UI", 21, "bold"))
    style.configure("Telemetry.TLabel", background=base, foreground=p["blue"], font=("Consolas", 10))
    style.configure("Heading.TLabel", background=surface, font=("Segoe UI", 12, "bold"))
    style.configure("Gold.TLabel", background=surface, foreground=p["gold"], font=bold)
    style.configure("Eyebrow.TLabel", background=surface, foreground=muted, font=("Segoe UI", 9, "bold"))
    style.configure("Muted.TLabel", background=surface, foreground=muted, font=body)
    style.configure("Micro.TLabel", background=surface, foreground=muted, font=("Segoe UI", 9))
    style.configure("Card.TLabelframe", background=surface, bordercolor=line, borderwidth=1, relief="solid")
    style.configure("Card.TLabelframe.Label", background=surface, foreground=muted, font=bold)

    def button(name, normal, active, down, text, border):
        style.configure(name, font=bold, foreground=text, background=normal, bordercolor=border,
                        lightcolor=normal, darkcolor=normal, borderwidth=1, relief="flat",
                        focuscolor=text, focusthickness=1, padding=(12, 7), anchor="center")
        fills = [("disabled", surface), ("pressed", down), ("active", active)]
        style.map(name, background=fills, lightcolor=fills, darkcolor=fills,
                  foreground=[("disabled", dim)], bordercolor=[("disabled", line), ("focus", mint), ("active", border)])

    for name in ("TButton", "Secondary.TButton"):
        button(name, "#1a3040", hover, pressed, ink, "#415a6b")
    for name in ("Accent.TButton", "Primary.TButton"):
        button(name, mint, "#a2efd7", "#65c9aa", base, mint)
    button("Ghost.TButton", surface, hover, pressed, muted, line)
    button("Danger.TButton", "#a53043", "#b83d50", "#852536", ink, p["danger"])

    for name in ("TEntry", "TCombobox"):
        style.configure(name, foreground=ink, fieldbackground=inset, background=surface, bordercolor=field_border,
                        lightcolor=inset, darkcolor=inset, insertcolor=mint, selectbackground=selection,
                        selectforeground=ink, arrowcolor=muted, padding=(7, 5))
        style.map(name, fieldbackground=[("disabled", surface), ("readonly", inset)],
                  foreground=[("disabled", dim), ("readonly", ink)],
                  bordercolor=[("disabled", line), ("focus", mint), ("active", p["blue"])],
                  lightcolor=[("focus", inset)], darkcolor=[("focus", inset)],
                  arrowcolor=[("disabled", dim), ("active", mint)])
    # The dropdown and activity log are classic Tk children, outside ttk's styles.
    for resource, color in (("background", inset), ("foreground", ink),
                            ("selectBackground", selection), ("selectForeground", ink)):
        window.option_add(f"*TCombobox*Listbox.{resource}", color, "widgetDefault")
        window.option_add(f"*Text.{resource}", color, "widgetDefault")
    for resource, value in (("font", ("Consolas", 10)), ("insertBackground", mint),
                            ("highlightBackground", line), ("highlightColor", mint),
                            ("highlightThickness", 1), ("borderWidth", 0), ("padX", 10), ("padY", 8)):
        window.option_add(f"*Text.{resource}", value, "widgetDefault")

    style.configure("TCheckbutton", background=surface, foreground=muted, font=body, padding=(2, 5),
                    indicatorbackground=inset, indicatorforeground=base, indicatormargin=(0, 0, 6, 0),
                    bordercolor=field_border)
    style.map("TCheckbutton", background=[("active", surface)], foreground=[("disabled", dim), ("active", ink)],
              indicatorbackground=[("disabled", line), ("selected", mint), ("active", hover)],
              bordercolor=[("focus", mint), ("active", p["blue"])])
    style.configure("Treeview", rowheight=32, foreground=ink, background=inset, fieldbackground=inset,
                    bordercolor=line, borderwidth=1, font=body, relief="flat")
    style.map("Treeview", background=[("selected", selection)], foreground=[("selected", ink)],
              bordercolor=[("focus", mint)])
    style.configure("Treeview.Heading", background=surface, foreground=muted, font=bold, bordercolor=line,
                    lightcolor=surface, darkcolor=surface, padding=(8, 6), relief="flat")
    style.map("Treeview.Heading", background=[("active", hover)], foreground=[("active", ink)])

    style.configure("TNotebook", background=base, bordercolor=line, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", font=bold, background=base, foreground=muted, padding=(14, 7),
                    bordercolor=line, lightcolor=base, darkcolor=base)
    style.map("TNotebook.Tab", background=[("selected", surface), ("active", hover)],
              foreground=[("disabled", dim), ("selected", mint), ("active", ink)],
              lightcolor=[("selected", surface)], darkcolor=[("selected", surface)])
    for orientation in ("Vertical", "Horizontal"):
        name = f"{orientation}.TScrollbar"
        style.configure(name, background=field_border, troughcolor=inset, bordercolor=inset, arrowcolor=ink,
                        lightcolor=field_border, darkcolor=field_border, arrowsize=12, gripcount=0, relief="flat")
        style.map(name, background=[("pressed", dim), ("active", dim)])
    style.configure("TSeparator", background=line)
    return p
