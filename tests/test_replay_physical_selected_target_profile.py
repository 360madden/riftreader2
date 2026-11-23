"""Offline original-byte replay checks for physical selected-target profiles."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
from shutil import copytree
import unittest
from unittest.mock import patch

from scripts import physical_selected_target_profile as profile
from scripts import replay_physical_selected_target_profile as replay
from tests import test_physical_selected_target_profile as fixture_module
from tests.test_native_unit_level_projection import report as keyed_level_report


class TargetProfileReplayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.SelectedTargetProfileTests(
            methodName="test_four_source_native_profile_candidate")
        self.fixture.setUp()
        self.addCleanup(self.fixture.temp.cleanup)

    @staticmethod
    def decode(kind, raw):
        return deepcopy(raw.get("fakeProjection",
                                raw.get("observation", {}).get("fakeProjection")))

    def generate(self):
        with patch.object(profile.physical_rift, "_native_values",
                          side_effect=self.decode):
            return self.fixture.execute()

    def check(self, path, **options):
        with patch.object(replay.physical_rift, "_native_values",
                          side_effect=self.decode):
            return replay.replay(path, **options)

    def keyed_source(self, *, started=10, entity=fixture_module.ENTITY, **observation):
        report = keyed_level_report()
        row = report["observation"]["rows"][0]
        start, end = fixture_module.time(started), fixture_module.time(started + 1)
        row.update(startedAtUtc=start, completedAtUtc=end, entityAddressDecimal=str(entity))
        report["observation"].update(identity=deepcopy(fixture_module.IDENTITY),
                                     selfKey=fixture_module.SELF,
                                     startedAtUtc=start, completedAtUtc=end, rows=[row])
        report["observation"].update(observation)
        return report

    def pin_keyed(self, source):
        path = self.fixture.output / "keyed-level.json"
        raw = json.dumps(source).encode("utf-8")
        path.write_bytes(raw)
        return {"keyed_levels": path, "keyed_levels_sha256": hashlib.sha256(raw).hexdigest()}

    def mutate(self, file, mutate, update_profile_sha=False):
        path = self.fixture.output / file
        source = json.loads(path.read_text(encoding="utf-8"))
        mutate(source)
        path.write_text(json.dumps(source, separators=(",", ":")), encoding="utf-8")
        if update_profile_sha:
            report = self.fixture.output / "profile.json"
            record = json.loads(report.read_text(encoding="utf-8"))
            key = {
                "selected-before.json": "selectedBefore",
                "selected-position.json": "selectedPosition",
                "unit-name.json": "unitName",
                "selected-after.json": "selectedAfter",
            }[file]
            record["nativeSourcesSha256"][key] = hashlib.sha256(
                path.read_bytes()).hexdigest().upper()
            report.write_text(json.dumps(record), encoding="utf-8")

    def test_actual_source_files_are_independently_reopened_and_checked(self):
        path, profile_data = self.generate()
        verification = self.check(path)
        self.assertEqual(verification["status"], "source-replayed-candidate")
        self.assertEqual(verification["sourceCount"], 4)
        self.assertEqual(verification["selectedUnitIdCandidate"],
                         profile_data["selectedUnitIdCandidate"])
        self.assertEqual(verification["baseNameCandidate"], "Argent Glade Guard")
        self.assertEqual(verification["targetLevelCandidate"], 10)
        self.assertEqual(verification["healthCandidate"]["current"], 522)
        self.assertFalse(verification["inputSent"])

    def test_keyed_level_replays_matching_and_different_native_candidates(self):
        path, _ = self.generate()
        for value, status in ((10, "matching-native-level-candidates"),
                              (11, "different-native-level-candidates")):
            with self.subTest(value=value):
                source = self.keyed_source()
                source["observation"]["rows"][0]["numericLevelCandidate"] = value
                pinned = self.pin_keyed(source)
                result = self.check(path, **pinned)["keyedLevelComparison"]
                self.assertEqual(result["status"], status)
                self.assertEqual(result["keyedLevelCandidate"], value)
                self.assertEqual(result["keyedSourceSha256"], pinned["keyed_levels_sha256"].upper())

    def test_keyed_level_refuses_changed_entity_owner_or_comparison_window(self):
        path, _ = self.generate()
        cases = {
            "entity-mismatch": self.keyed_source(entity=fixture_module.ENTITY + 8),
            "owner-mismatch": self.keyed_source(selfKey="123"),
            "outside-comparison-window": self.keyed_source(started=300),
        }
        for reason, source in cases.items():
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                self.check(path, **self.pin_keyed(source))
        pinned = self.pin_keyed(self.keyed_source())
        pinned["keyed_levels"].write_bytes(pinned["keyed_levels"].read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "keyed-level-source-sha-mismatch"):
            self.check(path, **pinned)

    def test_changed_original_selected_target_is_not_replayed(self):
        path, _ = self.generate()
        self.mutate("selected-after.json", lambda d:
                    d["observation"].update(targetKey=43))
        with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
            self.check(path)

    def test_a_copied_bundle_replays_its_own_sources(self):
        path, _ = self.generate()
        moved = copytree(path.parent, path.parent.parent / "copied-profile") / path.name
        self.assertEqual(self.check(moved)["status"], "source-replayed-candidate")

    def test_copied_bundle_accepts_windows_source_metadata_on_posix(self):
        path, _ = self.generate()
        record = json.loads(path.read_text(encoding="utf-8"))
        recorded_path = r"X:\Original Windows Checkout\selected-position.json"
        record["sourcePaths"]["selectedPosition"] = recorded_path
        path.write_text(json.dumps(record), encoding="utf-8")

        def analysis_path(value):
            return PurePosixPath(value) if value == recorded_path else Path(value)

        with patch.object(replay, "Path", side_effect=analysis_path):
            result = self.check(path)
        self.assertEqual(result["status"], "source-replayed-candidate")
        self.assertEqual(result["sourceCount"], 4)

    def test_another_player_name_source_is_refused(self):
        path, _ = self.generate()
        self.mutate("unit-name.json", lambda d: d["fakeProjection"].update(selfKey="123"),
                    update_profile_sha=True)
        with self.assertRaisesRegex(ValueError, "name-owner-mismatch"):
            self.check(path)

    def test_changed_original_name_does_not_preserve_name(self):
        path, _ = self.generate()
        self.mutate("unit-name.json", lambda d:
                    d["fakeProjection"]["rows"][0].update(
                        baseNameCandidate="Invented"), update_profile_sha=True)
        with self.assertRaisesRegex(ValueError,
                                     "summary-field-conflict-baseNameCandidate"):
            self.check(path)

    def test_modified_profile_level_cannot_be_source_replayed(self):
        path, _ = self.generate()
        data = json.loads(path.read_text())
        data["targetLevelCandidate"] = 100
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,
                                     "summary-field-conflict-targetLevelCandidate"):
            self.check(path)

    def test_profile_source_path_cannot_escape_bundle(self):
        path, _ = self.generate()
        data = json.loads(path.read_text())
        data["sourcePaths"]["unitName"] = str(
            self.fixture.output.parent / "foreign-unit-name.json")
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "source-path-or-sha-invalid"):
            self.check(path)

    def test_entire_source_bundle_has_exact_owner(self):
        path, _ = self.generate()
        self.mutate("selected-after.json", lambda d:
                    d["observation"]["identity"].update(processId=123),
                    update_profile_sha=True)
        with self.assertRaisesRegex(ValueError, "source-owner-changed"):
            self.check(path)

    def test_changed_selected_unit_even_with_updated_sha_is_refused(self):
        path, _ = self.generate()
        self.mutate("selected-after.json", lambda d:
                    d["observation"].update(
                        targetKey=int(d["observation"]["targetKey"])+1),
                    update_profile_sha=True)
        with self.assertRaisesRegex(ValueError, "selected-unit-or-entity-changed"):
            self.check(path)

    def test_no_target_baseline_replays_only_two_sources(self):
        self.fixture.docs = [
            fixture_module.target_doc(0, 1, state="unavailable"),
            fixture_module.target_doc(8, 9, state="unavailable")
        ]
        path, _ = self.generate()
        verified = self.check(path)
        self.assertEqual(verified["sourceCount"], 2)
        self.assertIsNone(verified["selectedUnitIdCandidate"])
        self.assertEqual(verified["profileStatus"], "no-target-baseline-candidate")

    def test_burst_time_reorder_aborts(self):
        path, _ = self.generate()
        self.mutate("selected-position.json",
                    lambda d: d["observations"][0].update(
                        startedAtUtc="2026-11-21T21:00:00.0000000Z"),
                    update_profile_sha=True)
        with self.assertRaises(ValueError):
            self.check(path)

    def test_source_report_symlink_never_followed(self):
        path, _ = self.generate()
        name = self.fixture.output/"unit-name.json"
        copy = self.fixture.output.parent/"name-copy.json"
        copy.write_bytes(name.read_bytes())
        try:
            name.unlink()
            name.symlink_to(copy)
        except OSError:
            self.skipTest("Symlink creation not supported by current test runtime")
        with self.assertRaisesRegex(ValueError, "source-file-unavailable"):
            self.check(path)


if __name__ == "__main__":
    unittest.main()
