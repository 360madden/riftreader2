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


class ReadLiveReceiptTests(unittest.TestCase):
    def evaluate(self, value, receiver=RECEIVER):
        return gate.evaluate_receipt(
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


if __name__ == "__main__":
    unittest.main()
