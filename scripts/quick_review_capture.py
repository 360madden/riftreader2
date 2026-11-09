"""Display an exact RR2 capture quickly without moving or modifying its source.

The JPEG is a non-authoritative visual preview. The original BMP/PNG, metadata,
review age, and SHA-256 remain the sole movement admission evidence.
"""
from __future__ import annotations

import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys

MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_JPEG_BYTES = 40_000
MIN_WIDTH = 500
HASH = re.compile(r"[0-9A-Fa-f]{64}\Z")


def preview(capture: Path, expected_sha256: str, width: int = 840) -> dict:
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        raise ValueError("invalid-capture-hash")
    if not 500 <= width <= 1600:
        raise ValueError("invalid-preview-width")
    capture = Path(capture)
    if (capture.is_symlink() or not capture.is_file()
            or not 0 < capture.stat().st_size <= MAX_CAPTURE_BYTES):
        raise ValueError("capture-unavailable")
    raw = capture.read_bytes()
    digest = sha256(raw).hexdigest().upper()
    if digest != expected_sha256.upper():
        raise ValueError("capture-hash-mismatch")

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as error:
        raise ValueError("pillow-unavailable") from error

    try:
        with Image.open(BytesIO(raw)) as image:
            if (image.format not in ("BMP", "PNG") or not 1 <= image.width <= 8192
                    or not 1 <= image.height <= 8192):
                raise ValueError("capture-image-invalid")
            original_size = (image.width, image.height)
            source = image.convert("RGB")
        for size in (width, round(width * .85), round(width * .7), MIN_WIDTH):
            target = max(MIN_WIDTH, size)
            scaled = source.copy()
            scaled.thumbnail((target, target), Image.Resampling.LANCZOS)
            stream = BytesIO()
            scaled.save(stream, format="JPEG", quality=58, optimize=True)
            if stream.tell() <= MAX_JPEG_BYTES:
                return {
                    "sourceSha256": digest,
                    "sourceDimensions": list(original_size),
                    "previewDimensions": [scaled.width, scaled.height],
                    "previewFormat": "jpeg",
                    "nonAuthoritative": True,
                    "base64": base64.b64encode(stream.getvalue()).decode("ascii"),
                }
        raise ValueError("preview-too-large")
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("capture-image-unreadable") from error


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--width", type=int, default=840)
    args = parser.parse_args(argv)
    try:
        result = preview(args.capture, args.sha256, args.width)
    except ValueError as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), flush=True)
        return 2
    print(json.dumps(result, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
