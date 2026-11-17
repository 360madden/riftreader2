"""No-process tests for the physical-native composite player-state collector."""
from __future__ import annotations
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import collect_physical_player_state as state

OWNER = {
    "hostName": state.HOST, "processId": 123,
    "processStartUtcTicks": "639300936028818696",
    "executableSha256": state.BUILD_SHA,
    "hwnd": 789, "executablePath": r"C:\Games\RIFT\rift_x64.exe",
}
SELECTION = {"status": "ready", "ownerHost": state.HOST, "target": OWNER}


class StateTests(unittest.TestCase):
    def fake_read(self, selection, kind, path, *, samples, interval_ms,
                  key="239816685251645959", module=123456, epoch=None):
        identity = {
            "processId": OWNER["processId"],
            "processStartUtcTicks": int(epoch or OWNER["processStartUtcTicks"]),
            "executableSha256": selection["target"]["executableSha256"].upper(),
            "moduleBaseAddress": module, "moduleSize": 1234567,
        }
        path.write_text(json.dumps({"status": "complete", "identity": identity,
                                    "completedSamples": samples}), encoding="utf-8")
        source_sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        burst = {"status": "candidate-only", "sourceReportSha256": source_sha,
                 "sourceBuildSha256": selection["target"]["executableSha256"].upper(),
                 "processId": OWNER["processId"],
                 "processStartUtcTicks": OWNER["processStartUtcTicks"],
                 "unitKey": key, "sampleCount": samples}
        return {"status": "complete", "nativeRead": kind, "target": selection["target"],
                "nativeOutput": str(path),
                "nativeValues": {"unitKey": key, "x": 5.2},
                **({"nativeBurstSummary": burst}
                   if kind == "vitals" else {})}

    def test_three_existing_native_readers_produce_hashed_same_owner_receipt(self):
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical",
                          return_value=SELECTION) as select, \
             patch.object(state.physical_rift, "read_native", side_effect=self.fake_read) as read:
            path, report = state.collect(123, Path(temp) / "result", samples=3)
            self.assertEqual(select.call_count, 7)
            self.assertEqual(read.call_count, 3)
            self.assertEqual([call.args[1] for call in read.call_args_list], list(state.KINDS))
            self.assertEqual(report["status"], "complete-candidate")
            self.assertEqual(report["selfKeyCandidate"], "239816685251645959")
            self.assertIn("NOT atomic", report["qualification"])
            self.assertEqual(json.loads(path.read_text()), report)
            for row in report["sources"].values():
                self.assertEqual(row["samples"], 3)
                self.assertEqual(hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest().upper(),
                                 row["sourceSha256"])

    def test_updated_build_collects_three_sources_and_refuses_unqualified_stats(self):
        updated = deepcopy(SELECTION)
        updated["target"]["executableSha256"] = next(
            sha for sha in state.SUPPORTED_BUILDS if sha != state.BUILD_SHA)
        with (TemporaryDirectory() as temp,
              patch.object(state.socket, "gethostname", return_value=state.HOST),
              patch.object(state.physical_rift, "select_physical", return_value=updated),
              patch.object(state.physical_rift, "read_native", side_effect=self.fake_read) as read):
            path, report = state.collect(123, Path(temp) / "updated", samples=2)
            self.assertEqual(set(report["sources"]), set(state.KINDS))
            self.assertEqual(report["target"]["executableSha256"],
                             updated["target"]["executableSha256"])
            self.assertEqual(json.loads(path.read_text()), report)
            self.assertEqual(read.call_count, 3)
            with self.assertRaisesRegex(ValueError, "postpatch-stats-unqualified"):
                state.collect(123, Path(temp) / "refused", include_stats=True)
            self.assertFalse((Path(temp) / "refused").exists())
            self.assertEqual(read.call_count, 3)

    def stats_read(self, selection, kind, path, **options):
        self.assertEqual(kind, "stats")
        self.assertEqual(options, {})  # Stats reader does not accept burst options.
        fields = (("armor", 37), ("powerAttack", 24), ("powerSpell", 32),
                  ("critAttack", 26), ("critSpell", 33), ("strength", 5),
                  ("dexterity", 1), ("intelligence", 3), ("wisdom", 4),
                  ("endurance", 2), ("resistLife", 35), ("resistDeath", 36),
                  ("resistFire", 38), ("resistWater", 39), ("resistEarth", 40),
                  ("resistAir", 41), ("hit", 31), ("critPower", 83),
                  ("block", 27), ("dodge", 30))
        mapping = [-1] * 84
        rows = []
        for index, (name, selector) in enumerate(fields):
            mapping[selector] = index
            value = {"status": "raw-candidate", "rawSigned64": 100 + index,
                     "doubleCandidate": float(100 + index),
                     "precision": "exact-integer-range"}
            rows.append({"name": name, "selector": selector, "mappedIndex": index,
                         "ordinary": value.copy(), "unbuffed": value.copy()})
        source = {
            "schemaVersion": 1, "contractVersion": "native-current-stats-candidate/1",
            "status": "complete", "observation": {
                "identity": {"processId": OWNER["processId"],
                             "processStartUtcTicks": int(OWNER["processStartUtcTicks"]),
                             "executableSha256": state.BUILD_SHA,
                             "moduleBaseAddress": 123456, "moduleSize": 1234567},
                "unitKey": 239816685251645959,
                "startedAtUtc": "2026-11-15T18:00:03Z",
                "completedAtUtc": "2026-11-15T18:00:04Z",
                "qualification": "raw typed stat candidates; API availability, units, freshness and restart unverified",
                "selectorMapCandidate": mapping, "stats": rows,
            },
        }
        path.write_text(json.dumps(source), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"status": "complete", "nativeRead": kind, "target": selection["target"],
                "nativeOutput": str(path), "nativeSourceSha256": digest,
                "nativeValues": state.physical_rift._native_values("stats", source)}

    def test_opt_in_stats_joins_same_owner_with_one_shot_and_pinned_values(self):
        def fake(selection, kind, path, **options):
            if kind == "stats":
                return self.stats_read(selection, kind, path, **options)
            return self.fake_read(selection, kind, path, **options)
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION) as select, \
             patch.object(state.physical_rift, "read_native", side_effect=fake) as read:
            path, report = state.collect(123, Path(temp) / "out", samples=2, include_stats=True)
            self.assertEqual(select.call_count, 9)
            self.assertEqual(read.call_count, 4)
            self.assertEqual(set(report["sources"]), set(state.KINDS) | {"stats"})
            self.assertEqual(report["sources"]["stats"]["samples"], 1)
            self.assertEqual(report["sources"]["stats"]["candidateValues"]["selectorCount"], 20)
            self.assertEqual(json.loads(path.read_text()), report)

    def test_stats_wrong_source_digest_is_refused_before_summary(self):
        def fake(selection, kind, path, **options):
            if kind == "stats":
                result = self.stats_read(selection, kind, path, **options)
                result["nativeSourceSha256"] = "0" * 64
                return result
            return self.fake_read(selection, kind, path, **options)
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "stats-source-identity-invalid"):
                state.collect(123, dest, include_stats=True)
            self.assertFalse((dest / "summary.json").exists())

    def test_include_stats_cli_shows_all_source_pinned_raw_candidates(self):
        report = {
            "status": "complete-candidate", "target": OWNER,
            "selfKeyCandidate": "239816685251645959",
            "qualification": "Sequential read-only native candidates, unqualified",
            "sources": {
                "player-context": {"sourceSha256": "A" * 64, "candidateValues": {}},
                "position": {"sourceSha256": "B" * 64, "candidateValues": {}},
                "vitals": {"sourceSha256": "C" * 64, "candidateValues": {}},
                "stats": {"sourceSha256": "D" * 64,
                          "candidateValues": {"status": "candidate-only", "selectorCount": 20,
                                              "stats": [{"name": "armor", "ordinary": {"rawSigned64": 4156}}]}},
            },
        }
        output = StringIO()
        with patch.object(state, "collect", return_value=(Path("fresh/summary.json"), report)) as collect, \
             redirect_stdout(output):
            self.assertEqual(0, state.main(["--physical-pid", "123", "--include-stats"]))
        collect.assert_called_once()
        self.assertTrue(collect.call_args.kwargs["include_stats"])
        shown = json.loads(output.getvalue())
        self.assertEqual(20, shown["statsCandidate"]["selectorCount"])
        self.assertEqual(4156, shown["statsCandidate"]["stats"][0]["ordinary"]["rawSigned64"])
        self.assertEqual("D" * 64, shown["sources"]["stats"])

    def test_wrong_host_or_invalid_pid_never_reads_process(self):
        with patch.object(state.socket, "gethostname", return_value="OTHER"), \
             patch.object(state.physical_rift, "select_physical") as select:
            with self.assertRaisesRegex(ValueError, "wrong-host"):
                state.collect(123, Path("unused"))
            select.assert_not_called()
        with patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical") as select:
            with self.assertRaisesRegex(ValueError, "explicit-pid-required"):
                state.collect(0, Path("unused"))
            select.assert_not_called()

    def test_unavailable_or_wrong_build_never_reads(self):
        invalid = deepcopy(SELECTION)
        invalid["target"]["executableSha256"] = "0" * 64
        with patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=invalid), \
             patch.object(state.physical_rift, "read_native") as read:
            with self.assertRaisesRegex(ValueError, "physical-process-identity-unavailable"):
                state.collect(123, Path("unused"))
            read.assert_not_called()

    def test_changed_epoch_between_readers_refused(self):
        changed = deepcopy(SELECTION)
        changed["target"]["processStartUtcTicks"] = "11111"
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical",
                          side_effect=[SELECTION, SELECTION, changed]), \
             patch.object(state.physical_rift, "read_native", side_effect=self.fake_read) as read:
            with self.assertRaisesRegex(ValueError, "epoch-changed-after-read"):
                state.collect(123, Path(temp) / "out")
            self.assertEqual(read.call_count, 1)

    def test_cross_source_unit_key_change_is_rejected(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            key = "555" if kind == "position" else "444"
            return self.fake_read(selection, kind, path, samples=samples,
                                  interval_ms=interval_ms, key=key)
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake) as read:
            with self.assertRaisesRegex(ValueError, "self-key-changed"):
                state.collect(123, Path(temp) / "out")
            self.assertEqual(read.call_count, 2)

    def test_changed_module_is_rejected(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            return self.fake_read(selection, kind, path, samples=samples,
                                  interval_ms=interval_ms,
                                  module=987 if kind == "position" else 123456)
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake):
            with self.assertRaisesRegex(ValueError, "module-owner-changed"):
                state.collect(123, Path(temp) / "out")

    def test_duplicate_source_owner_key_is_rejected_before_summary(self):
        def ambiguous(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace('"processId": 123',
                                        '"processId": 999, "processId": 123', 1),
                            encoding="utf-8")
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=ambiguous):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_nonfinite_source_json_is_rejected_before_summary(self):
        def nonfinite(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace('"status": "complete"',
                                        '"untrusted": NaN, "status": "complete"', 1),
                            encoding="utf-8")
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=nonfinite):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "nonfinite-json"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_vitals_burst_claiming_another_source_is_rejected_before_summary(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            if kind == "vitals":
                result["nativeBurstSummary"]["sourceReportSha256"] = "0" * 64
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "vitals-burst-source-mismatch"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_vitals_burst_claiming_different_process_epoch_is_rejected(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            if kind == "vitals":
                result["nativeBurstSummary"]["processStartUtcTicks"] = "111"
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "vitals-burst-source-mismatch"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_reader_unavailable_does_not_publish_complete_summary(self):
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", return_value={"status": "blocked"}):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "player-context-read-unavailable"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_invalid_bounds_do_not_select_process(self):
        with patch.object(state, "pin") as select:
            for samples, interval in ((1, 0), (11, 0), (3, -1), (3, 1001)):
                with self.subTest(samples=samples, interval=interval):
                    with self.assertRaisesRegex(ValueError, "invalid-sampling-bounds"):
                        state.collect(123, Path("unused"), samples=samples, interval_ms=interval)
            select.assert_not_called()

    def test_relative_output_directory_is_rooted_locally(self):
        with TemporaryDirectory() as temp, \
             patch.object(state, "ROOT", Path(temp)), \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=self.fake_read):
            path, report = state.collect(123, Path("result"))
            self.assertEqual(path, Path(temp) / "result" / "summary.json")
            self.assertEqual(report["sources"]["position"]["samples"], 3)

    def test_cli_exposes_actual_native_candidates_without_claiming_qualification(self):
        report = {
            "status": "complete-candidate", "selfKeyCandidate": "239816685251645959",
            "target": OWNER, "qualification": "Native candidates only; no Lua validation.",
            "sources": {
                "player-context": {"sourceSha256": "a" * 64, "candidateValues": {
                    "level": {"status": "numeric-getter-and-presentation-candidate", "rawCandidate": 45},
                    "calling": {"rawCandidate": 1, "nameCandidate": "warrior"},
                    "combat": {"status": "raw-byte-candidate", "candidate": False},
                    "target": {"status": "raw-getter-zero-candidate", "unitIdCandidate": None},
                }},
                "position": {"sourceSha256": "b" * 64, "candidateValues": {
                    "x": 7192.7124, "y": 874.0665, "z": 3018.9937,
                    "refreshGuardStatus": "guard-ineligible-candidate",
                }},
                "vitals": {"sourceSha256": "c" * 64, "candidateValues": {
                    "health": {"status": "calculated-candidate", "current": 18208, "maximum": 18208},
                    "mana": {"status": "unavailable", "current": None},
                    "energy": {"status": "unavailable", "current": None},
                }},
            },
        }
        output = StringIO()
        with patch.object(state, "collect", return_value=(Path("fresh/summary.json"), report)), \
             redirect_stdout(output):
            self.assertEqual(0, state.main(["--physical-pid", "123"]))
        shown = json.loads(output.getvalue())
        self.assertEqual(123, shown["processId"])
        self.assertEqual("7192.7124", str(shown["positionCandidate"]["x"]))
        self.assertEqual(45, shown["playerContextCandidate"]["level"]["rawCandidate"])
        self.assertEqual("raw-getter-zero-candidate", shown["playerContextCandidate"]["target"]["status"])
        self.assertIsNone(shown["playerContextCandidate"]["target"]["unitIdCandidate"])
        self.assertEqual(18208, shown["vitalsCandidate"]["health"]["current"])
        self.assertEqual("unavailable", shown["vitalsCandidate"]["energy"]["status"])
        self.assertEqual("a" * 64, shown["sources"]["player-context"])
        self.assertEqual(report["qualification"], shown["qualification"])


if __name__ == "__main__":
    unittest.main()
