import importlib.util
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'body_server', Path(__file__).resolve().parents[1] / 'servidor/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class IncompleteBodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = server.App(Path(self.tmp.name) / 'db', '1234567890', 'device-test')
        self.httpd = server.make_server('127.0.0.1', 0, self.app)
        self.httpd.connection_deadline = 0.2
        self.finished = threading.Event()
        finished = self.finished

        class ObservedHandler(server.Handler):
            def finish(self):
                try:
                    super().finish()
                finally:
                    finished.set()

        self.httpd.RequestHandlerClass = ObservedHandler
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def check_incomplete_body(self, half_close):
        body = json.dumps({'device': 'porta01', 'boot_id': 'boot1',
                           'clock_synced': True, 'queued': 0}).encode()
        headers = (b'POST /api/device/heartbeat HTTP/1.1\r\nHost: localhost\r\n'
                   b'X-Device-Key: device-test\r\nContent-Length: '
                   + str(len(body) + 10).encode() + b'\r\n\r\n')
        with socket.create_connection(('127.0.0.1', self.httpd.server_port), timeout=2) as sock:
            sock.settimeout(2)
            sock.sendall(headers + body)
            if half_close:
                sock.shutdown(socket.SHUT_WR)
            while sock.recv(4096):
                pass
        self.assertTrue(self.finished.wait(2), 'handler did not finish')
        with self.app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM devices').fetchone()[0], 0)

    def test_valid_json_before_half_close_does_not_mutate(self):
        self.check_incomplete_body(half_close=True)

    def test_valid_json_before_deadline_does_not_mutate(self):
        self.check_incomplete_body(half_close=False)


if __name__ == '__main__':
    unittest.main()
