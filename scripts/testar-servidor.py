#!/usr/bin/env python3
"""Teste do servidor sem hardware, só com pedidos que não gravam nada no banco.

Confia apenas nas raízes de firmware/Esp32CamRede/ServerCA.h, as mesmas da CAM, e
reaproveita uma conexão como ela. Não manda heartbeat: um heartbeat com outro
cam_boot_id enquanto a CAM real está ligada faria o servidor somar os contadores
dela duas vezes.

Uso:
  DEVICE_KEY=... python3 scripts/testar-servidor.py https://dispensario-pse.duckdns.org
  # painel também (senha do navegador + PIN):
  DEVICE_KEY=... PAINEL_USUARIO=admin PAINEL_SENHA=... ADMIN_PIN=... python3 scripts/testar-servidor.py <url>
"""
import base64
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def roots_from_header():
    text = (ROOT / "firmware/Esp32CamRede/ServerCA.h").read_text()
    lines = re.findall(r'^"(.*)\\n"$', text, re.M)
    pem = "\n".join(lines) + "\n"
    if pem.count("BEGIN CERTIFICATE") < 1:
        sys.exit("ServerCA.h sem certificado")
    return pem


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    url = urlparse(sys.argv[1])
    key = os.environ.get("DEVICE_KEY", "")
    if url.scheme != "https" or not url.hostname or not key:
        sys.exit("informe uma URL https:// e DEVICE_KEY no ambiente")
    with tempfile.NamedTemporaryFile("w", suffix=".pem") as ca:
        ca.write(roots_from_header())
        ca.flush()
        context = ssl.create_default_context(cafile=ca.name)
    started = time.time()
    conn = http.client.HTTPSConnection(url.hostname, url.port or 443, context=context, timeout=10)
    try:
        conn.connect()
    except ssl.SSLCertVerificationError as error:
        sys.exit(f"FALHA: certificado não fecha nas raízes da CAM ({error.verify_message})")
    print(f"ok  TLS {conn.sock.version()} com as raízes da CAM, handshake {1000 * (time.time() - started):.0f} ms")
    failures = 0

    def check(label, method, path, headers, expected):
        nonlocal failures
        started = time.time()
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        body = response.read()
        ok = response.status == expected
        failures += not ok
        print(f"{'ok ' if ok else 'ERRO'} {label}: {response.status} (esperado {expected}), {1000 * (time.time() - started):.0f} ms")
        return body

    device = os.environ.get("DEVICE_ID", "porta01")
    body = check("chave da CAM", "GET", f"/api/device/command?device={device}", {"X-Device-Key": key}, 200)
    if body:
        print(f"     comando pendente: {json.loads(body).get('command')}")
    check("chave errada é recusada", "GET", f"/api/device/command?device={device}", {"X-Device-Key": "x" * 16}, 401)
    check("painel sem senha é recusado", "GET", "/", {}, 401)
    user, password, pin = (os.environ.get(n, "") for n in ("PAINEL_USUARIO", "PAINEL_SENHA", "ADMIN_PIN"))
    if user and password and pin:
        auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        body = check("painel com senha e PIN", "GET", "/api/admin/overview", {"Authorization": auth, "X-Admin-Pin": pin}, 200)
        if body:
            data = json.loads(body)
            for d in data["devices"]:
                age = data["server_time"] - d["seen_at"]
                print(f"     aparelho {d['device']}: visto há {age} s, fila {d['queued']}, relógio {'ok' if d['clock_synced'] else 'sem NTP'}")
            print(f"     {len(data['events'])} eventos, {len(data['users'])} IDs")
    conn.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
