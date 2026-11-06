"""Host-only tests for one-use intake of two guest-declared snapshot hashes."""
from __future__ import annotations

from http.client import HTTPConnection
from http.server import HTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.receive_guest_snapshot_hashes import (
    ROUTE, decode_hashes, handler_for,
)

A = "A" * 64
B = "B" * 64
WIRE = f"{A}|12345|{B}|54321".encode("ascii")


def exchange(body: bytes, *, route=ROUTE, guest="127.0.0.1", method="POST",
             content_type="text/plain"):
    with tempfile.TemporaryDirectory() as temp:
        destination = Path(temp) / "hashes.json"
        handler = handler_for(destination, guest)
        with HTTPServer(("127.0.0.1", 0), handler) as server:
            server.timeout = 3
            server.delivered = False
            server.result = None
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                # On Windows, a rejected POST with unread bytes can be reset on close.
                # Early-denial cases only need headers/peer identity, not a body.
                wire = body if (guest == "127.0.0.1" and route == ROUTE
                                and method == "POST" and content_type == "text/plain") else b""
                connection.request(method, route, body=wire, headers={"Content-Type": content_type})
                response = connection.getresponse()
                status = response.status
                response.read()
                connection.close()
            finally:
                thread.join(timeout=5)
                if thread.is_alive():
                    raise AssertionError("one-request HTTP test server did not exit")
        record = json.loads(destination.read_text()) if destination.exists() else None
        return status, record


class GuestHashIntakeTests(unittest.TestCase):
    def test_parses_exact_two_digest_declarations(self):
        samples = decode_hashes(WIRE)
        self.assertEqual(samples, [
            {"name": "sample-01", "sha256": A, "bytes": 12345},
            {"name": "sample-02", "sha256": B, "bytes": 54321},
        ])

    def test_rejects_bad_shapes_and_oversize(self):
        for wire in (b"", b"a" * 181, WIRE.lower(),
                     f"{A}|0|{B}|1".encode(),
                     f"{A}|01|{B}|1".encode(),
                     f"{A}|16777217|{B}|1".encode(),
                     f"{A}|1|{A}|2".encode(),
                     WIRE + b"garbage"):
            with self.subTest(wire=wire[:22]):
                with self.assertRaises(ValueError):
                    decode_hashes(wire)

    def test_accepts_only_one_guest_declaration_and_records_pin(self):
        status, record = exchange(WIRE)
        self.assertEqual(status, 201)
        self.assertEqual(record["evidenceKind"], "guest-typed-snapshot-hash-declaration/1")
        self.assertEqual(record["requestSha256"],
                         "0BF11FCFB280BF4042DC97CA68DE98AA8099B4194F9DD2D241F34C82E7DFF92F")
        self.assertEqual(record["samples"][1]["sha256"], B)
        self.assertIn("Guest-declared", record["limitation"])

    def test_denies_wrong_guest_ip_without_publication(self):
        status, record = exchange(WIRE, guest="192.0.2.55")
        self.assertEqual(status, 403)
        self.assertIsNone(record)

    def test_denies_wrong_route_and_method_without_publication(self):
        for opts, expected in (({"route": "/other"}, 404),
                               ({"method": "GET"}, 405),
                               ({"method": "PUT"}, 405)):
            with self.subTest(opts=opts):
                status, record = exchange(WIRE, **opts)
                self.assertEqual(status, expected)
                self.assertIsNone(record)

    def test_denies_wrong_content_type(self):
        status, record = exchange(WIRE, content_type="application/json")
        self.assertEqual(status, 415)
        self.assertIsNone(record)

    def test_denies_bad_payload_without_file(self):
        status, record = exchange(b"invalid")
        self.assertEqual(status, 400)
        self.assertIsNone(record)

    def test_never_reuses_existing_declaration_destination(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root) / "prior.json"
            dest.write_text("preserve")
            with self.assertRaisesRegex(ValueError, "never overwrite"):
                handler_for(dest, "127.0.0.1")
            self.assertEqual(dest.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
