"""Loopback-only tests for the one-use, hash-pinned guest memory-map receiver."""
import hashlib
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.receive_guest_memory_report import (
    MAX_UPLOAD_BYTES, ROUTE, POINTER_ROUTE, checked_target, create_handler,
)


def exchange(body: bytes, *, expected: str | None = None,
             peer: str = "127.0.0.1", route: str = ROUTE,
             method: str = "POST", content_type: str = "application/octet-stream",
             max_bytes: int = 1024, create_conflict: bool = False,
             missing_length: bool = False, replace_link: bool = False,
             send_body: bool = True, accepted_route: str = ROUTE):
    with tempfile.TemporaryDirectory() as folder:
        dest = Path(folder) / "map.json"
        if expected is None:
            expected = hashlib.sha256(body).hexdigest()
        handler = create_handler(dest, expected, peer, max_bytes,
                                 route=accepted_route)
        if create_conflict:
            dest.write_bytes(b"existing data")
        with HTTPServer(("127.0.0.1", 0), handler) as server:
            server.timeout = 3
            server.delivered = False
            server.upload_info = None
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                headers = {"Content-Type": content_type}
                def request_and_read():
                    # Header-only rejection probes avoid Windows resets from unread POST bodies.
                    if missing_length or not send_body:
                        client.putrequest(method, route)
                        for name, value in headers.items():
                            client.putheader(name, value)
                        if not missing_length:
                            client.putheader("Content-Length", str(len(body)))
                        client.endheaders()
                    else:
                        client.request(method, route, body=body, headers=headers)
                    response = client.getresponse()
                    code = response.status
                    response.read()
                    return code

                if replace_link:
                    with patch("scripts.receive_guest_memory_report.os.link", side_effect=FileExistsError):
                        status = request_and_read()
                else:
                    status = request_and_read()
                client.close()
            finally:
                thread.join(timeout=4)
                if thread.is_alive():
                    raise AssertionError("HTTP server request did not complete")
        return {
            "status": status, "delivered": server.delivered,
            "bytes": dest.read_bytes() if dest.is_file() else None,
            "info": server.upload_info,
            "partials": list(Path(folder).glob("*.partial")),
        }


class ExactGuestReportTests(unittest.TestCase):
    def test_success_exact_sha_and_no_partial_file(self):
        blob = b'{"evidenceKind":"native-memory-map/1"}\n' * 25
        actual = exchange(blob)
        self.assertEqual(actual["status"], 201)
        self.assertTrue(actual["delivered"])
        self.assertEqual(actual["bytes"], blob)
        self.assertEqual(actual["info"]["sha256"], hashlib.sha256(blob).hexdigest())
        self.assertEqual(actual["info"]["guest"], "127.0.0.1")
        self.assertEqual(actual["partials"], [])

    def test_pointer_archive_route_reuses_content_addressed_receiver(self):
        body = b"pointer-archive-zipped-placeholder-fixture"
        valid = exchange(body, route=POINTER_ROUTE, accepted_route=POINTER_ROUTE)
        self.assertEqual(valid["status"], 201)
        self.assertEqual(valid["bytes"], body)
        wrong = exchange(body, route=ROUTE, accepted_route=POINTER_ROUTE,
                         send_body=False)
        self.assertEqual(wrong["status"], 404)
        self.assertIsNone(wrong["bytes"])

    def test_wrong_sha_is_not_published(self):
        result = exchange(b"changed", expected=hashlib.sha256(b"original").hexdigest())
        self.assertEqual(result["status"], 422)
        self.assertFalse(result["delivered"])
        self.assertIsNone(result["bytes"])

    def test_only_exact_guest_address(self):
        result = exchange(b"map", peer="192.0.2.99", send_body=False)
        self.assertEqual(result["status"], 403)
        self.assertIsNone(result["bytes"])

    def test_only_exact_route(self):
        result = exchange(b"map", route="/anything-else", send_body=False)
        self.assertEqual(result["status"], 404)
        self.assertIsNone(result["bytes"])

    def test_no_get_or_file_serving(self):
        result = exchange(b"map", method="GET", send_body=False)
        self.assertEqual(result["status"], 405)
        self.assertFalse(result["delivered"])

    def test_explicit_content_type_required(self):
        result = exchange(b"map", content_type="application/json", send_body=False)
        self.assertEqual(result["status"], 415)
        self.assertIsNone(result["bytes"])

    def test_strict_maximum_before_body_read(self):
        result = exchange(b"five5", max_bytes=4, send_body=False)
        self.assertEqual(result["status"], 413)
        self.assertIsNone(result["bytes"])

    def test_missing_length_refused(self):
        result = exchange(b"", missing_length=True)
        self.assertEqual(result["status"], 411)
        self.assertIsNone(result["bytes"])

    def test_preexisting_destination_preserved(self):
        result = exchange(b"map", create_conflict=True, send_body=False)
        self.assertEqual(result["status"], 409)
        self.assertEqual(result["bytes"], b"existing data")

    def test_publication_race_cannot_overwrite(self):
        result = exchange(b"map", replace_link=True)
        self.assertEqual(result["status"], 409)
        self.assertIsNone(result["bytes"])
        self.assertEqual(result["partials"], [])

    def test_invalid_expected_sha_or_guest_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "report.json"
            with self.assertRaises(ValueError):
                create_handler(dest, "abcd", "127.0.0.1")
            with self.assertRaises(ValueError):
                create_handler(dest, "a" * 64, "not-an-address")
            with self.assertRaises(ValueError):
                create_handler(dest, "a" * 64, "127.0.0.1", MAX_UPLOAD_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "unsupported fixed"):
                create_handler(dest, "a" * 64, "127.0.0.1", route="/arbitrary")

    def test_destination_restrictions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            allowed = root / "artifacts"
            allowed.mkdir()
            target = allowed / "report.json"
            self.assertEqual(checked_target(target, scope=allowed), target)
            with self.assertRaises(ValueError):
                checked_target(root / "outside.json", scope=allowed)
            target.write_text("preexisting", encoding="ascii")
            with self.assertRaises(ValueError):
                checked_target(target, scope=allowed)


if __name__ == "__main__":
    unittest.main()
