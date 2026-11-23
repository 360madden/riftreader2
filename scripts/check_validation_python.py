"""Check host test imports without starting a window or a live backend."""

import importlib
import sys


def main():
    failures = []
    for module in ("lupa.lua51", "numpy", "PIL.Image", "PySide6.QtWidgets", "pytest", "vncdotool.api"):
        try:
            importlib.import_module(module)
        except (ImportError, OSError) as error:
            failures.append(f"{module}: {error}")

    try:
        import tkinter

        tkinter.Tcl()
    except Exception as error:
        failures.append(f"tkinter/Tcl: {error}")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
