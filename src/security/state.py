from __future__ import annotations
import time
from typing import Any

VALID_LEVELS = {"full", "partial", "position_only", "none"}


class ClientPacket:
    """O que o servidor envia ao cliente por tick — somente-leitura."""

    def __init__(self, entries: dict[str, dict], obstacles: list) -> None:
        self._entries = entries
        self.obstacles = obstacles

    def get(self, pid: str) -> dict:
        return self._entries.get(pid, {"level": "none", "pos": None, "predicted_px": None})

    def all_pids(self) -> list[str]:
        return list(self._entries.keys())

    def level(self, pid: str) -> str:
        return self._entries.get(pid, {}).get("level", "none")

    def pos(self, pid: str) -> tuple | None:
        return self._entries.get(pid, {}).get("pos", None)


class StateMemory:
    """
    Memória interna do servidor com dead-reckoning.
    Servidor escreve via update(). Cliente recebe APENAS via get_client_packet().
    """

    # Grace period do DR: quanto tempo o ghost permanece ativo após zone=none
    DR_CAP_S: float = 0.25

    def __init__(self) -> None:
        self._state: dict[str, dict] = {}
        # DR: {pid: {pos, vel, ts, jitter_buf: list[float]}}
        self._dr: dict[str, dict] = {}
        self._obstacles: list = []

    def set_obstacles(self, obstacles: list) -> None:
        self._obstacles = obstacles

    def update(self, pid: str, level: str, pos: tuple | None) -> None:
        assert level in VALID_LEVELS, f"Nível inválido: {level}"
        self._state[pid] = {"level": level, "pos": pos}

        if level == "full" and pos is not None:
            now = time.monotonic()
            prev = self._dr.get(pid)
            if prev is not None:
                dt = now - prev["ts"]
                if dt > 0:
                    vx = (pos[0] - prev["pos"][0]) / dt
                    vy = (pos[1] - prev["pos"][1]) / dt
                    # mantém buffer de jitter (últimos 8 inter-tick intervals)
                    jbuf = prev.get("jitter_buf", [])
                    jbuf.append(dt * 1000.0)
                    if len(jbuf) > 8:
                        jbuf.pop(0)
                else:
                    vx, vy = 0.0, 0.0
                    jbuf = prev.get("jitter_buf", [])
            else:
                vx, vy = 0.0, 0.0
                jbuf = []
            self._dr[pid] = {"pos": pos, "vel": (vx, vy), "ts": now, "jitter_buf": jbuf}

        elif level == "none":
            dr = self._dr.get(pid)
            if dr is not None:
                if time.monotonic() - dr["ts"] > self.DR_CAP_S:
                    self._dr.pop(pid, None)

    def remove(self, pid: str) -> None:
        self._state.pop(pid, None)
        self._dr.pop(pid, None)

    def clear(self) -> None:
        self._state.clear()
        self._dr.clear()

    def _get_dr_predicted_pos(self, pid: str, cell_size: int) -> tuple[float, float] | None:
        dr = self._dr.get(pid)
        if dr is None:
            return None
        dt = time.monotonic() - dr["ts"]
        if dt > self.DR_CAP_S:
            self._dr.pop(pid, None)
            return None
        vx, vy = dr["vel"]
        px = dr["pos"][0] + vx * dt
        py = dr["pos"][1] + vy * dt
        return (px * cell_size + cell_size / 2, py * cell_size + cell_size / 2)

    def get_client_packet(self, cell_size: int = 50) -> "ClientPacket":
        entries: dict[str, dict] = {}
        for pid, data in self._state.items():
            level = data["level"]
            pos   = data["pos"]
            if level == "full":
                dr_px = self._get_dr_predicted_pos(pid, cell_size)
                entries[pid] = {"level": "full", "pos": pos, "predicted_px": dr_px}
            elif level in ("partial", "position_only"):
                entries[pid] = {"level": level, "pos": pos, "predicted_px": None}
            else:
                dr_px = self._get_dr_predicted_pos(pid, cell_size)
                entries[pid] = {"level": "none", "pos": None, "predicted_px": dr_px}
        return ClientPacket(entries, self._obstacles)
