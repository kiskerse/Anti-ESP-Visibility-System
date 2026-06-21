"""
Entry point — 128 TPS com TickClock preciso.

Janelas:
  1. Servidor (omnisciente)
  2. Cliente player_a1 (team A)
  3. ESP protegido  (ClientPacket filtrado)
  4. ESP desprotegido (state bruto)

Teclas:
  WASD  — move player_a1
  R     — toggle IA
  H     — toggle janelas ESP
  Space — smoke no centro do mapa
  T     — mostra stats do TickClock no terminal
"""
from __future__ import annotations

import os, sys, random, tkinter as tk
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from security.pvs   import load_or_build
from security.smoke import SmokeSystem
from security.state import StateMemory
from sim.game       import Game
from sim.client     import Client
from sim.players    import Players
from sim.map_gen    import generate_map, spawn_players
from sim.wallhack_esp import WallhackESP
from sim.tick_clock import TickClock

HUMAN_PID   = "player_a1"
MAP_W       = 60
MAP_H       = 60
CELL_SIZE   = 14
N_OBSTACLES = 45
TARGET_TPS  = 128
CLIENT_FPS  = 60
AI_EVERY    = 2    # move a cada 2 ticks (64 Hz movimento)
CACHE_PATH  = os.path.join(
    os.path.dirname(__file__), "..", "pvs_cache_60x60_s42.pkl.gz"
)


def run() -> None:
    print("[MAP] Gerando mapa 60×60, 45 obstáculos...")
    obstacles, solid = generate_map(MAP_W, MAP_H, N_OBSTACLES, seed=42)
    positions, teams = spawn_players(MAP_W, MAP_H, solid, 5, 5)

    pvs_idx   = load_or_build(MAP_W, MAP_H, obstacles, CACHE_PATH)
    smoke_sys = SmokeSystem()

    print(f"[PVS] {pvs_idx.stats()}")
    print(f"[SERVER] Target: {TARGET_TPS} TPS  Budget: {1000/TARGET_TPS:.4f}ms/tick")

    config = {"map_w": MAP_W, "map_h": MAP_H, "cell_size": CELL_SIZE, "obstacles": obstacles}
    state: dict[str, Any] = {
        "map_w": MAP_W, "map_h": MAP_H,
        "map_width": MAP_W, "map_height": MAP_H,
        "positions": positions, "teams": teams, "obstacles": obstacles,
    }

    memories: dict[str, StateMemory] = {
        pid: StateMemory(rtt_ms=30.0) for pid in positions
    }

    root   = tk.Tk()
    root.title(f"Servidor {TARGET_TPS}TPS  |  WASD=mover  R=IA  H=ESP  Space=smoke  T=stats")

    game   = Game(config, pvs_idx, smoke_sys, create_ui=True)
    player = Players()
    clock  = TickClock(target_tps=TARGET_TPS)

    client = Client(HUMAN_PID, CELL_SIZE, MAP_W, MAP_H, CLIENT_FPS, team="team_a")
    esp_p  = WallhackESP(CELL_SIZE, MAP_W, MAP_H, CLIENT_FPS, False, "team_a")
    esp_r  = WallhackESP(CELL_SIZE, MAP_W, MAP_H, CLIENT_FPS, True,  "team_a")

    ai_ref  = {"active": True}
    esp_ref = {"active": True}
    tick_n  = [0]

    def handle_key(event):
        k = getattr(event, "keysym", None)
        if k == "r":
            ai_ref["active"] = not ai_ref["active"]
            root.title(f"Servidor {TARGET_TPS}TPS | IA={'ON' if ai_ref['active'] else 'OFF'}")
        elif k == "h":
            esp_ref["active"] = not esp_ref["active"]
        elif k == "space":
            smoke_sys.add_smoke(MAP_W//2, MAP_H//2, radius=4.0, duration_ticks=600)
        elif k == "t":
            stats = clock.stats()
            print(f"\n[TickClock] {stats}")
        else:
            player.move_keyboard(event, state, solid, HUMAN_PID)

    root.bind("<KeyPress>", handle_key)

    # intervalo do tick do servidor em ms para after()
    # nota: Tkinter after() tem granularidade de ~1ms; para 128 TPS (7.8ms)
    # isso é aceitável para simulação visual
    server_interval_ms = int(1000 / TARGET_TPS)

    clock.start()

    def tick():
        tick_n[0] += 1
        clock.wait_next_tick()

        if ai_ref["active"] and tick_n[0] % AI_EVERY == 0:
            player.move_all_ai(state, solid, HUMAN_PID)

        game.maybe_spawn_smoke(state, prob=0.002)
        game.tick(state, memories)

        pkt = memories[HUMAN_PID].get_client_packet(HUMAN_PID, CELL_SIZE)
        client.deliver_packet(pkt)

        if esp_ref["active"]:
            esp_p.deliver_packet(pkt)
            visible_legit = {
                pid for pid in pkt.all_enemy_pids() if pkt.level(pid) == "full"
            }
            esp_r.deliver_raw(state, visible_legit)

        clock.end_tick()

        # redesenha servidor a cada 4 ticks (32 Hz visual para poupar CPU)
        if tick_n[0] % 4 == 0:
            game.draw(state)

        root.after(server_interval_ms, tick)

    root.after(200, tick)
    root.mainloop()


if __name__ == "__main__":
    run()
