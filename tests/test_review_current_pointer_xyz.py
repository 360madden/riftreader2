"""Offline contract regressions for current-epoch pointer-to-typed comparison."""
import base64
import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from scripts import review_current_pointer_xyz as review

GAME_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
TICKS = 639284177321390013
XYZ = (7461.1997070312, 863.84997558594, 2977.0598144531)


class CurrentPointerReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = {
            "processId": 6940, "processStartUtcTicks": TICKS,
            "executableSha256": GAME_SHA,
        }
        self.request = {
            "schemaVersion": 1, "evidenceKind": review.REQUEST_KIND,
            "target": self.target, "rootRva": "0x32E0200",
            "offsets": ["0x0"], "terminalByteLength": 816,
            "maxDurationMilliseconds": 5000,
        }
        self.source = {
            "schemaVersion": 1, "evidenceKind": review.SOURCE_KIND,
            "status": "advanced-in-covered-scope", "identity": dict(self.target),
            "source": {
                "after": {"completedAtUtc": "2026-10-24T21:36:29.2356771Z"}},
            "selected": {
                "before": {"playerUnitId": "u035400012FA2D207",
                           "sequence": 112332, "frameTime": 56728.36,
                           "xyz": dict(zip("xyz", XYZ))},
                "after": {"playerUnitId": "u035400012FA2D207",
                          "sequence": 112588, "frameTime": 56858.11,
                          "xyz": dict(zip("xyz", XYZ))},
            },
        }
        self.identity = {
            **self.target, "moduleBaseAddress": 0x7FF6EBDA0000,
            "moduleSize": 62611456, "executablePath": r"C:\RIFT_TRANSFER\RIFT\rift_x64.exe",
        }
        self.owner = 0x216ECFE06A0
        self.before = self.make_report("2026-10-24T22:12:00Z")
        self.after = self.make_report("2026-10-24T22:13:00Z")
        self.reqfile = self.root / "request.json"
        self.sourcefile = self.root / "source.json"
        self.beforefile = self.root / "before.json"
        self.afterfile = self.root / "after.json"
        self.write(self.reqfile, self.request)
        self.write(self.sourcefile, self.source)
        self.write(self.beforefile, self.before)
        self.write(self.afterfile, self.after)

    def write(self, path, payload):
        path.write_text(json.dumps(payload), encoding="utf-8")

    def make_report(self, when, *, coords=XYZ):
        data = bytearray(816)
        struct.pack_into("<fff", data, 0x320, *coords)
        raw_ptr = struct.pack("<Q", self.owner)
        request_data = json.dumps(self.request).encode("utf-8")
        return {
            "schemaVersion": 1, "evidenceKind": review.POINTER_KIND,
            "requestSha256": hashlib.sha256(request_data).hexdigest().upper(),
            "completedAtUtc": when,
            "chain": {"rootRva": review.ROOT_RVA, "offsets": [0]},
            "resolution": {
                "status": "complete", "reason": None,
                "expectedIdentity": dict(self.identity),
                "observedIdentity": dict(self.identity),
                "hops": [{
                    "level": 1,
                    "pointerAddress": self.identity["moduleBaseAddress"] + review.ROOT_RVA,
                    "pointerBytes": base64.b64encode(raw_ptr).decode("ascii"),
                    "pointerValue": self.owner,
                    "offset": 0, "resolvedAddress": self.owner,
                }],
                "terminalAddress": self.owner,
                "terminalRead": {
                    "status": "success",
                    "bytes": base64.b64encode(data).decode("ascii"),
                    "win32ErrorCode": None, "reason": None,
                },
                "failedRead": None, "failedReadAddress": None,
            },
        }

    def sync_reports(self):
        """Request file hash changes when a fixture request is rewritten."""
        raw = self.reqfile.read_bytes()
        digest = hashlib.sha256(raw).hexdigest().upper()
        self.before["requestSha256"] = digest
        self.after["requestSha256"] = digest
        self.write(self.beforefile, self.before)
        self.write(self.afterfile, self.after)

    def inspect(self):
        return review.review(
            self.beforefile, self.afterfile, self.reqfile, self.sourcefile,
            hashlib.sha256(self.sourcefile.read_bytes()).hexdigest().upper(), 0.02)

    def test_exact_source_and_two_native_windows_candidate_match(self):
        self.sync_reports()
        value = self.inspect()
        self.assertEqual(value["status"], "candidate-compatible")
        self.assertEqual(value["qualification"], "candidate-only-not-synchronized")
        self.assertEqual(value["playerUnitId"], "u035400012FA2D207")
        self.assertEqual(len(value["comparisons"]), 2)
        self.assertTrue(all(v["allAxesWithinTolerance"] for v in value["comparisons"]))
        self.assertGreater(value["comparisons"][0]["sourceToNativeSeconds"], 1800)

    def test_wrong_position_preserved_as_disagreement(self):
        self.sync_reports()
        self.after = self.make_report("2026-10-24T22:13:00Z",
                                      coords=(7458.0, XYZ[1], XYZ[2]))
        self.write(self.afterfile, self.after)
        result = self.inspect()
        self.assertEqual(result["status"], "candidate-disagrees")
        self.assertFalse(result["comparisons"][1]["allAxesWithinTolerance"])

    def test_wrong_pointer_hop_and_raw_bytes_are_rejected(self):
        self.sync_reports()
        for key, bad in (("pointerAddress", 12345), ("pointerValue", self.owner + 4)):
            record = json.loads(self.beforefile.read_text())
            record["resolution"]["hops"][0][key] = bad
            self.write(self.beforefile, record)
            with self.subTest(key=key), self.assertRaises(review.EvidenceError):
                self.inspect()
            self.write(self.beforefile, self.before)

    def test_rejects_wrong_process_epoch_and_sha_pin(self):
        self.sync_reports()
        original = self.after["resolution"]["observedIdentity"]["processStartUtcTicks"]
        self.after["resolution"]["observedIdentity"]["processStartUtcTicks"] = TICKS - 1
        self.write(self.afterfile, self.after)
        with self.assertRaisesRegex(review.EvidenceError, "epoch"):
            self.inspect()
        self.after["resolution"]["observedIdentity"]["processStartUtcTicks"] = original
        self.write(self.afterfile, self.after)
        with self.assertRaisesRegex(review.EvidenceError, "changed"):
            review.review(self.beforefile, self.afterfile, self.reqfile,
                          self.sourcefile, "F" * 64, 0.02)

    def test_rejects_stale_or_conflicting_typed_frame_source(self):
        self.sync_reports()
        self.source["selected"]["after"]["sequence"] = 100
        self.write(self.sourcefile, self.source)
        with self.assertRaisesRegex(review.EvidenceError, "did not independently advance"):
            self.inspect()

    def test_rejects_typed_movement_as_nonstationary_reference(self):
        self.sync_reports()
        self.source["selected"]["before"]["xyz"]["x"] -= 2.0
        self.write(self.sourcefile, self.source)
        with self.assertRaisesRegex(review.EvidenceError, "position changed"):
            self.inspect()

    def test_rejects_incomplete_native_terminal_and_nan_float(self):
        self.sync_reports()
        self.before["resolution"]["terminalRead"]["status"] = "partial"
        self.write(self.beforefile, self.before)
        with self.assertRaisesRegex(review.EvidenceError, "incomplete"):
            self.inspect()
        self.before = self.make_report("2026-10-24T22:12:00Z", coords=(float("nan"), 1.0, 2.0))
        self.write(self.beforefile, self.before)
        with self.assertRaisesRegex(review.EvidenceError, "nonfinite"):
            self.inspect()

    def test_rejects_reused_native_bytes_and_reversed_capture_time(self):
        self.sync_reports()
        self.afterfile.write_bytes(self.beforefile.read_bytes())
        with self.assertRaisesRegex(review.EvidenceError, "same bytes"):
            self.inspect()
        self.after = self.make_report("2026-10-24T21:00:00Z")
        self.write(self.afterfile, self.after)
        with self.assertRaisesRegex(review.EvidenceError, "chronologically"):
            self.inspect()

    def test_rejects_duplicate_json_source_keys(self):
        self.sync_reports()
        self.sourcefile.write_text('{"status":"bad","status":"good"}')
        with self.assertRaisesRegex(review.EvidenceError, "duplicate JSON"):
            self.inspect()

    def test_output_is_no_overwrite_and_retains_originals(self):
        self.sync_reports()
        destination = self.root / "result.json"
        source_sha = hashlib.sha256(self.sourcefile.read_bytes()).hexdigest().upper()
        args = ["--before", str(self.beforefile), "--after", str(self.afterfile),
                "--request", str(self.reqfile), "--source", str(self.sourcefile),
                "--source-sha256", source_sha, "--output", str(destination)]
        self.assertEqual(review.main(args), 0)
        saved = destination.read_bytes()
        self.assertEqual(review.main(args), 2)
        self.assertEqual(destination.read_bytes(), saved)
        self.assertTrue(destination.is_file())


if __name__ == "__main__":
    unittest.main()
