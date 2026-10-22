import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("access_server", ROOT / "servidor/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = server.App(Path(self.temp.name) / "test.sqlite3", "1234567890", "device-test")
        self.httpd = server.make_server("127.0.0.1", 0, self.app)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, auth="admin"):
        headers = {"Content-Type": "application/json"}
        if auth == "admin":
            headers["X-Admin-Pin"] = "1234567890"
        elif auth == "device":
            headers["X-Device-Key"] = "device-test"
        body = json.dumps(data).encode() if data is not None else None
        try:
            result = urlopen(Request(self.base + path, body, headers), timeout=3)
        except HTTPError as error:
            result = error
        raw = result.read()
        payload = json.loads(raw) if result.headers.get("Content-Type", "").startswith("application/json") else raw
        return result.code, payload

    def event(self, **changes):
        data = dict(event_id="porta01-boot1-1", device="porta01", boot_id="boot1", type="user_enrolled",
                    user_id=1, method="admin", reason="", active=True, epoch=None, uptime_ms=12000)
        data.update(changes)
        return data

    def enroll(self):
        return self.request("/api/device/events", self.event(), "device")

    def reset(self, **changes):
        data = dict(device="porta01", user_id=1, pin="012345", confirmation="012345")
        data.update(changes)
        return self.request("/api/admin/reset", data)

    def test_auth_required_and_roles_separated(self):
        self.assertEqual(self.request("/api/admin/overview", auth=None)[0], 401)
        self.assertEqual(self.request("/api/admin/overview", auth="device")[0], 401)
        self.assertEqual(self.request("/api/device/events", self.event(), "admin")[0], 401)

    def test_configuration_requires_explicit_credentials(self):
        for values in [{}, {"ADMIN_PIN": "1234567890"}, {"ADMIN_PIN": "123", "DEVICE_KEY": "x" * 16}]:
            with self.assertRaises(ValueError):
                server.settings_from_environment(values)
        values = {"ADMIN_PIN": "1234567890", "DEVICE_KEY": "sample-device-key"}
        self.assertEqual(server.settings_from_environment(values), ("1234567890", "sample-device-key", "porta01"))

    def test_page_and_script_available_without_login(self):
        self.assertIn(b"Controle de acesso", self.request("/", auth=None)[1])
        self.assertEqual(self.request("/app.js", auth=None)[0], 200)
        self.assertEqual(self.request("/style.css", auth=None)[0], 200)

    def test_event_ack_only_after_storage_and_dedup(self):
        status, payload = self.enroll()
        self.assertEqual((status, payload["accepted"]), (200, "porta01-boot1-1"))
        self.assertEqual(self.enroll()[0], 200)
        overview = self.request("/api/admin/overview")[1]
        self.assertEqual(len(overview["events"]), 1)
        self.assertEqual(overview["users"][0]["user_id"], 1)

    def test_collision_rejected(self):
        self.enroll()
        self.assertEqual(self.request("/api/device/events", self.event(user_id=2), "device")[0], 409)

    def test_soft_delete_and_reactivate_preserve_id(self):
        self.enroll()
        self.request("/api/device/events", self.event(event_id="2", type="user_disabled", active=False), "device")
        self.assertEqual(self.request("/api/admin/overview")[1]["users"][0]["active"], 0)
        self.request("/api/device/events", self.event(event_id="3", type="user_enabled"), "device")
        users = self.request("/api/admin/overview")[1]["users"]
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["active"], 1)

    def test_unknown_time_not_replaced_with_server_time(self):
        self.enroll()
        event = self.request("/api/admin/overview")[1]["events"][0]
        self.assertIsNone(event["epoch"])
        self.assertEqual(event["uptime_ms"], 12000)
        self.assertGreater(event["received_at"], 1700000000)

    def test_command_pending_until_device_confirms(self):
        self.enroll()
        status, pending = self.reset()
        self.assertEqual(status, 202)
        result = self.request("/api/device/command?device=porta01", auth="device")[1]["command"]
        self.assertEqual(result["pin"], "012345")
        self.assertEqual(result["id"], pending["command_id"])
        self.assertEqual(self.request("/api/admin/overview")[1]["commands"][0]["status"], "pending")
        ack = dict(device="porta01", command_id=result["id"], ok=True, reason="ok")
        self.assertEqual(self.request("/api/device/command-result", ack, "device")[0], 200)
        self.assertEqual(self.request("/api/device/command-result", ack, "device")[0], 200)
        self.assertIsNone(self.request("/api/device/command?device=porta01", auth="device")[1]["command"])
        self.assertEqual(self.request("/api/admin/overview")[1]["commands"][0]["status"], "applied")
        with self.app.connect() as db:
            self.assertIsNone(db.execute("SELECT pin FROM commands").fetchone()[0])

    def test_rejected_command_not_marked_applied(self):
        self.enroll()
        command_id = self.reset()[1]["command_id"]
        self.request("/api/device/command-result", dict(device="porta01", command_id=command_id, ok=False, reason="pin_in_use"), "device")
        self.assertEqual(self.request("/api/admin/overview")[1]["commands"][0]["status"], "rejected")

    def test_pending_command_identity_stays_same_across_retry_and_restart(self):
        self.enroll()
        self.reset()
        first = self.request("/api/device/command?device=porta01", auth="device")[1]["command"]
        second = self.request("/api/device/command?device=porta01", auth="device")[1]["command"]
        self.assertEqual(first, second)
        self.assertRegex(first["token"], r"^[0-9a-f]{16}$")
        restarted = server.App(self.app.database, "1234567890", "device-test")
        with restarted.connect() as db:
            self.assertEqual(db.execute("SELECT token FROM commands WHERE id=?", (first["id"],)).fetchone()[0], first["token"])

    def test_validation_and_duplicate_pending(self):
        self.assertEqual(self.reset()[0], 404)
        self.enroll()
        for changes in [dict(pin="12345"), dict(confirmation="999999"), dict(user_id=True), dict(pin="abcdef", confirmation="abcdef")]:
            self.assertEqual(self.reset(**changes)[0], 400)
        self.assertEqual(self.reset()[0], 202)
        self.assertEqual(self.reset()[0], 409)

    def test_invalid_events_and_foreign_device(self):
        for changes in [dict(type=[]), dict(user_id=101), dict(epoch=True), dict(active="true"), dict(device="outra")]:
            self.assertEqual(self.request("/api/device/events", self.event(**changes), "device")[0], 400)

    def test_no_password_exposed_in_overview(self):
        self.enroll()
        self.reset()
        raw = json.dumps(self.request("/api/admin/overview")[1])
        self.assertNotIn("012345", raw)
        self.assertNotIn("1234567890", raw)

    def test_device_status_and_snapshots(self):
        self.request("/api/device/events", self.event(type="user_snapshot"), "device")
        self.request("/api/device/heartbeat", dict(device="porta01", boot_id="boot1", clock_synced=True, queued=5), "device")
        overview = self.request("/api/admin/overview")[1]
        self.assertEqual(overview["events"], [])
        self.assertEqual(len(overview["users"]), 1)
        self.assertEqual(overview["devices"][0]["queued"], 5)

    def test_sqlite_persists_after_new_app_instance(self):
        self.enroll()
        other = server.App(self.app.database, "1234567890", "device-test")
        with other.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_filter_searches_history_before_recent_limit(self):
        self.enroll()  # ID 1 terá um registro mais antigo que os 200 seguintes.
        with self.app.connect() as db:
            db.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
                (f"new-{i}", "porta01", "boot1", "access_granted", 2, "password", "", 1, None, i, 2000000000)
                for i in range(200)
            ])
        all_events = self.request("/api/admin/overview")[1]["events"]
        self.assertEqual(len(all_events), 200)
        self.assertTrue(all(e["user_id"] == 2 for e in all_events))
        code, data = self.request("/api/admin/overview?user_id=1")
        self.assertEqual(code, 200)
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["events"][0]["user_id"], 1)
        for invalid in ["0", "101", "abc"]:
            self.assertEqual(self.request(f"/api/admin/overview?user_id={invalid}")[0], 400)


if __name__ == "__main__":
    unittest.main()
