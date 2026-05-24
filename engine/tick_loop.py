"""
Fixed-timestep accumulator.

Permite simular física em passos discretos de FIXED_DT (1/60), independente
da framerate de render. Crítico para:

- Determinismo entre cliente e servidor (mesma sequência de inputs produz
  o mesmo resultado em ambos os lados).
- Evitar bugs de tunneling quando o render fica em FPS alto (e dt muito
  pequeno faz colisões "tremerem") ou baixo (e dt grande faz player
  atravessar paredes).

Uso:
    loop = TickLoop(FIXED_DT)
    while running:
        dt = clock.tick(FPS) / 1000.0
        for _ in loop.step(dt):
            simulation.tick(inputs, FIXED_DT)
        render(simulation.snapshot())
"""

import time


class TickLoop:
    """Acumulador de tempo. Cada chamada step(dt) devolve um iterável que
    conta quantos ticks fixos cabem no `dt` acumulado.

    Garante limite máximo de ticks por step (`max_steps`) para evitar o
    "spiral of death" quando o sistema fica devendo CPU — em vez de tentar
    rodar 50 ticks atrasados num frame só, descarta o excesso.
    """

    def __init__(self, fixed_dt: float = 1.0 / 60.0, max_steps: int = 8):
        self.fixed_dt = fixed_dt
        self.max_steps = max_steps
        self._accum = 0.0

    def step(self, dt: float) -> int:
        """Acumula dt e retorna o número de ticks fixos que devem rodar."""
        # Cap defensivo: dt absurdo (suspend, alt-tab) seria convertido em
        # dezenas de ticks. Capamos em max_steps * fixed_dt + margem.
        cap = self.max_steps * self.fixed_dt
        if dt > cap:
            dt = cap

        self._accum += dt
        ticks = 0
        while self._accum >= self.fixed_dt and ticks < self.max_steps:
            self._accum -= self.fixed_dt
            ticks += 1
        return ticks

    def alpha(self) -> float:
        """Fração do próximo tick já acumulada (0..1). Útil para interpolar
        render entre dois ticks consecutivos da simulação."""
        return self._accum / self.fixed_dt


class RealTimeLoop:
    """Variante para o servidor: agenda ticks em horário absoluto (asyncio).

    Diferente do TickLoop (driven por dt do render), aqui o relógio é fixo
    e o loop espera até o próximo tick. Mantém o servidor rodando em 60 Hz
    estáveis mesmo sob carga leve.
    """

    def __init__(self, fixed_dt: float = 1.0 / 60.0):
        self.fixed_dt = fixed_dt
        self._next = time.monotonic()

    def sleep_until_next(self) -> float:
        """Calcula segundos até o próximo tick. Retorna 0 se já atrasou."""
        now = time.monotonic()
        wait = self._next - now
        self._next += self.fixed_dt
        return max(0.0, wait)

    def reset(self):
        self._next = time.monotonic()
