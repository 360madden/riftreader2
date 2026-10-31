"""Offline contract and provenance tests for exact-epoch native HP rereads."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from scripts.reread_current_native_hp import BUILD, GUEST, candidates, run


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class NativeHealthRereadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive = Path(self.tmp.name) / "scout.zip"

    def make_archive(self, *, build=BUILD, saved_build=BUILD,
                     valid_layout=True, corrupt_sha=False):
        data = bytearray(100)
        if valid_layout:
            struct.pack_into("<i", data, 24, 45)
            struct.pack_into("<i", data, 28, 65536)
            for offset in (32, 40, 48):
                struct.pack_into("<i", data, offset, 18208)
        data = bytes(data)
        target = {
            "processId": 8164,
            "processStartUtcTicks": 639290507142219120,
            "executableSha256": build,
        }
        identity = {**target, "executableSha256": saved_build}
        snapshot = {
            "identity": identity,
            "chunks": [{
                "address": "0x200010000",
                "requestedByteLength": 100,
                "status": "success",
                "bytesBase64": base64.b64encode(data).decode("ascii"),
                "bytesSha256": sha(data),
            }],
        }
        raw = json.dumps(snapshot).encode("utf-8")
        index = {
            "evidenceKind": "native-value-scout/1",
            "request": {"target": target},
            "candidates": [{
                "status": "success",
                "snapshotFile": "capture-001.snapshot.json",
                "snapshotSha256": "0" * 64 if corrupt_sha else sha(raw),
            }],
        }
        with zipfile.ZipFile(self.archive, "w") as z:
            z.writestr("index.json", json.dumps(index))
            z.writestr("capture-001.snapshot.json", raw)

    def test_valid_hash_pinned_snapshot_and_hp_layout(self):
        self.make_archive()
        target, ranges = candidates(self.archive, 18208, 45)
        self.assertEqual(8164, target["processId"])
        self.assertEqual([0x200010000], [address for address, _ in ranges])
        self.assertEqual(100, len(ranges[0][1]))
        self.assertEqual(18208, struct.unpack_from("<i", ranges[0][1], 40)[0])

    def test_rejects_wrong_game_build(self):
        self.make_archive(build="0" * 64)
        with self.assertRaisesRegex(ValueError, "scout-build-mismatch"):
            candidates(self.archive, 18208, 45)

    def test_rejects_changed_snapshot_identity(self):
        self.make_archive(saved_build="0" * 64)
        with self.assertRaisesRegex(ValueError, "scout-candidate-identity-mismatch"):
            candidates(self.archive, 18208, 45)

    def test_rejects_tampered_source(self):
        self.make_archive(corrupt_sha=True)
        with self.assertRaisesRegex(ValueError, "scout-snapshot-sha-mismatch"):
            candidates(self.archive, 18208, 45)

    def test_rejects_missing_hp_layout_and_bad_seed(self):
        self.make_archive(valid_layout=False)
        with self.assertRaisesRegex(ValueError, "no-structural-hp-candidates"):
            candidates(self.archive, 18208, 45)
        self.make_archive()
        with self.assertRaisesRegex(ValueError, "no-structural-hp-candidates"):
            candidates(self.archive, 123, 45)

    def test_selection_is_bounded(self):
        self.make_archive()
        for count in (0, 65):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "invalid-selection"):
                candidates(self.archive, 18208, 45, limit=count)
        self.assertEqual(1, len(candidates(self.archive, 18208, 45, limit=64)[1]))

    def test_missing_reader_and_unpinned_executable_fail_before_guest(self):
        for pid, exe, pin in ((None, None, None), (1, "RiftReader2.Live.exe", "A" * 64),
                              (-1, None, None)):
            with self.subTest(pid=pid, exe=exe), self.assertRaisesRegex(ValueError, "invalid-lab-or-reader"):
                run("lab1", pid, exe, pin, self.archive, 18208, 45)
        with self.assertRaisesRegex(ValueError, "guest-reader-executable-sha-required"):
            run("lab1", None, "RiftReader2.Live.exe", None, self.archive, 18208, 45)

    def test_guest_script_is_read_only_and_hash_checks_executable(self):
        self.assertIn("snapshot-native", GUEST)
        self.assertIn("native-reader-executable-sha-mismatch", GUEST)
        self.assertIn("Get-FileHash", GUEST)
        for prohibited in ("WriteProcessMemory", "VirtualProtectEx", "SendKeys",
                           "SetForegroundWindow", " /reloadui", " /rr2bind",
                           "Start-Process", "Stop-Process"):
            self.assertNotIn(prohibited, GUEST)


if __name__ == "__main__":
    unittest.main()

