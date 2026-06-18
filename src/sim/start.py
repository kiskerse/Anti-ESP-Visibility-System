from __future__ import annotations

import os, random, sys, tkinter as tk
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from security.state import StateMemory
from sim.client import Client
from sim.game import Game
from sim.players import Players
from sim.wallhack_esp import WallhackESP


def startGame(
    config: dict[str, Any],
    state:  dict[str, Any],
    ai_movement:         bool = True,
    ai_move_every_n_ticks: int = 3,
    show_wallhack_protected:   bool = True,   # ESP lendo ClientPacket (protegido)
    show_wallhack_unprotected: bool = True,   # ESP lendo state bruto (sem proteção)
) -> None:
    root = tk.Tk()
    root.title("Servidor  |  WASD = mover  |  R = toggle IA  |  H = toggle ESP")

    memory = StateMemory()
    game   = Game(istate={}, config=config, create_ui=True)
    game.draw_random_obstacles()
    state["obstacles"] = game.obstaculos
    memory.set_obstacles(game.obstaculos)

    for pid, pos in state["positions"].items():
        game.compute_lines_of_sight(pid, pos)

    player = Players()
    cell   = config.get("tamanho_celula", 50)

    client = Client(
        client_id="player1",
        cell_size=cell,
        map_w=state["map_width"],
        map_h=state["map_height"],
        fps=config.get("client_fps", 60),
    )

    # ESP protegido — lê ClientPacket (o mesmo que o cliente legítimo)
    esp_prot = WallhackESP(cell, state["map_width"], state["map_height"],
                           fps=config.get("client_fps", 60), sem_protecao=False) \
               if show_wallhack_protected else None

    # ESP desprotegido — lê state bruto (jogo sem proteção)
    esp_raw  = WallhackESP(cell, state["map_width"], state["map_height"],
                           fps=config.get("client_fps", 60), sem_protecao=True) \
               if show_wallhack_unprotected else None

    ai_ref  = {"active": ai_movement}
    esp_ref = {"active": True}

    def _handle_key(event):
        k = getattr(event, "keysym", None)
        if k == "r":
            ai_ref["active"] = not ai_ref["active"]
            root.title(f"Servidor | IA {'ON' if ai_ref['active'] else 'OFF'}")
        elif k == "h":
            esp_ref["active"] = not esp_ref["active"]
        else:
            player.move_using_keyboard(event, state, state["map_width"], state["map_height"])

    root.bind("<KeyPress>", lambda e: _handle_key(e))

    server_fps      = config.get("server_fps", 60)
    server_interval = int(max(1, 1000 / server_fps))
    tick_counter    = [0]

    def tick():
        tick_counter[0] += 1

        if ai_ref["active"] and tick_counter[0] % ai_move_every_n_ticks == 0:
            player.move_all_enemies(state)

        try:
            game.tick(state, "player1", memory)
            packet = memory.get_client_packet(cell)

            # cliente legítimo
            client.deliver_packet(packet)

            if esp_ref["active"]:
                # ESP protegido: recebe o mesmo ClientPacket que o cliente legítimo
                if esp_prot:
                    esp_prot.deliver_packet(packet)

                # ESP desprotegido: recebe o state bruto + set de quem o legítimo vê
                if esp_raw:
                    visible_legit = {
                        pid for pid in packet.all_pids()
                        if packet.level(pid) == "full" and pid != "player1"
                    }
                    esp_raw.deliver_raw_state(state, visible_legit)

            game.draw(state)
        except Exception as e:
            print(f"[tick error] {e}")

        root.after(server_interval, tick)

    root.after(200, tick)
    root.mainloop()

if __name__ == "__main__":
    # Mapa maior e mais realista (40×40, mais obstáculos)
    map_w, map_h, cell = 40, 40, 30
    cfg = {
        "largura":        map_w * cell,
        "altura":         map_h * cell,
        "tamanho_celula": cell,
        "n_rays":         360,
        "server_fps":     60,
        "client_fps":     60,
    }

    _game = Game({}, cfg, create_ui=False)
    # força mais obstáculos para mapa realista
    import types as _t
    _orig = _game._generate_obstacle
    _count = [0]
    obstacles: list = []
    while len(obstacles) < 25:
        o = _orig()
        obstacles.append(o)
    _game.obstaculos = obstacles

    def blocked(x: int, y: int) -> bool:
        for obs in obstacles:
            ox, oy, ow, oh, *_ = obs
            if ox <= x <= ox + ow - 1 and oy <= y <= oy + oh - 1:
                return True
        return False

    def free_cell(occupied: set) -> tuple[int, int]:
        for _ in range(5000):
            x = random.randint(0, map_w - 1)
            y = random.randint(0, map_h - 1)
            if (x, y) not in occupied and not blocked(x, y):
                return x, y
        raise RuntimeError("Sem célula livre")

    occupied: set[tuple[int, int]] = set()
    state: dict[str, Any] = {
        "map_width":  map_w,
        "map_height": map_h,
        "positions":  {},
        "obstacles":  obstacles,
    }

    px, py = free_cell(occupied); occupied.add((px, py))
    state["positions"]["player1"] = (px, py, 0)

    for i in range(1, 9):   # 8 inimigos para mapa realista
        ex, ey = free_cell(occupied); occupied.add((ex, ey))
        state["positions"][f"enemy{i}"] = (ex, ey, 0)

    startGame(cfg, state,
              ai_movement=True,
              ai_move_every_n_ticks=3,
              show_wallhack_protected=True,
              show_wallhack_unprotected=True)
