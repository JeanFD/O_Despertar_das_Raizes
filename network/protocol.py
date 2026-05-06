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

MODE_COOP   = "coop"
MODE_BOSS   = "boss"
MODE_VERSUS = "vs"

EV_DAMAGED     = "dmg"
EV_DIED        = "died"
EV_ABILITY     = "ability"
EV_PICKUP      = "pickup"
EV_ROUND_START = "round_start"
EV_ROUND_END   = "round_end"
EV_MATCH_END   = "match_end"


def encode(msg_type: str, **payload) -> bytes:
    packet = {"t": msg_type, "ts": time.monotonic()}
    packet.update(payload)
    return json.dumps(packet, separators=(",", ":")).encode("utf-8")


def decode(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
