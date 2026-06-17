# Relatório Técnico — Protótipo Anti-Wallhack
### Fog of War Server-Autoritativo com Predição por Dead-Reckoning

**Submetido à:** Riot Games — Anti-Cheat / Game Security  
**Data:** 2026-06-17

---

## Sumário Executivo

Este relatório documenta um aperfeiçoamento ao sistema de Fog of War (FoW) já presente em
League of Legends e títulos similares. A proposta consiste em dois mecanismos que atuam
em conjunto:

1. **Zonas de visibilidade server-autoritativas** — o servidor classifica cada inimigo em
   um de quatro níveis de informação antes de escrever qualquer dado na memória do cliente.
   O cliente jamais recebe coordenadas exatas de jogadores que não estão totalmente visíveis.

2. **Dead-reckoning (DR) no cliente** — para evitar o artefato visual de teleporte causado
   pela remoção abrupta de posições, o cliente extrapola a posição usando o vetor de
   velocidade derivado das duas últimas atualizações do servidor. O ghost é desbotado e
   limitado a 250 ms para evitar previsões absurdas.

Ambos os mecanismos operam inteiramente com dados já disponíveis no motor de jogo.
Nenhuma nova superfície de ataque é introduzida.

---

## 1. Motivação

### 1.1 Como os wallhacks funcionam atualmente

Um wallhack lê o espaço de endereços do cliente para encontrar structs de posição de
jogadores. Como o cliente precisa de renderização suave, ele tradicionalmente armazena
o estado completo do mundo localmente. Mesmo com FoW a nível de rede (servidor não envia
nada para inimigos invisíveis), muitas implementações guardam a última posição conhecida
em memória indefinidamente — o cheat simplesmente lê esse valor.

### 1.2 Brecha no FoW atual

O FoW do League of Legends já retém posições de inimigos invisíveis. Porém, duas brechas
persistem:

| Brecha | Impacto |
|---|---|
| Última posição conhecida permanece em memória do cliente | O cheat lê coordenadas obsoletas mas ainda úteis no curto prazo |
| Remoção repentina de posição causa teleporte visual ao reentrar no FOV | UX ruim leva muitas implementações a reintroduzir algum buffer — o que reexpõe coordenadas |

O sistema proposto fecha ambas as brechas simultaneamente.

---

## 2. Como o mecanismo funciona — explicação didática

### 2.1 A analogia do sinal de rádio

Pense em cada jogador como uma torre de rádio que emite sinais com diferentes intensidades
de acordo com a distância e obstrução:

```
         [VOCÊ]
            │
   ┌────────┴──────────────────────────┐
   │                                   │
  0.33×R         0.66×R              R (raio máximo)
   │                                   │
  SINAL          SINAL              SINAL
  FORTE          FRACO             MÍNIMO
 (full)        (partial)        (position_only)
```

- **Sinal forte (full):** inimigo próximo e visível → servidor envia posição exata
  → cliente desenha avatar sólido.
- **Sinal fraco (partial):** inimigo a média distância mas visível → servidor envia
  só a célula arredondada do grid → cliente desenha um **círculo de probabilidade**
  ("alguém está em algum lugar aqui").
- **Sinal mínimo (position_only):** inimigo no limite do alcance → círculo ainda
  maior e mais vago.
- **Sem sinal (none):** inimigo atrás de parede ou fora do alcance → cliente não
  recebe nada.

### 2.2 O que o raycasting faz

O servidor lança N raios em 360° a partir da posição do observador:

```
         raio →→→→→[PAREDE]  ← bloqueado
        /
       /
[VOCÊ] ——raio→→→→→→→→→→→→→→→ ← livre, alcança o inimigo
       \
        \
         raio →→→→→→→[PAREDE]  ← bloqueado
```

Se qualquer raio chegar até o inimigo sem colidir com obstáculo → inimigo é visível.
O servidor então decide qual nível de informação enviar com base na distância calculada.

### 2.3 O que o cheat encontra na memória

| Situação | Sem esta melhoria | Com esta melhoria |
|---|---|---|
| Inimigo atrás de parede | Posição exata em memória | Nada (ou ghost desbotado) |
| Inimigo longe mas visível | Posição exata em memória | Célula de grid (~40-100 px de precisão) |
| Inimigo próximo e visível | Posição exata | Posição exata (necessário para renderização) |

O wallhack mais perigoso é o que revela inimigos atrás de paredes. Com esta abordagem,
a memória do cliente simplesmente **não contém essa informação**. Não há como roubar o
que não existe.

### 2.4 Dead-reckoning — eliminando o teleporte visual

**O problema:** quando um inimigo sai do cone de visão, o servidor para de enviar
a posição. Sem compensação, o avatar desaparece instantaneamente. Na próxima vez que
o inimigo entrar no FOV, ele "teleporta" para a nova posição.

**A solução:** `StateMemory` mantém um vetor de velocidade estimado a partir das
últimas duas posições recebidas no nível `full`:

```
Tick N:   pos=(10,5)
Tick N+1: pos=(11,5)  →  velocidade = (+1 célula/tick, 0)

Tick N+2: servidor envia "none" (inimigo saiu do FOV)
          cliente calcula: posição provável = (12, 5)
          cliente desenha ghost desbotado/tracejado em (12,5)

Tick N+3: inimigo retorna ao FOV → pos=(12,5) confirmado pelo servidor
          cliente faz lerp suave: sem teleporte
```

**Propriedade de segurança:** o DR usa **exclusivamente dados já recebidos
legitimamente**. Um cheat que lê a memória encontra apenas a última posição
autorizada — nenhuma informação nova é calculada ou vazada.

---

## 3. Metodologia do Benchmark

### 3.1 O que é medido

| Métrica | Definição |
|---|---|
| `avg_tick_ms` | Tempo médio por tick do servidor incluindo metade do RTT simulado antes e depois do cálculo |
| `p95_tick_ms` | Percentil 95 do tempo de tick (indicador de cauda de latência) |
| `compute_ms` | Tempo puro de raycasting + classificação de visibilidade (sem ping simulado) |
| `tps` | Ticks por segundo efetivos = 1000 / avg_tick_ms |
| `budget_ok` | True se `compute_ms ≤ 16,67 ms` (budget de 60 TPS) |

### 3.2 Regiões simuladas

Os valores de ping representam RTTs típicos medidos a partir de cada região para um
nó de borda em São Paulo, com base em dados públicos de latência da Riot.

**Brasil**

| Região | Ping simulado |
|---|---|
| São Paulo | 30 ms |
| Rio de Janeiro | 40 ms |
| Brasília | 55 ms |
| Belo Horizonte | 48 ms |
| Curitiba | 52 ms |
| Porto Alegre | 70 ms |
| Salvador | 90 ms |
| Fortaleza | 110 ms |
| Recife | 105 ms |
| Manaus | 120 ms |
| Belém | 115 ms |

**América Latina** (Buenos Aires 80 ms → Caracas 110 ms)

**Global** (Los Angeles 140 ms → Sydney 260 ms)

### 3.3 Cenários de benchmark

| Cenário | n_rays | Ticks | Regiões |
|---|---|---|---|
| Baseline | 180 | 300 | Brasil |
| Alta precisão | 720 | 150 | Brasil |
| Global baseline | 180 | 150 | Todas |
| Global alta precisão | 360 | 100 | Todas |

---

## 4. Resultados

### 4.1 Baseline (n_rays = 180) — Brasil

| Região | Ping | Avg tick | P95 | Compute | TPS | Budget |
|---|---|---|---|---|---|---|
| São Paulo | 30 ms | ~71 ms | ~75 ms | ~11 ms | ~14 | ✓ |
| Rio de Janeiro | 40 ms | ~82 ms | ~87 ms | ~11 ms | ~12 | ✓ |
| Brasília | 55 ms | ~96 ms | ~102 ms | ~11 ms | ~10 | ✓ |
| Porto Alegre | 70 ms | ~111 ms | ~117 ms | ~11 ms | ~9 | ✓ |
| Fortaleza | 110 ms | ~152 ms | ~160 ms | ~11 ms | ~7 | ✓ |
| Manaus | 120 ms | ~161 ms | ~168 ms | ~11 ms | ~6 | ✓ |

O `compute_ms` (~11 ms) fica abaixo do budget de 16,67 ms para 60 TPS em todas as
regiões brasileiras com n_rays=180. O `avg_tick_ms` é dominado pelo ping simulado,
não pelo cálculo do servidor.

### 4.2 Alta precisão (n_rays = 720) — Brasil

| Região | Avg tick | Compute | TPS | Budget |
|---|---|---|---|---|
| São Paulo | ~179 ms | ~49 ms | ~5,6 | ✗ |
| Manaus | ~269 ms | ~49 ms | ~3,7 | ✗ |

O raycasting de alta precisão aumenta o tempo de computação ~4,5× e ultrapassa o
budget de 60 TPS. Não recomendado para servidores competitivos sem a estratégia
adaptativa descrita na Seção 5.

### 4.3 TPS vs Ping — todas as regiões (baseline)

```
TPS
 14 │ ● São Paulo (30 ms)
 12 │   ● Rio (40 ms)
 10 │     ● Brasília (55 ms)
  9 │       ● Porto Alegre (70 ms)
  8 │         ● Buenos Aires (80 ms)
  7 │           ● Fortaleza (110 ms)
  6 │             ● Manaus (120 ms)
  5 │               ● Los Angeles (140 ms)
  4 │                   ● Londres (180 ms)
  3 │                       ● Sydney (260 ms)
    └──────────────────────────────────────→ Ping (ms)
      30   80  120  150  180  220  260
```

O TPS efetivo é inversamente proporcional ao ping porque `avg_tick_ms ≈ compute_ms + ping_ms`.

---

## 5. Recomendações

### 5.1 Densidade adaptativa de raios

Usar n_rays como função da distância do inimigo ao observador:

```
distância ≤ 0,33 × raio  →  n_rays = 360  (alta precisão para curta distância)
distância ≤ 0,66 × raio  →  n_rays = 180  (padrão)
distância >  0,66 × raio →  n_rays =  90  (grosseiro; só precisa de LOS aproximado)
```

Mantém o compute médio abaixo de 16 ms enquanto melhora a precisão exatamente onde
importa (encontros de curta distância).

### 5.2 Particionamento espacial

Substituir o scan linear O(n_rays × n_obstáculos) por um grid uniforme ou quadtree.
Para um mapa 20×20 com 15 obstáculos, isso reduz a checagem de obstáculos por raio de
~15 comparações para ~2-3 em média. Speedup esperado: 3-5×.

### 5.3 Cache de resultados de LOS

Cachear o resultado de visibilidade para cada par (observador, alvo) por até 50 ms
(3 ticks a 60 TPS). Invalidar apenas quando algum dos jogadores se mover mais de uma
célula do grid. Redução esperada de compute: ~60% em condições típicas de partida onde
a maioria dos jogadores está estacionária entre decisões.

### 5.4 Ajuste de parâmetros do dead-reckoning

| Parâmetro | Valor sugerido | Justificativa |
|---|---|---|
| `lerp_factor` | 0,25 por frame | ~100 ms de convergência a 60 fps; lag imperceptível |
| Cap do DR | 250 ms | Além disso o ghost diverge da realidade; melhor esconder |
| Janela estável parcial | 200 ms | Previne jitter quando o servidor arredonda a posição |

### 5.5 Roadmap de deployment

1. **Fase 1 (simulação headless):** validar em simulador de partida com 10 bots e medir frame times.
2. **Fase 2 (shadow mode):** rodar o novo classificador de visibilidade em paralelo com o existente; comparar outputs; medir delta.
3. **Fase 3 (playtest interno):** habilitar para playtests internos da Riot; coletar avaliações subjetivas de pop-in.
4. **Fase 4 (beta opt-in):** publicar atrás de feature flag; medir mudança na taxa de detecção de cheats.

---

## 6. Análise de Segurança

### 6.1 Modelo de ameaça

| Ameaça | Antes | Depois |
|---|---|---|
| Wallhack lê posição exata da memória | Floats exatos em memória | Apenas zona + célula arredondada |
| Aim-assist a partir de zona parcial | N/A | Precisão de ~1 célula de grid; não explorável para mira |
| Reconstrução de posição via velocidade DR | N/A | Usa inteiros de grid; cap de 250 ms |
| Leitura da última posição conhecida | Sempre em memória | Limpa quando zona = none |
| Falsificar escritas no StateMemory pelo cliente | N/A | StateMemory escrito apenas pelo código do servidor |

### 6.2 Risco residual

- Jogadores nas zonas `partial` ou `position_only` ainda têm coordenadas aproximadas de
  grid em memória. Um cheat que as lê pode mostrar "alguém está neste quadrante" —
  equivalente ao mecanismo de ping do minimapa existente, não significativamente pior.
- A precisão de 1 célula de grid corresponde a ~40-100 px dependendo da escala do mapa,
  tornando impossível aim assistance precisa apenas com dados de zona parcial.

---

## 7. Conclusão

O aperfeiçoamento proposto fecha as duas brechas principais no design anti-wallhack do FoW existente:

1. **Sem coordenadas exploráveis** de jogadores fora da visão total na memória do cliente.
2. **Sem teleporte visual** graças aos ghosts de dead-reckoning que extrapolam movimento suave
   apenas a partir de dados já autorizados pelo servidor.

A configuração baseline (n_rays=180) mantém o compute do servidor dentro do budget de 60 TPS
em todas as regiões testadas do Brasil e América Latina. Com as otimizações de densidade adaptativa
de raios e particionamento espacial, o mesmo budget é sustentável globalmente.

Recomendamos prosseguir para a Fase 1 (simulação headless de partida) para validar o throughput
em escala de lobby completo de 10 jogadores.

---

## Apêndices

### A. Inventário de arquivos

| Arquivo | Descrição |
|---|---|
| `src/security/state.py` | StateMemory com rastreamento DR |
| `src/sim/game.py` | Servidor: raycasting, zonas, geração de obstáculos |
| `src/sim/client.py` | Cliente: renderização por zona, lerp, ghost DR |
| `src/sim/players.py` | Movimento com detecção de colisão |
| `src/sim/start.py` | Simulação interativa Tkinter |
| `src/sim/benchmark.py` | Engine de benchmark headless |
| `src/sim/run_benchmark_comparison.py` | Runner de múltiplos cenários |
| `src/benchmark_baseline.*` | Resultados baseline (JSON + CSV) |
| `src/benchmark_high_precision.*` | Resultados alta precisão (JSON + CSV) |
| `src/benchmark_global_baseline.*` | Resultados global baseline (JSON + CSV) |
| `src/benchmark_global_hp.*` | Resultados global 360-raios (JSON + CSV) |

### B. Como reproduzir os resultados

```bash
python src/sim/run_benchmark_comparison.py
```

Todos os artefatos JSON e CSV são escritos em `src/`.

### C. Glossário

| Termo | Definição |
|---|---|
| FoW | Fog of War — mecânica de jogo que esconde informações fora do alcance de visão |
| DR | Dead-reckoning — prever posição futura a partir da última posição conhecida + velocidade |
| LOS | Line of Sight — se um raio do observador ao alvo está desobstruído |
| RTT | Round-Trip Time — latência de rede (ping) |
| TPS | Ticks Por Segundo — taxa de atualização do servidor |
| n_rays | Número de raios lançados por jogador por tick para cálculo de LOS |
