# O Despertar das Raízes

Jogo de plataforma 2D com combate, exploração e multiplayer online. Engine própria em Python + pygame, com modos cooperativo, boss-fight e versus 1v1.

> **Status:** em desenvolvimento ativo. Single-player e multiplayer funcionais; arte de placeholder em parte dos sprites.

---

## Como rodar

### Requisitos

- Python 3.10+
- `pygame`, `pytmx` (únicas dependências)

### Instalação

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### Single-player

```bash
python main.py
```

Entrypoint único — abre direto no menu principal. Use `Configurações` para alternar fullscreen, mostrar FPS e ajustar volume.

### Multiplayer

O jogo usa um **servidor dedicado** com matchmaking por código de lobby — não é necessário estar na mesma rede local nem digitar IP.

1. No menu, entre em `Multiplayer`
2. Um jogador escolhe **Criar Partida** — o servidor devolve um código de lobby (ex.: `A3F9`)
3. O outro escolhe **Entrar na Partida** — a lista de lobbies abertos aparece automaticamente; `R` atualiza a lista
4. Se o lobby não estiver na lista, é possível digitar o código manualmente
5. O lobby confirma a conexão dos dois lados antes do match começar

O endereço do servidor fica em `settings.py` (`SERVER_HOST` / `MATCHMAKING_HOST`). Para rodar seu próprio servidor, veja `server/` — `matchmaking.py` (HTTP, porta 8080) e `game_server.py` (UDP, porta 7777), com `deploy.sh` de exemplo.

### Diagnóstico de rede

Se a conexão falhar, `test_net.py` testa a comunicação UDP sem subir o pygame:

```bash
python test_net.py host                     # máquina A
python test_net.py client <IP_DA_MAQUINA_A> # máquina B
```

`PONG recebido!` = rede OK. Travar em `Aguardando...` = firewall bloqueando.

**Liberar firewall (Windows, PowerShell como admin):**

```powershell
New-NetFirewallRule -DisplayName "ODespertarMP" -Direction Inbound -Protocol UDP -LocalPort 7777,7778,7779 -Action Allow
```

### Sair

`ESC` abre o pause; `Q` no pause volta ao menu. No menu principal, `Sair` encerra.

---

## Controles padrão

| Tecla | Ação |
|---|---|
| `A` `D` / `←` `→` | Mover |
| `Espaço` / `W` / `↑` | Pular |
| `S` / `↓` | Agachar / descer plataforma |
| `Shift` esquerdo | Correr |
| `Z` ou `J` | Ataque corpo a corpo |
| `X` ou `K` | Ataque à distância |
| `C` ou `L` | Parry / defesa |
| `ESC` | Pausar |

No modo boss-fight, quem controla o boss usa `←` `→` (mover), `↑` (pular) e `Teclado numérico 0` (atacar).

Mapeamentos exatos em `entities/player.py` e `entities/boss.py` — sistema de rebinding ainda não exposto na UI de configurações.

---

## Modos de jogo

| Modo | Descrição |
|---|---|
| **Single-player** | Campanha exploratória — atravessar mundo construído com Tiled (`world.tmx`), enfrentar inimigos, coletar itens, derrotar bosses |
| **Cooperativo** | Dois jogadores compartilham a campanha |
| **Boss-fight** | Um jogador controla o herói, outro controla o boss em arena dedicada |
| **Versus 1v1** | Partida competitiva best-of-3 (configurável) com rounds de 60s (READY → COUNTDOWN → FIGHTING → ROUND_END → MATCH_END), timer, ring-out e match-end autoritativo no host |

---

## Arquitetura

Engine inspirada em ECS (Entity-Component-System) com state machine global e fixed timestep.

```
┌──────────────────────────────────────────────────────────────┐
│  Game (engine/game.py)                                       │
│  Game loop a 60 FPS · MAX_FRAME_DT cap para suspend/resume   │
│                                                              │
│  ┌──────────┬───────────┬──────────────┬──────────┬───────┐  │
│  │ AssetMgr │ EventBus  │ StateMachine │ Settings │ Sound │  │
│  └──────────┴───────────┴──────────────┴──────────┴───────┘  │
│                          │                                   │
│         ┌────────────────┼────────────────┐                  │
│         ▼                ▼                ▼                  │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐          │
│  │  States    │  │  Systems    │  │  Entities    │          │
│  │ menus,     │  │ physics,    │  │ player, boss,│          │
│  │ gameplay,  │  │ combat,     │  │ enemies,     │          │
│  │ versus,    │  │ ability,    │  │ projectile,  │          │
│  │ lobby...   │  │ render      │  │ pickup...    │          │
│  └────────────┘  └─────────────┘  └──────────────┘          │
│                                          │                   │
│                          ┌───────────────┴──────────────┐    │
│                          ▼                              ▼    │
│                   ┌────────────┐                ┌─────────┐  │
│                   │ Components │                │  World  │  │
│                   │ animation, │                │ tilemap,│  │
│                   │ health,    │                │ arena,  │  │
│                   │ hitbox,    │                │ parallax│  │
│                   │ physics    │                │ layer   │  │
│                   └────────────┘                └─────────┘  │
└──────────────────────────────────────────────────────────────┘

         (Multiplayer)
         ┌────────────────────────────────────────────┐
         │  matchmaking.py  (HTTP :8080)              │
         │      cria/lista lobbies, devolve código    │
         │                    │                       │
         │                    ▼                       │
         │  game_server.py  (UDP :7777)               │
         │  simulação autoritativa · VersusMatch      │
         │  protocol.py: HI / INP / ST / EV           │
         └────────────────────────────────────────────┘
```

**Host autoritativo, cliente espelha.** O host roda toda a simulação (física, combate, regras de match) e envia snapshot autoritativo a cada frame. O cliente só envia inputs e aplica o snapshot recebido.

### Decisões técnicas

- **Fixed timestep + cap de delta** (`MAX_FRAME_DT = 1/30`) — evita que jogadores atravessem o chão quando a janela perde foco e o SO devolve um delta absurdo no resume. AABB simples sem sweep, então o cap é a defesa.
- **VersusMatch é puramente lógica** (sem pygame, sem render) — facilita serialização para enviar snapshots autoritativos do host ao cliente.
- **Snapshots idempotentes, eventos com ACK** — `ST` pode ser perdido sem prejuízo; mudanças de estado discretas (round_start, dmg, died, match_end) vão por `send_event`, com retransmissão a cada 100ms até 8 tentativas e dedupe por seq no cliente.
- **Settings persistidas em `data/settings.json`** — fullscreen, volume, shake, mostrar FPS — aplicadas antes do menu para evitar flicker no startup.
- **Save system slot-based** — múltiplos slots de save em `data/saves/`.

---

## Estrutura do projeto

```
O_Despertar_das_Raizes/
├── main.py
├── settings.py             # Constantes globais (resolução, FPS, gravidade, portas, IP do servidor)
├── test_net.py             # Diagnóstico manual de rede (não é teste unitário)
│
├── engine/                 # Core do motor
│   ├── game.py             # Game loop + bootstrap dos subsistemas
│   ├── state_machine.py    # Pilha de estados
│   ├── asset_manager.py    # Cache de imagens/sons
│   ├── sound_manager.py    # Música e SFX
│   ├── camera.py           # Câmera com follow + clamping
│   ├── event_bus.py        # Pub/sub para eventos de jogo
│   ├── settings_manager.py # Leitura/escrita de data/settings.json
│   └── versus_match.py     # Engine autoritativa de match 1v1 (best-of-N)
│
├── states/                 # Todos os estados/telas
│   ├── base_state.py
│   ├── main_menu.py
│   ├── settings_state.py
│   ├── credits_state.py
│   ├── save_menu.py
│   ├── lobby_state.py
│   ├── multiplayer_menu.py
│   ├── play_state.py
│   ├── gameplay.py
│   ├── multiplayer_gameplay.py
│   ├── versus_gameplay.py
│   ├── versus_post_match.py
│   ├── respawn_state.py
│   ├── victory_state.py
│   └── pause.py
│
├── systems/                # Sistemas (ECS-like)
│   ├── physics_system.py   # Gravidade, colisão AABB com tilemap
│   ├── combat_system.py    # Hitbox vs hitbox, dano, knockback
│   ├── ability_system.py   # Cooldowns e ativação de habilidades
│   └── render_system.py    # Desenho ordenado por z
│
├── entities/               # Atores do mundo
│   ├── entity.py           # Base com add/get de components
│   ├── player.py           # Player local (519 linhas — controle, animação, abilities)
│   ├── remote_player.py    # Player espelhado do peer remoto
│   ├── boss.py
│   ├── projectile.py
│   ├── remote_projectile.py
│   ├── pickup.py
│   ├── spike.py
│   ├── static_spike.py
│   └── enemies/
│       ├── crawler.py
│       └── scarecrow.py
│
├── components/             # Dados puros anexados a entities
│   ├── animation.py
│   ├── health.py
│   ├── hitbox.py
│   └── physics_body.py
│
├── world/                  # Construção e renderização do mundo
│   ├── tilemap.py          # Carrega TMX via pytmx
│   ├── level.py
│   ├── arena.py            # Mapa dedicado ao versus (fallback procedural se o TMX falhar)
│   └── parallax_layer.py
│
├── network/                # Cliente de rede
│   ├── server_client.py    # Conexão com o servidor dedicado
│   ├── host.py             # Servidor autoritativo (host local)
│   ├── client.py           # Cliente que recebe snapshots
│   ├── connection.py       # Wrapper de socket UDP (recv + heartbeat em threads)
│   ├── discovery.py        # Broadcast UDP na LAN (legado)
│   └── protocol.py         # Tipos de mensagem (HI / INP / ST / EV) + encode/decode JSON
│
├── server/                 # Servidor dedicado (roda no VPS)
│   ├── matchmaking.py      # HTTP :8080 — cria/lista/join de lobbies por código
│   ├── game_server.py      # UDP :7777 — simulação autoritativa headless
│   ├── dedicated_conn.py
│   └── deploy.sh
│
├── ui/
│   ├── hud.py              # HP bar, timer, banners de round
│   └── menu_ui.py          # Botões e widgets compartilhados
│
├── data/
│   ├── settings.json       # Preferências do usuário
│   ├── save_system.py
│   └── saves/              # Slots de save (gerados em runtime)
│
└── assets/
    ├── images/             # Sprites, backgrounds (placeholder em parte)
    ├── audio/              # Música e efeitos sonoros
    └── maps/               # world.tmx, arena.tmx (Tiled)
```

Total: ~7.600 linhas de Python.

---

## Protocolo de rede (resumo)

Mensagens trafegam como JSON compacto em UTF-8 sobre **UDP**. Cada pacote tem `t` (tipo) e `ts` (monotonic timestamp).

| Tipo | Direção | Uso |
|---|---|---|
| `HI` / `HI_ACK` | C→H / H→C | Handshake inicial |
| `INP` | C→H | Input do cliente (todo frame) |
| `ST` | H→C | Snapshot autoritativo de estado (todo frame) |
| `EV` / `EV_ACK` | H↔C | Eventos críticos confirmados (round_start, round_end, match_end, dmg, died, ability, pickup) |
| `PING` / `PONG` | C↔H | Heartbeat (1s) |
| `BYE` | qualquer | Desconexão |

Portas:

| Porta | Protocolo | Uso | Definida em |
|---|---|---|---|
| `7777` | UDP | Game server / host | `settings.py` |
| `7778` | UDP | Cliente | `settings.py` |
| `7779` | UDP | Discovery na LAN (legado) | `network/discovery.py` |
| `8080` | HTTP | Matchmaking (lobbies) | `settings.py` |

Timeout de conexão: `NET_TIMEOUT = 5.0` (`settings.py`).

---

## Roadmap

- Substituir arte placeholder por sprites finais
- Sistema de rebinding de teclas exposto na UI
- Mais bosses e biomas no mapa cooperativo
- Persistência de progresso no modo versus (ranking local)
- Reconexão automática em queda de rede
- Suporte a mais de 2 jogadores

---

## Licença

A definir — projeto pessoal em desenvolvimento.

## Autores

- **Jean Ferreira Dias** — [github.com/JeanFD](https://github.com/JeanFD)
- **Lara Domingos Viana** — [github.com/Lara-Viana](https://github.com/Lara-Viana)
