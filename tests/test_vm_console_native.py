import importlib.util
import json
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest.mock import patch


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

    def test_tcp_parser_returns_matching_listener_owners(self):
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
