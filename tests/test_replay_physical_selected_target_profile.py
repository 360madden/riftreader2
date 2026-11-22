"""Offline original-byte replay checks for physical selected-target profiles."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from shutil import copytree
import unittest
from unittest.mock import patch

from scripts import physical_selected_target_profile as profile
from scripts import replay_physical_selected_target_profile as replay
from tests import test_physical_selected_target_profile as fixture_module


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

    def check(self, path):
        with patch.object(replay.physical_rift, "_native_values",
                          side_effect=self.decode):
            return replay.replay(path)

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
