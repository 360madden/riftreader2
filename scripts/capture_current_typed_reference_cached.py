"""Compatibility entry point for current RR2R1 typed-reference capture.

The former cached-reader route targeted the legacy producer and is no longer
executable. This wrapper requires an exact RR2R1 reader session plus a reviewed
RiftReader2.Live binary and forwards to the current staged capture. It sends no
game input and does not reload or restart RIFT.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def capture(lab: str = "lab1", *, session_id: str | None = None,
            reader: Path | None = None, reader_sha256: str | None = None) -> dict:
    if session_id is None:
        raise ValueError("rr2-reference-session-id-required;legacy-cached-capture-removed")
    if reader is None or reader_sha256 is None:
        raise ValueError(
            "rr2-reference-requires-reviewed-reader-and-sha256;legacy-cached-reader-removed")
    from scripts.capture_current_typed_reference import capture as staged_capture
    return staged_capture(lab, reader, reader_sha256, session_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--reader", type=Path, required=True)
    parser.add_argument("--reader-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = capture(args.lab, session_id=args.session_id, reader=args.reader,
                         reader_sha256=args.reader_sha256)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
