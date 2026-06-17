from typing import Any
import tkinter as tk


class Players:
    """Move a single active player while preventing collisions with obstacles
    and other players. Methods take a `player_id` so only that player moves.
    """

    def _is_blocked(self, state: dict[str, Any], player_id: str, x: int, y: int) -> bool:
        # check map bounds
        if x < 0 or y < 0 or x >= state.get("map_width", 0) or y >= state.get("map_height", 0):
            return True
        # check obstacles (stored as grid cells: ox, oy, ow, oh, ...)
        for obs in state.get("obstacles", []):
            ox, oy, ow, oh, *_ = obs
            if ox <= x <= ox + ow - 1 and oy <= y <= oy + oh - 1:
                return True
        # check other players occupancy
        for pid, pos in state.get("positions", {}).items():
            if pid == player_id:
                continue
            px, py, _ = pos
            if px == x and py == y:
                return True
        return False

    def move_up(self, state: dict[str, Any], player_id: str) -> None:
        x, y, z = state['positions'].get(player_id, (0, 0, 0))
        new_y = max(0, y - 1)
        if not self._is_blocked(state, player_id, x, new_y):
            state['positions'][player_id] = (x, new_y, z)

    def move_down(self, state: dict[str, Any], player_id: str) -> None:
        x, y, z = state['positions'].get(player_id, (0, 0, 0))
        new_y = min(state.get('map_height', 0) - 1, y + 1)
        if not self._is_blocked(state, player_id, x, new_y):
            state['positions'][player_id] = (x, new_y, z)

    def move_left(self, state: dict[str, Any], player_id: str) -> None:
        x, y, z = state['positions'].get(player_id, (0, 0, 0))
        new_x = max(0, x - 1)
        if not self._is_blocked(state, player_id, new_x, y):
            state['positions'][player_id] = (new_x, y, z)

    def move_right(self, state: dict[str, Any], player_id: str) -> None:
        x, y, z = state['positions'].get(player_id, (0, 0, 0))
        new_x = min(state.get('map_width', 0) - 1, x + 1)
        if not self._is_blocked(state, player_id, new_x, y):
            state['positions'][player_id] = (new_x, y, z)

    def move_using_keyboard(
        self,
        event: tk.Event,
        state: dict[str, Any],
        width: int,
        height: int,
        player_id: str = "player1",
    ) -> None:
        keysym = getattr(event, "keysym", None)
        if keysym == 'w':
            self.move_up(state, player_id)
        elif keysym == 's':
            self.move_down(state, player_id)
        elif keysym == 'a':
            self.move_left(state, player_id)
        elif keysym == 'd':
            self.move_right(state, player_id)