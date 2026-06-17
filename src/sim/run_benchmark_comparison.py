"""
Run all benchmark scenarios and produce JSON + CSV artefacts under src/.

Scenarios
---------
  baseline       : n_rays=180, ticks=300, Brazil regions
  high_precision : n_rays=720, ticks=150, Brazil regions
  global_baseline: n_rays=180, ticks=150, all global regions
  adaptive       : alternates between 180 and 360 rays depending on player proximity

Usage
-----
    python src/sim/run_benchmark_comparison.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from time import perf_counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sim.benchmark import (
    simulate_ping_benchmark,
    REGIONS_BRAZIL,
    REGIONS_LATAM,
    REGIONS_GLOBAL,
    ALL_REGIONS,
)

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAP_W, MAP_H, CELL = 80, 80, 40

BASE_STATE = {
    "map_width":  MAP_W,
    "map_height": MAP_H,
    "positions": {
        "player1": (10, 40, 0),
        "enemy1":  (60, 40, 0),
        "enemy2":  (40, 20, 0),
    },
}


def make_cfg(n_rays: int) -> dict:
    return {
        "largura":        MAP_W * CELL,
        "altura":         MAP_H * CELL,
        "tamanho_celula": CELL,
        "n_rays":         n_rays,
    }


def run_and_save(
    name: str,
    cfg: dict,
    state: dict,
    regions: dict,
    ticks: int,
) -> tuple[dict, str, str]:
    import copy
    t0 = perf_counter()
    res = simulate_ping_benchmark(copy.deepcopy(state), cfg, regions, ticks=ticks)
    elapsed = perf_counter() - t0

    out_json = os.path.join(OUT_DIR, f"benchmark_{name}.json")
    out_csv  = os.path.join(OUT_DIR, f"benchmark_{name}.csv")

    payload = {
        "scenario":  name,
        "config":    cfg,
        "ticks":     ticks,
        "elapsed_s": round(elapsed, 3),
        "results":   res,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "region", "ping_ms", "avg_tick_ms", "p95_tick_ms",
            "compute_ms", "tps", "budget_ok",
        ])
        for region, data in res.items():
            writer.writerow([
                region,
                data["ping_ms"],
                data["avg_tick_ms"],
                data["p95_tick_ms"],
                data["compute_ms"],
                data["tps"],
                data["budget_ok"],
            ])

    return res, out_json, out_csv


def print_table(name: str, res: dict) -> None:
    print(f"\n{'='*90}")
    print(f"  Scenario: {name}")
    print(f"{'='*90}")
    print(f"  {'Region':<22} {'Ping':>6} {'Avg tick':>10} {'P95':>10} {'Compute':>10} {'TPS':>7} {'Budget':>8}")
    print(f"  {'-'*82}")
    for region, v in res.items():
        ok = "✓" if v["budget_ok"] else "✗"
        print(
            f"  {region:<22} {v['ping_ms']:>5}ms"
            f" {v['avg_tick_ms']:>9.2f}ms"
            f" {v['p95_tick_ms']:>9.2f}ms"
            f" {v['compute_ms']:>9.2f}ms"
            f" {v['tps']:>6.2f}"
            f" {ok:>8}"
        )


if __name__ == "__main__":
    scenarios = [
        ("baseline",        make_cfg(180), REGIONS_BRAZIL, 300),
        ("high_precision",  make_cfg(720), REGIONS_BRAZIL, 150),
        ("global_baseline", make_cfg(180), ALL_REGIONS,    150),
        ("global_hp",       make_cfg(360), ALL_REGIONS,    100),
    ]

    all_results = {}
    for name, cfg, regions, ticks in scenarios:
        print(f"\nRunning [{name}]  n_rays={cfg['n_rays']}  ticks={ticks}  regions={len(regions)} ...")
        res, jpath, cpath = run_and_save(name, cfg, BASE_STATE, regions, ticks)
        all_results[name] = res
        print_table(name, res)
        print(f"  → {jpath}")
        print(f"  → {cpath}")

    # cross-scenario comparison for Brazil
    print(f"\n{'='*90}")
    print("  Cross-scenario comparison — Brazil regions  (baseline vs high_precision)")
    print(f"{'='*90}")
    print(f"  {'Region':<22} {'Base avg':>10} {'HP avg':>10} {'Base TPS':>9} {'HP TPS':>9} {'Overhead':>10}")
    print(f"  {'-'*75}")
    for region in REGIONS_BRAZIL:
        if region in all_results["baseline"] and region in all_results["high_precision"]:
            b = all_results["baseline"][region]
            h = all_results["high_precision"][region]
            overhead = ((h["compute_ms"] - b["compute_ms"]) / max(b["compute_ms"], 0.001)) * 100
            print(
                f"  {region:<22}"
                f" {b['avg_tick_ms']:>9.2f}ms"
                f" {h['avg_tick_ms']:>9.2f}ms"
                f" {b['tps']:>8.2f}"
                f" {h['tps']:>8.2f}"
                f" {overhead:>+9.1f}%"
            )

    print("\nAll benchmark files written to src/")
