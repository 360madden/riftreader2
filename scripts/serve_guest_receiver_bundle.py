"""One-shot, host-only HTTP handoff of the pinned RIFT-Lab-1 receiver ZIP.

This is a temporary maintenance channel, not the guest control listener.
Only the exact signed-in guest address can GET the exact expected ZIP.
No game input, VM configuration change, credentials, or public network bind.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.control_host import HostConfig

ZIP_PATH = ROOT / "artifacts" / "receiver-milestones-20261022-01" / "host-only-download" / "RR2-Guest-Startup-v2.zip"
EXPECTED = "ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f"
RESOURCE = "/RR2-Guest-Startup-v2.zip"
MIN_BYTES = 1024
MAX_BYTES = 65536


def verify_zip(path: Path, digest: str = EXPECTED) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("pinned bundle unavailable")
    size = path.stat().st_size
    if not MIN_BYTES <= size <= MAX_BYTES:
        raise ValueError("invalid pinned bundle size")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("pinned bundle hash changed")
    return payload


def create_handler(payload: bytes, guest: str):
    if not payload or not isinstance(payload, bytes):
        raise ValueError("bundle bytes required")
    if not isinstance(ipaddress.ip_address(guest), ipaddress.IPv4Address):
        raise ValueError("IPv4 guest address required")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            if self.client_address[0] != guest:
                self.send_error(403, "guest address not allowed")
                return
            if self.path != RESOURCE:
                self.send_error(404, "only pinned bundle is served")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="RR2-Guest-Startup-v2.zip"')
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
            self.server.delivered = True

        def do_HEAD(self):
            self.send_error(405, "GET only")

        def do_POST(self):
            self.send_error(405, "GET only")

        def log_message(self, fmt, *args):
            # No URL parameters or request data in logs.
            pass

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=49712)
    parser.add_argument("--seconds", type=int, default=150)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    try:
        config = HostConfig.load(args.config)
        if (config.bind_address != "192.168.56.1" or
                config.guest_address != "192.168.56.128" or
                args.port != config.agent_port or
                not 15 <= args.seconds <= 240):
            raise ValueError("RIFT-Lab-1 host-only target differs")
        payload = verify_zip(ZIP_PATH)
        descriptor = {
            "state": "verified-not-serving",
            "host": config.bind_address,
            "guest": config.guest_address,
            "port": args.port,
            "route": RESOURCE,
            "sha256": EXPECTED,
            "bytes": len(payload),
            "lifetimeSeconds": args.seconds,
            "guestInputSent": False,
            "vmSettingsChanged": False,
        }
        if not args.serve:
            print(json.dumps(descriptor), flush=True)
            return 0
        handler = create_handler(payload, config.guest_address)
        with HTTPServer((config.bind_address, args.port), handler) as server:
            server.timeout = 1
            server.delivered = False
            descriptor["state"] = "serving-exact-guest"
            print(json.dumps(descriptor), flush=True)
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline and not server.delivered:
                server.handle_request()
            print(json.dumps({
                "state": "bundle-delivered" if server.delivered else "expired-no-delivery",
                "delivered": bool(server.delivered),
                "utc": datetime.now(timezone.utc).isoformat(),
            }), flush=True)
            return 0 if server.delivered else 3
    except (ValueError, OSError, socket.error) as exc:
        print(json.dumps({"state": "blocked", "reason": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
