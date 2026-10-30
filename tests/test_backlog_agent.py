import importlib.util
import socket
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location(
    'backlog_server', Path(__file__).resolve().parents[1] / 'servidor/server.py'
)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class BacklogTests(unittest.TestCase):
    def test_listen_uses_connection_limit_during_initialization(self):
        class SmallServer(server.BoundedHTTPServer):
            max_connections = 3

        original_listen = socket.socket.listen
        calls = []

        def listen(sock, backlog):
            calls.append(backlog)
            return original_listen(sock, backlog)

        with mock.patch.object(socket.socket, 'listen', listen):
            httpd = SmallServer(('127.0.0.1', 0), server.Handler)
        try:
            self.assertEqual(calls, [3])
            self.assertEqual(httpd.request_queue_size, httpd.max_connections)
        finally:
            httpd.server_close()

    def test_full_connection_limit_rejects_and_releases_on_dispatch_error(self):
        class SmallServer(server.BoundedHTTPServer):
            max_connections = 2

        httpd = SmallServer(('127.0.0.1', 0), server.Handler)
        try:
            self.assertTrue(httpd._slots.acquire(blocking=False))
            self.assertTrue(httpd._slots.acquire(blocking=False))
            request = object()
            with mock.patch.object(httpd, 'shutdown_request') as shutdown, \
                 mock.patch.object(server.ThreadingHTTPServer, 'process_request') as dispatch:
                httpd.process_request(request, ('127.0.0.1', 1))
                shutdown.assert_called_once_with(request)
                dispatch.assert_not_called()
            httpd._slots.release()
            with mock.patch.object(server.ThreadingHTTPServer, 'process_request', side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    httpd.process_request(request, ('127.0.0.1', 1))
            self.assertTrue(httpd._slots.acquire(blocking=False))
            self.assertFalse(httpd._slots.acquire(blocking=False))
        finally:
            httpd.server_close()
