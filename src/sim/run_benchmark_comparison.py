"""Runner de benchmark — gera JSON, CSV e imprime tabelas de impacto competitivo."""
from __future__ import annotations

import copy, csv, json, os, sys, types

# stub tkinter para ambiente headless
tk_stub = types.ModuleType("tkinter")
class _S:
    def __init__(self,*a,**k): pass
    def __call__(self,*a,**k): return self
    def __getattr__(self,n): return self
for _a in ["Tk","Toplevel","Canvas","Event","Frame","Label","Button"]:
    setattr(tk_stub, _a, _S)
sys.modules.setdefault("tkinter", tk_stub)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sim.benchmark import (
    run_benchmark,
    REGIONS_BRAZIL, REGIONS_LATAM, REGIONS_GLOBAL, ALL_REGIONS,
)

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAP_W, MAP_H, CELL = 20, 20, 50

BASE_STATE = {
    "map_width":  MAP_W,
    "map_height": MAP_H,
    "positions": {
        "player1": (2,  10, 0),
        "enemy1":  (17, 10, 0),
        "enemy2":  (10, 2,  0),
        "enemy3":  (10, 17, 0),
        "enemy4":  (15, 15, 0),
    },
}


def make_cfg(n_rays: int) -> dict:
    return {
        "largura": MAP_W * CELL, "altura": MAP_H * CELL,
        "tamanho_celula": CELL, "n_rays": n_rays,
    }


def save(name: str, cfg: dict, res: dict, ticks: int) -> None:
    with open(f"{OUT}/benchmark_{name}.json", "w", encoding="utf-8") as f:
        json.dump({"scenario": name, "config": cfg, "ticks": ticks, "results": res}, f, indent=2, ensure_ascii=False)
    with open(f"{OUT}/benchmark_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["region","ping_ms","compute_ms","avg_tick_ms","p95_tick_ms",
                    "tps","budget_ok","overhead_pct","popin_events","dr_coverage_pct","dr_gap_ms"])
        for r, d in res.items():
            w.writerow([r, d["ping_ms"], d["compute_ms"], d["avg_tick_ms"], d["p95_tick_ms"],
                        d["tps"], d["budget_ok"], d["overhead_pct"],
                        d["popin_events"], d["dr_coverage_pct"], d["dr_gap_ms"]])


def print_table(name: str, res: dict) -> None:
    print(f"\n{'='*105}")
    print(f"  Scenario: {name}")
    print(f"{'='*105}")
    print(f"  {'Região':<20} {'Ping':>5} {'Compute':>9} {'AvgTick':>9} {'P95':>9} {'TPS':>6} {'Budget':>7} {'Overhead':>9} {'PopIn':>6} {'DR Cov':>7} {'DR Gap':>8}")
    print(f"  {'-'*99}")
    for region, v in res.items():
        ok = "✓" if v["budget_ok"] else "✗"
        print(
            f"  {region:<20} {v['ping_ms']:>4}ms"
            f" {v['compute_ms']:>8.2f}ms"
            f" {v['avg_tick_ms']:>8.2f}ms"
            f" {v['p95_tick_ms']:>8.2f}ms"
            f" {v['tps']:>5.1f}"
            f" {ok:>7}"
            f" {v['overhead_pct']:>8.1f}%"
            f" {v['popin_events']:>6}"
            f" {v['dr_coverage_pct']:>6.1f}%"
            f" {v['dr_gap_ms']:>7.2f}ms"
        )


SCENARIOS = [
    # (nome,           n_rays, regions,        ticks, move_enemies)
    ("baseline_static",   360, REGIONS_BRAZIL, 30,    False),
    ("baseline_ai",       360, REGIONS_BRAZIL, 30,    True),
    ("global_static",     360, ALL_REGIONS,    20,    False),
    ("global_ai",         360, ALL_REGIONS,    20,    True),
    ("hires_ai",          720, REGIONS_BRAZIL, 15,    True),
]

if __name__ == "__main__":
    all_res = {}
    for name, n_rays, regions, ticks, move in SCENARIOS:
        cfg = make_cfg(n_rays)
        print(f"\nRunning [{name}]  n_rays={n_rays}  ticks={ticks}  move_enemies={move}  regions={len(regions)} ...")
        res = run_benchmark(copy.deepcopy(BASE_STATE), cfg, regions, ticks=ticks, move_enemies=move)
        all_res[name] = res
        print_table(name, res)
        save(name, cfg, res, ticks)

    # resumo competitivo
    print(f"\n{'='*105}")
    print("  RESUMO IMPACTO COMPETITIVO — São Paulo (baseline_static vs baseline_ai)")
    print(f"{'='*105}")
    sp_s = all_res["baseline_static"].get("São Paulo", {})
    sp_a = all_res["baseline_ai"].get("São Paulo", {})
    if sp_s and sp_a:
        print(f"  TPS static:        {sp_s['tps']:.1f}")
        print(f"  TPS com IA:        {sp_a['tps']:.1f}")
        print(f"  Pop-in estático:   {sp_s['popin_events']} eventos")
        print(f"  Pop-in com IA:     {sp_a['popin_events']} eventos")
        print(f"  DR coverage (IA):  {sp_a['dr_coverage_pct']:.1f}%")
        print(f"  DR gap (IA):       {sp_a['dr_gap_ms']:.2f}ms de pop-in residual")
    print("\nArquivos salvos em src/")
