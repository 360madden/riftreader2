"""Offline Windows physical client reservation tests; fake PID, no RIFT access."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import unittest

from scripts.nav_physical_reservation import (
    PhysicalClientIdentity, PhysicalClientReservation, PhysicalReservationError,
    mutex_name,
)


MACHINE = socket.gethostname()
PID = 1876543  # A synthetic PID; no process is opened.
TICKS = 639299470183328173
SHA = "a" * 64
EXPECTED = PhysicalClientIdentity(MACHINE, PID, TICKS, SHA)
CHILD = """
import sys
from scripts.nav_physical_reservation import (
    PhysicalClientIdentity, PhysicalClientReservation, PhysicalReservationError)
identity = PhysicalClientIdentity(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
try:
    with PhysicalClientReservation(identity, lambda: identity):
        print("acquired", flush=True)
except PhysicalReservationError as error:
    print(str(error), flush=True)
"""


@unittest.skipUnless(os.name == "nt", "Windows named mutex only")
class PhysicalReservationTests(unittest.TestCase):
    def child_attempt(self):
        completed = subprocess.run(
            [sys.executable, "-B", "-c", CHILD, MACHINE, str(PID), str(TICKS), SHA],
            cwd=Path(__file__).resolve().parents[1], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
        self.assertEqual(completed.stderr, "")
        return completed.stdout.strip()

    def test_exact_identity_is_required_and_host_is_local(self):
        changes = [
            dict(machine_name="NOT-THIS-HOST"),
            dict(process_id=True),
            dict(process_id=0),
            dict(process_start_utc_ticks=0),
            dict(executable_sha256="A" * 64),
            dict(executable_sha256="g" * 64),
        ]
        for change in changes:
            candidate = {**EXPECTED.__dict__, **change}
            with self.subTest(change=change), self.assertRaises(PhysicalReservationError):
                identity = PhysicalClientIdentity(**candidate)
                PhysicalClientReservation(identity, lambda: identity)
        self.assertTrue(mutex_name(EXPECTED).startswith("Local\\RiftReader2.PhysicalClient."))

    def test_name_uses_host_pid_and_epoch_not_sha(self):
        other_build = PhysicalClientIdentity(MACHINE, PID, TICKS, "b" * 64)
        other_epoch = PhysicalClientIdentity(MACHINE, PID, TICKS + 1, SHA)
        other_pid = PhysicalClientIdentity(MACHINE, PID + 1, TICKS, SHA)
        self.assertEqual(mutex_name(EXPECTED), mutex_name(other_build))
        self.assertNotEqual(mutex_name(EXPECTED), mutex_name(other_epoch))
        self.assertNotEqual(mutex_name(EXPECTED), mutex_name(other_pid))

    def test_duplicate_same_process_and_second_process_refused_then_released(self):
        first = PhysicalClientReservation(EXPECTED, lambda: EXPECTED)
        second = PhysicalClientReservation(EXPECTED, lambda: EXPECTED)
        with first:
            self.assertTrue(first.held)
            self.assertEqual(first.check(), EXPECTED)
            with self.assertRaisesRegex(PhysicalReservationError, "physical-reservation-busy"):
                with second:
                    self.fail("duplicate reservation admitted")
            self.assertEqual(self.child_attempt(), "physical-reservation-busy")
        self.assertFalse(first.held)
        self.assertEqual(self.child_attempt(), "acquired")

    def test_context_releases_on_exception(self):
        with self.assertRaisesRegex(RuntimeError, "test interruption"):
            with PhysicalClientReservation(EXPECTED, lambda: EXPECTED):
                raise RuntimeError("test interruption")
        with PhysicalClientReservation(EXPECTED, lambda: EXPECTED) as resumed:
            self.assertTrue(resumed.held)

    def test_identity_rechecked_before_entry_and_on_demand(self):
        wrong = PhysicalClientIdentity(MACHINE, PID, TICKS + 1, SHA)
        with self.assertRaisesRegex(PhysicalReservationError, "identity-changed"):
            with PhysicalClientReservation(EXPECTED, lambda: wrong):
                self.fail("stale identity admitted")
        samples = [EXPECTED, wrong]
        with PhysicalClientReservation(EXPECTED, lambda: samples.pop(0)) as lease:
            with self.assertRaisesRegex(PhysicalReservationError, "identity-changed"):
                lease.check()
            self.assertTrue(lease.held)
        with PhysicalClientReservation(EXPECTED, lambda: EXPECTED):
            pass

    def test_revalidation_failure_releases_and_no_callback_misuse(self):
        def unavailable():
            raise OSError("fake observation lost")
        with self.assertRaisesRegex(PhysicalReservationError, "identity-unavailable"):
            with PhysicalClientReservation(EXPECTED, unavailable):
                self.fail("unavailable identity admitted")
        with PhysicalClientReservation(EXPECTED, lambda: EXPECTED):
            pass
        with self.assertRaisesRegex(PhysicalReservationError, "arguments-invalid"):
            PhysicalClientReservation(EXPECTED, None)

    def test_wrong_thread_cannot_release(self):
        errors = []
        with PhysicalClientReservation(EXPECTED, lambda: EXPECTED) as lease:
            worker = threading.Thread(target=lambda: self._attempt_wrong_thread(lease, errors))
            worker.start()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, ["physical-reservation-wrong-thread"])
            self.assertTrue(lease.held)

    @staticmethod
    def _attempt_wrong_thread(lease, errors):
        try:
            lease.release()
        except PhysicalReservationError as error:
            errors.append(str(error))


if __name__ == "__main__":
    unittest.main()
