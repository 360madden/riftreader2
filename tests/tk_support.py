"""Recover one observed transient Tk bootstrap failure; never skip broken checks.

Windows/Python 3.14 combined GUI runs sometimes report missing installed scripts
or tcl_findLibrary during repeated initialization. The underlying native cause is
unqualified. Retry once with a fresh interpreter only for those startup errors
and only when the interpreter's own installed library files are present.
"""
from pathlib import Path
import sys
import tkinter as tk


def reject_error_dialog(title, message, **kwargs):
    """Unexpected fixture errors must not open modal windows on the user's desktop."""
    raise AssertionError(f"Unexpected GUI test error dialog: {title}: {message}")


def _installed_libraries(root):
    library = (Path(root.tk.call("info", "library")) if root is not None else
               Path(sys.base_prefix) / "tcl" / f"tcl{tk.TclVersion}")
    return all(path.is_file() for path in (library / "init.tcl", library / "auto.tcl",
               library.parent / f"tk{tk.TkVersion}" / "tk.tcl"))


def withdrawn_root(factory, *args, **kwargs):
    kwargs["useTk"] = False
    for attempt in range(2):
        root = None
        try:
            root = factory(*args, **kwargs)
            root.loadtk()
            root.withdraw()
            return root
        except BaseException as exc:
            transient = isinstance(exc, tk.TclError) and any(message in str(exc) for message in (
                "Can't find a usable tk.tcl", "Can't find a usable init.tcl",
                'invalid command name "tcl_findLibrary"', "couldn't read file"))
            try:
                retry = attempt == 0 and transient and _installed_libraries(root)
            except (tk.TclError, OSError, TypeError):
                retry = False
            try:
                if root is not None: root.destroy()
            except tk.TclError:
                pass  # Failed Tk bootstrap may not have installed 'destroy'.
            if not retry:
                raise
