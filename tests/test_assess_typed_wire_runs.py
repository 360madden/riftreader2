"""Focused tests for offline typed-wire run assessment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.assess_typed_wire_runs import _run, summarize


IDENTITY = {
    "processId": 9752,
    "processStartUtcTicks": 639294897826627677,
    "executableSha256": "A" * 64,
}


def report(status: str, *, before_sequence: int = 10, after_sequence: int = 12,
           player: str = "u0123", before_completed: str = "2026-11-06T12:00:01Z",
           after_started: str = "2026-11-06T12:00:09Z") -> dict:
    selected = None
    advances = None
    if status == "advanced-in-covered-scope":
        selected = {
            "before": {"sequence": before_sequence, "frameTime": 100.0,
                       "playerUnitId": player, "xyz": {"x": 1, "y": 2, "z": 3}},
            "after": {"sequence": after_sequence, "frameTime": 102.0,
                      "playerUnitId": player, "xyz": {"x": 1, "y": 2, "z": 3}},
        }
        advances = {"sequenceDelta": after_sequence - before_sequence,
                    "frameTimeDelta": 2.0}
    return {
        "schemaVersion": 1,
        "evidenceKind": "typed-wire-snapshot-inspection/1",
        "status": status,
        "reason": "fixture",
        "identity": IDENTITY,
        "source": {
            "before": {"snapshotSha256": "B" * 64,
                       "startedAtUtc": "2026-11-06T12:00:00Z",
                       "completedAtUtc": before_completed},
            "after": {"snapshotSha256": "C" * 64,
                      "startedAtUtc": after_started,
                      "completedAtUtc": "2026-11-06T12:00:22Z"},
        },
        "selected": selected,
        "advances": advances,
    }


class TypedWireRunAssessmentTests(unittest.TestCase):
    def test_run_manifest_binds_exact_snapshot_and_request_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            request = b'{"request":1}\n'
            snapshot = b'{"snapshot":1}\n'
            (run / "capture-01.request.json").write_bytes(request)
            (run / "capture-01.snapshot.json").write_bytes(snapshot)
            index = {
                "schemaVersion": 1,
                "evidenceKind": "native-typed-inline-capture/1",
                "status": "partial",
                "publishedSnapshots": 1,
                "candidates": [{
                    "requestFile": "capture-01.request.json",
                    "requestSha256": hashlib.sha256(request).hexdigest().upper(),
                    "snapshotFile": "capture-01.snapshot.json",
                    "snapshotSha256": hashlib.sha256(snapshot).hexdigest().upper(),
                }],
            }
            (run / "index.json").write_text(json.dumps(index), encoding="utf-8")
            _, snapshots, bindings = _run(run, "fixture")
            self.assertEqual([item.name for item in snapshots], ["capture-01.snapshot.json"])
            self.assertEqual(bindings["capture-01.snapshot.json"], index["candidates"][0]["snapshotSha256"])
            (run / "capture-01.snapshot.json").write_bytes(snapshot + b" ")
            with self.assertRaisesRegex(ValueError, "manifest-bound capture bytes differ"):
                _run(run, "fixture")

    def test_selects_latest_advancing_pair_inside_declared_window(self):
        older = report("advanced-in-covered-scope", after_sequence=12)
        latest = report("advanced-in-covered-scope", before_sequence=20, after_sequence=24)
        latest["selected"]["before"]["frameTime"] = 200.0
        latest["selected"]["after"]["frameTime"] = 204.0
        result = summarize(
            [("older.json", older), ("latest.json", latest),
             ("blocked.json", report("blocked"))],
            maximum_run_gap_seconds=10.0)
        self.assertEqual(result["status"], "advancing-reference-in-pairing-window")
        self.assertEqual(result["selectedDiagnostic"], "latest.json")
        self.assertEqual(result["playerUnitId"], "u0123")
        self.assertEqual(result["diagnostics"], {
            "total": 3, "advancing": 2, "advancingWithinWindow": 2,
            "blocked": 1, "unavailable": 0})

    def test_preserves_advancing_evidence_but_rejects_pairing_window(self):
        result = summarize(
            [("pair.json", report(
                "advanced-in-covered-scope", after_started="2026-11-06T12:00:13.5Z"))],
            maximum_run_gap_seconds=10.0)
        self.assertEqual(result["status"], "advancing-reference-outside-pairing-window")
        self.assertFalse(result["pairingWindow"]["withinWindow"])

    def test_no_advancing_pair_is_explicit(self):
        result = summarize(
            [("blocked.json", report("blocked")),
             ("unavailable.json", report("unavailable"))],
            maximum_run_gap_seconds=10.0)
        self.assertEqual(result["status"], "no-advancing-reference")
        self.assertIsNone(result["selectedDiagnostic"])
        self.assertEqual(result["diagnostics"], {
            "total": 2, "advancing": 0, "advancingWithinWindow": 0,
            "blocked": 1, "unavailable": 1})

    def test_run_index_gap_cannot_hide_out_of_window_selected_snapshots(self):
        # A run envelope could appear only three seconds apart while the exact
        # selected snapshot pair is twenty seconds apart. The diagnostic-bound
        # snapshot times, not caller-supplied run timing, control the result.
        adversarial = report(
            "advanced-in-covered-scope",
            before_completed="2026-11-06T12:00:01Z",
            after_started="2026-11-06T12:00:21Z",
        )
        result = summarize(
            [("adversarial.json", adversarial)], maximum_run_gap_seconds=10.0)
        self.assertEqual(result["status"], "advancing-reference-outside-pairing-window")
        self.assertEqual(result["pairingWindow"]["selectedSnapshotGapSeconds"], 20.0)
        self.assertFalse(result["pairingWindow"]["withinWindow"])

    def test_malformed_inspector_contract_fails_closed(self):
        malformed = report("advanced-in-covered-scope")
        malformed["schemaVersion"] = 2
        with self.assertRaisesRegex(ValueError, "contract or status"):
            summarize([("malformed.json", malformed)], maximum_run_gap_seconds=10.0)


class ReferenceBindingAssessmentTests(unittest.TestCase):
    def test_older_advancing_pair_does_not_hide_drift_diagnostic(self):
        nonce = "a" * 32
        good = report("advanced-in-covered-scope")
        for row in good["selected"].values():
            row.update(protocol="RR2R1", addon="RiftReader2", addonVersion="0.2.0",
                       source="rift-api", sessionId=nonce, epoch=1)
        for reason in ("source-epoch-changed", "player-identity-changed", "before:malformed-complete-frame"):
            blocked = report("blocked")
            blocked["reason"] = reason
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "diagnostic-failed"):
                summarize([("good", good), ("blocked", blocked)], maximum_run_gap_seconds=15, session_id=nonce)

    def test_session_mode_rejects_legacy_foreign_nonce_and_epoch(self):
        nonce = "a" * 32
        legacy = report("advanced-in-covered-scope")
        with self.assertRaises(ValueError):
            summarize([("legacy", legacy)], maximum_run_gap_seconds=15, session_id=nonce)
        for row in legacy["selected"].values():
            row.update(protocol="RR2R1", addon="RiftReader2", addonVersion="0.2.0",
                       source="rift-api", sessionId=nonce, epoch=1)
        result = summarize([("rr2", legacy)], maximum_run_gap_seconds=15, session_id=nonce)
        self.assertEqual(result["status"], "advancing-reference-in-pairing-window")
        for changes in ({"sessionId": "b" * 32}, {"epoch": 2}):
            value = json.loads(json.dumps(legacy))
            value["selected"]["after"].update(changes)
            with self.assertRaises(ValueError):
                summarize([("bad", value)], maximum_run_gap_seconds=15, session_id=nonce)


if __name__ == "__main__":
    unittest.main()
