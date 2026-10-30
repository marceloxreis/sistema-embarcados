import importlib.util
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location(
    'timer_failure_server', Path(__file__).resolve().parents[1] / 'servidor/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class TimerFailureTests(unittest.TestCase):
    def test_timer_start_failure_closes_connection_and_recovers_slot(self):
        class SingleSlotServer(server.BoundedHTTPServer):
            max_connections = 1

        with tempfile.TemporaryDirectory() as tmp:
            httpd = SingleSlotServer(('127.0.0.1', 0), server.Handler)
            httpd.app = server.App(Path(tmp) / 'db', '1234567890', 'device-test')
            httpd.daemon_threads = True
            request, peer = socket.socketpair()
            try:
                self.assertTrue(httpd._slots.acquire(blocking=False))
                with mock.patch.object(server.threading.Timer, 'start', side_effect=RuntimeError('timer failed')), \
                     mock.patch.object(server.ThreadingHTTPServer, 'process_request_thread') as handler:
                    with self.assertRaisesRegex(RuntimeError, 'timer failed'):
                        httpd.process_request_thread(request, ('127.0.0.1', 1))
                    handler.assert_not_called()
                self.assertEqual(request.fileno(), -1)
                peer.settimeout(1)
                self.assertEqual(peer.recv(1), b'')
                self.assertTrue(httpd._slots.acquire(blocking=False))
                httpd._slots.release()

                thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
                thread.start()
                try:
                    with socket.create_connection(httpd.server_address, timeout=2) as client:
                        client.settimeout(2)
                        client.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
                        response = b''
                        while chunk := client.recv(4096):
                            response += chunk
                    self.assertIn(b'HTTP/1.0 200', response)
                finally:
                    httpd.shutdown()
                    thread.join(2)
            finally:
                request.close()
                peer.close()
                httpd.server_close()


if __name__ == '__main__':
    unittest.main()
