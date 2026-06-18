"""Runner completo — gera JSON, CSV e tabelas de impacto competitivo."""
from __future__ import annotations

import copy, csv, json, os, sys, types

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

OUT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAP_W   = 40
MAP_H   = 40
CELL    = 30
N_ENEMIES = 8

BASE_STATE = {
    "map_width":  MAP_W,
    "map_height": MAP_H,
    "positions": {
        "player1": (2,  20, 0),
        **{f"enemy{i}": (MAP_W - 3 - (i % 5) * 6, 5 + i * 4, 0) for i in range(1, N_ENEMIES + 1)},
    },
}

def cfg(n_rays: int) -> dict:
    return {"largura": MAP_W*CELL, "altura": MAP_H*CELL,
            "tamanho_celula": CELL, "n_rays": n_rays}


def save(name: str, c: dict, res: dict, ticks: int) -> None:
    with open(f"{OUT}/benchmark_{name}.json", "w", encoding="utf-8") as f:
        json.dump({"scenario": name, "config": c, "ticks": ticks, "results": res}, f, indent=2, ensure_ascii=False)
    cols = ["region","ping_ms","compute_ms","avg_tick_ms","p95_tick_ms","tps",
            "budget_ok","overhead_pct","cpu_pct","gpu_util",
            "popin_events","dr_coverage_pct","dr_gap_ms",
            "wh_advantage_avg","wh_advantage_pct","wh_reduction_pct",
            "delay_total_ms","ping_half_ms","tick_comp_ms","jitter_comp_ms","margin_ms"]
    with open(f"{OUT}/benchmark_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r, d in res.items():
            w.writerow({"region": r, **d})


def print_table(name: str, res: dict) -> None:
    print(f"\n{'='*120}")
    print(f"  Cenário: {name}")
    print(f"{'='*120}")
    hdr = f"  {'Região':<20} {'Ping':>5} {'Compute':>9} {'CPU%':>5} {'GPU%':>5} {'TPS':>6} {'Budget':>7} {'WH Adv':>7} {'WH Red%':>8} {'DR Cov':>7} {'DelayTotal':>11}"
    print(hdr)
    print(f"  {'-'*114}")
    for region, v in res.items():
        ok = "✓" if v["budget_ok"] else "✗"
        print(
            f"  {region:<20} {v['ping_ms']:>4}ms"
            f" {v['compute_ms']:>8.3f}ms"
            f" {v['cpu_pct']:>4.1f}%"
            f" {v['gpu_util']:>4.1f}%"
            f" {v['tps']:>5.1f}"
            f" {ok:>7}"
            f" {v['wh_advantage_avg']:>6.2f}"
            f" {v['wh_reduction_pct']:>7.1f}%"
            f" {v['dr_coverage_pct']:>6.1f}%"
            f" {v['delay_total_ms']:>10.2f}ms"
        )


SCENARIOS = [
    ("realista_brasil",  360, REGIONS_BRAZIL, 20, True,  25),
    ("realista_global",  360, ALL_REGIONS,    15, True,  25),
    ("hires_brasil",     720, REGIONS_BRAZIL, 15, True,  25),
    ("denso_brasil",     360, REGIONS_BRAZIL, 15, True,  40),   # 40 obstáculos
]

if __name__ == "__main__":
    all_res: dict[str, dict] = {}

    for name, n_rays, regions, ticks, move, n_obs in SCENARIOS:
        c = cfg(n_rays)
        print(f"\nRunning [{name}]  n_rays={n_rays}  obstacles={n_obs}  ticks={ticks}  regiões={len(regions)} ...")
        res = run_benchmark(copy.deepcopy(BASE_STATE), c, regions,
                            ticks=ticks, move_enemies=move, n_obstacles=n_obs)
        all_res[name] = res
        print_table(name, res)
        save(name, c, res, ticks)

    # resumo de vantagem wallhack
    print(f"\n{'='*120}")
    print("  RESUMO: Vantagem do Wallhack — São Paulo (com proteção ativa)")
    print(f"{'='*120}")
    for name in SCENARIOS:
        nm = name[0]
        sp = all_res[nm].get("São Paulo", {})
        if sp:
            print(f"  [{nm:<22}] WH vantagem média: {sp['wh_advantage_avg']:.2f} inimigos "
                  f"| Redução: {sp['wh_reduction_pct']:.1f}% "
                  f"| Delay total: {sp['delay_total_ms']:.1f}ms "
                  f"| Jitter comp: {sp['jitter_comp_ms']:.2f}ms")

    with open(f"{OUT}/benchmark_all.json", "w", encoding="utf-8") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False)
    print("\nTodos os arquivos salvos em src/")
