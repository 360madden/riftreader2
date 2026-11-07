import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import json
import os
import socket
import shutil
import struct
from contextlib import ExitStack, contextmanager, nullcontext


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "addon_command_console", ROOT / "scripts" / "addon_command_console.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class RegularReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "receipt.json"
        self.path.write_bytes(b"old")

    def replacement_before_open(self, content):
        replacement = self.directory / "replacement.json"
        replacement.write_bytes(content)
        original_open = Path.open

        def replace_then_open(path, *args, **kwargs):
            if path == self.path:
                os.replace(replacement, self.path)
            return original_open(path, *args, **kwargs)
        return mock.patch.object(Path, "open", replace_then_open)

    def test_atomic_replacement_before_open_accepts_new_size(self):
        with self.replacement_before_open(b"new content"):
            self.assertEqual(module._read_regular(self.path, 32, "blocked"), b"new content")

    def test_oversize_replacement_rejected_before_read(self):
        replacement = self.directory / "replacement.json"
        replacement.write_bytes(b"x" * 33)
        original_open = Path.open
        reads = []
        class Tracked:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def read(self, count):
                reads.append(count)
                return self.stream.read(count)
        def replace_then_open(path, *args, **kwargs):
            os.replace(replacement, self.path)
            return Tracked(original_open(path, *args, **kwargs))
        with mock.patch.object(Path, "open", replace_then_open):
            with self.assertRaisesRegex(module.Blocked, "blocked"):
                module._read_regular(self.path, 32, "blocked")
        self.assertEqual(reads, [])

    def test_growth_after_fstat_is_bounded_and_rejected(self):
        original_open = Path.open
        real_fstat = module.os.fstat
        reads = []
        class Tracked:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def read(self, count):
                reads.append(count)
                return self.stream.read(count)
        def opened(path, *args, **kwargs):
            return Tracked(original_open(path, *args, **kwargs))
        calls = 0
        def grow(fd):
            nonlocal calls
            info = real_fstat(fd)
            calls += 1
            if calls == 1:
                with original_open(self.path, "ab") as stream:
                    stream.write(b"x" * 100)
            return info
        with mock.patch.object(Path, "open", opened), mock.patch.object(module.os, "fstat", grow):
            with self.assertRaisesRegex(module.Blocked, "blocked"):
                module._read_regular(self.path, 32, "blocked")
        self.assertEqual(reads, [33])

    def test_path_swap_after_open_rejected(self):
        other = self.directory / "other.json"
        other.write_bytes(b"new")  # Same size and timestamp, but a different file.
        initial = self.path.stat()
        os.utime(other, ns=(initial.st_atime_ns, initial.st_mtime_ns))
        self.assertEqual(other.stat().st_size, initial.st_size)
        self.assertEqual(other.stat().st_mtime_ns, initial.st_mtime_ns)
        self.assertFalse(os.path.samestat(initial, other.stat()))
        real_lstat = Path.lstat
        calls = 0
        def changed(path, *args, **kwargs):
            nonlocal calls
            if path == self.path:
                calls += 1
                if calls == 2:
                    return real_lstat(other)
            return real_lstat(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", changed):
            with self.assertRaisesRegex(module.Blocked, "blocked"):
                module._read_regular(self.path, 32, "blocked")

    def test_inplace_truncation_rejected(self):
        real_fstat = module.os.fstat
        calls = 0
        def mutate(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.path.write_bytes(b"x")
            return real_fstat(fd)
        with mock.patch.object(module.os, "fstat", mutate):
            with self.assertRaisesRegex(module.Blocked, "blocked"):
                module._read_regular(self.path, 32, "blocked")

    def test_reparse_flag_after_open_rejected(self):
        real_lstat = Path.lstat
        calls = 0
        def changed(path, *args, **kwargs):
            nonlocal calls
            info = real_lstat(path, *args, **kwargs)
            if path == self.path:
                calls += 1
                if calls == 2:
                    values = {name: getattr(info, name) for name in (
                        "st_mode", "st_size", "st_mtime_ns", "st_dev", "st_ino")}
                    values["st_file_attributes"] = 0x400
                    return type("Stat", (), values)()
            return info
        with mock.patch.object(Path, "lstat", changed), mock.patch.object(
                module.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400, create=True):
            with self.assertRaisesRegex(module.Blocked, "blocked"):
                module._read_regular(self.path, 32, "blocked")


class AddonCommandValidationTests(unittest.TestCase):
    def test_guest_cache_alias_only_matches_relocated_lab1(self):
        current = Path(r"C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx")
        old = Path(r"C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx")
        self.assertEqual(
            module.legacy_guest_target_for_vmx(current),
            "RiftReader2 Guest Windows: " + str(old.resolve(strict=False)),
        )
        self.assertIsNone(module.legacy_guest_target_for_vmx(
            Path(r"C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx")))
        self.assertIsNone(module.legacy_guest_target_for_vmx(old))

    def test_exact_simple_commands(self):
        for value in ("/reloadui", "/rr2guide status", "/rr2guide clear"):
            self.assertEqual(value, module.validate_addon_command(value))

    def test_exact_bind_commands(self):
        for lab in ("lab1", "lab2"):
            value = f"/rr2guide bind {lab} " + "a" * 32
            self.assertEqual(value, module.validate_addon_command(value))

    def test_exact_rebind_commands_use_the_bind_identity_rules(self):
        for lab in ("lab1", "lab2"):
            value = f"/rr2guide rebind {lab} " + "a" * 32
            self.assertEqual(value, module.validate_addon_command(value, lab))
            self.assertEqual(
                {"type": "command", "command": value},
                module.validate_operation(value, None, lab),
            )
            other_lab = "lab2" if lab == "lab1" else "lab1"
            with self.assertRaisesRegex(module.Blocked, "addon-command-lab-mismatch"):
                module.validate_addon_command(value, other_lab)

    def test_result_contract(self):
        value = ("/rr2guide result lab2 " + "b" * 32
                 + " 1 2 3 4 u800000000000001 10.5 -2 4.25 5 3 4 -12")
        self.assertEqual(value, module.validate_addon_command(value))

    def test_fractional_source_clock_and_exact_lab(self):
        value = ("/rr2guide result lab2 " + "b" * 32
                 + " 1 2 3 4.125 u800000000000001 10.5 -2 4.25 5 3 4 -12")
        self.assertEqual(value, module.validate_addon_command(value, "lab2"))
        with self.assertRaisesRegex(module.Blocked, "addon-command-lab-mismatch"):
            module.validate_addon_command(value, "lab1")

    def test_rejects_arbitrary_commands_and_text(self):
        rejected = [
            "/say hello", "/script print(1)", "/rr2guide", "/rr2guide bind lab3 " + "a" * 32,
            "/rr2guide bind lab2 " + "A" * 32, "/reloadui ", "/reloadui\n",
            "/rr2guide rebind lab3 " + "a" * 32, "/rr2guide rebind lab2 " + "A" * 32,
            "/rr2guide rebind lab2 " + "a" * 31, "/rr2guide rebind  lab2 " + "a" * 32,
            "/rr2guide result lab2 " + "b" * 32
            + " 1 2 3 4 u800000000000001 10 -2 4 99 3 4 -12",
            "/" + "x" * 512,
        ]
        for value in rejected:
            with self.subTest(value=value[:50]), self.assertRaises(module.Blocked):
                module.validate_addon_command(value)

    def test_rejects_result_nonfinite_and_unsafe_integer(self):
        base = "/rr2guide result lab1 " + "1" * 32
        for suffix in (
            " 0 2 3 4 player 1 2 3 5 3 4 0",
            " 1 2 3 9007199254740992 player 1 2 3 5 3 4 0",
            " 1 2 3 4 player 1e999 2 3 5 3 4 0",
        ):
            with self.subTest(suffix=suffix), self.assertRaises(module.Blocked):
                module.validate_addon_command(base + suffix)

    def test_hide_addon_is_narrow_and_bounded(self):
        self.assertEqual(
            {"type": "ui-step", "step": "hide-addon", "frame": "readiness", "x": 742, "y": 418},
            module.validate_operation(None, "hide-addon", "lab2", "readiness", 742, 418),
        )
        for args in (
            (None, "hide-addon", "lab2", None, 742, 418),
            (None, "hide-addon", "lab2", "casting", -1, 236),
            (None, "hide-addon", "lab2", "other", 10, 10),
            ("/rr2guide status", None, "lab2", "casting", 1015, 236),
        ):
            with self.subTest(args=args), self.assertRaises(module.Blocked):
                module.validate_operation(*args)


class ReviewReceiptTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 28, 12, 0, 30, tzinfo=timezone.utc)
        self.plan = {
            "captureId": "a" * 32,
            "screenSha256": "b" * 64,
            "capturedAtUtc": (self.now - timedelta(seconds=20)).isoformat(),
            "operation": {"type": "command", "command": "/rr2guide status"},
        }
        self.plan["planSha256"] = module._plan_sha(self.plan)
        self.receipt = {
            "schemaVersion": 1,
            "captureId": self.plan["captureId"],
            "screenSha256": self.plan["screenSha256"],
            "planSha256": self.plan["planSha256"],
            "reviewedAtUtc": (self.now - timedelta(seconds=2)).isoformat(),
            "decision": "approved",
            "gameForeground": True,
            "textEntryClosed": False,
            "chatEntryOpen": True,
            "chatEntryEmpty": True,
            "chatEntryFocused": True,
            "panelOpen": False,
            "soleControllerIdle": True,
            "knownControllerIdle": True,
            "queueIdle": True,
            "reviewer": "root-agent",
            "note": "RIFT is foreground and chat input is safe.",
        }

    def test_accepts_exact_fresh_review(self):
        module.validate_review(self.plan, self.receipt, self.now)

    def test_rejects_capture_mismatch(self):
        self.receipt["captureId"] = "c" * 32
        with self.assertRaisesRegex(module.Blocked, "review-capture-mismatch"):
            module.validate_review(self.plan, self.receipt, self.now)

    def test_rejects_whole_plan_change(self):
        self.plan["operation"]["command"] = "/reloadui"
        with self.assertRaisesRegex(module.Blocked, "plan-changed"):
            module.validate_review(self.plan, self.receipt, self.now)

    def test_rejects_stale_capture(self):
        self.plan["capturedAtUtc"] = (self.now - timedelta(seconds=61)).isoformat()
        self.plan["planSha256"] = module._plan_sha(self.plan)
        self.receipt["planSha256"] = self.plan["planSha256"]
        with self.assertRaisesRegex(module.Blocked, "stale-review-capture"):
            module.validate_review(self.plan, self.receipt, self.now)

    def test_rejects_nonforeground_or_wrong_reviewer(self):
        for field, value in (("gameForeground", False), ("reviewer", "human")):
            receipt = dict(self.receipt)
            receipt[field] = value
            with self.subTest(field=field), self.assertRaises(module.Blocked):
                module.validate_review(self.plan, receipt, self.now)

    def test_closed_chat_rejects_command(self):
        self.receipt["chatEntryOpen"] = False
        self.receipt["textEntryClosed"] = True
        with self.assertRaisesRegex(module.Blocked, "reviewed-ui-state-mismatch"):
            module.validate_review(self.plan, self.receipt, self.now)

    def test_command_rejects_nonempty_or_unfocused_chat(self):
        for field in ("chatEntryEmpty", "chatEntryFocused"):
            receipt = dict(self.receipt)
            receipt[field] = False
            with self.subTest(field=field), self.assertRaisesRegex(
                    module.Blocked, "reviewed-ui-state-mismatch"):
                module.validate_review(self.plan, receipt, self.now)

    def test_ui_steps_require_exact_reviewed_state(self):
        cases = (
            ("open-chat", False, False, True),
            ("close-ui", True, False, True),
        )
        for step, panel_open, chat_open, text_closed in cases:
            plan = dict(self.plan)
            plan["operation"] = {"type": "ui-step", "step": step}
            plan["planSha256"] = module._plan_sha(plan)
            receipt = dict(self.receipt, planSha256=plan["planSha256"],
                           panelOpen=panel_open, chatEntryOpen=chat_open,
                           chatEntryEmpty=False, chatEntryFocused=False,
                           textEntryClosed=text_closed)
            with self.subTest(step=step):
                module.validate_review(plan, receipt, self.now)

    def test_deferred_review_binds_destination_and_sequence(self):
        plan = dict(self.plan)
        plan["operation"] = {"type": "deferred-result", "intentSha256": "f" * 64,
            "frozenCalculatorDirectory": r"C:\frozen", "intent": {
                "resultSequence": 7, "destination": {"x": 13, "y": 2, "z": 24}}}
        plan["planSha256"] = module._plan_sha(plan)
        receipt = dict(self.receipt, planSha256=plan["planSha256"],
                       deferredIntentReviewed=True, deferredResultSequenceReviewed=7,
                       deferredDestinationXReviewed=13, deferredDestinationYReviewed=2,
                       deferredDestinationZReviewed=24)
        module.validate_review(plan, receipt, self.now)
        receipt["deferredDestinationXReviewed"] = 14
        with self.assertRaisesRegex(module.Blocked, "reviewed-ui-state-mismatch"):
            module.validate_review(plan, receipt, self.now)

    def test_hide_review_binds_exact_frame_and_point(self):
        plan = dict(self.plan)
        plan["operation"] = {"type": "ui-step", "step": "hide-addon",
                             "frame": "casting", "x": 1015, "y": 236,
                             "screenWidth": 1211, "screenHeight": 757}
        plan["planSha256"] = module._plan_sha(plan)
        receipt = dict(self.receipt, planSha256=plan["planSha256"], panelOpen=True,
                       chatEntryOpen=False, chatEntryEmpty=False, chatEntryFocused=False,
                       textEntryClosed=True, hideButtonReviewed=True,
                       hideFrameReviewed="casting", hideXReviewed=1015, hideYReviewed=236)
        module.validate_review(plan, receipt, self.now)
        for field, value in (("hideFrameReviewed", "readiness"),
                             ("hideXReviewed", 742), ("hideYReviewed", 418),
                             ("hideButtonReviewed", False)):
            changed = dict(receipt)
            changed[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                    module.Blocked, "reviewed-ui-state-mismatch"):
                module.validate_review(plan, changed, self.now)


class IdentityValidationTests(unittest.TestCase):
    def test_preserves_exact_native_tick(self):
        value = module.validate_expected_game(
            "lab2", 1234, 639288075394270241, "D" * 64
        )
        self.assertEqual(639288075394270241, value["processStartUtcTicks"])
        self.assertEqual("d" * 64, value["executableSha256"])

    def test_require_game_rejects_one_tick_difference(self):
        expected = module.validate_expected_game(
            "lab2", 1234, 639288075394270241, "d" * 64
        )
        actual = {"processId": 1234, "processStartUtcTicks": 639288075394270240,
                  "executableSha256": "d" * 64}
        with self.assertRaisesRegex(module.Blocked, "game-identity-drift"):
            module._require_game(actual, expected)

    def test_identity_session_closes_and_sanitizes_guest_failure(self):
        events = []

        class FailedSession:
            def __enter__(self):
                events.append("enter")
                return self

            def __exit__(self, *_args):
                events.append("exit")

            def powershell(self, _script):
                raise module.SessionError("sensitive fixture detail")

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(module, "GuestSession", return_value=FailedSession()), \
                self.assertRaisesRegex(module.Blocked, "^game-identity-unavailable$"):
            config = module.Config(Path("lab.vmx"), 5905, Path("vmrun.exe"), Path(folder))
            module.query_game_identity(config, {"vmwarePid": 99})

        self.assertEqual(["enter", "exit"], events)


class ExecuteTests(unittest.TestCase):
    class Client:
        def __init__(self, fail_release=False):
            self.events = []
            self.fail_release = fail_release

        def keyPress(self, key):
            self.events.append(("press", key))

        def keyUp(self, key):
            self.events.append(("up", key))
            if self.fail_release and key == "enter":
                raise RuntimeError("release failure")

        def disconnect(self):
            self.events.append(("disconnect",))

        def mouseMove(self, x, y):
            self.events.append(("move", x, y))

        def mousePress(self, button):
            self.events.append(("mousePress", button))

        def mouseUp(self, button):
            self.events.append(("mouseUp", button))
            if self.fail_release:
                raise RuntimeError("mouse release failure")

    def normal_execution_fixture(self, output, client=None):
        now = datetime.now(timezone.utc)
        game = module.validate_expected_game("lab2", 55, 639288075394270241, "d" * 64)
        vm = {"vmwarePid": 99, "vmwareStartUtc": "epoch"}
        command = "/rr2guide bind lab2 " + "a" * 32
        screen = output / "review-screen.png"
        screen.write_bytes(b"reviewed screen")
        plan = {
            "schemaVersion": 1, "captureId": "e" * 32,
            "capturedAtUtc": (now - timedelta(seconds=2)).isoformat(),
            "screen": str(screen), "screenSha256": module._sha(screen),
            "operation": {"type": "command", "command": command},
            "vmIdentity": vm, "gameIdentity": game,
        }
        plan["planSha256"] = module._plan_sha(plan)
        plan_path = output / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        review = {
            "schemaVersion": 1, "captureId": plan["captureId"],
            "screenSha256": plan["screenSha256"], "reviewedAtUtc": now.isoformat(),
            "planSha256": plan["planSha256"],
            "decision": "approved", "gameForeground": True,
            "textEntryClosed": False, "chatEntryOpen": True,
            "chatEntryEmpty": True, "chatEntryFocused": True, "panelOpen": False,
            "soleControllerIdle": True, "knownControllerIdle": True, "queueIdle": True,
            "reviewer": "root-agent", "note": "RIFT foreground reviewed",
        }
        review_path = output / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        config = module.Config(Path("lab.vmx"), 5905, Path("vmrun.exe"), output)
        return config, plan_path, review_path, game, vm, command, client or self.Client()

    @contextmanager
    def replay_execution_environment(self, output):
        fixture = self.normal_execution_fixture(output)
        config, plan_path, review_path, game, vm, command, client = fixture

        def capture(_client, destination):
            destination.write_bytes(b"after")
            return 800, 600

        with ExitStack() as stack:
            for name, replacement in (
                ("ControlMutex", mock.Mock(side_effect=lambda *_: nullcontext())),
                ("collect_identity", mock.Mock(return_value=vm)),
                ("verify_identity", mock.Mock(return_value=vm)),
                ("game_identity_session", mock.Mock(side_effect=lambda *_: nullcontext(object()))),
                ("query_game_identity_in_session", mock.Mock(
                    return_value={key: game[key] for key in game if key != "lab"})),
                ("connect", mock.Mock(return_value=client)),
                ("_capture", mock.Mock(side_effect=capture)),
                ("_type_text", mock.Mock(side_effect=lambda _client, text:
                                         client.events.append(("text", text)))),
            ):
                stack.enter_context(mock.patch.object(module, name, replacement))
            stack.enter_context(mock.patch.object(module.time, "sleep"))
            yield config, plan_path, review_path, command, client

    def test_report_publication_failure_cannot_replay_sent_command(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.replay_execution_environment(output) as (config, plan, review, command, client):
                atomic_json = module._atomic_json

                def fail_final_report(path, value):
                    if path == output / "execution.json":
                        raise OSError("fixture report publication failure")
                    return atomic_json(path, value)

                with mock.patch.object(module, "_atomic_json", side_effect=fail_final_report), \
                        self.assertRaises(OSError):
                    module.execute(config, plan, review)
                self.assertFalse((output / "execution.json").exists())
                marker = (output / "execution-attempt.json").read_bytes()
                with self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                    module.execute(config, plan, review)
                self.assertEqual(marker, (output / "execution-attempt.json").read_bytes())
                self.assertEqual([("text", command)], [e for e in client.events if e[0] == "text"])
                self.assertEqual([("press", "enter")], [e for e in client.events if e[0] == "press"])
                self.assertIn(("up", "enter"), client.events)
                self.assertIn(("disconnect",), client.events)

    def test_claim_blocks_contender_before_final_report_is_published(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.replay_execution_environment(output) as (config, plan, review, command, client):
                atomic_json = module._atomic_json
                contenders = []

                def contender_before_publication(path, report):
                    if path == output / "execution.json":
                        self.assertFalse(path.exists())
                        with self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                            module.execute(config, plan, review)
                        contenders.append(None)
                    return atomic_json(path, report)

                with mock.patch.object(module, "_atomic_json", side_effect=contender_before_publication):
                    winner = module.execute(config, plan, review)
                self.assertEqual(1, len(contenders))
                self.assertEqual(winner, json.loads((output / "execution.json").read_text()))
                self.assertEqual([("text", command)], [e for e in client.events if e[0] == "text"])

    def test_cancelled_send_with_unwritable_report_still_blocks_replay(self):
        for cancellation in (KeyboardInterrupt, SystemExit):
            with self.subTest(cancellation=cancellation), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)
                with self.replay_execution_environment(output) as (config, plan, review, _, client):
                    atomic_json = module._atomic_json

                    def fail_report(path, value):
                        if path == output / "execution.json":
                            raise OSError("fixture final publication failure")
                        return atomic_json(path, value)

                    def cancelled_send(*_args):
                        client.keyPress("enter")
                        raise cancellation()

                    with mock.patch.object(module, "_send_operation", side_effect=cancelled_send) as send, \
                            mock.patch.object(module, "_atomic_json", side_effect=fail_report):
                        with self.assertRaises(OSError):
                            module.execute(config, plan, review)
                        self.assertFalse((output / "execution.json").exists())
                        marker = (output / "execution-attempt.json").read_bytes()
                        with self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                            module.execute(config, plan, review)
                        send.assert_called_once()
                    self.assertEqual(marker, (output / "execution-attempt.json").read_bytes())
                    self.assertIn(("up", "enter"), client.events)
                    self.assertIn(("disconnect",), client.events)

    def test_two_callers_passing_early_check_keep_single_winning_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.replay_execution_environment(output) as (config, plan, review, command, client):
                entries = []
                winner = []

                @contextmanager
                def interleaved_mutex(*_args):
                    entries.append(None)
                    # Outer caller reached mutex admission with no report/marker.
                    # Let a second caller acquire and finish before outer acquires.
                    if len(entries) == 1:
                        self.assertFalse((output / "execution-attempt.json").exists())
                        self.assertFalse((output / "execution.json").exists())
                        module.execute(config, plan, review)
                        winner.append((output / "execution.json").read_bytes())
                    yield

                with mock.patch.object(module, "ControlMutex", side_effect=interleaved_mutex), \
                        self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                    module.execute(config, plan, review)
                self.assertEqual(2, len(entries))
                self.assertEqual(winner[0], (output / "execution.json").read_bytes())
                self.assertEqual("completed", json.loads(winner[0])["status"])
                self.assertEqual([("text", command)], [e for e in client.events if e[0] == "text"])
                self.assertEqual([("press", "enter")], [e for e in client.events if e[0] == "press"])

    def test_waiting_contender_cannot_send_after_owner_report_publication_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.replay_execution_environment(output) as (config, plan, review, command, client):
                entered = []
                retained = []
                atomic_json = module._atomic_json

                def fail_report(path, value):
                    if path == output / "execution.json":
                        raise OSError("fixture final publication failure")
                    return atomic_json(path, value)

                @contextmanager
                def owner_first(*_args):
                    entered.append(None)
                    if len(entered) == 1:
                        with self.assertRaises(OSError):
                            module.execute(config, plan, review)
                        self.assertFalse((output / "execution.json").exists())
                        retained.append((output / "execution-attempt.json").read_bytes())
                    yield

                with mock.patch.object(module, "ControlMutex", side_effect=owner_first), \
                        mock.patch.object(module, "_atomic_json", side_effect=fail_report), \
                        self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                    module.execute(config, plan, review)
                self.assertEqual(2, len(entered))
                self.assertFalse((output / "execution.json").exists())
                self.assertEqual(retained[0], (output / "execution-attempt.json").read_bytes())
                self.assertEqual([("text", command)], [e for e in client.events if e[0] == "text"])
                self.assertEqual([("press", "enter")], [e for e in client.events if e[0] == "press"])

    def test_legacy_report_appearing_at_mutex_admission_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.replay_execution_environment(output) as (config, plan, review, _, client):
                legacy = b'{"status":"completed","legacyEvidence":"retain exact bytes"}'

                @contextmanager
                def report_wins(*_args):
                    (output / "execution.json").write_bytes(legacy)
                    yield

                with mock.patch.object(module, "ControlMutex", side_effect=report_wins), \
                        self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                    module.execute(config, plan, review)
                self.assertEqual(legacy, (output / "execution.json").read_bytes())
                self.assertFalse((output / "execution-attempt.json").exists())
                self.assertEqual([], client.events)
                module.connect.assert_not_called()

    def test_attempt_state_stat_failure_blocks_without_input_or_publication(self):
        for target, fail_at in (("execution.json", 1), ("execution-attempt.json", 1),
                                ("execution.json", 2)):
            with self.subTest(target=target, fail_at=fail_at), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)
                with self.replay_execution_environment(output) as (config, plan, review, _, client):
                    actual_lstat = Path.lstat
                    calls = []

                    def inaccessible_stat(path, *args, **kwargs):
                        if path == output / target:
                            calls.append(None)
                            if len(calls) == fail_at:
                                raise PermissionError("fixture inaccessible attempt state")
                        return actual_lstat(path, *args, **kwargs)

                    with mock.patch.object(Path, "lstat", inaccessible_stat), \
                            self.assertRaisesRegex(module.Blocked, "^attempt-state-unavailable$"):
                        module.execute(config, plan, review)
                    self.assertEqual(fail_at, len(calls))
                    self.assertEqual([], client.events)
                    module.connect.assert_not_called()
                    self.assertFalse((output / "execution.json").exists())
                    self.assertFalse((output / "execution-attempt.json").exists())

    def test_dangling_legacy_report_entry_blocks_without_following_link(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.replay_execution_environment(output) as (config, plan, review, _, client):
                actual_lstat = Path.lstat

                def dangling_entry_stat(path, *args, **kwargs):
                    if path == output / "execution.json":
                        # lstat observes the directory entry even when its target
                        # cannot be opened. No privileged symlink creation needed.
                        return os.stat_result((0o120777, 0, 0, 1, 0, 0, 0, 0, 0, 0))
                    return actual_lstat(path, *args, **kwargs)

                with mock.patch.object(Path, "lstat", dangling_entry_stat), \
                        self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                    module.execute(config, plan, review)
                self.assertEqual([], client.events)
                module.connect.assert_not_called()
                self.assertFalse((output / "execution-attempt.json").exists())

    def test_marker_storage_failures_send_nothing_and_retain_partial_claim(self):
        for failure in ("create", "write", "flush", "fsync"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)
                marker = output / "execution-attempt.json"
                with self.replay_execution_environment(output) as (config, plan, review, _, client):
                    original_open = Path.open

                    class FailingStream:
                        def __init__(self, stream):
                            self.stream = stream

                        def __enter__(self):
                            return self

                        def __exit__(self, *_args):
                            self.stream.close()

                        def write(self, data):
                            if failure == "write":
                                self.stream.write(data[:8])
                                raise OSError("fixture partial marker write")
                            return self.stream.write(data)

                        def flush(self):
                            self.stream.flush()
                            if failure == "flush":
                                raise OSError("fixture marker flush failure")

                        def fileno(self):
                            return self.stream.fileno()

                    def failing_open(path, *args, **kwargs):
                        if path == marker and args and args[0] == "xb":
                            if failure == "create":
                                raise PermissionError("fixture marker create failure")
                            return FailingStream(original_open(path, *args, **kwargs))
                        return original_open(path, *args, **kwargs)

                    with ExitStack() as stack:
                        stack.enter_context(mock.patch.object(Path, "open", failing_open))
                        if failure == "fsync":
                            stack.enter_context(mock.patch.object(
                                module.os, "fsync", side_effect=OSError("fixture marker fsync failure")))
                        with self.assertRaises(module.Blocked):
                            module.execute(config, plan, review)
                    self.assertEqual([], client.events)
                    module.connect.assert_not_called()
                    self.assertFalse((output / "execution.json").exists())
                    if failure == "create":
                        self.assertFalse(marker.exists())
                    else:
                        retained = marker.read_bytes()
                        self.assertTrue(retained)
                        with self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                            module.execute(config, plan, review)
                        self.assertEqual(retained, marker.read_bytes())
                        self.assertEqual([], client.events)

    def test_send_failure_or_cancellation_releases_and_retains_attempt(self):
        for failure in (RuntimeError, KeyboardInterrupt, SystemExit):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)
                with self.replay_execution_environment(output) as (config, plan, review, _, client):
                    def partially_send(*_args):
                        client.keyPress("enter")
                        raise failure("fixture interrupted send")

                    with mock.patch.object(module, "_send_operation", side_effect=partially_send) as send:
                        with self.assertRaises(module.Blocked):
                            module.execute(config, plan, review)
                        marker = (output / "execution-attempt.json").read_bytes()
                        with self.assertRaisesRegex(module.Blocked, "^operation-already-attempted$"):
                            module.execute(config, plan, review)
                        send.assert_called_once()
                    self.assertEqual(marker, (output / "execution-attempt.json").read_bytes())
                    self.assertIn(("up", "enter"), client.events)
                    self.assertIn(("disconnect",), client.events)
                    report = json.loads((output / "execution.json").read_text())
                    self.assertTrue(report["inputMayHaveBeenSent"])
                    self.assertTrue(report["releaseSucceeded"])

    def test_success_claim_is_bound_and_synced_before_first_input(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with self.replay_execution_environment(output) as (config, plan, review, _, client):
                syncs = []
                actual_fsync = module.os.fsync
                actual_send = module._send_operation
                expected_plan = json.loads(plan.read_text())

                def record_sync(fd):
                    actual_fsync(fd)
                    syncs.append(fd)

                def inspect_before_send(*args):
                    self.assertTrue(syncs, "claim must reach fsync before any key or text input")
                    self.assertEqual([], client.events)
                    claim = json.loads((output / "execution-attempt.json").read_text())
                    self.assertEqual(1, claim["schemaVersion"])
                    self.assertEqual(expected_plan["captureId"], claim["captureId"])
                    self.assertEqual(expected_plan["planSha256"], claim["planSha256"])
                    datetime.fromisoformat(claim["attemptedAtUtc"].replace("Z", "+00:00"))
                    return actual_send(*args)

                with mock.patch.object(module.os, "fsync", side_effect=record_sync), \
                        mock.patch.object(module, "_send_operation", side_effect=inspect_before_send):
                    report = module.execute(config, plan, review)
                self.assertEqual("completed", report["status"])
                self.assertTrue(report["releaseSucceeded"])
                self.assertTrue((output / "execution-attempt.json").exists())

    def test_execute_revalidates_and_types_one_exact_command(self):
        now = datetime.now(timezone.utc)
        game = module.validate_expected_game("lab2", 55, 639288075394270241, "d" * 64)
        vm = {"vmwarePid": 99, "vmwareStartUtc": "epoch"}
        command = "/rr2guide bind lab2 " + "a" * 32
        client = self.Client()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            screen = output / "review-screen.png"
            screen.write_bytes(b"reviewed screen")
            plan = {
                "schemaVersion": 1, "captureId": "e" * 32,
                "capturedAtUtc": (now - timedelta(seconds=2)).isoformat(),
                "screen": str(screen), "screenSha256": module._sha(screen),
                "operation": {"type": "command", "command": command},
                "vmIdentity": vm, "gameIdentity": game,
            }
            plan["planSha256"] = module._plan_sha(plan)
            plan_path = output / "plan.json"
            plan_path.write_text(__import__("json").dumps(plan), encoding="utf-8")
            review = {
                "schemaVersion": 1, "captureId": plan["captureId"],
                "screenSha256": plan["screenSha256"], "reviewedAtUtc": now.isoformat(),
                "planSha256": plan["planSha256"],
                "decision": "approved", "gameForeground": True,
                "textEntryClosed": False, "chatEntryOpen": True,
                "chatEntryEmpty": True, "chatEntryFocused": True, "panelOpen": False,
                "soleControllerIdle": True,
                "knownControllerIdle": True, "queueIdle": True,
                "reviewer": "root-agent", "note": "RIFT foreground reviewed",
            }
            review_path = output / "review.json"
            review_path.write_text(__import__("json").dumps(review), encoding="utf-8")
            config = module.Config(Path("lab.vmx"), 5905, Path("vmrun.exe"), output)

            def fake_capture(_client, destination):
                destination.write_bytes(b"after")
                return 800, 600

            identity_session = object()

            with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                    mock.patch.object(module, "collect_identity", return_value=vm), \
                    mock.patch.object(module, "verify_identity", return_value=vm), \
                    mock.patch.object(module, "game_identity_session",
                                      return_value=__import__("contextlib").nullcontext(identity_session)) as session_factory, \
                    mock.patch.object(module, "query_game_identity_in_session",
                                      return_value={k: game[k] for k in game if k != "lab"}) as query, \
                    mock.patch.object(module, "connect", return_value=client), \
                    mock.patch.object(module, "_capture", side_effect=fake_capture), \
                    mock.patch.object(module, "_type_text", side_effect=lambda _client, value: client.events.append(("text", value))), \
                    mock.patch.object(module, "validate_review", wraps=module.validate_review) as review_check, \
                    mock.patch.object(module.time, "sleep"):
                report = module.execute(config, plan_path, review_path)
            sidecar = json.loads((output / "execution-timings.json").read_text())
            self.assertEqual([e["phase"] for e in sidecar["events"]],
                             ["vm-identity-before", "guest-session-acquire", "game-identity-before",
                              "vnc-connect-initiate", "input", "screen-capture",
                              "vm-identity-after", "game-identity-after"])
            self.assertNotIn(command, json.dumps(sidecar))
            self.assertEqual(set(sidecar), {"schemaVersion", "operation", "events"})
            self.assertTrue(all(set(e) == {"phase", "elapsedNs"} and e["elapsedNs"] >= 0
                                for e in sidecar["events"]))

        self.assertEqual("completed", report["status"])
        self.assertTrue(report["inputSent"])
        self.assertEqual(2, query.call_count)
        session_factory.assert_called_once_with(config, vm)
        self.assertEqual([identity_session, identity_session],
                         [call.args[1] for call in query.call_args_list])
        pressed = [item[1] for item in client.events if item[0] == "press"]
        self.assertEqual(["enter"], pressed)
        self.assertEqual([("text", command)], [item for item in client.events if item[0] == "text"])
        released = [item[1] for item in client.events if item[0] == "up"]
        self.assertTrue({"enter", "esc", "shift", "ctrl", "alt", "super", "a"}.issubset(released))
        self.assertTrue(report["releaseSucceeded"])
        self.assertEqual(2, review_check.call_count)

    def test_execute_failure_releases_client_before_identity_session_closes(self):
        for failure in ("send", "capture"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                timeline = []

                class TrackedClient(self.Client):
                    def disconnect(inner_self):
                        timeline.append("client-disconnect")
                        super().disconnect()

                class TrackedSession:
                    def __enter__(inner_self):
                        timeline.append("session-enter")
                        return inner_self

                    def __exit__(inner_self, *_args):
                        timeline.append("session-exit")

                output = Path(folder)
                config, plan_path, review_path, game, vm, _, client = \
                    self.normal_execution_fixture(output, TrackedClient())

                def fake_capture(_client, destination):
                    if failure == "capture" and destination.name == "after-screen.png":
                        raise RuntimeError("fixture capture failure")
                    destination.write_bytes(b"after")
                    return 800, 600

                send = (mock.Mock(side_effect=RuntimeError("fixture send failure"))
                        if failure == "send" else mock.Mock())
                actual_game = {key: game[key] for key in game if key != "lab"}
                with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                        mock.patch.object(module, "collect_identity", return_value=vm), \
                        mock.patch.object(module, "game_identity_session", return_value=TrackedSession()), \
                        mock.patch.object(module, "query_game_identity_in_session", return_value=actual_game), \
                        mock.patch.object(module, "connect", return_value=client), \
                        mock.patch.object(module, "_capture", side_effect=fake_capture), \
                        mock.patch.object(module, "_send_operation", send), \
                        mock.patch.object(module.time, "sleep"), \
                        self.assertRaisesRegex(module.Blocked, "console-operation-failed"):
                    module.execute(config, plan_path, review_path)

                sidecar = json.loads((output / "execution-timings.json").read_text())
                phases = [e["phase"] for e in sidecar["events"]]
                self.assertIn("input", phases)
                self.assertNotIn("fixture", json.dumps(sidecar))
                self.assertLess(timeline.index("client-disconnect"), timeline.index("session-exit"))
                self.assertTrue(any(event[0] == "up" for event in client.events))

    def test_execute_preinput_rejection_closes_session_without_sending_input(self):
        for rejection in ("stale-review", "game-drift"):
            with self.subTest(rejection=rejection), tempfile.TemporaryDirectory() as folder:
                timeline = []

                class TrackedSession:
                    def __enter__(inner_self):
                        timeline.append("session-enter")
                        return inner_self

                    def __exit__(inner_self, *_args):
                        timeline.append("session-exit")

                output = Path(folder)
                config, plan_path, review_path, game, vm, _, client = \
                    self.normal_execution_fixture(output)
                actual_game = {key: game[key] for key in game if key != "lab"}
                if rejection == "game-drift":
                    actual_game = dict(actual_game)
                    actual_game["processStartUtcTicks"] -= 1
                review_effect = ([None, module.Blocked("stale-review-capture")]
                                 if rejection == "stale-review" else None)
                with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                        mock.patch.object(module, "collect_identity", return_value=vm), \
                        mock.patch.object(module, "game_identity_session", return_value=TrackedSession()), \
                        mock.patch.object(module, "query_game_identity_in_session", return_value=actual_game), \
                        mock.patch.object(module, "connect", return_value=client) as connect_client, \
                        mock.patch.object(module, "validate_review", side_effect=review_effect) if review_effect else __import__("contextlib").nullcontext(), \
                        self.assertRaises(module.Blocked):
                    module.execute(config, plan_path, review_path)

                self.assertEqual(["session-enter", "session-exit"], timeline)
                self.assertFalse(any(event[0] in ("press", "mousePress") for event in client.events))
                if rejection == "game-drift":
                    connect_client.assert_not_called()

    def test_normal_prepare_queries_game_once_before_capture(self):
        game = module.validate_expected_game("lab2", 55, 639288075394270241, "d" * 64)
        actual_game = {key: game[key] for key in game if key != "lab"}
        vm = {"vmwarePid": 99, "vmwareStartUtc": "epoch"}
        client = self.Client()
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "prepared"
            config = module.Config(Path("lab.vmx"), 5906, Path("vmrun.exe"), output)
            order = []

            def fake_capture(_client, destination):
                order.append("capture")
                destination.write_bytes(b"screen")
                return 1211, 757

            def fake_query(*_args):
                order.append("game")
                return actual_game

            def fake_verify(*_args):
                order.append("vm")
                return vm

            with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                    mock.patch.object(module, "collect_identity", return_value=vm), \
                    mock.patch.object(module, "verify_identity", side_effect=fake_verify) as verify, \
                    mock.patch.object(module, "query_game_identity", side_effect=fake_query) as query, \
                    mock.patch.object(module, "connect", return_value=client), \
                    mock.patch.object(module, "_capture", side_effect=fake_capture):
                plan = module.prepare(config, "/rr2guide status", None, game)
            sidecar = json.loads((output / "prepare-timings.json").read_text())
            self.assertEqual([e["phase"] for e in sidecar["events"]],
                             ["vm-identity-before", "game-identity", "vnc-connect-initiate",
                              "screen-capture", "vm-identity-after"])
            self.assertNotIn("rr2guide", json.dumps(sidecar))

        self.assertEqual(1, query.call_count)
        verify.assert_called_once_with(config, vm)
        self.assertEqual(["game", "capture", "vm"], order)
        self.assertEqual({"type": "command", "command": "/rr2guide status"}, plan["operation"])

    def test_timing_output_failure_does_not_mask_operation_or_delay_release(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            config, plan_path, review_path, game, vm, _, client = self.normal_execution_fixture(output)
            actual_game = {key: game[key] for key in game if key != "lab"}
            with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                 mock.patch.object(module, "collect_identity", return_value=vm), \
                 mock.patch.object(module, "game_identity_session", return_value=__import__("contextlib").nullcontext(object())), \
                 mock.patch.object(module, "query_game_identity_in_session", return_value=actual_game), \
                 mock.patch.object(module, "connect", return_value=client), \
                 mock.patch.object(module, "_send_operation", side_effect=RuntimeError("secret-error")), \
                 mock.patch.object(module._PhaseTimings, "publish", side_effect=OSError("timing-output-error")), \
                 self.assertRaisesRegex(module.Blocked, "console-operation-failed"):
                module.execute(config, plan_path, review_path)
            self.assertTrue(any(event[0] == "up" for event in client.events))
            self.assertEqual(json.loads((output / "execution.json").read_text())["reason"], "console-operation-failed")

    def test_timing_interrupt_does_not_send_and_releases_connected_client(self):
        from contextlib import nullcontext
        for interrupt_at, cancellation in ((8, KeyboardInterrupt), (8, SystemExit),
                                           (9, KeyboardInterrupt), (9, SystemExit)):
            # Connect completion and immediately before input.
            with self.subTest(interrupt_at=interrupt_at, cancellation=cancellation), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)
                config, plan_path, review_path, game, vm, _, client = self.normal_execution_fixture(output)
                actual = {key: game[key] for key in game if key != "lab"}
                calls = []
                def clock():
                    calls.append(None)
                    if len(calls) == interrupt_at:
                        raise cancellation()
                    return len(calls)
                with mock.patch.object(module, "ControlMutex", return_value=nullcontext()), \
                     mock.patch.object(module, "collect_identity", return_value=vm), \
                     mock.patch.object(module, "game_identity_session", return_value=nullcontext(object())), \
                     mock.patch.object(module, "query_game_identity_in_session", return_value=actual), \
                     mock.patch.object(module, "connect", return_value=client), \
                     mock.patch.object(module, "_send_operation") as send, \
                     mock.patch.object(module.time, "monotonic_ns", side_effect=clock), \
                     self.assertRaisesRegex(module.Blocked, "console-operation-failed"):
                    module.execute(config, plan_path, review_path)
                receipt = json.loads((output / "execution.json").read_text())
                self.assertFalse(receipt["inputSent"])
                send.assert_not_called()
                self.assertTrue(any(event[0] == "up" for event in client.events))
                self.assertIn(("disconnect",), client.events)

    def test_end_clock_interrupt_after_input_records_attempt_and_blocks_retry(self):
        from contextlib import nullcontext
        for cancellation in (KeyboardInterrupt, SystemExit):
            with self.subTest(cancellation=cancellation), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)
                config, plan_path, review_path, game, vm, _, client = self.normal_execution_fixture(output)
                actual = {key: game[key] for key in game if key != "lab"}
                ticks = []
                def clock():
                    ticks.append(None)
                    if len(ticks) == 10:
                        raise cancellation()
                    return len(ticks)
                with mock.patch.object(module, "ControlMutex", return_value=nullcontext()), \
                     mock.patch.object(module, "collect_identity", return_value=vm), \
                     mock.patch.object(module, "game_identity_session", return_value=nullcontext(object())), \
                     mock.patch.object(module, "query_game_identity_in_session", return_value=actual), \
                     mock.patch.object(module, "connect", return_value=client), \
                     mock.patch.object(module, "_send_operation") as send, \
                     mock.patch.object(module.time, "monotonic_ns", side_effect=clock):
                    with self.assertRaisesRegex(module.Blocked, "console-operation-failed"):
                        module.execute(config, plan_path, review_path)
                    receipt = json.loads((output / "execution.json").read_text())
                    self.assertEqual(receipt["status"], "blocked")
                    self.assertTrue(receipt["inputMayHaveBeenSent"])
                    self.assertTrue(receipt["inputSent"])
                    self.assertTrue(receipt["releaseSucceeded"])
                    self.assertIn(("disconnect",), client.events)
                    with self.assertRaisesRegex(module.Blocked, "operation-already-attempted"):
                        module.execute(config, plan_path, review_path)
                    send.assert_called_once()

    def test_phase_end_cancellation_propagates_even_during_handled_outer_error(self):
        timing = module._PhaseTimings(Path("unused"), "execution")
        try:
            raise ValueError("handled")
        except ValueError:
            with mock.patch.object(module.time, "monotonic_ns", side_effect=[1, KeyboardInterrupt()]):
                with self.assertRaises(KeyboardInterrupt):
                    timing.call("input", lambda: None)

    def test_timing_busy_mutex_does_not_publish_sidecar(self):
        from contextlib import contextmanager
        @contextmanager
        def busy():
            raise module.Blocked("mutex-busy")
            yield
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            config, plan_path, review_path, *_ = self.normal_execution_fixture(output)
            with mock.patch.object(module, "ControlMutex", return_value=busy()), \
                 self.assertRaisesRegex(module.Blocked, "mutex-busy"):
                module.execute(config, plan_path, review_path)
            self.assertFalse((output / "execution-timings.json").exists())

    def test_timing_directory_replacement_refuses_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "owned"
            output.mkdir()
            timing = module._PhaseTimings(output, "prepare")
            timing.activate()
            output.rename(Path(folder) / "old")
            output.mkdir()
            timing.publish()
            self.assertFalse((output / "prepare-timings.json").exists())

    def test_timing_end_clock_interrupt_does_not_mask_existing_error(self):
        timing = module._PhaseTimings(Path("unused"), "execution")
        with mock.patch.object(module.time, "monotonic_ns", side_effect=[1, KeyboardInterrupt()]):
            with self.assertRaisesRegex(ValueError, "original-error"):
                timing.call("input", mock.Mock(side_effect=ValueError("original-error")))

    def test_timing_publish_cancel_preserves_prior_error(self):
        from types import SimpleNamespace
        @module._with_timings("prepare")
        def fake(config, *, _timing):
            raise ValueError("original-error")
        with mock.patch.object(module._PhaseTimings, "publish", side_effect=KeyboardInterrupt()):
            with self.assertRaisesRegex(ValueError, "original-error"):
                fake(SimpleNamespace(output=Path("unused")))
        @module._with_timings("prepare")
        def succeeded(config, *, _timing):
            return 1
        with mock.patch.object(module._PhaseTimings, "publish", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                succeeded(SimpleNamespace(output=Path("unused")))

    def test_timing_clock_failure_preserves_operation_result(self):
        timing = module._PhaseTimings(Path("unused"), "execution")
        with mock.patch.object(module.time, "monotonic_ns", side_effect=RuntimeError("clock failure")):
            self.assertEqual(timing.call("input", lambda: "original-result"), "original-result")
            with self.assertRaisesRegex(ValueError, "original-error"):
                timing.call("release", mock.Mock(side_effect=ValueError("original-error")))
        self.assertEqual(timing.events, [])

    def test_prepare_capture_failure_records_partial_phases_after_disconnect(self):
        game = module.validate_expected_game("lab2", 55, 639288075394270241, "d" * 64)
        actual_game = {key: game[key] for key in game if key != "lab"}
        vm = {"vmwarePid": 99, "vmwareStartUtc": "epoch"}
        client = self.Client()
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "prepared"
            config = module.Config(Path("lab.vmx"), 5906, Path("vmrun.exe"), output)
            with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                 mock.patch.object(module, "collect_identity", return_value=vm), \
                 mock.patch.object(module, "query_game_identity", return_value=actual_game), \
                 mock.patch.object(module, "connect", return_value=client), \
                 mock.patch.object(module, "_capture", side_effect=ValueError("original capture error")), \
                 self.assertRaisesRegex(ValueError, "original capture error"):
                module.prepare(config, "/rr2guide status", None, game)
            self.assertIn(("disconnect",), client.events)
            phases = [e["phase"] for e in json.loads((output / "prepare-timings.json").read_text())["events"]]
            self.assertEqual(phases, ["vm-identity-before", "game-identity", "vnc-connect-initiate", "screen-capture"])

    def test_release_failure_is_reported(self):
        client = self.Client(fail_release=True)
        self.assertFalse(module._release_keys(client, "/reloadui"))
        self.assertIn(("up", "enter"), client.events)

    def test_ui_steps_send_exactly_one_key(self):
        for step, expected in (("open-chat", "enter"), ("close-ui", "esc")):
            client = self.Client()
            module._send_operation(client, {"type": "ui-step", "step": step}, "")
            with self.subTest(step=step):
                self.assertEqual([("press", expected)], client.events)

    def test_hide_addon_sends_one_left_click_and_requires_mouse_release(self):
        operation = {"type": "ui-step", "step": "hide-addon", "frame": "casting",
                     "x": 1015, "y": 236, "screenWidth": 1211, "screenHeight": 757}
        client = self.Client()
        module._send_operation(client, operation, "")
        self.assertEqual([("move", 1015, 236), ("mousePress", 1)], client.events)
        self.assertTrue(module._release_operation(client, "", operation))
        self.assertIn(("mouseUp", 1), client.events)
        self.assertFalse(module._release_operation(self.Client(fail_release=True), "", operation))

    def test_deferred_result_types_generated_command_then_enter(self):
        client = self.Client()
        operation = {"type": "deferred-result"}
        command = "/rr2guide result lab2 " + "a" * 32 + " 1 2 3 4 p 1 2 3 5 3 4 0"
        with mock.patch.object(module, "_type_text",
                               side_effect=lambda _client, value: client.events.append(("text", value))):
            module._send_operation(client, operation, command)
        self.assertEqual([("text", command), ("press", "enter")], client.events)

    def test_execute_rejects_stale_game_before_connect(self):
        # The one-tick exact-start mismatch is the important fail-closed boundary.
        expected = module.validate_expected_game("lab2", 55, 639288075394270241, "d" * 64)
        actual = dict(expected)
        actual.pop("lab")
        actual["processStartUtcTicks"] -= 1
        with self.assertRaisesRegex(module.Blocked, "game-identity-drift"):
            module._require_game(actual, expected)


class FastResultTests(unittest.TestCase):
    nonce = "1" * 32

    def fixture(self, folder):
        now = datetime.now(timezone.utc)
        receipt = {
            "schemaVersion": 1, "receiverInstance": "receiver-1",
            "receivedAtUtc": (now - timedelta(milliseconds=50)).isoformat(),
            "receivedMonotonicNs": __import__("time").monotonic_ns() - 50_000_000,
            "sourceAddress": "192.168.56.129",
            "gameReady": False, "note": "Delivery only",
            "observation": {
                "schemaVersion": 1, "instanceId": "11111111-2222-4333-8444-555555555555", "nonce": self.nonce,
                "sequence": 9, "capturedAtUtc": (now - timedelta(milliseconds=100)).strftime("%Y-%m-%dT%H:%M:%S.%f0Z"),
                "monotonicMilliseconds": 1000.0, "readerStatus": "running", "readerReason": None,
                "target": {"processId": 2700, "processStartUtcTicks": 639288075394270241,
                           "executablePath": r"C:\RIFT\rift_x64.exe",
                           "executableSha256": "A" * 64, "readerSessionNonce": self.nonce},
                "riftReader2": {"schemaVersion": 1, "bindingStatus": "bound", "freshnessStatus": "fresh", "reason": None,
                    "lastAdvanceAgeMilliseconds": 100, "freshnessTimeoutMilliseconds": 5000,
                    "remainingFreshMilliseconds": 4900, "selectionStatus": "selected",
                    "scanStartedAtTimestamp": 100, "publishedAtTimestamp": 200,
                    "lastAdvanceAtTimestamp": 190, "envelopeSha256": "B" * 64,
                    "addonFrameSha256": "C" * 64, "candidateSequence": 12, "candidateEpoch": 3,
                    "scan": {"completed": True, "status": "complete", "plannedBytes": 1000,
                             "scannedBytes": 1000, "regionCount": 3, "elapsedMilliseconds": 25,
                             "endpointCandidateCount": 2, "malformedCandidateCount": 0,
                             "matchingCandidateCount": 1, "identicalCopyCount": 1, "reason": None},
                    "observation": {"schemaVersion": 1, "addonVersion": "0.1.0",
                        "sequence": 12, "epoch": 3,
                        "clock": {"status": "ok", "value": 123.5},
                        "player": {"status": "ok", "value": "u123_ABC"},
                        "fields": {"coordX": {"status": "ok", "value": 10},
                                   "coordY": {"status": "ok", "value": 2},
                                   "coordZ": {"status": "ok", "value": 20},
                                   "health": {"status": "ok", "value": 100},
                                   "healthMax": {"status": "ok", "value": 100},
                                   "combat": {"status": "ok", "value": False}}}},
                "delivery": {"enabled": True}, "nativePower": {"status": "unavailable"}
            }}
        path = Path(folder) / "latest.json"
        data = json.dumps(receipt).encode()
        path.write_bytes(data)
        pin = {"schemaVersion": 1, "lab": "lab2", "vmIdentity": {"vm": 1},
               "gameIdentity": {"processId": 2700, "processStartUtcTicks": 639288075394270241,
                                "executablePath": r"C:\RIFT\rift_x64.exe", "executableSha256": "A" * 64},
               "reader": {"processId": 11392, "processStartUtcTicks": 639288297024623618,
                          "executableSha256": "b" * 64, "instanceId": "11111111-2222-4333-8444-555555555555",
                          "nonce": self.nonce, "sourceAddress": "192.168.56.129"},
               "receiver": {"instanceId": "receiver-1", "processId": 24144,
                            "processStartUtcTicks": 639288285817563480,
                            "executablePath": r"C:\Python\python.exe", "executableSha256": "c" * 64,
                            "endpoint": "192.168.56.1:49712"},
               "receiptPath": str(path), "receiptSha256": __import__("hashlib").sha256(data).hexdigest()}
        command = (f"/rr2guide result lab2 {self.nonce} 1 3 12 123.5 u123_ABC "
                   "10 2 20 5 3 4 0")
        return pin, receipt, command

    def calculator(self):
        directory = ROOT / "src" / "RiftReader2.Cli" / "bin" / "Release" / "net10.0"
        dotnet = Path(shutil.which("dotnet"))
        return {"dotnetPath": str(dotnet), "dotnetSha256": module._sha(dotnet),
                "directory": str(directory),
                "files": {name: module._sha(directory / name) for name in module.CALCULATOR_FILES}}

    def intent(self, pin, receipt):
        selected = receipt["observation"]["riftReader2"]["observation"]
        return {"schemaVersion": 1, "lab": "lab2", "nonce": pin["reader"]["nonce"],
                "resultSequence": 7, "destination": {"x": 13, "y": 2, "z": 24},
                "seed": {"player": selected["player"]["value"], "epoch": selected["epoch"],
                         "x": 10, "y": 2, "z": 20}, "calculator": self.calculator()}

    def post_receipt(self, source, input_sent_at):
        current = json.loads(json.dumps(source))
        current["receivedAtUtc"] = (input_sent_at + timedelta(milliseconds=350)).isoformat()
        current["receivedMonotonicNs"] = __import__("time").monotonic_ns() - 10_000_000
        current["observation"]["sequence"] += 1
        current["observation"]["capturedAtUtc"] = (input_sent_at + timedelta(milliseconds=300)).isoformat()
        selected = current["observation"]["riftReader2"]["observation"]
        selected["sequence"] += 1
        selected["clock"]["value"] += 0.5
        return current

    def test_post_input_receipt_accepts_strictly_new_fresh_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, source, _ = self.fixture(folder)
            sent = datetime.now(timezone.utc) - timedelta(milliseconds=500)
            source["observation"]["capturedAtUtc"] = (sent - timedelta(milliseconds=100)).isoformat()
            current = self.post_receipt(source, sent)
            data = json.dumps(current).encode()
            with mock.patch.object(module, "_fast_receipt", side_effect=[
                    module.Blocked("live-receipt-not-fresh"),
                    (current, data, {"status": "fresh"}),
            ]), mock.patch.object(module.time, "sleep"):
                actual, actual_bytes, gate = module._post_input_receipt(pin, source, sent, 1)
            self.assertEqual((current, data, "fresh"), (actual, actual_bytes, gate["status"]))

    def test_post_input_receipt_stale_until_deadline_times_out(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, source, _ = self.fixture(folder)
            sent = datetime.now(timezone.utc) - timedelta(milliseconds=500)
            source["observation"]["capturedAtUtc"] = (sent - timedelta(milliseconds=100)).isoformat()
            with mock.patch.object(module, "_fast_receipt",
                                   side_effect=module.Blocked("live-receipt-not-fresh")), \
                    self.assertRaisesRegex(module.Blocked, "post-input-receipt-timeout"):
                module._post_input_receipt(pin, source, sent, 0)

    def test_post_input_receipt_identity_failure_is_immediate(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, source, _ = self.fixture(folder)
            sent = datetime.now(timezone.utc) - timedelta(milliseconds=500)
            source["observation"]["capturedAtUtc"] = (sent - timedelta(milliseconds=100)).isoformat()
            with mock.patch.object(module, "_fast_receipt",
                                   side_effect=module.Blocked("live-target-identity-mismatch")) as read, \
                    self.assertRaisesRegex(module.Blocked, "live-target-identity-mismatch"):
                module._post_input_receipt(pin, source, sent, 4)
            read.assert_called_once_with(pin, initial=False)

    def test_post_input_receipt_rejects_nonadvancing_or_preinput_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, source, _ = self.fixture(folder)
            sent = datetime.now(timezone.utc) - timedelta(milliseconds=500)
            source["observation"]["capturedAtUtc"] = (sent - timedelta(milliseconds=100)).isoformat()
            for mutation in ("outer", "received", "captured"):
                current = self.post_receipt(source, sent)
                if mutation == "outer":
                    current["observation"]["sequence"] = source["observation"]["sequence"]
                elif mutation == "received":
                    current["receivedAtUtc"] = (sent - timedelta(milliseconds=1)).isoformat()
                else:
                    current["observation"]["capturedAtUtc"] = (sent + timedelta(milliseconds=249)).isoformat()
                with self.subTest(mutation=mutation), \
                        mock.patch.object(module, "_fast_receipt", return_value=(current, b"x", {})), \
                        self.assertRaisesRegex(module.Blocked, "post-input-receipt-timeout"):
                    module._post_input_receipt(pin, source, sent, 0)

    def test_post_input_receipt_rejects_continuity_or_origin_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, source, _ = self.fixture(folder)
            sent = datetime.now(timezone.utc) - timedelta(milliseconds=500)
            source["observation"]["capturedAtUtc"] = (sent - timedelta(milliseconds=100)).isoformat()
            for mutation in ("epoch", "origin"):
                current = self.post_receipt(source, sent)
                selected = current["observation"]["riftReader2"]["observation"]
                if mutation == "epoch":
                    selected["epoch"] += 1
                else:
                    selected["fields"]["coordX"]["value"] += 0.500001
                reason = "continuity-lost" if mutation == "epoch" else "position-changed"
                with self.subTest(mutation=mutation), \
                        mock.patch.object(module, "_fast_receipt", return_value=(current, b"x", {})), \
                        self.assertRaisesRegex(module.Blocked, reason):
                    module._post_input_receipt(pin, source, sent, 0)

    def test_fast_execute_uses_post_receipt_not_post_input_guestops(self):
        now = datetime.now(timezone.utc)
        vm = {"vmwarePid": 99, "vmwareStartUtc": "epoch"}
        client = ExecuteTests.Client()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            pin, receipt, command = self.fixture(folder)
            pin["vmIdentity"] = vm
            screen = output / "review-screen.png"
            screen.write_bytes(b"reviewed screen")
            snapshot = json.dumps(receipt["observation"], ensure_ascii=True,
                                  sort_keys=True, separators=(",", ":")).encode("ascii")
            receipt_bytes = json.dumps(receipt).encode()
            (output / "source-receipt.json").write_bytes(receipt_bytes)
            (output / "source-snapshot.json").write_bytes(snapshot)
            game = {"lab": "lab2", **{key: pin["gameIdentity"][key] for key in
                    ("processId", "processStartUtcTicks", "executableSha256")}}
            source = {"sourcePin": pin,
                      "receiptSha256": __import__("hashlib").sha256(receipt_bytes).hexdigest(),
                      "snapshotSha256": __import__("hashlib").sha256(snapshot).hexdigest()}
            plan = {"schemaVersion": 1, "captureId": "e" * 32,
                    "capturedAtUtc": (now - timedelta(seconds=2)).isoformat(),
                    "screen": str(screen), "screenSha256": module._sha(screen),
                    "operation": {"type": "command", "command": command},
                    "vmIdentity": vm, "gameIdentity": game, "fastResultSource": source}
            plan["planSha256"] = module._plan_sha(plan)
            plan_path = output / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            review = {"schemaVersion": 1, "captureId": plan["captureId"],
                      "screenSha256": plan["screenSha256"], "reviewedAtUtc": now.isoformat(),
                      "planSha256": plan["planSha256"], "decision": "approved",
                      "gameForeground": True, "textEntryClosed": False,
                      "chatEntryOpen": True, "chatEntryEmpty": True,
                      "chatEntryFocused": True, "panelOpen": False,
                      "soleControllerIdle": True, "knownControllerIdle": True,
                      "queueIdle": True, "reviewer": "root-agent", "note": "reviewed"}
            review_path = output / "review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            post = self.post_receipt(receipt, now - timedelta(seconds=1))
            post_bytes = json.dumps(post).encode()
            config = module.Config(Path("lab.vmx"), 5905, Path("vmrun.exe"), output)

            def fake_capture(_client, destination):
                destination.write_bytes(b"after")
                return 800, 600

            send_completed = []

            def fake_send(*_args):
                send_completed.append(datetime.now(timezone.utc))

            with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                    mock.patch.object(module, "collect_identity", return_value=vm), \
                    mock.patch.object(module, "verify_identity", return_value=vm) as verify, \
                    mock.patch.object(module, "query_game_identity") as query, \
                    mock.patch.object(module, "connect", return_value=client), \
                    mock.patch.object(module, "_capture", side_effect=fake_capture), \
                    mock.patch.object(module, "_send_operation", side_effect=fake_send), \
                    mock.patch.object(module, "_fast_receipt", return_value=(receipt, receipt_bytes, {})), \
                    mock.patch.object(module, "_post_input_receipt", return_value=(post, post_bytes, {})) as post_check, \
                    mock.patch.object(module, "_fast_age"), mock.patch.object(module.time, "sleep"):
                report = module.execute(config, plan_path, review_path)

            self.assertEqual("completed", report["status"])
            query.assert_not_called()
            verify.assert_called_once_with(config, vm)
            post_check.assert_called_once()
            input_sent_at = post_check.call_args.args[2]
            self.assertGreaterEqual(input_sent_at, send_completed[0])
            self.assertEqual(
                input_sent_at,
                datetime.fromisoformat(report["inputSentAtUtc"].replace("Z", "+00:00")),
            )
            saved = output / "post-input-source-receipt.json"
            self.assertEqual(post_bytes, saved.read_bytes())
            self.assertEqual(module._sha(saved), report["postInputReceipt"]["sha256"])

    def test_exact_result_matches_authenticated_source(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt, command = self.fixture(folder)
            module._require_result_matches(command, pin, receipt)
            with mock.patch.object(module, "_validate_receiver_host"):
                loaded, _, _ = module._fast_receipt(pin, initial=True)
            self.assertEqual("11111111-2222-4333-8444-555555555555", loaded["observation"]["instanceId"])

    def test_full_gate_allows_but_does_not_consume_additive_fast_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt, _ = self.fixture(folder)
            receipt["observation"]["fastObservation"] = {"untrustedByFullGate": True}
            receipt["observation"]["fastObservationDiagnostic"] = {
                "status": "rejected", "reason": "candidate-region-scope-too-large"}
            data = json.dumps(receipt).encode()
            Path(pin["receiptPath"]).write_bytes(data)
            pin["receiptSha256"] = module.hashlib.sha256(data).hexdigest()
            with mock.patch.object(module, "_validate_receiver_host"):
                loaded, _, gate = module._fast_receipt(pin, initial=True)
            self.assertEqual("fresh", gate["status"])
            self.assertEqual({"untrustedByFullGate": True},
                             loaded["observation"]["fastObservation"])
            self.assertEqual("rejected",
                             loaded["observation"]["fastObservationDiagnostic"]["status"])

    def test_deferred_calculation_uses_pinned_cli_and_current_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt, _ = self.fixture(folder)
            intent = self.intent(pin, receipt)
            output = Path(folder) / "output"
            output.mkdir()
            frozen = module._freeze_calculator(intent["calculator"], output)
            module._require_seed(intent, pin, receipt)
            command, evidence = module._calculate_deferred(intent, pin, receipt, output, frozen)
            self.assertEqual(
                f"/rr2guide result lab2 {self.nonce} 7 3 12 123.5 u123_ABC 10 2 20 5 3 4 0",
                command)
            self.assertEqual(module._sha(output / "deferred-guidance-report.json"),
                             evidence["reportSha256"])

    def test_deferred_seed_rejects_player_epoch_or_origin_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt, _ = self.fixture(folder)
            intent = self.intent(pin, receipt)
            for field, value in (("player", "other"), ("epoch", 4), ("x", 10.6)):
                changed = json.loads(json.dumps(intent))
                changed["seed"][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(
                        module.Blocked, "seed-mismatch"):
                    module._require_seed(changed, pin, receipt)

    def test_deferred_seed_exact_prepare_and_half_unit_execution_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt, _ = self.fixture(folder)
            intent = self.intent(pin, receipt)
            changed = json.loads(json.dumps(receipt))
            changed["observation"]["riftReader2"]["observation"]["fields"]["coordX"]["value"] = 10.1
            with self.assertRaisesRegex(module.Blocked, "seed-mismatch"):
                module._require_seed(intent, pin, changed, exact_origin=True)
            changed["observation"]["riftReader2"]["observation"]["fields"]["coordX"]["value"] = 10.5
            module._require_seed(intent, pin, changed)
            changed["observation"]["riftReader2"]["observation"]["fields"]["coordX"]["value"] = 10.500001
            with self.assertRaisesRegex(module.Blocked, "seed-mismatch"):
                module._require_seed(intent, pin, changed)

    def test_final_origin_must_match_actual_calculation_source(self):
        with tempfile.TemporaryDirectory() as folder:
            _, receipt, _ = self.fixture(folder)
            current = json.loads(json.dumps(receipt))
            current["observation"]["riftReader2"]["observation"]["fields"]["coordX"]["value"] = 10.6
            with self.assertRaisesRegex(module.Blocked, "position-changed"):
                module._require_origin_near(receipt, current)

    def test_result_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt, command = self.fixture(folder)
            for changed in (command.replace(" 12 123.5 ", " 13 123.5 "),
                            command.replace(self.nonce, "2" * 32)):
                with self.subTest(changed=changed), self.assertRaises(module.Blocked):
                    module._require_result_matches(changed, pin, receipt)

    def test_stale_original_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            _, receipt, _ = self.fixture(folder)
            receipt["receivedMonotonicNs"] -= 9_000_000_000
            with self.assertRaisesRegex(module.Blocked, "fast-result-source-expired"):
                module._fast_age(receipt)

    def test_near_timeout_inner_source_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            _, receipt, _ = self.fixture(folder)
            receipt["observation"]["riftReader2"]["lastAdvanceAgeMilliseconds"] = 7900
            with self.assertRaisesRegex(module.Blocked, "fast-result-source-expired"):
                module._fast_age(receipt)

    def test_reload_player_and_replay_regression_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            _, frozen, _ = self.fixture(folder)
            for mutate in (
                lambda current: current["observation"]["riftReader2"]["observation"].update(epoch=4),
                lambda current: current["observation"]["riftReader2"]["observation"]["player"].update(value="other"),
                lambda current: current["observation"]["riftReader2"]["observation"].update(sequence=11),
                lambda current: current["observation"]["riftReader2"]["observation"]["clock"].update(value=122.0),
            ):
                current = json.loads(json.dumps(frozen))
                mutate(current)
                with self.subTest(mutate=mutate), self.assertRaisesRegex(
                        module.Blocked, "continuity-lost"):
                    module._require_continuity(frozen, current)

    def test_terminated_or_live_fork_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, receipt, _ = self.fixture(folder)
            for mutation in ("terminated", "fork"):
                changed = json.loads(json.dumps(receipt))
                if mutation == "terminated":
                    changed["observation"]["readerStatus"] = "terminated"
                else:
                    changed["observation"]["instanceId"] = "reader-2"
                data = json.dumps(changed).encode()
                Path(pin["receiptPath"]).write_bytes(data)
                candidate = dict(pin, receiptSha256=__import__("hashlib").sha256(data).hexdigest())
                with mock.patch.object(module, "_validate_receiver_host"), self.assertRaises(module.Blocked):
                    module._fast_receipt(candidate, initial=True)

    def test_receipt_byte_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            pin, _, _ = self.fixture(folder)
            Path(pin["receiptPath"]).write_text("{}", encoding="utf-8")
            with mock.patch.object(module, "_validate_receiver_host"), \
                    self.assertRaisesRegex(module.Blocked, "sha256-mismatch"):
                module._fast_receipt(pin, initial=True)

    def test_native_receiver_identity_and_listener_pin(self):
        receiver = {"instanceId": "receiver-1", "processId": 24144,
                    "processStartUtcTicks": 639288285817563485,
                    "executablePath": r"C:\Python314\python.exe",
                    "executableSha256": "0" * 64, "endpoint": "192.168.56.1:49712"}
        native = {"pid": 24144, "image": r"C:\Python314\python.exe",
                  "startTicks": 134377053817563485}
        with mock.patch.object(module, "_receiver_listener_owner", return_value=24144), \
                mock.patch.object(module, "process_identity", side_effect=[native, native]) as identity, \
                mock.patch.object(module, "_sha", return_value="0" * 64):
            module._validate_receiver_host(receiver)
        self.assertEqual(2, identity.call_count)

    def test_native_listener_requires_one_exact_private_address_row(self):
        self.assertEqual(24144, module._select_receiver_listener(
            [("192.168.56.1", 24144)], "192.168.56.1"))
        for rows in ([("127.0.0.1", 24144)], [("192.168.56.1", 99),
                    ("127.0.0.1", 24144)], []):
            with self.subTest(rows=rows), self.assertRaisesRegex(
                    module.Blocked, "not-unique"):
                module._select_receiver_listener(rows, "192.168.56.1")

    def test_native_listener_table_accepts_passive_state_metadata(self):
        def row(state, address, port, pid):
            return struct.pack(
                "<6I", state, struct.unpack("<I", socket.inet_aton(address))[0],
                socket.htons(port), 0, 0, pid)

        table = struct.pack("<I", 2)
        table += row(0, "192.168.56.1", 49712, 40940)
        table += row(2, "127.0.0.1", 49713, 99)

        self.assertEqual(
            [("192.168.56.1", 40940)],
            module._parse_receiver_listener_rows(table, 49712),
        )

    def test_native_receiver_rejects_owner_hash_and_process_drift(self):
        receiver = {"instanceId": "receiver-1", "processId": 24144,
                    "processStartUtcTicks": 639288285817563485,
                    "executablePath": r"C:\Python314\python.exe",
                    "executableSha256": "0" * 64, "endpoint": "192.168.56.1:49712"}
        native = {"pid": 24144, "image": r"C:\Python314\python.exe",
                  "startTicks": 134377053817563485}
        with mock.patch.object(module, "_receiver_listener_owner", return_value=99), \
                self.assertRaisesRegex(module.Blocked, "identity-mismatch"):
            module._validate_receiver_host(receiver)
        with mock.patch.object(module, "_receiver_listener_owner", return_value=24144), \
                mock.patch.object(module, "process_identity", side_effect=[native, native]), \
                mock.patch.object(module, "_sha", return_value="f" * 64), \
                self.assertRaisesRegex(module.Blocked, "identity-mismatch"):
            module._validate_receiver_host(receiver)
        changed = dict(native, startTicks=native["startTicks"] + 1)
        with mock.patch.object(module, "_receiver_listener_owner", return_value=24144), \
                mock.patch.object(module, "process_identity", side_effect=[native, changed]), \
                mock.patch.object(module, "_sha", return_value="0" * 64), \
                self.assertRaisesRegex(module.Blocked, "identity-mismatch"):
            module._validate_receiver_host(receiver)
        for changed_receiver in (
            dict(receiver, processStartUtcTicks=receiver["processStartUtcTicks"] + 1),
            dict(receiver, executablePath=r"C:\Other\python.exe"),
        ):
            with mock.patch.object(module, "_receiver_listener_owner", return_value=24144), \
                    mock.patch.object(module, "process_identity", side_effect=[native, native]), \
                    mock.patch.object(module, "_sha", return_value="0" * 64), \
                    self.assertRaisesRegex(module.Blocked, "identity-mismatch"):
                module._validate_receiver_host(changed_receiver)
        with mock.patch.object(module, "_receiver_listener_owner", side_effect=[24144, 99]), \
                mock.patch.object(module, "process_identity", side_effect=[native, native]), \
                mock.patch.object(module, "_sha", return_value="0" * 64), \
                self.assertRaisesRegex(module.Blocked, "identity-mismatch"):
            module._validate_receiver_host(receiver)


if __name__ == "__main__":
    unittest.main()
