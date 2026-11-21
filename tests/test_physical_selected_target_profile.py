"""Pure native-selected-target profile tests; no RIFT input or process required."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_selected_target_profile as profile

PID = 37676
KEY = "9223372039438477006"
UNIT = "u800000009A0026CE"
SELF = "239816685251645959"
ENTITY = 2275681213968
XYZ = {"x": 6046.1846, "y": 832.3002, "z": 3125.9717}
PROCESS = {
    "processId": PID, "processStartUtcTicks": "639308565554559088",
    "executableSha256": profile.BUILD_1179,
    "executablePath": r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
    "hostName": "AMD-DESKTOP", "hwnd": 454545,
}
IDENTITY = {k: (int(v) if k == "processStartUtcTicks" else v)
            for k, v in PROCESS.items()
            if k in ("processId", "processStartUtcTicks",
                     "executableSha256", "executablePath")}


def time(index):
    return f"2026-11-21T21:01:{index // 10:02d}.{index % 10}000000+00:00"


def target_doc(start, end, *, state="candidate", key=KEY, entity=ENTITY):
    has = state == "candidate"
    return {
        "observation": {
            "identity": deepcopy(IDENTITY), "selfKey": int(SELF),
            "startedAtUtc": time(start), "completedAtUtc": time(end),
            "targetEntity": entity if has else None,
            "targetKey": int(key) if has else None,
            "targetUnitId": (f"u{int(key):016X}" if has else None),
        },
        "fakeProjection": {
            "status": state, "selfUnitKey": SELF,
            "unitKey": key if has else None,
            "unitId": f"u{int(key):016X}" if has else None,
            "numericLevelCandidate": 10 if has else None,
            "health": ({"status": "calculated-candidate", "current": 522,
                        "maximum": 522, "unavailableReason": None} if has else None),
            "energy": ({"status": "calculated-candidate", "current": 100,
                        "maximum": 100, "unavailableReason": None} if has else None),
            "positionCandidate": deepcopy(XYZ) if has else None,
        },
    }


def position_doc():
    rows = []
    for start, end in ((2, 3), (4, 5)):
        rows.append({
            "identity": deepcopy(IDENTITY),
            "startedAtUtc": time(start), "completedAtUtc": time(end),
            "targetEntityDecimal": str(ENTITY),
        })
    values = [{
        "status": "position-candidate", "selfKey": SELF, "targetKey": KEY,
        "rawFallbackKey": KEY, "targetPositionXYZCandidate": deepcopy(XYZ)
    } for _ in rows]
    for row, value in zip(rows, values):
        row["fakeProjection"] = deepcopy(value)
    return {
        "identity": deepcopy(IDENTITY),
        "requestedSamples": 2, "completedSamples": 2,
        "observation": deepcopy(rows[-1]),
        "observations": rows,
        "fakeProjection": values[-1],
        "fakeBurst": values,
    }


def name_doc():
    return {"observation": {"identity": deepcopy(IDENTITY),
                            "startedAtUtc": time(6),
                            "completedAtUtc": time(7)},
            "fakeProjection": {
                "selfKey": SELF, "rows": [{
                    "unitKey": KEY, "entityAddressDecimal": str(ENTITY),
                    "status": "available-candidate",
                    "baseNameCandidate": "Argent Glade Guard",
                }],
            }}


class SelectedTargetProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "candidate"
        self.docs = [target_doc(0, 1), position_doc(),
                     name_doc(), target_doc(8, 9)]
        self.calls = []
        self.selections = []

    def choose(self, host, pid):
        self.selections.append((host, pid))
        return {"ownerHost": host, "status": "ready",
                "target": deepcopy(PROCESS)}

    def read(self, selection, kind, *, output, samples=None,
             interval_ms=None, unit_keys=None):
        i = len(self.calls)
        self.calls.append((kind, samples, interval_ms, unit_keys))
        source = self.docs[i]
        output = Path(output)
        raw = json.dumps(source, separators=(",", ":")).encode()
        output.write_bytes(raw)
        return {
            "status": "complete", "nativeRead": kind,
            "nativeOutput": str(output), "target": deepcopy(PROCESS),
            "nativeSourceSha256": hashlib.sha256(raw).hexdigest().upper(),
            "nativeValues": deepcopy(source["fakeProjection"]),
            **({"nativeBurstValues": deepcopy(source["fakeBurst"])}
               if kind == "selected-position" else {}),
        }

    def execute(self):
        with patch.object(profile.physical_rift, "_native_values",
                          side_effect=lambda kind, document:
                          deepcopy(document["fakeProjection"])):
            return profile.capture("AMD-DESKTOP", PID, self.output,
                                   select=self.choose, read=self.read)

    def test_four_source_native_profile_candidate(self):
        path, result = self.execute()
        self.assertTrue(path.is_file())
        self.assertEqual(result["status"], "selected-target-candidate")
        self.assertEqual(result["selectedUnitIdCandidate"], UNIT)
        self.assertEqual(result["baseNameCandidate"], "Argent Glade Guard")
        self.assertEqual(result["targetLevelCandidate"], 10)
        self.assertEqual(result["healthCandidate"]["current"], 522)
        self.assertEqual(result["positionAgreement"], "within-0.10-native-units")
        self.assertEqual(len(result["nativeSourcesSha256"]), 4)
        self.assertEqual(self.calls, [
            ("selected-target", None, None, None),
            ("selected-position", 2, 100, None),
            ("unit-names", None, None, [KEY]),
            ("selected-target", None, None, None),
        ])
        self.assertEqual(len(self.selections), 2)
        self.assertFalse(result["gameplayInputSent"])
        self.assertEqual(result["hostilityStatus"], "unqualified")
        self.assertEqual(result, json.loads(path.read_text(encoding="utf-8")))

    def test_no_target_baseline_skips_position_and_name_reads(self):
        self.docs = [target_doc(0, 1, state="unavailable"),
                     target_doc(8, 9, state="unavailable")]
        path, result = self.execute()
        self.assertTrue(path.is_file())
        self.assertEqual(result["status"], "no-target-baseline-candidate")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result["selectedUnitIdCandidate"], None)
        self.assertEqual(set(result["nativeSourcesSha256"]),
                         {"selectedBefore", "selectedAfter"})
        self.assertFalse((self.output / "unit-name.json").exists())

    def test_target_change_between_native_reads_aborts_and_keeps_sources(self):
        self.docs[-1] = target_doc(8, 9, key=str(int(KEY) + 1))
        with self.assertRaisesRegex(ValueError, "selected-unit-or-entity-changed"):
            self.execute()
        self.assertTrue((self.output/"failure.json").is_file())
        self.assertFalse((self.output/"profile.json").exists())
        self.assertEqual(len(self.calls), 4)

    def test_name_entity_change_withholds_name(self):
        self.docs[2]["fakeProjection"]["rows"][0]["entityAddressDecimal"] = "999999999"
        _, result = self.execute()
        self.assertIsNone(result["baseNameCandidate"])
        self.assertEqual(result["nameStatus"], "entity-mismatch-unavailable")
        self.assertEqual(result["targetLevelCandidate"], 10)

    def test_selected_position_drift_withholds_xyz(self):
        self.docs[1]["fakeBurst"][-1]["targetPositionXYZCandidate"]["x"] += 3.5
        self.docs[1]["fakeProjection"] = self.docs[1]["fakeBurst"][-1]
        _, result = self.execute()
        self.assertEqual(result["positionAgreement"], "moved-or-disagreed")
        self.assertIsNone(result["positionXYZCandidate"])
        self.assertGreater(result["maxSequentialPositionDelta"], 3.0)

    def test_changed_selected_position_key_fails(self):
        self.docs[1]["fakeBurst"][0]["targetKey"] = "99"
        with self.assertRaisesRegex(ValueError, "selected-position-identity-changed"):
            self.execute()

    def test_changed_level_withholds_level(self):
        self.docs[-1]["fakeProjection"]["numericLevelCandidate"] = 11
        _, result = self.execute()
        self.assertEqual(result["levelAgreement"], "unavailable-or-changed")
        self.assertIsNone(result["targetLevelCandidate"])

    def test_bad_native_sha_receipt_fails_before_next_read(self):
        original = self.read
        def malformed(selection, kind, **kwargs):
            result = original(selection, kind, **kwargs)
            result["nativeSourceSha256"] = "0"*64
            return result
        with patch.object(profile.physical_rift, "_native_values",
                          side_effect=lambda _, document:
                          deepcopy(document["fakeProjection"])):
            with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                profile.capture("AMD-DESKTOP", PID, self.output,
                                select=self.choose, read=malformed)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue((self.output / "failure.json").exists())

    def test_bad_order_or_capture_span_refused(self):
        self.docs[2]["observation"]["startedAtUtc"] = time(1)
        with self.assertRaisesRegex(ValueError, "nonsequential-native-evidence"):
            self.execute()

    def test_changed_process_after_reads_refused(self):
        def changed(host, pid):
            return self.choose(host, pid) if len(self.selections) == 0 else {
                "status": "ready", "target": dict(PROCESS, processId=999)}
        with patch.object(profile.physical_rift, "_native_values",
                          side_effect=lambda _, document:
                          deepcopy(document["fakeProjection"])):
            with self.assertRaisesRegex(ValueError, "physical-process-changed"):
                profile.capture("AMD-DESKTOP", PID, self.output,
                                select=changed, read=self.read)

    def test_existing_output_directory_and_wrong_pid_rejected_without_reads(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "output-directory-must-be-new"):
            self.execute()
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, "invalid-expected-host-or-pid"):
            profile.capture("AMD-DESKTOP", True, self.output,
                            select=self.choose, read=self.read)

    def test_unqualified_process_build_refused_before_source_creation(self):
        def wrong(host, pid):
            return {"status": "ready",
                    "target": dict(PROCESS, executableSha256="0"*64)}
        with self.assertRaisesRegex(ValueError, "physical-1179-process-unavailable"):
            profile.capture("AMD-DESKTOP", PID, self.output,
                            select=wrong, read=self.read)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
