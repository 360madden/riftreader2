"""Offline coverage for dynamic, bounded Telemetry Lua publisher scope discovery.

No physical process access. Markers are synthetic complete Telemetry wires,
and the survey alone never qualifies an independent API/native observation.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import capture_physical_telemetry_zone as capture
from scripts import replay_physical_telemetry_zone as verify
from tests.test_capture_physical_telemetry_zone import HOST, CaptureTests, FakeRead, FakeProcess
from tests.test_replay_physical_telemetry_zone import ZoneEvidenceTests, SELF, ZONE

BASE = 0x13000000
BLOCK = capture.CHUNK
PLAYER = f"u{SELF:016X}"


def wire(seq, *, epoch, player=PLAYER, zone=ZONE, session="a" * 32,
         clock=None, zone_age=0.5):
    raw = ZoneEvidenceTests.frame(seq)
    raw["epoch"] = epoch
    raw["sessionId"] = session
    raw["playerId"] = player
    raw["playerTelemetry"]["id"] = player
    raw["frameTime"] = float(seq * 0.5 if clock is None else clock)
    raw["playerTelemetry"]["zone"]["sampledAt"] = raw["frameTime"] - zone_age
    raw["playerTelemetry"]["zone"]["id"] = zone
    return verify.PREFIX + json.dumps(raw, separators=(",", ":")).encode("ascii") + verify.SUFFIX


def reader(groups, *, scope_count=4):
    memory = bytearray(BLOCK * scope_count + capture.MAX_FRAME_BYTES)
    for index, entries in groups.items():
        for number, value in enumerate(entries, 1):
            position = index * BLOCK + 1024 + number * 4096
            memory[position:position + len(value)] = value
    return FakeRead(memory)


class AutoScopeTests(unittest.TestCase):
    def test_prefers_new_publisher_epoch_over_higher_stale_sequence(self):
        fake = reader({
            0: [wire(115000, epoch=39), wire(115001, epoch=39)],
            1: [wire(20, epoch=40), wire(21, epoch=40), wire(22, epoch=40)],
            2: [wire(115002, epoch=39), wire(115003, epoch=39)],
        })
        found = capture.survey_scopes(
            fake, start=BASE, scan_bytes=BLOCK, scope_count=4,
            expected_player=PLAYER, expected_zone=ZONE)
        self.assertEqual(found["status"], "scoped-candidate")
        self.assertEqual(found["selectedStartAddress"], f"0x{BASE + BLOCK:X}")
        self.assertEqual(found["expectedZoneIdCandidate"], ZONE)
        self.assertEqual(found["surveyedBytes"], 4 * BLOCK)
        self.assertEqual(found["scopes"][0]["topEpoch"], 39)
        self.assertEqual(found["scopes"][1]["topEpoch"], 40)
        self.assertEqual(found["scopes"][1]["validFrameCandidates"], 3)
        self.assertIn("not a source-freshness result", found["qualification"])

    def test_second_probe_prefers_actively_advancing_scope(self):
        # A cold scope's first-pass sequence is one ahead of the live scope.
        # Only the live scope publishes a new same-session generation on probe.
        old = wire(50, epoch=40)
        new = wire(52, epoch=40)
        self.assertEqual(len(old), len(new))
        fake = reader({
            0: [wire(50, epoch=40), wire(51, epoch=40)],
            1: [wire(49, epoch=40), old],
        }, scope_count=2)
        original_read = fake.read
        reads = 0

        def advancing_read(address, size):
            nonlocal reads
            if address == BASE + BLOCK and size == BLOCK:
                reads += 1
                if reads == 2:
                    position = BLOCK + 1024 + 2 * 4096
                    fake.buffer[position:position + len(old)] = new
            return original_read(address, size)

        fake.read = advancing_read
        with patch.object(capture.time, "sleep"):
            found = capture.survey_scopes(
                fake, start=BASE, scan_bytes=BLOCK, scope_count=2,
                expected_player=PLAYER, expected_zone=ZONE)
        self.assertEqual(found["selectedStartAddress"], f"0x{BASE + BLOCK:X}")
        self.assertEqual(found["selectionBasis"], "advancing-same-session-survey-candidate")
        self.assertEqual(found["surveyedBytes"], 2 * BLOCK)
        self.assertEqual(found["progressProbeReadBytes"], 2 * BLOCK)
        self.assertFalse(found["scopes"][0]["progressProbeAdvancing"])
        self.assertTrue(found["scopes"][1]["progressProbeAdvancing"])
        self.assertIn("not a source-freshness result", found["qualification"])

    def test_static_competing_scopes_remain_unqualified_survey_candidates(self):
        fake = reader({
            0: [wire(50, epoch=40), wire(51, epoch=40)],
            1: [wire(49, epoch=40), wire(50, epoch=40)],
        }, scope_count=2)
        with patch.object(capture.time, "sleep"):
            found = capture.survey_scopes(
                fake, start=BASE, scan_bytes=BLOCK, scope_count=2,
                expected_player=PLAYER, expected_zone=ZONE)
        self.assertEqual(found["selectedStartAddress"], f"0x{BASE:X}")
        self.assertEqual(found["selectionBasis"], "one-shot-generation-candidate")
        self.assertFalse(any(row["progressProbeAdvancing"]
                             for row in found["scopes"]))

    def test_wrong_player_zone_and_single_frame_are_not_admitted(self):
        fake = reader({
            0: [wire(1, epoch=40, player="u0000000000000001"),
                wire(2, epoch=40, player="u0000000000000001")],
            1: [wire(1, epoch=41, zone="z0000000CB7B53FD7"),
                wire(2, epoch=41, zone="z0000000CB7B53FD7")],
            2: [wire(1, epoch=42)]
        })
        found = capture.survey_scopes(
            fake, start=BASE, scan_bytes=BLOCK, scope_count=4,
            expected_player=PLAYER, expected_zone=ZONE)
        self.assertEqual(found["status"], "unqualified")
        self.assertIsNone(found["selectedStartAddress"])
        self.assertEqual(sum(x["candidateGenerations"] for x in found["scopes"]), 0)
        self.assertEqual(found["scopes"][2]["validFrameCandidates"], 1)

    def test_nonadvancing_source_clock_is_not_rankable(self):
        fake = reader({0: [wire(1, epoch=40, clock=100),
                           wire(2, epoch=40, clock=99)]})
        found = capture.survey_scopes(
            fake, start=BASE, scan_bytes=BLOCK, scope_count=1,
            expected_player=PLAYER, expected_zone=ZONE)
        self.assertEqual(found["status"], "unqualified")
        self.assertEqual(found["scopes"][0]["validFrameCandidates"], 2)
        self.assertEqual(found["scopes"][0]["candidateGenerations"], 0)

    def test_scope_count_invalid_or_unbounded_fails_before_reads(self):
        fake = FakeProcess(123)
        with fake:
            for n in (0, 9, 1.1, True):
                with self.subTest(count=n), self.assertRaisesRegex(
                        ValueError, "invalid-scope-count-or-range"):
                    capture.survey_scopes(
                        fake, start=BASE, scan_bytes=BLOCK, scope_count=n,
                        expected_player=PLAYER, expected_zone=ZONE)
            self.assertEqual(fake.calls, [])

    def test_auto_scope_selection_adds_source_report_before_native_bracket(self):
        helper = CaptureTests()
        helper.setUp()
        sample = deepcopy(helper.selection)
        events = []

        def native(sel, kind, *, output):
            events.append(Path(output).name)
            return helper._fake_native(sel, kind, output)

        def survey(fake, *, start, scan_bytes, scope_count, expected_player, expected_zone):
            self.assertEqual(start, BASE)
            self.assertEqual(scan_bytes, BLOCK)
            self.assertEqual(scope_count, 3)
            self.assertEqual(expected_player, PLAYER)
            self.assertEqual(expected_zone, ZONE)
            events.append("survey")
            return {"status": "scoped-candidate",
                    "selectedStartAddress": f"0x{BASE + BLOCK:X}",
                    "expectedZoneIdCandidate": ZONE, "surveyedBytes": BLOCK * 3,
                    "scopes": [{"startAddress": f"0x{BASE+BLOCK:X}",
                                "topEpoch": 40, "topSession": "a"*32}],
                    "qualification": "survey candidate only"}

        calls = []
        def scan(fake, path, **kwargs):
            events.append(path.name)
            path.mkdir()
            calls.append(kwargs["start"])
            count = len(calls)
            values = (1, 2) if count == 1 else (2, 3)
            return {"startedAtUtc": f"2026-11-20T10:50:{count + 10:02d}Z",
                    "completedAtUtc": f"2026-11-20T10:50:{count + 10:02d}.5Z",
                    "readBytes": BLOCK, "failedChunks": 0, "hits": 2,
                    "frames": [{"addr": f"0x{BASE+x:X}", "seq": x,
                                "epoch": 40, "session": "a" * 32, "clock": float(x),
                                "zoneId": ZONE, "sha": f"{x:064X}"}
                               for x in values]}

        with TemporaryDirectory() as tmp:
            destination = Path(tmp) / "record"
            with (patch.object(capture.socket, "gethostname", return_value=HOST),
                  patch.object(capture.physical_rift, "select_physical", return_value=sample),
                  patch.object(capture.physical_rift, "read_native", side_effect=native),
                  patch.object(capture, "survey_scopes", side_effect=survey),
                  patch.object(capture, "scan", side_effect=scan),
                  patch.object(capture.verify, "replay",
                               return_value={"status": "matching-candidates"}) as verified,
                  patch.object(capture.time, "sleep")):
                path, result = capture.collect(
                    123, destination, scan_bytes=BLOCK, gap_ms=0,
                    auto_scope=True, scope_count=3, reader_factory=FakeProcess)
            self.assertEqual(result["status"], "matching-candidates")
            self.assertEqual(result["scopeSurvey"]["selectedStartAddress"],
                             f"0x{BASE+BLOCK:X}")
            self.assertEqual(calls, [BASE + BLOCK, BASE + BLOCK])
            self.assertEqual(events,
                             ["native-survey-owner.json", "survey", "native-before.json",
                              "pass-01", "pass-02", "native-after.json"])
            self.assertTrue((destination / "scope-survey.json").is_file())
            self.assertTrue((destination / "native-survey-owner.json").is_file())
            self.assertEqual(json.loads(path.read_text()), result)
            verified.assert_called_once_with(path)

    def test_undiscovered_scope_preserves_survey_diagnostic_and_blocks_bracket(self):
        helper = CaptureTests()
        helper.setUp()
        selection = deepcopy(helper.selection)

        with TemporaryDirectory() as tmp:
            destination = Path(tmp) / "record"
            with (patch.object(capture.socket, "gethostname", return_value=HOST),
                  patch.object(capture.physical_rift, "select_physical", return_value=selection),
                  patch.object(capture.physical_rift, "read_native",
                               side_effect=helper._fake_native) as native,
                  patch.object(capture, "scan") as scan):
                with self.assertRaisesRegex(ValueError,
                                            "no-current-player-zone-scope-in-survey"):
                    capture.collect(
                        123, destination, scan_bytes=BLOCK, gap_ms=0,
                        auto_scope=True, scope_count=2, reader_factory=FakeProcess)
                self.assertEqual(native.call_count, 1)
                scan.assert_not_called()
            saved = json.loads((destination / "scope-survey.json").read_text())
            self.assertEqual(saved["status"], "unqualified")
            self.assertIsNone(saved["selectedStartAddress"])
            self.assertFalse((destination / "summary.json").exists())

    def test_map_discovery_passes_only_discovered_nonadjacent_scopes_to_survey(self):
        helper = CaptureTests()
        helper.setUp()
        selection = deepcopy(helper.selection)
        found = [BASE + BLOCK, BASE + 4 * BLOCK]
        result = {"status": "scope-locations-candidate",
                  "candidateStartAddresses": [f"0x{x:X}" for x in found]}
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "record"
            with (patch.object(capture.socket, "gethostname", return_value=HOST),
                  patch.object(capture.physical_rift, "select_physical",
                               return_value=selection),
                  patch.object(capture.physical_rift, "read_native",
                               side_effect=helper._fake_native),
                  patch.object(capture.locator, "discover", return_value=result) as locate,
                  patch.object(capture, "survey_scopes",
                               side_effect=ValueError("stopped-after-map")) as survey):
                with self.assertRaisesRegex(ValueError, "stopped-after-map"):
                    capture.collect(
                        123, path, scan_bytes=BLOCK, gap_ms=0, auto_scope=True,
                        discover_scope=True, scope_count=2, reader_factory=FakeProcess)
            self.assertTrue((path / "native-survey-owner.json").is_file())
            self.assertEqual(survey.call_args.kwargs["scope_addresses"], found)
            self.assertEqual(survey.call_args.kwargs["start"], found[0])
            self.assertEqual(survey.call_args.kwargs["scope_count"], 2)
            self.assertEqual(locate.call_args.kwargs["marker"], capture.MARKER)
            self.assertEqual(locate.call_args.kwargs["max_scopes"], 2)

    def test_discover_without_auto_scope_refuses_before_any_process_access(self):
        with patch.object(capture, "admission") as admission:
            with self.assertRaisesRegex(ValueError, "invalid-scope-discovery-options"):
                capture.collect(123, Path("never-created"),
                                auto_scope=False, discover_scope=True)
            admission.assert_not_called()


    def test_cli_explicit_auto_scope_forwards_options(self):
        summary = {"status":"unqualified","target":{"processId":123},
                   "nativeAfter":{"zoneIdCandidate":ZONE},
                   "sourceClockProgression":"unqualified","qualification":"candidate",
                   "passes":[]}
        with (patch.object(capture, "collect", return_value=(Path("receipt.json"), summary)) as called,
              patch.object(capture.Path, "read_bytes", return_value=b"test"),
              redirect_stdout(StringIO())):
            code = capture.main(["--physical-pid", "123", "--auto-scope", "--scope-count", "3"])
        self.assertEqual(code, 2)
        self.assertTrue(called.call_args.kwargs["auto_scope"])
        self.assertEqual(called.call_args.kwargs["scope_count"], 3)

    def test_auto_scope_bool_and_scope_count_validate_without_host_probe(self):
        with patch.object(capture, "admission") as admission:
            with self.assertRaisesRegex(ValueError, "invalid-auto-scope-options"):
                capture.collect(123, Path("unused"), auto_scope=1)
            with self.assertRaisesRegex(ValueError, "invalid-auto-scope-options"):
                capture.collect(123, Path("unused"), auto_scope=True, scope_count=9)
            admission.assert_not_called()


if __name__ == "__main__":
    unittest.main()
