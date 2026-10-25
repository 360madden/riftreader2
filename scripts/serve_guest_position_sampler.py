"""Independent one-use guest delivery for exact-build read-only position sampling.

Host-only SHA/size preflight by default. --serve must run as signed-in Windows
pythonw.exe, binds VMnet8 for one exact RIFT-Lab-1 guest peer, serves one fixed
allowlisted payload, expires within ten minutes, and records an ignored receipt.
No VM controller or guest memory is accessed by this module.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse the already SHA-pinned, historical delivery handler byte-for-byte.
from scripts.serve_guest_native_scout import (
    BIND, GUEST, PORT, MAX_SECONDS, DeliveryHandler, open_verified_payload, serve,
)

BUNDLES = {
    "executable": (
        ROOT / "artifacts" / "validation" / "20261025T084650Z-2e1829ff"
        / "native-published" / "RiftReader2.Live.exe",
        74349475,
        "5ca4a6ea9b8904c4987315aa2ae287b3f32b4bb8ed27f5ba951d4d704682c07b",
        "/rr2-position-sampler-oct25-01.exe",
        "rr2-position-sampler-oct25-01.exe",
    ),
    "profile": (
        ROOT / "config" / "position-candidate-profile.json",
        395,
        "ffa948c24170070f7a0e7a986273bef7e0774d953dfea4ecabb14112fccf88c8",
        "/rr2-position-profile-oct25-01.json",
        "rr2-position-profile-oct25-01.json",
    ),
}
ROUTE_FILENAMES = {values[3]: values[4] for values in BUNDLES.values()}
EVENT_DIR = ROOT / "artifacts" / "validation" / "position-sampler-transfer-events-oct25-01"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class PositionDeliveryServer(HTTPServer):
    """Fixed-route owner compatible with the existing one-use delivery handler."""

    allow_reuse_address = False
    request_queue_size = 2

    def __init__(self, address, guest: str, payload, length: int, digest: str,
                 *, resource: str):
        if resource not in ROUTE_FILENAMES:
            raise ValueError("unapproved position delivery route")
        if type(length) is not int or length <= 0:
            raise ValueError("invalid declared length")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid declared SHA")
        self.guest = str(ipaddress.IPv4Address(guest))
        self.payload = payload
        self.length = length
        self.sha256 = digest
        self.resource = resource
        self.download_name = ROUTE_FILENAMES[resource]
        self.delivered = False
        self.denied = 0
        self.incomplete = 0
        self.delivered_bytes = 0
        super().__init__(address, DeliveryHandler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", choices=tuple(BUNDLES), required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not 30 <= args.seconds <= MAX_SECONDS:
            raise ValueError("invalid expiry")
        path, length, digest, resource, filename = BUNDLES[args.bundle]
        with open_verified_payload(path, length, digest) as payload:
            preflight = {
                "state": "verified-not-serving", "bundle": args.bundle,
                "bind": BIND, "allowedGuest": GUEST, "port": PORT,
                "resource": resource, "filename": filename,
                "sha256": digest.upper(), "byteLength": length,
                "deadlineSeconds": args.seconds,
                "guestBytesVerified": False, "guestReaderExecuted": False,
            }
            if not args.serve:
                print(json.dumps(preflight, sort_keys=True))
                return 0
            if os.name != "nt" or Path(sys.executable).name.casefold() != "pythonw.exe":
                raise ValueError("live delivery requires signed-in Windows pythonw.exe")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
                check.bind((BIND, 0))
            with PositionDeliveryServer(
                (BIND, PORT), GUEST, payload, length, digest, resource=resource
            ) as server:
                EVENT_DIR.mkdir(parents=True, exist_ok=True)
                receipt = EVENT_DIR / (uuid4().hex + ".json")
                started = timestamp()

                def record(state):
                    entry = {
                        **preflight, "state": state, "startedUtc": started,
                        "updatedUtc": timestamp(), "serverPid": os.getpid(),
                        "pythonExecutable": sys.executable,
                        "deliveredBytes": server.delivered_bytes,
                        "deniedRequests": server.denied,
                        "incompleteResponses": server.incomplete,
                    }
                    staged = receipt.with_suffix(".partial")
                    with staged.open("x", encoding="utf-8") as output:
                        json.dump(entry, output, indent=2, sort_keys=True)
                        output.write("\n")
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(staged, receipt)

                return 0 if serve(server, args.seconds, record) == "delivered" else 3
    except (ValueError, OSError, socket.error) as error:
        print(json.dumps({"state": "blocked", "reason": type(error).__name__}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
