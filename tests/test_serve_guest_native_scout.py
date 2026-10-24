"""Host-only tests for streaming native-scout transfer (never access RIFT VM)."""
from __future__ import annotations

import hashlib
from http.client import HTTPConnection, IncompleteRead
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.serve_guest_native_scout import (
    DeliveryServer, EXPECTED_BYTES, EXPECTED_SHA256, RESOURCE, SOURCE,
    open_verified_payload, serve,
)


def exchange(payload: bytes, method="GET", path=RESOURCE, guest="127.0.0.1",
             declared_length=None, declared_sha=None):
    digest = hashlib.sha256(payload).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "scout.exe"
        source.write_bytes(payload)
        with open_verified_payload(source, len(payload), digest) as stream:
            with DeliveryServer(
                ("127.0.0.1", 0), guest, stream,
                len(payload) if declared_length is None else declared_length,
                digest if declared_sha is None else declared_sha,
            ) as server:
                server.timeout = 3
                thread = threading.Thread(target=server.handle_request)
                thread.start()
                try:
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=4)
                    connection.request(method, path)
                    reply = connection.getresponse()
                    status = reply.status
                    headers = dict(reply.getheaders())
                    try:
                        data = reply.read()
                    except IncompleteRead as error:
                        data = error.partial
                    connection.close()
                finally:
                    thread.join(timeout=5)
                    if thread.is_alive():
                        raise AssertionError("single-response server did not exit")
                return status, headers, data, server.delivered, server.incomplete, server.denied


class ScoutTransferTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE.is_file(), "published scout absent on this host")
    def test_actual_74mb_bundle_matches_pin(self):
        with open_verified_payload(SOURCE, EXPECTED_BYTES, EXPECTED_SHA256) as stream:
            self.assertEqual(stream.read(2), b"MZ")
            self.assertEqual(stream.seek(0, 2), EXPECTED_BYTES)

    def test_streams_more_than_one_chunk_and_publishes_checksum_header(self):
        payload = b"MZ" + (bytes(range(256)) * 800)
        status, headers, data, delivered, incomplete, denied = exchange(payload)
        self.assertEqual(status, 200)
        self.assertEqual(data, payload)
        self.assertEqual(int(headers["Content-Length"]), len(payload))
        self.assertEqual(headers["X-Content-SHA256"], hashlib.sha256(payload).hexdigest().upper())
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertTrue(delivered)
        self.assertEqual((incomplete, denied), (0, 0))

    def test_rejects_other_guest_address(self):
        status, _, data, delivered, _, denied = exchange(b"abc", guest="192.0.2.1")
        self.assertEqual(status, 403)
        self.assertEqual(data, b"")
        self.assertFalse(delivered)
        self.assertEqual(denied, 1)

    def test_rejects_wrong_path_and_query(self):
        for path in ("/something.exe", RESOURCE + "?query=yes", "/../other"):
            with self.subTest(path=path):
                status, _, data, delivered, _, denied = exchange(b"abc", path=path)
                self.assertEqual((status, data, delivered, denied), (404, b"", False, 1))

    def test_head_does_not_consume_download(self):
        status, headers, data, delivered, incomplete, denied = exchange(b"abc", method="HEAD")
        self.assertEqual((status, data, delivered, incomplete, denied), (200, b"", False, 0, 0))
        self.assertEqual(int(headers["Content-Length"]), 3)

    def test_write_methods_do_not_execute_or_deliver(self):
        for method in ("POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                status, _, data, delivered, _, denied = exchange(b"abc", method=method)
                self.assertEqual((status, data, delivered, denied), (405, b"", False, 1))

    def test_short_stream_cannot_claim_delivery(self):
        status, headers, data, delivered, incomplete, _ = exchange(b"abc", declared_length=5)
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), 5)
        self.assertEqual(data, b"abc")
        self.assertFalse(delivered)
        self.assertEqual(incomplete, 1)

    def test_bad_stream_digest_cannot_claim_delivery(self):
        status, _, data, delivered, incomplete, _ = exchange(
            b"abc", declared_sha=hashlib.sha256(b"different").hexdigest()
        )
        self.assertEqual(status, 200)
        self.assertEqual(data, b"abc")
        self.assertFalse(delivered)
        self.assertEqual(incomplete, 1)

    def test_hash_size_and_bool_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.exe"
            path.write_bytes(b"abc")
            digest = hashlib.sha256(b"abc").hexdigest()
            for length, sha in (
                (4, digest), (3, hashlib.sha256(b"abd").hexdigest()),
                (True, digest), (3, "not-hex"),
            ):
                with self.subTest(length=length, sha=sha):
                    with self.assertRaises(ValueError):
                        open_verified_payload(path, length, sha)

    def test_invalid_serve_deadline_refused_without_opening_socket(self):
        class Dummy:
            pass
        for value in (True, 0, 29, 601, 10.1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    serve(Dummy(), value)


if __name__ == "__main__":
    unittest.main()
