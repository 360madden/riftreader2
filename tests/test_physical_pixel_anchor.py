"""Source/native rack-frame audits deliberately fail closed for stale RR2 screens."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_pixel_anchor as anchor
from scripts import physical_pixel_ray


IDENTITY = {
    "processId": 37928, "processStartUtcTicks": 639303416167439797,
    "executablePath": r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
    "executableSha256": "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8",
    "moduleBaseAddress": 140701863903232, "moduleSize": 63164416,
}
SOURCE_SHA = "A" * 64
CODE_SHA = "B" * 64
WINDOW = ["2026-11-16T06:58:29.873317+00:00",
          "2026-11-16T06:59:28.794533+00:00"]


def fake_rack():
    return {
        "schema": anchor.RACK_SCHEMA, "status": "complete", "identity": dict(IDENTITY),
        "navigationQualified": False, "nativeContactOrBlocking": "unknown",
        "ownerChain": {"worldAddress": "0x2d211001880"},
        "sourceJoin": {
            "status": "source-MOPP-pose-and-complete-code-matched-with-sibling-box-control",
            "sourcePlacement": "world_7168_2816.cdr|357",
            "sourceHkxSha256": SOURCE_SHA, "sourceMoppCodeSha256": CODE_SHA,
            "observedContact": False, "observedBlocking": False,
        },
        "instance": {
            "bodyWorldPose3x4": [[1, 0, 0, 10], [0, 1, 0, 20], [0, 0, 1, 30]],
            "codeReadCoverage": "complete", "completeCodeSha256": CODE_SHA,
        },
    }


def fake_join(rack_sha):
    return {
        "schema": anchor.JOIN_SCHEMA,
        "status": "same-havok-world-source-anchor-consistent",
        "processId": IDENTITY["processId"],
        "processStartUtcTicks": IDENTITY["processStartUtcTicks"],
        "ownedHavokWorld": "0x2d211001880",
        "rackSourcePlacement": "world_7168_2816.cdr|357",
        "rackSourceHkxSha256": SOURCE_SHA,
        "sourceMoppCodeSha256": CODE_SHA,
        "nativeRackTranslationXYZ": [10, 20, 30],
        "sourceRackTranslationXYZ": [10, 20, 30],
        "sourceToNativeRackMaxTranslationError": 0,
        "sourceToNativeRackMaxBasisError": 0,
        "bracketWindowUtc": WINDOW,
        "totalBracketSeconds": 58.921216,
        "inputReports": [
            {"sha256": "c" * 64}, {"sha256": rack_sha}, {"sha256": "d" * 64},
        ],
        "sameProcessEpochReaderPlayerAndHavokWorld": True,
        "sourceNativeRackPoseMatchedWithinBracket": True,
        "capturesSimultaneous": False,
        "passivePlayerPositionFreshnessQualified": False,
        "watchSourceFrameQualified": False,
        "watchLocalityQualified": False,
        "watchNativePadPresentQualified": False,
        "contactOrBlockingQualified": False,
        "watchScanAuthorized": False,
        "navigationAdmissionQualified": False,
    }


class SourceAnchorAuditTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="rr2-anchor-audit-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.join_path = self.root / "source-join.json"
        self.rack_path = self.root / "rack-report.json"
        self.retained = {
            "identity": dict(IDENTITY),
            "capturedAtUtc": "2026-11-16T06:59:06.8+00:00",
        }
        self.rack = fake_rack()
        self.join = {}

    def run_audit(self):
        rack_bytes = json.dumps(self.rack).encode("utf-8")
        self.rack_path.write_bytes(rack_bytes)
        rack_sha = hashlib.sha256(rack_bytes).hexdigest()
        if not self.join:
            self.join = fake_join(rack_sha)
        else:
            # Keep the join tied to the exact newly written rack, unless a test
            # deliberately corrupts the report link.
            self.join["inputReports"][1]["sha256"] = rack_sha
        join_bytes = json.dumps(self.join).encode("utf-8")
        self.join_path.write_bytes(join_bytes)
        return anchor.audit(
            self.retained, self.join_path, hashlib.sha256(join_bytes).hexdigest(),
            self.rack_path, rack_sha)

    def test_matching_epoch_and_bracket_still_do_not_qualify_mesh(self):
        result = self.run_audit()
        self.assertEqual(result["status"], "candidate-context-only")
        self.assertTrue(result["processEpochMatches"])
        self.assertTrue(result["executableBuildMatches"])
        self.assertTrue(result["moduleMappingMatches"])
        self.assertTrue(result["captureInsideAnchorBracket"])
        self.assertFalse(result["sourceMeshFrameQualified"])
        self.assertFalse(result["screenshotWorldMembershipProven"])
        self.assertFalse(result["visibleSurfaceDepthQualified"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["inputSent"])
        self.assertIn("one-rack-anchor-does-not-register-the-entire-screenshot-obj",
                      result["blockers"])

    def test_epoch_mismatch_includes_pid_reuse_and_restarted_process(self):
        for field, value in (("processId", 51524),
                             ("processStartUtcTicks", 639301139727197117)):
            with self.subTest(field=field):
                self.retained["identity"] = dict(IDENTITY, **{field: value})
                result = self.run_audit()
                self.assertEqual(result["status"], "blocked")
                self.assertFalse(result["processEpochMatches"])
                self.assertIn("screenshot-process-epoch-differs-from-rack-anchor",
                              result["blockers"])

    def test_identical_epoch_but_different_build_or_outside_window_blocks(self):
        self.retained["identity"]["executableSha256"] = "0" * 64
        result = self.run_audit()
        self.assertFalse(result["executableBuildMatches"])
        self.assertEqual(result["status"], "blocked")
        self.retained["identity"] = dict(IDENTITY)
        self.retained["capturedAtUtc"] = "2026-11-12T21:35:54+00:00"
        result = self.run_audit()
        self.assertFalse(result["captureInsideAnchorBracket"])
        self.assertEqual(result["status"], "blocked")
        self.retained["capturedAtUtc"] = "2026-11-16T06:59:06.8+00:00"
        self.retained["identity"]["moduleBaseAddress"] += 0x10000
        result = self.run_audit()
        self.assertFalse(result["moduleMappingMatches"])
        self.assertIn("screenshot-module-mapping-differs-from-rack-anchor",
                      result["blockers"])

    def test_anchor_report_is_sha_pinned_and_join_must_pin_rack(self):
        self.run_audit()
        with self.assertRaisesRegex(ValueError, "source-anchor-join-sha256-mismatch"):
            anchor.audit(self.retained, self.join_path, "0" * 64,
                         self.rack_path, hashlib.sha256(self.rack_path.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "source-anchor-rack-sha256-mismatch"):
            anchor.audit(self.retained, self.join_path,
                         hashlib.sha256(self.join_path.read_bytes()).hexdigest(),
                         self.rack_path, "0" * 64)
        self.join = fake_join("e" * 64)
        self.join["inputReports"][1]["sha256"] = "e" * 64
        # Run an exact prebuilt, but incorrectly linked, receipt.
        self.join_path.write_text(json.dumps(self.join), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source-anchor-rack-not-pinned-by-join"):
            anchor.audit(self.retained, self.join_path,
                         hashlib.sha256(self.join_path.read_bytes()).hexdigest(),
                         self.rack_path, hashlib.sha256(self.rack_path.read_bytes()).hexdigest())

    def test_anchor_world_pose_and_source_controls_must_agree(self):
        for name, mutator, reason in (
            ("world", lambda d: d["ownerChain"].update(worldAddress="0x2"),
             "source-anchor-havok-world-inconsistent"),
            ("pose", lambda d: d["instance"]["bodyWorldPose3x4"][0].__setitem__(3, 11),
             "source-anchor-native-body-translation-inconsistent"),
            ("source", lambda d: d["sourceJoin"].update(sourceHkxSha256="f"*64),
             "source-anchor-rack-source-inconsistent"),
            ("native", lambda d: d["instance"].update(codeReadCoverage="partial"),
             "source-anchor-rack-native-control-unqualified"),
        ):
            with self.subTest(name=name):
                self.rack = fake_rack()
                mutator(self.rack)
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_audit()
                self.join = {}

    def test_forged_navigation_admission_and_invalid_bracket_refuse(self):
        self.join = fake_join(hashlib.sha256(
            json.dumps(self.rack).encode("utf-8")).hexdigest())
        self.join["navigationAdmissionQualified"] = True
        with self.assertRaisesRegex(ValueError, "source-anchor-join-flag-invalid"):
            self.run_audit()
        self.join = {}
        self.rack = fake_rack()
        self.retained["capturedAtUtc"] = "2026-11-16T06:59:06"
        with self.assertRaisesRegex(ValueError, "retained-ray-utc-missing-zone"):
            self.run_audit()
        self.retained["capturedAtUtc"] = "2026-11-16T06:59:06+00:00"
        self.retained["identity"]["processStartUtcTicks"] = True
        with self.assertRaisesRegex(ValueError, "retained-ray-process-identity-missing"):
            self.run_audit()


class ArchivedPhysicalSourceAnchorTests(unittest.TestCase):
    """Optional real AMD-DESKTOP provenance; all inputs are retained, no RIFT reads."""

    def test_real_source_anchor_has_same_executable_but_different_epoch(self):
        root = Path(__file__).resolve().parents[1]
        capture = root / "artifacts/waypoint-view-a07ef160cdd34d5f9465b13e372c44fb"
        rack_dir = Path(r"C:\work\RiftWorld\artifacts\p0_source_frame_rack_20261116_0159_et")
        necessary = (capture / "observation.json", capture / "route.json",
                     rack_dir / "source-frame-join-r3-r4.json", rack_dir / "report.json")
        if not all(path.is_file() for path in necessary):
            self.skipTest("exact AMD-DESKTOP historical evidence not installed")
        retained = physical_pixel_ray.pick_retained(
            capture / "observation.json", capture / "route.json", 962, 321)
        result = anchor.audit(
            retained, necessary[2],
            "367544fbeca884b32bfb906a36efd6307aa66d9e305220f85b69320503c13771",
            necessary[3],
            "650c7989f5cdc06f70e769148e82e1941a07e4911a169cec1aaceb843712e957")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["screenshot"]["processId"], 51524)
        self.assertEqual(result["anchor"]["processId"], 37928)
        self.assertTrue(result["executableBuildMatches"])
        self.assertTrue(result["moduleMappingMatches"])
        self.assertFalse(result["processEpochMatches"])
        self.assertFalse(result["captureInsideAnchorBracket"])
        self.assertFalse(result["sourceMeshFrameQualified"])


if __name__ == "__main__":
    unittest.main()
