"""One-use exact-guest claim intake for a two-run typed inline ZIP's SHA and size.

Only records a claimed digest and process/build epoch; no ZIP bytes, game memory,
commands or credentials are accepted. The existing separately configured,
SHA-pinned 16 MiB report receiver must transfer the ZIP afterward.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys

from scripts.receive_guest_snapshot_hashes import (
    GUEST_ADDRESS, HOST_ADDRESS, PORT, receive_once,
)

ROUTE = "/rr2-typed-inline-zip-claim-oct24-01"
MAX_ZIP_BYTES = 16 * 1024 * 1024
MAX_CLAIM_BYTES = 255
SHA256 = re.compile(r"[0-9A-F]{64}\Z")
WIRE = re.compile(
    rb"RR2INLINEZIP1\|([0-9A-F]{64})\|([1-9][0-9]{0,7})"
    rb"\|([1-9][0-9]{0,9})\|([1-9][0-9]{0,18})"
    rb"\|([0-9A-F]{64})\|([0-9A-F]{64})\Z"
)


def decode_claim(data: bytes, *, pid: int, ticks: int,
                 game_sha: str, bundle_sha: str) -> dict:
    if (type(data) is not bytes or len(data) > MAX_CLAIM_BYTES
            or type(pid) is not int or pid <= 0
            or type(ticks) is not int or ticks <= 0
            or not isinstance(game_sha, str) or SHA256.fullmatch(game_sha) is None
            or not isinstance(bundle_sha, str) or SHA256.fullmatch(bundle_sha) is None):
        raise ValueError("invalid exact-epoch hash-claim context")
    match = WIRE.fullmatch(data)
    if match is None:
        raise ValueError("not a strict RR2INLINEZIP1 declaration")
    archive_sha, archive_size, process_id, start_ticks, source_sha, binary_sha = (
        value.decode("ascii") for value in match.groups()
    )
    size = int(archive_size)
    if (not 1 <= size <= MAX_ZIP_BYTES
            or int(process_id) != pid or int(start_ticks) != ticks
            or source_sha != game_sha or binary_sha != bundle_sha):
        raise ValueError("ZIP size or exact process/bundle identity differs")
    return {
        "zipSha256": archive_sha,
        "zipBytes": size,
        "target": {
            "processId": pid, "processStartUtcTicks": ticks,
            "executableSha256": game_sha,
        },
        "bundleSha256": bundle_sha,
    }


def handler_for(destination: Path, guest_address: str, *,
                pid: int, ticks: int, game_sha: str, bundle_sha: str):
    if (not destination.is_absolute() or not destination.parent.is_dir()
            or destination.is_symlink() or destination.exists()):
        raise ValueError("claim destination must be new inside existing absolute directory")
    guest = str(ipaddress.IPv4Address(guest_address))
    # Validate the expected epoch before any listener is constructed.
    decode_claim(
        ("RR2INLINEZIP1|" + "A" * 64 + "|1|" + str(pid) + "|" + str(ticks)
         + "|" + game_sha + "|" + bundle_sha).encode("ascii"),
        pid=pid, ticks=ticks, game_sha=game_sha, bundle_sha=bundle_sha,
    )

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
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return self.reply(411)
            if re.fullmatch(r"[0-9]+", raw_length) is None:
                return self.reply(400)
            length = int(raw_length)
            if not 1 <= length <= MAX_CLAIM_BYTES:
                return self.reply(413)
            try:
                self.connection.settimeout(5)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("short guest declaration")
                claim = decode_claim(
                    raw, pid=pid, ticks=ticks,
                    game_sha=game_sha, bundle_sha=bundle_sha)
                receipt = {
                    "schemaVersion": 1,
                    "evidenceKind": "guest-typed-inline-zip-claim/1",
                    "source": "guest-declared-only",
                    "guest": guest,
                    "receivedAtUtc": datetime.now(timezone.utc).isoformat(),
                    **claim,
                    "limitation": (
                        "Digest and size are claims, not a transferred ZIP; "
                        "the next receiver and offline verifier must independently prove bytes."),
                }
                with destination.open("x", encoding="utf-8", newline="\n") as output:
                    json.dump(receipt, output, indent=2)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                self.server.delivered = True
                self.server.result = receipt
                return self.reply(201)
            except FileExistsError:
                return self.reply(409)
            except (ValueError, OSError):
                return self.reply(400)

        def do_GET(self):
            self.reply(405)

        def do_HEAD(self):
            self.reply(405)

        def do_PUT(self):
            self.reply(405)

        def do_DELETE(self):
            self.reply(405)

        def log_message(self, *_args):
            # Do not log incoming paths, hash contents or request headers.
            pass

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--process-start-ticks", type=int, required=True)
    parser.add_argument("--game-sha256", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.port != PORT or not 30 <= args.seconds <= 600:
            raise ValueError("fixed VMnet8 port and 30-600 second limit required")
        output = args.output
        artifacts = Path(__file__).resolve().parents[1] / "artifacts"
        if (not output.is_absolute() or not output.parent.is_dir()
                or output.parent.is_symlink()
                or not output.parent.resolve(strict=True).is_relative_to(artifacts.resolve())):
            raise ValueError("claim receipt must be inside existing ignored artifacts")
        handler = handler_for(
            output, GUEST_ADDRESS, pid=args.process_id, ticks=args.process_start_ticks,
            game_sha=args.game_sha256, bundle_sha=args.bundle_sha256)
        descriptor = {
            "state": "verified-not-serving",
            "host": HOST_ADDRESS, "guest": GUEST_ADDRESS, "port": PORT,
            "route": ROUTE, "maximumZipBytes": MAX_ZIP_BYTES,
            "target": {
                "processId": args.process_id,
                "processStartUtcTicks": args.process_start_ticks,
                "executableSha256": args.game_sha256,
            },
            "bundleSha256": args.bundle_sha256,
            "guestZipReceived": False,
            "guestMemoryAccessed": False,
        }
        if not args.serve:
            print(json.dumps(descriptor))
            return 0
        if os.name != "nt" or Path(sys.executable).name.casefold() != "pythonw.exe":
            raise ValueError("live hash intake requires signed-in Windows Pythonw")
        print(json.dumps({**descriptor, "state": "serving"}), flush=True)
        result = receive_once(HOST_ADDRESS, PORT, handler, args.seconds)
        if result is None:
            print(json.dumps({"state": "expired-no-claim"}), flush=True)
            return 3
        print(json.dumps({"state": "claim-received", "zipBytes": result["zipBytes"]}), flush=True)
        return 0
    except (OSError, ValueError, socket.error) as error:
        print(json.dumps({"state": "blocked", "reason": type(error).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
