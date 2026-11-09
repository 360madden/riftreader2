import importlib.util
import json
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "vm_console_native.py"
SPEC = importlib.util.spec_from_file_location("vm_console_native", SCRIPT)
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)


def plan(*actions):
    return {"schemaVersion": 1, "actions": list(actions)}


class IdentityParserTests(unittest.TestCase):
    def test_parses_vmware_log_epoch_and_pid(self):
        header = (
            "2026-10-20T10:43:56.803Z In(05) vmx - "
            "Log for VMware Workstation pid=39056 version=17.6\n"
        )
        self.assertEqual(
            console.parse_vmware_log_identity(header),
            ("2026-10-20T10:43:56.803Z", 39056),
        )

    def test_rejects_log_without_identity(self):
        with self.assertRaisesRegex(console.Blocked, "vm-log-identity-unavailable"):
            console.parse_vmware_log_identity("ordinary log line\n")

    def test_vmrun_parser_ignores_heading_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            vmx = Path(directory) / "RIFT-Lab.vmx"
            parsed = console.parse_vmrun_list(
                f"Total running VMs: 1\n\n{vmx}\n"
            )
            self.assertEqual(parsed, [vmx.resolve()])

    def test_tcp_parser_strict_default_returns_only_listen_state_owners(self):
        rows = [
            (2, "127.0.0.1", 5905, 39056),
            (5, "127.0.0.1", 5905, 99),
            (2, "127.0.0.1", 5906, 100),
        ]
        encoded = struct.pack("<I", len(rows))
        for state, ip, port, pid in rows:
            address = struct.unpack("<I", socket.inet_aton(ip))[0]
            encoded += struct.pack(
                "<6I", state, address, socket.htons(port), 0, 0, pid
            )
        self.assertEqual(
            console.parse_tcp_listener_rows(encoded, 5905),
            [("127.0.0.1", 39056)],
        )

    def test_tcp_parser_listener_table_accepts_passive_state_metadata(self):
        address = struct.unpack("<I", socket.inet_aton("127.0.0.1"))[0]
        encoded = struct.pack("<I6I", 1, 1, address, socket.htons(5906), 0, 0, 42160)
        self.assertEqual(
            console.parse_tcp_listener_rows(encoded, 5906, listener_table=True),
            [("127.0.0.1", 42160)],
        )
        self.assertEqual(console.parse_tcp_listener_rows(encoded, 5906), [])

    def test_tcp_parser_rejects_truncated_table(self):
        with self.assertRaisesRegex(console.Blocked, "listener-query-invalid"):
            console.parse_tcp_listener_rows(struct.pack("<I", 1), 5905)

    def test_verify_identity_uses_direct_checks_without_vmrun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = console.validate_config(
                root / "RIFT-Lab.vmx",
                5905,
                root / "VMware" / "vmrun.exe",
                root / "out",
            )
            epoch = "2026-10-20T10:43:56.803Z"
            start_ticks = 134369666367568030
            process = {
                "pid": 39056,
                "image": str((config.vmrun.parent / "x64" / "vmware-vmx.exe").resolve()),
                "startTicks": start_ticks,
            }
            expected = {
                "vmx": console.path_key(config.vmx),
                "port": 5905,
                "logEpoch": epoch,
                "listenerPid": 39056,
                **process,
            }
            binding = ("stable",)
            with (
                patch.object(console, "_binding_files", return_value=binding),
                patch.object(console, "_log_identity", return_value=(epoch, 39056)),
                patch.object(console, "process_identity", return_value=process),
                patch.object(console, "listener_owner", return_value=39056),
                patch.object(console.subprocess, "run") as vmrun,
            ):
                self.assertEqual(console.verify_identity(config, expected), expected)
                vmrun.assert_not_called()

    def test_verify_identity_rejects_changed_pinned_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = console.validate_config(
                root / "RIFT-Lab.vmx",
                5905,
                root / "VMware" / "vmrun.exe",
                root / "out",
            )
            epoch = "2026-10-20T10:43:56.803Z"
            process = {
                "pid": 39056,
                "image": str((config.vmrun.parent / "x64" / "vmware-vmx.exe").resolve()),
                "startTicks": 134369666367568030,
            }
            expected = {
                "vmx": console.path_key(config.vmx),
                "port": 5905,
                "logEpoch": epoch,
                "listenerPid": 39056,
                **process,
            }
            expected["pid"] = 99
            with (
                patch.object(console, "_binding_files", return_value=("stable",)),
                patch.object(console, "_log_identity", return_value=(epoch, 39056)),
                patch.object(console, "process_identity", return_value=process),
                patch.object(console, "listener_owner", return_value=39056),
                patch.object(console.subprocess, "run") as vmrun,
            ):
                with self.assertRaisesRegex(console.Blocked, "target-drift"):
                    console.verify_identity(config, expected)
                vmrun.assert_not_called()


class PathConfigTests(unittest.TestCase):
    def test_config_normalizes_paths_and_accepts_absolute_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = console.validate_config(
                root / "folder" / ".." / "RIFT-Lab.vmx",
                5905,
                root / "VMware" / "vmrun.exe",
                root / "evidence",
            )
            self.assertTrue(config.vmx.is_absolute())
            self.assertEqual(config.vmx.name, "RIFT-Lab.vmx")
            self.assertEqual(config.output, (root / "evidence").resolve())

    def test_config_rejects_invalid_port_and_boolean_port(self):
        for value in (0, 65536, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(console.Blocked, "invalid-console-port"):
                    console.validate_config(
                        Path("lab.vmx"), value, Path("vmrun.exe"), Path("out")
                    )

    def test_config_rejects_wrong_file_kinds(self):
        with self.assertRaisesRegex(console.Blocked, "invalid-vmx-path"):
            console.validate_config(
                Path("lab.txt"), 5905, Path("vmrun.exe"), Path("out")
            )
        with self.assertRaisesRegex(console.Blocked, "invalid-vmrun-path"):
            console.validate_config(
                Path("lab.vmx"), 5905, Path("vmware.exe"), Path("out")
            )

    def test_mutex_name_is_stable_and_does_not_contain_path(self):
        first = console.mutex_name(Path("RIFT-Lab.vmx"))
        second = console.mutex_name(Path("RIFT-Lab.vmx"))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("Local\\RiftReader.VMConsole."))
        self.assertNotIn("lab", first.casefold())

    def test_parser_has_required_cli_shape(self):
        args = console.build_parser().parse_args(
            [
                "--vmx",
                "lab.vmx",
                "--output",
                "out",
                "bootstrap",
                "--actions",
                "actions.json",
            ]
        )
        self.assertEqual(args.port, 5905)
        self.assertEqual(args.command, "bootstrap")
        self.assertEqual(args.actions, Path("actions.json"))


class ControlMutexWaitTests(unittest.TestCase):
    def api(self, outcome):
        api = Mock()
        api.CreateMutexW.return_value = 123
        api.WaitForSingleObject.return_value = outcome
        api.ReleaseMutex.return_value = True
        return api

    def assert_acquired(self, outcome, *, abandoned):
        api = self.api(outcome)
        mutex = console.ControlMutex(Path("mock-only.vmx"))
        with patch.object(console, "_kernel32", return_value=api):
            with mutex as acquired:
                self.assertIs(acquired, mutex)
                self.assertEqual(mutex.handle, 123)
                self.assertIs(mutex.owner_thread, console.threading.current_thread())
                self.assertEqual(mutex.abandoned, abandoned)
                api.CloseHandle.assert_not_called()
                api.ReleaseMutex.assert_not_called()
            api.WaitForSingleObject.assert_called_once_with(123, 0)
            self.assertIs(api.WaitForSingleObject.restype, console.wintypes.DWORD)
            api.ReleaseMutex.assert_called_once_with(123)
            api.CloseHandle.assert_called_once_with(123)
            self.assertIsNone(mutex.handle)

    def assert_blocked(self, outcome, reason):
        api = self.api(outcome)
        mutex = console.ControlMutex(Path("mock-only.vmx"))
        with patch.object(console, "_kernel32", return_value=api):
            with self.assertRaises(console.Blocked) as raised:
                with mutex:
                    self.fail("Unacquired mutex must not admit the body")
        self.assertEqual(str(raised.exception), reason)
        api.WaitForSingleObject.assert_called_once_with(123, 0)
        self.assertIs(api.WaitForSingleObject.restype, console.wintypes.DWORD)
        api.CloseHandle.assert_called_once_with(123)
        api.ReleaseMutex.assert_not_called()
        self.assertIsNone(mutex.handle)
        self.assertIsNone(mutex.owner_thread)
        self.assertFalse(mutex.abandoned)

    def test_acquired_wait_admits_owner(self):
        self.assert_acquired(0, abandoned=False)

    def test_abandoned_wait_admits_owner_and_marks_abandoned(self):
        self.assert_acquired(0x80, abandoned=True)

    def test_timeout_remains_controller_busy(self):
        self.assert_blocked(0x102, "controller-busy")

    def test_wait_failed_has_distinct_nonsecret_reason(self):
        self.assert_blocked(0xFFFFFFFF, "controller-lock-wait-failed")

    def test_unexpected_wait_fails_closed_with_distinct_reason(self):
        self.assert_blocked(0x40, "controller-lock-wait-unexpected")


class VncConnectionCleanupTests(unittest.TestCase):
    class Reactor:
        def __init__(self):
            self.calls = 0

        def callFromThread(self, callback, *args):
            self.calls += 1
            callback(*args)

    class Api:
        class ThreadedVNCClientProxy:
            def __init__(self, factory, timeout=0):
                self.factory = factory
                self.timeout = timeout
                self.protocol = None

    class BaseFactory:
        protocol = None

        def __init__(self):
            self.lost = 0
            self.failed = 0

        def clientConnectionLost(self, connector, reason):
            self.lost += 1

        def clientConnectionFailed(self, connector, reason):
            self.failed += 1

    class BaseClient:
        def connectionMade(self):
            self.made = True

    class ClientModule:
        VNCDoToolFactory = None
        VNCDoToolClient = None

    class Transport:
        def __init__(self, factory):
            self.factory = factory
            self.aborts = 0
            self.graceful = 0

        def abortConnection(self):
            self.aborts += 1
            self.factory.clientConnectionLost(None, "aborted")

        def loseConnection(self):
            self.graceful += 1
            self.factory.clientConnectionLost(None, "closed")

    def types(self):
        reactor = self.Reactor()
        api = type(
            "ApiModule",
            (),
            {
                "ThreadedVNCClientProxy": self.Api.ThreadedVNCClientProxy,
                "reactor": reactor,
            },
        )
        clients = type(
            "ClientModule",
            (),
            {
                "VNCDoToolFactory": self.BaseFactory,
                "VNCDoToolClient": self.BaseClient,
            },
        )
        factory_type, proxy_type = console._vnc_connection_types(api, clients)
        return reactor, factory_type, proxy_type

    def connected(self, factory_type):
        factory = factory_type()
        protocol = factory.protocol()
        protocol.factory = factory
        protocol.transport = self.Transport(factory)
        protocol.connectionMade()
        return factory, protocol

    def test_pre_auth_disconnect_aborts_only_its_raw_transport(self):
        reactor, factory_type, proxy_type = self.types()
        first, first_protocol = self.connected(factory_type)
        second, second_protocol = self.connected(factory_type)
        proxy = proxy_type(first, timeout=0.1)

        proxy.disconnect()

        self.assertEqual(first_protocol.transport.aborts, 1)
        self.assertEqual(first_protocol.transport.graceful, 0)
        self.assertTrue(first._rr2_closed.is_set())
        self.assertEqual(second_protocol.transport.aborts, 0)
        self.assertFalse(second._rr2_closed.is_set())
        self.assertEqual(reactor.calls, 1)

    def test_authenticated_disconnect_is_graceful_and_bounded(self):
        _, factory_type, proxy_type = self.types()
        factory, protocol = self.connected(factory_type)
        proxy = proxy_type(factory, timeout=0.1)
        proxy.protocol = protocol

        proxy.disconnect()

        self.assertEqual(protocol.transport.graceful, 1)
        self.assertEqual(protocol.transport.aborts, 0)
        self.assertTrue(factory._rr2_closed.is_set())

    def test_repeated_disconnect_does_not_close_transport_twice(self):
        _, factory_type, proxy_type = self.types()
        factory, protocol = self.connected(factory_type)
        proxy = proxy_type(factory, timeout=0.1)
        proxy.protocol = protocol

        proxy.disconnect()
        proxy.disconnect()

        self.assertEqual(protocol.transport.graceful, 1)
        self.assertEqual(protocol.transport.aborts, 0)

    def test_disconnect_before_tcp_connection_aborts_when_protocol_arrives(self):
        _, factory_type, proxy_type = self.types()
        factory = factory_type()
        proxy = proxy_type(factory, timeout=0)

        proxy.disconnect()
        protocol = factory.protocol()
        protocol.factory = factory
        protocol.transport = self.Transport(factory)
        protocol.connectionMade()

        self.assertTrue(factory._rr2_close_requested)
        self.assertEqual(protocol.transport.aborts, 1)
        self.assertTrue(factory._rr2_closed.is_set())

    def test_connection_failure_releases_only_that_waiter(self):
        _, factory_type, _ = self.types()
        first = factory_type()
        second = factory_type()

        first.clientConnectionFailed(None, "refused")

        self.assertTrue(first._rr2_closed.is_set())
        self.assertFalse(second._rr2_closed.is_set())
        self.assertEqual(first.failed, 1)


class ActionValidationTests(unittest.TestCase):
    def test_text_keypress_maps_uppercase_to_explicit_shift_chords(self):
        for character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            with self.subTest(character=character):
                self.assertEqual(
                    console.text_keypress(character),
                    "shift-" + character.casefold(),
                )

    def test_text_keypress_maps_all_shifted_ascii_to_base_keys(self):
        expected = {
            "~": "shift-`",
            "!": "shift-1",
            "@": "shift-2",
            "#": "shift-3",
            "$": "shift-4",
            "%": "shift-5",
            "^": "shift-6",
            "&": "shift-7",
            "*": "shift-8",
            "(": "shift-9",
            ")": "shift-0",
            "_": "shift-minus",
            "+": "shift-=",
            "{": "shift-[",
            "}": "shift-]",
            "|": "shift-\\",
            ":": "shift-;",
            '"': "shift-'",
            "<": "shift-,",
            ">": "shift-.",
            "?": "shift-/",
        }
        self.assertEqual(console.SHIFTED_ASCII_BASE.keys(), expected.keys())
        for character, keypress in expected.items():
            with self.subTest(character=character):
                self.assertEqual(console.text_keypress(character), keypress)

    def test_type_text_uses_mapped_keypresses_without_live_input(self):
        class FakeClient:
            def __init__(self):
                self.keys = []

            def keyPress(self, key):
                self.keys.append(key)

        client = FakeClient()
        console._type_text(client, "Az_')\"")
        self.assertEqual(
            client.keys,
            ["shift-a", "z", "shift-minus", "'", "shift-0", "shift-'"],
        )

    def test_text_keypress_maps_literal_minus_to_named_base_key(self):
        self.assertEqual(console.text_keypress("-"), "minus")

    def test_accepts_atomic_windows_run_text(self):
        actions = console.validate_actions(
            plan({"type": "windowsRunText", "text": "powershell -NoProfile"})
        )
        self.assertEqual(actions[0]["type"], "windowsRunText")

    def test_accepts_explicit_run_text_submit_and_bounded_click(self):
        actions = console.validate_actions(
            plan(
                {"type": "keyChord", "keys": ["super", "r"]},
                {"type": "text", "text": "cmd /c ver"},
                {"type": "keyPress", "key": "enter"},
                {"type": "click", "x": 1279, "y": 719, "button": 1},
                {"type": "keyChord", "keys": ["alt", "tab"]},
                {"type": "keyPress", "key": "esc"},
            ),
            (1280, 720),
        )
        self.assertEqual(len(actions), 6)

    def test_text_requires_explicit_windows_run_open(self):
        with self.assertRaisesRegex(
            console.Blocked, "bootstrap-text-requires-windows-run"
        ):
            console.validate_actions(plan({"type": "text", "text": "whoami"}))

    def test_text_cannot_follow_focus_changing_action(self):
        with self.assertRaisesRegex(
            console.Blocked, "bootstrap-text-requires-windows-run"
        ):
            console.validate_actions(
                plan(
                    {"type": "keyChord", "keys": ["super", "r"]},
                    {"type": "keyChord", "keys": ["alt", "tab"]},
                    {"type": "text", "text": "whoami"},
                )
            )

    def test_rejects_movement_and_arbitrary_keys(self):
        cases = [
            {"type": "keyPress", "key": "w"},
            {"type": "keyPress", "key": "a"},
            {"type": "keyChord", "keys": ["ctrl", "c"]},
            {"type": "keyChord", "keys": ["super", "d"]},
        ]
        for action in cases:
            with self.subTest(action=action):
                with self.assertRaises(console.Blocked):
                    console.validate_actions(plan(action))

    def test_rejects_control_unicode_and_oversize_text(self):
        for value in ("line1\nline2", "snowman \u2603", "x" * 2049):
            with self.subTest(value=value[:20]):
                with self.assertRaisesRegex(console.Blocked, "invalid-bootstrap-text"):
                    console.validate_actions(
                        plan({"type": "windowsRunText", "text": value})
                    )

    def test_rejects_click_outside_current_screen(self):
        for x, y in ((1280, 0), (0, 720), (-1, 0), (0, -1)):
            with self.subTest(x=x, y=y):
                with self.assertRaisesRegex(console.Blocked, "invalid-bootstrap-click"):
                    console.validate_actions(
                        plan({"type": "click", "x": x, "y": y, "button": 1}),
                        (1280, 720),
                    )

    def test_rejects_extra_fields_and_non_left_click(self):
        with self.assertRaisesRegex(console.Blocked, "invalid-bootstrap-action-fields"):
            console.validate_actions(
                plan({"type": "keyPress", "key": "enter", "hold": 1})
            )
        with self.assertRaisesRegex(console.Blocked, "invalid-bootstrap-click"):
            console.validate_actions(
                plan({"type": "click", "x": 1, "y": 1, "button": 2})
            )
        with self.assertRaisesRegex(console.Blocked, "invalid-bootstrap-click"):
            console.validate_actions(
                plan({"type": "click", "x": 1, "y": 1, "button": True})
            )

    def test_rejects_boolean_schema_version(self):
        with self.assertRaisesRegex(console.Blocked, "unsupported-bootstrap-schema"):
            console.validate_actions(
                {
                    "schemaVersion": True,
                    "actions": [{"type": "keyPress", "key": "esc"}],
                }
            )

    def test_rejects_empty_or_excessive_action_list(self):
        with self.assertRaisesRegex(console.Blocked, "invalid-bootstrap-actions"):
            console.validate_actions(plan())
        with self.assertRaisesRegex(console.Blocked, "invalid-bootstrap-actions"):
            console.validate_actions(
                plan(*({"type": "keyPress", "key": "esc"} for _ in range(33)))
            )

    def test_load_actions_parses_valid_json_without_executing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            path.write_text(
                json.dumps(plan({"type": "keyPress", "key": "esc"})),
                encoding="utf-8",
            )
            self.assertEqual(console.load_actions(path)[0]["key"], "esc")


if __name__ == "__main__":
    unittest.main()
