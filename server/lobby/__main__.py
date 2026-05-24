"""
Entrypoint do lobby/matchmaker HTTP.

Uso:
    python -m server.lobby --port 8080 [--token-secret <hex>]
                            [--server-host <ip>]
                            [--port-range 7780-7799]

Implementação minimalista usando http.server da stdlib — sem FastAPI.
nginx faz TLS na frente.
"""
from __future__ import annotations
import argparse
import logging
import sys

from server.lobby.app import LobbyApp, serve


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="server.lobby")
    p.add_argument("--host", default="127.0.0.1",
                   help="bind host (use 127.0.0.1 atrás de nginx)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--token-secret", default="dev-secret-CHANGE-ME",
                   help="HMAC secret para gerar tokens de join")
    p.add_argument("--server-host", default="",
                   help="host público dos game_servers (visível ao jogador)")
    p.add_argument("--port-range", default="7780-7799",
                   help="faixa de portas UDP para game_servers")
    p.add_argument("--server-cmd", default="",
                   help="comando para spawnar game_server (default: python -m server)")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    lo, hi = args.port_range.split("-")
    app = LobbyApp(
        token_secret=args.token_secret,
        server_host=args.server_host or args.host,
        port_low=int(lo),
        port_high=int(hi),
        server_cmd=args.server_cmd,
    )
    serve(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
