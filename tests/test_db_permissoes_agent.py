import concurrent.futures
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("access_server_permissions", ROOT / "servidor/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@unittest.skipUnless(os.name == "posix", "permissões POSIX")
class DatabasePermissionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.sqlite3"

    def test_new_database_is_private_with_permissive_umask(self):
        # Isolar umask em processo filho: não afeta outras threads do teste.
        script = """import importlib.util, os, sys
os.umask(0)
spec = importlib.util.spec_from_file_location('server', sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.App(sys.argv[2], '1234567890', 'device-test')
"""
        subprocess.run([sys.executable, "-c", script, str(ROOT / "servidor/server.py"), str(self.path)], check=True)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_existing_database_permissions_and_contents_are_preserved(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE existing (value TEXT)")
            db.execute("INSERT INTO existing VALUES ('preservado')")
        self.path.chmod(0o644)
        app = server.App(self.path, "1234567890", "device-test")
        with app.connect() as db:
            self.assertEqual(db.execute("SELECT value FROM existing").fetchone()[0], "preservado")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)

    def test_concurrent_connections_create_one_private_database(self):
        app = server.App.__new__(server.App)
        app.database = str(self.path)
        def open_connection(_):
            with app.connect() as db:
                return db.execute("SELECT 1").fetchone()[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(list(pool.map(open_connection, range(24))), [1] * 24)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_creation_errors_are_not_ignored(self):
        app = server.App.__new__(server.App)
        app.database = str(self.path)
        with patch.object(server.os, "open", side_effect=PermissionError("denied")), \
             patch.object(server.sqlite3, "connect") as connect:
            with self.assertRaises(PermissionError):
                app.connect()
            connect.assert_not_called()

    def test_sqlite_special_names_are_not_created_as_files(self):
        app = server.App.__new__(server.App)
        for name in ("", ":memory:"):
            app.database = name
            with patch.object(server.os, "open", side_effect=AssertionError("unexpected file creation")):
                with self.assertRaisesRegex(ValueError, "persistente"):
                    app.connect()


if __name__ == "__main__":
    unittest.main()
