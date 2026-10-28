"""Host-only pinned position delivery tests; no guest or live VM access."""
from __future__ import annotations

import hashlib
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.serve_guest_native_scout import APPROVED_FILENAMES, open_verified_payload
from scripts.serve_guest_position_sampler import (
    BUNDLES, EVENT_DIR, PositionDeliveryServer, ROUTE_FILENAMES, main,
)


def exchange(payload: bytes, *, bundle: str, method="GET", url=None,
             guest="127.0.0.1"):
    _source, _length, _sha, resource, _filename = BUNDLES[bundle]
    digest = hashlib.sha256(payload).hexdigest()
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "fixture.bin"
        source.write_bytes(payload)
        with open_verified_payload(source, len(payload), digest) as stream:
            with PositionDeliveryServer(("127.0.0.1", 0), guest, stream, len(payload),
                                        digest, resource=resource) as server:
                server.timeout = 3
                thread = threading.Thread(target=server.handle_request)
                thread.start()
                try:
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=4)
                    connection.request(method, resource if url is None else url)
                    reply = connection.getresponse()
                    response = (reply.status, dict(reply.getheaders()), reply.read())
                    connection.close()
                finally:
                    thread.join(timeout=5)
                    if thread.is_alive():
                        raise AssertionError("single request did not settle")
                return (*response, server.delivered, server.denied,
                        server.incomplete)


class PositionDeliveryTests(unittest.TestCase):
    def test_legacy_sha_pinned_handler_allowlist_is_unchanged(self):
        self.assertNotIn(BUNDLES["executable"][3], APPROVED_FILENAMES)
        self.assertNotIn(BUNDLES["profile"][3], APPROVED_FILENAMES)

    @unittest.skipUnless(BUNDLES["executable"][0].is_file(), "validated native publish absent")
    def test_real_executable_exact_byte_pin(self):
        source, length, digest, *_ = BUNDLES["executable"]
        with open_verified_payload(source, length, digest) as stream:
            self.assertEqual(stream.read(2), b"MZ")
            self.assertEqual(stream.seek(0, 2), length)

    def test_real_tracked_profile_exact_byte_pin(self):
        source, length, digest, *_ = BUNDLES["profile"]
        with open_verified_payload(source, length, digest) as stream:
            self.assertIn(b'"fieldId": "player.position.xyz"', stream.read())

    def test_separate_routes_carry_exact_bytes_with_distinct_filenames(self):
        payload = b"MZ" + (bytes(range(256)) * 400)
        for bundle in BUNDLES:
            with self.subTest(bundle=bundle):
                status, headers, body, delivered, denied, incomplete = exchange(
                    payload, bundle=bundle,
                )
                self.assertEqual((status, body, delivered, denied, incomplete),
                                 (200, payload, True, 0, 0))
                self.assertEqual(headers["X-Content-SHA256"],
                                 hashlib.sha256(payload).hexdigest().upper())
                self.assertEqual(headers["Content-Disposition"],
                                 'attachment; filename="' + BUNDLES[bundle][4] + '"')

    def test_cross_route_query_and_unauthorized_peer_fail_closed(self):
        for bundle in BUNDLES:
            resource = BUNDLES[bundle][3]
            other = next(v[3] for k, v in BUNDLES.items() if k != bundle)
            for url in (other, resource + "?q=1", "/../other"):
                status, _headers, body, delivered, denied, _incomplete = exchange(
                    b"abc", bundle=bundle, url=url,
                )
                self.assertEqual((status, body, delivered, denied),
                                 (404, b"", False, 1))
            status, _headers, body, delivered, denied, _incomplete = exchange(
                b"abc", bundle=bundle, guest="192.0.2.1",
            )
            self.assertEqual((status, body, delivered, denied),
                             (403, b"", False, 1))

    def test_head_and_methods_do_not_consume_payload(self):
        status, headers, body, delivered, denied, _incomplete = exchange(
            b"abc", bundle="profile", method="HEAD",
        )
        self.assertEqual((status, body, delivered, denied), (200, b"", False, 0))
        self.assertEqual(int(headers["Content-Length"]), 3)
        for method in ("POST", "PUT", "DELETE"):
            status, _headers, body, delivered, denied, _incomplete = exchange(
                b"abc", bundle="profile", method=method,
            )
            self.assertEqual((status, body, delivered, denied),
                             (405, b"", False, 1))

    def test_unknown_route_rejected_before_socket_bind(self):
        with self.assertRaisesRegex(ValueError, "unapproved position delivery route"):
            PositionDeliveryServer(("127.0.0.1", 0), "127.0.0.1", None, 3,
                                   hashlib.sha256(b"abc").hexdigest(),
                                   resource="/unapproved.exe")

    def test_host_only_preflight_does_not_create_receipt_directory(self):
        before = EVENT_DIR.exists()
        self.assertEqual(0, main(["--bundle", "profile", "--seconds", "30"]))
        self.assertEqual(before, EVENT_DIR.exists())

    def test_invalid_deadlines_fail_without_listener(self):
        for seconds in ("0", "601"):
            self.assertEqual(2, main(["--bundle", "profile", "--seconds", seconds]))


if __name__ == "__main__":
    unittest.main()
