"""Offline hash-pinned visual comparison of two retained RIFT screenshots.

Pixel changes can come from camera movement, animation, HUD or lighting:
they are not actor-heading, successful-input or player-turn proof.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quick_review_capture import MAX_CAPTURE_BYTES

HASH = re.compile(r"[0-9A-Fa-f]{64}\Z")
QUALIFICATION = "visual-pixel-difference-only; player-facing, camera movement and input response unqualified"


def _load(path, expected_hash):
    from PIL import Image, UnidentifiedImageError

    if not isinstance(expected_hash, str) or HASH.fullmatch(expected_hash) is None:
        raise ValueError("invalid-source-hash")
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_CAPTURE_BYTES:
        raise ValueError("source-capture-unavailable")
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest().upper()
    if digest != expected_hash.upper():
        raise ValueError("source-hash-mismatch")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ("PNG", "BMP") or not 16 <= image.width <= 8192 or not 16 <= image.height <= 8192:
                raise ValueError("source-image-invalid")
            return image.convert("RGB"), digest
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("source-image-unreadable") from error


def compare(before, before_hash, after, after_hash, output, *, crop=None, threshold=16):
    """Compare corresponding pixels and save a labelled, non-authoritative preview."""
    from PIL import Image, ImageChops, ImageDraw, ImageStat

    if type(threshold) is not int or not 1 <= threshold <= 255:
        raise ValueError("invalid-difference-threshold")
    left, left_hash = _load(before, before_hash)
    right, right_hash = _load(after, after_hash)
    if left.size != right.size:
        raise ValueError("source-dimensions-mismatch")
    width, height = left.size
    if crop is None:
        crop = (width // 4, height // 8, width * 3 // 4, height * 7 // 8)
    if (not isinstance(crop, (tuple, list)) or len(crop) != 4
            or any(type(v) is not int for v in crop)
            or not 0 <= crop[0] < crop[2] <= width
            or not 0 <= crop[1] < crop[3] <= height):
        raise ValueError("invalid-comparison-crop")
    first, second = left.crop(crop), right.crop(crop)
    difference = ImageChops.difference(first, second)
    rgb = difference.tobytes()
    changed = sum(max(rgb[index:index + 3]) >= threshold
                  for index in range(0, len(rgb), 3))
    count = first.width * first.height
    mean_channel_delta = sum(ImageStat.Stat(difference).mean) / 3

    preview_left, preview_right = first.copy(), second.copy()
    preview_left.thumbnail((640, 640), Image.Resampling.LANCZOS)
    preview_right.thumbnail((640, 640), Image.Resampling.LANCZOS)
    board = Image.new("RGB", (preview_left.width + preview_right.width,
                              max(preview_left.height, preview_right.height) + 25), (24, 24, 24))
    board.paste(preview_left, (0, 25))
    board.paste(preview_right, (preview_left.width, 25))
    labels = ImageDraw.Draw(board)
    labels.text((8, 5), "BEFORE", fill=(255, 255, 255))
    labels.text((preview_left.width + 8, 5), "AFTER", fill=(255, 255, 255))
    image_bytes = BytesIO()
    board.save(image_bytes, format="PNG", optimize=True)
    output = Path(output)
    if not output.parent.is_dir() or output.is_symlink():
        raise ValueError("preview-destination-invalid")
    with output.open("xb") as handle:
        handle.write(image_bytes.getvalue())
    return {
        "schemaVersion": 1, "status": "visual-difference-candidate",
        "beforeSha256": left_hash, "afterSha256": right_hash,
        "sourceDimensions": [width, height], "comparisonCrop": list(crop),
        "pixelThreshold": threshold, "changedPixelFraction": round(changed / count, 6),
        "meanAbsoluteChannelDelta": round(mean_channel_delta, 6),
        "sourceBytesEqual": left_hash == right_hash,
        "previewPath": str(output), "previewSha256": sha256(image_bytes.getvalue()).hexdigest().upper(),
        "qualification": QUALIFICATION
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--before-sha", required=True)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--after-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--crop", nargs=4, type=int)
    parser.add_argument("--threshold", type=int, default=16)
    args = parser.parse_args(argv)
    try:
        result = compare(args.before, args.before_sha, args.after, args.after_sha, args.output,
                         crop=args.crop, threshold=args.threshold)
    except (ValueError, FileExistsError, OSError, ImportError) as error:
        reason = str(error) if isinstance(error, ValueError) else "preview-write-or-pillow-unavailable"
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
