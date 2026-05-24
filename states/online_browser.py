"""
Browser de salas online (matchmaker HTTP).

Substituto WAN do discovery por broadcast UDP do modo LAN. Lista salas
do MATCHMAKER_URL configurado em settings.py. Permite criar sala nova
ou entrar em uma existente.
"""
from __future__ import annotations
import threading
import pygame

from states.base_state import BaseState
from ui.menu_ui import draw_gradient_bg, draw_title, draw_hint_bar
from network.matchmaker_client import MatchmakerClient, MatchmakerError


class OnlineBrowserState(BaseState):

    def __init__(self, game, base_url: str):
        super().__init__(game)
        self.base_url = base_url
        self.client = MatchmakerClient(base_url)
        self._rooms: list = []
        self._sel = 0
        self._status = "Conectando ao matchmaker..."
        self._error = ""
        self._tick = 0
        self._loading = True
        # nick é só um campo simples — pode virar input editável depois
        self._nick = "jogador"

    def on_enter(self):
        self._refresh()

    def _refresh(self):
        self._loading = True
        self._error = ""
        self._status = "Buscando salas..."
        threading.Thread(target=self._refresh_thread, daemon=True).start()

    def _refresh_thread(self):
        try:
            data = self.client.list_rooms()
            self._rooms = data.get("rooms", []) if isinstance(data, dict) else data
            self._status = f"{len(self._rooms)} sala(s) encontrada(s)"
        except MatchmakerError as e:
            self._error = f"Erro do matchmaker: {e}"
            self._rooms = []
        except Exception as e:
            self._error = f"Erro inesperado: {e}"
            self._rooms = []
        finally:
            self._loading = False

    # ── Eventos ────────────────────────────────────────────────────────────

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if self._loading:
            if event.key == pygame.K_ESCAPE:
                self.game.states.pop()
            return
        items = self._rooms + [{"id": "__new__", "name": "+ Criar nova sala"}]
        n = max(1, len(items))
        if event.key in (pygame.K_UP, pygame.K_w):
            self._sel = (self._sel - 1) % n
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._sel = (self._sel + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._activate(items[self._sel])
        elif event.key == pygame.K_r:
            self._refresh()
        elif event.key == pygame.K_ESCAPE:
            self.game.states.pop()

    def _activate(self, item):
        if item.get("id") == "__new__":
            threading.Thread(target=self._do_create, daemon=True).start()
        else:
            threading.Thread(target=self._do_join, args=(item["id"],),
                             daemon=True).start()

    def _do_create(self):
        self._status = "Criando sala..."
        self._loading = True
        try:
            resp = self.client.create_room(name="Sala", mode="vs",
                                           nick=self._nick, max_players=2)
            self._connect_to_server(resp)
        except MatchmakerError as e:
            self._error = f"Falha ao criar: {e}"
        finally:
            self._loading = False

    def _do_join(self, room_id: str):
        self._status = f"Entrando em {room_id}..."
        self._loading = True
        try:
            resp = self.client.join_room(room_id, nick=self._nick)
            self._connect_to_server(resp)
        except MatchmakerError as e:
            self._error = f"Falha ao entrar: {e}"
        finally:
            self._loading = False

    def _connect_to_server(self, mm_resp: dict):
        from network.online_client import OnlineClient
        from states.online_gameplay import OnlineGameplayState

        host = mm_resp["server_host"]
        port = int(mm_resp["server_port"])
        token = mm_resp.get("token", "")

        cli = OnlineClient()
        ok = cli.connect(host, port, nick=self._nick, token=token, timeout=8.0)
        if not ok:
            self._error = (f"Não conectou em {host}:{port}\n"
                           f"motivo: {cli.last_disconnect_reason or 'timeout'}")
            cli.close()
            return
        # Lança gameplay no main thread via uma flag — state machine não
        # é thread-safe. Aqui fazemos states.change diretamente porque o
        # render loop não roda enquanto _do_create/_do_join estão executando
        # de forma síncrona via thread — porém o pygame state.change é
        # idempotente. Para máxima segurança, deixamos uma flag.
        self._pending_state = OnlineGameplayState(self.game, cli, cli.my_id, cli.room_mode)

    def update(self, dt):
        self._tick += 1
        pending = getattr(self, "_pending_state", None)
        if pending is not None:
            self._pending_state = None
            self.game.states.change(pending)

    # ── Draw ──────────────────────────────────────────────────────────────

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_title(surface, "PARTIDAS ONLINE", surface.get_height() // 6)
        W, H = surface.get_size()
        f_title = pygame.font.SysFont("consolas,monospace", 18)
        f_item = pygame.font.SysFont("consolas,monospace", 22)
        f_small = pygame.font.SysFont("consolas,monospace", 14)

        # Status / erro
        if self._error:
            for i, line in enumerate(self._error.split("\n")):
                t = f_title.render(line, True, (255, 100, 100))
                surface.blit(t, (W // 2 - t.get_width() // 2,
                                 H // 2 - 150 + i * 22))
        else:
            t = f_title.render(self._status, True, (160, 200, 160))
            surface.blit(t, (W // 2 - t.get_width() // 2, H // 2 - 150))

        # Lista
        items = self._rooms + [{"id": "__new__", "name": "+ Criar nova sala"}]
        start_y = H // 2 - 80
        for i, item in enumerate(items):
            sel = (i == self._sel)
            color = (255, 220, 60) if sel else (180, 180, 200)
            prefix = "▶ " if sel else "  "
            if item.get("id") == "__new__":
                label = item["name"]
            else:
                p = item.get("players", 0)
                m = item.get("max", 2)
                label = f"{item.get('name','?')}   [{item.get('mode','?').upper()}]   {p}/{m}"
            t = f_item.render(prefix + label, True, color)
            surface.blit(t, (W // 2 - t.get_width() // 2, start_y + i * 36))

        # Servidor
        srv = f_small.render(f"matchmaker: {self.base_url}",
                             True, (90, 90, 110))
        surface.blit(srv, (W // 2 - srv.get_width() // 2, H - 60))

        hint = "↑↓ navegar  ENTER selecionar  R atualizar  ESC voltar"
        draw_hint_bar(surface, hint)
