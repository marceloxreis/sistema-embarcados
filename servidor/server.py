#!/usr/bin/env python3
"""Servidor local acadêmico. Python >=3.9, apenas biblioteca padrão."""
import argparse
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STATIC = Path(__file__).parent / "static"
EVENT_TYPES = {
    "device_boot", "storage_error", "user_snapshot", "user_enrolled",
    "user_disabled", "user_enabled", "password_reset", "admin_login",
    "access_granted", "access_denied", "door_opened", "door_closed",
    "entry_expired", "door_timeout", "forced_open", "enroll_failed",
}
METHODS = {"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web"}


def valid_pin(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{6}", value) is not None


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def text(value, length):
    return isinstance(value, str) and len(value) <= length


def settings_from_environment(environment):
    admin_pin = environment.get("ADMIN_PIN", "")
    device_key = environment.get("DEVICE_KEY", "")
    if not re.fullmatch(r"[0-9]{10}", admin_pin):
        raise ValueError("Defina ADMIN_PIN no ambiente com os mesmos 10 dígitos do Config.h local.")
    if len(device_key) < 16:
        raise ValueError("Defina DEVICE_KEY no ambiente com pelo menos 16 caracteres, igual ao Config.h local.")
    return admin_pin, device_key, environment.get("DEVICE_ID", "porta01")


class App:
    def __init__(self, database, admin_pin, device_key, device_id="porta01"):
        self.database, self.admin_pin = str(database), admin_pin
        self.device_key, self.device_id = device_key, device_id
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, device TEXT NOT NULL, boot_id TEXT NOT NULL,
                    type TEXT NOT NULL, user_id INTEGER NOT NULL, method TEXT NOT NULL,
                    reason TEXT NOT NULL, active INTEGER NOT NULL, epoch INTEGER,
                    uptime_ms INTEGER NOT NULL, received_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS users (
                    device TEXT NOT NULL, user_id INTEGER NOT NULL,
                    active INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    PRIMARY KEY(device, user_id));
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT NOT NULL,
                    user_id INTEGER NOT NULL, pin TEXT, token TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,
                    finished_at INTEGER);
                CREATE TABLE IF NOT EXISTS devices (
                    device TEXT PRIMARY KEY, boot_id TEXT NOT NULL, clock_synced INTEGER NOT NULL,
                    queued INTEGER NOT NULL, seen_at INTEGER NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        return db


class Handler(BaseHTTPRequestHandler):
    server_version = "ControleAcesso/1.0"

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        # Não registrar corpo nem cabeçalhos, que podem conter credenciais.
        return

    def reply(self, code, data, content_type="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, device=False):
        header = "X-Device-Key" if device else "X-Admin-Pin"
        expected = self.app.device_key if device else self.app.admin_pin
        supplied = self.headers.get(header, "")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            self.reply(401, {"error": "Autenticação necessária."})
            return False
        return True

    def body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError()
            result = json.loads(self.rfile.read(length))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, UnicodeDecodeError):
            self.reply(400, {"error": "JSON inválido ou corpo muito grande."})
            return None

    def do_GET(self):
        try:
            self.get()
        except sqlite3.Error:
            self.reply(503, {"error": "Banco indisponível; tente novamente."})

    def get(self):
        url = urlparse(self.path)
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if url.path in assets:
            name, mime = assets[url.path]
            self.reply(200, (STATIC / name).read_bytes(), mime)
            return
        if url.path == "/api/admin/overview":
            if not self.authorized():
                return
            query = parse_qs(url.query, keep_blank_values=True)
            where, parameters = "type != 'user_snapshot'", []
            if "user_id" in query:
                requested_id = query["user_id"][0]
                if not re.fullmatch(r"[0-9]{1,3}", requested_id) or not 1 <= int(requested_id) <= 100:
                    self.reply(400, {"error": "Filtro de ID deve estar entre 1 e 100."})
                    return
                where += " AND user_id=?"
                parameters.append(int(requested_id))
            with self.app.connect() as db:
                events = [dict(r) for r in db.execute(f"SELECT * FROM events WHERE {where} ORDER BY received_at DESC, rowid DESC LIMIT 200", parameters)]
                users = [dict(r) for r in db.execute("SELECT * FROM users ORDER BY user_id")]
                commands = [dict(r) for r in db.execute("SELECT id, device, user_id, status, reason, created_at, finished_at FROM commands ORDER BY id DESC LIMIT 30")]
                devices = [dict(r) for r in db.execute("SELECT * FROM devices")]
            self.reply(200, {"events": events, "users": users, "commands": commands,
                             "devices": devices, "server_time": int(time.time())})
        elif url.path == "/api/device/command":
            if not self.authorized(device=True):
                return
            device = parse_qs(url.query).get("device", [""])[0]
            if device != self.app.device_id:
                self.reply(400, {"error": "Dispositivo inválido."})
                return
            with self.app.connect() as db:
                row = db.execute("SELECT id, user_id, pin, token FROM commands WHERE device=? AND status='pending' ORDER BY id LIMIT 1", (device,)).fetchone()
            self.reply(200, {"command": dict(row) if row else None})
        else:
            self.reply(404, {"error": "Rota não encontrada."})

    def do_POST(self):
        try:
            self.post()
        except sqlite3.Error:
            self.reply(503, {"error": "Banco indisponível; tente novamente."})

    def post(self):
        path = urlparse(self.path).path
        routes = {"/api/device/events", "/api/device/heartbeat", "/api/device/command-result", "/api/admin/reset"}
        if path not in routes:
            self.reply(404, {"error": "Rota não encontrada."})
            return
        if not self.authorized(device=path.startswith("/api/device/")):
            return
        data = self.body()
        if data is None:
            return
        if path.startswith("/api/device/") and data.get("device") != self.app.device_id:
            self.reply(400, {"error": "Dispositivo inválido."})
            return
        now = int(time.time())
        if path == "/api/device/events":
            self.receive_event(data, now)
        elif path == "/api/device/heartbeat":
            if not (text(data.get("boot_id"), 32) and type(data.get("clock_synced")) is bool
                    and integer(data.get("queued"), 0, 128)):
                self.reply(400, {"error": "Status inválido."})
                return
            with self.app.connect() as db:
                db.execute("INSERT INTO devices VALUES(?,?,?,?,?) ON CONFLICT(device) DO UPDATE SET boot_id=excluded.boot_id, clock_synced=excluded.clock_synced, queued=excluded.queued, seen_at=excluded.seen_at",
                           (data["device"], data["boot_id"], data["clock_synced"], data["queued"], now))
            self.reply(200, {"ok": True})
        elif path == "/api/admin/reset":
            device, user = data.get("device"), data.get("user_id")
            if not (device == self.app.device_id and integer(user, 1, 100)
                    and valid_pin(data.get("pin")) and data.get("pin") == data.get("confirmation")):
                self.reply(400, {"error": "Informe ID válido e duas senhas iguais de 6 dígitos."})
                return
            with self.app.connect() as db:
                if not db.execute("SELECT 1 FROM users WHERE device=? AND user_id=?", (device, user)).fetchone():
                    self.reply(404, {"error": "ID ainda não recebido do ESP32."})
                    return
                if db.execute("SELECT 1 FROM commands WHERE device=? AND user_id=? AND status='pending'", (device, user)).fetchone():
                    self.reply(409, {"error": "Já existe uma alteração pendente para este ID."})
                    return
                cursor = db.execute("INSERT INTO commands(device,user_id,pin,token,created_at) VALUES(?,?,?,?,?)", (device, user, data["pin"], secrets.token_hex(8), now))
                command_id = cursor.lastrowid
            self.reply(202, {"command_id": command_id, "status": "pending"})
        else:
            if not (integer(data.get("command_id"), 1, 2147483647) and type(data.get("ok")) is bool
                    and text(data.get("reason"), 40)):
                self.reply(400, {"error": "Resultado inválido."})
                return
            with self.app.connect() as db:
                command = db.execute("SELECT status FROM commands WHERE id=? AND device=?", (data["command_id"], data["device"])).fetchone()
                if not command:
                    self.reply(404, {"error": "Comando inexistente."})
                    return
                if command["status"] == "pending":
                    db.execute("UPDATE commands SET status=?,reason=?,pin=NULL,finished_at=? WHERE id=?",
                               ("applied" if data["ok"] else "rejected", data["reason"], now, data["command_id"]))
            self.reply(200, {"accepted": data["command_id"]})

    def receive_event(self, data, now):
        epoch = data.get("epoch")
        event_type, method = data.get("type"), data.get("method")
        if not (text(data.get("event_id"), 72) and data.get("event_id")
                and text(data.get("boot_id"), 32) and data.get("boot_id")
                and isinstance(event_type, str) and event_type in EVENT_TYPES
                and isinstance(method, str) and method in METHODS
                and integer(data.get("user_id"), 0, 100)
                and text(data.get("reason"), 40) and type(data.get("active")) is bool
                and integer(data.get("uptime_ms"), 0, 4294967295)
                and (epoch is None or integer(epoch, 1700000000, 4102444800))):
            self.reply(400, {"error": "Evento inválido."})
            return
        fields = (data["event_id"], data["device"], data["boot_id"], event_type,
                  data["user_id"], method, data["reason"], data["active"], epoch, data["uptime_ms"])
        with self.app.connect() as db:
            cursor = db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)", fields + (now,))
            if not cursor.rowcount:
                existing = db.execute("SELECT event_id,device,boot_id,type,user_id,method,reason,active,epoch,uptime_ms FROM events WHERE event_id=?", (data["event_id"],)).fetchone()
                if tuple(existing) != fields:
                    self.reply(409, {"error": "ID de evento já usado com outro conteúdo."})
                    return
            elif data["user_id"] and event_type in {"user_enrolled", "user_snapshot", "user_disabled", "user_enabled"}:
                db.execute("INSERT INTO users VALUES(?,?,?,?) ON CONFLICT(device,user_id) DO UPDATE SET active=excluded.active, updated_at=excluded.updated_at",
                           (data["device"], data["user_id"], data["active"], now))
        # Confirmar somente depois de encerrar/commit da transação.
        self.reply(200, {"accepted": data["event_id"]})


def make_server(host, port, app):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = app
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 para receber ESP32 na rede local.")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=str(Path(__file__).parent / "historico.sqlite3"))
    args = parser.parse_args()
    try:
        admin_pin, device_key, device_id = settings_from_environment(os.environ)
    except ValueError as error:
        parser.error(str(error))
    app = App(args.db, admin_pin, device_key, device_id)
    server = make_server(args.host, args.port, app)
    print(f"Painel local: http://127.0.0.1:{args.port} | Escutando em {args.host}", flush=True)
    print("Protótipo para LAN. Nenhum ESP32 é simulado automaticamente.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
