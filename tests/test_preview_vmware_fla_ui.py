"""Focused, no-focus tests for the optional FlaUI host-window preview."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from scripts import preview_vmware_fla_ui as preview


def listing(*entries):
    return {"content": [{"text": "\n".join(
        f'- {handle}: "{title}" ({process})'
        for handle, title, process in entries)}]}


def png(width=974, height=845):
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13)
            + b"IHDR" + struct.pack(">II", width, height) + b"\x00" * 20)


class FakeClient:
    def __init__(self, result, *, write=True, method="native-window",
                 fallback=False, width=974, height=845, data=None):
        self.result = result
        self.write = write
        self.method = method
        self.fallback = fallback
        self.width = width
        self.height = height
        self.data = data if data is not None else png()
        self.calls = []

    def tool(self, name, args=None):
        self.calls.append((name, args))
        if name == "windows_list_windows":
            return self.result
        if name != "windows_screenshot":
            raise AssertionError("unexpected tool")
        if self.write:
            Path(args["savePath"]).write_bytes(self.data)
        return {"content": [{"text": json.dumps({
            "method": self.method, "screenFallback": self.fallback,
            "width": self.width, "height": self.height})}]}


class PreviewTests(unittest.TestCase):
    def test_selects_only_exact_lab_window(self):
        windows = listing(
            ("w1", preview.LAB_TITLES["lab2"], "vmware"),
            ("w2", preview.LAB_TITLES["lab1"], "vmware"),
            ("w3", "Other VMware Workstation", "vmware"),
        )
        self.assertEqual(preview.select_window(windows, "lab2"), "w1")
        self.assertEqual(preview.select_window(windows, "lab1"), "w2")

    def test_rejects_duplicate_or_spoofed_window(self):
        exact = preview.LAB_TITLES["lab2"]
        for windows in (
            listing(),
            listing(("w1", exact, "notepad")),
            listing(("w1", exact + " extra", "vmware")),
            listing(("w1", exact, "vmware"), ("w2", exact, "vmware")),
        ):
            with self.subTest(windows=windows), self.assertRaisesRegex(
                    preview.PreviewError, "vmware-window-not-unique-or-missing"):
                preview.select_window(windows, "lab2")

    def test_success_is_explicitly_non_authoritative(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "image.png"
            fake = FakeClient(listing(("w1", preview.LAB_TITLES["lab2"], "vmware")))
            result = preview.capture_with_client(fake, "lab2", path)
            self.assertEqual(result["status"], "captured-nonauthoritative")
            self.assertTrue(result["nonAuthoritative"])
            self.assertFalse(result["movementEligible"])
            self.assertFalse(result["gameProcessIdentityVerified"])
            self.assertFalse(result["requestedFocusChange"])
            self.assertFalse(result["gameInputSent"])
            self.assertEqual(result["imageWidth"], 974)
            self.assertEqual(result["imageHeight"], 845)
            self.assertEqual(result["imageSha256"], hashlib.sha256(png()).hexdigest().upper())
            self.assertEqual([c[0] for c in fake.calls],
                             ["windows_list_windows", "windows_screenshot"])
            args = fake.calls[1][1]
            self.assertTrue(args["background"])
            self.assertTrue(args["strictNative"])
            self.assertFalse(args["parkPointer"])
            self.assertFalse(args["includeImage"])
            self.assertEqual(args["savePath"], str(path.resolve()))
            self.assertNotIn("captureId", result)
            self.assertNotIn("reviewDeadlineUtc", result)

    def test_rejects_screen_fallback_or_unproven_native_method(self):
        with tempfile.TemporaryDirectory() as folder:
            for method, fallback in (("screen", False), ("native-window", True)):
                with self.subTest(method=method, fallback=fallback):
                    path = Path(folder) / f"{method}-{fallback}.png"
                    fake = FakeClient(listing(("w1", preview.LAB_TITLES["lab1"], "vmware")),
                                      method=method, fallback=fallback)
                    with self.assertRaisesRegex(preview.PreviewError,
                                                "native-capture-not-proven"):
                        preview.capture_with_client(fake, "lab1", path)

    def test_rejects_missing_invalid_or_wrong_sized_image(self):
        with tempfile.TemporaryDirectory() as folder:
            options = [
                {"write": False},
                {"data": b"not-a-png" + b"\x00" * 40},
                {"width": 1000},
            ]
            for i, option in enumerate(options):
                fake = FakeClient(listing(("w1", preview.LAB_TITLES["lab2"], "vmware")),
                                  **option)
                with self.subTest(option=option), self.assertRaises(preview.PreviewError):
                    preview.capture_with_client(fake, "lab2", Path(folder) / f"{i}.png")

    def test_wrong_machine_rejected_before_any_capture(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                preview.socket, "gethostname", return_value="LEGION"):
            path = Path(folder) / "not-created"
            with self.assertRaisesRegex(preview.PreviewError, "wrong-machine"):
                preview.capture("lab2", "AMD-DESKTOP", path)
            self.assertFalse(path.exists())

    def test_wrong_expected_host_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                preview.socket, "gethostname", return_value="AMD-DESKTOP"):
            with self.assertRaisesRegex(preview.PreviewError, "wrong-machine"):
                preview.capture("lab2", "LEGION", Path(folder) / "not-created")

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                preview.socket, "gethostname", return_value="AMD-DESKTOP"):
            root = Path(folder) / "flaui"
            (root / "local/dotnet").mkdir(parents=True)
            (root / "local/dotnet/dotnet.exe").write_bytes(b"x")
            server = root / "src/FlaUI.Mcp/bin/Release/net8.0-windows/FlaUI.Mcp.dll"
            server.parent.mkdir(parents=True)
            server.write_bytes(b"x")
            existing = Path(folder) / "output"
            existing.mkdir()
            (existing / "image.png").write_bytes(b"untouched")
            with self.assertRaises(FileExistsError):
                preview.capture("lab1", "AMD-DESKTOP", existing, root)
            self.assertEqual((existing / "image.png").read_bytes(), b"untouched")


if __name__ == "__main__":
    unittest.main()
