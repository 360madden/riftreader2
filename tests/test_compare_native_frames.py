"""Deterministic offline QA for retained top-down and bottom-up native BMPs."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.compare_native_frames import (
    FrameError, compare_files, main, parse_roi, read_frame,
)


def write_bmp(path: Path, rows: list[list[tuple[int, int, int, int]]],
              *, top_down: bool = True) -> None:
    height = len(rows)
    width = len(rows[0])
    assert height > 0 and width > 0 and all(len(row) == width for row in rows)
    payload = b"".join(bytes(pixel) for row in
                       (rows if top_down else reversed(rows)) for pixel in row)
    header = bytearray(54)
    header[:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + len(payload))
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<ii", header, 18, width, -height if top_down else height)
    struct.pack_into("<HH", header, 26, 1, 32)
    path.write_bytes(header + payload)


class NativeFrameDiffTests(unittest.TestCase):
    def test_top_down_and_bottom_up_identical_rgb_ignore_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.bmp", Path(directory) / "b.bmp"
            write_bmp(a, [[(1, 2, 3, 0), (5, 6, 7, 10)],
                          [(8, 9, 10, 11), (12, 13, 14, 12)]])
            write_bmp(b, [[(1, 2, 3, 255), (5, 6, 7, 42)],
                          [(8, 9, 10, 254), (12, 13, 14, 0)]],
                      top_down=False)
            report = compare_files(a, b)
            self.assertFalse(report["identicalImageBytes"])
            self.assertEqual(report["regions"]["full"]["changedPixels"], 0)
            self.assertEqual(report["regions"]["full"]["meanAbsoluteRgbDelta"], 0)
            self.assertEqual(report["inputs"][0]["sha256"],
                             hashlib.sha256(a.read_bytes()).hexdigest().upper())

    def test_roi_and_pixel_mean_are_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.bmp", Path(directory) / "b.bmp"
            empty = (0, 0, 0, 0)
            write_bmp(a, [[empty, empty], [empty, empty]])
            write_bmp(b, [[empty, (10, 0, 0, 0)],
                          [empty, (20, 20, 20, 0)]])
            report = compare_files(a, b, ["right=1,0,2,2", "top=0,0,2,1"])
            self.assertEqual(report["regions"]["full"]["changedPixels"], 2)
            self.assertEqual(report["regions"]["full"]["changedPercent"], 50.0)
            self.assertEqual(report["regions"]["full"]["meanAbsoluteRgbDelta"],
                             round(70 / 12, 4))
            self.assertEqual(report["regions"]["right"]["changedPercent"], 100.0)
            self.assertEqual(report["regions"]["top"]["changedPercent"], 50.0)
            self.assertEqual(report["image"], {"width": 2, "height": 2, "bitDepth": 32})

    def test_invalid_header_and_dimensions_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.bmp"
            write_bmp(path, [[(1, 2, 3, 4)]])
            original = path.read_bytes()
            changes = [
                (0, b"ZZ"),
                (26, (2).to_bytes(2, "little")),
                (28, (24).to_bytes(2, "little")),
                (30, (1).to_bytes(4, "little")),
                (18, (0).to_bytes(4, "little")),
                (22, (0).to_bytes(4, "little")),
                (14, (500).to_bytes(4, "little")),
            ]
            for offset, value in changes:
                with self.subTest(offset=offset, value=value):
                    damaged = bytearray(original)
                    damaged[offset:offset + len(value)] = value
                    path.write_bytes(damaged)
                    with self.assertRaises(FrameError):
                        read_frame(path)
            path.write_bytes(original[:-1])
            with self.assertRaises(FrameError):
                read_frame(path)

    def test_different_image_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.bmp", Path(directory) / "b.bmp"
            write_bmp(a, [[(0, 0, 0, 0)]])
            write_bmp(b, [[(0, 0, 0, 0), (0, 0, 0, 0)]])
            with self.assertRaisesRegex(FrameError, "dimensions"):
                compare_files(a, b)

    def test_invalid_or_duplicate_rois_are_rejected(self):
        for value in ["too wide=0,0,1,1", "world=0,0,3,1",
                      "world=1,1,0,0", "world=-1,0,1,1", "world=1,1,1,2",
                      "world=0,0,a,1", "world=0,0,1"]:
            with self.subTest(value=value):
                with self.assertRaises(FrameError):
                    parse_roi(value, 2, 2)
        with tempfile.TemporaryDirectory() as directory:
            a = Path(directory) / "a.bmp"
            write_bmp(a, [[(0, 0, 0, 0)]])
            with self.assertRaisesRegex(FrameError, "duplicate"):
                compare_files(a, a, ["full=0,0,1,1"])
            with self.assertRaisesRegex(FrameError, "maximum eight"):
                compare_files(a, a, [f"n{i}=0,0,1,1" for i in range(9)])

    def test_cli_refuses_overwrite_and_preserves_report(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b, report = (Path(directory) / x for x in ("a.bmp", "b.bmp", "report.json"))
            write_bmp(a, [[(0, 0, 0, 0)]])
            write_bmp(b, [[(1, 0, 0, 0)]])
            args = ["--before", str(a), "--after", str(b),
                    "--roi", "detail=0,0,1,1", "--output", str(report)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
            digest = hashlib.sha256(report.read_bytes()).hexdigest()
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
            self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
