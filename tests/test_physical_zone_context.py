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
from tests.test_physical_only_selection import IDENTITY as BASE_IDENTITY, REPORT_IDENTITY as BASE_REPORT_IDENTITY

SHA_1177 = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
SHA_1179 = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"
QUALIFICATION_1179 = "1179 raw zone/cache candidates only; outer descriptor, child, zone ID and API agreement unverified"
QUALIFICATION_ID_1179 = "1179 zone ID candidate only; API correspondence, world instance, freshness and restart unverified"
IDENTITY = dict(BASE_IDENTITY, executableSha256=SHA_1177)
REPORT_IDENTITY = dict(BASE_REPORT_IDENTITY, executableSha256=SHA_1177)


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


def typed_report_1179():
    source = report()
    row = source["observation"]
    base = 0x140000000
    row["identity"].update(executableSha256=SHA_1179, moduleBaseAddress=base, moduleSize=0x3C51000)
    row.update(qualification=QUALIFICATION_ID_1179, outerVtableCandidate=True, recordAddress=0x10002000,
               recordVtable=base + 0x2B37EA8, recordGetterRva=0x1E7F180, rawNameRef=0x20003000)
    return source



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
        source["observation"].update(rawZoneKey=2**32 - 1, zoneIdCandidate="zFFFFFFFFD2EA79BE")
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
        source["observation"].update(childStatus="null", childKey=None, zoneIdCandidate="z487C9102A1DBBCFC")
        self.assertEqual(p._native_values("zone-context", source)["status"], "available-candidate")

    def test_1177_full_zone_id_must_match_child_even_with_correct_zone_key(self):
        source = report()
        row = source["observation"]
        row["zoneIdCandidate"] = "z487c9102d2ea79be"
        self.assertEqual(p._native_values("zone-context", source)["status"], "available-candidate")
        row["zoneIdCandidate"] = "z487C9102DEADBEEF"
        with self.assertRaisesRegex(ValueError, "invalid-native-zone-context-id"):
            p._native_values("zone-context", source)

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

    def run_native(self, *, stale=False, wrong_summary=False, unavailable=False, updated=False, wrong_epoch=False):
        with TemporaryDirectory() as directory:
            exe, path = Path(directory) / "reader.exe", Path(directory) / "zone.json"
            exe.write_bytes(b"MZ")
            selection = dict(status="ready", ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY))
            if updated:
                selection["target"]["executableSha256"] = SHA_1179

            def run(command, **kwargs):
                expected = [str(exe), "sample-current-zone-seed", "--pid", "123",
                            "--start-ticks", IDENTITY["processStartUtcTicks"], "--output", str(path)]
                self.assertEqual(command, expected + (["--sha256", SHA_1179] if updated else []))
                source = typed_report_1179() if updated else report()
                if wrong_epoch:
                    source["observation"]["identity"]["processStartUtcTicks"] += 1
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



    def test_unknown_zone_reader_sha_is_rejected(self):
        source = report()
        source["observation"]["identity"]["executableSha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "unsupported-native-zone-context-sha"):
            p._native_values("zone-context", source)

    def test_1179_typed_outer_does_not_qualify_child_or_id(self):
        source = typed_report_1179()
        row = source["observation"]
        row.update(qualification="1179 outer type candidate only; child, zone ID, API agreement and restart unverified",
                   rawZoneKey=12, childStatus="unverified-type",
                   childKey=None, zoneIdCandidate=None, rawNameRef=None)
        value = p._native_values("zone-context", source)
        self.assertEqual(value["status"], "unavailable")
        self.assertIsNone(value["zoneIdCandidate"])
        self.assertEqual(value["rawZoneKey"], 12)
        self.assertEqual(value["reason"], "zone-child-type-unverified")
        self.assertIs(value["outerVtableCandidate"], True)
        with self.assertRaisesRegex(ValueError, "invalid-native-zone-context-qualification"):
            p._native_values("zone-context", dict(source, observation=dict(row, qualification=QUALIFICATION_1179)))
        for change in (dict(childStatus="null", zoneIdCandidate="z0000000CD2EA79BE"),
                       dict(zoneIdCandidate="z0000000CD2EA79BE"), dict(childStatus="null"),
                       dict(childStatus="type-1e17-raw-candidate", childKey=123),
                       dict(status="unqualified-cache-record", childStatus="null")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                p._native_values("zone-context", dict(source, observation=dict(row, **change)))

    def test_1179_typed_id_fixed_native_vectors(self):
        for child, key, expected in (
                ("null", None, "z487C9102A1DBBCFC"),
                ("type-1e17-raw-candidate", 650763347, "z487C9102D2EA79BE"),
                ("type-1e17-raw-candidate", 0, "z487C9102A1DBBCFC"),
                ("type-1e17-raw-candidate", 0xFFFFFFFF, "z487C91021104BD15")):
            with self.subTest(child=child, key=key):
                source = typed_report_1179()
                row = source["observation"]
                row.update(childStatus=child, childKey=key, zoneIdCandidate=expected)
                if child == "null":
                    row["rawNameRef"] = 0
                value = p._native_values("zone-context", source)
                self.assertEqual(value["status"], "available-candidate")
                self.assertEqual(value["zoneIdCandidate"], expected)
                self.assertEqual(value["qualification"], QUALIFICATION_ID_1179)
                self.assertEqual(value["worldInstanceStatus"], "unavailable")

    def test_1179_cannot_forge_derivation_outer_child_qualification_or_build(self):
        source = typed_report_1179()
        row = source["observation"]
        for change in (dict(zoneIdCandidate="z487C9102D2EA79BF"), dict(zoneIdCandidate="z00000000D2EA79BE"),
                       dict(zoneIdCandidate=None), dict(childKey=650763348), dict(childKey=True),
                       dict(childStatus="null", childKey=None), dict(childStatus="unverified-type", childKey=None),
                       dict(status="unqualified-cache-record"), dict(status="cache-miss"),
                       dict(outerVtableCandidate=False), dict(outerVtableCandidate=None), dict(outerVtableCandidate=1),
                       dict(qualification=None), dict(qualification=QUALIFICATION_1179),
                       dict(identity=dict(row["identity"], executableSha256=SHA_1177)),
                       dict(identity=dict(row["identity"], executableSha256="a" * 64))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                p._native_values("zone-context", dict(source, observation=dict(row, **change)))

    def test_1179_typed_child_cannot_be_the_outer_record(self):
        source = typed_report_1179()
        row = source["observation"]
        row["rawNameRef"] = row["recordAddress"]
        with self.assertRaisesRegex(ValueError, "invalid-native-zone-1179-child-geometry"):
            p._native_values("zone-context", source)

    def test_1179_rejects_forged_raw_geometry_even_with_true_outer_flag(self):
        source = typed_report_1179()
        row = source["observation"]
        for field, faults in (
                ("recordAddress", (0, 0xFFFF, 0x100001, 0x7FFFFFFFFFF8, None)),
                ("recordVtable", (0, row["recordVtable"] + 8, float(row["recordVtable"]))),
                ("recordGetterRva", (0, row["recordGetterRva"] + 8, float(row["recordGetterRva"]))),
                ("rawNameRef", (0, True, 0x100001, 0x7FFFFFFFFFF8, None)),
                ("moduleBaseAddress", (0, True, 0x140000008, 0x7FFFFFFFF000, None)),
                ("moduleSize", (0, True, 0x2B37EA8, 2**32, None))):
            for value in faults:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    forged = deepcopy(source)
                    target = forged["observation"]
                    if field.startswith("module"):
                        target = target["identity"]
                    if value is None:
                        del target[field]
                    else:
                        target[field] = value
                    p._native_values("zone-context", forged)
        row.update(childStatus="null", childKey=None, zoneIdCandidate="z487C9102A1DBBCFC")
        for child_ref in (row["rawNameRef"], False, None):
            with self.subTest(null_child_ref=child_ref), self.assertRaises(ValueError):
                p._native_values("zone-context", dict(source, observation=dict(row, rawNameRef=child_ref)))

    def test_1179_genuine_zone_hash_does_not_attest_to_a_relocated_module(self):
        # Fixed zone/child-only vector from the accepted 1179 capture; addresses below are synthetic.
        source = typed_report_1179()
        row = source["observation"]
        row.update(rawZoneKey=12, childKey=1830661357, zoneIdCandidate="z0000000CB7B53FD7")
        self.assertEqual(p._native_values("zone-context", source)["status"], "available-candidate")

        # The saved vtable still falls INSIDE this relocated module, but at the wrong RVA.
        shift = 0x10000
        row["identity"]["moduleBaseAddress"] += shift
        with self.assertRaisesRegex(ValueError, "invalid-native-zone-1179-outer-geometry"):
            p._native_values("zone-context", source)
        row["recordVtable"] += shift
        self.assertEqual(p._native_values("zone-context", source)["zoneIdCandidate"], "z0000000CB7B53FD7")

        for required in ("recordVtable", "recordGetterRva"):
            with self.subTest(missing=required), self.assertRaisesRegex(ValueError, "invalid-native-zone-1179-outer-geometry"):
                forged = deepcopy(source)
                del forged["observation"][required]
                p._native_values("zone-context", forged)

    def test_1179_fresh_candidate_requires_selected_process_epoch(self):
        result = self.run_native(updated=True)
        self.assertEqual(result["nativeValues"]["status"], "available-candidate")
        self.assertEqual(self.run_native(updated=True, stale=True)["status"], "blocked")
        self.assertEqual(self.run_native(updated=True, wrong_epoch=True)["status"], "blocked")


    def test_1179_zone_context_admits_explicit_sha_but_withholds_unverified_zone_id(self):
        updated_sha = SHA_1179
        with TemporaryDirectory() as directory:
            exe, path = Path(directory) / "reader.exe", Path(directory) / "zone-1179.json"
            exe.write_bytes(b"MZ")
            selection = dict(status="ready", ownerHost="AMD-DESKTOP", target=deepcopy(IDENTITY))
            selection["target"]["executableSha256"] = updated_sha

            def run(command, **kwargs):
                self.assertEqual(command, [str(exe), "sample-current-zone-seed", "--pid", "123",
                    "--start-ticks", IDENTITY["processStartUtcTicks"], "--output", str(path),
                    "--sha256", updated_sha])
                source = report()
                source["observation"]["identity"]["executableSha256"] = updated_sha
                source["observation"]["qualification"] = QUALIFICATION_1179
                now = datetime.now(timezone.utc).isoformat()
                source["observation"].update(startedAtUtc=now, completedAtUtc=now,
                    status="unqualified-cache-record", childStatus="unverified-type",
                    childKey=None, zoneIdCandidate=None, outerVtableCandidate=True)
                path.write_text(json.dumps(source))
                receipt = dict(recordType="native-current-zone-seed-summary/1",
                    status="unqualified-cache-record", output=str(path))
                return subprocess.CompletedProcess(command, 0, json.dumps(receipt), "")

            with patch.object(p.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(p, "NATIVE_EXE", exe), patch.object(p.subprocess, "run", side_effect=run):
                result = p.read_native(selection, "zone-context", output=path)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["nativeValues"]["status"], "unavailable")
            self.assertEqual(result["nativeValues"]["reason"], "unqualified-cache-record")
            self.assertEqual(result["nativeValues"]["rawZoneKey"], 1216123138)
            self.assertIsNone(result["nativeValues"]["zoneIdCandidate"])
            self.assertIs(result["nativeValues"]["outerVtableCandidate"], True)

            forged = json.loads(path.read_text())
            for invalid in (1, "true"):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "invalid-native-zone-outer-diagnostic"):
                    forged["observation"]["outerVtableCandidate"] = invalid
                    p._native_values("zone-context", forged)

if __name__ == "__main__":
    unittest.main()
