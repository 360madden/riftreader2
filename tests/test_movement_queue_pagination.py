"""Fail-closed queue preflight tests for the reviewed movement runner."""

from contextlib import contextmanager
import unittest
from unittest.mock import patch

import scripts.run_movement_session as runner


RESOURCE = "vm:lab2"


def resource(generation=1):
    return {"name": RESOURCE, "epoch": "epoch-lab2", "generation": generation,
            "blocked": False, "holder": None}


def request(sequence, state="succeeded", resource_name=RESOURCE):
    return {"sequence": sequence, "request_id": f"request-{sequence}", "state": state,
            "specification": {"resources": {resource_name: "epoch"}}}


def pages(second, *, first_resource=None, second_resource=None, cursor=100):
    first = [request(number) for number in range(1, 101)]
    return {
        0: {"resources": [first_resource or resource()], "requests": first,
            "next_sequence": 100},
        100: {"resources": [second_resource or resource()], "requests": second,
              "next_sequence": cursor},
    }


class FakeQueue:
    def __init__(self, page_map, *, other_grant=False, no_grant=False):
        self.page_map = page_map
        self.other_grant = other_grant
        self.no_grant = no_grant
        self.cursors = []
        self.submissions = []
        self.dispatches = 0
        self.dispatch_targets = []
        self.cancellations = []
        self.checks = []

    @contextmanager
    def dispatch_fence(self, timeout):
        self.assert_timeout = timeout
        yield

    def status(self, *, after_sequence=0, limit=100):
        self.cursors.append(after_sequence)
        assert limit == 100
        return self.page_map[after_sequence]

    def submit(self, request_id, *args, **kwargs):
        self.submissions.append(request_id)

    def dispatch(self, *, request_id=None):
        self.dispatches += 1
        self.dispatch_targets.append(request_id)
        if self.no_grant:
            return None
        return {"request_id": "another-request" if self.other_grant
                else self.submissions[-1], "token": "a" * 64}

    def cancel(self, request_id, owner):
        self.cancellations.append((request_id, owner))
        return {"request_id": request_id, "state": "cancelled"}

    def check(self, request_id, token):
        self.checks.append((request_id, token))
        return {"request_id": request_id}

    def finish(self, request_id, token, outcome, evidence):
        return {"request_id": request_id, "state": outcome}


class QueuePaginationTests(unittest.TestCase):
    def acquire(self, queue):
        with patch.object(runner, "AccessQueue", return_value=queue):
            return runner.acquire({"database": "unused-by-fake", "resource": RESOURCE})

    def test_later_page_same_lab_pending_is_rejected(self):
        queue = FakeQueue(pages([request(101, "queued")], cursor=None))
        with self.assertRaisesRegex(runner.MovementSessionError, "pending work"):
            self.acquire(queue)
        self.assertEqual(queue.cursors, [0, 100])
        self.assertEqual(queue.submissions, [])
        self.assertEqual(queue.dispatches, 0)

    def test_later_page_other_lab_pending_is_not_global_blocker(self):
        queue = FakeQueue(pages([request(101, "active", "vm:lab1")], cursor=None))
        lease, grant = self.acquire(queue)
        self.assertEqual(queue.cursors, [0, 100])
        self.assertEqual(lease.request_id, grant["request_id"])
        self.assertEqual(queue.checks, [(grant["request_id"], "a" * 64)])

    def test_later_page_cleanup_same_lab_is_rejected(self):
        queue = FakeQueue(pages([request(101, "cleanup")], cursor=None))
        with self.assertRaisesRegex(runner.MovementSessionError, "pending work"):
            self.acquire(queue)
        self.assertEqual(queue.dispatches, 0)

    def test_repeated_cursor_is_rejected(self):
        queue = FakeQueue(pages([request(101)], cursor=100))
        with self.assertRaisesRegex(runner.MovementSessionError, "pagination stalled"):
            self.acquire(queue)
        self.assertEqual(queue.dispatches, 0)

    def test_empty_page_with_continuation_is_rejected(self):
        queue = FakeQueue(pages([], cursor=101))
        with self.assertRaisesRegex(runner.MovementSessionError, "pagination stalled"):
            self.acquire(queue)
        self.assertEqual(queue.dispatches, 0)

    def test_resource_generation_change_is_rejected(self):
        queue = FakeQueue(pages([request(101)], cursor=None,
                                second_resource=resource(generation=2)))
        with self.assertRaisesRegex(runner.MovementSessionError, "resource changed"):
            self.acquire(queue)
        self.assertEqual(queue.dispatches, 0)

    def test_other_request_grant_is_rejected_without_check(self):
        queue = FakeQueue(pages([], cursor=None), other_grant=True)
        with self.assertRaisesRegex(runner.MovementSessionError, "lease unavailable"):
            self.acquire(queue)
        self.assertEqual(queue.dispatches, 1)
        self.assertEqual(queue.dispatch_targets, queue.submissions)
        self.assertEqual(queue.cancellations, [(queue.submissions[0], "movement-session")])
        self.assertEqual(queue.checks, [])

    def test_targeted_dispatch_none_cancels_own_pending_request(self):
        queue = FakeQueue(pages([], cursor=None), no_grant=True)
        with self.assertRaisesRegex(runner.MovementSessionError, "lease unavailable"):
            self.acquire(queue)
        self.assertEqual(queue.dispatch_targets, queue.submissions)
        self.assertEqual(queue.cancellations, [(queue.submissions[0], "movement-session")])
        self.assertEqual(queue.checks, [])

    def test_cleanup_finds_own_completed_request_on_later_page(self):
        completed = request(101)
        completed["request_id"] = "movement-own"
        queue = FakeQueue(pages([completed], cursor=None))
        lease = runner.LiveQueueLease(queue, "movement-own", "a" * 64, RESOURCE)
        self.assertEqual(lease.finish("succeeded", ["test"]), {
            "request_id": "movement-own", "state": "succeeded"})
        self.assertEqual(queue.cursors, [0, 100])

    def test_cleanup_rejects_stalled_pagination(self):
        completed = request(101)
        completed["request_id"] = "movement-own"
        queue = FakeQueue(pages([completed], cursor=100))
        lease = runner.LiveQueueLease(queue, "movement-own", "a" * 64, RESOURCE)
        with self.assertRaisesRegex(runner.MovementSessionError, "cleanup pagination stalled"):
            lease.finish("succeeded", ["test"])

    def test_cleanup_rejects_resource_change(self):
        completed = request(101)
        completed["request_id"] = "movement-own"
        queue = FakeQueue(pages([completed], cursor=None,
                                second_resource=resource(generation=2)))
        lease = runner.LiveQueueLease(queue, "movement-own", "a" * 64, RESOURCE)
        with self.assertRaisesRegex(runner.MovementSessionError, "resource changed"):
            lease.finish("succeeded", ["test"])


if __name__ == "__main__":
    unittest.main()
