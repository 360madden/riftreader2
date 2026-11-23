"""Offline empirical four-direction movement basis from already completed helper receipts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import contextlib
from io import StringIO
import json
import math
from pathlib import Path
import shutil
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import physical_move_basis as basis
from scripts import launch_physical_waypoints as launcher
from scripts.physical_move_basis_waypoint import read_basis
from scripts.physical_waypoints import PhysicalAdapter
from scripts import prepare_physical_move_calibration as preflight
from tests.test_analyze_physical_turn_pair import sample
from tests.test_physical_facing import report as facing_report
from tests.test_physical_move_key_calibration import receipt


class PhysicalMoveBasisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = {}
        for index, (key, dx, dz) in enumerate(
                (("w", -2, 0), ("s", 1, 0), ("q", 0, 1), ("e", 0, -1))):
            self.paths[key] = self.save(key, index, dx, dz)

    def save(self, key, index, dx, dz):
        base = receipt()
        base["keys"] = [key]
        before, after = (base["xyzFeedback"]["beforeXYZ"],
                         base["xyzFeedback"]["afterXYZ"])
        t = datetime(2026, 11, 11, 14, 50, 0, tzinfo=timezone.utc) + timedelta(seconds=2*index)
        def iso(ms):
            return (t + timedelta(milliseconds=ms)).isoformat()
        before.update(startedAtUtc=iso(0), completedAtUtc=iso(10))
        after.update(startedAtUtc=iso(700), completedAtUtc=iso(710),
                     x=before["x"]+dx, z=before["z"]+dz)
        base["xyzFeedback"].update(
            deltaXYZ={"x": dx, "y": 0, "z": dz},
            planarDisplacementCandidate=math.hypot(dx, dz),
            captureGapSeconds=.690)
        path = self.root / f"{key}-{index}.json"
        path.write_text(json.dumps(base), encoding="utf-8")
        return path

    def analyze(self, *, later_forward=None, turn_sources=None):
        return basis.analyze(self.paths, later_forward=later_forward, turn_sources=turn_sources)

    def turn_trial(self, key, second, before_angle, after_angle, *, moving=False, wrong_host=False):
        pulse = receipt()
        pulse.update(keys=[key], observedMilliseconds=255, holdMilliseconds=250,
                     xyzFeedback=None)
        if wrong_host:
            pulse["machine"] = "DIFFERENT-PC"
        identity = {field: pulse[field] for field in ("processId", "processStartUtcTicks", "executableSha256")}
        identity["executablePath"] = r"C:\RIFT\rift_x64.exe"
        t = datetime(2026, 11, 11, 14, 54, second, tzinfo=timezone.utc)

        def stamp(milliseconds):
            return (t + timedelta(milliseconds=milliseconds)).isoformat()

        def facing(endpoint, angle, offset, drift):
            report = facing_report()
            report["identity"] = identity
            for index, row in enumerate(report["observations"]):
                orientation = sample("orientation", 1, -angle, identity=identity)
                orientation["unitKey"] = "42"
                bearing = -orientation["secondary"]["planarAngleDegreesCandidate"]
                delta = (row["playerSystemBearingDegreesCandidate"] - bearing + 180) % 360 - 180
                row.update(identity=identity, playerKeyDecimal="42",
                           startedAtUtc=stamp(offset + 25 * index), completedAtUtc=stamp(offset + 25 * index + 1),
                           positionOrientationCandidate=orientation, bodyBearingDegreesCandidate=bearing,
                           primaryBearingDegreesCandidate=bearing, playerSystemMinusBodyDegreesCandidate=delta,
                           playerSystemMinusPrimaryDegreesCandidate=delta)
                position = dict(row["positionCandidate"])
                position["x"] += drift
                row["entityPositionCandidate"] = position
                row["entityPositionRawBits"] = [struct.unpack("<I", struct.pack("<f", v))[0]
                                               for v in position.values()]
            path = self.root / f"{key}-{endpoint}.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            return path

        pulse["inputCallTiming"] = {
            "startedAtUtc": stamp(200), "completedAtUtc": stamp(460), "monotonicElapsedMilliseconds": 260,
            "executorObservedMilliseconds": 255, "utcOrderValid": True, "wallClockConsistentWithMonotonic": True,
        }
        pulse["keySendEvents"] = [
            {"key": key, "phase": phase, "callStartedAtUtc": stamp(offset),
             "callCompletedAtUtc": stamp(offset + 1), "sendCallElapsedMilliseconds": 1, "inserted": True}
            for phase, offset in (("key-down", 205), ("key-up", 455))
        ]
        pulse["keyHoldWindows"] = [{
            "key": key, "status": "candidate-sendinput-hold-bounds", "minimumMillisecondsCandidate": 249,
            "midpointMillisecondsCandidate": 250, "maximumMillisecondsCandidate": 251,
            "exactKeyDownUpTimesKnown": False, "gameResponseVerified": False,
            "downCallStartedAtUtc": stamp(205), "downCallCompletedAtUtc": stamp(206),
            "upCallStartedAtUtc": stamp(455), "upCallCompletedAtUtc": stamp(456),
        }]
        pulse_path = self.root / f"{key}-pulse.json"
        pulse_path.write_text(json.dumps(pulse), encoding="utf-8")
        return (facing("before", before_angle, 0, 0), pulse_path,
                facing("after", after_angle, 630, .2 if moving else 0))

    def test_four_vectors_generate_cardinal_candidate_without_navigation_authority(self):
        result = self.analyze()
        self.assertEqual("offline-physical-key-basis-candidate", result["status"])
        self.assertTrue(result["cardinalGeometryCandidate"])
        self.assertFalse(result["navigationEligible"])
        self.assertFalse(result["sameFacingConfirmed"])
        self.assertFalse(result["gameResponseVerified"])
        self.assertEqual(set(result["samples"]), {"w", "s", "q", "e"})
        self.assertEqual(len(set(result["sourceReceiptsSha256"].values())), 4)
        self.assertAlmostEqual(result["geometry"]["forwardVsBackward"]
                               ["unsignedAngleDegreesCandidate"], 180)
        self.assertAlmostEqual(result["geometry"]["forwardVsLeftStrafe"]
                               ["unsignedAngleDegreesCandidate"], 90)
        self.assertAlmostEqual(result["geometry"]["leftVsRightStrafe"]
                               ["unsignedAngleDegreesCandidate"], 180)
        self.assertAlmostEqual(result["geometry"]["forwardVsBackward"]
                               ["firstSpeedOverSecondCandidate"], 2)

    def test_cli_adds_measured_turn_candidates_consumed_by_waypoints(self):
        a = self.turn_trial("a", 5, 175, -150)
        d = self.turn_trial("d", 7, -150, 175)
        output = self.root / "with-turns.json"
        argv = []
        for key, name in zip("wsqe", ("forward", "backward", "left", "right")):
            argv.extend((f"--{name}", str(self.paths[key])))
        argv.extend(("--turn-a", *map(str, a), "--turn-d", *map(str, d), "--out", str(output)))
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(basis.main(argv), 0)
        document, _ = read_basis(output)
        turn_rates = PhysicalAdapter.turn_rates(SimpleNamespace(basis=document))
        self.assertAlmostEqual(turn_rates["a"], .14, places=6)
        self.assertAlmostEqual(turn_rates["d"], -.14, places=6)
        self.assertFalse(document["turnCalibrationCandidate"]["turnResponseQualified"])
        self.assertFalse(document["navigationEligible"])

    def test_turn_rates_reject_incomplete_foreign_or_translating_trials(self):
        a = self.turn_trial("a", 5, 0, 35)
        with self.assertRaisesRegex(ValueError, "turn-basis-both-keys-required"):
            self.analyze(turn_sources={"a": a})
        d = self.turn_trial("d", 7, 35, 0, wrong_host=True)
        with self.assertRaisesRegex(ValueError, "turn-basis-pulse-identity-mismatch"):
            self.analyze(turn_sources={"a": a, "d": d})
        d = self.turn_trial("d", 7, 35, 0, moving=True)
        with self.assertRaisesRegex(ValueError, "turn-basis-position-drift"):
            self.analyze(turn_sources={"a": a, "d": d})

    def test_turn_rates_reject_reversed_brackets_and_overlapping_pulses(self):
        a = self.turn_trial("a", 5, 0, 35)
        d = self.turn_trial("d", 5, 35, 0)
        with self.assertRaisesRegex(ValueError, "turn-basis-overlapping-trials"):
            self.analyze(turn_sources={"a": a, "d": d})
        d = self.turn_trial("d", 7, 35, 0)
        with self.assertRaisesRegex(ValueError, "turn-basis-facing-pulse-order-invalid"):
            self.analyze(turn_sources={"a": a, "d": (d[2], d[1], d[0])})

    def test_turn_rates_require_measured_hold_and_correct_direction(self):
        a = self.turn_trial("a", 5, 0, 35)
        d = self.turn_trial("d", 7, 35, 40)
        with self.assertRaisesRegex(ValueError, "turn-basis-rate-unqualified"):
            self.analyze(turn_sources={"a": a, "d": d})
        d = self.turn_trial("d", 7, 35, 0)
        pulse = json.loads(d[1].read_text(encoding="utf-8"))
        for field in ("inputCallTiming", "keySendEvents", "keyHoldWindows"):
            pulse.pop(field)
        d[1].write_text(json.dumps(pulse), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "turn-basis-bounded-hold-required"):
            self.analyze(turn_sources={"a": a, "d": d})

    def test_measurements_must_match_and_follow_optional_target_preflight(self):
        identity = self.analyze()["identity"]
        target = {"hostName": identity["machine"], "processId": identity["processId"],
                  "processStartUtcTicks": identity["processStartUtcTicks"],
                  "executableSha256": identity["gameBuildSha256"]}
        observed = {"unitKey": identity["unitKey"], "completedAtUtc": "2026-11-11T14:49:59Z"}
        with patch.object(preflight, "verify_preflight", return_value=(target, observed, "B" * 64)):
            report = basis.analyze(self.paths, target_preflight=Path("preflight.json"))
            self.assertEqual(report["preflightSummarySha256"], "B" * 64)
            observed["completedAtUtc"] = "2026-11-11T14:50:02Z"
            with self.assertRaisesRegex(ValueError, "basis-measurement-predates-preflight"):
                basis.analyze(self.paths, target_preflight=Path("preflight.json"))
            target["processStartUtcTicks"] = "1"
            with self.assertRaisesRegex(ValueError, "basis-calibration-preflight-target-mismatch"):
                basis.analyze(self.paths, target_preflight=Path("preflight.json"))

    def calibration_folder(self):
        folder = self.root / "calibration bundle"
        folder.mkdir()
        for key, source in self.paths.items():
            shutil.copyfile(source, folder / f"{key}.json")
        a = self.turn_trial("a", 5, 175, -150)
        d = self.turn_trial("d", 7, -150, 175)
        for key, trial in (("a", a), ("d", d)):
            for part, path in zip(("before", "pulse", "after"), trial):
                shutil.copyfile(path, folder / f"{key}-{part}.json")

        raw = json.loads(a[0].read_text(encoding="utf-8"))
        for row in raw["observations"]:
            for field in ("startedAtUtc", "completedAtUtc"):
                row[field] = row[field].replace("T14:54:", "T14:49:")
        raw["observation"] = raw["observations"][-1]
        facing_path = folder / preflight.FACING
        facing_path.write_text(json.dumps(raw), encoding="utf-8")
        target = dict(raw["identity"], hostName="AMD-DESKTOP", hwnd=42,
                      processStartUtcTicks=str(raw["identity"]["processStartUtcTicks"]))
        summary = {"schema": preflight.SCHEMA, "status": "calibration-baseline-ready", "target": target,
                   "inputSent": False, "focusRequested": False, "baseline": preflight.baseline(facing_path, target)}
        (folder / preflight.SUMMARY).write_text(json.dumps(summary), encoding="utf-8")
        return folder

    def test_complete_calibration_bundle_rebuilds_after_copy(self):
        folder = self.calibration_folder()
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(basis.main(["--bundle", str(folder)]), 0)
        saved, digest = read_basis(folder / basis.BUNDLE_REPORT)
        moved = shutil.copytree(folder, self.root / "another checkout")
        with contextlib.redirect_stdout(StringIO()) as output:
            self.assertEqual(basis.main(["--verify-bundle", str(moved)]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "verified-calibration-bundle")
        self.assertEqual(report["identity"], saved["identity"])
        self.assertEqual(report["basisSha256"], digest)
        self.assertEqual(report["sourceCount"], 12)
        self.assertFalse(report["movementEligible"])
        self.assertEqual(read_basis(moved / basis.BUNDLE_REPORT)[1], digest)

        target, _, _ = preflight.verify_preflight(moved / preflight.SUMMARY)
        host = target["hostName"]
        reader = self.root / "reader.exe"
        reader.touch()
        with patch.dict("os.environ", {"RR2_WAYPOINTS_BASIS": str(moved)}), \
             patch.object(launcher.socket, "gethostname", return_value=host), \
             patch.object(launcher, "_check_tkinter", return_value={"status": "available"}), \
             patch.object(launcher.physical_rift, "check_native_reader", return_value={"status": "ready"}), \
             patch.object(launcher.physical_rift, "NATIVE_EXE", reader), \
             patch.object(launcher.physical_rift, "select_physical") as select, \
             patch.object(PhysicalAdapter, "read", return_value=SimpleNamespace(bearing=12)):
            check = launcher.check_local_setup(dependencies_only=True)
            self.assertTrue(check["ready"])
            self.assertEqual(check["checks"]["movementBasis"]["path"], str(moved))
            select.assert_not_called()
            select.return_value = {"status": "ready", "target": target}
            adapter = PhysicalAdapter(host, target["processId"])
            self.assertEqual(adapter.basis_sha, digest)

    def test_bundle_rejects_valid_json_edits_to_sources_and_saved_rates(self):
        folder = self.calibration_folder()
        basis.calibration_bundle(folder)
        with self.assertRaisesRegex(ValueError, "calibration-bundle-output-exists"):
            basis.calibration_bundle(folder)
        path = folder / basis.BUNDLE_REPORT
        original = path.read_bytes()
        saved = json.loads(original)
        saved["turnCalibrationCandidate"]["rates"]["a"]["degreesPerMillisecondCandidate"] += .01
        path.write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "calibration-bundle-basis-mismatch"):
            basis.calibration_bundle(folder, verify=True)
        path.write_bytes(original)

        source = folder / "w.json"
        receipt_data = json.loads(source.read_bytes())
        receipt_data["annotation"] = "Edited without changing the calculated motion"
        source.write_text(json.dumps(receipt_data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "calibration-bundle-basis-mismatch"):
            launcher.read_waypoints_basis(folder)

    def test_basis_from_a_third_host_can_be_reopened_and_rejects_mixed_hosts(self):
        host = "RR2_FIELD-PC"
        for path in self.paths.values():
            source = json.loads(path.read_text(encoding="utf-8"))
            source["machine"] = host
            path.write_text(json.dumps(source), encoding="utf-8")
        output = self.root / "basis.json"
        output.write_text(json.dumps(self.analyze()), encoding="utf-8")
        self.assertEqual(read_basis(output)[0]["identity"]["machine"], host)
        self.paths["e"] = self.save("e", 3, 0, -1)
        with self.assertRaisesRegex(ValueError, "basis-player-process-build-mismatch"):
            self.analyze()

    def test_later_forward_reports_direction_change_but_not_heading(self):
        later = self.save("w", 4, -.5, 1)
        result = self.analyze(later_forward=later)
        self.assertIn("earlyVsLaterForward", result["geometry"])
        self.assertTrue(result["cardinalGeometryCandidate"])
        self.assertFalse(result["sameFacingConfirmed"])
        self.assertFalse(result["navigationEligible"])
        self.assertGreater(
            result["geometry"]["earlyVsLaterForward"]["unsignedAngleDegreesCandidate"], 10)
        self.assertEqual(len(result["samples"]), 5)
        # A large unverified direction change does not produce a strafe forecast.
        self.assertIsNone(result["laterFacingReprojectionCandidate"])

    def test_small_later_direction_change_reprojects_keys_without_authorizing_input(self):
        later = self.save("w", 4, -2, -.5)
        result = self.analyze(later_forward=later)
        model = result["laterFacingReprojectionCandidate"]
        self.assertEqual("unverified-rigid-rotation-model", model["status"])
        self.assertFalse(model["sameFacingConfirmed"])
        self.assertFalse(model["navigationEligible"])
        self.assertGreater(model["relativeDirectionChangeDegreesCandidate"], 10)
        self.assertLess(model["relativeDirectionChangeDegreesCandidate"], 20)
        self.assertLess(model["modeledVectors"]["q"]["vxPerMillisecondCandidate"], 0)
        self.assertGreater(model["modeledVectors"]["q"]["vzPerMillisecondCandidate"], 0)
        self.assertFalse(result["headingQualified"])
        later = self.save("w", 5, -3, -.5)
        # This test remains chronological because its timestamp follows E.
        result = self.analyze(later_forward=later)
        self.assertIsNone(result["laterFacingReprojectionCandidate"])

    def test_rejects_identity_conflict_duplicate_source_and_key_swap(self):
        original = json.loads(self.paths["e"].read_text(encoding="utf-8"))
        changed = deepcopy(original)
        changed["processStartUtcTicks"] += 1
        self.paths["e"].write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "basis-player-process-build-mismatch"):
            self.analyze()
        self.paths["e"].write_text(json.dumps(original), encoding="utf-8")
        self.paths["e"] = self.paths["q"]
        with self.assertRaisesRegex(ValueError, "basis-key-mismatch"):
            self.analyze()
        self.paths["e"] = self.save("e", 3, 0, -1)
        self.assertEqual("offline-physical-key-basis-candidate", self.analyze()["status"])
        self.paths["e"] = self.paths["w"]
        with self.assertRaisesRegex(ValueError, "basis-key-mismatch"):
            self.analyze()

    def test_rejects_out_of_order_timestamps_and_malformed_input(self):
        original = json.loads(self.paths["e"].read_text(encoding="utf-8"))
        changed = deepcopy(original)
        changed["xyzFeedback"]["beforeXYZ"]["startedAtUtc"] = "2026-11-11T14:49:59+00:00"
        changed["xyzFeedback"]["beforeXYZ"]["completedAtUtc"] = "2026-11-11T14:49:59.010+00:00"
        changed["xyzFeedback"]["afterXYZ"]["startedAtUtc"] = "2026-11-11T14:49:59.700+00:00"
        changed["xyzFeedback"]["afterXYZ"]["completedAtUtc"] = "2026-11-11T14:49:59.710+00:00"
        self.paths["e"].write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "basis-chronology-invalid"):
            self.analyze()
        self.paths["e"].write_text(json.dumps(original), encoding="utf-8")
        changed = deepcopy(original)
        changed["xyzFeedback"]["deltaXYZ"]["x"] = 100
        self.paths["e"].write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "helper-native-delta-mismatch"):
            self.analyze()

    def test_cli_file_new_only(self):
        args = []
        for key, flag in (("w", "--forward"), ("s", "--backward"),
                          ("q", "--left"), ("e", "--right")):
            args.extend([flag, str(self.paths[key])])
        out = self.root / "comparison.json"
        with contextlib.redirect_stdout(StringIO()) as capture:
            self.assertEqual(basis.main(args+["--out",str(out)]),0)
        self.assertEqual(json.loads(capture.getvalue()),
                         json.loads(out.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(StringIO()) as capture:
            self.assertEqual(basis.main(args+["--out",str(out)]),2)
        self.assertEqual(json.loads(capture.getvalue())["status"],"blocked")


if __name__ == "__main__":
    unittest.main()
