import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import scripts.waypoint_diagnostics as diagnostics_module
from scripts.waypoint_diagnostics import Diagnostics, existing_report, existing_status


def _entries(diagnostics: Diagnostics):
    paths = [Path(f"{diagnostics.log_path}.{index}") for index in (2, 1)] + [diagnostics.log_path]
    result = []
    for path in paths:
        if path.exists():
            result.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return result


class WaypointDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_writes_utf8_context_and_rotates(self):
        with mock.patch.object(diagnostics_module, "MAX_BYTES", 350):
            diagnostics = Diagnostics(self.root)
            diagnostics.set_context(
                host="AMD-DESKTOP", appVersion="2.4", sessionId="session", password="nope"
            )
            for index in range(30):
                diagnostics.info("café", index=index, detail="x" * 80)

        self.assertTrue(diagnostics.log_path.exists())
        self.assertTrue(Path(f"{diagnostics.log_path}.1").exists())
        self.assertFalse(Path(f"{diagnostics.log_path}.3").exists())
        entries = _entries(diagnostics)
        self.assertTrue(any(entry["message"] == "café" for entry in entries))
        self.assertTrue(all(entry["threadName"] == "MainThread" for entry in entries))
        self.assertEqual(entries[-1]["context"]["password"], "<redacted>")
        self.assertTrue(diagnostics.status()["available"])

    def test_keeps_only_ten_newest_log_groups(self):
        directory = self.root / "artifacts" / "waypoint-logs"
        directory.mkdir(parents=True)
        for index in range(12):
            path = directory / f"waypoints-old-{index:02d}.log"
            path.write_text("old\n", encoding="utf-8")
            os.utime(path, (index + 1, index + 1))
            Path(f"{path}.1").write_text("backup\n", encoding="utf-8")

        diagnostics = Diagnostics(self.root)
        bases = list(directory.glob("waypoints-*.log"))

        self.assertEqual(len(bases), 10)
        self.assertIn(diagnostics.log_path, bases)
        self.assertFalse((directory / "waypoints-old-00.log").exists())
        self.assertFalse(Path(f"{directory / 'waypoints-old-00.log'}.1").exists())

    def test_retention_protects_active_same_process_sessions_then_cleans_closed(self):
        sessions = [Diagnostics(self.root) for _ in range(12)]
        for index, session in enumerate(sessions):
            os.utime(session.log_path, (index + 1, index + 1))

        trigger = Diagnostics(self.root)
        self.assertTrue(all(session.log_path.exists() for session in sessions))

        closed_oldest = sessions[0]
        closed_oldest.close()
        second_trigger = Diagnostics(self.root)

        self.assertFalse(closed_oldest.log_path.exists())
        self.assertTrue(all(session.log_path.exists() for session in sessions[1:]))
        for session in sessions[1:]:
            session.close()
        trigger.close()
        second_trigger.close()

    def test_fail_soft_when_log_directory_is_not_a_directory(self):
        blocker = self.root / "artifacts"
        blocker.write_text("not a directory", encoding="utf-8")

        diagnostics = Diagnostics(self.root)
        diagnostics.info("must not raise")
        status = diagnostics.status()

        self.assertFalse(status["available"])
        self.assertTrue(status["error"])
        self.assertEqual(Path(status["directory"]), blocker / "waypoint-logs")

    def test_concurrent_writers_produce_complete_json_lines(self):
        diagnostics = Diagnostics(self.root)
        workers = [
            threading.Thread(
                target=lambda worker=index: [
                    diagnostics.info("worker event", worker=worker, item=item) for item in range(50)
                ]
            )
            for index in range(8)
        ]

        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        entries = _entries(diagnostics)
        events = [entry for entry in entries if entry["message"] == "worker event"]
        self.assertEqual(len(events), 400)
        self.assertEqual({entry["worker"] for entry in events}, set(range(8)))

    def test_report_is_bounded_controlled_and_readable(self):
        diagnostics = Diagnostics(self.root)
        diagnostics.set_context(host="AMD-DESKTOP", appVersion="9.1", guiPid=123, sessionId="abc")
        diagnostics.warning("route paused", reason="foreground lost")
        report = diagnostics.report(
            {
                "route": {"name": "Test route", "points": list(range(100))},
                "pose": {"x": 1, "z": 2},
                "rawArgs": ["--secret", "do-not-copy"],
                "environment": {"HOME": "private"},
                "status": "x" * 100_000,
                "view": {"tab": "Scene & beacons"},
                "recentResults": ["capture failed"],
                "diagnostics": {"reader": "unavailable"},
                "contextComparison": {"expectedPid": 123, "actualPid": 456},
            }
        )

        self.assertLessEqual(len(report), diagnostics_module.MAX_REPORT_CHARS)
        self.assertIn("App version: 9.1", report)
        self.assertIn("AMD-DESKTOP", report)
        self.assertIn("Test route", report)
        self.assertIn("route paused", report)
        self.assertIn("Scene & beacons", report)
        self.assertIn("capture failed", report)
        self.assertIn("unavailable", report)
        self.assertIn("expectedPid", report)
        self.assertNotIn("rawArgs", report)
        self.assertNotIn("do-not-copy", report)
        self.assertNotIn("HOME", report)

    def test_exception_captures_full_stack(self):
        diagnostics = Diagnostics(self.root)

        def inner():
            raise RuntimeError("deep failure")

        def outer():
            inner()

        try:
            outer()
        except RuntimeError:
            diagnostics.exception("operation failed")

        entry = _entries(diagnostics)[-1]
        self.assertEqual(entry["level"], "ERROR")
        self.assertEqual(entry["exceptionType"], "RuntimeError")
        self.assertIn("in outer", entry["traceback"])
        self.assertIn("in inner", entry["traceback"])
        self.assertIn("deep failure", entry["traceback"])
        self.assertIn("\n", entry["traceback"])

    def test_existing_helpers_are_read_only_and_bounded(self):
        diagnostics = Diagnostics(self.root)
        diagnostics.set_context(host="AMD-DESKTOP", appVersion="4.2", sessionId="saved")
        diagnostics.warning("saved warning", detail="z" * 100_000)
        before = sorted(path.name for path in diagnostics.directory.iterdir())
        diagnostics.close()

        status = existing_status(self.root)
        report = existing_report(self.root)
        after = sorted(path.name for path in diagnostics.directory.iterdir())

        self.assertEqual(before, after)
        self.assertTrue(status["offline"])
        self.assertTrue(status["available"])
        self.assertEqual(Path(status["logFile"]), diagnostics.log_path)
        self.assertIn("saved logs only", report)
        self.assertIn("No live app snapshot", report)
        self.assertIn("saved warning", report)
        self.assertIn("App version: 4.2", report)
        self.assertLessEqual(len(report), diagnostics_module.MAX_REPORT_CHARS)

    def test_existing_helpers_report_missing_logs_without_creating_directory(self):
        status = existing_status(self.root)
        report = existing_report(self.root)

        self.assertFalse(status["available"])
        self.assertTrue(status["offline"])
        self.assertIn("No saved", status["error"])
        self.assertIn("saved logs only", report)
        self.assertFalse((self.root / "artifacts").exists())

    def test_hooks_log_chain_and_restore(self):
        sys_calls = []
        thread_calls = []

        def previous_sys(*args):
            sys_calls.append(args)

        def previous_thread(args):
            thread_calls.append(args)

        with mock.patch.object(sys, "excepthook", previous_sys), mock.patch.object(
            threading, "excepthook", previous_thread
        ):
            diagnostics = Diagnostics(self.root)
            diagnostics.install_hooks()
            installed_sys = sys.excepthook
            installed_thread = threading.excepthook

            try:
                raise ValueError("hook failure")
            except ValueError:
                exc_type, exc_value, exc_tb = sys.exc_info()
            installed_sys(exc_type, exc_value, exc_tb)

            class Args:
                pass

            args = Args()
            args.exc_type = exc_type
            args.exc_value = exc_value
            args.exc_traceback = exc_tb
            args.thread = threading.current_thread()
            installed_thread(args)

            self.assertEqual(len(sys_calls), 1)
            self.assertEqual(thread_calls, [args])
            entries = _entries(diagnostics)
            self.assertTrue(
                any(
                    entry["message"] == "Unhandled exception" and "hook failure" in entry["traceback"]
                    for entry in entries
                )
            )
            self.assertTrue(any(entry["message"] == "Unhandled thread exception" for entry in entries))

            diagnostics.close()
            self.assertIs(sys.excepthook, previous_sys)
            self.assertIs(threading.excepthook, previous_thread)
            self.assertFalse(diagnostics.status()["available"])


if __name__ == "__main__":
    unittest.main()
