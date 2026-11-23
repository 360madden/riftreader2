"""Bounded read-only NPC source relocation without a saved scout seed."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import npc_survey_live as npc
from scripts import replay_npc_survey
from tests.test_replay_npc_survey import NONCE, PLAYER, UNIT, wire

ADDRESS = 0x10000
TARGET = {
    "hostName": "AMD-DESKTOP", "processId": 37676,
    "processStartUtcTicks": "639308565554559088",
    "executableSha256": "D" * 64,
}
REGION_SIZE = 65536


class Reader:
    def __init__(self, wires=()):
        self.region = bytearray(REGION_SIZE)
        for address, raw in wires:
            at = address - ADDRESS
            self.region[at:at+len(raw)] = raw
        self.read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def readable_private_regions(self):
        return [(ADDRESS, ADDRESS + REGION_SIZE)]

    def read(self, address, length):
        self.read_count += 1
        if not ADDRESS <= address < ADDRESS + REGION_SIZE:
            return b""
        return bytes(self.region[address-ADDRESS:address-ADDRESS+length])


class NPCMapScoutTests(unittest.TestCase):
    def reader(self, _, raws):
        return Reader(raws)

    def bind(self, **overrides):
        target = dict(TARGET, **overrides)
        return {"status": "ready", "target": target}

    def test_real_map_scanner_recovers_only_matching_nonce_and_player(self):
        first, second = wire(10), wire(11)
        raw = [(ADDRESS + 130, first), (ADDRESS + 3100, second)]
        selections = []
        def select(**kwargs):
            selections.append(kwargs)
            return self.bind()
        holder = Reader(raw)
        results = npc.scout_mapped(
            TARGET, NONCE, PLAYER, [UNIT],
            reader_factory=lambda _: holder,
            selection_reader=select, max_bytes=REGION_SIZE)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][1], first)
        self.assertEqual(results[1][1], second)
        self.assertEqual(results[1][0]["address"], hex(ADDRESS+3100).replace("0x", "0x").upper().replace("0X", "0x"))
        self.assertEqual(len(selections), 2)
        self.assertTrue(holder.read_count >= 3)
        self.assertEqual(npc.scout_mapped(
            TARGET, "b"*32, PLAYER, [UNIT],
            reader_factory=lambda _: Reader(raw),
            selection_reader=lambda **_: self.bind(), max_bytes=REGION_SIZE), [])
        self.assertEqual(npc.scout_mapped(
            TARGET, NONCE, "u0000000000000003", [UNIT],
            reader_factory=lambda _: Reader(raw),
            selection_reader=lambda **_: self.bind(), max_bytes=REGION_SIZE), [])

    def test_bounded_map_diagnostics_prove_scan_only_not_live_publisher(self):
        raw = [(ADDRESS + 333, wire(10))]
        with TemporaryDirectory() as temp:
            report = Path(temp) / "locator.json"
            found = npc.scout_mapped(
                TARGET, NONCE, PLAYER, [UNIT],
                reader_factory=lambda _: Reader(raw),
                selection_reader=lambda **_: self.bind(),
                max_bytes=REGION_SIZE, diagnostics=report)
            self.assertEqual(len(found), 1)
            self.assertTrue(report.is_file())
            recorded = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(recorded["status"], "matching-source-candidates")
            self.assertEqual(recorded["matchingFrameCandidates"], 1)
            self.assertEqual(recorded["locator"]["scannedBytes"], REGION_SIZE)
            self.assertFalse(recorded["inputSent"])
            with self.assertRaisesRegex(ValueError, "new-diagnostics-file-required"):
                npc.scout_mapped(
                    TARGET, NONCE, PLAYER, [UNIT],
                    reader_factory=lambda _: self.fail("must refuse before reading"),
                    selection_reader=lambda **_: self.fail("must refuse before preflight"),
                    max_bytes=REGION_SIZE, diagnostics=report)
            missed = Path(temp) / "absent.json"
            result = npc.scout_mapped(
                TARGET, "b" * 32, PLAYER, [UNIT],
                reader_factory=lambda _: Reader(raw),
                selection_reader=lambda **_: self.bind(),
                max_bytes=REGION_SIZE, diagnostics=missed)
            self.assertEqual(result, [])
            saved = json.loads(missed.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "unqualified-bounded-search")
            self.assertEqual(saved["matchingFrameCandidates"], 0)
            self.assertIn("do not prove addon absence", saved["qualification"])

    def test_actual_normalized_acquire_owner_pins_full_window_identity(self):
        full = dict(TARGET, executablePath=r"C:\\Program Files (x86)\\Glyph\\Games\\RIFT\\Live\\rift_x64.exe",
                    hwnd=3541956)
        normalized = npc._target(full)
        self.assertNotIn("hostName", normalized)
        self.assertIsInstance(normalized["processStartUtcTicks"], int)
        def select(**kwargs):
            return {"status": "ready", "target": dict(full)}
        frames = npc.scout_mapped(
            normalized, NONCE, PLAYER, [UNIT],
            expected_host="AMD-DESKTOP", owner_target=full,
            reader_factory=lambda _: Reader([(ADDRESS+320, wire(10))]),
            selection_reader=select, max_bytes=REGION_SIZE)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0][1], wire(10))
        def changed_window(**kwargs):
            return {"status": "ready", "target": dict(full, hwnd=88)}
        with self.assertRaisesRegex(ValueError, "process-identity-unavailable"):
            npc.scout_mapped(
                normalized, NONCE, PLAYER, [UNIT],
                expected_host="AMD-DESKTOP", owner_target=full,
                reader_factory=lambda _: self.fail("no memory reads"),
                selection_reader=changed_window, max_bytes=REGION_SIZE)

    def test_wrong_process_before_and_after_read_refused(self):
        with self.assertRaisesRegex(ValueError, "process-identity-unavailable"):
            npc.scout_mapped(
                TARGET, NONCE, PLAYER, [UNIT],
                reader_factory=lambda _: Reader(),
                selection_reader=lambda **_: self.bind(processId=999),
                max_bytes=REGION_SIZE)
        reads = 0
        def select(**kwargs):
            nonlocal reads
            reads += 1
            return self.bind(processId=999 if reads > 1 else TARGET["processId"])
        with self.assertRaisesRegex(ValueError, "process-changed"):
            npc.scout_mapped(
                TARGET, NONCE, PLAYER, [UNIT],
                reader_factory=lambda _: Reader([(ADDRESS+80, wire(10))]),
                selection_reader=select, max_bytes=REGION_SIZE)

    def test_invalid_budget_before_process_read(self):
        for budget in (True, 1, 1024 * 1024 * 1024):
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(ValueError, "invalid-byte-budget"):
                    npc.scout_mapped(
                        TARGET, NONCE, PLAYER, [UNIT], max_bytes=budget,
                        reader_factory=lambda _: self.fail("no process read"),
                        selection_reader=lambda **_: self.fail("no preflight"))

    def test_acquire_auto_map_produces_existing_replayable_original_sources(self):
        frames = [wire(10), wire(11)]
        candidates = [[({"address": f"0x{ADDRESS+i*4096:X}"}, raw)]
                      for i, raw in enumerate(frames)]
        target = dict(TARGET, hostName="RIFT-STATION")
        with TemporaryDirectory() as temp:
            saved = Path(temp) / "run"
            published = saved.parent / "RiftReader2.Live.exe"
            published.touch()
            with (patch.object(npc.physical_rift, "select_physical",
                               return_value={"status": "ready", "target": target}),
                  patch.object(npc.physical_rift, "read_native", return_value={
                      "status": "complete", "target": target, "nativeValues": {"unitKey": "1"}}) as read,
                  patch.object(npc, "scout_mapped", side_effect=candidates) as scout,
                  patch.object(npc.survival_live, "autodiscover_seed") as seeded,
                  patch.object(npc.time, "sleep")):
                report = npc.acquire("rift-station", 37676, NONCE, [UNIT],
                                     saved, attempts=2, auto_map=True, native_reader=published,
                                     expected_start_ticks=target["processStartUtcTicks"],
                                     expected_sha256=target["executableSha256"].lower(),
                                     capture_deadline_utc=(datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat())
                self.assertEqual(read.call_args.kwargs["native_reader"], published)
                seeded.assert_not_called()
            self.assertEqual(report["status"], "advancing")
            self.assertEqual(report["host"], "RIFT-STATION")
            self.assertIsNone(report["seedIndex"])
            self.assertEqual(report["memoryLocator"], "bounded-readable-private-map")
            self.assertEqual(scout.call_count, 2)
            self.assertEqual([x["sequence"] for x in report["sources"]], [10, 11])
            self.assertTrue((saved/"frame-01.wire").is_file())
            self.assertEqual((saved/"frame-02.wire").read_bytes(), wire(11))
            self.assertEqual(replay_npc_survey.replay(saved/"result.json")["confirmedUnitIds"], [UNIT])

    def test_plan_refuses_recycled_pid_or_changed_build_before_any_survey_read(self):
        with TemporaryDirectory() as temp:
            dest = Path(temp) / "run"
            for changes in ({"processStartUtcTicks": "639308565554559089"}, {"executableSha256": "A" * 64}):
                with (self.subTest(changes=changes),
                      patch.dict("os.environ", {"RR2_NATIVE_READER": ""}),
                      patch.object(npc.physical_rift, "select_physical", return_value=self.bind(**changes)),
                      patch.object(npc.physical_rift, "read_native") as read,
                      patch.object(npc, "scout_mapped") as scout):
                    with self.assertRaisesRegex(ValueError, "survey-bind-plan-process-mismatch"):
                        npc.acquire("AMD-DESKTOP", 37676, NONCE, [UNIT], dest, auto_map=True,
                                    expected_start_ticks=TARGET["processStartUtcTicks"],
                                    expected_sha256=TARGET["executableSha256"])
                    read.assert_not_called()
                    scout.assert_not_called()
                    self.assertFalse(dest.exists())

    def test_expired_plan_command_refuses_before_selecting_rift(self):
        with (TemporaryDirectory() as temp,
              patch.object(npc.physical_rift, "select_physical") as select,
              redirect_stdout(StringIO()) as output):
            dest = Path(temp) / "run"
            code = npc.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "37676",
                             "--session-id", NONCE, "--unit-ids", UNIT, "--auto-map",
                             "--expect-start-ticks", TARGET["processStartUtcTicks"],
                             "--expect-sha256", TARGET["executableSha256"],
                             "--capture-deadline-utc", "2000-01-01T00:00:00Z", "--output", str(dest)])
            self.assertFalse(dest.exists())
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["reason"], "survey-bind-plan-expired")
        select.assert_not_called()

    def test_expiry_during_a_scout_prevents_publishing_a_survey(self):
        start = datetime(2026, 11, 21, tzinfo=timezone.utc)
        deadline = start + timedelta(seconds=2)
        with (TemporaryDirectory() as temp,
              patch.dict("os.environ", {"RR2_NATIVE_READER": ""}),
              patch.object(npc.physical_rift, "select_physical", return_value=self.bind()),
              patch.object(npc.physical_rift, "read_native", return_value={
                  "status": "complete", "target": TARGET, "nativeValues": {"unitKey": "1"}}),
              patch.object(npc, "scout_mapped", return_value=[]) as scout,
              patch.object(npc, "datetime", wraps=datetime) as clock):
            clock.now.side_effect = [start, start, start, deadline]
            dest = Path(temp) / "run"
            with self.assertRaisesRegex(ValueError, "survey-bind-plan-expired"):
                npc.acquire("AMD-DESKTOP", 37676, NONCE, [UNIT], dest, auto_map=True,
                            expected_start_ticks=TARGET["processStartUtcTicks"],
                            expected_sha256=TARGET["executableSha256"], capture_deadline_utc=deadline.isoformat())
            scout.assert_called_once()
            self.assertFalse((dest / "result.json").exists())

    def test_reject_auto_map_and_old_seed_without_creating_output(self):
        with TemporaryDirectory() as temp:
            dest = Path(temp)/"result"
            with self.assertRaisesRegex(ValueError, "invalid-mapped-survey-options"):
                npc.acquire("AMD-DESKTOP", 37676, NONCE, [UNIT], dest,
                            seed_index="old-seed.json", auto_map=True)
            self.assertFalse(dest.exists())
        for malformed in (1, None, "yes"):
            with self.subTest(value=malformed):
                with self.assertRaisesRegex(ValueError, "invalid-mapped-survey-options"):
                    npc.acquire("AMD-DESKTOP", 37676, NONCE, [UNIT], "absent",
                                auto_map=malformed)

    def test_unbound_publisher_returns_unqualified_without_invented_values(self):
        target = dict(TARGET)
        with TemporaryDirectory() as temp:
            dest = Path(temp)/"unbound"
            with (patch.object(npc.physical_rift, "select_physical",
                               return_value={"status": "ready", "target": target}),
                  patch.object(npc, "_target", side_effect=lambda v: v),
                  patch.object(npc, "_same_target", return_value=True),
                  patch.object(npc.physical_rift, "read_native", return_value={
                      "status": "complete", "target": target, "nativeValues": {"unitKey": "1"}}),
                  patch.object(npc, "scout_mapped", return_value=[]),
                  patch.object(npc.time, "sleep")):
                result = npc.acquire("AMD-DESKTOP", 37676, NONCE, [UNIT],
                                     dest, attempts=2, auto_map=True)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], "no-advancing-survey-pair")
            self.assertFalse(result["inputSent"])
            self.assertEqual(result["sources"], [])
            self.assertFalse((dest/"frame-01.wire").exists())


if __name__ == "__main__":
    unittest.main()
