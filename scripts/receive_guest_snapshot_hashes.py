"""One-use, guest-IP-limited intake of hashes for two *future* snapshot reports.

This transfers only the guest-declared SHA-256/byte counts, never game memory.
Use each resulting digest with the existing content-pinned, one-use report
receiver, then validate both complete original reports independently on host.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys
import time

HOST_ADDRESS = "192.168.56.1"
GUEST_ADDRESS = "192.168.56.128"
PORT = 8765
ROUTE = "/rr2-typed-snapshot-hashes-oct24-01"
SIZE_CAP = 16 * 1024 * 1024
WIRE_PATTERN = re.compile(rb"([0-9A-F]{64})\|([1-9][0-9]{0,7})\|([0-9A-F]{64})\|([1-9][0-9]{0,7})\Z")
PLAN_SHA = "C8D508350162FBF5D245F65BBE5E140DD6A5A8BECD3DF67E3810CC2ADDDDE3A7"
REQUEST_SHA = "0BF11FCFB280BF4042DC97CA68DE98AA8099B4194F9DD2D241F34C82E7DFF92F"


def decode_hashes(data: bytes) -> list[dict]:
    if not isinstance(data, bytes) or len(data) > 180:
        raise ValueError("declared hashes exceed bounded wire")
    match = WIRE_PATTERN.fullmatch(data)
    if match is None:
        raise ValueError("expected two uppercase SHA-256 and decimal lengths")
    a, a_size, b, b_size = match.groups()
    values = [("sample-01", a, a_size), ("sample-02", b, b_size)]
    samples = []
    for name, digest, size in values:
        n = int(size)
        if not 1 <= n <= SIZE_CAP:
            raise ValueError("declared report bytes outside receiver limit")
        samples.append({"name": name, "sha256": digest.decode("ascii"), "bytes": n})
    if samples[0]["sha256"] == samples[1]["sha256"]:
        raise ValueError("two acquisition reports cannot be byte-identical")
    return samples


def handler_for(destination: Path, guest_address: str, *, request_sha: str = REQUEST_SHA):
    if not destination.is_absolute() or not destination.parent.is_dir():
        raise ValueError("existing absolute destination parent required")
    if destination.exists() or destination.is_symlink():
        raise ValueError("never overwrite a prior guest hash receipt")
    guest = str(ipaddress.IPv4Address(guest_address))
    if not re.fullmatch(r"[0-9A-F]{64}", request_sha):
        raise ValueError("invalid pinned snapshot request hash")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def reply(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.close_connection = True

        def do_POST(self):
            if self.client_address[0] != guest:
                return self.reply(403)
            if self.path != ROUTE:
                return self.reply(404)
            if getattr(self.server, "delivered", False) or destination.exists():
                return self.reply(409)
            if self.headers.get("Transfer-Encoding"):
                return self.reply(400)
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "text/plain":
                return self.reply(415)
            length = self.headers.get("Content-Length")
            if length is None:
                return self.reply(411)
            if not re.fullmatch(r"[0-9]+", length):
                return self.reply(400)
            n = int(length)
            if not 1 <= n <= 180:
                return self.reply(413)
            try:
                self.connection.settimeout(5)
                data = self.rfile.read(n)
                if len(data) != n:
                    raise ValueError("short digest declaration")
                values = decode_hashes(data)
                result = {
                    "schemaVersion": 1,
                    "evidenceKind": "guest-typed-snapshot-hash-declaration/1",
                    "requestSha256": request_sha,
                    "sourcePlanSha256": PLAN_SHA,
                    "guest": guest,
                    "receivedAtUtc": datetime.now(timezone.utc).isoformat(),
                    "samples": values,
                    "limitation": "Guest-declared hashes only; no original report has yet been transferred or verified.",
                }
                # Exclusive publication; never silently replace a prior declaration.
                with destination.open("x", encoding="utf-8", newline="\n") as stream:
                    json.dump(result, stream, indent=2)
                    stream.write("\n")
                    stream.flush()
                self.server.delivered = True
                self.server.result = result
            except FileExistsError:
                return self.reply(409)
            except (OSError, ValueError):
                return self.reply(400)
            return self.reply(201)

        def do_GET(self):
            self.reply(405)

        def do_HEAD(self):
            self.reply(405)

        def do_PUT(self):
            self.reply(405)

        def log_message(self, *_args):
            # Digest values and guest request details stay out of server logs.
            pass

    return Handler


def receive_once(bind: str, port: int, handler, seconds: int):
    with HTTPServer((bind, port), handler) as server:
        server.timeout = 1
        server.delivered = False
        server.result = None
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not server.delivered:
            server.handle_request()
        return server.result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args(argv)
    try:
        import hashlib
        if args.expected_plan_sha256 != PLAN_SHA:
            raise ValueError("exact known follow-up plan digest required")
        if hashlib.sha256(args.plan.read_bytes()).hexdigest().upper() != PLAN_SHA:
            raise ValueError("plan source bytes changed")
        plan = json.loads(args.plan.read_text("utf-8"))
        if (plan["evidenceKind"] != "typed-scout-snapshot-followup-plan/1"
                or [x["requestSha256"] for x in plan["independentSamples"]] != [REQUEST_SHA, REQUEST_SHA]):
            raise ValueError("plan request digests changed")
        if args.port != PORT or not 30 <= args.seconds <= 600:
            raise ValueError("pinned network port or timeout differs")
        output = args.output.resolve(strict=False)
        if (not args.output.is_absolute() or args.output.is_symlink()
                or not output.parent.is_dir()):
            raise ValueError("destination must be an absolute non-symlink under an existing folder")
        if not output.parent.is_relative_to(Path(__file__).resolve().parents[1] / "artifacts"):
            raise ValueError("destination outside repository artifacts")
        handler = handler_for(output, GUEST_ADDRESS)
        print(json.dumps({"state": "serving" if args.serve else "verified-not-serving",
                          "route": ROUTE, "bind": HOST_ADDRESS, "guest": GUEST_ADDRESS,
                          "requestSha256": REQUEST_SHA, "noGameMemory": True}), flush=True)
        if not args.serve:
            return 0
        result = receive_once(HOST_ADDRESS, PORT, handler, args.seconds)
        if result is None:
            print(json.dumps({"state": "expired"}), flush=True)
            return 3
        print(json.dumps({"state": "received", "sampleCount": len(result["samples"])}), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError, socket.error) as error:
        print(json.dumps({"state": "blocked", "reason": type(error).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
