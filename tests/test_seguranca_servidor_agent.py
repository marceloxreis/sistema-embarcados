import importlib.util
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('security_server', Path(__file__).resolve().parents[1] / 'servidor/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app = server.App(Path(self.tmp.name) / 'db', '1234567890', 'device-test')
        self.httpd = server.make_server('127.0.0.1', 0, app)
        self.httpd.auth_window = 0.4
        self.httpd.connection_deadline = 0.3
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.httpd.server_port}'

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, header, value):
        try:
            response = urlopen(Request(self.url + path, headers={header: value}), timeout=2)
        except HTTPError as error:
            response = error
        with response:
            return response.status

    def test_failures_are_bounded_across_admin_routes_and_expire(self):
        for _ in range(10):
            self.assertEqual(self.request('/api/admin/overview', 'X-Admin-Pin', 'wrong'), 401)
        self.assertEqual(self.request('/api/admin/photo?event_id=x', 'X-Admin-Pin', '1234567890'), 429)
        self.assertEqual(self.request('/api/device/command?device=porta01', 'X-Device-Key', 'device-test'), 200)
        time.sleep(0.5)
        self.assertEqual(self.request('/api/admin/overview', 'X-Admin-Pin', '1234567890'), 200)

    def test_incomplete_headers_expire_even_with_trickle(self):
        sock = socket.create_connection(('127.0.0.1', self.httpd.server_port), timeout=2)
        sock.settimeout(1)
        try:
            sock.sendall(b'GET / HTTP/1.1\r\nHost: x\r\nX-Test: ')
            time.sleep(0.2)
            sock.sendall(b'a')
            time.sleep(0.2)
            self.assertEqual(sock.recv(100), b'')
        finally:
            sock.close()
        self.assertEqual(self.request('/api/admin/overview', 'X-Admin-Pin', '1234567890'), 200)

    def test_incomplete_body_expires_and_server_recovers(self):
        sock = socket.create_connection(('127.0.0.1', self.httpd.server_port), timeout=2)
        sock.settimeout(1)
        try:
            sock.sendall(b'POST /api/device/heartbeat HTTP/1.1\r\nHost: x\r\nX-Device-Key: device-test\r\nContent-Length: 100\r\n\r\n{')
            time.sleep(0.4)
            self.assertEqual(sock.recv(100), b'')
        finally:
            sock.close()
        self.assertEqual(self.request('/api/device/command?device=porta01', 'X-Device-Key', 'device-test'), 200)

    def test_concurrent_failures_cannot_exceed_limit(self):
        self.httpd.auth_window = 5
        self.httpd.connection_deadline = 5
        for _ in range(6):
            self.assertEqual(self.request('/api/admin/overview', 'X-Admin-Pin', 'wrong'), 401)
        barrier = threading.Barrier(7)
        statuses = []
        def attempt():
            barrier.wait()
            statuses.append(self.request('/api/admin/overview', 'X-Admin-Pin', 'wrong'))
        threads = [threading.Thread(target=attempt) for _ in range(6)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(statuses.count(401), 4)
        self.assertEqual(statuses.count(429), 2)

    def test_connection_limit_releases_slots_after_deadline(self):
        self.httpd._slots = threading.BoundedSemaphore(2)
        held = []
        try:
            for _ in range(2):
                sock = socket.create_connection(('127.0.0.1', self.httpd.server_port), timeout=2)
                sock.sendall(b'GET / HTTP/1.1\r\nHost:')
                held.append(sock)
            time.sleep(0.1)
            extra = socket.create_connection(('127.0.0.1', self.httpd.server_port), timeout=2)
            extra.settimeout(1)
            try:
                self.assertEqual(extra.recv(1), b'')
            finally:
                extra.close()
            time.sleep(0.4)
            self.assertEqual(self.request('/api/admin/overview', 'X-Admin-Pin', '1234567890'), 200)
        finally:
            for sock in held:
                sock.close()
