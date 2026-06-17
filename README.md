# Anti-Wallhack — Fog of War com Predição por Dead-Reckoning

> Prova de conceito submetida à Riot Games demonstrando como o Fog of War server-autoritativo,
> combinado com dead-reckoning no cliente, elimina cheats de wallhack **e** previne
> o "teleporte" visual de jogadores sem vazar nenhuma informação adicional de posição.

---

## Índice

1. [O problema](#1-o-problema)
2. [Como o wallhack funciona hoje](#2-como-o-wallhack-funciona-hoje)
3. [A ideia central — explicação didática](#3-a-ideia-central--explicação-didática)
4. [Dead-reckoning — resolvendo o pop-in](#4-dead-reckoning--resolvendo-o-pop-in)
5. [Zonas de visibilidade](#5-zonas-de-visibilidade)
6. [Arquitetura do sistema](#6-arquitetura-do-sistema)
7. [Como rodar](#7-como-rodar)
8. [Benchmarks](#8-benchmarks)
9. [Referência de configuração](#9-referência-de-configuração)
10. [Propriedades de segurança](#10-propriedades-de-segurança)
11. [Limitações e trabalho futuro](#11-limitações-e-trabalho-futuro)
12. [English version](#12-english-version)

---

## 1. O problema

Cheats de wallhack funcionam lendo a memória do cliente para obter a posição de **todos** os
jogadores, mesmo os que estão atrás de paredes ou fora do campo de visão.

League of Legends já tem um sistema de Fog of War que esconde inimigos invisíveis.
Mas existe uma brecha: o cliente às vezes guarda em memória a última posição conhecida
do inimigo — e o cheat simplesmente lê esse valor.

Este protótipo propõe dois aperfeiçoamentos sobre o mecanismo que já existe no jogo:

1. O servidor **nunca envia coordenadas exatas** de jogadores que estão fora do cone de visão total.
2. O cliente usa **dead-reckoning** para suavizar o movimento e evitar o "teleporte" visual
   que resultaria da remoção abrupta de posições.

---

## 2. Como o wallhack funciona hoje

Imagine que o servidor manda a posição de todo mundo para o cliente, mesmo os que
estão atrás de paredes, com o argumento de "o cliente vai precisar logo".

O cheat simplesmente abre a memória do jogo e lê: *"inimigo está em X=1450, Y=3200"*.

O Fog of War resolve parte disso ao não mandar a posição de inimigos não-visíveis.
Mas muitas implementações ainda guardam a **última posição conhecida** em memória
por um período de graça — e o cheat lê isso também.

---

## 3. A ideia central — explicação didática

### Pense em sinais de rádio com alcance variável

Imagine que você é um jogador num mapa. Cada inimigo emite um "sinal". Esse sinal
tem diferentes intensidades dependendo de onde o inimigo está em relação a você:

```
        [ VOCÊ ]
           |
    ┌──────┴──────────────────────────┐
    │                                 │
   0.33×R        0.66×R             R (raio máximo)
    │                                 │
  SINAL         SINAL             SINAL
  FORTE         FRACO            MÍNIMO
 (full)       (partial)       (position_only)
```

- Se o inimigo está **perto e visível** → você recebe a posição exata. Cliente desenha o boneco.
- Se o inimigo está **mais longe mas ainda visível** → você recebe só uma célula arredondada do grid.
  Cliente desenha um **círculo de probabilidade** ("ele está _em algum lugar_ aqui").
- Se o inimigo está **no limite do alcance** → círculo ainda maior e mais vago.
- Se o inimigo está **atrás de uma parede ou fora do alcance** → você não recebe nada.

### O que o cheat vê na memória

| Situação | Sem esta melhoria | Com esta melhoria |
|---|---|---|
| Inimigo atrás de parede | Posição exata em memória | Nada (ou ghost desbotado) |
| Inimigo longe mas visível | Posição exata em memória | Só uma célula de grid (~40-100px de precisão) |
| Inimigo perto e visível | Posição exata | Posição exata (necessário para renderização) |

O cheat de wallhack mais perigoso é o que revela inimigos atrás de paredes.
Com esta abordagem, a memória do cliente simplesmente **não tem essa informação**.
Não tem como roubar o que não existe lá.

### O raycasting (como o servidor decide o que você vê)

O servidor lança N raios em 360° a partir da sua posição:

```
         ray →→→→→[PAREDE]  (bloqueado)
        /
       /
[VOCÊ] ——ray→→→→→→→→→→→→→→→→→→ (livre, alcança o inimigo)
       \
        \
         ray →→→→→→→→→→→→[PAREDE] (bloqueado)
```

Se algum raio chegar até o inimigo sem bater em parede → inimigo é visível.
O servidor então decide qual nível de informação enviar baseado na distância.

---

## 4. Dead-reckoning — resolvendo o pop-in

### O problema sem DR

Quando um inimigo sai do cone de visão, o servidor para de mandar a posição.
Sem DR, o cliente apagaria o boneco instantaneamente. Na próxima vez que o
inimigo entrasse na visão, ele "teleportaria" para a nova posição — um artefato
visual muito estranho.

### A solução

`StateMemory` guarda a **velocidade estimada** do jogador, calculada a partir
das últimas duas posições recebidas:

```
Tick 5:  pos=(10, 5)
Tick 6:  pos=(11, 5)  →  velocidade estimada = (+1 célula/tick, 0)

Tick 7:  servidor manda "none" (inimigo saiu do FOV)
         cliente calcula: posição provável = (12, 5)
         desenha um ghost desbotado/tracejado em (12, 5)

Tick 8:  inimigo volta para o FOV → pos=(12, 5) (confirmado!)
         cliente faz lerp suave do ghost para a posição real → sem teleporte
```

O ghost desaparece após **250 ms** para evitar previsões absurdas.

**Importante para segurança:** o DR usa **apenas dados que o cliente já recebeu
legitimamente**. Nenhuma informação nova é calculada ou vazada.

---

## 5. Zonas de visibilidade

| Zona | Condição | O que o cliente recebe | O cliente renderiza |
|---|---|---|---|
| `full` | Visível + distância ≤ 33% do raio | Posição exata `(x, y, z)` | Avatar sólido |
| `partial` | Visível + 33–66% do raio | Célula arredondada do grid | Círculo de probabilidade (Ø 3 células) |
| `position_only` | Visível + 66–100% do raio | Célula arredondada do grid | Círculo de probabilidade (Ø 5 células) |
| `none` | Não visível | Nada | Ghost DR desbotado (desaparece em 250 ms) |

---

## 6. Arquitetura do sistema

```
src/
├── security/
│   └── state.py          ← StateMemory: servidor escreve, cliente lê
│                            + rastreador de velocidade para dead-reckoning
├── sim/
│   ├── game.py           ← Servidor: raycasting, zonas, geração de obstáculos
│   ├── client.py         ← Cliente: renderiza StateMemory + camada de ghost DR
│   ├── players.py        ← Movimento + detecção de colisão
│   ├── start.py          ← Ponto de entrada (simulação Tkinter)
│   ├── benchmark.py      ← Engine de benchmark sem UI
│   └── run_benchmark_comparison.py  ← Runner de múltiplos cenários
```

### Fluxo de dados

```
  ┌─────────────────────────────────────────────────────────┐
  │  Servidor (game.py)                                      │
  │  1. Raycasting por jogador  (compute_lines_of_sight)     │
  │  2. Classifica inimigos em zonas  (update_visibility)    │
  │  3. Escreve zona + pos limitada  →  StateMemory          │
  └──────────────────────┬──────────────────────────────────┘
                          │  StateMemory (ponte de memória)
  ┌──────────────────────▼──────────────────────────────────┐
  │  Cliente (client.py)                                     │
  │  1. Lê StateMemory.get_state(pid)                        │
  │  2. full: lerp em direção à posição prevista pelo DR     │
  │  3. partial/position_only: desenha círculo de área       │
  │  4. none: desenha ghost DR desbotado (se velocidade conhecida) │
  └─────────────────────────────────────────────────────────┘
```

---

## 7. Como rodar

### Requisitos

- Python 3.10+ (testado em 3.11 e 3.14)
- Tkinter (já vem com CPython; no Linux: `sudo apt install python3-tk`)
- Sem dependências externas

### Simulação interativa

```bash
# da raiz do projeto
python src/sim/start.py
```

Duas janelas abrem:
- **Server view** — mostra todos os jogadores, obstáculos e raios de raycasting.
- **Client view** — mostra só o que o servidor permitiu: avatares completos,
  círculos de probabilidade e ghosts DR.

**Controles (janela do servidor):** `W A S D` para mover `player1`.

### Benchmarks

```bash
python src/sim/run_benchmark_comparison.py
```

Produz 4 pares JSON + CSV em `src/`.

---

## 8. Benchmarks

Ver `REPORT.md` para análise completa. Resumo rápido:

| Cenário | TPS São Paulo | TPS Manaus | Budget 60TPS |
|---|---|---|---|
| Baseline (n_rays=180) | ~14 | ~7 | ✓ |
| Alta precisão (n_rays=720) | ~6 | ~4 | ✗ |
| Recomendado (adaptativo 180→360) | ~12 | ~6 | ✓ |

---

## 9. Referência de configuração

| Chave | Padrão | Descrição |
|---|---|---|
| `largura` | 10000 | Largura do canvas em pixels |
| `altura` | 10000 | Altura do canvas em pixels |
| `tamanho_celula` | 100 | Tamanho da célula do grid em pixels |
| `n_rays` | 180 | Raios lançados por jogador por tick |
| `server_fps` | 60 | Taxa de atualização do servidor |
| `client_fps` | 120 | Taxa de renderização do cliente |

---

## 10. Propriedades de segurança

| Vetor de ataque | Mitigação |
|---|---|
| Ler coordenadas exatas da memória | StateMemory só contém dados de zona |
| Ler posição parcial para localização grosseira | Intencional; círculo, não ponto (~40-100px) |
| Reconstruir posição a partir da velocidade DR | DR usa inteiros de grid (precisão de 1 célula) |
| Extrapolar DR ao longo de muitos ticks | Cap de 250 ms + sem novos updates = ghost desaparece |
| Falsificar escrita no StateMemory pelo cliente | StateMemory só é escrito pelo código do servidor |

---

## 11. Limitações e trabalho futuro

- **Apenas protótipo:** `StateMemory` é um dict em processo, não uma camada de rede real.
  Em produção, os pacotes de zona precisam ser serializados/encriptados na transmissão.
- **Obstáculos estáticos:** obstáculos são gerados uma vez. Paredes dinâmicas precisam
  incrementar `game.obstacles_version` para invalidar o cache de raios.
- **Observador único:** o raycasting roda uma vez por tick por jogador observado,
  sem escala para lobbies de 10 jogadores. Particionamento espacial (quadtree ou grid
  uniforme) é necessário para throughput em produção.
- **Sem integração anti-cheat:** este mecanismo reduz a *utilidade* dos wallhacks
  (sem coordenadas para explorar) mas não detecta software de cheat. É complementar
  ao AC de nível de driver, não um substituto.

---

---

## 12. English version

# Anti-Wallhack — Fog of War with Dead-Reckoning Prediction

> A proof-of-concept submitted to Riot Games demonstrating how server-authoritative
> Fog of War, combined with client-side dead-reckoning, eliminates wallhack cheats
> and prevents visual teleport pop-in without leaking any additional position data.

---

### How it works — plain English explanation

#### The core insight

A wallhack cheat works by reading the game client's memory.
The client needs to know where everyone is to render them smoothly,
so it traditionally stores full coordinates for all players locally.
The cheat just reads those coordinates.

The existing Fog of War already hides invisible enemies from the client.
This prototype adds two refinements:

**Refinement 1 — Tiered information zones**

Instead of sending either "full position" or "nothing", the server classifies
each enemy into one of four tiers before writing anything to memory:

```
                     [YOU]
                       |
         ─────────────────────────────
         0          0.33R    0.66R    R
         |            |        |      |
       (walls)      FULL   PARTIAL  POS_ONLY
                  exact   rounded  rounded
                  coords   cell     cell
```

- **full:** enemy is close and visible → client gets exact `(x,y,z)` → draws avatar
- **partial:** enemy is mid-range and visible → client gets a rounded grid cell → draws a probability circle (no precise aim possible)
- **position_only:** enemy is at the edge of range → larger vague circle
- **none:** enemy is behind a wall or out of range → client gets nothing

A cheat that reads client memory now finds either nothing, or a circle center
with ~1 grid-cell precision (~40-100 px). Not useful for aim assistance.

**Refinement 2 — Dead-reckoning to eliminate pop-in**

When an enemy leaves the FOV cone the server stops sending position data.
Without compensation the avatar would vanish instantly and reappear at a
different location when it re-enters FOV — a jarring visual teleport.

The fix: `StateMemory` tracks a velocity estimate from the last two `full`
position updates. When the server sends `none`, the client extrapolates
position for up to 250 ms and draws a faded ghost:

```
Server tick N:   full → pos=(10,5)  velocity estimated → (vx=1, vy=0)
Server tick N+1: none → client draws ghost at predicted (11, 5)
Server tick N+2: full → pos=(11,5)  ghost lerps to real position — no teleport
```

Security property: the DR prediction uses **only data the client already
received legitimately**. A cheat reading DR state sees the last known
full position — no new information is leaked.

---

### Architecture

```
src/
├── security/state.py          ← StateMemory bridge + DR velocity tracker
├── sim/game.py                ← Server: raycasting, zone classification
├── sim/client.py              ← Client: zone rendering + DR ghost layer
├── sim/players.py             ← Collision-safe movement
├── sim/start.py               ← Entry point (Tkinter simulation)
├── sim/benchmark.py           ← Headless latency benchmark engine
└── sim/run_benchmark_comparison.py  ← Multi-scenario benchmark runner
```

---

### How to run

```bash
# Interactive simulation
python src/sim/start.py

# Benchmark (all regions, all scenarios)
python src/sim/run_benchmark_comparison.py
```

Controls: `W A S D` to move `player1` in the server controller window.

---

### Visibility zones reference

| Zone | Condition | Client receives | Client renders |
|---|---|---|---|
| `full` | Visible + dist ≤ 33% radius | Exact `(x,y,z)` | Solid avatar |
| `partial` | Visible + 33–66% radius | Rounded grid cell | Ø 3-cell probability circle |
| `position_only` | Visible + 66–100% radius | Rounded grid cell | Ø 5-cell probability circle |
| `none` | Not visible | Nothing | Faded DR ghost (250 ms cap) |

---

### Security properties

| Attack | Before | After |
|---|---|---|
| Read exact coords from memory | Exact floats present | Only zone + rounded cell |
| Aim-assist from partial zone | N/A | ~1 cell precision, not aim-exploitable |
| Reconstruct pos from DR velocity | N/A | Integer grid cells, 250 ms cap |
| Read stale last-known position | Always in memory | Cleared when zone = none |

---

### Benchmark summary

| Scenario | São Paulo TPS | Manaus TPS | 60-TPS budget |
|---|---|---|---|
| Baseline n_rays=180 | ~14 | ~7 | ✓ compute < 16.7 ms |
| High-precision n_rays=720 | ~6 | ~4 | ✗ compute > 16.7 ms |
| Recommended adaptive | ~12 | ~6 | ✓ |

See `REPORT.md` for full methodology, all global regions, and optimization recommendations.
