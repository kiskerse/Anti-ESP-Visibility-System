"""
Benchmark 128 TPS — PVS + Entry Masking + Adaptive DR + Hysteresis.

Métricas principais:
  compute_ms          : tempo puro do tick do servidor (PVS + state machine)
  achieved_tps        : TPS real alcançado (vs target 128)
  overhead_pct        : compute_ms / 7.8125ms x 100
  jitter_ms           : desvio padrão dos inter-tick intervals
  missed_ticks_pct    : % ticks que excederam budget

Métricas de contenção de informação:
  entry_mask_ticks    : total de ticks em estado "entering" (entry masking ativo)
  entry_mask_pct      : % dos ticks de visibilidade que usaram mascaramento
  info_delay_ms       : atraso médio entre cruzamento de LOS e posição exata em memória
                        = ENTRY_MASK_TICKS x tick_budget_ms + HYSTERESIS_TICKS x tick_budget_ms
  dr_cap_ms           : cap de DR usado para esta região (adaptativo ao ping)
  dr_ghost_reduction  : redução de exposição de ghost vs cap fixo 250ms

Métricas de vantagem wallhack:
  wh_advantage_avg    : média de inimigos extras visíveis via ESP
  wh_advantage_pct    : % ticks com vantagem wallhack > 0
  wh_reduction_pct    : redução vs baseline sem proteção

Fórmula de delay total:
  DelayTotal = (Ping/2) + TickCompensação + JitterCompensação + MargemSegurança
"""

from __future__ import annotations

import copy
import random
import statistics
import time
from typing import Any

import psutil

from security.pvs   import PVSIndex
from security.smoke import SmokeSystem
from security.state import StateMemory, adaptive_dr_cap_ms, ENTRY_MASK_GRID
from sim.game       import Game, ENTRY_MASK_TICKS, HYSTERESIS_TICKS
from sim.map_gen    import generate_map, spawn_players

MARGIN_MS    = 10.0
TARGET_TPS   = 128
TICK_BUDGET  = 1000.0 / TARGET_TPS   # 7.8125 ms

REGIONS_BRAZIL = {
    "São Paulo": 30, "Rio de Janeiro": 40, "Brasília": 55,
    "Belo Horizonte": 48, "Curitiba": 52, "Porto Alegre": 70,
    "Salvador": 90, "Fortaleza": 110, "Recife": 105,
    "Manaus": 120, "Belém": 115,
}
REGIONS_LATAM = {
    "Buenos Aires": 80, "Santiago": 85, "Lima": 95,
    "Bogotá": 100, "Caracas": 110,
}
REGIONS_GLOBAL = {
    "Los Angeles": 140, "New York": 150, "London": 180,
    "Frankfurt": 185, "Tokyo": 220, "Seoul": 215,
    "Sydney": 260, "Singapore": 240,
}
ALL_REGIONS = {**REGIONS_BRAZIL, **REGIONS_LATAM, **REGIONS_GLOBAL}


def _move_all_ai(state: dict, solid: frozenset, human: str = "player_a1") -> None:
    dirs = [(0,-1),(0,1),(-1,0),(1,0)]
    mw, mh = state["map_w"], state["map_h"]
    for pid, pos in list(state["positions"].items()):
        if pid == human:
            continue
        x, y, *rest = pos
        z = rest[0] if rest else 0
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = int(x)+dx, int(y)+dy
            if 0 <= nx < mw and 0 <= ny < mh and (nx, ny) not in solid:
                occupied = {(int(p[0]),int(p[1])) for pp,p in state["positions"].items() if pp!=pid}
                if (nx, ny) not in occupied:
                    state["positions"][pid] = (nx, ny, z)
                    break


def _wh_advantage(state: dict, packet, obs_team: str) -> int:
    legit = {pid for pid in packet.all_enemy_pids() if packet.level(pid) == "full"}
    all_e = {pid for pid in state["positions"] if state["teams"].get(pid) != obs_team}
    return len(all_e - legit)


def run_benchmark(
    pvs_idx:      PVSIndex,
    obstacles:    list,
    solid:        frozenset,
    positions:    dict,
    teams:        dict,
    regions:      dict[str, int] | None = None,
    ticks:        int   = 50,
    move_every:   int   = 3,
    n_smokes:     int   = 3,
    map_w:        int   = 60,
    map_h:        int   = 60,
) -> dict[str, Any]:
    if regions is None:
        regions = REGIONS_BRAZIL

    proc    = psutil.Process()
    results: dict[str, Any] = {}

    for region, ping_ms in regions.items():
        half_s      = ping_ms / 2000.0
        rtt_ms      = float(ping_ms)
        dr_cap      = adaptive_dr_cap_ms(rtt_ms)
        dr_reduction = round((1 - dr_cap / 250.0) * 100, 1)

        smoke_sys = SmokeSystem()
        for _ in range(n_smokes):
            for _ in range(100):
                sx, sy = random.randint(5, map_w-5), random.randint(5, map_h-5)
                if (sx, sy) not in solid:
                    smoke_sys.add_smoke(sx, sy, 3.0, 99999)
                    break

        cfg  = {"map_w": map_w, "map_h": map_h, "cell_size": 1, "obstacles": obstacles}
        game = Game(cfg, pvs_idx, smoke_sys, create_ui=False)
        st   = {
            "map_w": map_w, "map_h": map_h,
            "positions": copy.deepcopy(positions),
            "teams": teams, "obstacles": obstacles,
        }
        mems = {pid: StateMemory(rtt_ms) for pid in positions}

        compute_ms_list:   list[float] = []
        tick_ms_list:      list[float] = []
        inter_ms_list:     list[float] = []
        cpu_list:          list[float] = []
        wh_adv_list:       list[int]   = []
        entry_mask_count   = 0
        full_tick_count    = 0
        last_t             = None

        for ti in range(ticks):
            if ti % move_every == 0:
                _move_all_ai(st, solid)

            # simula RTT: half_s antes do tick (inbound)
            t_wall0 = time.perf_counter()
            time.sleep(half_s)

            proc.cpu_percent(interval=None)
            t_compute0 = time.perf_counter()
            game.tick(st, mems)
            t_compute1 = time.perf_counter()
            cpu_list.append(proc.cpu_percent(interval=None))
            compute_ms_list.append((t_compute1 - t_compute0) * 1000.0)

            # inter-tick
            if last_t is not None:
                inter_ms_list.append((t_compute0 - last_t) * 1000.0)
            last_t = t_compute0

            # métricas de entry masking
            pkt = mems["player_a1"].get_client_packet("player_a1", 1)
            for pid in pkt.all_enemy_pids():
                if pkt.level(pid) == "full":
                    full_tick_count += 1
                    if pkt.is_entering(pid):
                        entry_mask_count += 1

            wh_adv_list.append(_wh_advantage(st, pkt, "team_a"))

            # simula RTT: half_s depois do tick (outbound)
            time.sleep(half_s)
            tick_ms_list.append((time.perf_counter() - t_wall0) * 1000.0)

        avg_c   = statistics.mean(compute_ms_list)
        avg_t   = statistics.mean(tick_ms_list)
        p95_t   = sorted(tick_ms_list)[int(len(tick_ms_list) * 0.95)]
        jitter  = statistics.stdev(inter_ms_list) if len(inter_ms_list) > 1 else 0.0
        missed  = sum(1 for c in compute_ms_list if c > TICK_BUDGET)
        ach_tps = 1000.0 / statistics.mean(inter_ms_list) if inter_ms_list else 0.0
        cpu_avg = statistics.mean(cpu_list) if cpu_list else 0.0

        wh_avg  = statistics.mean(wh_adv_list)
        n_e     = sum(1 for pid in st["positions"] if st["teams"].get(pid) != "team_a")
        wh_red  = (1 - wh_avg / n_e) * 100 if n_e > 0 else 100.0
        wh_pct  = sum(1 for v in wh_adv_list if v > 0) / ticks * 100

        em_pct  = (entry_mask_count / full_tick_count * 100) if full_tick_count > 0 else 0.0

        # delay total com jitter real
        delay_total = ping_ms / 2.0 + TICK_BUDGET + jitter + MARGIN_MS
        # atraso de info = ticks de mascaramento + histerese convertidos para ms
        info_delay  = (ENTRY_MASK_TICKS + HYSTERESIS_TICKS) * TICK_BUDGET

        results[region] = {
            "ping_ms":             ping_ms,
            "compute_ms":          round(avg_c, 4),
            "avg_tick_ms":         round(avg_t, 2),
            "p95_tick_ms":         round(p95_t, 2),
            "achieved_tps":        round(ach_tps, 1),
            "target_tps":          TARGET_TPS,
            "tick_budget_ms":      round(TICK_BUDGET, 4),
            "overhead_pct":        round(avg_c / TICK_BUDGET * 100, 3),
            "missed_ticks":        missed,
            "missed_pct":          round(missed / ticks * 100, 1),
            "jitter_ms":           round(jitter, 3),
            "cpu_pct":             round(cpu_avg, 1),
            "gpu_pct":             0.0,
            "gpu_note":            "Servidor não renderiza — GPU: 0%",
            "dr_cap_ms":           round(dr_cap, 1),
            "dr_ghost_reduction_pct": dr_reduction,
            "entry_mask_ticks":    entry_mask_count,
            "entry_mask_pct":      round(em_pct, 1),
            "info_delay_ms":       round(info_delay, 2),
            "hysteresis_ticks":    HYSTERESIS_TICKS,
            "entry_mask_grid":     ENTRY_MASK_GRID,
            "wh_advantage_avg":    round(wh_avg, 2),
            "wh_advantage_pct":    round(wh_pct, 1),
            "wh_reduction_pct":    round(wh_red, 1),
            "delay_total_ms":      round(delay_total, 2),
            "ping_half_ms":        round(ping_ms / 2.0, 1),
            "tick_comp_ms":        round(TICK_BUDGET, 4),
            "margin_ms":           MARGIN_MS,
        }

    return results
