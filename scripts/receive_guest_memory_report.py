"""One-use, content-addressed RIFT-Lab guest map report ingestion.

The listener accepts one exact SHA-256-matching report from the fixed host-only
guest IPv4 address, to a fresh ignored artifact path. It cannot serve files,
execute commands, alter the VM, or overwrite an existing file. This is not a
general-purpose guest control listener.
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
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.control_host import HostConfig

ROUTE = "/rr2-map-oct24-01-report.json"
POINTER_ROUTE = "/rr2-native-pointer-oct24-01-report.zip"
HOST_ADDRESS = "192.168.56.1"
GUEST_ADDRESS = "192.168.56.128"
HOST_PORT = 8765
MAX_UPLOAD_BYTES = 16 * 1024 * 1024
ARTIFACT_SCOPE = ROOT / "artifacts" / "update-recovery-20261023-01"


def checked_target(path: Path, scope: Path = ARTIFACT_SCOPE) -> Path:
    """Confine a never-before-published report to an existing artifact folder."""
    if not path.is_absolute() or path.is_symlink() or path.exists():
        raise ValueError("report destination must be absolute, absent, and not a symlink")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("report destination parent unavailable or symbolic")
    resolved_parent = path.parent.resolve(strict=True)
    resolved_scope = scope.resolve(strict=True)
    if resolved_parent != resolved_scope and not resolved_parent.is_relative_to(resolved_scope):
        raise ValueError("report destination is outside recovery artifacts")
    return resolved_parent / path.name


def create_handler(destination: Path, expected_sha256: str, guest: str,
                   max_bytes: int = MAX_UPLOAD_BYTES, *, route: str = ROUTE):
    """Return a strictly scoped HTTP/1.0 POST handler; no listener is started."""
    if not destination.is_absolute() or not destination.parent.is_dir():
        raise ValueError("absolute destination and existing directory required")
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination must not exist")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("expected full SHA-256 is required")
    if not isinstance(ipaddress.ip_address(guest), ipaddress.IPv4Address):
        raise ValueError("IPv4 guest address required")
    if not 1 <= max_bytes <= MAX_UPLOAD_BYTES:
        raise ValueError("invalid byte ceiling")
    if route not in (ROUTE, POINTER_ROUTE):
        raise ValueError("unsupported fixed one-use receiver route")
    expected = expected_sha256.lower()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def _deny(self, status: int):
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.close_connection = True

        def do_POST(self):
            if self.client_address[0] != guest:
                return self._deny(403)
            if self.path != route:
                return self._deny(404)
            if getattr(self.server, "delivered", False):
                return self._deny(409)
            if self.headers.get("Transfer-Encoding"):
                return self._deny(400)
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
                return self._deny(415)
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return self._deny(411)
            if not re.fullmatch(r"[0-9]+", raw_length):
                return self._deny(400)
            length = int(raw_length)
            if length < 1 or length > max_bytes:
                return self._deny(413)
            if destination.exists() or destination.is_symlink():
                return self._deny(409)

            temp: Path | None = None
            try:
                self.connection.settimeout(8)
                sha = hashlib.sha256()
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix=".rr2-map-", suffix=".partial",
                    dir=destination.parent, delete=False
                ) as stream:
                    temp = Path(stream.name)
                    remaining = length
                    while remaining:
                        part = self.rfile.read(min(65536, remaining))
                        if not part:
                            raise ValueError("upload ended before Content-Length")
                        sha.update(part)
                        stream.write(part)
                        remaining -= len(part)
                    stream.flush()
                    os.fsync(stream.fileno())
                if sha.hexdigest() != expected:
                    return self._deny(422)
                # No-clobber atomic publication within the same directory.
                # An existing destination is never replaced, including in a race.
                os.link(temp, destination)
                self.server.delivered = True
                self.server.upload_info = {
                    "bytes": length, "sha256": sha.hexdigest(),
                    "guest": self.client_address[0],
                    "utc": datetime.now(timezone.utc).isoformat()
                }
                self.send_response(201)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except FileExistsError:
                self._deny(409)
            except (OSError, ValueError):
                self._deny(400)
            finally:
                if temp is not None:
                    try:
                        temp.unlink(missing_ok=True)
                    except OSError:
                        pass

        def do_GET(self):
            self._deny(405)

        def do_HEAD(self):
            self._deny(405)

        def do_PUT(self):
            self._deny(405)

        def do_DELETE(self):
            self._deny(405)

        def log_message(self, fmt, *args):
            # No paths, HTTP headers, received bytes, or file contents in logs.
            pass

    return Handler


def receive_once(bind: str, port: int, handler, seconds: int):
    with HTTPServer((bind, port), handler) as server:
        server.timeout = 1
        server.delivered = False
        server.upload_info = None
        until = time.monotonic() + seconds
        while time.monotonic() < until and not server.delivered:
            server.handle_request()
        return server.upload_info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--port", type=int, default=HOST_PORT)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--kind", choices=("map", "pointer"), default="map")
    args = parser.parse_args()
    try:
        config = HostConfig.load(args.config)
        if config.bind_address != HOST_ADDRESS or config.guest_address != GUEST_ADDRESS:
            raise ValueError("configured VMware host/guest network differs")
        if args.port != HOST_PORT or not 30 <= args.seconds <= 600:
            raise ValueError("unsafe transfer port or lifetime")
        destination = checked_target(args.output)
        receipt = checked_target(args.receipt)
        if receipt == destination:
            raise ValueError("receipt overlaps report destination")
        route = ROUTE if args.kind == "map" else POINTER_ROUTE
        handler = create_handler(destination, args.expected_sha256, GUEST_ADDRESS,
                                 route=route)
        descriptor = {
            "state": "verified-not-serving",
            "host": HOST_ADDRESS, "port": HOST_PORT, "guest": GUEST_ADDRESS,
            "route": route, "destination": str(destination),
            "expectedSha256": args.expected_sha256.upper(),
            "maximumBytes": MAX_UPLOAD_BYTES,
            "lifetimeSeconds": args.seconds,
            "noGameInput": True,
            "noVmSettingChanges": True,
        }
        if not args.serve:
            print(json.dumps(descriptor), flush=True)
            return 0
        print(json.dumps({**descriptor, "state": "serving-exact-report"}), flush=True)
        result = receive_once(HOST_ADDRESS, HOST_PORT, handler, args.seconds)
        if result is None:
            print(json.dumps({"state": "expired-no-report"}), flush=True)
            return 3
        published = {
            "schemaVersion": 1,
            "purpose": ("content-addressed-guest-map-transfer" if args.kind == "map"
                        else "content-addressed-guest-pointer-transfer"),
            "state": "received", "destination": str(destination), **result
        }
        with receipt.open("x", encoding="utf-8") as output:
            json.dump(published, output, indent=2)
        print(json.dumps(published), flush=True)
        return 0
    except (ValueError, OSError, socket.error) as exc:
        print(json.dumps({"state": "blocked", "reason": type(exc).__name__}), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
