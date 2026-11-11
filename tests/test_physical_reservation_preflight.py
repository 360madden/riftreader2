"""Read-only physical-client reservation preflight; synthetic PID and selector."""
import contextlib
import io
import json
import os
import socket
import unittest
from unittest.mock import patch

from scripts import physical_reservation_preflight as probe
from scripts.nav_physical_reservation import (
    PhysicalClientIdentity, PhysicalClientReservation, PhysicalReservationError,
)


HOST = socket.gethostname()
PID = 1876544  # A synthetic PID; these tests never inspect a live game.
TICKS = 639299470183328173
SHA = "a" * 64
TARGET = {
    "hostName": HOST, "processId": PID,
    "processStartUtcTicks": str(TICKS), "executableSha256": SHA,
    "executablePath": r"C:\RIFT\rift_x64.exe", "hwnd": 0,
}


def ready(**changes):
    return {"status": "ready", "workflow": "physical", "ownerHost": HOST,
            "target": {**TARGET, **changes}}


@unittest.skipUnless(os.name == "nt", "Windows physical reservation only")
class ReadOnlyPhysicalPreflightTests(unittest.TestCase):
    def test_stable_target_owns_and_releases_reservation(self):
        calls = []
        def selector(**kwargs):
            calls.append(kwargs)
            return ready()
        receipt = probe.preflight(HOST, PID, selector=selector)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls, [{"expected_host": HOST, "physical_pid": PID}] * 3)
        self.assertEqual(receipt["status"], "verified-read-only")
        self.assertEqual(receipt["recordType"], "physical-reservation-preflight/1")
        self.assertEqual(receipt["identity"]["processId"], PID)
        self.assertEqual(receipt["identity"]["processStartUtcTicks"], str(TICKS))
        self.assertEqual(receipt["reservation"], "acquired-and-released")
        self.assertIs(receipt["movementEligible"], False)
        self.assertIs(receipt["gameInputSent"], False)
        self.assertIs(receipt["controlAgentStarted"], False)
        identity = PhysicalClientIdentity(HOST, PID, TICKS, SHA)
        with PhysicalClientReservation(identity, lambda: identity):
            pass

    def test_absent_or_ambiguous_process_fails_before_mutex(self):
        for reason in ("not-running", "ambiguous-process"):
            def selector(**_):
                return {"status": "blocked", "reason": reason}
            with self.subTest(reason=reason), self.assertRaisesRegex(
                    probe.PhysicalPreflightError, reason):
                probe.preflight(HOST, PID, selector=selector)

    def test_invalid_or_cross_host_request_fails_before_selection(self):
        def no_select(**_):
            self.fail("selector must not be called")
        for host, pid in (("OTHER-HOST", PID), (HOST, 0), (HOST, True)):
            with self.subTest(host=host, pid=pid), self.assertRaises(
                    probe.PhysicalPreflightError):
                probe.preflight(host, pid, selector=no_select)

    def test_wrong_pid_executable_or_host_is_rejected(self):
        for changes in (
            {"processId": PID + 1},
            {"executablePath": r"C:\Other\other.exe"},
            {"hostName": "OTHER-HOST"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                    probe.PhysicalPreflightError):
                probe.selected_identity(ready(**changes), HOST, PID)

    def test_changed_identity_under_reservation_refuses_and_releases(self):
        for field, value in (("processStartUtcTicks", str(TICKS + 1)),
                             ("executableSha256", "b" * 64),
                             ("processId", PID + 1)):
            calls = 0
            def selector(**_):
                nonlocal calls
                calls += 1
                return ready() if calls == 1 else ready(**{field: value})
            with self.subTest(field=field), self.assertRaises(
                    (PhysicalReservationError, probe.PhysicalPreflightError)):
                probe.preflight(HOST, PID, selector=selector)
            self.assertEqual(probe.preflight(HOST, PID, selector=lambda **_: ready())["status"],
                             "verified-read-only")

    def test_second_lease_owner_blocks_preflight(self):
        identity = PhysicalClientIdentity(HOST, PID, TICKS, SHA)
        with PhysicalClientReservation(identity, lambda: identity):
            with self.assertRaisesRegex(PhysicalReservationError, "physical-reservation-busy"):
                probe.preflight(HOST, PID, selector=lambda **_: ready())

    def test_cli_emits_one_json_result_and_blocked_exit(self):
        ok = {"status": "verified-read-only", "identity": {"processId": PID}}
        with patch.object(probe, "preflight", return_value=ok):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(probe.main(["--host", HOST, "--pid", str(PID)]), 0)
            self.assertEqual(json.loads(output.getvalue()), ok)
        with patch.object(probe, "preflight", side_effect=probe.PhysicalPreflightError("not-running")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(probe.main(["--host", HOST, "--pid", str(PID)]), 2)
            self.assertEqual(json.loads(output.getvalue())["reason"], "not-running")


if __name__ == "__main__":
    unittest.main()
