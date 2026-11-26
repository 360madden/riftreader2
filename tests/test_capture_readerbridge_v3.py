import base64
from contextlib import chdir, nullcontext, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import capture_readerbridge_v3 as capture
from scripts import replay_readerbridge_v3 as replay
from scripts.readerbridge_v3 import decode_packet
from tests.test_physical_player_context_projection import report as native_context_report
from tests.test_readerbridge_v3 import EMPTY, NAME, PLAYER, STATS, packet, section, slot


BODY = section("P", PLAYER.replace(b"name=6:" + NAME, b"name=5:Atank")) + section("S", STATS)
PACKET = packet(BODY)
DECODED = decode_packet(PACKET)
TARGET = {"processId": 2468, "processStartUtcTicks": 123456789,
          "executableSha256": "A" * 64}
SELF_NUMBER = 239816685251645959
SELF_ID = "u035400012FA2D207"


HOST = "RIFT-STATION"


def snapshot(data):
    return {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1",
            "identity": TARGET, "status": "complete", "chunks": [{
                "address": "0x100000", "requestedByteLength": len(data),
                "status": "success", "bytesRead": len(data),
                "bytesBase64": base64.b64encode(data).decode(),
                "bytesSha256": hashlib.sha256(data).hexdigest().upper()}]}


class FakeRunner:
    def __init__(self, *, sequence_offsets=(0, 1, 2), unmatched_header=False, malformed_companion=False,
                 corrupt_capture_hash=False, scout_exit=3, unmatched_scouts=0):
        self.calls = []
        self.sequence_offsets = sequence_offsets
        self.unmatched_header = unmatched_header
        self.malformed_companion = malformed_companion
        self.corrupt_capture_hash = corrupt_capture_hash
        self.scout_exit = scout_exit
        self.scouts = 0
        self.unmatched_scouts = unmatched_scouts

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        command = args[1]
        request_path = Path(args[args.index("--request") + 1])
        output = Path(args[args.index("--output") + 1])
        request = json.loads(request_path.read_text())
        if command == "scout-values-native":
            self.scouts += 1
            output.mkdir()
            delta = self.sequence_offsets[self.scouts - 1]
            sequence = DECODED["sequence"] + delta
            clock = DECODED["sourceTimeMs"] + delta * 1000
            previous = slot(sequence - 1, clock - 1, 0, 129, BODY) if sequence > 1 else EMPTY
            self.current_packet = packet(BODY, seq=sequence, clock=clock, previous=previous)
            companion = (f"RRAPICOORD1|schema=1|seq={sequence}|"
                         f"sampledAt={clock / 1000:.3f}|source=rift-api|"
                         "view=Inspect.Unit.Detail(player)|status=pass|x=7429.0|y=863.0|z=2935.0|"
                         f"playerId={SELF_ID}|name=Atank\0").encode().ljust(512, b"\0")
            entries = []
            records = [("readerbridge-prefix", self.current_packet[:512], "0x100000")]
            if self.scouts > self.unmatched_scouts:
                records.append(("coord-prefix", companion, "0x200000"))
            if self.unmatched_header:
                unmatched = packet(BODY, seq=sequence + 1, clock=clock + 1000)
                records.append(("readerbridge-prefix", unmatched[:512], "0x300000"))
            if self.malformed_companion:
                records.append(("coord-prefix", b"RRAPICOORD1|seq=123|", "0x400000"))
            for index, (kind, data, address) in enumerate(records, 1):
                name = f"capture-{index:03}.snapshot.json"
                raw = json.dumps(snapshot(data)).encode()
                (output / name).write_bytes(raw)
                entries.append({"address": address, "status": "success",
                                "referenceNames": [kind], "snapshotFile": name,
                                "snapshotSha256": hashlib.sha256(raw).hexdigest().upper()})
            index = {"evidenceKind": "native-value-scout/1", "status": "partial",
                     "reason": "byte-budget-exceeded",
                     "identity": TARGET, "request": request, "candidates": entries}
            (output / "index.json").write_text(json.dumps(index))
        elif command == "capture-native":
            ranges = []
            offset = 0
            for item in request["ranges"]:
                data = self.current_packet[offset:offset + item["byteLength"]]
                offset += len(data)
                digest = hashlib.sha256(data).hexdigest().upper()
                if self.corrupt_capture_hash:
                    digest = "0" * 64
                ranges.append({"rangeId": item["id"], "requestedAddress": item["address"],
                               "resolvedAddress": item["address"],
                               "requestedByteLength": item["byteLength"], "status": "success",
                               "bytesRead": len(data), "bytesBase64": base64.b64encode(data).decode(),
                               "bytesSha256": digest})
            sampled_at = datetime.now(timezone.utc).isoformat()
            report = {"evidenceKind": "native-memory-semantic-unqualified", "request": request,
                      "capture": {"status": "complete", "identity": TARGET,
                                  "samples": [{"ranges": ranges, "startedAtUtc": sampled_at,
                                               "completedAtUtc": sampled_at}]}}
            output.write_text(json.dumps(report))
        else:
            raise AssertionError(command)
        return subprocess.CompletedProcess(args, self.scout_exit if command == "scout-values-native" else 0,
                                           "", "")


class CaptureReaderBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        local_host = patch.object(capture.physical_rift.socket, "gethostname", return_value=HOST)
        local_host.start()
        self.addCleanup(local_host.stop)
        self.reader = self.root / "Reader with spaces" / "RiftReader2.Live.exe"
        self.reader.parent.mkdir()
        self.reader.touch()
        self.context_reads = []
        self.seed = self.root / "seed.json"
        self.seed.write_text(json.dumps({"evidenceKind": "native-value-scout/1",
                                         "identity": TARGET,
                                         "coveredSpans": [{"baseAddress": "0x3CA60000",
                                                            "byteLength": 64 * capture.MIB}]}))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def selector(**kwargs):
        return {"status": "ready", "ownerHost": HOST, "target": TARGET}

    def read_context(self, selection, kind, *, native_reader):
        self.context_reads.append((kind, native_reader))
        return {**selection, "status": "complete", "nativeRead": kind,
                "nativeValues": {"unitKey": str(SELF_NUMBER),
                                 "sampledAtUtc": datetime.now(timezone.utc).isoformat()}}

    def acquire_two_generations(self, runner, read_context):
        sleeps = []
        with chdir(self.root):
            result = capture.acquire(HOST, TARGET["processId"], Path("seed.json"),
                                     Path("out"), runner=runner, sleep=sleeps.append,
                                     selector=self.selector, native_reader=self.reader,
                                     read_context=read_context, progress=lambda _: None)
        return result, sleeps

    def test_dependency_check_requires_all_reader_commands_and_never_selects_rift(self):
        commands = ("sample-current-player-context", "scout-values-native", "capture-native")
        args = ["--expected-host", HOST, "--check-dependencies", "--native-reader", str(self.reader)]
        with patch.object(capture, "acquire") as acquire, \
                patch.object(capture.physical_rift, "select_physical") as select, \
                patch.object(capture, "check_installed_addon", return_value={"status": "files-present"}), \
                patch.object(capture.physical_rift.observe_physical, "_run") as run:
            for missing in (None, *commands):
                with self.subTest(missing=missing):
                    run.reset_mock()
                    run.return_value = (0, "\n".join(
                        ["RiftReader2.Live native tools", *(command for command in commands if command != missing)]))
                    with redirect_stdout(StringIO()) as stdout:
                        self.assertEqual(2 if missing else 0, capture.main(args))
                    report = json.loads(stdout.getvalue())
                    self.assertFalse(report["inputSent"])
                    self.assertEqual(report["readerBridgePublisher"], "unverified")
                    self.assertEqual(report["nativeReaderPath"], str(self.reader))
                    if missing:
                        self.assertEqual(report["status"], "blocked")
                        self.assertEqual(report["missingCommands"], [missing])
                    else:
                        self.assertEqual(report["status"], "ready")
                        self.assertEqual(report["nativeCommandsAdvertised"], 3)
                    run.assert_called_once()
                    self.assertEqual(run.call_args.args[0], [self.reader, "--help"])
        acquire.assert_not_called()
        select.assert_not_called()

    def test_installed_addon_reports_matching_changed_and_missing_source_files(self):
        folder = self.root / "Redirected AddOns" / "ReaderBridge"
        folder.mkdir(parents=True)
        manifest = folder / "RiftAddon.toc"
        module = folder / "ReaderBridge.lua"
        manifest.write_bytes(b'RunOnStartup = {"ReaderBridge.lua"}')
        module.write_bytes(b'local version = "fixture"')
        pins = {"startupManifestSha256": hashlib.sha256(manifest.read_bytes()).hexdigest().upper(),
                "schemaSourceSha256": hashlib.sha256(module.read_bytes()).hexdigest().upper()}
        with patch.object(capture.observe_physical, "local_rift_addons_root", return_value=folder.parent), \
                patch.dict(capture.PRODUCER, pins):
            result = capture.check_installed_addon()
            self.assertEqual(result["status"], "files-present")
            self.assertTrue(result["matchesDecoderReference"])
            module.write_bytes(b'local version = "custom"')
            result = capture.check_installed_addon()
            self.assertEqual(result["status"], "files-present")
            self.assertFalse(result["files"]["ReaderBridge.lua"]["matchesDecoderReference"])
            manifest.unlink()
            result = capture.check_installed_addon()
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["files"]["RiftAddon.toc"]["status"], "missing")

    def test_wrong_host_never_checks_installed_readerbridge_files(self):
        with patch.object(capture, "check_installed_addon") as addon, redirect_stdout(StringIO()) as stdout:
            self.assertEqual(capture.main(["--expected-host", "OTHER-PC", "--check-dependencies"]), 2)
        self.assertEqual(json.loads(stdout.getvalue())["installedAddon"],
                         {"status": "not-checked", "reason": "host-mismatch"})
        addon.assert_not_called()

    def test_addon_file_marked_offline_is_reported_without_opening_it(self):
        path = Mock(spec=Path)
        path.lstat.return_value = Mock(st_mode=capture.stat.S_IFREG, st_size=32,
                                       st_file_attributes=capture.stat.FILE_ATTRIBUTE_OFFLINE)
        self.assertEqual(capture._installed_addon_file(path, "A" * 64), {"status": "cloud-recall-required"})
        path.open.assert_not_called()

    def test_dependency_check_rejects_capture_options(self):
        for option, value in (("--physical-pid", "1"), ("--seed-index", "seed.json"),
                              ("--output", "new path"), ("--scan-mib", "16")):
            with self.subTest(option=option), redirect_stderr(StringIO()), \
                    patch.object(capture.physical_rift, "check_native_reader") as check, \
                    self.assertRaises(SystemExit) as exc:
                capture.main(["--expected-host", HOST, "--check-dependencies", option, value])
            self.assertEqual(exc.exception.code, 2)
            check.assert_not_called()

    def test_capture_cli_keeps_its_default_scan_budget(self):
        output = self.root / "out"
        with patch.object(capture, "acquire", return_value={"status": "captured"}) as acquire, \
                redirect_stdout(StringIO()):
            self.assertEqual(0, capture.main([
                "--expected-host", HOST, "--physical-pid", "2468", "--seed-index", str(self.seed),
                "--output", str(output), "--native-reader", str(self.reader),
            ]))
        acquire.assert_called_once_with(HOST, 2468, self.seed, output, scan_mib=16, native_reader=self.reader,
                                        include_selected_target=False)

    def test_acquires_two_advancing_generations_with_bounded_requests(self):
        runner = FakeRunner()
        result, sleeps = self.acquire_two_generations(runner, self.read_context)
        self.assertFalse(result["ready"])
        self.assertFalse(result["inputSent"])
        self.assertEqual([DECODED["sequence"], DECODED["sequence"] + 1],
                         [g["sequence"] for g in result["generations"]])
        self.assertEqual([1.1], sleeps)
        self.assertEqual(4, len(runner.calls))
        self.assertEqual([("player-context", self.reader)] * 2, self.context_reads)
        self.assertTrue(all(call[0][0] == str(self.reader) for call in runner.calls))
        self.assertTrue(all(Path(call[0][3]).parent == self.root / "out" for call in runner.calls))
        self.assertTrue(all(Path(call[0][5]).parent == self.root / "out" for call in runner.calls))
        self.assertTrue(all(call[1]["timeout"] == 15 for call in runner.calls))
        scout_request = json.loads((self.root / "out/attempt-1.scout.request.json").read_text())
        self.assertEqual(16 * capture.MIB, scout_request["maxScanBytes"])
        self.assertEqual(3000, scout_request["maxDurationMilliseconds"])
        self.assertEqual(32768, scout_request["maxRegionCount"])
        self.assertEqual(64, scout_request["maxMatchCount"])
        self.assertEqual([capture.RBRG_PREFIX, capture.RRAP_PREFIX],
                         [r["value"] for r in scout_request["references"]])
        capture_request = json.loads((self.root / "out/attempt-1.capture.request.json").read_text())
        self.assertEqual([4096, 4096, 200], [r["byteLength"] for r in capture_request["ranges"]])

    def test_reads_newest_packet_that_has_a_same_generation_companion(self):
        result, _ = self.acquire_two_generations(
            FakeRunner(unmatched_header=True, malformed_companion=True), self.read_context)
        self.assertEqual(["0x100000", "0x100000"], [item["packetAddress"] for item in result["generations"]])
        self.assertEqual([2, 2], [item["packetCandidateCount"] for item in result["attempts"]])
        self.assertEqual([1, 1], [item["matchedPacketCandidateCount"] for item in result["attempts"]])
        self.assertEqual([1, 1], [item["rejectedCompanionCount"] for item in result["attempts"]])

    def test_replays_copied_packets_companions_and_native_level_sources(self):
        def native_context(selection, kind, *, native_reader):
            result = self.read_context(selection, kind, native_reader=native_reader)
            document = native_context_report()
            timestamp = result["nativeValues"]["sampledAtUtc"]
            document["observation"].update(identity=TARGET, startedAtUtc=timestamp, completedAtUtc=timestamp)
            source = self.root / f"player-context-{len(self.context_reads)}.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            return dict(result, nativeOutput=str(source),
                        nativeValues=capture.physical_rift._native_values(kind, document))

        self.acquire_two_generations(FakeRunner(), native_context)
        copied = shutil.copytree(self.root / "out", self.root / "copied capture")
        (self.root / "out").rename(self.root / "prior capture")
        result = replay.replay(copied / "result.json")
        self.assertEqual(result["playerLevelComparison"]["status"], "matching-native-and-lua-player-level-candidates")
        self.assertEqual([45, 45], [row["level"] for row in result["generations"]])
        self.assertFalse(result["ready"] or result["inputSent"])
        for name, reason in (("native-player-after.json", "native-context-sha-mismatch"),
                             ("generation-2.bin", "packet-bytes-mismatch")):
            with self.subTest(source=name):
                source = copied / name
                raw = source.read_bytes()
                source.write_bytes(b"X" + raw[1:])
                try:
                    with self.assertRaisesRegex(ValueError, reason):
                        replay.replay(copied / "result.json")
                finally:
                    source.write_bytes(raw)

    def test_selected_target_replay_requires_ordered_hashed_sources_and_matching_names(self):
        references = {}
        for key, (name, kind) in capture.SELECTED_TARGET_SOURCES.items():
            second = {"selectedBefore": 0, "nameBefore": 1, "nameAfter": 4, "selectedAfter": 5}[key]
            observation = dict(identity=TARGET, selfKey=SELF_NUMBER, targetKey=1234, targetEntity=4567,
                               startedAtUtc=f"2026-11-21T00:00:0{second}Z",
                               completedAtUtc=f"2026-11-21T00:00:0{second}.1Z")
            values = (dict(status="candidate", unitId="u00000000000004D2", numericLevelCandidate=14)
                      if kind == "selected-target" else dict(selectedBaseNameCandidate="Tira Marlas"))
            raw = json.dumps(dict(observation=observation, values=values)).encode()
            (self.root / name).write_bytes(raw)
            references[key] = {"file": name, "sha256": hashlib.sha256(raw).hexdigest().upper()}
        generations = [{"luaTarget": {"name": "Tira Marlas", "level": 14},
                        "startedAtUtc": f"2026-11-21T00:00:0{second}Z",
                        "completedAtUtc": f"2026-11-21T00:00:0{second}.1Z"} for second in (2, 3)]
        with patch.object(capture.physical_rift, "_native_values", side_effect=lambda _, doc: doc["values"]):
            def compare():
                return replay._selected_target_levels(self.root, references, TARGET, SELF_ID, generations)

            result = compare()
            self.assertEqual(result["status"], "matching-named-target-level-candidates")
            self.assertFalse(result["luaUnitIdProvided"])
            generations[0]["luaTarget"]["name"] = "Another NPC"
            self.assertEqual(compare()["status"], "different-native-and-lua-target-names")
            generations[-1]["completedAtUtc"] = "2026-11-21T00:00:05Z"
            with self.assertRaisesRegex(ValueError, "selected-target-does-not-bracket-packets"):
                compare()
            name_report = self.root / "name-after.json"
            name_report.write_bytes(name_report.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "selected-target-source-sha-mismatch"):
                compare()

    def test_finds_current_private_scope_without_a_seed_and_rechecks_owner(self):
        address = 16 * capture.MIB
        raw = PACKET.ljust(65536, b"\0")
        mapped = Mock()
        mapped.readable_private_regions.return_value = [(address, address + len(raw))]
        mapped.read.side_effect = lambda start, count: raw[start - address:start - address + count]
        selector = Mock(side_effect=self.selector)
        factory = Mock(return_value=nullcontext(mapped))
        output = self.root / "mapped"
        result = capture.acquire(HOST, TARGET["processId"], None, output, runner=FakeRunner(),
                                 sleep=lambda _: None, selector=selector, native_reader=self.reader,
                                 read_context=self.read_context, progress=lambda _: None, reader_factory=factory)
        factory.assert_called_once_with(TARGET["processId"])
        self.assertEqual(selector.call_count, 2)
        self.assertEqual(result["scope"]["candidateStartAddresses"], [f"0x{address:X}"])
        self.assertEqual(json.loads((output / "scope-survey.json").read_bytes())["target"], TARGET)
        self.assertFalse(result["inputSent"])

    def test_refuses_publication_when_the_native_player_changes(self):
        def changed_player(*args, **kwargs):
            result = self.read_context(*args, **kwargs)
            if len(self.context_reads) == 2:
                result["nativeValues"]["unitKey"] = str(SELF_NUMBER + 1)
            return result

        with self.assertRaisesRegex(capture.CaptureError, "player-changed-during-readerbridge-acquisition"):
            self.acquire_two_generations(FakeRunner(), changed_player)
        self.assertTrue((self.root / "out/generation-2.bin").is_file())
        self.assertFalse((self.root / "out/result.json").exists())

    def test_rejects_seed_from_another_epoch_before_native_or_output(self):
        bad = json.loads(self.seed.read_text())
        bad["identity"]["processStartUtcTicks"] += 1
        self.seed.write_text(json.dumps(bad))
        runner = FakeRunner()
        with self.assertRaisesRegex(capture.CaptureError, "seed-process-epoch-or-build-mismatch"):
            capture.acquire(HOST, TARGET["processId"], self.seed, self.root / "out",
                            runner=runner, selector=self.selector, native_reader=self.reader, read_context=self.read_context,
                            progress=lambda _: None)
        self.assertEqual([], runner.calls)
        self.assertFalse((self.root / "out").exists())

    def test_missing_reader_refuses_before_process_selection(self):
        selector = Mock()
        output = self.root / "out"
        with self.assertRaisesRegex(capture.CaptureError, "native-reader-not-built"):
            capture.acquire(HOST, TARGET["processId"], self.seed, output,
                            native_reader=self.root / "missing.exe", selector=selector)
        selector.assert_not_called()
        self.assertFalse(output.exists())

    def test_stale_player_context_refuses_before_packet_acquisition(self):
        runner = FakeRunner()
        output = self.root / "out"

        def stale_context(*args, **kwargs):
            context = self.read_context(*args, **kwargs)
            stale = datetime.now(timezone.utc) - timedelta(seconds=20)
            context["nativeValues"]["sampledAtUtc"] = stale.isoformat()
            return context

        with self.assertRaisesRegex(capture.CaptureError, "stale-player-context"):
            capture.acquire(HOST, TARGET["processId"], self.seed, output,
                            native_reader=self.reader, runner=runner, selector=self.selector,
                            read_context=stale_context, progress=lambda _: None)
        self.assertEqual([], runner.calls)
        self.assertFalse(output.exists())

    def test_rejects_scan_above_32_mib_and_existing_output(self):
        with self.assertRaisesRegex(capture.CaptureError, "scan-mib-out-of-range"):
            capture.acquire(HOST, 1, self.seed, self.root / "out", scan_mib=33)
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaisesRegex(capture.CaptureError, "output-already-exists"):
            capture.acquire(HOST, 1, self.seed, output)

    def test_rejects_unverified_range_hash_and_never_publishes_ready(self):
        runner = FakeRunner(corrupt_capture_hash=True)
        with self.assertRaisesRegex(capture.CaptureError, "two-advancing-generations-not-observed"):
            capture.acquire(HOST, TARGET["processId"], self.seed, self.root / "out",
                            runner=runner, sleep=lambda _: None, selector=self.selector,
                            native_reader=self.reader, read_context=self.read_context, progress=lambda _: None)
        self.assertFalse((self.root / "out/result.json").exists())
        self.assertEqual(3, runner.scouts)
        self.assertEqual(6, len(runner.calls))  # three scouts and three packet reads, never more

    def test_accepts_real_like_partial_scout_exit_three_but_not_identity_failure(self):
        runner = FakeRunner(scout_exit=3)
        request = self.root / "request.json"
        request.write_text("{}")
        reader = self.root / "RiftReader2.Live.exe"
        capture._run_native("scout-values-native", request, self.root / "unused", runner, native_reader=reader)
        self.assertEqual(runner.calls[0][0][0], str(reader))

        directory = self.root / "scout"
        directory.mkdir()
        index = {"evidenceKind": "native-value-scout/1", "status": "partial",
                 "reason": "byte-budget-exceeded", "identity": TARGET,
                 "request": {"target": TARGET}, "candidates": []}
        self.assertEqual([], capture._validate_scout(index, TARGET, directory))
        index["reason"] = "process-identity-changed"
        with self.assertRaisesRegex(capture.CaptureError, "invalid-scout-owner-or-status"):
            capture._validate_scout(index, TARGET, directory)

    def test_packet_candidate_prequalification_requires_magic_control(self):
        self.assertEqual(DECODED["sequence"], capture._packet_control_sequence(PACKET[:512]))
        self.assertIsNone(capture._packet_control_sequence(b"RBRG" + b"\0" * 508))

    def test_stalled_second_attempt_does_not_block_advancing_third(self):
        runner = FakeRunner(sequence_offsets=(0, 0, 2))
        result, _ = self.acquire_two_generations(runner, self.read_context)
        self.assertEqual(3, runner.scouts)
        self.assertEqual([DECODED["sequence"], DECODED["sequence"] + 2],
                         [item["sequence"] for item in result["generations"]])
        self.assertEqual("readerbridge-generation-not-advancing",
                         result["attempts"][1]["candidateFailure"])

    def test_first_match_on_third_window_gets_one_confirmation_attempt(self):
        # Reproduce the live case: two unmatched scopes, then one good generation.
        starts = [16 * capture.MIB, 32 * capture.MIB, 48 * capture.MIB]
        runner = FakeRunner(sequence_offsets=(0, 1, 2, 3), unmatched_scouts=2)
        output = self.root / "late-match"
        with patch.object(capture, "_locate_packet_scopes", return_value=({}, starts)):
            result = capture.acquire(HOST, TARGET["processId"], None, output,
                                     runner=runner, sleep=lambda _: None, selector=self.selector,
                                     native_reader=self.reader, read_context=self.read_context,
                                     progress=lambda _: None)
        self.assertEqual(4, runner.scouts)
        self.assertEqual(4, result["scope"]["maxAttempts"])
        self.assertEqual([f"0x{x:X}" for x in starts + [starts[-1]]],
                         [attempt["startAddress"] for attempt in result["attempts"]])
        self.assertEqual([DECODED["sequence"] + 2, DECODED["sequence"] + 3],
                         [item["sequence"] for item in result["generations"]])
        self.assertFalse(result["ready"] or result["inputSent"])

    def test_one_generation_and_stalled_third_gets_bounded_confirmation(self):
        runner = FakeRunner(sequence_offsets=(0, 1, 1, 3), unmatched_scouts=1)
        result, _ = self.acquire_two_generations(runner, self.read_context)
        self.assertEqual(4, runner.scouts)
        self.assertEqual(4, result["scope"]["maxAttempts"])
        self.assertEqual([DECODED["sequence"] + 1, DECODED["sequence"] + 3],
                         [item["sequence"] for item in result["generations"]])
        self.assertEqual("readerbridge-generation-not-advancing",
                         result["attempts"][2]["candidateFailure"])
        self.assertFalse(result["ready"] or result["inputSent"])

    def test_no_generation_does_not_extend_the_original_budget(self):
        runner = FakeRunner(unmatched_scouts=3)
        with self.assertRaisesRegex(capture.CaptureError, "two-advancing-generations-not-observed"):
            self.acquire_two_generations(runner, self.read_context)
        self.assertEqual(3, runner.scouts)
        self.assertFalse((self.root / "out/result.json").exists())

    def test_late_match_with_stalled_confirmation_remains_unavailable(self):
        runner = FakeRunner(sequence_offsets=(0, 1, 2, 2), unmatched_scouts=2)
        with self.assertRaisesRegex(capture.CaptureError, "two-advancing-generations-not-observed"):
            self.acquire_two_generations(runner, self.read_context)
        self.assertEqual(4, runner.scouts)
        self.assertFalse((self.root / "out/result.json").exists())

    def test_clock_rollback_is_not_advancing_even_when_sequence_increases(self):
        retained = [{"sequence": 10, "sourceTimeMs": 2000}]
        with self.assertRaisesRegex(capture.CaptureError, "generation-not-advancing"):
            capture._require_advancing({"sequence": 11, "sourceTimeMs": 1999}, retained)
        self.assertEqual(1, len(retained))

    def test_strict_json_and_finite_companion_validation_are_structured(self):
        with self.assertRaisesRegex(capture.CaptureError, "duplicate-json-key:x"):
            capture._loads_json('{"x":1,"x":2}', "duplicate.json")
        with self.assertRaisesRegex(capture.CaptureError, "nonfinite-json-number:NaN"):
            capture._loads_json('{"x":NaN}', "nonfinite.json")
        companion = (f"RRAPICOORD1|seq=1|sampledAt=1.000|playerId={SELF_ID}|name=Atank|"
                     "status=pass|x=NaN|y=0|z=0\0").encode()
        with self.assertRaisesRegex(capture.CaptureError, "nonfinite-rrap-coordinate"):
            capture._companion(companion)


if __name__ == "__main__":
    unittest.main()
