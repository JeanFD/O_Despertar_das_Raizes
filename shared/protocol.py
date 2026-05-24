"""
Protocolo binário compartilhado entre cliente e servidor dedicado.

Usa msgpack quando disponível (binário, ~5x menor que JSON, parser em C).
Cai para JSON se msgpack não estiver instalado — útil para desenvolvimento
sem dependência extra; produção deve ter msgpack via requirements-server.txt.

Schema versionado (PROTOCOL_VERSION): handshake recusa cliente com versão
incompatível. Quando o wire format mudar, incrementar.
"""
from __future__ import annotations
import json
import time
from typing import Any

PROTOCOL_VERSION = 2

# ── Codec selection ──────────────────────────────────────────────────────

try:
    import msgpack  # type: ignore
    _HAS_MSGPACK = True

    def _encode_bytes(obj: Any) -> bytes:
        return msgpack.packb(obj, use_bin_type=True)

    def _decode_bytes(raw: bytes) -> Any:
        return msgpack.unpackb(raw, raw=False)
except ImportError:
    _HAS_MSGPACK = False

    def _encode_bytes(obj: Any) -> bytes:
        return json.dumps(obj, separators=(",", ":")).encode("utf-8")

    def _decode_bytes(raw: bytes) -> Any:
        return json.loads(raw.decode("utf-8"))


def codec_name() -> str:
    return "msgpack" if _HAS_MSGPACK else "json"


# ── Tipos de mensagem ────────────────────────────────────────────────────
# Strings curtas para reduzir overhead — campo "t" no envelope.

MSG_HELLO       = "HI"     # C→S handshake (com token de sala)
MSG_HELLO_ACK   = "HK"     # S→C handshake confirmado
MSG_HELLO_NACK  = "HN"     # S→C handshake recusado (token inválido, versão)
MSG_INPUT       = "I"      # C→S input do tick (30 Hz)
MSG_SNAPSHOT    = "S"      # S→C snapshot (30 Hz)
MSG_FULLSNAP    = "F"      # S→C snapshot completo (recovery)
MSG_EVENT       = "E"      # S→C ou C→S evento crítico
MSG_EVENT_ACK   = "A"      # ack de evento
MSG_PING        = "P"      # heartbeat
MSG_PONG        = "Q"      # resposta heartbeat
MSG_DISCONNECT  = "B"      # bye


# ── Encode / decode com envelope ─────────────────────────────────────────

def encode(msg_type: str, **payload) -> bytes:
    """Envelope binário: {"t": tipo, "ts": time, ...payload}."""
    packet = {"t": msg_type, "ts": time.monotonic()}
    packet.update(payload)
    return _encode_bytes(packet)


def decode(raw: bytes) -> dict:
    """Decodifica pacote. Retorna dict vazio se falhar (resistência a lixo)."""
    try:
        obj = _decode_bytes(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# ── Helpers de input ─────────────────────────────────────────────────────
# Bitmask de teclas — cabe em 1 byte. Reduz cada INP de ~80 bytes (JSON
# dict) para ~12 bytes (tick + mask + ju). Cliente envia 30 Hz, com isso
# o upstream cai pra ~360 B/s.

INP_LEFT    = 1 << 0
INP_RIGHT   = 1 << 1
INP_DOWN    = 1 << 2
INP_SHIFT   = 1 << 3
INP_ATTACK  = 1 << 4
INP_RANGED  = 1 << 5
INP_PARRY   = 1 << 6
INP_JUMP    = 1 << 7    # edge — só ativo no frame em que apertou


def input_dict_to_bitmask(inp: dict) -> int:
    """Converte input expandido para máscara compacta."""
    mask = 0
    if inp.get("l"):  mask |= INP_LEFT
    if inp.get("r"):  mask |= INP_RIGHT
    if inp.get("dn"): mask |= INP_DOWN
    if inp.get("sh"): mask |= INP_SHIFT
    if inp.get("at"): mask |= INP_ATTACK
    if inp.get("rn"): mask |= INP_RANGED
    if inp.get("pa"): mask |= INP_PARRY
    if inp.get("ju"): mask |= INP_JUMP
    return mask


def bitmask_to_input_dict(mask: int) -> dict:
    """Inverso. Servidor decodifica e passa ao Player.apply_net_input."""
    return {
        "l":  bool(mask & INP_LEFT),
        "r":  bool(mask & INP_RIGHT),
        "dn": bool(mask & INP_DOWN),
        "sh": bool(mask & INP_SHIFT),
        "at": bool(mask & INP_ATTACK),
        "rn": bool(mask & INP_RANGED),
        "pa": bool(mask & INP_PARRY),
        "ju": bool(mask & INP_JUMP),
    }
