"""Offline scalar-versus-actor states: don't promote constant fields into yaw."""
from __future__ import annotations
from copy import deepcopy
import contextlib
from io import StringIO
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from scripts import compare_physical_scalar_actor_states as check
from scripts import fresh_native_smoothed_scalar as scalar
from tests.test_analyze_physical_turn_pair import (
    IDENTITY, KEY, PLAYER_ENTITY, report as pose_report, timestamp,
)


def scalar_report(seconds, values=(0.0, 0.0, 0.0, 15.0)):
    rows = []
    for sec in seconds:
        rows.append({
            "identity": deepcopy(IDENTITY),
            "startedAtUtc": timestamp(sec),
            "completedAtUtc": timestamp(sec, 1000),
            "playerKeyDecimal": KEY,
            "playerEntityDecimal": PLAYER_ENTITY,
            "componentAddressDecimal": "1779061295856",
            "rawBits": [struct.unpack("<I", struct.pack("<f", v))[0] for v in values],
            **dict(zip(scalar.VALUES, values)),
            "headingQualified": False, "qualification": scalar.QUALIFICATION,
        })
    burst = len(rows) > 1
    output = {
        "schemaVersion": 1,
        "status": "complete",
        "contractVersion": ("native-current-smoothed-scalar-candidate-burst/1"
                            if burst else "native-current-smoothed-scalar-candidate/1"),
        "identity": deepcopy(IDENTITY),
        "observation": deepcopy(rows[-1]),
    }
    if burst:
        output.update(
            requestedSamples=len(rows), completedSamples=len(rows), observations=rows)
    return output


class CrossEpochScalarPoseTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.paths = {
            k: root / f"{k}.json"
            for k in ("old_scalar", "old_pose", "new_scalar", "new_pose")
        }
        self.old_scalar = scalar_report([3])
        self.old_pose = pose_report("actor-pose", [1, 2], [111.8823, 111.8823])
        self.new_scalar = scalar_report([10, 11])
        self.new_pose = pose_report("actor-pose", [13, 14], [10.228, 10.228])
        self.store()

    def store(self):
        for key in self.paths:
            self.paths[key].write_text(json.dumps(getattr(self, key), allow_nan=False),
                                        encoding="utf-8")

    def compare(self):
        return check.compare(*(self.paths[key] for key in
                               ("old_scalar", "old_pose", "new_scalar", "new_pose")))

    def test_unchanged_scalar_across_distinct_actor_angles_is_not_heading_proof(self):
        result = self.compare()
        self.assertTrue(result["unchangedScalarDespiteDifferentActorAngleCandidate"])
        self.assertTrue(result["scalarUnchangedAcrossBothPairs"])
        self.assertLess(result["actorAngleChangeDegreesCandidate"], -100)
        self.assertTrue(result["actorPoseStableWithinEachPair"])
        self.assertEqual(result["oldScalarValues"], [0, 0, 0, 15])
        self.assertEqual(result["newScalarValues"], [0, 0, 0, 15])
        self.assertEqual(len(set(result["sourceSha256"].values())), 4)
        self.assertFalse(result["headingQualified"])
        self.assertFalse(result["navigationEligible"])
        self.assertFalse(result["gameInputResponseVerified"])

    def test_changed_scalar_only_observed_not_declared_yaw(self):
        self.new_scalar = scalar_report([10, 11], values=(.5, 0., 0., 15.))
        self.store()
        result = self.compare()
        self.assertFalse(result["scalarUnchangedAcrossBothPairs"])
        self.assertTrue(result["scalarFieldsChangedAcrossActorStatesObserved"])
        self.assertFalse(result["headingQualified"])

    def test_no_significant_actor_angle_change_is_negative_control(self):
        self.new_pose = pose_report("actor-pose", [13, 14], [111.9, 111.9])
        self.store()
        result = self.compare()
        self.assertFalse(result["unchangedScalarDespiteDifferentActorAngleCandidate"])
        self.assertLess(abs(result["actorAngleChangeDegreesCandidate"]), 1)

    def test_wrong_entity_and_process_epoch_block(self):
        self.new_scalar["observations"][0]["playerEntityDecimal"] = "1779162488344"
        self.store()
        with self.assertRaisesRegex(ValueError, "scalar-owner-changed"):
            self.compare()
        self.new_scalar = scalar_report([10, 11])
        self.new_pose["identity"]["processStartUtcTicks"] += 1
        for row in self.new_pose["observations"]:
            row["identity"]["processStartUtcTicks"] += 1
        self.new_pose["observation"]["identity"]["processStartUtcTicks"] += 1
        self.store()
        with self.assertRaisesRegex(ValueError, "scalar-pose-process-player-mismatch"):
            self.compare()

    def test_unpaired_time_and_changed_scalar_bits_block(self):
        self.new_scalar = scalar_report([50, 51])
        self.store()
        with self.assertRaisesRegex(ValueError, "scalar-pose-captures-too-far-apart"):
            self.compare()
        self.new_scalar = scalar_report([10, 11])
        self.new_scalar["observations"][1]["rawBits"][0] = 123
        self.new_scalar["observation"]["rawBits"][0] = 123
        self.store()
        with self.assertRaises(scalar.Blocked):
            self.compare()

    def test_cli_writes_new_json_only_and_blocks_reuse(self):
        root = self.paths["old_scalar"].parent
        output = root / "out.json"
        args = [val for key in ("old_scalar", "old_pose", "new_scalar", "new_pose")
                for val in ("--" + key.replace("_", "-"), str(self.paths[key]))]
        args += ["--out", str(output)]
        with contextlib.redirect_stdout(StringIO()) as std:
            self.assertEqual(0, check.main(args))
        self.assertEqual(json.loads(std.getvalue()),
                         json.loads(output.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(StringIO()) as std:
            self.assertEqual(2, check.main(args))
        self.assertEqual(json.loads(std.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
