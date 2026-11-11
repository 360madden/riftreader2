"""Offline verification of physical-RIFT player-context value retrieval."""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as physical


QUALIFICATION = "candidate-only; changed-state, API correspondence and restart unverified"
SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
TICKS = 639299470183328173
UNIT = 239816685251645959


def report():
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-player-context-candidate-sample/1",
        "status": "complete",
        "qualification": QUALIFICATION,
        "observation": {
            "identity": {
                "processId": 44888, "processStartUtcTicks": TICKS,
                "executableSha256": SHA,
            },
            "startedAtUtc": "2026-11-11T09:22:03.8267044+00:00",
            "completedAtUtc": "2026-11-11T09:22:03.8343433+00:00",
            "qualification": QUALIFICATION,
            "unitKey": UNIT, "entity": 0x12345000,
            "rawLevel": 45,
            "levelStatus": "numeric-getter-and-presentation-candidate",
            "rawCombat": 0, "combatStatus": "raw-byte-candidate",
            "combatCandidate": False, "rawCalling": 1,
            "callingCandidate": "warrior", "rawFallbackKey": 0,
            "targetStatus": "raw-getter-zero-candidate",
            "targetKeyCandidate": 0, "targetUnitIdCandidate": None,
        },
    }


class PhysicalPlayerContextTests(unittest.TestCase):
    def test_projects_useful_candidates_without_unqualified_pointers(self):
        result = physical._native_values("player-context", report())
        self.assertEqual(str(UNIT), result["unitKey"])
        self.assertEqual(45, result["level"]["rawCandidate"])
        self.assertEqual({"status": "raw-byte-candidate", "rawByte": 0, "candidate": False},
                         result["combat"])
        self.assertEqual({"status": "raw-getter-zero-candidate", "unitIdCandidate": None},
                         result["target"])
        self.assertEqual({"rawCandidate": 1, "nameCandidate": "warrior"}, result["calling"])
        self.assertNotIn("entity", result)
        self.assertNotIn("owner", result)

    def test_target_identity_stays_lossless_and_unavailable_stays_null(self):
        source = report()
        key = 0x80000002CD0034D1
        source["observation"].update(rawFallbackKey=key, targetKeyCandidate=key,
                                     targetStatus="fallback-key-candidate",
                                     targetUnitIdCandidate=f"u{key:016X}")
        result = physical._native_values("player-context", source)
        self.assertEqual("u80000002CD0034D1", result["target"]["unitIdCandidate"])
        source["observation"].update(targetStatus="override-unavailable",
                                     targetKeyCandidate=None, targetUnitIdCandidate=None)
        self.assertIsNone(physical._native_values("player-context", source)["target"]["unitIdCandidate"])

    def test_invalid_identity_shapes_and_candidate_contradictions_rejected(self):
        mutations = (
            lambda r: r.update(contractVersion="some-other-version"),
            lambda r: r["observation"].update(unitKey=True),
            lambda r: r["observation"].update(rawLevel=True),
            lambda r: r["observation"].update(combatCandidate=True),
            lambda r: r["observation"].update(rawCalling=2),
            lambda r: r["observation"].update(targetUnitIdCandidate="u0000000000000001"),
            lambda r: r["observation"].update(completedAtUtc="2026-11-11T09:22:02Z"),
            lambda r: r["observation"].update(startedAtUtc="2026-11-11T09:22:03"),
        )
        for mutate in mutations:
            bad = copy.deepcopy(report())
            mutate(bad)
            with self.subTest(mutate=str(mutate)), self.assertRaises(ValueError):
                physical._native_values("player-context", bad)

    def test_physical_reader_receipt_exposes_projection(self):
        source = report()
        selection = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": {
            "hostName": "AMD-DESKTOP", "processId": 44888,
            "processStartUtcTicks": str(TICKS), "executableSha256": SHA,
        }}
        with TemporaryDirectory() as folder:
            executable = Path(folder) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            output = Path(folder) / "context.json"

            def fake_run(command, **_):
                output.write_text(json.dumps(source), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "recordType": physical.NATIVE_RECEIPTS["player-context"],
                    "status": "complete", "output": str(output),
                }), "")

            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selection, "player-context", output)
            self.assertEqual("complete", result["status"])
            self.assertEqual(str(UNIT), result["nativeValues"]["unitKey"])
            self.assertEqual(45, result["nativeValues"]["level"]["rawCandidate"])
            self.assertIn("candidate-only", result["qualification"])


if __name__ == "__main__":
    unittest.main()
