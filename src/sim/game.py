"""
Servidor — PVS + Smokes + Entry Masking + Hysteresis (128 TPS).

Máquina de estados de visibilidade por par (observer, enemy):

  ┌──────────────────────────────────────────────────────────────────┐
  │                   NONE                                           │
  │       (nada na memória — LOS=false ou não confirmado)            │
  └──────────────┬───────────────────────────────────────────────────┘
                 │ LOS=true por HYSTERESIS_TICKS consecutivos
                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                  ENTERING                                        │
  │       (posição arredondada ENTRY_MASK_GRID por ENTRY_MASK_TICKS) │
  │       ← evita revelar ponto exato de entrada no LOS             │
  └──────────────┬───────────────────────────────────────────────────┘
                 │ após ENTRY_MASK_TICKS
                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                  VISIBLE                                         │
  │       (posição exata enviada ao cliente)                         │
  └──────────────┬───────────────────────────────────────────────────┘
                 │ LOS=false por HYSTERESIS_TICKS consecutivos
                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                  NONE  (DR ativo por adaptive_dr_cap_ms)         │
  └──────────────────────────────────────────────────────────────────┘

Parâmetros tuning:
  HYSTERESIS_TICKS  = 1  → 7.8ms @ 128 TPS (evita flickering em borda de LOS)
  ENTRY_MASK_TICKS  = 1  → 7.8ms @ 128 TPS
  ENTRY_MASK_GRID   = 4  → +/-2 células de incerteza na posição de entrada
"""

from __future__ import annotations

import random
import tkinter as tk
from dataclasses import dataclass
from typing import Any

from security.pvs   import PVSIndex, Cell
from security.smoke import SmokeSystem
from security.state import StateMemory, _round_to_grid, ENTRY_MASK_GRID


# Parâmetros da máquina de estados
HYSTERESIS_TICKS = 1   # ticks consecutivos para confirmar mudança de LOS
ENTRY_MASK_TICKS = 1   # ticks de posição mascarada antes de revelar exata


@dataclass
class VisInfo:
    """Estado de visibilidade de um par (observador, alvo)."""
    state:           str   = "none"      # "none" | "entering" | "visible"
    confirm_ticks:   int   = 0           # ticks consecutivos no estado atual
    entry_ticks:     int   = 0           # ticks em "entering"


class Game:

    def __init__(
        self,
        config:    dict[str, Any],
        pvs_index: PVSIndex,
        smoke_sys: SmokeSystem,
        create_ui: bool = True,
    ) -> None:
        self.map_w     = config["map_w"]
        self.map_h     = config["map_h"]
        self.cell_size = config["cell_size"]
        self.pvs       = pvs_index
        self.smoke_sys = smoke_sys
        self.obstacles: list[tuple] = config.get("obstacles", [])

        self._solid = frozenset(
            (x, y)
            for (ox, oy, ow, oh, *_) in self.obstacles
            for x in range(ox, ox + ow)
            for y in range(oy, oy + oh)
        )

        # máquina de estados: {obs_pid: {tgt_pid: VisInfo}}
        self._vis: dict[str, dict[str, VisInfo]] = {}

        self.canvas = None
        self.root   = None
        if create_ui:
            self.root = tk.Toplevel()
            self.root.title("Servidor — visão omnisciente")
            w = self.map_w * self.cell_size
            h = self.map_h * self.cell_size
            self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#0d0d0d")
            self.canvas.pack()

    # Helpers

    def pos_to_cell(self, x: float, y: float) -> Cell:
        return Cell(int(x), int(y))

    def is_solid(self, x: int, y: int) -> bool:
        return (x, y) in self._solid

    def _masked_pos(self, x: float, y: float, z: float) -> tuple:
        """Posição arredondada para ENTRY_MASK_GRID — usada no tick de entrada."""
        return (_round_to_grid(x, ENTRY_MASK_GRID),
                _round_to_grid(y, ENTRY_MASK_GRID),
                z)

    # Máquina de estados de visibilidade

    def _update_vis_state(
        self,
        obs_pid: str,
        tgt_pid: str,
        los_raw: bool,       # resultado bruto do PVS + smoke
        tgt_pos: tuple,
        memory:  StateMemory,
    ) -> None:
        """Atualiza o estado de visibilidade e escreve na StateMemory."""

        obs_map = self._vis.setdefault(obs_pid, {})
        vi = obs_map.get(tgt_pid, VisInfo())
        x, y, *rest = tgt_pos
        z = rest[0] if rest else 0

        # transição baseada no estado atual

        if vi.state == "none":
            if los_raw:
                vi.confirm_ticks += 1
                if vi.confirm_ticks >= HYSTERESIS_TICKS:
                    # confirmado: entra em ENTERING
                    vi = VisInfo("entering", 0, 1)
                    memory.update_enemy(tgt_pid, "entering", self._masked_pos(x, y, z))
                else:
                    memory.update_enemy(tgt_pid, "none", None)
            else:
                vi = VisInfo("none", 0, 0)
                memory.update_enemy(tgt_pid, "none", None)

        elif vi.state == "entering":
            if not los_raw:
                # saiu do LOS durante entry masking — volta a none
                vi = VisInfo("none", 0, 0)
                memory.update_enemy(tgt_pid, "none", None)
            elif vi.entry_ticks >= ENTRY_MASK_TICKS:
                # mascaramento concluído — promove para visible com posição exata
                vi = VisInfo("visible", 0, 0)
                memory.update_enemy(tgt_pid, "full", tgt_pos)
            else:
                vi.entry_ticks += 1
                memory.update_enemy(tgt_pid, "entering", self._masked_pos(x, y, z))

        elif vi.state == "visible":
            if not los_raw:
                vi.confirm_ticks += 1
                if vi.confirm_ticks >= HYSTERESIS_TICKS:
                    # confirmado: saiu de LOS → none (DR assume)
                    vi = VisInfo("none", 0, 0)
                    memory.update_enemy(tgt_pid, "none", None)
                else:
                    # ainda "visible" por histerese — mantém última posição
                    memory.update_enemy(tgt_pid, "full", tgt_pos)
            else:
                vi = VisInfo("visible", 0, 0)
                memory.update_enemy(tgt_pid, "full", tgt_pos)

        obs_map[tgt_pid] = vi

    # Tick principal

    def tick(
        self,
        state:    dict[str, Any],
        memories: dict[str, StateMemory],
    ) -> None:
        positions = state["positions"]
        team_map  = state["teams"]
        smokes    = self.smoke_sys.active_smokes()

        for obs_pid, obs_pos in positions.items():
            obs_x, obs_y, *_ = obs_pos
            obs_cell = self.pos_to_cell(obs_x, obs_y)
            obs_team = team_map[obs_pid]
            mem      = memories[obs_pid]

            mem.set_obstacles(self.obstacles)
            mem.set_smokes(self.smoke_sys.get_snapshot())
            mem.update_ally(obs_pid, obs_pos)

            visible_cells = self.pvs.visible_from(obs_cell)

            for tgt_pid, tgt_pos in positions.items():
                if tgt_pid == obs_pid:
                    continue
                tgt_x, tgt_y, *_ = tgt_pos
                tgt_cell  = self.pos_to_cell(tgt_x, tgt_y)
                same_team = team_map[tgt_pid] == obs_team

                if same_team:
                    mem.update_ally(tgt_pid, tgt_pos)
                    continue

                # PVS lookup 
                in_pvs = tgt_cell in visible_cells

                # smoke override 
                if in_pvs:
                    blocked = self.smoke_sys.blocks_los(
                        obs_x + 0.5, obs_y + 0.5,
                        tgt_x + 0.5, tgt_y + 0.5,
                    )
                    los_raw = not blocked
                else:
                    los_raw = False

                self._update_vis_state(obs_pid, tgt_pid, los_raw, tgt_pos, mem)

        self.smoke_sys.tick()

    # Smoke spawn aleatório

    def maybe_spawn_smoke(self, state: dict, prob: float = 0.002) -> None:
        if random.random() < prob:
            for _ in range(50):
                sx = random.randint(5, self.map_w - 5)
                sy = random.randint(5, self.map_h - 5)
                if not self.is_solid(sx, sy):
                    self.smoke_sys.add_smoke(sx, sy, radius=3.0, duration_ticks=600)
                    break

    # Desenho servidor

    def draw(self, state: dict[str, Any]) -> None:
        if not self.canvas or not self.root:
            return
        self.canvas.delete("all")
        cs = self.cell_size

        for obs in self.obstacles:
            ox, oy, ow, oh, *_ = obs
            self.canvas.create_rectangle(
                ox*cs, oy*cs, (ox+ow)*cs, (oy+oh)*cs,
                fill="#444", outline="#666",
            )

        for s in self.smoke_sys.active_smokes():
            r = s.radius * cs
            self.canvas.create_oval(
                s.cx*cs - r, s.cy*cs - r, s.cx*cs + r, s.cy*cs + r,
                fill="#88aaaa", outline="#aadddd", stipple="gray50",
            )

        team_map = state["teams"]
        for pid, pos in state["positions"].items():
            x, y, *_ = pos
            cx_px = x*cs + cs/2
            cy_px = y*cs + cs/2
            r     = max(3, cs//3)
            color = "#4488ff" if team_map.get(pid) == "team_a" else "#ff4444"
            self.canvas.create_oval(cx_px-r, cy_px-r, cx_px+r, cy_px+r,
                                    fill=color, outline="white", width=1)
            self.canvas.create_text(cx_px, cy_px-r-3, text=pid[-2:],
                                    fill="white", font=("Courier", 6))

        self.root.update_idletasks()
        self.root.update()
