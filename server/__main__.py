"""
Entrypoint do servidor dedicado.

Uso:
    python -m server --port 7777 [--mode vs] [--max-players 2]
                     [--token-secret <hex>] [--idle-timeout 60]

Apenas o servidor de UMA sala. O lobby HTTP (server/lobby/__main__.py)
fica em processo separado e spawna estes via systemd ou subprocess.
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import signal
import sys

from server.game_server import GameServer


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="server",
                                description="Servidor dedicado headless")
    p.add_argument("--port", type=int, default=7777, help="porta UDP")
    p.add_argument("--mode", default="vs",
                   choices=("vs", "coop", "boss"),
                   help="modo de partida")
    p.add_argument("--max-players", type=int, default=2)
    p.add_argument("--token-secret", default="",
                   help="segredo HMAC para validar tokens (vazio = aceita todos)")
    p.add_argument("--idle-timeout", type=float, default=60.0,
                   help="encerra se ficar sem jogadores por N segundos")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("server")
    log.info("iniciando game_server porta=%d modo=%s", args.port, args.mode)

    server = GameServer(
        port=args.port,
        mode=args.mode,
        max_players=args.max_players,
        token_secret=args.token_secret,
        idle_timeout=args.idle_timeout,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(*_):
        log.info("sinal recebido — encerrando")
        server.request_stop()

    # Windows: signal.SIGTERM não existe; ignoramos silenciosamente
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            signal.signal(sig, _shutdown)

    try:
        loop.run_until_complete(server.run())
    finally:
        loop.close()
    log.info("game_server encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
