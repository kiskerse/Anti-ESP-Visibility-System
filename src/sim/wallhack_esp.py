"""
Wallhack ESP que também mede vantagem real do cheat com e sem proteção PVS.

Protegido:  lê ClientPacket — mesmos dados do cliente legítimo.
Desprotegido: lê state bruto — vê todos os inimigos.
"""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from security.state import ClientPacket

FADE_TICKS = 6


class WallhackESP:

    def __init__(self, cell_size: int, map_w: int, map_h: int,
                 fps: int = 60, sem_protecao: bool = False, observer_team: str = "team_a") -> None:
        self.cell_size     = cell_size
        self.sem_protecao  = sem_protecao
        self.observer_team = observer_team

        self._packet:         ClientPacket | None = None
        self._raw_state:      dict | None = None
        self._visible_legit:  set[str] = set()

        self.advantage_history: list[int] = []
        self.total_ticks          = 0
        self.ticks_with_advantage = 0

        mode = "DESPROTEGIDO — cheat vê tudo" if sem_protecao else "PROTEGIDO — cheat filtrado"
        self.root = tk.Toplevel()
        self.root.title(f"ESP [{mode}]")
        self.root.configure(bg="#080808")
        w, h = map_w * cell_size, map_h * cell_size
        self.canvas = tk.Canvas(self.root, width=w, height=h,
                                bg="#080808", highlightthickness=0)
        self.canvas.pack()
        self._running  = True
        self._interval = int(max(1, 1000 / fps))
        self._loop()

    def deliver_packet(self, packet: "ClientPacket") -> None:
        self._packet = packet

    def deliver_raw(self, state: dict, visible_legit: set[str]) -> None:
        self._raw_state     = state
        self._visible_legit = visible_legit

    def _draw(self) -> None:
        self.canvas.delete("all")
        cs  = self.cell_size
        r   = max(3, cs // 3)
        adv = 0

        if self.sem_protecao and self._raw_state:
            legit = self._visible_legit
            teams = self._raw_state.get("teams", {})
            for pid, pos in self._raw_state["positions"].items():
                if teams.get(pid) == self.observer_team:
                    continue
                x, y, *_ = pos
                px, py = x * cs + cs / 2, y * cs + cs / 2
                extra  = pid not in legit
                color  = "#ff2222" if extra else "#ff8822"
                self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                        fill=color, outline="white", width=2)
                if extra:
                    self.canvas.create_text(px, py - r - 5, text="ESP!",
                                            fill="#ff2222", font=("Courier", 8, "bold"))
                    adv += 1

        elif not self.sem_protecao and self._packet:
            for epid in self._packet.all_enemy_pids():
                level = self._packet.level(epid)
                pos   = self._packet.pos(epid)
                dr    = self._packet.get(epid).get("predicted_px")
                if level == "full" and pos:
                    px, py = pos[0] * cs + cs / 2, pos[1] * cs + cs / 2
                    self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                            fill="#ff8822", outline="white")
                elif dr:
                    dpx, dpy = dr
                    self.canvas.create_oval(dpx - r, dpy - r, dpx + r, dpy + r,
                                            fill="#442200", outline="#664400", dash=(2, 3))

        self.total_ticks += 1
        self.advantage_history.append(adv)
        if len(self.advantage_history) > 300:
            self.advantage_history.pop(0)
        if adv > 0:
            self.ticks_with_advantage += 1

        avg = sum(self.advantage_history) / max(len(self.advantage_history), 1)
        pct = self.ticks_with_advantage / max(self.total_ticks, 1) * 100
        mode_str = "DESPROTEGIDO" if self.sem_protecao else "PROTEGIDO"
        col_m = "#ff4444" if self.sem_protecao else "#44ff44"
        self.canvas.create_text(4, 4, text=f"ESP {mode_str}", fill=col_m,
                                anchor="nw", font=("Courier", 8, "bold"))
        self.canvas.create_text(4, 16, text=f"Vantagem atual: {adv}  média: {avg:.1f}",
                                fill="#ffff00", anchor="nw", font=("Courier", 7))
        self.canvas.create_text(4, 27, text=f"Ticks c/ vantagem: {pct:.1f}%",
                                fill="#ffaa00", anchor="nw", font=("Courier", 7))

    def _loop(self) -> None:
        if not self._running:
            return
        try:
            self._draw()
        except Exception:
            pass
        self.root.after(self._interval, self._loop)

    def stop(self) -> None:
        self._running = False
        try:
            self.root.destroy()
        except Exception:
            pass

    def stats(self) -> dict:
        avg = sum(self.advantage_history) / max(len(self.advantage_history), 1)
        pct = self.ticks_with_advantage / max(self.total_ticks, 1) * 100
        return {"avg_advantage": round(avg, 2),
                "pct_ticks_with_advantage": round(pct, 1),
                "total_ticks": self.total_ticks}
