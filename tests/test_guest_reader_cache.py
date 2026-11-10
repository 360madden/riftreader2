"""Offline and local-PowerShell tests for the optional verified guest reader cache."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import launch_live_reader as launcher


class GuestReaderCacheTests(unittest.TestCase):
    def test_cache_path_is_exact_hash_and_lab_scoped(self):
        a = launcher.guest_reader_cache_path("lab1", "A" * 64)
        b = launcher.guest_reader_cache_path("lab2", "A" * 64)
        self.assertNotEqual(a, b)
        self.assertIn("ReaderCache", a)
        self.assertIn("A" * 64, a)
        for lab, digest in (("lab3", "A" * 64), ("lab1", "A" * 63),
                            ("lab1", "a" * 64), ("lab2", "../escape")):
            with self.subTest(lab=lab, digest=digest), self.assertRaisesRegex(
                    RuntimeError, "invalid-reader-cache-identity"):
                launcher.guest_reader_cache_path(lab, digest)

    def test_cache_hit_uses_guest_copy_without_host_transfer(self):
        session = mock.Mock()
        cache = launcher.guest_reader_cache_path("lab2", "A" * 64)
        mode = launcher.stage_reader(
            session, Path("reader.exe"), r"C:\run\RiftReader2.Live.exe", "A" * 64,
            cache_path=cache, cache_hit=True)
        self.assertEqual(mode, "verified-guest-cache")
        session.run.assert_not_called()
        session.powershell.assert_called_once()
        script = session.powershell.call_args.args[0]
        self.assertIn("Get-FileHash", script)
        self.assertIn("reader-cache-hash-drift", script)
        self.assertIn("guest-reader-copy-hash-mismatch", script)

    def test_cache_miss_populates_only_after_host_copy(self):
        session = mock.Mock()
        cache = launcher.guest_reader_cache_path("lab1", "B" * 64)
        mode = launcher.stage_reader(
            session, Path("reader.exe"), r"C:\run\RiftReader2.Live.exe", "B" * 64,
            cache_path=cache, cache_hit=False, run_id="lab1-" + "a" * 32)
        self.assertEqual(mode, "host-transfer-cache-populated")
        session.run.assert_called_once_with(
            "copyFileFromHostToGuest", "reader.exe", r"C:\run\RiftReader2.Live.exe",
            timeout=300)
        script = session.powershell.call_args.args[0]
        self.assertIn("reader-cache-staging-hash-mismatch", script)
        self.assertIn("Move-Item", script)
        self.assertIn("reader-cache-publish-hash-mismatch", script)

    def test_default_transfer_unchanged_and_invalid_cache_rejected_early(self):
        session = mock.Mock()
        self.assertEqual(launcher.stage_reader(
            session, Path("reader.exe"), "guest.exe", "A" * 64), "host-transfer")
        session.run.assert_called_once()
        session.powershell.assert_not_called()
        for kwargs in ({"cache_hit": True}, {"cache_hit": "true"},
                       {"cache_path": "guest-cache", "run_id": "invalid"}):
            with self.subTest(kwargs=kwargs):
                session.reset_mock()
                with self.assertRaises(RuntimeError):
                    launcher.stage_reader(
                        session, Path("reader.exe"), "guest.exe", "A" * 64, **kwargs)
                session.run.assert_not_called()
                session.powershell.assert_not_called()

    def test_cache_probe_revalidates_hash_and_type(self):
        script = launcher.guest_reader_cache_probe(
            r"C:\cache\RiftReader2.Live.exe", "A" * 64)
        self.assertIn("Get-FileHash", script)
        self.assertIn("reader-cache-hash-mismatch", script)
        self.assertIn("$cacheHit=$true", script)
        self.assertIn("Test-Path -LiteralPath $cache -PathType Leaf", script)

    def test_opt_in_flag_defaults_off(self):
        basic = ["--lab", "lab2", "--expected-game-pid", "1",
                 "--expected-game-start-ticks", "2",
                 "--expected-game-sha256", "A" * 64,
                 "--reader", r"C:\reader.exe", "--reader-sha256", "B" * 64,
                 "--output", r"C:\out"]
        self.assertFalse(launcher.parser().parse_args(basic).reuse_guest_reader)
        self.assertTrue(launcher.parser().parse_args(
            basic + ["--reuse-guest-reader"]).reuse_guest_reader)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
    def test_real_powershell_probe_detects_miss_hit_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "cache.exe"
            digest = launcher.sha(Path(__file__))
            script = launcher.guest_reader_cache_probe(str(cache), digest)
            def check():
                return subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "$ErrorActionPreference='Stop';" + script + ";Write-Output $cacheHit"],
                    capture_output=True, text=True, timeout=25)
            miss = check()
            self.assertEqual(miss.returncode, 0, miss.stderr)
            self.assertEqual(miss.stdout.strip(), "False")
            cache.write_bytes(Path(__file__).read_bytes())
            hit = check()
            self.assertEqual(hit.returncode, 0, hit.stderr)
            self.assertEqual(hit.stdout.strip(), "True")
            cache.write_bytes(b"corrupt")
            corrupt = check()
            self.assertNotEqual(corrupt.returncode, 0)
            self.assertIn("reader-cache-hash-mismatch", corrupt.stderr)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
    def test_real_powershell_publish_copy_and_corruption_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reader.exe"
            source.write_bytes(b"verified-reader-binary-for-test")
            digest = launcher.sha(source)
            cache = root / "cache" / digest / "RiftReader2.Live.exe"
            destination = root / "run" / "RiftReader2.Live.exe"
            destination.parent.mkdir()
            scripts = (
                launcher.guest_reader_cache_publish(
                    str(source), str(cache), digest, "lab2-" + "b" * 32),
                launcher.guest_reader_cache_copy(
                    str(cache), str(destination), digest),
            )
            for script in scripts:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "$ErrorActionPreference='Stop';" + script],
                    capture_output=True, text=True, timeout=25)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(cache.read_bytes(), source.read_bytes())
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            cache.write_bytes(b"corrupted")
            refused = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "$ErrorActionPreference='Stop';" + scripts[1]],
                capture_output=True, text=True, timeout=25)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("reader-cache-hash-drift", refused.stderr)
            self.assertEqual(destination.read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
