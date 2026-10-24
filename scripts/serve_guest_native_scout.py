"""One-use, stream-verified delivery of the pinned V2 read-only native scout.

This is a host-only file handoff, not a remote execution or control endpoint.
It binds only VMnet8, serves one exact 74 MB published executable to the
known RIFT-Lab-1 guest, records an ignored local receipt, and expires. The
guest MUST independently verify the full SHA-256 before launching the scout.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "validation" / "rr2-scout-publish-20261024-01" / "RiftReader2.Live.exe"
EVENT_DIR = SOURCE.parent / "transfer-events"
EXPECTED_BYTES = 74209699
EXPECTED_SHA256 = "c34d1c9bc5ec134d50ae38fbe6a16d13b0dbac9ec412d9c4f4714e3ddfd9876c"
RESOURCE = "/rr2-scout-oct24-01.exe"
BIND = "192.168.56.1"
GUEST = "192.168.56.128"
PORT = 8765
MAX_SECONDS = 600
CHUNK = 65536


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_verified_payload(path: Path, expected_bytes: int, expected_sha256: str):
    """Return a still-open read-only descriptor, pinned by count and SHA-256."""
    if (not isinstance(path, Path) or not path.is_file() or path.is_symlink()
            or type(expected_bytes) is not int or expected_bytes <= 0
            or not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
        raise ValueError("invalid pinned payload metadata")
    if path.stat().st_size != expected_bytes:
        raise ValueError("pinned payload size changed")
    stream = path.open("rb")
    try:
        digest = hashlib.sha256()
        count = 0
        while chunk := stream.read(CHUNK):
            count += len(chunk)
            if count > expected_bytes:
                raise ValueError("pinned payload grew")
            digest.update(chunk)
        if count != expected_bytes or digest.hexdigest() != expected_sha256:
            raise ValueError("pinned payload digest changed")
        if os.fstat(stream.fileno()).st_size != expected_bytes:
            raise ValueError("pinned payload size drift")
        stream.seek(0)
        return stream
    except BaseException:
        stream.close()
        raise


class DeliveryServer(HTTPServer):
    allow_reuse_address = False
    request_queue_size = 2

    def __init__(self, address, guest: str, payload, length: int, digest: str):
        self.guest = str(ipaddress.IPv4Address(guest))
        if type(length) is not int or length <= 0:
            raise ValueError("invalid declared length")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid declared SHA")
        self.payload = payload
        self.length = length
        self.sha256 = digest
        self.delivered = False
        self.denied = 0
        self.incomplete = 0
        self.delivered_bytes = 0
        super().__init__(address, DeliveryHandler)


class DeliveryHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "RR2NativeScoutHandoff/1"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass  # Never log guest paths, request strings or headers.

    def _deny(self, status: int):
        self.server.denied += 1
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.close_connection = True

    def _allowed(self) -> bool:
        if self.client_address[0] != self.server.guest:
            self._deny(403)
            return False
        if self.path != RESOURCE:
            self._deny(404)
            return False
        if self.server.delivered:
            self._deny(409)
            return False
        return True

    def _headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", 'attachment; filename="rr2-scout-oct24-01.exe"')
        self.send_header("Content-Length", str(self.server.length))
        self.send_header("X-Content-SHA256", self.server.sha256.upper())
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_HEAD(self):
        if self._allowed():
            self._headers()  # HEAD does not consume the only download.

    def do_GET(self):
        if not self._allowed():
            return
        sent = 0
        digest = hashlib.sha256()
        try:
            self.connection.settimeout(30)
            self.server.payload.seek(0)
            self._headers()
            while sent < self.server.length:
                chunk = self.server.payload.read(min(CHUNK, self.server.length - sent))
                if not chunk:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
                digest.update(chunk)
            self.wfile.flush()
            if sent == self.server.length and digest.hexdigest() == self.server.sha256:
                self.server.delivered = True
                self.server.delivered_bytes = sent
                return
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        self.server.incomplete += 1

    def do_POST(self):
        self._deny(405)

    def do_PUT(self):
        self._deny(405)

    def do_DELETE(self):
        self._deny(405)


def serve(server: DeliveryServer, seconds: int, progress=None) -> str:
    if type(seconds) is not int or not 30 <= seconds <= MAX_SECONDS:
        raise ValueError("invalid one-use deadline")
    server.timeout = 0.25
    deadline = time.monotonic() + seconds
    if progress:
        progress("listening")
    while time.monotonic() < deadline and not server.delivered:
        server.handle_request()
    outcome = "delivered" if server.delivered else "expired"
    if progress:
        progress(outcome)
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        if not 30 <= args.seconds <= MAX_SECONDS:
            raise ValueError("invalid expiry")
        with open_verified_payload(SOURCE, EXPECTED_BYTES, EXPECTED_SHA256) as payload:
            descriptor = {
                "state": "verified-not-serving", "host": BIND, "guest": GUEST,
                "port": PORT, "path": RESOURCE, "sha256": EXPECTED_SHA256.upper(),
                "bytes": EXPECTED_BYTES, "lifetimeSeconds": args.seconds,
                "guestFileVerified": False, "guestScannerExecuted": False,
            }
            if not args.serve:
                print(json.dumps(descriptor))
                return 0
            if os.name != "nt" or Path(sys.executable).name.casefold() != "pythonw.exe":
                raise ValueError("live transfer requires signed-in Windows Pythonw")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
                check.bind((BIND, 0))
            with DeliveryServer((BIND, PORT), GUEST, payload, EXPECTED_BYTES, EXPECTED_SHA256) as server:
                EVENT_DIR.mkdir(parents=True, exist_ok=True)
                event = EVENT_DIR / (uuid4().hex + ".json")
                started = timestamp()

                def record(state):
                    receipt = {
                        **descriptor, "state": state, "startedUtc": started,
                        "updatedUtc": timestamp(), "serverPid": os.getpid(),
                        "pythonExecutable": sys.executable,
                        "deliveredBytes": server.delivered_bytes,
                        "deniedRequests": server.denied,
                        "incompleteResponses": server.incomplete,
                    }
                    staged = event.with_suffix(".partial")
                    with staged.open("x", encoding="utf-8") as output:
                        json.dump(receipt, output, indent=2)
                        output.write("\n")
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(staged, event)

                return 0 if serve(server, args.seconds, record) == "delivered" else 3
    except (ValueError, OSError, socket.error) as error:
        print(json.dumps({"state": "blocked", "reason": type(error).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
