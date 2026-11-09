"""Display an exact RR2 capture quickly without moving or modifying its source.

The preview is non-authoritative. The original BMP/PNG, metadata, review age,
and SHA-256 remain the sole movement admission evidence. Compact WebP is an
explicit file-only transport option, not a desktop capture or visual approval.
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
MAX_COMPACT_BYTES = 4_500
MIN_WIDTH = 500
HASH = re.compile(r"[0-9A-Fa-f]{64}\Z")


def preview(capture: Path, expected_sha256: str, width: int = 840, *,
            compact: bool = False, crop: tuple[int, int, int, int] | None = None) -> dict:
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        raise ValueError("invalid-capture-hash")
    if not 500 <= width <= 1600:
        raise ValueError("invalid-preview-width")
    if type(compact) is not bool or (crop is not None and not compact):
        raise ValueError("invalid-preview-mode")
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
        if compact:
            box = (0, 0, *original_size) if crop is None else crop
            if (not isinstance(box, (list, tuple)) or len(box) != 4
                    or any(type(value) is not int for value in box)
                    or not 0 <= box[0] < box[2] <= original_size[0]
                    or not 0 <= box[1] < box[3] <= original_size[1]):
                raise ValueError("invalid-preview-crop")
            source = source.crop(box)
            for target in dict.fromkeys((min(width, 540), MIN_WIDTH)):
                scaled = source.copy()
                scaled.thumbnail((target, target), Image.Resampling.LANCZOS)
                for quality in (30, 15, 0):
                    stream = BytesIO()
                    scaled.save(stream, format="WEBP", quality=quality, method=4)
                    data = stream.getvalue()
                    if len(data) <= MAX_COMPACT_BYTES:
                        return {"sourceSha256": digest,
                                "sourceDimensions": list(original_size),
                                "sourceCrop": list(box),
                                "previewDimensions": [scaled.width, scaled.height],
                                "previewFormat": "webp", "previewQuality": quality,
                                "previewSha256": sha256(data).hexdigest().upper(),
                                "nonAuthoritative": True,
                                "base64": base64.b64encode(data).decode("ascii")}
            raise ValueError("preview-too-large")
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
    parser.add_argument("--compact", action="store_true",
                        help="explicit bounded WebP file preview; does not extend review age")
    parser.add_argument("--crop", nargs=4, type=int, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                        help="optional source-coordinate detail crop; requires --compact")
    args = parser.parse_args(argv)
    try:
        result = preview(args.capture, args.sha256, args.width,
                         compact=args.compact, crop=args.crop)
    except ValueError as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), flush=True)
        return 2
    print(json.dumps(result, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
