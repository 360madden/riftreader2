"""Offline tests of RR2 observation delivery and replay protection."""
import ast
import hashlib
import http.client
from http.server import HTTPServer
import ipaddress
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from scripts import observation_receiver as receiver


class ReceiverTests(unittest.TestCase):
    def test_managed_receiver_source_pin_matches_shipped_source(self):
        """Catch stale pins on every platform, including without Windows msvcrt."""
        root = Path(__file__).resolve().parents[1]
        manager = ast.parse((root / 'scripts' / 'ensure_receiver.py').read_text(encoding='utf-8'))
        assignments = [node.value for node in manager.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == 'SOURCE_SHA256'
                               for target in node.targets)]
        self.assertEqual(len(assignments), 1)
        pinned = ast.literal_eval(assignments[0])
        actual = hashlib.sha256((root / 'scripts' / 'observation_receiver.py').read_bytes()).hexdigest().upper()
        self.assertEqual(pinned, actual, 'review receiver changes and update its source pin')

    def test_valid_delivery_and_replay(self):
        config = {'bindAddress': '192.168.56.1', 'guestSubnet': '192.168.56.0/24', 'port': 49813, 'token': 'x' * 32}
        with tempfile.TemporaryDirectory() as folder:
            store = receiver.ObservationStore(folder)
            with patch.object(receiver, 'validate_config', return_value=ipaddress.ip_network('127.0.0.0/8')):
                server = HTTPServer(('127.0.0.1', 0), receiver.make_handler(config, store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(thread.join)
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            def post(token, value):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                connection.request('POST', '/observation', json.dumps(value), {'X-RiftReader-Token': token})
                response = connection.getresponse()
                response.read()
                connection.close()
                return response.status
            observation = {'schemaVersion': 1, 'instanceId': 'a' * 32, 'sequence': 1}
            self.assertEqual(post('wrong', observation), 403)
            self.assertEqual(post(config['token'], observation), 200)
            receipt = json.loads((Path(folder) / 'latest.json').read_text())
            self.assertEqual(receipt['observation'], observation)
            self.assertFalse(receipt['gameReady'])
            self.assertEqual(receipt['sourceAddress'], '127.0.0.1')
            self.assertEqual(post(config['token'], observation), 400)
            self.assertEqual(receiver.ObservationStore(folder).last[observation['instanceId']], 1)

    def test_config_rejects_public_wildcard_and_broad_subnet(self):
        config = {'bindAddress': '192.168.56.1', 'guestSubnet': '192.168.56.0/24', 'port': 49813, 'token': 'x' * 32}
        receiver.validate_config(config)
        for patch_value in ({'bindAddress': '0.0.0.0'}, {'guestSubnet': '192.168.0.0/16'}, {'token': 'short'}):
            with self.subTest(patch_value=patch_value), self.assertRaises(ValueError):
                receiver.validate_config({**config, **patch_value})


if __name__ == '__main__':
    unittest.main()
