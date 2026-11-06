from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import launch_live_reader
from scripts.live_reader_config import (
    DEFAULT_SCAN_BYTES,
    MAX_SCAN_BYTES,
    build_live_configuration,
    load_scan_limits,
    resolve_max_scan_bytes,
)


class LiveReaderConfigTests(unittest.TestCase):
    def test_tracked_profile_keeps_default_and_raises_only_lab1(self):
        self.assertEqual(6 * 1024**3, resolve_max_scan_bytes("lab1"))
        self.assertEqual(DEFAULT_SCAN_BYTES, resolve_max_scan_bytes("lab2"))

    def test_vm_paths_and_cached_guest_fallback_are_scoped_per_lab(self):
        self.assertEqual(
            str(launch_live_reader.LABS["lab1"]["vmx"]),
            r"C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx",
        )
        self.assertEqual(
            str(launch_live_reader.LABS["lab2"]["vmx"]),
            r"C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx",
        )
        self.assertEqual(
            launch_live_reader.legacy_guest_target("lab1"),
            "RiftReader2 Guest Windows: "
            + str(launch_live_reader.LABS["lab1"]["legacyGuestVmx"].resolve(strict=False)),
        )
        self.assertIsNone(launch_live_reader.legacy_guest_target("lab2"))
        self.assertNotEqual(
            launch_live_reader.legacy_guest_target("lab1"),
            "RiftReader2 Guest Windows: "
            + str(launch_live_reader.LABS["lab2"]["vmx"].resolve(strict=False)),
        )

    def test_explicit_override_wins_and_is_bounded(self):
        self.assertEqual(5 * 1024**3, resolve_max_scan_bytes("lab1", override=5 * 1024**3))
        for value in (0, MAX_SCAN_BYTES + 1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_max_scan_bytes("lab1", override=value)

    def test_profile_shape_and_values_fail_closed(self):
        cases = (
            {"schemaVersion": 2, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {}},
            {"schemaVersion": 1, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {"lab3": 1}},
            {"schemaVersion": 1, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {"lab1": 0}},
            {"schemaVersion": 1, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {}, "extra": 1},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "limits.json"
            for value in cases:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_scan_limits(path)

    def test_builder_places_resolved_limit_in_reader_configuration(self):
        value = build_live_configuration(
            endpoint="http://192.168.56.1:49813/observe",
            token="x" * 32,
            output_path=r"C:\reader\latest.json",
            duration_seconds=900,
            poll_interval_milliseconds=250,
            max_scan_bytes=6 * 1024**3,
        )
        self.assertEqual(6 * 1024**3, value["maxScanBytes"])
        self.assertEqual(10, value["maxScanSeconds"])
        self.assertEqual(4 * 1024**3, DEFAULT_SCAN_BYTES)

    def test_tracked_launcher_writes_resolved_lab1_limit(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}
        ):
            limit = resolve_max_scan_bytes("lab1")
            staging, path, _ = launch_live_reader.private_config(
                "unit-launcher",
                "http://192.168.56.1:49813/observe",
                "x" * 32,
                r"C:\reader\latest.json",
                900,
                250,
                limit,
            )
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(6 * 1024**3, value["maxScanBytes"])
            finally:
                launch_live_reader.clean_private(staging)


if __name__ == "__main__":
    unittest.main()
