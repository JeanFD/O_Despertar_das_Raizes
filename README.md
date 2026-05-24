# O Despertar das Raízes

Jogo de plataforma 2D com combate, exploração e multiplayer local (LAN). Engine própria em Python + pygame, com modos cooperativo, boss-fight e versus 1v1.

> **Status:** em desenvolvimento ativo. Single-player e multiplayer LAN funcionais; arte de placeholder em parte dos sprites.

---

## Modos de jogo

| Modo | Descrição |
|---|---|
| **Single-player** | Campanha exploratória — atravessar mundo construído com Tiled (`world.tmx`), enfrentar inimigos, coletar itens, derrotar bosses |
| **Cooperativo (LAN)** | Dois jogadores na mesma rede compartilham a campanha |
| **Boss-fight (LAN)** | Um jogador controla o herói, outro controla o boss em arena dedicada |
| **Versus 1v1 (LAN)** | Partida competitiva best-of-3 com sistema de rounds (READY → COUNTDOWN → FIGHTING → ROUND_END), timer, ring-out e match-end autoritativo no host |

Descoberta de host na LAN é automática (broadcast UDP na porta 7779) — basta o jogador clicar em "Procurar partidas".

---

## Arquitetura

Engine inspirada em ECS (Entity-Component-System) com state machine global e fixed timestep.

```
┌──────────────────────────────────────────────────────────────┐
│  Game (engine/game.py)                                       │
│  Game loop a 60 FPS · MAX_FRAME_DT cap para suspend/resume   │
│                                                              │
│  ┌─────────────┬──────────────┬─────────────┬────────────┐  │
│  │ AssetMgr    │  EventBus    │ StateMachine│ Settings   │  │
│  └─────────────┴──────────────┴─────────────┴────────────┘  │
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
         ┌─────────────────────────────────────┐
         │  Network (UDP discovery + TCP/UDP)  │
         │  HostAnnouncer ◄─ broadcast ─► Cli  │
         │  protocol.py: HI / INP / ST / EV    │
         │  VersusMatch: regras autoritativas  │
         └─────────────────────────────────────┘
```

### Decisões técnicas

- **Fixed timestep + cap de delta** (`MAX_FRAME_DT = 1/30`) — evita que jogadores atravessem o chão quando a janela perde foco e o SO devolve um delta absurdo no resume. AABB simples sem sweep, então o cap é a defesa.
- **VersusMatch é puramente lógica** (sem pygame, sem render) — facilita serialização para enviar snapshots autoritativos do host ao cliente.
- **Discovery falha silenciosa** — se a porta 7779 está ocupada, o jogo segue funcionando (só perde o auto-descobrir; host manual pelo IP continua).
- **Settings persistidas em `data/settings.json`** — fullscreen, volume, shake, mostrar FPS — aplicadas antes do menu para evitar flicker no startup.
- **Save system slot-based** — múltiplos slots de save em `data/saves/`.

---

## Estrutura do projeto

```
O_Despertar_das_Raizes/
├── main.py
├── settings.py             # Constantes globais (resolução, FPS, gravidade, portas)
│
├── engine/                 # Core do motor
│   ├── game.py             # Game loop + bootstrap dos subsistemas
│   ├── state_machine.py    # Pilha de estados
│   ├── asset_manager.py    # Cache de imagens/sons
│   ├── camera.py           # Câmera com follow + clamping
│   ├── event_bus.py        # Pub/sub para eventos de jogo
│   ├── settings_manager.py # Leitura/escrita de data/settings.json
│   └── versus_match.py     # Engine autoritativa de match 1v1 (best-of-N)
│
├── states/                 # Todos os estados/telas
│   ├── main_menu.py
│   ├── settings_state.py
│   ├── save_menu.py
│   ├── lobby_state.py
│   ├── multiplayer_menu.py
│   ├── play_state.py
│   ├── gameplay.py
│   ├── multiplayer_gameplay.py
│   ├── versus_gameplay.py
│   ├── versus_post_match.py
│   ├── respawn_state.py
│   └── pause.py
│
├── systems/                # Sistemas (ECS-like)
│   ├── physics_system.py   # Gravidade, colisão AABB com tilemap
│   ├── combat_system.py    # Hitbox vs hitbox, dano, knockback
│   ├── ability_system.py   # Cooldowns e ativação de habilidades
│   └── render_system.py    # Desenho ordenado por z
│
├── entities/               # Atores do mundo
│   ├── player.py           # Player local (458 linhas — controle, animação, abilities)
│   ├── remote_player.py    # Player espelhado do peer remoto
│   ├── boss.py
│   ├── projectile.py
│   ├── remote_projectile.py
│   ├── pickup.py
│   ├── spike.py
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
│   ├── arena.py            # Mapa dedicado ao versus
│   └── parallax_layer.py
│
├── network/                # Multiplayer LAN
│   ├── discovery.py        # Broadcast UDP HostAnnouncer / busca
│   ├── host.py             # Servidor autoritativo
│   ├── client.py           # Cliente que recebe snapshots
│   ├── connection.py       # Wrapper de socket com timeout
│   └── protocol.py         # Tipos de mensagem (HI / INP / ST / EV) + encode/decode JSON
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
    └── maps/               # world.tmx, arena.tmx (Tiled)
```

Total: ~5.200 linhas de Python.

---

## Protocolo de rede (resumo)

Mensagens trafegam como JSON compacto em UTF-8. Cada pacote tem `t` (tipo) e `ts` (monotonic timestamp).

| Tipo | Direção | Uso |
|---|---|---|
| `HI` / `HI_ACK` | C→H / H→C | Handshake inicial |
| `INP` | C→H | Input do cliente |
| `ST` | H→C | Snapshot autoritativo de estado |
| `EV` / `EV_ACK` | H↔C | Eventos críticos confirmados (round_start, round_end, match_end, dmg, died, ability, pickup) |
| `PING` / `PONG` | C↔H | Heartbeat |
| `BYE` | qualquer | Desconexão |

Portas padrão (configuráveis em `settings.py`):
- `7777` — host TCP/UDP
- `7778` — cliente
- `7779` — discovery (broadcast)

---

## Como rodar

### Requisitos

- Python 3.10+
- `pygame`, `pytmx`

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

Abre no menu principal. Use `Settings` para alternar fullscreen, mostrar FPS, ajustar volume.

### Multiplayer LAN

1. Ambos os jogadores precisam estar na mesma rede local
2. Um deles entra em `Multiplayer → Hospedar` e escolhe o modo (coop / boss / versus)
3. O outro entra em `Multiplayer → Procurar partidas` — a busca usa broadcast UDP, não precisa digitar IP
4. Lobby confirma conexão antes do match começar

### Sair do jogo

`ESC` em qualquer estado, ou fechar a janela.

---

## Controles padrão

| Tecla | Ação |
|---|---|
| Setas / WASD | Mover |
| Espaço | Pular |
| J / K / L | Habilidades (ataque, especial, defesa) |
| ESC | Pausar / voltar ao menu |

(Mapeamentos exatos em `entities/player.py` — sistema de rebinding ainda não exposto na UI de settings.)

---

## Roadmap

- Substituir arte placeholder por sprites finais
- Sistema de rebinding de teclas exposto na UI
- Mais bosses e biomas no mapa cooperativo
- Persistência de progresso no modo versus (ranking local)
- Reconexão automática em queda de rede

---

## Licença

A definir — projeto pessoal em desenvolvimento.

## Autores

- **Jean Ferreira Dias** — [github.com/JeanFD](https://github.com/JeanFD)
- **Lara Domingos Viana** — [github.com/Lara-Viana](https://github.com/Lara-Viana)
