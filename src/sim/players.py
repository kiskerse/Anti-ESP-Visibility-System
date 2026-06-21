from __future__ import annotations

import random
import tkinter as tk


class Players:

    _DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]

    def __init__(self) -> None:
        self._ai_dir:   dict[str, tuple[int, int]] = {}
        self._ai_steps: dict[str, int] = {}

    def _solid_set(self, state: dict) -> frozenset:
        s: set = set()
        for (ox, oy, ow, oh, *_) in state.get("obstacles", []):
            for x in range(ox, ox + ow):
                for y in range(oy, oy + oh):
                    s.add((x, y))
        return frozenset(s)

    def _is_blocked(self, state: dict, solid: frozenset, pid: str, x: int, y: int) -> bool:
        mw = state.get("map_w", state.get("map_width", 60))
        mh = state.get("map_h", state.get("map_height", 60))
        if x < 0 or y < 0 or x >= mw or y >= mh:
            return True
        if (x, y) in solid:
            return True
        for opid, pos in state["positions"].items():
            if opid == pid:
                continue
            px, py, *_ = pos
            if int(px) == x and int(py) == y:
                return True
        return False

    def _try_move(self, state: dict, solid: frozenset, pid: str, dx: int, dy: int) -> bool:
        x, y, *rest = state["positions"][pid]
        z = rest[0] if rest else 0
        nx, ny = int(x) + dx, int(y) + dy
        if not self._is_blocked(state, solid, pid, nx, ny):
            state["positions"][pid] = (nx, ny, z)
            return True
        return False

    def move_keyboard(self, event: tk.Event, state: dict, solid: frozenset,
                      player_id: str = "player_a1") -> None:
        k = getattr(event, "keysym", None)
        m = {"w": (0, -1), "s": (0, 1), "a": (-1, 0), "d": (1, 0)}
        if k in m:
            self._try_move(state, solid, player_id, *m[k])

    def move_ai(self, state: dict, solid: frozenset, pid: str) -> None:
        steps = self._ai_steps.get(pid, 0)
        cur   = self._ai_dir.get(pid, random.choice(self._DIRS))
        if steps <= 0 or not self._try_move(state, solid, pid, *cur):
            dirs = self._DIRS[:]
            random.shuffle(dirs)
            for d in dirs:
                if self._try_move(state, solid, pid, *d):
                    self._ai_dir[pid]   = d
                    self._ai_steps[pid] = random.randint(3, 8)
                    return
            self._ai_dir[pid]   = random.choice(self._DIRS)
            self._ai_steps[pid] = 1
        else:
            self._ai_steps[pid] = steps - 1

    def move_all_ai(self, state: dict, solid: frozenset,
                    human_pid: str = "player_a1") -> None:
        for pid in list(state["positions"]):
            if pid != human_pid:
                self.move_ai(state, solid, pid)
