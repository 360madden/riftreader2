from __future__ import annotations

import ctypes
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "vmware_guest_session.py"
SPEC = importlib.util.spec_from_file_location("vmware_guest_session", SCRIPT)
session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(session)


def prompt(user="guest", password="guest-secret"):
    return ctypes.create_unicode_buffer(user), ctypes.create_unicode_buffer(password)


class GuestSessionTests(unittest.TestCase):
    def make(self, runner, *, identities=None, prompt_result=None, reader=None,
             cached=None, writer=None, cache=False, guest_prompt=None):
        values = iter(identities or ["epoch"] * 20)
        return session.GuestSession(
            Path("C:/VMware/vmrun.exe"), Path("C:/VMs/RIFT-Lab.vmx"),
            lambda: next(values), _runner=runner,
            _credential_reader=reader or (lambda target: "vm-secret"),
            _guest_credential_reader=lambda _target: cached,
            _guest_credential_writer=writer or (lambda *_args: None),
            _guest_prompt=guest_prompt or (lambda: prompt_result or prompt()),
            cache_guest_credentials=cache,
        )

    def test_powershell_uses_allowlisted_fixed_program_and_encoded_script(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((list(argv), kwargs)); return subprocess.CompletedProcess(argv, 0, "ok", "")
        with self.make(runner) as guest:
            self.assertEqual(guest.powershell("Write-Output 'hello'"), "ok")
        argv, options = calls[0]
        self.assertEqual(argv[9:13], ["runProgramInGuest", "C:\\VMs\\RIFT-Lab.vmx", session.POWERSHELL, "-NoProfile"])
        self.assertIn("-EncodedCommand", argv)
        self.assertNotIn("hello", " ".join(argv))
        self.assertEqual(options["timeout"], 150)

    def test_large_powershell_script_fails_closed_before_vmrun(self):
        calls = []
        def runner(argv, **_kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with self.make(runner) as guest:
            with self.assertRaisesRegex(session.SessionError, "guest-powershell-script-too-large"):
                guest.powershell("Write-Output x\n" * 500)
        self.assertEqual([], calls)

    def test_secrets_are_not_in_sanitized_failure_or_retained_after_close(self):
        def runner(_argv, **_kwargs):
            return subprocess.CompletedProcess([], 9, "process list secret", "password secret")
        guest = self.make(runner)
        with self.assertRaises(session.SessionError) as caught:
            with guest:
                guest.run("listProcessesInGuest")
        message = str(caught.exception)
        self.assertNotIn("vm-secret", message)
        self.assertNotIn("guest-secret", message)
        self.assertNotIn("process list", message)
        self.assertIsNone(guest._vm_secret)
        self.assertIsNone(guest._password)

    def test_guest_password_buffer_is_zeroed_on_close(self):
        user, password = prompt()
        guest = self.make(
            lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
            prompt_result=(user, password),
        )
        with guest:
            self.assertEqual(password.value, "guest-secret")
        self.assertEqual(password.value, "")

    def test_timeout_does_not_chain_exception_containing_secret_argv(self):
        def runner(argv, **_kwargs):
            raise subprocess.TimeoutExpired(argv, 1)
        with self.make(runner) as guest:
            with self.assertRaisesRegex(session.SessionError, "guest-command-timeout") as caught:
                guest.run("listProcessesInGuest")
        self.assertIsNone(caught.exception.__cause__)

    def test_changed_identity_blocks_command_after_runner(self):
        calls = []
        def runner(argv, **_kwargs):
            calls.append(argv); return subprocess.CompletedProcess(argv, 0, "output", "")
        guest = self.make(runner, identities=["epoch-a", "epoch-a", "epoch-a", "epoch-b"])
        with guest:
            with self.assertRaisesRegex(session.SessionError, "vm-identity-changed"):
                guest.run("listProcessesInGuest")
        self.assertEqual(len(calls), 1)

    def test_prompt_cancellation_closes_partial_session(self):
        guest = session.GuestSession(
            Path("vmrun.exe"), Path("lab.vmx"), lambda: "epoch",
            _credential_reader=lambda _target: "vm-secret",
            _guest_prompt=lambda: (_ for _ in ()).throw(session.SessionError("guest-credential-prompt-cancelled")),
            _runner=lambda *_a, **_k: self.fail("runner called"),
        )
        with self.assertRaisesRegex(session.SessionError, "prompt-cancelled"):
            guest.__enter__()
        self.assertIsNone(guest._vm_secret)

    def test_prompt_flags_explicitly_forbid_persistence(self):
        self.assertEqual(session.CREDUI_FLAGS_DO_NOT_PERSIST, 0x00002)
        flags = (session.CREDUI_FLAGS_GENERIC_CREDENTIALS |
                 session.CREDUI_FLAGS_ALWAYS_SHOW_UI |
                 session.CREDUI_FLAGS_DO_NOT_PERSIST)
        self.assertTrue(flags & session.CREDUI_FLAGS_DO_NOT_PERSIST)

    def test_default_target_preserves_supplied_vmx_spelling(self):
        observed = []
        guest = self.make(lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", ""),
                          reader=lambda target: observed.append(target) or "secret")
        with guest:
            pass
        self.assertEqual(observed, ["VMware Encrypted VM: C:\\VMs\\RIFT-Lab.vmx"])

    def test_command_allowlist_rejects_unknown_command_without_runner(self):
        called = []
        with self.make(lambda *a, **k: called.append(a)) as guest:
            with self.assertRaisesRegex(session.SessionError, "not-allowed"):
                guest.run("deleteFileInGuest", "C:\\data")
        self.assertEqual(called, [])

    def test_copy_refuses_overwrite_and_removes_partial_failed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); existing = root / "exists.zip"; existing.write_bytes(b"keep")
            calls = []
            def runner(argv, **_kwargs):
                calls.append(argv)
                Path(argv[-1]).write_bytes(b"partial")
                return subprocess.CompletedProcess(argv, 8, "", "sensitive")
            with self.make(runner) as guest:
                with self.assertRaisesRegex(session.SessionError, "invalid-copy-destination"):
                    guest.copy_from_guest("C:\\one.zip", existing)
                output = root / "new.zip"
                with self.assertRaisesRegex(session.SessionError, "guest-command-failed"):
                    guest.copy_from_guest("C:\\one.zip", output)
                self.assertFalse(output.exists())
            self.assertEqual(existing.read_bytes(), b"keep")
            self.assertEqual(len(calls), 1)

    def test_copy_race_preserves_other_writers_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.zip"
            def runner(argv, **_kwargs):
                Path(argv[-1]).write_bytes(b"guest bytes")
                output.write_bytes(b"other writer")
                return subprocess.CompletedProcess(argv, 0, "", "")
            with self.make(runner) as guest:
                with self.assertRaisesRegex(session.SessionError, "destination-raced"):
                    guest.copy_from_guest("C:\\result.zip", output)
            self.assertEqual(output.read_bytes(), b"other writer")
            self.assertEqual(list(output.parent.glob("*.vmrun-part")), [])

    def test_verified_prompted_login_is_cached_only_after_validation(self):
        calls = []
        writes = []
        def runner(argv, **_kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "processes", "")
        guest = self.make(runner, cache=True, writer=lambda *args: writes.append(args))
        with guest:
            self.assertEqual(len(writes), 1)
            self.assertEqual(guest.credential_source, "prompt")
            self.assertTrue(guest.cache_written)
        self.assertIsNone(guest.credential_source)
        self.assertFalse(guest.cache_written)
        self.assertEqual(calls[0][9], "listProcessesInGuest")
        self.assertEqual(writes[0][1:], ("guest", "guest-secret"))
        self.assertTrue(writes[0][0].startswith("RiftReader2 Guest Windows: "))

    def test_failed_validation_does_not_cache_prompted_login(self):
        writes = []
        guest = self.make(
            lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 1, "", "secret"),
            cache=True, writer=lambda *args: writes.append(args),
        )
        with self.assertRaisesRegex(session.SessionError, "credential-validation-failed"):
            guest.__enter__()
        self.assertEqual(writes, [])
        self.assertIsNone(guest._password)

    def test_cancelled_prompt_does_not_cache(self):
        writes = []
        guest = self.make(
            lambda *_a, **_k: self.fail("runner called"), cache=True,
            writer=lambda *args: writes.append(args),
            guest_prompt=lambda: (_ for _ in ()).throw(
                session.SessionError("guest-credential-prompt-cancelled")),
        )
        with self.assertRaisesRegex(session.SessionError, "prompt-cancelled"):
            guest.__enter__()
        self.assertEqual(writes, [])

    def test_cached_login_is_reused_without_prompt_even_without_write_opt_in(self):
        cached_user, cached_password = prompt("cached-user", "cached-password")
        prompted = []
        writes = []
        guest = self.make(
            lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, "processes", ""),
            cached=(cached_user, cached_password), cache=False,
            writer=lambda *args: writes.append(args),
            guest_prompt=lambda: prompted.append(True) or prompt(),
        )
        with guest:
            self.assertEqual(guest._username.value, "cached-user")
            self.assertEqual(guest.credential_source, "cache")
            self.assertFalse(guest.cache_written)
        self.assertEqual(prompted, [])
        self.assertEqual(writes, [])
        self.assertEqual(cached_user.value, "")
        self.assertEqual(cached_password.value, "")

    def test_stale_cached_login_fails_without_prompt_or_overwrite(self):
        cached = prompt("old-user", "old-password")
        prompted = []
        writes = []
        guest = self.make(
            lambda argv, **_kwargs: subprocess.CompletedProcess(
                argv, 1, "", "Invalid user name or password: secret"),
            cached=cached, cache=True, writer=lambda *args: writes.append(args),
            guest_prompt=lambda: prompted.append(True) or prompt(),
        )
        with self.assertRaisesRegex(session.SessionError, "cached-guest-credential-invalid"):
            guest.__enter__()
        self.assertEqual(prompted, [])
        self.assertEqual(writes, [])
        self.assertEqual(cached[1].value, "")

    def test_failure_reports_only_safe_exit_and_category(self):
        def runner(argv, **_kwargs):
            return subprocess.CompletedProcess(
                argv, 17, "sensitive-user", "VMware Tools are not running; password=secret")
        with self.make(runner) as guest:
            with self.assertRaises(session.SessionError) as caught:
                guest.run("listProcessesInGuest")
        message = str(caught.exception)
        self.assertEqual(
            message,
            "guest-command-failed:listProcessesInGuest:exit=17:category=guest-tools-unavailable",
        )
        self.assertNotIn("sensitive-user", message)
        self.assertNotIn("secret", message)

    @unittest.skipUnless(session.os.name == "nt", "Windows Credential Manager contract")
    def test_credential_writer_uses_local_machine_persist_and_wipes_blob_buffer(self):
        observed = {}
        wiped = []

        class FakeWrite:
            argtypes = None
            restype = None
            def __call__(self, pointer, flags):
                credential = pointer._obj
                observed.update(
                    target=credential.TargetName,
                    username=credential.UserName,
                    persist=credential.Persist,
                    flags=flags,
                    blob=ctypes.string_at(credential.Blob, credential.BlobSize),
                )
                return True

        class FakeApi:
            CredWriteW = FakeWrite()

        original_wipe = session._wipe
        def recording_wipe(buffer):
            original_wipe(buffer)
            wiped.append(buffer)

        with mock.patch.object(session.ctypes, "WinDLL", return_value=FakeApi()), \
             mock.patch.object(session, "_wipe", side_effect=recording_wipe):
            session._save_guest_credentials("target", "guest", "p@ss")

        self.assertEqual(observed["target"], "target")
        self.assertEqual(observed["username"], "guest")
        self.assertEqual(observed["persist"], session.CRED_PERSIST_LOCAL_MACHINE)
        self.assertEqual(observed["flags"], 0)
        self.assertEqual(observed["blob"].decode("utf-16-le"), "p@ss")
        self.assertEqual(len(wiped), 1)
        self.assertEqual(wiped[0].value, "")


if __name__ == "__main__":
    unittest.main()
