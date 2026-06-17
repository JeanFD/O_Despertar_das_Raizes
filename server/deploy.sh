#!/bin/bash
# deploy.sh — rode este script no VPS após subir os arquivos
# Uso: bash server/deploy.sh

set -e

echo "=== Instalando dependências ==="
apt-get update -qq
apt-get install -y python3 python3-pip libsdl2-dev libsdl2-image-dev \
                   libsdl2-mixer-dev libsdl2-ttf-dev

pip3 install -r server/requirements_server.txt

echo "=== Criando serviços systemd ==="

# Serviço do servidor de jogo (UDP 7777)
cat > /etc/systemd/system/despertar-game.service << 'EOF'
[Unit]
Description=O Despertar das Raizes - Game Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/despertar
ExecStart=/usr/bin/python3 server/game_server.py
Restart=always
RestartSec=3
Environment=SDL_VIDEODRIVER=dummy
Environment=SDL_AUDIODRIVER=dummy

[Install]
WantedBy=multi-user.target
EOF

# Serviço do matchmaking (HTTP 8080)
cat > /etc/systemd/system/despertar-match.service << 'EOF'
[Unit]
Description=O Despertar das Raizes - Matchmaking
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/despertar
ExecStart=/usr/bin/python3 server/matchmaking.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "=== Abrindo portas no firewall ==="
ufw allow 22/tcp
ufw allow 7777/udp
ufw allow 8080/tcp
ufw --force enable

echo "=== Ativando serviços ==="
systemctl daemon-reload
systemctl enable despertar-game despertar-match
systemctl start  despertar-game despertar-match

echo ""
echo "=== Deploy concluído! ==="
echo "Status:"
systemctl status despertar-game --no-pager
systemctl status despertar-match --no-pager
