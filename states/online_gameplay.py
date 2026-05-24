"""
Gameplay state da arquitetura 2.0 (cliente-servidor dedicado).

Diferenças vs. multiplayer_gameplay.py (legado P2P/LAN):

1. CLIENT-SIDE PREDICTION: cliente roda Simulation local com o input do
   próprio jogador. Movimento responde no MESMO frame que a tecla é
   apertada — zero input lag percebido.
2. SERVER RECONCILIATION: ao receber snapshot do servidor, cliente faz
   rollback do próprio Player e reaplica todos os inputs pendentes.
3. ENTITY INTERPOLATION: jogador remoto vive num buffer com timestamps
   reais; render fica 100 ms atrás do servidor, mas sempre fluido.
4. PROTOCOLO BINÁRIO: shared/protocol.py com msgpack + bitmask de input.
5. AMBOS OS LADOS SÃO CLIENTES: ninguém hospeda — o servidor dedicado
   roda na VPS.
"""
from __future__ import annotations
import pygame
import time
from typing import Optional

from states.base_state import BaseState
from entities.player import Player
from entities.remote_player import RemotePlayer
from systems.physics_system import PhysicsSystem
from systems.combat_system import CombatSystem
from systems.render_system import RenderSystem
from engine.camera import Camera
from engine.tick_loop import TickLoop
from world.tilemap import Tilemap
from components.health import Health
from shared.protocol import input_dict_to_bitmask
from shared.snapshot import apply_delta
from shared.interp_buffer import InterpBuffer
from shared.input_buffer import InputBuffer

FIXED_DT = 1.0 / 60.0
SNAPSHOT_RATE_DIVISOR = 2          # cliente envia input a cada 2 ticks (30 Hz)


class OnlineGameplayState(BaseState):
    """Cliente conectado a um GameServer dedicado."""

    def __init__(self, game, online_client, my_id: str, mode: str):
        super().__init__(game)
        self.net = online_client
        self.my_id = my_id            # "p1" ou "p2"
        self.opponent_id = "p2" if my_id == "p1" else "p1"
        self.mode = mode

        # Mundo replicado do servidor (mesmo tilemap simples da arena)
        self._tilemap = self._build_arena()
        self._world_w = 80 * 32
        self._world_h = 19 * 32

        self._physics = PhysicsSystem(self._tilemap)
        self._render = RenderSystem()
        self._camera = Camera(self._world_w, self._world_h)

        # Players: local (com prediction) + remoto (com interp buffer)
        spawns = {"p1": (200.0, 500.0), "p2": (1800.0, 500.0)}
        sx_local, sy_local = spawns[my_id]
        sx_rem, sy_rem = spawns[self.opponent_id]
        self._local: Player = Player(game, sx_local, sy_local, team_id=my_id)
        for ab in self._local.abilities:
            self._local.abilities[ab] = True
        self._remote: RemotePlayer = RemotePlayer(game, sx_rem, sy_rem)
        self._entities = [self._local, self._remote]
        self._camera.follow(self._local)

        # Buffers de rede
        self._input_buf = InputBuffer()
        self._interp = InterpBuffer(interp_delay=0.10, max_extrap=0.20)

        # Snapshot reconstruído (delta encoded)
        self._last_full_snap: Optional[dict] = None
        self._last_ack_input_tick = 0
        self._last_server_tick = 0

        # Para emparelhar o tick fixo
        self._loop = TickLoop(FIXED_DT, max_steps=4)
        self._tick_count = 0
        self._snap_send_counter = 0
        self._jump_edge = False
        self._disconnected = False
        self._disconnect_reason = ""
        self._paused = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def on_enter(self):
        pass

    def on_exit(self):
        if self.net:
            self.net.close()

    def _build_arena(self) -> Tilemap:
        tm = Tilemap(32)
        for gx in range(80):
            tm.add_tile(gx, 18)
        for gy in range(0, 19):
            tm.add_tile(0, gy)
            tm.add_tile(79, gy)
        return tm

    # ── Eventos de input ─────────────────────────────────────────────────

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            if self._disconnected:
                self._quit_to_menu()
            else:
                self._paused = not self._paused
            return
        if self._paused:
            if event.key == pygame.K_q:
                self._quit_to_menu()
            return
        if event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
            self._jump_edge = True
            self._local.jump_buffer = 0.10

    # ── Update — tick fixo + render dt ───────────────────────────────────

    def update(self, dt: float):
        if self._paused:
            return
        if not self.net.alive():
            if not self._disconnected:
                self._disconnected = True
                self._disconnect_reason = self.net.last_disconnect_reason or "timeout"
            return

        # 1. Processa snapshots recebidos (reconciliação + interp buffer)
        self._consume_snapshots()
        self._consume_events()

        # 2. Roda física LOCAL em ticks fixos (prediction)
        n_ticks = self._loop.step(dt)
        for _ in range(n_ticks):
            self._tick_local()

        # 3. Camera segue o player local (já predito)
        self._camera.update(dt)

    def _tick_local(self):
        """Um passo de simulação local. Apenas player local sofre física."""
        self._tick_count += 1

        # Coleta input atual e registra no buffer
        inp = self._collect_input()
        self._input_buf.push(inp)

        # Aplica input no player local (mesma rotina do single-player)
        self._local.apply_net_input(inp)

        # Física + animação só do player local. O remoto é interpolado
        # a partir do buffer — não sofre física no cliente.
        self._physics.update([self._local], FIXED_DT)
        self._local.update(FIXED_DT)

        # Envia input ao servidor (não em todo tick — divide por SNAPSHOT_RATE_DIVISOR)
        self._snap_send_counter += 1
        if self._snap_send_counter >= SNAPSHOT_RATE_DIVISOR:
            self._snap_send_counter = 0
            bitmask = input_dict_to_bitmask(inp)
            self.net.send_input(bitmask, self._input_buf.latest_tick,
                                ack_snap_tick=self._last_server_tick)

    def _collect_input(self) -> dict:
        keys = pygame.key.get_pressed()
        ju = 1 if self._jump_edge else 0
        self._jump_edge = False
        return {
            "l":  int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            "r":  int(keys[pygame.K_d] or keys[pygame.K_RIGHT]),
            "dn": int(keys[pygame.K_s] or keys[pygame.K_DOWN]),
            "sh": int(keys[pygame.K_LSHIFT]),
            "at": int(keys[pygame.K_z] or keys[pygame.K_j]),
            "rn": int(keys[pygame.K_x] or keys[pygame.K_k]),
            "pa": int(keys[pygame.K_c] or keys[pygame.K_l]),
            "ju": ju,
        }

    # ── Snapshots ────────────────────────────────────────────────────────

    def _consume_snapshots(self):
        for recv_t, msg in self.net.poll_snapshots():
            full = self._reconstruct_snapshot(msg)
            if full is None:
                continue
            self._last_server_tick = full.get("t", self._last_server_tick)
            self._last_ack_input_tick = max(self._last_ack_input_tick,
                                            int(msg.get("ack", 0)))
            # 1. RemotePlayer: empilha no buffer com timestamp de recepção
            remote_state = full.get("pl", {}).get(self.opponent_id)
            if remote_state:
                # carrega tick para resolver fora de ordem
                stamped = dict(remote_state)
                stamped["tick"] = full.get("t", 0)
                self._interp.push(stamped, recv_time=recv_t)
            # 2. Player local: reconciliação (descarta inputs aplicados,
            #    snap pra autoridade, reaplica pendentes)
            local_state = full.get("pl", {}).get(self.my_id)
            if local_state:
                self._reconcile_local(local_state)

    def _reconstruct_snapshot(self, msg: dict) -> Optional[dict]:
        """Aplica delta sobre o último snapshot completo conhecido."""
        delta = msg.get("d", {})
        base_tick = msg.get("bt", 0)
        if base_tick == 0 or self._last_full_snap is None:
            self._last_full_snap = dict(delta) if delta else None
        else:
            self._last_full_snap = apply_delta(self._last_full_snap, delta)
        if self._last_full_snap:
            self._last_full_snap["t"] = msg.get("tk", self._last_full_snap.get("t", 0))
        return self._last_full_snap

    def _reconcile_local(self, server_state: dict):
        """Reconcilia player local com autoridade do servidor."""
        ack = self._last_ack_input_tick
        # Descarta inputs já aplicados no servidor
        self._input_buf.prune_acked(ack)

        # Aplica posição autoritativa
        sx = server_state.get("x")
        sy = server_state.get("y")
        if sx is None or sy is None:
            return
        dx = sx - self._local.pos.x
        dy = sy - self._local.pos.y
        # Se a divergência é pequena, faz lerp suave em vez de teleporte.
        # Para divergência > 32 px, snap direto (provavelmente parede ou morte).
        dist2 = dx * dx + dy * dy
        if dist2 < 32 * 32:
            self._local.pos.x += dx * 0.5
            self._local.pos.y += dy * 0.5
        else:
            self._local.pos.x = sx
            self._local.pos.y = sy
        # vel também
        self._local.vel.x = server_state.get("vx", self._local.vel.x)
        self._local.vel.y = server_state.get("vy", self._local.vel.y)

        # HP autoritativo
        hp = self._local.get(Health)
        if hp and "hp" in server_state:
            hp.current = float(server_state["hp"])

        # Alive
        if "al" in server_state:
            self._local.alive = bool(server_state["al"])

        # Reaplica inputs pendentes (replay)
        for tick, inp in self._input_buf.pending():
            self._local.apply_net_input(inp)
            self._physics.update([self._local], FIXED_DT)
            self._local.update(FIXED_DT)

    def _consume_events(self):
        for ev in self.net.poll_events():
            # eventos críticos do servidor — dano, morte, round_start, etc.
            # Por enquanto só logamos; integração com VersusMatch fica para
            # quando o servidor expor o estado de match.
            pass

    # ── Render ────────────────────────────────────────────────────────────

    def draw(self, surface):
        surface.fill((15, 12, 25))
        self._tilemap.draw(surface, self._camera)

        # RemotePlayer: amostra o buffer de interpolação
        interp_state = self._interp.sample()
        if interp_state is not None:
            self._remote.apply_state(interp_state)
        self._remote.update(0.016)  # animação cosmética

        self._render.draw_entities(surface, self._entities, self._camera)
        self._draw_hud(surface)
        self._draw_net_info(surface)
        if self._paused:
            self._draw_pause(surface)
        elif self._disconnected:
            self._draw_disconnect(surface)

    def _draw_hud(self, surface):
        hp_l = self._local.get(Health)
        if hp_l:
            _bar(surface, 20, 20, 200, 16, hp_l.current, hp_l.max_hp,
                 (220, 60, 60), (60, 20, 20))
        hp_r = self._remote.get(Health)
        if hp_r:
            W = surface.get_width()
            _bar(surface, W - 220, 20, 200, 16, hp_r.current, hp_r.max_hp,
                 (50, 50, 220), (20, 20, 60))

    def _draw_net_info(self, surface):
        f = pygame.font.SysFont("consolas,monospace", 13)
        W, H = surface.get_size()
        rtt_ms = int(self.net.rtt * 1000)
        txt = f.render(
            f"ONLINE  {self.mode.upper()}  {self.my_id.upper()}  RTT {rtt_ms}ms",
            True, (90, 130, 90),
        )
        surface.blit(txt, (W - txt.get_width() - 8, H - 20))

    def _draw_pause(self, surface):
        W, H = surface.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        surface.blit(ov, (0, 0))
        f1 = pygame.font.SysFont("consolas,monospace", 42)
        f2 = pygame.font.SysFont("consolas,monospace", 22)
        t1 = f1.render("PAUSADO", True, (255, 255, 255))
        t2 = f2.render("ESC = continuar    Q = sair", True, (180, 180, 180))
        surface.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 50))
        surface.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 + 16))

    def _draw_disconnect(self, surface):
        W, H = surface.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        surface.blit(ov, (0, 0))
        f1 = pygame.font.SysFont("consolas,monospace", 38)
        f2 = pygame.font.SysFont("consolas,monospace", 22)
        t1 = f1.render("Conexão Perdida", True, (255, 80, 80))
        sub = f"motivo: {self._disconnect_reason or 'timeout'}"
        t2 = f2.render(sub + "   —   ESC para voltar", True, (200, 200, 200))
        surface.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 40))
        surface.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 + 20))

    def _quit_to_menu(self):
        from states.main_menu import MainMenu
        self.game.states.change(MainMenu(self.game))


def _bar(surf, x, y, w, h, cur, mx, fg, bg):
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=4)
    fill = int(w * (max(0.0, cur) / max(mx, 1)))
    if fill:
        pygame.draw.rect(surf, fg, (x, y, fill, h), border_radius=4)
    pygame.draw.rect(surf, (255, 255, 255), (x, y, w, h), 1, border_radius=4)
