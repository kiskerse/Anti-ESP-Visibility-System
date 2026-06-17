import json
import os
import sys

# ensure src is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sim.benchmark import simulate_ping_benchmark

if __name__ == '__main__':
    map_w = 80
    map_h = 80
    cell = 40
    cfg = {"largura": map_w * cell, "altura": map_h * cell, "tamanho_celula": cell, "n_rays": 180}
    state = {
        "map_width": map_w,
        "map_height": map_h,
        "positions": {"player1": (10, 40, 0), "enemy1": (60, 40, 0)},
    }
    regions = {
        "Sao_Paulo": 30,
        "Rio_de_Janeiro": 40,
        "Brasilia": 55,
        "Manaus": 120,
        "Fortaleza": 110,
        "Porto_Alegre": 70,
    }
    # reduced ticks for quick run
    res = simulate_ping_benchmark(state, cfg, regions, ticks=20)
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'benchmark_results.json'))
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=2)
    print('Benchmark complete. Results written to', out_path)
    for k, v in res.items():
        print(f"{k}: ping={v['ping_ms']}ms avg_tick={v['avg_tick_s']*1000:.2f}ms tps={v['tps']:.2f}")
