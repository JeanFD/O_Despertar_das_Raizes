# network/protocol.py
import json
import time

MSG_HELLO        = "HI"
MSG_HELLO_ACK    = "HI_ACK"
MSG_INPUT        = "INP"
MSG_STATE        = "ST"
MSG_EVENT        = "EV"
MSG_EVENT_ACK    = "EV_ACK"
MSG_PING         = "PING"
MSG_PONG         = "PONG"
MSG_DISCONNECT   = "BYE"

MODE_COOP = "coop"
MODE_BOSS = "boss"

EV_DAMAGED = "dmg"
EV_DIED    = "died"
EV_ABILITY = "ability"
EV_PICKUP  = "pickup"


def encode(msg_type: str, **payload) -> bytes:
    packet = {"t": msg_type, "ts": time.monotonic()}
    packet.update(payload)
    return json.dumps(packet, separators=(",", ":")).encode("utf-8")


def decode(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
