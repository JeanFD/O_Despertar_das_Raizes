# Deploy

Scripts e unidades systemd para subir o servidor dedicado em uma VPS Linux.

## install.sh — provisionamento idempotente

Roda como root na VPS recém-contratada. Faz:

- update do sistema
- usuário não-root `odr` com sudo
- firewall (ufw): SSH/HTTP/HTTPS + UDP 7780-7799
- fail2ban + unattended-upgrades
- timezone America/Sao_Paulo, NTP on
- clone/pull do repositório
- venv com dependências do servidor (`requirements-server.txt`)
- gera segredo HMAC em `/etc/odr/secret`
- escreve unit do lobby (sem usar o template — embutida com substituições)
- nginx como reverse proxy
- TLS opcional com certbot

Uso:
```bash
sudo bash deploy/install.sh --domain despertarraizes.com.br --email voce@email.com
```

## odr-lobby.service + odr-server@.service

Alternativa "limpa" às units embutidas pelo install.sh — para quem prefere
copiar manualmente. O lobby spawna game_servers como subprocess; em produção
você pode trocar para `systemctl start odr-server@7780` se quiser controle
mais granular.

## Operação

```bash
systemctl status odr-lobby
systemctl restart odr-lobby
journalctl -u odr-lobby -f
curl http://localhost/api/health
```

Atualizar código:
```bash
sudo -u odr git -C /home/odr/O_Despertar_das_Raizes pull
sudo -u odr /home/odr/O_Despertar_das_Raizes/.venv/bin/pip install \
  -r /home/odr/O_Despertar_das_Raizes/requirements-server.txt
sudo systemctl restart odr-lobby
```
