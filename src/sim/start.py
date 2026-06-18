from __future__ import annotations

import os
import random
import sys
import tkinter as tk
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from security.state import StateMemory
from sim.client import Client
from sim.game import Game
from sim.players import Players


def startGame(
    config: dict[str, Any],
    state: dict[str, Any],
    ai_movement: bool = True,          # ← liga/desliga movimento aleatório dos inimigos
    ai_move_every_n_ticks: int = 3,    # move inimigos a cada N ticks do servidor (velocidade da IA)
) -> None:
    root = tk.Tk()
    root.title("Server Controller (WASD para mover | 'r' liga/desliga IA)")

    memory = StateMemory()
    game = Game(istate={}, config=config, create_ui=True)
    game.draw_random_obstacles()
    state["obstacles"] = game.obstaculos
    memory.set_obstacles(game.obstaculos)

    for pid, pos in state["positions"].items():
        game.compute_lines_of_sight(pid, pos)

    player = Players()

    client = Client(
        client_id="player1",
        cell_size=config.get("tamanho_celula", 50),
        map_w=state["map_width"],
        map_h=state["map_height"],
        fps=config.get("client_fps", 60),
    )

    root.bind(
        "<KeyPress>",
        lambda e: _handle_key(e, player, state, ai_movement_ref),
    )

    # referência mutável para toggle em runtime
    ai_movement_ref = {"active": ai_movement}

    def _handle_key(event, pl, st, ai_ref):
        k = getattr(event, "keysym", None)
        if k == "r":
            ai_ref["active"] = not ai_ref["active"]
            status = "ON" if ai_ref["active"] else "OFF"
            root.title(f"Server Controller — IA {status}")
        else:
            pl.move_using_keyboard(event, st, st["map_width"], st["map_height"])

    root.bind("<KeyPress>", lambda e: _handle_key(e, player, state, ai_movement_ref))

    game.draw(state)

    server_fps = config.get("server_fps", 60)
    server_interval = int(max(1, 1000 / server_fps))
    tick_counter = [0]

    def tick():
        tick_counter[0] += 1

        # move inimigos com IA a cada N ticks
        if ai_movement_ref["active"] and tick_counter[0] % ai_move_every_n_ticks == 0:
            player.move_all_enemies(state)

        # servidor calcula visibilidade → StateMemory → ClientPacket → cliente
        try:
            game.tick(state, "player1", memory)
            packet = memory.get_client_packet(config.get("tamanho_celula", 50))
            client.deliver_packet(packet)
            game.draw(state)
        except Exception as e:
            print(f"[tick error] {e}")

        root.after(server_interval, tick)

    root.after(200, tick)
    root.mainloop()


if __name__ == "__main__":
    map_w, map_h, cell = 20, 20, 50
    cfg = {
        "largura":        map_w * cell,
        "altura":         map_h * cell,
        "tamanho_celula": cell,
        "n_rays":         360,
        "server_fps":     60,
        "client_fps":     60,
    }

    _game = Game({}, cfg, create_ui=False)
    _game.draw_random_obstacles()
    obstacles = _game.obstaculos

    def blocked(x: int, y: int) -> bool:
        for obs in obstacles:
            ox, oy, ow, oh, *_ = obs
            if ox <= x <= ox + ow - 1 and oy <= y <= oy + oh - 1:
                return True
        return False

    def free_cell(occupied: set) -> tuple[int, int]:
        for _ in range(2000):
            x, y = random.randint(0, map_w - 1), random.randint(0, map_h - 1)
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

    for i in range(1, 5):
        ex, ey = free_cell(occupied); occupied.add((ex, ey))
        state["positions"][f"enemy{i}"] = (ex, ey, 0)

    # Iniciar com IA ligada — pressione 'r' para alternar
    startGame(cfg, state, ai_movement=True, ai_move_every_n_ticks=4)
