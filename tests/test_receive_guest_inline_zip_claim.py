"""Loopback-only proof of exact-epoch ZIP hash declaration before content-pinned upload."""
from __future__ import annotations

from http.client import HTTPConnection
from http.server import HTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.receive_guest_inline_zip_claim import (
    MAX_ZIP_BYTES, ROUTE, decode_claim, handler_for,
)
from scripts.receive_guest_memory_report import (
    ROUTE as ZIP_UPLOAD_ROUTE, create_handler as upload_handler,
)
from scripts.verify_typed_inline_archive import ArchiveError, verify_archive, verify_and_publish
from tests.test_verify_typed_inline_archive import (
    BUNDLE, GAME, PID, TICKS, archive_file, members,
)

HASH = "A" * 64


def declaration(*, digest: str = HASH, size: int = 7575,
                pid: int = PID, ticks: int = TICKS,
                game: str = GAME, bundle: str = BUNDLE) -> bytes:
    return f"RR2INLINEZIP1|{digest}|{size}|{pid}|{ticks}|{game}|{bundle}".encode("ascii")


def roundtrip(handler, method="POST", route=ROUTE, body=b"",
              content_type="text/plain", *, header_only=False, missing_length=False):
    with HTTPServer(("127.0.0.1", 0), handler) as server:
        server.timeout = 4
        server.delivered = False
        server.result = None
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=4)
            if header_only or missing_length:
                client.putrequest(method, route)
                client.putheader("Content-Type", content_type)
                if not missing_length:
                    client.putheader("Content-Length", str(len(body)))
                client.endheaders()
            else:
                client.request(method, route, body=body,
                               headers={"Content-Type": content_type})
            response = client.getresponse()
            code = response.status
            response.read()
            client.close()
        finally:
            thread.join(timeout=5)
            if thread.is_alive():
                raise AssertionError("one-use loopback response thread did not exit")
        return code, server.result if server.result is not None else getattr(server, "upload_info", None)


class GuestZipClaimTests(unittest.TestCase):
    def test_exact_guest_claim_schema_and_epoch(self):
        raw = declaration()
        record = decode_claim(raw, pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
        self.assertEqual(record["zipSha256"], HASH)
        self.assertEqual(record["zipBytes"], 7575)
        self.assertEqual(record["target"]["processStartUtcTicks"], TICKS)
        self.assertEqual(record["bundleSha256"], BUNDLE)

    def test_rejects_unbounded_or_noncanonical_declarations(self):
        bad = (
            b"", b"not-a-zip-claim", declaration().lower(), declaration() + b"garbage",
            declaration(size=0), declaration(size=MAX_ZIP_BYTES + 1),
            declaration(size=1).replace(b"|1|", b"|01|", 1),
            declaration(digest="x" * 64), declaration(game="C" * 64),
            declaration(bundle="D" * 64), declaration(pid=PID + 1),
            declaration(ticks=TICKS + 1),
        )
        for raw in bad:
            with self.subTest(data=raw[:48]):
                with self.assertRaises(ValueError):
                    decode_claim(raw, pid=PID, ticks=TICKS,
                                 game_sha=GAME, bundle_sha=BUNDLE)

    def test_invalid_declared_context_cannot_create_handler(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary) / "claim.json"
            for context in (
                {"pid": 0}, {"ticks": 0}, {"game_sha": GAME.lower()},
                {"bundle_sha": "not-full-sha"},
            ):
                with self.subTest(context=context):
                    args = {"pid": PID, "ticks": TICKS, "game_sha": GAME,
                            "bundle_sha": BUNDLE}
                    args.update(context)
                    with self.assertRaises(ValueError):
                        handler_for(dest, "127.0.0.1", **args)

    def test_valid_post_writes_exact_claim_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary) / "claim.json"
            handler = handler_for(dest, "127.0.0.1",
                                  pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
            code, result = roundtrip(handler, body=declaration())
            self.assertEqual(code, 201)
            self.assertTrue(dest.is_file())
            on_disk = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, result)
            self.assertEqual(result["evidenceKind"], "guest-typed-inline-zip-claim/1")
            self.assertEqual(result["source"], "guest-declared-only")
            self.assertIn("not a transferred ZIP", result["limitation"])

    def test_wrong_path_guest_and_type_rejected_without_receipt(self):
        for settings, expected in (
            ({"route": "/wrong"}, 404),
            ({"guest": "192.0.2.1"}, 403),
            ({"content_type": "application/json"}, 415),
            ({"method": "GET"}, 405),
        ):
            with self.subTest(settings=settings), tempfile.TemporaryDirectory() as temporary:
                dest = Path(temporary) / "claim.json"
                guest = settings.get("guest", "127.0.0.1")
                handler = handler_for(dest, guest, pid=PID, ticks=TICKS,
                                      game_sha=GAME, bundle_sha=BUNDLE)
                opts = {key: value for key, value in settings.items() if key != "guest"}
                code, record = roundtrip(
                    handler, body=declaration(), header_only=True, **opts)
                self.assertEqual(code, expected)
                self.assertIsNone(record)
                self.assertFalse(dest.exists())

    def test_missing_or_oversized_body_rejected_without_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for mode, expected in (("missing", 411), ("oversized", 413)):
                with self.subTest(mode=mode):
                    dest = base / (mode + ".json")
                    handler = handler_for(dest, "127.0.0.1", pid=PID, ticks=TICKS,
                                          game_sha=GAME, bundle_sha=BUNDLE)
                    code, record = roundtrip(
                        handler, body=b"X" * 256 if mode == "oversized" else b"",
                        header_only=True, missing_length=mode == "missing")
                    self.assertEqual(code, expected)
                    self.assertIsNone(record)
                    self.assertFalse(dest.exists())

    def test_invalid_wire_rejected_without_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary) / "claim.json"
            handler = handler_for(dest, "127.0.0.1",
                                  pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
            code, record = roundtrip(handler, body=declaration(ticks=TICKS + 1))
            self.assertEqual(code, 400)
            self.assertIsNone(record)
            self.assertFalse(dest.exists())

    def test_refuses_overwrite_of_any_existing_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary) / "claim.json"
            dest.write_text("preserve", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "claim destination"):
                handler_for(dest, "127.0.0.1",
                            pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
            self.assertEqual(dest.read_text(encoding="ascii"), "preserve")

    def test_claim_then_existing_sha_pinned_receiver_then_offline_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive, digest = archive_file(base, members())
            raw = archive.read_bytes()
            declared = declaration(digest=digest, size=len(raw))
            claim_dest = base / "claim.json"
            claim_handler = handler_for(claim_dest, "127.0.0.1", pid=PID,
                                        ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE)
            code, record = roundtrip(claim_handler, body=declared)
            self.assertEqual(code, 201)
            self.assertEqual(record["zipSha256"], digest)
            self.assertEqual(record["zipBytes"], len(raw))

            received = base / "received.zip"
            receiving_handler = upload_handler(
                received, record["zipSha256"], "127.0.0.1")
            status, uploaded = roundtrip(
                receiving_handler, method="POST", route=ZIP_UPLOAD_ROUTE,
                body=raw, content_type="application/octet-stream")
            self.assertEqual(status, 201)
            self.assertEqual(received.read_bytes(), raw)
            files, proof = verify_archive(
                received, record["zipSha256"], pid=PID, ticks=TICKS,
                game_sha=GAME, bundle_sha=BUNDLE)
            self.assertEqual(len(files), 8)
            self.assertEqual([r["snapshotCount"] for r in proof["runs"]], [1, 1])
            self.assertFalse(proof["typedFrameQualified"])
            upload = {
                "schemaVersion": 1, "purpose": "content-addressed-guest-map-transfer",
                "state": "received", "destination": str(received), **uploaded,
            }
            upload_path = base / "upload-receipt.json"
            upload_path.write_text(json.dumps(upload), encoding="utf-8")
            receipt = verify_and_publish(
                received, record["zipSha256"], base / "recovered",
                pid=PID, ticks=TICKS, game_sha=GAME, bundle_sha=BUNDLE,
                claim_path=claim_dest, upload_path=upload_path,
                expected_guest="127.0.0.1")
            self.assertEqual(receipt["guestTransfer"]["zipBytes"], len(raw))
            self.assertEqual(receipt["guestTransfer"]["guest"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
