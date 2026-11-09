"""Limite de tentativas atrás de proxy reverso local (Caddy na VM)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("access_server_proxy", ROOT / "servidor/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ProxyOrigemTests(unittest.TestCase):
    def start(self, trust_proxy):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        app = server.App(Path(self.temp.name) / "t.sqlite3", "1234567890", "device-test")
        httpd = server.make_server("127.0.0.1", 0, app, trust_proxy)
        thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.base = f"http://127.0.0.1:{httpd.server_port}"

    def heartbeat(self, key, forwarded):
        body = json.dumps({"device": "porta01", "boot_id": "b1", "clock_synced": True, "queued": 0}).encode()
        headers = {"Content-Type": "application/json", "X-Device-Key": key, "X-Forwarded-For": forwarded}
        try:
            return urlopen(Request(self.base + "/api/device/heartbeat", body, headers), timeout=3).code
        except HTTPError as error:
            return error.code

    def burn(self, forwarded):
        # Esgota as 10 tentativas do papel "device" para esta origem.
        for _ in range(10):
            self.assertEqual(self.heartbeat("errada-errada-errada", forwarded), 401)
        self.assertEqual(self.heartbeat("errada-errada-errada", forwarded), 429)

    def test_com_trust_proxy_atacante_nao_bloqueia_a_cam(self):
        self.start(trust_proxy=True)
        self.burn("203.0.113.9")
        self.assertEqual(self.heartbeat("device-test", "198.51.100.7"), 200)

    def test_usa_o_valor_mais_a_direita_do_cabecalho(self):
        # Cliente forja um IP à esquerda; o proxy acrescenta o real à direita.
        self.start(trust_proxy=True)
        self.burn("198.51.100.7, 203.0.113.9")
        self.assertEqual(self.heartbeat("device-test", "203.0.113.9, 198.51.100.7"), 200)
        self.assertEqual(self.heartbeat("device-test", "198.51.100.7, 203.0.113.9"), 429)

    def test_sem_trust_proxy_cabecalho_e_ignorado(self):
        self.start(trust_proxy=False)
        self.burn("203.0.113.9")
        self.assertEqual(self.heartbeat("device-test", "198.51.100.7"), 429)


if __name__ == "__main__":
    unittest.main()
