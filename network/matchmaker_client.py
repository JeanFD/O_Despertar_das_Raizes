"""
Cliente HTTP do lobby/matchmaker.

Conversa com server/lobby (em http://MATCHMAKER_HOST). Usa apenas stdlib
(urllib + json) para não puxar requests/httpx no cliente.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional


class MatchmakerError(Exception):
    pass


class MatchmakerClient:
    def __init__(self, base_url: str, timeout: float = 6.0):
        # base_url tipo "https://despertarraizes.com.br" (sem barra final)
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    # ── Endpoints ─────────────────────────────────────────────────────────

    def list_rooms(self) -> list:
        return self._get("/api/rooms")

    def create_room(self, name: str, mode: str, nick: str,
                    max_players: int = 2) -> dict:
        return self._post("/api/rooms", {
            "name": name, "mode": mode, "nick": nick,
            "max_players": max_players,
        })

    def join_room(self, room_id: str, nick: str) -> dict:
        return self._post(f"/api/rooms/{room_id}/join", {"nick": nick})

    def health(self) -> dict:
        return self._get("/api/health")

    # ── Internos ──────────────────────────────────────────────────────────

    def _get(self, path: str):
        return self._request("GET", path, None)

    def _post(self, path: str, body: dict):
        return self._request("POST", path, body)

    def _request(self, method: str, path: str, body: Optional[dict]):
        url = self.base + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
                msg = payload.get("error", str(e))
            except Exception:
                msg = str(e)
            raise MatchmakerError(f"{e.code}: {msg}") from None
        except urllib.error.URLError as e:
            raise MatchmakerError(f"sem conexão: {e.reason}") from None
        except Exception as e:
            raise MatchmakerError(str(e)) from None
