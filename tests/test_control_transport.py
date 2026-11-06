"""Disposable TCP transport tests; no live VM or game input."""
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tests.test_control_host import host


class ObservedSocket:
    """Delegate real I/O, with narrow optional send faults in this test only."""
    def __init__(self, sock):
        self.sock = sock
        self.send_entered = threading.Event()
        self.calls = 0
        self.sent = 0
        self.chunk = None
        self.fail_after = None
        self.zero = False
        self.interrupt_once = False
        self.delay = 0

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def sendall(self, data):
        self.send_entered.set()
        self.calls += 1
        return self.sock.sendall(data)

    def send(self, data):
        self.send_entered.set()
        self.calls += 1
        if self.interrupt_once:
            self.interrupt_once = False
            raise InterruptedError()
        if self.zero:
            return 0
        if self.fail_after is not None and self.sent >= self.fail_after:
            raise OSError("PRIVATE_FAULT_PAYLOAD")
        if self.delay:
            time.sleep(self.delay)
        count = self.sock.send(data[:self.chunk] if self.chunk else data)
        self.sent += count
        return count


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.journal = host.EvidenceJournal(Path(self.temporary.name))
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0)); listener.listen(1)
        self.peer = socket.create_connection(listener.getsockname(), timeout=2)
        accepted, _ = listener.accept(); listener.close()
        accepted.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        self.peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        self.socket = ObservedSocket(accepted)
        self.closed_notices = []
        self.session = host.AgentSession(self.socket, "127.0.0.1", {
            "instanceId": "test-instance", "machineName": "TEST-GUEST"},
            self.journal, lambda value: self.closed_notices.append(value))
        self.session.start()
        self.stream = self.peer.makefile("rb")
        self.workers = []
        self.addCleanup(self.finish)

    def finish(self):
        self.session.close()
        try:
            self.peer.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.stream.close(); self.peer.close()
        self.session._reader.join(2)
        for thread, _ in self.workers:
            thread.join(3)
            self.assertFalse(thread.is_alive(), "private request worker leaked")
        self.assertFalse(self.session._reader.is_alive(), "private receive worker leaked")

    def launch(self, operation="status", payload=None, *, access=None):
        result = {}
        def invoke():
            try:
                result["value"] = self.session.request(operation, payload or {}, access=access)
            except Exception as error:
                result["error"] = error
        thread = threading.Thread(target=invoke)
        self.workers.append((thread, result)); thread.start()
        return thread, result

    def respond(self, command, payload=None):
        self.peer.sendall(host.encode_frame({"type": "response", "id": command["id"],
                                             "payload": payload or {"ok": True}}))

    def settled(self, worker, seconds=2):
        thread, result = worker
        thread.join(seconds)
        self.assertFalse(thread.is_alive(), "request did not settle within test bound")
        return result

    def error(self, worker):
        result = self.settled(worker)
        self.assertIsInstance(result.get("error"), host.ControlHostError, result)
        return str(result["error"])

    def wait_closed(self):
        end = time.monotonic() + 2
        while not self.session.closed and time.monotonic() < end:
            time.sleep(.005)
        self.assertTrue(self.session.closed)

    def test_nonreading_peer_cannot_hold_send_indefinitely(self):
        with patch.object(host, "SEND_TIMEOUT_SECONDS", .15, create=True):
            worker = self.launch("action", {"testPadding": "x" * (4 * 1024 * 1024)})
            self.assertTrue(self.socket.send_entered.wait(1))
            message = self.error(worker)
        self.assertIn("send", message)
        self.assertIn("uncertain", message)
        self.assertTrue(self.session.closed)
        self.assertEqual(self.session._pending, {})
        self.assertTrue(self.session.wait_controls_idle(.2))
        self.assertTrue(self.session._send_lock.acquire(blocking=False))
        self.session._send_lock.release()

    def test_stop_waiting_behind_stall_fails_without_fabricated_release(self):
        with patch.object(host, "SEND_TIMEOUT_SECONDS", .15, create=True):
            action = self.launch("action", {"testPadding": "x" * (4 * 1024 * 1024)})
            self.assertTrue(self.socket.send_entered.wait(1))
            stop = self.launch("stop")
            self.error(action); self.error(stop)
        self.assertTrue(self.session.closed)
        self.assertNotIn("value", stop[1])
        self.assertEqual(self.session._sequence, 1)

    def test_partial_failure_closes_stream_instead_of_replaying_frame(self):
        self.socket.chunk = 13; self.socket.fail_after = 13
        message = self.error(self.launch("status"))
        self.assertEqual(self.socket.sent, 13)
        self.assertTrue(self.session.closed)
        self.assertNotIn("PRIVATE_FAULT_PAYLOAD", message)
        calls = self.socket.calls
        self.error(self.launch("status"))
        self.assertEqual(self.socket.calls, calls)

    def test_zero_byte_send_is_terminal_not_spin(self):
        self.socket.zero = True
        self.error(self.launch("status"))
        self.assertEqual(self.socket.calls, 1)
        self.assertTrue(self.session.closed)

    def test_short_writes_preserve_exact_frame_and_response(self):
        self.socket.chunk = 7
        worker = self.launch("status", {"unicode": "ü 世界"})
        command = host.read_frame(self.stream)
        self.assertEqual(command["payload"], {"unicode": "ü 世界"})
        self.respond(command)
        self.assertEqual(self.settled(worker)["value"], {"ok": True})
        self.assertGreater(self.socket.calls, 2)
        self.assertFalse(self.session.closed)

    def test_interrupted_send_retries_only_remaining_transport_bytes(self):
        self.socket.interrupt_once = True; self.socket.chunk = 19
        worker = self.launch()
        command = host.read_frame(self.stream); self.respond(command)
        self.assertEqual(self.settled(worker)["value"], {"ok": True})
        self.assertEqual(self.session._sequence, 1)

    def test_progress_does_not_reset_total_send_deadline(self):
        self.socket.chunk = 1; self.socket.delay = .02
        with patch.object(host, "SEND_TIMEOUT_SECONDS", .08, create=True):
            self.error(self.launch("status"))
        self.assertTrue(0 < self.socket.sent < 100)
        self.assertTrue(self.session.closed)

    def test_send_lock_wait_is_bounded_and_closes_uncertain_transport(self):
        with patch.object(host, "SEND_TIMEOUT_SECONDS", .08, create=True):
            with self.session._send_lock:
                worker = self.launch("status")
                self.error(worker)
        self.assertEqual(self.socket.calls, 0)
        self.assertTrue(self.session.closed)

    def test_external_close_settles_stalled_sender_and_reader(self):
        worker = self.launch("action", {"testPadding": "x" * (4 * 1024 * 1024)})
        self.assertTrue(self.socket.send_entered.wait(1))
        self.session.close()
        self.error(worker)
        self.session._reader.join(1)
        self.assertFalse(self.session._reader.is_alive())

    def test_suspended_idle_read_can_be_closed_promptly(self):
        self.session.close()
        self.session._reader.join(1)
        self.assertFalse(self.session._reader.is_alive())
        self.assertFalse(self.session.summary()["connected"])

    def test_fragmented_response_is_reassembled(self):
        worker = self.launch(); command = host.read_frame(self.stream)
        frame = host.encode_frame({"type": "response", "id": command["id"], "payload": {"text": "ü 世界"}})
        for byte in frame:
            self.peer.sendall(bytes([byte]))
        self.assertEqual(self.settled(worker)["value"], {"text": "ü 世界"})

    def test_two_coalesced_responses_are_not_lost(self):
        one = self.launch(); first = host.read_frame(self.stream)
        two = self.launch(); second = host.read_frame(self.stream)
        data = b"".join(host.encode_frame({"type": "response", "id": c["id"],
                                         "payload": {"sequence": c["sequence"]}}) for c in (second, first))
        self.peer.sendall(data)
        self.assertEqual(self.settled(one)["value"], {"sequence": 1})
        self.assertEqual(self.settled(two)["value"], {"sequence": 2})

    def test_concurrent_senders_do_not_interleave_frames(self):
        self.socket.chunk = 3
        workers = [self.launch("status", {"caller": i}) for i in range(5)]
        commands = [host.read_frame(self.stream) for _ in workers]
        self.assertEqual([c["sequence"] for c in commands], [1, 2, 3, 4, 5])
        for command in reversed(commands):
            self.respond(command, {"caller": command["payload"]["caller"]})
        self.assertEqual(sorted(self.settled(w)["value"]["caller"] for w in workers), list(range(5)))

    def test_send_failure_fails_other_pending_waiter(self):
        previous = self.launch(); host.read_frame(self.stream)
        self.socket.fail_after = self.socket.sent
        self.error(self.launch("stop")); self.error(previous)
        self.assertTrue(self.session.closed)

    def test_response_timeout_remains_distinct_and_no_retry(self):
        with patch.object(host, "REQUEST_TIMEOUT_SECONDS", .08):
            worker = self.launch(); command = host.read_frame(self.stream)
            message = self.error(worker)
        self.assertIn("deadline", message)
        self.assertEqual(command["sequence"], 1)
        self.assertTrue(self.session.closed)

    def test_peer_eof_mid_frame_is_failure_not_partial_response(self):
        worker = self.launch(); command = host.read_frame(self.stream)
        self.peer.sendall(b'{"type":"response","id":"' + command["id"].encode())
        self.peer.shutdown(socket.SHUT_WR)
        self.error(worker)
        self.assertTrue(self.session.closed)

    def test_duplicate_response_closes_session(self):
        worker = self.launch(); command = host.read_frame(self.stream)
        self.respond(command); self.settled(worker)
        self.respond(command); self.wait_closed()

    def test_bounded_receive_rejects_oversized_unterminated_frame(self):
        worker = self.launch(); host.read_frame(self.stream)
        with patch.object(host, "MAX_FRAME_BYTES", 512):
            self.peer.sendall(b"x" * 514)
            self.error(worker)
        self.assertTrue(self.session.closed)

    def test_exact_receive_limit_is_accepted(self):
        worker = self.launch(); command = host.read_frame(self.stream)
        response = {"type": "response", "id": command["id"], "payload": {"data": "x" * 300}}
        frame = host.encode_frame(response)
        with patch.object(host, "MAX_FRAME_BYTES", len(frame) - 1):
            self.peer.sendall(frame)
            self.assertEqual(self.settled(worker)["value"], response["payload"])

    def test_invalid_outbound_json_sends_nothing_and_leaves_session_usable(self):
        self.error(self.launch("status", {"invalid": float("nan")}))
        self.assertEqual(self.socket.calls, 0)
        self.assertFalse(self.session.closed)
        worker = self.launch(); command = host.read_frame(self.stream); self.respond(command)
        self.assertEqual(self.settled(worker)["value"], {"ok": True})

    def test_receiver_does_not_change_socket_timeout_per_request(self):
        self.assertEqual(self.socket.gettimeout(), 0.0)
        worker = self.launch(); command = host.read_frame(self.stream); self.respond(command)
        self.settled(worker)
        self.assertEqual(self.socket.gettimeout(), 0.0)

    def test_default_two_second_wire_deadline_is_exercised(self):
        self.assertEqual(host.SEND_TIMEOUT_SECONDS, 2.0)
        started = time.monotonic()
        worker = self.launch("action", {"testPadding": "x" * (4 * 1024 * 1024)})
        result = self.settled(worker, seconds=5)
        self.assertIsInstance(result.get("error"), host.ControlHostError)
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(self.session.closed)

    def test_watchdog_keeps_expired_owner_blocked_after_stalled_send(self):
        from tests.test_nav_access_queue import nav, Clock
        from tests.test_nav_control_watchdog import VM, TARGET
        from scripts.nav_control_watchdog import LeaseWatchdog, bind_identity, resource_epoch
        clock = Clock()
        authority = nav.AccessQueue(Path(self.temporary.name) / "queue.sqlite3", create=True, clock=clock)
        self.session.vm_identity = dict(VM)
        identity = bind_identity(self.session.summary(), {
            "instanceId": "test-instance", "target": {**TARGET, "machineName": "TEST-GUEST"}})
        epoch = resource_epoch(identity)
        row = authority.register("vm:lab-1", epoch)
        authority.cleanup("vm:lab-1", epoch, row["generation"], clock.now,
                          "synthetic-baseline", stopped=True, released=True, in_flight=False)
        self.session.dispatch_policy = nav.QueueDispatchPolicy(authority, {"vm:lab-1": epoch})
        watchdog = LeaseWatchdog(authority, self.session, "vm:lab-1", identity, self.journal)
        authority.submit("a", "worker-a", "A", {"vm:lab-1": epoch})
        grant = authority.dispatch()
        with patch.object(host, "SEND_TIMEOUT_SECONDS", .15):
            worker = self.launch("action", {"testPadding": "x" * (4 * 1024 * 1024)},
                                 access={"request_id": "a", "token": grant["token"]})
            self.assertTrue(self.socket.send_entered.wait(1))
            clock.now += 5000
            result = watchdog.tick()
            self.error(worker)
        self.assertEqual(result["state"], "blocked")
        self.assertFalse(result["cleanupPublished"])
        snapshot = authority.status()
        self.assertTrue(snapshot["resources"][0]["blocked"])
        self.assertEqual(snapshot["requests"][0]["state"], "cleanup")
        self.assertIsNone(authority.dispatch())
        self.assertTrue(self.session.wait_controls_idle(.2))

    def test_frame_after_valid_response_does_not_bypass_size_limit(self):
        worker = self.launch(); command = host.read_frame(self.stream)
        valid = host.encode_frame({"type": "response", "id": command["id"], "payload": {"ok": True}})
        with patch.object(host, "MAX_FRAME_BYTES", 512):
            self.peer.sendall(valid + b"x" * 514)
            self.wait_closed()
            self.settled(worker)
        self.assertEqual(self.session._pending, {})

    def test_close_is_idempotent_and_notifies_gateway_once(self):
        self.session.close(); self.session.close()
        self.session._reader.join(1)
        self.assertEqual(len(self.closed_notices), 1)

    def test_short_idle_gap_between_frame_fragments_is_not_eof(self):
        worker = self.launch(); command = host.read_frame(self.stream)
        data = host.encode_frame({"type": "response", "id": command["id"], "payload": {"ok": True}})
        self.peer.sendall(data[:10])
        time.sleep(.12)
        self.assertFalse(self.session.closed)
        self.peer.sendall(data[10:])
        self.assertEqual(self.settled(worker)["value"], {"ok": True})

    def test_outbound_size_rejection_does_not_poison_next_request(self):
        with patch.object(host, "MAX_FRAME_BYTES", 128):
            self.error(self.launch("status", {"padding": "x" * 512}))
        self.assertEqual(self.socket.calls, 0)
        worker = self.launch(); command = host.read_frame(self.stream); self.respond(command)
        self.assertEqual(self.settled(worker)["value"], {"ok": True})



def malformed_case(data):
    def test(self):
        worker = self.launch(); host.read_frame(self.stream)
        self.peer.sendall(data)
        self.error(worker)
        self.assertTrue(self.session.closed)
    return test


for name, data in {
    "duplicate_properties": b'{"type":"response","type":"response"}\n',
    "non_object": b'[]\n',
    "nonfinite": b'{"type":"response","id":"00000000000000000000000000000000","payload":{"x":NaN}}\n',
    "unknown_id": b'{"type":"response","id":"00000000000000000000000000000000","payload":{}}\n',
    "invalid_utf8": b'\xff\n',
}.items():
    setattr(TransportTests, 'test_reject_' + name, malformed_case(data))


if __name__ == '__main__':
    unittest.main()
