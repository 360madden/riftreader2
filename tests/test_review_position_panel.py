"""Synthetic offline tests for the position-panel evidence reviewer."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "review_position_panel.py"
SPEC = importlib.util.spec_from_file_location("review_position_panel", SCRIPT)
reviewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviewer)

PROFILE_SHA = "A" * 64
BUILD_SHA = "B" * 64


def profile():
    return {
        "executableSha256": BUILD_SHA,
        "rootRva": 0x32E0200,
        "xOffset": 0x320,
        "yOffset": 0x324,
        "zOffset": 0x328,
        "terminalByteLength": 812,
    }


def identity(pid=1234, ticks=639285359295548343):
    return {
        "processId": pid,
        "processStartUtcTicks": ticks,
        "executablePath": "C:\\RIFT\\rift_x64.exe",
        "executableSha256": BUILD_SHA,
        "moduleBaseAddress": 0x7FF600000000,
        "moduleSize": 62611456,
    }


def observation(x=7460.63, y=863.8044, z=2976.6167):
    return {
        "sequence": 1,
        "startedAtUtc": "2026-10-25T14:39:56.1047643+00:00",
        "completedAtUtc": "2026-10-25T14:39:56.2526586+00:00",
        "monotonicStartMilliseconds": 0.01,
        "monotonicEndMilliseconds": 147.89,
        "status": "complete",
        "reason": None,
        "x": x,
        "y": y,
        "z": z,
        "ownerAddress": "0x202BA8B1480",
        "terminalBytesSha256": "C" * 64,
        "changeFromPrevious": None,
    }


def sample_report(process, sample):
    return {
        "schemaVersion": 1,
        "contractVersion": "native-position-samples/1",
        "qualification": "candidate-only-not-motion-or-update-qualified",
        "profileSha256": PROFILE_SHA,
        "profile": profile(),
        "samples": {
            "status": "complete",
            "reason": None,
            "identity": process,
            "startedAtUtc": sample["startedAtUtc"],
            "completedAtUtc": sample["completedAtUtc"],
            "requestedSamples": 1,
            "completedSamples": 1,
            "observations": [sample],
        },
    }


def event(kind, value=None, second=0):
    return {
        "atUtc": f"2026-10-25T14:40:{second:02d}+00:00",
        "kind": kind,
        "value": value,
    }


class PositionPanelReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.process = identity()
        self.sample = observation()

    def write_session(self):
        value = {
            "schemaVersion": 1,
            "contractVersion": "native-position-panel-session/1",
            "startedAtUtc": "2026-10-25T14:39:00+00:00",
            "qualification": "candidate-only",
            "sourceSha256": PROFILE_SHA,
            "profile": profile(),
            "maximumMonitoringSeconds": 600,
            "pollDelayMilliseconds": 1000,
            "freshnessTimeoutMilliseconds": 3000,
            "noGameInput": True,
            "patchRecovery": "deferred; exact-build guard retained",
        }
        (self.root / "panel-session.json").write_text(
            json.dumps(value) + "\n", encoding="utf-8"
        )

    def write_report(self, name="read-00001.json", report=None):
        report = report or sample_report(self.process, self.sample)
        data = (json.dumps(report) + "\n").encode()
        (self.root / name).write_bytes(data)
        return {
            "path": name,
            "sha256": hashlib.sha256(data).hexdigest().upper(),
            "identity": copy.deepcopy(report["samples"]["identity"]),
        }

    def write_events(self, events):
        (self.root / "panel-events.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8"
        )

    def build(self, raw_sample=None, outcome="live", add_valid_after=False):
        self.write_session()
        raw_sample = raw_sample or self.sample
        report_value = self.write_report(report=sample_report(self.process, raw_sample))
        if outcome == "live":
            state = {
                "status": "live", "reason": None,
                "identity": copy.deepcopy(self.process),
                "observation": copy.deepcopy(raw_sample),
                "isMonitoring": True, "isReading": False,
            }
        else:
            state = {
                "status": "unavailable", "reason": "position-values-not-ready",
                "identity": None, "observation": None,
                "isMonitoring": True, "isReading": False,
            }
        events = [event("opened", {"processId": 9, "directory": str(self.root)}),
                  event("report", report_value, 1), event("state", state, 2)]
        if add_valid_after:
            next_value = self.write_report("read-00002.json")
            live = {
                "status": "live", "reason": None,
                "identity": copy.deepcopy(self.process),
                "observation": copy.deepcopy(self.sample),
                "isMonitoring": True, "isReading": False,
            }
            events.extend([event("report", next_value, 3), event("state", live, 4)])
        events.extend([
            event("state", {"status": "stopped", "reason": None,
                "identity": None, "observation": None,
                "isMonitoring": False, "isReading": False}, 5),
            event("closed", None, 6),
        ])
        self.write_events(events)

    def test_clean_candidate_session(self):
        self.build()
        result = reviewer.review_session(self.root)
        self.assertEqual(result["status"], "recorded-checks-passed")
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["counts"]["state:live"], 1)
        self.assertEqual(result["epochs"][0]["liveStates"], 1)

    def test_subnormal_published_live_is_a_finding(self):
        self.build(observation(2 ** -127, 2 ** -128, 2 ** -129))
        result = reviewer.review_session(self.root)
        self.assertEqual(result["status"], "recorded-checks-failed")
        self.assertIn("subnormal-published-live",
                      {item["reason"] for item in result["findings"]})

    def test_subnormal_withheld_then_valid_is_clean(self):
        self.build(observation(2 ** -127, 2 ** -128, 2 ** -129),
                   outcome="unavailable", add_valid_after=True)
        result = reviewer.review_session(self.root)
        self.assertEqual(result["status"], "recorded-checks-passed")
        self.assertEqual(result["counts"]["subnormalRawObservations"], 1)
        self.assertEqual(result["counts"]["startupWithheldStates"], 1)

    def test_zero_and_negative_coordinates_are_valid(self):
        self.build(observation(0.0, -12.5, -0.0))
        self.assertEqual(reviewer.review_session(self.root)["findings"], [])

    def test_tampered_report_hash_is_rejected(self):
        self.build()
        (self.root / "read-00001.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Report hash mismatch"):
            reviewer.review_session(self.root)

    def test_report_path_traversal_is_rejected(self):
        self.build()
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        events[1]["value"]["path"] = "../read-00001.json"
        self.write_events(events)
        with self.assertRaisesRegex(ValueError, "Report path"):
            reviewer.review_session(self.root)

    def test_rehashed_profile_mismatch_is_rejected(self):
        self.build()
        path = self.root / "read-00001.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["profile"]["rootRva"] += 8
        data = (json.dumps(report) + "\n").encode()
        path.write_bytes(data)
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        events[1]["value"]["sha256"] = hashlib.sha256(data).hexdigest().upper()
        self.write_events(events)
        with self.assertRaisesRegex(ValueError, "Report profile mismatch"):
            reviewer.review_session(self.root)

    def test_rehashed_identity_mismatch_is_rejected(self):
        self.build()
        path = self.root / "read-00001.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["samples"]["identity"]["processId"] += 1
        data = (json.dumps(report) + "\n").encode()
        path.write_bytes(data)
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        events[1]["value"]["sha256"] = hashlib.sha256(data).hexdigest().upper()
        self.write_events(events)
        with self.assertRaisesRegex(ValueError, "Report identity mismatch"):
            reviewer.review_session(self.root)

    def test_live_state_without_report_is_rejected(self):
        self.write_session()
        live = {"status": "live", "reason": None, "identity": self.process,
                "observation": self.sample, "isMonitoring": False, "isReading": False}
        self.write_events([event("opened"), event("state", live, 1), event("closed", None, 2)])
        with self.assertRaisesRegex(ValueError, "no preceding report"):
            reviewer.review_session(self.root)

    def test_non_live_state_retaining_values_is_a_finding(self):
        self.build()
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        events[-2]["value"]["identity"] = copy.deepcopy(self.process)
        self.write_events(events)
        result = reviewer.review_session(self.root)
        self.assertIn("non-live-state-retained-values",
                      {item["reason"] for item in result["findings"]})

    def test_cli_refuses_to_overwrite_output(self):
        self.build()
        output = self.root / "review.json"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(reviewer.main(["--session-dir", str(self.root),
                                            "--output", str(output)]), 0)
        original = output.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(reviewer.main(["--session-dir", str(self.root),
                                            "--output", str(output)]), 1)
        self.assertEqual(output.read_bytes(), original)

    def test_duplicate_json_key_is_rejected(self):
        self.build()
        path = self.root / "panel-session.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace('{"schemaVersion": 1,',
                                     '{"schemaVersion": 1, "schemaVersion": 1,'),
                        encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            reviewer.review_session(self.root)

    def test_unreferenced_report_file_is_rejected(self):
        self.build()
        (self.root / "read-99999.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unreferenced or missing"):
            reviewer.review_session(self.root)

    def test_report_cannot_be_reused_live_after_unavailable_outcome(self):
        self.build(outcome="unavailable")
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        reused = {
            "status": "live", "reason": None,
            "identity": copy.deepcopy(self.process),
            "observation": copy.deepcopy(self.sample),
            "isMonitoring": True, "isReading": False,
        }
        events.insert(-2, event("state", reused, 4))
        self.write_events(events)
        with self.assertRaises(ValueError):
            reviewer.review_session(self.root)

    def test_report_without_immediate_state_outcome_is_rejected(self):
        self.build()
        extra = self.write_report("read-00002.json")
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        events.insert(-1, event("report", extra, 6))
        self.write_events(events)
        with self.assertRaises(ValueError):
            reviewer.review_session(self.root)

    def test_subnormal_report_requires_matching_withheld_outcome(self):
        self.build(observation(2 ** -127, 2 ** -128, 2 ** -129),
                   outcome="unavailable", add_valid_after=True)
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        events[2]["value"]["reason"] = "some-other-unavailable-reason"
        self.write_events(events)
        result = reviewer.review_session(self.root)
        self.assertEqual(result["status"], "recorded-checks-failed")
        self.assertIn("subnormal-withholding-not-established",
                      {item["reason"] for item in result["findings"]})

    def test_invalid_and_reversed_journal_timestamps_are_rejected(self):
        for mode in ("invalid", "reversed"):
            with self.subTest(mode=mode):
                self.build()
                events = [json.loads(line) for line in
                          (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
                events[1]["atUtc"] = (
                    "not-a-timestamp" if mode == "invalid"
                    else "2026-10-25T14:39:59+00:00"
                )
                self.write_events(events)
                with self.assertRaises(ValueError):
                    reviewer.review_session(self.root)

    def test_decreasing_report_indices_are_rejected(self):
        self.build(add_valid_after=True)
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        first_report = next(item for item in events if item["kind"] == "report")
        second_report = [item for item in events if item["kind"] == "report"][1]
        first_report["value"], second_report["value"] = (
            second_report["value"], first_report["value"]
        )
        self.write_events(events)
        with self.assertRaises(ValueError):
            reviewer.review_session(self.root)

    def test_same_pid_and_start_cannot_change_module_base(self):
        self.build(add_valid_after=True)
        path = self.root / "read-00002.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["samples"]["identity"]["moduleBaseAddress"] += 0x1000
        data = (json.dumps(report) + "\n").encode()
        path.write_bytes(data)
        events = [json.loads(line) for line in
                  (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
        report_event = [item for item in events if item["kind"] == "report"][1]
        report_event["value"]["sha256"] = hashlib.sha256(data).hexdigest().upper()
        report_event["value"]["identity"] = copy.deepcopy(report["samples"]["identity"])
        live_state = [item for item in events
                      if item["kind"] == "state" and item["value"]["status"] == "live"][1]
        live_state["value"]["identity"] = copy.deepcopy(report["samples"]["identity"])
        self.write_events(events)
        with self.assertRaises(ValueError):
            reviewer.review_session(self.root)

    def test_finite_report_may_end_expired_or_stopped(self):
        for status in ("expired", "stopped"):
            with self.subTest(status=status):
                self.build()
                extra = self.write_report("read-00002.json")
                events = [json.loads(line) for line in
                          (self.root / "panel-events.jsonl").read_text(encoding="utf-8").splitlines()]
                outcome = {
                    "status": status,
                    "reason": ("monitoring-limit-reached" if status == "expired" else None),
                    "identity": None,
                    "observation": None,
                    "isMonitoring": False,
                    "isReading": False,
                }
                events[-2:-2] = [event("report", extra, 4), event("state", outcome, 5)]
                self.write_events(events)
                result = reviewer.review_session(self.root)
                self.assertEqual(result["status"], "recorded-checks-passed")


if __name__ == "__main__":
    unittest.main()
