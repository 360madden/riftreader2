"""Synthetic complete-bundle tests for opt-in Power and native Experience."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import collect_physical_player_state as state
from scripts import replay_physical_player_state as replay
from tests.test_physical_player_context_projection import report as context_report
from tests.test_summarize_native_vitals_burst import field, unavailable
from tests.test_native_experience_values_validation import updated_fixture

HOST = "RIFT-STATION"
KEY = 239816685251645959
SHA = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
IDENTITY = {
    "processId": 123, "processStartUtcTicks": 638000000000000001,
    "executableSha256": SHA, "executablePath": r"C:\Games\RIFT\rift_x64.exe",
    "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000,
}
OWNER = {**IDENTITY, "hostName": HOST, "hwnd": 1234,
         "processStartUtcTicks": str(IDENTITY["processStartUtcTicks"])}
SELECTION = {"status": "ready", "target": OWNER, "ownerHost": HOST}


class PowerStateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.output = self.root / "state"
        self.enterContext(patch.dict("os.environ", {
            "RR2_PHYSICAL_TOOLS_ROOT": "debug", "RR2_NATIVE_READER": "",
        }))
        self.enterContext(patch.object(state.socket, "gethostname", return_value=HOST))
        self.select = self.enterContext(patch.object(state.physical_rift, "select_physical",
                                                     return_value=deepcopy(SELECTION)))
        self.reads = []
        self.change = None
        self.read = self.enterContext(patch.object(state.physical_rift, "read_native",
                                                   side_effect=self.fake_read))

    def fake_read(self, selection, kind, path, *, samples=None, interval_ms=None, **options):
        # This fixture only writes offline reports; it never starts the reader.
        index = len(self.reads)
        self.reads.append(path.stem)
        rows = []
        start = datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc)
        if kind == "experience-values":
            self.assertIsNone(samples)
            self.assertIsNone(interval_ms)
            source = updated_fixture()
            o = source["observation"]
            t = start + timedelta(seconds=index*5)
            for row in (o, o["seed"]):
                row.update(identity=IDENTITY.copy(), startedAtUtc=t.isoformat(),
                           completedAtUtc=(t+timedelta(milliseconds=100)).isoformat())
            o["seed"]["unitKey"] = KEY
            o.update(valueStatus="raw-values-candidate", mode=2,
                     needed=500, accumulatedCandidate=300)
            return self.save_source(selection, kind, path, source)
        for n in range(samples):
            t = start + timedelta(seconds=index*5+n)
            times = {"startedAtUtc": t.isoformat(),
                     "completedAtUtc": (t+timedelta(milliseconds=100)).isoformat()}
            if kind == "player-context":
                row = dict(context_report()["observation"], identity=IDENTITY.copy(),
                           unitKey=KEY, **times)
            elif kind == "position":
                row = dict(unitKey=str(KEY), x=1.0, y=2.0, z=3.0, **times)
            elif kind == "vitals":
                row = dict(identity=IDENTITY.copy(), unitKey=KEY, resourceKindCandidate=1,
                           health=field(100, 100), mana=unavailable("not-mana-kind-three"),
                           energy=unavailable("not-energy-kind-four"), **times)
            elif kind == "power":
                row = dict(status="complete", reason=None, power=90+n, maximum=100,
                           baseValue=90, rate=1200, sequence=1,
                           clockSeconds=100+n, anchorSeconds=100, **times)
            else:
                raise AssertionError(kind)
            rows.append(row)
        source = {"schemaVersion": 1, "status": "complete", "identity": IDENTITY.copy(),
                  "requestedSamples": samples}
        if kind == "power":
            source.update(contractVersion="native-power-samples/1", qualification="candidate-only",
                          recipe=state.physical_rift.POWER_RECIPES[SHA], samples=rows)
        else:
            source.update(completedSamples=samples, observations=rows)
            if kind != "position":
                source["observation"] = rows[-1]
            if kind == "player-context":
                source.update(contractVersion="native-current-player-context-candidate-burst/1",
                              qualification=context_report()["qualification"])
        return self.save_source(selection, kind, path, source)

    def save_source(self, selection, kind, path, source):
        if self.change:
            self.change(path.stem, source)
        path.write_text(json.dumps(source), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"status": "complete", "nativeRead": kind, "target": selection["target"],
                "nativeOutput": str(path), "nativeSourceSha256": digest,
                "nativeValues": state.physical_rift._native_values(kind, source,
                                                                   current_acquisition=True)}

    def collect(self):
        return state.collect(123, self.output, include_power=True, samples=2)

    def test_collect_and_replay_actual_sources_without_fabricating_power_key(self):
        path, summary = self.collect()
        self.assertEqual(self.reads, ["player-context", "position", "vitals",
                                      "power", "player-context-after"])
        self.assertEqual("unavailable", summary["powerBracketCandidate"]["nativePowerUnitKeyStatus"])
        power = summary["sources"]["power"]["candidateValues"]
        self.assertNotIn("unitKey", power)
        self.assertEqual([90, 91], [row["current"] for row in power["samples"]])
        result = replay.verified_state(path)
        self.assertEqual(result["powerBracketCandidate"], summary["powerBracketCandidate"])
        self.assertEqual(result["candidateValues"]["power"], power)
        self.assertEqual(result["selfKeyCandidate"], str(KEY))

    def test_unsupported_power_build_never_reads(self):
        old = deepcopy(SELECTION)
        old["target"]["executableSha256"] = state.BUILD_SHA
        self.select.return_value = old
        with self.assertRaisesRegex(ValueError, "power-build-unsupported"):
            self.collect()
        self.read.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_changed_player_after_power_refuses_publication(self):
        def change(kind, source):
            if kind == "player-context-after":
                for row in source["observations"]:
                    row["unitKey"] = KEY+1
        self.change = change
        with self.assertRaisesRegex(ValueError, "self-key-changed"):
            self.collect()
        self.assertFalse((self.output / "summary.json").exists())

    def test_power_time_outside_context_refuses_before_publication(self):
        def change(kind, source):
            if kind == "power":
                for n, row in enumerate(source["samples"]):
                    row["startedAtUtc"] = f"2026-11-26T07:00:0{n}Z"
                    row["completedAtUtc"] = f"2026-11-26T07:00:0{n}.1Z"
        self.change = change
        with self.assertRaisesRegex(ValueError, "power-sample-time-order"):
            self.collect()
        self.assertFalse((self.output / "summary.json").exists())

    def test_replay_rejects_missing_context_and_forged_key_claim(self):
        path, summary = self.collect()
        altered = deepcopy(summary)
        altered["sources"].pop("player-context-after")
        path.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid-summary-owner"):
            replay.verified_state(path)
        altered = deepcopy(summary)
        altered["powerBracketCandidate"]["nativePowerUnitKeyStatus"] = "verified"
        path.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "power-bracket-summary-mismatch"):
            replay.verified_state(path)


    def test_experience_only_is_source_pinned_and_replayable(self):
        path, summary = state.collect(123, self.output, samples=2, include_experience=True)
        self.assertEqual(self.reads, ["player-context", "position", "vitals", "experience-values"])
        source = summary["sources"]["experience-values"]
        self.assertEqual(1, source["samples"])
        self.assertEqual(300, source["candidateValues"]["accumulatedCandidate"])
        self.assertEqual(0.6, source["candidateValues"]["progressFractionCandidate"])
        self.assertEqual(source["candidateValues"],
                         replay.verified_state(path)["candidateValues"]["experience-values"])

    def test_power_and_experience_share_the_existing_owner_checks(self):
        path, summary = state.collect(123, self.output, samples=2,
                                      include_experience=True, include_power=True)
        self.assertEqual(self.reads, ["player-context", "position", "vitals",
                                      "experience-values", "power", "player-context-after"])
        result = replay.verified_state(path)
        self.assertEqual(300, result["candidateValues"]["experience-values"]["accumulatedCandidate"])
        self.assertEqual("unavailable", result["powerBracketCandidate"]["nativePowerUnitKeyStatus"])

    def test_experience_missing_is_not_zero(self):
        def change(kind, source):
            if kind == "experience-values":
                source["observation"].update(valueStatus="provider-uninitialized",
                                             needed=None, accumulatedCandidate=None, mode=None)
        self.change = change
        path, _ = state.collect(123, self.output, samples=2, include_experience=True)
        xp = replay.verified_state(path)["candidateValues"]["experience-values"]
        self.assertEqual("provider-uninitialized", xp["valueStatus"])
        self.assertIsNone(xp["accumulatedCandidate"])
        self.assertIsNone(xp["progressFractionCandidate"])

    def test_experience_foreign_key_refuses_publication(self):
        def change(kind, source):
            if kind == "experience-values":
                source["observation"]["seed"]["unitKey"] = KEY + 1
        self.change = change
        with self.assertRaisesRegex(ValueError, "self-key-changed"):
            state.collect(123, self.output, samples=2, include_experience=True)
        self.assertFalse((self.output / "summary.json").exists())

    def test_experience_nested_epoch_mismatch_refuses_publication(self):
        def change(kind, source):
            if kind == "experience-values":
                source["observation"]["seed"]["identity"]["processStartUtcTicks"] += 1
        self.change = change
        with self.assertRaises(ValueError):
            state.collect(123, self.output, samples=2, include_experience=True)
        self.assertFalse((self.output / "summary.json").exists())

    def test_experience_earlier_timestamp_refuses_publication(self):
        def change(kind, source):
            if kind == "experience-values":
                for row in (source["observation"], source["observation"]["seed"]):
                    row.update(startedAtUtc="2026-11-26T07:00:00Z",
                               completedAtUtc="2026-11-26T07:00:01Z")
        self.change = change
        with self.assertRaisesRegex(ValueError, "experience-values-sample-time-order"):
            state.collect(123, self.output, samples=2, include_experience=True)
        self.assertFalse((self.output / "summary.json").exists())

    def test_experience_replay_rejects_forged_projection_and_source_hash(self):
        path, summary = state.collect(123, self.output, samples=2, include_experience=True)
        forged = deepcopy(summary)
        forged["sources"]["experience-values"]["candidateValues"]["accumulatedCandidate"] = 301
        path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "experience-values-candidate-projection-mismatch"):
            replay.verified_state(path)
        path.write_text(json.dumps(summary), encoding="utf-8")
        raw = self.output / "experience-values.json"
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            replay.verified_state(path)


if __name__ == "__main__":
    unittest.main()
