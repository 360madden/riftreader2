"""Offline tests of live field-lab old-epoch rejection evidence.

These use synthetic reports, not the live game or an attached process.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_native_field_evidence import (
    ROOT_RVA,
    START,
    TICKS,
    _new_health_epoch,
    evidence,
    health_fixture,
)


def make_reports(mode="retired"):
    previous = health_fixture()
    current = _new_health_epoch(previous)
    current["plan"]["oldPid"] = (
        previous["identity"]["processId"]
        if mode == "retired" else current["identity"]["processId"]
    )
    current["plan"]["oldStartTicks"] = previous["identity"]["processStartUtcTicks"]
    current["oldEpochRejected"] = True
    current["oldEpochError"] = (
        "OpenProcess failed with Win32 error 87."
        if mode == "retired"
        else "The process start identity does not match the capture request."
    )
    return previous, current


class NativeOldEpochEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def evaluate(self, previous, current):
        before, probe = self.root / "prior.json", self.root / "probe.json"
        before.write_text(json.dumps(previous) + "\n", encoding="utf-8")
        probe.write_text(json.dumps(current) + "\n", encoding="utf-8")
        return evidence.review_old_epoch_probe(before, probe, ROOT_RVA)

    def test_retired_pid_open_rejected_is_explicit_and_scoped(self):
        a, b = make_reports()
        result = self.evaluate(a, b)
        self.assertEqual(result["testMode"], "retired-pid-open-rejected")
        self.assertTrue(result["oldEpochRejected"])
        self.assertEqual(result["requestedOldPid"], a["identity"]["processId"])
        self.assertEqual(result["requestedOldStartUtcTicks"], TICKS)
        self.assertEqual(result["qualification"], "candidate-only")
        self.assertEqual(result["updateSurvival"], "not-assessed")
        self.assertTrue(result["currentPositionWithinTolerance"])
        self.assertEqual(result["currentRootStability"], "verified")

    def test_current_pid_wrong_start_is_an_independent_negative_case(self):
        a, b = make_reports("samepid")
        result = self.evaluate(a, b)
        self.assertEqual(result["testMode"], "live-pid-stale-start-rejected")
        self.assertEqual(result["requestedOldPid"], b["identity"]["processId"])
        self.assertNotEqual(result["requestedOldStartUtcTicks"], b["identity"]["processStartUtcTicks"])
        self.assertIn("process start identity", result["rejectionReason"])

    def test_reversed_report_input_does_not_invent_history(self):
        a, b = make_reports()
        with self.assertRaises(evidence.EvidenceError):
            self.evaluate(b, a)

    def test_mismatched_prior_start_is_not_sufficient(self):
        a, b = make_reports()
        b["plan"]["oldStartTicks"] += 1
        with self.assertRaisesRegex(evidence.EvidenceError, "independent prior-epoch"):
            self.evaluate(a, b)

    def test_nonstale_start_is_not_accepted(self):
        a, b = make_reports("samepid")
        b["plan"]["oldStartTicks"] = b["identity"]["processStartUtcTicks"]
        with self.assertRaisesRegex(evidence.EvidenceError, "independent prior-epoch"):
            self.evaluate(a, b)

    def test_missing_plan_fields_fail_closed(self):
        a, b = make_reports()
        del b["plan"]["oldPid"]
        with self.assertRaisesRegex(evidence.EvidenceError, "oldPid"):
            self.evaluate(a, b)

    def test_boolean_pid_is_not_an_integer_identity(self):
        a, b = make_reports()
        b["plan"]["oldPid"] = True
        with self.assertRaisesRegex(evidence.EvidenceError, "oldPid"):
            self.evaluate(a, b)

    def test_no_explicit_rejection_cannot_pass(self):
        a, b = make_reports()
        b["oldEpochRejected"] = False
        with self.assertRaisesRegex(evidence.EvidenceError, "explicitly reject"):
            self.evaluate(a, b)

    def test_missing_error_reason_cannot_pass(self):
        a, b = make_reports()
        del b["oldEpochError"]
        with self.assertRaisesRegex(evidence.EvidenceError, "negative-check reason"):
            self.evaluate(a, b)

    def test_wrong_error_reason_cannot_pass(self):
        a, b = make_reports("samepid")
        b["oldEpochError"] = "OpenProcess failed with Win32 error 87."
        with self.assertRaisesRegex(evidence.EvidenceError, "reason does not match"):
            self.evaluate(a, b)

    def test_incorrect_retired_pid_rejected(self):
        a, b = make_reports()
        b["plan"]["oldPid"] = 99991
        with self.assertRaisesRegex(evidence.EvidenceError, "neither|does not match the prior"):
            self.evaluate(a, b)

    def test_prior_and_current_builds_must_match(self):
        a, b = make_reports()
        b["identity"]["executableSha256"] = "B" * 64
        b["plan"]["buildSha256"] = "B" * 64
        for key in ("referenceBefore", "referenceAfter"):
            b[key]["target"]["executableSha256"] = "B" * 64
        with self.assertRaisesRegex(evidence.EvidenceError, "builds differ"):
            self.evaluate(a, b)

    def test_different_character_not_a_matching_epoch(self):
        a, b = make_reports()
        for key in ("referenceBefore", "referenceAfter"):
            b[key]["readback"]["typedApi"]["snapshot"]["player"]["unitId"] = "other-player"
        with self.assertRaisesRegex(evidence.EvidenceError, "character identities differ"):
            self.evaluate(a, b)

    def test_same_process_epoch_not_a_restart(self):
        a, b = make_reports()
        b["identity"]["processId"] = a["identity"]["processId"]
        b["identity"]["processStartUtcTicks"] = TICKS
        for key in ("referenceBefore", "referenceAfter"):
            b[key]["target"]["processId"] = a["identity"]["processId"]
            b[key]["target"]["processStartUtc"] = START
        with self.assertRaisesRegex(evidence.EvidenceError, "different process epoch"):
            self.evaluate(a, b)

    def test_unstable_current_root_is_not_accepted(self):
        a, b = make_reports()
        b["windows"][0]["stable"] = False
        with self.assertRaisesRegex(evidence.EvidenceError, "root and typed Lua"):
            self.evaluate(a, b)

    def test_incorrect_current_native_position_is_not_accepted(self):
        a, b = make_reports()
        b["referenceBefore"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]["coordX"]["value"] += 8
        b["referenceAfter"]["readback"]["typedApi"]["snapshot"]["player"]["fields"]["coordX"]["value"] += 8
        with self.assertRaisesRegex(evidence.EvidenceError, "root and typed Lua"):
            self.evaluate(a, b)

    def test_prior_must_precede_probe(self):
        a, b = make_reports()
        a["startedAtUtc"] = "2026-10-19T10:00:00Z"
        a["completedAtUtc"] = "2026-10-19T10:01:00Z"
        with self.assertRaisesRegex(evidence.EvidenceError, "must precede"):
            self.evaluate(a, b)

    def test_cli_atomic_publication_and_replay(self):
        a, b = make_reports("samepid")
        self.evaluate(a, b)
        destination = self.root / "evidence.json"
        args = [
            "--verify-old-epoch",
            "--prior-report", str(self.root / "prior.json"),
            "--report", str(self.root / "probe.json"),
            "--root-rva", "0x32E0200",
            "--output", str(destination),
        ]
        self.assertEqual(evidence.main(args), 0)
        first = destination.read_bytes()
        self.assertEqual(json.loads(first)["testMode"], "live-pid-stale-start-rejected")
        self.assertEqual(evidence.main(args), 2)
        self.assertEqual(destination.read_bytes(), first)

    def test_cli_rejects_missing_prior_report(self):
        a, b = make_reports()
        self.evaluate(a, b)
        self.assertEqual(evidence.main([
            "--verify-old-epoch", "--report", str(self.root / "probe.json"),
            "--root-rva", "0x32E0200",
        ]), 2)

    def test_cli_rejects_incompatible_review_modes(self):
        a, b = make_reports()
        self.evaluate(a, b)
        self.assertEqual(evidence.main([
            "--verify-old-epoch", "--compare-health-hits",
            "--prior-report", str(self.root / "prior.json"),
            "--report", str(self.root / "probe.json"),
            "--root-rva", "0x32E0200",
        ]), 2)


if __name__ == "__main__":
    unittest.main()
