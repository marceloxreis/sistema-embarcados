import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('uri_server', ROOT / 'servidor/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class DatabaseUriTests(unittest.TestCase):
    def test_uri_rejected_before_files_created_with_permissive_umask(self):
        with tempfile.TemporaryDirectory() as temp:
            script = '''import importlib.util, os, sys
os.umask(0)
os.chdir(sys.argv[2])
spec = importlib.util.spec_from_file_location("server", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
try:
    m.App("file:actual.db?mode=rwc", "1234567890", "device-test")
except ValueError:
    pass
else:
    raise AssertionError("URI accepted")
'''
            subprocess.run([sys.executable, '-c', script, str(ROOT / 'servidor/server.py'), temp], check=True)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_uri_existing_target_is_not_modified(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'existing.sqlite'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE original (value TEXT)')
                db.execute("INSERT INTO original VALUES ('preservado')")
            path.chmod(0o644)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                server.App(f'file:{path}?mode=rwc', '1234567890', 'device-test')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_literal_special_filename_and_existing_database(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'file:literal?name.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE original (value TEXT)')
                db.execute("INSERT INTO original VALUES ('preservado')")
            path.chmod(0o644)
            app = server.App(path, '1234567890', 'device-test')
            with app.connect() as db:
                self.assertEqual(db.execute('SELECT value FROM original').fetchone()[0], 'preservado')
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_database_directory_lost_after_startup(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'data'
            directory.mkdir()
            path = directory / 'db.sqlite'
            app = server.App(path, '1234567890', 'device-test')
            httpd = server.make_server('127.0.0.1', 0, app)
            thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            self.addCleanup(thread.join)
            self.addCleanup(httpd.server_close)
            self.addCleanup(httpd.shutdown)
            path.rename(Path(temp) / 'saved.sqlite')
            directory.rmdir()
            base = f'http://127.0.0.1:{httpd.server_port}'
            def request(path, data=None, auth=True):
                headers = {'Content-Type': 'application/json'}
                if auth:
                    headers['X-Admin-Pin'] = '1234567890'
                try:
                    response = urlopen(Request(base + path, None if data is None else json.dumps(data).encode(), headers), timeout=3)
                except HTTPError as error:
                    response = error
                with response:
                    return response.status, json.loads(response.read())
            self.assertEqual(request('/api/admin/overview', auth=False)[0], 401)
            self.assertEqual(request('/api/admin/overview')[0], 503)
            payload = {'device': 'porta01', 'user_id': 1, 'pin': '123456', 'confirmation': '123456'}
            self.assertEqual(request('/api/admin/reset', payload, False)[0], 401)
            self.assertEqual(request('/api/admin/reset', payload)[0], 503)
            with sqlite3.connect(Path(temp) / 'saved.sqlite') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM commands').fetchone()[0], 0)
            self.assertFalse(directory.exists())

if __name__ == '__main__':
    unittest.main()
