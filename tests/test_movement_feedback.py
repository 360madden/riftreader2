import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import movement_feedback as module


class Clock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Reader:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def __call__(self, pin, *, initial):
        self.calls += 1
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        data = json.dumps(value, separators=(",", ":")).encode()
        return value, data, {"status": "fresh"}


class MovementFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 29, 20, 30, tzinfo=timezone.utc)
        self.pin = {
            "lab": "lab1",
            "receiver": {"instanceId": "receiver-1"},
            "reader": {
                "processId": 50,
                "processStartUtcTicks": 60,
                "executableSha256": "c" * 64,
                "instanceId": "reader-1",
                "nonce": "a" * 32,
                "sourceAddress": "192.168.56.128",
            },
            "gameIdentity": {
                "processId": 123,
                "processStartUtcTicks": 456,
                "executablePath": "C:\\RIFT\\rift_x64.exe",
                "executableSha256": "b" * 64,
            },
        }

    def receipt(self, *, outer=10, addon=20, clock=30.0, epoch=2,
                player="unit-1", captured=None, received=None, x=1.0, y=2.0, z=3.0):
        captured = captured or self.now
        received = received or captured + timedelta(milliseconds=10)
        return {
            "receiverInstance": "receiver-1",
            "receivedAtUtc": received.isoformat(),
            "sourceAddress": "192.168.56.128",
            "observation": {
                "instanceId": "reader-1",
                "nonce": "a" * 32,
                "sequence": outer,
                "capturedAtUtc": captured.isoformat(),
                "target": {
                    "processId": 123,
                    "processStartUtcTicks": 456,
                    "executablePath": "C:\\RIFT\\rift_x64.exe",
                    "executableSha256": "b" * 64,
                },
                "riftReader2": {"observation": {
                    "sequence": addon,
                    "epoch": epoch,
                    "clock": {"status": "ok", "value": clock},
                    "player": {"status": "ok", "value": player},
                    "fields": {
                        "coordX": {"status": "ok", "value": x},
                        "coordY": {"status": "ok", "value": y},
                        "coordZ": {"status": "ok", "value": z},
                    },
                }},
            },
        }

    def adapter(self, folder, values, clock=None):
        clock = clock or Clock()
        reader = Reader(values)
        return module.PinnedFeedback(
            self.pin, Path(folder), receipt_reader=reader,
            monotonic=clock.monotonic, sleep=clock.sleep), reader

    def baseline(self, folder, receipt=None):
        receipt = receipt or self.receipt()
        adapter, _ = self.adapter(folder, [receipt])
        return adapter.read("baseline")

    def test_read_retains_exact_receipt_and_json_safe_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            adapter, reader = self.adapter(folder, [receipt])
            sample = adapter.read("baseline")

            expected = json.dumps(receipt, separators=(",", ":")).encode()
            self.assertEqual((1.0, 2.0, 3.0), sample.xyz)
            self.assertEqual(expected, sample.raw_receipt_path.read_bytes())
            self.assertEqual(hashlib.sha256(expected).hexdigest(), sample.raw_receipt_sha256)
            self.assertEqual("lab1", sample.to_dict()["lab"])
            self.assertEqual({"x": 1.0, "y": 2.0, "z": 3.0}, sample.to_dict()["xyz"])
            self.assertEqual(1, reader.calls)

    def test_wait_accepts_only_strict_post_action_advancement(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            too_early = self.receipt(
                outer=11, addon=21, clock=31,
                captured=completed + timedelta(milliseconds=249))
            accepted = self.receipt(
                outer=12, addon=22, clock=32, x=1.5,
                captured=completed + timedelta(milliseconds=250))
            delayed_same_frame = self.receipt(
                outer=13, addon=22, clock=32, x=1.5,
                captured=completed + timedelta(milliseconds=700))
            post_barrier = self.receipt(
                outer=14, addon=23, clock=33, x=1.75,
                captured=completed + timedelta(seconds=1))
            adapter, reader = self.adapter(
                folder, [too_early, accepted, delayed_same_frame, post_barrier])

            sample = adapter.wait_after(completed, prior)

            self.assertEqual(14, sample.outer_sequence)
            self.assertEqual(23, sample.addon_sequence)
            self.assertEqual(33, sample.addon_clock)
            self.assertEqual((1.75, 2.0, 3.0), sample.xyz)
            self.assertEqual(4, reader.calls)
            self.assertTrue((Path(folder) / "barrier-10-12-receipt.json").is_file())

    def test_wait_retries_only_stale_and_nonadvancing_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            stale = module._console.Blocked("live-receipt-not-fresh")
            same = self.receipt(outer=10, addon=20, clock=30,
                                captured=completed + timedelta(seconds=1))
            accepted = self.receipt(outer=11, addon=21, clock=31,
                                    captured=completed + timedelta(seconds=1))
            final = self.receipt(outer=12, addon=22, clock=32,
                                 captured=completed + timedelta(seconds=2))
            adapter, reader = self.adapter(folder, [stale, same, accepted, final])

            self.assertEqual(12, adapter.wait_after(completed, prior).outer_sequence)
            self.assertEqual(4, reader.calls)

    def test_wait_times_out_on_nonadvancing_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            same = self.receipt(captured=self.now + timedelta(seconds=2))
            clock = Clock()

            class SameReader:
                def __call__(self, pin, *, initial):
                    return same, b"{}", {}

            adapter = module.PinnedFeedback(
                self.pin, Path(folder), receipt_reader=SameReader(),
                monotonic=clock.monotonic, sleep=clock.sleep)
            with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-timeout"):
                adapter.wait_after(self.now + timedelta(seconds=1), prior, 0.1)

    def test_wait_next_accepts_one_distinct_fresh_no_input_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            stale = module._console.Blocked("live-receipt-not-fresh")
            same = self.receipt(captured=self.now + timedelta(seconds=1))
            accepted = self.receipt(
                outer=11, addon=21, clock=31, x=1.1,
                captured=self.now + timedelta(seconds=2))
            adapter, reader = self.adapter(folder, [stale, same, accepted])

            sample = adapter.wait_next(prior)

            self.assertEqual(11, sample.outer_sequence)
            self.assertEqual((1.1, 2.0, 3.0), sample.xyz)
            self.assertEqual(3, reader.calls)
            self.assertTrue((Path(folder) / "next-10-11-receipt.json").is_file())
            self.assertEqual([], list(Path(folder).glob("barrier-*-receipt.json")))

    def test_wait_next_rejects_regression_or_identity_failure_immediately(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            regressed = self.receipt(outer=9, addon=21, clock=31,
                                     captured=self.now + timedelta(seconds=1))
            adapter, reader = self.adapter(folder, [regressed])
            with self.assertRaisesRegex(module._console.Blocked, "continuity-lost"):
                adapter.wait_next(prior)
            self.assertEqual(1, reader.calls)

            adapter, reader = self.adapter(
                folder, [module._console.Blocked("live-target-identity-mismatch")])
            with self.assertRaisesRegex(module._console.Blocked, "live-target-identity-mismatch"):
                adapter.wait_next(prior)
            self.assertEqual(1, reader.calls)

    def test_continuity_loss_is_immediate(self):
        for change in ("outer-regression", "addon-regression", "clock-regression",
                       "epoch-change", "player-change"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                prior = self.baseline(folder)
                current = self.receipt(outer=11, addon=21, clock=31,
                                       captured=self.now + timedelta(seconds=2))
                if change == "outer-regression":
                    current["observation"]["sequence"] = 9
                elif change == "addon-regression":
                    current["observation"]["riftReader2"]["observation"]["sequence"] = 19
                elif change == "clock-regression":
                    current["observation"]["riftReader2"]["observation"]["clock"]["value"] = 29
                elif change == "epoch-change":
                    current["observation"]["riftReader2"]["observation"]["epoch"] = 3
                else:
                    current["observation"]["riftReader2"]["observation"]["player"]["value"] = "other"
                adapter, reader = self.adapter(folder, [current])
                with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-continuity-lost"):
                    adapter.wait_after(self.now + timedelta(seconds=1), prior)
                self.assertEqual(1, reader.calls)

    def test_identity_or_malformed_failure_is_not_retried(self):
        for reason in ("live-reader-identity-mismatch", "unexpected-live-selected-fields"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as folder:
                prior = self.baseline(folder)
                adapter, reader = self.adapter(folder, [module._console.Blocked(reason)])
                with self.assertRaisesRegex(module._console.Blocked, reason):
                    adapter.wait_after(self.now + timedelta(seconds=1), prior)
                self.assertEqual(1, reader.calls)

    def test_unavailable_or_nonfinite_coordinate_fails_closed(self):
        for value in (float("nan"), True, "1"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                receipt = self.receipt()
                receipt["observation"]["riftReader2"]["observation"]["fields"]["coordX"]["value"] = value
                adapter, _ = self.adapter(folder, [receipt])
                with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-invalid-coordinate"):
                    adapter.read("bad")

    def test_evidence_is_no_overwrite_and_label_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            adapter, _ = self.adapter(folder, [receipt, copy.deepcopy(receipt)])
            adapter.read("baseline")
            with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-evidence-exists"):
                adapter.read("baseline")
            adapter, _ = self.adapter(folder, [receipt])
            with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-invalid-label"):
                adapter.read("../escape")

    def test_invalid_action_time_timeout_or_prior_lab_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            adapter, _ = self.adapter(folder, [])
            for completed, timeout, reason in (
                (self.now.replace(tzinfo=None), 1, "action-time-must-be-aware"),
                (self.now, 0, "invalid-timeout"),
                (self.now, 4.6, "invalid-timeout"),
            ):
                with self.subTest(reason=reason), \
                        self.assertRaisesRegex(module._console.Blocked, reason):
                    adapter.wait_after(completed, prior, timeout)
            changed = copy.copy(prior)
            object.__setattr__(changed, "lab", "lab2")
            with self.assertRaisesRegex(module._console.Blocked, "prior-lab-mismatch"):
                adapter.wait_after(self.now, changed)

    def test_action_wait_allows_measured_four_point_five_second_bound_only(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            adapter, reader = self.adapter(
                folder, [module._console.Blocked("live-target-identity-mismatch")])
            with self.assertRaisesRegex(module._console.Blocked, "live-target-identity-mismatch"):
                adapter.wait_after(self.now, prior, timeout_seconds=4.5)
            self.assertEqual(1, reader.calls)
            adapter, _ = self.adapter(folder, [])
            with self.assertRaisesRegex(module._console.Blocked, "invalid-timeout"):
                adapter.wait_after(self.now, prior, timeout_seconds=4.5001)

    def test_no_input_wait_retains_three_second_ceiling(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            adapter, _ = self.adapter(folder, [])
            with self.assertRaisesRegex(module._console.Blocked, "invalid-timeout"):
                adapter.wait_next(prior, timeout_seconds=3.0001)

    def test_foreign_same_lab_prior_is_rejected_before_reading(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            for field, value, reason in (
                ("receiver_instance", "other", "prior-reader-mismatch"),
                ("reader_instance", "other", "prior-reader-mismatch"),
                ("reader_nonce", "d" * 32, "prior-reader-mismatch"),
                ("source_address", "192.168.56.129", "prior-reader-mismatch"),
                ("reader_process_id", 51, "prior-reader-mismatch"),
            ):
                with self.subTest(field=field):
                    foreign = copy.copy(prior)
                    object.__setattr__(foreign, field, value)
                    adapter, reader = self.adapter(folder, [])
                    with self.assertRaisesRegex(module._console.Blocked, reason):
                        adapter.wait_after(self.now, foreign)
                    self.assertEqual(0, reader.calls)
            foreign = copy.copy(prior)
            foreign.target["processId"] = 999
            adapter, reader = self.adapter(folder, [])
            with self.assertRaisesRegex(module._console.Blocked, "prior-target-mismatch"):
                adapter.wait_after(self.now, foreign)
            self.assertEqual(0, reader.calls)

    def test_constructor_pin_copy_is_not_affected_by_caller_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            original = copy.deepcopy(self.pin)
            reader = Reader([self.receipt()])
            adapter = module.PinnedFeedback(original, Path(folder), receipt_reader=reader)
            original["reader"]["nonce"] = "f" * 32

            sample = adapter.read("baseline")

            self.assertEqual("a" * 32, sample.reader_nonce)


if __name__ == "__main__":
    unittest.main()
