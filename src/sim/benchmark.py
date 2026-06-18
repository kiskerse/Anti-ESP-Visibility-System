"""
Benchmark de impacto competitivo — Anti-Wallhack com DR.

Fórmula de delay total (por tick):
  DelayTotal = (Ping / 2) + TickCompensação + JitterCompensação + MargemSegurança

  onde:
    Ping / 2             = metade do RTT (one-way delay ao servidor)
    TickCompensação      = 1000 / server_fps  (janela de um tick)
    JitterCompensação    = std_dev dos inter-tick intervals (últimos 8 ticks)
    MargemSegurança      = 10ms fixo (buffer conservador)

Métricas de CPU/GPU:
  cpu_pct   : % CPU do processo durante o tick (via psutil)
  cpu_total : % CPU total da máquina
  gpu_util  : % GPU estimada (Tkinter/Canvas não usa GPU; valor é 0 para
              renderização em software — anotado como tal no relatório)

Métricas de vantagem do wallhack:
  wh_advantage_avg    : média de inimigos extras que o cheat veria
  wh_advantage_pct    : % de ticks onde o cheat teria alguma vantagem
  wh_reduction_pct    : redução percentual de vantagem vs baseline sem proteção
"""

from __future__ import annotations

import random
import statistics
import time
from typing import Any

import psutil

from sim.game import Game
from security.state import StateMemory


# ---------------------------------------------------------------------------
# Regiões
# ---------------------------------------------------------------------------

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
    "Buenos Aires": 80, "Santiago": 85, "Lima": 95, "Bogotá": 100, "Caracas": 110,
}
REGIONS_GLOBAL: dict[str, int] = {
    "Los Angeles": 140, "New York": 150, "London": 180,
    "Frankfurt": 185, "Tokyo": 220, "Seoul": 215, "Sydney": 260, "Singapore": 240,
}
ALL_REGIONS = {**REGIONS_BRAZIL, **REGIONS_LATAM, **REGIONS_GLOBAL}

MARGIN_SAFETY_MS = 10.0   # MargemSegurança fixa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jitter_compensation(inter_tick_ms: list[float]) -> float:
    """Desvio padrão dos inter-tick intervals — estimativa de jitter."""
    if len(inter_tick_ms) < 2:
        return 0.0
    return statistics.stdev(inter_tick_ms)


def _tick_compensation(server_fps: int) -> float:
    return 1000.0 / server_fps


def total_delay(
    ping_ms: float,
    inter_tick_ms: list[float],
    server_fps: int,
) -> dict[str, float]:
    tick_comp   = _tick_compensation(server_fps)
    jitter_comp = _jitter_compensation(inter_tick_ms)
    dt = ping_ms / 2.0 + tick_comp + jitter_comp + MARGIN_SAFETY_MS
    return {
        "ping_half_ms":    round(ping_ms / 2.0, 2),
        "tick_comp_ms":    round(tick_comp, 2),
        "jitter_comp_ms":  round(jitter_comp, 2),
        "margin_ms":       MARGIN_SAFETY_MS,
        "delay_total_ms":  round(dt, 2),
    }


def _move_enemies(state: dict, obstacles: list, map_w: int, map_h: int) -> None:
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
            blocked = any(
                ox <= nx <= ox + ow - 1 and oy <= ny <= oy + oh - 1
                for (ox, oy, ow, oh, *_) in obstacles
            )
            if not blocked:
                state["positions"][pid] = (nx, ny, z)
                break


def _count_wallhack_advantage(state: dict, packet) -> int:
    """Conta quantos inimigos um wallhack desprotegido veria além do legítimo."""
    legit_visible = {
        pid for pid in packet.all_pids()
        if packet.level(pid) == "full" and pid != "player1"
    }
    all_enemies = {pid for pid in state["positions"] if str(pid).startswith("enemy")}
    return len(all_enemies - legit_visible)


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_benchmark(
    state: dict[str, Any],
    config: dict[str, Any],
    regions: dict[str, int],
    ticks:        int  = 100,
    move_enemies: bool = True,
    move_every:   int  = 3,
    server_fps:   int  = 60,
    n_obstacles:  int  = 25,
) -> dict[str, Any]:
    import copy

    game = Game({}, config, create_ui=False)
    # força mapa realista com n_obstacles
    while len(game.obstaculos) < n_obstacles:
        game.obstaculos.append(game._generate_obstacle())
    game.obstacles_version += 1

    st = copy.deepcopy(state)
    st["obstacles"] = game.obstaculos
    memory = StateMemory()
    memory.set_obstacles(game.obstaculos)
    map_w, map_h = st["map_width"], st["map_height"]
    budget_ms    = 1000.0 / server_fps

    for pid, pos in st["positions"].items():
        game.compute_lines_of_sight(pid, pos)

    proc = psutil.Process()
    results: dict[str, Any] = {}

    for region, ping_ms in regions.items():
        half_delay     = ping_ms / 2000.0
        compute_times: list[float] = []
        tick_times:    list[float] = []
        cpu_pct_list:  list[float] = []
        inter_tick_ms: list[float] = []

        prev_levels:    dict[str, str] = {}
        popin_events    = 0
        dr_covered      = 0
        dr_gap_ms_list: list[float] = []

        wh_advantage_list: list[int] = []

        local_st = copy.deepcopy(st)
        last_tick_t = None

        for tick_i in range(ticks):
            if move_enemies and tick_i % move_every == 0:
                _move_enemies(local_st, game.obstaculos, map_w, map_h)

            t0 = time.perf_counter()
            time.sleep(half_delay)

            # CPU antes do tick
            proc.cpu_percent(interval=None)

            tc0 = time.perf_counter()
            game.tick(local_st, "player1", memory)
            tc1 = time.perf_counter()

            cpu_this = proc.cpu_percent(interval=None)
            compute_times.append((tc1 - tc0) * 1000.0)
            cpu_pct_list.append(cpu_this)

            # inter-tick jitter
            if last_tick_t is not None:
                inter_tick_ms.append((tc0 - last_tick_t) * 1000.0)
            last_tick_t = tc0

            # pop-in e wallhack
            packet = memory.get_client_packet(config.get("tamanho_celula", 50))
            for pid in packet.all_pids():
                if pid == "player1":
                    continue
                cur  = packet.level(pid)
                prev = prev_levels.get(pid, cur)
                if prev == "none" and cur == "full":
                    popin_events += 1
                    if packet.get(pid).get("predicted_px") is not None:
                        dr_covered += 1
                    else:
                        dr_gap_ms_list.append((tc1 - tc0) * 1000.0)
                prev_levels[pid] = cur

            wh_advantage_list.append(_count_wallhack_advantage(local_st, packet))

            time.sleep(half_delay)
            t1 = time.perf_counter()
            tick_times.append((t1 - t0) * 1000.0)

        avg_compute  = statistics.mean(compute_times)
        avg_tick     = statistics.mean(tick_times)
        p95_tick     = sorted(tick_times)[int(len(tick_times) * 0.95)]
        tps          = 1000.0 / avg_tick if avg_tick > 0 else 0.0
        avg_cpu      = statistics.mean(cpu_pct_list) if cpu_pct_list else 0.0

        dr_cov_pct   = (dr_covered / popin_events * 100) if popin_events > 0 else 100.0
        dr_gap_avg   = statistics.mean(dr_gap_ms_list) if dr_gap_ms_list else 0.0

        wh_avg       = statistics.mean(wh_advantage_list)
        wh_pct       = sum(1 for v in wh_advantage_list if v > 0) / ticks * 100
        # % de redução vs baseline (sem proteção todos os inimigos seriam visíveis)
        n_enemies    = sum(1 for pid in local_st["positions"] if str(pid).startswith("enemy"))
        wh_reduction = (1 - wh_avg / n_enemies) * 100 if n_enemies > 0 else 100.0

        delay_info   = total_delay(ping_ms, inter_tick_ms, server_fps)

        results[region] = {
            "ping_ms":           ping_ms,
            "compute_ms":        round(avg_compute, 3),
            "avg_tick_ms":       round(avg_tick, 2),
            "p95_tick_ms":       round(p95_tick, 2),
            "tps":               round(tps, 2),
            "budget_ms":         round(budget_ms, 2),
            "budget_ok":         avg_compute <= budget_ms,
            "overhead_pct":      round(avg_compute / budget_ms * 100, 2),
            "cpu_pct":           round(avg_cpu, 1),
            "gpu_util":          0.0,   # Tkinter/Canvas = renderização CPU; GPU não utilizada
            "gpu_note":          "Canvas 2D via CPU — GPU não utilizada neste protótipo",
            "popin_events":      popin_events,
            "dr_coverage_pct":   round(dr_cov_pct, 1),
            "dr_gap_ms":         round(dr_gap_avg, 2),
            "wh_advantage_avg":  round(wh_avg, 2),
            "wh_advantage_pct":  round(wh_pct, 1),
            "wh_reduction_pct":  round(wh_reduction, 1),
            "delay_total_ms":    delay_info["delay_total_ms"],
            "ping_half_ms":      delay_info["ping_half_ms"],
            "tick_comp_ms":      delay_info["tick_comp_ms"],
            "jitter_comp_ms":    delay_info["jitter_comp_ms"],
            "margin_ms":         delay_info["margin_ms"],
        }

    return results
