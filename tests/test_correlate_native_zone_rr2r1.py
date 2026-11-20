"""Offline-only native-to-RR2R1 zone candidate comparison regression tests."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import correlate_native_zone_rr2r1 as mod
from tests.test_inspect_typed_resource import snapshot
from tests.test_physical_zone_context import typed_report_1179

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / "contracts/addon/fixtures/reference-v1.json").read_text())
NONCE = REFERENCE["nonce"]
PLAYER = 0x035400012FA2D207
ZONE = "z487C9102D2EA79BE"


class ZoneCorrelationTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.native_path = self.dir / "native-zone.json"
        self.typed_path = self.dir / "reference.json"
        self.native = typed_report_1179()
        self.native["observation"]["selfKey"] = PLAYER
        self.save_native()
        self.lua = deepcopy(REFERENCE["before"])
        self.lua["player"] = {"status": "ok", "value": f"u{PLAYER:016X}"}
        self.lua["fields"]["zone"] = {"status": "ok", "value": ZONE}
        self.save_reference()

    def save_native(self):
        self.native_path.write_text(json.dumps(self.native), encoding="utf-8")

    def save_reference(self):
        raw = b"RR2R1|" + json.dumps(self.lua, separators=(",", ":")).encode("ascii") + b"|ENDRR2R1"
        snapshot(self.typed_path, raw)
        report = json.loads(self.typed_path.read_text(encoding="utf-8"))
        report["identity"] = deepcopy(self.native["observation"]["identity"])
        report["startedAtUtc"] = "2026-11-12T17:45:28.3550000+00:00"
        report["completedAtUtc"] = "2026-11-12T17:45:28.5550000+00:00"
        self.typed_path.write_text(json.dumps(report), encoding="utf-8")

    def read(self, **options):
        return mod.compare(self.native_path, self.typed_path, NONCE, **options)

    def test_true_candidate_agreement_preserves_evidence_and_scope(self):
        value = self.read()
        self.assertEqual(value["status"], "matching-candidates")
        self.assertEqual(value["luaZoneIdCandidate"], ZONE)
        self.assertEqual(value["nativeZoneIdCandidate"], ZONE)
        self.assertEqual(value["playerUnitId"], f"u{PLAYER:016X}")
        self.assertEqual(value["worldInstanceStatus"], "unavailable")
        self.assertEqual(value["referenceSessionId"], NONCE)
        self.assertTrue(value["nativeSourceSha256"])
        self.assertTrue(value["referenceSnapshotSha256"])
        self.assertIn("not an atomic", value["qualification"])

    def test_different_valid_zone_id_is_mismatch_not_false_match(self):
        self.lua["fields"]["zone"]["value"] = "z0000000CB7B53FD7"
        self.save_reference()
        self.assertEqual(self.read()["status"], "mismatched-candidates")

    def test_wrong_process_epoch_or_build_is_refused(self):
        for field, wrong in (("processId", 999),
                             ("processStartUtcTicks", 123),
                             ("executableSha256", "F" * 64)):
            with self.subTest(field=field):
                self.save_reference()
                snap = json.loads(self.typed_path.read_text())
                snap["identity"][field] = wrong
                self.typed_path.write_text(json.dumps(snap), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "process-epoch-or-build-mismatch"):
                    self.read()

    def test_wrong_module_and_player_refused(self):
        self.lua["player"]["value"] = "u0000000000000001"
        self.save_reference()
        with self.assertRaisesRegex(ValueError, "player-identity-mismatch"):
            self.read()
        self.lua["player"]["value"] = f"u{PLAYER:016X}"
        self.save_reference()
        snap = json.loads(self.typed_path.read_text())
        snap["identity"]["moduleBaseAddress"] += 0x1000
        self.typed_path.write_text(json.dumps(snap), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "module-identity-mismatch"):
            self.read()

    def test_zone_unavailable_or_noncanonical_refused(self):
        self.lua["fields"]["zone"] = {"status": "unavailable"}
        self.save_reference()
        with self.assertRaisesRegex(ValueError, "lua-zone-unavailable"):
            self.read()
        self.lua["fields"]["zone"] = {"status": "ok", "value": "Sanctum"}
        self.save_reference()
        with self.assertRaisesRegex(ValueError, "lua-zone-not-canonical-id"):
            self.read()

    def test_cross_day_comparison_refused_even_with_same_zone(self):
        snap = json.loads(self.typed_path.read_text())
        snap["startedAtUtc"] = "2026-11-15T00:00:01+00:00"
        snap["completedAtUtc"] = "2026-11-15T00:00:02+00:00"
        self.typed_path.write_text(json.dumps(snap), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sample-gap-too-large"):
            self.read()

    def test_tenth_microsecond_gap_is_not_silently_truncated(self):
        # Native UTC ends at ...3548083, reference begins exactly one 100 ns
        # tick later: a zero-gap budget must reject it rather than round to 0.
        report = json.loads(self.typed_path.read_text(encoding="utf-8"))
        report["startedAtUtc"] = "2026-11-12T17:45:28.3548084+00:00"
        report["completedAtUtc"] = "2026-11-12T17:45:28.3548084+00:00"
        self.typed_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sample-gap-too-large"):
            self.read(max_gap_seconds=0)
        self.assertEqual(self.read(max_gap_seconds=1)["status"], "matching-candidates")

    def test_invalid_gap_budget_refused(self):
        for gap in (-1, 31, float("inf"), True):
            with self.subTest(gap=gap), self.assertRaisesRegex(ValueError, "invalid-gap-budget"):
                self.read(max_gap_seconds=gap)

    def test_foreign_nonce_and_corrupt_native_report_refused(self):
        with self.assertRaisesRegex(ValueError, "session-mismatch"):
            mod.compare(self.native_path, self.typed_path, "a" * 32)
        self.native["observation"]["zoneIdCandidate"] = "zFFFFFFFF00000000"
        self.save_native()
        with self.assertRaisesRegex(ValueError, "invalid-native-zone-context-id"):
            self.read()

    def test_cli_outputs_bounded_result_without_overwriting(self):
        dest = self.dir / "result.json"
        args = ["--native-zone", str(self.native_path),
                "--reference-snapshot", str(self.typed_path),
                "--session-id", NONCE, "--output", str(dest)]
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(mod.main(args), 0)
        result = json.loads(dest.read_text())
        self.assertEqual(result["status"], "matching-candidates")
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(mod.main(args), 2)
        self.assertIn("output-exists", out.getvalue())

    def test_never_accesses_the_running_game(self):
        with patch.object(mod.physical_rift, "select_physical") as select, \
             patch.object(mod.physical_rift, "read_native") as read:
            self.read()
            select.assert_not_called()
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
