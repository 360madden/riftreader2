"""Offline tests for source-hashed selected-target change comparison."""
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import compare_native_target_reports as module
from scripts.sample_current_native_selected_target import GAME_SHA, QUALIFICATION

PID = 123
TICKS = 639296903905448486
TARGET = 0x80000002CD0034D1
START = "2026-11-08T01:00:00+00:00"
END = "2026-11-08T01:00:01+00:00"
AFTER_START = "2026-11-08T01:00:02+00:00"
AFTER_END = "2026-11-08T01:00:03+00:00"


def report(*, start=START, end=END, target=TARGET, health=100, energy=50):
    identity = dict(processId=PID, processStartUtcTicks=TICKS, executableSha256=GAME_SHA)
    def metric(value):
        if value is None:
            return dict(status="unavailable", current=None, maximum=None,
                        unavailableReason="not-present")
        return dict(status="calculated-candidate", current=value, maximum=100,
                    unavailableReason=None)
    vitals = dict(identity=identity.copy(), unitKey=target,
                  startedAtUtc=start, completedAtUtc=end,
                  qualification="candidate-only; semantics/passive-freshness/restart-unverified",
                  health=metric(health), energy=metric(energy), mana=metric(None))
    position = dict(status="candidate", unitKey=target, componentAddress=0x20070000,
                    startedAtUtc=start, completedAtUtc=end,
                    position=dict(x=1.5, y=2.0, z=3.0),
                    qualification="cached position candidate; freshness and target semantics unverified")
    context = dict(qualification="typed owner raw inputs; target level presentation, combat semantics and freshness unverified",
                   status="owner-unavailable", owner=None, rawLevel=None, rawCombat=None,
                   combatCandidate=None, levelStatus=None, levelBranch=None,
                   numericLevelCandidate=None)
    observation = dict(identity=identity, startedAtUtc=start, completedAtUtc=end,
                       selfKey=321, status="candidate",
                       beforeGuardStatus="fallback-key-candidate",
                       afterGuardStatus="fallback-key-candidate", targetKey=target,
                       targetUnitId=f"u{target:016X}", targetEntity=0x20040000,
                       targetVitals=vitals, nameSeed={}, targetContext=context,
                       targetPosition=position, qualification=QUALIFICATION)
    return dict(schemaVersion=1,
                contractVersion="native-current-selected-target-candidate-sample/1",
                status="complete", qualification=QUALIFICATION,
                observation=observation)


def pair():
    return report(), report(start=AFTER_START, end=AFTER_END,
                            health=80, energy=45)


def compare(before=None, after=None, **kwargs):
    b, a = pair()
    return module.compare_reports(before or b, after or a, pid=PID, ticks=TICKS,
                                  before_sha256="A" * 64, after_sha256="B" * 64,
                                  **kwargs)


class NativeTargetComparisonTests(unittest.TestCase):
    def test_direct_script_entrypoint_imports_repo_package(self):
        result = subprocess.run([sys.executable, str(Path(module.__file__).resolve()), "--help"],
                                cwd=module.ROOT, text=True, capture_output=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--before", result.stdout)

    def test_same_target_reports_candidate_deltas_and_nulls(self):
        first, second = pair()
        original = copy.deepcopy((first, second))
        result = compare(first, second)
        self.assertEqual("same-target-candidate", result["targetContinuity"])
        self.assertEqual(-20, result["resources"]["health"]["deltaCurrentCandidate"])
        self.assertEqual(-5, result["resources"]["energy"]["deltaCurrentCandidate"])
        self.assertIs(result["resources"]["health"]["changedCurrentCandidate"], True)
        self.assertIsNone(result["resources"]["mana"]["deltaCurrentCandidate"])
        self.assertIsNone(result["resources"]["mana"]["before"]["current"])
        self.assertEqual(str(TARGET), result["beforeTarget"]["unitKey"])
        self.assertEqual(original, (first, second))
        self.assertIn("unqualified", result["qualification"])

    def test_same_target_position_delta_is_candidate_not_motion(self):
        first, second = pair()
        second["observation"]["targetPosition"]["position"] = {
            "x": 4.5, "y": 6.0, "z": 15.0,
        }
        result = compare(first, second)
        position = result["position"]
        self.assertEqual("same-component-delta-candidate", position["status"])
        self.assertEqual({"x": 3.0, "y": 4.0, "z": 12.0},
                         position["deltaCandidate"])
        self.assertAlmostEqual(13.0, position["distance3dCandidate"])
        self.assertAlmostEqual((3.0 ** 2 + 12.0 ** 2) ** 0.5,
                               position["horizontalXZDistanceCandidate"])
        self.assertIn("movement/freshness unverified", position["qualification"])

    def test_target_or_component_change_withholds_position_delta(self):
        first, second = pair()
        second["observation"]["targetPosition"]["componentAddress"] += 0x110
        changed = compare(first, second)["position"]
        self.assertEqual("unavailable-component-changed", changed["status"])
        self.assertIsNone(changed["deltaCandidate"])
        self.assertIsNone(changed["distance3dCandidate"])

        first, second = pair()
        target = TARGET + 1
        ob = second["observation"]
        ob.update(targetKey=target, targetUnitId=f"u{target:016X}")
        ob["targetVitals"]["unitKey"] = target
        ob["targetPosition"]["unitKey"] = target
        changed = compare(first, second)["position"]
        self.assertEqual("unavailable-target-changed-or-missing", changed["status"])
        self.assertIsNone(changed["deltaCandidate"])

        first, second = pair()
        ob = second["observation"]["targetPosition"]
        ob.update(status="component-unavailable", componentAddress=None,
                  startedAtUtc=None, completedAtUtc=None, position=None)
        missing = compare(first, second)["position"]
        self.assertEqual("unavailable-position", missing["status"])
        self.assertIsNone(missing["horizontalXZDistanceCandidate"])

    def test_extreme_finite_position_does_not_emit_infinite_delta(self):
        first, second = pair()
        first["observation"]["targetPosition"]["position"]["x"] = 1e308
        second["observation"]["targetPosition"]["position"]["x"] = -1e308
        value = compare(first, second)
        self.assertEqual("unavailable-arithmetic-overflow",
                         value["position"]["status"])
        self.assertIsNone(value["position"]["deltaCandidate"])
        json.dumps(value, allow_nan=False)

    def test_changed_target_never_compares_resources(self):
        first, second = pair()
        other = TARGET + 1
        observation = second["observation"]
        observation["targetKey"] = other
        observation["targetUnitId"] = f"u{other:016X}"
        observation["targetVitals"]["unitKey"] = other
        observation["targetPosition"]["unitKey"] = other
        result = compare(first, second)
        self.assertEqual("different-target-candidate", result["targetContinuity"])
        self.assertIsNone(result["resources"]["health"]["deltaCurrentCandidate"])

    def test_missing_target_is_not_zero_or_changed_health(self):
        first, second = pair()
        observation = first["observation"]
        observation.update(status="unavailable",
                           beforeGuardStatus="raw-getter-zero-candidate",
                           afterGuardStatus=None, targetKey=None, targetUnitId=None,
                           targetEntity=None, targetVitals=None, targetContext=None,
                           targetPosition=None)
        result = compare(first, second)
        self.assertEqual("target-acquired-candidate", result["targetContinuity"])
        self.assertIsNone(result["resources"]["health"]["before"]["current"])
        self.assertEqual("raw-getter-zero-candidate",
                         result["resources"]["health"]["before"]["unavailableReason"])
        self.assertIsNone(result["resources"]["health"]["deltaCurrentCandidate"])

    def test_source_epoch_and_player_change_are_rejected(self):
        first, second = pair()
        second["observation"]["identity"]["processStartUtcTicks"] += 1
        with self.assertRaises(ValueError):
            compare(first, second)
        first, second = pair()
        second["observation"]["selfKey"] += 1
        with self.assertRaisesRegex(ValueError, "player-changed"):
            compare(first, second)

    def test_overlapping_and_identical_reports_are_rejected(self):
        first, second = pair()
        second["observation"]["startedAtUtc"] = END
        with self.assertRaisesRegex(ValueError, "observations-overlap"):
            compare(first, second)
        with self.assertRaisesRegex(ValueError, "identical-source"):
            module.compare_reports(first, second, pid=PID, ticks=TICKS,
                                   before_sha256="A" * 64, after_sha256="a" * 64)

    def test_saved_file_cli_publishes_hashes_without_guest_operations(self):
        first, second = pair()
        with tempfile.TemporaryDirectory() as folder:
            before_path = Path(folder) / "before.json"
            after_path = Path(folder) / "after.json"
            before_bytes = json.dumps(first).encode()
            after_bytes = json.dumps(second).encode()
            before_path.write_bytes(before_bytes)
            after_path.write_bytes(after_bytes)
            output = io.StringIO()
            with redirect_stdout(output):
                code = module.main(["--before", str(before_path), "--after", str(after_path),
                                    "--pid", str(PID), "--start-ticks", str(TICKS)])
            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            self.assertEqual(hashlib.sha256(before_bytes).hexdigest().upper(),
                             result["beforeSourceSha256"])
            self.assertEqual(-20, result["resources"]["health"]["deltaCurrentCandidate"])
            self.assertEqual("offline-saved-report", result["mode"])

    def test_unavailable_and_invalid_sources_block(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            for raw in (b"", b"not-json", b"x" * (module.MAX_REPORT_BYTES + 1)):
                path.write_bytes(raw)
                with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                    module.load_report(path)
            path.write_text("{}", encoding="utf-8")
            link = Path(folder) / "link.json"
            try:
                link.symlink_to(path)
            except (OSError, NotImplementedError):
                pass
            else:
                with self.assertRaisesRegex(ValueError, "source-unavailable"):
                    module.load_report(link)

    def test_invalid_capture_has_sanitized_cli_error(self):
        with tempfile.TemporaryDirectory() as folder:
            before = Path(folder) / "first.json"
            after = Path(folder) / "second.json"
            before.write_text("{}", encoding="utf-8")
            after.write_text("{}", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = module.main(["--before", str(before), "--after", str(after),
                                    "--pid", str(PID), "--start-ticks", str(TICKS)])
            self.assertEqual(2, code)
            self.assertEqual("native-target-compare-invalid-report",
                             json.loads(output.getvalue())["reason"])


if __name__ == "__main__":
    unittest.main()
