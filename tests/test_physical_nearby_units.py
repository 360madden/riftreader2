"""Offline and injected-reader checks for the physical nearby native CLI."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_nearby_units as near
from scripts.native_unit_level_projection import values as level_projection
from scripts.join_physical_nearby_npc_survey import original_native_nearby
from tests.test_native_unit_level_projection import report as level_report

SHA = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
TIMES = ["2026-11-21T17:25:59.0000000+00:00",
         "2026-11-21T17:26:00.0000000+00:00"]
PROCESS = {
    "processId": 37676, "processStartUtcTicks": "639308565554559088",
    "executableSha256": SHA,
    "executablePath": r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
    "hostName": "AMD-DESKTOP", "hwnd": 991,
}


def synthetic():
    identity = {
        "processId": 37676, "processStartUtcTicks": 639308565554559088,
        "executableSha256": SHA,
        "executablePath": PROCESS["executablePath"],
    }
    original_rows = [
        {"unitKey": "43", "entityAddressDecimal": "200000000"},
        {"unitKey": "44", "entityAddressDecimal": "200000512"},
    ]
    pos_raw = {"observation": {
        "identity": identity, "selfKey": "42",
        "startedAtUtc": TIMES[0],
        "completedAtUtc": TIMES[0],
        "selfPositionCandidate": {"x": 100.0, "y": 10.0, "z": 50.0},
        "rows": original_rows,
    }}
    rows = [
        {"unitKey": "43", "unitIdCandidate": "u000000000000002B",
         "horizontalDistanceCandidate": 2.5,
         "positionXYZCandidate": {"x": 101.5, "y": 10.5, "z": 52.0},
         "screenPointCandidate": {"status": "available-candidate"}},
        {"unitKey": "44", "unitIdCandidate": "u000000000000002C",
         "horizontalDistanceCandidate": 18.0,
         "positionXYZCandidate": {"x": 118.0, "y": 10.0, "z": 50.0},
         "screenPointCandidate": {"status": "unavailable"}},
    ]
    position_values = {
        "selfKey": "42", "units": rows, "unitsExamined": 5,
        "positionsFound": 2, "worldCoverage": "bounded-unit-manager-subset",
    }
    name_raw = {"observation": {
        "identity": deepcopy(identity), "startedAtUtc": TIMES[1],
        "completedAtUtc": TIMES[1],
    }}
    name_values = {
        "selfKey": "42", "rows": [
            {"unitKey": "43", "entityAddressDecimal": "200000000",
             "status": "available-candidate",
             "baseNameCandidate": "Sample Guard", "reason": None},
            {"unitKey": "44", "entityAddressDecimal": "200000512",
             "status": "unavailable",
             "baseNameCandidate": None, "reason": "cache-miss"},
        ],
    }
    return pos_raw, position_values, name_raw, name_values


class NearbyUnitTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dest = Path(self.directory.name) / "new-capture"
        self.docs = synthetic()
        self.level_doc = level_report()
        level = self.level_doc["observation"]
        level["identity"] = deepcopy(self.docs[0]["observation"]["identity"])
        captured_at = "2026-11-21T17:26:01.0000000Z"
        level.update(startedAtUtc=captured_at, completedAtUtc=captured_at)
        for row, key in zip(level["rows"], ("43", "44")):
            row.update(unitKey=key, unitIdCandidate=f"u{int(key):016X}",
                       startedAtUtc=captured_at, completedAtUtc=captured_at)
        level["rows"][0]["entityAddressDecimal"] = "200000000"
        self.selections = []
        self.reads = []
        self.readers = []

    def choose(self, host, pid):
        self.selections.append((host, pid))
        return {"status": "ready", "target": deepcopy(PROCESS),
                "ownerHost": "AMD-DESKTOP"}

    def read(self, selection, kind, *, output, unit_limit=None,
             unit_keys=None, native_reader=None):
        self.reads.append((kind, unit_limit, unit_keys))
        self.readers.append(native_reader)
        if kind == "unit-levels":
            raw, values = self.level_doc, level_projection(self.level_doc)
        else:
            raw, values = self.docs[:2] if kind == "unit-positions" else self.docs[2:]
        raw = deepcopy(raw)
        raw["observation"]["identity"] = deepcopy(self.docs[0]["observation"]["identity"])
        content = json.dumps(raw, separators=(",", ":")).encode()
        Path(output).write_bytes(content)
        return {"status": "complete", "nativeRead": kind,
                "nativeOutput": str(output),
                "nativeSourceSha256": hashlib.sha256(content).hexdigest().upper(),
                "nativeValues": deepcopy(values),
                "target": deepcopy(selection["target"])}

    def invoke(self, **kwargs):
        with patch.object(near.physical_rift, "_native_values",
                          side_effect=self.project):
            return near.capture("AMD-DESKTOP", 37676, self.dest,
                                choose=self.choose, read=self.read, **kwargs)

    def project(self, kind, document):
        if kind == "unit-levels":
            return level_projection(document)
        return deepcopy(self.docs[1] if kind == "unit-positions" else self.docs[3])

    def test_bounded_native_position_and_name_candidates(self):
        path, report = self.invoke()
        self.assertTrue(path.is_file())
        self.assertEqual(report["status"], "nearby-unit-candidates")
        self.assertEqual(self.selections,
                         [("AMD-DESKTOP", 37676), ("AMD-DESKTOP", 37676)])
        self.assertEqual(self.reads,
                         [("unit-positions", 512, None),
                          ("unit-names", None, ["43", "44"])])
        self.assertEqual(report["namedCandidateCount"], 1)
        self.assertEqual(report["totalNearbyPositionCandidates"], 2)
        self.assertEqual(report["samples"][0]["nameCandidate"], "Sample Guard")
        self.assertEqual(report["samples"][0]["heightDeltaCandidate"], 0.5)
        self.assertEqual(report["samples"][1]["nameUnavailableReason"], "cache-miss")
        self.assertEqual(report["samples"][0]["combatSuitabilityStatus"], "unqualified")
        self.assertFalse(report["inputSent"])
        self.assertTrue(all(len(sha) == 64 for sha in report["sourceSha256"].values()))
        self.assertEqual(json.loads(path.read_text())["samples"], report["samples"])

    def test_levels_are_bound_to_entities_and_replayed_from_original(self):
        published = self.dest.parent / "RiftReader2.Live.exe"
        published.touch()
        path, report = self.invoke(include_levels=True, native_reader=published)
        self.assertEqual(self.readers, [published] * 3)
        self.assertEqual(self.reads[-1], ("unit-levels", None, ["43", "44"]))
        self.assertEqual(report["numericLevelCandidateCount"], 1)
        self.assertEqual(report["samples"][0]["numericLevelCandidate"], 10)
        self.assertIsNone(report["samples"][1]["numericLevelCandidate"])
        self.assertEqual(report["samples"][0]["combatSuitabilityStatus"], "unqualified")
        with patch.object(near.physical_rift, "_native_values", side_effect=self.project):
            rebuilt, _, _ = original_native_nearby(path)
            self.assertEqual(rebuilt, report)
            (self.dest / "unit-levels-native.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "level-source-sha-mismatch"):
                original_native_nearby(path)

    def test_level_entity_change_withholds_level(self):
        self.level_doc["observation"]["rows"][0]["entityAddressDecimal"] = "200000512"
        _, report = self.invoke(include_levels=True)
        self.assertEqual(report["numericLevelCandidateCount"], 0)
        self.assertIsNone(report["samples"][0]["numericLevelCandidate"])
        self.assertEqual(report["samples"][0]["levelUnavailableReason"], "entity-changed-between-reads")

    def test_level_batch_is_bounded_and_prioritizes_named_units(self):
        samples = [{"unitKey": str(key), "nameStatus": "unavailable" if key < 6
                    else "available-candidate"} for key in range(1, 19)]
        self.assertEqual(near.level_batch_keys(samples), [str(key) for key in range(6, 18)])

    def test_level_reader_time_must_follow_names_within_window(self):
        level = self.level_doc["observation"]
        late = "2026-11-21T17:26:30.0000000Z"
        level.update(startedAtUtc=late, completedAtUtc=late)
        for row in level["rows"]:
            row.update(startedAtUtc=late, completedAtUtc=late)
        with self.assertRaisesRegex(ValueError, "level-source-outside-capture-window"):
            self.invoke(include_levels=True)

    def test_entity_change_withholds_name_instead_of_reusing_old_identity(self):
        p, v, n, nv = self.docs
        nv["rows"][0]["entityAddressDecimal"] = "300000000"
        path, report = self.invoke()
        self.assertIsNone(report["samples"][0]["nameCandidate"])
        self.assertEqual(report["samples"][0]["nameUnavailableReason"],
                         "entity-changed-between-reads")
        self.assertEqual(report["namedCandidateCount"], 0)
        self.assertTrue(path.is_file())

    def test_name_self_identity_change_fails_closed_and_preserves_original(self):
        self.docs[3]["selfKey"] = "99"
        with self.assertRaisesRegex(ValueError, "position-name-owner-changed"):
            self.invoke()
        self.assertTrue((self.dest / "unit-positions-native.json").is_file())
        self.assertTrue((self.dest / "unit-names-native.json").is_file())
        self.assertTrue((self.dest / "failure.json").is_file())
        self.assertFalse((self.dest / "nearby-report.json").exists())

    def test_reversed_name_sample_time_refuses(self):
        self.docs[2]["observation"]["startedAtUtc"] = "2026-11-20T12:00:00Z"
        with self.assertRaisesRegex(ValueError, "position-name-time-order-reversed"):
            self.invoke()

    def test_original_sha_mismatch_is_not_admitted(self):
        def altered_receipt(*args, **kwargs):
            receipt = self.read(*args, **kwargs)
            receipt["nativeSourceSha256"] = "0" * 64
            return receipt

        with patch.object(near.physical_rift, "_native_values",
                          return_value=self.docs[1]):
            with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                near.capture("AMD-DESKTOP", 37676, self.dest,
                             choose=self.choose, read=altered_receipt)
        self.assertEqual(len(self.reads), 1)
        self.assertTrue((self.dest / "failure.json").is_file())

    def test_explicit_wrong_process_or_missing_output_dir_blocks_before_reads(self):
        for host, pid in (("LEGION", 0), ("other/path", 37676),
                          ("AMD-DESKTOP", True)):
            with self.subTest(host=host, pid=pid):
                with self.assertRaisesRegex(ValueError, "invalid-explicit-host-or-pid"):
                    self.invoke_wrong(host, pid)
        with self.assertRaisesRegex(ValueError, "physical-process-unavailable"):
            self.invoke_wrong("OTHER-PC", 37676)
        self.assertEqual(self.reads, [])
        self.assertFalse(self.dest.exists())
        self.dest.mkdir()
        with self.assertRaisesRegex(ValueError, "output-must-be-new"):
            self.invoke()
        self.assertEqual(self.reads, [])

    def invoke_wrong(self, host, pid):
        return near.capture(host, pid, self.dest,
                            choose=self.choose, read=self.read)

    def test_radius_limit_refusal_and_empty_nearby_result(self):
        for values in ({"radius": -1}, {"radius": 500},
                       {"limit": 33}, {"limit": True}):
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, "invalid-radius-or-limit"):
                    self.invoke(**values)
                self.assertFalse(self.dest.exists())
        path, report = self.invoke(radius=1.0)
        self.assertTrue(path.is_file())
        self.assertEqual(report["status"], "no-nearby-position-candidates")
        self.assertEqual(report["samples"], [])
        self.assertEqual(report["sourceSha256"]["unitNames"], None)
        self.assertEqual(len(self.reads), 1)
        self.assertFalse((self.dest / "unit-names-native.json").exists())
        self.assertFalse((self.dest / "failure.json").exists())

    def test_source_receipt_process_change_cannot_be_promoted(self):
        selection = {"status": "ready", "target": deepcopy(PROCESS)}
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.json"
            original, values, _, _ = self.docs
            raw = deepcopy(original)
            raw["observation"]["identity"]["processId"] = 4
            data = json.dumps(raw).encode()
            path.write_bytes(data)
            receipt = {"status": "complete", "nativeRead": "unit-positions",
                       "nativeOutput": str(path), "target": deepcopy(PROCESS),
                       "nativeValues": values,
                       "nativeSourceSha256": hashlib.sha256(data).hexdigest().upper()}
            with self.assertRaisesRegex(ValueError, "source-process-identity-mismatch"):
                near.source_from_receipt(receipt, path, selection, "unit-positions")

    def test_cli_prints_summary_without_unsafe_read(self):
        report = {"status": "nearby-unit-candidates",
                  "totalNearbyPositionCandidates": 3,
                  "namedCandidateCount": 2, "samples": [0, 1],
                  "inputSent": False}
        with patch.object(near, "capture", return_value=(
                self.dest / "nearby-report.json", report)) as run, \
                redirect_stdout(StringIO()) as printed:
            result = near.main(["--expected-host", "AMD-DESKTOP",
                                "--physical-pid", "37676",
                                "--output-dir", str(self.dest)])
        self.assertEqual(result, 0)
        parsed = json.loads(printed.getvalue())
        self.assertEqual(parsed["namedCandidates"], 2)
        self.assertFalse(parsed["inputSent"])
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
