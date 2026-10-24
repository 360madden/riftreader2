#!/usr/bin/env python3
"""Compare retained 32-bit native BMP frames without changing source images.

This is an offline pixel-difference diagnostic. Changed pixels alone cannot
establish player movement, geometric optical flow, or live field semantics.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 16 * 1024 * 1024
ROI_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")


class FrameError(ValueError):
    """A BMP, ROI, or publication precondition is not satisfied."""


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    top_down: bool
    pixel_offset: int
    raw: bytes
    sha256: str


def read_frame(path: Path) -> Frame:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise FrameError("BMP exceeds 64 MiB limit")
    if len(raw) < 54 or raw[:2] != b"BM":
        raise FrameError("not a complete Windows BMP header")
    file_size = struct.unpack_from("<I", raw, 2)[0]
    pixel_offset = struct.unpack_from("<I", raw, 10)[0]
    dib_size = struct.unpack_from("<I", raw, 14)[0]
    width, signed_height = struct.unpack_from("<ii", raw, 18)
    planes, bits_per_pixel = struct.unpack_from("<HH", raw, 26)
    compression = struct.unpack_from("<I", raw, 30)[0]
    if file_size != len(raw) or dib_size < 40 or pixel_offset < 14 + dib_size:
        raise FrameError("BMP header sizes or pixel offset are inconsistent")
    if (width <= 0 or signed_height == 0 or planes != 1 or bits_per_pixel != 32
            or compression != 0):
        raise FrameError("only uncompressed 32-bit Windows BMP is supported")
    height = abs(signed_height)
    pixels = width * height
    if pixels > MAX_PIXELS or pixel_offset + pixels * 4 > len(raw):
        raise FrameError("BMP pixel extent exceeds bounds or file bytes")
    return Frame(width, height, signed_height < 0, pixel_offset, raw,
                 hashlib.sha256(raw).hexdigest().upper())


def parse_roi(value: str, width: int, height: int) -> tuple[str, tuple[int, int, int, int]]:
    try:
        name, coords = value.split("=", 1)
        parts = coords.split(",")
        if not ROI_NAME.fullmatch(name) or len(parts) != 4:
            raise ValueError()
        if any(not re.fullmatch(r"[0-9]+", part) for part in parts):
            raise ValueError()
        x0, y0, x1, y1 = (int(part) for part in parts)
    except ValueError as error:
        raise FrameError("ROI must be NAME=X0,Y0,X1,Y1 using nonnegative integers") from error
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise FrameError(f"ROI {name} is empty or outside the image")
    return name, (x0, y0, x1, y1)


def compare_region(first: Frame, second: Frame,
                   roi: tuple[int, int, int, int]) -> dict:
    if (first.width, first.height) != (second.width, second.height):
        raise FrameError("BMP pixel dimensions differ")
    x0, y0, x1, y1 = roi
    if not (0 <= x0 < x1 <= first.width and 0 <= y0 < y1 <= first.height):
        raise FrameError("comparison ROI is invalid")
    changed = 0
    absolute = 0
    for y in range(y0, y1):
        a_row = y if first.top_down else first.height - 1 - y
        b_row = y if second.top_down else second.height - 1 - y
        for x in range(x0, x1):
            a = first.pixel_offset + (a_row * first.width + x) * 4
            b = second.pixel_offset + (b_row * second.width + x) * 4
            # Ignore BMP's unused fourth channel, not color information.
            red_blue_green = (
                abs(first.raw[a] - second.raw[b]),
                abs(first.raw[a + 1] - second.raw[b + 1]),
                abs(first.raw[a + 2] - second.raw[b + 2]),
            )
            changed += any(red_blue_green)
            absolute += sum(red_blue_green)
    total = (x1 - x0) * (y1 - y0)
    return {
        "bounds": [x0, y0, x1, y1],
        "totalPixels": total,
        "changedPixels": changed,
        "changedPercent": round(100 * changed / total, 4),
        "meanAbsoluteRgbDelta": round(absolute / (total * 3), 4),
    }


def compare_files(first_path: Path, second_path: Path,
                  roi_specs: list[str] | None = None) -> dict:
    first = read_frame(first_path)
    second = read_frame(second_path)
    if (first.width, first.height) != (second.width, second.height):
        raise FrameError("BMP pixel dimensions differ")
    regions = {"full": (0, 0, first.width, first.height)}
    for spec in roi_specs or []:
        if len(regions) > 8:
            raise FrameError("maximum eight custom ROIs exceeded")
        name, bounds = parse_roi(spec, first.width, first.height)
        if name in regions:
            raise FrameError(f"duplicate ROI name: {name}")
        regions[name] = bounds
    return {
        "schemaVersion": 1,
        "evidenceKind": "native-bmp-frame-difference/1",
        "inputs": [
            {"path": str(first_path), "sha256": first.sha256},
            {"path": str(second_path), "sha256": second.sha256},
        ],
        "image": {"width": first.width, "height": first.height, "bitDepth": 32},
        "identicalImageBytes": first.raw == second.raw,
        "regions": {name: compare_region(first, second, bounds)
                    for name, bounds in regions.items()},
        "limitations": [
            "Pixel changes do not prove player or camera movement.",
            "Only captured BMP pixels were compared; field and scene semantics are unqualified.",
            "The fourth BMP channel is ignored and top-down/bottom-up storage is normalized.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--roi", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_files(args.before, args.after, args.roi)
        serialized = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output is not None:
            # Never overwrite retained comparison evidence.
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
        print(serialized, end="")
        return 0
    except (OSError, FrameError, struct.error) as error:
        print(json.dumps({"state": "blocked", "reason": str(error)[:256]}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
