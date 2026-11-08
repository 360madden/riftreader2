"""Offline tests for one-epoch 480-second reader freshness observation."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import observe_live_reader_freshness as observer


NOW = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)


def fixture():
    summary = {
        "status": "reader-running-postflight-verified", "lab": "lab2", "runId": "run",
        "readerPid": 12, "readerStartUtcTicks": "22", "readerSha256": "a" * 64,
        "nonce": "nonce", "expiresAtUtc": (NOW + timedelta(seconds=600)).isoformat(),
        "guestDirectory": "guest", "guestOutput": "out",
        "gamePid": 33, "gameStartUtcTicks": "44", "gameSha256": "b" * 64,
        "receiver": {"pid": 55, "processStartUtcTicks": "66", "image": "image",
                     "address": "127.0.0.1", "port": 49923, "configSha256": "c" * 64},
        "vmIdentityStable": True, "inputSent": False, "controlAgentStopped": False,
        "cleanup": "bounded exit", "atUtc": NOW.isoformat(),
    }
    pin = {
        "lab": "lab2",
        "reader": {"nonce": "nonce", "processId": 12, "processStartUtcTicks": 22,
                   "executableSha256": "a" * 64},
        "gameIdentity": {"processId": 33, "processStartUtcTicks": 44,
                         "executableSha256": "b" * 64},
        "receiver": {"processId": 55, "processStartUtcTicks": 66},
    }
    return pin, summary


class FakeSample:
    def __init__(self, number, xyz=(0.0, 0.0, 0.0), captured_at_utc=NOW):
        self.number = number
        self.xyz = xyz
        self.addon_epoch = 1
        self.player = "player-1"
        self.captured_at_utc = captured_at_utc

    def to_dict(self):
        return {"outerSequence": self.number, "addonSequence": self.number,
                "addonEpoch": self.addon_epoch, "player": self.player,
                "xyz": dict(zip(("x", "y", "z"), self.xyz))}


class FakeFeedback:
    def wait_initial(self, timeout_seconds=4.5):
        assert timeout_seconds == 4.5
        return FakeSample(0, captured_at_utc=NOW - timedelta(seconds=4))


class SimulatedClock:
    def __init__(self, step=4.0):
        self.elapsed = 0.0
        self.step = step

    def mono(self):
        return self.elapsed

    def now(self):
        return NOW + timedelta(seconds=self.elapsed)

    def sleep(self, _):
        self.elapsed += self.step


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.pin, self.summary = fixture()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_binding_valid_with_full_budget(self):
        expiry = observer.validate_binding(self.pin, self.summary, now=NOW)
        self.assertGreater((expiry - NOW).total_seconds(), 525)

    def test_binding_rejects_old_nonce(self):
        self.pin["reader"]["nonce"] = "old"
        with self.assertRaisesRegex(observer.ObserverError, "reader-summary-pin-mismatch"):
            observer.validate_binding(self.pin, self.summary, now=NOW)

    def test_binding_rejects_game_epoch_change(self):
        self.pin["gameIdentity"]["processStartUtcTicks"] += 1
        with self.assertRaisesRegex(observer.ObserverError, "game-summary-pin-mismatch"):
            observer.validate_binding(self.pin, self.summary, now=NOW)

    def test_binding_rejects_receiver_epoch_change(self):
        self.pin["receiver"]["processId"] += 1
        with self.assertRaisesRegex(observer.ObserverError, "receiver-summary-pin-mismatch"):
            observer.validate_binding(self.pin, self.summary, now=NOW)

    def test_binding_rejects_insufficient_expiry_budget(self):
        self.summary["expiresAtUtc"] = (NOW + timedelta(seconds=525)).isoformat()
        with self.assertRaisesRegex(observer.ObserverError, "reader-expiry-budget-insufficient"):
            observer.validate_binding(self.pin, self.summary, now=NOW)

    def test_binding_rejects_shortened_qualification(self):
        with self.assertRaisesRegex(observer.ObserverError, "duration-must-be-at-least-480s"):
            observer.validate_binding(self.pin, self.summary, now=NOW,
                                      duration_seconds=479)

    def observe_fake(self, step=4.0, drift=False, frozen=False,
                     slow_final_seconds=0, capture_skip=False, read_errors=()):
        clock = SimulatedClock(step)
        index = [0]
        errors = list(read_errors)

        def read(_pin, *, initial=False):
            if errors:
                raise errors.pop(0)
            index[0] += 1
            return {"sequence": index[0]}, b"{}", {}

        def validate(prior, receipt):
            return "wait" if frozen else ("accept"
                if receipt["sequence"] > prior.number else "wait")

        def sample(_pin, receipt, _raw, _directory, _label):
            captured = clock.now()
            if capture_skip and clock.elapsed >= 8:
                captured += timedelta(seconds=8 if capture_skip is True else capture_skip)
            if slow_final_seconds and clock.elapsed >= 480:
                clock.elapsed += slow_final_seconds
            return FakeSample(receipt["sequence"],
                              (.1, 0.0, 0.0) if drift else (0.0, 0.0, 0.0),
                              captured_at_utc=captured)

        target = Path(self.temp.name) / "evidence"
        with patch.object(observer.feedback, "_validate_next", side_effect=validate), \
             patch.object(observer.feedback, "_sample_from_receipt", side_effect=sample):
            try:
                result = observer.observe(
                    self.pin, self.summary, target, clock=clock.mono, now=clock.now,
                    sleep=clock.sleep, feedback_factory=lambda _p, _d: FakeFeedback(),
                    receipt_reader=read)
                return result, target
            except observer.ObserverError:
                return None, target

    def test_full_480_seconds_requires_advancing_observations(self):
        result, target = self.observe_fake()
        self.assertEqual(result["status"], "passed")
        self.assertGreaterEqual(result["observedSeconds"], 480)
        self.assertGreater(result["acceptedSamples"], 100)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "passed")
        ledger = (target / "samples.jsonl").read_bytes()
        rows = [json.loads(line) for line in ledger.splitlines()]
        self.assertEqual(len(rows), result["acceptedSamples"])
        self.assertEqual([row["index"] for row in rows],
                         list(range(result["acceptedSamples"])))
        self.assertEqual(result["ledgerSha256"], hashlib.sha256(ledger).hexdigest())
        self.assertEqual(result["maximumAcceptanceGapSeconds"], 4.0)
        self.assertEqual(result["maximumCaptureGapSeconds"], 4.0)
        self.assertEqual(result["transientUnavailableReads"], 0)

    def test_transient_unavailable_read_is_counted_but_not_accepted(self):
        unavailable = observer.console.Blocked("live-receipt-unavailable")
        result, target = self.observe_fake(step=.2, read_errors=(unavailable,))

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["transientUnavailableReads"], 1)
        rows = (target / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), result["acceptedSamples"])
        self.assertEqual(json.loads(rows[1])["sample"]["outerSequence"], 1)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["transientUnavailableReads"], 1)

    def test_persistent_unavailable_reads_still_fail_on_exact_gap_gate(self):
        unavailable = observer.console.Blocked("live-receipt-unavailable")
        result, target = self.observe_fake(
            step=1.0, read_errors=(unavailable,) * 10)

        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["reason"], "observation-gap-exceeded")
        self.assertEqual(summary["transientUnavailableReads"], 5)
        self.assertEqual(summary["acceptedSamples"], 1)

    def test_other_blocked_reason_is_not_tolerated(self):
        changed = observer.console.Blocked("observation-identity-changed")
        with self.assertRaisesRegex(observer.console.Blocked,
                                    "observation-identity-changed"):
            self.observe_fake(step=.2, read_errors=(changed,))

        target = Path(self.temp.name) / "evidence"
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["reason"], "observation-identity-changed")
        self.assertEqual(summary["transientUnavailableReads"], 0)
        self.assertEqual(summary["acceptedSamples"], 1)

    def test_five_second_gap_fails_closed(self):
        result, target = self.observe_fake(step=5.0)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["reason"], "observation-gap-exceeded")

    def test_capture_gap_fails_even_if_receipts_arrive_on_time(self):
        result, target = self.observe_fake(capture_skip=True)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["reason"], "source-capture-gap-exceeded")
        gap = summary["captureGapFailure"]
        self.assertEqual(gap["gapSeconds"], 12.0)
        self.assertEqual(gap["limitExclusiveSeconds"], 4.5)
        self.assertEqual(gap["previousCapturedAtUtc"], (NOW + timedelta(seconds=4)).isoformat())
        self.assertEqual(gap["rejectedCapturedAtUtc"], (NOW + timedelta(seconds=16)).isoformat())
        self.assertEqual(gap["previousAcceptedSampleIndex"], 2)
        self.assertEqual(gap["rejectedRawReceiptLabel"], "observer-00003")
        self.assertEqual(summary["acceptedSamples"], 3)
        self.assertEqual(len((target / "samples.jsonl").read_text(encoding="utf-8").splitlines()), 3)
        self.assertNotIn("sourceQualification", summary)

    def test_capture_gap_just_below_limit_is_accepted(self):
        result, _ = self.observe_fake(capture_skip=0.499)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["maximumCaptureGapSeconds"], 4.499)
        self.assertNotIn("captureGapFailure", result)

    def test_capture_gap_at_limit_fails_closed(self):
        result, target = self.observe_fake(capture_skip=0.5)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["reason"], "source-capture-gap-exceeded")
        self.assertEqual(summary["captureGapFailure"]["gapSeconds"], 4.5)
        self.assertEqual(summary["acceptedSamples"], 3)

    def test_capture_gap_just_above_limit_fails_closed(self):
        result, target = self.observe_fake(capture_skip=0.501)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["reason"], "source-capture-gap-exceeded")
        self.assertEqual(summary["captureGapFailure"]["gapSeconds"], 4.501)
        self.assertEqual(summary["captureGapFailure"]["rejectedRawReceiptLabel"],
                         "observer-00003")
        self.assertEqual(summary["acceptedSamples"], 3)

    def test_planar_drift_fails_closed(self):
        result, target = self.observe_fake(drift=True)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["reason"], "stationary-planar-drift")

    def test_slow_final_receipt_cannot_pass_after_expiry_margin(self):
        result, target = self.observe_fake(slow_final_seconds=80)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["reason"], "reader-expiry-margin-exceeded")

    def test_slow_final_processing_cannot_pass_with_observation_gap(self):
        result, target = self.observe_fake(slow_final_seconds=5)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["reason"], "observation-processing-gap-exceeded")

    def test_production_advancement_rejects_duplicate_clock_and_epoch_change(self):
        prior = SimpleNamespace(outer_sequence=10, addon_sequence=20, addon_epoch=5,
                                addon_clock=100.0, player="player-1", captured_at_utc=NOW)
        def receipt(clock=101.0, epoch=5, outer=11):
            return {"_movementSource": "full", "observation": {
                "sequence": outer, "capturedAtUtc": (NOW + timedelta(seconds=1)).isoformat(),
                "riftReader2": {"observation": {"sequence": 21, "epoch": epoch,
                    "clock": {"value": clock}, "player": {"value": "player-1"}}}}}
        self.assertEqual(observer.feedback._validate_next(prior, receipt()), "accept")
        self.assertEqual(observer.feedback._validate_next(prior, receipt(clock=100.0)), "wait")
        with self.assertRaisesRegex(observer.console.Blocked, "movement-feedback-continuity-lost"):
            observer.feedback._validate_next(prior, receipt(epoch=6))
        with self.assertRaisesRegex(observer.console.Blocked, "movement-feedback-continuity-lost"):
            observer.feedback._validate_next(prior, receipt(outer=9))

    def test_frozen_sequence_never_passes(self):
        result, target = self.observe_fake(step=.25, frozen=True)
        self.assertIsNone(result)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["reason"], "observation-gap-exceeded")
        self.assertEqual(summary["acceptedSamples"], 1)


if __name__ == "__main__":
    unittest.main()
