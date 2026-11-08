"""Offline validation and simulated VMware transport for the location/pair wrapper."""
import copy
import base64
import ctypes
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import sample_current_native_location_pair as native
from tests.test_sample_current_native_xyz import FakeGuest, FakeLab
from scripts.vmware_guest_session import MAX_ENCODED_POWERSHELL_CHARS

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
                "beforeGuardStatus": "fallback-key-candidate" if target else "raw-getter-zero-candidate",
                "afterGuardStatus": "fallback-key-candidate" if target else "raw-getter-zero-candidate",
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
        zone.update(zoneIdCandidate="z00000007A1DBBCFC", status="type-0073-candidate", childStatus="null")
        self.assertEqual("z00000007A1DBBCFC", self.check(value, "location-context")["zoneIdCandidate"])
        zone["selfKey"] = 456
        with self.assertRaises(ValueError): self.check(value, "location-context")

    def test_zone_capture_must_follow_position_even_within_outer_interval(self):
        value = location()
        zone = value["observation"]["zone"]
        # Equal boundaries are valid: the .NET reader captures zone after XYZ.
        zone.update(startedAtUtc=B, completedAtUtc=D)
        self.check(value, "location-context")
        for earlier in (A, "2026-11-07T00:00:00.0009999Z"):
            zone.update(startedAtUtc=earlier, completedAtUtc=D)
            with self.subTest(startedAtUtc=earlier), self.assertRaises(ValueError):
                self.check(value, "location-context")

    def test_zone_full_formula_and_signed_child_boundaries(self):
        for child, expected in ((0, "A1DBBCFC"), (1, "B2B23994"),
                                (2147483647, "A1DBBCFC"), (2147483648, "1104BD15"),
                                (4294967295, "1104BD15")):
            value = location()
            zone = value["observation"]["zone"]
            zone.update(status="type-0073-candidate", childStatus="type-1e17-raw-candidate",
                        childKey=child, zoneIdCandidate="z00000007" + expected)
            with self.subTest(child=child):
                self.assertEqual(zone["zoneIdCandidate"], self.check(value, "location-context")["zoneIdCandidate"])
                zone["zoneIdCandidate"] = "z0000000700000000"
                with self.assertRaises(ValueError): self.check(value, "location-context")

    def test_inconsistent_zone_branch_or_child_rejected(self):
        for changes in (
                dict(status="invented"),
                dict(status="type-0073-candidate", childStatus="null", zoneIdCandidate="z0000000700000000"),
                dict(status="type-0073-candidate", childStatus="null", childKey=1, zoneIdCandidate="z00000007A1DBBCFC"),
                dict(status="type-0073-candidate", childStatus="type-1e17-raw-candidate", zoneIdCandidate="z00000007A1DBBCFC"),
                dict(status="type-0073-candidate", childStatus="null", zoneIdCandidate=None),
                dict(status="null-provider", childStatus="null"),
                dict(status="unqualified-cache-record", childStatus="null", zoneIdCandidate="z00000007A1DBBCFC")):
            value = location()
            value["observation"]["zone"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check(value, "location-context")

    def test_guard_status_must_match_target_presence(self):
        unavailable = ("raw-getter-zero-candidate", "override-unavailable", "guard-unreadable-or-invalid")
        for guard in unavailable:
            value = paired(False)
            value["observation"].update(beforeGuardStatus=guard, afterGuardStatus=guard)
            self.assertIsNone(self.check(value, "paired-position")["target"])
        for target, guard in ((True, ""), (True, "getter-candidate"),
                              (True, "guard-unreadable-or-invalid"), (False, "fallback-key-candidate")):
            value = paired(target)
            value["observation"].update(beforeGuardStatus=guard, afterGuardStatus=guard)
            with self.subTest(target=target, guard=guard), self.assertRaises(ValueError):
                self.check(value, "paired-position")

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

    def test_native_hash_matches_independent_signed_csharp_arithmetic(self):
        # C# unchecked int/uint casts and division truncated toward zero.
        def reference(key):
            signed = ctypes.c_int32(key).value
            quotient = int(signed / 127773)
            remainder = signed - quotient * 127773
            value = ctypes.c_int32(remainder * 16807 - quotient * 2836).value
            return ctypes.c_uint32(value if value >= 0 else value + 2147483647).value
        keys = {0, 1, 127772, 127773, 127774, 0x7FFFFFFE, 0x7FFFFFFF,
                0x80000000, 0x80000001, 0xFFFFFFFE, 0xFFFFFFFF}
        keys.update((index * 2654435761) & 0xFFFFFFFF for index in range(257))
        for key in sorted(keys):
            with self.subTest(key=key):
                self.assertEqual(reference(key), native.native_hash(key))
                value = location()
                raw_key = key ^ 0xFFFFFFFF
                total = ctypes.c_uint32(reference(key) + 0x7A6F656E).value
                low = ctypes.c_uint32(reference(total) + total).value
                expected = f"z{raw_key:08X}{low:08X}"
                value["observation"]["zone"].update(
                    rawZoneKey=raw_key, status="type-0073-candidate",
                    childStatus="type-1e17-raw-candidate", childKey=key, zoneIdCandidate=expected)
                self.assertEqual(expected, self.check(value, "location-context")["zoneIdCandidate"])

    def test_all_unavailable_zone_branches_remain_null(self):
        branches = [(status, None) for status in
                    ("null-provider", "null-registry", "cache-miss", "null-holder", "null-record")]
        branches += [("unqualified-cache-record", child) for child in
                     ("null", "type-1e17-raw-candidate", "unverified-type")]
        branches += [("type-0073-candidate", "unverified-type")]
        for status, child in branches:
            value = location()
            zone = value["observation"]["zone"]
            zone.update(status=status, childStatus=child,
                        childKey=9 if child == "type-1e17-raw-candidate" else None)
            with self.subTest(status=status, child=child):
                self.assertIsNone(self.check(value, "location-context")["zoneIdCandidate"])
                zone["zoneIdCandidate"] = "z00000007A1DBBCFC"
                with self.assertRaises(ValueError): self.check(value, "location-context")

    def test_zone_unsigned_fields_and_candidate_spelling_are_strict(self):
        for field in ("rawZoneKey", "childKey"):
            for bad in (True, False, -1, 2**32, 7.0, "7", None, [], {}):
                value = location()
                value["observation"]["zone"].update(
                    status="type-0073-candidate", childStatus="type-1e17-raw-candidate",
                    childKey=0, zoneIdCandidate="z00000007A1DBBCFC")
                value["observation"]["zone"][field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    self.check(value, "location-context")
        for bad in ("z00000007a1dbbcfc", "Z00000007A1DBBCFC", "z00000008A1DBBCFC",
                    "z00000007A1DBBCFD", 7, True, [], {}):
            value = location()
            value["observation"]["zone"].update(
                status="type-0073-candidate", childStatus="null", zoneIdCandidate=bad)
            with self.subTest(candidate=bad), self.assertRaises(ValueError):
                self.check(value, "location-context")

    def test_guard_matrix_excludes_unknown_and_contradictory_states(self):
        for target in (False, True):
            for guard in ("", "getter-candidate", "candidate", None, True, [], {},
                          "fallback-key-candidate", "raw-getter-zero-candidate",
                          "override-unavailable", "guard-unreadable-or-invalid"):
                value = paired(target)
                value["observation"].update(beforeGuardStatus=guard, afterGuardStatus=guard)
                allowed = (guard == "fallback-key-candidate" if target else
                           guard in ("raw-getter-zero-candidate", "override-unavailable", "guard-unreadable-or-invalid"))
                with self.subTest(target=target, guard=guard):
                    if allowed: self.check(value, "paired-position")
                    else:
                        with self.assertRaises(ValueError): self.check(value, "paired-position")

    def test_timestamp_tick_precision_and_utc_only_contract(self):
        self.assertEqual(1, native.stamp("2026-11-07T00:00:00.0000001Z") - native.stamp(A))
        self.assertEqual(native.stamp("2026-11-07T00:00:00.1Z"),
                         native.stamp("2026-11-07T00:00:00.1000000+00:00"))
        for bad in ("2026-11-07T00:00:00.00000001Z", "2026-11-07T00:00:00+01:00",
                    "2026-11-07T00:00:00", "2026-02-30T00:00:00Z"):
            with self.subTest(stamp=bad), self.assertRaises(ValueError): native.stamp(bad)

    def test_missing_or_promoted_contract_is_rejected(self):
        for mode, source in (("location-context", location()), ("paired-position", paired())):
            for bad in (None, {}, [], {**source, "schemaVersion": True}, {**source, "status": "qualified"}):
                with self.assertRaises(ValueError): self.check(bad, mode)
            source["observation"]["qualification"] = "qualified"
            with self.assertRaises(ValueError): self.check(source, mode)


class StagedGuest(FakeGuest):
    """Exercise actual staged_script; never emulate an over-limit encoded launch."""
    def __init__(self, *, launch_error=None, capture_copy_error=None, **kwargs):
        super().__init__(**kwargs)
        self.launch_error = launch_error
        self.capture_copy_error = capture_copy_error
        self.staged = {}
        self.script_copy_calls = 0
        self.run_calls = []
        self.direct_powershell_calls = 0

    def powershell(self, script, *, timeout=60):
        self.direct_powershell_calls += 1
        if len(base64.b64encode(script.encode("utf-16-le"))) > MAX_ENCODED_POWERSHELL_CHARS:
            raise native.SessionError("guest-powershell-script-too-large")
        raise AssertionError("Location/pair scripts must use staged -File execution")

    def run(self, action, *args, **kwargs):
        self.run_calls.append((action, args, kwargs))
        if action == "copyFileFromHostToGuest" and Path(args[0]).suffix == ".ps1":
            if Path(args[0]).name == "capture.ps1" and self.capture_copy_error is not None:
                raise self.capture_copy_error
            self.staged[args[1]] = Path(args[0]).read_text(encoding="utf-8-sig")
            self.script_copy_calls += 1
            return ""
        if action == "runProgramInGuest":
            if "-EncodedCommand" in args or "-File" not in args:
                raise AssertionError("Unexpected guest launch")
            script = self.staged[args[args.index("-File") + 1]]
            self.shell_scripts.append(script)
            if "& $exe sample-current-" in script and self.launch_error is not None:
                raise self.launch_error
            return ""
        return super().run(action, *args, **kwargs)


class WrapperTests(unittest.TestCase):
    def run_fake(self, mode, *, installed=True, result=None, pin_sha=True, source_changed=False,
                 reader_changed=False, launch_error=None, capture_copy_error=None, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        reader = folder / "RiftReader2.Live.exe"
        reader.write_bytes(b"offline-fake-reader")
        guest = StagedGuest(installed=installed, launch_error=launch_error,
                            capture_copy_error=capture_copy_error,
                            result=(location() if mode == "location-context" else paired()) if result is None else result)
        lab = FakeLab(guest)
        self.last_guest, self.last_folder = guest, folder
        source_calls = 0
        reader_calls = 0
        def digest(path):
            nonlocal source_calls, reader_calls
            if Path(path) == reader:
                reader_calls += 1
                return native.READER_SHA if pin_sha and (not reader_changed or reader_calls == 1) else "0"*64
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
            self.assertEqual(2, summary["schemaVersion"])
            self.assertGreater(TICKS, 2**53)
            self.assertEqual(str(TICKS), summary["gameProcessStartUtcTicks"])
            envelope = json.loads((Path(summary["sourceReport"]).parent / "summary.json").read_text())
            self.assertEqual(str(TICKS), envelope["gameProcessStartUtcTicks"])
            self.assertIs(type(envelope["gameProcessStartUtcTicks"]), str)
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

    def test_guest_binary_is_held_open_and_reparse_checked_through_command(self):
        _, guest = self.run_fake("paired-position")
        launch = guest.shell_scripts[-1]
        self.assertIn("ReparsePoint", launch)
        self.assertIn("[IO.FileShare]::Read", launch)
        self.assertIn("ComputeHash($readerGuard)", launch)
        self.assertLess(launch.index("ComputeHash($readerGuard)"), launch.index("& $exe sample-current-"))
        self.assertGreater(launch.rindex("finally{$readerGuard.Dispose()}"), launch.index("& $exe sample-current-"))

    def test_launch_timeout_retains_uncertainty_without_retry_or_summary(self):
        with self.assertRaisesRegex(RuntimeError, "guest-execution-uncertain:no-drain-proof:no-retry"):
            self.run_fake("location-context", launch_error=native.SessionError("guest-command-timeout:runProgramInGuest"))
        self.assertEqual(2, len(self.last_guest.shell_scripts))
        receipts = list(self.last_folder.rglob("execution-uncertain.json"))
        self.assertEqual(1, len(receipts))
        receipt = json.loads(receipts[0].read_text())
        self.assertEqual("unverified", receipt["guestDrainStatus"])
        self.assertEqual(2, receipt["schemaVersion"])
        self.assertEqual(str(TICKS), receipt["gameProcessStartUtcTicks"])
        self.assertIs(type(receipt["gameProcessStartUtcTicks"]), str)
        self.assertFalse(receipt["automaticRetry"])
        self.assertFalse(receipt["cooperativeExclusionReleaseAllowed"])
        self.assertIsNone(receipt["guestProcessId"])
        self.assertFalse(list(self.last_folder.rglob("summary.json")))
        self.assertFalse(list(self.last_folder.rglob("samples.json")))

    def test_staged_launch_does_not_hit_actual_encoded_command_limit(self):
        for mode in ("location-context", "paired-position"):
            summary, guest = self.run_fake(mode)
            with self.subTest(mode=mode):
                self.assertEqual(0, guest.direct_powershell_calls)
                self.assertEqual(2, guest.script_copy_calls)
                self.assertEqual(2, len([x for x in guest.run_calls if x[0] == "runProgramInGuest"]))
                launch = guest.shell_scripts[-1]
                self.assertGreater(len(base64.b64encode(launch.encode("utf-16-le"))),
                                   MAX_ENCODED_POWERSHELL_CHARS)
                self.assertEqual(launch, (Path(summary["sourceReport"]).parent / "capture.ps1").read_text(encoding="utf-8-sig"))

    def test_guard_exact_helper_and_scope_wraps_report_checks(self):
        with patch.object(native, "guest_reader_check", wraps=native.guest_reader_check) as guard:
            _, guest = self.run_fake("location-context")
        guard.assert_called_once()
        self.assertEqual(native.READER_SHA, guard.call_args.args[1])
        self.assertEqual({"hold_open": True}, guard.call_args.kwargs)
        launch = guest.shell_scripts[-1]
        self.assertLess(launch.index("ReparsePoint"), launch.index("$readerGuard=[IO.File]::Open"))
        self.assertLess(launch.index("ComputeHash($readerGuard)"), launch.index("& $exe sample-current-"))
        self.assertLess(launch.index("native-report-missing"), launch.rindex("finally{$readerGuard.Dispose()}"))
        self.assertNotIn("[IO.FileShare]::ReadWrite", launch)
        self.assertNotIn("[IO.FileShare]::Delete", launch)

    def test_timeout_receipt_write_failure_still_denies_release_and_retry(self):
        original_open = Path.open
        def denied(path, *args, **kwargs):
            if path.name == "execution-uncertain.json":
                raise PermissionError("test receipt denied")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", denied), self.assertRaisesRegex(
                RuntimeError, "no-drain-proof:no-retry:receipt-unavailable; retain exclusion"):
            self.run_fake("paired-position", launch_error=native.SessionError("guest-command-timeout:runProgramInGuest"))
        self.assertEqual(2, len(self.last_guest.shell_scripts))
        self.assertFalse(list(self.last_folder.rglob("summary.json")))
        self.assertFalse(list(self.last_folder.rglob("samples.json")))

    def test_staging_timeout_does_not_retry_or_claim_a_running_child(self):
        with self.assertRaisesRegex(native.SessionError, "guest-command-timeout:copyFileFromHostToGuest"):
            self.run_fake("paired-position", capture_copy_error=native.SessionError("guest-command-timeout:copyFileFromHostToGuest"))
        self.assertEqual(1, len(self.last_guest.shell_scripts))
        self.assertFalse(list(self.last_folder.rglob("execution-uncertain.json")))
        self.assertFalse(list(self.last_folder.rglob("summary.json")))

    def test_reader_changed_after_capture_blocks_success(self):
        with self.assertRaisesRegex(ValueError, "source-changed"):
            self.run_fake("location-context", reader_changed=True)
        self.assertFalse(list(self.last_folder.rglob("summary.json")))
        self.assertEqual(2, len(self.last_guest.shell_scripts))

    def test_other_guest_failure_does_not_fabricate_timeout_receipt(self):
        with self.assertRaisesRegex(native.SessionError, "guest-command-failed"):
            self.run_fake("paired-position", launch_error=native.SessionError("guest-command-failed:runProgramInGuest"))
        self.assertFalse(list(self.last_folder.rglob("execution-uncertain.json")))
        self.assertEqual(2, len(self.last_guest.shell_scripts))

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
