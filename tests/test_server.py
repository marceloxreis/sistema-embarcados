import contextlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
from unittest import mock
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
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(poll_interval=0.01), daemon=True)
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

    def photo(self, event_id, jpeg=b"\xff\xd8test\xff\xd9", key="device-test"):
        headers = {"Content-Type": "image/jpeg", "X-Event-Id": event_id, "X-Device-Key": key}
        try:
            result = urlopen(Request(self.base + "/api/device/photo", jpeg, headers), timeout=3)
        except HTTPError as error:
            result = error
        return result.code, json.loads(result.read())

    def test_photo_requires_grant_and_auth_and_is_idempotent(self):
        event_id = "porta01-boot1-1"
        jpeg = b"\xff\xd8test\xff\xd9"
        self.assertEqual(self.photo(event_id, key="wrong")[0], 401)
        self.assertEqual(self.photo(event_id)[0], 404)
        self.enroll()
        self.assertEqual(self.photo(event_id)[0], 404)
        self.request("/api/device/events", self.event(event_id="grant", type="access_granted", method="password"), "device")
        self.assertEqual(self.photo("grant", b"bad")[0], 400)
        self.assertEqual(self.photo("grant", b"\xff\xd8" + b"x" * server.MAX_PHOTO_BYTES + b"\xff\xd9")[0], 400)
        self.assertEqual(self.photo("grant", jpeg)[0], 200)
        self.assertEqual(self.photo("grant", jpeg)[0], 200)
        events = self.request("/api/admin/overview")[1]["events"]
        self.assertEqual(next(e for e in events if e["event_id"] == "grant")["has_photo"], 1)
        self.assertEqual(self.photo("grant", b"\xff\xd8other\xff\xd9")[0], 409)
        self.assertEqual(self.request("/api/admin/photo?event_id=grant", auth=None)[0], 401)
        self.assertEqual(self.request("/api/admin/photo?event_id=grant"), (200, jpeg))
        restarted = server.App(self.app.database, "1234567890", "device-test")
        with restarted.connect() as db:
            self.assertEqual(db.execute("SELECT jpeg FROM photos WHERE event_id='grant'").fetchone()[0], jpeg)

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

    def test_simultaneous_resets_create_only_one_pending_command(self):
        self.enroll()
        barrier = threading.Barrier(3)
        statuses = []
        def submit():
            barrier.wait()
            statuses.append(self.reset()[0])
        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join()
        self.assertEqual(sorted(statuses), [202, 409])
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM commands WHERE status='pending'").fetchone()[0], 1)

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

    def heartbeat(self, **changes):
        data = dict(device="porta01", boot_id="boot1", clock_synced=True, queued=0)
        data.update(changes)
        return self.request("/api/device/heartbeat", data, "device")

    def test_heartbeat_accepts_uint32_counters(self):
        for value in [0, 1, 4294967295]:
            self.assertEqual(self.heartbeat(dropped=value, rejected=value)[0], 200)
        self.assertEqual(self.heartbeat(dropped=7, rejected=3)[0], 200)
        device = self.request("/api/admin/overview")[1]["devices"][0]
        self.assertEqual((device["dropped"], device["rejected"]), (7, 3))

    def test_heartbeat_rejects_invalid_counters(self):
        invalid_values = [-1, 4294967296, True, False, "1", 1.5, None, [], {}]
        for field in ("dropped", "rejected"):
            for value in invalid_values:
                self.assertEqual(self.heartbeat(**{field: value})[0], 400, (field, value))
        # Valor inválido não altera o último estado registrado.
        self.heartbeat(dropped=5, rejected=2)
        self.assertEqual(self.heartbeat(dropped=-1)[0], 400)
        device = self.request("/api/admin/overview")[1]["devices"][0]
        self.assertEqual((device["dropped"], device["rejected"]), (5, 2))

    def test_heartbeat_without_counters_is_zero_for_old_firmware(self):
        self.heartbeat(dropped=9, rejected=9)
        self.assertEqual(self.heartbeat()[0], 200)
        device = self.request("/api/admin/overview")[1]["devices"][0]
        self.assertEqual((device["dropped"], device["rejected"]), (0, 0))

    def test_overview_exposes_counters_for_new_database(self):
        self.heartbeat(dropped=1, rejected=2)
        device = self.request("/api/admin/overview")[1]["devices"][0]
        self.assertEqual(device["dropped"], 1)
        self.assertEqual(device["rejected"], 2)

    def test_old_database_is_migrated_without_losing_rows(self):
        old_path = Path(self.temp.name) / "antigo.sqlite3"
        with sqlite3.connect(old_path) as db:
            # Schema anterior: devices sem dropped/rejected.
            db.executescript("""
                CREATE TABLE devices (
                    device TEXT PRIMARY KEY, boot_id TEXT NOT NULL, clock_synced INTEGER NOT NULL,
                    queued INTEGER NOT NULL, seen_at INTEGER NOT NULL);
                INSERT INTO devices VALUES('porta01', 'boot0', 1, 4, 1700000001);
            """)
        os.chmod(old_path, 0o640)
        migrated = server.App(old_path, "1234567890", "device-test")
        with migrated.connect() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(devices)")}
            self.assertTrue({"dropped", "rejected"} <= columns)
            row = db.execute("SELECT boot_id, queued, dropped, rejected FROM devices WHERE device='porta01'").fetchone()
            self.assertEqual(tuple(row), ("boot0", 4, 0, 0))
        # Migração é idempotente e não altera permissões de arquivo existente.
        server.App(old_path, "1234567890", "device-test")
        self.assertEqual(os.stat(old_path).st_mode & 0o777, 0o640)
        # Servidor migrado aceita o heartbeat novo e expõe os contadores.
        self.httpd.app = migrated
        self.assertEqual(self.heartbeat(dropped=3, rejected=0)[0], 200)
        device = self.request("/api/admin/overview")[1]["devices"][0]
        self.assertEqual((device["dropped"], device["rejected"]), (3, 0))

    def test_new_database_is_created_owner_only(self):
        mode = os.stat(self.app.database).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def device(self):
        with self.app.connect() as db:
            return dict(db.execute("SELECT * FROM devices WHERE device='porta01'").fetchone())

    def totals(self):
        device = self.request("/api/admin/overview")[1]["devices"][0]
        return {name: device[name] + device[f"{name}_prev"] for name in ("dropped", "rejected", "photo_rejected")}

    def test_counters_accumulate_across_boots(self):
        self.heartbeat(boot_id="boot1", dropped=5, rejected=2, photo_rejected=1)
        self.heartbeat(boot_id="boot2", dropped=3, rejected=0, photo_rejected=0)
        stored = self.device()
        self.assertEqual((stored["dropped_prev"], stored["rejected_prev"], stored["photo_rejected_prev"]), (5, 2, 1))
        self.assertEqual((stored["dropped"], stored["rejected"], stored["photo_rejected"]), (3, 0, 0))
        self.assertEqual(self.totals(), {"dropped": 8, "rejected": 2, "photo_rejected": 1})
        self.heartbeat(boot_id="boot3", dropped=1, rejected=1, photo_rejected=1)
        self.assertEqual(self.totals(), {"dropped": 9, "rejected": 3, "photo_rejected": 2})

    def test_same_cam_replaces_counters(self):
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=5, rejected=2)
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=7, rejected=2)
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=7, rejected=2)  # repetido não soma
        stored = self.device()
        self.assertEqual((stored["dropped"], stored["dropped_prev"], stored["rejected_prev"]), (7, 0, 0))
        self.assertEqual(self.totals()["dropped"], 7)
        # Queda com o mesmo cam_boot_id é reinício da CAM: o valor anterior vai para *_prev.
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=4)
        self.assertEqual(self.totals(), {"dropped": 11, "rejected": 2, "photo_rejected": 0})

    def test_old_firmware_after_reboot_keeps_totals(self):
        self.heartbeat(boot_id="boot1", dropped=4, rejected=1, photo_rejected=2)
        # Firmware antigo: sem contadores, após reboot (boot_id novo).
        self.assertEqual(self.heartbeat(boot_id="boot2")[0], 200)
        self.assertEqual(self.totals(), {"dropped": 4, "rejected": 1, "photo_rejected": 2})
        self.assertEqual((self.device()["dropped"], self.device()["photo_rejected"]), (0, 0))
        # Mesmo boot sem contadores não apaga o acumulado.
        self.heartbeat(boot_id="boot2")
        self.assertEqual(self.totals(), {"dropped": 4, "rejected": 1, "photo_rejected": 2})
        # Firmware novo no boot seguinte soma por cima.
        self.heartbeat(boot_id="boot3", dropped=1)
        self.assertEqual(self.totals(), {"dropped": 5, "rejected": 1, "photo_rejected": 2})

    def clear_device(self):
        with self.app.connect() as db:
            db.execute("DELETE FROM devices")

    def test_photo_rejected_validation(self):
        for value in [0, 1, 4294967295]:
            self.clear_device()
            self.assertEqual(self.heartbeat(photo_rejected=value)[0], 200)
        for value in [-1, 4294967296, True, False, "1", 1.5, None, [], {}]:
            self.assertEqual(self.heartbeat(photo_rejected=value)[0], 400, value)
        self.clear_device()
        self.heartbeat(photo_rejected=6)
        self.assertEqual(self.heartbeat(photo_rejected=-1)[0], 400)
        self.assertEqual(self.device()["photo_rejected"], 6)
        # Ausente conta como 0; a queda para 0 é reinício e o valor vai para *_prev.
        self.heartbeat(boot_id="boot2")
        self.assertEqual(self.device()["photo_rejected"], 0)
        self.assertEqual(self.totals()["photo_rejected"], 6)

    def test_totals_saturate_at_safe_limit(self):
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=10)
        with self.app.connect() as db:
            db.execute("UPDATE devices SET dropped=? WHERE device='porta01'", (server.MAX_TOTAL,))
        self.assertEqual(self.heartbeat(cam_boot_id="b2c3d4e5", dropped=5)[0], 200)
        self.assertEqual(self.device()["dropped_prev"], server.MAX_TOTAL)
        self.assertEqual(self.heartbeat(cam_boot_id="c3d4e5f6", dropped=1)[0], 200)
        self.assertEqual(self.device()["dropped_prev"], server.MAX_TOTAL)
        self.assertEqual(self.totals()["dropped"], server.MAX_TOTAL + 1)

    def test_cam_boot_id_validation_keeps_state(self):
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=3)
        before = self.device()
        for value in ["A1B2C3D4", "a1b2c3d", "a1b2c3d45", "a1b2c3dg", "", 12345678, None, True, ["a1b2c3d4"]]:
            self.assertEqual(self.heartbeat(cam_boot_id=value, dropped=9)[0], 400, value)
        self.assertEqual(self.device(), before)
        # Ausente (firmware antigo) e id válido são aceitos.
        self.assertEqual(self.heartbeat()[0], 200)
        self.assertEqual(self.heartbeat(cam_boot_id="0f0f0f0f")[0], 200)
        self.assertEqual(self.device()["cam_boot_id"], "0f0f0f0f")

    def test_mega_boot_change_alone_does_not_accumulate(self):
        self.heartbeat(boot_id="mega1", cam_boot_id="a1b2c3d4", dropped=5, rejected=2, photo_rejected=1)
        self.heartbeat(boot_id="mega2", cam_boot_id="a1b2c3d4", dropped=5, rejected=2, photo_rejected=1)
        stored = self.device()
        self.assertEqual((stored["dropped_prev"], stored["rejected_prev"], stored["photo_rejected_prev"]), (0, 0, 0))
        self.assertEqual(self.totals(), {"dropped": 5, "rejected": 2, "photo_rejected": 1})
        self.heartbeat(boot_id="mega3", cam_boot_id="a1b2c3d4", dropped=6, rejected=2, photo_rejected=1)
        self.assertEqual(self.totals(), {"dropped": 6, "rejected": 2, "photo_rejected": 1})

    def test_cam_restart_with_same_boot_id_accumulates(self):
        self.heartbeat(boot_id="mega1", cam_boot_id="a1b2c3d4", dropped=5, rejected=2, photo_rejected=1)
        self.heartbeat(boot_id="mega1", cam_boot_id="b2c3d4e5", dropped=2, rejected=0, photo_rejected=0)
        self.assertEqual(self.totals(), {"dropped": 7, "rejected": 2, "photo_rejected": 1})
        # Mesmo cam_boot_id com contador menor também é reinício.
        self.heartbeat(boot_id="mega1", cam_boot_id="b2c3d4e5", dropped=1, rejected=0, photo_rejected=0)
        self.assertEqual(self.totals(), {"dropped": 8, "rejected": 2, "photo_rejected": 1})

    def test_first_cam_id_on_old_data_does_not_double_count(self):
        # Dados do regime antigo, sem queda: o primeiro cam_boot_id só grava.
        self.heartbeat(boot_id="mega1", dropped=5, rejected=2)
        self.heartbeat(boot_id="mega1", cam_boot_id="a1b2c3d4", dropped=5, rejected=2)
        self.assertEqual(self.totals(), {"dropped": 5, "rejected": 2, "photo_rejected": 0})
        # Com queda na transição, o valor antigo é reinício e vai para *_prev.
        self.clear_device()
        self.heartbeat(boot_id="mega1", dropped=8, rejected=2)
        self.heartbeat(boot_id="mega1", cam_boot_id="a1b2c3d4", dropped=1, rejected=0)
        self.assertEqual(self.totals(), {"dropped": 9, "rejected": 2, "photo_rejected": 0})

    def test_new_cam_id_with_equal_or_higher_counters_accumulates_previous(self):
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=0, rejected=5, photo_rejected=2)
        # Nova CAM sem queda de contador: a troca de cam_boot_id ainda é reinício.
        self.assertEqual(self.heartbeat(cam_boot_id="b2c3d4e5", dropped=0, rejected=6, photo_rejected=2)[0], 200)
        stored = self.device()
        self.assertEqual((stored["dropped_prev"], stored["rejected_prev"], stored["photo_rejected_prev"]), (0, 5, 2))
        self.assertEqual((stored["dropped"], stored["rejected"], stored["photo_rejected"]), (0, 6, 2))
        self.assertEqual(stored["cam_boot_id"], "b2c3d4e5")
        self.assertEqual(self.totals(), {"dropped": 0, "rejected": 11, "photo_rejected": 4})

    def test_heartbeat_without_cam_id_keeps_stored_id_for_next_restart(self):
        self.heartbeat(cam_boot_id="a1b2c3d4", dropped=1, rejected=5, photo_rejected=2)
        # Firmware antigo (sem cam_boot_id) não apaga o id armazenado nem soma nada.
        self.assertEqual(self.heartbeat(dropped=1, rejected=5, photo_rejected=2)[0], 200)
        self.assertEqual(self.device()["cam_boot_id"], "a1b2c3d4")
        self.assertEqual(self.totals(), {"dropped": 1, "rejected": 5, "photo_rejected": 2})
        # Depois, o id B com contadores não menores soma o valor de A.
        self.assertEqual(self.heartbeat(cam_boot_id="b2c3d4e5", dropped=1, rejected=6, photo_rejected=2)[0], 200)
        stored = self.device()
        self.assertEqual(stored["cam_boot_id"], "b2c3d4e5")
        self.assertEqual((stored["dropped_prev"], stored["rejected_prev"], stored["photo_rejected_prev"]), (1, 5, 2))
        self.assertEqual(self.totals(), {"dropped": 2, "rejected": 11, "photo_rejected": 4})

    def test_two_threads_with_different_cam_ids_neither_duplicate_nor_lose(self):
        for round_number in range(10):
            self.clear_device()
            barrier = threading.Barrier(2)
            statuses = []

            def post(cam, values):
                barrier.wait()
                dropped, rejected, photo_rejected = values
                statuses.append(self.heartbeat(boot_id="mega1", cam_boot_id=cam, dropped=dropped,
                                               rejected=rejected, photo_rejected=photo_rejected)[0])

            threads = [threading.Thread(target=post, args=("a1b2c3d4", (4, 1, 0))),
                       threading.Thread(target=post, args=("b2c3d4e5", (3, 2, 5)))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(statuses, [200, 200], round_number)
            # Qualquer ordem dá 4+3, 1+2 e 0+5: sem valor duplicado nem perdido.
            self.assertEqual(self.totals(), {"dropped": 7, "rejected": 3, "photo_rejected": 5}, round_number)
            self.assertIn(self.device()["cam_boot_id"], {"a1b2c3d4", "b2c3d4e5"})

    V1_DEVICES = """
        CREATE TABLE devices (device TEXT PRIMARY KEY, boot_id TEXT NOT NULL, clock_synced INTEGER NOT NULL,
            queued INTEGER NOT NULL, seen_at INTEGER NOT NULL);
        INSERT INTO devices VALUES('porta01', 'boot0', 1, 4, 1700000001);
    """
    V2_DEVICES = """
        CREATE TABLE devices (device TEXT PRIMARY KEY, boot_id TEXT NOT NULL, clock_synced INTEGER NOT NULL,
            queued INTEGER NOT NULL, seen_at INTEGER NOT NULL,
            dropped INTEGER NOT NULL DEFAULT 0, rejected INTEGER NOT NULL DEFAULT 0);
        INSERT INTO devices VALUES('porta01', 'boot0', 1, 4, 1700000001, 6, 2);
    """

    def legacy_database(self, name, script):
        path = Path(self.temp.name) / name
        db = sqlite3.connect(path)
        try:
            db.executescript(script)
        finally:
            db.close()
        return path

    def test_database_from_previous_version_is_migrated_and_accumulates(self):
        migrated = server.App(self.legacy_database("v2.sqlite3", self.V2_DEVICES), "1234567890", "device-test")
        self.app = self.httpd.app = migrated
        with migrated.connect() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(devices)")}
            self.assertTrue({"photo_rejected", "dropped_prev", "rejected_prev", "photo_rejected_prev"} <= columns)
            row = dict(db.execute("SELECT * FROM devices").fetchone())
        self.assertEqual((row["dropped"], row["rejected"], row["photo_rejected"]), (6, 2, 0))
        self.assertEqual((row["dropped_prev"], row["rejected_prev"], row["photo_rejected_prev"]), (0, 0, 0))
        self.assertEqual(self.heartbeat(boot_id="boot1", dropped=1)[0], 200)
        self.assertEqual(self.totals(), {"dropped": 7, "rejected": 2, "photo_rejected": 0})

    def test_database_from_first_version_is_migrated_and_accumulates(self):
        migrated = server.App(self.legacy_database("v1.sqlite3", self.V1_DEVICES), "1234567890", "device-test")
        self.app = self.httpd.app = migrated
        self.assertEqual(self.heartbeat(boot_id="boot1", dropped=2, rejected=1, photo_rejected=3)[0], 200)
        self.assertEqual(self.heartbeat(boot_id="boot2")[0], 200)
        self.assertEqual(self.totals(), {"dropped": 2, "rejected": 1, "photo_rejected": 3})

    def test_concurrent_migration_of_old_database(self):
        for round_number in range(5):
            path = self.legacy_database(f"concorrente-{round_number}.sqlite3", self.V1_DEVICES)
            barrier = threading.Barrier(2)
            errors = []

            def migrate():
                barrier.wait()
                try:
                    server.App(path, "1234567890", "device-test")
                except Exception as error:  # a falha deve aparecer no teste
                    errors.append(error)

            threads = [threading.Thread(target=migrate) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [], round_number)
            with sqlite3.connect(path) as db:
                columns = [row[1] for row in db.execute("PRAGMA table_info(devices)")]
                row = db.execute("SELECT queued, dropped, photo_rejected FROM devices").fetchone()
            self.assertEqual(len(columns), len(set(columns)))
            self.assertEqual(tuple(row), (4, 0, 0))

    def test_migration_error_on_read_only_database(self):
        path = self.legacy_database("somente-leitura.sqlite3", self.V2_DEVICES)
        os.chmod(path, 0o444)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                server.App(path, "1234567890", "device-test")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o444)
        finally:
            os.chmod(path, 0o600)

    def run_cli(self, database):
        environment = {"PATH": os.environ.get("PATH", ""), "ADMIN_PIN": "1234567890",
                       "DEVICE_KEY": "device-test-key-123"}
        return subprocess.run([sys.executable, str(ROOT / "servidor/server.py"), "--db", str(database), "--port", "0"],
                              env=environment, capture_output=True, text=True, timeout=30)

    def test_cli_reports_database_error_without_traceback(self):
        path = self.legacy_database("cli-somente-leitura.sqlite3", self.V2_DEVICES)
        os.chmod(path, 0o444)
        try:
            result = self.run_cli(path)
        finally:
            os.chmod(path, 0o600)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("não foi possível abrir ou migrar o banco", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        result = self.run_cli(Path(self.temp.name) / "pasta-inexistente" / "banco.sqlite3")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_render_shows_accumulated_totals_and_persistent_warning(self):
        if shutil.which("node") is None:
            message = "node não encontrado: render() do app.js ficou sem cobertura."
            if os.environ.get("CONTROLE_TEST_STRICT") == "1":
                self.fail(message)
            self.skipTest(message)
        base = {"device": "porta01", "boot_id": "boot1", "clock_synced": True, "queued": 0, "seen_at": 1700000100,
                "dropped": 0, "rejected": 0, "photo_rejected": 0, "dropped_prev": 0, "rejected_prev": 0, "photo_rejected_prev": 0}
        scenarios = [
            {**base, "dropped": 2, "rejected": 1},
            {**base, "rejected_prev": 3},
            {**base},
            {**base, "photo_rejected": 1, "photo_rejected_prev": 3},
            {**base, "dropped": 5, "dropped_prev": 7},
            {**base, "rejected": 9007199254740991, "rejected_prev": 5},
            None,
        ]
        payload = json.dumps([{"overview": {"devices": [d] if d else [], "users": [], "events": [], "commands": [],
                                            "server_time": 1700000110}} for d in scenarios])
        result = subprocess.run(["node", "-e", JS_RENDER_HARNESS, str(ROOT / "servidor/static/app.js"), payload],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        current, earlier, clean, photo, dropped_only, saturated, absent = json.loads(result.stdout)
        # "dropped" é reservado no firmware: não aparece no painel nem no aviso.
        self.assertIn("Descartados após rejeição definitiva: 1 (", current["device-counters"]["text"])
        self.assertNotIn("fila cheia", current["device-counters"]["text"])
        self.assertFalse(current["device-loss"]["hidden"])
        self.assertNotIn("reinicializações anteriores", current["device-loss"]["text"])
        self.assertFalse(earlier["device-loss"]["hidden"])
        self.assertIn("Descartados após rejeição definitiva: 3 (", earlier["device-counters"]["text"])
        self.assertIn("reinicializações anteriores", earlier["device-loss"]["text"])
        self.assertTrue(clean["device-loss"]["hidden"])
        self.assertEqual(clean["device-loss"]["text"], "")
        self.assertIn("Descartados após rejeição definitiva: 0 (", clean["device-counters"]["text"])
        self.assertIn("Eventos aceitos sem foto por rejeição definitiva: 0.", clean["device-photo-loss"]["text"])
        # Eventos aceitos sem foto também geram aviso persistente, em linha separada.
        self.assertFalse(photo["device-loss"]["hidden"])
        self.assertIn("aparecem no histórico sem imagem", photo["device-loss"]["text"])
        self.assertNotIn("Eventos descartados", photo["device-loss"]["text"])
        self.assertIn("Eventos aceitos sem foto por rejeição definitiva: 4.", photo["device-photo-loss"]["text"])
        self.assertTrue(dropped_only["device-loss"]["hidden"])
        self.assertIn("Descartados após rejeição definitiva: 0 (", dropped_only["device-counters"]["text"])
        # Soma de exibição limitada a Number.MAX_SAFE_INTEGER.
        self.assertIn("Descartados após rejeição definitiva: 9007199254740991 (", saturated["device-counters"]["text"])
        self.assertTrue(absent["device-counters"]["hidden"])
        self.assertTrue(absent["device-photo-loss"]["hidden"])
        self.assertTrue(absent["device-loss"]["hidden"])

    @contextlib.contextmanager
    def connection_factory(self, factory):
        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            return real_connect(*args, factory=factory, **kwargs)

        with mock.patch.object(sqlite3, "connect", connect):
            yield

    def snapshot(self, path):
        db = sqlite3.connect(path)
        try:
            columns = [row[1] for row in db.execute("PRAGMA table_info(devices)")]
            return columns, db.execute("SELECT * FROM devices").fetchall()
        finally:
            db.close()

    BAD_COLUMNS = (("dropped", "INTEGER NOT NULL DEFAULT 0"), ("bogus", "NOT A TYPE (("))

    def test_failed_migration_rolls_back_and_leaves_database_unchanged(self):
        path = self.legacy_database("falha-migracao.sqlite3", self.V1_DEVICES)
        before = self.snapshot(path)
        # Falha no meio da migração: a primeira coluna já foi acrescentada na transação.
        with mock.patch.object(server, "DEVICE_COLUMNS", self.BAD_COLUMNS):
            with self.assertRaises(sqlite3.OperationalError):
                server.App(path, "1234567890", "device-test")
        self.assertEqual(self.snapshot(path), before)
        # Nenhuma transação ficou aberta: outra conexão consegue gravar.
        db = sqlite3.connect(path, timeout=1)
        try:
            db.execute("CREATE TABLE sonda (x INTEGER)")
            db.commit()
        finally:
            db.close()

    def test_failed_rollback_does_not_mask_migration_error(self):
        class BrokenRollback(sqlite3.Connection):
            def rollback(self):
                raise sqlite3.OperationalError("rollback quebrado")

        path = self.legacy_database("rollback-quebrado.sqlite3", self.V1_DEVICES)
        with self.connection_factory(BrokenRollback), mock.patch.object(server, "DEVICE_COLUMNS", self.BAD_COLUMNS):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                server.App(path, "1234567890", "device-test")
        self.assertNotIn("rollback quebrado", str(caught.exception))
        self.assertIn("syntax error", str(caught.exception))

    def test_duplicate_column_race_is_tolerated(self):
        path = self.legacy_database("coluna-duplicada.sqlite3", self.V1_DEVICES)
        server.App(path, "1234567890", "device-test")  # esquema completo
        columns_before = self.snapshot(path)[0]

        class StalePragma(sqlite3.Connection):
            # Simula outro processo que criou as colunas depois da leitura do PRAGMA.
            def execute(self, sql, parameters=(), /):
                if sql == "PRAGMA table_info(devices)":
                    return [{"name": name} for name in ("device", "boot_id", "clock_synced", "queued", "seen_at")]
                return super().execute(sql, parameters)

        with self.connection_factory(StalePragma):
            server.App(path, "1234567890", "device-test")
        self.assertEqual(self.snapshot(path)[0], columns_before)

    def test_connection_closes_and_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with self.app.connect() as db:
                held = db
                db.execute("INSERT INTO users VALUES('porta01', 77, 1, 1700000000)")
                raise RuntimeError("falha de teste")
        with self.assertRaises(sqlite3.ProgrammingError):
            held.execute("SELECT 1")  # conexão fechada
        with self.app.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM users WHERE user_id=77").fetchone())
            db.execute("INSERT INTO users VALUES('porta01', 78, 1, 1700000000)")  # commit ao sair
        with self.app.connect() as db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM users WHERE user_id=78").fetchone())

    def test_pending_command_older_than_ttl_expires_and_erases_pin(self):
        self.enroll()
        old = int(time.time()) - server.COMMAND_TTL - 1
        recent = int(time.time()) - 60
        with self.app.connect() as db:
            db.execute("INSERT INTO commands(device,user_id,pin,token,created_at) VALUES('porta01',1,'111111','aaaaaaaaaaaaaaaa',?)", (old,))
            db.execute("INSERT INTO commands(device,user_id,pin,token,created_at) VALUES('porta01',2,'222222','bbbbbbbbbbbbbbbb',?)", (recent,))
        command = self.request("/api/device/command?device=porta01", auth="device")[1]["command"]
        self.assertEqual(command["user_id"], 2)  # o recente continua pendente e é entregue
        overview = self.request("/api/admin/overview")[1]
        expired = [c for c in overview["commands"] if c["user_id"] == 1][0]
        self.assertEqual((expired["status"], expired["reason"]), ("rejected", "expired"))
        with self.app.connect() as db:
            self.assertIsNone(db.execute("SELECT pin FROM commands WHERE user_id=1").fetchone()[0])
            self.assertEqual(db.execute("SELECT pin FROM commands WHERE user_id=2").fetchone()[0], "222222")
        # Com o comando antigo expirado, o mesmo ID aceita novo reset (antes respondia 409).
        self.assertEqual(self.reset(user_id=1)[0], 202)

    def test_command_within_ttl_stays_pending_and_blocks_reset(self):
        self.enroll()
        created = int(time.time()) - server.COMMAND_TTL + 60
        with self.app.connect() as db:
            db.execute("INSERT INTO commands(device,user_id,pin,token,created_at) VALUES('porta01',1,'111111','aaaaaaaaaaaaaaaa',?)", (created,))
        self.assertEqual(self.request("/api/admin/reset", dict(device="porta01", user_id=1, pin="123456", confirmation="123456"))[0], 409)

    def insert_command(self, user_id, created_at, status="pending", reason="", token="aaaaaaaaaaaaaaaa"):
        with self.app.connect() as db:
            db.execute("INSERT INTO commands(device,user_id,pin,token,status,reason,created_at) VALUES('porta01',?,?,?,?,?,?)",
                       (user_id, "111111" if status == "pending" else None, token, status, reason, created_at))
            return db.execute("SELECT id FROM commands WHERE user_id=? AND token=?", (user_id, token)).fetchone()[0]

    def test_expired_command_confirmed_ok_by_device_becomes_applied(self):
        self.enroll()
        command_id = self.insert_command(1, int(time.time()) - 24 * 3600 - 5)
        self.assertIsNone(self.request("/api/device/command?device=porta01", auth="device")[1]["command"])
        ack = dict(device="porta01", command_id=command_id, ok=True, reason="ok")
        self.assertEqual(self.request("/api/device/command-result", ack, "device")[0], 200)
        overview = self.request("/api/admin/overview")[1]
        self.assertEqual((overview["commands"][0]["status"], overview["commands"][0]["reason"]), ("applied", "ok"))
        with self.app.connect() as db:
            self.assertIsNone(db.execute("SELECT pin FROM commands WHERE id=?", (command_id,)).fetchone()[0])
            self.assertIsNotNone(db.execute("SELECT finished_at FROM commands WHERE id=?", (command_id,)).fetchone()[0])

    def test_expired_command_reported_not_ok_stays_expired(self):
        self.enroll()
        command_id = self.insert_command(1, int(time.time()) - 24 * 3600 - 5)
        self.assertIsNone(self.request("/api/device/command?device=porta01", auth="device")[1]["command"])
        ack = dict(device="porta01", command_id=command_id, ok=False, reason="pin_in_use")
        self.assertEqual(self.request("/api/device/command-result", ack, "device")[0], 200)
        overview = self.request("/api/admin/overview")[1]
        self.assertEqual((overview["commands"][0]["status"], overview["commands"][0]["reason"]), ("rejected", "expired"))

    def test_expire_commands_keeps_applied_and_other_rejections(self):
        self.insert_command(1, int(time.time()) - 48 * 3600, status="applied", reason="ok", token="aaaaaaaaaaaaaaaa")
        self.insert_command(2, int(time.time()) - 48 * 3600, status="rejected", reason="pin_in_use", token="bbbbbbbbbbbbbbbb")
        with self.app.connect() as db:
            server.expire_commands(db)
            rows = db.execute("SELECT user_id, status, reason FROM commands ORDER BY user_id").fetchall()
        self.assertEqual([tuple(row) for row in rows], [(1, "applied", "ok"), (2, "rejected", "pin_in_use")])

    def test_command_ttl_contract_is_24_hours(self):
        self.enroll()
        now = int(time.time())
        self.insert_command(1, now - 24 * 3600 - 5, token="aaaaaaaaaaaaaaaa")
        self.insert_command(2, now - 23 * 3600, token="bbbbbbbbbbbbbbbb")
        command = self.request("/api/device/command?device=porta01", auth="device")[1]["command"]
        self.assertEqual(command["user_id"], 2)
        with self.app.connect() as db:
            status = dict(db.execute("SELECT user_id, status FROM commands").fetchall())
        self.assertEqual(status, {1: "rejected", 2: "pending"})

    def test_deeply_nested_json_reports_400(self):
        nested = b'{"a":' + b"[" * 5000 + b"]" * 5000 + b"}"
        headers = {"Content-Type": "application/json", "X-Device-Key": "device-test"}
        try:
            result = urlopen(Request(self.base + "/api/device/events", nested, headers), timeout=3)
        except HTTPError as error:
            result = error
        self.assertEqual(result.code, 400)
        self.assertEqual(json.loads(result.read())["error"], "JSON inválido ou corpo muito grande.")

    def test_missing_static_file_returns_404(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch.object(server, "STATIC", Path(empty)):
            self.assertEqual(self.request("/")[0], 404)
            self.assertEqual(self.request("/app.js")[0], 404)
        self.assertEqual(self.request("/")[0], 200)


# Renderiza render() do app.js com DOM falso, um cenário por contexto.
JS_RENDER_HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const [file, payload] = process.argv.slice(1);
const source = fs.readFileSync(file, 'utf8');
function element(id) {
  return { id, hidden: false, textContent: '', className: '', value: '', disabled: false, type: '', alt: '',
    replaceChildren() {}, append() {}, add() {}, addEventListener() {}, reset() {}, focus() {},
    removeAttribute() {}, querySelector() { return { disabled: false }; }, src: '' };
}
const results = JSON.parse(payload).map(scenario => {
  const elements = {};
  const document = { hidden: false,
    getElementById(id) { if (!elements[id]) elements[id] = element(id); return elements[id]; },
    createElement(tag) { return element(tag); } };
  const context = { document, console: { log() {}, error() {} },
    Option: class { constructor(text, value) { this.text = text; this.value = value; } },
    URL: { createObjectURL() { return ''; }, revokeObjectURL() {} }, fetch() { throw new Error('sem rede'); },
    setInterval() { return 0; }, clearInterval() {}, setTimeout() { return 0; }, clearTimeout() {} };
  vm.createContext(context);
  vm.runInContext(source, context);
  context.scenario = scenario.overview;
  vm.runInContext('overview = scenario; render();', context);
  const pick = id => ({ text: elements[id] ? elements[id].textContent : null, hidden: elements[id] ? elements[id].hidden : null });
  return { 'device-counters': pick('device-counters'), 'device-photo-loss': pick('device-photo-loss'), 'device-loss': pick('device-loss') };
});
process.stdout.write(JSON.stringify(results));
"""


if __name__ == "__main__":
    unittest.main()
