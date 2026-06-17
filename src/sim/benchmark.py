"""
Benchmark: server-side visibility computation cost under simulated network
latencies for multiple global regions.

Regions are grouped as:
  - Brazil (internal Riot SA servers)
  - Latin America (wider region)
  - North America / Europe / Asia (global comparison)

Each scenario measures:
  - avg_tick_ms  : mean wall-clock time per server tick (visibility + simulated RTT)
  - tps          : effective server ticks per second
  - compute_ms   : pure visibility computation time (excluding simulated ping)
  - p95_tick_ms  : 95th-percentile tick time (tail latency)
  - budget_ok    : True if avg tick fits within a 16.67 ms server budget (60 TPS)
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from sim.game import Game


# ---------------------------------------------------------------------------
# Region ping table (simulated RTT in ms)
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
    "Buenos Aires":  80,
    "Santiago":      85,
    "Lima":          95,
    "Bogotá":       100,
    "Caracas":      110,
    "Montevideo":    82,
}

REGIONS_GLOBAL: dict[str, int] = {
    "Los Angeles":   140,
    "New York":      150,
    "London":        180,
    "Frankfurt":     185,
    "São Paulo":      30,
    "Tokyo":         220,
    "Seoul":         215,
    "Sydney":        260,
    "Singapore":     240,
}

ALL_REGIONS: dict[str, int] = {**REGIONS_BRAZIL, **REGIONS_LATAM, **REGIONS_GLOBAL}


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def simulate_ping_benchmark(
    state: dict[str, Any],
    config: dict[str, Any],
    regions: dict[str, int],
    ticks: int = 200,
) -> dict[str, Any]:
    """Headless benchmark.

    Simulates network RTT by sleeping half-ping before and after each
    server visibility computation, then records timing statistics.
    """
    results: dict[str, Any] = {}
    game = Game(istate={}, config=config, create_ui=False)
    game.draw_random_obstacles()
    state["obstacles"] = game.obstaculos

    server_budget_ms = 1000.0 / 60.0  # 60 TPS budget

    for region, ping_ms in regions.items():
        half_delay = ping_ms / 2000.0  # seconds
        tick_times: list[float] = []
        compute_times: list[float] = []

        for _ in range(ticks):
            t0 = time.perf_counter()

            # simulate inbound network delay
            time.sleep(half_delay)

            # pure server-side computation
            tc0 = time.perf_counter()
            game.compute_lines_of_sight("player1", state["positions"]["player1"])
            game.update_visibility(
                state, "player1", memory=None, fov_deg=90.0, radius=8.0, dir_angle=0.0
            )
            tc1 = time.perf_counter()
            compute_times.append((tc1 - tc0) * 1000.0)

            # simulate outbound network delay
            time.sleep(half_delay)

            t1 = time.perf_counter()
            tick_times.append((t1 - t0) * 1000.0)

        avg_tick = statistics.mean(tick_times)
        p95_tick = sorted(tick_times)[int(len(tick_times) * 0.95)]
        avg_compute = statistics.mean(compute_times)
        tps = 1000.0 / avg_tick if avg_tick > 0 else 0.0

        results[region] = {
            "ping_ms":        ping_ms,
            "avg_tick_ms":    round(avg_tick, 2),
            "p95_tick_ms":    round(p95_tick, 2),
            "compute_ms":     round(avg_compute, 2),
            "tps":            round(tps, 2),
            "budget_ok":      avg_compute <= server_budget_ms,
        }

    return results


# ---------------------------------------------------------------------------
# CLI entry point (quick smoke-test)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    map_w, map_h, cell = 80, 80, 40
    cfg = {
        "largura": map_w * cell,
        "altura":  map_h * cell,
        "tamanho_celula": cell,
        "n_rays": 180,
    }
    state = {
        "map_width":  map_w,
        "map_height": map_h,
        "positions":  {"player1": (10, 40, 0), "enemy1": (60, 40, 0)},
    }
    res = simulate_ping_benchmark(state, cfg, REGIONS_BRAZIL, ticks=50)
    print(f"{'Region':<20} {'Ping':>6} {'Avg tick':>10} {'P95':>10} {'Compute':>10} {'TPS':>7} {'Budget OK':>10}")
    print("-" * 80)
    for region, v in res.items():
        ok = "✓" if v["budget_ok"] else "✗"
        print(
            f"{region:<20} {v['ping_ms']:>5}ms {v['avg_tick_ms']:>9.2f}ms "
            f"{v['p95_tick_ms']:>9.2f}ms {v['compute_ms']:>9.2f}ms "
            f"{v['tps']:>6.2f} {ok:>10}"
        )
