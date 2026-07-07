# Arquitetura Multiplayer 2.0 — Servidor Dedicado em VPS

Proposta técnica para migrar `O Despertar das Raízes` de **multiplayer P2P em LAN** para **multiplayer cliente-servidor pela internet**, hospedado em VPS (HostGator), com jogabilidade fluida para ambos os jogadores.

> **Status:** proposta de arquitetura. Nenhum código foi alterado.
> **Autor da análise:** revisão da base atual (~5.200 linhas) + benchmarks teóricos.

---

## 1. Diagnóstico — por que o P2 trava hoje

Antes de propor o novo, é importante entender **por que o atual é injogável para o P2** mesmo em LAN. Não é uma falha de implementação isolada — são 5 problemas combinados.

### 1.1 Cliente não tem predição real (input lag = RTT + 1 frame)

Em `states/multiplayer_gameplay.py:357` o cliente faz:

```python
def _reconcile_local(self, s: dict):
    """Em LAN a latência é < 5 ms — snapeia direto sem threshold para
    eliminar qualquer acúmulo de desincronização."""
    e.pos.x = s.get("x", e.pos.x)   # ← teleporta toda hora
    e.pos.y = s.get("y", e.pos.y)
```

Tradução: o P2 aperta `→`, o input vai pelo socket, espera o host processar, espera o snapshot voltar, **e só então** vê o personagem andar. Em LAN são 1-3 frames (~16-48 ms). Em WAN para HostGator (Brasil → São Paulo) seriam **5-8 frames de delay visível**. Isso é o que se sente como "tudo trava".

A única "predição" que existe (`_predict_local_facing`) é cosmética — vira o sprite, mas não move.

### 1.2 RemotePlayer usa LERP exponencial em vez de buffer de interpolação

Em `entities/remote_player.py:89`:

```python
def update(self, dt: float):
    alpha = min(1.0, LERP_SPEED * dt)
    self.pos.x += (self._target_x - self.pos.x) * alpha
```

Esse "exponential decay lerp" tem 2 problemas crônicos:
- **Movimento elástico/borrachudo** — nunca chega no alvo, sempre persegue assintoticamente.
- **Não tem noção de tempo real entre snapshots.** Se chega 1 snapshot, depois 100 ms sem nada, depois 2 de uma vez, o personagem dá um salto seguido de uma parada.

O padrão correto (Source Engine, Overwatch, Rocket League) é: **buffer de 2-3 snapshots com timestamps** e renderiza com 100-150 ms de delay, interpolando linearmente entre dois estados conhecidos.

### 1.3 JSON @ 60 Hz toda frame, sem delta

`network/protocol.py:28` codifica tudo como JSON. Um snapshot real do co-op pesa ~600 bytes. A 60 Hz, são **36 KB/s por lado**, e em Python o `json.dumps` + `json.loads` consome CPU significativa. Para LAN é "ok"; para WAN é desperdício gritante.

Padrão profissional: **binário (msgpack/struct) @ 20-30 Hz com delta encoding** = ~3-5 KB/s.

### 1.4 Host é um dos jogadores (P2P)

Hoje o "host" é a máquina de um dos jogadores. Implicações:
- **NAT/firewall doméstico bloqueia conexão direta pela internet.** É por isso que só funciona em LAN. Furar NAT exige STUN/TURN/UPnP — sem isso, o discovery por broadcast UDP (`network/discovery.py:7779`) **só funciona dentro do mesmo roteador**.
- **Host tem 0 ms de latência; cliente paga o RTT inteiro.** Vantagem competitiva injusta no Versus.
- **Se o host tem FPS drop, o cliente trava junto.**

### 1.5 Sem tickrate fixo separado do render

`engine/game.py:53` roda física no `dt` variável do `clock.tick(FPS)`. Se o host está em 30 FPS por qualquer motivo (janela em background, GPU fraca, alt-tab), a simulação inteira roda em 30 Hz e o cliente herda isso. Servidores competitivos rodam **tick fixo (60-128 Hz) desacoplado do render**.

---

## 2. Visão geral da nova arquitetura

```
                    ┌─────────────────────────────────────────────────┐
                    │                  VPS (HostGator)                │
                    │                                                 │
                    │   ┌─────────────────┐    ┌──────────────────┐   │
                    │   │  Lobby/Match    │    │  Game Server     │   │
                    │   │  Service        │◄──►│  (headless)      │   │
                    │   │  (HTTP/REST)    │    │  tick: 60 Hz     │   │
                    │   │  porta 443      │    │  porta 7777 UDP  │   │
                    │   └────────▲────────┘    └────────▲─────────┘   │
                    │            │                      │             │
                    │            │   systemd / docker   │             │
                    └────────────┼──────────────────────┼─────────────┘
                                 │                      │
                  ┌──────────────┘                      │
                  │ HTTPS (lobby)                       │ UDP (gameplay)
                  │ - listar salas                      │ - input (30 Hz)
                  │ - criar/entrar                      │ - snapshot (20-30 Hz)
                  │ - heartbeat                         │ - eventos críticos c/ ACK
                  │                                     │
        ┌─────────▼─────────┐                ┌──────────▼──────────┐
        │  CLIENTE P1       │                │  CLIENTE P2          │
        │  (pygame)         │                │  (pygame)            │
        │                   │                │                      │
        │  • prediction     │                │  • prediction        │
        │  • reconciliation │                │  • reconciliation    │
        │  • interp. buffer │                │  • interp. buffer    │
        │  • render @ 60+   │                │  • render @ 60+      │
        └───────────────────┘                └──────────────────────┘
```

### Princípios

1. **Servidor dedicado autoritativo** — ninguém "hospeda"; ambos são clientes iguais.
2. **Client-side prediction + server reconciliation** — o cliente roda a própria física localmente, servidor corrige.
3. **Entity interpolation** para o jogador remoto (renderiza 100 ms "no passado", mas sempre fluido).
4. **Tickrate fixo de 60 Hz** no servidor, snapshot rate de 30 Hz.
5. **Protocolo binário** (`msgpack`) com delta encoding.
6. **Lobby HTTP separado** do gameplay — permite listar salas pela internet sem broadcast.
7. **Headless** — servidor não importa pygame.

---

## 3. Topologia em detalhe

### 3.1 Diagrama de processos na VPS

```
┌──────────────────────── VPS (1 vCPU, 2 GB RAM, Linux) ────────────────────────┐
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  nginx (reverse proxy + TLS)             :443                           │  │
│  │      ├─ /api/* → lobby:8080                                             │  │
│  │      └─ /     → static landing page                                     │  │
│  └────────────────────────────┬────────────────────────────────────────────┘  │
│                               │                                               │
│  ┌────────────────────────────▼────────────────────────┐                      │
│  │  lobby_service.py            :8080 HTTP             │                      │
│  │  ─────────────────────────────────────────          │                      │
│  │  • POST /rooms      criar sala                      │                      │
│  │  • GET  /rooms      listar salas abertas            │                      │
│  │  • POST /rooms/{id}/join                            │                      │
│  │  • WebSocket /ws/{room_id}  (lobby chat/ready)      │                      │
│  │  • salva estado em SQLite local                     │                      │
│  └────────────────────────────┬────────────────────────┘                      │
│                               │ spawn / IPC                                   │
│  ┌────────────────────────────▼────────────────────────┐                      │
│  │  game_server.py    [N processos]   UDP :7777-7799   │                      │
│  │  ─────────────────────────────────────────          │                      │
│  │  • 1 processo por sala (até 20 salas paralelas)     │                      │
│  │  • headless: sem pygame, sem render, sem áudio      │                      │
│  │  • tick fixo 60 Hz (asyncio + monotonic)            │                      │
│  │  • snapshot rate 30 Hz                              │                      │
│  │  • encerra sozinho se sala vazia > 60 s             │                      │
│  └─────────────────────────────────────────────────────┘                      │
│                                                                               │
│  systemd:                                                                     │
│      odr-lobby.service       (always-on)                                      │
│      odr-server@<port>.service  (template, instanciado pelo lobby)            │
│                                                                               │
│  ufw:                                                                         │
│      ALLOW 443/tcp                                                            │
│      ALLOW 7777-7799/udp                                                      │
│      DENY  todo o resto                                                       │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Dimensionamento

Para uma VPS modesta da HostGator (1 vCPU / 2 GB RAM):

| Recurso | Custo por sala ativa | Capacidade estimada |
|---|---|---|
| CPU | ~3-5% (Python tick 60 Hz, 2 entidades) | **15-25 salas simultâneas** |
| RAM | ~30-50 MB por processo de sala | **20-30 salas (~1 GB)** |
| Bandwidth | ~5 KB/s ↑ + 5 KB/s ↓ por jogador | **trivial** (HostGator entrega TB/mês) |
| Latência Brasil→VPS São Paulo | 5-25 ms | jogável para BR-only |
| Latência Brasil→VPS EUA | 100-180 ms | ainda jogável com interp/prediction |

**Recomendação de plano:** VPS "Snappy 2000" da HostGator (2 vCPU, 4 GB) com **datacenter em São Paulo** se disponível. Se só houver opção nos EUA, ainda funciona — o netcode foi desenhado para isso.

---

## 4. Protocolo de rede 2.0

### 4.1 Tabela de mensagens

Mantém a filosofia atual (campo `t` + payload), mas migra para **MessagePack** (binário, ~5x menor que JSON, parser em C).

| Tipo | Direção | Confiabilidade | Frequência | Payload |
|---|---|---|---|---|
| `HI` / `HI_ACK` | C↔S | reliable (retry) | 1x | nick, room_token, version |
| `INP` | C→S | unreliable | 30 Hz | tick, bitmask de teclas |
| `SNAP` | S→C | unreliable | 30 Hz | tick, ack_inp, delta de entities |
| `FULLSNAP` | S→C | reliable | sob pedido | snapshot completo (recovery) |
| `EV` / `EV_ACK` | S↔C | reliable (retry+ack) | sob demanda | round_start, dmg, died, match_end |
| `PING` / `PONG` | C↔S | unreliable | 1 Hz | timestamp p/ medir RTT |
| `BYE` | C↔S | unreliable | 1x | motivo |

### 4.2 Tamanho do pacote — comparação

```
SNAPSHOT ATUAL (JSON)                  SNAPSHOT NOVO (msgpack + delta)
─────────────────────────              ──────────────────────────────────
{"t":"ST","ts":12.34,                  ▒ tick (uint32)            4 B
 "p1":{"x":120.5,"y":300.0,            ▒ ack_inp (uint32)         4 B
       "vx":0,"vy":0,                  ▒ mask de mudanças (u16)   2 B
       "facing":1,"hp":100,            ▒ p1.x delta (i16 *0.1)    2 B
       "anim":"idle",...},             ▒ p1.y delta (i16 *0.1)    2 B
 "p2":{...},                           ▒ p2.x delta + flags       4 B
 "proj":[...],                         ▒ ...
 "ack":42}                             ─────────────────────
   ≈ 580 bytes / pacote                  ≈ 60-90 bytes / pacote
   ≈ 34 KB/s @ 60 Hz                     ≈ 2.4 KB/s @ 30 Hz
```

Ganho: **~14x menos banda**, **~10x menos CPU em encode/decode**.

### 4.3 Tickrate vs. snapshot rate vs. render rate

Três relógios separados:

```
RENDER  ████████████████████████████████████████  60+ Hz (FPS local, pode subir)
        │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │
SIM/TICK█████████████████████████████████████████ 60 Hz fixo (cliente E servidor)
        │   │   │   │   │   │   │   │   │   │
INP-OUT ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼     30 Hz (cliente envia input
                                                       agregado de 2 ticks)
SNAP-IN ▼       ▼       ▼       ▼       ▼          30 Hz (servidor manda snapshot
                                                       a cada 2 ticks)
```

Implementação: `tick_accumulator` clássico (timestep fixo), igual ao que já temos parcialmente em `MAX_STEPS=8` (`settings.py`), mas agora **autoritativo** em ambos os lados.

---

## 5. Client-Side Prediction + Server Reconciliation

Essa é **a mudança que mata o input lag do P2.**

### 5.1 O loop do cliente

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTE (cada tick)                             │
│                                                                              │
│   1. capturar input local        ──►  input{tick=N, l,r,ju,at,...}           │
│                                                                              │
│   2. armazenar em fila local     ──►  pending_inputs.append(input)           │
│                                                                              │
│   3. RODAR FÍSICA LOCALMENTE     ──►  player_local.tick(input, dt)           │
│      (mesma física do servidor!)      ↳ vê o resultado IMEDIATAMENTE         │
│                                                                              │
│   4. enviar input ao servidor    ──►  UDP send INP                           │
│                                                                              │
│   5. (se chegou) processar SNAP do servidor                                  │
│      ┌──────────────────────────────────────────────────────────┐            │
│      │  a. servidor disse "no tick K, sua pos era X,Y"          │            │
│      │  b. descartar pending_inputs com tick <= K (já aplicados)│            │
│      │  c. RESETAR player_local para (X,Y)                      │            │
│      │  d. REAPLICAR pending_inputs[K+1 .. N] em sequência      │            │
│      │     ─► resultado: posição prevista corrigida              │            │
│      └──────────────────────────────────────────────────────────┘            │
│                                                                              │
│   6. atualizar buffer de interpolação do remote_player com SNAP              │
│                                                                              │
│   7. renderizar:                                                             │
│       - player_local em pos real (predita)                                   │
│       - player_remoto em pos interpolada (~100 ms atrás)                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Insight crítico:** o cliente reaplica TODA a fila de inputs ainda não confirmados. Se a previsão estava certa, a posição não muda (zero glitch). Se estava errada (ex: travou numa parede que o cliente não viu), o player "desliza" suavemente para a posição correta — mas sem nunca parar de responder ao input.

### 5.2 O loop do servidor

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            SERVIDOR (cada tick, 60 Hz)                       │
│                                                                              │
│   1. drenar inputs recebidos (UDP)                                           │
│      ─► para cada jogador: pegar o input com maior tick                      │
│                                                                              │
│   2. aplicar inputs nos Player                                               │
│                                                                              │
│   3. PhysicsSystem.update(entities, FIXED_DT)                                │
│   4. CombatSystem.update(entities, FIXED_DT)                                 │
│   5. VersusMatch.tick(...)  (se modo versus)                                 │
│                                                                              │
│   6. para cada player conectado:                                             │
│      gravar histórico (ring buffer 1s) para LAG COMPENSATION                 │
│                                                                              │
│   7. a cada 2 ticks (30 Hz):                                                 │
│       montar snapshot incluindo:                                             │
│         • tick atual                                                         │
│         • ack_inp = maior tick de input processado deste jogador             │
│         • delta de cada entity vs. último snapshot que ESTE cliente acked    │
│       enviar UDP                                                             │
│                                                                              │
│   8. enviar eventos críticos pendentes com retry (igual hoje)                │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Entity Interpolation (RemotePlayer fluido)

Substitui o `LERP_SPEED = 18.0` por buffer de timestamps reais:

```
TEMPO REAL          ──────────────────────────────────────────►
                    t=0ms  t=33ms  t=66ms  t=99ms  t=132ms  t=165ms
                      │      │       │       │       │        │
SNAPSHOTS CHEGAM      S1     S2      S3      S4      S5       S6
                      ▼      ▼       ▼       ▼       ▼        ▼
BUFFER:               [S1]   [S1,S2] [S2,S3] [S3,S4] [S4,S5]  [S5,S6]

RENDER (com 100ms de delay):
                                       ████ render entre S1 e S2 (interpolando)
                                              ████ entre S2 e S3
                                                     ████ entre S3 e S4
                                                            ████ entre S4 e S5
```

**Algoritmo:**
1. Cliente mantém `render_time = server_time - 100ms`
2. A cada frame, acha os 2 snapshots em volta de `render_time`
3. `alpha = (render_time - snap_a.time) / (snap_b.time - snap_a.time)`
4. `pos = lerp(snap_a.pos, snap_b.pos, alpha)`

Se o buffer ficar vazio (perda de pacote), **extrapola** por até 200 ms usando a velocidade do último snapshot. Acima disso, congela e mostra ícone de lag.

Resultado: **o RemotePlayer se move com a mesma fluidez do local**, mesmo com 80 ms de latência.

### 5.4 Lag Compensation (anti-"matei mas não morreu")

Quando o servidor recebe um ataque do cliente:

```
                              tick N (servidor "agora")
                              │
  histórico do alvo  ◄────────┼────  últimos 60 ticks (1 s)
  [N-30] [N-25] [N-20] ... [N-1] [N]
                  ▲
                  │
       cliente atacou neste tick
       (ele viu o inimigo nessa posição)

→ servidor REBOBINA o alvo para tick (N - rtt/2) antes de testar a hitbox
→ aplica dano se acertava NAQUELE estado
→ resto da simulação continua em tick N
```

Isso é "lag compensation" (Source-style). Custo: ~5 KB de RAM por jogador (60 ticks × snapshot pequeno). Implementação no `CombatSystem`.

---

## 6. Lobby / Matchmaking

### 6.1 Fluxo do jogador

```
┌─────────────┐                ┌────────────┐                ┌──────────────┐
│  Cliente A  │                │   Lobby    │                │  Cliente B   │
└──────┬──────┘                │  (HTTPS)   │                └──────┬───────┘
       │                       └─────┬──────┘                       │
       │ POST /rooms                  │                              │
       │ {name:"Sala do Jean",        │                              │
       │  mode:"vs", max:2}           │                              │
       ├─────────────────────────────►│                              │
       │                              │ spawn game_server :7780     │
       │                              ├──────────────►               │
       │ ◄─{room_id, server_port,     │                              │
       │     join_token_A}            │                              │
       │                              │  GET /rooms ◄────────────────┤
       │                              ├─[{id, name, players:1/2}]──►│
       │                              │  POST /rooms/{id}/join ◄────┤
       │ ◄────────── WS notify ───────┤───{server_port, token_B}───►│
       │                              │                              │
       │  UDP HI(token_A) → server:7780 ◄───────  UDP HI(token_B) ──┤
       │                                                              │
       │ ◄═════════════ PARTIDA RODA NO GAME_SERVER ═════════════════►│
       │                                                              │
       │  BYE                          │                              │
       ├─────────────────────────────►│  server detecta sala vazia   │
       │                              │  e encerra após 60s          │
```

### 6.2 Endpoints HTTP (esboço)

```
POST  /api/rooms                     criar sala
      body: {name, mode, max_players, password?}
      resp: {room_id, server_host, server_port, join_token}

GET   /api/rooms                     listar salas abertas
      resp: [{id, name, mode, players, max, has_password}]

POST  /api/rooms/{id}/join           pegar token de entrada
      body: {nick, password?}
      resp: {server_host, server_port, join_token}

GET   /api/health                    healthcheck (uptime, salas ativas)

WS    /api/ws/rooms                  notificações de salas (opcional)
```

Stack sugerida: **FastAPI + uvicorn** (assíncrono, leve, ~30 MB RAM). SQLite local para persistir salas/estatísticas.

---

## 7. Estrutura de pastas proposta

```
O_Despertar_das_Raizes/
│
├── engine/
│   ├── game.py
│   ├── ...
│   ├── simulation.py            ★ NOVO — World simulável headless (sem pygame)
│   │                              extrai física+combate+versus em uma classe
│   │                              que roda igual no servidor e no cliente
│   ├── tick_loop.py             ★ NOVO — fixed timestep accumulator
│   └── versus_match.py
│
├── shared/                      ★ NOVO — código compartilhado client/server
│   ├── protocol.py              ★ msgpack encode/decode, schemas, versionamento
│   ├── snapshot.py              ★ delta encoding / decoding
│   ├── input_buffer.py          ★ fila de inputs pendentes (cliente)
│   ├── interp_buffer.py         ★ buffer de snapshots para interpolação
│   └── lag_comp.py              ★ ring buffer de histórico de entidades
│
├── server/                      ★ NOVO — código que SÓ roda na VPS
│   ├── __main__.py              ★ entrypoint: python -m server --port 7780
│   ├── game_server.py           ★ loop autoritativo headless
│   ├── room.py                  ★ wrapper de uma sala/partida
│   ├── connections.py           ★ socket asyncio + dispatch
│   └── lobby/
│       ├── app.py               ★ FastAPI app
│       ├── routes.py            ★ endpoints REST
│       ├── room_registry.py     ★ SQLite + spawn de game_server
│       └── tokens.py            ★ JWT de join (curto, 60 s)
│
├── network/                     ⇨ refatorado para cliente apenas
│   ├── client.py                ⇨ usa shared/protocol, shared/interp_buffer
│   ├── connection.py            ⇨ mantém threads recv/heartbeat
│   ├── matchmaker_client.py     ★ NOVO — cliente HTTP do lobby
│   └── ⊗ host.py                ⇨ REMOVIDO (servidor não é mais o jogador)
│   └── ⊗ discovery.py           ⇨ REMOVIDO (substituído pelo lobby HTTP)
│
├── deploy/                      ★ NOVO
│   ├── odr-lobby.service        systemd unit
│   ├── odr-server@.service      systemd unit template (instanced)
│   ├── nginx.conf               reverse proxy + TLS
│   ├── Dockerfile               (opcional)
│   ├── docker-compose.yml       (opcional)
│   └── install.sh               provisioning idempotente da VPS
│
├── states/
│   ├── multiplayer_menu.py      ⇨ refatorado: "Procurar partidas" → HTTP
│   ├── lobby_state.py           ⇨ lista de salas via HTTP
│   └── multiplayer_gameplay.py  ⇨ usa client-side prediction
│
└── settings.py                  ⇨ +MATCHMAKER_URL, +SERVER_HOST padrão
```

Legenda: ★ novo &nbsp;&nbsp; ⇨ refatorado &nbsp;&nbsp; ⊗ removido

---

## 8. Plano de implementação faseado

Cada fase é um PR independente, testável e reversível. **Não pular fases** — cada uma estabelece a base para a próxima.

### Fase 0 — Refactor: extrair Simulation headless `[5-8h]`
**Objetivo:** ter uma classe `Simulation` que roda física+combate+match SEM importar pygame.

- Criar `engine/simulation.py` com `Simulation.tick(inputs: dict, dt: float)`.
- Mover `PhysicsSystem`, `CombatSystem`, `VersusMatch.tick` para dentro dela.
- Player passa a aceitar inputs como `dict` (não `pygame.key.get_pressed()`). O `_NetKeys` adapter atual já mostra que isso é viável.
- **Critério de aceite:** `python -c "from engine.simulation import Simulation; s=Simulation(); s.tick({}, 0.016)"` roda sem importar pygame.
- **Risco:** quebrar single-player. Mitigação: `gameplay.py` (single) também passa a usar `Simulation` — vira camada única.

### Fase 1 — Tickrate fixo no cliente `[2-3h]`
- Implementar `tick_accumulator` em `Game.run` (consumir `dt` em passos de `FIXED_DT = 1/60`).
- Render fica desacoplado: pode rodar a 144 Hz, sim só 60 Hz.
- **Critério de aceite:** rodar com `FPS=30` e `FPS=144` produz a mesma simulação determinística (mesmas posições após N ticks).

### Fase 2 — Protocolo binário (msgpack) `[2-4h]`
- Adicionar `msgpack` em `requirements.txt`.
- Rewriting `network/protocol.py`: `encode`/`decode` viram msgpack.
- Schemas versionados (campo `v` no handshake — recusa client de versão errada).
- **Critério de aceite:** LAN multiplayer atual continua funcionando idêntico, mas com pacotes ~5x menores (medir com Wireshark).

### Fase 3 — Servidor headless dedicado `[8-12h]`
- Criar `server/game_server.py` que roda `Simulation` em loop com `asyncio` + UDP.
- Mover lógica de `network/host.py` para lá (sem pygame).
- Cliente passa a se conectar a `(SERVER_HOST, PORT)` por config — sem discovery por enquanto.
- **Critério de aceite:** subir `python -m server --port 7777` em uma máquina, dois clientes conectam por IP fixo, partida funciona.
- **Marco:** já dá pra subir na VPS e jogar pela internet (manual, via IP).

### Fase 4 — Entity interpolation `[3-5h]`
- Criar `shared/interp_buffer.py`.
- `RemotePlayer.apply_state` agora **enfileira** com timestamp; `update` renderiza com delay de 100 ms.
- Extrapolação por 200 ms se buffer vazio.
- **Critério de aceite:** simular 80 ms de latência com `tc qdisc add dev lo root netem delay 80ms` (Linux) ou Clumsy (Windows) — RemotePlayer move suavemente, sem stutter.

### Fase 5 — Client-side prediction + reconciliation `[6-10h]`
- Criar `shared/input_buffer.py` (fila de inputs com tick).
- Cliente roda `Simulation` localmente só para o **próprio** player.
- Ao receber snapshot: rollback + replay dos inputs pendentes.
- **Critério de aceite:** input lag do P2 cai de "RTT inteiro" para "0 ms percebido" mesmo com 100 ms simulados.

### Fase 6 — Lobby / Matchmaker HTTP `[6-10h]`
- `server/lobby/` em FastAPI.
- `network/matchmaker_client.py` faz `requests.get("/api/rooms")`.
- UI: substituir `multiplayer_menu.py` "Procurar partidas (LAN)" por "Salas online".
- Tokens JWT curtos para join (evita IP-hijack).
- **Critério de aceite:** jogador A cria sala via UI; jogador B vê na lista em < 2 s e entra com 1 clique.

### Fase 7 — Lag compensation `[4-6h]`
- `shared/lag_comp.py`: ring buffer de 60 estados por entidade.
- `CombatSystem.update` no servidor: ao processar hit, rebobina alvo para `now - rtt/2`.
- **Critério de aceite:** com 100 ms de latência, ataque feito "encostado" no inimigo registra hit 99% das vezes (vs. ~50% sem comp).

### Fase 8 — Deploy + observabilidade `[4-6h]`
- `deploy/install.sh`: provisiona a VPS (ufw, fail2ban, nginx, systemd, certbot).
- `deploy/odr-server@.service`: template instanciado por porta.
- Endpoint `/api/health` com métricas (salas ativas, RTT médio, tick miss rate).
- Logs estruturados (JSON) em `/var/log/odr/`.
- **Critério de aceite:** `ssh vps "systemctl restart odr-lobby"` traz tudo de volta em < 5 s. Reboot da VPS recompoe sozinho.

### Fase 9 (opcional) — Hardening `[3-5h]`
- Rate limit no lobby (FastAPI + slowapi).
- Validação de input no servidor (bitmask whitelisted).
- Anti-cheat básico: servidor descarta input com `tick` muito longe do servidor.
- Reconnect automático (cliente guarda token, reusa em queda < 30 s).

**Total estimado:** 43-69 h de trabalho focado. Pode ser feito por uma pessoa em ~3-5 semanas part-time, ou ~10 dias full-time.

---

## 9. Mudanças por arquivo (resumo)

| Arquivo | Mudança | Fase |
|---|---|---|
| `engine/game.py` | tick accumulator fixo | 1 |
| `engine/simulation.py` | **NOVO** — World simulável headless | 0 |
| `entities/player.py` | aceitar input dict; remover `pygame.key.get_pressed()` direto | 0 |
| `entities/remote_player.py` | substituir LERP por interp buffer | 4 |
| `network/protocol.py` | msgpack + delta + versionamento | 2 |
| `network/host.py` | **REMOVER** (vira `server/game_server.py`) | 3 |
| `network/discovery.py` | **REMOVER** (substituído pelo lobby) | 6 |
| `network/client.py` | usa interp buffer + input buffer | 4, 5 |
| `states/multiplayer_menu.py` | UI de "salas online" via HTTP | 6 |
| `states/multiplayer_gameplay.py` | client-side prediction, reconciliation | 5 |
| `server/*` | **NOVO** — todo o stack do servidor | 3, 6 |
| `shared/*` | **NOVO** — código comum cliente/servidor | 2, 4, 5, 7 |
| `deploy/*` | **NOVO** — provisioning da VPS | 8 |
| `requirements.txt` | +msgpack, +fastapi, +uvicorn, +pyjwt (server-only em `requirements-server.txt`) | 2, 6 |

---

## 10. O que VOCÊ precisa fazer na VPS — checklist completo

Esta seção é um **passo-a-passo prático** para você, dono do projeto, do momento "vou contratar uma VPS" até "o jogo está no ar". Marque os checkboxes conforme avança.

### 10.0 Antes de contratar — decisões a tomar

- [ ] **Datacenter:** confirmar com o suporte da HostGator se há datacenter no **Brasil (São Paulo)**. Se sim, escolher esse — latência cai de ~120 ms (EUA) para ~15 ms. Se não houver, é aceitável (o netcode foi desenhado pra WAN), mas a experiência ficará "internacional".
- [ ] **Plano:** começar com **VPS Snappy 1000** (1 vCPU, 2 GB RAM, ~R$ 60/mês). Suporta ~15 salas. Migra para Snappy 2000 quando precisar.
- [ ] **Sistema operacional:** escolher **Ubuntu Server 22.04 LTS** (ou 24.04 LTS). NÃO escolher CentOS/AlmaLinux — toda a documentação abaixo é Ubuntu/Debian. NÃO escolher Windows Server — caro e sem ganho aqui.
- [ ] **Domínio (opcional mas recomendado):** registrar um `.com.br` (ex: `despertarraizes.com.br`) — facilita TLS e o IP da VPS pode mudar. Custo ~R$ 40/ano (Registro.br).

### 10.1 Dia 1 — Contratação e acesso

**O que a HostGator te entrega ao contratar:**

| Item | Onde encontrar | Você vai precisar |
|---|---|---|
| IP público (v4) | Painel da HostGator → Detalhes da VPS | Para o DNS e para SSH |
| Usuário root + senha | E-mail de boas-vindas | Para o primeiro login SSH |
| Porta SSH | Geralmente 22 (confirmar) | Para `ssh` |
| Painel de gerenciamento (cPanel/WHM ou outro) | Link no e-mail | Para reboot/snapshots |

**Suas ações:**

- [ ] **Anotar o IP** em local seguro (`Bitwarden`, `1Password` ou similar).
- [ ] **Configurar DNS** (se comprou domínio): no painel do registrador, criar registro A apontando `despertarraizes.com.br → IP_DA_VPS`. Propaga em ~15 min.
- [ ] **Primeiro login SSH** do seu PC:
  ```bash
  ssh root@<IP_DA_VPS>
  # cola a senha que veio por e-mail
  ```
  Se der erro de "host key" — normal no primeiro acesso, digite `yes`.
- [ ] **Trocar a senha de root**:
  ```bash
  passwd
  ```
- [ ] **Gerar chave SSH** no seu PC (se ainda não tem) e copiar para a VPS — assim você nunca mais digita senha:
  ```bash
  # No SEU PC (Windows PowerShell ou Git Bash):
  ssh-keygen -t ed25519                       # aceita os defaults
  type $env:USERPROFILE\.ssh\id_ed25519.pub   # copia o conteúdo

  # No SSH da VPS:
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  nano ~/.ssh/authorized_keys                 # cola o conteúdo, salva (Ctrl+O, Enter, Ctrl+X)
  chmod 600 ~/.ssh/authorized_keys
  ```
- [ ] **Testar login sem senha** abrindo um novo terminal: `ssh root@<IP>` deve entrar direto.

### 10.2 Dia 1 — Hardening básico (NÃO PULAR)

Uma VPS exposta na internet sem hardening é comprometida em horas. Faça **antes de subir qualquer código**.

- [ ] **Atualizar o sistema:**
  ```bash
  apt update && apt upgrade -y && apt autoremove -y
  reboot   # se atualizou kernel
  ```
- [ ] **Criar usuário não-root** (você nunca vai rodar o jogo como root):
  ```bash
  adduser odr                       # criar senha forte
  usermod -aG sudo odr
  rsync -a ~/.ssh /home/odr/        # reutilizar sua chave SSH
  chown -R odr:odr /home/odr/.ssh
  ```
  Testar de outro terminal: `ssh odr@<IP>` — deve entrar.
- [ ] **Desabilitar login SSH de root e por senha** (só chave SSH passa):
  ```bash
  nano /etc/ssh/sshd_config
  # mudar/garantir as linhas:
  #   PermitRootLogin no
  #   PasswordAuthentication no
  #   PubkeyAuthentication yes
  systemctl restart ssh
  ```
  ⚠️ **Antes de desconectar, abra OUTRO terminal e teste `ssh odr@<IP>`.** Se entrar, ok. Se NÃO entrar, você ainda tem a sessão atual aberta para corrigir — não a feche enquanto não testar.
- [ ] **Firewall (ufw):** bloqueia tudo exceto SSH (22), HTTPS (443) e portas de jogo (7777-7799 UDP):
  ```bash
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow 22/tcp
  ufw allow 80/tcp                  # certbot precisa pra emitir TLS
  ufw allow 443/tcp
  ufw allow 7777:7799/udp           # range de salas
  ufw enable                        # confirme "y"
  ufw status
  ```
- [ ] **fail2ban** (banimento automático de IPs que tentam força-bruta SSH):
  ```bash
  apt install -y fail2ban
  systemctl enable --now fail2ban
  ```
- [ ] **Updates automáticos de segurança:**
  ```bash
  apt install -y unattended-upgrades
  dpkg-reconfigure -plow unattended-upgrades   # responda "Yes"
  ```
- [ ] **Timezone e NTP** (importante: relógio errado = TLS quebra e tickrate fica torto):
  ```bash
  timedatectl set-timezone America/Sao_Paulo
  timedatectl set-ntp true
  timedatectl                                  # confere
  ```
- [ ] **Hostname amigável** (opcional):
  ```bash
  hostnamectl set-hostname odr-game-01
  ```

### 10.3 Dia 1 ou 2 — Instalar dependências do projeto

- [ ] Voltar para o usuário não-root:
  ```bash
  exit                              # sai do root, se entrou
  ssh odr@<IP>
  ```
- [ ] **Python 3.11+** e ferramentas:
  ```bash
  sudo apt install -y python3.11 python3.11-venv python3-pip git nginx certbot python3-certbot-nginx htop
  python3.11 --version              # confere
  ```
- [ ] **Clonar o repositório** (após Fase 3 do plano estar pronta no GitHub):
  ```bash
  cd ~
  git clone https://github.com/JeanFD/O_Despertar_das_Raizes.git
  cd O_Despertar_das_Raizes
  ```
- [ ] **Criar ambiente virtual + instalar dependências do servidor:**
  ```bash
  python3.11 -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements-server.txt   # arquivo criado na Fase 6
  ```
  > **Nota:** `requirements-server.txt` terá só `msgpack`, `fastapi`, `uvicorn[standard]`, `pyjwt` — **sem pygame**. O servidor é headless.

### 10.4 Dia 2 — Subir o serviço com systemd

systemd garante que o serviço **liga sozinho no boot** e **reinicia se cair**.

- [ ] **Instalar units** (criadas na Fase 8 do plano):
  ```bash
  sudo cp deploy/odr-lobby.service /etc/systemd/system/
  sudo cp deploy/odr-server@.service /etc/systemd/system/
  sudo systemctl daemon-reload
  ```
- [ ] **Ligar e ativar o lobby:**
  ```bash
  sudo systemctl enable --now odr-lobby
  sudo systemctl status odr-lobby          # esperar "active (running)"
  ```
- [ ] **Conferir que está escutando:**
  ```bash
  sudo ss -tunlp | grep -E '8080|7777'
  curl http://localhost:8080/api/health     # deve responder JSON
  ```

### 10.5 Dia 2 — Nginx + TLS (HTTPS)

Para o cliente do jogo aceitar conexão HTTPS sem warning, precisa de TLS de verdade.

- [ ] **Editar config do nginx** (do `deploy/nginx.conf`):
  ```bash
  sudo cp deploy/nginx.conf /etc/nginx/sites-available/odr
  sudo ln -sf /etc/nginx/sites-available/odr /etc/nginx/sites-enabled/
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t                           # valida config
  sudo systemctl reload nginx
  ```
- [ ] **Emitir certificado Let's Encrypt** (precisa do DNS já apontando):
  ```bash
  sudo certbot --nginx -d despertarraizes.com.br
  # certbot pede e-mail, aceita termos e edita o nginx automaticamente
  ```
- [ ] **Renovação automática** (certbot já configura via timer, mas confira):
  ```bash
  sudo systemctl list-timers | grep certbot
  ```
- [ ] **Testar do seu PC:**
  ```
  https://despertarraizes.com.br/api/health   ► deve abrir sem warning de TLS
  ```

### 10.6 Dia 2 — Configurar o cliente para apontar para a VPS

No `settings.py` do cliente:

```python
# Antes (LAN):
HOST_PORT = 7777

# Depois (VPS):
MATCHMAKER_URL = "https://despertarraizes.com.br"
# server_host e server_port virão na resposta do lobby por sala
```

- [ ] Distribuir o build atualizado para os jogadores (ou mantê-los rodando direto do `git pull`).

### 10.7 Dia a dia — comandos que você vai usar

| Para... | Comando |
|---|---|
| Ver se o lobby está rodando | `sudo systemctl status odr-lobby` |
| Listar partidas ativas (processos de sala) | `sudo systemctl list-units 'odr-server@*'` |
| Ver logs do lobby ao vivo | `sudo journalctl -u odr-lobby -f` |
| Ver logs de TODAS as partidas | `sudo journalctl -u 'odr-server@*' -f` |
| Atualizar código | `cd ~/O_Despertar_das_Raizes && git pull && . .venv/bin/activate && pip install -r requirements-server.txt && sudo systemctl restart odr-lobby` |
| Reboot da VPS (raro) | `sudo reboot` — tudo volta sozinho graças ao systemd |
| Ver consumo de RAM/CPU | `htop` |
| Ver bandwidth gasto | painel da HostGator → "Tráfego" |
| Métricas do jogo | `curl https://despertarraizes.com.br/api/health \| jq` |

### 10.8 Sinais de alarme — quando agir

| Sintoma | Causa provável | Ação |
|---|---|---|
| `systemctl status odr-lobby` mostra "failed" | Bug no código ou dependência faltando | Ver `journalctl -u odr-lobby --since "10 min ago"` |
| RAM ficou em 90%+ | Vazamento ou salas demais | `htop`; se passar disso por > 1 h, considere reiniciar; investigar leak |
| `df -h` mostra `/` em 80%+ | Logs cresceram demais | `sudo journalctl --vacuum-time=7d` |
| Jogadores reportam "não consigo conectar" | Firewall / certificado vencido / IP mudou | Conferir `ufw status`, `certbot certificates`, `curl /api/health` |
| Login SSH não funciona | Você se trancou fora | Painel da HostGator → console "VNC" — funciona mesmo sem SSH |

### 10.9 Backup — o que salvar

A maior parte da VPS é descartável (código está no GitHub). O que **não está no Git** e precisa de backup:

- [ ] **Banco SQLite** do lobby (`~/O_Despertar_das_Raizes/server/lobby/data.db` — estatísticas, históricos).
  - Backup diário simples via cron:
    ```bash
    crontab -e
    # adicionar:
    0 3 * * * cp ~/O_Despertar_das_Raizes/server/lobby/data.db ~/backups/data.$(date +\%F).db
    ```
- [ ] **Certificados TLS** (`/etc/letsencrypt/`) — em caso de migração de VPS.
- [ ] **Configuração do nginx** (`/etc/nginx/sites-available/odr`).

Idealmente, baixar esses arquivos para seu PC semanalmente via `scp odr@<IP>:~/backups/ .`

### 10.10 Quando migrar de plano

Hora de subir de Snappy 1000 → 2000 quando:

- CPU média (em `htop`) passa de **60%** por > 1 h em horário de pico.
- RAM passa de **80%** consistente.
- Mais de **10 salas simultâneas** virou rotina (limite seguro do plano básico).

A HostGator permite upgrade in-place (a VPS reinicia uma vez). Snapshot antes, por garantia.

---

### 10.A Provisionamento automatizado (alternativa ao passo-a-passo)

Para quem prefere um único comando ao invés de fazer 10.1-10.5 à mão, o repositório terá (Fase 8 do plano) um script `deploy/install.sh` idempotente:

```bash
# Após contratar a VPS e fazer o primeiro login como root:
ssh root@<vps-ip>
curl -fsSL https://raw.githubusercontent.com/JeanFD/O_Despertar_das_Raizes/main/deploy/install.sh | bash -s -- --domain despertarraizes.com.br --email seu@email.com
```

O script executa, na ordem, **tudo de 10.2 a 10.5**: hardening, usuário não-root, firewall, fail2ban, dependências, clone do repo, venv, systemd units, nginx, TLS via certbot. É seguro rodar de novo — detecta o que já foi feito e pula.

> **Recomendação:** na primeira vez, **faça à mão (10.1-10.5)** para entender o que cada passo faz. Da segunda VPS em diante (ex: migração, ambiente de teste), use o script.

### 10.B Custos estimados (HostGator Brasil — preços de referência)

| Item | Custo | Comentário |
|---|---|---|
| **VPS Snappy 1000** (1 vCPU, 2 GB) | ~R$ 60/mês | Suporta ~15 salas simultâneas. Suficiente para teste e early players. |
| **VPS Snappy 2000** (2 vCPU, 4 GB) | ~R$ 110/mês | Suporta ~30 salas. **Sweet spot** para produção. |
| **Domínio .com.br** | ~R$ 40/ano | Registro.br direto sai mais barato que via HostGator. |
| **TLS (Let's Encrypt)** | gratuito | Renovação automática via certbot. |
| **Backup snapshot HostGator** | ~R$ 15/mês | Opcional — você pode fazer scp manual também. |
| **Total mensal estimado** | **R$ 60-130/mês** | Para até 30 salas simultâneas. |

---

## 11. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Refactor para `Simulation` headless quebra single-player | Alta | Médio | Fase 0 separada, com critério explícito de "single-player continua funcionando" antes de mergear. |
| Determinismo divergente entre cliente e servidor (float drift) | Média | Alto | Usar `FIXED_DT = 1/60` exato; evitar `time.monotonic()` dentro da simulação. Snapshot a 30 Hz corrige drifts pequenos automaticamente. |
| HostGator não tem datacenter em SP | Baixa | Médio | Conferir antes de contratar. Se necessário, alternativas: Magalu Cloud, AWS Lightsail SP, DigitalOcean SP. |
| Latência alta (>150 ms) torna prediction agressiva visível | Média | Médio | Interp window adaptativo (100→200 ms conforme RTT). Aceitar como "modo internacional". |
| DDoS na porta 7777-7799 | Baixa | Alto | `fail2ban` + rate limit por IP no nível do socket. Tamanho de pacote limite. |
| Custo da VPS escala mal com sucesso | Baixa | Baixo | Migrar para Lightsail/Hetzner depois — código não muda. |

---

## 12. O que NÃO está no escopo desta proposta

Coisas que ficam para depois ou para outras propostas:

- **Reconnect automático em queda de rede** (item já no roadmap do README).
- **Anti-cheat sério** (validar fisicamente cada input no servidor — só faz sentido se houver competitivo ranqueado).
- **Replay system** (gravar inputs do servidor para replay determinístico).
- **Voice chat** — fora do escopo, usar Discord/Mumble.
- **Mobile/web client** — Pygame não roda em mobile nativo; web exigiria pygbag + WebSocket.
- **Persistência de progresso entre partidas** (XP, ranking) — só faz sentido com conta de usuário, que exige sistema de login.

---

## 13. Critérios de sucesso

O projeto será considerado um sucesso quando, **com a VPS no ar**:

1. ✅ Dois jogadores em casas diferentes (qualquer estado do Brasil) conseguem entrar em uma sala em < 30 s desde abrir o jogo.
2. ✅ O P2 não tem input lag perceptível (subjetivo: "sente igual ao single-player").
3. ✅ O RemotePlayer se move com fluidez visível, sem stutter, mesmo com 100 ms de latência.
4. ✅ Ataques registram hit/miss de forma justa para ambos os lados (lag comp funcionando).
5. ✅ Servidor sobrevive a 24 h ininterruptas sem vazamento de memória ou crash.
6. ✅ Reiniciar a VPS recompõe tudo automaticamente sem intervenção manual.

---

## 14. Próximos passos sugeridos

1. **Decidir**: aceitar a arquitetura como está, ajustar escopo, ou pedir alternativas (ex: usar Photon/Mirror em vez de stack próprio).
2. Se aceita: **abrir issues no GitHub** uma por fase (0-9), nessa ordem.
3. **Contratar a VPS** já na Fase 3 (servidor headless) — antes disso, dá pra simular tudo localmente.
4. **Reservar tempo** para a Fase 0 (refactor): é o investimento que destrava todo o resto.

---

*Documento técnico — revisão 1 — autoria: análise da base existente em `engine/`, `network/`, `entities/`, `states/`.*
