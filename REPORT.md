# Relatório Técnico — Anti-Wallhack com Dead-Reckoning

## Impacto Competitivo, Benchmark com Fórmula de Delay e Análise de Vantagem ESP

**Submetido à:** Riot Games — Anti-Cheat / Game Security  
**Data:** 2026-06-18

---

> [!IMPORTANT]
> Este sistema **minimiza** a vantagem do wallhack no Valorant. Ele **não elimina** o problema.

## 1. Sumário

| Métrica | Valor (cenário realista, SP) |
| ------- | ---------------------------- |
| Compute por tick | ~0.57ms |
| Overhead do budget 60 TPS | ~3.4% |
| CPU do processo (raycasting) | < 5% |
| GPU utilizada | 0% (Canvas 2D = CPU-only) |
| DR coverage (anti pop-in) | 100% |
| Pop-in residual | 0 eventos |
| Redução de vantagem wallhack | ~60% (inimigos mistos: próximos + distantes) |
| Delay total (São Paulo, 30ms ping) | ~42ms |
| Delay total (Manaus, 120ms ping) | ~87ms |

O número de **60% de redução de vantagem** merece contexto: ocorre em cenário onde metade
dos inimigos está próxima (potencialmente visível) e metade está em cantos distantes do mapa.
Quando todos os inimigos estão atrás de obstáculos, a redução chega a 100%.
Quando todos estão em linha de visão direta, a redução é 0% — mas nesse caso o cheat não
oferece vantagem de qualquer forma (o cliente legítimo os vê).

---

## 2. Fórmula de Delay Total

### 2.1 Definição

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

### 2.2 Delay calculado por região (n_rays=360, 60 TPS)

| Região | Ping | Ping/2 | TickComp | JitterComp | Margem | **DelayTotal** |
| --- | --- | --- | --- | --- | --- | --- |
| São Paulo | 30ms | 15ms | 16.67ms | ~0.13ms | 10ms | **~42ms** |
| Rio de Janeiro | 40ms | 20ms | 16.67ms | ~0.15ms | 10ms | **~47ms** |
| Brasília | 55ms | 27.5ms | 16.67ms | ~0.15ms | 10ms | **~54ms** |
| Porto Alegre | 70ms | 35ms | 16.67ms | ~0.20ms | 10ms | **~62ms** |
| Manaus | 120ms | 60ms | 16.67ms | ~0.20ms | 10ms | **~87ms** |
| Los Angeles | 140ms | 70ms | 16.67ms | ~0.50ms | 10ms | **~97ms** |
| London | 180ms | 90ms | 16.67ms | ~0.70ms | 10ms | **~117ms** |
| Sydney | 260ms | 130ms | 16.67ms | ~1.00ms | 10ms | **~158ms** |

> [!TIP]
> O delay total representa a janela máxima de incerteza de posição que o
DR precisa cobrir. Com DR cap de 250ms, o ghost cobre confortavelmente todos os cenários
testados. A Compensação do Jitter é pequena (geralmente $\leqslant$ 1ms) porque o raycasting é determinístico e
não introduz variância de processamento significativa neste protótipo Python.

---

## 3. Uso de CPU e GPU

[![Watch the video](https://img.youtube.com/vi/HVZZQFaUx_E/hqdefault.jpg)](https://www.youtube.com/embed/HVZZQFaUx_E)

### 3.1 CPU


O raycasting é puramente sequencial e executado na thread do servidor a cada tick.

| Cenário | Compute puro | CPU do processo | Observação |
| --- | --- | --- | --- |
| n_rays=360, 25 obstáculos | ~0.20–0.57ms | < 5% | Python puro, single-thread |
| n_rays=720, 25 obstáculos | ~0.35–0.87ms | < 8% | 2× raios, ~60% mais compute |
| n_rays=360, 40 obstáculos | ~0.19–0.88ms | < 6% | mais obstáculos não aumentam muito; O(raios × obstáculos) por passo |

> [!NOTE]
> Os valores de CPU acima são para o processo de benchmark isolado.
Em produção com múltiplos jogadores simultâneos, o custo escala linearmente com o número
de pares (observador, alvo) — não com o total de jogadores.

### 3.2 GPU

**GPU utilizada: 0%.**

O protótipo usa Tkinter/Canvas, que é renderização 2D por CPU (sem aceleração de hardware).
Isso é intencional para o protótipo — a lógica do servidor (raycasting + StateMemory) não
usa GPU de nenhuma forma.

Em produção no Valorant:

- O servidor de jogo não renderiza nada — CPU only
- O cliente usa GPU para renderização, mas isso é independente deste sistema
- A vantagem deste sistema em produção é exatamente essa separação: o servidor (CPU) decide
  o que enviar; o cliente (GPU) renderiza apenas o autorizado

---

## 4. Simulação do Wallhack ESP

[![Watch the video](https://img.youtube.com/vi/WgowtZMCr2s/hqdefault.jpg)](https://www.youtube.com/embed/WgowtZMCr2s)

### 4.1 O que foi simulado

O módulo `wallhack_esp.py` simula dois cenários:

**Modo desprotegido** (`sem_protecao=True`):

- Lê o `state` bruto do servidor diretamente
- Desenha todos os inimigos em vermelho, sem obstáculos
- Representa o que um wallhack faria num jogo sem este sistema

> [!NOTE]
> O modo `Sem Proteção` é como o cheat se comportaria sem a proteção

**Modo protegido** (`sem_protecao=False`):

- Lê o mesmo `ClientPacket` que o cliente legítimo recebe
- Só pode desenhar o que o servidor autorizou
- Demonstra que o cheat não obtém informação adicional

> [!IMPORTANT]
> A "vantagem wallhack" é definida como: $ \text{vantagem} = (\text{inimigos que o cheat vê}) − (\text{inimigos que o cliente legítimo já vê}) $

### 4.2 Resultados da simulação

#### Cenário realista (player no centro, inimigos mistos — próximos e distantes)

| Situação | Inimigos extras via cheat | Redução de vantagem |
| --- | --- | --- |
| Sem proteção (baseline) | ~8 de 8 | — |
| Com proteção + player no canto | ~8 de 8 | ~0% (nenhum em LOS) |
| Com proteção + player no centro | ~3.2 de 8 | **~60%** |
| Com proteção + todos em LOS | 0 de 8 | 100% (cheat = legítimo) |

**Por que 60% e não 100%?**

Porque o sistema protege apenas inimigos **fora do LOS**. Os ~3.2 inimigos "extras" que o
cheat ainda vê são os que estão em linha de visão direta com o player1 — o cliente legítimo
também os veria, então não há vantagem real. O número de ~3.2 inclui inimigos em transição
(entrando/saindo do LOS durante o movimento da IA) cobertos pelo ghost DR.

A vantagem real do wallhack com este sistema ativo é **zero para inimigos visíveis** e
**provavelmente baixas para inimigos fora do LOS** (não há dado na memória. Entretanto, nos testes não foram expostos nenhum caso a qual o cheat recebia uma vantagem). O único valor residual seria
o ghost DR — mas ele contém apenas extrapolação de velocidade, não posição confirmada,
e expira em 250ms.

> [!WARNING]
> Poderá haver alguns movimentos sem sentidos, porém, acredito que não é algo que você poderá ver, principalmente em um FPS

### 4.3 Comparação visual (como aparece no ESP)

```j

SEM proteção:                        COM proteção:
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  [■] inimigo 1 (ESP!)        │    │  [■] inimigo 1 (já visível)  │
│  [■] inimigo 2 (ESP!)        │    │                              │
│  [■] inimigo 3 (ESP!)        │    │  [⋯] ghost DR inimigo 3      │
│  [■] inimigo 4 (já visível)  │    │  [■] inimigo 4 (já visível)  │
│  [■] inimigo 5 (ESP!)        │    │                              │
│  [■] inimigo 6 (ESP!)        │    │                              │
│  [■] inimigo 7 (ESP!)        │    │                              │
│  [■] inimigo 8 (ESP!)        │    │                              │
│  ← SEM obstáculos            │    │  ← SEM obstáculos            │
│  Vantagem: +7 inimigos       │    │  Vantagem: 0 inimigos        │
└──────────────────────────────┘    └──────────────────────────────┘

```

> [!NOTE]
> O ghost DR (⋯) aparece apenas para inimigos que saíram do LOS recentemente, com posição
imprecisa (extrapolada). Provavelmente não é útil para `Aim Assistance (Aimbot)`.

---

## 5. Benchmark

### 5.1 Cenário realista (n_rays=360, 25 obstáculos, IA ativa)

| Região | Ping | Compute | Overhead | TPS | WH Adv | WH Red% | DR Cov | DelayTotal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| São Paulo | 30ms | 0.57ms | 3.4% | ~24 | 3.2 | 60.0% | 100% | 41.8ms |
| Rio de Janeiro | 40ms | 0.57ms | 3.4% | ~21 | 3.2 | 60.0% | 100% | 46.8ms |
| Brasília | 55ms | 0.57ms | 3.4% | ~17 | 3.2 | 60.0% | 100% | 54.3ms |
| Porto Alegre | 70ms | 0.57ms | 3.4% | ~14 | 3.2 | 60.0% | 100% | 61.8ms |
| Manaus | 120ms | 0.57ms | 3.4% | ~8 | 3.2 | 60.0% | 100% | 86.8ms |

> [!NOTE]
> *TPS baixo em Manaus = RTT alto, não overhead do sistema. Compute permanece < 1ms.*

### 5.2 Alta precisão (n_rays=720, 25 obstáculos)

| Região | Compute | Overhead | WH Red% | DelayTotal |
| --- | --- | --- | --- | --- |
| São Paulo | 0.87ms | 5.2% | 60.0% | 42.1ms |
| Manaus | 0.87ms | 5.2% | 60.0% | 87.1ms |

> [!NOTE]
> Dobrar os raios aumenta o overhead de 3.4% para 5.2% — ainda confortável.
Não altera a vantagem wallhack (determinada por LOS, não por densidade de raios após certo limiar).

### 5.3 Mapa denso (n_rays=360, 40 obstáculos)

Com 40 obstáculos (mapa mais próximo do Valorant):

- Compute sobe levemente (~0.88ms) por causa de mais colisões por raio
- WH reduction **sobe para ~75-85%** porque mais obstáculos = menos LOS = wallhack vê menos
- Confirma que em mapas mais complexos o sistema é **mais eficaz**, não menos

---

## 6. O que este sistema NÃO faz

- **Não detecta cheaters.** Vanguard faz isso. Este sistema é complementar.
- **Não remove vantagem para inimigos em LOS.** Nem deve — o jogador legítimo também os vê.
- **Não funciona como única proteção.** Em mapas abertos sem obstáculos, o LOS é quase
  total e o wallhack veria tudo igualmente.
- **Não substitui driver-level AC.** Um cheat que intercepta pacotes de rede ainda
  receberia o ClientPacket — mas esse pacote já é filtrado por design.

### 6.1 Por que ainda vale para o Valorant

O Valorant tem mapas densos com múltiplas camadas de cobertura. Em condições típicas de
partida, estima-se que 60–80% dos inimigos estão fora do LOS em qualquer dado momento.
Este sistema blinda exatamente essa janela — os inimigos que o wallhack mais explora são
os que estão atrás de paredes enquanto o jogador se posiciona.

A vantagem tática eliminada é a mais importante: **saber que há um inimigo se posicionando
atrás de uma parede específica antes de você dobrar o ângulo**.

---

## 7. Conclusão

O sistema reduz a vantagem do wallhack em **~60% em condições mistas** e em até **100%
para inimigos fora do LOS** — que é exatamente o caso de uso principal do cheat.

O custo computacional foi considerado desprezível (< 5% do budget do servidor em Python puro). O anti pop-in é completo (DR coverage possuiu bons números em todos os testesm, demonstrando alta eficiência).

> [!WARNING]
> Como já comentado antes, esse projeto não é a solução para eliminar ESP e vazamento de state na memória, e sim um minimizador das vantagens do ESP. Além disso, o desempenho parece não ser afetado de forma significativa aqui, entretanto, vale ressaltar que essa implementação em jogos multiplayer poderá haver eficiência diferente. Com isso, é interessante fazer adaptações ao implementar

---

## Projeto & Testes

### A. Arquivos gerados

| Arquivo | Conteúdo |
| --- | --- |
| `benchmark_realista_brasil.json/csv` | n_rays=360, 25 obs, Brasil |
| `benchmark_realista_global.json/csv` | n_rays=360, 25 obs, global |
| `benchmark_hires_brasil.json/csv` | n_rays=720, 25 obs, Brasil |
| `benchmark_denso_brasil.json/csv` | n_rays=360, 40 obs, Brasil |
| `benchmark_all.json` | Todos consolidados |

### B. Como reproduzir

```bash
python src/sim/run_benchmark_comparison.py
```

### C. Como executar o ESP wallhack visual

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

### D. Dicionário

| Termo | Definição |
| --- | --- |
| LOS | Line of Sight — raio desobstruído entre observador e alvo |
| DR | Dead-reckoning — extrapolação de posição por velocidade estimada |
| ESP | Extra Sensory Perception — tipo de wallhack que desenha bonecos sobre paredes |
| RTT | Round-Trip Time — tempo de ida e volta na rede (ping) |
| ClientPacket | Snapshot somente-leitura gerado pelo servidor com dados filtrados por LOS |
| DelayTotal | Latência percebida pelo jogador incluindo ping, tick e jitter |
