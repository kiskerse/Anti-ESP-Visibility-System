# Anti-Wallhack FoW — Protótipo de Contenção de Informação

Protótipo que implementa e testa três mecanismos de contenção de informação sobre o sistema de Fog of War server-autoritativo descrito pela Riot para o Valorant.

## Motivação

O artigo da Riot [Demolishing Wallhacks: Valorant's Fog of War](https://www.riotgames.com/en/news/demolishing-wallhacks-valorants-fog-war) descreve o PVS (Potentially Visible Set) como mecanismo base para impedir que o cliente receba posições de inimigos fora do LOS. O que o artigo não detalha é o comportamento no tick exato de entrada no LOS — o ponto onde a posição exata do peek aparece na memória do cliente pela primeira vez.

Além disso, ao analisar vídeos sobre a trapaça Wallhack ESP foi possível visualizar que o FoW funciona apenas mitigava a vantagem em lugares muito distantes e não apresentava eficiência, pois havia uma janela de tempo alta devido ao efeito `pop-in`, a qual comprometia a qualidade da experiência do jogador.

Este protótipo testa se três mecanismos adicionais conseguem reduzir essa janela de informação sem impacto perceptível no gameplay:

1. **Entry Masking** — posição arredondada no tick de entrada no LOS (7.8ms @ 128 TPS)
2. **Adaptive DR Cap** — cap de dead-reckoning proporcional ao RTT do jogador
3. **Hysteresis** — confirmação de 1 tick antes de mudar estado de visibilidade

## O que este projeto não é

Uma solução completa para wallhack. O vetor que este protótipo fecha é leitura direta de memória de processo para posições fora do LOS. Cheats que operam em nível de kernel ou hardware não são afetados.

## Demonstração

![Demo](/docs/demo_antiwallhack.mp4)

Quatro painéis:

1. Servidor (omnisciente)
2. Cliente (filtrado)
3. ESP Protegido (cheat com ClientPacket)
4. ESP Desprotegido (cheat com state bruto).

## Resultados resumidos

| Métrica | Valor |
|---------|-------|
| Compute por tick (Python, 10 players) | 0.18–0.25ms |
| Overhead do budget 128 TPS (7.81ms) | 2.3–3.1% |
| Info delay do entry masking | 15.62ms |
| Redução de ghost DR — São Paulo | 76% (250ms → 60ms) |
| Ticks perdidos | 0 |

Análise completa, gráficos e metodologia: **[REPORT.md](REPORT.md)**

## Como rodar

```bash
pip install psutil numpy matplotlib pillow
python src/sim/start.py                      # simulação visual
python src/sim/run_benchmark_comparison.py   # benchmark headless
python src/sim/render_video.py               # gera o vídeo
```

## Licença

MIT — veja [LICENSE](LICENSE)
