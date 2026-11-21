"""Offline RR2 native/Lua target-sequence classifier and source-integrity tests.

All target A->B->A examples are explicit synthetic fixtures. No RIFT input,
read-only process attachment or desktop automation is used.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from scripts import replay_physical_telemetry_target as target
from tests.test_replay_physical_telemetry_zone import ZoneEvidenceTests

PLAYER = "u035400012FA2D207"
A = "u00000000000000A1"
B = "u00000000000000B2"
SRC = Path(__file__).resolve().parents[1]


def none_state(doc):
    doc.update(selectionState="none", targetId=None, target={})


def selected(doc, key):
    doc.update(selectionState="selected", targetId=key, target={"id": key, "name": "Test target"})


class TargetSequenceTests(unittest.TestCase):
    def setUp(self):
        self.fx = ZoneEvidenceTests("test_good_synthetic_source_bracket_without_live_process")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        for pass_number in (1, 2):
            for slot in (1, 2):
                self.fx.edit_wire(pass_number, slot, none_state)

    def change(self, states):
        for (pass_number, slot), value in states.items():
            action = none_state if value is None else lambda doc, key=value: selected(doc, key)
            self.fx.edit_wire(pass_number, slot, action)

    def test_valid_no_target_source_baseline_is_explicit_candidate(self):
        with (patch.object(target.zone.physical_rift, "select_physical") as select,
              patch.object(target.zone.physical_rift, "read_native") as read):
            result = target.replay(self.fx.summary)
            select.assert_not_called()
            read.assert_not_called()
        self.assertEqual(result["status"], "no-target-baseline-candidate")
        self.assertEqual(result["qualificationStatus"], "candidate-only")
        self.assertEqual(result["observedFrameCount"], 3)
        self.assertEqual(result["recordedFrameOccurrences"], 4)
        self.assertEqual(result["noTargetFrameCount"], 3)
        self.assertEqual(result["selectedTargetFrameCount"], 0)
        self.assertEqual(result["transitions"], [])
        self.assertEqual(result["aBaCycles"], [])
        self.assertEqual(result["runs"][0]["targetUnitIdCandidate"], None)
        self.assertEqual(result["playerUnitId"], PLAYER)
        self.assertEqual(result["worldInstanceStatus"], "unavailable")

    def test_source_pinned_a_b_a_detected_not_assumed_user_input(self):
        self.change({(1,1): A, (1,2): B, (2,1): B, (2,2): A})
        result = target.replay(self.fx.summary)
        self.assertEqual(result["status"], "a-b-a-target-candidate")
        self.assertEqual(result["selectedTargetFrameCount"], 3)
        self.assertEqual(len(result["transitions"]), 2)
        self.assertEqual(len(result["aBaCycles"]), 1)
        self.assertEqual(result["aBaCycles"][0], {
            "firstTargetUnitIdCandidate": A,
            "otherTargetUnitIdCandidate": B,
            "firstSequence": 1,
            "otherSequence": 2,
            "returnedSequence": 3
        })
        self.assertIn("No native selected-target", result["qualification"])
        self.assertIn("controlled input", result["qualification"])

    def test_explicit_per_frame_evidence_is_source_verified_and_opt_in(self):
        self.change({(1, 1): A, (1, 2): B, (2, 1): B, (2, 2): A})
        normal = target.replay(self.fx.summary)
        self.assertNotIn("observedTargetFrames", normal)
        detailed = target.replay(self.fx.summary, include_frames=True)
        self.assertEqual([row["sequence"] for row in detailed["observedTargetFrames"]],
                         [1, 2, 3])
        self.assertEqual(
            [row["targetUnitIdCandidate"] for row in detailed["observedTargetFrames"]],
            [A, B, A])
        self.assertTrue(all(len(row["sourceSha256"]) == 64
                            for row in detailed["observedTargetFrames"]))
        with self.assertRaisesRegex(ValueError, "invalid-include-frames-option"):
            target.replay(self.fx.summary, include_frames=1)

    def test_selected_frames_without_return_are_not_a_b_a(self):
        self.change({(1,1): A, (1,2): B, (2,1): B, (2,2): B})
        result = target.replay(self.fx.summary)
        self.assertEqual(result["status"], "selected-target-observations-candidate")
        self.assertEqual(len(result["transitions"]), 1)
        self.assertEqual(result["aBaCycles"], [])

    def test_no_target_to_selected_observed_as_transition_not_aba(self):
        self.change({(1,2): A, (2,1): A, (2,2): A})
        result = target.replay(self.fx.summary)
        self.assertEqual(result["status"], "selected-target-observations-candidate")
        self.assertEqual(result["noTargetFrameCount"], 1)
        self.assertEqual(result["selectedTargetFrameCount"], 2)
        self.assertEqual(result["transitions"][0]["fromTargetUnitIdCandidate"], None)
        self.assertEqual(result["transitions"][0]["toTargetUnitIdCandidate"], A)
        self.assertEqual(result["aBaCycles"], [])

    def test_selected_status_requires_exact_target_identity_and_details(self):
        for bad in (
            lambda doc: doc.update(selectionState="selected", targetId=A, target={}),
            lambda doc: doc.update(selectionState="selected", targetId="wrong",
                                   target={"id": "wrong"}),
            lambda doc: doc.update(selectionState="selected", targetId=A,
                                   target={"id": B}),
            lambda doc: doc.update(selectionState="selected", targetId=PLAYER,
                                   target={"id": PLAYER}),
            lambda doc: doc.update(selectionState="unknown", targetId=A,
                                   target={"id": A}),
        ):
            with self.subTest(bad=bad):
                self.fx.edit_wire(2, 2, bad)
                with self.assertRaisesRegex(
                        ValueError, "selected-target-id-unqualified|selected-player-is-not-target-proof"):
                    target.replay(self.fx.summary)
                self.fx.edit_wire(2, 2, none_state)

    def test_no_target_state_with_hidden_target_id_is_refused(self):
        self.fx.edit_wire(2, 2, lambda doc: doc.update(targetId=A))
        with self.assertRaisesRegex(ValueError, "none-state-has-target"):
            target.replay(self.fx.summary)

    def test_tampering_saved_wire_without_repinned_sha_is_refused(self):
        self.fx.edit_wire(2, 2, lambda doc: selected(doc, A), repin=False)
        with self.assertRaisesRegex(ValueError, "wire-source-sha-mismatch"):
            target.replay(self.fx.summary)

    def test_conflicting_duplicate_sequence_source_is_refused(self):
        self.fx.edit_wire(2, 1, lambda doc: selected(doc, A))
        with self.assertRaisesRegex(ValueError, "conflicting-retained-sequence"):
            target.replay(self.fx.summary)

    def test_wrong_process_epoch_and_fabricated_zone_gate_fail_closed(self):
        self.fx.record["target"]["processStartUtcTicks"] = "9"
        self.fx.save()
        with self.assertRaisesRegex(ValueError, "native-process-epoch-or-build"):
            target.replay(self.fx.summary)

    def test_cli_creates_file_only_once_and_returns_candidate_state(self):
        with TemporaryDirectory() as temp:
            destination = Path(temp) / "target-audit.json"
            params = ["--summary", str(self.fx.summary), "--output", str(destination)]
            with redirect_stdout(StringIO()) as capture:
                self.assertEqual(target.main(params), 0)
            self.assertEqual(json.loads(destination.read_text())["status"],
                             "no-target-baseline-candidate")
            self.assertEqual(json.loads(capture.getvalue())["noTargetFrameCount"], 3)
            with redirect_stdout(StringIO()) as refused:
                self.assertEqual(target.main(params), 2)
            self.assertIn("output-exists", refused.getvalue())

    def test_real_physical_autoscope_baseline_replays_when_available(self):
        source = SRC / "artifacts/physical-telemetry-zone-autoscope-20261120-0640/summary.json"
        if not source.is_file():
            self.skipTest("Ignored, same-machine physical evidence not available")
        result = target.replay(source)
        self.assertEqual(result["status"], "no-target-baseline-candidate")
        self.assertEqual(result["playerUnitId"], PLAYER)
        self.assertEqual(result["observedFrameCount"], 22)
        self.assertEqual(result["noTargetFrameCount"], 22)
        self.assertEqual(result["selectedTargetFrameCount"], 0)


if __name__ == "__main__":
    unittest.main()
