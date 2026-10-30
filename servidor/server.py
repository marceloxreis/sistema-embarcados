#!/usr/bin/env python3
"""Servidor local acadêmico. Python >=3.9, apenas biblioteca padrão."""
import argparse
import contextlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STATIC = Path(__file__).parent / "static"
MAX_PHOTO_BYTES = 256 * 1024
EVENT_TYPES = {
    "device_boot", "storage_error", "user_snapshot", "user_enrolled",
    "user_disabled", "user_enabled", "password_reset", "admin_login",
    "access_granted", "access_denied", "door_opened", "door_closed",
    "entry_expired", "door_timeout", "forced_open", "enroll_failed",
}
METHODS = {"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web"}
# Contadores do heartbeat. Ausentes contam como 0 (firmware antigo).
COUNTER_FIELDS = ("dropped", "rejected", "photo_rejected")
# Teto dos totais acumulados: cabe em INTEGER do SQLite e continua exato em
# JavaScript (Number.MAX_SAFE_INTEGER). Evita overflow em casos absurdos.
MAX_TOTAL = 2**53 - 1
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY, device TEXT NOT NULL, boot_id TEXT NOT NULL,
        type TEXT NOT NULL, user_id INTEGER NOT NULL, method TEXT NOT NULL,
        reason TEXT NOT NULL, active INTEGER NOT NULL, epoch INTEGER,
        uptime_ms INTEGER NOT NULL, received_at INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS users (
        device TEXT NOT NULL, user_id INTEGER NOT NULL,
        active INTEGER NOT NULL, updated_at INTEGER NOT NULL,
        PRIMARY KEY(device, user_id))""",
    """CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT NOT NULL,
        user_id INTEGER NOT NULL, pin TEXT, token TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        reason TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,
        finished_at INTEGER)""",
    """CREATE TABLE IF NOT EXISTS devices (
        device TEXT PRIMARY KEY, boot_id TEXT NOT NULL, clock_synced INTEGER NOT NULL,
        queued INTEGER NOT NULL, seen_at INTEGER NOT NULL,
        dropped INTEGER NOT NULL DEFAULT 0, rejected INTEGER NOT NULL DEFAULT 0,
        photo_rejected INTEGER NOT NULL DEFAULT 0,
        dropped_prev INTEGER NOT NULL DEFAULT 0, rejected_prev INTEGER NOT NULL DEFAULT 0,
        photo_rejected_prev INTEGER NOT NULL DEFAULT 0,
        cam_boot_id TEXT NOT NULL DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS photos (
        event_id TEXT PRIMARY KEY REFERENCES events(event_id),
        jpeg BLOB NOT NULL, received_at INTEGER NOT NULL)""",
)
# Colunas acrescentadas a bancos antigos. Nomes e definições fixos no código.
DEVICE_COLUMNS = (
    ("dropped", "INTEGER NOT NULL DEFAULT 0"),
    ("rejected", "INTEGER NOT NULL DEFAULT 0"),
    ("photo_rejected", "INTEGER NOT NULL DEFAULT 0"),
    ("dropped_prev", "INTEGER NOT NULL DEFAULT 0"),
    ("rejected_prev", "INTEGER NOT NULL DEFAULT 0"),
    ("photo_rejected_prev", "INTEGER NOT NULL DEFAULT 0"),
    ("cam_boot_id", "TEXT NOT NULL DEFAULT ''"),
)


def valid_pin(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{6}", value) is not None


def valid_cam_boot_id(value):
    # Identificador do boot da CAM: 8 caracteres hexadecimais minúsculos.
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{8}", value) is not None


# Comando pendente sem confirmação após este prazo vira "rejected/expired" e perde a senha.
COMMAND_TTL = 24 * 3600


def expire_commands(db):
    # Chamar dentro da transação, antes de ler ou criar comandos. Usa o mesmo relógio de created_at.
    now = int(time.time())
    db.execute("UPDATE commands SET status='rejected',reason='expired',pin=NULL,finished_at=? "
               "WHERE status='pending' AND created_at<?", (now, now - COMMAND_TTL))


@contextlib.contextmanager
def transaction(db):
    # Commit ao sair sem erro, rollback em erro, e fecha a conexão sempre.
    # Falha no rollback não substitui a exceção original.
    try:
        yield db
        db.commit()
    except BaseException:
        try:
            db.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        db.close()


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
            # Migração em uma única transação de escrita. BEGIN IMMEDIATE antes de
            # qualquer leitura do esquema: duas inicializações concorrentes se
            # serializam e a segunda enxerga as colunas já criadas pela primeira.
            # executescript não serve aqui, pois emite COMMIT antes de rodar.
            db.execute("BEGIN IMMEDIATE")
            try:
                for statement in SCHEMA:
                    db.execute(statement)
                # Bancos antigos: CREATE TABLE IF NOT EXISTS não altera a tabela
                # existente, então acrescenta as colunas faltantes. Nomes fixos.
                columns = {row["name"] for row in db.execute("PRAGMA table_info(devices)")}
                for column, definition in DEVICE_COLUMNS:
                    if column not in columns:
                        try:
                            db.execute(f"ALTER TABLE devices ADD COLUMN {column} {definition}")
                        except sqlite3.OperationalError as error:
                            # Rede de segurança caso outro processo já tenha criado a coluna.
                            if "duplicate column name" not in str(error):
                                raise
                db.execute("COMMIT")
            except BaseException:
                try:
                    db.rollback()
                except sqlite3.Error:
                    pass  # Falha no rollback não pode substituir a exceção original.
                raise

    def connect(self):
        # Use em with: commit ao sair, rollback em erro, conexão fechada sempre.
        return transaction(self.open_connection())

    def open_connection(self):
        if self.database in ("", ":memory:"):
            raise ValueError("Informe um caminho de banco persistente; nome vazio e :memory: não são aceitos.")
        # URIs SQLite podem apontar para outro arquivo que não o criado abaixo.
        # Use caminho normal (por exemplo ./file:nome para nome literal).
        if self.database.startswith("file:"):
            raise ValueError("URIs SQLite file: não são aceitas; informe um caminho normal.")
        # A criação exclusiva restringe bancos novos, sem alterar arquivos existentes.
        # SQLite reabre o caminho: isso não impede troca de caminho/symlink e não
        # define permissões de backups.
        if os.name == "posix":
            try:
                fd = os.open(self.database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
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
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, device=False):
        header = "X-Device-Key" if device else "X-Admin-Pin"
        expected = self.app.device_key if device else self.app.admin_pin
        supplied = self.headers.get(header, "")
        valid = hmac.compare_digest(supplied.encode(), expected.encode())
        outcome = self.server.check_auth(self.client_address[0], device, valid)
        if outcome == "limited":
            self.reply(429, {"error": "Muitas tentativas; tente novamente mais tarde."})
            return False
        if not valid:
            self.reply(401, {"error": "Autenticação necessária."})
            return False
        return True

    def body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError()
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, UnicodeDecodeError, RecursionError):
            # RecursionError: JSON aninhado demais, que o decodificador não consegue percorrer.
            self.reply(400, {"error": "JSON inválido ou corpo muito grande."})
            return None

    def connect(self):
        # Converter somente falhas do acesso ao arquivo do banco, não OSError
        # de operações HTTP ou arquivos estáticos, em indisponibilidade SQLite.
        try:
            db = self.app.open_connection()
        except OSError as error:
            raise sqlite3.OperationalError("Não foi possível abrir o banco") from error
        return transaction(db)

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
            try:
                body = (STATIC / name).read_bytes()
            except OSError:
                self.reply(404, {"error": "Arquivo não encontrado."})
                return
            self.reply(200, body, mime)
            return
        if url.path == "/api/admin/photo":
            if not self.authorized():
                return
            event_id = parse_qs(url.query).get("event_id", [""])[0]
            with self.connect() as db:
                row = db.execute("SELECT jpeg FROM photos WHERE event_id=?", (event_id,)).fetchone()
            if row is None:
                self.reply(404, {"error": "Foto não encontrada."})
            else:
                self.reply(200, row["jpeg"], "image/jpeg")
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
            with self.connect() as db:
                expire_commands(db)
                events = [dict(r) for r in db.execute(f"SELECT events.*, EXISTS(SELECT 1 FROM photos WHERE photos.event_id=events.event_id) AS has_photo FROM events WHERE {where} ORDER BY received_at DESC, rowid DESC LIMIT 200", parameters)]
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
            with self.connect() as db:
                expire_commands(db)
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
        if path == "/api/device/photo":
            if self.authorized(device=True):
                self.receive_photo()
            return
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
            # Contadores são opcionais para compatibilidade com firmware antigo:
            # ausentes contam como 0; presentes precisam ser uint32 (bool é rejeitado).
            counters = {name: data.get(name, 0) for name in COUNTER_FIELDS}
            # cam_boot_id é opcional (firmware antigo não o envia); se presente, precisa ser válido.
            has_cam = "cam_boot_id" in data
            if not (text(data.get("boot_id"), 32) and type(data.get("clock_synced")) is bool
                    and integer(data.get("queued"), 0, 128)
                    and all(integer(value, 0, 4294967295) for value in counters.values())
                    and (not has_cam or valid_cam_boot_id(data["cam_boot_id"]))):
                self.reply(400, {"error": "Status inválido."})
                return
            with self.connect() as db:
                # Leitura e gravação na mesma transação de escrita.
                db.execute("BEGIN IMMEDIATE")
                stored = db.execute("SELECT * FROM devices WHERE device=?", (data["device"],)).fetchone()
                # Os contadores pertencem à CAM. Ao reiniciar a CAM, o valor armazenado
                # vai para *_prev, e os totais são prev + atual. Mudança só de boot_id
                # (Mega) não acumula. Há reinício quando o cam_boot_id muda ou quando
                # algum contador cai abaixo do armazenado (inclusive firmware antigo,
                # sem cam_boot_id, que zera os contadores ao reiniciar).
                # Transição de cam_boot_id vazio para um id novo só grava, sem somar:
                # o valor armazenado pode ser do mesmo boot da CAM, gravado antes do
                # servidor ser atualizado, e somar contaria duas vezes. Só soma se
                # algum contador cair, o que prova reinício.
                previous = {name: 0 for name in COUNTER_FIELDS}
                cam_boot_id = data["cam_boot_id"] if has_cam else ""
                if stored is not None:
                    cam_boot_id = data["cam_boot_id"] if has_cam else stored["cam_boot_id"]
                    previous = {name: stored[f"{name}_prev"] for name in COUNTER_FIELDS}
                    cam_changed = bool(stored["cam_boot_id"]) and cam_boot_id != stored["cam_boot_id"]
                    decreased = any(counters[name] < stored[name] for name in COUNTER_FIELDS)
                    if cam_changed or decreased:
                        previous = {name: min(stored[f"{name}_prev"] + stored[name], MAX_TOTAL)
                                    for name in COUNTER_FIELDS}
                db.execute("INSERT INTO devices(device,boot_id,clock_synced,queued,seen_at,"
                           "dropped,rejected,photo_rejected,dropped_prev,rejected_prev,photo_rejected_prev,cam_boot_id) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                           "ON CONFLICT(device) DO UPDATE SET boot_id=excluded.boot_id, clock_synced=excluded.clock_synced, "
                           "queued=excluded.queued, seen_at=excluded.seen_at, dropped=excluded.dropped, rejected=excluded.rejected, "
                           "photo_rejected=excluded.photo_rejected, dropped_prev=excluded.dropped_prev, "
                           "rejected_prev=excluded.rejected_prev, photo_rejected_prev=excluded.photo_rejected_prev, "
                           "cam_boot_id=excluded.cam_boot_id",
                           (data["device"], data["boot_id"], data["clock_synced"], data["queued"], now,
                            counters["dropped"], counters["rejected"], counters["photo_rejected"],
                            previous["dropped"], previous["rejected"], previous["photo_rejected"], cam_boot_id))
            self.reply(200, {"ok": True})
        elif path == "/api/admin/reset":
            device, user = data.get("device"), data.get("user_id")
            if not (device == self.app.device_id and integer(user, 1, 100)
                    and valid_pin(data.get("pin")) and data.get("pin") == data.get("confirmation")):
                self.reply(400, {"error": "Informe ID válido e duas senhas iguais de 6 dígitos."})
                return
            with self.connect() as db:
                # Serializar a verificação e a criação para não aceitar duas
                # solicitações simultâneas para o mesmo ID.
                db.execute("BEGIN IMMEDIATE")
                expire_commands(db)
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
            with self.connect() as db:
                command = db.execute("SELECT status, reason FROM commands WHERE id=? AND device=?", (data["command_id"], data["device"])).fetchone()
                if not command:
                    self.reply(404, {"error": "Comando inexistente."})
                    return
                if command["status"] == "pending":
                    db.execute("UPDATE commands SET status=?,reason=?,pin=NULL,finished_at=? WHERE id=?",
                               ("applied" if data["ok"] else "rejected", data["reason"], now, data["command_id"]))
                elif command["status"] == "rejected" and command["reason"] == "expired" and data["ok"]:
                    # Expirou no servidor, mas o Mega já trocou a senha: o resultado ok prevalece.
                    db.execute("UPDATE commands SET status='applied',reason=?,pin=NULL,finished_at=? WHERE id=?",
                               (data["reason"], now, data["command_id"]))
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
        with self.connect() as db:
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

    def receive_photo(self):
        event_id = self.headers.get("X-Event-Id", "")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not (event_id and len(event_id) <= 72 and 4 <= length <= MAX_PHOTO_BYTES
                and self.headers.get_content_type() == "image/jpeg"):
            self.reply(400, {"error": "Foto ou identificação inválida."})
            return
        jpeg = self.rfile.read(length)
        if len(jpeg) != length or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            self.reply(400, {"error": "JPEG inválido ou incompleto."})
            return
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            event = db.execute("SELECT device,type FROM events WHERE event_id=?", (event_id,)).fetchone()
            if event is None or event["device"] != self.app.device_id or event["type"] != "access_granted":
                self.reply(404, {"error": "Acesso autorizado não encontrado."})
                return
            existing = db.execute("SELECT jpeg FROM photos WHERE event_id=?", (event_id,)).fetchone()
            if existing is not None and existing["jpeg"] != jpeg:
                self.reply(409, {"error": "Evento já possui outra foto."})
                return
            if existing is None:
                db.execute("INSERT INTO photos VALUES(?,?,?)", (event_id, jpeg, int(time.time())))
        self.reply(200, {"accepted": event_id})


class BoundedHTTPServer(ThreadingHTTPServer):
    # A janela é compartilhada entre rotas do mesmo papel para impedir que
    # alternar endpoints multiplique as tentativas disponíveis.
    auth_window = 60.0
    auth_limit = 10
    auth_max_origins = 1024
    connection_deadline = 15.0
    max_connections = 32

    def __init__(self, address, handler):
        # TCPServer chama listen durante a inicialização da classe base.
        self.request_queue_size = self.max_connections
        super().__init__(address, handler)
        self._auth_lock = threading.Lock()
        self._auth_failures = {}
        self._slots = threading.BoundedSemaphore(self.max_connections)

    def check_auth(self, origin, device, valid):
        now = time.monotonic()
        key = (origin, device)
        with self._auth_lock:
            for existing, attempts in list(self._auth_failures.items()):
                remaining = [t for t in attempts if now - t < self.auth_window]
                if remaining:
                    self._auth_failures[existing] = remaining
                else:
                    del self._auth_failures[existing]
            attempts = self._auth_failures.get(key, [])
            if len(attempts) >= self.auth_limit:
                return "limited"
            if not valid:
                if key not in self._auth_failures and len(self._auth_failures) >= self.auth_max_origins:
                    return "limited"
                self._auth_failures.setdefault(key, []).append(now)
            return "ok"

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        def expire():
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        timer = None
        try:
            try:
                timer = threading.Timer(self.connection_deadline, expire)
                timer.daemon = True
                timer.start()
            except BaseException:
                try:
                    if timer is not None:
                        timer.cancel()
                finally:
                    self.shutdown_request(request)
                raise
            try:
                super().process_request_thread(request, client_address)
            finally:
                timer.cancel()
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        # O prazo pode fechar uma conexão enquanto o handler responde.
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def make_server(host, port, app):
    server = BoundedHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = app
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 para receber ESP32 na rede local.")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=str(Path(__file__).parent / "historico.sqlite3"),
                        help="Caminho do banco persistente; nome vazio, :memory: e URIs SQLite file: não são aceitos.")
    args = parser.parse_args()
    try:
        admin_pin, device_key, device_id = settings_from_environment(os.environ)
        app = App(args.db, admin_pin, device_key, device_id)
    except ValueError as error:
        parser.error(str(error))
    except (sqlite3.Error, OSError) as error:
        # Falha ao abrir ou migrar o banco: mensagem clara, sem traceback.
        print(f"Erro: não foi possível abrir ou migrar o banco '{args.db}': {error}", file=sys.stderr)
        sys.exit(1)
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
