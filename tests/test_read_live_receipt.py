from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "read-live-receipt.py"
SPEC = importlib.util.spec_from_file_location("read_live_receipt", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

NOW = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)
NOW_NS = 10_000_000_000
NONCE = "0123456789abcdef0123456789abcdef"
RECEIVER = "receiver-1"


def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def valid_receipt():
    captured = NOW - timedelta(milliseconds=300)
    received = NOW - timedelta(milliseconds=100)
    return {
        "schemaVersion": 1,
        "receiverInstance": RECEIVER,
        "receivedAtUtc": stamp(received),
        "receivedMonotonicNs": NOW_NS - 100_000_000,
        "sourceAddress": "192.168.56.128",
        "observation": {
            "schemaVersion": 1,
            "instanceId": "11111111-2222-4333-8444-555555555555",
            "nonce": NONCE,
            "sequence": 4,
            "capturedAtUtc": stamp(captured),
            "readerStatus": "running",
            "target": {"readerSessionNonce": NONCE},
            "riftReader2": {
                "bindingStatus": "bound",
                "freshnessStatus": "fresh",
                "lastAdvanceAgeMilliseconds": 100,
                "freshnessTimeoutMilliseconds": 5000,
                "selectionStatus": "selected",
                "observation": {"sequence": 7},
                "scan": {"completed": True, "status": "complete"},
            },
        },
    }


def valid_fast_receipt():
    value = valid_receipt()
    value["observation"]["riftReader2"]["bindingStatus"] = "unbound"
    value["observation"]["riftReader2"]["freshnessStatus"] = "unavailable"
    value["observation"]["fastObservation"] = {
        "schemaVersion": 1,
        "provenance": "recent-full-scan-anchored-candidate-regions/1",
        "bindingStatus": "bound-scoped",
        "freshnessStatus": "fresh-scoped",
        "reason": None,
        "anchor": {
            "fullScanStartedAtTimestamp": 1_000_000,
            "fullScanCompletedAtTimestamp": 2_000_000,
            "timestampFrequency": 1_000_000,
            "envelopeSha256": "a" * 64,
            "addonFrameSha256": "b" * 64,
            "candidateSequence": 6,
            "candidateEpoch": 2,
            "candidateClock": 29.0,
            "playerId": "unit-1",
            "regionCount": 2,
            "totalRegionBytes": 8192,
            "maxAgeMilliseconds": 10_000,
        },
        "selectionStatus": "selected-scoped",
        "envelopeSha256": "c" * 64,
        "addonFrameSha256": "d" * 64,
        "candidateSequence": 7,
        "candidateEpoch": 2,
        "publishedAtTimestamp": 3_100_000,
        "lastAdvanceAtTimestamp": 2_500_000,
        "lastAdvanceAgeMilliseconds": 600,
        "freshnessTimeoutMilliseconds": 5000,
        "observation": {
            "schemaVersion": 1,
            "addonVersion": "0.1.0",
            "sequence": 7,
            "epoch": 2,
            "clock": {"status": "ok", "value": 30.0},
            "player": {"status": "ok", "value": "unit-1"},
            "fields": {},
        },
        "scan": {
            "scope": "candidate-regions",
            "status": "complete",
            "completed": True,
            "startedAtTimestamp": 2_500_000,
            "completedAtTimestamp": 3_000_000,
            "plannedBytes": 8192,
            "scannedBytes": 8192,
            "regionCount": 2,
            "elapsedMilliseconds": 500,
            "endpointCandidateCount": 1,
            "malformedCandidateCount": 0,
            "matchingCandidateCount": 1,
            "identicalCopyCount": 1,
            "reason": None,
        },
    }
    return value


class ReadLiveReceiptTests(unittest.TestCase):
    def evaluate(self, value, receiver=RECEIVER):
        return gate.evaluate_receipt(
            value,
            NONCE,
            receiver,
            now_monotonic_ns=NOW_NS,
            now_utc=NOW,
        )

    def evaluate_fast(self, value, receiver=RECEIVER):
        return gate.evaluate_fast_observation(
            value,
            NONCE,
            receiver,
            now_monotonic_ns=NOW_NS,
            now_utc=NOW,
        )

    def test_valid_snapshot_has_conditional_freshness_label(self):
        result = self.evaluate(valid_receipt())
        self.assertEqual(result["status"], "fresh")
        self.assertTrue(result["snapshotOnly"])
        self.assertFalse(result["gameReady"])
        self.assertIn("Synchronized-clock", result["assumption"])

    def test_stale_outer_receipt_is_rejected(self):
        value = valid_receipt()
        value["receivedMonotonicNs"] = NOW_NS - 2_000_000_001
        with self.assertRaisesRegex(gate.GateError, "outer receipt"):
            self.evaluate(value)

    def test_stale_inner_age_with_fresh_outer_is_rejected(self):
        value = valid_receipt()
        value["observation"]["riftReader2"]["lastAdvanceAgeMilliseconds"] = 4800
        with self.assertRaisesRegex(gate.GateError, "inner last advance"):
            self.evaluate(value)

    def test_nonce_mismatch_is_rejected_at_root_and_target(self):
        for mutate in (
            lambda value: value["observation"].update(nonce="a" * 32),
            lambda value: value["observation"]["target"].update(readerSessionNonce="a" * 32),
        ):
            with self.subTest(mutate=mutate):
                value = valid_receipt()
                mutate(value)
                with self.assertRaisesRegex(gate.GateError, "nonce mismatch"):
                    self.evaluate(value)

    def test_future_or_old_guest_capture_clock_is_rejected(self):
        for offset in (0.4, -3.0):
            with self.subTest(offset=offset):
                value = valid_receipt()
                value["observation"]["capturedAtUtc"] = stamp(
                    datetime.fromisoformat(value["receivedAtUtc"].replace("Z", "+00:00"))
                    + timedelta(seconds=offset)
                )
                with self.assertRaisesRegex(gate.GateError, "capture clock"):
                    self.evaluate(value)

    def test_receiver_restart_identity_is_rejected(self):
        with self.assertRaisesRegex(gate.GateError, "receiver instance mismatch"):
            self.evaluate(valid_receipt(), receiver="prior-receiver")

    def test_unavailable_or_terminated_is_rejected(self):
        for field, value in (("readerStatus", "terminated"), ("freshnessStatus", "unavailable")):
            receipt = valid_receipt()
            if field == "readerStatus":
                receipt["observation"][field] = value
            else:
                receipt["observation"]["riftReader2"][field] = value
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                self.evaluate(receipt)

    def test_duplicate_json_property_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
            with self.assertRaisesRegex(gate.GateError, "duplicate JSON property"):
                gate.load_receipt(path)

    def test_missing_or_nonfinite_inner_ages_are_rejected(self):
        for value in (None, float("nan"), float("inf")):
            receipt = valid_receipt()
            receipt["observation"]["riftReader2"]["lastAdvanceAgeMilliseconds"] = value
            with self.subTest(value=value), self.assertRaisesRegex(gate.GateError, "lastAdvanceAge"):
                self.evaluate(receipt)

    def test_fast_observation_is_explicitly_scoped_and_anchor_bounded(self):
        result = self.evaluate_fast(valid_fast_receipt())
        self.assertEqual("fresh-scoped", result["status"])
        self.assertEqual("candidate-regions", result["scope"])
        self.assertEqual(
            "recent-full-scan-anchored-candidate-regions/1", result["provenance"])
        self.assertAlmostEqual(1650, result["anchorAgeMilliseconds"])
        self.assertAlmostEqual(1150, result["effectiveInnerAgeMilliseconds"])

    def test_fast_observation_rejects_expired_or_incomplete_scope(self):
        for mutate, reason in (
            (lambda fast: fast["anchor"].update(maxAgeMilliseconds=9999), "age bound"),
            (lambda fast: fast["scan"].update(scannedBytes=4096), "completely cover"),
            (lambda fast: fast["scan"].update(scope="whole-readable-private"), "not complete"),
            (lambda fast: fast.update(provenance="unknown/1"), "contract"),
        ):
            with self.subTest(reason=reason):
                receipt = valid_fast_receipt()
                mutate(receipt["observation"]["fastObservation"])
                with self.assertRaisesRegex(gate.GateError, reason):
                    self.evaluate_fast(receipt)

    def test_fast_observation_accepts_one_gib_scope_and_rejects_one_byte_more(self):
        receipt = valid_fast_receipt()
        fast = receipt["observation"]["fastObservation"]
        one_gib = 1024 * 1024 * 1024
        fast["anchor"]["totalRegionBytes"] = one_gib
        fast["scan"]["plannedBytes"] = one_gib
        fast["scan"]["scannedBytes"] = one_gib
        self.assertEqual("fresh-scoped", self.evaluate_fast(receipt)["status"])

        too_large = valid_fast_receipt()
        fast = too_large["observation"]["fastObservation"]
        fast["anchor"]["totalRegionBytes"] = one_gib + 1
        fast["scan"]["plannedBytes"] = one_gib + 1
        fast["scan"]["scannedBytes"] = one_gib + 1
        with self.assertRaisesRegex(gate.GateError, "region-byte bound"):
            self.evaluate_fast(too_large)

    def test_fast_observation_requires_strict_source_advancement(self):
        for mutate in (
            lambda fast: fast["observation"].update(sequence=6),
            lambda fast: fast["observation"]["clock"].update(value=29.0),
            lambda fast: fast["observation"]["player"].update(value="other"),
            lambda fast: fast["observation"].update(epoch=3),
        ):
            receipt = valid_fast_receipt()
            mutate(receipt["observation"]["fastObservation"])
            with self.subTest(mutate=mutate), self.assertRaises(gate.GateError):
                self.evaluate_fast(receipt)

    def test_fast_observation_preserves_outer_nonce_receiver_and_time_gates(self):
        receipt = valid_fast_receipt()
        receipt["observation"]["nonce"] = "f" * 32
        with self.assertRaisesRegex(gate.GateError, "nonce mismatch"):
            self.evaluate_fast(receipt)
        with self.assertRaisesRegex(gate.GateError, "receiver instance mismatch"):
            self.evaluate_fast(valid_fast_receipt(), receiver="other")

    def test_fast_observation_host_ages_sample_and_anchor_from_publication(self):
        receipt = valid_fast_receipt()
        receipt["observation"]["fastObservation"]["freshnessTimeoutMilliseconds"] = 1100
        with self.assertRaisesRegex(gate.GateError, "last advance is expired"):
            self.evaluate_fast(receipt)

        receipt = valid_fast_receipt()
        fast = receipt["observation"]["fastObservation"]
        fast["scan"]["startedAtTimestamp"] = 11_000_000
        fast["scan"]["completedAtTimestamp"] = 11_500_000
        fast["lastAdvanceAtTimestamp"] = 11_000_000
        fast["publishedAtTimestamp"] = 11_600_000
        with self.assertRaisesRegex(gate.GateError, "anchor is expired"):
            self.evaluate_fast(receipt)


if __name__ == "__main__":
    unittest.main()
