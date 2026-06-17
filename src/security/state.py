from __future__ import annotations
import time
from typing import Any


class StateMemory:
    """Shared memory bridge between server and client.

    The server is the sole writer; the client only reads.
    Includes a dead-reckoning layer so the client can predict smooth
    positions while waiting for the next server update, preventing
    teleport artifacts without leaking real coordinates.
    """

    def __init__(self) -> None:
        self.memory: dict[str, Any] = {}
        # dead-reckoning state: pid -> {pos, vel, ts}
        self._dr: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Server-side write API
    # ------------------------------------------------------------------

    def update_state(self, player_id: str, state: Any) -> None:
        """Server writes authoritative state for a player."""
        prev = self.memory.get(player_id)
        self.memory[player_id] = state

        # update dead-reckoning velocity estimate when we have a full position
        if isinstance(state, dict) and state.get("level") == "full":
            pos = state.get("pos")
            if pos is not None:
                now = time.monotonic()
                prev_dr = self._dr.get(player_id)
                if prev_dr is not None and prev_dr.get("pos") is not None:
                    dt = now - prev_dr["ts"]
                    if dt > 0:
                        px, py = prev_dr["pos"][0], prev_dr["pos"][1]
                        vx = (pos[0] - px) / dt
                        vy = (pos[1] - py) / dt
                    else:
                        vx, vy = 0.0, 0.0
                else:
                    vx, vy = 0.0, 0.0
                self._dr[player_id] = {"pos": pos, "vel": (vx, vy), "ts": now}

    def get_state(self, player_id: str) -> Any:
        """Client reads last authoritative state."""
        return self.memory.get(player_id)

    def get_predicted_pos(self, player_id: str, cell_size: int = 50) -> tuple[float, float] | None:
        """Return a dead-reckoning predicted pixel position for *player_id*.

        Used by the client renderer to smoothly extrapolate position between
        server ticks — no new information is revealed, only extrapolated from
        what was already received.

        Returns pixel coords (px, py) or None if insufficient data.
        """
        dr = self._dr.get(player_id)
        if dr is None:
            return None
        pos = dr.get("pos")
        if pos is None:
            return None
        vx, vy = dr.get("vel", (0.0, 0.0))
        dt = time.monotonic() - dr["ts"]
        # clamp extrapolation to 250 ms to avoid wild predictions
        dt = min(dt, 0.25)
        pred_gx = pos[0] + vx * dt
        pred_gy = pos[1] + vy * dt
        return (
            pred_gx * cell_size + cell_size / 2,
            pred_gy * cell_size + cell_size / 2,
        )

    def get_all_states(self) -> dict[str, Any]:
        return self.memory

    def remove_state(self, player_id: str) -> None:
        self.memory.pop(player_id, None)
        self._dr.pop(player_id, None)

    def clear_memory(self) -> None:
        self.memory.clear()
        self._dr.clear()
