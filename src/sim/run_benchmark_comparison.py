"""
Runner completo — 128 TPS, entry masking, adaptive DR, regiões globais.
"""
from __future__ import annotations

import copy, csv, json, os, sys, types

tk_stub = types.ModuleType("tkinter")
class _S:
    def __init__(self,*a,**k): pass
    def __call__(self,*a,**k): return self
    def __getattr__(self,n): return self
for _a in ["Tk","Toplevel","Canvas","Event","Frame"]:
    setattr(tk_stub, _a, _S)
sys.modules.setdefault("tkinter", tk_stub)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from security.pvs  import load_or_build
from sim.benchmark import run_benchmark, REGIONS_BRAZIL, REGIONS_LATAM, REGIONS_GLOBAL, ALL_REGIONS, TARGET_TPS, TICK_BUDGET
from sim.map_gen   import generate_map, spawn_players

OUT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAP_W   = 60
MAP_H   = 60
N_OBS   = 45
SEED    = 42
CACHE   = os.path.join(OUT, "pvs_cache_60x60_s42.pkl.gz")


def save(name: str, res: dict, ticks: int) -> None:
    cols = [
        "region","ping_ms","compute_ms","achieved_tps","target_tps",
        "tick_budget_ms","overhead_pct","missed_ticks","missed_pct",
        "jitter_ms","cpu_pct","gpu_pct",
        "dr_cap_ms","dr_ghost_reduction_pct",
        "entry_mask_ticks","entry_mask_pct","info_delay_ms",
        "wh_advantage_avg","wh_advantage_pct","wh_reduction_pct",
        "delay_total_ms","ping_half_ms","tick_comp_ms","margin_ms",
    ]
    with open(f"{OUT}/benchmark_{name}.json", "w", encoding="utf-8") as f:
        json.dump({"scenario": name, "ticks": ticks, "target_tps": TARGET_TPS,
                   "tick_budget_ms": TICK_BUDGET, "results": res}, f, indent=2, ensure_ascii=False)
    with open(f"{OUT}/benchmark_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for region, d in res.items():
            w.writerow({"region": region, **d})


def print_table(name: str, res: dict) -> None:
    print(f"\n{'='*115}")
    print(f"  Cenário: {name}  (target={TARGET_TPS} TPS, budget={TICK_BUDGET:.4f}ms)")
    print(f"{'='*115}")
    hdr = (f"  {'Região':<20} {'Ping':>5} {'Compute':>9} {'Ovhd':>6} "
           f"{'Miss%':>6} {'DR cap':>7} {'DR-Red':>7} "
           f"{'InfoDly':>8} {'WH Red':>7} {'DelayTot':>10}")
    print(hdr)
    print(f"  {'-'*109}")
    for region, v in res.items():
        ok = "✓" if v["missed_pct"] == 0 else f"✗{v['missed_pct']:.0f}%"
        print(
            f"  {region:<20} {v['ping_ms']:>4}ms"
            f" {v['compute_ms']:>8.4f}ms"
            f" {v['overhead_pct']:>5.2f}%"
            f" {ok:>6}"
            f" {v['dr_cap_ms']:>6.0f}ms"
            f" {v['dr_ghost_reduction_pct']:>6.0f}%"
            f" {v['info_delay_ms']:>7.2f}ms"
            f" {v['wh_reduction_pct']:>6.0f}%"
            f" {v['delay_total_ms']:>9.2f}ms"
        )


SCENARIOS = [
    ("brasil_128tps",  REGIONS_BRAZIL, 25),
    ("latam_128tps",   REGIONS_LATAM,  20),
    ("global_128tps",  ALL_REGIONS,    15),
]

if __name__ == "__main__":
    print("[MAP] Gerando mapa 60×60...")
    obstacles, solid = generate_map(MAP_W, MAP_H, N_OBS, seed=SEED)
    positions, teams = spawn_players(MAP_W, MAP_H, solid, 5, 5)

    pvs_idx = load_or_build(MAP_W, MAP_H, obstacles, CACHE)
    print(f"[PVS] Stats: {pvs_idx.stats()}")

    all_results: dict[str, dict] = {}
    for name, regions, ticks in SCENARIOS:
        print(f"\nRunning [{name}]  ticks={ticks}  regiões={len(regions)} ...")
        res = run_benchmark(pvs_idx, obstacles, solid, positions, teams,
                            regions=regions, ticks=ticks, map_w=MAP_W, map_h=MAP_H)
        all_results[name] = res
        print_table(name, res)
        save(name, res, ticks)

    # resumo executivo
    print(f"\n{'='*115}")
    print(f"  RESUMO EXECUTIVO — Contenção de Informação @ {TARGET_TPS} TPS")
    print(f"{'='*115}")
    print(f"  {'Métrica':<40} {'SP (30ms)':>12} {'Manaus (120ms)':>15} {'Sydney (260ms)':>15}")
    print(f"  {'-'*85}")
    for label, city in [("Compute por tick", "São Paulo"),
                         ("Overhead do budget", "São Paulo"),
                         ("DR cap adaptativo", "São Paulo"),
                         ("Redução de ghost DR vs 250ms", "São Paulo"),
                         ("Info delay (entry masking)", "São Paulo"),
                         ("Delay total", "São Paulo")]:
        row_br = all_results["brasil_128tps"].get("São Paulo", {})
        row_ma = all_results["brasil_128tps"].get("Manaus", {})
        row_sy = all_results["global_128tps"].get("Sydney", {})
        key_map = {
            "Compute por tick": "compute_ms",
            "Overhead do budget": "overhead_pct",
            "DR cap adaptativo": "dr_cap_ms",
            "Redução de ghost DR vs 250ms": "dr_ghost_reduction_pct",
            "Info delay (entry masking)": "info_delay_ms",
            "Delay total": "delay_total_ms",
        }
        k = key_map[label]
        unit = "%" if "pct" in k or "overhead" in k or "reduction" in k else "ms"
        v1 = row_br.get(k, "?")
        v2 = row_ma.get(k, "?")
        v3 = row_sy.get(k, "?")
        print(f"  {label:<40} {str(v1)+unit:>12} {str(v2)+unit:>15} {str(v3)+unit:>15}")

    with open(f"{OUT}/benchmark_all_128tps.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n  Arquivos salvos em src/")
