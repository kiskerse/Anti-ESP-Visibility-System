"""
StateMemory + ClientPacket — ponte servidor→cliente.

Novidades para 128 TPS:
  - Nível "entering" para entry masking (posição arredondada 1 tick)
  - DR cap adaptativo por ping estimado
  - Remoção imediata de DR quando cap expira (sem janela residual)
"""
from __future__ import annotations

import time
from typing import Any

# Levels válidos escritos pelo servidor
VALID_LEVELS = {"full", "entering", "none"}

# Resolução do grid de mascaramento de entrada (células)
ENTRY_MASK_GRID = 4   # arredonda para múltiplo de 4 células

# DR cap padrão e limites (ms)
DR_CAP_DEFAULT_MS = 120.0
DR_CAP_MIN_MS     = 50.0
DR_CAP_MAX_MS     = 150.0


def _round_to_grid(val: float, grid: int = ENTRY_MASK_GRID) -> int:
    """Arredonda para o múltiplo de `grid` mais próximo."""
    return round(val / grid) * grid


def adaptive_dr_cap_ms(rtt_ms: float) -> float:
    """
    Cap de DR adaptativo ao RTT estimado do jogador.

    Fórmula: clamp(2 × RTT, DR_CAP_MIN_MS, DR_CAP_MAX_MS)

    São Paulo (30ms RTT) → 60ms  (~8 ticks @ 128 TPS)
    Manaus (120ms RTT)   → 150ms (~19 ticks @ 128 TPS)
    London (180ms RTT)   → 150ms (cap máximo)

    Reduz exposição de ghost vs cap fixo de 250ms.
    """
    return max(DR_CAP_MIN_MS, min(DR_CAP_MAX_MS, 2.0 * rtt_ms))


class ClientPacket:
    """Snapshot somente-leitura entregue pelo servidor ao cliente."""

    def __init__(
        self,
        entries:   dict[str, dict],
        obstacles: list,
        smokes:    list[dict],
        allies:    dict[str, tuple],
    ) -> None:
        self._entries  = entries
        self.obstacles = obstacles
        self.smokes    = smokes
        self.allies    = allies

    def get(self, pid: str) -> dict:
        return self._entries.get(pid, {"level": "none", "pos": None, "predicted_px": None})

    def all_enemy_pids(self) -> list[str]:
        return list(self._entries.keys())

    def level(self, pid: str) -> str:
        return self._entries.get(pid, {}).get("level", "none")

    def pos(self, pid: str) -> tuple | None:
        return self._entries.get(pid, {}).get("pos", None)

    def is_entering(self, pid: str) -> bool:
        """True se este é um tick de entry masking (posição arredondada)."""
        return self._entries.get(pid, {}).get("entering", False)


class StateMemory:
    """
    Memória interna do servidor.

    Separação por time:
      - Aliados: sempre full
      - Inimigos: filtrado por PVS + smokes + entry masking
    """

    def __init__(self, rtt_ms: float = 30.0) -> None:
        self._enemy_state: dict[str, dict] = {}
        self._ally_state:  dict[str, tuple] = {}
        self._dr:          dict[str, dict]  = {}
        self._obstacles:   list = []
        self._smokes:      list[dict] = []
        self._dr_cap_s     = adaptive_dr_cap_ms(rtt_ms) / 1000.0

    def set_rtt(self, rtt_ms: float) -> None:
        self._dr_cap_s = adaptive_dr_cap_ms(rtt_ms) / 1000.0

    def set_obstacles(self, obstacles: list) -> None:
        self._obstacles = obstacles

    def set_smokes(self, smokes: list[dict]) -> None:
        self._smokes = smokes

    def update_ally(self, pid: str, pos: tuple) -> None:
        self._ally_state[pid] = pos

    def update_enemy(self, pid: str, level: str, pos: tuple | None) -> None:
        """
        level="full"     → posição exata (inimigo totalmente visível)
        level="entering" → posição mascarada (1 tick de entry masking)
        level="none"     → não visível, nada na memória de posição
        """
        assert level in VALID_LEVELS, f"level inválido: {level}"
        self._enemy_state[pid] = {"level": level, "pos": pos}

        now = time.monotonic()

        if level in ("full", "entering") and pos is not None:
            prev = self._dr.get(pid)
            if prev is not None and level == "full":
                # só atualiza velocidade quando temos posição exata
                dt = now - prev["ts"]
                if dt > 0:
                    vx = (pos[0] - prev["pos"][0]) / dt
                    vy = (pos[1] - prev["pos"][1]) / dt
                    jbuf = prev.get("jitter_buf", [])
                    jbuf.append(dt * 1000.0)
                    if len(jbuf) > 8:
                        jbuf.pop(0)
                else:
                    vx, vy = 0.0, 0.0
                    jbuf = prev.get("jitter_buf", [])
            else:
                # primeira aparição ou entering: não temos velocidade ainda
                vx, vy = 0.0, 0.0
                jbuf   = []
            self._dr[pid] = {"pos": pos, "vel": (vx, vy), "ts": now, "jitter_buf": jbuf}

        elif level == "none":
            # limpa DR se cap expirou; mantém enquanto dentro do cap
            dr = self._dr.get(pid)
            if dr is not None and (now - dr["ts"]) > self._dr_cap_s:
                # apaga completamente — sem residual na memória
                del self._dr[pid]

    def remove(self, pid: str) -> None:
        self._enemy_state.pop(pid, None)
        self._ally_state.pop(pid, None)
        self._dr.pop(pid, None)

    def clear(self) -> None:
        self._enemy_state.clear()
        self._ally_state.clear()
        self._dr.clear()

    def _dr_predicted_px(self, pid: str, cell_size: int) -> tuple | None:
        dr = self._dr.get(pid)
        if dr is None:
            return None
        now = time.monotonic()
        dt  = now - dr["ts"]
        if dt > self._dr_cap_s:
            # expirou — remove e retorna None (nada na memória)
            del self._dr[pid]
            return None
        vx, vy = dr["vel"]
        px = dr["pos"][0] + vx * dt
        py = dr["pos"][1] + vy * dt
        return (px * cell_size + cell_size / 2, py * cell_size + cell_size / 2)

    def get_client_packet(self, observer_pid: str, cell_size: int = 50) -> ClientPacket:
        entries: dict[str, dict] = {}

        for pid, data in self._enemy_state.items():
            level = data["level"]
            pos   = data["pos"]

            if level in ("full", "entering") and pos is not None:
                dr_px   = self._dr_predicted_px(pid, cell_size)
                is_ent  = (level == "entering")
                entries[pid] = {
                    "level":     "full",    # cliente nunca sabe que é "entering"
                    "pos":       pos,       # pode ser arredondada (se entering)
                    "predicted_px": dr_px,
                    "entering":  is_ent,    # flag interna para métricas
                }
            else:
                dr_px = self._dr_predicted_px(pid, cell_size)
                entries[pid] = {
                    "level":     "none",
                    "pos":       None,
                    "predicted_px": dr_px,
                    "entering":  False,
                }

        allies = dict(self._ally_state)
        allies.pop(observer_pid, None)
        return ClientPacket(entries, self._obstacles, list(self._smokes), allies)
