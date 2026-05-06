# engine/versus_match.py
"""
Engine de regras de uma partida Versus 1v1.

Estados (fases) de um round:
    READY     — players spawnaram, input bloqueado, pose inicial   (~1.2s)
    COUNTDOWN — banner "3 / 2 / 1 / FIGHT!", input bloqueado       (~3.0s)
    FIGHTING  — combate livre, timer corre                         (≤ROUND_TIME)
    ROUND_END — banner "K.O." ou "TIME UP", input bloqueado        (~2.5s)
    MATCH_END — banner final "PLAYER N WINS"                       (até ESC)

Regras:
- Best-of-N (default 3): vence quem fechar (N//2 + 1) rounds primeiro.
- Round termina por:
    a) HP de um lado <= 0          → outro vence o round
    b) Player saiu do mundo (ring-out) → outro vence o round
    c) Timer expira                 → vence quem tem mais HP; empate possível
- Empate de round: nenhum dos lados pontua, novo round inicia.
- Match termina quando algum dos lados atinge 'rounds_to_win'.
- Engine é puramente lógica (sem pygame). O estado é serializável.
"""

PHASE_READY     = "ready"
PHASE_COUNTDOWN = "countdown"
PHASE_FIGHTING  = "fighting"
PHASE_ROUND_END = "round_end"
PHASE_MATCH_END = "match_end"

DEFAULT_ROUND_TIME      = 60.0
DEFAULT_READY_TIME      = 1.2
DEFAULT_COUNTDOWN_TIME  = 3.0
DEFAULT_ROUND_END_TIME  = 2.5


class VersusMatch:
    """Máquina de estados de uma partida 1v1.

    Apenas o host roda esta engine de forma autoritativa. O cliente
    recebe um snapshot serializado em cada frame e/ou eventos críticos
    (round_start, round_end, match_end) com ACK.
    """

    def __init__(self,
                 best_of: int = 3,
                 round_time: float = DEFAULT_ROUND_TIME):
        self.best_of        = best_of
        self.rounds_to_win  = best_of // 2 + 1
        self.round_time     = round_time

        self.score_p1   = 0
        self.score_p2   = 0
        self.round_idx  = 1
        self.phase      = PHASE_READY
        self.timer      = DEFAULT_READY_TIME
        self.fight_left = round_time

        # Vencedor do último round / da partida.
        # 0 = empate, 1 = p1, 2 = p2, None = ainda não decidido
        self.last_round_winner: int | None = None
        self.match_winner:      int | None = None

    # ── Consulta ──────────────────────────────────────────────────────────────

    @property
    def in_match(self) -> bool:
        return self.phase != PHASE_MATCH_END

    @property
    def can_act(self) -> bool:
        """True quando os jogadores podem efetivamente lutar (input liberado)."""
        return self.phase == PHASE_FIGHTING

    def to_dict(self) -> dict:
        """Snapshot serializável para broadcast."""
        return {
            "ph":  self.phase,
            "ri":  self.round_idx,
            "s1":  self.score_p1,
            "s2":  self.score_p2,
            "tm":  round(self.timer, 3),
            "fl":  round(self.fight_left, 3),
            "lw":  self.last_round_winner,
            "mw":  self.match_winner,
            "bo":  self.best_of,
            "rtw": self.rounds_to_win,
        }

    def apply_dict(self, s: dict):
        """Aplica snapshot recebido (cliente)."""
        if not s:
            return
        self.phase              = s.get("ph", self.phase)
        self.round_idx          = s.get("ri", self.round_idx)
        self.score_p1           = s.get("s1", self.score_p1)
        self.score_p2           = s.get("s2", self.score_p2)
        self.timer              = s.get("tm", self.timer)
        self.fight_left         = s.get("fl", self.fight_left)
        self.last_round_winner  = s.get("lw", self.last_round_winner)
        self.match_winner       = s.get("mw", self.match_winner)
        self.best_of            = s.get("bo", self.best_of)
        self.rounds_to_win      = s.get("rtw", self.rounds_to_win)

    # ── Ciclo do host ─────────────────────────────────────────────────────────

    def tick(self,
             dt: float,
             p1_alive: bool, p1_hp: float,
             p2_alive: bool, p2_hp: float) -> dict:
        """
        Avança a máquina de estados em um frame.

        Retorna um dict com 'transitions': lista de eventos críticos
        que aconteceram neste tick (a serem replicados ao cliente):

            [{"ev": "round_start", "round": 2}, ...]

        O caller é responsável por:
        - Spawnar/resetar entidades nos PHASE_READY
        - Bloquear input/movimento se not can_act
        - Aplicar dano/colisões só durante PHASE_FIGHTING
        """
        transitions = []
        self.timer = max(0.0, self.timer - dt)

        if self.phase == PHASE_READY:
            if self.timer <= 0:
                self.phase = PHASE_COUNTDOWN
                self.timer = DEFAULT_COUNTDOWN_TIME

        elif self.phase == PHASE_COUNTDOWN:
            if self.timer <= 0:
                self.phase = PHASE_FIGHTING
                self.fight_left = self.round_time
                transitions.append({
                    "ev":    "round_start",
                    "round": self.round_idx,
                })

        elif self.phase == PHASE_FIGHTING:
            self.fight_left = max(0.0, self.fight_left - dt)
            winner = self._evaluate_round_end(p1_alive, p1_hp, p2_alive, p2_hp)
            if winner is not None:
                self._end_round(winner, transitions)

        elif self.phase == PHASE_ROUND_END:
            if self.timer <= 0:
                if self.match_winner is not None:
                    self.phase = PHASE_MATCH_END
                    self.timer = 0.0
                    transitions.append({
                        "ev":     "match_end",
                        "winner": self.match_winner,
                        "s1":     self.score_p1,
                        "s2":     self.score_p2,
                    })
                else:
                    self._begin_next_round()
                    transitions.append({
                        "ev":    "next_round",
                        "round": self.round_idx,
                    })

        return {"transitions": transitions}

    # ── Internos ──────────────────────────────────────────────────────────────

    def _evaluate_round_end(self,
                            p1_alive: bool, p1_hp: float,
                            p2_alive: bool, p2_hp: float) -> int | None:
        """0=empate, 1=p1, 2=p2, None=continua."""
        p1_dead = (not p1_alive) or p1_hp <= 0
        p2_dead = (not p2_alive) or p2_hp <= 0

        if p1_dead and p2_dead:
            return 0
        if p1_dead:
            return 2
        if p2_dead:
            return 1

        if self.fight_left <= 0:
            if p1_hp > p2_hp:
                return 1
            if p2_hp > p1_hp:
                return 2
            return 0
        return None

    def _end_round(self, winner: int, transitions: list):
        self.last_round_winner = winner
        if winner == 1:
            self.score_p1 += 1
        elif winner == 2:
            self.score_p2 += 1
        # winner == 0 → empate, ninguém pontua

        if self.score_p1 >= self.rounds_to_win:
            self.match_winner = 1
        elif self.score_p2 >= self.rounds_to_win:
            self.match_winner = 2

        self.phase = PHASE_ROUND_END
        self.timer = DEFAULT_ROUND_END_TIME

        transitions.append({
            "ev":     "round_end",
            "round":  self.round_idx,
            "winner": winner,
            "s1":     self.score_p1,
            "s2":     self.score_p2,
        })

    def _begin_next_round(self):
        self.round_idx += 1
        self.phase = PHASE_READY
        self.timer = DEFAULT_READY_TIME
        self.fight_left = self.round_time
        self.last_round_winner = None
