#!/usr/bin/env bash
#
# Provisionamento idempotente da VPS para o servidor dedicado.
#
# Uso (como root):
#   curl -fsSL <url-deste-arquivo> | bash -s -- --domain example.com --email a@b.c
#
# Ou clonando o repo:
#   sudo bash deploy/install.sh --domain example.com --email a@b.c
#
# Pode rodar de novo — detecta o que já foi feito e pula.

set -euo pipefail

# ── Args ───────────────────────────────────────────────────────────────────
DOMAIN=""
EMAIL=""
REPO_URL="${REPO_URL:-https://github.com/JeanFD/O_Despertar_das_Raizes.git}"
ODR_USER="${ODR_USER:-odr}"
ODR_HOME="/home/${ODR_USER}"
ODR_DIR="${ODR_HOME}/O_Despertar_das_Raizes"
PYTHON="python3.11"
PORT_RANGE_LOW=7780
PORT_RANGE_HIGH=7799
LOBBY_PORT=8080

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)         DOMAIN="$2"; shift 2 ;;
    --email)          EMAIL="$2"; shift 2 ;;
    --no-tls)         DOMAIN=""; shift ;;
    *) echo "argumento desconhecido: $1"; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Este script precisa rodar como root. Use: sudo bash $0 ..."
  exit 1
fi

step() { echo -e "\n\033[1;34m== $* ==\033[0m"; }
ok()   { echo -e "  \033[32m✓ $*\033[0m"; }
skip() { echo -e "  \033[33m· $* (já feito)\033[0m"; }

# ── 1. Atualização do sistema ──────────────────────────────────────────────
step "atualizando pacotes"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get -yq upgrade
apt-get -yq install $PYTHON ${PYTHON}-venv ${PYTHON}-pip git nginx \
                   ufw fail2ban certbot python3-certbot-nginx \
                   htop ca-certificates unattended-upgrades
ok "pacotes instalados"

# ── 2. Usuário sem-privilégio ──────────────────────────────────────────────
step "usuário ${ODR_USER}"
if id "$ODR_USER" &>/dev/null; then
  skip "usuário existe"
else
  adduser --disabled-password --gecos "" "$ODR_USER"
  usermod -aG sudo "$ODR_USER"
  ok "usuário criado"
fi

# ── 3. Firewall ────────────────────────────────────────────────────────────
step "firewall (ufw)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow ${PORT_RANGE_LOW}:${PORT_RANGE_HIGH}/udp
ufw --force enable
ok "ufw aplicado (22, 80, 443 tcp + ${PORT_RANGE_LOW}-${PORT_RANGE_HIGH} udp)"

# ── 4. fail2ban + unattended-upgrades ──────────────────────────────────────
step "fail2ban + auto-updates"
systemctl enable --now fail2ban >/dev/null
echo 'APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";' > /etc/apt/apt.conf.d/20auto-upgrades
ok "fail2ban ativo, auto-updates habilitados"

# ── 5. NTP / timezone ──────────────────────────────────────────────────────
step "relógio"
timedatectl set-timezone America/Sao_Paulo || true
timedatectl set-ntp true || true
ok "timezone=America/Sao_Paulo, ntp=on"

# ── 6. Clone / pull do repo ────────────────────────────────────────────────
step "código do jogo"
if [[ -d "$ODR_DIR/.git" ]]; then
  sudo -u "$ODR_USER" git -C "$ODR_DIR" pull --ff-only
  skip "repo já existia — fez git pull"
else
  sudo -u "$ODR_USER" git clone "$REPO_URL" "$ODR_DIR"
  ok "clonado em $ODR_DIR"
fi

# ── 7. venv + dependências do servidor ─────────────────────────────────────
step "venv e dependências"
if [[ ! -d "$ODR_DIR/.venv" ]]; then
  sudo -u "$ODR_USER" $PYTHON -m venv "$ODR_DIR/.venv"
fi
sudo -u "$ODR_USER" bash -lc "
  cd '$ODR_DIR'
  . .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements-server.txt
"
ok "dependências instaladas"

# ── 8. systemd units ───────────────────────────────────────────────────────
step "systemd units"

# Gera token-secret persistente em /etc/odr/secret
mkdir -p /etc/odr
if [[ ! -f /etc/odr/secret ]]; then
  python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/odr/secret
  chmod 600 /etc/odr/secret
fi
TOKEN_SECRET="$(cat /etc/odr/secret)"

cat > /etc/systemd/system/odr-lobby.service <<EOF
[Unit]
Description=O Despertar das Raizes — Lobby HTTP
After=network.target

[Service]
Type=simple
User=$ODR_USER
WorkingDirectory=$ODR_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$ODR_DIR/.venv/bin/python -m server.lobby \\
  --host 127.0.0.1 --port $LOBBY_PORT \\
  --server-host ${DOMAIN:-127.0.0.1} \\
  --port-range ${PORT_RANGE_LOW}-${PORT_RANGE_HIGH} \\
  --server-cmd "$ODR_DIR/.venv/bin/python -m server" \\
  --token-secret $TOKEN_SECRET
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
ok "/etc/systemd/system/odr-lobby.service"

systemctl daemon-reload
systemctl enable --now odr-lobby
ok "odr-lobby ativo"

# ── 9. Nginx ───────────────────────────────────────────────────────────────
step "nginx"
SERVER_NAME="${DOMAIN:-_}"
cat > /etc/nginx/sites-available/odr <<EOF
server {
    listen 80;
    server_name ${SERVER_NAME};

    location /api/ {
        proxy_pass http://127.0.0.1:${LOBBY_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location / {
        return 200 "odr ok\\n";
        add_header Content-Type text/plain;
    }
}
EOF
ln -sf /etc/nginx/sites-available/odr /etc/nginx/sites-enabled/odr
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
ok "nginx reload"

# ── 10. TLS (Let's Encrypt) ────────────────────────────────────────────────
if [[ -n "$DOMAIN" && -n "$EMAIL" ]]; then
  step "TLS para $DOMAIN"
  certbot --nginx --non-interactive --agree-tos \
    -m "$EMAIL" -d "$DOMAIN" || echo "certbot falhou — continue manualmente"
  ok "TLS configurado (ou tentativa registrada)"
else
  skip "TLS pulado — passe --domain e --email para emitir"
fi

# ── Resumo ─────────────────────────────────────────────────────────────────
echo
echo "============================================================"
echo "  PROVISIONAMENTO CONCLUÍDO"
echo "============================================================"
echo "  Usuário do serviço: $ODR_USER"
echo "  Repositório:        $ODR_DIR"
echo "  Lobby HTTP:         http://127.0.0.1:$LOBBY_PORT  (atrás do nginx)"
echo "  Portas UDP de jogo: ${PORT_RANGE_LOW}-${PORT_RANGE_HIGH}"
echo "  Segredo HMAC em:    /etc/odr/secret"
echo
echo "  Verificar:"
echo "    systemctl status odr-lobby"
echo "    curl http://localhost/api/health"
echo "    journalctl -u odr-lobby -f"
echo
