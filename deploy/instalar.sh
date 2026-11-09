#!/usr/bin/env bash
# Instala servidor + Caddy numa VM Ubuntu 24.04 limpa. Rodar na VM, como root:
#   sudo DOMINIO=controle-acesso.duckdns.org PAINEL_USUARIO=admin bash deploy/instalar.sh
# Pede a senha do painel (camada do Caddy; ou PAINEL_SENHA no ambiente) e gera ADMIN_PIN e DEVICE_KEY se ainda não existirem.
# Pode ser rodado de novo para atualizar o código: preserva /etc/controle-acesso.env e o banco.
# Opcional: DUCKDNS_TOKEN=... faz a VM manter o domínio DuckDNS no IP atual (boot e a cada 5 min).
# Instala também o backup diário do banco (03:30, 14 dias em /var/lib/controle-acesso/backups).
set -euo pipefail
: "${DOMINIO:?defina DOMINIO (ex.: controle-acesso.duckdns.org)}"
PAINEL_USUARIO="${PAINEL_USUARIO:-admin}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "rode com sudo"; exit 1; }

apt-get update -q
apt-get install -y -q python3 debian-keyring debian-archive-keyring apt-transport-https curl gnupg
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q && apt-get install -y -q caddy
fi

id controle >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin controle
install -d -m 0755 /opt/controle-acesso
rm -rf /opt/controle-acesso/servidor /opt/controle-acesso/deploy
cp -r "$REPO_DIR/servidor" "$REPO_DIR/deploy" /opt/controle-acesso/
rm -f /opt/controle-acesso/servidor/*.sqlite3*
chown -R root:root /opt/controle-acesso

ENV=/etc/controle-acesso.env
if [ ! -f "$ENV" ]; then
  PIN=$(python3 -c 'import secrets; print("".join(secrets.choice("0123456789") for _ in range(10)))')
  KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
  umask 077
  printf 'ADMIN_PIN=%s\nDEVICE_KEY=%s\nDEVICE_ID=porta01\n' "$PIN" "$KEY" > "$ENV"
  echo ">> $ENV criado. Copie DEVICE_KEY para o Config.h da CAM e ADMIN_PIN para o Config.h do Mega:"
  cat "$ENV"
fi
chown root:controle "$ENV"; chmod 0640 "$ENV"

for unit in controle-acesso.service controle-acesso-backup.service controle-acesso-backup.timer duckdns.service duckdns.timer; do
  install -m 0644 "$REPO_DIR/deploy/$unit" "/etc/systemd/system/$unit"
done
# DuckDNS opcional: DUCKDNS_TOKEN no ambiente grava o arquivo; DUCKDNS_DOMINIO sai do DOMINIO.
if [ -n "${DUCKDNS_TOKEN:-}" ]; then
  umask 077
  printf 'DUCKDNS_DOMINIO=%s\nDUCKDNS_TOKEN=%s\n' "${DOMINIO%%.duckdns.org}" "$DUCKDNS_TOKEN" > /etc/controle-acesso-duckdns.env
  chmod 0600 /etc/controle-acesso-duckdns.env
fi
systemctl daemon-reload
systemctl enable --now controle-acesso controle-acesso-backup.timer duckdns.timer
systemctl restart controle-acesso

if [ ! -f /etc/caddy/painel.hash ]; then
  if [ -n "${PAINEL_SENHA:-}" ]; then
    caddy hash-password --plaintext "$PAINEL_SENHA" > /etc/caddy/painel.hash
  else
    echo ">> Senha do painel para o usuário '$PAINEL_USUARIO' (pedida pelo navegador antes do PIN):"
    caddy hash-password > /etc/caddy/painel.hash
  fi
  chmod 0640 /etc/caddy/painel.hash; chown root:caddy /etc/caddy/painel.hash
fi
HASH=$(cat /etc/caddy/painel.hash)
sed -e "s|@DOMINIO@|$DOMINIO|g" -e "s|@PAINEL_USUARIO@|$PAINEL_USUARIO|g" -e "s|@PAINEL_HASH@|$HASH|g" \
  "$REPO_DIR/deploy/Caddyfile.modelo" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy || systemctl restart caddy

echo ">> Pronto: https://$DOMINIO  (CAM: SERVER_URL = \"https://$DOMINIO\")"
