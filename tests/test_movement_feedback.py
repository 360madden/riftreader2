import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


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
        receipt, gate = value if isinstance(value, tuple) else (value, {"status": "fresh"})
        data = json.dumps(receipt, separators=(",", ":")).encode()
        return receipt, data, gate


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
                "riftReader2": {"bindingStatus": "bound", "freshnessStatus": "fresh", "observation": {
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


    def scoped(self, receipt):
        """Model a gate-validated fresh scoped scan in the same publication loop."""
        chosen = copy.deepcopy(receipt)
        chosen["_movementSource"] = "fast"
        chosen["observation"]["fastObservation"] = {
            "provenance": "recent-full-scan-anchored-candidate-regions/1",
            "scan": {"scope": "candidate-regions"},
            "observation": copy.deepcopy(chosen["observation"]["riftReader2"]["observation"]),
        }
        return chosen

    def wire_receipt(self, folder, *, full_addon=20, full_clock=30.0,
                     fast_addon=21, fast_clock=31.0):
        pin = copy.deepcopy(self.pin)
        pin["receiptPath"] = str(Path(folder) / "latest.json")
        pin["receiptSha256"] = hashlib.sha256(b"wire").hexdigest()
        full = self.receipt(addon=full_addon, clock=full_clock)[
            "observation"]["riftReader2"]["observation"]
        full.update(schemaVersion=1, addonVersion="0.1.0")
        fast = copy.deepcopy(full)
        fast.update(sequence=fast_addon)
        fast["clock"]["value"] = fast_clock
        receipt = {
            "schemaVersion": 1, "receiverInstance": "receiver-1",
            "receivedAtUtc": self.now.isoformat(), "receivedMonotonicNs": 1,
            "sourceAddress": "192.168.56.128", "gameReady": False, "note": "delivery",
            "observation": {
                "schemaVersion": 1, "instanceId": "reader-1", "nonce": "a" * 32,
                "sequence": 10, "capturedAtUtc": self.now.isoformat(),
                "monotonicMilliseconds": 1.0, "readerStatus": "running", "readerReason": None,
                "target": {**self.pin["gameIdentity"], "readerSessionNonce": "a" * 32},
                "riftReader2": {"bindingStatus": "bound", "freshnessStatus": "fresh",
                                "observation": full},
                "delivery": {}, "nativePower": {},
                "fastObservation": {"observation": fast},
            },
        }
        return pin, receipt

    def test_immutable_journal_pin_follows_current_head_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            observations = Path(folder) / "observations"
            bucket = hashlib.sha256(self.pin["reader"]["instanceId"].encode()).hexdigest()
            journal = observations / "journal" / bucket / "00000010.json"
            journal.parent.mkdir(parents=True)
            journal.write_bytes(b"bootstrap")
            latest = observations / "latest.json"
            latest.write_bytes(b"live-1")
            pin = copy.deepcopy(self.pin)
            pin["receiptPath"] = str(journal)
            pin["receiptSha256"] = hashlib.sha256(b"bootstrap").hexdigest()

            with mock.patch.object(module._console, "_validate_receiver_host"), \
                    mock.patch.object(module, "_validate_movement_receipt_bytes",
                                      side_effect=lambda _pin, data: ({}, data, {})):
                self.assertEqual(b"bootstrap", module._movement_receipt(pin, initial=True)[1])
                self.assertEqual(b"live-1", module._movement_receipt(pin, initial=False)[1])
                latest.write_bytes(b"live-2")
                self.assertEqual(b"live-2", module._movement_receipt(pin, initial=False)[1])
                journal.write_bytes(b"tampered")
                with self.assertRaisesRegex(module._console.Blocked, "live-receipt-sha256-mismatch"):
                    module._movement_receipt(pin, initial=False)

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
            self.assertEqual("whole-readable-private", sample.source_scope)
            self.assertEqual("nonce-bound-complete-process-scan/1", sample.source_provenance)
            self.assertEqual(1, reader.calls)

    def test_read_accepts_explicit_scoped_selection_without_promoting_full_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt(outer=11, addon=21, clock=31, x=1.5)
            selected = receipt["observation"]["riftReader2"]["observation"]
            receipt["observation"]["riftReader2"]["bindingStatus"] = "unbound"
            receipt["observation"]["riftReader2"]["freshnessStatus"] = "unavailable"
            receipt["observation"]["fastObservation"] = {
                "provenance": "recent-full-scan-anchored-candidate-regions/1",
                "bindingStatus": "bound-scoped",
                "freshnessStatus": "fresh-scoped",
                "observation": selected,
                "scan": {"scope": "candidate-regions"},
            }
            adapter, _ = self.adapter(folder, [receipt])

            sample = adapter.read("scoped")

            self.assertEqual((1.5, 2.0, 3.0), sample.xyz)
            self.assertEqual("candidate-regions", sample.source_scope)
            self.assertEqual(
                "recent-full-scan-anchored-candidate-regions/1", sample.source_provenance)

    def test_movement_scoped_reader_preserves_exact_reader_and_game_pins(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt = self.wire_receipt(folder)
            receipt["observation"]["fastObservationDiagnostic"] = {
                "status": "created", "reason": None}
            with mock.patch.object(module._console, "_validate_receiver_host"), \
                    mock.patch.object(module._console, "_read_regular", return_value=b"wire"), \
                    mock.patch.object(module._console, "_strict_json_bytes", return_value=receipt), \
                    mock.patch.object(module._console._live_gate, "evaluate_receipt",
                                      side_effect=module._console._live_gate.GateError("full stale")), \
                    mock.patch.object(module._console._live_gate, "evaluate_fast_observation",
                                      return_value={"status": "fresh-scoped"}):
                loaded, data, gate = module._movement_receipt(pin, initial=True)
                self.assertIsNot(receipt, loaded)
                self.assertEqual("fast", loaded["_movementSource"])
                self.assertEqual(b"wire", data)
                self.assertEqual("fresh-scoped", gate["status"])

                receipt["observation"]["instanceId"] = "other-reader"
                with self.assertRaisesRegex(module._console.Blocked, "reader-identity-mismatch"):
                    module._movement_receipt(pin, initial=True)

    def test_movement_chooses_newest_validated_source_and_ignores_invalid_or_older_fast(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt = self.wire_receipt(folder)
            common = (
                mock.patch.object(module._console, "_validate_receiver_host"),
                mock.patch.object(module._console, "_read_regular", return_value=b"wire"),
                mock.patch.object(module._console, "_strict_json_bytes", return_value=receipt),
            )
            with common[0], common[1], common[2], \
                    mock.patch.object(module._console._live_gate, "evaluate_receipt",
                                      return_value={"status": "fresh"}), \
                    mock.patch.object(module._console._live_gate, "evaluate_fast_observation",
                                      return_value={"status": "fresh-scoped"}):
                loaded, _, gate = module._movement_receipt(pin, initial=True)
                self.assertEqual("fast", loaded["_movementSource"])
                self.assertEqual("fastObservation", gate["sourceBlock"])

            pin, receipt = self.wire_receipt(folder)
            with mock.patch.object(module._console, "_validate_receiver_host"), \
                    mock.patch.object(module._console, "_read_regular", return_value=b"wire"), \
                    mock.patch.object(module._console, "_strict_json_bytes", return_value=receipt), \
                    mock.patch.object(module._console._live_gate, "evaluate_receipt",
                                      return_value={"status": "fresh"}), \
                    mock.patch.object(module._console._live_gate, "evaluate_fast_observation",
                                      side_effect=module._console._live_gate.GateError("bad fast")):
                loaded, _, _ = module._movement_receipt(pin, initial=True)
                self.assertEqual("full", loaded["_movementSource"])

            pin, receipt = self.wire_receipt(
                folder, full_addon=20, full_clock=30, fast_addon=19, fast_clock=29)
            with mock.patch.object(module._console, "_validate_receiver_host"), \
                    mock.patch.object(module._console, "_read_regular", return_value=b"wire"), \
                    mock.patch.object(module._console, "_strict_json_bytes", return_value=receipt), \
                    mock.patch.object(module._console._live_gate, "evaluate_receipt",
                                      return_value={"status": "fresh"}), \
                    mock.patch.object(module._console._live_gate, "evaluate_fast_observation",
                                      return_value={"status": "fresh-scoped"}):
                loaded, _, _ = module._movement_receipt(pin, initial=True)
                self.assertEqual("full", loaded["_movementSource"])

    def test_wait_initial_retries_only_stale_then_preserves_accepted_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            stale = module._console.Blocked("live-receipt-not-fresh")
            accepted = self.receipt(outer=11, addon=21, clock=31)
            adapter, reader = self.adapter(folder, [stale, stale, accepted])

            sample = adapter.wait_initial()

            self.assertEqual(11, sample.outer_sequence)
            self.assertEqual(3, reader.calls)
            self.assertEqual(
                [Path(folder) / "initial-receipt.json"],
                list(Path(folder).glob("*-receipt.json")))

    def test_wait_initial_stale_timeout_and_identity_failure_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            clock = Clock()

            class StaleReader:
                def __call__(self, pin, *, initial):
                    raise module._console.Blocked("live-receipt-not-fresh")

            adapter = module.PinnedFeedback(
                self.pin, Path(folder), receipt_reader=StaleReader(),
                monotonic=clock.monotonic, sleep=clock.sleep)
            with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-timeout"):
                adapter.wait_initial(timeout_seconds=0.1)
            self.assertEqual([], list(Path(folder).glob("*-receipt.json")))

            adapter, reader = self.adapter(
                folder, [module._console.Blocked("live-reader-identity-mismatch")])
            with self.assertRaisesRegex(module._console.Blocked, "live-reader-identity-mismatch"):
                adapter.wait_initial(timeout_seconds=4.5)
            self.assertEqual(1, reader.calls)
            self.assertEqual([], list(Path(folder).glob("*-receipt.json")))

    def test_wait_initial_has_exact_four_point_five_second_ceiling(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter, _ = self.adapter(folder, [])
            with self.assertRaisesRegex(module._console.Blocked, "invalid-timeout"):
                adapter.wait_initial(timeout_seconds=4.5001)

    def test_action_ready_accepts_full_and_waits_for_fast_anchor_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            full = {"sourceBlock": "riftReader2",
                    "effectiveInnerAgeMilliseconds": 800.0,
                    "freshnessTimeoutMilliseconds": 5000.0}
            adapter, reader = self.adapter(folder, [(receipt, full)])
            sample = adapter.wait_action_ready()
            self.assertEqual(10, sample.outer_sequence)
            self.assertEqual("ready-1-10-receipt.json", sample.raw_receipt_path.name)
            self.assertTrue(sample.raw_receipt_path.is_file())
            self.assertEqual(1, reader.calls)

        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            expiring = {"sourceBlock": "fastObservation",
                        "anchorAgeMilliseconds": 7401.6,
                        "anchorMaxAgeMilliseconds": 10000.0}
            renewed = {"sourceBlock": "fastObservation",
                       "anchorAgeMilliseconds": 3750.0,
                       "anchorMaxAgeMilliseconds": 10000.0}
            adapter, reader = self.adapter(folder, [
                (receipt, expiring), (receipt, renewed)])
            self.assertEqual(10, adapter.wait_action_ready().outer_sequence)
            self.assertEqual(2, reader.calls)

    def test_action_ready_rejects_bad_budget_and_times_out_without_action(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            invalid = {"sourceBlock": "fastObservation",
                       "anchorAgeMilliseconds": 1.0}
            adapter, _ = self.adapter(folder, [(receipt, invalid)])
            with self.assertRaisesRegex(module._console.Blocked,
                                        "movement-feedback-anchor-budget-invalid"):
                adapter.wait_action_ready()

        with tempfile.TemporaryDirectory() as folder:
            clock = Clock()
            expiring = {"sourceBlock": "fastObservation",
                        "anchorAgeMilliseconds": 9500.0,
                        "anchorMaxAgeMilliseconds": 10000.0}
            receipt = self.receipt()
            adapter, _ = self.adapter(
                folder, [(receipt, expiring)] * 4, clock=clock)
            with self.assertRaisesRegex(module._console.Blocked,
                                        "movement-feedback-anchor-budget-timeout"):
                adapter.wait_action_ready(timeout_seconds=0.1)

    def test_action_ready_default_remains_ten_seconds_but_prearm_may_wait_twenty(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            ready = {"sourceBlock": "fastObservation",
                     "anchorAgeMilliseconds": 1000.0,
                     "anchorMaxAgeMilliseconds": 10000.0}
            adapter, _ = self.adapter(folder, [(receipt, ready)])
            self.assertEqual(10, adapter.wait_action_ready().outer_sequence)
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            ready = {"sourceBlock": "fastObservation",
                     "anchorAgeMilliseconds": 1000.0,
                     "anchorMaxAgeMilliseconds": 10000.0}
            adapter, _ = self.adapter(folder, [(receipt, ready)])
            self.assertEqual(10, adapter.wait_action_ready(timeout_seconds=20.0).outer_sequence)
        with tempfile.TemporaryDirectory() as folder:
            adapter, _ = self.adapter(folder, [])
            with self.assertRaisesRegex(module._console.Blocked,
                                        "movement-feedback-invalid-timeout"):
                adapter.wait_action_ready(timeout_seconds=20.0001)

    def test_action_ready_custom_anchor_reserve_is_bounded_and_enforced(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            below = {"sourceBlock": "fastObservation",
                     "anchorAgeMilliseconds": 1000.001,
                     "anchorMaxAgeMilliseconds": 10000.0}
            enough = {"sourceBlock": "fastObservation",
                      "anchorAgeMilliseconds": 1000.0,
                      "anchorMaxAgeMilliseconds": 10000.0}
            adapter, reader = self.adapter(folder, [(receipt, below), (receipt, enough)])
            sample = adapter.wait_action_ready(
                timeout_seconds=20.0,
                minimum_fast_anchor_remaining_milliseconds=9000.0)
            self.assertEqual(10, sample.outer_sequence)
            self.assertEqual(2, reader.calls)
        with tempfile.TemporaryDirectory() as folder:
            adapter, _ = self.adapter(folder, [])
            for reserve in (6249.999, 10000.001, True, float("nan")):
                with self.subTest(reserve=reserve), self.assertRaisesRegex(
                        module._console.Blocked, "anchor-reserve-invalid"):
                    adapter.wait_action_ready(
                        minimum_fast_anchor_remaining_milliseconds=reserve)

    def test_action_ready_headroom_boundary_is_inclusive_and_below_it_waits(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            boundary = {"sourceBlock": "fastObservation",
                        "anchorAgeMilliseconds": 3750.0,
                        "anchorMaxAgeMilliseconds": 10000.0}
            adapter, _ = self.adapter(folder, [(receipt, boundary)])
            self.assertEqual(10, adapter.wait_action_ready().outer_sequence)

        with tempfile.TemporaryDirectory() as folder:
            receipt = self.receipt()
            below = {"sourceBlock": "fastObservation",
                     "anchorAgeMilliseconds": 3750.001,
                     "anchorMaxAgeMilliseconds": 10000.0}
            adapter, _ = self.adapter(folder, [(receipt, below)] * 3)
            with self.assertRaisesRegex(module._console.Blocked,
                                        "movement-feedback-anchor-budget-timeout"):
                adapter.wait_action_ready(timeout_seconds=0.05)

    def test_action_ready_waits_for_new_addon_sample_after_previous_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            clock = Clock()
            full = {"sourceBlock": "riftReader2",
                    "effectiveInnerAgeMilliseconds": 900.0,
                    "freshnessTimeoutMilliseconds": 5000.0}
            baseline = self.receipt(outer=1594, addon=4878, clock=118117.414)
            repeated = self.receipt(outer=1597, addon=4878, clock=118117.414)
            adapter, reader = self.adapter(
                folder, [(baseline, full)] + [(repeated, full)] * 4, clock=clock)
            self.assertEqual(4878, adapter.wait_action_ready().addon_sequence)
            with self.assertRaisesRegex(module._console.Blocked,
                                        "movement-feedback-anchor-budget-timeout"):
                adapter.wait_action_ready(timeout_seconds=0.1)
            self.assertEqual(4, reader.calls)
            self.assertEqual(1, len(list(Path(folder).glob("ready-*-receipt.json"))))

        with tempfile.TemporaryDirectory() as folder:
            full = {"sourceBlock": "riftReader2",
                    "effectiveInnerAgeMilliseconds": 900.0,
                    "freshnessTimeoutMilliseconds": 5000.0}
            baseline = self.receipt(outer=1594, addon=4878, clock=118117.414)
            repeated = self.receipt(outer=1595, addon=4878, clock=118117.414,
                                    captured=self.now + timedelta(seconds=1))
            advanced = self.receipt(outer=1596, addon=4879, clock=118118.0,
                                    captured=self.now + timedelta(seconds=2))
            adapter, reader = self.adapter(
                folder, [(baseline, full), (repeated, full), (advanced, full)])
            adapter.wait_action_ready()
            self.assertEqual(4879, adapter.wait_action_ready().addon_sequence)
            self.assertEqual(3, reader.calls)

    def test_action_ready_full_source_needs_headroom_before_pulse(self):
        with tempfile.TemporaryDirectory() as folder:
            clock = Clock()
            expired_soon = {"sourceBlock": "riftReader2",
                            "effectiveInnerAgeMilliseconds": 3596.7175,
                            "freshnessTimeoutMilliseconds": 5000.0}
            adapter, reader = self.adapter(
                folder, [(self.receipt(), expired_soon)] * 3, clock=clock)
            with self.assertRaisesRegex(module._console.Blocked,
                                        "movement-feedback-anchor-budget-timeout"):
                adapter.wait_action_ready(timeout_seconds=0.05)
            self.assertEqual(2, reader.calls)
            self.assertEqual([], list(Path(folder).glob("ready-*-receipt.json")))

        with tempfile.TemporaryDirectory() as folder:
            full_at_boundary = {"sourceBlock": "riftReader2",
                                "effectiveInnerAgeMilliseconds": 2500.0,
                                "freshnessTimeoutMilliseconds": 5000.0}
            adapter, reader = self.adapter(
                folder, [(self.receipt(), full_at_boundary)])
            self.assertEqual(10, adapter.wait_action_ready().outer_sequence)
            self.assertEqual(1, reader.calls)

    def test_action_ready_rejects_missing_full_source_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter, _ = self.adapter(folder, [(self.receipt(), {
                "sourceBlock": "riftReader2"})])
            with self.assertRaisesRegex(module._console.Blocked,
                                        "movement-feedback-full-budget-invalid"):
                adapter.wait_action_ready()

    def test_wait_accepts_only_strict_post_action_advancement(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            early_barrier = self.receipt(
                outer=11, addon=21, clock=31,
                captured=completed + timedelta(milliseconds=90))
            accepted = self.scoped(self.receipt(
                outer=12, addon=22, clock=32, x=1.5,
                captured=completed + timedelta(milliseconds=250)))
            adapter, reader = self.adapter(
                folder, [early_barrier, accepted])

            sample = adapter.wait_after(completed, prior)

            self.assertEqual(12, sample.outer_sequence)
            self.assertEqual(22, sample.addon_sequence)
            self.assertEqual(32, sample.addon_clock)
            self.assertEqual((1.5, 2.0, 3.0), sample.xyz)
            self.assertEqual(2, reader.calls)
            self.assertTrue((Path(folder) / "barrier-10-11-receipt.json").is_file())


    def test_async_full_completion_after_barrier_requires_later_scoped_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            barrier = self.receipt(
                outer=11, addon=21, clock=31,
                captured=completed + timedelta(milliseconds=90))
            # Full scan may have started before input and finished after this
            # barrier, so its later outer receipt is NOT post-action evidence.
            in_flight_full = self.receipt(
                outer=12, addon=22, clock=32, x=9.0,
                captured=completed + timedelta(milliseconds=350))
            fresh_scoped = self.scoped(self.receipt(
                outer=13, addon=23, clock=33, x=1.5,
                captured=completed + timedelta(milliseconds=700)))
            adapter, reader = self.adapter(
                folder, [barrier, in_flight_full, fresh_scoped])

            sample = adapter.wait_after(completed, prior)

            self.assertEqual(13, sample.outer_sequence)
            self.assertEqual((1.5, 2.0, 3.0), sample.xyz)
            self.assertEqual("candidate-regions", sample.source_scope)
            self.assertEqual(3, reader.calls)
            self.assertFalse((Path(folder) / "after-10-12-receipt.json").exists())
            self.assertTrue((Path(folder) / "after-10-13-receipt.json").is_file())

    def test_async_intervening_full_epoch_change_fails_immediately(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            barrier = self.receipt(
                outer=11, addon=21, clock=31,
                captured=completed + timedelta(milliseconds=90))
            changed_full = self.receipt(
                outer=12, addon=22, clock=32, epoch=3,
                captured=completed + timedelta(milliseconds=350))
            future_fast = self.scoped(self.receipt(
                outer=13, addon=23, clock=33,
                captured=completed + timedelta(milliseconds=700)))
            adapter, reader = self.adapter(
                folder, [barrier, changed_full, future_fast])
            with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-continuity-lost"):
                adapter.wait_after(completed, prior)
            self.assertEqual(2, reader.calls)
            self.assertEqual([], list(Path(folder).glob("after-*-receipt.json")))

    def test_async_full_only_after_barrier_times_out_without_movement_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            barrier = self.receipt(
                outer=11, addon=21, clock=31,
                captured=completed + timedelta(milliseconds=90))
            newer_full = self.receipt(
                outer=12, addon=22, clock=32, x=9.0,
                captured=completed + timedelta(milliseconds=500))
            clock = Clock()

            class FullOnlyReader:
                def __init__(self):
                    self.calls = 0

                def __call__(self, pin, *, initial):
                    self.calls += 1
                    receipt = barrier if self.calls == 1 else newer_full
                    return receipt, json.dumps(receipt).encode(), {"status": "fresh"}

            reader = FullOnlyReader()
            adapter = module.PinnedFeedback(
                self.pin, Path(folder), receipt_reader=reader,
                monotonic=clock.monotonic, sleep=clock.sleep)
            with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-timeout"):
                adapter.wait_after(completed, prior, timeout_seconds=0.15)
            self.assertGreaterEqual(reader.calls, 2)
            self.assertEqual([], list(Path(folder).glob("after-*-receipt.json")))

    def test_wait_does_not_use_a_pre_action_capture_as_barrier(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            pre_action = self.receipt(
                outer=11, addon=21, clock=31,
                captured=completed - timedelta(milliseconds=1),
                received=completed + timedelta(milliseconds=10))
            barrier = self.receipt(
                outer=12, addon=22, clock=32,
                captured=completed + timedelta(milliseconds=90))
            accepted = self.scoped(self.receipt(
                outer=13, addon=23, clock=33,
                captured=completed + timedelta(milliseconds=300)))
            adapter, reader = self.adapter(folder, [pre_action, barrier, accepted])

            sample = adapter.wait_after(completed, prior)

            self.assertEqual(13, sample.outer_sequence)
            self.assertEqual(3, reader.calls)
            self.assertFalse((Path(folder) / "barrier-10-11-receipt.json").exists())
            self.assertTrue((Path(folder) / "barrier-10-12-receipt.json").is_file())

    def test_wait_never_promotes_the_barrier_to_final_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            barrier = self.receipt(
                outer=11, addon=21, clock=31,
                captured=completed + timedelta(milliseconds=90))
            data = json.dumps(barrier, separators=(",", ":")).encode()
            clock = Clock()

            class BarrierOnlyReader:
                def __call__(self, pin, *, initial):
                    return barrier, data, {"status": "fresh"}

            adapter = module.PinnedFeedback(
                self.pin, Path(folder), receipt_reader=BarrierOnlyReader(),
                monotonic=clock.monotonic, sleep=clock.sleep)
            with self.assertRaisesRegex(module._console.Blocked, "movement-feedback-timeout"):
                adapter.wait_after(completed, prior, timeout_seconds=0.1)
            self.assertTrue((Path(folder) / "barrier-10-11-receipt.json").is_file())
            self.assertEqual([], list(Path(folder).glob("after-*-receipt.json")))

    def test_wait_retries_only_stale_and_nonadvancing_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            completed = self.now + timedelta(seconds=1)
            stale = module._console.Blocked("live-receipt-not-fresh")
            same = self.receipt(outer=10, addon=20, clock=30,
                                captured=completed + timedelta(seconds=1))
            accepted = self.receipt(outer=11, addon=21, clock=31,
                                    captured=completed + timedelta(seconds=1))
            final = self.scoped(self.receipt(
                outer=12, addon=22, clock=32,
                captured=completed + timedelta(seconds=2)))
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
                (self.now, 6.1, "invalid-timeout"),
            ):
                with self.subTest(reason=reason), \
                        self.assertRaisesRegex(module._console.Blocked, reason):
                    adapter.wait_after(completed, prior, timeout)
            changed = copy.copy(prior)
            object.__setattr__(changed, "lab", "lab2")
            with self.assertRaisesRegex(module._console.Blocked, "prior-lab-mismatch"):
                adapter.wait_after(self.now, changed)

    def test_action_wait_allows_three_scan_intervals_with_six_second_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            prior = self.baseline(folder)
            adapter, reader = self.adapter(
                folder, [module._console.Blocked("live-target-identity-mismatch")])
            with self.assertRaisesRegex(module._console.Blocked, "live-target-identity-mismatch"):
                adapter.wait_after(self.now, prior, timeout_seconds=6.0)
            self.assertEqual(1, reader.calls)
            adapter, _ = self.adapter(folder, [])
            with self.assertRaisesRegex(module._console.Blocked, "invalid-timeout"):
                adapter.wait_after(self.now, prior, timeout_seconds=6.0001)

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
