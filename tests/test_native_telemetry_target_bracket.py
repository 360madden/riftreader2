"""Exact-source optional native target endpoint replay and collector contract tests.

All target A->B->A observations below are synthetic. No game input or process
access is performed by this test suite.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import replay_physical_telemetry_target as replay
from scripts import capture_physical_telemetry_zone as collect
from scripts import replay_physical_telemetry_zone as zone
from tests.test_physical_player_xyz_bracket import fixture
from tests.test_replay_physical_telemetry_target import TargetSequenceTests, A, B
from tests.test_replay_physical_telemetry_zone import ZONE
from tests.test_capture_physical_telemetry_zone import HOST, CaptureTests, FakeProcess

SELF = 0x035400012FA2D207


class NativeTargetSourceTests(unittest.TestCase):
    def setUp(self):
        self.case = TargetSequenceTests("test_valid_no_target_source_baseline_is_explicit_candidate")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.fx = self.case.fx
        self.original_zone_identity = self.fx.natives["before"]["observation"]["identity"]

    def attach(self, *, before_id=None, after_id=None):
        out = self.fx.folder
        context, _, _, _ = fixture()
        for label, start, stop, value in (
                ("before", "2026-11-20T10:50:11.1200000Z",
                 "2026-11-20T10:50:11.1500000Z", before_id),
                ("after", "2026-11-20T10:50:12.5000000Z",
                 "2026-11-20T10:50:12.6000000Z", after_id)):
            body = deepcopy(context)
            row = body["observation"]
            row["identity"] = deepcopy(self.original_zone_identity)
            row["startedAtUtc"], row["completedAtUtc"] = start, stop
            row["unitKey"] = SELF
            if value is not None:
                native_int = int(value[1:], 16)
                row.update(rawFallbackKey=native_int,
                           targetStatus="fallback-key-candidate",
                           targetKeyCandidate=native_int,
                           targetUnitIdCandidate=value)
            path = out / f"native-target-{label}.json"
            path.write_text(json.dumps(body), encoding="utf-8")
            values = zone.physical_rift._native_values("player-context", body)
            self.fx.record["nativeTargetBefore" if label == "before" else "nativeTargetAfter"] = {
                "source": str(path),
                "sha256": zone.digest(path.read_bytes()),
                "unitKeyCandidate": values["unitKey"],
                "targetStatus": values["target"]["status"],
                "targetUnitIdCandidate": values["target"]["unitIdCandidate"],
                "startedAtUtc": start,
                "completedAtUtc": stop,
            }
        self.fx.save()

    def test_native_raw_zero_and_lua_none_are_compatible_candidates(self):
        self.attach()
        x = replay.replay(self.fx.summary)
        self.assertEqual(x["status"], "no-target-baseline-candidate")
        value = x["nativeTargetComparison"]
        self.assertEqual(value["status"], "matching-endpoint-candidates")
        self.assertEqual(value["before"]["comparison"],
                         "lua-none-vs-native-zero-candidate")
        self.assertEqual(value["after"]["comparison"],
                         "lua-none-vs-native-zero-candidate")
        self.assertIn("not independent no-target proof", value["qualification"])
        self.assertEqual(len(value["before"]["sourceSha256"]), 64)

    def test_selected_native_a_and_lua_a_b_a_agree_on_endpoints_only(self):
        self.case.change({(1,1): A, (1,2): B, (2,1): B, (2,2): A})
        self.attach(before_id=A, after_id=A)
        x = replay.replay(self.fx.summary)
        self.assertEqual(x["status"], "a-b-a-target-candidate")
        self.assertEqual(x["nativeTargetComparison"]["status"], "matching-endpoint-candidates")
        self.assertEqual(x["nativeTargetComparison"]["before"]["comparison"],
                         "matched-id-candidate")
        self.assertIn("sequential", x["qualification"])

    def test_different_lua_endpoint_from_native_is_reported_not_hidden(self):
        self.case.change({(1,1): A, (1,2): B, (2,1): B, (2,2): B})
        self.attach(before_id=A, after_id=A)
        x = replay.replay(self.fx.summary)
        self.assertEqual(x["status"], "selected-target-observations-candidate")
        self.assertEqual(x["nativeTargetComparison"]["status"], "different-endpoint-candidates")
        self.assertEqual(x["nativeTargetComparison"]["after"]["comparison"],
                         "different-id-candidate")

    def test_partial_or_fabricated_native_bracket_refused(self):
        self.attach()
        del self.fx.record["nativeTargetAfter"]
        self.fx.save()
        with self.assertRaisesRegex(ValueError, "partial-native-target-bracket"):
            replay.replay(self.fx.summary)

    def test_changed_native_source_without_sha_update_refused(self):
        self.attach()
        path = self.fx.folder / "native-target-after.json"
        source = json.loads(path.read_text())
        source["observation"]["rawFallbackKey"] = 123
        path.write_text(json.dumps(source))
        with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
            replay.replay(self.fx.summary)

    def test_rehashed_different_native_module_refused(self):
        self.attach()
        path = self.fx.folder / "native-target-after.json"
        source = json.loads(path.read_text())
        source["observation"]["identity"]["moduleBaseAddress"] += 8192
        path.write_text(json.dumps(source))
        self.fx.record["nativeTargetAfter"]["sha256"] = zone.digest(path.read_bytes())
        self.fx.save()
        with self.assertRaisesRegex(ValueError, "native-target-process-module-mismatch"):
            replay.replay(self.fx.summary)

    def test_native_target_outside_lua_bracket_refused(self):
        self.attach()
        path = self.fx.folder / "native-target-before.json"
        source = json.loads(path.read_text())
        source["observation"]["startedAtUtc"] = "2026-11-20T10:50:11.9990000Z"
        source["observation"]["completedAtUtc"] = "2026-11-20T10:50:12.0100000Z"
        path.write_text(json.dumps(source))
        self.fx.record["nativeTargetBefore"].update(
            sha256=zone.digest(path.read_bytes()),
            startedAtUtc=source["observation"]["startedAtUtc"],
            completedAtUtc=source["observation"]["completedAtUtc"])
        self.fx.save()
        with self.assertRaisesRegex(ValueError, "native-target-not-bracketed"):
            replay.replay(self.fx.summary)

    def test_capture_native_target_uses_real_single_shot_contract(self):
        with TemporaryDirectory() as tmp:
            sel = CaptureTests("test_exact_1179_admission_and_wrong_build_refusal")
            sel.setUp()
            source, _, _, _ = fixture()
            row = source["observation"]
            row["identity"]["executableSha256"] = zone.SHA_1179
            row["identity"]["processStartUtcTicks"] = int(sel.target["processStartUtcTicks"])
            row["identity"]["processId"] = sel.target["processId"]
            row["identity"]["executablePath"] = sel.target["executablePath"]
            row["unitKey"] = SELF
            def read(s, kind, *, output):
                self.assertEqual(kind, "player-context")
                Path(output).write_text(json.dumps(source), encoding="utf-8")
                return {"status": "complete", "target": s["target"],
                        "nativeRead": kind, "nativeOutput": str(output),
                        # The real player-context reader omits nativeSourceSha256.
                        "nativeValues": zone.physical_rift._native_values(kind, source)}
            with patch.object(collect.physical_rift, "read_native", side_effect=read):
                result = collect.native_target(sel.selection, Path(tmp), "before")
            self.assertEqual(result["sha256"], zone.digest((Path(tmp) / "native-target-before.json").read_bytes()))
            self.assertEqual(result["targetStatus"], "raw-getter-zero-candidate")
            self.assertEqual(result["unitKeyCandidate"], str(SELF))
            self.assertEqual(result["targetUnitIdCandidate"], None)
            self.assertTrue((Path(tmp)/"native-target-before.json").is_file())

            def forged_hash(s, kind, *, output):
                receipt = read(s, kind, output=output)
                return {**receipt, "nativeSourceSha256": "F" * 64}

            with patch.object(collect.physical_rift, "read_native", side_effect=forged_hash):
                with self.assertRaisesRegex(ValueError, "native-target-source-hash-mismatch"):
                    collect.native_target(sel.selection, Path(tmp), "after")

    def test_invalid_native_target_option_blocks_before_host_or_game(self):
        with patch.object(collect, "admission") as admission:
            with self.assertRaisesRegex(ValueError, "invalid-native-target-option"):
                collect.collect(123, Path("unused"), include_native_target=1)
            admission.assert_not_called()


    def test_opted_in_native_target_capture_orders_both_sources_around_lua(self):
        basic = CaptureTests("test_exact_1179_admission_and_wrong_build_refusal")
        basic.setUp()
        events = []
        source, _, _, _ = fixture()
        row = source["observation"]
        row["identity"].update(
            executableSha256=basic.target["executableSha256"],
            processStartUtcTicks=int(basic.target["processStartUtcTicks"]),
            processId=basic.target["processId"], executablePath=basic.target["executablePath"])
        row["unitKey"] = SELF

        def native(sel, kind, *, output, native_reader):
            self.assertEqual(native_reader, published)
            events.append(kind + "-" + Path(output).name)
            if kind == "zone-context":
                return basic._fake_native(sel, kind, output)
            Path(output).write_text(json.dumps(source), encoding="utf-8")
            return {"status": "complete", "target": sel["target"],
                    "nativeRead": kind, "nativeOutput": str(output),
                    "nativeValues": zone.physical_rift._native_values(kind, source)}

        def scan(fake, path, **kwargs):
            events.append(path.name)
            path.mkdir()
            number = 1 if path.name == "pass-01" else 2
            return {"startedAtUtc": f"2026-11-20T10:50:{number + 10:02d}Z",
                    "completedAtUtc": f"2026-11-20T10:50:{number + 10:02d}.5Z",
                    "readBytes": collect.CHUNK,
                    "failedChunks": 0,
                    "hits": 2,
                    "frames": [{"addr": "0x13000001", "seq": number,
                                "epoch": 40, "session": "a" * 32,
                                "clock": float(number),
                                "zoneId": ZONE, "sha": f"{number:064X}"},
                               {"addr": "0x13000002", "seq": number + 1,
                                "epoch": 40, "session": "a" * 32,
                                "clock": float(number + 1),
                                "zoneId": ZONE, "sha": f"{number+1:064X}"}]}

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "bundle"
            published = Path(tmp) / "RiftReader2.Live.exe"
            published.write_bytes(b"reader")
            with (patch.object(collect.socket, "gethostname", return_value=HOST),
                  patch.object(collect.physical_rift, "select_physical",
                               return_value=basic.selection),
                  patch.object(collect.physical_rift, "read_native", side_effect=native),
                  patch.object(collect, "scan", side_effect=scan),
                  patch.object(collect.verify, "replay",
                               return_value={"status": "matching-candidates"}),
                  patch.object(collect.target_audit, "replay",
                               return_value={"nativeTargetComparison": {
                                   "status": "matching-endpoint-candidates"}}) as target_replay,
                  patch.object(collect.time, "sleep")):
                path, report = collect.collect(
                    123, dest, scan_bytes=collect.CHUNK, gap_ms=0,
                    include_native_target=True, reader_factory=FakeProcess,
                    native_reader=published)
            self.assertTrue(path.is_file())
            self.assertEqual(report["nativeTargetBefore"]["targetStatus"],
                             "raw-getter-zero-candidate")
            self.assertEqual(report["nativeTargetAfter"]["targetUnitIdCandidate"], None)
            self.assertEqual(events, [
                "zone-context-native-before.json", "player-context-native-target-before.json",
                "pass-01", "pass-02", "player-context-native-target-after.json",
                "zone-context-native-after.json"
            ])
            target_replay.assert_called_once_with(path)

    def test_native_target_player_mismatch_blocks_before_lua_scan(self):
        basic = CaptureTests("test_exact_1179_admission_and_wrong_build_refusal")
        basic.setUp()
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "bundle"
            with (patch.object(collect.socket, "gethostname", return_value=HOST),
                  patch.object(collect.physical_rift, "select_physical",
                               return_value=basic.selection),
                  patch.object(collect.physical_rift, "read_native",
                               side_effect=basic._fake_native),
                  patch.object(collect, "native_target", return_value={
                      "unitKeyCandidate": "1",
                      "targetStatus": "raw-getter-zero-candidate",
                      "targetUnitIdCandidate": None}),
                  patch.object(collect, "scan") as scan):
                with self.assertRaisesRegex(ValueError,
                                            "native-target-player-changed-before"):
                    collect.collect(123, dest, scan_bytes=collect.CHUNK, gap_ms=0,
                                    include_native_target=True)
                scan.assert_not_called()
            self.assertTrue((dest / "native-before.json").is_file())
            self.assertFalse((dest / "summary.json").exists())

if __name__ == "__main__":
    unittest.main()
