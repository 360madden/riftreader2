"""Exact saved zone contract and injected CLI acquisition; no native game access."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as p
from tests.test_physical_only_selection import IDENTITY, REPORT_IDENTITY


def report():
    return {"schemaVersion": 1, "contractVersion": "native-current-zone-seed-candidate/1",
        "status": "complete", "observation": {
            "identity": deepcopy(REPORT_IDENTITY),
            "startedAtUtc": "2026-11-12T17:45:28.2968382+00:00",
            "completedAtUtc": "2026-11-12T17:45:28.3548083+00:00",
            "selfKey": 2**64 - 1, "rawZoneKey": 1216123138,
            "status": "type-0073-candidate", "childStatus": "type-1e17-raw-candidate",
            "childKey": 650763347, "zoneIdCandidate": "z487C9102D2EA79BE",
            "qualification": "zone ID candidate only; API correspondence, name, freshness and restart unverified",
            "acquisitionElapsedMilliseconds": 58.0929, "acquisitionElapsedClock": "monotonic-stopwatch",
            "acquisitionElapsedKind": "zone-read-including-final-validation"}}


class ZoneContextTests(unittest.TestCase):
    def test_actual_shape_nested_identity_exact_zone_and_lossless_self_key(self):
        value = p._native_values("zone-context", report())
        self.assertEqual(value["selfKey"], "18446744073709551615")
        self.assertEqual(value["rawZoneKey"], 1216123138)
        self.assertEqual(value["zoneIdCandidate"], "z487C9102D2EA79BE")
        self.assertEqual(value["status"], "available-candidate")
        self.assertEqual(value["worldInstanceStatus"], "unavailable")
        self.assertEqual(value["nativeStatus"], "type-0073-candidate")
        self.assertIn("restart unverified", value["qualification"])

    def test_optional_matching_top_identity_and_uint32_max_key(self):
        source = report()
        source["identity"] = deepcopy(source["observation"]["identity"])
        source["observation"].update(rawZoneKey=2**32 - 1, zoneIdCandidate="zFFFFFFFF00000000")
        self.assertEqual(p._native_values("zone-context", source)["rawZoneKey"], 4294967295)

    def test_unresolved_statuses_keep_raw_key_and_explicit_reason(self):
        for status in ("null-provider", "null-registry", "cache-miss", "null-holder", "null-record",
                       "unqualified-cache-record", "type-0073-candidate"):
            with self.subTest(status=status):
                source = report()
                child = "unverified-type" if status in ("unqualified-cache-record", "type-0073-candidate") else None
                source["observation"].update(status=status, childStatus=child, childKey=None, zoneIdCandidate=None)
                value = p._native_values("zone-context", source)
                self.assertEqual(value["status"], "unavailable")
                self.assertEqual(value["nativeStatus"], status)
                self.assertEqual(value["rawZoneKey"], 1216123138)
                self.assertTrue(value["reason"])
                self.assertIsNone(value["zoneIdCandidate"])

    def test_null_child_can_support_typed_zone_id(self):
        source = report()
        source["observation"].update(childStatus="null", childKey=None)
        self.assertEqual(p._native_values("zone-context", source)["status"], "available-candidate")

    def test_forged_or_missing_zone_id_and_status_rejected(self):
        for change in (dict(zoneIdCandidate="zBAD"), dict(zoneIdCandidate="z00000000D2EA79BE"),
                       dict(status="cache-miss"), dict(status="complete"), dict(zoneIdCandidate=None),
                       dict(childStatus="null"), dict(childKey=True), dict(childKey=2**32)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                source = report()
                source["observation"].update(change)
                p._native_values("zone-context", source)

    def test_float_boolean_string_and_overflow_keys_rejected(self):
        for field, values in (("selfKey", (float(2**64 - 1), True, "42", 0, 2**64)),
                              ("rawZoneKey", (1., True, "12", -1, 2**32))):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    source = report()
                    source["observation"][field] = value
                    p._native_values("zone-context", source)

    def test_identity_contract_and_qualification_mismatches_rejected(self):
        for fault in ("top", "pid", "ticks", "sha", "contract", "qualification", "schema"):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                source = report()
                if fault == "top": source["identity"] = dict(REPORT_IDENTITY, processId=999)
                if fault == "pid": source["observation"]["identity"]["processId"] = True
                if fault == "ticks": source["observation"]["identity"]["processStartUtcTicks"] = "1"
                if fault == "sha": source["observation"]["identity"]["executableSha256"] = "bad"
                if fault == "contract": source["contractVersion"] = "other/1"
                if fault == "qualification": source["observation"]["qualification"] = "qualified"
                if fault == "schema": source["schemaVersion"] = True
                p._native_values("zone-context", source)

    def test_exact_100ns_order_utc_and_elapsed_validation(self):
        for change in (dict(startedAtUtc="2026-11-12T17:45:28.3548084Z"),
                       dict(completedAtUtc="2026-11-12T17:45:28.3548083-05:00"),
                       dict(acquisitionElapsedMilliseconds=True),
                       dict(acquisitionElapsedMilliseconds=float("nan")),
                       dict(acquisitionElapsedClock="wallclock")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                source = report()
                source["observation"].update(change)
                p._native_values("zone-context", source)

    def run_native(self, *, stale=False, wrong_summary=False, unavailable=False):
        with TemporaryDirectory() as directory:
            exe, path = Path(directory) / "reader.exe", Path(directory) / "zone.json"
            exe.write_bytes(b"MZ")
            selection = dict(status="ready", ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY))
            def run(command, **kwargs):
                self.assertEqual(command, [str(exe), "sample-current-zone-seed", "--pid", "123",
                    "--start-ticks", IDENTITY["processStartUtcTicks"], "--output", str(path)])
                source = report()
                if not stale:
                    now = datetime.now(timezone.utc).isoformat()
                    source["observation"].update(startedAtUtc=now, completedAtUtc=now)
                if unavailable:
                    source["observation"].update(status="cache-miss", childStatus=None, childKey=None, zoneIdCandidate=None)
                path.write_text(json.dumps(source))
                summary = dict(recordType="native-current-zone-seed-summary/1",
                    status="complete" if wrong_summary else source["observation"]["status"], output=str(path))
                return subprocess.CompletedProcess(command, 0, json.dumps(summary), "")
            with patch.object(p.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(p, "NATIVE_EXE", exe), patch.object(p.subprocess, "run", side_effect=run):
                result = p.read_native(selection, "zone-context", output=path)
            if result["status"] == "complete":
                self.assertEqual(result["nativeSourceSha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(result["nativeOutput"], str(path))
            return result

    def test_new_command_typed_summary_invocation_freshness_and_source_hash(self):
        result = self.run_native()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeRead"], "zone-context")
        self.assertEqual(result["nativeValues"]["selfKey"], str(2**64 - 1))

    def test_unresolved_context_is_complete_acquisition_not_fabricated_zone(self):
        result = self.run_native(unavailable=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["nativeValues"]["status"], "unavailable")
        self.assertEqual(result["nativeValues"]["reason"], "cache-miss")

    def test_retained_or_mismatched_receipt_cannot_become_fresh_read(self):
        self.assertEqual(self.run_native(stale=True)["status"], "blocked")
        self.assertEqual(self.run_native(wrong_summary=True)["status"], "blocked")

    def test_existing_mappings_preserved_and_zone_cannot_request_burst(self):
        self.assertEqual(p.NATIVE_READS["facing"], "sample-current-facing")
        self.assertEqual(p.NATIVE_READS["unit-positions"], "sample-current-unit-positions")
        self.assertEqual(p.NATIVE_RECEIPTS["stats"], "native-current-stats-summary/1")
        selection = dict(status="ready", ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY))
        with patch.object(p.socket, "gethostname", return_value="AMD-DESKTOP"), patch.object(p.subprocess, "run") as run:
            self.assertEqual(p.read_native(selection, "zone-context", samples=2)["status"], "blocked")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
