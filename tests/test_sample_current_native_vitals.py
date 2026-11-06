"""Offline validation of explicit-reader, no-input vitals host sampling."""
from __future__ import annotations

import copy
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import sample_current_native_vitals as module
from tests.test_sample_current_native_xyz import FakeLab
from scripts.vmware_guest_session import MAX_ENCODED_POWERSHELL_CHARS

PID, TICKS = 11572, 639293038821710082


def report():
    field = {"status": "calculated-candidate", "unavailableReason": None,
             "current": 100, "maximum": 100, "inputs": {"baseRaw": 100}}
    mana = copy.deepcopy(field)
    mana["inputs"]["verifiedTypeCode"] = "0x072A"
    energy = {"status": "unavailable", "unavailableReason": "not-energy-kind-four",
              "current": None, "maximum": None, "inputs": None}
    return {"schemaVersion": 1, "contractVersion": "native-current-vitals-candidate-sample/2",
            "status": "complete", "sourceBuildSha256": module.GAME_SHA,
            "source": "native-process-memory", "qualification": module.QUALIFICATION,
            "observation": {"source": "native-process-memory", "qualification": module.QUALIFICATION,
                "identity": {"processId": PID, "processStartUtcTicks": TICKS, "executableSha256": module.GAME_SHA},
                "unitKey": 123, "startedAtUtc": "2026-11-06T12:00:00Z", "completedAtUtc": "2026-11-06T12:00:00.050Z",
                "health": copy.deepcopy(field), "mana": mana, "energy": energy}}


class FakeGuest:
    def __init__(self, result=None, corrupt_hash=False, raw_report=None):
        self.result = result or report()
        self.raw_report = raw_report if raw_report is not None else json.dumps(self.result).encode()
        self.corrupt_hash = corrupt_hash
        self.scripts = []
        self.copies = []
        self.staged = {}
        self.launch_arguments = []

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def powershell(self, script, **_): raise AssertionError("Encoded PowerShell must not be used")
    def run(self, action, *args, **_):
        if action == "copyFileFromHostToGuest":
            self.copies.append(args)
            if Path(args[0]).suffix == ".ps1":
                self.staged[args[1]] = Path(args[0]).read_text(encoding="utf-8-sig")
        elif action == "runProgramInGuest":
            self.launch_arguments.append(args)
            self.scripts.append(self.staged[args[-1]])
        else: raise AssertionError(action)
    def copy_from_guest(self, source, destination, **_):
        if destination.name == "identity.json":
            destination.write_text(json.dumps({"pid": PID, "ticks": TICKS, "sha": module.GAME_SHA, "installed": False}))
        elif destination.name == "samples.json":
            destination.write_bytes(self.raw_report)
        elif destination.name == "samples.sha256":
            value = hashlib.sha256(self.raw_report).hexdigest().upper()
            destination.write_text("0" * 64 if self.corrupt_hash else value)
        else: raise AssertionError(destination)


class VitalsHostTests(unittest.TestCase):
    def validate(self, value): return module.validate_report(value, pid=PID, ticks=TICKS)

    def test_valid_candidate_and_unavailable_energy(self):
        self.assertEqual(50, self.validate(report())["readMilliseconds"])
        value = report()
        self.assertEqual("unavailable", self.validate(value)["energy"]["status"])

    def test_accepts_legacy_v1_without_promoting_missing_mana(self):
        value = report()
        value["contractVersion"] = "native-current-vitals-candidate-sample/1"
        del value["observation"]["mana"]
        validated = self.validate(value)
        self.assertEqual("native-current-vitals-candidate-sample/1", validated["contractVersion"])
        self.assertEqual("unavailable", validated["mana"]["status"])
        self.assertEqual("legacy-contract-v1-without-mana", validated["mana"]["unavailableReason"])

    def test_v2_requires_explicit_mana_field(self):
        value = report()
        del value["observation"]["mana"]
        with self.assertRaisesRegex(ValueError, "field-missing"):
            self.validate(value)

    def test_v2_rejects_simultaneously_calculated_mana_and_energy(self):
        value = report()
        value["observation"]["energy"] = copy.deepcopy(value["observation"]["health"])
        with self.assertRaisesRegex(ValueError, "resource-kind-conflict"):
            self.validate(value)

    def test_v2_requires_exact_mana_type_evidence(self):
        for type_code in (None, "0x072B", 0x072A, True):
            value = report()
            inputs = value["observation"]["mana"]["inputs"]
            if type_code is None:
                del inputs["verifiedTypeCode"]
            else:
                inputs["verifiedTypeCode"] = type_code
            with self.subTest(type_code=type_code), self.assertRaisesRegex(ValueError, "mana-type-evidence"):
                self.validate(value)

    def test_v2_requires_exact_energy_type_evidence(self):
        for type_code in (None, "0x072A", 0x072B, True):
            value = report()
            value["observation"]["mana"] = {"status": "unavailable",
                "unavailableReason": "not-mana-kind-three", "current": None,
                "maximum": None, "inputs": None}
            value["observation"]["energy"] = copy.deepcopy(value["observation"]["health"])
            inputs = value["observation"]["energy"]["inputs"]
            if type_code is None:
                inputs.pop("verifiedTypeCode", None)
            else:
                inputs["verifiedTypeCode"] = type_code
            with self.subTest(type_code=type_code), self.assertRaisesRegex(ValueError, "energy-type-evidence"):
                self.validate(value)

    def test_v2_requires_opposite_resource_to_be_explicitly_inapplicable(self):
        value = report()
        value["observation"]["energy"]["unavailableReason"] = "missing"
        with self.assertRaisesRegex(ValueError, "mana-energy-exclusion"):
            self.validate(value)

        value = report()
        value["observation"]["mana"] = {"status": "unavailable",
            "unavailableReason": "not-mana-kind-three", "current": None,
            "maximum": None, "inputs": None}
        value["observation"]["energy"] = copy.deepcopy(value["observation"]["health"])
        value["observation"]["energy"]["inputs"]["verifiedTypeCode"] = "0x072B"
        self.assertEqual("calculated-candidate", self.validate(value)["energy"]["status"])

    def test_rejects_promoted_status_or_qualification(self):
        for key, value in [("status", "qualified"), ("qualification", "fresh"), ("source", "addon"), ("schemaVersion", True)]:
            r = report(); r[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(r)

    def test_rejects_epoch_and_build_mismatch(self):
        for key, value in [("processId", 1), ("processStartUtcTicks", TICKS + 1), ("executableSha256", "0" * 64)]:
            r = report(); r["observation"]["identity"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "epoch"): self.validate(r)

    def test_rejects_invalid_field_states_and_numbers(self):
        for update in [{"status": "trusted"}, {"current": True}, {"current": 101}, {"maximum": 0},
                       {"inputs": None}, {"unavailableReason": "unexpected"},
                       {"status": "unavailable", "unavailableReason": "missing"}]:
            r = report(); r["observation"]["health"].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError): self.validate(r)

    def test_rejects_invalid_acquisition_time_and_owner(self):
        for key, value in [("unitKey", 0), ("unitKey", True), ("startedAtUtc", "bad"),
                           ("completedAtUtc", "2026-11-06T11:00:00Z"), ("startedAtUtc", "2026-11-06T12:00:00")]:
            r = report(); r["observation"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(r)

    def run_fake(self, root, guest, guest_root=None):
        exe = root / "RiftReader2.Live.exe"; exe.write_bytes(b"fake-published-executable")
        sha = module.digest(exe)
        lab = FakeLab(guest)
        if guest_root is not None:
            lab._configuration = lambda _: (None, None, {"vmrun": "mock"}, {"guestRoot": guest_root})
        with mock.patch.object(module, "EVIDENCE", root / "runs"), mock.patch.object(module, "LabCodex", return_value=lab):
            return module.run("lab2", exe, sha), sha

    def test_stages_unique_hash_pinned_reader_and_verifies_report(self):
        with tempfile.TemporaryDirectory() as folder:
            guest = FakeGuest(); result, sha = self.run_fake(Path(folder), guest)
            self.assertEqual("candidate-only", result["status"])
            self.assertFalse(result["guestReaderReused"])
            self.assertEqual(3, len(guest.copies))
            self.assertIn(sha, guest.copies[1][1])
            self.assertEqual(2, len(guest.launch_arguments))
            for args in guest.launch_arguments:
                self.assertEqual(("-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                                  "-ExecutionPolicy", "Bypass", "-File"), args[1:-1])
                self.assertNotIn("-EncodedCommand", args)
            joined = "\n".join(guest.scripts)
            for expected in ["guest-staging-exists", "guest-reader-exists", "sample-current-vitals", "game-epoch-changed", "Get-FileHash",
                             "guest-identity-size-invalid", "guest-report-size-invalid", str(module.IDENTITY_MAX_BYTES), str(module.REPORT_MAX_BYTES)]:
                self.assertIn(expected, joined)
            self.assertNotIn("sample-current-position", joined)
            self.assertTrue(Path(result["sourceReport"]).with_name("summary.json").is_file())

    def test_long_guest_paths_stage_scripts_above_encoded_command_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            guest = FakeGuest()
            result, _ = self.run_fake(Path(folder), guest,
                guest_root="C:\\Users\\Public\\Documents\\" + "long folder name " * 6)
            self.assertEqual("candidate-only", result["status"])
            self.assertTrue(any(len(base64.b64encode(script.encode("utf-16-le"))) > MAX_ENCODED_POWERSHELL_CHARS
                                for script in guest.scripts))
            self.assertEqual(2, len(guest.launch_arguments))
            self.assertTrue(all("-File" in args for args in guest.launch_arguments))
            self.assertEqual(2, len(guest.staged))

    def test_transfer_hash_mismatch_prevents_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, "report-sha-mismatch"):
                self.run_fake(root, FakeGuest(corrupt_hash=True))
            self.assertEqual([], list(root.rglob("summary.json")))

    def test_repeated_calls_use_new_guest_and_host_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); first, second = FakeGuest(), FakeGuest()
            one, _ = self.run_fake(root, first)
            two, _ = self.run_fake(root, second)
            self.assertNotEqual(one["sourceReport"], two["sourceReport"])
            self.assertNotEqual(first.copies[1][1], second.copies[1][1])

    def test_nonfinite_json_inputs_prevent_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); wrong = report()
            wrong["observation"]["health"]["inputs"]["gameClock"] = float("nan")
            with self.assertRaisesRegex(ValueError, "nonfinite-json"):
                self.run_fake(root, FakeGuest(result=wrong))
            self.assertEqual([], list(root.rglob("summary.json")))

    def test_exponent_overflow_in_nested_json_prevents_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); wrong = report()
            wrong["observation"]["health"]["inputs"]["nested"] = ["EXPONENT"]
            raw = json.dumps(wrong).replace('"EXPONENT"', '1e999').encode()
            with self.assertRaisesRegex(ValueError, "nonfinite-json"):
                self.run_fake(root, FakeGuest(raw_report=raw))
            self.assertEqual([], list(root.rglob("summary.json")))

    def test_direct_validation_rejects_recursive_nonfinite_values(self):
        wrong = report(); wrong["observation"]["health"]["inputs"]["nested"] = [{"value": float("inf")}]
        with self.assertRaisesRegex(ValueError, "nonfinite-json"):
            self.validate(wrong)

    def test_oversized_report_prevents_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, "evidence-size-invalid"):
                self.run_fake(root, FakeGuest(raw_report=b" " * (module.REPORT_MAX_BYTES + 1)))
            self.assertEqual([], list(root.rglob("summary.json")))

    def test_oversized_identity_prevents_reader_launch(self):
        class OversizedIdentityGuest(FakeGuest):
            def copy_from_guest(self, source, destination, **kwargs):
                if destination.name == "identity.json":
                    destination.write_bytes(b" " * (module.IDENTITY_MAX_BYTES + 1))
                else:
                    super().copy_from_guest(source, destination, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            guest = OversizedIdentityGuest()
            with self.assertRaisesRegex(ValueError, "evidence-size-invalid"):
                self.run_fake(Path(folder), guest)
            self.assertEqual(1, len(guest.copies))
            self.assertEqual(1, len(guest.scripts))

    def test_launch_timeout_reports_unverified_guest_process_cleanup(self):
        class TimeoutGuest(FakeGuest):
            def run(self, action, *args, **kwargs):
                super().run(action, *args, **kwargs)
                if action == "runProgramInGuest" and "sample-current-vitals" in self.scripts[-1]:
                    raise module.SessionError("guest-command-timeout:runProgramInGuest")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(module.SessionError, "guest-reader-process-cleanup-unverified"):
                self.run_fake(root, TimeoutGuest())
            self.assertEqual([], list(root.rglob("summary.json")))

    def test_wrong_epoch_prevents_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); wrong = report(); wrong["observation"]["identity"]["processId"] = 1
            with self.assertRaisesRegex(ValueError, "epoch"):
                self.run_fake(root, FakeGuest(result=wrong))
            self.assertEqual([], list(root.rglob("summary.json")))

    def test_bad_reader_hash_rejected_before_lab_access(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(module, "LabCodex") as lab:
            exe = Path(folder) / "RiftReader2.Live.exe"; exe.write_bytes(b"x")
            for sha in ["bad", "0" * 64]:
                with self.assertRaises(ValueError): module.run("lab2", exe, sha)
            lab.assert_not_called()


if __name__ == "__main__": unittest.main()
