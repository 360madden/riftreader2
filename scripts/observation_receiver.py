"""RR2 host-only observation sink; receipt means delivery, not game readiness."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

MAX_BODY = 131072


def validate_config(config):
    address = ipaddress.ip_address(config['bindAddress'])
    networks = tuple(map(ipaddress.ip_network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
    subnet = ipaddress.ip_network(config['guestSubnet'], strict=True)
    if (address.version != 4 or not any(address in net for net in networks)
            or subnet.version != 4 or address not in subnet or subnet.prefixlen < 24
            or type(config['port']) is not int or not 1024 <= config['port'] <= 65535
            or not isinstance(config['token'], str) or not 32 <= len(config['token']) <= 512):
        raise ValueError('invalid-receiver-config')
    return subnet


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.receipt-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'), allow_nan=False)
            stream.flush()
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


MAX_JOURNAL_SEQUENCE = 8192  # Preserve evidence, reject overflow instead of pruning an active run.


def journal_receipt_path(root, instance, sequence):
    """Deterministic safe name for exactly one received outer sequence."""
    if (not isinstance(instance, str) or not 16 <= len(instance) <= 64
            or type(sequence) is not int or not 1 <= sequence <= MAX_JOURNAL_SEQUENCE):
        raise ValueError('invalid-journal-key')
    bucket = hashlib.sha256(instance.encode('utf-8')).hexdigest()
    return Path(root) / 'journal' / bucket / f'{sequence:08d}.json'


def atomic_new_json(path, value):
    """A complete receipt becomes visible atomically, without replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.parent.parent.is_symlink():
        raise ValueError('journal-reparse')
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.journal-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)  # Same-volume atomic no-replace on NTFS.
        except FileExistsError as error:
            raise ValueError('journal-duplicate-receipt') from error
    finally:
        if os.path.exists(name):
            os.unlink(name)


class ObservationStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        history = self.root / 'sequence-history.json'
        self.last = json.loads(history.read_text(encoding='utf-8')) if history.exists() else {}
        if not isinstance(self.last, dict) or any(not isinstance(k, str) or type(v) is not int or v < 1 for k, v in self.last.items()):
            raise ValueError('invalid-sequence-history')
        self.receiver_instance = uuid4().hex

    def accept(self, value, source):
        if not isinstance(value, dict) or type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1:
            raise ValueError('unsupported-schema')
        instance, sequence = value.get('instanceId'), value.get('sequence')
        if not isinstance(instance, str) or not 16 <= len(instance) <= 64 or type(sequence) is not int or sequence < 1:
            raise ValueError('invalid-sequence')
        if sequence <= self.last.get(instance, 0):
            raise ValueError('non-advancing-sequence')
        next_history = dict(self.last)
        next_history[instance] = sequence
        if len(next_history) > 64:
            del next_history[next(iter(next_history))]
        envelope = {'schemaVersion': 1, 'receiverInstance': self.receiver_instance,
                    'receivedAtUtc': datetime.now(timezone.utc).isoformat(),
                    'receivedMonotonicNs': time.monotonic_ns(), 'sourceAddress': source,
                    'observation': value, 'gameReady': False,
                    'note': 'Delivery only; evaluate target, freshness and game state separately.'}
        atomic_new_json(journal_receipt_path(self.root, instance, sequence), envelope)
        atomic_json(self.root / 'sequence-history.json', next_history)
        self.last = next_history
        atomic_json(self.root / 'latest.json', envelope)


def make_handler(config, store):
    subnet = validate_config(config)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)
        def log_message(self, *_):
            pass
        def respond(self, code, status):
            data = json.dumps({'status': status}).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_POST(self):
            if self.path != '/observation':
                return self.respond(404, 'not-found')
            supplied = self.headers.get('X-RiftReader-Token', '')
            if ipaddress.ip_address(self.client_address[0]) not in subnet or not hmac.compare_digest(supplied.encode(), config['token'].encode()):
                return self.respond(403, 'forbidden')
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                    raise ValueError('invalid-length')
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError('incomplete')
                value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid-number')))
                store.accept(value, self.client_address[0])
            except (ValueError, UnicodeError, TimeoutError):
                return self.respond(400, 'invalid-observation')
            self.respond(200, 'recorded')
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    store = ObservationStore(args.output.resolve())
    with HTTPServer((config['bindAddress'], config['port']), make_handler(config, store)) as server:
        print(json.dumps({'status': 'listening', 'address': config['bindAddress'], 'port': config['port'], 'output': str(store.root)}), flush=True)
        server.serve_forever(poll_interval=0.2)


if __name__ == '__main__':
    main()
