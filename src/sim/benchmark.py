"""
Benchmark de impacto competitivo do sistema Anti-Wallhack.

Mede três dimensões:
  1. Custo de compute (raycasting) por tick
  2. Impacto de latência por região (simula RTT real)
  3. Qualidade anti pop-in: frequência de transições none→full (pop-in events)
     e tempo médio em que o DR cobre a transição (DR coverage)

Métricas relevantes para gameplay competitivo:
  - tick_budget_ms   : budget do servidor (1000/server_fps)
  - compute_ms       : tempo puro de raycasting + classificação
  - overhead_%       : compute/budget × 100
  - effective_tps    : ticks/s considerando ping
  - popin_rate       : transições none→full por tick (0 = perfeito)
  - dr_coverage_%    : % das transições cobertas pelo DR (ghost visível)
  - dr_gap_ms        : tempo médio de gap sem cobertura (pop-in real)
"""

from __future__ import annotations

import math
import random
import statistics
import time
from typing import Any

from sim.game import Game
from security.state import StateMemory


REGIONS_BRAZIL: dict[str, int] = {
    "São Paulo":      30,
    "Rio de Janeiro": 40,
    "Brasília":       55,
    "Belo Horizonte": 48,
    "Curitiba":       52,
    "Porto Alegre":   70,
    "Salvador":       90,
    "Fortaleza":     110,
    "Recife":        105,
    "Manaus":        120,
    "Belém":         115,
}

REGIONS_LATAM: dict[str, int] = {
    "Buenos Aires":  80,
    "Santiago":      85,
    "Lima":          95,
    "Bogotá":       100,
    "Caracas":      110,
}

REGIONS_GLOBAL: dict[str, int] = {
    "Los Angeles":  140,
    "New York":     150,
    "London":       180,
    "Frankfurt":    185,
    "Tokyo":        220,
    "Seoul":        215,
    "Sydney":       260,
    "Singapore":    240,
}

ALL_REGIONS = {**REGIONS_BRAZIL, **REGIONS_LATAM, **REGIONS_GLOBAL}


def _move_enemies_random(state: dict, obstacles: list, map_w: int, map_h: int) -> None:
    """Move inimigos aleatoriamente respeitando obstáculos (versão headless)."""
    dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    for pid, pos in list(state["positions"].items()):
        if not str(pid).startswith("enemy"):
            continue
        x, y, *rest = pos
        z = rest[0] if rest else 0
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= map_w or ny >= map_h:
                continue
            blocked = False
            for obs in obstacles:
                ox, oy, ow, oh, *_ = obs
                if ox <= nx <= ox + ow - 1 and oy <= ny <= oy + oh - 1:
                    blocked = True
                    break
            if not blocked:
                state["positions"][pid] = (nx, ny, z)
                break


def run_benchmark(
    state: dict[str, Any],
    config: dict[str, Any],
    regions: dict[str, int],
    ticks: int = 100,
    move_enemies: bool = True,
    move_every: int = 3,
    server_fps: int = 60,
) -> dict[str, Any]:
    """Roda benchmark headless e retorna métricas por região."""

    import copy
    game = Game({}, config, create_ui=False)
    game.draw_random_obstacles()
    st = copy.deepcopy(state)
    st["obstacles"] = game.obstaculos
    memory = StateMemory()
    memory.set_obstacles(game.obstaculos)

    map_w = st["map_width"]
    map_h = st["map_height"]
    budget_ms = 1000.0 / server_fps
    results: dict[str, Any] = {}

    # pré-aquece raios
    for pid, pos in st["positions"].items():
        game.compute_lines_of_sight(pid, pos)

    for region, ping_ms in regions.items():
        half_delay = ping_ms / 2000.0
        compute_times: list[float] = []
        tick_times: list[float] = []

        # métricas de pop-in
        prev_levels: dict[str, str] = {}
        popin_events = 0       # transições none → full
        dr_covered   = 0       # dessas, quantas tinham DR ativo
        dr_gap_ms_list: list[float] = []

        local_st = copy.deepcopy(st)

        for tick_i in range(ticks):
            if move_enemies and tick_i % move_every == 0:
                _move_enemies_random(local_st, game.obstaculos, map_w, map_h)

            t0 = time.perf_counter()
            time.sleep(half_delay)

            tc0 = time.perf_counter()
            game.tick(local_st, "player1", memory)
            tc1 = time.perf_counter()
            compute_times.append((tc1 - tc0) * 1000.0)

            # analisa pop-in
            packet = memory.get_client_packet(config.get("tamanho_celula", 50))
            for pid in packet.all_pids():
                if pid == "player1":
                    continue
                cur_level  = packet.level(pid)
                prev_level = prev_levels.get(pid, cur_level)
                if prev_level == "none" and cur_level == "full":
                    popin_events += 1
                    dr_px = packet.get(pid).get("predicted_px")
                    if dr_px is not None:
                        dr_covered += 1
                    else:
                        # gap real: tick_ms sem cobertura DR
                        dr_gap_ms_list.append((tc1 - tc0) * 1000.0)
                prev_levels[pid] = cur_level

            time.sleep(half_delay)
            t1 = time.perf_counter()
            tick_times.append((t1 - t0) * 1000.0)

        avg_compute = statistics.mean(compute_times)
        avg_tick    = statistics.mean(tick_times)
        p95_tick    = sorted(tick_times)[int(len(tick_times) * 0.95)]
        tps         = 1000.0 / avg_tick if avg_tick > 0 else 0.0

        dr_cov_pct  = (dr_covered / popin_events * 100) if popin_events > 0 else 100.0
        dr_gap_avg  = statistics.mean(dr_gap_ms_list) if dr_gap_ms_list else 0.0

        results[region] = {
            "ping_ms":       ping_ms,
            "compute_ms":    round(avg_compute, 2),
            "avg_tick_ms":   round(avg_tick, 2),
            "p95_tick_ms":   round(p95_tick, 2),
            "tps":           round(tps, 2),
            "budget_ms":     round(budget_ms, 2),
            "budget_ok":     avg_compute <= budget_ms,
            "overhead_pct":  round(avg_compute / budget_ms * 100, 1),
            "popin_events":  popin_events,
            "dr_coverage_pct": round(dr_cov_pct, 1),
            "dr_gap_ms":     round(dr_gap_avg, 2),
        }

    return results
