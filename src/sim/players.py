from __future__ import annotations

import random
import tkinter as tk
from typing import Any


class Players:
    """Movimento de jogadores — humano (teclado) e IA (aleatório com pathfinding simples)."""

    # direções possíveis: cima, baixo, esquerda, direita
    _DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]

    def _is_blocked(self, state: dict[str, Any], pid: str, x: int, y: int) -> bool:
        if x < 0 or y < 0 or x >= state.get("map_width", 0) or y >= state.get("map_height", 0):
            return True
        for obs in state.get("obstacles", []):
            ox, oy, ow, oh, *_ = obs
            if ox <= x <= ox + ow - 1 and oy <= y <= oy + oh - 1:
                return True
        for other_pid, pos in state.get("positions", {}).items():
            if other_pid == pid:
                continue
            px, py, *_ = pos
            if px == x and py == y:
                return True
        return False

    def _try_move(self, state: dict[str, Any], pid: str, dx: int, dy: int) -> bool:
        x, y, *rest = state["positions"].get(pid, (0, 0, 0))
        z = rest[0] if rest else 0
        nx, ny = x + dx, y + dy
        if not self._is_blocked(state, pid, nx, ny):
            state["positions"][pid] = (nx, ny, z)
            return True
        return False

    # ------------------------------------------------------------------
    # Controle humano
    # ------------------------------------------------------------------

    def move_using_keyboard(
        self,
        event: tk.Event,
        state: dict[str, Any],
        width: int,
        height: int,
        player_id: str = "player1",
    ) -> None:
        k = getattr(event, "keysym", None)
        if k == "w":
            self._try_move(state, player_id, 0, -1)
        elif k == "s":
            self._try_move(state, player_id, 0, 1)
        elif k == "a":
            self._try_move(state, player_id, -1, 0)
        elif k == "d":
            self._try_move(state, player_id, 1, 0)

    # ------------------------------------------------------------------
    # Movimento aleatório de IA (respeita obstáculos)
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        # estado interno de cada IA: direção atual e contador de passos
        self._ai_dir: dict[str, tuple[int, int]] = {}
        self._ai_steps: dict[str, int] = {}

    def move_ai_random(self, state: dict[str, Any], pid: str) -> None:
        """Move um inimigo com IA aleatória estilo "random walk com inércia".

        A IA mantém a direção atual por alguns passos antes de sortear
        uma nova — isso produz movimento mais natural (menos jitter) e
        facilita a observação do pop-in e dead-reckoning.
        """
        steps_left = self._ai_steps.get(pid, 0)
        current_dir = self._ai_dir.get(pid, random.choice(self._DIRS))

        if steps_left <= 0 or not self._try_move(state, pid, *current_dir):
            # escolhe nova direção aleatória (embaralha para não ter viés)
            dirs = self._DIRS[:]
            random.shuffle(dirs)
            moved = False
            for d in dirs:
                if self._try_move(state, pid, *d):
                    self._ai_dir[pid] = d
                    self._ai_steps[pid] = random.randint(2, 6)
                    moved = True
                    break
            if not moved:
                # preso — sorteia direção e aguarda
                self._ai_dir[pid] = random.choice(self._DIRS)
                self._ai_steps[pid] = 1
        else:
            self._ai_steps[pid] = steps_left - 1

    def move_all_enemies(self, state: dict[str, Any]) -> None:
        """Move todos os pids que começam com 'enemy'."""
        for pid in list(state.get("positions", {}).keys()):
            if str(pid).startswith("enemy"):
                self.move_ai_random(state, pid)
