import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch

from scripts.benchmark_guest_transfers import TransferHandler


class TransferBenchmarkTests(unittest.TestCase):
    def test_synthetic_routes_are_one_use_and_verify_uploaded_bytes(self):
        data = b'bounded fixture'
        item = dict(data=data, sha256=hashlib.sha256(data).hexdigest(), case='fixture')
        server = ThreadingHTTPServer(('127.0.0.1', 0), TransferHandler)
        server.lock = threading.Lock(); server.completed = []
        server.routes = {(method, path): item for method, path in
                         [('GET', '/download'), ('POST', '/upload'), ('POST', '/bad')]}
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(method, path, body=None):
            connection = HTTPConnection(*server.server_address, timeout=5)
            try:
                connection.request(method, path, body=body)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()
        try:
            with patch('scripts.benchmark_guest_transfers.GUEST', '192.0.2.1'):
                self.assertEqual(request('GET', '/download')[0], 404)
            with patch('scripts.benchmark_guest_transfers.GUEST', '127.0.0.1'):
                self.assertEqual(request('GET', '/download'), (200, data))
                self.assertEqual(request('GET', '/download')[0], 404)
                self.assertEqual(request('POST', '/bad', b'x' * len(data))[0], 422)
                self.assertEqual(request('POST', '/upload', data), (200, item['sha256'].encode()))
                self.assertEqual(request('POST', '/upload', data)[0], 404)
            self.assertEqual(len(server.completed), 2)
        finally:
            server.shutdown(); server.server_close(); thread.join()
