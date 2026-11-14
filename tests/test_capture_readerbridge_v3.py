import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import capture_readerbridge_v3 as capture
from scripts.readerbridge_v3 import decode_packet


ROOT = Path(__file__).resolve().parents[1]
PACKET = (ROOT / "artifacts/survival-readerbridge-20261114/quick-1.bin").read_bytes()
DECODED = decode_packet(PACKET)
TARGET = {"processId": 2468, "processStartUtcTicks": 123456789,
          "executableSha256": "A" * 64}
SELF_NUMBER = 239816685251645959
SELF_ID = "u035400012FA2D207"


class Adapter:
    target = TARGET
    unit_key = str(SELF_NUMBER)

    def __init__(self, host, pid, basis):
        self.arguments = host, pid, basis


def snapshot(data):
    return {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1",
            "identity": TARGET, "status": "complete", "chunks": [{
                "address": "0x100000", "requestedByteLength": len(data),
                "status": "success", "bytesRead": len(data),
                "bytesBase64": base64.b64encode(data).decode(),
                "bytesSha256": hashlib.sha256(data).hexdigest().upper()}]}


class FakeRunner:
    def __init__(self, *, advancing=True, corrupt_capture_hash=False, scout_exit=3):
        self.calls = []
        self.advancing = advancing
        self.corrupt_capture_hash = corrupt_capture_hash
        self.scout_exit = scout_exit
        self.scouts = 0

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        command = args[1]
        request_path = Path(args[args.index("--request") + 1])
        output = Path(args[args.index("--output") + 1])
        request = json.loads(request_path.read_text())
        if command == "scout-values-native":
            self.scouts += 1
            output.mkdir()
            # Use the real CRC-valid packet.  On the second successful attempt,
            # advancing is represented by adjusting the first decoded result in
            # the test's decoder shim, while the retained bytes remain authentic.
            companion = (f"RRAPICOORD1|schema=1|seq={DECODED['sequence']}|"
                         f"sampledAt={DECODED['sourceTimeMs'] / 1000:.3f}|source=rift-api|"
                         "view=Inspect.Unit.Detail(player)|status=pass|x=7429.0|y=863.0|z=2935.0|"
                         f"playerId={SELF_ID}|name=Atank\0").encode().ljust(512, b"\0")
            entries = []
            for index, (kind, data, address) in enumerate((
                    ("readerbridge-prefix", PACKET[:512], "0x100000"),
                    ("coord-prefix", companion, "0x200000")), 1):
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
                data = PACKET[offset:offset + item["byteLength"]]
                offset += len(data)
                digest = hashlib.sha256(data).hexdigest().upper()
                if self.corrupt_capture_hash:
                    digest = "0" * 64
                ranges.append({"rangeId": item["id"], "requestedAddress": item["address"],
                               "resolvedAddress": item["address"],
                               "requestedByteLength": item["byteLength"], "status": "success",
                               "bytesRead": len(data), "bytesBase64": base64.b64encode(data).decode(),
                               "bytesSha256": digest})
            report = {"evidenceKind": "native-memory-semantic-unqualified", "request": request,
                      "capture": {"status": "complete", "identity": TARGET,
                                  "samples": [{"ranges": ranges}]}}
            output.write_text(json.dumps(report))
        else:
            raise AssertionError(command)
        return subprocess.CompletedProcess(args, self.scout_exit if command == "scout-values-native" else 0,
                                           "", "")


class CaptureReaderBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed.json"
        self.seed.write_text(json.dumps({"evidenceKind": "native-value-scout/1",
                                         "identity": TARGET,
                                         "coveredSpans": [{"baseAddress": "0x3CA60000",
                                                            "byteLength": 64 * capture.MIB}]}))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def selector(**kwargs):
        return {"status": "ready", "target": TARGET}

    def test_acquires_two_advancing_generations_with_bounded_requests(self):
        runner = FakeRunner()
        calls = {"decode": 0}
        original = capture.decode_packet

        def advancing_decoder(packet):
            value = dict(original(packet))
            calls["decode"] += 1
            if calls["decode"] == 2:
                value["sequence"] += 1
                value["sourceTimeMs"] += 1000
            return value

        # The second companion must track the generation produced by the shim.
        original_companion = capture._companion

        def advancing_companion(data):
            value = original_companion(data)
            if value and runner.scouts == 2:
                value["sequence"] += 1
                value["sampledAt"] = str(DECODED["sourceTimeMs"] / 1000 + 1)
            return value

        capture.decode_packet = advancing_decoder
        capture._companion = advancing_companion
        try:
            sleeps = []
            result = capture.acquire("AMD-DESKTOP", TARGET["processId"], self.seed,
                                     self.root / "out", runner=runner, sleep=sleeps.append,
                                     selector=self.selector, adapter_factory=Adapter,
                                     progress=lambda _: None)
        finally:
            capture.decode_packet = original
            capture._companion = original_companion
        self.assertFalse(result["ready"])
        self.assertFalse(result["inputSent"])
        self.assertEqual([DECODED["sequence"], DECODED["sequence"] + 1],
                         [g["sequence"] for g in result["generations"]])
        self.assertEqual([1.1], sleeps)
        self.assertEqual(4, len(runner.calls))
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

    def test_rejects_seed_from_another_epoch_before_native_or_output(self):
        bad = json.loads(self.seed.read_text())
        bad["identity"]["processStartUtcTicks"] += 1
        self.seed.write_text(json.dumps(bad))
        runner = FakeRunner()
        with self.assertRaisesRegex(capture.CaptureError, "seed-process-epoch-or-build-mismatch"):
            capture.acquire("AMD-DESKTOP", TARGET["processId"], self.seed, self.root / "out",
                            runner=runner, selector=self.selector, adapter_factory=Adapter,
                            progress=lambda _: None)
        self.assertEqual([], runner.calls)
        self.assertFalse((self.root / "out").exists())

    def test_rejects_scan_above_32_mib_and_existing_output(self):
        with self.assertRaisesRegex(capture.CaptureError, "scan-mib-out-of-range"):
            capture.acquire("AMD-DESKTOP", 1, self.seed, self.root / "out", scan_mib=33)
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaisesRegex(capture.CaptureError, "output-already-exists"):
            capture.acquire("AMD-DESKTOP", 1, self.seed, output)

    def test_rejects_unverified_range_hash_and_never_publishes_ready(self):
        runner = FakeRunner(corrupt_capture_hash=True)
        with self.assertRaisesRegex(capture.CaptureError, "two-advancing-generations-not-observed"):
            capture.acquire("AMD-DESKTOP", TARGET["processId"], self.seed, self.root / "out",
                            runner=runner, sleep=lambda _: None, selector=self.selector,
                            adapter_factory=Adapter, progress=lambda _: None)
        self.assertFalse((self.root / "out/result.json").exists())
        self.assertEqual(3, runner.scouts)
        self.assertEqual(6, len(runner.calls))  # three scouts and three packet reads, never more

    def test_accepts_real_like_partial_scout_exit_three_but_not_identity_failure(self):
        runner = FakeRunner(scout_exit=3)
        request = self.root / "request.json"
        request.write_text("{}")
        capture._run_native("scout-values-native", request, self.root / "unused", runner)

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
        runner = FakeRunner()
        deltas = (0, 0, 2)
        calls = {"decode": 0}
        original_decode = capture.decode_packet
        original_companion = capture._companion

        def decoder(packet):
            value = dict(original_decode(packet))
            delta = deltas[calls["decode"]]
            calls["decode"] += 1
            value["sequence"] += delta
            value["sourceTimeMs"] += delta * 1000
            return value

        def companion(data):
            value = original_companion(data)
            if value:
                delta = deltas[runner.scouts - 1]
                value["sequence"] += delta
                value["sampledAt"] = str(DECODED["sourceTimeMs"] / 1000 + delta)
            return value

        capture.decode_packet = decoder
        capture._companion = companion
        try:
            result = capture.acquire("AMD-DESKTOP", TARGET["processId"], self.seed,
                                     self.root / "out", runner=runner, sleep=lambda _: None,
                                     selector=self.selector, adapter_factory=Adapter,
                                     progress=lambda _: None)
        finally:
            capture.decode_packet = original_decode
            capture._companion = original_companion
        self.assertEqual(3, runner.scouts)
        self.assertEqual([DECODED["sequence"], DECODED["sequence"] + 2],
                         [item["sequence"] for item in result["generations"]])
        self.assertEqual("readerbridge-generation-not-advancing",
                         result["attempts"][1]["candidateFailure"])

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
