"""Isolated tests for single-purpose receiver bundle delivery; no VM access."""
import hashlib
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.serve_guest_receiver_bundle import (
    EXPECTED, RESOURCE, ZIP_PATH, create_handler, verify_zip,
)


def request(handler, path: str):
    with HTTPServer(("127.0.0.1", 0), handler) as server:
        server.timeout = 3
        server.delivered = False
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            client.request("GET", path)
            response = client.getresponse()
            status, headers, data = response.status, response.getheaders(), response.read()
            client.close()
        finally:
            thread.join(timeout=4)
            if thread.is_alive():
                raise AssertionError("request server did not terminate")
    return status, dict(headers), data, server.delivered


class BundleServerTests(unittest.TestCase):
    @unittest.skipUnless(ZIP_PATH.is_file(), "pinned guest ZIP not present")
    def test_real_bundle_hash_is_verified(self):
        actual = verify_zip(ZIP_PATH)
        self.assertEqual(hashlib.sha256(actual).hexdigest(), EXPECTED)

    def test_changed_bundle_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.zip"
            path.write_bytes(b"z" * 2048)
            with self.assertRaisesRegex(ValueError, "hash changed"):
                verify_zip(path)

    def test_only_pinned_route_and_exact_guest_gets_bytes(self):
        payload = b"test-artifact"
        status, headers, data, delivered = request(create_handler(payload, "127.0.0.1"), RESOURCE)
        self.assertEqual(status, 200)
        self.assertEqual(data, payload)
        self.assertEqual(int(headers["Content-Length"]), len(payload))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertTrue(delivered)
        status, _, _, delivered = request(create_handler(payload, "127.0.0.1"), "/secret")
        self.assertEqual(status, 404)
        self.assertFalse(delivered)

    def test_guest_address_gate_refuses_other_client(self):
        status, _, _, delivered = request(create_handler(b"x", "192.0.2.1"), RESOURCE)
        self.assertEqual(status, 403)
        self.assertFalse(delivered)


if __name__ == "__main__":
    unittest.main()
