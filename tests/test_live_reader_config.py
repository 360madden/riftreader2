from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import launch_live_reader
from scripts.live_reader_config import (
    DEFAULT_SCAN_BYTES,
    MAX_SCAN_BYTES,
    build_live_configuration,
    load_scan_limits,
    resolve_max_scan_bytes,
)


class LiveReaderConfigTests(unittest.TestCase):
    def test_tracked_profile_keeps_default_and_raises_only_lab1(self):
        self.assertEqual(6 * 1024**3, resolve_max_scan_bytes("lab1"))
        self.assertEqual(DEFAULT_SCAN_BYTES, resolve_max_scan_bytes("lab2"))

    def test_vm_paths_and_cached_guest_fallback_are_scoped_per_lab(self):
        self.assertEqual(
            str(launch_live_reader.LABS["lab1"]["vmx"]),
            r"C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx",
        )
        self.assertEqual(
            str(launch_live_reader.LABS["lab2"]["vmx"]),
            r"C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx",
        )
        self.assertEqual(
            launch_live_reader.legacy_guest_target("lab1"),
            "RiftReader2 Guest Windows: "
            + str(launch_live_reader.LABS["lab1"]["legacyGuestVmx"].resolve(strict=False)),
        )
        self.assertIsNone(launch_live_reader.legacy_guest_target("lab2"))
        self.assertNotEqual(
            launch_live_reader.legacy_guest_target("lab1"),
            "RiftReader2 Guest Windows: "
            + str(launch_live_reader.LABS["lab2"]["vmx"].resolve(strict=False)),
        )

    def test_explicit_override_wins_and_is_bounded(self):
        self.assertEqual(5 * 1024**3, resolve_max_scan_bytes("lab1", override=5 * 1024**3))
        for value in (0, MAX_SCAN_BYTES + 1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_max_scan_bytes("lab1", override=value)

    def test_profile_shape_and_values_fail_closed(self):
        cases = (
            {"schemaVersion": 2, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {}},
            {"schemaVersion": 1, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {"lab3": 1}},
            {"schemaVersion": 1, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {"lab1": 0}},
            {"schemaVersion": 1, "defaultMaxScanBytes": DEFAULT_SCAN_BYTES, "labs": {}, "extra": 1},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "limits.json"
            for value in cases:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_scan_limits(path)

    def test_builder_places_resolved_limit_in_reader_configuration(self):
        value = build_live_configuration(
            endpoint="http://192.168.56.1:49813/observe",
            token="x" * 32,
            output_path=r"C:\reader\latest.json",
            duration_seconds=900,
            poll_interval_milliseconds=250,
            max_scan_bytes=6 * 1024**3,
        )
        self.assertEqual(6 * 1024**3, value["maxScanBytes"])
        self.assertEqual(10, value["maxScanSeconds"])
        self.assertEqual(4 * 1024**3, DEFAULT_SCAN_BYTES)

    def test_tracked_launcher_writes_resolved_lab1_limit(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}
        ):
            limit = resolve_max_scan_bytes("lab1")
            staging, path, _ = launch_live_reader.private_config(
                "unit-launcher",
                "http://192.168.56.1:49813/observe",
                "x" * 32,
                r"C:\reader\latest.json",
                900,
                250,
                limit,
            )
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(6 * 1024**3, value["maxScanBytes"])
            finally:
                launch_live_reader.clean_private(staging)

    def test_cleanup_accepts_virtualized_equivalent_parent(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}
        ):
            base = Path(directory) / "RiftReader2" / "HybridStaging"
            staging = base / "run"
            staging.mkdir(parents=True)
            virtual = Path(directory) / "virtualized" / "run"
            original_samefile = launch_live_reader.os.path.samefile
            def samefile(left, right):
                if Path(left) == virtual.parent and Path(right) == base:
                    return True
                return original_samefile(left, right)
            with mock.patch.object(Path, "resolve", return_value=virtual), \
                 mock.patch.object(launch_live_reader.os.path, "samefile", side_effect=samefile), \
                 mock.patch.object(launch_live_reader.shutil, "rmtree") as remove:
                launch_live_reader.clean_private(staging)
            remove.assert_called_once_with(virtual)

    def test_cleanup_rejects_other_directory_and_unverifiable_identity(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}
        ):
            base = Path(directory) / "RiftReader2" / "HybridStaging"
            base.mkdir(parents=True)
            outside = Path(directory) / "outside"
            outside.mkdir()
            with mock.patch.object(launch_live_reader.shutil, "rmtree") as remove:
                with self.assertRaisesRegex(RuntimeError, "private-staging-cleanup-scope"):
                    launch_live_reader.clean_private(outside)
                with mock.patch.object(launch_live_reader.os.path, "samefile", side_effect=OSError("denied")):
                    with self.assertRaisesRegex(RuntimeError, "private-staging-cleanup-scope"):
                        launch_live_reader.clean_private(outside)
                remove.assert_not_called()

    def test_cleanup_rejects_symlink_and_reparse_point(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ", {"LOCALAPPDATA": directory}
        ):
            base = Path(directory) / "RiftReader2" / "HybridStaging"
            staging = base / "run"
            staging.mkdir(parents=True)
            with mock.patch.object(Path, "lstat") as info, \
                 mock.patch.object(launch_live_reader.shutil, "rmtree") as remove:
                info.return_value.st_file_attributes = 0x400
                with self.assertRaisesRegex(RuntimeError, "private-staging-cleanup-scope"):
                    launch_live_reader.clean_private(staging)
                remove.assert_not_called()
            link = base / "link"
            try:
                link.symlink_to(staging, target_is_directory=True)
            except OSError:
                return  # Windows developer-mode privileges may be unavailable.
            with self.assertRaisesRegex(RuntimeError, "private-staging-cleanup-scope"):
                launch_live_reader.clean_private(link)
            self.assertTrue(staging.is_dir())

class LaunchFailureCleanupTests(unittest.TestCase):
    def test_guest_script_separates_body_without_trailing_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            session = mock.Mock()
            session.copy_from_guest.side_effect = lambda source, target, **kwargs: target.write_text('{}')
            result = launch_live_reader.run_guest_script(
                session, output, "$payload=@{status='ok'}", "lab1-test", "test")
            script = (output / "test.ps1").read_text(encoding="utf-8-sig")
            self.assertIn("$payload=@{status='ok'}\n$payload|ConvertTo-Json", script)
            self.assertEqual(result, {})

    def test_generated_scope_is_strict(self):
        from scripts.guest_staging_cleanup import guest_body
        valid = "lab2-" + "a" * 32
        body = guest_body("lab2", valid)
        self.assertIn(valid, body)
        self.assertIn(r"RIFT-LAB-2\mrkoo", body)
        for lab, run in (("lab3", valid), ("lab1", valid), ("lab2", "../escape"),
                         ("lab2", "lab2-" + "A" * 32)):
            with self.subTest(lab=lab, run=run), self.assertRaises(RuntimeError):
                guest_body(lab, run)

    def test_launch_failures_clean_only_after_config_copy_attempt(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        receipt = {"status": "deleted", "fileExisted": True, "deleted": True,
                   "otherReaderCountBefore": 0, "otherReaderCountAfter": 0,
                   "inputSent": False}
        for failure in ("preflight", "reader-copy", "config-copy", "launch", "cleanup-fails",
                        "host-cleanup-fails", "vm-drift", "post-session", "receipt-pid",
                        "receipt-ticks", "receipt-build", "snapshot-mismatch", "success"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                reader = root / "reader.exe"
                reader.write_bytes(b"reader")
                receiver = root / "receiver.json"
                receiver.write_text("{}")
                staging = root / "private"
                staging.mkdir()
                config = staging / "config.json"
                config.write_text("private")
                args = SimpleNamespace(output=root / "out", reader=reader,
                    reader_sha256=launch_live_reader.sha(reader), receiver_config=receiver,
                    lab="lab1", duration_seconds=900, poll_interval_milliseconds=500,
                    max_scan_bytes=1000, expected_game_pid=1, expected_game_start_ticks=2,
                    expected_game_sha256="A" * 64)
                def patch(name, **kwargs):
                    return stack.enter_context(mock.patch.object(launch_live_reader, name, **kwargs))
                patch("receiver_preflight", return_value=({}, "token", "endpoint"))
                patch("validate_config", return_value=SimpleNamespace(vmrun="vmrun", vmx="vmx"))
                patch("collect_identity", return_value={"vm": 1})
                patch("verify_identity", side_effect=(RuntimeError("original-post-session") if failure == "post-session"
                                                       else RuntimeError("drift") if failure == "vm-drift"
                                                       else None), return_value={"vm": 1})
                patch("private_config", return_value=(staging, config, "hash"))
                session_type = patch("GuestSession")
                session = session_type.return_value.__enter__.return_value
                session.credential_source = "cache"
                def copy_snapshot(source, target, **kwargs):
                    value = {"nonce": "a" * 32, "readerStatus": "running", "target": {
                        "processId": args.expected_game_pid,
                        "processStartUtcTicks": args.expected_game_start_ticks,
                        "readerSessionNonce": "a" * 32,
                        "executableSha256": args.expected_game_sha256},
                        "delivery": {"enabled": True, "endpoint": "endpoint"}}
                    if failure == "snapshot-mismatch":
                        value["target"]["processStartUtcTicks"] += 1
                    target.write_text(json.dumps(value))
                session.copy_from_guest.side_effect = copy_snapshot
                def copy(*args, **kwargs):
                    if failure == "reader-copy" and str(args[1]).endswith("reader.exe"):
                        raise RuntimeError("original-reader-copy")
                    if failure == "config-copy" and str(args[1]).endswith("config.json"):
                        raise RuntimeError("original-config-copy")
                session.run.side_effect = copy
                def guest_script(session, output, body, run_id, label, **kwargs):
                    if label == "preflight":
                        if failure == "preflight":
                            raise RuntimeError("original-preflight")
                        return {"status": "guest-preflight-passed"}
                    if label == "cleanup":
                        if failure == "cleanup-fails":
                            raise RuntimeError("secret-cleanup-error")
                        return receipt
                    if failure in ("success", "post-session", "receipt-pid", "receipt-ticks",
                                   "receipt-build", "snapshot-mismatch"):
                        ready = {"status": "reader-ready", "readerSha256": args.reader_sha256,
                                "nonce": "a" * 32, "readerPid": 5, "readerStartUtcTicks": "6",
                                "expiresAtUtc": "later", "gamePid": args.expected_game_pid,
                                "gameStartUtcTicks": str(args.expected_game_start_ticks),
                                "gameSha256": args.expected_game_sha256}
                        if failure == "receipt-pid":
                            ready["gamePid"] += 1
                        elif failure == "receipt-ticks":
                            ready["gameStartUtcTicks"] = str(args.expected_game_start_ticks + 1)
                        elif failure == "receipt-build":
                            ready["gameSha256"] = "B" * 64
                        return ready
                    raise RuntimeError("original-launch")
                run = patch("run_guest_script", side_effect=guest_script)
                if failure == "host-cleanup-fails":
                    patch("clean_private", side_effect=RuntimeError("original-host-cleanup"))
                else:
                    patch("clean_private")
                if failure == "success":
                    self.assertEqual(launch_live_reader.execute(args)["status"],
                                     "reader-running-postflight-verified")
                else:
                    with self.assertRaisesRegex(RuntimeError, "original-|reader-launch-receipt-mismatch|reader-snapshot-mismatch"):
                        launch_live_reader.execute(args)
                    self.assertFalse((args.output / "summary.json").exists())
                labels = [call.args[4] for call in run.call_args_list]
                if failure in ("preflight", "reader-copy", "success"):
                    self.assertNotIn("cleanup", labels)
                    self.assertFalse((args.output / "guest-cleanup.json").exists())
                else:
                    self.assertEqual(labels.count("cleanup"), 0 if failure in ("vm-drift", "post-session") else 1)
                    outcome = json.loads((args.output / "guest-cleanup.json").read_text())
                    self.assertEqual(outcome["status"], "unverified" if failure in ("cleanup-fails", "vm-drift", "post-session") else "deleted")
                    if failure == "post-session":
                        self.assertEqual(outcome["reason"], "session-closed")
                    self.assertNotIn("secret", json.dumps(outcome))
                if failure == "host-cleanup-fails":
                    self.assertEqual(json.loads((args.output / "host-cleanup.json").read_text()),
                                     {"status": "unverified"})


if __name__ == "__main__":
    unittest.main()
