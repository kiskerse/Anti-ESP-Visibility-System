from __future__ import annotations
import time
from typing import Any


# Tipos permitidos de visibilidade
VALID_LEVELS = {"full", "partial", "position_only", "none"}


class ClientPacket:
    """O que o servidor envia ao cliente por tick.

    O cliente só enxerga este objeto — jamais o state bruto do servidor.
    Contém apenas o que cada nível de visibilidade permite revelar.
    """

    def __init__(self, entries: dict[str, dict], obstacles: list) -> None:
        # entries: {pid: {"level": str, "pos": tuple|None}}
        self._entries = entries
        self.obstacles = obstacles  # obstáculos são públicos (o mapa é visível)

    def get(self, pid: str) -> dict:
        """Retorna o pacote de um jogador específico. Sempre seguro."""
        return self._entries.get(pid, {"level": "none", "pos": None})

    def all_pids(self) -> list[str]:
        """Lista de IDs presentes neste pacote."""
        return list(self._entries.keys())

    def level(self, pid: str) -> str:
        return self._entries.get(pid, {}).get("level", "none")

    def pos(self, pid: str) -> tuple | None:
        return self._entries.get(pid, {}).get("pos", None)


class StateMemory:
    """Memória interna do servidor com dead-reckoning.

    O servidor escreve via update().
    O cliente recebe apenas via get_client_packet() — um snapshot somente-leitura.
    O cliente nunca tem acesso a este objeto diretamente.
    """

    def __init__(self) -> None:
        # estado autorizado por zona: {pid: {"level": str, "pos": tuple|None}}
        self._state: dict[str, dict] = {}
        # dead-reckoning: {pid: {"pos": tuple, "vel": tuple, "ts": float}}
        self._dr: dict[str, dict] = {}
        # obstáculos (público — o mapa é visível)
        self._obstacles: list = []

    # ------------------------------------------------------------------
    # API do servidor (escrita)
    # ------------------------------------------------------------------

    def set_obstacles(self, obstacles: list) -> None:
        self._obstacles = obstacles

    def update(self, pid: str, level: str, pos: tuple | None) -> None:
        """Servidor escreve o resultado de visibilidade para um jogador."""
        assert level in VALID_LEVELS, f"Nível inválido: {level}"

        self._state[pid] = {"level": level, "pos": pos}

        # atualiza dead-reckoning apenas quando temos posição exata
        if level == "full" and pos is not None:
            now = time.monotonic()
            prev = self._dr.get(pid)
            if prev is not None:
                dt = now - prev["ts"]
                if dt > 0:
                    vx = (pos[0] - prev["pos"][0]) / dt
                    vy = (pos[1] - prev["pos"][1]) / dt
                else:
                    vx, vy = 0.0, 0.0
            else:
                vx, vy = 0.0, 0.0
            self._dr[pid] = {"pos": pos, "vel": (vx, vy), "ts": now}

        # limpa DR quando não visível (evita cheat ler última posição)
        elif level == "none":
            dr = self._dr.get(pid)
            if dr is not None:
                dt = time.monotonic() - dr["ts"]
                if dt > 0.25:  # grace period de 250ms para o ghost DR
                    self._dr.pop(pid, None)

    def remove(self, pid: str) -> None:
        self._state.pop(pid, None)
        self._dr.pop(pid, None)

    def clear(self) -> None:
        self._state.clear()
        self._dr.clear()

    # ------------------------------------------------------------------
    # Dead-reckoning (uso interno do servidor para compor o pacote)
    # ------------------------------------------------------------------

    def _get_dr_predicted_pos(self, pid: str, cell_size: int) -> tuple[float, float] | None:
        """Posição extrapolada pelo DR — só usada internamente pelo servidor
        ao compor o ClientPacket. O cliente nunca chama isso."""
        dr = self._dr.get(pid)
        if dr is None:
            return None
        dt = time.monotonic() - dr["ts"]
        if dt > 0.25:
            self._dr.pop(pid, None)
            return None
        vx, vy = dr["vel"]
        px = dr["pos"][0] + vx * dt
        py = dr["pos"][1] + vy * dt
        return (
            px * cell_size + cell_size / 2,
            py * cell_size + cell_size / 2,
        )

    # ------------------------------------------------------------------
    # API do cliente (leitura — único ponto de saída)
    # ------------------------------------------------------------------

    def get_client_packet(self, cell_size: int = 50) -> ClientPacket:
        """Servidor chama isso e entrega o resultado ao cliente.

        O cliente jamais tem acesso ao StateMemory em si.
        O ClientPacket é somente-leitura e contém apenas dados autorizados.
        """
        entries: dict[str, dict] = {}

        for pid, data in self._state.items():
            level = data["level"]
            pos = data["pos"]

            if level == "full":
                # posição exata + previsão DR para suavização
                dr_px = self._get_dr_predicted_pos(pid, cell_size)
                entries[pid] = {
                    "level": "full",
                    "pos": pos,
                    "predicted_px": dr_px,  # pixel coords para lerp no cliente
                }

            elif level in ("partial", "position_only"):
                entries[pid] = {"level": level, "pos": pos, "predicted_px": None}

            else:  # none
                # inclui ghost DR se ainda dentro do grace period
                dr_px = self._get_dr_predicted_pos(pid, cell_size)
                entries[pid] = {
                    "level": "none",
                    "pos": None,
                    "predicted_px": dr_px,  # None se expirou
                }

        return ClientPacket(entries, self._obstacles)
