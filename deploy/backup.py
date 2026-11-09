#!/usr/bin/env python3
"""Cópia consistente do banco (API de backup do SQLite) e retenção de N dias.
Uso: backup.py <banco> <pasta> [dias]. Roda pelo controle-acesso-backup.timer."""
import sqlite3, sys, time
from pathlib import Path

db, folder = Path(sys.argv[1]), Path(sys.argv[2])
keep_days = int(sys.argv[3]) if len(sys.argv) > 3 else 14
folder.mkdir(mode=0o700, parents=True, exist_ok=True)
target = folder / f"historico-{time.strftime('%Y-%m-%d')}.sqlite3"
partial = target.with_suffix(".parcial")
src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
dst = sqlite3.connect(partial)
with dst:
    src.backup(dst)
src.close()
check = dst.execute("PRAGMA integrity_check").fetchone()[0]
dst.close()
if check != "ok":
    partial.unlink()
    sys.exit(f"integridade falhou: {check}")
partial.chmod(0o600)
partial.replace(target)
cutoff = time.time() - keep_days * 86400
for old in folder.glob("historico-*.sqlite3"):
    if old.stat().st_mtime < cutoff:
        old.unlink()
print(f"backup ok: {target} ({target.stat().st_size} bytes)")
