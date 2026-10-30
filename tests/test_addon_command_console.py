import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import json
import socket
import shutil
import struct


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "addon_command_console", ROOT / "scripts" / "addon_command_console.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class AddonCommandValidationTests(unittest.TestCase):
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

            with mock.patch.object(module, "ControlMutex", return_value=__import__("contextlib").nullcontext()), \
                    mock.patch.object(module, "collect_identity", return_value=vm), \
                    mock.patch.object(module, "verify_identity", return_value=vm), \
                    mock.patch.object(module, "query_game_identity", return_value={k: game[k] for k in game if k != "lab"}) as query, \
                    mock.patch.object(module, "connect", return_value=client), \
                    mock.patch.object(module, "_capture", side_effect=fake_capture), \
                    mock.patch.object(module, "_type_text", side_effect=lambda _client, value: client.events.append(("text", value))), \
                    mock.patch.object(module, "validate_review", wraps=module.validate_review) as review_check, \
                    mock.patch.object(module.time, "sleep"):
                report = module.execute(config, plan_path, review_path)

        self.assertEqual("completed", report["status"])
        self.assertTrue(report["inputSent"])
        self.assertEqual(2, query.call_count)
        pressed = [item[1] for item in client.events if item[0] == "press"]
        self.assertEqual(["enter"], pressed)
        self.assertEqual([("text", command)], [item for item in client.events if item[0] == "text"])
        released = [item[1] for item in client.events if item[0] == "up"]
        self.assertTrue({"enter", "esc", "shift", "ctrl", "alt", "super", "a"}.issubset(released))
        self.assertTrue(report["releaseSucceeded"])
        self.assertEqual(2, review_check.call_count)

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

        self.assertEqual(1, query.call_count)
        verify.assert_called_once_with(config, vm)
        self.assertEqual(["game", "capture", "vm"], order)
        self.assertEqual({"type": "command", "command": "/rr2guide status"}, plan["operation"])

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
