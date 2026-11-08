"""Offline validation and simulated VMware transport for the location/pair wrapper."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import sample_current_native_location_pair as native
from tests.test_sample_current_native_xyz import FakeGuest, FakeLab

PID, TICKS = 11572, 639293038821710082
A, B, C, D = ("2026-11-07T00:00:00.0000000Z", "2026-11-07T00:00:00.0010000Z",
              "2026-11-07T00:00:00.0020000Z", "2026-11-07T00:00:00.0030000Z")


def identity():
    return {"processId": PID, "processStartUtcTicks": TICKS, "executablePath": "rift_x64.exe",
            "executableSha256": native.GAME_SHA, "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000}


def location():
    return {"schemaVersion": 1, "status": "complete", "contractVersion": "native-current-location-context-candidate/1",
            "observation": {"identity": identity(), "startedAtUtc": A, "completedAtUtc": D,
                "unitKey": "123", "unitIdCandidate": "u000000000000007B",
                "positionStartedAtUtc": A, "positionCompletedAtUtc": B, "position": {"x": 1, "y": 2, "z": 3},
                "status": "candidate-only", "worldInstanceStatus": "unavailable",
                "qualification": native.LOCATION_QUALIFICATION,
                "zone": {"identity": identity(), "startedAtUtc": C, "completedAtUtc": D,
                         "selfKey": 123, "rawZoneKey": 7, "status": "null-provider",
                         "zoneIdCandidate": None, "qualification": native.ZONE_QUALIFICATION}}}


def paired(target=True):
    def sample(key, start, end, utc_start, utc_end):
        return {"status": "candidate", "unitKey": str(key), "unitIdCandidate": f"u{key:016X}",
                "position": {"x": 1, "y": 2, "z": 3}, "startedAtUtc": utc_start, "completedAtUtc": utc_end,
                "monotonicStartMilliseconds": start, "monotonicEndMilliseconds": end}
    return {"schemaVersion": 1, "status": "complete",
            "contractVersion": "native-current-paired-position-candidate-sample/1",
            "qualification": native.PAIR_QUALIFICATION, "processRevalidationStatus": "passed-before-publication",
            "observation": {"identity": identity(), "startedAtUtc": A, "completedAtUtc": D,
                "clockDomain": "a" * 32, "self": sample(123, 0, 1, A, B),
                "target": sample(456, 2, 3, C, D) if target else None,
                "targetStatus": "candidate" if target else "unavailable",
                "beforeGuardStatus": "getter-candidate", "afterGuardStatus": "getter-candidate",
                "acquisitionSpanMilliseconds": 3, "startSkewMilliseconds": 2 if target else None,
                "maximumSampleSeparationMilliseconds": 3 if target else None,
                "status": "paired-candidate" if target else "target-unavailable",
                "qualification": native.PAIR_QUALIFICATION, "zoneIdentityStatus": "unavailable",
                "worldIdentityStatus": "unavailable", "atomicityQualified": False}}


class ValidationTests(unittest.TestCase):
    def check(self, report, mode):
        return native.validate_report(report, mode=mode, pid=PID, ticks=TICKS)

    def test_location_null_zone_and_typed_id_are_preserved(self):
        value = location()
        self.assertIsNone(self.check(value, "location-context")["zoneIdCandidate"])
        zone = value["observation"]["zone"]
        zone.update(zoneIdCandidate="z0000000700000000", status="type-0073-candidate", childStatus="null")
        self.assertEqual("z0000000700000000", self.check(value, "location-context")["zoneIdCandidate"])
        zone["selfKey"] = 456
        with self.assertRaises(ValueError): self.check(value, "location-context")

    def test_pair_candidate_null_target_and_missing_component_are_distinct(self):
        self.assertIsNone(self.check(paired(False), "paired-position")["target"])
        value = paired()
        self.assertEqual("456", self.check(value, "paired-position")["target"]["unitKey"])
        value["observation"]["target"].update(status="component-unavailable", position=None)
        value["observation"].update(status="target-unavailable", targetStatus="component-unavailable")
        self.assertIsNone(self.check(value, "paired-position")["target"]["position"])

    def test_wrong_epoch_module_build_unit_and_nonfinite_rejected(self):
        for mode, source in (("location-context", location()), ("paired-position", paired())):
            for key, value in (("processId", True), ("processStartUtcTicks", TICKS+1),
                               ("executableSha256", "0"*64), ("moduleBaseAddress", 3), ("moduleSize", 1)):
                report = copy.deepcopy(source)
                report["observation"]["identity"][key] = value
                with self.subTest(mode=mode, key=key), self.assertRaises(ValueError): self.check(report, mode)
            row = source["observation"] if mode == "location-context" else source["observation"]["self"]
            for bad in (True, "0", "01", "18446744073709551616"):
                report = copy.deepcopy(source)
                own = report["observation"] if mode == "location-context" else report["observation"]["self"]
                own["unitKey"] = bad
                with self.assertRaises(ValueError): self.check(report, mode)
            row["position"]["x"] = float("nan")
            with self.assertRaises(ValueError): self.check(source, mode)

    def test_inverted_nested_tick_interval_and_pair_guard_or_span_rejected(self):
        value = location()
        value["observation"]["zone"]["startedAtUtc"] = "2026-11-07T00:00:00.0030001Z"
        with self.assertRaises(ValueError): self.check(value, "location-context")
        for key, bad in (("afterGuardStatus", "changed"), ("atomicityQualified", True),
                         ("zoneIdentityStatus", "qualified"), ("acquisitionSpanMilliseconds", 1001),
                         ("startSkewMilliseconds", 3), ("maximumSampleSeparationMilliseconds", 4),
                         ("clockDomain", "bad")):
            value = paired()
            value["observation"][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(value, "paired-position")

    def test_missing_or_promoted_contract_is_rejected(self):
        for mode, source in (("location-context", location()), ("paired-position", paired())):
            for bad in (None, {}, [], {**source, "schemaVersion": True}, {**source, "status": "qualified"}):
                with self.assertRaises(ValueError): self.check(bad, mode)
            source["observation"]["qualification"] = "qualified"
            with self.assertRaises(ValueError): self.check(source, mode)


class WrapperTests(unittest.TestCase):
    def run_fake(self, mode, *, installed=True, result=None, pin_sha=True, source_changed=False, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        reader = folder / "RiftReader2.Live.exe"
        reader.write_bytes(b"offline-fake-reader")
        guest = FakeGuest(installed=installed, result=result or (location() if mode == "location-context" else paired()))
        lab = FakeLab(guest)
        source_calls = 0
        def digest(path):
            nonlocal source_calls
            if Path(path) == reader: return native.READER_SHA if pin_sha else "0"*64
            source_calls += 1
            return ("A" if not source_changed or source_calls == 1 else "B")*64
        with patch.object(native, "READER", reader), patch.object(native, "READER_LENGTH", reader.stat().st_size), \
                patch.object(native, "EVIDENCE", folder/"runs"), patch.object(native, "digest", side_effect=digest), \
                patch.object(native, "LabCodex", return_value=lab):
            summary = native.run("lab2", mode, **kwargs)
        return summary, guest

    def test_each_mode_reuses_pinned_cache_and_retains_source_hashes(self):
        for mode in ("location-context", "paired-position"):
            summary, guest = self.run_fake(mode)
            self.assertTrue(summary["guestReaderReused"])
            self.assertEqual(0, guest.copy_calls)
            self.assertEqual("A"*64, summary["sourceScriptSha256"])
            self.assertEqual(native.READER_SHA, summary["readerExecutableSha256"])
            raw = Path(summary["sourceReport"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest().upper(), summary["sourceReportSha256"])
            self.assertEqual("candidate-only", summary["status"])
            self.assertEqual("unverified-not-acquired-by-wrapper", summary["cooperativeExclusionStatus"])
            self.assertEqual("unqualified", summary["liveReadiness"])
            self.assertIn("does not acquire", native.__doc__)
            self.assertIn("activeNativeRead", native.__doc__)
            scripts = " ".join(guest.shell_scripts)
            self.assertIn("sample-current-" + mode, scripts)
            self.assertIn("CreateNew", scripts)
            self.assertIn("game-epoch-changed", scripts)
            self.assertNotIn("Stop-Process", scripts)
            self.assertNotIn("Start-Process", scripts)

    def test_missing_cache_copies_only_into_isolated_sha_folder(self):
        summary, guest = self.run_fake("paired-position", installed=False)
        self.assertFalse(summary["guestReaderReused"])
        self.assertEqual(1, guest.copy_calls)
        self.assertIn("current-location-pair-" + native.READER_SHA[:16], guest.shell_scripts[1])

    def test_sha_source_and_report_mismatches_fail_closed(self):
        with self.assertRaises(ValueError): self.run_fake("location-context", pin_sha=False)
        with self.assertRaisesRegex(ValueError, "source-changed"):
            self.run_fake("location-context", source_changed=True)
        value = paired()
        value["observation"]["identity"]["processId"] += 1
        with self.assertRaises(ValueError): self.run_fake("paired-position", result=value)

    def test_optional_process_pin_mismatch_and_options_stop_before_launch(self):
        with self.assertRaisesRegex(ValueError, "game-pin-mismatch"):
            self.run_fake("location-context", expected_game={
                "lab": "lab2", "processId": PID+1, "processStartUtcTicks": TICKS, "executableSha256": native.GAME_SHA})
        with patch.object(native, "LabCodex") as api:
            for lab, mode in (("bad", "paired-position"), ("lab2", "bad")):
                with self.assertRaises(ValueError): native.run(lab, mode)
            api.assert_not_called()


if __name__ == "__main__": unittest.main()
