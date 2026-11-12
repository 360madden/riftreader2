#!/usr/bin/env python3
"""Offline before/after visual-change check for RR2's WGC screenshot receipts.

This checks only pixels and retained capture identities. It does not send input,
read game memory, establish actor yaw, or prove a particular key caused the view.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageChops

Image.MAX_IMAGE_PIXELS = 4096 * 2160
MAX_PNG_BYTES = 12 * 1024 * 1024
MAX_RECEIPT_BYTES = 128 * 1024
SAMPLE_WIDTH, SAMPLE_HEIGHT = 96, 64


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def unique_fields(pairs: list[tuple[str, object]]) -> dict:
    found: dict = {}
    for key, value in pairs:
        require(key not in found, "visual-duplicate-json-key")
        found[key] = value
    return found


def read_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink()
            and 1 <= path.stat().st_size <= MAX_RECEIPT_BYTES,
            "visual-receipt-missing-or-oversized")
    data = json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_fields,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("visual-nonfinite-json")))
    require(type(data) is dict, "visual-receipt-invalid")
    return data


def utc(value: object) -> datetime:
    require(type(value) is str and len(value) <= 48, "visual-time-invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("visual-time-invalid") from error
    require(result.utcoffset() == timedelta(0), "visual-time-invalid")
    return result


def read_frame(image_path: Path, receipt_path: Path) -> tuple[dict, Image.Image, str]:
    report = read_json(receipt_path)
    require(report.get("schemaVersion") == 1
            and report.get("status") == "unqualified-gpu-window-frame"
            and report.get("inputSent") is False
            and report.get("focusChangedByProbe") is False
            and report.get("bodyHeadingVerified") is False
            and report.get("gameResponseVerified") is False,
            "visual-capture-receipt-unqualified")
    require(type(report.get("machine")) is str
            and report.get("requestedBackend") in ("wgc", "dxgi"),
            "visual-capture-receipt-invalid")
    targets = (report.get("targetBefore"), report.get("targetAfter"))
    require(all(type(x) is dict for x in targets), "visual-target-missing")
    keys = ("pid", "startTicks", "sha256", "hwnd", "processName", "width", "height")
    ident = tuple(targets[0].get(k) for k in keys)
    require(ident == tuple(targets[1].get(k) for k in keys)
            and type(ident[0]) is int and ident[0] > 0
            and type(ident[1]) is int and ident[1] > 0
            and type(ident[2]) is str and len(ident[2]) == 64
            and type(ident[3]) is int and ident[3] > 0
            and type(ident[4]) is str and ident[4]
            and type(ident[5]) is int and type(ident[6]) is int,
            "visual-target-identity-invalid")
    width, height = report.get("frameWidth"), report.get("frameHeight")
    require(type(width) is int and type(height) is int
            and 64 <= width <= 4096 and 64 <= height <= 2160,
            "visual-frame-dimensions-invalid")
    started = utc(report.get("capturedStartedAtUtc"))
    ended = utc(report.get("capturedCompletedAtUtc"))
    require(started <= ended and (ended-started).total_seconds() <= 6,
            "visual-capture-timing-invalid")

    require(type(report.get("outputPath")) is str
            and Path(report["outputPath"]).resolve() == image_path.resolve(),
            "visual-receipt-path-mismatch")
    require(image_path.is_file() and not image_path.is_symlink()
            and 1 <= image_path.stat().st_size <= MAX_PNG_BYTES,
            "visual-image-missing-or-oversized")
    raw = image_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    require(digest == report.get("imageSha256")
            and len(raw) == report.get("imageBytes"), "visual-image-hash-or-size-mismatch")
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), "visual-image-not-png")
    try:
        with Image.open(image_path) as opened:
            require(opened.format == "PNG" and opened.size == (width, height),
                    "visual-png-dimensions-mismatch")
            image = opened.convert("RGB")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("visual-image-decode-failed") from error

    quality = report.get("quality")
    require(type(quality) is dict and quality.get("potentiallyBlankOrBlack") is False,
            "visual-unusable-capture-quality")
    return report, image, digest


def visual_compare(before_png: Path, after_png: Path,
                   before_json: Path, after_json: Path) -> dict:
    before, bimage, before_sha = read_frame(before_png, before_json)
    after, aimage, after_sha = read_frame(after_png, after_json)
    ids = ("pid", "startTicks", "sha256", "hwnd", "processName", "width", "height")
    require(before["machine"] == after["machine"]
            and all(before["targetBefore"][k] == after["targetBefore"][k] for k in ids),
            "visual-session-or-window-changed")
    require(bimage.size == aimage.size, "visual-frame-size-changed")
    gap = (utc(after["capturedStartedAtUtc"]) -
           utc(before["capturedCompletedAtUtc"])).total_seconds()
    require(0 <= gap <= 30, "visual-pair-time-gap-invalid")

    width, height = bimage.size
    crop = (int(width * .15), int(height * .2),
            int(width * .85), int(height * .75))
    def downsample(image: Image.Image) -> Image.Image:
        return image.crop(crop).resize((SAMPLE_WIDTH, SAMPLE_HEIGHT),
                                       Image.Resampling.BILINEAR)

    left = downsample(bimage)
    right = downsample(aimage)
    difference = ImageChops.difference(left, right)
    channels = difference.tobytes()  # RGB, three bytes per sampled pixel.
    sample_count = len(channels) // 3
    changed = sum(1 for i in range(0, len(channels), 3)
                  if max(channels[i:i+3]) >= 24)
    mean_abs_channel_delta = sum(channels) / len(channels)
    changed_fraction = changed / sample_count
    candidate = changed_fraction >= .18 and mean_abs_channel_delta >= 15
    return {
        "schemaVersion": 1,
        "status": "offline-visual-change-candidate",
        "machine": before["machine"],
        "targetIdentity": {k: before["targetBefore"][k] for k in ids},
        "beforeImageSha256": before_sha,
        "afterImageSha256": after_sha,
        "beforeReceiptSha256": hashlib.sha256(before_json.read_bytes()).hexdigest().upper(),
        "afterReceiptSha256": hashlib.sha256(after_json.read_bytes()).hexdigest().upper(),
        "captureGapSeconds": gap,
        "comparisonCropPixels": crop,
        "sampledPixels": sample_count,
        "changedPixelFractionCandidate": changed_fraction,
        "meanAbsoluteChannelDeltaCandidate": mean_abs_channel_delta,
        "visibleViewChangeCandidate": candidate,
        "inputSent": False,
        "gameResponseVerified": False,
        "actorHeadingQualified": False,
        "cameraHeadingQualified": False,
        "limitations": [
            "Visual difference may reflect animation, UI, weather or other scene changes.",
            "A difference between two screenshots is not proof an A/D key caused it.",
            "Screenshots cannot distinguish player body yaw from camera-only movement.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-png", required=True, type=Path)
    parser.add_argument("--after-png", required=True, type=Path)
    parser.add_argument("--before-receipt", required=True, type=Path)
    parser.add_argument("--after-receipt", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = visual_compare(args.before_png, args.after_png,
                                args.before_receipt, args.after_receipt)
        content = json.dumps(result, allow_nan=False, sort_keys=True)
        if args.out is not None:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(content + "\n")
        print(content)
        return 0
    except (ValueError, OSError, OverflowError, TypeError, KeyError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error),
                          "inputSent": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
