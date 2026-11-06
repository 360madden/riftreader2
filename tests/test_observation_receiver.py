"""Offline tests of RR2 observation delivery and replay protection."""
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
