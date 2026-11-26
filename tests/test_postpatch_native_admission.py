"""Offline admission checks for physical RIFT build 1179 native reads.

No game process, window, controller, or real native reader is contacted.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_rift
from tests.test_sample_current_native_selected_target import report as selected_fixture


BUILD_1179 = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
HISTORICAL_BUILD = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"


def selection(sha=BUILD_1179):
    return {
        "status": "ready",
        "ownerHost": "AMD-DESKTOP",
        "target": {
            "hostName": "AMD-DESKTOP",
            "processId": 12345,
            "processStartUtcTicks": "638000000000000001",
            "executableSha256": sha,
        },
    }


class PostpatchNativeAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        executable = self.folder / "offline-native-reader.exe"
        executable.write_bytes(b"MZ")
        for obj, name, value in (
            (physical_rift, "NATIVE_EXE", executable),
            # Keep this offline fixture independent of the actual host's reader
            # registration and RR2_NATIVE_READER override. The fake executable
            # exercises admission/argument assembly, not tool discovery.
            (physical_rift, "_configured_native_reader_path", lambda override: None),
            (physical_rift.socket, "gethostname", lambda: "AMD-DESKTOP"),
        ):
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_unqualified_fields_are_refused_before_native_launch(self):
        # Old-build research is not an implicit qualification for build 1179.
        for kind in (
            "smoothed-scalar",
        ):
            with self.subTest(kind=kind), patch.object(physical_rift.subprocess, "run") as run:
                result = physical_rift.read_native(
                    selection(), kind, self.folder / (kind + ".json"),
                    unit_keys=["1"] if kind == "unit-names" else None,
                )
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "postpatch-native-read-unqualified")
                run.assert_not_called()

    def test_facing_target_passes_explicit_build_and_include_flag(self):
        with patch.object(physical_rift.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 3, "", "offline-refusal")) as run:
            result = physical_rift.read_native(
                selection(), "facing", self.folder / "target.json", include_target=True,
            )
            self.assertEqual(result["reason"], "native-reader-failed")
            args = run.call_args.args[0]
            self.assertEqual(args[args.index("--sha256") + 1], BUILD_1179)
            self.assertEqual(args[args.index("--include-target") + 1], "true")

    def test_admitted_kinds_pass_the_exact_sha_to_native_reader(self):
        # A synthetic nonzero native exit proves command assembly, not live semantics.
        for kind in ("position", "facing", "actor-pose", "orientation", "unit-positions", "selected-position", "selected-target", "vitals", "player-context", "stats", "zone-context", "target-name", "unit-names"):
            with self.subTest(kind=kind), patch.object(
                physical_rift.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 3, "", "offline-refusal"),
            ) as run:
                result = physical_rift.read_native(
                    selection(BUILD_1179.lower()), kind, self.folder / (kind + ".json"),
                    unit_keys=["1"] if kind == "unit-names" else None,
                )
                self.assertEqual(result["reason"], "native-reader-failed")
                args = run.call_args.args[0]
                self.assertEqual(args[1], physical_rift.NATIVE_READS[kind])
                self.assertEqual(args[2:6], [
                    "--pid", "12345", "--start-ticks", "638000000000000001",
                ])
                self.assertEqual(args.count("--sha256"), 1)
                self.assertEqual(args[args.index("--sha256") + 1], BUILD_1179)
                if kind == "selected-target":
                    for option in ("--include-name-seed", "--include-position",
                                   "--include-context"):
                        self.assertEqual(args[args.index(option) + 1], "true")

    def test_postpatch_selected_target_projection_retains_exact_keys_and_candidate_levels(self):
        source = selected_fixture()
        owner = source["observation"]
        owner["identity"]["executableSha256"] = BUILD_1179
        owner["targetVitals"]["identity"]["executableSha256"] = BUILD_1179
        owner["targetVitals"]["health"].update(
            status="calculated-candidate", current=522, maximum=522,
            unavailableReason=None)
        owner["targetContext"].update(
            status="raw-typed-candidate", owner=0x20080000,
            rawLevel=0, rawCombat=0, combatCandidate=False,
            levelStatus="numeric-getter-candidate",
            levelBranch="alternate-secondary", numericLevelCandidate=10)
        values = physical_rift._native_values("selected-target", source)
        self.assertEqual(values["unitId"], owner["targetUnitId"])
        self.assertEqual(values["unitKey"], str(owner["targetKey"]))
        self.assertEqual(values["numericLevelCandidate"], 10)
        self.assertEqual(values["health"]["current"], 522)
        self.assertFalse(values["combatCandidate"])
        self.assertEqual(values["status"], "candidate")
        self.assertIsNone(physical_rift._native_values("selected-target", selected_fixture()))
        owner["targetKey"] += 1
        with self.assertRaisesRegex(ValueError, "invalid selected-target report"):
            physical_rift._native_values("selected-target", source)

    def test_postpatch_target_name_accepts_only_explicit_raw_only_dictionary_refusal(self):
        identity = {
            "processId": 12345,
            "processStartUtcTicks": 638000000000000001,
            "executableSha256": BUILD_1179,
        }
        row = {
            "identity": identity,
            "startedAtUtc": "2026-11-18T13:00:00+00:00",
            "completedAtUtc": "2026-11-18T13:00:01+00:00",
            "selfKey": 1, "targetKey": 2,
            "targetEntity": 65536, "collection": 65544,
            "templateKey": 7, "selector": 1, "tlsIndex": 0,
            "localizationMode": 1, "formattingFlag": 0,
            "status": "raw-candidate", "recordAddress": 65552,
            "localizationKey": 42, "fallbackText": "Acolyte",
            "dictionary": None, "dictionaryStatus": "not-acquired-raw-only",
            "qualification": "cache-only raw candidate; name publication, freshness and restart unverified",
        }
        report = {
            "schemaVersion": 1,
            "contractVersion": "native-target-template-name-candidate/1",
            "status": "complete", "observation": row,
        }
        values = physical_rift._native_values("target-name", report)
        self.assertEqual(values["status"], "available-candidate")
        self.assertEqual(values["rawFallbackNameCandidate"], "Acolyte")
        self.assertEqual(values["selectedBaseNameCandidate"], "Acolyte")
        self.assertEqual(values["localizationKey"], 42)
        self.assertIn("cache-only", values["qualification"])
        for wrong_marker in (None, "dictionary-loaded"):
            with self.subTest(marker=wrong_marker):
                row["dictionaryStatus"] = wrong_marker
                with self.assertRaises(ValueError):
                    physical_rift._native_values("target-name", report)
        row["dictionaryStatus"] = "not-acquired-raw-only"
        row["dictionary"] = {}
        with self.assertRaises(ValueError):
            physical_rift._native_values("target-name", report)

    def test_historical_build_does_not_inherit_new_build_admission(self):
        # Historical invocation may still be attempted, but is independently
        # subject to the native reader's own exact-build checks.
        with patch.object(
            physical_rift.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 3, "", "offline-refusal"),
        ) as run:
            result = physical_rift.read_native(
                selection(HISTORICAL_BUILD), "vitals", self.folder / "historical.json",
            )
            self.assertEqual(result["reason"], "native-reader-failed")
            self.assertNotIn("--sha256", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
