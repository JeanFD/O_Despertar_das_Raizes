"""
test_net.py — Diagnóstico de rede para multiplayer

Uso:
  Máquina A (host):    python test_net.py host
  Máquina B (cliente): python test_net.py client <IP_DA_MAQUINA_A>

Se aparecer "PONG recebido!" a rede está OK e o jogo vai conectar.
Se travar em "Aguardando...", o firewall está bloqueando.
"""

import socket
import sys
import time

HOST_PORT   = 7777
CLIENT_PORT = 7778
TIMEOUT     = 10.0


def get_lan_ips():
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            found.append(ip)
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except Exception:
        pass
    return found


def run_host():
    ips = get_lan_ips()
    print("=== HOST ===")
    print(f"IPs desta máquina: {', '.join(ips) if ips else 'não detectado'}")
    print(f"Aguardando PING na porta UDP {HOST_PORT}...")
    print("(Passe o IP acima para o cliente)")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", HOST_PORT))
    except OSError as e:
        print(f"\nERRO: Não foi possível abrir a porta {HOST_PORT}: {e}")
        print("Tente fechar outros programas que possam estar usando essa porta.")
        sys.exit(1)

    sock.settimeout(TIMEOUT)
    try:
        data, addr = sock.recvfrom(64)
        print(f"\nPING recebido de {addr[0]}:{addr[1]} — enviando PONG...")
        sock.sendto(b"PONG", addr)
        print("PONG enviado! Conexao OK.")
    except socket.timeout:
        print(f"\nNenhum PING recebido em {TIMEOUT}s.")
        print("Verifique se o firewall está liberando a porta UDP 7777.")
        print_firewall_tip()
    finally:
        sock.close()


def run_client(host_ip):
    print("=== CLIENTE ===")
    print(f"Enviando PING para {host_ip}:{HOST_PORT}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", CLIENT_PORT))
    except OSError as e:
        print(f"ERRO ao abrir porta local {CLIENT_PORT}: {e}")
        sys.exit(1)

    sock.settimeout(TIMEOUT)
    deadline = time.monotonic() + TIMEOUT
    received = False

    while time.monotonic() < deadline:
        try:
            sock.sendto(b"PING", (host_ip, HOST_PORT))
            sock.settimeout(1.0)
            data, addr = sock.recvfrom(64)
            if data == b"PONG":
                print(f"\nPONG recebido de {addr[0]}! Conexao OK.")
                print("A rede está funcionando. Pode usar o multiplayer no jogo.")
                received = True
                break
        except socket.timeout:
            print(".", end="", flush=True)

    if not received:
        print(f"\n\nSem resposta de {host_ip}:{HOST_PORT} em {TIMEOUT}s.")
        print("Causas mais comuns:")
        print("  1) O host ainda não rodou 'python test_net.py host'")
        print("  2) Firewall bloqueando — veja instruções abaixo")
        print("  3) IP errado — confira o IP exibido no host")
        print_firewall_tip()

    sock.close()


def print_firewall_tip():
    print("""
--- Como liberar o firewall no Windows ---
Abra o PowerShell como Administrador e cole:

  New-NetFirewallRule -DisplayName "ODespertarMP" `
    -Direction Inbound -Protocol UDP `
    -LocalPort 7777,7778 -Action Allow

Para remover depois:
  Remove-NetFirewallRule -DisplayName "ODespertarMP"
""")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("host", "client"):
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] == "host":
        run_host()
    else:
        if len(sys.argv) < 3:
            print("Uso: python test_net.py client <IP_DO_HOST>")
            sys.exit(1)
        run_client(sys.argv[2])
