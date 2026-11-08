import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.hold_review_lease import ReviewLeaseError, hold_review_lease
from scripts.nav_access_queue import QueueError


class Clock:
    def __init__(self):
        self.seconds = 0.0

    def monotonic(self):
        return self.seconds

    def wall_ms(self):
        return int(self.seconds * 1000)

    def sleep(self, seconds):
        self.seconds += seconds


class FakeQueue:
    def __init__(self, database, *, end_after=None):
        self.database = database
        self.end_after = end_after
        self.calls = []
        self.record = {"request_id": "movement-123", "state": "active",
                       "deadline_ms": 120000, "expires_ms": 30000,
                       "lease": {"vm:lab-1": {"epoch": "epoch", "generation": 3}}}

    def check(self, request_id, token):
        self.calls.append(("check", request_id, token))
        return dict(self.record)

    def heartbeat(self, request_id, token):
        self.calls.append(("heartbeat", request_id, token))
        count = sum(call[0] == "heartbeat" for call in self.calls)
        if self.end_after is not None and count > self.end_after:
            self.record["state"] = "succeeded"
            raise QueueError("lease is not active or token does not match")
        return {"request_id": request_id, "expires_ms": 30000,
                "deadline_ms": self.record["deadline_ms"]}

    def status(self, **_):
        self.calls.append(("status",))
        return {"requests": [dict(self.record)], "next_sequence": None}

    def __getattr__(self, name):
        if name in ("finish", "cancel"):
            raise AssertionError(f"helper must not call {name}")
        raise AttributeError(name)


class HoldReviewLeaseTests(unittest.TestCase):
    def test_direct_script_help_imports_project_package(self):
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "hold_review_lease.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--help"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--session-plan", result.stdout)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def fixture(self):
        database = self.root / "queue.sqlite3"; database.write_bytes(b"fixture")
        host = self.write("host.json", {"database": str(database)})
        host_sha = hashlib.sha256(host.read_bytes()).hexdigest().upper()
        grant = self.write("grant.private.json",
                           {"request_id": "movement-123", "token": "a" * 64})
        session = self.write("session.json", {"schemaVersion": 1,
            "evidenceKind": "reviewed-movement-session/1",
            "hostPlan": str(host), "hostPlanSha256": host_sha,
            "privateGrant": str(grant), "lease": {"request_id": "movement-123",
                "deadline_ms": 120000,
                "lease": {"vm:lab-1": {"epoch": "epoch", "generation": 3}}}})
        return session

    def test_bounded_hold_only_checks_and_heartbeats(self):
        session = self.fixture(); clock = Clock(); queues = []
        def factory(database):
            queue = FakeQueue(database); queues.append(queue); return queue
        result = hold_review_lease(session, interval_seconds=8, max_seconds=20,
            queue_factory=factory, monotonic=clock.monotonic,
            wall_ms=clock.wall_ms, sleep=clock.sleep)
        self.assertEqual(result["reason"], "bounded-window-ended")
        self.assertEqual(result["heartbeats"], 3)
        self.assertEqual(result["heldSeconds"], 20)
        self.assertEqual([call[0] for call in queues[0].calls],
                         ["check", "heartbeat", "heartbeat", "heartbeat"])
        self.assertNotIn("a" * 64, json.dumps(result))

    def test_owner_completion_stops_without_finish_or_cancel(self):
        session = self.fixture(); clock = Clock(); queues = []
        def factory(database):
            queue = FakeQueue(database, end_after=2); queues.append(queue); return queue
        result = hold_review_lease(session, interval_seconds=8, max_seconds=40,
            queue_factory=factory, monotonic=clock.monotonic,
            wall_ms=clock.wall_ms, sleep=clock.sleep)
        self.assertEqual(result["reason"], "lease-ended-by-owner-or-queue")
        self.assertEqual(result["heartbeats"], 2)
        self.assertEqual([call[0] for call in queues[0].calls],
                         ["check", "heartbeat", "heartbeat", "heartbeat", "status"])

    def test_absolute_deadline_shortens_local_window(self):
        session = self.fixture(); clock = Clock(); clock.seconds = 115
        result = hold_review_lease(session, interval_seconds=8, max_seconds=110,
            queue_factory=FakeQueue, monotonic=clock.monotonic,
            wall_ms=clock.wall_ms, sleep=clock.sleep)
        self.assertEqual(result["heldSeconds"], 4)
        self.assertEqual(result["heartbeats"], 1)

    def test_changed_host_pin_or_private_grant_is_rejected(self):
        session = self.fixture()
        value = json.loads(session.read_text())
        value["hostPlanSha256"] = "0" * 64
        session.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ReviewLeaseError, "host plan pin changed"):
            hold_review_lease(session, queue_factory=FakeQueue)
        session = self.fixture(); value = json.loads(session.read_text())
        grant = Path(value["privateGrant"])
        grant.write_text(json.dumps({"request_id": "foreign", "token": "b" * 64}),
                         encoding="utf-8")
        with self.assertRaisesRegex(ReviewLeaseError, "differs from session"):
            hold_review_lease(session, queue_factory=FakeQueue)

    def test_invalid_intervals_are_rejected_before_queue_access(self):
        session = self.fixture()
        for interval, maximum in ((0, 20), (16, 20), (8, 0), (8, 111)):
            with self.subTest(interval=interval, maximum=maximum):
                with self.assertRaises(ReviewLeaseError):
                    hold_review_lease(session, interval_seconds=interval,
                                      max_seconds=maximum, queue_factory=FakeQueue)


if __name__ == "__main__":
    unittest.main()
