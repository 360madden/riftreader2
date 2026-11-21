"""Offline contract and admission tests for native keyed unit-level candidates."""
from __future__ import annotations

from copy import deepcopy
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import native_unit_level_projection as levels
from scripts import physical_rift

SHA = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
START = "2026-11-21T21:12:00.0000000Z"
END = "2026-11-21T21:12:00.4000000Z"


def report():
    return {
        "schemaVersion": 1,
        "contractVersion": levels.CONTRACT,
        "status": "complete",
        "observation": {
            "identity": {
                "processId": 37676,
                "processStartUtcTicks": 639308565554559088,
                "executableSha256": SHA,
            },
            "startedAtUtc": START,
            "completedAtUtc": END,
            "selfKey": "42", "qualification": levels.QUALIFICATION,
            "rows": [
                {
                    "unitKey": "9223372039438477006",
                    "unitIdCandidate": "u800000009A0026CE",
                    "status": "numeric-level-candidate",
                    "entityAddressDecimal": "2275681213968",
                    "numericLevelCandidate": 10,
                    "levelBranch": "alternate-secondary",
                    "unavailableReason": None,
                    "startedAtUtc": "2026-11-21T21:12:00.0100000Z",
                    "completedAtUtc": "2026-11-21T21:12:00.1100000Z",
                },
                {
                    "unitKey": "9223372039438477007",
                    "unitIdCandidate": "u800000009A0026CF",
                    "status": "unavailable",
                    "entityAddressDecimal": None,
                    "numericLevelCandidate": None,
                    "levelBranch": None,
                    "unavailableReason": "native-component-or-owner-unavailable",
                    "startedAtUtc": "2026-11-21T21:12:00.2000000Z",
                    "completedAtUtc": "2026-11-21T21:12:00.2100000Z",
                },
            ],
        },
    }


class KeyedNativeLevelProjectionTests(unittest.TestCase):
    def test_pinned_level_candidate_and_unknowns(self):
        source = report()
        original = deepcopy(source)
        result = levels.values(source)
        self.assertEqual(result["selfKey"], "42")
        self.assertEqual(result["numericLevelCandidateCount"], 1)
        self.assertEqual(result["rows"][0]["numericLevelCandidate"], 10)
        self.assertEqual(result["rows"][0]["levelBranch"], "alternate-secondary")
        self.assertIsNone(result["rows"][1]["numericLevelCandidate"])
        self.assertEqual(result["combatSuitabilityStatus"], "unqualified")
        self.assertEqual(result["hostilityStatus"], "unavailable")
        self.assertEqual(original, source)

    def test_same_projection_through_physical_wrapper(self):
        self.assertEqual(physical_rift._native_values("unit-levels", report()),
                         levels.values(report()))

    def test_id_owner_and_chronology_tampering_refused(self):
        bad = (
            lambda d: d["observation"]["rows"][0].update(
                unitIdCandidate="u000000009A0026CE"),
            lambda d: d["observation"]["rows"][1].update(
                unitKey=d["observation"]["rows"][0]["unitKey"]),
            lambda d: d["observation"].update(selfKey="00"),
            lambda d: d["observation"]["identity"].update(processId=True),
            lambda d: d["observation"]["rows"][0].update(
                completedAtUtc="2026-11-21T21:11:00.0000000Z"),
            lambda d: d["observation"]["rows"][0].update(
                entityAddressDecimal="12345"),
            lambda d: d["observation"].update(
                qualification="verified-hostility"),
        )
        for change in bad:
            with self.subTest(change=change):
                source = report()
                change(source)
                with self.assertRaises(ValueError):
                    levels.values(source)

    def test_numeric_level_bounds_refused(self):
        for value in (0, 1001, True, None, -1):
            with self.subTest(value=value):
                source = report()
                source["observation"]["rows"][0]["numericLevelCandidate"] = value
                with self.assertRaises(ValueError):
                    levels.values(source)

    def test_unavailable_level_cannot_hide_numeric_or_branch(self):
        for row in ("status", "numericLevelCandidate", "levelBranch"):
            with self.subTest(field=row):
                source = report()
                if row == "status":
                    source["observation"]["rows"][0]["status"] = "unavailable"
                elif row == "numericLevelCandidate":
                    source["observation"]["rows"][1]["numericLevelCandidate"] = 10
                else:
                    source["observation"]["rows"][1]["levelBranch"] = "alternate-primary"
                with self.assertRaises(ValueError):
                    levels.values(source)

    def test_bounded_unit_keys_do_not_launch_native_for_bad_inputs(self):
        with TemporaryDirectory() as temp:
            exe = Path(temp)/"native-reader.exe"
            exe.write_bytes(b"MZ")
            sel = {
                "status":"ready", "ownerHost":"AMD-DESKTOP",
                "target":{"hostName":"AMD-DESKTOP", "processId":37676,
                          "processStartUtcTicks":"639308565554559088",
                          "executableSha256":SHA},
            }
            with patch.object(physical_rift, "NATIVE_EXE", exe), \
                 patch.object(physical_rift.socket, "gethostname",
                              return_value="AMD-DESKTOP"), \
                 patch.object(physical_rift.subprocess, "run") as run:
                for unit_keys in (None, ["0"], ["1"]*13,
                                  [str(i) for i in range(1,14)]):
                    with self.subTest(keys=unit_keys):
                        result = physical_rift.read_native(
                            sel, "unit-levels", Path(temp)/"read.json",
                            unit_keys=unit_keys)
                        self.assertEqual(result["status"], "blocked")
                run.assert_not_called()

    def test_admitted_unit_level_reader_receives_correct_sha_and_decimal_keys(self):
        with TemporaryDirectory() as temp:
            exe = Path(temp)/"native-reader.exe"
            exe.write_bytes(b"MZ")
            sel = {
                "status":"ready", "ownerHost":"AMD-DESKTOP",
                "target":{"hostName":"AMD-DESKTOP", "processId":37676,
                          "processStartUtcTicks":"639308565554559088",
                          "executableSha256":SHA.lower()},
            }
            with patch.object(physical_rift, "NATIVE_EXE", exe), \
                 patch.object(physical_rift.socket, "gethostname",
                              return_value="AMD-DESKTOP"), \
                 patch.object(physical_rift.subprocess, "run",
                              return_value=subprocess.CompletedProcess([],3,"","offline-error")) as run:
                result = physical_rift.read_native(
                    sel,"unit-levels",Path(temp)/"read.json",
                    unit_keys=["9223372039438477006", "9223372039438477007"])
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "native-reader-failed")
                args = run.call_args.args[0]
                self.assertEqual(args[1],"sample-current-unit-levels")
                self.assertEqual(args[args.index("--sha256")+1],SHA)
                self.assertEqual(args[args.index("--keys")+1],
                                 "9223372039438477006,9223372039438477007")


if __name__ == "__main__":
    unittest.main()
