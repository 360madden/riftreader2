import unittest
from scripts.waypoint_connection import idle_read


class Adapter:
    def __init__(self, pid, result):
        self.pid = pid
        self.target = {"processStartUtcTicks": "100"}
        self.result = result

    def read(self, **kwargs):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ReconnectionTests(unittest.TestCase):
    def setUp(self):
        self.old = Adapter(1, ValueError("read unavailable"))
        self.new = Adapter(2, "fresh pose")
        self.selected = []

    def selector(self, host, pid):
        self.selected.append((host, pid))
        return {"status": "ready", "target": {"processId": 2}}

    def read(self, *, alive=False, selector=None, factory=None, auto=True):
        return idle_read(self.old, "AMD-DESKTOP", "basis", selector or self.selector,
                         factory or (lambda *args: self.new), auto_reconnect=auto,
                         alive=lambda *args: alive)

    def test_dead_process_reconnects_after_fresh_pose(self):
        adapter, pose, changed = self.read()
        self.assertIs(adapter, self.new)
        self.assertEqual((pose, changed), ("fresh pose", True))
        self.assertEqual(self.selected, [("AMD-DESKTOP", None)])

    def test_live_process_read_failure_never_switches(self):
        with self.assertRaisesRegex(ValueError, "read unavailable"):
            self.read(alive=True)
        self.assertFalse(self.selected)

    def test_explicit_pid_does_not_reconnect(self):
        with self.assertRaisesRegex(ValueError, "read unavailable"):
            self.read(auto=False)
        self.assertFalse(self.selected)

    def test_ambiguous_or_absent_selection_is_rejected(self):
        for reason in ("ambiguous", "absent"):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                self.read(selector=lambda *args: {"status": "blocked", "reason": reason})

    def test_factory_identity_refusal_propagates(self):
        def reject(*args):
            raise ValueError("different build or player")
        with self.assertRaisesRegex(ValueError, "different build or player"):
            self.read(factory=reject)

    def test_unavailable_new_pose_is_not_published(self):
        self.new.result = ValueError("new pose unavailable")
        with self.assertRaisesRegex(ValueError, "new pose unavailable"):
            self.read()


if __name__ == "__main__":
    unittest.main()
