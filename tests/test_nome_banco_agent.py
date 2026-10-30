import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'servidor/server.py'
spec = importlib.util.spec_from_file_location('nome_banco_server', SCRIPT)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class DatabaseNameTests(unittest.TestCase):
    def test_app_rejects_temporary_names(self):
        for name in ('', ':memory:'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'persistente'):
                server.App(name, '1234567890', 'device-test-key!')

    def test_cli_rejects_temporary_names_without_traceback(self):
        env = dict(os.environ, ADMIN_PIN='1234567890', DEVICE_KEY='device-test-key!')
        for name in ('', ':memory:'):
            with self.subTest(name=name):
                result = subprocess.run([sys.executable, str(SCRIPT), '--db', name], env=env,
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 2)
                self.assertIn('persistente', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_normal_path_persists_schema_across_connections(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'normal.sqlite3'
            app = server.App(path, '1234567890', 'device-test-key!')
            with app.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 0)
            self.assertTrue(path.is_file())

    def test_cli_starts_with_normal_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'normal.sqlite3'
            env = dict(os.environ, ADMIN_PIN='1234567890', DEVICE_KEY='device-test-key!')
            process = subprocess.Popen([sys.executable, str(SCRIPT), '--db', str(path), '--port', '0'],
                                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertIn('Painel local:', process.stdout.readline())
                self.assertIsNone(process.poll())
                self.assertTrue(path.is_file())
            finally:
                process.terminate()
                process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main()
