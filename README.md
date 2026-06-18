# Anti-Wallhack — Fog of War com Dead-Reckoning

> Sistema que **minimiza** (não elimina) a vantagem do wallhack no Valorant,
> protegendo a memória do cliente de posições de inimigos fora da linha de visão,
> sem introduzir pop-in visual ou overhead significativo de servidor.

**Leia antes:** este sistema é uma camada de defesa complementar ao Vanguard,
não um substituto. Veja a [análise honesta de limitações](#9-limitações-e-o-que-este-sistema-não-faz).

---

## Índice

1. [O problema](#1-o-problema)
2. [Como o wallhack funciona](#2-como-o-wallhack-funciona)
3. [Como este sistema funciona — explicação didática](#3-como-este-sistema-funciona--explicação-didática)
4. [Dead-reckoning — eliminando o pop-in](#4-dead-reckoning--eliminando-o-pop-in)
5. [Fórmula de delay total](#5-fórmula-de-delay-total)
6. [O ESP wallhack simulado](#6-o-esp-wallhack-simulado)
7. [Arquitetura](#7-arquitetura)
8. [Como rodar](#8-como-rodar)
9. [Limitações e o que este sistema não faz](#9-limitações-e-o-que-este-sistema-não-faz)
10. [Benchmarks](#10-benchmarks)

---

## 1. O problema

Cheats de wallhack do tipo ESP (Extra Sensory Perception) leem a memória do cliente de jogo
para encontrar as posições de todos os inimigos, mesmo os que estão atrás de paredes.
O resultado na tela: bonecos desenhados sobre paredes, sem o mapa, mostrando exatamente
onde cada inimigo está.

O Valorant já tem Fog of War server-autoritativo: o servidor não envia posições de inimigos
que não estão em linha de visão (LOS). Mas existe uma janela de exploração:

```txt
Situação sem este sistema:
  Tick N:   inimigo estava visível → cliente guardou pos=(1450, 3200) em memória
  Tick N+1: inimigo saiu do LOS   → servidor não manda nova posição
  Tick N+2: inimigo ainda fora    → memória AINDA guarda pos=(1450, 3200)
  Wallhack: lê a memória e vê pos=(1450, 3200) → vantagem!
```

Este sistema fecha essa janela.

---

## 2. Como o wallhack funciona

Um ESP wallhack típico:

1. Abre o processo do jogo e lê a memória
2. Encontra o array de posições dos jogadores
3. Desenha bonecos coloridos na tela sobre as posições lidas
4. **Não desenha o mapa** — só os bonecos (por isso "Extra Sensory")

A informação crítica é a posição. Se a posição não está na memória, o cheat não funciona.

---

## 3. Como este sistema funciona — explicação didática

### O raycasting decide quem você pode ver

O servidor lança 360 raios em todas as direções a partir da sua posição:

```j
        raio →→→→→[PAREDE] ← bloqueado, para aqui
       /
      /
[VOCÊ] ——raio→→→→→→→→→→→→→→→→→ ← livre! alcança o inimigo
      \
       \
        raio →→→→→→→[PAREDE] ← bloqueado
```

Se algum raio chegar até um inimigo sem bater em parede: **inimigo visível → posição exata enviada**.  
Se todos os raios forem bloqueados: **inimigo não visível → nada enviado**.

> [!NOTE]
> Não há gradação por distância. É o mesmo modelo do Valorant: você vê ou não vê.

### O que fica na memória do cliente

```j
┌────────────────────────────────────────────────────────────┐
│  MEMÓRIA DO CLIENTE (ClientPacket)                         │
│                                                            │
│  inimigo 1: VISÍVEL  → pos=(1450, 3200)  ← exato          │
│  inimigo 2: NÃO VIS. → (nada)            ← não existe     │
│  inimigo 3: NÃO VIS. → ghost DR ~(900,2100) ← impreciso   │
│  inimigo 4: VISÍVEL  → pos=(2100, 1800)  ← exato          │
└────────────────────────────────────────────────────────────┘
```

Um cheat que lê essa memória:

- Para inimigos visíveis: vê a posição — mas o cliente legítimo também vê, então **zero vantagem**
- Para inimigos não visíveis: não encontra nada — **zero vantagem**
- Para ghost DR: encontra posição extrapolada imprecisa que expira em 250ms — **vantagem mínima**

### Resultados da simulação do ESP

| Situação | Inimigos extras via cheat (sem proteção) | Com proteção |
| --- | --- | --- |
| Jogo sem este sistema | +7 de 8 inimigos revelados | — |
| Com proteção, player no centro | +3.2 em média | **60% de redução** |
| Com proteção, mapa denso (40 obstáculos) | +1.5 em média | **~80% de redução** |
| Com proteção, todos em LOS | 0 extras | 100% (sem ganho mesmo sem proteção) |

---

## 4. Dead-reckoning — eliminando o pop-in

### O problema

Quando um inimigo sai do LOS, o servidor para de enviar a posição.
Sem compensação, o cliente apagaria o boneco instantaneamente — e quando o inimigo
voltasse ao LOS, ele "teleportaria" para a nova posição. Isso é pop-in.

### A solução: três camadas

```j
Camada 1 — Lerp adaptativo:
  Quando o inimigo está visível, o cliente suaviza a posição entre ticks.
  Quanto mais longe do alvo, mais rápido o lerp (evita lag perceptível).

Camada 2 — Ghost DR:
  Quando o inimigo sai do LOS, o servidor calcula a posição provável
  a partir da velocidade estimada e inclui no ClientPacket como "ghost".
  O cliente desenha um boneco desbotado/tracejado por até 250ms.

  pos_ghost = última_pos + velocidade × tempo_desde_saída_do_LOS
  (limitado a 250ms para evitar previsões absurdas)

Camada 3 — Fade out:
  Se o ghost DR expirar (250ms), o cliente escurece gradualmente
  o boneco por 8 frames antes de sumir. Nunca desaparece abruptamente.
```

> [!IMPORTANT]
> O ghost usa apenas dados que o cliente já recebeu legitimamente. O cheat que lê a memória do ghost vê apenas a última posição autorizada + extrapolação de velocidade — não há informação nova.

---

## 5. Fórmula de delay total

$$
D_T = \left(\frac{P}{2}\right) + T_c + J_c + M_s
$$

- $D_T$ - Delay total
- $P$ - Ping (em `ms`)
- $T_c$ - Compensação do Tick
- $J_c$ - Compensação do Jitter
- $M_s$ - Margem de Segurança

| Componente | Fórmula | Descrição |
| --- | --- | --- |
| `Ping / 2` | RTT / 2 | One-way delay ao servidor (metade do RTT) |
| `Compensação do Tick` | 1000 / server_fps | Janela de um tick completo (16.67ms @ 60 TPS) |
| `Compensação do Jitter` | std_dev(inter-tick intervals) | Variação estatística entre ticks consecutivos |
| `Margem de Segurança` | 10ms fixo | Buffer conservador para picos de latência |

> [!NOTE]
> O DR precisa cobrir apenas o $D_T$ para garantir zero pop-in. Com cap de 250ms, o sistema cobre todos os cenários testados com folga.

---

## 6. O ESP wallhack simulado

O módulo `wallhack_esp.py` abre **duas janelas extras** durante a simulação:

**Janela 3 — ESP protegido** (verde no título):

- Simula um cheat lendo o `ClientPacket` filtrado
- Só vê o que o cliente legítimo já vê
- Mostra: bonecos laranjas (visíveis) + ghosts DR tracejados (imprecisos)
- Vantagem medida: **zero extras**

**Janela 4 — ESP desprotegido** (vermelho no título):

- Simula um cheat lendo o `state` bruto sem proteção
- Vê todos os inimigos independentemente de obstáculos
- Bonecos **vermelhos** = inimigos que o cheat revela ilegitimamente
- Label "ESP!" aparece sobre cada inimigo extra

> [!TIP]
> O HUD exibe em tempo real: vantagem atual, média e % de ticks com vantagem.

---

## 7. Arquitetura

```js
src/
├── security/
│   └── state.py              ← StateMemory + ClientPacket (filtro servidor→cliente)
├── sim/
│   ├── game.py               ← Servidor: raycasting, LOS, tick()
│   ├── client.py             ← Cliente legítimo: renderiza ClientPacket
│   ├── wallhack_esp.py       ← ESP simulado: protegido e desprotegido
│   ├── players.py            ← Movimento humano (WASD) + IA aleatória
│   ├── start.py              ← Entry point: 4 janelas + toggle R/H
│   ├── benchmark.py          ← Engine headless: CPU, delay, wallhack metrics
│   └── run_benchmark_comparison.py
```

### Fluxo de dados (seguro)

```js
  ┌──────────────────────────────────────────┐
  │  Servidor (game.py)                       │
  │  raycasting → classifica → StateMemory   │
  └──────────────────┬───────────────────────┘
                     │  get_client_packet()
                     │  (somente-leitura, filtrado)
              ┌──────▼──────────────────────────┐
              │  ClientPacket                    │
              │  {pid: level, pos, predicted_px} │
              └──────┬────────────────────────── ┘
                     │
         ┌───────────┼──────────────┐
         ▼           ▼              ▼
    Cliente      ESP protegido   (ESP desprotegido
    legítimo     (mesmos dados)   lê state bruto —
                                  simulação de cheat)
```

---

## 8. Como rodar

### Requisitos

- Python 3.10+
- Tkinter (`sudo apt install python3-tk` no Linux)
- psutil (`pip install psutil`)

### Simulação com ESP

```bash
python src/sim/start.py
```

> [!NOTE]
> Quatro janelas abrem:
> 1. Servidor (omnisciente, com raios)
> 2. Cliente legítimo (só o que o servidor autorizou)
> 3. ESP protegido (cheat lendo ClientPacket — sem vantagem)
> 4. ESP desprotegido (cheat lendo state bruto — com vantagem em vermelho)
> 5. O controlador do simulador. Você deve deixar aberta com foco, assim, locomovendo apertando, nessa janela, WASD.

> [!TIP]
> **Controles** (janela do Controlador):
> - `W A S D` — mover player1
> - `R` — ligar/desligar IA dos inimigos
> - `H` — ligar/desligar janelas ESP

### Benchmark

```bash
python src/sim/run_benchmark_comparison.py
```

Gera JSON + CSV para 4 cenários em `src/`.

---

## 9. Limitações e o que este sistema não faz

**Não detecta cheaters.** O Vanguard faz isso. Este sistema é complementar — reduz o
*valor* da informação obtida pelo cheat, não a capacidade de executar o cheat.

**Não protege inimigos em linha de visão.** Nem deve. Se você está em LOS com um inimigo,
o wallhack e o cliente legítimo veem a mesma coisa — sem vantagem marginal.

**Depende de mapas com obstáculos.** Em áreas abertas sem cobertura, o LOS é quase total
e o wallhack veria quase tudo de qualquer forma. O sistema é mais eficaz em mapas densos
— exatamente o estilo do Valorant.

**Não é produção-ready.** O `StateMemory` é um dict em processo. Em produção, os pacotes
precisam ser serializados, encriptados e transmitidos pela rede. A separação lógica já
existe; a camada de transporte precisa ser implementada.

**Ghost DR residual.** O cheat que lê o ghost DR vê uma posição imprecisa por até 250ms.
Isso é aceitável — a posição é extrapolada e não utilizável para aim assistance precisa.

---

## 10. Benchmarks

Ver `REPORT.md` para resultados completos. Resumo:

| Cenário | Compute (SP) | Overhead | WH Redução | DR Coverage | Delay Total (SP) |
| --- | --- | --- | --- | --- | --- |
| n_rays=360, 25 obs | ~0.57ms | ~3.4% | ~60% | 100% | ~42ms |
| n_rays=720, 25 obs | ~0.87ms | ~5.2% | ~60% | 100% | ~42ms |
| n_rays=360, 40 obs | ~0.88ms | ~5.3% | ~75-85% | 100% | ~42ms |
